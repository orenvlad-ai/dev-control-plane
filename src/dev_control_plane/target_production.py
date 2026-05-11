"""Explicit production apply/deploy lane for the wb-core target project.

The lane consumes verifier-passed managed-clone output. It never uses the
original target checkout as an execution workspace and never pushes directly to
main. Mutating execution is available only through an explicit CLI path; server
API exposure is plan/decision oriented.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import time
from typing import Any
from urllib import request as urllib_request

from dev_control_plane.github_auth import build_github_auth_status, github_command_env
from dev_control_plane.ssh_deploy import build_ssh_deploy_status, ssh_command_env, ssh_deploy_command
from dev_control_plane.state_layout import safe_state_component, slug_state_component
from dev_control_plane.toolchain import build_toolchain_status, runtime_command_env

TARGET_PROJECT_ID = "wb-core"
TARGET_REPO = "orenvlad-ai/wb-core"
TARGET_REPO_URL = "https://github.com/orenvlad-ai/wb-core.git"
BASE_BRANCH = "main"
BRANCH_PREFIX = "devcp"
DEFAULT_DEPLOY_RUNNER = "apps/registry_upload_http_entrypoint_hosted_runtime.py"
DEFAULT_DEPLOY_TARGET_FILE = "artifacts/registry_upload_http_entrypoint/input/hosted_runtime_target__europe_api.json"
PUBLIC_OPERATOR_URL = "https://api.selleros.pro/sheet-vitrina-v1/operator"
PUBLIC_BASE_URL = "https://api.selleros.pro"
APP_BACKUP_DIR = "/opt/wb-core-runtime/backups/dev-control-plane"
TARGET_PRODUCTION_LOCK_STALE_SECONDS_ENV = "DEV_CONTROL_PLANE_TARGET_PRODUCTION_LOCK_STALE_SECONDS"
DEFAULT_TARGET_PRODUCTION_LOCK_STALE_SECONDS = 4 * 60 * 60
PRODUCTION_DIFF_MISMATCH_BLOCKER = "promotion workspace diff does not match verified diff; do not deploy"

DERIVED_PACK_PREFIX = "wb_core_docs_master/"
DOCSET_MANIFEST = "99_MANIFEST__DOCSET_VERSION.md"
FORBIDDEN_DEPLOY_PATHS = (
    "runtime/",
    "deploy/",
    "infra/",
    "artifacts/registry_upload_http_entrypoint/",
    DERIVED_PACK_PREFIX,
    DOCSET_MANIFEST,
)
SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"Authorization\s*:\s*Bearer\s+\S+", re.IGNORECASE),
    re.compile(r"BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY"),
    re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
)
IGNORED_CHANGED_FILE_PREFIXES = (
    ".git/",
    ".pytest_cache/",
    ".ruff_cache/",
    "__pycache__/",
    "node_modules/",
)
IGNORED_CHANGED_FILE_SUFFIXES = (
    ".pyc",
    ".pyo",
)

CommandRunner = Callable[[Sequence[str], Path | None], subprocess.CompletedProcess[str]]


class ProductionDiffMismatchError(RuntimeError):
    def __init__(self, diagnostics: Mapping[str, Any]) -> None:
        super().__init__(PRODUCTION_DIFF_MISMATCH_BLOCKER)
        self.diagnostics = dict(diagnostics)


@dataclass(frozen=True)
class TargetProductionDecision:
    status: str
    allowed: bool
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    plan: dict[str, Any]


@dataclass(frozen=True)
class TargetProductionResult:
    status: str
    allowed: bool
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    plan: dict[str, Any]
    executed_steps: tuple[str, ...]
    target_branch: str | None = None
    target_pr_url: str | None = None
    target_pr_number: int | None = None
    pre_merge_main_commit: str | None = None
    merge_commit: str | None = None
    backup_path: str | None = None
    deploy_status: str | None = None
    public_verify_status: str | None = None
    rollback_plan_path: str | None = None


@dataclass(frozen=True)
class TargetProductionResumeResult:
    status: str
    allowed: bool
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    plan: dict[str, Any]
    executed_steps: tuple[str, ...]
    run_id: str
    target_pr_url: str | None = None
    target_pr_number: int | None = None
    merge_commit: str | None = None
    backup_path: str | None = None
    deploy_status: str | None = None
    public_verify_status: str | None = None
    rollback_plan_path: str | None = None
    resume_report_path: str | None = None


@dataclass(frozen=True)
class TargetProductionLock:
    lock_path: Path
    run_id: str
    token: str


def build_wb_core_production_plan(payload: Mapping[str, Any]) -> TargetProductionDecision:
    """Build and gate the wb-core production lane plan."""

    blockers: list[str] = []
    warnings: list[str] = []

    target_project_id = _text(payload.get("target_project_id") or TARGET_PROJECT_ID)
    target_repo = _text(payload.get("target_repo") or TARGET_REPO)
    target_repo_url = _text(payload.get("target_repo_url") or TARGET_REPO_URL)
    base_branch = _text(payload.get("base_branch") or BASE_BRANCH)
    run_id = _required_slug(payload.get("run_id"), fallback="run")
    task_slug = slug_state_component(_text(payload.get("task_slug") or payload.get("task_spec_id") or "task"))
    branch_name = _text(payload.get("branch_name")) or f"{BRANCH_PREFIX}/{run_id[:48]}-{task_slug[:48]}"
    changed_files = normalize_changed_files(_sequence(payload.get("changed_files")))
    deploy_runner = _text(payload.get("deploy_runner") or DEFAULT_DEPLOY_RUNNER)
    deploy_target_file = _text(payload.get("deploy_target_file") or DEFAULT_DEPLOY_TARGET_FILE)
    workspace_path = _optional_path(payload.get("workspace_path"))
    run_dir = _optional_path(payload.get("run_dir"))
    expected_label = _text(payload.get("expected_public_label"))
    execution_mode = _text(payload.get("execution_mode") or payload.get("apply_mode") or "production_lane")
    production_lane = _bool(payload.get("production_lane")) if "production_lane" in payload else True
    run_start_base_ref = _text(payload.get("run_start_base_ref") or payload.get("base_ref"))
    diff_artifact_path = _text(payload.get("diff_path") or payload.get("diff_artifact_path"))
    verified_workspace_source = _bool(payload.get("verified_workspace_source") or payload.get("use_verified_workspace_as_source"))

    if execution_mode not in {"production_lane", "target_pr_merge_deploy"}:
        blockers.append("production-lane endpoint requires execution_mode/apply_mode=production_lane")
    if not production_lane:
        blockers.append("production_lane flag must be true for target PR/merge/deploy execution")

    if target_project_id != TARGET_PROJECT_ID:
        blockers.append(f"production lane target_project_id must be {TARGET_PROJECT_ID}")
    if target_repo != TARGET_REPO:
        blockers.append(f"production lane target repo must be {TARGET_REPO}")
    if target_repo_url != TARGET_REPO_URL:
        blockers.append(f"production lane repo_url must be {TARGET_REPO_URL}")
    if base_branch != BASE_BRANCH:
        blockers.append("production lane base branch must be main")
    if not branch_name.startswith(f"{BRANCH_PREFIX}/"):
        blockers.append("target branch must use devcp/ prefix")
    if _bool(payload.get("push_to_main")):
        blockers.append("direct push to main is forbidden")
    if _bool(payload.get("direct_target_mutation")):
        blockers.append("direct target mutation is forbidden")
    if str(payload.get("verifier_status") or "").lower() != "passed":
        blockers.append("verifier must pass before target PR/merge/deploy")
    if _sequence(payload.get("forbidden_path_hits")):
        blockers.append("forbidden path changes detected")
    if str(payload.get("secrets_scan_status") or "passed") != "passed":
        blockers.append("secrets scan must pass before target PR/merge/deploy")
    if _text(payload.get("blocker")):
        blockers.append(f"blocker is present: {_text(payload.get('blocker'))}")
    if not changed_files:
        blockers.append("changed_files are required for production lane")

    protected_hits = _protected_path_hits(changed_files)
    if protected_hits:
        blockers.append("protected/forbidden target paths changed: " + ", ".join(protected_hits))

    commit_message = _text(payload.get("commit_message")) or f"Изменить UI label через DevControl ({run_id})"
    pr_title = _text(payload.get("pr_title")) or "Изменить UI label через DevControl"
    if not _contains_cyrillic(commit_message):
        blockers.append("target commit message must be in Russian")
    if not _contains_cyrillic(pr_title):
        blockers.append("target PR title must be in Russian")

    rules_summary: dict[str, Any] = {}
    if workspace_path:
        try:
            rules_summary = load_wb_core_rules_summary(workspace_path)
        except ValueError as exc:
            blockers.append(str(exc))
    else:
        blockers.append("managed workspace_path is required")
    if rules_summary:
        missing_required_rules = [
            key
            for key in ("README.md", "docs/architecture", "docs/modules")
            if not rules_summary.get("required_sources", {}).get(key)
        ]
        if missing_required_rules:
            blockers.append("target rules/source paths missing: " + ", ".join(missing_required_rules))
        if not rules_summary.get("deploy_runner_found"):
            blockers.append(f"approved WebCore deploy runner not found: {deploy_runner}")
        if not rules_summary.get("deploy_target_file_found"):
            blockers.append(f"approved WebCore deploy target file not found: {deploy_target_file}")

    if workspace_path and changed_files:
        secret_hits = scan_changed_files_for_secrets(workspace_path, changed_files)
        if secret_hits:
            blockers.append("secret-like content detected in changed files: " + ", ".join(secret_hits))

    lock_status = inspect_wb_core_production_lock(workspace_path=workspace_path, run_dir=run_dir, run_id=run_id)
    if lock_status["status"] == "active":
        blockers.append(
            "wb-core production lane is locked by active run "
            f"{lock_status.get('run_id')}; lock_path={lock_status.get('lock_path')}"
        )
    elif lock_status["status"] == "stale":
        blockers.append(
            "wb-core production lane has a stale lock; manual cleanup required after verifying no deploy is running: "
            f"{lock_status.get('lock_path')}"
        )

    rollback_plan = build_rollback_plan(
        run_id=run_id,
        branch_name=branch_name,
        pre_merge_main_commit=_text(payload.get("pre_merge_main_commit")) or "<recorded-before-merge>",
        merge_commit=_text(payload.get("merge_commit")) or "<recorded-after-merge>",
        deploy_runner=deploy_runner,
        deploy_target_file=deploy_target_file,
    )
    if not rollback_plan.get("commands"):
        blockers.append("rollback plan is required before deploy")

    pr_body = _target_pr_body(
        task_summary=_text(payload.get("task_summary") or payload.get("task_spec_summary") or "Микрозадача DevControl."),
        run_id=run_id,
        changed_files=changed_files,
        verifier_status=str(payload.get("verifier_status") or "unknown"),
        docs_update_status=_text(payload.get("docs_update_status") or "not_required"),
        deploy_runner=deploy_runner,
        rollback_plan=rollback_plan,
        expected_label=expected_label,
    )

    plan = {
        "target_project_id": TARGET_PROJECT_ID,
        "target_repo": TARGET_REPO,
        "target_repo_url": TARGET_REPO_URL,
        "base_branch": BASE_BRANCH,
        "source_mode": "remote_managed_clone",
        "execution_mode": "production_lane",
        "apply_mode": "target_pr_merge_deploy",
        "production_lane": True,
        "workspace_path": str(workspace_path) if workspace_path else None,
        "run_dir": str(run_dir) if run_dir else None,
        "run_id": run_id,
        "branch_name": branch_name,
        "commit_message": commit_message,
        "pr_title": pr_title,
        "pr_body": pr_body,
        "changed_files": list(changed_files),
        "verifier_changed_files": list(changed_files),
        "diff_artifact_path": diff_artifact_path or None,
        "diff_artifact_transport_used": not verified_workspace_source,
        "verified_workspace_source": verified_workspace_source,
        "deploy_runner": deploy_runner,
        "deploy_target_file": deploy_target_file,
        "deploy_commands": _deploy_commands(deploy_runner),
        "deploy_ssh_target": "configured-at-runtime",
        "public_operator_url": PUBLIC_OPERATOR_URL,
        "public_base_url": PUBLIC_BASE_URL,
        "expected_public_label": expected_label or None,
        "run_start_base_ref": run_start_base_ref or None,
        "rollback_plan": rollback_plan,
        "lock": lock_status,
        "target_rules": rules_summary,
        "status_sequence": [
            "managed_clone_done",
            "codex_done",
            "verifier_passed",
            "pr_created",
            "pr_merged",
            "backup_created",
            "deploy_started",
            "deploy_passed",
            "post_deploy_passed",
        ],
        "forbidden": {
            "push_directly_to_main": True,
            "deploy_without_merged_pr": True,
            "deploy_without_verifier": True,
            "deploy_without_rollback_plan": True,
            "external_wb_live_actions": True,
            "db_migrations_without_policy": True,
        },
    }
    return TargetProductionDecision(
        status="allowed" if not blockers else "denied",
        allowed=not blockers,
        blockers=tuple(blockers),
        warnings=tuple(warnings),
        plan=plan,
    )


def execute_wb_core_production_lane(
    payload: Mapping[str, Any],
    *,
    execute: bool = False,
    runner: CommandRunner | None = None,
) -> TargetProductionResult:
    """Execute or dry-run the wb-core production lane.

    This function intentionally shells out to `git`, `gh`, `ssh` and the target
    repo deploy runner only after `build_wb_core_production_plan` allows the
    payload. With `execute=False` it returns the exact command plan without
    target or server mutation.
    """

    decision = build_wb_core_production_plan(payload)
    if not decision.allowed:
        return TargetProductionResult(
            status="blocked",
            allowed=False,
            blockers=decision.blockers,
            warnings=decision.warnings,
            plan=decision.plan,
            executed_steps=(),
        )

    plan = dict(decision.plan)
    workspace = Path(str(plan["workspace_path"])).resolve()
    run_dir = _production_artifacts_dir(_optional_path(plan.get("run_dir")), workspace, plan["run_id"])
    run_dir.mkdir(parents=True, exist_ok=True)
    rollback_plan_path = run_dir / "rollback_plan.json"
    _write_rollback_plan(rollback_plan_path, plan)
    plan["rollback_plan_path"] = str(rollback_plan_path)

    commands = _execution_commands(plan)
    plan["execution_commands"] = commands
    if not execute:
        return TargetProductionResult(
            status="dry_run_ready",
            allowed=True,
            blockers=(),
            warnings=decision.warnings,
            plan=plan,
            executed_steps=("dry_run",),
            rollback_plan_path=str(rollback_plan_path),
        )

    command_runner = runner or _run_command
    executed: list[str] = []
    pr_url: str | None = None
    pr_number: int | None = None
    pre_merge_main: str | None = None
    merge_commit: str | None = None
    backup_path: str | None = None
    public_probe_payload: dict[str, Any] | None = None
    target_branch = str(plan["branch_name"])
    lock: TargetProductionLock | None = None

    try:
        plan["toolchain_preflight"] = _production_lane_toolchain_preflight(
            workspace=workspace,
            artifacts_dir=run_dir,
            env=_production_preflight_env(),
            github_runner=_github_auth_runner_from_command_runner(command_runner),
        )
        executed.append("production_toolchain_preflight")
        github_env = github_command_env(env=os.environ, askpass_dir=run_dir / "preflight")
        lock = acquire_wb_core_production_lock(workspace_path=workspace, run_dir=run_dir, run_id=str(plan["run_id"]))
        plan["lock"] = {"status": "acquired", "lock_path": str(lock.lock_path), "run_id": lock.run_id}
        executed.append("target_lock_acquired")
        _ensure_tool("gh", command_runner)
        if plan.get("verified_workspace_source"):
            plan["diff_apply_status"] = "not_used_verified_workspace_source"
            _prepare_verified_workspace_source_for_commit(workspace, plan)
        else:
            _prepare_workspace_for_verified_diff(workspace, plan, run_dir=run_dir)
        _ensure_clean_expected_workspace(
            workspace,
            plan["changed_files"],
            diagnostics_path=run_dir / "production_diff_gate.json",
            verifier_base_commit=plan.get("verifier_base_commit"),
            run_start_base_ref=plan.get("run_start_base_ref"),
            promotion_base_commit=plan.get("promotion_base_commit"),
            diff_artifact_path=plan.get("diff_artifact_path"),
            diff_apply_status=plan.get("diff_apply_status"),
            plan=plan,
        )
        pre_merge_main = _git_stdout(workspace, "ls-remote", "origin", f"refs/heads/{BASE_BRANCH}").split()[0]
        if plan.get("run_start_base_ref") and pre_merge_main != plan["run_start_base_ref"]:
            raise RuntimeError(
                "origin/main changed since managed clone start; re-run verifier on the current target main before production deploy"
            )
        _write_rollback_plan(rollback_plan_path, plan, pre_merge_main_commit=pre_merge_main)
        _git_checked(workspace, "fetch", "origin", BASE_BRANCH)
        _git_checked(workspace, "checkout", "-B", target_branch)
        _git_checked(workspace, "config", "user.name", "DevControl Plane")
        _git_checked(workspace, "config", "user.email", "devcontrol-plane@example.invalid")
        _git_checked(workspace, "add", "--", *plan["changed_files"])
        _git_checked(workspace, "commit", "-m", plan["commit_message"])
        executed.append("target_commit")
        committed_files = normalize_changed_files(_git_stdout(workspace, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD").splitlines())
        plan["committed_changed_files"] = list(committed_files)
        if committed_files != normalize_changed_files(plan["changed_files"]):
            raise RuntimeError("committed files do not match verified changed_files; do not deploy")
        target_head = _git_stdout(workspace, "rev-parse", "HEAD")
        _run_or_raise(command_runner, ["git", "push", "-u", "origin", target_branch], workspace, env=github_env)
        executed.append("target_push")

        pr_body_path = run_dir / "target_pr_body.md"
        pr_body_path.write_text(plan["pr_body"], encoding="utf-8")
        pr_create = _run_or_raise(
            command_runner,
            [
                "gh",
                "pr",
                "create",
                "--repo",
                TARGET_REPO,
                "--base",
                BASE_BRANCH,
                "--head",
                target_branch,
                "--title",
                plan["pr_title"],
                "--body-file",
                str(pr_body_path),
            ],
            workspace,
            env=github_env,
        )
        pr_url = pr_create.stdout.strip().splitlines()[-1]
        pr_view = _gh_json(
            command_runner,
            workspace,
            "pr",
            "view",
            pr_url,
            "--repo",
            TARGET_REPO,
            "--json",
            "number,state,headRefOid,url",
            env=github_env,
        )
        if pr_view.get("state") != "OPEN":
            raise RuntimeError(f"target PR is not open: {pr_view}")
        if pr_view.get("headRefOid") != target_head:
            raise RuntimeError("target PR head SHA does not match committed head")
        pr_number = int(pr_view["number"])
        executed.append("target_pr_created")

        _run_or_raise(
            command_runner,
            ["gh", "pr", "merge", str(pr_number), "--repo", TARGET_REPO, "--merge", "--delete-branch"],
            workspace,
            env=github_env,
        )
        merged = _gh_json(command_runner, workspace, "pr", "view", str(pr_number), "--repo", TARGET_REPO, "--json", "state,mergeCommit,url", env=github_env)
        if merged.get("state") != "MERGED":
            raise RuntimeError(f"target PR did not merge: {merged}")
        merge_commit = str((merged.get("mergeCommit") or {}).get("oid") or "")
        if not merge_commit:
            raise RuntimeError("target PR merge commit is missing")
        _write_rollback_plan(rollback_plan_path, plan, pre_merge_main_commit=pre_merge_main, merge_commit=merge_commit)
        executed.append("target_pr_merged")

        _git_checked(workspace, "checkout", BASE_BRANCH)
        _run_or_raise(command_runner, ["git", "pull", "--ff-only", "origin", BASE_BRANCH], workspace, env=github_env)
        head_after_pull = _git_stdout(workspace, "rev-parse", "HEAD")
        if head_after_pull != merge_commit:
            raise RuntimeError(f"deploy checkout is not merged PR commit: {head_after_pull} != {merge_commit}")

        backup_path = _create_remote_app_backup(command_runner, workspace, plan["run_id"], env=os.environ)
        executed.append("backup_created")
        deploy_env = {**os.environ, **runtime_command_env(os.environ), "WB_CORE_HOSTED_RUNTIME_TARGET_FILE": plan["deploy_target_file"]}
        for step, command in (
            ("print_plan", ["python3", plan["deploy_runner"], "print-plan"]),
            ("deploy_dry_run", ["python3", plan["deploy_runner"], "deploy", "--dry-run"]),
            ("deploy_live", ["python3", plan["deploy_runner"], "deploy"]),
            ("loopback_probe", ["python3", plan["deploy_runner"], "loopback-probe", "--as-of-date", "AUTO_YESTERDAY"]),
            ("public_probe", ["python3", plan["deploy_runner"], "public-probe", "--as-of-date", "AUTO_YESTERDAY"]),
        ):
            completed = _run_or_raise(command_runner, command, workspace, env=deploy_env)
            if step == "public_probe":
                public_probe_payload = _parse_json_object(completed.stdout)
            executed.append(step)

        public_status = _verify_public_operator_label(plan.get("expected_public_label"), public_probe_payload)
        executed.append("post_deploy_public_verify")
        result = TargetProductionResult(
            status="post_deploy_passed" if public_status == "passed" else "rollback_required",
            allowed=True,
            blockers=() if public_status == "passed" else ("public verify failed",),
            warnings=decision.warnings,
            plan=plan,
            executed_steps=tuple(executed),
            target_branch=target_branch,
            target_pr_url=pr_url,
            target_pr_number=pr_number,
            pre_merge_main_commit=pre_merge_main,
            merge_commit=merge_commit,
            backup_path=backup_path,
            deploy_status="passed",
            public_verify_status=public_status,
            rollback_plan_path=str(rollback_plan_path),
        )
        _write_result(run_dir, result)
        return result
    except Exception as exc:
        if isinstance(exc, ProductionDiffMismatchError):
            plan["diff_gate"] = dict(exc.diagnostics)
        result = TargetProductionResult(
            status="blocked",
            allowed=True,
            blockers=(_safe_exception_text(exc),),
            warnings=decision.warnings,
            plan=plan,
            executed_steps=tuple(executed),
            target_branch=target_branch,
            target_pr_url=pr_url,
            target_pr_number=pr_number,
            pre_merge_main_commit=pre_merge_main,
            merge_commit=merge_commit,
            backup_path=backup_path,
            deploy_status="blocked" if "deploy_live" not in executed else "started",
            public_verify_status=None,
            rollback_plan_path=str(rollback_plan_path),
        )
        _write_result(run_dir, result)
        return result
    finally:
        if lock is not None:
            release_wb_core_production_lock(lock)


def load_wb_core_rules_summary(workspace_path: Path) -> dict[str, Any]:
    workspace = workspace_path.resolve()
    if not workspace.exists():
        raise ValueError(f"managed workspace does not exist: {workspace}")
    if not (workspace / ".git").exists():
        raise ValueError(f"managed workspace is not a git checkout: {workspace}")
    if "workspaces" not in workspace.parts:
        raise ValueError("workspace_path must be inside a managed workspaces directory")
    required_sources = {
        "README.md": (workspace / "README.md").exists(),
        "AGENTS.md": (workspace / "AGENTS.md").exists(),
        "docs/architecture": (workspace / "docs" / "architecture").is_dir(),
        "docs/modules": (workspace / "docs" / "modules").is_dir(),
        "migration": (workspace / "migration").exists(),
    }
    docs = [
        "README.md",
        "AGENTS.md",
        *(_relative_files(workspace, workspace / "docs" / "architecture")),
        *(_relative_files(workspace, workspace / "docs" / "modules")),
        *(_relative_files(workspace, workspace / "migration")),
    ]
    return {
        "workspace_path": str(workspace),
        "required_sources": required_sources,
        "loaded_paths": docs[:200],
        "loaded_path_count": len(docs),
        "deploy_runner_found": (workspace / DEFAULT_DEPLOY_RUNNER).exists(),
        "deploy_target_file_found": (workspace / DEFAULT_DEPLOY_TARGET_FILE).exists(),
        "target_adapter_config": "configs/target_projects/wb_core.json",
        "rules_loaded_into_context": True,
    }


def inspect_wb_core_production_lock(
    *,
    workspace_path: Path | None,
    run_dir: Path | None,
    run_id: str,
    now: float | None = None,
) -> dict[str, Any]:
    """Return sanitized lock state for the single wb-core production lane."""

    state_root = _production_state_root(workspace_path=workspace_path, run_dir=run_dir)
    lock_path = _production_lock_path(state_root)
    stale_seconds = _lock_stale_seconds()
    payload = _read_lock_payload(lock_path)
    if payload is None:
        return {
            "status": "free",
            "target_project_id": TARGET_PROJECT_ID,
            "lock_path": str(lock_path),
            "stale_after_seconds": stale_seconds,
            "manual_cleanup": f"rm {shlex.quote(str(lock_path))}  # only after verifying no production lane is running",
        }
    created_at = _float_or_none(payload.get("created_at_epoch"))
    age_seconds = None if created_at is None else max(0.0, (time.time() if now is None else now) - created_at)
    status = "stale" if age_seconds is None or age_seconds > stale_seconds else "active"
    return {
        "status": status,
        "target_project_id": TARGET_PROJECT_ID,
        "lock_path": str(lock_path),
        "run_id": _text(payload.get("run_id")),
        "created_at": _text(payload.get("created_at")),
        "created_at_epoch": created_at,
        "age_seconds": age_seconds,
        "stale_after_seconds": stale_seconds,
        "manual_cleanup": f"rm {shlex.quote(str(lock_path))}  # only after verifying no production lane is running",
        "current_run_id": run_id,
    }


def acquire_wb_core_production_lock(*, workspace_path: Path, run_dir: Path, run_id: str) -> TargetProductionLock:
    """Create the single target production lock atomically."""

    state_root = _production_state_root(workspace_path=workspace_path, run_dir=run_dir)
    lock_path = _production_lock_path(state_root)
    status = inspect_wb_core_production_lock(workspace_path=workspace_path, run_dir=run_dir, run_id=run_id)
    if status["status"] != "free":
        raise RuntimeError(
            "wb-core production lane lock is not free: "
            f"{status['status']} at {status['lock_path']} for run {status.get('run_id') or 'unknown'}"
        )
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    token = f"{run_id}:{os.getpid()}:{time.time_ns()}"
    payload = {
        "target_project_id": TARGET_PROJECT_ID,
        "run_id": run_id,
        "pid": os.getpid(),
        "token": token,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_at_epoch": time.time(),
        "stale_after_seconds": _lock_stale_seconds(),
    }
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        fd = os.open(lock_path, flags, 0o600)
    except FileExistsError as exc:
        raise RuntimeError(f"wb-core production lane lock was acquired by another run: {lock_path}") from exc
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    return TargetProductionLock(lock_path=lock_path, run_id=run_id, token=token)


def release_wb_core_production_lock(lock: TargetProductionLock) -> None:
    payload = _read_lock_payload(lock.lock_path)
    if payload is None:
        return
    if payload.get("token") != lock.token:
        return
    try:
        lock.lock_path.unlink()
    except FileNotFoundError:
        return


def scan_changed_files_for_secrets(workspace_path: Path, changed_files: Sequence[str]) -> tuple[str, ...]:
    hits: list[str] = []
    workspace = workspace_path.resolve()
    for path in changed_files:
        candidate = (workspace / path).resolve()
        if not _is_relative_to(candidate, workspace) or not candidate.exists() or candidate.is_dir():
            continue
        try:
            text = candidate.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if any(pattern.search(text) for pattern in SECRET_PATTERNS):
            hits.append(path)
    return tuple(sorted(set(hits)))


def build_rollback_plan(
    *,
    run_id: str,
    branch_name: str,
    pre_merge_main_commit: str,
    merge_commit: str,
    deploy_runner: str,
    deploy_target_file: str,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "strategy": "git revert PR merge commit, then redeploy through approved WebCore runner; app tar backup is fallback evidence",
        "rollback_base_commit": pre_merge_main_commit,
        "merge_commit": merge_commit,
        "target_branch": branch_name,
        "full_vps_snapshot": "not_configured",
        "full_vps_snapshot_known_gap": "full VPS snapshot unavailable/not configured; rollback uses git/app backup",
        "commands": [
            f"git checkout {BASE_BRANCH}",
            f"git pull --ff-only origin {BASE_BRANCH}",
            f"git revert -m 1 {merge_commit}",
            "git push origin main  # only under explicit emergency rollback approval",
            f"WB_CORE_HOSTED_RUNTIME_TARGET_FILE={deploy_target_file} python3 {deploy_runner} deploy",
            f"WB_CORE_HOSTED_RUNTIME_TARGET_FILE={deploy_target_file} python3 {deploy_runner} loopback-probe --as-of-date AUTO_YESTERDAY",
            f"WB_CORE_HOSTED_RUNTIME_TARGET_FILE={deploy_target_file} python3 {deploy_runner} public-probe --as-of-date AUTO_YESTERDAY",
        ],
    }


def target_production_decision_to_dict(decision: TargetProductionDecision) -> dict[str, Any]:
    return _json_ready(asdict(decision))


def target_production_result_to_dict(result: TargetProductionResult) -> dict[str, Any]:
    return _json_ready(asdict(result))


def target_production_resume_result_to_dict(result: TargetProductionResumeResult) -> dict[str, Any]:
    return _json_ready(asdict(result))


def execute_wb_core_resume_deploy(
    *,
    run_id: str,
    state_dir: Path | None = None,
    run_dir: Path | None = None,
    execute: bool = False,
    runner: CommandRunner | None = None,
    env: Mapping[str, str] | None = None,
    github_runner: Any | None = None,
    ssh_runner: Any | None = None,
) -> TargetProductionResumeResult:
    """Resume only post-merge deploy stages for an already merged production-lane run.

    This path intentionally never runs Codex, creates a branch, commits, pushes,
    opens a PR or merges a PR. It consumes the existing production-lane result
    and resumes at backup/deploy/probe only after fail-closed eligibility gates.
    """

    command_runner = runner or _run_command
    runtime_env = env if env is not None else os.environ
    safe_run_id = safe_state_component(str(run_id), "run_id")
    try:
        context = _load_resume_context(run_id=safe_run_id, state_dir=state_dir, run_dir=run_dir)
    except Exception as exc:
        blocked_run_dir = (run_dir or _state_run_dir(safe_run_id, state_dir)).resolve()
        result = TargetProductionResumeResult(
            status="blocked",
            allowed=False,
            blockers=(_safe_exception_text(exc),),
            warnings=(),
            plan={},
            executed_steps=(),
            run_id=safe_run_id,
        )
        try:
            _write_resume_result(blocked_run_dir / "artifacts" / "production_lane", result)
        except Exception:
            pass
        return result
    plan = dict(context["plan"])
    run_id = str(context["run_id"])
    resume_run_dir = Path(str(context["run_dir"]))
    workspace = Path(str(context["workspace_path"]))
    merge_commit = str(context["merge_commit"])
    rollback_plan_path = str(context["rollback_plan_path"])
    resume_dir = resume_run_dir / "artifacts" / "production_lane"
    resume_dir.mkdir(parents=True, exist_ok=True)
    resume_report_path = resume_dir / "resume_deploy_report.json"
    executed: list[str] = []
    lock: TargetProductionLock | None = None
    backup_path: str | None = None
    public_probe_payload: dict[str, Any] | None = None

    try:
        preflight = _resume_deploy_preflight(
            workspace=workspace,
            artifacts_dir=resume_dir,
            env=runtime_env,
            github_runner=github_runner or _github_auth_runner_from_command_runner(command_runner),
            ssh_runner=ssh_runner,
        )
        plan["resume_preflight"] = preflight
        executed.append("resume_preflight")
        github_env = github_command_env(env=runtime_env, askpass_dir=resume_dir / "resume_preflight")
        lock_status = inspect_wb_core_production_lock(workspace_path=workspace, run_dir=resume_run_dir, run_id=run_id)
        plan["lock"] = lock_status
        if lock_status.get("status") != "free":
            raise RuntimeError(
                "wb-core production lane lock is not free for resume: "
                f"{lock_status.get('status')} run={lock_status.get('run_id') or 'unknown'}"
            )
        origin_main = _verify_merge_commit_on_main(command_runner, workspace, merge_commit, github_env)
        plan["origin_main_commit"] = origin_main
        executed.append("merge_commit_verified")
        plan["resume_commands"] = _resume_execution_commands(plan)

        if not execute:
            result = TargetProductionResumeResult(
                status="resume_dry_run_ready",
                allowed=True,
                blockers=(),
                warnings=(),
                plan=plan,
                executed_steps=tuple(executed),
                run_id=run_id,
                target_pr_url=str(context.get("target_pr_url") or ""),
                target_pr_number=_optional_int(context.get("target_pr_number")),
                merge_commit=merge_commit,
                rollback_plan_path=rollback_plan_path,
                resume_report_path=str(resume_report_path),
            )
            _write_resume_result(resume_dir, result)
            return result

        lock = acquire_wb_core_production_lock(workspace_path=workspace, run_dir=resume_run_dir, run_id=run_id)
        plan["lock"] = {"status": "acquired", "lock_path": str(lock.lock_path), "run_id": lock.run_id}
        executed.append("target_lock_acquired")
        _run_or_raise(command_runner, ["git", "checkout", "--detach", merge_commit], workspace, env=github_env)
        executed.append("deploy_checkout")
        backup_path = _create_remote_app_backup(command_runner, workspace, run_id, env=runtime_env)
        executed.append("backup_created")
        _write_json_artifact(
            resume_dir / "backup_result.json",
            {"status": "passed", "run_id": run_id, "backup_path": backup_path, "merge_commit": merge_commit},
        )

        deploy_env = {
            **os.environ,
            **runtime_command_env(runtime_env),
            "WB_CORE_HOSTED_RUNTIME_TARGET_FILE": str(plan["deploy_target_file"]),
        }
        deploy_results: list[dict[str, Any]] = []
        probe_results: list[dict[str, Any]] = []
        for step, command in (
            ("print_plan", ["python3", str(plan["deploy_runner"]), "print-plan"]),
            ("deploy_dry_run", ["python3", str(plan["deploy_runner"]), "deploy", "--dry-run"]),
            ("deploy_live", ["python3", str(plan["deploy_runner"]), "deploy"]),
            ("loopback_probe", ["python3", str(plan["deploy_runner"]), "loopback-probe", "--as-of-date", "AUTO_YESTERDAY"]),
            ("public_probe", ["python3", str(plan["deploy_runner"]), "public-probe", "--as-of-date", "AUTO_YESTERDAY"]),
        ):
            completed = _run_or_raise(command_runner, command, workspace, env=deploy_env)
            payload = {
                "step": step,
                "status": "passed",
                "returncode": completed.returncode,
                "stdout_excerpt": _safe_command_output(subprocess.CompletedProcess(args=completed.args, returncode=0, stdout=completed.stdout[-2000:], stderr="")),
            }
            if step == "public_probe":
                public_probe_payload = _parse_json_object(completed.stdout)
            if step.endswith("probe"):
                probe_results.append(payload)
            else:
                deploy_results.append(payload)
            executed.append(step)

        _write_json_artifact(resume_dir / "deploy_result.json", {"status": "passed", "steps": deploy_results})
        _write_json_artifact(resume_dir / "probe_result.json", {"status": "passed", "steps": probe_results, "public_probe": public_probe_payload})
        public_status = _verify_public_operator_label(plan.get("expected_public_label"), public_probe_payload)
        executed.append("post_deploy_public_verify")
        result = TargetProductionResumeResult(
            status="post_deploy_passed" if public_status == "passed" else "rollback_required",
            allowed=True,
            blockers=() if public_status == "passed" else ("public verify failed",),
            warnings=(),
            plan=plan,
            executed_steps=tuple(executed),
            run_id=run_id,
            target_pr_url=str(context.get("target_pr_url") or ""),
            target_pr_number=_optional_int(context.get("target_pr_number")),
            merge_commit=merge_commit,
            backup_path=backup_path,
            deploy_status="passed",
            public_verify_status=public_status,
            rollback_plan_path=rollback_plan_path,
            resume_report_path=str(resume_report_path),
        )
        _write_resume_result(resume_dir, result)
        _merge_resume_into_production_result(resume_dir, result)
        return result
    except Exception as exc:
        result = TargetProductionResumeResult(
            status="blocked",
            allowed=True,
            blockers=(_safe_exception_text(exc),),
            warnings=(),
            plan=plan,
            executed_steps=tuple(executed),
            run_id=run_id,
            target_pr_url=str(context.get("target_pr_url") or ""),
            target_pr_number=_optional_int(context.get("target_pr_number")),
            merge_commit=merge_commit,
            backup_path=backup_path,
            deploy_status="blocked" if "deploy_live" not in executed else "started",
            rollback_plan_path=rollback_plan_path,
            resume_report_path=str(resume_report_path),
        )
        _write_resume_result(resume_dir, result)
        return result
    finally:
        if lock is not None:
            release_wb_core_production_lock(lock)


def _production_lane_toolchain_preflight(
    *,
    workspace: Path,
    artifacts_dir: Path,
    env: Mapping[str, str] | None = None,
    github_runner: Any | None = None,
    ssh_runner: Any | None = None,
) -> dict[str, Any]:
    environment = env or _production_preflight_env()
    status = build_toolchain_status(env=environment, require_github_cli=True)
    status["workspace_path"] = str(workspace)
    status["target_requirements"] = {
        "skipped": True,
        "reason": "production-lane PR/merge preflight requires hosted baseline tools and gh; target-specific tooling was checked before verifier",
    }
    preflight_path = artifacts_dir / "preflight" / "production_lane_toolchain.json"
    preflight_path.parent.mkdir(parents=True, exist_ok=True)
    preflight_path.write_text(json.dumps(status, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    missing = [str(item) for item in status.get("missing_required", [])]
    github_status = build_github_auth_status(
        env=environment,
        repo=TARGET_REPO,
        repo_url=TARGET_REPO_URL,
        require_write=True,
        check_remote=True,
        askpass_dir=artifacts_dir / "preflight",
        runner=github_runner,
    )
    status["github_auth"] = github_status
    ssh_status = build_ssh_deploy_status(
        env=environment,
        target_id=TARGET_PROJECT_ID,
        check_remote=True,
        runner=ssh_runner,
    )
    status["ssh_deploy"] = ssh_status
    preflight_path.write_text(json.dumps(status, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    blockers = []
    if missing:
        blockers.append("missing required hosted tool(s): " + ", ".join(missing))
    if github_status.get("status") != "ready":
        blockers.append(str(github_status.get("blocker") or "GitHub auth is not ready"))
    if ssh_status.get("status") != "ready":
        blockers.append(str(ssh_status.get("blocker") or "SSH deploy target is not ready"))
    if blockers:
        raise RuntimeError("production lane preflight failed: " + "; ".join(blockers))
    return status


def _production_preflight_env() -> dict[str, str]:
    environment = {**os.environ, **runtime_command_env(os.environ, git_prompt=False)}
    for key in (
        "DEV_CONTROL_PLANE_SECRET_HOME",
        "DEV_CONTROL_PLANE_GITHUB_TOKEN",
        "DEV_CONTROL_PLANE_GITHUB_USERNAME",
        "GH_TOKEN",
        "GITHUB_TOKEN",
        "DEV_CONTROL_PLANE_WB_CORE_DEPLOY_SSH_ALIAS",
        "DEV_CONTROL_PLANE_WB_CORE_DEPLOY_SSH_HOST",
        "DEV_CONTROL_PLANE_WB_CORE_DEPLOY_SSH_USER",
        "DEV_CONTROL_PLANE_WB_CORE_DEPLOY_SSH_PORT",
        "DEV_CONTROL_PLANE_WB_CORE_DEPLOY_SSH_IDENTITY_FILE",
        "DEV_CONTROL_PLANE_WB_CORE_DEPLOY_SSH_KNOWN_HOSTS",
    ):
        value = os.environ.get(key)
        if value:
            environment[key] = value
    return environment


def _resume_deploy_preflight(
    *,
    workspace: Path,
    artifacts_dir: Path,
    env: Mapping[str, str] | None = None,
    github_runner: Any | None = None,
    ssh_runner: Any | None = None,
) -> dict[str, Any]:
    status = build_toolchain_status(env=env, require_github_cli=True)
    status["workspace_path"] = str(workspace)
    status["resume_scope"] = {
        "post_merge_only": True,
        "codex_rerun": False,
        "codex_required": False,
        "new_branch": False,
        "new_pr": False,
        "merge_again": False,
    }
    preflight_path = artifacts_dir / "resume_preflight" / "resume_deploy_preflight.json"
    preflight_path.parent.mkdir(parents=True, exist_ok=True)
    missing = [str(item) for item in status.get("missing_required", []) if str(item) != "codex"]
    if "codex" in status.get("missing_required", []):
        status["resume_scope"]["codex_missing_ignored_reason"] = "post-merge resume never reruns Codex"
        status["missing_required"] = missing
        status["status"] = "ready" if not missing else "blocked"
        for tool in status.get("tools", []):
            if isinstance(tool, dict) and tool.get("name") == "codex":
                tool["required"] = False
                tool["status"] = "not_required_for_resume"
                tool["reason"] = "post-merge resume never reruns Codex"
    github_status = build_github_auth_status(
        env=env,
        repo=TARGET_REPO,
        repo_url=TARGET_REPO_URL,
        require_write=True,
        check_remote=True,
        askpass_dir=artifacts_dir / "resume_preflight",
        runner=github_runner,
    )
    ssh_status = build_ssh_deploy_status(
        env=env,
        target_id=TARGET_PROJECT_ID,
        check_remote=True,
        runner=ssh_runner,
    )
    status["github_auth"] = github_status
    status["ssh_deploy"] = ssh_status
    _write_json_artifact(preflight_path, status)
    blockers = []
    if missing:
        blockers.append("missing required hosted tool(s): " + ", ".join(missing))
    if github_status.get("status") != "ready":
        blockers.append(str(github_status.get("blocker") or "GitHub auth is not ready"))
    if ssh_status.get("status") != "ready":
        blockers.append(str(ssh_status.get("blocker") or "SSH deploy target is not ready"))
    if blockers:
        raise RuntimeError("resume deploy preflight failed: " + "; ".join(blockers))
    return status


def _load_resume_context(*, run_id: str, state_dir: Path | None, run_dir: Path | None) -> dict[str, Any]:
    safe_run_id = safe_state_component(str(run_id), "run_id")
    resolved_run_dir = (run_dir or _state_run_dir(safe_run_id, state_dir)).resolve()
    if not resolved_run_dir.exists():
        raise RuntimeError(f"run directory is missing for resume: {safe_run_id}")
    production_path = resolved_run_dir / "artifacts" / "production_lane" / "production_lane_result.json"
    production = _read_json_if_exists(production_path)
    if not production:
        raise RuntimeError("production_lane_result.json is required for resume")
    plan = production.get("plan")
    if not isinstance(plan, Mapping):
        raise RuntimeError("production lane plan is missing from result")
    if str(plan.get("target_project_id") or "") != TARGET_PROJECT_ID:
        raise RuntimeError("resume deploy is allowed only for wb-core production-lane runs")
    if str(plan.get("execution_mode") or "") != "production_lane":
        raise RuntimeError("resume deploy requires execution_mode=production_lane")
    executed_steps = tuple(str(item) for item in _sequence(production.get("executed_steps")))
    if "target_pr_created" not in executed_steps or "target_pr_merged" not in executed_steps:
        raise RuntimeError("resume deploy requires an already created and merged PR")
    if "backup_created" in executed_steps or production.get("deploy_status") == "passed":
        raise RuntimeError("resume deploy is not needed because deploy already passed or backup was already created")
    target_pr_url = _text(production.get("target_pr_url"))
    target_pr_number = _optional_int(production.get("target_pr_number"))
    merge_commit = _text(production.get("merge_commit"))
    if not target_pr_url or target_pr_number is None:
        raise RuntimeError("resume deploy requires recorded PR URL and PR number")
    if not _looks_like_sha(merge_commit):
        raise RuntimeError("resume deploy requires a recorded PR merge commit")

    rollback_path = resolved_run_dir / "artifacts" / "production_lane" / "rollback_plan.json"
    rollback = _read_json_if_exists(rollback_path)
    if not rollback:
        rollback = dict(plan.get("rollback_plan") or {}) if isinstance(plan.get("rollback_plan"), Mapping) else {}
    if not rollback.get("commands"):
        raise RuntimeError("resume deploy requires a rollback plan")
    if _text(rollback.get("merge_commit")) and _text(rollback.get("merge_commit")) != merge_commit:
        raise RuntimeError("rollback plan merge_commit does not match production result")

    record = _read_json_if_exists(resolved_run_dir / "run.json")
    verifier_payload = _read_json_if_exists(resolved_run_dir / "verifier" / "verifier.json")
    result_payload = record.get("result") if isinstance(record.get("result"), Mapping) else {}
    verifier_status = _text(result_payload.get("verifier_status") or verifier_payload.get("status"))
    if verifier_status != "passed":
        raise RuntimeError("resume deploy requires verifier_status=passed")
    changed_files = _sequence(plan.get("changed_files") or result_payload.get("changed_files"))
    if not changed_files:
        raise RuntimeError("resume deploy requires recorded changed_files")
    protected_hits = _protected_path_hits(changed_files)
    if protected_hits:
        raise RuntimeError("protected/forbidden target paths changed: " + ", ".join(protected_hits))

    workspace = _optional_path(plan.get("workspace_path"))
    if workspace is None or not workspace.exists():
        raise RuntimeError("resume deploy requires the original managed workspace")
    rules = load_wb_core_rules_summary(workspace)
    if not rules.get("deploy_runner_found"):
        raise RuntimeError(f"approved WebCore deploy runner not found: {plan.get('deploy_runner')}")
    if not rules.get("deploy_target_file_found"):
        raise RuntimeError(f"approved WebCore deploy target file not found: {plan.get('deploy_target_file')}")
    secret_hits = scan_changed_files_for_secrets(workspace, changed_files)
    if secret_hits:
        raise RuntimeError("secret-like content detected in changed files: " + ", ".join(secret_hits))

    return {
        "run_id": safe_run_id,
        "run_dir": resolved_run_dir,
        "workspace_path": workspace.resolve(),
        "production_result": production,
        "plan": {
            **dict(plan),
            "run_id": safe_run_id,
            "run_dir": str(resolved_run_dir),
            "workspace_path": str(workspace.resolve()),
            "changed_files": list(changed_files),
            "rollback_plan": rollback,
            "rollback_plan_path": str(rollback_path),
            "merge_commit": merge_commit,
            "target_pr_url": target_pr_url,
            "target_pr_number": target_pr_number,
            "resume_mode": "post_merge_deploy_only",
            "resume_forbidden": {
                "codex_rerun": True,
                "new_branch": True,
                "new_pr": True,
                "merge_again": True,
                "target_source_edit": True,
            },
        },
        "target_pr_url": target_pr_url,
        "target_pr_number": target_pr_number,
        "merge_commit": merge_commit,
        "rollback_plan_path": rollback_path,
    }


def _state_run_dir(run_id: str, state_dir: Path | None) -> Path:
    state_root = (state_dir or Path(os.environ.get("DEV_CONTROL_PLANE_STATE_DIR") or "/tmp/development-control-plane-state")).expanduser().resolve()
    return state_root / "runs" / run_id


def _verify_merge_commit_on_main(
    command_runner: CommandRunner,
    workspace: Path,
    merge_commit: str,
    env: Mapping[str, str],
) -> str:
    _run_or_raise(command_runner, ["git", "fetch", "origin", BASE_BRANCH], workspace, env=env)
    _run_or_raise(command_runner, ["git", "merge-base", "--is-ancestor", merge_commit, f"origin/{BASE_BRANCH}"], workspace, env=env)
    head = _run_or_raise(command_runner, ["git", "rev-parse", f"origin/{BASE_BRANCH}"], workspace, env=env).stdout.strip()
    if not _looks_like_sha(head):
        raise RuntimeError("origin/main head could not be verified")
    return head


def _resume_execution_commands(plan: Mapping[str, Any]) -> list[list[str]]:
    rollback = plan.get("rollback_plan")
    rollback_merge = rollback.get("merge_commit") if isinstance(rollback, Mapping) else None
    merge_commit = str(plan.get("merge_commit") or rollback_merge or "")
    return [
        ["git", "fetch", "origin", BASE_BRANCH],
        ["git", "merge-base", "--is-ancestor", merge_commit, f"origin/{BASE_BRANCH}"],
        ["git", "checkout", "--detach", merge_commit],
        ["ssh", "<configured-wb-core-deploy-target>", "<create app backup>"],
        *[shlex.split(command) for command in _deploy_commands(str(plan["deploy_runner"]))],
    ]


def _write_resume_result(resume_dir: Path, result: TargetProductionResumeResult) -> None:
    payload = target_production_resume_result_to_dict(result)
    _write_json_artifact(resume_dir / "resume_deploy_result.json", payload)
    _write_json_artifact(resume_dir / "resume_deploy_report.json", _resume_report_payload(payload))


def _merge_resume_into_production_result(resume_dir: Path, result: TargetProductionResumeResult) -> None:
    path = resume_dir / "production_lane_result.json"
    production = _read_json_if_exists(path)
    if not production:
        return
    payload = target_production_resume_result_to_dict(result)
    production["resume_result"] = payload
    production["status"] = result.status
    production["backup_path"] = result.backup_path
    production["deploy_status"] = result.deploy_status
    production["public_verify_status"] = result.public_verify_status
    production["blockers"] = list(result.blockers)
    production["executed_steps"] = list(dict.fromkeys([*production.get("executed_steps", []), *result.executed_steps]))
    _write_json_artifact(path, production)


def _resume_report_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": payload.get("status"),
        "run_id": payload.get("run_id"),
        "resume_mode": "post_merge_deploy_only",
        "merge_commit": payload.get("merge_commit"),
        "target_pr_url": payload.get("target_pr_url"),
        "target_pr_number": payload.get("target_pr_number"),
        "backup_path": payload.get("backup_path"),
        "deploy_status": payload.get("deploy_status"),
        "public_verify_status": payload.get("public_verify_status"),
        "executed_steps": payload.get("executed_steps"),
        "blockers": payload.get("blockers"),
        "no_codex_rerun": True,
        "no_new_pr": True,
        "no_merge_again": True,
        "no_target_source_edit": True,
    }


def _target_pr_body(
    *,
    task_summary: str,
    run_id: str,
    changed_files: Sequence[str],
    verifier_status: str,
    docs_update_status: str,
    deploy_runner: str,
    rollback_plan: Mapping[str, Any],
    expected_label: str,
) -> str:
    files = "\n".join(f"- `{path}`" for path in changed_files) or "- нет"
    return "\n".join(
        (
            "## Задача",
            "",
            task_summary,
            "",
            "## DevControl run",
            "",
            f"- run_id: `{run_id}`",
            "",
            "## Изменённые файлы",
            "",
            files,
            "",
            "## Gates",
            "",
            f"- verifier: `{verifier_status}`",
            "- forbidden paths: clean",
            "- secrets scan: clean",
            f"- docs update status: `{docs_update_status}`",
            "",
            "## Deploy plan",
            "",
            f"- runner: `{deploy_runner}`",
            "- `print-plan`",
            "- `deploy --dry-run`",
            "- `deploy`",
            "- `loopback-probe --as-of-date AUTO_YESTERDAY`",
            "- `public-probe --as-of-date AUTO_YESTERDAY`",
            f"- public marker: `{expected_label or 'not specified'}`",
            "",
            "## Rollback plan",
            "",
            f"- rollback base: `{rollback_plan.get('rollback_base_commit')}`",
            f"- merge commit: `{rollback_plan.get('merge_commit')}`",
            "- rollback commands are stored in the DevControl production-lane report.",
            "",
        )
    )


def _deploy_commands(deploy_runner: str) -> list[str]:
    return [
        f"python3 {deploy_runner} print-plan",
        f"python3 {deploy_runner} deploy --dry-run",
        f"python3 {deploy_runner} deploy",
        f"python3 {deploy_runner} loopback-probe --as-of-date AUTO_YESTERDAY",
        f"python3 {deploy_runner} public-probe --as-of-date AUTO_YESTERDAY",
    ]


def _execution_commands(plan: Mapping[str, Any]) -> list[list[str]]:
    return [
        ["git", "checkout", "-B", str(plan["branch_name"])],
        ["git", "add", "--", *list(plan["changed_files"])],
        ["git", "commit", "-m", str(plan["commit_message"])],
        ["git", "push", "-u", "origin", str(plan["branch_name"])],
        ["gh", "pr", "create", "--repo", TARGET_REPO, "--base", BASE_BRANCH, "--head", str(plan["branch_name"])],
        ["gh", "pr", "merge", "<pr_number>", "--repo", TARGET_REPO, "--merge", "--delete-branch"],
        ["ssh", "<configured-wb-core-deploy-target>", "<create app backup>"],
        *[shlex.split(command) for command in plan["deploy_commands"]],
    ]


def _create_remote_app_backup(
    command_runner: CommandRunner,
    cwd: Path,
    run_id: str,
    *,
    env: Mapping[str, str] | None = None,
) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_run = slug_state_component(run_id, fallback="run")
    backup_path = f"{APP_BACKUP_DIR}/app_{safe_run}_{timestamp}.tar.gz"
    remote = (
        f"set -eu; mkdir -p {shlex.quote(APP_BACKUP_DIR)}; "
        f"tar --exclude='.git' --exclude='*.env' --exclude='.env' "
        f"-C /opt/wb-core-runtime -czf {shlex.quote(backup_path)} app; "
        f"test -s {shlex.quote(backup_path)}"
    )
    runtime_env = env or os.environ
    _run_or_raise(command_runner, ssh_deploy_command(remote, env=runtime_env), cwd, env=ssh_command_env(env=runtime_env))
    return backup_path


def _write_rollback_plan(
    path: Path,
    plan: dict[str, Any],
    *,
    pre_merge_main_commit: str | None = None,
    merge_commit: str | None = None,
) -> None:
    rollback_plan = build_rollback_plan(
        run_id=str(plan["run_id"]),
        branch_name=str(plan["branch_name"]),
        pre_merge_main_commit=pre_merge_main_commit or str(plan["rollback_plan"].get("rollback_base_commit") or "<recorded-before-merge>"),
        merge_commit=merge_commit or str(plan["rollback_plan"].get("merge_commit") or "<recorded-after-merge>"),
        deploy_runner=str(plan["deploy_runner"]),
        deploy_target_file=str(plan["deploy_target_file"]),
    )
    plan["rollback_plan"] = rollback_plan
    path.write_text(json.dumps(rollback_plan, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_result(run_dir: Path, result: TargetProductionResult) -> None:
    result_path = run_dir / "production_lane_result.json"
    result_path.write_text(
        json.dumps(target_production_result_to_dict(result), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _production_state_root(*, workspace_path: Path | None, run_dir: Path | None) -> Path:
    if run_dir is not None:
        resolved_run_dir = run_dir.resolve()
        if resolved_run_dir.parent.name == "runs":
            return resolved_run_dir.parent.parent
        if "runs" in resolved_run_dir.parts:
            idx = list(resolved_run_dir.parts).index("runs")
            return Path(*resolved_run_dir.parts[:idx]).resolve()
    if workspace_path is not None:
        resolved_workspace = workspace_path.resolve()
        parts = list(resolved_workspace.parts)
        if "workspaces" in parts:
            idx = parts.index("workspaces")
            return Path(*parts[:idx]).resolve()
        if len(resolved_workspace.parents) > 2:
            return resolved_workspace.parents[2]
    return Path(os.environ.get("DEV_CONTROL_PLANE_STATE_DIR") or "/tmp/development-control-plane-state").resolve()


def _production_lock_path(state_root: Path) -> Path:
    return state_root / "locks" / f"{TARGET_PROJECT_ID}-production-lane.lock.json"


def _read_lock_payload(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (json.JSONDecodeError, OSError):
        return {
            "run_id": "unknown",
            "created_at": "",
            "created_at_epoch": None,
        }
    return payload if isinstance(payload, dict) else {"run_id": "unknown", "created_at_epoch": None}


def _read_json_if_exists(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return dict(payload) if isinstance(payload, Mapping) else {}


def _write_json_artifact(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_json_ready(_sanitize_payload(payload)), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _lock_stale_seconds() -> float:
    raw = os.environ.get(TARGET_PRODUCTION_LOCK_STALE_SECONDS_ENV)
    if raw is None or raw.strip() == "":
        return float(DEFAULT_TARGET_PRODUCTION_LOCK_STALE_SECONDS)
    try:
        value = float(raw)
    except ValueError:
        return float(DEFAULT_TARGET_PRODUCTION_LOCK_STALE_SECONDS)
    return value if value > 0 else float(DEFAULT_TARGET_PRODUCTION_LOCK_STALE_SECONDS)


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _looks_like_sha(value: Any) -> bool:
    return bool(re.fullmatch(r"[0-9a-fA-F]{40}", str(value or "").strip()))


def _safe_exception_text(exc: Exception) -> str:
    return _safe_command_output(subprocess.CompletedProcess(args=(), returncode=1, stderr=str(exc), stdout=""))


def _probe_failure_summary(raw: str) -> str:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return ""
    if not isinstance(payload, Mapping) or payload.get("ok") is not False:
        return ""
    routes = _sequence_of_mappings(payload.get("routes"))
    failed_routes = [route for route in routes if route.get("ok") is not True]
    header_parts = ["probe failed"]
    if payload.get("target_id"):
        header_parts.append(f"target_id={payload.get('target_id')}")
    if payload.get("base_url"):
        header_parts.append(f"base_url={payload.get('base_url')}")
    header_parts.append(f"failed_routes={len(failed_routes)}")
    details: list[str] = []
    for route in failed_routes[:8]:
        route_name = str(route.get("route") or route.get("name") or "<unknown>")
        bits = [f"route={route_name}"]
        if route.get("http_status") is not None:
            bits.append(f"http_status={route.get('http_status')}")
        if route.get("network_error"):
            bits.append(f"network_error={route.get('network_error')}")
        if route.get("detail"):
            bits.append(f"detail={route.get('detail')}")
        body = str(route.get("body_excerpt") or "").strip()
        if body:
            body = re.sub(r"\s+", " ", body)[:280]
            bits.append(f"body_excerpt={body}")
        details.append("; ".join(bits))
    if not details and payload.get("detail"):
        details.append(str(payload.get("detail")))
    if len(failed_routes) > len(details):
        details.append(f"... {len(failed_routes) - len(details)} more failed route(s)")
    return ": ".join(("; ".join(header_parts), " | ".join(details))) if details else "; ".join(header_parts)


def _verify_public_operator_label(
    expected_label: str | None,
    public_probe_payload: Mapping[str, Any] | None = None,
) -> str:
    if public_probe_payload is not None:
        if public_probe_payload.get("ok") is not True:
            return "failed"
        if not expected_label:
            return "passed"
        body = "\n".join(
            str(route.get("body_excerpt") or "")
            for route in _sequence_of_mappings(public_probe_payload.get("routes"))
            if str(route.get("route") or "") in {"operator_ui", "operator_reports", "web_vitrina_page"}
        )
        return "passed" if expected_label in body else "failed"
    try:
        with urllib_request.urlopen(PUBLIC_OPERATOR_URL, timeout=30) as response:
            body = response.read().decode("utf-8", errors="replace")
            if response.status != 200:
                return "failed"
            if expected_label and expected_label not in body:
                return "failed"
            return "passed"
    except Exception:
        return "failed"


def _parse_json_object(raw: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _sequence_of_mappings(value: Any) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return ()
    return tuple(item for item in value if isinstance(item, Mapping))


def _ensure_tool(name: str, runner: CommandRunner) -> None:
    result = runner(["/usr/bin/env", "sh", "-lc", f"command -v {shlex.quote(name)} >/dev/null"], None)
    if result.returncode != 0:
        raise RuntimeError(f"required tool is missing: {name}")


def _prepare_workspace_for_verified_diff(workspace: Path, plan: dict[str, Any], *, run_dir: Path) -> None:
    expected_base = _text(plan.get("run_start_base_ref") or plan.get("verifier_base_commit"))
    _git_checked(workspace, "reset", "--hard", "HEAD")
    _git_checked(workspace, "clean", "-fd")
    if expected_base:
        checkout = _git(workspace, "checkout", "--detach", expected_base)
        if checkout.returncode != 0:
            plan["base_checkout_status"] = "failed"
            raise RuntimeError("verified diff base checkout failed; do not deploy: " + _safe_command_output(checkout))
        plan["base_checkout_status"] = "checked_out_expected_base"
    else:
        plan["base_checkout_status"] = "kept_current_head"
    base_commit = _git_stdout(workspace, "rev-parse", "HEAD")
    plan["promotion_base_commit"] = base_commit
    plan.setdefault("verifier_base_commit", plan.get("run_start_base_ref") or base_commit)
    diff_path = _optional_path(plan.get("diff_artifact_path"))
    if diff_path is None:
        plan["diff_apply_status"] = "not_available_existing_workspace_checked"
        return
    diff_path = diff_path.resolve()
    plan["diff_artifact_path"] = str(diff_path)
    if not diff_path.exists():
        plan["diff_apply_status"] = "missing"
        diagnostics = _production_diff_gate_diagnostics(
            workspace,
            plan["changed_files"],
            verifier_base_commit=plan.get("verifier_base_commit"),
            promotion_base_commit=base_commit,
            run_start_base_ref=plan.get("run_start_base_ref"),
            diff_artifact_path=str(diff_path),
            diff_apply_status="missing",
            exact_blocker="verified diff artifact is missing; do not deploy",
        )
        plan["diff_gate"] = diagnostics
        (run_dir / "production_diff_gate.json").write_text(
            json.dumps(_json_ready(diagnostics), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        raise RuntimeError("verified diff artifact is missing; do not deploy")
    _git_checked(workspace, "reset", "--hard", "HEAD")
    _git_checked(workspace, "clean", "-fd")
    apply_result = _git(workspace, "apply", "--3way", "--whitespace=nowarn", str(diff_path))
    if apply_result.returncode != 0:
        plan["diff_apply_status"] = "failed"
        diagnostics = _production_diff_gate_diagnostics(
            workspace,
            plan["changed_files"],
            verifier_base_commit=plan.get("verifier_base_commit"),
            promotion_base_commit=base_commit,
            run_start_base_ref=plan.get("run_start_base_ref"),
            diff_artifact_path=str(diff_path),
            diff_apply_status="failed",
            exact_blocker="verified diff artifact does not apply cleanly; do not deploy",
        )
        diagnostics["diff_apply_error"] = _safe_command_output(apply_result)
        plan["diff_gate"] = diagnostics
        (run_dir / "production_diff_gate.json").write_text(
            json.dumps(_json_ready(diagnostics), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        raise RuntimeError("verified diff artifact does not apply cleanly; do not deploy: " + _safe_command_output(apply_result))
    _git_checked(workspace, "reset", "--mixed", "HEAD")
    _git_checked(workspace, "add", "-N", ".")
    plan["diff_apply_status"] = "applied"


def _prepare_verified_workspace_source_for_commit(workspace: Path, plan: dict[str, Any]) -> None:
    expected = normalize_changed_files(plan.get("changed_files") or [])
    base = _text(plan.get("run_start_base_ref") or plan.get("verifier_base_commit"))
    status_files = _git_changed_files(workspace)
    committed_files: tuple[str, ...] = ()
    if base:
        committed_files = normalize_changed_files(_git_stdout(workspace, "diff", "--name-only", base, "HEAD").splitlines())
        plan["verified_workspace_committed_changed_files"] = list(committed_files)
    plan["verified_workspace_status_changed_files"] = list(status_files)
    combined = normalize_changed_files((*status_files, *committed_files))
    if committed_files:
        if combined != expected:
            plan["diff_gate"] = _production_diff_gate_diagnostics(
                workspace,
                expected,
                verifier_base_commit=plan.get("verifier_base_commit"),
                promotion_base_commit=_safe_git_stdout(workspace, "rev-parse", "HEAD"),
                run_start_base_ref=plan.get("run_start_base_ref"),
                diff_artifact_path=plan.get("diff_artifact_path"),
                diff_apply_status="not_used_verified_workspace_source",
                exact_blocker=PRODUCTION_DIFF_MISMATCH_BLOCKER,
            )
            plan["diff_gate"]["committed_changed_files"] = list(committed_files)
            raise RuntimeError(PRODUCTION_DIFF_MISMATCH_BLOCKER)
        _git_checked(workspace, "reset", "--soft", base)
        plan["verified_workspace_source_status"] = "committed_changes_soft_reset_to_verified_base"
        return
    if combined and combined != expected:
        plan["diff_gate"] = _production_diff_gate_diagnostics(
            workspace,
            expected,
            verifier_base_commit=plan.get("verifier_base_commit"),
            promotion_base_commit=_safe_git_stdout(workspace, "rev-parse", "HEAD"),
            run_start_base_ref=plan.get("run_start_base_ref"),
            diff_artifact_path=plan.get("diff_artifact_path"),
            diff_apply_status="not_used_verified_workspace_source",
            exact_blocker=PRODUCTION_DIFF_MISMATCH_BLOCKER,
        )
        plan["diff_gate"]["committed_changed_files"] = list(committed_files)
        raise RuntimeError(PRODUCTION_DIFF_MISMATCH_BLOCKER)
    if not combined and expected:
        raise RuntimeError("verified workspace has no changed files relative to verifier base; do not deploy")
    plan["verified_workspace_source_status"] = "working_tree_changes_ready_for_commit"


def _ensure_clean_expected_workspace(
    workspace: Path,
    changed_files: Sequence[str],
    *,
    diagnostics_path: Path | None = None,
    verifier_base_commit: Any = None,
    promotion_base_commit: Any = None,
    run_start_base_ref: Any = None,
    diff_artifact_path: Any = None,
    diff_apply_status: Any = None,
    plan: dict[str, Any] | None = None,
) -> None:
    expected = normalize_changed_files(changed_files)
    actual = _git_changed_files(workspace)
    diagnostics = _production_diff_gate_diagnostics(
        workspace,
        expected,
        verifier_base_commit=verifier_base_commit,
        promotion_base_commit=promotion_base_commit,
        run_start_base_ref=run_start_base_ref,
        diff_artifact_path=diff_artifact_path,
        diff_apply_status=diff_apply_status,
        exact_blocker=PRODUCTION_DIFF_MISMATCH_BLOCKER,
    )
    if sorted(actual) != sorted(expected):
        if diagnostics_path is not None:
            diagnostics_path.parent.mkdir(parents=True, exist_ok=True)
            diagnostics_path.write_text(
                json.dumps(_json_ready(diagnostics), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        if plan is not None:
            plan["diff_gate"] = diagnostics
        raise ProductionDiffMismatchError(diagnostics)
    diagnostics["status"] = "passed"
    if diagnostics_path is not None:
        diagnostics_path.parent.mkdir(parents=True, exist_ok=True)
        diagnostics_path.write_text(
            json.dumps(_json_ready(diagnostics), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if plan is not None:
        plan["diff_gate"] = diagnostics
    _git_checked(workspace, "diff", "--check")


def _git_changed_files(workspace: Path) -> tuple[str, ...]:
    status = _git_stdout(workspace, "status", "--porcelain=v1", "--untracked-files=all")
    return _changed_files_from_status(status)


def _production_diff_gate_diagnostics(
    workspace: Path,
    verifier_changed_files: Sequence[str],
    *,
    verifier_base_commit: Any = None,
    promotion_base_commit: Any = None,
    run_start_base_ref: Any = None,
    diff_artifact_path: Any = None,
    diff_apply_status: Any = None,
    exact_blocker: str = PRODUCTION_DIFF_MISMATCH_BLOCKER,
) -> dict[str, Any]:
    verifier = normalize_changed_files(verifier_changed_files)
    actual = _git_changed_files(workspace)
    status = _git_stdout(workspace, "status", "--porcelain=v1", "--untracked-files=all")
    staged, unstaged, untracked = _git_status_file_sets(status)
    return {
        "status": "failed",
        "exact_blocker": exact_blocker,
        "verifier_changed_files": list(verifier),
        "promotion_workspace_changed_files": list(actual),
        "missing_from_promotion": [item for item in verifier if item not in actual],
        "extra_in_promotion": [item for item in actual if item not in verifier],
        "untracked_files": list(untracked),
        "staged_files": list(staged),
        "unstaged_files": list(unstaged),
        "verifier_base_commit": _text(verifier_base_commit) or None,
        "promotion_base_commit": _text(promotion_base_commit) or _safe_git_stdout(workspace, "rev-parse", "HEAD") or None,
        "run_start_base_ref": _text(run_start_base_ref) or None,
        "promotion_workspace_path": str(workspace.resolve()),
        "diff_artifact_path": _text(diff_artifact_path) or None,
        "diff_apply_status": _text(diff_apply_status) or "not_recorded",
        "pr_attempted": False,
        "branch_attempted": False,
        "commit_attempted": False,
        "push_attempted": False,
        "merge_attempted": False,
        "deploy_attempted": False,
    }


def _changed_files_from_status(status: str) -> tuple[str, ...]:
    changed: list[str] = []
    for line in status.splitlines():
        if not line:
            continue
        path = line[3:] if len(line) > 3 else ""
        if " -> " in path:
            path = path.rsplit(" -> ", 1)[1]
        path = path.strip()
        if path:
            changed.append(path)
    return normalize_changed_files(changed)


def _git_status_file_sets(status: str) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    staged: list[str] = []
    unstaged: list[str] = []
    untracked: list[str] = []
    for line in status.splitlines():
        if not line:
            continue
        x = line[0] if len(line) > 0 else " "
        y = line[1] if len(line) > 1 else " "
        path = line[3:] if len(line) > 3 else ""
        if " -> " in path:
            path = path.rsplit(" -> ", 1)[1]
        normalized = normalize_changed_file_path(path)
        if not normalized:
            continue
        if x == "?" and y == "?":
            untracked.append(normalized)
            continue
        if x.strip():
            staged.append(normalized)
        if y.strip():
            unstaged.append(normalized)
    return normalize_changed_files(staged), normalize_changed_files(unstaged), normalize_changed_files(untracked)


def normalize_changed_files(paths: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted(dict.fromkeys(path for path in (normalize_changed_file_path(item) for item in paths) if path)))


def normalize_changed_file_path(path: Any) -> str:
    text = str(path or "").strip().replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    text = text.lstrip("/")
    if not text or text in {".", ".."} or ".." in Path(text).parts:
        return ""
    if any(text == prefix.rstrip("/") or text.startswith(prefix) for prefix in IGNORED_CHANGED_FILE_PREFIXES):
        return ""
    if any(text.endswith(suffix) for suffix in IGNORED_CHANGED_FILE_SUFFIXES):
        return ""
    return text


def _safe_git_stdout(workspace: Path, *args: str) -> str:
    try:
        return _git_stdout(workspace, *args)
    except Exception:
        return ""


def _gh_json(runner: CommandRunner, cwd: Path, *args: str, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    result = _run_or_raise(runner, ["gh", *args], cwd, env=env)
    return json.loads(result.stdout)


def _run_or_raise(
    runner: CommandRunner,
    command: Sequence[str],
    cwd: Path | None,
    *,
    env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    if env is not None and runner is _run_command:
        result = subprocess.run(tuple(command), cwd=cwd, capture_output=True, text=True, check=False, env=dict(env))
    else:
        result = runner(command, cwd)
    if result.returncode != 0:
        raise RuntimeError(_safe_command_output(result) or f"command failed: {command[0]}")
    return result


def _github_auth_runner_from_command_runner(runner: CommandRunner) -> Any:
    def _run(command: Sequence[str], cwd: Path | None, env: Mapping[str, str]) -> subprocess.CompletedProcess[str]:
        if runner is _run_command:
            try:
                return subprocess.run(tuple(command), cwd=cwd, capture_output=True, text=True, check=False, timeout=12, env=dict(env))
            except subprocess.TimeoutExpired:
                return subprocess.CompletedProcess(args=tuple(command), returncode=124, stdout="", stderr="command timed out")
        return runner(command, cwd)

    return _run


def _run_command(command: Sequence[str], cwd: Path | None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(tuple(command), cwd=cwd, capture_output=True, text=True, check=False, env=runtime_command_env(os.environ))


def _git_stdout(cwd: Path, *args: str) -> str:
    result = _git(cwd, *args)
    if result.returncode != 0:
        raise RuntimeError(_safe_command_output(result) or f"git {' '.join(args)} failed")
    return result.stdout.rstrip("\n")


def _git_checked(cwd: Path, *args: str) -> None:
    result = _git(cwd, *args)
    if result.returncode != 0:
        raise RuntimeError(_safe_command_output(result) or f"git {' '.join(args)} failed")


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(("git", *args), cwd=cwd, capture_output=True, text=True, check=False)


def _safe_command_output(result: subprocess.CompletedProcess[str]) -> str:
    probe_summary = _probe_failure_summary(result.stdout.strip())
    if probe_summary:
        text = probe_summary
    else:
        text = "\n".join(part for part in (result.stdout.strip(), result.stderr.strip()) if part)
    text = re.sub(r"sk-[A-Za-z0-9_-]{8,}", "sk-***", text)
    text = re.sub(r"(Authorization\s*:\s*Bearer\s+)\S+", r"\1***", text, flags=re.IGNORECASE)
    text = re.sub(r"gh[pousr]_[A-Za-z0-9_]{8,}", "gh_***", text)
    text = re.sub(r"github_pat_[A-Za-z0-9_]{8,}", "github_pat_***", text)
    text = re.sub(r"(?i)(identity file\s+)[^\s]+", r"\1[redacted]", text)
    text = re.sub(r"(?i)(key_load_public:\s+No such file or directory:?\s*)[^\s]+", r"\1[redacted]", text)
    return text[-4000:]


def _production_artifacts_dir(run_dir: Path | None, workspace: Path, run_id: str) -> Path:
    if run_dir:
        return run_dir / "artifacts" / "production_lane"
    state_root = workspace.parents[2] if len(workspace.parents) > 2 else workspace.parent
    return state_root / "runs" / slug_state_component(run_id, fallback="run") / "artifacts" / "production_lane"


def _relative_files(workspace: Path, root: Path) -> list[str]:
    if not root.exists():
        return []
    if root.is_file():
        return [root.relative_to(workspace).as_posix()]
    return sorted(path.relative_to(workspace).as_posix() for path in root.rglob("*") if path.is_file())[:200]


def _protected_path_hits(changed_files: Sequence[str]) -> tuple[str, ...]:
    hits = []
    for path in changed_files:
        normalized = path.strip().lstrip("/")
        if normalized == DOCSET_MANIFEST or normalized.startswith(DERIVED_PACK_PREFIX):
            hits.append(path)
        if any(normalized == item.rstrip("/") or normalized.startswith(item) for item in FORBIDDEN_DEPLOY_PATHS if item.endswith("/")):
            hits.append(path)
        if normalized.startswith("artifacts/registry_upload_http_entrypoint/"):
            hits.append(path)
    return tuple(sorted(set(hits)))


def _required_slug(value: Any, *, fallback: str) -> str:
    return slug_state_component(str(value or fallback), fallback=fallback)


def _sequence(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)):
        return (str(value),)
    if isinstance(value, Sequence):
        return tuple(str(item) for item in value if str(item).strip())
    return (str(value),)


def _optional_path(value: Any) -> Path | None:
    text = _text(value)
    return Path(text) if text else None


def _text(value: Any) -> str:
    return str(value or "").strip()


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _contains_cyrillic(value: str) -> bool:
    return bool(re.search(r"[А-Яа-яЁё]", value))


def _is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False


def _json_ready(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    return value


def _sanitize_payload(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_payload(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_payload(item) for item in value]
    if isinstance(value, str):
        return _safe_command_output(subprocess.CompletedProcess(args=(), returncode=0, stdout=value, stderr=""))
    return value
