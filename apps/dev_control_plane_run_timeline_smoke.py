"""Smoke-check handoff contract diagnostics and run timeline parsing."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (SRC, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dev_control_plane.contracts import (  # noqa: E402
    build_codex_prompt,
    frozen_task_spec_payload_from_mapping,
    sprint_steps_from_task_spec_mapping,
    task_spec_from_mapping,
)
from dev_control_plane.execution import cleanup_target_run, run_codex_cli  # noqa: E402
from dev_control_plane.target_projects import TargetProjectConfig  # noqa: E402
from dev_control_plane.timeline import parse_codex_jsonl_log  # noqa: E402


def main() -> None:
    with TemporaryDirectory(prefix="dev-control-plane-timeline-smoke-") as tmp_raw:
        tmp = Path(tmp_raw)
        target_repo = tmp / "target-repo"
        _create_fixture_target(target_repo)
        target_config = _target_config(target_repo)
        frozen = frozen_task_spec_payload_from_mapping(_draft_spec(), frozen_at="2026-05-05T00:00:00Z")
        task_spec = task_spec_from_mapping(frozen)
        step = sprint_steps_from_task_spec_mapping(frozen, task_spec)[0]
        prompt = build_codex_prompt(task_spec, step)
        for token in (
            'Your final answer MUST start with the exact first line: "=== ДЛЯ КУРАТОРА ===".',
            'Do not start the final answer with "Статус:"',
            "If either exact heading is missing, the deterministic verifier will fail the run.",
        ):
            if token not in prompt:
                raise AssertionError(f"prompt missing strict handoff contract token: {token}")

        bad_codex = tmp / "bad-codex"
        good_codex = tmp / "good-codex"
        _write_fake_codex(bad_codex, include_curator_block=False)
        _write_fake_codex(good_codex, include_curator_block=True)

        original_head = _git(target_repo, "rev-parse", "HEAD")
        original_status = _git(target_repo, "status", "--short")
        bad = run_codex_cli(
            frozen,
            target_config=target_config,
            step_id=None,
            state_dir=tmp / "runs-bad",
            allow_real_codex=True,
            codex_bin=str(bad_codex),
        )
        if bad.status != "failed":
            raise AssertionError(f"bad handoff run must fail verifier: {bad}")
        if "отсутствует === ДЛЯ КУРАТОРА ===" not in str(bad.blocker_reason):
            raise AssertionError(f"bad handoff reason must name missing curator block: {bad.blocker_reason}")
        if bad.next_manual_step != "Повторите запуск после исправления prompt contract или проверьте handoff вручную.":
            raise AssertionError(f"bad handoff next step must be operator-readable: {bad.next_manual_step}")
        cleanup_target_run(Path(bad.run_dir))

        good = run_codex_cli(
            frozen,
            target_config=target_config,
            step_id=None,
            state_dir=tmp / "runs-good",
            allow_real_codex=True,
            codex_bin=str(good_codex),
        )
        if good.status != "verifier_passed" or good.verifier_status != "passed":
            raise AssertionError(f"good handoff run must pass verifier: {good}")
        cleanup_target_run(Path(good.run_dir))
        if _git(target_repo, "rev-parse", "HEAD") != original_head or _git(target_repo, "status", "--short") != original_status:
            raise AssertionError("fixture target repo mutated during timeline smoke")

        log_path = tmp / "codex-jsonl.log"
        log_path.write_text(
            "\n".join(
                (
                    "plain non-json line",
                    '{"type":"thread.started"}',
                    '{"type":"turn.started","message":"reading task"}',
                    '{"type":"agent_message","message":"thinking about a bounded docs change"}',
                    '{"type":"command_execution","status":"in_progress","command":"git diff --check","output":"' + ("x" * 900) + '"}',
                    '{"type":"command_execution","status":"completed","command":"git diff --check"}',
                    '{"type":"file_change","path":"docs/dev_control_plane_probe.md"}',
                    '{"type":"turn.completed"}',
                    '{"type":',
                )
            )
            + "\n",
            encoding="utf-8",
        )
        events = parse_codex_jsonl_log(log_path)
        titles = [event["title"] for event in events]
        for expected in (
            "Codex начал работу...",
            "Codex анализирует задачу...",
            "Codex запустил проверку: git diff --check",
            "Проверка прошла: git diff --check",
            "Codex изменил файл: docs/dev_control_plane_probe.md",
            "Codex завершил ход работы.",
        ):
            if expected not in titles:
                raise AssertionError(f"timeline parser missing {expected}: {events}")
        if not any(event["level"] == "warning" for event in events):
            raise AssertionError(f"invalid JSON line should produce warning event: {events}")
        long_details = [event.get("detail") or "" for event in events if event["title"].startswith("Codex запустил проверку")]
        if not long_details or len(long_details[0]) > 500:
            raise AssertionError(f"timeline details must be present and truncated: {long_details}")

    print("dev-control-plane-run-timeline-smoke passed")


def _create_fixture_target(repo: Path) -> None:
    (repo / "docs").mkdir(parents=True)
    (repo / "README.md").write_text("# Timeline fixture\n", encoding="utf-8")
    _git_checked(repo.parent, "init", str(repo))
    _git_checked(repo, "config", "user.email", "smoke@example.invalid")
    _git_checked(repo, "config", "user.name", "Smoke Test")
    _git_checked(repo, "add", ".")
    _git_checked(repo, "commit", "-m", "Initial timeline fixture")


def _target_config(repo: Path) -> TargetProjectConfig:
    return TargetProjectConfig(
        project_id="timeline-fixture",
        display_name="timeline-fixture",
        repo_path=str(repo),
        source_of_truth_paths=("README.md", "docs/"),
        derived_secondary_paths=("derived_project_pack/",),
        default_forbidden_paths=("derived_project_pack/**", "target_project_docs_manifest.md"),
        default_forbidden_actions=(
            "live_deploy",
            "ssh",
            "root_shell",
            "public_route_change",
            "direct_target_mutation",
            "auto_merge",
            "secrets_write",
        ),
        default_required_smokes=("git diff --check",),
        codex_prompt_contract={
            "required_headers": ["Класс задачи:", "Причина классификации:", "Режим выполнения:"],
            "final_blocks": ["=== ДЛЯ КУРАТОРА ===", "=== СЖАТАЯ ПРОВЕРКА ==="],
        },
        control_plane_notes=("target repo is read-only by default",),
        product_plane_notes=("fixture target has no product plane",),
        target_readonly_by_default=True,
        execution_policy={
            "default_mode": "fake",
            "allow_managed_clone_execution": True,
            "allow_direct_target_mutation": False,
            "allow_live_deploy": False,
            "allow_auto_merge": False,
            "require_explicit_real_codex_flag": True,
        },
    )


def _draft_spec() -> dict:
    return {
        "id": "timeline-handoff-task",
        "version": "1.0",
        "status": "draft",
        "title": "Timeline handoff probe",
        "goal": "Create a docs-only probe file in a managed clone.",
        "scope": ["Create docs/dev_control_plane_probe.md."],
        "not_in_scope": ["Do not mutate original target repo.", "Do not commit, push, merge or deploy."],
        "task_class": "L3",
        "class_reason": "Smoke covers gated managed-clone execution contract.",
        "risks": ["Fake Codex binary simulates handoff formatting."],
        "acceptance_criteria": ["probe file exists", "original target repo unchanged"],
        "required_smokes": ["git diff --check"],
        "allowed_paths": ["docs/dev_control_plane_probe.md"],
        "forbidden_paths": ["derived_project_pack/**", "target_project_docs_manifest.md"],
        "allowed_actions": [],
        "forbidden_actions": [
            "live_deploy",
            "ssh",
            "root_shell",
            "public_route_change",
            "direct_target_mutation",
            "auto_merge",
            "secrets_write",
            "execution_from_discussion",
        ],
        "human_gates": ["operator confirms managed clone Codex run"],
    }


def _write_fake_codex(path: Path, *, include_curator_block: bool) -> None:
    curator_block = (
        '"=== ДЛЯ КУРАТОРА ===\\n"\n'
        '    "Статус: fake Codex completed\\n"\n'
        if include_curator_block
        else '"Статус: fake Codex completed\\n"\n'
    )
    path.write_text(
        f"""#!/usr/bin/env python3
