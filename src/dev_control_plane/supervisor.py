"""Deterministic local Supervisor v2 engine and read-only loopback status API."""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone
import hashlib
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
import threading
import time
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import urlsplit

from .orchestration_contracts import (
    Checkpoint,
    OrchestrationValidationError,
    TaskPassport,
    TerminalEvidence,
    Workstream,
    contract_to_dict,
    validate_checkpoint_binding,
    validate_terminal_binding,
    validate_workstream_against_passport,
)
from .projection_client import ProjectionPublisher, PublishResult
from .projection_store import (
    PROJECTION_CONTRACT,
    SECRET_KEY_RE,
    SECRET_VALUE_RE,
    projection_envelope_from_mapping,
)
from .release_scheduler import ReleaseCandidate, ScheduleDecision, schedule_releases
from .supervisor_registry import (
    CASConflict,
    LockConflict,
    LockGrant,
    StaleGenerationError,
    SupervisorFence,
    SupervisorRegistry,
)

SERVICE_ROLE = "local_supervisor_v2"
OWNER_ACCEPTANCE_SCHEMA = "dev-control-plane/owner-acceptance/v2"
CONTOUR_VERIFICATION_SCHEMA = "dev-control-plane/contour-verification/v2"
EXACT_OWNER_ACCEPTANCE = "Задача принята"
LOCAL_HOST = "127.0.0.1"
PROGRESS_EVENT_TYPES = ("executor_started", "checkpoint", "technical_terminal")
CANONICAL_PROGRESS = (5, 15, 25, 40, 55, 65, 72, 80, 88, 95, 100)


class SupervisorError(RuntimeError):
    """A controlled Supervisor invariant or input failure."""


@dataclass(frozen=True)
class OwnerAcceptanceReceipt:
    receipt_id: str
    task_id: str
    task_revision: int
    curator_thread_id: str
    reply: str
    created_at: str
    schema: str = OWNER_ACCEPTANCE_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != OWNER_ACCEPTANCE_SCHEMA:
            raise SupervisorError("owner acceptance schema mismatch")
        for name in ("receipt_id", "task_id", "curator_thread_id"):
            _machine(name, getattr(self, name))
        if isinstance(self.task_revision, bool) or not isinstance(self.task_revision, int) or self.task_revision < 1:
            raise SupervisorError("owner acceptance task_revision must be positive")
        if self.reply != EXACT_OWNER_ACCEPTANCE:
            raise SupervisorError(f"owner acceptance reply must be exactly {EXACT_OWNER_ACCEPTANCE!r}")
        _timestamp(self.created_at)


@dataclass(frozen=True)
class ContourVerification:
    verification_id: str
    task_id: str
    workstream_id: str
    task_revision: int
    workstream_revision: int
    contour: str
    terminal_digest: str
    source: str
    passed: bool
    checks: Sequence[str]
    evidence: Sequence[str]
    verified_at: str
    schema: str = CONTOUR_VERIFICATION_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != CONTOUR_VERIFICATION_SCHEMA:
            raise SupervisorError("contour verification schema mismatch")
        for name in ("verification_id", "task_id", "workstream_id"):
            _machine(name, getattr(self, name))
        if self.source not in {
            "github_release_train_readback",
            "diagnostic_verifier",
            "artifact_verifier",
        }:
            raise SupervisorError("contour verification source is not independently allowlisted")
        if self.contour not in {"release:done", "release:production", "diagnostic", "artifact"}:
            raise SupervisorError("contour verification contour is invalid")
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 1 for value in (self.task_revision, self.workstream_revision)):
            raise SupervisorError("contour verification revisions must be positive")
        if len(self.terminal_digest) != 64 or any(character not in "0123456789abcdef" for character in self.terminal_digest):
            raise SupervisorError("contour verification terminal_digest must be sha256")
        if self.passed is not True:
            raise SupervisorError("contour verification must independently pass")
        if not self.checks or not self.evidence:
            raise SupervisorError("contour verification requires checks and evidence")
        for name in ("checks", "evidence"):
            values = tuple(getattr(self, name))
            if any(not isinstance(item, str) or not item.strip() or len(item) > 1_000 for item in values):
                raise SupervisorError(f"contour verification {name} contains invalid evidence")
            object.__setattr__(self, name, values)
        _timestamp(self.verified_at)


@dataclass(frozen=True)
class TickResult:
    projection_reserved: bool
    projection_event_id: str | None
    publish_results: tuple[PublishResult, ...]


