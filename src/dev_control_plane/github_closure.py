"""GitHub closure policy helpers for dev-control-plane-owned PRs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

DEV_CONTROL_PLANE_REPO = "orenvlad-ai/dev-control-plane"
CODEX_BRANCH_PREFIX = "codex/"
DERIVED_PACK_PREFIX = "dev_control_plane_docs_master/"
DOCSET_MANIFEST = "99_MANIFEST__DOCSET_VERSION.md"
TASK_CLASSES = {"L1", "L2", "L3"}


@dataclass(frozen=True)
class MergeEligibilityInput:
    repo: str
    task_class: str
    pr_number: int | None
    pr_state: str
    branch_name: str
    expected_head_sha: str
    pr_head_sha: str
    working_tree_clean: bool
    required_checks_passed: bool
    diff_check_passed: bool
    cached_diff_check_passed: bool
    verifier_status: str
    forbidden_path_hits: Sequence[str] = field(default_factory=tuple)
    forbidden_action_hits: Sequence[str] = field(default_factory=tuple)
    changed_files: Sequence[str] = field(default_factory=tuple)
    secrets_scan_passed: bool = False
    handoff_required_fields_present: bool = False
    handoff_has_compact_check: bool = False
    blocker: str | None = None
    no_auto_merge: bool = False
    codex_owned_branch: bool = False
    pr_created_for_current_task: bool = False
    derived_sync_task: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "forbidden_path_hits", tuple(str(path) for path in self.forbidden_path_hits))
        object.__setattr__(self, "forbidden_action_hits", tuple(str(action) for action in self.forbidden_action_hits))
        object.__setattr__(self, "changed_files", tuple(str(path) for path in self.changed_files))


@dataclass(frozen=True)
class MergeEligibilityResult:
    allowed: bool
    blockers: tuple[str, ...]


@dataclass(frozen=True)
class GitHubClosureDecision:
    allowed: bool
    blockers: tuple[str, ...]
    merge_allowed: bool
    delete_branch_allowed: bool
    mode: str = "decision_only"
    actual_merge_executed: bool = False
    actual_branch_deleted: bool = False
    next_manual_step: str | None = None


def evaluate_dev_control_plane_merge_eligibility(payload: MergeEligibilityInput) -> MergeEligibilityResult:
    blockers: list[str] = []

    if payload.repo != DEV_CONTROL_PLANE_REPO:
        blockers.append(f"repo is not dev-control-plane: {payload.repo}")
    if payload.task_class not in TASK_CLASSES:
        blockers.append(f"unknown task class: {payload.task_class}")
    if not payload.pr_created_for_current_task and not _is_codex_owned_branch(payload.branch_name, payload.codex_owned_branch):
        blockers.append("PR is not current-task or codex-owned")
    if payload.pr_number is None:
        blockers.append("PR number is missing")
    if payload.pr_state.upper() != "OPEN":
        blockers.append(f"PR is not open: {payload.pr_state}")
    if not payload.expected_head_sha or payload.pr_head_sha != payload.expected_head_sha:
        blockers.append("PR head SHA does not match expected SHA")
    if not payload.working_tree_clean:
        blockers.append("git working tree is not clean")
    if not payload.required_checks_passed:
        blockers.append("required checks did not pass")
    if not payload.diff_check_passed:
        blockers.append("git diff --check did not pass")
    if not payload.cached_diff_check_passed:
        blockers.append("git diff --cached --check did not pass")
    if payload.verifier_status != "passed":
        blockers.append(f"verifier is not passed: {payload.verifier_status}")
    if payload.forbidden_path_hits:
        blockers.append("forbidden paths detected: " + ", ".join(payload.forbidden_path_hits))
    if payload.forbidden_action_hits:
        blockers.append("forbidden actions detected: " + ", ".join(payload.forbidden_action_hits))
    protected_hits = _protected_docset_hits(payload.changed_files)
    if protected_hits and not payload.derived_sync_task:
        blockers.append("protected derived docset paths changed: " + ", ".join(protected_hits))
    if not payload.secrets_scan_passed:
        blockers.append("secrets scan did not pass")
    if not payload.handoff_required_fields_present:
        blockers.append("handoff required fields are missing")
    if not payload.handoff_has_compact_check:
        blockers.append("handoff compact check block is missing")
    if payload.blocker:
        blockers.append(f"blocker present: {payload.blocker}")
    if payload.no_auto_merge:
        blockers.append("NO_AUTO_MERGE is set")

    return MergeEligibilityResult(allowed=not blockers, blockers=tuple(blockers))


def evaluate_dev_control_plane_closure_decision(
    payload: Mapping[str, Any] | MergeEligibilityInput,
    *,
    requested_auto_merge: bool = False,
) -> GitHubClosureDecision:
    eligibility = payload if isinstance(payload, MergeEligibilityInput) else merge_eligibility_input_from_mapping(payload)
    result = evaluate_dev_control_plane_merge_eligibility(eligibility)
    blockers = result.blockers
    if requested_auto_merge and not result.allowed:
        next_manual_step = "Leave PR open and resolve exact blockers before merge."
    elif requested_auto_merge:
        next_manual_step = "GitHub merge/delete branch may run through the external gh workflow."
    else:
        next_manual_step = "Decision only; no GitHub mutation was requested."
    return GitHubClosureDecision(
        allowed=result.allowed,
        blockers=blockers,
        merge_allowed=result.allowed and requested_auto_merge,
        delete_branch_allowed=result.allowed and requested_auto_merge,
        next_manual_step=next_manual_step,
    )


def merge_eligibility_input_from_mapping(payload: Mapping[str, Any]) -> MergeEligibilityInput:
    return MergeEligibilityInput(
        repo=_required_str(payload, "repo"),
        task_class=_required_str(payload, "task_class"),
        pr_number=_optional_int(payload.get("pr_number")),
        pr_state=_required_str(payload, "pr_state"),
        branch_name=_required_str(payload, "branch_name"),
        expected_head_sha=_required_str(payload, "expected_head_sha"),
        pr_head_sha=_required_str(payload, "pr_head_sha"),
        working_tree_clean=_bool(payload.get("working_tree_clean")),
        required_checks_passed=_bool(payload.get("required_checks_passed")),
        diff_check_passed=_bool(payload.get("diff_check_passed")),
        cached_diff_check_passed=_bool(payload.get("cached_diff_check_passed")),
        verifier_status=_required_str(payload, "verifier_status"),
        forbidden_path_hits=_str_sequence(payload.get("forbidden_path_hits", ())),
        forbidden_action_hits=_str_sequence(payload.get("forbidden_action_hits", ())),
        changed_files=_str_sequence(payload.get("changed_files", ())),
        secrets_scan_passed=_bool(payload.get("secrets_scan_passed")),
        handoff_required_fields_present=_bool(payload.get("handoff_required_fields_present")),
        handoff_has_compact_check=_bool(payload.get("handoff_has_compact_check")),
        blocker=_optional_str(payload.get("blocker")),
        no_auto_merge=_bool(payload.get("no_auto_merge")),
        codex_owned_branch=_bool(payload.get("codex_owned_branch")),
        pr_created_for_current_task=_bool(payload.get("pr_created_for_current_task")),
        derived_sync_task=_bool(payload.get("derived_sync_task")),
    )


def github_closure_decision_to_dict(decision: GitHubClosureDecision) -> dict[str, Any]:
    return {
        "status": "allowed" if decision.allowed else "denied",
        "allowed": decision.allowed,
        "blockers": list(decision.blockers),
        "merge_allowed": decision.merge_allowed,
        "delete_branch_allowed": decision.delete_branch_allowed,
        "mode": decision.mode,
        "actual_merge_executed": decision.actual_merge_executed,
        "actual_branch_deleted": decision.actual_branch_deleted,
        "next_manual_step": decision.next_manual_step,
        "decision_source": "dev_control_plane.github_closure",
    }


def _is_codex_owned_branch(branch_name: str, codex_owned_branch: bool) -> bool:
    return codex_owned_branch and branch_name.startswith(CODEX_BRANCH_PREFIX)


def _protected_docset_hits(changed_files: Sequence[str]) -> tuple[str, ...]:
    hits = [
        path
        for path in changed_files
        if path == DOCSET_MANIFEST or path.startswith(DERIVED_PACK_PREFIX)
    ]
    return tuple(sorted(set(hits)))


def _required_str(payload: Mapping[str, Any], key: str) -> str:
    value = str(payload.get(key) or "").strip()
    if not value:
        raise ValueError(f"{key} is required")
    return value


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _str_sequence(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)):
        return (str(value),)
    if not isinstance(value, Sequence):
        raise ValueError("expected a sequence")
    return tuple(str(item) for item in value)
