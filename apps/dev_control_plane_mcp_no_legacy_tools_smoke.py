"""Smoke-check that removed legacy orchestration tools are not exported by MCP."""

from __future__ import annotations

from dev_control_plane_mcp_public_discovery_smoke import LEGACY_TOOLS, PROTECTED_TOOLS, READ_TOOLS, _free_port, _get_json, _mcp, _server_env, _start_server, _wait_ready

from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory


def main() -> None:
    port = _free_port()
    with TemporaryDirectory(prefix="dev-control-plane-no-legacy-tools-") as tmp_raw:
        tmp = Path(tmp_raw)
        process = _start_server(port, tmp)
        try:
            base_url = f"http://127.0.0.1:{port}"
            _wait_ready(base_url)
            public_names = {tool.get("name") for tool in _mcp(base_url, "tools/list", {}).get("tools", [])}
            if public_names != READ_TOOLS:
                raise AssertionError(f"public tools must stay minimal: {public_names}")
            if public_names & (LEGACY_TOOLS | PROTECTED_TOOLS):
                raise AssertionError(f"public discovery leaked removed/protected tools: {public_names}")
            status = _get_json(base_url + "/mcp")
            legacy = status.get("legacy_orchestration") or {}
            if legacy.get("status") != "removed" or legacy.get("mcp_legacy_tools_exported") is not False:
                raise AssertionError(f"MCP status must report removed legacy tools: {legacy}")
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
    print("dev-control-plane-mcp-no-legacy-tools-smoke passed")


if __name__ == "__main__":
    main()