class SupervisorEngine:
    """One deterministic engine backed exclusively by one fenced registry."""

    def __init__(
        self,
        registry: SupervisorRegistry,
        fence: SupervisorFence,
        *,
        supervisor_id: str,
        publisher: ProjectionPublisher | None = None,
        contour_verifier: Callable[[TaskPassport, TerminalEvidence], ContourVerification] | None = None,
        clock: Callable[[], float] = time.time,
        projection_heartbeat_seconds: float = 30.0,
    ) -> None:
        self.registry = registry
        self.fence = fence
        self.supervisor_id = _machine("supervisor_id", supervisor_id)
        self.publisher = publisher
        self.contour_verifier = contour_verifier
        self.clock = clock
        if projection_heartbeat_seconds <= 0:
            raise SupervisorError("projection heartbeat must be positive")
        self.projection_heartbeat_seconds = float(projection_heartbeat_seconds)
        self._last_tick_error: str | None = None
        self.registry.supersede_stale_projection_snapshots(self.fence)

    def renew_lease(self) -> SupervisorFence:
        self.fence = self.registry.renew_generation(self.fence)
        return self.fence

    def register(
        self,
        passport: TaskPassport,
        workstream: Workstream,
        *,
        message_id: str,
        source: str = "local-cli",
    ) -> dict[str, Any]:
        _ensure_sanitized(contract_to_dict(passport))
        _ensure_sanitized(contract_to_dict(workstream))
        validate_workstream_against_passport(workstream, passport)
        exact_executor = workstream.executor or passport.executor
        if exact_executor is None:
            raise SupervisorError("registration requires an exact workstream executor identity")
        if workstream.generation != 1:
            raise SupervisorError("initial registration requires workstream generation 1")

        existing_task = self.registry.get_task(passport.task_id)
        if existing_task is None:
            task = self.registry.create_task(passport, self.fence, idempotency_key=f"register:{message_id}")
        else:
            if existing_task.passport != contract_to_dict(passport):
                raise SupervisorError("task_id is already bound to another Passport revision")
            task = existing_task
        current_workstream = self.registry.get_workstream(workstream.workstream_id)
        if current_workstream is None:
            if workstream.revision != 1:
                raise SupervisorError("a new initial workstream must start at revision 1")
            self.registry.create_workstream(workstream, self.fence)
        elif current_workstream.contract != contract_to_dict(workstream):
            unbound = contract_to_dict(workstream)
            unbound["executor"] = None
            if (
                current_workstream.revision != workstream.revision
                or current_workstream.contract != unbound
            ):
                raise SupervisorError("workstream_id is already bound to another contract")
            self.registry.bind_initial_workstream_executor(
                workstream,
                expected_revision=current_workstream.revision,
                fence=self.fence,
            )

        executor = self.registry.current_executor(passport.task_id, workstream.workstream_id)
        if executor is None:
            executor = self.registry.register_executor(
                passport.task_id,
                workstream.workstream_id,
                exact_executor,
                expected_current_generation=0,
                checkpoint_digest=_digest_text("registration:" + passport.task_id + ":" + workstream.workstream_id),
                fence=self.fence,
            )
        elif (
            executor.thread_id,
            executor.host_id,
            executor.model,
            executor.reasoning,
        ) != (
            exact_executor.thread_id,
            exact_executor.host_id,
            exact_executor.model,
            exact_executor.reasoning,
        ):
            raise SupervisorError("registered executor identity does not match the exact Passport")

        event_id = _bounded_id(f"started:{passport.task_id}:{workstream.workstream_id}:g{executor.executor_generation}")
        event_payload = {
            "schema": "dev-control-plane/supervisor-event/v2",
            "progress": 5,
            "delta_ru": "Исполнитель зарегистрирован с проверенной точной идентичностью.",
            "current_ru": "Выполняется первый детерминированный этап задачи.",
            "objective_invalidated": False,
            "task_revision": task.revision,
            "workstream_revision": workstream.revision,
            "executor_generation": executor.executor_generation,
            "created_at": workstream.created_at,
        }
        created = self.registry.record_input_event_outbox(
            message_id=message_id,
            source=source,
            input_payload={"passport": contract_to_dict(passport), "workstream": contract_to_dict(workstream)},
            event_id=event_id,
            event_type="executor_started",
            event_payload=event_payload,
            outbox_items=(self._dirty_item(event_id, passport.task_id),),
            fence=self.fence,
            task_id=passport.task_id,
            workstream_id=workstream.workstream_id,
            executor_generation=executor.executor_generation,
        )
        return {
            "created": created,
            "task_id": passport.task_id,
            "workstream_id": workstream.workstream_id,
            "executor_generation": executor.executor_generation,
            "progress": 5,
        }

    def import_checkpoint(
        self,
        checkpoint: Checkpoint,
        *,
        message_id: str,
        source: str = "codex-app-server",
        preheld_thread_lock: LockGrant | None = None,
    ) -> dict[str, Any]:
        payload = contract_to_dict(checkpoint)
        _ensure_sanitized(payload)
        existing_checkpoint = self.registry.get_event(checkpoint.event_id)
        if existing_checkpoint is not None:
            if existing_checkpoint["payload"].get("contract") == payload:
                return {
                    "created": False,
                    "task_id": checkpoint.task_id,
                    "workstream_id": checkpoint.workstream_id,
                    "progress": checkpoint.progress_stage,
                    "objective_invalidated": bool(existing_checkpoint["payload"].get("objective_invalidated")),
                }
            raise SupervisorError("checkpoint event_id is already bound to different evidence")
        task = self._required_task(checkpoint.task_id)
        workstream = self._required_workstream(checkpoint.workstream_id, checkpoint.task_id)
        executor = self._required_executor(checkpoint.task_id, checkpoint.workstream_id)
        validate_checkpoint_binding(
            checkpoint,
            task_revision=task.revision,
            workstream_revision=workstream.revision,
            executor_generation=executor.executor_generation,
            executor=checkpoint.executor.__class__(
                executor.thread_id, executor.host_id, executor.model, executor.reasoning
            ),
        )
        current_progress = self._workstream_progress(checkpoint.workstream_id)["progress"]
        invalidation = any(item.startswith("objective_invalidation:") for item in checkpoint.evidence)
        if checkpoint.progress_stage < current_progress and not invalidation:
            raise SupervisorError("progress downgrade requires explicit objective_invalidation evidence")
        if current_progress == 100:
            raise SupervisorError("checkpoint cannot follow technical terminal evidence")

        owns_thread_grant = preheld_thread_lock is None
        thread_grant = preheld_thread_lock or self.registry.acquire_thread_lock(
            checkpoint.executor.thread_id, checkpoint.task_id, self.fence,
            owner_workstream_id=checkpoint.workstream_id,
        )
        if not owns_thread_grant:
            self.registry.attest_lock_grant(
                thread_grant,
                self.fence,
                expected_kind="thread",
                expected_key=checkpoint.executor.thread_id,
                expected_task_id=checkpoint.task_id,
                expected_workstream_id=checkpoint.workstream_id,
            )
        try:
            event_payload = {
                "schema": "dev-control-plane/supervisor-event/v2",
                "contract": payload,
                "progress": checkpoint.progress_stage,
                "delta_ru": checkpoint.delta_ru,
                "current_ru": checkpoint.current_ru,
                "objective_invalidated": invalidation,
                "task_revision": checkpoint.task_revision,
                "workstream_revision": checkpoint.workstream_revision,
                "executor_generation": checkpoint.executor_generation,
                "created_at": checkpoint.created_at,
            }
            created = self.registry.record_input_event_outbox(
                message_id=message_id,
                source=source,
                input_payload=payload,
                event_id=checkpoint.event_id,
                event_type="checkpoint",
                event_payload=event_payload,
                outbox_items=(self._dirty_item(checkpoint.event_id, checkpoint.task_id),),
                fence=self.fence,
                task_id=checkpoint.task_id,
                workstream_id=checkpoint.workstream_id,
                executor_generation=checkpoint.executor_generation,
            )
        finally:
            if owns_thread_grant:
                self.registry.release_locks(thread_grant, self.fence)
        return {
            "created": created,
            "task_id": checkpoint.task_id,
            "workstream_id": checkpoint.workstream_id,
            "progress": checkpoint.progress_stage,
            "objective_invalidated": invalidation,
        }

    def import_terminal(
        self,
        terminal: TerminalEvidence,
        *,
        message_id: str,
        source: str = "codex-app-server",
        preheld_thread_lock: LockGrant | None = None,
    ) -> dict[str, Any]:
        payload = contract_to_dict(terminal)
        _ensure_sanitized(payload)
        existing_terminal = self.registry.get_event(terminal.event_id)
        if existing_terminal is not None:
            stored = existing_terminal["payload"].get("contract")
            if stored == payload:
                return {
                    "created": False,
                    "attention_id": existing_terminal["payload"].get("attention_id") or None,
                    "progress": 100,
                    "technical_complete": bool(existing_terminal["payload"].get("closure_barrier")),
                }
            raise SupervisorError("terminal event_id is already bound to different evidence")

        task = self._required_task(terminal.task_id)
        workstream = self._required_workstream(terminal.workstream_id, terminal.task_id)
        executor = self._required_executor(terminal.task_id, terminal.workstream_id)
        passport = _passport_from_record(task.passport)
        observed_executor = terminal.executor.__class__(
            executor.thread_id, executor.host_id, executor.model, executor.reasoning
        )
        validate_terminal_binding(
            terminal,
            contour=passport.contour,
            task_revision=task.revision,
            workstream_revision=workstream.revision,
            executor_generation=executor.executor_generation,
            executor=observed_executor,
        )
        if self._current_binding_terminal_events(task, workstream, executor):
            raise SupervisorError(
                "current workstream/executor binding already has terminal evidence"
            )
        _verify_contour_evidence(passport, terminal)
        if self.contour_verifier is None:
            raise SupervisorError("terminal closure requires an independent typed contour verifier")
        verification = self.contour_verifier(passport, terminal)
        _validate_contour_verification(verification, passport, terminal)
        event_payload = {
            "schema": "dev-control-plane/supervisor-event/v2",
            "contract": payload,
            "independent_verification": asdict(verification),
            "workstream_generation": workstream.generation,
            "progress": 100,
            "delta_ru": "Получено и независимо сверено terminal evidence для заявленного контура.",
            "current_ru": "Workstream завершён; проверяется общий closure manifest задачи.",
            "objective_invalidated": False,
            "closure_barrier": False,
            "barrier_terminal_event_ids": [],
            "attention_id": "",
            "curator_event_id": "",
            "handoff_ru": "",
            "created_at": terminal.created_at,
        }
        pending_event = {
            "event_id": terminal.event_id,
            "task_id": terminal.task_id,
            "workstream_id": terminal.workstream_id,
            "executor_generation": terminal.executor_generation,
            "payload": event_payload,
            "created_at": self.clock(),
        }
        closure_events = self._technical_closure_events(task, pending_event=pending_event)
        attention_id: str | None = None
        attention_item: dict[str, Any] | None = None
        if closure_events:
            terminal_event_ids = tuple(sorted(str(item["event_id"]) for item in closure_events))
            barrier_digest = _digest_text("|".join(terminal_event_ids))
            attention_id = _bounded_id(f"attention:{terminal.task_id}:r{task.revision}:{barrier_digest[:24]}")
            curator_event_id = _bounded_id(f"curator:{terminal.task_id}:r{task.revision}:{barrier_digest[:24]}")
            handoff = _task_terminal_handoff(passport, closure_events)
            event_payload.update(
                {
                    "closure_barrier": True,
                    "barrier_terminal_event_ids": list(terminal_event_ids),
                    "attention_id": attention_id,
                    "curator_event_id": curator_event_id,
                    "handoff_ru": handoff,
                    "current_ru": "Техническое завершение всей задачи ожидает явной приёмки владельцем.",
                }
            )
            attention_item = {
                "event_id": curator_event_id,
                "kind": "curator_attention",
                "payload": {
                    "schema": "dev-control-plane/curator-attention/v2",
                    "attention_id": attention_id,
                    "task_id": terminal.task_id,
                    "workstream_id": terminal.workstream_id,
                    "curator_thread_id": passport.curator.thread_id,
                    "kind": "terminal",
                    "handoff_ru": handoff,
                    "required_action": "Ответьте ровно «Задача принята».",
                    "created_at": terminal.created_at,
                },
                "task_id": terminal.task_id,
                "coalescible": False,
                "coalesce_key": None,
            }
        owns_thread_grant = preheld_thread_lock is None
        thread_grant = preheld_thread_lock or self.registry.acquire_thread_lock(
            terminal.executor.thread_id, terminal.task_id, self.fence,
            owner_workstream_id=terminal.workstream_id,
        )
        if not owns_thread_grant:
            self.registry.attest_lock_grant(
                thread_grant,
                self.fence,
                expected_kind="thread",
                expected_key=terminal.executor.thread_id,
                expected_task_id=terminal.task_id,
                expected_workstream_id=terminal.workstream_id,
            )
        try:
            # Recheck under the per-thread serialization grant.  The first
            # exact event-id replay returned above; a second distinct terminal
            # for the same current binding would make the task barrier
            # ambiguous and must never be persisted.
            if self._current_binding_terminal_events(task, workstream, executor):
                raise SupervisorError(
                    "current workstream/executor binding already has terminal evidence"
                )
            created = self.registry.record_input_event_outbox(
                message_id=message_id,
                source=source,
                input_payload=payload,
                event_id=terminal.event_id,
                event_type="technical_terminal",
                event_payload=event_payload,
                outbox_items=tuple(
                    item
                    for item in (self._dirty_item(terminal.event_id, terminal.task_id), attention_item)
                    if item is not None
                ),
                fence=self.fence,
                task_id=terminal.task_id,
                workstream_id=terminal.workstream_id,
                executor_generation=terminal.executor_generation,
            )
        finally:
            if owns_thread_grant:
                self.registry.release_locks(thread_grant, self.fence)
        return {
            "created": created,
            "attention_id": attention_id,
            "progress": 100,
            "technical_complete": bool(closure_events),
            "verification_id": verification.verification_id,
            # A terminal workstream is not a task-level target-lane closure.
            # The logical lane remains fenced until the exact closure actuator
            # receipt or explicit owner acceptance releases the whole task.
            "released_reservation_locks": 0,
        }

    def owner_accept(
        self,
        receipt: OwnerAcceptanceReceipt,
        *,
        message_id: str,
        source: str = "exact-curator-thread",
    ) -> dict[str, Any]:
        payload = owner_acceptance_to_dict(receipt)
        _ensure_sanitized(payload)
        event_id = _bounded_id("owner-accepted:" + receipt.receipt_id)
        existing = self.registry.get_event(event_id)
        if existing is not None:
            if existing["payload"].get("receipt") == payload:
                return {"created": False, "task_id": receipt.task_id, "accepted": True}
            raise SupervisorError("owner acceptance event is bound to another receipt")
        task = self._required_task(receipt.task_id)
        passport = _passport_from_record(task.passport)
        if receipt.curator_thread_id != passport.curator.thread_id:
            raise SupervisorError("owner receipt did not arrive from the exact curator thread")
        if receipt.task_revision != task.revision:
            raise CASConflict("owner receipt is stale for the current task revision")
        terminals = self._technical_closure_events(task)
        if not terminals:
            raise SupervisorError("owner acceptance is forbidden before every current workstream proves closure")
        barrier_events = [item for item in terminals if item["payload"].get("closure_barrier") is True]
        if len(barrier_events) != 1:
            raise SupervisorError("owner acceptance requires one current task-level closure attention")
        barrier = barrier_events[0]
        event_payload = {
            "schema": "dev-control-plane/supervisor-event/v2",
            "receipt": payload,
            "technical_terminal_event_ids": sorted(str(item["event_id"]) for item in terminals),
            "closure_attention_event_id": barrier["payload"]["curator_event_id"],
            "accepted_at": receipt.created_at,
        }
        created = self.registry.accept_task_by_owner(
            message_id=message_id,
            source=source,
            receipt_payload=payload,
            task_id=receipt.task_id,
            expected_revision=receipt.task_revision,
            event_id=event_id,
            event_payload=event_payload,
            outbox_items=(self._dirty_item(event_id, receipt.task_id),),
            fence=self.fence,
        )
        released = self._release_task_scheduler_reservations(receipt.task_id)
        return {
            "created": created,
            "task_id": receipt.task_id,
            "accepted": True,
            "released_reservation_locks": released,
        }

    def schedule(
        self,
        candidates: Sequence[ReleaseCandidate],
        *,
        message_id: str,
        completed_task_ids: Sequence[str] = (),
        active_logical_lane_id: str | None = None,
    ) -> dict[str, Any]:
        candidate_payload = [asdict(candidate) for candidate in candidates]
        _ensure_sanitized(candidate_payload)
        input_payload = {
            "candidates": candidate_payload,
            "completed_task_ids": list(completed_task_ids),
            "active_logical_lane_id": active_logical_lane_id,
        }
        input_digest = _digest_json(input_payload)
        event_id = _bounded_id("schedule:" + input_digest[:40])
        existing = self.registry.get_event(event_id)
        if existing is not None:
            return dict(existing["payload"]["decision"])
        decision = schedule_releases(
            candidates,
            completed_task_ids=completed_task_ids,
            active_logical_lane_id=active_logical_lane_id,
            now=_iso(self.clock()),
        )
        decision_payload = _schedule_decision_payload(decision)
        reservations = ()
        if decision.kind == "release_sequence":
            first_id = decision.candidate_ids[0]
            selected = next(candidate for candidate in candidates if candidate.candidate_id == first_id)
            reservations = self.registry.acquire_scheduler_reservation(
                task_id=selected.task_id,
                workstream_id=selected.workstream_id,
                target_id=selected.target_id,
                resources=selected.resources,
                fence=self.fence,
            )
            event_type = "release_reserved"
            task_id = selected.task_id
            workstream_id = selected.workstream_id
        else:
            event_type = "semantic_release_case" if decision.kind == "semantic_release_plan" else "release_wait"
            task_id = candidates[0].task_id if candidates else None
            workstream_id = candidates[0].workstream_id if candidates else None
        event_payload = {
            "schema": "dev-control-plane/supervisor-event/v2",
            "decision": decision_payload,
            "candidates": candidate_payload,
            "created_at": _iso(self.clock()),
        }
        try:
            created = self.registry.record_input_event_outbox(
                message_id=message_id,
                source="deterministic-scheduler",
                input_payload=input_payload,
                event_id=event_id,
                event_type=event_type,
                event_payload=event_payload,
                outbox_items=(self._dirty_item(event_id, task_id),),
                fence=self.fence,
                task_id=task_id,
                workstream_id=workstream_id,
            )
        except Exception:
            if reservations:
                self.registry.release_scheduler_reservation(reservations, self.fence)
            raise
        result = dict(decision_payload)
        result["created"] = created
        result["reservation"] = (
            {
                "task_id": reservations[0].owner_task_id,
                "workstream_id": reservations[0].owner_workstream_id,
                "generation": reservations[0].generation,
                "expires_at": reservations[0].expires_at,
                "lock_count": sum(len(item.keys) for item in reservations),
            }
            if reservations
            else None
        )
        return result

    def tick(self, *, publish_limit: int = 10) -> TickResult:
        self._recover_scheduler_reservations()
        projection_event_id: str | None = None
        reserved = False
        outstanding = self.registry.list_outbox_summaries(
            kinds=("projection_snapshot",), states=("pending", "inflight")
        )
        dirty = (
            ()
            if outstanding
            else self.registry.claim_outbox(
                self.fence,
                worker_id="supervisor-projection-builder",
                limit=100,
                visibility_timeout=60,
                kinds=("projection_dirty",),
            )
        )
        if dirty:
            trigger = _digest_text("|".join(message.event_id for message in dirty))
            try:
                projection_event_id = self._reserve_projection(trigger)
                for message in dirty:
                    self.registry.ack_outbox(message.event_id, message.claim_token, self.fence)
                reserved = True
            except Exception:
                retry_at = self.clock() + 5
                for message in dirty:
                    self.registry.nack_outbox(
                        message.event_id,
                        message.claim_token,
                        self.fence,
                        retry_at=retry_at,
                        sanitized_error="projection_snapshot_build_failed",
                    )
                raise
        elif not outstanding and self._heartbeat_due():
            bucket = int(self.clock() // self.projection_heartbeat_seconds)
            projection_event_id = self._reserve_projection(f"heartbeat:{self.fence.generation}:{bucket}")
            reserved = True
        published = self.publisher.publish_available(self.registry, self.fence, limit=publish_limit) if self.publisher else ()
        self._last_tick_error = None
        return TickResult(reserved, projection_event_id, tuple(published))

    def _recover_scheduler_reservations(self) -> None:
        tasks = {task.task_id: task for task in self.registry.list_tasks()}
        events = self.registry.list_events(
            event_types=(
                "release_reserved", "release_head_reserved", "release_superseded",
                "target_lane_closure_completed",
            )
        )
        closed_tasks = {
            task_id
            for task_id, task in tasks.items()
            if task.state == "accepted"
            or any(
                _target_lane_closure_matches_task(event, task)
                for event in events
                if event.get("event_type") == "target_lane_closure_completed"
                and event.get("task_id") == task_id
            )
        }
        for lock in self.registry.inspect_locks():
            task_id = str(lock.get("owner_task_id") or "")
            workstream_id = str(lock.get("owner_workstream_id") or "")
            if task_id in closed_tasks and workstream_id:
                self.registry.release_scheduler_reservation_owner(
                    task_id=task_id,
                    workstream_id=workstream_id,
                    fence=self.fence,
                )

        latest_by_workstream: dict[tuple[str, str], tuple[int, Mapping[str, Any]]] = {}
        for index, event in enumerate(events):
            if event["event_type"] in {"release_reserved", "release_head_reserved"} and event["workstream_id"]:
                latest_by_workstream[(str(event["task_id"]), str(event["workstream_id"]))] = (
                    index,
                    event,
                )
        for (task_id, workstream_id), (reservation_index, event) in latest_by_workstream.items():
            task = tasks.get(task_id)
            if task is None or task_id in closed_tasks:
                continue
            payload = event["payload"]
            if event["event_type"] == "release_head_reserved":
                selected = payload.get("candidate")
            else:
                candidate_ids = payload.get("decision", {}).get("candidate_ids", [])
                selected = next(
                    (
                        item
                        for item in payload.get("candidates", [])
                        if candidate_ids and item.get("candidate_id") == candidate_ids[0]
                    ),
                    None,
                )
            if not isinstance(selected, Mapping):
                continue
            binding = (str(selected.get("candidate_id") or ""), str(selected.get("pr_head_sha") or ""))
            superseded = False
            for later in events[reservation_index + 1 :]:
                if later.get("task_id") != task_id or later.get("workstream_id") != workstream_id:
                    continue
                if later["event_type"] in {"release_reserved", "release_head_reserved"}:
                    # This reservation is no longer current. Its outcome must
                    # never release or renew a newer exact candidate binding.
                    break
                if (
                    later["event_type"] == "release_superseded"
                    and _release_outcome_binding(later) == binding
                ):
                    superseded = True
            if superseded:
                self.registry.release_scheduler_reservation_owner(
                    task_id=task_id,
                    workstream_id=workstream_id,
                    fence=self.fence,
                )
                continue
            self.registry.renew_scheduler_reservation_owner(
                task_id=task_id,
                workstream_id=workstream_id,
                target_id=str(selected["target_id"]),
                resources=tuple(selected["resources"]),
                fence=self.fence,
            )

    def projection_snapshot(self) -> dict[str, list[dict[str, Any]]]:
        tasks = self.registry.list_tasks()
        workstreams = self.registry.list_workstreams()
        events = self.registry.list_events()
        attention_outbox = self.registry.list_outbox_records(kinds=("curator_attention",))
        events_by_task: dict[str, list[dict[str, Any]]] = {}
        events_by_workstream: dict[str, list[dict[str, Any]]] = {}
        for event in events:
            if event["task_id"]:
                events_by_task.setdefault(str(event["task_id"]), []).append(event)
            if event["workstream_id"]:
                events_by_workstream.setdefault(str(event["workstream_id"]), []).append(event)

        task_rows: list[dict[str, Any]] = []
        workstream_rows: list[dict[str, Any]] = []
        release_rows: list[dict[str, Any]] = []
        incident_rows: list[dict[str, Any]] = []
        attention_rows: list[dict[str, Any]] = []
        acceptance_rows: list[dict[str, Any]] = []
        accepted_by_task: dict[str, bool] = {}
        task_by_id = {item.task_id: item for item in tasks}
        resolved_attention: dict[str, str] = {}
        for event in events:
            payload = event.get("payload")
            if not isinstance(payload, Mapping):
                continue
            attention_event_id = payload.get("resolved_attention_event_id")
            if isinstance(attention_event_id, str) and attention_event_id:
                resolved_attention[attention_event_id] = str(
                    payload.get("updated_at") or _iso(float(event["created_at"]))
                )

        for task in tasks:
            passport = _passport_from_record(task.passport)
            task_events = events_by_task.get(task.task_id, [])
            owner_event = _latest_event(task_events, "owner_accepted")
            accepted = task.state == "accepted" or owner_event is not None
            accepted_by_task[task.task_id] = accepted
            closure_events = () if accepted else self._technical_closure_events(task)
            barrier_event = next(
                (item for item in closure_events if item["payload"].get("closure_barrier") is True),
                None,
            )
            historical_barrier = _latest_barrier_event(task_events)
            task_status = (
                "accepted"
                if accepted
                else "awaiting_acceptance"
                if barrier_event is not None
                else _projection_task_status(task.state)
            )
            updated_at = _latest_timestamp(task.updated_at, task_events)
            task_rows.append(
                {
                    "task_id": task.task_id,
                    "revision": task.revision,
                    "title": passport.title,
                    "status": task_status,
                    "objective": passport.objective,
                    "active": not accepted,
                    "accepted": accepted,
                    "created_at": passport.created_at,
                    "updated_at": updated_at,
                }
            )
            for workstream in (item for item in workstreams if item.task_id == task.task_id):
                contract = _workstream_from_record(workstream.contract)
                stream_events = events_by_workstream.get(workstream.workstream_id, [])
                progress = _progress_from_events(stream_events)
                terminal = _matching_current_terminal(task, workstream, stream_events, self.registry)
                status = (
                    "completed"
                    if accepted
                    else "awaiting_acceptance"
                    if terminal is not None
                    else _projection_workstream_status(workstream.state, stream_events)
                )
                blocker = _projection_blocker(status, stream_events, attention_outbox)
                workstream_rows.append(
                    {
                        "workstream_id": workstream.workstream_id,
                        "task_id": task.task_id,
                        "revision": workstream.revision,
                        "title": contract.title,
                        "status": status,
                        "progress": 100 if accepted or terminal is not None else progress["progress"],
                        "remaining_range": (
                            "0 этапов" if accepted or terminal is not None else _remaining_range(progress["progress"])
                        ),
                        "delta": progress["delta_ru"],
                        "current_action": (
                            "Задача принята владельцем."
                            if accepted
                            else "Workstream завершён; ожидается closure остальных частей задачи."
                            if terminal is not None and barrier_event is None
                            else progress["current_ru"]
                        ),
                        "blocker": blocker,
                        "active": not accepted,
                        "updated_at": _latest_timestamp(task.updated_at, stream_events),
                    }
                )
            release_rows.extend(_release_projection(task.task_id, task_events))
            incident_rows.extend(_incident_projection(task.task_id, task_events))
            proof_event = barrier_event or historical_barrier
            technical_complete = barrier_event is not None or accepted
            proof_payload = proof_event["payload"] if proof_event is not None else {}
            proof_contract = proof_payload.get("contract", {})
            acceptance_rows.append(
                {
                    "acceptance_id": _bounded_id("acceptance:" + task.task_id),
                    "task_id": task.task_id,
                    "revision": task.revision,
                    "status": "accepted" if accepted else "awaiting_owner" if technical_complete else "not_ready",
                    "technical_complete": technical_complete,
                    "owner_accepted": accepted,
                    "requested_at": str(proof_payload.get("created_at") or "") if technical_complete else "",
                    "accepted_at": owner_event["payload"]["accepted_at"] if owner_event else "",
                    "summary": str(
                        proof_contract.get("summary_ru")
                        or ("Техническое завершение доказано для всего closure manifest." if technical_complete else "Техническое завершение ещё не доказано.")
                    ),
                    "updated_at": owner_event["payload"]["accepted_at"] if owner_event else updated_at,
                }
            )

        for item in attention_outbox:
            payload = item.get("payload")
            if not isinstance(payload, Mapping):
                continue
            task_id = str(payload.get("task_id") or "")
            task = task_by_id.get(task_id)
            if task is None:
                continue
            kind = str(payload.get("kind") or "")
            resolved = (
                accepted_by_task.get(task_id, False) and kind == "terminal"
            ) or item["event_id"] in resolved_attention or item["state"] == "superseded"
            status = "resolved" if resolved else "delivered" if item["state"] == "delivered" else "pending"
            handoff = str(payload.get("handoff_ru") or "Требуется внимание к задаче.")
            attention_rows.append(
                {
                    "attention_id": str(payload["attention_id"]),
                    "task_id": task_id,
                    "workstream_id": payload.get("workstream_id"),
                    "revision": task.revision,
                    "kind": kind,
                    "status": status,
                    "summary": handoff[:1_000],
                    "required_action": str(payload["required_action"]),
                    "created_at": str(payload["created_at"]),
                    "updated_at": resolved_attention.get(
                        str(item["event_id"]), _iso(float(item["updated_at"]))
                    ),
                }
            )
        projection = {
            "tasks": task_rows,
            "workstreams": workstream_rows,
            "release_lanes": release_rows,
            "incidents": incident_rows,
            "attention": attention_rows,
            "acceptance": acceptance_rows,
        }
        _ensure_sanitized(projection)
        return projection

    def local_state(self) -> dict[str, Any]:
        projection = self.projection_snapshot()
        queue = self.registry.list_outbox_summaries()
        return {
            "service_role": SERVICE_ROLE,
            "control_authority": True,
            "http_mutation_enabled": False,
            "supervisor_id": self.supervisor_id,
            "generation": self.fence.generation,
            "projection_configured": self.publisher is not None,
            "queue": {
                "pending": sum(item["state"] == "pending" for item in queue),
                "inflight": sum(item["state"] == "inflight" for item in queue),
                "delivered": sum(item["state"] == "delivered" for item in queue),
            },
            "projection": projection,
        }

    def health(self) -> dict[str, Any]:
        registry_health = self.registry.health()
        lease = self.registry.current_generation()
        lease_live = (
            lease.get("generation") == self.fence.generation
            and lease.get("owner_id") == self.fence.owner_id
            and float(lease.get("expires_at") or 0) > self.clock()
        )
        return {
            "status": "ready" if registry_health["ok"] and lease_live else "not_ready",
            "service_role": SERVICE_ROLE,
            "control_authority": True,
            "single_writer_generation": self.fence.generation,
            "lease_live": lease_live,
            "registry": registry_health,
            "projection_configured": self.publisher is not None,
            "last_tick_error": self._last_tick_error,
        }

    def readiness(self) -> dict[str, Any]:
        health = self.health()
        return {
            "ready": health["status"] == "ready",
            "service_role": SERVICE_ROLE,
            "generation": self.fence.generation,
            "single_writer": health["lease_live"],
        }

    def _required_task(self, task_id: str) -> Any:
        task = self.registry.get_task(task_id)
        if task is None:
            raise SupervisorError(f"unknown task: {task_id}")
        return task

    def _required_workstream(self, workstream_id: str, task_id: str) -> Any:
        workstream = self.registry.get_workstream(workstream_id)
        if workstream is None or workstream.task_id != task_id:
            raise SupervisorError("unknown or cross-task workstream")
        return workstream

    def _required_executor(self, task_id: str, workstream_id: str) -> Any:
        executor = self.registry.current_executor(task_id, workstream_id)
        if executor is None:
            raise SupervisorError("workstream has no active executor")
        return executor

    def _technical_closure_events(
        self,
        task: Any,
        *,
        pending_event: Mapping[str, Any] | None = None,
    ) -> tuple[Mapping[str, Any], ...]:
        """Return one current, independently verified terminal per declared stream.

        The Passport closure manifest is immutable for its revision. Historical
        terminals from replaced workstream/executor generations never satisfy
        this barrier.
        """

        passport = _passport_from_record(task.passport)
        observed = list(
            self.registry.list_events(task_id=task.task_id, event_types=("technical_terminal",))
        )
        if pending_event is not None:
            observed.append(dict(pending_event))
        selected: list[Mapping[str, Any]] = []
        for workstream_id in passport.workstream_ids:
            workstream = self.registry.get_workstream(workstream_id)
            executor = self.registry.current_executor(task.task_id, workstream_id)
            if workstream is None or workstream.task_id != task.task_id or executor is None:
                return ()
            matches: list[Mapping[str, Any]] = []
            for event in observed:
                if event.get("workstream_id") != workstream_id:
                    continue
                payload = event.get("payload")
                contract = payload.get("contract") if isinstance(payload, Mapping) else None
                verification = payload.get("independent_verification") if isinstance(payload, Mapping) else None
                if not isinstance(contract, Mapping) or not isinstance(verification, Mapping):
                    continue
                binding = (
                    contract.get("task_id"),
                    contract.get("task_revision"),
                    contract.get("workstream_id"),
                    contract.get("workstream_revision"),
                    contract.get("executor_generation"),
                    payload.get("workstream_generation"),
                    event.get("executor_generation"),
                    verification.get("passed"),
                )
                expected = (
                    task.task_id,
                    task.revision,
                    workstream_id,
                    workstream.revision,
                    executor.executor_generation,
                    workstream.generation,
                    executor.executor_generation,
                    True,
                )
                if binding == expected:
                    matches.append(event)
            if len(matches) != 1:
                return ()
            selected.append(matches[0])
        return tuple(selected)

    def _current_binding_terminal_events(
        self,
        task: Any,
        workstream: Any,
        executor: Any,
    ) -> tuple[Mapping[str, Any], ...]:
        """Return terminal rows bound to one exact current executor generation."""

        matches: list[Mapping[str, Any]] = []
        for event in self.registry.list_events(
            task_id=task.task_id,
            workstream_id=workstream.workstream_id,
            event_types=("technical_terminal",),
        ):
            payload = event.get("payload")
            contract = payload.get("contract") if isinstance(payload, Mapping) else None
            if not isinstance(contract, Mapping):
                continue
            if (
                contract.get("task_id") == task.task_id
                and contract.get("task_revision") == task.revision
                and contract.get("workstream_id") == workstream.workstream_id
                and contract.get("workstream_revision") == workstream.revision
                and contract.get("executor_generation") == executor.executor_generation
                and payload.get("workstream_generation") == workstream.generation
                and event.get("executor_generation") == executor.executor_generation
            ):
                matches.append(event)
        return tuple(matches)

    def _release_task_scheduler_reservations(self, task_id: str) -> int:
        """Release every scheduler owner of one task after task-level closure."""

        owners = {
            str(item["owner_workstream_id"])
            for item in self.registry.inspect_locks()
            if item.get("owner_task_id") == task_id
            and item.get("owner_workstream_id")
            and item.get("lock_kind") in {"task", "resource", "release_lane"}
        }
        return sum(
            self.registry.release_scheduler_reservation_owner(
                task_id=task_id,
                workstream_id=workstream_id,
                fence=self.fence,
            )
            for workstream_id in sorted(owners)
        )

    def _workstream_progress(self, workstream_id: str) -> dict[str, Any]:
        return _progress_from_events(
            self.registry.list_events(workstream_id=workstream_id, event_types=PROGRESS_EVENT_TYPES)
        )

    def _dirty_item(self, trigger_event_id: str, task_id: str | None) -> dict[str, Any]:
        event_id = _bounded_id("dirty:" + _digest_text(trigger_event_id)[:40])
        return {
            "event_id": event_id,
            "kind": "projection_dirty",
            "payload": {"trigger_event_id": trigger_event_id},
            "task_id": task_id,
            "coalescible": True,
            "coalesce_key": "global-projection",
        }

    def _reserve_projection(self, trigger: str) -> str:
        projection = self.projection_snapshot()
        event_id = _bounded_id(
            f"projection:{self.fence.generation}:" + _digest_text(trigger)[:32]
        )
        idempotency_key = _bounded_id("projection-idem:" + _digest_text(event_id)[:32])
        validation_envelope = {
            "contract": PROJECTION_CONTRACT,
            "supervisor_id": self.supervisor_id,
            "generation": self.fence.generation,
            "sequence": 1,
            "revision": 1,
            "event_id": event_id,
            "idempotency_key": idempotency_key,
            "timestamp": max(1, int(self.clock())),
            "projection": projection,
        }
        projection_envelope_from_mapping(validation_envelope)
        self.registry.reserve_projection_snapshot(
            supervisor_id=self.supervisor_id,
            projection=projection,
            event_id=event_id,
            idempotency_key=idempotency_key,
            fence=self.fence,
        )
        return event_id

    def _heartbeat_due(self) -> bool:
        snapshots = self.registry.list_outbox_summaries(kinds=("projection_snapshot",))
        if not snapshots:
            return True
        return self.clock() - max(float(item["created_at"]) for item in snapshots) >= self.projection_heartbeat_seconds


class SupervisorHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, engine: SupervisorEngine, host: str, port: int) -> None:
        if host != LOCAL_HOST:
            raise SupervisorError("local Supervisor HTTP must bind only to 127.0.0.1")
        self.engine = engine
        super().__init__((host, port), SupervisorRequestHandler)


