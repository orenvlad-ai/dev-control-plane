"""Execution and promotion coordinator foundation for parallel tasks.

This module is intentionally state-machine only.  It can bind fake managed
run ids, reconcile explicit run results and prepare/fake promotion decisions,
but it never starts Codex, sprint/ping-pong or real production-lane work.
"""

from __future__ import annotations

from collections.abc import Sequence as SequenceABC
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Literal, Mapping, Sequence
import uuid

from dev_control_plane.parallel_ledger import (
    PARALLEL_PING_PONG_ENABLED,
    ParallelLedgerError,
    ParallelLedgerPolicyError,
    ParallelTaskLedger,
    PromotionCandidate,
    TaskRecord,
    promotion_state_summary,
    task_record_summary,
)
from dev_control_plane.state_layout import safe_state_component


ParallelPromotionMode = Literal["dry_run", "fake_complete"]
BUSY_PROMOTION_STATES = {"auto_promoting_first", "production_lane_running"}


@dataclass(frozen=True)
class ParallelPromotionDecision:
    status: str
    allowed: bool
    target_id: str
    promotion_epoch: str | None
    task_id: str | None = None
    selected_task_id: str | None = None
    blockers: tuple[str, ...] = ()
    mode: str = "dry_run"
    production_lane_started: bool = False
    fake_production_run_id: str | None = None


class ParallelCoordinatorError(ValueError):
    pass