from pathlib import Path
import sys

if "--version" in sys.argv:
    print("fake-codex-timeline 1.0")
    raise SystemExit(0)

workspace = Path(sys.argv[sys.argv.index("--cd") + 1])
handoff = Path(sys.argv[sys.argv.index("--output-last-message") + 1])
(workspace / "docs").mkdir(parents=True, exist_ok=True)
(workspace / "docs" / "dev_control_plane_probe.md").write_text("timeline probe\\n", encoding="utf-8")
handoff.write_text(
    {curator_block}
    "Что сделано: created docs/dev_control_plane_probe.md\\n"
    "Изменённые/созданные файлы: docs/dev_control_plane_probe.md\\n"
    "Ключевой результат: probe artifact created\\n"
    "Что НЕ тронуто / что осталось вне scope: original target repo, live/deploy/SSH/root\\n"
    "Следующий шаг: review diff\\n"
    "Если есть блокер — точная причина: none\\n"
    "\\n=== СЖАТАЯ ПРОВЕРКА ===\\n"
    "- fake Codex binary\\n"
    "- managed clone only\\n"
    "- verifier contract smoke\\n"
    "Главный вывод: handoff contract path exercised.\\n",
    encoding="utf-8",
)
print('{{"type":"thread.started"}}')
print('{{"type":"file_change","path":"docs/dev_control_plane_probe.md"}}')
print('{{"type":"command_execution","status":"completed","command":"git diff --check"}}')
print('{{"type":"turn.completed"}}')
""",
        encoding="utf-8",
    )
    path.chmod(0o700)


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise AssertionError(result.stderr or result.stdout)
    return result.stdout.strip()


def _git_checked(repo: Path, *args: str) -> None:
    _git(repo, *args)


if __name__ == "__main__":
    main()
