"""Smoke-check sprint orchestrator remains frozen for operator MCP flow."""

from __future__ import annotations

from dev_control_plane_mcp_start_sprint_smoke import main as _start_sprint_smoke


def main() -> None:
    _start_sprint_smoke()
    print("dev-control-plane-sprint-orchestrator-smoke passed")


if __name__ == "__main__":
    main()
