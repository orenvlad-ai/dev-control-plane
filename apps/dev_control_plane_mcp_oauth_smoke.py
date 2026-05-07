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
        process = subprocess.Popen(
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

            public_tools = _mcp(base_url, "tools/list", {})
            public_names = {tool.get("name") for tool in public_tools.get("tools", [])}
            write_names = {
                "request_rollback",
                "resume_wb_core_production_deploy",
                "start_managed_clone_run",
                "start_wb_core_production_lane",
            }
            target_doc_names = {"list_target_docs", "search_target_docs", "get_target_doc", "read_target_docs"}
            if public_names & write_names:
                raise AssertionError("public no-auth discovery must not expose write tools")
            if public_names & target_doc_names:
                raise AssertionError("public no-auth discovery must not expose authenticated target docs tools")

            oauth_tools = _mcp(base_url, "tools/list", {}, token=access_token)
            oauth_defs = oauth_tools.get("tools", [])
            oauth_names = {tool.get("name") for tool in oauth_defs}
            if not write_names.issubset(oauth_names):
                raise AssertionError(f"OAuth-authenticated discovery must expose write tools: {oauth_names}")
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
            denied_resume = _tool(base_url, "resume_wb_core_production_deploy", {"run_id": "missing-run", "dry_run": True})
            if denied_resume.get("status") != "denied":
                raise AssertionError(f"unauthenticated resume write must remain denied: {denied_resume}")
            denied_docs = _tool(base_url, "list_target_docs", {"target_id": "wb-core"})
            if denied_docs.get("status") != "denied":
                raise AssertionError(f"unauthenticated target docs read must remain denied: {denied_docs}")
            denied_docs_fallback = _tool(base_url, "read_target_docs", {"action": "list", "target_id": "wb-core"})
            if denied_docs_fallback.get("status") != "denied":
                raise AssertionError(f"unauthenticated target docs fallback must remain denied: {denied_docs_fallback}")
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

            state_text = "\n".join(path.read_text(encoding="utf-8", errors="replace") for path in state_dir.rglob("*") if path.is_file())
            if access_token in state_text or code in state_text or "oauth-smoke-verifier" in state_text:
                raise AssertionError("OAuth raw token, code or verifier leaked into runtime state")
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

    print("dev-control-plane-mcp-oauth-smoke passed")


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
    env["DEV_CONTROL_PLANE_ENABLE_FAKE_CURATOR"] = "1"
    return env


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


if __name__ == "__main__":
    main()
