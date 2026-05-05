"""Smoke-check wb-core UI-template allowed_paths and verifier policy."""

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

from dev_control_plane.ai import CuratorDraftRequest, draft_task_spec  # noqa: E402
from dev_control_plane.contracts import frozen_task_spec_payload_from_mapping  # noqa: E402
from dev_control_plane.execution import run_codex_cli  # noqa: E402
from dev_control_plane.target_projects import load_target_project_config, target_project_defaults  # noqa: E402


TASK_TEXT = "Найди в UI место, где отображается название вкладки/раздела «Витрина», и замени видимый текст на «Витрина 2»."
TEMPLATE_PATH = "packages/adapters/templates/sheet_vitrina_v1_web_vitrina.html"


def main() -> None:
    with TemporaryDirectory(prefix="dev-control-plane-allowed-paths-") as tmp_raw:
        tmp = Path(tmp_raw)
        repo = tmp / "wb-core"
        config_path = tmp / "wb_core.json"
        _create_fixture_repo(repo)
        _write_target_config(config_path, repo)
        target_config = load_target_project_config(config_path)
        defaults = target_project_defaults(target_config)

        draft = draft_task_spec(
            CuratorDraftRequest(
                discussion_id="allowed-paths-smoke",
                messages=({"role": "operator", "content": TASK_TEXT},),
                target_project_id="wb-core",
                target_defaults=defaults,
                mode="fake",
            )
        )
        if draft.status != "success" or not draft.task_spec:
            raise AssertionError(f"fake curator did not produce task spec: {draft}")
        allowed_paths = list(draft.task_spec.get("allowed_paths", []))
        if TEMPLATE_PATH not in allowed_paths or "packages/adapters/templates/*.html" not in allowed_paths:
            raise AssertionError(f"UI-label task must include bounded template allowed_paths: {allowed_paths}")
        for unsafe in ("packages/**", "runtime/**", "deploy/**", "infra/**"):
            if unsafe in allowed_paths:
                raise AssertionError(f"allowed_paths must not open broad unsafe path {unsafe}: {allowed_paths}")

        frozen = frozen_task_spec_payload_from_mapping(draft.task_spec)
        ok_codex = tmp / "fake-codex-ok.py"
        _write_fake_codex(ok_codex, TEMPLATE_PATH, "Витрина 2")
        ok_result = run_codex_cli(
            frozen,
            target_config=target_config,
            step_id="step-001",
            state_dir=tmp / "state-ok",
            allow_real_codex=True,
            codex_bin=str(ok_codex),
        )
        if ok_result.status != "verifier_passed" or ok_result.verifier_status != "passed":
            raise AssertionError(f"expected UI-label template diff must pass verifier: {ok_result}")
        if ok_result.changed_files != (TEMPLATE_PATH,):
            raise AssertionError(f"expected only template file to change: {ok_result.changed_files}")

        bad_codex = tmp / "fake-codex-bad.py"
        _write_fake_codex(bad_codex, "runtime/unsafe.txt", "bad")
        bad_result = run_codex_cli(
            frozen,
            target_config=target_config,
            step_id="step-001",
            state_dir=tmp / "state-bad",
            allow_real_codex=True,
            codex_bin=str(bad_codex),
        )
        if bad_result.status not in {"blocked", "failed"} or "runtime/unsafe.txt" not in str(bad_result.blocker_reason):
            raise AssertionError(f"forbidden runtime path must stay blocked: {bad_result}")

    print("dev-control-plane-allowed-paths-smoke passed")


def _create_fixture_repo(repo: Path) -> None:
    template = repo / TEMPLATE_PATH
    template.parent.mkdir(parents=True)
    template.write_text("<button>Витрина</button>\n", encoding="utf-8")
    (repo / "README.md").write_text("# wb-core fixture\n", encoding="utf-8")
    _git(repo.parent, "init", str(repo))
    _git(repo, "config", "user.email", "smoke@example.invalid")
    _git(repo, "config", "user.name", "Smoke Test")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "Initial fixture")


def _write_target_config(path: Path, repo: Path) -> None:
    payload = {
        "project_id": "wb-core",
        "display_name": "wb-core",
        "repo_path": str(repo),
        "source_mode": "local_path",
        "source_of_truth_paths": ["README.md", "docs/architecture/", "docs/modules/", "migration/"],
        "default_forbidden_paths": [
            "wb_core_docs_master/**",
            "99_MANIFEST__DOCSET_VERSION.md",
            "runtime/**",
            "deploy/**",
            "infra/**",
            "artifacts/registry_upload_http_entrypoint/**",
        ],
        "default_forbidden_actions": ["live_deploy", "ssh", "root_shell", "public_route_change", "direct_target_mutation", "auto_merge"],
        "default_required_smokes": ["git diff --check"],
        "target_readonly_by_default": True,
        "execution_policy": {
            "allow_managed_clone_execution": True,
            "allow_direct_target_mutation": False,
            "allow_live_deploy": False,
            "allow_auto_merge": False,
            "require_explicit_real_codex_flag": True,
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_fake_codex(path: Path, changed_path: str, value: str) -> None:
    script = f'''#!/usr/bin/env python3
from pathlib import Path
import sys

if "--version" in sys.argv:
    print("fake-codex-allowed-paths 1.0")
    raise SystemExit(0)

workspace = Path(sys.argv[sys.argv.index("--cd") + 1])
handoff = Path(sys.argv[sys.argv.index("--output-last-message") + 1])
target = workspace / {changed_path!r}
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text({value!r} + "\\n", encoding="utf-8")
handoff.parent.mkdir(parents=True, exist_ok=True)
handoff.write_text("""=== ДЛЯ КУРАТОРА ===

Статус: fake Codex completed
Что сделано: changed fixture path
Изменённые/созданные файлы: {changed_path}
Что НЕ тронуто / что осталось вне scope: original target, PR, merge, deploy
Проверки: fake
Если есть блокер — точная причина: none

=== СЖАТАЯ ПРОВЕРКА ===

- managed clone only
- verifier owns result
- fake Codex
Главный вывод: smoke.
""", encoding="utf-8")
'''
    path.write_text(script, encoding="utf-8")
    path.chmod(0o755)


def _git(cwd: Path, *args: str) -> None:
    completed = subprocess.run(("git", *args), cwd=cwd, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed\nstdout={completed.stdout}\nstderr={completed.stderr}")


if __name__ == "__main__":
    main()
