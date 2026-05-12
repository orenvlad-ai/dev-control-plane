"""Smoke-check the bounded MCP endpoint, auth, artifacts and parallel run model."""

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
SRC = ROOT / "src"
for path in (SRC, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dev_control_plane.target_production import acquire_wb_core_production_lock, release_wb_core_production_lock  # noqa: E402

SERVER = ROOT / "apps" / "dev_control_plane_server.py"
TOKEN = "mcp-smoke-token-0123456789abcdef0123456789abcdef"


def main() -> None:
    port = _free_port()
    with TemporaryDirectory(prefix="dev-control-plane-mcp-smoke-") as tmp_raw:
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

            initialize = _mcp(base_url, "initialize", {})
            if initialize.get("serverInfo", {}).get("name") != "dev-control-plane":
                raise AssertionError(f"MCP initialize must return server info: {initialize}")
            tools = _mcp(base_url, "tools/list", {})
            names = {tool.get("name") for tool in tools.get("tools", [])}
            read_required = {
                "get_status",
                "get_operator_parity_status",
                "list_targets",
                "list_active_runs",
                "get_run_status",
                "get_run_report",
                "list_run_artifacts",
                "get_run_artifact",
                "get_rollback_plan",
                "search",
                "fetch",
            }
            missing = read_required - names
            if missing:
                raise AssertionError(f"MCP public tools/list missing read tools: {missing}")
            hidden_writes = {
                "start_wb_core_auto_task",
                "start_wb_core_operator_parity_task",
                "start_wb_core_production_lane",
                "start_managed_clone_run",
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
                "resume_wb_core_production_deploy",
                "request_rollback",
            }
            frozen_operator_tools = {"start_sprint"}
            hidden_authenticated_reads = {
                "list_target_docs",
                "search_target_docs",
                "get_target_doc",
                "read_target_docs",
            }
            if names & hidden_writes:
                raise AssertionError(f"MCP public no-auth discovery must hide write tools: {names & hidden_writes}")
            if names & frozen_operator_tools:
                raise AssertionError(f"MCP public no-auth discovery must hide frozen operator tools: {names & frozen_operator_tools}")
            if names & hidden_authenticated_reads:
                raise AssertionError(f"MCP public no-auth discovery must hide authenticated target docs tools: {names & hidden_authenticated_reads}")
            if any("shell" in str(name).lower() or "command" in str(name).lower() for name in names):
                raise AssertionError(f"MCP must not expose arbitrary shell/command tools: {names}")
            _assert_tool_metadata(tools.get("tools", []), expect_write_tools=False)

            authed_tools = _mcp(base_url, "tools/list", {}, token=TOKEN)
            authed_names = {tool.get("name") for tool in authed_tools.get("tools", [])}
            if not hidden_writes.issubset(authed_names):
                raise AssertionError(f"MCP authenticated tools/list must include gated write tools: {authed_names}")
            if authed_names & frozen_operator_tools:
                raise AssertionError(f"MCP authenticated operator discovery must not expose frozen sprint tools: {authed_names & frozen_operator_tools}")
            if not hidden_authenticated_reads.issubset(authed_names):
                raise AssertionError(f"MCP authenticated tools/list must include OAuth-gated target docs tools: {authed_names}")
            _assert_tool_metadata(authed_tools.get("tools", []), expect_write_tools=True)

            status = _tool(base_url, "get_status", {})
            if status.get("status") != "ok" or status.get("mcp", {}).get("transport") != "streamable_http":
                raise AssertionError(f"get_status must expose MCP status: {status}")
            if status.get("mcp", {}).get("chatgpt_auth_strategy") != "mixed_noauth_read_oauth_write":
                raise AssertionError(f"get_status must report ChatGPT read-only auth strategy: {status.get('mcp')}")
            if status.get("mcp", {}).get("chatgpt_write_tools_ready") is not True:
                raise AssertionError(f"ChatGPT write tools must be reported ready through OAuth: {status.get('mcp')}")
            targets = _tool(base_url, "list_targets", {})
            if "wb-core" not in [item.get("target_id") for item in targets.get("targets", [])]:
                raise AssertionError(f"list_targets must include wb-core: {targets}")
            active = _tool(base_url, "list_active_runs", {})
            if active.get("status") != "ok":
                raise AssertionError(f"list_active_runs must work: {active}")
            unknown = _tool(base_url, "get_run_status", {"run_id": "missing-run-id"})
            if unknown.get("status") != "not_found":
                raise AssertionError(f"unknown run_id must be controlled not_found: {unknown}")

            denied = _tool(base_url, "start_wb_core_production_lane", {"task_text": "dry run denied", "dry_run": True})
            if denied.get("status") != "denied" or denied.get("chatgpt_write_tools_ready") is not True:
                raise AssertionError(f"unauthenticated write tool must be denied: {denied}")
            docs_denied = _tool(base_url, "list_target_docs", {"target_id": "wb-core"})
            if docs_denied.get("status") != "denied":
                raise AssertionError(f"unauthenticated target docs tool must be denied: {docs_denied}")
            frozen_sprint = _tool(base_url, "start_sprint", {"target_id": "wb-core", "sprint_text": "must not start"}, token=TOKEN)
            if (
                frozen_sprint.get("status") != "blocked"
                or "start_sprint is frozen for operator flow" not in str(frozen_sprint.get("blocker") or "")
                or frozen_sprint.get("run_id")
            ):
                raise AssertionError(f"authenticated start_sprint must be frozen without run creation: {frozen_sprint}")

            prod = _tool(
                base_url,
                "start_wb_core_production_lane",
                {"task_text": "MCP smoke production dry-run one", "dry_run": True, "idempotency_key": "prod-dry-one"},
                token=TOKEN,
            )
            prod_run_id = str(prod.get("run_id") or "")
            if prod.get("status") != "completed_dry_run" or not prod_run_id:
                raise AssertionError(f"authenticated production dry-run must return run_id: {prod}")
            report = _tool(base_url, "get_run_report", {"run_id": prod_run_id})
            if report.get("production_lane_result") or report.get("deploy_result", {}).get("deploy_status"):
                raise AssertionError(f"dry-run must not report PR/deploy mutation: {report}")
            rollback = _tool(base_url, "get_rollback_plan", {"run_id": prod_run_id})
            if rollback.get("status") != "ok" or not rollback.get("rollback_plan", {}).get("commands"):
                raise AssertionError(f"dry-run must expose rollback plan: {rollback}")
            artifacts = _tool(base_url, "list_run_artifacts", {"run_id": prod_run_id})
            artifact_ids = {item.get("artifact_id") for item in artifacts.get("artifacts", [])}
            if not {"prompt", "handoff", "mcp_production_lane_report", "rollback_plan"}.issubset(artifact_ids):
                raise AssertionError(f"dry-run artifacts missing expected ids: {artifacts}")
            prompt = _tool(base_url, "get_run_artifact", {"run_id": prod_run_id, "artifact_id": "prompt"})
            if "MCP smoke production dry-run one" not in prompt.get("content", ""):
                raise AssertionError(f"prompt artifact must be readable: {prompt}")
            secret = _tool(base_url, "get_run_artifact", {"run_id": prod_run_id, "artifact_id": "env"})
            if secret.get("status") != "denied":
                raise AssertionError(f"secret-like artifact request must be denied: {secret}")

            prod2 = _tool(
                base_url,
                "start_wb_core_production_lane",
                {"task_text": "MCP smoke production dry-run two", "dry_run": True},
                token=TOKEN,
            )
            if prod2.get("run_id") == prod_run_id:
                raise AssertionError("two production dry-runs must have distinct run_id values")
            prompt2 = _tool(base_url, "get_run_artifact", {"run_id": prod2["run_id"], "artifact_id": "prompt"})
            if "dry-run two" not in prompt2.get("content", "") or "dry-run one" in prompt2.get("content", ""):
                raise AssertionError("run artifacts must remain isolated")

            managed_one = _tool(
                base_url,
                "start_managed_clone_run",
                {"target_id": "wb-core", "task_text": "managed clone fake one"},
                token=TOKEN,
            )
            managed_two = _tool(
                base_url,
                "start_managed_clone_run",
                {"target_id": "wb-core", "task_text": "managed clone fake two"},
                token=TOKEN,
            )
            if managed_one.get("run_id") == managed_two.get("run_id"):
                raise AssertionError("parallel managed-clone calls must return distinct run_id values")
            one_final = _wait_run_status(base_url, managed_one["run_id"], {"passed", "failed", "blocked"})
            two_final = _wait_run_status(base_url, managed_two["run_id"], {"passed", "failed", "blocked"})
            if one_final.get("status") != "passed" or two_final.get("status") != "passed":
                raise AssertionError(f"fake managed-clone runs must finish independently: {one_final} {two_final}")
            one_prompt = _tool(base_url, "get_run_artifact", {"run_id": managed_one["run_id"], "artifact_id": "prompt"})
            two_prompt = _tool(base_url, "get_run_artifact", {"run_id": managed_two["run_id"], "artifact_id": "prompt"})
            if "fake one" not in one_prompt.get("content", "") or "fake two" in one_prompt.get("content", ""):
                raise AssertionError("managed run one prompt must not mix run two task text")
            if "fake two" not in two_prompt.get("content", "") or "fake one" in two_prompt.get("content", ""):
                raise AssertionError("managed run two prompt must not mix run one task text")

            lock_workspace = state_dir / "workspaces" / "lock-smoke" / "wb-core"
            lock_workspace.mkdir(parents=True)
            lock_run_dir = state_dir / "runs" / "lock-smoke"
            lock_run_dir.mkdir(parents=True)
            lock = acquire_wb_core_production_lock(workspace_path=lock_workspace, run_dir=lock_run_dir, run_id="active-lock-smoke")
            try:
                waiting = _tool(
                    base_url,
                    "start_wb_core_production_lane",
                    {"task_text": "MCP smoke lock waiting", "dry_run": True},
                    token=TOKEN,
                )
                if waiting.get("status") != "waiting_for_target_lock" or waiting.get("lock_wait", {}).get("active_run_id") != "active-lock-smoke":
                    raise AssertionError(f"active lock must return waiting state with active_run_id: {waiting}")
            finally:
                release_wb_core_production_lock(lock)
            free = _tool(base_url, "get_production_lock_status", {"target_id": "wb-core"})
            if free.get("lock_status") != "free":
                raise AssertionError(f"lock must be free after release: {free}")

            search = _tool(base_url, "search", {"query": "MCP"})
            if search.get("status") != "ok" or not search.get("results"):
                raise AssertionError(f"search must return sanitized results: {search}")
            fetched = _tool(base_url, "fetch", {"id": search["results"][0]["id"]})
            if fetched.get("status") in {"failed", "denied", "error"}:
                raise AssertionError(f"fetch must return controlled response: {fetched}")
            _write_mcp_runs(
                state_dir,
                {
                    "mcp-denied-terminal-smoke": {
                        "run_id": "mcp-denied-terminal-smoke",
                        "target_id": "wb-core",
                        "status": "denied",
                        "current_stage": "cancelled",
                        "blocker": "operator requested cancel from live monitor",
                        "created_at": "2099-01-01T00:00:00Z",
                        "updated_at": "2099-01-01T00:00:00Z",
                    }
                },
            )
            active_after_denied = _tool(base_url, "list_active_runs", {})
            if "mcp-denied-terminal-smoke" in [run.get("run_id") for run in active_after_denied.get("runs", [])]:
                raise AssertionError(f"denied/cancelled terminal run must not stay active: {active_after_denied}")

            state_text = "\n".join(path.read_text(encoding="utf-8", errors="replace") for path in state_dir.rglob("*") if path.is_file())
            auth_header_marker = "Authorization:" + " Bearer"
            if TOKEN in state_text or auth_header_marker in state_text:
                raise AssertionError("MCP token or Authorization header leaked into state/audit/artifacts")
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

    print("dev-control-plane-mcp-smoke passed")


def _mcp(base_url: str, method: str, params: Mapping[str, Any], *, token: str | None = None) -> dict[str, Any]:
    body = json.dumps({"jsonrpc": "2.0", "id": f"smoke-{time.time_ns()}", "method": method, "params": params}).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib_request.Request(base_url + "/mcp", data=body, method="POST", headers=headers)
    with urllib_request.urlopen(request, timeout=10) as response:
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
    raise AssertionError(f"run did not reach terminal status: {last}")


def _assert_tool_metadata(tools: list[Mapping[str, Any]], *, expect_write_tools: bool) -> None:
    write_tools = {"start_wb_core_auto_task", "start_wb_core_operator_parity_task", "start_wb_core_production_lane", "start_managed_clone_run", "submit_parallel_task", "start_parallel_task_execution", "reconcile_parallel_task", "promote_parallel_task", "promote_next_parallel_candidate", "promote_parallel_selection", "merge_deploy_ready_run", "refresh_selected_candidate", "clear_wb_core_promotion_queue", "archive_wb_core_auto_task_run", "resume_wb_core_production_deploy", "request_rollback"}
    authenticated_read_tools = {"list_target_docs", "search_target_docs", "get_target_doc", "read_target_docs"}
    for tool in tools:
        name = str(tool.get("name") or "")
        if not tool.get("description"):
            raise AssertionError(f"tool description is required: {tool}")
        annotations = tool.get("annotations") or {}
        meta = tool.get("_meta") or {}
        if name in write_tools:
            if not expect_write_tools:
                raise AssertionError(f"public tools/list must not include write tool: {name}")
            if annotations.get("readOnlyHint") is not False:
                raise AssertionError(f"write tool must not be marked read-only: {tool}")
            if not meta.get("dev-control-plane/auth"):
                raise AssertionError(f"write tool must carry auth marker metadata: {tool}")
            schemes = tool.get("securitySchemes") or meta.get("securitySchemes") or []
            if {"type": "oauth2", "scopes": ["dcp.write"]} not in schemes:
                raise AssertionError(f"write tool must advertise OAuth write scope: {tool}")
        elif name in authenticated_read_tools:
            if not expect_write_tools:
                raise AssertionError(f"public tools/list must not include authenticated read tool: {name}")
            if annotations.get("readOnlyHint") is not True or annotations.get("destructiveHint") is not False:
                raise AssertionError(f"authenticated read tool must be marked read-only/non-destructive: {tool}")
            if meta.get("dev-control-plane/exposure") != "oauth_protected_read_only":
                raise AssertionError(f"authenticated read tool must carry exposure metadata: {tool}")
            schemes = tool.get("securitySchemes") or meta.get("securitySchemes") or []
            if {"type": "oauth2", "scopes": ["dcp.write"]} not in schemes:
                raise AssertionError(f"authenticated read tool must advertise OAuth session scope: {tool}")
        else:
            if annotations.get("readOnlyHint") is not True:
                raise AssertionError(f"read tool must carry readOnlyHint=true: {tool}")
            schemes = tool.get("securitySchemes") or meta.get("securitySchemes") or []
            if {"type": "noauth"} not in schemes:
                raise AssertionError(f"read tool must advertise noauth security scheme: {tool}")


def _write_mcp_runs(state_dir: Path, updates: Mapping[str, Mapping[str, Any]]) -> None:
    path = state_dir / "collections" / "mcp_runs.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if not isinstance(existing, dict):
        existing = {}
    existing.update({key: dict(value) for key, value in updates.items()})
    path.write_text(json.dumps(existing, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _wait_ready(base_url: str) -> None:
    deadline = time.time() + 10
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib_request.urlopen(base_url + "/api/state", timeout=2) as response:
                json.loads(response.read().decode("utf-8"))
            return
        except Exception as exc:
            last_error = exc
            time.sleep(0.1)
    raise AssertionError(f"server did not become ready: {last_error}")


def _server_env(tmp: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("OPENAI_API_KEY", None)
    env.pop("CURATOR_COCKPIT_OPENAI_MODEL", None)
    env.pop("CURATOR_COCKPIT_OPENAI_REASONING_EFFORT", None)
    env["DEV_CONTROL_PLANE_SECRET_HOME"] = str(tmp / "secrets")
    env["DEV_CONTROL_PLANE_MCP_TOKEN"] = TOKEN
    env["DEV_CONTROL_PLANE_MCP_FAKE_RUNS"] = "1"
    env["DEV_CONTROL_PLANE_ENABLE_FAKE_CURATOR"] = "1"
    return env


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


if __name__ == "__main__":
    main()
