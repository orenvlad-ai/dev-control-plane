"""Smoke-check parallel execution/reconciliation/promotion coordinator."""

from __future__ import annotations

from pathlib import Path
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (SRC, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dev_control_plane.parallel_coordinator import ParallelExecutionCoordinator  # noqa: E402
from dev_control_plane.parallel_ledger import ParallelLedgerPolicyError, ParallelTaskLedger  # noqa: E402


def main() -> int:
    with TemporaryDirectory(prefix="dev-control-plane-parallel-coordinator-") as tmp:
        ledger = ParallelTaskLedger.from_state_dir(Path(tmp) / "state")
        coordinator = ParallelExecutionCoordinator(ledger)

        chat_a = ledger.submit_task(
            target_id="wb-core",
            task_text="Task from chat A",
            source="chat-a",
            source_chat="chat-a",
            idempotency_key="task-a",
            now="2026-05-09T00:00:00Z",
        )
        chat_b = ledger.submit_task(
            target_id="wb-core",
            task_text="Task from chat B",
            source="chat-b",
            source_chat="chat-b",
            now="2026-05-09T00:00:01Z",
        )
        idle = ledger.submit_task(
            target_id="wb-core",
            task_text="Submitted only",
            source="chat-c",
            now="2026-05-09T00:00:02Z",
        )
        duplicate = ledger.submit_task(
            target_id="wb-core",
            task_text="duplicate",
            source="chat-a",
            idempotency_key="task-a",
            now="2026-05-09T00:00:03Z",
        )
        if duplicate.task_id != chat_a.task_id:
            raise AssertionError("submit idempotency must not create duplicate tasks")
        if ledger.get_task(idle.task_id).status != "submitted":
            raise AssertionError("submit without start must remain state-only/submitted")

        start_a = coordinator.start_managed_execution(chat_a.task_id, run_id="pmr-chat-a", now="2026-05-09T00:01:00Z")
        start_b = coordinator.start_managed_execution(chat_b.task_id, run_id="pmr-chat-b", now="2026-05-09T00:01:01Z")
        for started in (start_a, start_b):
            if started.get("status") != "managed_run_running" or started.get("codex_started") is not False:
                raise AssertionError(f"fake managed start must bind only state, not Codex: {started}")
            if started.get("ping_pong_started") is not False or started.get("production_lane_started") is not False:
                raise AssertionError(f"parallel execution must not call ping-pong or production: {started}")
        replay = coordinator.start_managed_execution(chat_a.task_id, now="2026-05-09T00:01:02Z")
        if replay.get("idempotent_replay") is not True or replay.get("run_id") != "pmr-chat-a":
            raise AssertionError(f"start execution should replay existing run binding: {replay}")

        passed = coordinator.reconcile_managed_run(
            chat_a.task_id,
            run_status="passed",
            verifier_status="passed",
            changed_files=["docs/example.md"],
            verifier_summary={"forbidden_paths_clean": True, "verifier_status": "passed"},
            now="2026-05-09T00:02:00Z",
        )
        if passed.get("status") != "verifier_passed" or passed.get("candidate_created") is not True:
            raise AssertionError(f"passed run should create verifier_passed candidate: {passed}")
        failed = coordinator.reconcile_managed_run(
            chat_b.task_id,
            run_status="failed",
            verifier_status="failed",
            blocker="fake run failed",
            now="2026-05-09T00:02:01Z",
        )
        if failed.get("status") != "failed":
            raise AssertionError(f"failed run should mark task failed: {failed}")

        queued = coordinator.promote_task(chat_a.task_id, allow_auto_first_promotion=False, now="2026-05-09T00:03:00Z")
        if queued.get("status") != "promotion_queued" or queued.get("production_lane_started") is not False:
            raise AssertionError(f"without explicit policy promotion must queue only: {queued}")
        promoted = coordinator.promote_task(chat_a.task_id, allow_auto_first_promotion=True, now="2026-05-09T00:04:00Z")
        if promoted.get("status") != "auto_promoting_first" or promoted.get("real_production_lane_started") is not False:
            raise AssertionError(f"explicit policy should mark auto_promoting_first without real production: {promoted}")

    with TemporaryDirectory(prefix="dev-control-plane-parallel-freeze-") as tmp:
        ledger = ParallelTaskLedger.from_state_dir(Path(tmp) / "state")
        coordinator = ParallelExecutionCoordinator(ledger)
        first = _submitted_started_passed(ledger, coordinator, "first", "2026-05-09T01:00:00Z")
        second = _submitted_started_passed(ledger, coordinator, "second", "2026-05-09T01:00:01Z")
        completed = coordinator.promote_next_safe_candidate(
            "wb-core",
            allow_auto_first_promotion=True,
            mode="fake_complete",
            now="2026-05-09T01:05:00Z",
        )
        if completed.get("status") != "production_complete" or completed.get("fake_production_run_id") is None:
            raise AssertionError(f"fake completion should mark production_complete: {completed}")
        if ledger.get_task(first.task_id).status != "production_complete":
            raise AssertionError("first verifier-passed task should be fake-completed")
        loser = ledger.get_task(second.task_id)
        if loser.status != "refresh_required" or loser.refresh_required is not True:
            raise AssertionError(f"loser should require refresh after production_complete: {loser}")
        try:
            ledger.ensure_promotable(second.task_id)
        except ParallelLedgerPolicyError:
            pass
        else:
            raise AssertionError("frozen/refresh_required candidate must not be promotable")
        late = coordinator.reconcile_managed_run(
            second.task_id,
            run_status="passed",
            verifier_status="passed",
            changed_files=["late.md"],
            now="2026-05-09T01:06:00Z",
        )
        if late.get("task", {}).get("status") != "refresh_required":
            raise AssertionError(f"late result after freeze must not become promotable: {late}")

    with TemporaryDirectory(prefix="dev-control-plane-parallel-dispatcher-") as tmp:
        ledger = ParallelTaskLedger.from_state_dir(Path(tmp) / "state")
        coordinator = ParallelExecutionCoordinator(ledger)
        unsafe = _submitted_started_passed(
            ledger,
            coordinator,
            "unsafe",
            "2026-05-09T02:00:00Z",
            verifier_summary={"forbidden_paths_clean": False, "forbidden_paths_touched": ["runtime/secret"]},
        )
        safe = _submitted_started_passed(
            ledger,
            coordinator,
            "safe",
            "2026-05-09T02:00:01Z",
            verifier_summary={"forbidden_paths_clean": True},
        )
        blocked = ledger.submit_task(target_id="wb-core", task_text="blocked", source="chat-z", now="2026-05-09T02:00:02Z")
        ledger.bind_managed_run(blocked.task_id, "pmr-blocked", now="2026-05-09T02:01:00Z")
        ledger.reconcile_managed_run_result(blocked.task_id, run_status="blocked", blocker="blocked", now="2026-05-09T02:02:00Z")
        chosen = coordinator.promote_next_safe_candidate(
            "wb-core",
            allow_auto_first_promotion=True,
            now="2026-05-09T02:03:00Z",
        )
        if chosen.get("task_id") != safe.task_id or chosen.get("status") != "auto_promoting_first":
            raise AssertionError(f"dispatcher must skip unsafe/blocked and choose safe candidate: {chosen}")
        unsafe_after = ledger.get_task(unsafe.task_id)
        if unsafe_after.status != "verifier_passed":
            raise AssertionError("unsafe candidate should remain unpromoted for operator action")
        busy = coordinator.promote_next_safe_candidate("wb-core", allow_auto_first_promotion=True)
        if busy.get("allowed") is not False:
            raise AssertionError(f"target promotion should stay serial while candidate is auto_promoting_first: {busy}")

    print("dev-control-plane-parallel-coordinator-smoke: ok")
    return 0


def _submitted_started_passed(
    ledger: ParallelTaskLedger,
    coordinator: ParallelExecutionCoordinator,
    name: str,
    now: str,
    *,
    verifier_summary: dict | None = None,
):
    task = ledger.submit_task(target_id="wb-core", task_text=f"task {name}", source=name, now=now)
    coordinator.start_managed_execution(task.task_id, run_id=f"pmr-{name}", now=now)
    coordinator.reconcile_managed_run(
        task.task_id,
        run_status="passed",
        verifier_status="passed",
        changed_files=[f"{name}.md"],
        verifier_summary=verifier_summary or {"forbidden_paths_clean": True},
        now=now,
    )
    return ledger.get_task(task.task_id)


if __name__ == "__main__":
    raise SystemExit(main())
