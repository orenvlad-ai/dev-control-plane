"""Smoke-check task step normalization and practical safe probe drafting."""

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

from dev_control_plane.secrets import SECRET_HOME_ENV  # noqa: E402

SERVER = ROOT / "apps" / "dev_control_plane_server.py"
RUNNABLE_STEP_MESSAGE = "В карточке задачи не найден шаг запуска"


def main() -> None:
    with TemporaryDirectory(prefix="dev-control-plane-task-flow-") as tmp:
        tmp_path = Path(tmp)
        fixture_repo = tmp_path / "fixture-target"
        config_dir = tmp_path / "target-configs"
        state_dir = tmp_path / "state"
        config_dir.mkdir(parents=True)
        _create_fixture_repo(fixture_repo)
        _write_fixture_config(config_dir / "fixture.json", fixture_repo)

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
            env=_smoke_env(tmp_path / "empty-secrets"),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        created_runs: list[str] = []
        try:
            base_url = f"http://127.0.0.1:{port}"
            _wait_ready(base_url)

            no_step_spec = _base_task_spec("task-no-step", "docs/dev_control_plane_probe.md")
            no_step_spec.pop("sprint_steps", None)
            saved = _post_json(base_url + "/api/task-specs", no_step_spec)
            frozen = _post_json(base_url + f"/api/task-specs/{saved['id']}/freeze", {})
            stored = _get_json(base_url + f"/api/task-specs/{saved['id']}")
            if frozen.get("status") != "frozen" or stored.get("sprint_steps", [{}])[0].get("id") != "step-001":
                raise AssertionError(f"missing sprint_steps must normalize to step-001: {stored}")
            guided = _post_json(base_url + "/api/guided-safe-fake-run", {"task_spec_id": saved["id"]})
            created_runs.append(guided["run_id"])
            if guided.get("status") != "verifier_passed" or guided.get("step_id") != "step-001":
                raise AssertionError(f"guided flow must pass default step: {guided}")

            custom_spec = _base_task_spec("task-custom-step", "docs/custom_probe.md")
            custom_spec["sprint_steps"] = [
                {
                    "id": "custom-step-abc",
                    "sequence": 1,
                    "title": "Create custom probe doc",
                    "goal": "Create a custom probe doc in managed clone only.",
                    "task_class": "L2",
                    "scope": ["docs/custom_probe.md"],
                    "acceptance_criteria": ["Prompt can be generated for the custom step"],
                    "required_smokes": ["git diff --check"],
                    "stop_conditions": ["stop if requested work leaves docs/custom_probe.md"],
                }
            ]
            saved_custom = _post_json(base_url + "/api/task-specs", custom_spec)
            _post_json(base_url + f"/api/task-specs/{saved_custom['id']}/freeze", {})
            guided_custom = _post_json(base_url + "/api/guided-safe-fake-run", {"task_spec_id": saved_custom["id"]})
            created_runs.append(guided_custom["run_id"])
            if guided_custom.get("status") != "verifier_passed" or guided_custom.get("step_id") != "custom-step-abc":
                raise AssertionError(f"guided flow must use first custom step id: {guided_custom}")

            invalid = _base_task_spec("task-invalid-step", "docs/invalid_probe.md")
            invalid.update({"status": "frozen", "frozen_at": "2026-05-01T00:00:00Z", "spec_hash": "invalid-smoke"})
            invalid["sprint_steps"] = "not-a-list"
            _write_task_spec_state(state_dir, invalid)
            error_payload = _expect_http_error(
                lambda: _post_json(base_url + "/api/guided-safe-fake-run", {"task_spec_id": invalid["id"]}),
                expected_status=400,
            )
            if RUNNABLE_STEP_MESSAGE not in error_payload.get("error", ""):
                raise AssertionError(f"invalid runnable step must return clear blocker: {error_payload}")
            if "Сначала зафиксируйте задачу" in error_payload.get("error", ""):
                raise AssertionError(f"frozen invalid step must not be reported as missing freeze: {error_payload}")

            discussion = _post_json(base_url + "/api/discussions", {"title": "Safe probe"})
            discussion = _post_json(
                base_url + f"/api/discussions/{discussion['id']}/messages",
                {
                    "role": "operator",
                    "content": (
                        "Пробная безопасная задача для проверки real Codex lane. "
                        "В managed clone wb-core создать маленький docs-only файл docs/dev_control_plane_probe.md. "
                        "Оригинальный wb-core напрямую не менять. Не трогать runtime, deploy, public routes, "
                        "wb_core_docs_master, manifest, SellerOS/product-plane. Не делать commit, push или merge."
                    ),
                },
            )
            drafted = _post_json(
                base_url + f"/api/discussions/{discussion['id']}/draft-task-spec",
                {"mode": "fake", "target_project_id": "fixture-target"},
            )
            task_spec = drafted["task_spec"]
            allowed_paths = task_spec.get("allowed_paths", [])
            if "docs/dev_control_plane_probe.md" not in allowed_paths and "docs/" not in allowed_paths:
                raise AssertionError(f"safe probe draft must keep narrow docs path allowed: {task_spec}")
            for path in ("wb_core_docs_master/**", "99_MANIFEST__DOCSET_VERSION.md"):
                if path not in task_spec.get("forbidden_paths", []):
                    raise AssertionError(f"safe probe draft missing target forbidden path {path}: {task_spec}")
            for broad_path in ("README.md", "docs/architecture/**", "docs/modules/**", "migration/**"):
                if broad_path in task_spec.get("forbidden_paths", []):
                    raise AssertionError(f"source-of-truth path must not be automatic forbidden path {broad_path}: {task_spec}")
            gates = " ".join(task_spec.get("human_gates", [])).lower()
            for forbidden_gate in ("managed clone path", "real codex lane", "authorize real codex"):
                if forbidden_gate in gates:
                    raise AssertionError(f"safe probe draft has over-conservative gate {forbidden_gate}: {task_spec}")
            if not task_spec.get("sprint_steps"):
                raise AssertionError(f"safe probe draft must include runnable sprint step: {task_spec}")
            _post_json(base_url + f"/api/task-specs/{drafted['task_spec_id']}/freeze", {})
            guided_probe = _post_json(base_url + "/api/guided-safe-fake-run", {"task_spec_id": drafted["task_spec_id"]})
            created_runs.append(guided_probe["run_id"])
            if guided_probe.get("status") != "verifier_passed":
                raise AssertionError(f"safe probe guided fake-flow must pass: {guided_probe}")
        finally:
            for run_id in created_runs:
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

    print("dev-control-plane-task-flow-smoke passed")


