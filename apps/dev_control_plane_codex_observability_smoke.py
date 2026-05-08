"""Smoke-check Codex observability helpers, transcript formatting and prompt gate."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import time
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (SRC, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dev_control_plane.codex_observability import (  # noqa: E402
    codex_observability_status,
    codex_run_reconciliation,
    codex_stale_assessment,
    finalize_process_state,
    terminate_run_owned_process_group,
    write_process_started,
)
from dev_control_plane.execution import RealCodexRunRequest, _prompt_consistency_gate, _run_codex_cli_executor  # noqa: E402
from dev_control_plane.live_monitor import append_terminal_output, read_terminal_tail  # noqa: E402


def main() -> None:
    status = codex_observability_status(env={})
    if status.get("status") != "ready" or status.get("io_mode", {}).get("effective") != "event":
        raise AssertionError(f"Codex observability status must be safe and ready: {status}")

    with TemporaryDirectory(prefix="dev-control-plane-codex-observability-") as tmp_raw:
        run_dir = Path(tmp_raw) / "runs" / "mcp-prod-smoke"
        run_dir.mkdir(parents=True)

        append_terminal_output(
            run_dir,
            '{"type":"item.started","item":{"id":"cmd-1","type":"command_execution","command":["python3","-m","py_compile"]},"timestamp":"2026-05-08T00:00:00Z"}\n'
            '{"type":"item.completed","item":{"id":"cmd-1","type":"command_execution","command":["python3","-m","py_compile"],"exit_code":0,"stdout":"compile passed"},"status":"completed","duration_ms":15}\n'
            '{"type":"turn.completed","usage":{"input_tokens":999}}\n',
        )
        tail = read_terminal_tail(run_dir)
        plain = tail.get("plain_text", "")
        if "started command_execution" not in plain or "compile passed" not in plain:
            raise AssertionError(f"human transcript must expand Codex item events: {tail}")
        for raw_marker in ("turn.completed", "input_tokens", "{\"type\""):
            if raw_marker in plain or raw_marker in tail.get("ansi_text", ""):
                raise AssertionError(f"raw JSON envelope must not leak into human transcript: {raw_marker} {tail}")

        sleeper = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            write_process_started(
                run_dir,
                pid=sleeper.pid,
                pgid=os.getpgid(sleeper.pid),
                command_preview=["python3", "-c", "[sleep omitted]"],
                io_mode="event",
                max_wall_seconds=3600,
                no_output_seconds=3600,
            )
            assessment = codex_stale_assessment(run_dir)
            if assessment.get("status") != "running" or assessment.get("alive") is not True:
                raise AssertionError(f"fresh process must assess as running: {assessment}")
            cancelled = terminate_run_owned_process_group(run_dir, reason="smoke cancel")
            if cancelled.get("status") != "cancelled":
                raise AssertionError(f"run-owned process cancel must succeed: {cancelled}")
            deadline = time.time() + 3
            while time.time() < deadline and sleeper.poll() is None:
                time.sleep(0.05)
            if sleeper.poll() is None:
                raise AssertionError("cancel must terminate the run-owned process")
        finally:
            if sleeper.poll() is None:
                os.killpg(os.getpgid(sleeper.pid), 9)
                sleeper.wait(timeout=5)

        run_dir.joinpath("artifacts").mkdir(exist_ok=True)
        run_dir.joinpath("artifacts", "handoff.md").write_text("handoff exists after observer failure", encoding="utf-8")
        reconciliation = codex_run_reconciliation(
            run_dir,
            declared_status="failed",
            current_stage="failed",
            blocker="name 'time' is not defined",
        )
        if reconciliation.get("effective_status") != "needs_verifier_after_control_error":
            raise AssertionError(f"handoff without verifier must reconcile as needs-verifier control error: {reconciliation}")
        if reconciliation.get("handoff_present_verifier_missing_due_to_control_error") is not True:
            raise AssertionError(f"handoff/verifier gap must be explicit: {reconciliation}")

        stale_dir = Path(tmp_raw) / "runs" / "operator-stale"
        stale_dir.mkdir(parents=True)
        write_process_started(
            stale_dir,
            pid=os.getpid(),
            pgid=os.getpgid(os.getpid()),
            command_preview=["self"],
            io_mode="event",
            max_wall_seconds=3600,
            no_output_seconds=3600,
        )
        finalize_process_state(stale_dir, status="stale_lost_process", timeout_reason="operator marked stale/blocked")
        stale = codex_run_reconciliation(
            stale_dir,
            declared_status="stale_lost_process",
            current_stage="stale_lost_process",
            blocker="operator marked stale/blocked",
        )
        if stale.get("operator_label") != "остановлено оператором" or stale.get("effective_activity") != "stale":
            raise AssertionError(f"operator stale state must be amber/operator-labelled: {stale}")

        exec_dir = Path(tmp_raw) / "runs" / "executor-regression"
        workspace = exec_dir / "workspace"
        logs = exec_dir / "logs"
        artifacts = exec_dir / "artifacts"
        workspace.mkdir(parents=True)
        logs.mkdir(parents=True)
        artifacts.mkdir(parents=True)
        fake_codex = Path(tmp_raw) / "fake-codex.py"
        fake_codex.write_text(
            "#!/usr/bin/env python3\n"
            "import time\n"
            "print('fake codex started', flush=True)\n"
            "time.sleep(0.4)\n"
            "print('=== ДЛЯ КУРАТОРА ===\\nstatus ok\\n=== СЖАТАЯ ПРОВЕРКА ===\\nok', flush=True)\n",
            encoding="utf-8",
        )
        fake_codex.chmod(0o755)
        prompt = artifacts / "prompt.md"
        prompt.write_text("safe prompt", encoding="utf-8")
        exit_code = _run_codex_cli_executor(
            RealCodexRunRequest(
                id="executor-regression",
                target_project_id="wb-core",
                task_spec_id="task",
                step_id="step-001",
                target_config_path=None,
                state_dir=str(Path(tmp_raw)),
                base_ref="HEAD",
                allow_real_codex=True,
                codex_bin=str(fake_codex),
            ),
            workspace_path=workspace,
            prompt_path=prompt,
            handoff_path=artifacts / "handoff.md",
            log_path=logs / "codex.log",
        )
        if exit_code != 0:
            raise AssertionError(f"executor regression must finish without NameError/time import failure: {exit_code}")
        process_state = codex_stale_assessment(exec_dir)
        if process_state.get("status") != "exited":
            raise AssertionError(f"executor process state must finalize cleanly: {process_state}")

    prod_conflict = _prompt_consistency_gate(
        "Режим выполнения: repo-only, no live/deploy, no UI, no Codex worker run",
        execution_mode="production_lane",
        codex_run=True,
    )
    if prod_conflict.status != "failed" or "production_lane conflicts" not in str(prod_conflict.reason):
        raise AssertionError(f"production-lane contradictory prompt must be blocked: {prod_conflict}")

    managed_ok = _prompt_consistency_gate(
        "Режим выполнения: managed_clone_only\nНе менять backend/API. Исправить CSS layout.",
        execution_mode="managed_clone_only",
        codex_run=True,
    )
    if managed_ok.status != "passed":
        raise AssertionError(f"normal managed-clone UI-scoped task must not be blocked: {managed_ok}")

    print("dev-control-plane-codex-observability-smoke passed")


if __name__ == "__main__":
    main()
