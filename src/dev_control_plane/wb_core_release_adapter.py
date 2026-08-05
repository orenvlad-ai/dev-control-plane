"""Bounded local adapter for the external ``orenvlad-ai/wb-core`` Release Train.

The adapter is intentionally not a second release actuator.  It may publish
only the existing trusted-main orchestration admission command and, after an
independently authorized task-level closure, the existing idempotent logical
lane-release command.  It otherwise reads GitHub-owned labels and Actions-owned
proof comments.  Merge, deploy, verify, rollback, LOOP acknowledgement and UI
acceptance remain exclusively inside the target repository's Release Train.

All network/process waits are supplied by a small typed API.  The production
API can use the target's exact ``origin/main`` ``queue-status`` runner plus the
allowlisted GitHub client below; deterministic smokes use a fake API.  Raw
provider payloads and comment bodies never cross the typed boundary.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import re
import subprocess
import time
from typing import Any, Protocol


WB_CORE_REPOSITORY = "orenvlad-ai/wb-core"
WB_CORE_BASE_REF = "main"
WB_CORE_TARGET_ID = WB_CORE_REPOSITORY
WB_CORE_TARGET_ADAPTER = "wb-core-github-release-train-v2"
WB_CORE_PRODUCTION_TARGET = "wb_core_eu_hosted_runtime_active"
WB_CORE_PRODUCTION_DOMAIN = "api.selleros.pro"
WB_CORE_ADMISSION_MARKER = "wb-core-orchestration-admission-proof"
WB_CORE_COMPLETION_MARKER = "wb-core-release-completion-proof"
WB_CORE_RECONCILE_MARKER = "wb-core-release-reconcile-proof"

WB_CORE_REQUEST_SCHEMA = "dev-control-plane/wb-core-release-request/v2"
WB_CORE_OUTCOME_SCHEMA = "dev-control-plane/wb-core-release-outcome/v2"
WB_CORE_RUNTIME_OBSERVATION_SCHEMA = "dev-control-plane/release-action-observation/v2"
WB_CORE_ADMISSION_BINDING_SCHEMA = (
    "dev-control-plane/wb-core-admission-binding/v2"
)
WB_CORE_LANE_RELEASE_REQUEST_SCHEMA = (
    "dev-control-plane/wb-core-lane-release-request/v2"
)
WB_CORE_LANE_RELEASE_OUTCOME_SCHEMA = (
    "dev-control-plane/wb-core-lane-release-outcome/v2"
)

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_TARGET_TASK_RE = re.compile(r"^[a-z0-9][a-z0-9-]{7,63}$")
_MACHINE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}$")
_PR_URL_RE = re.compile(r"^https://github\.com/orenvlad-ai/wb-core/pull/[1-9][0-9]*$")
_PR_IDENTITY_RE = re.compile(
    r"^github-pr-v1:orenvlad-ai/wb-core:"
    r"(?P<number>[1-9][0-9]*):(?P<head>[0-9a-f]{40}):(?P<merge>[0-9a-f]{40})$"
)
_WB_CORE_DEPLOY_IDENTITY_RE = re.compile(
    r"^hosted-release-v1:wb_core_eu_hosted_runtime_active:api\.selleros\.pro:"
    r"(?P<release>[0-9a-f]{40})$"
)

_TASK_LABELS = frozenset({"task:standard", "task:loop"})
_SCOPE_LABELS = frozenset(
    {"scope:repo-only", "scope:live-runtime", "scope:production-mutation"}
)
_TERMINAL_LABELS = frozenset(
    {"release:done", "release:production", "release:superseded", "release:retired"}
)
_QUEUE_STATUSES = frozenset(
    {
        "idle",
        "halted",
        "gate-conflict",
        "awaiting-agent",
        "awaiting-ui",
        "finance-deploy-lease",
        "running",
        "ready",
    }
)
_LANE_STATUSES = frozenset({"idle", "owned", "conflict"})
_OUTCOME_STATUSES = frozenset(
    {
        "admission_submitted",
        "admitted",
        "waiting_foreign_lane",
        "waiting_release",
        "readmission_required",
        "terminal",
        "failed",
    }
)
_LANE_RELEASE_STATUSES = frozenset(
    {"release_submitted", "released", "stale", "failed"}
)
_ALLOWED_INTEGRITY_SIGNALS = frozenset({"terminal-release-lane-owner"})
_COMMAND_ASSOCIATIONS = frozenset({"OWNER", "MEMBER"})
_BOT_LOGINS = frozenset({"github-actions", "github-actions[bot]"})
_MAX_PROVIDER_OUTPUT_BYTES = 16_000_000


class WbCoreReleaseAdapterError(RuntimeError):
    """A sanitized target transport or typed-boundary failure."""


@dataclass(frozen=True)
class WbCoreReleaseRequest:
    """Immutable local binding for one target PR release observation."""

    candidate_id: str
    task_id: str
    target_task_id: str
    workstream_id: str
    task_revision: int
    workstream_revision: int
    passport_digest: str
    pr_number: int
    expected_head_sha: str
    contour: str
    admission_binding: WbCoreAdmissionBinding | None = None
    expected_merge_sha: str | None = None
    target_id: str = WB_CORE_TARGET_ID
    schema: str = WB_CORE_REQUEST_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != WB_CORE_REQUEST_SCHEMA:
            raise ValueError("wb-core release request schema mismatch")
        if self.target_id != WB_CORE_TARGET_ID:
            raise ValueError("wb-core release request target mismatch")
        _machine("candidate_id", self.candidate_id)
        _machine("task_id", self.task_id)
        _machine("workstream_id", self.workstream_id)
        if self.target_task_id != derive_wb_core_target_task_id(self.task_id):
            raise ValueError("wb-core target task bridge is not the deterministic local-task binding")
        for name in ("task_revision", "workstream_revision", "pr_number"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if not _DIGEST_RE.fullmatch(self.passport_digest):
            raise ValueError("passport_digest must be a lowercase sha256")
        if not _SHA_RE.fullmatch(self.expected_head_sha):
            raise ValueError("expected_head_sha must be an exact lowercase Git SHA")
        if self.expected_merge_sha is not None and not _SHA_RE.fullmatch(self.expected_merge_sha):
            raise ValueError("expected_merge_sha must be an exact lowercase Git SHA or null")
        if self.contour not in {"release:done", "release:production"}:
            raise ValueError("wb-core adapter supports only release:done/release:production")
        if self.admission_binding is not None:
            binding = self.admission_binding
            if not isinstance(binding, WbCoreAdmissionBinding):
                raise ValueError("admission_binding must be typed or null")
            if (
                self.expected_merge_sha is None
                or binding.pr_number != self.pr_number
                or binding.head_sha != self.expected_head_sha
                or binding.target_task_id != self.target_task_id
                or binding.task_revision > self.task_revision
            ):
                raise ValueError("terminal admission binding is stale or cross-bound")

    @property
    def expected_scope_label(self) -> str:
        return "scope:repo-only" if self.contour == "release:done" else "scope:live-runtime"

    @property
    def expected_terminal_label(self) -> str:
        return "release:done" if self.contour == "release:done" else "release:production"

    @property
    def expected_completion_contour(self) -> str:
        return "repo-only" if self.contour == "release:done" else "production-verified"

    def admission_command(self) -> str:
        return (
            f"/wb-core orchestration admit {self.pr_number} "
            f"head {self.expected_head_sha} task {self.target_task_id} "
            f"revision {self.task_revision} passport sha256:{self.passport_digest}"
        )

    def admission_command_digest(self) -> str:
        return _sha256_text(self.admission_command())


@dataclass(frozen=True)
class WbCoreAdmissionProof:
    """One Actions-owned exact-head admission marker."""

    pr_number: int
    owner_pr: int
    head_sha: str
    target_task_id: str
    task_revision: int
    passport_digest: str

    def __post_init__(self) -> None:
        for name in ("pr_number", "owner_pr", "task_revision"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"admission proof {name} must be positive")
        if not _SHA_RE.fullmatch(self.head_sha):
            raise ValueError("admission proof head is invalid")
        if not _TARGET_TASK_RE.fullmatch(self.target_task_id):
            raise ValueError("admission proof task is invalid")
        if not _DIGEST_RE.fullmatch(self.passport_digest):
            raise ValueError("admission proof passport is invalid")

    def binding(self) -> tuple[Any, ...]:
        return (
            self.pr_number,
            self.owner_pr,
            self.head_sha,
            self.target_task_id,
            self.task_revision,
            self.passport_digest,
        )

    def digest(self) -> str:
        return _sha256_json(asdict(self))


@dataclass(frozen=True)
class WbCoreAdmissionBinding:
    """Durable immutable admission proof preserved across Passport revisions."""

    target_id: str
    pr_number: int
    owner_pr: int
    head_sha: str
    target_task_id: str
    task_revision: int
    passport_digest: str
    proof_digest: str
    schema: str = WB_CORE_ADMISSION_BINDING_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != WB_CORE_ADMISSION_BINDING_SCHEMA:
            raise ValueError("wb-core admission binding schema mismatch")
        if self.target_id != WB_CORE_TARGET_ID:
            raise ValueError("wb-core admission binding target mismatch")
        proof = WbCoreAdmissionProof(
            pr_number=self.pr_number,
            owner_pr=self.owner_pr,
            head_sha=self.head_sha,
            target_task_id=self.target_task_id,
            task_revision=self.task_revision,
            passport_digest=self.passport_digest,
        )
        if self.proof_digest != proof.digest():
            raise ValueError("wb-core admission binding proof digest mismatch")

    @classmethod
    def from_proof(cls, proof: WbCoreAdmissionProof) -> "WbCoreAdmissionBinding":
        if not isinstance(proof, WbCoreAdmissionProof):
            raise ValueError("wb-core admission binding requires a typed target proof")
        return cls(
            target_id=WB_CORE_TARGET_ID,
            pr_number=proof.pr_number,
            owner_pr=proof.owner_pr,
            head_sha=proof.head_sha,
            target_task_id=proof.target_task_id,
            task_revision=proof.task_revision,
            passport_digest=proof.passport_digest,
            proof_digest=proof.digest(),
        )

    def proof(self) -> WbCoreAdmissionProof:
        return WbCoreAdmissionProof(
            pr_number=self.pr_number,
            owner_pr=self.owner_pr,
            head_sha=self.head_sha,
            target_task_id=self.target_task_id,
            task_revision=self.task_revision,
            passport_digest=self.passport_digest,
        )


@dataclass(frozen=True)
class WbCoreTerminalProof:
    """One Actions-owned STANDARD terminal marker."""

    pr_number: int
    merge_sha: str
    contour: str
    marker: str = WB_CORE_COMPLETION_MARKER

    def __post_init__(self) -> None:
        if isinstance(self.pr_number, bool) or not isinstance(self.pr_number, int) or self.pr_number < 1:
            raise ValueError("terminal proof PR number must be positive")
        if not _SHA_RE.fullmatch(self.merge_sha):
            raise ValueError("terminal proof merge SHA is invalid")
        if self.contour not in {"repo-only", "production-verified"}:
            raise ValueError("terminal proof contour is invalid")
        if self.marker not in {WB_CORE_COMPLETION_MARKER, WB_CORE_RECONCILE_MARKER}:
            raise ValueError("terminal proof marker is not allowlisted")
        if self.marker == WB_CORE_RECONCILE_MARKER and self.contour != "production-verified":
            raise ValueError("reconcile proof can attest only production-verified")

    def digest(self) -> str:
        return _sha256_json(asdict(self))


@dataclass(frozen=True)
class WbCoreCommandReceipt:
    """Sanitized GitHub issue-comment transport receipt."""

    command_digest: str
    comment_id: int
    created_at: str

    def __post_init__(self) -> None:
        if not _DIGEST_RE.fullmatch(self.command_digest):
            raise ValueError("command receipt digest is invalid")
        if isinstance(self.comment_id, bool) or not isinstance(self.comment_id, int) or self.comment_id < 1:
            raise ValueError("command receipt comment id must be positive")
        if not isinstance(self.created_at, str) or not self.created_at or len(self.created_at) > 100:
            raise ValueError("command receipt timestamp is invalid")
        _rfc3339(self.created_at)


@dataclass(frozen=True)
class WbCoreLaneReleaseRequest:
    """Task-level authorization to release one exact target logical lane.

    ``closure_event_id`` and ``evidence_digest`` bind the request to durable
    local closure truth.  The required adapter authorization callback must
    independently prove that this is either task-level contour closure or the
    one parked serious-stall outcome; a terminal PR alone is insufficient.
    """

    closure_event_id: str
    task_id: str
    target_task_id: str
    task_revision: int
    anchor_pr: int
    outcome: str
    evidence_digest: str
    target_id: str = WB_CORE_TARGET_ID
    schema: str = WB_CORE_LANE_RELEASE_REQUEST_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != WB_CORE_LANE_RELEASE_REQUEST_SCHEMA:
            raise ValueError("wb-core lane-release request schema mismatch")
        if self.target_id != WB_CORE_TARGET_ID:
            raise ValueError("wb-core lane-release target mismatch")
        _machine("closure_event_id", self.closure_event_id)
        _machine("task_id", self.task_id)
        if self.target_task_id != derive_wb_core_target_task_id(self.task_id):
            raise ValueError("wb-core lane-release target task bridge is invalid")
        for name in ("task_revision", "anchor_pr"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"lane-release {name} must be positive")
        if self.outcome not in {"completed", "parked"}:
            raise ValueError("lane-release outcome must be completed or parked")
        if not _DIGEST_RE.fullmatch(self.evidence_digest):
            raise ValueError("lane-release evidence must be a lowercase sha256")

    def release_command(self) -> str:
        return (
            f"/wb-core orchestration release-lane {self.anchor_pr} "
            f"task {self.target_task_id} revision {self.task_revision} "
            f"outcome {self.outcome} evidence sha256:{self.evidence_digest}"
        )

    def release_command_digest(self) -> str:
        return _sha256_text(self.release_command())


@dataclass(frozen=True)
class WbCoreLaneReleaseProof:
    """Actions-owned proof emitted by the target lane-release handler."""

    owner_pr: int
    target_task_id: str
    task_revision: int
    outcome: str
    evidence_digest: str

    def __post_init__(self) -> None:
        for name in ("owner_pr", "task_revision"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"lane-release proof {name} must be positive")
        if not _TARGET_TASK_RE.fullmatch(self.target_task_id):
            raise ValueError("lane-release proof task is invalid")
        if self.outcome not in {"completed", "parked"}:
            raise ValueError("lane-release proof outcome is invalid")
        if not _DIGEST_RE.fullmatch(self.evidence_digest):
            raise ValueError("lane-release proof evidence is invalid")

    def binding(self) -> tuple[Any, ...]:
        return (
            self.owner_pr,
            self.target_task_id,
            self.task_revision,
            self.outcome,
            self.evidence_digest,
        )

    def digest(self) -> str:
        return _sha256_json(asdict(self))


@dataclass(frozen=True)
class WbCorePullReadback:
    """Sanitized PR, admission and terminal truth from GitHub."""

    number: int
    state: str
    is_draft: bool
    head_sha: str
    base_ref: str
    labels: Sequence[str]
    url: str
    merge_sha: str | None = None
    admission_proofs: Sequence[WbCoreAdmissionProof] = field(default_factory=tuple)
    terminal_proofs: Sequence[WbCoreTerminalProof] = field(default_factory=tuple)
    submitted_command_digests: Sequence[str] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if isinstance(self.number, bool) or not isinstance(self.number, int) or self.number < 1:
            raise ValueError("PR number must be positive")
        normalized_state = str(self.state).upper()
        if normalized_state not in {"OPEN", "MERGED", "CLOSED"}:
            raise ValueError("PR state is invalid")
        object.__setattr__(self, "state", normalized_state)
        if not isinstance(self.is_draft, bool):
            raise ValueError("PR draft state must be boolean")
        if not _SHA_RE.fullmatch(self.head_sha):
            raise ValueError("PR head SHA is invalid")
        if self.base_ref != WB_CORE_BASE_REF:
            raise ValueError("PR base is not main")
        labels = _stable_strings("labels", self.labels, maximum=256)
        object.__setattr__(self, "labels", labels)
        if not _PR_URL_RE.fullmatch(self.url) or not self.url.endswith(f"/{self.number}"):
            raise ValueError("PR URL is invalid")
        if self.merge_sha is not None and not _SHA_RE.fullmatch(self.merge_sha):
            raise ValueError("PR merge SHA is invalid")
        if (self.state == "MERGED") != (self.merge_sha is not None):
            raise ValueError("PR state and merge identity are inconsistent")
        admissions = tuple(self.admission_proofs)
        terminals = tuple(self.terminal_proofs)
        if any(not isinstance(item, WbCoreAdmissionProof) for item in admissions):
            raise ValueError("PR admission proof boundary is untyped")
        if any(not isinstance(item, WbCoreTerminalProof) for item in terminals):
            raise ValueError("PR terminal proof boundary is untyped")
        if any(item.pr_number != self.number for item in admissions + terminals):
            raise ValueError("PR proof belongs to another pull request")
        commands = _stable_strings(
            "submitted_command_digests", self.submitted_command_digests, maximum=2_000
        )
        if any(not _DIGEST_RE.fullmatch(item) for item in commands):
            raise ValueError("submitted command digest is invalid")
        object.__setattr__(self, "admission_proofs", admissions)
        object.__setattr__(self, "terminal_proofs", terminals)
        object.__setattr__(self, "submitted_command_digests", commands)


@dataclass(frozen=True)
class WbCoreQueueReadback:
    """Typed subset of target ``github_release_train.py queue-status``."""

    queue_status: str
    lane_status: str
    integrity_status: str
    lane_owner_pr: int | None = None
    lane_task_id: str | None = None
    lane_revision: int | None = None
    integrity_signals: Sequence[str] = field(default_factory=tuple)
    active_prs: Sequence[int] = field(default_factory=tuple)
    release_proofs: Sequence[WbCoreLaneReleaseProof] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.queue_status not in _QUEUE_STATUSES:
            raise ValueError("target queue status is unknown")
        if self.lane_status not in _LANE_STATUSES:
            raise ValueError("target release lane status is unknown")
        if self.integrity_status not in {"ok", "attention"}:
            raise ValueError("target queue integrity status is unknown")
        if self.lane_status == "owned":
            if (
                isinstance(self.lane_owner_pr, bool)
                or not isinstance(self.lane_owner_pr, int)
                or self.lane_owner_pr < 1
                or not isinstance(self.lane_task_id, str)
                or not _TARGET_TASK_RE.fullmatch(self.lane_task_id)
                or isinstance(self.lane_revision, bool)
                or not isinstance(self.lane_revision, int)
                or self.lane_revision < 1
            ):
                raise ValueError("owned target release lane identity is incomplete")
        elif any(value is not None for value in (self.lane_owner_pr, self.lane_task_id, self.lane_revision)):
            raise ValueError("non-owned target release lane cannot carry an owner identity")
        signals = _stable_strings("integrity_signals", self.integrity_signals, maximum=32)
        if not set(signals).issubset(_ALLOWED_INTEGRITY_SIGNALS):
            raise ValueError("target queue returned an unknown integrity signal")
        if (self.integrity_status == "attention") != bool(signals):
            raise ValueError("target queue integrity signal state is inconsistent")
        active: list[int] = []
        for value in self.active_prs:
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError("target queue active PR identity is invalid")
            if value not in active:
                active.append(value)
            if len(active) > 3_000:
                raise ValueError("target queue active PR readback is oversized")
        if self.lane_status == "owned" and self.lane_owner_pr not in active:
            raise ValueError("target release lane owner is absent from active readback")
        proofs = tuple(self.release_proofs)
        if any(not isinstance(item, WbCoreLaneReleaseProof) for item in proofs):
            raise ValueError("target lane-release proof boundary is untyped")
        if len({item.owner_pr for item in proofs}) != len(proofs):
            raise ValueError("target lane-release proof owner is duplicated")
        if len(proofs) > 32:
            raise ValueError("target lane-release proof readback is oversized")
        object.__setattr__(self, "integrity_signals", signals)
        object.__setattr__(self, "active_prs", tuple(active))
        object.__setattr__(self, "release_proofs", proofs)

    @classmethod
    def from_target_snapshot(
        cls,
        payload: Mapping[str, Any],
        *,
        expected_release_proof_prs: Sequence[int] = (),
    ) -> "WbCoreQueueReadback":
        """Parse the canonical target readback without retaining raw payloads."""

        if not isinstance(payload, Mapping) or payload.get("status") != "ok":
            raise WbCoreReleaseAdapterError("target_queue_readback_invalid")
        queue = payload.get("queue")
        lane = payload.get("release_lane")
        integrity = payload.get("integrity")
        active = payload.get("active")
        proofs_raw = payload.get("release_lane_proofs")
        if not all(isinstance(item, Mapping) for item in (queue, lane, integrity)):
            raise WbCoreReleaseAdapterError("target_queue_readback_invalid")
        if not isinstance(active, Sequence) or isinstance(active, (str, bytes, bytearray)):
            raise WbCoreReleaseAdapterError("target_queue_readback_invalid")
        if not isinstance(proofs_raw, Sequence) or isinstance(
            proofs_raw, (str, bytes, bytearray)
        ):
            raise WbCoreReleaseAdapterError("target_queue_readback_invalid")
        expected_proof_prs: set[int] = set()
        for value in expected_release_proof_prs:
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise WbCoreReleaseAdapterError("target_queue_readback_invalid")
            expected_proof_prs.add(value)
        lane_status = str(lane.get("status") or "")
        signals_raw = integrity.get("signals")
        if not isinstance(signals_raw, Sequence) or isinstance(signals_raw, (str, bytes, bytearray)):
            raise WbCoreReleaseAdapterError("target_queue_readback_invalid")
        signals: list[str] = []
        for item in signals_raw:
            if not isinstance(item, Mapping) or not isinstance(item.get("code"), str):
                raise WbCoreReleaseAdapterError("target_queue_readback_invalid")
            signals.append(str(item["code"]))
        active_prs: list[int] = []
        for item in active:
            if not isinstance(item, Mapping):
                raise WbCoreReleaseAdapterError("target_queue_readback_invalid")
            number = item.get("pr")
            if isinstance(number, bool) or not isinstance(number, int) or number < 1:
                raise WbCoreReleaseAdapterError("target_queue_readback_invalid")
            active_prs.append(number)
        release_proofs: list[WbCoreLaneReleaseProof] = []
        for item in proofs_raw:
            if not isinstance(item, Mapping) or set(item) != {
                "owner_pr",
                "task_id",
                "revision",
                "outcome",
                "evidence_digest",
            }:
                raise WbCoreReleaseAdapterError("target_queue_readback_invalid")
            owner_pr = item.get("owner_pr")
            revision = item.get("revision")
            if (
                isinstance(owner_pr, bool)
                or not isinstance(owner_pr, int)
                or owner_pr not in expected_proof_prs
                or isinstance(revision, bool)
                or not isinstance(revision, int)
                or not isinstance(item.get("task_id"), str)
                or not isinstance(item.get("outcome"), str)
                or not isinstance(item.get("evidence_digest"), str)
            ):
                raise WbCoreReleaseAdapterError("target_queue_readback_invalid")
            try:
                release_proofs.append(
                    WbCoreLaneReleaseProof(
                        owner_pr=owner_pr,
                        target_task_id=str(item["task_id"]),
                        task_revision=revision,
                        outcome=str(item["outcome"]),
                        evidence_digest=_prefixed_digest(item["evidence_digest"]),
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise WbCoreReleaseAdapterError("target_queue_readback_invalid") from exc
        try:
            if lane_status == "owned":
                owner_pr_raw = lane.get("owner_pr")
                revision_raw = lane.get("revision")
                task_id_raw = lane.get("task_id")
                if (
                    isinstance(owner_pr_raw, bool)
                    or not isinstance(owner_pr_raw, int)
                    or isinstance(revision_raw, bool)
                    or not isinstance(revision_raw, int)
                    or not isinstance(task_id_raw, str)
                ):
                    raise ValueError("lane identity")
            return cls(
                queue_status=str(queue.get("status") or ""),
                lane_status=lane_status,
                integrity_status=str(integrity.get("status") or ""),
                lane_owner_pr=(lane["owner_pr"] if lane_status == "owned" else None),
                lane_task_id=(lane["task_id"] if lane_status == "owned" else None),
                lane_revision=(lane["revision"] if lane_status == "owned" else None),
                integrity_signals=tuple(signals),
                active_prs=tuple(active_prs),
                release_proofs=tuple(release_proofs),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise WbCoreReleaseAdapterError("target_queue_readback_invalid") from exc


@dataclass(frozen=True)
class WbCoreReleaseOutcome:
    """One bounded, non-secret adapter observation for durable runtime handling."""

    status: str
    reason_code: str
    candidate_id: str
    task_id: str
    target_task_id: str
    workstream_id: str
    task_revision: int
    workstream_revision: int
    pr_number: int
    expected_head_sha: str
    observed_head_sha: str
    contour: str
    command_digest: str
    pr_url: str
    admission_binding: WbCoreAdmissionBinding | None = None
    merge_sha: str | None = None
    terminal_label: str | None = None
    terminal_proof_digest: str | None = None
    command_comment_id: int | None = None
    next_poll_after_seconds: float | None = None
    evidence: Sequence[str] = field(default_factory=tuple)
    schema: str = WB_CORE_OUTCOME_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != WB_CORE_OUTCOME_SCHEMA or self.status not in _OUTCOME_STATUSES:
            raise ValueError("wb-core release outcome status is invalid")
        _machine("reason_code", self.reason_code)
        for name in ("candidate_id", "task_id", "workstream_id"):
            _machine(name, getattr(self, name))
        if self.target_task_id != derive_wb_core_target_task_id(self.task_id):
            raise ValueError("wb-core release outcome target task bridge is invalid")
        for name in ("task_revision", "workstream_revision", "pr_number"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError("wb-core release outcome revision/PR is invalid")
        if not _SHA_RE.fullmatch(self.expected_head_sha) or not _SHA_RE.fullmatch(self.observed_head_sha):
            raise ValueError("wb-core release outcome head identity is invalid")
        if self.contour not in {"release:done", "release:production"}:
            raise ValueError("wb-core release outcome contour is invalid")
        if not _DIGEST_RE.fullmatch(self.command_digest):
            raise ValueError("wb-core release outcome command digest is invalid")
        if not _PR_URL_RE.fullmatch(self.pr_url):
            raise ValueError("wb-core release outcome PR URL is invalid")
        if not self.pr_url.endswith(f"/{self.pr_number}"):
            raise ValueError("wb-core release outcome PR URL names another PR")
        if self.admission_binding is not None:
            binding = self.admission_binding
            if (
                not isinstance(binding, WbCoreAdmissionBinding)
                or binding.pr_number != self.pr_number
                or binding.head_sha != self.observed_head_sha
                or binding.target_task_id != self.target_task_id
                or binding.task_revision > self.task_revision
            ):
                raise ValueError("wb-core outcome admission binding is invalid")
        if self.merge_sha is not None and not _SHA_RE.fullmatch(self.merge_sha):
            raise ValueError("wb-core release outcome merge SHA is invalid")
        if self.terminal_label is not None and self.terminal_label not in {
            "release:done", "release:production"
        }:
            raise ValueError("wb-core release outcome terminal label is invalid")
        if self.terminal_proof_digest is not None and not _DIGEST_RE.fullmatch(
            self.terminal_proof_digest
        ):
            raise ValueError("wb-core release outcome terminal proof digest is invalid")
        if self.command_comment_id is not None and (
            isinstance(self.command_comment_id, bool)
            or not isinstance(self.command_comment_id, int)
            or self.command_comment_id < 1
        ):
            raise ValueError("wb-core release outcome comment receipt is invalid")
        if self.next_poll_after_seconds is not None and (
            isinstance(self.next_poll_after_seconds, bool)
            or not isinstance(self.next_poll_after_seconds, (int, float))
            or not 0 <= float(self.next_poll_after_seconds) <= 3_600
        ):
            raise ValueError("wb-core release outcome next poll is invalid")
        evidence = _stable_strings("outcome.evidence", self.evidence, maximum=32)
        object.__setattr__(self, "evidence", evidence)
        if self.status == "terminal" and (
            self.merge_sha is None
            or self.terminal_label is None
            or self.terminal_proof_digest is None
            or self.admission_binding is None
            or self.observed_head_sha != self.expected_head_sha
            or self.terminal_label != self.contour
        ):
            raise ValueError("terminal wb-core outcome lacks immutable proof")

    @property
    def pr_identity(self) -> str | None:
        if self.status != "terminal" or self.merge_sha is None:
            return None
        return (
            f"github-pr-v1:{WB_CORE_REPOSITORY}:{self.pr_number}:"
            f"{self.expected_head_sha}:{self.merge_sha}"
        )

    @property
    def hosted_deploy_identity(self) -> str | None:
        if self.status != "terminal" or self.contour != "release:production" or self.merge_sha is None:
            return None
        return (
            f"hosted-release-v1:{WB_CORE_PRODUCTION_TARGET}:"
            f"{WB_CORE_PRODUCTION_DOMAIN}:{self.merge_sha}"
        )

    def to_mapping(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["evidence"] = list(self.evidence)
        return payload


@dataclass(frozen=True)
class WbCoreLaneReleaseOutcome:
    """Sanitized receipt/observation for the task-level lane release."""

    status: str
    reason_code: str
    closure_event_id: str
    task_id: str
    target_task_id: str
    task_revision: int
    anchor_pr: int
    outcome: str
    evidence_digest: str
    command_digest: str
    lane_status: str
    observed_lane_owner_pr: int | None = None
    command_comment_id: int | None = None
    release_proof_digest: str | None = None
    next_poll_after_seconds: float | None = None
    evidence: Sequence[str] = field(default_factory=tuple)
    schema: str = WB_CORE_LANE_RELEASE_OUTCOME_SCHEMA

    def __post_init__(self) -> None:
        if (
            self.schema != WB_CORE_LANE_RELEASE_OUTCOME_SCHEMA
            or self.status not in _LANE_RELEASE_STATUSES
        ):
            raise ValueError("wb-core lane-release outcome status is invalid")
        _machine("reason_code", self.reason_code)
        _machine("closure_event_id", self.closure_event_id)
        _machine("task_id", self.task_id)
        if self.target_task_id != derive_wb_core_target_task_id(self.task_id):
            raise ValueError("wb-core lane-release outcome task bridge is invalid")
        for name in ("task_revision", "anchor_pr"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError("wb-core lane-release outcome identity is invalid")
        if self.outcome not in {"completed", "parked"}:
            raise ValueError("wb-core lane-release outcome kind is invalid")
        if not _DIGEST_RE.fullmatch(self.evidence_digest) or not _DIGEST_RE.fullmatch(
            self.command_digest
        ):
            raise ValueError("wb-core lane-release outcome digest is invalid")
        if self.lane_status not in _LANE_STATUSES:
            raise ValueError("wb-core lane-release observed lane status is invalid")
        if self.observed_lane_owner_pr is not None and (
            isinstance(self.observed_lane_owner_pr, bool)
            or not isinstance(self.observed_lane_owner_pr, int)
            or self.observed_lane_owner_pr < 1
        ):
            raise ValueError("wb-core lane-release observed owner is invalid")
        if (self.lane_status == "owned") != (self.observed_lane_owner_pr is not None):
            raise ValueError("wb-core lane-release lane owner state is inconsistent")
        if self.command_comment_id is not None and (
            isinstance(self.command_comment_id, bool)
            or not isinstance(self.command_comment_id, int)
            or self.command_comment_id < 1
        ):
            raise ValueError("wb-core lane-release comment receipt is invalid")
        if self.release_proof_digest is not None and not _DIGEST_RE.fullmatch(
            self.release_proof_digest
        ):
            raise ValueError("wb-core lane-release proof digest is invalid")
        if self.next_poll_after_seconds is not None and (
            isinstance(self.next_poll_after_seconds, bool)
            or not isinstance(self.next_poll_after_seconds, (int, float))
            or not 1 <= float(self.next_poll_after_seconds) <= 3_600
        ):
            raise ValueError("wb-core lane-release next poll is invalid")
        if self.status == "released" and self.release_proof_digest is None:
            raise ValueError("released wb-core lane lacks an exact target proof")
        if self.status == "release_submitted" and self.next_poll_after_seconds is None:
            raise ValueError("pending wb-core lane release lacks a durable poll delay")
        evidence = _stable_strings("lane_release.evidence", self.evidence, maximum=16)
        object.__setattr__(self, "evidence", evidence)

    def to_mapping(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["evidence"] = list(self.evidence)
        return payload


class WbCoreReleaseTrainApi(Protocol):
    """Exact target boundary used by :class:`WbCoreReleaseAdapter`.

    ``read_queue_status`` must come from the current trusted ``origin/main``
    target runner. ``read_pull`` must include only bot-authenticated proof
    markers. Mutation methods may create only one issue comment containing the
    exact allowlisted command supplied by the corresponding adapter.
    """

    def orchestration_required(self) -> bool: ...

    def read_queue_status(
        self, release_proof_prs: Sequence[int] = ()
    ) -> WbCoreQueueReadback: ...

    def read_pull(self, pr_number: int) -> WbCorePullReadback: ...

    def submit_admission(
        self, pr_number: int, command: str, command_digest: str
    ) -> WbCoreCommandReceipt: ...

    def submit_lane_release(
        self, anchor_pr: int, command: str, command_digest: str
    ) -> WbCoreCommandReceipt: ...


class WbCoreReleaseAdapter:
    """Observe or admit one immutable target candidate without releasing it."""

    def __init__(
        self,
        api: WbCoreReleaseTrainApi,
        *,
        fence_guard: Callable[[str, WbCoreReleaseRequest], None],
        max_polls: int = 2,
        poll_interval_seconds: float = 0.0,
        next_poll_after_seconds: float = 30.0,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if not callable(fence_guard):
            raise ValueError("a live Supervisor fence guard is required")
        if isinstance(max_polls, bool) or not isinstance(max_polls, int) or not 1 <= max_polls <= 5:
            raise ValueError("wb-core adapter max_polls must be between one and five")
        if not 0 <= poll_interval_seconds <= 10:
            raise ValueError("wb-core adapter poll interval is out of bounds")
        if not 1 <= next_poll_after_seconds <= 3_600:
            raise ValueError("wb-core adapter durable poll interval is out of bounds")
        self.api = api
        self.fence_guard = fence_guard
        self.max_polls = max_polls
        self.poll_interval_seconds = float(poll_interval_seconds)
        self.next_poll_after_seconds = float(next_poll_after_seconds)
        self.sleeper = sleeper

    def advance(self, request: WbCoreReleaseRequest) -> WbCoreReleaseOutcome:
        """Perform at most one admission mutation and a bounded proof readback."""

        if not isinstance(request, WbCoreReleaseRequest):
            raise ValueError("wb-core adapter request is untyped")
        required = self._external(
            request,
            "orchestration_enforcement_readback",
            self.api.orchestration_required,
        )
        if required is not True:
            # Enforcement off would let the target worker ignore the v2 binding.
            pull = self._read_pull(request)
            return self._outcome(
                request,
                pull,
                status="failed",
                reason_code="orchestration_enforcement_disabled",
            )

        submitted: WbCoreCommandReceipt | None = None
        for poll_index in range(self.max_polls):
            queue = self._read_queue(request)
            pull = self._read_pull(request)
            disposition = self._classify(request, queue, pull)
            if disposition != "submit_admission":
                return disposition

            if submitted is None:
                command = request.admission_command()
                digest = request.admission_command_digest()
                submitted = self._external(
                    request,
                    "admission_command",
                    lambda: self.api.submit_admission(request.pr_number, command, digest),
                )
                if not isinstance(submitted, WbCoreCommandReceipt) or submitted.command_digest != digest:
                    raise WbCoreReleaseAdapterError("admission_transport_receipt_invalid")
            if poll_index + 1 < self.max_polls:
                if self.poll_interval_seconds:
                    self.sleeper(self.poll_interval_seconds)
                continue
            return self._outcome(
                request,
                pull,
                status="admission_submitted",
                reason_code="trusted_main_admission_pending",
                command_comment_id=submitted.comment_id,
                evidence=(f"command:sha256:{submitted.command_digest}",),
            )
        raise AssertionError("bounded admission loop did not return")

    def observe(self, request: WbCoreReleaseRequest) -> WbCoreReleaseOutcome:
        """Read exact target truth once and never publish an admission command."""

        if not isinstance(request, WbCoreReleaseRequest):
            raise ValueError("wb-core adapter request is untyped")
        required = self._external(
            request,
            "orchestration_enforcement_readback",
            self.api.orchestration_required,
        )
        queue = self._read_queue(request)
        pull = self._read_pull(request)
        if required is not True:
            return self._outcome(
                request,
                pull,
                status="failed",
                reason_code="orchestration_enforcement_disabled",
            )
        disposition = self._classify(request, queue, pull)
        if disposition == "submit_admission":
            return self._outcome(
                request,
                pull,
                status="waiting_release",
                reason_code="exact_admission_not_submitted",
            )
        return disposition

    def verify_terminal(self, request: WbCoreReleaseRequest) -> WbCoreReleaseOutcome:
        """Return one exact terminal proof or fail with a sanitized reason code."""

        outcome = self.observe(request)
        if outcome.status != "terminal":
            raise WbCoreReleaseAdapterError(
                "wb_core_terminal_not_proven_" + outcome.reason_code
            )
        return outcome

    def _classify(
        self,
        request: WbCoreReleaseRequest,
        queue: WbCoreQueueReadback,
        pull: WbCorePullReadback,
    ) -> WbCoreReleaseOutcome | str:
        labels = set(pull.labels)
        if pull.number != request.pr_number:
            return self._outcome(request, pull, "failed", "pr_identity_mismatch")
        if pull.head_sha != request.expected_head_sha:
            status = "readmission_required" if pull.state == "OPEN" else "failed"
            reason = "pr_head_changed" if pull.state == "OPEN" else "merged_head_mismatch"
            return self._outcome(request, pull, status, reason)
        if pull.is_draft:
            return self._outcome(request, pull, "failed", "pr_is_draft")
        if queue.lane_status == "conflict" or queue.queue_status == "gate-conflict":
            return self._outcome(request, pull, "failed", "target_queue_integrity_failed")
        if queue.queue_status == "halted":
            return self._outcome(request, pull, "failed", "target_queue_halted")

        task_labels = labels & _TASK_LABELS
        scope_labels = labels & _SCOPE_LABELS
        if task_labels != {"task:standard"} or scope_labels != {request.expected_scope_label}:
            return self._outcome(request, pull, "failed", "pr_classification_mismatch")
        if "release:halted" in labels:
            return self._outcome(request, pull, "failed", "target_release_halted")
        if "release:blocked" in labels:
            return self._outcome(request, pull, "failed", "target_release_blocked")

        current_proofs = tuple(
            proof for proof in pull.admission_proofs if proof.head_sha == pull.head_sha
        )
        distinct_bindings = {proof.binding() for proof in current_proofs}
        if len(distinct_bindings) > 1:
            return self._outcome(request, pull, "failed", "admission_proof_conflict")
        admission = current_proofs[-1] if current_proofs else None
        if admission is not None:
            actual_binding = WbCoreAdmissionBinding.from_proof(admission)
            if request.admission_binding is not None:
                binding_matches = actual_binding == request.admission_binding
            else:
                binding_matches = (
                    admission.pr_number == request.pr_number
                    and admission.target_task_id == request.target_task_id
                    and admission.task_revision == request.task_revision
                    and admission.passport_digest == request.passport_digest
                )
            if not binding_matches:
                return self._outcome(
                    request,
                    pull,
                    "failed",
                    "admission_binding_mismatch",
                )

        present_terminal = labels & _TERMINAL_LABELS
        if request.expected_terminal_label in labels:
            if pull.state != "MERGED" or pull.merge_sha is None or admission is None:
                return self._outcome(request, pull, "failed", "terminal_identity_incomplete")
            if (
                request.expected_merge_sha is not None
                and pull.merge_sha != request.expected_merge_sha
            ):
                return self._outcome(request, pull, "failed", "terminal_merge_mismatch")
            terminal = self._matching_terminal_proof(request, pull)
            if terminal is None:
                return self._outcome(request, pull, "failed", "terminal_proof_missing")
            return self._outcome(
                request,
                pull,
                "terminal",
                "terminal_release_proven",
                merge_sha=pull.merge_sha,
                terminal_label=request.expected_terminal_label,
                terminal_proof_digest=terminal.digest(),
                admission_binding=WbCoreAdmissionBinding.from_proof(admission),
                evidence=(
                    f"admission:sha256:{admission.digest()}",
                    f"terminal:sha256:{terminal.digest()}",
                ),
            )
        if present_terminal:
            return self._outcome(request, pull, "failed", "terminal_contour_mismatch")
        if pull.state == "MERGED":
            if admission is None or pull.merge_sha is None:
                return self._outcome(request, pull, "failed", "merged_identity_incomplete")
            return self._outcome(
                request,
                pull,
                "waiting_release",
                "terminal_release_pending",
                merge_sha=pull.merge_sha,
                admission_binding=WbCoreAdmissionBinding.from_proof(admission),
            )
        if pull.state != "OPEN":
            return self._outcome(request, pull, "failed", "pr_state_invalid")

        if queue.lane_status == "owned":
            if queue.lane_task_id != request.target_task_id:
                return self._outcome(
                    request,
                    pull,
                    "waiting_foreign_lane",
                    "foreign_release_lane",
                )
            if int(queue.lane_revision or 0) > request.task_revision:
                return self._outcome(request, pull, "failed", "release_lane_revision_newer")
        if queue.queue_status in {"awaiting-agent", "awaiting-ui", "finance-deploy-lease"} and (
            queue.lane_status != "owned" or queue.lane_task_id != request.target_task_id
        ):
            return self._outcome(
                request,
                pull,
                "waiting_foreign_lane",
                "foreign_exclusive_gate",
            )

        if admission is not None:
            if (
                queue.lane_status != "owned"
                or queue.lane_task_id != request.target_task_id
                or admission.owner_pr != queue.lane_owner_pr
            ):
                return self._outcome(
                    request,
                    pull,
                    "failed",
                    "admission_lane_binding_mismatch",
                )
            if not labels & {
                "release:staged",
                "release:ready",
                "release:running",
                "release:awaiting-agent",
                "release:awaiting-ui",
            }:
                return self._outcome(request, pull, "failed", "admitted_release_state_missing")
            return self._outcome(
                request,
                pull,
                "admitted",
                "exact_admission_proven",
                admission_binding=WbCoreAdmissionBinding.from_proof(admission),
                evidence=(f"admission:sha256:{admission.digest()}",),
            )

        if "release:staged" not in labels:
            return self._outcome(request, pull, "failed", "release_staged_missing")
        command_digest = request.admission_command_digest()
        if command_digest in pull.submitted_command_digests:
            return self._outcome(
                request,
                pull,
                "admission_submitted",
                "trusted_main_admission_pending",
                evidence=(f"command:sha256:{command_digest}",),
            )
        return "submit_admission"

    def _matching_terminal_proof(
        self,
        request: WbCoreReleaseRequest,
        pull: WbCorePullReadback,
    ) -> WbCoreTerminalProof | None:
        matches = tuple(
            proof
            for proof in pull.terminal_proofs
            if proof.merge_sha == pull.merge_sha
            and proof.contour == request.expected_completion_contour
        )
        distinct = {(item.pr_number, item.merge_sha, item.contour) for item in matches}
        if len(distinct) != 1:
            return None
        return sorted(matches, key=lambda item: item.marker)[0]

    def _read_queue(self, request: WbCoreReleaseRequest) -> WbCoreQueueReadback:
        value = self._external(
            request,
            "queue_status_readback",
            lambda: self.api.read_queue_status(()),
        )
        if not isinstance(value, WbCoreQueueReadback):
            raise WbCoreReleaseAdapterError("target_queue_readback_untyped")
        return value

    def _read_pull(self, request: WbCoreReleaseRequest) -> WbCorePullReadback:
        value = self._external(
            request,
            "pull_request_readback",
            lambda: self.api.read_pull(request.pr_number),
        )
        if not isinstance(value, WbCorePullReadback):
            raise WbCoreReleaseAdapterError("target_pull_readback_untyped")
        return value

    def _external(
        self,
        request: WbCoreReleaseRequest,
        boundary: str,
        operation: Callable[[], Any],
    ) -> Any:
        self.fence_guard(f"before_{boundary}", request)
        value = operation()
        self.fence_guard(f"after_{boundary}", request)
        return value

    def _outcome(
        self,
        request: WbCoreReleaseRequest,
        pull: WbCorePullReadback,
        status: str,
        reason_code: str,
        *,
        merge_sha: str | None = None,
        terminal_label: str | None = None,
        terminal_proof_digest: str | None = None,
        admission_binding: WbCoreAdmissionBinding | None = None,
        command_comment_id: int | None = None,
        evidence: Sequence[str] = (),
    ) -> WbCoreReleaseOutcome:
        return WbCoreReleaseOutcome(
            status=status,
            reason_code=reason_code,
            candidate_id=request.candidate_id,
            task_id=request.task_id,
            target_task_id=request.target_task_id,
            workstream_id=request.workstream_id,
            task_revision=request.task_revision,
            workstream_revision=request.workstream_revision,
            pr_number=request.pr_number,
            expected_head_sha=request.expected_head_sha,
            observed_head_sha=pull.head_sha,
            contour=request.contour,
            command_digest=request.admission_command_digest(),
            pr_url=pull.url,
            admission_binding=admission_binding,
            merge_sha=merge_sha,
            terminal_label=terminal_label,
            terminal_proof_digest=terminal_proof_digest,
            command_comment_id=command_comment_id,
            next_poll_after_seconds=(
                self.next_poll_after_seconds
                if status
                in {
                    "admission_submitted",
                    "admitted",
                    "waiting_foreign_lane",
                    "waiting_release",
                }
                else None
            ),
            evidence=tuple(evidence),
        )


class WbCoreReleaseLaneAdapter:
    """Release one target logical lane after durable task-level closure.

    This is a bounded transport for wb-core's existing trusted-main
    ``release-lane`` command, not a local label mutator.  The required
    ``authorization_guard`` is the Supervisor-owned proof that the whole task
    contour is closed or that the task was parked after the serious-stall
    policy.  It is rechecked immediately before the sole possible mutation.
    """

    def __init__(
        self,
        api: WbCoreReleaseTrainApi,
        *,
        fence_guard: Callable[[str, WbCoreLaneReleaseRequest], None],
        authorization_guard: Callable[[WbCoreLaneReleaseRequest], None],
        max_polls: int = 2,
        poll_interval_seconds: float = 0.0,
        next_poll_after_seconds: float = 30.0,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if not callable(fence_guard) or not callable(authorization_guard):
            raise ValueError("lane release requires fence and durable authorization guards")
        if (
            isinstance(max_polls, bool)
            or not isinstance(max_polls, int)
            or not 1 <= max_polls <= 5
        ):
            raise ValueError("wb-core lane-release max_polls must be between one and five")
        if not 0 <= poll_interval_seconds <= 10:
            raise ValueError("wb-core lane-release poll interval is out of bounds")
        if not 1 <= next_poll_after_seconds <= 3_600:
            raise ValueError("wb-core lane-release durable poll interval is out of bounds")
        self.api = api
        self.fence_guard = fence_guard
        self.authorization_guard = authorization_guard
        self.max_polls = max_polls
        self.poll_interval_seconds = float(poll_interval_seconds)
        self.next_poll_after_seconds = float(next_poll_after_seconds)
        self.sleeper = sleeper

    def advance(
        self, request: WbCoreLaneReleaseRequest
    ) -> WbCoreLaneReleaseOutcome:
        """Publish at most one exact command and read its Actions proof."""

        if not isinstance(request, WbCoreLaneReleaseRequest):
            raise ValueError("wb-core lane-release request is untyped")
        self.authorization_guard(request)
        required = self._external(
            request,
            "orchestration_enforcement_readback",
            self.api.orchestration_required,
        )
        submitted: WbCoreCommandReceipt | None = None
        for poll_index in range(self.max_polls):
            queue = self._read_queue(request)
            pull = self._read_pull(request)
            if required is not True:
                return self._outcome(
                    request,
                    queue,
                    "failed",
                    "orchestration_enforcement_disabled",
                )
            disposition = self._classify(request, queue, pull)
            if disposition != "submit_lane_release":
                return disposition
            if submitted is None:
                # Closure state is local durable authority and is re-read at
                # the last safe boundary before the outbound GitHub command.
                self.authorization_guard(request)
                command = request.release_command()
                digest = request.release_command_digest()
                submitted = self._external(
                    request,
                    "lane_release_command",
                    lambda: self.api.submit_lane_release(
                        request.anchor_pr, command, digest
                    ),
                )
                if (
                    not isinstance(submitted, WbCoreCommandReceipt)
                    or submitted.command_digest != digest
                ):
                    raise WbCoreReleaseAdapterError(
                        "lane_release_transport_receipt_invalid"
                    )
            if poll_index + 1 < self.max_polls:
                if self.poll_interval_seconds:
                    self.sleeper(self.poll_interval_seconds)
                continue
            return self._outcome(
                request,
                queue,
                "release_submitted",
                "trusted_main_lane_release_pending",
                command_comment_id=submitted.comment_id,
                evidence=(f"command:sha256:{submitted.command_digest}",),
            )
        raise AssertionError("bounded lane-release loop did not return")

    def _classify(
        self,
        request: WbCoreLaneReleaseRequest,
        queue: WbCoreQueueReadback,
        pull: WbCorePullReadback,
    ) -> WbCoreLaneReleaseOutcome | str:
        if pull.number != request.anchor_pr:
            return self._outcome(request, queue, "failed", "lane_anchor_mismatch")
        if queue.lane_status == "conflict" or queue.queue_status == "gate-conflict":
            return self._outcome(
                request, queue, "failed", "target_queue_integrity_failed"
            )

        proofs = tuple(
            proof
            for proof in queue.release_proofs
            if proof.owner_pr == request.anchor_pr
        )
        if len({proof.binding() for proof in proofs}) > 1:
            return self._outcome(
                request, queue, "failed", "lane_release_proof_conflict"
            )
        proof = proofs[-1] if proofs else None
        if proof is not None:
            expected = (
                request.anchor_pr,
                request.target_task_id,
                request.task_revision,
                request.outcome,
                request.evidence_digest,
            )
            if proof.binding() != expected:
                return self._outcome(
                    request,
                    queue,
                    "stale",
                    "lane_release_proof_binding_mismatch",
                    release_proof_digest=proof.digest(),
                )
            # The proof is written before the owner label is removed.  A
            # same-owner read is therefore an expected bounded transition;
            # never publish a duplicate command merely to hurry it.
            if queue.lane_status == "owned" and queue.lane_owner_pr == request.anchor_pr:
                if queue.lane_task_id != request.target_task_id:
                    return self._outcome(
                        request, queue, "stale", "lane_release_owner_task_changed"
                    )
                return self._outcome(
                    request,
                    queue,
                    "release_submitted",
                    "lane_release_proof_observed_owner_transition_pending",
                    release_proof_digest=proof.digest(),
                    evidence=(f"lane-release:sha256:{proof.digest()}",),
                )
            return self._outcome(
                request,
                queue,
                "released",
                "exact_lane_release_proven",
                release_proof_digest=proof.digest(),
                evidence=(f"lane-release:sha256:{proof.digest()}",),
            )

        if queue.lane_status == "idle":
            return self._outcome(
                request, queue, "stale", "lane_release_owner_missing_without_proof"
            )
        if queue.lane_owner_pr != request.anchor_pr:
            return self._outcome(
                request, queue, "stale", "lane_release_anchor_is_not_current_owner"
            )
        if queue.lane_task_id != request.target_task_id:
            return self._outcome(
                request, queue, "stale", "lane_release_owner_task_changed"
            )
        if int(queue.lane_revision or 0) > request.task_revision:
            return self._outcome(
                request, queue, "stale", "lane_release_revision_is_stale"
            )
        digest = request.release_command_digest()
        if digest in pull.submitted_command_digests:
            return self._outcome(
                request,
                queue,
                "release_submitted",
                "trusted_main_lane_release_pending",
                evidence=(f"command:sha256:{digest}",),
            )
        return "submit_lane_release"

    def _read_queue(
        self, request: WbCoreLaneReleaseRequest
    ) -> WbCoreQueueReadback:
        value = self._external(
            request,
            "queue_status_readback",
            lambda: self.api.read_queue_status((request.anchor_pr,)),
        )
        if not isinstance(value, WbCoreQueueReadback):
            raise WbCoreReleaseAdapterError("target_queue_readback_untyped")
        return value

    def _read_pull(
        self, request: WbCoreLaneReleaseRequest
    ) -> WbCorePullReadback:
        value = self._external(
            request,
            "pull_request_readback",
            lambda: self.api.read_pull(request.anchor_pr),
        )
        if not isinstance(value, WbCorePullReadback):
            raise WbCoreReleaseAdapterError("target_pull_readback_untyped")
        return value

    def _external(
        self,
        request: WbCoreLaneReleaseRequest,
        boundary: str,
        operation: Callable[[], Any],
    ) -> Any:
        self.fence_guard(f"before_{boundary}", request)
        value = operation()
        self.fence_guard(f"after_{boundary}", request)
        return value

    def _outcome(
        self,
        request: WbCoreLaneReleaseRequest,
        queue: WbCoreQueueReadback,
        status: str,
        reason_code: str,
        *,
        command_comment_id: int | None = None,
        release_proof_digest: str | None = None,
        evidence: Sequence[str] = (),
    ) -> WbCoreLaneReleaseOutcome:
        return WbCoreLaneReleaseOutcome(
            status=status,
            reason_code=reason_code,
            closure_event_id=request.closure_event_id,
            task_id=request.task_id,
            target_task_id=request.target_task_id,
            task_revision=request.task_revision,
            anchor_pr=request.anchor_pr,
            outcome=request.outcome,
            evidence_digest=request.evidence_digest,
            command_digest=request.release_command_digest(),
            lane_status=queue.lane_status,
            observed_lane_owner_pr=queue.lane_owner_pr,
            command_comment_id=command_comment_id,
            release_proof_digest=release_proof_digest,
            next_poll_after_seconds=(
                self.next_poll_after_seconds
                if status == "release_submitted"
                else None
            ),
            evidence=tuple(evidence),
        )


QueueSnapshotReader = Callable[[Sequence[int]], Mapping[str, Any]]


class GhWbCoreReleaseTrainApi:
    """Allowlisted GitHub transport plus an injected trusted-main queue reader.

    The queue reader is deliberately mandatory: reimplementing the target's
    queue classifier in this repository would create a second Release Train.
    It must execute the exact current target ``queue-status`` entrypoint from a
    verified ``origin/main`` source, append one ``--release-proof-pr`` per
    supplied identity, and return its JSON object.
    """

    _PR_FIELDS = "number,state,isDraft,headRefOid,baseRefName,labels,mergeCommit,url"

    def __init__(
        self,
        *,
        queue_snapshot_reader: QueueSnapshotReader,
        gh_binary: str = "gh",
        timeout_seconds: float = 45.0,
    ) -> None:
        if not callable(queue_snapshot_reader):
            raise ValueError("trusted-main wb-core queue reader is required")
        if not isinstance(gh_binary, str) or not gh_binary or "\x00" in gh_binary:
            raise ValueError("gh binary is invalid")
        if not 1 <= timeout_seconds <= 120:
            raise ValueError("GitHub timeout is out of bounds")
        self.queue_snapshot_reader = queue_snapshot_reader
        self.gh_binary = gh_binary
        self.timeout_seconds = float(timeout_seconds)

    def orchestration_required(self) -> bool:
        payload = self._run_json(
            (
                "api",
                f"repos/{WB_CORE_REPOSITORY}/actions/variables/WB_CORE_ORCHESTRATION_REQUIRED",
            )
        )
        if not isinstance(payload, Mapping):
            raise WbCoreReleaseAdapterError("target_enforcement_readback_invalid")
        raw_value = payload.get("value")
        if not isinstance(raw_value, str):
            raise WbCoreReleaseAdapterError("target_enforcement_readback_invalid")
        value = raw_value.strip().casefold()
        if value not in {"true", "false"}:
            raise WbCoreReleaseAdapterError("target_enforcement_readback_invalid")
        return value == "true"

    def read_queue_status(
        self, release_proof_prs: Sequence[int] = ()
    ) -> WbCoreQueueReadback:
        proof_prs: list[int] = []
        for value in release_proof_prs:
            _positive_pr(value)
            if value not in proof_prs:
                proof_prs.append(value)
            if len(proof_prs) > 32:
                raise WbCoreReleaseAdapterError("target_queue_readback_oversized")
        try:
            payload = self.queue_snapshot_reader(tuple(proof_prs))
        except Exception as exc:
            raise WbCoreReleaseAdapterError("target_queue_readback_failed") from exc
        return WbCoreQueueReadback.from_target_snapshot(
            payload,
            expected_release_proof_prs=tuple(proof_prs),
        )

    def read_pull(self, pr_number: int) -> WbCorePullReadback:
        _positive_pr(pr_number)
        payload = self._run_json(
            (
                "pr",
                "view",
                str(pr_number),
                "--repo",
                WB_CORE_REPOSITORY,
                "--json",
                self._PR_FIELDS,
            )
        )
        comments = self._run_json(
            (
                "api",
                "--paginate",
                "--slurp",
                f"/repos/{WB_CORE_REPOSITORY}/issues/{pr_number}/comments?per_page=100",
            ),
            max_output_bytes=_MAX_PROVIDER_OUTPUT_BYTES,
        )
        return pull_readback_from_github(payload, comments)

    def submit_admission(
        self,
        pr_number: int,
        command: str,
        command_digest: str,
    ) -> WbCoreCommandReceipt:
        _positive_pr(pr_number)
        if not _DIGEST_RE.fullmatch(command_digest) or _sha256_text(command) != command_digest:
            raise WbCoreReleaseAdapterError("admission_command_digest_mismatch")
        if not _valid_admission_command(command, pr_number):
            raise WbCoreReleaseAdapterError("admission_command_not_allowlisted")
        return self._submit_comment(
            pr_number,
            command,
            command_digest,
            receipt_error="admission_transport_receipt_invalid",
        )

    def submit_lane_release(
        self,
        anchor_pr: int,
        command: str,
        command_digest: str,
    ) -> WbCoreCommandReceipt:
        _positive_pr(anchor_pr)
        if not _DIGEST_RE.fullmatch(command_digest) or _sha256_text(command) != command_digest:
            raise WbCoreReleaseAdapterError("lane_release_command_digest_mismatch")
        if not _valid_lane_release_command(command, anchor_pr):
            raise WbCoreReleaseAdapterError("lane_release_command_not_allowlisted")
        return self._submit_comment(
            anchor_pr,
            command,
            command_digest,
            receipt_error="lane_release_transport_receipt_invalid",
        )

    def _submit_comment(
        self,
        pr_number: int,
        command: str,
        command_digest: str,
        *,
        receipt_error: str,
    ) -> WbCoreCommandReceipt:
        payload = self._run_json(
            (
                "api",
                "--method",
                "POST",
                f"repos/{WB_CORE_REPOSITORY}/issues/{pr_number}/comments",
                "-f",
                f"body={command}",
            )
        )
        if not isinstance(payload, Mapping):
            raise WbCoreReleaseAdapterError(receipt_error)
        try:
            comment_id = payload["id"]
            created_at = payload["created_at"]
            if (
                isinstance(comment_id, bool)
                or not isinstance(comment_id, int)
                or not isinstance(created_at, str)
            ):
                raise ValueError("receipt")
            return WbCoreCommandReceipt(
                command_digest=command_digest,
                comment_id=comment_id,
                created_at=created_at,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise WbCoreReleaseAdapterError(receipt_error) from exc

    def _run_json(
        self,
        arguments: Sequence[str],
        *,
        max_output_bytes: int = 1_000_000,
    ) -> Any:
        try:
            completed = subprocess.run(
                [self.gh_binary, *arguments],
                check=False,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise WbCoreReleaseAdapterError("github_transport_unavailable") from exc
        if completed.returncode != 0:
            raise WbCoreReleaseAdapterError(
                f"github_transport_failed_exit_{completed.returncode}"
            )
        try:
            encoded = completed.stdout.encode("utf-8")
        except UnicodeError as exc:
            raise WbCoreReleaseAdapterError("github_readback_invalid_text") from exc
        if len(encoded) > max_output_bytes:
            raise WbCoreReleaseAdapterError("github_readback_oversized")
        try:
            return json.loads(completed.stdout)
        except (json.JSONDecodeError, UnicodeError) as exc:
            raise WbCoreReleaseAdapterError("github_readback_invalid_json") from exc


def pull_readback_from_github(payload: Any, comments_payload: Any) -> WbCorePullReadback:
    """Reduce GitHub PR/comments to exact bot proofs and command receipts."""

    if not isinstance(payload, Mapping):
        raise WbCoreReleaseAdapterError("target_pull_readback_invalid")
    comments = _flatten_comments(comments_payload)
    try:
        number_raw = payload["number"]
        if isinstance(number_raw, bool) or not isinstance(number_raw, int):
            raise ValueError("number")
        number = number_raw
        raw_state = str(payload.get("state") or "").upper()
        merge_raw = payload.get("mergeCommit")
        merge_oid = merge_raw.get("oid") if isinstance(merge_raw, Mapping) else None
        if merge_oid is not None and not isinstance(merge_oid, str):
            raise ValueError("merge oid")
        merge_sha = merge_oid or ""
        if raw_state not in {"OPEN", "MERGED", "CLOSED"}:
            raise ValueError("state")
        if _SHA_RE.fullmatch(merge_sha) and raw_state != "MERGED":
            raise ValueError("merge state")
        if raw_state == "MERGED" and not _SHA_RE.fullmatch(merge_sha):
            raise ValueError("merge state")
        state = raw_state
        head_sha_raw = payload["headRefOid"]
        base_ref_raw = payload["baseRefName"]
        url_raw = payload["url"]
        if not all(isinstance(item, str) for item in (head_sha_raw, base_ref_raw, url_raw)):
            raise ValueError("pull identity")
        head_sha = head_sha_raw
        draft_raw = payload.get("isDraft")
        if not isinstance(draft_raw, bool):
            raise ValueError("isDraft")
        labels_raw = payload.get("labels")
        if not isinstance(labels_raw, Sequence) or isinstance(labels_raw, (str, bytes, bytearray)):
            raise ValueError("labels")
        labels = tuple(
            str(item["name"])
            for item in labels_raw
            if isinstance(item, Mapping) and isinstance(item.get("name"), str)
        )
        if len(labels) != len(labels_raw):
            raise ValueError("labels")
        admissions: list[WbCoreAdmissionProof] = []
        terminals: list[WbCoreTerminalProof] = []
        commands: list[str] = []
        for comment in comments:
            body = str(comment.get("body") or "")
            user = comment.get("user")
            login = str(user.get("login") or "") if isinstance(user, Mapping) else ""
            if login in _BOT_LOGINS:
                for fields in _marker_fields(body, WB_CORE_ADMISSION_MARKER):
                    if set(fields) != {"head", "owner_pr", "passport", "pr", "revision", "task"}:
                        continue
                    passport = _prefixed_digest(fields["passport"])
                    admissions.append(
                        WbCoreAdmissionProof(
                            pr_number=int(fields["pr"]),
                            owner_pr=int(fields["owner_pr"]),
                            head_sha=fields["head"],
                            target_task_id=fields["task"],
                            task_revision=int(fields["revision"]),
                            passport_digest=passport,
                        )
                    )
                for fields in _marker_fields(body, WB_CORE_COMPLETION_MARKER):
                    if set(fields) != {"contour", "merge", "pr"}:
                        continue
                    terminals.append(
                        WbCoreTerminalProof(
                            pr_number=int(fields["pr"]),
                            merge_sha=fields["merge"],
                            contour=fields["contour"],
                        )
                    )
                for fields in _marker_fields(body, WB_CORE_RECONCILE_MARKER):
                    if set(fields) != {"merge", "pr"}:
                        continue
                    terminals.append(
                        WbCoreTerminalProof(
                            pr_number=int(fields["pr"]),
                            merge_sha=fields["merge"],
                            contour="production-verified",
                            marker=WB_CORE_RECONCILE_MARKER,
                        )
                    )
            association = str(comment.get("author_association") or "").upper()
            command = body.strip()
            if association in _COMMAND_ASSOCIATIONS and (
                _valid_admission_command(command, number)
                or _valid_lane_release_command(command, number)
            ):
                commands.append(_sha256_text(command))
        return WbCorePullReadback(
            number=number,
            state=state,
            is_draft=draft_raw,
            head_sha=head_sha,
            base_ref=base_ref_raw,
            labels=labels,
            url=url_raw,
            merge_sha=merge_sha if _SHA_RE.fullmatch(merge_sha) else None,
            admission_proofs=tuple(admissions),
            terminal_proofs=tuple(terminals),
            submitted_command_digests=tuple(commands),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise WbCoreReleaseAdapterError("target_pull_readback_invalid") from exc


def _flatten_comments(payload: Any) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(payload, Sequence) or isinstance(payload, (str, bytes, bytearray)):
        raise WbCoreReleaseAdapterError("target_comment_readback_invalid")
    comments: list[Mapping[str, Any]] = []
    # ``gh api --paginate --slurp`` returns pages; accept a single unpaged list
    # only for purpose-built connectors that already performed full pagination.
    pages: Sequence[Any]
    if payload and all(isinstance(item, Mapping) for item in payload):
        pages = (payload,)
    else:
        pages = payload
    for page in pages:
        if not isinstance(page, Sequence) or isinstance(page, (str, bytes, bytearray)):
            raise WbCoreReleaseAdapterError("target_comment_readback_invalid")
        for item in page:
            if not isinstance(item, Mapping):
                raise WbCoreReleaseAdapterError("target_comment_readback_invalid")
            comments.append(item)
            if len(comments) > 3_000:
                raise WbCoreReleaseAdapterError("target_comment_readback_oversized")
    return tuple(comments)


def _marker_fields(body: str, marker: str) -> tuple[dict[str, str], ...]:
    prefix = f"<!-- {marker} "
    matches: list[dict[str, str]] = []
    for line in body.splitlines():
        if not line.startswith(prefix) or not line.endswith(" -->"):
            continue
        fields: dict[str, str] = {}
        valid = True
        for token in line[len(prefix) : -4].split():
            key, separator, value = token.partition("=")
            if not separator or not key or not value or key in fields:
                valid = False
                break
            fields[key] = value
        if valid:
            matches.append(fields)
    return tuple(matches)


def _valid_admission_command(command: str, pr_number: int) -> bool:
    parts = command.split()
    if (
        len(parts) != 12
        or parts[:3] != ["/wb-core", "orchestration", "admit"]
        or parts[4] != "head"
        or parts[6] != "task"
        or parts[8] != "revision"
        or parts[10] != "passport"
    ):
        return False
    try:
        return (
            int(parts[3]) == pr_number
            and _SHA_RE.fullmatch(parts[5]) is not None
            and _TARGET_TASK_RE.fullmatch(parts[7]) is not None
            and int(parts[9]) > 0
            and _DIGEST_RE.fullmatch(_prefixed_digest(parts[11])) is not None
        )
    except (TypeError, ValueError):
        return False


def _valid_lane_release_command(command: str, anchor_pr: int) -> bool:
    parts = command.split()
    if (
        len(parts) != 12
        or parts[:3] != ["/wb-core", "orchestration", "release-lane"]
        or parts[4] != "task"
        or parts[6] != "revision"
        or parts[8] != "outcome"
        or parts[10] != "evidence"
    ):
        return False
    try:
        return (
            int(parts[3]) == anchor_pr
            and _TARGET_TASK_RE.fullmatch(parts[5]) is not None
            and int(parts[7]) > 0
            and parts[9] in {"completed", "parked"}
            and _DIGEST_RE.fullmatch(_prefixed_digest(parts[11])) is not None
        )
    except (TypeError, ValueError):
        return False


def _prefixed_digest(value: str) -> str:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        raise ValueError("digest prefix")
    digest = value[7:]
    if not _DIGEST_RE.fullmatch(digest):
        raise ValueError("digest")
    return digest


def _positive_pr(value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise WbCoreReleaseAdapterError("target_pr_number_invalid")


def derive_wb_core_target_task_id(local_task_id: str) -> str:
    """Map a generic v2 task identity into wb-core's narrower task token.

    The mapping deliberately excludes the mutable Passport revision: all PRs
    and corrective revisions of one logical task must retain the same target
    release lane.  Revision and Passport digest remain separate mandatory
    fields in every admission command.
    """

    normalized = _machine("local_task_id", local_task_id)
    digest = hashlib.sha256(
        b"dev-control-plane/wb-core-target-task/v2\0" + normalized.encode("utf-8")
    ).hexdigest()
    return f"dcpv2-{digest[:40]}"


def wb_core_terminal_request_from_contracts(
    *,
    candidate_id: str,
    passport: Any,
    terminal: Any,
    pr_identity: str,
    admission_binding: WbCoreAdmissionBinding | None = None,
) -> WbCoreReleaseRequest:
    """Bind current v2 contracts to one immutable wb-core terminal request."""

    # Local imports keep this target adapter usable by small tooling without
    # making orchestration contracts a module-import side effect.
    from .orchestration_contracts import (  # pylint: disable=import-outside-toplevel
        TaskPassport,
        TerminalEvidence,
        contract_digest,
    )

    if not isinstance(passport, TaskPassport) or not isinstance(
        terminal, TerminalEvidence
    ):
        raise ValueError("wb-core terminal request requires typed v2 contracts")
    if (
        terminal.task_id != passport.task_id
        or terminal.task_revision != passport.revision
        or terminal.closure_kind != passport.contour
        or terminal.workstream_id not in passport.workstream_ids
    ):
        raise ValueError("wb-core terminal contracts are stale or cross-bound")
    if passport.contour not in {"release:done", "release:production"}:
        raise ValueError("wb-core terminal request requires a release contour")
    if pr_identity not in terminal.pr_identities:
        raise ValueError("wb-core terminal request PR is absent from terminal evidence")
    if (
        passport.release_manifest is not None
        and pr_identity not in passport.release_manifest.pr_identities
    ):
        raise ValueError("wb-core terminal request PR is absent from release manifest")
    match = _PR_IDENTITY_RE.fullmatch(pr_identity) if isinstance(pr_identity, str) else None
    if match is None:
        raise ValueError("wb-core terminal PR identity is malformed")
    if admission_binding is not None and (
        not isinstance(admission_binding, WbCoreAdmissionBinding)
        or admission_binding.pr_number != int(match.group("number"))
        or admission_binding.head_sha != match.group("head")
        or admission_binding.target_task_id
        != derive_wb_core_target_task_id(passport.task_id)
        or admission_binding.task_revision > passport.revision
    ):
        raise ValueError("wb-core durable admission binding is stale or cross-bound")
    return WbCoreReleaseRequest(
        candidate_id=_machine("candidate_id", candidate_id),
        task_id=passport.task_id,
        target_task_id=derive_wb_core_target_task_id(passport.task_id),
        workstream_id=terminal.workstream_id,
        task_revision=passport.revision,
        workstream_revision=terminal.workstream_revision,
        passport_digest=contract_digest(passport),
        pr_number=int(match.group("number")),
        expected_head_sha=match.group("head"),
        expected_merge_sha=match.group("merge"),
        contour=passport.contour,
        admission_binding=admission_binding,
    )


class WbCoreContourAdapter:
    """Independent read-only contour verifier backed by target GitHub truth."""

    def __init__(
        self,
        release_adapter: WbCoreReleaseAdapter,
        *,
        admission_binding_resolver: Callable[
            [Any, Any, str], WbCoreAdmissionBinding
        ]
        | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not isinstance(release_adapter, WbCoreReleaseAdapter):
            raise ValueError("wb-core contour verifier requires the typed release adapter")
        if not callable(clock):
            raise ValueError("wb-core contour verifier clock is invalid")
        if admission_binding_resolver is not None and not callable(
            admission_binding_resolver
        ):
            raise ValueError("wb-core admission binding resolver is invalid")
        self.release_adapter = release_adapter
        self.admission_binding_resolver = admission_binding_resolver
        self.clock = clock

    def __call__(self, passport: Any, terminal: Any) -> Any:
        from .contour_verifier import (  # pylint: disable=import-outside-toplevel
            ContourVerifierError,
            IndependentContourProof,
        )
        from .orchestration_contracts import (  # pylint: disable=import-outside-toplevel
            TaskPassport,
            TerminalEvidence,
        )
        from .supervisor import terminal_contract_digest  # pylint: disable=import-outside-toplevel

        if not isinstance(passport, TaskPassport) or not isinstance(
            terminal, TerminalEvidence
        ):
            raise ContourVerifierError("wb-core verifier requires typed v2 contracts")
        if (
            terminal.task_id != passport.task_id
            or terminal.task_revision != passport.revision
            or terminal.closure_kind != passport.contour
            or terminal.workstream_id not in passport.workstream_ids
            or terminal.owner_acceptance_required is not True
        ):
            raise ContourVerifierError(
                "wb-core terminal claim is stale or bound to another Passport"
            )
        if passport.contour not in {"release:done", "release:production"}:
            raise ContourVerifierError("wb-core verifier received a non-release contour")
        if not terminal.pr_identities:
            raise ContourVerifierError("wb-core release has no immutable PR identity")
        if not passport.multi_pr_intent and len(terminal.pr_identities) != 1:
            raise ContourVerifierError("single-PR wb-core release has multiple PR identities")
        if passport.multi_pr_intent and passport.release_manifest is None:
            raise ContourVerifierError("multi-PR wb-core release lacks a closure manifest")
        if passport.release_manifest is not None and (
            tuple(passport.release_manifest.pr_identities)
            != tuple(terminal.pr_identities)
            or tuple(passport.release_manifest.deploy_identities)
            != tuple(terminal.deploy_identities)
        ):
            raise ContourVerifierError(
                "wb-core terminal identities differ from the release manifest"
            )

        seen_prs: set[int] = set()
        outcomes: list[WbCoreReleaseOutcome] = []
        for index, identity in enumerate(terminal.pr_identities):
            match = _PR_IDENTITY_RE.fullmatch(identity)
            if match is None:
                raise ContourVerifierError("wb-core immutable PR identity is malformed")
            number = int(match.group("number"))
            if number in seen_prs:
                raise ContourVerifierError("wb-core immutable PR identity is duplicated")
            seen_prs.add(number)
            candidate_digest = _sha256_text(
                f"{terminal.terminal_id}\0{identity}\0{index}"
            )
            try:
                admission_binding = (
                    self.admission_binding_resolver(passport, terminal, identity)
                    if self.admission_binding_resolver is not None
                    else None
                )
                if admission_binding is not None and not isinstance(
                    admission_binding, WbCoreAdmissionBinding
                ):
                    raise ValueError("durable admission resolver returned no typed binding")
                request = wb_core_terminal_request_from_contracts(
                    candidate_id=f"wbcore-verify-{candidate_digest[:32]}",
                    passport=passport,
                    terminal=terminal,
                    pr_identity=identity,
                    admission_binding=admission_binding,
                )
                outcome = self.release_adapter.verify_terminal(request)
            except (ValueError, WbCoreReleaseAdapterError) as exc:
                reason = str(exc)
                if not _MACHINE_RE.fullmatch(reason):
                    reason = "target_terminal_readback_failed"
                raise ContourVerifierError(
                    "wb-core terminal proof failed: " + reason
                ) from exc
            if outcome.pr_identity != identity:
                raise ContourVerifierError(
                    "wb-core terminal proof returned another immutable PR"
                )
            if (
                admission_binding is not None
                and outcome.admission_binding != admission_binding
            ):
                raise ContourVerifierError(
                    "wb-core target proof differs from durable admission binding"
                )
            outcomes.append(outcome)

        merge_shas = tuple(outcome.merge_sha for outcome in outcomes)
        if any(value is None for value in merge_shas):
            raise ContourVerifierError("wb-core terminal proof omitted a merge identity")
        deploy_evidence: list[str] = []
        if passport.contour == "release:done":
            if terminal.deploy_identities:
                raise ContourVerifierError(
                    "repo-only wb-core contour claims a production deployment"
                )
        else:
            if not terminal.deploy_identities:
                raise ContourVerifierError(
                    "production wb-core contour lacks a hosted release identity"
                )
            deploy_releases: list[str] = []
            for identity in terminal.deploy_identities:
                match = _WB_CORE_DEPLOY_IDENTITY_RE.fullmatch(identity)
                if match is None:
                    raise ContourVerifierError(
                        "wb-core hosted release identity names an unapproved target"
                    )
                release_sha = match.group("release")
                if release_sha not in merge_shas:
                    raise ContourVerifierError(
                        "wb-core hosted release identity is not bound to a proved merge"
                    )
                deploy_releases.append(release_sha)
                deploy_evidence.append(f"hosted:{identity}")
            if deploy_releases[-1] != merge_shas[-1]:
                raise ContourVerifierError(
                    "wb-core final hosted release differs from the final merge"
                )
            if len(set(deploy_releases)) != len(deploy_releases):
                raise ContourVerifierError("wb-core hosted release identity is duplicated")

        terminal_digest = terminal_contract_digest(terminal)
        evidence = tuple(
            [
                *(
                    f"github:pr:{outcome.pr_number}:head:{outcome.expected_head_sha}:"
                    f"merge:{outcome.merge_sha}:proof:{outcome.terminal_proof_digest}:"
                    f"admission:{outcome.admission_binding.proof_digest}"
                    for outcome in outcomes
                ),
                *deploy_evidence,
            ]
        )
        checks = [
            "wb_core_orchestration_enforcement_enabled",
            "wb_core_canonical_queue_read",
            "wb_core_exact_admission_proved",
            "wb_core_pr_merge_identity_proved",
            "wb_core_actions_terminal_proof_matched",
        ]
        if passport.contour == "release:production":
            checks.append("wb_core_hosted_release_identity_matched")
        observed_at = datetime.fromtimestamp(
            float(self.clock()), tz=timezone.utc
        ).isoformat().replace("+00:00", "Z")
        return IndependentContourProof(
            target=WB_CORE_REPOSITORY,
            task_id=terminal.task_id,
            workstream_id=terminal.workstream_id,
            task_revision=terminal.task_revision,
            workstream_revision=terminal.workstream_revision,
            contour=terminal.closure_kind,
            terminal_digest=terminal_digest,
            source="github_release_train_readback",
            passed=True,
            checks=tuple(checks),
            evidence=evidence,
            observed_at=observed_at,
        )


def wb_core_release_request_from_mapping(value: Mapping[str, Any]) -> WbCoreReleaseRequest:
    """Strict private-runtime decoder for one immutable target request."""

    if not isinstance(value, Mapping) or set(value) != set(WbCoreReleaseRequest.__dataclass_fields__):
        raise ValueError("wb-core release request fields are invalid")
    raw = dict(value)
    binding = raw.get("admission_binding")
    if binding is not None:
        raw["admission_binding"] = wb_core_admission_binding_from_mapping(binding)
    return WbCoreReleaseRequest(**raw)


def wb_core_admission_binding_from_mapping(
    value: Mapping[str, Any],
) -> WbCoreAdmissionBinding:
    """Strict decoder for one target-owned immutable admission proof."""

    if not isinstance(value, Mapping) or set(value) != set(
        WbCoreAdmissionBinding.__dataclass_fields__
    ):
        raise ValueError("wb-core admission binding fields are invalid")
    binding = WbCoreAdmissionBinding(**dict(value))
    if asdict(binding) != dict(value):
        raise ValueError("wb-core admission binding is not canonical")
    return binding


def wb_core_release_outcome_from_mapping(value: Mapping[str, Any]) -> WbCoreReleaseOutcome:
    """Strict durable decoder and round-trip check for one adapter outcome."""

    if not isinstance(value, Mapping) or set(value) != set(WbCoreReleaseOutcome.__dataclass_fields__):
        raise ValueError("wb-core release outcome fields are invalid")
    raw = dict(value)
    raw["evidence"] = tuple(raw["evidence"])
    binding = raw.get("admission_binding")
    if binding is not None:
        raw["admission_binding"] = wb_core_admission_binding_from_mapping(binding)
    outcome = WbCoreReleaseOutcome(**raw)
    if outcome.to_mapping() != dict(value):
        raise ValueError("wb-core release outcome is not canonical")
    return outcome


def wb_core_lane_release_request_from_mapping(
    value: Mapping[str, Any],
) -> WbCoreLaneReleaseRequest:
    """Strict private-runtime decoder for task-level lane authorization."""

    if not isinstance(value, Mapping) or set(value) != set(
        WbCoreLaneReleaseRequest.__dataclass_fields__
    ):
        raise ValueError("wb-core lane-release request fields are invalid")
    return WbCoreLaneReleaseRequest(**dict(value))


def wb_core_lane_release_outcome_from_mapping(
    value: Mapping[str, Any],
) -> WbCoreLaneReleaseOutcome:
    """Strict durable decoder for one target lane-release observation."""

    if not isinstance(value, Mapping) or set(value) != set(
        WbCoreLaneReleaseOutcome.__dataclass_fields__
    ):
        raise ValueError("wb-core lane-release outcome fields are invalid")
    raw = dict(value)
    raw["evidence"] = tuple(raw["evidence"])
    outcome = WbCoreLaneReleaseOutcome(**raw)
    if outcome.to_mapping() != dict(value):
        raise ValueError("wb-core lane-release outcome is not canonical")
    return outcome


def wb_core_runtime_result(
    outcome: WbCoreReleaseOutcome,
    *,
    completed_at: str | None = None,
    observed_at: str | None = None,
) -> dict[str, Any]:
    """Map a terminal outcome to the existing receipt, otherwise to observation.

    The Supervisor must durably requeue nonterminal observations without
    charging the incident budget. ``failed`` remains a causal failure and
    ``readmission_required`` asks the internal resolver for the observed new
    head; neither is presented as a passed release receipt.
    """

    if not isinstance(outcome, WbCoreReleaseOutcome):
        raise ValueError("wb-core runtime result requires a typed outcome")
    if outcome.status == "failed":
        # A target invariant/enforcement failure is causal incident input.  It
        # must never be persisted as an ordinary polling observation.
        raise WbCoreReleaseAdapterError(outcome.reason_code)
    timestamp = observed_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    _rfc3339(timestamp)
    if outcome.status != "terminal":
        retry_after = (
            None
            if outcome.status == "readmission_required"
            else outcome.next_poll_after_seconds
        )
        if outcome.status != "readmission_required" and retry_after is None:
            raise ValueError("nonterminal wb-core outcome lacks a durable polling delay")
        return {
            "schema": WB_CORE_RUNTIME_OBSERVATION_SCHEMA,
            "status": outcome.status,
            "reason_code": outcome.reason_code,
            "candidate_id": outcome.candidate_id,
            "task_id": outcome.task_id,
            "workstream_id": outcome.workstream_id,
            "task_revision": outcome.task_revision,
            "workstream_revision": outcome.workstream_revision,
            "expected_head_sha": outcome.expected_head_sha,
            "observed_head_sha": outcome.observed_head_sha,
            "retry_after_seconds": retry_after,
            "observed_at": timestamp,
            "evidence": list(outcome.evidence),
            # Preserve the target-owned admission proof once it exists.  A
            # parked local task may need to release an already-owned target
            # lane before a final ReleaseClosureManifest can legitimately be
            # created.  The binding is sanitized, immutable and self-checking;
            # it contains no provider payload or credential material.
            "admission_binding": (
                asdict(outcome.admission_binding)
                if outcome.admission_binding is not None
                else None
            ),
        }
    if (
        outcome.merge_sha is None
        or outcome.terminal_proof_digest is None
        or outcome.admission_binding is None
    ):
        raise ValueError("terminal wb-core outcome is incomplete")
    timestamp = completed_at or timestamp
    _rfc3339(timestamp)
    return {
        "schema": "dev-control-plane/release-action-receipt/v2",
        "status": "passed",
        "candidate_id": outcome.candidate_id,
        "task_id": outcome.task_id,
        "workstream_id": outcome.workstream_id,
        "task_revision": outcome.task_revision,
        "workstream_revision": outcome.workstream_revision,
        "pr_head_sha": outcome.expected_head_sha,
        "pr_url": outcome.pr_url,
        "merge_sha": outcome.merge_sha,
        "contour": outcome.contour,
        "deploy_identity": outcome.hosted_deploy_identity,
        "verification_identity": (
            "wb-core-actions-terminal-proof:sha256:" + outcome.terminal_proof_digest
        ),
        "admission_binding": asdict(outcome.admission_binding),
        "completed_at": timestamp,
    }


def _rfc3339(value: str) -> None:
    if not isinstance(value, str) or not value or len(value) > 100:
        raise ValueError("timestamp is invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("timestamp is invalid") from exc
    if parsed.tzinfo is None:
        raise ValueError("timestamp is missing a timezone")


def _machine(label: str, value: Any) -> str:
    if not isinstance(value, str) or not _MACHINE_RE.fullmatch(value):
        raise ValueError(f"{label} must be a bounded machine identity")
    return value


def _stable_strings(label: str, values: Sequence[str], *, maximum: int) -> tuple[str, ...]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes, bytearray)):
        raise ValueError(f"{label} must be an array")
    result: list[str] = []
    for value in values:
        if (
            not isinstance(value, str)
            or not value
            or value != value.strip()
            or len(value) > 1_000
            or any(ord(character) < 32 for character in value)
        ):
            raise ValueError(f"{label} contains invalid text")
        if value not in result:
            result.append(value)
        if len(result) > maximum:
            raise ValueError(f"{label} is oversized")
    return tuple(result)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_json(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
