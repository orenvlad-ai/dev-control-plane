"""Exact retry/successor/arbiter/park policy and strict HumanGate validation."""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
import re
from typing import Any, Mapping, Sequence

from .orchestration_contracts import ArbiterDecision, HUMAN_GATE_REASON_CODES

INCIDENT_ACTIONS = frozenset(
    {
        "retry_current_executor",
        "start_successor_executor",
        "await_successor_proof",
        "invoke_incident_arbiter",
        "await_arbiter_decision",
        "apply_arbiter_decision",
        "verify_arbiter_application",
        "park_workstream",
        "resolved",
    }
)
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


class IncidentPolicyError(ValueError):
    """Incident state transition is malformed or would weaken anti-loop policy."""


class DuplicateBudgetError(IncidentPolicyError):
    """A new retry budget was requested without a material causal change."""


class HumanGateValidationError(IncidentPolicyError):
    """The proposed HumanGate is not strictly human-exclusive."""


@dataclass(frozen=True)
class IncidentContext:
    passport_revision: int
    strategy_digest: str
    causal_evidence_digest: str
    verified_checkpoint_id: str

    def __post_init__(self) -> None:
        if isinstance(self.passport_revision, bool) or not isinstance(self.passport_revision, int) or self.passport_revision < 1:
            raise IncidentPolicyError("passport_revision must be a positive integer")
        for name in ("strategy_digest", "causal_evidence_digest"):
            if not _DIGEST_RE.fullmatch(getattr(self, name)):
                raise IncidentPolicyError(f"{name} must be sha256")
        _machine("verified_checkpoint_id", self.verified_checkpoint_id)


@dataclass(frozen=True)
class CausalFailure:
    fingerprint: str
    stage: str
    error_code: str
    check_id: str
    executor_generation: int
    evidence: Sequence[str]
    fresh_truth_verified: bool

    def __post_init__(self) -> None:
        if not _DIGEST_RE.fullmatch(self.fingerprint):
            raise IncidentPolicyError("failure fingerprint must be sha256")
        for name in ("stage", "error_code", "check_id"):
            _machine(name, getattr(self, name))
        if (
            isinstance(self.executor_generation, bool)
            or not isinstance(self.executor_generation, int)
            or self.executor_generation < 1
        ):
            raise IncidentPolicyError("executor_generation must be positive")
        evidence = _texts("failure.evidence", self.evidence, required=True)
        object.__setattr__(self, "evidence", evidence)
        if not isinstance(self.fresh_truth_verified, bool):
            raise IncidentPolicyError("fresh_truth_verified must be a boolean")


@dataclass(frozen=True)
class IncidentState:
    task_id: str
    workstream_id: str
    fingerprint: str
    context: IncidentContext
    failure_count: int = 0
    current_executor_generation: int = 1
    retry_used: bool = False
    successor_generation: int | None = None
    successor_proof_event_id: str | None = None
    predecessor_stale: bool = False
    incident_case_id: str | None = None
    incident_case_digest: str | None = None
    arbiter_decision_id: str | None = None
    arbiter_applied: bool = False
    independent_verification: str | None = None
    parked: bool = False
    resolved: bool = False

    def __post_init__(self) -> None:
        _machine("task_id", self.task_id)
        _machine("workstream_id", self.workstream_id)
        if not _DIGEST_RE.fullmatch(self.fingerprint):
            raise IncidentPolicyError("incident fingerprint must be sha256")
        if self.failure_count < 0 or self.current_executor_generation < 1:
            raise IncidentPolicyError("invalid failure count or executor generation")
        if self.successor_generation is not None:
            expected_successor = (
                self.current_executor_generation
                if self.successor_proof_event_id is not None
                else self.current_executor_generation + 1
            )
            if self.successor_generation != expected_successor:
                raise IncidentPolicyError("successor must be exactly one generation after its predecessor")
        if self.predecessor_stale and not self.successor_proof_event_id:
            raise IncidentPolicyError("predecessor cannot become stale before successor proof")
        if self.incident_case_id is None and self.incident_case_digest is not None:
            raise IncidentPolicyError("incident digest requires an incident case id")
        if self.incident_case_digest is not None and not _DIGEST_RE.fullmatch(self.incident_case_digest):
            raise IncidentPolicyError("incident case digest must be sha256")
        if self.arbiter_decision_id is not None and self.incident_case_id is None:
            raise IncidentPolicyError("arbiter decision requires an incident case")
        if self.arbiter_applied and self.arbiter_decision_id is None:
            raise IncidentPolicyError("arbiter cannot be applied before its single decision")
        if self.independent_verification not in {None, "passed", "failed"}:
            raise IncidentPolicyError("invalid independent verification state")
        if self.parked and self.independent_verification != "failed":
            raise IncidentPolicyError("parking after arbiter requires failed independent verification")
        if self.resolved and self.independent_verification != "passed":
            raise IncidentPolicyError("resolution requires passed independent verification")
        if self.parked and self.resolved:
            raise IncidentPolicyError("an incident cannot be both parked and resolved")


