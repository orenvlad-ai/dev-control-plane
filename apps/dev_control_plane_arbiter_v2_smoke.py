"""Fake-only smoke for the fresh ephemeral Sol Ultra arbiter."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (SRC, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dev_control_plane.arbiter import (  # noqa: E402
    ArbiterCase,
    ArbiterError,
    FreshSolArbiter,
    _reject_runtime_identity_mismatch,
)
from dev_control_plane.orchestration_contracts import RevisionBinding  # noqa: E402


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="dev-control-plane-arbiter-smoke-") as raw:
        root = Path(raw)
        fake = root / "fake-codex"
        log = root / "invocation.json"
        binding = RevisionBinding(
            task_id="task-1",
            task_revision=2,
            workstream_id="ws-1",
            workstream_revision=3,
            pr_head_sha="a" * 40,
            resources=("repo:dev-control-plane",),
        )
        digest = hashlib.sha256(b"frozen-case").hexdigest()
        source_snapshot = {"reason": "shared_contract", "safe": True, "nested": {"order": ["task-1"]}}
        case = ArbiterCase(
            kind="release_plan",
            case_id="release-plan:fixture",
            case_digest=digest,
            bindings=(binding,),
            snapshot=source_snapshot,
        )
        source_snapshot["reason"] = "mutated-after-case-creation"
        source_snapshot["nested"]["order"].append("task-2")
        if case.snapshot["reason"] != "shared_contract" or case.snapshot["nested"]["order"] != ("task-1",):
            raise AssertionError(f"arbiter case did not freeze its input snapshot: {case.snapshot}")
        try:
            case.snapshot["reason"] = "mutated-through-case"  # type: ignore[index]
        except TypeError:
            pass
        else:
            raise AssertionError("arbiter case snapshot remained mutable")
        fake.write_text(_fake_source(log, case, binding), encoding="utf-8")
        fake.chmod(0o700)
        arbiter = FreshSolArbiter(
            codex_bin=str(fake),
            timeout_seconds=5,
            env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(root), "OPENAI_API_KEY": "fake-must-not-propagate"},
        )
        decision = arbiter.decide(case, cwd=ROOT)
        assert decision.case_digest == digest and decision.model == "gpt-5.6-sol"
        invocation = json.loads(log.read_text(encoding="utf-8"))
        arguments = invocation["arguments"]
        for required in (
            "--ephemeral",
            "--ignore-user-config",
            "--ignore-rules",
            "--strict-config",
            'approval_policy="never"',
            'web_search="disabled"',
            'shell_environment_policy.inherit="none"',
            "read-only",
            "gpt-5.6-sol",
            'model_reasoning_effort="ultra"',
            "--output-schema",
            "--skip-git-repo-check",
        ):
            assert required in arguments, (required, arguments)
        assert "--dangerously-bypass-approvals-and-sandbox" not in arguments
        assert invocation["prompt_count"] == 1
        assert invocation["has_frozen_snapshot"] is True
        assert invocation["has_mutated_snapshot"] is False
        assert invocation["cwd_is_isolated"] is True
        assert invocation["sensitive_env_present"] is False

        stale_fake = root / "fake-codex-stale"
        stale_log = root / "stale-invocation.json"
        stale_binding = RevisionBinding(
            task_id=binding.task_id,
            task_revision=binding.task_revision + 1,
            workstream_id=binding.workstream_id,
            workstream_revision=binding.workstream_revision,
            pr_head_sha=binding.pr_head_sha,
            resources=binding.resources,
        )
        stale_fake.write_text(_fake_source(stale_log, case, stale_binding), encoding="utf-8")
        stale_fake.chmod(0o700)
        try:
            FreshSolArbiter(codex_bin=str(stale_fake), timeout_seconds=5).decide(case, cwd=ROOT)
        except ArbiterError as exc:
            if "stale" not in str(exc):
                raise AssertionError(f"stale arbiter decision failed for the wrong reason: {exc}") from exc
        else:
            raise AssertionError("arbiter accepted a decision bound to a stale task revision")

        slow_fake = root / "fake-codex-slow"
        slow_fake.write_text(
            "#!/usr/bin/env python3\nimport sys, time\nsys.stdin.read()\ntime.sleep(10)\n",
            encoding="utf-8",
        )
        slow_fake.chmod(0o700)
        started = time.monotonic()
        try:
            FreshSolArbiter(codex_bin=str(slow_fake), timeout_seconds=0.05).decide(case, cwd=ROOT)
        except ArbiterError as exc:
            if "timeout" not in str(exc):
                raise AssertionError(f"bounded arbiter timeout failed for the wrong reason: {exc}") from exc
        else:
            raise AssertionError("arbiter did not enforce its bounded timeout")
        if time.monotonic() - started > 1:
            raise AssertionError("arbiter timeout did not terminate its owned process promptly")
        for event in (
            '{"type":"model/rerouted","toModel":"fallback"}',
            '{"type":"turn.started","model":"fallback"}',
            '{"type":"turn.started","reasoningEffort":"high"}',
        ):
            try:
                _reject_runtime_identity_mismatch(event)
            except ArbiterError:
                pass
            else:
                raise AssertionError(f"arbiter accepted runtime identity mismatch: {event}")
    print("arbiter v2 smoke: ok")


def _fake_source(log: Path, case: ArbiterCase, binding: RevisionBinding) -> str:
    decision = {
        "decision_id": "decision-1",
        "kind": case.kind,
        "case_id": case.case_id,
        "case_digest": case.case_digest,
        "bindings": [
            {
                "task_id": binding.task_id,
                "task_revision": binding.task_revision,
                "workstream_id": binding.workstream_id,
                "workstream_revision": binding.workstream_revision,
                "pr_head_sha": binding.pr_head_sha,
                "resources": list(binding.resources),
            }
        ],
        "steps": [
            {
                "step_id": "step-1",
                "action": "release",
                "task_id": binding.task_id,
                "workstream_id": binding.workstream_id,
                "depends_on": [],
            }
        ],
        "model": "gpt-5.6-sol",
        "reasoning": "ultra",
        "created_at": "2026-08-04T00:00:00Z",
        "schema": "dev-control-plane/arbiter-decision/v2",
    }
    return f'''#!/usr/bin/env python3
import json, os, pathlib, sys
prompt = sys.stdin.read()
args = sys.argv[1:]
pathlib.Path({str(log)!r}).write_text(json.dumps({{
    "arguments": args,
    "prompt_count": prompt.count("IMMUTABLE_CASE:"),
    "has_frozen_snapshot": '"reason":"shared_contract"' in prompt and '"order":["task-1"]' in prompt,
    "has_mutated_snapshot": "mutated-after-case-creation" in prompt or "task-2" in prompt,
    "cwd_is_isolated": pathlib.Path(args[args.index("--cd") + 1]) != pathlib.Path({str(ROOT)!r}),
    "sensitive_env_present": any(name in os.environ for name in ("OPENAI_API_KEY", "GITHUB_TOKEN", "AWS_SECRET_ACCESS_KEY")),
}}))
output = pathlib.Path(args[args.index("--output-last-message") + 1])
output.write_text(json.dumps({decision!r}))
raise SystemExit(0)
'''


if __name__ == "__main__":
    main()
