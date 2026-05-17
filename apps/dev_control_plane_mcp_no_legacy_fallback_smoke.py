"""Smoke-check that sprint/parallel/managed fallback runtime paths are removed."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from urllib import error as urllib_error, request as urllib_request

from dev_control_plane_mcp_public_discovery_smoke import _free_port, _mcp_expect_error, _start_server, _wait_ready


def main() -> None:
    port = _free_port()
    with TemporaryDirectory(prefix="dev-control-plane-no-legacy-fallback-") as tmp_raw:
        tmp = Path(tmp_raw)
        process = _start_server(port, tmp)
        try:
            base_url = f"http://127.0.0.1:{port}"
            _wait_ready(base_url)
            for tool_name, args in {
                "start_sprint": {"target_id": "wb-core", "sprint_text": "removed"},
                "start_managed_clone_run": {"target_id": "wb-core", "task_text": "removed"},
                "submit_parallel_task": {"target_id": "wb-core", "task_text": "removed"},
                "start_parallel_task_execution": {"task_id": "removed"},
                "promote_parallel_selection": {"target_id": "wb-core", "selected_ids": ["removed"]},
            }.items():
                error = _mcp_expect_error(base_url, "tools/call", {"name": tool_name, "arguments": args})
                if "unknown tool" not in str((error.get("error") or {}).get("message") or ""):
                    raise AssertionError(f"removed MCP legacy tool {tool_name} must be unknown: {error}")
            for path in (
                "/api/parallel-tasks",
                "/api/parallel-tasks/removed/start-execution",
                "/api/parallel-tasks/removed/reconcile",
                "/api/parallel-tasks/removed/promote",
                "/api/parallel-selection/promote",
                "/api/parallel-selection/refresh",
                "/api/parallel-targets/wb-core/promote-next",
                "/api/parallel-targets/wb-core/clear-promotion-queue",
            ):
                payload = _post_expect_gone(base_url + path)
                if payload.get("status") != "removed" or "sprint/ping-pong flow is removed" not in str(payload.get("blocker") or ""):
                    raise AssertionError(f"legacy API path must return removed blocker: {path} {payload}")
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
    print("dev-control-plane-mcp-no-legacy-fallback-smoke passed")


def _post_expect_gone(url: str) -> dict[str, object]:
    body = b"{}"
    req = urllib_request.Request(url, data=body, method="POST", headers={"Content-Type": "application/json"})
    try:
        with urllib_request.urlopen(req, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        raise AssertionError(f"expected 410 Gone for {url}, got success: {payload}")
    except urllib_error.HTTPError as exc:
        if exc.code != 410:
            raise
        return json.loads(exc.read().decode("utf-8"))


if __name__ == "__main__":
    main()
