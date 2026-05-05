"""Smoke-check local UI managed Codex endpoint with a fake Codex binary.

This smoke never invokes the real Codex CLI. It verifies that the local-only
server can start the gated UI path in a managed clone and that the original
target repo remains unchanged.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from tempfile import TemporaryDirectory
from urllib import error as urllib_error, request as urllib_request

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "apps" / "dev_control_plane_server.py"


def main() -> None:
    port = _free_port()
    with TemporaryDirectory(prefix="dev-control-plane-real-ui-smoke-") as tmp_raw:
        tmp = Path(tmp_raw)
        target_repo = tmp / "target-repo"
        config_dir = tmp / "configs"
        state_dir = tmp / "state"
        fake_codex = tmp / "fake-codex"
        _create_fixture_target(target_repo)
        _write_target_config(config_dir, target_repo)
        _write_fake_codex(fake_codex)
        original_status = _git(target_repo, "status", "--short")
        original_head = _git(target_repo, "rev-parse", "HEAD")

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
                "--target-config-dir",
                str(config_dir),
            ],
            cwd=ROOT,
            env=_server_env(tmp / "secrets", fake_codex),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        run_id = None
        try:
            base_url = f"http://127.0.0.1:{port}"
            _wait_ready(base_url)
            html = _get_text(base_url + "/")
            for token in (
                "Подготовить задачу",
                "Запустить Codex безопасно",
                "Результат выполнения",
                "Изменённые файлы",
                "Показать diff",
                "Показать handoff",
                "Дополнительные действия",
                "Тестовый прогон без Codex",
                "Ход выполнения",
                "Готовлю managed clone",
                "Codex выполняет задачу",
                "Проверяю результат",
                "managed clone",
                "Оригинальный wb-core не меняется",
            ):
                if token not in html:
                    raise AssertionError(f"root UI missing managed Codex token: {token}")
            for token in ("max-height: 400px", "overflow-y: auto"):
                if token not in html:
                    raise AssertionError(f"timeline must be fixed-height scrollable: {token}")

            state = _get_json(base_url + "/api/state")
            if state.get("real_codex_ui_enabled") is not True or state.get("real_codex_ui_mode") != "managed_clone_only":
                raise AssertionError(f"state must expose gated managed Codex UI mode: {state}")
            connections = _get_json(base_url + "/api/connections/status")
            if connections.get("control_plane", {}).get("real_codex_ui_enabled") is not True:
                raise AssertionError(f"connections must expose managed Codex UI mode: {connections}")

            draft = _post_json(base_url + "/api/task-specs", _task_spec(status="draft"))
            _expect_http_error(
                lambda: _post_json(base_url + f"/api/task-specs/{draft['id']}/run-codex-managed", {}),
                expected_status=400,
            )
            frozen_summary = _post_json(
                base_url + f"/api/task-specs/{draft['id']}/freeze",
                {"frozen_at": "2026-05-05T00:00:00Z"},
            )
            if frozen_summary.get("status") != "frozen":
                raise AssertionError(f"freeze failed: {frozen_summary}")

            _expect_http_error(
                lambda: _post_json(
                    base_url + f"/api/task-specs/{draft['id']}/run-codex-managed",
                    {"executor_command": "rm -rf /"},
                ),
                expected_status=400,
            )

            job = _post_json(base_url + f"/api/task-specs/{draft['id']}/run-codex-managed", {})
            if job.get("status") not in {"queued", "preparing", "running_codex", "verifying"}:
                raise AssertionError(f"managed Codex endpoint must return running job: {job}")
            job = _wait_job_passed(base_url, job["id"])
            run_id = job.get("run_id")
            if job.get("status") != "passed" or job.get("verifier_status") != "passed":
                raise AssertionError(f"managed Codex UI job must pass verifier: {job}")
            if job.get("changed_files") != ["docs/dev_control_plane_probe.md"]:
                raise AssertionError(f"job must report fake Codex changed file: {job}")
            if job.get("original_target_unchanged") is not True:
                raise AssertionError(f"job must confirm original target unchanged: {job}")
            timeline_titles = [event.get("title") for event in job.get("timeline_events", [])]
            for expected in (
                "Готовлю managed clone...",
                "Codex выполняет задачу...",
                "Codex изменил файл: docs/dev_control_plane_probe.md",
                "Проверка прошла: git diff --check",
                "Готово: verifier passed.",
            ):
                if expected not in timeline_titles:
                    raise AssertionError(f"job timeline missing {expected}: {job.get('timeline_events')}")

            run = _get_json(base_url + f"/api/runs/{run_id}")
            if "docs/dev_control_plane_probe.md" not in run.get("diff_text", ""):
                raise AssertionError(f"run must expose diff preview: {run}")
            result_summary = run.get("run_result_summary", {})
            if result_summary.get("changed_files") != ["docs/dev_control_plane_probe.md"]:
                raise AssertionError(f"run summary must expose changed files outside raw JSON: {run}")
            if result_summary.get("original_target_unchanged") is not True:
                raise AssertionError(f"run summary must expose target unchanged state: {run}")
            for token in ("=== ДЛЯ КУРАТОРА ===", "=== СЖАТАЯ ПРОВЕРКА ==="):
                if token not in run.get("handoff_text", ""):
                    raise AssertionError(f"run must expose handoff preview token {token}: {run}")
            if "Класс задачи:" not in run.get("prompt_text", ""):
                raise AssertionError("run must expose prompt preview")
            workspace_path = Path(run["workspace_path"]).resolve()
            if workspace_path == target_repo.resolve() or _is_relative_to(workspace_path, target_repo.resolve()):
                raise AssertionError(f"workspace must not be inside original target repo: {workspace_path}")
            if _git(target_repo, "status", "--short") != original_status or _git(target_repo, "rev-parse", "HEAD") != original_head:
                raise AssertionError("original target repo mutated during managed UI run")

            cleanup = _post_json(base_url + f"/api/runs/{run_id}/cleanup", {})
            if cleanup.get("cleanup", {}).get("status") != "cleaned":
                raise AssertionError(f"cleanup must remove owned managed workspace: {cleanup}")
            if workspace_path.exists():
                raise AssertionError(f"cleanup left managed workspace behind: {workspace_path}")
            run_id = None
        finally:
            if run_id:
                try:
                    _post_json(f"http://127.0.0.1:{port}/api/runs/{run_id}/cleanup", {})
                except Exception:
                    pass
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

    print("dev-control-plane-real-codex-ui-smoke passed")


def _create_fixture_target(repo: Path) -> None:
    (repo / "docs").mkdir(parents=True)
    (repo / "README.md").write_text("# Fixture target\n", encoding="utf-8")
    (repo / "docs" / "architecture.md").write_text("Architecture fixture\n", encoding="utf-8")
    _git_checked(repo.parent, "init", str(repo))
    _git_checked(repo, "config", "user.email", "smoke@example.invalid")
    _git_checked(repo, "config", "user.name", "Smoke Test")
    _git_checked(repo, "add", ".")
    _git_checked(repo, "commit", "-m", "Initial fixture target")


def _write_target_config(config_dir: Path, repo: Path) -> None:
    config_dir.mkdir(parents=True)
    payload = {
        "project_id": "fixture-target",
        "display_name": "fixture-target",
        "repo_path": str(repo),
        "source_of_truth_paths": ["README.md", "docs/"],
        "derived_secondary_paths": ["derived_project_pack/"],
        "default_forbidden_paths": ["derived_project_pack/**", "target_project_docs_manifest.md"],
        "default_forbidden_actions": [
            "live_deploy",
            "ssh",
            "root_shell",
            "public_route_change",
            "direct_target_mutation",
            "auto_merge",
            "secrets_write",
        ],
        "default_required_smokes": ["git diff --check"],
        "codex_prompt_contract": {
            "required_headers": ["Класс задачи:", "Причина классификации:", "Режим выполнения:"],
            "final_blocks": ["=== ДЛЯ КУРАТОРА ===", "=== СЖАТАЯ ПРОВЕРКА ==="],
        },
        "control_plane_notes": ["target repo is read-only by default"],
        "product_plane_notes": ["fixture target has no product plane"],
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
    (config_dir / "fixture_target.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _task_spec(*, status: str) -> dict:
    return {
        "id": "codex-ui-smoke-task",
        "version": "1.0",
        "status": status,
        "title": "Managed Codex UI smoke",
        "goal": "Verify managed Codex UI endpoint with fake Codex binary.",
        "scope": ["Create docs/dev_control_plane_probe.md in the managed clone."],
        "not_in_scope": ["Do not mutate original target repo.", "Do not commit, push, merge, deploy, SSH, or use root."],
        "task_class": "L3",
        "class_reason": "UI starts a gated execution path in a managed clone.",
        "risks": ["Codex execution is gated and smoke uses fake binary."],
        "acceptance_criteria": ["docs/dev_control_plane_probe.md exists in managed clone", "original target repo unchanged"],
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
        "human_gates": ["operator confirms managed clone Codex UI run"],
        "target_project_id": "fixture-target",
        "sprint_steps": [
            {
                "id": "custom-ui-step",
                "sequence": 1,
                "title": "Write managed Codex UI smoke artifact",
                "goal": "Create docs/dev_control_plane_probe.md inside the managed clone.",
                "task_class": "L3",
                "scope": ["docs/dev_control_plane_probe.md"],
                "acceptance_criteria": ["docs/dev_control_plane_probe.md exists"],
                "required_smokes": ["git diff --check"],
                "stop_conditions": ["stop on forbidden path or direct target mutation"],
            }
        ],
    }


def _write_fake_codex(path: Path) -> None:
    path.write_text(
        """#!/usr/bin/env python3
