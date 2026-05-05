"""Smoke-check runner/server GitHub closure decision workflow."""

from __future__ import annotations

import json
from pathlib import Path
import socket
import subprocess
import sys
import time
from tempfile import TemporaryDirectory
from urllib import request as urllib_request

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "apps" / "dev_control_plane_runner.py"
SERVER = ROOT / "apps" / "dev_control_plane_server.py"


def main() -> None:
    with TemporaryDirectory(prefix="dev-control-plane-github-closure-workflow-") as tmp_raw:
        tmp = Path(tmp_raw)
        allowed = _eligible_payload()
        denied_cases = (
            (_eligible_payload(blocker="manual blocker"), "blocker present"),
            (_eligible_payload(no_auto_merge=True), "NO_AUTO_MERGE is set"),
            (_eligible_payload(repo="orenvlad-ai/wb-core"), "repo is not dev-control-plane"),
            (_eligible_payload(forbidden_path_hits=("dev_control_plane_docs_master/fake.md",)), "forbidden paths detected"),
            (_eligible_payload(secrets_scan_passed=False), "secrets scan did not pass"),
            (_eligible_payload(pr_head_sha="different"), "PR head SHA does not match expected SHA"),
        )

        allowed_result = _runner_decision(tmp, allowed, expect_success=True)
        _assert_allowed_decision(allowed_result)
        if allowed_result.get("actual_merge_executed") is not False or allowed_result.get("mode") != "decision_only":
            raise AssertionError(f"runner decision must not perform GitHub mutation: {allowed_result}")

        for payload, expected_blocker in denied_cases:
            result = _runner_decision(tmp, payload, expect_success=False)
            _assert_denied_decision(result, expected_blocker)

        _exercise_server_decision(tmp, allowed, denied_cases[2][0])

    print("dev-control-plane-github-closure-workflow-smoke passed")


def _runner_decision(tmp: Path, payload: dict, *, expect_success: bool) -> dict:
    input_path = tmp / f"closure-{abs(hash(json.dumps(payload, sort_keys=True)))}.json"
    input_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    completed = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "github-closure-decision",
            "--input",
            str(input_path),
            "--auto-merge",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if expect_success and completed.returncode != 0:
        raise AssertionError(f"runner closure decision unexpectedly failed\nstdout={completed.stdout}\nstderr={completed.stderr}")
    if not expect_success and completed.returncode == 0:
        raise AssertionError(f"runner closure decision unexpectedly passed\nstdout={completed.stdout}")
    return json.loads(completed.stdout)


def _exercise_server_decision(tmp: Path, allowed: dict, denied: dict) -> None:
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
            str(tmp / "state"),
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        base_url = f"http://127.0.0.1:{port}"
        _wait_ready(base_url)
        state = _get_json(base_url + "/api/state")
        if state.get("github_closure_decision_enabled") is not True or state.get("github_closure_mode") != "decision_only":
            raise AssertionError(f"server must expose closure decision mode: {state}")
        allowed_result = _post_json(base_url + "/api/github-closure/decision", {"auto_merge": True, "eligibility": allowed})
        _assert_allowed_decision(allowed_result)
        denied_result = _post_json(base_url + "/api/github-closure/decision", {"auto_merge": True, "eligibility": denied})
        _assert_denied_decision(denied_result, "repo is not dev-control-plane")
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def _eligible_payload(**overrides) -> dict:
    payload = {
        "repo": "orenvlad-ai/dev-control-plane",
        "task_class": "L3",
        "pr_number": 4,
        "pr_state": "OPEN",
        "branch_name": "codex/github-closure-workflow",
        "expected_head_sha": "abc123",
        "pr_head_sha": "abc123",
        "working_tree_clean": True,
        "required_checks_passed": True,
        "diff_check_passed": True,
        "cached_diff_check_passed": True,
        "verifier_status": "passed",
        "forbidden_path_hits": [],
        "forbidden_action_hits": [],
        "changed_files": ["README.md", "src/dev_control_plane/github_closure.py"],
        "secrets_scan_passed": True,
        "handoff_required_fields_present": True,
        "handoff_has_compact_check": True,
        "blocker": None,
        "no_auto_merge": False,
        "codex_owned_branch": True,
        "pr_created_for_current_task": True,
        "derived_sync_task": False,
    }
    payload.update(overrides)
    return payload


def _assert_allowed_decision(result: dict) -> None:
    if result.get("status") != "allowed" or result.get("allowed") is not True:
        raise AssertionError(f"closure decision should allow clean self-merge: {result}")
    if result.get("merge_allowed") is not True or result.get("delete_branch_allowed") is not True:
        raise AssertionError(f"closure decision must allow merge and branch deletion when auto-merge requested: {result}")
    if result.get("blockers") != []:
        raise AssertionError(f"allowed decision must not include blockers: {result}")
    if result.get("decision_source") != "dev_control_plane.github_closure":
        raise AssertionError(f"runner/server decision must use github_closure helper: {result}")


def _assert_denied_decision(result: dict, expected_blocker: str) -> None:
    if result.get("status") != "denied" or result.get("allowed") is not False:
        raise AssertionError(f"closure decision should deny blocked merge: {result}")
    if result.get("merge_allowed") is not False or result.get("delete_branch_allowed") is not False:
        raise AssertionError(f"denied decision must not allow merge/delete branch: {result}")
    blockers = result.get("blockers") or []
    if not any(expected_blocker in blocker for blocker in blockers):
        raise AssertionError(f"expected blocker {expected_blocker!r}, got {blockers}")


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
    with urllib_request.urlopen(url, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


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


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


if __name__ == "__main__":
    main()
