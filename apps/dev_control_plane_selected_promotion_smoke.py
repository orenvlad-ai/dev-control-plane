"""Smoke-check deterministic selected Merge & Deploy planning."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (SRC, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dev_control_plane.selected_promotion import SelectedPromotionCandidate, plan_selected_promotion  # noqa: E402


def main() -> None:
    docs = _candidate("task-docs", ["docs/architecture/01_control_plane_mvp.md"], finished_at="2026-05-09T08:30:00Z")
    ui = _candidate("task-ui", ["src/dev_control_plane/server.py"], finished_at="2026-05-09T08:31:00Z")
    broad = _candidate("task-broad", ["src/dev_control_plane/server.py", "src/dev_control_plane/mcp.py"], finished_at="2026-05-09T08:32:00Z")
    failed = _candidate("task-failed", [], lifecycle_status="failed")
    frozen = _candidate("task-frozen", ["README.md"], lifecycle_status="refresh_required", status="refresh_required")

    plan = plan_selected_promotion([broad, docs, ui, failed, frozen], target_id="wb-core")
    ordered_ids = [candidate.candidate_id for candidate in plan.ordered]
    if ordered_ids != ["task-docs", "task-ui"]:
        raise AssertionError(f"planner should order low-risk non-overlapping candidates deterministically: {plan.to_dict()}")
    if [candidate.candidate_id for candidate in plan.refresh_required] != ["task-frozen", "task-broad"]:
        raise AssertionError(f"frozen and same-file overlap candidates must require refresh: {plan.to_dict()}")
    if [candidate.candidate_id for candidate in plan.blocked] != ["task-failed"]:
        raise AssertionError(f"failed candidate must be blocked: {plan.to_dict()}")
    if "production lane remains serial" not in " ".join(plan.reasons):
        raise AssertionError(f"planner should document serial production semantics: {plan.to_dict()}")

    mismatch = _candidate("task-other-target", ["README.md"], target_id="other")
    mismatch_plan = plan_selected_promotion([mismatch], target_id="wb-core")
    if mismatch_plan.status != "blocked" or not mismatch_plan.blocked:
        raise AssertionError(f"target mismatch must fail closed: {mismatch_plan.to_dict()}")

    print("dev-control-plane-selected-promotion-smoke passed")


def _candidate(
    candidate_id: str,
    files: list[str],
    *,
    target_id: str = "wb-core",
    lifecycle_status: str = "ready_for_promotion",
    status: str = "verifier_passed",
    finished_at: str = "2026-05-09T08:00:00Z",
) -> SelectedPromotionCandidate:
    return SelectedPromotionCandidate(
        candidate_id=candidate_id,
        selected_id=candidate_id,
        selection_type="task_id",
        target_id=target_id,
        source_kind="parallel_task",
        status=status,
        lifecycle_status=lifecycle_status,
        task_id=candidate_id,
        changed_files=tuple(files),
        finished_at=finished_at,
    )


if __name__ == "__main__":
    main()
