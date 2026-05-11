"""Smoke-check wb-core auto-production arbitration for MCP-submitted tasks."""

from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
from tempfile import TemporaryDirectory
from typing import Any, Mapping
from urllib import request as urllib_request

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (SRC, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dev_control_plane.parallel_ledger import ParallelTaskLedger  # noqa: E402
from dev_control_plane.target_production import acquire_wb_core_production_lock, release_wb_core_production_lock  # noqa: E402

SERVER = ROOT / "apps" / "dev_control_plane_server.py"
TOKEN = "auto-task-smoke-token-0123456789abcdef0123456789abcdef"
CLEANUP_REASON = "operator intentionally abandoned stale selected-promotion candidates to restore DevControl ready-to-work state; no wb-core deploy required"
CLEANUP_TASKS = (
    ("pt-cleanup-001", "real-run-cleanup-001", ["migration/69_sku_display_bundle_block_legacy_sample_source.md"]),
    ("pt-cleanup-002", "real-run-cleanup-002", ["migration/71_table_projection_bundle_block_parity_matrix.md"]),
    ("pt-cleanup-003", "real-run-cleanup-003", ["migration/69_sku_display_bundle_block_legacy_sample_source.md"]),
    ("pt-cleanup-004", "real-run-cleanup-004", ["migration/69_sku_display_bundle_block_legacy_sample_source.md"]),
    ("pt-cleanup-005", "real-run-cleanup-005", ["migration/71_table_projection_bundle_block_parity_matrix.md"]),
)


def main() -> None:
    _exclusive_when_idle()
    _internal_task_spec_wrapper_is_noop()
    _changed_files_recover_from_production_plan()
    _prepare_only_when_active_run_exists()
    _prepare_only_when_lock_busy()
    _single_ready_run_merge_deploy()
    _old_candidates_do_not_block_auto_task()
    _stale_group_without_current_child_does_not_block()
    _cleanup_archives_abandoned_selected_queue()
    _cleanup_refuses_active_run()
    _cleanup_refuses_busy_lock()
    _cleanup_refuses_active_production_run()
    _archive_blocked_auto_task_run()
    _archive_refuses_active_auto_task_run()
    _archive_refuses_merged_deployed_auto_task_run()
    _archive_safe_local_branch_cleanup()
    _concurrent_submissions_exclusive_then_prepare_only()
    _verifier_failed_never_promotes()
    print("dev-control-plane-wb-core-auto-task-smoke passed")


def _exclusive_when_idle() -> None:
    with _running_server() as ctx:
        before_count = len(_read_collection(ctx.state_dir, "mcp_runs"))
        result = _tool(
            ctx.base_url,
            "start_wb_core_auto_task",
            {"task_text": "Auto arbitration smoke exclusive", "idempotency_key": "exclusive", "max_wait_seconds": 5},
        )
        if result.get("route") != "wb_core_exclusive_auto_production" or result.get("auto_production_allowed") is not True:
            raise AssertionError(f"idle wb-core auto task must classify as exclusive: {result}")
        status = _tool(ctx.base_url, "get_run_status", {"run_id": result["run_id"]})
        if status.get("status") != "production_complete" or status.get("deferred_for_separate_deploy") is True:
            raise AssertionError(f"exclusive stub run must finish production_complete without deferral: {status}")
        if status.get("run_type") == "sprint" or status.get("child_run_ids") or status.get("parent_run_id"):
            raise AssertionError(f"direct auto task must not create sprint parent/child state: {status}")
        after_count = len(_read_collection(ctx.state_dir, "mcp_runs"))
        if after_count != before_count + 1:
            raise AssertionError(f"one external auto task must create exactly one run: before={before_count} after={after_count}")
        replay = _tool(
            ctx.base_url,
            "start_wb_core_auto_task",
            {"task_text": "Auto arbitration smoke exclusive duplicate", "idempotency_key": "exclusive", "max_wait_seconds": 5},
        )
        if replay.get("run_id") != result.get("run_id") or replay.get("idempotent_replay") is not True:
            raise AssertionError(f"idempotency_key must replay existing auto run: {replay}")


def _internal_task_spec_wrapper_is_noop() -> None:
    with _running_server() as ctx:
        before = _read_collection(ctx.state_dir, "mcp_runs")
        result = _tool(
            ctx.base_url,
            "start_wb_core_auto_task",
            {
                "task_text": "Task spec: internal-wrapper\nSprint step: 1. duplicate\n\nDo not start a duplicate Codex run.",
                "idempotency_key": "wrapper",
                "max_wait_seconds": 5,
            },
        )
        after = _read_collection(ctx.state_dir, "mcp_runs")
        if result.get("status") != "duplicate_internal_wrapper_ignored" or result.get("codex_started") is not False:
            raise AssertionError(f"internal Task spec wrapper must be ignored without Codex: {result}")
        if len(after) != len(before):
            raise AssertionError(f"internal Task spec wrapper must not create a run: before={before} after={after}")


def _changed_files_recover_from_production_plan() -> None:
    with _running_server() as ctx:
        run_id = "mcp-auto-changed-files-recovery-smoke"
        workspace = _seed_blocked_auto_task_run(ctx.state_dir, run_id)
        runs = _read_collection(ctx.state_dir, "mcp_runs")
        runs[run_id]["changed_files"] = []
        _write_collection(ctx.state_dir, "mcp_runs", runs)
        run_json = ctx.state_dir / "runs" / run_id / "run.json"
        record = json.loads(run_json.read_text(encoding="utf-8"))
        record["result"]["changed_files"] = []
        record["verifier"]["changed_files"] = []
        run_json.write_text(json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        verifier_path = ctx.state_dir / "runs" / run_id / "verifier" / "verifier.json"
        verifier = json.loads(verifier_path.read_text(encoding="utf-8"))
        verifier["changed_files"] = []
        verifier_path.write_text(json.dumps(verifier, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        status = _tool(ctx.base_url, "get_run_status", {"run_id": run_id})
        report = _tool(ctx.base_url, "get_run_report", {"run_id": run_id})
        expected = ["packages/application/example.py"]
        if status.get("changed_files") != expected:
            raise AssertionError(f"status must recover changed_files from production plan/workspace: {status}")
        if report.get("changed_files") != expected:
            raise AssertionError(f"report must recover changed_files from production plan/workspace: {report}")
        queued = _tool(
            ctx.base_url,
            "merge_deploy_ready_run",
            {"target_id": "wb-core", "run_id": run_id, "confirm_merge_deploy": True},
        )
        if queued.get("status") != "merge_deploy_queued":
            raise AssertionError(f"recoverable blocked run should queue guarded single Merge & Deploy: {queued}")
        final = _wait_run_status(ctx.base_url, run_id, {"production_complete", "blocked", "failed"})
        if final.get("status") != "production_complete":
            raise AssertionError(f"recoverable blocked run should complete in stub mode: {final}")
        if not workspace.exists():
            raise AssertionError("recovery smoke should preserve source workspace")


def _prepare_only_when_active_run_exists() -> None:
    with _running_server() as ctx:
        _write_collection(
            ctx.state_dir,
            "mcp_runs",
            {
                "active-wb-core-run": {
                    "run_id": "active-wb-core-run",
                    "target_id": "wb-core",
                    "status": "running_codex",
                    "current_stage": "running_codex",
                    "execution_mode": "managed_clone_only",
                    "created_at": "2099-01-01T00:00:00Z",
                    "updated_at": "2099-01-01T00:00:00Z",
                }
            },
        )
        result = _tool(
            ctx.base_url,
            "start_wb_core_auto_task",
            {"task_text": "Auto arbitration smoke deferred active", "idempotency_key": "active", "max_wait_seconds": 5},
        )
        _assert_prepare_only_result(result, "active non-terminal wb-core run")


def _prepare_only_when_lock_busy() -> None:
    with _running_server() as ctx:
        workspace = ctx.state_dir / "workspaces" / "lock-smoke" / "wb-core"
        run_dir = ctx.state_dir / "runs" / "lock-smoke"
        workspace.mkdir(parents=True)
        run_dir.mkdir(parents=True)
        lock = acquire_wb_core_production_lock(workspace_path=workspace, run_dir=run_dir, run_id="busy-lock-run")
        try:
            result = _tool(
                ctx.base_url,
                "start_wb_core_auto_task",
                {"task_text": "Auto arbitration smoke deferred lock", "idempotency_key": "lock", "max_wait_seconds": 5},
            )
            _assert_prepare_only_result(result, "production lock")
        finally:
            release_wb_core_production_lock(lock)


def _single_ready_run_merge_deploy() -> None:
    with _running_server() as ctx:
        workspace = ctx.state_dir / "workspaces" / "prepare-merge-lock" / "wb-core"
        lock_run_dir = ctx.state_dir / "runs" / "prepare-merge-lock"
        workspace.mkdir(parents=True)
        lock_run_dir.mkdir(parents=True)
        lock = acquire_wb_core_production_lock(workspace_path=workspace, run_dir=lock_run_dir, run_id="prepare-merge-lock")
        try:
            prepared = _tool(
                ctx.base_url,
                "start_wb_core_auto_task",
                {"task_text": "Auto arbitration smoke prepare then merge", "idempotency_key": "prepare-merge", "max_wait_seconds": 5},
            )
            _assert_prepare_only_result(prepared, "production lock")
        finally:
            release_wb_core_production_lock(lock)
        run_id = str(prepared.get("run_id") or "")
        rejected = _tool(
            ctx.base_url,
            "merge_deploy_ready_run",
            {"target_id": "wb-core", "selected_ids": [run_id, "other-ready-run"], "confirm_merge_deploy": True},
        )
        if rejected.get("status") != "blocked" or "exactly one" not in str(rejected.get("blocker") or ""):
            raise AssertionError(f"manual Merge & Deploy must reject multiple selected runs: {rejected}")
        needs_confirm = _tool(ctx.base_url, "merge_deploy_ready_run", {"target_id": "wb-core", "run_id": run_id})
        if needs_confirm.get("status") != "blocked" or "confirm_merge_deploy=true" not in str(needs_confirm.get("blocker") or ""):
            raise AssertionError(f"manual Merge & Deploy must require confirmation: {needs_confirm}")
        queued = _tool(
            ctx.base_url,
            "merge_deploy_ready_run",
            {"target_id": "wb-core", "run_id": run_id, "confirm_merge_deploy": True},
        )
        if queued.get("status") != "merge_deploy_queued" or queued.get("production_lane_started") is not True:
            raise AssertionError(f"single ready run Merge & Deploy must queue production lane: {queued}")
        final = _wait_run_status(ctx.base_url, run_id, {"production_complete", "blocked", "failed"})
        if final.get("status") != "production_complete" or final.get("manual_merge_deploy_stubbed") is not True:
            raise AssertionError(f"stubbed single ready run Merge & Deploy must complete without target mutation: {final}")


def _old_candidates_do_not_block_auto_task() -> None:
    with _running_server() as ctx:
        _write_collection(
            ctx.state_dir,
            "mcp_runs",
            {
                "mcp-managed-deferred-smoke": {
                    "run_id": "mcp-managed-deferred-smoke",
                    "target_id": "wb-core",
                    "status": "ready_for_separate_deploy",
                    "current_stage": "ready_for_separate_deploy",
                    "execution_mode": "managed_clone_only",
                    "deferred_for_separate_deploy": True,
                    "created_at": "2099-01-01T00:00:00Z",
                    "updated_at": "2099-01-01T00:00:00Z",
                }
            },
        )
        _write_collection(
            ctx.state_dir,
            "parallel_promotion_groups",
            {
                "promotion-group-deferred-smoke": {
                    "group_id": "promotion-group-deferred-smoke",
                    "target_id": "wb-core",
                    "status": "partially_deployed",
                    "current_step": "partially_deployed",
                    "selected_ids": ["mcp-managed-deferred-smoke"],
                    "deferred_task_ids": ["mcp-managed-deferred-smoke"],
                    "per_task_status": {"mcp-managed-deferred-smoke": "ready_for_separate_deploy"},
                    "created_at": "2099-01-01T00:00:00Z",
                    "updated_at": "2099-01-01T00:00:00Z",
                }
            },
        )
        result = _tool(
            ctx.base_url,
            "start_wb_core_auto_task",
            {"task_text": "Auto arbitration smoke deferred candidate", "idempotency_key": "deferred-candidate", "max_wait_seconds": 5},
        )
        if result.get("route") != "wb_core_exclusive_auto_production" or result.get("auto_production_allowed") is not True:
            raise AssertionError(f"legacy selected/deferred candidates must not block ordinary auto task: {result}")


def _stale_group_without_current_child_does_not_block() -> None:
    with _running_server() as ctx:
        _write_collection(
            ctx.state_dir,
            "mcp_runs",
            {
                "mcp-managed-stale-refresh": {
                    "run_id": "mcp-managed-stale-refresh",
                    "target_id": "wb-core",
                    "status": "refresh_required",
                    "current_stage": "selected_production_bridge_blocked",
                    "execution_mode": "managed_clone_only",
                    "created_at": "2026-05-09T00:00:00Z",
                    "updated_at": "2026-05-09T00:00:00Z",
                }
            },
        )
        _write_collection(
            ctx.state_dir,
            "parallel_promotion_groups",
            {
                "promotion-group-stale-refresh": {
                    "group_id": "promotion-group-stale-refresh",
                    "target_id": "wb-core",
                    "status": "blocked_by_conflict",
                    "current_step": "selected_production_bridge_blocked",
                    "selected_ids": ["mcp-managed-stale-refresh"],
                    "refresh_required_ids": ["mcp-managed-stale-refresh"],
                    "conflicted_ids": ["mcp-managed-stale-refresh"],
                    "per_task_status": {"mcp-managed-stale-refresh": "refresh_required"},
                    "created_at": "2026-05-09T00:00:00Z",
                    "updated_at": "2026-05-09T00:00:00Z",
                }
            },
        )
        result = _tool(
            ctx.base_url,
            "start_wb_core_auto_task",
            {"task_text": "Auto arbitration smoke stale group ignored", "idempotency_key": "stale-group", "max_wait_seconds": 5},
        )
        if result.get("route") != "wb_core_exclusive_auto_production" or result.get("auto_production_allowed") is not True:
            raise AssertionError(f"stale selected promotion group without current child must not block auto task: {result}")


def _cleanup_archives_abandoned_selected_queue() -> None:
    with _running_server() as ctx:
        task_ids = _seed_cleanup_candidates(ctx.state_dir)
        before = _tool(ctx.base_url, "list_parallel_candidates", {"target_id": "wb-core"})
        if {item.get("task_id") for item in before.get("candidates", [])} != set(task_ids):
            raise AssertionError(f"cleanup seed must create five active candidates: {before}")
        blocked = _tool(
            ctx.base_url,
            "start_wb_core_auto_task",
            {"task_text": "Auto arbitration cleanup must not block before archive", "idempotency_key": "cleanup-before", "max_wait_seconds": 5},
        )
        if blocked.get("route") != "wb_core_exclusive_auto_production" or blocked.get("auto_production_allowed") is not True:
            raise AssertionError(f"old selected queue must not block ordinary auto-task intake before cleanup: {blocked}")

        dry_run = _tool(
            ctx.base_url,
            "clear_wb_core_promotion_queue",
            {"target_id": "wb-core", "mode": "dry_run", "task_ids": task_ids, "reason": CLEANUP_REASON},
        )
        if dry_run.get("status") != "dry_run_ready" or dry_run.get("applied") is not False:
            raise AssertionError(f"cleanup dry-run must be ready without mutation: {dry_run}")
        if {item.get("task_id") for item in dry_run.get("tasks_to_archive", [])} != set(task_ids):
            raise AssertionError(f"cleanup dry-run must list selected tasks: {dry_run}")
        if set(dry_run.get("removed_candidate_ids") or []) != set(task_ids):
            raise AssertionError(f"cleanup dry-run must project active candidate removal: {dry_run}")
        if "promotion-group-cleanup-smoke" not in set(dry_run.get("affected_group_ids") or []):
            raise AssertionError(f"cleanup dry-run must report affected selected promotion group: {dry_run}")
        if dry_run.get("post_cleanup_wb_core_auto_task_arbitration", {}).get("status") != "would_unblock":
            raise AssertionError(f"cleanup dry-run must project wb-core auto-task unblock: {dry_run}")
        after_dry_run = _tool(ctx.base_url, "list_parallel_candidates", {"target_id": "wb-core"})
        if len(after_dry_run.get("candidates", [])) != 5:
            raise AssertionError(f"cleanup dry-run must not mutate active candidates: {after_dry_run}")

        denied_apply = _tool(
            ctx.base_url,
            "clear_wb_core_promotion_queue",
            {"target_id": "wb-core", "mode": "apply", "task_ids": task_ids, "reason": CLEANUP_REASON},
        )
        if denied_apply.get("status") != "blocked" or "confirm_clear=true" not in str(denied_apply.get("blocker") or ""):
            raise AssertionError(f"cleanup apply must require explicit confirmation: {denied_apply}")

        applied = _tool(
            ctx.base_url,
            "clear_wb_core_promotion_queue",
            {
                "target_id": "wb-core",
                "mode": "apply",
                "confirm_clear": True,
                "task_ids": task_ids,
                "reason": CLEANUP_REASON,
            },
        )
        if applied.get("status") != "applied" or applied.get("applied") is not True:
            raise AssertionError(f"cleanup apply must archive selected queue: {applied}")
        if set(applied.get("archived_task_ids") or []) != set(task_ids):
            raise AssertionError(f"cleanup apply must report archived task ids: {applied}")
        if applied.get("post_cleanup_candidate_count") != 0:
            raise AssertionError(f"cleanup apply must clear active candidate count: {applied}")
        if applied.get("post_cleanup_wb_core_auto_task_arbitration", {}).get("status") != "would_unblock":
            raise AssertionError(f"cleanup apply must unblock direct auto-task arbitration: {applied}")

        candidates = _tool(ctx.base_url, "list_parallel_candidates", {"target_id": "wb-core"})
        if candidates.get("candidates"):
            raise AssertionError(f"archived cleanup tasks must not remain eligible candidates: {candidates}")
        task = _tool(ctx.base_url, "get_parallel_task", {"task_id": task_ids[0]})
        fetched = task.get("task") or {}
        if fetched.get("status") != "abandoned_by_operator" or fetched.get("promotion_selectable") is not False:
            raise AssertionError(f"archived task must stay inspectable but non-selectable: {task}")
        if not fetched.get("cleanup_audit") or fetched.get("operator_lifecycle_status") != "archived":
            raise AssertionError(f"archived task must expose sanitized cleanup audit/lifecycle: {task}")
        groups = _read_collection(ctx.state_dir, "parallel_promotion_groups")
        group = groups.get("promotion-group-cleanup-smoke") or {}
        if group.get("status") != "archived" or group.get("cleanup_reason") != CLEANUP_REASON:
            raise AssertionError(f"cleanup must archive stale selected promotion groups: {group}")

        result = _tool(
            ctx.base_url,
            "start_wb_core_auto_task",
            {"task_text": "Auto arbitration cleanup unblocked", "idempotency_key": "cleanup-after", "max_wait_seconds": 5},
        )
        if result.get("route") != "wb_core_exclusive_auto_production" or result.get("auto_production_allowed") is not True:
            raise AssertionError(f"cleanup must unblock direct wb-core auto-task intake: {result}")
        status = _tool(ctx.base_url, "get_run_status", {"run_id": result["run_id"]})
        if status.get("status") != "production_complete":
            raise AssertionError(f"unblocked direct auto task should complete in stub mode: {status}")


def _cleanup_refuses_active_run() -> None:
    with _running_server() as ctx:
        task_ids = _seed_cleanup_candidates(ctx.state_dir, limit=1)
        _write_collection(
            ctx.state_dir,
            "mcp_runs",
            {
                "cleanup-active-run": {
                    "run_id": "cleanup-active-run",
                    "target_id": "wb-core",
                    "status": "running_codex",
                    "current_stage": "running_codex",
                    "execution_mode": "managed_clone_only",
                    "created_at": "2099-01-01T00:00:00Z",
                    "updated_at": "2099-01-01T00:00:00Z",
                }
            },
        )
        result = _tool(
            ctx.base_url,
            "clear_wb_core_promotion_queue",
            {"target_id": "wb-core", "mode": "apply", "confirm_clear": True, "task_ids": task_ids, "reason": CLEANUP_REASON},
        )
        if result.get("status") != "blocked" or "active runs exist" not in str(result.get("blocker") or ""):
            raise AssertionError(f"cleanup must refuse while target has active runs: {result}")
        _assert_cleanup_candidate_still_active(ctx.base_url, task_ids[0])


def _cleanup_refuses_busy_lock() -> None:
    with _running_server() as ctx:
        task_ids = _seed_cleanup_candidates(ctx.state_dir, limit=1)
        workspace = ctx.state_dir / "workspaces" / "cleanup-lock-smoke" / "wb-core"
        run_dir = ctx.state_dir / "runs" / "cleanup-lock-smoke"
        workspace.mkdir(parents=True)
        run_dir.mkdir(parents=True)
        lock = acquire_wb_core_production_lock(workspace_path=workspace, run_dir=run_dir, run_id="cleanup-busy-lock-run")
        try:
            result = _tool(
                ctx.base_url,
                "clear_wb_core_promotion_queue",
                {"target_id": "wb-core", "mode": "apply", "confirm_clear": True, "task_ids": task_ids, "reason": CLEANUP_REASON},
            )
        finally:
            release_wb_core_production_lock(lock)
        if result.get("status") != "blocked" or "production lock" not in str(result.get("blocker") or ""):
            raise AssertionError(f"cleanup must refuse while production lock is held: {result}")
        _assert_cleanup_candidate_still_active(ctx.base_url, task_ids[0])


def _cleanup_refuses_active_production_run() -> None:
    with _running_server() as ctx:
        task_ids = _seed_cleanup_candidates(ctx.state_dir, limit=1)
        ledger_path = ctx.state_dir / "collections" / "parallel_task_ledger.json"
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        ledger["tasks"][task_ids[0]]["production_run_id"] = "cleanup-active-production-run"
        ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        _write_collection(
            ctx.state_dir,
            "mcp_runs",
            {
                "cleanup-active-production-run": {
                    "run_id": "cleanup-active-production-run",
                    "target_id": "wb-core",
                    "status": "deploy_started",
                    "current_stage": "deploy_started",
                    "execution_mode": "production_lane",
                    "created_at": "2099-01-01T00:00:00Z",
                    "updated_at": "2099-01-01T00:00:00Z",
                }
            },
        )
        result = _tool(
            ctx.base_url,
            "clear_wb_core_promotion_queue",
            {"target_id": "wb-core", "mode": "apply", "confirm_clear": True, "task_ids": task_ids, "reason": CLEANUP_REASON},
        )
        if result.get("status") != "blocked" or "active production run" not in str(result.get("blocker") or ""):
            raise AssertionError(f"cleanup must refuse candidates with active production run binding: {result}")
        _assert_cleanup_candidate_still_active(ctx.base_url, task_ids[0])


def _archive_blocked_auto_task_run() -> None:
    with _running_server() as ctx:
        run_id = "mcp-auto-archive-smoke"
        _seed_blocked_auto_task_run(ctx.state_dir, run_id)
        dry_run = _tool(
            ctx.base_url,
            "archive_wb_core_auto_task_run",
            {"target_id": "wb-core", "run_id": run_id, "mode": "dry_run", "reason": "archive smoke"},
        )
        if dry_run.get("status") != "dry_run_ready" or dry_run.get("will_archive_run") is not True:
            raise AssertionError(f"blocked auto-task archive dry-run must be safe and explicit: {dry_run}")
        if dry_run.get("production_state", {}).get("pr_created") is not False or dry_run.get("production_state", {}).get("deploy_started") is not False:
            raise AssertionError(f"archive dry-run must expose no PR/deploy happened: {dry_run}")
        if dry_run.get("diff_gate", {}).get("missing_from_promotion") != ["packages/application/example.py"]:
            raise AssertionError(f"archive dry-run must expose regenerated diff mismatch diagnostics: {dry_run}")
        run_before = _tool(ctx.base_url, "get_run_status", {"run_id": run_id})
        if run_before.get("status") != "blocked":
            raise AssertionError(f"archive dry-run must not mutate run status: {run_before}")

        applied = _tool(
            ctx.base_url,
            "archive_wb_core_auto_task_run",
            {
                "target_id": "wb-core",
                "run_id": run_id,
                "mode": "apply",
                "confirm_archive": True,
                "reason": "operator abandoned blocked run in smoke",
            },
        )
        if applied.get("status") != "applied" or applied.get("new_status") != "abandoned_by_operator":
            raise AssertionError(f"blocked auto-task archive apply must mark abandoned: {applied}")
        status = _tool(ctx.base_url, "get_run_status", {"run_id": run_id})
        if status.get("status") != "abandoned_by_operator" or status.get("effective_activity") == "running":
            raise AssertionError(f"archived auto-task run must be terminal and inspectable: {status}")
        artifacts = _tool(ctx.base_url, "list_run_artifacts", {"run_id": run_id})
        artifact_ids = {item.get("artifact_id") for item in artifacts.get("artifacts", [])}
        if not {"diff", "handoff", "production_lane_report"}.issubset(artifact_ids):
            raise AssertionError(f"archive must preserve evidence artifacts: {artifacts}")
        intents = _read_collection(ctx.state_dir, "wb_core_auto_production_intents")
        if intents.get(run_id, {}).get("status") != "released":
            raise AssertionError(f"archive apply must release active auto intent: {intents}")
        result = _tool(
            ctx.base_url,
            "start_wb_core_auto_task",
            {"task_text": "Auto arbitration after archive smoke", "idempotency_key": "archive-after", "max_wait_seconds": 5},
        )
        if result.get("route") != "wb_core_exclusive_auto_production" or result.get("auto_production_allowed") is not True:
            raise AssertionError(f"archived auto-task run must not block future auto-task intake: {result}")


def _archive_refuses_active_auto_task_run() -> None:
    with _running_server() as ctx:
        run_id = "mcp-auto-archive-active-smoke"
        _seed_blocked_auto_task_run(ctx.state_dir, run_id, status="running_codex")
        result = _tool(
            ctx.base_url,
            "archive_wb_core_auto_task_run",
            {"target_id": "wb-core", "run_id": run_id, "mode": "apply", "confirm_archive": True, "reason": "archive smoke"},
        )
        if result.get("status") != "blocked" or "active/running" not in str(result.get("blocker") or ""):
            raise AssertionError(f"archive must refuse active/running auto-task run: {result}")


def _archive_refuses_merged_deployed_auto_task_run() -> None:
    with _running_server() as ctx:
        run_id = "mcp-auto-archive-merged-smoke"
        _seed_blocked_auto_task_run(ctx.state_dir, run_id, merged=True, deployed=True)
        result = _tool(
            ctx.base_url,
            "archive_wb_core_auto_task_run",
            {"target_id": "wb-core", "run_id": run_id, "mode": "apply", "confirm_archive": True, "reason": "archive smoke"},
        )
        blocker = str(result.get("blocker") or "")
        if result.get("status") != "blocked" or "PR was merged" not in blocker or "deploy started" not in blocker:
            raise AssertionError(f"archive must refuse merged/deployed run: {result}")


def _archive_safe_local_branch_cleanup() -> None:
    with _running_server() as ctx:
        run_id = "mcp-auto-archive-branch-smoke"
        branch = f"devcp/{run_id}-task"
        workspace = _seed_blocked_auto_task_run(ctx.state_dir, run_id, target_branch=branch)
        _git(workspace, "checkout", "-B", branch)
        _git(workspace, "checkout", "main")
        applied = _tool(
            ctx.base_url,
            "archive_wb_core_auto_task_run",
            {
                "target_id": "wb-core",
                "run_id": run_id,
                "mode": "apply",
                "confirm_archive": True,
                "reason": "archive branch cleanup smoke",
                "cleanup_branch": True,
            },
        )
        if applied.get("status") != "applied" or applied.get("branch_cleanup", {}).get("attempted") is not True:
            raise AssertionError(f"archive branch cleanup must apply for safe DevControl branch: {applied}")
        remaining = _git(workspace, "branch", "--list", branch)
        if remaining.strip():
            raise AssertionError(f"archive branch cleanup must delete only the safe local DevControl branch: {remaining}")


def _concurrent_submissions_exclusive_then_prepare_only() -> None:
    with _running_server(stub_delay_seconds=1.0) as ctx:
        results: list[dict[str, Any]] = []
        errors: list[BaseException] = []

        def call(index: int) -> None:
            try:
                results.append(
                    _tool(
                        ctx.base_url,
                        "start_wb_core_auto_task",
                        {
                            "task_text": f"Auto arbitration concurrent {index}",
                            "idempotency_key": f"concurrent-{index}",
                            "max_wait_seconds": 0,
                        },
                    )
                )
            except BaseException as exc:  # pragma: no cover - surfaced below
                errors.append(exc)

        threads = [threading.Thread(target=call, args=(index,)) for index in (1, 2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
        if errors:
            raise AssertionError(f"concurrent auto task call failed: {errors}")
        routes = [result.get("route") for result in results]
        if routes.count("wb_core_exclusive_auto_production") != 1 or routes.count("wb_core_prepare_only") != 1:
            raise AssertionError(f"concurrent auto tasks must produce one exclusive and one prepare-only run: {results}")
        for result in results:
            if result.get("route") == "wb_core_prepare_only":
                final = _wait_run_status(ctx.base_url, str(result.get("run_id") or ""), {"ready_for_single_merge_deploy", "blocked", "failed"})
                if final.get("status") != "ready_for_single_merge_deploy" or final.get("production_lane_started") is not False:
                    raise AssertionError(f"prepare-only concurrent task must stop before merge/deploy: {final}")
                continue
            final = _wait_run_status(ctx.base_url, str(result.get("run_id") or ""), {"production_complete", "blocked", "failed"})
            if final.get("status") != "production_complete":
                raise AssertionError(f"exclusive concurrent task must finish production_complete: {final}")


def _verifier_failed_never_promotes() -> None:
    with _running_server(stub_verifier_status="failed") as ctx:
        result = _tool(
            ctx.base_url,
            "start_wb_core_auto_task",
            {"task_text": "Auto arbitration smoke verifier failure", "idempotency_key": "verifier-failed", "max_wait_seconds": 5},
        )
        status = _tool(ctx.base_url, "get_run_status", {"run_id": result["run_id"]})
        if status.get("status") != "blocked" or status.get("verifier_status") != "failed":
            raise AssertionError(f"verifier failed auto task must block: {status}")
        if status.get("production_lane_started") is not False or status.get("branch_pr_created") not in {False, None}:
            raise AssertionError(f"verifier failed auto task must not PR/merge/deploy: {status}")


def _assert_blocked_result(result: Mapping[str, Any], reason_token: str) -> None:
    if result.get("status") != "blocked" or result.get("route") != "wb_core_direct_auto_blocked":
        raise AssertionError(f"busy wb-core auto task must return blocker before fallback execution: {result}")
    if result.get("accepted") is not False or result.get("run_id"):
        raise AssertionError(f"blocked direct auto task must not create a managed-clone-only run: {result}")
    if result.get("fallback_to_sprint") is not False or result.get("fallback_to_managed_clone_only") is not False:
        raise AssertionError(f"blocked direct auto task must forbid sprint/managed-clone fallback: {result}")
    reason = str(result.get("blocker") or result.get("separate_deploy_reason") or "")
    if reason_token not in reason:
        raise AssertionError(f"direct auto blocker must mention {reason_token!r}: {result}")


def _assert_prepare_only_result(result: Mapping[str, Any], reason_token: str) -> None:
    if result.get("route") != "wb_core_prepare_only":
        raise AssertionError(f"busy wb-core auto task must be accepted as prepare-only: {result}")
    if result.get("auto_production_allowed") is not False or result.get("prepare_only") is not True:
        raise AssertionError(f"prepare-only arbitration flags are wrong: {result}")
    if result.get("fallback_to_sprint") is not None or result.get("fallback_to_managed_clone_only") is not None:
        raise AssertionError(f"prepare-only route must not use sprint/managed-clone fallback flags: {result}")
    decision = result.get("arbitration_decision") or {}
    reason = str(decision.get("separate_deploy_reason") or result.get("separate_deploy_reason") or "")
    if reason_token not in reason:
        raise AssertionError(f"prepare-only reason must mention {reason_token!r}: {result}")
    if result.get("status") != "ready_for_single_merge_deploy":
        raise AssertionError(f"prepare-only task must stop ready for single Merge & Deploy in stub mode: {result}")
    if result.get("production_lane_started") is not False:
        raise AssertionError(f"prepare-only task must not start merge/deploy automatically: {result}")


def _assert_cleanup_candidate_still_active(base_url: str, task_id: str) -> None:
    task = _tool(base_url, "get_parallel_task", {"task_id": task_id}).get("task") or {}
    if task.get("status") != "verifier_passed" or task.get("promotion_selectable") is not True:
        raise AssertionError(f"blocked cleanup must leave candidate active/selectable: {task}")


def _seed_cleanup_candidates(state_dir: Path, *, limit: int | None = None) -> list[str]:
    selected = CLEANUP_TASKS[: limit or len(CLEANUP_TASKS)]
    ledger = ParallelTaskLedger.from_state_dir(state_dir)
    real_runs: dict[str, dict[str, Any]] = {}
    timestamp = "2026-05-11T00:00:00Z"
    for task_id, run_id, changed_files in selected:
        ledger.submit_task(
            target_id="wb-core",
            task_text=f"cleanup smoke candidate {task_id}",
            source="cleanup-smoke",
            source_tool="refresh_selected_candidate",
            submitted_by="smoke",
            task_id=task_id,
            now=timestamp,
        )
        ledger.bind_managed_run(task_id, run_id, now=timestamp)
        ledger.reconcile_managed_run_result(
            task_id,
            run_status="passed",
            verifier_status="passed",
            changed_files=changed_files,
            verifier_summary={"verifier_status": "passed", "source": "cleanup-smoke"},
            now=timestamp,
        )
        real_runs[run_id] = {
            "id": run_id,
            "run_id": run_id,
            "target_project_id": "wb-core",
            "status": "passed",
            "verifier_status": "passed",
            "changed_files": changed_files,
            "created_at": timestamp,
            "updated_at": timestamp,
            "finished_at": timestamp,
        }
    _write_collection(state_dir, "real_runs", real_runs)
    task_ids = [task_id for task_id, _run_id, _changed_files in selected]
    _write_collection(
        state_dir,
        "parallel_promotion_groups",
        {
            "promotion-group-cleanup-smoke": {
                "group_id": "promotion-group-cleanup-smoke",
                "target_id": "wb-core",
                "status": "blocked_by_conflict",
                "current_step": "selected_production_bridge_blocked",
                "blocker": "promotion workspace diff does not match verified diff; do not deploy",
                "selected_ids": task_ids,
                "planned_order": task_ids,
                "accepted_task_ids": task_ids,
                "deferred_task_ids": task_ids,
                "per_task_status": {task_id: "ready_for_separate_deploy" for task_id in task_ids},
                "created_at": timestamp,
                "updated_at": timestamp,
            }
        },
    )
    _write_collection(
        state_dir,
        "parallel_selection_attempts",
        {
            "selection-attempt-cleanup-smoke": {
                "target_id": "wb-core",
                "status": "blocked",
                "candidate_id": task_ids[0] if task_ids else "",
                "selected_id": task_ids[0] if task_ids else "",
                "blocker": "promotion workspace diff does not match verified diff; do not deploy",
                "created_at": timestamp,
                "updated_at": timestamp,
            }
        },
    )
    return task_ids


def _seed_blocked_auto_task_run(
    state_dir: Path,
    run_id: str,
    *,
    status: str = "blocked",
    merged: bool = False,
    deployed: bool = False,
    target_branch: str | None = None,
) -> Path:
    run_dir = state_dir / "runs" / run_id
    workspace = state_dir / "workspaces" / run_id / "wb-core"
    workspace.mkdir(parents=True)
    (workspace / "packages" / "application").mkdir(parents=True)
    (workspace / "packages" / "application" / "example.py").write_text("print('base')\n", encoding="utf-8")
    _git(workspace.parent, "init", "-b", "main", str(workspace))
    _git(workspace, "config", "user.email", "smoke@example.invalid")
    _git(workspace, "config", "user.name", "Smoke Test")
    _git(workspace, "add", ".")
    _git(workspace, "commit", "-m", "Initial auto archive fixture")
    base = _git(workspace, "rev-parse", "HEAD").strip()
    (run_dir / "artifacts").mkdir(parents=True)
    (run_dir / "logs").mkdir(parents=True)
    (run_dir / "verifier").mkdir(parents=True)
    (run_dir / "artifacts" / "diff.patch").write_text("", encoding="utf-8")
    (run_dir / "artifacts" / "handoff.md").write_text("=== ДЛЯ КУРАТОРА ===\n\nblocked archive smoke\n", encoding="utf-8")
    (run_dir / "verifier" / "verifier.json").write_text(json.dumps({"status": "passed", "changed_files": ["packages/application/example.py"]}) + "\n", encoding="utf-8")
    production_dir = run_dir / "artifacts" / "production_lane"
    production_dir.mkdir(parents=True)
    branch = target_branch or f"devcp/{run_id}-task"
    production = {
        "status": "blocked",
        "allowed": True,
        "blockers": ["promotion workspace diff does not match verified diff; do not deploy"],
        "warnings": [],
        "executed_steps": ["production_toolchain_preflight", "target_lock_acquired", *(["target_pr_merged"] if merged else []), *(["deploy_live"] if deployed else [])],
        "target_branch": branch,
        "target_pr_url": "https://github.com/orenvlad-ai/wb-core/pull/999" if merged else None,
        "target_pr_number": 999 if merged else None,
        "merge_commit": "a" * 40 if merged else None,
        "deploy_status": "passed" if deployed else "blocked",
        "plan": {
            "run_id": run_id,
            "run_dir": str(run_dir),
            "workspace_path": str(workspace),
            "branch_name": branch,
            "changed_files": ["packages/application/example.py"],
            "run_start_base_ref": base,
            "verifier_base_commit": base,
            "diff_artifact_path": str(run_dir / "artifacts" / "diff.patch"),
            "diff_apply_status": "not_recorded",
        },
    }
    (production_dir / "production_lane_result.json").write_text(json.dumps(production, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (production_dir / "rollback_plan.json").write_text(json.dumps({"commands": ["rollback smoke"]}) + "\n", encoding="utf-8")
    run_record = {
        "result": {
            "id": run_id,
            "status": status,
            "target_project_id": "wb-core",
            "run_dir": str(run_dir),
            "workspace_path": str(workspace),
            "diff_path": str(run_dir / "artifacts" / "diff.patch"),
            "handoff_path": str(run_dir / "artifacts" / "handoff.md"),
            "changed_files": ["packages/application/example.py"],
            "verifier_status": "passed",
            "blocker_reason": "promotion workspace diff does not match verified diff; do not deploy",
        },
        "verifier": {"status": "passed", "changed_files": ["packages/application/example.py"]},
        "updated_at": "2026-05-11T00:00:00Z",
    }
    (run_dir / "run.json").write_text(json.dumps(run_record, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_collection(
        state_dir,
        "mcp_runs",
        {
            run_id: {
                "run_id": run_id,
                "tool": "start_wb_core_auto_task",
                "target_id": "wb-core",
                "status": status,
                "current_stage": status,
                "route": "wb_core_exclusive_auto_production",
                "execution_mode": "wb_core_exclusive_auto_production",
                "auto_production_allowed": True,
                "run_dir": str(run_dir),
                "workspace_path": str(workspace),
                "diff_path": str(run_dir / "artifacts" / "diff.patch"),
                "handoff_path": str(run_dir / "artifacts" / "handoff.md"),
                "verifier_status": "passed",
                "changed_files": ["packages/application/example.py"],
                "blocker": "promotion workspace diff does not match verified diff; do not deploy",
                "deploy_status": "passed" if deployed else "blocked",
                "target_pr_url": "https://github.com/orenvlad-ai/wb-core/pull/999" if merged else None,
                "target_pr_number": 999 if merged else None,
                "merge_commit": "a" * 40 if merged else None,
                "created_at": "2026-05-11T00:00:00Z",
                "updated_at": "2026-05-11T00:00:00Z",
            }
        },
    )
    _write_collection(
        state_dir,
        "wb_core_auto_production_intents",
        {
            run_id: {
                "run_id": run_id,
                "target_id": "wb-core",
                "status": "active",
                "route": "wb_core_exclusive_auto_production",
                "created_at": "2026-05-11T00:00:00Z",
                "updated_at": "2026-05-11T00:00:00Z",
            }
        },
    )
    return workspace


class _ServerContext:
    def __init__(self, process: subprocess.Popen[str], base_url: str, state_dir: Path) -> None:
        self.process = process
        self.base_url = base_url
        self.state_dir = state_dir

    def __enter__(self) -> "_ServerContext":
        global _CURRENT_BASE_URL
        _CURRENT_BASE_URL = self.base_url
        return self

    def __exit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)
        tmp = getattr(self, "_tmp", None)
        if tmp is not None:
            tmp.cleanup()


_CURRENT_BASE_URL = ""


def _running_server(*, stub_delay_seconds: float = 0.0, stub_verifier_status: str = "passed") -> _ServerContext:
    tmp_raw = TemporaryDirectory(prefix="dev-control-plane-auto-task-")
    tmp = Path(tmp_raw.name)
    state_dir = tmp / "state"
    port = _free_port()
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
        env=_server_env(tmp, stub_delay_seconds=stub_delay_seconds, stub_verifier_status=stub_verifier_status),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    startup_line = process.stdout.readline() if process.stdout else ""
    if not startup_line:
        stderr = process.stderr.read() if process.stderr else ""
        raise RuntimeError(f"server did not print startup payload: {stderr}")
    try:
        startup = json.loads(startup_line)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"server startup payload is not JSON: {startup_line!r}") from exc
    context = _ServerContext(process, f"http://127.0.0.1:{int(startup.get('port') or port)}", state_dir)
    context._tmp = tmp_raw  # type: ignore[attr-defined]
    _wait_ready(context.base_url)
    return context


def _server_env(tmp: Path, *, stub_delay_seconds: float, stub_verifier_status: str) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("OPENAI_API_KEY", None)
    env["DEV_CONTROL_PLANE_SECRET_HOME"] = str(tmp / "secrets")
    env["DEV_CONTROL_PLANE_MCP_TOKEN"] = TOKEN
    env["DEV_CONTROL_PLANE_MCP_FAKE_RUNS"] = "1"
    env["DEV_CONTROL_PLANE_WB_CORE_AUTO_TASK_MODE"] = "stub"
    env["DEV_CONTROL_PLANE_WB_CORE_AUTO_TASK_STUB_VERIFIER_STATUS"] = stub_verifier_status
    if stub_delay_seconds:
        env["DEV_CONTROL_PLANE_WB_CORE_AUTO_TASK_STUB_DELAY_SECONDS"] = str(stub_delay_seconds)
    return env


def _tool(base_url: str, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
    result = _mcp(base_url, "tools/call", {"name": name, "arguments": dict(arguments)}, token=TOKEN)
    structured = result.get("structuredContent")
    if isinstance(structured, dict):
        return structured
    raise AssertionError(f"MCP tool result missing structuredContent for {name}: {result}")


def _mcp(base_url: str, method: str, params: Mapping[str, Any], *, token: str | None = None) -> dict[str, Any]:
    body = json.dumps({"jsonrpc": "2.0", "id": f"smoke-{time.time_ns()}", "method": method, "params": params}).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib_request.Request(base_url + "/mcp", data=body, method="POST", headers=headers)
    with urllib_request.urlopen(req, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if "error" in payload:
        raise AssertionError(f"MCP error for {method}: {payload}")
    return payload.get("result") or {}


def _wait_run_status(base_url: str, run_id: str, statuses: set[str]) -> dict[str, Any]:
    deadline = time.time() + 15
    last: dict[str, Any] = {}
    while time.time() < deadline:
        last = _tool(base_url, "get_run_status", {"run_id": run_id})
        if str(last.get("status") or "") in statuses:
            return last
        time.sleep(0.2)
    raise AssertionError(f"run {run_id} did not reach {statuses}: {last}")


def _wait_ready(base_url: str) -> None:
    deadline = time.time() + 10
    last_error: object = None
    while time.time() < deadline:
        try:
            with urllib_request.urlopen(base_url + "/api/state", timeout=5) as response:
                if response.status == 200:
                    return
        except Exception as exc:
            last_error = exc
            time.sleep(0.1)
    raise RuntimeError(f"server did not become ready at {base_url}: {last_error}")


def _write_collection(state_dir: Path, name: str, payload: Mapping[str, Any]) -> None:
    path = state_dir / "collections" / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_collection(state_dir: Path, name: str) -> dict[str, Any]:
    path = state_dir / "collections" / f"{name}.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _git(cwd: Path, *args: str) -> str:
    completed = subprocess.run(("git", *args), cwd=cwd, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed\nstdout={completed.stdout}\nstderr={completed.stderr}")
    return completed.stdout


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


if __name__ == "__main__":
    main()
