"""Fake-only end-to-end smoke for the deterministic local Supervisor v2."""

from __future__ import annotations

from dataclasses import asdict, replace
import hashlib
from http import HTTPStatus
import http.client
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from tempfile import TemporaryDirectory
import threading
import time
from typing import Any
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (SRC, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dev_control_plane.curator_delivery import CuratorDelivery, CuratorDeliveryError  # noqa: E402
from dev_control_plane.orchestration_contracts import (  # noqa: E402
    ArbiterDecision,
    AutonomyEnvelope,
    Checkpoint,
    CuratorIdentity,
    DecisionStep,
    ExecutorIdentity,
    ReleaseClosureManifest,
    TaskPassport,
    TerminalEvidence,
    Workstream,
)
from dev_control_plane.projection_client import (  # noqa: E402
    PRODUCTION_PROJECTION_ENDPOINT,
    ProjectionPublishError,
    ProjectionPublisher,
    TransportResponse,
    _https_transport,
)
from dev_control_plane.projection_server import (  # noqa: E402
    _ack_payload,
    _require_metadata_match,
    render_dashboard,
    verify_signed_request,
)
from dev_control_plane.projection_store import ProjectionStore, projection_envelope_from_mapping  # noqa: E402
from dev_control_plane.release_scheduler import (  # noqa: E402
    ReleaseCandidate,
    StaleArbiterDecision,
    schedule_releases,
    validate_arbiter_release_decision,
)
from dev_control_plane.supervisor import (  # noqa: E402
    ContourVerification,
    EXACT_OWNER_ACCEPTANCE,
    OwnerAcceptanceReceipt,
    SupervisorEngine,
    SupervisorError,
    SupervisorHTTPServer,
    stable_supervisor_id,
    terminal_contract_digest,
)
from dev_control_plane.supervisor_registry import (  # noqa: E402
    LockConflict,
    SupervisorRegistry,
)

NOW = "2026-08-05T08:00:00Z"
KEY = b"supervisor-v2-projection-smoke-key-material-32"


class MutableClock:
    def __init__(self, value: float) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value


class FakeProjectionTransport:
    def __init__(self, store: ProjectionStore, clock: MutableClock) -> None:
        self.store = store
        self.clock = clock
        self.calls = 0
        self.lose_first_ack = True
        self.bodies: list[bytes] = []
        self.header_timestamps: list[int] = []

    def __call__(self, endpoint: str, body: bytes, headers: object, timeout: float) -> TransportResponse:
        assert endpoint == PRODUCTION_PROJECTION_ENDPOINT and timeout > 0
        self.calls += 1
        self.bodies.append(body)
        metadata, body_digest = verify_signed_request(
            key=KEY,
            body=body,
            headers=headers,  # type: ignore[arg-type]
            now_epoch=self.clock(),
            max_skew_seconds=30,
        )
        self.header_timestamps.append(metadata.timestamp)
        envelope = projection_envelope_from_mapping(json.loads(body))
        _require_metadata_match(metadata, envelope)
        receipt = self.store.ingest(envelope, body_sha256=body_digest)
        if self.lose_first_ack:
            self.lose_first_ack = False
            raise OSError("simulated ACK loss")
        return TransportResponse(
            200,
            json.dumps(_ack_payload(receipt), sort_keys=True, separators=(",", ":")).encode(),
        )


def main() -> None:
    _curl_secrecy_smoke()
    _endpoint_gate_smoke()
    with TemporaryDirectory(prefix="dev-control-plane-supervisor-v2-") as raw:
        root = Path(raw)
        registry = SupervisorRegistry(root / "state" / "supervisor.sqlite3", lease_seconds=300)
        fence = registry.acquire_generation("supervisor-e2e-generation-1")
        projection_store = ProjectionStore(root / "hosted" / "projection.sqlite3")
        transport_clock = MutableClock(time.time())
        transport = FakeProjectionTransport(projection_store, transport_clock)
        publisher = ProjectionPublisher(
            endpoint=PRODUCTION_PROJECTION_ENDPOINT,
            key=KEY,
            transport=transport,
            clock=transport_clock,
            base_backoff_seconds=0.001,
            max_backoff_seconds=1,
        )
        verification_holder: dict[str, ContourVerification] = {}

        def verifier(_passport: TaskPassport, _terminal: TerminalEvidence) -> ContourVerification:
            return verification_holder["value"]

        engine = SupervisorEngine(
            registry,
            fence,
            supervisor_id=stable_supervisor_id(str(root / "state")),
            publisher=publisher,
            contour_verifier=verifier,
            projection_heartbeat_seconds=30,
        )

        passports: dict[str, TaskPassport] = {}
        workstreams: dict[str, Workstream] = {}
        for suffix, resource in (("a", "module:a"), ("b", "module:b"), ("c", "module:c")):
            passport, workstream = _registration(suffix, resource)
            passports[suffix] = passport
            workstreams[suffix] = workstream
            result = engine.register(
                passport,
                workstream,
                message_id=f"register-message-{suffix}",
            )
            assert result["created"] is True and result["progress"] == 5
        assert engine.register(
            passports["a"], workstreams["a"], message_id="register-message-a"
        )["created"] is False
        snapshot = engine.projection_snapshot()
        assert {item["progress"] for item in snapshot["workstreams"]} == {5}

        checkpoint_15 = _checkpoint(passports["a"], workstreams["a"], 15, "checkpoint-a-15", "event-a-15")
        assert engine.import_checkpoint(checkpoint_15, message_id="checkpoint-message-a-15")["progress"] == 15
        unchanged = replace(
            checkpoint_15,
            checkpoint_id="checkpoint-a-15-delta",
            event_id="event-a-15-delta",
            delta_ru="Процент не изменился: получено новое доказательство проверки.",
            current_ru="Продолжается тот же проверяемый этап.",
        )
        assert engine.import_checkpoint(unchanged, message_id="checkpoint-message-a-15-delta")["progress"] == 15

        checkpoint_40 = _checkpoint(passports["a"], workstreams["a"], 40, "checkpoint-a-40", "event-a-40")
        held = registry.acquire_thread_lock(
            passports["a"].executor.thread_id,  # type: ignore[union-attr]
            passports["a"].task_id,
            engine.fence,
            owner_workstream_id=workstreams["a"].workstream_id,
        )
        _raises(LockConflict, engine.import_checkpoint, checkpoint_40, message_id="checkpoint-message-a-40")
        registry.release_locks(held, engine.fence)
        assert engine.import_checkpoint(checkpoint_40, message_id="checkpoint-message-a-40")["progress"] == 40
        # An earlier checkpoint remains an idempotent receipt even after later progress.
        assert engine.import_checkpoint(checkpoint_15, message_id="checkpoint-message-a-15")["created"] is False
        downgrade = replace(
            checkpoint_40,
            checkpoint_id="checkpoint-a-invalid-downgrade",
            event_id="event-a-invalid-downgrade",
            progress_stage=25,
        )
        _raises(SupervisorError, engine.import_checkpoint, downgrade, message_id="checkpoint-invalid-downgrade")

        disjoint = (
            _candidate("candidate-a", passports["a"], workstreams["a"], "module:a", "src/a.py", "a" * 40, 2),
            _candidate("candidate-b", passports["b"], workstreams["b"], "module:b", "src/b.py", "b" * 40, 1),
        )
        scheduled = engine.schedule(disjoint, message_id="schedule-disjoint", active_logical_lane_id="lane-a")
        assert scheduled["kind"] == "release_sequence"
        assert scheduled["candidate_ids"] == ["candidate-a", "candidate-b"]
        assert scheduled["reservation"]["lock_count"] == 3
        lock_count = len(registry.inspect_locks())
        repeated_schedule = engine.schedule(disjoint, message_id="schedule-disjoint", active_logical_lane_id="lane-a")
        assert repeated_schedule["kind"] == "release_sequence" and len(registry.inspect_locks()) == lock_count

        overlap_b = _candidate(
            "candidate-overlap-b", passports["b"], workstreams["b"], "shared:contract", "src/shared.py", "c" * 40, 1
        )
        overlap_c = _candidate(
            "candidate-overlap-c", passports["c"], workstreams["c"], "shared:contract", "src/shared.py", "d" * 40, 2
        )
        conflict = engine.schedule((overlap_b, overlap_c), message_id="schedule-conflict")
        assert conflict["kind"] == "semantic_release_plan" and conflict["semantic_case"]

        same_task_one = replace(
            disjoint[0], holds_logical_lane=False, multi_pr_intent=False
        )
        same_task_two = replace(
            disjoint[1],
            task_id=same_task_one.task_id,
            workstream_id="workstream-same-task-two",
        )
        same_task_fast = schedule_releases((same_task_one, same_task_two), now=NOW)
        assert same_task_fast.kind == "release_sequence"
        assert tuple(same_task_fast.candidate_ids) == (
            same_task_two.candidate_id,
            same_task_one.candidate_id,
        )
        same_task_overlap = replace(
            same_task_two,
            resources=same_task_one.resources,
            passport_files=same_task_one.passport_files,
            diff_files=same_task_one.diff_files,
            modules=same_task_one.modules,
        )
        same_task_semantic = schedule_releases(
            (same_task_one, same_task_overlap), now=NOW
        )
        assert same_task_semantic.kind == "semantic_release_plan"
        assert same_task_semantic.semantic_case is not None
        assert len(same_task_semantic.semantic_case.candidates) == 2

        def malicious_decision(case: Any, first: ReleaseCandidate, second: ReleaseCandidate) -> ArbiterDecision:
            return ArbiterDecision(
                decision_id="malicious-release-plan",
                kind="release_plan",
                case_id=case.case_id,
                case_digest=case.case_digest,
                bindings=(first.binding(), second.binding()),
                steps=(
                    DecisionStep("malicious-step-one", "release", first.task_id, first.workstream_id, ()),
                    DecisionStep(
                        "malicious-step-two",
                        "release",
                        second.task_id,
                        second.workstream_id,
                        ("malicious-step-one",),
                    ),
                ),
                model="gpt-5.6-sol",
                reasoning="ultra",
                created_at=NOW,
            )

        unsafe = replace(overlap_b, unknown_classification=True)
        unsafe_schedule = schedule_releases((unsafe, overlap_c), now=NOW)
        assert unsafe_schedule.semantic_case is not None
        _raises(
            StaleArbiterDecision,
            validate_arbiter_release_decision,
            unsafe_schedule.semantic_case,
            malicious_decision(unsafe_schedule.semantic_case, unsafe, overlap_c),
        )

        dependency = replace(overlap_c, dependencies=(overlap_b.task_id,))
        blocked_dependency = replace(
            overlap_b,
            checks_green=False,
            admission_ready=False,
        )
        dependency_wait = schedule_releases(
            (blocked_dependency, dependency), now=NOW
        )
        assert dependency_wait.kind == "wait"
        assert dependency_wait.reason == "dependencies_not_complete"
        dependency_schedule = schedule_releases((overlap_b, dependency), now=NOW)
        assert dependency_schedule.semantic_case is not None
        _raises(
            StaleArbiterDecision,
            validate_arbiter_release_decision,
            dependency_schedule.semantic_case,
            malicious_decision(
                dependency_schedule.semantic_case, dependency, overlap_b
            ),
        )

        active = replace(
            overlap_b, holds_logical_lane=True, lane_healthy=True, multi_pr_intent=True
        )
        active_schedule = schedule_releases(
            (active, overlap_c), active_logical_lane_id=active.logical_lane_id, now=NOW
        )
        assert active_schedule.semantic_case is not None
        _raises(
            StaleArbiterDecision,
            validate_arbiter_release_decision,
            active_schedule.semantic_case,
            malicious_decision(active_schedule.semantic_case, overlap_c, active),
        )

        terminal = _terminal(passports["a"], workstreams["a"])
        verification_holder["value"] = ContourVerification(
            verification_id="verification-a-production",
            task_id=terminal.task_id,
            workstream_id=terminal.workstream_id,
            task_revision=terminal.task_revision,
            workstream_revision=terminal.workstream_revision,
            contour=terminal.closure_kind,
            terminal_digest=terminal_contract_digest(terminal),
            source="github_release_train_readback",
            passed=True,
            checks=("GitHub main and checks read back", "production probe passed"),
            evidence=("origin/main exact SHA", "deploy identity exact"),
            verified_at=NOW,
        )
        terminal_result = engine.import_terminal(terminal, message_id="terminal-message-a")
        assert terminal_result["progress"] == 100 and terminal_result["released_reservation_locks"] == 0
        assert registry.inspect_locks(kind="release_lane"), (
            "one workstream terminal must not release the task-level logical lane"
        )
        assert engine.import_terminal(terminal, message_id="terminal-message-a")["created"] is False
        distinct_terminal = replace(
            terminal,
            terminal_id="terminal-a-distinct-duplicate",
            event_id="event-terminal-a-distinct-duplicate",
        )
        _raises(
            SupervisorError,
            engine.import_terminal,
            distinct_terminal,
            message_id="terminal-message-a-distinct-duplicate",
        )
        assert len(
            registry.list_events(
                task_id=terminal.task_id,
                workstream_id=terminal.workstream_id,
                event_types=("technical_terminal",),
            )
        ) == 1
        attention = CuratorDelivery(registry, engine.fence)
        prepared = attention.prepare_one()
        assert prepared is not None
        assert prepared.curator_thread_id == passports["a"].curator.thread_id
        assert (
            "github-pr-v1:orenvlad-ai/dev-control-plane:123:"
            + "d" * 40
            + ":"
            + "e" * 40
        ) in prepared.handoff_ru
        assert (
            "hosted-release-v1:wb-core-eu-root:devcontrol.pro:" + "e" * 40
        ) in prepared.handoff_ru
        assert prepared.handoff_ru.endswith("Ответьте ровно «Задача принята».")
        delivery_receipt = attention.receipt(prepared)
        _raises(
            CuratorDeliveryError,
            attention.ack,
            replace(delivery_receipt, attention_id="attention-wrong"),
        )
        _raises(
            CuratorDeliveryError,
            attention.ack,
            replace(delivery_receipt, payload_digest="0" * 64),
        )
        attention.ack(delivery_receipt)
        assert attention.prepare_one() is None

        # Build the first projection; the server applies it but the ACK is lost.
        first_tick = engine.tick()
        assert first_tick.publish_results[0].status == "retry_scheduled"
        assert projection_store.public_state()["counts"]["awaiting_acceptance"] == 1
        original_body = transport.bodies[0]
        source_timestamp = json.loads(original_body)["timestamp"]
        transport_clock.value += 3_600
        time.sleep(0.01)
        retry_tick = engine.tick()
        assert retry_tick.projection_reserved is False
        assert retry_tick.publish_results[0].status == "delivered"
        assert transport.bodies[1] == original_body
        assert transport.header_timestamps[1] - source_timestamp > 30
        assert transport.header_timestamps[1] - transport.header_timestamps[0] > 30

        receipt = OwnerAcceptanceReceipt(
            receipt_id="owner-receipt-a",
            task_id=passports["a"].task_id,
            task_revision=1,
            curator_thread_id=passports["a"].curator.thread_id,
            reply=EXACT_OWNER_ACCEPTANCE,
            created_at=NOW,
        )
        accepted = engine.owner_accept(receipt, message_id="owner-acceptance-message-a")
        assert accepted["accepted"] is True
        assert accepted["released_reservation_locks"] == 3
        assert not [
            item
            for item in registry.inspect_locks()
            if item["owner_task_id"] == passports["a"].task_id
        ]
        assert engine.owner_accept(receipt, message_id="owner-acceptance-message-a")["created"] is False
        state_after_acceptance = engine.local_state()
        accepted_task = next(item for item in state_after_acceptance["projection"]["tasks"] if item["task_id"] == passport_task_id("a"))
        assert accepted_task["active"] is False and accepted_task["accepted"] is True
        _raises(
            SupervisorError,
            OwnerAcceptanceReceipt,
            receipt_id="bad-receipt",
            task_id=passports["b"].task_id,
            task_revision=1,
            curator_thread_id=passports["b"].curator.thread_id,
            reply="Да",
            created_at=NOW,
        )

        # One pending snapshot blocks another reservation; dirty state remains coalesced.
        accepted_tick = engine.tick()
        assert accepted_tick.projection_reserved is True
        assert accepted_tick.publish_results and accepted_tick.publish_results[0].status == "delivered"
        registry.reserve_projection_snapshot(
            supervisor_id=engine.supervisor_id,
            projection=engine.projection_snapshot(),
            event_id="projection-stale-generation-one",
            idempotency_key="projection-stale-generation-one-idem",
            fence=engine.fence,
        )
        registry.enqueue_outbox(
            "dirty-restart-proof",
            "projection_dirty",
            {"trigger_event_id": "restart-proof"},
            engine.fence,
            coalescible=True,
            coalesce_key="global-projection",
        )

        _http_read_only_smoke(engine)

        registry.release_generation(engine.fence)
        skipped = registry.acquire_generation("delivery-only-generation-2")
        registry.release_generation(skipped)
        restart_fence = registry.acquire_generation("supervisor-restart-generation-3")
        restart_engine = SupervisorEngine(
            registry,
            restart_fence,
            supervisor_id=engine.supervisor_id,
            publisher=publisher,
            contour_verifier=verifier,
        )
        stale = registry.list_outbox_summaries(
            kinds=("projection_snapshot",), states=("superseded",)
        )
        assert any(item["event_id"] == "projection-stale-generation-one" for item in stale)
        restart_tick = restart_engine.tick()
        assert restart_tick.projection_reserved is True
        assert restart_tick.publish_results[0].status == "delivered"
        hosted_source = projection_store.public_state()["source"]
        assert hosted_source["generation"] == restart_fence.generation == 3
        assert hosted_source["sequence"] == 1
        assert not any(item["task_id"] == passports["a"].task_id for item in projection_store.public_state()["tasks"])
        registry.release_generation(restart_fence)

        _multi_workstream_barrier_smoke(root / "multi-workstream")
        _scheduler_recovery_outcomes_smoke(root / "scheduler-recovery")
        _release_projection_dashboard_smoke(root / "release-projection")

    print("dev-control-plane-supervisor-v2-smoke passed")


def _registration(suffix: str, resource: str) -> tuple[TaskPassport, Workstream]:
    task_id = passport_task_id(suffix)
    executor = ExecutorIdentity(f"executor-thread-{suffix}", "mac-local", "gpt-5.6-sol", "ultra")
    final_pr = (
        "github-pr-v1:orenvlad-ai/dev-control-plane:123:"
        + "d" * 40
        + ":"
        + "e" * 40
    )
    manifest_prs = (
        (
            "github-pr-v1:orenvlad-ai/dev-control-plane:122:"
            + "c" * 40
            + ":"
            + "d" * 40,
            final_pr,
        )
        if suffix == "a"
        else (final_pr,)
    )
    passport = TaskPassport(
        task_id=task_id,
        revision=1,
        title=f"Supervisor smoke {suffix.upper()}",
        objective=f"Prove bounded Supervisor flow {suffix}.",
        expected_result="Durable evidence and exact acceptance.",
        contour="release:production",
        included_scope=(f"fixture {suffix}",),
        excluded_scope=("real AI", "real deploy"),
        constraints=("fake-only", "single writer"),
        acceptance=("all deterministic smoke assertions pass",),
        closure=("technical terminal and explicit owner receipt",),
        autonomy=AutonomyEnvelope(
            allowed_actions=(
                "codex_workspace_mutation",
                "self_merge",
                "self_hosted_deploy",
                "target_lane_release",
            ),
            prohibited_actions=("wb_github_command",),
            human_gate_reasons=("missing_credential",),
        ),
        workstream_ids=(f"workstream-{suffix}",),
        release_manifest=ReleaseClosureManifest(
            logical_lane_id=f"lane-{suffix}",
            pr_identities=manifest_prs,
            deploy_identities=(
                "hosted-release-v1:wb-core-eu-root:devcontrol.pro:" + "e" * 40,
            ),
            finalized_at=NOW,
        ),
        resources=(
            "target:orenvlad-ai/dev-control-plane",
            f"release-lane:lane-{suffix}",
            f"repo:{task_id}",
            resource,
        ),
        modules=(resource,),
        files=(f"src/{suffix}.py",),
        dependencies=(),
        multi_pr_intent=suffix == "a",
        multi_deploy_intent=False,
        curator=CuratorIdentity(f"curator-thread-{suffix}", "codex-desktop"),
        executor=executor,
        created_at=NOW,
    )
    workstream = Workstream(
        workstream_id=f"workstream-{suffix}",
        task_id=task_id,
        revision=1,
        generation=1,
        root_workstream_id=f"workstream-{suffix}",
        corrective_of_generation=None,
        title=f"Workstream {suffix.upper()}",
        objective=passport.objective,
        state="started",
        executor=executor,
        resources=(f"repo:{task_id}", resource),
        dependencies=(),
        created_at=NOW,
    )
    return passport, workstream


def _checkpoint(
    passport: TaskPassport,
    workstream: Workstream,
    progress: int,
    checkpoint_id: str,
    event_id: str,
) -> Checkpoint:
    assert passport.executor is not None
    return Checkpoint(
        checkpoint_id=checkpoint_id,
        event_id=event_id,
        task_id=passport.task_id,
        task_revision=1,
        workstream_id=workstream.workstream_id,
        workstream_revision=1,
        executor_generation=1,
        executor=passport.executor,
        progress_stage=progress,
        delta_ru=f"Получено доказательство canonical stage {progress}.",
        current_ru="Выполняется следующий проверяемый шаг.",
        evidence=(f"fixture:stage-{progress}",),
        created_at=NOW,
    )


def _terminal(passport: TaskPassport, workstream: Workstream) -> TerminalEvidence:
    assert passport.executor is not None
    return TerminalEvidence(
        terminal_id="terminal-a-production",
        event_id="event-terminal-a-production",
        task_id=passport.task_id,
        task_revision=1,
        workstream_id=workstream.workstream_id,
        workstream_revision=1,
        executor_generation=1,
        executor=passport.executor,
        closure_kind="release:production",
        summary_ru="Production-контур доказан fake readback без внешней мутации.",
        evidence=("origin/main:" + "e" * 40, "probe:healthy"),
        checks=("supervisor-smoke:passed",),
        pr_identities=passport.release_manifest.pr_identities,  # type: ignore[union-attr]
        deploy_identities=passport.release_manifest.deploy_identities,  # type: ignore[union-attr]
        owner_acceptance_required=True,
        created_at=NOW,
    )


def _candidate(
    candidate_id: str,
    passport: TaskPassport,
    workstream: Workstream,
    resource: str,
    file_name: str,
    sha: str,
    owner_priority: int,
) -> ReleaseCandidate:
    suffix = candidate_id.rsplit("-", 1)[-1]
    return ReleaseCandidate(
        candidate_id=candidate_id,
        task_id=passport.task_id,
        workstream_id=workstream.workstream_id,
        logical_lane_id=f"lane-{suffix}",
        target_id="dev-control-plane",
        task_revision=1,
        workstream_revision=1,
        pr_head_sha=sha,
        resources=(resource,),
        passport_files=(file_name,),
        diff_files=(file_name,),
        modules=(resource,),
        owner_priority=owner_priority,
        critical_path_value=1,
        unblock_value=1,
        risk_score=1,
        fairness_credit=1,
        ready_since=NOW,
        created_at=NOW,
        holds_logical_lane=candidate_id == "candidate-a",
        lane_healthy=True,
        multi_pr_intent=candidate_id == "candidate-a",
    )


def passport_task_id(suffix: str) -> str:
    return f"task-supervisor-{suffix}"


def _release_projection_dashboard_smoke(root: Path) -> None:
    registry = SupervisorRegistry(root / "supervisor.sqlite3", lease_seconds=120)
    fence = registry.acquire_generation("release-projection-generation")
    engine = SupervisorEngine(
        registry, fence, supervisor_id="release-projection-supervisor"
    )
    passport, stream = _registration("p", "module:projection")
    engine.register(passport, stream, message_id="release-projection-register")

    def registration(name: str, head: str) -> None:
        registry.append_event(
            f"release-registration-{name}",
            "release_candidate_registered",
            {
                "schema": "dev-control-plane/release-candidate-registration/v2",
                "task_id": passport.task_id,
                "task_revision": 1,
                "workstream_id": stream.workstream_id,
                "workstream_revision": 1,
                "expected_pr_head_sha": head,
                "target_id": "dev-control-plane",
            },
            fence,
            task_id=passport.task_id,
            workstream_id=stream.workstream_id,
        )

    heads = {name: character * 40 for name, character in (
        ("registered", "1"),
        ("admitted", "2"),
        ("proof", "3"),
        ("observed", "4"),
        ("old", "5"),
        ("new", "6"),
        ("done", "7"),
        ("production", "8"),
    )}
    registration("registered", heads["registered"])
    registration("admitted", heads["admitted"])
    admitted = _candidate(
        "candidate-admitted",
        passport,
        stream,
        "module:projection",
        "src/projection.py",
        heads["admitted"],
        1,
    )
    registry.append_event(
        "release-admission-focused",
        "release_candidate_admitted",
        {
            "schema": "dev-control-plane/release-candidate-admission/v2",
            "source_event_id": "release-registration-admitted",
            "candidate": asdict(admitted),
            "release_candidate": {
                "repo": "orenvlad-ai/dev-control-plane",
                "pr_number": 202,
            },
            "target_adapter": "self-release-train-v2",
            "scheduler_truth": {
                "pr_state": "OPEN",
                "merge_commit_sha": None,
            },
            "proof_only": False,
        },
        fence,
        task_id=passport.task_id,
        workstream_id=stream.workstream_id,
    )

    registration("proof", heads["proof"])
    proof = replace(
        _candidate(
            "candidate-proof",
            passport,
            stream,
            "module:projection",
            "src/projection.py",
            heads["proof"],
            1,
        ),
        admission_ready=False,
        checks_green=True,
    )
    registry.append_event(
        "release-proof-focused",
        "release_wait",
        {
            "schema": "dev-control-plane/supervisor-event/v2",
            "decision": {"kind": "wait", "candidate_ids": []},
            "candidates": [asdict(proof)],
            "created_at": NOW,
            "proof_only": True,
        },
        fence,
        task_id=passport.task_id,
        workstream_id=stream.workstream_id,
    )

    registration("observed", heads["observed"])
    observed = _candidate(
        "candidate-observed",
        passport,
        stream,
        "module:projection",
        "src/projection.py",
        heads["observed"],
        1,
    )
    registry.append_event(
        "release-observation-focused",
        "release_action_observed",
        {
            "schema": "dev-control-plane/release-action-observed-event/v2",
            "release_action_event_id": "release-action-focused",
            "target_adapter": "self-release-train-v2",
            "observation": {
                "status": "waiting_foreign_lane",
                "reason_code": "private_reason_must_not_render",
                "candidate_id": observed.candidate_id,
                "task_id": passport.task_id,
                "workstream_id": stream.workstream_id,
                "task_revision": 1,
                "workstream_revision": 1,
                "expected_head_sha": heads["observed"],
                "observed_head_sha": heads["observed"],
                "observed_at": NOW,
            },
        },
        fence,
        task_id=passport.task_id,
        workstream_id=stream.workstream_id,
    )

    registration("old", heads["old"])
    registration("new", heads["new"])
    registry.append_event(
        "release-superseded-focused",
        "release_superseded",
        {
            "schema": "dev-control-plane/release-superseded/v2",
            "candidate_id": "candidate-old",
            "task_revision": 1,
            "workstream_revision": 1,
            "pr_head_sha": heads["old"],
            "replacement_head_sha": heads["new"],
            "observation_event_id": "release-observation-readmission-focused",
        },
        fence,
        task_id=passport.task_id,
        workstream_id=stream.workstream_id,
    )

    for name, contour, deploy_identity in (
        ("done", "release:done", None),
        (
            "production",
            "release:production",
            "hosted-release-v1:wb-core-eu-root:devcontrol.pro:" + "a" * 40,
        ),
    ):
        registry.append_event(
            f"release-completed-{name}-focused",
            "release_completed",
            {
                "schema": "dev-control-plane/release-result-event/v2",
                "release_action_event_id": f"release-action-{name}-focused",
                "target_adapter": "self-release-train-v2",
                "receipt": {
                    "schema": "dev-control-plane/release-action-receipt/v2",
                    "status": "passed",
                    "candidate_id": f"candidate-{name}",
                    "task_id": passport.task_id,
                    "workstream_id": stream.workstream_id,
                    "task_revision": 1,
                    "workstream_revision": 1,
                    "pr_head_sha": heads[name],
                    "pr_url": f"https://github.com/orenvlad-ai/dev-control-plane/pull/{207 if name == 'done' else 208}",
                    "merge_sha": ("9" if name == "done" else "a") * 40,
                    "contour": contour,
                    "deploy_identity": deploy_identity,
                    "verification_identity": f"focused-{name}-verification",
                    "admission_binding": None,
                    "completed_at": NOW,
                },
            },
            fence,
            task_id=passport.task_id,
            workstream_id=stream.workstream_id,
        )

    snapshot = engine.projection_snapshot()
    rows = {
        item["head_sha"]: item
        for item in snapshot["release_lanes"]
        if item["task_id"] == passport.task_id
    }
    assert rows[heads["registered"]]["deploy_status"] == "candidate_registered"
    assert rows[heads["admitted"]]["deploy_status"] == "candidate_admitted"
    assert rows[heads["proof"]]["status"] == "merged"
    assert rows[heads["proof"]]["deploy_status"] == "proof_only"
    assert rows[heads["observed"]]["deploy_status"] == "waiting_foreign_lane"
    assert rows[heads["old"]]["deploy_status"] == "superseded_readmission"
    assert rows[heads["new"]]["deploy_status"] == "candidate_registered"
    assert rows[heads["done"]]["status"] == "merged"
    assert rows[heads["done"]]["deploy_status"] == "repository_done"
    assert rows[heads["done"]]["environment"] == "repository"
    assert rows[heads["production"]]["status"] == "production"
    assert rows[heads["production"]]["deploy_status"] == "production"

    task_row = next(item for item in snapshot["tasks"] if item["task_id"] == passport.task_id)
    stream_row = next(
        item for item in snapshot["workstreams"] if item["workstream_id"] == stream.workstream_id
    )

    def html(row: Mapping[str, Any]) -> str:
        return render_dashboard(
            {
                "stale": False,
                "last_seen": NOW,
                "last_seen_age_seconds": 0,
                "tasks": [
                    {
                        **task_row,
                        "workstreams": [stream_row],
                        "release_lanes": [row],
                        "incidents": [],
                        "attention": [],
                        "acceptance": None,
                    }
                ],
            }
        )

    rendered = {
        name: html(rows[heads[name]])
        for name in (
            "registered",
            "admitted",
            "proof",
            "observed",
            "old",
            "new",
            "done",
            "production",
        )
    }
    assert "PR зарегистрирован" in rendered["registered"]
    assert "кандидат допущен" in rendered["admitted"]
    assert "merge доказан" in rendered["proof"]
    assert "действие Release Train не требуется" in rendered["proof"]
    assert "ожидание внешней release lane" in rendered["observed"]
    assert "старый PR head заменён; новый зарегистрирован" in rendered["old"]
    assert "repo-only выпуск подтверждён; deploy не выполнялся" in rendered["done"]
    assert "развёртывание подтверждено" in rendered["production"]
    assert "private_reason_must_not_render" not in rendered["observed"]
    assert "scheduler_truth" not in "".join(rendered.values())
    registry.release_generation(fence)


def _multi_workstream_barrier_smoke(root: Path) -> None:
    registry = SupervisorRegistry(root / "supervisor.sqlite3", lease_seconds=120)
    fence = registry.acquire_generation("multi-workstream-generation")
    executor_one = ExecutorIdentity("executor-thread-multi-one", "mac-local", "gpt-5.6-sol", "ultra")
    executor_two = ExecutorIdentity("executor-thread-multi-two", "mac-local", "gpt-5.6-sol", "ultra")
    passport = TaskPassport(
        task_id="task-multi",
        revision=1,
        title="Multi-workstream closure barrier",
        objective="Require every declared current workstream before owner acceptance.",
        expected_result="Exactly one task-level terminal attention after both streams close.",
        contour="release:production",
        included_scope=("two independent workstreams",),
        excluded_scope=("real AI", "real deploy"),
        constraints=("one immutable closure manifest",),
        acceptance=("both terminal proofs are independently verified",),
        closure=("one owner attention after the envelope barrier",),
        autonomy=AutonomyEnvelope(
            allowed_actions=(
                "codex_workspace_mutation",
                "self_merge",
                "self_hosted_deploy",
                "target_lane_release",
            ),
            prohibited_actions=("wb_github_command",),
        ),
        workstream_ids=("workstream-multi-one", "workstream-multi-two"),
        release_manifest=ReleaseClosureManifest(
            logical_lane_id="lane-multi",
            pr_identities=(
                "github-pr-v1:orenvlad-ai/dev-control-plane:301:" + "1" * 40 + ":" + "2" * 40,
                "github-pr-v1:orenvlad-ai/dev-control-plane:302:" + "3" * 40 + ":" + "4" * 40,
            ),
            deploy_identities=(
                "hosted-release-v1:wb-core-eu-root:devcontrol.pro:" + "4" * 40,
            ),
            finalized_at=NOW,
        ),
        resources=(
            "target:orenvlad-ai/dev-control-plane",
            "release-lane:lane-multi",
            "repo:task-multi",
            "module:multi-one",
            "module:multi-two",
        ),
        modules=("module:multi-one", "module:multi-two"),
        files=("src/multi_one.py", "src/multi_two.py"),
        dependencies=(),
        multi_pr_intent=True,
        multi_deploy_intent=False,
        curator=CuratorIdentity("curator-thread-multi", "codex-desktop"),
        executor=None,
        created_at=NOW,
    )
    streams = (
        Workstream(
            workstream_id="workstream-multi-one",
            task_id=passport.task_id,
            revision=1,
            generation=1,
            root_workstream_id="workstream-multi-one",
            corrective_of_generation=None,
            title="Multi one",
            objective=passport.objective,
            state="started",
            executor=executor_one,
            resources=("repo:task-multi", "module:multi-one"),
            dependencies=(),
            created_at=NOW,
        ),
        Workstream(
            workstream_id="workstream-multi-two",
            task_id=passport.task_id,
            revision=1,
            generation=1,
            root_workstream_id="workstream-multi-two",
            corrective_of_generation=None,
            title="Multi two",
            objective=passport.objective,
            state="started",
            executor=executor_two,
            resources=("repo:task-multi", "module:multi-two"),
            dependencies=(),
            created_at=NOW,
        ),
    )
    verification: dict[str, ContourVerification] = {}
    engine = SupervisorEngine(
        registry,
        fence,
        supervisor_id=stable_supervisor_id(str(root)),
        contour_verifier=lambda _passport, _terminal: verification["value"],
    )
    for index, stream in enumerate(streams, 1):
        engine.register(passport, stream, message_id=f"register-multi-{index}")

    def terminal_for(index: int) -> TerminalEvidence:
        stream = streams[index - 1]
        assert stream.executor is not None
        return TerminalEvidence(
            terminal_id=f"terminal-multi-{index}",
            event_id=f"event-terminal-multi-{index}",
            task_id=passport.task_id,
            task_revision=1,
            workstream_id=stream.workstream_id,
            workstream_revision=1,
            executor_generation=1,
            executor=stream.executor,
            closure_kind="release:production",
            summary_ru=f"Workstream {index} независимо завершён.",
            evidence=(f"origin/main:{index}" + "e" * 39, "probe:healthy"),
            checks=(f"multi-{index}:passed",),
            pr_identities=passport.release_manifest.pr_identities,  # type: ignore[union-attr]
            deploy_identities=passport.release_manifest.deploy_identities,  # type: ignore[union-attr]
            owner_acceptance_required=True,
            created_at=NOW,
        )

    def set_verification(terminal: TerminalEvidence, index: int) -> None:
        verification["value"] = ContourVerification(
            verification_id=f"verification-multi-{index}",
            task_id=terminal.task_id,
            workstream_id=terminal.workstream_id,
            task_revision=terminal.task_revision,
            workstream_revision=terminal.workstream_revision,
            contour=terminal.closure_kind,
            terminal_digest=terminal_contract_digest(terminal),
            source="github_release_train_readback",
            passed=True,
            checks=(f"multi-{index}:passed",),
            evidence=(f"origin/main exact multi {index}", f"deploy exact multi {index}"),
            verified_at=NOW,
        )

    first = terminal_for(1)
    set_verification(first, 1)
    first_result = engine.import_terminal(first, message_id="terminal-multi-message-1")
    assert first_result["technical_complete"] is False and first_result["attention_id"] is None
    premature = OwnerAcceptanceReceipt(
        receipt_id="owner-receipt-multi",
        task_id=passport.task_id,
        task_revision=1,
        curator_thread_id=passport.curator.thread_id,
        reply=EXACT_OWNER_ACCEPTANCE,
        created_at=NOW,
    )
    _raises(SupervisorError, engine.owner_accept, premature, message_id="owner-multi-message")
    partial = engine.projection_snapshot()
    partial_task = next(item for item in partial["tasks"] if item["task_id"] == passport.task_id)
    partial_streams = {item["workstream_id"]: item for item in partial["workstreams"]}
    assert partial_task["status"] == "working"
    assert partial_streams["workstream-multi-one"]["status"] == "awaiting_acceptance"
    assert partial_streams["workstream-multi-two"]["progress"] == 5
    assert not partial["attention"]

    second = terminal_for(2)
    set_verification(second, 2)
    second_result = engine.import_terminal(second, message_id="terminal-multi-message-2")
    assert second_result["technical_complete"] is True and second_result["attention_id"]
    terminal_attention = registry.list_outbox_records(kinds=("curator_attention",))
    assert len(terminal_attention) == 1 and terminal_attention[0]["payload"]["kind"] == "terminal"
    assert engine.owner_accept(premature, message_id="owner-multi-message")["accepted"] is True
    registry.release_generation(fence)


def _scheduler_recovery_outcomes_smoke(root: Path) -> None:
    def scenario(suffix: str, outcome: str) -> int:
        scenario_root = root / f"{outcome}-{suffix}"
        registry = SupervisorRegistry(scenario_root / "supervisor.sqlite3", lease_seconds=120)
        fence = registry.acquire_generation(f"scheduler-recovery-{outcome}")
        engine = SupervisorEngine(
            registry,
            fence,
            supervisor_id=stable_supervisor_id(str(scenario_root)),
        )
        passport, stream = _registration(suffix, f"module:recovery-{suffix}")
        engine.register(passport, stream, message_id=f"register-recovery-{outcome}")
        candidate = _candidate(
            f"candidate-{suffix}", passport, stream, f"module:recovery-{suffix}",
            f"src/{suffix}.py", suffix * 40, 1,
        )
        engine.schedule((candidate,), message_id=f"schedule-recovery-{outcome}")
        payload = (
            {
                "action": {
                    "closure_id": f"closure-{suffix}",
                    "task_id": candidate.task_id,
                    "task_revision": 1,
                    "logical_lane_id": candidate.logical_lane_id,
                },
                "receipt": {
                    "closure_id": f"closure-{suffix}",
                    "task_id": candidate.task_id,
                    "task_revision": 1,
                    "status": "released",
                },
            }
            if outcome == "target_lane_closure_completed"
            else {"receipt": {"candidate_id": candidate.candidate_id, "pr_head_sha": candidate.pr_head_sha}}
            if outcome == "release_completed"
            else {"candidate_id": candidate.candidate_id, "pr_head_sha": candidate.pr_head_sha}
        )
        registry.append_event(
            f"{outcome}-recovery-{suffix}",
            outcome,
            payload,
            fence,
            task_id=candidate.task_id,
            workstream_id=candidate.workstream_id,
        )
        engine.tick()
        owned = sum(
            item["owner_workstream_id"] == candidate.workstream_id for item in registry.inspect_locks()
        )
        registry.release_scheduler_reservation_owner(
            task_id=candidate.task_id,
            workstream_id=candidate.workstream_id,
            fence=fence,
        )
        registry.release_generation(fence)
        return owned

    assert scenario("a", "release_completed") == 3, (
        "completed multi-PR lane must remain fenced until continuation/terminal"
    )
    assert scenario("b", "release_completed") == 3, (
        "completed single-PR lane remains fenced until task-level closure"
    )
    assert scenario("c", "release_stalled") == 3, (
        "parked workstream alone cannot release the task-level target lane"
    )
    assert scenario("d", "target_lane_closure_completed") == 0, (
        "exact task-level target-lane closure releases every selected owner"
    )


def _http_read_only_smoke(engine: SupervisorEngine) -> None:
    server = SupervisorHTTPServer(engine, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        connection = http.client.HTTPConnection(host, port, timeout=5)
        for path in ("/api/v2/health", "/api/v2/readiness", "/api/v2/state"):
            connection.request("GET", path)
            response = connection.getresponse()
            payload = json.loads(response.read())
            assert response.status == HTTPStatus.OK and isinstance(payload, dict)
        before = hashlib.sha256(
            json.dumps(engine.local_state(), ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest()
        for method in ("POST", "PUT", "PATCH", "DELETE", "OPTIONS"):
            connection.request(method, "/api/v2/state", body=b"{}", headers={"Content-Type": "application/json"})
            response = connection.getresponse()
            payload = json.loads(response.read())
            assert response.status == HTTPStatus.METHOD_NOT_ALLOWED
            assert payload["reason_code"] == "local_status_api_read_only"
        after = hashlib.sha256(
            json.dumps(engine.local_state(), ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest()
        assert before == after
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _endpoint_gate_smoke() -> None:
    _raises(
        ProjectionPublishError,
        ProjectionPublisher,
        endpoint="https://example.com/api/v2/ingest",
        key=KEY,
        transport=lambda *_args: TransportResponse(500, b"{}"),
    )
    _raises(
        ProjectionPublishError,
        ProjectionPublisher,
        endpoint=PRODUCTION_PROJECTION_ENDPOINT + "/",
        key=KEY,
        transport=lambda *_args: TransportResponse(500, b"{}"),
    )


def _curl_secrecy_smoke() -> None:
    secret_signature = "sha256=" + "f" * 64
    observed: dict[str, object] = {}

    def fake_run(arguments: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        observed["arguments"] = list(arguments)
        config_path = Path(arguments[-1])
        config = config_path.read_text(encoding="utf-8")
        observed["config"] = config
        observed["config_mode"] = stat.S_IMODE(config_path.stat().st_mode)
        body_match = re.search(r'data-binary = "@([^"]+)"', config)
        output_match = re.search(r'output = "([^"]+)"', config)
        assert body_match and output_match
        body_path = Path(body_match.group(1))
        observed["body_mode"] = stat.S_IMODE(body_path.stat().st_mode)
        observed["body"] = body_path.read_bytes()
        Path(output_match.group(1)).write_bytes(b'{"ok":true}')
        return subprocess.CompletedProcess(arguments, 0, stdout=b"200", stderr=b"")

    with patch("dev_control_plane.projection_client.subprocess.run", side_effect=fake_run):
        response = _https_transport(
            PRODUCTION_PROJECTION_ENDPOINT,
            b'{"safe":"body"}',
            {"Content-Type": "application/json", "X-DCP-Signature": secret_signature},
            5,
        )
    arguments = observed["arguments"]
    assert isinstance(arguments, list)
    joined = " ".join(arguments)
    assert secret_signature not in joined and "X-DCP-Signature" not in joined
    assert "-k" not in arguments and "--insecure" not in arguments
    assert observed["config_mode"] == 0o600 and observed["body_mode"] == 0o600
    assert secret_signature in str(observed["config"])
    assert response.status == 200 and response.body == b'{"ok":true}'


def _raises(exception: type[BaseException], function: object, *args: object, **kwargs: object) -> BaseException:
    try:
        function(*args, **kwargs)  # type: ignore[misc]
    except exception as exc:
        return exc
    except Exception as exc:
        raise AssertionError(f"expected {exception.__name__}, got {type(exc).__name__}: {exc}") from exc
    raise AssertionError(f"expected {exception.__name__}")


if __name__ == "__main__":
    main()
