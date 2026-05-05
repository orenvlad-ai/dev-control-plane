"""Smoke-check hosted-ready state/workspace layout ownership."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (SRC, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dev_control_plane.contracts import ControlPlaneValidationError, frozen_task_spec_payload_from_mapping  # noqa: E402
from dev_control_plane.execution import cleanup_run_worktree, load_run_record, run_step  # noqa: E402
from dev_control_plane.state_layout import (  # noqa: E402
    DEFAULT_STATE_DIR,
    STATE_DIR_ENV,
    ControlPlaneStateLayout,
    StateLayoutError,
    resolve_state_root,
)

RUNNER = ROOT / "apps" / "dev_control_plane_runner.py"


def main() -> None:
    with TemporaryDirectory(prefix="dev-control-plane-state-layout-") as tmp_raw:
        tmp = Path(tmp_raw)
        state_root = tmp / "state"
        hosted_root = tmp / "hosted-state"
        fixture_repo = tmp / "fixture-repo"
        task_spec_path = tmp / "task_spec.json"

        _create_fixture_repo(fixture_repo)
        frozen_spec = frozen_task_spec_payload_from_mapping(_task_spec(), "2026-05-05T00:00:00Z")
        _write_json(task_spec_path, frozen_spec)

        if resolve_state_root(None, env={STATE_DIR_ENV: str(hosted_root)}) != hosted_root.resolve():
            raise AssertionError("state root must honor DEV_CONTROL_PLANE_STATE_DIR")
        if resolve_state_root(None, env={}) != DEFAULT_STATE_DIR.resolve():
            raise AssertionError("state root must have a local default")

        layout = ControlPlaneStateLayout.from_path(state_root)
        layout.ensure_base_dirs()
        for path in (
            layout.runs_dir,
            layout.workspaces_dir,
            layout.artifacts_dir,
            layout.logs_dir,
            layout.verifier_dir,
            layout.collections_dir,
        ):
            if not path.exists() or not _is_relative_to(path, state_root.resolve()):
                raise AssertionError(f"layout directory is not owned by state root: {path}")

        _assert_path_traversal_blocked(layout)
        _assert_task_id_traversal_blocked(frozen_spec, fixture_repo, state_root)

        result = run_step(
            frozen_spec,
            step_id=None,
            repo_root=fixture_repo,
            state_dir=state_root,
            executor_mode="fake",
        )
        run_dir = Path(result.run_dir).resolve()
        worktree_path = Path(result.worktree_path or "").resolve()
        expected_run_layout = ControlPlaneStateLayout.from_path(state_root).run_layout(result.id)
        if run_dir != expected_run_layout.run_dir:
            raise AssertionError(f"run dir must use unified runs layout: {run_dir}")
        if Path(result.prompt_path).resolve() != expected_run_layout.prompt_path:
            raise AssertionError(f"prompt must be written under run artifacts: {result.prompt_path}")
        if Path(result.handoff_path or "").resolve() != expected_run_layout.handoff_path:
            raise AssertionError(f"handoff must be written under run artifacts: {result.handoff_path}")
        if Path(result.log_path or "").resolve() != expected_run_layout.executor_log_path:
            raise AssertionError(f"executor log must be written under run logs: {result.log_path}")
        if worktree_path != expected_run_layout.workspace_dir("local-repo"):
            raise AssertionError(f"fake-flow worktree must live under state workspaces: {worktree_path}")
        if not expected_run_layout.verifier_path.exists():
            raise AssertionError("verifier output must be written under run verifier directory")
        if not (expected_run_layout.checks_dir / "git_diff_check.txt").exists():
            raise AssertionError("verifier check output must be written under run verifier checks")
        record = load_run_record(run_dir)
        if record.get("verifier", {}).get("status") != "passed":
            raise AssertionError(f"load_run_record must read verifier output from new layout: {record}")
        cleanup = cleanup_run_worktree(run_dir)
        if cleanup.get("status") != "cleaned" or worktree_path.exists():
            raise AssertionError(f"cleanup must remove state-owned fake-flow worktree: {cleanup}")

        env_state = tmp / "env-state"
        prepared = _run_runner_without_state_dir(fixture_repo, task_spec_path, env_state)
        prepared_run_dir = Path(prepared["run_dir"]).resolve()
        if not _is_relative_to(prepared_run_dir, (env_state / "runs").resolve()):
            raise AssertionError(f"runner must use DEV_CONTROL_PLANE_STATE_DIR when --state-dir is omitted: {prepared}")

    print("dev-control-plane-state-layout-smoke passed")


def _assert_path_traversal_blocked(layout: ControlPlaneStateLayout) -> None:
    for bad in ("", ".", "..", "../run", "run/child", "run\\child", "run id"):
        try:
            layout.run_layout(bad)
        except StateLayoutError:
            continue
        raise AssertionError(f"unsafe run_id was accepted: {bad!r}")
    safe_run = layout.run_layout("run-safe")
    for bad in ("../target", "target/child", "target\\child", "target id"):
        try:
            safe_run.workspace_dir(bad)
        except StateLayoutError:
            continue
        raise AssertionError(f"unsafe workspace_id was accepted: {bad!r}")


def _assert_task_id_traversal_blocked(frozen_spec: dict, repo: Path, state_root: Path) -> None:
    unsafe_spec = dict(frozen_spec)
    unsafe_spec["id"] = "../bad-task"
    try:
        run_step(
            unsafe_spec,
            step_id=None,
            repo_root=repo,
            state_dir=state_root,
            executor_mode="fake",
        )
    except ControlPlaneValidationError:
        return
    raise AssertionError("unsafe task_id was accepted for run path construction")


def _run_runner_without_state_dir(repo: Path, task_spec_path: Path, state_dir: Path) -> dict:
    env = os.environ.copy()
    env[STATE_DIR_ENV] = str(state_dir)
    completed = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "prepare-run",
            "--task-spec",
            str(task_spec_path),
            "--repo-root",
            str(repo),
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise AssertionError(f"runner default state-dir smoke failed\nstdout={completed.stdout}\nstderr={completed.stderr}")
    return json.loads(completed.stdout)


def _create_fixture_repo(repo: Path) -> None:
    (repo / "docs").mkdir(parents=True)
    (repo / "README.md").write_text("# Fixture Repo\n", encoding="utf-8")
    (repo / "docs" / "example.md").write_text("example\n", encoding="utf-8")
    _git_checked(repo, "init")
    _git_checked(repo, "config", "user.email", "state-layout-smoke@example.invalid")
    _git_checked(repo, "config", "user.name", "State Layout Smoke")
    _git_checked(repo, "add", ".")
    _git_checked(repo, "commit", "-m", "Initialize fixture repo")


def _task_spec() -> dict:
    return {
        "id": "state-layout-smoke",
        "version": "1",
        "status": "draft",
        "title": "State layout smoke",
        "goal": "Verify state/workspace layout without real Codex.",
        "scope": ["docs/example.md"],
        "not_in_scope": ["real Codex", "OpenAI", "deploy", "target repo mutation"],
        "task_class": "L2",
        "class_reason": "Bounded local fake-flow path ownership smoke.",
        "risks": ["state paths must not escape the configured state root"],
        "acceptance_criteria": ["fake-flow writes artifacts under the unified layout"],
        "required_smokes": ["git diff --check"],
        "allowed_paths": ["docs/**"],
        "forbidden_paths": ["derived_project_pack/**", "target_project_docs_manifest.md"],
        "allowed_actions": ["repo_only_executor"],
        "forbidden_actions": [
            "live",
            "deploy",
            "live_deploy",
            "SSH",
            "ssh",
            "root",
            "root_shell",
            "public_route_change",
            "production_runtime_mutation",
            "execution_from_discussion",
            "codex_worker_run",
            "api_endpoints",
            "ui_implementation",
            "auto_merge",
            "direct_target_mutation",
        ],
    }


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _git_checked(cwd: Path, *args: str) -> None:
    completed = subprocess.run(("git", *args), cwd=cwd, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed\nstdout={completed.stdout}\nstderr={completed.stderr}")


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


if __name__ == "__main__":
    main()
