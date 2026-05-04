"""Smoke-check for target project adapter/config support."""

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

from dev_control_plane.ai import CuratorDraftRequest, draft_task_spec  # noqa: E402
from dev_control_plane.target_projects import (  # noqa: E402
    load_target_project_config,
    merge_target_defaults_into_task_spec_payload,
    target_project_defaults,
    validate_target_project,
)

CLI = ROOT / "apps" / "dev_control_plane_target_cli.py"
WB_CORE_CONFIG = ROOT / "configs" / "target_projects" / "wb_core.json"


def main() -> None:
    with TemporaryDirectory(prefix="dev-control-plane-target-smoke-") as tmp:
        tmp_path = Path(tmp)
        fixture_repo = tmp_path / "fixture-target"
        fixture_config_dir = tmp_path / "configs"
        fixture_config_dir.mkdir(parents=True)
        fixture_config = fixture_config_dir / "fixture.json"
        snapshot_path = tmp_path / "snapshot.json"

        _create_fixture_repo(fixture_repo)
        _write_fixture_config(fixture_config, fixture_repo)

        list_summary = _run_json("list-targets", "--config-dir", str(fixture_config_dir))
        if list_summary.get("status") != "ok" or len(list_summary.get("targets", [])) != 1:
            raise AssertionError(f"list-targets must report fixture target: {list_summary}")

        before_status = _git_text(fixture_repo, "status", "--short")
        validate_summary = _run_json("validate-target", "--config", str(fixture_config))
        if validate_summary.get("status") != "valid":
            raise AssertionError(f"fixture target must validate cleanly: {validate_summary}")
        if validate_summary.get("repo_exists") is not True or validate_summary.get("is_git_repo") is not True:
            raise AssertionError(f"fixture target must be an existing git repo: {validate_summary}")

        snapshot_summary = _run_json(
            "snapshot-target",
            "--config",
            str(fixture_config),
            "--output",
            str(snapshot_path),
            "--max-bytes-per-file",
            "5000",
        )
        if snapshot_summary.get("status") != "snapshot_created" or snapshot_summary.get("source_file_count", 0) < 4:
            raise AssertionError(f"snapshot-target must capture fixture source docs: {snapshot_summary}")
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        source_paths = {item.get("path") for item in snapshot.get("source_files", [])}
        for required in ("README.md", "docs/architecture/example.md", "docs/modules/00_INDEX__MODULES.md", "migration/example.md"):
            if required not in source_paths:
                raise AssertionError(f"snapshot missing source file: {required}")
        for path in ("derived_project_pack/**", "target_project_docs_manifest.md"):
            if path not in snapshot.get("forbidden_paths", []):
                raise AssertionError(f"snapshot missing forbidden path default: {path}")
        if before_status != _git_text(fixture_repo, "status", "--short"):
            raise AssertionError("target validation/snapshot must not mutate fixture repo")

        _validate_real_wb_core_config_read_only()
        _exercise_target_defaults_integration()

    print("dev-control-plane-target-smoke passed")


def _create_fixture_repo(repo: Path) -> None:
    (repo / "docs" / "architecture").mkdir(parents=True)
    (repo / "docs" / "modules").mkdir(parents=True)
    (repo / "migration").mkdir(parents=True)
    (repo / "README.md").write_text("# Fixture Target\n\nCanonical summary.\n", encoding="utf-8")
    (repo / "docs" / "architecture" / "example.md").write_text("# Architecture\n", encoding="utf-8")
    (repo / "docs" / "modules" / "00_INDEX__MODULES.md").write_text("# Modules\n", encoding="utf-8")
    (repo / "migration" / "example.md").write_text("# Migration\n", encoding="utf-8")
    _run_git(repo, "init")
    _run_git(repo, "add", ".")
    _run_git(repo, "-c", "user.name=Smoke", "-c", "user.email=smoke@example.invalid", "commit", "-m", "init fixture")


