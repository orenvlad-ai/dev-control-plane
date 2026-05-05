"""Smoke-check explicit wb-core production lane gates and dry-run plan."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import time
from tempfile import TemporaryDirectory
from typing import Any, Mapping
from urllib import request as urllib_request

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (SRC, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dev_control_plane.target_production import (  # noqa: E402
    acquire_wb_core_production_lock,
    build_wb_core_production_plan,
    execute_wb_core_production_lane,
    inspect_wb_core_production_lock,
    release_wb_core_production_lock,
)

RUNNER = ROOT / "apps" / "dev_control_plane_runner.py"
SERVER = ROOT / "apps" / "dev_control_plane_server.py"
TEMPLATE_PATH = "packages/adapters/templates/sheet_vitrina_v1_web_vitrina.html"


def main() -> None:
    with TemporaryDirectory(prefix="dev-control-plane-target-production-") as tmp_raw:
        tmp = Path(tmp_raw)
        workspace = tmp / "state" / "workspaces" / "run-prod-smoke" / "wb-core"
        run_dir = tmp / "state" / "runs" / "run-prod-smoke"
        _create_workspace(workspace)
        payload = _clean_payload(workspace, run_dir)

        plan = build_wb_core_production_plan(payload)
        if not plan.allowed:
            raise AssertionError(f"clean production lane plan must be allowed: {plan}")
        if plan.plan.get("branch_name", "").startswith("devcp/") is False:
            raise AssertionError(f"branch must use devcp prefix: {plan}")
        if plan.plan.get("rollback_plan", {}).get("commands") is None:
            raise AssertionError(f"rollback plan is required: {plan}")
        if not plan.plan.get("target_rules", {}).get("rules_loaded_into_context"):
            raise AssertionError(f"target rules must be loaded: {plan}")
        if plan.plan.get("execution_mode") != "production_lane" or plan.plan.get("apply_mode") != "target_pr_merge_deploy":
            raise AssertionError(f"production lane mode must be explicit: {plan}")
        if plan.plan.get("lock", {}).get("status") != "free":
            raise AssertionError(f"clean plan must expose free target lock: {plan}")
        if "deploy --dry-run" not in "\n".join(plan.plan.get("deploy_commands", [])):
            raise AssertionError(f"deploy dry-run must be part of plan: {plan}")
        if "wb-core PR" not in plan.plan.get("pr_title", ""):
            raise AssertionError(f"PR title must be Russian and task-specific: {plan}")

        dry_run = execute_wb_core_production_lane(payload, execute=False)
        if dry_run.status != "dry_run_ready" or not dry_run.rollback_plan_path:
            raise AssertionError(f"dry-run production lane must not mutate but must write rollback plan: {dry_run}")
        if "gh" not in json.dumps(dry_run.plan.get("execution_commands", []), ensure_ascii=False):
            raise AssertionError(f"dry-run must expose target PR commands: {dry_run}")
        if inspect_wb_core_production_lock(workspace_path=workspace, run_dir=run_dir, run_id=payload["run_id"])["status"] != "free":
            raise AssertionError("dry-run must not acquire production target lock")

        _assert_denied({**payload, "verifier_status": "failed"}, "verifier")
        _assert_denied({**payload, "changed_files": ["runtime/unsafe.py"]}, "protected/forbidden")
        _assert_denied({**payload, "secrets_scan_status": "failed"}, "secrets")
        _assert_denied({**payload, "push_to_main": True}, "direct push")
        _assert_denied({**payload, "commit_message": "DevControl change"}, "Russian")
        _assert_denied({**payload, "execution_mode": "managed_clone_only"}, "production-lane endpoint")
        _assert_denied({**payload, "production_lane": False}, "production_lane flag")

        lock = acquire_wb_core_production_lock(workspace_path=workspace, run_dir=run_dir, run_id="active-smoke")
        try:
            locked = build_wb_core_production_plan(payload)
            if locked.allowed or not any("locked by active run" in blocker for blocker in locked.blockers):
                raise AssertionError(f"active target lock must block production lane: {locked}")
        finally:
            release_wb_core_production_lock(lock)
        if inspect_wb_core_production_lock(workspace_path=workspace, run_dir=run_dir, run_id=payload["run_id"])["status"] != "free":
            raise AssertionError("target lock must be released after success/fail path")

        missing_docs = tmp / "state" / "workspaces" / "run-missing-docs" / "wb-core"
        _create_workspace(missing_docs, docs=False)
        _assert_denied({**payload, "workspace_path": str(missing_docs)}, "target rules")

        payload_path = tmp / "payload.json"
        _write_json(payload_path, payload)
        runner_plan = _run_json([sys.executable, str(RUNNER), "target-production-plan", "--input", str(payload_path)])
        if runner_plan.get("status") != "allowed":
            raise AssertionError(f"runner production plan must use helper: {runner_plan}")
        runner_dry = _run_json([sys.executable, str(RUNNER), "target-production-run", "--input", str(payload_path)])
        if runner_dry.get("status") != "dry_run_ready":
            raise AssertionError(f"runner dry-run must not execute mutation: {runner_dry}")

        server = subprocess.Popen(
            [
                sys.executable,
                str(SERVER),
                "--host",
                "127.0.0.1",
                "--port",
                "0",
                "--state-dir",
                str(tmp / "server-state"),
            ],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            started = json.loads(server.stdout.readline())
            base_url = f"http://127.0.0.1:{started['port']}"
            _wait_ready(base_url)
            state = _get_json(base_url + "/api/state")
            if state.get("target_production_lane_enabled") is not True:
                raise AssertionError(f"server must expose production lane policy: {state}")
            server_plan = _post_json(base_url + "/api/target-production/plan", payload)
            if server_plan.get("status") != "allowed":
                raise AssertionError(f"server production endpoint must use helper: {server_plan}")
        finally:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()

    print("dev-control-plane-target-production-smoke passed")


def _clean_payload(workspace: Path, run_dir: Path) -> dict[str, Any]:
    return {
        "target_project_id": "wb-core",
        "target_repo": "orenvlad-ai/wb-core",
        "target_repo_url": "https://github.com/orenvlad-ai/wb-core.git",
        "base_branch": "main",
        "run_id": "run-prod-smoke",
        "run_dir": str(run_dir),
        "workspace_path": str(workspace),
        "task_spec_id": "task-prod-smoke",
        "task_summary": "Микрозадача: заменить видимый label «Витрина» на «Витрина 2».",
        "changed_files": [TEMPLATE_PATH],
        "verifier_status": "passed",
        "forbidden_path_hits": [],
        "secrets_scan_status": "passed",
        "docs_update_status": "not_required",
        "expected_public_label": "Витрина 2",
        "commit_message": "Изменить label Витрина через DevControl (run-prod-smoke)",
        "pr_title": "Изменить wb-core PR label Витрина через DevControl",
    }


def _create_workspace(workspace: Path, *, docs: bool = True) -> None:
    (workspace / "packages" / "adapters" / "templates").mkdir(parents=True)
    (workspace / TEMPLATE_PATH).write_text("<button>Витрина 2</button>\n", encoding="utf-8")
    (workspace / "README.md").write_text("# wb-core fixture\n", encoding="utf-8")
    if docs:
        (workspace / "docs" / "architecture").mkdir(parents=True)
        (workspace / "docs" / "architecture" / "01.md").write_text("architecture\n", encoding="utf-8")
        (workspace / "docs" / "modules").mkdir(parents=True)
        (workspace / "docs" / "modules" / "01.md").write_text("module\n", encoding="utf-8")
        (workspace / "migration").mkdir(parents=True)
        (workspace / "migration" / "README.md").write_text("migration\n", encoding="utf-8")
    runner = workspace / "apps" / "registry_upload_http_entrypoint_hosted_runtime.py"
    runner.parent.mkdir(parents=True)
    runner.write_text("# deploy runner fixture\n", encoding="utf-8")
    target = workspace / "artifacts" / "registry_upload_http_entrypoint" / "input" / "hosted_runtime_target__europe_api.json"
    target.parent.mkdir(parents=True)
    target.write_text("{}\n", encoding="utf-8")
    _git(workspace.parent, "init", str(workspace))
    _git(workspace, "config", "user.email", "smoke@example.invalid")
    _git(workspace, "config", "user.name", "Smoke Test")
    _git(workspace, "add", ".")
    _git(workspace, "commit", "-m", "Initial fixture")
    (workspace / TEMPLATE_PATH).write_text("<button>Витрина 2</button>\n", encoding="utf-8")


def _assert_denied(payload: Mapping[str, Any], token: str) -> None:
    decision = build_wb_core_production_plan(payload)
    if decision.allowed or not any(token in blocker for blocker in decision.blockers):
        raise AssertionError(f"production lane must be denied by {token}: {decision}")


def _run_json(command: list[str]) -> dict[str, Any]:
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise AssertionError(f"command failed: {command}\nstdout={completed.stdout}\nstderr={completed.stderr}")
    return json.loads(completed.stdout)


def _git(cwd: Path, *args: str) -> None:
    completed = subprocess.run(("git", *args), cwd=cwd, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed\nstdout={completed.stdout}\nstderr={completed.stderr}")


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


def _get_json(url: str) -> dict[str, Any]:
    with urllib_request.urlopen(url, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _post_json(url: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib_request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib_request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
