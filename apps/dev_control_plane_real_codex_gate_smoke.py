"""Smoke-check gated Codex CLI target execution with a fake Codex binary.

This smoke never invokes the real Codex CLI. It verifies that the real execution
path is CLI-gated, uses a managed clone workspace, captures artifacts, and keeps
the original target repo unchanged.
"""

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
from dev_control_plane.target_projects import load_target_project_config, validate_target_project  # noqa: E402

RUNNER = ROOT / "apps" / "dev_control_plane_runner.py"
WB_CORE_CONFIG = ROOT / "configs" / "target_projects" / "wb_core.json"
WB_CORE_PATH = Path("/Users/ovlmacbook/Projects/wb-core")
MANDATORY_HANDOFF_BLOCKS = ("=== ДЛЯ КУРАТОРА ===", "=== СЖАТАЯ ПРОВЕРКА ===")


def main() -> None:
    with TemporaryDirectory(prefix="dev-control-plane-real-codex-gate-") as tmp:
        tmp_path = Path(tmp)
        target_repo = tmp_path / "fixture-target"
        state_dir = tmp_path / "state"
        config_path = tmp_path / "fixture_target.json"
        frozen_spec_path = tmp_path / "frozen_task_spec.json"
        fake_codex = tmp_path / "fake_codex.py"

        _create_fixture_target_repo(target_repo)
        _write_json(config_path, _fixture_target_config(target_repo))
        _write_json(frozen_spec_path, frozen_task_spec_payload_from_mapping(_draft_task_spec(), "2026-05-01T00:00:00Z"))
        _write_fake_codex(fake_codex)

        original_status_before = _git_text(target_repo, "status", "--short")
        prepared = _run_json(
            [
                "prepare-target-run",
                "--target-config",
                str(config_path),
                "--task-spec",
                str(frozen_spec_path),
                "--step-id",
                "step-001",
                "--state-dir",
                str(state_dir),
            ]
        )
        if prepared.get("status") != "prepared" or not Path(prepared["workspace_path"]).exists():
            raise AssertionError(f"prepare-target-run must create a managed workspace without execution: {prepared}")
        if prepared.get("step_id") != "custom-step-abc" or not prepared.get("warnings"):
            raise AssertionError(f"prepare-target-run must use first runnable custom step with warning: {prepared}")
        if Path(prepared["handoff_path"]).exists():
            raise AssertionError("prepare-target-run must not create a handoff")
        prepared_cleanup = _run_json(["cleanup-target-run", "--run-dir", prepared["run_dir"]])
        if prepared_cleanup.get("status") != "cleaned":
            raise AssertionError(f"prepared target workspace cleanup failed: {prepared_cleanup}")

        no_gate = _run_json(
            [
                "run-codex-cli",
                "--target-config",
                str(config_path),
                "--task-spec",
                str(frozen_spec_path),
                "--step-id",
                "step-001",
                "--state-dir",
                str(state_dir),
                "--codex-bin",
                str(fake_codex),
            ],
            expect_success=False,
        )
        if no_gate.get("status") != "blocked" or "--allow-real-codex" not in no_gate.get("blocker_reason", ""):
            raise AssertionError(f"Codex CLI without explicit gate must be blocked: {no_gate}")

        run = _run_json(
            [
                "run-codex-cli",
                "--target-config",
                str(config_path),
                "--task-spec",
                str(frozen_spec_path),
                "--step-id",
                "step-001",
                "--state-dir",
                str(state_dir),
                "--allow-real-codex",
                "--codex-bin",
                str(fake_codex),
            ]
        )
        if run.get("status") != "verifier_passed" or run.get("verifier_status") != "passed":
            raise AssertionError(f"fake Codex run must pass verifier: {run}")
        if run.get("step_id") != "custom-step-abc" or not run.get("warnings"):
            raise AssertionError(f"run-codex-cli must not block on mismatched requested step id: {run}")

        workspace_path = Path(run["workspace_path"]).resolve()
        if workspace_path == target_repo.resolve() or _is_relative_to(workspace_path, target_repo.resolve()):
            raise AssertionError(f"workspace must not overlap original target repo: {workspace_path}")
        expected_workspace_root = (state_dir / "workspaces" / run["run_id"]).resolve()
        if not _is_relative_to(workspace_path, expected_workspace_root):
            raise AssertionError(f"workspace must be owned by state workspaces: {workspace_path}")
        if not (workspace_path / "docs" / "fake_codex_result.md").exists():
            raise AssertionError("fake Codex changed file missing from managed workspace")

        if _git_text(target_repo, "status", "--short") != original_status_before:
            raise AssertionError("original fixture target repo changed during fake Codex run")

        diff_text = Path(run["diff_path"]).read_text(encoding="utf-8")
        if "docs/fake_codex_result.md" not in diff_text:
            raise AssertionError(f"diff artifact must capture fake changed file: {run['diff_path']}")

        handoff = Path(run["handoff_path"]).read_text(encoding="utf-8")
        for token in MANDATORY_HANDOFF_BLOCKS:
            if token not in handoff:
                raise AssertionError(f"handoff missing mandatory block: {token}")

        verify_passed = _run_json(["verify-target-run", "--run-dir", run["run_dir"]])
        if verify_passed.get("verifier_status") != "passed":
            raise AssertionError(f"verify-target-run must pass on fake Codex run: {verify_passed}")

        metadata_path = Path(run["run_dir"]) / "run.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["result"]["changed_files"] = [*metadata["result"].get("changed_files", []), "wb_core_docs_master/fake.md"]
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        verify_blocked = _run_json(["verify-target-run", "--run-dir", run["run_dir"]], expect_success=False)
        if verify_blocked.get("verifier_status") != "blocked":
            raise AssertionError(f"injected forbidden path must block target verifier: {verify_blocked}")
        if "wb_core_docs_master/fake.md" not in verify_blocked.get("forbidden_path_hits", []):
            raise AssertionError(f"forbidden path must be reported: {verify_blocked}")

        cleanup = _run_json(["cleanup-target-run", "--run-dir", run["run_dir"]])
        if cleanup.get("status") != "cleaned":
            raise AssertionError(f"cleanup-target-run must clean owned workspace: {cleanup}")
        if workspace_path.exists():
            raise AssertionError(f"cleanup-target-run left managed workspace behind: {workspace_path}")
        if not Path(run["run_dir"]).exists():
            raise AssertionError("cleanup-target-run should leave run metadata for audit")

        _validate_wb_core_read_only_if_available()

    print("dev-control-plane-real-codex-gate-smoke passed")


