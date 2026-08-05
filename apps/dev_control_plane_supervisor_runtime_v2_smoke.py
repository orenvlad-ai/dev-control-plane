"""Fake-only smoke for the composed private-socket Supervisor runtime."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, replace
import hashlib
import json
import os
from pathlib import Path
import socket
import sqlite3
import stat
import sys
from tempfile import TemporaryDirectory
import threading
import time
from types import SimpleNamespace
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (SRC, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dev_control_plane.codex_app_server import (  # noqa: E402
    CHECKPOINT_SCHEMA_VERSION,
    CodexAmbiguousOutcomeError,
    CodexCheckpoint,
    CodexContractError,
    CodexDisconnectedError,
    CodexLifecycleEvent,
    CodexRemoteError,
    CodexThreadIdentity,
    CodexTurnResult,
)
from dev_control_plane.curator_delivery import (  # noqa: E402
    OWNER_ACTION_ATTESTATION_SCHEMA,
    OwnerAcceptanceSourceVerifier,
    OwnerActionAttestationVerifier,
    owner_action_attestation_signature,
    owner_acceptance_source_signature,
)
from dev_control_plane.orchestration_contracts import (  # noqa: E402
    AutonomyEnvelope,
    ArbiterDecision,
    Checkpoint,
    CuratorIdentity,
    DEV_CONTROL_PLANE_RELEASE_TARGET,
    DecisionStep,
    ExecutorIdentity,
    ReleaseClosureManifest,
    RevisionBinding,
    TaskPassport,
    TerminalEvidence,
    Workstream,
    contract_to_dict,
)
from dev_control_plane.supervisor import (  # noqa: E402
    ContourVerification,
    OwnerAcceptanceReceipt,
    SupervisorEngine,
    SupervisorError,
    stable_supervisor_id,
    terminal_contract_digest,
)
from dev_control_plane.supervisor_registry import (  # noqa: E402
    LeaseHeldError,
    LockConflict,
    RegistryValidationError,
    SupervisorRegistry,
)
from dev_control_plane.release_scheduler import (  # noqa: E402
    ReleaseCandidate as SchedulerReleaseCandidate,
)
from dev_control_plane.release_train import (  # noqa: E402
    ReleaseCandidate as ReleaseTrainCandidate,
)
from dev_control_plane.wb_core_release_adapter import (  # noqa: E402
    WB_CORE_REPOSITORY,
    WB_CORE_TARGET_ADAPTER,
    WbCoreAdmissionBinding,
    WbCoreAdmissionProof,
    derive_wb_core_target_task_id,
)
from dev_control_plane.supervisor_runtime import (  # noqa: E402
    COMMAND_CONTRACT,
    SecurityPermissionChangeRequiresOwner,
    SupervisorCommandClient,
    SupervisorCommandError,
    SupervisorCommandServer,
    SupervisorRuntime,
    SupervisorRuntimeLoop,
    default_socket_path,
)

NOW = "2026-08-05T08:00:00Z"


class FakeCodexState:
    def __init__(self, registry: SupervisorRegistry) -> None:
        self.registry = registry
        self.threads: dict[str, list[str]] = {}
        self.start_calls = 0
        self.resume_calls: list[str] = []
        self.turn_calls = 0
        self.lock_conflict_proven = False
        self.sqlite_tx_proven = False
        self.lock_snapshots: list[tuple[str, tuple[dict[str, Any], ...]]] = []
        self.completed_turns: dict[str, dict[str, CodexTurnResult]] = {}
        self.recovery_calls = 0
        self.snapshot_calls = 0
        self.required_start_epochs: list[int | None] = []


class FakeCodexClient:
    def __init__(self, shared: FakeCodexState, **kwargs: Any) -> None:
        assert kwargs["model"] == "gpt-5.6-sol"
        assert kwargs["reasoning_effort"] == "ultra"
        assert kwargs["sandbox"] == "workspace-write"
        assert kwargs["approval_policy"] == "never"
        assert Path(kwargs["codex_bin"]).is_absolute()
        self.shared = shared
        self.owned_thread_ids = tuple(kwargs["owned_thread_ids"])
        self.connection_epoch = 0
        self._fresh_empty_thread_epochs: dict[str, int] = {}

    def connect(self) -> Any:
        if self.connection_epoch == 0:
            self.connection_epoch = 1
        return object()

    @contextmanager
    def pin_connection_epoch(self, required_connection_epoch: int) -> Any:
        if required_connection_epoch != self.connection_epoch:
            raise CodexAmbiguousOutcomeError(
                "fake connection epoch changed before durable receipt"
            )
        yield

    def start_thread(
        self,
        *,
        cwd: str,
        ephemeral: bool,
        required_connection_epoch: int | None = None,
    ) -> CodexThreadIdentity:
        assert Path(cwd).is_dir() and ephemeral is False
        assert required_connection_epoch in {None, self.connection_epoch}
        self.shared.required_start_epochs.append(required_connection_epoch)
        self.shared.start_calls += 1
        thread_id = f"executor-thread-{self.shared.start_calls}"
        self.shared.threads[thread_id] = []
        self.owned_thread_ids = tuple(sorted(set(self.owned_thread_ids) | {thread_id}))
        self._fresh_empty_thread_epochs[thread_id] = self.connection_epoch
        return CodexThreadIdentity(thread_id, f"session-{thread_id}", "openai", "app-server", "idle", False)

    def resume_thread(self, thread_id: str) -> CodexThreadIdentity:
        if thread_id not in self.shared.threads:
            raise RuntimeError("unknown fake thread")
        self.shared.resume_calls.append(thread_id)
        self._fresh_empty_thread_epochs.pop(thread_id, None)
        return CodexThreadIdentity(thread_id, f"session-{thread_id}", "openai", "app-server", "idle", False)

    def fresh_empty_turn_baseline(self, thread_id: str) -> tuple[str, ...] | None:
        if self._fresh_empty_thread_epochs.get(thread_id) != self.connection_epoch:
            return None
        return ()

    def consume_fresh_empty_turn_baseline(
        self,
        thread_id: str,
        *,
        required_connection_epoch: int | None = None,
    ) -> None:
        if (
            required_connection_epoch != self.connection_epoch
            or self._fresh_empty_thread_epochs.get(thread_id) != self.connection_epoch
        ):
            raise CodexContractError("fake fresh-thread proof changed before CAS")
        self._fresh_empty_thread_epochs.pop(thread_id, None)

    def read_thread_snapshot(self, thread_id: str, *, include_turns: bool) -> Mapping[str, Any]:
        assert include_turns is True
        self.shared.snapshot_calls += 1
        return {"id": thread_id, "turns": [{"id": item} for item in self.shared.threads[thread_id]]}

    def recover_lost_turn_receipt(
        self,
        thread_id: str,
        *,
        baseline_turn_ids: list[str],
        output_contract: str,
        expected_task_id: str,
        expected_workstream_id: str,
    ) -> CodexTurnResult:
        self.shared.recovery_calls += 1
        baseline = set(baseline_turn_ids)
        new_turn_ids = [
            turn_id
            for turn_id in self.shared.threads[thread_id]
            if turn_id not in baseline
        ]
        if len(new_turn_ids) != 1:
            raise CodexAmbiguousOutcomeError("fake recovery is not unique")
        stored = self.shared.completed_turns.get(thread_id, {}).get(new_turn_ids[0])
        if stored is None:
            raise CodexContractError("fake persisted turn has no typed output")
        assert stored.contract.kind == output_contract
        assert stored.contract.task_id == expected_task_id
        assert stored.contract.workstream_id == expected_workstream_id
        events = (
            CodexLifecycleEvent(
                "item/completed",
                thread_id,
                stored.turn_id,
                f"item-{stored.turn_id}",
                "agentMessage",
                None,
                self.connection_epoch,
                "thread_read_snapshot",
            ),
            CodexLifecycleEvent(
                "turn/completed",
                thread_id,
                stored.turn_id,
                None,
                None,
                "completed",
                self.connection_epoch,
                "thread_read_snapshot",
            ),
        )
        return replace(stored, events=events)

    def run_turn(
        self,
        thread_id: str,
        prompt: str,
        *,
        output_contract: str,
        expected_task_id: str,
        expected_workstream_id: str,
        cwd: str,
        required_connection_epoch: int | None = None,
    ) -> CodexTurnResult:
        assert required_connection_epoch == self.connection_epoch
        self._fresh_empty_thread_epochs.pop(thread_id, None)
        assert output_contract == "checkpoint"
        assert (
            "ORCHESTRATOR_V2_BOUND_ENVELOPE" in prompt
            or "ORCHESTRATOR_V2_SUCCESSOR_PROOF" in prompt
        )
        # A second SQLite writer can start while the model call is active; no
        # Supervisor transaction is held across this wait.
        connection = sqlite3.connect(self.shared.registry.db_path, timeout=2)
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.rollback()
            self.shared.sqlite_tx_proven = True
        finally:
            connection.close()
        # The atomic task/resource reservation remains renewed beyond its short
        # initial TTL, so a release reservation cannot overlap the long turn.
        time.sleep(0.22)
        self.shared.lock_snapshots.append(("before-contention", self.shared.registry.inspect_locks()))
        fence = _current_fence_holder[0]
        try:
            self.shared.registry.acquire_scheduler_reservation(
                task_id=expected_task_id,
                workstream_id=expected_workstream_id,
                target_id="target-smoke",
                resources=("repo:runtime-smoke", "module:runtime"),
                fence=fence,
                ttl=1,
            )
        except LockConflict:
            self.shared.lock_conflict_proven = True
        else:
            raise AssertionError("release overlapped an active execution reservation")
        time.sleep(0.15)
        self.shared.lock_snapshots.append(("after-contention", self.shared.registry.inspect_locks()))
        self.shared.turn_calls += 1
        turn_id = f"turn-{self.shared.turn_calls}"
        self.shared.threads[thread_id].append(turn_id)
        checkpoint = CodexCheckpoint(
            schema_version=CHECKPOINT_SCHEMA_VERSION,
            kind="checkpoint",
            task_id=expected_task_id,
            workstream_id=expected_workstream_id,
            generation=1,
            stage="implementation",
            progress_percent=25,
            delta="Создана проверяемая fake-дельта.",
            current_action="Продолжается fake-only проверка.",
            evidence=("fake_app_server_typed_event",),
            causal_fingerprint=None,
        )
        result = CodexTurnResult(thread_id, turn_id, "completed", checkpoint, ())
        self.shared.completed_turns.setdefault(thread_id, {})[turn_id] = result
        return result

    def shutdown(self) -> None:
        return None


class AmbiguousInitialCodexClient(FakeCodexClient):
    def start_thread(
        self,
        *,
        cwd: str,
        ephemeral: bool,
        required_connection_epoch: int | None = None,
    ) -> CodexThreadIdentity:
        super().start_thread(
            cwd=cwd,
            ephemeral=ephemeral,
            required_connection_epoch=required_connection_epoch,
        )
        raise CodexDisconnectedError(
            "fake disconnect after initial thread/start acceptance"
        )


class FailingTurnCodexClient(FakeCodexClient):
    def run_turn(self, *_args: Any, **_kwargs: Any) -> CodexTurnResult:
        self.shared.turn_calls += 1
        raise RuntimeError("fake bounded canary transport failure")


class EmptyThreadReadRejectedCodexClient(FakeCodexClient):
    """Match current App Server: an empty new thread has no stored rollout yet."""

    def read_thread_snapshot(self, thread_id: str, *, include_turns: bool) -> Mapping[str, Any]:
        if not self.shared.threads[thread_id]:
            self.shared.snapshot_calls += 1
            raise CodexRemoteError("thread/read", -32600, "empty thread is not persisted")
        return super().read_thread_snapshot(thread_id, include_turns=include_turns)

    def run_turn(self, thread_id: str, *args: Any, **kwargs: Any) -> CodexTurnResult:
        inflight = self.shared.registry.list_outbox_records(
            kinds=("codex_followup",),
            states=("inflight",),
        )
        assert len(inflight) == 1
        intent = inflight[0]["payload"]["call_intent"]
        assert intent is not None
        if self.shared.turn_calls == 0:
            assert intent["baseline_turn_ids"] == []
        assert inflight[0]["payload"]["model_attempt_count"] == 1
        return super().run_turn(thread_id, *args, **kwargs)


class EmptyThreadReadRejectedFailingTurnCodexClient(EmptyThreadReadRejectedCodexClient):
    def run_turn(self, thread_id: str, *args: Any, **kwargs: Any) -> CodexTurnResult:
        inflight = self.shared.registry.list_outbox_records(
            kinds=("codex_followup",),
            states=("inflight",),
        )
        assert len(inflight) == 1
        assert inflight[0]["payload"]["call_intent"]["baseline_turn_ids"] == []
        assert inflight[0]["payload"]["model_attempt_count"] == 1
        self._fresh_empty_thread_epochs.pop(thread_id, None)
        self.shared.turn_calls += 1
        raise RuntimeError("fake bounded canary transport failure")


class SimulatedRuntimeCrash(BaseException):
    pass


class SameConnectionCrashOnceCodexClient(FakeCodexClient):
    """Model one lost receipt without replacing the owned App Server child."""

    def __init__(self, shared: FakeCodexState, **kwargs: Any) -> None:
        super().__init__(shared, **kwargs)
        self.tainted_thread_ids: set[str] = set()
        self._crashed_once = False

    def resume_thread(self, thread_id: str) -> CodexThreadIdentity:
        identity = super().resume_thread(thread_id)
        self.tainted_thread_ids.discard(thread_id)
        return identity

    def recover_lost_turn_receipt(self, *args: Any, **kwargs: Any) -> CodexTurnResult:
        result = super().recover_lost_turn_receipt(*args, **kwargs)
        self.tainted_thread_ids.discard(result.thread_id)
        return result

    def run_turn(self, thread_id: str, *args: Any, **kwargs: Any) -> CodexTurnResult:
        if thread_id in self.tainted_thread_ids:
            raise CodexContractError("fake recovered thread remained tainted")
        result = super().run_turn(thread_id, *args, **kwargs)
        if not self._crashed_once:
            self._crashed_once = True
            self.tainted_thread_ids.add(thread_id)
            raise SimulatedRuntimeCrash(
                "fake same-connection exit after model success before receipt"
            )
        return result


class CrashAfterSuccessfulTurnCodexClient(FakeCodexClient):
    def run_turn(self, *args: Any, **kwargs: Any) -> CodexTurnResult:
        super().run_turn(*args, **kwargs)
        raise SimulatedRuntimeCrash("fake process exit after model success before receipt")


class MalformedRecoveryCodexClient(FakeCodexClient):
    def recover_lost_turn_receipt(self, *_args: Any, **_kwargs: Any) -> CodexTurnResult:
        self.shared.recovery_calls += 1
        raise CodexContractError("fake malformed persisted schema-bound output")


_current_fence_holder: list[Any] = []


def main() -> None:
    with TemporaryDirectory(prefix="dcpv2-runtime-", dir="/tmp") as raw:
        root = Path(raw)
        workspace = root / "managed"
        workspace.mkdir()
        task_workspace = workspace / "runtime-task"
        task_workspace.mkdir()
        registry = SupervisorRegistry(root / "state" / "supervisor.sqlite3", lease_seconds=2)
        fence = registry.acquire_generation("runtime-smoke-generation-1")
        _current_fence_holder[:] = [fence]
        shared = FakeCodexState(registry)
        runtime = _runtime(registry, fence, workspace, shared)
        server = SupervisorCommandServer(runtime, default_socket_path(root / "state"))
        server.start()
        assert runtime.readiness()["ready"] is True
        socket_path = default_socket_path(root / "state")
        metadata = socket_path.lstat()
        assert stat.S_ISSOCK(metadata.st_mode) and stat.S_IMODE(metadata.st_mode) == 0o600
        client = SupervisorCommandClient(socket_path)

        passport, workstream = _contracts()
        queued = client.request(
            "start_executor",
            {
                "passport": contract_to_dict(passport),
                "workstream": contract_to_dict(workstream),
                "cwd": str(task_workspace),
                "message_id": "runtime-start-message",
            },
            request_id="runtime-start-request",
        )
        assert queued["queued"] is True
        replayed_start = client.request(
            "start_executor",
            {
                "passport": contract_to_dict(passport),
                "workstream": contract_to_dict(workstream),
                "cwd": str(task_workspace),
                "message_id": "runtime-start-message",
            },
            request_id="runtime-start-replay-request",
        )
        assert replayed_start["queued"] is False
        other_workspace = workspace / "other-start"
        other_workspace.mkdir()
        try:
            client.request(
                "start_executor",
                {
                    "passport": contract_to_dict(passport),
                    "workstream": contract_to_dict(workstream),
                    "cwd": str(other_workspace),
                    "message_id": "runtime-start-message",
                },
                request_id="runtime-start-conflict-request",
            )
        except SupervisorCommandError:
            pass
        else:
            raise AssertionError("conflicting start orphaned a second workspace binding")
        binding = registry.get_workspace_binding(
            passport.task_id, workstream.workstream_id
        )
        assert binding is not None and binding["canonical_path"] == str(task_workspace.resolve())
        started = runtime.process_codex_once()
        assert started.status == "registered" and shared.start_calls == 1
        executor = registry.current_executor(passport.task_id, workstream.workstream_id)
        assert executor is not None and executor.model == "gpt-5.6-sol" and executor.reasoning == "ultra"
        assert runtime._codex_client is not None
        resume_count = len(shared.resume_calls)
        runtime._codex_client.connection_epoch += 1
        assert runtime.resume_owned_threads() == (executor.thread_id,)
        assert len(shared.resume_calls) == resume_count + 1

        swapped_workspace = workspace / "other-task"
        swapped_workspace.mkdir()
        registry.bind_workspace(
            task_id="other-runtime-task",
            workstream_id="other-runtime-workstream",
            canonical_path=str(swapped_workspace.resolve()),
            fence=fence,
        )
        for forbidden_cwd in (str(swapped_workspace), str(ROOT)):
            try:
                client.request(
                    "codex_followup",
                    {
                        "task_id": passport.task_id,
                        "workstream_id": workstream.workstream_id,
                        "prompt": "This cross-workspace call must fail.",
                        "output_contract": "checkpoint",
                        "cwd": forbidden_cwd,
                        "terminal_context": None,
                        "call_policy": "standard",
                        "message_id": "forbidden-cwd-" + hashlib.sha256(forbidden_cwd.encode()).hexdigest()[:12],
                    },
                    request_id="forbidden-cwd-request-" + hashlib.sha256(forbidden_cwd.encode()).hexdigest()[:12],
                )
            except SupervisorCommandError:
                pass
            else:
                raise AssertionError("cross-task or original-checkout cwd was accepted")

        client.request(
            "codex_followup",
            {
                "task_id": passport.task_id,
                "workstream_id": workstream.workstream_id,
                "prompt": "Сделай bounded fake checkpoint.",
                "output_contract": "checkpoint",
                "cwd": str(task_workspace),
                "terminal_context": None,
                "call_policy": "standard",
                "message_id": "runtime-followup-message",
            },
            request_id="runtime-followup-request",
        )
        followed = runtime.process_codex_once()
        assert followed.status == "delivered" and shared.turn_calls == 1, (
            followed,
            shared.turn_calls,
            registry.list_events(task_id=passport.task_id),
            shared.lock_snapshots,
        )
        assert shared.sqlite_tx_proven and shared.lock_conflict_proven
        checkpoint_events = registry.list_events(
            task_id=passport.task_id,
            workstream_id=workstream.workstream_id,
            event_types=("checkpoint",),
        )
        assert checkpoint_events[-1]["payload"]["contract"]["progress_stage"] == 25
        assert not registry.inspect_locks()

        # Unknown/malformed frames are rejected without mutating the registry.
        try:
            client.request("unknown_command", {}, request_id="unknown-command-request")
        except SupervisorCommandError:
            pass
        else:
            raise AssertionError("unknown private command was accepted")
        raw_client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        raw_client.connect(str(socket_path))
        raw_client.sendall(json.dumps({"contract": COMMAND_CONTRACT}).encode() + b"\n")
        rejected = json.loads(raw_client.makefile("rb").readline())
        raw_client.close()
        assert rejected["ok"] is False

        # A live generation cannot be replaced.
        try:
            registry.acquire_generation("forged-second-generation")
        except LeaseHeldError:
            pass
        else:
            raise AssertionError("second Supervisor generation was admitted")

        server.stop()
        runtime.close()
        registry.release_generation(fence)
        restart_fence = registry.acquire_generation("runtime-smoke-generation-2")
        _current_fence_holder[:] = [restart_fence]
        restarted = _runtime(registry, restart_fence, workspace, shared)
        resumed = restarted.resume_owned_threads()
        assert resumed == (executor.thread_id,) and executor.thread_id in shared.resume_calls
        assert shared.start_calls == 1
        restarted.close()
        registry.release_generation(restart_fence)

    _lease_starvation_smoke()
    _owner_source_attestation_smoke()
    _multi_workstream_owner_attestation_smoke()
    _qualification_evidence_smoke()
    _fresh_empty_thread_baseline_smoke()
    _single_attempt_canary_failure_smoke()
    _split_canary_failure_recovery_smoke()
    _lost_receipt_recovery_smoke()
    _partial_result_receipt_recovery_smoke()
    _partial_result_invalid_intent_smoke()
    _same_connection_lost_receipt_taint_smoke()
    _attention_receipt_restart_smoke()
    _release_orchestration_smoke()
    _release_all_wait_refresh_restart_smoke()
    _multi_workstream_multi_pr_restart_smoke()
    _release_resolution_merged_race_smoke()
    _release_protected_human_gate_smoke()
    _release_wait_refresh_smoke()
    _release_nonterminal_observation_smoke()
    _release_wait_then_failure_budget_smoke()
    _release_readmission_smoke()
    _release_incident_smoke()
    _release_incident_crash_reconcile_smoke()
    _anti_loop_successor_cause_smoke()
    _corrective_generation_recovery_smoke()
    _preactivation_structural_repair_smoke()
    _unbound_start_reconciliation_restart_smoke()
    _sibling_parking_isolation_restart_smoke()
    _manifest_revision_lock_smoke()
    _target_lane_closure_smoke()
    _wb_core_parked_admission_closure_smoke()
    print("dev-control-plane-supervisor-runtime-v2-smoke passed")


class FakeReleaseWorkers:
    def __init__(self, *, fail_release: bool = False) -> None:
        self.fail_release = fail_release
        self.resolver_calls = 0
        self.release_calls = 0
        self.release_arbiter_calls = 0
        self.incident_arbiter_calls = 0
        self.application_calls = 0
        self.actual_files: dict[str, tuple[str, ...]] = {}
        self.merged_heads: set[str] = set()
        self.merge_commit_shas: dict[str, str] = {}
        self.pr_numbers: dict[str, int] = {}
        self.required_checks: dict[str, tuple[str, ...]] = {}
        self.blocked_heads: set[str] = set()
        self.protected_heads: set[str] = set()
        self.truth_head_override: str | None = None
        self.truth_task_revision_override: int | None = None
        self.contours: dict[str, str] = {}
        self.release_plan_wait_after_first = False
        self.release_plan_all_wait = False
        self.release_observations: list[tuple[str, str | None, float | None]] = []
        self.merged_on_remediation = False

    def resolver(self, payload: Mapping[str, Any], guard: Any) -> Mapping[str, Any]:
        candidate = payload["candidate"]
        guard.checkpoint()
        self.resolver_calls += 1
        files = self.actual_files[str(candidate["pr_head_sha"])]
        merged = str(candidate["pr_head_sha"]) in self.merged_heads or (
            self.merged_on_remediation and bool(payload.get("remediation_decision_id"))
        )
        if not merged and str(candidate["pr_head_sha"]) in self.protected_heads:
            raise SecurityPermissionChangeRequiresOwner(
                expected_head_sha=str(candidate["pr_head_sha"]),
                evidence=("protected_controller_diff", "open_pr_readback"),
            )
        return {
            "release_candidate": {
                "lane_id": candidate["logical_lane_id"],
                "task_id": candidate["task_id"],
                "workstream_id": candidate["workstream_id"],
                "revision": candidate["task_revision"],
                "repo": "orenvlad-ai/dev-control-plane",
                "pr_number": self.pr_numbers.get(
                    str(candidate["pr_head_sha"]), self.resolver_calls
                ),
                "expected_head_sha": candidate["pr_head_sha"],
                "base_ref": "main",
                "required_checks": list(
                    self.required_checks.get(
                        str(candidate["pr_head_sha"]), ("v2-suite",)
                    )
                ),
                "declared_files": candidate["passport_files"],
                "resources": candidate["resources"],
                "multi_pr": candidate["multi_pr_intent"],
            },
            "target_adapter": "dev-control-plane-hosted-v2",
            "scheduler_truth": {
                "task_revision": self.truth_task_revision_override or candidate["task_revision"],
                "workstream_revision": candidate["workstream_revision"],
                "pr_head_sha": self.truth_head_override or candidate["pr_head_sha"],
                "target_id": candidate["target_id"],
                "pr_state": "MERGED" if merged else "OPEN",
                "merge_commit_sha": (
                    self.merge_commit_shas.get(
                        str(candidate["pr_head_sha"]), "9" * 40
                    )
                    if merged
                    else None
                ),
                "diff_files": list(files),
                "checks_green": str(candidate["pr_head_sha"]) not in self.blocked_heads,
                "admission_ready": (
                    False
                    if merged
                    else str(candidate["pr_head_sha"]) not in self.blocked_heads
                ),
                "merge_conflict": False,
                "passport_diff_mismatch": not set(files).issubset(set(candidate["passport_files"])),
                "unknown_classification": False,
            },
        }

    def release(self, payload: Mapping[str, Any], guard: Any) -> Mapping[str, Any]:
        guard.checkpoint()
        self.release_calls += 1
        if self.fail_release:
            raise RuntimeError("stable fake release failure")
        guard.checkpoint()
        candidate = payload["candidate"]
        contour = self.contours.get(str(candidate["task_id"]), "release:production")
        merge_sha = hashlib.sha256(f"merge-{self.release_calls}".encode()).hexdigest()[:40]
        if self.release_observations:
            status, observed_head, retry_after = self.release_observations.pop(0)
            return {
                "schema": "dev-control-plane/release-action-observation/v2",
                "status": status,
                "reason_code": f"fake_{status}",
                "candidate_id": candidate["candidate_id"],
                "task_id": candidate["task_id"],
                "workstream_id": candidate["workstream_id"],
                "task_revision": candidate["task_revision"],
                "workstream_revision": candidate["workstream_revision"],
                "expected_head_sha": candidate["pr_head_sha"],
                "observed_head_sha": observed_head or candidate["pr_head_sha"],
                "retry_after_seconds": retry_after,
                "observed_at": NOW,
                "evidence": [f"fake:{status}"],
                "admission_binding": None,
            }
        return {
            "schema": "dev-control-plane/release-action-receipt/v2",
            "status": "passed",
            "candidate_id": candidate["candidate_id"],
            "task_id": candidate["task_id"],
            "workstream_id": candidate["workstream_id"],
            "task_revision": candidate["task_revision"],
            "workstream_revision": candidate["workstream_revision"],
            "pr_head_sha": candidate["pr_head_sha"],
            "pr_url": f"https://github.com/orenvlad-ai/dev-control-plane/pull/{self.release_calls}",
            "merge_sha": merge_sha,
            "contour": contour,
            "deploy_identity": (
                "hosted-release-v1:wb-core-eu-root:devcontrol.pro:" + merge_sha
                if contour == "release:production"
                else None
            ),
            "verification_identity": f"fake-verify:{self.release_calls}",
            "admission_binding": None,
            "completed_at": NOW,
        }

    def release_arbiter(self, payload: Mapping[str, Any], guard: Any) -> ArbiterDecision:
        guard.checkpoint()
        self.release_arbiter_calls += 1
        semantic = payload["semantic_case"]
        candidates = sorted(semantic["candidates"], key=lambda item: item["candidate_id"])
        bindings = tuple(_binding(item) for item in candidates)
        steps = tuple(
            DecisionStep(
                step_id=f"release-step-{index}",
                action=(
                    "wait"
                    if self.release_plan_all_wait
                    or (self.release_plan_wait_after_first and index > 1)
                    else "release"
                ),
                task_id=item["task_id"],
                workstream_id=item["workstream_id"],
                depends_on=() if index == 1 else (f"release-step-{index - 1}",),
            )
            for index, item in enumerate(candidates, start=1)
        )
        return ArbiterDecision(
            decision_id=f"release-decision-{self.release_arbiter_calls}",
            kind="release_plan",
            case_id=semantic["case_id"],
            case_digest=semantic["case_digest"],
            bindings=bindings,
            steps=steps,
            model="gpt-5.6-sol",
            reasoning="ultra",
            created_at=NOW,
        )

    def incident_arbiter(self, payload: Mapping[str, Any], guard: Any) -> ArbiterDecision:
        guard.checkpoint()
        self.incident_arbiter_calls += 1
        binding = payload["binding"]
        return ArbiterDecision(
            decision_id=f"incident-decision-{self.incident_arbiter_calls}",
            kind="incident",
            case_id=payload["case_id"],
            case_digest=payload["case_digest"],
            bindings=(RevisionBinding(
                task_id=binding["task_id"],
                task_revision=binding["task_revision"],
                workstream_id=binding["workstream_id"],
                workstream_revision=binding["workstream_revision"],
                pr_head_sha=binding["pr_head_sha"],
                resources=tuple(binding["resources"]),
            ),),
            steps=(DecisionStep(
                step_id="verify-release-once",
                action="verify",
                task_id=binding["task_id"],
                workstream_id=binding["workstream_id"],
            ),),
            model="gpt-5.6-sol",
            reasoning="ultra",
            created_at=NOW,
        )

    def application(self, payload: Mapping[str, Any], guard: Any) -> Mapping[str, Any]:
        guard.checkpoint()
        self.application_calls += 1
        guard.checkpoint()
        remediation = payload.get("remediation")
        schema = remediation.get("schema") if isinstance(remediation, Mapping) else None
        disposition = (
            "dispatch_release_once"
            if schema == "dev-control-plane/release-incident-remediation/v2"
            else "dispatch_target_lane_once"
            if schema == "dev-control-plane/target-lane-incident-remediation/v2"
            else "park"
        )
        return {
            "schema": "dev-control-plane/incident-application-disposition/v2",
            "applied": True,
            "disposition": disposition,
            "verification_identity": f"fake-independent-verification:{self.application_calls}",
        }


class FakeTargetLaneClosure:
    def __init__(self, statuses: list[str], *, fail: bool = False) -> None:
        self.statuses = list(statuses)
        self.fail = fail
        self.calls: list[dict[str, Any]] = []

    def __call__(self, payload: Mapping[str, Any], guard: Any) -> Mapping[str, Any]:
        guard.checkpoint()
        self.calls.append(dict(payload))
        guard.checkpoint()
        if self.fail:
            raise RuntimeError("stable target lane closure failure")
        status = self.statuses.pop(0)
        if status == "error":
            raise RuntimeError("stable target lane closure failure")
        return {
            "schema": "dev-control-plane/target-lane-closure-receipt/v2",
            "status": status,
            "closure_id": payload["closure_id"],
            "supervisor_generation": payload["supervisor_generation"],
            "task_id": payload["task_id"],
            "task_revision": payload["task_revision"],
            "workstream_id": payload["workstream_id"],
            "workstream_revision": payload["workstream_revision"],
            "target_id": payload["target_id"],
            "logical_lane_id": payload["logical_lane_id"],
            "outcome": payload["outcome"],
            "closure_event_id": payload["closure_event_id"],
            "closure_event_digest": payload["closure_event_digest"],
            "reason_code": f"fake_{status}",
            "evidence_digest": hashlib.sha256(
                f"{payload['closure_id']}:{status}:{len(self.calls)}".encode()
            ).hexdigest(),
            "retry_after_seconds": 1.0 if status == "submitted" else None,
            "observed_at": NOW,
        }


def _multi_workstream_owner_attestation_smoke() -> None:
    with TemporaryDirectory(prefix="dcpv2-owner-multi-", dir="/tmp") as raw:
        root = Path(raw)
        workspace = root / "managed"
        workspace.mkdir()
        registry = SupervisorRegistry(root / "supervisor.sqlite3", lease_seconds=30)
        fence = registry.acquire_generation("owner-multi-generation")
        current_terminal: list[TerminalEvidence] = []

        def verifier(_passport: TaskPassport, terminal: TerminalEvidence) -> ContourVerification:
            current_terminal[:] = [terminal]
            return ContourVerification(
                verification_id=f"verification-{terminal.workstream_id}",
                task_id=terminal.task_id,
                workstream_id=terminal.workstream_id,
                task_revision=terminal.task_revision,
                workstream_revision=terminal.workstream_revision,
                contour=terminal.closure_kind,
                terminal_digest=terminal_contract_digest(terminal),
                source="diagnostic_verifier",
                passed=True,
                checks=("diagnostic:passed",),
                evidence=("diagnostic:independent",),
                verified_at=NOW,
            )

        engine = SupervisorEngine(
            registry,
            fence,
            supervisor_id="owner-multi-supervisor",
            contour_verifier=verifier,
        )
        executors = (
            ExecutorIdentity("owner-multi-thread-one", "mac-local", "gpt-5.6-sol", "ultra"),
            ExecutorIdentity("owner-multi-thread-two", "mac-local", "gpt-5.6-sol", "ultra"),
        )
        passport = TaskPassport(
            task_id="owner-multi-task",
            revision=1,
            title="Multi owner barrier",
            objective="Prove exact task-level acceptance barrier.",
            expected_result="One exact delivered attention.",
            contour="diagnostic",
            included_scope=("two streams",),
            excluded_scope=("live work",),
            constraints=("fake only",),
            acceptance=("exact owner reply",),
            closure=("all streams terminal",),
            autonomy=AutonomyEnvelope(
                allowed_actions=("codex_workspace_mutation",),
                prohibited_actions=("target_release_command",),
                human_gate_reasons=("platform_hard_stop",),
            ),
            workstream_ids=("owner-multi-one", "owner-multi-two"),
            release_manifest=None,
            resources=("module:owner-one", "module:owner-two"),
            modules=("module:owner-one", "module:owner-two"),
            files=("src/owner_one.py", "src/owner_two.py"),
            dependencies=(),
            multi_pr_intent=False,
            multi_deploy_intent=False,
            curator=CuratorIdentity("owner-multi-curator", "desktop-host"),
            executor=None,
            created_at=NOW,
        )
        streams: list[Workstream] = []
        for index, executor in enumerate(executors, start=1):
            stream = Workstream(
                workstream_id=f"owner-multi-{'one' if index == 1 else 'two'}",
                task_id=passport.task_id,
                revision=1,
                generation=1,
                root_workstream_id=f"owner-multi-{'one' if index == 1 else 'two'}",
                corrective_of_generation=None,
                title=f"Owner stream {index}",
                objective=passport.objective,
                state="working",
                executor=executor,
                resources=(f"module:owner-{'one' if index == 1 else 'two'}",),
                dependencies=(),
                created_at=NOW,
            )
            streams.append(stream)
            engine.register(passport, stream, message_id=f"owner-multi-register-{index}")
            terminal = TerminalEvidence(
                terminal_id=f"owner-multi-terminal-{index}",
                event_id=f"owner-multi-terminal-event-{index}",
                task_id=passport.task_id,
                task_revision=1,
                workstream_id=stream.workstream_id,
                workstream_revision=1,
                executor_generation=1,
                executor=executor,
                closure_kind="diagnostic",
                summary_ru=f"Поток {index} завершён.",
                evidence=(f"diagnostic:evidence-{index}",),
                checks=("diagnostic:passed",),
                pr_identities=(),
                deploy_identities=(),
                owner_acceptance_required=True,
                created_at=NOW,
            )
            engine.import_terminal(terminal, message_id=f"owner-multi-terminal-message-{index}")

        attention = registry.list_outbox_records(kinds=("curator_attention",))
        assert len(attention) == 1
        attention_event_id = attention[0]["event_id"]
        claimed = registry.claim_outbox(
            fence,
            worker_id="owner-multi-delivery",
            limit=1,
            visibility_timeout=30,
            kinds=("curator_attention",),
        )
        registry.ack_outbox(claimed[0].event_id, claimed[0].claim_token, fence)
        # A later stale/non-barrier terminal proves the runtime does not use
        # chronological `terminals[-1]` as the acceptance authority.
        registry.append_event(
            "owner-multi-stale-terminal",
            "technical_terminal",
            {
                "contract": {"task_revision": 999, "workstream_revision": 999},
                "closure_barrier": False,
                "curator_event_id": "",
            },
            fence,
            task_id=passport.task_id,
            workstream_id=streams[0].workstream_id,
            executor_generation=1,
        )
        key_path = root / "owner.key"
        key = b"owner-multi-attestation-key-material-32-bytes"
        key_path.write_bytes(key)
        key_path.chmod(0o600)
        workers = FakeReleaseWorkers()
        runtime = SupervisorRuntime(
            engine,
            allowed_workspace_root=workspace,
            codex_bin="/usr/bin/true",
            release_executor=workers.release,
            release_candidate_resolver=workers.resolver,
            release_arbiter_executor=workers.release_arbiter,
            incident_arbiter_executor=workers.incident_arbiter,
            incident_application_executor=workers.application,
            target_lane_closure_executor=lambda _payload, guard: _unused_lane_closure(guard),
            owner_acceptance_verifier=OwnerAcceptanceSourceVerifier(key_path),
        )
        receipt = OwnerAcceptanceReceipt(
            receipt_id="owner-multi-receipt",
            task_id=passport.task_id,
            task_revision=1,
            curator_thread_id=passport.curator.thread_id,
            reply="Задача принята",
            created_at=NOW,
        )
        attestation = {
            "schema": "dev-control-plane/owner-acceptance-source/v2",
            "curator_thread_id": receipt.curator_thread_id,
            "source_message_id": "owner-multi-source-message",
            "attention_event_id": attention_event_id,
            "observed_at_epoch": time.time(),
            "reply_sha256": hashlib.sha256(receipt.reply.encode()).hexdigest(),
            "signature": "",
        }
        attestation["signature"] = owner_acceptance_source_signature(key, receipt, attestation)
        result = runtime.handle_command(
            {
                "contract": COMMAND_CONTRACT,
                "command": "owner_acceptance",
                "request_id": "owner-multi-accept-request",
                "payload": {
                    "receipt": asdict(receipt),
                    "source_attestation": attestation,
                    "message_id": "owner-multi-accept-message",
                },
            }
        )["result"]
        assert result["accepted"] is True and registry.get_task(passport.task_id).state == "accepted"
        runtime.close()
        registry.release_generation(fence)


def _qualification_evidence_smoke() -> None:
    with TemporaryDirectory(prefix="dcpv2-qualification-", dir="/tmp") as raw:
        root = Path(raw)
        workspace = root / "managed"
        workspace.mkdir()
        registry = SupervisorRegistry(root / "state" / "supervisor.sqlite3", lease_seconds=30)
        fence = registry.acquire_generation("qualification-generation")

        def verifier(_passport: TaskPassport, terminal: TerminalEvidence) -> ContourVerification:
            return ContourVerification(
                verification_id="qualification-verification",
                task_id=terminal.task_id,
                workstream_id=terminal.workstream_id,
                task_revision=terminal.task_revision,
                workstream_revision=terminal.workstream_revision,
                contour=terminal.closure_kind,
                terminal_digest=terminal_contract_digest(terminal),
                source="diagnostic_verifier",
                passed=True,
                checks=("qualification:passed",),
                evidence=("qualification:independent",),
                verified_at=NOW,
            )

        engine = SupervisorEngine(
            registry,
            fence,
            supervisor_id="qualification-supervisor",
            contour_verifier=verifier,
        )
        executor = ExecutorIdentity("qualification-thread", "mac-local", "gpt-5.6-sol", "ultra")
        release_sha = "e" * 40
        passport = TaskPassport(
            task_id="qualification-task",
            revision=1,
            title="Qualification pilot",
            objective="Prove direct runtime qualification evidence.",
            expected_result="One exact nonterminal App Server checkpoint turn.",
            contour="diagnostic",
            included_scope=("pilot",),
            excluded_scope=("live mutation",),
            constraints=("one model call",),
            acceptance=("typed evidence passed",),
            closure=("final attention deferred until post-cutover proof",),
            autonomy=AutonomyEnvelope(
                allowed_actions=("codex_workspace_mutation",),
                prohibited_actions=("target_release_command",),
                human_gate_reasons=("platform_hard_stop",),
            ),
            workstream_ids=("qualification-workstream",),
            release_manifest=None,
            resources=("module:qualification", f"qualification:{release_sha}"),
            modules=("module:qualification",),
            files=("src/qualification.py",),
            dependencies=(),
            multi_pr_intent=False,
            multi_deploy_intent=False,
            curator=CuratorIdentity("qualification-curator", "desktop-host"),
            executor=executor,
            created_at=NOW,
        )
        stream = Workstream(
            workstream_id="qualification-workstream",
            task_id=passport.task_id,
            revision=1,
            generation=1,
            root_workstream_id="qualification-workstream",
            corrective_of_generation=None,
            title="Qualification workstream",
            objective=passport.objective,
            state="working",
            executor=executor,
            resources=passport.resources,
            dependencies=(),
            created_at=NOW,
        )
        engine.register(passport, stream, message_id="qualification-register")
        checkpoint = Checkpoint(
            checkpoint_id="qualification-checkpoint",
            event_id="qualification-checkpoint-event",
            task_id=passport.task_id,
            task_revision=1,
            workstream_id=stream.workstream_id,
            workstream_revision=1,
            executor_generation=1,
            executor=executor,
            progress_stage=40,
            delta_ru="Получен один schema-bound checkpoint.",
            current_ru="Финальный attention отложен до post-cutover proof.",
            evidence=("qualification:checkpoint",),
            created_at=NOW,
        )
        engine.import_checkpoint(checkpoint, message_id="qualification-checkpoint-message")
        pilot_workspace = workspace / "qualification-task"
        pilot_workspace.mkdir()
        registry.bind_workspace(
            task_id=passport.task_id,
            workstream_id=stream.workstream_id,
            canonical_path=str(pilot_workspace.resolve()),
            fence=fence,
        )
        registry.accept_inbox_and_enqueue(
            message_id="qualification-followup-message",
            source="qualification-smoke",
            inbox_payload={"kind": "single_attempt_canary"},
            outbox_event_id="qualification-followup-event",
            outbox_kind="codex_followup",
            outbox_payload={
                "schema": "dev-control-plane/codex-followup/v2",
                "task_id": passport.task_id,
                "task_revision": 1,
                "workstream_id": stream.workstream_id,
                "workstream_revision": 1,
                "executor_generation": 1,
                "thread_id": executor.thread_id,
                "host_id": executor.host_id,
                "model": executor.model,
                "reasoning": executor.reasoning,
                "prompt": "One bounded qualification checkpoint.",
                "output_contract": "checkpoint",
                "cwd": str(pilot_workspace.resolve()),
                "terminal_context": None,
                "causal_fingerprint": None,
                "causal_binding": None,
                "call_intent": {
                    "supervisor_generation": fence.generation,
                    "started_at": NOW,
                    "baseline_turn_ids": [],
                },
                "call_policy": "single_attempt_canary",
                "model_attempt_count": 1,
                "message_id": "qualification-followup-message",
            },
            fence=fence,
            task_id=passport.task_id,
        )
        attempted = registry.claim_outbox(
            fence,
            worker_id="qualification-smoke-worker",
            limit=1,
            visibility_timeout=30,
            kinds=("codex_followup",),
        )
        assert len(attempted) == 1
        registry.ack_outbox(attempted[0].event_id, attempted[0].claim_token, fence)
        registry.append_event(
            "qualification-old-turn-receipt",
            "codex_turn_receipt",
            {
                "schema": "dev-control-plane/codex-turn-receipt/v2",
                "output_contract": "checkpoint",
                "model_attempt_count": 1,
                "model_call_count": 1,
                "supervisor_generation": max(0, fence.generation - 1),
                "task_revision": 1,
                "workstream_revision": 1,
            },
            fence,
            task_id=passport.task_id,
            workstream_id=stream.workstream_id,
            executor_generation=1,
        )
        qualification_receipt_payload = {
                "schema": "dev-control-plane/codex-turn-receipt/v2",
                "followup_event_id": "qualification-followup-event",
                "contract_event_id": checkpoint.event_id,
                "contract_digest": hashlib.sha256(json.dumps(contract_to_dict(checkpoint), sort_keys=True).encode()).hexdigest(),
                "output_contract": "checkpoint",
                "thread_id": executor.thread_id,
                "turn_id": "qualification-turn",
                "turn_status": "completed",
                "lifecycle_event_count": 4,
                "lifecycle_digest": "a" * 64,
                "lifecycle_methods": ["item/completed", "turn/completed", "turn/started"],
                "item_ids": ["qualification-item"],
                "terminal_turn_ids": ["qualification-turn"],
                "model_attempt_count": 1,
                "model_call_count": 1,
                "receipt_source": "live_notification",
                "call_policy": "single_attempt_canary",
                "transport": "stdio",
                "websocket_used": False,
                "binary": str(Path("/usr/bin/true").resolve()),
                "model": "gpt-5.6-sol",
                "reasoning": "ultra",
                "supervisor_generation": fence.generation,
                "task_revision": 1,
                "workstream_revision": 1,
                "executor_generation": 1,
                "created_at": NOW,
            }
        registry.append_event(
            "qualification-turn-receipt",
            "codex_turn_receipt",
            qualification_receipt_payload,
            fence,
            task_id=passport.task_id,
            workstream_id=stream.workstream_id,
            executor_generation=1,
        )
        workers = FakeReleaseWorkers()
        runtime = SupervisorRuntime(
            engine,
            allowed_workspace_root=workspace,
            codex_bin="/usr/bin/true",
            release_executor=workers.release,
            release_candidate_resolver=workers.resolver,
            release_arbiter_executor=workers.release_arbiter,
            incident_arbiter_executor=workers.incident_arbiter,
            incident_application_executor=workers.application,
            target_lane_closure_executor=lambda _payload, guard: _unused_lane_closure(guard),
            activation_identity={
                "schema": "dev-control-plane/runtime-activation/v2",
                "release_sha": release_sha,
                "activation_nonce_sha256": "f" * 64,
                "pid": os.getpid(),
                "python_executable": str(Path(sys.executable).resolve()),
                "entrypoint": str((root / "releases" / release_sha / "apps" / "dev_control_plane_supervisor_v2.py").resolve()),
                "bind_host": "127.0.0.1",
                "bind_port": 8766,
            },
        )
        server = SupervisorCommandServer(runtime, default_socket_path(root / "state"))
        server.start()
        evidence = runtime.local_state()["qualification_evidence"]
        assert evidence["status"] == "passed", evidence
        assert evidence["app_server_canary"]["contract_kind"] == "checkpoint"
        assert evidence["app_server_canary"]["progress_percent"] == 40
        assert evidence["app_server_canary"]["model_attempt_count"] == 1
        assert evidence["app_server_canary"]["model_call_count"] == 1
        assert evidence["app_server_canary"]["single_attempt_canary"] is True
        assert evidence["staged_runtime"]["additional_model_calls"] == 0
        assert evidence["staged_runtime"]["final_attention_deferred"] is True
        assert evidence["staged_runtime"]["socket_mode"] == "0600"
        assert len(evidence["app_server_canary"]["checkpoint_payload_sha256"]) == 64
        server.stop()
        runtime.close()
        registry.release_generation(fence)

        # The staged foreground pilot is generation N, while launchd becomes
        # generation N+1.  Durable receipt generations are provenance, not a
        # requirement that the proving model call be repeated after restart.
        restart_fence = registry.acquire_generation("qualification-generation-restarted")
        _current_fence_holder[:] = [restart_fence]
        restarted_engine = SupervisorEngine(
            registry,
            restart_fence,
            supervisor_id="qualification-supervisor-restarted",
            contour_verifier=verifier,
        )
        shared = FakeCodexState(registry)
        shared.threads[executor.thread_id] = []
        restarted = SupervisorRuntime(
            restarted_engine,
            allowed_workspace_root=workspace,
            codex_bin="/usr/bin/true",
            codex_client_factory=lambda **kwargs: FakeCodexClient(shared, **kwargs),
            release_executor=workers.release,
            release_candidate_resolver=workers.resolver,
            release_arbiter_executor=workers.release_arbiter,
            incident_arbiter_executor=workers.incident_arbiter,
            incident_application_executor=workers.application,
            target_lane_closure_executor=lambda _payload, guard: _unused_lane_closure(guard),
            activation_identity={
                "schema": "dev-control-plane/runtime-activation/v2",
                "release_sha": release_sha,
                "activation_nonce_sha256": "f" * 64,
                "pid": os.getpid(),
                "python_executable": str(Path(sys.executable).resolve()),
                "entrypoint": str((root / "releases" / release_sha / "apps" / "dev_control_plane_supervisor_v2.py").resolve()),
                "bind_host": "127.0.0.1",
                "bind_port": 8766,
            },
        )
        restarted_server = SupervisorCommandServer(restarted, default_socket_path(root / "state"))
        restarted_server.start()
        assert restarted.resume_owned_threads() == (executor.thread_id,)
        assert shared.resume_calls == [executor.thread_id]
        restarted_evidence = restarted.local_state()["qualification_evidence"]
        assert restarted_evidence["status"] == "passed", restarted_evidence
        assert restarted_evidence["app_server_canary"]["model_attempt_count"] == 1
        assert restarted_evidence["app_server_canary"]["model_call_count"] == 1
        assert restarted_evidence["staged_runtime"]["additional_model_calls"] == 0

        failure_event_id = (
            "qualification-canary-failed:"
            + hashlib.sha256("qualification-followup-event".encode("utf-8")).hexdigest()[:48]
        )
        registry.append_event(
            failure_event_id,
            "qualification_canary_failed",
            {
                "schema": "dev-control-plane/qualification-canary-failure/v2",
                "status": "failed",
                "decision": "stop_qualification",
                "followup_event_id": "qualification-followup-event",
                "error_code": "simulated_split_receipt",
                "call_policy": "single_attempt_canary",
                "model_attempt_count": 1,
                "call_intent_present": True,
                "worker_claim_count": 1,
                "retry_allowed": False,
                "successor_allowed": False,
                "arbiter_allowed": False,
                "attention_created": False,
                "updated_at": NOW,
            },
            restart_fence,
            task_id=passport.task_id,
            workstream_id=stream.workstream_id,
            executor_generation=1,
        )
        vetoed = restarted.local_state()["qualification_evidence"]
        assert vetoed["status"] == "blocked", vetoed
        assert vetoed["app_server_canary"]["model_call_count"] == 1

        second_receipt_payload = {
            **qualification_receipt_payload,
            "supervisor_generation": restart_fence.generation,
            "turn_id": "qualification-second-turn",
            "item_ids": ["qualification-second-item"],
            "terminal_turn_ids": ["qualification-second-turn"],
            "lifecycle_digest": "b" * 64,
        }
        registry.append_event(
            "qualification-second-current-turn-receipt",
            "codex_turn_receipt",
            second_receipt_payload,
            restart_fence,
            task_id=passport.task_id,
            workstream_id=stream.workstream_id,
            executor_generation=1,
        )
        blocked = restarted.local_state()["qualification_evidence"]
        assert blocked["status"] == "blocked"
        assert blocked["app_server_canary"]["model_call_count"] == 2
        restarted_server.stop()
        restarted.close()
        registry.release_generation(restart_fence)


def _fresh_empty_thread_baseline_smoke() -> None:
    with TemporaryDirectory(prefix="dcpv2-fresh-empty-thread-", dir="/tmp") as raw:
        root = Path(raw)
        workspace_root = root / "managed"
        workspace_root.mkdir()
        task_workspace = workspace_root / "task"
        task_workspace.mkdir()
        registry = SupervisorRegistry(root / "supervisor.sqlite3", lease_seconds=30)
        fence = registry.acquire_generation("fresh-empty-thread-generation")
        _current_fence_holder[:] = [fence]
        shared = FakeCodexState(registry)
        runtime = _runtime(
            registry,
            fence,
            workspace_root,
            shared,
            client_type=EmptyThreadReadRejectedCodexClient,
        )
        passport, stream = _contracts()
        runtime.handle_command(
            {
                "contract": COMMAND_CONTRACT,
                "command": "start_executor",
                "request_id": "fresh-empty-start-request",
                "payload": {
                    "passport": contract_to_dict(passport),
                    "workstream": contract_to_dict(stream),
                    "cwd": str(task_workspace),
                    "message_id": "fresh-empty-start-message",
                },
            }
        )
        assert runtime.process_codex_once().status == "registered"

        for index in (1, 2):
            runtime.handle_command(
                {
                    "contract": COMMAND_CONTRACT,
                    "command": "codex_followup",
                    "request_id": f"fresh-empty-followup-request-{index}",
                    "payload": {
                        "task_id": passport.task_id,
                        "workstream_id": stream.workstream_id,
                        "prompt": f"Bounded call {index}.",
                        "output_contract": "checkpoint",
                        "cwd": str(task_workspace),
                        "terminal_context": None,
                        "call_policy": "standard",
                        "message_id": f"fresh-empty-followup-message-{index}",
                    },
                }
            )
            outcome = runtime.process_codex_once()
            assert outcome.status == "delivered", (
                outcome,
                registry.list_events(task_id=passport.task_id),
                registry.list_outbox_records(kinds=("codex_followup",)),
            )
            assert shared.turn_calls == index
            assert shared.snapshot_calls == index - 1

        records = registry.list_outbox_records(kinds=("codex_followup",))
        assert len(records) == 2
        assert records[0]["payload"]["call_intent"]["baseline_turn_ids"] == []
        assert records[1]["payload"]["call_intent"]["baseline_turn_ids"] == ["turn-1"]
        assert not registry.list_events(
            task_id=passport.task_id,
            event_types=("incident_policy", "qualification_canary_failed"),
        )
        runtime.close()
        registry.release_generation(fence)


def _single_attempt_canary_failure_smoke() -> None:
    with TemporaryDirectory(prefix="dcpv2-single-canary-", dir="/tmp") as raw:
        root = Path(raw)
        workspace_root = root / "managed"
        workspace_root.mkdir()
        task_workspace = workspace_root / "task"
        task_workspace.mkdir()
        registry = SupervisorRegistry(root / "supervisor.sqlite3", lease_seconds=30)
        fence = registry.acquire_generation("single-canary-generation")
        _current_fence_holder[:] = [fence]
        shared = FakeCodexState(registry)
        runtime = _runtime(
            registry,
            fence,
            workspace_root,
            shared,
            client_type=EmptyThreadReadRejectedFailingTurnCodexClient,
        )
        passport, stream = _contracts()
        runtime.handle_command(
            {
                "contract": COMMAND_CONTRACT,
                "command": "start_executor",
                "request_id": "single-canary-start-request",
                "payload": {
                    "passport": contract_to_dict(passport),
                    "workstream": contract_to_dict(stream),
                    "cwd": str(task_workspace),
                    "message_id": "single-canary-start-message",
                },
            }
        )
        assert runtime.process_codex_once().status == "registered"
        runtime.handle_command(
            {
                "contract": COMMAND_CONTRACT,
                "command": "codex_followup",
                "request_id": "single-canary-followup-request",
                "payload": {
                    "task_id": passport.task_id,
                    "workstream_id": stream.workstream_id,
                    "prompt": "One call only.",
                    "output_contract": "checkpoint",
                    "cwd": str(task_workspace),
                    "terminal_context": None,
                    "call_policy": "single_attempt_canary",
                    "message_id": "single-canary-followup-message",
                },
            }
        )
        failed = runtime.process_codex_once()
        assert failed.status == "qualification_failed" and shared.turn_calls == 1, failed
        assert shared.snapshot_calls == 0
        assert runtime.process_codex_once().status == "idle"
        assert shared.turn_calls == 1
        records = registry.list_outbox_records(kinds=("codex_followup",))
        assert len(records) == 1
        assert records[0]["state"] == "delivered"
        assert records[0]["payload"]["model_attempt_count"] == 1
        assert records[0]["payload"]["call_policy"] == "single_attempt_canary"
        failures = registry.list_events(
            task_id=passport.task_id,
            event_types=("qualification_canary_failed",),
        )
        assert len(failures) == 1
        assert failures[0]["payload"]["decision"] == "stop_qualification"
        assert failures[0]["payload"]["retry_allowed"] is False
        assert not registry.list_events(
            task_id=passport.task_id,
            event_types=("incident_policy",),
        )
        assert not registry.list_outbox_records(
            kinds=("codex_successor_start", "incident_arbiter", "curator_attention"),
            states=("pending", "inflight"),
        )
        assert registry.get_task(passport.task_id).state != "parked"

        duplicate_command = {
            "contract": COMMAND_CONTRACT,
            "command": "codex_followup",
            "request_id": "single-canary-duplicate-request",
            "payload": {
                "task_id": passport.task_id,
                "workstream_id": stream.workstream_id,
                "prompt": "A second qualification canary is forbidden.",
                "output_contract": "checkpoint",
                "cwd": str(task_workspace),
                "terminal_context": None,
                "call_policy": "single_attempt_canary",
                "message_id": "single-canary-duplicate-message",
            },
        }
        try:
            runtime.handle_command(duplicate_command)
        except SupervisorCommandError:
            pass
        else:
            raise AssertionError("command intake admitted a second qualification canary")
        assert shared.turn_calls == 1

        # Bypass command intake to prove the worker repeats the durable budget
        # check immediately before any model transport.
        bypass_payload = dict(records[0]["payload"])
        bypass_payload.update(
            {
                "prompt": "Worker budget gate must stop this injected duplicate.",
                "call_intent": None,
                "model_attempt_count": 0,
                "message_id": "single-canary-worker-bypass-message",
            }
        )
        registry.enqueue_outbox(
            "single-canary-worker-bypass-event",
            "codex_followup",
            bypass_payload,
            fence,
            task_id=passport.task_id,
        )
        worker_blocked = runtime.process_codex_once()
        assert worker_blocked.status == "qualification_failed", worker_blocked
        assert shared.turn_calls == 1 and shared.recovery_calls == 0
        assert len(
            registry.list_events(
                task_id=passport.task_id,
                event_types=("qualification_canary_failed",),
            )
        ) == 2
        runtime.close()
        registry.release_generation(fence)


def _split_canary_failure_recovery_smoke() -> None:
    """A durable stop event from an old split receipt permits ACK only."""

    with TemporaryDirectory(prefix="dcpv2-split-canary-failure-", dir="/tmp") as raw:
        root = Path(raw)
        workspace_root = root / "managed"
        workspace_root.mkdir()
        task_workspace = workspace_root / "task"
        task_workspace.mkdir()
        registry = SupervisorRegistry(root / "supervisor.sqlite3", lease_seconds=30)
        fence = registry.acquire_generation("split-canary-failure-generation")
        _current_fence_holder[:] = [fence]
        shared = FakeCodexState(registry)
        runtime = _runtime(registry, fence, workspace_root, shared)
        passport, stream = _contracts()
        runtime.handle_command(
            {
                "contract": COMMAND_CONTRACT,
                "command": "start_executor",
                "request_id": "split-canary-start-request",
                "payload": {
                    "passport": contract_to_dict(passport),
                    "workstream": contract_to_dict(stream),
                    "cwd": str(task_workspace),
                    "message_id": "split-canary-start-message",
                },
            }
        )
        assert runtime.process_codex_once().status == "registered"
        runtime.handle_command(
            {
                "contract": COMMAND_CONTRACT,
                "command": "codex_followup",
                "request_id": "split-canary-followup-request",
                "payload": {
                    "task_id": passport.task_id,
                    "workstream_id": stream.workstream_id,
                    "prompt": "This durable failure must prevent a model call.",
                    "output_contract": "checkpoint",
                    "cwd": str(task_workspace),
                    "terminal_context": None,
                    "call_policy": "single_attempt_canary",
                    "message_id": "split-canary-followup-message",
                },
            }
        )
        claimed = registry.claim_outbox(
            fence,
            worker_id="split-canary-old-worker",
            limit=1,
            visibility_timeout=0.001,
            kinds=("codex_followup",),
        )
        assert len(claimed) == 1
        message = claimed[0]
        failure_event_id = (
            "qualification-canary-failed:"
            + hashlib.sha256(message.event_id.encode("utf-8")).hexdigest()[:48]
        )
        registry.append_event(
            failure_event_id,
            "qualification_canary_failed",
            {
                "schema": "dev-control-plane/qualification-canary-failure/v2",
                "status": "failed",
                "decision": "stop_qualification",
                "followup_event_id": message.event_id,
                "error_code": "simulated_split_receipt",
                "call_policy": "single_attempt_canary",
                "model_attempt_count": 0,
                "call_intent_present": False,
                "worker_claim_count": 1,
                "retry_allowed": False,
                "successor_allowed": False,
                "arbiter_allowed": False,
                "attention_created": False,
                "updated_at": NOW,
            },
            fence,
            task_id=passport.task_id,
            workstream_id=stream.workstream_id,
            executor_generation=1,
        )
        time.sleep(0.01)
        recovered = runtime.process_codex_once()
        assert recovered.status == "qualification_failed", recovered
        assert shared.turn_calls == 0 and shared.recovery_calls == 0
        records = registry.list_outbox_records(kinds=("codex_followup",))
        assert len(records) == 1 and records[0]["state"] == "delivered"
        assert records[0]["attempts"] == 2
        assert len(
            registry.list_events(
                task_id=passport.task_id,
                event_types=("qualification_canary_failed",),
            )
        ) == 1
        try:
            runtime.handle_command(
                {
                    "contract": COMMAND_CONTRACT,
                    "command": "codex_followup",
                    "request_id": "split-canary-duplicate-request",
                    "payload": {
                        "task_id": passport.task_id,
                        "workstream_id": stream.workstream_id,
                        "prompt": "Count-zero failure still consumes the canary budget.",
                        "output_contract": "checkpoint",
                        "cwd": str(task_workspace),
                        "terminal_context": None,
                        "call_policy": "single_attempt_canary",
                        "message_id": "split-canary-duplicate-message",
                    },
                }
            )
        except SupervisorCommandError:
            pass
        else:
            raise AssertionError("count-zero stop admitted a replacement canary")
        assert shared.turn_calls == 0 and shared.recovery_calls == 0
        runtime.close()
        registry.release_generation(fence)


def _lost_receipt_recovery_smoke() -> None:
    for malformed in (False, True):
        suffix = "malformed" if malformed else "typed"
        with TemporaryDirectory(prefix=f"dcpv2-lost-receipt-{suffix}-", dir="/tmp") as raw:
            root = Path(raw)
            workspace_root = root / "managed"
            workspace_root.mkdir()
            task_workspace = workspace_root / "task"
            task_workspace.mkdir()
            registry = SupervisorRegistry(root / "supervisor.sqlite3", lease_seconds=30)
            first_fence = registry.acquire_generation(f"lost-receipt-{suffix}-generation-one")
            _current_fence_holder[:] = [first_fence]
            shared = FakeCodexState(registry)
            runtime = _runtime(
                registry,
                first_fence,
                workspace_root,
                shared,
                client_type=CrashAfterSuccessfulTurnCodexClient,
            )
            passport, stream = _contracts()
            runtime.handle_command(
                {
                    "contract": COMMAND_CONTRACT,
                    "command": "start_executor",
                    "request_id": f"lost-receipt-{suffix}-start-request",
                    "payload": {
                        "passport": contract_to_dict(passport),
                        "workstream": contract_to_dict(stream),
                        "cwd": str(task_workspace),
                        "message_id": f"lost-receipt-{suffix}-start-message",
                    },
                }
            )
            assert runtime.process_codex_once().status == "registered"
            runtime.handle_command(
                {
                    "contract": COMMAND_CONTRACT,
                    "command": "codex_followup",
                    "request_id": f"lost-receipt-{suffix}-followup-request",
                    "payload": {
                        "task_id": passport.task_id,
                        "workstream_id": stream.workstream_id,
                        "prompt": "One durable model attempt with crash recovery.",
                        "output_contract": "checkpoint",
                        "cwd": str(task_workspace),
                        "terminal_context": None,
                        "call_policy": "single_attempt_canary",
                        "message_id": f"lost-receipt-{suffix}-followup-message",
                    },
                }
            )
            try:
                runtime.process_codex_once()
            except SimulatedRuntimeCrash:
                pass
            else:
                raise AssertionError("fake receipt-loss process crash was swallowed")
            assert shared.turn_calls == 1 and shared.start_calls == 1
            stranded = registry.list_outbox_records(kinds=("codex_followup",))
            assert len(stranded) == 1 and stranded[0]["state"] == "inflight"
            assert stranded[0]["payload"]["call_intent"] is not None
            assert stranded[0]["payload"]["model_attempt_count"] == 1
            assert not registry.list_events(
                task_id=passport.task_id,
                event_types=("checkpoint", "incident_policy", "codex_turn_receipt"),
            )
            runtime.close()
            registry.release_generation(first_fence)

            second_fence = registry.acquire_generation(
                f"lost-receipt-{suffix}-generation-two"
            )
            _current_fence_holder[:] = [second_fence]
            restarted = _runtime(
                registry,
                second_fence,
                workspace_root,
                shared,
                client_type=(MalformedRecoveryCodexClient if malformed else FakeCodexClient),
            )
            outcome = restarted.process_codex_once()
            assert shared.turn_calls == 1 and shared.start_calls == 1
            assert shared.recovery_calls == 1
            assert not registry.list_outbox_records(
                kinds=("codex_successor_start",), states=("pending", "inflight")
            )
            if malformed:
                assert outcome.status == "qualification_failed", outcome
                assert registry.get_task(passport.task_id).state != "parked"
                failures = registry.list_events(
                    task_id=passport.task_id,
                    event_types=("qualification_canary_failed",),
                )
                assert len(failures) == 1
                assert failures[0]["payload"]["decision"] == "stop_qualification"
                assert not registry.list_events(
                    task_id=passport.task_id,
                    event_types=("checkpoint", "codex_turn_receipt", "incident_policy"),
                )
                assert not registry.list_outbox_records(
                    kinds=("codex_successor_start", "incident_arbiter", "curator_attention"),
                    states=("pending", "inflight"),
                )
            else:
                assert outcome.status == "delivered", outcome
                assert registry.get_task(passport.task_id).state != "parked"
                assert not registry.list_events(
                    task_id=passport.task_id,
                    event_types=("incident_policy",),
                )
                checkpoints = registry.list_events(
                    task_id=passport.task_id,
                    workstream_id=stream.workstream_id,
                    event_types=("checkpoint",),
                )
                assert len(checkpoints) == 1
                receipts = registry.list_events(
                    task_id=passport.task_id,
                    workstream_id=stream.workstream_id,
                    event_types=("codex_turn_receipt",),
                )
                assert len(receipts) == 1
                receipt = receipts[0]["payload"]
                assert receipt["receipt_source"] == "thread_read_recovery"
                assert receipt["model_attempt_count"] == 1
                assert receipt["model_call_count"] == 1
                assert receipt["recovery_model_call_count"] == 0
                assert receipt["lifecycle_methods"] == []
                assert receipt["structural_lifecycle_methods"] == [
                    "item/completed",
                    "turn/completed",
                ]
                assert receipt["snapshot_lifecycle_methods"] == [
                    "item/completed",
                    "turn/completed",
                ]
                assert receipt["lifecycle_evidence_sources"] == [
                    "thread_read_snapshot"
                ]
                assert not registry.list_outbox_records(
                    kinds=("curator_attention",), states=("pending", "inflight")
                )
            restarted.close()
            registry.release_generation(second_fence)


def _partial_result_receipt_recovery_smoke() -> None:
    """A checkpoint-only crash is structurally receipted without a second turn."""

    with TemporaryDirectory(prefix="dcpv2-partial-result-receipt-", dir="/tmp") as raw:
        root = Path(raw)
        workspace_root = root / "managed"
        workspace_root.mkdir()
        task_workspace = workspace_root / "task"
        task_workspace.mkdir()
        registry = SupervisorRegistry(root / "supervisor.sqlite3", lease_seconds=30)
        first_fence = registry.acquire_generation("partial-result-generation-one")
        _current_fence_holder[:] = [first_fence]
        shared = FakeCodexState(registry)
        runtime = _runtime(registry, first_fence, workspace_root, shared)
        runtime.visibility_timeout_seconds = 0.05
        passport, stream = _contracts()
        runtime.handle_command(
            {
                "contract": COMMAND_CONTRACT,
                "command": "start_executor",
                "request_id": "partial-result-start-request",
                "payload": {
                    "passport": contract_to_dict(passport),
                    "workstream": contract_to_dict(stream),
                    "cwd": str(task_workspace),
                    "message_id": "partial-result-start-message",
                },
            }
        )
        assert runtime.process_codex_once().status == "registered"
        runtime.handle_command(
            {
                "contract": COMMAND_CONTRACT,
                "command": "codex_followup",
                "request_id": "partial-result-followup-request",
                "payload": {
                    "task_id": passport.task_id,
                    "workstream_id": stream.workstream_id,
                    "prompt": "Persist checkpoint before structural receipt crash.",
                    "output_contract": "checkpoint",
                    "cwd": str(task_workspace),
                    "terminal_context": None,
                    "call_policy": "single_attempt_canary",
                    "message_id": "partial-result-followup-message",
                },
            }
        )
        original_record = registry.record_input_event_outbox
        crashed = [False]

        def crash_before_structural_receipt(**kwargs: Any) -> bool:
            if (
                kwargs.get("source") == "codex-app-server-structural-receipt"
                and not crashed[0]
            ):
                crashed[0] = True
                raise SimulatedRuntimeCrash("checkpoint persisted before turn receipt")
            return original_record(**kwargs)

        registry.record_input_event_outbox = crash_before_structural_receipt  # type: ignore[method-assign]
        try:
            runtime.process_codex_once()
        except SimulatedRuntimeCrash:
            pass
        else:
            raise AssertionError("partial result/receipt crash was swallowed")
        finally:
            registry.record_input_event_outbox = original_record  # type: ignore[method-assign]
        assert shared.turn_calls == 1 and shared.recovery_calls == 0
        checkpoints = registry.list_events(
            task_id=passport.task_id,
            event_types=("checkpoint",),
        )
        assert len(checkpoints) == 1
        assert not registry.list_events(
            task_id=passport.task_id,
            event_types=("codex_turn_receipt", "qualification_canary_failed"),
        )
        runtime.close()
        registry.release_generation(first_fence)

        second_fence = registry.acquire_generation("partial-result-generation-two")
        _current_fence_holder[:] = [second_fence]
        restarted = _runtime(registry, second_fence, workspace_root, shared)
        recovered = restarted.process_codex_once()
        assert recovered.status == "delivered", recovered
        assert shared.turn_calls == 1 and shared.recovery_calls == 1
        receipts = registry.list_events(
            task_id=passport.task_id,
            event_types=("codex_turn_receipt",),
        )
        assert len(receipts) == 1
        assert receipts[0]["payload"]["receipt_source"] == "thread_read_recovery"
        assert not registry.list_events(
            task_id=passport.task_id,
            event_types=("qualification_canary_failed",),
        )
        records = registry.list_outbox_records(kinds=("codex_followup",))
        assert len(records) == 1 and records[0]["state"] == "delivered"
        restarted.close()
        registry.release_generation(second_fence)


def _partial_result_invalid_intent_smoke() -> None:
    """A result without its exact one-call intent can never trigger a turn."""

    invalid_variants = (
        ("missing-intent", None, 1),
        (
            "missing-attempt",
            {
                "supervisor_generation": 1,
                "started_at": NOW,
                "baseline_turn_ids": [],
            },
            0,
        ),
    )
    for suffix, call_intent, model_attempt_count in invalid_variants:
        with TemporaryDirectory(
            prefix=f"dcpv2-partial-result-{suffix}-",
            dir="/tmp",
        ) as raw:
            root = Path(raw)
            workspace_root = root / "managed"
            workspace_root.mkdir()
            task_workspace = workspace_root / "task"
            task_workspace.mkdir()
            registry = SupervisorRegistry(root / "supervisor.sqlite3", lease_seconds=30)
            fence = registry.acquire_generation(f"partial-result-{suffix}-generation")
            _current_fence_holder[:] = [fence]
            shared = FakeCodexState(registry)
            runtime = _runtime(registry, fence, workspace_root, shared)
            passport, stream = _contracts()
            runtime.handle_command(
                {
                    "contract": COMMAND_CONTRACT,
                    "command": "start_executor",
                    "request_id": f"partial-result-{suffix}-start-request",
                    "payload": {
                        "passport": contract_to_dict(passport),
                        "workstream": contract_to_dict(stream),
                        "cwd": str(task_workspace),
                        "message_id": f"partial-result-{suffix}-start-message",
                    },
                }
            )
            assert runtime.process_codex_once().status == "registered"
            executor = registry.current_executor(passport.task_id, stream.workstream_id)
            assert executor is not None
            followup_event_id = f"partial-result-{suffix}-followup-event"
            result_event_id = (
                "codex-result:"
                + hashlib.sha256(followup_event_id.encode("utf-8")).hexdigest()[:48]
            )
            checkpoint = Checkpoint(
                checkpoint_id=f"partial-result-{suffix}-checkpoint",
                event_id=result_event_id,
                task_id=passport.task_id,
                task_revision=1,
                workstream_id=stream.workstream_id,
                workstream_revision=1,
                executor_generation=executor.executor_generation,
                executor=ExecutorIdentity(
                    executor.thread_id,
                    executor.host_id,
                    executor.model,
                    executor.reasoning,
                ),
                progress_stage=25,
                delta_ru="Смоделирован частично сохранённый checkpoint.",
                current_ru="Проверяется fail-closed восстановление.",
                evidence=("smoke:partial-result",),
                created_at=NOW,
            )
            registry.append_event(
                result_event_id,
                "checkpoint",
                {
                    "schema": "dev-control-plane/supervisor-event/v2",
                    "contract": contract_to_dict(checkpoint),
                    "progress": 25,
                    "delta_ru": checkpoint.delta_ru,
                    "current_ru": checkpoint.current_ru,
                    "objective_invalidated": False,
                    "task_revision": 1,
                    "workstream_revision": 1,
                    "executor_generation": executor.executor_generation,
                    "created_at": NOW,
                },
                fence,
                task_id=passport.task_id,
                workstream_id=stream.workstream_id,
                executor_generation=executor.executor_generation,
            )
            registry.enqueue_outbox(
                followup_event_id,
                "codex_followup",
                {
                    "schema": "dev-control-plane/codex-followup/v2",
                    "task_id": passport.task_id,
                    "task_revision": 1,
                    "workstream_id": stream.workstream_id,
                    "workstream_revision": 1,
                    "executor_generation": executor.executor_generation,
                    "thread_id": executor.thread_id,
                    "host_id": executor.host_id,
                    "model": executor.model,
                    "reasoning": executor.reasoning,
                    "prompt": "This malformed partial result must never call Codex.",
                    "output_contract": "checkpoint",
                    "cwd": str(task_workspace.resolve()),
                    "terminal_context": None,
                    "causal_fingerprint": None,
                    "causal_binding": None,
                    "call_intent": call_intent,
                    "call_policy": "single_attempt_canary",
                    "model_attempt_count": model_attempt_count,
                    "message_id": f"partial-result-{suffix}-followup-message",
                },
                fence,
                task_id=passport.task_id,
            )
            failed = runtime.process_codex_once()
            assert failed.status == "qualification_failed", failed
            assert shared.turn_calls == 0 and shared.recovery_calls == 0
            records = registry.list_outbox_records(kinds=("codex_followup",))
            assert len(records) == 1 and records[0]["state"] == "delivered"
            failures = registry.list_events(
                task_id=passport.task_id,
                event_types=("qualification_canary_failed",),
            )
            assert len(failures) == 1
            runtime.close()
            registry.release_generation(fence)


def _same_connection_lost_receipt_taint_smoke() -> None:
    """Exact recovery clears same-epoch taint without a second model call."""

    with TemporaryDirectory(prefix="dcpv2-same-connection-recovery-", dir="/tmp") as raw:
        root = Path(raw)
        workspace_root = root / "managed"
        workspace_root.mkdir()
        task_workspace = workspace_root / "task"
        task_workspace.mkdir()
        registry = SupervisorRegistry(root / "supervisor.sqlite3", lease_seconds=30)
        fence = registry.acquire_generation("same-connection-recovery-generation")
        _current_fence_holder[:] = [fence]
        shared = FakeCodexState(registry)
        runtime = _runtime(
            registry,
            fence,
            workspace_root,
            shared,
            client_type=SameConnectionCrashOnceCodexClient,
        )
        # The fake turn itself lasts longer than this claim, so the exact same
        # process can reclaim the lost receipt immediately after the injected
        # crash without a wall-clock sleep.
        runtime.visibility_timeout_seconds = 0.05
        passport, stream = _contracts()
        runtime.handle_command(
            {
                "contract": COMMAND_CONTRACT,
                "command": "start_executor",
                "request_id": "same-connection-start-request",
                "payload": {
                    "passport": contract_to_dict(passport),
                    "workstream": contract_to_dict(stream),
                    "cwd": str(task_workspace),
                    "message_id": "same-connection-start-message",
                },
            }
        )
        assert runtime.process_codex_once().status == "registered"
        executor = registry.current_executor(passport.task_id, stream.workstream_id)
        assert executor is not None
        runtime.handle_command(
            {
                "contract": COMMAND_CONTRACT,
                "command": "codex_followup",
                "request_id": "same-connection-first-followup-request",
                "payload": {
                    "task_id": passport.task_id,
                    "workstream_id": stream.workstream_id,
                    "prompt": "Persist one turn, then recover its lost receipt.",
                    "output_contract": "checkpoint",
                    "cwd": str(task_workspace),
                    "terminal_context": None,
                    "call_policy": "single_attempt_canary",
                    "message_id": "same-connection-first-followup-message",
                },
            }
        )
        try:
            runtime.process_codex_once()
        except SimulatedRuntimeCrash:
            pass
        else:
            raise AssertionError("same-connection lost-receipt crash was swallowed")
        adapter = runtime._codex_client
        assert isinstance(adapter, SameConnectionCrashOnceCodexClient)
        assert executor.thread_id in adapter.tainted_thread_ids
        assert shared.turn_calls == 1 and shared.recovery_calls == 0

        recovered = runtime.process_codex_once()
        assert recovered.status == "delivered", recovered
        assert shared.turn_calls == 1 and shared.recovery_calls == 1
        assert executor.thread_id not in adapter.tainted_thread_ids

        runtime.handle_command(
            {
                "contract": COMMAND_CONTRACT,
                "command": "codex_followup",
                "request_id": "same-connection-next-followup-request",
                "payload": {
                    "task_id": passport.task_id,
                    "workstream_id": stream.workstream_id,
                    "prompt": "Run the next distinct serialized turn.",
                    "output_contract": "checkpoint",
                    "cwd": str(task_workspace),
                    "terminal_context": None,
                    "call_policy": "standard",
                    "message_id": "same-connection-next-followup-message",
                },
            }
        )
        next_turn = runtime.process_codex_once()
        assert next_turn.status == "delivered", next_turn
        assert shared.turn_calls == 2 and shared.recovery_calls == 1
        receipts = registry.list_events(
            task_id=passport.task_id,
            workstream_id=stream.workstream_id,
            event_types=("codex_turn_receipt",),
        )
        assert len(receipts) == 2
        assert receipts[0]["payload"]["receipt_source"] == "thread_read_recovery"
        assert receipts[0]["payload"]["model_call_count"] == 1
        assert receipts[0]["payload"]["recovery_model_call_count"] == 0
        runtime.close()
        registry.release_generation(fence)


def _attention_receipt_restart_smoke() -> None:
    """A delivered bridge receipt survives one Supervisor generation change."""

    with TemporaryDirectory(prefix="dcpv2-attention-restart-", dir="/tmp") as raw:
        root = Path(raw)
        workspace = root / "managed"
        workspace.mkdir()
        now = [time.time()]
        registry = SupervisorRegistry(
            root / "supervisor.sqlite3",
            lease_seconds=30,
            clock=lambda: now[0],
        )
        first_fence = registry.acquire_generation("attention-generation-one")
        shared = FakeCodexState(registry)
        first_runtime = _runtime(registry, first_fence, workspace, shared)
        passport, stream = _contracts()
        attention_executor = ExecutorIdentity(
            "attention-restart-thread", "mac-local", "gpt-5.6-sol", "ultra"
        )
        passport = replace(passport, executor=attention_executor)
        stream = replace(stream, executor=attention_executor, state="working")
        first_runtime.engine.register(
            passport, stream, message_id="attention-restart-register"
        )

        def enqueue(
            runtime: SupervisorRuntime, event_id: str, attention_id: str
        ) -> None:
            registry.enqueue_outbox(
                event_id,
                "curator_attention",
                {
                    "schema": "dev-control-plane/curator-attention/v2",
                    "attention_id": attention_id,
                    "task_id": passport.task_id,
                    "workstream_id": stream.workstream_id,
                    "curator_thread_id": passport.curator.thread_id,
                    "kind": "human_gate",
                    "handoff_ru": "Статус: Блокер",
                    "required_action": "Выполнить одно точное human-only действие.",
                    "created_at": NOW,
                },
                runtime.engine.fence,
                task_id=passport.task_id,
                coalescible=False,
            )

        def command(runtime: SupervisorRuntime, name: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
            return runtime.handle_command(
                {
                    "contract": COMMAND_CONTRACT,
                    "command": name,
                    "request_id": f"{name}-{hashlib.sha256(json.dumps(dict(payload), sort_keys=True).encode()).hexdigest()[:16]}",
                    "payload": dict(payload),
                }
            )["result"]

        enqueue(first_runtime, "attention-restart-ack-event", "attention-restart-ack")
        prepared = command(
            first_runtime, "prepare_attention", {"visibility_timeout": 120}
        )
        assert prepared is not None
        first_runtime.close()
        registry.release_generation(first_fence)

        second_fence = registry.acquire_generation("attention-generation-two")
        second_runtime = _runtime(registry, second_fence, workspace, shared)
        ack_payload = {
            key: prepared[key]
            for key in (
                "event_id", "attention_id", "curator_thread_id",
                "payload_digest", "claim_token",
            )
        }
        for field, wrong in (
            ("claim_token", "wrong-attention-claim-token"),
            ("payload_digest", "0" * 64),
            ("curator_thread_id", "wrong-curator-thread"),
            ("attention_id", "wrong-attention-id"),
        ):
            try:
                command(second_runtime, "ack_attention", {**ack_payload, field: wrong})
            except SupervisorCommandError:
                pass
            else:
                raise AssertionError(f"cross-bound restart ACK accepted: {field}")
            inflight = registry.list_outbox_records(
                kinds=("curator_attention",), states=("inflight",)
            )
            assert len(inflight) == 1 and inflight[0]["event_id"] == prepared["event_id"]

        acknowledged = command(second_runtime, "ack_attention", ack_payload)
        assert acknowledged["delivered"] is True
        assert acknowledged["prior_generation_receipt"] is True
        replay = command(second_runtime, "ack_attention", ack_payload)
        assert replay == {
            "delivered": True,
            "idempotent": True,
            "event_id": prepared["event_id"],
        }

        enqueue(
            second_runtime,
            "attention-restart-no-receipt-event",
            "attention-restart-no-receipt",
        )
        ambiguous_prepared = command(
            second_runtime, "prepare_attention", {"visibility_timeout": 120}
        )
        assert ambiguous_prepared is not None
        second_runtime.close()
        registry.release_generation(second_fence)

        now[0] += 600
        third_fence = registry.acquire_generation("attention-generation-three")
        third_runtime = _runtime(registry, third_fence, workspace, shared)
        attempts_before = next(
            item
            for item in registry.list_outbox_records(kinds=("curator_attention",))
            if item["event_id"] == ambiguous_prepared["event_id"]
        )["attempts"]
        assert command(
            third_runtime, "prepare_attention", {"visibility_timeout": 120}
        ) is None
        ambiguous_record = next(
            item
            for item in registry.list_outbox_records(kinds=("curator_attention",))
            if item["event_id"] == ambiguous_prepared["event_id"]
        )
        assert ambiguous_record["state"] == "inflight"
        assert ambiguous_record["attempts"] == attempts_before
        projected = next(
            item
            for item in third_runtime.engine.projection_snapshot()["attention"]
            if item["attention_id"] == ambiguous_prepared["attention_id"]
        )
        assert projected["status"] == "pending"
        ambiguous_ack = {
            key: ambiguous_prepared[key]
            for key in (
                "event_id", "attention_id", "curator_thread_id",
                "payload_digest", "claim_token",
            )
        }
        assert command(third_runtime, "ack_attention", ambiguous_ack)[
            "prior_generation_receipt"
        ] is True

        enqueue(
            third_runtime,
            "attention-restart-nack-event",
            "attention-restart-nack",
        )
        nack_prepared = command(
            third_runtime, "prepare_attention", {"visibility_timeout": 120}
        )
        assert nack_prepared is not None
        third_runtime.close()
        registry.release_generation(third_fence)

        fourth_fence = registry.acquire_generation("attention-generation-four")
        fourth_runtime = _runtime(registry, fourth_fence, workspace, shared)
        retry_at = now[0] + 60
        nack_payload = {
            **{
                key: nack_prepared[key]
                for key in (
                    "event_id", "attention_id", "curator_thread_id",
                    "payload_digest", "claim_token",
                )
            },
            "retry_at": retry_at,
            "reason_code": "supported_bridge_retry",
        }
        nacked = command(fourth_runtime, "nack_attention", nack_payload)
        assert nacked["pending"] is True
        assert nacked["prior_generation_receipt"] is True
        pending = registry.list_outbox_records(
            kinds=("curator_attention",), states=("pending",)
        )
        assert len(pending) == 1
        assert pending[0]["event_id"] == nack_prepared["event_id"]
        assert command(
            fourth_runtime, "prepare_attention", {"visibility_timeout": 120}
        ) is None
        fourth_runtime.close()
        registry.release_generation(fourth_fence)


def _record_fake_task_lane_closure(
    registry: SupervisorRegistry,
    fence: Any,
    *,
    task_id: str,
    task_revision: int,
    workstream_id: str,
    logical_lane_id: str,
) -> None:
    closure_id = f"smoke-closure-{task_id}-r{task_revision}"
    registry.append_event(
        f"smoke-target-lane-closed-{task_id}-r{task_revision}",
        "target_lane_closure_completed",
        {
            "schema": "dev-control-plane/target-lane-closure-result-event/v2",
            "action": {
                "closure_id": closure_id,
                "task_id": task_id,
                "task_revision": task_revision,
                "workstream_id": workstream_id,
                "logical_lane_id": logical_lane_id,
            },
            "receipt": {
                "closure_id": closure_id,
                "task_id": task_id,
                "task_revision": task_revision,
                "workstream_id": workstream_id,
                "status": "released",
            },
        },
        fence,
        task_id=task_id,
        workstream_id=workstream_id,
    )


def _release_orchestration_smoke() -> None:
    with TemporaryDirectory(prefix="dcpv2-release-runtime-", dir="/tmp") as raw:
        root = Path(raw)
        workspace = root / "managed"
        workspace.mkdir()
        registry = SupervisorRegistry(root / "supervisor.sqlite3", lease_seconds=30)
        fence = registry.acquire_generation("release-runtime-generation")
        engine = SupervisorEngine(registry, fence, supervisor_id="release-runtime-supervisor")
        workers = FakeReleaseWorkers()
        workers.release_plan_wait_after_first = True
        runtime = _release_runtime(engine, workspace, workers)

        passport, stream = _release_registration(engine, "fast", "module:fast", "src/fast.py")
        fast_head = "a" * 40
        workers.actual_files[fast_head] = ("src/fast.py",)
        registered = _runtime_register_release_candidate(
            runtime, passport.task_id, stream.workstream_id, fast_head, "register-fast-candidate"
        )
        assert registered["created"] is True
        registered_row = next(
            item
            for item in engine.projection_snapshot()["release_lanes"]
            if item["task_id"] == passport.task_id
        )
        assert registered_row["status"] == "pr_open"
        assert registered_row["deploy_status"] == "candidate_registered"
        assert runtime.process_release_once().status == "scheduled"
        assert runtime.process_release_once().status == "resolved"
        release_action = next(
            item
            for item in registry.list_outbox_records(
                kinds=("release_action",), states=("pending",)
            )
            if item["task_id"] == passport.task_id
        )
        candidate = release_action["payload"]["candidate"]
        release_result_event_id = (
            "release-result:"
            + hashlib.sha256(str(release_action["event_id"]).encode()).hexdigest()[:48]
        )
        registry.append_event(
            release_result_event_id,
            "release_completed",
            {
                "schema": "dev-control-plane/release-result-event/v2",
                "release_action_event_id": release_action["event_id"],
                "receipt": {
                    "status": "passed",
                    "candidate_id": candidate["candidate_id"],
                    "task_id": candidate["task_id"],
                    "workstream_id": candidate["workstream_id"],
                    "task_revision": candidate["task_revision"],
                    "workstream_revision": candidate["workstream_revision"],
                    "pr_head_sha": candidate["pr_head_sha"],
                    "contour": passport.contour,
                },
                "target_adapter": release_action["payload"]["target_adapter"],
            },
            fence,
            task_id=passport.task_id,
            workstream_id=stream.workstream_id,
        )
        assert runtime.process_release_once().status == "deduped"
        assert len(registry.list_events(event_types=("release_completed",))) == 1
        assert workers.release_calls == 0 and registry.inspect_locks(kind="release_lane")
        _record_fake_task_lane_closure(
            registry,
            fence,
            task_id=passport.task_id,
            task_revision=1,
            workstream_id=stream.workstream_id,
            logical_lane_id=f"release-task-fast",
        )
        engine.tick()
        assert not registry.inspect_locks()
        assert runtime.process_release_once().status == "idle"

        first_passport, first_stream = _release_registration(
            engine, "semantic-one", "module:shared", "src/shared.py"
        )
        second_passport, second_stream = _release_registration(
            engine, "semantic-two", "module:shared", "src/shared.py"
        )
        first_head = "b" * 40
        second_head = "c" * 40
        workers.actual_files[first_head] = ("src/shared.py",)
        workers.actual_files[second_head] = ("src/shared.py",)
        _runtime_register_release_candidate(
            runtime,
            first_passport.task_id,
            first_stream.workstream_id,
            first_head,
            "register-semantic-one-candidate",
        )
        _runtime_register_release_candidate(
            runtime,
            second_passport.task_id,
            second_stream.workstream_id,
            second_head,
            "register-semantic-two-candidate",
        )
        assert runtime.process_release_once().status == "scheduled"
        assert runtime.process_release_once().status == "decided"
        assert runtime.process_release_once().status == "scheduled"
        assert runtime.process_release_once().status == "resolved"
        assert runtime.process_release_once().status == "delivered"
        first_semantic_completion = next(
            event
            for event in registry.list_events(event_types=("release_completed",))
            if event["task_id"]
            in {first_passport.task_id, second_passport.task_id}
        )
        first_semantic_task = str(first_semantic_completion["task_id"])
        first_semantic_stream = str(first_semantic_completion["workstream_id"])
        _record_fake_task_lane_closure(
            registry,
            fence,
            task_id=first_semantic_task,
            task_revision=1,
            workstream_id=first_semantic_stream,
            logical_lane_id=(
                "release-task-semantic-one"
                if first_semantic_task == first_passport.task_id
                else "release-task-semantic-two"
            ),
        )
        engine.tick()
        assert runtime.process_release_once().status == "scheduled"
        assert runtime.process_release_once().status == "resolved"
        assert runtime.process_release_once().status == "delivered"
        completed = registry.list_events(event_types=("release_completed",))
        assert len(completed) == 3 and workers.release_arbiter_calls == 1
        assert len(registry.list_events(event_types=("release_plan_superseded",))) == 1
        second_semantic_completion = next(
            event
            for event in completed
            if event["task_id"]
            in {first_passport.task_id, second_passport.task_id}
            and event["task_id"] != first_semantic_task
        )
        second_semantic_task = str(second_semantic_completion["task_id"])
        _record_fake_task_lane_closure(
            registry,
            fence,
            task_id=second_semantic_task,
            task_revision=1,
            workstream_id=str(second_semantic_completion["workstream_id"]),
            logical_lane_id=(
                "release-task-semantic-one"
                if second_semantic_task == first_passport.task_id
                else "release-task-semantic-two"
            ),
        )
        engine.tick()
        assert not registry.inspect_locks()

        try:
            runtime.handle_command(
                {
                    "contract": COMMAND_CONTRACT,
                    "command": "schedule",
                    "request_id": "forged-schedule-request",
                    "payload": {},
                }
            )
        except SupervisorCommandError:
            pass
        else:
            raise AssertionError("caller-authored schedule command remained reachable")
        try:
            runtime.handle_command(
                {
                    "contract": COMMAND_CONTRACT,
                    "command": "register_release_candidate",
                    "request_id": "forged-registration-request",
                    "payload": {
                        "task_id": passport.task_id,
                        "workstream_id": stream.workstream_id,
                        "expected_pr_head_sha": fast_head,
                        "message_id": "forged-registration-message",
                        "resources": ["module:forged"],
                        "owner_priority": 0,
                        "active_logical_lane_id": "forged-lane",
                        "completed_task_ids": [],
                    },
                }
            )
        except SupervisorCommandError:
            pass
        else:
            raise AssertionError("release registration accepted caller-authored scheduler policy")

        merged_passport, merged_stream = _release_registration(
            engine, "merged-proof", "module:merged", "src/merged.py"
        )
        merged_head = "e" * 40
        workers.actual_files[merged_head] = ("src/merged.py",)
        workers.merged_heads.add(merged_head)
        _runtime_register_release_candidate(
            runtime,
            merged_passport.task_id,
            merged_stream.workstream_id,
            merged_head,
            "register-merged-proof-candidate",
        )
        assert runtime.process_release_once().status == "proof_only_wait"
        merged_waits = registry.list_events(
            task_id=merged_passport.task_id, event_types=("release_wait",)
        )
        assert len(merged_waits) == 1
        assert merged_waits[0]["payload"]["candidates"][0]["admission_ready"] is False
        merged_row = next(
            item
            for item in engine.projection_snapshot()["release_lanes"]
            if item["task_id"] == merged_passport.task_id
        )
        assert merged_row["status"] == "merged"
        assert merged_row["deploy_status"] == "proof_only"
        assert not [
            item
            for item in registry.list_outbox_records(
                kinds=("release_candidate_resolution", "release_action")
            )
            if item["task_id"] == merged_passport.task_id
        ]
        runtime.close()
        registry.release_generation(fence)

    _release_registration_restart_smoke()


def _release_all_wait_refresh_restart_smoke() -> None:
    """All-wait polls truth durably and never asks Sol again unchanged."""

    with TemporaryDirectory(prefix="dcpv2-release-all-wait-", dir="/tmp") as raw:
        root = Path(raw)
        workspace = root / "managed"
        workspace.mkdir()
        now = [1_786_000_000.0]

        def clock() -> float:
            return now[0]

        registry = SupervisorRegistry(
            root / "supervisor.sqlite3", lease_seconds=30, clock=clock
        )
        first_fence = registry.acquire_generation("all-wait-generation-one")
        first_engine = SupervisorEngine(
            registry,
            first_fence,
            supervisor_id="all-wait-supervisor",
            clock=clock,
        )
        workers = FakeReleaseWorkers()
        workers.release_plan_all_wait = True
        first_runtime = _release_runtime(
            first_engine, workspace, workers, clock=clock
        )
        first_passport, first_stream = _release_registration(
            first_engine,
            "all-wait-one",
            "module:all-wait-shared",
            "src/all_wait_shared.py",
        )
        second_passport, second_stream = _release_registration(
            first_engine,
            "all-wait-two",
            "module:all-wait-shared",
            "src/all_wait_shared.py",
        )
        first_head = "1" * 40
        second_head = "2" * 40
        workers.actual_files[first_head] = ("src/all_wait_shared.py",)
        workers.actual_files[second_head] = ("src/all_wait_shared.py",)
        _runtime_register_release_candidate(
            first_runtime,
            first_passport.task_id,
            first_stream.workstream_id,
            first_head,
            "register-all-wait-one-candidate",
        )
        _runtime_register_release_candidate(
            first_runtime,
            second_passport.task_id,
            second_stream.workstream_id,
            second_head,
            "register-all-wait-two-candidate",
        )
        assert first_runtime.process_release_once().status == "scheduled"
        assert first_runtime.process_release_once().status == "decided"
        assert first_runtime.process_release_once().status == "scheduled"
        assert workers.release_arbiter_calls == 1
        refresh = registry.list_outbox_records(
            kinds=("release_candidate_intake",), states=("pending",)
        )
        refresh = tuple(
            item
            for item in refresh
            if item["payload"].get("semantic_case_id")
        )
        assert len(refresh) == 1
        case_id = refresh[0]["payload"]["semantic_case_id"]
        case_digest = refresh[0]["payload"]["semantic_case_digest"]

        first_runtime.close()
        registry.release_generation(first_fence)
        second_fence = registry.acquire_generation("all-wait-generation-two")
        second_engine = SupervisorEngine(
            registry,
            second_fence,
            supervisor_id="all-wait-supervisor",
            clock=clock,
        )
        second_runtime = _release_runtime(
            second_engine, workspace, workers, clock=clock
        )
        second_runtime.maintenance_tick()
        assert workers.release_arbiter_calls == 1
        now[0] += 2
        unchanged = second_runtime.process_release_once()
        assert unchanged.status == "scheduled"
        assert workers.release_arbiter_calls == 1
        decisions = registry.list_events(event_types=("release_plan_decision",))
        assert len(decisions) == 1
        assert decisions[0]["payload"]["semantic_case"]["case_id"] == case_id
        assert decisions[0]["payload"]["semantic_case"]["case_digest"] == case_digest

        second_runtime.maintenance_tick()
        next_refresh = tuple(
            item
            for item in registry.list_outbox_records(
                kinds=("release_candidate_intake",), states=("pending",)
            )
            if item["payload"].get("semantic_case_id") == case_id
        )
        assert len(next_refresh) == 1
        workers.blocked_heads.add(second_head)
        now[0] += 2
        changed = second_runtime.process_release_once()
        assert changed.status == "scheduled"
        assert workers.release_arbiter_calls == 1
        assert len(
            registry.list_events(event_types=("release_plan_superseded",))
        ) == 1
        selected = registry.list_events(event_types=("release_head_reserved",))
        assert selected
        selected_candidate = selected[-1]["payload"]["candidate"]
        assert selected_candidate["pr_head_sha"] in {first_head, second_head}
        assert registry.inspect_locks(kind="release_lane")

        second_runtime.close()
        registry.release_generation(second_fence)
        third_fence = registry.acquire_generation("all-wait-generation-three")
        assert not registry.inspect_locks(), "new generation must rebuild locks from durable heads"
        third_engine = SupervisorEngine(
            registry,
            third_fence,
            supervisor_id="all-wait-supervisor",
            clock=clock,
        )
        third_runtime = _release_runtime(
            third_engine, workspace, workers, clock=clock
        )
        third_runtime.maintenance_tick()
        recovered = registry.inspect_locks(kind="release_lane")
        assert len(recovered) == 1
        assert recovered[0]["owner_task_id"] == selected_candidate["task_id"]
        assert recovered[0]["owner_workstream_id"] == selected_candidate["workstream_id"]
        assert workers.release_arbiter_calls == 1
        third_runtime.close()
        registry.release_generation(third_fence)


def _release_registration_restart_smoke() -> None:
    with TemporaryDirectory(prefix="dcpv2-release-restart-", dir="/tmp") as raw:
        root = Path(raw)
        workspace = root / "managed"
        workspace.mkdir()
        registry = SupervisorRegistry(root / "supervisor.sqlite3", lease_seconds=30)
        first_fence = registry.acquire_generation("release-restart-generation-one")
        first_engine = SupervisorEngine(
            registry, first_fence, supervisor_id="release-restart-supervisor"
        )
        workers = FakeReleaseWorkers()
        first_runtime = _release_runtime(first_engine, workspace, workers)
        passport, stream = _release_registration(
            first_engine, "restart", "module:restart", "src/restart.py"
        )
        head = "1" * 40
        workers.actual_files[head] = ("src/restart.py",)
        queued = _runtime_register_release_candidate(
            first_runtime,
            passport.task_id,
            stream.workstream_id,
            head,
            "register-restart-candidate",
        )
        assert queued["created"] is True
        assert registry.list_outbox_summaries(kinds=("release_candidate_intake",))[0]["state"] == "pending"
        first_runtime.close()
        registry.release_generation(first_fence)

        second_fence = registry.acquire_generation("release-restart-generation-two")
        second_engine = SupervisorEngine(
            registry, second_fence, supervisor_id="release-restart-supervisor"
        )
        second_runtime = _release_runtime(second_engine, workspace, workers)
        assert second_runtime.process_release_once().status == "scheduled"
        assert second_runtime.process_release_once().status == "resolved"
        assert second_runtime.process_release_once().status == "delivered"
        replay = _runtime_register_release_candidate(
            second_runtime,
            passport.task_id,
            stream.workstream_id,
            head,
            "register-restart-candidate",
        )
        assert replay["created"] is False
        assert second_runtime.process_release_once().status == "idle"

        stale_passport, stale_stream = _release_registration(
            second_engine, "stale-truth", "module:stale", "src/stale.py"
        )
        stale_head = "2" * 40
        workers.actual_files[stale_head] = ("src/stale.py",)
        workers.truth_head_override = "3" * 40
        workers.truth_task_revision_override = 2
        _runtime_register_release_candidate(
            second_runtime,
            stale_passport.task_id,
            stale_stream.workstream_id,
            stale_head,
            "register-stale-truth-candidate",
        )
        failed = second_runtime.process_release_once()
        assert failed.status == "retry_scheduled"
        assert not registry.list_events(
            task_id=stale_passport.task_id,
            event_types=("release_reserved", "semantic_release_case"),
        )
        assert not [
            item
            for item in registry.list_outbox_records(kinds=("release_action",))
            if item["task_id"] == stale_passport.task_id
        ]
        second_runtime.close()
        registry.release_generation(second_fence)


def _multi_workstream_multi_pr_restart_smoke() -> None:
    with TemporaryDirectory(prefix="dcpv2-multi-pr-restart-", dir="/tmp") as raw:
        root = Path(raw)
        workspace = root / "managed"
        workspace.mkdir()
        registry = SupervisorRegistry(root / "supervisor.sqlite3", lease_seconds=30)
        first_fence = registry.acquire_generation("multi-pr-restart-one")
        first_engine = SupervisorEngine(
            registry, first_fence, supervisor_id="multi-pr-restart-supervisor"
        )
        task_id = "release-mpr-envelope"
        stream_ids = ("multi-pr-stream-one", "multi-pr-stream-two")
        resources = (
            f"target:{DEV_CONTROL_PLANE_RELEASE_TARGET}",
            "release-lane:multi-pr-logical-lane",
            "module:multi-pr-chain",
        )
        passport = TaskPassport(
            task_id=task_id,
            revision=1,
            title="Multi PR restart handoff",
            objective="Release two already admitted workstreams in one logical lane.",
            expected_result="Second PR continues after restart without registration stimulus.",
            contour="release:production",
            included_scope=("two workstreams",),
            excluded_scope=("real mutation",),
            constraints=("fake only",),
            acceptance=("both receipts",),
            closure=("single acceptance envelope",),
            autonomy=AutonomyEnvelope(
                allowed_actions=(
                    "codex_workspace_mutation",
                    "self_merge",
                    "self_hosted_deploy",
                    "target_lane_release",
                ),
                prohibited_actions=("wb_github_command",),
                human_gate_reasons=("platform_hard_stop",),
            ),
            workstream_ids=stream_ids,
            release_manifest=None,
            resources=resources,
            modules=("module:multi-pr-chain",),
            files=("src/multi_pr_one.py", "src/multi_pr_two.py"),
            dependencies=(),
            multi_pr_intent=True,
            multi_deploy_intent=False,
            curator=CuratorIdentity("multi-pr-curator", "desktop-host"),
            executor=None,
            created_at=NOW,
        )
        streams: list[Workstream] = []
        for index, stream_id in enumerate(stream_ids, start=1):
            executor = ExecutorIdentity(
                f"multi-pr-thread-{index}", "mac-local", "gpt-5.6-sol", "ultra"
            )
            stream = Workstream(
                workstream_id=stream_id,
                task_id=task_id,
                revision=1,
                generation=1,
                root_workstream_id=stream_id,
                corrective_of_generation=None,
                title=f"Multi PR stream {index}",
                objective=passport.objective,
                state="waiting_release",
                executor=executor,
                resources=resources,
                dependencies=(),
                created_at=NOW,
            )
            first_engine.register(
                passport, stream, message_id=f"multi-pr-register-stream-{index}"
            )
            streams.append(stream)
        workers = FakeReleaseWorkers()
        heads = ("4" * 40, "5" * 40)
        workers.actual_files[heads[0]] = ("src/multi_pr_one.py",)
        workers.actual_files[heads[1]] = ("src/multi_pr_two.py",)
        first_runtime = _release_runtime(first_engine, workspace, workers)
        for index, (stream, head) in enumerate(zip(streams, heads), start=1):
            _runtime_register_release_candidate(
                first_runtime,
                task_id,
                stream.workstream_id,
                head,
                f"multi-pr-register-candidate-{index}",
            )
        assert first_runtime.process_release_once().status == "scheduled"
        assert first_runtime.process_release_once().status == "decided"
        assert first_runtime.process_release_once().status == "scheduled"
        assert first_runtime.process_release_once().status == "resolved"
        assert first_runtime.process_release_once().status == "delivered"
        assert workers.release_calls == 1
        first_completed = registry.list_events(
            task_id=task_id, event_types=("release_completed",)
        )
        assert len(first_completed) == 1
        predecessor_workstream = str(first_completed[0]["workstream_id"])
        retained = registry.inspect_locks(kind="release_lane")
        assert len(retained) == 1
        assert retained[0]["owner_workstream_id"] != predecessor_workstream
        first_runtime.close()
        registry.release_generation(first_fence)

        second_fence = registry.acquire_generation("multi-pr-restart-two")
        second_engine = SupervisorEngine(
            registry, second_fence, supervisor_id="multi-pr-restart-supervisor"
        )
        second_runtime = _release_runtime(second_engine, workspace, workers)
        assert second_runtime.process_release_once().status == "resolved"
        assert second_runtime.process_release_once().status == "delivered"
        assert workers.release_calls == 2
        assert workers.release_arbiter_calls == 1
        completed = registry.list_events(
            task_id=task_id, event_types=("release_completed",)
        )
        assert {item["workstream_id"] for item in completed} == set(stream_ids)
        assert predecessor_workstream in stream_ids
        assert len(registry.list_events(event_types=("release_plan_superseded",))) == 1
        second_runtime.close()
        registry.release_generation(second_fence)


def _release_resolution_merged_race_smoke() -> None:
    with TemporaryDirectory(prefix="dcpv2-release-merged-race-", dir="/tmp") as raw:
        root = Path(raw)
        workspace = root / "managed"
        workspace.mkdir()
        registry = SupervisorRegistry(root / "supervisor.sqlite3", lease_seconds=30)
        fence = registry.acquire_generation("release-merged-race-generation")
        engine = SupervisorEngine(
            registry, fence, supervisor_id="release-merged-race-supervisor"
        )
        workers = FakeReleaseWorkers()
        runtime = _release_runtime(engine, workspace, workers)
        passport, stream = _release_registration(
            engine, "merged-race", "module:merged-race", "src/merged_race.py"
        )
        head = "8" * 40
        workers.actual_files[head] = ("src/merged_race.py",)
        _runtime_register_release_candidate(
            runtime,
            passport.task_id,
            stream.workstream_id,
            head,
            "register-merged-race-candidate",
        )
        assert runtime.process_release_once().status == "scheduled"
        assert registry.inspect_locks(kind="release_lane")
        # Exact GitHub truth changes only after intake/reservation. Resolution
        # must fold MERGED into proof-only rather than retrying or mutating.
        workers.merged_heads.add(head)
        proof = runtime.process_release_once()
        assert proof.status == "proof_only_wait"
        assert workers.release_calls == 0
        assert registry.inspect_locks(kind="release_lane")
        _record_fake_task_lane_closure(
            registry,
            fence,
            task_id=passport.task_id,
            task_revision=1,
            workstream_id=stream.workstream_id,
            logical_lane_id="release-task-merged-race",
        )
        engine.tick()
        assert not registry.inspect_locks()
        proof_events = registry.list_events(
            task_id=passport.task_id, event_types=("release_proof_only",)
        )
        assert len(proof_events) == 1
        assert proof_events[0]["payload"]["scheduler_truth"]["pr_state"] == "MERGED"
        assert proof_events[0]["payload"]["scheduler_truth"]["merge_commit_sha"] == "9" * 40
        assert not registry.list_events(
            task_id=passport.task_id,
            event_types=("release_failure_observed", "incident_policy", "release_stalled"),
        )
        assert not [
            item
            for item in registry.list_outbox_records(kinds=("release_action",))
            if item["task_id"] == passport.task_id
        ]
        rows = engine.projection_snapshot()["release_lanes"]
        row = next(item for item in rows if item["task_id"] == passport.task_id)
        assert row["status"] == "merged" and row["deploy_status"] == "proof_only"
        runtime.maintenance_tick()
        assert runtime.process_release_once().status == "idle"
        runtime.close()
        registry.release_generation(fence)


def _release_protected_human_gate_smoke() -> None:
    with TemporaryDirectory(prefix="dcpv2-protected-gate-", dir="/tmp") as raw:
        root = Path(raw)
        workspace = root / "managed"
        workspace.mkdir()
        registry = SupervisorRegistry(root / "supervisor.sqlite3", lease_seconds=30)
        fence = registry.acquire_generation("protected-gate-generation")
        engine = SupervisorEngine(
            registry, fence, supervisor_id="protected-gate-supervisor"
        )
        workers = FakeReleaseWorkers()
        runtime = _release_runtime(engine, workspace, workers)
        passport, stream = _release_registration(
            engine, "protected-gate", "module:controller", "src/controller.py"
        )
        assert "security_permission_change" not in passport.autonomy.human_gate_reasons
        head = "7" * 40
        workers.actual_files[head] = ("src/controller.py",)
        workers.protected_heads.add(head)
        _runtime_register_release_candidate(
            runtime,
            passport.task_id,
            stream.workstream_id,
            head,
            "register-protected-gate-candidate",
        )
        result = runtime.process_release_once()
        assert result.status == "human_gate"
        assert workers.release_calls == 0 and workers.release_arbiter_calls == 0
        attention = [
            item
            for item in registry.list_outbox_records(kinds=("curator_attention",))
            if item["task_id"] == passport.task_id
        ]
        assert len(attention) == 1 and attention[0]["coalescible"] is False
        intake = [
            item
            for item in registry.list_outbox_records(kinds=("release_candidate_intake",))
            if item["task_id"] == passport.task_id
        ]
        assert len(intake) == 1 and intake[0]["state"] == "delivered"
        assert registry.get_task(passport.task_id).state == "parked"
        assert registry.get_workstream(stream.workstream_id).state == "blocked"
        assert runtime.process_release_once().status == "idle"
        runtime.close()
        registry.release_generation(fence)


def _release_wait_refresh_smoke() -> None:
    with TemporaryDirectory(prefix="dcpv2-release-wait-refresh-", dir="/tmp") as raw:
        root = Path(raw)
        workspace = root / "managed"
        workspace.mkdir()
        now = [time.time()]
        clock = lambda: now[0]
        registry = SupervisorRegistry(
            root / "supervisor.sqlite3", lease_seconds=1_000, clock=clock
        )
        fence = registry.acquire_generation("release-wait-refresh-generation")
        engine = SupervisorEngine(
            registry, fence, supervisor_id="release-wait-refresh-supervisor", clock=clock
        )
        workers = FakeReleaseWorkers()
        runtime = _release_runtime(engine, workspace, workers, clock=clock)
        passport, stream = _release_registration(
            engine, "wait-refresh", "module:wait-refresh", "src/wait_refresh.py"
        )
        head = "8" * 40
        workers.actual_files[head] = ("src/wait_refresh.py",)
        workers.blocked_heads.add(head)
        _runtime_register_release_candidate(
            runtime,
            passport.task_id,
            stream.workstream_id,
            head,
            "register-wait-refresh-candidate",
        )
        assert runtime.process_release_once().status == "waiting_candidate"
        assert not registry.list_events(
            task_id=passport.task_id, event_types=("release_reserved",)
        )
        workers.blocked_heads.remove(head)
        now[0] += 2.0
        assert runtime.process_release_once().status == "scheduled"
        assert runtime.process_release_once().status == "resolved"
        assert runtime.process_release_once().status == "delivered"
        runtime.close()
        registry.release_generation(fence)


def _release_nonterminal_observation_smoke() -> None:
    with TemporaryDirectory(prefix="dcpv2-release-observation-", dir="/tmp") as raw:
        root = Path(raw)
        workspace = root / "managed"
        workspace.mkdir()
        registry = SupervisorRegistry(root / "supervisor.sqlite3", lease_seconds=30)
        fence = registry.acquire_generation("release-observation-generation")
        engine = SupervisorEngine(
            registry, fence, supervisor_id="release-observation-supervisor"
        )
        workers = FakeReleaseWorkers()
        runtime = _release_runtime(engine, workspace, workers)
        passport, stream = _release_registration(
            engine, "observation", "module:observation", "src/observation.py"
        )
        head = "4" * 40
        workers.actual_files[head] = ("src/observation.py",)
        _runtime_register_release_candidate(
            runtime,
            passport.task_id,
            stream.workstream_id,
            head,
            "register-observation-candidate",
        )
        assert runtime.process_release_once().status == "scheduled"
        assert runtime.process_release_once().status == "resolved"
        workers.release_observations.append(("waiting_foreign_lane", None, 30.0))
        observed = runtime.process_release_once()
        assert observed.status == "waiting_foreign_lane"
        audit = registry.list_events(
            task_id=passport.task_id, event_types=("release_action_observed",)
        )
        assert len(audit) == 1
        assert audit[0]["payload"]["observation"]["status"] == "waiting_foreign_lane"
        observed_row = next(
            item
            for item in engine.projection_snapshot()["release_lanes"]
            if item["task_id"] == passport.task_id
        )
        assert observed_row["status"] == "ready"
        assert observed_row["deploy_status"] == "waiting_foreign_lane"
        action = next(
            item
            for item in registry.list_outbox_records(kinds=("release_action",))
            if item["task_id"] == passport.task_id
        )
        assert action["state"] == "pending"
        assert not registry.list_events(
            task_id=passport.task_id, event_types=("incident_policy", "release_stalled")
        )
        runtime.close()
        registry.release_generation(fence)


def _release_wait_then_failure_budget_smoke() -> None:
    with TemporaryDirectory(prefix="dcpv2-release-wait-failure-", dir="/tmp") as raw:
        root = Path(raw)
        workspace = root / "managed"
        workspace.mkdir()
        now = [time.time()]
        clock = lambda: now[0]
        registry = SupervisorRegistry(
            root / "supervisor.sqlite3", lease_seconds=10_000, clock=clock
        )
        fence = registry.acquire_generation("release-wait-failure-generation")
        engine = SupervisorEngine(
            registry,
            fence,
            supervisor_id="release-wait-failure-supervisor",
            clock=clock,
        )
        workers = FakeReleaseWorkers()
        runtime = _release_runtime(engine, workspace, workers, clock=clock)
        passport, stream = _release_registration(
            engine, "wait-failure", "module:wait-failure", "src/wait_failure.py"
        )
        head = "7" * 40
        workers.actual_files[head] = ("src/wait_failure.py",)
        _runtime_register_release_candidate(
            runtime,
            passport.task_id,
            stream.workstream_id,
            head,
            "register-wait-failure-candidate",
        )
        assert runtime.process_release_once().status == "scheduled"
        assert runtime.process_release_once().status == "resolved"
        for _index in range(4):
            workers.release_observations.append(("waiting_release", None, 30.0))
            assert runtime.process_release_once().status == "waiting_release"
            now[0] += 31.0
        workers.fail_release = True
        first_failure = runtime.process_release_once()
        assert first_failure.status == "retry_scheduled"
        second_failure = runtime.process_release_once()
        assert second_failure.status == "incident_open"
        failures = registry.list_events(
            task_id=passport.task_id, event_types=("release_failure_observed",)
        )
        assert sorted(item["payload"]["occurrence"] for item in failures) == [1, 2]
        assert len(
            registry.list_events(task_id=passport.task_id, event_types=("incident_policy",))
        ) == 1
        runtime.close()
        registry.release_generation(fence)


def _release_readmission_smoke() -> None:
    with TemporaryDirectory(prefix="dcpv2-release-readmission-", dir="/tmp") as raw:
        root = Path(raw)
        workspace = root / "managed"
        workspace.mkdir()
        registry = SupervisorRegistry(root / "supervisor.sqlite3", lease_seconds=30)
        first_fence = registry.acquire_generation("release-readmission-generation-one")
        first_engine = SupervisorEngine(
            registry, first_fence, supervisor_id="release-readmission-supervisor"
        )
        workers = FakeReleaseWorkers()
        first_runtime = _release_runtime(first_engine, workspace, workers)
        passport, stream = _release_registration(
            first_engine, "readmission", "module:readmission", "src/readmission.py"
        )
        old_head = "5" * 40
        new_head = "6" * 40
        workers.actual_files[old_head] = ("src/readmission.py",)
        workers.actual_files[new_head] = ("src/readmission.py",)
        _runtime_register_release_candidate(
            first_runtime,
            passport.task_id,
            stream.workstream_id,
            old_head,
            "register-readmission-old-head",
        )
        assert first_runtime.process_release_once().status == "scheduled"
        assert first_runtime.process_release_once().status == "resolved"
        workers.release_observations.append(("readmission_required", new_head, None))
        readmission = first_runtime.process_release_once()
        assert readmission.status == "readmission_queued"
        superseded = registry.list_events(
            task_id=passport.task_id, event_types=("release_superseded",)
        )
        assert len(superseded) == 1
        assert superseded[0]["payload"]["pr_head_sha"] == old_head
        assert superseded[0]["payload"]["replacement_head_sha"] == new_head
        readmission_rows = [
            item
            for item in first_engine.projection_snapshot()["release_lanes"]
            if item["task_id"] == passport.task_id
        ]
        assert {item["head_sha"] for item in readmission_rows} == {old_head, new_head}
        assert next(item for item in readmission_rows if item["head_sha"] == old_head)[
            "deploy_status"
        ] == "superseded_readmission"
        assert next(item for item in readmission_rows if item["head_sha"] == new_head)[
            "deploy_status"
        ] == "candidate_registered"
        assert not registry.inspect_locks()
        first_runtime.close()
        registry.release_generation(first_fence)

        second_fence = registry.acquire_generation("release-readmission-generation-two")
        second_engine = SupervisorEngine(
            registry, second_fence, supervisor_id="release-readmission-supervisor"
        )
        second_runtime = _release_runtime(second_engine, workspace, workers)
        second_runtime.maintenance_tick()
        assert not registry.inspect_locks()
        assert second_runtime.process_release_once().status == "scheduled"
        assert second_runtime.process_release_once().status == "resolved"
        assert second_runtime.process_release_once().status == "delivered"
        completed = registry.list_events(
            task_id=passport.task_id, event_types=("release_completed",)
        )
        assert len(completed) == 1
        assert completed[0]["payload"]["receipt"]["pr_head_sha"] == new_head
        assert workers.release_calls == 2
        assert not registry.list_events(
            task_id=passport.task_id, event_types=("incident_policy", "release_stalled")
        )
        second_runtime.close()
        registry.release_generation(second_fence)


def _release_incident_smoke() -> None:
    with TemporaryDirectory(prefix="dcpv2-release-incident-", dir="/tmp") as raw:
        root = Path(raw)
        workspace = root / "managed"
        workspace.mkdir()
        registry = SupervisorRegistry(root / "supervisor.sqlite3", lease_seconds=30)
        fence = registry.acquire_generation("release-incident-generation")
        engine = SupervisorEngine(registry, fence, supervisor_id="release-incident-supervisor")
        workers = FakeReleaseWorkers(fail_release=True)
        runtime = _release_runtime(engine, workspace, workers)
        passport, stream = _release_registration(
            engine, "incident", "module:incident", "src/incident.py"
        )
        head = "d" * 40
        workers.actual_files[head] = ("src/incident.py",)
        _runtime_register_release_candidate(
            runtime, passport.task_id, stream.workstream_id, head, "register-incident-candidate"
        )
        assert runtime.process_release_once().status == "scheduled"
        assert runtime.process_release_once().status == "resolved"
        assert runtime.process_release_once().status == "retry_scheduled"
        assert runtime.process_release_once().status == "incident_open"
        assert workers.release_calls == 2 and workers.incident_arbiter_calls == 0
        assert runtime.process_incident_policy_once().status == "decided"
        application = runtime.process_incident_policy_once()
        assert application.status == "dispatched"
        pending = runtime._latest_incident_state(
            passport.task_id,
            stream.workstream_id,
            next(
                event["payload"]["fingerprint"]
                for event in registry.list_events(
                    task_id=passport.task_id,
                    event_types=("incident_policy",),
                )
                if event["payload"].get("status") == "application_pending"
            ),
        )
        assert pending is not None and pending.arbiter_applied
        assert not pending.resolved and pending.independent_verification is None
        assert workers.incident_arbiter_calls == 1 and workers.application_calls == 1
        assert runtime.process_release_once().status == "resolved"
        assert runtime.process_release_once().status == "parked"
        assert workers.release_calls == 3 and workers.incident_arbiter_calls == 1
        incidents = registry.list_events(task_id=passport.task_id, event_types=("incident_policy",))
        assert any(event["payload"].get("successor_applicable") is False for event in incidents)
        assert registry.get_task(passport.task_id).state == "parked"
        attention = registry.list_outbox_records(kinds=("curator_attention",))
        assert len(attention) == 1 and attention[0]["coalescible"] is False
        runtime.close()
        registry.release_generation(fence)


def _release_incident_crash_reconcile_smoke() -> None:
    """A durable actuator receipt resolves after a crash, never before it."""

    with TemporaryDirectory(prefix="dcpv2-release-incident-crash-", dir="/tmp") as raw:
        root = Path(raw)
        workspace = root / "managed"
        workspace.mkdir()
        registry = SupervisorRegistry(root / "supervisor.sqlite3", lease_seconds=30)
        first_fence = registry.acquire_generation("release-incident-crash-one")
        first_engine = SupervisorEngine(
            registry,
            first_fence,
            supervisor_id="release-incident-crash-supervisor",
        )
        workers = FakeReleaseWorkers(fail_release=True)
        runtime = _release_runtime(first_engine, workspace, workers)
        passport, stream = _release_registration(
            first_engine, "incident-crash", "module:incident-crash", "src/incident_crash.py"
        )
        head = "e" * 40
        workers.actual_files[head] = ("src/incident_crash.py",)
        _runtime_register_release_candidate(
            runtime,
            passport.task_id,
            stream.workstream_id,
            head,
            "register-incident-crash-candidate",
        )
        assert runtime.process_release_once().status == "scheduled"
        assert runtime.process_release_once().status == "resolved"
        assert runtime.process_release_once().status == "retry_scheduled"
        assert runtime.process_release_once().status == "incident_open"
        assert runtime.process_incident_policy_once().status == "decided"
        assert runtime.process_incident_policy_once().status == "dispatched"
        pending_event = next(
            event
            for event in registry.list_events(
                task_id=passport.task_id, event_types=("incident_policy",)
            )
            if event["payload"].get("status") == "application_pending"
        )
        fingerprint = str(pending_event["payload"]["fingerprint"])
        assert runtime.process_release_once().status == "resolved"
        workers.fail_release = False
        # Model a process death after the exact release receipt is durable but
        # before the deterministic incident fold executes.
        runtime._reconcile_incident_applications = lambda: None  # type: ignore[method-assign]
        assert runtime.process_release_once().status == "delivered"
        pending_state = runtime._latest_incident_state(
            passport.task_id, stream.workstream_id, fingerprint
        )
        assert pending_state is not None and pending_state.arbiter_applied
        assert pending_state.independent_verification is None and not pending_state.resolved
        assert len(
            registry.list_events(
                task_id=passport.task_id,
                event_types=("release_completed",),
            )
        ) == 1
        runtime.close()
        registry.release_generation(first_fence)

        second_fence = registry.acquire_generation("release-incident-crash-two")
        second_engine = SupervisorEngine(
            registry,
            second_fence,
            supervisor_id="release-incident-crash-supervisor",
        )
        restarted = _release_runtime(second_engine, workspace, workers)
        restarted.maintenance_tick()
        resolved = restarted._latest_incident_state(
            passport.task_id, stream.workstream_id, fingerprint
        )
        assert resolved is not None and resolved.resolved
        assert resolved.independent_verification == "passed" and not resolved.parked
        assert len(
            registry.list_events(
                task_id=passport.task_id, event_types=("incident_policy",)
            )
        ) >= 4
        assert not registry.list_outbox_records(
            kinds=("curator_attention",), states=("pending", "inflight")
        )
        restarted.close()
        registry.release_generation(second_fence)


def _target_lane_closure_smoke() -> None:
    def contracts(suffix: str, *, multi_pr: bool) -> tuple[TaskPassport, Workstream, tuple[str, ...]]:
        task_id = f"lane-closure-task-{suffix}"
        workstream_id = f"lane-closure-workstream-{suffix}"
        executor = ExecutorIdentity(
            f"lane-closure-thread-{suffix}", "mac-local", "gpt-5.6-sol", "ultra"
        )
        prs = (
            "github-pr-v1:orenvlad-ai/dev-control-plane:201:" + "a" * 40 + ":" + "b" * 40,
            "github-pr-v1:orenvlad-ai/dev-control-plane:202:" + "c" * 40 + ":" + "d" * 40,
        )
        if not multi_pr:
            prs = prs[:1]
        passport = TaskPassport(
            task_id=task_id,
            revision=1,
            title=f"Target lane closure {suffix}",
            objective="Close one exact external logical lane after task closure.",
            expected_result="Durable target lane proof.",
            contour="release:done",
            included_scope=("target lane",),
            excluded_scope=("live mutation",),
            constraints=("fake only",),
            acceptance=("exact lane proof",),
            closure=("task-level barrier",),
            autonomy=AutonomyEnvelope(
                allowed_actions=(
                    "codex_workspace_mutation",
                    "self_merge",
                    "target_lane_release",
                ),
                prohibited_actions=("self_hosted_deploy",),
                human_gate_reasons=("platform_hard_stop",),
            ),
            workstream_ids=(workstream_id,),
            release_manifest=ReleaseClosureManifest(
                logical_lane_id=f"logical-lane-{suffix}",
                pr_identities=prs,
                deploy_identities=(),
                finalized_at=NOW,
            ),
            resources=(
                f"target:{DEV_CONTROL_PLANE_RELEASE_TARGET}",
                f"release-lane:logical-lane-{suffix}",
                f"module:lane-{suffix}",
            ),
            modules=(f"module:lane-{suffix}",),
            files=(f"src/lane_{suffix}.py",),
            dependencies=(),
            multi_pr_intent=multi_pr,
            multi_deploy_intent=False,
            curator=CuratorIdentity(f"lane-closure-curator-{suffix}", "desktop-host"),
            executor=executor,
            created_at=NOW,
        )
        stream = Workstream(
            workstream_id=workstream_id,
            task_id=task_id,
            revision=1,
            generation=1,
            root_workstream_id=workstream_id,
            corrective_of_generation=None,
            title=f"Lane closure stream {suffix}",
            objective=passport.objective,
            state="waiting_release",
            executor=executor,
            resources=passport.resources,
            dependencies=(),
            created_at=NOW,
        )
        return passport, stream, prs

    with TemporaryDirectory(prefix="dcpv2-target-lane-complete-", dir="/tmp") as raw:
        root = Path(raw)
        workspace = root / "managed"
        workspace.mkdir()
        now = [time.time()]
        registry = SupervisorRegistry(
            root / "supervisor.sqlite3", lease_seconds=300, clock=lambda: now[0]
        )
        first_fence = registry.acquire_generation("target-lane-generation-one")
        passport, stream, prs = contracts("complete", multi_pr=True)

        def verifier(_passport: TaskPassport, terminal: TerminalEvidence) -> ContourVerification:
            return ContourVerification(
                verification_id="target-lane-verification",
                task_id=terminal.task_id,
                workstream_id=terminal.workstream_id,
                task_revision=terminal.task_revision,
                workstream_revision=terminal.workstream_revision,
                contour=terminal.closure_kind,
                terminal_digest=terminal_contract_digest(terminal),
                source="github_release_train_readback",
                passed=True,
                checks=("target-lane:passed",),
                evidence=("origin/main exact",),
                verified_at=NOW,
            )

        first_engine = SupervisorEngine(
            registry,
            first_fence,
            supervisor_id="target-lane-supervisor",
            contour_verifier=verifier,
            clock=lambda: now[0],
        )
        initial_passport = replace(passport, release_manifest=None)
        first_engine.register(initial_passport, stream, message_id="target-lane-register")
        callback = FakeTargetLaneClosure(["submitted", "released"])
        release_workers = FakeReleaseWorkers()
        release_workers.contours[passport.task_id] = "release:done"
        release_workers.actual_files["a" * 40] = ("src/lane_complete.py",)
        first_runtime = SupervisorRuntime(
            first_engine,
            allowed_workspace_root=workspace,
            codex_bin="/usr/bin/true",
            release_executor=release_workers.release,
            release_candidate_resolver=release_workers.resolver,
            release_arbiter_executor=release_workers.release_arbiter,
            incident_arbiter_executor=release_workers.incident_arbiter,
            incident_application_executor=release_workers.application,
            target_lane_closure_executor=callback,
            clock=lambda: now[0],
            retry_delay_seconds=0,
        )
        _runtime_register_release_candidate(
            first_runtime,
            passport.task_id,
            stream.workstream_id,
            "a" * 40,
            "target-lane-first-pr-registration",
        )
        assert first_runtime.process_release_once().status == "scheduled"
        assert first_runtime.process_release_once().status == "resolved"
        assert first_runtime.process_release_once().status == "delivered"
        assert registry.inspect_locks(kind="release_lane"), "multi-PR lane was not retained"
        first_runtime.maintenance_tick()
        assert not registry.list_outbox_summaries(kinds=("target_lane_closure",)), (
            "first PR of a multi-PR manifest closed the task lane early"
        )
        release_workers.actual_files["c" * 40] = ("src/lane_complete.py",)
        _runtime_register_release_candidate(
            first_runtime,
            passport.task_id,
            stream.workstream_id,
            "c" * 40,
            "target-lane-second-pr-stale-registration",
        )
        revision = first_runtime.handle_command(
            {
                "contract": COMMAND_CONTRACT,
                "command": "revise_release_manifest",
                "request_id": "target-lane-manifest-revision-request",
                "payload": {
                    "task_id": passport.task_id,
                    "expected_revision": 1,
                    "release_manifest": contract_to_dict(passport.release_manifest),
                    "message_id": "target-lane-manifest-revision-message",
                },
            }
        )["result"]
        assert revision["created"] is True and revision["revision"] == 2
        assert revision["released_reservation_locks"] > 0 and not registry.inspect_locks()
        assert revision["superseded_release_outbox"] >= 1
        assert any(
            item["state"] == "superseded"
            for item in registry.list_outbox_records(kinds=("release_candidate_intake",))
        )
        replay = first_runtime.handle_command(
            {
                "contract": COMMAND_CONTRACT,
                "command": "revise_release_manifest",
                "request_id": "target-lane-manifest-revision-replay",
                "payload": {
                    "task_id": passport.task_id,
                    "expected_revision": 1,
                    "release_manifest": contract_to_dict(passport.release_manifest),
                    "message_id": "target-lane-manifest-revision-message",
                },
            }
        )["result"]
        assert replay["created"] is False and replay["event_id"] == revision["event_id"]
        reordered = ReleaseClosureManifest(
            logical_lane_id=passport.release_manifest.logical_lane_id,  # type: ignore[union-attr]
            pr_identities=tuple(reversed(prs)),
            deploy_identities=(),
            finalized_at="2026-08-05T09:00:00Z",
        )
        try:
            first_runtime.handle_command(
                {
                    "contract": COMMAND_CONTRACT,
                    "command": "revise_release_manifest",
                    "request_id": "target-lane-manifest-reorder-request",
                    "payload": {
                        "task_id": passport.task_id,
                        "expected_revision": 2,
                        "release_manifest": contract_to_dict(reordered),
                        "message_id": "target-lane-manifest-reorder-message",
                    },
                }
            )
        except SupervisorCommandError:
            pass
        else:
            raise AssertionError("release manifest reorder was accepted")
        terminal = TerminalEvidence(
            terminal_id="target-lane-terminal",
            event_id="target-lane-terminal-event",
            task_id=passport.task_id,
            task_revision=2,
            workstream_id=stream.workstream_id,
            workstream_revision=1,
            executor_generation=1,
            executor=stream.executor,  # type: ignore[arg-type]
            closure_kind="release:done",
            summary_ru="Весь multi-PR closure manifest доказан.",
            evidence=("origin/main:" + "d" * 40,),
            checks=("target-lane:passed",),
            pr_identities=prs,
            deploy_identities=(),
            owner_acceptance_required=True,
            created_at=NOW,
        )
        first_engine.import_terminal(terminal, message_id="target-lane-terminal-message")
        first_runtime.maintenance_tick()
        pending = registry.list_outbox_records(kinds=("target_lane_closure",))
        assert len(pending) == 1 and pending[0]["coalescible"] is False
        assert first_engine.projection_snapshot()["release_lanes"][-1]["deploy_status"] == "lane_closure_pending"
        first_runtime.close()
        registry.release_generation(first_fence)

        now[0] += 1
        second_fence = registry.acquire_generation("target-lane-generation-two")
        second_engine = SupervisorEngine(
            registry,
            second_fence,
            supervisor_id="target-lane-supervisor",
            contour_verifier=verifier,
            clock=lambda: now[0],
        )
        second_runtime = SupervisorRuntime(
            second_engine,
            allowed_workspace_root=workspace,
            codex_bin="/usr/bin/true",
            release_executor=lambda _payload, guard: _unused_release(guard),
            release_candidate_resolver=lambda _payload, guard: _unused_resolver(guard),
            release_arbiter_executor=lambda _payload, guard: _unused_arbiter(guard),
            incident_arbiter_executor=lambda _payload, guard: _unused_arbiter(guard),
            incident_application_executor=lambda _payload, guard: _unused_application(guard),
            target_lane_closure_executor=callback,
            clock=lambda: now[0],
            retry_delay_seconds=0,
        )
        second_runtime.maintenance_tick()
        assert second_runtime.process_release_once().status == "stale_discarded"
        current_task = registry.get_task(passport.task_id)
        current_stream = registry.get_workstream(stream.workstream_id)
        assert current_task is not None and current_stream is not None
        registry.update_task_state(
            passport.task_id,
            expected_revision=current_task.revision,
            new_state="waiting_release",
            fence=second_fence,
        )
        registry.update_workstream_state(
            stream.workstream_id,
            current_stream.generation,
            expected_revision=current_stream.revision,
            new_state="technical_complete",
            fence=second_fence,
        )
        assert second_runtime.process_release_once().status == "stale_discarded"
        now[0] += 1
        second_runtime.maintenance_tick()
        submitted = second_runtime.process_release_once()
        assert submitted.status == "submitted"
        assert callback.calls[-1]["task_revision"] == 3
        assert callback.calls[-1]["workstream_revision"] == 2
        assert callback.calls[-1]["anchor_pr_identity"] == prs[0]
        assert callback.calls[-1]["ordered_pr_identities"] == list(prs)
        submitted_rows = second_engine.projection_snapshot()["release_lanes"]
        assert any(row["deploy_status"] == "lane_closure_submitted" for row in submitted_rows)
        now[0] += 2
        released = second_runtime.process_release_once()
        assert released.status == "released"
        assert len(registry.list_events(event_types=("target_lane_closure_completed",))) == 1
        registry.enqueue_outbox(
            "target-lane-completed-result-replay",
            "target_lane_closure",
            callback.calls[-1],
            second_fence,
            task_id=passport.task_id,
            coalescible=False,
        )
        assert second_runtime.process_release_once().status == "deduped"
        released_rows = second_engine.projection_snapshot()["release_lanes"]
        assert any(row["deploy_status"] == "lane_released" for row in released_rows)
        second_runtime.maintenance_tick()
        assert second_runtime.process_release_once().status == "idle"
        assert len(callback.calls) == 2
        second_runtime.close()
        registry.release_generation(second_fence)

    with TemporaryDirectory(prefix="dcpv2-target-lane-single-manifest-", dir="/tmp") as raw:
        root = Path(raw)
        workspace = root / "managed"
        workspace.mkdir()
        registry = SupervisorRegistry(root / "supervisor.sqlite3", lease_seconds=300)
        fence = registry.acquire_generation("target-lane-single-generation")
        final_passport, stream, prs = contracts("single", multi_pr=False)

        def single_verifier(
            _passport: TaskPassport, terminal: TerminalEvidence
        ) -> ContourVerification:
            return ContourVerification(
                verification_id="target-lane-single-verification",
                task_id=terminal.task_id,
                workstream_id=terminal.workstream_id,
                task_revision=terminal.task_revision,
                workstream_revision=terminal.workstream_revision,
                contour=terminal.closure_kind,
                terminal_digest=terminal_contract_digest(terminal),
                source="github_release_train_readback",
                passed=True,
                checks=("target-lane-single:passed",),
                evidence=("origin/main exact",),
                verified_at=NOW,
            )

        engine = SupervisorEngine(
            registry,
            fence,
            supervisor_id="target-lane-single-supervisor",
            contour_verifier=single_verifier,
        )
        engine.register(
            replace(final_passport, release_manifest=None),
            stream,
            message_id="target-lane-single-register",
        )
        terminal = TerminalEvidence(
            terminal_id="target-lane-single-terminal",
            event_id="target-lane-single-terminal-event",
            task_id=final_passport.task_id,
            task_revision=1,
            workstream_id=stream.workstream_id,
            workstream_revision=1,
            executor_generation=1,
            executor=stream.executor,  # type: ignore[arg-type]
            closure_kind="release:done",
            summary_ru="Single PR closure доказан.",
            evidence=("origin/main:" + "b" * 40,),
            checks=("target-lane-single:passed",),
            pr_identities=prs,
            deploy_identities=(),
            owner_acceptance_required=True,
            created_at=NOW,
        )
        try:
            engine.import_terminal(terminal, message_id="target-lane-single-terminal-before-manifest")
        except SupervisorError:
            pass
        else:
            raise AssertionError("release terminal was admitted without a finalized manifest")
        callback = FakeTargetLaneClosure(["released"])
        runtime = SupervisorRuntime(
            engine,
            allowed_workspace_root=workspace,
            codex_bin="/usr/bin/true",
            release_executor=lambda _payload, guard: _unused_release(guard),
            release_candidate_resolver=lambda _payload, guard: _unused_resolver(guard),
            release_arbiter_executor=lambda _payload, guard: _unused_arbiter(guard),
            incident_arbiter_executor=lambda _payload, guard: _unused_arbiter(guard),
            incident_application_executor=lambda _payload, guard: _unused_application(guard),
            target_lane_closure_executor=callback,
            retry_delay_seconds=0,
        )
        revised = runtime.handle_command(
            {
                "contract": COMMAND_CONTRACT,
                "command": "revise_release_manifest",
                "request_id": "target-lane-single-manifest-request",
                "payload": {
                    "task_id": final_passport.task_id,
                    "expected_revision": 1,
                    "release_manifest": contract_to_dict(final_passport.release_manifest),
                    "message_id": "target-lane-single-manifest-message",
                },
            }
        )["result"]
        assert revised["created"] is True and revised["revision"] == 2
        engine.import_terminal(
            replace(terminal, task_revision=2),
            message_id="target-lane-single-terminal-after-manifest",
        )
        events_before_rejected_revision = registry.list_events(
            task_id=final_passport.task_id
        )
        outbox_before_rejected_revision = registry.list_outbox_summaries()
        try:
            runtime.handle_command(
                {
                    "contract": COMMAND_CONTRACT,
                    "command": "revise_release_manifest",
                    "request_id": "target-lane-post-terminal-manifest-request",
                    "payload": {
                        "task_id": final_passport.task_id,
                        "expected_revision": 2,
                        "release_manifest": contract_to_dict(
                            replace(
                                final_passport.release_manifest,
                                finalized_at="2026-08-05T10:00:00Z",
                            )
                        ),
                        "message_id": "target-lane-post-terminal-manifest-message",
                    },
                }
            )
        except SupervisorCommandError:
            pass
        else:
            raise AssertionError("post-terminal manifest revision was accepted")
        assert registry.get_task(final_passport.task_id).revision == 2
        assert registry.list_events(
            task_id=final_passport.task_id
        ) == events_before_rejected_revision
        assert registry.list_outbox_summaries() == outbox_before_rejected_revision
        runtime.maintenance_tick()
        assert runtime.process_release_once().status == "released"
        runtime.maintenance_tick()
        assert runtime.process_release_once().status == "idle"
        assert len(callback.calls) == 1
        assert len(registry.list_events(event_types=("passport_revised",))) == 1
        assert len(registry.list_events(event_types=("target_lane_closure_completed",))) == 1
        runtime.close()
        registry.release_generation(fence)

    with TemporaryDirectory(prefix="dcpv2-target-lane-incident-success-", dir="/tmp") as raw:
        root = Path(raw)
        workspace = root / "managed"
        workspace.mkdir()
        registry = SupervisorRegistry(root / "supervisor.sqlite3", lease_seconds=300)
        fence = registry.acquire_generation("target-lane-incident-success-generation")
        passport, stream, _prs = contracts("ok", multi_pr=False)
        engine = SupervisorEngine(
            registry,
            fence,
            supervisor_id="target-lane-incident-success-supervisor",
            contour_verifier=lambda *_args: (_ for _ in ()).throw(
                AssertionError("unexpected terminal")
            ),
        )
        engine.register(passport, stream, message_id="target-lane-incident-success-register")
        registry.append_event(
            "target-lane-incident-success-source",
            "release_stalled",
            {
                "schema": "dev-control-plane/release-stalled/v2",
                "status": "parked",
                "candidate_id": "target-lane-incident-success-candidate",
                "task_revision": 1,
                "workstream_revision": 1,
                "pr_head_sha": "a" * 40,
                "error_code": "stable_fake_stall",
            },
            fence,
            task_id=passport.task_id,
            workstream_id=stream.workstream_id,
        )
        registry.update_task_state(
            passport.task_id, expected_revision=1, new_state="parked", fence=fence
        )
        registry.update_workstream_state(
            stream.workstream_id,
            1,
            expected_revision=1,
            new_state="parked",
            fence=fence,
        )
        callback = FakeTargetLaneClosure(["error", "error", "parked"])
        policy_workers = FakeReleaseWorkers()
        runtime = SupervisorRuntime(
            engine,
            allowed_workspace_root=workspace,
            codex_bin="/usr/bin/true",
            release_executor=lambda _payload, guard: _unused_release(guard),
            release_candidate_resolver=lambda _payload, guard: _unused_resolver(guard),
            release_arbiter_executor=lambda _payload, guard: _unused_arbiter(guard),
            incident_arbiter_executor=policy_workers.incident_arbiter,
            incident_application_executor=policy_workers.application,
            target_lane_closure_executor=callback,
            retry_delay_seconds=0,
        )
        runtime.maintenance_tick()
        assert runtime.process_release_once().status == "retry_scheduled"
        assert runtime.process_release_once().status == "incident_open"
        assert runtime.process_incident_policy_once().status == "decided"
        assert runtime.process_incident_policy_once().status == "dispatched"
        pending = next(
            event
            for event in registry.list_events(
                task_id=passport.task_id, event_types=("incident_policy",)
            )
            if event["payload"].get("status") == "application_pending"
        )
        assert pending["payload"]["disposition"] == "dispatch_target_lane_once"
        assert runtime.process_release_once().status == "parked"
        resolved = runtime._latest_incident_state(
            passport.task_id,
            stream.workstream_id,
            str(pending["payload"]["fingerprint"]),
        )
        assert resolved is not None and resolved.resolved
        assert resolved.independent_verification == "passed"
        assert len(callback.calls) == 3
        assert policy_workers.incident_arbiter_calls == 1
        assert len(
            registry.list_events(event_types=("target_lane_closure_completed",))
        ) == 1
        assert not registry.list_outbox_records(kinds=("curator_attention",))
        runtime.maintenance_tick()
        assert runtime.process_release_once().status == "idle"
        runtime.close()
        registry.release_generation(fence)

    with TemporaryDirectory(prefix="dcpv2-target-lane-parked-", dir="/tmp") as raw:
        root = Path(raw)
        workspace = root / "managed"
        workspace.mkdir()
        registry = SupervisorRegistry(root / "supervisor.sqlite3", lease_seconds=300)
        fence = registry.acquire_generation("target-lane-parked-generation")
        passport, stream, _prs = contracts("parked", multi_pr=False)
        engine = SupervisorEngine(
            registry,
            fence,
            supervisor_id="target-lane-parked-supervisor",
            contour_verifier=lambda *_args: (_ for _ in ()).throw(AssertionError("unexpected terminal")),
        )
        engine.register(passport, stream, message_id="target-lane-parked-register")
        registry.append_event(
            "target-lane-parked-source",
            "release_stalled",
            {
                "schema": "dev-control-plane/release-stalled/v2",
                "status": "parked",
                "candidate_id": "target-lane-parked-candidate",
                "task_revision": 1,
                "workstream_revision": 1,
                "pr_head_sha": "a" * 40,
                "error_code": "stable_fake_stall",
            },
            fence,
            task_id=passport.task_id,
            workstream_id=stream.workstream_id,
        )
        registry.update_task_state(
            passport.task_id, expected_revision=1, new_state="parked", fence=fence
        )
        registry.update_workstream_state(
            stream.workstream_id,
            1,
            expected_revision=1,
            new_state="parked",
            fence=fence,
        )
        failing = FakeTargetLaneClosure([], fail=True)
        policy_workers = FakeReleaseWorkers()
        runtime = SupervisorRuntime(
            engine,
            allowed_workspace_root=workspace,
            codex_bin="/usr/bin/true",
            release_executor=lambda _payload, guard: _unused_release(guard),
            release_candidate_resolver=lambda _payload, guard: _unused_resolver(guard),
            release_arbiter_executor=lambda _payload, guard: _unused_arbiter(guard),
            incident_arbiter_executor=policy_workers.incident_arbiter,
            incident_application_executor=policy_workers.application,
            target_lane_closure_executor=failing,
            retry_delay_seconds=0,
        )
        runtime.maintenance_tick()
        assert runtime.process_release_once().status == "retry_scheduled"
        assert runtime.process_release_once().status == "incident_open"
        assert runtime.process_incident_policy_once().status == "decided"
        assert runtime.process_incident_policy_once().status == "dispatched"
        assert runtime.process_release_once().status == "parked"
        assert len(failing.calls) == 3
        assert policy_workers.incident_arbiter_calls == 1
        assert policy_workers.application_calls == 1
        assert len(
            registry.list_events(event_types=("target_lane_closure_failure_observed",))
        ) == 3
        assert not registry.list_events(event_types=("target_lane_closure_stalled",))
        attention = [
            item
            for item in registry.list_outbox_records(kinds=("curator_attention",))
            if item["payload"].get("kind") == "serious_stall"
        ]
        assert len(attention) == 1 and attention[0]["coalescible"] is False
        parked_rows = engine.projection_snapshot()["release_lanes"]
        runtime.maintenance_tick()
        assert runtime.process_release_once().status == "idle"
        assert policy_workers.incident_arbiter_calls == 1
        runtime.close()
        registry.release_generation(fence)

    with TemporaryDirectory(prefix="dcpv2-target-lane-arbiter-fail-loop-", dir="/tmp") as raw:
        root = Path(raw)
        workspace = root / "managed"
        workspace.mkdir()
        registry = SupervisorRegistry(root / "supervisor.sqlite3", lease_seconds=300)
        first_fence = registry.acquire_generation("target-lane-loop-generation-one")
        passport, stream, _prs = contracts("arbiter-loop", multi_pr=False)
        first_engine = SupervisorEngine(
            registry,
            first_fence,
            supervisor_id="target-lane-loop-supervisor",
            contour_verifier=lambda *_args: (_ for _ in ()).throw(
                AssertionError("unexpected terminal")
            ),
        )
        first_engine.register(
            passport, stream, message_id="target-lane-loop-register"
        )
        registry.append_event(
            "target-lane-loop-release-source",
            "release_stalled",
            {
                "schema": "dev-control-plane/release-stalled/v2",
                "status": "parked",
                "candidate_id": "target-lane-loop-candidate",
                "task_revision": 1,
                "workstream_revision": 1,
                "pr_head_sha": "a" * 40,
                "error_code": "stable_fake_stall",
            },
            first_fence,
            task_id=passport.task_id,
            workstream_id=stream.workstream_id,
        )
        registry.update_task_state(
            passport.task_id,
            expected_revision=1,
            new_state="parked",
            fence=first_fence,
        )
        registry.update_workstream_state(
            stream.workstream_id,
            1,
            expected_revision=1,
            new_state="parked",
            fence=first_fence,
        )
        failing_closure = FakeTargetLaneClosure([], fail=True)
        arbiter_calls = [0]

        def fail_before_incident_decision(
            _payload: Mapping[str, Any], guard: Any
        ) -> ArbiterDecision:
            guard.checkpoint()
            arbiter_calls[0] += 1
            raise RuntimeError("stable target lane incident arbiter failure")

        first_runtime = SupervisorRuntime(
            first_engine,
            allowed_workspace_root=workspace,
            codex_bin="/usr/bin/true",
            release_executor=lambda _payload, guard: _unused_release(guard),
            release_candidate_resolver=lambda _payload, guard: _unused_resolver(guard),
            release_arbiter_executor=lambda _payload, guard: _unused_arbiter(guard),
            incident_arbiter_executor=fail_before_incident_decision,
            incident_application_executor=lambda _payload, guard: _unused_application(guard),
            target_lane_closure_executor=failing_closure,
            retry_delay_seconds=0,
        )
        first_runtime.maintenance_tick()
        original_action = next(
            event["payload"]
            for event in registry.list_events(
                task_id=passport.task_id,
                event_types=("target_lane_closure_pending",),
            )
        )
        assert first_runtime.process_release_once().status == "retry_scheduled"
        assert first_runtime.process_release_once().status == "incident_open"
        assert first_runtime.process_incident_policy_once().status == "parked"
        duplicate_action = {
            **original_action,
            "supervisor_generation": first_fence.generation + 1,
        }
        registry.enqueue_outbox(
            "target-lane-loop-already-queued-duplicate",
            "target_lane_closure",
            duplicate_action,
            first_fence,
            task_id=passport.task_id,
            coalescible=False,
        )
        first_runtime.close()
        registry.release_generation(first_fence)

        second_fence = registry.acquire_generation("target-lane-loop-generation-two")
        assert second_fence.generation == duplicate_action["supervisor_generation"]
        second_engine = SupervisorEngine(
            registry,
            second_fence,
            supervisor_id="target-lane-loop-supervisor",
            contour_verifier=lambda *_args: (_ for _ in ()).throw(
                AssertionError("unexpected terminal")
            ),
        )
        restarted = SupervisorRuntime(
            second_engine,
            allowed_workspace_root=workspace,
            codex_bin="/usr/bin/true",
            release_executor=lambda _payload, guard: _unused_release(guard),
            release_candidate_resolver=lambda _payload, guard: _unused_resolver(guard),
            release_arbiter_executor=lambda _payload, guard: _unused_arbiter(guard),
            incident_arbiter_executor=fail_before_incident_decision,
            incident_application_executor=lambda _payload, guard: _unused_application(guard),
            target_lane_closure_executor=failing_closure,
            retry_delay_seconds=0,
        )
        restarted.maintenance_tick()
        assert restarted.process_release_once().status == "stale_discarded"
        for _ in range(10):
            restarted.maintenance_tick()
            assert restarted.process_release_once().status == "idle"
            assert restarted.process_incident_policy_once().status == "idle"

        lane_events = registry.list_events(task_id=passport.task_id)
        target_lane_incidents = [
            event
            for event in lane_events
            if event["event_type"] == "incident_policy"
            and event["payload"].get("actor") == "mechanical_target_lane_closure"
        ]
        arbiter_failures = [
            event
            for event in lane_events
            if event["event_type"] == "incident_policy"
            and event["payload"].get("status") == "arbiter_failed_fail_closed"
        ]
        attention = [
            item
            for item in registry.list_outbox_records(kinds=("curator_attention",))
            if item["task_id"] == passport.task_id
            and item["payload"].get("kind") == "serious_stall"
        ]
        assert len(
            [
                event
                for event in lane_events
                if event["event_type"] == "target_lane_closure_pending"
            ]
        ) == 1
        assert len(
            [
                event
                for event in lane_events
                if event["event_type"] == "target_lane_closure_failure_observed"
            ]
        ) == 2
        assert len(target_lane_incidents) == 1
        assert len(arbiter_failures) == 1
        assert len(attention) == 1 and attention[0]["coalescible"] is False
        assert len(
            [
                event
                for event in lane_events
                if event["event_type"] == "target_lane_closure_superseded"
            ]
        ) == 1
        assert len(failing_closure.calls) == 2
        assert arbiter_calls[0] == 1
        restarted.close()
        registry.release_generation(second_fence)


def _release_runtime(
    engine: SupervisorEngine,
    workspace: Path,
    workers: FakeReleaseWorkers,
    *,
    clock: Any = time.time,
) -> SupervisorRuntime:
    return SupervisorRuntime(
        engine,
        allowed_workspace_root=workspace,
        codex_bin="/usr/bin/true",
        release_executor=workers.release,
        release_candidate_resolver=workers.resolver,
        release_arbiter_executor=workers.release_arbiter,
        incident_arbiter_executor=workers.incident_arbiter,
        incident_application_executor=workers.application,
        target_lane_closure_executor=lambda _payload, guard: _unused_lane_closure(guard),
        clock=clock,
        retry_delay_seconds=0,
    )


def _wb_core_parked_admission_closure_smoke() -> None:
    """Historical wb-core r1 admission closes a current parked r2 lane."""

    with TemporaryDirectory(prefix="dcpv2-wb-parked-admission-", dir="/tmp") as raw:
        root = Path(raw)
        workspace = root / "managed"
        workspace.mkdir()
        registry = SupervisorRegistry(root / "supervisor.sqlite3", lease_seconds=300)
        fence = registry.acquire_generation("wb-parked-admission-generation")
        executor = ExecutorIdentity(
            "wb-parked-admission-thread", "mac-local", "gpt-5.6-sol", "ultra"
        )
        passport = TaskPassport(
            task_id="wb-parked-admission-task",
            revision=1,
            title="WB parked admission closure",
            objective="Release one historically admitted wb-core lane after local parking.",
            expected_result="One exact parked target-lane receipt.",
            contour="release:done",
            included_scope=("wb-core lane",),
            excluded_scope=("product mutation",),
            constraints=("fake only",),
            acceptance=("historical admission remains exact",),
            closure=("parked lane released",),
            autonomy=AutonomyEnvelope(
                allowed_actions=(
                    "codex_workspace_mutation",
                    "wb_github_command",
                    "target_lane_release",
                ),
                prohibited_actions=("self_hosted_deploy",),
                human_gate_reasons=("platform_hard_stop",),
            ),
            workstream_ids=("wb-parked-admission-workstream",),
            release_manifest=None,
            resources=(
                f"target:{WB_CORE_REPOSITORY}",
                "release-lane:wb-parked-logical-lane",
                "module:wb-parked-admission",
            ),
            modules=("module:wb-parked-admission",),
            files=("src/wb_parked_admission.py",),
            dependencies=(),
            multi_pr_intent=False,
            multi_deploy_intent=False,
            curator=CuratorIdentity("wb-parked-admission-curator", "desktop-host"),
            executor=executor,
            created_at=NOW,
        )
        stream = Workstream(
            workstream_id="wb-parked-admission-workstream",
            task_id=passport.task_id,
            revision=1,
            generation=1,
            root_workstream_id="wb-parked-admission-workstream",
            corrective_of_generation=None,
            title="WB parked admission stream",
            objective=passport.objective,
            state="waiting_release",
            executor=executor,
            resources=passport.resources,
            dependencies=(),
            created_at=NOW,
        )
        engine = SupervisorEngine(
            registry,
            fence,
            supervisor_id="wb-parked-admission-supervisor",
            contour_verifier=lambda *_args: (_ for _ in ()).throw(
                AssertionError("unexpected terminal")
            ),
        )
        engine.register(passport, stream, message_id="wb-parked-admission-register")
        head = "1" * 40
        proof = WbCoreAdmissionProof(
            pr_number=501,
            owner_pr=501,
            head_sha=head,
            target_task_id=derive_wb_core_target_task_id(passport.task_id),
            task_revision=1,
            passport_digest="2" * 64,
        )
        admission = WbCoreAdmissionBinding.from_proof(proof)
        candidate = SchedulerReleaseCandidate(
            candidate_id="wb-parked-admission-candidate",
            task_id=passport.task_id,
            workstream_id=stream.workstream_id,
            logical_lane_id="wb-parked-logical-lane",
            target_id=WB_CORE_REPOSITORY,
            task_revision=1,
            workstream_revision=1,
            pr_head_sha=head,
            resources=("module:wb-parked-admission",),
            passport_files=("src/wb_parked_admission.py",),
            diff_files=("src/wb_parked_admission.py",),
            modules=("module:wb-parked-admission",),
            ready_since=NOW,
            created_at=NOW,
        )
        release_candidate = ReleaseTrainCandidate(
            lane_id="wb-parked-logical-lane",
            task_id=passport.task_id,
            workstream_id=stream.workstream_id,
            revision=1,
            repo=WB_CORE_REPOSITORY,
            pr_number=501,
            expected_head_sha=head,
            base_ref="main",
            required_checks=("wb-core-release-train",),
            declared_files=("src/wb_parked_admission.py",),
            resources=("module:wb-parked-admission",),
        )
        registry.acquire_scheduler_reservation(
            task_id=passport.task_id,
            workstream_id=stream.workstream_id,
            target_id=WB_CORE_REPOSITORY,
            resources=candidate.resources,
            fence=fence,
            ttl=300,
        )
        action_event_id = "wb-parked-admission-release-action"
        action_payload = {
            "schema": "dev-control-plane/release-action/v2",
            "candidate": asdict(candidate),
            "release_candidate": asdict(release_candidate),
            "target_adapter": WB_CORE_TARGET_ADAPTER,
            "reservation_event_id": "wb-parked-admission-seed",
            "task_revision": 1,
            "workstream_revision": 1,
            "pr_head_sha": head,
            "remediation_decision_id": None,
        }
        registry.record_input_event_outbox(
            message_id="wb-parked-admission-seed-message",
            source="runtime-smoke",
            input_payload={"action_event_id": action_event_id},
            event_id="wb-parked-admission-seed",
            event_type="release_candidate_resolved",
            event_payload={
                "schema": "dev-control-plane/release-candidate-resolved-event/v2",
                "candidate": asdict(candidate),
                "target_adapter": WB_CORE_TARGET_ADAPTER,
                "release_candidate": asdict(release_candidate),
            },
            outbox_items=(
                {
                    "event_id": action_event_id,
                    "kind": "release_action",
                    "payload": action_payload,
                    "task_id": passport.task_id,
                    "coalescible": False,
                    "coalesce_key": None,
                },
            ),
            fence=fence,
            task_id=passport.task_id,
            workstream_id=stream.workstream_id,
        )

        def admitted_observation(
            payload: Mapping[str, Any], guard: Any
        ) -> Mapping[str, Any]:
            guard.checkpoint()
            guard.checkpoint()
            observed = payload["candidate"]
            return {
                "schema": "dev-control-plane/release-action-observation/v2",
                "status": "admitted",
                "reason_code": "exact_admission_proven",
                "candidate_id": observed["candidate_id"],
                "task_id": observed["task_id"],
                "workstream_id": observed["workstream_id"],
                "task_revision": observed["task_revision"],
                "workstream_revision": observed["workstream_revision"],
                "expected_head_sha": head,
                "observed_head_sha": head,
                "retry_after_seconds": 30.0,
                "observed_at": NOW,
                "evidence": [f"admission:sha256:{admission.proof_digest}"],
                "admission_binding": asdict(admission),
            }

        callback = FakeTargetLaneClosure(["parked"])
        runtime = SupervisorRuntime(
            engine,
            allowed_workspace_root=workspace,
            codex_bin="/usr/bin/true",
            release_executor=admitted_observation,
            target_lane_closure_executor=callback,
            require_automation_workers=False,
            retry_delay_seconds=0,
        )
        assert runtime.process_release_once().status == "admitted"
        observed_events = registry.list_events(
            task_id=passport.task_id, event_types=("release_action_observed",)
        )
        assert len(observed_events) == 1
        assert observed_events[0]["payload"]["observation"][
            "admission_binding"
        ] == asdict(admission)
        registry.append_event(
            "wb-parked-admission-source",
            "release_stalled",
            {
                "schema": "dev-control-plane/release-stalled/v2",
                "status": "parked",
                "candidate_id": candidate.candidate_id,
                "task_revision": 1,
                "workstream_revision": 1,
                "pr_head_sha": head,
                "error_code": "external_target_stall",
            },
            fence,
            task_id=passport.task_id,
            workstream_id=stream.workstream_id,
        )
        registry.update_workstream_state(
            stream.workstream_id,
            1,
            expected_revision=1,
            new_state="parked",
            fence=fence,
        )
        registry.update_task_state(
            passport.task_id,
            expected_revision=1,
            new_state="parked",
            fence=fence,
        )
        runtime.maintenance_tick()
        pending = registry.list_outbox_records(
            kinds=("target_lane_closure",), states=("pending",)
        )
        assert len(pending) == 1
        action = pending[0]["payload"]
        assert action["binding_kind"] == "parked_admission"
        assert action["task_revision"] == 2
        assert action["workstream_revision"] == 2
        parked_admission = action["parked_admission"]
        assert parked_admission["admission_task_revision"] == 1
        assert parked_admission["admission_workstream_revision"] == 1
        assert parked_admission["release_action_event_id"] == action_event_id
        assert parked_admission["admission_binding"] == asdict(admission)
        assert runtime.process_release_once().status == "parked"
        assert len(callback.calls) == 1
        assert callback.calls[0]["binding_kind"] == "parked_admission"
        parked_rows = [
            item
            for item in engine.projection_snapshot()["release_lanes"]
            if item["task_id"] == passport.task_id
        ]
        parked_row = next(
            item for item in parked_rows if item["head_sha"] == head
        )
        assert parked_row["deploy_status"] == "lane_closure_parked"
        assert parked_row["pr_url"].endswith("/pull/501")
        assert runtime._target_lane_ready_for_attention(passport.task_id, 2)
        runtime.close()
        registry.release_generation(fence)


def _manifest_revision_lock_smoke() -> None:
    """A manifest CAS never revokes the locks of a live model wait."""

    with TemporaryDirectory(prefix="dcpv2-manifest-lock-", dir="/tmp") as raw:
        root = Path(raw)
        workspace = root / "managed"
        workspace.mkdir()
        registry = SupervisorRegistry(root / "state" / "supervisor.sqlite3")
        fence = registry.acquire_generation("manifest-lock-generation")
        engine = SupervisorEngine(
            registry,
            fence,
            supervisor_id="manifest-lock-supervisor",
            contour_verifier=lambda *_args: (_ for _ in ()).throw(
                AssertionError("unexpected terminal")
            ),
        )
        passport, stream = _release_registration(
            engine,
            "manifest-lock",
            "module:shared-manifest-lock",
            "src/manifest_lock.py",
        )
        workers = FakeReleaseWorkers()
        runtime = _release_runtime(engine, workspace, workers)
        manifest = ReleaseClosureManifest(
            logical_lane_id="release-task-manifest-lock",
            pr_identities=(
                "github-pr-v1:orenvlad-ai/dev-control-plane:991:"
                + "a" * 40
                + ":"
                + "b" * 40,
            ),
            deploy_identities=(
                "hosted-release-v1:wb-core-eu-root:devcontrol.pro:" + "b" * 40,
            ),
            finalized_at=NOW,
        )
        execution = registry.acquire_execution_reservation(
            task_id=passport.task_id,
            workstream_id=stream.workstream_id,
            thread_id=stream.executor.thread_id,  # type: ignore[union-attr]
            workspace_id="workspace-manifest-lock",
            resources=("module:shared-manifest-lock",),
            fence=fence,
            ttl=120,
        )
        request = {
            "contract": COMMAND_CONTRACT,
            "command": "revise_release_manifest",
            "request_id": "manifest-lock-revision-request",
            "payload": {
                "task_id": passport.task_id,
                "expected_revision": 1,
                "release_manifest": contract_to_dict(manifest),
                "message_id": "manifest-lock-revision-message",
            },
        }
        try:
            runtime.handle_command(request)
        except LockConflict:
            pass
        else:
            raise AssertionError("manifest revision revoked a live execution reservation")
        observed = {
            (item["lock_kind"], item["lock_key"])
            for item in registry.inspect_locks()
            if item["owner_task_id"] == passport.task_id
        }
        assert {
            ("task", passport.task_id),
            ("thread", stream.executor.thread_id),  # type: ignore[union-attr]
            ("workspace", "workspace-manifest-lock"),
            ("resource", "module:shared-manifest-lock"),
        } <= observed
        try:
            registry.acquire_resource_locks(
                ("module:shared-manifest-lock",),
                "competing-manifest-task",
                fence,
                ttl=30,
            )
        except LockConflict:
            pass
        else:
            raise AssertionError("competing shared-resource mutation overlapped the model wait")
        registry.release_execution_reservation(execution, fence)
        registry.acquire_scheduler_reservation(
            task_id=passport.task_id,
            workstream_id=stream.workstream_id,
            target_id="dev-control-plane",
            resources=("module:shared-manifest-lock",),
            fence=fence,
            ttl=120,
        )
        revised = runtime.handle_command(request)["result"]
        assert revised["revision"] == 2 and revised["released_reservation_locks"] == 3
        assert not [
            item
            for item in registry.inspect_locks()
            if item["owner_task_id"] == passport.task_id
        ]
        runtime.close()
        registry.release_generation(fence)


def _anti_loop_successor_cause_smoke() -> None:
    """One successor preserves its root and never recursively creates another."""

    with TemporaryDirectory(prefix="dcpv2-successor-cause-", dir="/tmp") as raw:
        root = Path(raw)
        workspace = root / "managed"
        workspace.mkdir()
        registry = SupervisorRegistry(root / "state" / "supervisor.sqlite3")
        fence = registry.acquire_generation("successor-cause-generation-one")
        engine = SupervisorEngine(
            registry,
            fence,
            supervisor_id="successor-cause-supervisor",
            contour_verifier=lambda *_args: (_ for _ in ()).throw(
                AssertionError("unexpected terminal")
            ),
        )
        workers = FakeReleaseWorkers()
        runtime = _release_runtime(engine, workspace, workers)

        def reserved_successor(suffix: str) -> tuple[TaskPassport, Workstream, Any, str]:
            passport, stream = _release_registration(
                engine,
                suffix,
                f"module:{suffix}",
                f"src/{suffix.replace('-', '_')}.py",
            )
            assert stream.executor is not None
            checkpoint = Checkpoint(
                checkpoint_id=f"checkpoint-{suffix}",
                event_id=f"checkpoint-event-{suffix}",
                task_id=passport.task_id,
                task_revision=1,
                workstream_id=stream.workstream_id,
                workstream_revision=1,
                executor_generation=1,
                executor=stream.executor,
                progress_stage=15,
                delta_ru="Проверена исходная сеть.",
                current_ru="Готовится bounded retry.",
                evidence=("fresh_network_truth",),
                created_at=NOW,
            )
            engine.import_checkpoint(checkpoint, message_id=f"checkpoint-input-{suffix}")
            task_workspace = workspace / suffix
            task_workspace.mkdir()
            registry.bind_workspace(
                task_id=passport.task_id,
                workstream_id=stream.workstream_id,
                canonical_path=str(task_workspace.resolve()),
                fence=fence,
            )
            runtime.handle_command(
                {
                    "contract": COMMAND_CONTRACT,
                    "command": "codex_followup",
                    "request_id": f"followup-request-{suffix}",
                    "payload": {
                        "task_id": passport.task_id,
                        "workstream_id": stream.workstream_id,
                        "prompt": "Continue the exact bounded work.",
                        "output_contract": "checkpoint",
                        "cwd": str(task_workspace),
                        "terminal_context": None,
                        "call_policy": "standard",
                        "message_id": f"followup-message-{suffix}",
                    },
                }
            )
            for attempt in ("first", "second"):
                followup = registry.claim_outbox(
                    fence,
                    worker_id=f"{suffix}-{attempt}",
                    limit=1,
                    visibility_timeout=30,
                    kinds=("codex_followup",),
                )[0]
                result = runtime._handle_worker_failure(
                    followup,
                    CodexDisconnectedError("bounded network unavailable"),
                    task_id=passport.task_id,
                    workstream_id=stream.workstream_id,
                )
            assert result.status == "start_successor_executor"
            successor = next(
                item
                for item in registry.claim_outbox(
                    fence,
                    worker_id=f"{suffix}-successor",
                    limit=2,
                    visibility_timeout=30,
                    kinds=("codex_successor_start",),
                )
                if item.task_id == passport.task_id
            )
            return passport, stream, successor, str(successor.payload["causal_fingerprint"])

        same_passport, same_stream, same_message, same_fingerprint = reserved_successor(
            "same-net"
        )
        same_result = runtime._handle_worker_failure(
            same_message,
            CodexDisconnectedError("bounded network unavailable"),
            task_id=same_passport.task_id,
            workstream_id=same_stream.workstream_id,
        )
        assert same_result.status == "invoke_incident_arbiter"
        assert runtime.process_incident_policy_once().status == "decided"

        changed_passport, changed_stream, changed_message, changed_root = reserved_successor(
            "changed-net"
        )
        changed_first = runtime._handle_worker_failure(
            changed_message,
            CodexContractError("successor checkpoint schema is invalid"),
            task_id=changed_passport.task_id,
            workstream_id=changed_stream.workstream_id,
        )
        assert changed_first.status == "retry_scheduled"
        changed_retry = next(
            item
            for item in registry.claim_outbox(
                fence,
                worker_id="successor-changed-retry",
                limit=2,
                visibility_timeout=30,
                kinds=("codex_successor_start",),
            )
            if item.task_id == changed_passport.task_id
        )
        changed_second = runtime._handle_worker_failure(
            changed_retry,
            CodexContractError("successor checkpoint schema is invalid"),
            task_id=changed_passport.task_id,
            workstream_id=changed_stream.workstream_id,
        )
        assert changed_second.status == "invoke_incident_arbiter"
        assert runtime.process_incident_policy_once().status == "decided"
        assert workers.incident_arbiter_calls == 2

        successor_rows = registry.list_outbox_records(kinds=("codex_successor_start",))
        for passport in (same_passport, changed_passport):
            owned = [item for item in successor_rows if item["task_id"] == passport.task_id]
            assert len(owned) == 1 and owned[0]["state"] == "delivered"
        assert runtime.process_codex_once().status == "idle"
        runtime.maintenance_tick()
        assert len(registry.list_outbox_records(kinds=("codex_successor_start",))) == 2

        same_state = runtime._latest_incident_state(
            same_passport.task_id, same_stream.workstream_id, same_fingerprint
        )
        assert same_state is not None
        assert same_state.failure_count == 3 and same_state.incident_case_id is not None
        changed_states = [
            event["payload"]["incident_state"]
            for event in registry.list_events(
                task_id=changed_passport.task_id,
                workstream_id=changed_stream.workstream_id,
                event_types=("incident_policy",),
            )
            if isinstance(event.get("payload", {}).get("incident_state"), Mapping)
        ]
        changed_fingerprint = next(
            item["fingerprint"]
            for item in changed_states
            if item["fingerprint"] != changed_root
        )
        changed_state = runtime._latest_incident_state(
            changed_passport.task_id,
            changed_stream.workstream_id,
            changed_fingerprint,
        )
        assert changed_state is not None
        assert changed_state.failure_count == 2 and changed_state.incident_case_id is not None
        assert runtime.process_incident_policy_once().status == "parked"
        assert runtime.process_incident_policy_once().status == "parked"
        assert workers.application_calls == 2
        assert runtime.process_incident_policy_once().status == "idle"
        attention = registry.list_outbox_records(kinds=("curator_attention",))
        for passport in (same_passport, changed_passport):
            assert len([item for item in attention if item["task_id"] == passport.task_id]) == 1
        assert workers.incident_arbiter_calls == 2

        runtime.close()
        registry.release_generation(fence)
        second_fence = registry.acquire_generation("successor-cause-generation-two")
        second_engine = SupervisorEngine(
            registry,
            second_fence,
            supervisor_id="successor-cause-supervisor",
            contour_verifier=lambda *_args: (_ for _ in ()).throw(
                AssertionError("unexpected terminal")
            ),
        )
        restarted = _release_runtime(
            second_engine, workspace, FakeReleaseWorkers()
        )
        durable = restarted._latest_incident_state(
            changed_passport.task_id, changed_stream.workstream_id, changed_fingerprint
        )
        assert durable is not None
        assert durable.failure_count == 2 and durable.incident_case_id is not None
        restarted.maintenance_tick()
        assert restarted.process_codex_once().status == "idle"
        assert len(registry.list_outbox_records(kinds=("codex_successor_start",))) == 2
        restarted.close()
        registry.release_generation(second_fence)


def _release_registration(
    engine: SupervisorEngine,
    suffix: str,
    resource: str,
    file_name: str,
) -> tuple[TaskPassport, Workstream]:
    task_id = f"release-task-{suffix}"
    workstream_id = f"workstream-release-{suffix}"
    executor = ExecutorIdentity(f"thread-release-{suffix}", "mac-local", "gpt-5.6-sol", "ultra")
    passport = TaskPassport(
        task_id=task_id,
        revision=1,
        title=f"Release {suffix}",
        objective="Prove autonomous release orchestration.",
        expected_result="One bounded fake release.",
        contour="release:production",
        included_scope=(file_name,),
        excluded_scope=("live mutation",),
        constraints=("fake only",),
        acceptance=("release receipt",),
        closure=("production proof",),
        autonomy=AutonomyEnvelope(
            allowed_actions=(
                "codex_workspace_mutation",
                "self_merge",
                "self_hosted_deploy",
                "target_lane_release",
            ),
            prohibited_actions=("wb_github_command",),
            human_gate_reasons=("platform_hard_stop",),
        ),
        workstream_ids=(workstream_id,),
        release_manifest=None,
        resources=(
            f"target:{DEV_CONTROL_PLANE_RELEASE_TARGET}",
            f"release-lane:release-task-{suffix}",
            resource,
        ),
        modules=(resource,),
        files=(file_name,),
        dependencies=(),
        multi_pr_intent=False,
        multi_deploy_intent=False,
        curator=CuratorIdentity(f"curator-{suffix}", "desktop-host"),
        executor=executor,
        created_at=NOW,
    )
    stream = Workstream(
        workstream_id=workstream_id,
        task_id=task_id,
        revision=1,
        generation=1,
        root_workstream_id=workstream_id,
        corrective_of_generation=None,
        title=f"Release stream {suffix}",
        objective=passport.objective,
        state="waiting_release",
        executor=executor,
        resources=passport.resources,
        dependencies=(),
        created_at=NOW,
    )
    engine.register(passport, stream, message_id=f"register-{suffix}")
    return passport, stream


def _runtime_register_release_candidate(
    runtime: SupervisorRuntime,
    task_id: str,
    workstream_id: str,
    head_sha: str,
    message_id: str,
) -> Mapping[str, Any]:
    return runtime.handle_command(
        {
            "contract": COMMAND_CONTRACT,
            "command": "register_release_candidate",
            "request_id": f"request-{message_id}",
            "payload": {
                "task_id": task_id,
                "workstream_id": workstream_id,
                "expected_pr_head_sha": head_sha,
                "message_id": message_id,
            },
        }
    )["result"]


def _binding(candidate: Mapping[str, Any]) -> RevisionBinding:
    return RevisionBinding(
        task_id=candidate["task_id"],
        task_revision=candidate["task_revision"],
        workstream_id=candidate["workstream_id"],
        workstream_revision=candidate["workstream_revision"],
        pr_head_sha=candidate["pr_head_sha"],
        resources=tuple(candidate["resources"]),
    )


def _runtime(
    registry: SupervisorRegistry,
    fence: Any,
    workspace: Path,
    shared: FakeCodexState,
    *,
    owner_action_verifier: Any = None,
    client_type: type[FakeCodexClient] = FakeCodexClient,
) -> SupervisorRuntime:
    engine = SupervisorEngine(
        registry,
        fence,
        supervisor_id=stable_supervisor_id(str(registry.db_path.parent)),
        contour_verifier=lambda *_args: (_ for _ in ()).throw(AssertionError("unexpected terminal")),
    )
    return SupervisorRuntime(
        engine,
        allowed_workspace_root=workspace,
        codex_client_factory=lambda **kwargs: client_type(shared, **kwargs),
        codex_bin="/usr/bin/true",
        release_executor=lambda _payload, guard: _unused_release(guard),
        release_candidate_resolver=lambda _payload, guard: _unused_resolver(guard),
        release_arbiter_executor=lambda _payload, guard: _unused_arbiter(guard),
        incident_arbiter_executor=lambda _payload, guard: _unused_arbiter(guard),
        incident_application_executor=lambda _payload, guard: _unused_application(guard),
        target_lane_closure_executor=lambda _payload, guard: _unused_lane_closure(guard),
        owner_action_verifier=owner_action_verifier,
        retry_delay_seconds=0,
        visibility_timeout_seconds=2,
        execution_lock_ttl_seconds=0.15,
    )


def _contracts() -> tuple[TaskPassport, Workstream]:
    passport = TaskPassport(
        task_id="task-runtime-smoke",
        revision=1,
        title="Runtime composition smoke",
        objective="Prove exact daemon composition.",
        expected_result="One exact persistent executor and durable checkpoint.",
        contour="diagnostic",
        included_scope=("runtime",),
        excluded_scope=("real model", "real release"),
        constraints=("fake-only",),
        acceptance=("runtime smoke passes",),
        closure=("diagnostic proof",),
        autonomy=AutonomyEnvelope(
            allowed_actions=("codex_workspace_mutation",),
            prohibited_actions=("self_hosted_deploy",),
            human_gate_reasons=("platform_hard_stop",),
        ),
        workstream_ids=("workstream-runtime-smoke",),
        release_manifest=None,
        resources=("repo:runtime-smoke", "module:runtime"),
        modules=("module:runtime",),
        files=("src/dev_control_plane/supervisor_runtime.py",),
        dependencies=(),
        multi_pr_intent=False,
        multi_deploy_intent=False,
        curator=CuratorIdentity("curator-runtime-smoke", "desktop-host"),
        executor=None,
        created_at=NOW,
    )
    workstream = Workstream(
        workstream_id="workstream-runtime-smoke",
        task_id=passport.task_id,
        revision=1,
        generation=1,
        root_workstream_id="workstream-runtime-smoke",
        corrective_of_generation=None,
        title="Runtime workstream",
        objective=passport.objective,
        state="started",
        executor=None,
        resources=passport.resources,
        dependencies=(),
        created_at=NOW,
    )
    return passport, workstream


class SlowPublisher:
    def publish_available(self, *_args: Any, **_kwargs: Any) -> tuple[Any, ...]:
        time.sleep(0.65)
        return ()


def _corrective_generation_recovery_smoke() -> None:
    with TemporaryDirectory(prefix="dcpv2-corrective-", dir="/tmp") as raw:
        root = Path(raw)
        workspace_root = root / "managed"
        workspace_root.mkdir()
        workspace = workspace_root / "task"
        workspace.mkdir()
        key_path = root / "owner-action.key"
        key = b"corrective-owner-action-key-material-32-bytes"
        key_path.write_bytes(key)
        key_path.chmod(0o600)
        registry = SupervisorRegistry(root / "supervisor.sqlite3", lease_seconds=30)
        fence = registry.acquire_generation("corrective-generation-one")
        _current_fence_holder[:] = [fence]
        shared = FakeCodexState(registry)
        runtime = _runtime(
            registry,
            fence,
            workspace_root,
            shared,
            owner_action_verifier=OwnerActionAttestationVerifier(key_path),
        )
        passport, stream = _contracts()
        runtime.handle_command(
            {
                "contract": COMMAND_CONTRACT,
                "command": "start_executor",
                "request_id": "corrective-start-request",
                "payload": {
                    "passport": contract_to_dict(passport),
                    "workstream": contract_to_dict(stream),
                    "cwd": str(workspace),
                    "message_id": "corrective-start-message",
                },
            }
        )
        assert runtime.process_codex_once().status == "registered"
        executor = registry.current_executor(passport.task_id, stream.workstream_id)
        assert executor is not None
        exact_executor = ExecutorIdentity(
            executor.thread_id, executor.host_id, executor.model, executor.reasoning
        )
        checkpoint = Checkpoint(
            checkpoint_id="corrective-checkpoint",
            event_id="corrective-checkpoint-event",
            task_id=passport.task_id,
            task_revision=1,
            workstream_id=stream.workstream_id,
            workstream_revision=1,
            executor_generation=1,
            executor=exact_executor,
            progress_stage=15,
            delta_ru="Зафиксирован проверенный checkpoint.",
            current_ru="Ожидается human-only действие.",
            evidence=("corrective:checkpoint",),
            created_at=NOW,
        )
        runtime.engine.import_checkpoint(
            checkpoint, message_id="corrective-checkpoint-message"
        )
        attention_event_id = "corrective-human-attention-event"
        trigger_payload = {
            "schema": "dev-control-plane/human-gate-event/v2",
            "revision": 1,
            "status": "human_gate",
            "fingerprint": hashlib.sha256(b"corrective-human-gate").hexdigest(),
            "summary": "Доказан human-only blocker.",
            "decision": "park_workstream",
            "attempt": 1,
            "reason_code": "platform_hard_stop",
            "requested_action": "Разрешить точное продолжение corrective generation",
            "attention_event_id": attention_event_id,
            "prerequisite_event_id": "corrective-checkpoint-event",
            "updated_at": NOW,
        }
        trigger_event_id = "corrective-human-gate-event"
        registry.enqueue_outbox(
            attention_event_id,
            "curator_attention",
            {
                "schema": "dev-control-plane/curator-attention/v2",
                "attention_id": "corrective-human-attention",
                "task_id": passport.task_id,
                "workstream_id": stream.workstream_id,
                "curator_thread_id": passport.curator.thread_id,
                "kind": "human_gate",
                "handoff_ru": "Статус: Блокер",
                "required_action": trigger_payload["requested_action"],
                "created_at": NOW,
            },
            fence,
            task_id=passport.task_id,
        )
        registry.append_event(
            trigger_event_id,
            "incident_policy",
            trigger_payload,
            fence,
            task_id=passport.task_id,
            workstream_id=stream.workstream_id,
            executor_generation=1,
        )
        parked_task = registry.update_task_state(
            passport.task_id,
            expected_revision=1,
            new_state="parked",
            fence=fence,
        )
        parked_stream = registry.update_workstream_state(
            stream.workstream_id,
            1,
            expected_revision=1,
            new_state="blocked",
            fence=fence,
        )
        trigger_digest = hashlib.sha256(
            json.dumps(
                trigger_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        replacement = replace(passport, revision=parked_task.revision + 1)
        corrective = replace(
            stream,
            revision=1,
            generation=2,
            corrective_of_generation=1,
            state="recovering",
            executor=None,
        )
        attestation = {
            "schema": OWNER_ACTION_ATTESTATION_SCHEMA,
            "trigger_event_id": trigger_event_id,
            "trigger_event_digest": trigger_digest,
            "task_id": passport.task_id,
            "task_revision": parked_task.revision,
            "workstream_id": stream.workstream_id,
            "workstream_generation": parked_stream.generation,
            "workstream_revision": parked_stream.revision,
            "curator_thread_id": passport.curator.thread_id,
            "requested_action": trigger_payload["requested_action"],
            "action_sha256": hashlib.sha256(
                trigger_payload["requested_action"].encode()
            ).hexdigest(),
            "source_message_id": "corrective-owner-source-message",
            "observed_at_epoch": time.time(),
            "signature": "",
        }
        attestation["signature"] = owner_action_attestation_signature(key, attestation)
        recovery_payload = {
            "task_id": passport.task_id,
            "expected_task_revision": parked_task.revision,
            "workstream_id": stream.workstream_id,
            "expected_workstream_generation": parked_stream.generation,
            "expected_workstream_revision": parked_stream.revision,
            "expected_executor_generation": 1,
            "trigger_event_id": trigger_event_id,
            "trigger_event_digest": trigger_digest,
            "replacement_passport": contract_to_dict(replacement),
            "corrective_workstream": contract_to_dict(corrective),
            "strategy_digest": hashlib.sha256(b"strategy-v2").hexdigest(),
            "causal_evidence_digest": hashlib.sha256(b"evidence-v2").hexdigest(),
            "justification": "Владелец выполнил точное human-only действие",
            "cwd": str(workspace),
            "prompt": "Продолжить из проверенного checkpoint.",
            "owner_action_attestation": attestation,
            "message_id": "corrective-recovery-message",
        }
        result = runtime.handle_command(
            {
                "contract": COMMAND_CONTRACT,
                "command": "apply_corrective_generation",
                "request_id": "corrective-recovery-request",
                "payload": recovery_payload,
            }
        )["result"]
        assert result["created"] is True
        assert runtime.handle_command(
            {
                "contract": COMMAND_CONTRACT,
                "command": "prepare_attention",
                "request_id": "corrective-attention-after-recovery",
                "payload": {"visibility_timeout": 30},
            }
        )["result"] is None
        assert registry.get_task(passport.task_id).state == "recovering"
        assert registry.get_workstream(stream.workstream_id).state == "recovering"
        assert registry.current_executor(
            passport.task_id, stream.workstream_id
        ).executor_generation == 1
        proven = runtime.process_codex_once()
        assert proven.status == "successor_proven" and shared.start_calls == 2
        current_task = registry.get_task(passport.task_id)
        current_stream = registry.get_workstream(stream.workstream_id)
        current_executor = registry.current_executor(passport.task_id, stream.workstream_id)
        assert current_task is not None and current_task.state == "active"
        assert current_stream is not None and current_stream.state == "working"
        assert current_executor is not None and current_executor.executor_generation == 2
        recovery_events = registry.list_events(
            task_id=passport.task_id,
            workstream_id=stream.workstream_id,
            event_types=("incident_policy",),
        )
        assert recovery_events[-1]["payload"]["status"] == "recovery_proven"
        followups = registry.list_outbox_records(
            kinds=("codex_followup",), states=("pending",)
        )
        assert len(followups) == 1
        assert followups[0]["payload"]["task_revision"] == current_task.revision
        assert (
            followups[0]["payload"]["workstream_revision"]
            == current_stream.revision
        )
        stored_recovery = next(
            event
            for event in recovery_events
            if event["payload"].get("status") == "corrective_generation_applied"
        )
        assert len(stored_recovery["payload"]["owner_action_attestation_digest"]) == 64
        projected_attention = runtime.engine.projection_snapshot()["attention"]
        assert next(
            item
            for item in projected_attention
            if item["attention_id"] == "corrective-human-attention"
        )["status"] == "resolved"
        runtime.close()
        registry.release_generation(fence)
        restart = registry.acquire_generation("corrective-generation-two")
        assert registry.get_task(passport.task_id).state == "active"
        assert registry.get_workstream(stream.workstream_id).state == "working"
        assert registry.current_executor(
            passport.task_id, stream.workstream_id
        ).executor_generation == 2
        assert not registry.list_outbox_records(
            kinds=("codex_successor_start",), states=("pending", "inflight")
        )
        registry.release_generation(restart)


def _unbound_start_reconciliation_restart_smoke() -> None:
    with TemporaryDirectory(prefix="dcpv2-unbound-reconcile-", dir="/tmp") as raw:
        root = Path(raw)
        workspace_root = root / "managed"
        workspace_root.mkdir()
        workspace = workspace_root / "task"
        workspace.mkdir()
        registry = SupervisorRegistry(root / "supervisor.sqlite3", lease_seconds=30)
        first_fence = registry.acquire_generation("unbound-generation-one")
        _current_fence_holder[:] = [first_fence]
        shared = FakeCodexState(registry)
        first_engine = SupervisorEngine(
            registry,
            first_fence,
            supervisor_id="unbound-supervisor-one",
            contour_verifier=lambda *_args: (_ for _ in ()).throw(
                AssertionError("unexpected terminal")
            ),
        )
        first_runtime = SupervisorRuntime(
            first_engine,
            allowed_workspace_root=workspace_root,
            codex_client_factory=lambda **kwargs: AmbiguousInitialCodexClient(
                shared, **kwargs
            ),
            codex_bin="/usr/bin/true",
            release_executor=lambda _payload, guard: _unused_release(guard),
            release_candidate_resolver=lambda _payload, guard: _unused_resolver(guard),
            release_arbiter_executor=lambda _payload, guard: _unused_arbiter(guard),
            incident_arbiter_executor=lambda _payload, guard: _unused_arbiter(guard),
            incident_application_executor=lambda _payload, guard: _unused_application(guard),
            target_lane_closure_executor=lambda _payload, guard: _unused_lane_closure(guard),
            retry_delay_seconds=0,
        )
        passport, stream = _contracts()
        start_payload = {
            "passport": contract_to_dict(passport),
            "workstream": contract_to_dict(stream),
            "cwd": str(workspace),
            "message_id": "unbound-initial-message",
        }
        first_runtime.handle_command(
            {
                "contract": COMMAND_CONTRACT,
                "command": "start_executor",
                "request_id": "unbound-initial-request",
                "payload": start_payload,
            }
        )
        assert registry.get_task(passport.task_id) is not None
        failed = first_runtime.process_codex_once()
        assert failed.status == "parked" and shared.start_calls == 1
        parked_task = registry.get_task(passport.task_id)
        parked_stream = registry.get_workstream(stream.workstream_id)
        assert parked_task is not None and parked_task.state == "parked"
        assert parked_stream is not None and parked_stream.state == "blocked"
        projection = first_engine.projection_snapshot()
        assert next(
            item for item in projection["tasks"] if item["task_id"] == passport.task_id
        )["active"] is True
        assert next(
            item
            for item in projection["workstreams"]
            if item["workstream_id"] == stream.workstream_id
        )["blocker"]
        failure_event = registry.list_events(
            task_id=passport.task_id,
            workstream_id=stream.workstream_id,
            event_types=("incident_policy",),
        )[-1]
        failure_digest = hashlib.sha256(
            json.dumps(
                failure_event["payload"],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        first_runtime.close()
        registry.release_generation(first_fence)

        second_fence = registry.acquire_generation("unbound-generation-two")
        _current_fence_holder[:] = [second_fence]
        second_runtime = _runtime(registry, second_fence, workspace_root, shared)
        try:
            second_runtime.handle_command(
                {
                    "contract": COMMAND_CONTRACT,
                    "command": "start_executor",
                    "request_id": "unbound-blind-retry-request",
                    "payload": {**start_payload, "message_id": "unbound-blind-retry-message"},
                }
            )
        except SupervisorCommandError:
            pass
        else:
            raise AssertionError("ambiguous unbound start admitted a blind new intent")
        replacement_passport = replace(
            passport,
            revision=parked_task.revision + 1,
            objective="Prove reconciled initial executor registration.",
        )
        replacement_stream = replace(
            stream,
            revision=parked_stream.revision + 1,
            objective=replacement_passport.objective,
            state="started",
            executor=None,
        )
        reconciliation_payload = {
            "task_id": passport.task_id,
            "expected_task_revision": parked_task.revision,
            "workstream_id": stream.workstream_id,
            "expected_workstream_revision": parked_stream.revision,
            "failed_event_id": failure_event["event_id"],
            "failed_event_digest": failure_digest,
            "replacement_passport": contract_to_dict(replacement_passport),
            "replacement_workstream": contract_to_dict(replacement_stream),
            "strategy_digest": hashlib.sha256(b"unbound-strategy-v2").hexdigest(),
            "justification": "Исключён старый orphan intent и изменён Passport",
            "cwd": str(workspace),
            "message_id": "unbound-reconciliation-message",
        }
        reconciled = second_runtime.handle_command(
            {
                "contract": COMMAND_CONTRACT,
                "command": "reconcile_unbound_start",
                "request_id": "unbound-reconciliation-request",
                "payload": reconciliation_payload,
            }
        )["result"]
        assert reconciled["created"] is True
        replay = second_runtime.handle_command(
            {
                "contract": COMMAND_CONTRACT,
                "command": "reconcile_unbound_start",
                "request_id": "unbound-reconciliation-replay-request",
                "payload": reconciliation_payload,
            }
        )["result"]
        assert replay["created"] is False
        assert second_runtime.handle_command(
            {
                "contract": COMMAND_CONTRACT,
                "command": "prepare_attention",
                "request_id": "unbound-stale-attention-request",
                "payload": {"visibility_timeout": 30},
            }
        )["result"] is None
        registered = second_runtime.process_codex_once()
        assert registered.status == "registered" and shared.start_calls == 2
        executor = registry.current_executor(passport.task_id, stream.workstream_id)
        assert executor is not None and executor.executor_generation == 1
        starts = [
            item
            for item in registry.list_outbox_records(kinds=("codex_thread_start",))
            if item["task_id"] == passport.task_id
        ]
        assert len(starts) == 2
        assert [item["state"] for item in starts] == ["delivered", "delivered"]
        second_runtime.close()
        registry.release_generation(second_fence)


def _preactivation_structural_repair_smoke() -> None:
    """Repair the exact invalid PR91 alias without resuming or calling a model."""

    with TemporaryDirectory(prefix="dcpv2-preactivation-structural-", dir="/tmp") as raw:
        root = Path(raw)
        workspace = root / "managed"
        workspace.mkdir()
        database = root / "state" / "supervisor.sqlite3"
        registry = SupervisorRegistry(database)
        first_fence = registry.acquire_generation("preactivation-source-generation")
        shared = FakeCodexState(registry)
        old_merge_sha = "237ccdd6f3361775f6a67892b793a19b0fb934a7"
        old_head_sha = "958054318a1b5eecd6550e61f7f834872014f96b"
        task_id = "orchestrator-v2-pr91-pilot"
        workstream_id = "orchestrator-v2-pr91-release"
        source_resources = (
            f"target:{DEV_CONTROL_PLANE_RELEASE_TARGET}",
            f"release-lane:{workstream_id}",
            "repo:orenvlad-ai/dev-control-plane",
            "module:codex-app-server",
            "module:local-install",
            "module:supervisor-registry",
            "module:supervisor-runtime",
        )
        source_passport = TaskPassport(
            task_id=task_id,
            revision=1,
            title="Проверка выпуска Orchestrator Codex v2",
            objective="Доказать один ограниченный production bootstrap-пилот Supervisor v2 на точном merged release.",
            expected_result="Один новый exact Codex thread gpt-5.6-sol ultra, один schema-bound checkpoint и проверяемая release projection без повторного model call.",
            contour="release:production",
            included_scope=("PR 91", "hosted projection", "local staged pilot"),
            excluded_scope=("изменения wb-core", "owner acceptance"),
            constraints=("ровно один single_attempt_canary model call",),
            acceptance=("точный executor thread зарегистрирован",),
            closure=("hosted release identity проверена",),
            autonomy=AutonomyEnvelope(
                allowed_actions=(
                    "codex_workspace_mutation",
                    "github_readback",
                    "hosted_readback",
                    "self_merge",
                    "self_hosted_deploy",
                    "target_lane_release",
                ),
                prohibited_actions=(
                    "repo_edit",
                    "local_checks",
                    "wb_github_command",
                    "target_release_command",
                ),
                human_gate_reasons=("platform_hard_stop",),
            ),
            workstream_ids=(workstream_id,),
            release_manifest=ReleaseClosureManifest(
                logical_lane_id=workstream_id,
                pr_identities=(
                    f"github-pr-v1:orenvlad-ai/dev-control-plane:91:{old_head_sha}:{old_merge_sha}",
                ),
                deploy_identities=(
                    f"hosted-release-v1:wb-core-eu-root:devcontrol.pro:{old_merge_sha}",
                ),
                finalized_at=NOW,
            ),
            resources=source_resources,
            modules=("module:supervisor-runtime",),
            files=("src/dev_control_plane/supervisor_runtime.py",),
            dependencies=(),
            multi_pr_intent=False,
            multi_deploy_intent=False,
            curator=CuratorIdentity(
                "019fa7f5-5f36-7101-8e07-27f8cdfbab08", "local"
            ),
            executor=None,
            created_at=NOW,
        )
        source_workstream = Workstream(
            workstream_id=workstream_id,
            task_id=task_id,
            revision=1,
            generation=1,
            root_workstream_id=workstream_id,
            corrective_of_generation=None,
            title="Bootstrap release qualification",
            objective="Получить один durable checkpoint и доказать exact release identity до activation.",
            state="started",
            executor=None,
            resources=source_resources,
            dependencies=(),
            created_at=NOW,
        )
        first_runtime = _runtime(
            registry, first_fence, workspace, shared
        )
        queued = first_runtime.handle_command(
            {
                "contract": COMMAND_CONTRACT,
                "command": "start_executor",
                "request_id": "preactivation-source-start-request",
                "payload": {
                    "passport": contract_to_dict(source_passport),
                    "workstream": contract_to_dict(source_workstream),
                    "cwd": str(workspace),
                    "message_id": "preactivation-source-start-message",
                },
            }
        )
        assert queued["result"]["queued"] is True
        assert first_runtime.process_codex_once().status == "registered"
        assert shared.start_calls == 1 and shared.turn_calls == 0
        historical_candidates = tuple(
            SchedulerReleaseCandidate(
                candidate_id=f"preactivation-historical-{index}",
                task_id=task_id,
                workstream_id=(
                    workstream_id
                    if index == 1
                    else "preactivation-historical-sibling"
                ),
                logical_lane_id=workstream_id,
                target_id=DEV_CONTROL_PLANE_RELEASE_TARGET,
                task_revision=2,
                workstream_revision=2,
                pr_head_sha=str(index) * 40,
                resources=("module:historical-overlap",),
                passport_files=("src/historical_overlap.py",),
                diff_files=("src/historical_overlap.py",),
                modules=("module:historical-overlap",),
                ready_since=NOW,
                created_at=NOW,
            )
            for index in (1, 2)
        )
        historical_schedule = first_runtime.engine.schedule(
            historical_candidates,
            message_id="preactivation-historical-semantic-case",
        )
        assert historical_schedule["kind"] == "semantic_release_plan"
        first_runtime._reconcile_release_orchestration()
        historical_arbiter = registry.list_outbox_records(
            kinds=("release_arbiter_case",), states=("pending",)
        )
        assert len(historical_arbiter) == 1
        assert historical_arbiter[0]["task_id"] is None
        assert historical_arbiter[0]["writer_generation"] == first_fence.generation
        for index in range(4):
            fingerprint = hashlib.sha256(
                f"preactivation-source-cause-{index}".encode()
            ).hexdigest()
            registry.append_event(
                f"preactivation-source-incident-{index}",
                "incident_policy",
                {
                    "schema": "dev-control-plane/incident-state-event/v2",
                    "revision": 2,
                    "status": "arbiter_failed_fail_closed",
                    "fingerprint": fingerprint,
                    "summary": "Старый bootstrap-инцидент.",
                    "decision": "park_workstream",
                    "attempt": 3,
                    "updated_at": NOW,
                },
                first_fence,
                task_id=task_id,
                workstream_id=workstream_id,
                executor_generation=1,
            )
            registry.enqueue_outbox(
                f"preactivation-source-attention-{index}",
                "curator_attention",
                {
                    "schema": "dev-control-plane/curator-attention/v2",
                    "attention_id": f"preactivation-attention-{index}",
                    "kind": "serious_stall",
                    "task_id": task_id,
                    "workstream_id": workstream_id,
                    "curator_thread_id": source_passport.curator.thread_id,
                    "handoff_ru": "Старый blocker.",
                    "required_action": "Старое действие.",
                    "created_at": NOW,
                },
                first_fence,
                task_id=task_id,
            )
        delivered_attention = registry.claim_outbox(
            first_fence,
            worker_id="preactivation-delivered-attention-fixture",
            limit=1,
            visibility_timeout=30,
            kinds=("curator_attention",),
        )
        assert len(delivered_attention) == 1
        registry.ack_outbox(
            delivered_attention[0].event_id,
            delivered_attention[0].claim_token,
            first_fence,
        )
        first_runtime.close()
        registry.release_generation(first_fence)

        # Reproduce the exact stored legacy alias without invoking the new
        # parser.  Direct SQL is fixture-only; production uses the registry.
        source_passport_raw = contract_to_dict(source_passport)
        source_passport_raw["revision"] = 2
        source_passport_raw["resources"][0] = "target:dev-control-plane"
        source_workstream_raw = contract_to_dict(source_workstream)
        source_workstream_raw.update(
            {
                "revision": 2,
                "state": "parked",
                "executor": {
                    "thread_id": "executor-thread-1",
                    "host_id": stable_supervisor_id(str(database.parent)).replace(
                        "mac-supervisor", "mac-host"
                    ),
                    "model": "gpt-5.6-sol",
                    "reasoning": "ultra",
                },
            }
        )
        source_workstream_raw["resources"][0] = "target:dev-control-plane"
        passport_json = json.dumps(
            source_passport_raw,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        workstream_json = json.dumps(
            source_workstream_raw,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        connection = sqlite3.connect(database)
        try:
            connection.execute(
                "UPDATE tasks SET revision=2,state='parked',passport_json=?,passport_digest=? WHERE task_id=?",
                (passport_json, hashlib.sha256(passport_json.encode()).hexdigest(), task_id),
            )
            connection.execute(
                "UPDATE workstreams SET revision=2,state='parked',contract_json=?,contract_digest=? WHERE workstream_id=? AND generation=1",
                (
                    workstream_json,
                    hashlib.sha256(workstream_json.encode()).hexdigest(),
                    workstream_id,
                ),
            )
            connection.commit()
        finally:
            connection.close()

        second_fence = registry.acquire_generation(
            "preactivation-repair-generation"
        )
        _current_fence_holder[:] = [second_fence]
        replacement_merge_sha = "a" * 40
        replacement_head_sha = "b" * 40
        replacement_resources = (
            f"target:{DEV_CONTROL_PLANE_RELEASE_TARGET}",
            f"release-lane:{workstream_id}",
            "repo:orenvlad-ai/dev-control-plane",
            "module:codex-app-server",
            "module:local-install",
            "module:supervisor-registry",
            "module:supervisor-runtime",
            f"qualification:{replacement_merge_sha}",
        )
        replacement = replace(
            source_passport,
            revision=3,
            included_scope=tuple(source_passport.included_scope) + ("PR 92",),
            constraints=tuple(source_passport.constraints)
            + ("structural thread/start only",),
            resources=replacement_resources,
            files=tuple(source_passport.files)
            + ("src/dev_control_plane/supervisor_registry.py",),
            release_manifest=ReleaseClosureManifest(
                logical_lane_id=workstream_id,
                pr_identities=(
                    f"github-pr-v1:orenvlad-ai/dev-control-plane:91:{old_head_sha}:{old_merge_sha}",
                    f"github-pr-v1:orenvlad-ai/dev-control-plane:92:{replacement_head_sha}:{replacement_merge_sha}",
                ),
                deploy_identities=(
                    f"hosted-release-v1:wb-core-eu-root:devcontrol.pro:{old_merge_sha}",
                    f"hosted-release-v1:wb-core-eu-root:devcontrol.pro:{replacement_merge_sha}",
                ),
                finalized_at=NOW,
            ),
            multi_pr_intent=True,
            multi_deploy_intent=True,
        )
        corrective = Workstream(
            workstream_id=workstream_id,
            task_id=task_id,
            revision=1,
            generation=2,
            root_workstream_id=workstream_id,
            corrective_of_generation=1,
            title=source_workstream.title,
            objective=source_workstream.objective,
            state="recovering",
            executor=None,
            resources=replacement_resources,
            dependencies=(),
            created_at=NOW,
        )
        preactivation_release = FakeReleaseWorkers()
        preactivation_release.actual_files[replacement_head_sha] = tuple(
            replacement.files
        )
        preactivation_release.merged_heads.add(replacement_head_sha)
        preactivation_release.merge_commit_shas[replacement_head_sha] = (
            replacement_merge_sha
        )
        preactivation_release.pr_numbers[replacement_head_sha] = 92
        preactivation_release.required_checks[replacement_head_sha] = (
            "v2-suite",
            "self-closure",
        )
        repair_runtime = SupervisorRuntime(
            SupervisorEngine(
                registry,
                second_fence,
                supervisor_id=stable_supervisor_id(str(database.parent)),
                contour_verifier=lambda *_args: (_ for _ in ()).throw(
                    AssertionError("unexpected terminal")
                ),
            ),
            allowed_workspace_root=workspace,
            codex_client_factory=lambda **kwargs: FakeCodexClient(shared, **kwargs),
            codex_bin="/usr/bin/true",
            release_executor=lambda _payload, guard: _unused_release(guard),
            release_candidate_resolver=preactivation_release.resolver,
            release_arbiter_executor=lambda _payload, guard: _unused_arbiter(guard),
            incident_arbiter_executor=lambda _payload, guard: _unused_arbiter(guard),
            incident_application_executor=lambda _payload, guard: _unused_application(guard),
            target_lane_closure_executor=lambda _payload, guard: _unused_lane_closure(guard),
            allow_external_policy_adapters=True,
            visibility_timeout_seconds=2,
            activation_identity={
                "schema": "dev-control-plane/runtime-activation/v2",
                "release_sha": replacement_merge_sha,
                "activation_nonce_sha256": "c" * 64,
                "pid": os.getpid(),
                "python_executable": sys.executable,
                "entrypoint": str(Path(__file__).resolve()),
                "bind_host": "127.0.0.1",
                "bind_port": 8766,
            },
            preactivation_repair_mode=True,
        )
        assert repair_runtime.health()["status"] == "not_ready"
        assert repair_runtime.process_codex_once().status == "disabled"
        assert repair_runtime.process_release_once().status == "disabled"
        assert repair_runtime.process_incident_policy_once().status == "disabled"
        assert shared.resume_calls == []
        repair_command = {
            "contract": COMMAND_CONTRACT,
            "command": "apply_preactivation_structural_repair",
            "request_id": "preactivation-repair-request",
            "payload": {
                    "task_id": task_id,
                    "expected_task_revision": 2,
                    "workstream_id": workstream_id,
                    "expected_workstream_generation": 1,
                    "expected_workstream_revision": 2,
                    "expected_executor_generation": 1,
                    "replacement_passport": contract_to_dict(replacement),
                    "corrective_workstream": contract_to_dict(corrective),
                    "cwd": str(workspace),
                    "expected_pr_head_sha": replacement_head_sha,
                    "justification": "Canonical target and PR92 qualification repair before first turn.",
                    "message_id": "preactivation-repair-message",
            },
        }
        forged_manifest = replace(
            replacement.release_manifest,
            pr_identities=(
                f"github-pr-v1:orenvlad-ai/dev-control-plane:91:{'d' * 40}:{old_merge_sha}",
                replacement.release_manifest.pr_identities[-1],
            ),
        )
        forged_replacement = replace(
            replacement,
            release_manifest=forged_manifest,
        )
        try:
            repair_runtime.handle_command(
                {
                    **repair_command,
                    "payload": {
                        **repair_command["payload"],
                        "replacement_passport": contract_to_dict(
                            forged_replacement
                        ),
                    },
                }
            )
        except RegistryValidationError:
            pass
        else:
            raise AssertionError(
                "preactivation repair rewrote its immutable PR91 manifest prefix"
            )
        repair = repair_runtime.handle_command(repair_command)["result"]
        assert repair["created"] is True and repair["status"] == "successor_reserved"
        replayed = repair_runtime.handle_command(
            {**repair_command, "request_id": "preactivation-repair-replay"}
        )["result"]
        assert replayed["created"] is False
        assert len(tuple(registry.backup_dir.glob("*.sqlite3"))) == 1
        try:
            repair_runtime.handle_command(
                {
                    **repair_command,
                    "request_id": "preactivation-repair-different-message-request",
                    "payload": {
                        **repair_command["payload"],
                        "message_id": "preactivation-repair-different-message",
                    },
                }
            )
        except SupervisorCommandError:
            pass
        else:
            raise AssertionError(
                "preactivation repair created a second caller-selected backup"
            )
        assert len(tuple(registry.backup_dir.glob("*.sqlite3"))) == 1

        # A process death after the repair transaction but before start_intent
        # cannot transfer the one-shot thread/start budget to a new writer.
        generation_loss_database = (
            root / "generation-loss-state" / "supervisor.sqlite3"
        )
        registry.backup(generation_loss_database)
        generation_loss_registry = SupervisorRegistry(generation_loss_database)
        generation_loss_registry.release_generation(second_fence)
        generation_loss_fence = generation_loss_registry.acquire_generation(
            "preactivation-generation-loss"
        )
        _current_fence_holder[:] = [generation_loss_fence]
        generation_loss_runtime = SupervisorRuntime(
            SupervisorEngine(
                generation_loss_registry,
                generation_loss_fence,
                supervisor_id=stable_supervisor_id(
                    str(generation_loss_database.parent)
                ),
                contour_verifier=lambda *_args: (_ for _ in ()).throw(
                    AssertionError("unexpected terminal")
                ),
            ),
            allowed_workspace_root=workspace,
            codex_client_factory=lambda **kwargs: FakeCodexClient(shared, **kwargs),
            codex_bin="/usr/bin/true",
            release_executor=lambda _payload, guard: _unused_release(guard),
            release_candidate_resolver=preactivation_release.resolver,
            release_arbiter_executor=lambda _payload, guard: _unused_arbiter(guard),
            incident_arbiter_executor=lambda _payload, guard: _unused_arbiter(guard),
            incident_application_executor=lambda _payload, guard: _unused_application(guard),
            target_lane_closure_executor=lambda _payload, guard: _unused_lane_closure(guard),
            activation_identity={
                "schema": "dev-control-plane/runtime-activation/v2",
                "release_sha": replacement_merge_sha,
                "activation_nonce_sha256": "c" * 64,
                "pid": os.getpid(),
                "python_executable": sys.executable,
                "entrypoint": str(Path(__file__).resolve()),
                "bind_host": "127.0.0.1",
                "bind_port": 8766,
            },
            preactivation_repair_mode=True,
        )
        generation_loss = (
            generation_loss_runtime.process_preactivation_repair_once()
        )
        assert generation_loss.status == "parked"
        assert (
            generation_loss.detail
            == "preactivation_repair_process_generation_lost"
        )
        assert shared.start_calls == 1 and shared.turn_calls == 0
        generation_loss_state = (
            generation_loss_registry.preactivation_structural_repair_state()
        )
        assert generation_loss_state["status"] == "parked"
        assert len(
            generation_loss_registry.list_outbox_records(
                kinds=("curator_attention",), states=("pending",)
            )
        ) == 1
        generation_loss_runtime.close()
        generation_loss_registry.release_generation(generation_loss_fence)
        _current_fence_holder[:] = [second_fence]

        # The same reserved source state fails closed if thread/start becomes
        # ambiguous: one serious-stall attention is created atomically, and
        # neither a retry nor another structural start remains claimable.
        failure_database = root / "failure-state" / "supervisor.sqlite3"
        registry.backup(failure_database)
        failure_registry = SupervisorRegistry(failure_database)
        failed_claims = failure_registry.claim_outbox(
            second_fence,
            worker_id="preactivation-ambiguous-start-smoke",
            limit=1,
            visibility_timeout=30,
            kinds=("codex_preactivation_successor_start",),
        )
        assert len(failed_claims) == 1
        ambiguous_payload = dict(failed_claims[0].payload)
        ambiguous_payload["start_intent"] = {
            "supervisor_generation": second_fence.generation,
            "started_at": NOW,
            "app_server_connection_epoch": 1,
        }
        failed_message = failure_registry.replace_claimed_outbox_payload(
            failed_claims[0].event_id,
            failed_claims[0].claim_token,
            ambiguous_payload,
            second_fence,
        )
        failed = failure_registry.fail_preactivation_structural_repair(
            claimed_outbox_event_id=failed_message.event_id,
            claim_token=failed_message.claim_token,
            error_code="codex_ambiguous_outcome",
            fence=second_fence,
        )
        failed_state = failure_registry.preactivation_structural_repair_state()
        assert failed_state["status"] == "parked"
        assert failed_state["failure_event_id"] == failed["failure_event_id"]
        assert failed_state["error_code"] == "codex_ambiguous_outcome"
        assert failed_state["attention_event_id"] == failed["attention_event_id"]
        pending_stalls = [
            item
            for item in failure_registry.list_outbox_records(
                kinds=("curator_attention",), states=("pending",)
            )
            if item["payload"].get("kind") == "serious_stall"
        ]
        assert len(pending_stalls) == 1
        assert pending_stalls[0]["coalescible"] is False
        assert (
            pending_stalls[0]["payload"]["attention_id"]
            == failed["failure_event_id"]
        )
        assert (
            pending_stalls[0]["payload"]["curator_thread_id"]
            == replacement.curator.thread_id
        )
        assert not failure_registry.claim_outbox(
            second_fence,
            worker_id="preactivation-no-retry-smoke",
            limit=1,
            visibility_timeout=30,
            kinds=("codex_preactivation_successor_start",),
        )
        assert shared.start_calls == 1 and shared.turn_calls == 0
        failure_registry.release_generation(second_fence)
        try:
            repair_runtime.handle_command(
                {
                "contract": COMMAND_CONTRACT,
                "command": "runtime_state",
                "request_id": "preactivation-runtime-state-rejected",
                "payload": {},
                }
            )
        except SupervisorCommandError:
            pass
        else:
            raise AssertionError(
                "preactivation repair mode exposed normal runtime_state"
            )
        assert shared.start_calls == 1 and shared.turn_calls == 0
        outcome = repair_runtime.process_preactivation_repair_once()
        assert outcome.status == "successor_proven", outcome
        assert shared.start_calls == 2 and shared.turn_calls == 0
        assert shared.required_start_epochs[-1] == 1
        assert shared.resume_calls == []
        assert repair_runtime.preactivation_repair_complete is True
        assert repair_runtime.health()["status"] == "ready"
        completed_replay = repair_runtime.handle_command(
            {**repair_command, "request_id": "preactivation-repair-completed-replay"}
        )["result"]
        assert completed_replay["created"] is False
        assert completed_replay["status"] == "completed"
        current = registry.current_executor(task_id, workstream_id)
        assert current is not None and current.executor_generation == 2
        assert current.thread_id == "executor-thread-2"
        old = [
            item
            for item in registry.list_outbox_records(kinds=("curator_attention",))
        ]
        assert len(old) == 4
        assert {item["state"] for item in old} == {"delivered", "superseded"}
        projection = repair_runtime.engine.projection_snapshot()
        assert len(projection["incidents"]) == 4
        assert {item["status"] for item in projection["incidents"]} == {"resolved"}
        assert {item["status"] for item in projection["attention"]} == {"resolved"}
        projection_before_noop = registry.list_outbox_records(
            kinds=("projection_snapshot",)
        )
        repair_runtime.maintenance_tick()
        assert registry.list_outbox_records(
            kinds=("projection_snapshot",)
        ) == projection_before_noop

        # A crash after durable completion but before the same-process Event,
        # HTTP bind and canary cannot reuse the empty-thread shortcut.  A new
        # repair-mode process parks immediately, creates one durable attention
        # and performs no resume/start/model operation.
        restart_database = root / "restart-state" / "supervisor.sqlite3"
        registry.backup(restart_database)
        restart_registry = SupervisorRegistry(restart_database)
        restart_registry.release_generation(second_fence)
        restart_fence = restart_registry.acquire_generation(
            "preactivation-completed-restart-generation"
        )
        restart_runtime = SupervisorRuntime(
            SupervisorEngine(
                restart_registry,
                restart_fence,
                supervisor_id=stable_supervisor_id(str(restart_database.parent)),
                contour_verifier=lambda *_args: (_ for _ in ()).throw(
                    AssertionError("unexpected terminal")
                ),
            ),
            allowed_workspace_root=workspace,
            codex_client_factory=lambda **kwargs: FakeCodexClient(shared, **kwargs),
            codex_bin="/usr/bin/true",
            release_executor=lambda _payload, guard: _unused_release(guard),
            release_candidate_resolver=lambda _payload, guard: _unused_resolver(guard),
            release_arbiter_executor=lambda _payload, guard: _unused_arbiter(guard),
            incident_arbiter_executor=lambda _payload, guard: _unused_arbiter(guard),
            incident_application_executor=lambda _payload, guard: _unused_application(guard),
            target_lane_closure_executor=lambda _payload, guard: _unused_lane_closure(guard),
            activation_identity={
                "schema": "dev-control-plane/runtime-activation/v2",
                "release_sha": replacement_merge_sha,
                "activation_nonce_sha256": "c" * 64,
                "pid": os.getpid(),
                "python_executable": sys.executable,
                "entrypoint": str(Path(__file__).resolve()),
                "bind_host": "127.0.0.1",
                "bind_port": 8766,
            },
            preactivation_repair_mode=True,
        )
        restart_state = restart_registry.preactivation_structural_repair_state()
        assert restart_state["status"] == "parked"
        assert (
            restart_state["error_code"]
            == "preactivation_same_process_epoch_lost"
        )
        assert restart_runtime.health()["status"] == "not_ready"
        assert restart_runtime.preactivation_repair_complete is False
        assert restart_registry.current_executor(task_id, workstream_id) is None
        restart_stalls = [
            item
            for item in restart_registry.list_outbox_records(
                kinds=("curator_attention",), states=("pending",)
            )
            if item["payload"].get("kind") == "serious_stall"
        ]
        assert len(restart_stalls) == 1
        assert (
            restart_stalls[0]["payload"]["attention_id"]
            == restart_state["failure_event_id"]
        )
        restart_outcome = restart_runtime.process_preactivation_repair_once()
        assert restart_outcome.status == "idle"
        assert shared.start_calls == 2 and shared.turn_calls == 0
        assert shared.resume_calls == []
        restart_runtime.close()
        restart_registry.release_generation(restart_fence)

        admission = repair_runtime.process_release_once()
        assert admission.status == "proof_only_wait", admission
        assert repair_runtime.preactivation_release_admission_complete is True
        assert preactivation_release.resolver_calls == 1
        assert preactivation_release.release_arbiter_calls == 0
        assert repair_runtime.process_incident_policy_once().status == "disabled"
        assert len(
            registry.list_events(event_types=("semantic_release_case",))
        ) == 1
        assert not tuple(
            record
            for record in registry.list_outbox_records(
                kinds=(
                    "release_candidate_resolution",
                    "release_action",
                    "release_arbiter_case",
                    "incident_arbiter_application",
                    "target_lane_closure",
                )
            )
            if record.get("state") in {"pending", "inflight"}
            or (
                record.get("state") == "delivered"
                and record.get("writer_generation") == second_fence.generation
            )
        )
        assert registry.list_outbox_records(
            kinds=("release_arbiter_case",), states=("superseded",)
        )

        # Losing the exact structural-start epoch can never fall back to
        # thread/read or resume for the one qualification canary.
        repair_client = repair_runtime._codex_client
        assert isinstance(repair_client, FakeCodexClient)
        snapshot_calls_before_epoch_loss = shared.snapshot_calls
        resume_calls_before_epoch_loss = tuple(shared.resume_calls)
        repair_client.connection_epoch += 1
        try:
            repair_runtime._new_call_intent_for_thread(
                repair_client,
                "executor-thread-2",
                required_fresh_epoch=1,
            )
        except CodexAmbiguousOutcomeError:
            pass
        else:
            raise AssertionError(
                "preactivation canary reconnected after structural completion"
            )
        assert shared.snapshot_calls == snapshot_calls_before_epoch_loss
        assert tuple(shared.resume_calls) == resume_calls_before_epoch_loss
        repair_client.connection_epoch = 1

        queued_canary = repair_runtime.handle_command(
            {
                "contract": COMMAND_CONTRACT,
                "command": "codex_followup",
                "request_id": "preactivation-canary-request",
                "payload": {
                    "task_id": task_id,
                    "workstream_id": workstream_id,
                    "prompt": "Return the exact qualification checkpoint.",
                    "output_contract": "checkpoint",
                    "cwd": str(workspace),
                    "terminal_context": None,
                    "call_policy": "single_attempt_canary",
                    "message_id": "preactivation-canary-message",
                },
            }
        )["result"]
        assert queued_canary["queued"] is True
        canary = repair_runtime.process_codex_once()
        assert canary.status == "delivered" and shared.turn_calls == 1, (
            canary,
            shared.turn_calls,
            registry.list_events(event_types=("qualification_canary_failed",)),
        )
        assert repair_runtime.preactivation_canary_complete is True
        assert repair_runtime.process_release_once().status == "disabled"
        assert repair_runtime.process_incident_policy_once().status == "disabled"
        for forbidden_after_canary in ("register", "queue_release_action"):
            try:
                repair_runtime.handle_command(
                    {
                        "contract": COMMAND_CONTRACT,
                        "command": forbidden_after_canary,
                        "request_id": (
                            "preactivation-post-canary-"
                            + forbidden_after_canary
                        ),
                        "payload": {},
                    }
                )
            except SupervisorCommandError:
                pass
            else:
                raise AssertionError(
                    "repair-mode exposed mutation after qualification"
                )
        qualification = repair_runtime._qualification_evidence()
        assert qualification["staged_runtime"]["final_attention_deferred"] is True
        repair_events = registry.list_events(
            event_types=(
                "preactivation_structural_repair",
                "preactivation_structural_repair_completed",
            )
        )
        assert [item["event_type"] for item in repair_events] == [
            "preactivation_structural_repair",
            "preactivation_structural_repair_completed",
        ]
        assert repair_events[0]["executor_generation"] == 1
        assert repair_events[1]["executor_generation"] == 2
        completion = repair_events[1]["payload"]
        assert completion["expected_pr_head_sha"] == replacement_head_sha
        assert completion["activation_release_sha"] == replacement_merge_sha
        assert completion["same_process_epoch"] is True
        assert completion["real_model_calls"] == 0
        repair_runtime.close()
        registry.release_generation(second_fence)


def _sibling_parking_isolation_restart_smoke() -> None:
    with TemporaryDirectory(prefix="dcpv2-sibling-park-", dir="/tmp") as raw:
        root = Path(raw)
        workspace = root / "managed"
        workspace.mkdir()
        registry = SupervisorRegistry(root / "supervisor.sqlite3", lease_seconds=30)
        first_fence = registry.acquire_generation("sibling-park-generation-one")
        engine = SupervisorEngine(
            registry,
            first_fence,
            supervisor_id="sibling-park-supervisor-one",
            contour_verifier=lambda *_args: (_ for _ in ()).throw(
                AssertionError("unexpected terminal")
            ),
        )
        passport = TaskPassport(
            task_id="sibling-park-task",
            revision=1,
            title="Sibling parking isolation",
            objective="Keep an independent sibling runnable.",
            expected_result="Only the affected workstream parks.",
            contour="diagnostic",
            included_scope=("two workstreams",),
            excluded_scope=("live release",),
            constraints=("isolate failures",),
            acceptance=("sibling checkpoint accepted",),
            closure=("aggregate park only after both stop",),
            autonomy=AutonomyEnvelope(
                allowed_actions=("codex_workspace_mutation",),
                prohibited_actions=("target_release_command",),
                human_gate_reasons=("platform_hard_stop",),
            ),
            workstream_ids=("sibling-park-one", "sibling-park-two"),
            release_manifest=None,
            resources=("module:sibling-one", "module:sibling-two"),
            modules=("module:sibling-one", "module:sibling-two"),
            files=("src/sibling_one.py", "src/sibling_two.py"),
            dependencies=(),
            multi_pr_intent=False,
            multi_deploy_intent=False,
            curator=CuratorIdentity("sibling-park-curator", "desktop-host"),
            executor=None,
            created_at=NOW,
        )
        executors = (
            ExecutorIdentity("sibling-thread-one", "mac-local", "gpt-5.6-sol", "ultra"),
            ExecutorIdentity("sibling-thread-two", "mac-local", "gpt-5.6-sol", "ultra"),
        )
        streams: list[Workstream] = []
        for index, executor in enumerate(executors, start=1):
            stream = Workstream(
                workstream_id=f"sibling-park-{'one' if index == 1 else 'two'}",
                task_id=passport.task_id,
                revision=1,
                generation=1,
                root_workstream_id=f"sibling-park-{'one' if index == 1 else 'two'}",
                corrective_of_generation=None,
                title=f"Sibling stream {index}",
                objective=passport.objective,
                state="working",
                executor=executor,
                resources=(f"module:sibling-{'one' if index == 1 else 'two'}",),
                dependencies=(),
                created_at=NOW,
            )
            streams.append(stream)
            engine.register(
                passport, stream, message_id=f"sibling-park-register-{index}"
            )
        runtime = SupervisorRuntime(
            engine,
            allowed_workspace_root=workspace,
            codex_bin="/usr/bin/true",
            release_executor=lambda _payload, guard: _unused_release(guard),
            release_candidate_resolver=lambda _payload, guard: _unused_resolver(guard),
            release_arbiter_executor=lambda _payload, guard: _unused_arbiter(guard),
            incident_arbiter_executor=lambda _payload, guard: _unused_arbiter(guard),
            incident_application_executor=lambda _payload, guard: _unused_application(guard),
            target_lane_closure_executor=lambda _payload, guard: _unused_lane_closure(guard),
        )
        registry.append_event(
            "sibling-release-stalled",
            "release_stalled",
            {
                "schema": "dev-control-plane/release-stalled/v2",
                "status": "parked",
                "error_code": "isolated_release_failure",
            },
            first_fence,
            task_id=passport.task_id,
            workstream_id=streams[0].workstream_id,
        )
        runtime._park_release_binding(
            SimpleNamespace(
                task_id=passport.task_id,
                workstream_id=streams[0].workstream_id,
            )
        )
        task_after_first = registry.get_task(passport.task_id)
        assert task_after_first is not None
        assert task_after_first.state == "active" and task_after_first.revision == 1
        assert registry.get_workstream(streams[0].workstream_id).state == "parked"
        assert registry.get_workstream(streams[1].workstream_id).state == "working"
        engine.import_checkpoint(
            Checkpoint(
                checkpoint_id="sibling-checkpoint",
                event_id="sibling-checkpoint-event",
                task_id=passport.task_id,
                task_revision=1,
                workstream_id=streams[1].workstream_id,
                workstream_revision=1,
                executor_generation=1,
                executor=executors[1],
                progress_stage=25,
                delta_ru="Независимый sibling продолжил работу.",
                current_ru="Выполняется следующий безопасный этап.",
                evidence=("sibling:isolation",),
                created_at=NOW,
            ),
            message_id="sibling-checkpoint-message",
        )
        runtime.close()
        registry.release_generation(first_fence)

        second_fence = registry.acquire_generation("sibling-park-generation-two")
        restarted_engine = SupervisorEngine(
            registry,
            second_fence,
            supervisor_id="sibling-park-supervisor-two",
            contour_verifier=lambda *_args: (_ for _ in ()).throw(
                AssertionError("unexpected terminal")
            ),
        )
        projection = restarted_engine.projection_snapshot()
        assert next(
            item for item in projection["tasks"] if item["task_id"] == passport.task_id
        )["status"] == "working"
        rows = {
            item["workstream_id"]: item for item in projection["workstreams"]
        }
        assert rows[streams[0].workstream_id]["status"] == "blocked"
        assert rows[streams[1].workstream_id]["status"] == "working"
        restarted_runtime = SupervisorRuntime(
            restarted_engine,
            allowed_workspace_root=workspace,
            codex_bin="/usr/bin/true",
            release_executor=lambda _payload, guard: _unused_release(guard),
            release_candidate_resolver=lambda _payload, guard: _unused_resolver(guard),
            release_arbiter_executor=lambda _payload, guard: _unused_arbiter(guard),
            incident_arbiter_executor=lambda _payload, guard: _unused_arbiter(guard),
            incident_application_executor=lambda _payload, guard: _unused_application(guard),
            target_lane_closure_executor=lambda _payload, guard: _unused_lane_closure(guard),
        )
        registry.append_event(
            "sibling-incident-parked",
            "incident_policy",
            {
                "schema": "dev-control-plane/incident-state-event/v2",
                "status": "parked",
                "summary": "Второй sibling также доказанно припаркован.",
                "fingerprint": hashlib.sha256(b"sibling-two-incident").hexdigest(),
            },
            second_fence,
            task_id=passport.task_id,
            workstream_id=streams[1].workstream_id,
            executor_generation=1,
        )
        restarted_runtime._park_incident_binding(
            SimpleNamespace(
                task_id=passport.task_id,
                workstream_id=streams[1].workstream_id,
            )
        )
        final_task = registry.get_task(passport.task_id)
        assert final_task is not None and final_task.state == "parked"
        assert final_task.revision == 2
        restarted_runtime.close()
        registry.release_generation(second_fence)


def _lease_starvation_smoke() -> None:
    with TemporaryDirectory(prefix="dcpv2-lease-", dir="/tmp") as raw:
        root = Path(raw)
        workspace = root / "managed"
        workspace.mkdir()
        registry = SupervisorRegistry(root / "supervisor.sqlite3", lease_seconds=0.3)
        fence = registry.acquire_generation("lease-starvation-generation")
        shared = FakeCodexState(registry)
        engine = SupervisorEngine(
            registry,
            fence,
            supervisor_id="lease-starvation-supervisor",
            publisher=SlowPublisher(),  # type: ignore[arg-type]
            contour_verifier=lambda *_args: (_ for _ in ()).throw(AssertionError("unexpected terminal")),
        )
        runtime = SupervisorRuntime(
            engine,
            allowed_workspace_root=workspace,
            codex_client_factory=lambda **kwargs: FakeCodexClient(shared, **kwargs),
            codex_bin="/usr/bin/true",
            release_executor=lambda _payload, guard: _unused_release(guard),
            release_candidate_resolver=lambda _payload, guard: _unused_resolver(guard),
            release_arbiter_executor=lambda _payload, guard: _unused_arbiter(guard),
            incident_arbiter_executor=lambda _payload, guard: _unused_arbiter(guard),
            incident_application_executor=lambda _payload, guard: _unused_application(guard),
            target_lane_closure_executor=lambda _payload, guard: _unused_lane_closure(guard),
        )
        loop = SupervisorRuntimeLoop(runtime, maintenance_interval_seconds=0.05, codex_poll_seconds=0.05)
        loop.start()
        time.sleep(0.5)
        lease = registry.current_generation()
        assert lease["generation"] == fence.generation and lease["expires_at"] > time.time()
        try:
            registry.acquire_generation("lease-starvation-forged")
        except LeaseHeldError:
            pass
        else:
            raise AssertionError("slow projection publication starved the singleton lease")
        loop.stop(timeout=3)
        runtime.close()
        registry.release_generation(engine.fence)


def _owner_source_attestation_smoke() -> None:
    with TemporaryDirectory(prefix="dcpv2-owner-", dir="/tmp") as raw:
        key_path = Path(raw) / "owner.key"
        key = b"owner-acceptance-smoke-key-material-32-bytes"
        key_path.write_bytes(key)
        key_path.chmod(0o600)
        receipt = OwnerAcceptanceReceipt(
            receipt_id="owner-receipt-runtime-smoke",
            task_id="task-runtime-smoke",
            task_revision=1,
            curator_thread_id="curator-runtime-smoke",
            reply="Задача принята",
            created_at=NOW,
        )
        attestation = {
            "schema": "dev-control-plane/owner-acceptance-source/v2",
            "curator_thread_id": receipt.curator_thread_id,
            "source_message_id": "curator-message-runtime-smoke",
            "attention_event_id": "curator-attention-runtime-smoke",
            "observed_at_epoch": time.time(),
            "reply_sha256": hashlib.sha256(receipt.reply.encode()).hexdigest(),
            "signature": "",
        }
        attestation["signature"] = owner_acceptance_source_signature(key, receipt, attestation)
        verifier = OwnerAcceptanceSourceVerifier(key_path)
        assert verifier(receipt, attestation) is True
        assert verifier(receipt, {**attestation, "source_message_id": "forged-message"}) is False


def _unused_release(guard: Any) -> Mapping[str, Any]:
    guard.checkpoint()
    guard.checkpoint()
    raise AssertionError("unexpected release callback")


def _unused_resolver(guard: Any) -> Mapping[str, Any]:
    guard.checkpoint()
    raise AssertionError("unexpected resolver callback")


def _unused_arbiter(guard: Any) -> Any:
    guard.checkpoint()
    raise AssertionError("unexpected arbiter callback")


def _unused_application(guard: Any) -> Mapping[str, Any]:
    guard.checkpoint()
    guard.checkpoint()
    raise AssertionError("unexpected application callback")


def _unused_lane_closure(guard: Any) -> Mapping[str, Any]:
    guard.checkpoint()
    guard.checkpoint()
    raise AssertionError("unexpected target lane closure callback")


if __name__ == "__main__":
    main()
