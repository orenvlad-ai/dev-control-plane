"""Decision-only target PR, preview and approval workflow contracts."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal, Mapping

from dev_control_plane.state_layout import slug_state_component

WorkflowStatus = Literal["allowed", "denied", "dry_run_ready"]

DEFAULT_TARGET_REPO = "orenvlad-ai/wb-core"
DEFAULT_TARGET_PROJECT_ID = "wb-core"
DEFAULT_BASE_BRANCH = "main"
BRANCH_PREFIX = "devcp"
PREVIEW_BASE_URL = "https://devcontrol.pro/previews/wb-core"
PRODUCTION_DEPLOY_DISABLED_REASON = "production deploy policy is not enabled for target repos"


@dataclass(frozen=True)
class TargetWorkflowDecision:
    status: WorkflowStatus
    action: str
    allowed: bool
    blockers: Sequence[str]
    warnings: Sequence[str]
    plan: Mapping[str, Any]


def build_target_pr_plan(payload: Mapping[str, Any]) -> TargetWorkflowDecision:
    """Build a non-mutating target PR plan from managed workspace output."""

    blockers = _common_target_blockers(payload)
    if _bool(payload.get("push_to_main")):
        blockers.append("target PR workflow must not push to main")
    if _bool(payload.get("auto_merge")):
        blockers.append("target PR auto-merge is disabled without explicit approval policy")
    if str(payload.get("workspace_source") or "managed_clone") != "managed_clone":
        blockers.append("target PR changes must come from managed clone workspace")
    if str(payload.get("verifier_status") or "").lower() != "passed":
        blockers.append("verifier must pass before target PR creation")
    if _sequence(payload.get("forbidden_path_hits")):
        blockers.append("forbidden path changes detected")
    if str(payload.get("secrets_scan_status") or "passed") != "passed":
        blockers.append("secrets scan must pass before target PR creation")
    if _text(payload.get("blocker")):
        blockers.append(f"blocker is present: {_text(payload.get('blocker'))}")

    run_id = _required_slug(payload.get("run_id"), fallback="run")
    task_slug = slug_state_component(str(payload.get("task_slug") or payload.get("task_spec_id") or "task"))
    branch_name = f"{BRANCH_PREFIX}/{run_id[:48]}-{task_slug[:48]}"
    changed_files = _sequence(payload.get("changed_files"))
    preview_url = _text(payload.get("preview_url")) or f"{PREVIEW_BASE_URL}/{run_id}/"
    title = _text(payload.get("pr_title")) or f"DevControl: результат {run_id}"
    summary = _text(payload.get("task_spec_summary")) or "TaskSpec summary is not provided."
    verifier_result = _text(payload.get("verifier_result")) or str(payload.get("verifier_status") or "unknown")
    pr_body = _target_pr_body(summary, changed_files, verifier_result, preview_url)
    plan = {
        "target_project_id": DEFAULT_TARGET_PROJECT_ID,
        "target_repo": DEFAULT_TARGET_REPO,
        "base_branch": DEFAULT_BASE_BRANCH,
        "branch_name": branch_name,
        "commit_message": _text(payload.get("commit_message")) or f"DevControl: результат {run_id}",
        "pr_title": title,
        "pr_body": pr_body,
        "draft": True,
        "preview_url": preview_url,
        "mutates_original_target": False,
        "push_to_main_allowed": False,
        "auto_merge_allowed": False,
    }
    return _decision("target_pr_plan", not blockers, blockers, (), plan)


def build_preview_plan(payload: Mapping[str, Any]) -> TargetWorkflowDecision:
    """Build a dry-run preview plan without touching WebCore production runtime."""

    blockers = _common_target_blockers(payload)
    run_id = _required_slug(payload.get("run_id"), fallback="run")
    state_root = Path(str(payload.get("state_root") or "/opt/dev-control-plane-runtime/state"))
    preview_path = (state_root / "previews" / run_id).as_posix()
    preview_url = f"{PREVIEW_BASE_URL}/{run_id}/"
    warnings: list[str] = []
    if not _text(payload.get("preview_runtime_command")):
        warnings.append("real WebCore preview deploy is blocked until a target preview runtime command is defined")
    plan = {
        "target_project_id": DEFAULT_TARGET_PROJECT_ID,
        "preview_status": "contract_only",
        "preview_url": preview_url,
        "preview_state_path": preview_path,
        "requires_auth_boundary": True,
        "uses_devcontrol_domain": True,
        "uses_production_webcore_runtime": False,
        "forbidden_production_paths": [
            "/opt/wb-core-runtime/**",
            "/opt/wb-ai/.env",
            "/etc/nginx/sites-enabled/wb-ai",
        ],
        "public_without_auth_allowed": False,
        "real_preview_deploy_allowed": False,
        "dry_run_only": True,
    }
    return TargetWorkflowDecision(
        status="dry_run_ready" if not blockers else "denied",
        action="preview_plan",
        allowed=not blockers,
        blockers=tuple(blockers),
        warnings=tuple(warnings),
        plan=plan,
    )


def evaluate_target_approval(payload: Mapping[str, Any]) -> TargetWorkflowDecision:
    """Evaluate approve/reject policy without merging or deploying target code."""

    decision = str(payload.get("decision") or "approve").strip().lower()
    blockers = _common_target_blockers(payload)
    if decision not in {"approve", "reject"}:
        blockers.append("decision must be approve or reject")
    if decision == "reject":
        plan = {
            "target_project_id": DEFAULT_TARGET_PROJECT_ID,
            "reject_allowed": not blockers,
            "target_pr_action": "leave_open_or_close_with_comment",
            "production_deploy_allowed": False,
            "production_deploy_reason": PRODUCTION_DEPLOY_DISABLED_REASON,
        }
        return _decision("target_reject_decision", not blockers, blockers, (), plan)

    if str(payload.get("preview_status") or "").lower() != "passed":
        blockers.append("preview must pass before target PR merge approval")
    if str(payload.get("verifier_status") or "").lower() != "passed":
        blockers.append("verifier must pass before target PR merge approval")
    if _sequence(payload.get("forbidden_path_hits")):
        blockers.append("forbidden path changes detected")
    if str(payload.get("secrets_scan_status") or "passed") != "passed":
        blockers.append("secrets scan must pass before target PR merge approval")
    if _text(payload.get("blocker")):
        blockers.append(f"blocker is present: {_text(payload.get('blocker'))}")
    if not _bool(payload.get("target_merge_policy_enabled")):
        blockers.append("target PR merge policy is disabled by default")
    if _bool(payload.get("production_deploy_requested")):
        blockers.append(PRODUCTION_DEPLOY_DISABLED_REASON)
    plan = {
        "target_project_id": DEFAULT_TARGET_PROJECT_ID,
        "target_merge_allowed": not blockers,
        "target_auto_merge_allowed": False,
        "production_deploy_allowed": False,
        "production_deploy_reason": PRODUCTION_DEPLOY_DISABLED_REASON,
    }
    return _decision("target_approve_decision", not blockers, blockers, (), plan)


def target_workflow_decision_to_dict(decision: TargetWorkflowDecision) -> dict[str, Any]:
    return _json_ready(asdict(decision))


def _common_target_blockers(payload: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    if str(payload.get("target_project_id") or DEFAULT_TARGET_PROJECT_ID) != DEFAULT_TARGET_PROJECT_ID:
        blockers.append("target_project_id must be wb-core")
    if str(payload.get("target_repo") or DEFAULT_TARGET_REPO) != DEFAULT_TARGET_REPO:
        blockers.append("target_repo must be orenvlad-ai/wb-core")
    if str(payload.get("base_branch") or DEFAULT_BASE_BRANCH) != DEFAULT_BASE_BRANCH:
        blockers.append("base_branch must be main")
    if str(payload.get("target_source_mode") or "remote_managed_clone") != "remote_managed_clone":
        blockers.append("target source must be remote_managed_clone")
    if _bool(payload.get("direct_target_mutation")):
        blockers.append("direct target mutation is forbidden")
    if _bool(payload.get("production_deploy_requested")) and not _bool(payload.get("allow_production_deploy_policy")):
        blockers.append(PRODUCTION_DEPLOY_DISABLED_REASON)
    return blockers


def _target_pr_body(summary: str, changed_files: Sequence[str], verifier_result: str, preview_url: str) -> str:
    changed_block = "\n".join(f"- `{path}`" for path in changed_files) or "- нет файлов в плане"
    return "\n".join(
        (
            "## Сводка TaskSpec",
            "",
            summary,
            "",
            "## Изменённые файлы",
            "",
            changed_block,
            "",
            "## Результат verifier",
            "",
            verifier_result,
            "",
            "## Preview URL",
            "",
            preview_url,
            "",
            "## Откат / закрытие",
            "",
            "Закрыть PR и удалить ветку `devcp/*`; production не изменяется.",
            "",
        )
    )


def _decision(
    action: str,
    allowed: bool,
    blockers: Sequence[str],
    warnings: Sequence[str],
    plan: Mapping[str, Any],
) -> TargetWorkflowDecision:
    return TargetWorkflowDecision(
        status="allowed" if allowed else "denied",
        action=action,
        allowed=allowed,
        blockers=tuple(blockers),
        warnings=tuple(warnings),
        plan=plan,
    )


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


def _text(value: Any) -> str:
    return str(value or "").strip()


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _json_ready(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    return value