class SupervisorRequestHandler(BaseHTTPRequestHandler):
    server: SupervisorHTTPServer

    def do_GET(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        if path == "/api/v2/health":
            self._send(self.server.engine.health())
        elif path == "/api/v2/readiness":
            payload = self.server.engine.readiness()
            self._send(payload, HTTPStatus.OK if payload["ready"] else HTTPStatus.SERVICE_UNAVAILABLE)
        elif path == "/api/v2/state":
            self._send(self.server.engine.local_state())
        else:
            self._send({"status": "not_found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        self._deny()

    def do_PUT(self) -> None:  # noqa: N802
        self._deny()

    def do_PATCH(self) -> None:  # noqa: N802
        self._deny()

    def do_DELETE(self) -> None:  # noqa: N802
        self._deny()

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._deny()

    def _deny(self) -> None:
        self._send(
            {"status": "denied", "reason_code": "local_status_api_read_only", "service_role": SERVICE_ROLE},
            HTTPStatus.METHOD_NOT_ALLOWED,
            allow="GET",
        )

    def _send(self, payload: Mapping[str, Any], status: HTTPStatus = HTTPStatus.OK, *, allow: str | None = None) -> None:
        body = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        if allow:
            self.send_header("Allow", allow)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


class SupervisorBackgroundLoop:
    """Lease renewal and bounded tick loop for the one local engine process."""

    def __init__(self, engine: SupervisorEngine, *, interval_seconds: float = 10.0) -> None:
        if interval_seconds <= 0:
            raise SupervisorError("background interval must be positive")
        self.engine = engine
        self.interval_seconds = float(interval_seconds)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            raise SupervisorError("background loop already started")
        self._thread = threading.Thread(target=self._run, name="dev-control-plane-v2-supervisor", daemon=True)
        self._thread.start()

    def stop(self, *, timeout: float = 15.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                raise SupervisorError("background Supervisor loop did not stop")

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                if self.engine.fence.expires_at - self.engine.clock() <= self.engine.registry.lease_seconds / 2:
                    self.engine.renew_lease()
                self.engine.tick()
            except Exception as exc:
                self.engine._last_tick_error = type(exc).__name__
            self._stop.wait(self.interval_seconds)


def owner_acceptance_from_mapping(payload: Mapping[str, Any]) -> OwnerAcceptanceReceipt:
    expected = {item.name for item in fields(OwnerAcceptanceReceipt)}
    if not isinstance(payload, Mapping) or set(payload) != expected:
        raise SupervisorError("owner acceptance fields are invalid")
    return OwnerAcceptanceReceipt(**dict(payload))


def owner_acceptance_to_dict(receipt: OwnerAcceptanceReceipt) -> dict[str, Any]:
    return asdict(receipt)


def release_candidate_from_mapping(payload: Mapping[str, Any]) -> ReleaseCandidate:
    expected = {item.name for item in fields(ReleaseCandidate)}
    if not isinstance(payload, Mapping) or set(payload) != expected:
        raise SupervisorError("release candidate fields are invalid")
    return ReleaseCandidate(**dict(payload))


def stable_supervisor_id(state_identity: str) -> str:
    return "mac-supervisor:" + _digest_text(state_identity)[:24]


def terminal_contract_digest(terminal: TerminalEvidence) -> str:
    return _digest_json(contract_to_dict(terminal))


def _validate_contour_verification(
    verification: ContourVerification,
    passport: TaskPassport,
    terminal: TerminalEvidence,
) -> None:
    expected = (
        terminal.task_id,
        terminal.workstream_id,
        terminal.task_revision,
        terminal.workstream_revision,
        passport.contour,
        terminal_contract_digest(terminal),
    )
    observed = (
        verification.task_id,
        verification.workstream_id,
        verification.task_revision,
        verification.workstream_revision,
        verification.contour,
        verification.terminal_digest,
    )
    if observed != expected:
        raise SupervisorError("independent contour verification is stale or bound to another terminal")


def _schedule_decision_payload(decision: ScheduleDecision) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "kind": decision.kind,
        "candidate_ids": list(decision.candidate_ids),
        "reason": decision.reason or "",
    }
    if decision.semantic_case is not None:
        payload["semantic_case"] = {
            "case_id": decision.semantic_case.case_id,
            "case_digest": decision.semantic_case.case_digest,
            "reasons": list(decision.semantic_case.reasons),
            "created_at": decision.semantic_case.created_at,
        }
    else:
        payload["semantic_case"] = None
    return payload


def _progress_from_events(events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    progress = {
        "progress": 5,
        "delta_ru": "Исполнитель зарегистрирован.",
        "current_ru": "Выполняется первый детерминированный этап задачи.",
        "blocker": "",
    }
    for event in events:
        if event.get("event_type") not in PROGRESS_EVENT_TYPES:
            continue
        payload = event.get("payload")
        if not isinstance(payload, Mapping):
            continue
        observed = payload.get("progress")
        if observed in CANONICAL_PROGRESS:
            progress = {
                "progress": int(observed),
                "delta_ru": str(payload.get("delta_ru") or progress["delta_ru"]),
                "current_ru": str(payload.get("current_ru") or progress["current_ru"]),
                "blocker": str(payload.get("blocker") or ""),
            }
    return progress


def _release_projection(task_id: str, events: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    # A release row is folded by the immutable workstream/head binding rather
    # than by an event id.  Registrations intentionally precede allocation of a
    # scheduler candidate id, while admission/reservation/receipt events use
    # that candidate id.  Keeping the binding stable lets one sanitized row
    # advance across those stages and also keeps an old superseded head visible
    # beside its replacement registration during readmission.
    result: dict[tuple[str, str], dict[str, Any]] = {}
    phases: dict[tuple[str, str], int] = {}

    def apply(
        *,
        workstream_id: Any,
        head_sha: Any,
        revision: Any,
        release_id: Any,
        environment: Any,
        phase: int,
        status: str,
        deploy_status: str,
        verification_status: str,
        event: Mapping[str, Any],
        pr_url: str = "",
        merge_sha: str = "",
        updated_at: str | None = None,
    ) -> None:
        stream = str(workstream_id or event.get("workstream_id") or "")
        head = str(head_sha or "")
        if not stream or not head:
            return
        binding = (stream, head)
        row = result.get(binding)
        if row is None:
            row = {
                "release_id": _bounded_id(str(release_id or event["event_id"])),
                "task_id": task_id,
                "workstream_id": stream,
                "revision": int(revision or 1),
                "status": status,
                "pr_url": pr_url,
                "pr_number": _pr_number(pr_url),
                "head_sha": head,
                "merge_sha": merge_sha,
                "environment": str(environment or ""),
                "deploy_status": deploy_status,
                "verification_status": verification_status,
                "updated_at": updated_at or _iso(float(event["created_at"])),
            }
            result[binding] = row
            phases[binding] = phase
            return

        # Candidate identity and PR metadata may become known after the
        # registration.  They are safe to enrich even when equal timestamps
        # make the registry's deterministic event-id order differ from causal
        # order.  State itself advances only by a monotonic fold phase.
        if release_id:
            row["release_id"] = _bounded_id(str(release_id))
        if pr_url:
            row["pr_url"] = pr_url
            row["pr_number"] = _pr_number(pr_url)
        if environment:
            row["environment"] = str(environment)
        if merge_sha:
            row["merge_sha"] = merge_sha
        row["revision"] = max(int(row["revision"]), int(revision or 1))
        if phase >= phases[binding]:
            row.update(
                {
                    "status": status,
                    "deploy_status": deploy_status,
                    "verification_status": verification_status,
                    "updated_at": updated_at or _iso(float(event["created_at"])),
                }
            )
            phases[binding] = phase

    for event in events:
        event_type = event.get("event_type")
        if event_type not in {
            "release_candidate_registered",
            "release_candidate_admitted",
            "release_wait",
            "release_reserved",
            "release_head_reserved",
            "semantic_release_case",
            "release_action_observed",
            "release_superseded",
            "release_completed",
            "release_proof_only",
            "release_stalled",
            "target_lane_closure_pending",
            "target_lane_closure_observed",
            "target_lane_closure_completed",
            "target_lane_closure_stalled",
        }:
            continue
        payload = event.get("payload")
        if not isinstance(payload, Mapping):
            continue

        if event_type == "release_candidate_registered":
            if payload.get("task_id") != task_id:
                continue
            apply(
                workstream_id=payload.get("workstream_id"),
                head_sha=payload.get("expected_pr_head_sha"),
                revision=payload.get("task_revision"),
                release_id=event.get("event_id"),
                environment=payload.get("target_id"),
                phase=10,
                status="pr_open",
                deploy_status="candidate_registered",
                verification_status="pending",
                event=event,
            )
            continue

        if event_type == "release_candidate_admitted":
            candidate = payload.get("candidate")
            truth = payload.get("scheduler_truth")
            release_candidate = payload.get("release_candidate")
            if not isinstance(candidate, Mapping) or candidate.get("task_id") != task_id:
                continue
            truth = truth if isinstance(truth, Mapping) else {}
            release_candidate = release_candidate if isinstance(release_candidate, Mapping) else {}
            proof_only = payload.get("proof_only") is True or truth.get("pr_state") == "MERGED"
            blocked = any(
                candidate.get(name) is True
                for name in ("merge_conflict", "passport_diff_mismatch", "unknown_classification")
            )
            if proof_only:
                status = "merged"
                deploy = "proof_only"
                verification = "merged_proof"
            elif blocked:
                status = "blocked"
                deploy = "admission_blocked"
                verification = "github_truth_checked"
            elif candidate.get("admission_ready") is True:
                status = "ready"
                deploy = "candidate_admitted"
                verification = "github_checks_passed"
            elif candidate.get("checks_green") is False:
                status = "checks_running"
                deploy = "awaiting_admission"
                verification = "github_checks_pending"
            else:
                status = "pr_open"
                deploy = "awaiting_admission"
                verification = "github_truth_checked"
            pr_url = _release_candidate_pr_url(release_candidate)
            apply(
                workstream_id=candidate.get("workstream_id"),
                head_sha=candidate.get("pr_head_sha"),
                revision=candidate.get("task_revision"),
                release_id=candidate.get("candidate_id"),
                environment=candidate.get("target_id"),
                phase=20,
                status=status,
                deploy_status=deploy,
                verification_status=verification,
                pr_url=pr_url,
                merge_sha=str(truth.get("merge_commit_sha") or ""),
                event=event,
            )
            continue

        if event_type in {"release_reserved", "release_head_reserved", "semantic_release_case"}:
            raw_candidates = (
                [payload.get("candidate")]
                if event_type == "release_head_reserved"
                else payload.get("candidates", [])
            )
            for candidate in raw_candidates:
                if not isinstance(candidate, Mapping) or candidate.get("task_id") != task_id:
                    continue
                semantic = event_type == "semantic_release_case"
                apply(
                    workstream_id=candidate.get("workstream_id"),
                    head_sha=candidate.get("pr_head_sha"),
                    revision=candidate.get("task_revision"),
                    release_id=candidate.get("candidate_id"),
                    environment=candidate.get("target_id"),
                    phase=30 if semantic else 40,
                    status="planned" if semantic else "ready",
                    deploy_status="semantic_plan_required" if semantic else "lane_reserved",
                    verification_status="github_checks_passed",
                    updated_at=str(payload.get("created_at") or _iso(float(event["created_at"]))),
                    event=event,
                )
            continue

        if event_type == "release_wait":
            for candidate in payload.get("candidates", []):
                if not isinstance(candidate, Mapping) or candidate.get("task_id") != task_id:
                    continue
                proof_only = candidate.get("admission_ready") is False and bool(
                    candidate.get("checks_green")
                )
                blocked = any(
                    candidate.get(name) is True
                    for name in ("merge_conflict", "passport_diff_mismatch", "unknown_classification")
                )
                status = "merged" if proof_only else "blocked" if blocked else "checks_running"
                apply(
                    workstream_id=candidate.get("workstream_id"),
                    head_sha=candidate.get("pr_head_sha"),
                    revision=candidate.get("task_revision"),
                    release_id=candidate.get("candidate_id"),
                    environment=candidate.get("target_id"),
                    phase=35,
                    status=status,
                    deploy_status="proof_only" if proof_only else "awaiting_admission",
                    verification_status="merged_proof" if proof_only else "github_checks_pending",
                    updated_at=str(payload.get("created_at") or _iso(float(event["created_at"]))),
                    event=event,
                )
            continue

        if event_type == "release_action_observed":
            observation = payload.get("observation")
            if not isinstance(observation, Mapping) or observation.get("task_id") != task_id:
                continue
            observation_status = str(observation.get("status") or "")
            status = {
                "admission_submitted": "checks_running",
                "admitted": "ready",
                "waiting_foreign_lane": "ready",
                "waiting_release": "ready",
                "readmission_required": "blocked",
            }.get(observation_status)
            if status is None:
                continue
            apply(
                workstream_id=observation.get("workstream_id"),
                head_sha=observation.get("expected_head_sha"),
                revision=observation.get("task_revision"),
                release_id=observation.get("candidate_id"),
                environment=payload.get("target_adapter"),
                phase=50 if observation_status != "readmission_required" else 80,
                status=status,
                deploy_status=observation_status,
                verification_status=(
                    "readmission_required"
                    if observation_status == "readmission_required"
                    else "observation_confirmed"
                ),
                updated_at=str(observation.get("observed_at") or _iso(float(event["created_at"]))),
                event=event,
            )
            continue

        if event_type == "release_superseded":
            apply(
                workstream_id=event.get("workstream_id"),
                head_sha=payload.get("pr_head_sha"),
                revision=payload.get("task_revision"),
                release_id=payload.get("candidate_id"),
                environment="",
                phase=90,
                status="blocked",
                deploy_status="superseded_readmission",
                verification_status="readmission_required",
                event=event,
            )
            continue

        if event_type == "release_proof_only":
            candidate = payload.get("candidate")
            truth = payload.get("scheduler_truth")
            release_candidate = payload.get("release_candidate")
            if not isinstance(candidate, Mapping) or candidate.get("task_id") != task_id:
                continue
            truth = truth if isinstance(truth, Mapping) else {}
            release_candidate = release_candidate if isinstance(release_candidate, Mapping) else {}
            apply(
                workstream_id=candidate.get("workstream_id"),
                head_sha=candidate.get("pr_head_sha"),
                revision=candidate.get("task_revision"),
                release_id=candidate.get("candidate_id"),
                environment=candidate.get("target_id"),
                phase=60,
                status="merged",
                deploy_status="proof_only",
                verification_status="merged_proof",
                pr_url=_release_candidate_pr_url(release_candidate),
                merge_sha=str(truth.get("merge_commit_sha") or ""),
                updated_at=str(payload.get("created_at") or _iso(float(event["created_at"]))),
                event=event,
            )
            continue

        if event_type in {
            "target_lane_closure_pending",
            "target_lane_closure_observed",
            "target_lane_closure_completed",
            "target_lane_closure_stalled",
        }:
            if event_type == "target_lane_closure_pending":
                action = payload
                receipt: Mapping[str, Any] = {}
                closure_status = "pending"
            else:
                action_raw = payload.get("action")
                receipt_raw = payload.get("receipt")
                action = action_raw if isinstance(action_raw, Mapping) else {}
                receipt = receipt_raw if isinstance(receipt_raw, Mapping) else {}
                closure_status = str(receipt.get("status") or "parked")
            if action.get("task_id") != task_id:
                continue
            pr_url, head_sha, merge_sha = _release_identity_projection(
                str(action.get("anchor_pr_identity") or "")
            )
            if not head_sha and action.get("binding_kind") == "parked_admission":
                parked = action.get("parked_admission")
                parked_head = (
                    parked.get("expected_head_sha")
                    if isinstance(parked, Mapping)
                    else None
                )
                parked_pr = parked.get("pr_number") if isinstance(parked, Mapping) else None
                if (
                    isinstance(parked_head, str)
                    and re.fullmatch(r"[0-9a-f]{40}", parked_head)
                    and isinstance(parked_pr, int)
                    and not isinstance(parked_pr, bool)
                    and parked_pr > 0
                ):
                    head_sha = parked_head
                    pr_url = f"https://github.com/{action.get('target_id')}/pull/{parked_pr}"
            if not head_sha:
                continue
            if closure_status == "pending":
                status = "verifying"
                deploy_status = "lane_closure_pending"
                verification_status = "pending"
                phase = 120
                updated_at = _iso(float(event["created_at"]))
            elif closure_status == "submitted":
                status = "verifying"
                deploy_status = "lane_closure_submitted"
                verification_status = "submitted"
                phase = 130
                updated_at = str(receipt.get("observed_at") or _iso(float(event["created_at"])))
            elif closure_status == "released":
                status = "production" if action.get("contour") == "release:production" else "merged"
                deploy_status = "lane_released"
                verification_status = "released"
                phase = 140
                updated_at = str(receipt.get("observed_at") or _iso(float(event["created_at"])))
            else:
                status = "failed"
                deploy_status = "lane_closure_parked"
                verification_status = "parked"
                phase = 140
                updated_at = str(receipt.get("observed_at") or _iso(float(event["created_at"])))
            apply(
                workstream_id=action.get("workstream_id"),
                head_sha=head_sha,
                revision=action.get("task_revision"),
                release_id=action.get("closure_id"),
                environment=action.get("target_id"),
                phase=phase,
                status=status,
                deploy_status=deploy_status,
                verification_status=verification_status,
                pr_url=pr_url,
                merge_sha=merge_sha,
                updated_at=updated_at,
                event=event,
            )
            continue

        if event_type == "release_completed":
            receipt = payload.get("receipt")
            if not isinstance(receipt, Mapping) or receipt.get("task_id") != task_id:
                continue
            contour = receipt.get("contour")
            deploy_identity = receipt.get("deploy_identity")
            repo_done = contour == "release:done" and deploy_identity is None
            production = (
                contour == "release:production"
                and isinstance(deploy_identity, str)
                and deploy_identity.startswith("hosted-release-v1:")
            )
            if not (repo_done or production):
                apply(
                    workstream_id=receipt.get("workstream_id"),
                    head_sha=receipt.get("pr_head_sha"),
                    revision=receipt.get("task_revision"),
                    release_id=receipt.get("candidate_id"),
                    environment="",
                    phase=110,
                    status="failed",
                    deploy_status="parked",
                    verification_status="invalid_contour_receipt",
                    pr_url=str(receipt.get("pr_url") or ""),
                    merge_sha=str(receipt.get("merge_sha") or ""),
                    updated_at=str(
                        receipt.get("completed_at") or _iso(float(event["created_at"]))
                    ),
                    event=event,
                )
                continue
            apply(
                workstream_id=receipt.get("workstream_id"),
                head_sha=receipt.get("pr_head_sha"),
                revision=receipt.get("task_revision"),
                release_id=receipt.get("candidate_id"),
                environment="production" if production else "repository",
                phase=110,
                status="production" if production else "merged",
                deploy_status="production" if production else "repository_done",
                verification_status="passed",
                pr_url=str(receipt.get("pr_url") or ""),
                merge_sha=str(receipt.get("merge_sha") or ""),
                updated_at=str(receipt.get("completed_at") or _iso(float(event["created_at"]))),
                event=event,
            )
            continue
        apply(
            workstream_id=event.get("workstream_id"),
            head_sha=payload.get("pr_head_sha"),
            revision=payload.get("task_revision"),
            release_id=payload.get("candidate_id"),
            environment="",
            phase=100,
            status="failed",
            deploy_status="parked",
            verification_status="failed",
            event=event,
        )
    return sorted(result.values(), key=lambda item: (str(item["updated_at"]), str(item["release_id"])))


def _release_candidate_pr_url(candidate: Mapping[str, Any]) -> str:
    repo = candidate.get("repo")
    pr_number = candidate.get("pr_number")
    if (
        not isinstance(repo, str)
        or repo.count("/") != 1
        or not all(part and part.replace("-", "").replace("_", "").replace(".", "").isalnum() for part in repo.split("/"))
        or isinstance(pr_number, bool)
        or not isinstance(pr_number, int)
        or pr_number < 1
    ):
        return ""
    return f"https://github.com/{repo}/pull/{pr_number}"


def _release_identity_projection(identity: str) -> tuple[str, str, str]:
    parts = identity.split(":")
    if (
        len(parts) != 5
        or parts[0] != "github-pr-v1"
        or parts[1].count("/") != 1
        or not parts[2].isdigit()
        or int(parts[2]) < 1
        or len(parts[3]) != 40
        or len(parts[4]) != 40
        or any(character not in "0123456789abcdef" for character in parts[3] + parts[4])
    ):
        return "", "", ""
    repo = parts[1]
    if not all(
        part and part.replace("-", "").replace("_", "").replace(".", "").isalnum()
        for part in repo.split("/")
    ):
        return "", "", ""
    return f"https://github.com/{repo}/pull/{int(parts[2])}", parts[3], parts[4]


def _incident_projection(task_id: str, events: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    # Keep the append-only audit in SQLite while exposing one current row per
    # causal incident.  A later resolution event replaces the old open/parked
    # projection instead of leaving historical incident noise active.
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for event in events:
        if event.get("event_type") != "incident_policy":
            continue
        payload = event.get("payload")
        if not isinstance(payload, Mapping):
            continue
        workstream_id = str(event.get("workstream_id") or "")
        fingerprint = str(payload.get("fingerprint") or event["event_id"])
        result[(workstream_id, fingerprint)] = {
            "incident_id": str(event["event_id"]),
            "task_id": task_id,
            "workstream_id": event.get("workstream_id"),
            "revision": int(payload.get("revision") or 1),
            "status": _incident_status(str(payload.get("status") or "open")),
            "fingerprint": fingerprint,
            "summary": str(payload.get("summary") or "Инцидент зарегистрирован."),
            "decision": str(payload.get("decision") or ""),
            "attempt": int(payload.get("attempt") or 0),
            "updated_at": str(payload.get("updated_at") or _iso(float(event["created_at"]))),
        }
    return sorted(
        result.values(),
        key=lambda item: (
            str(item["workstream_id"] or ""),
            str(item["fingerprint"]),
        ),
    )


def _release_row_from_receipt(
    task_id: str,
    receipt: Mapping[str, Any],
    event: Mapping[str, Any],
) -> dict[str, Any]:
    production = (
        receipt.get("contour") == "release:production"
        and isinstance(receipt.get("deploy_identity"), str)
        and str(receipt.get("deploy_identity")).startswith("hosted-release-v1:")
    )
    return {
        "release_id": str(receipt["candidate_id"]),
        "task_id": task_id,
        "workstream_id": receipt.get("workstream_id"),
        "revision": int(receipt.get("task_revision") or 1),
        "status": "production" if production else "merged",
        "pr_url": str(receipt.get("pr_url") or ""),
        "pr_number": _pr_number(str(receipt.get("pr_url") or "")),
        "head_sha": str(receipt.get("pr_head_sha") or ""),
        "merge_sha": str(receipt.get("merge_sha") or ""),
        "environment": "production" if production else "repository",
        "deploy_status": "production" if production else "repository_done",
        "verification_status": "passed",
        "updated_at": str(receipt.get("completed_at") or _iso(float(event["created_at"]))),
    }


def _release_outcome_binding(event: Mapping[str, Any]) -> tuple[str, str] | None:
    """Return the immutable candidate/head pair for one release outcome."""

    payload = event.get("payload")
    if not isinstance(payload, Mapping):
        return None
    event_type = event.get("event_type")
    if event_type == "release_completed":
        receipt = payload.get("receipt")
        if not isinstance(receipt, Mapping):
            return None
        candidate_id = receipt.get("candidate_id")
        head_sha = receipt.get("pr_head_sha")
    elif event_type in {"release_stalled", "release_superseded"}:
        candidate_id = payload.get("candidate_id")
        head_sha = payload.get("pr_head_sha")
    elif event_type == "release_proof_only":
        candidate = payload.get("candidate")
        if not isinstance(candidate, Mapping):
            return None
        candidate_id = candidate.get("candidate_id")
        head_sha = candidate.get("pr_head_sha")
    else:
        return None
    if not isinstance(candidate_id, str) or not candidate_id or not isinstance(head_sha, str) or not head_sha:
        return None
    return candidate_id, head_sha


def _target_lane_closure_matches_task(event: Mapping[str, Any], task: Any) -> bool:
    """Accept only one exact task-revision terminal lane receipt as closure."""

    payload = event.get("payload")
    action = payload.get("action") if isinstance(payload, Mapping) else None
    receipt = payload.get("receipt") if isinstance(payload, Mapping) else None
    return bool(
        isinstance(action, Mapping)
        and isinstance(receipt, Mapping)
        and event.get("task_id") == task.task_id
        and action.get("task_id") == task.task_id
        and action.get("task_revision") == task.revision
        and receipt.get("task_id") == task.task_id
        and receipt.get("task_revision") == task.revision
        and receipt.get("closure_id") == action.get("closure_id")
        and receipt.get("status") in {"released", "parked"}
    )


def _pr_number(url: str) -> int | None:
    try:
        value = int(url.rstrip("/").rsplit("/", 1)[-1])
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _incident_status(raw: str) -> str:
    value = raw.lower()
    if value == "resolved" or "resolved" in value:
        return "resolved"
    if value == "parked" or "park" in value or "human_gate" in value or "failed_fail_closed" in value:
        return "parked"
    if any(marker in value for marker in ("retry", "successor", "arbiter", "application", "recover")):
        return "recovering"
    if any(marker in value for marker in ("failure", "incident", "investigat")):
        return "investigating"
    return "open"


def _verify_contour_evidence(passport: TaskPassport, terminal: TerminalEvidence) -> None:
    normalized_checks = " ".join(terminal.checks).lower()
    if not any(marker in normalized_checks for marker in ("passed", "success", "green", "пройден", "успеш")):
        raise SupervisorError("terminal checks do not independently prove a passing result")
    evidence = " ".join(terminal.evidence).lower()
    if passport.contour.startswith("release:"):
        manifest = passport.release_manifest
        if manifest is None:
            raise SupervisorError(
                "release terminal requires a finalized typed Passport release_manifest"
            )
        if not terminal.pr_identities:
            raise SupervisorError("release closure requires immutable PR identity")
        if tuple(terminal.pr_identities) != tuple(manifest.pr_identities):
            raise SupervisorError("release terminal PR identities differ from the final Passport manifest")
        if tuple(terminal.deploy_identities) != tuple(manifest.deploy_identities):
            raise SupervisorError("release terminal deploy identities differ from the final Passport manifest")
        if "origin/main" not in evidence and "origin_main" not in evidence:
            raise SupervisorError("release closure requires exact origin/main evidence")
    if passport.contour == "release:production":
        if not terminal.deploy_identities:
            raise SupervisorError("production closure requires immutable deploy identity")
        if not any(marker in evidence for marker in ("probe:healthy", "production:healthy", "prod:healthy")):
            raise SupervisorError("production closure requires independent healthy probe evidence")
    if passport.contour == "artifact" and "artifact:" not in evidence:
        raise SupervisorError("artifact closure requires immutable artifact evidence")


def _task_terminal_handoff(
    passport: TaskPassport,
    terminal_events: Sequence[Mapping[str, Any]],
) -> str:
    """Render one task-level attention after every declared stream closes."""

    verifier_evidence: list[str] = []
    pr_identities: list[str] = []
    deploy_identities: list[str] = []
    checks: list[str] = []
    summaries: list[str] = []
    for event in terminal_events:
        payload = event["payload"]
        contract = payload["contract"]
        verification = payload["independent_verification"]
        summaries.append(str(contract["summary_ru"]))
        verifier_evidence.extend(str(item) for item in verification["evidence"])
        checks.extend(str(item) for item in verification["checks"])
        pr_identities.extend(str(item) for item in contract.get("pr_identities", ()))
        deploy_identities.extend(str(item) for item in contract.get("deploy_identities", ()))
    # For a release, the concise handoff names the final immutable identities
    # from the terminal contract itself. Verifier evidence is a fallback only
    # for non-release contours, where PR/deploy identities do not exist.
    if passport.contour.startswith("release:") and pr_identities:
        evidence = [pr_identities[-1]]
        if passport.contour == "release:production" and deploy_identities:
            evidence.append(deploy_identities[-1])
    else:
        evidence = list(dict.fromkeys(verifier_evidence))[:2]
    evidence = list(dict.fromkeys(evidence))[:2]
    checks = list(dict.fromkeys(checks))[:4]
    summaries = list(dict.fromkeys(summaries))[:2]
    done_items = summaries or evidence
    done_lines = "\n".join(f"- {item}" for item in done_items)
    proof_line = f"Доказательства: {'; '.join(evidence)}\n" if evidence else ""
    limitation = "; ".join(passport.excluded_scope[:2]) or "существенных не заявлено"
    return (
        "Статус: Завершена — требуется приёмка\n"
        f"Задача: {passport.title}\n"
        f"Сделано:\n{done_lines}\n"
        f"{proof_line}"
        f"Проверки: {'; '.join(checks)}\n"
        f"Реальные ограничения: {limitation}\n"
        "Ответьте ровно «Задача принята»."
    )


def _projection_task_status(state: str) -> str:
    return {
        "active": "working",
        "waiting_release": "waiting_release",
        "recovering": "recovering",
        "parked": "parked",
        "acceptance_pending": "awaiting_acceptance",
        "accepted": "accepted",
    }.get(state, "working")


def _projection_workstream_status(state: str, task_events: Sequence[Mapping[str, Any]]) -> str:
    latest_release_type = next(
        (
            str(event.get("event_type"))
            for event in reversed(task_events)
            if event.get("event_type")
            in {
                "release_candidate_registered",
                "release_candidate_admitted",
                "release_wait",
                "release_reserved",
                "semantic_release_case",
                "release_action_observed",
                "release_superseded",
                "release_proof_only",
                "release_completed",
                "release_stalled",
            }
        ),
        None,
    )
    if latest_release_type == "release_stalled":
        return "blocked"
    if latest_release_type in {
        "release_candidate_registered",
        "release_candidate_admitted",
        "release_wait",
        "release_reserved",
        "semantic_release_case",
        "release_action_observed",
        "release_superseded",
        "release_proof_only",
    }:
        return "waiting_release"
    return {
        "started": "working",
        "working": "working",
        "waiting_release": "waiting_release",
        "recovering": "recovering",
        "blocked": "blocked",
        "technical_complete": "awaiting_acceptance",
        "acceptance_pending": "awaiting_acceptance",
        "parked": "parked",
    }.get(state, "working")


def _matching_current_terminal(
    task: Any,
    workstream: Any,
    events: Sequence[Mapping[str, Any]],
    registry: SupervisorRegistry,
) -> Mapping[str, Any] | None:
    executor = registry.current_executor(task.task_id, workstream.workstream_id)
    if executor is None:
        return None
    matched: list[Mapping[str, Any]] = []
    for event in events:
        if event.get("event_type") != "technical_terminal":
            continue
        payload = event.get("payload")
        contract = payload.get("contract") if isinstance(payload, Mapping) else None
        verification = payload.get("independent_verification") if isinstance(payload, Mapping) else None
        if not isinstance(contract, Mapping) or not isinstance(verification, Mapping):
            continue
        if (
            contract.get("task_revision") == task.revision
            and contract.get("workstream_revision") == workstream.revision
            and contract.get("executor_generation") == executor.executor_generation
            and payload.get("workstream_generation") == workstream.generation
            and event.get("executor_generation") == executor.executor_generation
            and verification.get("passed") is True
        ):
            matched.append(event)
    return matched[0] if len(matched) == 1 else None


def _latest_barrier_event(events: Sequence[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    matched = [
        event
        for event in events
        if event.get("event_type") == "technical_terminal"
        and isinstance(event.get("payload"), Mapping)
        and event["payload"].get("closure_barrier") is True
    ]
    return matched[-1] if matched else None


def _projection_blocker(
    status: str,
    stream_events: Sequence[Mapping[str, Any]],
    attention_records: Sequence[Mapping[str, Any]],
) -> str:
    if status != "blocked":
        return ""
    workstream_ids = {str(event.get("workstream_id")) for event in stream_events}
    for item in reversed(attention_records):
        payload = item.get("payload")
        if not isinstance(payload, Mapping) or str(payload.get("workstream_id")) not in workstream_ids:
            continue
        if payload.get("kind") in {"human_gate", "serious_stall"}:
            return str(payload.get("handoff_ru") or payload.get("required_action"))[:500]
    for event in reversed(stream_events):
        payload = event.get("payload")
        if not isinstance(payload, Mapping):
            continue
        if event.get("event_type") == "release_stalled":
            return f"Release Train припаркован: {str(payload.get('error_code') or 'verified_failure')[:440]}"
        if event.get("event_type") == "incident_policy":
            summary = str(payload.get("summary") or "")
            if summary:
                return summary[:500]
    raise SupervisorError("blocked workstream has no durable strict-blocker evidence")


def _remaining_range(progress: int) -> str:
    ranges = {
        5: "≈6–9 проверяемых этапов",
        15: "≈5–8 проверяемых этапов",
        25: "≈4–7 проверяемых этапов",
        40: "≈3–6 проверяемых этапов",
        55: "≈3–5 проверяемых этапов",
        65: "≈2–4 проверяемых этапа",
        72: "≈2–3 проверяемых этапа",
        80: "≈1–3 проверяемых этапа",
        88: "≈1–2 проверяемых этапа",
        95: "≈1 проверяемый этап",
        100: "0 этапов",
    }
    return ranges[progress]


def _latest_event(events: Sequence[Mapping[str, Any]], event_type: str) -> Mapping[str, Any] | None:
    matched = [event for event in events if event.get("event_type") == event_type]
    return matched[-1] if matched else None


def _latest_timestamp(base_epoch: float, events: Sequence[Mapping[str, Any]]) -> str:
    latest = max([base_epoch, *(float(event["created_at"]) for event in events)])
    return _iso(latest)


def _passport_from_record(payload: Mapping[str, Any]) -> TaskPassport:
    from .orchestration_contracts import task_passport_from_mapping

    return task_passport_from_mapping(payload)


def _workstream_from_record(payload: Mapping[str, Any]) -> Workstream:
    from .orchestration_contracts import workstream_from_mapping

    return workstream_from_mapping(payload)


def _ensure_sanitized(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if SECRET_KEY_RE.search(str(key)):
                raise SupervisorError("contract contains a forbidden secret-like field")
            _ensure_sanitized(item)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            _ensure_sanitized(item)
    elif isinstance(value, str) and SECRET_VALUE_RE.search(value):
        raise SupervisorError("contract contains secret-like content")


def _machine(label: str, value: Any) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > 127
        or any(ord(character) < 33 for character in value)
    ):
        raise SupervisorError(f"{label} must be a bounded machine identifier")
    return value


def _bounded_id(value: str) -> str:
    if len(value) <= 127:
        return _machine("identifier", value)
    return _machine("identifier", value[:80] + ":" + _digest_text(value)[:40])


def _timestamp(value: str) -> None:
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except (TypeError, ValueError) as exc:
        raise SupervisorError("timestamp must be RFC3339") from exc
    if parsed.tzinfo is None:
        raise SupervisorError("timestamp must include timezone")


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _digest_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _digest_json(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
