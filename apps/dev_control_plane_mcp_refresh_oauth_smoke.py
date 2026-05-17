"""Smoke-check MCP OAuth offline_access refresh-token rotation and reuse handling."""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from tempfile import TemporaryDirectory
from typing import Any, Mapping
from urllib import error as urllib_error, parse, request as urllib_request

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "apps" / "dev_control_plane_server.py"


def main() -> None:
    port = _free_port()
    with TemporaryDirectory(prefix="dev-control-plane-mcp-refresh-") as tmp_raw:
        tmp = Path(tmp_raw)
        state_dir = tmp / "state"
        process = _start_server(port, state_dir, tmp)
        try:
            base_url = f"http://127.0.0.1:{port}"
            _wait_ready(base_url)
            resource = f"{base_url}/mcp"

            metadata = _get_json(f"{base_url}/.well-known/oauth-authorization-server")
            if "refresh_token" not in metadata.get("grant_types_supported", []):
                raise AssertionError(f"authorization metadata must support refresh_token grant: {metadata}")
            if "offline_access" not in metadata.get("scopes_supported", []):
                raise AssertionError(f"authorization metadata must support offline_access scope: {metadata}")

            client = _post_json(
                f"{base_url}/oauth/register",
                {"client_name": "MCP refresh smoke", "redirect_uris": ["http://127.0.0.1/callback"]},
            )
            client_id = str(client.get("client_id") or "")
            verifier = "refresh-smoke-verifier-0123456789abcdefghijklmnopqrstuvwxyz"
            auth_params = {
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": "http://127.0.0.1/callback",
                "scope": "dcp.write offline_access",
                "state": "refresh-smoke-state",
                "resource": resource,
                "code_challenge": _pkce_challenge(verifier),
                "code_challenge_method": "S256",
            }
            redirect = _post_form_no_redirect(f"{base_url}/oauth/authorize", auth_params)
            code = parse.parse_qs(parse.urlparse(redirect).query).get("code", [""])[0]
            token = _post_form(
                f"{base_url}/oauth/token",
                {
                    "grant_type": "authorization_code",
                    "client_id": client_id,
                    "redirect_uri": "http://127.0.0.1/callback",
                    "code": code,
                    "code_verifier": verifier,
                    "resource": resource,
                },
            )
            access_token = str(token.get("access_token") or "")
            refresh_token = str(token.get("refresh_token") or "")
            if not access_token or not refresh_token or token.get("scope") != "dcp.write offline_access":
                raise AssertionError(f"offline authorization_code exchange must issue scoped access + refresh tokens: {token}")

            status = _tool(base_url, "get_status", {}, token=access_token)
            oauth_status = (status.get("mcp") or {}).get("oauth") or {}
            if oauth_status.get("refresh_supported") is not True or oauth_status.get("active_refresh_tokens_count") != 1:
                raise AssertionError(f"get_status must report active refresh support: {oauth_status}")

            refreshed = _post_form(
                f"{base_url}/oauth/token",
                {"grant_type": "refresh_token", "client_id": client_id, "refresh_token": refresh_token, "resource": resource},
            )
            rotated_access = str(refreshed.get("access_token") or "")
            rotated_refresh = str(refreshed.get("refresh_token") or "")
            if not rotated_access or not rotated_refresh or rotated_refresh == refresh_token:
                raise AssertionError(f"refresh grant must rotate access and refresh tokens: {refreshed}")
            rotated_status = _tool(base_url, "get_status", {}, token=rotated_access)
            rotated_oauth = (rotated_status.get("mcp") or {}).get("oauth") or {}
            if rotated_oauth.get("active_refresh_tokens_count") != 1 or rotated_oauth.get("revoked_refresh_tokens_count", 0) < 1:
                raise AssertionError(f"refresh rotation must leave one active token and one revoked old token: {rotated_oauth}")

            reuse = _post_form_expect_error(
                f"{base_url}/oauth/token",
                {"grant_type": "refresh_token", "client_id": client_id, "refresh_token": refresh_token, "resource": resource},
            )
            if reuse.get("oauth_error_code") != "refresh_token_reuse_detected":
                raise AssertionError(f"old refresh token reuse must be detected: {reuse}")
            after_reuse = _tool(base_url, "start_wb_core_auto_task", {"task_text": "must be denied after refresh family revoke"}, token=rotated_access)
            if after_reuse.get("status") != "denied":
                raise AssertionError(f"refresh token family revoke must revoke issued access tokens: {after_reuse}")

            _write_expired_refresh_token(state_dir, client_id, resource)
            expired = _post_form_expect_error(
                f"{base_url}/oauth/token",
                {"grant_type": "refresh_token", "client_id": client_id, "refresh_token": "dcp-refresh-expired-smoke", "resource": resource},
            )
            if expired.get("oauth_error_code") != "refresh_token_expired":
                raise AssertionError(f"expired refresh token must return stable reason: {expired}")

            _assert_no_raw_secret_state(state_dir, [access_token, refresh_token, rotated_access, rotated_refresh, code, verifier])
            status_text = json.dumps(_get_json(base_url + "/mcp"), ensure_ascii=False, sort_keys=True)
            for forbidden in ('"access_token"', '"refresh_token"', "Bearer "):
                if forbidden in status_text:
                    raise AssertionError(f"public MCP status leaked token material marker {forbidden}")
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

    print("dev-control-plane-mcp-refresh-oauth-smoke passed")


