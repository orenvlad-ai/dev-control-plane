"""Repo-only execution loop contracts for the development control-plane MVP."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
import fnmatch
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import threading
import time
from typing import Any, Callable, Literal, Mapping, Sequence
import uuid

from dev_control_plane.contracts import (
    ControlPlaneValidationError,
    DEFAULT_EXECUTION_MODE,
    SprintStep,
    TaskSpec,
    build_codex_prompt,
    sprint_step_to_dict,
    sprint_steps_from_task_spec_mapping,
    task_spec_from_mapping,
    validate_sprint_step,
    validate_task_spec,
)
from dev_control_plane.state_layout import (
    ControlPlaneStateLayout,
    StateLayoutError,
    safe_state_component,
    slug_state_component,
)
from dev_control_plane.runtime_config import load_runtime_config
from dev_control_plane.live_monitor import append_live_event, append_terminal_output, sanitize_terminal_text, terminal_log_path, terminalize_output
from dev_control_plane.codex_observability import (
    codex_stale_assessment,
    codex_supervision_config,
    finalize_process_state,
    read_process_state,
    terminate_run_owned_process_group,
    update_process_activity,
    write_process_started,
)
from dev_control_plane.target_projects import (
    TargetProjectConfig,
    merge_target_defaults_into_task_spec_payload,
    target_project_config_to_dict,
    validate_target_project,
)
from dev_control_plane.toolchain import (
    build_codex_runtime_parity_status,
    build_environment_parity_artifact,
    build_toolchain_status,
    requires_webcore_ui_browser_tools,
    runtime_command_env,
)

ExecutorMode = Literal["fake", "command"]
RealCodexExecutorMode = Literal["codex_cli"]
WorkspaceStrategy = Literal["managed_clone"]
RunStatus = Literal["prepared", "running", "verifier_passed", "failed", "blocked", "human_gate_required"]
CheckStatus = Literal["passed", "failed", "skipped"]
VerifierStatus = Literal["passed", "failed", "blocked"]

EXECUTOR_MODES = {"fake", "command"}
RUN_STATUSES = {"prepared", "running", "verifier_passed", "failed", "blocked", "human_gate_required"}
CHECK_STATUSES = {"passed", "failed", "skipped"}
VERIFIER_STATUSES = {"passed", "failed", "blocked"}
MANDATORY_HANDOFF_BLOCKS = ("=== ДЛЯ КУРАТОРА ===", "=== СЖАТАЯ ПРОВЕРКА ===")
COMMAND_FORBIDDEN_TOKENS = ("live_deploy", "deploy", "ssh", "sudo", "root_shell")
CODEX_CLI_FORBIDDEN_ACTIONS = ("live_deploy", "ssh", "root_shell", "public_route_change")
RUN_METADATA_FILE = "run.json"
MANAGED_WORKSPACE_METADATA_FILE = "managed_workspace.json"
RUNNABLE_STEP_MISSING_MESSAGE = "В карточке задачи не найден шаг запуска"
LOCAL_WORKSPACE_ID = "local-repo"
PROMPT_CONSISTENCY_CHECK_NAME = "prompt_consistency_gate"


@dataclass(frozen=True)
class RunRequest:
    id: str
    task_spec_id: str
    step_id: str
    executor_mode: ExecutorMode
    repo_root: str
    state_dir: str
    base_ref: str
    branch_name: str | None = None
    allow_real_executor: bool = False
    executor_command: str | None = None
    created_at: str = field(default_factory=lambda: _now_utc())


@dataclass(frozen=True)
class RealCodexRunRequest:
    id: str
    target_project_id: str
    task_spec_id: str
    step_id: str
    target_config_path: str | None
    state_dir: str
    base_ref: str
    workspace_strategy: WorkspaceStrategy = "managed_clone"
    executor_mode: RealCodexExecutorMode = "codex_cli"
    allow_real_codex: bool = False
    codex_bin: str = "codex"
    codex_args: Sequence[str] = field(default_factory=tuple)
    codex_model: str = "gpt-5.5"
    codex_reasoning_effort: str = "xhigh"
    sandbox_mode: str = "workspace-write"
    approval_policy: str = "never"
    created_at: str = field(default_factory=lambda: _now_utc())

    def __post_init__(self) -> None:
        object.__setattr__(self, "codex_args", tuple(str(item) for item in self.codex_args))


@dataclass(frozen=True)
class ManagedWorkspaceMetadata:
    original_repo_path: str
    original_head: str
    original_status_before: str
    workspace_path: str
    base_ref: str
    created_at: str = field(default_factory=lambda: _now_utc())


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: CheckStatus
    command: str | None = None
    output_path: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class VerifierResult:
    status: VerifierStatus
    check_results: Sequence[CheckResult]
    changed_files: Sequence[str]
    forbidden_path_hits: Sequence[str]
    mandatory_handoff_blocks_present: bool
    blocker_reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "check_results", tuple(self.check_results))
        object.__setattr__(self, "changed_files", tuple(self.changed_files))
        object.__setattr__(self, "forbidden_path_hits", tuple(self.forbidden_path_hits))


@dataclass(frozen=True)
class RunResult:
    id: str
    status: RunStatus
    task_spec_id: str
    step_id: str
    branch_name: str | None
    worktree_path: str | None
    run_dir: str
    prompt_path: str
    handoff_path: str | None
    log_path: str | None
    changed_files: Sequence[str]
    check_results: Sequence[CheckResult]
    blocker_reason: str | None = None
    next_manual_step: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "changed_files", tuple(self.changed_files))
        object.__setattr__(self, "check_results", tuple(self.check_results))


@dataclass(frozen=True)
class RealCodexRunResult:
    id: str
    status: RunStatus
    target_project_id: str
    task_spec_id: str
    step_id: str
    run_dir: str
    workspace_path: str | None
    prompt_path: str
    handoff_path: str | None
    log_path: str | None
    diff_path: str | None
    changed_files: Sequence[str]
    check_results: Sequence[CheckResult]
    verifier_status: str | None = None
    blocker_reason: str | None = None
    next_manual_step: str | None = None
    codex_exit_code: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "changed_files", tuple(self.changed_files))
        object.__setattr__(self, "check_results", tuple(self.check_results))


def prepare_run(
    task_spec_payload: Mapping[str, Any],
    *,
    step_id: str | None,
    repo_root: Path,
    state_dir: Path,
    base_ref: str | None = None,
    branch_name: str | None = None,
    executor_mode: ExecutorMode = "fake",
    allow_real_executor: bool = False,
    executor_command: str | None = None,
) -> RunResult:
    task_spec, step = _validated_task_and_step(task_spec_payload, step_id)
    _validate_path_component_ids(task_spec, step)
    _validate_executor_policy(task_spec, executor_mode, allow_real_executor, executor_command)

    repo_root = _resolve_repo_root(repo_root)
    base_ref = base_ref or _git_output(repo_root, "rev-parse", "HEAD")
    run_id = _new_run_id(task_spec, step)
    layout = _state_layout_or_raise(state_dir)
    run_layout = layout.run_layout(run_id)
    run_dir = run_layout.run_dir
    prompt_path = run_layout.prompt_path
    run_layout.ensure_dirs()
    if (run_dir / RUN_METADATA_FILE).exists():
        raise ControlPlaneExecutionError(f"run already exists: {run_dir}")
    append_live_event(
        run_dir,
        stage="queued",
        title="Run queued.",
        status="queued",
        source="runner",
        run_id=run_id,
        target_id=str(task_spec_payload.get("target_project_id") or "local"),
    )
    append_terminal_output(run_dir, f"\x1b[2mQueued managed Codex run {run_id}.\x1b[0m\n")
    execution_mode = _execution_mode_from_payload(task_spec_payload)
    prompt_path.write_text(build_codex_prompt(task_spec, step, execution_mode=execution_mode), encoding="utf-8")

    request = RunRequest(
        id=run_id,
        task_spec_id=task_spec.id,
        step_id=step.id,
        executor_mode=executor_mode,
        repo_root=str(repo_root),
        state_dir=str(layout.state_root),
        base_ref=base_ref,
        branch_name=branch_name,
        allow_real_executor=allow_real_executor,
        executor_command=_metadata_command(executor_mode, executor_command),
    )
    result = RunResult(
        id=run_id,
        status="prepared",
        task_spec_id=task_spec.id,
        step_id=step.id,
        branch_name=branch_name,
        worktree_path=None,
        run_dir=str(run_dir),
        prompt_path=str(prompt_path),
        handoff_path=None,
        log_path=None,
        changed_files=(),
        check_results=(),
    )
    _write_run_metadata(run_dir, request, task_spec_payload, step, result)
    return result


def run_step(
    task_spec_payload: Mapping[str, Any],
    *,
    step_id: str | None,
    repo_root: Path,
    state_dir: Path,
    base_ref: str | None = None,
    branch_name: str | None = None,
    executor_mode: ExecutorMode = "fake",
    allow_real_executor: bool = False,
    executor_command: str | None = None,
) -> RunResult:
    task_spec, step = _validated_task_and_step(task_spec_payload, step_id)
    _validate_path_component_ids(task_spec, step)
    _validate_executor_policy(task_spec, executor_mode, allow_real_executor, executor_command)

    repo_root = _resolve_repo_root(repo_root)
    base_ref = base_ref or _git_output(repo_root, "rev-parse", "HEAD")
    run_id = _new_run_id(task_spec, step)
    layout = _state_layout_or_raise(state_dir)
    run_layout = layout.run_layout(run_id)
    run_dir = run_layout.run_dir
    prompt_path = run_layout.prompt_path
    handoff_path = run_layout.handoff_path
    log_path = run_layout.executor_log_path
    run_layout.ensure_dirs()
    if (run_dir / RUN_METADATA_FILE).exists():
        raise ControlPlaneExecutionError(f"run already exists: {run_dir}")
    execution_mode = _execution_mode_from_payload(task_spec_payload)
    prompt_path.write_text(build_codex_prompt(task_spec, step, execution_mode=execution_mode), encoding="utf-8")

    branch_name = branch_name or f"control-plane/run/{run_id}"
    request = RunRequest(
        id=run_id,
        task_spec_id=task_spec.id,
        step_id=step.id,
        executor_mode=executor_mode,
        repo_root=str(repo_root),
        state_dir=str(layout.state_root),
        base_ref=base_ref,
        branch_name=branch_name,
        allow_real_executor=allow_real_executor,
        executor_command=_metadata_command(executor_mode, executor_command),
    )
    result = RunResult(
        id=run_id,
        status="running",
        task_spec_id=task_spec.id,
        step_id=step.id,
        branch_name=branch_name,
        worktree_path=None,
        run_dir=str(run_dir),
        prompt_path=str(prompt_path),
        handoff_path=str(handoff_path),
        log_path=str(log_path),
        changed_files=(),
        check_results=(),
    )
    _write_run_metadata(run_dir, request, task_spec_payload, step, result)

    worktree_path = run_layout.workspace_dir(LOCAL_WORKSPACE_ID)
    try:
        _create_worktree(repo_root, worktree_path, branch_name, base_ref)
    except ControlPlaneExecutionError as exc:
        blocked = replace(
            result,
            status="blocked",
            blocker_reason=str(exc),
            next_manual_step="Inspect git worktree state, branch refs and base_ref before retrying.",
        )
        _write_run_metadata(run_dir, request, task_spec_payload, step, blocked)
        return blocked

    result = replace(result, worktree_path=str(worktree_path))
    _write_run_metadata(run_dir, request, task_spec_payload, step, result)

    if executor_mode == "fake":
        _run_fake_executor(task_spec, step, result)
    else:
        _run_command_executor(worktree_path, handoff_path, log_path, executor_command or "")

    changed_files = _collect_changed_files(worktree_path)
    result = replace(result, changed_files=changed_files)
    _write_run_metadata(run_dir, request, task_spec_payload, step, result)

    verifier = verify_run(run_dir)
    status = _run_status_from_verifier(verifier)
    blocker_reason = verifier.blocker_reason
    if executor_mode == "command" and _command_failed(log_path):
        status = "failed"
        blocker_reason = "executor command exited non-zero"
    final = replace(
        result,
        status=status,
        changed_files=verifier.changed_files,
        check_results=verifier.check_results,
        blocker_reason=blocker_reason,
        next_manual_step=_next_manual_step(status, blocker_reason),
    )
    _write_run_metadata(run_dir, request, task_spec_payload, step, final)
    return final


def prepare_target_run(
    task_spec_payload: Mapping[str, Any],
    *,
    target_config: TargetProjectConfig,
    step_id: str | None,
    state_dir: Path,
    base_ref: str | None = None,
    target_config_path: Path | None = None,
) -> RealCodexRunResult:
    merged_payload = merge_target_defaults_into_task_spec_payload(task_spec_payload, target_config)
    task_spec, step = _validated_task_and_step(merged_payload, step_id)
    _validate_path_component_ids(task_spec, step, target_id=target_config.project_id)
    target_validation = validate_target_project(target_config)
    _validate_real_codex_policy(task_spec, target_config, target_validation, allow_real_codex=True, prepare_only=True)

    layout = _state_layout_or_raise(state_dir)
    run_id = _new_run_id(task_spec, step)
    run_layout = layout.run_layout(run_id)
    run_dir = run_layout.run_dir
    prompt_path = run_layout.prompt_path
    handoff_path = run_layout.handoff_path
    log_path = run_layout.codex_log_path
    diff_path = run_layout.diff_path
    run_layout.ensure_dirs()
    if (run_dir / RUN_METADATA_FILE).exists():
        raise ControlPlaneExecutionError(f"run already exists: {run_dir}")
    execution_mode = _execution_mode_from_payload(merged_payload)
    prompt_path.write_text(build_codex_prompt(task_spec, step, execution_mode=execution_mode), encoding="utf-8")

    workspace = create_managed_target_workspace(
        target_config,
        run_dir,
        workspace_path=run_layout.workspace_dir(_slug(target_config.project_id)),
        base_ref=base_ref,
    )
    append_live_event(
        run_dir,
        stage="clone",
        title="Managed clone workspace ready.",
        status="preparing",
        detail=workspace.base_ref,
        source="runner",
        run_id=run_id,
        target_id=target_config.project_id,
    )
    append_terminal_output(run_dir, "\x1b[36mManaged clone workspace ready.\x1b[0m\n")
    request = RealCodexRunRequest(
        id=run_id,
        target_project_id=target_config.project_id,
        task_spec_id=task_spec.id,
        step_id=step.id,
        target_config_path=str(target_config_path) if target_config_path else None,
        state_dir=str(layout.state_root),
        base_ref=workspace.base_ref,
        allow_real_codex=False,
    )
    result = RealCodexRunResult(
        id=run_id,
        status="prepared",
        target_project_id=target_config.project_id,
        task_spec_id=task_spec.id,
        step_id=step.id,
        run_dir=str(run_dir),
        workspace_path=workspace.workspace_path,
        prompt_path=str(prompt_path),
        handoff_path=str(handoff_path),
        log_path=str(log_path),
        diff_path=str(diff_path),
        changed_files=(),
        check_results=(),
    )
    _write_target_run_metadata(run_dir, request, target_config, merged_payload, step, result, workspace)
    return result


def run_codex_cli(
    task_spec_payload: Mapping[str, Any],
    *,
    target_config: TargetProjectConfig,
    step_id: str | None,
    state_dir: Path,
    allow_real_codex: bool = False,
    codex_bin: str | None = None,
    codex_args: Sequence[str] = (),
    base_ref: str | None = None,
    run_id: str | None = None,
    target_config_path: Path | None = None,
    progress_callback: Callable[[str], None] | None = None,
) -> RealCodexRunResult:
    _notify_progress(progress_callback, "preparing")
    merged_payload = merge_target_defaults_into_task_spec_payload(task_spec_payload, target_config)
    task_spec, step = _validated_task_and_step(merged_payload, step_id)
    _validate_path_component_ids(task_spec, step, target_id=target_config.project_id)
    target_validation = validate_target_project(target_config)
    _validate_real_codex_policy(task_spec, target_config, target_validation, allow_real_codex=allow_real_codex)

    layout = _state_layout_or_raise(state_dir)
    run_id = safe_state_component(run_id, "run_id") if run_id else _new_run_id(task_spec, step)
    run_layout = layout.run_layout(run_id)
    run_dir = run_layout.run_dir
    prompt_path = run_layout.prompt_path
    handoff_path = run_layout.handoff_path
    log_path = run_layout.codex_log_path
    diff_path = run_layout.diff_path
    run_layout.ensure_dirs()
    if (run_dir / RUN_METADATA_FILE).exists():
        raise ControlPlaneExecutionError(f"run already exists: {run_dir}")
    execution_mode = _execution_mode_from_payload(merged_payload)
    prompt_path.write_text(build_codex_prompt(task_spec, step, execution_mode=execution_mode), encoding="utf-8")

    workspace = create_managed_target_workspace(
        target_config,
        run_dir,
        workspace_path=run_layout.workspace_dir(_slug(target_config.project_id)),
        base_ref=base_ref,
    )
    effective_codex_bin = codex_bin or os.environ.get("DEV_CONTROL_PLANE_CODEX_BIN") or "codex"
    runtime_config = load_runtime_config()
    request = RealCodexRunRequest(
        id=run_id,
        target_project_id=target_config.project_id,
        task_spec_id=task_spec.id,
        step_id=step.id,
        target_config_path=str(target_config_path) if target_config_path else None,
        state_dir=str(layout.state_root),
        base_ref=workspace.base_ref,
        allow_real_codex=allow_real_codex,
        codex_bin=effective_codex_bin,
        codex_args=tuple(codex_args),
        codex_model=runtime_config.codex.model,
        codex_reasoning_effort=runtime_config.codex.reasoning_effort,
        sandbox_mode=runtime_config.codex.sandbox_mode,
    )
    result = RealCodexRunResult(
        id=run_id,
        status="running",
        target_project_id=target_config.project_id,
        task_spec_id=task_spec.id,
        step_id=step.id,
        run_dir=str(run_dir),
        workspace_path=workspace.workspace_path,
        prompt_path=str(prompt_path),
        handoff_path=str(handoff_path),
        log_path=str(log_path),
        diff_path=str(diff_path),
        changed_files=(),
        check_results=(),
    )
    _write_target_run_metadata(run_dir, request, target_config, merged_payload, step, result, workspace)

    prompt_gate = _prompt_consistency_gate(
        prompt_path.read_text(encoding="utf-8"),
        execution_mode=execution_mode,
        codex_run=True,
    )
    if prompt_gate.status == "failed":
        blocked = replace(
            result,
            status="blocked",
            check_results=(prompt_gate,),
            blocker_reason=prompt_gate.reason,
            next_manual_step="Fix the task envelope/mode conflict and start a new run.",
        )
        _write_target_run_metadata(run_dir, request, target_config, merged_payload, step, blocked, workspace)
        append_live_event(
            run_dir,
            stage="blocker",
            title="Prompt consistency gate blocked Codex.",
            status="blocked",
            level="error",
            detail=prompt_gate.reason,
            source="runner",
            run_id=run_id,
            target_id=target_config.project_id,
        )
        append_terminal_output(run_dir, f"\x1b[31mPrompt consistency gate blocked Codex: {prompt_gate.reason}\x1b[0m\n")
        return blocked

    prompt_text = prompt_path.read_text(encoding="utf-8")
    preflight_checks = _run_codex_workspace_preflight(
        Path(workspace.workspace_path),
        run_dir,
        codex_bin=effective_codex_bin,
        target_id=target_config.project_id,
        base_commit=workspace.base_ref,
        prompt_text=prompt_text,
        codex_model=runtime_config.codex.model,
        codex_reasoning_effort=runtime_config.codex.reasoning_effort,
    )
    failed_preflight = [check for check in preflight_checks if check.status == "failed"]
    if failed_preflight:
        reason = "; ".join(check.reason or check.name for check in failed_preflight)
        blocked = replace(
            result,
            status="blocked",
            check_results=tuple(preflight_checks),
            blocker_reason=f"managed workspace preflight failed: {reason}",
            next_manual_step="Проверьте hosted managed workspace tools before retrying Codex.",
        )
        _write_target_run_metadata(run_dir, request, target_config, merged_payload, step, blocked, workspace)
        append_live_event(
            run_dir,
            stage="blocker",
            title="Managed workspace preflight blocked Codex.",
            status="blocked",
            level="error",
            detail=reason,
            source="runner",
            run_id=run_id,
            target_id=target_config.project_id,
        )
        append_terminal_output(run_dir, f"\x1b[31mPreflight blocked: {reason}\x1b[0m\n")
        return blocked

    _notify_progress(progress_callback, "running_codex")
    append_live_event(
        run_dir,
        stage="codex_started",
        title="Codex CLI started.",
        status="running_codex",
        source="runner",
        run_id=run_id,
        target_id=target_config.project_id,
    )
    append_terminal_output(run_dir, "\x1b[1;36mCodex CLI started.\x1b[0m\n")
    exit_code = _run_codex_cli_executor(
        request,
        workspace_path=Path(workspace.workspace_path),
        prompt_path=prompt_path,
        handoff_path=handoff_path,
        log_path=log_path,
    )
    append_live_event(
        run_dir,
        stage="codex_finished",
        title="Codex CLI finished.",
        status="codex_finished",
        level="success" if exit_code == 0 else "error",
        detail=f"exit_code={exit_code}",
        source="runner",
        run_id=run_id,
        target_id=target_config.project_id,
    )
    _write_diff_artifact(Path(workspace.workspace_path), diff_path)
    changed_files = _collect_changed_files(Path(workspace.workspace_path))
    result = replace(result, changed_files=changed_files, codex_exit_code=exit_code)
    _write_target_run_metadata(run_dir, request, target_config, merged_payload, step, result, workspace)

    _notify_progress(progress_callback, "verifying")
    append_live_event(
        run_dir,
        stage="verifier",
        title="Verifier started.",
        status="verifying",
        source="verifier",
        run_id=run_id,
        target_id=target_config.project_id,
    )
    verifier = verify_target_run(run_dir)
    status = _run_status_from_verifier(verifier)
    blocker_reason = verifier.blocker_reason
    if exit_code != 0:
        status = "failed"
        blocker_reason = f"Codex CLI exited non-zero: {exit_code}"
    final = replace(
        result,
        status=status,
        verifier_status=verifier.status,
        changed_files=verifier.changed_files,
        check_results=verifier.check_results,
        blocker_reason=blocker_reason,
        next_manual_step=_next_manual_step(status, blocker_reason),
    )
    _write_target_run_metadata(run_dir, request, target_config, merged_payload, step, final, workspace)
    append_live_event(
        run_dir,
        stage="completed" if final.status == "passed" else final.status,
        title="Verifier completed.",
        status=final.status,
        level="success" if final.status == "passed" else "error",
        detail=blocker_reason,
        source="verifier",
        run_id=run_id,
        target_id=target_config.project_id,
    )
    append_terminal_output(
        run_dir,
        f"\x1b[{'32' if final.status == 'passed' else '31'}mVerifier status: {final.status}\x1b[0m\n",
    )
    return final


def _execution_mode_from_payload(payload: Mapping[str, Any]) -> str:
    raw = str(payload.get("execution_mode") or "").strip()
    if raw:
        return raw
    note = str(payload.get("explicit_policy_note") or "").strip()
    if "production_lane" in note:
        return "production_lane"
    if "managed_clone_only" in note:
        return "managed_clone_only"
    return DEFAULT_EXECUTION_MODE


def _prompt_consistency_gate(prompt_text: str, *, execution_mode: str, codex_run: bool) -> CheckResult:
    searchable = _lower_for_policy(_prompt_without_execution_mode_line(prompt_text))
    mode = _lower_for_policy(execution_mode)
    blockers: list[str] = []
    production_mode = "production_lane" in str(execution_mode or "").lower() or "production lane" in mode
    ui_task = _contains_any(searchable, ("browser ui", "operator ui", "frontend ui", "/runs/live", "/sheet-vitrina", "страниц", "интерфейс", "таблиц", "layout"))
    explicit_no_ui = _contains_phrase(searchable, "no ui") or "без ui" in searchable
    explicit_no_codex = _contains_phrase(searchable, "no codex worker run") or "без codex worker" in searchable
    if production_mode:
        for phrase in ("repo only", "no live/deploy", "no live deploy", "no deploy", "no ui", "no codex worker run"):
            if _contains_phrase(searchable, phrase) or _contains_phrase(mode, phrase):
                blockers.append(f"production_lane conflicts with `{phrase}`")
    if ui_task and explicit_no_ui:
        blockers.append("UI task conflicts with `no UI`")
    if codex_run and explicit_no_codex:
        blockers.append("Codex run conflicts with `no Codex worker run`")
    if blockers:
        return CheckResult(
            name=PROMPT_CONSISTENCY_CHECK_NAME,
            status="failed",
            reason="; ".join(blockers),
        )
    return CheckResult(name=PROMPT_CONSISTENCY_CHECK_NAME, status="passed", reason=f"execution_mode={execution_mode}")


def _prompt_without_execution_mode_line(prompt_text: str) -> str:
    lines = []
    for line in str(prompt_text or "").splitlines():
        lowered = line.strip().lower()
        if lowered.startswith("режим выполнения:") or lowered.startswith("execution mode:"):
            continue
        lines.append(line)
    return "\n".join(lines)


def _lower_for_policy(text: Any) -> str:
    return " " + str(text or "").replace("_", " ").replace("-", " ").lower() + " "


def _contains_phrase(text: str, phrase: str) -> bool:
    return phrase.lower() in text


def _contains_any(text: str, phrases: Sequence[str]) -> bool:
    return any(phrase in text for phrase in phrases)


def _notify_progress(callback: Callable[[str], None] | None, status: str) -> None:
    if callback is None:
        return
    callback(status)


def create_managed_target_workspace(
    target_config: TargetProjectConfig,
    run_dir: Path,
    *,
    workspace_path: Path | None = None,
    base_ref: str | None = None,
) -> ManagedWorkspaceMetadata:
    validation = validate_target_project(target_config)
    if validation.status == "blocked":
        raise ControlPlaneExecutionError(
            f"target project validation blocked: {'; '.join(validation.blockers)}"
        )
    source_mode = str(getattr(target_config, "source_mode", "local_path") or "local_path")
    source_repo = Path(validation.repo_path).resolve()
    if source_mode == "remote_managed_clone":
        if not target_config.repo_url:
            raise ControlPlaneExecutionError("repo_url is required for remote managed clone")
        original_head = validation.head_commit or target_config.branch
        original_status_before = "remote_managed_clone_source: no original target worktree in hosted runtime"
    else:
        original_head = validation.head_commit or _git_output(source_repo, "rev-parse", "HEAD")
        original_status_before = _git_output(source_repo, "status", "--short")
    effective_base_ref = base_ref or original_head
    workspace_path = (
        workspace_path
        if workspace_path is not None
        else (run_dir / "workspace" / _slug(target_config.project_id))
    ).resolve()
    workspace_owner = _workspace_owner_for_run_dir(run_dir, _slug(target_config.project_id))
    if not _is_relative_to(workspace_path, workspace_owner) and not _is_relative_to(workspace_path, run_dir.resolve()):
        raise ControlPlaneExecutionError(f"workspace path escapes owned state workspace: {workspace_path}")
    if workspace_path.exists():
        raise ControlPlaneExecutionError(f"managed workspace already exists: {workspace_path}")
    workspace_path.parent.mkdir(parents=True, exist_ok=True)

    if source_mode == "remote_managed_clone":
        clone = _git(
            run_dir,
            "clone",
            "--branch",
            target_config.branch,
            "--single-branch",
            "--no-tags",
            str(target_config.repo_url),
            str(workspace_path),
        )
    else:
        clone = _git(source_repo, "clone", "--no-hardlinks", str(source_repo), str(workspace_path))
    if clone.returncode != 0:
        raise ControlPlaneExecutionError(_command_output(clone) or "git clone failed")
    checkout = _git(workspace_path, "checkout", "--detach", effective_base_ref)
    if checkout.returncode != 0:
        raise ControlPlaneExecutionError(_command_output(checkout) or f"git checkout failed: {effective_base_ref}")

    metadata = ManagedWorkspaceMetadata(
        original_repo_path=str(target_config.repo_url) if source_mode == "remote_managed_clone" else str(source_repo),
        original_head=original_head,
        original_status_before=original_status_before,
        workspace_path=str(workspace_path),
        base_ref=effective_base_ref,
    )
    (run_dir / MANAGED_WORKSPACE_METADATA_FILE).write_text(
        json.dumps(managed_workspace_metadata_to_dict(metadata), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return metadata


def verify_run(run_dir: Path) -> VerifierResult:
    metadata = _read_run_metadata(run_dir)
    request = metadata["request"]
    result = metadata["result"]
    task_spec = task_spec_from_mapping(metadata["task_spec"])
    validate_task_spec(task_spec, require_frozen=True)

    run_dir = Path(str(result["run_dir"]))
    prompt_path = Path(str(result["prompt_path"]))
    handoff_raw = result.get("handoff_path")
    handoff_path = Path(str(handoff_raw)) if handoff_raw else None
    worktree_raw = result.get("worktree_path")
    worktree_path = Path(str(worktree_raw)) if worktree_raw else None
    checks_dir = run_dir / "verifier" / "checks"
    checks_dir.mkdir(parents=True, exist_ok=True)

    check_results: list[CheckResult] = []
    if prompt_path.exists():
        check_results.append(CheckResult(name="prompt_exists", status="passed", output_path=str(prompt_path)))
    else:
        check_results.append(CheckResult(name="prompt_exists", status="failed", reason="prompt file is missing"))

    handoff_text = ""
    if handoff_path and handoff_path.exists():
        handoff_text = handoff_path.read_text(encoding="utf-8")
        check_results.append(CheckResult(name="handoff_exists", status="passed", output_path=str(handoff_path)))
    else:
        check_results.append(CheckResult(name="handoff_exists", status="failed", reason="handoff file is missing"))

    handoff_contract_violations = _handoff_contract_violations(handoff_text)
    mandatory_blocks_present = not handoff_contract_violations
    handoff_contract_reason = _handoff_contract_reason(handoff_contract_violations)
    check_results.append(
        CheckResult(
            name="handoff_mandatory_blocks",
            status="passed" if mandatory_blocks_present else "failed",
            output_path=str(handoff_path) if handoff_path else None,
            reason=handoff_contract_reason,
        )
    )

    changed_files = _merged_changed_files(result, worktree_path)
    forbidden_hits = _forbidden_path_hits(changed_files, task_spec.forbidden_paths)
    allowed_violations = _allowed_path_violations(changed_files, task_spec.allowed_paths)
    check_results.append(
        CheckResult(
            name="forbidden_paths",
            status="passed" if not forbidden_hits else "failed",
            reason=None if not forbidden_hits else f"forbidden path changes detected: {', '.join(forbidden_hits)}",
        )
    )
    check_results.append(
        CheckResult(
            name="allowed_paths",
            status="passed" if not allowed_violations else "failed",
            reason=None if not allowed_violations else f"changes outside allowed paths: {', '.join(allowed_violations)}",
        )
    )

    check_results.append(_fake_executor_policy_check(request))
    check_results.append(_git_diff_check(worktree_path, checks_dir))

    failed_checks = [check for check in check_results if check.status == "failed"]
    if forbidden_hits:
        status: VerifierStatus = "blocked"
        blocker_reason = f"forbidden path changes detected: {', '.join(forbidden_hits)}"
    elif handoff_contract_reason and _only_failed_check(check_results, "handoff_mandatory_blocks"):
        status = "failed"
        blocker_reason = handoff_contract_reason
    elif failed_checks:
        status = "failed"
        blocker_reason = "; ".join(check.reason or check.name for check in failed_checks)
    else:
        status = "passed"
        blocker_reason = None

    verifier = VerifierResult(
        status=status,
        check_results=tuple(check_results),
        changed_files=tuple(changed_files),
        forbidden_path_hits=tuple(forbidden_hits),
        mandatory_handoff_blocks_present=mandatory_blocks_present,
        blocker_reason=blocker_reason,
    )
    _write_verifier_result(run_dir, verifier)
    return verifier


def verify_target_run(run_dir: Path) -> VerifierResult:
    metadata = _read_run_metadata(run_dir)
    request = metadata["request"]
    result = metadata["result"]
    task_spec = task_spec_from_mapping(metadata["task_spec"])
    validate_task_spec(task_spec, require_frozen=True)

    run_dir = Path(str(result["run_dir"]))
    prompt_path = Path(str(result["prompt_path"]))
    handoff_raw = result.get("handoff_path")
    handoff_path = Path(str(handoff_raw)) if handoff_raw else None
    workspace_raw = result.get("workspace_path")
    workspace_path = Path(str(workspace_raw)) if workspace_raw else None
    diff_raw = result.get("diff_path")
    diff_path = Path(str(diff_raw)) if diff_raw else None
    checks_dir = run_dir / "verifier" / "checks"
    checks_dir.mkdir(parents=True, exist_ok=True)

    check_results: list[CheckResult] = []
    if prompt_path.exists():
        check_results.append(CheckResult(name="prompt_exists", status="passed", output_path=str(prompt_path)))
    else:
        check_results.append(CheckResult(name="prompt_exists", status="failed", reason="prompt file is missing"))

    handoff_text = ""
    if handoff_path and handoff_path.exists():
        handoff_text = handoff_path.read_text(encoding="utf-8")
        check_results.append(CheckResult(name="handoff_exists", status="passed", output_path=str(handoff_path)))
    else:
        check_results.append(CheckResult(name="handoff_exists", status="failed", reason="handoff file is missing"))

    handoff_contract_violations = _handoff_contract_violations(handoff_text)
    mandatory_blocks_present = not handoff_contract_violations
    handoff_contract_reason = _handoff_contract_reason(handoff_contract_violations)
    check_results.append(
        CheckResult(
            name="handoff_mandatory_blocks",
            status="passed" if mandatory_blocks_present else "failed",
            output_path=str(handoff_path) if handoff_path else None,
            reason=handoff_contract_reason,
        )
    )

    if diff_path and diff_path.exists():
        check_results.append(CheckResult(name="diff_artifact_exists", status="passed", output_path=str(diff_path)))
    else:
        check_results.append(CheckResult(name="diff_artifact_exists", status="failed", reason="diff artifact is missing"))

    changed_files = _merged_target_changed_files(result, workspace_path)
    forbidden_hits = _forbidden_path_hits(changed_files, task_spec.forbidden_paths)
    allowed_violations = _allowed_path_violations(changed_files, task_spec.allowed_paths)
    check_results.append(
        CheckResult(
            name="forbidden_paths",
            status="passed" if not forbidden_hits else "failed",
            reason=None if not forbidden_hits else f"forbidden path changes detected: {', '.join(forbidden_hits)}",
        )
    )
    check_results.append(
        CheckResult(
            name="allowed_paths",
            status="passed" if not allowed_violations else "failed",
            reason=None if not allowed_violations else f"changes outside allowed paths: {', '.join(allowed_violations)}",
        )
    )
    check_results.append(_managed_workspace_policy_check(request, result, run_dir))
    check_results.append(_target_repo_unchanged_check(request))
    check_results.append(_codex_cli_exit_check(result))
    check_results.append(_live_actions_stay_forbidden_check(task_spec))
    check_results.append(_git_diff_check(workspace_path, checks_dir))

    failed_checks = [check for check in check_results if check.status == "failed"]
    if forbidden_hits:
        status: VerifierStatus = "blocked"
        blocker_reason = f"forbidden path changes detected: {', '.join(forbidden_hits)}"
    elif _check_failed(check_results, "target_repo_unchanged"):
        status = "blocked"
        blocker_reason = _check_reason(check_results, "target_repo_unchanged")
    elif handoff_contract_reason and _only_failed_check(check_results, "handoff_mandatory_blocks"):
        status = "failed"
        blocker_reason = handoff_contract_reason
    elif failed_checks:
        status = "failed"
        blocker_reason = "; ".join(check.reason or check.name for check in failed_checks)
    else:
        status = "passed"
        blocker_reason = None

    verifier = VerifierResult(
        status=status,
        check_results=tuple(check_results),
        changed_files=tuple(changed_files),
        forbidden_path_hits=tuple(forbidden_hits),
        mandatory_handoff_blocks_present=mandatory_blocks_present,
        blocker_reason=blocker_reason,
    )
    _write_verifier_result(run_dir, verifier)
    return verifier


def cleanup_target_run(run_dir: Path) -> dict[str, Any]:
    metadata = _read_run_metadata(run_dir)
    result = metadata["result"]
    run_dir = Path(str(result["run_dir"])).resolve()
    workspace_raw = result.get("workspace_path")
    if not workspace_raw:
        return {"status": "skipped", "reason": "target run has no workspace_path"}
    workspace_path = Path(str(workspace_raw)).resolve()
    workspace_owner = _workspace_owner_from_metadata(metadata, run_dir)
    if not _is_relative_to(workspace_path, workspace_owner) and not _is_relative_to(workspace_path, run_dir):
        raise ControlPlaneExecutionError(f"refusing to remove workspace outside owned state workspace: {workspace_path}")
    original_repo_raw = metadata.get("workspace", {}).get("original_repo_path")
    if original_repo_raw and not _is_urlish(original_repo_raw) and _same_path_or_child(
        workspace_path,
        Path(str(original_repo_raw)).resolve(),
    ):
        raise ControlPlaneExecutionError("refusing to remove original target repo")
    if workspace_path.exists():
        shutil.rmtree(workspace_path)
    return {"status": "cleaned", "workspace_path": str(workspace_path), "run_dir": str(run_dir)}


def cleanup_run_worktree(run_dir: Path) -> dict[str, Any]:
    metadata = _read_run_metadata(run_dir)
    request = metadata["request"]
    result = metadata["result"]
    repo_root = Path(str(request["repo_root"]))
    state_dir = Path(str(request["state_dir"])).resolve()
    worktree_raw = result.get("worktree_path")
    branch_name = result.get("branch_name")
    if not worktree_raw:
        return {"status": "skipped", "reason": "run has no worktree_path"}

    worktree_path = Path(str(worktree_raw)).resolve()
    if not _is_relative_to(worktree_path, state_dir):
        raise ControlPlaneExecutionError(f"refusing to remove worktree outside state_dir: {worktree_path}")

    if worktree_path.exists():
        _git_checked(repo_root, "worktree", "remove", "--force", str(worktree_path))
    if branch_name and _branch_exists(repo_root, str(branch_name)):
        _git_checked(repo_root, "branch", "-D", str(branch_name))
    return {"status": "cleaned", "worktree_path": str(worktree_path), "branch_name": branch_name}


def load_run_record(run_dir: Path) -> dict[str, Any]:
    metadata = _read_run_metadata(run_dir)
    verifier_path = _verifier_result_path(run_dir)
    legacy_verifier_path = run_dir / "verifier.json"
    if verifier_path.exists():
        verifier = json.loads(verifier_path.read_text(encoding="utf-8"))
        if isinstance(verifier, Mapping):
            metadata["verifier"] = _json_ready(dict(verifier))
    elif legacy_verifier_path.exists():
        verifier = json.loads(legacy_verifier_path.read_text(encoding="utf-8"))
        if isinstance(verifier, Mapping):
            metadata["verifier"] = _json_ready(dict(verifier))
    return _json_ready(metadata)


def run_result_to_dict(result: RunResult) -> dict[str, Any]:
    return _json_ready(asdict(result))


def real_codex_run_result_to_dict(result: RealCodexRunResult) -> dict[str, Any]:
    return _json_ready(asdict(result))


def verifier_result_to_dict(result: VerifierResult) -> dict[str, Any]:
    return _json_ready(asdict(result))


def check_result_to_dict(result: CheckResult) -> dict[str, Any]:
    return _json_ready(asdict(result))


def real_codex_run_request_to_dict(request: RealCodexRunRequest) -> dict[str, Any]:
    return _json_ready(asdict(request))


def managed_workspace_metadata_to_dict(metadata: ManagedWorkspaceMetadata) -> dict[str, Any]:
    return _json_ready(asdict(metadata))


class ControlPlaneExecutionError(RuntimeError):
    """Raised when the repo-only execution loop cannot continue safely."""


def _validated_task_and_step(payload: Mapping[str, Any], step_id: str | None) -> tuple[TaskSpec, SprintStep]:
    task_spec = task_spec_from_mapping(payload)
    validate_task_spec(task_spec, require_frozen=True)
    try:
        steps = sprint_steps_from_task_spec_mapping(payload, task_spec)
        for step in steps:
            validate_sprint_step(step)
    except ControlPlaneValidationError as exc:
        raise ControlPlaneValidationError(RUNNABLE_STEP_MISSING_MESSAGE) from exc
    if not steps:
        raise ControlPlaneValidationError(RUNNABLE_STEP_MISSING_MESSAGE)
    if step_id:
        for step in steps:
            if step.id == step_id:
                return task_spec, step
    return task_spec, steps[0]


def _validate_path_component_ids(task_spec: TaskSpec, step: SprintStep, *, target_id: str | None = None) -> None:
    try:
        safe_state_component(task_spec.id, "task_id")
        safe_state_component(step.id, "step_id")
        if target_id is not None:
            safe_state_component(target_id, "target_id")
    except StateLayoutError as exc:
        raise ControlPlaneValidationError(str(exc)) from exc


def _validate_executor_policy(
    task_spec: TaskSpec,
    executor_mode: str,
    allow_real_executor: bool,
    executor_command: str | None,
) -> None:
    if executor_mode not in EXECUTOR_MODES:
        raise ControlPlaneValidationError(f"executor_mode must be one of {sorted(EXECUTOR_MODES)}")
    if executor_mode == "fake":
        if executor_command:
            raise ControlPlaneValidationError("fake executor mode does not accept executor_command")
        return
    if not allow_real_executor:
        raise ControlPlaneValidationError("command executor requires --allow-real-executor")
    if not executor_command:
        raise ControlPlaneValidationError("command executor requires --executor-command")
    if "repo_only_executor" not in task_spec.allowed_actions:
        raise ControlPlaneValidationError("command executor requires allowed_actions to include repo_only_executor")
    lowered = executor_command.lower()
    blocked = [token for token in COMMAND_FORBIDDEN_TOKENS if token in lowered]
    if blocked:
        raise ControlPlaneValidationError(f"executor_command contains forbidden tokens: {blocked}")


def _validate_real_codex_policy(
    task_spec: TaskSpec,
    target_config: TargetProjectConfig,
    target_validation: Any,
    *,
    allow_real_codex: bool,
    prepare_only: bool = False,
) -> None:
    if target_validation.status == "blocked":
        raise ControlPlaneValidationError(
            f"target project validation blocked: {'; '.join(target_validation.blockers)}"
        )
    policy = dict(target_config.execution_policy)
    if not policy.get("allow_managed_clone_execution", False):
        raise ControlPlaneValidationError("target execution policy blocks managed clone execution")
    if policy.get("allow_direct_target_mutation", False):
        raise ControlPlaneValidationError("target execution policy must not allow direct target mutation")
    if policy.get("allow_live_deploy", False):
        raise ControlPlaneValidationError("target execution policy must not allow live deploy")
    if policy.get("allow_auto_merge", False):
        raise ControlPlaneValidationError("target execution policy must not allow auto-merge")
    if not prepare_only and policy.get("require_explicit_real_codex_flag", True) and not allow_real_codex:
        raise ControlPlaneValidationError("Codex CLI execution requires --allow-real-codex")
    if not prepare_only and not allow_real_codex:
        raise ControlPlaneValidationError("Codex CLI execution requires --allow-real-codex")

    forbidden_actions = {str(action) for action in task_spec.forbidden_actions}
    missing_forbidden = [action for action in CODEX_CLI_FORBIDDEN_ACTIONS if action not in forbidden_actions]
    if missing_forbidden:
        raise ControlPlaneValidationError(f"task spec missing required forbidden actions: {missing_forbidden}")
    if any(action in task_spec.allowed_actions for action in CODEX_CLI_FORBIDDEN_ACTIONS):
        raise ControlPlaneValidationError("task spec allowed_actions must not allow live/deploy/SSH/root/public actions")
    if "real_codex_execution" in forbidden_actions and not task_spec.explicit_policy_note:
        raise ControlPlaneValidationError(
            "real_codex_execution is forbidden by task spec; add explicit_policy_note before real Codex CLI"
        )


def _metadata_command(executor_mode: str, executor_command: str | None) -> str | None:
    if executor_mode != "command" or not executor_command:
        return None
    return "[redacted-command]"


def _create_worktree(repo_root: Path, worktree_path: Path, branch_name: str, base_ref: str) -> None:
    worktree_path.parent.mkdir(parents=True, exist_ok=True)
    if worktree_path.exists():
        raise ControlPlaneExecutionError(f"worktree path already exists: {worktree_path}")
    result = _git(repo_root, "worktree", "add", "-b", branch_name, str(worktree_path), base_ref)
    if result.returncode != 0:
        raise ControlPlaneExecutionError(_command_output(result) or "git worktree add failed")


def _run_fake_executor(task_spec: TaskSpec, step: SprintStep, result: RunResult) -> None:
    assert result.handoff_path is not None
    assert result.log_path is not None
    handoff = "\n".join(
        (
            "=== ДЛЯ КУРАТОРА ===",
            "",
            "Статус: fake executor completed repo-only simulation",
            f"Что сделано: prepared bounded run for {task_spec.id}/{step.id}",
            "Изменённые/созданные файлы: none",
            "Ключевой результат: deterministic fake handoff written for verifier smoke",
            "Что НЕ тронуто / что осталось вне scope: live/deploy/SSH/root/OpenAI/Codex CLI",
            "Следующий шаг: review verifier result",
            "Если есть блокер — точная причина: none",
            "Repo state: isolated worktree, no repo changes",
            "Live deploy state: not run",
            "Public verify result: not applicable",
            "Sheet verify result: not applicable",
            "Upload-ready source state: not applicable",
            "Manual-only remainder: none",
            "Commit status: not run",
            "Commit hash: none",
            "Push status: not run",
            "PR status: not created",
            "Ссылка на PR: none",
            "Merge status: not run",
            "Delete branch status: not run",
            "Exact blocker: none",
            "",
            "=== СЖАТАЯ ПРОВЕРКА ===",
            "",
            "- fake executor only",
            "- no live/deploy/SSH/root action",
            "- verifier owns completion decision",
            "Главный вывод: repo-only fake execution artifact is ready for verification.",
            "",
        )
    )
    Path(result.handoff_path).write_text(handoff, encoding="utf-8")
    Path(result.log_path).write_text("fake executor completed; no command executed\n", encoding="utf-8")


def _run_command_executor(worktree_path: Path, handoff_path: Path, log_path: Path, executor_command: str) -> None:
    args = shlex.split(executor_command)
    if not args:
        raise ControlPlaneValidationError("executor_command must not be empty")
    completed = subprocess.run(
        args,
        cwd=worktree_path,
        capture_output=True,
        text=True,
        check=False,
        env=_safe_command_env(),
    )
    output = (completed.stdout or "") + (completed.stderr or "")
    log_path.write_text(
        f"exit_code={completed.returncode}\ncommand=[redacted-command]\n\n{output}",
        encoding="utf-8",
    )
    handoff_path.write_text(output, encoding="utf-8")


def _run_codex_cli_executor(
    request: RealCodexRunRequest,
    *,
    workspace_path: Path,
    prompt_path: Path,
    handoff_path: Path,
    log_path: Path,
) -> int:
    prompt_text = prompt_path.read_text(encoding="utf-8")
    command = _build_codex_cli_command(
        request.codex_bin,
        codex_model=request.codex_model,
        codex_reasoning_effort=request.codex_reasoning_effort,
        sandbox_mode=request.sandbox_mode,
        workspace_path=workspace_path,
        handoff_path=handoff_path,
        extra_args=request.codex_args,
        prompt_text=prompt_text,
    )
    run_dir = log_path.parent.parent
    command_preview = _codex_command_preview(command)
    supervision = codex_supervision_config()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        "\n".join(
            (
                "exit_code=pending",
                f"command={json.dumps(command_preview, ensure_ascii=False)}",
                "",
                "STREAM:",
                "",
            )
        ),
        encoding="utf-8",
    )
    append_terminal_output(run_dir, f"\x1b[2mcommand={json.dumps(command_preview, ensure_ascii=False)}\x1b[0m\n")
    process = subprocess.Popen(
        command,
        cwd=workspace_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        env=_safe_command_env(),
        start_new_session=True,
    )
    try:
        process_group_id = os.getpgid(process.pid)
    except ProcessLookupError:
        process_group_id = process.pid
    write_process_started(
        run_dir,
        pid=process.pid,
        pgid=process_group_id,
        command_preview=command_preview,
        io_mode=str(supervision["effective_io_mode"]),
        max_wall_seconds=int(supervision["max_wall_seconds"]),
        no_output_seconds=int(supervision["no_output_seconds"]),
    )
    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []
    terminal_path = terminal_log_path(run_dir)
    terminal_path.parent.mkdir(parents=True, exist_ok=True)
    stream_lock = threading.Lock()

    def stream_pipe(pipe: Any, chunks: list[str], label: str) -> None:
        if pipe is None:
            return
        with log_path.open("a", encoding="utf-8") as log_handle, terminal_path.open("a", encoding="utf-8") as terminal_handle:
            log_handle.write(f"\n{label}:\n")
            pending = ""
            while True:
                chunk = pipe.read(1)
                if not chunk:
                    break
                chunks.append(chunk)
                pending += chunk
                with stream_lock:
                    log_handle.write(chunk)
                    log_handle.flush()
                update_process_activity(run_dir, output=True)
                if chunk in {"\n", "\r"} or len(pending) >= 2048:
                    sanitized = sanitize_terminal_text(terminalize_output(pending))
                    pending = ""
                    with stream_lock:
                        if sanitized:
                            terminal_handle.write(sanitized)
                            terminal_handle.flush()
            sanitized = sanitize_terminal_text(terminalize_output(pending))
            if sanitized:
                with stream_lock:
                    terminal_handle.write(sanitized)
                    terminal_handle.flush()

    threads = [
        threading.Thread(target=stream_pipe, args=(process.stdout, stdout_chunks, "STDOUT"), daemon=True),
        threading.Thread(target=stream_pipe, args=(process.stderr, stderr_chunks, "STDERR"), daemon=True),
    ]
    for thread in threads:
        thread.start()
    timeout_reason = None
    while True:
        returncode = process.poll()
        if returncode is not None:
            break
        assessment = codex_stale_assessment(run_dir)
        if assessment.get("status") == "stale_timeout":
            timeout_reason = str(assessment.get("blocker") or "Codex stale timeout")
            append_terminal_output(run_dir, f"\n\x1b[31mCodex watchdog timeout: {timeout_reason}\x1b[0m\n")
            append_live_event(
                run_dir,
                stage="stale_timeout",
                title="Codex watchdog marked run stale.",
                status="stale_timeout",
                level="error",
                detail=timeout_reason,
                source="watchdog",
                run_id=request.id,
                target_id=request.target_project_id,
            )
            terminate_run_owned_process_group(run_dir, reason=timeout_reason)
            returncode = 124
            break
        time.sleep(0.25)
    for thread in threads:
        thread.join(timeout=2)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"\nexit_code={returncode}\n")
    finalize_process_state(
        run_dir,
        status="stale_timeout" if timeout_reason else "exited",
        exit_code=returncode,
        timeout_reason=timeout_reason,
    )
    append_terminal_output(run_dir, f"\n\x1b[{'32' if returncode == 0 else '31'}mCodex exit_code={returncode}\x1b[0m\n")
    stdout = "".join(stdout_chunks)
    if not handoff_path.exists() and stdout.strip():
        handoff_path.write_text(stdout, encoding="utf-8")
    return returncode


def _build_codex_cli_command(
    codex_bin: str,
    *,
    codex_model: str,
    codex_reasoning_effort: str,
    sandbox_mode: str,
    workspace_path: Path,
    handoff_path: Path,
    extra_args: Sequence[str],
    prompt_text: str,
) -> list[str]:
    if not codex_bin.strip():
        raise ControlPlaneValidationError("codex binary must not be empty")
    command = [
        codex_bin,
        "exec",
        "--cd",
        str(workspace_path),
        "--sandbox",
        sandbox_mode,
        "--model",
        codex_model,
        "-c",
        f"model_reasoning_effort={json.dumps(codex_reasoning_effort)}",
        "--json",
        "--output-last-message",
        str(handoff_path),
    ]
    command.extend(str(arg) for arg in extra_args)
    command.append(prompt_text)
    return command


def _run_codex_workspace_preflight(
    workspace_path: Path,
    run_dir: Path,
    *,
    codex_bin: str,
    target_id: str | None = None,
    base_commit: str | None = None,
    prompt_text: str | None = None,
    codex_model: str | None = None,
    codex_reasoning_effort: str | None = None,
) -> tuple[CheckResult, ...]:
    checks_dir = run_dir / "verifier" / "preflight"
    checks_dir.mkdir(parents=True, exist_ok=True)
    command_env = _safe_command_env()
    toolchain = build_toolchain_status(env=command_env, workspace_path=workspace_path, codex_bin=codex_bin)
    (checks_dir / "toolchain.json").write_text(
        json.dumps(toolchain, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    requires_browser = requires_webcore_ui_browser_tools(target_id=target_id, prompt_text=prompt_text)
    runtime_parity = build_codex_runtime_parity_status(
        env=command_env,
        workspace_path=workspace_path,
        codex_bin=codex_bin,
        target_id=target_id,
        base_commit=base_commit,
        prompt_text=prompt_text,
        codex_model=codex_model,
        codex_reasoning_effort=codex_reasoning_effort,
        require_browser=requires_browser,
        launch_browser=requires_browser,
    )
    (checks_dir / "runtime_parity.json").write_text(
        json.dumps(runtime_parity, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    environment_parity = build_environment_parity_artifact(
        env=command_env,
        workspace_path=workspace_path,
        codex_bin=codex_bin,
        target_id=target_id or "unknown",
        base_commit=base_commit or "",
        prompt_text=prompt_text,
        codex_model=codex_model,
        codex_reasoning_effort=codex_reasoning_effort,
        launch_browser=requires_browser,
    )
    environment_parity_path = run_dir / "artifacts" / "environment_parity.json"
    environment_parity_path.parent.mkdir(parents=True, exist_ok=True)
    environment_parity_path.write_text(
        json.dumps(environment_parity, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    commands: tuple[tuple[str, Sequence[str]], ...] = (
        ("preflight_pwd", ("pwd",)),
        ("preflight_git_status", ("git", "status", "--short", "--branch")),
        ("preflight_rg_version", ("rg", "--version")),
        ("preflight_python3_version", ("python3", "--version")),
        ("preflight_jq_version", ("jq", "--version")),
        ("preflight_codex_version", (codex_bin, "--version")),
    )
    results: list[CheckResult] = []
    results.append(
        CheckResult(
            name="preflight_workspace_exists",
            status="passed" if workspace_path.exists() and workspace_path.is_dir() else "failed",
            reason=f"workspace exists: {workspace_path}" if workspace_path.exists() else f"workspace missing: {workspace_path}",
        )
    )
    write_check_path = workspace_path / ".dev-control-plane-write-check"
    try:
        write_check_path.write_text("ok\n", encoding="utf-8")
        write_check_path.unlink()
        results.append(CheckResult(name="preflight_workspace_write", status="passed", reason="workspace write check passed"))
    except Exception as exc:
        results.append(CheckResult(name="preflight_workspace_write", status="failed", reason=str(exc)))

    for missing in toolchain.get("missing_required", []):
        results.append(
            CheckResult(
                name=f"preflight_required_tool_{missing}",
                status="failed",
                output_path=str(checks_dir / "toolchain.json"),
                reason=f"missing required hosted tool: {missing}",
            )
        )
    for warning in toolchain.get("warnings", []):
        results.append(
            CheckResult(
                name=f"preflight_tool_warning_{_slug(str(warning))}",
                status="skipped",
                output_path=str(checks_dir / "toolchain.json"),
                reason=str(warning),
            )
        )
    codex = runtime_parity.get("codex") if isinstance(runtime_parity.get("codex"), Mapping) else {}
    if codex.get("auth_required"):
        results.append(
            CheckResult(
                name="preflight_codex_authenticated",
                status="passed" if codex.get("authenticated") else "failed",
                output_path=str(checks_dir / "runtime_parity.json"),
                reason=None if codex.get("authenticated") else str(codex.get("auth_blocker") or "Codex CLI is not authenticated"),
            )
        )
    missing_baseline = [
        name
        for name in runtime_parity.get("required_package_managers", [])
        if name in set(runtime_parity.get("missing_required", []))
    ]
    if missing_baseline:
        results.append(
            CheckResult(
                name="preflight_node_package_manager_baseline",
                status="failed",
                output_path=str(checks_dir / "runtime_parity.json"),
                reason=f"missing hosted Node/package-manager baseline tools: {', '.join(missing_baseline)}",
            )
        )
    elif runtime_parity.get("node_package_manager_baseline_required"):
        results.append(
            CheckResult(
                name="preflight_node_package_manager_baseline",
                status="passed",
                output_path=str(checks_dir / "runtime_parity.json"),
                reason="node/npm/corepack/pnpm/yarn baseline is ready",
            )
        )
    if runtime_parity.get("webcore_ui_browser_required"):
        results.append(
            CheckResult(
                name="preflight_webcore_ui_browser_ready",
                status="passed" if runtime_parity.get("webcore_ui_browser_ready") else "failed",
                output_path=str(checks_dir / "runtime_parity.json"),
                reason=None
                if runtime_parity.get("webcore_ui_browser_ready")
                else str((runtime_parity.get("browser") or {}).get("blocker") or "WebCore UI browser readiness is blocked"),
            )
        )
    for name, command in commands:
        output_path = checks_dir / f"{name}.txt"
        try:
            completed = subprocess.run(
                command,
                cwd=workspace_path,
                capture_output=True,
                text=True,
                check=False,
                timeout=15,
                env=command_env,
            )
            output = _command_output(completed)
        except Exception as exc:
            output = str(exc)
            completed = subprocess.CompletedProcess(command, 1, "", output)
        output_path.write_text(output, encoding="utf-8")
        results.append(
            CheckResult(
                name=name,
                status="passed" if completed.returncode == 0 else "failed",
                command=" ".join(command),
                output_path=str(output_path),
                reason=None if completed.returncode == 0 else output or f"{name} failed",
            )
        )
    return tuple(results)


def _codex_command_preview(command: Sequence[str]) -> list[str]:
    if not command:
        return []
    return [*command[:-1], "[prompt omitted]"]


def _command_failed(log_path: Path) -> bool:
    if not log_path.exists():
        return False
    first_line = log_path.read_text(encoding="utf-8").splitlines()[:1]
    return bool(first_line and first_line[0].strip() != "exit_code=0")


def _collect_changed_files(worktree_path: Path) -> tuple[str, ...]:
    paths: set[str] = set()
    for command in (
        ("status", "--short", "--untracked-files=all"),
        ("diff", "--name-only"),
        ("diff", "--cached", "--name-only"),
    ):
        result = _git(worktree_path, *command)
        if result.returncode != 0:
            continue
        for line in result.stdout.splitlines():
            path = _parse_changed_file_line(line, command[0])
            if path:
                paths.add(_normalize_repo_path(path))
    return tuple(sorted(paths))


def _merged_changed_files(result: Mapping[str, Any], worktree_path: Path | None) -> tuple[str, ...]:
    changed: set[str] = set(_normalize_repo_path(path) for path in result.get("changed_files", []) if str(path).strip())
    if worktree_path and worktree_path.exists():
        changed.update(_collect_changed_files(worktree_path))
    return tuple(sorted(changed))


def _merged_target_changed_files(result: Mapping[str, Any], workspace_path: Path | None) -> tuple[str, ...]:
    changed: set[str] = set(_normalize_repo_path(path) for path in result.get("changed_files", []) if str(path).strip())
    if workspace_path and workspace_path.exists():
        changed.update(_collect_changed_files(workspace_path))
    return tuple(sorted(changed))


def _write_diff_artifact(workspace_path: Path, diff_path: Path) -> None:
    workspace_path = workspace_path.resolve()
    diff_path.parent.mkdir(parents=True, exist_ok=True)
    _git(workspace_path, "add", "-N", ".")
    diff = _git(workspace_path, "diff", "--binary", "HEAD", "--", ".")
    output = _command_output(diff)
    diff_path.write_text(output, encoding="utf-8")


def _parse_changed_file_line(line: str, command_name: str) -> str:
    if command_name != "status":
        return line.strip()
    if len(line) < 4:
        return ""
    path = line[3:].strip()
    if " -> " in path:
        path = path.split(" -> ", 1)[1].strip()
    return path


def _forbidden_path_hits(paths: Sequence[str], forbidden_patterns: Sequence[str]) -> tuple[str, ...]:
    hits: list[str] = []
    for path in paths:
        normalized = _normalize_repo_path(path)
        if any(_path_matches(normalized, pattern) for pattern in forbidden_patterns):
            hits.append(normalized)
    return tuple(sorted(set(hits)))


def _allowed_path_violations(paths: Sequence[str], allowed_patterns: Sequence[str]) -> tuple[str, ...]:
    violations: list[str] = []
    for path in paths:
        normalized = _normalize_repo_path(path)
        if not any(_path_matches(normalized, pattern) for pattern in allowed_patterns):
            violations.append(normalized)
    return tuple(sorted(set(violations)))


def _path_matches(path: str, pattern: str) -> bool:
    normalized_pattern = _normalize_repo_path(pattern)
    if fnmatch.fnmatchcase(path, normalized_pattern):
        return True
    if normalized_pattern.endswith("/**"):
        return path.startswith(normalized_pattern[:-3] + "/")
    return False


def _fake_executor_policy_check(request: Mapping[str, Any]) -> CheckResult:
    if request.get("executor_mode") != "fake":
        return CheckResult(name="fake_executor_policy", status="skipped", reason="executor mode is not fake")
    if request.get("executor_command"):
        return CheckResult(
            name="fake_executor_policy",
            status="failed",
            reason="fake executor metadata unexpectedly includes executor_command",
        )
    return CheckResult(name="fake_executor_policy", status="passed", reason="no command executed in fake mode")


def _managed_workspace_policy_check(
    request: Mapping[str, Any],
    result: Mapping[str, Any],
    run_dir: Path,
) -> CheckResult:
    if request.get("workspace_strategy") != "managed_clone":
        return CheckResult(
            name="managed_workspace_policy",
            status="failed",
            reason="target run must use managed_clone workspace strategy",
        )
    workspace_raw = result.get("workspace_path")
    if not workspace_raw:
        return CheckResult(name="managed_workspace_policy", status="failed", reason="workspace_path is missing")
    workspace_path = Path(str(workspace_raw)).resolve()
    workspace_owner = _workspace_owner_from_request(request, result, run_dir)
    if not _is_relative_to(workspace_path, workspace_owner) and not _is_relative_to(workspace_path, run_dir.resolve()):
        return CheckResult(
            name="managed_workspace_policy",
            status="failed",
            reason=f"workspace path is outside owned state workspace: {workspace_path}",
        )
    original_repo_raw = request.get("original_repo_path")
    if original_repo_raw and not _is_urlish(original_repo_raw) and _same_path_or_child(
        workspace_path,
        Path(str(original_repo_raw)).resolve(),
    ):
        return CheckResult(
            name="managed_workspace_policy",
            status="failed",
            reason="workspace path overlaps original target repo",
        )
    return CheckResult(name="managed_workspace_policy", status="passed", reason="workspace is managed under state workspaces")


def _target_repo_unchanged_check(request: Mapping[str, Any]) -> CheckResult:
    source_mode = str(request.get("target_source_mode") or "local_path")
    original_repo_raw = request.get("original_repo_path")
    if not original_repo_raw:
        return CheckResult(name="target_repo_unchanged", status="failed", reason="original_repo_path is missing")
    if source_mode == "remote_managed_clone" or _is_urlish(original_repo_raw):
        return CheckResult(
            name="target_repo_unchanged",
            status="passed",
            reason="remote managed clone source has no original target worktree to mutate",
        )
    repo = Path(str(original_repo_raw)).resolve()
    if not repo.exists():
        return CheckResult(name="target_repo_unchanged", status="failed", reason=f"original repo missing: {repo}")
    current_head = _git_output(repo, "rev-parse", "HEAD")
    current_status = _git_output(repo, "status", "--short")
    expected_head = str(request.get("original_head") or "")
    expected_status = str(request.get("original_status_before") or "")
    if current_head != expected_head:
        return CheckResult(
            name="target_repo_unchanged",
            status="failed",
            reason=f"original target HEAD changed: expected {expected_head}, got {current_head}",
        )
    if current_status != expected_status:
        return CheckResult(
            name="target_repo_unchanged",
            status="failed",
            reason="original target working tree status changed during run",
        )
    return CheckResult(name="target_repo_unchanged", status="passed", reason="original target repo unchanged")


def _codex_cli_exit_check(result: Mapping[str, Any]) -> CheckResult:
    exit_code = result.get("codex_exit_code")
    if exit_code is None:
        return CheckResult(name="codex_cli_exit", status="skipped", reason="Codex CLI was not executed")
    if exit_code == 0:
        return CheckResult(name="codex_cli_exit", status="passed", reason="Codex CLI exited 0")
    return CheckResult(name="codex_cli_exit", status="failed", reason=f"Codex CLI exited non-zero: {exit_code}")


def _live_actions_stay_forbidden_check(task_spec: TaskSpec) -> CheckResult:
    forbidden_actions = {str(action) for action in task_spec.forbidden_actions}
    missing = [action for action in CODEX_CLI_FORBIDDEN_ACTIONS if action not in forbidden_actions]
    if missing:
        return CheckResult(
            name="live_actions_stay_forbidden",
            status="failed",
            reason=f"required forbidden actions missing: {missing}",
        )
    return CheckResult(name="live_actions_stay_forbidden", status="passed", reason="live/deploy/SSH/root remain forbidden")


def _git_diff_check(worktree_path: Path | None, checks_dir: Path) -> CheckResult:
    if not worktree_path or not worktree_path.exists():
        return CheckResult(name="git_diff_check", status="skipped", reason="worktree is not available")
    output_path = checks_dir / "git_diff_check.txt"
    result = _git(worktree_path, "diff", "--check")
    output = _command_output(result)
    output_path.write_text(output, encoding="utf-8")
    return CheckResult(
        name="git_diff_check",
        status="passed" if result.returncode == 0 else "failed",
        command="git diff --check",
        output_path=str(output_path),
        reason=None if result.returncode == 0 else output or "git diff --check failed",
    )


def _run_status_from_verifier(verifier: VerifierResult) -> RunStatus:
    if verifier.status == "passed":
        return "verifier_passed"
    if verifier.status == "blocked":
        return "blocked"
    return "failed"


def _next_manual_step(status: RunStatus, blocker_reason: str | None) -> str | None:
    if status not in {"blocked", "failed", "human_gate_required"}:
        return None
    if blocker_reason and "отчёт не соответствует handoff contract" in blocker_reason:
        return "Повторите запуск после исправления prompt contract или проверьте handoff вручную."
    return blocker_reason or "Inspect run artifacts and verifier output."


def _state_layout_or_raise(state_dir: Path) -> ControlPlaneStateLayout:
    try:
        layout = ControlPlaneStateLayout.from_path(state_dir)
        layout.ensure_base_dirs()
        return layout
    except StateLayoutError as exc:
        raise ControlPlaneExecutionError(str(exc)) from exc


def _workspace_owner_for_run_dir(run_dir: Path, workspace_id: str | None = None) -> Path:
    run_dir = run_dir.resolve()
    if run_dir.parent.name == "runs":
        try:
            run_layout = ControlPlaneStateLayout.from_path(run_dir.parent.parent).run_layout(run_dir.name)
            return run_layout.workspace_dir(workspace_id) if workspace_id else run_layout.workspace_root
        except StateLayoutError as exc:
            raise ControlPlaneExecutionError(str(exc)) from exc
    return (run_dir / "workspace").resolve()


def _workspace_owner_from_metadata(metadata: Mapping[str, Any], run_dir: Path) -> Path:
    request = metadata.get("request", {})
    result = metadata.get("result", {})
    if isinstance(request, Mapping) and isinstance(result, Mapping):
        return _workspace_owner_from_request(request, result, run_dir)
    return _workspace_owner_for_run_dir(run_dir)


def _workspace_owner_from_request(request: Mapping[str, Any], result: Mapping[str, Any], run_dir: Path) -> Path:
    state_raw = request.get("state_dir")
    run_id = str(result.get("id") or request.get("id") or run_dir.name)
    if state_raw:
        try:
            return ControlPlaneStateLayout.from_path(Path(str(state_raw))).run_layout(run_id).workspace_root
        except StateLayoutError:
            return (run_dir / "workspace").resolve()
    return _workspace_owner_for_run_dir(run_dir)


def _verifier_result_path(run_dir: Path) -> Path:
    return run_dir / "verifier" / "verifier.json"


def _handoff_contract_violations(handoff_text: str) -> list[str]:
    violations: list[str] = []
    missing = [block for block in MANDATORY_HANDOFF_BLOCKS if block not in handoff_text]
    if missing:
        violations.append("отсутствует " + ", ".join(missing))
    first_non_empty = next((line.strip() for line in handoff_text.splitlines() if line.strip()), "")
    if MANDATORY_HANDOFF_BLOCKS[0] in handoff_text and first_non_empty != MANDATORY_HANDOFF_BLOCKS[0]:
        violations.append(f"{MANDATORY_HANDOFF_BLOCKS[0]} должен быть первой строкой финального ответа")
    return violations


def _handoff_contract_reason(violations: Sequence[str]) -> str | None:
    if not violations:
        return None
    return (
        "Codex выполнил изменения, но отчёт не соответствует handoff contract: "
        + "; ".join(violations)
    )


def _only_failed_check(checks: Sequence[CheckResult], name: str) -> bool:
    failed = [check.name for check in checks if check.status == "failed"]
    return failed == [name]


def _check_failed(checks: Sequence[CheckResult], name: str) -> bool:
    return any(check.name == name and check.status == "failed" for check in checks)


def _check_reason(checks: Sequence[CheckResult], name: str) -> str | None:
    for check in checks:
        if check.name == name:
            return check.reason
    return None


def _resolve_repo_root(repo_root: Path) -> Path:
    candidate = repo_root.resolve()
    result = _git(candidate, "rev-parse", "--show-toplevel")
    if result.returncode != 0:
        raise ControlPlaneExecutionError(_command_output(result) or f"not a git repo: {candidate}")
    actual = Path(result.stdout.strip()).resolve()
    if actual != candidate:
        raise ControlPlaneExecutionError(f"repo_root must be git toplevel: expected {actual}, got {candidate}")
    return actual


def _git_output(cwd: Path, *args: str) -> str:
    result = _git(cwd, *args)
    if result.returncode != 0:
        raise ControlPlaneExecutionError(_command_output(result) or f"git {' '.join(args)} failed")
    return result.stdout.strip()


def _git_checked(cwd: Path, *args: str) -> None:
    result = _git(cwd, *args)
    if result.returncode != 0:
        raise ControlPlaneExecutionError(_command_output(result) or f"git {' '.join(args)} failed")


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(("git", *args), cwd=cwd, capture_output=True, text=True, check=False, env=_safe_command_env())


def _branch_exists(repo_root: Path, branch_name: str) -> bool:
    result = _git(repo_root, "rev-parse", "--verify", "--quiet", branch_name)
    return result.returncode == 0


def _command_output(result: subprocess.CompletedProcess[str]) -> str:
    return "\n".join(part for part in (result.stdout.strip(), result.stderr.strip()) if part)


def _safe_command_env() -> dict[str, str]:
    return runtime_command_env(git_prompt=True)


def _write_run_metadata(
    run_dir: Path,
    request: RunRequest,
    task_spec_payload: Mapping[str, Any],
    step: SprintStep,
    result: RunResult,
) -> None:
    payload = {
        "schema_version": 1,
        "request": run_request_to_dict(request),
        "task_spec": _json_ready(dict(task_spec_payload)),
        "sprint_step": sprint_step_to_dict(step),
        "result": run_result_to_dict(result),
        "updated_at": _now_utc(),
    }
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / RUN_METADATA_FILE).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_target_run_metadata(
    run_dir: Path,
    request: RealCodexRunRequest,
    target_config: TargetProjectConfig,
    task_spec_payload: Mapping[str, Any],
    step: SprintStep,
    result: RealCodexRunResult,
    workspace: ManagedWorkspaceMetadata,
) -> None:
    request_payload = real_codex_run_request_to_dict(request)
    request_payload.update(
        {
            "original_repo_path": workspace.original_repo_path,
            "original_head": workspace.original_head,
            "original_status_before": workspace.original_status_before,
            "target_source_mode": getattr(target_config, "source_mode", "local_path"),
            "target_repo_url": getattr(target_config, "repo_url", None),
            "target_branch": getattr(target_config, "branch", "main"),
        }
    )
    payload = {
        "schema_version": 2,
        "request": request_payload,
        "target_project": target_project_config_to_dict(target_config),
        "workspace": managed_workspace_metadata_to_dict(workspace),
        "task_spec": _json_ready(dict(task_spec_payload)),
        "sprint_step": sprint_step_to_dict(step),
        "result": real_codex_run_result_to_dict(result),
        "updated_at": _now_utc(),
    }
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / RUN_METADATA_FILE).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_verifier_result(run_dir: Path, verifier: VerifierResult) -> None:
    path = _verifier_result_path(run_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(verifier_result_to_dict(verifier), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _read_run_metadata(run_dir: Path) -> dict[str, Any]:
    path = run_dir / RUN_METADATA_FILE
    if not path.exists():
        raise ControlPlaneExecutionError(f"run metadata not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ControlPlaneExecutionError("run metadata must be a JSON object")
    for key in ("request", "task_spec", "result"):
        if key not in payload or not isinstance(payload[key], dict):
            raise ControlPlaneExecutionError(f"run metadata missing object: {key}")
    return payload


def run_request_to_dict(request: RunRequest) -> dict[str, Any]:
    return _json_ready(asdict(request))


def _new_run_id(task_spec: TaskSpec, step: SprintStep) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"run-{_slug(task_spec.id)[:32]}-{_slug(step.id)[:32]}-{timestamp}-{uuid.uuid4().hex[:8]}"


def _slug(value: str) -> str:
    return slug_state_component(value)


def _now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _normalize_repo_path(path: Any) -> str:
    return str(path).strip().replace("\\", "/").lstrip("./")


def _is_urlish(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return text.startswith(("https://", "http://", "ssh://", "git@", "file://"))


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


def _same_path_or_child(path: Path, parent: Path) -> bool:
    path = path.resolve()
    parent = parent.resolve()
    return path == parent or _is_relative_to(path, parent)
