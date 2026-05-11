"""Smoke-check OAuth-gated MCP write tools without real production mutation."""

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
            if issuer.get("registration_endpoint") != f"{base_url}/oauth/register" or "S256" not in issuer.get("code_challenge_methods_supported", []):
                raise AssertionError(f"authorization server metadata must expose DCR + PKCE: {issuer}")

            client = _post_json(
                f"{base_url}/oauth/register",
                {
                    "client_name": "MCP OAuth smoke",
                    "redirect_uris": ["http://127.0.0.1/callback"],
                },
            )
            if client.get("client_secret"):
                raise AssertionError("DCR response must not issue a client_secret; public PKCE client is expected")
            client_id = str(client.get("client_id") or "")
            if not client_id:
                raise AssertionError(f"DCR must return client_id: {client}")

            verifier = "oauth-smoke-verifier-0123456789abcdefghijklmnopqrstuvwxyz"
            challenge = _pkce_challenge(verifier)
            auth_params = {
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": "http://127.0.0.1/callback",
                "scope": "dcp.write",
                "state": "oauth-smoke-state",
                "resource": resource,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
            authorize_html = _get_text(f"{base_url}/oauth/authorize?{parse.urlencode(auth_params)}")
            if "Authorize dev-control-plane MCP" not in authorize_html:
                raise AssertionError("authorization page must render controlled consent form")
            redirect = _post_form_no_redirect(f"{base_url}/oauth/authorize", auth_params)
            parsed = parse.urlparse(redirect)
            returned = parse.parse_qs(parsed.query)
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
            if token.get("token_type") != "Bearer" or token.get("scope") != "dcp.write" or not access_token:
                raise AssertionError(f"token response must be bearer with dcp.write scope: {token}")
            state = _get_json(base_url + "/api/state")
            oauth_status = ((state.get("mcp") or {}).get("auth") or {}).get("oauth") or {}
            if oauth_status.get("registered_clients_count", 0) < 1 or oauth_status.get("active_grants_count", 0) < 1:
                raise AssertionError(f"status endpoint must report sanitized OAuth readiness: {oauth_status}")
            storage = oauth_status.get("storage") or {}
            if storage.get("mode") != "durable_state_collection" or storage.get("restart_survives") is not True:
                raise AssertionError(f"OAuth clients/grants must be reported as durable state collections: {oauth_status}")
            diagnostics = oauth_status.get("auth_failure_diagnostics") or {}
            for reason in (
                "unauthenticated_call",
                "client_or_grant_not_found",
                "token_expired",
                "write_scope_missing",
                "invalid_resource_metadata",
            ):
                if reason not in diagnostics.get("supported_reason_codes", []):
                    raise AssertionError(f"OAuth diagnostics missing reason {reason}: {diagnostics}")

            process = _restart_server(process, port, state_dir, tmp)
            _wait_ready(base_url)
            restarted_state = _get_json(base_url + "/api/state")
            restarted_oauth = ((restarted_state.get("mcp") or {}).get("auth") or {}).get("oauth") or {}
            if restarted_oauth.get("registered_clients_count", 0) < 1 or restarted_oauth.get("active_grants_count", 0) < 1:
                raise AssertionError(f"OAuth clients/grants must survive service restart: {restarted_oauth}")

            public_tools = _mcp(base_url, "tools/list", {})
            public_names = {tool.get("name") for tool in public_tools.get("tools", [])}
            write_names = {
                "request_rollback",
                "resume_wb_core_production_deploy",
                "start_wb_core_auto_task",
                "start_managed_clone_run",
                "submit_parallel_task",
                "start_parallel_task_execution",
                "reconcile_parallel_task",
                "promote_parallel_task",
                "promote_next_parallel_candidate",
                "promote_parallel_selection",
                "refresh_selected_candidate",
                "clear_wb_core_promotion_queue",
                "archive_wb_core_auto_task_run",
                "start_wb_core_production_lane",
            }
            frozen_operator_tools = {"start_sprint"}
            target_doc_names = {"list_target_docs", "search_target_docs", "get_target_doc", "read_target_docs"}
            if public_names & write_names:
                raise AssertionError("public no-auth discovery must not expose write tools")
            if public_names & frozen_operator_tools:
                raise AssertionError("public no-auth discovery must not expose frozen sprint tools")
            if public_names & target_doc_names:
                raise AssertionError("public no-auth discovery must not expose authenticated target docs tools")

            oauth_tools = _mcp(base_url, "tools/list", {}, token=access_token)
            oauth_defs = oauth_tools.get("tools", [])
            oauth_names = {tool.get("name") for tool in oauth_defs}
            if not write_names.issubset(oauth_names):
                raise AssertionError(f"OAuth-authenticated discovery must expose write tools: {oauth_names}")
            if oauth_names & frozen_operator_tools:
                raise AssertionError(f"OAuth-authenticated operator discovery must not expose frozen sprint tools: {oauth_names & frozen_operator_tools}")
            if not target_doc_names.issubset(oauth_names):
                raise AssertionError(f"OAuth-authenticated discovery must expose target docs read tools: {oauth_names}")
            for tool in oauth_defs:
                if tool.get("name") in write_names:
                    schemes = tool.get("securitySchemes") or (tool.get("_meta") or {}).get("securitySchemes") or []
                    if {"type": "oauth2", "scopes": ["dcp.write"]} not in schemes:
                        raise AssertionError(f"write tool must advertise OAuth scope: {tool}")
                if tool.get("name") in target_doc_names:
                    annotations = tool.get("annotations") or {}
                    if annotations.get("readOnlyHint") is not True:
                        raise AssertionError(f"target docs tool must be marked read-only: {tool}")
                    schemes = tool.get("securitySchemes") or (tool.get("_meta") or {}).get("securitySchemes") or []
                    if {"type": "oauth2", "scopes": ["dcp.write"]} not in schemes:
                        raise AssertionError(f"target docs tool must advertise authenticated OAuth scope: {tool}")

            denied = _tool(base_url, "start_wb_core_production_lane", {"task_text": "oauth denied", "dry_run": True})
            if denied.get("status") != "denied":
                raise AssertionError(f"unauthenticated write must remain denied: {denied}")
            if denied.get("auth_failure_code") != "unauthenticated_call":
                raise AssertionError(f"unauthenticated denial must include stable sanitized reason: {denied}")
            denied_auto = _tool(base_url, "start_wb_core_auto_task", {"task_text": "oauth auto denied"})
            if denied_auto.get("status") != "denied" or denied_auto.get("auth_failure_code") != "unauthenticated_call":
                raise AssertionError(f"unauthenticated auto task write must remain denied with stable reason: {denied_auto}")
            unknown_token = _tool(
                base_url,
                "start_wb_core_production_lane",
                {"task_text": "unknown token denied", "dry_run": True},
                token="dcp-access-unknown-smoke-token",
            )
            if unknown_token.get("status") != "denied" or unknown_token.get("auth_failure_code") != "client_or_grant_not_found":
                raise AssertionError(f"unknown grant denial must be explicit and sanitized: {unknown_token}")
            denied_resume = _tool(base_url, "resume_wb_core_production_deploy", {"run_id": "missing-run", "dry_run": True})
            if denied_resume.get("status") != "denied":
                raise AssertionError(f"unauthenticated resume write must remain denied: {denied_resume}")
            denied_selection = _tool(
                base_url,
                "promote_parallel_selection",
                {"target_id": "wb-core", "selected_ids": ["missing"], "confirm_merge_deploy": True},
            )
            if denied_selection.get("status") != "denied":
                raise AssertionError(f"unauthenticated selected promotion write must remain denied: {denied_selection}")
            denied_refresh = _tool(base_url, "refresh_selected_candidate", {"target_id": "wb-core", "source_run_id": "missing"})
            if denied_refresh.get("status") != "denied":
                raise AssertionError(f"unauthenticated refresh selected candidate write must remain denied: {denied_refresh}")
            denied_cleanup = _tool(base_url, "clear_wb_core_promotion_queue", {"target_id": "wb-core", "reason": "must not clear without auth"})
            if denied_cleanup.get("status") != "denied":
                raise AssertionError(f"unauthenticated cleanup queue write must remain denied: {denied_cleanup}")
            denied_archive = _tool(base_url, "archive_wb_core_auto_task_run", {"target_id": "wb-core", "run_id": "missing", "reason": "must not archive without auth"})
            if denied_archive.get("status") != "denied":
                raise AssertionError(f"unauthenticated archive write must remain denied: {denied_archive}")
            denied_docs = _tool(base_url, "list_target_docs", {"target_id": "wb-core"})
            if denied_docs.get("status") != "denied":
                raise AssertionError(f"unauthenticated target docs read must remain denied: {denied_docs}")
            denied_docs_fallback = _tool(base_url, "read_target_docs", {"action": "list", "target_id": "wb-core"})
            if denied_docs_fallback.get("status") != "denied":
                raise AssertionError(f"unauthenticated target docs fallback must remain denied: {denied_docs_fallback}")
            frozen_sprint = _tool(
                base_url,
                "start_sprint",
                {"target_id": "wb-core", "sprint_text": "OAuth sprint must stay frozen"},
                token=access_token,
            )
            if (
                frozen_sprint.get("status") != "blocked"
                or "start_sprint is frozen for operator flow" not in str(frozen_sprint.get("blocker") or "")
                or frozen_sprint.get("run_id")
            ):
                raise AssertionError(f"OAuth start_sprint must be frozen without parent/child runs: {frozen_sprint}")
            dry_run = _tool(
                base_url,
                "start_wb_core_production_lane",
                {"task_text": "OAuth smoke production dry-run", "dry_run": True},
                token=access_token,
            )
            if dry_run.get("status") != "completed_dry_run" or not dry_run.get("run_id"):
                raise AssertionError(f"OAuth write dry-run must complete without real production mutation: {dry_run}")
            resume_missing = _tool(
                base_url,
                "resume_wb_core_production_deploy",
                {"run_id": "missing-run", "dry_run": True},
                token=access_token,
            )
            if resume_missing.get("status") != "blocked" or "production_lane_result.json is required" not in " ".join(resume_missing.get("blockers") or []):
                raise AssertionError(f"OAuth resume dry-run must be accepted but fail closed on missing run: {resume_missing}")
            report = _tool(base_url, "get_run_report", {"run_id": dry_run["run_id"]})
            if report.get("production_lane_result") or report.get("deploy_result", {}).get("deploy_status"):
                raise AssertionError(f"OAuth dry-run must not produce PR/deploy result: {report}")
            auto = _tool(
                base_url,
                "start_wb_core_auto_task",
                {"task_text": "OAuth smoke auto task exclusive", "idempotency_key": "auto-oauth-smoke", "max_wait_seconds": 5},
                token=access_token,
            )
            if auto.get("route") != "wb_core_exclusive_auto_production" or auto.get("auto_production_allowed") is not True:
                raise AssertionError(f"OAuth auto task must classify exclusive when idle: {auto}")
            auto_status = _tool(base_url, "get_run_status", {"run_id": auto["run_id"]})
            if auto_status.get("status") != "production_complete" or auto_status.get("branch_pr_created") is not False:
                raise AssertionError(f"OAuth auto task smoke must finish through stubbed route without target mutation: {auto_status}")

            _write_oauth_token(
                state_dir,
                "dcp-access-missing-scope-smoke-token",
                client_id=client_id,
                scope="profile",
                resource=resource,
                expires_at_epoch=time.time() + 3600,
            )
            missing_scope = _tool(
                base_url,
                "start_wb_core_production_lane",
                {"task_text": "missing scope denied", "dry_run": True},
                token="dcp-access-missing-scope-smoke-token",
            )
            if missing_scope.get("status") != "denied" or missing_scope.get("auth_failure_code") != "write_scope_missing":
                raise AssertionError(f"missing scope denial must be explicit: {missing_scope}")

            _write_oauth_token(
                state_dir,
                "dcp-access-wrong-resource-smoke-token",
                client_id=client_id,
                scope="dcp.write",
                resource="https://example.invalid/mcp",
                expires_at_epoch=time.time() + 3600,
            )
            wrong_resource = _tool(
                base_url,
                "start_wb_core_production_lane",
                {"task_text": "wrong resource denied", "dry_run": True},
                token="dcp-access-wrong-resource-smoke-token",
            )
            if wrong_resource.get("status") != "denied" or wrong_resource.get("auth_failure_code") != "invalid_resource_metadata":
                raise AssertionError(f"resource mismatch denial must be explicit: {wrong_resource}")

            _expire_oauth_token(state_dir, access_token)
            expired = _tool(
                base_url,
                "start_wb_core_production_lane",
                {"task_text": "expired token denied", "dry_run": True},
                token=access_token,
            )
            if expired.get("status") != "denied" or expired.get("auth_failure_code") != "token_expired":
                raise AssertionError(f"expired token denial must be explicit: {expired}")

            state_text = "\n".join(path.read_text(encoding="utf-8", errors="replace") for path in state_dir.rglob("*") if path.is_file())
            for raw_secret in (
                access_token,
                code,
                "oauth-smoke-verifier",
                "dcp-access-missing-scope-smoke-token",
                "dcp-access-wrong-resource-smoke-token",
            ):
                if raw_secret in state_text:
                    raise AssertionError("OAuth raw token, code or verifier leaked into runtime state")
            if "Authorization:" in state_text or "Bearer " in state_text:
                raise AssertionError("OAuth raw token, code or verifier leaked into runtime state")
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

    print("dev-control-plane-mcp-oauth-smoke passed")


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


def _write_oauth_token(
    state_dir: Path,
    raw_token: str,
    *,
    client_id: str,
    scope: str,
    resource: str,
    expires_at_epoch: float,
) -> None:
    path = state_dir / "collections" / "mcp_oauth_tokens.json"
    tokens = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if not isinstance(tokens, dict):
        tokens = {}
    tokens[_sha256(raw_token)] = {
        "client_id": client_id,
        "scope": scope,
        "resource": resource,
        "created_at": "2026-05-11T00:00:00Z",
        "expires_at_epoch": expires_at_epoch,
    }
    path.write_text(json.dumps(tokens, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _expire_oauth_token(state_dir: Path, raw_token: str) -> None:
    path = state_dir / "collections" / "mcp_oauth_tokens.json"
    tokens = json.loads(path.read_text(encoding="utf-8"))
    key = _sha256(raw_token)
    if key not in tokens:
        raise AssertionError("access token hash missing from OAuth token collection")
    tokens[key]["expires_at_epoch"] = 1
    path.write_text(json.dumps(tokens, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


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


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


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


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


if __name__ == "__main__":
    main()