@dataclass(frozen=True)
class IncidentTransition:
    state: IncidentState
    action: str
    detail: str

    def __post_init__(self) -> None:
        if self.action not in INCIDENT_ACTIONS:
            raise IncidentPolicyError(f"unknown incident action: {self.action!r}")


@dataclass(frozen=True)
class HumanGateRequest:
    gate_id: str
    task_id: str
    workstream_id: str
    reason_code: str
    requested_actions: Sequence[str]
    human_exclusive: bool
    already_authorized_by_passport: bool
    independent_safe_work_complete: bool
    repo_owned_remediation_exhausted: bool
    evidence: Sequence[str]

    def __post_init__(self) -> None:
        for name in ("gate_id", "task_id", "workstream_id"):
            _machine(name, getattr(self, name))
        if self.reason_code not in HUMAN_GATE_REASON_CODES:
            raise HumanGateValidationError(f"reason is outside the closed HumanGate allowlist: {self.reason_code!r}")
        actions = _texts("requested_actions", self.requested_actions, required=True)
        if len(actions) != 1:
            raise HumanGateValidationError("HumanGate must request exactly one minimal action")
        if "\n" in actions[0] or len(actions[0]) > 512:
            raise HumanGateValidationError("HumanGate action must be one bounded line")
        object.__setattr__(self, "requested_actions", actions)
        object.__setattr__(self, "evidence", _texts("human_gate.evidence", self.evidence, required=True))


def build_causal_fingerprint(
    *,
    stage: str,
    error_code: str,
    check_id: str,
    target_id: str,
    normalized_cause_code: str,
) -> str:
    """Build a stable fingerprint from typed causes, never arbitrary model prose."""

    payload = {}
    for name, value in (
        ("stage", stage),
        ("error_code", error_code),
        ("check_id", check_id),
        ("target_id", target_id),
        ("normalized_cause_code", normalized_cause_code),
    ):
        payload[name] = _machine(name, value)
    return _digest(payload)


def begin_incident_budget(
    *,
    task_id: str,
    workstream_id: str,
    failure: CausalFailure,
    context: IncidentContext,
) -> IncidentTransition:
    if not failure.fresh_truth_verified:
        raise IncidentPolicyError("first retry requires fresh deterministic truth evidence")
    state = IncidentState(
        task_id=task_id,
        workstream_id=workstream_id,
        fingerprint=failure.fingerprint,
        context=context,
        failure_count=1,
        current_executor_generation=failure.executor_generation,
        retry_used=True,
    )
    return IncidentTransition(state, "retry_current_executor", "first occurrence: one bounded retry")


