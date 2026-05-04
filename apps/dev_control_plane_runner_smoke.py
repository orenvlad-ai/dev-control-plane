"""Smoke-check for the repo-only development control-plane MVP runner."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (SRC, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dev_control_plane.contracts import frozen_task_spec_payload_from_mapping  # noqa: E402

RUNNER = ROOT / "apps" / "dev_control_plane_runner.py"
EXAMPLE_SPEC = ROOT / "artifacts" / "input" / "example_task_spec.json"
MANDATORY_PROMPT_TOKENS = (
    "Класс задачи:",
    "Причина классификации:",
    "Режим выполнения:",
    "=== ДЛЯ КУРАТОРА ===",
    "=== СЖАТАЯ ПРОВЕРКА ===",
)


def main() -> None:
    with TemporaryDirectory(prefix="dev-control-plane-runner-smoke-") as tmp:
        tmp_path = Path(tmp)
        state_dir = tmp_path / "state"
        frozen_spec_path = tmp_path / "frozen_task_spec.json"
        run_dirs: list[Path] = []
        try:
            _exercise_runner_smoke(state_dir, frozen_spec_path, run_dirs)
        finally:
            _cleanup_runs(run_dirs)

    print("dev-control-plane-mvp-runner-smoke passed")


def _exercise_runner_smoke(state_dir: Path, frozen_spec_path: Path, run_dirs: list[Path]) -> None:
    draft_spec = json.loads(EXAMPLE_SPEC.read_text(encoding="utf-8"))
    frozen_spec = frozen_task_spec_payload_from_mapping(draft_spec, frozen_at="2026-05-01T00:00:00Z")
    _write_json(frozen_spec_path, frozen_spec)

    draft_rejection = _run_json(
        [
            "prepare-run",
            "--task-spec",
            str(EXAMPLE_SPEC),
            "--step-id",
            "step-001",
            "--repo-root",
            str(ROOT),
            "--state-dir",
            str(state_dir),
        ],
        expect_success=False,
    )
    if "frozen" not in " ".join(draft_rejection.get("errors", [])):
        raise AssertionError(f"draft task spec must be rejected: {draft_rejection}")

    prepared = _run_json(
        [
            "prepare-run",
            "--task-spec",
            str(frozen_spec_path),
            "--step-id",
            "step-001",
            "--repo-root",
            str(ROOT),
            "--state-dir",
            str(state_dir),
        ]
    )
    if prepared.get("status") != "prepared":
        raise AssertionError(f"prepare-run must return prepared: {prepared}")
    if prepared.get("worktree_path") is not None:
        raise AssertionError(f"prepare-run must not create worktree: {prepared}")
    prompt = Path(prepared["prompt_path"]).read_text(encoding="utf-8")
    for token in MANDATORY_PROMPT_TOKENS:
        if token not in prompt:
            raise AssertionError(f"prepared prompt missing token: {token}")

    no_steps_spec = dict(frozen_spec)
    no_steps_spec.pop("sprint_steps", None)
    no_steps_path = frozen_spec_path.with_name("frozen_task_spec_no_steps.json")
    _write_json(no_steps_path, no_steps_spec)
    prepared_default_step = _run_json(
        [
            "prepare-run",
            "--task-spec",
            str(no_steps_path),
            "--repo-root",
            str(ROOT),
            "--state-dir",
            str(state_dir),
        ]
    )
    if prepared_default_step.get("status") != "prepared" or prepared_default_step.get("step_id") != "step-001":
        raise AssertionError(f"runner must normalize missing sprint_steps to default step: {prepared_default_step}")

    custom_step_spec = dict(frozen_spec)
    custom_step_spec["sprint_steps"] = [
        {
            "id": "custom-step-abc",
            "sequence": 1,
            "title": "Custom first step",
            "goal": "Exercise first runnable step selection.",
            "task_class": "L2",
            "scope": list(frozen_spec["allowed_paths"]),
            "acceptance_criteria": ["runner selects first runnable step"],
            "required_smokes": ["git diff --check"],
            "stop_conditions": ["stop if scope changes"],
        }
    ]
    custom_step_path = frozen_spec_path.with_name("frozen_task_spec_custom_step.json")
    _write_json(custom_step_path, custom_step_spec)
    prepared_custom_step = _run_json(
        [
            "prepare-run",
            "--task-spec",
            str(custom_step_path),
            "--step-id",
            "step-001",
            "--repo-root",
            str(ROOT),
            "--state-dir",
            str(state_dir),
        ]
    )
    if prepared_custom_step.get("step_id") != "custom-step-abc":
        raise AssertionError(f"runner must fall back to first custom step id: {prepared_custom_step}")
    if not prepared_custom_step.get("warnings"):
        raise AssertionError(f"runner must warn when requested step id is not found: {prepared_custom_step}")

    command_rejection = _run_json(
        [
            "run-step",
            "--task-spec",
            str(frozen_spec_path),
            "--step-id",
            "step-001",
            "--repo-root",
            str(ROOT),
            "--state-dir",
            str(state_dir),
            "--executor-mode",
            "command",
            "--executor-command",
            "true",
        ],
        expect_success=False,
    )
    if "--allow-real-executor" not in " ".join(command_rejection.get("errors", [])):
        raise AssertionError(f"command mode without explicit gate must be rejected: {command_rejection}")

    fake_run = _run_json(
        [
            "run-step",
            "--task-spec",
            str(frozen_spec_path),
            "--step-id",
            "step-001",
            "--repo-root",
            str(ROOT),
            "--state-dir",
            str(state_dir),
            "--executor-mode",
            "fake",
        ]
    )
    run_dirs.append(Path(fake_run["run_dir"]))
    if fake_run.get("status") != "verifier_passed" or fake_run.get("verifier_status") != "passed":
        raise AssertionError(f"fake run must pass verifier: {fake_run}")

    worktree_path = Path(fake_run["worktree_path"]).resolve()
    if worktree_path == ROOT.resolve():
        raise AssertionError("runner worktree must not be the main working tree")
    if not _is_relative_to(worktree_path, state_dir.resolve()):
        raise AssertionError(f"runner worktree must stay under smoke state_dir: {worktree_path}")

    handoff = Path(fake_run["handoff_path"]).read_text(encoding="utf-8")
    for token in ("=== ДЛЯ КУРАТОРА ===", "=== СЖАТАЯ ПРОВЕРКА ==="):
        if token not in handoff:
            raise AssertionError(f"handoff missing mandatory block: {token}")
    log_text = Path(fake_run["log_path"]).read_text(encoding="utf-8").lower()
    for forbidden in ("live_deploy", "ssh", "root_shell"):
        if forbidden in log_text:
            raise AssertionError(f"fake executor log must not mention executed forbidden action: {forbidden}")

    verify_passed = _run_json(["verify-run", "--run-dir", fake_run["run_dir"]])
    if verify_passed.get("verifier_status") != "passed":
        raise AssertionError(f"verify-run must pass on fake run: {verify_passed}")
    fake_policy = _check_by_name(verify_passed, "fake_executor_policy")
    if fake_policy.get("status") != "passed":
        raise AssertionError(f"fake executor policy check must pass: {fake_policy}")

    metadata_path = Path(fake_run["run_dir"]) / "run.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["result"]["changed_files"] = ["derived_project_pack/generated.md"]
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    verify_blocked = _run_json(["verify-run", "--run-dir", fake_run["run_dir"]], expect_success=False)
    if verify_blocked.get("verifier_status") != "blocked":
        raise AssertionError(f"forbidden path fixture must block verification: {verify_blocked}")
    if "derived_project_pack/generated.md" not in verify_blocked.get("forbidden_path_hits", []):
        raise AssertionError(f"forbidden path hit must be reported: {verify_blocked}")

    cleanup = _run_json(["cleanup-run", "--run-dir", fake_run["run_dir"]])
    if cleanup.get("status") != "cleaned":
        raise AssertionError(f"cleanup-run must remove smoke worktree: {cleanup}")
    run_dirs.clear()


def _cleanup_runs(run_dirs: list[Path]) -> None:
    errors: list[str] = []
    for run_dir in run_dirs:
        try:
            _run_json(["cleanup-run", "--run-dir", str(run_dir)])
        except Exception as exc:
            errors.append(f"{run_dir}: {exc}")
    if errors:
        raise AssertionError("failed to cleanup smoke worktrees: " + "; ".join(errors))


def _run_json(args: list[str], expect_success: bool = True) -> dict[str, Any]:
    completed = subprocess.run(
        [sys.executable, str(RUNNER), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if expect_success and completed.returncode != 0:
        raise AssertionError(f"command failed: {args}\nstdout={completed.stdout}\nstderr={completed.stderr}")
    if not expect_success and completed.returncode == 0:
        raise AssertionError(f"command unexpectedly passed: {args}\nstdout={completed.stdout}")
    return json.loads(completed.stdout)


def _check_by_name(summary: dict[str, Any], name: str) -> dict[str, Any]:
    for check in summary.get("check_results", []):
        if check.get("name") == name:
            return check
    raise AssertionError(f"check not found: {name}")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


if __name__ == "__main__":
    main()
