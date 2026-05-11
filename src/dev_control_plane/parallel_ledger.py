"""Parallel task ledger MVP for target-scoped promotion orchestration.

The ledger is a small machine-readable state layer.  It does not start
managed runs, sprint runs or production-lane work; callers bind already
created run ids and move records through explicit transitions.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence
import uuid

from dev_control_plane.state_layout import ControlPlaneStateLayout, StateLayoutError, safe_state_component


ParallelTaskStatus = Literal[
    "submitted",
    "managed_run_running",
    "verifier_passed",
    "auto_promoting_first",
    "production_lane_running",
    "production_complete",
    "frozen_base_stale",
    "refresh_required",
    "promotion_queued",
    "blocked",
    "failed",
]
ParallelRunKind = Literal["managed_clone", "production_lane"]
CandidateStatus = Literal["eligible", "promotion_queued", "auto_promoting_first", "frozen", "blocked"]
PromotionEpochStatus = Literal["open", "auto_promoting_first", "production_lane_running", "production_complete"]

PARALLEL_LEDGER_COLLECTION = "parallel_task_ledger"
PARALLEL_LEDGER_SCHEMA_VERSION = 1
PARALLEL_PING_PONG_ENABLED = False
PARALLEL_PING_PONG_STATUS = "frozen"
TERMINAL_TASK_STATUSES = {"production_complete", "blocked", "failed"}
FROZEN_TASK_STATUSES = {"frozen_base_stale", "refresh_required"}


class ParallelLedgerError(ValueError):
    """Raised when a parallel ledger transition is invalid."""


class ParallelLedgerPolicyError(ParallelLedgerError):
    """Raised when a transition requires explicit policy approval."""


@dataclass(frozen=True)
class ParallelRun:
    run_id: str
    task_id: str
    target_id: str
    promotion_epoch: str
    run_kind: ParallelRunKind
    execution_mode: str
    status: str
    bound_at: str


@dataclass(frozen=True)
class PromotionCandidate:
    task_id: str
    target_id: str
    promotion_epoch: str
    managed_run_id: str
    status: CandidateStatus
    verifier_passed_at: str
    selected_at: str | None = None
    blocker: str | None = None


@dataclass(frozen=True)
class TaskRecord:
    task_id: str
    target_id: str
    promotion_epoch: str
    source: str
    task_text: str
    status: ParallelTaskStatus
    submitted_at: str
    updated_at: str
    batch_id: str | None = None
    release_group: str | None = None
    chat_id: str | None = None
    source_id: str | None = None
    source_chat: str | None = None
    source_tool: str | None = None
    submitted_by: str | None = None
    idempotency_key: str | None = None
    managed_run_id: str | None = None
    production_run_id: str | None = None
    verifier_passed_at: str | None = None
    changed_files: Sequence[str] = field(default_factory=tuple)
    verifier_summary: Mapping[str, Any] = field(default_factory=dict)
    refresh_required: bool = False
    frozen_by_task_id: str | None = None
    blocker: str | None = None
    parallel_ping_pong_enabled: bool = PARALLEL_PING_PONG_ENABLED

    def __post_init__(self) -> None:
        object.__setattr__(self, "changed_files", tuple(str(item) for item in self.changed_files))
        object.__setattr__(self, "verifier_summary", dict(self.verifier_summary))


@dataclass(frozen=True)
class TargetPromotionState:
    target_id: str
    promotion_epoch: str
    status: PromotionEpochStatus
    created_at: str
    updated_at: str
    auto_promote_first_policy_enabled: bool = False
    first_candidate_task_id: str | None = None
    production_run_id: str | None = None
    completed_task_id: str | None = None
    completed_at: str | None = None
    frozen_task_ids: Sequence[str] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "frozen_task_ids", tuple(str(item) for item in self.frozen_task_ids))


@dataclass(frozen=True)
class ParallelLedgerSnapshot:
    schema_version: int
    parallel_ping_pong_enabled: bool
    parallel_ping_pong_status: str
    tasks: Mapping[str, TaskRecord]
    runs: Mapping[str, ParallelRun]
    candidates: Mapping[str, PromotionCandidate]
    promotion_states: Mapping[str, TargetPromotionState]


class ParallelTaskLedger:
    """File-backed JSON ledger for parallel task lifecycle state."""

    def __init__(self, path: Path) -> None:
        self.path = path

    @classmethod
    def from_state_dir(cls, state_dir: Path | str | None = None) -> "ParallelTaskLedger":
        layout = ControlPlaneStateLayout.from_path(state_dir)
        layout.ensure_base_dirs()
        return cls(layout.collection_path(PARALLEL_LEDGER_COLLECTION))

    def snapshot(self) -> ParallelLedgerSnapshot:
        payload = self._read_payload()
        return ParallelLedgerSnapshot(
            schema_version=int(payload.get("schema_version") or PARALLEL_LEDGER_SCHEMA_VERSION),
            parallel_ping_pong_enabled=bool(payload.get("parallel_ping_pong_enabled", PARALLEL_PING_PONG_ENABLED)),
            parallel_ping_pong_status=str(payload.get("parallel_ping_pong_status") or PARALLEL_PING_PONG_STATUS),
            tasks={key: _task_from_dict(value) for key, value in _mapping(payload.get("tasks")).items()},
            runs={key: _run_from_dict(value) for key, value in _mapping(payload.get("runs")).items()},
            candidates={key: _candidate_from_dict(value) for key, value in _mapping(payload.get("candidates")).items()},
            promotion_states={
                key: _promotion_state_from_dict(value)
                for key, value in _mapping(payload.get("promotion_states")).items()
            },
        )

    def submit_task(
        self,
        *,
        target_id: str,
        task_text: str,
        source: str,
        chat_id: str | None = None,
        source_id: str | None = None,
        source_chat: str | None = None,
        source_tool: str | None = None,
        submitted_by: str | None = None,
        batch_id: str | None = None,
        release_group: str | None = None,
        promotion_epoch: str | None = None,
        idempotency_key: str | None = None,
        task_id: str | None = None,
        now: str | None = None,
    ) -> TaskRecord:
        payload = self._read_payload()
        timestamp = now or _now_utc()
        target = _safe_id(target_id, "target_id")
        epoch = promotion_epoch or _current_or_new_epoch(payload, target, timestamp)
        epoch = _safe_id(epoch, "promotion_epoch")
        source_value = _required_text(source, "source")
        text_value = _required_text(task_text, "task_text")
        normalized_idempotency = _optional_text(idempotency_key)
        if normalized_idempotency:
            existing = _find_idempotent_task(payload, target, epoch, normalized_idempotency)
            if existing is not None:
                return _task_from_dict(existing)

        record_id = _safe_id(task_id or _new_task_id(timestamp), "task_id")
        tasks = _mapping(payload.setdefault("tasks", {}))
        if record_id in tasks:
            raise ParallelLedgerError(f"task already exists: {record_id}")
        task = TaskRecord(
            task_id=record_id,
            target_id=target,
            promotion_epoch=epoch,
            source=source_value,
            chat_id=_optional_text(chat_id) or _optional_text(source_chat),
            source_id=_optional_text(source_id),
            source_chat=_optional_text(source_chat),
            source_tool=_optional_text(source_tool),
            submitted_by=_optional_text(submitted_by),
            batch_id=_optional_text(batch_id),
            release_group=_optional_text(release_group),
            task_text=text_value,
            idempotency_key=normalized_idempotency,
            status="submitted",
            submitted_at=timestamp,
            updated_at=timestamp,
        )
        tasks[record_id] = _json_ready(asdict(task))
        _ensure_epoch_state(payload, target, epoch, timestamp)
        self._write_payload(payload)
        return task

    def get_task(self, task_id: str) -> TaskRecord:
        return self._get_task_from_payload(self._read_payload(), task_id)

    def bind_managed_run(self, task_id: str, run_id: str, *, now: str | None = None) -> TaskRecord:
        payload = self._read_payload()
        timestamp = now or _now_utc()
        task = self._get_task_from_payload(payload, task_id)
        _ensure_not_frozen_for_promotion(task)
        if task.status not in {"submitted", "managed_run_running"}:
            raise ParallelLedgerError(f"managed run can be bound only from submitted/running state: {task.status}")
        normalized_run_id = _safe_id(run_id, "run_id")
        runs = _mapping(payload.setdefault("runs", {}))
        if normalized_run_id in runs and str(runs[normalized_run_id].get("task_id")) != task.task_id:
            raise ParallelLedgerError(f"run id is already bound to another task: {normalized_run_id}")
        updated = replace(
            task,
            status="managed_run_running",
            managed_run_id=normalized_run_id,
            updated_at=timestamp,
            blocker=None,
        )
        runs[normalized_run_id] = _json_ready(
            asdict(
                ParallelRun(
                    run_id=normalized_run_id,
                    task_id=task.task_id,
                    target_id=task.target_id,
                    promotion_epoch=task.promotion_epoch,
                    run_kind="managed_clone",
                    execution_mode="managed_clone_only",
                    status="running",
                    bound_at=timestamp,
                )
            )
        )
        _put_task(payload, updated)
        self._write_payload(payload)
        return updated

    def mark_verifier_passed(self, task_id: str, *, now: str | None = None) -> TaskRecord:
        payload = self._read_payload()
        timestamp = now or _now_utc()
        task = self._get_task_from_payload(payload, task_id)
        _ensure_not_frozen_for_promotion(task)
        if not task.managed_run_id:
            raise ParallelLedgerError("verifier_passed requires a bound managed run")
        if task.status not in {"managed_run_running", "verifier_passed", "promotion_queued"}:
            raise ParallelLedgerError(f"verifier can pass only after managed run starts: {task.status}")
        updated = replace(
            task,
            status="verifier_passed",
            verifier_passed_at=timestamp,
            updated_at=timestamp,
            blocker=None,
        )
        candidates = _mapping(payload.setdefault("candidates", {}))
        candidates[task.task_id] = _json_ready(
            asdict(
                PromotionCandidate(
                    task_id=task.task_id,
                    target_id=task.target_id,
                    promotion_epoch=task.promotion_epoch,
                    managed_run_id=task.managed_run_id,
                    status="eligible",
                    verifier_passed_at=timestamp,
                )
            )
        )
        _put_task(payload, updated)
        self._write_payload(payload)
        return updated

    def reconcile_managed_run_result(
        self,
        task_id: str,
        *,
        run_status: str,
        verifier_status: str | None = None,
        changed_files: Sequence[str] = (),
        verifier_summary: Mapping[str, Any] | None = None,
        blocker: str | None = None,
        now: str | None = None,
    ) -> TaskRecord:
        payload = self._read_payload()
        timestamp = now or _now_utc()
        task = self._get_task_from_payload(payload, task_id)
        normalized_status = str(run_status or "").strip().lower()
        normalized_verifier = str(verifier_status or "").strip().lower()
        files = _changed_files(changed_files)
        summary = _summary_mapping(verifier_summary)
        if files:
            summary.setdefault("changed_files_count", len(files))
        if normalized_verifier:
            summary.setdefault("verifier_status", normalized_verifier)

        if normalized_status in {"running", "managed_run_running", "running_codex", "queued"}:
            if not task.managed_run_id:
                raise ParallelLedgerError("running reconciliation requires a bound managed run")
            updated = replace(
                task,
                status="managed_run_running",
                changed_files=files,
                verifier_summary=summary,
                updated_at=timestamp,
                blocker=None,
            )
            _put_task(payload, updated)
            self._write_payload(payload)
            return updated

        if normalized_status in {"passed", "completed", "verifier_passed"} and normalized_verifier in {"", "passed", "ok", "success", "verifier_passed"}:
            if not task.managed_run_id:
                raise ParallelLedgerError("verifier_passed reconciliation requires a bound managed run")
            if task.refresh_required or task.status in FROZEN_TASK_STATUSES:
                updated = replace(
                    task,
                    changed_files=files,
                    verifier_summary=summary,
                    updated_at=timestamp,
                    blocker=task.blocker or "managed run passed after base changed; refresh required before promotion",
                )
                _put_task(payload, updated)
                self._write_payload(payload)
                return updated
            if task.status not in {"managed_run_running", "verifier_passed", "promotion_queued"}:
                raise ParallelLedgerError(f"verifier can pass only after managed run starts: {task.status}")
            updated = replace(
                task,
                status="verifier_passed",
                verifier_passed_at=timestamp,
                changed_files=files,
                verifier_summary=summary,
                updated_at=timestamp,
                blocker=None,
            )
            candidates = _mapping(payload.setdefault("candidates", {}))
            candidates[task.task_id] = _json_ready(
                asdict(
                    PromotionCandidate(
                        task_id=task.task_id,
                        target_id=task.target_id,
                        promotion_epoch=task.promotion_epoch,
                        managed_run_id=task.managed_run_id,
                        status="eligible",
                        verifier_passed_at=timestamp,
                    )
                )
            )
            _put_task(payload, updated)
            self._write_payload(payload)
            return updated

        if normalized_status in {"blocked", "cancelled", "stale_timeout", "stale_lost_process"}:
            updated = replace(
                task,
                status="blocked",
                changed_files=files,
                verifier_summary=summary,
                blocker=_optional_text(blocker) or f"managed run status: {normalized_status}",
                updated_at=timestamp,
            )
            _put_task(payload, updated)
            _mapping(payload.setdefault("candidates", {})).pop(updated.task_id, None)
            self._write_payload(payload)
            return updated

        if normalized_status in {"failed", "error"} or normalized_verifier in {"failed", "error"}:
            updated = replace(
                task,
                status="failed",
                changed_files=files,
                verifier_summary=summary,
                blocker=_optional_text(blocker) or "managed run failed",
                updated_at=timestamp,
            )
            _put_task(payload, updated)
            _mapping(payload.setdefault("candidates", {})).pop(updated.task_id, None)
            self._write_payload(payload)
            return updated

        raise ParallelLedgerError(f"unsupported managed run status for reconciliation: {run_status}")

    def select_first_finished_eligible_candidate(
        self,
        *,
        target_id: str,
        promotion_epoch: str | None = None,
    ) -> PromotionCandidate | None:
        snapshot = self.snapshot()
        target = _safe_id(target_id, "target_id")
        epoch = promotion_epoch or _active_epoch_for_target(snapshot, target)
        if epoch is None:
            return None
        candidates = [
            candidate
            for candidate in snapshot.candidates.values()
            if candidate.target_id == target
            and candidate.promotion_epoch == epoch
            and candidate.status in {"eligible", "promotion_queued"}
        ]
        if not candidates:
            return None
        tasks = snapshot.tasks
        return sorted(
            candidates,
            key=lambda item: (
                item.verifier_passed_at,
                tasks.get(item.task_id).submitted_at if item.task_id in tasks else "",
                item.task_id,
            ),
        )[0]

    def mark_first_candidate_auto_promoting_first(
        self,
        *,
        target_id: str,
        promotion_epoch: str | None = None,
        explicit_policy: bool = False,
        now: str | None = None,
    ) -> TaskRecord:
        payload = self._read_payload()
        timestamp = now or _now_utc()
        target = _safe_id(target_id, "target_id")
        epoch = promotion_epoch or _active_epoch_for_target_payload(payload, target)
        if epoch is None:
            raise ParallelLedgerError(f"no promotion epoch for target: {target}")
        candidate = self.select_first_finished_eligible_candidate(target_id=target, promotion_epoch=epoch)
        if candidate is None:
            raise ParallelLedgerError("no eligible promotion candidate")
        return self.mark_candidate_auto_promoting_first(
            candidate.task_id,
            explicit_policy=explicit_policy,
            now=timestamp,
        )

    def mark_candidate_auto_promoting_first(
        self,
        task_id: str,
        *,
        explicit_policy: bool = False,
        now: str | None = None,
    ) -> TaskRecord:
        payload = self._read_payload()
        timestamp = now or _now_utc()
        normalized_task_id = _safe_id(task_id, "task_id")
        candidate = _maybe_candidate(payload, normalized_task_id)
        if candidate is None:
            raise ParallelLedgerError(f"task is not a promotion candidate: {normalized_task_id}")
        task = self._get_task_from_payload(payload, candidate.task_id)
        _ensure_not_frozen_for_promotion(task)
        if not explicit_policy:
            queued = replace(
                task,
                status="promotion_queued",
                updated_at=timestamp,
                blocker="explicit auto-promote-first policy is required",
            )
            _put_task(payload, queued)
            _put_candidate(
                payload,
                replace(
                    candidate,
                    status="promotion_queued",
                    blocker="explicit auto-promote-first policy is required",
                ),
            )
            self._write_payload(payload)
            raise ParallelLedgerPolicyError("explicit auto-promote-first policy is required")
        updated = replace(task, status="auto_promoting_first", updated_at=timestamp, blocker=None)
        _put_task(payload, updated)
        _put_candidate(payload, replace(candidate, status="auto_promoting_first", selected_at=timestamp, blocker=None))
        state = _ensure_epoch_state(payload, task.target_id, task.promotion_epoch, timestamp)
        _put_epoch_state(
            payload,
            replace(
                state,
                status="auto_promoting_first",
                auto_promote_first_policy_enabled=True,
                first_candidate_task_id=task.task_id,
                updated_at=timestamp,
            ),
        )
        self._write_payload(payload)
        return updated

    def bind_production_lane_run(self, task_id: str, run_id: str, *, now: str | None = None) -> TaskRecord:
        payload = self._read_payload()
        timestamp = now or _now_utc()
        task = self._get_task_from_payload(payload, task_id)
        _ensure_not_frozen_for_promotion(task)
        if task.status != "auto_promoting_first":
            raise ParallelLedgerError(f"production lane can start only for auto_promoting_first: {task.status}")
        normalized_run_id = _safe_id(run_id, "run_id")
        updated = replace(
            task,
            status="production_lane_running",
            production_run_id=normalized_run_id,
            updated_at=timestamp,
            blocker=None,
        )
        runs = _mapping(payload.setdefault("runs", {}))
        runs[normalized_run_id] = _json_ready(
            asdict(
                ParallelRun(
                    run_id=normalized_run_id,
                    task_id=task.task_id,
                    target_id=task.target_id,
                    promotion_epoch=task.promotion_epoch,
                    run_kind="production_lane",
                    execution_mode="production_lane",
                    status="running",
                    bound_at=timestamp,
                )
            )
        )
        _put_task(payload, updated)
        state = _ensure_epoch_state(payload, task.target_id, task.promotion_epoch, timestamp)
        _put_epoch_state(
            payload,
            replace(
                state,
                status="production_lane_running",
                production_run_id=normalized_run_id,
                updated_at=timestamp,
            ),
        )
        self._write_payload(payload)
        return updated

    def mark_production_complete(
        self,
        task_id: str,
        *,
        now: str | None = None,
        freeze_siblings: bool = True,
    ) -> TaskRecord:
        payload = self._read_payload()
        timestamp = now or _now_utc()
        winner = self._get_task_from_payload(payload, task_id)
        if winner.status not in {"production_lane_running", "auto_promoting_first"}:
            raise ParallelLedgerError(f"production_complete requires selected production candidate: {winner.status}")
        completed = replace(winner, status="production_complete", updated_at=timestamp, blocker=None)
        _put_task(payload, completed)
        _mapping(payload.setdefault("candidates", {})).pop(completed.task_id, None)
        frozen_ids: list[str] = []
        tasks = _mapping(payload.setdefault("tasks", {}))
        if freeze_siblings:
            for raw_task_id, raw_task in list(tasks.items()):
                task = _task_from_dict(raw_task)
                if task.task_id == completed.task_id:
                    continue
                if task.target_id != completed.target_id or task.promotion_epoch != completed.promotion_epoch:
                    continue
                if task.status in TERMINAL_TASK_STATUSES:
                    continue
                stale_status: ParallelTaskStatus = (
                    "refresh_required" if task.status in {"verifier_passed", "promotion_queued"} else "frozen_base_stale"
                )
                frozen = replace(
                    task,
                    status=stale_status,
                    refresh_required=True,
                    frozen_by_task_id=completed.task_id,
                    blocker=f"base stale after production_complete of {completed.task_id}; refresh required",
                    updated_at=timestamp,
                )
                _put_task(payload, frozen)
                frozen_ids.append(task.task_id)
                candidate = _maybe_candidate(payload, task.task_id)
                if candidate is not None:
                    _put_candidate(
                        payload,
                        replace(
                            candidate,
                            status="frozen",
                            blocker=f"base stale after production_complete of {completed.task_id}; refresh required",
                        ),
                    )
        state = _ensure_epoch_state(payload, completed.target_id, completed.promotion_epoch, timestamp)
        _put_epoch_state(
            payload,
            replace(
                state,
                status="production_complete",
                completed_task_id=completed.task_id,
                completed_at=timestamp,
                frozen_task_ids=tuple(sorted(set((*state.frozen_task_ids, *frozen_ids)))),
                updated_at=timestamp,
            ),
        )
        self._write_payload(payload)
        return completed

    def ensure_promotable(self, task_id: str) -> TaskRecord:
        task = self._get_task_from_payload(self._read_payload(), task_id)
        _ensure_not_frozen_for_promotion(task)
        if task.status not in {"verifier_passed", "promotion_queued", "auto_promoting_first"}:
            raise ParallelLedgerError(f"task is not in a promotable state: {task.status}")
        return task

    def mark_blocked(self, task_id: str, blocker: str, *, now: str | None = None) -> TaskRecord:
        payload = self._read_payload()
        timestamp = now or _now_utc()
        task = self._get_task_from_payload(payload, task_id)
        updated = replace(task, status="blocked", blocker=_required_text(blocker, "blocker"), updated_at=timestamp)
        _put_task(payload, updated)
        _mapping(payload.setdefault("candidates", {})).pop(updated.task_id, None)
        self._write_payload(payload)
        return updated

    def mark_failed(self, task_id: str, blocker: str, *, now: str | None = None) -> TaskRecord:
        payload = self._read_payload()
        timestamp = now or _now_utc()
        task = self._get_task_from_payload(payload, task_id)
        updated = replace(task, status="failed", blocker=_required_text(blocker, "blocker"), updated_at=timestamp)
        _put_task(payload, updated)
        _mapping(payload.setdefault("candidates", {})).pop(updated.task_id, None)
        self._write_payload(payload)
        return updated

    def list_tasks(
        self,
        *,
        target_id: str | None = None,
        promotion_epoch: str | None = None,
    ) -> tuple[TaskRecord, ...]:
        snapshot = self.snapshot()
        target = _safe_id(target_id, "target_id") if target_id else None
        epoch = _safe_id(promotion_epoch, "promotion_epoch") if promotion_epoch else None
        return tuple(
            sorted(
                (
                    task
                    for task in snapshot.tasks.values()
                    if (target is None or task.target_id == target)
                    and (epoch is None or task.promotion_epoch == epoch)
                ),
                key=lambda item: (item.target_id, item.promotion_epoch, item.submitted_at, item.task_id),
            )
        )

    def status(self) -> dict[str, Any]:
        snapshot = self.snapshot()
        return {
            "schema_version": snapshot.schema_version,
            "task_count": len(snapshot.tasks),
            "run_binding_count": len(snapshot.runs),
            "candidate_count": len(snapshot.candidates),
            "promotion_epoch_count": len(snapshot.promotion_states),
            "parallel_ping_pong_enabled": snapshot.parallel_ping_pong_enabled,
            "parallel_ping_pong_status": snapshot.parallel_ping_pong_status,
            "intake_model": "multi_source_per_target_epoch",
        }

    def target_promotion_state(
        self,
        target_id: str,
        promotion_epoch: str | None = None,
    ) -> TargetPromotionState | None:
        snapshot = self.snapshot()
        target = _safe_id(target_id, "target_id")
        epoch = _safe_id(promotion_epoch, "promotion_epoch") if promotion_epoch else _active_epoch_for_target(snapshot, target)
        if epoch is None:
            return None
        return snapshot.promotion_states.get(_epoch_key(target, epoch))

    def list_candidates(
        self,
        *,
        target_id: str | None = None,
        promotion_epoch: str | None = None,
    ) -> tuple[PromotionCandidate, ...]:
        snapshot = self.snapshot()
        target = _safe_id(target_id, "target_id") if target_id else None
        epoch = _safe_id(promotion_epoch, "promotion_epoch") if promotion_epoch else None
        return tuple(
            sorted(
                (
                    candidate
                    for candidate in snapshot.candidates.values()
                    if (target is None or candidate.target_id == target)
                    and (epoch is None or candidate.promotion_epoch == epoch)
                ),
                key=lambda item: (item.target_id, item.promotion_epoch, item.verifier_passed_at, item.task_id),
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return _snapshot_to_payload(self.snapshot())

    def _get_task_from_payload(self, payload: Mapping[str, Any], task_id: str) -> TaskRecord:
        normalized = _safe_id(task_id, "task_id")
        tasks = _mapping(payload.get("tasks"))
        raw = tasks.get(normalized)
        if raw is None:
            raise ParallelLedgerError(f"unknown task_id: {normalized}")
        return _task_from_dict(raw)

    def _read_payload(self) -> dict[str, Any]:
        if not self.path.exists():
            return _empty_payload()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ParallelLedgerError(f"parallel ledger is not valid JSON: {self.path}") from exc
        if not isinstance(raw, dict):
            raise ParallelLedgerError("parallel ledger root must be an object")
        payload = _empty_payload()
        payload.update(raw)
        payload["parallel_ping_pong_enabled"] = PARALLEL_PING_PONG_ENABLED
        payload["parallel_ping_pong_status"] = PARALLEL_PING_PONG_STATUS
        return payload

    def _write_payload(self, payload: Mapping[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        normalized = _normalize_payload(payload)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(normalized, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(self.path)


def _empty_payload() -> dict[str, Any]:
    return {
        "schema_version": PARALLEL_LEDGER_SCHEMA_VERSION,
        "parallel_ping_pong_enabled": PARALLEL_PING_PONG_ENABLED,
        "parallel_ping_pong_status": PARALLEL_PING_PONG_STATUS,
        "tasks": {},
        "runs": {},
        "candidates": {},
        "promotion_states": {},
    }


def _normalize_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    normalized = _empty_payload()
    normalized["schema_version"] = int(payload.get("schema_version") or PARALLEL_LEDGER_SCHEMA_VERSION)
    normalized["tasks"] = dict(_mapping(payload.get("tasks")))
    normalized["runs"] = dict(_mapping(payload.get("runs")))
    normalized["candidates"] = dict(_mapping(payload.get("candidates")))
    normalized["promotion_states"] = dict(_mapping(payload.get("promotion_states")))
    return normalized


def _snapshot_to_payload(snapshot: ParallelLedgerSnapshot) -> dict[str, Any]:
    return {
        "schema_version": snapshot.schema_version,
        "parallel_ping_pong_enabled": snapshot.parallel_ping_pong_enabled,
        "parallel_ping_pong_status": snapshot.parallel_ping_pong_status,
        "tasks": {key: _json_ready(asdict(value)) for key, value in snapshot.tasks.items()},
        "runs": {key: _json_ready(asdict(value)) for key, value in snapshot.runs.items()},
        "candidates": {key: _json_ready(asdict(value)) for key, value in snapshot.candidates.items()},
        "promotion_states": {
            key: _json_ready(asdict(value)) for key, value in snapshot.promotion_states.items()
        },
    }


def _task_from_dict(payload: Mapping[str, Any]) -> TaskRecord:
    return TaskRecord(
        task_id=_safe_id(payload.get("task_id"), "task_id"),
        target_id=_safe_id(payload.get("target_id"), "target_id"),
        promotion_epoch=_safe_id(payload.get("promotion_epoch"), "promotion_epoch"),
        source=_required_text(payload.get("source"), "source"),
        chat_id=_optional_text(payload.get("chat_id")),
        source_id=_optional_text(payload.get("source_id")),
        source_chat=_optional_text(payload.get("source_chat")),
        source_tool=_optional_text(payload.get("source_tool")),
        submitted_by=_optional_text(payload.get("submitted_by")),
        batch_id=_optional_text(payload.get("batch_id")),
        release_group=_optional_text(payload.get("release_group")),
        task_text=_required_text(payload.get("task_text"), "task_text"),
        idempotency_key=_optional_text(payload.get("idempotency_key")),
        status=_status(payload.get("status")),
        submitted_at=_required_text(payload.get("submitted_at"), "submitted_at"),
        updated_at=_required_text(payload.get("updated_at"), "updated_at"),
        managed_run_id=_optional_text(payload.get("managed_run_id")),
        production_run_id=_optional_text(payload.get("production_run_id")),
        verifier_passed_at=_optional_text(payload.get("verifier_passed_at")),
        changed_files=_changed_files(_sequence(payload.get("changed_files"))),
        verifier_summary=_summary_mapping(payload.get("verifier_summary") if isinstance(payload.get("verifier_summary"), Mapping) else {}),
        refresh_required=bool(payload.get("refresh_required", False)),
        frozen_by_task_id=_optional_text(payload.get("frozen_by_task_id")),
        blocker=_optional_text(payload.get("blocker")),
        parallel_ping_pong_enabled=False,
    )


def task_record_summary(task: TaskRecord) -> dict[str, Any]:
    return {
        "task_id": task.task_id,
        "task_title": _task_title(task.task_text),
        "target_id": task.target_id,
        "status": task.status,
        "source": task.source,
        "source_id": task.source_id,
        "source_chat": task.source_chat,
        "source_tool": task.source_tool,
        "submitted_by": task.submitted_by,
        "batch_id": task.batch_id,
        "release_group": task.release_group,
        "promotion_epoch": task.promotion_epoch,
        "managed_run_id": task.managed_run_id,
        "production_run_id": task.production_run_id,
        "run_binding": {
            "managed_run_id": task.managed_run_id,
            "production_run_id": task.production_run_id,
        },
        "verifier_passed_at": task.verifier_passed_at,
        "changed_files": list(task.changed_files),
        "verifier_summary": dict(task.verifier_summary),
        "refresh_required": task.refresh_required,
        "frozen_by_task_id": task.frozen_by_task_id,
        "blocker": task.blocker,
        "created_at": task.submitted_at,
        "submitted_at": task.submitted_at,
        "updated_at": task.updated_at,
        "parallel_ping_pong_enabled": task.parallel_ping_pong_enabled,
    }


def _task_title(task_text: str) -> str:
    text = " ".join(str(task_text or "").replace("\n", " ").split())
    for prefix in ("Класс задачи:", "Задача:", "Task:", "Goal:", "Operator note:"):
        if text.startswith(prefix):
            text = text[len(prefix) :].strip()
    stopwords = {"и", "или", "в", "на", "для", "по", "and", "or", "the", "a", "to", "of", "for"}
    words = [
        word.strip(".,;:!?()[]{}\"'`")
        for word in text.split()
        if word.strip(".,;:!?()[]{}\"'`") and word.strip(".,;:!?()[]{}\"'`").lower() not in stopwords
    ]
    if not words:
        return "Задача"
    return " ".join(words[:5])[:64]


def promotion_state_summary(
    state: TargetPromotionState | None,
    *,
    target_id: str,
    promotion_epoch: str | None = None,
) -> dict[str, Any]:
    if state is None:
        return {
            "status": "not_found",
            "target_id": target_id,
            "promotion_epoch": promotion_epoch,
            "blocker": "promotion state not found",
        }
    return {
        "status": "ok",
        "target_id": state.target_id,
        "promotion_epoch": state.promotion_epoch,
        "promotion_status": state.status,
        "auto_promote_first_policy_enabled": state.auto_promote_first_policy_enabled,
        "first_candidate_task_id": state.first_candidate_task_id,
        "production_run_id": state.production_run_id,
        "completed_task_id": state.completed_task_id,
        "completed_at": state.completed_at,
        "frozen_task_ids": list(state.frozen_task_ids),
        "created_at": state.created_at,
        "updated_at": state.updated_at,
        "parallel_ping_pong_enabled": PARALLEL_PING_PONG_ENABLED,
    }


def _run_from_dict(payload: Mapping[str, Any]) -> ParallelRun:
    run_kind = str(payload.get("run_kind") or "")
    if run_kind not in {"managed_clone", "production_lane"}:
        raise ParallelLedgerError(f"invalid run_kind: {run_kind}")
    return ParallelRun(
        run_id=_safe_id(payload.get("run_id"), "run_id"),
        task_id=_safe_id(payload.get("task_id"), "task_id"),
        target_id=_safe_id(payload.get("target_id"), "target_id"),
        promotion_epoch=_safe_id(payload.get("promotion_epoch"), "promotion_epoch"),
        run_kind=run_kind,  # type: ignore[arg-type]
        execution_mode=_required_text(payload.get("execution_mode"), "execution_mode"),
        status=_required_text(payload.get("status"), "status"),
        bound_at=_required_text(payload.get("bound_at"), "bound_at"),
    )


def _candidate_from_dict(payload: Mapping[str, Any]) -> PromotionCandidate:
    status = str(payload.get("status") or "")
    if status not in {"eligible", "promotion_queued", "auto_promoting_first", "frozen", "blocked"}:
        raise ParallelLedgerError(f"invalid candidate status: {status}")
    return PromotionCandidate(
        task_id=_safe_id(payload.get("task_id"), "task_id"),
        target_id=_safe_id(payload.get("target_id"), "target_id"),
        promotion_epoch=_safe_id(payload.get("promotion_epoch"), "promotion_epoch"),
        managed_run_id=_safe_id(payload.get("managed_run_id"), "managed_run_id"),
        status=status,  # type: ignore[arg-type]
        verifier_passed_at=_required_text(payload.get("verifier_passed_at"), "verifier_passed_at"),
        selected_at=_optional_text(payload.get("selected_at")),
        blocker=_optional_text(payload.get("blocker")),
    )


def _promotion_state_from_dict(payload: Mapping[str, Any]) -> TargetPromotionState:
    status = str(payload.get("status") or "")
    if status not in {"open", "auto_promoting_first", "production_lane_running", "production_complete"}:
        raise ParallelLedgerError(f"invalid promotion epoch status: {status}")
    return TargetPromotionState(
        target_id=_safe_id(payload.get("target_id"), "target_id"),
        promotion_epoch=_safe_id(payload.get("promotion_epoch"), "promotion_epoch"),
        status=status,  # type: ignore[arg-type]
        created_at=_required_text(payload.get("created_at"), "created_at"),
        updated_at=_required_text(payload.get("updated_at"), "updated_at"),
        auto_promote_first_policy_enabled=bool(payload.get("auto_promote_first_policy_enabled", False)),
        first_candidate_task_id=_optional_text(payload.get("first_candidate_task_id")),
        production_run_id=_optional_text(payload.get("production_run_id")),
        completed_task_id=_optional_text(payload.get("completed_task_id")),
        completed_at=_optional_text(payload.get("completed_at")),
        frozen_task_ids=tuple(str(item) for item in _sequence(payload.get("frozen_task_ids"))),
    )


def _current_or_new_epoch(payload: Mapping[str, Any], target_id: str, timestamp: str) -> str:
    existing = _active_epoch_for_target_payload(payload, target_id)
    if existing:
        return existing
    return _safe_id(f"epoch-{timestamp.replace(':', '').replace('-', '')}-{uuid.uuid4().hex[:8]}", "promotion_epoch")


def _active_epoch_for_target(snapshot: ParallelLedgerSnapshot, target_id: str) -> str | None:
    states = [
        state
        for state in snapshot.promotion_states.values()
        if state.target_id == target_id and state.status != "production_complete"
    ]
    if not states:
        return None
    return sorted(states, key=lambda item: (item.updated_at, item.promotion_epoch))[-1].promotion_epoch


def _active_epoch_for_target_payload(payload: Mapping[str, Any], target_id: str) -> str | None:
    states = [
        _promotion_state_from_dict(raw)
        for raw in _mapping(payload.get("promotion_states")).values()
        if str(raw.get("target_id") or "") == target_id and str(raw.get("status") or "") != "production_complete"
    ]
    if not states:
        return None
    return sorted(states, key=lambda item: (item.updated_at, item.promotion_epoch))[-1].promotion_epoch


def _ensure_epoch_state(
    payload: Mapping[str, Any],
    target_id: str,
    promotion_epoch: str,
    timestamp: str,
) -> TargetPromotionState:
    states = _mapping(payload.setdefault("promotion_states", {}))  # type: ignore[attr-defined]
    key = _epoch_key(target_id, promotion_epoch)
    if key in states:
        return _promotion_state_from_dict(states[key])
    state = TargetPromotionState(
        target_id=target_id,
        promotion_epoch=promotion_epoch,
        status="open",
        created_at=timestamp,
        updated_at=timestamp,
    )
    states[key] = _json_ready(asdict(state))
    return state


def _put_epoch_state(payload: Mapping[str, Any], state: TargetPromotionState) -> None:
    states = _mapping(payload.setdefault("promotion_states", {}))  # type: ignore[attr-defined]
    states[_epoch_key(state.target_id, state.promotion_epoch)] = _json_ready(asdict(state))


def _put_task(payload: Mapping[str, Any], task: TaskRecord) -> None:
    tasks = _mapping(payload.setdefault("tasks", {}))  # type: ignore[attr-defined]
    tasks[task.task_id] = _json_ready(asdict(task))


def _put_candidate(payload: Mapping[str, Any], candidate: PromotionCandidate) -> None:
    candidates = _mapping(payload.setdefault("candidates", {}))  # type: ignore[attr-defined]
    candidates[candidate.task_id] = _json_ready(asdict(candidate))


def _maybe_candidate(payload: Mapping[str, Any], task_id: str) -> PromotionCandidate | None:
    raw = _mapping(payload.get("candidates")).get(task_id)
    return _candidate_from_dict(raw) if raw is not None else None


def _find_idempotent_task(
    payload: Mapping[str, Any],
    target_id: str,
    promotion_epoch: str,
    idempotency_key: str,
) -> Mapping[str, Any] | None:
    for raw in _mapping(payload.get("tasks")).values():
        if (
            str(raw.get("target_id") or "") == target_id
            and str(raw.get("promotion_epoch") or "") == promotion_epoch
            and str(raw.get("idempotency_key") or "") == idempotency_key
        ):
            return raw
    return None


def _ensure_not_frozen_for_promotion(task: TaskRecord) -> None:
    if task.refresh_required or task.status in FROZEN_TASK_STATUSES:
        raise ParallelLedgerPolicyError(
            f"task {task.task_id} requires refresh before promotion after base changed"
        )


def _epoch_key(target_id: str, promotion_epoch: str) -> str:
    return f"{target_id}--{promotion_epoch}"


def _status(value: Any) -> ParallelTaskStatus:
    status = str(value or "")
    allowed = {
        "submitted",
        "managed_run_running",
        "verifier_passed",
        "auto_promoting_first",
        "production_lane_running",
        "production_complete",
        "frozen_base_stale",
        "refresh_required",
        "promotion_queued",
        "blocked",
        "failed",
    }
    if status not in allowed:
        raise ParallelLedgerError(f"invalid task status: {status}")
    return status  # type: ignore[return-value]


def _safe_id(value: Any, label: str) -> str:
    try:
        return safe_state_component(str(value or ""), label)
    except StateLayoutError as exc:
        raise ParallelLedgerError(str(exc)) from exc


def _required_text(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ParallelLedgerError(f"{label} must not be empty")
    return text


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _changed_files(value: Sequence[Any]) -> tuple[str, ...]:
    files: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if not text:
            continue
        files.append(text[:500])
        if len(files) >= 200:
            break
    return tuple(files)


def _summary_mapping(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, Any] = {}
    for key, item in value.items():
        text_key = str(key)[:120]
        if isinstance(item, Mapping):
            result[text_key] = _summary_mapping(item)
        elif isinstance(item, Sequence) and not isinstance(item, (str, bytes)):
            result[text_key] = [str(entry)[:500] for entry in list(item)[:100]]
        elif isinstance(item, bool) or item is None:
            result[text_key] = item
        elif isinstance(item, (int, float)):
            result[text_key] = item
        else:
            result[text_key] = str(item)[:1000]
    return result


def _mapping(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ParallelLedgerError("ledger section must be an object")
    return value


def _sequence(value: Any) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)):
        return (value,)
    if isinstance(value, Sequence):
        return tuple(value)
    return (value,)


def _json_ready(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    return value


def _new_task_id(timestamp: str) -> str:
    safe_time = timestamp.replace("-", "").replace(":", "")
    return f"pt-{safe_time}-{uuid.uuid4().hex[:12]}"


def _now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
