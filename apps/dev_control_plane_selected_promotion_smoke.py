"""Smoke-check deterministic selected Merge & Deploy planning."""

from __future__ import annotations

from pathlib import Path
import json
import os
import socket
import subprocess
import sys
import time
from tempfile import TemporaryDirectory
from typing import Any, Mapping
from urllib.error import HTTPError
from urllib import request as urllib_request

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (SRC, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dev_control_plane.selected_promotion import SelectedPromotionCandidate, plan_selected_promotion  # noqa: E402

SERVER = ROOT / "apps" / "dev_control_plane_server.py"


def main() -> None:
    _planner_smoke()
    _group_worker_continues_after_conflict_smoke()
    _server_selected_promotion_smoke()
    print("dev-control-plane-selected-promotion-smoke passed")


def _planner_smoke() -> None:
    docs = _candidate("task-docs", ["docs/architecture/01_control_plane_mvp.md"], finished_at="2026-05-09T08:30:00Z")
    ui = _candidate("task-ui", ["src/dev_control_plane/server.py"], finished_at="2026-05-09T08:31:00Z")
    broad = _candidate("task-broad", ["src/dev_control_plane/server.py", "src/dev_control_plane/mcp.py"], finished_at="2026-05-09T08:32:00Z")
    failed = _candidate("task-failed", [], lifecycle_status="failed")
    frozen = _candidate("task-frozen", ["README.md"], lifecycle_status="refresh_required", status="refresh_required")

    plan = plan_selected_promotion([broad, docs, ui, failed, frozen], target_id="wb-core")
    ordered_ids = [candidate.candidate_id for candidate in plan.ordered]
    if ordered_ids != ["task-docs", "task-ui"]:
        raise AssertionError(f"planner should order low-risk non-overlapping candidates deterministically: {plan.to_dict()}")
    if [candidate.candidate_id for candidate in plan.refresh_required] != ["task-frozen"]:
        raise AssertionError(f"frozen candidates must require refresh: {plan.to_dict()}")
    if [candidate.candidate_id for candidate in plan.deferred] != ["task-broad"]:
        raise AssertionError(f"same-file group overlap candidates must defer to separate deploy: {plan.to_dict()}")
    if plan.status != "planned_with_deferred" or plan.to_dict().get("deferred_task_ids") != ["task-broad"]:
        raise AssertionError(f"planner must expose deferred group-conflict ids: {plan.to_dict()}")
    if [candidate.candidate_id for candidate in plan.blocked] != ["task-failed"]:
        raise AssertionError(f"failed candidate must be blocked: {plan.to_dict()}")
    if "production lane remains serial" not in " ".join(plan.reasons):
        raise AssertionError(f"planner should document serial production semantics: {plan.to_dict()}")
    overlap_warning_plan = plan_selected_promotion([ui, broad], target_id="wb-core", allow_refresh=True)
    if "must be rebased/reverified" not in " ".join(overlap_warning_plan.reasons):
        raise AssertionError(f"planner should warn that same-file overlap needs refresh after partial deploy: {overlap_warning_plan.to_dict()}")

    mismatch = _candidate("task-other-target", ["README.md"], target_id="other")
    mismatch_plan = plan_selected_promotion([mismatch], target_id="wb-core")
    if mismatch_plan.status != "blocked" or not mismatch_plan.blocked:
        raise AssertionError(f"target mismatch must fail closed: {mismatch_plan.to_dict()}")


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


def _group_worker_continues_after_conflict_smoke() -> None:
    from dev_control_plane.server import CockpitStateStore, _selected_promotion_conflict_files  # noqa: PLC0415

    first = _candidate("task-conflict-first", ["migration/04_phase_0_1_backlog.md"])
    second = _candidate("task-deploy-second", ["migration/05_contract_inventory.md"])
    deferred = _candidate(
        "task-deferred-overlap",
        ["migration/04_phase_0_1_backlog.md"],
        lifecycle_status="ready_for_separate_deploy",
        status="ready_for_separate_deploy",
    )
    group_id = "promotion-group-smoke-worker-continues"
    conflict_blocker = (
        "selected managed run regenerated diff does not apply cleanly to current target main:\n"
        "Applied patch to 'migration/04_phase_0_1_backlog.md' with conflicts.\n"
        "U migration/04_phase_0_1_backlog.md"
    )
    with TemporaryDirectory(prefix="dev-control-plane-selected-worker-") as tmp_raw:
        tmp = Path(tmp_raw)
        state_dir = tmp / "state"
        store = CockpitStateStore(state_dir, ROOT / "configs" / "target_projects")
        _write_groups(
            state_dir,
            {
                group_id: {
                    "group_id": group_id,
                    "target_id": "wb-core",
                    "selected_ids": [first.candidate_id, second.candidate_id, deferred.candidate_id],
                    "selection_type": "task_id",
                    "mode": "auto_order",
                    "status": "promotion_running",
                    "current_step": "promotion_running",
                    "created_at": "2099-01-01T02:00:00Z",
                    "updated_at": "2099-01-01T02:00:00Z",
                    "planned_order": [first.candidate_id, second.candidate_id],
                    "accepted_task_ids": [first.candidate_id, second.candidate_id],
                    "deferred_task_ids": [deferred.candidate_id],
                    "per_task_status": {
                        first.candidate_id: "planned",
                        second.candidate_id: "planned",
                        deferred.candidate_id: "ready_for_separate_deploy",
                    },
                    "conflict_reason_by_task": {
                        deferred.candidate_id: "changed-file overlap with current group: migration/04_phase_0_1_backlog.md"
                    },
                    "recommended_action": "Запустите отдельный Merge & Deploy для deferred-задач.",
                }
            },
        )

        calls: list[str] = []

        def fake_execute(candidate: SelectedPromotionCandidate, *, group_id: str | None = None) -> dict[str, Any]:
            calls.append(candidate.candidate_id)
            if candidate.candidate_id == first.candidate_id:
                raise RuntimeError(conflict_blocker)
            if candidate.candidate_id != second.candidate_id or group_id != "promotion-group-smoke-worker-continues":
                raise AssertionError(f"unexpected worker candidate/group: {candidate} {group_id}")
            return {
                "status": "post_deploy_passed",
                "run_id": "selected-prod-second",
                "target_pr_url": "https://github.com/orenvlad-ai/wb-core/pull/305",
                "merge_commit": "merge-second",
                "deploy_status": "passed",
                "public_verify_status": "passed",
            }

        store._execute_selected_managed_run_production = fake_execute  # type: ignore[method-assign]
        store._selected_group_promotion_worker(group_id, [first.to_dict()])
        group = _read_groups(state_dir).get(group_id) or {}
        if calls != [first.candidate_id, second.candidate_id]:
            raise AssertionError(f"group worker must continue after conflict and try later accepted candidate: {calls}")
        if group.get("status") != "partially_deployed" or group.get("current_step") != "partially_deployed":
            raise AssertionError(f"group must finish as partially_deployed after later success: {group}")
        per_task = group.get("per_task_status") or {}
        if per_task.get(first.candidate_id) != "ready_for_separate_deploy":
            raise AssertionError(f"conflicted accepted candidate must become ready_for_separate_deploy: {group}")
        if per_task.get(second.candidate_id) != "production_complete":
            raise AssertionError(f"later accepted candidate must become production_complete: {group}")
        if per_task.get(deferred.candidate_id) != "ready_for_separate_deploy":
            raise AssertionError(f"pre-planned deferred candidate must stay ready_for_separate_deploy: {group}")
        if group.get("production_run_ids") != ["selected-prod-second"]:
            raise AssertionError(f"group should record only successful production runs: {group}")
        deferred_ids = set(group.get("deferred_task_ids") or [])
        if not {first.candidate_id, deferred.candidate_id}.issubset(deferred_ids):
            raise AssertionError(f"group should retain pre-planned and live-conflicted deferred ids: {group}")
        if group.get("conflicted_ids") != [first.candidate_id]:
            raise AssertionError(f"live-conflicted accepted candidate should be marked conflicted: {group}")
        if "migration/04_phase_0_1_backlog.md" not in group.get("conflict_files", []):
            raise AssertionError(f"group should expose live conflict file: {group}")
        if group.get("blocker"):
            raise AssertionError(f"group partial deploy conflict should not be a red blocker: {group}")
        refresh_source = "mcp-managed-refresh-source"
        refresh_run = "run-refresh-smoke-passed"
        refresh_group_id = "promotion-group-refresh-complete"
        _write_groups(
            state_dir,
            {
                refresh_group_id: {
                    "group_id": refresh_group_id,
                    "target_id": "wb-core",
                    "selected_ids": [refresh_source],
                    "selection_type": "run_id",
                    "mode": "auto_order",
                    "status": "partially_deployed",
                    "current_step": "partially_deployed",
                    "created_at": "2099-01-01T03:00:00Z",
                    "updated_at": "2099-01-01T03:01:00Z",
                    "planned_order": [refresh_source],
                    "deferred_task_ids": [refresh_source],
                    "refresh_required_ids": [refresh_source],
                    "conflicted_ids": [refresh_source],
                    "per_task_status": {refresh_source: "ready_for_separate_deploy"},
                    "conflict_files": ["packages/adapters/templates/sheet_vitrina_v1_web_vitrina.html"],
                    "recommended_action": "Пересобрать",
                }
            },
        )
        refresh_plans_path = state_dir / "collections" / "parallel_refresh_plans.json"
        refresh_plans_path.write_text(
            json.dumps(
                {
                    "refresh-plan-smoke": {
                        "refresh_plan_id": "refresh-plan-smoke",
                        "source_run_id": refresh_source,
                        "source_candidate_id": refresh_source,
                        "refresh_run_id": "real-run-refresh-smoke",
                        "group_id": refresh_group_id,
                        "status": "refresh_managed_run_started",
                    }
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        real_runs_path = state_dir / "collections" / "real_runs.json"
        real_runs_path.write_text(
            json.dumps({"real-run-refresh-smoke": {"id": "real-run-refresh-smoke", "run_id": refresh_run}}, indent=2) + "\n",
            encoding="utf-8",
        )
        store._complete_refreshed_source_candidate(
            SelectedPromotionCandidate(
                candidate_id=refresh_run,
                selected_id=refresh_run,
                selection_type="run_id",
                target_id="wb-core",
                source_kind="managed_run",
                status="verifier_passed",
                lifecycle_status="ready_for_promotion",
                managed_run_id=refresh_run,
                changed_files=("packages/adapters/templates/sheet_vitrina_v1_web_vitrina.html",),
            ),
            {
                "run_id": "selected-prod-refresh-smoke",
                "target_pr_url": "https://github.com/orenvlad-ai/wb-core/pull/305",
                "merge_commit": "merge-refresh",
                "deploy_status": "passed",
                "public_verify_status": "passed",
            },
        )
        refresh_group = _read_groups(state_dir).get(refresh_group_id) or {}
        if refresh_group.get("status") != "production_complete":
            raise AssertionError(f"completed refreshed candidate must close source group: {refresh_group}")
        if (refresh_group.get("per_task_status") or {}).get(refresh_source) != "production_complete":
            raise AssertionError(f"source child must become production_complete after refreshed deploy: {refresh_group}")
        if refresh_group.get("deferred_task_ids") or refresh_group.get("refresh_required_ids") or refresh_group.get("conflicted_ids"):
            raise AssertionError(f"completed refresh should clear deferred/conflict ids: {refresh_group}")
        if refresh_group.get("conflict_files") or refresh_group.get("recommended_action"):
            raise AssertionError(f"completed refresh should clear conflict metadata: {refresh_group}")
    if _selected_promotion_conflict_files(conflict_blocker) != ["migration/04_phase_0_1_backlog.md"]:
        raise AssertionError("selected diff apply conflict should expose conflict files")
    production_probe_blocker = (
        "public verify failed: route body contained a data fragment with conflict-like wording "
        "but no selected managed run diff apply failure"
    )
    if _selected_promotion_conflict_files(production_probe_blocker):
        raise AssertionError("non-apply production blockers must not be classified as selected-promotion conflicts")



def _server_selected_promotion_smoke() -> None:
    port = _free_port()
    with TemporaryDirectory(prefix="dev-control-plane-selected-promotion-") as tmp_raw:
        tmp = Path(tmp_raw)
        state_dir = tmp / "state"
        process = subprocess.Popen(
            [
                sys.executable,
                str(SERVER),
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--state-dir",
                str(state_dir),
            ],
            cwd=ROOT,
            env=_server_env(tmp),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            base_url = f"http://127.0.0.1:{port}"
            _wait_ready(base_url)
            first = _ready_task(base_url, "Исправить кнопку без заливки и проверить мониторинг", ["templates/button.html"])
            second = _ready_task(base_url, "Sticky группы таблицы в мониторинге", ["templates/sticky.html"])
            third = _ready_task(base_url, "Кэш таблицы и индикатор свежести", ["templates/cache.html"])

            single = _post_json(
                base_url + "/api/parallel-selection/promote",
                {
                    "target_id": "wb-core",
                    "selected_ids": [first],
                    "selection_type": "task_id",
                    "confirm_merge_deploy": True,
                    "allow_auto_first_promotion": True,
                    "allow_real_production_promotion": True,
                },
            )
            if single.get("status") != "blocked" or single.get("group_created") is not False:
                raise AssertionError(f"single selected promotion must fail closed visibly, without group block: {single}")
            if "RunArtifactPromotionAdapter" not in str(single.get("blocker") or "") and "disabled" not in str(single.get("blocker") or ""):
                raise AssertionError(f"single selected promotion must return exact bridge blocker: {single}")

            live_after_single = _get_json(base_url + "/api/runs/live")
            first_card = next(run for run in live_after_single.get("runs", []) if run.get("run_id") == first)
            if first_card.get("status") != "blocked" or not first_card.get("blocker"):
                raise AssertionError(f"single selected blocker must be visible on the original card: {first_card}")
            title = str(first_card.get("task_title") or "")
            if title.startswith("pt-") or len(title.split()) > 5 or "кнопку" not in title:
                raise AssertionError(f"card title should be human-readable fallback, not task_id: {first_card}")

            group = _post_json(
                base_url + "/api/parallel-selection/promote",
                {
                    "target_id": "wb-core",
                    "selected_ids": [first, second],
                    "selection_type": "task_id",
                    "mode": "auto_order",
                    "confirm_merge_deploy": True,
                    "allow_auto_first_promotion": True,
                    "allow_real_production_promotion": True,
                },
            )
            group_id = str(group.get("group_id") or "")
            if group.get("status") != "blocked" or group.get("group_created") is not True or not group_id:
                raise AssertionError(f"group selected promotion must create blocked inspectable group when bridge disabled: {group}")
            fetched_group = _get_json(base_url + f"/api/parallel-promotion-groups/{group_id}")
            if fetched_group.get("group", {}).get("status") != "blocked":
                raise AssertionError(f"group status must be readable from backend storage: {fetched_group}")
            group_detail = _get_json(base_url + f"/api/runs/{group_id}/live")
            if group_detail.get("status") != "ok" or group_detail.get("report", {}).get("promotion_group", {}).get("status") != "blocked":
                raise AssertionError(f"group should be inspectable as monitor detail: {group_detail}")
            group_tail = _get_json(base_url + f"/api/runs/{group_id}/log-tail")
            if "RunArtifactPromotionAdapter" not in str(group_tail.get("plain_text") or ""):
                raise AssertionError(f"group terminal tail should explain blocker: {group_tail}")
            mcp_group_status = _mcp(base_url, "tools/call", {"name": "get_run_status", "arguments": {"run_id": group_id}})
            structured = mcp_group_status.get("structuredContent") or {}
            if structured.get("status") != "blocked" or structured.get("run_type") != "group_promotion":
                raise AssertionError(f"MCP get_run_status should understand promotion groups: {mcp_group_status}")

            cancelled = _post_json(base_url + f"/api/runs/{group_id}/cancel", {"reason": "selected promotion smoke cancel"})
            if cancelled.get("status") != "cancelled":
                raise AssertionError(f"Stop/cancel must update promotion group state: {cancelled}")
            cancelled_group = _get_json(base_url + f"/api/parallel-promotion-groups/{group_id}")
            if cancelled_group.get("group", {}).get("status") != "cancelled":
                raise AssertionError(f"cancelled group must stay cancelled in backend: {cancelled_group}")

            ghost_id = "promotion-group-20260509T135513Z-smokeghost"
            _write_groups(
                state_dir,
                {
                    ghost_id: {
                        "group_id": ghost_id,
                        "target_id": "wb-core",
                        "selected_ids": [first, second],
                        "selection_type": "task_id",
                        "mode": "auto_order",
                        "status": "planned",
                        "current_step": "plan_ready",
                        "created_at": "2000-01-01T00:00:00Z",
                        "updated_at": "2000-01-01T00:00:00Z",
                        "planned_order": [first, second],
                        "per_task_status": {first: "planned", second: "planned"},
                    }
                },
            )
            live_after_ghost = _get_json(base_url + "/api/runs/live")
            ghost = next(run for run in live_after_ghost.get("runs", []) if run.get("run_id") == ghost_id)
            if ghost.get("active") is True or ghost.get("status") not in {"expired", "blocked"}:
                raise AssertionError(f"stale ghost group must not remain active/blinking: {ghost}")

            completed_group_id = "promotion-group-20260509T145445Z-smokecomplete"
            _write_groups(
                state_dir,
                {
                    completed_group_id: {
                        "group_id": completed_group_id,
                        "target_id": "wb-core",
                        "selected_ids": [first, second],
                        "selection_type": "task_id",
                        "mode": "auto_order",
                        "status": "production_complete",
                        "current_step": "production_complete",
                        "created_at": "2099-01-01T00:00:00Z",
                        "updated_at": "2099-01-01T00:01:00Z",
                        "finished_at": "2099-01-01T00:01:00Z",
                        "planned_order": [first, second],
                        "per_task_status": {first: "production_complete", second: "production_complete"},
                        "production_run_ids": ["selected-prod-first", "selected-prod-second"],
                        "pr_urls": ["https://github.com/orenvlad-ai/wb-core/pull/298", "https://github.com/orenvlad-ai/wb-core/pull/299"],
                        "merge_commits": ["32b2710", "64e8d12"],
                        "deploy_status": "passed",
                        "public_verify_status": "passed",
                    }
                },
            )
            live_after_completed_group = _get_json(base_url + "/api/runs/live")
            cards = {run.get("run_id"): run for run in live_after_completed_group.get("runs", [])}
            for child_id in (first, second):
                child = cards.get(child_id)
                if not child:
                    raise AssertionError(f"selected child card missing after completed group: {child_id}")
                if child.get("operator_lifecycle_status") != "production_complete" or child.get("operator_lifecycle_label") != "В проде":
                    raise AssertionError(f"selected child must become production_complete/green after group deploy: {child}")
                if child.get("promotion_selectable") is not False:
                    raise AssertionError(f"selected child must no longer be selectable after production_complete: {child}")
                if child.get("selected_promotion_group_id") != completed_group_id or not child.get("pr_url"):
                    raise AssertionError(f"selected child must show group/production linkage: {child}")
            third_card = cards.get(third)
            if not third_card:
                raise AssertionError("unselected third child card missing")
            if third_card.get("operator_lifecycle_status") != "ready_for_promotion" or third_card.get("promotion_selectable") is not True:
                raise AssertionError(f"unselected child must remain ready/selectable for manual test: {third_card}")

            conflict_run_id = "mcp-managed-20260509T164540Z-smokeconflict"
            _write_managed_run_artifacts(
                state_dir,
                conflict_run_id,
                ["apps/sheet_vitrina_v1_web_vitrina_browser_smoke.py", "packages/adapters/templates/sheet_vitrina_v1_web_vitrina.html"],
            )
            conflict_group_id = "promotion-group-20260509T164540Z-smokeconflict"
            conflict_blocker = (
                "selected managed run regenerated diff does not apply cleanly to current target main:\n"
                "Applied patch to 'apps/sheet_vitrina_v1_web_vitrina_browser_smoke.py' cleanly.\n"
                "Applied patch to 'packages/adapters/templates/sheet_vitrina_v1_web_vitrina.html' with conflicts.\n"
                "U packages/adapters/templates/sheet_vitrina_v1_web_vitrina.html"
            )
            _write_groups(
                state_dir,
                {
                    conflict_group_id: {
                        "group_id": conflict_group_id,
                        "target_id": "wb-core",
                        "selected_ids": [first, second, conflict_run_id],
                        "selection_type": "run_id",
                        "mode": "auto_order",
                        "status": "partially_deployed",
                        "current_step": "partially_deployed",
                        "created_at": "2099-01-01T01:00:00Z",
                        "updated_at": "2099-01-01T01:02:00Z",
                        "finished_at": "2099-01-01T01:02:00Z",
                        "planned_order": [first, second, conflict_run_id],
                        "accepted_task_ids": [first, second],
                        "deferred_task_ids": [conflict_run_id],
                        "per_task_status": {first: "production_complete", second: "production_complete", conflict_run_id: "ready_for_separate_deploy"},
                        "production_run_ids": ["selected-prod-first", "selected-prod-second"],
                        "pr_urls": ["https://github.com/orenvlad-ai/wb-core/pull/300", "https://github.com/orenvlad-ai/wb-core/pull/301"],
                        "merge_commits": ["abc123", "def456"],
                        "deploy_status": "passed",
                        "public_verify_status": "passed",
                        "blocker": None,
                        "conflicted_ids": [conflict_run_id],
                        "conflict_files": ["packages/adapters/templates/sheet_vitrina_v1_web_vitrina.html"],
                        "conflict_reason_by_task": {conflict_run_id: conflict_blocker},
                        "refresh_required_ids": [],
                        "recommended_action": "Запустите отдельный Merge & Deploy для deferred-задач.",
                    }
                },
            )
            live_after_conflict_group = _get_json(base_url + "/api/runs/live")
            conflict_cards = {run.get("run_id"): run for run in live_after_conflict_group.get("runs", [])}
            conflict_group = conflict_cards.get(conflict_group_id)
            if not conflict_group or conflict_group.get("active") is True or conflict_group.get("status") != "partially_deployed":
                raise AssertionError(f"partial conflict group must be terminal/non-active: {conflict_group}")
            conflict_child = conflict_cards.get(conflict_run_id)
            if not conflict_child:
                raise AssertionError("conflict child run card missing")
            if conflict_child.get("operator_lifecycle_status") != "ready_for_separate_deploy":
                raise AssertionError(f"conflict child must become ready_for_separate_deploy, not red blocker: {conflict_child}")
            if conflict_child.get("active") is True or conflict_child.get("effective_activity") == "running":
                raise AssertionError(f"conflict child must not pulse as active/running: {conflict_child}")
            if conflict_child.get("promotion_selectable") is not True:
                raise AssertionError(f"conflict child must remain selectable for separate Merge & Deploy: {conflict_child}")
            if "отдельной выкладке" not in str(conflict_child.get("operator_lifecycle_label") or ""):
                raise AssertionError(f"conflict child should have clear separate-deploy label: {conflict_child}")
            if "отдельный Merge & Deploy" not in str(conflict_child.get("recommended_action") or ""):
                raise AssertionError(f"conflict child should show separate deploy action: {conflict_child}")
            mcp_conflict_status = _mcp(base_url, "tools/call", {"name": "get_run_status", "arguments": {"run_id": conflict_group_id}})
            conflict_structured = mcp_conflict_status.get("structuredContent") or {}
            if (
                conflict_structured.get("status") != "partially_deployed"
                or conflict_structured.get("conflicted_ids") != [conflict_run_id]
                or conflict_structured.get("deferred_task_ids") != [conflict_run_id]
                or not conflict_structured.get("recommended_action")
            ):
                raise AssertionError(f"MCP get_run_status should expose conflict/refresh info: {mcp_conflict_status}")
            mcp_child_status = _mcp(base_url, "tools/call", {"name": "get_run_status", "arguments": {"run_id": conflict_run_id}})
            child_structured = mcp_child_status.get("structuredContent") or {}
            if (
                child_structured.get("operator_lifecycle_status") != "ready_for_separate_deploy"
                or child_structured.get("status") != "ready_for_separate_deploy"
                or child_structured.get("effective_activity") == "running"
                or child_structured.get("promotion_selectable") is not True
                or "отдельный Merge & Deploy" not in str(child_structured.get("recommended_action") or "")
            ):
                raise AssertionError(f"MCP get_run_status should expose child conflict override: {mcp_child_status}")
            deferred_promote = _post_json(
                base_url + "/api/parallel-selection/promote",
                {
                    "target_id": "wb-core",
                    "selected_ids": [conflict_run_id],
                    "selection_type": "auto",
                    "mode": "auto_order",
                    "confirm_merge_deploy": True,
                    "allow_real_production_promotion": True,
                    "allow_refresh": True,
                    "idempotency_key": "ui-like-deferred-noop-regression",
                },
            )
            if (
                deferred_promote.get("status") != "refresh_managed_run_started"
                or deferred_promote.get("selection_kind") != "single"
                or deferred_promote.get("group_created") is not False
                or deferred_promote.get("production_lane_started") is not False
                or deferred_promote.get("real_production_lane_started") is not False
                or not deferred_promote.get("refresh_run_id")
            ):
                raise AssertionError(f"deferred-only Merge & Deploy must start refresh visibly, not no-op: {deferred_promote}")
            deferred_refresh_job = _get_json(base_url + f"/api/real-runs/{deferred_promote.get('refresh_run_id')}")
            if deferred_refresh_job.get("target_project_id") != "wb-core" or deferred_refresh_job.get("status") != "queued":
                raise AssertionError(f"deferred-only refresh run must be backend-backed: {deferred_refresh_job}")
            deferred_refresh_task = _get_json(base_url + f"/api/parallel-tasks/{deferred_promote.get('task_id')}")
            if (
                deferred_refresh_task.get("task", {}).get("source_tool") != "refresh_selected_candidate"
                or deferred_refresh_task.get("task", {}).get("status") != "managed_run_running"
                or deferred_refresh_task.get("task", {}).get("managed_run_id") != deferred_promote.get("refresh_run_id")
            ):
                raise AssertionError(f"deferred-only refresh task must be visible and linked: {deferred_refresh_task}")
            task_text = str(deferred_refresh_task.get("task", {}).get("task_text") or "")
            if not task_text:
                ledger_payload = json.loads((state_dir / "collections" / "parallel_task_ledger.json").read_text(encoding="utf-8"))
                task_text = str(
                    (ledger_payload.get("tasks") or {}).get(str(deferred_promote.get("task_id")), {}).get("task_text") or ""
                )
            if "Move the top source/header strip" in task_text:
                raise AssertionError("refresh task must not reuse stale hardcoded intent summary")
            if "Пересобери intent исходной задачи поверх текущего main" not in task_text:
                raise AssertionError(f"refresh task must keep source intent rebuild instruction: {deferred_refresh_task}")
            deferred_promote_again = _post_json(
                base_url + "/api/parallel-selection/promote",
                {
                    "target_id": "wb-core",
                    "selected_ids": [conflict_run_id],
                    "selection_type": "auto",
                    "mode": "auto_order",
                    "confirm_merge_deploy": True,
                    "allow_real_production_promotion": True,
                    "allow_refresh": True,
                    "idempotency_key": "ui-like-deferred-noop-regression-second-click",
                },
            )
            if deferred_promote_again.get("refresh_run_id") != deferred_promote.get("refresh_run_id"):
                raise AssertionError(f"second deferred click must be idempotent for refresh run: {deferred_promote_again}")

            legacy_conflict_run_id = "mcp-managed-20260509T164540Z-smokelegacy"
            _write_managed_run_artifacts(
                state_dir,
                legacy_conflict_run_id,
                ["apps/sheet_vitrina_v1_web_vitrina_browser_smoke.py", "packages/adapters/templates/sheet_vitrina_v1_web_vitrina.html"],
            )
            legacy_waiting_run_id = "mcp-managed-20260509T164540Z-smokewaiting"
            _write_managed_run_artifacts(
                state_dir,
                legacy_waiting_run_id,
                ["packages/adapters/templates/sheet_vitrina_v1_web_vitrina.html"],
            )
            legacy_group_id = "promotion-group-20260509T164540Z-smokelegacy"
            _write_groups(
                state_dir,
                {
                    legacy_group_id: {
                        "group_id": legacy_group_id,
                        "target_id": "wb-core",
                        "selected_ids": [first, second, legacy_conflict_run_id, legacy_waiting_run_id],
                        "selection_type": "run_id",
                        "mode": "auto_order",
                        "status": "blocked",
                        "current_step": "selected_production_bridge_blocked",
                        "created_at": "2099-01-01T01:03:00Z",
                        "updated_at": "2099-01-01T01:04:00Z",
                        "finished_at": "2099-01-01T01:04:00Z",
                        "planned_order": [first, second, legacy_conflict_run_id, legacy_waiting_run_id],
                        "per_task_status": {
                            first: "production_complete",
                            second: "production_complete",
                            legacy_conflict_run_id: "production_lane_running",
                            legacy_waiting_run_id: "production_lane_running",
                        },
                        "production_run_ids": ["selected-prod-first", "selected-prod-second"],
                        "pr_urls": ["https://github.com/orenvlad-ai/wb-core/pull/302", "https://github.com/orenvlad-ai/wb-core/pull/303"],
                        "merge_commits": ["aaa111", "bbb222"],
                        "deploy_status": "passed",
                        "public_verify_status": "passed",
                        "blocker": conflict_blocker,
                        "conflicted_ids": [legacy_conflict_run_id],
                        "refresh_required_ids": [legacy_conflict_run_id],
                    }
                },
            )
            live_after_legacy_group = _get_json(base_url + "/api/runs/live")
            legacy_cards = {run.get("run_id"): run for run in live_after_legacy_group.get("runs", [])}
            legacy_group = legacy_cards.get(legacy_group_id)
            if not legacy_group or legacy_group.get("active") is True or legacy_group.get("status") != "partially_deployed":
                raise AssertionError(f"legacy blocked conflict group must reconcile to terminal partially_deployed: {legacy_group}")
            legacy_child = legacy_cards.get(legacy_conflict_run_id)
            if (
                not legacy_child
                or legacy_child.get("operator_lifecycle_status") != "ready_for_separate_deploy"
                or legacy_child.get("promotion_selectable") is not True
                or legacy_child.get("active") is True
            ):
                raise AssertionError(f"legacy conflict child must reconcile to ready_for_separate_deploy/non-active: {legacy_child}")
            legacy_waiting_child = legacy_cards.get(legacy_waiting_run_id)
            if (
                not legacy_waiting_child
                or legacy_waiting_child.get("operator_lifecycle_status") != "refresh_required"
                or legacy_waiting_child.get("active") is True
                or legacy_waiting_child.get("effective_activity") == "running"
            ):
                raise AssertionError(f"legacy terminal conflict group must not leave later child running: {legacy_waiting_child}")
            if "packages/adapters/templates/sheet_vitrina_v1_web_vitrina.html" not in legacy_group.get("conflict_files", []):
                raise AssertionError(f"legacy conflict group must expose conflict file: {legacy_group}")
            if "отдельный Merge & Deploy" not in str(legacy_group.get("recommended_action") or ""):
                raise AssertionError(f"legacy conflict group must expose separate deploy recommendation: {legacy_group}")

            stopped_child = _post_json(base_url + f"/api/runs/{conflict_run_id}/cancel", {"reason": "selected promotion smoke child stop"})
            if stopped_child.get("status") != "blocked_by_operator":
                raise AssertionError(f"Stop on conflict child must update visible backend state: {stopped_child}")
            live_after_child_stop = _get_json(base_url + "/api/runs/live")
            stopped_card = next(run for run in live_after_child_stop.get("runs", []) if run.get("run_id") == conflict_run_id)
            if stopped_card.get("active") is True or stopped_card.get("operator_lifecycle_label") != "Остановлено":
                raise AssertionError(f"stopped conflict child must be terminal/non-pulsing: {stopped_card}")

            refresh_plan = _post_json(
                base_url + "/api/parallel-selection/refresh",
                {
                    "target_id": "wb-core",
                    "source_run_id": conflict_run_id,
                    "group_id": conflict_group_id,
                    "conflict_files": ["packages/adapters/templates/sheet_vitrina_v1_web_vitrina.html"],
                    "mode": "managed_clone_only",
                    "confirm_start": True,
                    "idempotency_key": "refresh-smoke-conflict",
                },
            )
            if refresh_plan.get("status") != "refresh_task_submitted" or refresh_plan.get("production_lane_started") is not False:
                raise AssertionError(f"refresh candidate should create managed_clone_only task only: {refresh_plan}")
            refresh_task = _get_json(base_url + f"/api/parallel-tasks/{refresh_plan.get('task_id')}")
            if refresh_task.get("task", {}).get("source_tool") != "refresh_selected_candidate":
                raise AssertionError(f"refresh task must preserve source linkage: {refresh_task}")
            refresh_started = _post_json(
                base_url + "/api/parallel-selection/refresh",
                {
                    "target_id": "wb-core",
                    "source_run_id": conflict_run_id,
                    "group_id": conflict_group_id,
                    "conflict_files": ["packages/adapters/templates/sheet_vitrina_v1_web_vitrina.html"],
                    "mode": "managed_clone_only",
                    "confirm_start": True,
                    "start_managed_run": True,
                    "idempotency_key": "refresh-smoke-conflict-start",
                },
            )
            if (
                refresh_started.get("status") != "refresh_managed_run_started"
                or refresh_started.get("codex_started") is not True
                or not refresh_started.get("refresh_run_id")
                or refresh_started.get("production_lane_started") is not False
            ):
                raise AssertionError(f"refresh candidate should be able to start managed_clone_only run: {refresh_started}")
            refresh_job = _get_json(base_url + f"/api/real-runs/{refresh_started.get('refresh_run_id')}")
            if refresh_job.get("target_project_id") != "wb-core" or refresh_job.get("status") != "queued":
                raise AssertionError(f"refresh managed-clone run should be backend-backed: {refresh_job}")
            started_task = _get_json(base_url + f"/api/parallel-tasks/{refresh_started.get('task_id')}")
            if (
                started_task.get("task", {}).get("status") != "managed_run_running"
                or started_task.get("task", {}).get("managed_run_id") != refresh_started.get("refresh_run_id")
            ):
                raise AssertionError(f"refresh task must be bound to managed run: {started_task}")
            _update_real_run(
                state_dir,
                str(refresh_started.get("refresh_run_id")),
                {
                    "status": "passed",
                    "run_id": "run-refresh-smoke-passed",
                    "verifier_status": "passed",
                    "changed_files": ["packages/adapters/templates/sheet_vitrina_v1_web_vitrina.html"],
                    "updated_at": "2099-01-01T01:06:00Z",
                    "message": "Refresh smoke passed verifier.",
                },
            )
            live_after_refresh_passed = _get_json(base_url + "/api/runs/live")
            refresh_task_card = next(
                run for run in live_after_refresh_passed.get("runs", []) if run.get("run_id") == refresh_started.get("task_id")
            )
            if (
                refresh_task_card.get("status") != "verifier_passed"
                or refresh_task_card.get("active") is True
                or refresh_task_card.get("promotion_selectable") is not True
                or refresh_task_card.get("refreshed_candidate_id") != "run-refresh-smoke-passed"
            ):
                raise AssertionError(f"passed refresh task must become ready/non-active in monitor: {refresh_task_card}")
            refreshed_plan = _post_json(
                base_url + "/api/parallel-selection/promote",
                {
                    "target_id": "wb-core",
                    "selected_ids": [refresh_started.get("task_id")],
                    "selection_type": "auto",
                    "mode": "auto_order",
                    "plan_only": True,
                    "allow_refresh": True,
                },
            )
            if (
                refreshed_plan.get("status") != "plan_ready"
                or refreshed_plan.get("plan", {}).get("accepted_task_ids") != [refresh_started.get("task_id")]
            ):
                raise AssertionError(
                    f"refreshed parallel task bound to passed real run must resolve as promotable: {refreshed_plan}"
                )
            refresh_preview = _post_json(
                base_url + "/api/parallel-selection/refresh",
                {
                    "target_id": "wb-core",
                    "source_run_id": conflict_run_id,
                    "mode": "managed_clone_only",
                    "confirm_start": False,
                },
            )
            if refresh_preview.get("status") != "refresh_plan_ready" or refresh_preview.get("task_created") is not False:
                raise AssertionError(f"refresh preview must not create task without confirmation: {refresh_preview}")

            separate_group_id = "promotion-group-20260509T164540Z-smokeseparate"
            _write_groups(
                state_dir,
                {
                    separate_group_id: {
                        "group_id": separate_group_id,
                        "target_id": "wb-core",
                        "selected_ids": [conflict_run_id],
                        "selection_type": "run_id",
                        "mode": "auto_order",
                        "status": "production_complete",
                        "current_step": "production_complete",
                        "created_at": "2099-01-01T01:07:00Z",
                        "updated_at": "2099-01-01T01:08:00Z",
                        "finished_at": "2099-01-01T01:08:00Z",
                        "planned_order": [conflict_run_id],
                        "accepted_task_ids": [conflict_run_id],
                        "per_task_status": {conflict_run_id: "production_complete"},
                        "production_run_ids": ["selected-prod-separate"],
                        "pr_urls": ["https://github.com/orenvlad-ai/wb-core/pull/304"],
                        "merge_commits": ["ccc333"],
                        "deploy_status": "passed",
                        "public_verify_status": "passed",
                    }
                },
            )
            live_after_separate_group = _get_json(base_url + "/api/runs/live")
            separate_cards = {run.get("run_id"): run for run in live_after_separate_group.get("runs", [])}
            deployed_deferred = separate_cards.get(conflict_run_id)
            if (
                not deployed_deferred
                or deployed_deferred.get("operator_lifecycle_status") != "production_complete"
                or deployed_deferred.get("promotion_selectable") is not False
            ):
                raise AssertionError(f"subsequent separate deploy must mark deferred child production_complete: {deployed_deferred}")

            page = _get_text(base_url + "/runs/live")
            for token in ("task-title", "shortRunTitle", "observeRunStatusChanges", "notificationCount", "🔔", "#timelineList li", "lastPromptText", "Пересобрать", "refreshSelectedCandidate", "Нужен refresh", "Конфликт после выкладки"):
                if token not in page:
                    raise AssertionError(f"monitor page must include selected-promotion UI hardening token: {token}")
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def _ready_task(base_url: str, text: str, files: list[str]) -> str:
    submitted = _post_json(base_url + "/api/parallel-tasks", {"target_id": "wb-core", "task_text": text, "source": "smoke"})
    task_id = str(submitted.get("task_id") or "")
    if not task_id:
        raise AssertionError(f"submit must return task_id: {submitted}")
    _post_json(base_url + f"/api/parallel-tasks/{task_id}/start-execution", {"starter_mode": "fake"})
    reconciled = _post_json(
        base_url + f"/api/parallel-tasks/{task_id}/reconcile",
        {
            "run_status": "passed",
            "verifier_status": "passed",
            "changed_files": files,
            "verifier_summary": {"forbidden_paths_clean": True, "source": "selected-promotion-smoke"},
        },
    )
    if reconciled.get("status") != "verifier_passed":
        raise AssertionError(f"task must become verifier_passed: {reconciled}")
    return task_id


def _mcp(base_url: str, method: str, params: Mapping[str, Any]) -> dict[str, Any]:
    body = json.dumps({"jsonrpc": "2.0", "id": f"smoke-{time.time_ns()}", "method": method, "params": params}).encode("utf-8")
    req = urllib_request.Request(base_url + "/mcp", data=body, method="POST", headers={"Content-Type": "application/json"})
    with urllib_request.urlopen(req, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if "error" in payload:
        raise AssertionError(f"MCP error for {method}: {payload}")
    return payload.get("result") or {}


def _get_text(url: str) -> str:
    with urllib_request.urlopen(url, timeout=10) as response:
        return response.read().decode("utf-8")


def _get_json(url: str) -> dict[str, Any]:
    return json.loads(_get_text(url))


def _post_json(url: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    body = json.dumps(dict(payload)).encode("utf-8")
    request = urllib_request.Request(url, data=body, method="POST", headers={"Content-Type": "application/json"})
    try:
        with urllib_request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise AssertionError(f"POST {url} failed with HTTP {exc.code}: {detail}") from exc


def _write_groups(state_dir: Path, groups: Mapping[str, Mapping[str, Any]]) -> None:
    path = state_dir / "collections" / "parallel_promotion_groups.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if not isinstance(existing, dict):
        existing = {}
    existing.update({key: dict(value) for key, value in groups.items()})
    path.write_text(json.dumps(existing, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_groups(state_dir: Path) -> dict[str, Any]:
    path = state_dir / "collections" / "parallel_promotion_groups.json"
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise AssertionError(f"groups collection should be an object: {payload}")
    return payload


def _write_managed_run_artifacts(state_dir: Path, run_id: str, changed_files: list[str]) -> None:
    run_dir = state_dir / "runs" / run_id
    artifacts = run_dir / "artifacts"
    logs = run_dir / "logs"
    workspace = state_dir / "workspaces" / run_id / "wb-core"
    artifacts.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)
    workspace.mkdir(parents=True, exist_ok=True)
    prompt_path = artifacts / "prompt.md"
    handoff_path = artifacts / "handoff.md"
    diff_path = artifacts / "diff.patch"
    prompt_path.write_text("Fix Web Vitrina selected conflict source prompt.\n", encoding="utf-8")
    handoff_path.write_text("=== ДЛЯ КУРАТОРА ===\nVerifier passed before later main changes.\n", encoding="utf-8")
    diff_path.write_text(
        "diff --git a/packages/adapters/templates/sheet_vitrina_v1_web_vitrina.html b/packages/adapters/templates/sheet_vitrina_v1_web_vitrina.html\n"
        "--- a/packages/adapters/templates/sheet_vitrina_v1_web_vitrina.html\n"
        "+++ b/packages/adapters/templates/sheet_vitrina_v1_web_vitrina.html\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n",
        encoding="utf-8",
    )
    now = "2099-01-01T01:01:00Z"
    record = {
        "schema_version": 2,
        "created_at": now,
        "updated_at": now,
        "request": {
            "id": run_id,
            "target_project_id": "wb-core",
            "task_spec_id": f"task-spec-{run_id}",
            "step_id": "smoke",
            "state_dir": str(state_dir),
            "executor_mode": "fake",
        },
        "target_project": {"project_id": "wb-core"},
        "workspace": {"workspace_path": str(workspace), "base_ref": "source-base"},
        "task_spec": {"id": f"task-spec-{run_id}", "title": "Conflict source task"},
        "result": {
            "id": run_id,
            "status": "passed",
            "target_project_id": "wb-core",
            "run_dir": str(run_dir),
            "workspace_path": str(workspace),
            "prompt_path": str(prompt_path),
            "handoff_path": str(handoff_path),
            "diff_path": str(diff_path),
            "changed_files": changed_files,
            "check_results": [],
            "verifier_status": "passed",
            "blocker_reason": None,
        },
        "verifier": {
            "status": "passed",
            "changed_files": changed_files,
            "forbidden_path_hits": [],
            "check_results": [],
        },
    }
    (run_dir / "run.json").write_text(json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    runs_path = state_dir / "collections" / "runs.json"
    runs_path.parent.mkdir(parents=True, exist_ok=True)
    runs = json.loads(runs_path.read_text(encoding="utf-8")) if runs_path.exists() else {}
    if not isinstance(runs, dict):
        runs = {}
    runs[run_id] = {
        "run_id": run_id,
        "status": "passed",
        "target_project_id": "wb-core",
        "run_dir": str(run_dir),
        "task_title": "Conflict source task",
        "changed_files": changed_files,
        "verifier_status": "passed",
        "created_at": now,
        "updated_at": now,
    }
    runs_path.write_text(json.dumps(runs, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _update_real_run(state_dir: Path, run_id: str, updates: Mapping[str, Any]) -> None:
    path = state_dir / "collections" / "real_runs.json"
    jobs = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if not isinstance(jobs, dict) or run_id not in jobs:
        raise AssertionError(f"real run job missing: {run_id}")
    job = dict(jobs[run_id])
    job.update(dict(updates))
    jobs[run_id] = job
    path.write_text(json.dumps(jobs, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _wait_ready(base_url: str) -> None:
    deadline = time.time() + 10
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            _get_json(base_url + "/api/state")
            return
        except Exception as exc:
            last_error = exc
            time.sleep(0.1)
    raise AssertionError(f"server did not become ready: {last_error}")


def _server_env(tmp: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("OPENAI_API_KEY", None)
    env.pop("DEV_CONTROL_PLANE_PARALLEL_PRODUCTION_BRIDGE_MODE", None)
    env["DEV_CONTROL_PLANE_REFRESH_MANAGED_RUN_MODE"] = "stub"
    env["DEV_CONTROL_PLANE_SECRET_HOME"] = str(tmp / "secrets")
    return env


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


if __name__ == "__main__":
    main()
