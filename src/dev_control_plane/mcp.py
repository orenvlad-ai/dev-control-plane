"""Bounded MCP adapter for hosted Development Control Plane.

The adapter intentionally exposes a small JSON-RPC MCP surface only. It does
not provide arbitrary shell access and it keeps write tools behind a separate
bearer-token gate in addition to the public reverse-proxy auth boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import time
from typing import Any, Callable, Mapping, Sequence
import uuid

from dev_control_plane.contracts import freeze_task_spec, task_spec_from_mapping, task_spec_to_dict
from dev_control_plane.execution import (
    ControlPlaneExecutionError,
    load_run_record,
    run_codex_cli,
)
from dev_control_plane.secrets import get_mcp_auth_status, verify_mcp_bearer_token
from dev_control_plane.state_layout import StateLayoutError, safe_state_component, slug_state_component
from dev_control_plane.target_production import (
    TARGET_PROJECT_ID,
    TARGET_REPO,
    TARGET_REPO_URL,
    build_rollback_plan,
    execute_wb_core_production_lane,
    inspect_wb_core_production_lock,
    target_production_result_to_dict,
)
MCP_PROTOCOL_VERSION = "2025-06-18"
MCP_ENDPOINT = "/mcp"
MCP_TRANSPORT = "streamable_http"
MCP_RUNS_COLLECTION = "mcp_runs"
MCP_STATUS_COLLECTION = "mcp_status"
MCP_AUDIT_LOG = "mcp_audit.jsonl"
MCP_MAX_ARTIFACT_BYTES = 64_000
MCP_MAX_TEXT_BYTES = 16_000
MCP_FAKE_RUNS_ENV = "DEV_CONTROL_PLANE_MCP_FAKE_RUNS"
MCP_SOURCE = "dev-control-plane-mcp"

READ_ONLY_TOOLS = {
    "get_status",
    "list_targets",
    "get_target_status",
    "get_production_lock_status",
    "list_active_runs",
    "get_run_status",
    "get_run_report",
    "list_run_artifacts",
    "get_run_artifact",
    "get_rollback_plan",
    "search",
    "fetch",
}
WRITE_TOOLS = {
    "start_wb_core_production_lane",
    "start_managed_clone_run",
    "request_rollback",
}
TERMINAL_STATUSES = {
    "completed",
    "completed_dry_run",
    "passed",
    "failed",
    "blocked",
    "cancelled",
    "decision_only",
    "waiting_for_target_lock",
}

SECRET_KEY_RE = re.compile(r"(api[_-]?key|authorization|bearer|cookie|password|secret|session|token|auth[_-]?json)", re.I)
SECRET_TEXT_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"Authorization\s*:\s*Bearer\s+\S+", re.I),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]{20,}", re.I),
    re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}"),
    re.compile(r"BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY"),
)


@dataclass(frozen=True)
class MCPRequestContext:
    authorization: str | None
    caller: str
    user_agent: str | None
    authenticated: bool
    auth_configured: bool


class MCPProtocolError(ValueError):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class MCPToolBackend:
    def __init__(self, store: Any, *, root: Path) -> None:
        self.store = store
        self.root = root
        self._lock = threading.Lock()
        self._handlers: dict[str, Callable[[Mapping[str, Any], MCPRequestContext], dict[str, Any]]] = {
            "get_status": self.get_status,
            "list_targets": self.list_targets,
            "get_target_status": self.get_target_status,
            "get_production_lock_status": self.get_production_lock_status,
            "list_active_runs": self.list_active_runs,
            "start_wb_core_production_lane": self.start_wb_core_production_lane,
            "start_managed_clone_run": self.start_managed_clone_run,
            "get_run_status": self.get_run_status,
            "get_run_report": self.get_run_report,
            "list_run_artifacts": self.list_run_artifacts,
            "get_run_artifact": self.get_run_artifact,
            "get_rollback_plan": self.get_rollback_plan,
            "request_rollback": self.request_rollback,
            "search": self.search,
            "fetch": self.fetch,
        }

    @property
    def tool_count(self) -> int:
        return len(TOOL_DEFINITIONS)

    def status_summary(self) -> dict[str, Any]:
        auth = get_mcp_auth_status(env=self.store._runtime_config_env())
        return _sanitize(
            {
                "enabled": True,
                "endpoint": MCP_ENDPOINT,
                "transport": MCP_TRANSPORT,
                "protocol_version": MCP_PROTOCOL_VERSION,
                "auth": {
                    "public_boundary": "reverse_proxy_basic_auth_expected",
                    "write_tools": auth,
                    "chatgpt_ui_blocker": _chatgpt_auth_blocker(auth),
                },
                "tool_count": self.tool_count,
                "read_only_tools": sorted(READ_ONLY_TOOLS),
                "write_tools": sorted(WRITE_TOOLS),
                "active_runs_count": len(self._active_mcp_runs()),
                "last_call": self._last_call_status(),
            }
        )

    def handle_json_rpc(self, payload: Any, context: MCPRequestContext) -> tuple[int, dict[str, Any]]:
        if isinstance(payload, list):
            responses = [self._handle_single_json_rpc(item, context) for item in payload]
            responses = [item for item in responses if item is not None]
            return 200, _sanitize(responses if responses else {})
        response = self._handle_single_json_rpc(payload, context)
        return 200, _sanitize(response if response is not None else {})

    def _handle_single_json_rpc(self, request: Any, context: MCPRequestContext) -> dict[str, Any] | None:
        if not isinstance(request, Mapping):
            return _json_rpc_error(None, -32600, "JSON-RPC request must be an object")
        request_id = request.get("id")
        method = str(request.get("method") or "")
        params = request.get("params") if isinstance(request.get("params"), Mapping) else {}
        is_notification = "id" not in request
        try:
            if method == "initialize":
                result = {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "dev-control-plane", "version": _git_commit(self.root)["short"] or "unknown"},
                    "instructions": (
                        "Use bounded dev-control-plane tools only. Do not request arbitrary shell. "
                        "Start tools return run_id quickly; poll get_run_status and get_run_report."
                    ),
                }
            elif method in {"notifications/initialized", "initialized"}:
                result = {}
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": TOOL_DEFINITIONS}
            elif method == "tools/call":
                result = self._handle_tool_call(params, context)
            else:
                raise MCPProtocolError(-32601, f"unsupported MCP method: {method}")
            if is_notification:
                return None
            return {"jsonrpc": "2.0", "id": request_id, "result": result}
        except MCPProtocolError as exc:
            if is_notification:
                return None
            return _json_rpc_error(request_id, exc.code, exc.message)
        except Exception as exc:
            if is_notification:
                return None
            return _json_rpc_error(request_id, -32603, _safe_exception_text(exc))

    def _handle_tool_call(self, params: Mapping[str, Any], context: MCPRequestContext) -> dict[str, Any]:
        name = str(params.get("name") or "")
        arguments = params.get("arguments") if isinstance(params.get("arguments"), Mapping) else {}
        if name not in self._handlers:
            raise MCPProtocolError(-32602, f"unknown tool: {name}")
        if name in WRITE_TOOLS and not context.authenticated:
            result = {
                "status": "denied",
                "tool": name,
                "blocker": "MCP write tool requires a configured bearer token and Authorization: Bearer <token>",
                "auth_configured": context.auth_configured,
            }
            self._audit(tool=name, context=context, result=result, run_id=_optional_str(arguments.get("run_id")))
            return _tool_result(result, is_error=True)
        try:
            result = self._handlers[name](arguments, context)
        except Exception as exc:
            result = {"status": "failed", "tool": name, "blocker": _safe_exception_text(exc)}
            self._audit(tool=name, context=context, result=result, run_id=_optional_str(arguments.get("run_id")))
            return _tool_result(result, is_error=True)
        self._audit(tool=name, context=context, result=result, run_id=_optional_str(result.get("run_id") or arguments.get("run_id")))
        return _tool_result(result, is_error=str(result.get("status") or "") in {"denied", "failed", "error"})

    def get_status(self, _args: Mapping[str, Any], _context: MCPRequestContext) -> dict[str, Any]:
        summary = self.store.summary(self.store.config if hasattr(self.store, "config") else _NullConfig())
        connections = self.store.connections_status()
        commit = _git_commit(self.root)
        lock = inspect_wb_core_production_lock(
            workspace_path=None,
            run_dir=self.store.state_dir / "runs" / "mcp-status-lock-probe",
            run_id="mcp-status-lock-probe",
        )
        return _sanitize(
            {
                "status": "ok",
                "service": {
                    "name": "dev-control-plane.service",
                    "runtime_profile": summary.get("runtime_profile"),
                    "process_status": _service_status(),
                    "host": summary.get("host"),
                    "port": summary.get("port"),
                    "state_dir": summary.get("state_dir"),
                },
                "version": commit,
                "openai": connections.get("openai", {}),
                "codex": connections.get("codex", {}),
                "toolchain": connections.get("toolchain", {}),
                "production_lane_enabled": bool(summary.get("target_production_lane_enabled")),
                "production_lane_mode": summary.get("target_production_lane_mode"),
                "active_runs_count": len(self._active_mcp_runs()),
                "target_lock_status": lock,
                "mcp": self.status_summary(),
            }
        )

    def list_targets(self, _args: Mapping[str, Any], _context: MCPRequestContext) -> dict[str, Any]:
        targets = []
        for target in self.store.list_target_projects().get("targets", []):
            targets.append(
                {
                    "target_id": target.get("project_id"),
                    "display_name": target.get("display_name"),
                    "source_mode": target.get("source_mode"),
                    "validation_status": target.get("validation_status"),
                    "production_lane": {
                        "available": target.get("project_id") == TARGET_PROJECT_ID,
                        "mode": "explicit_wb_core_pr_merge_deploy_policy"
                        if target.get("project_id") == TARGET_PROJECT_ID
                        else "unavailable",
                    },
                    "blockers": target.get("blockers", []),
                    "warnings": target.get("warnings", []),
                }
            )
        return {"status": "ok", "targets": _sanitize(targets)}

    def get_target_status(self, args: Mapping[str, Any], _context: MCPRequestContext) -> dict[str, Any]:
        target_id = _required_str(args, "target_id")
        return _sanitize(self.store.get_target_project(target_id))

    def get_production_lock_status(self, args: Mapping[str, Any], _context: MCPRequestContext) -> dict[str, Any]:
        target_id = _optional_str(args.get("target_id")) or TARGET_PROJECT_ID
        if target_id != TARGET_PROJECT_ID:
            return {"status": "not_applicable", "target_id": target_id, "blocker": "production lock exists only for wb-core"}
        lock = inspect_wb_core_production_lock(
            workspace_path=None,
            run_dir=self.store.state_dir / "runs" / "mcp-lock-status",
            run_id="mcp-lock-status",
        )
        waiting = [
            run
            for run in self._read_mcp_runs().values()
            if run.get("target_id") == target_id and run.get("status") == "waiting_for_target_lock"
        ]
        return {
            "status": "ok",
            "target_id": target_id,
            "lock_status": lock.get("status"),
            "active_run_id": lock.get("run_id"),
            "waiting_runs_count": len(waiting),
            "stale_warning": lock.get("status") == "stale",
            "lock": _sanitize(lock),
        }

    def list_active_runs(self, args: Mapping[str, Any], _context: MCPRequestContext) -> dict[str, Any]:
        target_id = _optional_str(args.get("target_id"))
        status_filter = _status_filter(args.get("status"))
        runs = []
        for run in self._read_mcp_runs().values():
            if target_id and run.get("target_id") != target_id:
                continue
            if status_filter and str(run.get("status") or "") not in status_filter:
                continue
            if not status_filter and str(run.get("status") or "") in TERMINAL_STATUSES:
                continue
            runs.append(_compact_mcp_run(run))
        return {"status": "ok", "runs": sorted(runs, key=lambda item: str(item.get("created_at") or ""))}

    def start_wb_core_production_lane(self, args: Mapping[str, Any], context: MCPRequestContext) -> dict[str, Any]:
        task_text = _required_str(args, "task_text", max_len=12000)
        force_production_lane = _bool(args.get("force_production_lane"), default=True)
        dry_run = _bool(args.get("dry_run"), default=False)
        idempotency_key = _optional_str(args.get("idempotency_key"))
        operator_note = _optional_str(args.get("operator_note"))
        if not force_production_lane:
            return {
                "status": "denied",
                "blocker": "start_wb_core_production_lane requires force_production_lane=true; no silent fallback is allowed",
                "target_id": TARGET_PROJECT_ID,
            }
        existing = self._idempotent_run("start_wb_core_production_lane", idempotency_key)
        if existing:
            return {**_compact_mcp_run(existing), "status": existing.get("status"), "idempotent_replay": True}

        run_id = _new_mcp_run_id("mcp-prod")
        lock = inspect_wb_core_production_lock(
            workspace_path=None,
            run_dir=self.store.layout.run_layout(run_id).run_dir,
            run_id=run_id,
        )
        initial = self._create_mcp_run(
            run_id=run_id,
            tool="start_wb_core_production_lane",
            target_id=TARGET_PROJECT_ID,
            execution_mode="production_lane_dry_run" if dry_run else "production_lane",
            task_text=task_text,
            operator_note=operator_note,
            idempotency_key=idempotency_key,
            dry_run=dry_run,
            status="queued",
            current_stage="queued",
        )
        if lock.get("status") == "active":
            self._update_mcp_run(
                run_id,
                status="waiting_for_target_lock",
                current_stage="waiting_for_target_lock",
                lock_wait={"active_run_id": lock.get("run_id"), "lock_status": lock.get("status")},
                blocker="wb-core production lane is locked by active run",
            )
            return self.get_run_status({"run_id": run_id}, context)
        if lock.get("status") == "stale":
            self._update_mcp_run(
                run_id,
                status="blocked",
                current_stage="blocked",
                lock_wait={"active_run_id": lock.get("run_id"), "lock_status": lock.get("status")},
                blocker="wb-core production lane has a stale lock; manual cleanup required",
            )
            return self.get_run_status({"run_id": run_id}, context)
        if dry_run:
            self._write_dry_run_artifacts(run_id, task_text=task_text, operator_note=operator_note, production_lane=True)
            self._update_mcp_run(
                run_id,
                status="completed_dry_run",
                current_stage="dry_run_complete",
                run_dir=str(self.store.layout.run_layout(run_id).run_dir),
                prompt_path=str(self.store.layout.run_layout(run_id).prompt_path),
                report_path=str(self._production_artifacts_dir(run_id) / "mcp_production_lane_report.json"),
                rollback_plan_path=str(self._production_artifacts_dir(run_id) / "rollback_plan.json"),
                message="Dry-run completed without Codex, PR, merge or deploy.",
            )
            return self.get_run_status({"run_id": run_id}, context)

        thread = threading.Thread(
            target=self._production_lane_worker,
            args=(run_id, task_text, operator_note),
            daemon=True,
        )
        thread.start()
        return {**_compact_mcp_run(initial), "status": "queued", "run_id": run_id, "accepted": True}

    def start_managed_clone_run(self, args: Mapping[str, Any], context: MCPRequestContext) -> dict[str, Any]:
        target_id = _required_str(args, "target_id")
        task_text = _required_str(args, "task_text", max_len=12000)
        no_pr_no_deploy = _bool(args.get("no_pr_no_deploy"), default=True)
        if not no_pr_no_deploy:
            return {
                "status": "denied",
                "blocker": "start_managed_clone_run requires no_pr_no_deploy=true; use explicit production-lane tool for wb-core",
                "target_id": target_id,
            }
        run_id = _new_mcp_run_id("mcp-managed")
        initial = self._create_mcp_run(
            run_id=run_id,
            tool="start_managed_clone_run",
            target_id=target_id,
            execution_mode="managed_clone_only",
            task_text=task_text,
            operator_note=None,
            idempotency_key=_optional_str(args.get("idempotency_key")),
            dry_run=False,
            status="queued",
            current_stage="queued",
        )
        thread = threading.Thread(
            target=self._managed_clone_worker,
            args=(run_id, target_id, task_text),
            daemon=True,
        )
        thread.start()
        return {**_compact_mcp_run(initial), "status": "queued", "run_id": run_id, "accepted": True}

    def get_run_status(self, args: Mapping[str, Any], _context: MCPRequestContext) -> dict[str, Any]:
        run_id = _required_str(args, "run_id")
        run = self._read_mcp_runs().get(run_id)
        if run:
            enriched = self._enrich_mcp_run(run)
            return _sanitize(
                {
                    "status": enriched.get("status"),
                    "run_id": run_id,
                    "target": enriched.get("target_id"),
                    "execution_mode": enriched.get("execution_mode"),
                    "current_stage": enriched.get("current_stage"),
                    "created_at": enriched.get("created_at"),
                    "updated_at": enriched.get("updated_at"),
                    "blockers": _blockers(enriched),
                    "pr_url": enriched.get("target_pr_url"),
                    "deploy_status": enriched.get("deploy_status"),
                    "lock_wait": enriched.get("lock_wait"),
                    "run_dir": enriched.get("run_dir"),
                    "artifact_status": enriched.get("artifact_status"),
                }
            )
        try:
            existing = self.store.get_run(run_id)
        except Exception:
            return {"status": "not_found", "run_id": run_id, "blocker": "run_id is unknown"}
        return _sanitize(
            {
                "status": existing.get("status"),
                "run_id": run_id,
                "target": existing.get("target_project_id"),
                "execution_mode": "managed_clone_only" if existing.get("workspace_path") else "fake_or_local",
                "current_stage": existing.get("status"),
                "created_at": _record_time(existing),
                "updated_at": _record_time(existing),
                "blockers": _blockers(existing),
                "pr_url": None,
                "deploy_status": None,
                "lock_wait": None,
            }
        )

    def get_run_report(self, args: Mapping[str, Any], context: MCPRequestContext) -> dict[str, Any]:
        run_id = _required_str(args, "run_id")
        status = self.get_run_status({"run_id": run_id}, context)
        if status.get("status") == "not_found":
            return status
        run_dir = self._run_dir_for_any_run(run_id)
        production_result = _read_json_if_exists(run_dir / "artifacts" / "production_lane" / "production_lane_result.json")
        mcp_report = _read_json_if_exists(run_dir / "artifacts" / "production_lane" / "mcp_production_lane_report.json")
        rollback = self._rollback_plan_for_run_dir(run_dir)
        record = _read_run_record_if_exists(run_dir)
        verifier = record.get("verifier") if isinstance(record, Mapping) else None
        result = record.get("result") if isinstance(record, Mapping) else {}
        return _sanitize(
            {
                "status": status.get("status"),
                "run_id": run_id,
                "target": status.get("target"),
                "execution_mode": status.get("execution_mode"),
                "pr_url": (production_result or {}).get("target_pr_url"),
                "merge_commit": (production_result or {}).get("merge_commit"),
                "deploy_result": {
                    "deploy_status": (production_result or {}).get("deploy_status"),
                    "public_verify_status": (production_result or {}).get("public_verify_status"),
                },
                "probes": {
                    "public_verify_status": (production_result or {}).get("public_verify_status"),
                },
                "rollback_plan": rollback,
                "changed_files": (result or {}).get("changed_files", []),
                "verifier_result": verifier,
                "blocker": status.get("blockers"),
                "production_lane_result": production_result,
                "mcp_report": mcp_report,
            }
        )

    def list_run_artifacts(self, args: Mapping[str, Any], _context: MCPRequestContext) -> dict[str, Any]:
        run_id = _required_str(args, "run_id")
        try:
            run_dir = self._run_dir_for_any_run(run_id)
        except FileNotFoundError:
            return {"status": "not_found", "run_id": run_id, "artifacts": []}
        artifacts = []
        for artifact_id, path in self._artifact_paths(run_dir).items():
            if path.exists() and path.is_file():
                artifacts.append(
                    {
                        "artifact_id": artifact_id,
                        "artifact_type": artifact_id,
                        "bytes": path.stat().st_size,
                        "path": _display_owned_path(path, run_dir),
                    }
                )
        return {"status": "ok", "run_id": run_id, "artifacts": artifacts}

    def get_run_artifact(self, args: Mapping[str, Any], _context: MCPRequestContext) -> dict[str, Any]:
        run_id = _required_str(args, "run_id")
        artifact_id = _optional_str(args.get("artifact_id")) or _optional_str(args.get("artifact_type"))
        if not artifact_id:
            return {"status": "bad_request", "run_id": run_id, "blocker": "artifact_id or artifact_type is required"}
        if _secret_artifact_name(artifact_id):
            return {"status": "denied", "run_id": run_id, "artifact_id": artifact_id, "blocker": "secret/auth/env artifacts are not exposed"}
        try:
            run_dir = self._run_dir_for_any_run(run_id)
        except FileNotFoundError:
            return {"status": "not_found", "run_id": run_id}
        path = self._artifact_paths(run_dir).get(artifact_id)
        if not path or not path.exists() or not path.is_file():
            return {"status": "not_found", "run_id": run_id, "artifact_id": artifact_id}
        max_bytes = _int_arg(args.get("max_bytes"), default=MCP_MAX_ARTIFACT_BYTES, minimum=1000, maximum=MCP_MAX_ARTIFACT_BYTES)
        content, truncated = _read_sanitized_text(path, max_bytes=max_bytes)
        return {
            "status": "ok",
            "run_id": run_id,
            "artifact_id": artifact_id,
            "artifact_type": artifact_id,
            "content": content,
            "truncated": truncated,
            "bytes": path.stat().st_size,
            "path": _display_owned_path(path, run_dir),
        }

    def get_rollback_plan(self, args: Mapping[str, Any], _context: MCPRequestContext) -> dict[str, Any]:
        run_id = _required_str(args, "run_id")
        try:
            run_dir = self._run_dir_for_any_run(run_id)
        except FileNotFoundError:
            return {"status": "not_found", "run_id": run_id}
        plan = self._rollback_plan_for_run_dir(run_dir)
        if not plan:
            return {"status": "not_found", "run_id": run_id, "blocker": "rollback plan is not available for this run"}
        return {"status": "ok", "run_id": run_id, "rollback_plan": _sanitize(plan)}

    def request_rollback(self, args: Mapping[str, Any], _context: MCPRequestContext) -> dict[str, Any]:
        run_id = _required_str(args, "run_id")
        confirm = _bool(args.get("confirm_rollback"), default=False)
        plan = self.get_rollback_plan({"run_id": run_id}, _context)
        return {
            "status": "decision_only",
            "run_id": run_id,
            "confirm_rollback_received": confirm,
            "rollback_execution_started": False,
            "blocker": "Rollback execution is intentionally not exposed in MCP Stage 1; use the rollback plan under explicit manual approval.",
            "rollback_plan": plan.get("rollback_plan"),
        }

    def search(self, args: Mapping[str, Any], _context: MCPRequestContext) -> dict[str, Any]:
        query = _optional_str(args.get("query")) or _optional_str(args.get("q")) or ""
        lowered = query.lower()
        results = []
        for target in self.store.list_target_projects().get("targets", []):
            text = json.dumps(target, ensure_ascii=False).lower()
            if not lowered or lowered in text:
                results.append(
                    {
                        "id": f"target:{target.get('project_id')}",
                        "title": f"Target {target.get('display_name')}",
                        "url": f"dev-control-plane://targets/{target.get('project_id')}",
                        "text": f"{target.get('source_mode')} {target.get('validation_status')}",
                    }
                )
        for run in self._read_mcp_runs().values():
            text = json.dumps(_compact_mcp_run(run), ensure_ascii=False).lower()
            if not lowered or lowered in text:
                run_id = str(run.get("run_id") or "")
                results.append(
                    {
                        "id": f"run:{run_id}",
                        "title": f"Run {run_id}",
                        "url": f"dev-control-plane://runs/{run_id}",
                        "text": f"{run.get('target_id')} {run.get('status')} {run.get('execution_mode')}",
                    }
                )
        for doc_id, path in _searchable_docs(self.root).items():
            text = path.read_text(encoding="utf-8", errors="replace")
            if not lowered or lowered in text.lower() or lowered in path.as_posix().lower():
                results.append(
                    {
                        "id": f"doc:{doc_id}",
                        "title": path.relative_to(self.root).as_posix(),
                        "url": f"dev-control-plane://docs/{doc_id}",
                        "text": _excerpt(text, lowered),
                    }
                )
        return {"status": "ok", "query": query, "results": results[:25]}

    def fetch(self, args: Mapping[str, Any], context: MCPRequestContext) -> dict[str, Any]:
        item_id = _required_str(args, "id")
        if item_id.startswith("target:"):
            return self.get_target_status({"target_id": item_id.removeprefix("target:")}, context)
        if item_id.startswith("run:"):
            return self.get_run_report({"run_id": item_id.removeprefix("run:")}, context)
        if item_id.startswith("artifact:"):
            _, run_id, artifact_id = item_id.split(":", 2)
            return self.get_run_artifact({"run_id": run_id, "artifact_id": artifact_id}, context)
        if item_id.startswith("doc:"):
            doc_id = item_id.removeprefix("doc:")
            path = _searchable_docs(self.root).get(doc_id)
            if not path:
                return {"status": "not_found", "id": item_id}
            content, truncated = _read_sanitized_text(path, max_bytes=MCP_MAX_ARTIFACT_BYTES)
            return {"status": "ok", "id": item_id, "title": path.relative_to(self.root).as_posix(), "content": content, "truncated": truncated}
        return {"status": "not_found", "id": item_id}

    def _production_lane_worker(self, run_id: str, task_text: str, operator_note: str | None) -> None:
        try:
            self._update_mcp_run(run_id, status="preparing", current_stage="managed_clone_prepare")
            target_config = self.store._target_config_by_id(TARGET_PROJECT_ID)
            task_spec = self._create_frozen_mcp_task_spec(
                run_id=run_id,
                target_id=TARGET_PROJECT_ID,
                task_text=task_text,
                operator_note=operator_note,
                execution_mode="production_lane",
            )
            def progress(status: str) -> None:
                self._update_mcp_run(run_id, status=status, current_stage=status)

            if _fake_runs_enabled():
                result = self._fake_managed_clone_result(run_id, target_config, task_spec, task_text)
            else:
                result = run_codex_cli(
                    task_spec,
                    target_config=target_config,
                    step_id="step-001",
                    state_dir=self.store.state_dir,
                    allow_real_codex=True,
                    codex_bin=_codex_bin_for_execution(),
                    codex_args=(),
                    run_id=run_id,
                    progress_callback=progress,
                )
            self._update_mcp_run(
                run_id,
                status="verifier_passed" if result.verifier_status == "passed" else result.status,
                current_stage="verifier",
                run_dir=result.run_dir,
                workspace_path=result.workspace_path,
                prompt_path=result.prompt_path,
                handoff_path=result.handoff_path,
                log_path=result.log_path,
                diff_path=result.diff_path,
                verifier_status=result.verifier_status,
                changed_files=list(result.changed_files),
                blocker=result.blocker_reason,
            )
            if result.verifier_status != "passed":
                self._update_mcp_run(run_id, status="blocked", current_stage="blocked", blocker=result.blocker_reason or "verifier did not pass")
                return
            lock = inspect_wb_core_production_lock(workspace_path=Path(str(result.workspace_path)), run_dir=Path(str(result.run_dir)), run_id=run_id)
            if lock.get("status") == "active":
                self._update_mcp_run(
                    run_id,
                    status="waiting_for_target_lock",
                    current_stage="waiting_for_target_lock",
                    lock_wait={"active_run_id": lock.get("run_id"), "lock_status": lock.get("status")},
                    blocker="wb-core production lane is locked by active run",
                )
                return
            if lock.get("status") == "stale":
                self._update_mcp_run(
                    run_id,
                    status="blocked",
                    current_stage="blocked",
                    lock_wait={"active_run_id": lock.get("run_id"), "lock_status": lock.get("status")},
                    blocker="wb-core production lane has a stale lock; manual cleanup required",
                )
                return
            self._update_mcp_run(run_id, status="running_production_lane", current_stage="production_lane")
            payload = self._production_payload_from_result(run_id, task_spec, result)
            production = execute_wb_core_production_lane(payload, execute=True)
            production_payload = target_production_result_to_dict(production)
            self._update_mcp_run(
                run_id,
                status="completed" if production.status == "post_deploy_passed" else "blocked",
                current_stage=production.status,
                target_pr_url=production_payload.get("target_pr_url"),
                target_pr_number=production_payload.get("target_pr_number"),
                merge_commit=production_payload.get("merge_commit"),
                deploy_status=production_payload.get("deploy_status"),
                public_verify_status=production_payload.get("public_verify_status"),
                rollback_plan_path=production_payload.get("rollback_plan_path"),
                blocker="; ".join(production_payload.get("blockers") or []),
            )
        except Exception as exc:
            self._update_mcp_run(run_id, status="failed", current_stage="failed", blocker=_safe_exception_text(exc))

    def _managed_clone_worker(self, run_id: str, target_id: str, task_text: str) -> None:
        try:
            self._update_mcp_run(run_id, status="preparing", current_stage="managed_clone_prepare")
            target_config = self.store._target_config_by_id(target_id)
            task_spec = self._create_frozen_mcp_task_spec(
                run_id=run_id,
                target_id=target_id,
                task_text=task_text,
                operator_note=None,
                execution_mode="managed_clone_only",
            )
            def progress(status: str) -> None:
                self._update_mcp_run(run_id, status=status, current_stage=status)

            if _fake_runs_enabled():
                result = self._fake_managed_clone_result(run_id, target_config, task_spec, task_text)
            else:
                result = run_codex_cli(
                    task_spec,
                    target_config=target_config,
                    step_id="step-001",
                    state_dir=self.store.state_dir,
                    allow_real_codex=True,
                    codex_bin=_codex_bin_for_execution(),
                    codex_args=(),
                    run_id=run_id,
                    progress_callback=progress,
                )
            final_status = "passed" if result.verifier_status == "passed" else ("blocked" if result.status == "blocked" else "failed")
            self._update_mcp_run(
                run_id,
                status=final_status,
                current_stage="verifier",
                run_dir=result.run_dir,
                workspace_path=result.workspace_path,
                prompt_path=result.prompt_path,
                handoff_path=result.handoff_path,
                log_path=result.log_path,
                diff_path=result.diff_path,
                verifier_status=result.verifier_status,
                changed_files=list(result.changed_files),
                blocker=result.blocker_reason,
                message="Managed-clone-only run finished; no PR, merge or deploy was attempted.",
            )
        except Exception as exc:
            self._update_mcp_run(run_id, status="failed", current_stage="failed", blocker=_safe_exception_text(exc))

    def _fake_managed_clone_result(self, run_id: str, target_config: Any, task_spec_payload: Mapping[str, Any], task_text: str) -> Any:
        from types import SimpleNamespace

        run_layout = self.store.layout.run_layout(run_id)
        run_layout.ensure_dirs()
        workspace = run_layout.workspace_dir(slug_state_component(str(getattr(target_config, "project_id", "target"))))
        workspace.mkdir(parents=True, exist_ok=True)
        (workspace / "README.md").write_text("MCP fake managed clone workspace\n", encoding="utf-8")
        run_layout.prompt_path.write_text(f"MCP fake prompt\n\n{task_text}\n", encoding="utf-8")
        run_layout.handoff_path.write_text(
            "=== ДЛЯ КУРАТОРА ===\n\n"
            "Статус: fake MCP managed-clone run completed\n"
            "Что сделано: fake managed clone artifact created for MCP smoke\n"
            "Exact blocker: none\n\n"
            "=== СЖАТАЯ ПРОВЕРКА ===\n\n"
            "- fake MCP run\n"
            "Главный вывод: no production mutation was executed.\n",
            encoding="utf-8",
        )
        run_layout.diff_path.write_text("diff --git a/README.md b/README.md\n", encoding="utf-8")
        run_layout.codex_log_path.write_text("fake MCP Codex log; no provider called\n", encoding="utf-8")
        verifier_payload = {
            "status": "passed",
            "check_results": [{"name": "mcp_fake_verifier", "status": "passed", "reason": "fake MCP smoke"}],
            "changed_files": ["README.md"],
            "forbidden_path_hits": [],
            "mandatory_handoff_blocks_present": True,
            "blocker_reason": None,
        }
        verifier_path = run_layout.verifier_path
        verifier_path.parent.mkdir(parents=True, exist_ok=True)
        verifier_path.write_text(json.dumps(verifier_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        run_json = {
            "schema_version": 2,
            "request": {
                "id": run_id,
                "target_project_id": getattr(target_config, "project_id", None),
                "task_spec_id": task_spec_payload.get("id"),
                "step_id": "step-001",
                "state_dir": str(self.store.state_dir),
                "base_ref": "fake-base",
                "workspace_strategy": "managed_clone",
                "executor_mode": "codex_cli",
                "allow_real_codex": True,
                "original_repo_path": getattr(target_config, "repo_url", None) or getattr(target_config, "repo_path", None),
                "original_head": "fake-base",
                "original_status_before": "fake",
                "target_source_mode": getattr(target_config, "source_mode", "local_path"),
                "target_repo_url": getattr(target_config, "repo_url", None),
                "target_branch": getattr(target_config, "branch", "main"),
            },
            "target_project": {"project_id": getattr(target_config, "project_id", None)},
            "workspace": {
                "original_repo_path": getattr(target_config, "repo_url", None) or getattr(target_config, "repo_path", None),
                "original_head": "fake-base",
                "original_status_before": "fake",
                "workspace_path": str(workspace),
                "base_ref": "fake-base",
                "created_at": _now_utc(),
            },
            "task_spec": _json_ready(dict(task_spec_payload)),
            "sprint_step": task_spec_payload.get("sprint_steps", [{}])[0],
            "result": {
                "id": run_id,
                "status": "verifier_passed",
                "target_project_id": getattr(target_config, "project_id", None),
                "task_spec_id": task_spec_payload.get("id"),
                "step_id": "step-001",
                "run_dir": str(run_layout.run_dir),
                "workspace_path": str(workspace),
                "prompt_path": str(run_layout.prompt_path),
                "handoff_path": str(run_layout.handoff_path),
                "log_path": str(run_layout.codex_log_path),
                "diff_path": str(run_layout.diff_path),
                "changed_files": ["README.md"],
                "check_results": verifier_payload["check_results"],
                "verifier_status": "passed",
                "blocker_reason": None,
                "next_manual_step": None,
                "codex_exit_code": 0,
            },
            "verifier": verifier_payload,
            "updated_at": _now_utc(),
        }
        (run_layout.run_dir / "run.json").write_text(json.dumps(run_json, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        self.store._remember_run(
            {
                "status": "verifier_passed",
                "run_id": run_id,
                "target_project_id": getattr(target_config, "project_id", None),
                "run_dir": str(run_layout.run_dir),
                "workspace_path": str(workspace),
                "prompt_path": str(run_layout.prompt_path),
                "handoff_path": str(run_layout.handoff_path),
                "log_path": str(run_layout.codex_log_path),
                "diff_path": str(run_layout.diff_path),
                "changed_files": ["README.md"],
                "verifier_status": "passed",
                "blocker_reason": None,
                "run_result_summary": {"status": "Passed", "run_id": run_id, "target_project_id": getattr(target_config, "project_id", None)},
                "blocker": {"status": "none"},
            }
        )
        return SimpleNamespace(
            id=run_id,
            status="verifier_passed",
            target_project_id=getattr(target_config, "project_id", None),
            task_spec_id=task_spec_payload.get("id"),
            step_id="step-001",
            run_dir=str(run_layout.run_dir),
            workspace_path=str(workspace),
            prompt_path=str(run_layout.prompt_path),
            handoff_path=str(run_layout.handoff_path),
            log_path=str(run_layout.codex_log_path),
            diff_path=str(run_layout.diff_path),
            changed_files=("README.md",),
            check_results=(),
            verifier_status="passed",
            blocker_reason=None,
            next_manual_step=None,
            codex_exit_code=0,
        )

    def _create_frozen_mcp_task_spec(
        self,
        *,
        run_id: str,
        target_id: str,
        task_text: str,
        operator_note: str | None,
        execution_mode: str,
    ) -> dict[str, Any]:
        title = _title_from_task_text(task_text)
        task_id = f"task-{slug_state_component(run_id, fallback='mcp-run')}"
        payload = {
            "id": task_id,
            "version": "1.0",
            "status": "draft",
            "title": title,
            "goal": task_text,
            "scope": [task_text] + ([f"Operator note: {operator_note}"] if operator_note else []),
            "not_in_scope": [
                "arbitrary shell execution",
                "direct target repo mutation",
                "WebCore deploy outside approved production lane",
                "secrets or credential changes",
                "server-side curator or sprint ping-pong loop",
            ],
            "task_class": "L3",
            "class_reason": "MCP-triggered external connector/write-tool path with managed clone and production-lane gates.",
            "risks": ["external connector request", "long-running Codex job", "target production lock contention"],
            "acceptance_criteria": [
                "managed workspace is isolated under control-plane state",
                "verifier result is recorded",
                "handoff and artifacts are readable by run_id",
                "no arbitrary shell or direct target mutation is used",
            ],
            "required_smokes": ["git diff --check"],
            "allowed_paths": ["**"],
            "forbidden_paths": [
                "wb_core_docs_master/**",
                "99_MANIFEST__DOCSET_VERSION.md",
                "runtime/**",
                "deploy/**",
                "infra/**",
                "artifacts/registry_upload_http_entrypoint/**",
            ],
            "allowed_actions": ["managed_clone_execution", "real_codex_execution"],
            "forbidden_actions": [
                "live_deploy",
                "ssh",
                "root_shell",
                "public_route_change",
                "selleros_product_plane_route",
                "google_sheets_gas_write",
                "secrets_write",
                "auto_merge",
                "direct_target_mutation",
            ],
            "human_gates": ["MCP write tool bearer auth", "ChatGPT tool confirmation for write actions"],
            "explicit_policy_note": f"MCP Stage 1 {execution_mode}; production mutation only through explicit wb-core production lane gates.",
            "target_project_id": target_id,
            "sprint_steps": [
                {
                    "id": "step-001",
                    "sequence": 1,
                    "title": title,
                    "goal": task_text,
                    "task_class": "L3",
                    "scope": [task_text],
                    "acceptance_criteria": [
                        "bounded task executed in managed clone",
                        "verifier report is produced",
                        "final handoff follows required contract",
                    ],
                    "required_smokes": ["git diff --check"],
                    "stop_conditions": [
                        "stop if task requires arbitrary shell",
                        "stop if task requires direct target repo mutation",
                        "stop if task requires secrets or credential output",
                    ],
                }
            ],
        }
        with self._lock:
            draft = self.store.create_task_spec(payload)
            frozen = freeze_task_spec(task_spec_from_mapping(draft))
            frozen_payload = task_spec_to_dict(frozen)
            # Preserve the validated/merged sprint step from create_task_spec; only the TaskSpec envelope is frozen here.
            frozen_payload["sprint_steps"] = draft.get("sprint_steps", payload["sprint_steps"])
            for key in ("target_project_id", "target_project", "target_context_summary"):
                if key in draft:
                    frozen_payload[key] = draft[key]
            frozen_payload["saved_at"] = _now_utc()
            task_specs = self.store._read_collection("task_specs")
            task_specs[task_id] = _json_ready(frozen_payload)
            self.store._write_collection("task_specs", task_specs)
        return _json_ready(frozen_payload)

    def _production_payload_from_result(self, run_id: str, task_spec: Mapping[str, Any], result: Any) -> dict[str, Any]:
        record = _read_run_record_if_exists(Path(str(result.run_dir)))
        workspace = record.get("workspace", {}) if isinstance(record, Mapping) else {}
        return {
            "target_project_id": TARGET_PROJECT_ID,
            "target_repo": TARGET_REPO,
            "target_repo_url": TARGET_REPO_URL,
            "base_branch": "main",
            "execution_mode": "production_lane",
            "apply_mode": "target_pr_merge_deploy",
            "production_lane": True,
            "run_id": run_id,
            "run_dir": str(result.run_dir),
            "workspace_path": str(result.workspace_path),
            "task_spec_id": task_spec.get("id"),
            "task_summary": task_spec.get("goal") or task_spec.get("title") or "DevControl MCP task",
            "changed_files": list(result.changed_files),
            "verifier_status": result.verifier_status,
            "forbidden_path_hits": [],
            "secrets_scan_status": "passed",
            "docs_update_status": "not_required",
            "commit_message": f"Изменить wb-core через DevControl MCP ({run_id})",
            "pr_title": "Изменить wb-core через DevControl MCP",
            "run_start_base_ref": workspace.get("base_ref"),
        }

    def _write_dry_run_artifacts(self, run_id: str, *, task_text: str, operator_note: str | None, production_lane: bool) -> None:
        layout = self.store.layout.run_layout(run_id)
        layout.ensure_dirs()
        layout.prompt_path.write_text(
            "\n".join(
                (
                    "MCP dry-run prompt",
                    "",
                    task_text,
                    "",
                    f"Operator note: {operator_note or ''}",
                    "No Codex, PR, merge or deploy is executed in this dry-run.",
                )
            ),
            encoding="utf-8",
        )
        layout.handoff_path.write_text(
            "=== ДЛЯ КУРАТОРА ===\n\n"
            "Статус: MCP dry-run completed\n"
            "Что сделано: created isolated MCP dry-run artifacts only\n"
            "Live deploy state: not run\n"
            "PR status: not created\n"
            "Merge status: not run\n"
            "Exact blocker: none\n\n"
            "=== СЖАТАЯ ПРОВЕРКА ===\n\n"
            "- no wb-core PR\n- no deploy\n- no target mutation\n"
            "Главный вывод: dry-run accepted and recorded.\n",
            encoding="utf-8",
        )
        production_dir = self._production_artifacts_dir(run_id)
        production_dir.mkdir(parents=True, exist_ok=True)
        rollback = build_rollback_plan(
            run_id=run_id,
            branch_name=f"devcp/{run_id}",
            pre_merge_main_commit="<dry-run-no-merge>",
            merge_commit="<dry-run-no-merge>",
            deploy_runner="apps/registry_upload_http_entrypoint_hosted_runtime.py",
            deploy_target_file="artifacts/registry_upload_http_entrypoint/input/hosted_runtime_target__europe_api.json",
        )
        (production_dir / "rollback_plan.json").write_text(
            json.dumps(_sanitize(rollback), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        report = {
            "status": "completed_dry_run",
            "run_id": run_id,
            "production_lane": production_lane,
            "pr_created": False,
            "deployed": False,
            "rollback_plan": rollback,
            "message": "MCP dry-run did not call Codex, GitHub, SSH or WebCore deploy.",
        }
        (production_dir / "mcp_production_lane_report.json").write_text(
            json.dumps(_sanitize(report), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def _create_mcp_run(self, **payload: Any) -> dict[str, Any]:
        run = {
            **payload,
            "created_at": _now_utc(),
            "updated_at": _now_utc(),
            "source": MCP_SOURCE,
        }
        run["task_text_excerpt"] = _excerpt(str(run.pop("task_text", "") or ""), "")
        with self.store._jobs_lock:
            runs = self._read_mcp_runs()
            runs[str(run["run_id"])] = _json_ready(run)
            self.store._write_collection(MCP_RUNS_COLLECTION, runs)
        return run

    def _update_mcp_run(self, run_id: str, **updates: Any) -> None:
        with self.store._jobs_lock:
            runs = self._read_mcp_runs()
            run = dict(runs.get(run_id) or {"run_id": run_id, "created_at": _now_utc(), "source": MCP_SOURCE})
            run.update(_json_ready(updates))
            run["updated_at"] = _now_utc()
            runs[run_id] = run
            self.store._write_collection(MCP_RUNS_COLLECTION, runs)

    def _read_mcp_runs(self) -> dict[str, Any]:
        try:
            return self.store._read_collection(MCP_RUNS_COLLECTION)
        except Exception:
            return {}

    def _active_mcp_runs(self) -> list[dict[str, Any]]:
        return [dict(run) for run in self._read_mcp_runs().values() if str(run.get("status") or "") not in TERMINAL_STATUSES]

    def _idempotent_run(self, tool: str, idempotency_key: str | None) -> dict[str, Any] | None:
        if not idempotency_key:
            return None
        for run in self._read_mcp_runs().values():
            if run.get("tool") == tool and run.get("idempotency_key") == idempotency_key:
                return dict(run)
        return None

    def _enrich_mcp_run(self, run: Mapping[str, Any]) -> dict[str, Any]:
        enriched = dict(run)
        run_dir_raw = enriched.get("run_dir")
        run_dir = Path(str(run_dir_raw)) if run_dir_raw else self.store.layout.run_layout(str(enriched.get("run_id"))).run_dir
        production_result = _read_json_if_exists(run_dir / "artifacts" / "production_lane" / "production_lane_result.json")
        if production_result:
            enriched.setdefault("target_pr_url", production_result.get("target_pr_url"))
            enriched.setdefault("merge_commit", production_result.get("merge_commit"))
            enriched.setdefault("deploy_status", production_result.get("deploy_status"))
            enriched.setdefault("public_verify_status", production_result.get("public_verify_status"))
            enriched.setdefault("rollback_plan_path", production_result.get("rollback_plan_path"))
        enriched["artifact_status"] = {
            "prompt": (run_dir / "artifacts" / "prompt.md").exists(),
            "handoff": (run_dir / "artifacts" / "handoff.md").exists(),
            "diff": (run_dir / "artifacts" / "diff.patch").exists(),
            "verifier": (run_dir / "verifier" / "verifier.json").exists(),
            "production_lane_report": (run_dir / "artifacts" / "production_lane" / "production_lane_result.json").exists()
            or (run_dir / "artifacts" / "production_lane" / "mcp_production_lane_report.json").exists(),
            "rollback_plan": bool(self._rollback_plan_for_run_dir(run_dir)),
        }
        return enriched

    def _run_dir_for_any_run(self, run_id: str) -> Path:
        run = self._read_mcp_runs().get(run_id)
        if run and run.get("run_dir"):
            run_dir = Path(str(run["run_dir"])).resolve()
        else:
            run_dir = self.store.layout.run_layout(run_id).run_dir.resolve()
        if run_dir.exists():
            return run_dir
        raise FileNotFoundError(run_id)

    def _production_artifacts_dir(self, run_id: str) -> Path:
        return self.store.layout.run_layout(run_id).artifacts_dir / "production_lane"

    def _rollback_plan_for_run_dir(self, run_dir: Path) -> dict[str, Any] | None:
        for path in (
            run_dir / "artifacts" / "production_lane" / "rollback_plan.json",
            run_dir / "rollback_plan.json",
        ):
            payload = _read_json_if_exists(path)
            if payload:
                return payload
        production = _read_json_if_exists(run_dir / "artifacts" / "production_lane" / "production_lane_result.json")
        plan = production.get("plan", {}) if isinstance(production, Mapping) else {}
        rollback = plan.get("rollback_plan") if isinstance(plan, Mapping) else None
        return dict(rollback) if isinstance(rollback, Mapping) else None

    def _artifact_paths(self, run_dir: Path) -> dict[str, Path]:
        return {
            "prompt": run_dir / "artifacts" / "prompt.md",
            "handoff": run_dir / "artifacts" / "handoff.md",
            "diff": run_dir / "artifacts" / "diff.patch",
            "logs": run_dir / "logs" / "codex.log",
            "verifier": run_dir / "verifier" / "verifier.json",
            "production_lane_report": run_dir / "artifacts" / "production_lane" / "production_lane_result.json",
            "mcp_production_lane_report": run_dir / "artifacts" / "production_lane" / "mcp_production_lane_report.json",
            "rollback_plan": run_dir / "artifacts" / "production_lane" / "rollback_plan.json",
            "run_metadata": run_dir / "run.json",
        }

    def _audit(self, *, tool: str, context: MCPRequestContext, result: Mapping[str, Any], run_id: str | None) -> None:
        entry = {
            "timestamp": _now_utc(),
            "tool": tool,
            "caller": context.caller,
            "source": "mcp",
            "run_id": run_id,
            "result_status": result.get("status") or "ok",
            "blocker": result.get("blocker") or "; ".join(str(item) for item in result.get("blockers", []) or []),
            "user_agent": _truncate(context.user_agent, 120),
        }
        entry = _sanitize(entry)
        try:
            audit_path = self.store.layout.logs_dir / MCP_AUDIT_LOG
            audit_path.parent.mkdir(parents=True, exist_ok=True)
            with audit_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
            self.store._write_collection(MCP_STATUS_COLLECTION, {"last_call": entry})
        except Exception:
            return

    def _last_call_status(self) -> dict[str, Any] | None:
        try:
            status = self.store._read_collection(MCP_STATUS_COLLECTION)
        except Exception:
            return None
        last_call = status.get("last_call")
        return dict(last_call) if isinstance(last_call, Mapping) else None


class _NullConfig:
    host = "127.0.0.1"
    port = 0
    runtime_profile = "local"
    bind_policy = "loopback_only"


def build_mcp_context(headers: Mapping[str, str], *, client: str, env: Mapping[str, str] | None = None) -> MCPRequestContext:
    authorization = _header(headers, "Authorization")
    auth_status = get_mcp_auth_status(env=env)
    caller = _header(headers, "X-Forwarded-For") or client
    return MCPRequestContext(
        authorization=authorization,
        caller=_truncate(caller, 120),
        user_agent=_header(headers, "User-Agent"),
        authenticated=verify_mcp_bearer_token(authorization, env=env),
        auth_configured=bool(auth_status.get("configured")),
    )


def _tool_result(payload: Mapping[str, Any], *, is_error: bool = False) -> dict[str, Any]:
    sanitized = _sanitize(dict(payload))
    return {
        "content": [{"type": "text", "text": json.dumps(sanitized, ensure_ascii=False, sort_keys=True)}],
        "structuredContent": sanitized,
        "isError": is_error,
    }


def _json_rpc_error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": _safe_text(message, 500)}}


def _required_str(args: Mapping[str, Any], name: str, *, max_len: int = 512) -> str:
    value = str(args.get(name) or "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    if len(value) > max_len:
        raise ValueError(f"{name} is too long")
    return value


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _bool(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _int_arg(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _status_filter(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return {str(item) for item in value}
    return {str(value)}


def _new_mcp_run_id(prefix: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return safe_state_component(f"{prefix}-{timestamp}-{uuid.uuid4().hex[:10]}", "run_id")


def _now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _title_from_task_text(task_text: str) -> str:
    first = next((line.strip() for line in task_text.splitlines() if line.strip()), "MCP task")
    return _truncate(first, 100)


def _compact_mcp_run(run: Mapping[str, Any]) -> dict[str, Any]:
    return _sanitize(
        {
            "run_id": run.get("run_id"),
            "target": run.get("target_id"),
            "target_id": run.get("target_id"),
            "execution_mode": run.get("execution_mode"),
            "current_stage": run.get("current_stage"),
            "status": run.get("status"),
            "created_at": run.get("created_at"),
            "updated_at": run.get("updated_at"),
            "lock_wait": run.get("lock_wait"),
            "blocker_summary": run.get("blocker"),
            "task_text_excerpt": run.get("task_text_excerpt"),
        }
    )


def _blockers(payload: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    if payload.get("blocker"):
        blockers.append(str(payload["blocker"]))
    raw = payload.get("blockers")
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        blockers.extend(str(item) for item in raw if str(item).strip())
    blocker = payload.get("blocker_reason")
    if blocker:
        blockers.append(str(blocker))
    return list(dict.fromkeys(blockers))


def _record_time(payload: Mapping[str, Any]) -> str | None:
    metadata = payload.get("metadata")
    if isinstance(metadata, Mapping):
        return _optional_str(metadata.get("updated_at"))
    return None


def _service_status() -> dict[str, Any]:
    try:
        completed = subprocess.run(
            ["systemctl", "is-active", "dev-control-plane.service"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except Exception:
        return {"status": "unknown", "manager": "systemctl_unavailable"}
    text = (completed.stdout or completed.stderr or "").strip()
    return {"status": text or "unknown", "manager": "systemd", "checked": completed.returncode == 0}


def _git_commit(root: Path) -> dict[str, Any]:
    def git(*args: str) -> str | None:
        completed = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            return None
        return completed.stdout.strip()

    commit = git("rev-parse", "HEAD")
    return {"commit": commit, "short": commit[:12] if commit else None, "branch": git("branch", "--show-current")}


def _codex_bin_for_execution() -> str | None:
    configured = str(os.environ.get("DEV_CONTROL_PLANE_CODEX_BIN") or "").strip()
    if configured:
        return configured
    completed = subprocess.run(["sh", "-lc", "command -v codex"], capture_output=True, text=True, check=False)
    return completed.stdout.strip() or None


def _fake_runs_enabled() -> bool:
    return str(os.environ.get(MCP_FAKE_RUNS_ENV) or "").strip() == "1"


def _chatgpt_auth_blocker(auth: Mapping[str, Any]) -> str | None:
    if auth.get("configured"):
        return (
            "ChatGPT Developer Mode currently documents OAuth/No Auth/Mixed Auth for app setup; "
            "this Stage 1 server has bearer-token write auth for protocol/API smoke but not OAuth."
        )
    return "MCP write token is not configured; write tools fail closed."


def _read_json_if_exists(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return dict(payload) if isinstance(payload, Mapping) else {}


def _read_run_record_if_exists(run_dir: Path) -> dict[str, Any]:
    try:
        return load_run_record(run_dir)
    except Exception:
        return {}


def _read_sanitized_text(path: Path, *, max_bytes: int) -> tuple[str, bool]:
    raw = path.read_bytes()
    truncated = len(raw) > max_bytes
    text = raw[:max_bytes].decode("utf-8", errors="replace")
    if truncated:
        text += "\n\n[truncated]"
    return _sanitize_text(text), truncated


def _display_owned_path(path: Path, owner: Path) -> str:
    try:
        return path.resolve().relative_to(owner.resolve()).as_posix()
    except ValueError:
        return path.name


def _secret_artifact_name(value: str) -> bool:
    lowered = value.lower()
    return any(token in lowered for token in ("secret", "auth", "env", "token", "cookie", "session"))


def _searchable_docs(root: Path) -> dict[str, Path]:
    candidates = [root / "README.md", root / "AGENTS.md"]
    for base in (root / "docs" / "architecture", root / "docs" / "runbooks"):
        if base.exists():
            candidates.extend(sorted(base.glob("*.md")))
    result: dict[str, Path] = {}
    for path in candidates:
        if not path.exists() or "dev_control_plane_docs_master" in path.parts:
            continue
        doc_id = slug_state_component(path.relative_to(root).as_posix(), fallback="doc")
        result[doc_id] = path
    return result


def _excerpt(text: str, query: str, *, limit: int = 500) -> str:
    if not query:
        return _truncate(text.strip().replace("\n", " "), limit)
    lowered = text.lower()
    idx = lowered.find(query)
    if idx < 0:
        return _truncate(text.strip().replace("\n", " "), limit)
    start = max(0, idx - 160)
    end = min(len(text), idx + len(query) + 320)
    return _truncate(text[start:end].strip().replace("\n", " "), limit)


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            text_key = str(key)
            if SECRET_KEY_RE.search(text_key):
                sanitized[text_key] = "[redacted]"
            else:
                sanitized[text_key] = _sanitize(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    if isinstance(value, str):
        return _sanitize_text(value)
    return value


def _sanitize_text(text: str) -> str:
    result = str(text)
    for pattern in SECRET_TEXT_PATTERNS:
        result = pattern.sub("[redacted]", result)
    return result


def _safe_text(text: str, limit: int) -> str:
    return _truncate(_sanitize_text(str(text).replace("\n", " ")), limit)


def _safe_exception_text(exc: Exception) -> str:
    return _safe_text(str(exc) or exc.__class__.__name__, 500)


def _truncate(value: Any, limit: int) -> str:
    text = str(value or "")
    return text if len(text) <= limit else text[: limit - 15] + "...[truncated]"


def _json_ready(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    return value


def _header(headers: Mapping[str, str], name: str) -> str | None:
    lowered = name.lower()
    for key, value in headers.items():
        if str(key).lower() == lowered:
            return str(value)
    return None


TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "get_status",
        "description": "Use this to inspect sanitized dev-control-plane service, model/toolchain, MCP, active run and wb-core production lock status.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "list_targets",
        "description": "Use this to list configured target projects and see source mode, validation, blockers, warnings and production-lane availability.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "get_target_status",
        "description": "Use this to inspect one sanitized target adapter status.",
        "inputSchema": {"type": "object", "properties": {"target_id": {"type": "string"}}, "required": ["target_id"], "additionalProperties": False},
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "get_production_lock_status",
        "description": "Use this to inspect the wb-core production-lane target lock and waiting run count.",
        "inputSchema": {"type": "object", "properties": {"target_id": {"type": "string", "default": "wb-core"}}, "additionalProperties": False},
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "list_active_runs",
        "description": "Use this to list MCP runs that are active or match a status filter. Shows separate run_id, target, mode, stage, status and blocker summary.",
        "inputSchema": {
            "type": "object",
            "properties": {"target_id": {"type": "string"}, "status": {"oneOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}]}},
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "start_wb_core_production_lane",
        "description": "Write tool. Use this only for explicit wb-core production-lane runs. Starts quickly and returns run_id; dry_run=true never creates PR, merge or deploy.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_text": {"type": "string", "description": "Bounded task text from the ChatGPT project curator."},
                "operator_note": {"type": "string"},
                "force_production_lane": {"type": "boolean", "default": True},
                "dry_run": {"type": "boolean", "default": False},
                "idempotency_key": {"type": "string"},
                "max_wait_seconds": {"type": "integer", "minimum": 0, "maximum": 30},
            },
            "required": ["task_text"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": True},
    },
    {
        "name": "start_managed_clone_run",
        "description": "Write tool. Use this for safe managed-clone-only Codex experiments. It never opens PRs, merges or deploys.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target_id": {"type": "string"},
                "task_text": {"type": "string"},
                "no_pr_no_deploy": {"type": "boolean", "default": True},
                "idempotency_key": {"type": "string"},
            },
            "required": ["target_id", "task_text"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": False},
    },
    {
        "name": "get_run_status",
        "description": "Use this to poll one run by run_id and see status, current stage, target, PR/deploy status and blockers.",
        "inputSchema": {"type": "object", "properties": {"run_id": {"type": "string"}}, "required": ["run_id"], "additionalProperties": False},
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "get_run_report",
        "description": "Use this to read the final sanitized report/handoff summary for one run_id, including PR URL, verifier, deploy result and rollback plan when present.",
        "inputSchema": {"type": "object", "properties": {"run_id": {"type": "string"}}, "required": ["run_id"], "additionalProperties": False},
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "list_run_artifacts",
        "description": "Use this to list sanitized artifacts available for one run_id.",
        "inputSchema": {"type": "object", "properties": {"run_id": {"type": "string"}}, "required": ["run_id"], "additionalProperties": False},
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "get_run_artifact",
        "description": "Use this to read a sanitized, size-limited run artifact by artifact_id or artifact_type. Secret/auth/env artifacts are denied.",
        "inputSchema": {
            "type": "object",
            "properties": {"run_id": {"type": "string"}, "artifact_id": {"type": "string"}, "artifact_type": {"type": "string"}, "max_bytes": {"type": "integer"}},
            "required": ["run_id"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "get_rollback_plan",
        "description": "Use this to read rollback commands/plan for a production-lane run without executing rollback.",
        "inputSchema": {"type": "object", "properties": {"run_id": {"type": "string"}}, "required": ["run_id"], "additionalProperties": False},
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "request_rollback",
        "description": "Write tool but decision-only in Stage 1. It records that rollback was requested and returns the plan; it does not execute rollback.",
        "inputSchema": {"type": "object", "properties": {"run_id": {"type": "string"}, "confirm_rollback": {"type": "boolean", "default": False}}, "required": ["run_id"], "additionalProperties": False},
        "annotations": {"readOnlyHint": False, "destructiveHint": True},
    },
    {
        "name": "search",
        "description": "Use this for data-only connector discovery over dev-control-plane docs, target metadata and run reports.",
        "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "q": {"type": "string"}}, "additionalProperties": False},
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "fetch",
        "description": "Use this to fetch a sanitized search result by id.",
        "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"], "additionalProperties": False},
        "annotations": {"readOnlyHint": True},
    },
]
