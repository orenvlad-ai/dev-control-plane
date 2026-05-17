"""Smoke-check OAuth-gated MCP simple operator flow without target mutation."""

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

READ_TOOLS = {
    "get_run_artifact",
    "get_run_log_tail",
    "get_run_report",
    "get_run_status",
    "get_run_timeline",
    "get_status",
    "get_target_status",
    "list_active_runs",
    "list_run_artifacts",
    "list_targets",
}
AUTHENTICATED_READ_TOOLS = {"list_target_docs", "search_target_docs", "get_target_doc", "read_target_docs"}
WRITE_TOOLS = {"start_wb_core_auto_task", "request_rollback"}
LEGACY_TOOLS = {
    "archive_wb_core_auto_task_run",
    "clear_wb_core_promotion_queue",
    "get_operator_parity_status",
    "get_parallel_task",
    "get_production_lock_status",
    "get_rollback_plan",
    "get_target_promotion_state",
    "list_parallel_candidates",
    "list_parallel_tasks",
    "merge_deploy_ready_run",
    "promote_next_parallel_candidate",
    "promote_parallel_selection",
    "promote_parallel_task",
    "reconcile_parallel_task",
    "refresh_selected_candidate",
    "resume_wb_core_production_deploy",
    "start_managed_clone_run",
    "start_parallel_task_execution",
    "start_sprint",
    "start_wb_core_operator_parity_task",
    "start_wb_core_production_lane",
    "submit_parallel_task",
}