class ParallelExecutionCoordinator:
    def __init__(self, ledger: ParallelTaskLedger) -> None:
        self.ledger = ledger

    def start_managed_execution(
        self,
        task_id: str,
        *,
        starter_mode: str = "fake",
        run_id: str | None = None,
        now: str | None = None,
    ) -> dict[str, Any]:
        if starter_mode != "fake":
            raise ParallelCoordinatorError("parallel execution MVP supports only starter_mode=fake")
        task = self.ledger.get_task(task_id)
        if task.managed_run_id:
            return {
                "status": "managed_run_running",
                "task": task_record_summary(task),
                "task_id": task.task_id,
                "run_id": task.managed_run_id,
                "idempotent_replay": True,
                "starter_mode": starter_mode,
                "codex_started": False,
                "ping_pong_started": False,
                "production_lane_started": False,
            }
        bound = self.ledger.bind_managed_run(task.task_id, run_id or _new_parallel_run_id("pmr"), now=now)
        return {
            "status": "managed_run_running",
            "task": task_record_summary(bound),
            "task_id": bound.task_id,
            "run_id": bound.managed_run_id,
            "idempotent_replay": False,
            "starter_mode": starter_mode,
            "execution_mode": "managed_clone_only",
            "codex_started": False,
            "ping_pong_started": False,
            "production_lane_started": False,
        }

    def reconcile_managed_run(
        self,
        task_id: str,
        *,
        run_status: str,
        verifier_status: str | None = None,
        changed_files: Sequence[str] = (),
        verifier_summary: Mapping[str, Any] | None = None,
        blocker: str | None = None,
        now: str | None = None,
    ) -> dict[str, Any]:
        task = self.ledger.reconcile_managed_run_result(
            task_id,
            run_status=run_status,
            verifier_status=verifier_status,
            changed_files=changed_files,
            verifier_summary=verifier_summary,
            blocker=blocker,
            now=now,
        )
        return {
            "status": task.status,
            "task": task_record_summary(task),
            "task_id": task.task_id,
            "run_id": task.managed_run_id,
            "candidate_created": task.status == "verifier_passed",
            "production_lane_started": False,
            "ping_pong_started": False,
        }

    def list_candidates(
        self,
        *,
        target_id: str | None = None,
        promotion_epoch: str | None = None,
    ) -> dict[str, Any]:
        snapshot = self.ledger.snapshot()
        candidates = []
        for candidate in self.ledger.list_candidates(target_id=target_id, promotion_epoch=promotion_epoch):
            task = snapshot.tasks.get(candidate.task_id)
            candidates.append(_candidate_summary(candidate, task, self._promotion_blockers(task) if task else ("unknown task",)))
        return {
            "status": "ok",
            "candidates": candidates,
            "parallel_ping_pong_enabled": PARALLEL_PING_PONG_ENABLED,
        }

    def promote_task(
        self,
        task_id: str,
        *,
        allow_auto_first_promotion: bool = False,
        mode: ParallelPromotionMode = "dry_run",
        now: str | None = None,
    ) -> dict[str, Any]:
        if mode not in {"dry_run", "fake_complete"}:
            return _decision_payload(
                ParallelPromotionDecision(
                    status="denied",
                    allowed=False,
                    target_id="",
                    promotion_epoch=None,
                    task_id=task_id,
                    blockers=("parallel promotion MVP allows only mode=dry_run or mode=fake_complete",),
                    mode=mode,
                )
            )
        task = self.ledger.get_task(task_id)
        blockers = self._promotion_blockers(task)
        if blockers:
            return _decision_payload(
                ParallelPromotionDecision(
                    status="blocked",
                    allowed=False,
                    target_id=task.target_id,
                    promotion_epoch=task.promotion_epoch,
                    task_id=task.task_id,
                    blockers=blockers,
                    mode=mode,
                ),
                task=task,
            )
        if task.status == "auto_promoting_first":
            final_task = task
            fake_production_run_id = None
            status = "auto_promoting_first"
            if mode == "fake_complete":
                fake_production_run_id = _new_parallel_run_id("ppr")
                self.ledger.bind_production_lane_run(task.task_id, fake_production_run_id, now=now)
                final_task = self.ledger.mark_production_complete(task.task_id, now=now)
                status = "production_complete"
            return _decision_payload(
                ParallelPromotionDecision(
                    status=status,
                    allowed=True,
                    target_id=final_task.target_id,
                    promotion_epoch=final_task.promotion_epoch,
                    task_id=final_task.task_id,
                    selected_task_id=final_task.task_id,
                    mode=mode,
                    production_lane_started=False,
                    fake_production_run_id=fake_production_run_id,
                ),
                task=final_task,
            )
        selected = self._first_safe_candidate(task.target_id, task.promotion_epoch)
        if selected is None:
            return _decision_payload(
                ParallelPromotionDecision(
                    status="blocked",
                    allowed=False,
                    target_id=task.target_id,
                    promotion_epoch=task.promotion_epoch,
                    task_id=task.task_id,
                    blockers=("no eligible promotion candidate",),
                    mode=mode,
                ),
                task=task,
            )
        if selected.task_id != task.task_id:
            return _decision_payload(
                ParallelPromotionDecision(
                    status="blocked",
                    allowed=False,
                    target_id=task.target_id,
                    promotion_epoch=task.promotion_epoch,
                    task_id=task.task_id,
                    selected_task_id=selected.task_id,
                    blockers=(f"task is not the first-finished eligible candidate: {selected.task_id}",),
                    mode=mode,
                ),
                task=task,
            )
        if not allow_auto_first_promotion:
            try:
                self.ledger.mark_candidate_auto_promoting_first(
                    task.task_id,
                    explicit_policy=False,
                    now=now,
                )
            except ParallelLedgerPolicyError as exc:
                queued = self.ledger.get_task(task.task_id)
                return _decision_payload(
                    ParallelPromotionDecision(
                        status="promotion_queued",
                        allowed=False,
                        target_id=task.target_id,
                        promotion_epoch=task.promotion_epoch,
                        task_id=task.task_id,
                        selected_task_id=task.task_id,
                        blockers=(str(exc),),
                        mode=mode,
                    ),
                    task=queued,
                )
        promoted = self.ledger.mark_candidate_auto_promoting_first(
            task.task_id,
            explicit_policy=True,
            now=now,
        )
        fake_production_run_id = None
        final_task = promoted
        status = "auto_promoting_first"
        if mode == "fake_complete":
            fake_production_run_id = _new_parallel_run_id("ppr")
            self.ledger.bind_production_lane_run(promoted.task_id, fake_production_run_id, now=now)
            final_task = self.ledger.mark_production_complete(promoted.task_id, now=now)
            status = "production_complete"
        return _decision_payload(
            ParallelPromotionDecision(
                status=status,
                allowed=True,
                target_id=final_task.target_id,
                promotion_epoch=final_task.promotion_epoch,
                task_id=final_task.task_id,
                selected_task_id=final_task.task_id,
                mode=mode,
                production_lane_started=False,
                fake_production_run_id=fake_production_run_id,
            ),
            task=final_task,
        )

    def promote_next_safe_candidate(
        self,
        target_id: str,
        *,
        promotion_epoch: str | None = None,
        allow_auto_first_promotion: bool = False,
        mode: ParallelPromotionMode = "dry_run",
        now: str | None = None,
    ) -> dict[str, Any]:
        target = safe_state_component(target_id, "target_id")
        candidates = [
            candidate
            for candidate in self.ledger.list_candidates(target_id=target, promotion_epoch=promotion_epoch)
            if candidate.status in {"eligible", "promotion_queued"}
        ]
        skipped: list[dict[str, Any]] = []
        for candidate in candidates:
            task = self.ledger.snapshot().tasks.get(candidate.task_id)
            blockers = self._promotion_blockers(task)
            if blockers:
                skipped.append(_candidate_summary(candidate, task, blockers))
                continue
            return self.promote_task(
                candidate.task_id,
                allow_auto_first_promotion=allow_auto_first_promotion,
                mode=mode,
                now=now,
            )
        if not candidates:
            return _decision_payload(
                ParallelPromotionDecision(
                    status="blocked",
                    allowed=False,
                    target_id=target_id,
                    promotion_epoch=promotion_epoch,
                    blockers=("no eligible promotion candidate",),
                    mode=mode,
                )
            )
        payload = _decision_payload(
            ParallelPromotionDecision(
                status="blocked",
                allowed=False,
                target_id=target_id,
                promotion_epoch=promotion_epoch,
                blockers=("no safe eligible promotion candidate",),
                mode=mode,
            )
        )
        payload["skipped_candidates"] = skipped
        return payload

    def _first_safe_candidate(self, target_id: str, promotion_epoch: str | None) -> PromotionCandidate | None:
        for candidate in self.ledger.list_candidates(target_id=target_id, promotion_epoch=promotion_epoch):
            if candidate.status not in {"eligible", "promotion_queued"}:
                continue
            task = self.ledger.snapshot().tasks.get(candidate.task_id)
            if not self._promotion_blockers(task):
                return candidate
        return None

    def _promotion_blockers(self, task: TaskRecord | None) -> tuple[str, ...]:
        if task is None:
            return ("unknown task",)
        blockers: list[str] = []
        if task.refresh_required or task.status in {"frozen_base_stale", "refresh_required"}:
            blockers.append("task is frozen/stale and requires refresh before promotion")
        if task.status not in {"verifier_passed", "promotion_queued", "auto_promoting_first"}:
            blockers.append(f"task status is not promotable: {task.status}")
        if task.blocker and task.status != "promotion_queued":
            blockers.append(str(task.blocker))
        summary = dict(task.verifier_summary)
        if summary.get("forbidden_paths_clean") is False:
            blockers.append("verifier reported forbidden paths are not clean")
        for key in ("forbidden_paths_touched", "forbidden_paths", "forbidden_path_hits"):
            value = summary.get(key)
            if isinstance(value, SequenceABC) and not isinstance(value, (str, bytes)) and list(value):
                blockers.append(f"verifier reported {key}")
        state = self.ledger.target_promotion_state(task.target_id, promotion_epoch=task.promotion_epoch)
        if state is not None and state.status in BUSY_PROMOTION_STATES and state.first_candidate_task_id not in {None, task.task_id}:
            blockers.append(f"target promotion state is busy with {state.first_candidate_task_id}")
        if state is not None and state.status == "production_complete" and state.completed_task_id != task.task_id:
            blockers.append("promotion epoch is already production_complete")
        return tuple(dict.fromkeys(blockers))