def observe_same_failure(state: IncidentState, failure: CausalFailure) -> IncidentTransition:
    """Advance the exact anti-loop sequence for the same causal fingerprint."""

    if failure.fingerprint != state.fingerprint:
        raise IncidentPolicyError("different causal fingerprint requires an explicit new incident budget")
    if not failure.fresh_truth_verified:
        raise IncidentPolicyError("same causal occurrence requires refreshed deterministic truth evidence")
    if state.resolved:
        return IncidentTransition(state, "resolved", "incident already resolved")
    if state.parked:
        return IncidentTransition(state, "park_workstream", "same causal failure remains parked")
    if failure.executor_generation < state.current_executor_generation:
        raise IncidentPolicyError("late predecessor failure is stale evidence")

    if state.arbiter_applied:
        parked = replace(
            state,
            failure_count=state.failure_count + 1,
            independent_verification="failed",
            parked=True,
        )
        return IncidentTransition(
            parked,
            "park_workstream",
            "same failure after the one arbiter application: no fourth retry or second arbiter",
        )

    if state.incident_case_id is not None:
        action = "apply_arbiter_decision" if state.arbiter_decision_id else "await_arbiter_decision"
        return IncidentTransition(state, action, "the single incident arbiter path is already reserved")

    if state.successor_generation is not None and state.successor_proof_event_id is None:
        return IncidentTransition(
            state,
            "await_successor_proof",
            "predecessor remains current until the one successor proves startup from checkpoint",
        )

    if not state.retry_used:
        retried = replace(state, failure_count=state.failure_count + 1, retry_used=True)
        return IncidentTransition(retried, "retry_current_executor", "one bounded current-executor retry")

    if state.successor_generation is None:
        successor_generation = state.current_executor_generation + 1
        successor = replace(
            state,
            failure_count=state.failure_count + 1,
            successor_generation=successor_generation,
        )
        return IncidentTransition(
            successor,
            "start_successor_executor",
            "second occurrence: create exactly one successor from verified checkpoint",
        )

    if not state.predecessor_stale:
        raise IncidentPolicyError("successor proof invariant is inconsistent")
    if failure.executor_generation != state.current_executor_generation:
        raise IncidentPolicyError("third failure must be observed from the proven successor generation")
    case_id, case_digest = _incident_case(state, failure)
    incident = replace(
        state,
        failure_count=state.failure_count + 1,
        incident_case_id=case_id,
        incident_case_digest=case_digest,
    )
    return IncidentTransition(
        incident,
        "invoke_incident_arbiter",
        "third occurrence: create one incident and invoke one fresh schema-bound arbiter",
    )


def escalate_failed_successor(
    state: IncidentState,
    failure: CausalFailure,
    *,
    occurrence_already_counted: bool = False,
) -> IncidentTransition:
    """Escalate when the one permitted successor cannot prove startup.

    A successor-start worker is itself the already-reserved successor.  It may
    never answer a failure by creating another executor.  The original causal
    root reaches its third occurrence immediately; a materially changed cause
    receives its one bounded retry first and then takes the same single-arbiter
    path because a second successor would be unsafe.
    """

    if failure.fingerprint != state.fingerprint:
        raise IncidentPolicyError("failed successor escalation fingerprint changed")
    if not failure.fresh_truth_verified:
        raise IncidentPolicyError("failed successor escalation requires fresh truth")
    if state.resolved:
        return IncidentTransition(state, "resolved", "incident already resolved")
    if state.parked:
        return IncidentTransition(state, "park_workstream", "same causal failure remains parked")
    if state.arbiter_applied or state.incident_case_id is not None:
        return observe_same_failure(state, failure)
    case_base = (
        replace(state, failure_count=state.failure_count - 1)
        if occurrence_already_counted
        else state
    )
    case_id, case_digest = _incident_case(case_base, failure)
    incident = replace(
        state,
        failure_count=(
            state.failure_count
            if occurrence_already_counted
            else state.failure_count + 1
        ),
        incident_case_id=case_id,
        incident_case_digest=case_digest,
    )
    return IncidentTransition(
        incident,
        "invoke_incident_arbiter",
        "the one reserved successor failed: forbid a second successor and invoke one arbiter",
    )


def record_successor_proof(
    state: IncidentState,
    *,
    successor_generation: int,
    proof_event_id: str,
) -> IncidentState:
    if state.successor_generation is None or state.successor_generation != successor_generation:
        raise IncidentPolicyError("successor proof does not match the one reserved successor")
    if state.successor_proof_event_id is not None:
        if state.successor_proof_event_id == proof_event_id:
            return state
        raise IncidentPolicyError("successor proof may be recorded only once")
    proof = _machine("proof_event_id", proof_event_id)
    return replace(
        state,
        current_executor_generation=successor_generation,
        successor_proof_event_id=proof,
        predecessor_stale=True,
    )


def record_incident_arbiter_decision(state: IncidentState, decision: ArbiterDecision) -> IncidentState:
    if state.incident_case_id is None or state.incident_case_digest is None:
        raise IncidentPolicyError("incident has not reached its third occurrence")
    if decision.kind != "incident":
        raise IncidentPolicyError("release arbiter answer cannot resolve an incident")
    if decision.case_id != state.incident_case_id or decision.case_digest != state.incident_case_digest:
        raise IncidentPolicyError("incident arbiter decision has stale immutable binding")
    if state.arbiter_decision_id is not None:
        if state.arbiter_decision_id == decision.decision_id:
            return state
        raise IncidentPolicyError("a second incident arbiter decision is forbidden")
    return replace(state, arbiter_decision_id=decision.decision_id)


