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
            if "Development Control Plane" not in html or "Панель" not in html:
                raise AssertionError("root route must return unified dashboard HTML")
            for token in (
                "Панель",
                "Подключение",
                "Мониторинг",
                "Технические детали",
                "Сервис DevControl",
                "MCP auth/tools",
                "GitHub-доступ",
                "SSH-деплой",
                "Активные запуски",
                "wb-core production lock",
                "Parallel task ledger",
                "frozen_base_stale / refresh_required",
                "Promote next dry",
                "Настройки куратора",
                "Curator model",
                "Curator reasoning",
                "Настройки Codex",
                "Codex model",
                "Codex reasoning",
                "Сохранить",
                "Codex CLI",
                "Технические детали / Advanced",
                "Sanitized diagnostics",
                "Browser command input отсутствует",
            ):
                if token not in html:
                    raise AssertionError(f"root route must expose dashboard UI token: {token}")
            for token in ("Опиши задачу", "Куратор думает", "OpenAI curator model", "openaiModelInput", "Проверяю OpenAI", "Fake curator"):
                if token in html:
                    raise AssertionError(f"primary dashboard must hide legacy chat/OpenAI control token: {token}")

            state = _get_json(base_url + "/api/state")
            if state.get("host") != "127.0.0.1" or state.get("local_only") is not True:
                raise AssertionError(f"server must report local-only 127.0.0.1 binding: {state}")
            allowed_live_monitor_routes = {
                "GET /runs/live",
                "GET /runs/{run_id}/watch",
                "GET /api/runs/live",
                "GET /api/runs/stream",
                "GET /api/runs/{id}/live",
                "GET /api/runs/{id}/timeline",
                "GET /api/runs/{id}/log-tail",
                "GET /api/runs/{id}/stream",
            }
            for route in state.get("exposed_routes", []):
                if "deploy" in route.lower() or ("live" in route.lower() and route not in allowed_live_monitor_routes):
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

            runtime_config = _get_json(base_url + "/api/runtime-config")
            if runtime_config.get("openai", {}).get("model") != "gpt-5.5":
                raise AssertionError(f"runtime config must expose default OpenAI model: {runtime_config}")
            saved_runtime = _post_json(
                base_url + "/api/runtime-config",
                {
                    "profile": "fast",
                    "openai": {"model": "gpt-5.4", "reasoning_effort": "high"},
                    "codex": {
                        "model": "gpt-5.4",
                        "reasoning_effort": "high",
                        "sandbox_mode": "workspace-write",
                    },
                },
            )
            if (
                saved_runtime.get("openai", {}).get("model") != "gpt-5.4"
                or saved_runtime.get("openai", {}).get("reasoning_effort") != "high"
                or saved_runtime.get("codex", {}).get("model") != "gpt-5.4"
                or saved_runtime.get("codex", {}).get("reasoning_effort") != "high"
                or saved_runtime.get("codex", {}).get("sandbox_mode") != "workspace-write"
            ):
                raise AssertionError(f"runtime config save must preserve explicit settings and ignore profile: {saved_runtime}")
            if "profiles" in saved_runtime.get("options", {}):
                raise AssertionError(f"runtime config must not expose deprecated profiles: {saved_runtime}")
            _expect_http_error(
                lambda: _post_json(base_url + "/api/runtime-config", {"openai": {"model": "not-a-real-model"}}),
                expected_status=400,
            )
            runtime_connections = _get_json(base_url + "/api/connections/status")
            if runtime_connections.get("runtime_config", {}).get("openai", {}).get("model") != "gpt-5.4":
                raise AssertionError(f"connections status must include runtime model config: {runtime_connections}")
            if runtime_connections.get("runtime_config", {}).get("openai", {}).get("reasoning_effort") != "high":
                raise AssertionError(f"connections status must include runtime reasoning config: {runtime_connections}")
            toolchain = runtime_connections.get("toolchain", {})
            if "tools" not in toolchain or "missing_required" not in toolchain:
                raise AssertionError(f"connections status must include sanitized toolchain diagnostics: {runtime_connections}")
            toolchain_status = _get_json(base_url + "/api/toolchain/status")
            if "tools" not in toolchain_status or "path" not in toolchain_status:
                raise AssertionError(f"toolchain endpoint must expose capability matrix: {toolchain_status}")
            serialized_runtime = json.dumps(runtime_connections, ensure_ascii=False)
            for secret_marker in ("OPENAI_API_KEY", "Bearer ", "auth.json", "sk-test"):
                if secret_marker in serialized_runtime:
                    raise AssertionError(f"runtime status leaked secret marker {secret_marker}: {runtime_connections}")

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

            async_discussion = _post_json(base_url + "/api/discussions", {"title": "Hosted card prepare flow smoke"})
            async_discussion = _post_json(
                base_url + f"/api/discussions/{async_discussion['id']}/messages",
                {
                    "role": "operator",
                    "content": "Найди в UI место, где отображается название вкладки/раздела «Витрина», и замени видимый текст на «Витрина 2».",
                },
            )
            async_job = _post_json(
                base_url + f"/api/discussions/{async_discussion['id']}/draft-task-spec-jobs",
                {"mode": "fake", "target_project_id": "wb-core"},
            )
            async_result = _wait_draft_job(base_url, async_job["id"])
            if async_result.get("status") != "drafted":
                raise AssertionError(f"async hosted card prepare flow must draft valid task spec: {async_result}")
            if async_result.get("task_spec", {}).get("target_project_id") != "wb-core":
                raise AssertionError(f"async hosted card prepare flow must preserve target project: {async_result}")

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


def _wait_draft_job(base_url: str, job_id: str) -> dict:
    deadline = time.time() + 10
    while time.time() < deadline:
        job = _get_json(base_url + f"/api/draft-task-spec-jobs/{job_id}")
        if job.get("status") in {"drafted", "blocked", "failed"}:
            return job.get("result") or job
        time.sleep(0.05)
    raise AssertionError(f"draft task card job did not finish: {_get_json(base_url + f'/api/draft-task-spec-jobs/{job_id}')}")


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
    env.pop("CURATOR_COCKPIT_OPENAI_REASONING_EFFORT", None)
    env.pop("DEV_CONTROL_PLANE_OPENAI_TIMEOUT_SECONDS", None)
    env.pop("DEV_CONTROL_PLANE_OPENAI_RETRY_COUNT", None)
    env.pop("DEV_CONTROL_PLANE_OPENAI_RETRY_BACKOFF_SECONDS", None)
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
