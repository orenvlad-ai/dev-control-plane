"""Smoke-check operator-facing lifecycle mapping for Monitoring cards."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (SRC, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dev_control_plane.operator_lifecycle import decorate_operator_lifecycle, operator_lifecycle_for  # noqa: E402


def main() -> None:
    managed_passed = operator_lifecycle_for(
        {
            "status": "passed",
            "execution_mode": "managed_clone_only",
            "verifier_status": "passed",
            "started_at": "2026-05-09T08:44:00Z",
            "finished_at": "2026-05-09T08:58:00Z",
        }
    )
    if managed_passed["status"] != "ready_for_promotion" or managed_passed["tone"] != "ready":
        raise AssertionError(f"managed verifier success must be amber ready, not green complete: {managed_passed}")
    if managed_passed["selectable"] is not True or "14м" not in managed_passed.get("time_summary", ""):
        raise AssertionError(f"ready managed run should be selectable and show duration: {managed_passed}")
    if managed_passed.get("time_summary") != "старт 09.05 08:44 · финиш 08:58 · 14м":
        raise AssertionError(f"same-day timing must include start date and finish clock: {managed_passed}")

    overnight = operator_lifecycle_for(
        {
            "status": "passed",
            "execution_mode": "managed_clone_only",
            "verifier_status": "passed",
            "started_at": "2026-05-10T23:58:00Z",
            "finished_at": "2026-05-11T00:04:00Z",
        }
    )
    if overnight.get("time_summary") != "старт 10.05 23:58 · финиш 11.05 00:04 · 6м":
        raise AssertionError(f"cross-day timing must include both dates: {overnight}")

    active_timing = operator_lifecycle_for(
        {
            "status": "running_codex",
            "current_stage": "running_codex",
            "started_at": "2026-05-11T00:25:00Z",
            "updated_at": "2026-05-11T00:26:00Z",
        }
    )
    if not str(active_timing.get("time_summary") or "").startswith("старт 11.05 00:25 · в работе · "):
        raise AssertionError(f"running timing must include start date and in-work label: {active_timing}")

    production_complete = operator_lifecycle_for(
        {
            "status": "completed",
            "execution_mode": "production_lane",
            "deploy_status": "post_deploy_passed",
            "production_lane_report": {"merge_commit": "abc123", "public_verify_status": "passed"},
        }
    )
    if production_complete["status"] != "production_complete" or production_complete["tone"] != "ok":
        raise AssertionError(f"production complete must be the only green success state: {production_complete}")

    blocked = operator_lifecycle_for({"status": "failed", "blocker": "verifier failed"})
    if blocked["tone"] != "bad" or blocked["selectable"] is not False:
        raise AssertionError(f"blocked/failed must be red and non-selectable: {blocked}")

    archived = operator_lifecycle_for({"status": "abandoned_by_operator", "archive_reason": "operator cleanup"})
    if archived["status"] != "archived" or archived["selectable"] is not False or archived["label"] != "Архив":
        raise AssertionError(f"operator-abandoned cleanup entries must be archived/non-actionable: {archived}")

    refresh = operator_lifecycle_for({"status": "frozen_base_stale", "refresh_required": True})
    if refresh["status"] != "refresh_required" or refresh["tone"] != "refresh":
        raise AssertionError(f"frozen/stale candidate must require refresh: {refresh}")

    separate = operator_lifecycle_for({"status": "ready_for_separate_deploy", "separate_deploy_reason": "same-file group overlap"})
    if separate["status"] != "ready_for_separate_deploy" or separate["tone"] != "ready" or separate["selectable"] is not True:
        raise AssertionError(f"deferred conflict candidate must stay yellow/selectable for separate deploy: {separate}")

    partial = operator_lifecycle_for({"status": "partially_deployed"})
    if partial["status"] != "partially_deployed" or partial["tone"] != "ready" or partial["label"] != "Задеплоено частично":
        raise AssertionError(f"partial group deploy must be warning/ready, not red blocker: {partial}")

    running = operator_lifecycle_for({"status": "running_codex", "current_stage": "running_codex"})
    if running["status"] != "running" or running["tone"] != "running":
        raise AssertionError(f"active Codex status must map to running: {running}")

    dry_run = operator_lifecycle_for({"status": "completed_dry_run", "execution_mode": "production_lane_dry_run"})
    if dry_run["selectable"] is not False:
        raise AssertionError(f"production dry-run must not be selectable for Merge & Deploy: {dry_run}")

    sprint = operator_lifecycle_for({"status": "passed", "run_type": "sprint", "verifier_status": "passed"})
    if sprint["status"] != "sprint_archival" or sprint["selectable"] is not False:
        raise AssertionError(f"historical sprint parent must be archival/non-selectable: {sprint}")
    sprint_child = operator_lifecycle_for({"status": "passed", "parent_run_id": "mcp-sprint-archival", "verifier_status": "passed"})
    if sprint_child["status"] != "sprint_archival" or sprint_child["selectable"] is not False:
        raise AssertionError(f"historical sprint child must be archival/non-selectable: {sprint_child}")

    payload = decorate_operator_lifecycle({"status": "verifier_passed", "target_id": "wb-core"})
    for key in ("operator_lifecycle_status", "operator_lifecycle_label", "operator_lifecycle_tone", "promotion_selectable", "operator_time_summary"):
        if key not in payload:
            raise AssertionError(f"decorated payload missing {key}: {payload}")

    print("dev-control-plane-operator-lifecycle-smoke passed")


if __name__ == "__main__":
    main()
