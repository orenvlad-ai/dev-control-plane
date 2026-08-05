"""Comprehensive fake-only smoke for the Orchestrator v2 deterministic core."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import os
from pathlib import Path
import sqlite3
import stat
import sys
from tempfile import TemporaryDirectory
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (SRC, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dev_control_plane.incident_policy import (  # noqa: E402
    CausalFailure,
    DuplicateBudgetError,
    HumanGateRequest,
    HumanGateValidationError,
    IncidentContext,
    IncidentPolicyError,
    begin_incident_budget,
    build_causal_fingerprint,
    observe_same_failure,
    record_arbiter_application,
    record_incident_arbiter_decision,
    record_independent_verification,
    record_successor_proof,
    renew_incident_budget,
    validate_human_gate,
)
from dev_control_plane.orchestration_contracts import (  # noqa: E402
    ArbiterDecision,
    AutonomyEnvelope,
    Checkpoint,
    CuratorIdentity,
    DecisionStep,
    ExecutorIdentity,
    OrchestrationValidationError,
    RevisionBinding,
    TaskPassport,
    TerminalEvidence,
    Workstream,
    checkpoint_from_mapping,
    contract_to_dict,
    task_passport_from_mapping,
    terminal_evidence_from_mapping,
    validate_checkpoint_binding,
    validate_terminal_binding,
)
from dev_control_plane.release_scheduler import (  # noqa: E402
    ReleaseCandidate,
    StaleArbiterDecision,
    revalidate_case_against_candidates,
    schedule_releases,
    validate_arbiter_release_decision,
)
from dev_control_plane.supervisor_registry import (  # noqa: E402
    CASConflict,
    IdempotencyConflict,
    LeaseHeldError,
    LockConflict,
    RegistryValidationError,
    StaleGenerationError,
    SupervisorRegistry,
)

NOW = "2026-08-05T00:00:00Z"
SHA_A = "a" * 40
SHA_B = "b" * 40


def main() -> None:
    _contract_smoke()
    _scheduler_smoke()
    _incident_smoke()
    with TemporaryDirectory(prefix="dev-control-plane-v2-registry-") as raw:
        root = Path(raw)
        _path_safety_smoke(root)
        _migration_backup_smoke(root)
        _projection_transport_durability_smoke(root)
        _registry_smoke(root)
    print("dev-control-plane-v2-registry-smoke passed")


def _path_safety_smoke(root: Path) -> None:
    protected = root / "must-remain-plain.sqlite3"
    protected.write_text("do-not-touch", encoding="utf-8")

    hardlink_state = root / "hardlink-state"
    hardlink_state.mkdir(mode=0o700)
    hardlink_database = hardlink_state / "supervisor.sqlite3"
    os.link(protected, hardlink_database)
    _raises(RegistryValidationError, SupervisorRegistry, hardlink_database)
    if protected.read_text(encoding="utf-8") != "do-not-touch":
        raise AssertionError("registry followed a hard-linked database path")

    lock_state = root / "linked-lock-state"
    lock_state.mkdir(mode=0o700)
    lock_path = lock_state / "supervisor.sqlite3.migrate.lock"
    lock_path.symlink_to(protected)
    _raises(
        RegistryValidationError,
        SupervisorRegistry,
        lock_state / "supervisor.sqlite3",
    )
    if protected.read_text(encoding="utf-8") != "do-not-touch":
        raise AssertionError("registry followed a migration-lock symlink")


def _contract_smoke() -> None:
    passport = _passport()
    parsed = task_passport_from_mapping(contract_to_dict(passport))
    if parsed != passport:
        raise AssertionError("TaskPassport strict round trip changed content")
    invalid_payload = contract_to_dict(passport)
    invalid_payload["legacy_sprint"] = True
    _raises(OrchestrationValidationError, task_passport_from_mapping, invalid_payload)
    _raises(
        OrchestrationValidationError,
        ExecutorIdentity,
        thread_id="executor-bad",
        host_id="mac-local",
        model="gpt-5.5",
        reasoning="xhigh",
    )

    executor = _executor("executor-1")
    checkpoint = Checkpoint(
        checkpoint_id="checkpoint-1",
        event_id="event-checkpoint-1",
        task_id=passport.task_id,
        task_revision=1,
        workstream_id="workstream-1",
        workstream_revision=1,
        executor_generation=1,
        executor=executor,
        progress_stage=15,
        delta_ru="Проверен текущий контракт.",
        current_ru="Создаётся изолированный registry.",
        evidence=("fixture:preflight",),
        created_at=NOW,
    )
    if checkpoint_from_mapping(contract_to_dict(checkpoint)) != checkpoint:
        raise AssertionError("Checkpoint strict round trip changed content")
    validate_checkpoint_binding(
        checkpoint,
        task_revision=1,
        workstream_revision=1,
        executor_generation=1,
        executor=executor,
    )
    _raises(
        OrchestrationValidationError,
        validate_checkpoint_binding,
        checkpoint,
        task_revision=2,
        workstream_revision=1,
        executor_generation=1,
        executor=executor,
    )

    terminal = TerminalEvidence(
        terminal_id="terminal-1",
        event_id="event-terminal-1",
        task_id=passport.task_id,
        task_revision=1,
        workstream_id="workstream-1",
        workstream_revision=1,
        executor_generation=1,
        executor=executor,
        closure_kind="release:production",
        summary_ru="Контур production доказан.",
        evidence=("origin/main:abc", "probe:https"),
        checks=("smoke:passed",),
        pr_identities=("orenvlad-ai/example#1",),
        deploy_identities=("deploy:pilot-1",),
        owner_acceptance_required=True,
        created_at=NOW,
    )
    if terminal_evidence_from_mapping(contract_to_dict(terminal)) != terminal:
        raise AssertionError("TerminalEvidence strict round trip changed content")
    validate_terminal_binding(
        terminal,
        contour="release:production",
        task_revision=1,
        workstream_revision=1,
        executor_generation=1,
        executor=executor,
    )


def _registry_smoke(root: Path) -> None:
    db_path = root / "private-state" / "supervisor.sqlite3"
    registry = SupervisorRegistry(db_path, lease_seconds=120)
    pragmas = registry.pragmas()
    expected = {"journal_mode": "wal", "synchronous": 2, "foreign_keys": 1, "user_version": 3}
    for key, value in expected.items():
        if pragmas[key] != value:
            raise AssertionError(f"unsafe SQLite pragma {key}: {pragmas}")
    if stat.S_IMODE(db_path.stat().st_mode) != 0o600 or stat.S_IMODE(db_path.parent.stat().st_mode) != 0o700:
        raise AssertionError("registry paths are not private")

    fence = registry.acquire_generation("supervisor-smoke-1")
    competing = SupervisorRegistry(db_path, lease_seconds=120)
    _raises(LeaseHeldError, competing.acquire_generation, "supervisor-smoke-2")

    passport = _passport()
    task = registry.create_task(passport, fence, idempotency_key="create-task-1")
    replay = registry.create_task(passport, fence, idempotency_key="create-task-1")
    if task != replay or task.revision != 1:
        raise AssertionError("task creation is not idempotent")
    _raises(
        IdempotencyConflict,
        registry.create_task,
        replace(passport, title="Different request"),
        fence,
        idempotency_key="create-task-1",
    )

    workstream = Workstream(
        workstream_id="workstream-1",
        task_id=passport.task_id,
        revision=1,
        generation=1,
        root_workstream_id="workstream-1",
        corrective_of_generation=None,
        title="Registry foundation",
        objective="Prove durable orchestration primitives.",
        state="started",
        executor=passport.executor,
        resources=("repo:dev-control-plane", "module:registry"),
        dependencies=(),
        created_at=NOW,
    )
    registry.create_workstream(workstream, fence)

    first_executor = registry.register_executor(
        passport.task_id,
        workstream.workstream_id,
        _executor("executor-1"),
        expected_current_generation=0,
        checkpoint_digest=_sha("checkpoint-1"),
        fence=fence,
    )
    successor = registry.register_executor(
        passport.task_id,
        workstream.workstream_id,
        _executor("executor-2"),
        expected_current_generation=1,
        checkpoint_digest=_sha("checkpoint-verified"),
        fence=fence,
    )
    if successor.state != "pending" or registry.current_executor(passport.task_id, workstream.workstream_id) != first_executor:
        raise AssertionError("predecessor became stale before successor proof")
    _raises(
        StaleGenerationError,
        registry.append_event,
        "event-pending-successor",
        "checkpoint",
        {"safe": True},
        fence,
        task_id=passport.task_id,
        workstream_id=workstream.workstream_id,
        executor_generation=2,
    )
    activated = registry.activate_successor(
        passport.task_id,
        workstream.workstream_id,
        2,
        proof_event_id="successor-proof-1",
        fence=fence,
    )
    if activated.state != "active" or activated.proof_event_id != "successor-proof-1":
        raise AssertionError("successor proof did not atomically activate the successor")
    _raises(
        StaleGenerationError,
        registry.append_event,
        "event-late-predecessor",
        "checkpoint",
        {"safe": True},
        fence,
        task_id=passport.task_id,
        workstream_id=workstream.workstream_id,
        executor_generation=1,
    )
    if not registry.append_event(
        "event-current-executor",
        "checkpoint",
        {"progress": 15},
        fence,
        task_id=passport.task_id,
        workstream_id=workstream.workstream_id,
        executor_generation=2,
    ):
        raise AssertionError("current executor event was not accepted")
    if registry.append_event(
        "event-current-executor",
        "checkpoint",
        {"progress": 15},
        fence,
        task_id=passport.task_id,
        workstream_id=workstream.workstream_id,
        executor_generation=2,
    ):
        raise AssertionError("duplicate event was not deduplicated")
    _raises(
        IdempotencyConflict,
        registry.append_event,
        "event-current-executor",
        "checkpoint",
        {"progress": 25},
        fence,
        task_id=passport.task_id,
        workstream_id=workstream.workstream_id,
        executor_generation=2,
    )

    _concurrent_cas_smoke(db_path, fence, passport.task_id)
    _lock_smoke(registry, fence, passport.task_id, workstream.workstream_id)

    if not registry.accept_inbox_and_enqueue(
        message_id="inbox-1",
        source="codex-app-server",
        inbox_payload={"event": "turn.completed"},
        outbox_event_id="outbox-progress-1",
        outbox_kind="projection_progress",
        outbox_payload={"progress": 40},
        fence=fence,
        task_id=passport.task_id,
        coalescible=True,
        coalesce_key=passport.task_id,
    ):
        raise AssertionError("transactional inbox/outbox intake failed")
    if registry.accept_inbox_and_enqueue(
        message_id="inbox-1",
        source="codex-app-server",
        inbox_payload={"event": "turn.completed"},
        outbox_event_id="outbox-progress-1",
        outbox_kind="projection_progress",
        outbox_payload={"progress": 40},
        fence=fence,
        task_id=passport.task_id,
        coalescible=True,
        coalesce_key=passport.task_id,
    ):
        raise AssertionError("duplicate inbox message created duplicate outbox work")
    _raises(
        RegistryValidationError,
        registry.enqueue_outbox,
        "outbox-terminal-bad",
        "terminal",
        {"terminal": True},
        fence,
        coalescible=True,
        coalesce_key=passport.task_id,
    )
    registry.enqueue_outbox(
        "outbox-attention-1",
        "attention",
        {"status": "acceptance_pending"},
        fence,
        task_id=passport.task_id,
    )

    # A fresh process-like instance observes the same durable queue after an offline period.
    restarted = SupervisorRegistry(db_path, lease_seconds=120)
    claimed = restarted.claim_outbox(fence, worker_id="projection-worker", limit=1)
    if len(claimed) != 1 or restarted.pending_outbox_count() != 2:
        raise AssertionError("restart/offline outbox replay lost durable messages")
    restarted.ack_outbox(claimed[0].event_id, claimed[0].claim_token, fence)
    stranded = restarted.claim_outbox(fence, worker_id="projection-worker", limit=1, visibility_timeout=0.01)
    if len(stranded) != 1:
        raise AssertionError("failed to reserve an outbox item for generation fencing smoke")

    registry.release_generation(fence)
    new_fence = restarted.acquire_generation("supervisor-smoke-2")
    if new_fence.generation != fence.generation + 1:
        raise AssertionError("restart did not advance the singleton generation")
    _raises(
        StaleGenerationError,
        registry.append_event,
        "event-stale-supervisor",
        "checkpoint",
        {"progress": 55},
        fence,
    )
    _raises(
        StaleGenerationError,
        restarted.ack_outbox,
        stranded[0].event_id,
        stranded[0].claim_token,
        fence,
    )
    replayed = restarted.claim_outbox(
        new_fence,
        worker_id="projection-worker-new-generation",
        limit=10,
        now=time.time() + 1,
    )
    if not replayed:
        raise AssertionError("new generation did not replay expired inflight/pending outbox")
    for message in replayed:
        restarted.ack_outbox(message.event_id, message.claim_token, new_fence)
    if restarted.pending_outbox_count() != 0:
        raise AssertionError("outbox receipts did not reach durable delivered state")
    if not restarted.health()["ok"]:
        raise AssertionError(f"registry quick_check failed: {restarted.health()}")
    restarted.release_generation(new_fence)


def _concurrent_cas_smoke(db_path: Path, fence: object, task_id: str) -> None:
    barrier = threading.Barrier(2)
    outcomes: list[str] = []
    outcome_lock = threading.Lock()

    def mutate(state: str) -> None:
        local = SupervisorRegistry(db_path, lease_seconds=120)
        barrier.wait()
        try:
            local.update_task_state(task_id, expected_revision=1, new_state=state, fence=fence)
        except CASConflict:
            result = "conflict"
        else:
            result = "updated"
        with outcome_lock:
            outcomes.append(result)

    threads = [threading.Thread(target=mutate, args=(state,)) for state in ("waiting_release", "recovering")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    if any(thread.is_alive() for thread in threads) or sorted(outcomes) != ["conflict", "updated"]:
        raise AssertionError(f"optimistic CAS concurrency was not single-winner: {outcomes}")


def _lock_smoke(registry: SupervisorRegistry, fence: object, task_id: str, workstream_id: str) -> None:
    task_grant = registry.acquire_task_lock(task_id, fence, owner_workstream_id=workstream_id)
    registry.release_locks(task_grant, fence)
    thread_grant = registry.acquire_thread_lock("executor-thread-2", task_id, fence, owner_workstream_id=workstream_id)
    registry.release_locks(thread_grant, fence)
    resources = registry.acquire_resource_locks(
        ("module:z", "module:a"), task_id, fence, owner_workstream_id=workstream_id
    )
    if resources.keys != ("module:a", "module:z"):
        raise AssertionError("resource locks were not acquired in deterministic sorted order")
    _raises(
        LockConflict,
        registry.acquire_resource_locks,
        ("module:new", "module:z"),
        "other-task",
        fence,
    )
    active_keys = {item["lock_key"] for item in registry.inspect_locks(kind="resource")}
    if "module:new" in active_keys:
        raise AssertionError("failed multi-resource acquisition left a partial lock")
    registry.release_locks(resources, fence)
    lane = registry.acquire_release_lane("target:wb-core", task_id, fence, owner_workstream_id=workstream_id)
    renewed = registry.renew_lock(lane, fence, ttl=600)
    if renewed.expires_at <= lane.expires_at:
        raise AssertionError("global release lane lease was not renewed")
    registry.release_locks(renewed, fence)


def _migration_backup_smoke(root: Path) -> None:
    legacy_path = root / "legacy-state" / "supervisor.sqlite3"
    legacy_path.parent.mkdir(parents=True)
    connection = sqlite3.connect(legacy_path)
    try:
        connection.execute("CREATE TABLE archived_legacy_audit(id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
        connection.execute("INSERT INTO archived_legacy_audit VALUES ('legacy-1', 'sanitized')")
        connection.commit()
    finally:
        connection.close()
    registry = SupervisorRegistry(legacy_path)
    backups = tuple(registry.backup_dir.glob("*.before-v0-to-v3.*.sqlite3"))
    if len(backups) != 1 or stat.S_IMODE(backups[0].stat().st_mode) != 0o600:
        raise AssertionError("upgrade did not create one private recoverable pre-migration backup")
    with sqlite3.connect(backups[0]) as backup:
        row = backup.execute("SELECT payload FROM archived_legacy_audit WHERE id = 'legacy-1'").fetchone()
    if row != ("sanitized",):
        raise AssertionError("pre-migration backup did not preserve legacy audit evidence")

    # Build an exact v1-shaped fixture with existing snapshots, then prove the
    # v2 migration seeds counters from envelope coordinates rather than row
    # counts and leaves a recoverable pre-migration backup.
    v1_path = root / "v1-state" / "supervisor.sqlite3"
    v1_registry = SupervisorRegistry(v1_path)
    v1_fence = v1_registry.acquire_generation("migration-v1-seed")
    for index in range(1, 4):
        coordinates = v1_registry.reserve_projection_snapshot(
            supervisor_id="migration-supervisor",
            projection={"tasks": []},
            event_id=f"migration-projection-{index}",
            idempotency_key=f"migration-idem-{index}",
            fence=v1_fence,
        )
        if coordinates != {"generation": 1, "sequence": index, "revision": index}:
            raise AssertionError(f"unexpected v1 seed coordinates: {coordinates}")
    v1_registry.release_generation(v1_fence)
    with sqlite3.connect(v1_path) as connection:
        connection.execute("DROP TABLE projection_transport_state")
        connection.execute("DROP TABLE workspace_bindings")
        connection.execute("DELETE FROM schema_migrations WHERE version IN (2, 3)")
        connection.execute("PRAGMA user_version = 1")
        connection.commit()
    migrated = SupervisorRegistry(v1_path)
    if migrated.projection_transport_state() != {"generation": 1, "sequence": 3, "revision": 3}:
        raise AssertionError("v1 snapshot coordinates were not recovered during migration")
    v1_backups = tuple(migrated.backup_dir.glob("*.before-v1-to-v3.*.sqlite3"))
    if len(v1_backups) != 1:
        raise AssertionError("v1-to-v2 migration did not create exactly one recoverable backup")
    with sqlite3.connect(v1_backups[0]) as backup:
        if int(backup.execute("SELECT COUNT(*) FROM outbox WHERE kind='projection_snapshot'").fetchone()[0]) != 3:
            raise AssertionError("v1 migration backup lost projection transport evidence")
    migrated_fence = migrated.acquire_generation("migration-v2-resume")
    resumed = migrated.reserve_projection_snapshot(
        supervisor_id="migration-supervisor",
        projection={"tasks": []},
        event_id="migration-projection-resumed",
        idempotency_key="migration-idem-resumed",
        fence=migrated_fence,
    )
    if resumed != {"generation": 2, "sequence": 1, "revision": 4}:
        raise AssertionError(f"migrated counters did not resume monotonically: {resumed}")
    migrated.release_generation(migrated_fence)


def _projection_transport_durability_smoke(root: Path) -> None:
    db_path = root / "projection-transport" / "supervisor.sqlite3"
    registry = SupervisorRegistry(db_path, delivered_projection_retention=2)
    fence = registry.acquire_generation("projection-retention-smoke")
    for index in range(1, 5):
        coordinates = registry.reserve_projection_snapshot(
            supervisor_id="projection-retention-supervisor",
            projection={"tasks": []},
            event_id=f"projection-retained-{index}",
            idempotency_key=f"projection-retained-idem-{index}",
            fence=fence,
        )
        if coordinates != {"generation": 1, "sequence": index, "revision": index}:
            raise AssertionError(f"projection counter drifted before compaction: {coordinates}")
        claimed = registry.claim_outbox(
            fence,
            worker_id="projection-retention-worker",
            kinds=("projection_snapshot",),
        )
        if len(claimed) != 1:
            raise AssertionError("projection snapshot was not durably claimable")
        registry.ack_outbox(claimed[0].event_id, claimed[0].claim_token, fence)

    delivered = registry.list_outbox_summaries(
        kinds=("projection_snapshot",), states=("delivered",)
    )
    if tuple(item["event_id"] for item in delivered) != (
        "projection-retained-3",
        "projection-retained-4",
    ):
        raise AssertionError(f"delivered projection retention was not bounded: {delivered}")
    if registry.projection_transport_state() != {"generation": 1, "sequence": 4, "revision": 4}:
        raise AssertionError("projection counters depended on compacted outbox rows")

    for event_id, kind in (("terminal-preserved", "terminal"), ("attention-preserved", "attention")):
        registry.enqueue_outbox(event_id, kind, {"sanitized": True}, fence)
    preserved = registry.claim_outbox(
        fence,
        worker_id="nonprojection-retention-worker",
        kinds=("terminal", "attention"),
    )
    for message in preserved:
        registry.ack_outbox(message.event_id, message.claim_token, fence)
    if {item["event_id"] for item in registry.list_outbox_summaries(states=("delivered",))} != {
        "projection-retained-3",
        "projection-retained-4",
        "terminal-preserved",
        "attention-preserved",
    }:
        raise AssertionError("projection compaction removed terminal/attention history")

    registry.release_generation(fence)
    restored_path = root / "projection-restored" / "supervisor.sqlite3"
    registry.backup(restored_path)
    restored = SupervisorRegistry(restored_path, delivered_projection_retention=2)
    if restored.projection_transport_state() != {"generation": 1, "sequence": 4, "revision": 4}:
        raise AssertionError("online backup/restore lost durable projection counters")
    if {item["event_id"] for item in restored.list_outbox_summaries(kinds=("terminal", "attention"))} != {
        "terminal-preserved",
        "attention-preserved",
    }:
        raise AssertionError("online backup/restore lost non-coalescible audit history")
    restored_fence = restored.acquire_generation("projection-restored-supervisor")
    resumed = restored.reserve_projection_snapshot(
        supervisor_id="projection-retention-supervisor",
        projection={"tasks": []},
        event_id="projection-after-restore",
        idempotency_key="projection-after-restore-idem",
        fence=restored_fence,
    )
    if resumed != {"generation": 2, "sequence": 1, "revision": 5}:
        raise AssertionError(f"restored transport did not resume monotonically: {resumed}")
    replay = restored.reserve_projection_snapshot(
        supervisor_id="projection-retention-supervisor",
        projection={"tasks": []},
        event_id="projection-after-restore",
        idempotency_key="projection-after-restore-idem",
        fence=restored_fence,
    )
    if replay != resumed:
        raise AssertionError("retained projection reservation was not idempotent after restore")
    restored.release_generation(restored_fence)


def _scheduler_smoke() -> None:
    first = _candidate(
        candidate_id="candidate-a",
        task_id="task-a",
        workstream_id="workstream-a",
        lane="lane-a",
        sha=SHA_A,
        resource="module:a",
        file_name="src/a.py",
        owner_priority=10,
    )
    second = _candidate(
        candidate_id="candidate-b",
        task_id="task-b",
        workstream_id="workstream-b",
        lane="lane-b",
        sha=SHA_B,
        resource="module:b",
        file_name="src/b.py",
        owner_priority=0,
    )
    decision = schedule_releases((second, first), active_logical_lane_id="lane-a", now=NOW)
    if decision.kind != "release_sequence" or decision.candidate_ids != ("candidate-a", "candidate-b"):
        raise AssertionError(f"hard-order continuity was not deterministic: {decision}")

    overlap = replace(
        second,
        resources=("module:a",),
        passport_files=("src/a.py",),
        diff_files=("src/a.py",),
        modules=("module:a",),
    )
    semantic = schedule_releases((first, overlap), now=NOW)
    if semantic.kind != "semantic_release_plan" or semantic.semantic_case is None:
        raise AssertionError("overlapping candidates did not create a mandatory RELEASE_PLAN case")
    case = semantic.semantic_case
    release_decision = ArbiterDecision(
        decision_id="release-decision-1",
        kind="release_plan",
        case_id=case.case_id,
        case_digest=case.case_digest,
        bindings=tuple(candidate.binding() for candidate in case.candidates),
        steps=(
            DecisionStep("release-a", "release", "task-a", "workstream-a"),
            DecisionStep("release-b", "release", "task-b", "workstream-b", depends_on=("release-a",)),
        ),
        model="gpt-5.6-sol",
        reasoning="ultra",
        created_at=NOW,
    )
    if validate_arbiter_release_decision(case, release_decision) != ("release-a", "release-b"):
        raise AssertionError("valid bound arbiter DAG was not accepted")
    _raises(
        StaleArbiterDecision,
        revalidate_case_against_candidates,
        case,
        (replace(first, task_revision=2), overlap),
    )
    conflict = schedule_releases((replace(first, merge_conflict=True), overlap), now=NOW)
    if conflict.kind != "semantic_release_plan":
        raise AssertionError("two admitted candidates with a merge conflict did not require RELEASE_PLAN")
    singleton_conflict = schedule_releases((replace(first, merge_conflict=True),), now=NOW)
    if singleton_conflict.kind != "wait":
        raise AssertionError("a single conflicted candidate must wait for remediation")
    nonready_overlap = replace(overlap, checks_green=False)
    fast_path = schedule_releases((first, nonready_overlap), now=NOW)
    if fast_path.kind != "release_sequence" or fast_path.candidate_ids != (first.candidate_id,):
        raise AssertionError("a non-ready overlap candidate blocked the one-green fast path")
    mismatch = schedule_releases((replace(first, passport_diff_mismatch=True),), now=NOW)
    if mismatch.kind != "wait":
        raise AssertionError("an unsafe singleton Passport/diff mismatch was released")


def _incident_smoke() -> None:
    fingerprint = build_causal_fingerprint(
        stage="full-checks",
        error_code="check-failed",
        check_id="semantic-smoke",
        target_id="dev-control-plane",
        normalized_cause_code="fixture-regression",
    )
    context = IncidentContext(1, _sha("strategy-1"), _sha("evidence-1"), "checkpoint-verified-1")
    first_failure = CausalFailure(
        fingerprint,
        "full-checks",
        "check-failed",
        "semantic-smoke",
        1,
        ("check:failed",),
        True,
    )
    transition = begin_incident_budget(
        task_id="task-incident", workstream_id="workstream-incident", failure=first_failure, context=context
    )
    if transition.action != "retry_current_executor":
        raise AssertionError("first causal occurrence did not reserve one retry")
    _raises(
        IncidentPolicyError,
        observe_same_failure,
        transition.state,
        replace(first_failure, fresh_truth_verified=False),
    )
    transition = observe_same_failure(transition.state, first_failure)
    if transition.action != "start_successor_executor" or transition.state.successor_generation != 2:
        raise AssertionError("second causal occurrence did not reserve exactly one successor")
    waiting = observe_same_failure(transition.state, first_failure)
    if waiting.action != "await_successor_proof" or waiting.state.predecessor_stale:
        raise AssertionError("predecessor became stale without successor proof")
    state = record_successor_proof(
        transition.state, successor_generation=2, proof_event_id="successor-proof-incident"
    )
    successor_failure = replace(first_failure, executor_generation=2)
    transition = observe_same_failure(state, successor_failure)
    if transition.action != "invoke_incident_arbiter" or transition.state.incident_case_id is None:
        raise AssertionError("third causal occurrence did not reserve the one incident arbiter")
    state = transition.state
    arbiter = ArbiterDecision(
        decision_id="incident-decision-1",
        kind="incident",
        case_id=state.incident_case_id or "missing",
        case_digest=state.incident_case_digest or _sha("missing"),
        bindings=(RevisionBinding("task-incident", 1, "workstream-incident", 1, SHA_A, ("module:registry",)),),
        steps=(
            DecisionStep(
                "incident-remediation-1",
                "apply_repo_remediation",
                "task-incident",
                "workstream-incident",
            ),
        ),
        model="gpt-5.6-sol",
        reasoning="ultra",
        created_at=NOW,
    )
    state = record_incident_arbiter_decision(state, arbiter)
    _raises(
        IncidentPolicyError,
        record_incident_arbiter_decision,
        state,
        replace(arbiter, decision_id="incident-decision-2"),
    )
    applied = record_arbiter_application(state, decision_id=arbiter.decision_id)
    if applied.action != "verify_arbiter_application":
        raise AssertionError("arbiter application skipped independent verification")
    parked = record_independent_verification(applied.state, passed=False)
    if parked.action != "park_workstream" or not parked.state.parked:
        raise AssertionError("same failure after arbiter was not parked")
    if observe_same_failure(parked.state, successor_failure).action != "park_workstream":
        raise AssertionError("parked incident reopened a forbidden retry path")
    _raises(
        DuplicateBudgetError,
        renew_incident_budget,
        parked.state,
        new_fingerprint=fingerprint,
        new_context=context,
        justification="No material change.",
    )
    renewed = renew_incident_budget(
        parked.state,
        new_fingerprint=fingerprint,
        new_context=replace(context, strategy_digest=_sha("strategy-2")),
        justification="The bounded remediation strategy changed.",
    )
    if renewed.failure_count != 0 or renewed.retry_used:
        raise AssertionError("material strategy change did not create a clean bounded budget")

    valid_gate = HumanGateRequest(
        gate_id="gate-credential-1",
        task_id="task-incident",
        workstream_id="workstream-incident",
        reason_code="missing_credential",
        requested_actions=("Добавьте GitHub credential в локальное secret-хранилище.",),
        human_exclusive=True,
        already_authorized_by_passport=False,
        independent_safe_work_complete=True,
        repo_owned_remediation_exhausted=True,
        evidence=("sanitized readiness: missing",),
    )
    if validate_human_gate(valid_gate) != valid_gate:
        raise AssertionError("strict allowlisted HumanGate was not accepted")
    _raises(
        HumanGateValidationError,
        validate_human_gate,
        replace(valid_gate, human_exclusive=False),
    )
    _raises(
        HumanGateValidationError,
        HumanGateRequest,
        **{**valid_gate.__dict__, "requested_actions": ("Action one", "Action two")},
    )


def _passport() -> TaskPassport:
    return TaskPassport(
        task_id="task-registry-smoke",
        revision=1,
        title="Orchestrator v2 registry smoke",
        objective="Prove deterministic durable orchestration state.",
        expected_result="All fake-only registry invariants pass.",
        contour="release:production",
        included_scope=("new v2 registry modules",),
        excluded_scope=("real Codex", "live deploy"),
        constraints=("single writer", "no secrets"),
        acceptance=("restart and fencing are proven",),
        closure=("smoke exits zero", "owner acceptance remains explicit"),
        autonomy=AutonomyEnvelope(
            allowed_actions=(
                "codex_workspace_mutation",
                "repo_edit",
                "local_checks",
                "self_merge",
                "self_hosted_deploy",
                "target_lane_release",
            ),
            prohibited_actions=("wb_github_command",),
            human_gate_reasons=("missing_credential", "interactive_2fa"),
        ),
        workstream_ids=("workstream-1",),
        release_manifest=None,
        resources=(
            "target:orenvlad-ai/dev-control-plane",
            "release-lane:dev-control-plane",
            "repo:dev-control-plane",
            "module:registry",
        ),
        modules=("supervisor_registry",),
        files=("src/dev_control_plane/supervisor_registry.py",),
        dependencies=(),
        multi_pr_intent=False,
        multi_deploy_intent=False,
        curator=CuratorIdentity("curator-thread", "codex-desktop"),
        executor=_executor("executor-1"),
        created_at=NOW,
    )


def _executor(thread_id: str) -> ExecutorIdentity:
    return ExecutorIdentity(thread_id, "mac-local", "gpt-5.6-sol", "ultra")


def _candidate(
    *,
    candidate_id: str,
    task_id: str,
    workstream_id: str,
    lane: str,
    sha: str,
    resource: str,
    file_name: str,
    owner_priority: int,
) -> ReleaseCandidate:
    return ReleaseCandidate(
        candidate_id=candidate_id,
        task_id=task_id,
        workstream_id=workstream_id,
        logical_lane_id=lane,
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
        holds_logical_lane=lane == "lane-a",
        lane_healthy=True,
        multi_pr_intent=lane == "lane-a",
    )


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _raises(exception_type: type[BaseException], function: object, *args: object, **kwargs: object) -> BaseException:
    try:
        function(*args, **kwargs)  # type: ignore[misc]
    except exception_type as exc:
        return exc
    except Exception as exc:
        raise AssertionError(
            f"expected {exception_type.__name__}, observed {type(exc).__name__}: {exc}"
        ) from exc
    raise AssertionError(f"expected {exception_type.__name__} from {getattr(function, '__name__', function)!r}")


if __name__ == "__main__":
    main()
