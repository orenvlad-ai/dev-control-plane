"""Smoke-check that MCP get_status/state/logs do not expose raw OAuth material."""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from urllib import parse

from dev_control_plane_mcp_refresh_oauth_smoke import (
    _free_port,
    _mcp,
    _pkce_challenge,
    _post_form,
    _post_form_no_redirect,
    _post_json,
    _start_server,
    _wait_ready,
)


def main() -> None:
    port = _free_port()
    with TemporaryDirectory(prefix="dev-control-plane-status-secrets-") as tmp_raw:
        tmp = Path(tmp_raw)
        state_dir = tmp / "state"
        process = _start_server(port, state_dir, tmp)
        try:
            base_url = f"http://127.0.0.1:{port}"
            _wait_ready(base_url)
            resource = f"{base_url}/mcp"
            client = _post_json(f"{base_url}/oauth/register", {"client_name": "status secret smoke", "redirect_uris": ["http://127.0.0.1/callback"]})
            client_id = str(client.get("client_id") or "")
            verifier = "status-secret-verifier-0123456789abcdefghijklmnopqrstuvwxyz"
            redirect = _post_form_no_redirect(
                f"{base_url}/oauth/authorize",
                {
                    "response_type": "code",
                    "client_id": client_id,
                    "redirect_uri": "http://127.0.0.1/callback",
                    "scope": "dcp.write offline_access",
                    "state": "status-secret-state",
                    "resource": resource,
                    "code_challenge": _pkce_challenge(verifier),
                    "code_challenge_method": "S256",
                },
            )
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
            status = _mcp(base_url, "tools/call", {"name": "get_status", "arguments": {}}, token=access_token)
            text = json.dumps(status, ensure_ascii=False, sort_keys=True)
            for forbidden in (access_token, refresh_token, code, verifier, '"access_token"', '"refresh_token"', "Authorization:", "Bearer "):
                if forbidden and forbidden in text:
                    raise AssertionError(f"get_status leaked raw OAuth material marker: {forbidden[:24]}")
            state_text = "\n".join(path.read_text(encoding="utf-8", errors="replace") for path in state_dir.rglob("*") if path.is_file())
            for forbidden in (access_token, refresh_token, code, verifier, "Authorization:", "Bearer "):
                if forbidden and forbidden in state_text:
                    raise AssertionError("runtime state leaked raw OAuth material")
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
    print("dev-control-plane-mcp-get-status-no-secrets-smoke passed")


if __name__ == "__main__":
    main()
