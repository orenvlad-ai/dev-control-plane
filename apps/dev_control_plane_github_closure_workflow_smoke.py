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
SRC = ROOT / "src"
for path in (SRC, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dev_control_plane.v2_suite_contract import AUTHORITATIVE_CHECK_COUNT, AUTHORITATIVE_SMOKES  # noqa: E402
from apps.dev_control_plane_self_closure_v2 import SelfClosureError, evaluate_self_closure  # noqa: E402

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
        _exercise_v2_self_closure()
        _assert_v2_workflow_contract()

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


def _exercise_v2_self_closure() -> None:
    head_sha = "a" * 40
    event = _v2_pull_event(head_sha=head_sha)
    evidence = _v2_suite_evidence(head_sha=head_sha)
    policy = evidence["static_policy"]
    decision = evaluate_self_closure(
        event,
        checkout_head=head_sha,
        changed_files=("README.md", "src/dev_control_plane/supervisor.py"),
        working_tree_clean=True,
        diff_check_passed=True,
        cached_diff_check_passed=True,
        suite_evidence=evidence,
        static_policy=policy,
    )
    if not decision.allowed or not decision.merge_allowed:
        raise AssertionError(f"head-bound self-closure should pass: {decision}")

    forged = _v2_suite_evidence(head_sha="b" * 40)
    try:
        evaluate_self_closure(
            event,
            checkout_head=head_sha,
            changed_files=("README.md",),
            working_tree_clean=True,
            diff_check_passed=True,
            cached_diff_check_passed=True,
            suite_evidence=forged,
            static_policy=policy,
        )
    except SelfClosureError as exc:
        if "head_mismatch" not in str(exc):
            raise AssertionError(f"unexpected forged-evidence denial: {exc}") from exc
    else:
        raise AssertionError("executor-authored PR text must not replace exact-head suite evidence")

    no_auto = _v2_pull_event(head_sha=head_sha, title="NO_AUTO_MERGE: inspect")
    denied = evaluate_self_closure(
        no_auto,
        checkout_head=head_sha,
        changed_files=("README.md",),
        working_tree_clean=True,
        diff_check_passed=True,
        cached_diff_check_passed=True,
        suite_evidence=evidence,
        static_policy=policy,
    )
    if denied.allowed or not any("NO_AUTO_MERGE" in blocker for blocker in denied.blockers):
        raise AssertionError(f"NO_AUTO_MERGE must remain fail-closed: {denied}")

    protected = evaluate_self_closure(
        event,
        checkout_head=head_sha,
        changed_files=("dev_control_plane_docs_master/generated.md",),
        working_tree_clean=True,
        diff_check_passed=True,
        cached_diff_check_passed=True,
        suite_evidence=evidence,
        static_policy=policy,
    )
    if protected.allowed or not any("protected derived docset" in blocker for blocker in protected.blockers):
        raise AssertionError(f"protected derived pack must remain fail-closed: {protected}")


def _assert_v2_workflow_contract() -> None:
    source = (ROOT / ".github/workflows/orchestrator-v2.yml").read_text(encoding="utf-8")
    required = (
        "self-closure:",
        "needs: v2-suite",
        "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02",
        "actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093",
        "github.event.pull_request.head.sha",
        "dev_control_plane_self_closure_v2.py",
        "persist-credentials: false",
    )
    missing = [item for item in required if item not in source]
    if missing:
        raise AssertionError(f"v2 self-closure workflow lost trusted bindings: {missing}")


def _v2_pull_event(*, head_sha: str, title: str = "Orchestrator v2") -> dict:
    return {
        "repository": {"full_name": "orenvlad-ai/dev-control-plane"},
        "pull_request": {
            "number": 17,
            "state": "open",
            "title": title,
            "body": (
                "=== ДЛЯ КУРАТОРА ===\n"
                "Статус: готово к машинной проверке. Проверки перечислены ниже.\n\n"
                "=== СЖАТАЯ ПРОВЕРКА ===\n"
                "Полный fake-first suite привязан к exact head; ручная приёмка не подменяется."
            ),
            "base": {"ref": "main", "sha": "c" * 40},
            "head": {"ref": "codex/orchestrator-v2", "sha": head_sha},
        },
    }


def _v2_suite_evidence(*, head_sha: str) -> dict:
    return {
        "schema": "dev-control-plane/v2-suite-evidence/v2",
        "status": "passed",
        "suite": "orchestrator_v2",
        "commit_sha": head_sha,
        "checks": AUTHORITATIVE_CHECK_COUNT,
        "smokes": [
            {"path": path, "status": "passed", "seconds": 0.001}
            for path in AUTHORITATIVE_SMOKES
        ],
        "real_model_calls": 0,
        "static_policy": {
            "projection_is_read_only": True,
            "legacy_operator_parity_disabled": True,
            "workflow_mutation_authority": "none",
            "secrets_scan": "passed",
            "scanned_file_count": 10,
        },
    }


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
