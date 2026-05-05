"""Smoke-check target PR/preview/approval decision-only workflow."""

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

from dev_control_plane.target_workflow import (  # noqa: E402
    build_preview_plan,
    build_target_pr_plan,
    evaluate_target_approval,
)

RUNNER = ROOT / "apps" / "dev_control_plane_runner.py"
SERVER = ROOT / "apps" / "dev_control_plane_server.py"


def main() -> None:
    clean = _clean_payload()

    pr_plan = build_target_pr_plan(clean)
    if not pr_plan.allowed or pr_plan.plan.get("branch_name", "").startswith("devcp/") is False:
        raise AssertionError(f"clean target PR plan must be allowed with devcp branch: {pr_plan}")
    if "Сводка TaskSpec" not in str(pr_plan.plan.get("pr_body")):
        raise AssertionError(f"target PR body must include required sections: {pr_plan}")
    _assert_denied(build_target_pr_plan({**clean, "auto_merge": True}), "auto-merge")
    _assert_denied(build_target_pr_plan({**clean, "target_repo": "orenvlad-ai/dev-control-plane"}), "target_repo")
    _assert_denied(build_target_pr_plan({**clean, "forbidden_path_hits": ["wb_core_docs_master/x.md"]}), "forbidden")
    _assert_denied(build_target_pr_plan({**clean, "secrets_scan_status": "failed"}), "secrets")

    preview = build_preview_plan(clean)
    if not preview.allowed or preview.status != "dry_run_ready":
        raise AssertionError(f"preview dry-run contract must be ready: {preview}")
    if preview.plan.get("uses_production_webcore_runtime"):
        raise AssertionError(f"preview must not use WebCore production runtime: {preview}")
    if not preview.warnings:
        raise AssertionError("preview dry-run must warn that real preview runtime command is still required")

    approval = evaluate_target_approval(
        {
            **clean,
            "decision": "approve",
            "preview_status": "passed",
            "target_merge_policy_enabled": True,
        }
    )
    if not approval.allowed or approval.plan.get("production_deploy_allowed") is not False:
        raise AssertionError(f"clean approval should allow target merge gate but not production deploy: {approval}")
    _assert_denied(evaluate_target_approval({**clean, "decision": "approve", "preview_status": "failed"}), "preview")
    _assert_denied(evaluate_target_approval({**clean, "decision": "approve", "blocker": "manual stop"}), "blocker")
    reject = evaluate_target_approval({**clean, "decision": "reject"})
    if not reject.allowed or reject.plan.get("production_deploy_allowed") is not False:
        raise AssertionError(f"reject must be allowed without production mutation: {reject}")

    with TemporaryDirectory(prefix="dev-control-plane-target-workflow-") as tmp:
        tmp_path = Path(tmp)
        payload_path = tmp_path / "payload.json"
        _write_json(payload_path, clean)
        runner_plan = _run_json([sys.executable, str(RUNNER), "target-pr-plan", "--input", str(payload_path)])
        if runner_plan.get("action") != "target_pr_plan" or runner_plan.get("allowed") is not True:
            raise AssertionError(f"runner target-pr-plan must use workflow helper: {runner_plan}")
        preview_plan = _run_json([sys.executable, str(RUNNER), "preview-plan", "--input", str(payload_path)])
        if preview_plan.get("action") != "preview_plan" or preview_plan.get("plan", {}).get("dry_run_only") is not True:
            raise AssertionError(f"runner preview-plan must be dry-run only: {preview_plan}")

        server = subprocess.Popen(
            [
                sys.executable,
                str(SERVER),
                "--host",
                "127.0.0.1",
                "--port",
                "0",
                "--state-dir",
                str(tmp_path / "state"),
            ],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            first_line = server.stdout.readline() if server.stdout else ""
            started = json.loads(first_line)
            base_url = f"http://127.0.0.1:{started['port']}"
            _wait_ready(base_url)
            state = _get_json(base_url + "/api/state")
            if state.get("target_workflow_decision_enabled") is not True:
                raise AssertionError(f"server must expose target workflow decision mode: {state}")
            server_plan = _post_json(base_url + "/api/target-workflow/pr-plan", clean)
            if server_plan.get("action") != "target_pr_plan" or server_plan.get("allowed") is not True:
                raise AssertionError(f"server target workflow endpoint must use helper: {server_plan}")
        finally:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()

    print("dev-control-plane-target-workflow-smoke passed")


def _clean_payload() -> dict[str, Any]:
    return {
        "target_project_id": "wb-core",
        "target_repo": "orenvlad-ai/wb-core",
        "target_source_mode": "remote_managed_clone",
        "base_branch": "main",
        "run_id": "run-target-workflow-smoke",
        "task_spec_id": "target-workflow-smoke",
        "task_spec_summary": "Проверка decision-only target workflow.",
        "workspace_source": "managed_clone",
        "changed_files": ["README.md"],
        "verifier_status": "passed",
        "verifier_result": "passed",
        "secrets_scan_status": "passed",
        "forbidden_path_hits": [],
        "direct_target_mutation": False,
        "production_deploy_requested": False,
    }


def _assert_denied(decision, token: str) -> None:
    if decision.allowed or not any(token in blocker for blocker in decision.blockers):
        raise AssertionError(f"decision must be denied by {token}: {decision}")


def _run_json(command: list[str], expect_success: bool = True) -> dict[str, Any]:
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    if expect_success and completed.returncode != 0:
        raise AssertionError(f"command failed: {command}\nstdout={completed.stdout}\nstderr={completed.stderr}")
    if not expect_success and completed.returncode == 0:
        raise AssertionError(f"command unexpectedly passed: {command}\nstdout={completed.stdout}")
    return json.loads(completed.stdout)


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
    request = urllib_request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib_request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