def target_promotion_plan(ledger: ParallelTaskLedger, target_id: str, promotion_epoch: str | None = None) -> dict[str, Any]:
    state = ledger.target_promotion_state(target_id, promotion_epoch=promotion_epoch)
    return promotion_state_summary(state, target_id=target_id, promotion_epoch=promotion_epoch)


def _candidate_summary(candidate: PromotionCandidate, task: TaskRecord | None, blockers: Sequence[str]) -> dict[str, Any]:
    return {
        "task_id": candidate.task_id,
        "target_id": candidate.target_id,
        "promotion_epoch": candidate.promotion_epoch,
        "managed_run_id": candidate.managed_run_id,
        "status": candidate.status,
        "verifier_passed_at": candidate.verifier_passed_at,
        "selected_at": candidate.selected_at,
        "blocker": candidate.blocker,
        "task_status": None if task is None else task.status,
        "refresh_required": None if task is None else task.refresh_required,
        "changed_files": [] if task is None else list(task.changed_files),
        "promotion_blockers": list(blockers),
    }


def _decision_payload(decision: ParallelPromotionDecision, *, task: TaskRecord | None = None) -> dict[str, Any]:
    payload = asdict(decision)
    payload["blockers"] = list(decision.blockers)
    payload["parallel_ping_pong_enabled"] = PARALLEL_PING_PONG_ENABLED
    payload["ping_pong_started"] = False
    payload["codex_started"] = False
    payload["real_production_lane_started"] = False
    if task is not None:
        payload["task"] = task_record_summary(task)
    return payload


def _new_parallel_run_id(prefix: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return safe_state_component(f"{prefix}-{timestamp}-{uuid.uuid4().hex[:10]}", "run_id")
