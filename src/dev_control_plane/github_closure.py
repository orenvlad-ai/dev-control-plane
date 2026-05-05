"""GitHub closure policy helpers for dev-control-plane-owned PRs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

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


def _is_codex_owned_branch(branch_name: str, codex_owned_branch: bool) -> bool:
    return codex_owned_branch and branch_name.startswith(CODEX_BRANCH_PREFIX)


def _protected_docset_hits(changed_files: Sequence[str]) -> tuple[str, ...]:
    hits = [
        path
        for path in changed_files
        if path == DOCSET_MANIFEST or path.startswith(DERIVED_PACK_PREFIX)
    ]
    return tuple(sorted(set(hits)))
