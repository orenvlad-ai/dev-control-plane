"""Smoke-check remote managed clone target source without mutating wb-core."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (SRC, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dev_control_plane.contracts import frozen_task_spec_payload_from_mapping  # noqa: E402
from dev_control_plane.execution import create_managed_target_workspace  # noqa: E402
from dev_control_plane.state_layout import ControlPlaneStateLayout  # noqa: E402
from dev_control_plane.target_projects import load_target_project_config, validate_target_project  # noqa: E402

RUNNER = ROOT / "apps" / "dev_control_plane_runner.py"


def main() -> None:
    with TemporaryDirectory(prefix="dev-control-plane-remote-target-") as tmp:
        root = Path(tmp)
        source_repo = root / "source"
        bare_repo = root / "source.git"
        missing_local_path = root / "missing-local-wb-core"
        config_path = root / "target.json"
        task_spec_path = root / "task.json"
        state_dir = root / "state"

        _create_source_repo(source_repo)
        _git_checked(root, "clone", "--bare", str(source_repo), str(bare_repo))
        repo_url = f"file://{bare_repo}"
        _write_json(config_path, _remote_config(repo_url, missing_local_path))
        _write_json(task_spec_path, frozen_task_spec_payload_from_mapping(_task_spec(), "2026-05-05T00:00:00Z"))

        config = load_target_project_config(config_path)
        validation = validate_target_project(config)
        if validation.status != "warning":
            raise AssertionError(f"remote target with missing local path must warn, not block: {validation}")
        if not validation.remote_source_available or not validation.managed_clone_ready:
            raise AssertionError(f"remote target must be clone-ready: {validation}")
        if validation.repo_exists:
            raise AssertionError("missing local repo_path must not be required in remote mode")

        layout = ControlPlaneStateLayout.from_path(state_dir)
        run_layout = layout.run_layout("run-remote-source-smoke")
        run_layout.ensure_dirs()
        workspace = create_managed_target_workspace(
            config,
            run_layout.run_dir,
            workspace_path=run_layout.workspace_dir(config.project_id),
        )
        workspace_path = Path(workspace.workspace_path)
        if not (workspace_path / "README.md").exists():
            raise AssertionError(f"remote managed clone did not materialize source files: {workspace_path}")
        if missing_local_path.exists():
            raise AssertionError("remote managed clone must not create or mutate configured local repo_path")

        prepared = _run_json(
            [
                "prepare-target-run",
                "--target-config",
                str(config_path),
                "--task-spec",
                str(task_spec_path),
                "--state-dir",
                str(state_dir),
            ]
        )
        if prepared.get("status") != "prepared":
            raise AssertionError(f"remote prepare-target-run must prepare managed clone: {prepared}")
        prepared_workspace = Path(prepared["workspace_path"])
        if not (prepared_workspace / "docs" / "architecture" / "remote.md").exists():
            raise AssertionError(f"prepared remote workspace missing expected source file: {prepared}")
        cleanup = _run_json(["cleanup-target-run", "--run-dir", prepared["run_dir"]])
        if cleanup.get("status") != "cleaned":
            raise AssertionError(f"remote cleanup must clean managed workspace: {cleanup}")
        if prepared_workspace.exists():
            raise AssertionError("cleanup-target-run must remove remote managed workspace")
        if missing_local_path.exists():
            raise AssertionError("remote prepare/cleanup must not create configured local repo_path")

    print("dev-control-plane-target-remote-source-smoke passed")


def _create_source_repo(repo: Path) -> None:
    (repo / "docs" / "architecture").mkdir(parents=True)
    (repo / "docs" / "modules").mkdir(parents=True)
    (repo / "migration").mkdir(parents=True)
    (repo / "README.md").write_text("# Remote Fixture\n", encoding="utf-8")
    (repo / "docs" / "architecture" / "remote.md").write_text("# Remote Architecture\n", encoding="utf-8")
    (repo / "docs" / "modules" / "remote.md").write_text("# Remote Module\n", encoding="utf-8")
    (repo / "migration" / "remote.md").write_text("# Remote Migration\n", encoding="utf-8")
    _git_checked(repo, "init", "-b", "main")
    _git_checked(repo, "config", "user.email", "dev-control-plane@example.invalid")
    _git_checked(repo, "config", "user.name", "Development Control Plane Smoke")
    _git_checked(repo, "add", ".")
    _git_checked(repo, "commit", "-m", "Initialize remote fixture")


def _remote_config(repo_url: str, missing_local_path: Path) -> dict[str, Any]:
    return {
        "project_id": "wb-core",
        "display_name": "wb-core",
        "repo_path": str(missing_local_path),
        "source_mode": "remote_managed_clone",
        "repo_url": repo_url,
        "branch": "main",
        "source_of_truth_paths": ["README.md", "docs/architecture/", "docs/modules/", "migration/"],
        "derived_secondary_paths": ["wb_core_docs_master/"],
        "default_forbidden_paths": ["wb_core_docs_master/**", "99_MANIFEST__DOCSET_VERSION.md"],
        "default_forbidden_actions": ["live_deploy", "ssh", "root_shell", "public_route_change"],
        "default_required_smokes": ["git diff --check"],
        "codex_prompt_contract": {
            "required_headers": ["Класс задачи:", "Причина классификации:", "Режим выполнения:"],
            "final_blocks": ["=== ДЛЯ КУРАТОРА ===", "=== СЖАТАЯ ПРОВЕРКА ==="],
        },
        "control_plane_notes": ["remote source smoke"],
        "product_plane_notes": ["target production remains untouched"],
        "target_readonly_by_default": True,
        "execution_policy": {
            "default_mode": "fake",
            "allow_managed_clone_execution": True,
            "allow_direct_target_mutation": False,
            "allow_live_deploy": False,
            "allow_auto_merge": False,
            "require_explicit_real_codex_flag": True,
        },
    }


def _task_spec() -> dict[str, Any]:
    return {
        "id": "remote-target-smoke",
        "version": "1",
        "status": "draft",
        "title": "Remote target smoke",
        "goal": "Prepare a managed clone from remote source only.",
        "scope": ["docs/**"],
        "not_in_scope": ["original target mutation", "production deploy"],
        "task_class": "L3",
        "class_reason": "remote target source boundary smoke",
        "explicit_policy_note": "L3 smoke validates remote managed clone policy without target mutation.",
        "risks": [],
        "acceptance_criteria": ["managed clone is created under state"],
        "required_smokes": ["git diff --check"],
        "allowed_paths": ["docs/**"],
        "forbidden_paths": ["wb_core_docs_master/**", "99_MANIFEST__DOCSET_VERSION.md"],
        "allowed_actions": ["managed_clone_execution"],
        "forbidden_actions": ["live_deploy", "ssh", "root_shell", "public_route_change"],
        "human_gates": [],
        "sprint_steps": [
            {
                "id": "remote-step",
                "sequence": 1,
                "title": "Prepare remote clone",
                "goal": "Create managed workspace only.",
                "task_class": "L3",
                "scope": ["docs/**"],
                "acceptance_criteria": ["workspace exists"],
                "required_smokes": ["git diff --check"],
                "stop_conditions": ["stop on target mutation"],
            }
        ],
    }


def _run_json(args: list[str]) -> dict[str, Any]:
    completed = subprocess.run(
        [sys.executable, str(RUNNER), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise AssertionError(f"runner failed: {args}\nstdout={completed.stdout}\nstderr={completed.stderr}")
    return json.loads(completed.stdout)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _git_checked(cwd: Path, *args: str) -> None:
    completed = subprocess.run(("git", *args), cwd=cwd, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed\nstdout={completed.stdout}\nstderr={completed.stderr}")


if __name__ == "__main__":
    main()