def _create_fixture_target_repo(repo: Path) -> None:
    (repo / "docs" / "architecture").mkdir(parents=True)
    (repo / "docs" / "modules").mkdir(parents=True)
    (repo / "migration").mkdir(parents=True)
    (repo / "README.md").write_text("# Fixture Target\n", encoding="utf-8")
    (repo / "docs" / "architecture" / "example.md").write_text("architecture source\n", encoding="utf-8")
    (repo / "docs" / "modules" / "00_INDEX__MODULES.md").write_text("modules source\n", encoding="utf-8")
    (repo / "migration" / "example.md").write_text("migration source\n", encoding="utf-8")
    _git_checked(repo, "init")
    _git_checked(repo, "config", "user.email", "dev-control-plane@example.invalid")
    _git_checked(repo, "config", "user.name", "Development Control Plane Smoke")
    _git_checked(repo, "add", ".")
    _git_checked(repo, "commit", "-m", "Initialize fixture target")


def _fixture_target_config(repo: Path) -> dict[str, Any]:
    return {
        "project_id": "fixture-target",
        "display_name": "Fixture Target",
        "repo_path": str(repo),
        "source_of_truth_paths": ["README.md", "docs/architecture/", "docs/modules/", "migration/"],
        "derived_secondary_paths": ["wb_core_docs_master/"],
        "default_forbidden_paths": ["wb_core_docs_master/**", "99_MANIFEST__DOCSET_VERSION.md"],
        "default_forbidden_actions": [
            "live_deploy",
            "ssh",
            "root_shell",
            "public_route_change",
            "secrets_write",
        ],
        "default_required_smokes": ["git diff --check"],
        "codex_prompt_contract": {
            "required_headers": ["Класс задачи:", "Причина классификации:", "Режим выполнения:"],
            "final_blocks": list(MANDATORY_HANDOFF_BLOCKS),
        },
        "control_plane_notes": ["fixture target remains read-only"],
        "product_plane_notes": ["no product-plane routes in smoke"],
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


def _draft_task_spec() -> dict[str, Any]:
    return {
        "id": "real-codex-gate-smoke",
        "version": "1",
        "status": "draft",
        "title": "Exercise gated Codex CLI execution",
        "goal": "Verify that the control-plane can run a gated fake Codex CLI in a managed target workspace.",
        "scope": ["Create a harmless docs artifact in the managed workspace only."],
        "not_in_scope": ["mutating the original target repo", "live deploy", "SSH/root actions"],
        "task_class": "L2",
        "class_reason": "bounded repo-only managed workspace execution smoke",
        "risks": ["execution automation must remain gated and workspace-scoped"],
        "acceptance_criteria": ["managed workspace receives fake Codex output", "original target repo stays unchanged"],
        "required_smokes": ["git diff --check"],
        "allowed_paths": ["docs/**"],
        "forbidden_paths": ["wb_core_docs_master/**", "99_MANIFEST__DOCSET_VERSION.md"],
        "allowed_actions": ["repo_only_executor", "managed_clone_execution", "real_codex_cli"],
        "forbidden_actions": ["live_deploy", "ssh", "root_shell", "public_route_change", "secrets_write"],
        "human_gates": [],
        "sprint_steps": [
            {
                "id": "custom-step-abc",
                "sequence": 1,
                "title": "Write fake Codex docs artifact",
                "goal": "Create docs/fake_codex_result.md inside the managed workspace.",
                "task_class": "L2",
                "scope": ["docs/fake_codex_result.md"],
                "acceptance_criteria": ["diff artifact includes docs/fake_codex_result.md"],
                "required_smokes": ["git diff --check"],
                "stop_conditions": ["stop if execution leaves managed workspace"],
            }
        ],
    }


def _write_fake_codex(path: Path) -> None:
    script = r'''#!/usr/bin/env python3
from pathlib import Path
import json
import sys

args = sys.argv[1:]
workspace = Path(args[args.index("--cd") + 1])
handoff_path = Path(args[args.index("--output-last-message") + 1])
(workspace / "docs").mkdir(parents=True, exist_ok=True)
(workspace / "docs" / "fake_codex_result.md").write_text("fake Codex result\n", encoding="utf-8")
handoff_path.parent.mkdir(parents=True, exist_ok=True)
handoff_path.write_text("""=== ДЛЯ КУРАТОРА ===

Статус: fake Codex CLI completed
Что сделано: wrote docs/fake_codex_result.md in managed workspace
Изменённые/созданные файлы: docs/fake_codex_result.md
Ключевой результат: fake Codex CLI path produced deterministic artifacts
Что НЕ тронуто / что осталось вне scope: original target repo, live/deploy/SSH/root
Следующий шаг: review verifier result
Если есть блокер — точная причина: none
Repo state: managed workspace only
Live deploy state: not run
Public verify result: not applicable
Sheet verify result: not applicable
Upload-ready source state: not applicable
Manual-only remainder: none
Commit status: not run
Commit hash: none
Push status: not run
PR status: not created
Ссылка на PR: none
Merge status: not run
Delete branch status: not run
Exact blocker: none

=== СЖАТАЯ ПРОВЕРКА ===

- fake Codex binary
- managed workspace only
- verifier owns completion decision
Главный вывод: gated Codex CLI path is smoke-tested without real Codex.
""", encoding="utf-8")
print(json.dumps({"status": "fake_codex_completed"}))
'''
    path.write_text(script, encoding="utf-8")
    path.chmod(0o755)


def _validate_wb_core_read_only_if_available() -> None:
    if not WB_CORE_PATH.exists():
        return
    before = _git_text(WB_CORE_PATH, "status", "--short")
    config = load_target_project_config(WB_CORE_CONFIG)
    validation = validate_target_project(config)
    if not validation.repo_exists or not validation.is_git_repo:
        raise AssertionError(f"wb-core target config should validate as a git repo when path exists: {validation}")
    after = _git_text(WB_CORE_PATH, "status", "--short")
    if after != before:
        raise AssertionError("wb-core original repo changed during real Codex gate smoke")


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


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _git_checked(cwd: Path, *args: str) -> None:
    result = subprocess.run(("git", *args), cwd=cwd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed\nstdout={result.stdout}\nstderr={result.stderr}")


def _git_text(cwd: Path, *args: str) -> str:
    result = subprocess.run(("git", *args), cwd=cwd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


if __name__ == "__main__":
    main()
