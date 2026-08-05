"""GitHub Actions self-closure admission for Orchestrator v2 PRs.

This is a deterministic check, not a merge actuator.  It binds the repository's
existing closure policy to the immutable pull-request event, exact checked-out
head, complete Git diff, a head-bound authoritative-suite receipt, and policy
checks recomputed by this job.  The PR body is checked only as a human handoff;
executor-authored marker text is never accepted as verification evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (SRC, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dev_control_plane.github_closure import (  # noqa: E402
    DERIVED_PACK_PREFIX,
    DEV_CONTROL_PLANE_REPO,
    DOCSET_MANIFEST,
    evaluate_dev_control_plane_closure_decision,
    github_closure_decision_to_dict,
)
from dev_control_plane.v2_suite_contract import (  # noqa: E402
    AUTHORITATIVE_CHECK_COUNT,
    AUTHORITATIVE_SMOKES,
)
from apps.dev_control_plane_v2_suite import run_static_policy_checks  # noqa: E402


HANDOFF_HEADER = "=== ДЛЯ КУРАТОРА ==="
COMPACT_HEADER = "=== СЖАТАЯ ПРОВЕРКА ==="
SUITE_EVIDENCE_SCHEMA = "dev-control-plane/v2-suite-evidence/v2"
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_MAX_EVENT_BYTES = 2_000_000
_MAX_EVIDENCE_BYTES = 1_000_000
_MAX_BODY_CHARS = 50_000


class SelfClosureError(RuntimeError):
    """A sanitized self-closure admission failure."""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate exact v2 self-closure PR admission")
    parser.add_argument("--event-file", type=Path, default=os.environ.get("GITHUB_EVENT_PATH"))
    parser.add_argument("--suite-evidence", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        event = _read_event(args.event_file)
        suite_evidence = _read_json_file(
            args.suite_evidence,
            max_bytes=_MAX_EVIDENCE_BYTES,
            reason="suite_evidence_file_invalid",
        )
        pull = _mapping(event, "pull_request")
        base = _mapping(pull, "base")
        head = _mapping(pull, "head")
        base_sha = _sha("base.sha", base.get("sha"))
        head_sha = _sha("head.sha", head.get("sha"))
        checkout_head = _git(("rev-parse", "HEAD")).strip()
        if checkout_head != head_sha:
            raise SelfClosureError("checked_out_head_differs_from_pull_request")
        changed_files = _changed_files(base_sha, head_sha)
        clean = not _git(("status", "--porcelain")).strip()
        diff_clean = _git_ok(("diff", "--check", f"{base_sha}...{head_sha}"))
        cached_clean = _git_ok(("diff", "--cached", "--check"))
        _validate_suite_evidence(suite_evidence, expected_head_sha=head_sha)
        static_policy = run_static_policy_checks()
        decision = evaluate_self_closure(
            event,
            checkout_head=checkout_head,
            changed_files=changed_files,
            working_tree_clean=clean,
            diff_check_passed=diff_clean,
            cached_diff_check_passed=cached_clean,
            suite_evidence=suite_evidence,
            static_policy=static_policy,
        )
    except (OSError, ValueError, SelfClosureError, subprocess.SubprocessError) as exc:
        print(
            json.dumps(
                {
                    "schema": "dev-control-plane/self-closure-check/v2",
                    "status": "denied",
                    "reason_code": _reason_code(exc),
                },
                sort_keys=True,
            )
        )
        return 1
    payload = github_closure_decision_to_dict(decision)
    payload.update(
        {
            "schema": "dev-control-plane/self-closure-check/v2",
            "head_sha": checkout_head,
            "changed_files_digest": hashlib.sha256(
                "\0".join(changed_files).encode("utf-8")
            ).hexdigest(),
            "changed_files_count": len(changed_files),
            "suite_evidence_digest": _canonical_digest(suite_evidence),
            "static_policy_digest": _canonical_digest(static_policy),
            "verification_source": "head_bound_suite_plus_recomputed_policy",
        }
    )
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if decision.allowed and decision.merge_allowed else 1


def evaluate_self_closure(
    event: Mapping[str, Any],
    *,
    checkout_head: str,
    changed_files: Sequence[str],
    working_tree_clean: bool,
    diff_check_passed: bool,
    cached_diff_check_passed: bool,
    suite_evidence: Mapping[str, Any],
    static_policy: Mapping[str, Any],
) -> Any:
    """Return the repository-owned decision for one immutable PR snapshot."""

    pull = _mapping(event, "pull_request")
    repository = _mapping(event, "repository")
    base = _mapping(pull, "base")
    head = _mapping(pull, "head")
    body = pull.get("body") or ""
    title = pull.get("title") or ""
    if not isinstance(body, str) or not isinstance(title, str):
        raise SelfClosureError("pull_request_text_invalid")
    if len(body) > _MAX_BODY_CHARS or len(title) > 500:
        raise SelfClosureError("pull_request_text_oversized")
    repo = repository.get("full_name")
    if repo != DEV_CONTROL_PLANE_REPO:
        raise SelfClosureError("repository_identity_mismatch")
    if base.get("ref") != "main":
        raise SelfClosureError("pull_request_base_mismatch")
    head_sha = _sha("head.sha", head.get("sha"))
    if checkout_head != head_sha:
        raise SelfClosureError("pull_request_head_mismatch")
    branch = head.get("ref")
    if not isinstance(branch, str) or not branch.startswith("codex/"):
        raise SelfClosureError("branch_is_not_codex_owned")
    number = pull.get("number")
    if isinstance(number, bool) or not isinstance(number, int) or number < 1:
        raise SelfClosureError("pull_request_number_invalid")
    if pull.get("state") != "open":
        raise SelfClosureError("pull_request_not_open")
    _validate_handoff_structure(body)
    no_auto_merge = "NO_AUTO_MERGE" in title or "NO_AUTO_MERGE" in body
    normalized_files = tuple(_repo_path(item) for item in changed_files)
    if not normalized_files or len(set(normalized_files)) != len(normalized_files):
        raise SelfClosureError("changed_file_set_invalid")
    _validate_suite_evidence(suite_evidence, expected_head_sha=head_sha)
    _validate_static_policy(static_policy)
    forbidden_path_hits = tuple(
        path
        for path in normalized_files
        if path == DOCSET_MANIFEST or path.startswith(DERIVED_PACK_PREFIX)
    )
    payload = {
        "repo": repo,
        "task_class": "L3",
        "pr_number": number,
        "pr_state": "OPEN",
        "branch_name": branch,
        "expected_head_sha": head_sha,
        "pr_head_sha": checkout_head,
        "working_tree_clean": working_tree_clean,
        "required_checks_passed": True,
        "diff_check_passed": diff_check_passed,
        "cached_diff_check_passed": cached_diff_check_passed,
        "verifier_status": "passed",
        "forbidden_path_hits": list(forbidden_path_hits),
        "forbidden_action_hits": [],
        "changed_files": list(normalized_files),
        "secrets_scan_passed": True,
        "handoff_required_fields_present": True,
        "handoff_has_compact_check": True,
        "blocker": None,
        "no_auto_merge": no_auto_merge,
        "codex_owned_branch": True,
        "pr_created_for_current_task": True,
        "derived_sync_task": False,
    }
    return evaluate_dev_control_plane_closure_decision(payload, requested_auto_merge=True)


def _read_event(path: Path | None) -> Mapping[str, Any]:
    if path is None:
        raise SelfClosureError("github_event_file_missing")
    return _read_json_file(path, max_bytes=_MAX_EVENT_BYTES, reason="github_event_file_invalid")


def _read_json_file(path: Path, *, max_bytes: int, reason: str) -> Mapping[str, Any]:
    metadata = path.lstat()
    if not path.is_file() or path.is_symlink() or not 1 <= metadata.st_size <= max_bytes:
        raise SelfClosureError(reason)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise SelfClosureError(reason)
    return payload


def _validate_suite_evidence(evidence: Mapping[str, Any], *, expected_head_sha: str) -> None:
    if evidence.get("schema") != SUITE_EVIDENCE_SCHEMA or evidence.get("status") != "passed":
        raise SelfClosureError("authoritative_suite_not_passed")
    if evidence.get("commit_sha") != expected_head_sha:
        raise SelfClosureError("authoritative_suite_head_mismatch")
    if evidence.get("checks") != AUTHORITATIVE_CHECK_COUNT or evidence.get("real_model_calls") != 0:
        raise SelfClosureError("authoritative_suite_contract_mismatch")
    smokes = evidence.get("smokes")
    if not isinstance(smokes, list) or tuple(item.get("path") for item in smokes if isinstance(item, Mapping)) != tuple(
        AUTHORITATIVE_SMOKES
    ):
        raise SelfClosureError("authoritative_suite_membership_mismatch")
    if any(not isinstance(item, Mapping) or item.get("status") != "passed" for item in smokes):
        raise SelfClosureError("authoritative_suite_member_failed")
    _validate_static_policy(_mapping(evidence, "static_policy"))


def _validate_static_policy(policy: Mapping[str, Any]) -> None:
    if policy.get("projection_is_read_only") is not True:
        raise SelfClosureError("projection_policy_not_proven")
    if policy.get("legacy_operator_parity_disabled") is not True:
        raise SelfClosureError("legacy_retirement_not_proven")
    if policy.get("workflow_mutation_authority") != "none":
        raise SelfClosureError("workflow_mutation_authority_not_proven_absent")
    if policy.get("secrets_scan") != "passed":
        raise SelfClosureError("secrets_scan_not_proven")
    count = policy.get("scanned_file_count")
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise SelfClosureError("static_policy_file_count_invalid")


def _validate_handoff_structure(body: str) -> None:
    curator_at = body.find(HANDOFF_HEADER)
    compact_at = body.find(COMPACT_HEADER)
    if curator_at < 0 or compact_at <= curator_at:
        raise SelfClosureError("handoff_headers_missing_or_out_of_order")
    curator_text = body[curator_at + len(HANDOFF_HEADER) : compact_at].strip()
    compact_text = body[compact_at + len(COMPACT_HEADER) :].strip()
    if len(curator_text) < 20 or len(compact_text) < 20:
        raise SelfClosureError("handoff_sections_empty")


def _canonical_digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _changed_files(base_sha: str, head_sha: str) -> tuple[str, ...]:
    raw = subprocess.run(
        ["git", "diff", "--name-only", "-z", f"{base_sha}...{head_sha}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        timeout=60,
    ).stdout
    values = tuple(item.decode("utf-8", errors="strict") for item in raw.split(b"\0") if item)
    return tuple(sorted(values))


def _git(arguments: Sequence[str]) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if completed.returncode != 0:
        raise SelfClosureError("git_readback_failed")
    return completed.stdout


def _git_ok(arguments: Sequence[str]) -> bool:
    return subprocess.run(
        ["git", *arguments],
        cwd=ROOT,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=60,
    ).returncode == 0


def _mapping(value: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    item = value.get(key)
    if not isinstance(item, Mapping):
        raise SelfClosureError(f"{key}_missing")
    return item


def _sha(label: str, value: Any) -> str:
    if not isinstance(value, str) or not _SHA_RE.fullmatch(value):
        raise SelfClosureError(label.replace(".", "_") + "_invalid")
    return value


def _repo_path(value: Any) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\0" in value:
        raise SelfClosureError("changed_file_path_invalid")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise SelfClosureError("changed_file_path_unsafe")
    return value


def _reason_code(exc: Exception) -> str:
    text = str(exc).strip().lower().replace(".", "_")
    text = re.sub(r"[^a-z0-9_]+", "_", text).strip("_")
    return text[:120] or "self_closure_failed"


if __name__ == "__main__":
    raise SystemExit(main())
