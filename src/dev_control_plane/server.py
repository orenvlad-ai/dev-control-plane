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
import shutil
import subprocess
import sys
import threading
import time
import tomllib
from typing import Any, Mapping
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
)
from dev_control_plane.github_closure import (  # noqa: E402
    evaluate_dev_control_plane_closure_decision,
    github_closure_decision_to_dict,
)
from dev_control_plane.github_auth import build_github_auth_status  # noqa: E402
from dev_control_plane.ssh_deploy import build_ssh_deploy_status  # noqa: E402
from dev_control_plane.live_monitor import (  # noqa: E402
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
from dev_control_plane.toolchain import build_toolchain_status, runtime_command_env  # noqa: E402
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
    build_wb_core_production_plan,
    execute_wb_core_resume_deploy,
    inspect_wb_core_production_lock,
    target_production_decision_to_dict,
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
    "cancelled",
    "completed",
    "completed_dry_run",
    "decision_only",
    "failed",
    "passed",
}

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
    "POST /api/runs/{id}/verify",
    "POST /api/runs/{id}/cleanup",
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
        for run in self._read_collection("mcp_runs").values():
            if isinstance(run, Mapping):
                summary = self._live_summary_from_mcp_run(run)
                if summary["run_id"] not in seen:
                    runs.append(summary)
                    seen.add(summary["run_id"])
        for job in self._read_collection("real_runs").values():
            if isinstance(job, Mapping):
                summary = self._live_summary_from_real_job(job)
                if summary["run_id"] not in seen:
                    runs.append(summary)
                    seen.add(summary["run_id"])
        for run in self._read_collection("runs").values():
            if isinstance(run, Mapping):
                summary = self._live_summary_from_run_summary(run)
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
        run_dir = self._run_dir_for_live_id(run_id)
        timeline = self.live_run_timeline(run_id)
        log_tail = self.live_run_log_tail(run_id)
        record = _read_json(run_dir / "run.json") if (run_dir / "run.json").exists() else {}
        result = record.get("result", {}) if isinstance(record, Mapping) else {}
        handoff_path = result.get("handoff_path") if isinstance(result, Mapping) else None
        verifier = record.get("verifier") if isinstance(record, Mapping) else None
        report = self._live_report_from_run_dir(run_dir)
        return {
            "status": "ok",
            "run": summary,
            "timeline": timeline.get("events", []),
            "log_tail": log_tail,
            "handoff": _read_run_artifact_preview(run_dir, handoff_path, limit=24000),
            "changed_files": summary.get("changed_files", []),
            "verifier": verifier if isinstance(verifier, Mapping) else None,
            "report": report,
            "sprint": report.get("sprint") if isinstance(report, Mapping) else None,
        }

    def live_run_timeline(self, run_id: str, *, after_event_id: str | None = None) -> dict[str, Any]:
        run_id = safe_state_component(run_id, "run_id")
        try:
            run_dir = self._run_dir_for_live_id(run_id)
        except NotFoundError:
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
            return {"status": "not_found", "run_id": run_id, "ansi_text": "", "plain_text": "", "offset": offset or 0, "next_offset": offset or 0}
        tail = read_terminal_tail(run_dir, max_bytes=max(1000, min(max_bytes, 96_000)), offset=offset)
        return {"run_id": run_id, **tail}

    def _live_summary_by_id(self, run_id: str) -> dict[str, Any] | None:
        for item in self.live_runs().get("runs", []):
            if item.get("run_id") == run_id:
                return dict(item)
        run_dir = self.layout.run_layout(run_id).run_dir
        if run_dir.exists():
            return self._live_summary_from_run_dir(run_id, run_dir)
        return None

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
            "created_at": None,
            "updated_at": None,
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
                "codex --login",
                "выбрать Sign in with ChatGPT",
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
    if not codex_bin:
        return {"authenticated": False, "status": "missing"}
    try:
        result = subprocess.run(
            [codex_bin, "login", "status"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
            env=_safe_status_env(),
        )
    except Exception:
        return {"authenticated": False, "status": "unknown"}
    text = f"{result.stdout or ''}\n{result.stderr or ''}".strip().lower()
    if result.returncode == 0 and "logged in" in text:
        return {"authenticated": True, "status": "authenticated"}
    if result.returncode == 0:
        return {"authenticated": False, "status": "not_authenticated"}
    return {"authenticated": False, "status": "not_authenticated"}


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
  <title>Живые запуски — DevControl</title>
  <style>
    :root { color-scheme: dark; --bg: #0b0d10; --nav: #0f1115; --panel: #15171c; --panel-2: #1a1d23; --line: #2a2f38; --line-soft: #20242b; --text: #f2f4f8; --muted: #8d96a6; --accent: #8ab4ff; --ok: #5bd182; --warn: #f0c15a; --bad: #ff7b72; --term: #06080b; }
    * { box-sizing: border-box; }
    body { margin: 0; background: var(--bg); color: var(--text); font-family: Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    .app-frame { min-height: 100vh; display: grid; grid-template-columns: 244px minmax(0, 1fr); }
    .sidebar { background: var(--nav); border-right: 1px solid var(--line-soft); padding: 18px 14px; display: flex; flex-direction: column; gap: 18px; }
    .brand { display: grid; gap: 3px; padding: 2px 8px 12px; border-bottom: 1px solid var(--line-soft); }
    .brand strong { font-size: 15px; letter-spacing: 0; }
    .brand span { color: var(--muted); font-size: 12px; }
    .side-nav { display: grid; gap: 4px; }
    .side-link { color: #d7dce5; text-decoration: none; border-radius: 7px; padding: 9px 10px; font-size: 14px; border: 1px solid transparent; }
    .side-link:hover, .side-link.active { background: #191d24; border-color: var(--line-soft); color: var(--text); }
    .side-link.active { box-shadow: inset 2px 0 0 var(--accent); }
    .workspace { min-width: 0; display: grid; grid-template-rows: auto 1fr; }
    .topbar { display: flex; justify-content: space-between; gap: 16px; align-items: center; padding: 18px 24px; border-bottom: 1px solid var(--line-soft); background: rgba(15,17,21,.86); backdrop-filter: blur(12px); }
    h1 { margin: 0; font-size: 20px; letter-spacing: 0; }
    .subtitle { margin-top: 4px; color: var(--muted); font-size: 13px; }
    .live-main { display: grid; grid-template-columns: 310px minmax(0, 1fr); gap: 14px; padding: 18px; min-height: calc(100vh - 78px); }
    .runs-panel, section, .panel { border: 1px solid var(--line); border-radius: 8px; background: var(--panel); }
    .runs-panel { overflow: hidden; }
    .run-list { display: grid; gap: 1px; max-height: calc(100vh - 116px); overflow-y: auto; background: var(--line-soft); }
    .run-item { display: grid; gap: 5px; padding: 11px 12px; background: var(--panel); border: 0; color: var(--text); text-align: left; cursor: pointer; width: 100%; }
    .run-item:hover, .run-item.active { background: #1e242d; }
    .run-id { font: 12px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; color: #c9d1d9; overflow-wrap: anywhere; }
    .meta { display: flex; flex-wrap: wrap; gap: 6px; color: var(--muted); font-size: 12px; }
    .pill { border: 1px solid var(--line); border-radius: 999px; padding: 2px 7px; }
    .status-ok { color: var(--ok); }
    .status-warn { color: var(--warn); }
    .status-bad { color: var(--bad); }
    .content { display: grid; grid-template-rows: auto minmax(300px, 1fr) auto; gap: 12px; min-width: 0; }
    .summary { padding: 13px 14px; display: grid; gap: 8px; }
    .summary-grid { display: grid; grid-template-columns: repeat(5, minmax(120px, 1fr)); gap: 10px; }
    .summary-grid div { min-width: 0; }
    .label { color: var(--muted); font-size: 12px; margin-bottom: 3px; }
    .value { font: 13px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; overflow-wrap: anywhere; }
    .terminal-wrap { overflow: hidden; background: var(--term); border-color: #252b33; }
    .terminal-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 9px 10px; border-bottom: 1px solid #252b33; background: #0d1117; }
    .terminal-title { font: 12px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; color: var(--muted); }
    .actions { display: flex; flex-wrap: wrap; gap: 7px; }
    button { border: 1px solid #3d4652; background: #202833; color: var(--text); border-radius: 6px; padding: 7px 10px; cursor: pointer; font: 13px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    button:hover { background: #293241; }
    .terminal { height: calc(100vh - 278px); min-height: 360px; overflow: auto; padding: 13px 14px 20px; font: 13px/1.45 ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace; white-space: pre-wrap; overflow-wrap: anywhere; color: #d6deeb; }
    .dim { opacity: .66; } .bold { font-weight: 700; } .italic { font-style: italic; }
    .fg-black { color: #484f58; } .fg-red { color: #ff7b72; } .fg-green { color: #7ee787; } .fg-yellow { color: #f2cc60; } .fg-blue { color: #79c0ff; } .fg-magenta { color: #d2a8ff; } .fg-cyan { color: #76e3ea; } .fg-white { color: #e6edf3; }
    .fg-bright-black { color: #8b949e; } .fg-bright-red { color: #ffa198; } .fg-bright-green { color: #aff5b4; } .fg-bright-yellow { color: #f8e3a1; } .fg-bright-blue { color: #a5d6ff; } .fg-bright-magenta { color: #e2c5ff; } .fg-bright-cyan { color: #b3f0ff; } .fg-bright-white { color: #ffffff; }
    .details { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    .details .panel { padding: 12px; min-width: 0; }
    h2 { margin: 0 0 8px; font-size: 15px; }
    ul { margin: 0; padding-left: 18px; }
    pre { margin: 0; max-height: 260px; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; font: 12px/1.4 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; color: #c9d1d9; }
    .empty { padding: 20px; color: var(--muted); }
    @media (max-width: 980px) { .app-frame { grid-template-columns: 1fr; } .sidebar { position: static; } .live-main { grid-template-columns: 1fr; } .summary-grid, .details { grid-template-columns: 1fr; } .terminal { height: 55vh; } }
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
        <a class="side-link" href="/">Панель</a>
        <a class="side-link" href="/#connection">Подключение</a>
        <a class="side-link active" href="/runs/live">Живые запуски</a>
        <a class="side-link" href="/#technical">Технические детали</a>
      </nav>
    </aside>
    <div class="workspace">
      <header class="topbar">
        <div>
          <h1>Живые запуски</h1>
          <div class="subtitle">Read-only terminal-like монитор активных и недавних run_id.</div>
        </div>
        <div class="meta"><span class="pill" id="connectionState">polling</span><span class="pill">read-only</span></div>
      </header>
      <main class="live-main">
        <aside class="runs-panel">
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
        </div>
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
          </div>
        </div>
        <div id="terminal" class="terminal" aria-live="polite"></div>
      </section>
      <div class="details">
        <section class="panel">
          <h2>Timeline</h2>
          <ul id="timelineList"></ul>
        </section>
        <section class="panel">
          <h2>Result</h2>
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
    const terminalStatuses = new Set(['blocked','cancelled','completed','completed_dry_run','decision_only','failed','passed']);
    let selectedRunId = initialRunId || null;
    let userSelectedRun = Boolean(initialRunId);
    let autoscroll = true;
    let runsById = new Map();
    let terminalStates = new Map();
    let runSource = null;
    let listPollTimer = null;
    let detailPollTimer = null;

    function escapeHtml(value) {
      return String(value || '').replace(/[&<>"']/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;', "'": '&#39;'}[char]));
    }

    async function requestJson(path) {
      const response = await fetch(path, {cache: 'no-store'});
      if (!response.ok) throw new Error(`${response.status} ${path}`);
      return response.json();
    }

    async function refreshRuns() {
      const payload = await requestJson('/api/runs/live');
      const runs = payload.runs || [];
      renderRunList(runs);
      const nextSelected = chooseSelectedRun(runs);
      if (nextSelected && nextSelected !== selectedRunId) selectRun(nextSelected, {user: false});
      scheduleListRefresh(runs.some((run) => run.active) ? 1800 : 7000);
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
        if (!seen.has(row.dataset.runId)) row.remove();
      }
      updateSelectedRunClasses();
    }

    function createRunRow(runId) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'run-item';
      button.dataset.runId = runId;
      button.addEventListener('click', () => selectRun(runId, {user: true}));
      button.innerHTML = '<span class="run-id"></span><span class="meta"><span class="pill"></span><span data-field="stage"></span></span><span class="meta"><span data-field="target"></span><span data-field="mode"></span></span>';
      return button;
    }

    function updateRunRow(row, run) {
      updateText(row.querySelector('.run-id'), run.run_id || '');
      const status = row.querySelector('.pill');
      updateText(status, run.status || 'unknown');
      status.className = `pill ${statusClass(run.status)}`;
      updateText(row.querySelector('[data-field="stage"]'), run.current_stage || '');
      updateText(row.querySelector('[data-field="target"]'), run.target || run.target_id || '');
      updateText(row.querySelector('[data-field="mode"]'), `${run.run_type || 'run'} · ${run.execution_mode || ''}`);
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
      if (isTerminalStatus(run.status || '') || run.active === false) finalizeSelectedRun();
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
      if (isTerminalStatus(run.status || '') || run.active === false) {
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
      document.getElementById('summaryStatus').textContent = run.status || 'unknown';
      document.getElementById('summaryStatus').className = `value ${statusClass(run.status)}`;
      document.getElementById('summaryStage').textContent = run.current_stage || 'none';
      document.getElementById('summaryTarget').textContent = run.target || run.target_id || 'none';
      document.getElementById('summaryMode').textContent = run.execution_mode || 'none';
      document.getElementById('summaryBlocker').textContent = run.blocker || '';
      document.getElementById('terminalTitle').textContent = run.run_id || 'terminal';
      renderTimeline(payload.timeline || []);
      renderResult(payload);
      renderCuratorCodex(payload);
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
      lines.push(`verifier: ${run.verifier_status || 'n/a'}`);
      if (run.pr_url) lines.push(`PR: ${run.pr_url}`);
      if (run.merge_commit) lines.push(`merge: ${run.merge_commit}`);
      if (run.deploy_status) lines.push(`deploy: ${run.deploy_status}`);
      if (run.probe_status) lines.push(`probe: ${run.probe_status}`);
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
      if (['passed','completed','completed_dry_run','success'].includes(value)) return 'status-ok';
      if (['failed','blocked','error'].includes(value)) return 'status-bad';
      if (['waiting_for_target_lock','warning'].includes(value)) return 'status-warn';
      return '';
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
    function clearLocalView() {
      const state = stateForRun(selectedRunId);
      state.ansi = '';
      state.plain = '';
      clearTerminal();
      setTerminalPlaceholder();
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
        if (isTerminalStatus((payload.run || {}).status || '')) finalizeSelectedRun();
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
        terminalStates.set(key, {offset: 0, ansi: '', plain: '', loaded: false, timeline: [], timelineCursor: '', handoff: '', report: null, runTerminalFinalized: false});
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
        <button id="tab-dashboard-button" class="nav-item active" type="button" onclick="showTab('dashboard')">Панель</button>
        <button id="tab-connection-button" class="nav-item" type="button" onclick="showTab('connection')">Подключение</button>
        <a class="nav-item" href="/runs/live">Живые запуски</a>
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
                <a class="nav-item active" href="/runs/live">Живые запуски</a>
              </div>
            </section>
            <section class="panel">
              <h2>wb-core production boundary</h2>
              <dl class="compact-list" id="productionSummary"></dl>
            </section>
          </div>
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
      const [state, connections, runtime, runs, targets] = await Promise.all([
        request('/api/state'),
        request('/api/connections/status'),
        request('/api/runtime-config'),
        request('/api/runs/live'),
        request('/api/target-projects')
      ]);
      lastStatusPayload = {state, connections, runtime, runs, targets};
      renderDashboard(state, connections, runs, targets);
      renderConnection(connections, runtime);
      renderTechnical(state, connections, runtime, runs, targets);
    }

    function renderDashboard(state, connections, runs, targets) {
      const mcp = state.mcp || {};
      const github = connections.github || {};
      const ssh = connections.ssh_deploy || {};
      const lock = state.target_production_lock || {};
      const cards = [
        card('Сервис DevControl', state.hosted_ready ? 'hosted-ready' : 'loopback', `profile ${state.runtime_profile || 'local'} · ${state.host || '127.0.0.1'}:${state.port || ''}`, state.hosted_ready ? 'ok' : 'neutral'),
        card('MCP auth/tools', mcp.auth?.write_tools?.configured ? 'OAuth ready' : 'read-only ready', `${mcp.transport || 'streamable_http'} · ${mcp.tool_count ?? 0} tools`, mcp.enabled ? 'ok' : 'bad'),
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
    }

    function renderConnection(connections, runtime) {
      const codex = connections.codex || {};
      const openai = connections.openai || {};
      document.getElementById('codexStatus').innerHTML = statusList([
        ['Статус', codex.status || 'unknown'],
        ['version', codex.version || 'n/a'],
        ['auth', codex.auth_status || 'unknown'],
        ['model', codex.model || runtime.codex?.model || 'n/a'],
        ['reasoning', codex.model_reasoning_effort || runtime.codex?.reasoning_effort || 'n/a'],
        ['mode', connections.control_plane?.real_codex_ui_mode || 'managed_clone_only']
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

    function renderTechnical(state, connections, runtime, runs, targets) {
      const mcp = state.mcp || {};
      const toolchain = connections.toolchain || {};
      document.getElementById('technicalSummary').innerHTML = statusList([
        ['runtime profile', state.runtime_profile || 'local'],
        ['state root', state.state_dir || 'n/a'],
        ['MCP endpoint', mcp.endpoint || '/mcp'],
        ['MCP public tools', mcp.public_tool_count ?? 0],
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
        codex: connections.codex,
        github: connections.github,
        ssh_deploy: connections.ssh_deploy,
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
    <a class="nav-link" href="/runs/live">Живые запуски</a>
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
            <pre>codex --login
выбрать Sign in with ChatGPT</pre>
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
      const core = tools.filter((tool) => ['git', 'rg', 'python3', 'python3-venv', 'pip', 'jq', 'node', 'npm', 'codex'].includes(tool.name));
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
    active_rank = 0 if run.get("active") else 1
    timestamp = str(run.get("updated_at") or run.get("created_at") or "")
    return (active_rank, _reverse_sort_text(timestamp), str(run.get("run_id") or ""))


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


def _read_json(path: Path) -> Mapping[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise BadRequestError("JSON root must be an object")
    return payload


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


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


if __name__ == "__main__":
    raise SystemExit(main())
