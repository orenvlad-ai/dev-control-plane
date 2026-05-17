"""Smoke-check the current minimal MCP operator surface."""

from __future__ import annotations

from dev_control_plane_mcp_oauth_smoke import main as _oauth_smoke
from dev_control_plane_mcp_no_legacy_tools_smoke import main as _no_legacy_tools_smoke


def main() -> None:
    _oauth_smoke()
    _no_legacy_tools_smoke()
    print("dev-control-plane-mcp-smoke passed")


if __name__ == "__main__":
    main()
