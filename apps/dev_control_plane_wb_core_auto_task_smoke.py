"""Smoke-check wb-core auto-production arbitration for MCP-submitted tasks."""

from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
from tempfile import TemporaryDirectory
from typing import Any, Mapping
from urllib import request as urllib_request

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (SRC, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dev_control_plane.target_production import acquire_wb_core_production_lock, release_wb_core_production_lock  # noqa: E402

SERVER = ROOT / "apps" / "dev_control_plane_server.py"
TOKEN = "auto-task-smoke-token-0123456789abcdef0123456789abcdef"


def main() -> None:
    _exclusive_when_idle()
    _blocked_when_active_run_exists()
    _blocked_when_lock_busy()
    _blocked_when_candidate_waits()
    _concurrent_submissions_single_winner()
    _verifier_failed_never_promotes()
    print("dev-control-plane-wb-core-auto-task-smoke passed")


def _exclusive_when_idle() -> None:
    with _running_server() as ctx:
        result = _tool(
            ctx.base_url,
            "start_wb_core_auto_task",
            {"task_text": "Auto arbitration smoke exclusive", "idempotency_key": "exclusive", "max_wait_seconds": 5},
        )
        if result.get("route") != "wb_core_exclusive_auto_production" or result.get("auto_production_allowed") is not True:
            raise AssertionError(f"idle wb-core auto task must classify as exclusive: {result}")
        status = _tool(ctx.base_url, "get_run_status", {"run_id": result["run_id"]})
        if status.get("status") != "production_complete" or status.get("deferred_for_separate_deploy") is True:
            raise AssertionError(f"exclusive stub run must finish production_complete without deferral: {status}")
        if status.get("run_type") == "sprint" or status.get("child_run_ids") or status.get("parent_run_id"):
            raise AssertionError(f"direct auto task must not create sprint parent/child state: {status}")
        replay = _tool(
            ctx.base_url,
            "start_wb_core_auto_task",
            {"task_text": "Auto arbitration smoke exclusive duplicate", "idempotency_key": "exclusive", "max_wait_seconds": 5},
        )
        if replay.get("run_id") != result.get("run_id") or replay.get("idempotent_replay") is not True:
            raise AssertionError(f"idempotency_key must replay existing auto run: {replay}")


def _blocked_when_active_run_exists() -> None:
    with _running_server() as ctx:
        _write_collection(
            ctx.state_dir,
            "mcp_runs",
            {
                "active-wb-core-run": {
                    "run_id": "active-wb-core-run",
                    "target_id": "wb-core",
                    "status": "running_codex",
                    "current_stage": "running_codex",
                    "execution_mode": "managed_clone_only",
                    "created_at": "2099-01-01T00:00:00Z",
                    "updated_at": "2099-01-01T00:00:00Z",
                }
            },
        )
        result = _tool(
            ctx.base_url,
            "start_wb_core_auto_task",
            {"task_text": "Auto arbitration smoke deferred active", "idempotency_key": "active", "max_wait_seconds": 5},
        )
        _assert_blocked_result(result, "active non-terminal wb-core run")


def _blocked_when_lock_busy() -> None:
    with _running_server() as ctx:
        workspace = ctx.state_dir / "workspaces" / "lock-smoke" / "wb-core"
        run_dir = ctx.state_dir / "runs" / "lock-smoke"
        workspace.mkdir(parents=True)
        run_dir.mkdir(parents=True)
        lock = acquire_wb_core_production_lock(workspace_path=workspace, run_dir=run_dir, run_id="busy-lock-run")
        try:
            result = _tool(
                ctx.base_url,
                "start_wb_core_auto_task",
                {"task_text": "Auto arbitration smoke deferred lock", "idempotency_key": "lock", "max_wait_seconds": 5},
            )
            _assert_blocked_result(result, "production lock")
        finally:
            release_wb_core_production_lock(lock)


def _blocked_when_candidate_waits() -> None:
    with _running_server() as ctx:
        _write_collection(
            ctx.state_dir,
            "parallel_promotion_groups",
            {
                "promotion-group-deferred-smoke": {
                    "group_id": "promotion-group-deferred-smoke",
                    "target_id": "wb-core",
                    "status": "partially_deployed",
                    "current_step": "partially_deployed",
                    "selected_ids": ["mcp-managed-deferred-smoke"],
                    "deferred_task_ids": ["mcp-managed-deferred-smoke"],
                    "per_task_status": {"mcp-managed-deferred-smoke": "ready_for_separate_deploy"},
                    "created_at": "2099-01-01T00:00:00Z",
                    "updated_at": "2099-01-01T00:00:00Z",
                }
            },
        )
        result = _tool(
            ctx.base_url,
            "start_wb_core_auto_task",
            {"task_text": "Auto arbitration smoke deferred candidate", "idempotency_key": "deferred-candidate", "max_wait_seconds": 5},
        )
        _assert_blocked_result(result, "separate deploy")


def _concurrent_submissions_single_winner() -> None:
    with _running_server(stub_delay_seconds=1.0) as ctx:
        results: list[dict[str, Any]] = []
        errors: list[BaseException] = []

        def call(index: int) -> None:
            try:
                results.append(
                    _tool(
                        ctx.base_url,
                        "start_wb_core_auto_task",
                        {
                            "task_text": f"Auto arbitration concurrent {index}",
                            "idempotency_key": f"concurrent-{index}",
                            "max_wait_seconds": 0,
                        },
                    )
                )
            except BaseException as exc:  # pragma: no cover - surfaced below
                errors.append(exc)

        threads = [threading.Thread(target=call, args=(index,)) for index in (1, 2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
        if errors:
            raise AssertionError(f"concurrent auto task call failed: {errors}")
        routes = [result.get("route") for result in results]
        if routes.count("wb_core_exclusive_auto_production") != 1 or routes.count("wb_core_direct_auto_blocked") != 1:
            raise AssertionError(f"exactly one concurrent auto task may win direct production exclusivity: {results}")
        for result in results:
            if result.get("route") == "wb_core_direct_auto_blocked":
                _assert_blocked_result(result, "active wb-core auto-production intent")
                continue
            final = _wait_run_status(ctx.base_url, str(result.get("run_id") or ""), {"production_complete", "blocked", "failed"})
            if final.get("status") != "production_complete":
                raise AssertionError(f"exclusive concurrent task must finish production_complete: {final}")


def _verifier_failed_never_promotes() -> None:
    with _running_server(stub_verifier_status="failed") as ctx:
        result = _tool(
            ctx.base_url,
            "start_wb_core_auto_task",
            {"task_text": "Auto arbitration smoke verifier failure", "idempotency_key": "verifier-failed", "max_wait_seconds": 5},
        )
        status = _tool(ctx.base_url, "get_run_status", {"run_id": result["run_id"]})
        if status.get("status") != "blocked" or status.get("verifier_status") != "failed":
            raise AssertionError(f"verifier failed auto task must block: {status}")
        if status.get("production_lane_started") is not False or status.get("branch_pr_created") not in {False, None}:
            raise AssertionError(f"verifier failed auto task must not PR/merge/deploy: {status}")


def _assert_blocked_result(result: Mapping[str, Any], reason_token: str) -> None:
    if result.get("status") != "blocked" or result.get("route") != "wb_core_direct_auto_blocked":
        raise AssertionError(f"busy wb-core auto task must return blocker before fallback execution: {result}")
    if result.get("accepted") is not False or result.get("run_id"):
        raise AssertionError(f"blocked direct auto task must not create a managed-clone-only run: {result}")
    if result.get("fallback_to_sprint") is not False or result.get("fallback_to_managed_clone_only") is not False:
        raise AssertionError(f"blocked direct auto task must forbid sprint/managed-clone fallback: {result}")
    reason = str(result.get("blocker") or result.get("separate_deploy_reason") or "")
    if reason_token not in reason:
        raise AssertionError(f"direct auto blocker must mention {reason_token!r}: {result}")


class _ServerContext:
    def __init__(self, process: subprocess.Popen[str], base_url: str, state_dir: Path) -> None:
        self.process = process
        self.base_url = base_url
        self.state_dir = state_dir

    def __enter__(self) -> "_ServerContext":
        global _CURRENT_BASE_URL
        _CURRENT_BASE_URL = self.base_url
        return self

    def __exit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)
        tmp = getattr(self, "_tmp", None)
        if tmp is not None:
            tmp.cleanup()


_CURRENT_BASE_URL = ""


def _running_server(*, stub_delay_seconds: float = 0.0, stub_verifier_status: str = "passed") -> _ServerContext:
    tmp_raw = TemporaryDirectory(prefix="dev-control-plane-auto-task-")
    tmp = Path(tmp_raw.name)
    state_dir = tmp / "state"
    port = _free_port()
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
        env=_server_env(tmp, stub_delay_seconds=stub_delay_seconds, stub_verifier_status=stub_verifier_status),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    startup_line = process.stdout.readline() if process.stdout else ""
    if not startup_line:
        stderr = process.stderr.read() if process.stderr else ""
        raise RuntimeError(f"server did not print startup payload: {stderr}")
    try:
        startup = json.loads(startup_line)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"server startup payload is not JSON: {startup_line!r}") from exc
    context = _ServerContext(process, f"http://127.0.0.1:{int(startup.get('port') or port)}", state_dir)
    context._tmp = tmp_raw  # type: ignore[attr-defined]
    _wait_ready(context.base_url)
    return context


def _server_env(tmp: Path, *, stub_delay_seconds: float, stub_verifier_status: str) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("OPENAI_API_KEY", None)
    env["DEV_CONTROL_PLANE_SECRET_HOME"] = str(tmp / "secrets")
    env["DEV_CONTROL_PLANE_MCP_TOKEN"] = TOKEN
    env["DEV_CONTROL_PLANE_MCP_FAKE_RUNS"] = "1"
    env["DEV_CONTROL_PLANE_WB_CORE_AUTO_TASK_MODE"] = "stub"
    env["DEV_CONTROL_PLANE_WB_CORE_AUTO_TASK_STUB_VERIFIER_STATUS"] = stub_verifier_status
    if stub_delay_seconds:
        env["DEV_CONTROL_PLANE_WB_CORE_AUTO_TASK_STUB_DELAY_SECONDS"] = str(stub_delay_seconds)
    return env


def _tool(base_url: str, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
    result = _mcp(base_url, "tools/call", {"name": name, "arguments": dict(arguments)}, token=TOKEN)
    structured = result.get("structuredContent")
    if isinstance(structured, dict):
        return structured
    raise AssertionError(f"MCP tool result missing structuredContent for {name}: {result}")


def _mcp(base_url: str, method: str, params: Mapping[str, Any], *, token: str | None = None) -> dict[str, Any]:
    body = json.dumps({"jsonrpc": "2.0", "id": f"smoke-{time.time_ns()}", "method": method, "params": params}).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib_request.Request(base_url + "/mcp", data=body, method="POST", headers=headers)
    with urllib_request.urlopen(req, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if "error" in payload:
        raise AssertionError(f"MCP error for {method}: {payload}")
    return payload.get("result") or {}


def _wait_run_status(base_url: str, run_id: str, statuses: set[str]) -> dict[str, Any]:
    deadline = time.time() + 15
    last: dict[str, Any] = {}
    while time.time() < deadline:
        last = _tool(base_url, "get_run_status", {"run_id": run_id})
        if str(last.get("status") or "") in statuses:
            return last
        time.sleep(0.2)
    raise AssertionError(f"run {run_id} did not reach {statuses}: {last}")


def _wait_ready(base_url: str) -> None:
    deadline = time.time() + 10
    last_error: object = None
    while time.time() < deadline:
        try:
            with urllib_request.urlopen(base_url + "/api/state", timeout=5) as response:
                if response.status == 200:
                    return
        except Exception as exc:
            last_error = exc
            time.sleep(0.1)
    raise RuntimeError(f"server did not become ready at {base_url}: {last_error}")


def _write_collection(state_dir: Path, name: str, payload: Mapping[str, Any]) -> None:
    path = state_dir / "collections" / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


if __name__ == "__main__":
    main()
