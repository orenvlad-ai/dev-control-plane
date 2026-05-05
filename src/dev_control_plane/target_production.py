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
from typing import Any
from urllib import request as urllib_request

from dev_control_plane.state_layout import slug_state_component

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
)

CommandRunner = Callable[[Sequence[str], Path | None], subprocess.CompletedProcess[str]]


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
    changed_files = _sequence(payload.get("changed_files"))
    deploy_runner = _text(payload.get("deploy_runner") or DEFAULT_DEPLOY_RUNNER)
    deploy_target_file = _text(payload.get("deploy_target_file") or DEFAULT_DEPLOY_TARGET_FILE)
    workspace_path = _optional_path(payload.get("workspace_path"))
    run_dir = _optional_path(payload.get("run_dir"))
    expected_label = _text(payload.get("expected_public_label"))

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
        "workspace_path": str(workspace_path) if workspace_path else None,
        "run_dir": str(run_dir) if run_dir else None,
        "run_id": run_id,
        "branch_name": branch_name,
        "commit_message": commit_message,
        "pr_title": pr_title,
        "pr_body": pr_body,
        "changed_files": list(changed_files),
        "deploy_runner": deploy_runner,
        "deploy_target_file": deploy_target_file,
        "deploy_commands": _deploy_commands(deploy_runner),
        "public_operator_url": PUBLIC_OPERATOR_URL,
        "public_base_url": PUBLIC_BASE_URL,
        "expected_public_label": expected_label or None,
        "rollback_plan": rollback_plan,
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
    rollback_plan_path.write_text(
        json.dumps(plan["rollback_plan"], ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
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

    _ensure_tool("gh", command_runner)
    _ensure_clean_expected_workspace(workspace, plan["changed_files"])
    pre_merge_main = _git_stdout(workspace, "ls-remote", "origin", f"refs/heads/{BASE_BRANCH}").split()[0]
    _git_checked(workspace, "fetch", "origin", BASE_BRANCH)
    _git_checked(workspace, "checkout", "-B", plan["branch_name"])
    _git_checked(workspace, "config", "user.name", "DevControl Plane")
    _git_checked(workspace, "config", "user.email", "devcontrol-plane@example.invalid")
    _git_checked(workspace, "add", "--", *plan["changed_files"])
    _git_checked(workspace, "commit", "-m", plan["commit_message"])
    executed.append("target_commit")
    target_head = _git_stdout(workspace, "rev-parse", "HEAD")
    _run_or_raise(command_runner, ["git", "push", "-u", "origin", plan["branch_name"]], workspace)
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
            plan["branch_name"],
            "--title",
            plan["pr_title"],
            "--body-file",
            str(pr_body_path),
        ],
        workspace,
    )
    pr_url = pr_create.stdout.strip().splitlines()[-1]
    pr_view = _gh_json(command_runner, workspace, "pr", "view", pr_url, "--repo", TARGET_REPO, "--json", "number,state,headRefOid,url")
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
    )
    merged = _gh_json(command_runner, workspace, "pr", "view", str(pr_number), "--repo", TARGET_REPO, "--json", "state,mergeCommit,url")
    if merged.get("state") != "MERGED":
        raise RuntimeError(f"target PR did not merge: {merged}")
    merge_commit = str((merged.get("mergeCommit") or {}).get("oid") or "")
    if not merge_commit:
        raise RuntimeError("target PR merge commit is missing")
    executed.append("target_pr_merged")

    _git_checked(workspace, "checkout", BASE_BRANCH)
    _git_checked(workspace, "pull", "--ff-only", "origin", BASE_BRANCH)
    head_after_pull = _git_stdout(workspace, "rev-parse", "HEAD")
    if head_after_pull != merge_commit:
        raise RuntimeError(f"deploy checkout is not merged PR commit: {head_after_pull} != {merge_commit}")

    backup_path = _create_remote_app_backup(command_runner, workspace, plan["run_id"])
    executed.append("backup_created")
    deploy_env = {**os.environ, "WB_CORE_HOSTED_RUNTIME_TARGET_FILE": plan["deploy_target_file"]}
    for step, command in (
        ("print_plan", ["python3", plan["deploy_runner"], "print-plan"]),
        ("deploy_dry_run", ["python3", plan["deploy_runner"], "deploy", "--dry-run"]),
        ("deploy_live", ["python3", plan["deploy_runner"], "deploy"]),
        ("loopback_probe", ["python3", plan["deploy_runner"], "loopback-probe", "--as-of-date", "AUTO_YESTERDAY"]),
        ("public_probe", ["python3", plan["deploy_runner"], "public-probe", "--as-of-date", "AUTO_YESTERDAY"]),
    ):
        _run_or_raise(command_runner, command, workspace, env=deploy_env)
        executed.append(step)

    public_status = _verify_public_operator_label(plan.get("expected_public_label"))
    executed.append("post_deploy_public_verify")
    result = TargetProductionResult(
        status="post_deploy_passed" if public_status == "passed" else "rollback_required",
        allowed=True,
        blockers=() if public_status == "passed" else ("public verify failed",),
        warnings=decision.warnings,
        plan=plan,
        executed_steps=tuple(executed),
        target_branch=plan["branch_name"],
        target_pr_url=pr_url,
        target_pr_number=pr_number,
        pre_merge_main_commit=pre_merge_main,
        merge_commit=merge_commit,
        backup_path=backup_path,
        deploy_status="passed",
        public_verify_status=public_status,
        rollback_plan_path=str(rollback_plan_path),
    )
    result_path = run_dir / "production_lane_result.json"
    result_path.write_text(json.dumps(target_production_result_to_dict(result), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


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
        ["ssh", "wb-core-eu-root", "<create app backup>"],
        *[shlex.split(command) for command in plan["deploy_commands"]],
    ]


def _create_remote_app_backup(command_runner: CommandRunner, cwd: Path, run_id: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_run = slug_state_component(run_id, fallback="run")
    backup_path = f"{APP_BACKUP_DIR}/app_{safe_run}_{timestamp}.tar.gz"
    remote = (
        f"set -eu; mkdir -p {shlex.quote(APP_BACKUP_DIR)}; "
        f"tar --exclude='.git' --exclude='*.env' --exclude='.env' "
        f"-C /opt/wb-core-runtime -czf {shlex.quote(backup_path)} app; "
        f"test -s {shlex.quote(backup_path)}"
    )
    _run_or_raise(command_runner, ["ssh", "wb-core-eu-root", remote], cwd)
    return backup_path


def _verify_public_operator_label(expected_label: str | None) -> str:
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


def _ensure_tool(name: str, runner: CommandRunner) -> None:
    result = runner(["/usr/bin/env", "sh", "-lc", f"command -v {shlex.quote(name)} >/dev/null"], None)
    if result.returncode != 0:
        raise RuntimeError(f"required tool is missing: {name}")


def _ensure_clean_expected_workspace(workspace: Path, changed_files: Sequence[str]) -> None:
    actual = tuple(_git_stdout(workspace, "diff", "--name-only").splitlines())
    if sorted(actual) != sorted(changed_files):
        raise RuntimeError(f"workspace diff does not match verifier changed_files: actual={actual}, expected={changed_files}")
    _git_checked(workspace, "diff", "--check")


def _gh_json(runner: CommandRunner, cwd: Path, *args: str) -> dict[str, Any]:
    result = _run_or_raise(runner, ["gh", *args], cwd)
    return json.loads(result.stdout)


def _run_or_raise(
    runner: CommandRunner,
    command: Sequence[str],
    cwd: Path | None,
    *,
    env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    if env is not None:
        result = subprocess.run(tuple(command), cwd=cwd, capture_output=True, text=True, check=False, env=dict(env))
    else:
        result = runner(command, cwd)
    if result.returncode != 0:
        raise RuntimeError(_safe_command_output(result) or f"command failed: {command[0]}")
    return result


def _run_command(command: Sequence[str], cwd: Path | None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(tuple(command), cwd=cwd, capture_output=True, text=True, check=False)


def _git_stdout(cwd: Path, *args: str) -> str:
    result = _git(cwd, *args)
    if result.returncode != 0:
        raise RuntimeError(_safe_command_output(result) or f"git {' '.join(args)} failed")
    return result.stdout.strip()


def _git_checked(cwd: Path, *args: str) -> None:
    result = _git(cwd, *args)
    if result.returncode != 0:
        raise RuntimeError(_safe_command_output(result) or f"git {' '.join(args)} failed")


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(("git", *args), cwd=cwd, capture_output=True, text=True, check=False)


def _safe_command_output(result: subprocess.CompletedProcess[str]) -> str:
    text = "\n".join(part for part in (result.stdout.strip(), result.stderr.strip()) if part)
    text = re.sub(r"sk-[A-Za-z0-9_-]{8,}", "sk-***", text)
    text = re.sub(r"(Authorization\s*:\s*Bearer\s+)\S+", r"\1***", text, flags=re.IGNORECASE)
    text = re.sub(r"gh[pousr]_[A-Za-z0-9_]{8,}", "gh_***", text)
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
