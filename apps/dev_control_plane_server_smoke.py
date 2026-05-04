"""Smoke-check for the local-only development control-plane MVP server."""

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

SERVER = ROOT / "apps" / "dev_control_plane_server.py"


def main() -> None:
    port = _free_port()
    with TemporaryDirectory(prefix="dev-control-plane-server-smoke-") as tmp:
        state_dir = Path(tmp) / "state"
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
            ],
            cwd=ROOT,
            env=_server_smoke_env(Path(tmp) / "empty-secrets"),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        created_run_id = None
        try:
            base_url = f"http://127.0.0.1:{port}"
            _wait_ready(base_url)

            html = _get_text(base_url + "/")
            if "Development Control Plane" not in html or "Local-only Development Control Plane prototype" not in html:
                raise AssertionError("root route must return cockpit HTML with local-only notice")
            for token in (
                "Чат",
                "Подключения",
                "Технические детали",
                "Опиши задачу",
                "Отправить",
                "Подготовить задачу",
                "Карточка задачи",
                "Результат выполнения",
                "Изменённые файлы",
                "Показать diff",
                "Показать handoff",
                "Дополнительные действия",
                "Сформировать карточку вручную",
                "Зафиксировать вручную",
                "Тестовый прогон без Codex",
                "Запустить Codex безопасно",
                "Ход выполнения",
                "Готовлю managed clone",
                "Codex выполняет задачу",
                "Проверяю результат",
                "managed clone",
                "Куратор думает",
                "Формирую карточку",
                "Фиксирую задачу",
                "Проверяю сценарий",
                "Проверяю OpenAI",
                "OpenAI-куратор",
                "Codex CLI",
            ):
                if token not in html:
                    raise AssertionError(f"root route must expose Russian chat-first UI token: {token}")
            for token in ("max-height: 400px", "overflow-y: auto"):
                if token not in html:
                    raise AssertionError(f"timeline must be fixed-height scrollable: {token}")
            if "Fake curator" in html:
                raise AssertionError("operator UI must not expose fake curator selector")

            state = _get_json(base_url + "/api/state")
            if state.get("host") != "127.0.0.1" or state.get("local_only") is not True:
                raise AssertionError(f"server must report local-only 127.0.0.1 binding: {state}")
            for route in state.get("exposed_routes", []):
                if "deploy" in route.lower() or "live" in route.lower():
                    raise AssertionError(f"server must not expose live/deploy route: {route}")
            if state.get("live_deploy_enabled") is not False or state.get("public_routes_enabled") is not False:
                raise AssertionError(f"live/public flags must stay false: {state}")
            if state.get("fake_executor_enabled") is not True or state.get("real_executor_enabled") is not True:
                raise AssertionError(f"server must expose fake and gated real executor state: {state}")
            if state.get("real_codex_ui_enabled") is not True or state.get("real_codex_ui_mode") != "managed_clone_only":
                raise AssertionError(f"server must expose managed-clone real Codex UI mode: {state}")
            if state.get("ai_curator_enabled") is not True or state.get("openai_curator_optional") is not True:
                raise AssertionError(f"server must expose optional AI curator state: {state}")
            if state.get("target_project_count", 0) < 1:
                raise AssertionError(f"server must expose configured target projects: {state}")

            connections = _get_json(base_url + "/api/connections/status")
            serialized_connections = json.dumps(connections, ensure_ascii=False)
            if "OPENAI_API_KEY" in serialized_connections:
                raise AssertionError(f"connections status must not expose API key field names or values: {connections}")
            if connections.get("openai", {}).get("configured") is not False:
                raise AssertionError(f"OpenAI should be disconnected in smoke env: {connections}")
            if connections.get("openai", {}).get("source") != "missing":
                raise AssertionError(f"OpenAI source should be missing without env key: {connections}")
            if "installed" not in connections.get("codex", {}) or "version" not in connections.get("codex", {}):
                raise AssertionError(f"Codex status must include installed/version fields: {connections}")
            control = connections.get("control_plane", {})
            if control.get("local_only") is not True or control.get("public_routes_enabled") is not False:
                raise AssertionError(f"connections control-plane status must stay local-only: {connections}")
            if control.get("real_codex_ui_enabled") is not True or control.get("real_codex_ui_mode") != "managed_clone_only":
                raise AssertionError(f"real Codex UI must stay managed-clone only: {connections}")

            targets = _get_json(base_url + "/api/target-projects")
            target_ids = [target.get("project_id") for target in targets.get("targets", [])]
            if "wb-core" not in target_ids:
                raise AssertionError(f"server target list must include wb-core config: {targets}")
            wb_target = _get_json(base_url + "/api/target-projects/wb-core")
            if wb_target.get("target", {}).get("target_readonly_by_default") is not True:
                raise AssertionError(f"wb-core target must be read-only by default: {wb_target}")

            discussion = _post_json(base_url + "/api/discussions", {"title": "Smoke discussion"})
            discussion_id = discussion["id"]
            discussion = _post_json(
                base_url + f"/api/discussions/{discussion_id}/messages",
                {"role": "operator", "content": "Prepare a local repo-only task."},
            )
            messages = discussion.get("messages", [])
            if len(messages) != 2 or messages[1].get("role") != "curator":
                raise AssertionError(f"operator message must append curator response: {messages}")
            if "OpenAI-куратор не подключён" not in messages[1].get("content", ""):
                raise AssertionError(f"missing OpenAI key must be shown as clean curator message: {messages}")

            openai_draft_blocker = _post_json(
                base_url + f"/api/discussions/{discussion_id}/draft-task-spec",
                {},
            )
            if openai_draft_blocker.get("status") != "blocked" or openai_draft_blocker.get("blocked_reason") != "OPENAI_API_KEY missing":
                raise AssertionError(f"draft without OpenAI key must fail closed cleanly: {openai_draft_blocker}")

            draft_summary = _post_json(
                base_url + f"/api/discussions/{discussion_id}/draft-task-spec",
                {"mode": "fake"},
            )
            if draft_summary.get("status") != "drafted" or draft_summary.get("provider") != "fake":
                raise AssertionError(f"fake curator must draft valid task spec: {draft_summary}")
            task_spec_id = draft_summary["task_spec_id"]
            draft = _get_json(base_url + f"/api/task-specs/{task_spec_id}")
            for path in ("derived_project_pack/**", "target_project_docs_manifest.md"):
                if path not in draft.get("forbidden_paths", []):
                    raise AssertionError(f"draft must preserve forbidden path: {path}")
            for action in ("live_deploy", "ssh", "root_shell", "public_route_change"):
                if action not in draft.get("forbidden_actions", []):
                    raise AssertionError(f"draft must preserve forbidden action: {action}")

            _expect_http_error(
                lambda: _post_json(base_url + f"/api/task-specs/{task_spec_id}/generate-prompt", {"step_id": "step-001"}),
                expected_status=400,
            )
            _expect_http_error(
                lambda: _post_json(base_url + f"/api/task-specs/{task_spec_id}/prepare-run", {"step_id": "step-001"}),
                expected_status=400,
            )
            _expect_http_error(
                lambda: _post_json(base_url + f"/api/task-specs/{task_spec_id}/run-fake", {"step_id": "step-001"}),
                expected_status=400,
            )
            _expect_http_error(
                lambda: _post_json(base_url + "/api/guided-safe-fake-run", {"task_spec_id": task_spec_id, "step_id": "step-001"}),
                expected_status=400,
            )

            frozen_summary = _post_json(
                base_url + f"/api/task-specs/{task_spec_id}/freeze",
                {"frozen_at": "2026-05-01T00:00:00Z"},
            )
            if frozen_summary.get("status") != "frozen" or not frozen_summary.get("spec_hash"):
                raise AssertionError(f"freeze must return frozen spec hash: {frozen_summary}")

            frozen = _get_json(base_url + f"/api/task-specs/{task_spec_id}")
            if frozen.get("status") != "frozen":
                raise AssertionError(f"stored task spec must be frozen: {frozen}")
            if not frozen.get("sprint_steps"):
                raise AssertionError("stored task spec must keep sprint steps")

            prompt_summary = _post_json(
                base_url + f"/api/task-specs/{task_spec_id}/generate-prompt",
                {"step_id": "step-001"},
            )
            if not prompt_summary.get("mandatory_blocks_present"):
                raise AssertionError(f"prompt summary must confirm mandatory blocks: {prompt_summary}")

            prompt = _get_text(base_url + f"/api/prompts/{prompt_summary['id']}")
            for token in (
                "Класс задачи:",
                "Причина классификации:",
                "Режим выполнения:",
                "=== ДЛЯ КУРАТОРА ===",
                "=== СЖАТАЯ ПРОВЕРКА ===",
            ):
                if token not in prompt:
                    raise AssertionError(f"generated prompt missing token: {token}")

            prepared = _post_json(
                base_url + f"/api/task-specs/{task_spec_id}/prepare-run",
                {"step_id": "step-001"},
            )
            if prepared.get("status") != "prepared" or prepared.get("verifier_status") is not None:
                raise AssertionError(f"prepare-run must only prepare local artifacts: {prepared}")
            prepared_run = _get_json(base_url + f"/api/runs/{prepared['run_id']}")
            if "Класс задачи:" not in prepared_run.get("prompt_text", ""):
                raise AssertionError(f"prepared run must expose prompt preview: {prepared_run}")
            if prepared_run.get("handoff_text") is not None:
                raise AssertionError(f"prepared run must not have handoff yet: {prepared_run}")

            fake_run = _post_json(
                base_url + f"/api/task-specs/{task_spec_id}/run-fake",
                {"step_id": "step-001"},
            )
            created_run_id = fake_run["run_id"]
            if fake_run.get("status") != "verifier_passed" or fake_run.get("verifier_status") != "passed":
                raise AssertionError(f"run-fake must pass verifier: {fake_run}")
            if fake_run.get("mandatory_handoff_blocks_present") is not True:
                raise AssertionError(f"run-fake must report mandatory handoff blocks: {fake_run}")
            worktree_path = Path(fake_run["worktree_path"]).resolve()
            if worktree_path == ROOT.resolve() or not _is_relative_to(worktree_path, state_dir.resolve()):
                raise AssertionError(f"run-fake must use isolated smoke worktree: {worktree_path}")

            run = _get_json(base_url + f"/api/runs/{created_run_id}")
            for token in ("=== ДЛЯ КУРАТОРА ===", "=== СЖАТАЯ ПРОВЕРКА ==="):
                if token not in run.get("handoff_text", ""):
                    raise AssertionError(f"run handoff missing token: {token}")
            if "Класс задачи:" not in run.get("prompt_text", ""):
                raise AssertionError("run prompt preview must include classification header")

            verified = _post_json(base_url + f"/api/runs/{created_run_id}/verify", {})
            if verified.get("verifier_status") != "passed":
                raise AssertionError(f"verify-run endpoint must pass: {verified}")

            cleanup = _post_json(base_url + f"/api/runs/{created_run_id}/cleanup", {})
            if cleanup.get("cleanup", {}).get("status") != "cleaned":
                raise AssertionError(f"cleanup endpoint must clean owned worktree: {cleanup}")
            if worktree_path.exists():
                raise AssertionError(f"cleanup must remove owned worktree: {worktree_path}")
            if _branch_exists(str(fake_run["branch_name"])):
                raise AssertionError(f"cleanup must remove owned test branch: {fake_run['branch_name']}")
            created_run_id = None

            guided = _post_json(
                base_url + "/api/guided-safe-fake-run",
                {"task_spec_id": task_spec_id, "step_id": "step-001"},
            )
            created_run_id = guided["run_id"]
            if guided.get("status") != "verifier_passed" or guided.get("verifier_status") != "passed":
                raise AssertionError(f"guided safe fake flow must pass verifier: {guided}")
            guided_run = _get_json(base_url + f"/api/runs/{created_run_id}")
            if not guided_run.get("prompt_text") or not guided_run.get("handoff_text"):
                raise AssertionError(f"guided run must expose prompt and handoff: {guided_run}")
            _post_json(base_url + f"/api/runs/{created_run_id}/cleanup", {})
            if _branch_exists(str(guided_run["branch_name"])):
                raise AssertionError(f"guided cleanup must remove owned test branch: {guided_run['branch_name']}")
            created_run_id = None

            _expect_http_error(lambda: _get_json(base_url + "/api/live-deploy"), expected_status=404)
            _expect_http_error(lambda: _get_json(base_url + "/deploy"), expected_status=404)
        finally:
            if created_run_id:
                try:
                    _post_json(base_url + f"/api/runs/{created_run_id}/cleanup", {})
                except Exception:
                    pass
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

    print("dev-control-plane-mvp-server-smoke passed")


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


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _branch_exists(branch_name: str) -> bool:
    completed = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", branch_name],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode == 0


def _server_smoke_env(secret_home: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("OPENAI_API_KEY", None)
    env.pop("CURATOR_COCKPIT_OPENAI_MODEL", None)
    env["DEV_CONTROL_PLANE_SECRET_HOME"] = str(secret_home)
    env["DEV_CONTROL_PLANE_ENABLE_FAKE_CURATOR"] = "1"
    return env


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


if __name__ == "__main__":
    main()