def _write_fixture_config(path: Path, repo: Path) -> None:
    payload = {
        "project_id": "fixture-target",
        "display_name": "Fixture Target",
        "repo_path": str(repo),
        "source_of_truth_paths": [
            "README.md",
            "docs/architecture/",
            "docs/modules/",
            "migration/",
        ],
        "derived_secondary_paths": ["derived_project_pack/"],
        "default_forbidden_paths": ["derived_project_pack/**", "target_project_docs_manifest.md"],
        "default_forbidden_actions": ["live_deploy", "ssh", "root_shell", "public_route_change"],
        "default_required_smokes": ["git diff --check"],
        "codex_prompt_contract": {
            "required_headers": ["Класс задачи:", "Причина классификации:", "Режим выполнения:"],
            "final_blocks": ["=== ДЛЯ КУРАТОРА ===", "=== СЖАТАЯ ПРОВЕРКА ==="],
        },
        "control_plane_notes": ["fixture target is read-only"],
        "product_plane_notes": ["fixture has no product-plane"],
        "target_readonly_by_default": True,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _validate_real_wb_core_config_read_only() -> None:
    config = load_target_project_config(WB_CORE_CONFIG)
    repo = Path(config.repo_path)
    if not repo.exists():
        print("wb-core target path missing; real target validation skipped")
        return
    before_status = _git_text(repo, "status", "--short")
    result = validate_target_project(config)
    if result.status == "blocked":
        raise AssertionError(f"wb-core target validation must not be blocked when repo exists: {result}")
    if result.repo_exists is not True or result.is_git_repo is not True:
        raise AssertionError(f"wb-core target must be existing git repo: {result}")
    if "README.md" not in result.source_of_truth_found:
        raise AssertionError(f"wb-core target must find README.md: {result}")
    if not any(path.startswith("docs/architecture") for path in result.source_of_truth_found):
        raise AssertionError(f"wb-core target must find docs/architecture source path: {result}")
    after_status = _git_text(repo, "status", "--short")
    if before_status != after_status:
        raise AssertionError("wb-core read-only validation changed git status")


def _exercise_target_defaults_integration() -> None:
    config = load_target_project_config(WB_CORE_CONFIG)
    draft = {
        "id": "task-target-defaults-smoke",
        "version": "v1",
        "status": "draft",
        "title": "Target defaults smoke",
        "goal": "Validate target defaults merge into a draft task spec.",
        "scope": ["src/dev_control_plane/target_projects.py"],
        "not_in_scope": ["target repo mutation"],
        "task_class": "L2",
        "class_reason": "Repo-only smoke for target adapter defaults.",
        "risks": [],
        "acceptance_criteria": ["Target defaults are merged"],
        "required_smokes": [],
        "allowed_paths": ["src/dev_control_plane/target_projects.py"],
        "forbidden_paths": [],
        "allowed_actions": ["repo_edit"],
        "forbidden_actions": [],
        "human_gates": [],
        "frozen_at": None,
        "spec_hash": None,
    }
    merged = merge_target_defaults_into_task_spec_payload(draft, config)
    for path in ("wb_core_docs_master/**", "99_MANIFEST__DOCSET_VERSION.md"):
        if path not in merged.get("forbidden_paths", []):
            raise AssertionError(f"merged target defaults missing forbidden path: {path}")
    for action in ("live_deploy", "ssh", "root_shell", "public_route_change"):
        if action not in merged.get("forbidden_actions", []):
            raise AssertionError(f"merged target defaults missing forbidden action: {action}")
    if "git diff --check" not in merged.get("required_smokes", []):
        raise AssertionError("merged target defaults missing required smoke")

    result = draft_task_spec(
        CuratorDraftRequest(
            discussion_id="target-defaults",
            messages=[{"role": "operator", "content": "Prepare a bounded wb-core repo-only task."}],
            mode="fake",
            target_project_id=config.project_id,
            target_defaults=target_project_defaults(config),
        )
    )
    if result.status != "success" or not result.task_spec:
        raise AssertionError(f"fake curator must apply target defaults: {result}")
    for path in ("wb_core_docs_master/**", "99_MANIFEST__DOCSET_VERSION.md"):
        if path not in result.task_spec.get("forbidden_paths", []):
            raise AssertionError(f"fake draft missing target forbidden path: {path}")
    if "git diff --check" not in result.task_spec.get("required_smokes", []):
        raise AssertionError("fake draft missing target required smoke")


def _run_json(*args: str) -> dict[str, Any]:
    completed = subprocess.run(
        [sys.executable, str(CLI), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise AssertionError(f"target CLI failed: {args}\nstdout={completed.stdout}\nstderr={completed.stderr}")
    return json.loads(completed.stdout)


def _run_git(cwd: Path, *args: str) -> None:
    completed = subprocess.run(("git", *args), cwd=cwd, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed\nstdout={completed.stdout}\nstderr={completed.stderr}")


def _git_text(cwd: Path, *args: str) -> str:
    completed = subprocess.run(("git", *args), cwd=cwd, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()


if __name__ == "__main__":
    main()
