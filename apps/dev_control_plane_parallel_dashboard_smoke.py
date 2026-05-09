"""Smoke-check operator-visible parallel task dashboard and guarded modes."""

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


def main() -> None:
    port = _free_port()
    with TemporaryDirectory(prefix="dev-control-plane-parallel-dashboard-") as tmp_raw:
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

            first = _submit(base_url, "chat-a", "parallel dashboard first")
            second = _submit(base_url, "chat-b", "parallel dashboard second")
            blocked = _submit(base_url, "chat-c", "parallel dashboard blocked")

            _post_json(base_url + f"/api/parallel-tasks/{first}/start-execution", {"starter_mode": "fake"})
            real_stub = _post_json(
                base_url + f"/api/parallel-tasks/{second}/start-execution",
                {"execution_mode": "real_managed_clone", "run_id": "pmr-real-stub-dashboard"},
            )
            if real_stub.get("status") != "managed_run_running" or real_stub.get("real_mode_stubbed") is not True:
                raise AssertionError(f"stubbed real managed mode should bind state only: {real_stub}")
            if real_stub.get("codex_started") is not False or real_stub.get("production_lane_started") is not False:
                raise AssertionError(f"stubbed real managed mode must not start Codex/production: {real_stub}")

            _post_json(
                base_url + f"/api/parallel-tasks/{first}/reconcile",
                {
                    "run_status": "passed",
                    "verifier_status": "passed",
                    "changed_files": ["docs/parallel-dashboard.md"],
                    "verifier_summary": {"forbidden_paths_clean": True, "source": "dashboard-smoke"},
                },
            )
            _post_json(
                base_url + f"/api/parallel-tasks/{second}/reconcile",
                {
                    "run_status": "passed",
                    "verifier_status": "passed",
                    "changed_files": ["docs/parallel-second.md"],
                    "verifier_summary": {"forbidden_paths_clean": True, "source": "dashboard-smoke"},
                },
            )
            _post_json(
                base_url + f"/api/parallel-tasks/{blocked}/reconcile",
                {"run_status": "blocked", "blocker": "dashboard smoke blocker"},
            )

            single_plan = _post_json(
                base_url + "/api/parallel-selection/promote",
                {
                    "target_id": "wb-core",
                    "selected_ids": [first],
                    "selection_type": "task_id",
                    "plan_only": True,
                },
            )
            if single_plan.get("status") != "plan_ready" or single_plan.get("group_created") is not False:
                raise AssertionError(f"single selected promotion should plan without group block: {single_plan}")

            group_plan = _post_json(
                base_url + "/api/parallel-selection/promote",
                {
                    "target_id": "wb-core",
                    "selected_ids": [first, second],
                    "selection_type": "task_id",
                    "mode": "auto_order",
                    "confirm_merge_deploy": True,
                    "allow_real_production_promotion": True,
                },
            )
            if group_plan.get("status") != "group_plan_ready" or not group_plan.get("group_id") or group_plan.get("production_lane_started") is not False:
                raise AssertionError(f"group selected promotion should create a test-safe group block: {group_plan}")
            live = _get_json(base_url + "/api/runs/live")
            if not any(run.get("run_id") == group_plan.get("group_id") and run.get("run_type") == "group_promotion" for run in live.get("runs", [])):
                raise AssertionError(f"group promotion block should be visible in monitoring runs: {live}")

            bridged = _post_json(
                base_url + "/api/parallel-targets/wb-core/promote-next",
                {
                    "allow_auto_first_promotion": True,
                    "allow_real_production_promotion": True,
                    "mode": "real_production_bridge",
                },
            )
            if bridged.get("status") != "production_bridge_stubbed" or bridged.get("real_production_lane_started") is not False:
                raise AssertionError(f"production bridge must be stubbed/test-safe in smoke: {bridged}")

            html = _get_text(base_url + "/")
            for token in (
                "Parallel task ledger",
                "frozen_base_stale / refresh_required",
                "Promote next dry",
                "Promote next fake",
                "Parallel action running",
                "fake start",
                "fake complete",
            ):
                if token not in html:
                    raise AssertionError(f"dashboard must expose parallel operator UI token: {token}")
            for forbidden in ("executor_command", "terminal input", "shell command", "Authorization: Bearer"):
                if forbidden in html:
                    raise AssertionError(f"dashboard must not expose unsafe parallel UI token: {forbidden}")

            monitor = _get_text(base_url + "/runs/live")
            for token in ("Мониторинг", "Merge & Deploy", 'data-role="promote-select"', "summaryTime", "summaryChanges"):
                if token not in monitor:
                    raise AssertionError(f"monitoring UI must expose selected promotion/card timing token: {token}")
            if "Живые запуски" in monitor:
                raise AssertionError("monitoring UI must not use the old primary section label")

            listed = _get_json(base_url + "/api/parallel-tasks?target_id=wb-core")
            serialized = json.dumps(listed, ensure_ascii=False)
            if "task_text" in serialized or "Authorization: Bearer" in serialized:
                raise AssertionError(f"parallel summaries must stay sanitized: {listed}")
            statuses = {task.get("task_id"): task.get("status") for task in listed.get("tasks", [])}
            if list(statuses.values()).count("production_complete") != 1:
                raise AssertionError(f"one winner should be fake production_complete: {listed}")
            if list(statuses.values()).count("refresh_required") != 1:
                raise AssertionError(f"one sibling should freeze as refresh_required: {listed}")
            if statuses.get(blocked) != "blocked":
                raise AssertionError(f"blocked task should remain visibly blocked: {listed}")

            candidates = _get_json(base_url + "/api/parallel-targets/wb-core/promotion-candidates")
            if not any(candidate.get("refresh_required") is True for candidate in candidates.get("candidates", [])):
                raise AssertionError(f"candidates should expose refresh_required sibling state: {candidates}")
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

    print("dev-control-plane-parallel-dashboard-smoke passed")


def _submit(base_url: str, source_chat: str, text: str) -> str:
    result = _post_json(
        base_url + "/api/parallel-tasks",
        {
            "target_id": "wb-core",
            "task_text": text,
            "source": source_chat,
            "source_chat": source_chat,
        },
    )
    task_id = str(result.get("task_id") or "")
    if result.get("status") != "submitted" or not task_id:
        raise AssertionError(f"submit must create a parallel task: {result}")
    return task_id


def _get_text(url: str) -> str:
    with urllib_request.urlopen(url, timeout=10) as response:
        return response.read().decode("utf-8")


def _get_json(url: str) -> dict[str, Any]:
    with urllib_request.urlopen(url, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _post_json(url: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    body = json.dumps(dict(payload)).encode("utf-8")
    request = urllib_request.Request(url, data=body, method="POST", headers={"Content-Type": "application/json"})
    with urllib_request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


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
    env["DEV_CONTROL_PLANE_SECRET_HOME"] = str(tmp / "secrets")
    env["DEV_CONTROL_PLANE_PARALLEL_REAL_MANAGED_RUNS"] = "stub"
    env["DEV_CONTROL_PLANE_PARALLEL_PRODUCTION_BRIDGE_MODE"] = "stub"
    return env


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


if __name__ == "__main__":
    main()
