from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import unittest
from unittest import mock

from dcp_orchestrator.canary import (
    CanarySupervisor,
    MARKER_BYTES,
    MARKER_RELATIVE,
    WorkerReceipt,
)
from dcp_orchestrator.config import (
    BUNDLE_ID,
    CANONICAL_PROMPT,
    ENV_PREFIX,
    IPC_NAMESPACE,
    PROCESS_ID,
    PRODUCT_NAME,
    RuntimePaths,
    SERVICE_ID,
    TASK_ID,
)
from dcp_orchestrator.provenance import HistoryRefs


@contextmanager
def isolated_paths():
    with tempfile.TemporaryDirectory(prefix="dcp-orchestrator-tests-") as directory:
        with mock.patch.dict(os.environ, {f"{ENV_PREFIX}ROOT": directory}, clear=False):
            yield RuntimePaths.from_environment()


class SuccessWorker:
    def execute(self, cwd: Path) -> WorkerReceipt:
        marker = cwd / MARKER_RELATIVE
        marker.parent.mkdir()
        marker.write_bytes(MARKER_BYTES)
        return WorkerReceipt(41001, 0, "test-codex-worker", hashlib.sha256(b"ok").hexdigest())


class ExtraMutationWorker(SuccessWorker):
    def execute(self, cwd: Path) -> WorkerReceipt:
        receipt = super().execute(cwd)
        (cwd / "unexpected.txt").write_text("unsafe\n", encoding="utf-8")
        return receipt


class FailedWorker:
    def execute(self, cwd: Path) -> WorkerReceipt:
        return WorkerReceipt(41002, 3, "test-codex-worker", hashlib.sha256(b"failed").hexdigest())


class CanaryTests(unittest.TestCase):
    def test_identity_and_provider_neutral_default(self):
        self.assertEqual(PRODUCT_NAME, "DCP Orchestrator")
        self.assertEqual(BUNDLE_ID, "pro.devcontrol.dcp-orchestrator")
        self.assertEqual(PROCESS_ID, "dcp-orchestrator")
        self.assertEqual(SERVICE_ID, "pro.devcontrol.dcp-orchestrator.lab")
        self.assertEqual(IPC_NAMESPACE, "dcp-orchestrator")
        self.assertEqual(TASK_ID, "dcp-lab-canary-001")
        self.assertLessEqual(len(CANONICAL_PROMPT), 120)
        self.assertEqual(
            HistoryRefs().to_dict(),
            {
                "provider": "none",
                "session": None,
                "checkpoint": None,
                "commit": None,
                "digest": None,
                "url": None,
            },
        )

    def test_success_has_one_attempt_worker_and_cleanup_before_terminal(self):
        snapshots = []
        with isolated_paths() as paths:
            result = CanarySupervisor(paths, SuccessWorker(), snapshots.append).run()
            self.assertEqual(result["state"], "succeeded")
            self.assertEqual(result["task_id"], TASK_ID)
            self.assertEqual(result["card_count"], 1)
            self.assertEqual(result["attempt_count"], 1)
            self.assertEqual(result["worker_count"], 1)
            self.assertEqual(result["retry_count"], 0)
            self.assertEqual(
                [event["state"] for event in result["transitions"]],
                ["preparing", "running", "verifying", "cleaning", "succeeded"],
            )
            self.assertEqual(len(result["evidence_refs"]), 2)
            self.assertFalse(paths.worktrees.joinpath(result["run_id"]).exists())
            self.assertFalse(paths.locks.joinpath(f"{TASK_ID}.lock").exists())
            record_dir = paths.records / result["run_id"]
            terminal = json.loads((record_dir / "terminal-task.json").read_text())
            evidence = json.loads((record_dir / "evidence-manifest.json").read_text())
            self.assertEqual(terminal["state"], "succeeded")
            self.assertEqual(evidence["marker"]["byte_count"], 20)
            self.assertTrue(evidence["cleanup"]["marker_disappeared"])
            self.assertTrue(evidence["cleanup"]["worktree_removed"])
            self.assertTrue(evidence["cleanup"]["branch_removed"])
            self.assertFalse(evidence["operator_prompt_retained"])
            self.assertFalse(evidence["worker_transcript_retained"])
            self.assertEqual(snapshots[-1]["state"], "succeeded")
            self.assertEqual(len(snapshots[-1]["evidence_refs"]), 2)

    def test_worker_failure_is_truthful_and_cleanup_still_runs(self):
        with isolated_paths() as paths:
            result = CanarySupervisor(paths, FailedWorker()).run()
            self.assertEqual(result["state"], "failed")
            self.assertEqual(result["terminal_reason"], "worker_nonzero_exit")
            evidence_path = paths.records / result["run_id"] / "evidence-manifest.json"
            evidence = json.loads(evidence_path.read_text())
            self.assertTrue(evidence["cleanup"]["worktree_removed"])
            self.assertNotIn("marker", evidence)

    def test_extra_mutation_is_safety_violation(self):
        with isolated_paths() as paths:
            result = CanarySupervisor(paths, ExtraMutationWorker()).run()
            self.assertEqual(result["state"], "safety_violation")
            self.assertEqual(result["terminal_reason"], "mutation_set_outside_marker_allowlist")

    def test_cleanup_failure_cannot_be_reported_as_success(self):
        from dcp_orchestrator import canary as canary_module

        original_git = canary_module._git

        def fail_worktree_remove(*args, **kwargs):
            if args[:3] == ("worktree", "remove", "--force"):
                return subprocess.CompletedProcess(["git", *args], 1, b"", b"injected failure")
            return original_git(*args, **kwargs)

        with isolated_paths() as paths:
            with mock.patch.object(canary_module, "_git", side_effect=fail_worktree_remove):
                result = CanarySupervisor(paths, SuccessWorker()).run()
            self.assertEqual(result["state"], "cleanup_failed")
            self.assertEqual(result["terminal_reason"], "cleanup_incomplete")
            evidence = json.loads(
                (paths.records / result["run_id"] / "evidence-manifest.json").read_text()
            )
            self.assertIn("worktree_remove_failed", evidence["cleanup"]["errors"])

    def test_fake_canary_needs_no_outbound_network(self):
        with isolated_paths() as paths:
            with mock.patch.object(socket.socket, "connect", side_effect=AssertionError("network denied")):
                result = CanarySupervisor(paths, SuccessWorker()).run()
            self.assertEqual(result["state"], "succeeded")


if __name__ == "__main__":
    unittest.main()
