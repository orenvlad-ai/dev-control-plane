"""Selected Merge & Deploy planning for DevControl parallel/operator flows."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence
import uuid

from dev_control_plane.state_layout import safe_state_component


@dataclass(frozen=True)
class SelectedPromotionCandidate:
    candidate_id: str
    selected_id: str
    selection_type: str
    target_id: str
    source_kind: str
    status: str
    lifecycle_status: str
    managed_run_id: str | None = None
    task_id: str | None = None
    changed_files: tuple[str, ...] = ()
    finished_at: str | None = None
    base_commit: str | None = None
    blocker: str | None = None
    risk: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["changed_files"] = list(self.changed_files)
        return payload


@dataclass(frozen=True)
class SelectedPromotionPlan:
    target_id: str
    selected_count: int
    ordered: tuple[SelectedPromotionCandidate, ...] = ()
    deferred: tuple[SelectedPromotionCandidate, ...] = ()
    blocked: tuple[SelectedPromotionCandidate, ...] = ()
    refresh_required: tuple[SelectedPromotionCandidate, ...] = ()
    reasons: tuple[str, ...] = ()
    conflict_reason_by_task: Mapping[str, str] = field(default_factory=dict)
    mode: str = "auto_order"
    status: str = "planned"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "target_id": self.target_id,
            "selected_count": self.selected_count,
            "mode": self.mode,
            "accepted_task_ids": [candidate.candidate_id for candidate in self.ordered],
            "deferred_task_ids": [candidate.candidate_id for candidate in self.deferred],
            "conflict_detected": bool(self.deferred),
            "conflict_reason_by_task": dict(self.conflict_reason_by_task),
            "ordered": [candidate.to_dict() for candidate in self.ordered],
            "deferred": [candidate.to_dict() for candidate in self.deferred],
            "blocked": [candidate.to_dict() for candidate in self.blocked],
            "refresh_required": [candidate.to_dict() for candidate in self.refresh_required],
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class SelectedPromotionGroup:
    group_id: str
    target_id: str
    selected_ids: tuple[str, ...]
    selection_type: str
    mode: str
    status: str
    created_at: str
    updated_at: str
    planned_order: tuple[str, ...] = ()
    accepted_task_ids: tuple[str, ...] = ()
    deferred_task_ids: tuple[str, ...] = ()
    blocked_ids: tuple[str, ...] = ()
    refresh_required_ids: tuple[str, ...] = ()
    current_step: str | None = None
    per_task_status: Mapping[str, str] = field(default_factory=dict)
    conflict_reason_by_task: Mapping[str, str] = field(default_factory=dict)
    blocker: str | None = None
    finished_at: str | None = None
    cancelled_at: str | None = None
    expired_at: str | None = None
    production_run_id: str | None = None
    production_run_ids: tuple[str, ...] = ()
    pr_urls: tuple[str, ...] = ()
    merge_commits: tuple[str, ...] = ()
    deploy_status: str | None = None
    public_verify_status: str | None = None
    conflicted_ids: tuple[str, ...] = ()
    conflict_files: tuple[str, ...] = ()
    recommended_action: str | None = None
    confirm_merge_deploy: bool = False
    allow_real_production_promotion: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["selected_ids"] = list(self.selected_ids)
        payload["planned_order"] = list(self.planned_order)
        payload["accepted_task_ids"] = list(self.accepted_task_ids)
        payload["deferred_task_ids"] = list(self.deferred_task_ids)
        payload["blocked_ids"] = list(self.blocked_ids)
        payload["refresh_required_ids"] = list(self.refresh_required_ids)
        payload["per_task_status"] = dict(self.per_task_status)
        payload["conflict_reason_by_task"] = dict(self.conflict_reason_by_task)
        payload["production_run_ids"] = list(self.production_run_ids)
        payload["pr_urls"] = list(self.pr_urls)
        payload["merge_commits"] = list(self.merge_commits)
        payload["conflicted_ids"] = list(self.conflicted_ids)
        payload["conflict_files"] = list(self.conflict_files)
        return payload


def plan_selected_promotion(
    candidates: Sequence[SelectedPromotionCandidate],
    *,
    target_id: str,
    mode: str = "auto_order",
    allow_refresh: bool = False,
) -> SelectedPromotionPlan:
    blocked: list[SelectedPromotionCandidate] = []
    ready: list[SelectedPromotionCandidate] = []
    deferred: list[SelectedPromotionCandidate] = []
    refresh_required: list[SelectedPromotionCandidate] = []
    reasons: list[str] = []
    conflict_reason_by_task: dict[str, str] = {}
    for candidate in candidates:
        if candidate.target_id != target_id:
            blocked.append(_with_blocker(candidate, f"target mismatch: {candidate.target_id}"))
            continue
        if candidate.lifecycle_status == "refresh_required" or candidate.status in {"refresh_required", "frozen_base_stale"}:
            refresh_required.append(_with_blocker(candidate, "candidate requires refresh/reverify before promotion"))
            continue
        if candidate.blocker:
            blocked.append(candidate)
            continue
        if candidate.lifecycle_status not in {"ready_for_promotion", "ready_for_separate_deploy"}:
            blocked.append(_with_blocker(candidate, f"candidate lifecycle is not ready_for_promotion: {candidate.lifecycle_status}"))
            continue
        ready.append(candidate)
    ordered: list[SelectedPromotionCandidate] = []
    seen_files: set[str] = set()
    for candidate in sorted(ready, key=_candidate_sort_key):
        files = set(candidate.changed_files)
        overlap = files & seen_files
        if overlap:
            reason = f"changed-file overlap with current group: {', '.join(sorted(overlap)[:5])}"
            if allow_refresh:
                reasons.append(f"{candidate.candidate_id} overlaps earlier selected files and must be rebased/reverified before promotion")
            else:
                deferred.append(_with_status(candidate, status="ready_for_separate_deploy", lifecycle_status="ready_for_separate_deploy"))
                conflict_reason_by_task[candidate.candidate_id] = reason
                reasons.append(f"{candidate.candidate_id} overlaps earlier selected files and is deferred for a separate deploy")
                continue
        ordered.append(candidate)
        seen_files.update(files)
    if not ordered and deferred and not blocked and not refresh_required:
        status = "deferred_only"
    elif not ordered and (blocked or refresh_required):
        status = "blocked"
    elif deferred:
        status = "planned_with_deferred"
    elif refresh_required:
        status = "planned_with_refresh_required"
    elif blocked:
        status = "planned_with_blockers"
    else:
        status = "planned"
    if ordered:
        reasons.append("production lane remains serial; planned_order is deterministic")
    return SelectedPromotionPlan(
        target_id=target_id,
        selected_count=len(candidates),
        ordered=tuple(ordered),
        deferred=tuple(deferred),
        blocked=tuple(blocked),
        refresh_required=tuple(refresh_required),
        reasons=tuple(dict.fromkeys(reasons)),
        conflict_reason_by_task=conflict_reason_by_task,
        mode=mode,
        status=status,
    )


def new_group_id(prefix: str = "promotion-group") -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return safe_state_component(f"{prefix}-{timestamp}-{uuid.uuid4().hex[:10]}", "group_id")


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def candidate_from_mapping(payload: Mapping[str, Any]) -> SelectedPromotionCandidate:
    return SelectedPromotionCandidate(
        candidate_id=str(payload.get("candidate_id") or payload.get("task_id") or payload.get("run_id") or ""),
        selected_id=str(payload.get("selected_id") or payload.get("candidate_id") or payload.get("task_id") or payload.get("run_id") or ""),
        selection_type=str(payload.get("selection_type") or "auto"),
        target_id=str(payload.get("target_id") or ""),
        source_kind=str(payload.get("source_kind") or ""),
        status=str(payload.get("status") or ""),
        lifecycle_status=str(payload.get("lifecycle_status") or payload.get("operator_lifecycle_status") or ""),
        managed_run_id=str(payload.get("managed_run_id") or "") or None,
        task_id=str(payload.get("task_id") or "") or None,
        changed_files=tuple(str(item) for item in payload.get("changed_files") or ()),
        finished_at=str(payload.get("finished_at") or "") or None,
        base_commit=str(payload.get("base_commit") or "") or None,
        blocker=str(payload.get("blocker") or "") or None,
        risk=str(payload.get("risk") or "unknown"),
    )


def group_from_mapping(payload: Mapping[str, Any]) -> SelectedPromotionGroup:
    return SelectedPromotionGroup(
        group_id=str(payload.get("group_id") or ""),
        target_id=str(payload.get("target_id") or ""),
        selected_ids=tuple(str(item) for item in payload.get("selected_ids") or ()),
        selection_type=str(payload.get("selection_type") or "auto"),
        mode=str(payload.get("mode") or "auto_order"),
        status=str(payload.get("status") or "planned"),
        created_at=str(payload.get("created_at") or ""),
        updated_at=str(payload.get("updated_at") or ""),
        planned_order=tuple(str(item) for item in payload.get("planned_order") or ()),
        accepted_task_ids=tuple(str(item) for item in payload.get("accepted_task_ids") or ()),
        deferred_task_ids=tuple(str(item) for item in payload.get("deferred_task_ids") or ()),
        blocked_ids=tuple(str(item) for item in payload.get("blocked_ids") or ()),
        refresh_required_ids=tuple(str(item) for item in payload.get("refresh_required_ids") or ()),
        current_step=str(payload.get("current_step") or "") or None,
        per_task_status=dict(payload.get("per_task_status") or {}),
        conflict_reason_by_task=dict(payload.get("conflict_reason_by_task") or {}),
        blocker=str(payload.get("blocker") or "") or None,
        finished_at=str(payload.get("finished_at") or "") or None,
        cancelled_at=str(payload.get("cancelled_at") or "") or None,
        expired_at=str(payload.get("expired_at") or "") or None,
        production_run_id=str(payload.get("production_run_id") or "") or None,
        production_run_ids=tuple(str(item) for item in payload.get("production_run_ids") or ()),
        pr_urls=tuple(str(item) for item in payload.get("pr_urls") or ()),
        merge_commits=tuple(str(item) for item in payload.get("merge_commits") or ()),
        deploy_status=str(payload.get("deploy_status") or "") or None,
        public_verify_status=str(payload.get("public_verify_status") or "") or None,
        conflicted_ids=tuple(str(item) for item in payload.get("conflicted_ids") or ()),
        conflict_files=tuple(str(item) for item in payload.get("conflict_files") or ()),
        recommended_action=str(payload.get("recommended_action") or "") or None,
        confirm_merge_deploy=bool(payload.get("confirm_merge_deploy", False)),
        allow_real_production_promotion=bool(payload.get("allow_real_production_promotion", False)),
    )


def _candidate_sort_key(candidate: SelectedPromotionCandidate) -> tuple[int, str, str]:
    return (_risk_score(candidate), candidate.finished_at or "", candidate.candidate_id)


def _risk_score(candidate: SelectedPromotionCandidate) -> int:
    files = list(candidate.changed_files)
    if not files:
        return 2
    if all(_docs_file(path) for path in files):
        return 0
    if all(_ui_file(path) or _docs_file(path) for path in files):
        return 1
    return 2


def _docs_file(path: str) -> bool:
    return path in {"README.md", "AGENTS.md"} or path.startswith(("docs/", "migration/"))


def _ui_file(path: str) -> bool:
    return path.endswith((".html", ".css", ".js", ".ts", ".tsx")) or "/templates/" in path


def _with_blocker(candidate: SelectedPromotionCandidate, blocker: str) -> SelectedPromotionCandidate:
    return SelectedPromotionCandidate(
        candidate_id=candidate.candidate_id,
        selected_id=candidate.selected_id,
        selection_type=candidate.selection_type,
        target_id=candidate.target_id,
        source_kind=candidate.source_kind,
        status=candidate.status,
        lifecycle_status=candidate.lifecycle_status,
        managed_run_id=candidate.managed_run_id,
        task_id=candidate.task_id,
        changed_files=candidate.changed_files,
        finished_at=candidate.finished_at,
        base_commit=candidate.base_commit,
        blocker=blocker,
        risk=candidate.risk,
    )


def _with_status(candidate: SelectedPromotionCandidate, *, status: str, lifecycle_status: str) -> SelectedPromotionCandidate:
    return SelectedPromotionCandidate(
        candidate_id=candidate.candidate_id,
        selected_id=candidate.selected_id,
        selection_type=candidate.selection_type,
        target_id=candidate.target_id,
        source_kind=candidate.source_kind,
        status=status,
        lifecycle_status=lifecycle_status,
        managed_run_id=candidate.managed_run_id,
        task_id=candidate.task_id,
        changed_files=candidate.changed_files,
        finished_at=candidate.finished_at,
        base_commit=candidate.base_commit,
        blocker=None,
        risk=candidate.risk,
    )
