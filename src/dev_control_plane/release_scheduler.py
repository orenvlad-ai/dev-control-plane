"""Deterministic release scheduling and immutable RELEASE_PLAN cases.

The scheduler never mutates GitHub or registry state.  It either returns a
mechanical deterministic sequence or freezes one semantic case that a fresh
schema-bound arbiter may answer once.  Arbiter answers are accepted only while
every task revision, PR head and resource binding remains exact.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any, Iterable, Sequence

from .orchestration_contracts import ArbiterDecision, RevisionBinding

_SHA_RE = re.compile(r"^[0-9a-f]{40,64}$")
SEMANTIC_RELEASE_REASONS = frozenset(
    {
        "overlapping_files",
        "overlapping_modules",
        "overlapping_resources",
        "shared_database",
        "shared_schema",
        "shared_migration",
        "shared_contract",
        "explicit_dependency",
        "active_multi_pr_lane_competition",
        "merge_conflict",
        "passport_diff_mismatch",
        "unknown_classification",
        "multiple_safe_orders",
    }
)


class ReleaseSchedulingError(ValueError):
    """A release candidate or semantic decision violates deterministic policy."""


class StaleArbiterDecision(ReleaseSchedulingError):
    """An arbiter answer no longer matches its immutable case."""


@dataclass(frozen=True)
class ReleaseCandidate:
    candidate_id: str
    task_id: str
    workstream_id: str
    logical_lane_id: str
    target_id: str
    task_revision: int
    workstream_revision: int
    pr_head_sha: str
    resources: Sequence[str]
    passport_files: Sequence[str]
    diff_files: Sequence[str]
    modules: Sequence[str] = field(default_factory=tuple)
    databases: Sequence[str] = field(default_factory=tuple)
    schemas: Sequence[str] = field(default_factory=tuple)
    migrations: Sequence[str] = field(default_factory=tuple)
    shared_contracts: Sequence[str] = field(default_factory=tuple)
    dependencies: Sequence[str] = field(default_factory=tuple)
    owner_priority: int | None = None
    critical_path_value: int = 0
    unblock_value: int = 0
    risk_score: int = 0
    fairness_credit: int = 0
    ready_since: str = "1970-01-01T00:00:00Z"
    created_at: str = "1970-01-01T00:00:00Z"
    checks_green: bool = True
    admission_ready: bool = True
    merge_conflict: bool = False
    passport_diff_mismatch: bool = False
    unknown_classification: bool = False
    holds_logical_lane: bool = False
    lane_healthy: bool = True
    multi_pr_intent: bool = False
    multiple_safe_orders: bool = False

    def __post_init__(self) -> None:
        for name in ("candidate_id", "task_id", "workstream_id", "logical_lane_id", "target_id"):
            _machine(name, getattr(self, name))
        for name in ("task_revision", "workstream_revision"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ReleaseSchedulingError(f"{name} must be a positive integer")
        if not _SHA_RE.fullmatch(self.pr_head_sha):
            raise ReleaseSchedulingError("pr_head_sha must be a lowercase Git object id")
        for name in (
            "resources", "passport_files", "diff_files", "modules", "databases", "schemas",
            "migrations", "shared_contracts",
        ):
            object.__setattr__(self, name, _unique_values(name, getattr(self, name)))
        object.__setattr__(self, "dependencies", _unique_machine_values("dependencies", self.dependencies))
        if not self.resources:
            raise ReleaseSchedulingError("release candidate must classify at least one resource")
        if self.task_id in self.dependencies:
            raise ReleaseSchedulingError("release candidate cannot depend on itself")
        if self.owner_priority is not None and (
            isinstance(self.owner_priority, bool) or not isinstance(self.owner_priority, int) or self.owner_priority < 0
        ):
            raise ReleaseSchedulingError("owner_priority must be a non-negative integer or null")
        for name in ("critical_path_value", "unblock_value", "risk_score", "fairness_credit"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ReleaseSchedulingError(f"{name} must be a non-negative integer")
        _timestamp("ready_since", self.ready_since)
        _timestamp("created_at", self.created_at)
        for name in (
            "checks_green", "admission_ready", "merge_conflict", "passport_diff_mismatch",
            "unknown_classification", "holds_logical_lane", "lane_healthy", "multi_pr_intent",
            "multiple_safe_orders",
        ):
            if not isinstance(getattr(self, name), bool):
                raise ReleaseSchedulingError(f"{name} must be a boolean")

    @property
    def mechanically_ready(self) -> bool:
        return (
            self.checks_green
            and self.admission_ready
            and not self.merge_conflict
            and not self.passport_diff_mismatch
            and not self.unknown_classification
        )

    def binding(self) -> RevisionBinding:
        return RevisionBinding(
            task_id=self.task_id,
            task_revision=self.task_revision,
            workstream_id=self.workstream_id,
            workstream_revision=self.workstream_revision,
            pr_head_sha=self.pr_head_sha,
            resources=tuple(sorted(self.resources)),
        )


@dataclass(frozen=True)
class SemanticReleaseCase:
    case_id: str
    case_digest: str
    reasons: Sequence[str]
    candidates: Sequence[ReleaseCandidate]
    created_at: str

    def __post_init__(self) -> None:
        _machine("case_id", self.case_id)
        if not re.fullmatch(r"[0-9a-f]{64}", self.case_digest):
            raise ReleaseSchedulingError("case_digest must be sha256")
        reasons = tuple(sorted(set(self.reasons)))
        if not reasons or not set(reasons).issubset(SEMANTIC_RELEASE_REASONS):
            raise ReleaseSchedulingError("semantic case has no valid mandatory reason")
        candidates = tuple(self.candidates)
        if not candidates:
            raise ReleaseSchedulingError("semantic case must contain candidates")
        object.__setattr__(self, "reasons", reasons)
        object.__setattr__(self, "candidates", candidates)
        _timestamp("created_at", self.created_at)


@dataclass(frozen=True)
class ScheduleDecision:
    kind: str
    candidate_ids: Sequence[str] = field(default_factory=tuple)
    reason: str | None = None
    semantic_case: SemanticReleaseCase | None = None

    def __post_init__(self) -> None:
        if self.kind not in {"release_sequence", "semantic_release_plan", "wait"}:
            raise ReleaseSchedulingError(f"unknown schedule decision: {self.kind!r}")
        object.__setattr__(self, "candidate_ids", tuple(self.candidate_ids))
        if self.kind == "semantic_release_plan" and self.semantic_case is None:
            raise ReleaseSchedulingError("semantic_release_plan requires a frozen case")
        if self.kind != "semantic_release_plan" and self.semantic_case is not None:
            raise ReleaseSchedulingError("only semantic_release_plan may carry a case")


def schedule_releases(
    candidates: Sequence[ReleaseCandidate],
    *,
    completed_task_ids: Iterable[str] = (),
    active_logical_lane_id: str | None = None,
    now: str | None = None,
) -> ScheduleDecision:
    """Return a deterministic release sequence or one immutable semantic case."""

    items = tuple(candidates)
    ids = [candidate.candidate_id for candidate in items]
    if len(set(ids)) != len(ids):
        raise ReleaseSchedulingError("candidate_id values must be unique")
    task_ids = [candidate.task_id for candidate in items]
    workstream_bindings = [
        (candidate.task_id, candidate.workstream_id) for candidate in items
    ]
    if len(set(workstream_bindings)) != len(workstream_bindings):
        raise ReleaseSchedulingError(
            "one scheduler snapshot may contain only one ready candidate per workstream"
        )
    if active_logical_lane_id is not None:
        _machine("active_logical_lane_id", active_logical_lane_id)
    if not items:
        return ScheduleDecision(kind="wait", reason="no_ready_candidates")

    completed = set(completed_task_ids)
    candidates_by_task: dict[str, list[ReleaseCandidate]] = {}
    for candidate in items:
        candidates_by_task.setdefault(candidate.task_id, []).append(candidate)

    # Merely mentioning an unresolved dependency in the same snapshot is not
    # completion evidence.  It may unlock dependants only when *all* of that
    # task's current candidates are admitted/green, so the semantic DAG can
    # bind every predecessor.  This fixed point also prevents a red A from
    # being bypassed by a green B -> A (including transitive chains).
    schedulable_tasks = set(completed)
    while True:
        newly_schedulable = {
            task_id
            for task_id, task_candidates in candidates_by_task.items()
            if task_id not in schedulable_tasks
            and all(
                candidate.checks_green and candidate.admission_ready
                for candidate in task_candidates
            )
            and all(
                dependency in schedulable_tasks
                for candidate in task_candidates
                for dependency in candidate.dependencies
            )
        }
        if not newly_schedulable:
            break
        schedulable_tasks.update(newly_schedulable)

    considered = tuple(
        candidate for candidate in items if candidate.task_id in schedulable_tasks
    )
    if not considered:
        return ScheduleDecision(kind="wait", reason="dependencies_not_complete")

    # A non-ready candidate cannot force a green, independent candidate into a
    # semantic case.  Conflict/mismatch candidates are semantic-eligible only
    # after checks and admission; unsafe singletons wait for correction.
    semantic_eligible = tuple(
        candidate for candidate in considered if candidate.checks_green and candidate.admission_ready
    )
    reasons = (
        _semantic_reasons(semantic_eligible, active_logical_lane_id=active_logical_lane_id)
        if len(semantic_eligible) >= 2
        else ()
    )
    if reasons:
        case = build_semantic_release_case(semantic_eligible, reasons=reasons, created_at=now)
        return ScheduleDecision(kind="semantic_release_plan", semantic_case=case, reason=",".join(reasons))

    ready = tuple(candidate for candidate in considered if candidate.mechanically_ready)
    if not ready:
        return ScheduleDecision(kind="wait", reason="checks_admission_or_conflict")

    ordered = _deterministic_order(ready, active_logical_lane_id=active_logical_lane_id)
    return ScheduleDecision(
        kind="release_sequence",
        candidate_ids=tuple(candidate.candidate_id for candidate in ordered),
        reason="mechanical_hard_order",
    )


def build_semantic_release_case(
    candidates: Sequence[ReleaseCandidate],
    *,
    reasons: Sequence[str],
    created_at: str | None = None,
) -> SemanticReleaseCase:
    frozen_candidates = tuple(sorted(candidates, key=lambda item: item.candidate_id))
    frozen_reasons = tuple(sorted(set(reasons)))
    timestamp = created_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    snapshot = {
        "kind": "RELEASE_PLAN",
        "reasons": frozen_reasons,
        "candidates": [_candidate_snapshot(candidate) for candidate in frozen_candidates],
    }
    digest = hashlib.sha256(_canonical_json(snapshot).encode("utf-8")).hexdigest()
    return SemanticReleaseCase(
        case_id=f"release-plan:{digest[:24]}",
        case_digest=digest,
        reasons=frozen_reasons,
        candidates=frozen_candidates,
        created_at=timestamp,
    )


def validate_arbiter_release_decision(
    semantic_case: SemanticReleaseCase,
    decision: ArbiterDecision,
) -> tuple[str, ...]:
    """Validate exact case/revision/SHA/resource binding and return topological step ids."""

    if decision.kind != "release_plan":
        raise StaleArbiterDecision("arbiter answer is not a RELEASE_PLAN decision")
    if decision.case_id != semantic_case.case_id or decision.case_digest != semantic_case.case_digest:
        raise StaleArbiterDecision("arbiter answer belongs to another immutable case")
    expected = {
        (binding.task_id, binding.workstream_id): _binding_snapshot(binding)
        for binding in (candidate.binding() for candidate in semantic_case.candidates)
    }
    observed = {
        (binding.task_id, binding.workstream_id): _binding_snapshot(binding)
        for binding in decision.bindings
    }
    if observed != expected:
        raise StaleArbiterDecision("task revision, PR head or resource binding is stale")
    covered = {(step.task_id, step.workstream_id) for step in decision.steps}
    if covered != set(expected):
        raise StaleArbiterDecision("arbiter sequence must account for every candidate exactly by binding")
    order = _topological_step_order(decision)
    steps_by_binding = {
        (step.task_id, step.workstream_id): step for step in decision.steps
    }
    candidates_by_binding = {
        (candidate.task_id, candidate.workstream_id): candidate
        for candidate in semantic_case.candidates
    }

    def ancestors(step_id: str) -> set[str]:
        result: set[str] = set()
        pending = list(next(step for step in decision.steps if step.step_id == step_id).depends_on)
        steps_by_id = {step.step_id: step for step in decision.steps}
        while pending:
            dependency = pending.pop()
            if dependency in result:
                continue
            result.add(dependency)
            pending.extend(steps_by_id[dependency].depends_on)
        return result

    active_bindings = {
        binding
        for binding, candidate in candidates_by_binding.items()
        if candidate.holds_logical_lane and candidate.lane_healthy
    }
    for binding, step in steps_by_binding.items():
        if step.action != "release":
            continue
        candidate = candidates_by_binding[binding]
        if not candidate.mechanically_ready:
            raise StaleArbiterDecision(
                "arbiter cannot release an unsafe or unclassified candidate"
            )
        required_predecessors = {
            other_binding
            for other_binding, other in candidates_by_binding.items()
            if other.task_id in candidate.dependencies
        }
        if binding not in active_bindings:
            required_predecessors |= active_bindings
        observed_ancestors = ancestors(step.step_id)
        for predecessor_binding in required_predecessors:
            predecessor = steps_by_binding[predecessor_binding]
            if (
                predecessor.action != "release"
                or predecessor.step_id not in observed_ancestors
            ):
                raise StaleArbiterDecision(
                    "arbiter plan violates dependency or active-lane precedence"
                )
    return order


def revalidate_case_against_candidates(
    semantic_case: SemanticReleaseCase,
    current_candidates: Sequence[ReleaseCandidate],
) -> None:
    expected = {
        candidate.candidate_id: _candidate_snapshot(candidate) for candidate in semantic_case.candidates
    }
    observed = {candidate.candidate_id: _candidate_snapshot(candidate) for candidate in current_candidates}
    if expected != observed:
        raise StaleArbiterDecision("candidate snapshot changed after semantic case creation")


def _semantic_reasons(
    candidates: Sequence[ReleaseCandidate],
    *,
    active_logical_lane_id: str | None,
) -> tuple[str, ...]:
    reasons: set[str] = set()
    for candidate in candidates:
        if candidate.merge_conflict:
            reasons.add("merge_conflict")
        if candidate.passport_diff_mismatch or set(candidate.diff_files) - set(candidate.passport_files):
            reasons.add("passport_diff_mismatch")
        if candidate.unknown_classification:
            reasons.add("unknown_classification")
        if candidate.multiple_safe_orders:
            reasons.add("multiple_safe_orders")

    task_ids = {candidate.task_id for candidate in candidates}
    if any(set(candidate.dependencies) & task_ids for candidate in candidates):
        reasons.add("explicit_dependency")

    lane_holders = [candidate for candidate in candidates if candidate.holds_logical_lane and candidate.multi_pr_intent]
    if len({candidate.logical_lane_id for candidate in lane_holders}) > 1:
        reasons.add("active_multi_pr_lane_competition")
    if active_logical_lane_id is not None:
        active = [candidate for candidate in candidates if candidate.logical_lane_id == active_logical_lane_id]
        competing = [candidate for candidate in candidates if candidate.logical_lane_id != active_logical_lane_id]
        if active and competing and any(_candidates_interact(left, right) for left in active for right in competing):
            reasons.add("active_multi_pr_lane_competition")

    for index, left in enumerate(candidates):
        for right in candidates[index + 1 :]:
            _add_overlap_reason(reasons, "overlapping_files", left.diff_files, right.diff_files)
            _add_overlap_reason(reasons, "overlapping_modules", left.modules, right.modules)
            _add_overlap_reason(reasons, "overlapping_resources", left.resources, right.resources)
            _add_overlap_reason(reasons, "shared_database", left.databases, right.databases)
            _add_overlap_reason(reasons, "shared_schema", left.schemas, right.schemas)
            _add_overlap_reason(reasons, "shared_migration", left.migrations, right.migrations)
            _add_overlap_reason(reasons, "shared_contract", left.shared_contracts, right.shared_contracts)
    return tuple(sorted(reasons))


def _deterministic_order(
    candidates: Sequence[ReleaseCandidate],
    *,
    active_logical_lane_id: str | None,
) -> tuple[ReleaseCandidate, ...]:
    def priority(candidate: ReleaseCandidate) -> tuple[Any, ...]:
        continuity = 0 if active_logical_lane_id and candidate.logical_lane_id == active_logical_lane_id and candidate.lane_healthy else 1
        owner_priority = candidate.owner_priority if candidate.owner_priority is not None else 2**31 - 1
        return (
            continuity,
            owner_priority,
            -candidate.critical_path_value,
            -candidate.unblock_value,
            candidate.risk_score,
            -candidate.fairness_credit,
            _parse_timestamp(candidate.ready_since),
            _parse_timestamp(candidate.created_at),
            candidate.candidate_id,
        )

    return tuple(sorted(candidates, key=priority))


def _candidates_interact(left: ReleaseCandidate, right: ReleaseCandidate) -> bool:
    dimensions = (
        (left.diff_files, right.diff_files),
        (left.modules, right.modules),
        (left.resources, right.resources),
        (left.databases, right.databases),
        (left.schemas, right.schemas),
        (left.migrations, right.migrations),
        (left.shared_contracts, right.shared_contracts),
    )
    return any(set(first) & set(second) for first, second in dimensions)


def _add_overlap_reason(reasons: set[str], reason: str, left: Sequence[str], right: Sequence[str]) -> None:
    if set(left) & set(right):
        reasons.add(reason)


def _candidate_snapshot(candidate: ReleaseCandidate) -> dict[str, Any]:
    payload = asdict(candidate)
    for name in (
        "resources", "passport_files", "diff_files", "modules", "databases", "schemas",
        "migrations", "shared_contracts", "dependencies",
    ):
        payload[name] = sorted(payload[name])
    return payload


def _binding_snapshot(binding: RevisionBinding) -> dict[str, Any]:
    return {
        "task_id": binding.task_id,
        "task_revision": binding.task_revision,
        "workstream_id": binding.workstream_id,
        "workstream_revision": binding.workstream_revision,
        "pr_head_sha": binding.pr_head_sha,
        "resources": sorted(binding.resources),
    }


def _topological_step_order(decision: ArbiterDecision) -> tuple[str, ...]:
    steps = {step.step_id: step for step in decision.steps}
    remaining = {step_id: set(step.depends_on) for step_id, step in steps.items()}
    ordered: list[str] = []
    while remaining:
        ready = sorted(step_id for step_id, dependencies in remaining.items() if not dependencies)
        if not ready:
            raise StaleArbiterDecision("arbiter decision DAG is cyclic")
        for step_id in ready:
            ordered.append(step_id)
            remaining.pop(step_id)
        for dependencies in remaining.values():
            dependencies.difference_update(ready)
    return tuple(ordered)


def _machine(label: str, value: Any) -> str:
    if (
        not isinstance(value, str) or not value or value != value.strip() or len(value) > 256
        or any(ord(character) < 33 for character in value)
    ):
        raise ReleaseSchedulingError(f"{label} must be a bounded machine value")
    return value


def _unique_values(label: str, values: Sequence[str]) -> tuple[str, ...]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes, bytearray)):
        raise ReleaseSchedulingError(f"{label} must be an array")
    normalized = tuple(_bounded_value(f"{label}[]", value) for value in values)
    if len(set(normalized)) != len(normalized):
        raise ReleaseSchedulingError(f"{label} must not contain duplicates")
    return normalized


def _unique_machine_values(label: str, values: Sequence[str]) -> tuple[str, ...]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes, bytearray)):
        raise ReleaseSchedulingError(f"{label} must be an array")
    normalized = tuple(_machine(f"{label}[]", value) for value in values)
    if len(set(normalized)) != len(normalized):
        raise ReleaseSchedulingError(f"{label} must not contain duplicates")
    return normalized


def _bounded_value(label: str, value: Any) -> str:
    if (
        not isinstance(value, str) or not value or value != value.strip() or len(value) > 1024
        or any(ord(character) < 32 for character in value)
    ):
        raise ReleaseSchedulingError(f"{label} must be a bounded value")
    return value


def _timestamp(label: str, value: str) -> None:
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except (TypeError, ValueError) as exc:
        raise ReleaseSchedulingError(f"{label} must be RFC3339") from exc
    if parsed.tzinfo is None:
        raise ReleaseSchedulingError(f"{label} must include a timezone")


def _parse_timestamp(value: str) -> float:
    parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    return parsed.timestamp()


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
