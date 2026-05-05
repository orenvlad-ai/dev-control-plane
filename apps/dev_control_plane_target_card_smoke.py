"""Smoke-check target card generation for remote warning and blocked targets."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time
from tempfile import TemporaryDirectory
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (SRC, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dev_control_plane.server import CockpitStateStore  # noqa: E402


def main() -> None:
    previous_fake = os.environ.get("DEV_CONTROL_PLANE_ENABLE_FAKE_CURATOR")
    os.environ["DEV_CONTROL_PLANE_ENABLE_FAKE_CURATOR"] = "1"
    try:
        with TemporaryDirectory(prefix="dev-control-plane-target-card-") as tmp:
            root = Path(tmp)
            config_dir = root / "configs"
            config_dir.mkdir(parents=True)
            source_repo = root / "source"
            bare_repo = root / "source.git"
            local_repo = root / "local"

            _create_source_repo(source_repo)
            _git_checked(root, "clone", "--bare", str(source_repo), str(bare_repo))
            _create_source_repo(local_repo)

            _write_json(config_dir / "remote.json", _remote_warning_config(f"file://{bare_repo}", root / "missing"))
            _write_json(config_dir / "blocked.json", _blocked_config(root / "missing-blocked"))
            _write_json(config_dir / "local.json", _local_config(local_repo))

            store = CockpitStateStore(root / "state", config_dir)
            remote = _draft_card(store, "remote-target", "wb-core")
            if remote.get("status") != "drafted":
                raise AssertionError(f"remote warning target must draft card successfully: {remote}")
            remote_summary = remote.get("task_spec", {}).get("target_context_summary", {})
            if remote_summary.get("validation_status") != "warning":
                raise AssertionError(f"remote target must remain warning, not blocked: {remote_summary}")
            if remote_summary.get("source_mode") != "remote_managed_clone":
                raise AssertionError(f"remote target source mode lost: {remote_summary}")
            if remote_summary.get("remote_source_available") is not True or remote_summary.get("managed_clone_ready") is not True:
                raise AssertionError(f"remote target must be managed-clone ready: {remote_summary}")
            if remote_summary.get("source_of_truth_paths_found") != []:
                raise AssertionError(f"hosted remote target should tolerate empty local source paths: {remote_summary}")
            if not remote.get("task_card", {}).get("warnings"):
                raise AssertionError(f"target warnings must be card warnings, not blockers: {remote}")

            remote_job_result = _draft_card_job(store, "remote-target-job", "wb-core")
            if remote_job_result.get("status") != "drafted":
                raise AssertionError(f"remote warning target async prepare flow must draft card successfully: {remote_job_result}")
            if remote_job_result.get("task_spec", {}).get("target_context_summary", {}).get("validation_status") != "warning":
                raise AssertionError(f"async prepare flow must preserve target warning status: {remote_job_result}")

            blocked = _draft_card(store, "blocked-target", "blocked-target")
            if blocked.get("status") != "blocked" or "repo_path does not exist" not in blocked.get("blocked_reason", ""):
                raise AssertionError(f"blocked target must return exact blocker without crashing: {blocked}")

            local = _draft_card(store, "local-target", "local-target")
            if local.get("status") != "drafted":
                raise AssertionError(f"local_path target card generation regressed: {local}")
            local_summary = local.get("task_spec", {}).get("target_context_summary", {})
            if local_summary.get("validation_status") != "valid" or "README.md" not in local_summary.get("source_of_truth_paths_found", []):
                raise AssertionError(f"local_path target summary must remain valid with source paths: {local_summary}")
    finally:
        if previous_fake is None:
            os.environ.pop("DEV_CONTROL_PLANE_ENABLE_FAKE_CURATOR", None)
        else:
            os.environ["DEV_CONTROL_PLANE_ENABLE_FAKE_CURATOR"] = previous_fake

    print("dev-control-plane-target-card-smoke passed")


def _draft_card(store: CockpitStateStore, title: str, target_project_id: str) -> dict[str, Any]:
    discussion = store.create_discussion({"title": title})
    store.add_message(
        discussion["id"],
        {"role": "operator", "content": "заменить UI label Витрина на Витрина 2"},
    )
    return store.draft_task_spec_from_discussion(
        discussion["id"],
        {"mode": "fake", "target_project_id": target_project_id},
    )


def _draft_card_job(store: CockpitStateStore, title: str, target_project_id: str) -> dict[str, Any]:
    discussion = store.create_discussion({"title": title})
    store.add_message(
        discussion["id"],
        {
            "role": "operator",
            "content": "Найди в UI место, где отображается название вкладки/раздела «Витрина», и замени видимый текст на «Витрина 2».",
        },
    )
    job = store.start_draft_task_spec_job(
        discussion["id"],
        {"mode": "fake", "target_project_id": target_project_id},
    )
    deadline = time.time() + 10
    while time.time() < deadline:
        latest = store.get_draft_task_spec_job(job["id"])
        if latest.get("status") in {"drafted", "blocked", "failed"}:
            return latest.get("result") or latest
        time.sleep(0.05)
    raise AssertionError(f"async draft card job did not finish: {store.get_draft_task_spec_job(job['id'])}")


def _create_source_repo(repo: Path) -> None:
    (repo / "docs" / "architecture").mkdir(parents=True)
    (repo / "docs" / "modules").mkdir(parents=True)
    (repo / "migration").mkdir(parents=True)
    (repo / "README.md").write_text("# Target Fixture\n", encoding="utf-8")
    (repo / "docs" / "architecture" / "card.md").write_text("# Architecture\n", encoding="utf-8")
    (repo / "docs" / "modules" / "card.md").write_text("# Module\n", encoding="utf-8")
    (repo / "migration" / "card.md").write_text("# Migration\n", encoding="utf-8")
    _git_checked(repo, "init", "-b", "main")
    _git_checked(repo, "config", "user.email", "dev-control-plane@example.invalid")
    _git_checked(repo, "config", "user.name", "Development Control Plane Smoke")
    _git_checked(repo, "add", ".")
    _git_checked(repo, "commit", "-m", "Initialize target fixture")


def _remote_warning_config(repo_url: str, missing_path: Path) -> dict[str, Any]:
    payload = _base_config("wb-core", "wb-core", missing_path)
    payload.update({"source_mode": "remote_managed_clone", "repo_url": repo_url, "branch": "main"})
    return payload


def _blocked_config(missing_path: Path) -> dict[str, Any]:
    return _base_config("blocked-target", "Blocked Target", missing_path)


def _local_config(repo_path: Path) -> dict[str, Any]:
    return _base_config("local-target", "Local Target", repo_path)


def _base_config(project_id: str, display_name: str, repo_path: Path) -> dict[str, Any]:
    return {
        "project_id": project_id,
        "display_name": display_name,
        "repo_path": str(repo_path),
        "source_of_truth_paths": ["README.md", "docs/architecture/", "docs/modules/", "migration/"],
        "derived_secondary_paths": ["wb_core_docs_master/"],
        "default_forbidden_paths": ["wb_core_docs_master/**", "99_MANIFEST__DOCSET_VERSION.md"],
        "default_forbidden_actions": ["live_deploy", "ssh", "root_shell", "public_route_change"],
        "default_required_smokes": ["git diff --check"],
        "codex_prompt_contract": {
            "required_headers": ["Класс задачи:", "Причина классификации:", "Режим выполнения:"],
            "final_blocks": ["=== ДЛЯ КУРАТОРА ===", "=== СЖАТАЯ ПРОВЕРКА ==="],
        },
        "control_plane_notes": ["target card smoke"],
        "product_plane_notes": ["no product mutation"],
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


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _git_checked(cwd: Path, *args: str) -> None:
    completed = subprocess.run(("git", *args), cwd=cwd, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed\nstdout={completed.stdout}\nstderr={completed.stderr}")


if __name__ == "__main__":
    main()