from pathlib import Path
import sys

if "--version" in sys.argv:
    print("fake-codex-ui 1.0")
    raise SystemExit(0)

workspace = Path(sys.argv[sys.argv.index("--cd") + 1])
handoff = Path(sys.argv[sys.argv.index("--output-last-message") + 1])
(workspace / "docs").mkdir(parents=True, exist_ok=True)
(workspace / "docs" / "dev_control_plane_probe.md").write_text("managed Codex UI smoke\\n", encoding="utf-8")
handoff.write_text(
    "=== ДЛЯ КУРАТОРА ===\\n"
    "Статус: fake Codex UI completed\\n"
    "Что сделано: created docs/dev_control_plane_probe.md in managed clone\\n"
    "Что НЕ тронуто / что осталось вне scope: original target repo, live/deploy/SSH/root\\n"
    "\\n=== СЖАТАЯ ПРОВЕРКА ===\\n"
    "- fake Codex UI binary\\n"
    "- managed clone only\\n"
    "- verifier expected to pass\\n"
    "Главный вывод: UI managed Codex path works without real Codex.\\n",
    encoding="utf-8",
)
print("fake Codex UI done")
print('{"type":"thread.started"}')
print('{"type":"turn.started","message":"reading task"}')
print('{"type":"agent_message","message":"I will make the docs-only change."}')
print('{"type":"file_change","path":"docs/dev_control_plane_probe.md"}')
print('{"type":"command_execution","status":"completed","command":"git diff --check"}')
print('{"type":"turn.completed"}')
""",
        encoding="utf-8",
    )
    path.chmod(0o700)


def _wait_job_passed(base_url: str, job_id: str) -> dict:
    deadline = time.time() + 20
    last_job: dict | None = None
    while time.time() < deadline:
        last_job = _get_json(base_url + f"/api/real-runs/{job_id}")
        if last_job.get("status") in {"passed", "failed", "blocked"}:
            return last_job
        time.sleep(0.2)
    raise AssertionError(f"managed Codex job did not finish: {last_job}")


def _wait_ready(base_url: str) -> None:
    deadline = time.time() + 10
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            _get_json(base_url + "/api/state")
            return
        except Exception as exc:
            last_error = exc
            time.sleep(0.1)
    raise AssertionError(f"server did not become ready: {last_error}")


def _get_json(url: str) -> dict:
    return json.loads(_get_text(url))


def _get_text(url: str) -> str:
    with urllib_request.urlopen(url, timeout=10) as response:
        return response.read().decode("utf-8")


def _post_json(url: str, payload: dict) -> dict:
    body = json.dumps(payload).encode("utf-8")
    request = urllib_request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib_request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _expect_http_error(callback, expected_status: int) -> None:
    try:
        callback()
    except urllib_error.HTTPError as exc:
        if exc.code != expected_status:
            raise AssertionError(f"expected HTTP {expected_status}, got {exc.code}") from exc
        return
    raise AssertionError(f"expected HTTP {expected_status}")


def _server_env(secret_home: Path, fake_codex: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["DEV_CONTROL_PLANE_SECRET_HOME"] = str(secret_home)
    env["DEV_CONTROL_PLANE_CODEX_BIN"] = str(fake_codex)
    env.pop("OPENAI_API_KEY", None)
    env.pop("CURATOR_COCKPIT_OPENAI_MODEL", None)
    env.pop("CURATOR_COCKPIT_OPENAI_REASONING_EFFORT", None)
    return env


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise AssertionError(result.stderr or result.stdout)
    return result.stdout.strip()


def _git_checked(repo: Path, *args: str) -> None:
    _git(repo, *args)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


if __name__ == "__main__":
    main()