def _base_task_spec(task_id: str, allowed_path: str) -> dict:
    return {
        "id": task_id,
        "version": "v1",
        "status": "draft",
        "title": "Safe docs-only probe",
        "goal": f"Create {allowed_path} in a managed clone only.",
        "scope": [allowed_path],
        "not_in_scope": ["live deploy", "direct target repo mutation", "commit/push/merge"],
        "task_class": "L2",
        "class_reason": "Bounded local-only docs probe with no live/public/runtime/deploy impact.",
        "risks": ["Task must remain in managed clone only"],
        "acceptance_criteria": ["Safe fake flow can run without real Codex"],
        "required_smokes": ["git diff --check"],
        "allowed_paths": [allowed_path],
        "forbidden_paths": ["wb_core_docs_master/**", "99_MANIFEST__DOCSET_VERSION.md"],
        "allowed_actions": ["repo_edit", "local_smoke"],
        "forbidden_actions": [
            "live_deploy",
            "ssh",
            "root_shell",
            "public_route_change",
            "selleros_product_plane_route",
            "google_sheets_gas_write",
            "secrets_write",
            "auto_merge",
            "direct_target_mutation",
            "execution_from_discussion",
        ],
        "human_gates": [],
        "frozen_at": None,
        "spec_hash": None,
    }


def _create_fixture_repo(repo: Path) -> None:
    (repo / "docs" / "architecture").mkdir(parents=True)
    (repo / "docs" / "modules").mkdir(parents=True)
    (repo / "migration").mkdir(parents=True)
    (repo / "README.md").write_text("# Fixture Target\n", encoding="utf-8")
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
        "derived_secondary_paths": ["wb_core_docs_master/"],
        "default_forbidden_paths": [
            "wb_core_docs_master/**",
            "99_MANIFEST__DOCSET_VERSION.md",
            "runtime/**",
            "deploy/**",
            "infra/**",
            "artifacts/registry_upload_http_entrypoint/**",
        ],
        "default_forbidden_actions": [
            "live_deploy",
            "ssh",
            "root_shell",
            "public_route_change",
            "selleros_product_plane_route",
            "google_sheets_gas_write",
            "secrets_write",
            "auto_merge",
            "direct_target_mutation",
        ],
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


def _write_task_spec_state(state_dir: Path, payload: dict) -> None:
    path = state_dir / "task_specs.json"
    collection = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    collection[payload["id"]] = payload
    path.write_text(json.dumps(collection, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


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
    with urllib_request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def _expect_http_error(callback, expected_status: int) -> dict:
    try:
        callback()
    except urllib_error.HTTPError as exc:
        text = exc.read().decode("utf-8")
        if exc.code != expected_status:
            raise AssertionError(f"expected HTTP {expected_status}, got {exc.code}: {text}") from exc
        return json.loads(text)
    raise AssertionError(f"expected HTTP {expected_status}")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _smoke_env(secret_home: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("OPENAI_API_KEY", None)
    env.pop("CURATOR_COCKPIT_OPENAI_MODEL", None)
    env.pop("CURATOR_COCKPIT_OPENAI_REASONING_EFFORT", None)
    env[SECRET_HOME_ENV] = str(secret_home)
    env["DEV_CONTROL_PLANE_ENABLE_FAKE_CURATOR"] = "1"
    return env


def _run_git(cwd: Path, *args: str) -> None:
    completed = subprocess.run(("git", *args), cwd=cwd, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed\nstdout={completed.stdout}\nstderr={completed.stderr}")


if __name__ == "__main__":
    main()
