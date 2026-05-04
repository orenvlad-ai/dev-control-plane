"""End-to-end smoke-check for development control-plane MVP local CLI tooling."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (SRC, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

EXAMPLE_SPEC = ROOT / "artifacts" / "input" / "example_task_spec.json"
CLI = ROOT / "apps" / "dev_control_plane_cli.py"


def main() -> None:
    with TemporaryDirectory(prefix="dev-control-plane-cli-smoke-") as tmp:
        tmp_dir = Path(tmp)
        frozen_a = tmp_dir / "frozen-a.json"
        frozen_b = tmp_dir / "frozen-b.json"
        prompt_path = tmp_dir / "prompt.txt"

        validate_summary = _run_json("validate-task-spec", "--input", str(EXAMPLE_SPEC))
        if not validate_summary.get("validation_ok"):
            raise AssertionError(f"example task spec must validate: {validate_summary}")
        if "derived_project_pack/**" not in validate_summary.get("forbidden_paths", []):
            raise AssertionError("validation summary must keep derived project pack forbidden path")
        if "target_project_docs_manifest.md" not in validate_summary.get("forbidden_paths", []):
            raise AssertionError("validation summary must keep target manifest forbidden path")
        for action in ("live_deploy", "ssh", "root_shell", "public_route_change", "execution_from_discussion"):
            if action not in validate_summary.get("forbidden_actions", []):
                raise AssertionError(f"validation summary missing forbidden action: {action}")
        for action in ("live", "deploy", "live_deploy", "SSH", "ssh", "root", "root_shell"):
            if action in validate_summary.get("allowed_actions", []):
                raise AssertionError(f"dangerous action must not be allowed: {action}")

        freeze_args = (
            "freeze-task-spec",
            "--input",
            str(EXAMPLE_SPEC),
            "--frozen-at",
            "2026-05-01T00:00:00Z",
        )
        freeze_summary_a = _run_json(*freeze_args, "--output", str(frozen_a))
        freeze_summary_b = _run_json(*freeze_args, "--output", str(frozen_b))
        freeze_summary_time_variant = _run_json(
            "freeze-task-spec",
            "--input",
            str(EXAMPLE_SPEC),
            "--frozen-at",
            "2026-05-02T00:00:00Z",
            "--output",
            str(tmp_dir / "frozen-time-variant.json"),
        )
        if freeze_summary_a.get("status") != "frozen":
            raise AssertionError(f"freeze must return frozen status: {freeze_summary_a}")
        if freeze_summary_a.get("spec_hash") != freeze_summary_b.get("spec_hash"):
            raise AssertionError("fixed freeze input must produce stable spec_hash")
        if freeze_summary_a.get("spec_hash") != freeze_summary_time_variant.get("spec_hash"):
            raise AssertionError("spec_hash must not depend on frozen_at timestamp")

        frozen_payload = json.loads(frozen_a.read_text(encoding="utf-8"))
        if frozen_payload.get("status") != "frozen":
            raise AssertionError(f"frozen payload status drifted: {frozen_payload.get('status')}")
        if not frozen_payload.get("spec_hash"):
            raise AssertionError("frozen payload must contain spec_hash")

        draft_prompt = _run(
            "generate-codex-prompt",
            "--task-spec",
            str(EXAMPLE_SPEC),
            "--step-id",
            "step-001",
            "--output",
            str(prompt_path),
            check=False,
        )
        if draft_prompt.returncode == 0:
            raise AssertionError("draft task spec must be rejected by generate-codex-prompt")

        prompt_summary = _run_json(
            "generate-codex-prompt",
            "--task-spec",
            str(frozen_a),
            "--step-id",
            "step-001",
            "--output",
            str(prompt_path),
        )
        if not prompt_summary.get("mandatory_blocks_present"):
            raise AssertionError(f"prompt summary must confirm mandatory blocks: {prompt_summary}")

        prompt = prompt_path.read_text(encoding="utf-8")
        for token in (
            "Класс задачи:",
            "Причина классификации:",
            "Режим выполнения:",
            "=== ДЛЯ КУРАТОРА ===",
            "=== СЖАТАЯ ПРОВЕРКА ===",
            "derived_project_pack/**",
            "target_project_docs_manifest.md",
            "live_deploy",
            "ssh",
            "root_shell",
        ):
            if token not in prompt:
                raise AssertionError(f"generated prompt missing token: {token}")

    print("dev-control-plane-mvp-cli-smoke passed")


def _run_json(*args: str) -> dict:
    result = _run(*args, check=True)
    return json.loads(result.stdout)


def _run(*args: str, check: bool) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        cwd=ROOT,
        check=check,
        text=True,
        capture_output=True,
    )


if __name__ == "__main__":
    main()
