"""Bounded MCP adapter for hosted Development Control Plane.

The adapter intentionally exposes a small JSON-RPC MCP surface only. Public
ChatGPT Developer Mode discovery is read-only/no-auth; write tools are hidden
from unauthenticated tool discovery and remain gated by server-side auth.
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
from dev_control_plane.codex_observability import codex_observability_status, codex_run_reconciliation
from dev_control_plane.execution import (
    ControlPlaneExecutionError,
    load_run_record,
    run_codex_cli,
)
from dev_control_plane.live_monitor import (
    append_live_event,
    append_terminal_output,
    live_url,
    read_live_timeline,
    read_terminal_tail,
    sanitize_terminal_text,
)
from dev_control_plane.mcp_oauth import MCP_WRITE_SCOPE, bearer_token_from_header, external_base_url
from dev_control_plane.operator_lifecycle import decorate_operator_lifecycle
from dev_control_plane.secrets import get_mcp_auth_status, verify_mcp_bearer_token
from dev_control_plane.state_layout import StateLayoutError, safe_state_component, slug_state_component
from dev_control_plane.target_docs import (
    TARGET_DOC_TOOL_NAMES,
    build_target_docs_readiness,
    get_target_doc as read_target_doc,
    list_target_docs as read_target_docs_list,
    search_target_docs as read_target_docs_search,
)
from dev_control_plane.target_projects import load_target_project_configs
from dev_control_plane.target_production import (
    TARGET_PROJECT_ID,
    TARGET_REPO,
    TARGET_REPO_URL,
    build_rollback_plan,
    execute_wb_core_resume_deploy,
    execute_wb_core_production_lane,
    inspect_wb_core_production_lock,
    target_production_resume_result_to_dict,
    target_production_result_to_dict,
)
MCP_PROTOCOL_VERSION = "2025-06-18"
MCP_ENDPOINT = "/mcp"
MCP_TRANSPORT = "streamable_http"
MCP_CHATGPT_AUTH_STRATEGY = "mixed_noauth_read_oauth_write"
MCP_RUNS_COLLECTION = "mcp_runs"
MCP_STATUS_COLLECTION = "mcp_status"
MCP_AUDIT_LOG = "mcp_audit.jsonl"
WB_CORE_AUTO_INTENTS_COLLECTION = "wb_core_auto_production_intents"
MCP_MAX_ARTIFACT_BYTES = 64_000
MCP_MAX_TEXT_BYTES = 16_000
MCP_FAKE_RUNS_ENV = "DEV_CONTROL_PLANE_MCP_FAKE_RUNS"
MCP_SOURCE = "dev-control-plane-mcp"
SPRINT_BRIDGE_MARKER = "DEVCONTROL_START_SPRINT_V1"
SPRINT_FROZEN_BLOCKER = "start_sprint is frozen for operator flow; use direct wb-core auto Codex task"
SPRINT_INTERNAL_ENABLE_ENV = "DEV_CONTROL_PLANE_ENABLE_FROZEN_SPRINT_INTERNAL"

TOOL_AUTH_PUBLIC_NOAUTH = "public_noauth"
TOOL_AUTH_OAUTH_REQUIRED = "oauth_required"
TOOL_KIND_READ = "read"
TOOL_KIND_WRITE = "write"

MCP_TOOL_REGISTRY: dict[str, dict[str, Any]] = {
    "get_status": {"auth_policy": TOOL_AUTH_PUBLIC_NOAUTH, "kind": TOOL_KIND_READ, "public_visible": True, "scopes": ()},
    "list_targets": {"auth_policy": TOOL_AUTH_PUBLIC_NOAUTH, "kind": TOOL_KIND_READ, "public_visible": True, "scopes": ()},
    "get_target_status": {"auth_policy": TOOL_AUTH_PUBLIC_NOAUTH, "kind": TOOL_KIND_READ, "public_visible": True, "scopes": ()},
    "get_production_lock_status": {"auth_policy": TOOL_AUTH_PUBLIC_NOAUTH, "kind": TOOL_KIND_READ, "public_visible": True, "scopes": ()},
    "list_active_runs": {"auth_policy": TOOL_AUTH_PUBLIC_NOAUTH, "kind": TOOL_KIND_READ, "public_visible": True, "scopes": ()},
    "get_run_status": {"auth_policy": TOOL_AUTH_PUBLIC_NOAUTH, "kind": TOOL_KIND_READ, "public_visible": True, "scopes": ()},
    "get_run_report": {"auth_policy": TOOL_AUTH_PUBLIC_NOAUTH, "kind": TOOL_KIND_READ, "public_visible": True, "scopes": ()},
    "list_run_artifacts": {"auth_policy": TOOL_AUTH_PUBLIC_NOAUTH, "kind": TOOL_KIND_READ, "public_visible": True, "scopes": ()},
    "get_run_artifact": {"auth_policy": TOOL_AUTH_PUBLIC_NOAUTH, "kind": TOOL_KIND_READ, "public_visible": True, "scopes": ()},
    "get_run_timeline": {"auth_policy": TOOL_AUTH_PUBLIC_NOAUTH, "kind": TOOL_KIND_READ, "public_visible": True, "scopes": ()},
    "get_run_log_tail": {"auth_policy": TOOL_AUTH_PUBLIC_NOAUTH, "kind": TOOL_KIND_READ, "public_visible": True, "scopes": ()},
    "get_rollback_plan": {"auth_policy": TOOL_AUTH_PUBLIC_NOAUTH, "kind": TOOL_KIND_READ, "public_visible": True, "scopes": ()},
    "search": {"auth_policy": TOOL_AUTH_PUBLIC_NOAUTH, "kind": TOOL_KIND_READ, "public_visible": True, "scopes": ()},
    "fetch": {"auth_policy": TOOL_AUTH_PUBLIC_NOAUTH, "kind": TOOL_KIND_READ, "public_visible": True, "scopes": ()},
    "list_parallel_tasks": {"auth_policy": TOOL_AUTH_PUBLIC_NOAUTH, "kind": TOOL_KIND_READ, "public_visible": True, "scopes": ()},
    "get_parallel_task": {"auth_policy": TOOL_AUTH_PUBLIC_NOAUTH, "kind": TOOL_KIND_READ, "public_visible": True, "scopes": ()},
    "get_target_promotion_state": {"auth_policy": TOOL_AUTH_PUBLIC_NOAUTH, "kind": TOOL_KIND_READ, "public_visible": True, "scopes": ()},
    "list_parallel_candidates": {"auth_policy": TOOL_AUTH_PUBLIC_NOAUTH, "kind": TOOL_KIND_READ, "public_visible": True, "scopes": ()},
    "list_target_docs": {"auth_policy": TOOL_AUTH_OAUTH_REQUIRED, "kind": TOOL_KIND_READ, "public_visible": False, "scopes": (MCP_WRITE_SCOPE,)},
    "search_target_docs": {"auth_policy": TOOL_AUTH_OAUTH_REQUIRED, "kind": TOOL_KIND_READ, "public_visible": False, "scopes": (MCP_WRITE_SCOPE,)},
    "get_target_doc": {"auth_policy": TOOL_AUTH_OAUTH_REQUIRED, "kind": TOOL_KIND_READ, "public_visible": False, "scopes": (MCP_WRITE_SCOPE,)},
    "read_target_docs": {"auth_policy": TOOL_AUTH_OAUTH_REQUIRED, "kind": TOOL_KIND_READ, "public_visible": False, "scopes": (MCP_WRITE_SCOPE,)},
    "start_wb_core_auto_task": {"auth_policy": TOOL_AUTH_OAUTH_REQUIRED, "kind": TOOL_KIND_WRITE, "public_visible": False, "scopes": (MCP_WRITE_SCOPE,)},
    "start_wb_core_production_lane": {"auth_policy": TOOL_AUTH_OAUTH_REQUIRED, "kind": TOOL_KIND_WRITE, "public_visible": False, "scopes": (MCP_WRITE_SCOPE,)},
    "start_managed_clone_run": {"auth_policy": TOOL_AUTH_OAUTH_REQUIRED, "kind": TOOL_KIND_WRITE, "public_visible": False, "scopes": (MCP_WRITE_SCOPE,)},
    "submit_parallel_task": {"auth_policy": TOOL_AUTH_OAUTH_REQUIRED, "kind": TOOL_KIND_WRITE, "public_visible": False, "scopes": (MCP_WRITE_SCOPE,)},
    "start_parallel_task_execution": {"auth_policy": TOOL_AUTH_OAUTH_REQUIRED, "kind": TOOL_KIND_WRITE, "public_visible": False, "scopes": (MCP_WRITE_SCOPE,)},
    "reconcile_parallel_task": {"auth_policy": TOOL_AUTH_OAUTH_REQUIRED, "kind": TOOL_KIND_WRITE, "public_visible": False, "scopes": (MCP_WRITE_SCOPE,)},
    "promote_parallel_task": {"auth_policy": TOOL_AUTH_OAUTH_REQUIRED, "kind": TOOL_KIND_WRITE, "public_visible": False, "scopes": (MCP_WRITE_SCOPE,)},
    "promote_next_parallel_candidate": {"auth_policy": TOOL_AUTH_OAUTH_REQUIRED, "kind": TOOL_KIND_WRITE, "public_visible": False, "scopes": (MCP_WRITE_SCOPE,)},
    "promote_parallel_selection": {"auth_policy": TOOL_AUTH_OAUTH_REQUIRED, "kind": TOOL_KIND_WRITE, "public_visible": False, "scopes": (MCP_WRITE_SCOPE,)},
    "refresh_selected_candidate": {"auth_policy": TOOL_AUTH_OAUTH_REQUIRED, "kind": TOOL_KIND_WRITE, "public_visible": False, "scopes": (MCP_WRITE_SCOPE,)},
    "start_sprint": {
        "auth_policy": TOOL_AUTH_OAUTH_REQUIRED,
        "kind": TOOL_KIND_WRITE,
        "public_visible": False,
        "scopes": (MCP_WRITE_SCOPE,),
        "operator_visible": False,
        "frozen": True,
    },
    "resume_wb_core_production_deploy": {"auth_policy": TOOL_AUTH_OAUTH_REQUIRED, "kind": TOOL_KIND_WRITE, "public_visible": False, "scopes": (MCP_WRITE_SCOPE,)},
    "request_rollback": {"auth_policy": TOOL_AUTH_OAUTH_REQUIRED, "kind": TOOL_KIND_WRITE, "public_visible": False, "scopes": (MCP_WRITE_SCOPE,)},
}
READ_ONLY_TOOLS = frozenset(name for name, policy in MCP_TOOL_REGISTRY.items() if policy["auth_policy"] == TOOL_AUTH_PUBLIC_NOAUTH and policy["kind"] == TOOL_KIND_READ)
AUTHENTICATED_READ_TOOLS = frozenset(name for name, policy in MCP_TOOL_REGISTRY.items() if policy["auth_policy"] == TOOL_AUTH_OAUTH_REQUIRED and policy["kind"] == TOOL_KIND_READ)
WRITE_TOOLS = frozenset(name for name, policy in MCP_TOOL_REGISTRY.items() if policy["auth_policy"] == TOOL_AUTH_OAUTH_REQUIRED and policy["kind"] == TOOL_KIND_WRITE)
OAUTH_REQUIRED_TOOLS = AUTHENTICATED_READ_TOOLS | WRITE_TOOLS
TERMINAL_STATUSES = {
    "blocked_by_conflict",
    "blocked_by_operator",
    "completed",
    "completed_dry_run",
    "conflict_detected",
    "blocked",
    "cancelled",
    "decision_only",
    "denied",
    "expired",
    "failed",
    "needs_rework",
    "needs_verifier_after_control_error",
    "partial_group_blocked",
    "partial_group_complete_with_blockers",
    "passed",
    "partially_deployed",
    "post_deploy_passed",
    "production_complete",
    "ready_for_separate_deploy",
    "refresh_required",
    "resume_dry_run_ready",
    "waiting_for_target_lock",
    "stale_lost_process",
    "stale_timeout",
}

NOAUTH_SECURITY_SCHEMES = [{"type": "noauth"}]
WRITE_SECURITY_SCHEMES = [{"type": "oauth2", "scopes": [MCP_WRITE_SCOPE]}]
AUTHENTICATED_READ_SECURITY_SCHEMES = [{"type": "oauth2", "scopes": [MCP_WRITE_SCOPE]}]
WRITE_AUTH_MARKER = {
    "required": True,
    "chatgpt_ready": True,
    "implemented_mode": "oauth2_authorization_code_pkce",
    "scope": MCP_WRITE_SCOPE,
    "legacy_bearer_mode": "protocol_smoke_only",
}
AUTHENTICATED_READ_AUTH_MARKER = {
    "required": True,
    "chatgpt_ready": True,
    "implemented_mode": "oauth2_authorization_code_pkce",
    "scope": MCP_WRITE_SCOPE,
    "read_only": True,
    "legacy_bearer_mode": "protocol_smoke_only",
}

SECRET_KEY_RE = re.compile(r"(api[_-]?key|authorization|bearer|cookie|password|secret|session|token|auth[_-]?json)", re.I)
SECRET_TEXT_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"Authorization\s*:\s*Bearer\s+\S+", re.I),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]{20,}", re.I),
    re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY"),
    re.compile(r"/opt/dev-control-plane-runtime/(?:secrets|\\.codex)/[^\s:]+"),
    re.compile(r"(?i)(identity file\s+)[^\s]+"),
)


@dataclass(frozen=True)
class MCPRequestContext:
    authorization: str | None
    caller: str
    user_agent: str | None
    authenticated: bool
    auth_configured: bool
    auth_type: str | None = None
    auth_scopes: tuple[str, ...] = ()
    base_url: str | None = None
    auth_failure_code: str | None = None
    auth_failure_reason: str | None = None


class MCPProtocolError(ValueError):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class MCPToolBackend:
    def __init__(self, store: Any, *, root: Path, oauth_provider: Any | None = None) -> None:
        self.store = store
        self.root = root
        self.oauth_provider = oauth_provider
        self._lock = threading.Lock()
        handlers: dict[str, Callable[[Mapping[str, Any], MCPRequestContext], dict[str, Any]]] = {
            "get_status": self.get_status,
            "list_targets": self.list_targets,
            "get_target_status": self.get_target_status,
            "get_production_lock_status": self.get_production_lock_status,
            "list_active_runs": self.list_active_runs,
            "start_wb_core_production_lane": self.start_wb_core_production_lane,
            "start_managed_clone_run": self.start_managed_clone_run,
            "submit_parallel_task": self.submit_parallel_task,
            "start_parallel_task_execution": self.start_parallel_task_execution,
            "reconcile_parallel_task": self.reconcile_parallel_task,
            "promote_parallel_task": self.promote_parallel_task,
            "promote_next_parallel_candidate": self.promote_next_parallel_candidate,
            "promote_parallel_selection": self.promote_parallel_selection,
            "refresh_selected_candidate": self.refresh_selected_candidate,
            "start_sprint": self.start_sprint,
            "resume_wb_core_production_deploy": self.resume_wb_core_production_deploy,
            "get_run_status": self.get_run_status,
            "get_run_report": self.get_run_report,
            "list_run_artifacts": self.list_run_artifacts,
            "get_run_artifact": self.get_run_artifact,
            "get_run_timeline": self.get_run_timeline,
            "get_run_log_tail": self.get_run_log_tail,
            "get_rollback_plan": self.get_rollback_plan,
            "request_rollback": self.request_rollback,
            "start_wb_core_auto_task": self.start_wb_core_auto_task,
            "list_target_docs": self.list_target_docs,
            "search_target_docs": self.search_target_docs,
            "get_target_doc": self.get_target_doc,
            "read_target_docs": self.read_target_docs,
            "list_parallel_tasks": self.list_parallel_tasks,
            "get_parallel_task": self.get_parallel_task,
            "get_target_promotion_state": self.get_target_promotion_state,
            "list_parallel_candidates": self.list_parallel_candidates,
            "search": self.search,
            "fetch": self.fetch,
        }
        missing_handlers = sorted(set(MCP_TOOL_REGISTRY) - set(handlers))
        if missing_handlers:
            raise RuntimeError(f"MCP tool registry missing handlers: {', '.join(missing_handlers)}")
        self._handlers = {name: handlers[name] for name in MCP_TOOL_REGISTRY}

    @property
    def tool_count(self) -> int:
        return len(_tool_names())

    @property
    def public_tool_count(self) -> int:
        return len(_tool_names(public=True))

    def status_summary(self, *, public: bool = False) -> dict[str, Any]:
        legacy_auth = get_mcp_auth_status(env=self.store._runtime_config_env())
        public_origin = str(os.environ.get("DEV_CONTROL_PLANE_PUBLIC_ORIGIN") or "https://devcontrol.pro").rstrip("/")
        oauth = self.oauth_provider.status(public_origin) if self.oauth_provider is not None else {"enabled": False}
        return _sanitize(
            {
                "enabled": True,
                "endpoint": MCP_ENDPOINT,
                "transport": MCP_TRANSPORT,
                "protocol_version": MCP_PROTOCOL_VERSION,
                "chatgpt_auth_strategy": MCP_CHATGPT_AUTH_STRATEGY,
                "chatgpt_read_tools_ready": True,
                "chatgpt_authenticated_read_tools_ready": bool(oauth.get("enabled")),
                "chatgpt_write_tools_ready": bool(oauth.get("enabled")),
                "auth": {
                    "public_boundary": "main_ui_basic_auth_with_mcp_read_only_noauth_exception",
                    "write_tools": {
                        "auth_mode": "oauth2_authorization_code_pkce",
                        "configured": bool(oauth.get("enabled")),
                        "scope": MCP_WRITE_SCOPE,
                        "authorize_url": oauth.get("authorize_url"),
                        "exchange_url": oauth.get("exchange_url"),
                        "register_url": oauth.get("register_url"),
                        "resource_metadata_url": oauth.get("resource_metadata_url"),
                        "authorize_user_gate": oauth.get("authorize_user_gate"),
                        "legacy_protocol_gate_configured": bool(legacy_auth.get("configured")),
                    },
                    "oauth": oauth,
                    "chatgpt_ui_blocker": _chatgpt_auth_blocker(oauth),
                    "reconnect_diagnostics": {
                        "sanitized": True,
                        "durable_storage": (oauth.get("storage") or {}).get("mode"),
                        "restart_survives_registered_clients": bool((oauth.get("storage") or {}).get("restart_survives")),
                        "reason_codes": (oauth.get("auth_failure_diagnostics") or {}).get("supported_reason_codes", []),
                        "external_connector_cache_limitation": (oauth.get("auth_failure_diagnostics") or {}).get("external_connector_cache_limitation"),
                    },
                },
                "tool_count": self.tool_count,
                "public_tool_count": self.public_tool_count,
                "exported_tools": sorted(_tool_names(public=public)),
                "read_only_tools": sorted(_tool_names(auth_policy=TOOL_AUTH_PUBLIC_NOAUTH, kind=TOOL_KIND_READ)),
                "authenticated_read_tools": [] if public else sorted(_tool_names(auth_policy=TOOL_AUTH_OAUTH_REQUIRED, kind=TOOL_KIND_READ)),
                "target_docs_readiness": self._target_docs_readiness(),
                "parallel_task_ledger": self.store.parallel_ledger_status()
                if hasattr(self.store, "parallel_ledger_status")
                else {"status": "unavailable"},
                "write_tools": [] if public else sorted(_tool_names(auth_policy=TOOL_AUTH_OAUTH_REQUIRED, kind=TOOL_KIND_WRITE)),
                "write_tools_hidden": public,
                "authenticated_read_tools_hidden": public,
                "tool_registry": _tool_registry_status(public=public),
                "public_discovery": {
                    "mode": "no_auth_read_only",
                    "write_tools_visible_without_auth": False,
                    "target_docs_tools_visible_without_auth": False,
                    "target_docs_tools_direct_call_status": "denied",
                    "write_tools_direct_call_status": "denied",
                },
                "authenticated_discovery": {
                    "target_docs_tools_visible_with_oauth": bool(oauth.get("enabled")),
                    "write_tools_visible_with_oauth": bool(oauth.get("enabled")),
                    "required_scope": MCP_WRITE_SCOPE,
                },
                "sprint_compatibility_bridge": {
                    "status": "frozen",
                    "canonical_tool": "start_sprint",
                    "bridge_tool": "start_managed_clone_run",
                    "marker": SPRINT_BRIDGE_MARKER,
                    "auth": "oauth_dcp_write_required",
                    "target_id": TARGET_PROJECT_ID,
                    "execution_mode": "managed_clone_only",
                    "no_pr_no_deploy_required": True,
                    "production_lane_allowed": False,
                    "operator_visible": False,
                    "blocker": SPRINT_FROZEN_BLOCKER,
                },
                "parallel_task_intake": {
                    "status": "ready",
                    "storage": "state/collections/parallel_task_ledger.json",
                    "submit_tool": "submit_parallel_task",
                    "execution_tool": "start_parallel_task_execution",
                    "reconcile_tool": "reconcile_parallel_task",
                    "promotion_tools": ["promote_parallel_task", "promote_next_parallel_candidate", "promote_parallel_selection", "refresh_selected_candidate"],
                    "selected_promotion_tool": "promote_parallel_selection",
                    "read_tools": ["list_parallel_tasks", "get_parallel_task", "list_parallel_candidates", "get_target_promotion_state"],
                    "operator_dashboard": "/",
                    "submit_auth": "oauth_dcp_write_required",
                    "execution_started_on_submit": False,
                    "default_execution_mode": "fake_state_only",
                    "guarded_real_managed_clone_mode": "disabled_without_runtime_flag_and_confirm",
                    "ping_pong_enabled": False,
                    "start_sprint_used": False,
                    "real_production_lane_default": False,
                    "real_production_bridge_default": "disabled",
                    "production_lane_started_on_submit": False,
                },
                "wb_core_auto_task_arbitration": {
                    "status": "ready",
                    "tool": "start_wb_core_auto_task",
                    "storage": f"state/collections/{WB_CORE_AUTO_INTENTS_COLLECTION}.json",
                    "default_route": "direct-production-capable-or-blocker",
                    "fallback_to_sprint": False,
                    "fallback_to_managed_clone_only": False,
                    "exclusive_route": "wb_core_exclusive_auto_production",
                    "blocked_route": "wb_core_direct_auto_blocked",
                    "decision_owner": "server_atomic_state",
                    "chatgpt_decides_exclusivity": False,
                    "production_lane": "existing_wb_core_pr_merge_deploy_policy",
                    "deferred_auto_promote": False,
                },
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
                        "Use bounded dev-control-plane read-only tools from ChatGPT Developer Mode. "
                        "Write tools require OAuth authorization with dcp.write scope and are hidden from public no-auth discovery. "
                        "Do not request arbitrary shell."
                    ),
                }
            elif method in {"notifications/initialized", "initialized"}:
                result = {}
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": self._tool_definitions_for_context(context)}
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
        policy = MCP_TOOL_REGISTRY.get(name)
        if not policy or name not in self._handlers:
            raise MCPProtocolError(-32602, f"unknown tool: {name}")
        if policy["auth_policy"] == TOOL_AUTH_OAUTH_REQUIRED and not context.authenticated:
            base_url = context.base_url or "https://devcontrol.pro"
            authenticate = self.oauth_provider.www_authenticate(base_url) if self.oauth_provider is not None else None
            is_read_only = policy["kind"] == TOOL_KIND_READ
            failure_code = context.auth_failure_code or "unauthenticated_call"
            failure_reason = context.auth_failure_reason or "OAuth bearer token is missing; authenticate with dcp.write."
            result = {
                "status": "denied",
                "tool": name,
                "blocker": (
                    "MCP authenticated read tools require OAuth authorization with dcp.write scope; public no-auth discovery hides them."
                    if is_read_only
                    else "MCP write tools require OAuth authorization with dcp.write scope."
                ),
                "auth_configured": context.auth_configured,
                "auth_failure_code": failure_code,
                "auth_failure_reason": failure_reason,
                "_mcp_meta": {"mcp/www_authenticate": authenticate} if authenticate else {},
            }
            if is_read_only:
                result["chatgpt_authenticated_read_tools_ready"] = self.oauth_provider is not None
            else:
                result["chatgpt_write_tools_ready"] = self.oauth_provider is not None
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

    def _tool_definitions_for_context(self, context: MCPRequestContext) -> list[dict[str, Any]]:
        if context.authenticated:
            names = set(_tool_names(include_internal=_sprint_internal_runtime_enabled()))
            return [tool for tool in TOOL_DEFINITIONS if str(tool.get("name") or "") in names]
        public_names = _tool_names(public=True)
        return [tool for tool in TOOL_DEFINITIONS if str(tool.get("name") or "") in public_names]

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
                "codex_runtime_parity": connections.get("codex_runtime_parity", {}),
                "codex_observability": codex_observability_status(env=self.store._runtime_config_env()),
                "github": connections.get("github", {}),
                "ssh_deploy": connections.get("ssh_deploy", {}),
                "toolchain": connections.get("toolchain", {}),
                "production_lane_enabled": bool(summary.get("target_production_lane_enabled")),
                "production_lane_mode": summary.get("target_production_lane_mode"),
                "active_runs_count": len(self._active_mcp_runs()),
                "target_lock_status": lock,
                "mcp": self.status_summary(public=not _context.authenticated),
                "parallel_task_ledger": self.store.parallel_ledger_status()
                if hasattr(self.store, "parallel_ledger_status")
                else {"status": "unavailable"},
                "mcp_auth_context": {
                    "authenticated": _context.authenticated,
                    "auth_type": _context.auth_type,
                    "scopes": list(_context.auth_scopes),
                    "auth_failure_code": None if _context.authenticated else _context.auth_failure_code,
                    "auth_failure_reason": None if _context.authenticated else _context.auth_failure_reason,
                    "authenticated_read_tools_visible": _context.authenticated,
                    "write_tools_visible": _context.authenticated,
                },
                "target_docs_readiness": self._target_docs_readiness(),
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
        seen: set[str] = set()
        for run in self._read_mcp_runs().values():
            enriched = self._apply_promotion_group_child_override(self._enrich_mcp_run(run))
            if target_id and enriched.get("target_id") != target_id:
                continue
            if status_filter and str(enriched.get("status") or "") not in status_filter and str(enriched.get("effective_status") or "") not in status_filter:
                continue
            if not status_filter and str(enriched.get("status") or "") in TERMINAL_STATUSES and enriched.get("effective_activity") != "running":
                continue
            runs.append(_compact_mcp_run(enriched))
            seen.add(str(enriched.get("run_id") or ""))
        for job_id, raw_job in self.store._read_collection("real_runs").items():
            if not isinstance(raw_job, Mapping):
                continue
            enriched = self._real_job_live_summary(str(raw_job.get("id") or job_id))
            if not enriched:
                continue
            run_key = str(enriched.get("run_id") or "")
            if run_key in seen:
                continue
            if target_id and enriched.get("target_id") != target_id:
                continue
            if status_filter and str(enriched.get("status") or "") not in status_filter and str(enriched.get("effective_status") or "") not in status_filter:
                continue
            if not status_filter and str(enriched.get("status") or "") in TERMINAL_STATUSES and enriched.get("effective_activity") != "running":
                continue
            runs.append(_compact_mcp_run(enriched))
            seen.add(run_key)
        return {"status": "ok", "runs": sorted(runs, key=lambda item: str(item.get("effective_recency_at") or item.get("updated_at") or item.get("created_at") or ""), reverse=True)}

    def submit_parallel_task(self, args: Mapping[str, Any], context: MCPRequestContext) -> dict[str, Any]:
        payload = dict(args)
        payload.setdefault("source", MCP_SOURCE)
        payload.setdefault("source_tool", "mcp")
        if context.user_agent and not payload.get("source_id"):
            payload["source_id"] = _safe_text(context.user_agent, 160)
        result = self.store.submit_parallel_task(payload)
        result["tool"] = "submit_parallel_task"
        result["accepted"] = True
        result["execution_started"] = False
        result["codex_started"] = False
        result["production_lane_started"] = False
        result["ping_pong_started"] = False
        return _sanitize(result)

    def start_parallel_task_execution(self, args: Mapping[str, Any], _context: MCPRequestContext) -> dict[str, Any]:
        task_id = _required_str(args, "task_id")
        return _sanitize(
            self.store.start_parallel_task_execution(
                task_id,
                {
                    "starter_mode": _optional_str(args.get("starter_mode")) or _optional_str(args.get("execution_mode")) or "fake",
                    "execution_mode": _optional_str(args.get("execution_mode")),
                    "confirm_real_managed_clone": _bool(args.get("confirm_real_managed_clone"), default=False),
                    "task_spec_id": _optional_str(args.get("task_spec_id")),
                    "run_id": _optional_str(args.get("run_id")),
                },
            )
        )

    def reconcile_parallel_task(self, args: Mapping[str, Any], _context: MCPRequestContext) -> dict[str, Any]:
        task_id = _required_str(args, "task_id")
        payload = {
            "run_status": _optional_str(args.get("run_status")),
            "run_id": _optional_str(args.get("run_id")),
            "real_job_id": _optional_str(args.get("real_job_id")),
            "verifier_status": _optional_str(args.get("verifier_status")),
            "changed_files": args.get("changed_files") if isinstance(args.get("changed_files"), (list, tuple)) else [],
            "verifier_summary": args.get("verifier_summary") if isinstance(args.get("verifier_summary"), Mapping) else {},
            "blocker": _optional_str(args.get("blocker")),
        }
        return _sanitize(self.store.reconcile_parallel_task(task_id, payload))

    def promote_parallel_task(self, args: Mapping[str, Any], _context: MCPRequestContext) -> dict[str, Any]:
        task_id = _required_str(args, "task_id")
        return _sanitize(
            self.store.promote_parallel_task(
                task_id,
                {
                    "allow_auto_first_promotion": _bool(args.get("allow_auto_first_promotion"), default=False),
                    "allow_real_production_promotion": _bool(args.get("allow_real_production_promotion"), default=False),
                    "mode": _optional_str(args.get("mode")) or "dry_run",
                },
            )
        )

    def promote_next_parallel_candidate(self, args: Mapping[str, Any], _context: MCPRequestContext) -> dict[str, Any]:
        target_id = _required_str(args, "target_id")
        return _sanitize(
            self.store.promote_next_parallel_candidate(
                target_id,
                {
                    "promotion_epoch": _optional_str(args.get("promotion_epoch")),
                    "allow_auto_first_promotion": _bool(args.get("allow_auto_first_promotion"), default=False),
                    "allow_real_production_promotion": _bool(args.get("allow_real_production_promotion"), default=False),
                    "mode": _optional_str(args.get("mode")) or "dry_run",
                },
            )
        )

    def promote_parallel_selection(self, args: Mapping[str, Any], _context: MCPRequestContext) -> dict[str, Any]:
        target_id = _required_str(args, "target_id")
        selected_ids = args.get("selected_ids") if isinstance(args.get("selected_ids"), (list, tuple)) else []
        payload = {
            "target_id": target_id,
            "selected_ids": [str(item) for item in selected_ids],
            "selection_type": _optional_str(args.get("selection_type")) or "auto",
            "mode": _optional_str(args.get("mode")) or "auto_order",
            "confirm_merge_deploy": _bool(args.get("confirm_merge_deploy"), default=False),
            "allow_refresh": _bool(args.get("allow_refresh"), default=False),
            "dry_run": _bool(args.get("dry_run"), default=False),
            "plan_only": _bool(args.get("plan_only"), default=False),
            "operator_note": _optional_str(args.get("operator_note")),
            "idempotency_key": _optional_str(args.get("idempotency_key")),
            "allow_auto_first_promotion": _bool(args.get("allow_auto_first_promotion"), default=False),
            "allow_real_production_promotion": _bool(args.get("allow_real_production_promotion"), default=False),
        }
        return _sanitize(self.store.promote_parallel_selection(payload))

    def refresh_selected_candidate(self, args: Mapping[str, Any], _context: MCPRequestContext) -> dict[str, Any]:
        target_id = _required_str(args, "target_id")
        payload = {
            "target_id": target_id,
            "source_run_id": _optional_str(args.get("source_run_id")),
            "candidate_id": _optional_str(args.get("candidate_id")),
            "selected_id": _optional_str(args.get("selected_id")),
            "selection_type": _optional_str(args.get("selection_type")) or "auto",
            "group_id": _optional_str(args.get("group_id")),
            "conflict_reason": _optional_str(args.get("conflict_reason")),
            "conflict_files": [str(item) for item in args.get("conflict_files", [])] if isinstance(args.get("conflict_files"), (list, tuple)) else [],
            "mode": _optional_str(args.get("mode")) or "managed_clone_only",
            "confirm_start": _bool(args.get("confirm_start"), default=False),
            "start_managed_run": _bool(args.get("start_managed_run"), default=False),
            "source_chat": _optional_str(args.get("source_chat")),
            "submitted_by": _optional_str(args.get("submitted_by")),
            "release_group": _optional_str(args.get("release_group")),
            "idempotency_key": _optional_str(args.get("idempotency_key")),
        }
        return _sanitize(self.store.refresh_selected_candidate(payload))

    def list_parallel_tasks(self, args: Mapping[str, Any], _context: MCPRequestContext) -> dict[str, Any]:
        return _sanitize(
            self.store.list_parallel_tasks(
                target_id=_optional_str(args.get("target_id")),
                promotion_epoch=_optional_str(args.get("promotion_epoch")),
                status=_optional_str(args.get("status")),
            )
        )

    def get_parallel_task(self, args: Mapping[str, Any], _context: MCPRequestContext) -> dict[str, Any]:
        task_id = _required_str(args, "task_id")
        return _sanitize(self.store.get_parallel_task(task_id))

    def get_target_promotion_state(self, args: Mapping[str, Any], _context: MCPRequestContext) -> dict[str, Any]:
        target_id = _required_str(args, "target_id")
        return _sanitize(
            self.store.get_target_promotion_state(
                target_id,
                promotion_epoch=_optional_str(args.get("promotion_epoch")),
            )
        )

    def list_parallel_candidates(self, args: Mapping[str, Any], _context: MCPRequestContext) -> dict[str, Any]:
        return _sanitize(
            self.store.list_parallel_candidates(
                target_id=_optional_str(args.get("target_id")),
                promotion_epoch=_optional_str(args.get("promotion_epoch")),
            )
        )

    def start_wb_core_auto_task(self, args: Mapping[str, Any], context: MCPRequestContext) -> dict[str, Any]:
        task_text = _required_str(args, "task_text", max_len=12000)
        idempotency_key = _optional_str(args.get("idempotency_key"))
        operator_note = _optional_str(args.get("operator_note"))
        max_wait_seconds = _int_arg(args.get("max_wait_seconds"), default=0, minimum=0, maximum=30)
        existing = self._idempotent_run("start_wb_core_auto_task", idempotency_key)
        if existing:
            return {**_compact_mcp_run(existing), "status": existing.get("status"), "idempotent_replay": True}

        with self._lock:
            existing = self._idempotent_run("start_wb_core_auto_task", idempotency_key)
            if existing:
                return {**_compact_mcp_run(existing), "status": existing.get("status"), "idempotent_replay": True}
            run_id = _new_mcp_run_id("mcp-auto")
            decision = self._wb_core_auto_arbitration_decision(run_id)
            urls = _run_live_urls(context.base_url, run_id)
            if not decision["auto_production_allowed"]:
                return {
                    "status": "blocked",
                    "accepted": False,
                    "tool": "start_wb_core_auto_task",
                    "target_id": TARGET_PROJECT_ID,
                    "route": decision["route"],
                    "auto_production_allowed": False,
                    "blocker": decision.get("blocker") or decision.get("separate_deploy_reason") or "direct wb-core auto task is blocked",
                    "arbitration_decision": decision,
                    "fallback_to_sprint": False,
                    "fallback_to_managed_clone_only": False,
                }
            initial = self._create_mcp_run(
                run_id=run_id,
                tool="start_wb_core_auto_task",
                run_type="auto_task",
                target_id=TARGET_PROJECT_ID,
                execution_mode=decision["route"],
                route=decision["route"],
                arbitration_route=decision["route"],
                auto_production_allowed=decision["auto_production_allowed"],
                deferred_for_separate_deploy=not decision["auto_production_allowed"],
                separate_deploy_reason=decision.get("separate_deploy_reason"),
                arbitration_decision=decision,
                wb_core_auto_task=True,
                task_text=task_text,
                operator_note=operator_note,
                idempotency_key=idempotency_key,
                dry_run=False,
                live_url=urls["live_url"],
                watch_url=urls["watch_url"],
                status="queued",
                current_stage="auto_task_queued",
            )
            self._record_wb_core_auto_intent(run_id, decision=decision, status="active")

        thread = threading.Thread(
            target=self._wb_core_auto_task_worker,
            args=(run_id, task_text, operator_note),
            daemon=True,
        )
        thread.start()
        if max_wait_seconds:
            waited = self._wait_mcp_run(run_id, max_wait_seconds=max_wait_seconds)
            if waited:
                return self.get_run_status({"run_id": run_id}, context)
        return {
            **_compact_mcp_run(initial),
            "status": "queued",
            "run_id": run_id,
            "accepted": True,
            "tool": "start_wb_core_auto_task",
            "target_id": TARGET_PROJECT_ID,
            "route": decision["route"],
            "auto_production_allowed": decision["auto_production_allowed"],
            "deferred_for_separate_deploy": not decision["auto_production_allowed"],
            "arbitration_decision": decision,
            **urls,
        }

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
        urls = _run_live_urls(context.base_url, run_id)
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
            live_url=urls["live_url"],
            watch_url=urls["watch_url"],
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
        return {**_compact_mcp_run(initial), "status": "queued", "run_id": run_id, "accepted": True, **urls}

    def start_managed_clone_run(self, args: Mapping[str, Any], context: MCPRequestContext) -> dict[str, Any]:
        target_id = _required_str(args, "target_id")
        task_text = _required_str(args, "task_text", max_len=12000)
        no_pr_no_deploy = _bool(args.get("no_pr_no_deploy"), default=True)
        if _has_sprint_bridge_marker(task_text):
            if not _sprint_internal_runtime_enabled():
                return _frozen_sprint_result(
                    target_id=target_id,
                    bridge_tool="start_managed_clone_run",
                    extra={"marker": SPRINT_BRIDGE_MARKER},
                )
            if not no_pr_no_deploy:
                return {
                    "status": "denied",
                    "target_id": target_id,
                    "compatibility_bridge": "start_managed_clone_run",
                    "marker": SPRINT_BRIDGE_MARKER,
                    "blocker": "Sprint compatibility bridge requires no_pr_no_deploy=true.",
                }
            parsed = _parse_sprint_bridge_payload(task_text)
            if parsed.get("status") != "ok":
                return {
                    "status": "blocked",
                    "target_id": target_id,
                    "compatibility_bridge": "start_managed_clone_run",
                    "marker": SPRINT_BRIDGE_MARKER,
                    "blocker": parsed.get("blocker") or "invalid sprint compatibility payload",
                }
            sprint_args = dict(parsed["payload"])
            sprint_args["target_id"] = target_id
            if args.get("idempotency_key") is not None:
                sprint_args["idempotency_key"] = _optional_str(args.get("idempotency_key"))
            if args.get("operator_note") is not None and "operator_note" not in sprint_args:
                sprint_args["operator_note"] = _optional_str(args.get("operator_note"))
            result = self._start_sprint_core(
                sprint_args,
                context,
                bridge_tool="start_managed_clone_run",
            )
            result["compatibility_bridge"] = "start_managed_clone_run"
            result["marker"] = SPRINT_BRIDGE_MARKER
            return result
        if not no_pr_no_deploy:
            return {
                "status": "denied",
                "blocker": "start_managed_clone_run requires no_pr_no_deploy=true; use explicit production-lane tool for wb-core",
                "target_id": target_id,
            }
        run_id = _new_mcp_run_id("mcp-managed")
        urls = _run_live_urls(context.base_url, run_id)
        initial = self._create_mcp_run(
            run_id=run_id,
            tool="start_managed_clone_run",
            target_id=target_id,
            execution_mode="managed_clone_only",
            task_text=task_text,
            operator_note=None,
            idempotency_key=_optional_str(args.get("idempotency_key")),
            dry_run=False,
            live_url=urls["live_url"],
            watch_url=urls["watch_url"],
            status="queued",
            current_stage="queued",
        )
        thread = threading.Thread(
            target=self._managed_clone_worker,
            args=(run_id, target_id, task_text),
            daemon=True,
        )
        thread.start()
        return {**_compact_mcp_run(initial), "status": "queued", "run_id": run_id, "accepted": True, **urls}

    def start_sprint(self, args: Mapping[str, Any], context: MCPRequestContext) -> dict[str, Any]:
        if not _sprint_internal_runtime_enabled():
            return _frozen_sprint_result(target_id=_optional_str(args.get("target_id")) or TARGET_PROJECT_ID, bridge_tool=None)
        return self._start_sprint_core(args, context, bridge_tool=None)

    def _start_sprint_core(self, args: Mapping[str, Any], context: MCPRequestContext, *, bridge_tool: str | None) -> dict[str, Any]:
        target_id = _required_str(args, "target_id")
        sprint_text = _required_str(args, "sprint_text", max_len=16000)
        execution_mode = _optional_str(args.get("execution_mode")) or "managed_clone_only"
        if target_id != TARGET_PROJECT_ID:
            return {"status": "denied", "target_id": target_id, "blocker": "internal start_sprint currently allows only target_id=wb-core"}
        if execution_mode != "managed_clone_only":
            return {
                "status": "denied",
                "target_id": target_id,
                "blocker": "internal start_sprint supports only execution_mode=managed_clone_only; production_lane is not allowed",
            }
        max_steps = _int_arg(args.get("max_steps"), default=2, minimum=1, maximum=3)
        max_retries = _int_arg(args.get("max_retries_per_step"), default=1, minimum=0, maximum=1)
        idempotency_key = _optional_str(args.get("idempotency_key"))
        existing = self._idempotent_run("start_sprint", idempotency_key)
        if existing:
            return {**_compact_mcp_run(existing), "status": existing.get("status"), "idempotent_replay": True}

        run_id = _new_mcp_run_id("mcp-sprint")
        urls = _run_live_urls(context.base_url, run_id)
        layout = self.store.layout.run_layout(run_id)
        layout.ensure_dirs()
        initial = self._create_mcp_run(
            run_id=run_id,
            tool="start_sprint",
            run_type="sprint",
            started_via_tool=bridge_tool or "start_sprint",
            compatibility_bridge=bridge_tool,
            target_id=target_id,
            execution_mode="managed_clone_only",
            sprint_text=sprint_text,
            operator_note=_optional_str(args.get("operator_note")),
            idempotency_key=idempotency_key,
            max_steps=max_steps,
            max_retries_per_step=max_retries,
            current_step_index=0,
            child_run_ids=[],
            curator_decisions=[],
            run_dir=str(layout.run_dir),
            live_url=urls["live_url"],
            watch_url=urls["watch_url"],
            status="queued",
            current_stage="sprint_queued",
        )
        self._write_sprint_prompt(
            run_id,
            sprint_text=sprint_text,
            operator_note=_optional_str(args.get("operator_note")),
            max_steps=max_steps,
            max_retries_per_step=max_retries,
        )
        thread = threading.Thread(
            target=self._sprint_worker,
            args=(run_id, target_id, sprint_text, max_steps, max_retries),
            daemon=True,
        )
        thread.start()
        result = {**_compact_mcp_run(initial), "status": "queued", "run_id": run_id, "accepted": True, **urls}
        if bridge_tool:
            result["started_via_tool"] = bridge_tool
            result["canonical_tool"] = "start_sprint"
        return result

    def resume_wb_core_production_deploy(self, args: Mapping[str, Any], context: MCPRequestContext) -> dict[str, Any]:
        run_id = _required_str(args, "run_id")
        dry_run = _bool(args.get("dry_run"), default=True)
        confirm = _bool(args.get("confirm_resume_deploy"), default=False)
        urls = _run_live_urls(context.base_url, run_id)
        existing = self._read_mcp_runs().get(run_id)
        if not existing:
            self._create_mcp_run(
                run_id=run_id,
                tool="resume_wb_core_production_deploy",
                target_id=TARGET_PROJECT_ID,
                execution_mode="production_lane_resume",
                task_text=f"Resume already merged wb-core production-lane deploy for {run_id}",
                operator_note=None,
                idempotency_key=_optional_str(args.get("idempotency_key")),
                dry_run=dry_run,
                live_url=urls["live_url"],
                watch_url=urls["watch_url"],
                status="queued",
                current_stage="resume_queued",
            )
        if dry_run:
            result = execute_wb_core_resume_deploy(run_id=run_id, state_dir=self.store.state_dir, execute=False)
            payload = target_production_resume_result_to_dict(result)
            self._update_mcp_run(
                run_id,
                tool="resume_wb_core_production_deploy",
                target_id=TARGET_PROJECT_ID,
                execution_mode="production_lane_resume_dry_run",
                status="completed_dry_run" if result.allowed and not result.blockers else "blocked",
                current_stage=payload.get("status"),
                merge_commit=payload.get("merge_commit"),
                target_pr_url=payload.get("target_pr_url"),
                target_pr_number=payload.get("target_pr_number"),
                deploy_status=payload.get("deploy_status"),
                public_verify_status=payload.get("public_verify_status"),
                rollback_plan_path=payload.get("rollback_plan_path"),
                blocker="; ".join(payload.get("blockers") or []),
                message="Resume deploy dry-run eligibility evaluated; no backup, deploy or probe was executed.",
            )
            return {**payload, **urls}
        if not confirm:
            self._update_mcp_run(
                run_id,
                status="blocked",
                current_stage="resume_confirmation_required",
                blocker="confirm_resume_deploy=true is required when dry_run=false",
            )
            return {
                "status": "denied",
                "run_id": run_id,
                "accepted": False,
                "resume_started": False,
                "blocker": "confirm_resume_deploy=true is required when dry_run=false",
                **urls,
            }
        self._update_mcp_run(
            run_id,
            tool="resume_wb_core_production_deploy",
            target_id=TARGET_PROJECT_ID,
            execution_mode="production_lane_resume",
            status="queued",
            current_stage="resume_queued",
            message="Queued post-merge resume deploy.",
        )
        thread = threading.Thread(target=self._resume_deploy_worker, args=(run_id,), daemon=True)
        thread.start()
        return {"status": "queued", "run_id": run_id, "accepted": True, "resume_started": True, **urls}

    def get_run_status(self, args: Mapping[str, Any], _context: MCPRequestContext) -> dict[str, Any]:
        run_id = _required_str(args, "run_id")
        run = self._read_mcp_runs().get(run_id)
        if run:
            enriched = self._apply_promotion_group_child_override(self._enrich_mcp_run(run))
            return _sanitize(self._status_payload_from_enriched_run(run_id, enriched))
        real_enriched = self._real_job_live_summary(run_id)
        if real_enriched:
            return _sanitize(self._status_payload_from_enriched_run(run_id, real_enriched))
        try:
            existing = self.store.get_run(run_id)
        except Exception:
            try:
                group = self.store.get_parallel_promotion_group(run_id).get("group") or {}
            except Exception:
                return {"status": "not_found", "run_id": run_id, "blocker": "run_id is unknown"}
            return _sanitize(
                {
                    "status": group.get("status"),
                    "run_id": run_id,
                    "target": group.get("target_id"),
                    "run_type": "group_promotion",
                    "execution_mode": group.get("execution_mode") or "selected_merge_deploy_group",
                    "current_stage": group.get("current_step"),
                    "created_at": group.get("created_at"),
                    "updated_at": group.get("updated_at"),
                    "blockers": _blockers(group),
                    "partial_result": {
                        "status": group.get("status"),
                        "production_run_ids": group.get("production_run_ids", []),
                        "pr_urls": group.get("pr_urls", []),
                        "merge_commits": group.get("merge_commits", []),
                        "deploy_status": group.get("deploy_status"),
                        "public_verify_status": group.get("public_verify_status"),
                    },
                    "selected_ids": group.get("selected_ids", []),
                    "planned_order": group.get("planned_order", []),
                    "accepted_task_ids": group.get("accepted_task_ids", []),
                    "deferred_task_ids": group.get("deferred_task_ids", []),
                    "per_task_status": group.get("per_task_status", {}),
                    "conflicted_ids": group.get("conflicted_ids", []),
                    "conflict_files": group.get("conflict_files", []),
                    "conflict_reason_by_task": group.get("conflict_reason_by_task", {}),
                    "refresh_required_ids": group.get("refresh_required_ids", []),
                    "recommended_action": group.get("recommended_action"),
                    "pr_url": None,
                    "deploy_status": None,
                    "lock_wait": None,
                    "live_url": live_url(_public_origin(), None),
                    "watch_url": live_url(_public_origin(), run_id),
                    "operator_label": group.get("operator_lifecycle_label"),
                    "operator_lifecycle_status": group.get("operator_lifecycle_status"),
                }
            )
        existing_summary = self._apply_promotion_group_child_override(
            {
                "status": existing.get("status"),
                "run_id": run_id,
                "target": existing.get("target_project_id"),
                "target_id": existing.get("target_project_id"),
                "execution_mode": "managed_clone_only" if existing.get("workspace_path") else "fake_or_local",
                "current_stage": existing.get("status"),
                "created_at": _record_time(existing),
                "updated_at": _record_time(existing),
                "blockers": _blockers(existing),
                "pr_url": None,
                "deploy_status": None,
                "lock_wait": None,
                "live_url": live_url(_public_origin(), None),
                "watch_url": live_url(_public_origin(), run_id),
            }
        )
        existing_summary["blockers"] = _blockers(existing_summary)
        return _sanitize(existing_summary)

    def get_run_report(self, args: Mapping[str, Any], context: MCPRequestContext) -> dict[str, Any]:
        run_id = _required_str(args, "run_id")
        status = self.get_run_status({"run_id": run_id}, context)
        if status.get("status") == "not_found":
            return status
        run_dir = self._run_dir_for_any_run(run_id)
        production_result = _read_json_if_exists(run_dir / "artifacts" / "production_lane" / "production_lane_result.json")
        resume_result = _read_json_if_exists(run_dir / "artifacts" / "production_lane" / "resume_deploy_result.json")
        recovery_report = _read_json_if_exists(run_dir / "artifacts" / "production_lane" / "resume_deploy_report.json")
        sprint_report = _read_json_if_exists(run_dir / "artifacts" / "sprint" / "sprint_report.json")
        latest_result = resume_result or production_result
        mcp_report = _read_json_if_exists(run_dir / "artifacts" / "production_lane" / "mcp_production_lane_report.json")
        rollback = self._rollback_plan_for_run_dir(run_dir)
        record = _read_run_record_if_exists(run_dir)
        verifier = record.get("verifier") if isinstance(record, Mapping) else None
        result = record.get("result") if isinstance(record, Mapping) else {}
        handoff_path = run_dir / "artifacts" / "handoff.md"
        handoff_excerpt = None
        handoff_truncated = False
        if handoff_path.exists():
            handoff_excerpt, handoff_truncated = _read_sanitized_text(handoff_path, max_bytes=12000)
        reconciliation = codex_run_reconciliation(
            run_dir,
            declared_status=status.get("status"),
            current_stage=status.get("current_stage"),
            blocker=json.dumps(status.get("blockers") or [], ensure_ascii=False),
        )
        return _sanitize(
            {
                "status": status.get("status"),
                "effective_status": reconciliation.get("effective_status"),
                "effective_activity": reconciliation.get("effective_activity"),
                "is_inconsistent": reconciliation.get("is_inconsistent"),
                "run_id": run_id,
                "target": status.get("target"),
                "execution_mode": status.get("execution_mode"),
                "pr_url": (latest_result or {}).get("target_pr_url"),
                "merge_commit": (latest_result or {}).get("merge_commit"),
                "deploy_result": {
                    "deploy_status": (latest_result or {}).get("deploy_status"),
                    "public_verify_status": (latest_result or {}).get("public_verify_status"),
                },
                "probes": {
                    "public_verify_status": (latest_result or {}).get("public_verify_status"),
                },
                "rollback_plan": rollback,
                "changed_files": (result or {}).get("changed_files", []),
                "verifier_result": verifier,
                "handoff": {
                    "present": handoff_path.exists(),
                    "excerpt": handoff_excerpt,
                    "truncated": handoff_truncated,
                },
                "control_plane_observer": {
                    "status": reconciliation.get("control_plane_observer_status"),
                    "blocker": reconciliation.get("control_plane_observer_blocker"),
                    "operator_label": reconciliation.get("operator_label"),
                    "verifier_gap": reconciliation.get("verifier_gap"),
                    "handoff_present_verifier_missing_due_to_control_error": reconciliation.get("handoff_present_verifier_missing_due_to_control_error"),
                },
                "blocker": status.get("blockers"),
                "production_lane_result": production_result,
                "resume_deploy_result": resume_result,
                "recovery_report": recovery_report,
                "sprint_report": sprint_report,
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

    def get_run_timeline(self, args: Mapping[str, Any], _context: MCPRequestContext) -> dict[str, Any]:
        run_id = _required_str(args, "run_id")
        try:
            run_dir = self._run_dir_for_any_run(run_id)
        except FileNotFoundError:
            try:
                job = self.store.get_real_run_job(run_id)
            except Exception:
                job = {}
            if job:
                return {
                    "status": "ok",
                    "run_id": run_id,
                    "events": _sanitize(job.get("timeline_events") or []),
                }
            return {"status": "not_found", "run_id": run_id}
        record = _read_run_record_if_exists(run_dir)
        fallback = []
        if record:
            try:
                from dev_control_plane.timeline import build_run_timeline

                fallback = build_run_timeline({"run_id": run_id}, record).get("events", [])
            except Exception:
                fallback = []
        return {"status": "ok", "run_id": run_id, "events": read_live_timeline(run_dir, fallback_events=fallback)}

    def get_run_log_tail(self, args: Mapping[str, Any], _context: MCPRequestContext) -> dict[str, Any]:
        run_id = _required_str(args, "run_id")
        max_bytes = _int_arg(args.get("max_bytes"), default=24_000, minimum=1000, maximum=64_000)
        try:
            run_dir = self._run_dir_for_any_run(run_id)
        except FileNotFoundError:
            return {"status": "not_found", "run_id": run_id}
        tail = read_terminal_tail(run_dir, max_bytes=max_bytes)
        return {"status": tail.get("status"), "run_id": run_id, "ansi_text": tail.get("ansi_text"), "plain_text": tail.get("plain_text"), "truncated": tail.get("truncated"), "source": tail.get("source")}

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

    def list_target_docs(self, args: Mapping[str, Any], _context: MCPRequestContext) -> dict[str, Any]:
        target_id = _required_str(args, "target_id")
        config = self._target_docs_config(target_id)
        return _sanitize(read_target_docs_list(config, state_dir=self.store.state_dir))

    def search_target_docs(self, args: Mapping[str, Any], _context: MCPRequestContext) -> dict[str, Any]:
        target_id = _required_str(args, "target_id")
        query = _required_str(args, "query", max_len=500)
        config = self._target_docs_config(target_id)
        return _sanitize(
            read_target_docs_search(
                config,
                state_dir=self.store.state_dir,
                query=query,
                max_results=_optional_int(args.get("max_results")),
                path_prefix=_optional_str(args.get("path_prefix")),
            )
        )

    def get_target_doc(self, args: Mapping[str, Any], _context: MCPRequestContext) -> dict[str, Any]:
        target_id = _required_str(args, "target_id")
        path = _required_str(args, "path", max_len=500)
        config = self._target_docs_config(target_id)
        return _sanitize(
            read_target_doc(
                config,
                state_dir=self.store.state_dir,
                path=path,
                line_start=_optional_int(args.get("line_start")),
                line_end=_optional_int(args.get("line_end")),
                max_bytes=_optional_int(args.get("max_bytes")),
            )
        )

    def read_target_docs(self, args: Mapping[str, Any], context: MCPRequestContext) -> dict[str, Any]:
        action = _required_str(args, "action", max_len=20).lower()
        if action == "list":
            return self.list_target_docs(args, context)
        if action == "search":
            return self.search_target_docs(args, context)
        if action == "get":
            return self.get_target_doc(args, context)
        return {
            "status": "bad_request",
            "tool": "read_target_docs",
            "blocker": "action must be one of: list, search, get",
        }

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

    def _sprint_worker(self, run_id: str, target_id: str, sprint_text: str, max_steps: int, max_retries_per_step: int) -> None:
        decisions: list[dict[str, Any]] = []
        child_run_ids: list[str] = []
        final_status = "blocked"
        final_summary = ""
        blocker = ""
        try:
            layout = self.store.layout.run_layout(run_id)
            layout.ensure_dirs()
            self._update_mcp_run(run_id, status="curator_planning", current_stage="curator_planning")
            append_terminal_output(layout.run_dir, "\x1b[1;36mServer curator started sprint planning.\x1b[0m\n")
            target_context = self._sprint_target_context(target_id)
            step_index = 1
            retry_count = 0
            last_handoff = ""
            last_verifier_status = ""

            while step_index <= max_steps:
                plan = self._sprint_plan_decision(
                    run_id=run_id,
                    step_index=step_index,
                    retry_count=retry_count,
                    sprint_text=sprint_text,
                    target_context=target_context,
                    previous_handoff=last_handoff,
                )
                decisions.append(self._record_sprint_decision(run_id, plan))
                step_task = str(plan.get("next_step_task_text") or "")
                if not step_task:
                    blocker = "curator did not produce next_step_task_text"
                    final_status = "blocked"
                    break

                child_run_id = _new_mcp_run_id("mcp-managed")
                child_run_ids.append(child_run_id)
                self._write_child_runs_artifact(run_id, child_run_ids)
                self._update_mcp_run(
                    run_id,
                    status="running",
                    current_stage=f"sprint_step_{step_index}_codex",
                    current_step_index=step_index,
                    child_run_ids=child_run_ids,
                    curator_decisions=_compact_decisions(decisions),
                )
                append_terminal_output(
                    layout.run_dir,
                    f"\x1b[36mCurator queued Codex step {step_index}"
                    f"{' retry ' + str(retry_count) if retry_count else ''}: {plan.get('reason')}\x1b[0m\n",
                )
                urls = _run_live_urls(_public_origin(), child_run_id)
                self._create_mcp_run(
                    run_id=child_run_id,
                    tool="start_managed_clone_run",
                    run_type="managed",
                    parent_run_id=run_id,
                    target_id=target_id,
                    execution_mode="managed_clone_only",
                    task_text=step_task,
                    operator_note="server sprint orchestrator child run",
                    idempotency_key=None,
                    dry_run=False,
                    sprint_step_index=step_index,
                    sprint_retry=retry_count,
                    live_url=urls["live_url"],
                    watch_url=urls["watch_url"],
                    status="queued",
                    current_stage="queued",
                )
                self._managed_clone_worker(child_run_id, target_id, step_task)
                child = dict(self._read_mcp_runs().get(child_run_id) or {})
                last_handoff = self._child_handoff_summary(child)
                last_verifier_status = str(child.get("verifier_status") or "")
                review = self._sprint_review_decision(
                    run_id=run_id,
                    step_index=step_index,
                    retry_count=retry_count,
                    child_run=child,
                    handoff_summary=last_handoff,
                    max_retries_per_step=max_retries_per_step,
                )
                decisions.append(self._record_sprint_decision(run_id, review))
                self._update_mcp_run(
                    run_id,
                    status="curator_review",
                    current_stage=f"sprint_step_{step_index}_review",
                    child_run_ids=child_run_ids,
                    curator_decisions=_compact_decisions(decisions),
                    verifier_status=last_verifier_status,
                )
                append_terminal_output(layout.run_dir, f"\x1b[36mCurator review: {review.get('decision')} - {review.get('reason')}\x1b[0m\n")

                if review.get("decision") == "retry_step":
                    retry_count += 1
                    continue
                if review.get("decision") == "finish":
                    final_status = "passed"
                    final_summary = str(review.get("final_summary") or "Sprint completed.")
                    break
                if review.get("decision") == "next_step":
                    step_index += 1
                    retry_count = 0
                    continue
                final_status = "blocked"
                blocker = str(review.get("blocker") or review.get("reason") or "curator blocked sprint")
                break
            else:
                final_status = "blocked"
                blocker = "max_steps reached before curator finish decision"

            if not final_summary:
                final_summary = "Sprint completed." if final_status == "passed" else "Sprint stopped before completion."
            report = self._write_sprint_report(
                run_id,
                target_id=target_id,
                sprint_text=sprint_text,
                status=final_status,
                blocker=blocker,
                child_run_ids=child_run_ids,
                decisions=decisions,
                final_summary=final_summary,
                verifier_status=last_verifier_status,
            )
            self._update_mcp_run(
                run_id,
                status=final_status,
                current_stage="sprint_finished" if final_status == "passed" else "sprint_blocked",
                child_run_ids=child_run_ids,
                curator_decisions=_compact_decisions(decisions),
                sprint_report_path=report.get("sprint_report_path"),
                handoff_path=report.get("sprint_handoff_path"),
                blocker=blocker,
                message=final_summary,
            )
        except Exception as exc:
            self._update_mcp_run(run_id, status="failed", current_stage="sprint_failed", blocker=_safe_exception_text(exc), child_run_ids=child_run_ids)

    def _sprint_plan_decision(
        self,
        *,
        run_id: str,
        step_index: int,
        retry_count: int,
        sprint_text: str,
        target_context: Mapping[str, Any],
        previous_handoff: str,
    ) -> dict[str, Any]:
        context_text = _truncate(json.dumps(target_context, ensure_ascii=False, sort_keys=True), 7000)
        retry_note = f"\nRetry reason: previous attempt needs correction.\nPrevious handoff:\n{previous_handoff}\n" if retry_count else ""
        step_task = (
            f"Server-side sprint step {step_index} for target wb-core.\n\n"
            f"Original sprint request:\n{sprint_text}\n"
            f"{retry_note}\n"
            "Target docs context excerpt:\n"
            f"{context_text}\n\n"
            "Execution constraints:\n"
            "- Work only in the managed clone workspace.\n"
            "- Do not open a PR, merge, deploy, SSH, mutate runtime, or touch the original target repo.\n"
            "- Do not read or expose secrets.\n"
            "- Keep changes bounded to the sprint request.\n"
            "- Final answer must start with === ДЛЯ КУРАТОРА === and include === СЖАТАЯ ПРОВЕРКА ===.\n"
        )
        return {
            "timestamp": _now_utc(),
            "phase": "plan",
            "decision": "next_step",
            "reason": "curator selected one bounded managed-clone Codex step",
            "next_step_task_text": step_task,
            "acceptance_criteria": [
                "child Codex run uses managed_clone_only",
                "handoff and verifier artifacts are produced",
                "no PR, merge, deploy or original target mutation is attempted",
            ],
            "risk_class": "L3",
            "retry_reason": "previous verifier/handoff issue" if retry_count else "",
            "final_summary": "",
            "blocker": "",
            "run_id": run_id,
            "step_index": step_index,
            "retry": retry_count,
        }

    def _sprint_review_decision(
        self,
        *,
        run_id: str,
        step_index: int,
        retry_count: int,
        child_run: Mapping[str, Any],
        handoff_summary: str,
        max_retries_per_step: int,
    ) -> dict[str, Any]:
        child_status = str(child_run.get("status") or "")
        verifier_status = str(child_run.get("verifier_status") or "")
        child_run_id = str(child_run.get("run_id") or "")
        if child_status == "passed" and verifier_status == "passed":
            decision = "finish"
            reason = "child Codex run passed verifier; MVP sprint can finish"
            blocker = ""
            final_summary = f"Sprint finished after step {step_index}; child run {child_run_id} passed verifier."
        elif retry_count < max_retries_per_step:
            decision = "retry_step"
            reason = "child Codex run did not pass; one bounded retry is available"
            blocker = ""
            final_summary = ""
        else:
            decision = "blocked"
            reason = "child Codex run did not pass and retry budget is exhausted"
            blocker = str(child_run.get("blocker") or child_run.get("blocker_summary") or reason)
            final_summary = ""
        return {
            "timestamp": _now_utc(),
            "phase": "review",
            "decision": decision,
            "reason": reason,
            "next_step_task_text": "",
            "acceptance_criteria": [],
            "risk_class": "L3",
            "retry_reason": reason if decision == "retry_step" else "",
            "final_summary": final_summary,
            "blocker": blocker,
            "run_id": run_id,
            "step_index": step_index,
            "retry": retry_count,
            "child_run_id": child_run_id,
            "child_status": child_status,
            "verifier_status": verifier_status,
            "handoff_summary": _truncate(handoff_summary, 3000),
        }

    def _sprint_target_context(self, target_id: str) -> dict[str, Any]:
        config = self._target_docs_config(target_id)
        context: dict[str, Any] = {"target_id": target_id, "docs": [], "excerpts": []}
        try:
            listing = read_target_docs_list(config, state_dir=self.store.state_dir)
            context["docs"] = listing.get("docs", [])
            context["ref"] = listing.get("ref")
        except Exception as exc:
            context["docs_blocker"] = _safe_exception_text(exc)
        for path in ("README.md", "docs/modules/00_INDEX__MODULES.md"):
            try:
                doc = read_target_doc(config, state_dir=self.store.state_dir, path=path, max_bytes=6000)
                context["excerpts"].append(
                    {
                        "path": path,
                        "ref": doc.get("ref"),
                        "content_excerpt": _truncate(doc.get("content"), 6000),
                    }
                )
            except Exception as exc:
                context["excerpts"].append({"path": path, "blocker": _safe_exception_text(exc)})
        return _sanitize(context)

    def _write_sprint_prompt(
        self,
        run_id: str,
        *,
        sprint_text: str,
        operator_note: str | None,
        max_steps: int,
        max_retries_per_step: int,
    ) -> None:
        artifacts = self._sprint_artifacts_dir(run_id)
        artifacts.mkdir(parents=True, exist_ok=True)
        (artifacts / "sprint_prompt.md").write_text(
            "\n".join(
                (
                    "# DevControl Sprint Prompt",
                    "",
                    f"run_id: {run_id}",
                    "target_id: wb-core",
                    "execution_mode: managed_clone_only",
                    f"max_steps: {max_steps}",
                    f"max_retries_per_step: {max_retries_per_step}",
                    "",
                    "## Sprint Text",
                    sprint_text,
                    "",
                    "## Operator Note",
                    operator_note or "",
                    "",
                    "No PR, merge, deploy, SSH or production-lane stage is allowed inside sprint MVP.",
                )
            ),
            encoding="utf-8",
        )

    def _record_sprint_decision(self, run_id: str, decision: Mapping[str, Any]) -> dict[str, Any]:
        artifacts = self._sprint_artifacts_dir(run_id)
        artifacts.mkdir(parents=True, exist_ok=True)
        payload = _sanitize(dict(decision))
        with (artifacts / "curator_decisions.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        with (artifacts / "curator_transcript.md").open("a", encoding="utf-8") as handle:
            handle.write(
                f"## {payload.get('timestamp')} - {payload.get('phase')} - {payload.get('decision')}\n\n"
                f"Reason: {payload.get('reason')}\n\n"
                f"Child: {payload.get('child_run_id') or 'n/a'}\n\n"
                f"Verifier: {payload.get('verifier_status') or 'n/a'}\n\n"
                f"Blocker: {payload.get('blocker') or 'none'}\n\n"
            )
        return payload

    def _write_child_runs_artifact(self, run_id: str, child_run_ids: Sequence[str]) -> None:
        artifacts = self._sprint_artifacts_dir(run_id)
        artifacts.mkdir(parents=True, exist_ok=True)
        payload = {"status": "ok", "run_id": run_id, "child_run_ids": list(child_run_ids), "updated_at": _now_utc()}
        (artifacts / "child_runs.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _child_handoff_summary(self, child_run: Mapping[str, Any]) -> str:
        handoff_path = _optional_str(child_run.get("handoff_path"))
        if not handoff_path:
            return ""
        try:
            content, _truncated = _read_sanitized_text(Path(handoff_path), max_bytes=12000)
            return _truncate(content, 4000)
        except Exception:
            return ""

    def _write_sprint_report(
        self,
        run_id: str,
        *,
        target_id: str,
        sprint_text: str,
        status: str,
        blocker: str,
        child_run_ids: Sequence[str],
        decisions: Sequence[Mapping[str, Any]],
        final_summary: str,
        verifier_status: str,
    ) -> dict[str, Any]:
        layout = self.store.layout.run_layout(run_id)
        artifacts = self._sprint_artifacts_dir(run_id)
        artifacts.mkdir(parents=True, exist_ok=True)
        report = _sanitize(
            {
                "status": status,
                "run_id": run_id,
                "target_id": target_id,
                "execution_mode": "managed_clone_only",
                "sprint_text_excerpt": _excerpt(sprint_text, ""),
                "child_run_ids": list(child_run_ids),
                "curator_decisions": list(decisions),
                "final_summary": final_summary,
                "blocker": blocker,
                "verifier_status": verifier_status,
                "production_lane_started": False,
                "pr_created": False,
                "deploy_started": False,
                "updated_at": _now_utc(),
            }
        )
        sprint_report_path = artifacts / "sprint_report.json"
        sprint_report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        handoff = (
            "=== ДЛЯ КУРАТОРА ===\n\n"
            f"Статус: {'sprint completed' if status == 'passed' else 'sprint blocked'}\n"
            f"Что сделано: {final_summary}\n"
            f"Child runs: {', '.join(child_run_ids) if child_run_ids else 'none'}\n"
            "PR/Merge/Deploy: not run\n"
            f"Blocker: {blocker or 'none'}\n\n"
            "=== СЖАТАЯ ПРОВЕРКА ===\n\n"
            f"- managed_clone_only: yes\n"
            f"- production_lane: not run\n"
            f"- child runs: {len(child_run_ids)}\n"
            f"- verifier: {verifier_status or 'n/a'}\n"
        )
        sprint_handoff_path = artifacts / "sprint_handoff.md"
        sprint_handoff_path.write_text(handoff, encoding="utf-8")
        run_json = {
            "schema_version": 1,
            "type": "sprint",
            "result": {
                "id": run_id,
                "status": status,
                "target_project_id": target_id,
                "run_dir": str(layout.run_dir),
                "handoff_path": str(sprint_handoff_path),
                "changed_files": [],
                "verifier_status": verifier_status,
                "blocker_reason": blocker or None,
            },
            "sprint_report": report,
            "updated_at": _now_utc(),
        }
        (layout.run_dir / "run.json").write_text(json.dumps(run_json, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return {"sprint_report_path": str(sprint_report_path), "sprint_handoff_path": str(sprint_handoff_path), "report": report}

    def _sprint_artifacts_dir(self, run_id: str) -> Path:
        return self.store.layout.run_layout(run_id).artifacts_dir / "sprint"

    def _wb_core_auto_task_worker(self, run_id: str, task_text: str, operator_note: str | None) -> None:
        try:
            run = self._read_mcp_runs().get(run_id) or {}
            route = str(run.get("route") or run.get("arbitration_route") or "")
            if route == "wb_core_exclusive_auto_production":
                if _auto_task_stub_enabled():
                    self._exclusive_auto_task_stub_worker(run_id, task_text, operator_note)
                else:
                    self._production_lane_worker(run_id, task_text, operator_note)
                    final = self._read_mcp_runs().get(run_id) or {}
                    if str(final.get("status") or "") == "completed" and str(final.get("public_verify_status") or "") in {"passed", "ok", "success"}:
                        self._update_mcp_run(
                            run_id,
                            status="production_complete",
                            current_stage=str(final.get("current_stage") or "post_deploy_passed"),
                            route="wb_core_exclusive_auto_production",
                            arbitration_route="wb_core_exclusive_auto_production",
                            auto_production_allowed=True,
                            deferred_for_separate_deploy=False,
                            finished_at=_now_utc(),
                            message="Exclusive auto-production completed through existing wb-core production lane.",
                        )
            else:
                blocker = str(run.get("blocker") or "direct wb-core auto production-capable route is blocked; no managed-clone-only fallback is allowed")
                self._update_mcp_run(
                    run_id,
                    status="blocked",
                    current_stage="auto_task_blocked",
                    blocker=blocker,
                    auto_production_allowed=False,
                    production_lane_started=False,
                    real_production_lane_started=False,
                    finished_at=_now_utc(),
                )
        except Exception as exc:
            self._update_mcp_run(
                run_id,
                status="failed",
                current_stage="auto_task_failed",
                blocker=_safe_exception_text(exc),
                auto_production_allowed=False,
                finished_at=_now_utc(),
            )
        finally:
            final = self._read_mcp_runs().get(run_id) or {}
            if _auto_task_run_is_terminal(final):
                self._release_wb_core_auto_intent(
                    run_id,
                    status=str(final.get("status") or "terminal"),
                    reason=str(final.get("blocker") or final.get("separate_deploy_reason") or ""),
                )

    def _exclusive_auto_task_stub_worker(self, run_id: str, task_text: str, operator_note: str | None) -> None:
        self._update_mcp_run(
            run_id,
            status="preparing",
            current_stage="managed_clone_prepare",
            route="wb_core_exclusive_auto_production",
            arbitration_route="wb_core_exclusive_auto_production",
            auto_production_allowed=True,
        )
        target_config = self.store._target_config_by_id(TARGET_PROJECT_ID)
        task_spec = self._create_frozen_mcp_task_spec(
            run_id=run_id,
            target_id=TARGET_PROJECT_ID,
            task_text=task_text,
            operator_note=operator_note,
            execution_mode="wb_core_exclusive_auto_production",
        )
        result = self._fake_managed_clone_result(run_id, target_config, task_spec, task_text)
        delay = _auto_task_stub_delay_seconds()
        if delay:
            time.sleep(delay)
        if _auto_task_stub_verifier_status() != "passed":
            self._update_mcp_run(
                run_id,
                status="blocked",
                current_stage="verifier_failed",
                run_dir=result.run_dir,
                workspace_path=result.workspace_path,
                prompt_path=result.prompt_path,
                handoff_path=result.handoff_path,
                log_path=result.log_path,
                diff_path=result.diff_path,
                verifier_status="failed",
                changed_files=list(result.changed_files),
                blocker="stubbed verifier failure for auto-production arbitration test",
                production_lane_started=False,
                real_production_lane_started=False,
                finished_at=_now_utc(),
            )
            return
        self._update_mcp_run(
            run_id,
            status="verifier_passed",
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
        self._update_mcp_run(
            run_id,
            status="production_complete",
            current_stage="post_deploy_passed",
            deploy_status="passed",
            public_verify_status="passed",
            auto_production_allowed=True,
            deferred_for_separate_deploy=False,
            branch_pr_created=False,
            production_lane_started=True,
            real_production_lane_started=False,
            production_lane_stubbed=True,
            finished_at=_now_utc(),
            message="Stubbed exclusive auto-production completed for deterministic tests; no target mutation occurred.",
        )

    def _wb_core_auto_arbitration_decision(self, run_id: str) -> dict[str, Any]:
        reasons: list[str] = []
        uncertain = False
        try:
            lock = inspect_wb_core_production_lock(
                workspace_path=None,
                run_dir=self.store.layout.run_layout(run_id).run_dir,
                run_id=run_id,
            )
            lock_status = str(lock.get("status") or "unknown")
            if lock_status != "free":
                reasons.append(f"wb-core production lock is {lock_status}" + (f" by {lock.get('run_id')}" if lock.get("run_id") else ""))
        except Exception as exc:
            lock = {"status": "unknown", "blocker": _safe_exception_text(exc)}
            reasons.append("wb-core production lock status is not provable")
            uncertain = True
        try:
            active_runs = self._active_wb_core_server_runs()
            if active_runs:
                reasons.append("active non-terminal wb-core run exists: " + ", ".join(active_runs[:5]))
        except Exception as exc:
            active_runs = []
            reasons.append("active wb-core run state is not provable")
            uncertain = True
        try:
            active_intents = self._active_wb_core_auto_intents()
            if active_intents:
                reasons.append("active wb-core auto-production intent exists: " + ", ".join(active_intents[:5]))
        except Exception:
            active_intents = []
            reasons.append("auto-production intent state is not provable")
            uncertain = True
        try:
            deferred = self._deferred_wb_core_candidates()
            if deferred:
                reasons.append("deferred/selected wb-core candidate requires separate deploy: " + ", ".join(deferred[:5]))
        except Exception:
            deferred = []
            reasons.append("deferred candidate state is not provable")
            uncertain = True

        if reasons or uncertain:
            blocker = "direct wb-core auto production-capable route is blocked: " + ("; ".join(reasons) or "exclusivity cannot be proven")
            return {
                "status": "blocked",
                "target_id": TARGET_PROJECT_ID,
                "route": "wb_core_direct_auto_blocked",
                "auto_production_allowed": False,
                "deferred_for_separate_deploy": False,
                "blocker": blocker,
                "separate_deploy_reason": "; ".join(reasons) or "exclusivity cannot be proven",
                "busy_reasons": reasons or ["exclusivity cannot be proven"],
                "lock": _sanitize(lock),
                "active_run_ids": active_runs,
                "active_auto_intents": active_intents,
                "deferred_candidate_ids": deferred,
                "decision_owner": "devcontrol_server_atomic_state",
                "decided_at": _now_utc(),
            }
        return {
            "status": "exclusive",
            "target_id": TARGET_PROJECT_ID,
            "route": "wb_core_exclusive_auto_production",
            "auto_production_allowed": True,
            "deferred_for_separate_deploy": False,
            "busy_reasons": [],
            "lock": _sanitize(lock),
            "active_run_ids": [],
            "active_auto_intents": [],
            "deferred_candidate_ids": [],
            "decision_owner": "devcontrol_server_atomic_state",
            "decided_at": _now_utc(),
        }

    def _active_wb_core_server_runs(self) -> list[str]:
        active: list[str] = []
        for run_id, run in self._read_mcp_runs().items():
            if not isinstance(run, Mapping):
                continue
            if str(run.get("target_id") or "") != TARGET_PROJECT_ID:
                continue
            if _auto_task_run_is_terminal(run):
                continue
            active.append(str(run.get("run_id") or run_id))
        for run_id, job in self.store._read_collection("real_runs").items():
            if not isinstance(job, Mapping):
                continue
            if str(job.get("target_project_id") or "") != TARGET_PROJECT_ID:
                continue
            if _auto_task_run_is_terminal(job):
                continue
            active.append(str(job.get("run_id") or job.get("id") or run_id))
        for raw in self.store._read_collection("parallel_promotion_groups").values():
            if not isinstance(raw, Mapping) or str(raw.get("target_id") or "") != TARGET_PROJECT_ID:
                continue
            status = str(raw.get("status") or "")
            has_bound_production = bool(raw.get("production_run_id") or raw.get("production_run_ids"))
            if status in {"promotion_running", "production_lane_running"} and has_bound_production:
                active.append(str(raw.get("group_id") or "parallel-promotion-group"))
        return list(dict.fromkeys(active))

    def _active_wb_core_auto_intents(self) -> list[str]:
        self._reconcile_wb_core_auto_intents()
        active: list[str] = []
        for run_id, intent in self.store._read_collection(WB_CORE_AUTO_INTENTS_COLLECTION).items():
            if not isinstance(intent, Mapping):
                continue
            if str(intent.get("target_id") or TARGET_PROJECT_ID) != TARGET_PROJECT_ID:
                continue
            if str(intent.get("status") or "") == "active":
                active.append(str(intent.get("run_id") or run_id))
        return active

    def _reconcile_wb_core_auto_intents(self) -> None:
        intents = self.store._read_collection(WB_CORE_AUTO_INTENTS_COLLECTION)
        runs = self._read_mcp_runs()
        changed = False
        for run_id, raw in list(intents.items()):
            if not isinstance(raw, Mapping) or str(raw.get("status") or "") != "active":
                continue
            run = runs.get(str(run_id))
            if not isinstance(run, Mapping):
                intent = dict(raw)
                intent.update(
                    {
                        "status": "stale_lost_run",
                        "terminal_run_status": "stale_lost_run",
                        "release_reason": "auto-production intent had no matching mcp run state during reconciliation",
                        "released_at": _now_utc(),
                        "updated_at": _now_utc(),
                    }
                )
                intents[str(run_id)] = _json_ready(intent)
                changed = True
                continue
            if _auto_task_run_is_terminal(run):
                intent = dict(raw)
                intent.update(
                    {
                        "status": "released",
                        "terminal_run_status": str(run.get("status") or "terminal"),
                        "release_reason": str(run.get("blocker") or run.get("separate_deploy_reason") or ""),
                        "released_at": _now_utc(),
                        "updated_at": _now_utc(),
                    }
                )
                intents[str(run_id)] = _json_ready(intent)
                changed = True
        if changed:
            self.store._write_collection(WB_CORE_AUTO_INTENTS_COLLECTION, intents)

    def _deferred_wb_core_candidates(self) -> list[str]:
        deferred: list[str] = []
        blocking_child_ids: set[str] = set()
        for run_id, run in self._read_mcp_runs().items():
            if not isinstance(run, Mapping) or str(run.get("target_id") or "") != TARGET_PROJECT_ID:
                continue
            run_key = str(run.get("run_id") or run_id)
            if str(run.get("status") or "") == "ready_for_separate_deploy" or run.get("deferred_for_separate_deploy"):
                deferred.append(run_key)
                blocking_child_ids.add(run_key)
        try:
            for task in self.store._parallel_ledger().list_tasks(target_id=TARGET_PROJECT_ID):
                if task.status in {
                    "verifier_passed",
                    "promotion_queued",
                    "auto_promoting_first",
                    "production_lane_running",
                    "refresh_required",
                    "frozen_base_stale",
                }:
                    deferred.append(str(task.task_id))
                    blocking_child_ids.add(str(task.task_id))
        except Exception:
            raise
        for group_id, raw in self.store._read_collection("parallel_promotion_groups").items():
            if not isinstance(raw, Mapping) or str(raw.get("target_id") or "") != TARGET_PROJECT_ID:
                continue
            child_ids = {
                str(item)
                for key in ("deferred_task_ids", "refresh_required_ids", "conflicted_ids", "accepted_task_ids", "planned_order")
                for item in (raw.get(key) or [])
                if str(item or "")
            }
            if not child_ids.intersection(blocking_child_ids):
                continue
            if raw.get("deferred_task_ids") or raw.get("refresh_required_ids") or raw.get("conflicted_ids") or str(raw.get("status") or "") in {"partially_deployed", "ready_for_separate_deploy"}:
                deferred.append(str(raw.get("group_id") or group_id))
        return list(dict.fromkeys(item for item in deferred if item))

    def _record_wb_core_auto_intent(self, run_id: str, *, decision: Mapping[str, Any], status: str) -> None:
        intents = self.store._read_collection(WB_CORE_AUTO_INTENTS_COLLECTION)
        intents[run_id] = _json_ready(
            {
                "run_id": run_id,
                "target_id": TARGET_PROJECT_ID,
                "status": status,
                "route": decision.get("route"),
                "auto_production_allowed": decision.get("auto_production_allowed"),
                "busy_reasons": decision.get("busy_reasons") or [],
                "created_at": _now_utc(),
                "updated_at": _now_utc(),
            }
        )
        self.store._write_collection(WB_CORE_AUTO_INTENTS_COLLECTION, intents)

    def _release_wb_core_auto_intent(self, run_id: str, *, status: str, reason: str = "") -> None:
        intents = self.store._read_collection(WB_CORE_AUTO_INTENTS_COLLECTION)
        intent = dict(intents.get(run_id) or {})
        if not intent:
            return
        intent.update(
            {
                "status": "released",
                "terminal_run_status": status,
                "release_reason": _safe_text(reason, 500),
                "released_at": _now_utc(),
                "updated_at": _now_utc(),
            }
        )
        intents[run_id] = _json_ready(intent)
        self.store._write_collection(WB_CORE_AUTO_INTENTS_COLLECTION, intents)

    def _wait_mcp_run(self, run_id: str, *, max_wait_seconds: int) -> bool:
        deadline = time.time() + max_wait_seconds
        while time.time() < deadline:
            run = self._read_mcp_runs().get(run_id) or {}
            if _auto_task_run_is_terminal(run):
                return True
            time.sleep(0.1)
        return False

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
            self._update_mcp_run_after_control_plane_exception(run_id, exc, default_stage="production_control_error")

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
            self._update_mcp_run_after_control_plane_exception(run_id, exc, default_stage="managed_control_error")

    def _update_mcp_run_after_control_plane_exception(self, run_id: str, exc: Exception, *, default_stage: str) -> None:
        blocker = _safe_exception_text(exc)
        run = self._read_mcp_runs().get(run_id) or {}
        run_dir_raw = run.get("run_dir")
        run_dir = Path(str(run_dir_raw)).resolve() if run_dir_raw else self.store.layout.run_layout(run_id).run_dir.resolve()
        reconciliation = codex_run_reconciliation(
            run_dir,
            declared_status="failed",
            current_stage=default_stage,
            blocker=blocker,
        )
        status = "failed"
        stage = default_stage
        message = "Control-plane observer failed."
        if reconciliation.get("effective_activity") == "running":
            status = "control_error_codex_running"
            stage = "control_error_codex_running"
            message = "DevControl observer failed, but Codex still appears active."
        elif reconciliation.get("handoff_present_verifier_missing_due_to_control_error"):
            status = "needs_verifier_after_control_error"
            stage = "needs_verifier_after_control_error"
            message = "Handoff exists, but verifier did not run because of a DevControl control error."
        self._update_mcp_run(
            run_id,
            status=status,
            current_stage=stage,
            blocker=blocker,
            control_plane_observer_status="error",
            control_plane_observer_blocker=blocker,
            effective_status=reconciliation.get("effective_status"),
            effective_activity=reconciliation.get("effective_activity"),
            is_inconsistent=reconciliation.get("is_inconsistent"),
            operator_label=reconciliation.get("operator_label") or "ошибка DevControl",
            message=message,
        )

    def _resume_deploy_worker(self, run_id: str) -> None:
        try:
            self._update_mcp_run(run_id, status="running", current_stage="resume_preflight")
            result = execute_wb_core_resume_deploy(run_id=run_id, state_dir=self.store.state_dir, execute=True)
            payload = target_production_resume_result_to_dict(result)
            self._update_mcp_run(
                run_id,
                status="completed" if result.status == "post_deploy_passed" else "blocked",
                current_stage=result.status,
                target_pr_url=payload.get("target_pr_url"),
                target_pr_number=payload.get("target_pr_number"),
                merge_commit=payload.get("merge_commit"),
                deploy_status=payload.get("deploy_status"),
                public_verify_status=payload.get("public_verify_status"),
                rollback_plan_path=payload.get("rollback_plan_path"),
                blocker="; ".join(payload.get("blockers") or []),
                message="Resume deploy finished." if result.status == "post_deploy_passed" else "Resume deploy blocked.",
            )
        except Exception as exc:
            self._update_mcp_run(run_id, status="failed", current_stage="resume_failed", blocker=_safe_exception_text(exc))

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
        append_terminal_output(
            run_layout.run_dir,
            "\x1b[1;32mCodex fake managed clone completed.\x1b[0m\n"
            "spinner: cloning\rspinner: done\n"
            "\x1b]0;unsafe-title\x07unsafe title control stripped\n",
        )
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
            "human_gates": ["MCP OAuth dcp.write authorization", "ChatGPT tool confirmation for write actions"],
            "explicit_policy_note": f"MCP Stage 1 {execution_mode}; production mutation only through explicit wb-core production lane gates.",
            "execution_mode": execution_mode,
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
        append_terminal_output(
            layout.run_dir,
            "\x1b[1;33mMCP production-lane dry-run.\x1b[0m\n"
            "No Codex, PR, merge, SSH or WebCore deploy executed.\n",
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
        run_id = str(run["run_id"])
        urls = _run_live_urls(_public_origin(), run_id)
        run.setdefault("live_url", urls["live_url"])
        run.setdefault("watch_url", urls["watch_url"])
        self._record_live_transition(run_id, run)
        with self.store._jobs_lock:
            runs = self._read_mcp_runs()
            runs[run_id] = _json_ready(run)
            self.store._write_collection(MCP_RUNS_COLLECTION, runs)
        return run

    def _update_mcp_run(self, run_id: str, **updates: Any) -> None:
        with self.store._jobs_lock:
            runs = self._read_mcp_runs()
            run = dict(runs.get(run_id) or {"run_id": run_id, "created_at": _now_utc(), "source": MCP_SOURCE})
            run.update(_json_ready(updates))
            run["updated_at"] = _now_utc()
            if not run.get("live_url") or not run.get("watch_url"):
                run.update(_run_live_urls(_public_origin(), run_id))
            runs[run_id] = run
            self.store._write_collection(MCP_RUNS_COLLECTION, runs)
        if "status" in updates or "current_stage" in updates or "blocker" in updates:
            self._record_live_transition(run_id, run)

    def _record_live_transition(self, run_id: str, run: Mapping[str, Any]) -> None:
        try:
            layout = self.store.layout.run_layout(run_id)
            layout.ensure_dirs()
            stage = str(run.get("current_stage") or run.get("status") or "queued")
            status = str(run.get("status") or stage)
            level = _live_level(status)
            title = _live_title(stage, status)
            detail = _optional_str(run.get("blocker")) or _optional_str(run.get("message"))
            append_live_event(
                layout.run_dir,
                stage=stage,
                title=title,
                status=status,
                level=level,
                detail=detail,
                source="mcp",
                run_id=run_id,
                target_id=_optional_str(run.get("target_id")),
            )
            append_terminal_output(layout.run_dir, f"{_sgr_for_level(level)}{title}\x1b[0m\n")
        except Exception:
            return

    def _read_mcp_runs(self) -> dict[str, Any]:
        try:
            return self.store._read_collection(MCP_RUNS_COLLECTION)
        except Exception:
            return {}

    def _real_job_live_summary(self, run_id: str) -> dict[str, Any] | None:
        try:
            job = self.store.get_real_run_job(run_id)
        except Exception:
            return None
        try:
            summary = self.store._live_summary_from_real_job(job)  # type: ignore[attr-defined]
            self.store._decorate_live_summary_observability(summary)  # type: ignore[attr-defined]
        except Exception:
            summary = {
                "run_id": str(job.get("run_id") or job.get("id") or run_id),
                "target_id": job.get("target_project_id"),
                "target": job.get("target_project_id"),
                "run_type": "managed",
                "execution_mode": "managed_clone_codex",
                "status": job.get("status"),
                "current_stage": job.get("status"),
                "created_at": job.get("created_at"),
                "updated_at": job.get("updated_at"),
                "blocker": job.get("blocker_reason"),
                "changed_files": job.get("changed_files", []),
                "verifier_status": job.get("verifier_status"),
                "live_url": live_url(_public_origin(), None),
                "watch_url": live_url(_public_origin(), str(job.get("run_id") or job.get("id") or run_id)),
                "active": not _auto_task_run_is_terminal(job),
            }
            decorate_operator_lifecycle(summary)
        summary.setdefault("real_job_id", job.get("id") or run_id)
        summary.setdefault("run_id", str(job.get("run_id") or job.get("id") or run_id))
        summary.setdefault("target_id", job.get("target_project_id"))
        summary.setdefault("target", job.get("target_project_id"))
        summary.setdefault("execution_mode", "managed_clone_codex")
        summary.setdefault("run_type", "managed")
        summary.setdefault("live_url", live_url(_public_origin(), None))
        summary.setdefault("watch_url", live_url(_public_origin(), str(summary.get("run_id") or run_id)))
        return self._apply_promotion_group_child_override(summary)

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
        resume_result = _read_json_if_exists(run_dir / "artifacts" / "production_lane" / "resume_deploy_result.json")
        latest_result = resume_result or production_result
        if latest_result:
            enriched.setdefault("target_pr_url", latest_result.get("target_pr_url"))
            enriched.setdefault("merge_commit", latest_result.get("merge_commit"))
            enriched.setdefault("deploy_status", latest_result.get("deploy_status"))
            enriched.setdefault("public_verify_status", latest_result.get("public_verify_status"))
            enriched.setdefault("rollback_plan_path", latest_result.get("rollback_plan_path"))
        enriched["artifact_status"] = {
            "prompt": (run_dir / "artifacts" / "prompt.md").exists(),
            "handoff": (run_dir / "artifacts" / "handoff.md").exists(),
            "diff": (run_dir / "artifacts" / "diff.patch").exists(),
            "verifier": (run_dir / "verifier" / "verifier.json").exists(),
            "production_lane_report": (run_dir / "artifacts" / "production_lane" / "production_lane_result.json").exists()
            or (run_dir / "artifacts" / "production_lane" / "mcp_production_lane_report.json").exists(),
            "resume_deploy_report": (run_dir / "artifacts" / "production_lane" / "resume_deploy_report.json").exists(),
            "rollback_plan": bool(self._rollback_plan_for_run_dir(run_dir)),
            "sprint_report": (run_dir / "artifacts" / "sprint" / "sprint_report.json").exists(),
            "sprint_handoff": (run_dir / "artifacts" / "sprint" / "sprint_handoff.md").exists(),
        }
        reconciliation = codex_run_reconciliation(
            run_dir,
            declared_status=enriched.get("status"),
            current_stage=enriched.get("current_stage"),
            blocker=enriched.get("blocker"),
        )
        enriched["run_state_reconciliation"] = reconciliation
        enriched["effective_status"] = reconciliation.get("effective_status")
        enriched["effective_activity"] = reconciliation.get("effective_activity")
        enriched["is_inconsistent"] = reconciliation.get("is_inconsistent")
        enriched["operator_label"] = reconciliation.get("operator_label")
        enriched["control_plane_observer_status"] = reconciliation.get("control_plane_observer_status")
        enriched["control_plane_observer_blocker"] = reconciliation.get("control_plane_observer_blocker")
        return enriched

    def _status_payload_from_enriched_run(self, run_id: str, enriched: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "status": enriched.get("status"),
            "run_id": enriched.get("run_id") or run_id,
            "real_job_id": enriched.get("real_job_id"),
            "target": enriched.get("target_id"),
            "run_type": enriched.get("run_type") or _run_type_from_mode(enriched.get("execution_mode")),
            "execution_mode": enriched.get("execution_mode"),
            "current_stage": enriched.get("current_stage"),
            "current_step_index": enriched.get("current_step_index"),
            "child_run_ids": enriched.get("child_run_ids", []),
            "curator_decisions": enriched.get("curator_decisions", []),
            "started_via_tool": enriched.get("started_via_tool"),
            "compatibility_bridge": enriched.get("compatibility_bridge"),
            "created_at": enriched.get("created_at"),
            "updated_at": enriched.get("updated_at"),
            "blockers": _blockers(enriched),
            "verifier_status": enriched.get("verifier_status"),
            "changed_files": enriched.get("changed_files", []),
            "pr_url": enriched.get("target_pr_url"),
            "deploy_status": enriched.get("deploy_status"),
            "lock_wait": enriched.get("lock_wait"),
            "live_url": enriched.get("live_url") or live_url(_public_origin(), None),
            "watch_url": enriched.get("watch_url") or live_url(_public_origin(), run_id),
            "run_dir": enriched.get("run_dir"),
            "artifact_status": enriched.get("artifact_status"),
            "effective_status": enriched.get("effective_status"),
            "effective_activity": enriched.get("effective_activity"),
            "is_inconsistent": enriched.get("is_inconsistent"),
            "operator_label": enriched.get("operator_label"),
            "control_plane_observer_status": enriched.get("control_plane_observer_status"),
            "control_plane_observer_blocker": enriched.get("control_plane_observer_blocker"),
            "run_state_reconciliation": enriched.get("run_state_reconciliation"),
            "operator_lifecycle_status": enriched.get("operator_lifecycle_status"),
            "operator_lifecycle_label": enriched.get("operator_lifecycle_label"),
            "operator_lifecycle_tone": enriched.get("operator_lifecycle_tone"),
            "promotion_selectable": enriched.get("promotion_selectable"),
            "promotion_selection_reason": enriched.get("promotion_selection_reason"),
            "selected_promotion_group_id": enriched.get("selected_promotion_group_id"),
            "group_id": enriched.get("group_id"),
            "promotion_group_status": enriched.get("promotion_group_status"),
            "promotion_group_child_status": enriched.get("promotion_group_child_status"),
            "refresh_required": enriched.get("refresh_required"),
            "conflict_detected": enriched.get("conflict_detected"),
            "conflict_files": enriched.get("conflict_files", []),
            "recommended_action": enriched.get("recommended_action"),
            "refresh_plan_id": enriched.get("refresh_plan_id"),
            "refresh_task_id": enriched.get("refresh_task_id"),
            "refresh_run_id": enriched.get("refresh_run_id"),
            "refreshed_candidate_id": enriched.get("refreshed_candidate_id"),
            "route": enriched.get("route") or enriched.get("arbitration_route"),
            "arbitration_route": enriched.get("arbitration_route") or enriched.get("route"),
            "auto_production_allowed": enriched.get("auto_production_allowed"),
            "deferred_for_separate_deploy": enriched.get("deferred_for_separate_deploy"),
            "separate_deploy_reason": enriched.get("separate_deploy_reason"),
            "merge_deploy_skipped_blocker": enriched.get("merge_deploy_skipped_blocker"),
            "branch_pr_created": enriched.get("branch_pr_created"),
            "production_lane_started": enriched.get("production_lane_started"),
            "real_production_lane_started": enriched.get("real_production_lane_started"),
            "arbitration_decision": enriched.get("arbitration_decision"),
        }

    def _apply_promotion_group_child_override(self, run: Mapping[str, Any]) -> dict[str, Any]:
        enriched = dict(run)
        run_id = str(enriched.get("run_id") or "")
        task_id = str(enriched.get("task_id") or "")
        if not run_id and not task_id:
            return enriched
        try:
            overrides = self.store._promotion_group_child_overrides()  # type: ignore[attr-defined]
        except Exception:
            return enriched
        override = overrides.get(run_id) or overrides.get(task_id)
        if not isinstance(override, Mapping):
            return enriched
        enriched.update(_sanitize(dict(override)))
        if not bool(enriched.get("active")) and str(enriched.get("effective_activity") or "") == "running":
            enriched["effective_activity"] = "stopped"
        status = str(enriched.get("status") or "")
        if status in TERMINAL_STATUSES or status in {"conflict_detected", "partially_deployed", "ready_for_separate_deploy", "refresh_required", "needs_rework", "blocked_by_conflict"}:
            enriched["effective_activity"] = "stopped"
            enriched["active"] = False
        decorate_operator_lifecycle(enriched)
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
            "environment_parity": run_dir / "artifacts" / "environment_parity.json",
            "logs": run_dir / "logs" / "codex.log",
            "terminal_log": run_dir / "logs" / "terminal.log",
            "timeline": run_dir / "logs" / "timeline.jsonl",
            "verifier": run_dir / "verifier" / "verifier.json",
            "production_lane_report": run_dir / "artifacts" / "production_lane" / "production_lane_result.json",
            "mcp_production_lane_report": run_dir / "artifacts" / "production_lane" / "mcp_production_lane_report.json",
            "resume_preflight": run_dir / "artifacts" / "production_lane" / "resume_preflight" / "resume_deploy_preflight.json",
            "backup_result": run_dir / "artifacts" / "production_lane" / "backup_result.json",
            "deploy_result": run_dir / "artifacts" / "production_lane" / "deploy_result.json",
            "probe_result": run_dir / "artifacts" / "production_lane" / "probe_result.json",
            "resume_deploy_report": run_dir / "artifacts" / "production_lane" / "resume_deploy_report.json",
            "resume_deploy_result": run_dir / "artifacts" / "production_lane" / "resume_deploy_result.json",
            "rollback_plan": run_dir / "artifacts" / "production_lane" / "rollback_plan.json",
            "sprint_prompt": run_dir / "artifacts" / "sprint" / "sprint_prompt.md",
            "curator_decisions": run_dir / "artifacts" / "sprint" / "curator_decisions.jsonl",
            "curator_transcript": run_dir / "artifacts" / "sprint" / "curator_transcript.md",
            "child_runs": run_dir / "artifacts" / "sprint" / "child_runs.json",
            "sprint_report": run_dir / "artifacts" / "sprint" / "sprint_report.json",
            "sprint_handoff": run_dir / "artifacts" / "sprint" / "sprint_handoff.md",
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

    def _target_docs_config(self, target_id: str) -> Any:
        if target_id != TARGET_PROJECT_ID:
            raise ValueError("target docs MCP tools currently allow only target_id=wb-core")
        return self.store._target_config_by_id(target_id)

    def _target_docs_readiness(self) -> dict[str, Any]:
        try:
            target_config_dir = getattr(self.store, "target_config_dir", None)
            configs = load_target_project_configs(Path(target_config_dir)) if target_config_dir else ()
            return build_target_docs_readiness(configs, self.store.state_dir)
        except Exception as exc:
            return {
                "status": "blocked",
                "access_mode": "oauth_session_required",
                "read_only": True,
                "tools": list(TARGET_DOC_TOOL_NAMES),
                "blocker": _safe_exception_text(exc),
            }


class _NullConfig:
    host = "127.0.0.1"
    port = 0
    runtime_profile = "local"
    bind_policy = "loopback_only"


def build_mcp_context(
    headers: Mapping[str, str],
    *,
    client: str,
    env: Mapping[str, str] | None = None,
    oauth_provider: Any | None = None,
) -> MCPRequestContext:
    authorization = _header(headers, "Authorization")
    auth_status = get_mcp_auth_status(env=env)
    caller = _header(headers, "X-Forwarded-For") or client
    base_url = external_base_url(headers)
    token = bearer_token_from_header(authorization)
    oauth_verification = oauth_provider.verify_access_token(token or "", base_url=base_url) if oauth_provider is not None else None
    oauth_authenticated = bool(oauth_verification and oauth_verification.active)
    legacy_authenticated = verify_mcp_bearer_token(authorization, env=env)
    auth_type = "oauth2" if oauth_authenticated else ("legacy_bearer" if legacy_authenticated else None)
    scopes = tuple(oauth_verification.scopes) if oauth_verification and oauth_verification.active else ()
    auth_failure_code = None
    auth_failure_reason = None
    if not oauth_authenticated and not legacy_authenticated:
        if authorization and token is None:
            auth_failure_code = "unsupported_authorization_scheme"
            auth_failure_reason = "Authorization header is present but is not a Bearer token."
        elif oauth_verification and oauth_verification.reason_code:
            auth_failure_code = oauth_verification.reason_code
            auth_failure_reason = oauth_verification.blocker
        else:
            auth_failure_code = "unauthenticated_call"
            auth_failure_reason = "OAuth bearer token is missing; authenticate with dcp.write."
    return MCPRequestContext(
        authorization=authorization,
        caller=_truncate(caller, 120),
        user_agent=_header(headers, "User-Agent"),
        authenticated=oauth_authenticated or legacy_authenticated,
        auth_configured=bool(auth_status.get("configured")) or oauth_provider is not None,
        auth_type=auth_type,
        auth_scopes=scopes,
        base_url=base_url,
        auth_failure_code=auth_failure_code,
        auth_failure_reason=auth_failure_reason,
    )


def _tool_result(payload: Mapping[str, Any], *, is_error: bool = False) -> dict[str, Any]:
    raw = dict(payload)
    meta = raw.pop("_mcp_meta", None)
    sanitized = _sanitize(raw)
    result = {
        "content": [{"type": "text", "text": json.dumps(sanitized, ensure_ascii=False, sort_keys=True)}],
        "structuredContent": sanitized,
        "isError": is_error,
    }
    if isinstance(meta, Mapping) and meta:
        result["_meta"] = _sanitize_tool_meta(dict(meta))
    return result


def _json_rpc_error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": _safe_text(message, 500)}}


def _sanitize_tool_meta(meta: Mapping[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in meta.items():
        text_key = str(key)
        if text_key == "mcp/www_authenticate":
            sanitized[text_key] = str(value or "")
        else:
            sanitized[text_key] = _sanitize(value)
    return sanitized


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


def _has_sprint_bridge_marker(task_text: str) -> bool:
    return task_text.startswith(SPRINT_BRIDGE_MARKER)


def _sprint_internal_runtime_enabled() -> bool:
    return str(os.environ.get(SPRINT_INTERNAL_ENABLE_ENV) or "").strip().lower() in {"1", "true", "yes"}


def _frozen_sprint_result(
    *,
    target_id: str,
    bridge_tool: str | None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "status": "blocked",
        "target_id": target_id,
        "tool": "start_sprint",
        "canonical_tool": "start_sprint",
        "blocker": SPRINT_FROZEN_BLOCKER,
        "frozen": True,
        "operator_visible": False,
        "accepted": False,
        "run_id": None,
        "fallback_to_sprint": False,
        "fallback_to_managed_clone_only": False,
        "direct_tool": "start_wb_core_auto_task",
    }
    if bridge_tool:
        payload["compatibility_bridge"] = bridge_tool
        payload["started_via_tool"] = bridge_tool
    if extra:
        payload.update(dict(extra))
    return payload


def _parse_sprint_bridge_payload(task_text: str) -> dict[str, Any]:
    raw_payload = task_text[len(SPRINT_BRIDGE_MARKER) :].strip()
    if not raw_payload:
        return {"status": "blocked", "blocker": "Sprint compatibility payload JSON is required after DEVCONTROL_START_SPRINT_V1."}
    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError:
        return {"status": "blocked", "blocker": "Sprint compatibility payload must be valid JSON."}
    if not isinstance(payload, Mapping):
        return {"status": "blocked", "blocker": "Sprint compatibility payload must be a JSON object."}
    allowed_keys = {"sprint_text", "max_steps", "max_retries_per_step", "execution_mode"}
    unexpected = sorted(str(key) for key in set(payload) - allowed_keys)
    if unexpected:
        return {"status": "blocked", "blocker": f"Sprint compatibility payload has unsupported keys: {', '.join(unexpected)}."}
    sprint_text = str(payload.get("sprint_text") or "").strip()
    if not sprint_text:
        return {"status": "blocked", "blocker": "Sprint compatibility payload requires non-empty sprint_text."}
    parsed: dict[str, Any] = {
        "sprint_text": sprint_text,
        "execution_mode": str(payload.get("execution_mode") or "managed_clone_only").strip() or "managed_clone_only",
    }
    for name, default, minimum, maximum in (
        ("max_steps", 2, 1, 3),
        ("max_retries_per_step", 1, 0, 1),
    ):
        parsed_int = _parse_sprint_bridge_int(payload.get(name), name=name, default=default, minimum=minimum, maximum=maximum)
        if isinstance(parsed_int, Mapping):
            return parsed_int
        parsed[name] = parsed_int
    return {"status": "ok", "payload": parsed}


def _parse_sprint_bridge_int(value: Any, *, name: str, default: int, minimum: int, maximum: int) -> int | dict[str, str]:
    if value is None:
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return {"status": "blocked", "blocker": f"Sprint compatibility payload field {name} must be an integer."}
    if parsed < minimum or parsed > maximum:
        return {"status": "blocked", "blocker": f"Sprint compatibility payload field {name} must be between {minimum} and {maximum}."}
    return parsed


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


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


def _public_origin() -> str:
    return str(os.environ.get("DEV_CONTROL_PLANE_PUBLIC_ORIGIN") or "https://devcontrol.pro").rstrip("/")


def _run_live_urls(base_url: str | None, run_id: str) -> dict[str, str]:
    origin = str(base_url or _public_origin()).rstrip("/")
    return {"live_url": live_url(origin, None), "watch_url": live_url(origin, run_id)}


def _live_level(status: str) -> str:
    if status in {"completed", "completed_dry_run", "passed", "verifier_passed"}:
        return "success"
    if status in {"failed", "blocked"}:
        return "error"
    if status in {"waiting_for_target_lock", "decision_only"}:
        return "warning"
    return "info"


def _live_title(stage: str, status: str) -> str:
    mapping = {
        "queued": "Queued.",
        "managed_clone_prepare": "Preparing managed clone.",
        "preparing": "Preparing run.",
        "running_codex": "Codex is running.",
        "verifying": "Verifier is running.",
        "verifier": "Verifier finished.",
        "production_lane": "Production lane stage reached.",
        "resume_queued": "Resume deploy queued.",
        "resume_preflight": "Resume deploy preflight running.",
        "resume_dry_run_ready": "Resume deploy dry-run ready.",
        "resume_confirmation_required": "Resume deploy confirmation required.",
        "post_deploy_passed": "Resume deploy passed.",
        "rollback_required": "Resume deploy needs rollback decision.",
        "resume_failed": "Resume deploy failed.",
        "dry_run_complete": "Dry-run completed.",
        "waiting_for_target_lock": "Waiting for target production lock.",
        "blocked": "Run blocked.",
        "failed": "Run failed.",
    }
    return mapping.get(stage) or mapping.get(status) or f"Stage: {stage or status}"


def _sgr_for_level(level: str) -> str:
    return {"success": "\x1b[32m", "warning": "\x1b[33m", "error": "\x1b[31m"}.get(level, "\x1b[36m")


def _title_from_task_text(task_text: str) -> str:
    first = next((line.strip() for line in task_text.splitlines() if line.strip()), "MCP task")
    return _truncate(first, 100)


def _compact_mcp_run(run: Mapping[str, Any]) -> dict[str, Any]:
    return _sanitize(
        {
            "run_id": run.get("run_id"),
            "target": run.get("target_id"),
            "target_id": run.get("target_id"),
            "run_type": run.get("run_type") or _run_type_from_mode(run.get("execution_mode")),
            "execution_mode": run.get("execution_mode"),
            "route": run.get("route") or run.get("arbitration_route"),
            "arbitration_route": run.get("arbitration_route") or run.get("route"),
            "current_stage": run.get("current_stage"),
            "current_step_index": run.get("current_step_index"),
            "status": run.get("status"),
            "effective_status": run.get("effective_status"),
            "effective_activity": run.get("effective_activity"),
            "effective_recency_at": run.get("effective_recency_at") or (run.get("run_state_reconciliation") or {}).get("effective_recency_at")
            if isinstance(run.get("run_state_reconciliation"), Mapping)
            else run.get("effective_recency_at"),
            "is_inconsistent": run.get("is_inconsistent"),
            "operator_label": run.get("operator_label"),
            "operator_lifecycle_status": run.get("operator_lifecycle_status"),
            "operator_lifecycle_label": run.get("operator_lifecycle_label"),
            "operator_lifecycle_tone": run.get("operator_lifecycle_tone"),
            "promotion_selectable": run.get("promotion_selectable"),
            "refresh_required": run.get("refresh_required"),
            "deferred_for_separate_deploy": run.get("deferred_for_separate_deploy"),
            "auto_production_allowed": run.get("auto_production_allowed"),
            "separate_deploy_reason": run.get("separate_deploy_reason"),
            "branch_pr_created": run.get("branch_pr_created"),
            "conflict_detected": run.get("conflict_detected"),
            "conflict_files": run.get("conflict_files", []),
            "separate_deploy_reason": run.get("separate_deploy_reason"),
            "recommended_action": run.get("recommended_action"),
            "selected_promotion_group_id": run.get("selected_promotion_group_id"),
            "refresh_run_id": run.get("refresh_run_id"),
            "control_plane_observer_status": run.get("control_plane_observer_status"),
            "started_via_tool": run.get("started_via_tool"),
            "compatibility_bridge": run.get("compatibility_bridge"),
            "created_at": run.get("created_at"),
            "updated_at": run.get("updated_at"),
            "lock_wait": run.get("lock_wait"),
            "blocker_summary": run.get("blocker"),
            "child_run_ids": run.get("child_run_ids", []),
            "task_text_excerpt": run.get("task_text_excerpt"),
            "live_url": run.get("live_url") or live_url(_public_origin(), None),
            "watch_url": run.get("watch_url") or live_url(_public_origin(), str(run.get("run_id") or "")),
        }
    )


def _run_type_from_mode(mode: Any) -> str:
    value = str(mode or "")
    if "auto" in value:
        return "auto_task"
    if "sprint" in value:
        return "sprint"
    if "production" in value:
        return "production"
    if "managed" in value:
        return "managed"
    return "run"


def _compact_decisions(decisions: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for decision in decisions[-8:]:
        compact.append(
            _sanitize(
                {
                    "timestamp": decision.get("timestamp"),
                    "phase": decision.get("phase"),
                    "decision": decision.get("decision"),
                    "reason": decision.get("reason"),
                    "step_index": decision.get("step_index"),
                    "retry": decision.get("retry"),
                    "child_run_id": decision.get("child_run_id"),
                    "verifier_status": decision.get("verifier_status"),
                    "blocker": decision.get("blocker"),
                }
            )
        )
    return compact


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
    deployed_commit = str(os.environ.get("DEV_CONTROL_PLANE_GIT_COMMIT") or "").strip()
    deployed_branch = str(os.environ.get("DEV_CONTROL_PLANE_GIT_BRANCH") or "").strip()
    if not deployed_commit:
        deployed_commit_path = root / ".deploy-commit"
        if deployed_commit_path.exists():
            deployed_commit_lines = deployed_commit_path.read_text(encoding="utf-8").strip().splitlines()
            deployed_commit = deployed_commit_lines[0].strip() if deployed_commit_lines else ""
    if not deployed_branch:
        deployed_branch_path = root / ".deploy-branch"
        if deployed_branch_path.exists():
            deployed_branch_lines = deployed_branch_path.read_text(encoding="utf-8").strip().splitlines()
            deployed_branch = deployed_branch_lines[0].strip() if deployed_branch_lines else ""
    if deployed_commit:
        return {
            "commit": deployed_commit,
            "short": deployed_commit[:12],
            "branch": deployed_branch or None,
            "source": "deploy_metadata",
        }

    def git(*args: str) -> str | None:
        completed = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            return None
        return completed.stdout.strip()

    commit = git("rev-parse", "HEAD")
    return {"commit": commit, "short": commit[:12] if commit else None, "branch": git("branch", "--show-current"), "source": "git"}


def _codex_bin_for_execution() -> str | None:
    configured = str(os.environ.get("DEV_CONTROL_PLANE_CODEX_BIN") or "").strip()
    if configured:
        return configured
    completed = subprocess.run(["sh", "-lc", "command -v codex"], capture_output=True, text=True, check=False)
    return completed.stdout.strip() or None


def _fake_runs_enabled() -> bool:
    return str(os.environ.get(MCP_FAKE_RUNS_ENV) or "").strip() == "1"


def _auto_task_stub_enabled() -> bool:
    return str(os.environ.get("DEV_CONTROL_PLANE_WB_CORE_AUTO_TASK_MODE") or "").strip().lower() in {"stub", "fake"}


def _auto_task_stub_delay_seconds() -> float:
    try:
        return max(0.0, min(5.0, float(os.environ.get("DEV_CONTROL_PLANE_WB_CORE_AUTO_TASK_STUB_DELAY_SECONDS") or "0")))
    except ValueError:
        return 0.0


def _auto_task_stub_verifier_status() -> str:
    value = str(os.environ.get("DEV_CONTROL_PLANE_WB_CORE_AUTO_TASK_STUB_VERIFIER_STATUS") or "passed").strip().lower()
    return "failed" if value in {"failed", "blocked", "fail"} else "passed"


def _auto_task_run_is_terminal(run: Mapping[str, Any]) -> bool:
    status = str(run.get("status") or "")
    if status in TERMINAL_STATUSES:
        return True
    if status in {"deploy_passed", "post_deploy_passed"}:
        return True
    if run.get("active") is False:
        return True
    return False


def _chatgpt_auth_blocker(auth: Mapping[str, Any]) -> str | None:
    if auth.get("enabled"):
        return None
    return "OAuth-compatible write auth is not enabled; write tools remain hidden from public discovery and fail closed."


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
    if path.name in {"codex.log", "executor.log", "terminal.log"}:
        return sanitize_terminal_text(text), truncated
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


def _tool_names(
    *,
    public: bool | None = None,
    auth_policy: str | None = None,
    kind: str | None = None,
    include_internal: bool = False,
) -> tuple[str, ...]:
    names: list[str] = []
    for name, policy in MCP_TOOL_REGISTRY.items():
        if not include_internal and policy.get("operator_visible") is False:
            continue
        if public is True and not bool(policy.get("public_visible")):
            continue
        if auth_policy and policy.get("auth_policy") != auth_policy:
            continue
        if kind and policy.get("kind") != kind:
            continue
        names.append(name)
    return tuple(names)


def _tool_registry_status(*, public: bool) -> dict[str, Any]:
    definitions = {str(tool.get("name") or "") for tool in TOOL_DEFINITIONS}
    registry_names = set(MCP_TOOL_REGISTRY)
    return {
        "authoritative": True,
        "registry_tool_count": len(MCP_TOOL_REGISTRY),
        "definition_tool_count": len(TOOL_DEFINITIONS),
        "operator_tool_count": len(_tool_names()),
        "exported_tool_names": sorted(_tool_names(public=public)),
        "public_tool_names": sorted(_tool_names(auth_policy=TOOL_AUTH_PUBLIC_NOAUTH)),
        "oauth_required_read_tools": sorted(_tool_names(auth_policy=TOOL_AUTH_OAUTH_REQUIRED, kind=TOOL_KIND_READ)),
        "oauth_required_write_tools": sorted(_tool_names(auth_policy=TOOL_AUTH_OAUTH_REQUIRED, kind=TOOL_KIND_WRITE)),
        "internal_frozen_tools": sorted(
            name for name, policy in MCP_TOOL_REGISTRY.items() if bool(policy.get("frozen"))
        ),
        "registry_definition_parity": registry_names == definitions,
        "missing_definitions": sorted(registry_names - definitions),
        "unregistered_definitions": sorted(definitions - registry_names),
    }


def _with_tool_metadata(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for tool in tools:
        name = str(tool.get("name") or "")
        policy = MCP_TOOL_REGISTRY.get(name)
        if not policy:
            raise RuntimeError(f"MCP tool definition is not registered: {name}")
        is_read_only = policy["kind"] == TOOL_KIND_READ
        auth_policy = policy["auth_policy"]
        item = dict(tool)
        annotations = dict(item.get("annotations") or {})
        annotations["readOnlyHint"] = is_read_only
        annotations.setdefault("destructiveHint", False if is_read_only or name == "start_managed_clone_run" else True)
        annotations.setdefault("openWorldHint", False if is_read_only else True)
        annotations.setdefault("idempotentHint", False)
        item["annotations"] = annotations

        meta = dict(item.get("_meta") or {})
        if auth_policy == TOOL_AUTH_PUBLIC_NOAUTH:
            item["securitySchemes"] = NOAUTH_SECURITY_SCHEMES
            meta["securitySchemes"] = NOAUTH_SECURITY_SCHEMES
            meta["dev-control-plane/exposure"] = "public_read_only"
        else:
            scopes = [str(scope) for scope in policy.get("scopes") or (MCP_WRITE_SCOPE,)]
            schemes = [{"type": "oauth2", "scopes": scopes}]
            item["securitySchemes"] = schemes
            meta["dev-control-plane/auth"] = AUTHENTICATED_READ_AUTH_MARKER if is_read_only else WRITE_AUTH_MARKER
            meta["dev-control-plane/chatgpt"] = "hidden_until_oauth"
            meta["dev-control-plane/exposure"] = "oauth_protected_read_only" if is_read_only else "oauth_protected_write"
            meta["securitySchemes"] = schemes
        item["_meta"] = meta
        enriched.append(item)
    return enriched


TOOL_DEFINITIONS: list[dict[str, Any]] = _with_tool_metadata([
    {
        "name": "get_status",
        "description": "Use this when the user asks whether dev-control-plane is healthy. Returns sanitized service, model/toolchain, MCP, active run and wb-core production lock status.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "list_targets",
        "description": "Use this when the user asks what dev-control-plane can operate on. Lists targets, source mode, validation, blockers, warnings and production-lane availability.",
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
        "name": "list_target_docs",
        "description": "Authenticated read-only tool. Use this to list allowlisted source-of-truth docs for a target such as wb-core. Requires an authenticated MCP session and never checks out, resets or mutates the target repo.",
        "inputSchema": {
            "type": "object",
            "properties": {"target_id": {"type": "string"}},
            "required": ["target_id"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
    },
    {
        "name": "search_target_docs",
        "description": "Authenticated read-only tool. Use this when the user asks for current WebCore/wb-core docs context. Searches only allowlisted target docs paths and returns sanitized snippets with path, line range and commit.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target_id": {"type": "string"},
                "query": {"type": "string"},
                "max_results": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
                "path_prefix": {"type": "string"},
            },
            "required": ["target_id", "query"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
    },
    {
        "name": "get_target_doc",
        "description": "Authenticated read-only tool. Use this to read a sanitized, size-limited target doc from the allowlist by path and optional line range. Rejects forbidden paths and path traversal.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target_id": {"type": "string"},
                "path": {"type": "string"},
                "line_start": {"type": "integer", "minimum": 1},
                "line_end": {"type": "integer", "minimum": 1},
                "max_bytes": {"type": "integer", "minimum": 1000, "maximum": 64000, "default": 24000},
            },
            "required": ["target_id", "path"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
    },
    {
        "name": "read_target_docs",
        "description": "Authenticated read-only compatibility tool. Use this when ChatGPT needs one callable target docs action. Requires OAuth and routes action=list/search/get to the bounded target docs readers for wb-core.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["list", "search", "get"]},
                "target_id": {"type": "string", "default": "wb-core"},
                "query": {"type": "string"},
                "path": {"type": "string"},
                "max_results": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
                "path_prefix": {"type": "string"},
                "line_start": {"type": "integer", "minimum": 1},
                "line_end": {"type": "integer", "minimum": 1},
                "max_bytes": {"type": "integer", "minimum": 1000, "maximum": 64000, "default": 24000},
            },
            "required": ["action", "target_id"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
    },
    {
        "name": "get_production_lock_status",
        "description": "Use this to inspect the wb-core production-lane target lock and waiting run count.",
        "inputSchema": {"type": "object", "properties": {"target_id": {"type": "string", "default": "wb-core"}}, "additionalProperties": False},
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "list_active_runs",
        "description": "Use this when the user asks what is currently running. Lists active MCP runs or runs matching a status filter, with run_id, target, mode, stage and blocker summary.",
        "inputSchema": {
            "type": "object",
            "properties": {"target_id": {"type": "string"}, "status": {"oneOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}]}},
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "list_parallel_tasks",
        "description": "Use this to inspect the sanitized parallel task ledger. Lists submitted tasks by optional target_id, promotion_epoch or status. This does not start Codex, PRs, merges, deploys or sprint/ping-pong.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target_id": {"type": "string"},
                "promotion_epoch": {"type": "string"},
                "status": {"type": "string"},
            },
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
    },
    {
        "name": "get_parallel_task",
        "description": "Use this to inspect one sanitized parallel task ledger record by task_id. The response omits the full task text and never starts execution.",
        "inputSchema": {
            "type": "object",
            "properties": {"task_id": {"type": "string"}},
            "required": ["task_id"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
    },
    {
        "name": "get_target_promotion_state",
        "description": "Use this to inspect sanitized target promotion state for the parallel task ledger. Returns target_id + promotion_epoch first-candidate/completion/freeze state only.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target_id": {"type": "string"},
                "promotion_epoch": {"type": "string"},
            },
            "required": ["target_id"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
    },
    {
        "name": "list_parallel_candidates",
        "description": "Use this to inspect sanitized promotion candidates for the parallel task ledger. Returns verifier-passed candidate metadata and promotion blockers; it never starts production.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target_id": {"type": "string"},
                "promotion_epoch": {"type": "string"},
            },
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
    },
    {
        "name": "start_wb_core_auto_task",
        "description": "Write tool. Use this for normal ChatGPT-submitted wb-core/WebCore tasks. Requires OAuth dcp.write. DevControl atomically starts one direct production-capable route when exclusive, or returns a precise blocker before Codex starts. Do not fall back to start_sprint, start_managed_clone_run or managed-clone-only execution.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_text": {"type": "string", "description": "Bounded wb-core/WebCore task text from the ChatGPT project."},
                "idempotency_key": {"type": "string"},
                "operator_note": {"type": "string"},
                "max_wait_seconds": {"type": "integer", "minimum": 0, "maximum": 30},
            },
            "required": ["task_text"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": True, "openWorldHint": False},
    },
    {
        "name": "start_wb_core_production_lane",
        "description": "Write tool. Use this only when the user explicitly asks to start a wb-core production-lane run. Requires OAuth dcp.write scope. Starts quickly and returns run_id; dry_run=true never creates PR, merge or deploy.",
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
        "description": "Write tool. Use this only when the user explicitly asks to start a managed-clone-only Codex run for non-production review work. Requires OAuth dcp.write scope. It never opens PRs, merges or deploys, and must not be used as a fallback for ordinary wb-core/WebCore tasks that expect merge/deploy. DEVCONTROL_START_SPRINT_V1 bridge payloads are frozen and return a blocker.",
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
        "name": "submit_parallel_task",
        "description": "Write tool. Use this only to submit a task into the DevControl parallel task ledger. Requires OAuth dcp.write scope. It records state only and does not start Codex, start_sprint, ping-pong, PR, merge, deploy or production_lane.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target_id": {"type": "string"},
                "task_text": {"type": "string"},
                "source": {"type": "string"},
                "source_id": {"type": "string"},
                "source_chat": {"type": "string"},
                "source_tool": {"type": "string"},
                "submitted_by": {"type": "string"},
                "batch_id": {"type": "string"},
                "release_group": {"type": "string"},
                "promotion_epoch": {"type": "string"},
                "idempotency_key": {"type": "string"},
            },
            "required": ["target_id", "task_text"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False},
    },
    {
        "name": "start_parallel_task_execution",
        "description": "Write tool. Use this only to explicitly start/bind a submitted parallel task. Requires OAuth dcp.write. Default starter_mode=fake is state-only. execution_mode=real_managed_clone is guarded and disabled unless the server runtime explicitly enables it; it never calls start_sprint, PR, merge, deploy or production_lane.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "starter_mode": {"type": "string", "enum": ["fake", "real_managed_clone"], "default": "fake"},
                "execution_mode": {"type": "string", "enum": ["fake", "real_managed_clone"]},
                "confirm_real_managed_clone": {"type": "boolean", "default": False},
                "task_spec_id": {"type": "string"},
                "run_id": {"type": "string"},
            },
            "required": ["task_id"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False},
    },
    {
        "name": "reconcile_parallel_task",
        "description": "Write tool. Use this to explicitly reconcile a parallel task from a managed-run status/report. Requires OAuth dcp.write. If run_status is omitted, DevControl tries to read sanitized existing run/job artifacts by run_id or bound run_id. It updates ledger status/candidate state only and never starts production.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "run_status": {"type": "string"},
                "run_id": {"type": "string"},
                "real_job_id": {"type": "string"},
                "verifier_status": {"type": "string"},
                "changed_files": {"type": "array", "items": {"type": "string"}},
                "verifier_summary": {"type": "object"},
                "blocker": {"type": "string"},
            },
            "required": ["task_id"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False},
    },
    {
        "name": "promote_parallel_task",
        "description": "Write tool. Use this for an explicit parallel promotion decision. Requires OAuth dcp.write. Without allow_auto_first_promotion=true it queues/blocks. mode=fake_complete simulates production_complete for tests. mode=real_production_bridge also requires allow_real_production_promotion=true; hosted/live runtime starts the existing gated wb-core production lane and non-live runtimes fail closed.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "allow_auto_first_promotion": {"type": "boolean", "default": False},
                "allow_real_production_promotion": {"type": "boolean", "default": False},
                "mode": {"type": "string", "enum": ["dry_run", "fake_complete", "real_production_bridge"], "default": "dry_run"},
            },
            "required": ["task_id"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False},
    },
    {
        "name": "promote_next_parallel_candidate",
        "description": "Write tool. Use this to select the next safe first-finished candidate for a target. Requires OAuth dcp.write. It skips frozen/blocked/stale candidates and never runs real production lane.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target_id": {"type": "string"},
                "promotion_epoch": {"type": "string"},
                "allow_auto_first_promotion": {"type": "boolean", "default": False},
                "allow_real_production_promotion": {"type": "boolean", "default": False},
                "mode": {"type": "string", "enum": ["dry_run", "fake_complete", "real_production_bridge"], "default": "dry_run"},
            },
            "required": ["target_id"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False},
    },
    {
        "name": "promote_parallel_selection",
        "description": "Write tool. Use this for the same selected Merge & Deploy flow as the operator Monitoring UI. Requires OAuth dcp.write. Accepts task_id, run_id or candidate_id selections, plans single or group promotion, and is fail-closed unless confirm_merge_deploy plus explicit policy flags are present. In hosted/live runtime it binds real selected production run ids through the existing gated wb-core production lane; non-live runtimes plan or fail closed.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target_id": {"type": "string"},
                "selected_ids": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                "selection_type": {"type": "string", "enum": ["auto", "task_id", "run_id", "candidate_id"], "default": "auto"},
                "mode": {"type": "string", "enum": ["manual_order", "auto_order"], "default": "auto_order"},
                "confirm_merge_deploy": {"type": "boolean", "default": False},
                "allow_refresh": {"type": "boolean", "default": False},
                "dry_run": {"type": "boolean", "default": False},
                "plan_only": {"type": "boolean", "default": False},
                "operator_note": {"type": "string"},
                "idempotency_key": {"type": "string"},
                "allow_auto_first_promotion": {"type": "boolean", "default": False},
                "allow_real_production_promotion": {"type": "boolean", "default": False},
            },
            "required": ["target_id", "selected_ids"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": True, "openWorldHint": False},
    },
    {
        "name": "refresh_selected_candidate",
        "description": "Write tool. Create a managed_clone_only refresh/rework task for a selected promotion candidate that became stale or conflicted after partial group deployment. Requires OAuth dcp.write. Does not start production lane, PR, merge or deploy.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target_id": {"type": "string"},
                "source_run_id": {"type": "string"},
                "candidate_id": {"type": "string"},
                "selected_id": {"type": "string"},
                "selection_type": {"type": "string", "enum": ["auto", "task_id", "run_id", "candidate_id"], "default": "auto"},
                "group_id": {"type": "string"},
                "conflict_reason": {"type": "string"},
                "conflict_files": {"type": "array", "items": {"type": "string"}},
                "mode": {"type": "string", "enum": ["managed_clone_only"], "default": "managed_clone_only"},
                "confirm_start": {"type": "boolean", "default": False},
                "start_managed_run": {"type": "boolean", "default": False},
                "source_chat": {"type": "string"},
                "submitted_by": {"type": "string"},
                "release_group": {"type": "string"},
                "idempotency_key": {"type": "string"},
            },
            "required": ["target_id"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False},
    },
    {
        "name": "start_sprint",
        "description": "Frozen/internal compatibility surface. start_sprint is hidden from ordinary ChatGPT operator discovery; non-internal calls return blocker: start_sprint is frozen for operator flow; use direct wb-core auto Codex task.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target_id": {"type": "string", "enum": ["wb-core"]},
                "sprint_text": {"type": "string"},
                "max_steps": {"type": "integer", "minimum": 1, "maximum": 3, "default": 2},
                "max_retries_per_step": {"type": "integer", "minimum": 0, "maximum": 1, "default": 1},
                "execution_mode": {"type": "string", "enum": ["managed_clone_only"], "default": "managed_clone_only"},
                "operator_note": {"type": "string"},
                "idempotency_key": {"type": "string"},
            },
            "required": ["target_id", "sprint_text"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": True},
    },
    {
        "name": "resume_wb_core_production_deploy",
        "description": "Write tool. Use this only when the user explicitly asks to resume backup/deploy/probes for an already merged blocked wb-core production-lane run. Requires OAuth dcp.write scope. dry_run=true only checks eligibility; dry_run=false requires confirm_resume_deploy=true and never reruns Codex, creates a branch, opens a PR or merges again.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string"},
                "dry_run": {"type": "boolean", "default": True},
                "confirm_resume_deploy": {"type": "boolean", "default": False},
                "idempotency_key": {"type": "string"},
                "max_wait_seconds": {"type": "integer", "minimum": 0, "maximum": 30},
            },
            "required": ["run_id"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": True},
    },
    {
        "name": "get_run_status",
        "description": "Use this when the user provides a run_id and asks for progress. Returns status, current stage, target, PR/deploy status and blockers.",
        "inputSchema": {"type": "object", "properties": {"run_id": {"type": "string"}}, "required": ["run_id"], "additionalProperties": False},
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "get_run_report",
        "description": "Use this when the user asks for the final report or handoff for a run_id. Returns sanitized PR, verifier, deploy and rollback details when present.",
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
        "name": "get_run_timeline",
        "description": "Use this to read sanitized live-monitor timeline/stage events for a run_id.",
        "inputSchema": {"type": "object", "properties": {"run_id": {"type": "string"}}, "required": ["run_id"], "additionalProperties": False},
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "get_run_log_tail",
        "description": "Use this to read a sanitized terminal-like log tail for a run_id. Unsafe terminal controls are stripped; safe ANSI SGR color/style may remain.",
        "inputSchema": {
            "type": "object",
            "properties": {"run_id": {"type": "string"}, "max_bytes": {"type": "integer", "minimum": 1000, "maximum": 64000}},
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
])

_TOOL_DEFINITION_NAMES = {str(tool.get("name") or "") for tool in TOOL_DEFINITIONS}
if _TOOL_DEFINITION_NAMES != set(MCP_TOOL_REGISTRY):
    missing = sorted(set(MCP_TOOL_REGISTRY) - _TOOL_DEFINITION_NAMES)
    extra = sorted(_TOOL_DEFINITION_NAMES - set(MCP_TOOL_REGISTRY))
    raise RuntimeError(f"MCP tool registry/definition mismatch: missing={missing} extra={extra}")