def record_arbiter_application(state: IncidentState, *, decision_id: str) -> IncidentTransition:
    if state.arbiter_decision_id != decision_id:
        raise IncidentPolicyError("only the recorded arbiter decision may be applied")
    if state.arbiter_applied:
        raise IncidentPolicyError("arbiter decision may be applied only once")
    applied = replace(state, arbiter_applied=True)
    return IncidentTransition(
        applied,
        "verify_arbiter_application",
        "arbiter decision applied once; independent verification is mandatory",
    )


def record_independent_verification(state: IncidentState, *, passed: bool) -> IncidentTransition:
    if not state.arbiter_applied:
        raise IncidentPolicyError("independent verification requires an applied arbiter decision")
    if state.independent_verification is not None:
        raise IncidentPolicyError("independent verification may be recorded only once")
    if passed:
        resolved = replace(state, independent_verification="passed", resolved=True)
        return IncidentTransition(resolved, "resolved", "independent verification passed")
    parked = replace(state, independent_verification="failed", parked=True)
    return IncidentTransition(
        parked,
        "park_workstream",
        "independent verification failed: park and create exact serious-stall attention",
    )


def renew_incident_budget(
    state: IncidentState,
    *,
    new_fingerprint: str,
    new_context: IncidentContext,
    justification: str,
) -> IncidentState:
    """Create a blank budget only after a real Passport/strategy/causal change."""

    if not _DIGEST_RE.fullmatch(new_fingerprint):
        raise IncidentPolicyError("new_fingerprint must be sha256")
    _text("justification", justification)
    materially_changed = (
        new_fingerprint != state.fingerprint
        or new_context.passport_revision != state.context.passport_revision
        or new_context.strategy_digest != state.context.strategy_digest
        or new_context.causal_evidence_digest != state.context.causal_evidence_digest
    )
    if not materially_changed:
        raise DuplicateBudgetError("new retry budget requires changed Passport, strategy or causal evidence")
    return IncidentState(
        task_id=state.task_id,
        workstream_id=state.workstream_id,
        fingerprint=new_fingerprint,
        context=new_context,
        current_executor_generation=state.current_executor_generation,
    )


def validate_human_gate(request: HumanGateRequest) -> HumanGateRequest:
    failures: list[str] = []
    if not request.human_exclusive:
        failures.append("next action is not proven human-exclusive")
    if request.already_authorized_by_passport:
        failures.append("Passport already authorizes the action")
    if not request.independent_safe_work_complete:
        failures.append("independent safe work is incomplete")
    if not request.repo_owned_remediation_exhausted:
        failures.append("repo-owned remediation is not exhausted")
    if failures:
        raise HumanGateValidationError("; ".join(failures))
    return request


def _incident_case(state: IncidentState, failure: CausalFailure) -> tuple[str, str]:
    snapshot = {
        "kind": "INCIDENT",
        "task_id": state.task_id,
        "workstream_id": state.workstream_id,
        "fingerprint": state.fingerprint,
        "failure_count": state.failure_count + 1,
        "passport_revision": state.context.passport_revision,
        "strategy_digest": state.context.strategy_digest,
        "causal_evidence_digest": state.context.causal_evidence_digest,
        "verified_checkpoint_id": state.context.verified_checkpoint_id,
        "executor_generation": failure.executor_generation,
    }
    digest = _digest(snapshot)
    return f"incident:{digest[:24]}", digest


def _digest(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _machine(label: str, value: Any) -> str:
    if (
        not isinstance(value, str) or not value or value != value.strip() or len(value) > 256
        or any(ord(character) < 33 for character in value)
    ):
        raise IncidentPolicyError(f"{label} must be a bounded machine value")
    return value


def _text(label: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 4096:
        raise IncidentPolicyError(f"{label} must be bounded non-empty text")
    return value.strip()


def _texts(label: str, values: Sequence[str], *, required: bool = False) -> tuple[str, ...]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes, bytearray)):
        raise IncidentPolicyError(f"{label} must be an array")
    normalized = tuple(_text(f"{label}[]", value) for value in values)
    if required and not normalized:
        raise IncidentPolicyError(f"{label} must not be empty")
    if len(set(normalized)) != len(normalized):
        raise IncidentPolicyError(f"{label} must not contain duplicates")
    return normalized
