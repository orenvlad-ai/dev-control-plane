"""Smoke-check parallel task ledger API and MCP surface."""

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
TOKEN = "parallel-ledger-smoke-token-0123456789abcdef0123456789abcdef"


def main() -> None:
    port = _free_port()
    with TemporaryDirectory(prefix="dev-control-plane-parallel-api-") as tmp_raw:
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

            state = _get_json(base_url + "/api/state")
            ledger_status = state.get("parallel_task_ledger") or {}
            if ledger_status.get("parallel_ping_pong_enabled") is not False:
                raise AssertionError(f"state must expose frozen parallel ping-pong: {ledger_status}")

            first = _post_json(
                base_url + "/api/parallel-tasks",
                {
                    "target_id": "wb-core",
                    "task_text": "Parallel API smoke task from chat A",
                    "source": "chatgpt-project-a",
                    "source_chat": "chat-a",
                    "idempotency_key": "parallel-api-same-request",
                },
            )
            first_task_id = str(first.get("task_id") or "")
            if first.get("status") != "submitted" or not first_task_id:
                raise AssertionError(f"API submit must create a task record: {first}")
            for key in ("execution_started", "codex_started", "production_lane_started", "ping_pong_started"):
                if first.get(key) is not False:
                    raise AssertionError(f"submit must not start execution side effects: {first}")

            duplicate = _post_json(
                base_url + "/api/parallel-tasks",
                {
                    "target_id": "wb-core",
                    "task_text": "Duplicate should not create a second task",
                    "source": "chatgpt-project-a",
                    "source_chat": "chat-a",
                    "idempotency_key": "parallel-api-same-request",
                },
            )
            if duplicate.get("task_id") != first_task_id:
                raise AssertionError(f"idempotency_key must replay existing task id: {duplicate}")

            second = _post_json(
                base_url + "/api/parallel-tasks",
                {
                    "target_id": "wb-core",
                    "task_text": "Parallel API smoke task from MCP B",
                    "source": "mcp-tool-b",
                    "source_chat": "chat-b",
                    "release_group": "release-smoke",
                },
            )
            if second.get("task", {}).get("release_group") != "release-smoke":
                raise AssertionError(f"release_group must be optional metadata: {second}")

            listed = _get_json(base_url + "/api/parallel-tasks?target_id=wb-core")
            tasks = listed.get("tasks") or []
            if len(tasks) != 2:
                raise AssertionError(f"API list should contain two unique tasks: {listed}")
            epochs = {task.get("promotion_epoch") for task in tasks}
            if len(epochs) != 1:
                raise AssertionError(f"different sources should share one target promotion epoch: {listed}")
            if {task.get("source") for task in tasks} != {"chatgpt-project-a", "mcp-tool-b"}:
                raise AssertionError(f"API list should preserve source metadata: {listed}")
            if any("task_text" in task for task in tasks):
                raise AssertionError(f"parallel task summaries must not expose full task_text: {listed}")

            fetched = _get_json(base_url + f"/api/parallel-tasks/{first_task_id}")
            if fetched.get("task", {}).get("task_id") != first_task_id:
                raise AssertionError(f"API get should return the requested task: {fetched}")
            promotion = _get_json(base_url + "/api/parallel-targets/wb-core/promotion-state")
            if promotion.get("status") != "ok" or promotion.get("target_id") != "wb-core":
                raise AssertionError(f"promotion state must be readable for target: {promotion}")

            public_tools = _mcp(base_url, "tools/list", {})
            public_names = {tool.get("name") for tool in public_tools.get("tools", [])}
            for expected in ("list_parallel_tasks", "get_parallel_task", "list_parallel_candidates", "get_target_promotion_state"):
                if expected not in public_names:
                    raise AssertionError(f"public discovery must expose sanitized read tool {expected}: {public_names}")
            hidden_parallel_writes = {
                "submit_parallel_task",
                "start_parallel_task_execution",
                "reconcile_parallel_task",
                "promote_parallel_task",
                "promote_next_parallel_candidate",
                "promote_parallel_selection",
                "merge_deploy_ready_run",
                "refresh_selected_candidate",
                "clear_wb_core_promotion_queue",
                "archive_wb_core_auto_task_run",
            }
            if public_names & hidden_parallel_writes:
                raise AssertionError(f"public no-auth discovery must hide parallel write tools: {public_names & hidden_parallel_writes}")
            denied = _tool(
                base_url,
                "submit_parallel_task",
                {"target_id": "wb-core", "task_text": "must not submit without auth"},
            )
            if denied.get("status") != "denied":
                raise AssertionError(f"no-auth submit_parallel_task must be denied: {denied}")
            denied_start = _tool(base_url, "start_parallel_task_execution", {"task_id": first_task_id})
            if denied_start.get("status") != "denied":
                raise AssertionError(f"no-auth start_parallel_task_execution must be denied: {denied_start}")
            denied_selection = _tool(
                base_url,
                "promote_parallel_selection",
                {"target_id": "wb-core", "selected_ids": [first_task_id], "confirm_merge_deploy": True},
            )
            if denied_selection.get("status") != "denied":
                raise AssertionError(f"no-auth promote_parallel_selection must be denied: {denied_selection}")
            denied_single_merge = _tool(base_url, "merge_deploy_ready_run", {"target_id": "wb-core", "run_id": "missing", "confirm_merge_deploy": True})
            if denied_single_merge.get("status") != "denied":
                raise AssertionError(f"no-auth merge_deploy_ready_run must be denied: {denied_single_merge}")
            denied_refresh = _tool(base_url, "refresh_selected_candidate", {"target_id": "wb-core", "source_run_id": "missing"})
            if denied_refresh.get("status") != "denied":
                raise AssertionError(f"no-auth refresh_selected_candidate must be denied: {denied_refresh}")
            denied_cleanup = _tool(base_url, "clear_wb_core_promotion_queue", {"target_id": "wb-core", "reason": "must not clear without auth"})
            if denied_cleanup.get("status") != "denied":
                raise AssertionError(f"no-auth clear_wb_core_promotion_queue must be denied: {denied_cleanup}")
            denied_archive = _tool(base_url, "archive_wb_core_auto_task_run", {"target_id": "wb-core", "run_id": "missing", "reason": "must not archive without auth"})
            if denied_archive.get("status") != "denied":
                raise AssertionError(f"no-auth archive_wb_core_auto_task_run must be denied: {denied_archive}")
            real_start_blocked = _tool(
                base_url,
                "start_parallel_task_execution",
                {"task_id": first_task_id, "execution_mode": "real_managed_clone", "confirm_real_managed_clone": True},
                token=TOKEN,
            )
            if real_start_blocked.get("status") != "blocked" or real_start_blocked.get("codex_started") is not False:
                raise AssertionError(f"guarded real managed execution must be disabled by default: {real_start_blocked}")

            authed_tools = _mcp(base_url, "tools/list", {}, token=TOKEN)
            submit_tool = next((tool for tool in authed_tools.get("tools", []) if tool.get("name") == "submit_parallel_task"), None)
            if not submit_tool:
                raise AssertionError("authenticated discovery must expose submit_parallel_task")
            authed_names = {tool.get("name") for tool in authed_tools.get("tools", [])}
            if not hidden_parallel_writes.issubset(authed_names):
                raise AssertionError(f"authenticated discovery must expose parallel write tools: {authed_names}")
            annotations = submit_tool.get("annotations") or {}
            if annotations.get("readOnlyHint") is not False or annotations.get("destructiveHint") is not False:
                raise AssertionError(f"submit_parallel_task must be write but non-destructive: {submit_tool}")
            schemes = submit_tool.get("securitySchemes") or (submit_tool.get("_meta") or {}).get("securitySchemes") or []
            if {"type": "oauth2", "scopes": ["dcp.write"]} not in schemes:
                raise AssertionError(f"submit_parallel_task must advertise OAuth write scope: {submit_tool}")

            mcp_submit = _tool(
                base_url,
                "submit_parallel_task",
                {
                    "target_id": "wb-core",
                    "task_text": "Parallel MCP smoke task from chat C",
                    "source": "chatgpt-project-c",
                    "source_chat": "chat-c",
                    "source_tool": "chatgpt-mcp",
                    "batch_id": "batch-smoke",
                    "idempotency_key": "parallel-mcp-same-request",
                },
                token=TOKEN,
            )
            mcp_task_id = str(mcp_submit.get("task_id") or "")
            if mcp_submit.get("status") != "submitted" or not mcp_task_id:
                raise AssertionError(f"authenticated MCP submit should create ledger task: {mcp_submit}")
            if any(mcp_submit.get(key) is not False for key in ("execution_started", "codex_started", "production_lane_started", "ping_pong_started")):
                raise AssertionError(f"MCP submit must not start execution side effects: {mcp_submit}")
            mcp_replay = _tool(
                base_url,
                "submit_parallel_task",
                {
                    "target_id": "wb-core",
                    "task_text": "Parallel MCP duplicate",
                    "source": "chatgpt-project-c",
                    "idempotency_key": "parallel-mcp-same-request",
                },
                token=TOKEN,
            )
            if mcp_replay.get("task_id") != mcp_task_id:
                raise AssertionError(f"MCP idempotency must replay task id: {mcp_replay}")

            started = _tool(base_url, "start_parallel_task_execution", {"task_id": mcp_task_id}, token=TOKEN)
            if started.get("status") != "managed_run_running" or started.get("codex_started") is not False:
                raise AssertionError(f"MCP start execution must bind fake run only: {started}")
            reconciled = _tool(
                base_url,
                "reconcile_parallel_task",
                {
                    "task_id": mcp_task_id,
                    "run_status": "passed",
                    "verifier_status": "passed",
                    "changed_files": ["docs/parallel.md"],
                    "verifier_summary": {"forbidden_paths_clean": True},
                },
                token=TOKEN,
            )
            if reconciled.get("status") != "verifier_passed" or reconciled.get("production_lane_started") is not False:
                raise AssertionError(f"MCP reconcile passed should create candidate only: {reconciled}")
            candidates = _tool(base_url, "list_parallel_candidates", {"target_id": "wb-core"})
            if not any(candidate.get("task_id") == mcp_task_id for candidate in candidates.get("candidates", [])):
                raise AssertionError(f"MCP candidates should include reconciled task: {candidates}")
            selected_plan = _tool(
                base_url,
                "promote_parallel_selection",
                {
                    "target_id": "wb-core",
                    "selected_ids": [mcp_task_id],
                    "selection_type": "task_id",
                    "plan_only": True,
                },
                token=TOKEN,
            )
            if selected_plan.get("status") != "plan_ready" or selected_plan.get("group_created") is not False:
                raise AssertionError(f"MCP selected promotion plan should resolve a task_id candidate: {selected_plan}")
            queued = _tool(base_url, "promote_parallel_task", {"task_id": mcp_task_id}, token=TOKEN)
            if queued.get("status") != "promotion_queued" or queued.get("real_production_lane_started") is not False:
                raise AssertionError(f"MCP promote without policy should queue only: {queued}")
            real_bridge_blocked = _tool(
                base_url,
                "promote_parallel_task",
                {
                    "task_id": mcp_task_id,
                    "allow_auto_first_promotion": True,
                    "allow_real_production_promotion": True,
                    "mode": "real_production_bridge",
                },
                token=TOKEN,
            )
            if real_bridge_blocked.get("status") != "blocked" or real_bridge_blocked.get("real_production_lane_started") is not False:
                raise AssertionError(f"real production bridge must be disabled by default: {real_bridge_blocked}")
            promoted = _tool(
                base_url,
                "promote_next_parallel_candidate",
                {"target_id": "wb-core", "allow_auto_first_promotion": True, "mode": "dry_run"},
                token=TOKEN,
            )
            if promoted.get("status") != "auto_promoting_first" or promoted.get("real_production_lane_started") is not False:
                raise AssertionError(f"MCP promote with policy should update state without real production: {promoted}")

            mcp_list = _tool(base_url, "list_parallel_tasks", {"target_id": "wb-core"})
            if len(mcp_list.get("tasks") or []) != 3:
                raise AssertionError(f"MCP list should see three unique ledger tasks: {mcp_list}")
            mcp_get = _tool(base_url, "get_parallel_task", {"task_id": mcp_task_id})
            if mcp_get.get("task", {}).get("batch_id") != "batch-smoke":
                raise AssertionError(f"MCP get should return sanitized task metadata: {mcp_get}")
            mcp_state = _tool(base_url, "get_target_promotion_state", {"target_id": "wb-core"})
            if mcp_state.get("status") != "ok" or mcp_state.get("parallel_ping_pong_enabled") is not False:
                raise AssertionError(f"MCP promotion state should be readable and ping-pong frozen: {mcp_state}")

            status = _tool(base_url, "get_status", {})
            registry = (status.get("mcp") or {}).get("tool_registry") or {}
            if registry.get("registry_definition_parity") is not True:
                raise AssertionError(f"MCP registry/definition parity must stay clean: {registry}")
            intake = (status.get("mcp") or {}).get("parallel_task_intake") or {}
            if intake.get("execution_started_on_submit") is not False or intake.get("ping_pong_enabled") is not False:
                raise AssertionError(f"get_status must expose state-only parallel intake: {intake}")

            mcp_runs_path = state_dir / "collections" / "mcp_runs.json"
            if mcp_runs_path.exists() and json.loads(mcp_runs_path.read_text(encoding="utf-8") or "{}"):
                raise AssertionError("parallel task submit must not create MCP run records")

            old_managed = _tool(
                base_url,
                "start_managed_clone_run",
                {"target_id": "wb-core", "task_text": "old managed run selection resolver smoke", "no_pr_no_deploy": True},
                token=TOKEN,
            )
            old_run_id = str(old_managed.get("run_id") or "")
            if old_managed.get("status") != "queued" or not old_run_id:
                raise AssertionError(f"fake managed-clone start should return a run_id: {old_managed}")
            final_old_run = _wait_run_status(base_url, old_run_id, {"passed", "failed", "blocked"})
            if final_old_run.get("status") != "passed":
                raise AssertionError(f"fake managed run should pass before resolver test: {final_old_run}")
            old_run_selection = _tool(
                base_url,
                "promote_parallel_selection",
                {
                    "target_id": "wb-core",
                    "selected_ids": [old_run_id],
                    "selection_type": "run_id",
                    "plan_only": True,
                },
                token=TOKEN,
            )
            ordered = (((old_run_selection.get("plan") or {}).get("ordered")) or [{}])[0]
            if old_run_selection.get("status") != "plan_ready" or ordered.get("source_kind") != "managed_run":
                raise AssertionError(f"selected promotion must resolve verifier-passed managed run_id: {old_run_selection}")
            state_text = "\n".join(
                path.read_text(encoding="utf-8", errors="replace")
                for path in state_dir.rglob("*")
                if path.is_file()
            )
            for forbidden in (TOKEN, "Authorization: Bearer", "mcp-sprint-", "mcp-prod-", "start_wb_core_production_lane"):
                if forbidden in state_text:
                    raise AssertionError(f"parallel task state leaked forbidden marker or side effect: {forbidden}")
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

    print("dev-control-plane-parallel-api-mcp-smoke passed")


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


def _wait_run_status(base_url: str, run_id: str, terminal: set[str]) -> dict[str, Any]:
    deadline = time.time() + 10
    last: dict[str, Any] = {}
    while time.time() < deadline:
        last = _tool(base_url, "get_run_status", {"run_id": run_id})
        if str(last.get("status") or "") in terminal:
            return last
        time.sleep(0.1)
    raise AssertionError(f"run {run_id} did not reach terminal status: {last}")


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
    env["DEV_CONTROL_PLANE_MCP_TOKEN"] = TOKEN
    env["DEV_CONTROL_PLANE_MCP_FAKE_RUNS"] = "1"
    return env


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


if __name__ == "__main__":
    main()
