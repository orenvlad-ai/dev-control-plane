"""Practical target-aware cockpit smoke-check."""

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
SRC = ROOT / "src"
for path in (SRC, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dev_control_plane.target_projects import load_target_project_config, validate_target_project  # noqa: E402

SERVER = ROOT / "apps" / "dev_control_plane_server.py"
WB_CORE_CONFIG = ROOT / "configs" / "target_projects" / "wb_core.json"


def main() -> None:
    with TemporaryDirectory(prefix="dev-control-plane-practical-cockpit-") as tmp:
        tmp_path = Path(tmp)
        fixture_repo = tmp_path / "fixture-target"
        config_dir = tmp_path / "target-configs"
        state_dir = tmp_path / "state"
        config_dir.mkdir(parents=True)
        fixture_config = config_dir / "fixture.json"

        _create_fixture_repo(fixture_repo)
        _write_fixture_config(fixture_config, fixture_repo)
        before_fixture_status = _git_text(fixture_repo, "status", "--short")
        before_wb_status = _wb_core_status()

        port = _free_port()
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
            env=_smoke_env_without_openai(tmp_path / "empty-secrets"),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        created_run_id = None
        try:
            base_url = f"http://127.0.0.1:{port}"
            _wait_ready(base_url)

            html = _get_text(base_url + "/")
            for token in (
                "Чат",
                "Подключения",
                "Технические детали",
                "Карточка задачи",
                "Блокер",
                "Сформировать карточку задачи",
                "Безопасно проверить сценарий",
                "Запустить Codex безопасно",
                "managed clone",
                "Куратор думает",
                "Формирую карточку",
                "Фиксирую задачу",
                "Проверяю сценарий",
                "Проверяю OpenAI",
                "Технические детали (Advanced)",
            ):
                if token not in html:
                    raise AssertionError(f"cockpit HTML missing practical marker: {token}")
            if "Fake curator" in html:
                raise AssertionError("operator UI must not expose fake curator selector")

            state = _get_json(base_url + "/api/state")
            if state.get("target_config_dir") != str(config_dir):
                raise AssertionError(f"server must use temp target config dir: {state}")

            targets = _get_json(base_url + "/api/targets")
            if [target.get("project_id") for target in targets.get("targets", [])] != ["fixture-target"]:
                raise AssertionError(f"target list must expose fixture target only: {targets}")

            target = _get_json(base_url + "/api/targets/fixture-target/summary")
            summary = target.get("summary", {})
            if summary.get("validation_status") != "valid":
                raise AssertionError(f"fixture target summary must be valid: {target}")
            for key in ("source_of_truth_paths_found", "default_forbidden_paths", "default_forbidden_actions"):
                if not summary.get(key):
                    raise AssertionError(f"target summary missing {key}: {summary}")

            discussion = _post_json(base_url + "/api/discussions", {"title": "Practical smoke"})
            discussion_id = discussion["id"]
            _post_json(
                base_url + f"/api/discussions/{discussion_id}/messages",
                {"role": "operator", "content": "Add a bounded docs-only improvement for the target project."},
            )

            openai_blocked = _post_json(
                base_url + f"/api/discussions/{discussion_id}/draft-task-spec",
                {"mode": "openai", "target_project_id": "fixture-target"},
            )
            if openai_blocked.get("status") != "blocked" or openai_blocked.get("blocked_reason") != "OPENAI_API_KEY missing":
                raise AssertionError(f"OpenAI mode without key must fail closed: {openai_blocked}")

            draft_summary = _post_json(
                base_url + f"/api/discussions/{discussion_id}/draft-task-spec",
                {"mode": "fake", "target_project_id": "fixture-target"},
            )
            if draft_summary.get("status") != "drafted":
                raise AssertionError(f"fake target-aware draft must succeed: {draft_summary}")
            task_spec = draft_summary["task_spec"]
            task_spec_id = draft_summary["task_spec_id"]
            if task_spec.get("target_project_id") != "fixture-target":
                raise AssertionError(f"draft must retain target project id: {task_spec}")
            for path in ("derived_project_pack/**", "target_project_docs_manifest.md"):
                if path not in task_spec.get("forbidden_paths", []):
                    raise AssertionError(f"draft missing target forbidden path: {path}")
            for action in ("live_deploy", "ssh", "root_shell", "public_route_change"):
                if action not in task_spec.get("forbidden_actions", []):
                    raise AssertionError(f"draft missing target forbidden action: {action}")
            if "git diff --check" not in task_spec.get("required_smokes", []):
                raise AssertionError("draft missing target required smoke")
            if not task_spec.get("target_context_summary"):
                raise AssertionError("draft must carry compact target context summary")
            if draft_summary.get("task_card", {}).get("next_recommended_action") != "Freeze Task":
                raise AssertionError(f"draft response must include task card next action: {draft_summary}")

            frozen = _post_json(
                base_url + f"/api/task-specs/{task_spec_id}/freeze",
                {"frozen_at": "2026-05-01T00:00:00Z"},
            )
            if frozen.get("status") != "frozen":
                raise AssertionError(f"freeze must pass: {frozen}")
            stored = _get_json(base_url + f"/api/task-specs/{task_spec_id}")
            if stored.get("target_project_id") != "fixture-target":
                raise AssertionError(f"frozen spec must preserve target project id: {stored}")

            guided = _post_json(
                base_url + "/api/guided-safe-fake-run",
                {"task_spec_id": task_spec_id, "step_id": "step-001"},
            )
            created_run_id = guided["run_id"]
            if guided.get("status") != "verifier_passed" or guided.get("verifier_status") != "passed":
                raise AssertionError(f"guided fake flow must pass verifier: {guided}")
            if guided.get("target_project_id") != "fixture-target":
                raise AssertionError(f"guided summary must include target project id: {guided}")
            result_summary = guided.get("run_result_summary", {})
            if result_summary.get("status") != "Passed" or result_summary.get("target_project_id") != "fixture-target":
                raise AssertionError(f"guided result summary must be operator-readable: {guided}")

            run = _get_json(base_url + f"/api/runs/{created_run_id}")
            if run.get("run_result_summary", {}).get("status") != "Passed":
                raise AssertionError(f"GET run must include compact passed summary: {run}")
            if run.get("blocker", {}).get("status") != "none":
                raise AssertionError(f"passed run must show no blocker: {run.get('blocker')}")
            if not run.get("prompt_text") or not run.get("handoff_text"):
                raise AssertionError("run must expose prompt/handoff previews for advanced details")

            run_summary = _get_json(base_url + f"/api/runs/{created_run_id}/summary")
            if run_summary.get("status") != "Passed" or run_summary.get("prompt_available") is not True:
                raise AssertionError(f"run summary endpoint must be compact: {run_summary}")

            cleanup = _post_json(base_url + f"/api/runs/{created_run_id}/cleanup", {})
            if cleanup.get("cleanup", {}).get("status") != "cleaned":
                raise AssertionError(f"cleanup must remove owned worktree: {cleanup}")
            created_run_id = None
        finally:
            if created_run_id:
                try:
                    _post_json(f"http://127.0.0.1:{port}/api/runs/{created_run_id}/cleanup", {})
                except Exception:
                    pass
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

        if before_fixture_status != _git_text(fixture_repo, "status", "--short"):
            raise AssertionError("fixture target repo must remain unchanged")
        _verify_wb_core_read_only(before_wb_status)

    print("dev-control-plane-practical-cockpit-smoke passed")


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
        "source_of_truth_paths": ["README.md", "docs/architecture/", "docs/modules/", "migration/"],
        "derived_secondary_paths": ["derived_project_pack/"],
        "default_forbidden_paths": ["derived_project_pack/**", "target_project_docs_manifest.md"],
        "default_forbidden_actions": ["live_deploy", "ssh", "root_shell", "public_route_change"],
        "default_required_smokes": ["git diff --check"],
        "codex_prompt_contract": {
            "required_headers": ["Класс задачи:", "Причина классификации:", "Режим выполнения:"],
            "final_blocks": ["=== ДЛЯ КУРАТОРА ===", "=== СЖАТАЯ ПРОВЕРКА ==="],
        },
        "control_plane_notes": ["current ChatGPT Project workflow remains canonical until explicit cutover"],
        "product_plane_notes": ["fixture product-plane is not controlled by this cockpit"],
        "target_readonly_by_default": True,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _wb_core_status() -> str | None:
    config = load_target_project_config(WB_CORE_CONFIG)
    repo = Path(config.repo_path)
    if not repo.exists():
        return None
    return _git_text(repo, "status", "--short")


def _verify_wb_core_read_only(before_status: str | None) -> None:
    config = load_target_project_config(WB_CORE_CONFIG)
    repo = Path(config.repo_path)
    if not repo.exists():
        print("wb-core target path missing; real read-only validation skipped")
        return
    result = validate_target_project(config)
    if result.status == "blocked":
        raise AssertionError(f"wb-core target validation blocked: {result}")
    after_status = _git_text(repo, "status", "--short")
    if before_status != after_status:
        raise AssertionError("wb-core status changed during practical cockpit smoke")


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
    try:
        with urllib_request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib_error.HTTPError as exc:
        text = exc.read().decode("utf-8")
        raise AssertionError(f"HTTP {exc.code}: {text}") from exc


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _smoke_env_without_openai(secret_home: Path) -> dict[str, str]:
    env = dict(os.environ)
    for key in ("OPENAI_API_KEY", "CURATOR_COCKPIT_OPENAI_MODEL", "CURATOR_COCKPIT_OPENAI_TIMEOUT_SECONDS"):
        env.pop(key, None)
    env["DEV_CONTROL_PLANE_SECRET_HOME"] = str(secret_home)
    env["DEV_CONTROL_PLANE_ENABLE_FAKE_CURATOR"] = "1"
    return env


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