def _write_expired_refresh_token(state_dir: Path, client_id: str, resource: str) -> None:
    path = state_dir / "collections" / "mcp_oauth_refresh_tokens.json"
    tokens = _read_json(path)
    tokens[_sha256("dcp-refresh-expired-smoke")] = {
        "client_id": client_id,
        "scope": "dcp.write offline_access",
        "resource": resource,
        "refresh_family_id": "dcp-family-expired-smoke",
        "status": "active",
        "created_at": "2026-01-01T00:00:00Z",
        "expires_at_epoch": time.time() - 1,
    }
    _write_json(path, tokens)


def _assert_no_raw_secret_state(state_dir: Path, raw_values: list[str]) -> None:
    text = "\n".join(path.read_text(encoding="utf-8", errors="replace") for path in state_dir.rglob("*") if path.is_file())
    for value in raw_values:
        if value and value in text:
            raise AssertionError("raw OAuth token, code or verifier leaked into state")
    if "Authorization:" in text or "Bearer " in text:
        raise AssertionError("raw Authorization/Bearer material leaked into state")


def _mcp(base_url: str, method: str, params: Mapping[str, Any], *, token: str | None = None) -> dict[str, Any]:
    body = json.dumps({"jsonrpc": "2.0", "id": f"smoke-{time.time_ns()}", "method": method, "params": params}).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib_request.Request(base_url + "/mcp", data=body, method="POST", headers=headers)
    with urllib_request.urlopen(req, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if "error" in payload:
        raise AssertionError(f"MCP error for {method}: {payload}")
    return payload.get("result") or {}


def _tool(base_url: str, name: str, arguments: Mapping[str, Any], *, token: str | None = None) -> dict[str, Any]:
    result = _mcp(base_url, "tools/call", {"name": name, "arguments": dict(arguments)}, token=token)
    structured = result.get("structuredContent")
    if isinstance(structured, dict):
        return structured
    content = result.get("content", [])
    if content and isinstance(content[0], dict):
        return json.loads(content[0].get("text") or "{}")
    return {}


def _start_server(port: int, state_dir: Path, tmp: Path) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [sys.executable, str(SERVER), "--host", "127.0.0.1", "--port", str(port), "--state-dir", str(state_dir)],
        cwd=ROOT,
        env=_server_env(tmp),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _server_env(tmp: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("OPENAI_API_KEY", None)
    env.pop("DEV_CONTROL_PLANE_MCP_TOKEN", None)
    env["DEV_CONTROL_PLANE_SECRET_HOME"] = str(tmp / "secrets")
    env["DEV_CONTROL_PLANE_MCP_FAKE_RUNS"] = "1"
    env["DEV_CONTROL_PLANE_WB_CORE_AUTO_TASK_MODE"] = "stub"
    env["DEV_CONTROL_PLANE_ENABLE_FAKE_CURATOR"] = "1"
    return env


def _get_json(url: str) -> dict[str, Any]:
    with urllib_request.urlopen(url, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _post_json(url: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    body = json.dumps(dict(payload)).encode("utf-8")
    req = urllib_request.Request(url, data=body, method="POST", headers={"Content-Type": "application/json"})
    with urllib_request.urlopen(req, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _post_form(url: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    body = parse.urlencode(dict(payload)).encode("utf-8")
    req = urllib_request.Request(url, data=body, method="POST", headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib_request.urlopen(req, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _post_form_expect_error(url: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    try:
        success = _post_form(url, payload)
    except urllib_error.HTTPError as exc:
        return json.loads(exc.read().decode("utf-8"))
    raise AssertionError(f"expected OAuth error, got success: {success}")


def _post_form_no_redirect(url: str, payload: Mapping[str, Any]) -> str:
    class NoRedirect(urllib_request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
            return None

    opener = urllib_request.build_opener(NoRedirect)
    body = parse.urlencode(dict(payload)).encode("utf-8")
    req = urllib_request.Request(url, data=body, method="POST", headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        opener.open(req, timeout=10)
    except urllib_error.HTTPError as exc:
        if exc.code == 302:
            return str(exc.headers.get("Location") or "")
        raise
    raise AssertionError("authorization approval must redirect")


def _wait_ready(base_url: str) -> None:
    deadline = time.time() + 10
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            _get_json(base_url + "/api/state")
            return
        except Exception as exc:
            last_error = exc
            time.sleep(0.1)
    raise AssertionError(f"server did not become ready: {last_error}")


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise AssertionError(f"expected JSON object at {path}")
    return loaded


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


if __name__ == "__main__":
    main()
