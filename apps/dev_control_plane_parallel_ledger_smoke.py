"""Smoke-check the parallel task ledger MVP state machine."""

from __future__ import annotations

from tempfile import TemporaryDirectory
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (SRC, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dev_control_plane.parallel_ledger import (  # noqa: E402
    PARALLEL_PING_PONG_ENABLED,
    ParallelLedgerPolicyError,
    ParallelTaskLedger,
)


def main() -> int:
    with TemporaryDirectory(prefix="dev-control-plane-parallel-ledger-") as tmp:
        state_dir = Path(tmp) / "state"
        ledger = ParallelTaskLedger.from_state_dir(state_dir)

        first = ledger.submit_task(
            target_id="wb-core",
            task_text="Task from ChatGPT project A",
            source="chatgpt-project-a",
            chat_id="chat-a",
            idempotency_key="same-request",
            now="2026-05-09T00:00:00Z",
        )
        duplicate = ledger.submit_task(
            target_id="wb-core",
            task_text="Task from ChatGPT project A duplicate",
            source="chatgpt-project-a",
            chat_id="chat-a",
            idempotency_key="same-request",
            now="2026-05-09T00:00:01Z",
        )
        if duplicate.task_id != first.task_id:
            raise AssertionError("idempotency_key must return the existing task in the same target epoch")
        if first.batch_id is not None or first.release_group is not None:
            raise AssertionError("batch/release_group must be optional")
        if first.parallel_ping_pong_enabled or PARALLEL_PING_PONG_ENABLED:
            raise AssertionError("parallel-flow must keep ping-pong/server-side curator disabled")

        second = ledger.submit_task(
            target_id="wb-core",
            task_text="Task from a different source without batch",
            source="mcp-tool-b",
            chat_id="chat-b",
            now="2026-05-09T00:00:02Z",
        )
        third = ledger.submit_task(
            target_id="wb-core",
            task_text="Task in an optional release group",
            source="api-import",
            release_group="release-2026-05-09",
            now="2026-05-09T00:00:03Z",
        )
        if {first.source, second.source, third.source} != {"chatgpt-project-a", "mcp-tool-b", "api-import"}:
            raise AssertionError("tasks from multiple sources must share one target ledger")
        if len({first.promotion_epoch, second.promotion_epoch, third.promotion_epoch}) != 1:
            raise AssertionError("multi-source tasks should share the current target promotion epoch")

        ledger.bind_managed_run(first.task_id, "mcp-managed-first", now="2026-05-09T00:01:00Z")
        ledger.bind_managed_run(second.task_id, "mcp-managed-second", now="2026-05-09T00:01:01Z")
        ledger.bind_managed_run(third.task_id, "mcp-managed-third", now="2026-05-09T00:01:02Z")
        ledger.mark_verifier_passed(second.task_id, now="2026-05-09T00:02:00Z")
        ledger.mark_verifier_passed(first.task_id, now="2026-05-09T00:02:01Z")

        selected = ledger.select_first_finished_eligible_candidate(target_id="wb-core")
        if selected is None or selected.task_id != second.task_id:
            raise AssertionError(f"first verifier-passed candidate must be selected first: {selected}")

        try:
            ledger.mark_first_candidate_auto_promoting_first(
                target_id="wb-core",
                explicit_policy=False,
                now="2026-05-09T00:03:00Z",
            )
        except ParallelLedgerPolicyError:
            pass
        else:
            raise AssertionError("auto_promoting_first must require explicit policy")
        queued = ledger.snapshot().tasks[second.task_id]
        if queued.status != "promotion_queued":
            raise AssertionError(f"candidate should be queued, not promoted without explicit policy: {queued}")

        promoted = ledger.mark_first_candidate_auto_promoting_first(
            target_id="wb-core",
            explicit_policy=True,
            now="2026-05-09T00:04:00Z",
        )
        if promoted.task_id != second.task_id or promoted.status != "auto_promoting_first":
            raise AssertionError(f"explicit policy should promote first candidate: {promoted}")
        ledger.bind_production_lane_run(second.task_id, "mcp-prod-second", now="2026-05-09T00:05:00Z")
        ledger.mark_production_complete(second.task_id, now="2026-05-09T00:06:00Z")
        after = ledger.snapshot()
        if after.tasks[second.task_id].status != "production_complete":
            raise AssertionError("winning task must become production_complete")
        if after.tasks[first.task_id].status != "refresh_required":
            raise AssertionError(f"verifier-passed loser must require refresh: {after.tasks[first.task_id]}")
        if after.tasks[third.task_id].status != "frozen_base_stale":
            raise AssertionError(f"running loser must be frozen_base_stale: {after.tasks[third.task_id]}")
        for loser_id in (first.task_id, third.task_id):
            try:
                ledger.ensure_promotable(loser_id)
            except ParallelLedgerPolicyError:
                pass
            else:
                raise AssertionError("frozen candidates must not be promotable without refresh")

        status = ledger.status()
        if status.get("parallel_ping_pong_enabled") is not False or status.get("intake_model") != "multi_source_per_target_epoch":
            raise AssertionError(f"ledger status must expose frozen ping-pong and intake model: {status}")

        reloaded = ParallelTaskLedger.from_state_dir(state_dir)
        if len(reloaded.list_tasks(target_id="wb-core")) != 3:
            raise AssertionError("ledger should persist tasks as machine-readable JSON")

    print("dev-control-plane-parallel-ledger-smoke: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
