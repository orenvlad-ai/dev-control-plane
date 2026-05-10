"""Local/hosted-ready development control-plane MVP prototype server.

This server is intentionally a repo-only/local prototype. It does not register
production routes, does not call OpenAI unless explicitly selected, and does
not run Codex.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time
import tomllib
from typing import Any, Mapping, Sequence
from urllib.parse import parse_qs, unquote, urlparse

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
for path in (SRC, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dev_control_plane.contracts import (  # noqa: E402
    ControlPlaneValidationError,
    build_codex_prompt,
    freeze_task_spec,
    sprint_step_to_dict,
    sprint_steps_from_task_spec_mapping,
    task_spec_from_mapping,
    task_spec_to_dict,
    validate_sprint_step,
    validate_task_spec,
)
from dev_control_plane.ai import (  # noqa: E402
    CuratorDraftRequest,
    curator_draft_result_to_dict,
    draft_task_spec,
    openai_connection_test,
    openai_connection_test_result_to_dict,
    openai_curator_chat_reply,
    openai_operator_message,
)
from dev_control_plane.execution import (  # noqa: E402
    ControlPlaneExecutionError,
    cleanup_target_run,
    cleanup_run_worktree,
    load_run_record,
    prepare_run,
    run_result_to_dict,
    run_codex_cli,
    run_step,
    verifier_result_to_dict,
    verify_run,
    verify_target_run,
)
from dev_control_plane.codex_observability import (  # noqa: E402
    codex_observability_status,
    codex_run_reconciliation,
    codex_stale_assessment,
    finalize_process_state,
    read_process_state,
    terminate_run_owned_process_group,
)
from dev_control_plane.github_closure import (  # noqa: E402
    evaluate_dev_control_plane_closure_decision,
    github_closure_decision_to_dict,
)
from dev_control_plane.github_auth import build_github_auth_status  # noqa: E402
from dev_control_plane.parallel_ledger import (  # noqa: E402
    PARALLEL_PING_PONG_ENABLED,
    ParallelLedgerError,
    ParallelTaskLedger,
    promotion_state_summary,
    task_record_summary,
)
from dev_control_plane.parallel_coordinator import (  # noqa: E402
    ParallelCoordinatorError,
    ParallelExecutionCoordinator,
)
from dev_control_plane.operator_lifecycle import decorate_operator_lifecycle  # noqa: E402
from dev_control_plane.selected_promotion import (  # noqa: E402
    SelectedPromotionCandidate,
    SelectedPromotionGroup,
    candidate_from_mapping,
    group_from_mapping,
    new_group_id,
    now_utc as selected_now_utc,
    plan_selected_promotion,
)
from dev_control_plane.ssh_deploy import build_ssh_deploy_status  # noqa: E402
from dev_control_plane.live_monitor import (  # noqa: E402
    append_live_event,
    append_terminal_output,
    is_terminal_status,
    live_url,
    read_live_timeline,
    read_terminal_tail,
    sanitize_terminal_text,
)
from dev_control_plane.secrets import get_openai_credentials, get_openai_status  # noqa: E402
from dev_control_plane.state_layout import (  # noqa: E402
    ControlPlaneStateLayout,
    DEFAULT_STATE_DIR,
    STATE_DIR_ENV,
    StateLayoutError,
    resolve_state_root,
    safe_state_component,
    slug_state_component,
)
from dev_control_plane.runtime_config import (  # noqa: E402
    RuntimeConfigError,
    load_runtime_config,
    runtime_config_public_dict,
    save_runtime_config,
)
from dev_control_plane.toolchain import (  # noqa: E402
    build_codex_auth_status,
    build_codex_runtime_parity_status,
    build_toolchain_status,
    runtime_command_env,
)
from dev_control_plane.target_projects import (  # noqa: E402
    build_target_context_snapshot,
    build_target_context_summary,
    load_target_project_configs,
    merge_target_defaults_into_task_spec_payload,
    target_context_summary_to_dict,
    target_project_config_to_dict,
    target_project_defaults,
    target_project_validation_result_to_dict,
    validate_target_project,
)
from dev_control_plane.target_workflow import (  # noqa: E402
    build_preview_plan,
    build_target_pr_plan,
    evaluate_target_approval,
    target_workflow_decision_to_dict,
)
from dev_control_plane.target_production import (  # noqa: E402
    DEFAULT_DEPLOY_RUNNER,
    DEFAULT_DEPLOY_TARGET_FILE,
    TARGET_PROJECT_ID,
    TARGET_REPO,
    TARGET_REPO_URL,
    build_wb_core_production_plan,
    execute_wb_core_production_lane,
    execute_wb_core_resume_deploy,
    inspect_wb_core_production_lock,
    target_production_decision_to_dict,
    target_production_result_to_dict,
    target_production_resume_result_to_dict,
)
from dev_control_plane.timeline import append_timeline_event, build_run_timeline  # noqa: E402
from dev_control_plane.mcp import (  # noqa: E402
    MCP_ENDPOINT,
    MCP_TRANSPORT,
    MCPToolBackend,
    build_mcp_context,
)
from dev_control_plane.mcp_oauth import (  # noqa: E402
    MCPOAuthProvider,
    OAuthError,
    external_base_url,
    parse_form_urlencoded,
)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
RUNTIME_PROFILE_ENV = "DEV_CONTROL_PLANE_RUNTIME_PROFILE"
HOST_ENV = "DEV_CONTROL_PLANE_HOST"
PORT_ENV = "DEV_CONTROL_PLANE_PORT"
DEFAULT_RUNTIME_PROFILE = "local"
HOSTED_RUNTIME_PROFILE = "hosted"
RUNTIME_PROFILES = {DEFAULT_RUNTIME_PROFILE, HOSTED_RUNTIME_PROFILE}
HOSTED_STATE_DIR = Path("/var/lib/dev-control-plane")
BIND_POLICY = "loopback_only"
EXAMPLE_TASK_SPEC = ROOT / "artifacts" / "input" / "example_task_spec.json"
TARGET_CONFIG_DIR = ROOT / "configs" / "target_projects"
LOCAL_ONLY_NOTICE = "Development Control Plane server: loopback-only bind, optional OpenAI intake, managed-clone Codex UI run, no live/deploy/public route."
OPENAI_DISCONNECTED_MESSAGE = "OpenAI-куратор не подключён. Подключите OPENAI_API_KEY в терминале."
FREEZE_TASK_FIRST_MESSAGE = "Сначала зафиксируйте задачу"
RUNNABLE_STEP_MISSING_MESSAGE = "В карточке задачи не найден шаг запуска"
RUNNABLE_STEP_MISSING_NEXT_STEP = "Пересформируйте карточку или сохраните карточку с шагом запуска"
TERMINAL_LIVE_STATUSES = {
    "blocked",
    "blocked_by_conflict",
    "blocked_by_operator",
    "cancelled",
    "completed",
    "completed_dry_run",
    "conflict_detected",
    "denied",
    "decision_only",
    "expired",
    "failed",
    "needs_rework",
    "passed",
    "partially_deployed",
    "partial_group_blocked",
    "partial_group_complete_with_blockers",
    "ready_for_separate_deploy",
    "refresh_required",
    "needs_verifier_after_control_error",
    "stale_lost_process",
    "stale_timeout",
}
PROMOTION_GROUP_COLLECTION = "parallel_promotion_groups"
PROMOTION_SELECTION_ATTEMPTS_COLLECTION = "parallel_selection_attempts"
PROMOTION_REFRESH_PLAN_COLLECTION = "parallel_refresh_plans"
PROMOTION_GROUP_ACTIVE_STATUSES = {"planned", "plan_ready", "group_plan_ready", "waiting", "promotion_running"}
PROMOTION_GROUP_TERMINAL_STATUSES = {
    "blocked",
    "blocked_by_conflict",
    "blocked_by_operator",
    "cancelled",
    "completed",
    "expired",
    "failed",
    "partially_deployed",
    "partial_group_blocked",
    "partial_group_complete_with_blockers",
    "production_complete",
    "ready_for_separate_deploy",
}
PROMOTION_GROUP_PLAN_TTL_SECONDS = 15 * 60

EXPOSED_ROUTES = (
    "GET /",
    "GET /runs/live",
    "GET /runs/{run_id}/watch",
    "GET /api/state",
    "GET /api/runs/live",
    "GET /api/runs/stream",
    "GET /api/runs/{id}/live",
    "GET /api/runs/{id}/timeline",
    "GET /api/runs/{id}/log-tail",
    "GET /api/runs/{id}/stream",
    "GET /mcp",
    "POST /mcp",
    "POST /mcp/stream",
    "GET /.well-known/oauth-protected-resource",
    "GET /.well-known/oauth-protected-resource/mcp",
    "GET /.well-known/oauth-authorization-server",
    "GET /.well-known/openid-configuration",
    "GET /oauth/authorize",
    "POST /oauth/authorize",
    "POST /oauth/register",
    "POST /oauth/token",
    "GET /api/connections/status",
    "GET /api/runtime-config",
    "GET /api/toolchain/status",
    "GET /api/example-task-spec",
    "GET /api/target-projects",
    "GET /api/target-projects/{id}",
    "GET /api/target-projects/{id}/summary",
    "GET /api/parallel-tasks",
    "GET /api/parallel-tasks/{id}",
    "GET /api/parallel-promotion-groups",
    "GET /api/parallel-promotion-groups/{id}",
    "GET /api/parallel-targets/{id}/promotion-candidates",
    "GET /api/parallel-targets/{id}/promotion-state",
    "GET /api/targets",
    "GET /api/targets/{id}/summary",
    "GET /api/task-specs/{id}",
    "GET /api/prompts/{prompt_id}",
    "GET /api/runs/{id}",
    "GET /api/runs/{id}/summary",
    "GET /api/real-runs/{id}",
    "GET /api/draft-task-spec-jobs/{id}",
    "POST /api/discussions",
    "POST /api/connections/openai-test",
    "POST /api/runtime-config",
    "POST /api/discussions/{id}/messages",
    "POST /api/discussions/{id}/draft-task-spec",
    "POST /api/discussions/{id}/draft-task-spec-jobs",
    "POST /api/task-specs",
    "POST /api/task-specs/{id}/freeze",
    "POST /api/task-specs/{id}/generate-prompt",
    "POST /api/task-specs/{id}/prepare-run",
    "POST /api/task-specs/{id}/run-fake",
    "POST /api/task-specs/{id}/run-codex-managed",
    "POST /api/guided-safe-fake-run",
    "POST /api/github-closure/decision",
    "POST /api/target-workflow/pr-plan",
    "POST /api/target-workflow/preview-plan",
    "POST /api/target-workflow/approval-decision",
    "POST /api/target-production/plan",
    "POST /api/parallel-tasks",
    "POST /api/parallel-tasks/{id}/start-execution",
    "POST /api/parallel-tasks/{id}/reconcile",
    "POST /api/parallel-tasks/{id}/promote",
    "POST /api/parallel-selection/promote",
    "POST /api/parallel-selection/refresh",
    "POST /api/parallel-promotion-groups/{id}/cancel",
    "POST /api/parallel-targets/{id}/promote-next",
    "POST /api/runs/{id}/verify",
    "POST /api/runs/{id}/cleanup",
    "POST /api/runs/{id}/cancel",
    "POST /api/runs/{id}/mark-stale",
)


@dataclass(frozen=True)
class CockpitServerConfig:
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    state_dir: Path = DEFAULT_STATE_DIR
    target_config_dir: Path = TARGET_CONFIG_DIR
    runtime_profile: str = DEFAULT_RUNTIME_PROFILE
    bind_policy: str = BIND_POLICY


class CockpitStateStore:
    def __init__(self, state_dir: Path, target_config_dir: Path) -> None:
        self.layout = ControlPlaneStateLayout.from_path(state_dir)
        self.layout.ensure_base_dirs()
        self.state_dir = self.layout.state_root
        self.prompts_dir = self.layout.artifacts_dir / "prompts"
        self.target_config_dir = target_config_dir
        self._jobs_lock = threading.Lock()
        self.prompts_dir.mkdir(parents=True, exist_ok=True)

    def summary(self, config: CockpitServerConfig) -> dict[str, Any]:
        discussions = self._read_collection("discussions")
        task_specs = self._read_collection("task_specs")
        prompts = self._read_collection("prompts")
        runs = self._read_collection("runs")
        targets = self._target_summaries()
        return {
            "status": "ok",
            "local_only": True,
            "host": config.host,
            "port": config.port,
            "runtime_profile": config.runtime_profile,
            "bind_policy": config.bind_policy,
            "state_dir": str(self.state_dir),
            "state_layout": {
                "runs_dir": str(self.layout.runs_dir),
                "workspaces_dir": str(self.layout.workspaces_dir),
                "artifacts_dir": str(self.layout.artifacts_dir),
                "logs_dir": str(self.layout.logs_dir),
                "verifier_dir": str(self.layout.verifier_dir),
                "collections_dir": str(self.layout.collections_dir),
            },
            "target_config_dir": str(self.target_config_dir),
            "counts": {
                "discussions": len(discussions),
                "messages": sum(len(item.get("messages", [])) for item in discussions.values()),
                "task_specs": len(task_specs),
                "prompts": len(prompts),
                "runs": len(runs),
            },
            "discussions": sorted(discussions),
            "task_specs": sorted(task_specs),
            "prompts": sorted(prompts),
            "runs": sorted(runs),
            "target_projects": [item["project_id"] for item in targets],
            "target_project_count": len(targets),
            "exposed_routes": list(EXPOSED_ROUTES),
            "live_deploy_enabled": False,
            "public_routes_enabled": False,
            "codex_runner_enabled": True,
            "fake_executor_enabled": True,
            "real_executor_enabled": True,
            "ai_curator_enabled": True,
            "openai_curator_optional": True,
            "openai_api_enabled": False,
            "real_codex_ui_enabled": True,
            "real_codex_ui_mode": "managed_clone_only",
            "github_closure_decision_enabled": True,
            "github_closure_mode": "decision_only",
            "target_workflow_decision_enabled": True,
            "target_workflow_mode": "decision_only",
            "target_production_lane_enabled": True,
            "target_production_lane_mode": "explicit_wb_core_pr_merge_deploy_policy",
            "target_production_lane_statuses": [
                "managed_clone_done",
                "codex_done",
                "verifier_passed",
                "pr_created",
                "pr_merged",
                "backup_created",
                "deploy_started",
                "deploy_passed",
                "post_deploy_passed",
                "blocked",
            ],
            "target_production_lock": inspect_wb_core_production_lock(
                workspace_path=None,
                run_dir=self.state_dir / "runs" / "state-api-lock-probe",
                run_id="state-api-lock-probe",
            ),
            "parallel_task_ledger": self.parallel_ledger_status(),
            "codex_observability": codex_observability_status(env=self._runtime_config_env()),
            "mcp": self.mcp_status() if hasattr(self, "mcp_status") else None,
            "hosted_ready": config.runtime_profile == HOSTED_RUNTIME_PROFILE,
            "notice": LOCAL_ONLY_NOTICE,
        }

    def connections_status(self) -> dict[str, Any]:
        return build_connections_status(env=self._runtime_config_env())

    def openai_connection_test(self) -> dict[str, Any]:
        return openai_connection_test_result_to_dict(openai_connection_test())

    def runtime_config_status(self) -> dict[str, Any]:
        return runtime_config_public_dict(env=self._runtime_config_env())

    def mcp_status(self) -> dict[str, Any]:
        backend = getattr(self, "mcp_backend", None)
        if backend is None:
            return {
                "enabled": False,
                "endpoint": MCP_ENDPOINT,
                "transport": MCP_TRANSPORT,
                "tool_count": 0,
            }
        return backend.status_summary()

    def parallel_ledger_status(self) -> dict[str, Any]:
        try:
            return _sanitize_parallel_payload(self._parallel_ledger().status())
        except ParallelLedgerError as exc:
            return {"status": "blocked", "blocker": str(exc)}

    def submit_parallel_task(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        target_id = _required_payload_str(payload, "target_id")
        self._target_config_by_id(target_id)
        task_text = _sanitize_parallel_input_text(_required_payload_str(payload, "task_text"))
        if len(task_text) > 16000:
            raise BadRequestError("task_text is too long")
        source = (
            _sanitize_optional_parallel_input_text(payload.get("source"))
            or _sanitize_optional_parallel_input_text(payload.get("source_id"))
            or _sanitize_optional_parallel_input_text(payload.get("source_tool"))
            or "api"
        )
        try:
            task = self._parallel_ledger().submit_task(
                target_id=target_id,
                task_text=task_text,
                source=source,
                chat_id=_sanitize_optional_parallel_input_text(payload.get("chat_id")),
                source_id=_sanitize_optional_parallel_input_text(payload.get("source_id")),
                source_chat=_sanitize_optional_parallel_input_text(payload.get("source_chat")),
                source_tool=_sanitize_optional_parallel_input_text(payload.get("source_tool")),
                submitted_by=_sanitize_optional_parallel_input_text(payload.get("submitted_by")),
                batch_id=_sanitize_optional_parallel_input_text(payload.get("batch_id")),
                release_group=_sanitize_optional_parallel_input_text(payload.get("release_group")),
                promotion_epoch=_sanitize_optional_parallel_input_text(payload.get("promotion_epoch")),
                idempotency_key=_sanitize_optional_parallel_input_text(payload.get("idempotency_key")),
            )
        except ParallelLedgerError as exc:
            raise BadRequestError(str(exc)) from exc
        return {
            "status": "submitted",
            "task": _sanitize_parallel_payload(task_record_summary(task)),
            "task_id": task.task_id,
            "target_id": task.target_id,
            "promotion_epoch": task.promotion_epoch,
            "execution_started": False,
            "codex_started": False,
            "production_lane_started": False,
            "ping_pong_started": False,
            "parallel_ping_pong_enabled": PARALLEL_PING_PONG_ENABLED,
        }

    def list_parallel_tasks(
        self,
        *,
        target_id: str | None = None,
        promotion_epoch: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        try:
            tasks = list(self._parallel_ledger().list_tasks(target_id=target_id, promotion_epoch=promotion_epoch))
        except ParallelLedgerError as exc:
            raise BadRequestError(str(exc)) from exc
        if status:
            tasks = [task for task in tasks if task.status == status]
        return {
            "status": "ok",
            "tasks": [_sanitize_parallel_payload(decorate_operator_lifecycle(task_record_summary(task))) for task in tasks],
            "ledger": self.parallel_ledger_status(),
        }

    def get_parallel_task(self, task_id: str) -> dict[str, Any]:
        try:
            task = self._parallel_ledger().get_task(task_id)
        except ParallelLedgerError as exc:
            raise NotFoundError(str(exc)) from exc
        return {"status": "ok", "task": _sanitize_parallel_payload(decorate_operator_lifecycle(task_record_summary(task)))}

    def get_target_promotion_state(self, target_id: str, *, promotion_epoch: str | None = None) -> dict[str, Any]:
        self._target_config_by_id(target_id)
        try:
            state = self._parallel_ledger().target_promotion_state(target_id, promotion_epoch=promotion_epoch)
        except ParallelLedgerError as exc:
            raise BadRequestError(str(exc)) from exc
        return _sanitize_parallel_payload(
            promotion_state_summary(state, target_id=target_id, promotion_epoch=promotion_epoch)
        )

    def start_parallel_task_execution(self, task_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        execution_mode = (
            _optional_str(payload.get("execution_mode"))
            or _optional_str(payload.get("starter_mode"))
            or "fake"
        )
        if execution_mode in {"real", "real_managed_clone"}:
            return self._start_parallel_task_real_managed(task_id, payload)
        if execution_mode not in {"fake", "managed_clone_fake"}:
            return {
                "status": "blocked",
                "task_id": task_id,
                "execution_mode": execution_mode,
                "blocker": "unsupported parallel execution_mode; use fake or real_managed_clone",
                "codex_started": False,
                "ping_pong_started": False,
                "production_lane_started": False,
            }
        try:
            return _sanitize_parallel_payload(
                self._parallel_coordinator().start_managed_execution(
                    task_id,
                    starter_mode="fake",
                    run_id=_sanitize_optional_parallel_input_text(payload.get("run_id")),
                )
            )
        except (ParallelCoordinatorError, ParallelLedgerError) as exc:
            raise BadRequestError(str(exc)) from exc

    def _start_parallel_task_real_managed(self, task_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        try:
            task = self._parallel_ledger().get_task(task_id)
        except ParallelLedgerError as exc:
            raise BadRequestError(str(exc)) from exc
        if task.managed_run_id:
            return {
                "status": task.status,
                "task": _sanitize_parallel_payload(task_record_summary(task)),
                "task_id": task.task_id,
                "run_id": task.managed_run_id,
                "idempotent_replay": True,
                "execution_mode": "real_managed_clone",
                "real_managed_clone_started": False,
                "codex_started": False,
                "ping_pong_started": False,
                "production_lane_started": False,
            }
        configured = str(os.environ.get("DEV_CONTROL_PLANE_PARALLEL_REAL_MANAGED_RUNS") or "").strip().lower()
        if configured == "stub":
            run_id = _sanitize_optional_parallel_input_text(payload.get("run_id")) or f"real-stub-{task.task_id}"
            try:
                bound = self._parallel_ledger().bind_managed_run(task.task_id, run_id)
            except ParallelLedgerError as exc:
                raise BadRequestError(str(exc)) from exc
            return {
                "status": "managed_run_running",
                "task": _sanitize_parallel_payload(task_record_summary(bound)),
                "task_id": bound.task_id,
                "run_id": bound.managed_run_id,
                "execution_mode": "real_managed_clone",
                "real_managed_clone_started": False,
                "real_mode_stubbed": True,
                "codex_started": False,
                "ping_pong_started": False,
                "production_lane_started": False,
            }
        if configured not in {"1", "true", "enabled"}:
            return {
                "status": "blocked",
                "task_id": task.task_id,
                "target_id": task.target_id,
                "execution_mode": "real_managed_clone",
                "blocker": "real parallel managed-clone execution is disabled; set DEV_CONTROL_PLANE_PARALLEL_REAL_MANAGED_RUNS=1 and pass confirm_real_managed_clone=true",
                "real_managed_clone_started": False,
                "codex_started": False,
                "ping_pong_started": False,
                "production_lane_started": False,
            }
        if not _bool_from_payload(payload.get("confirm_real_managed_clone")):
            return {
                "status": "blocked",
                "task_id": task.task_id,
                "target_id": task.target_id,
                "execution_mode": "real_managed_clone",
                "blocker": "confirm_real_managed_clone=true is required for real managed-clone execution",
                "real_managed_clone_started": False,
                "codex_started": False,
                "ping_pong_started": False,
                "production_lane_started": False,
            }
        task_spec_id = _sanitize_optional_parallel_input_text(payload.get("task_spec_id"))
        if not task_spec_id:
            return {
                "status": "blocked",
                "task_id": task.task_id,
                "target_id": task.target_id,
                "execution_mode": "real_managed_clone",
                "blocker": "task_spec_id is required to bridge a parallel task into the existing managed-clone runner",
                "real_managed_clone_started": False,
                "codex_started": False,
                "ping_pong_started": False,
                "production_lane_started": False,
            }
        try:
            task_spec_payload = self.get_task_spec(task_spec_id)
        except Exception as exc:
            return {
                "status": "blocked",
                "task_id": task.task_id,
                "target_id": task.target_id,
                "execution_mode": "real_managed_clone",
                "blocker": f"task_spec_id is not readable for real managed-clone bridge: {exc}",
                "real_managed_clone_started": False,
                "codex_started": False,
                "ping_pong_started": False,
                "production_lane_started": False,
            }
        task_spec_target = _optional_str(task_spec_payload.get("target_project_id")) or _optional_str(
            payload.get("target_project_id")
        )
        if task_spec_target and task_spec_target != task.target_id:
            return {
                "status": "blocked",
                "task_id": task.task_id,
                "target_id": task.target_id,
                "execution_mode": "real_managed_clone",
                "blocker": f"task_spec target {task_spec_target} does not match ledger target {task.target_id}",
                "real_managed_clone_started": False,
                "codex_started": False,
                "ping_pong_started": False,
                "production_lane_started": False,
            }
        job_payload = dict(payload)
        job_payload["target_project_id"] = task.target_id
        job = self.start_managed_codex_run(task_spec_id, job_payload)
        job_id = str(job.get("id") or "")
        try:
            bound = self._parallel_ledger().bind_managed_run(task.task_id, job_id)
        except ParallelLedgerError as exc:
            raise BadRequestError(str(exc)) from exc
        return {
            "status": "managed_run_running",
            "task": _sanitize_parallel_payload(task_record_summary(bound)),
            "task_id": bound.task_id,
            "run_id": bound.managed_run_id,
            "real_job_id": job_id,
            "execution_mode": "real_managed_clone",
            "real_managed_clone_started": True,
            "codex_started": True,
            "ping_pong_started": False,
            "production_lane_started": False,
        }

    def reconcile_parallel_task(self, task_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        normalized_payload = dict(payload)
        if not _optional_str(normalized_payload.get("run_status")):
            artifact_payload = self._parallel_reconcile_payload_from_existing_run(task_id, normalized_payload)
            if artifact_payload.get("status") == "blocked":
                return artifact_payload
            normalized_payload.update(artifact_payload)
        run_status = _required_payload_str(normalized_payload, "run_status")
        verifier_summary = (
            normalized_payload.get("verifier_summary")
            if isinstance(normalized_payload.get("verifier_summary"), Mapping)
            else {}
        )
        try:
            return _sanitize_parallel_payload(
                self._parallel_coordinator().reconcile_managed_run(
                    task_id,
                    run_status=run_status,
                    verifier_status=_optional_str(normalized_payload.get("verifier_status")),
                    changed_files=_string_list(normalized_payload.get("changed_files")),
                    verifier_summary=verifier_summary,
                    blocker=_sanitize_optional_parallel_input_text(normalized_payload.get("blocker")),
                )
            )
        except (ParallelCoordinatorError, ParallelLedgerError) as exc:
            raise BadRequestError(str(exc)) from exc

    def _parallel_reconcile_payload_from_existing_run(self, task_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        run_id = _sanitize_optional_parallel_input_text(payload.get("run_id")) or _sanitize_optional_parallel_input_text(
            payload.get("real_job_id")
        )
        if not run_id:
            try:
                run_id = self._parallel_ledger().get_task(task_id).managed_run_id
            except ParallelLedgerError as exc:
                return {"status": "blocked", "blocker": str(exc)}
        if not run_id:
            return {"status": "blocked", "blocker": "run_id is required when run_status is not provided"}
        jobs = self._read_collection("real_runs")
        raw_job = jobs.get(run_id)
        if isinstance(raw_job, Mapping):
            job = self.get_real_run_job(run_id)
            run_status = _parallel_status_from_run_status(job.get("status"))
            if run_status in {"running", "managed_run_running"}:
                return {
                    "run_status": "running",
                    "verifier_status": job.get("verifier_status"),
                    "changed_files": job.get("changed_files", []),
                    "verifier_summary": {
                        "source": "real_run_job",
                        "real_job_id": run_id,
                        "job_status": job.get("status"),
                        "verifier_status": job.get("verifier_status"),
                    },
                }
            if run_status in {"passed", "failed", "blocked"}:
                verifier_status = _optional_str(job.get("verifier_status"))
                if run_status == "passed" and not verifier_status:
                    return {
                        "status": "blocked",
                        "blocker": f"real run {run_id} is terminal but verifier_status is missing",
                        "run_id": run_id,
                    }
                return {
                    "run_status": run_status,
                    "verifier_status": verifier_status,
                    "changed_files": job.get("changed_files", []),
                    "blocker": job.get("blocker_reason"),
                    "verifier_summary": {
                        "source": "real_run_job",
                        "real_job_id": run_id,
                        "job_status": job.get("status"),
                        "verifier_status": verifier_status,
                        "handoff_present": bool(job.get("handoff_path")),
                        "changed_files_count": len(job.get("changed_files") or []),
                    },
                }
        try:
            summary = self.get_run_summary(run_id)
        except Exception:
            return {
                "status": "blocked",
                "blocker": f"run report/artifact not found for {run_id}; provide run_status explicitly or wait for run artifacts",
                "run_id": run_id,
            }
        run_status = _parallel_status_from_run_status(summary.get("status"))
        verifier_status = _optional_str(summary.get("verifier_status"))
        if run_status == "passed" and not verifier_status:
            return {
                "status": "blocked",
                "blocker": f"run {run_id} is terminal but verifier_status is missing",
                "run_id": run_id,
            }
        return {
            "run_status": run_status,
            "verifier_status": verifier_status,
            "changed_files": summary.get("changed_files", []),
            "blocker": summary.get("blocker_reason") or summary.get("blocker"),
            "verifier_summary": {
                "source": "run_summary",
                "run_id": run_id,
                "status": summary.get("status"),
                "verifier_status": verifier_status,
                "changed_files_count": len(summary.get("changed_files") or []),
            },
        }

    def list_parallel_candidates(
        self,
        *,
        target_id: str | None = None,
        promotion_epoch: str | None = None,
    ) -> dict[str, Any]:
        try:
            return _sanitize_parallel_payload(
                self._parallel_coordinator().list_candidates(
                    target_id=target_id,
                    promotion_epoch=promotion_epoch,
                )
            )
        except (ParallelCoordinatorError, ParallelLedgerError) as exc:
            raise BadRequestError(str(exc)) from exc

    def promote_parallel_task(self, task_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        mode = _optional_str(payload.get("mode")) or "dry_run"
        real_bridge = _bool_from_payload(payload.get("allow_real_production_promotion")) or mode == "real_production_bridge"
        if real_bridge:
            return self._parallel_real_production_bridge(task_id, payload)
        try:
            return _sanitize_parallel_payload(
                self._parallel_coordinator().promote_task(
                    task_id,
                    allow_auto_first_promotion=_bool_from_payload(payload.get("allow_auto_first_promotion")),
                    mode=mode,  # type: ignore[arg-type]
                )
            )
        except (ParallelCoordinatorError, ParallelLedgerError) as exc:
            raise BadRequestError(str(exc)) from exc

    def promote_next_parallel_candidate(self, target_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        self._target_config_by_id(target_id)
        mode = _optional_str(payload.get("mode")) or "dry_run"
        real_bridge = _bool_from_payload(payload.get("allow_real_production_promotion")) or mode == "real_production_bridge"
        if real_bridge:
            return self._parallel_next_real_production_bridge(target_id, payload)
        try:
            return _sanitize_parallel_payload(
                self._parallel_coordinator().promote_next_safe_candidate(
                    target_id,
                    promotion_epoch=_sanitize_optional_parallel_input_text(payload.get("promotion_epoch")),
                    allow_auto_first_promotion=_bool_from_payload(payload.get("allow_auto_first_promotion")),
                    mode=mode,  # type: ignore[arg-type]
                )
            )
        except (ParallelCoordinatorError, ParallelLedgerError) as exc:
            raise BadRequestError(str(exc)) from exc

    def _parallel_real_production_bridge(self, task_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        if not _bool_from_payload(payload.get("allow_auto_first_promotion")):
            return {
                "status": "blocked",
                "task_id": task_id,
                "blocker": "allow_auto_first_promotion=true is required before production bridge",
                "real_production_lane_started": False,
            }
        mode = self._parallel_production_bridge_runtime_mode()
        if mode == "stub":
            result = self._parallel_coordinator().promote_task(
                task_id,
                allow_auto_first_promotion=True,
                mode="fake_complete",
            )
            result["allow_real_production_promotion"] = True
            result["real_production_lane_started"] = False
            result["production_bridge_mode"] = "stub"
            if result.get("allowed") is True:
                result["status"] = "production_bridge_stubbed"
                result["production_bridge_stubbed"] = True
            else:
                result["production_bridge_stubbed"] = False
            return _sanitize_parallel_payload(result)
        return {
            "status": "blocked",
            "task_id": task_id,
            "blocker": "real production bridge is disabled by default; this MVP does not start the real production lane",
            "allow_real_production_promotion": True,
            "real_production_lane_started": False,
            "required_future_gate": "wire to existing start_wb_core_production_lane after target lock/preflight approval",
        }

    def _parallel_next_real_production_bridge(self, target_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        if not _bool_from_payload(payload.get("allow_auto_first_promotion")):
            return {
                "status": "blocked",
                "target_id": target_id,
                "blocker": "allow_auto_first_promotion=true is required before production bridge",
                "real_production_lane_started": False,
            }
        candidate = self._parallel_ledger().select_first_finished_eligible_candidate(
            target_id=target_id,
            promotion_epoch=_sanitize_optional_parallel_input_text(payload.get("promotion_epoch")),
        )
        if candidate is None:
            return {
                "status": "blocked",
                "target_id": target_id,
                "blocker": "no eligible promotion candidate",
                "real_production_lane_started": False,
            }
        return self._parallel_real_production_bridge(candidate.task_id, payload)

    def list_parallel_promotion_groups(self, *, target_id: str | None = None) -> dict[str, Any]:
        self.reconcile_parallel_promotion_groups()
        groups = []
        for item in self._read_collection(PROMOTION_GROUP_COLLECTION).values():
            if not isinstance(item, Mapping):
                continue
            group = group_from_mapping(item)
            if target_id and group.target_id != target_id:
                continue
            payload = group.to_dict()
            payload["run_id"] = group.group_id
            payload["run_type"] = "group_promotion"
            decorate_operator_lifecycle(payload)
            groups.append(_sanitize_parallel_payload(payload))
        groups.sort(key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""), reverse=True)
        return {"status": "ok", "groups": groups}

    def get_parallel_promotion_group(self, group_id: str) -> dict[str, Any]:
        group_id = safe_state_component(group_id, "group_id")
        self.reconcile_parallel_promotion_groups()
        group = self._read_collection(PROMOTION_GROUP_COLLECTION).get(group_id)
        if not isinstance(group, Mapping):
            raise NotFoundError(f"parallel promotion group not found: {group_id}")
        payload = group_from_mapping(group).to_dict()
        payload["run_id"] = group_id
        payload["run_type"] = "group_promotion"
        decorate_operator_lifecycle(payload)
        return {"status": "ok", "group": _sanitize_parallel_payload(payload)}

    def cancel_parallel_promotion_group(self, group_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        group_id = safe_state_component(group_id, "group_id")
        reason = sanitize_terminal_text(str(payload.get("reason") or "operator cancelled promotion group"))[:700]
        updated = self._update_parallel_promotion_group(
            group_id,
            status="cancelled",
            current_step="cancelled",
            blocker=reason,
            cancelled_at=_now_utc(),
            finished_at=_now_utc(),
        )
        if updated is None:
            raise NotFoundError(f"parallel promotion group not found: {group_id}")
        return {"status": "cancelled", "group_id": group_id, "group": self.get_parallel_promotion_group(group_id).get("group")}

    def _cancel_parallel_promotion_child(self, run_id: str, reason: str) -> dict[str, Any] | None:
        groups = self._read_collection(PROMOTION_GROUP_COLLECTION)
        for group_id, raw in groups.items():
            if not isinstance(raw, Mapping):
                continue
            selected = [str(item) for item in raw.get("selected_ids") or []]
            per_task = dict(raw.get("per_task_status") or {})
            if run_id not in selected and run_id not in per_task:
                continue
            current_child_status = str(per_task.get(run_id) or "")
            if current_child_status == "production_complete":
                return {
                    "status": "blocked",
                    "run_id": run_id,
                    "blocker": "cannot cancel a child that is already production_complete",
                    "group": self.get_parallel_promotion_group(str(group_id)).get("group"),
                }
            per_task[run_id] = "blocked_by_operator"
            updated = self._update_parallel_promotion_group(
                str(group_id),
                per_task_status=per_task,
                blocker=reason or "Остановлено оператором",
                current_step="blocked_by_operator",
                finished_at=raw.get("finished_at") or _now_utc(),
            )
            if updated is None:
                continue
            run = self.live_run_detail(run_id).get("run")
            return {"status": "blocked_by_operator", "run_id": run_id, "group_id": str(group_id), "run": run}
        return None

    def reconcile_parallel_promotion_groups(self) -> dict[str, Any]:
        groups = self._read_collection(PROMOTION_GROUP_COLLECTION)
        changed = False
        updates: list[dict[str, Any]] = []
        bridge_available = self._parallel_production_bridge_runtime_mode() in {"stub", "live"}
        for group_id, raw in list(groups.items()):
            if not isinstance(raw, Mapping):
                continue
            group = dict(raw)
            status = str(group.get("status") or "")
            step = str(group.get("current_step") or "")
            conflict_migration = _reconcile_legacy_conflict_group(group)
            if conflict_migration:
                group.update(conflict_migration)
                groups[group_id] = _json_ready(group)
                changed = True
                updates.append(
                    {
                        "group_id": str(group_id),
                        "status": str(group.get("status") or ""),
                        "blocker": str(group.get("blocker") or ""),
                    }
                )
                status = str(group.get("status") or "")
                step = str(group.get("current_step") or "")
            if status in PROMOTION_GROUP_TERMINAL_STATUSES:
                continue
            blocker = ""
            next_status = ""
            next_step = ""
            if status in PROMOTION_GROUP_ACTIVE_STATUSES and step in {"", "planned", "plan_ready", "waiting"}:
                if group.get("allow_real_production_promotion") and not bridge_available:
                    next_status = "blocked"
                    next_step = "blocked"
                    blocker = (
                        "Real production bridge for selected Merge & Deploy is disabled; "
                        "RunArtifactPromotionAdapter is required before managed run artifacts can be applied."
                    )
                elif self._promotion_group_age_seconds(group) >= PROMOTION_GROUP_PLAN_TTL_SECONDS:
                    next_status = "expired"
                    next_step = "expired"
                    blocker = "promotion group plan expired without a backend worker or production bridge action"
            if not next_status:
                continue
            timestamp = _now_utc()
            group.update(
                {
                    "status": next_status,
                    "current_step": next_step,
                    "blocker": blocker,
                    "updated_at": timestamp,
                    "finished_at": timestamp,
                    "expired_at": timestamp if next_status == "expired" else group.get("expired_at"),
                }
            )
            groups[group_id] = _json_ready(group)
            changed = True
            updates.append({"group_id": group_id, "status": next_status, "blocker": blocker})
        if changed:
            self._write_collection(PROMOTION_GROUP_COLLECTION, groups)
        return {"status": "ok", "updated": updates}

    def _update_parallel_promotion_group(self, group_id: str, **updates: Any) -> dict[str, Any] | None:
        groups = self._read_collection(PROMOTION_GROUP_COLLECTION)
        existing = groups.get(group_id)
        if not isinstance(existing, Mapping):
            return None
        group = dict(existing)
        group.update(_json_ready(updates))
        group["updated_at"] = _now_utc()
        groups[group_id] = _json_ready(group)
        self._write_collection(PROMOTION_GROUP_COLLECTION, groups)
        return group

    def _record_selected_promotion_attempt(
        self,
        candidate: SelectedPromotionCandidate,
        *,
        status: str,
        blocker: str | None,
        plan: Any | None = None,
        current_stage: str | None = None,
        extra: Mapping[str, Any] | None = None,
    ) -> None:
        attempts = self._read_collection(PROMOTION_SELECTION_ATTEMPTS_COLLECTION)
        timestamp = _now_utc()
        payload = {
            "selected_id": candidate.selected_id,
            "candidate_id": candidate.candidate_id,
            "selection_type": candidate.selection_type,
            "target_id": candidate.target_id,
            "source_kind": candidate.source_kind,
            "status": status,
            "current_stage": current_stage or ("selected_promotion_blocked" if blocker else "selected_promotion_planned"),
            "blocker": blocker,
            "plan_status": getattr(plan, "status", None),
            "updated_at": timestamp,
        }
        if extra:
            payload.update(_json_ready(dict(extra)))
        attempts[candidate.selected_id] = _json_ready(payload)
        self._write_collection(PROMOTION_SELECTION_ATTEMPTS_COLLECTION, attempts)

    def _complete_refreshed_source_candidate(
        self,
        candidate: SelectedPromotionCandidate,
        production_result: Mapping[str, Any],
    ) -> None:
        candidate_ids = {
            str(candidate.selected_id or ""),
            str(candidate.candidate_id or ""),
            str(candidate.managed_run_id or ""),
            str(candidate.task_id or ""),
        }
        real_runs = self._read_collection("real_runs")
        for real_id, raw_real in real_runs.items():
            if not isinstance(raw_real, Mapping):
                continue
            if str(raw_real.get("run_id") or "") in candidate_ids:
                candidate_ids.add(str(real_id))
        candidate_ids.discard("")

        refresh_plans = self._read_collection(PROMOTION_REFRESH_PLAN_COLLECTION)
        groups = self._read_collection(PROMOTION_GROUP_COLLECTION)
        changed = False
        for raw_plan in refresh_plans.values():
            if not isinstance(raw_plan, Mapping):
                continue
            refresh_ids = {
                str(raw_plan.get("refresh_run_id") or ""),
                str(raw_plan.get("refresh_task_id") or ""),
                str(raw_plan.get("task_spec_id") or ""),
            }
            refresh_ids.discard("")
            if not refresh_ids.intersection(candidate_ids):
                continue
            group_id = str(raw_plan.get("group_id") or "")
            source_id = str(raw_plan.get("source_candidate_id") or raw_plan.get("source_run_id") or "")
            if not group_id or not source_id:
                continue
            raw_group = groups.get(group_id)
            if not isinstance(raw_group, Mapping):
                continue
            group = dict(raw_group)
            per_task = dict(group.get("per_task_status") or {})
            per_task[source_id] = "production_complete"
            group["per_task_status"] = per_task
            group["status"] = "production_complete" if per_task and all(
                str(status) == "production_complete" for status in per_task.values()
            ) else str(group.get("status") or "partially_deployed")
            if group["status"] == "production_complete":
                group["current_step"] = "production_complete"
                group["blocker"] = None
                group["recommended_action"] = None
                group["conflict_files"] = []
                group["conflict_reason_by_task"] = {}
                group["finished_at"] = _now_utc()
            group["updated_at"] = _now_utc()
            for field in ("deferred_task_ids", "refresh_required_ids", "conflicted_ids", "blocked_ids"):
                group[field] = [str(item) for item in group.get(field) or [] if str(item) != source_id]
            production_run_id = str(production_result.get("run_id") or "")
            pr_url = str(production_result.get("target_pr_url") or production_result.get("pr_url") or "")
            merge_commit = str(production_result.get("merge_commit") or "")
            if production_run_id:
                group["production_run_id"] = production_run_id
                group["production_run_ids"] = _unique_strings([*(group.get("production_run_ids") or []), production_run_id])
            if pr_url:
                group["pr_urls"] = _unique_strings([*(group.get("pr_urls") or []), pr_url])
            if merge_commit:
                group["merge_commits"] = _unique_strings([*(group.get("merge_commits") or []), merge_commit])
            group["deploy_status"] = production_result.get("deploy_status") or group.get("deploy_status")
            group["public_verify_status"] = production_result.get("public_verify_status") or group.get("public_verify_status")
            groups[group_id] = _json_ready(group)
            changed = True
        if changed:
            self._write_collection(PROMOTION_GROUP_COLLECTION, groups)

    def _apply_selected_promotion_attempt(self, summary: dict[str, Any], attempts: Mapping[str, Any]) -> None:
        run_id = str(summary.get("run_id") or "")
        if not run_id:
            return
        attempt = attempts.get(run_id) or attempts.get(str(summary.get("task_id") or ""))
        if not isinstance(attempt, Mapping):
            return
        if summary.get("operator_lifecycle_status") == "production_complete":
            return
        blocker = str(attempt.get("blocker") or "").strip()
        status = str(attempt.get("status") or "blocked")
        if blocker or status in {"promotion_running", "production_complete", "deploy_passed", "post_deploy_passed"}:
            for key in (
                "operator_lifecycle",
                "operator_lifecycle_status",
                "operator_lifecycle_label",
                "operator_lifecycle_tone",
                "operator_time_summary",
                "promotion_selectable",
                "promotion_selection_reason",
            ):
                summary.pop(key, None)
            summary["status"] = status
            summary["display_status"] = status
            summary["effective_status"] = status
            summary["current_stage"] = str(attempt.get("current_stage") or status)
            summary["blocker"] = blocker
            summary["promotion_attempt"] = _sanitize_parallel_payload(dict(attempt))
            summary["updated_at"] = attempt.get("updated_at") or summary.get("updated_at")
            summary["active"] = status == "promotion_running"
            for key in ("production_run_id", "pr_url", "merge_commit", "deploy_status", "public_verify_status"):
                if attempt.get(key):
                    summary[key] = attempt.get(key)
            decorate_operator_lifecycle(summary)

    def _promotion_group_child_overrides(self) -> dict[str, dict[str, Any]]:
        overrides: dict[str, dict[str, Any]] = {}
        refresh_plans_by_source: dict[str, Mapping[str, Any]] = {}
        for raw_plan in self._read_collection(PROMOTION_REFRESH_PLAN_COLLECTION).values():
            if not isinstance(raw_plan, Mapping):
                continue
            source_run_id = str(raw_plan.get("source_run_id") or "")
            if not source_run_id:
                continue
            current = refresh_plans_by_source.get(source_run_id)
            if current and str(current.get("updated_at") or "") > str(raw_plan.get("updated_at") or ""):
                continue
            refresh_plans_by_source[source_run_id] = raw_plan
        for raw in self._read_collection(PROMOTION_GROUP_COLLECTION).values():
            if not isinstance(raw, Mapping):
                continue
            group = group_from_mapping(raw).to_dict()
            group_id = str(group.get("group_id") or "")
            if not group_id:
                continue
            updated_at = str(group.get("updated_at") or group.get("finished_at") or group.get("created_at") or "")
            group_status = str(group.get("status") or "")
            current_step = str(group.get("current_step") or group_status)
            per_task = group.get("per_task_status") if isinstance(group.get("per_task_status"), Mapping) else {}
            group_blocker = _joined_blockers(group)
            terminal_conflict_group = (
                group_status in {"blocked", "blocked_by_conflict", "partially_deployed", "partial_group_blocked", "partial_group_complete_with_blockers"}
                and (
                    bool(group.get("conflicted_ids") or group.get("refresh_required_ids"))
                    or _selected_promotion_has_conflict(group_blocker)
                    or "selected_production_bridge_blocked" in current_step
                )
            )
            deferred_ids = {str(item) for item in group.get("deferred_task_ids") or [] if str(item)}
            conflict_reason_by_task = group.get("conflict_reason_by_task") if isinstance(group.get("conflict_reason_by_task"), Mapping) else {}
            group_conflicted_ids = {str(item) for item in group.get("conflicted_ids") or [] if str(item)}
            group_refresh_required_ids = {str(item) for item in group.get("refresh_required_ids") or [] if str(item)}
            selected_ids = [str(item) for item in group.get("selected_ids") or [] if str(item)]
            planned_order = [str(item) for item in group.get("planned_order") or selected_ids if str(item)]
            child_ids = list(dict.fromkeys([*selected_ids, *[str(item) for item in per_task.keys() if str(item)]]))
            for child_id in child_ids:
                child_status = str(per_task.get(child_id) or "")
                if not child_status and group_status == "production_complete":
                    child_status = "production_complete"
                if (
                    terminal_conflict_group
                    and child_status in {"production_lane_running", "promotion_running", "auto_promoting_first", ""}
                ):
                    child_status = "ready_for_separate_deploy" if child_id in group_conflicted_ids or child_id in deferred_ids else "refresh_required"
                    if child_status == "refresh_required" and child_id not in group_refresh_required_ids:
                        group_refresh_required_ids.add(child_id)
                if child_status not in {
                    "production_complete",
                    "production_lane_running",
                    "blocked",
                    "blocked_by_operator",
                    "ready_for_separate_deploy",
                    "refresh_required",
                    "conflict_detected",
                    "blocked_by_conflict",
                    "needs_rework",
                }:
                    continue
                previous = overrides.get(child_id)
                if previous and str(previous.get("updated_at") or "") > updated_at:
                    continue
                status = {
                    "production_complete": "production_complete",
                    "production_lane_running": "promotion_running",
                    "blocked": "blocked",
                    "blocked_by_operator": "blocked_by_operator",
                    "ready_for_separate_deploy": "ready_for_separate_deploy",
                    "refresh_required": "refresh_required",
                    "conflict_detected": "conflict_detected",
                    "blocked_by_conflict": "blocked_by_conflict",
                    "needs_rework": "needs_rework",
                }[child_status]
                index = planned_order.index(child_id) if child_id in planned_order else -1
                override: dict[str, Any] = {
                    "status": status,
                    "display_status": status,
                    "effective_status": status,
                    "current_stage": "production_complete" if child_status == "production_complete" else current_step,
                    "selected_promotion_group_id": group_id,
                    "group_id": group_id,
                    "promotion_group_status": group_status,
                    "promotion_group_child_status": child_status,
                    "updated_at": updated_at,
                    "active": child_status == "production_lane_running",
                }
                if child_status == "production_complete":
                    override["blocker"] = None
                    override["finished_at"] = group.get("finished_at") or updated_at
                    override["deploy_status"] = group.get("deploy_status")
                    override["public_verify_status"] = group.get("public_verify_status")
                    override["production_run_id"] = _indexed(group.get("production_run_ids"), index) or group.get("production_run_id")
                    override["pr_url"] = _indexed(group.get("pr_urls"), index)
                    override["merge_commit"] = _indexed(group.get("merge_commits"), index)
                elif child_status in {"conflict_detected", "blocked_by_conflict", "needs_rework"}:
                    conflict_files = [str(item) for item in group.get("conflict_files") or [] if str(item)]
                    reason = _conflict_operator_reason(conflict_files, group.get("blocker"))
                    override["refresh_required"] = True
                    override["conflict_detected"] = True
                    override["conflict_files"] = conflict_files
                    override["recommended_action"] = group.get("recommended_action") or _refresh_candidate_recommendation()
                    override["blocker"] = reason
                elif child_status == "ready_for_separate_deploy":
                    conflict_files = [str(item) for item in group.get("conflict_files") or [] if str(item)]
                    reason = str(conflict_reason_by_task.get(child_id) or group.get("blocker") or "conflict with selected group; deploy separately")
                    override["deferred_for_separate_deploy"] = True
                    override["conflict_detected"] = bool(conflict_files or reason)
                    override["conflict_files"] = conflict_files
                    override["separate_deploy_reason"] = reason
                    override["recommended_action"] = group.get("recommended_action") or "Запустите отдельный Merge & Deploy для этой задачи."
                    override["blocker"] = None
                elif child_status == "blocked_by_operator":
                    override["blocker"] = "Остановлено оператором"
                elif child_status == "blocked":
                    override["blocker"] = group.get("blocker") or "selected promotion group blocked"
                elif child_status == "refresh_required":
                    override["refresh_required"] = True
                    override["recommended_action"] = group.get("recommended_action") or _refresh_candidate_recommendation()
                    override["blocker"] = group.get("blocker") or _conflict_operator_reason([], None)
                refresh_plan = refresh_plans_by_source.get(child_id)
                if isinstance(refresh_plan, Mapping):
                    override["refresh_plan_id"] = refresh_plan.get("refresh_plan_id")
                    override["refresh_task_id"] = refresh_plan.get("refresh_task_id")
                    override["refreshed_candidate_id"] = refresh_plan.get("refresh_run_id") or refresh_plan.get("refresh_task_id")
                    override["refresh_run_id"] = refresh_plan.get("refresh_run_id")
                    override["refresh_status"] = refresh_plan.get("status")
                overrides[child_id] = _json_ready(override)
        return overrides

    def _apply_promotion_group_child_override(self, summary: dict[str, Any], overrides: Mapping[str, Any]) -> None:
        run_id = str(summary.get("run_id") or "")
        if not run_id:
            return
        override = overrides.get(run_id) or overrides.get(str(summary.get("task_id") or ""))
        if not isinstance(override, Mapping):
            return
        for key in (
            "operator_lifecycle",
            "operator_lifecycle_status",
            "operator_lifecycle_label",
            "operator_lifecycle_tone",
            "operator_time_summary",
            "promotion_selectable",
            "promotion_selection_reason",
        ):
            summary.pop(key, None)
        summary.update(_json_ready(dict(override)))
        decorate_operator_lifecycle(summary)

    def _promotion_group_age_seconds(self, group: Mapping[str, Any]) -> int:
        created = _parse_iso_utc(str(group.get("created_at") or ""))
        if created is None:
            return PROMOTION_GROUP_PLAN_TTL_SECONDS
        return max(0, int((datetime.now(timezone.utc) - created).total_seconds()))

    def _parallel_production_bridge_runtime_mode(self) -> str:
        configured = str(os.environ.get("DEV_CONTROL_PLANE_PARALLEL_PRODUCTION_BRIDGE_MODE") or "").strip().lower()
        if configured:
            return configured
        if str(os.environ.get(RUNTIME_PROFILE_ENV) or "").strip().lower() == HOSTED_RUNTIME_PROFILE:
            return "live"
        return ""

    def promote_parallel_selection(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        target_id = _required_payload_str(payload, "target_id")
        self._target_config_by_id(target_id)
        selected_ids = _string_list(payload.get("selected_ids"))
        if not selected_ids:
            raise BadRequestError("selected_ids is required")
        selection_type = _sanitize_optional_parallel_input_text(payload.get("selection_type")) or "auto"
        mode = _sanitize_optional_parallel_input_text(payload.get("mode")) or "auto_order"
        plan_only = _bool_from_payload(payload.get("plan_only"))
        dry_run = _bool_from_payload(payload.get("dry_run")) or plan_only
        confirm = _bool_from_payload(payload.get("confirm_merge_deploy"))
        candidates = [
            self._resolve_selected_promotion_candidate(target_id, selected_id, selection_type=selection_type)
            for selected_id in selected_ids
        ]
        allow_refresh = _bool_from_payload(payload.get("allow_refresh"))
        plan = plan_selected_promotion(candidates, target_id=target_id, mode=mode, allow_refresh=allow_refresh)
        plan_payload = _sanitize_parallel_payload(plan.to_dict())
        if plan_only:
            return {
                "status": "plan_ready" if plan.ordered else "blocked",
                "target_id": target_id,
                "selection_type": selection_type,
                "selected_ids": selected_ids,
                "plan": plan_payload,
                "group_created": False,
                "production_lane_started": False,
                "real_production_lane_started": False,
            }
        if len(selected_ids) == 1:
            return self._promote_single_selection(
                candidates[0],
                plan=plan,
                payload=payload,
                dry_run=dry_run,
                confirm=confirm,
            )
        return self._promote_group_selection(
            target_id,
            selected_ids,
            selection_type=selection_type,
            mode=mode,
            plan=plan,
            payload=payload,
            dry_run=dry_run,
            confirm=confirm,
        )

    def refresh_selected_candidate(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        target_id = _required_payload_str(payload, "target_id")
        self._target_config_by_id(target_id)
        source_id = (
            _sanitize_optional_parallel_input_text(payload.get("source_run_id"))
            or _sanitize_optional_parallel_input_text(payload.get("candidate_id"))
            or _sanitize_optional_parallel_input_text(payload.get("selected_id"))
        )
        if not source_id:
            raise BadRequestError("source_run_id or candidate_id is required")
        mode = _sanitize_optional_parallel_input_text(payload.get("mode")) or "managed_clone_only"
        if mode != "managed_clone_only":
            return {
                "status": "blocked",
                "target_id": target_id,
                "source_id": source_id,
                "blocker": "refresh candidate supports only managed_clone_only mode",
                "codex_started": False,
                "production_lane_started": False,
            }
        selection_type = _sanitize_optional_parallel_input_text(payload.get("selection_type")) or "auto"
        try:
            candidate = self._resolve_selected_promotion_candidate(target_id, source_id, selection_type=selection_type)
        except Exception:
            candidate = SelectedPromotionCandidate(
                candidate_id=source_id,
                selected_id=source_id,
                selection_type="run_id",
                target_id=target_id,
                source_kind="managed_run",
                status="verifier_passed",
                lifecycle_status="ready_for_promotion",
                managed_run_id=source_id,
            )
        source_run_id = candidate.managed_run_id or (candidate.candidate_id if candidate.source_kind == "managed_run" else None)
        if not source_run_id and source_id:
            try:
                self._run_dir_for_live_id(source_id)
                source_run_id = source_id
            except Exception:
                source_run_id = None
        if not source_run_id:
            return {
                "status": "blocked",
                "target_id": target_id,
                "source_id": source_id,
                "blocker": "refresh candidate requires a verifier-passed managed run_id with artifacts",
                "codex_started": False,
                "production_lane_started": False,
            }
        group_id = _sanitize_optional_parallel_input_text(payload.get("group_id"))
        allow_post_verifier_blocker = self._group_allows_refresh_for_child(group_id, source_run_id)
        artifacts = self._selected_refresh_source_artifacts(
            source_run_id,
            target_id=target_id,
            allow_post_verifier_blocker=allow_post_verifier_blocker,
        )
        conflict_files = _string_list(payload.get("conflict_files")) or artifacts["changed_files"]
        conflict_reason = (
            _sanitize_optional_parallel_input_text(payload.get("conflict_reason"))
            or _conflict_operator_reason(conflict_files, payload.get("blocker"))
        )
        prompt_excerpt = artifacts.get("prompt_excerpt") or ""
        handoff_excerpt = artifacts.get("handoff_excerpt") or ""
        task_text = _sanitize_parallel_input_text(
            "\n".join(
                [
                    "Пересобери intent исходной задачи поверх текущего main.",
                    "",
                    f"source_run_id: {source_run_id}",
                    f"group_id: {group_id or 'none'}",
                    f"conflict_reason: {conflict_reason}",
                    "conflict_files:",
                    *[f"- {item}" for item in conflict_files[:20]],
                    "previous_changed_files:",
                    *[f"- {item}" for item in artifacts["changed_files"][:40]],
                    "",
                    "Previous prompt excerpt:",
                    prompt_excerpt[:3000],
                    "",
                    "Previous handoff excerpt:",
                    handoff_excerpt[:5000],
                    "",
                    "Constraints:",
                    "- managed_clone_only only",
                    "- do not open PR, merge, deploy or run production lane",
                    "- preserve the original intent, resolve conflicts against current main, and produce a new handoff/verifier result",
                ]
            )
        )[:15000]
        if not _bool_from_payload(payload.get("confirm_start")):
            return {
                "status": "refresh_plan_ready",
                "target_id": target_id,
                "source_run_id": source_run_id,
                "group_id": group_id,
                "conflict_files": conflict_files,
                "recommended_action": _refresh_candidate_recommendation(),
                "blocker": "confirm_start=true is required to create a managed_clone_only refresh task",
                "task_created": False,
                "codex_started": False,
                "production_lane_started": False,
            }
        idempotency_key = (
            _sanitize_optional_parallel_input_text(payload.get("idempotency_key"))
            or f"refresh:{target_id}:{source_run_id}:{group_id or 'no-group'}"
        )
        task_result = self.submit_parallel_task(
            {
                "target_id": target_id,
                "task_text": task_text,
                "source": "selected_promotion_refresh",
                "source_id": source_run_id,
                "source_tool": "refresh_selected_candidate",
                "source_chat": _sanitize_optional_parallel_input_text(payload.get("source_chat")),
                "submitted_by": _sanitize_optional_parallel_input_text(payload.get("submitted_by")),
                "release_group": _sanitize_optional_parallel_input_text(payload.get("release_group")),
                "idempotency_key": idempotency_key,
            }
        )
        task_id = str(task_result.get("task_id") or "")
        refresh_plan_id = safe_state_component(
            f"refresh-plan-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{slug_state_component(source_run_id, fallback='run')[:48]}",
            "refresh_plan_id",
        )
        plans = self._read_collection(PROMOTION_REFRESH_PLAN_COLLECTION)
        existing_plan = next(
            (
                dict(raw)
                for raw in plans.values()
                if isinstance(raw, Mapping) and str(raw.get("idempotency_key") or "") == idempotency_key
            ),
            None,
        )
        if existing_plan is not None:
            refresh_plan = existing_plan
        else:
            refresh_plan = {
                "refresh_plan_id": refresh_plan_id,
                "status": "refresh_task_submitted",
                "target_id": target_id,
                "source_run_id": source_run_id,
                "source_candidate_id": candidate.candidate_id,
                "refresh_task_id": task_id,
                "group_id": group_id,
                "conflict_files": conflict_files,
                "previous_changed_files": artifacts["changed_files"],
                "conflict_reason": conflict_reason,
                "mode": "managed_clone_only",
                "created_at": _now_utc(),
                "updated_at": _now_utc(),
                "idempotency_key": idempotency_key,
                "recommended_action": "Запустите managed-clone refresh task, затем продвигайте новый verifier-passed candidate обычным selected Merge & Deploy.",
                "codex_started": False,
                "production_lane_started": False,
            }
            plans[refresh_plan_id] = _json_ready(refresh_plan)
            self._write_collection(PROMOTION_REFRESH_PLAN_COLLECTION, plans)
        start_managed_run = _bool_from_payload(payload.get("start_managed_run"))
        run_start: dict[str, Any] | None = None
        if start_managed_run:
            if refresh_plan.get("refresh_run_id"):
                run_start = {
                    "status": "already_started",
                    "run_id": refresh_plan.get("refresh_run_id"),
                    "task_spec_id": refresh_plan.get("task_spec_id"),
                    "watch_url": refresh_plan.get("watch_url"),
                    "live_url": refresh_plan.get("live_url"),
                    "codex_started": True,
                }
            else:
                run_start = self._start_refresh_managed_clone_run(
                    target_id=target_id,
                    source_run_id=source_run_id,
                    group_id=group_id,
                    task_id=task_id,
                    task_text=task_text,
                    conflict_files=conflict_files,
                    changed_files=artifacts["changed_files"],
                )
                now = _now_utc()
                refresh_plan.update(
                    {
                        "status": "refresh_managed_run_started",
                        "refresh_run_id": run_start.get("run_id"),
                        "task_spec_id": run_start.get("task_spec_id"),
                        "watch_url": run_start.get("watch_url"),
                        "live_url": run_start.get("live_url"),
                        "codex_started": True,
                        "updated_at": now,
                    }
                )
                plans = self._read_collection(PROMOTION_REFRESH_PLAN_COLLECTION)
                plans[str(refresh_plan.get("refresh_plan_id") or refresh_plan_id)] = _json_ready(refresh_plan)
                self._write_collection(PROMOTION_REFRESH_PLAN_COLLECTION, plans)
                try:
                    ledger = self._parallel_ledger()
                    ledger.bind_managed_run(
                        task_id,
                        run_id=str(run_start.get("run_id") or ""),
                    )
                    self._write_parallel_ledger(ledger)
                except Exception:
                    pass
        return {
            "status": "refresh_managed_run_started" if run_start else "refresh_task_submitted",
            "target_id": target_id,
            "source_run_id": source_run_id,
            "task_id": task_id,
            "refresh_plan_id": refresh_plan.get("refresh_plan_id"),
            "refresh_run_id": (run_start or {}).get("run_id") or refresh_plan.get("refresh_run_id"),
            "task_spec_id": (run_start or {}).get("task_spec_id") or refresh_plan.get("task_spec_id"),
            "watch_url": (run_start or {}).get("watch_url") or refresh_plan.get("watch_url"),
            "live_url": (run_start or {}).get("live_url") or refresh_plan.get("live_url"),
            "group_id": group_id,
            "conflict_files": conflict_files,
            "refresh_plan": _sanitize_parallel_payload(refresh_plan),
            "task": task_result.get("task"),
            "execution_mode": "managed_clone_only",
            "codex_started": bool(run_start),
            "production_lane_started": False,
        }

    def _start_refresh_managed_clone_run(
        self,
        *,
        target_id: str,
        source_run_id: str,
        group_id: str | None,
        task_id: str,
        task_text: str,
        conflict_files: Sequence[str],
        changed_files: Sequence[str],
    ) -> dict[str, Any]:
        if str(os.environ.get("DEV_CONTROL_PLANE_REFRESH_MANAGED_RUN_MODE") or "").strip().lower() == "stub":
            with self._jobs_lock:
                jobs = self._read_collection("real_runs")
                run_id = _new_id("real-run", jobs)
                jobs[run_id] = {
                    "id": run_id,
                    "status": "queued",
                    "task_spec_id": f"stub-refresh-{task_id}",
                    "target_project_id": target_id,
                    "step_id": "step-001",
                    "codex_bin": "stub",
                    "run_id": run_id,
                    "run_dir": None,
                    "workspace_path": None,
                    "prompt_path": None,
                    "handoff_path": None,
                    "log_path": None,
                    "diff_path": None,
                    "verifier_status": None,
                    "changed_files": list(changed_files),
                    "blocker_reason": None,
                    "next_manual_step": None,
                    "created_at": _now_utc(),
                    "updated_at": _now_utc(),
                    "message": "Stubbed managed-clone refresh run for smoke tests.",
                    "errors": [],
                    "timeline_events": append_timeline_event(
                        (),
                        phase="queued",
                        title="Refresh candidate managed-clone run queued.",
                        source="system",
                    ),
                }
                self._write_collection("real_runs", jobs)
            return {
                "status": "started",
                "task_spec_id": f"stub-refresh-{task_id}",
                "run_id": run_id,
                    "watch_url": live_url(_public_base_url(), run_id),
                    "live_url": live_url(_public_base_url(), None),
                "codex_started": True,
                "stubbed": True,
            }
        task_spec_id = safe_state_component(
            f"task-refresh-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{slug_state_component(source_run_id, fallback='run')[:44]}",
            "task_spec_id",
        )
        allowed_paths = list(dict.fromkeys([*conflict_files, *changed_files]))
        if not allowed_paths:
            allowed_paths = ["packages/adapters/templates/**", "apps/**"]
        intent_hint = (
            "Original intent summary: Move the top source/header strip information into the Table block header area; "
            "include useful content and Load and refresh button compactly; avoid duplicate Asia/Yekaterinburg; "
            "presentation/layout only."
        )
        payload = {
            "id": task_spec_id,
            "version": "1.0",
            "status": "draft",
            "title": "Пересобрать selected-promotion candidate",
            "goal": "\n\n".join([intent_hint, task_text]),
            "scope": [
                "Rebuild the selected promotion candidate intent on current target main.",
                "Use managed_clone_only execution and produce a fresh handoff/verifier result.",
                f"source_run_id: {source_run_id}",
                f"group_id: {group_id or 'none'}",
                f"parallel_refresh_task_id: {task_id}",
            ],
            "not_in_scope": [
                "Do not open PR.",
                "Do not merge.",
                "Do not deploy.",
                "Do not run production lane.",
                "Do not change secrets or auth configuration.",
            ],
            "task_class": "L3",
            "class_reason": "Refresh/rework of a selected-promotion candidate after current main changed; execution boundary remains managed_clone_only.",
            "risks": [
                "Original diff no longer applies cleanly to current main.",
                "Generated refresh must be verifier-passed before any later selected Merge & Deploy.",
            ],
            "acceptance_criteria": [
                "Managed clone run completes with verifier passed or returns an exact blocker.",
                "Original intent is rebuilt against current target main.",
                "No PR, merge, deploy, production lane or direct target mutation is performed by the refresh run.",
            ],
            "required_smokes": ["git diff --check"],
            "allowed_paths": allowed_paths,
            "human_gates": ["Operator must later use selected Merge & Deploy separately after verifier passed."],
            "explicit_policy_note": "managed_clone_only refresh candidate; no production_lane in this run",
            "target_project_id": target_id,
            "sprint_steps": [
                {
                    "id": "step-001",
                    "sequence": 1,
                    "title": "Refresh conflicted candidate",
                    "goal": "\n\n".join([intent_hint, task_text]),
                    "task_class": "L3",
                    "scope": [
                        "Resolve selected-promotion conflict on current main.",
                        "Keep execution managed_clone_only.",
                    ],
                    "acceptance_criteria": [
                        "Verifier passes for the refreshed candidate or exact blocker is reported.",
                        "No production action is started.",
                    ],
                    "required_smokes": ["git diff --check"],
                    "stop_conditions": [
                        "Stop if the old intent cannot be safely rebuilt without human product decision.",
                        "Stop if production, merge or deploy would be required.",
                    ],
                }
            ],
        }
        created = self.create_task_spec(payload)
        frozen = self.freeze_task_spec(str(created["id"]), {})
        run = self.start_managed_codex_run(str(frozen["id"]), {"target_project_id": target_id})
        run_id = str(run.get("id") or "")
        return {
            "status": "started",
            "task_spec_id": frozen["id"],
            "run_id": run_id,
                "watch_url": live_url(_public_base_url(), run_id),
                "live_url": live_url(_public_base_url(), None),
            "codex_started": True,
        }

    def _group_allows_refresh_for_child(self, group_id: str | None, source_run_id: str) -> bool:
        if not group_id:
            return False
        try:
            group = self.get_parallel_promotion_group(group_id).get("group") or {}
        except Exception:
            return False
        if not isinstance(group, Mapping):
            return False
        child_status = str((group.get("per_task_status") or {}).get(source_run_id) or "") if isinstance(group.get("per_task_status"), Mapping) else ""
        return (
            source_run_id in {str(item) for item in group.get("conflicted_ids") or []}
            or source_run_id in {str(item) for item in group.get("refresh_required_ids") or []}
            or child_status in {"conflict_detected", "refresh_required", "blocked_by_conflict", "needs_rework", "blocked_by_operator"}
        )

    def _selected_refresh_source_artifacts(
        self,
        source_run_id: str,
        *,
        target_id: str,
        allow_post_verifier_blocker: bool = False,
    ) -> dict[str, Any]:
        source_run_id = safe_state_component(source_run_id, "source_run_id")
        try:
            source_run_dir = self._run_dir_for_live_id(source_run_id)
            source_record = load_run_record(source_run_dir)
        except Exception as exc:
            raise BadRequestError(f"refresh source managed run artifacts are unavailable: {_safe_text(exc)}") from exc
        result = source_record.get("result") if isinstance(source_record.get("result"), Mapping) else {}
        verifier = source_record.get("verifier") if isinstance(source_record.get("verifier"), Mapping) else {}
        source_target = str(result.get("target_project_id") or target_id)
        if source_target != target_id:
            raise BadRequestError(f"refresh source target mismatch: {source_target}")
        verifier_status = str(result.get("verifier_status") or verifier.get("status") or "").lower()
        if verifier_status != "passed":
            raise BadRequestError(f"refresh source verifier is not passed: {verifier_status or 'missing'}")
        if result.get("blocker_reason") and not allow_post_verifier_blocker:
            raise BadRequestError(f"refresh source has blocker: {result.get('blocker_reason')}")
        changed_files = [str(item) for item in (result.get("changed_files") or []) if str(item).strip()]
        if not changed_files:
            raise BadRequestError("refresh source changed_files are missing")
        diff_path = Path(str(result.get("diff_path") or source_run_dir / "artifacts" / "diff.patch")).resolve()
        handoff_path = Path(str(result.get("handoff_path") or source_run_dir / "artifacts" / "handoff.md")).resolve()
        prompt_path = Path(str(result.get("prompt_path") or source_run_dir / "artifacts" / "prompt.md")).resolve()
        for label, path in (("diff.patch", diff_path), ("handoff.md", handoff_path), ("prompt.md", prompt_path)):
            if not _is_relative_to(path, source_run_dir.resolve()) or not path.exists():
                raise BadRequestError(f"refresh source {label} artifact is missing")
        return {
            "changed_files": changed_files,
            "diff_path": str(diff_path),
            "handoff_path": str(handoff_path),
            "prompt_path": str(prompt_path),
            "prompt_excerpt": _read_run_artifact_preview(source_run_dir, prompt_path, limit=6000) or "",
            "handoff_excerpt": _read_run_artifact_preview(source_run_dir, handoff_path, limit=9000) or "",
        }

    def _promote_single_selection(
        self,
        candidate: SelectedPromotionCandidate,
        *,
        plan,
        payload: Mapping[str, Any],
        dry_run: bool,
        confirm: bool,
    ) -> dict[str, Any]:
        if not plan.ordered:
            return {
                "status": "blocked",
                "selection_kind": "single",
                "candidate": _sanitize_parallel_payload(candidate.to_dict()),
                "plan": _sanitize_parallel_payload(plan.to_dict()),
                "blocker": "selected candidate is not ready for promotion",
                "group_created": False,
                "production_lane_started": False,
                "real_production_lane_started": False,
            }
        if dry_run or not confirm:
            return {
                "status": "single_plan_ready",
                "selection_kind": "single",
                "candidate": _sanitize_parallel_payload(candidate.to_dict()),
                "plan": _sanitize_parallel_payload(plan.to_dict()),
                "group_created": False,
                "production_lane_started": False,
                "real_production_lane_started": False,
                "blocker": None if confirm else "confirm_merge_deploy=true is required to start promotion",
            }
        if candidate.managed_run_id and _bool_from_payload(payload.get("allow_real_production_promotion")):
            bridge_mode = self._parallel_production_bridge_runtime_mode()
            if bridge_mode == "live":
                self._record_selected_promotion_attempt(
                    candidate,
                    status="promotion_running",
                    blocker=None,
                    plan=plan,
                    current_stage="selected_production_bridge",
                )
                thread = threading.Thread(
                    target=self._selected_single_promotion_worker,
                    args=(candidate.to_dict(),),
                    daemon=True,
                )
                thread.start()
                return {
                    "status": "promotion_running",
                    "selection_kind": "single",
                    "candidate": _sanitize_parallel_payload(candidate.to_dict()),
                    "plan": _sanitize_parallel_payload(plan.to_dict()),
                    "group_created": False,
                    "production_lane_started": True,
                    "real_production_lane_started": True,
                }
            if bridge_mode != "stub":
                standalone_blocker = (
                    "real production bridge for standalone managed run_id requires hosted RunArtifactPromotionAdapter mode; "
                    "no direct production lane is started"
                )
                self._record_selected_promotion_attempt(candidate, status="blocked", blocker=standalone_blocker, plan=plan)
                return {
                    "status": "blocked",
                    "selection_kind": "single",
                    "candidate": _sanitize_parallel_payload(candidate.to_dict()),
                    "plan": _sanitize_parallel_payload(plan.to_dict()),
                    "blocker": standalone_blocker,
                    "group_created": False,
                    "production_lane_started": False,
                    "real_production_lane_started": False,
                    "exact_blocker": "selected run_id is verifier-passed but hosted selected production bridge is not enabled",
                }
        if candidate.task_id:
            result = self.promote_parallel_task(
                candidate.task_id,
                {
                    "allow_auto_first_promotion": _bool_from_payload(payload.get("allow_auto_first_promotion")) or confirm,
                    "allow_real_production_promotion": _bool_from_payload(payload.get("allow_real_production_promotion")),
                    "mode": "real_production_bridge"
                    if _bool_from_payload(payload.get("allow_real_production_promotion"))
                    else "fake_complete",
                },
            )
            result["selection_kind"] = "single"
            result["group_created"] = False
            result["selected_candidate_id"] = candidate.candidate_id
            if str(result.get("status") or "") == "blocked":
                self._record_selected_promotion_attempt(
                    candidate,
                    status="blocked",
                    blocker=str(result.get("blocker") or "selected promotion is blocked"),
                    plan=plan,
                )
            return _sanitize_parallel_payload(result)
        standalone_blocker = "selected candidate is not bound to a verifier-passed managed run artifact"
        self._record_selected_promotion_attempt(candidate, status="blocked", blocker=standalone_blocker, plan=plan)
        return {
            "status": "blocked",
            "selection_kind": "single",
            "candidate": _sanitize_parallel_payload(candidate.to_dict()),
            "plan": _sanitize_parallel_payload(plan.to_dict()),
            "blocker": standalone_blocker,
            "group_created": False,
            "production_lane_started": False,
            "real_production_lane_started": False,
            "exact_blocker": "selected run_id is verifier-passed but not bound to a parallel task candidate",
        }

    def _promote_group_selection(
        self,
        target_id: str,
        selected_ids: Sequence[str],
        *,
        selection_type: str,
        mode: str,
        plan,
        payload: Mapping[str, Any],
        dry_run: bool,
        confirm: bool,
    ) -> dict[str, Any]:
        timestamp = selected_now_utc()
        allow_real = _bool_from_payload(payload.get("allow_real_production_promotion"))
        bridge_mode = self._parallel_production_bridge_runtime_mode()
        bridge_blocker = None
        if plan.ordered and confirm and not dry_run:
            if not allow_real:
                bridge_blocker = "allow_real_production_promotion=true is required for selected Merge & Deploy"
            elif bridge_mode not in {"stub", "live"}:
                bridge_blocker = (
                    "Real production bridge for selected Merge & Deploy is disabled; "
                    "RunArtifactPromotionAdapter is required before managed run artifacts can be applied."
                )
        start_live_bridge = bool(plan.ordered and confirm and not dry_run and allow_real and bridge_mode == "live" and not bridge_blocker)
        if start_live_bridge:
            group_status = "promotion_running"
        elif plan.ordered:
            group_status = "planned"
        elif plan.deferred and not plan.blocked and not plan.refresh_required:
            group_status = "ready_for_separate_deploy"
        else:
            group_status = "blocked"
        current_step = "selected_production_bridge" if start_live_bridge else "plan_ready"
        group_blocker = None if plan.ordered or plan.deferred else "no selected candidates are ready for promotion"
        if not plan.ordered and plan.deferred:
            current_step = "deferred_only"
        if bridge_blocker:
            group_status = "blocked"
            current_step = "blocked"
            group_blocker = bridge_blocker
        group = SelectedPromotionGroup(
            group_id=new_group_id(),
            target_id=target_id,
            selected_ids=tuple(selected_ids),
            selection_type=selection_type,
            mode=mode,
            status=group_status,
            created_at=timestamp,
            updated_at=timestamp,
            planned_order=tuple(candidate.candidate_id for candidate in plan.ordered),
            accepted_task_ids=tuple(candidate.candidate_id for candidate in plan.ordered),
            deferred_task_ids=tuple(candidate.candidate_id for candidate in plan.deferred),
            blocked_ids=tuple(candidate.candidate_id for candidate in plan.blocked),
            refresh_required_ids=tuple(candidate.candidate_id for candidate in plan.refresh_required),
            current_step=current_step,
            per_task_status={
                **{candidate.candidate_id: ("production_lane_running" if start_live_bridge else ("blocked" if bridge_blocker else "planned")) for candidate in plan.ordered},
                **{candidate.candidate_id: "ready_for_separate_deploy" for candidate in plan.deferred},
                **{candidate.candidate_id: "blocked" for candidate in plan.blocked},
                **{candidate.candidate_id: "refresh_required" for candidate in plan.refresh_required},
            },
            conflict_reason_by_task=dict(plan.conflict_reason_by_task),
            conflict_files=tuple(
                sorted({path for candidate in plan.deferred for path in candidate.changed_files})
            ),
            recommended_action="Запустите отдельный Merge & Deploy для deferred-задач." if plan.deferred else None,
            blocker=group_blocker,
            finished_at=timestamp if bridge_blocker or (not plan.ordered and plan.deferred) else None,
            confirm_merge_deploy=confirm,
            allow_real_production_promotion=allow_real,
        )
        groups = self._read_collection(PROMOTION_GROUP_COLLECTION)
        groups[group.group_id] = _json_ready(group.to_dict())
        self._write_collection(PROMOTION_GROUP_COLLECTION, groups)
        if start_live_bridge:
            thread = threading.Thread(
                target=self._selected_group_promotion_worker,
                args=(group.group_id, [candidate.to_dict() for candidate in plan.ordered]),
                daemon=True,
            )
            thread.start()
        result = {
            "status": "promotion_running" if start_live_bridge else ("blocked" if bridge_blocker or (not plan.ordered and not plan.deferred) else ("ready_for_separate_deploy" if not plan.ordered and plan.deferred else "group_plan_ready")),
            "selection_kind": "group",
            "target_id": target_id,
            "group_id": group.group_id,
            "group": _sanitize_parallel_payload(group.to_dict()),
            "plan": _sanitize_parallel_payload(plan.to_dict()),
            "accepted_task_ids": [candidate.candidate_id for candidate in plan.ordered],
            "deferred_task_ids": [candidate.candidate_id for candidate in plan.deferred],
            "conflict_detected": bool(plan.deferred),
            "conflict_files": sorted({path for candidate in plan.deferred for path in candidate.changed_files}),
            "conflict_reason_by_task": dict(plan.conflict_reason_by_task),
            "recommended_action": "Запустите отдельный Merge & Deploy для deferred-задач." if plan.deferred else None,
            "group_created": True,
            "dry_run": dry_run,
            "confirm_merge_deploy": confirm,
            "production_lane_started": start_live_bridge,
            "real_production_lane_started": start_live_bridge,
        }
        if bridge_blocker:
            result["blocker"] = bridge_blocker
            result["exact_blocker"] = bridge_blocker
        if not confirm:
            result["blocker"] = "confirm_merge_deploy=true is required to start group promotion"
        if dry_run:
            result["blocker"] = result.get("blocker") or "dry_run=true; no production lane started"
        return result

    def _selected_single_promotion_worker(self, candidate_payload: Mapping[str, Any]) -> None:
        candidate = candidate_from_mapping(candidate_payload)
        try:
            self._record_selected_promotion_attempt(
                candidate,
                status="promotion_running",
                blocker=None,
                current_stage="selected_production_bridge",
            )
            result = self._execute_selected_managed_run_production(candidate)
            status = "production_complete" if result.get("status") == "post_deploy_passed" else "blocked"
            self._record_selected_promotion_attempt(
                candidate,
                status=status,
                blocker=None if status == "production_complete" else _joined_blockers(result),
                current_stage=str(result.get("status") or status),
                extra={
                    "production_run_id": result.get("run_id"),
                    "pr_url": result.get("target_pr_url"),
                    "merge_commit": result.get("merge_commit"),
                    "deploy_status": result.get("deploy_status"),
                    "public_verify_status": result.get("public_verify_status"),
                },
            )
            if status == "production_complete":
                self._complete_refreshed_source_candidate(candidate, result)
        except Exception as exc:
            self._record_selected_promotion_attempt(
                candidate,
                status="blocked",
                blocker=_safe_text(exc),
                current_stage="selected_production_bridge_blocked",
            )

    def _selected_group_promotion_worker(self, group_id: str, candidate_payloads: Sequence[Mapping[str, Any]]) -> None:
        production_run_ids: list[str] = []
        pr_urls: list[str] = []
        merge_commits: list[str] = []
        per_task_status: dict[str, str] = {}
        current_candidate: SelectedPromotionCandidate | None = None
        try:
            for candidate in self._selected_group_worker_candidates(group_id, candidate_payloads):
                current_candidate = candidate
                group = self._read_collection(PROMOTION_GROUP_COLLECTION).get(group_id)
                if isinstance(group, Mapping) and str(group.get("status") or "") == "cancelled":
                    return
                per_task_status = dict(group.get("per_task_status") or {}) if isinstance(group, Mapping) else dict(per_task_status)
                per_task_status[candidate.candidate_id] = "production_lane_running"
                self._update_parallel_promotion_group(
                    group_id,
                    status="promotion_running",
                    current_step=f"promoting:{candidate.candidate_id}",
                    per_task_status=per_task_status,
                )
                try:
                    result = self._execute_selected_managed_run_production(candidate, group_id=group_id)
                except Exception as exc:
                    blocker = _safe_text(exc)
                    conflict_files = _selected_promotion_conflict_files(blocker)
                    if conflict_files:
                        per_task_status[candidate.candidate_id] = "ready_for_separate_deploy"
                        existing_group = self._read_collection(PROMOTION_GROUP_COLLECTION).get(group_id)
                        existing_refresh_ids = list(existing_group.get("refresh_required_ids") or []) if isinstance(existing_group, Mapping) else []
                        existing_conflicted_ids = list(existing_group.get("conflicted_ids") or []) if isinstance(existing_group, Mapping) else []
                        existing_deferred_ids = list(existing_group.get("deferred_task_ids") or []) if isinstance(existing_group, Mapping) else []
                        existing_conflict_files = list(existing_group.get("conflict_files") or []) if isinstance(existing_group, Mapping) else []
                        merged_conflict_files = _unique_strings([*existing_conflict_files, *conflict_files])
                        if candidate.candidate_id not in existing_conflicted_ids:
                            existing_conflicted_ids.append(candidate.candidate_id)
                        if candidate.candidate_id not in existing_deferred_ids:
                            existing_deferred_ids.append(candidate.candidate_id)
                        conflict_reason_by_task = dict(existing_group.get("conflict_reason_by_task") or {}) if isinstance(existing_group, Mapping) else {}
                        conflict_reason_by_task[candidate.candidate_id] = _conflict_operator_reason(conflict_files, blocker)
                        self._update_parallel_promotion_group(
                            group_id,
                            status="promotion_running",
                            current_step=f"deferred:{candidate.candidate_id}",
                            per_task_status=per_task_status,
                            blocker=None,
                            production_run_ids=production_run_ids,
                            pr_urls=pr_urls,
                            merge_commits=merge_commits,
                            conflicted_ids=existing_conflicted_ids,
                            conflict_files=merged_conflict_files,
                            deferred_task_ids=existing_deferred_ids,
                            conflict_reason_by_task=conflict_reason_by_task,
                            refresh_required_ids=existing_refresh_ids,
                            recommended_action="Запустите отдельный Merge & Deploy для deferred-задач.",
                        )
                        continue
                    raise
                production_run_id = str(result.get("run_id") or "")
                if production_run_id:
                    production_run_ids.append(production_run_id)
                if result.get("target_pr_url"):
                    pr_urls.append(str(result.get("target_pr_url")))
                if result.get("merge_commit"):
                    merge_commits.append(str(result.get("merge_commit")))
                if result.get("status") != "post_deploy_passed":
                    blocker = _joined_blockers(result) or "selected production bridge blocked"
                    conflict_files = _selected_promotion_conflict_files(blocker)
                    child_status = "ready_for_separate_deploy" if conflict_files else "blocked"
                    per_task_status[candidate.candidate_id] = child_status
                    existing_group = self._read_collection(PROMOTION_GROUP_COLLECTION).get(group_id)
                    existing_refresh_ids = list(existing_group.get("refresh_required_ids") or []) if isinstance(existing_group, Mapping) else []
                    existing_conflicted_ids = list(existing_group.get("conflicted_ids") or []) if isinstance(existing_group, Mapping) else []
                    if conflict_files and candidate.candidate_id not in existing_conflicted_ids:
                        existing_conflicted_ids.append(candidate.candidate_id)
                    existing_deferred_ids = list(existing_group.get("deferred_task_ids") or []) if isinstance(existing_group, Mapping) else []
                    existing_conflict_files = list(existing_group.get("conflict_files") or []) if isinstance(existing_group, Mapping) else []
                    merged_conflict_files = _unique_strings([*existing_conflict_files, *conflict_files])
                    if conflict_files and candidate.candidate_id not in existing_deferred_ids:
                        existing_deferred_ids.append(candidate.candidate_id)
                    conflict_reason_by_task = dict(existing_group.get("conflict_reason_by_task") or {}) if isinstance(existing_group, Mapping) else {}
                    if conflict_files:
                        conflict_reason_by_task[candidate.candidate_id] = _conflict_operator_reason(conflict_files, blocker)
                    if conflict_files:
                        self._update_parallel_promotion_group(
                            group_id,
                            status="promotion_running",
                            current_step=f"deferred:{candidate.candidate_id}",
                            per_task_status=per_task_status,
                            blocker=None,
                            production_run_id=production_run_id or None,
                            production_run_ids=production_run_ids,
                            pr_urls=pr_urls,
                            merge_commits=merge_commits,
                            deploy_status=result.get("deploy_status"),
                            public_verify_status=result.get("public_verify_status"),
                            conflicted_ids=existing_conflicted_ids,
                            conflict_files=merged_conflict_files,
                            deferred_task_ids=existing_deferred_ids,
                            conflict_reason_by_task=conflict_reason_by_task,
                            refresh_required_ids=existing_refresh_ids,
                            recommended_action="Запустите отдельный Merge & Deploy для deferred-задач.",
                        )
                        continue
                    self._update_parallel_promotion_group(
                        group_id,
                        status="blocked",
                        current_step="blocked",
                        per_task_status=per_task_status,
                        blocker=blocker,
                        finished_at=_now_utc(),
                        production_run_id=production_run_id or None,
                        production_run_ids=production_run_ids,
                        pr_urls=pr_urls,
                        merge_commits=merge_commits,
                        deploy_status=result.get("deploy_status"),
                        public_verify_status=result.get("public_verify_status"),
                        conflicted_ids=existing_conflicted_ids,
                        conflict_files=merged_conflict_files,
                        deferred_task_ids=existing_deferred_ids,
                        conflict_reason_by_task=conflict_reason_by_task,
                        refresh_required_ids=existing_refresh_ids,
                        recommended_action=None,
                    )
                    return
                per_task_status[candidate.candidate_id] = "production_complete"
                self._update_parallel_promotion_group(
                    group_id,
                    status="promotion_running",
                    current_step=f"completed:{candidate.candidate_id}",
                    per_task_status=per_task_status,
                    production_run_id=production_run_id or None,
                    production_run_ids=production_run_ids,
                    pr_urls=pr_urls,
                    merge_commits=merge_commits,
                    deploy_status=result.get("deploy_status"),
                    public_verify_status=result.get("public_verify_status"),
                )
            existing_group = self._read_collection(PROMOTION_GROUP_COLLECTION).get(group_id)
            deferred_ids = list(existing_group.get("deferred_task_ids") or []) if isinstance(existing_group, Mapping) else []
            if production_run_ids and deferred_ids:
                final_status = "partially_deployed"
            elif production_run_ids:
                final_status = "production_complete"
            elif deferred_ids:
                final_status = "ready_for_separate_deploy"
            else:
                final_status = "production_complete"
            self._update_parallel_promotion_group(
                group_id,
                status=final_status,
                current_step=final_status,
                per_task_status=per_task_status,
                finished_at=_now_utc(),
                blocker=None,
                production_run_id=production_run_ids[-1] if production_run_ids else None,
                production_run_ids=production_run_ids,
                pr_urls=pr_urls,
                merge_commits=merge_commits,
                deploy_status="passed" if production_run_ids else None,
                public_verify_status="passed" if production_run_ids else None,
                recommended_action="Запустите отдельный Merge & Deploy для deferred-задач." if deferred_ids else None,
            )
        except Exception as exc:
            blocker = _safe_text(exc)
            conflict_files = _selected_promotion_conflict_files(blocker)
            existing_group = self._read_collection(PROMOTION_GROUP_COLLECTION).get(group_id)
            if isinstance(existing_group, Mapping):
                per_task_status = dict(existing_group.get("per_task_status") or per_task_status)
            refresh_required_ids = list(existing_group.get("refresh_required_ids") or []) if isinstance(existing_group, Mapping) else []
            conflicted_ids = list(existing_group.get("conflicted_ids") or []) if isinstance(existing_group, Mapping) else []
            existing_conflict_files = list(existing_group.get("conflict_files") or []) if isinstance(existing_group, Mapping) else []
            merged_conflict_files = _unique_strings([*existing_conflict_files, *conflict_files])
            if current_candidate and conflict_files:
                per_task_status[current_candidate.candidate_id] = "ready_for_separate_deploy"
                if current_candidate.candidate_id not in conflicted_ids:
                    conflicted_ids.append(current_candidate.candidate_id)
            deferred_ids = list(existing_group.get("deferred_task_ids") or []) if isinstance(existing_group, Mapping) else []
            if current_candidate and conflict_files and current_candidate.candidate_id not in deferred_ids:
                deferred_ids.append(current_candidate.candidate_id)
            conflict_reason_by_task = dict(existing_group.get("conflict_reason_by_task") or {}) if isinstance(existing_group, Mapping) else {}
            if current_candidate and conflict_files:
                conflict_reason_by_task[current_candidate.candidate_id] = _conflict_operator_reason(conflict_files, blocker)
            group_status = "partially_deployed" if production_run_ids and conflict_files else ("ready_for_separate_deploy" if conflict_files else "blocked")
            self._update_parallel_promotion_group(
                group_id,
                status=group_status,
                current_step="partially_deployed" if production_run_ids and conflict_files else ("ready_for_separate_deploy" if conflict_files else "selected_production_bridge_blocked"),
                blocker=None if conflict_files else blocker,
                finished_at=_now_utc(),
                per_task_status=per_task_status,
                production_run_ids=production_run_ids,
                pr_urls=pr_urls,
                merge_commits=merge_commits,
                conflicted_ids=conflicted_ids,
                conflict_files=merged_conflict_files,
                deferred_task_ids=deferred_ids,
                conflict_reason_by_task=conflict_reason_by_task,
                refresh_required_ids=refresh_required_ids,
                recommended_action="Запустите отдельный Merge & Deploy для deferred-задач." if conflict_files else None,
            )

    def _selected_group_worker_candidates(
        self,
        group_id: str,
        candidate_payloads: Sequence[Mapping[str, Any]],
    ) -> list[SelectedPromotionCandidate]:
        candidates: list[SelectedPromotionCandidate] = []
        seen: set[str] = set()
        for raw_candidate in candidate_payloads:
            candidate = candidate_from_mapping(raw_candidate)
            if not candidate.candidate_id or candidate.candidate_id in seen:
                continue
            candidates.append(candidate)
            seen.add(candidate.candidate_id)
        group = self._read_collection(PROMOTION_GROUP_COLLECTION).get(group_id)
        if not isinstance(group, Mapping):
            return candidates
        target_id = str(group.get("target_id") or TARGET_PROJECT_ID)
        selection_type = str(group.get("selection_type") or "auto")
        for candidate_id in group.get("accepted_task_ids") or group.get("planned_order") or ():
            candidate_key = str(candidate_id or "")
            if not candidate_key or candidate_key in seen:
                continue
            candidates.append(
                self._resolve_selected_promotion_candidate(
                    target_id,
                    candidate_key,
                    selection_type=selection_type,
                )
            )
            seen.add(candidate_key)
        return candidates

    def _execute_selected_managed_run_production(
        self,
        candidate: SelectedPromotionCandidate,
        *,
        group_id: str | None = None,
    ) -> dict[str, Any]:
        source_run_id = candidate.managed_run_id or candidate.candidate_id
        if not source_run_id:
            raise BadRequestError("selected candidate is missing managed_run_id")
        source_run_dir = self._run_dir_for_live_id(source_run_id)
        source_record = load_run_record(source_run_dir)
        source_result = source_record.get("result") if isinstance(source_record.get("result"), Mapping) else {}
        source_verifier = source_record.get("verifier") if isinstance(source_record.get("verifier"), Mapping) else {}
        target_id = str(source_result.get("target_project_id") or candidate.target_id)
        if target_id != TARGET_PROJECT_ID:
            raise BadRequestError(f"selected production bridge supports only {TARGET_PROJECT_ID}, got {target_id}")
        verifier_status = str(source_result.get("verifier_status") or source_verifier.get("status") or "").lower()
        if verifier_status != "passed":
            raise BadRequestError(f"selected managed run verifier is not passed: {verifier_status or 'missing'}")
        if source_result.get("blocker_reason"):
            raise BadRequestError(f"selected managed run has blocker: {source_result.get('blocker_reason')}")
        changed_files = [str(item) for item in (source_result.get("changed_files") or candidate.changed_files or []) if str(item).strip()]
        if not changed_files:
            raise BadRequestError("selected managed run has no changed_files")
        source_diff = Path(str(source_result.get("diff_path") or source_run_dir / "artifacts" / "diff.patch")).resolve()
        if not _is_relative_to(source_diff, source_run_dir.resolve()) or not source_diff.exists():
            raise BadRequestError("selected managed run diff.patch artifact is missing or outside run dir")
        source_workspace = Path(str(source_result.get("workspace_path") or "")).resolve() if source_result.get("workspace_path") else None
        if source_workspace and (
            not _is_relative_to(source_workspace, self.state_dir.resolve() / "workspaces")
            or not source_workspace.exists()
            or not (source_workspace / ".git").exists()
        ):
            source_workspace = None
        source_handoff = Path(str(source_result.get("handoff_path") or source_run_dir / "artifacts" / "handoff.md")).resolve()
        if not _is_relative_to(source_handoff, source_run_dir.resolve()) or not source_handoff.exists():
            raise BadRequestError("selected managed run handoff artifact is missing or outside run dir")
        source_prompt = Path(str(source_result.get("prompt_path") or source_run_dir / "artifacts" / "prompt.md")).resolve()

        run_id = safe_state_component(
            f"selected-prod-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{slug_state_component(source_run_id, fallback='run')[:48]}",
            "run_id",
        )
        layout = self.layout.run_layout(run_id)
        layout.ensure_dirs()
        workspace = layout.workspace_dir("wb-core")
        self._clone_wb_core_for_selected_promotion(workspace)
        base_ref = _git_stdout_server(workspace, "rev-parse", "HEAD")
        apply_result = _run_git_server(workspace, "apply", "--3way", "--whitespace=nowarn", str(source_diff))
        if apply_result.returncode != 0:
            regenerated = self._regenerate_selected_source_patch(source_workspace, layout)
            if regenerated is None:
                raise BadRequestError("selected managed run diff does not apply cleanly to current target main: " + _safe_completed_output(apply_result))
            _run_git_server(workspace, "reset", "--hard", "HEAD")
            apply_result = _run_git_server(workspace, "apply", "--3way", "--whitespace=nowarn", str(regenerated))
            if apply_result.returncode != 0:
                raise BadRequestError(
                    "selected managed run regenerated diff does not apply cleanly to current target main: "
                    + _safe_completed_output(apply_result)
                )
        _run_git_server(workspace, "reset", "--mixed", "HEAD")
        diff_result = _run_git_server(workspace, "diff", "--binary", "HEAD", "--", ".")
        layout.diff_path.write_text(diff_result.stdout, encoding="utf-8")
        changed_after_apply = _git_stdout_server(workspace, "diff", "--name-only").splitlines()
        if not changed_after_apply:
            public_probe = self._run_selected_noop_public_probe(workspace)
            if source_prompt.exists() and _is_relative_to(source_prompt, source_run_dir.resolve()):
                shutil.copyfile(source_prompt, layout.prompt_path)
            else:
                layout.prompt_path.write_text(f"Selected promotion prompt for {source_run_id}\n", encoding="utf-8")
            shutil.copyfile(source_handoff, layout.handoff_path)
            prior = self._find_previous_selected_production_result(source_run_id, exclude_run_id=run_id)
            run_record = {
                "schema_version": 2,
                "request": {
                    "id": run_id,
                    "target_project_id": TARGET_PROJECT_ID,
                    "executor_mode": "selected_run_artifact_bridge",
                    "source_run_id": source_run_id,
                    "group_id": group_id,
                },
                "target_project": {"project_id": TARGET_PROJECT_ID},
                "workspace": {
                    "workspace_path": str(workspace),
                    "base_ref": base_ref,
                    "created_at": _now_utc(),
                    "source_run_id": source_run_id,
                },
                "task_spec": dict(source_record.get("task_spec") or {}),
                "result": {
                    "id": run_id,
                    "status": "production_complete",
                    "target_project_id": TARGET_PROJECT_ID,
                    "run_dir": str(layout.run_dir),
                    "workspace_path": str(workspace),
                    "prompt_path": str(layout.prompt_path),
                    "handoff_path": str(layout.handoff_path),
                    "log_path": str(layout.codex_log_path),
                    "diff_path": str(layout.diff_path),
                    "changed_files": [],
                    "verifier_status": "passed",
                    "blocker_reason": None,
                    "source_run_id": source_run_id,
                    "already_applied": True,
                    "previous_target_pr_url": prior.get("target_pr_url"),
                    "previous_merge_commit": prior.get("merge_commit"),
                },
                "updated_at": _now_utc(),
            }
            layout.metadata_path.write_text(json.dumps(_json_ready(run_record), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            append_live_event(
                layout.run_dir,
                stage="selected_artifact_already_applied",
                title="Selected managed-run diff is already present on current target main.",
                status="passed",
                level="success",
                detail=f"source_run_id={source_run_id}; public_probe=passed",
                source="selected_promotion",
                run_id=run_id,
            )
            append_terminal_output(layout.run_dir, f"Selected promotion bridge found {source_run_id} already applied on current main; public probe passed.\n")
            return {
                "status": "post_deploy_passed",
                "run_id": prior.get("run_id") or run_id,
                "target_pr_url": prior.get("target_pr_url"),
                "target_pr_number": prior.get("target_pr_number"),
                "merge_commit": prior.get("merge_commit") or base_ref,
                "deploy_status": "passed",
                "public_verify_status": "passed",
                "already_applied": True,
                "source_run_id": source_run_id,
                "public_probe": public_probe,
                "blockers": [],
            }
        if source_prompt.exists() and _is_relative_to(source_prompt, source_run_dir.resolve()):
            shutil.copyfile(source_prompt, layout.prompt_path)
        else:
            layout.prompt_path.write_text(f"Selected promotion prompt for {source_run_id}\n", encoding="utf-8")
        shutil.copyfile(source_handoff, layout.handoff_path)
        task_spec = dict(source_record.get("task_spec") or {})
        if not task_spec:
            raise BadRequestError("selected managed run task_spec is missing")
        run_record = {
            "schema_version": 2,
            "request": {
                "id": run_id,
                "target_project_id": TARGET_PROJECT_ID,
                "task_spec_id": task_spec.get("id"),
                "step_id": "selected-promotion",
                "state_dir": str(self.state_dir),
                "base_ref": base_ref,
                "workspace_strategy": "managed_clone",
                "executor_mode": "selected_run_artifact_bridge",
                "allow_real_codex": False,
                "original_repo_path": TARGET_REPO_URL,
                "original_head": base_ref,
                "original_status_before": "",
                "target_source_mode": "remote_managed_clone",
                "target_repo_url": TARGET_REPO_URL,
                "target_branch": "main",
                "source_run_id": source_run_id,
                "group_id": group_id,
            },
            "target_project": {"project_id": TARGET_PROJECT_ID},
            "workspace": {
                "original_repo_path": TARGET_REPO_URL,
                "original_head": base_ref,
                "original_status_before": "",
                "workspace_path": str(workspace),
                "base_ref": base_ref,
                "created_at": _now_utc(),
                "source_run_id": source_run_id,
            },
            "task_spec": task_spec,
            "sprint_step": source_record.get("sprint_step") or {},
            "result": {
                "id": run_id,
                "status": "verifier_passed",
                "target_project_id": TARGET_PROJECT_ID,
                "task_spec_id": task_spec.get("id"),
                "step_id": "selected-promotion",
                "run_dir": str(layout.run_dir),
                "workspace_path": str(workspace),
                "prompt_path": str(layout.prompt_path),
                "handoff_path": str(layout.handoff_path),
                "log_path": str(layout.codex_log_path),
                "diff_path": str(layout.diff_path),
                "changed_files": changed_after_apply,
                "check_results": [],
                "verifier_status": "passed",
                "blocker_reason": None,
                "next_manual_step": None,
                "codex_exit_code": None,
                "source_run_id": source_run_id,
            },
            "updated_at": _now_utc(),
        }
        layout.metadata_path.write_text(json.dumps(_json_ready(run_record), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        append_live_event(
            layout.run_dir,
            stage="selected_artifact_apply",
            title="Selected managed-run diff applied to fresh target main.",
            status="passed",
            level="info",
            detail=f"source_run_id={source_run_id}; changed_files={', '.join(changed_after_apply)}",
            source="selected_promotion",
            run_id=run_id,
        )
        append_terminal_output(layout.run_dir, f"Selected promotion bridge prepared {run_id} from {source_run_id}\n")
        verifier = verify_target_run(layout.run_dir)
        verifier_payload = verifier_result_to_dict(verifier)
        if verifier.status != "passed":
            raise BadRequestError("selected promotion verifier failed: " + str(verifier.blocker_reason or verifier.status))
        production_payload = {
            "target_project_id": TARGET_PROJECT_ID,
            "target_repo": TARGET_REPO,
            "target_repo_url": TARGET_REPO_URL,
            "base_branch": "main",
            "execution_mode": "production_lane",
            "apply_mode": "target_pr_merge_deploy",
            "production_lane": True,
            "run_id": run_id,
            "run_dir": str(layout.run_dir),
            "workspace_path": str(workspace),
            "task_spec_id": task_spec.get("id"),
            "task_summary": f"Selected Merge & Deploy from managed run {source_run_id}",
            "changed_files": list(verifier.changed_files),
            "verifier_status": verifier.status,
            "forbidden_path_hits": list(verifier.forbidden_path_hits),
            "secrets_scan_status": "passed",
            "docs_update_status": "not_required",
            "commit_message": f"Применить выбранный run DevControl ({source_run_id})",
            "pr_title": f"Применить выбранный run DevControl ({source_run_id})",
            "run_start_base_ref": base_ref,
        }
        production = execute_wb_core_production_lane(production_payload, execute=True)
        payload = target_production_result_to_dict(production)
        payload["run_id"] = run_id
        payload["source_run_id"] = source_run_id
        payload["verifier"] = verifier_payload
        return payload

    def _run_selected_noop_public_probe(self, workspace: Path) -> dict[str, Any]:
        runner = workspace / DEFAULT_DEPLOY_RUNNER
        target_file = workspace / DEFAULT_DEPLOY_TARGET_FILE
        if not runner.exists():
            raise BadRequestError("selected managed run is already applied, but public probe runner is missing")
        if not target_file.exists():
            raise BadRequestError("selected managed run is already applied, but public probe target file is missing")
        env = runtime_command_env(os.environ)
        env["WB_CORE_HOSTED_RUNTIME_TARGET_FILE"] = str(target_file)
        completed = subprocess.run(
            ("python3", str(runner), "public-probe", "--as-of-date", "AUTO_YESTERDAY"),
            cwd=workspace,
            capture_output=True,
            text=True,
            check=False,
            timeout=240,
            env=env,
        )
        if completed.returncode != 0:
            raise BadRequestError("selected managed run is already applied, but public probe failed: " + _safe_completed_output(completed))
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise BadRequestError("selected managed run is already applied, but public probe returned invalid JSON") from exc
        if not isinstance(payload, Mapping) or payload.get("ok") is not True:
            failed_routes = []
            if isinstance(payload, Mapping):
                for route in payload.get("routes") or []:
                    if isinstance(route, Mapping) and route.get("ok") is not True:
                        failed_routes.append(
                            f"{route.get('route') or 'unknown'}: {route.get('detail') or route.get('network_error') or route.get('http_status')}"
                        )
            detail = "; ".join(failed_routes[:3]) if failed_routes else "probe ok=false"
            raise BadRequestError("selected managed run is already applied, but public probe is not green: " + _safe_text(detail))
        return {
            "ok": True,
            "base_url": payload.get("base_url"),
            "route_count": len(payload.get("routes") or []),
        }

    def _find_previous_selected_production_result(self, source_run_id: str, *, exclude_run_id: str) -> dict[str, Any]:
        slug = slug_state_component(source_run_id, fallback="run")[:48]
        candidates: list[tuple[str, dict[str, Any]]] = []
        runs_dir = self.state_dir / "runs"
        if not runs_dir.exists():
            return {}
        for run_dir in sorted(runs_dir.glob("selected-prod-*")):
            if run_dir.name == exclude_run_id:
                continue
            if slug and slug not in run_dir.name:
                continue
            result_path = run_dir / "artifacts" / "production_lane" / "production_lane_result.json"
            if not result_path.exists():
                continue
            try:
                result = json.loads(result_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(result, Mapping):
                continue
            if not result.get("target_pr_url") and not result.get("merge_commit"):
                continue
            payload = dict(result)
            payload["run_id"] = payload.get("run_id") or run_dir.name
            candidates.append((run_dir.name, payload))
        if not candidates:
            return {}
        return candidates[-1][1]

    def _clone_wb_core_for_selected_promotion(self, workspace: Path) -> None:
        if workspace.exists():
            raise BadRequestError(f"selected production workspace already exists: {workspace}")
        workspace.parent.mkdir(parents=True, exist_ok=True)
        clone = subprocess.run(
            ("git", "clone", "--branch", "main", "--single-branch", "--no-tags", TARGET_REPO_URL, str(workspace)),
            cwd=self.state_dir,
            capture_output=True,
            text=True,
            check=False,
            env=runtime_command_env(os.environ),
        )
        if clone.returncode != 0:
            raise BadRequestError("failed to clone fresh target main for selected promotion: " + _safe_completed_output(clone))

    def _regenerate_selected_source_patch(self, source_workspace: Path | None, layout: Any) -> Path | None:
        if source_workspace is None:
            return None
        patch_path = layout.artifacts_dir / "source_regenerated.diff"
        _run_git_server(source_workspace, "add", "-N", ".")
        diff = _run_git_server(source_workspace, "diff", "--binary", "HEAD", "--", ".")
        if diff.returncode != 0 or not diff.stdout.strip():
            return None
        patch_path.write_text(diff.stdout, encoding="utf-8")
        return patch_path

    def _resolve_selected_promotion_candidate(
        self,
        target_id: str,
        selected_id: str,
        *,
        selection_type: str,
    ) -> SelectedPromotionCandidate:
        selected_id = safe_state_component(selected_id, "selected_id")
        if selection_type in {"auto", "task_id", "candidate_id"}:
            try:
                task = self._parallel_ledger().get_task(selected_id)
                summary = task_record_summary(task)
                decorate_operator_lifecycle(summary)
                return SelectedPromotionCandidate(
                    candidate_id=task.task_id,
                    selected_id=selected_id,
                    selection_type="task_id",
                    target_id=task.target_id,
                    source_kind="parallel_task",
                    status=task.status,
                    lifecycle_status=str(summary.get("operator_lifecycle_status") or ""),
                    managed_run_id=task.managed_run_id,
                    task_id=task.task_id,
                    changed_files=tuple(task.changed_files),
                    finished_at=task.verifier_passed_at or task.updated_at,
                    blocker=task.blocker,
                    risk=str(task.verifier_summary.get("risk") or "unknown"),
                )
            except ParallelLedgerError:
                if selection_type in {"task_id", "candidate_id"}:
                    return self._blocked_candidate(target_id, selected_id, selection_type, "parallel task/candidate not found")
        return self._resolve_run_candidate(target_id, selected_id, selection_type=selection_type)

    def _resolve_run_candidate(self, target_id: str, run_id: str, *, selection_type: str) -> SelectedPromotionCandidate:
        try:
            summary = self.get_run_summary(run_id)
        except Exception:
            try:
                job = self.get_real_run_job(run_id)
                summary = {
                    "run_id": run_id,
                    "target_id": job.get("target_project_id"),
                    "status": job.get("status"),
                    "verifier_status": job.get("verifier_status"),
                    "changed_files": job.get("changed_files", []),
                    "finished_at": job.get("updated_at"),
                    "blocker": job.get("blocker_reason"),
                }
            except Exception:
                return self._blocked_candidate(target_id, run_id, selection_type, "managed run report/artifacts not found")
        candidate_payload = {
            "run_id": run_id,
            "target_id": summary.get("target_id") or summary.get("target_project_id") or target_id,
            "status": summary.get("status"),
            "verifier_status": summary.get("verifier_status"),
            "execution_mode": summary.get("execution_mode") or "managed_clone",
            "changed_files": summary.get("changed_files", []),
            "finished_at": summary.get("finished_at") or summary.get("updated_at"),
            "blocker": summary.get("blocker_reason") or summary.get("blocker"),
        }
        decorate_operator_lifecycle(candidate_payload)
        blocker = candidate_payload.get("blocker")
        if candidate_payload.get("target_id") != target_id:
            blocker = f"target mismatch: {candidate_payload.get('target_id')}"
        return SelectedPromotionCandidate(
            candidate_id=run_id,
            selected_id=run_id,
            selection_type="run_id",
            target_id=str(candidate_payload.get("target_id") or target_id),
            source_kind="managed_run",
            status=str(candidate_payload.get("status") or ""),
            lifecycle_status=str(candidate_payload.get("operator_lifecycle_status") or ""),
            managed_run_id=run_id,
            task_id=None,
            changed_files=tuple(str(item) for item in candidate_payload.get("changed_files") or ()),
            finished_at=str(candidate_payload.get("finished_at") or "") or None,
            blocker=str(blocker or "") or None,
        )

    def _blocked_candidate(
        self,
        target_id: str,
        selected_id: str,
        selection_type: str,
        blocker: str,
    ) -> SelectedPromotionCandidate:
        return SelectedPromotionCandidate(
            candidate_id=selected_id,
            selected_id=selected_id,
            selection_type=selection_type,
            target_id=target_id,
            source_kind="unresolved",
            status="blocked",
            lifecycle_status="blocked",
            blocker=blocker,
        )

    def save_runtime_config(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        try:
            config = save_runtime_config(payload, env=self._runtime_config_env())
        except RuntimeConfigError as exc:
            raise BadRequestError(str(exc)) from exc
        return runtime_config_public_dict(config)

    def _runtime_config_env(self) -> dict[str, str]:
        env = dict(os.environ)
        env.setdefault("DEV_CONTROL_PLANE_STATE_DIR", str(self.state_dir))
        return env

    def _parallel_ledger(self) -> ParallelTaskLedger:
        return ParallelTaskLedger.from_state_dir(self.state_dir)

    def _parallel_coordinator(self) -> ParallelExecutionCoordinator:
        return ParallelExecutionCoordinator(self._parallel_ledger())

    def github_closure_decision(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        requested_auto_merge = _bool_from_payload(payload.get("auto_merge"))
        raw_eligibility = payload.get("eligibility")
        decision_payload = raw_eligibility if isinstance(raw_eligibility, Mapping) else payload
        try:
            decision = evaluate_dev_control_plane_closure_decision(
                decision_payload,
                requested_auto_merge=requested_auto_merge,
            )
        except ValueError as exc:
            raise BadRequestError(str(exc)) from exc
        result = github_closure_decision_to_dict(decision)
        result["requested_auto_merge"] = requested_auto_merge
        return result

    def target_pr_plan(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return target_workflow_decision_to_dict(build_target_pr_plan(payload))

    def preview_plan(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return target_workflow_decision_to_dict(build_preview_plan(payload))

    def target_approval_decision(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return target_workflow_decision_to_dict(evaluate_target_approval(payload))

    def target_production_plan(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return target_production_decision_to_dict(build_wb_core_production_plan(payload))

    def target_production_resume_deploy(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        run_id = _required_payload_str(payload, "run_id")
        execute = _bool_from_payload(payload.get("execute"))
        if execute and not _bool_from_payload(payload.get("confirm_resume_deploy")):
            return {
                "status": "denied",
                "allowed": False,
                "blockers": ["confirm_resume_deploy=true is required when execute=true"],
                "run_id": run_id,
            }
        result = execute_wb_core_resume_deploy(run_id=run_id, state_dir=self.state_dir, execute=execute)
        return target_production_resume_result_to_dict(result)

    def create_discussion(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        discussions = self._read_collection("discussions")
        discussion_id = _new_id("discussion", discussions)
        discussion = {
            "id": discussion_id,
            "status": "open",
            "title": str(payload.get("title") or "Local curator discussion"),
            "created_at": _now_utc(),
            "messages": [],
        }
        discussions[discussion_id] = discussion
        self._write_collection("discussions", discussions)
        return discussion

    def add_message(self, discussion_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        discussions = self._read_collection("discussions")
        discussion = discussions.get(discussion_id)
        if discussion is None:
            raise NotFoundError(f"discussion not found: {discussion_id}")
        role = str(payload.get("role") or "operator")
        content = str(payload.get("content") or "").strip()
        if role not in {"operator", "curator"}:
            raise BadRequestError("message role must be operator or curator")
        if not content:
            raise BadRequestError("message content is required")

        messages = list(discussion.get("messages") or [])
        messages.append(
            {
                "id": f"msg-{len(messages) + 1:03d}",
                "role": role,
                "content": content,
                "created_at": _now_utc(),
            }
        )
        if role == "operator":
            messages.append(
                {
                    "id": f"msg-{len(messages) + 1:03d}",
                    "role": "curator",
                    "content": _curator_chat_reply(messages),
                    "created_at": _now_utc(),
                }
            )
        discussion["messages"] = messages
        discussion["updated_at"] = _now_utc()
        discussions[discussion_id] = discussion
        self._write_collection("discussions", discussions)
        return discussion

    def draft_task_spec_from_discussion(self, discussion_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        total_started = time.perf_counter()
        timings: dict[str, float] = {
            "target_validation_duration_ms": 0.0,
            "context_build_duration_ms": 0.0,
            "curator_duration_ms": 0.0,
            "card_validation_duration_ms": 0.0,
        }
        discussion = self._get_discussion(discussion_id)
        target_project_id = _optional_str(payload.get("target_project_id"))
        target_defaults = None
        repo_context_summary = _optional_str(payload.get("repo_context_summary"))
        if target_project_id:
            target = self._target_config_by_id(target_project_id)
            step_started = time.perf_counter()
            validation = validate_target_project(target)
            timings["target_validation_duration_ms"] = _elapsed_ms(step_started)
            if validation.status == "blocked":
                return {
                    "status": "blocked",
                    "task_spec_id": None,
                    "validation_ok": False,
                    "errors": [],
                    "warnings": list(validation.warnings),
                    "provider": self._curator_mode_from_payload(payload),
                    "model": None,
                    "blocked_reason": "; ".join(validation.blockers),
                    "performance": _draft_performance_summary(
                        total_started,
                        timings,
                        provider=self._curator_mode_from_payload(payload),
                        discussion=discussion,
                        repo_context_summary=repo_context_summary,
                    ),
                }
            target_defaults = target_project_defaults(target)
            if not repo_context_summary:
                step_started = time.perf_counter()
                repo_context_summary = _target_context_for_intake(target, validation)
                timings["context_build_duration_ms"] = _elapsed_ms(step_started)
        mode = self._curator_mode_from_payload(payload)
        if mode == "fake" and not _fake_curator_enabled():
            return _openai_curator_blocked_response("Fake curator is disabled outside DEV_CONTROL_PLANE_ENABLE_FAKE_CURATOR=1")
        step_started = time.perf_counter()
        result = draft_task_spec(
            CuratorDraftRequest(
                discussion_id=discussion_id,
                messages=tuple(_safe_messages(discussion.get("messages", []))),
                existing_task_spec=_optional_mapping(payload.get("existing_task_spec")),
                repo_context_summary=repo_context_summary,
                target_project_id=target_project_id,
                target_defaults=target_defaults,
                mode=mode,
            )
        )
        timings["curator_duration_ms"] = _elapsed_ms(step_started)
        result_payload = curator_draft_result_to_dict(result)
        if result.status != "success" or not result.task_spec:
            return {
                "status": result.status,
                "task_spec_id": None,
                "validation_ok": False,
                "errors": result_payload["errors"],
                "warnings": result_payload["warnings"],
                "provider": result.provider,
                "model": result.model,
                "blocked_reason": result.blocked_reason,
                "error_type": result.error_type,
                "http_status": result.http_status,
                "request_id": result.request_id,
                "short_message": result.short_message,
                "suggested_next_step": result.suggested_next_step,
                "performance": _draft_performance_summary(
                    total_started,
                    timings,
                    provider=result.provider,
                    discussion=discussion,
                    repo_context_summary=repo_context_summary,
                    model=result.model,
                ),
            }

        try:
            step_started = time.perf_counter()
            saved = self.create_task_spec(result.task_spec)
            timings["card_validation_duration_ms"] = _elapsed_ms(step_started)
        except ControlPlaneValidationError as exc:
            return {
                "status": "failed",
                "task_spec_id": None,
                "validation_ok": False,
                "errors": [str(exc)],
                "warnings": result_payload["warnings"],
                "provider": result.provider,
                "model": result.model,
                "blocked_reason": f"invalid task card: {exc}",
                "error_type": "invalid_response",
                "http_status": None,
                "request_id": None,
                "short_message": str(exc),
                "suggested_next_step": "Проверьте карточку, target warnings и повторите формирование.",
                "performance": _draft_performance_summary(
                    total_started,
                    timings,
                    provider=result.provider,
                    discussion=discussion,
                    repo_context_summary=repo_context_summary,
                    model=result.model,
                ),
            }
        target_summary = self._target_summary_for_payload(saved)
        return {
            "status": "drafted",
            "task_spec_id": saved["id"],
            "task_spec": saved,
            "task_card": _task_card_summary(saved),
            "target_summary": target_summary,
            "next_recommended_action": _next_action_for_spec(saved),
            "validation_ok": True,
            "errors": [],
            "warnings": result_payload["warnings"],
            "provider": result.provider,
            "model": result.model,
            "blocked_reason": None,
            "performance": _draft_performance_summary(
                total_started,
                timings,
                provider=result.provider,
                discussion=discussion,
                repo_context_summary=repo_context_summary,
                model=result.model,
            ),
        }

    def start_draft_task_spec_job(self, discussion_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        self._get_discussion(discussion_id)
        job_id = self._create_draft_task_spec_job(discussion_id, payload)
        thread = threading.Thread(
            target=self._draft_task_spec_worker,
            args=(job_id, discussion_id, dict(payload)),
            daemon=True,
        )
        thread.start()
        return self.get_draft_task_spec_job(job_id)

    def get_draft_task_spec_job(self, job_id: str) -> dict[str, Any]:
        jobs = self._read_collection("draft_task_spec_jobs")
        job = jobs.get(job_id)
        if not isinstance(job, Mapping):
            raise NotFoundError(f"draft task card job not found: {job_id}")
        return _json_ready(dict(job))

    def _create_draft_task_spec_job(self, discussion_id: str, payload: Mapping[str, Any]) -> str:
        with self._jobs_lock:
            jobs = self._read_collection("draft_task_spec_jobs")
            job_id = _new_id("draft-job", jobs)
            jobs[job_id] = {
                "id": job_id,
                "status": "queued",
                "discussion_id": discussion_id,
                "target_project_id": _optional_str(payload.get("target_project_id")),
                "task_spec_id": None,
                "result": None,
                "blocked_reason": None,
                "errors": [],
                "created_at": _now_utc(),
                "updated_at": _now_utc(),
                "message": "Queued task card draft.",
            }
            self._write_collection("draft_task_spec_jobs", jobs)
        return job_id

    def _update_draft_task_spec_job(self, job_id: str, **updates: Any) -> None:
        with self._jobs_lock:
            jobs = self._read_collection("draft_task_spec_jobs")
            job = dict(jobs.get(job_id) or {})
            if not job:
                return
            job.update(_json_ready(updates))
            job["updated_at"] = _now_utc()
            jobs[job_id] = job
            self._write_collection("draft_task_spec_jobs", jobs)

    def _draft_task_spec_worker(self, job_id: str, discussion_id: str, payload: Mapping[str, Any]) -> None:
        try:
            self._update_draft_task_spec_job(
                job_id,
                status="running",
                message="Формируется карточка задачи.",
            )
            result = self.draft_task_spec_from_discussion(discussion_id, payload)
            result_status = str(result.get("status") or "failed")
            if result_status == "drafted":
                job_status = "drafted"
                message = "Карточка задачи сформирована."
            elif result_status == "blocked":
                job_status = "blocked"
                message = "Формирование карточки заблокировано."
            else:
                job_status = "failed"
                message = "Карточку задачи не удалось сформировать."
            self._update_draft_task_spec_job(
                job_id,
                status=job_status,
                task_spec_id=result.get("task_spec_id"),
                result=result,
                blocked_reason=result.get("blocked_reason"),
                errors=result.get("errors", []),
                message=message,
            )
        except Exception as exc:
            message = str(exc)
            self._update_draft_task_spec_job(
                job_id,
                status="failed",
                blocked_reason=message,
                errors=[message],
                result={
                    "status": "failed",
                    "task_spec_id": None,
                    "validation_ok": False,
                    "errors": [message],
                    "warnings": [],
                    "blocked_reason": message,
                    "short_message": message,
                    "suggested_next_step": "Проверьте target, OpenAI status и повторите формирование карточки.",
                },
                message="Карточку задачи не удалось сформировать.",
            )

    def _curator_mode_from_payload(self, payload: Mapping[str, Any]) -> str:
        raw_mode = str(payload.get("mode") or "").strip()
        if raw_mode == "fake":
            return "fake"
        return "openai"

    def create_task_spec(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        task_specs = self._read_collection("task_specs")
        target_project_id = _optional_str(payload.get("target_project_id"))
        normalized_payload = _json_ready(dict(payload))
        if target_project_id:
            normalized_payload = merge_target_defaults_into_task_spec_payload(
                normalized_payload,
                self._target_config_by_id(target_project_id),
            )
        task_spec = task_spec_from_mapping(normalized_payload)
        validate_task_spec(task_spec)
        steps = sprint_steps_from_task_spec_mapping(normalized_payload, task_spec)
        for step in steps:
            validate_sprint_step(step)
        stored = _json_ready(dict(normalized_payload))
        stored["id"] = task_spec.id
        stored["status"] = task_spec.status
        stored["forbidden_paths"] = list(task_spec.forbidden_paths)
        stored["forbidden_actions"] = list(task_spec.forbidden_actions)
        stored["required_smokes"] = list(task_spec.required_smokes)
        stored["sprint_steps"] = [sprint_step_to_dict(step) for step in steps]
        if target_project_id:
            stored["target_context_summary"] = target_context_summary_to_dict(
                build_target_context_summary(self._target_config_by_id(target_project_id))
            )
        stored["saved_at"] = _now_utc()
        task_specs[task_spec.id] = stored
        self._write_collection("task_specs", task_specs)
        return stored

    def get_task_spec(self, task_spec_id: str) -> dict[str, Any]:
        task_specs = self._read_collection("task_specs")
        task_spec = task_specs.get(task_spec_id)
        if task_spec is None:
            raise NotFoundError(f"task spec not found: {task_spec_id}")
        return task_spec

    def freeze_task_spec(self, task_spec_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        task_specs = self._read_collection("task_specs")
        existing = task_specs.get(task_spec_id)
        if existing is None:
            raise NotFoundError(f"task spec not found: {task_spec_id}")
        task_spec = task_spec_from_mapping(existing)
        if task_spec.status != "draft":
            raise BadRequestError("task spec is already frozen")
        frozen = freeze_task_spec(task_spec, frozen_at=_optional_str(payload.get("frozen_at")))
        frozen_payload = task_spec_to_dict(frozen)
        steps = sprint_steps_from_task_spec_mapping(existing, frozen)
        frozen_payload["sprint_steps"] = [sprint_step_to_dict(step) for step in steps]
        for key in ("target_project_id", "target_project", "target_context_summary"):
            if key in existing:
                frozen_payload[key] = existing[key]
        frozen_payload["saved_at"] = _now_utc()
        task_specs[task_spec_id] = frozen_payload
        self._write_collection("task_specs", task_specs)
        return frozen_payload

    def generate_prompt(self, task_spec_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        task_spec_payload = self.get_task_spec(task_spec_id)
        task_spec = task_spec_from_mapping(task_spec_payload)
        validate_task_spec(task_spec, require_frozen=True)
        steps = sprint_steps_from_task_spec_mapping(task_spec_payload, task_spec)
        step_id = str(payload.get("step_id") or steps[0].id)
        step = _select_step(steps, step_id)
        try:
            safe_state_component(task_spec.id, "task_id")
            safe_state_component(step.id, "step_id")
        except StateLayoutError as exc:
            raise BadRequestError(str(exc)) from exc
        prompt = build_codex_prompt(task_spec, step)

        prompts = self._read_collection("prompts")
        prompt_id = (
            f"prompt-{slug_state_component(task_spec.id)}-"
            f"{slug_state_component(step.id)}-{(task_spec.spec_hash or 'nohash')[:12]}"
        )
        prompt_path = self.layout.prompt_artifact_path(prompt_id)
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_path.write_text(prompt, encoding="utf-8")
        prompt_summary = {
            "id": prompt_id,
            "task_spec_id": task_spec.id,
            "task_class": task_spec.task_class,
            "step_id": step.id,
            "path": str(prompt_path),
            "created_at": _now_utc(),
            "mandatory_blocks_present": all(
                token in prompt
                for token in (
                    "Класс задачи:",
                    "Причина классификации:",
                    "Режим выполнения:",
                    "=== ДЛЯ КУРАТОРА ===",
                    "=== СЖАТАЯ ПРОВЕРКА ===",
                )
            ),
        }
        prompts[prompt_id] = prompt_summary
        self._write_collection("prompts", prompts)
        return prompt_summary

    def get_prompt_text(self, prompt_id: str) -> str:
        prompts = self._read_collection("prompts")
        prompt = prompts.get(prompt_id)
        if prompt is None:
            raise NotFoundError(f"prompt not found: {prompt_id}")
        return Path(str(prompt["path"])).read_text(encoding="utf-8")

    def prepare_run(self, task_spec_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        task_spec_payload = self.get_task_spec(task_spec_id)
        step_id = self._step_id_from_payload(task_spec_payload, payload)
        result = prepare_run(
            task_spec_payload,
            step_id=step_id,
            repo_root=ROOT,
            state_dir=self.state_dir,
            executor_mode="fake",
        )
        summary = _run_summary_from_result(result, verifier=None)
        _decorate_run_summary(summary, task_spec_payload)
        self._remember_run(summary)
        return summary

    def run_fake(self, task_spec_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        task_spec_payload = self.get_task_spec(task_spec_id)
        step_id = self._step_id_from_payload(task_spec_payload, payload)
        result = run_step(
            task_spec_payload,
            step_id=step_id,
            repo_root=ROOT,
            state_dir=self.state_dir,
            executor_mode="fake",
        )
        record = load_run_record(Path(result.run_dir))
        summary = _run_summary_from_record(record)
        _decorate_run_summary(summary, task_spec_payload)
        self._remember_run(summary)
        return summary

    def get_run(self, run_id: str) -> dict[str, Any]:
        run_dir = self._run_dir_for_id(run_id)
        record = load_run_record(run_dir)
        summary = _run_summary_from_record(record)
        _decorate_run_summary(summary, record.get("task_spec", {}))
        result = record.get("result", {})
        summary["metadata"] = record
        summary["prompt_text"] = _read_run_artifact_preview(run_dir, result.get("prompt_path"))
        summary["handoff_text"] = _read_run_artifact_preview(run_dir, result.get("handoff_path"))
        summary["diff_text"] = _read_run_artifact_preview(run_dir, result.get("diff_path"))
        timeline = build_run_timeline({"run_id": summary.get("run_id")}, record)
        summary["timeline_events"] = timeline["events"]
        summary["latest_event"] = timeline["events"][-1] if timeline["events"] else None
        summary["run_result_summary"] = _compact_run_result_summary(summary)
        summary["blocker"] = _blocker_summary(summary)
        return summary

    def get_run_summary(self, run_id: str) -> dict[str, Any]:
        return self.get_run(run_id)["run_result_summary"]

    def live_runs(self) -> dict[str, Any]:
        runs: list[dict[str, Any]] = []
        seen: set[str] = set()
        self.reconcile_parallel_promotion_groups()
        promotion_attempts = self._read_collection(PROMOTION_SELECTION_ATTEMPTS_COLLECTION)
        promotion_group_child_overrides = self._promotion_group_child_overrides()
        for run in self._read_collection("mcp_runs").values():
            if isinstance(run, Mapping):
                summary = self._live_summary_from_mcp_run(run)
                self._decorate_live_summary_observability(summary)
                self._apply_selected_promotion_attempt(summary, promotion_attempts)
                self._apply_promotion_group_child_override(summary, promotion_group_child_overrides)
                if summary["run_id"] not in seen:
                    runs.append(summary)
                    seen.add(summary["run_id"])
        for job in self._read_collection("real_runs").values():
            if isinstance(job, Mapping):
                summary = self._live_summary_from_real_job(job)
                self._decorate_live_summary_observability(summary)
                self._apply_selected_promotion_attempt(summary, promotion_attempts)
                self._apply_promotion_group_child_override(summary, promotion_group_child_overrides)
                if summary["run_id"] not in seen:
                    runs.append(summary)
                    seen.add(summary["run_id"])
        for run in self._read_collection("runs").values():
            if isinstance(run, Mapping):
                summary = self._live_summary_from_run_summary(run)
                self._decorate_live_summary_observability(summary)
                self._apply_selected_promotion_attempt(summary, promotion_attempts)
                self._apply_promotion_group_child_override(summary, promotion_group_child_overrides)
                if summary["run_id"] not in seen:
                    runs.append(summary)
                    seen.add(summary["run_id"])
        for task in self._parallel_ledger().list_tasks():
            summary = self._live_summary_from_parallel_task(task_record_summary(task))
            self._apply_selected_promotion_attempt(summary, promotion_attempts)
            self._apply_promotion_group_child_override(summary, promotion_group_child_overrides)
            if summary["run_id"] not in seen:
                runs.append(summary)
                seen.add(summary["run_id"])
        for group in self.list_parallel_promotion_groups().get("groups", []):
            if isinstance(group, Mapping):
                summary = self._live_summary_from_promotion_group(group)
                if summary["run_id"] not in seen:
                    runs.append(summary)
                    seen.add(summary["run_id"])
        runs = sorted(runs, key=_live_run_sort_key)
        active = [run for run in runs if run.get("active")]
        return {
            "status": "ok",
            "live_url": live_url(_public_base_url(), None),
            "active_count": len(active),
            "terminal_statuses": sorted(TERMINAL_LIVE_STATUSES),
            "runs": runs[:40],
            "active_runs": active[:20],
            "recent_runs": runs[:20],
        }

    def live_run_detail(self, run_id: str) -> dict[str, Any]:
        run_id = safe_state_component(run_id, "run_id")
        summary = self._live_summary_by_id(run_id)
        if summary is None:
            return {"status": "not_found", "run_id": run_id}
        try:
            run_dir = self._run_dir_for_live_id(run_id)
        except NotFoundError:
            if summary.get("run_type") == "group_promotion":
                return {
                    "status": "ok",
                    "run": summary,
                    "timeline": self._promotion_group_timeline(summary),
                    "log_tail": self._promotion_group_log_tail(summary),
                    "prompt": "",
                    "handoff": "",
                    "changed_files": [],
                    "verifier": None,
                    "report": {"promotion_group": summary},
                    "sprint": None,
                    "codex_process": None,
                    "stale_assessment": {"status": "not_applicable"},
                    "run_state_reconciliation": {},
                }
            return {
                "status": "ok",
                "run": summary,
                "timeline": [],
                "log_tail": {"status": "missing", "ansi_text": "", "plain_text": "", "offset": 0, "next_offset": 0},
                "prompt": "",
                "handoff": "",
                "changed_files": summary.get("changed_files", []),
                "verifier": None,
                "report": {"parallel_task": summary if summary.get("run_type") == "parallel_task" else None},
                "sprint": None,
                "codex_process": None,
                "stale_assessment": {"status": "missing"},
                "run_state_reconciliation": {},
            }
        timeline = self.live_run_timeline(run_id)
        log_tail = self.live_run_log_tail(run_id)
        record = _read_json(run_dir / "run.json") if (run_dir / "run.json").exists() else {}
        result = record.get("result", {}) if isinstance(record, Mapping) else {}
        prompt_path = result.get("prompt_path") if isinstance(result, Mapping) else None
        handoff_path = result.get("handoff_path") if isinstance(result, Mapping) else None
        if not prompt_path and (run_dir / "artifacts" / "prompt.md").exists():
            prompt_path = str(run_dir / "artifacts" / "prompt.md")
        if not handoff_path and (run_dir / "artifacts" / "handoff.md").exists():
            handoff_path = str(run_dir / "artifacts" / "handoff.md")
        verifier = record.get("verifier") if isinstance(record, Mapping) else None
        report = self._live_report_from_run_dir(run_dir)
        process_state = read_process_state(run_dir)
        stale_assessment = codex_stale_assessment(run_dir) if process_state else {"status": "missing"}
        reconciliation = summary.get("run_state_reconciliation") or codex_run_reconciliation(
            run_dir,
            declared_status=summary.get("status"),
            current_stage=summary.get("current_stage"),
            blocker=summary.get("blocker"),
        )
        return {
            "status": "ok",
            "run": summary,
            "timeline": timeline.get("events", []),
            "log_tail": log_tail,
            "prompt": _read_run_artifact_preview(run_dir, prompt_path, limit=30000),
            "handoff": _read_run_artifact_preview(run_dir, handoff_path, limit=24000),
            "changed_files": summary.get("changed_files", []),
            "verifier": verifier if isinstance(verifier, Mapping) else None,
            "report": report,
            "sprint": report.get("sprint") if isinstance(report, Mapping) else None,
            "codex_process": process_state,
            "stale_assessment": stale_assessment,
            "run_state_reconciliation": reconciliation,
        }

    def live_run_timeline(self, run_id: str, *, after_event_id: str | None = None) -> dict[str, Any]:
        run_id = safe_state_component(run_id, "run_id")
        try:
            run_dir = self._run_dir_for_live_id(run_id)
        except NotFoundError:
            summary = self._live_summary_by_id(run_id)
            if summary and summary.get("run_type") == "group_promotion":
                events = self._promotion_group_timeline(summary)
                if after_event_id:
                    cursor = str(after_event_id)
                    index = next((idx for idx, event in enumerate(events) if str(event.get("id") or "") == cursor), -1)
                    if index >= 0:
                        events = events[index + 1 :]
                next_cursor = str(events[-1].get("id") or "") if events else str(after_event_id or "")
                return {"status": "ok", "run_id": run_id, "events": events, "next_cursor": next_cursor, "updated_at": _now_utc()}
            return {"status": "not_found", "run_id": run_id, "events": []}
        fallback: list[dict[str, Any]] = []
        try:
            record = load_run_record(run_dir)
            fallback = build_run_timeline({"run_id": run_id}, record).get("events", [])
        except Exception:
            job = self._read_collection("real_runs").get(run_id)
            if isinstance(job, Mapping):
                fallback = [dict(event) for event in job.get("timeline_events", []) if isinstance(event, Mapping)]
        events = read_live_timeline(run_dir, fallback_events=fallback)
        if after_event_id:
            cursor = str(after_event_id)
            index = next((idx for idx, event in enumerate(events) if str(event.get("id") or "") == cursor), -1)
            if index >= 0:
                events = events[index + 1 :]
        next_cursor = str(events[-1].get("id") or "") if events else str(after_event_id or "")
        return {"status": "ok", "run_id": run_id, "events": events, "next_cursor": next_cursor, "updated_at": _now_utc()}

    def live_run_log_tail(self, run_id: str, *, max_bytes: int = 64000, offset: int | None = None) -> dict[str, Any]:
        run_id = safe_state_component(run_id, "run_id")
        try:
            run_dir = self._run_dir_for_live_id(run_id)
        except NotFoundError:
            summary = self._live_summary_by_id(run_id)
            if summary and summary.get("run_type") == "group_promotion":
                return self._promotion_group_log_tail(summary, offset=offset, max_bytes=max_bytes)
            return {"status": "not_found", "run_id": run_id, "ansi_text": "", "plain_text": "", "offset": offset or 0, "next_offset": offset or 0}
        tail = read_terminal_tail(run_dir, max_bytes=max(1000, min(max_bytes, 96_000)), offset=offset)
        return {"run_id": run_id, **tail}

    def _live_summary_by_id(self, run_id: str) -> dict[str, Any] | None:
        for item in self.live_runs().get("runs", []):
            if item.get("run_id") == run_id:
                return dict(item)
        run_dir = self.layout.run_layout(run_id).run_dir
        if run_dir.exists():
            summary = self._live_summary_from_run_dir(run_id, run_dir)
            self._decorate_live_summary_observability(summary)
            return summary
        return None

    def _decorate_live_summary_observability(self, summary: dict[str, Any]) -> None:
        run_id = str(summary.get("run_id") or "")
        if not run_id:
            return
        try:
            run_dir = self._run_dir_for_live_id(run_id)
        except Exception:
            return
        reconciliation = codex_run_reconciliation(
            run_dir,
            declared_status=summary.get("status"),
            current_stage=summary.get("current_stage"),
            blocker=summary.get("blocker"),
        )
        assessment = reconciliation.get("stale_assessment") if isinstance(reconciliation.get("stale_assessment"), Mapping) else {}
        artifacts = reconciliation.get("artifact_status") if isinstance(reconciliation.get("artifact_status"), Mapping) else {}
        summary["run_state_reconciliation"] = reconciliation
        summary["effective_status"] = reconciliation.get("effective_status")
        summary["effective_activity"] = reconciliation.get("effective_activity")
        summary["effective_recency_at"] = reconciliation.get("effective_recency_at")
        summary["display_status"] = reconciliation.get("effective_status") or summary.get("status")
        summary["operator_label"] = reconciliation.get("operator_label")
        summary["is_inconsistent"] = reconciliation.get("is_inconsistent")
        summary["control_plane_observer_status"] = reconciliation.get("control_plane_observer_status")
        summary["control_plane_observer_blocker"] = reconciliation.get("control_plane_observer_blocker")
        summary["artifact_status"] = artifacts
        summary["codex_process_status"] = reconciliation.get("codex_process_status")
        summary["codex_elapsed_seconds"] = assessment.get("elapsed_seconds")
        summary["codex_idle_seconds"] = assessment.get("idle_seconds")
        summary["last_activity_at"] = reconciliation.get("last_activity_at")
        summary["stale_assessment"] = assessment
        if reconciliation.get("effective_activity") in {"running", "queued", "waiting"}:
            summary["active"] = True
        elif reconciliation.get("effective_status") in {"needs_verifier_after_control_error"}:
            summary["active"] = False
        decorate_operator_lifecycle(summary)

    def _run_dir_for_live_id(self, run_id: str) -> Path:
        mcp = self._read_collection("mcp_runs").get(run_id)
        if isinstance(mcp, Mapping) and mcp.get("run_dir"):
            path = Path(str(mcp["run_dir"])).resolve()
            if _is_relative_to(path, self.state_dir) and path.exists():
                return path
        for collection in ("real_runs", "runs"):
            item = self._read_collection(collection).get(run_id)
            if isinstance(item, Mapping) and item.get("run_dir"):
                path = Path(str(item["run_dir"])).resolve()
                if _is_relative_to(path, self.state_dir) and path.exists():
                    return path
        path = self.layout.run_layout(run_id).run_dir
        if path.exists():
            return path
        raise NotFoundError(f"run not found: {run_id}")

    def _live_summary_from_mcp_run(self, run: Mapping[str, Any]) -> dict[str, Any]:
        run_id = str(run.get("run_id") or "")
        summary = {
            "run_id": run_id,
            "task_title": _human_task_title(run.get("task_title") or run.get("task_text_excerpt") or run.get("tool") or run_id),
            "source": "mcp",
            "run_type": run.get("run_type") or _run_type_from_execution_mode(run.get("execution_mode")),
            "target_id": run.get("target_id"),
            "target": run.get("target_id"),
            "execution_mode": run.get("execution_mode"),
            "status": run.get("status"),
            "current_stage": run.get("current_stage"),
            "created_at": run.get("created_at"),
            "updated_at": run.get("updated_at"),
            "blocker": run.get("blocker"),
            "changed_files": run.get("changed_files", []),
            "verifier_status": run.get("verifier_status"),
            "pr_url": run.get("target_pr_url"),
            "merge_commit": run.get("merge_commit"),
            "deploy_status": run.get("deploy_status"),
            "probe_status": run.get("public_verify_status"),
            "lock_wait": run.get("lock_wait"),
            "live_url": run.get("live_url") or live_url(_public_base_url(), None),
            "watch_url": run.get("watch_url") or live_url(_public_base_url(), run_id),
        }
        summary["active"] = not is_terminal_status(str(summary.get("status") or ""))
        return _json_ready(summary)

    def _live_summary_from_real_job(self, job: Mapping[str, Any]) -> dict[str, Any]:
        run_id = str(job.get("run_id") or job.get("id") or "")
        status = str(job.get("status") or "")
        summary = {
            "run_id": run_id,
            "task_title": _human_task_title(job.get("task_title") or job.get("task_spec_id") or run_id),
            "source": "real_run_job",
            "run_type": "managed",
            "target_id": job.get("target_project_id"),
            "target": job.get("target_project_id"),
            "execution_mode": "managed_clone_codex",
            "status": status,
            "current_stage": status,
            "created_at": job.get("created_at"),
            "updated_at": job.get("updated_at"),
            "blocker": job.get("blocker_reason"),
            "changed_files": job.get("changed_files", []),
            "verifier_status": job.get("verifier_status"),
            "live_url": live_url(_public_base_url(), None),
            "watch_url": live_url(_public_base_url(), run_id),
        }
        summary["active"] = not is_terminal_status(status)
        return _json_ready(summary)

    def _live_summary_from_run_summary(self, run: Mapping[str, Any]) -> dict[str, Any]:
        run_id = str(run.get("run_id") or "")
        status = str(run.get("status") or run.get("verifier_status") or "")
        summary = {
            "run_id": run_id,
            "task_title": _human_task_title(run.get("task_title") or run.get("title") or run.get("goal") or run_id),
            "source": "run_summary",
            "run_type": "managed",
            "target_id": run.get("target_project_id"),
            "target": run.get("target_project_id"),
            "execution_mode": "managed_clone",
            "status": status,
            "current_stage": status,
            "created_at": run.get("created_at"),
            "updated_at": run.get("updated_at"),
            "blocker": run.get("blocker_reason"),
            "changed_files": run.get("changed_files", []),
            "verifier_status": run.get("verifier_status"),
            "live_url": live_url(_public_base_url(), None),
            "watch_url": live_url(_public_base_url(), run_id),
        }
        summary["active"] = not is_terminal_status(status)
        return _json_ready(summary)

    def _live_summary_from_parallel_task(self, task: Mapping[str, Any]) -> dict[str, Any]:
        run_id = str(task.get("task_id") or "")
        refresh_plan = next(
            (
                raw
                for raw in self._read_collection(PROMOTION_REFRESH_PLAN_COLLECTION).values()
                if isinstance(raw, Mapping) and str(raw.get("refresh_task_id") or "") == run_id
            ),
            None,
        )
        summary = {
            "run_id": run_id,
            "task_id": run_id,
            "task_title": _human_task_title(task.get("task_title") or task.get("title") or run_id),
            "source": "parallel_task_ledger",
            "run_type": "parallel_task",
            "target_id": task.get("target_id"),
            "target": task.get("target_id"),
            "execution_mode": "parallel_task",
            "status": task.get("status"),
            "current_stage": task.get("status"),
            "created_at": task.get("submitted_at") or task.get("created_at"),
            "updated_at": task.get("updated_at"),
            "started_at": task.get("submitted_at") or task.get("created_at"),
            "finished_at": task.get("verifier_passed_at") or task.get("updated_at"),
            "blocker": task.get("blocker"),
            "changed_files": task.get("changed_files", []),
            "verifier_status": (task.get("verifier_summary") or {}).get("verifier_status")
            if isinstance(task.get("verifier_summary"), Mapping)
            else None,
            "managed_run_id": task.get("managed_run_id"),
            "production_run_id": task.get("production_run_id"),
            "promotion_epoch": task.get("promotion_epoch"),
            "refresh_required": task.get("refresh_required"),
            "live_url": live_url(_public_base_url(), None),
            "watch_url": live_url(_public_base_url(), run_id),
            "active": task.get("status") in {"submitted", "managed_run_running", "auto_promoting_first", "production_lane_running"},
        }
        if isinstance(refresh_plan, Mapping) and refresh_plan.get("refresh_run_id"):
            refresh_run_id = str(refresh_plan.get("refresh_run_id") or "")
            summary["managed_run_id"] = refresh_run_id
            summary["refresh_run_id"] = refresh_run_id
            summary["refreshed_candidate_id"] = refresh_plan.get("refreshed_candidate_id") or refresh_run_id
            try:
                refresh_job = self.get_real_run_job(refresh_run_id)
            except Exception:
                refresh_job = {}
            job_status = str(refresh_job.get("status") or refresh_plan.get("status") or "")
            actual_run_id = str(refresh_job.get("run_id") or refresh_run_id)
            if job_status in {"passed", "completed", "verifier_passed"}:
                summary.update(
                    {
                        "status": "verifier_passed",
                        "current_stage": "verifier_passed",
                        "verifier_status": str(refresh_job.get("verifier_status") or "passed"),
                        "changed_files": refresh_job.get("changed_files") or summary.get("changed_files", []),
                        "finished_at": refresh_job.get("updated_at") or summary.get("finished_at"),
                        "updated_at": refresh_job.get("updated_at") or summary.get("updated_at"),
                        "active": False,
                        "promotion_selectable": True,
                        "promotion_selection_reason": "",
                        "refreshed_candidate_id": actual_run_id,
                        "watch_url": live_url(_public_base_url(), actual_run_id),
                    }
                )
            elif job_status in {"blocked", "failed", "cancelled", "stale_timeout", "stale_lost_process"}:
                summary.update(
                    {
                        "status": job_status,
                        "current_stage": job_status,
                        "blocker": refresh_job.get("blocker_reason") or summary.get("blocker"),
                        "updated_at": refresh_job.get("updated_at") or summary.get("updated_at"),
                        "active": False,
                        "watch_url": live_url(_public_base_url(), actual_run_id),
                    }
                )
            elif job_status:
                summary.update(
                    {
                        "status": "managed_run_running",
                        "current_stage": job_status,
                        "updated_at": refresh_job.get("updated_at") or summary.get("updated_at"),
                        "active": True,
                        "watch_url": live_url(_public_base_url(), actual_run_id),
                    }
                )
        decorate_operator_lifecycle(summary)
        return _json_ready(summary)

    def _live_summary_from_promotion_group(self, group: Mapping[str, Any]) -> dict[str, Any]:
        run_id = str(group.get("group_id") or group.get("run_id") or "")
        status = str(group.get("status") or "")
        summary = {
            "run_id": run_id,
            "group_id": run_id,
            "task_title": _human_task_title(f"Merge & Deploy {len(group.get('selected_ids') or [])} tasks"),
            "source": "parallel_promotion_groups",
            "run_type": "group_promotion",
            "target_id": group.get("target_id"),
            "target": group.get("target_id"),
            "execution_mode": "selected_merge_deploy_group",
            "status": status,
            "current_stage": group.get("current_step") or group.get("status"),
            "created_at": group.get("created_at"),
            "updated_at": group.get("updated_at"),
            "started_at": group.get("created_at"),
            "finished_at": group.get("finished_at") or group.get("cancelled_at") or group.get("expired_at") or group.get("updated_at"),
            "blocker": group.get("blocker"),
            "changed_files": [],
            "selected_ids": group.get("selected_ids", []),
            "planned_order": group.get("planned_order", []),
            "accepted_task_ids": group.get("accepted_task_ids", []),
            "deferred_task_ids": group.get("deferred_task_ids", []),
            "refresh_required_ids": group.get("refresh_required_ids", []),
            "blocked_ids": group.get("blocked_ids", []),
            "conflicted_ids": group.get("conflicted_ids", []),
            "conflict_files": group.get("conflict_files", []),
            "conflict_reason_by_task": group.get("conflict_reason_by_task", {}),
            "recommended_action": group.get("recommended_action"),
            "per_task_status": group.get("per_task_status", {}),
            "production_run_id": group.get("production_run_id"),
            "production_run_ids": group.get("production_run_ids", []),
            "pr_url": (group.get("pr_urls") or [None])[-1] if isinstance(group.get("pr_urls"), list) and group.get("pr_urls") else None,
            "pr_urls": group.get("pr_urls", []),
            "merge_commit": (group.get("merge_commits") or [None])[-1] if isinstance(group.get("merge_commits"), list) and group.get("merge_commits") else None,
            "merge_commits": group.get("merge_commits", []),
            "deploy_status": group.get("deploy_status"),
            "public_verify_status": group.get("public_verify_status"),
            "live_url": live_url(_public_base_url(), None),
            "watch_url": live_url(_public_base_url(), run_id),
            "active": status in {"promotion_running"},
        }
        decorate_operator_lifecycle(summary)
        return _json_ready(summary)

    def _promotion_group_timeline(self, summary: Mapping[str, Any]) -> list[dict[str, Any]]:
        run_id = str(summary.get("run_id") or summary.get("group_id") or "")
        created = str(summary.get("created_at") or summary.get("updated_at") or _now_utc())
        updated = str(summary.get("updated_at") or created)
        status = str(summary.get("status") or "unknown")
        events = [
            {
                "id": f"{run_id}-created",
                "timestamp": created,
                "stage": "created",
                "status": "created",
                "level": "info",
                "title": "Promotion group created.",
                "detail": f"selected: {', '.join(str(item) for item in summary.get('selected_ids') or [])}",
            }
        ]
        detail = str(summary.get("blocker") or f"status: {status}")
        level = "error" if status in {"blocked", "cancelled", "expired", "failed"} else "info"
        events.append(
            {
                "id": f"{run_id}-{status}",
                "timestamp": updated,
                "stage": str(summary.get("current_stage") or status),
                "status": status,
                "level": level,
                "title": f"Promotion group {status}.",
                "detail": detail,
            }
        )
        return events

    def _promotion_group_log_tail(
        self,
        summary: Mapping[str, Any],
        *,
        offset: int | None = None,
        max_bytes: int = 64000,
    ) -> dict[str, Any]:
        lines = [
            f"Promotion group: {summary.get('run_id') or summary.get('group_id')}",
            f"target_id: {summary.get('target_id') or 'n/a'}",
            f"status: {summary.get('status') or 'unknown'}",
            f"stage: {summary.get('current_stage') or 'unknown'}",
            f"selected: {', '.join(str(item) for item in summary.get('selected_ids') or []) or 'none'}",
        ]
        if summary.get("planned_order"):
            lines.append(f"planned_order: {', '.join(str(item) for item in summary.get('planned_order') or [])}")
        if summary.get("accepted_task_ids"):
            lines.append(f"accepted_task_ids: {', '.join(str(item) for item in summary.get('accepted_task_ids') or [])}")
        if summary.get("deferred_task_ids"):
            lines.append(f"deferred_task_ids: {', '.join(str(item) for item in summary.get('deferred_task_ids') or [])}")
        if summary.get("conflict_files"):
            lines.append(f"conflict_files: {', '.join(str(item) for item in summary.get('conflict_files') or [])}")
        if summary.get("recommended_action"):
            lines.append(f"recommended_action: {summary.get('recommended_action')}")
        if summary.get("blocker"):
            lines.append(f"blocker: {summary.get('blocker')}")
        text = sanitize_terminal_text("\n".join(lines) + "\n")
        start = max(0, int(offset or 0))
        raw = text.encode("utf-8")
        chunk = raw[start : start + max(1000, min(max_bytes, 96_000))].decode("utf-8", errors="replace")
        next_offset = min(len(raw), start + len(chunk.encode("utf-8")))
        return {
            "status": "ok",
            "ansi_text": chunk,
            "plain_text": chunk,
            "offset": start,
            "next_offset": next_offset,
            "bytes": len(raw),
            "truncated": next_offset < len(raw),
        }

    def _live_summary_from_run_dir(self, run_id: str, run_dir: Path) -> dict[str, Any]:
        record = _read_json(run_dir / "run.json") if (run_dir / "run.json").exists() else {}
        result = record.get("result", {}) if isinstance(record, Mapping) else {}
        status = str(result.get("status") or "unknown") if isinstance(result, Mapping) else "unknown"
        return {
            "run_id": run_id,
            "source": "run_dir",
            "run_type": "managed",
            "target_id": result.get("target_project_id") if isinstance(result, Mapping) else None,
            "target": result.get("target_project_id") if isinstance(result, Mapping) else None,
            "execution_mode": "managed_clone",
            "status": status,
            "current_stage": status,
            "created_at": record.get("created_at") if isinstance(record, Mapping) else None,
            "updated_at": record.get("updated_at") if isinstance(record, Mapping) else None,
            "blocker": result.get("blocker_reason") if isinstance(result, Mapping) else None,
            "changed_files": result.get("changed_files", []) if isinstance(result, Mapping) else [],
            "verifier_status": result.get("verifier_status") if isinstance(result, Mapping) else None,
            "active": not is_terminal_status(status),
            "live_url": live_url(_public_base_url(), None),
            "watch_url": live_url(_public_base_url(), run_id),
        }

    def _live_report_from_run_dir(self, run_dir: Path) -> dict[str, Any]:
        production = _read_json(run_dir / "artifacts" / "production_lane" / "production_lane_result.json") if (run_dir / "artifacts" / "production_lane" / "production_lane_result.json").exists() else {}
        mcp_report = _read_json(run_dir / "artifacts" / "production_lane" / "mcp_production_lane_report.json") if (run_dir / "artifacts" / "production_lane" / "mcp_production_lane_report.json").exists() else {}
        sprint_report = _read_json(run_dir / "artifacts" / "sprint" / "sprint_report.json") if (run_dir / "artifacts" / "sprint" / "sprint_report.json").exists() else {}
        return _json_ready({"production_lane": production or mcp_report or None, "sprint": sprint_report or None})

    def verify_run(self, run_id: str) -> dict[str, Any]:
        run_dir = self._run_dir_for_id(run_id)
        verifier = verify_run(run_dir)
        record = load_run_record(run_dir)
        summary = _run_summary_from_record(record)
        summary["verifier"] = verifier_result_to_dict(verifier)
        _decorate_run_summary(summary, record.get("task_spec", {}))
        self._remember_run(summary)
        return summary

    def cleanup_run(self, run_id: str) -> dict[str, Any]:
        run_dir = self._run_dir_for_id(run_id)
        record = load_run_record(run_dir)
        result = record.get("result", {})
        cleanup = cleanup_target_run(run_dir) if isinstance(result, Mapping) and result.get("workspace_path") else cleanup_run_worktree(run_dir)
        summary = _run_summary_from_record(record)
        summary["cleanup"] = cleanup
        _decorate_run_summary(summary, record.get("task_spec", {}))
        self._remember_run(summary)
        return summary

    def cancel_run(self, run_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        run_id = safe_state_component(run_id, "run_id")
        if isinstance(self._read_collection(PROMOTION_GROUP_COLLECTION).get(run_id), Mapping):
            return self.cancel_parallel_promotion_group(run_id, payload)
        reason = sanitize_terminal_text(str(payload.get("reason") or "operator requested cancel"))[:500]
        promotion_child_cancel = self._cancel_parallel_promotion_child(run_id, reason)
        if promotion_child_cancel is not None:
            return promotion_child_cancel
        run_dir = self._run_dir_for_live_id(run_id)
        result = terminate_run_owned_process_group(run_dir, reason=reason)
        status = "cancelled" if result.get("status") == "cancelled" else str(result.get("status") or "blocked")
        self._mark_live_run_terminal(run_id, run_dir, status=status, stage="cancelled", blocker=reason)
        return {"status": status, "run_id": run_id, "cancel": result, "run": self.live_run_detail(run_id).get("run")}

    def mark_run_stale(self, run_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        run_id = safe_state_component(run_id, "run_id")
        if isinstance(self._read_collection(PROMOTION_GROUP_COLLECTION).get(run_id), Mapping):
            reason = sanitize_terminal_text(str(payload.get("reason") or "operator marked promotion group stale/blocked"))[:700]
            self._update_parallel_promotion_group(
                run_id,
                status="blocked",
                current_step="blocked",
                blocker=reason,
                finished_at=_now_utc(),
            )
            return {"status": "blocked", "run_id": run_id, "group": self.get_parallel_promotion_group(run_id).get("group")}
        run_dir = self._run_dir_for_live_id(run_id)
        assessment = codex_stale_assessment(run_dir)
        requested = str(payload.get("status") or assessment.get("status") or "stale_lost_process")
        status = requested if requested in {"stale_lost_process", "stale_timeout", "blocked"} else "stale_lost_process"
        blocker = sanitize_terminal_text(str(payload.get("reason") or assessment.get("blocker") or "operator marked run stale/blocked"))[:700]
        finalize_process_state(run_dir, status=status, timeout_reason=blocker)
        self._mark_live_run_terminal(run_id, run_dir, status=status, stage=status, blocker=blocker)
        return {"status": status, "run_id": run_id, "stale_assessment": assessment, "run": self.live_run_detail(run_id).get("run")}

    def _mark_live_run_terminal(self, run_id: str, run_dir: Path, *, status: str, stage: str, blocker: str) -> None:
        for collection in ("mcp_runs", "real_runs", "runs"):
            items = self._read_collection(collection)
            item = items.get(run_id)
            if isinstance(item, Mapping):
                updated = dict(item)
                updated["status"] = status
                updated["current_stage"] = stage
                updated["blocker"] = blocker
                updated["blocker_reason"] = blocker
                updated["updated_at"] = _now_utc()
                items[run_id] = _json_ready(updated)
                self._write_collection(collection, items)
        record_path = run_dir / "run.json"
        if record_path.exists():
            record = dict(_read_json(record_path))
            result = dict(record.get("result") or {})
            if result:
                result["status"] = "blocked" if status.startswith("stale_") else status
                result["blocker_reason"] = blocker
                result["next_manual_step"] = "Inspect preserved prompt/logs/artifacts before retrying."
                record["result"] = result
                record["updated_at"] = _now_utc()
                record_path.write_text(json.dumps(_json_ready(record), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        append_live_event(run_dir, stage=stage, title=f"Run marked {status}.", status=status, level="error", detail=blocker, source="operator", run_id=run_id)
        append_terminal_output(run_dir, f"\n\x1b[31mRun marked {status}: {blocker}\x1b[0m\n")

    def guided_safe_fake_run(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        task_spec_id = str(payload.get("task_spec_id") or "")
        if not task_spec_id:
            raise BadRequestError("task_spec_id is required")
        task_spec_payload = self.get_task_spec(task_spec_id)
        task_spec = task_spec_from_mapping(task_spec_payload)
        if task_spec.status != "frozen":
            raise BadRequestError(FREEZE_TASK_FIRST_MESSAGE)
        step_id = self._step_id_from_payload(task_spec_payload, payload)
        prompt_summary = self.generate_prompt(task_spec_id, {"step_id": step_id})
        prepared = self.prepare_run(task_spec_id, {"step_id": step_id})
        fake_run = self.run_fake(task_spec_id, {"step_id": step_id})
        verified = self.verify_run(str(fake_run["run_id"]))
        summary = {
            "status": "verifier_passed" if verified.get("verifier_status") == "passed" else "failed",
            "task_spec_id": task_spec_id,
            "step_id": step_id,
            "target_project_id": task_spec_payload.get("target_project_id"),
            "prompt_id": prompt_summary["id"],
            "prepared_run_id": prepared["run_id"],
            "run_id": fake_run["run_id"],
            "prompt_path": fake_run["prompt_path"],
            "handoff_path": fake_run["handoff_path"],
            "worktree_path": fake_run["worktree_path"],
            "verifier_status": verified.get("verifier_status"),
            "blocker_reason": verified.get("blocker_reason"),
            "mandatory_handoff_blocks_present": verified.get("mandatory_handoff_blocks_present"),
            "errors": [],
        }
        summary["run_result_summary"] = _compact_run_result_summary({**verified, **summary})
        summary["blocker"] = _blocker_summary({**verified, **summary})
        return summary

    def start_managed_codex_run(self, task_spec_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        forbidden_ui_fields = ("executor_command", "codex_bin", "codex_args", "codex_extra_arg", "command")
        supplied_forbidden = [field for field in forbidden_ui_fields if field in payload]
        if supplied_forbidden:
            raise BadRequestError(f"managed Codex UI run does not accept executor command fields: {supplied_forbidden}")
        task_spec_payload = self.get_task_spec(task_spec_id)
        task_spec = task_spec_from_mapping(task_spec_payload)
        if task_spec.status != "frozen":
            raise BadRequestError(FREEZE_TASK_FIRST_MESSAGE)
        target_project_id = _optional_str(task_spec_payload.get("target_project_id")) or _optional_str(
            payload.get("target_project_id")
        )
        if not target_project_id:
            raise BadRequestError("target project is required for managed Codex run")
        target_config = self._target_config_by_id(target_project_id)
        policy = dict(target_config.execution_policy)
        if not policy.get("allow_managed_clone_execution", False):
            raise BadRequestError("target execution policy blocks managed clone execution")
        if policy.get("allow_direct_target_mutation", False):
            raise BadRequestError("target execution policy must not allow direct target mutation")
        if policy.get("allow_live_deploy", False):
            raise BadRequestError("target execution policy must not allow live deploy")
        if policy.get("allow_auto_merge", False):
            raise BadRequestError("target execution policy must not allow auto-merge")
        validation = validate_target_project(target_config)
        if validation.status == "blocked":
            raise BadRequestError(f"target project validation blocked: {'; '.join(validation.blockers)}")
        step_id = self._step_id_from_payload(task_spec_payload, payload)
        codex_bin = _codex_bin_for_execution()
        if not codex_bin:
            raise BadRequestError("Codex CLI is not installed or not on PATH")

        job_id = self._create_real_run_job(task_spec_id, target_project_id, step_id, codex_bin)
        job = self.get_real_run_job(job_id)
        thread = threading.Thread(
            target=self._managed_codex_worker,
            args=(job_id, task_spec_payload, target_config, step_id, codex_bin),
            daemon=True,
        )
        thread.start()
        return job

    def get_real_run_job(self, job_id: str) -> dict[str, Any]:
        jobs = self._read_collection("real_runs")
        job = jobs.get(job_id)
        if not isinstance(job, Mapping):
            raise NotFoundError(f"real Codex job not found: {job_id}")
        job_payload = _json_ready(dict(job))
        record = None
        run_dir = job_payload.get("run_dir")
        if run_dir:
            try:
                run_dir_path = Path(str(run_dir)).resolve()
                if _is_relative_to(run_dir_path, self.state_dir.resolve()) and run_dir_path.exists():
                    record = load_run_record(run_dir_path)
            except Exception:
                record = None
        timeline = build_run_timeline(job_payload, record)
        job_payload["timeline_events"] = timeline["events"]
        job_payload["latest_event"] = timeline["events"][-1] if timeline["events"] else None
        job_payload["timeline_updated_at"] = timeline["updated_at"]
        return job_payload

    def _create_real_run_job(self, task_spec_id: str, target_project_id: str, step_id: str, codex_bin: str) -> str:
        with self._jobs_lock:
            jobs = self._read_collection("real_runs")
            job_id = _new_id("real-run", jobs)
            jobs[job_id] = {
                "id": job_id,
                "status": "queued",
                "task_spec_id": task_spec_id,
                "target_project_id": target_project_id,
                "step_id": step_id,
                "codex_bin": codex_bin,
                "run_id": None,
                "run_dir": None,
                "workspace_path": None,
                "prompt_path": None,
                "handoff_path": None,
                "log_path": None,
                "diff_path": None,
                "verifier_status": None,
                "changed_files": [],
                "blocker_reason": None,
                "next_manual_step": None,
                "created_at": _now_utc(),
                "updated_at": _now_utc(),
                "message": "Queued managed Codex run.",
                "errors": [],
                "timeline_events": append_timeline_event(
                    (),
                    phase="queued",
                    title="Ожидаем старт выполнения...",
                    source="system",
                ),
            }
            self._write_collection("real_runs", jobs)
        return job_id

    def _update_real_run_job(self, job_id: str, **updates: Any) -> None:
        with self._jobs_lock:
            jobs = self._read_collection("real_runs")
            job = dict(jobs.get(job_id) or {})
            if not job:
                return
            job.update(_json_ready(updates))
            status = str(updates.get("status") or "")
            if status:
                event = _timeline_event_for_job_status(status, detail=_optional_str(updates.get("blocker_reason")))
                if event:
                    job["timeline_events"] = append_timeline_event(
                        job.get("timeline_events", []),
                        phase=event["phase"],
                        level=event["level"],
                        title=event["title"],
                        detail=event.get("detail"),
                        source="system",
                    )
            job["updated_at"] = _now_utc()
            jobs[job_id] = job
            self._write_collection("real_runs", jobs)

    def _managed_codex_worker(
        self,
        job_id: str,
        task_spec_payload: Mapping[str, Any],
        target_config: Any,
        step_id: str,
        codex_bin: str,
    ) -> None:
        def progress(status: str) -> None:
            self._update_real_run_job(job_id, status=status, message=_real_codex_status_message(status))

        try:
            progress("preparing")
            result = run_codex_cli(
                task_spec_payload,
                target_config=target_config,
                step_id=step_id,
                state_dir=self.state_dir,
                allow_real_codex=True,
                codex_bin=codex_bin,
                codex_args=(),
                progress_callback=progress,
            )
            record = load_run_record(Path(result.run_dir))
            summary = _target_run_summary_from_record(record)
            _decorate_run_summary(summary, record.get("task_spec", {}))
            self._remember_run(summary)
            final_status = _real_job_status_from_result(summary)
            self._update_real_run_job(
                job_id,
                **_real_job_updates_from_summary(summary),
                status=final_status,
                message=_real_codex_status_message(final_status),
            )
        except ControlPlaneValidationError as exc:
            self._update_real_run_job(
                job_id,
                status="blocked",
                blocker_reason=str(exc),
                next_manual_step="Проверьте карточку задачи, target policy и настройки Codex.",
                message="Codex запуск заблокирован policy/verifier gate.",
                errors=[str(exc)],
            )
        except ControlPlaneExecutionError as exc:
            self._update_real_run_job(
                job_id,
                status="blocked",
                blocker_reason=str(exc),
                next_manual_step="Проверьте managed clone, Codex CLI и run artifacts.",
                message="Codex запуск заблокирован execution layer.",
                errors=[str(exc)],
            )
        except Exception as exc:
            self._update_real_run_job(
                job_id,
                status="failed",
                blocker_reason=str(exc),
                next_manual_step="Проверьте Codex CLI login и technical details.",
                message="Codex запуск завершился ошибкой.",
                errors=[str(exc)],
            )

    def _read_collection(self, name: str) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        for path in (self._legacy_collection_path(name), self.layout.collection_path(name)):
            if not path.exists():
                continue
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                raise BadRequestError(f"state collection is not an object: {name}")
            payload.update(loaded)
        return payload

    def _write_collection(self, name: str, payload: Mapping[str, Any]) -> None:
        path = self.layout.collection_path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_name(f".{path.name}.tmp")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp_path.replace(path)

    def _legacy_collection_path(self, name: str) -> Path:
        component = safe_state_component(name, "collection_name")
        return (self.state_dir / f"{component}.json").resolve()

    def _remember_run(self, summary: Mapping[str, Any]) -> None:
        run_id = str(summary.get("run_id") or "")
        if not run_id:
            raise BadRequestError("run summary is missing run_id")
        runs = self._read_collection("runs")
        runs[run_id] = _json_ready(dict(summary))
        self._write_collection("runs", runs)

    def _run_dir_for_id(self, run_id: str) -> Path:
        try:
            safe_run_id = safe_state_component(run_id, "run_id")
        except StateLayoutError as exc:
            raise BadRequestError(f"invalid run id: {run_id}") from exc
        runs = self._read_collection("runs")
        run = runs.get(safe_run_id)
        if isinstance(run, Mapping) and run.get("run_dir"):
            run_dir = Path(str(run["run_dir"])).resolve()
        else:
            run_dir = self.layout.run_layout(safe_run_id).run_dir
        if not _is_relative_to(run_dir, self.state_dir.resolve()):
            raise BadRequestError(f"run dir is outside local state dir: {run_dir}")
        if not run_dir.exists():
            raise NotFoundError(f"run not found: {run_id}")
        return run_dir

    def _step_id_from_payload(self, task_spec_payload: Mapping[str, Any], payload: Mapping[str, Any]) -> str:
        task_spec = task_spec_from_mapping(task_spec_payload)
        try:
            steps = sprint_steps_from_task_spec_mapping(task_spec_payload, task_spec)
        except ControlPlaneValidationError as exc:
            raise BadRequestError(RUNNABLE_STEP_MISSING_MESSAGE) from exc
        if payload.get("step_id"):
            step_id = str(payload["step_id"])
            if any(step.id == step_id for step in steps):
                return step_id
            raise BadRequestError(RUNNABLE_STEP_MISSING_MESSAGE)
        if not steps:
            raise BadRequestError(RUNNABLE_STEP_MISSING_MESSAGE)
        return steps[0].id

    def _get_discussion(self, discussion_id: str) -> Mapping[str, Any]:
        discussions = self._read_collection("discussions")
        discussion = discussions.get(discussion_id)
        if not isinstance(discussion, Mapping):
            raise NotFoundError(f"discussion not found: {discussion_id}")
        return discussion

    def list_target_projects(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "targets": self._target_summaries(),
        }

    def get_target_project(self, project_id: str) -> dict[str, Any]:
        config = self._target_config_by_id(project_id)
        validation = validate_target_project(config)
        summary = build_target_context_summary(config)
        return {
            "status": validation.status,
            "target": target_project_config_to_dict(config),
            "validation": target_project_validation_result_to_dict(validation),
            "summary": target_context_summary_to_dict(summary),
        }

    def _target_summaries(self) -> list[dict[str, Any]]:
        summaries: list[dict[str, Any]] = []
        for config in load_target_project_configs(self.target_config_dir):
            validation = validate_target_project(config)
            target_summary = build_target_context_summary(config)
            summaries.append(
                {
                    "project_id": config.project_id,
                    "display_name": config.display_name,
                    "repo_path": config.repo_path,
                    "source_mode": validation.source_mode,
                    "repo_url": validation.repo_url,
                    "branch": validation.branch,
                    "target_readonly_by_default": config.target_readonly_by_default,
                    "validation_status": validation.status,
                    "repo_exists": validation.repo_exists,
                    "is_git_repo": validation.is_git_repo,
                    "remote_source_available": validation.remote_source_available,
                    "managed_clone_ready": validation.managed_clone_ready,
                    "current_branch": validation.current_branch,
                    "head_commit": validation.head_commit,
                    "source_of_truth_paths_found": list(target_summary.source_of_truth_paths_found),
                    "missing_source_paths": list(target_summary.missing_source_paths),
                    "derived_secondary_paths": list(target_summary.derived_secondary_paths),
                    "default_forbidden_paths": list(target_summary.default_forbidden_paths),
                    "default_forbidden_actions": list(target_summary.default_forbidden_actions),
                    "default_required_smokes": list(target_summary.default_required_smokes),
                    "workflow_notes": list(target_summary.workflow_notes),
                    "warnings": list(validation.warnings),
                    "blockers": list(validation.blockers),
                }
            )
        return summaries

    def _target_config_by_id(self, project_id: str):
        for config in load_target_project_configs(self.target_config_dir):
            if config.project_id == project_id:
                return config
        raise NotFoundError(f"target project not found: {project_id}")

    def _target_summary_for_payload(self, payload: Mapping[str, Any]) -> dict[str, Any] | None:
        target_project_id = _optional_str(payload.get("target_project_id"))
        if not target_project_id:
            return None
        return target_context_summary_to_dict(build_target_context_summary(self._target_config_by_id(target_project_id)))


class CockpitRequestHandler(BaseHTTPRequestHandler):
    server: "CockpitHTTPServer"

    def do_GET(self) -> None:  # noqa: N802
        path = _route_path(self.path)
        try:
            if path in {"/.well-known/oauth-protected-resource", "/.well-known/oauth-protected-resource/mcp"}:
                self._send_json(self.server.oauth_provider.protected_resource_metadata(self._external_base_url()))
                return
            if path in {"/.well-known/oauth-authorization-server", "/.well-known/openid-configuration"}:
                self._send_json(self.server.oauth_provider.authorization_server_metadata(self._external_base_url()))
                return
            if path == "/oauth/authorize":
                html = self.server.oauth_provider.authorize_page(parse_qs(urlparse(self.path).query, keep_blank_values=True), self._external_base_url())
                self._send_html(html)
                return
            if path == "/runs/live":
                self._send_html(_render_live_runs_html())
                return
            parts = _split_path(path)
            if len(parts) == 3 and parts[0] == "runs" and parts[2] == "watch":
                run_id = safe_state_component(parts[1], "run_id")
                self._send_html(_render_live_runs_html(selected_run_id=run_id))
                return
            if path == "/":
                self._send_html(_render_operator_html())
                return
            if path in {"/mcp", "/mcp/stream"}:
                context = build_mcp_context(
                    {str(key): str(value) for key, value in self.headers.items()},
                    client=str(self.client_address[0] if self.client_address else ""),
                    env=self.server.store._runtime_config_env(),
                    oauth_provider=self.server.oauth_provider,
                )
                self._send_json(self.server.mcp_backend.status_summary(public=not context.authenticated))
                return
            if path == "/api/state":
                self._send_json(self.server.store.summary(self.server.config))
                return
            if path == "/api/connections/status":
                self._send_json(self.server.store.connections_status())
                return
            if path == "/api/runtime-config":
                self._send_json(self.server.store.runtime_config_status())
                return
            if path == "/api/toolchain/status":
                self._send_json(build_toolchain_status(env=_safe_status_env(), codex_bin=_codex_bin_for_execution()))
                return
            if path == "/api/example-task-spec":
                self._send_json(_read_json(EXAMPLE_TASK_SPEC))
                return
            if path in {"/api/target-projects", "/api/targets"}:
                self._send_json(self.server.store.list_target_projects())
                return
            if path == "/api/parallel-tasks":
                query = parse_qs(urlparse(self.path).query, keep_blank_values=True)
                self._send_json(
                    self.server.store.list_parallel_tasks(
                        target_id=_query_value(query, "target_id"),
                        promotion_epoch=_query_value(query, "promotion_epoch"),
                        status=_query_value(query, "status"),
                    )
                )
                return
            if path == "/api/parallel-promotion-groups":
                query = parse_qs(urlparse(self.path).query, keep_blank_values=True)
                self._send_json(self.server.store.list_parallel_promotion_groups(target_id=_query_value(query, "target_id")))
                return
            if path == "/api/runs/live":
                self._send_json(self.server.store.live_runs())
                return
            if path == "/api/runs/stream":
                self._stream_live_runs()
                return
            if len(parts) == 3 and parts[:2] == ["api", "target-projects"]:
                self._send_json(self.server.store.get_target_project(parts[2]))
                return
            if len(parts) == 4 and parts[:2] == ["api", "target-projects"] and parts[3] == "summary":
                self._send_json(self.server.store.get_target_project(parts[2]))
                return
            if len(parts) == 4 and parts[:2] == ["api", "targets"] and parts[3] == "summary":
                self._send_json(self.server.store.get_target_project(parts[2]))
                return
            if len(parts) == 3 and parts[:2] == ["api", "parallel-tasks"]:
                self._send_json(self.server.store.get_parallel_task(parts[2]))
                return
            if len(parts) == 3 and parts[:2] == ["api", "parallel-promotion-groups"]:
                self._send_json(self.server.store.get_parallel_promotion_group(parts[2]))
                return
            if len(parts) == 4 and parts[:2] == ["api", "parallel-targets"] and parts[3] == "promotion-candidates":
                query = parse_qs(urlparse(self.path).query, keep_blank_values=True)
                self._send_json(
                    self.server.store.list_parallel_candidates(
                        target_id=parts[2],
                        promotion_epoch=_query_value(query, "promotion_epoch"),
                    )
                )
                return
            if len(parts) == 4 and parts[:2] == ["api", "parallel-targets"] and parts[3] == "promotion-state":
                query = parse_qs(urlparse(self.path).query, keep_blank_values=True)
                self._send_json(
                    self.server.store.get_target_promotion_state(
                        parts[2],
                        promotion_epoch=_query_value(query, "promotion_epoch"),
                    )
                )
                return
            if len(parts) == 3 and parts[:2] == ["api", "task-specs"]:
                self._send_json(self.server.store.get_task_spec(parts[2]))
                return
            if len(parts) == 3 and parts[:2] == ["api", "prompts"]:
                self._send_text(self.server.store.get_prompt_text(parts[2]))
                return
            if len(parts) == 4 and parts[:2] == ["api", "runs"] and parts[3] == "live":
                self._send_json(self.server.store.live_run_detail(parts[2]))
                return
            if len(parts) == 4 and parts[:2] == ["api", "runs"] and parts[3] == "timeline":
                query = parse_qs(urlparse(self.path).query, keep_blank_values=True)
                after_event_id = (query.get("after") or query.get("cursor") or [""])[0] or None
                self._send_json(self.server.store.live_run_timeline(parts[2], after_event_id=after_event_id))
                return
            if len(parts) == 4 and parts[:2] == ["api", "runs"] and parts[3] == "log-tail":
                query = parse_qs(urlparse(self.path).query, keep_blank_values=True)
                max_bytes = _int_or_default((query.get("max_bytes") or ["64000"])[0], 64000)
                offset_raw = (query.get("offset") or [""])[0]
                offset = _int_or_default(offset_raw, 0) if offset_raw != "" else None
                self._send_json(self.server.store.live_run_log_tail(parts[2], max_bytes=max_bytes, offset=offset))
                return
            if len(parts) == 4 and parts[:2] == ["api", "runs"] and parts[3] == "stream":
                self._stream_run(parts[2])
                return
            if len(parts) == 3 and parts[:2] == ["api", "runs"]:
                self._send_json(self.server.store.get_run(parts[2]))
                return
            if len(parts) == 4 and parts[:2] == ["api", "runs"] and parts[3] == "summary":
                self._send_json(self.server.store.get_run_summary(parts[2]))
                return
            if len(parts) == 3 and parts[:2] == ["api", "real-runs"]:
                self._send_json(self.server.store.get_real_run_job(parts[2]))
                return
            if len(parts) == 3 and parts[:2] == ["api", "draft-task-spec-jobs"]:
                self._send_json(self.server.store.get_draft_task_spec_job(parts[2]))
                return
            self._send_error(HTTPStatus.NOT_FOUND, "route not found")
        except RequestError as exc:
            self._send_error(exc.status, str(exc))
        except OAuthError as exc:
            self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
        except Exception as exc:
            self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def do_POST(self) -> None:  # noqa: N802
        path = _route_path(self.path)
        try:
            if path == "/oauth/register":
                self._send_json(self.server.oauth_provider.register_client(self._read_json_body(), self._external_base_url()), HTTPStatus.CREATED)
                return
            if path == "/oauth/token":
                self._send_json(self.server.oauth_provider.exchange_token(self._read_form_or_json_body(), self._external_base_url()))
                return
            if path == "/oauth/authorize":
                redirect_to = self.server.oauth_provider.approve_authorization(self._read_form_or_json_body(), self._external_base_url())
                self._send_redirect(redirect_to)
                return
            raw_payload = self._read_json_value()
            if path in {"/mcp", "/mcp/stream"}:
                context = build_mcp_context(
                    {str(key): str(value) for key, value in self.headers.items()},
                    client=str(self.client_address[0] if self.client_address else ""),
                    env=self.server.store._runtime_config_env(),
                    oauth_provider=self.server.oauth_provider,
                )
                status, response = self.server.mcp_backend.handle_json_rpc(raw_payload, context)
                self._send_json(response, HTTPStatus(status))
                return
            if not isinstance(raw_payload, Mapping):
                raise BadRequestError("JSON body must be an object")
            payload = raw_payload
            if path == "/api/discussions":
                self._send_json(self.server.store.create_discussion(payload), HTTPStatus.CREATED)
                return
            if path == "/api/task-specs":
                self._send_json(self.server.store.create_task_spec(payload), HTTPStatus.CREATED)
                return
            if path == "/api/guided-safe-fake-run":
                self._send_json(self.server.store.guided_safe_fake_run(payload), HTTPStatus.CREATED)
                return
            if path == "/api/github-closure/decision":
                self._send_json(self.server.store.github_closure_decision(payload))
                return
            if path == "/api/target-workflow/pr-plan":
                self._send_json(self.server.store.target_pr_plan(payload))
                return
            if path == "/api/target-workflow/preview-plan":
                self._send_json(self.server.store.preview_plan(payload))
                return
            if path == "/api/target-workflow/approval-decision":
                self._send_json(self.server.store.target_approval_decision(payload))
                return
            if path == "/api/target-production/plan":
                self._send_json(self.server.store.target_production_plan(payload))
                return
            if path == "/api/target-production/resume-deploy":
                self._send_json(self.server.store.target_production_resume_deploy(payload))
                return
            if path == "/api/parallel-tasks":
                self._send_json(self.server.store.submit_parallel_task(payload), HTTPStatus.CREATED)
                return
            if path == "/api/parallel-selection/promote":
                self._send_json(self.server.store.promote_parallel_selection(payload), HTTPStatus.ACCEPTED)
                return
            if path == "/api/parallel-selection/refresh":
                self._send_json(self.server.store.refresh_selected_candidate(payload), HTTPStatus.ACCEPTED)
                return
            if path == "/api/connections/openai-test":
                self._send_json(self.server.store.openai_connection_test())
                return
            if path == "/api/runtime-config":
                self._send_json(self.server.store.save_runtime_config(payload))
                return
            if path == "/api/draft-task-spec":
                discussion_id = str(payload.get("discussion_id") or "")
                if not discussion_id:
                    raise BadRequestError("discussion_id is required")
                self._send_json(self.server.store.draft_task_spec_from_discussion(discussion_id, payload), HTTPStatus.CREATED)
                return
            if path == "/api/draft-task-spec-jobs":
                discussion_id = str(payload.get("discussion_id") or "")
                if not discussion_id:
                    raise BadRequestError("discussion_id is required")
                self._send_json(self.server.store.start_draft_task_spec_job(discussion_id, payload), HTTPStatus.ACCEPTED)
                return
            parts = _split_path(path)
            if len(parts) == 4 and parts[:2] == ["api", "discussions"] and parts[3] == "messages":
                self._send_json(self.server.store.add_message(parts[2], payload))
                return
            if len(parts) == 4 and parts[:2] == ["api", "discussions"] and parts[3] == "draft-task-spec":
                self._send_json(self.server.store.draft_task_spec_from_discussion(parts[2], payload), HTTPStatus.CREATED)
                return
            if len(parts) == 4 and parts[:2] == ["api", "discussions"] and parts[3] == "draft-task-spec-jobs":
                self._send_json(self.server.store.start_draft_task_spec_job(parts[2], payload), HTTPStatus.ACCEPTED)
                return
            if len(parts) == 4 and parts[:2] == ["api", "task-specs"] and parts[3] == "freeze":
                frozen = self.server.store.freeze_task_spec(parts[2], payload)
                self._send_json(
                    {
                        "status": "frozen",
                        "task_spec_id": frozen["id"],
                        "spec_hash": frozen["spec_hash"],
                        "frozen_at": frozen["frozen_at"],
                    }
                )
                return
            if len(parts) == 4 and parts[:2] == ["api", "task-specs"] and parts[3] == "generate-prompt":
                self._send_json(self.server.store.generate_prompt(parts[2], payload), HTTPStatus.CREATED)
                return
            if len(parts) == 4 and parts[:2] == ["api", "task-specs"] and parts[3] == "prepare-run":
                self._send_json(self.server.store.prepare_run(parts[2], payload), HTTPStatus.CREATED)
                return
            if len(parts) == 4 and parts[:2] == ["api", "task-specs"] and parts[3] == "run-fake":
                self._send_json(self.server.store.run_fake(parts[2], payload), HTTPStatus.CREATED)
                return
            if len(parts) == 4 and parts[:2] == ["api", "task-specs"] and parts[3] == "run-codex-managed":
                self._send_json(self.server.store.start_managed_codex_run(parts[2], payload), HTTPStatus.ACCEPTED)
                return
            if len(parts) == 4 and parts[:2] == ["api", "runs"] and parts[3] == "verify":
                self._send_json(self.server.store.verify_run(parts[2]))
                return
            if len(parts) == 4 and parts[:2] == ["api", "runs"] and parts[3] == "cleanup":
                self._send_json(self.server.store.cleanup_run(parts[2]))
                return
            if len(parts) == 4 and parts[:2] == ["api", "runs"] and parts[3] == "cancel":
                self._send_json(self.server.store.cancel_run(parts[2], payload))
                return
            if len(parts) == 4 and parts[:2] == ["api", "runs"] and parts[3] == "mark-stale":
                self._send_json(self.server.store.mark_run_stale(parts[2], payload))
                return
            if len(parts) == 4 and parts[:2] == ["api", "parallel-promotion-groups"] and parts[3] == "cancel":
                self._send_json(self.server.store.cancel_parallel_promotion_group(parts[2], payload))
                return
            if len(parts) == 4 and parts[:2] == ["api", "parallel-tasks"] and parts[3] == "start-execution":
                self._send_json(self.server.store.start_parallel_task_execution(parts[2], payload))
                return
            if len(parts) == 4 and parts[:2] == ["api", "parallel-tasks"] and parts[3] == "reconcile":
                self._send_json(self.server.store.reconcile_parallel_task(parts[2], payload))
                return
            if len(parts) == 4 and parts[:2] == ["api", "parallel-tasks"] and parts[3] == "promote":
                self._send_json(self.server.store.promote_parallel_task(parts[2], payload))
                return
            if len(parts) == 4 and parts[:2] == ["api", "parallel-targets"] and parts[3] == "promote-next":
                self._send_json(self.server.store.promote_next_parallel_candidate(parts[2], payload))
                return
            self._send_error(HTTPStatus.NOT_FOUND, "route not found")
        except RequestError as exc:
            self._send_error(exc.status, str(exc))
        except OAuthError as exc:
            self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
        except ControlPlaneValidationError as exc:
            self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
        except ControlPlaneExecutionError as exc:
            self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
        except Exception as exc:
            self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def do_OPTIONS(self) -> None:  # noqa: N802
        path = _route_path(self.path)
        if path in {
            "/mcp",
            "/mcp/stream",
            "/oauth/register",
            "/oauth/token",
            "/oauth/authorize",
            "/.well-known/oauth-protected-resource",
            "/.well-known/oauth-protected-resource/mcp",
            "/.well-known/oauth-authorization-server",
            "/.well-known/openid-configuration",
            "/api/runs/live",
            "/api/runs/stream",
            "/runs/live",
        }:
            self.send_response(HTTPStatus.NO_CONTENT)
            self.send_header("Allow", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
            self.end_headers()
            return
        self._send_error(HTTPStatus.NOT_FOUND, "route not found")

    def _stream_live_runs(self) -> None:
        self._send_sse_headers()
        previous_signature = ""
        for _ in range(90):
            payload = self.server.store.live_runs()
            signature = _sse_payload_signature(payload)
            if signature != previous_signature:
                previous_signature = signature
                if not self._write_sse_event("runs", payload):
                    return
            if payload.get("active_count") == 0 and previous_signature:
                return
            time.sleep(1)

    def _stream_run(self, run_id: str) -> None:
        run_id = safe_state_component(run_id, "run_id")
        self._send_sse_headers()
        previous_signature = ""
        for _ in range(90):
            payload = self.server.store.live_run_detail(run_id)
            signature = _sse_payload_signature(payload)
            if signature != previous_signature:
                previous_signature = signature
                if not self._write_sse_event("run", payload):
                    return
            if _live_payload_is_terminal(payload):
                return
            time.sleep(1)

    def _send_sse_headers(self) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

    def _write_sse_event(self, event: str, payload: Mapping[str, Any]) -> bool:
        body = f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False, sort_keys=True)}\n\n".encode("utf-8")
        try:
            self.wfile.write(body)
            self.wfile.flush()
            return True
        except (BrokenPipeError, ConnectionResetError):
            return False

    def log_message(self, format: str, *args: object) -> None:
        return

    def _read_json_body(self) -> Mapping[str, Any]:
        payload = self._read_json_value()
        if not isinstance(payload, Mapping):
            raise BadRequestError("JSON body must be an object")
        return payload

    def _read_json_value(self) -> Any:
        length = int(self.headers.get("Content-Length") or "0")
        if length == 0:
            return {}
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        return payload

    def _read_raw_body(self) -> bytes:
        length = int(self.headers.get("Content-Length") or "0")
        if length == 0:
            return b""
        return self.rfile.read(length)

    def _read_form_or_json_body(self) -> dict[str, Any]:
        raw = self._read_raw_body()
        if not raw:
            return {}
        content_type = str(self.headers.get("Content-Type") or "").lower()
        if "application/x-www-form-urlencoded" in content_type:
            return parse_form_urlencoded(raw)
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise BadRequestError("body must be an object")
        return payload

    def _external_base_url(self) -> str:
        return external_base_url({str(key): str(value) for key, value in self.headers.items()})

    def _send_json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, text: str) -> None:
        body = text.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_redirect(self, location: str) -> None:
        self.send_response(HTTPStatus.FOUND)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _send_error(self, status: HTTPStatus, message: str) -> None:
        self._send_json({"status": "error", "error": message}, status)


class CockpitHTTPServer(ThreadingHTTPServer):
    def __init__(self, config: CockpitServerConfig) -> None:
        if config.host != "127.0.0.1":
            raise ServerConfigError("Development Control Plane server is loopback-only and must bind 127.0.0.1")
        self.config = config
        self.store = CockpitStateStore(config.state_dir, config.target_config_dir)
        self.store.config = config
        self.oauth_provider = MCPOAuthProvider(self.store)
        self.mcp_backend = MCPToolBackend(self.store, root=ROOT, oauth_provider=self.oauth_provider)
        self.store.mcp_backend = self.mcp_backend
        self.store.oauth_provider = self.oauth_provider
        super().__init__((config.host, config.port), CockpitRequestHandler)


class ServerConfigError(ValueError):
    pass


class RequestError(Exception):
    status = HTTPStatus.BAD_REQUEST


class BadRequestError(RequestError):
    status = HTTPStatus.BAD_REQUEST


class NotFoundError(RequestError):
    status = HTTPStatus.NOT_FOUND


def build_server(config: CockpitServerConfig) -> CockpitHTTPServer:
    return CockpitHTTPServer(config)


def build_connections_status(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    runtime_env = env or os.environ
    runtime_config = load_runtime_config(env=runtime_env)
    runtime_payload = runtime_config_public_dict(runtime_config)
    openai_status = get_openai_status(env=runtime_env)
    codex_bin = _codex_bin_for_execution()
    codex_version = _codex_version(codex_bin) if codex_bin else None
    codex_auth = _codex_auth_status(codex_bin)
    codex_config = _codex_config_status()
    codex_model = runtime_config.codex.model if runtime_config.exists else codex_config["model"] or runtime_config.codex.model
    codex_effort = (
        runtime_config.codex.reasoning_effort
        if runtime_config.exists
        else codex_config["model_reasoning_effort"] or runtime_config.codex.reasoning_effort
    )
    toolchain = build_toolchain_status(env=runtime_env, codex_bin=codex_bin)
    codex_runtime_parity = build_codex_runtime_parity_status(
        env=runtime_env,
        codex_bin=codex_bin,
        codex_model=codex_model,
        codex_reasoning_effort=codex_effort,
        codex_auth=codex_auth,
    )
    github = build_github_auth_status(env=runtime_env, check_remote=True)
    ssh_deploy = build_ssh_deploy_status(env=runtime_env, check_remote=True)
    return {
        "openai": {
            "configured": openai_status["configured"],
            "status": "подключён" if openai_status["configured"] else "не подключён",
            "source": openai_status["source"],
            "model": openai_status["model"],
            "reasoning_effort": openai_status["reasoning_effort"],
            "store": openai_status["store"],
            "instructions": [
                "python3 apps/dev_control_plane_setup.py openai",
                "restart cockpit after setup",
            ],
        },
        "codex": {
            "installed": bool(codex_bin),
            "status": "установлен" if codex_bin else "не найден",
            "binary": codex_bin,
            "version": codex_version,
            "auth_check_supported": bool(codex_bin),
            "auth_status": codex_auth["status"],
            "authenticated": codex_auth["authenticated"],
            "config_status": codex_config["status"],
            "model": codex_model,
            "model_reasoning_effort": codex_effort,
            "model_source": runtime_config.codex.source if runtime_config.exists else codex_config["status"],
            "sandbox_mode": runtime_config.codex.sandbox_mode,
            "sandbox_source": runtime_config.codex.sandbox_source,
            "sandbox_warning": runtime_payload["codex"].get("sandbox_warning"),
            "config_warning": codex_config.get("warning"),
            "instructions": [
                "codex login",
                "codex login --device-auth",
                "hosted/headless сервер: выполнить device-auth от service user",
            ],
        },
        "control_plane": {
            "local_only": True,
            "public_routes_enabled": False,
            "real_codex_ui_enabled": True,
            "real_codex_ui_mode": "managed_clone_only",
            "safe_fake_flow_enabled": True,
            "arbitrary_shell_ui_enabled": False,
            "mcp_enabled": True,
            "mcp_transport": MCP_TRANSPORT,
            "mcp_endpoint": MCP_ENDPOINT,
        },
        "runtime_config": runtime_payload,
        "toolchain": toolchain,
        "codex_runtime_parity": codex_runtime_parity,
        "github": github,
        "ssh_deploy": ssh_deploy,
    }


def _codex_bin_for_execution() -> str | None:
    configured = str(os.environ.get("DEV_CONTROL_PLANE_CODEX_BIN") or "").strip()
    if configured:
        if Path(configured).exists() or shutil.which(configured):
            return configured
        return None
    return shutil.which("codex")


def _codex_version(codex_bin: str | None) -> str | None:
    if not codex_bin:
        return None
    try:
        result = subprocess.run(
            [codex_bin, "--version"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
            env=_safe_status_env(),
        )
    except Exception:
        return None
    text = (result.stdout or result.stderr or "").strip()
    return text.splitlines()[0] if text else None


def _codex_auth_status(codex_bin: str | None) -> dict[str, Any]:
    return build_codex_auth_status(codex_bin, env=_safe_status_env())


def _codex_config_status() -> dict[str, Any]:
    path = _codex_config_path()
    if not path.exists():
        return {"status": "missing", "model": None, "model_reasoning_effort": None}
    if not path.is_file():
        return {
            "status": "unavailable",
            "model": None,
            "model_reasoning_effort": None,
            "warning": "codex config path is not a file",
        }
    try:
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {
            "status": "parse_error",
            "model": None,
            "model_reasoning_effort": None,
            "warning": "codex config parse failed",
        }
    return {
        "status": "present",
        "model": _public_config_value(payload.get("model")),
        "model_reasoning_effort": _public_config_value(payload.get("model_reasoning_effort")),
    }


def _codex_config_path() -> Path:
    codex_home = str(os.environ.get("CODEX_HOME") or "").strip()
    if codex_home:
        return Path(codex_home).expanduser() / "config.toml"
    home = str(os.environ.get("HOME") or "").strip()
    if home:
        return Path(home).expanduser() / ".codex" / "config.toml"
    return Path.home() / ".codex" / "config.toml"


def _public_config_value(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    lowered = text.lower()
    if text.startswith("sk-") or "authorization" in lowered or "bearer " in lowered or "token" in lowered:
        return "[redacted]"
    return text[:80]


def _safe_status_env() -> dict[str, str]:
    return runtime_command_env(git_prompt=False)


def _fake_curator_enabled() -> bool:
    return str(os.environ.get("DEV_CONTROL_PLANE_ENABLE_FAKE_CURATOR") or "").strip() == "1"


def _openai_curator_blocked_response(reason: str) -> dict[str, Any]:
    return {
        "status": "blocked",
        "task_spec_id": None,
        "validation_ok": False,
        "errors": [],
        "warnings": [],
        "provider": "openai",
        "model": _resolved_openai_model(),
        "blocked_reason": reason,
        "error_type": "unknown_error",
        "http_status": None,
        "request_id": None,
        "short_message": reason,
        "suggested_next_step": "Use DEV_CONTROL_PLANE_ENABLE_FAKE_CURATOR=1 only for smoke/internal fallback.",
    }


def _resolved_openai_model() -> str | None:
    credentials = get_openai_credentials()
    return None if credentials is None else credentials.model or None


def _curator_chat_reply(messages: list[Mapping[str, Any]]) -> str:
    reply, diagnostic = openai_curator_chat_reply(messages)
    if reply:
        return reply
    if diagnostic:
        if diagnostic.error_type == "missing_api_key":
            return OPENAI_DISCONNECTED_MESSAGE
        return openai_operator_message(diagnostic)
    return "OpenAI-куратор недоступен: неизвестная ошибка OpenAI API. Повторите проверку во вкладке Подключения."


def _run_summary_from_result(result, verifier: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = run_result_to_dict(result)
    return {
        "status": payload["status"],
        "run_id": payload["id"],
        "task_spec_id": payload["task_spec_id"],
        "step_id": payload["step_id"],
        "branch_name": payload["branch_name"],
        "run_dir": payload["run_dir"],
        "worktree_path": payload["worktree_path"],
        "prompt_path": payload["prompt_path"],
        "handoff_path": payload["handoff_path"],
        "log_path": payload["log_path"],
        "changed_files": payload["changed_files"],
        "check_results": payload["check_results"],
        "blocker_reason": payload["blocker_reason"],
        "next_manual_step": payload["next_manual_step"],
        "verifier_status": None if verifier is None else verifier.get("status"),
        "mandatory_handoff_blocks_present": False if verifier is None else bool(verifier.get("mandatory_handoff_blocks_present")),
        "errors": [],
    }


def _run_summary_from_record(record: Mapping[str, Any]) -> dict[str, Any]:
    result = record.get("result")
    if not isinstance(result, Mapping):
        raise BadRequestError("run record missing result object")
    if result.get("workspace_path"):
        return _target_run_summary_from_record(record)
    verifier = record.get("verifier")
    if verifier is not None and not isinstance(verifier, Mapping):
        verifier = None
    return {
        "status": result.get("status"),
        "run_id": result.get("id"),
        "task_spec_id": result.get("task_spec_id"),
        "step_id": result.get("step_id"),
        "branch_name": result.get("branch_name"),
        "run_dir": result.get("run_dir"),
        "worktree_path": result.get("worktree_path"),
        "prompt_path": result.get("prompt_path"),
        "handoff_path": result.get("handoff_path"),
        "log_path": result.get("log_path"),
        "changed_files": result.get("changed_files", []),
        "check_results": result.get("check_results", []),
        "blocker_reason": result.get("blocker_reason"),
        "next_manual_step": result.get("next_manual_step"),
        "verifier_status": None if verifier is None else verifier.get("status"),
        "mandatory_handoff_blocks_present": False if verifier is None else bool(verifier.get("mandatory_handoff_blocks_present")),
        "errors": [],
    }


def _target_run_summary_from_record(record: Mapping[str, Any]) -> dict[str, Any]:
    result = record.get("result")
    if not isinstance(result, Mapping):
        raise BadRequestError("target run record missing result object")
    verifier = record.get("verifier")
    if verifier is not None and not isinstance(verifier, Mapping):
        verifier = None
    target_project = record.get("target_project")
    target_project_id = None
    if isinstance(target_project, Mapping):
        target_project_id = target_project.get("project_id")
    check_results = result.get("check_results", [])
    original_unchanged = _check_status(check_results, "target_repo_unchanged") == "passed"
    if verifier and isinstance(verifier.get("check_results"), list):
        original_unchanged = _check_status(verifier.get("check_results", []), "target_repo_unchanged") == "passed"
    return {
        "status": result.get("status"),
        "run_id": result.get("id"),
        "task_spec_id": result.get("task_spec_id"),
        "step_id": result.get("step_id"),
        "branch_name": None,
        "target_project_id": result.get("target_project_id") or target_project_id,
        "run_dir": result.get("run_dir"),
        "worktree_path": result.get("workspace_path"),
        "workspace_path": result.get("workspace_path"),
        "prompt_path": result.get("prompt_path"),
        "handoff_path": result.get("handoff_path"),
        "log_path": result.get("log_path"),
        "diff_path": result.get("diff_path"),
        "changed_files": result.get("changed_files", []),
        "check_results": check_results,
        "blocker_reason": result.get("blocker_reason"),
        "next_manual_step": result.get("next_manual_step"),
        "verifier_status": result.get("verifier_status") or (None if verifier is None else verifier.get("status")),
        "mandatory_handoff_blocks_present": False if verifier is None else bool(verifier.get("mandatory_handoff_blocks_present")),
        "codex_exit_code": result.get("codex_exit_code"),
        "original_target_unchanged": original_unchanged,
        "errors": [],
    }


def _decorate_run_summary(summary: dict[str, Any], task_spec_payload: Mapping[str, Any]) -> None:
    target_project_id = summary.get("target_project_id") or task_spec_payload.get("target_project_id")
    summary["target_project_id"] = target_project_id
    summary["changed_files_count"] = len(summary.get("changed_files") or [])
    summary["prompt_available"] = bool(summary.get("prompt_path"))
    summary["handoff_available"] = bool(summary.get("handoff_path"))
    summary["diff_available"] = bool(summary.get("diff_path"))
    summary["cleanup_available"] = bool(summary.get("worktree_path") or summary.get("workspace_path"))
    summary["blocker"] = _blocker_summary(summary)
    summary["run_result_summary"] = _compact_run_result_summary(summary)


def _compact_run_result_summary(summary: Mapping[str, Any]) -> dict[str, Any]:
    check_results = summary.get("check_results") or []
    return {
        "status": _operator_status(summary),
        "raw_status": summary.get("status"),
        "verifier_status": summary.get("verifier_status"),
        "target_project_id": summary.get("target_project_id"),
        "run_id": summary.get("run_id"),
        "changed_files": list(summary.get("changed_files") or []),
        "changed_files_count": len(summary.get("changed_files") or []),
        "blocker_reason": summary.get("blocker_reason"),
        "next_manual_step": summary.get("next_manual_step"),
        "prompt_available": bool(summary.get("prompt_path")),
        "handoff_available": bool(summary.get("handoff_path")),
        "diff_available": bool(summary.get("diff_path")),
        "cleanup_available": bool(summary.get("worktree_path") or summary.get("workspace_path")),
        "original_target_unchanged": summary.get("original_target_unchanged"),
        "target_repo_unchanged_status": _check_status(check_results, "target_repo_unchanged"),
        "git_diff_check_status": _check_status(check_results, "git_diff_check"),
    }


def _real_job_updates_from_summary(summary: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "run_id": summary.get("run_id"),
        "run_dir": summary.get("run_dir"),
        "workspace_path": summary.get("workspace_path") or summary.get("worktree_path"),
        "prompt_path": summary.get("prompt_path"),
        "handoff_path": summary.get("handoff_path"),
        "log_path": summary.get("log_path"),
        "diff_path": summary.get("diff_path"),
        "verifier_status": summary.get("verifier_status"),
        "changed_files": list(summary.get("changed_files") or []),
        "changed_files_count": len(summary.get("changed_files") or []),
        "blocker_reason": summary.get("blocker_reason"),
        "next_manual_step": summary.get("next_manual_step"),
        "mandatory_handoff_blocks_present": summary.get("mandatory_handoff_blocks_present"),
        "original_target_unchanged": summary.get("original_target_unchanged"),
        "run_result_summary": summary.get("run_result_summary") or _compact_run_result_summary(summary),
        "blocker": summary.get("blocker") or _blocker_summary(summary),
    }


def _real_job_status_from_result(summary: Mapping[str, Any]) -> str:
    status = str(summary.get("status") or "")
    verifier_status = str(summary.get("verifier_status") or "")
    if status == "verifier_passed" or verifier_status == "passed":
        return "passed"
    if status == "blocked" or verifier_status == "blocked":
        return "blocked"
    if status == "human_gate_required":
        return "blocked"
    return "failed"


def _real_codex_status_message(status: str) -> str:
    return {
        "queued": "Codex запуск поставлен в очередь.",
        "preparing": "Готовлю managed clone...",
        "running_codex": "Codex выполняет задачу...",
        "verifying": "Проверяю результат...",
        "passed": "Готово: Codex run прошёл verifier.",
        "blocked": "Блокер: Codex run остановлен gate/verifier.",
        "failed": "Ошибка: Codex run завершился неуспешно.",
    }.get(status, status)


def _timeline_event_for_job_status(status: str, *, detail: str | None = None) -> dict[str, Any] | None:
    mapping = {
        "queued": ("queued", "info", "Ожидаем старт выполнения..."),
        "preparing": ("preparing", "info", "Готовлю managed clone..."),
        "running_codex": ("codex", "info", "Codex выполняет задачу..."),
        "verifying": ("verifier", "info", "Verifier проверяет результат..."),
        "passed": ("complete", "success", "Готово: verifier passed."),
        "blocked": ("blocked", "error", "Блокер: Codex run остановлен."),
        "failed": ("failed", "error", "Ошибка: Codex run завершился неуспешно."),
    }
    raw = mapping.get(status)
    if not raw:
        return None
    phase, level, title = raw
    return {"phase": phase, "level": level, "title": title, "detail": detail}


def _blocker_summary(summary: Mapping[str, Any]) -> dict[str, Any]:
    reason = summary.get("blocker_reason")
    if not reason:
        return {
            "status": "none",
            "reason": None,
            "next_manual_step": None,
            "source": None,
            "technical_details": {},
        }
    verifier_status = summary.get("verifier_status")
    source = "verifier" if verifier_status in {"failed", "blocked"} else "execution"
    return {
        "status": "present",
        "reason": reason,
        "next_manual_step": summary.get("next_manual_step") or "Inspect run artifacts and verifier output.",
        "source": source,
        "technical_details": {
            "run_id": summary.get("run_id"),
            "verifier_status": verifier_status,
            "check_results": summary.get("check_results") or [],
        },
    }


def _check_status(check_results: Any, name: str) -> str | None:
    if not isinstance(check_results, list):
        return None
    for check in check_results:
        if isinstance(check, Mapping) and check.get("name") == name:
            return str(check.get("status") or "")
    return None


def _operator_status(summary: Mapping[str, Any]) -> str:
    status = str(summary.get("status") or "")
    verifier_status = str(summary.get("verifier_status") or "")
    if status == "verifier_passed" or verifier_status == "passed":
        return "Passed"
    if status == "blocked" or verifier_status == "blocked":
        return "Blocked"
    if status == "human_gate_required":
        return "Human gate required"
    if status == "failed" or verifier_status == "failed":
        return "Failed"
    if status == "prepared":
        return "Prepared"
    return status or "Unknown"


def _task_card_summary(spec: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "title": spec.get("title"),
        "target_project": spec.get("target_project_id"),
        "class": spec.get("task_class"),
        "goal": spec.get("goal"),
        "scope": spec.get("scope", []),
        "not_in_scope": spec.get("not_in_scope", []),
        "acceptance_criteria": spec.get("acceptance_criteria", []),
        "required_smokes": spec.get("required_smokes", []),
        "forbidden_paths": spec.get("forbidden_paths", []),
        "forbidden_actions": spec.get("forbidden_actions", []),
        "human_gates": spec.get("human_gates", []),
        "warnings": _target_warnings_from_spec(spec),
        "next_recommended_action": _next_action_for_spec(spec),
    }


def _target_warnings_from_spec(spec: Mapping[str, Any]) -> list[str]:
    summary = spec.get("target_context_summary")
    if isinstance(summary, Mapping):
        warnings = summary.get("warnings", [])
        if isinstance(warnings, list):
            return [str(item) for item in warnings]
    return []


def _next_action_for_spec(spec: Mapping[str, Any]) -> str:
    if not spec:
        return "Draft Task Spec from Discussion"
    if spec.get("status") != "frozen":
        return "Freeze Task"
    return "Run Safe Fake Flow"


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 1)


def _draft_performance_summary(
    total_started: float,
    timings: Mapping[str, float],
    *,
    provider: str,
    discussion: Mapping[str, Any],
    repo_context_summary: str | None,
    model: str | None = None,
) -> dict[str, Any]:
    runtime_config = load_runtime_config()
    openai_status = get_openai_status()
    messages = discussion.get("messages", [])
    text_payload = json.dumps({"messages": messages, "repo_context_summary": repo_context_summary}, ensure_ascii=False)
    selected_model = model or (openai_status.get("model") if provider == "openai" else None)
    selected_effort = openai_status.get("reasoning_effort") if provider == "openai" else None
    return {
        "total_duration_ms": _elapsed_ms(total_started),
        "target_validation_duration_ms": round(float(timings.get("target_validation_duration_ms") or 0.0), 1),
        "context_build_duration_ms": round(float(timings.get("context_build_duration_ms") or 0.0), 1),
        "openai_curator_duration_ms": round(float(timings.get("curator_duration_ms") or 0.0), 1),
        "card_validation_duration_ms": round(float(timings.get("card_validation_duration_ms") or 0.0), 1),
        "provider": provider,
        "selected_model": selected_model,
        "selected_reasoning_effort": selected_effort,
        "runtime_config_source": runtime_config.openai.source,
        "estimated_input_tokens": max(1, len(text_payload) // 4),
        "token_usage_source": "estimate",
    }


def _target_context_for_intake(target, validation) -> str:
    summary = target_context_summary_to_dict(build_target_context_summary(target))
    source_summary: str
    if _remote_managed_clone_warning_ready(validation):
        source_summary = (
            f"{target.display_name}: remote managed clone source is available at {validation.repo_url} "
            f"branch {validation.branch}; local repo_path is not required for hosted card generation. "
            "Configured source_of_truth_paths will be verified inside the managed clone workspace."
        )
    else:
        try:
            snapshot = build_target_context_snapshot(target, max_bytes_per_file=2000)
            source_summary = snapshot.source_summary
        except Exception as exc:
            source_summary = f"target context snapshot unavailable: {exc}"
    return _compact_target_context_for_intake(summary, source_summary)


def _remote_managed_clone_warning_ready(validation) -> bool:
    return (
        getattr(validation, "source_mode", None) == "remote_managed_clone"
        and getattr(validation, "remote_source_available", False) is True
        and getattr(validation, "managed_clone_ready", False) is True
    )


def _compact_target_context_for_intake(summary: Mapping[str, Any], source_summary: str) -> str:
    payload = {
        "project_id": summary.get("project_id"),
        "display_name": summary.get("display_name"),
        "source_mode": summary.get("source_mode"),
        "repo_url": summary.get("repo_url"),
        "branch": summary.get("branch"),
        "validation_status": summary.get("validation_status"),
        "remote_source_available": summary.get("remote_source_available"),
        "managed_clone_ready": summary.get("managed_clone_ready"),
        "current_branch": summary.get("current_branch"),
        "head_commit": summary.get("head_commit"),
        "source_of_truth_paths_found": summary.get("source_of_truth_paths_found", []),
        "missing_source_paths": summary.get("missing_source_paths", []),
        "derived_secondary_paths": summary.get("derived_secondary_paths", []),
        "default_forbidden_paths": summary.get("default_forbidden_paths", []),
        "default_forbidden_actions": summary.get("default_forbidden_actions", []),
        "default_required_smokes": summary.get("default_required_smokes", []),
        "workflow_notes": summary.get("workflow_notes", []),
        "warnings": summary.get("warnings", []),
        "source_summary": source_summary,
        "source_of_truth_note": "Target context is read-only evidence, not source of truth.",
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Loopback-only Development Control Plane server.")
    parser.add_argument("--host", help=f"Bind host. Defaults to ${HOST_ENV} or {DEFAULT_HOST}. Non-loopback bind is rejected.")
    parser.add_argument("--port", type=int, help=f"Bind port. Defaults to ${PORT_ENV} or {DEFAULT_PORT}.")
    parser.add_argument(
        "--state-dir",
        type=Path,
        help=(
            f"Control-plane state root. Defaults to ${STATE_DIR_ENV}, then {DEFAULT_STATE_DIR} for local "
            f"profile or {HOSTED_STATE_DIR} for hosted profile."
        ),
    )
    parser.add_argument(
        "--runtime-profile",
        choices=sorted(RUNTIME_PROFILES),
        help=f"Runtime profile. Defaults to ${RUNTIME_PROFILE_ENV} or {DEFAULT_RUNTIME_PROFILE}.",
    )
    parser.add_argument("--target-config-dir", default=TARGET_CONFIG_DIR, type=Path)
    args = parser.parse_args(argv)

    try:
        config = _server_config_from_args(args)
        server = build_server(config)
    except ServerConfigError as exc:
        print(
            json.dumps(
                {
                    "status": "blocked",
                    "error": str(exc),
                    "bind_policy": BIND_POLICY,
                    "local_only": True,
                    "public_routes_enabled": False,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
            flush=True,
        )
        return 2
    print(
        json.dumps(
            {
                "status": "serving",
                "host": config.host,
                "port": server.server_port,
                "runtime_profile": config.runtime_profile,
                "bind_policy": config.bind_policy,
                "state_dir": str(config.state_dir),
                "target_config_dir": str(config.target_config_dir),
                "local_only": True,
                "notice": LOCAL_ONLY_NOTICE,
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    return 0


def _server_config_from_args(args: argparse.Namespace) -> CockpitServerConfig:
    runtime_profile = _runtime_profile(args.runtime_profile)
    host = _host_value(args.host)
    port = _port_value(args.port)
    state_dir = _state_dir_value(args.state_dir, runtime_profile)
    return CockpitServerConfig(
        host=host,
        port=port,
        state_dir=state_dir,
        target_config_dir=args.target_config_dir,
        runtime_profile=runtime_profile,
        bind_policy=BIND_POLICY,
    )


def _runtime_profile(cli_value: str | None) -> str:
    value = str(cli_value or os.environ.get(RUNTIME_PROFILE_ENV) or DEFAULT_RUNTIME_PROFILE).strip().lower()
    if value not in RUNTIME_PROFILES:
        raise ServerConfigError(f"unsupported runtime profile: {value}")
    return value


def _host_value(cli_value: str | None) -> str:
    host = str(cli_value or os.environ.get(HOST_ENV) or DEFAULT_HOST).strip()
    if host != DEFAULT_HOST:
        raise ServerConfigError(f"non-loopback bind is not allowed by default: {host}")
    return host


def _port_value(cli_value: int | None) -> int:
    raw = cli_value if cli_value is not None else os.environ.get(PORT_ENV, DEFAULT_PORT)
    try:
        port = int(raw)
    except (TypeError, ValueError) as exc:
        raise ServerConfigError(f"invalid port: {raw}") from exc
    if port < 0 or port > 65535:
        raise ServerConfigError(f"port is out of range: {port}")
    return port


def _state_dir_value(cli_value: Path | None, runtime_profile: str) -> Path:
    default_state_dir = HOSTED_STATE_DIR if runtime_profile == HOSTED_RUNTIME_PROFILE else DEFAULT_STATE_DIR
    return resolve_state_root(cli_value, default=default_state_dir)


def _render_html() -> str:
    example = escape(EXAMPLE_TASK_SPEC.read_text(encoding="utf-8"))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Development Control Plane</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 0; background: #f7f7f5; color: #202124; }}
    header {{ padding: 18px 24px; background: #17202a; color: white; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 20px; display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
    section {{ background: white; border: 1px solid #d9d9d4; border-radius: 6px; padding: 14px; }}
    h1 {{ margin: 0; font-size: 22px; }}
    h2 {{ margin: 0 0 10px; font-size: 16px; }}
    textarea, input, select {{ width: 100%; box-sizing: border-box; border: 1px solid #c8c8c2; border-radius: 4px; padding: 8px; font: 13px ui-monospace, SFMono-Regular, Menlo, monospace; }}
    textarea {{ min-height: 150px; resize: vertical; }}
    button {{ margin: 8px 8px 0 0; border: 1px solid #2f5f8f; background: #2f6fab; color: white; border-radius: 4px; padding: 7px 10px; cursor: pointer; }}
    button.secondary {{ background: #f4f4f0; color: #202124; border-color: #b7b7b0; }}
    pre {{ white-space: pre-wrap; overflow-wrap: anywhere; background: #f3f3ef; padding: 10px; border-radius: 4px; max-height: 360px; overflow: auto; }}
    .full {{ grid-column: 1 / -1; }}
    .muted {{ color: #666; font-size: 13px; }}
  </style>
</head>
<body>
  <header>
    <h1>Development Control Plane</h1>
    <div class="muted">{escape(LOCAL_ONLY_NOTICE)}</div>
  </header>
  <main>
    <section class="full">
      <h2>Target Project</h2>
      <select id="targetProjectInput" onchange="selectTargetProject()">
        <option value="">No target selected</option>
      </select>
      <button class="secondary" onclick="loadTargets()">Refresh targets</button>
      <pre id="targetStatus">Target repos are external and read-only by default.</pre>
    </section>
    <section>
      <h2>Discuss</h2>
      <textarea id="messageInput" placeholder="Operator message"></textarea>
      <button onclick="addMessage()">Add message</button>
      <select id="curatorModeInput">
        <option value="fake">Fake curator</option>
        <option value="openai">OpenAI curator</option>
      </select>
      <button onclick="draftTaskSpec()">Draft Task Spec from Discussion</button>
      <pre id="messages">No discussion yet.</pre>
      <pre id="draftStatus">No draft requested.</pre>
    </section>
    <section>
      <h2>Human Gates</h2>
      <pre id="humanGates">No human gates for this spec.</pre>
    </section>
    <section class="full">
      <h2>Task Spec</h2>
      <h3>Task Card</h3>
      <pre id="taskSpecSummary">No task spec yet.</pre>
      <h3>Next recommended action</h3>
      <pre id="nextAction">Draft Task Spec from Discussion</pre>
      <details>
        <summary>Advanced / Raw JSON</summary>
        <textarea id="taskSpecInput">{example}</textarea>
        <button class="secondary" onclick="loadExample()">Load example task spec</button>
      </details>
      <button onclick="saveDraft()">Validate / Save Draft</button>
      <button onclick="freezeTask()">Freeze Task</button>
      <pre id="taskSpecStatus">Ready.</pre>
    </section>
    <section>
      <h2>Sprint Plan</h2>
      <pre id="sprintPlan">No saved task spec.</pre>
    </section>
    <section>
      <h2>Prompt</h2>
      <input id="stepIdInput" placeholder="optional step id">
      <button onclick="generatePrompt()">Generate Codex Prompt</button>
      <pre id="promptOutput">No prompt generated.</pre>
    </section>
    <section class="full">
      <h2>Run</h2>
      <div class="muted">UI execution is fake-flow or operator-confirmed real Codex in managed clone. No live/deploy/public route.</div>
      <button onclick="runSafeFakeFlow()">Run Safe Fake Flow</button>
      <button class="secondary" onclick="cleanupRun()">Cleanup Run</button>
      <details>
        <summary>Advanced run controls</summary>
        <button onclick="prepareRun()">Prepare Run</button>
        <button onclick="runFake()">Run Fake Executor</button>
        <button onclick="verifyRun()">Verify Run</button>
      </details>
      <h3>Result summary</h3>
      <pre id="runStatus">No run yet.</pre>
      <h3>Blocker</h3>
      <pre id="blockerStatus">No blocker</pre>
      <details>
        <summary>Prompt preview</summary>
        <pre id="runPrompt">No run prompt.</pre>
      </details>
      <details>
        <summary>Handoff preview</summary>
        <pre id="runHandoff">No handoff.</pre>
      </details>
    </section>
  </main>
  <script>
    let discussionId = null;
    let taskSpecId = null;
    let currentRunId = null;
    let selectedTargetProjectId = null;

    async function request(path, options = {{}}) {{
      const response = await fetch(path, options);
      const text = await response.text();
      const data = text ? JSON.parse(text) : {{}};
      if (!response.ok) throw new Error(data.error || response.statusText);
      return data;
    }}

    async function loadExample() {{
      const data = await request('/api/example-task-spec');
      document.getElementById('taskSpecInput').value = JSON.stringify(data, null, 2);
    }}

    async function loadTargets() {{
      const data = await request('/api/target-projects');
      const select = document.getElementById('targetProjectInput');
      const current = select.value;
      select.innerHTML = '<option value="">No target selected</option>';
      for (const target of data.targets || []) {{
        const option = document.createElement('option');
        option.value = target.project_id;
        option.textContent = `${{target.display_name}} (${{target.validation_status}})`;
        select.appendChild(option);
      }}
      if (current) select.value = current;
      selectedTargetProjectId = select.value || null;
      document.getElementById('targetStatus').textContent = JSON.stringify(data.targets || [], null, 2);
    }}

    async function selectTargetProject() {{
      selectedTargetProjectId = document.getElementById('targetProjectInput').value || null;
      if (!selectedTargetProjectId) {{
        document.getElementById('targetStatus').textContent = 'No target selected. Generic defaults will be used.';
        return;
      }}
      const data = await request(`/api/target-projects/${{selectedTargetProjectId}}`);
      document.getElementById('targetStatus').textContent = JSON.stringify(data, null, 2);
    }}

    async function addMessage() {{
      if (!discussionId) {{
        const discussion = await request('/api/discussions', {{method: 'POST', body: '{{}}'}});
        discussionId = discussion.id;
      }}
      const content = document.getElementById('messageInput').value;
      const discussion = await request(`/api/discussions/${{discussionId}}/messages`, {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{role: 'operator', content}})
      }});
      document.getElementById('messages').textContent = JSON.stringify(discussion.messages, null, 2);
    }}

    async function draftTaskSpec() {{
      try {{
        if (!discussionId) {{
          const discussion = await request('/api/discussions', {{method: 'POST', body: '{{}}'}});
          discussionId = discussion.id;
        }}
        const mode = document.getElementById('curatorModeInput').value || 'fake';
        const result = await request(`/api/discussions/${{discussionId}}/draft-task-spec`, {{
          method: 'POST',
          headers: {{'Content-Type': 'application/json'}},
          body: JSON.stringify({{mode, target_project_id: selectedTargetProjectId}})
        }});
        document.getElementById('draftStatus').textContent = JSON.stringify(result, null, 2);
        if (result.task_spec) {{
          taskSpecId = result.task_spec_id;
          document.getElementById('taskSpecInput').value = JSON.stringify(result.task_spec, null, 2);
          renderSpec(result.task_spec);
          if (result.target_summary) {{
            document.getElementById('targetStatus').textContent = JSON.stringify(result.target_summary, null, 2);
          }}
        }}
      }} catch (error) {{
        document.getElementById('draftStatus').textContent = String(error);
      }}
    }}

    async function saveDraft() {{
      try {{
        const payload = JSON.parse(document.getElementById('taskSpecInput').value);
        if (selectedTargetProjectId && !payload.target_project_id) payload.target_project_id = selectedTargetProjectId;
        const saved = await request('/api/task-specs', {{
          method: 'POST',
          headers: {{'Content-Type': 'application/json'}},
          body: JSON.stringify(payload)
        }});
        taskSpecId = saved.id;
        renderSpec(saved);
      }} catch (error) {{
        document.getElementById('taskSpecStatus').textContent = String(error);
      }}
    }}

    async function freezeTask() {{
      if (!taskSpecId) await saveDraft();
      const result = await request(`/api/task-specs/${{taskSpecId}}/freeze`, {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: '{{}}'
      }});
      const spec = await request(`/api/task-specs/${{taskSpecId}}`);
      renderSpec(spec);
      document.getElementById('taskSpecStatus').textContent = JSON.stringify(result, null, 2);
    }}

    async function generatePrompt() {{
      const stepId = document.getElementById('stepIdInput').value.trim();
      const summary = await request(`/api/task-specs/${{taskSpecId}}/generate-prompt`, {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify(stepId ? {{step_id: stepId}} : {{}})
      }});
      const response = await fetch(`/api/prompts/${{summary.id}}`);
      document.getElementById('promptOutput').textContent = await response.text();
    }}

    async function runSafeFakeFlow() {{
      try {{
        const summary = await request('/api/guided-safe-fake-run', {{
          method: 'POST',
          headers: {{'Content-Type': 'application/json'}},
          body: JSON.stringify({{task_spec_id: taskSpecId}})
        }});
        currentRunId = summary.run_id;
        renderRun(summary);
        await loadRun(currentRunId);
      }} catch (error) {{
        document.getElementById('runStatus').textContent = String(error);
      }}
    }}

    async function prepareRun() {{
      const stepId = document.getElementById('stepIdInput').value.trim();
      const summary = await request(`/api/task-specs/${{taskSpecId}}/prepare-run`, {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify(stepId ? {{step_id: stepId}} : {{}})
      }});
      currentRunId = summary.run_id;
      renderRun(summary);
      await loadRun(currentRunId);
    }}

    async function runFake() {{
      const stepId = document.getElementById('stepIdInput').value.trim();
      const summary = await request(`/api/task-specs/${{taskSpecId}}/run-fake`, {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify(stepId ? {{step_id: stepId}} : {{}})
      }});
      currentRunId = summary.run_id;
      renderRun(summary);
      await loadRun(currentRunId);
    }}

    async function verifyRun() {{
      if (!currentRunId) return;
      const summary = await request(`/api/runs/${{currentRunId}}/verify`, {{method: 'POST', body: '{{}}'}});
      renderRun(summary);
      await loadRun(currentRunId);
    }}

    async function cleanupRun() {{
      if (!currentRunId) return;
      const summary = await request(`/api/runs/${{currentRunId}}/cleanup`, {{method: 'POST', body: '{{}}'}});
      renderRun(summary);
    }}

    async function loadRun(runId) {{
      const run = await request(`/api/runs/${{runId}}`);
      renderRun(run);
      document.getElementById('runPrompt').textContent = run.prompt_text || 'No run prompt.';
      document.getElementById('runHandoff').textContent = run.handoff_text || 'No handoff.';
    }}

    function renderSpec(spec) {{
      document.getElementById('taskSpecStatus').textContent = JSON.stringify({{id: spec.id, status: spec.status, spec_hash: spec.spec_hash}}, null, 2);
      document.getElementById('taskSpecSummary').textContent = formatTaskCard(spec);
      document.getElementById('nextAction').textContent = nextActionForSpec(spec);
      document.getElementById('sprintPlan').textContent = JSON.stringify(spec.sprint_steps || [], null, 2);
      const gates = spec.human_gates || [];
      document.getElementById('humanGates').textContent = gates.length ? gates.map((gate) => `- ${{gate}}`).join('\\n') : 'No human gates for this spec.';
    }}

    function renderRun(run) {{
      const view = run.run_result_summary || {{
        status: run.status,
        verifier_status: run.verifier_status,
        target_project_id: run.target_project_id || null,
        run_id: run.run_id,
        changed_files_count: (run.changed_files || []).length,
        blocker_reason: run.blocker_reason || null,
        next_manual_step: run.next_manual_step || null,
        prompt_available: Boolean(run.prompt_path),
        handoff_available: Boolean(run.handoff_path),
        cleanup_available: Boolean(run.worktree_path)
      }};
      document.getElementById('runStatus').textContent = JSON.stringify(view, null, 2);
      const blocker = run.blocker || (run.blocker_reason ? {{
        status: 'present',
        reason: run.blocker_reason,
        next_manual_step: run.next_manual_step || 'Inspect run artifacts and verifier output.',
        source: 'verifier'
      }} : {{status: 'none', reason: null, next_manual_step: null, source: null}});
      document.getElementById('blockerStatus').textContent = blocker.status === 'none'
        ? 'No blocker'
        : JSON.stringify(blocker, null, 2);
    }}

    function nextActionForSpec(spec) {{
      if (!spec || !spec.id) return 'Draft Task Spec from Discussion';
      if (spec.status !== 'frozen') return 'Freeze Task';
      return 'Run Safe Fake Flow';
    }}

    function formatTaskCard(spec) {{
      const target = spec.target_project_id || 'none';
      const targetSummary = spec.target_context_summary || {{}};
      const warnings = targetSummary.warnings || [];
      return [
        `Title: ${{spec.title || ''}}`,
        `Target project: ${{target}}`,
        `Class: ${{spec.task_class || ''}}`,
        '',
        `Goal:\\n${{spec.goal || ''}}`,
        '',
        `Scope:\\n${{formatList(spec.scope)}}`,
        '',
        `Not in scope:\\n${{formatList(spec.not_in_scope)}}`,
        '',
        `Acceptance criteria:\\n${{formatList(spec.acceptance_criteria)}}`,
        '',
        `Required smokes:\\n${{formatList(spec.required_smokes)}}`,
        '',
        `Forbidden paths:\\n${{formatList(spec.forbidden_paths)}}`,
        '',
        `Forbidden actions:\\n${{formatList(spec.forbidden_actions)}}`,
        '',
        `Human gates:\\n${{formatList(spec.human_gates) || 'No human gates for this spec.'}}`,
        '',
        `Warnings:\\n${{formatList(warnings) || 'No warnings'}}`
      ].join('\\n');
    }}

    function formatList(value) {{
      if (!Array.isArray(value) || value.length === 0) return '';
      return value.map((item) => `- ${{item}}`).join('\\n');
    }}

    loadTargets().catch((error) => {{
      document.getElementById('targetStatus').textContent = String(error);
    }});
  </script>
</body>
</html>"""


def _render_live_runs_html(*, selected_run_id: str | None = None) -> str:
    html = """<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Мониторинг — DevControl</title>
  <style>
    :root { color-scheme: dark; --bg: #0b0d10; --nav: #0f1115; --panel: #15171c; --panel-2: #1a1d23; --line: #2a2f38; --line-soft: #20242b; --text: #f2f4f8; --muted: #8d96a6; --accent: #8ab4ff; --ok: #5bd182; --warn: #f0c15a; --bad: #ff7b72; --term: #06080b; }
    * { box-sizing: border-box; }
    body { margin: 0; background: var(--bg); color: var(--text); font-family: Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    .app-frame { height: 100vh; min-height: 0; display: grid; grid-template-columns: 244px minmax(0, 1fr); overflow: hidden; }
    .sidebar { background: var(--nav); border-right: 1px solid var(--line-soft); padding: 18px 14px; display: flex; flex-direction: column; gap: 18px; }
    .brand { display: grid; gap: 3px; padding: 2px 8px 12px; border-bottom: 1px solid var(--line-soft); }
    .brand strong { font-size: 15px; letter-spacing: 0; }
    .brand span { color: var(--muted); font-size: 12px; }
    .side-nav { display: grid; gap: 4px; }
    .side-link { color: #d7dce5; text-decoration: none; border-radius: 7px; padding: 9px 10px; font-size: 14px; border: 1px solid transparent; }
    .side-link:hover, .side-link.active { background: #191d24; border-color: var(--line-soft); color: var(--text); }
    .side-link.active { box-shadow: inset 2px 0 0 var(--accent); }
    .workspace { min-width: 0; min-height: 0; display: grid; grid-template-rows: auto minmax(0, 1fr); }
    .topbar { display: flex; justify-content: space-between; gap: 16px; align-items: center; padding: 18px 24px; border-bottom: 1px solid var(--line-soft); background: rgba(15,17,21,.86); backdrop-filter: blur(12px); }
    h1 { margin: 0; font-size: 20px; letter-spacing: 0; }
    .subtitle { margin-top: 4px; color: var(--muted); font-size: 13px; }
    .live-main { display: grid; grid-template-columns: 340px minmax(0, 1fr); gap: 14px; padding: 18px; min-height: 0; height: 100%; overflow: hidden; }
    .runs-panel, section, .panel { border: 1px solid var(--line); border-radius: 8px; background: var(--panel); }
    .runs-panel { overflow: hidden; min-height: 0; display: grid; grid-template-rows: auto minmax(0, 1fr); }
    .run-list { display: grid; align-content: start; gap: 1px; height: 100%; min-height: 0; overflow-y: auto; overflow-x: hidden; background: var(--line-soft); scrollbar-gutter: stable; padding-right: 3px; }
    .run-item { display: grid; gap: 6px; padding: 12px 20px 12px 14px; background: var(--panel); border: 0; color: var(--text); text-align: left; cursor: pointer; width: 100%; min-width: 0; overflow-wrap: anywhere; }
    .run-item:hover, .run-item.active { background: #1e242d; }
    .run-selector > span { min-width: 0; }
    .task-title { display: block; font-size: 14px; font-weight: 650; color: var(--text); line-height: 1.25; overflow-wrap: anywhere; }
    .run-id { font: 11px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; color: #8d96a6; overflow-wrap: anywhere; }
    .meta { display: flex; flex-wrap: wrap; gap: 6px; color: var(--muted); font-size: 12px; }
    .pill { border: 1px solid var(--line); border-radius: 999px; padding: 2px 7px; }
    .pill.status-running { border-color: #315fa8; background: #10233f; color: #a5d6ff; }
    .pill.status-stale { border-color: #725316; background: #2b220e; color: #f0c15a; }
    .pill.status-control { border-color: #7a5b1d; background: #30230c; color: #ffd27a; }
    .pill.status-failed { border-color: #7d3434; background: #321719; color: #ffb3ad; }
    .pill.status-ok { border-color: #2f6b45; background: #102419; color: #91f0ad; }
    .pill.status-ready { border-color: #725316; background: #2b220e; color: #f0c15a; }
    .pill.status-refresh { border-color: #6f4ab5; background: #241b34; color: #d2a8ff; }
    .selection-bar { display: grid; gap: 8px; padding: 10px 12px; border-bottom: 1px solid var(--line-soft); background: #11151b; }
    .selection-actions { display: flex; gap: 8px; align-items: center; }
    .selection-hint { color: var(--muted); font-size: 12px; }
    .run-selector { display: flex; align-items: center; gap: 7px; }
    .run-selector input { width: 15px; height: 15px; accent-color: var(--accent); }
    .run-selector input:disabled { opacity: .42; }
    .run-status-line { align-items: center; }
    .row-spinner { width: 8px; height: 8px; border-radius: 50%; background: var(--accent); box-shadow: 0 0 0 0 rgba(138,180,255,.55); animation: pulse 1.35s ease-in-out infinite; }
    .row-spinner.is-waiting { background: var(--warn); box-shadow: 0 0 0 0 rgba(240,193,90,.55); }
    .row-spinner.is-hidden { display: none; }
    .operator-label { color: var(--muted); }
    .status-ok { color: var(--ok); }
    .status-warn { color: var(--warn); }
    .status-bad { color: var(--bad); }
    .running-line { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; color: var(--muted); font-size: 12px; }
    .spinner { width: 10px; height: 10px; border-radius: 50%; background: var(--accent); box-shadow: 0 0 0 0 rgba(138,180,255,.55); animation: pulse 1.35s ease-in-out infinite; }
    .spinner.is-waiting { background: var(--warn); box-shadow: 0 0 0 0 rgba(240,193,90,.55); }
    .spinner.is-hidden { display: none; }
    @keyframes pulse { 0% { transform: scale(.82); box-shadow: 0 0 0 0 rgba(138,180,255,.45); } 70% { transform: scale(1); box-shadow: 0 0 0 7px rgba(138,180,255,0); } 100% { transform: scale(.82); box-shadow: 0 0 0 0 rgba(138,180,255,0); } }
    .content { display: flex; flex-direction: column; gap: 12px; min-width: 0; min-height: 0; height: 100%; overflow-y: auto; overflow-x: hidden; scrollbar-gutter: stable; padding-right: 4px; align-content: start; }
    .summary { padding: 13px 14px; display: grid; gap: 8px; }
    .summary-grid { display: grid; grid-template-columns: repeat(5, minmax(120px, 1fr)); gap: 10px; }
    .summary-grid div { min-width: 0; }
    .label { color: var(--muted); font-size: 12px; margin-bottom: 3px; }
    .value { font: 13px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; overflow-wrap: anywhere; }
    .terminal-wrap { overflow: hidden; background: var(--term); border-color: #252b33; min-height: clamp(260px, 36vh, 520px); max-height: clamp(320px, 44vh, 620px); display: flex; flex: 0 0 auto; flex-direction: column; }
    .terminal-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 9px 10px; border-bottom: 1px solid #252b33; background: #0d1117; }
    .terminal-title { font: 12px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; color: var(--muted); }
    .actions { display: flex; flex-wrap: wrap; gap: 7px; }
    button { border: 1px solid #3d4652; background: #202833; color: var(--text); border-radius: 6px; padding: 7px 10px; cursor: pointer; font: 13px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    button:hover { background: #293241; }
    button:disabled { cursor: not-allowed; opacity: .48; }
    button.danger { border-color: #6b2b32; background: #2b1518; color: #ffb3ad; }
    button.danger:hover { background: #3a1b20; }
    .terminal { flex: 1 1 auto; min-height: 0; height: auto; overflow: auto; padding: 13px 14px 20px; font: 13px/1.45 ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace; white-space: pre-wrap; overflow-wrap: anywhere; color: #d6deeb; }
    .dim { opacity: .66; } .bold { font-weight: 700; } .italic { font-style: italic; }
    .fg-black { color: #484f58; } .fg-red { color: #ff7b72; } .fg-green { color: #7ee787; } .fg-yellow { color: #f2cc60; } .fg-blue { color: #79c0ff; } .fg-magenta { color: #d2a8ff; } .fg-cyan { color: #76e3ea; } .fg-white { color: #e6edf3; }
    .fg-bright-black { color: #8b949e; } .fg-bright-red { color: #ffa198; } .fg-bright-green { color: #aff5b4; } .fg-bright-yellow { color: #f8e3a1; } .fg-bright-blue { color: #a5d6ff; } .fg-bright-magenta { color: #e2c5ff; } .fg-bright-cyan { color: #b3f0ff; } .fg-bright-white { color: #ffffff; }
    .details { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); grid-auto-rows: max-content; gap: 12px; min-width: 0; min-height: 0; align-items: start; overflow: visible; padding-bottom: 18px; flex: 0 0 auto; }
    .details .panel { padding: 12px; min-width: 0; min-height: 0; max-width: 100%; overflow: hidden; display: flex; flex-direction: column; gap: 8px; position: relative; }
    h2 { margin: 0 0 8px; font-size: 15px; }
    ul { margin: 0; padding-left: 18px; min-width: 0; }
    pre { margin: 0; flex: 1 1 auto; min-height: 0; max-height: min(34vh, 360px); overflow-y: auto; overflow-x: hidden; white-space: pre-wrap; overflow-wrap: anywhere; word-break: break-word; font: 12px/1.4 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; color: #c9d1d9; }
    #promptPanel, #resultPanel, #curatorCodexPanel { min-height: 0; height: clamp(220px, 32vh, 360px); overflow-y: auto; overflow-x: hidden; }
    #timelineList { list-style: none; padding: 0; display: grid; align-content: start; gap: 8px; height: clamp(220px, 32vh, 360px); overflow-y: auto; overflow-x: hidden; min-width: 0; }
    #timelineList li { border: 1px solid var(--line-soft); border-radius: 6px; padding: 8px; min-width: 0; overflow-wrap: anywhere; word-break: break-word; }
    #timelineList .dim { display: block; white-space: pre-wrap; overflow-wrap: anywhere; word-break: break-word; }
    .empty { padding: 20px; color: var(--muted); }
    @media (max-width: 980px) { .app-frame { height: auto; min-height: 100vh; overflow: visible; grid-template-columns: 1fr; } .sidebar { position: static; } .live-main { grid-template-columns: 1fr; height: auto; overflow: visible; } .runs-panel { min-height: 60vh; } .summary-grid, .details { grid-template-columns: 1fr; } .terminal { height: 55vh; } }
  </style>
</head>
<body>
  <div class="app-frame">
    <aside class="sidebar">
      <div class="brand">
        <strong>DevControl</strong>
        <span>Hosted control plane</span>
      </div>
      <nav class="side-nav" aria-label="DevControl navigation">
        <a class="side-link active" href="/runs/live">Мониторинг</a>
        <a class="side-link" href="/">Панель</a>
        <a class="side-link" href="/#connection">Подключение</a>
        <a class="side-link" href="/#technical">Технические детали</a>
      </nav>
    </aside>
    <div class="workspace">
      <header class="topbar">
        <div>
          <h1>Мониторинг</h1>
          <div class="subtitle">Read-only terminal-like монитор активных и недавних run_id.</div>
        </div>
        <div class="meta"><span class="pill" id="connectionState">polling</span><span class="pill">read-only</span></div>
      </header>
      <main class="live-main">
        <aside class="runs-panel">
          <div class="selection-bar">
            <div class="selection-actions">
              <button type="button" id="mergeDeployButton" onclick="promoteSelected()" disabled>Merge & Deploy</button>
              <button type="button" id="clearSelectionButton" onclick="clearPromotionSelection()" disabled>Сбросить</button>
            </div>
            <div class="selection-hint" id="selectionHint">Выберите задачи со статусом «Готово к выкладке».</div>
          </div>
          <div id="runList" class="run-list"><div class="empty">No active runs.</div></div>
        </aside>
        <div class="content">
      <section class="summary">
        <div class="summary-grid">
          <div><div class="label">run_id</div><div class="value" id="summaryRunId">none</div></div>
          <div><div class="label">Статус</div><div class="value" id="summaryStatus">idle</div></div>
          <div><div class="label">Этап</div><div class="value" id="summaryStage">none</div></div>
          <div><div class="label">target_id</div><div class="value" id="summaryTarget">none</div></div>
          <div><div class="label">mode</div><div class="value" id="summaryMode">none</div></div>
          <div><div class="label">Время</div><div class="value" id="summaryTime">none</div></div>
          <div><div class="label">Changed files</div><div class="value" id="summaryChanges">0</div></div>
        </div>
        <div class="running-line" id="runningIndicator"><span class="spinner is-hidden" id="runningSpinner"></span><span id="runningText">Нет активного этапа.</span><span id="runningElapsed"></span><span id="runningLastActivity"></span></div>
        <div class="value status-bad" id="summaryBlocker"></div>
      </section>
      <section class="terminal-wrap">
        <div class="terminal-toolbar">
          <div class="terminal-title" id="terminalTitle">terminal</div>
          <div class="actions">
            <button type="button" onclick="toggleAutoscroll()" id="autoscrollButton">Пауза autoscroll</button>
            <button type="button" onclick="jumpLatest()">К последнему</button>
            <button type="button" onclick="copyVisibleLog()">Копировать видимый sanitized log</button>
            <button type="button" onclick="clearLocalView()">Очистить локально</button>
            <button class="danger" type="button" onclick="cancelSelectedRun()">Остановить</button>
            <button type="button" onclick="markSelectedStale()">Пометить stale/blocked</button>
            <button type="button" onclick="refreshSelectedCandidate()" title="Нужен refresh · Конфликт после выкладки">Пересобрать</button>
          </div>
        </div>
        <div id="terminal" class="terminal" aria-live="polite"></div>
      </section>
      <div class="details">
        <section class="panel">
          <h2>Промпт</h2>
          <div class="actions"><button type="button" onclick="copyPrompt()">Копировать prompt</button></div>
          <pre id="promptPanel">Промпт отсутствует.</pre>
        </section>
        <section class="panel">
          <h2>Timeline</h2>
          <ul id="timelineList"></ul>
        </section>
        <section class="panel">
          <h2>Артефакты</h2>
          <pre id="resultPanel">No run selected.</pre>
        </section>
        <section class="panel">
          <h2>Куратор ↔ Codex</h2>
          <pre id="curatorCodexPanel">No sprint run selected.</pre>
        </section>
      </div>
    </div>
      </main>
    </div>
  </div>
  <script>
    const initialRunId = __SELECTED_RUN_ID__;
    const colorNames = ['black','red','green','yellow','blue','magenta','cyan','white'];
    const activeRunStatuses = new Set(['queued','submitted','preparing','managed_run_running','running','running_codex','running_production_lane','auto_promoting_first','promotion_running','production_lane_running','waiting_for_target_lock','control_error_codex_running']);
    const terminalStatuses = new Set(['blocked','blocked_by_conflict','blocked_by_operator','cancelled','completed','completed_dry_run','conflict_detected','decision_only','denied','expired','failed','needs_rework','needs_verifier_after_control_error','partially_deployed','partial_group_blocked','partial_group_complete_with_blockers','passed','production_complete','ready_for_separate_deploy','refresh_required','selected_production_bridge_blocked','stale_lost_process','stale_timeout']);
    let selectedRunId = initialRunId || null;
    let userSelectedRun = Boolean(initialRunId);
    let autoscroll = true;
    let selectedPromotionIds = new Set();
    let runsById = new Map();
    let terminalStates = new Map();
    let runSource = null;
    let listPollTimer = null;
    let detailPollTimer = null;
    let knownLifecycleByRun = new Map();
    let notificationCount = 0;
    let notificationBlinkTimer = null;
    let notificationBlinkOn = false;
    let notificationSoundEnabled = false;

    function escapeHtml(value) {
      return String(value || '').replace(/[&<>"']/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;', "'": '&#39;'}[char]));
    }

    async function requestJson(path, options = {}) {
      const response = await fetch(path, {cache: 'no-store', ...options});
      if (!response.ok) throw new Error(`${response.status} ${path}`);
      return response.json();
    }

    async function refreshRuns() {
      const payload = await requestJson('/api/runs/live');
      const runs = payload.runs || [];
      observeRunStatusChanges(runs);
      renderRunList(runs);
      const nextSelected = chooseSelectedRun(runs);
      if (nextSelected && nextSelected !== selectedRunId) selectRun(nextSelected, {user: false});
      scheduleListRefresh(runs.some((run) => run.active) ? 1800 : 7000);
    }

    function observeRunStatusChanges(runs) {
      const next = new Map();
      for (const run of runs) {
        const id = run.run_id || '';
        if (!id) continue;
        const key = lifecycleKey(run);
        const previous = knownLifecycleByRun.get(id);
        next.set(id, key);
        if (previous && previous !== key && isImportantLifecycleChange(previous, key)) {
          addStatusNotification(run);
        }
      }
      knownLifecycleByRun = next;
    }

    function lifecycleKey(run) {
      return [
        run.operator_lifecycle_status || '',
        run.effective_status || run.status || '',
        run.current_stage || '',
        run.deploy_status || '',
        run.probe_status || '',
        run.blocker ? 'blocker' : ''
      ].join('|');
    }

    function isImportantLifecycleChange(previous, current) {
      const important = ['ready_for_promotion', 'production_complete', 'blocked', 'failed', 'promotion_running', 'deploy_passed', 'post_deploy_passed'];
      return important.some((token) => current.includes(token) && !previous.includes(token));
    }

    function addStatusNotification(run) {
      notificationCount += 1;
      startNotificationBlink();
      playNotificationSound();
    }

    function startNotificationBlink() {
      if (notificationBlinkTimer) return;
      notificationBlinkTimer = setInterval(() => {
        notificationBlinkOn = !notificationBlinkOn;
        document.title = notificationBlinkOn && notificationCount > 0
          ? `🔔 ${notificationCount} ${notificationWord(notificationCount)} · Мониторинг`
          : 'Мониторинг';
      }, 900);
    }

    function notificationWord(count) {
      const mod10 = count % 10;
      const mod100 = count % 100;
      if (mod10 === 1 && mod100 !== 11) return 'уведомление';
      if ([2, 3, 4].includes(mod10) && ![12, 13, 14].includes(mod100)) return 'уведомления';
      return 'уведомлений';
    }

    function acknowledgeNotifications() {
      notificationCount = 0;
      document.title = 'Мониторинг';
      if (notificationBlinkTimer) clearInterval(notificationBlinkTimer);
      notificationBlinkTimer = null;
      notificationBlinkOn = false;
    }

    function playNotificationSound() {
      if (!notificationSoundEnabled || !window.AudioContext) return;
      try {
        const context = new AudioContext();
        const oscillator = context.createOscillator();
        const gain = context.createGain();
        oscillator.frequency.value = 880;
        gain.gain.value = 0.025;
        oscillator.connect(gain);
        gain.connect(context.destination);
        oscillator.start();
        oscillator.stop(context.currentTime + 0.08);
      } catch (_) {}
    }

    function chooseSelectedRun(runs) {
      const ids = new Set(runs.map((run) => run.run_id));
      if (selectedRunId && ids.has(selectedRunId)) return selectedRunId;
      userSelectedRun = false;
      const active = runs.find((run) => run.active);
      return (active || runs[0] || {}).run_id || null;
    }

    function renderRunList(runs) {
      const root = document.getElementById('runList');
      if (!runs.length) {
        runsById.clear();
        root.replaceChildren(emptyNode('No active or recent runs.'));
        return;
      }
      for (const empty of Array.from(root.querySelectorAll('.empty'))) empty.remove();
      const seen = new Set();
      for (const run of runs) {
        seen.add(run.run_id);
        runsById.set(run.run_id, run);
        let row = root.querySelector(`[data-run-id="${cssEscape(run.run_id)}"]`);
        if (!row) {
          row = createRunRow(run.run_id);
        }
        updateRunRow(row, run);
        root.appendChild(row);
      }
      for (const row of Array.from(root.querySelectorAll('.run-item'))) {
        if (!seen.has(row.dataset.runId)) {
          selectedPromotionIds.delete(row.dataset.runId);
          row.remove();
        }
      }
      updateSelectedRunClasses();
      updateSelectionControls();
    }

    function createRunRow(runId) {
      const button = document.createElement('div');
      button.className = 'run-item';
      button.setAttribute('role', 'button');
      button.tabIndex = 0;
      button.dataset.runId = runId;
      button.addEventListener('click', () => selectRun(runId, {user: true}));
      button.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          selectRun(runId, {user: true});
        }
      });
      button.innerHTML = '<label class="run-selector"><input type="checkbox" data-role="promote-select"><span><span class="task-title"></span><span class="run-id"></span></span></label><span class="meta run-status-line"><span class="row-spinner is-hidden"></span><span class="pill"></span><span data-field="stage"></span></span><span class="meta"><span data-field="target"></span><span data-field="mode"></span></span><span class="meta"><span data-field="time"></span><span data-field="changes"></span></span><span class="meta status-bad" data-field="blocker"></span>';
      const checkbox = button.querySelector('[data-role="promote-select"]');
      checkbox.addEventListener('click', (event) => event.stopPropagation());
      checkbox.addEventListener('change', () => togglePromotionSelection(runId, checkbox.checked));
      return button;
    }

    function updateRunRow(row, run) {
      updateText(row.querySelector('.task-title'), run.task_title || shortRunTitle(run));
      updateText(row.querySelector('.run-id'), run.run_id || '');
      const status = row.querySelector('.pill');
      const displayStatus = run.display_status || run.effective_status || run.status || 'unknown';
      const lifecycleLabel = run.operator_lifecycle_label || run.operator_label || displayStatus;
      updateText(status, lifecycleLabel);
      status.className = `pill ${statusClass(displayStatus)} ${badgeClass(run)}`;
      status.title = displayStatus;
      const rowSpinner = row.querySelector('.row-spinner');
      const running = isRunActuallyRunning(run);
      rowSpinner.classList.toggle('is-hidden', !running);
      rowSpinner.classList.toggle('is-waiting', String(displayStatus).includes('waiting') || String(run.operator_label || '').includes('ожид'));
      updateText(row.querySelector('[data-field="stage"]'), run.current_stage || '');
      updateText(row.querySelector('[data-field="target"]'), run.target || run.target_id || '');
      updateText(row.querySelector('[data-field="mode"]'), `${run.run_type || 'run'} · ${run.execution_mode || ''}`);
      updateText(row.querySelector('[data-field="time"]'), run.operator_time_summary || '');
      const changed = Array.isArray(run.changed_files) ? run.changed_files.length : 0;
      updateText(row.querySelector('[data-field="changes"]'), changed ? `${changed} files` : '');
      updateText(row.querySelector('[data-field="blocker"]'), run.blocker || '');
      const checkbox = row.querySelector('[data-role="promote-select"]');
      const selectable = Boolean(run.promotion_selectable);
      checkbox.disabled = !selectable;
      checkbox.title = selectable ? 'Выбрать для Merge & Deploy' : (run.promotion_selection_reason || 'Недоступно для Merge & Deploy');
      checkbox.checked = selectedPromotionIds.has(run.run_id || '');
      if (!selectable) selectedPromotionIds.delete(run.run_id || '');
    }

    function updateSelectedRunClasses() {
      for (const row of document.querySelectorAll('.run-item')) {
        row.classList.toggle('active', row.dataset.runId === selectedRunId);
      }
    }

    function selectRun(runId, options = {}) {
      if (!runId) return;
      const changed = selectedRunId !== runId;
      selectedRunId = runId;
      userSelectedRun = Boolean(options.user);
      if (changed) {
        closeStream();
        renderCachedTerminal();
      }
      updateSelectedRunClasses();
      scheduleRunRefresh(0);
      if (!isSelectedTerminal()) openStream();
    }

    async function loadRunFull() {
      if (!selectedRunId) return;
      const state = stateForRun(selectedRunId);
      const payload = await requestJson(`/api/runs/${encodeURIComponent(selectedRunId)}/live`);
      const tail = payload.log_tail || {};
      if (!state.loaded) {
        state.ansi = '';
        state.plain = '';
        state.offset = 0;
        clearTerminal();
        appendTerminalDelta(tail.ansi_text || '', tail.plain_text || '', tail.next_offset ?? tail.bytes ?? 0);
        state.loaded = true;
      }
      renderRunDetail(payload);
      const run = payload.run || {};
      if (isRunTerminal(run)) finalizeSelectedRun();
    }

    async function loadRunDelta() {
      if (!selectedRunId) return;
      const state = stateForRun(selectedRunId);
      const runId = selectedRunId;
      if (!state.loaded) {
        await loadRunFull();
        return;
      }
      const [live, timeline, tail] = await Promise.all([
        requestJson('/api/runs/live'),
        requestJson(`/api/runs/${encodeURIComponent(runId)}/timeline?cursor=${encodeURIComponent(state.timelineCursor || '')}`),
        requestJson(`/api/runs/${encodeURIComponent(runId)}/log-tail?offset=${encodeURIComponent(state.offset || 0)}&max_bytes=64000`)
      ]);
      if (runId !== selectedRunId) return;
      const run = (live.runs || []).find((item) => item.run_id === runId) || runsById.get(runId) || {};
      for (const event of timeline.events || []) state.timeline.push(event);
      state.timeline = dedupeTimeline(state.timeline).slice(-120);
      state.timelineCursor = timeline.next_cursor || state.timelineCursor;
      if (tail.status === 'ok') appendTerminalDelta(tail.ansi_text || '', tail.plain_text || '', tail.next_offset ?? state.offset);
      renderRunDetail({status: 'ok', run, timeline: state.timeline, log_tail: tail, changed_files: run.changed_files || [], verifier: null, report: state.report, handoff: state.handoff});
      if (isRunTerminal(run)) {
        const finalDetail = await requestJson(`/api/runs/${encodeURIComponent(runId)}/live`);
        if (runId === selectedRunId) {
          state.handoff = finalDetail.handoff || state.handoff;
          state.report = finalDetail.report || state.report;
          renderRunDetail({...finalDetail, timeline: state.timeline});
          finalizeSelectedRun();
        }
      }
    }

    function finalizeSelectedRun() {
      const state = stateForRun(selectedRunId);
      state.runTerminalFinalized = true;
      closeStream();
      scheduleRunRefresh(12000);
    }

    function scheduleRunRefresh(delay) {
      if (detailPollTimer) clearTimeout(detailPollTimer);
      detailPollTimer = setTimeout(() => {
        const state = selectedRunId ? stateForRun(selectedRunId) : null;
        if (!selectedRunId) return;
        loadRunDelta().catch(() => {});
        if (!state || !state.runTerminalFinalized) scheduleRunRefresh(1600);
      }, delay);
    }

    function scheduleListRefresh(delay) {
      if (listPollTimer) clearTimeout(listPollTimer);
      listPollTimer = setTimeout(() => refreshRuns().catch(() => scheduleListRefresh(5000)), delay);
    }

    function renderRunDetail(payload) {
      const run = payload.run || {};
      document.getElementById('summaryRunId').textContent = run.run_id || selectedRunId || 'none';
      const displayStatus = run.display_status || run.effective_status || run.status || 'unknown';
      document.getElementById('summaryStatus').textContent = run.operator_label ? `${displayStatus} · ${run.operator_label}` : displayStatus;
      document.getElementById('summaryStatus').className = `value ${statusClass(displayStatus)}`;
      document.getElementById('summaryStage').textContent = run.current_stage || 'none';
      document.getElementById('summaryTarget').textContent = run.target || run.target_id || 'none';
      document.getElementById('summaryMode').textContent = run.execution_mode || 'none';
      document.getElementById('summaryTime').textContent = run.operator_time_summary || 'none';
      const changed = run.changed_files || payload.changed_files || [];
      document.getElementById('summaryChanges').textContent = Array.isArray(changed) ? String(changed.length) : '0';
      document.getElementById('summaryBlocker').textContent = run.blocker || '';
      document.getElementById('terminalTitle').textContent = run.run_id || 'terminal';
      renderRunningIndicator(run, payload);
      renderPrompt(payload);
      renderTimeline(payload.timeline || []);
      renderResult(payload);
      renderCuratorCodex(payload);
    }

    function renderRunningIndicator(run, payload) {
      const spinner = document.getElementById('runningSpinner');
      const text = document.getElementById('runningText');
      const elapsed = document.getElementById('runningElapsed');
      const last = document.getElementById('runningLastActivity');
      const active = isRunActuallyRunning(run);
      spinner.classList.toggle('is-hidden', !active);
      spinner.classList.toggle('is-waiting', String(run.effective_status || run.status || '').includes('waiting') || String(run.operator_label || '').includes('ожид'));
      const stage = run.current_stage || run.effective_status || run.status || 'unknown';
      text.textContent = active ? (stage === 'running_codex' ? 'Codex работает' : `выполняется: ${stage}`) : 'Финальный статус зафиксирован.';
      const seconds = run.codex_elapsed_seconds ?? payload.stale_assessment?.elapsed_seconds;
      elapsed.textContent = seconds !== undefined && seconds !== null ? `elapsed ${seconds}s` : '';
      const activity = run.last_activity_at || payload.codex_process?.last_output_at || payload.codex_process?.last_event_at || '';
      last.textContent = activity ? `Последняя активность: ${activity}` : '';
    }

    function renderPrompt(payload) {
      const state = stateForRun(selectedRunId);
      const hasPrompt = Object.prototype.hasOwnProperty.call(payload, 'prompt') && typeof payload.prompt === 'string' && payload.prompt.length > 0;
      if (!hasPrompt && state.promptLoaded) return;
      const decoded = hasPrompt ? decodeEscapedText(payload.prompt) : 'Промпт отсутствует.';
      if (state.lastPromptText === decoded) return;
      state.lastPromptText = decoded;
      if (hasPrompt) state.promptLoaded = true;
      document.getElementById('promptPanel').textContent = decoded;
    }

    function renderTimeline(events) {
      const root = document.getElementById('timelineList');
      if (!events.length) {
        root.innerHTML = '<li class="dim">No events yet.</li>';
        return;
      }
      root.innerHTML = events.slice(-80).map((event) => `<li><span class="${statusClass(event.status || event.level)}">${escapeHtml(event.title || event.stage || '')}</span><br><span class="dim">${escapeHtml(event.timestamp || '')} ${escapeHtml(event.detail || '')}</span></li>`).join('');
    }

    function renderResult(payload) {
      const run = payload.run || {};
      const lines = [];
      lines.push(`status: ${run.status || 'unknown'}`);
      if (run.effective_status && run.effective_status !== run.status) lines.push(`effective_status: ${run.effective_status}`);
      if (run.is_inconsistent) lines.push('inconsistent: true');
      if (run.operator_label) lines.push(`operator_label: ${run.operator_label}`);
      if (run.control_plane_observer_status) lines.push(`control_plane_observer: ${run.control_plane_observer_status}`);
      if (run.control_plane_observer_blocker) lines.push(`control_plane_observer_blocker: ${run.control_plane_observer_blocker}`);
      lines.push(`verifier: ${run.verifier_status || 'n/a'}`);
      if (run.artifact_status?.handoff && !run.artifact_status?.verifier) lines.push('handoff_present_verifier_missing_due_to_control_error: true');
      if (run.pr_url) lines.push(`PR: ${run.pr_url}`);
      if (run.merge_commit) lines.push(`merge: ${run.merge_commit}`);
      if (run.deploy_status) lines.push(`deploy: ${run.deploy_status}`);
      if (run.probe_status) lines.push(`probe: ${run.probe_status}`);
      const group = payload.report?.promotion_group;
      if (group) {
        lines.push(`group_id: ${group.group_id || group.run_id || 'n/a'}`);
        lines.push(`selected_ids: ${(group.selected_ids || []).join(', ') || 'none'}`);
        lines.push(`planned_order: ${(group.planned_order || []).join(', ') || 'none'}`);
        if ((group.accepted_task_ids || []).length) lines.push(`accepted_task_ids: ${(group.accepted_task_ids || []).join(', ')}`);
        if ((group.deferred_task_ids || []).length) lines.push(`deferred_task_ids: ${(group.deferred_task_ids || []).join(', ')}`);
        if ((group.conflicted_ids || []).length) lines.push(`conflicted_ids: ${(group.conflicted_ids || []).join(', ')}`);
        if ((group.conflict_files || []).length) lines.push(`conflict_files: ${(group.conflict_files || []).join(', ')}`);
        if ((group.refresh_required_ids || []).length) lines.push(`refresh_required_ids: ${(group.refresh_required_ids || []).join(', ')}`);
        if (group.recommended_action) lines.push(`next: ${group.recommended_action}`);
        if (group.blocker) lines.push(`group_blocker: ${group.blocker}`);
      }
      if (run.recommended_action) lines.push(`next: ${run.recommended_action}`);
      if ((run.conflict_files || []).length) lines.push(`conflict_files: ${(run.conflict_files || []).join(', ')}`);
      const changed = run.changed_files || payload.changed_files || [];
      lines.push('');
      lines.push('changed files:');
      lines.push(...(changed.length ? changed.map((item) => `  - ${item}`) : ['  n/a']));
      const handoff = payload.handoff || stateForRun(selectedRunId).handoff || '';
      if (handoff) {
        lines.push('');
        lines.push('handoff:');
        lines.push(decodeEscapedText(handoff));
      }
      document.getElementById('resultPanel').textContent = lines.join('\\n');
    }

    function renderCuratorCodex(payload) {
      const sprint = payload.sprint || payload.report?.sprint || null;
      const root = document.getElementById('curatorCodexPanel');
      if (!root) return;
      if (!sprint) {
        root.textContent = 'Нет sprint exchange для выбранного run_id.';
        return;
      }
      const lines = [];
      lines.push(`status: ${sprint.status || 'unknown'}`);
      lines.push(`target_id: ${sprint.target_id || 'n/a'}`);
      lines.push(`execution_mode: ${sprint.execution_mode || 'managed_clone_only'}`);
      lines.push(`child_run_ids: ${(sprint.child_run_ids || []).join(', ') || 'none'}`);
      lines.push(`verifier: ${sprint.verifier_status || 'n/a'}`);
      if (sprint.blocker) lines.push(`blocker: ${sprint.blocker}`);
      lines.push('');
      lines.push('curator decisions:');
      for (const decision of sprint.curator_decisions || []) {
        lines.push(`- ${decision.phase || 'phase'} / ${decision.decision || 'decision'} / step ${decision.step_index || ''}`);
        if (decision.child_run_id) lines.push(`  child: ${decision.child_run_id}`);
        if (decision.reason) lines.push(`  reason: ${decision.reason}`);
        if (decision.verifier_status) lines.push(`  verifier: ${decision.verifier_status}`);
        if (decision.handoff_summary) lines.push(`  handoff: ${decodeEscapedText(decision.handoff_summary)}`);
        if (decision.blocker) lines.push(`  blocker: ${decision.blocker}`);
      }
      root.textContent = lines.join('\\n');
    }

    function appendTerminalDelta(ansi, plain, nextOffset) {
      if (!selectedRunId) return;
      const state = stateForRun(selectedRunId);
      const deltaAnsi = decodeEscapedText(String(ansi || ''));
      const deltaPlain = decodeEscapedText(String(plain || ''));
      if (!deltaAnsi && Number(nextOffset || 0) <= state.offset) return;
      const terminal = document.getElementById('terminal');
      if (terminal.dataset.placeholder === 'true') clearTerminal();
      const shouldScroll = autoscroll && isNearBottom(terminal);
      if (deltaAnsi) {
        terminal.insertAdjacentHTML('beforeend', ansiToHtml(applyCarriageReturns(deltaAnsi)));
        state.ansi += deltaAnsi;
        state.plain += deltaPlain || stripSgr(deltaAnsi);
      }
      state.offset = Math.max(state.offset, Number(nextOffset || state.offset || 0));
      if (shouldScroll) terminal.scrollTop = terminal.scrollHeight;
    }

    function renderCachedTerminal() {
      const terminal = document.getElementById('terminal');
      clearTerminal();
      const state = stateForRun(selectedRunId);
      if (state.ansi) {
        terminal.insertAdjacentHTML('beforeend', ansiToHtml(applyCarriageReturns(state.ansi)));
        terminal.scrollTop = terminal.scrollHeight;
      } else {
        setTerminalPlaceholder();
      }
    }

    function clearTerminal() {
      const terminal = document.getElementById('terminal');
      terminal.replaceChildren();
      terminal.dataset.placeholder = 'false';
    }

    function setTerminalPlaceholder() {
      const terminal = document.getElementById('terminal');
      terminal.innerHTML = '<span class="dim">No terminal output yet.</span>';
      terminal.dataset.placeholder = 'true';
    }

    function isNearBottom(element) {
      return element.scrollHeight - element.scrollTop - element.clientHeight < 48;
    }

    function applyCarriageReturns(text) {
      return String(text || '').split('\\n').map((line) => {
        if (!line.includes('\\r')) return line;
        let current = '';
        for (const part of line.split('\\r')) current = part.length >= current.length ? part : part + current.slice(part.length);
        return current;
      }).join('\\n');
    }

    function ansiToHtml(text) {
      let html = '';
      let classes = new Set();
      const stack = () => Array.from(classes).join(' ');
      const open = () => stack() ? `<span class="${stack()}">` : '';
      const close = () => stack() ? '</span>' : '';
      let openSpan = false;
      for (let i = 0; i < text.length; i++) {
        if (text[i] === '\\x1b' && text[i + 1] === '[') {
          const end = text.indexOf('m', i + 2);
          if (end !== -1 && end - i < 90) {
            if (openSpan) { html += close(); openSpan = false; }
            applySgr(text.slice(i + 2, end), classes);
            if (stack()) { html += open(); openSpan = true; }
            i = end;
            continue;
          }
        }
        html += escapeHtml(text[i]);
      }
      if (openSpan) html += close();
      return html || '<span class="dim">No terminal output yet.</span>';
    }

    function applySgr(params, classes) {
      const codes = (params || '0').split(';').filter(Boolean).map((value) => Number(value));
      if (!codes.length) codes.push(0);
      for (const code of codes) {
        if (code === 0) classes.clear();
        else if (code === 1) classes.add('bold');
        else if (code === 2) classes.add('dim');
        else if (code === 3) classes.add('italic');
        else if (code === 22) { classes.delete('bold'); classes.delete('dim'); }
        else if (code === 23) classes.delete('italic');
        else if (code === 39) removePrefix(classes, 'fg-');
        else if (30 <= code && code <= 37) { removePrefix(classes, 'fg-'); classes.add(`fg-${colorNames[code - 30]}`); }
        else if (90 <= code && code <= 97) { removePrefix(classes, 'fg-'); classes.add(`fg-bright-${colorNames[code - 90]}`); }
      }
    }

    function removePrefix(classes, prefix) {
      for (const item of Array.from(classes)) if (item.startsWith(prefix)) classes.delete(item);
    }

    function statusClass(status) {
      const value = String(status || '');
      if (['completed','production_complete','deploy_passed','post_deploy_passed','success'].includes(value)) return 'status-ok';
      if (['passed','verifier_passed','promotion_queued'].includes(value)) return 'status-warn';
      if (['failed','blocked','blocked_by_conflict','blocked_by_operator','cancelled','expired','error','selected_production_bridge_blocked'].includes(value)) return 'status-bad';
      if (['conflict_detected','needs_rework','partially_deployed','partial_group_blocked','partial_group_complete_with_blockers','ready_for_separate_deploy','refresh_required'].includes(value)) return 'status-warn';
      if (['waiting_for_target_lock','warning','stale_lost_process','stale_timeout','needs_verifier_after_control_error','control_error_codex_running'].includes(value)) return 'status-warn';
      return '';
    }

    function badgeClass(run) {
      const tone = run.operator_lifecycle_tone || run.operator_lifecycle?.tone || '';
      if (tone === 'ok') return 'status-ok';
      if (tone === 'ready') return 'status-ready';
      if (tone === 'refresh') return 'status-refresh';
      if (tone === 'running') return 'status-running';
      if (tone === 'bad') return 'status-failed';
      const value = String(run.display_status || run.effective_status || run.status || '');
      if (run.effective_activity === 'running' || value === 'control_error_codex_running' || ['queued','preparing','running_codex','running_production_lane'].includes(value)) return 'status-running';
      if (['stale_lost_process','stale_timeout'].includes(value) || run.effective_activity === 'stale') return 'status-stale';
      if (['needs_verifier_after_control_error','control_error_codex_running'].includes(value) || run.control_plane_observer_status === 'error') return 'status-control';
      if (['conflict_detected','needs_rework','refresh_required'].includes(value)) return 'status-refresh';
      if (['failed','blocked','blocked_by_conflict','blocked_by_operator','cancelled','expired','error','selected_production_bridge_blocked'].includes(value)) return 'status-failed';
      if (['partially_deployed','partial_group_blocked','partial_group_complete_with_blockers','passed','verifier_passed','promotion_queued','ready_for_separate_deploy'].includes(value)) return 'status-ready';
      if (['completed','production_complete','deploy_passed','post_deploy_passed','success'].includes(value)) return 'status-ok';
      return '';
    }

    function isRunTerminal(run) {
      if (!run) return false;
      const values = [
        run.effective_status,
        run.status,
        run.current_stage,
        run.operator_lifecycle_status
      ].map((item) => String(item || ''));
      if (values.some((value) => terminalStatuses.has(value))) return true;
      if (run.effective_activity === 'running') return false;
      return run.active === false;
    }

    function isRunActuallyRunning(run) {
      if (!run) return false;
      const values = [
        run.effective_status,
        run.status,
        run.current_stage,
        run.operator_lifecycle_status,
        run.deploy_status,
        run.public_verify_status
      ].map((item) => String(item || ''));
      if (values.some((value) => terminalStatuses.has(value))) return false;
      if (run.effective_activity && run.effective_activity !== 'running') return false;
      if (run.effective_activity === 'running') return true;
      return Boolean(run.active) && values.some((value) => activeRunStatuses.has(value));
    }

    function togglePromotionSelection(runId, checked) {
      if (!runId) return;
      if (checked) selectedPromotionIds.add(runId);
      else selectedPromotionIds.delete(runId);
      updateSelectionControls();
    }

    function clearPromotionSelection() {
      selectedPromotionIds.clear();
      for (const checkbox of document.querySelectorAll('[data-role="promote-select"]')) checkbox.checked = false;
      updateSelectionControls();
    }

    function updateSelectionControls() {
      const selected = Array.from(selectedPromotionIds).filter((runId) => runsById.has(runId));
      selectedPromotionIds = new Set(selected);
      const button = document.getElementById('mergeDeployButton');
      const clear = document.getElementById('clearSelectionButton');
      const hint = document.getElementById('selectionHint');
      if (!button || !hint) return;
      button.disabled = selected.length === 0;
      if (clear) clear.disabled = selected.length === 0;
      if (!selected.length) {
        hint.textContent = 'Выберите задачи со статусом «Готово к выкладке».';
        return;
      }
      const targets = Array.from(new Set(selected.map((runId) => (runsById.get(runId) || {}).target_id || (runsById.get(runId) || {}).target).filter(Boolean)));
      button.disabled = targets.length !== 1;
      hint.textContent = targets.length === 1
        ? `${selected.length} выбрано · target_id ${targets[0]}`
        : 'Выбранные задачи относятся к разным target_id; выберите один target.';
    }

    async function promoteSelected() {
      const selected = Array.from(selectedPromotionIds).filter((runId) => runsById.has(runId));
      const hint = document.getElementById('selectionHint');
      if (!selected.length) return;
      const targets = Array.from(new Set(selected.map((runId) => (runsById.get(runId) || {}).target_id || (runsById.get(runId) || {}).target).filter(Boolean)));
      if (targets.length !== 1) {
        hint.textContent = 'Merge & Deploy требует один target_id.';
        return;
      }
      hint.textContent = 'Планирование Merge & Deploy...';
      try {
        const result = await requestJson('/api/parallel-selection/promote', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            target_id: targets[0],
            selected_ids: selected,
            selection_type: 'auto',
            mode: 'auto_order',
            confirm_merge_deploy: true,
            allow_auto_first_promotion: true,
            allow_real_production_promotion: true,
            allow_refresh: true,
            idempotency_key: `ui-selected-${Date.now()}`
          })
        });
        hint.textContent = result.group_id
          ? `Group promotion ${result.group_id}: ${result.status || 'ok'}`
          : `Single promotion: ${result.status || 'ok'}`;
        await refreshRuns();
        if (result.group_id) selectRun(result.group_id, {user: true});
      } catch (error) {
        hint.textContent = String(error);
      }
    }

    function toggleAutoscroll() {
      autoscroll = !autoscroll;
      document.getElementById('autoscrollButton').textContent = autoscroll ? 'Пауза autoscroll' : 'Продолжить autoscroll';
    }
    function jumpLatest() {
      const terminal = document.getElementById('terminal');
      terminal.scrollTop = terminal.scrollHeight;
      autoscroll = true;
      document.getElementById('autoscrollButton').textContent = 'Пауза autoscroll';
    }
    async function copyVisibleLog() {
      const state = stateForRun(selectedRunId);
      await navigator.clipboard.writeText(state.plain || '');
    }
    async function copyPrompt() {
      const text = document.getElementById('promptPanel')?.textContent || '';
      await navigator.clipboard.writeText(text);
    }
    function clearLocalView() {
      const state = stateForRun(selectedRunId);
      state.ansi = '';
      state.plain = '';
      clearTerminal();
      setTerminalPlaceholder();
    }
    async function cancelSelectedRun() {
      if (!selectedRunId) return;
      await requestJson(`/api/runs/${encodeURIComponent(selectedRunId)}/cancel`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({reason: 'operator requested cancel from live monitor'})
      });
      await loadRunFull();
    }
    async function markSelectedStale() {
      if (!selectedRunId) return;
      await requestJson(`/api/runs/${encodeURIComponent(selectedRunId)}/mark-stale`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({reason: 'operator marked stale/blocked from live monitor'})
      });
      await loadRunFull();
    }
    async function refreshSelectedCandidate() {
      if (!selectedRunId) return;
      const run = runsById.get(selectedRunId) || {};
      const groupId = run.group_id || run.selected_promotion_group_id || (run.run_type === 'group_promotion' ? selectedRunId : null);
      const sourceId = (Array.isArray(run.conflicted_ids) && run.conflicted_ids[0]) || run.managed_run_id || run.task_id || selectedRunId;
      const targetId = run.target_id || run.target || 'wb-core';
      const result = await requestJson('/api/parallel-selection/refresh', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          target_id: targetId,
          candidate_id: sourceId,
          group_id: groupId,
          conflict_files: run.conflict_files || [],
          conflict_reason: run.blocker || '',
          mode: 'managed_clone_only',
          confirm_start: true,
          start_managed_run: true,
          idempotency_key: `ui-refresh-${sourceId}-${groupId || 'none'}`
        })
      });
      await refreshRuns();
      if (result.refresh_run_id) {
        selectRun(result.refresh_run_id, {user: true});
      } else {
        await loadRunFull();
      }
    }

    function openStream() {
      if (!selectedRunId || !window.EventSource || isSelectedTerminal()) return;
      runSource = new EventSource(`/api/runs/${encodeURIComponent(selectedRunId)}/stream`);
      document.getElementById('connectionState').textContent = 'sse';
      runSource.addEventListener('run', (event) => {
        const payload = JSON.parse(event.data);
        const state = stateForRun(selectedRunId);
        if (payload.log_tail && !state.loaded) appendTerminalDelta(payload.log_tail.ansi_text || '', payload.log_tail.plain_text || '', payload.log_tail.next_offset || 0);
        renderRunDetail(payload);
        if (isRunTerminal(payload.run || {})) finalizeSelectedRun();
      });
      runSource.onerror = () => {
        document.getElementById('connectionState').textContent = 'polling';
        closeStream();
      };
    }
    function closeStream() {
      if (runSource) runSource.close();
      runSource = null;
    }

    function stateForRun(runId) {
      const key = runId || '';
      if (!terminalStates.has(key)) {
        terminalStates.set(key, {offset: 0, ansi: '', plain: '', loaded: false, timeline: [], timelineCursor: '', handoff: '', report: null, lastPromptText: null, promptLoaded: false, runTerminalFinalized: false});
      }
      return terminalStates.get(key);
    }

    function isSelectedTerminal() {
      return selectedRunId ? stateForRun(selectedRunId).runTerminalFinalized : false;
    }

    function isTerminalStatus(status) {
      return terminalStatuses.has(String(status || ''));
    }

    function dedupeTimeline(events) {
      const seen = new Set();
      const result = [];
      for (const event of events) {
        const key = event.id || `${event.timestamp}-${event.stage}-${event.title}`;
        if (seen.has(key)) continue;
        seen.add(key);
        result.push(event);
      }
      return result;
    }

    function decodeEscapedText(text) {
      return String(text || '').replace(/\\\\n/g, '\\n').replace(/\\\\r/g, '\\r').replace(/\\\\t/g, '\\t');
    }

    function stripSgr(text) {
      return String(text || '').replace(/\\x1b\\[[0-9;]*m/g, '');
    }

    function updateText(node, value) {
      if (node && node.textContent !== String(value || '')) node.textContent = String(value || '');
    }

    function shortRunTitle(run) {
      const raw = String(run.task_title || run.operator_task_title || run.task_text_excerpt || run.run_id || 'Задача').trim();
      const words = raw.replace(/[\\n\\r]+/g, ' ').split(/\\s+/).filter(Boolean);
      return words.slice(0, 5).join(' ').slice(0, 64) || 'Задача';
    }

    function emptyNode(message) {
      const node = document.createElement('div');
      node.className = 'empty';
      node.textContent = message;
      return node;
    }

    function cssEscape(value) {
      if (window.CSS && CSS.escape) return CSS.escape(value);
      return String(value || '').replace(/["\\\\]/g, '\\\\$&');
    }

    document.addEventListener('visibilitychange', () => { if (!document.hidden) acknowledgeNotifications(); });
    document.addEventListener('click', () => { notificationSoundEnabled = true; if (!document.hidden) acknowledgeNotifications(); }, {passive: true});
    document.addEventListener('keydown', () => { notificationSoundEnabled = true; if (!document.hidden) acknowledgeNotifications(); }, {passive: true});

    setTerminalPlaceholder();
    refreshRuns().catch(() => scheduleListRefresh(5000));
    if (selectedRunId) selectRun(selectedRunId, {user: Boolean(initialRunId)});
  </script>
</body>
</html>
"""
    return html.replace("__SELECTED_RUN_ID__", json.dumps(selected_run_id or ""))


def _render_dashboard_html() -> str:
    return """<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Development Control Plane</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #0b0d10;
      --nav: #0f1115;
      --panel: #15171c;
      --panel-2: #1a1d23;
      --panel-3: #20242c;
      --line: #2a2f38;
      --line-soft: #20242b;
      --text: #f2f4f8;
      --muted: #8d96a6;
      --muted-2: #697383;
      --accent: #8ab4ff;
      --ok: #5bd182;
      --warn: #f0c15a;
      --bad: #ff7b72;
    }
    * { box-sizing: border-box; }
    body { margin: 0; background: var(--bg); color: var(--text); font-family: Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    .app-shell { min-height: 100vh; display: grid; grid-template-columns: 244px minmax(0, 1fr); }
    .sidebar { background: var(--nav); border-right: 1px solid var(--line-soft); padding: 18px 14px; display: flex; flex-direction: column; gap: 18px; }
    .brand { display: grid; gap: 3px; padding: 2px 8px 12px; border-bottom: 1px solid var(--line-soft); }
    .brand strong { font-size: 15px; letter-spacing: 0; }
    .brand span { color: var(--muted); font-size: 12px; }
    .side-nav { display: grid; gap: 4px; }
    .nav-item { width: 100%; text-align: left; color: #d7dce5; text-decoration: none; background: transparent; border: 1px solid transparent; border-radius: 7px; padding: 9px 10px; font-size: 14px; cursor: pointer; font: inherit; }
    .nav-item:hover, .nav-item.active { background: #191d24; border-color: var(--line-soft); color: var(--text); }
    .nav-item.active { box-shadow: inset 2px 0 0 var(--accent); }
    .sidebar-footer { margin-top: auto; color: var(--muted-2); font-size: 12px; line-height: 1.45; padding: 10px 8px; }
    .workspace { min-width: 0; display: grid; grid-template-rows: auto 1fr; }
    .topbar { min-height: 72px; display: flex; justify-content: space-between; align-items: center; gap: 16px; padding: 18px 24px; border-bottom: 1px solid var(--line-soft); background: rgba(15, 17, 21, .86); backdrop-filter: blur(12px); }
    .page-title { display: grid; gap: 4px; }
    h1 { margin: 0; font-size: 20px; letter-spacing: 0; }
    h2 { margin: 0; font-size: 16px; letter-spacing: 0; }
    h3 { margin: 0 0 10px; font-size: 13px; color: var(--muted); font-weight: 600; text-transform: uppercase; letter-spacing: .04em; }
    .subtitle, .muted { color: var(--muted); font-size: 13px; line-height: 1.45; }
    main { padding: 22px 24px 28px; min-width: 0; }
    .tab { display: none; }
    .tab.active { display: grid; gap: 18px; }
    .status-grid { display: grid; grid-template-columns: repeat(3, minmax(190px, 1fr)); gap: 14px; }
    .panel, .status-card { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; box-shadow: 0 16px 40px rgba(0,0,0,.18); }
    .panel { padding: 16px; }
    .status-card { min-height: 122px; padding: 16px; display: grid; align-content: space-between; gap: 14px; }
    .card-head { display: flex; justify-content: space-between; gap: 12px; align-items: start; }
    .card-title { font-size: 13px; color: var(--muted); }
    .card-value { font-size: 21px; line-height: 1.15; font-weight: 650; overflow-wrap: anywhere; }
    .card-detail { color: var(--muted); font-size: 12px; line-height: 1.45; overflow-wrap: anywhere; }
    .dot { width: 9px; height: 9px; border-radius: 50%; background: var(--muted-2); margin-top: 4px; flex: 0 0 auto; }
    .tone-ok .dot { background: var(--ok); }
    .tone-warn .dot { background: var(--warn); }
    .tone-bad .dot { background: var(--bad); }
    .tone-ok .card-value { color: var(--ok); }
    .tone-warn .card-value { color: var(--warn); }
    .tone-bad .card-value { color: var(--bad); }
    .two-col { display: grid; grid-template-columns: minmax(320px, .72fr) minmax(360px, 1fr); gap: 14px; align-items: start; }
    .compact-list { display: grid; gap: 10px; margin: 0; }
    .compact-list div { display: grid; grid-template-columns: 160px minmax(0, 1fr); gap: 12px; padding: 8px 0; border-bottom: 1px solid var(--line-soft); }
    .compact-list div:last-child { border-bottom: 0; }
    .compact-list dt { color: var(--muted); font-size: 12px; }
    .compact-list dd { margin: 0; overflow-wrap: anywhere; font: 13px/1.45 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
    label { display: block; color: var(--muted); font-size: 12px; margin: 12px 0 6px; }
    select { width: 100%; background: #0f1217; color: var(--text); border: 1px solid var(--line); border-radius: 8px; padding: 10px 11px; font: inherit; }
    button.primary { margin-top: 14px; border: 1px solid #365f9f; background: #1d3d70; color: var(--text); border-radius: 8px; padding: 10px 13px; cursor: pointer; font: inherit; }
    button.primary:hover { background: #244a84; }
    button.secondary { border: 1px solid var(--line); background: var(--panel-3); color: var(--text); border-radius: 8px; padding: 9px 12px; cursor: pointer; font: inherit; }
    .badge-row { display: flex; flex-wrap: wrap; gap: 8px; justify-content: flex-end; }
    .badge { border: 1px solid var(--line); background: var(--panel); border-radius: 999px; color: #c9d1dd; padding: 6px 9px; font-size: 12px; }
    .actions { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }
    .full-width { width: 100%; min-width: 0; }
    .section-head { display: flex; justify-content: space-between; gap: 14px; align-items: start; margin-bottom: 12px; }
    .table-wrap { width: 100%; min-width: 0; max-width: 100%; overflow-x: auto; border: 1px solid var(--line-soft); border-radius: 8px; background: #101318; }
    .data-table { width: 100%; min-width: 980px; border-collapse: collapse; font-size: 12px; }
    .data-table th, .data-table td { padding: 10px 11px; border-bottom: 1px solid var(--line-soft); text-align: left; vertical-align: top; }
    .data-table th { color: var(--muted); font-weight: 600; background: #12161c; position: sticky; top: 0; }
    .data-table tr:last-child td { border-bottom: 0; }
    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; overflow-wrap: anywhere; }
    .chip { display: inline-flex; align-items: center; border: 1px solid var(--line); background: var(--panel-2); border-radius: 999px; padding: 3px 8px; color: #d7dce5; font-size: 11px; white-space: nowrap; }
    .chip.ok { border-color: rgba(91,209,130,.35); color: var(--ok); }
    .chip.warn { border-color: rgba(240,193,90,.38); color: var(--warn); }
    .chip.bad { border-color: rgba(255,123,114,.42); color: var(--bad); }
    .mini-actions { display: flex; gap: 6px; flex-wrap: wrap; }
    .mini-actions button { border: 1px solid var(--line); background: var(--panel-3); color: var(--text); border-radius: 7px; padding: 5px 7px; cursor: pointer; font: inherit; font-size: 11px; }
    .mini-actions button:hover { border-color: var(--accent); }
    .action-status { min-height: 18px; margin-top: 10px; }
    pre { margin: 0; max-height: 420px; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; background: #0f1217; border: 1px solid var(--line-soft); border-radius: 8px; padding: 12px; color: #cbd3df; font: 12px/1.45 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
    details { border: 1px solid var(--line); border-radius: 8px; background: #12151a; padding: 12px; }
    summary { cursor: pointer; color: #d7dce5; font-weight: 600; }
    a { color: var(--accent); }
    @media (max-width: 980px) {
      .app-shell { grid-template-columns: 1fr; }
      .sidebar { position: static; }
      .status-grid, .two-col { grid-template-columns: 1fr; }
      .topbar { align-items: start; flex-direction: column; }
      .badge-row { justify-content: flex-start; }
    }
  </style>
</head>
<body>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand">
        <strong>DevControl</strong>
        <span>Hosted control plane</span>
      </div>
      <nav class="side-nav" aria-label="DevControl navigation">
        <a class="nav-item" href="/runs/live">Мониторинг</a>
        <button id="tab-dashboard-button" class="nav-item active" type="button" onclick="showTab('dashboard')">Панель</button>
        <button id="tab-connection-button" class="nav-item" type="button" onclick="showTab('connection')">Подключение</button>
        <button id="tab-technical-button" class="nav-item" type="button" onclick="showTab('technical')">Технические детали</button>
      </nav>
      <div class="sidebar-footer">MCP и live monitor остаются bounded. Browser command input отсутствует.</div>
    </aside>
    <div class="workspace">
      <header class="topbar">
        <div class="page-title">
          <h1 id="pageHeading">Development Control Plane</h1>
          <div id="pageSubtitle" class="subtitle">Единая темная панель для статусов, подключений и живых запусков.</div>
        </div>
        <div class="badge-row">
          <span class="badge" id="serviceBadge">Сервис: проверка</span>
          <span class="badge" id="mcpBadge">MCP: checking</span>
          <span class="badge" id="codexBadge">Codex: checking</span>
        </div>
      </header>
      <main>
        <section id="tab-dashboard" class="tab active">
          <div class="status-grid" id="dashboardCards"></div>
          <div class="two-col">
            <section class="panel">
              <h2>Активные и недавние запуски</h2>
              <p class="muted">Откройте live monitor, чтобы смотреть terminal-like output, timeline events, changed files и final handoff.</p>
              <div class="actions">
                <a class="nav-item active" href="/runs/live">Мониторинг</a>
              </div>
            </section>
            <section class="panel">
              <h2>wb-core production boundary</h2>
              <dl class="compact-list" id="productionSummary"></dl>
            </section>
          </div>
          <section class="panel full-width">
            <div class="section-head">
              <div>
                <h2>Parallel task ledger</h2>
                <p class="muted">Операторская доска state-machine задач. Default execution is fake/state-only; real managed-clone and production bridge require explicit guarded flags. frozen_base_stale / refresh_required показываются отдельно.</p>
              </div>
              <div class="actions">
                <button class="secondary" type="button" onclick="parallelPromoteNext('dry_run')">Promote next dry</button>
                <button class="secondary" type="button" onclick="parallelPromoteNext('fake_complete')">Promote next fake</button>
              </div>
            </div>
            <dl class="compact-list" id="parallelPromotionState"></dl>
            <div class="table-wrap">
              <table class="data-table" aria-label="Parallel task ledger">
                <thead>
                  <tr>
                    <th>task_id</th>
                    <th>target/status</th>
                    <th>source</th>
                    <th>batch/release</th>
                    <th>epoch/run</th>
                    <th>candidate</th>
                    <th>blocker</th>
                    <th>timestamps</th>
                    <th>actions</th>
                  </tr>
                </thead>
                <tbody id="parallelTasksBody">
                  <tr><td colspan="9" class="muted">Loading parallel tasks...</td></tr>
                </tbody>
              </table>
            </div>
            <div id="parallelActionStatus" class="muted action-status"></div>
          </section>
        </section>
        <section id="tab-connection" class="tab">
          <div class="two-col">
            <section class="panel">
              <h2>Настройки куратора</h2>
              <p class="muted">Только non-secret model/reasoning. API keys, OAuth grants и credentials остаются terminal-only.</p>
              <div id="curatorRuntimeControls"></div>
            </section>
            <section class="panel">
              <h2>Настройки Codex</h2>
              <p class="muted">Только non-secret Codex runtime defaults. Login и credentials остаются terminal-only.</p>
              <div id="codexRuntimeControls"></div>
              <button id="runtimeConfigSaveButton" class="primary" type="button" onclick="saveRuntimeConfig()">Сохранить</button>
              <div id="runtimeConfigStatus" class="muted">Настройки не менялись.</div>
            </section>
            <section class="panel">
              <h2>Готовность Codex CLI</h2>
              <dl class="compact-list" id="codexStatus"></dl>
            </section>
          </div>
        </section>
        <section id="tab-technical" class="tab">
          <div class="two-col">
            <section class="panel">
              <h2>Технические детали / Advanced</h2>
              <dl class="compact-list" id="technicalSummary"></dl>
              <div class="actions">
                <button class="secondary" type="button" onclick="refreshAll()">Обновить</button>
              </div>
            </section>
            <section class="panel">
              <h2>Sanitized diagnostics</h2>
              <details>
                <summary>Показать compact JSON</summary>
                <pre id="advancedJson">Loading...</pre>
              </details>
            </section>
          </div>
        </section>
      </main>
    </div>
  </div>
  <script>
    let lastStatusPayload = {};

    async function request(path, options = {}) {
      const response = await fetch(path, {cache: 'no-store', ...options});
      const text = await response.text();
      let data = {};
      try { data = text ? JSON.parse(text) : {}; } catch (error) { data = {error: text ? text.slice(0, 240) : response.statusText}; }
      if (!response.ok) throw new Error(data.error || response.statusText);
      return data;
    }

    function showTab(name) {
      for (const tab of document.querySelectorAll('.tab')) tab.classList.remove('active');
      for (const item of document.querySelectorAll('.side-nav .nav-item')) item.classList.remove('active');
      const tab = document.getElementById(`tab-${name}`);
      const button = document.getElementById(`tab-${name}-button`);
      if (tab) tab.classList.add('active');
      if (button) button.classList.add('active');
      const titles = {
        dashboard: ['Панель', 'Сервис, MCP, target lock и run readiness без raw debug шума.'],
        connection: ['Подключение', 'Curator и Codex model/reasoning settings.'],
        technical: ['Технические детали', 'Compact advanced diagnostics без raw secrets.']
      };
      document.getElementById('pageHeading').textContent = titles[name]?.[0] || 'Development Control Plane';
      document.getElementById('pageSubtitle').textContent = titles[name]?.[1] || '';
      if (location.hash !== `#${name}`) history.replaceState(null, '', name === 'dashboard' ? location.pathname : `#${name}`);
    }

    function bootTabFromHash() {
      const name = (location.hash || '').replace('#', '');
      if (['connection', 'technical'].includes(name)) showTab(name);
    }

    async function refreshAll() {
      const [state, connections, runtime, runs, targets, parallelTasks, parallelCandidates, parallelPromotion] = await Promise.all([
        request('/api/state'),
        request('/api/connections/status'),
        request('/api/runtime-config'),
        request('/api/runs/live'),
        request('/api/target-projects'),
        request('/api/parallel-tasks?target_id=wb-core'),
        request('/api/parallel-targets/wb-core/promotion-candidates'),
        request('/api/parallel-targets/wb-core/promotion-state')
      ]);
      lastStatusPayload = {state, connections, runtime, runs, targets, parallelTasks, parallelCandidates, parallelPromotion};
      renderDashboard(state, connections, runs, targets, parallelTasks, parallelCandidates, parallelPromotion);
      renderConnection(connections, runtime);
      renderTechnical(state, connections, runtime, runs, targets, parallelTasks, parallelCandidates, parallelPromotion);
    }

    function renderDashboard(state, connections, runs, targets, parallelTasks, parallelCandidates, parallelPromotion) {
      const mcp = state.mcp || {};
      const github = connections.github || {};
      const ssh = connections.ssh_deploy || {};
      const parity = connections.codex_runtime_parity || {};
      const lock = state.target_production_lock || {};
      const cards = [
        card('Сервис DevControl', state.hosted_ready ? 'hosted-ready' : 'loopback', `profile ${state.runtime_profile || 'local'} · ${state.host || '127.0.0.1'}:${state.port || ''}`, state.hosted_ready ? 'ok' : 'neutral'),
        card('MCP auth/tools', mcp.auth?.write_tools?.configured ? 'OAuth ready' : 'read-only ready', `${mcp.transport || 'streamable_http'} · ${mcp.tool_count ?? 0} tools`, mcp.enabled ? 'ok' : 'bad'),
        card('Codex runtime parity', parity.status || 'unknown', parity.exact_blocker || `browser ${parity.webcore_ui_browser_ready ? 'ready' : 'blocked'}`, parity.status === 'ready' ? 'ok' : 'bad'),
        card('GitHub-доступ', github.status || 'unknown', github.blocker || github.source || 'sanitized readiness', github.status === 'ready' ? 'ok' : (github.status === 'missing' ? 'bad' : 'warn')),
        card('SSH-деплой', ssh.status || 'unknown', ssh.blocker || ssh.source || 'sanitized readiness', ssh.status === 'ready' ? 'ok' : (ssh.status === 'missing' ? 'bad' : 'warn')),
        card('Активные запуски', String(runs.active_count ?? 0), `${(runs.runs || []).length} visible active/recent runs`, Number(runs.active_count || 0) > 0 ? 'warn' : 'ok'),
        card('wb-core production lock', lock.status || 'unknown', lock.active_run_id ? `active run ${lock.active_run_id}` : (lock.blocker || 'single-target serialization gate'), lock.status === 'free' ? 'ok' : (lock.status === 'locked' ? 'warn' : 'neutral'))
      ];
      document.getElementById('dashboardCards').innerHTML = cards.join('');
      document.getElementById('productionSummary').innerHTML = statusList([
        ['target', 'wb-core'],
        ['production_lane', state.target_production_lane_enabled ? 'enabled' : 'disabled'],
        ['lock status', lock.status || 'unknown'],
        ['active run', lock.active_run_id || 'none'],
        ['targets', (targets.targets || []).map((target) => target.project_id).join(', ') || 'none']
      ]);
      document.getElementById('serviceBadge').textContent = `Сервис: ${state.runtime_profile || 'local'}`;
      document.getElementById('mcpBadge').textContent = `MCP: ${mcp.tool_count ?? 0} tools`;
      document.getElementById('codexBadge').textContent = `Codex: ${connections.codex?.status || 'unknown'}`;
      renderParallelDashboard(parallelTasks, parallelCandidates, parallelPromotion);
    }

    function renderParallelDashboard(parallelTasks, parallelCandidates, parallelPromotion) {
      const tasks = parallelTasks?.tasks || [];
      const candidates = parallelCandidates?.candidates || [];
      const state = parallelPromotion || {};
      document.getElementById('parallelPromotionState').innerHTML = statusList([
        ['target_id', state.target_id || 'wb-core'],
        ['promotion_epoch', state.promotion_epoch || 'current'],
        ['state', state.promotion_state || state.status || 'none'],
        ['first candidate', state.first_candidate_task_id || 'none'],
        ['completed task', state.completed_task_id || 'none'],
        ['ping-pong', state.parallel_ping_pong_enabled === false ? 'frozen' : 'unknown']
      ]);
      const rows = tasks.map((task) => {
        const candidate = candidates.find((item) => item.task_id === task.task_id) || {};
        const stale = task.refresh_required || ['frozen_base_stale', 'refresh_required'].includes(task.status);
        const lifecycleTone = task.operator_lifecycle_tone || (stale ? 'refresh' : '');
        const statusTone = lifecycleTone === 'ok' ? 'ok' : (lifecycleTone === 'ready' || lifecycleTone === 'refresh' ? 'warn' : (['failed', 'blocked'].includes(task.status) ? 'bad' : ''));
        const lifecycleLabel = task.operator_lifecycle_label || task.status || 'unknown';
        const candidateText = candidate.status || (task.status === 'verifier_passed' ? 'eligible' : 'none');
        const blocker = task.blocker || candidate.blocker || (candidate.promotion_blockers || []).join('; ') || '';
        return `<tr>
          <td class="mono">${escapeHtml(task.task_id || '')}</td>
          <td>${statusChip(lifecycleLabel, statusTone)}<div class="muted mono">${escapeHtml(task.status || 'unknown')}</div><div class="muted mono">${escapeHtml(task.target_id || '')}</div>${stale ? '<div class="chip warn">refresh_required</div>' : ''}</td>
          <td><div>${escapeHtml(task.source || '')}</div><div class="muted">${escapeHtml(task.source_chat || task.chat_id || '')}</div><div class="muted">${escapeHtml(task.source_tool || '')}</div></td>
          <td><div>${escapeHtml(task.batch_id || 'none')}</div><div class="muted">${escapeHtml(task.release_group || 'none')}</div></td>
          <td><div class="mono">${escapeHtml(task.promotion_epoch || '')}</div><div class="muted mono">${escapeHtml(task.managed_run_id || 'no run')}</div></td>
          <td>${statusChip(candidateText, candidateText === 'eligible' ? 'ok' : (stale ? 'warn' : ''))}<div class="muted">${escapeHtml((candidate.promotion_blockers || []).join('; '))}</div></td>
          <td>${escapeHtml(blocker || 'none')}</td>
          <td><div>${escapeHtml(task.created_at || '')}</div><div class="muted">${escapeHtml(task.updated_at || '')}</div></td>
          <td><div class="mini-actions">
            ${parallelButton(task.task_id, 'start_fake', 'fake start')}
            ${parallelButton(task.task_id, 'reconcile_pass', 'pass')}
            ${parallelButton(task.task_id, 'reconcile_blocked', 'block')}
            ${parallelButton(task.task_id, 'promote_dry', 'dry')}
            ${parallelButton(task.task_id, 'promote_fake', 'fake complete')}
          </div></td>
        </tr>`;
      });
      document.getElementById('parallelTasksBody').innerHTML = rows.length ? rows.join('') : '<tr><td colspan="9" class="muted">Parallel ledger is empty. Submit through API/MCP; default execution remains state-only.</td></tr>';
    }

    function statusChip(value, tone) {
      const toneClass = tone ? ` ${tone}` : '';
      return `<span class="chip${toneClass}">${escapeHtml(value || 'unknown')}</span>`;
    }

    function parallelButton(taskId, action, label) {
      return `<button type="button" onclick="parallelAction('${escapeHtml(taskId)}', '${escapeHtml(action)}')">${escapeHtml(label)}</button>`;
    }

    async function parallelAction(taskId, action) {
      const status = document.getElementById('parallelActionStatus');
      status.textContent = 'Parallel action running...';
      let path = `/api/parallel-tasks/${encodeURIComponent(taskId)}/start-execution`;
      let body = {starter_mode: 'fake'};
      if (action === 'reconcile_pass') {
        path = `/api/parallel-tasks/${encodeURIComponent(taskId)}/reconcile`;
        body = {run_status: 'passed', verifier_status: 'passed', changed_files: [], verifier_summary: {forbidden_paths_clean: true, source: 'operator_dashboard_fake'}};
      } else if (action === 'reconcile_blocked') {
        path = `/api/parallel-tasks/${encodeURIComponent(taskId)}/reconcile`;
        body = {run_status: 'blocked', blocker: 'operator dashboard fake blocker'};
      } else if (action === 'promote_dry') {
        path = `/api/parallel-tasks/${encodeURIComponent(taskId)}/promote`;
        body = {allow_auto_first_promotion: true, mode: 'dry_run'};
      } else if (action === 'promote_fake') {
        path = `/api/parallel-tasks/${encodeURIComponent(taskId)}/promote`;
        body = {allow_auto_first_promotion: true, mode: 'fake_complete'};
      }
      try {
        const result = await request(path, {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify(body)
        });
        status.textContent = `${action}: ${result.status || 'ok'}`;
        await refreshAll();
      } catch (error) {
        status.textContent = String(error);
      }
    }

    async function parallelPromoteNext(mode) {
      const status = document.getElementById('parallelActionStatus');
      status.textContent = 'Parallel promote-next running...';
      try {
        const result = await request('/api/parallel-targets/wb-core/promote-next', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({allow_auto_first_promotion: true, mode})
        });
        status.textContent = `promote_next ${mode}: ${result.status || 'ok'}`;
        await refreshAll();
      } catch (error) {
        status.textContent = String(error);
      }
    }

    function renderConnection(connections, runtime) {
      const codex = connections.codex || {};
      const openai = connections.openai || {};
      const parity = connections.codex_runtime_parity || {};
      document.getElementById('codexStatus').innerHTML = statusList([
        ['Статус', codex.status || 'unknown'],
        ['version', codex.version || 'n/a'],
        ['auth', codex.auth_status || 'unknown'],
        ['model', codex.model || runtime.codex?.model || 'n/a'],
        ['reasoning', codex.model_reasoning_effort || runtime.codex?.reasoning_effort || 'n/a'],
        ['mode', connections.control_plane?.real_codex_ui_mode || 'managed_clone_only'],
        ['runtime parity', parity.status || 'unknown'],
        ['npm/corepack/pnpm/yarn', (parity.missing_required || []).filter((name) => ['npm','corepack','pnpm','yarn'].includes(name)).join(', ') || 'ready'],
        ['browser smokes', parity.webcore_ui_browser_ready ? 'ready' : (parity.browser?.blocker || 'blocked')],
        ['manual login', (codex.instructions || []).join(' / ') || 'codex login --device-auth']
      ]);
      renderCuratorControls(runtime, openai);
      renderCodexControls(runtime);
    }

    function renderCuratorControls(runtime, openaiStatus) {
      const options = runtime.options || {};
      const openai = runtime.openai || {};
      document.getElementById('curatorRuntimeControls').innerHTML = `
        <label for="curatorModelInput">Curator model</label>
        <select id="curatorModelInput">${optionHtml(options.openai_models || [], openai.model)}</select>
        <label for="curatorReasoningInput">Curator reasoning</label>
        <select id="curatorReasoningInput">${simpleOptionsHtml(options.reasoning_efforts || [], openai.reasoning_effort)}</select>
        <p class="muted">Статус: ${escapeHtml(openaiStatus.status || 'unknown')}. Active: ${escapeHtml(openai.model || 'not set')} / ${escapeHtml(openai.reasoning_effort || 'not set')} (${escapeHtml(openai.source || 'default')})</p>
      `;
    }

    function renderCodexControls(runtime) {
      const options = runtime.options || {};
      const codex = runtime.codex || {};
      document.getElementById('codexRuntimeControls').innerHTML = `
        <label for="codexModelInput">Codex model</label>
        <select id="codexModelInput">${optionHtml(options.codex_models || [], codex.model)}</select>
        <label for="codexReasoningInput">Codex reasoning</label>
        <select id="codexReasoningInput">${simpleOptionsHtml(options.reasoning_efforts || [], codex.reasoning_effort)}</select>
        <p class="muted">Active: ${escapeHtml(codex.model || 'not set')} / ${escapeHtml(codex.reasoning_effort || 'not set')} (${escapeHtml(codex.source || 'default')})</p>
      `;
    }

    async function saveRuntimeConfig() {
      const button = document.getElementById('runtimeConfigSaveButton');
      button.disabled = true;
      document.getElementById('runtimeConfigStatus').textContent = 'Сохраняю...';
      try {
        const payload = {
          openai: {
            model: document.getElementById('curatorModelInput')?.value || '',
            reasoning_effort: document.getElementById('curatorReasoningInput')?.value || ''
          },
          codex: {
            model: document.getElementById('codexModelInput')?.value || '',
            reasoning_effort: document.getElementById('codexReasoningInput')?.value || ''
          }
        };
        const saved = await request('/api/runtime-config', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify(payload)
        });
        document.getElementById('runtimeConfigStatus').textContent = `Сохранено: Curator ${saved.openai?.model}/${saved.openai?.reasoning_effort}; Codex ${saved.codex?.model}/${saved.codex?.reasoning_effort}.`;
        await refreshAll();
      } catch (error) {
        document.getElementById('runtimeConfigStatus').textContent = String(error);
      } finally {
        button.disabled = false;
      }
    }

    function renderTechnical(state, connections, runtime, runs, targets, parallelTasks, parallelCandidates, parallelPromotion) {
      const mcp = state.mcp || {};
      const toolchain = connections.toolchain || {};
      const parity = connections.codex_runtime_parity || {};
      const observability = state.codex_observability || {};
      document.getElementById('technicalSummary').innerHTML = statusList([
        ['runtime profile', state.runtime_profile || 'local'],
        ['state root', state.state_dir || 'n/a'],
        ['MCP endpoint', mcp.endpoint || '/mcp'],
        ['MCP public tools', mcp.public_tool_count ?? 0],
        ['Codex watchdog', observability.watchdog?.enabled ? 'ready' : 'unknown'],
        ['Codex io mode', observability.io_mode?.effective || 'event'],
        ['Codex runtime parity', parity.status || 'unknown'],
        ['webcore browser ready', parity.webcore_ui_browser_ready ? 'yes' : 'no'],
        ['toolchain', toolchain.status || 'unknown'],
        ['missing tools', (toolchain.missing_required || []).join(', ') || 'none'],
        ['run count', state.counts?.runs ?? 0]
      ]);
      document.getElementById('advancedJson').textContent = JSON.stringify({
        service: {
          runtime_profile: state.runtime_profile,
          host: state.host,
          port: state.port,
          state_dir: state.state_dir,
          counts: state.counts,
          exposed_routes: state.exposed_routes,
          target_production_lock: state.target_production_lock,
        },
        mcp,
        codex_observability: observability,
        codex: connections.codex,
        codex_runtime_parity: parity,
        github: connections.github,
        ssh_deploy: connections.ssh_deploy,
        parallel_task_ledger: {
          status: state.parallel_task_ledger,
          tasks: parallelTasks,
          candidates: parallelCandidates,
          promotion_state: parallelPromotion
        },
        runtime_config: runtime,
        live_runs: {active_count: runs.active_count, terminal_statuses: runs.terminal_statuses},
        targets: (targets.targets || []).map((target) => ({
          project_id: target.project_id,
          display_name: target.display_name,
          validation_status: target.validation_status,
          source_mode: target.source_mode,
          blockers: target.blockers,
          warnings: target.warnings
        }))
      }, null, 2);
    }

    function card(title, value, detail, tone) {
      const toneClass = tone ? ` tone-${tone}` : '';
      return `<article class="status-card${toneClass}"><div class="card-head"><div class="card-title">${escapeHtml(title)}</div><span class="dot"></span></div><div><div class="card-value">${escapeHtml(value)}</div><div class="card-detail">${escapeHtml(detail)}</div></div></article>`;
    }

    function statusList(items) {
      return items.map(([key, value]) => `<div><dt>${escapeHtml(key)}</dt><dd>${escapeHtml(String(value ?? ''))}</dd></div>`).join('');
    }

    function optionHtml(items, selected) {
      return (items || []).map((item) => {
        const id = item.id || item;
        const label = item.label || id;
        const isSelected = id === selected ? ' selected' : '';
        return `<option value="${escapeHtml(id)}"${isSelected}>${escapeHtml(label)}</option>`;
      }).join('');
    }

    function simpleOptionsHtml(items, selected) {
      return (items || []).map((id) => {
        const isSelected = id === selected ? ' selected' : '';
        return `<option value="${escapeHtml(id)}"${isSelected}>${escapeHtml(id)}</option>`;
      }).join('');
    }

    function escapeHtml(value) {
      return String(value ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#039;');
    }

    window.addEventListener('hashchange', bootTabFromHash);
    bootTabFromHash();
    refreshAll().catch((error) => {
      document.getElementById('dashboardCards').innerHTML = card('Dashboard load failed', String(error), 'Refresh or inspect Technical Details.', 'bad');
      document.getElementById('advancedJson').textContent = String(error);
    });
  </script>
</body>
</html>"""


def _render_operator_html() -> str:
    return _render_dashboard_html()


def _render_legacy_chat_operator_html() -> str:
    return """<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Development Control Plane</title>
  <style>
    :root { color-scheme: light; --bg: #f6f5f1; --panel: #ffffff; --line: #d9d6cd; --text: #202124; --muted: #62645f; --accent: #1f6f5b; --danger: #9f2f26; --soft: #eef4f1; }
    body { margin: 0; background: var(--bg); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    header { background: #1f262b; color: white; padding: 16px 22px; }
    header h1 { margin: 0 0 8px; font-size: 22px; letter-spacing: 0; }
    .topbar { display: grid; grid-template-columns: minmax(240px, 1fr) auto auto; gap: 12px; align-items: end; }
    .topbar label { display: block; font-size: 12px; color: #d7dedc; margin-bottom: 4px; }
    select, textarea, input { width: 100%; box-sizing: border-box; border: 1px solid var(--line); border-radius: 6px; padding: 9px; font: inherit; background: white; color: var(--text); }
    .badge { border: 1px solid rgba(255,255,255,.3); border-radius: 999px; padding: 7px 10px; font-size: 13px; white-space: nowrap; }
    nav { display: flex; flex-wrap: wrap; gap: 8px; padding: 10px 22px 0; background: #1f262b; }
    nav button { background: transparent; color: white; border: 1px solid rgba(255,255,255,.35); border-bottom: 0; border-radius: 7px 7px 0 0; padding: 9px 14px; cursor: pointer; }
    nav button.active { background: var(--bg); color: var(--text); border-color: var(--bg); }
    nav a.nav-link { margin-left: auto; color: white; text-decoration: none; border: 1px solid rgba(255,255,255,.35); border-bottom: 0; border-radius: 7px 7px 0 0; padding: 9px 14px; background: rgba(255,255,255,.06); }
    nav a.nav-link:hover { background: rgba(255,255,255,.12); }
    main { max-width: 1180px; margin: 0 auto; padding: 18px; }
    .tab { display: none; }
    .tab.active { display: block; }
    .grid { display: grid; grid-template-columns: minmax(360px, 1.15fr) minmax(320px, .85fr); gap: 14px; align-items: start; }
    section, .panel { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 14px; }
    h2 { margin: 0 0 10px; font-size: 17px; }
    h3 { margin: 12px 0 8px; font-size: 14px; }
    .muted { color: var(--muted); font-size: 13px; }
    .chat { min-height: 380px; max-height: 52vh; overflow: auto; display: flex; flex-direction: column; gap: 10px; padding: 8px; background: #fbfaf7; border: 1px solid var(--line); border-radius: 8px; }
    .bubble { max-width: 78%; border-radius: 12px; padding: 10px 12px; line-height: 1.38; white-space: pre-wrap; overflow-wrap: anywhere; animation: fadeIn .14s ease-out; }
    .operator { align-self: flex-end; background: #dfeee8; }
    .curator { align-self: flex-start; background: #f0eee8; }
    .system { align-self: center; background: #fff5d9; color: #604800; }
    .pending { opacity: .72; }
    .error { border: 1px solid #d39b93; background: #fff0ed; }
    .message-meta { display: block; margin-top: 5px; color: var(--muted); font-size: 12px; }
    .typing::after { content: ''; display: inline-block; width: 1.2em; text-align: left; animation: dots 1.1s steps(4, end) infinite; }
    .composer { display: grid; grid-template-columns: 1fr auto; gap: 8px; margin-top: 10px; align-items: end; }
    .composer textarea { min-height: 78px; resize: vertical; }
    button { border: 1px solid #1e6654; background: var(--accent); color: white; border-radius: 6px; padding: 9px 12px; cursor: pointer; font: inherit; }
    button:disabled { opacity: .66; cursor: wait; }
    button.secondary { background: #f6f5f1; color: var(--text); border-color: var(--line); }
    button.danger { background: var(--danger); border-color: var(--danger); }
    .actions { display: flex; flex-wrap: wrap; gap: 8px; margin: 12px 0; }
    .primary-actions button { font-weight: 600; }
    .card-list { margin: 0; padding-left: 18px; }
    .task-card dl { margin: 0; display: grid; grid-template-columns: 150px 1fr; gap: 8px 12px; }
    .task-card dt { color: var(--muted); }
    .task-card dd { margin: 0; }
    .result { background: var(--soft); border: 1px solid #cddbd4; border-radius: 8px; padding: 12px; }
    .result-summary dl { margin: 0; display: grid; grid-template-columns: 150px 1fr; gap: 8px 12px; }
    .result-summary dt { color: var(--muted); }
    .result-summary dd { margin: 0; }
    .inline-preview { margin-top: 10px; }
    .inline-preview pre { max-height: 260px; }
    .timeline { display: grid; gap: 8px; margin-top: 8px; max-height: 400px; overflow-y: auto; padding-right: 4px; }
    .timeline-event { border-left: 3px solid var(--line); background: #fbfaf7; padding: 8px 10px; border-radius: 6px; }
    .timeline-event strong { display: block; }
    .timeline-event .detail { color: var(--muted); font-size: 13px; margin-top: 3px; }
    .timeline-event.info { border-left-color: #6f8f86; }
    .timeline-event.success { border-left-color: #2d7b5f; background: #eef8f3; }
    .timeline-event.warning { border-left-color: #b9822c; background: #fff6e5; }
    .timeline-event.error { border-left-color: var(--danger); background: #fff0ed; }
    .action-status { min-height: 20px; margin: 10px 0; padding: 8px 10px; border-radius: 6px; background: #f4f3ee; color: var(--muted); font-size: 13px; }
    .action-status.running { background: #eef4f1; color: #235747; }
    .action-status.error { background: #fff0ed; color: #8c2d24; }
    .spinner { display: inline-block; width: .9em; height: .9em; border: 2px solid rgba(255,255,255,.45); border-top-color: white; border-radius: 50%; margin-right: 6px; vertical-align: -2px; animation: spin .8s linear infinite; }
    pre { white-space: pre-wrap; overflow-wrap: anywhere; background: #f4f3ee; border: 1px solid var(--line); border-radius: 6px; padding: 10px; max-height: 360px; overflow: auto; }
    details { margin-top: 10px; }
    summary { cursor: pointer; color: #264f44; font-weight: 600; }
    .connections { display: grid; grid-template-columns: repeat(2, minmax(260px, 1fr)); gap: 14px; }
    code { background: #efeee8; padding: 2px 4px; border-radius: 4px; }
    @media (max-width: 860px) { .topbar, .grid, .connections { grid-template-columns: 1fr; } .composer { grid-template-columns: 1fr; } .bubble { max-width: 92%; } }
    @keyframes spin { to { transform: rotate(360deg); } }
    @keyframes fadeIn { from { opacity: 0; transform: translateY(3px); } to { opacity: 1; transform: translateY(0); } }
    @keyframes dots { 0% { content: ''; } 25% { content: '.'; } 50% { content: '..'; } 75%, 100% { content: '...'; } }
  </style>
</head>
<body>
  <header>
    <h1>Development Control Plane</h1>
    <div class="topbar">
      <div>
        <label for="targetProjectInput">Целевой проект</label>
        <select id="targetProjectInput" onchange="selectTargetProject()">
          <option value="">Загрузка проектов...</option>
        </select>
      </div>
      <div class="badge" id="openaiBadge">OpenAI-куратор: проверка</div>
      <div class="badge" id="codexBadge">Codex CLI: проверка</div>
    </div>
    <div class="muted">Local-only Development Control Plane prototype. Локальный control-plane: без public route, live/deploy, Codex только в managed clone и без изменений в target repo.</div>
  </header>
  <nav>
    <button id="tab-chat-button" class="active" onclick="showTab('chat')">Чат</button>
    <button id="tab-connections-button" onclick="showTab('connections')">Подключения</button>
    <button id="tab-technical-button" onclick="showTab('technical')">Технические детали</button>
    <a class="nav-link" href="/runs/live">Мониторинг</a>
  </nav>
  <main>
    <div id="tab-chat" class="tab active">
      <div class="grid">
        <section>
          <h2>Чат</h2>
          <div id="chatMessages" class="chat"></div>
          <div class="composer">
            <textarea id="messageInput" placeholder="Опиши задачу"></textarea>
            <button id="sendButton" onclick="addMessage()">Отправить</button>
          </div>
          <div id="actionStatus" class="action-status">Готов к работе.</div>
          <div class="actions primary-actions">
            <button id="prepareTaskButton" onclick="prepareTask()">Подготовить задачу</button>
            <button id="codexRunButton" onclick="runCodexManaged()" disabled>Запустить Codex безопасно</button>
          </div>
          <details>
            <summary>Дополнительные действия</summary>
            <div class="actions">
              <button id="draftButton" class="secondary" onclick="draftTaskSpec()">Сформировать карточку вручную</button>
              <button id="freezeButton" class="secondary" onclick="freezeTask()">Зафиксировать вручную</button>
              <button id="safeFlowButton" class="secondary" onclick="runSafeFakeFlow()">Тестовый прогон без Codex</button>
            </div>
            <div class="muted">Тестовый прогон без Codex проверяет pipeline без реального Codex. Обычно не требуется перед стандартным managed-clone запуском.</div>
          </details>
          <div class="muted">Реальный Codex запускается только в managed clone. Оригинальный wb-core не меняется. Для wb-core дальнейший commit/PR/merge/deploy допускается только через явный production lane после verifier passed и target lock.</div>
        </section>
        <section>
          <h2>Карточка задачи</h2>
          <div id="taskCard" class="task-card muted">Пока нет карточки. Напишите задачу и нажмите “Подготовить задачу”.</div>
          <div id="draftMetrics" class="muted">Метрики подготовки появятся после формирования карточки.</div>
          <h3>Результат выполнения</h3>
          <div id="resultBox" class="result">Пока запусков нет.</div>
          <div id="resultSummaryBox" class="result result-summary">Результат выполнения появится после fake-run или Codex run.</div>
          <details id="diffInlineDetails" class="inline-preview">
            <summary>Показать diff</summary>
            <pre id="diffInlinePreview">Diff ещё не создан.</pre>
          </details>
          <details id="handoffInlineDetails" class="inline-preview">
            <summary>Показать handoff</summary>
            <pre id="handoffInlinePreview">Handoff ещё не создан.</pre>
          </details>
          <h3>Ход выполнения</h3>
          <div id="timelineBox" class="timeline">
            <div class="timeline-event info"><strong>Ожидаем старт выполнения…</strong><div class="detail">Готовлю managed clone… / Codex выполняет задачу… / Проверяю результат…</div></div>
          </div>
          <h3>Блокер</h3>
          <div id="blockerBox" class="muted">Блокера нет.</div>
          <h3>Production lane wb-core</h3>
          <div class="muted">Явный рабочий режим для wb-core: verifier-passed managed clone -> target lock -> wb-core PR -> merge -> backup -> approved WebCore deploy runner -> probes -> rollback report. Direct push to main is forbidden.</div>
          <div class="actions">
            <button id="productionLanePlanButton" class="secondary" onclick="planProductionLane()">Проверить production lane</button>
          </div>
          <pre id="productionLaneOutput">Production lane plan появится после verifier-passed Codex run.</pre>
          <details>
            <summary>Технические детали (Advanced)</summary>
            <h3>Raw JSON</h3>
            <textarea id="taskSpecInput" spellcheck="false"></textarea>
            <h3>Prompt</h3>
            <pre id="promptPreview">Prompt ещё не создан.</pre>
            <h3>Handoff</h3>
            <pre id="handoffPreview">Handoff ещё не создан.</pre>
            <h3>Diff</h3>
            <pre id="diffPreview">Diff ещё не создан.</pre>
            <h3>Logs / paths</h3>
            <pre id="technicalPaths">Нет данных.</pre>
          </details>
        </section>
      </div>
    </div>
    <div id="tab-connections" class="tab">
      <section>
        <h2>Подключения</h2>
        <div class="connections">
          <div class="panel">
            <h3>OpenAI-куратор</h3>
            <div id="openaiStatus">Проверка...</div>
            <div id="openaiRuntimeControls"></div>
            <button id="openaiTestButton" onclick="testOpenAI()">Проверить OpenAI</button>
            <pre id="openaiTestResult">Проверка ещё не запускалась.</pre>
            <p class="muted">API key не вводится в UI и не сохраняется в state.</p>
            <pre>python3 apps/dev_control_plane_setup.py openai
затем перезапустите cockpit</pre>
          </div>
          <div class="panel">
            <h3>Codex CLI</h3>
            <div id="codexStatus">Проверка...</div>
            <h3>Runtime toolchain</h3>
            <div id="toolchainStatus">Проверка...</div>
            <div id="codexRuntimeControls"></div>
            <button id="runtimeConfigSaveButton" onclick="saveRuntimeConfig()">Сохранить настройки</button>
            <div id="runtimeConfigStatus" class="muted">Настройки не менялись.</div>
            <p class="muted">Login не вводится в UI. Auth проверяется при первом CLI-запуске.</p>
            <pre>codex login
codex login --device-auth
hosted/headless: выполнить device-auth от service user</pre>
          </div>
          <div class="panel">
            <h3>MCP connector</h3>
            <div id="mcpStatus">Проверка...</div>
            <p class="muted">Stage 1 bridge для ChatGPT Developer Mode. Write tools требуют отдельный bearer token; token не отображается и не пишется в логи.</p>
            <pre>POST /mcp
transport: streamable_http</pre>
          </div>
        </div>
      </section>
    </div>
    <div id="tab-technical" class="tab">
      <section>
        <h2>Технические детали</h2>
        <div class="actions">
          <button class="secondary" onclick="loadState()">Обновить state</button>
          <button class="secondary" onclick="saveDraft()">Сохранить raw JSON как draft</button>
          <button class="secondary" onclick="generatePrompt()">Сгенерировать prompt</button>
          <button id="cleanupRunButton" class="secondary" onclick="cleanupRun()">Cleanup run</button>
        </div>
        <h3>Current state summary</h3>
        <pre id="stateSummary">Нет данных.</pre>
        <h3>Runs / prompts / paths</h3>
        <pre id="debugOutput">Нет данных.</pre>
      </section>
    </div>
  </main>
  <script>
    let discussionId = null;
    let taskSpecId = null;
    let currentRunId = null;
    let currentRun = null;
    let selectedTargetProjectId = null;
    let messages = [];
    let sendPending = false;
    let currentTaskSpec = null;
    let connectionsStatus = null;
    let realRunJobId = null;
    let realRunPollTimer = null;

    async function request(path, options = {}) {
      const response = await fetch(path, options);
      const text = await response.text();
      let data = {};
      try {
        data = text ? JSON.parse(text) : {};
      } catch (error) {
        data = {error: text ? text.slice(0, 240) : response.statusText};
      }
      if (!response.ok) throw new Error(data.error || response.statusText);
      return data;
    }

    function sleep(ms) {
      return new Promise((resolve) => setTimeout(resolve, ms));
    }

    async function testOpenAI() {
      const button = document.getElementById('openaiTestButton');
      setActionLoading(button, true, 'Проверяю OpenAI...');
      try {
        setActionStatus('Выполняется: Проверяю OpenAI...', 'running');
        const result = await request('/api/connections/openai-test', {method: 'POST', body: '{}'});
        document.getElementById('openaiTestResult').textContent = formatOpenAITest(result);
        document.getElementById('debugOutput').textContent = JSON.stringify(result, null, 2);
        setActionStatus(result.status === 'ok' ? 'OpenAI работает.' : 'OpenAI вернул диагностируемую ошибку.', result.status === 'ok' ? 'ready' : 'error');
      } catch (error) {
        document.getElementById('openaiTestResult').textContent = String(error);
        setActionStatus('Ошибка проверки OpenAI.', 'error');
        document.getElementById('debugOutput').textContent = String(error);
      } finally {
        setActionLoading(button, false);
      }
    }

    function showTab(name) {
      for (const tab of document.querySelectorAll('.tab')) tab.classList.remove('active');
      for (const button of document.querySelectorAll('nav button')) button.classList.remove('active');
      document.getElementById(`tab-${name}`).classList.add('active');
      document.getElementById(`tab-${name}-button`).classList.add('active');
    }

    async function loadConnections() {
      const data = await request('/api/connections/status');
      let mcp = {};
      try {
        const state = await request('/api/state');
        mcp = state.mcp || {};
      } catch (error) {
        mcp = {enabled: false, endpoint: '/mcp', transport: 'streamable_http', auth: {write_tools: {configured: false}}, last_call: {result_status: String(error)}};
      }
      connectionsStatus = data;
      const openai = data.openai || {};
      const codex = data.codex || {};
      const toolchain = data.toolchain || {};
      document.getElementById('openaiBadge').textContent = `OpenAI-куратор: ${openai.status || 'не подключён'}`;
      document.getElementById('codexBadge').textContent = `Codex CLI: ${codex.status || 'не найден'}`;
      document.getElementById('openaiStatus').innerHTML = statusList([
        ['Статус', openai.status || 'не подключён'],
        ['Источник', openai.source || 'missing'],
        ['Модель', openai.model || 'не задана'],
        ['Reasoning', openai.reasoning_effort || 'не задан'],
        ['Подключён / Не подключён', openai.configured ? 'Подключён' : 'Не подключён'],
        ['Что это значит', openaiStatusText(openai)]
      ]);
      document.getElementById('codexStatus').innerHTML = statusList([
        ['Статус', codex.status || 'не найден'],
        ['Версия', codex.version || 'нет данных'],
        ['Auth', codex.auth_status || 'unknown'],
        ['Модель', codex.model || 'не задана'],
        ['Reasoning', codex.model_reasoning_effort || 'не задан'],
        ['Sandbox', codex.sandbox_mode || 'не задан'],
        ['Config', codex.config_status || 'missing'],
        ['Проверка auth', codex.auth_check_supported ? 'поддерживается' : 'проверяется при первом CLI-запуске'],
        ['UI запуск', data.control_plane?.real_codex_ui_enabled ? 'managed clone only' : 'disabled']
      ]);
      document.getElementById('toolchainStatus').innerHTML = renderToolchainStatus(toolchain);
      document.getElementById('mcpStatus').innerHTML = statusList([
        ['Enabled', mcp.enabled ? 'yes' : 'no'],
        ['Endpoint', mcp.endpoint || '/mcp'],
        ['Transport', mcp.transport || 'streamable_http'],
        ['Auth configured', mcp.auth?.write_tools?.configured ? 'yes' : 'no'],
        ['Tool count', mcp.tool_count ?? 0],
        ['Active runs', mcp.active_runs_count ?? 0],
        ['Last call', mcp.last_call?.result_status || 'none']
      ]);
      renderRuntimeControls(data.runtime_config || {});
      updateActionAvailability();
      return data;
    }

    function renderToolchainStatus(toolchain) {
      const tools = toolchain.tools || [];
      const core = tools.filter((tool) => ['git', 'rg', 'python3', 'python3-venv', 'pip', 'jq', 'node', 'npm', 'corepack', 'pnpm', 'yarn', 'codex'].includes(tool.name));
      const rows = [
        ['Статус', toolchain.status || 'unknown'],
        ['Missing required', (toolchain.missing_required || []).join(', ') || 'нет'],
        ['Warnings', (toolchain.warnings || []).join('; ') || 'нет']
      ];
      const toolRows = core.map((tool) => [
        tool.name,
        `${tool.available ? 'ok' : 'missing'}${tool.path ? ` · ${tool.path}` : ''}${tool.version ? ` · ${tool.version}` : ''}`
      ]);
      return statusList([...rows, ...toolRows]);
    }

    function renderRuntimeControls(runtime) {
      const options = runtime.options || {};
      const openai = runtime.openai || {};
      const codex = runtime.codex || {};
      document.getElementById('openaiRuntimeControls').innerHTML = `
        <label for="openaiModelInput">OpenAI curator model</label>
        <select id="openaiModelInput">${optionHtml(options.openai_models || [], openai.model)}</select>
        <label for="openaiReasoningInput">OpenAI reasoning</label>
        <select id="openaiReasoningInput">${simpleOptionsHtml(options.reasoning_efforts || [], openai.reasoning_effort)}</select>
        <p class="muted">Active: ${escapeHtml(openai.model || 'не задана')} / ${escapeHtml(openai.reasoning_effort || 'не задан')} (${escapeHtml(openai.source || 'default')})</p>
      `;
      document.getElementById('codexRuntimeControls').innerHTML = `
        <label for="codexModelInput">Codex model</label>
        <select id="codexModelInput">${optionHtml(options.codex_models || [], codex.model)}</select>
        <label for="codexReasoningInput">Codex reasoning</label>
        <select id="codexReasoningInput">${simpleOptionsHtml(options.reasoning_efforts || [], codex.reasoning_effort)}</select>
        <label for="codexSandboxInput">Codex sandbox</label>
        <select id="codexSandboxInput">${simpleOptionsHtml(options.codex_sandbox_modes || [], codex.sandbox_mode)}</select>
        <p class="muted">${escapeHtml(codex.sandbox_warning || 'Sandbox mode задан через runtime config/default.')}</p>
      `;
    }

    async function saveRuntimeConfig() {
      const button = document.getElementById('runtimeConfigSaveButton');
      setActionLoading(button, true, 'Сохраняю...');
      try {
        const payload = {
          openai: {
            model: document.getElementById('openaiModelInput')?.value || '',
            reasoning_effort: document.getElementById('openaiReasoningInput')?.value || ''
          },
          codex: {
            model: document.getElementById('codexModelInput')?.value || '',
            reasoning_effort: document.getElementById('codexReasoningInput')?.value || '',
            sandbox_mode: document.getElementById('codexSandboxInput')?.value || ''
          }
        };
        const saved = await request('/api/runtime-config', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify(payload)
        });
        document.getElementById('runtimeConfigStatus').textContent = `Сохранено: ${saved.openai?.model}/${saved.openai?.reasoning_effort}, Codex ${saved.codex?.model}/${saved.codex?.reasoning_effort}.`;
        await loadConnections();
      } catch (error) {
        document.getElementById('runtimeConfigStatus').textContent = String(error);
      } finally {
        setActionLoading(button, false);
      }
    }

    function optionHtml(items, selected) {
      return items.map((item) => {
        const id = item.id || item;
        const label = item.label || id;
        const isSelected = id === selected ? ' selected' : '';
        return `<option value="${escapeHtml(id)}"${isSelected}>${escapeHtml(label)}</option>`;
      }).join('');
    }

    function simpleOptionsHtml(items, selected) {
      return (items || []).map((id) => {
        const isSelected = id === selected ? ' selected' : '';
        return `<option value="${escapeHtml(id)}"${isSelected}>${escapeHtml(id)}</option>`;
      }).join('');
    }

    function openaiStatusText(openai) {
      if (openai.source === 'env') return 'Подключён через переменные окружения.';
      if (openai.source === 'file') return 'Подключён через локальное хранилище.';
      return 'В терминале один раз выполните: python3 apps/dev_control_plane_setup.py openai. Затем перезапустите cockpit.';
    }

    async function loadTargets() {
      const data = await request('/api/target-projects');
      const select = document.getElementById('targetProjectInput');
      select.innerHTML = '<option value="">Без target project</option>';
      for (const target of data.targets || []) {
        const option = document.createElement('option');
        option.value = target.project_id;
        option.textContent = `${target.display_name} (${target.validation_status})`;
        select.appendChild(option);
      }
      if ((data.targets || []).some((target) => target.project_id === 'wb-core')) {
        select.value = 'wb-core';
      }
      selectedTargetProjectId = select.value || null;
      await selectTargetProject();
    }

    async function selectTargetProject() {
      selectedTargetProjectId = document.getElementById('targetProjectInput').value || null;
      updateActionAvailability();
      if (!selectedTargetProjectId) return;
      const data = await request(`/api/target-projects/${selectedTargetProjectId}`);
      document.getElementById('technicalPaths').textContent = JSON.stringify(data.summary || data, null, 2);
    }

    async function addMessage() {
      if (sendPending) return;
      const input = document.getElementById('messageInput');
      const button = document.getElementById('sendButton');
      const content = input.value.trim();
      if (!content) return;
      sendPending = true;
      input.value = '';
      input.disabled = true;
      const pendingId = `local-${Date.now()}`;
      messages.push({id: pendingId, role: 'operator', content, local_status: 'отправляется'});
      messages.push({id: `${pendingId}-typing`, role: 'curator', content: 'Куратор думает', local_status: 'typing'});
      renderMessages();
      setActionLoading(button, true, 'Отправляю...');
      setActionStatus('Выполняется: отправляю сообщение куратору...', 'running');
      try {
        if (!discussionId) {
          const discussion = await request('/api/discussions', {method: 'POST', body: '{}'});
          discussionId = discussion.id;
        }
        const discussion = await request(`/api/discussions/${discussionId}/messages`, {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({role: 'operator', content})
        });
        messages = discussion.messages || [];
        renderMessages();
        setActionStatus('Сообщение отправлено.', 'ready');
      } catch (error) {
        messages = messages.filter((message) => message.id !== `${pendingId}-typing`);
        const own = messages.find((message) => message.id === pendingId);
        if (own) own.local_status = 'ошибка';
        messages.push({
          id: `${pendingId}-error`,
          role: 'curator',
          content: 'Не удалось получить ответ. Попробуйте ещё раз.',
          local_status: 'ошибка',
        });
        renderMessages();
        setActionStatus('Ошибка отправки сообщения.', 'error');
        document.getElementById('debugOutput').textContent = String(error);
      } finally {
        sendPending = false;
        input.disabled = false;
        setActionLoading(button, false);
        input.focus();
      }
    }

    async function draftTaskSpec() {
      const button = document.getElementById('draftButton');
      setActionLoading(button, true, 'Формирую карточку...');
      setActionStatus('Выполняется: формирую карточку задачи...', 'running');
      try {
        if (!discussionId) {
          const discussion = await request('/api/discussions', {method: 'POST', body: '{}'});
          discussionId = discussion.id;
        }
        const job = await request(`/api/discussions/${discussionId}/draft-task-spec-jobs`, {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({target_project_id: selectedTargetProjectId})
        });
        const result = await pollDraftTaskSpecJob(job.id);
        if (result.status !== 'drafted') {
          const reason = result.blocked_reason || result.short_message || 'Карточку задачи не удалось сформировать.';
          renderBlocker({
            status: 'present',
            reason,
            next_manual_step: 'Подключите OpenAI в терминале и перезапустите cockpit.',
            source: 'curator'
          });
          setActionStatus(`Ошибка формирования карточки: ${reason}`, 'error');
          return null;
        }
        taskSpecId = result.task_spec_id;
        currentTaskSpec = result.task_spec;
        document.getElementById('taskSpecInput').value = JSON.stringify(result.task_spec, null, 2);
        renderTaskCard(result.task_spec);
        renderDraftMetrics(result.performance || {});
        const perf = result.performance || {};
        const metricText = perf.total_duration_ms ? ` Модель: ${perf.selected_model || 'n/a'} / ${perf.selected_reasoning_effort || 'n/a'}, ${perf.total_duration_ms} ms.` : '';
        renderResult({status: 'Готово', what: `Карточка задачи сформирована.${metricText}`, next: 'Проверьте карточку и зафиксируйте задачу.'});
        setActionStatus('Карточка задачи сформирована.', 'ready');
        return result.task_spec;
      } catch (error) {
        const reason = error && error.message ? error.message : String(error);
        renderBlocker({status: 'present', reason, next_manual_step: 'Проверьте подключение OpenAI и target status.', source: 'curator'});
        setActionStatus(`Ошибка формирования карточки: ${reason}`, 'error');
        document.getElementById('debugOutput').textContent = String(error);
        return null;
      } finally {
        setActionLoading(button, false);
      }
    }

    async function pollDraftTaskSpecJob(jobId) {
      if (!jobId) throw new Error('draft task card job id is missing');
      const terminalStatuses = new Set(['drafted', 'blocked', 'failed']);
      for (let attempt = 0; attempt < 360; attempt += 1) {
        const job = await request(`/api/draft-task-spec-jobs/${jobId}`);
        const status = job.status || 'unknown';
        document.getElementById('debugOutput').textContent = JSON.stringify({
          job_id: job.id,
          status,
          message: job.message,
          task_spec_id: job.task_spec_id,
          blocked_reason: job.blocked_reason
        }, null, 2);
        if (terminalStatuses.has(status)) {
          return job.result || {
            status,
            task_spec_id: job.task_spec_id,
            blocked_reason: job.blocked_reason,
            errors: job.errors || []
          };
        }
        setActionStatus(`Выполняется: ${job.message || 'формирую карточку задачи'} Статус: ${status}.`, 'running');
        await sleep(2000);
      }
      throw new Error('Формирование карточки не завершилось до клиентского timeout.');
    }

    function renderDraftMetrics(perf) {
      if (!perf || !perf.total_duration_ms) {
        document.getElementById('draftMetrics').textContent = 'Метрики подготовки недоступны.';
        return;
      }
      document.getElementById('draftMetrics').innerHTML = statusList([
        ['Duration total', `${perf.total_duration_ms} ms`],
        ['Target validation', `${perf.target_validation_duration_ms || 0} ms`],
        ['Context build', `${perf.context_build_duration_ms || 0} ms`],
        ['Curator', `${perf.openai_curator_duration_ms || 0} ms`],
        ['Card validation', `${perf.card_validation_duration_ms || 0} ms`],
        ['Model', perf.selected_model || 'n/a'],
        ['Reasoning', perf.selected_reasoning_effort || 'n/a'],
        ['Token estimate', perf.estimated_input_tokens || 'n/a']
      ]);
    }

    async function prepareTask() {
      const button = document.getElementById('prepareTaskButton');
      setActionLoading(button, true, 'Готовлю задачу...');
      setActionStatus('Выполняется: готовлю задачу...', 'running');
      try {
        if (!taskSpecId || !currentTaskSpec) {
          const drafted = await draftTaskSpec();
          if (!drafted || !currentTaskSpec) return;
        }
        if (currentTaskSpec.status === 'frozen') {
          renderResult({status: 'Готово', what: 'Задача уже зафиксирована.', next: 'Можно запускать Codex безопасно.'});
          setActionStatus('Задача готова к запуску Codex.', 'ready');
          return;
        }
        const gates = currentTaskSpec.human_gates || [];
        const risky = currentTaskSpec.task_class === 'L3' || gates.length > 0;
        if (risky) {
          renderResult({status: 'Нужен человек', what: 'Карточка задачи подготовлена и требует подтверждения перед freeze.', next: 'Проверьте карточку. Повторите “Подготовить задачу” и подтвердите freeze, если scope корректен.'});
          if (!confirm('Карточка содержит L3/gates или риск. Зафиксировать задачу после ручной проверки?')) {
            setActionStatus('Карточка подготовлена. Ожидается ручное подтверждение freeze.', 'ready');
            return;
          }
        }
        setActionLoading(button, true, 'Фиксирую задачу...');
        await freezeTask();
      } catch (error) {
        renderBlocker({status: 'present', reason: String(error), next_manual_step: 'Проверьте чат, карточку задачи и подключение OpenAI.', source: 'curator'});
        setActionStatus('Ошибка подготовки задачи.', 'error');
        document.getElementById('debugOutput').textContent = String(error);
      } finally {
        setActionLoading(button, false);
      }
    }

    async function saveDraft() {
      const payload = JSON.parse(document.getElementById('taskSpecInput').value || '{}');
      if (selectedTargetProjectId && !payload.target_project_id) payload.target_project_id = selectedTargetProjectId;
      const saved = await request('/api/task-specs', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload)
      });
      taskSpecId = saved.id;
      currentTaskSpec = saved;
      renderTaskCard(saved);
      return saved;
    }

    async function freezeTask() {
      const button = document.getElementById('freezeButton');
      setActionLoading(button, true, 'Фиксирую задачу...');
      setActionStatus('Выполняется: фиксирую задачу...', 'running');
      try {
        if (!taskSpecId) await saveDraft();
        const result = await request(`/api/task-specs/${taskSpecId}/freeze`, {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: '{}'
        });
        const spec = await request(`/api/task-specs/${taskSpecId}`);
        currentTaskSpec = spec;
        document.getElementById('taskSpecInput').value = JSON.stringify(spec, null, 2);
        renderTaskCard(spec);
        renderResult({status: 'Готово', what: `Задача зафиксирована. Hash: ${result.spec_hash}`, next: 'Можно запускать Codex безопасно.'});
        setActionStatus('Задача зафиксирована.', 'ready');
        return spec;
      } catch (error) {
        renderBlocker({status: 'present', reason: String(error), next_manual_step: 'Проверьте карточку задачи.', source: 'policy'});
        setActionStatus('Ошибка фиксации задачи.', 'error');
        document.getElementById('debugOutput').textContent = String(error);
        return null;
      } finally {
        setActionLoading(button, false);
      }
    }

    async function generatePrompt() {
      const summary = await request(`/api/task-specs/${taskSpecId}/generate-prompt`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: '{}'
      });
      const response = await fetch(`/api/prompts/${summary.id}`);
      document.getElementById('promptPreview').textContent = await response.text();
      document.getElementById('debugOutput').textContent = JSON.stringify(summary, null, 2);
    }

    async function runSafeFakeFlow() {
      const button = document.getElementById('safeFlowButton');
      setActionLoading(button, true, 'Проверяю сценарий...');
      setActionStatus('Выполняется: безопасно проверяю сценарий...', 'running');
      try {
        const summary = await request('/api/guided-safe-fake-run', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({task_spec_id: taskSpecId})
        });
        currentRunId = summary.run_id;
        renderRun(summary);
        await loadRun(currentRunId);
        setActionStatus('Безопасная проверка завершена.', 'ready');
      } catch (error) {
        renderBlocker(executionBlockerFromError(error));
        setActionStatus('Безопасная проверка завершилась ошибкой.', 'error');
        document.getElementById('debugOutput').textContent = String(error);
      } finally {
        setActionLoading(button, false);
      }
    }

    async function runCodexManaged() {
      const button = document.getElementById('codexRunButton');
      if (!taskSpecId) {
        renderBlocker({status: 'present', reason: 'Сначала сформируйте и зафиксируйте карточку задачи.', next_manual_step: 'Нажмите “Подготовить задачу”, затем повторите запуск Codex.', source: 'policy'});
        return;
      }
      if (!confirm('Запустить реальный Codex в managed clone. Оригинальный wb-core не будет изменён. Commit/push/merge/deploy не выполняются.')) {
        return;
      }
      setActionLoading(button, true, 'Запускаю Codex...');
      setActionStatus('Готовлю managed clone...', 'running');
      try {
        const job = await request(`/api/task-specs/${taskSpecId}/run-codex-managed`, {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({target_project_id: selectedTargetProjectId})
        });
        realRunJobId = job.id;
        renderRealCodexJob(job);
        pollRealRunJob(job.id);
      } catch (error) {
        renderBlocker(executionBlockerFromError(error));
        setActionStatus('Codex запуск заблокирован.', 'error');
        document.getElementById('debugOutput').textContent = String(error);
        setActionLoading(button, false);
      }
    }

    function pollRealRunJob(jobId) {
      if (realRunPollTimer) clearTimeout(realRunPollTimer);
      realRunPollTimer = setTimeout(async () => {
        try {
          const job = await request(`/api/real-runs/${jobId}`);
          renderRealCodexJob(job);
          if (['passed', 'failed', 'blocked'].includes(job.status)) {
            setActionLoading(document.getElementById('codexRunButton'), false);
            if (job.run_id) {
              currentRunId = job.run_id;
              await loadRun(job.run_id);
            }
            return;
          }
          pollRealRunJob(jobId);
        } catch (error) {
          setActionLoading(document.getElementById('codexRunButton'), false);
          setActionStatus('Не удалось получить статус Codex run.', 'error');
          document.getElementById('debugOutput').textContent = String(error);
        }
      }, 1200);
    }

    async function loadRun(runId) {
      const run = await request(`/api/runs/${runId}`);
      currentRun = run;
      renderRun(run);
      renderTimeline(run.timeline_events || []);
      document.getElementById('promptPreview').textContent = run.prompt_text || 'Prompt ещё не создан.';
      setPreviewText('handoffPreview', 'handoffInlinePreview', run.handoff_text, 'Handoff ещё не создан.', 160);
      setPreviewText('diffPreview', 'diffInlinePreview', run.diff_text, 'Diff ещё не создан.', 120);
      document.getElementById('technicalPaths').textContent = JSON.stringify({
        run_dir: run.run_dir,
        worktree_path: run.worktree_path,
        workspace_path: run.workspace_path,
        prompt_path: run.prompt_path,
        handoff_path: run.handoff_path,
        log_path: run.log_path,
        diff_path: run.diff_path
      }, null, 2);
    }

    async function planProductionLane() {
      const button = document.getElementById('productionLanePlanButton');
      const output = document.getElementById('productionLaneOutput');
      if (!currentRun) {
        output.textContent = 'Сначала нужен verifier-passed Codex run.';
        return;
      }
      setActionLoading(button, true, 'Проверяю...');
      try {
        const payload = {
          target_project_id: currentRun.target_project_id || currentTaskSpec?.target_project_id || selectedTargetProjectId,
          target_repo: 'orenvlad-ai/wb-core',
          target_repo_url: 'https://github.com/orenvlad-ai/wb-core.git',
          base_branch: 'main',
          execution_mode: 'production_lane',
          apply_mode: 'target_pr_merge_deploy',
          production_lane: true,
          run_id: currentRun.run_id,
          run_dir: currentRun.run_dir,
          workspace_path: currentRun.workspace_path,
          task_spec_id: currentRun.task_spec_id || currentTaskSpec?.id,
          task_summary: currentTaskSpec?.goal || currentTaskSpec?.title || 'DevControl task',
          changed_files: currentRun.changed_files || [],
          verifier_status: currentRun.verifier_status,
          forbidden_path_hits: currentRun.forbidden_path_hits || [],
          secrets_scan_status: 'passed',
          docs_update_status: 'not_required',
          expected_public_label: 'Витрина 2',
          commit_message: `Изменить label Витрина через DevControl (${currentRun.run_id || 'run'})`,
          pr_title: 'Изменить label Витрина через DevControl'
        };
        const plan = await request('/api/target-production/plan', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify(payload)
        });
        output.textContent = JSON.stringify(plan, null, 2);
      } catch (error) {
        output.textContent = String(error);
      } finally {
        setActionLoading(button, false);
      }
    }

    async function cleanupRun() {
      if (!currentRunId) return;
      const button = document.getElementById('cleanupRunButton');
      setActionLoading(button, true, 'Очищаю...');
      setActionStatus('Выполняется: очищаю проверочный запуск...', 'running');
      try {
        const summary = await request(`/api/runs/${currentRunId}/cleanup`, {method: 'POST', body: '{}'});
        document.getElementById('debugOutput').textContent = JSON.stringify(summary, null, 2);
        setActionStatus('Проверочный запуск очищен.', 'ready');
      } catch (error) {
        setActionStatus('Ошибка очистки проверочного запуска.', 'error');
        document.getElementById('debugOutput').textContent = String(error);
      } finally {
        setActionLoading(button, false);
      }
    }

    async function loadState() {
      const state = await request('/api/state');
      document.getElementById('stateSummary').textContent = JSON.stringify(state, null, 2);
    }

    function renderMessages() {
      const root = document.getElementById('chatMessages');
      root.innerHTML = '';
      for (const message of messages) {
        const bubble = document.createElement('div');
        const roleClass = message.role === 'operator' ? 'operator' : (message.role === 'curator' ? 'curator' : 'system');
        const statusClass = message.local_status === 'отправляется' ? 'pending' : (message.local_status === 'ошибка' ? 'error' : '');
        const typingClass = message.local_status === 'typing' ? 'typing pending' : '';
        bubble.className = `bubble ${roleClass} ${statusClass} ${typingClass}`.trim();
        bubble.textContent = message.content || '';
        if (message.local_status && message.local_status !== 'typing') {
          const meta = document.createElement('span');
          meta.className = 'message-meta';
          meta.textContent = message.local_status;
          bubble.appendChild(meta);
        }
        root.appendChild(bubble);
      }
      root.scrollTop = root.scrollHeight;
    }

    function renderTaskCard(spec) {
      currentTaskSpec = spec;
      updateActionAvailability();
      const gates = spec.human_gates || [];
      const targetSummary = spec.target_context_summary || {};
      const targetWarnings = Array.isArray(targetSummary.warnings) ? targetSummary.warnings : [];
      document.getElementById('taskCard').innerHTML = `
        <dl>
          <dt>Название</dt><dd>${escapeHtml(spec.title || '')}</dd>
          <dt>Проект</dt><dd>${escapeHtml(spec.target_project_id || selectedTargetProjectId || 'не выбран')}</dd>
          <dt>Статус target</dt><dd>${escapeHtml(targetSummary.validation_status || 'нет данных')}</dd>
          <dt>Класс задачи</dt><dd>${escapeHtml(spec.task_class || '')}</dd>
          <dt>Цель</dt><dd>${escapeHtml(spec.goal || '')}</dd>
          <dt>Что делаем</dt><dd>${listHtml(spec.scope)}</dd>
          <dt>Что НЕ делаем</dt><dd>${listHtml(spec.not_in_scope)}</dd>
          <dt>Проверки</dt><dd>${listHtml(spec.required_smokes)}</dd>
          <dt>Ограничения</dt><dd>${listHtml([...(spec.forbidden_paths || []), ...(spec.forbidden_actions || [])])}</dd>
          <dt>Где нужен человек</dt><dd>${gates.length ? listHtml(gates) : 'Не требуется'}</dd>
          <dt>Предупреждения target</dt><dd>${targetWarnings.length ? listHtml(targetWarnings) : 'Нет'}</dd>
        </dl>`;
    }

    function renderRun(run) {
      const view = run.run_result_summary || {};
      const isRealCodex = run.codex_exit_code !== undefined && run.codex_exit_code !== null || Boolean(run.workspace_path);
      const handoffContractError = String(run.blocker_reason || '').includes('handoff contract');
      renderResult({
        status: handoffContractError ? 'Ошибка формата отчёта Codex' : translateStatus(view.status || run.status),
        what: view.status === 'Passed' || run.status === 'verifier_passed'
          ? (isRealCodex ? 'Codex выполнил задачу в managed clone. Оригинальный target repo не менялся.' : 'Безопасная проверка прошла. Реальный Codex не запускался.')
          : (run.blocker_reason || 'Проверка завершилась неуспешно.'),
        next: run.next_manual_step || (view.status === 'Passed' ? 'Проверьте diff/handoff/verifier report перед любым будущим apply/PR flow.' : 'Посмотрите блокер.')
      });
      renderBlocker(run.blocker || (run.blocker_reason ? {
        status: 'present',
        reason: run.blocker_reason,
        next_manual_step: run.next_manual_step,
        source: 'verifier'
      } : {status: 'none'}));
      renderExecutionSummary(run);
      document.getElementById('debugOutput').textContent = JSON.stringify(run, null, 2);
    }

    function renderRealCodexJob(job) {
      const handoffContractError = String(job.blocker_reason || '').includes('handoff contract');
      const status = handoffContractError ? 'Ошибка формата отчёта Codex' : translateRealJobStatus(job.status);
      const changed = Array.isArray(job.changed_files) ? job.changed_files : [];
      renderResult({
        status,
        what: `${job.message || 'Codex job обновлён.'}${changed.length ? ` Изменённые файлы: ${changed.join(', ')}.` : ''}`,
        next: job.status === 'passed'
          ? 'Проверьте diff/handoff/verifier report в технических деталях.'
          : (job.next_manual_step || 'Дождитесь завершения или проверьте блокер.')
      });
      renderBlocker(job.blocker || (job.blocker_reason ? {
        status: 'present',
        reason: job.blocker_reason,
        next_manual_step: job.next_manual_step,
        source: 'execution'
      } : {status: 'none'}));
      renderExecutionSummary(job);
      renderTimeline(job.timeline_events || []);
      setActionStatus(`${status}: ${job.message || ''}`, ['failed', 'blocked'].includes(job.status) ? 'error' : (job.status === 'passed' ? 'ready' : 'running'));
      document.getElementById('technicalPaths').textContent = JSON.stringify({
        job_id: job.id,
        run_id: job.run_id,
        target_project_id: job.target_project_id,
        workspace_path: job.workspace_path,
        prompt_path: job.prompt_path,
        handoff_path: job.handoff_path,
        log_path: job.log_path,
        diff_path: job.diff_path,
        verifier_status: job.verifier_status,
        changed_files: changed,
        original_target_unchanged: job.original_target_unchanged
      }, null, 2);
      document.getElementById('debugOutput').textContent = JSON.stringify(job, null, 2);
    }

    function renderTimeline(events) {
      const root = document.getElementById('timelineBox');
      if (!root) return;
      const visibleEvents = Array.isArray(events) ? events.slice(-12) : [];
      if (!visibleEvents.length) {
        root.innerHTML = '<div class="timeline-event info"><strong>Ожидаем старт выполнения…</strong><div class="detail">Готовлю managed clone… / Codex выполняет задачу… / Проверяю результат…</div></div>';
        return;
      }
      root.innerHTML = visibleEvents.map((event) => {
        const level = ['info', 'success', 'warning', 'error'].includes(event.level) ? event.level : 'info';
        const detail = event.detail ? `<div class="detail">${escapeHtml(event.detail)}</div>` : '';
        return `<div class="timeline-event ${level}"><strong>${escapeHtml(event.title || '')}</strong>${detail}</div>`;
      }).join('');
      root.scrollTop = root.scrollHeight;
    }

    function renderResult(result) {
      document.getElementById('resultBox').innerHTML = `
        <strong>${escapeHtml(result.status || 'Готово')}</strong>
        <p>${escapeHtml(result.what || '')}</p>
        <p><strong>Что делать дальше:</strong> ${escapeHtml(result.next || 'Нет следующего шага.')}</p>`;
    }

    function renderExecutionSummary(source) {
      const view = source.run_result_summary || {};
      const changed = Array.isArray(source.changed_files) ? source.changed_files : (Array.isArray(view.changed_files) ? view.changed_files : []);
      const targetProject = source.target_project_id || view.target_project_id || currentTaskSpec?.target_project_id || selectedTargetProjectId || 'target project';
      const originalUnchanged = source.original_target_unchanged ?? view.original_target_unchanged;
      const originalLabel = originalUnchanged === true
        ? `${targetProject} не изменён`
        : (originalUnchanged === false ? `${targetProject}: есть риск изменения original repo` : 'Не применимо для fake-run');
      const verifierStatus = source.verifier_status || view.verifier_status || 'нет данных';
      const gitDiffStatus = checkStatus(source.check_results, 'git_diff_check') || view.git_diff_check_status || 'нет данных';
      const changedList = changed.length
        ? `<ul class="card-list">${changed.map((path) => `<li>${escapeHtml(path)}</li>`).join('')}</ul>`
        : 'Изменённых файлов нет';
      const nextStep = source.next_manual_step || view.next_manual_step || 'Проверьте diff/handoff перед будущим применением изменений';
      document.getElementById('resultSummaryBox').innerHTML = `
        <dl>
          <dt>Статус</dt><dd>${escapeHtml(translateStatus(view.status || source.status || source.verifier_status))}</dd>
          <dt>Изменённые файлы</dt><dd>${changedList}</dd>
          <dt>Количество изменений</dt><dd>${escapeHtml(String(view.changed_files_count ?? source.changed_files_count ?? changed.length))}</dd>
          <dt>Оригинальный проект</dt><dd>${escapeHtml(originalLabel)}</dd>
          <dt>Проверка</dt><dd>verifier ${escapeHtml(verifierStatus)}; git diff --check ${escapeHtml(gitDiffStatus)}</dd>
          <dt>Следующее действие</dt><dd>${escapeHtml(nextStep)}</dd>
        </dl>
        <div class="actions">
          <button class="secondary" onclick="showInlineDiff()">Показать diff</button>
          <button class="secondary" onclick="showInlineHandoff()">Показать handoff</button>
        </div>`;
    }

    function checkStatus(checks, name) {
      if (!Array.isArray(checks)) return null;
      const found = checks.find((check) => check && check.name === name);
      return found ? (found.status || null) : null;
    }

    function setPreviewText(primaryId, inlineId, text, fallback, maxLines) {
      const preview = compactPreview(text || '', fallback, maxLines);
      const primary = document.getElementById(primaryId);
      const inline = document.getElementById(inlineId);
      if (primary) primary.textContent = preview;
      if (inline) inline.textContent = preview;
    }

    function compactPreview(text, fallback, maxLines) {
      if (!text) return fallback;
      const lines = String(text).split('\\n');
      if (lines.length <= maxLines) return text;
      return `${lines.slice(0, maxLines).join('\\n')}\\n\\nПоказаны первые ${maxLines} строк. Полный artifact доступен по path в технических деталях.`;
    }

    function showInlineDiff() {
      const details = document.getElementById('diffInlineDetails');
      if (details) {
        details.open = true;
        details.scrollIntoView({block: 'nearest'});
      }
    }

    function showInlineHandoff() {
      const details = document.getElementById('handoffInlineDetails');
      if (details) {
        details.open = true;
        details.scrollIntoView({block: 'nearest'});
      }
    }

    function renderBlocker(blocker) {
      if (!blocker || blocker.status === 'none') {
        document.getElementById('blockerBox').textContent = 'Блокера нет.';
        return;
      }
      document.getElementById('blockerBox').innerHTML = `
        <strong>Блокер</strong>
        <p>${escapeHtml(blocker.reason || '')}</p>
        <p><strong>Что делать дальше:</strong> ${escapeHtml(blocker.next_manual_step || 'Проверьте технические детали.')}</p>
        <p class="muted">Источник: ${escapeHtml(blocker.source || 'unknown')}</p>`;
    }

    function setActionLoading(button, isLoading, loadingText) {
      if (!button) return;
      if (isLoading) {
        if (!button.dataset.originalText) button.dataset.originalText = button.textContent;
        button.dataset.loading = 'true';
        button.disabled = true;
        button.innerHTML = `<span class="spinner"></span>${escapeHtml(loadingText || 'Выполняется...')}`;
      } else {
        button.dataset.loading = 'false';
        button.disabled = false;
        button.textContent = button.dataset.originalText || button.textContent;
        updateActionAvailability();
      }
    }

    function setActionStatus(message, kind = 'ready') {
      const node = document.getElementById('actionStatus');
      if (!node) return;
      node.textContent = message || 'Готов к работе.';
      node.className = `action-status ${kind === 'running' ? 'running' : (kind === 'error' ? 'error' : '')}`;
    }

    function updateActionAvailability() {
      const button = document.getElementById('codexRunButton');
      if (!button || button.dataset.loading === 'true') return;
      const codexInstalled = Boolean(connectionsStatus?.codex?.installed);
      const frozen = currentTaskSpec?.status === 'frozen';
      const hasTarget = Boolean(currentTaskSpec?.target_project_id || selectedTargetProjectId);
      button.disabled = !(codexInstalled && frozen && hasTarget);
      button.title = button.disabled
        ? 'Нужны frozen task spec, выбранный target project и установленный Codex CLI.'
        : 'Запустить real Codex в managed clone.';
    }

    function executionBlockerFromError(error) {
      const reason = String(error).replace(/^Error:\\s*/, '');
      if (reason.includes('В карточке задачи не найден шаг запуска')) {
        return {
          status: 'present',
          reason,
          next_manual_step: 'Пересформируйте карточку или сохраните карточку с шагом запуска',
          source: 'execution'
        };
      }
      if (reason.includes('Сначала зафиксируйте задачу') || reason.includes('requires a frozen task spec')) {
        return {
          status: 'present',
          reason: 'Сначала зафиксируйте задачу',
          next_manual_step: 'Зафиксируйте карточку задачи и повторите безопасную проверку.',
          source: 'policy'
        };
      }
      return {
        status: 'present',
        reason,
        next_manual_step: 'Проверьте технические детали.',
        source: 'execution'
      };
    }

    function translateStatus(status) {
      if (status === 'Passed' || status === 'verifier_passed') return 'Готово';
      if (status === 'Blocked' || status === 'blocked') return 'Блокер';
      if (status === 'Failed' || status === 'failed') return 'Ошибка';
      if (status === 'Human gate required' || status === 'human_gate_required') return 'Нужен человек';
      if (status === 'passed') return 'Готово';
      if (status === 'prepared') return 'Подготовлено';
      if (status === 'queued') return 'В очереди';
      if (status === 'preparing') return 'Готовлю managed clone';
      if (status === 'running_codex') return 'Codex выполняет задачу';
      if (status === 'verifying') return 'Проверяю результат';
      return status || 'Готово';
    }

    function translateRealJobStatus(status) {
      if (status === 'queued') return 'В очереди';
      if (status === 'preparing') return 'Готовлю managed clone';
      if (status === 'running_codex') return 'Codex выполняет задачу';
      if (status === 'verifying') return 'Проверяю результат';
      if (status === 'passed') return 'Готово';
      if (status === 'blocked') return 'Блокер';
      if (status === 'failed') return 'Ошибка';
      return status || 'Готово';
    }

    function statusList(items) {
      return `<dl>${items.map(([key, value]) => `<dt>${escapeHtml(key)}</dt><dd>${escapeHtml(String(value ?? ''))}</dd>`).join('')}</dl>`;
    }

    function formatOpenAITest(result) {
      if (result.status === 'ok') {
        return `OpenAI работает\nМодель: ${result.model || 'не задана'}\nReasoning: ${result.reasoning_effort || 'не задан'}\nЧто дальше: ${result.suggested_next_step || 'Можно вернуться в чат.'}`;
      }
      return [
        `Ошибка: ${result.message || 'OpenAI недоступен'}`,
        `Тип: ${result.error_type || 'unknown_error'}`,
        `HTTP: ${result.http_status || 'нет'}`,
        `Request ID: ${result.request_id || 'нет'}`,
        `Что делать дальше: ${result.suggested_next_step || 'Проверьте настройки OpenAI.'}`
      ].join('\\n');
    }

    function listHtml(items) {
      if (!Array.isArray(items) || items.length === 0) return 'Не указано';
      return `<ul class="card-list">${items.map((item) => `<li>${escapeHtml(String(item))}</li>`).join('')}</ul>`;
    }

    function escapeHtml(value) {
      return String(value)
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#039;');
    }

    document.getElementById('messageInput').addEventListener('keydown', (event) => {
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        if (!sendPending) addMessage();
      }
    });

    loadConnections().catch((error) => { document.getElementById('openaiBadge').textContent = String(error); });
    loadTargets().catch((error) => { document.getElementById('technicalPaths').textContent = String(error); });
    loadState().catch(() => {});
  </script>
</body>
</html>"""


def _route_path(raw_path: str) -> str:
    return urlparse(raw_path).path


def _live_run_sort_key(run: Mapping[str, Any]) -> tuple[int, str, str]:
    activity = str(run.get("effective_activity") or "")
    active_rank = 0 if activity == "running" or run.get("active") else 1
    timestamp = str(run.get("effective_recency_at") or run.get("last_activity_at") or run.get("updated_at") or run.get("created_at") or "")
    return (active_rank, -_timestamp_sort_value(timestamp), str(run.get("run_id") or ""))


def _timestamp_sort_value(value: Any) -> float:
    text = str(value or "").strip()
    if not text:
        return 0.0
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _run_type_from_execution_mode(mode: Any) -> str:
    text = str(mode or "")
    if "sprint" in text:
        return "sprint"
    if "production" in text:
        return "production"
    if "managed" in text:
        return "managed"
    return "run"


def _live_payload_is_terminal(payload: Mapping[str, Any]) -> bool:
    run = payload.get("run")
    if not isinstance(run, Mapping):
        return False
    return str(run.get("status") or "") in TERMINAL_LIVE_STATUSES or run.get("active") is False


def _sse_payload_signature(payload: Mapping[str, Any]) -> str:
    compact = {
        "run": payload.get("run"),
        "active_count": payload.get("active_count"),
        "runs": [
            {
                "run_id": item.get("run_id"),
                "status": item.get("status"),
                "stage": item.get("current_stage"),
                "updated_at": item.get("updated_at"),
            }
            for item in payload.get("runs", [])
            if isinstance(item, Mapping)
        ],
        "timeline_last": _last_event_id(payload.get("timeline")),
        "log_next_offset": (payload.get("log_tail") or {}).get("next_offset") if isinstance(payload.get("log_tail"), Mapping) else None,
        "handoff": bool(payload.get("handoff")),
    }
    return json.dumps(compact, ensure_ascii=False, sort_keys=True)


def _last_event_id(events: Any) -> str | None:
    if isinstance(events, list) and events:
        last = events[-1]
        if isinstance(last, Mapping):
            return str(last.get("id") or "")
    return None


def _reverse_sort_text(value: str) -> str:
    return "".join(chr(0x10FFFF - ord(char)) for char in value)


def _split_path(path: str) -> list[str]:
    return [unquote(part) for part in path.split("/") if part]


def _query_value(query: Mapping[str, list[str]], key: str) -> str | None:
    value = (query.get(key) or [""])[0].strip()
    return value or None


def _read_json(path: Path) -> Mapping[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise BadRequestError("JSON root must be an object")
    return payload


def _run_git_server(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(("git", *args), cwd=cwd, capture_output=True, text=True, check=False, env=runtime_command_env(os.environ))


def _git_stdout_server(cwd: Path, *args: str) -> str:
    result = _run_git_server(cwd, *args)
    if result.returncode != 0:
        raise BadRequestError(_safe_completed_output(result) or f"git {' '.join(args)} failed")
    return result.stdout.strip()


def _safe_completed_output(result: subprocess.CompletedProcess[str]) -> str:
    text = "\n".join(part for part in (str(result.stdout or "").strip(), str(result.stderr or "").strip()) if part)
    text = sanitize_terminal_text(text)
    text = text.replace(os.environ.get("OPENAI_API_KEY", "") or "\0", "[redacted]")
    return text[-2000:]


def _safe_text(value: Any) -> str:
    return sanitize_terminal_text(str(value or ""))[:1000]


def _joined_blockers(payload: Mapping[str, Any]) -> str:
    blockers = payload.get("blockers")
    if isinstance(blockers, list):
        return "; ".join(str(item) for item in blockers if str(item).strip())
    if isinstance(blockers, tuple):
        return "; ".join(str(item) for item in blockers if str(item).strip())
    return str(payload.get("blocker") or payload.get("status") or "").strip()


def _selected_promotion_conflict_files(text: str) -> list[str]:
    sanitized = sanitize_terminal_text(str(text or ""))
    if not _selected_promotion_has_conflict(sanitized):
        return []
    files: list[str] = []
    for line in sanitized.splitlines():
        stripped = line.strip()
        if stripped.startswith("U "):
            files.append(stripped[2:].strip())
            continue
        match = re.search(r"['\"]([^'\"]+)['\"]\s+with conflicts", stripped, flags=re.I)
        if match:
            files.append(match.group(1).strip())
    return list(dict.fromkeys(path for path in files if path))


def _selected_promotion_has_conflict(text: str) -> bool:
    lowered = str(text or "").lower()
    return any(
        token in lowered
        for token in (
            "selected managed run diff does not apply cleanly",
            "selected managed run regenerated diff does not apply cleanly",
        )
    )


def _refresh_candidate_recommendation() -> str:
    return "Пересобрать: запустите Refresh candidate, чтобы пересобрать изменения поверх текущего main."


def _conflict_operator_reason(conflict_files: Sequence[str], blocker: Any) -> str:
    files = [str(item) for item in conflict_files if str(item).strip()]
    if files:
        return (
            "Задача была готова, но main изменился после выкладки других задач. "
            f"Конфликт в файле {files[0]}. {_refresh_candidate_recommendation()}"
        )
    raw = sanitize_terminal_text(str(blocker or "")).strip()
    if raw:
        return (
            "Задача была готова, но main изменился после выкладки других задач. "
            f"{raw[:500]} {_refresh_candidate_recommendation()}"
        )
    return "Задача была готова, но main изменился после выкладки других задач. " + _refresh_candidate_recommendation()


def _reconcile_legacy_conflict_group(group: Mapping[str, Any]) -> dict[str, Any] | None:
    blocker = _joined_blockers(group)
    parsed_files = _selected_promotion_conflict_files(blocker)
    stored_files = [str(item) for item in group.get("conflict_files") or [] if str(item).strip()]
    conflict_files = list(dict.fromkeys([*stored_files, *parsed_files]))
    if not conflict_files and not _selected_promotion_has_conflict(blocker):
        return None

    per_task = {
        str(key): str(value)
        for key, value in (group.get("per_task_status") or {}).items()
        if str(key)
    } if isinstance(group.get("per_task_status"), Mapping) else {}
    selected_ids = [str(item) for item in group.get("selected_ids") or [] if str(item)]
    planned_order = [str(item) for item in group.get("planned_order") or [] if str(item)]
    child_ids = list(dict.fromkeys([*planned_order, *selected_ids, *per_task.keys()]))
    conflicted_ids = [str(item) for item in group.get("conflicted_ids") or [] if str(item)]
    refresh_required_ids = [str(item) for item in group.get("refresh_required_ids") or [] if str(item)]
    deferred_ids = [str(item) for item in group.get("deferred_task_ids") or [] if str(item)]
    if (
        per_task
        and all(str(status) == "production_complete" for status in per_task.values())
        and not conflicted_ids
        and not refresh_required_ids
        and not deferred_ids
    ):
        timestamp = _now_utc()
        updates = {
            "status": "production_complete",
            "current_step": "production_complete",
            "blocker": None,
            "conflict_files": [],
            "conflict_reason_by_task": {},
            "recommended_action": None,
            "finished_at": group.get("finished_at") or timestamp,
            "updated_at": timestamp,
        }
        return updates if any(group.get(key) != value for key, value in updates.items()) else None

    conflict_child = ""
    for child_id in conflicted_ids:
        if child_id in child_ids or child_id in per_task:
            conflict_child = child_id
            break
    if not conflict_child:
        for wanted in ("production_lane_running", "promotion_running", "auto_promoting_first"):
            conflict_child = next((child_id for child_id in child_ids if per_task.get(child_id) == wanted), "")
            if conflict_child:
                break
    if not conflict_child:
        conflict_child = next((child_id for child_id in child_ids if per_task.get(child_id) != "production_complete"), "")

    updated_per_task = dict(per_task)
    if conflict_child and updated_per_task.get(conflict_child) != "blocked_by_operator":
        updated_per_task[conflict_child] = "ready_for_separate_deploy"
    if conflict_child and conflict_child not in conflicted_ids:
        conflicted_ids.append(conflict_child)

    had_success = any(
        str(status) == "production_complete"
        for child_id, status in updated_per_task.items()
        if child_id != conflict_child
    ) or bool(group.get("production_run_ids") or group.get("pr_urls") or group.get("merge_commits"))
    group_status = "partially_deployed" if had_success else "ready_for_separate_deploy"
    timestamp = _now_utc()
    blocker_text = _conflict_operator_reason(conflict_files, blocker)
    updates: dict[str, Any] = {
        "status": group_status,
        "current_step": "partially_deployed" if had_success else "ready_for_separate_deploy",
        "blocker": None,
        "conflict_files": conflict_files,
        "conflicted_ids": conflicted_ids,
        "deferred_task_ids": list(dict.fromkeys([*(group.get("deferred_task_ids") or []), *conflicted_ids])),
        "conflict_reason_by_task": {
            **(dict(group.get("conflict_reason_by_task") or {}) if isinstance(group.get("conflict_reason_by_task"), Mapping) else {}),
            **({conflict_child: blocker_text} if conflict_child else {}),
        },
        "refresh_required_ids": refresh_required_ids,
        "recommended_action": group.get("recommended_action") or "Запустите отдельный Merge & Deploy для deferred-задач.",
        "updated_at": timestamp,
        "finished_at": group.get("finished_at") or timestamp,
    }
    if updated_per_task:
        updates["per_task_status"] = updated_per_task

    changed = False
    for key, value in updates.items():
        if group.get(key) != value:
            changed = True
            break
    return updates if changed else None


def _read_run_artifact_preview(run_dir: Path, path: Any, limit: int = 20000) -> str | None:
    if not path:
        return None
    text_path = Path(str(path)).resolve()
    if not _is_relative_to(text_path, run_dir.resolve()):
        raise BadRequestError(f"run artifact path is outside run dir: {text_path}")
    if not text_path.exists():
        return None
    text = text_path.read_text(encoding="utf-8")
    return sanitize_terminal_text(text[:limit])


def _select_step(steps, step_id: str):
    for step in steps:
        if step.id == step_id:
            return step
    raise BadRequestError(RUNNABLE_STEP_MISSING_MESSAGE)


def _new_id(prefix: str, existing: Mapping[str, Any]) -> str:
    index = len(existing) + 1
    while f"{prefix}-{index:03d}" in existing:
        index += 1
    return f"{prefix}-{index:03d}"


def _now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso_utc(value: str) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _human_task_title(value: Any) -> str:
    text = sanitize_terminal_text(str(value or "")).replace("\n", " ").strip()
    text = " ".join(text.split())
    for prefix in (
        "Класс задачи:",
        "Задача:",
        "Task:",
        "Goal:",
        "Operator note:",
        "MCP fake prompt",
    ):
        if text.startswith(prefix):
            text = text[len(prefix) :].strip()
    stopwords = {"и", "или", "в", "на", "для", "по", "and", "or", "the", "a", "to", "of", "for"}
    words = [
        word.strip(".,;:!?()[]{}\"'`")
        for word in text.split()
        if word.strip(".,;:!?()[]{}\"'`") and word.strip(".,;:!?()[]{}\"'`").lower() not in stopwords
    ]
    if not words:
        return "Задача"
    title = " ".join(words[:5])
    if len(title) > 64:
        title = title[:61].rstrip() + "..."
    return title


def _public_base_url() -> str:
    return str(os.environ.get("DEV_CONTROL_PLANE_PUBLIC_ORIGIN") or "https://devcontrol.pro").rstrip("/")


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _int_or_default(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _optional_mapping(value: Any) -> Mapping[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise BadRequestError("existing_task_spec must be an object when provided")
    return value


def _bool_from_payload(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _required_payload_str(payload: Mapping[str, Any], key: str) -> str:
    value = str(payload.get(key) or "").strip()
    if not value:
        raise BadRequestError(f"{key} is required")
    return value


def _safe_messages(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    messages: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        messages.append(
            {
                "role": str(item.get("role") or "operator"),
                "content": str(item.get("content") or ""),
            }
        )
    return messages


def _json_ready(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    return value


def _sanitize_parallel_payload(value: Any) -> Any:
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if any(marker in key_text.lower() for marker in ("secret", "token", "password", "authorization", "cookie", "env")):
                result[key_text] = "[redacted]"
            else:
                result[key_text] = _sanitize_parallel_payload(item)
        return result
    if isinstance(value, list):
        return [_sanitize_parallel_payload(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_parallel_payload(item) for item in value]
    if isinstance(value, str):
        return sanitize_terminal_text(value)
    return value


def _sanitize_parallel_input_text(value: str) -> str:
    return sanitize_terminal_text(value).strip()


def _sanitize_optional_parallel_input_text(value: Any) -> str | None:
    if value is None:
        return None
    text = _sanitize_parallel_input_text(str(value))
    return text or None


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (str, bytes)):
        return [_sanitize_parallel_input_text(str(value))]
    if isinstance(value, list) or isinstance(value, tuple):
        return [_sanitize_parallel_input_text(str(item)) for item in value if str(item or "").strip()][:200]
    return [_sanitize_parallel_input_text(str(value))]


def _unique_strings(values: Sequence[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        result.append(text)
        seen.add(text)
    return result


def _indexed(value: Any, index: int) -> Any:
    if index < 0:
        return None
    if isinstance(value, (list, tuple)):
        return value[index] if index < len(value) else None
    return None


def _parallel_status_from_run_status(value: Any) -> str:
    status = str(value or "").strip().lower()
    if status in {
        "queued",
        "preparing",
        "running",
        "running_codex",
        "managed_run_running",
        "verifying",
    }:
        return "running"
    if status in {"passed", "success", "succeeded", "completed", "complete"}:
        return "passed"
    if status in {"blocked", "stale_timeout", "stale_lost_process", "cancelled", "canceled"}:
        return "blocked"
    if status in {"failed", "error", "errored"}:
        return "failed"
    return status or "blocked"


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


if __name__ == "__main__":
    raise SystemExit(main())
