"""Smoke-check dev-control-plane GitHub merge eligibility policy."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (SRC, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dev_control_plane.contracts import (  # noqa: E402
    build_codex_prompt,
    frozen_task_spec_payload_from_mapping,
    sprint_steps_from_task_spec_mapping,
    task_spec_from_mapping,
)
from dev_control_plane.github_closure import (  # noqa: E402
    DEV_CONTROL_PLANE_REPO,
    MergeEligibilityInput,
    evaluate_dev_control_plane_merge_eligibility,
)


def main() -> None:
    allowed = _eligible_payload(task_class="L3")
    result = evaluate_dev_control_plane_merge_eligibility(allowed)
    if not result.allowed:
        raise AssertionError(f"dev-control-plane L3 self-merge should be allowed when gates are clean: {result}")

    _assert_denied(_eligible_payload(blocker="manual blocker"), "blocker present")
    _assert_denied(
        _eligible_payload(forbidden_path_hits=("dev_control_plane_docs_master/index.md",)),
        "forbidden paths detected",
    )
    _assert_denied(_eligible_payload(repo="orenvlad-ai/wb-core"), "repo is not dev-control-plane")
    _assert_denied(_eligible_payload(no_auto_merge=True), "NO_AUTO_MERGE is set")

    pack_change = _eligible_payload(changed_files=("dev_control_plane_docs_master/00_INDEX.md",))
    _assert_denied(pack_change, "protected derived docset paths changed")
    pack_sync = _eligible_payload(
        changed_files=("dev_control_plane_docs_master/00_INDEX.md",),
        derived_sync_task=True,
    )
    if not evaluate_dev_control_plane_merge_eligibility(pack_sync).allowed:
        raise AssertionError("derived-sync task should be allowed to pass protected docset gate when other gates are clean")

    prompt = _github_closure_prompt()
    for token in (
        "Codex-Owned GitHub Closure Contract",
        "dev-control-plane",
        "NO_AUTO_MERGE",
        "Merge:",
        "Delete branch:",
    ):
        if token not in prompt:
            raise AssertionError(f"prompt contract missing GitHub closure token: {token}")

    print("dev-control-plane-github-closure-smoke passed")


def _eligible_payload(**overrides) -> MergeEligibilityInput:
    payload = {
        "repo": DEV_CONTROL_PLANE_REPO,
        "task_class": "L3",
        "pr_number": 3,
        "pr_state": "OPEN",
        "branch_name": "codex/github-closure-policy",
        "expected_head_sha": "abc123",
        "pr_head_sha": "abc123",
        "working_tree_clean": True,
        "required_checks_passed": True,
        "diff_check_passed": True,
        "cached_diff_check_passed": True,
        "verifier_status": "passed",
        "forbidden_path_hits": (),
        "forbidden_action_hits": (),
        "changed_files": ("README.md", "AGENTS.md", "src/dev_control_plane/github_closure.py"),
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
    return MergeEligibilityInput(**payload)


def _assert_denied(payload: MergeEligibilityInput, expected: str) -> None:
    result = evaluate_dev_control_plane_merge_eligibility(payload)
    if result.allowed:
        raise AssertionError(f"payload should be denied: {payload}")
    if not any(expected in blocker for blocker in result.blockers):
        raise AssertionError(f"expected blocker {expected!r}, got {result.blockers}")


def _github_closure_prompt() -> str:
    frozen = frozen_task_spec_payload_from_mapping(
        {
            "id": "github-closure-smoke",
            "version": "1",
            "status": "draft",
            "title": "GitHub closure smoke",
            "goal": "Verify Codex-owned dev-control-plane closure prompt contract.",
            "scope": ["README.md"],
            "not_in_scope": ["target repos", "production deploy", "preview deploy"],
            "task_class": "L3",
            "class_reason": "Governance policy smoke for repo closure.",
            "risks": ["merge must remain gate-bound"],
            "acceptance_criteria": ["prompt contains GitHub closure contract"],
            "required_smokes": ["python3 apps/dev_control_plane_github_closure_smoke.py"],
            "allowed_paths": ["README.md"],
            "forbidden_paths": ["dev_control_plane_docs_master/**", "99_MANIFEST__DOCSET_VERSION.md"],
            "allowed_actions": ["repo_governance_docs"],
            "forbidden_actions": [
                "live_deploy",
                "ssh",
                "root_shell",
                "public_route_change",
                "target_repo_mutation",
                "production_deploy",
                "preview_deploy",
            ],
            "human_gates": ["review GitHub closure policy"],
            "explicit_policy_note": "L3 governance smoke only.",
        },
        frozen_at="2026-05-05T00:00:00Z",
    )
    task_spec = task_spec_from_mapping(frozen)
    step = sprint_steps_from_task_spec_mapping(frozen, task_spec)[0]
    return build_codex_prompt(task_spec, step)


if __name__ == "__main__":
    main()
