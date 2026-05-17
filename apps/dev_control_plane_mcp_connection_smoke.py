"""Smoke-check the stable ChatGPT-style MCP connection contract."""

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
SRC = ROOT / "src"
for path in (SRC, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dev_control_plane.mcp import MCP_CONNECTION_CONTRACT_VERSION, MCP_PUBLIC_URL  # noqa: E402

SERVER = ROOT / "apps" / "dev_control_plane_server.py"


def main() -> None:
    port = _free_port()
    with TemporaryDirectory(prefix="dev-control-plane-mcp-connection-") as tmp_raw:
        tmp = Path(tmp_raw)
        state_dir = tmp / "state"
        process = _start_server(port, state_dir, tmp)
        try:
            base_url = f"http://127.0.0.1:{port}"
            _wait_ready(base_url)
            resource = f"{base_url}/mcp"

            protected = _get_json(f"{base_url}/.well-known/oauth-protected-resource/mcp")
            if protected.get("resource") != resource or base_url not in protected.get("authorization_servers", []):
                raise AssertionError(f"protected resource metadata must bind local MCP resource: {protected}")
            issuer = _get_json(f"{base_url}/.well-known/oauth-authorization-server")
            if issuer.get("issuer") != base_url or issuer.get("token_endpoint") != f"{base_url}/oauth/token":
                raise AssertionError(f"authorization server metadata must be stable and local to request host: {issuer}")

            public_status = _get_json(base_url + "/mcp")
            _assert_contract(public_status)
            public_hash_before = str(public_status.get("discovery_hash") or "")
            if len(public_hash_before) != 64:
                raise AssertionError(f"public discovery_hash must be a sha256 hex digest: {public_status}")

            public_tools = _mcp(base_url, "tools/list", {})
            _assert_stable_tool_list(public_tools.get("tools", []), base_url=base_url, state_dir=state_dir)
            public_tools_again = _mcp(base_url, "tools/list", {})
            if _canonical(public_tools) != _canonical(public_tools_again):
                raise AssertionError("public tools/list must be byte-stable across repeated calls")
            public_status_again = _tool(base_url, "get_status", {})
            if public_status_again.get("mcp", {}).get("discovery_hash") != public_hash_before:
                raise AssertionError(f"public discovery_hash changed without registry changes: {public_status_again.get('mcp')}")

            client = _post_json(
                f"{base_url}/oauth/register",
                {"client_name": "MCP connection smoke", "redirect_uris": ["http://127.0.0.1/callback"]},
            )
            client_id = str(client.get("client_id") or "")
            if not client_id or client.get("client_secret"):
                raise AssertionError(f"dynamic client registration must create a public PKCE client only: {client}")

            verifier = "connection-smoke-verifier-0123456789abcdefghijklmnopqrstuvwxyz"
            challenge = _pkce_challenge(verifier)
            auth_params = {
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": "http://127.0.0.1/callback",
                "scope": "dcp.write",
                "state": "connection-smoke-state",
                "resource": resource,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
            redirect = _post_form_no_redirect(f"{base_url}/oauth/authorize", auth_params)
            returned = parse.parse_qs(parse.urlparse(redirect).query)
            code = returned.get("code", [""])[0]
            if not code or returned.get("state", [""])[0] != "connection-smoke-state":
                raise AssertionError(f"authorization approval must return code and state: {redirect}")
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
            if token.get("token_type") != "Bearer" or token.get("scope") != "dcp.write" or not access_token:
                raise AssertionError(f"token exchange must return a scoped bearer token: {token}")

            authed_status = _tool(base_url, "get_status", {}, token=access_token)
            authed_mcp = authed_status.get("mcp") or {}
            _assert_contract(authed_mcp)
            oauth_status = authed_mcp.get("oauth") or {}
            if oauth_status.get("registered_clients_count", 0) < 1 or oauth_status.get("active_grants_count", 0) < 1:
                raise AssertionError(f"OAuth client/grant must be durable and active: {oauth_status}")
            if oauth_status.get("refresh_supported") is not True or oauth_status.get("offline_access_supported") is not True:
                raise AssertionError(f"refresh/offline support must be enabled: {oauth_status}")
            if oauth_status.get("token_expired_requires_reconnect") is not False:
                raise AssertionError(f"expired access tokens should be refreshable without manual reconnect: {oauth_status}")
            if oauth_status.get("pending_codes_count") != 0:
                raise AssertionError(f"used authorization code must be removed after exchange: {oauth_status}")
            authed_hash_before = str(authed_mcp.get("discovery_hash") or "")
            authed_tools = _mcp(base_url, "tools/list", {}, token=access_token)
            _assert_stable_tool_list(authed_tools.get("tools", []), base_url=base_url, state_dir=state_dir)
            if _tool(base_url, "get_status", {}, token=access_token).get("mcp", {}).get("discovery_hash") != authed_hash_before:
                raise AssertionError("authenticated discovery_hash changed across repeated status calls")

            process = _restart_server(process, port, state_dir, tmp)
            _wait_ready(base_url)
            restarted = _tool(base_url, "get_status", {}, token=access_token)
            restarted_mcp = restarted.get("mcp") or {}
            restarted_oauth = restarted_mcp.get("oauth") or {}
            if restarted_oauth.get("registered_clients_count", 0) < 1 or restarted_oauth.get("active_grants_count", 0) < 1:
                raise AssertionError(f"OAuth client/grant must survive restart: {restarted_oauth}")
            if restarted_mcp.get("discovery_hash") != authed_hash_before:
                raise AssertionError(f"authenticated discovery_hash changed after restart: {restarted_mcp}")
            if _get_json(base_url + "/mcp").get("discovery_hash") != public_hash_before:
                raise AssertionError("public discovery_hash changed after restart")

            _write_expired_oauth_state(state_dir)
            cleanup_status = _get_json(base_url + "/mcp")
            cleanup = ((cleanup_status.get("oauth") or {}).get("cleanup") or {})
            if cleanup.get("removed_expired_codes_count", 0) < 1:
                raise AssertionError(f"expired authorization codes must be cleaned: {cleanup}")
            if cleanup.get("removed_expired_grants_count", 0) < 1:
                raise AssertionError(f"old expired grants must be cleaned after retention: {cleanup}")
            if cleanup.get("removed_stale_clients_count", 0) < 1:
                raise AssertionError(f"stale registered clients must have cleanup policy: {cleanup}")
            _assert_expired_state_removed(state_dir, access_token, client_id)
            if cleanup_status.get("discovery_hash") != public_hash_before:
                raise AssertionError("public discovery_hash changed after OAuth cleanup")
            if _tool(base_url, "get_status", {}, token=access_token).get("mcp", {}).get("discovery_hash") != authed_hash_before:
                raise AssertionError("authenticated discovery_hash changed after OAuth cleanup")

            _assert_no_secret_leak(state_dir, [access_token, code, verifier])
            _assert_no_secret_leak_in_payload(public_status_again)
            _assert_no_secret_leak_in_payload(authed_status)
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

    print("dev-control-plane-mcp-connection-smoke passed")


def _assert_contract(status: Mapping[str, Any]) -> None:
    if status.get("connection_contract_version") != MCP_CONNECTION_CONTRACT_VERSION:
        raise AssertionError(f"MCP status must expose connection contract version: {status}")
    contract = status.get("connection_contract") or {}
    expected = {
        "public_url": MCP_PUBLIC_URL,
        "mcp_endpoint": f"{MCP_PUBLIC_URL}/mcp",
        "oauth_issuer": MCP_PUBLIC_URL,
        "oauth_resource": f"{MCP_PUBLIC_URL}/mcp",
        "resource_metadata": f"{MCP_PUBLIC_URL}/.well-known/oauth-protected-resource/mcp",
        "transport": "streamable_http",
        "auth": "oauth2_authorization_code_pkce",
        "scope": "dcp.write",
    }
    if contract != expected:
        raise AssertionError(f"MCP connection contract mismatch: {contract}")
    diagnostics = status.get("reconnect_diagnostics") or {}
    for reason in (
        "unauthenticated_call",
        "unsupported_authorization_scheme",
        "client_or_grant_not_found",
        "token_expired",
        "write_scope_missing",
        "invalid_resource_metadata",
        "refresh_token_expired",
        "refresh_token_revoked",
        "refresh_token_reuse_detected",
        "offline_access_not_requested",
    ):
        if reason not in diagnostics.get("reason_codes", []):
            raise AssertionError(f"reconnect diagnostics missing reason code {reason}: {diagnostics}")
    if not diagnostics.get("external_chatgpt_cache_limitation"):
        raise AssertionError(f"external ChatGPT cache limitation must be explicit: {diagnostics}")


def _assert_stable_tool_list(tools: Any, *, base_url: str, state_dir: Path) -> None:
    if not isinstance(tools, list) or not tools:
        raise AssertionError(f"tools/list must return a non-empty tool list: {tools}")
    names = [str(tool.get("name") or "") for tool in tools if isinstance(tool, Mapping)]
    if names != sorted(names):
        raise AssertionError(f"tools/list order must be stable and sorted by name: {names}")
    text = _canonical(tools)
    forbidden_fragments = [base_url, str(state_dir), "created_at", "updated_at", "expires_at_epoch"]
    for fragment in forbidden_fragments:
        if fragment and fragment in text:
            raise AssertionError(f"tools/list must not include runtime field or path {fragment!r}")


def _write_expired_oauth_state(state_dir: Path) -> None:
    collections_dir = state_dir / "collections"
    collections_dir.mkdir(parents=True, exist_ok=True)
    old_client_id = "dcp-client-old-cleanup-smoke"
    clients_path = collections_dir / "mcp_oauth_clients.json"
    codes_path = collections_dir / "mcp_oauth_codes.json"
    tokens_path = collections_dir / "mcp_oauth_tokens.json"
    clients = _read_json_file(clients_path)
    codes = _read_json_file(codes_path)
    tokens = _read_json_file(tokens_path)
    clients[old_client_id] = {
        "client_id": old_client_id,
        "client_name": "old cleanup smoke",
        "redirect_uris": ["http://127.0.0.1/callback"],
        "token_endpoint_auth_method": "none",
        "grant_types": ["authorization_code"],
        "response_types": ["code"],
        "scope": "dcp.write",
        "created_at": "2000-01-01T00:00:00Z",
    }
    codes["old-expired-code-hash"] = {
        "client_id": old_client_id,
        "redirect_uri": "http://127.0.0.1/callback",
        "scope": "dcp.write",
        "resource": "http://127.0.0.1/mcp",
        "code_challenge": "old",
        "code_challenge_method": "S256",
        "created_at": "2000-01-01T00:00:00Z",
        "expires_at_epoch": 1,
        "used": False,
    }
    tokens["old-expired-grant-hash"] = {
        "client_id": old_client_id,
        "scope": "dcp.write",
        "resource": "http://127.0.0.1/mcp",
        "created_at": "2000-01-01T00:00:00Z",
        "expires_at_epoch": 1,
    }
    _write_json_file(clients_path, clients)
    _write_json_file(codes_path, codes)
    _write_json_file(tokens_path, tokens)


def _assert_expired_state_removed(state_dir: Path, active_token: str, active_client_id: str) -> None:
    collections_dir = state_dir / "collections"
    clients = _read_json_file(collections_dir / "mcp_oauth_clients.json")
    codes = _read_json_file(collections_dir / "mcp_oauth_codes.json")
    tokens = _read_json_file(collections_dir / "mcp_oauth_tokens.json")
    if "dcp-client-old-cleanup-smoke" in clients:
        raise AssertionError("stale registered client was not removed")
    if "old-expired-code-hash" in codes:
        raise AssertionError("expired authorization code was not removed")
    if "old-expired-grant-hash" in tokens:
        raise AssertionError("old expired grant was not removed")
    if active_client_id not in clients:
        raise AssertionError("active OAuth client was removed during cleanup")
    if _sha256(active_token) not in tokens:
        raise AssertionError("active OAuth grant was removed during cleanup")


def _assert_no_secret_leak(state_dir: Path, raw_values: list[str]) -> None:
    state_text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in state_dir.rglob("*")
        if path.is_file()
    )
    for value in raw_values:
        if value and value in state_text:
            raise AssertionError("OAuth raw token, code or verifier leaked into runtime state")
    if "Authorization:" in state_text or "Bearer " in state_text:
        raise AssertionError("OAuth Authorization/Bearer material leaked into runtime state")


def _assert_no_secret_leak_in_payload(payload: Mapping[str, Any]) -> None:
    text = _canonical(payload)
    forbidden = ["Authorization:", "Bearer ", '"access_token"', '"client_secret"', '"refresh_token"']
    for fragment in forbidden:
        if fragment in text:
            raise AssertionError(f"status payload leaked secret-like field {fragment!r}")


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
        [
            sys.executable,
            str(SERVER),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--state-dir",
            str(state_dir),
        ],
        cwd=ROOT,
        env=_server_env(tmp),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _restart_server(process: subprocess.Popen[str], port: int, state_dir: Path, tmp: Path) -> subprocess.Popen[str]:
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
    return _start_server(port, state_dir, tmp)


def _get_json(url: str) -> dict[str, Any]:
    return json.loads(_get_text(url))


def _get_text(url: str) -> str:
    with urllib_request.urlopen(url, timeout=10) as response:
        return response.read().decode("utf-8")


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


def _server_env(tmp: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("OPENAI_API_KEY", None)
    env.pop("DEV_CONTROL_PLANE_MCP_TOKEN", None)
    env["DEV_CONTROL_PLANE_SECRET_HOME"] = str(tmp / "secrets")
    env["DEV_CONTROL_PLANE_MCP_FAKE_RUNS"] = "1"
    env["DEV_CONTROL_PLANE_WB_CORE_AUTO_TASK_MODE"] = "stub"
    env["DEV_CONTROL_PLANE_ENABLE_FAKE_CURATOR"] = "1"
    return env


def _read_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise AssertionError(f"expected object JSON file: {path}")
    return loaded


def _write_json_file(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _canonical(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


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