def main() -> None:
    port = _free_port()
    with TemporaryDirectory(prefix="dev-control-plane-mcp-oauth-") as tmp_raw:
        tmp = Path(tmp_raw)
        state_dir = tmp / "state"
        process = _start_server(port, state_dir, tmp)
        try:
            base_url = f"http://127.0.0.1:{port}"
            _wait_ready(base_url)
            resource = f"{base_url}/mcp"

            protected = _get_json(f"{base_url}/.well-known/oauth-protected-resource/mcp")
            if protected.get("resource") != resource or base_url not in protected.get("authorization_servers", []):
                raise AssertionError(f"protected resource metadata must identify MCP and auth server: {protected}")
            issuer = _get_json(f"{base_url}/.well-known/oauth-authorization-server")
            if issuer.get("registration_endpoint") != f"{base_url}/oauth/register" or "refresh_token" not in issuer.get("grant_types_supported", []):
                raise AssertionError(f"authorization server metadata must expose DCR + refresh-token grant: {issuer}")

            client = _post_json(
                f"{base_url}/oauth/register",
                {"client_name": "MCP OAuth smoke", "redirect_uris": ["http://127.0.0.1/callback"]},
            )
            if client.get("client_secret"):
                raise AssertionError("DCR response must not issue a client_secret")
            client_id = str(client.get("client_id") or "")
            verifier = "oauth-smoke-verifier-0123456789abcdefghijklmnopqrstuvwxyz"
            auth_params = {
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": "http://127.0.0.1/callback",
                "scope": "dcp.write offline_access",
                "state": "oauth-smoke-state",
                "resource": resource,
                "code_challenge": _pkce_challenge(verifier),
                "code_challenge_method": "S256",
            }
            redirect = _post_form_no_redirect(f"{base_url}/oauth/authorize", auth_params)
            returned = parse.parse_qs(parse.urlparse(redirect).query)
            code = returned.get("code", [""])[0]
            if not code or returned.get("state", [""])[0] != "oauth-smoke-state":
                raise AssertionError(f"authorization approval must redirect with code and state: {redirect}")
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
            if token.get("token_type") != "Bearer" or token.get("scope") != "dcp.write offline_access" or not access_token or not refresh_token:
                raise AssertionError(f"token response must include access + refresh tokens for offline scope: {token}")

            public_tools = _mcp(base_url, "tools/list", {})
            public_names = {str(tool.get("name") or "") for tool in public_tools.get("tools", [])}
            if public_names != READ_TOOLS:
                raise AssertionError(f"public discovery must expose only minimal read tools: {public_names}")
            if public_names & (WRITE_TOOLS | AUTHENTICATED_READ_TOOLS | LEGACY_TOOLS):
                raise AssertionError(f"public discovery leaked protected or legacy tools: {public_names}")

            oauth_tools = _mcp(base_url, "tools/list", {}, token=access_token)
            oauth_defs = oauth_tools.get("tools", [])
            oauth_names = {str(tool.get("name") or "") for tool in oauth_defs}
            expected = READ_TOOLS | AUTHENTICATED_READ_TOOLS | WRITE_TOOLS
            if oauth_names != expected:
                raise AssertionError(f"OAuth discovery must expose minimal authenticated surface: {oauth_names}")
            if oauth_names & LEGACY_TOOLS:
                raise AssertionError(f"OAuth discovery leaked legacy tools: {oauth_names & LEGACY_TOOLS}")
            _assert_tool_metadata(oauth_defs)

            status = _tool(base_url, "get_status", {}, token=access_token)
            mcp_status = status.get("mcp") or {}
            if mcp_status.get("connection_contract_version") != "mcp_connection_v1" or not mcp_status.get("discovery_hash"):
                raise AssertionError(f"get_status must expose connection v1 + discovery hash: {mcp_status}")
            oauth_status = mcp_status.get("oauth") or {}
            if oauth_status.get("active_refresh_tokens_count") != 1 or oauth_status.get("refresh_supported") is not True:
                raise AssertionError(f"OAuth status must report active refresh token support: {oauth_status}")
            diagnostics = mcp_status.get("reconnect_diagnostics") or {}
            for reason in (
                "unauthenticated_call",
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
                    raise AssertionError(f"OAuth diagnostics missing reason {reason}: {diagnostics}")

            denied = _tool(base_url, "start_wb_core_auto_task", {"task_text": "oauth denied"})
            if denied.get("status") != "denied" or denied.get("auth_failure_code") != "unauthenticated_call":
                raise AssertionError(f"unauthenticated write must be denied with stable reason: {denied}")
            auto = _tool(
                base_url,
                "start_wb_core_auto_task",
                {"task_text": "OAuth smoke direct auto task", "idempotency_key": "auto-oauth-smoke", "max_wait_seconds": 5},
                token=access_token,
            )
            if auto.get("route") != "wb_core_exclusive_auto_production" or auto.get("auto_production_allowed") is not True:
                raise AssertionError(f"OAuth auto task must classify exclusive when idle: {auto}")
            auto_status = _tool(base_url, "get_run_status", {"run_id": auto["run_id"]})
            if auto_status.get("status") != "production_complete" or auto_status.get("branch_pr_created") is not False:
                raise AssertionError(f"OAuth auto task smoke must finish through stubbed route without target mutation: {auto_status}")

            legacy_error = _mcp_expect_error(base_url, "tools/call", {"name": "start_sprint", "arguments": {"target_id": "wb-core", "sprint_text": "removed"}}, token=access_token)
            if "unknown tool" not in str((legacy_error.get("error") or {}).get("message") or ""):
                raise AssertionError(f"removed legacy MCP tools must not be callable: {legacy_error}")

            process = _restart_server(process, port, state_dir, tmp)
            _wait_ready(base_url)
            restarted = _tool(base_url, "get_status", {}, token=access_token)
            restarted_oauth = ((restarted.get("mcp") or {}).get("oauth") or {})
            if restarted_oauth.get("registered_clients_count", 0) < 1 or restarted_oauth.get("active_refresh_tokens_count", 0) < 1:
                raise AssertionError(f"OAuth client/refresh grant must survive service restart: {restarted_oauth}")

            _assert_no_raw_secret_state(state_dir, [access_token, refresh_token, code, verifier])
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

    print("dev-control-plane-mcp-oauth-smoke passed")


def _assert_tool_metadata(tools: list[Mapping[str, Any]]) -> None:
    for tool in tools:
        name = str(tool.get("name") or "")
        annotations = tool.get("annotations") or {}
        schemes = tool.get("securitySchemes") or (tool.get("_meta") or {}).get("securitySchemes") or []
        if name in WRITE_TOOLS:
            if annotations.get("readOnlyHint") is not False:
                raise AssertionError(f"write tool must not be marked read-only: {tool}")
            if {"type": "oauth2", "scopes": ["dcp.write"]} not in schemes:
                raise AssertionError(f"write tool must advertise OAuth scope: {tool}")
        elif name in AUTHENTICATED_READ_TOOLS:
            if annotations.get("readOnlyHint") is not True:
                raise AssertionError(f"authenticated read tool must be read-only: {tool}")
            if {"type": "oauth2", "scopes": ["dcp.write"]} not in schemes:
                raise AssertionError(f"authenticated read tool must advertise OAuth scope: {tool}")
        elif name in READ_TOOLS:
            if annotations.get("readOnlyHint") is not True:
                raise AssertionError(f"public read tool must be read-only: {tool}")


def _assert_no_raw_secret_state(state_dir: Path, raw_values: list[str]) -> None:
    state_text = "\n".join(path.read_text(encoding="utf-8", errors="replace") for path in state_dir.rglob("*") if path.is_file())
    for value in raw_values:
        if value and value in state_text:
            raise AssertionError("OAuth raw token, code or verifier leaked into runtime state")
    if "Authorization:" in state_text or "Bearer " in state_text:
        raise AssertionError("OAuth raw token, code or verifier leaked into runtime state")


def _start_server(port: int, state_dir: Path, tmp: Path) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [sys.executable, str(SERVER), "--host", "127.0.0.1", "--port", str(port), "--state-dir", str(state_dir)],
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


def _mcp(base_url: str, method: str, params: Mapping[str, Any], *, token: str | None = None) -> dict[str, Any]:
    payload = _mcp_raw(base_url, method, params, token=token)
    if "error" in payload:
        raise AssertionError(f"MCP error for {method}: {payload}")
    return payload.get("result") or {}


def _mcp_expect_error(base_url: str, method: str, params: Mapping[str, Any], *, token: str | None = None) -> dict[str, Any]:
    payload = _mcp_raw(base_url, method, params, token=token)
    if "error" not in payload:
        raise AssertionError(f"expected MCP error for {method}, got: {payload}")
    return payload


def _mcp_raw(base_url: str, method: str, params: Mapping[str, Any], *, token: str | None = None) -> dict[str, Any]:
    body = json.dumps({"jsonrpc": "2.0", "id": f"smoke-{time.time_ns()}", "method": method, "params": params}).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib_request.Request(base_url + "/mcp", data=body, method="POST", headers=headers)
    with urllib_request.urlopen(req, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _tool(base_url: str, name: str, arguments: Mapping[str, Any], *, token: str | None = None) -> dict[str, Any]:
    result = _mcp(base_url, "tools/call", {"name": name, "arguments": dict(arguments)}, token=token)
    structured = result.get("structuredContent")
    if isinstance(structured, dict):
        return structured
    content = result.get("content", [])
    if content and isinstance(content[0], dict):
        return json.loads(content[0].get("text") or "{}")
    return {}


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


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


if __name__ == "__main__":
    main()
