"""Smoke-check the simple direct wb-core auto-task MCP route."""

from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from tempfile import TemporaryDirectory
from typing import Any, Mapping
from urllib import request as urllib_request

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "apps" / "dev_control_plane_server.py"
TOKEN = "auto-task-smoke-token-0123456789abcdef0123456789abcdef"


def main() -> None:
    port = _free_port()
    with TemporaryDirectory(prefix="dev-control-plane-auto-task-") as tmp_raw:
        tmp = Path(tmp_raw)
        state_dir = tmp / "state"
        process = _start_server(port, state_dir, tmp)
        try:
            base_url = f"http://127.0.0.1:{port}"
            _wait_ready(base_url)

            status = _tool(base_url, "get_status", {})
            arbitration = ((status.get("mcp") or {}).get("wb_core_auto_task_arbitration") or {})
            if arbitration.get("default_route") != "exclusive-or-blocked":
                raise AssertionError(f"ordinary wb-core auto arbitration must advertise exclusive-or-blocked: {arbitration}")
            if arbitration.get("ordinary_prepare_only_fallback") is not False:
                raise AssertionError(f"ordinary wb-core auto route must not advertise prepare-only fallback: {arbitration}")
            legacy = ((status.get("mcp") or {}).get("legacy_orchestration") or {})
            if legacy.get("status") != "removed":
                raise AssertionError(f"legacy orchestration must be reported removed: {legacy}")

            before_runs = _read_collection(state_dir, "mcp_runs")
            result = _tool(
                base_url,
                "start_wb_core_auto_task",
                {"task_text": "Auto arbitration smoke exclusive", "idempotency_key": "exclusive", "max_wait_seconds": 5},
                token=TOKEN,
            )
            if result.get("route") != "wb_core_exclusive_auto_production" or result.get("auto_production_allowed") is not True:
                raise AssertionError(f"idle wb-core auto task must classify as exclusive: {result}")
            run_id = str(result.get("run_id") or "")
            run_status = _tool(base_url, "get_run_status", {"run_id": run_id})
            if run_status.get("status") != "production_complete":
                raise AssertionError(f"exclusive stub run must finish production_complete: {run_status}")
            if run_status.get("run_type") == "sprint" or run_status.get("child_run_ids") or run_status.get("parent_run_id"):
                raise AssertionError(f"direct auto task must not create sprint parent/child state: {run_status}")
            after_runs = _read_collection(state_dir, "mcp_runs")
            if len(after_runs) != len(before_runs) + 1:
                raise AssertionError(f"one external auto task must create exactly one run: before={before_runs} after={after_runs}")

            replay = _tool(
                base_url,
                "start_wb_core_auto_task",
                {"task_text": "Auto arbitration smoke exclusive duplicate", "idempotency_key": "exclusive", "max_wait_seconds": 5},
                token=TOKEN,
            )
            if replay.get("run_id") != run_id or replay.get("idempotent_replay") is not True:
                raise AssertionError(f"idempotency_key must replay existing auto run: {replay}")

            wrapper = _tool(
                base_url,
                "start_wb_core_auto_task",
                {
                    "task_text": "Task spec: legacy-wrapper\nSprint step: 1. duplicate\n\nDo not start a duplicate Codex run.",
                    "idempotency_key": "wrapper",
                    "max_wait_seconds": 5,
                },
                token=TOKEN,
            )
            if wrapper.get("status") != "blocked" or "sprint/ping-pong flow is removed" not in str(wrapper.get("blocker") or ""):
                raise AssertionError(f"legacy wrapper must be blocked with removed-flow blocker: {wrapper}")

            names = {str(tool.get("name") or "") for tool in _mcp(base_url, "tools/list", {}, token=TOKEN).get("tools", [])}
            legacy_tools = {
                "start_sprint",
                "start_managed_clone_run",
                "submit_parallel_task",
                "start_parallel_task_execution",
                "reconcile_parallel_task",
                "promote_parallel_task",
                "promote_parallel_selection",
                "promote_next_parallel_candidate",
                "refresh_selected_candidate",
                "merge_deploy_ready_run",
            }
            if names & legacy_tools:
                raise AssertionError(f"legacy tools must not be exported: {names & legacy_tools}")
            removed = _mcp_expect_error(base_url, "tools/call", {"name": "start_managed_clone_run", "arguments": {"target_id": "wb-core", "task_text": "removed"}}, token=TOKEN)
            if "unknown tool" not in str((removed.get("error") or {}).get("message") or ""):
                raise AssertionError(f"managed-clone fallback must be removed from MCP runtime: {removed}")
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

    print("dev-control-plane-wb-core-auto-task-smoke passed")


def _start_server(port: int, state_dir: Path, tmp: Path) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [sys.executable, str(SERVER), "--host", "127.0.0.1", "--port", str(port), "--state-dir", str(state_dir)],
        cwd=ROOT,
        env=_server_env(tmp),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


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


def _wait_ready(base_url: str) -> None:
    deadline = time.time() + 10
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib_request.urlopen(base_url + "/api/state", timeout=10) as response:
                json.loads(response.read().decode("utf-8"))
            return
        except Exception as exc:
            last_error = exc
            time.sleep(0.1)
    raise AssertionError(f"server did not become ready: {last_error}")


def _read_collection(state_dir: Path, name: str) -> dict[str, Any]:
    path = state_dir / "collections" / f"{name}.json"
    if not path.exists():
        return {}
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise AssertionError(f"expected state collection object: {name}")
    return loaded


def _server_env(tmp: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("OPENAI_API_KEY", None)
    env.pop("DEV_CONTROL_PLANE_MCP_TOKEN", None)
    env["DEV_CONTROL_PLANE_SECRET_HOME"] = str(tmp / "secrets")
    env["DEV_CONTROL_PLANE_MCP_TOKEN"] = TOKEN
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
