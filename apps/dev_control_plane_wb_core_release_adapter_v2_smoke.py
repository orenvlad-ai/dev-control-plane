"""Deterministic fake-API smoke for the external wb-core v2 adapter."""

from __future__ import annotations

from dataclasses import asdict, replace
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (SRC, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dev_control_plane.wb_core_release_adapter import (  # noqa: E402
    WB_CORE_ADMISSION_MARKER,
    WB_CORE_COMPLETION_MARKER,
    WbCoreAdmissionBinding,
    WbCoreAdmissionProof,
    WbCoreCommandReceipt,
    WbCoreContourAdapter,
    WbCoreLaneReleaseProof,
    WbCoreLaneReleaseRequest,
    WbCorePullReadback,
    WbCoreQueueReadback,
    WbCoreReleaseAdapter,
    WbCoreReleaseAdapterError,
    WbCoreReleaseLaneAdapter,
    WbCoreReleaseRequest,
    WbCoreTerminalProof,
    derive_wb_core_target_task_id,
    pull_readback_from_github,
    wb_core_admission_binding_from_mapping,
    wb_core_lane_release_outcome_from_mapping,
    wb_core_lane_release_request_from_mapping,
    wb_core_release_outcome_from_mapping,
    wb_core_release_request_from_mapping,
    wb_core_terminal_request_from_contracts,
    wb_core_runtime_result,
)
from dev_control_plane.orchestration_contracts import (  # noqa: E402
    ArbiterDecision,
    AutonomyEnvelope,
    CuratorIdentity,
    DecisionStep,
    ExecutorIdentity,
    ReleaseClosureManifest,
    RevisionBinding,
    TaskPassport,
    TerminalEvidence,
    contract_digest,
    contract_to_dict,
)
from dev_control_plane.release_train import PullRequestTruth  # noqa: E402
from apps import dev_control_plane_supervisor_v2 as supervisor_app  # noqa: E402


HEAD = "a" * 40
DRIFT_HEAD = "b" * 40
MERGE = "c" * 40
PASSPORT = "d" * 64
TASK = "task:wb-core:0001"
TARGET_TASK = derive_wb_core_target_task_id(TASK)
PR = 731


class FakeApi:
    def __init__(self, pull: WbCorePullReadback, queue: WbCoreQueueReadback) -> None:
        self.pull = pull
        self.queue = queue
        self.required = True
        self.submissions: list[tuple[int, str, str]] = []
        self.lane_submissions: list[tuple[int, str, str]] = []
        self.admit_after_submit = True
        self.release_after_submit = True

    def orchestration_required(self) -> bool:
        return self.required

    def read_queue_status(
        self, release_proof_prs: tuple[int, ...] = ()
    ) -> WbCoreQueueReadback:
        return replace(
            self.queue,
            release_proofs=tuple(
                proof
                for proof in self.queue.release_proofs
                if proof.owner_pr in release_proof_prs
            ),
        )

    def read_pull(self, pr_number: int) -> WbCorePullReadback:
        assert pr_number == PR
        return self.pull

    def submit_admission(
        self,
        pr_number: int,
        command: str,
        command_digest: str,
    ) -> WbCoreCommandReceipt:
        assert pr_number == PR and command_digest == REQUEST.admission_command_digest()
        self.submissions.append((pr_number, command, command_digest))
        if self.admit_after_submit:
            proof = _admission()
            self.pull = replace(
                self.pull,
                labels=("task:standard", "scope:repo-only", "release:ready", "release:lane-owner"),
                admission_proofs=(proof,),
                submitted_command_digests=(command_digest,),
            )
            self.queue = _queue(
                lane_status="owned",
                owner_pr=PR,
                task_id=TARGET_TASK,
                revision=REQUEST.task_revision,
                queue_status="ready",
                active_prs=(PR,),
            )
        return WbCoreCommandReceipt(command_digest, 9001, "2026-08-05T00:00:00Z")

    def submit_lane_release(
        self,
        anchor_pr: int,
        command: str,
        command_digest: str,
    ) -> WbCoreCommandReceipt:
        assert anchor_pr == PR
        assert command_digest == LANE_REQUEST.release_command_digest()
        self.lane_submissions.append((anchor_pr, command, command_digest))
        self.pull = replace(
            self.pull,
            submitted_command_digests=(
                *self.pull.submitted_command_digests,
                command_digest,
            ),
        )
        if self.release_after_submit:
            self.queue = _queue(
                release_proofs=(
                    WbCoreLaneReleaseProof(
                        owner_pr=PR,
                        target_task_id=TARGET_TASK,
                        task_revision=LANE_REQUEST.task_revision,
                        outcome=LANE_REQUEST.outcome,
                        evidence_digest=LANE_REQUEST.evidence_digest,
                    ),
                ),
            )
        return WbCoreCommandReceipt(command_digest, 9002, "2026-08-05T00:00:01Z")


class FakeGuard:
    def __init__(self) -> None:
        self.checks = 0

    def checkpoint(self) -> None:
        self.checks += 1


class FakeRegistry:
    def __init__(
        self,
        passport: TaskPassport,
        *,
        workstream_revision: int = 1,
        task_state: str = "active",
        workstream_state: str = "waiting_release",
        events: Sequence[Mapping[str, Any]] = (),
        outbox_records: Sequence[Mapping[str, Any]] = (),
        generation: int = 7,
    ) -> None:
        self.task = SimpleNamespace(
            task_id=passport.task_id,
            revision=passport.revision,
            state=task_state,
            passport=asdict(passport),
        )
        self.workstream = SimpleNamespace(
            task_id=passport.task_id,
            workstream_id=passport.workstream_ids[0],
            revision=workstream_revision,
            state=workstream_state,
        )
        self.events = [dict(event) for event in events]
        self.outbox_records = [dict(item) for item in outbox_records]
        self.generation = generation
        self.owner_id = "supervisor-owner-smoke"

    def replace_passport(self, passport: TaskPassport) -> None:
        self.task.revision = passport.revision
        self.task.passport = asdict(passport)

    def get_task(self, task_id: str) -> Any | None:
        return self.task if task_id == self.task.task_id else None

    def get_workstream(self, workstream_id: str) -> Any | None:
        return self.workstream if workstream_id == self.workstream.workstream_id else None

    def list_events(
        self,
        *,
        task_id: str | None = None,
        event_types: Sequence[str] = (),
    ) -> tuple[Mapping[str, Any], ...]:
        return tuple(
            event
            for event in self.events
            if (task_id is None or event.get("task_id") == task_id)
            and (not event_types or event.get("event_type") in event_types)
        )

    def get_event(self, event_id: str) -> Mapping[str, Any] | None:
        return next(
            (event for event in self.events if event.get("event_id") == event_id),
            None,
        )

    def list_outbox_records(
        self,
        *,
        kinds: Sequence[str] = (),
    ) -> tuple[Mapping[str, Any], ...]:
        return tuple(
            item
            for item in self.outbox_records
            if not kinds or item.get("kind") in kinds
        )

    def current_generation(self) -> Mapping[str, Any]:
        return {
            "generation": self.generation,
            "owner_id": self.owner_id,
            "expires_at": 4_102_444_800.0,
        }


class FakeGitHub:
    def __init__(
        self,
        truth: PullRequestTruth,
        *,
        on_read: Any | None = None,
    ) -> None:
        self.truth = truth
        self.on_read = on_read
        self.reads = 0
        self.merges = 0

    def read_pr(self, *, repo: str, pr_number: int) -> PullRequestTruth:
        assert repo in {
            supervisor_app.SELF_REPO,
            supervisor_app.WB_CORE_REPOSITORY,
        }
        assert pr_number == self.truth.number
        self.reads += 1
        if self.on_read is not None:
            self.on_read(self.reads)
        return self.truth

    def merge_pr(
        self,
        *,
        repo: str,
        pr_number: int,
        expected_head_sha: str,
    ) -> None:
        assert repo == supervisor_app.SELF_REPO
        assert pr_number == self.truth.number
        assert expected_head_sha == self.truth.head_sha
        self.merges += 1
        self.truth = replace(
            self.truth,
            state="MERGED",
            mergeable="UNKNOWN",
            merge_state="UNKNOWN",
            merge_commit_sha=MERGE,
        )


class BindingChainApi:
    def __init__(self, request: WbCoreReleaseRequest) -> None:
        self.request = request
        self.pull = WbCorePullReadback(
            number=request.pr_number,
            state="OPEN",
            is_draft=False,
            head_sha=request.expected_head_sha,
            base_ref="main",
            labels=("task:standard", "scope:repo-only", "release:staged"),
            url=f"https://github.com/orenvlad-ai/wb-core/pull/{request.pr_number}",
        )
        self.queue = _queue()
        self.submissions = 0
        self.lane_submissions = 0

    def orchestration_required(self) -> bool:
        return True

    def read_queue_status(
        self, release_proof_prs: tuple[int, ...] = ()
    ) -> WbCoreQueueReadback:
        return replace(
            self.queue,
            release_proofs=tuple(
                proof
                for proof in self.queue.release_proofs
                if proof.owner_pr in release_proof_prs
            ),
        )

    def read_pull(self, pr_number: int) -> WbCorePullReadback:
        assert pr_number == self.request.pr_number
        return self.pull

    def submit_admission(
        self,
        pr_number: int,
        command: str,
        command_digest: str,
    ) -> WbCoreCommandReceipt:
        assert pr_number == self.request.pr_number
        assert command == self.request.admission_command()
        assert command_digest == self.request.admission_command_digest()
        self.submissions += 1
        proof = WbCoreAdmissionProof(
            pr_number=pr_number,
            owner_pr=pr_number,
            head_sha=self.request.expected_head_sha,
            target_task_id=self.request.target_task_id,
            task_revision=self.request.task_revision,
            passport_digest=self.request.passport_digest,
        )
        self.pull = replace(
            self.pull,
            labels=("task:standard", "scope:repo-only", "release:ready"),
            admission_proofs=(proof,),
            submitted_command_digests=(command_digest,),
        )
        self.queue = _queue(
            lane_status="owned",
            owner_pr=pr_number,
            task_id=self.request.target_task_id,
            revision=self.request.task_revision,
            queue_status="ready",
        )
        return WbCoreCommandReceipt(
            command_digest,
            9101,
            "2026-08-05T00:00:00Z",
        )

    def make_terminal(self) -> None:
        self.pull = replace(
            self.pull,
            state="MERGED",
            labels=("task:standard", "scope:repo-only", "release:done"),
            merge_sha=MERGE,
            terminal_proofs=(
                WbCoreTerminalProof(self.request.pr_number, MERGE, "repo-only"),
            ),
        )

    def submit_lane_release(
        self,
        anchor_pr: int,
        command: str,
        command_digest: str,
    ) -> WbCoreCommandReceipt:
        assert anchor_pr == self.request.pr_number
        parts = command.split()
        assert parts[:3] == ["/wb-core", "orchestration", "release-lane"]
        revision = int(parts[7])
        outcome = parts[9]
        evidence = parts[11].removeprefix("sha256:")
        self.lane_submissions += 1
        self.pull = replace(
            self.pull,
            submitted_command_digests=(
                *self.pull.submitted_command_digests,
                command_digest,
            ),
        )
        self.queue = _queue(
            release_proofs=(
                WbCoreLaneReleaseProof(
                    owner_pr=anchor_pr,
                    target_task_id=self.request.target_task_id,
                    task_revision=revision,
                    outcome=outcome,
                    evidence_digest=evidence,
                ),
            ),
        )
        return WbCoreCommandReceipt(
            command_digest,
            9102,
            "2026-08-05T00:00:01Z",
        )


REQUEST = WbCoreReleaseRequest(
    candidate_id="candidate-wb-1",
    task_id=TASK,
    target_task_id=TARGET_TASK,
    workstream_id="workstream-wb-1",
    task_revision=3,
    workstream_revision=2,
    passport_digest=PASSPORT,
    pr_number=PR,
    expected_head_sha=HEAD,
    contour="release:done",
)

LANE_REQUEST = WbCoreLaneReleaseRequest(
    closure_event_id="closure-event-wb-1",
    task_id=TASK,
    target_task_id=TARGET_TASK,
    task_revision=3,
    anchor_pr=PR,
    outcome="completed",
    evidence_digest="e" * 64,
)


def main() -> None:
    assert REQUEST.target_id == "orenvlad-ai/wb-core"
    assert LANE_REQUEST.target_id == "orenvlad-ai/wb-core"
    _queue_parser_smoke()
    _github_parser_smoke()
    _admission_and_idempotency_smoke()
    _foreign_lane_smoke()
    _terminal_smoke()
    _runtime_mapping_smoke()
    _lane_release_smoke()
    _contour_adapter_smoke()
    _head_drift_smoke()
    _mismatch_and_failure_smoke()
    _fence_smoke()
    _production_resolver_smoke()
    _self_contour_executor_smoke()
    _composite_executor_smoke()
    _managed_queue_reader_smoke()
    _target_lane_composition_smoke()
    _incident_application_disposition_smoke()
    _parked_admission_lane_composition_smoke()
    _admission_binding_chain_e2e_smoke()
    print("wb-core release adapter v2 smoke: ok")


def _admission_and_idempotency_smoke() -> None:
    api = FakeApi(_staged_pull(), _queue())
    boundaries: list[str] = []
    adapter = WbCoreReleaseAdapter(
        api,
        fence_guard=lambda boundary, request: boundaries.append(boundary) if request == REQUEST else None,
        max_polls=2,
    )
    result = adapter.advance(REQUEST)
    assert result.status == "admitted" and result.reason_code == "exact_admission_proven"
    assert len(api.submissions) == 1
    assert api.submissions[0][1] == REQUEST.admission_command()
    assert "before_admission_command" in boundaries and "after_admission_command" in boundaries

    # The Actions-owned proof makes a repeated delivery purely observational.
    repeated = adapter.advance(REQUEST)
    assert repeated.status == "admitted" and len(api.submissions) == 1
    assert repeated.next_poll_after_seconds == 30.0

    # A crash after GitHub accepted the exact comment but before proof appears
    # is recovered by command-digest readback without a duplicate comment.
    pending_api = FakeApi(
        replace(
            _staged_pull(),
            submitted_command_digests=(REQUEST.admission_command_digest(),),
        ),
        _queue(),
    )
    pending = WbCoreReleaseAdapter(
        pending_api,
        fence_guard=lambda _boundary, _request: None,
    ).advance(REQUEST)
    assert pending.status == "admission_submitted" and not pending_api.submissions


def _foreign_lane_smoke() -> None:
    api = FakeApi(
        _staged_pull(),
        _queue(
            lane_status="owned",
            owner_pr=700,
            task_id="foreign-task-0001",
            revision=9,
            queue_status="running",
            active_prs=(700,),
        ),
    )
    result = WbCoreReleaseAdapter(
        api,
        fence_guard=lambda _boundary, _request: None,
    ).advance(REQUEST)
    assert result.status == "waiting_foreign_lane"
    assert result.reason_code == "foreign_release_lane" and not api.submissions


def _terminal_smoke() -> None:
    done_pull = replace(
        _staged_pull(),
        state="MERGED",
        labels=("task:standard", "scope:repo-only", "release:done", "release:lane-owner"),
        merge_sha=MERGE,
        admission_proofs=(_admission(),),
        terminal_proofs=(WbCoreTerminalProof(PR, MERGE, "repo-only"),),
    )
    done_api = FakeApi(
        done_pull,
        _queue(
            lane_status="owned",
            owner_pr=PR,
            task_id=TARGET_TASK,
            revision=3,
            active_prs=(PR,),
            integrity="attention",
            signals=("terminal-release-lane-owner",),
        ),
    )
    done = WbCoreReleaseAdapter(
        done_api,
        fence_guard=lambda _boundary, _request: None,
    ).advance(REQUEST)
    assert done.status == "terminal" and done.terminal_label == "release:done"
    assert done.merge_sha == MERGE and done.pr_identity == (
        f"github-pr-v1:orenvlad-ai/wb-core:{PR}:{HEAD}:{MERGE}"
    )

    production_request = replace(REQUEST, contour="release:production")
    production_pull = replace(
        done_pull,
        labels=("task:standard", "scope:live-runtime", "release:production", "release:lane-owner"),
        terminal_proofs=(WbCoreTerminalProof(PR, MERGE, "production-verified"),),
    )
    production = WbCoreReleaseAdapter(
        FakeApi(production_pull, done_api.queue),
        fence_guard=lambda _boundary, _request: None,
    ).advance(production_request)
    assert production.status == "terminal"
    assert production.terminal_label == "release:production"
    assert production.hosted_deploy_identity == (
        f"hosted-release-v1:wb_core_eu_hosted_runtime_active:api.selleros.pro:{MERGE}"
    )


def _runtime_mapping_smoke() -> None:
    observed = WbCoreReleaseAdapter(
        FakeApi(_staged_pull(), _queue()),
        fence_guard=lambda _boundary, _request: None,
    ).observe(REQUEST)
    mapped = wb_core_runtime_result(observed, observed_at="2026-08-05T00:00:00Z")
    assert mapped == {
        "schema": "dev-control-plane/release-action-observation/v2",
        "status": "waiting_release",
        "reason_code": "exact_admission_not_submitted",
        "candidate_id": REQUEST.candidate_id,
        "task_id": REQUEST.task_id,
        "workstream_id": REQUEST.workstream_id,
        "task_revision": REQUEST.task_revision,
        "workstream_revision": REQUEST.workstream_revision,
        "expected_head_sha": HEAD,
        "observed_head_sha": HEAD,
        "retry_after_seconds": 30.0,
        "observed_at": "2026-08-05T00:00:00Z",
        "evidence": [],
        "admission_binding": None,
    }

    admitted_api = FakeApi(_staged_pull(), _queue())
    admitted = WbCoreReleaseAdapter(
        admitted_api,
        fence_guard=lambda _boundary, _request: None,
        max_polls=2,
    ).advance(REQUEST)
    admitted_mapping = wb_core_runtime_result(
        admitted, observed_at="2026-08-05T00:00:01Z"
    )
    assert admitted_mapping["status"] == "admitted"
    assert wb_core_admission_binding_from_mapping(
        admitted_mapping["admission_binding"]
    ) == WbCoreAdmissionBinding.from_proof(_admission())
    assert admitted_mapping["evidence"] == [
        "admission:sha256:" + _admission().digest()
    ]

    drift = WbCoreReleaseAdapter(
        FakeApi(replace(_staged_pull(), head_sha=DRIFT_HEAD), _queue()),
        fence_guard=lambda _boundary, _request: None,
    ).observe(REQUEST)
    drift_mapping = wb_core_runtime_result(
        drift, observed_at="2026-08-05T00:00:00Z"
    )
    assert drift_mapping["retry_after_seconds"] is None
    assert drift_mapping["observed_head_sha"] == DRIFT_HEAD
    assert drift_mapping["admission_binding"] is None

    failed = WbCoreReleaseAdapter(
        FakeApi(replace(_staged_pull(), is_draft=True), _queue()),
        fence_guard=lambda _boundary, _request: None,
    ).observe(REQUEST)
    try:
        wb_core_runtime_result(failed, observed_at="2026-08-05T00:00:00Z")
    except WbCoreReleaseAdapterError as exc:
        assert str(exc) == "pr_is_draft"
    else:
        raise AssertionError("causal target failure was masked as a polling observation")


def _lane_release_smoke() -> None:
    terminal_pull = replace(
        _staged_pull(),
        state="MERGED",
        labels=(
            "task:standard",
            "scope:repo-only",
            "release:done",
            "release:lane-owner",
        ),
        merge_sha=MERGE,
        admission_proofs=(_admission(),),
        terminal_proofs=(WbCoreTerminalProof(PR, MERGE, "repo-only"),),
    )
    owned = _queue(
        lane_status="owned",
        owner_pr=PR,
        task_id=TARGET_TASK,
        revision=LANE_REQUEST.task_revision,
        integrity="attention",
        signals=("terminal-release-lane-owner",),
    )
    api = FakeApi(terminal_pull, owned)
    authorizations: list[str] = []

    def exact_lane_fence(
        _boundary: str, request: WbCoreLaneReleaseRequest
    ) -> None:
        assert request == LANE_REQUEST

    adapter = WbCoreReleaseLaneAdapter(
        api,
        fence_guard=exact_lane_fence,
        authorization_guard=lambda request: authorizations.append(
            request.closure_event_id
        ),
        max_polls=2,
    )
    released = adapter.advance(LANE_REQUEST)
    assert released.status == "released"
    assert released.reason_code == "exact_lane_release_proven"
    assert len(api.lane_submissions) == 1 and len(authorizations) == 2
    assert api.lane_submissions[0][1] == LANE_REQUEST.release_command()
    assert wb_core_lane_release_request_from_mapping(asdict(LANE_REQUEST)) == LANE_REQUEST
    assert wb_core_lane_release_outcome_from_mapping(released.to_mapping()) == released

    # Exact target proof makes replay observational and prevents a duplicate
    # release command even after the foreign queue has advanced.
    repeated = adapter.advance(LANE_REQUEST)
    assert repeated.status == "released" and len(api.lane_submissions) == 1

    forged = replace(
        api.queue.release_proofs[0], evidence_digest="f" * 64
    )
    forged_api = FakeApi(
        terminal_pull,
        _queue(release_proofs=(forged,)),
    )
    forged_result = WbCoreReleaseLaneAdapter(
        forged_api,
        fence_guard=lambda _boundary, _request: None,
        authorization_guard=lambda _request: None,
    ).advance(LANE_REQUEST)
    assert forged_result.status == "stale"
    assert forged_result.reason_code == "lane_release_proof_binding_mismatch"
    assert not forged_api.lane_submissions

    stale_api = FakeApi(
        terminal_pull,
        _queue(
            lane_status="owned",
            owner_pr=PR,
            task_id=TARGET_TASK,
            revision=LANE_REQUEST.task_revision + 1,
            integrity="attention",
            signals=("terminal-release-lane-owner",),
        ),
    )
    stale = WbCoreReleaseLaneAdapter(
        stale_api,
        fence_guard=lambda _boundary, _request: None,
        authorization_guard=lambda _request: None,
    ).advance(LANE_REQUEST)
    assert stale.status == "stale"
    assert stale.reason_code == "lane_release_revision_is_stale"
    assert not stale_api.lane_submissions

    # Crash recovery sees the exact OWNER/MEMBER command digest and does not
    # publish a second issue comment while target Actions is still working.
    pending_api = FakeApi(
        replace(
            terminal_pull,
            submitted_command_digests=(LANE_REQUEST.release_command_digest(),),
        ),
        owned,
    )
    pending_api.release_after_submit = False
    pending = WbCoreReleaseLaneAdapter(
        pending_api,
        fence_guard=lambda _boundary, _request: None,
        authorization_guard=lambda _request: None,
    ).advance(LANE_REQUEST)
    assert pending.status == "release_submitted"
    assert not pending_api.lane_submissions

    denied_api = FakeApi(terminal_pull, owned)

    def deny(_request: WbCoreLaneReleaseRequest) -> None:
        raise WbCoreReleaseAdapterError("durable_task_closure_not_proven")

    try:
        WbCoreReleaseLaneAdapter(
            denied_api,
            fence_guard=lambda _boundary, _request: None,
            authorization_guard=deny,
        ).advance(LANE_REQUEST)
    except WbCoreReleaseAdapterError as exc:
        assert str(exc) == "durable_task_closure_not_proven"
    else:
        raise AssertionError("lane release crossed a missing task-closure authorization")
    assert not denied_api.lane_submissions


def _contour_adapter_smoke() -> None:
    executor = ExecutorIdentity(
        "executor-thread-wb",
        "desktop-host-wb",
        "gpt-5.6-sol",
        "ultra",
    )
    passport = TaskPassport(
        task_id=TASK,
        revision=3,
        title="Проверка внешнего wb-core release contour",
        objective="Независимо сверить exact target Release Train truth.",
        expected_result="Terminal PR и Actions proof совпадают с Passport.",
        contour="release:done",
        included_scope=("wb-core governed PR",),
        excluded_scope=("direct target mutation",),
        constraints=("read-only terminal verification",),
        acceptance=("trusted-main terminal proof",),
        closure=("owner acceptance remains explicit",),
        autonomy=AutonomyEnvelope(
            allowed_actions=(
                "github_readback",
                "wb_github_command",
                "target_lane_release",
            ),
            prohibited_actions=("self_merge",),
        ),
        workstream_ids=(REQUEST.workstream_id,),
        release_manifest=None,
        resources=(
            "target:orenvlad-ai/wb-core",
            "release-lane:wb-core",
            "repo:wb-core",
        ),
        modules=("module:release-train",),
        files=("apps/example.py",),
        dependencies=(),
        multi_pr_intent=False,
        multi_deploy_intent=False,
        curator=CuratorIdentity("curator-thread-wb", "desktop-host-wb"),
        executor=executor,
        created_at="2026-08-05T00:00:00Z",
    )
    pr_identity = (
        f"github-pr-v1:orenvlad-ai/wb-core:{PR}:{HEAD}:{MERGE}"
    )
    terminal = TerminalEvidence(
        terminal_id="terminal-wb-contour",
        event_id="event-wb-contour",
        task_id=passport.task_id,
        task_revision=passport.revision,
        workstream_id=REQUEST.workstream_id,
        workstream_revision=2,
        executor_generation=1,
        executor=executor,
        closure_kind=passport.contour,
        summary_ru="Исполнитель заявил closure; read-only адаптер проверит target proof.",
        evidence=("executor:terminal",),
        checks=("executor:checks-passed",),
        pr_identities=(pr_identity,),
        deploy_identities=(),
        owner_acceptance_required=True,
        created_at="2026-08-05T00:00:00Z",
    )
    request = wb_core_terminal_request_from_contracts(
        candidate_id="candidate-wb-contour",
        passport=passport,
        terminal=terminal,
        pr_identity=pr_identity,
    )
    assert request.expected_merge_sha == MERGE
    assert request.passport_digest == contract_digest(passport)
    admission = WbCoreAdmissionProof(
        pr_number=PR,
        owner_pr=PR,
        head_sha=HEAD,
        target_task_id=derive_wb_core_target_task_id(passport.task_id),
        task_revision=passport.revision,
        passport_digest=contract_digest(passport),
    )
    pull = replace(
        _staged_pull(),
        state="MERGED",
        labels=("task:standard", "scope:repo-only", "release:done"),
        merge_sha=MERGE,
        admission_proofs=(admission,),
        terminal_proofs=(WbCoreTerminalProof(PR, MERGE, "repo-only"),),
    )
    release_adapter = WbCoreReleaseAdapter(
        FakeApi(
            pull,
            _queue(
                lane_status="owned",
                owner_pr=PR,
                task_id=TARGET_TASK,
                revision=passport.revision,
            ),
        ),
        fence_guard=lambda _boundary, _request: None,
    )
    proof = WbCoreContourAdapter(
        release_adapter,
        clock=lambda: 1_754_352_000.0,
    )(passport, terminal)
    assert proof.target == "orenvlad-ai/wb-core"
    assert proof.passed is True
    assert "wb_core_actions_terminal_proof_matched" in proof.checks

    production_passport = replace(passport, contour="release:production")
    deploy_identity = (
        "hosted-release-v1:wb_core_eu_hosted_runtime_active:"
        f"api.selleros.pro:{MERGE}"
    )
    production_terminal = replace(
        terminal,
        closure_kind="release:production",
        deploy_identities=(deploy_identity,),
    )
    production_admission = replace(
        admission,
        passport_digest=contract_digest(production_passport),
    )
    production_pull = replace(
        pull,
        labels=("task:standard", "scope:live-runtime", "release:production"),
        admission_proofs=(production_admission,),
        terminal_proofs=(
            WbCoreTerminalProof(PR, MERGE, "production-verified"),
        ),
    )
    production_proof = WbCoreContourAdapter(
        WbCoreReleaseAdapter(
            FakeApi(
                production_pull,
                _queue(
                    lane_status="owned",
                    owner_pr=PR,
                    task_id=TARGET_TASK,
                    revision=production_passport.revision,
                ),
            ),
            fence_guard=lambda _boundary, _request: None,
        ),
        clock=lambda: 1_754_352_000.0,
    )(production_passport, production_terminal)
    assert "wb_core_hosted_release_identity_matched" in production_proof.checks

    forged_terminal = replace(
        production_terminal,
        deploy_identities=(
            f"hosted-release-v1:wrong-target:api.selleros.pro:{MERGE}",
        ),
    )
    try:
        WbCoreContourAdapter(
            WbCoreReleaseAdapter(
                FakeApi(production_pull, _queue()),
                fence_guard=lambda _boundary, _request: None,
            )
        )(production_passport, forged_terminal)
    except RuntimeError:
        pass
    else:
        raise AssertionError("forged wb-core hosted identity passed contour verification")


def _head_drift_smoke() -> None:
    api = FakeApi(replace(_staged_pull(), head_sha=DRIFT_HEAD), _queue())
    result = WbCoreReleaseAdapter(
        api,
        fence_guard=lambda _boundary, _request: None,
    ).advance(REQUEST)
    assert result.status == "readmission_required"
    assert result.reason_code == "pr_head_changed"
    assert result.observed_head_sha == DRIFT_HEAD and not api.submissions


def _mismatch_and_failure_smoke() -> None:
    mismatched = replace(_admission(), task_revision=4)
    api = FakeApi(
        replace(
            _staged_pull(),
            labels=("task:standard", "scope:repo-only", "release:ready"),
            admission_proofs=(mismatched,),
        ),
        _queue(
            lane_status="owned", owner_pr=PR, task_id=TARGET_TASK, revision=3, queue_status="ready"
        ),
    )
    result = WbCoreReleaseAdapter(
        api,
        fence_guard=lambda _boundary, _request: None,
    ).advance(REQUEST)
    assert result.status == "failed" and result.reason_code == "admission_binding_mismatch"

    missing_proof_pull = replace(
        _staged_pull(),
        state="MERGED",
        labels=("task:standard", "scope:repo-only", "release:done"),
        merge_sha=MERGE,
        admission_proofs=(_admission(),),
    )
    missing = WbCoreReleaseAdapter(
        FakeApi(missing_proof_pull, _queue()),
        fence_guard=lambda _boundary, _request: None,
    ).advance(REQUEST)
    assert missing.status == "failed" and missing.reason_code == "terminal_proof_missing"

    disabled_api = FakeApi(_staged_pull(), _queue())
    disabled_api.required = False
    disabled = WbCoreReleaseAdapter(
        disabled_api,
        fence_guard=lambda _boundary, _request: None,
    ).advance(REQUEST)
    assert disabled.status == "failed"
    assert disabled.reason_code == "orchestration_enforcement_disabled"


def _fence_smoke() -> None:
    api = FakeApi(_staged_pull(), _queue())

    def fence(boundary: str, _request: WbCoreReleaseRequest) -> None:
        if boundary == "before_admission_command":
            raise WbCoreReleaseAdapterError("stale_supervisor_generation")

    try:
        WbCoreReleaseAdapter(api, fence_guard=fence).advance(REQUEST)
    except WbCoreReleaseAdapterError as exc:
        assert str(exc) == "stale_supervisor_generation"
    else:
        raise AssertionError("stale generation crossed target admission boundary")
    assert not api.submissions


def _queue_parser_smoke() -> None:
    snapshot = {
        "status": "ok",
        "queue": {"status": "idle"},
        "release_lane": {"status": "idle"},
        "integrity": {"status": "ok", "signals": []},
        "release_lane_proofs": [],
        "counts": {},
        "active": [],
    }
    parsed = WbCoreQueueReadback.from_target_snapshot(snapshot)
    assert parsed.queue_status == "idle" and parsed.lane_status == "idle"

    snapshot["release_lane_proofs"] = [
        {
            "owner_pr": PR,
            "task_id": TARGET_TASK,
            "revision": LANE_REQUEST.task_revision,
            "outcome": LANE_REQUEST.outcome,
            "evidence_digest": "sha256:" + LANE_REQUEST.evidence_digest,
        }
    ]
    proved = WbCoreQueueReadback.from_target_snapshot(
        snapshot,
        expected_release_proof_prs=(PR,),
    )
    assert proved.release_proofs[0].binding() == (
        PR,
        TARGET_TASK,
        LANE_REQUEST.task_revision,
        LANE_REQUEST.outcome,
        LANE_REQUEST.evidence_digest,
    )
    try:
        WbCoreQueueReadback.from_target_snapshot(snapshot)
    except WbCoreReleaseAdapterError as exc:
        assert str(exc) == "target_queue_readback_invalid"
    else:
        raise AssertionError("unrequested lane-release proof crossed queue boundary")


def _github_parser_smoke() -> None:
    admission_marker = (
        f"<!-- {WB_CORE_ADMISSION_MARKER} head={HEAD} owner_pr={PR} "
        f"passport=sha256:{PASSPORT} pr={PR} revision=3 task={TARGET_TASK} -->"
    )
    terminal_marker = (
        f"<!-- {WB_CORE_COMPLETION_MARKER} contour=repo-only merge={MERGE} pr={PR} -->"
    )
    provider = {
        "number": PR,
        "state": "MERGED",
        "isDraft": False,
        "headRefOid": HEAD,
        "baseRefName": "main",
        "labels": [
            {"name": "task:standard"},
            {"name": "scope:repo-only"},
            {"name": "release:done"},
        ],
        "mergeCommit": {"oid": MERGE},
        "url": f"https://github.com/orenvlad-ai/wb-core/pull/{PR}",
    }
    comments = [[
        {
            "id": 1,
            "body": admission_marker + "\n" + terminal_marker,
            "user": {"login": "github-actions[bot]"},
            "author_association": "NONE",
        },
        {
            "id": 2,
            "body": REQUEST.admission_command(),
            "user": {"login": "orenvlad-ai"},
            "author_association": "OWNER",
        },
        # A non-bot proof marker and an unauthorized command are ignored.
        {
            "id": 3,
            "body": admission_marker + "\n" + REQUEST.admission_command(),
            "user": {"login": "attacker"},
            "author_association": "NONE",
        },
        {
            "id": 4,
            "body": LANE_REQUEST.release_command(),
            "user": {"login": "orenvlad-ai"},
            "author_association": "OWNER",
        },
    ]]
    readback = pull_readback_from_github(provider, comments)
    assert readback.admission_proofs == (_admission(),)
    assert len(readback.terminal_proofs) == 1
    assert readback.submitted_command_digests == (
        REQUEST.admission_command_digest(),
        LANE_REQUEST.release_command_digest(),
    )


def _production_resolver_smoke() -> None:
    for protected_path in (
        "src/dev_control_plane/codex_app_server.py",
        "src/dev_control_plane/wb_core_release_adapter.py",
        "src/dev_control_plane/__init__.py",
        "src/dev_control_plane/target_projects.py",
        "src/dev_control_plane/ssh_deploy.py",
        "src/sqlite3.py",
        "src/http/__init__.py",
        "json.py",
        "http/__init__.py",
        "native_override.so",
        "pyproject.toml",
        "apps/sitecustomize.py",
        "apps/new_controller_bootstrap.py",
        "bootstrap-hooks.pth",
    ):
        assert supervisor_app._is_protected_self_governance_path(protected_path)
    assert not supervisor_app._is_protected_self_governance_path(
        "apps/dev_control_plane_example_smoke.py"
    )

    wb_passport = _runtime_passport(
        target=supervisor_app.WB_CORE_REPOSITORY,
        contour="release:done",
        task_id=TASK,
        workstream_id=REQUEST.workstream_id,
        revision=3,
        files=("apps/example.py",),
    )
    wb_registry = FakeRegistry(wb_passport, workstream_revision=2)
    wb_truth = _github_truth(
        target=supervisor_app.WB_CORE_REPOSITORY,
        pr_number=PR,
        files=tuple(wb_passport.files),
        checks={"baseline": "SUCCESS"},
    )
    wb = supervisor_app._ReleaseCandidateResolver(
        registry=wb_registry,
        gh_binary="/usr/bin/true",
        github=FakeGitHub(wb_truth),
        json_reader=_resolver_reader(
            supervisor_app.WB_CORE_REPOSITORY,
            wb_truth,
            labels=("task:standard", "scope:repo-only", "release:staged"),
        ),
    )(
        {"candidate": _resolver_candidate(wb_passport, HEAD, workstream_revision=2)},
        FakeGuard(),
    )
    assert wb["target_adapter"] == supervisor_app.WB_CORE_TARGET_ADAPTER
    assert tuple(wb["release_candidate"]["required_checks"]) == ("baseline",)
    assert wb["scheduler_truth"]["admission_ready"] is True
    assert wb["scheduler_truth"]["target_id"] == supervisor_app.WB_CORE_REPOSITORY

    self_passport = _runtime_passport(
        target=supervisor_app.SELF_REPO,
        contour="release:done",
        task_id="task:self-release:0001",
        workstream_id="workstream-self-release-1",
        revision=3,
        files=("docs/safe-change.md",),
    )
    self_registry = FakeRegistry(self_passport, workstream_revision=2)
    merged_truth = _github_truth(
        target=supervisor_app.SELF_REPO,
        pr_number=41,
        files=tuple(self_passport.files),
        checks={"v2-suite": "SUCCESS", "self-closure": "SUCCESS"},
        state="MERGED",
    )
    merged = supervisor_app._ReleaseCandidateResolver(
        registry=self_registry,
        gh_binary="/usr/bin/true",
        github=FakeGitHub(merged_truth),
        json_reader=_resolver_reader(supervisor_app.SELF_REPO, merged_truth),
    )(
        {"candidate": _resolver_candidate(self_passport, HEAD, workstream_revision=2)},
        FakeGuard(),
    )
    assert merged["scheduler_truth"]["pr_state"] == "MERGED"
    assert merged["scheduler_truth"]["merge_commit_sha"] == MERGE
    assert tuple(merged["release_candidate"]["required_checks"]) == (
        "v2-suite",
        "self-closure",
    )

    weak_truth = replace(
        merged_truth,
        state="OPEN",
        merge_commit_sha=None,
        checks={"v2-suite": "SUCCESS"},
    )
    weak = supervisor_app._ReleaseCandidateResolver(
        registry=self_registry,
        gh_binary="/usr/bin/true",
        github=FakeGitHub(weak_truth),
        json_reader=_resolver_reader(supervisor_app.SELF_REPO, weak_truth),
    )(
        {"candidate": _resolver_candidate(self_passport, HEAD, workstream_revision=2)},
        FakeGuard(),
    )
    assert weak["scheduler_truth"]["checks_green"] is False
    assert weak["scheduler_truth"]["admission_ready"] is False

    protected_truth = replace(
        weak_truth,
        files=(".github/workflows/forged-green.yml",),
        checks={"v2-suite": "SUCCESS", "self-closure": "SUCCESS"},
    )
    protected_passport = replace(
        self_passport,
        files=(".github/workflows/forged-green.yml",),
    )
    protected_registry = FakeRegistry(protected_passport, workstream_revision=2)
    try:
        supervisor_app._ReleaseCandidateResolver(
            registry=protected_registry,
            gh_binary="/usr/bin/true",
            github=FakeGitHub(protected_truth),
            json_reader=_resolver_reader(supervisor_app.SELF_REPO, protected_truth),
        )(
            {
                "candidate": _resolver_candidate(
                    protected_passport,
                    HEAD,
                    workstream_revision=2,
                )
            },
            FakeGuard(),
        )
    except supervisor_app.SecurityPermissionChangeRequiresOwner as exc:
        assert exc.expected_head_sha == HEAD
        assert "protected-path:.github/workflows/forged-green.yml" in exc.evidence
    else:
        raise AssertionError("forged green governance diff crossed self admission")

    protected_merged_truth = replace(
        protected_truth,
        state="MERGED",
        mergeable="UNKNOWN",
        merge_state="UNKNOWN",
        merge_commit_sha=MERGE,
    )
    protected_proof = supervisor_app._ReleaseCandidateResolver(
        registry=protected_registry,
        gh_binary="/usr/bin/true",
        github=FakeGitHub(protected_merged_truth),
        json_reader=_resolver_reader(
            supervisor_app.SELF_REPO,
            protected_merged_truth,
            discovery_state="OPEN",
        ),
    )(
        {
            "candidate": _resolver_candidate(
                protected_passport,
                HEAD,
                workstream_revision=2,
            )
        },
        FakeGuard(),
    )
    assert protected_proof["scheduler_truth"]["pr_state"] == "MERGED"
    assert protected_proof["scheduler_truth"]["admission_ready"] is False

    # A stale discovery that claimed MERGED may never fall back to an OPEN
    # mutation path on the subsequent complete PR readback.
    try:
        supervisor_app._ReleaseCandidateResolver(
            registry=self_registry,
            gh_binary="/usr/bin/true",
            github=FakeGitHub(weak_truth),
            json_reader=_resolver_reader(
                supervisor_app.SELF_REPO,
                weak_truth,
                discovery_state="MERGED",
            ),
        )(
            {"candidate": _resolver_candidate(self_passport, HEAD, workstream_revision=2)},
            FakeGuard(),
        )
    except RuntimeError as exc:
        assert "immutable scheduler snapshot" in str(exc)
    else:
        raise AssertionError("stale MERGED discovery reopened a mutation path")

    no_auto = replace(
        self_passport,
        constraints=("NO_AUTO_MERGE",),
    )
    no_auto_result = supervisor_app._ReleaseCandidateResolver(
        registry=FakeRegistry(no_auto, workstream_revision=2),
        gh_binary="/usr/bin/true",
        github=FakeGitHub(weak_truth),
        json_reader=_resolver_reader(supervisor_app.SELF_REPO, weak_truth),
    )(
        {"candidate": _resolver_candidate(no_auto, HEAD, workstream_revision=2)},
        FakeGuard(),
    )
    assert no_auto_result["scheduler_truth"]["unknown_classification"] is True
    assert no_auto_result["scheduler_truth"]["admission_ready"] is False

    drift_registry = FakeRegistry(self_passport, workstream_revision=2)

    def drift(_read: int) -> None:
        drift_registry.replace_passport(
            replace(self_passport, constraints=("changed during readback",))
        )

    try:
        supervisor_app._ReleaseCandidateResolver(
            registry=drift_registry,
            gh_binary="/usr/bin/true",
            github=FakeGitHub(weak_truth, on_read=drift),
            json_reader=_resolver_reader(supervisor_app.SELF_REPO, weak_truth),
        )(
            {"candidate": _resolver_candidate(self_passport, HEAD, workstream_revision=2)},
            FakeGuard(),
        )
    except RuntimeError as exc:
        assert str(exc) == "Task Passport changed during GitHub release readback"
    else:
        raise AssertionError("mutable Passport crossed exact GitHub readback")


def _self_contour_executor_smoke() -> None:
    passport = _runtime_passport(
        target=supervisor_app.SELF_REPO,
        contour="release:done",
        task_id="task:self-executor:0001",
        workstream_id="workstream-self-executor-1",
        revision=3,
        files=("docs/safe-change.md",),
    )
    registry = FakeRegistry(passport, workstream_revision=2)
    github = FakeGitHub(
        _github_truth(
            target=supervisor_app.SELF_REPO,
            pr_number=42,
            files=tuple(passport.files),
            checks={"v2-suite": "SUCCESS", "self-closure": "SUCCESS"},
        )
    )
    with tempfile.TemporaryDirectory() as temporary:
        executor = supervisor_app._SelfHostedReleaseExecutor(
            registry=registry,
            workspace_root=Path(temporary),
            projection_key_file=Path(temporary) / "unused.key",
            github=github,
        )

        def hosted_forbidden(*_args: Any, **_kwargs: Any) -> Any:
            raise AssertionError("release:done invoked a hosted deploy callback")

        executor._deploy = hosted_forbidden
        executor._deploy_readback = hosted_forbidden
        executor._verify = hosted_forbidden
        guard = FakeGuard()
        receipt = executor(
            _self_action_payload(passport, pr_number=42, workstream_revision=2),
            guard,
        )
    assert github.merges == 1 and guard.checks >= 2
    assert receipt["contour"] == "release:done"
    assert receipt["deploy_identity"] is None
    assert receipt["admission_binding"] is None
    assert receipt["verification_identity"] == f"github-merged-readback:{MERGE}"

    production = _runtime_passport(
        target=supervisor_app.SELF_REPO,
        contour="release:production",
        task_id="task:self-production:0001",
        workstream_id="workstream-self-production-1",
        revision=4,
        files=("docs/safe-production-change.md",),
    )
    production_github = FakeGitHub(
        _github_truth(
            target=supervisor_app.SELF_REPO,
            pr_number=43,
            files=tuple(production.files),
            checks={"v2-suite": "SUCCESS", "self-closure": "SUCCESS"},
        )
    )
    deploy_calls: list[str] = []
    with tempfile.TemporaryDirectory() as temporary:
        production_executor = supervisor_app._SelfHostedReleaseExecutor(
            registry=FakeRegistry(production, workstream_revision=3),
            workspace_root=Path(temporary),
            projection_key_file=Path(temporary) / "unused.key",
            github=production_github,
        )
        production_executor._deploy_readback = lambda _candidate, _sha: None

        def deploy(_candidate: Any, merge_sha: str) -> str:
            deploy_calls.append(merge_sha)
            return (
                "hosted-release-v1:wb-core-eu-root:devcontrol.pro:"
                + merge_sha
            )

        production_executor._deploy = deploy
        production_executor._verify = lambda _candidate, identity: {
            "status": "passed",
            "identity": "hosted-readonly-probes:" + identity.rsplit(":", 1)[-1],
        }
        production_receipt = production_executor(
            _self_action_payload(production, pr_number=43, workstream_revision=3),
            FakeGuard(),
        )
    assert deploy_calls == [MERGE]
    assert production_receipt["contour"] == "release:production"
    assert production_receipt["deploy_identity"] == (
        f"hosted-release-v1:wb-core-eu-root:devcontrol.pro:{MERGE}"
    )

    protected_production = replace(
        production,
        files=("src/dev_control_plane/codex_app_server.py",),
    )
    protected_production_github = FakeGitHub(
        _github_truth(
            target=supervisor_app.SELF_REPO,
            pr_number=46,
            files=tuple(protected_production.files),
            checks={"v2-suite": "SUCCESS", "self-closure": "SUCCESS"},
            state="MERGED",
        )
    )
    protected_deploy_calls: list[str] = []
    with tempfile.TemporaryDirectory() as temporary:
        protected_production_executor = supervisor_app._SelfHostedReleaseExecutor(
            registry=FakeRegistry(protected_production, workstream_revision=3),
            workspace_root=Path(temporary),
            projection_key_file=Path(temporary) / "unused.key",
            github=protected_production_github,
        )
        protected_production_executor._deploy_readback = lambda _candidate, _sha: None
        protected_production_executor._deploy = (
            lambda _candidate, sha: protected_deploy_calls.append(sha) or "forbidden"
        )
        protected_production_executor._verify = lambda *_args: {
            "status": "passed"
        }
        try:
            protected_production_executor(
                _self_action_payload(
                    protected_production,
                    pr_number=46,
                    workstream_revision=3,
                ),
                FakeGuard(),
            )
        except supervisor_app.SecurityPermissionChangeRequiresOwner:
            pass
        else:
            raise AssertionError("protected merged controller source crossed deploy gate")
    assert not protected_deploy_calls

    protected = replace(passport, files=("src/dev_control_plane/supervisor.py",))
    protected_github = FakeGitHub(
        _github_truth(
            target=supervisor_app.SELF_REPO,
            pr_number=44,
            files=tuple(protected.files),
            checks={"v2-suite": "SUCCESS", "self-closure": "SUCCESS"},
        )
    )
    with tempfile.TemporaryDirectory() as temporary:
        protected_executor = supervisor_app._SelfHostedReleaseExecutor(
            registry=FakeRegistry(protected, workstream_revision=2),
            workspace_root=Path(temporary),
            projection_key_file=Path(temporary) / "unused.key",
            github=protected_github,
        )
        try:
            protected_executor(
                _self_action_payload(protected, pr_number=44, workstream_revision=2),
                FakeGuard(),
            )
        except supervisor_app.SecurityPermissionChangeRequiresOwner:
            pass
        else:
            raise AssertionError("protected controller diff crossed immediate merge gate")
    assert protected_github.merges == 0

    denied_registry = FakeRegistry(production, workstream_revision=3)
    denied_registry.task.passport["autonomy"] = {
        "allowed_actions": ["github_readback", "self_merge", "target_lane_release"],
        "prohibited_actions": [
            "self_hosted_deploy",
            "wb_github_command",
            "target_release_command",
        ],
        "human_gate_reasons": [],
    }
    with tempfile.TemporaryDirectory() as temporary:
        denied = supervisor_app._SelfHostedReleaseExecutor(
            registry=denied_registry,
            workspace_root=Path(temporary),
            projection_key_file=Path(temporary) / "unused.key",
            github=FakeGitHub(
                _github_truth(
                    target=supervisor_app.SELF_REPO,
                    pr_number=45,
                    files=tuple(production.files),
                    checks={"v2-suite": "SUCCESS", "self-closure": "SUCCESS"},
                )
            ),
        )
        try:
            denied(
                _self_action_payload(
                    production,
                    pr_number=45,
                    workstream_revision=3,
                ),
                FakeGuard(),
            )
        except ValueError as exc:
            assert "self_hosted_deploy" in str(exc)
        else:
            raise AssertionError("prohibited hosted deploy crossed Passport autonomy")


def _composite_executor_smoke() -> None:
    calls: list[str] = []
    composite = supervisor_app._CompositeReleaseExecutor(
        self_executor=lambda _payload, _guard: calls.append("self") or {"target": "self"},
        wb_core_executor=lambda _payload, _guard: calls.append("wb") or {"target": "wb"},
    )
    assert composite(
        {"target_adapter": supervisor_app.SELF_HOSTED_ADAPTER}, FakeGuard()
    ) == {"target": "self"}
    assert composite(
        {"target_adapter": supervisor_app.WB_CORE_TARGET_ADAPTER}, FakeGuard()
    ) == {"target": "wb"}
    assert calls == ["self", "wb"]
    try:
        composite({"target_adapter": "unknown"}, FakeGuard())
    except RuntimeError:
        pass
    else:
        raise AssertionError("unknown target adapter crossed composite dispatch")


def _managed_queue_reader_smoke() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        source = Path(temporary).resolve()
        apps = source / "apps"
        apps.mkdir()
        runner = apps / "github_release_train.py"
        runner.write_text("# trusted-main fixture\n", encoding="utf-8")
        calls: list[tuple[list[str], Mapping[str, str], int]] = []

        def run(
            command: list[str],
            *,
            cwd: Path,
            timeout: float,
            env: Mapping[str, str],
            max_output_bytes: int,
        ) -> str:
            assert cwd == source and timeout == 180
            calls.append((command, env, max_output_bytes))
            return '{"status":"ok","queue":{"status":"idle"}}'

        reader = supervisor_app._WbCoreManagedQueueReader(
            workspace_root=source / "managed",
            gh_binary="/usr/bin/true",
            source_provider=lambda: source,
            command_runner=run,
        )
        assert reader((PR, PR, PR + 1))["status"] == "ok"
        command, environment, bound = calls[0]
        assert command == [
            sys.executable,
            str(runner),
            "queue-status",
            "--release-proof-pr",
            str(PR),
            "--release-proof-pr",
            str(PR + 1),
        ]
        assert bound == supervisor_app._WB_CORE_QUEUE_MAX_BYTES
        assert environment["GITHUB_REPOSITORY"] == "orenvlad-ai/wb-core"
        assert "GITHUB_TOKEN" not in environment and "GH_TOKEN" not in environment

        oversized = supervisor_app._WbCoreManagedQueueReader(
            workspace_root=source / "managed-oversized",
            gh_binary="/usr/bin/true",
            source_provider=lambda: source,
            command_runner=lambda *_args, **_kwargs: "x"
            * (supervisor_app._WB_CORE_QUEUE_MAX_BYTES + 1),
        )
        try:
            oversized(())
        except RuntimeError as exc:
            assert "oversized" in str(exc)
        else:
            raise AssertionError("oversized target queue output crossed boundary")


def _target_lane_composition_smoke() -> None:
    self_action = _closure_action(
        target=supervisor_app.SELF_REPO,
        task_id="task:lane-self:0001",
        workstream_id="workstream-lane-self-1",
        task_revision=2,
        workstream_revision=2,
        pr_identity=(
            f"github-pr-v1:{supervisor_app.SELF_REPO}:41:{HEAD}:{MERGE}"
        ),
    )
    executor = supervisor_app._TargetLaneClosureExecutor(
        registry=SimpleNamespace(),
        fence=SimpleNamespace(generation=7),
        wb_core_api=SimpleNamespace(),
    )
    executor._authorize = lambda _action, guard: guard.checkpoint()
    guard = FakeGuard()
    receipt = executor(self_action, guard)
    assert receipt["status"] == "released" and guard.checks == 2

    terminal_pull = replace(
        _staged_pull(),
        state="MERGED",
        labels=("task:standard", "scope:repo-only", "release:done"),
        merge_sha=MERGE,
        admission_proofs=(_admission(),),
        terminal_proofs=(WbCoreTerminalProof(PR, MERGE, "repo-only"),),
    )
    wb_api = FakeApi(
        terminal_pull,
        _queue(
            lane_status="owned",
            owner_pr=PR,
            task_id=TARGET_TASK,
            revision=LANE_REQUEST.task_revision,
            integrity="attention",
            signals=("terminal-release-lane-owner",),
        ),
    )
    wb_executor = supervisor_app._TargetLaneClosureExecutor(
        registry=SimpleNamespace(),
        fence=SimpleNamespace(generation=7),
        wb_core_api=wb_api,
    )
    wb_executor._authorize = lambda _action, guard: guard.checkpoint()
    wb_receipt = wb_executor(
        _closure_action(
            target=supervisor_app.WB_CORE_REPOSITORY,
            task_id=TASK,
            workstream_id=REQUEST.workstream_id,
            task_revision=LANE_REQUEST.task_revision,
            workstream_revision=2,
            pr_identity=(
                f"github-pr-v1:{supervisor_app.WB_CORE_REPOSITORY}:"
                f"{PR}:{HEAD}:{MERGE}"
            ),
            closure_event_id=LANE_REQUEST.closure_event_id,
            closure_event_digest=LANE_REQUEST.evidence_digest,
        ),
        FakeGuard(),
    )
    assert wb_receipt["status"] == "released"
    assert len(wb_api.lane_submissions) == 1


def _incident_application_disposition_smoke() -> None:
    binding = RevisionBinding(
        task_id=TASK,
        task_revision=REQUEST.task_revision,
        workstream_id=REQUEST.workstream_id,
        workstream_revision=REQUEST.workstream_revision,
        pr_head_sha=HEAD,
        resources=("resource:release-smoke",),
    )

    def decision(action: str) -> ArbiterDecision:
        return ArbiterDecision(
            decision_id=f"incident-disposition-{action}",
            kind="incident",
            case_id="incident-case-disposition",
            case_digest="8" * 64,
            bindings=(binding,),
            steps=(
                DecisionStep(
                    step_id=f"incident-step-{action}",
                    action=action,
                    task_id=binding.task_id,
                    workstream_id=binding.workstream_id,
                ),
            ),
            model="gpt-5.6-sol",
            reasoning="ultra",
            created_at="2026-08-05T00:00:00Z",
        )

    for action in ("wait", "verify", "park_workstream"):
        guard = FakeGuard()
        result = supervisor_app._apply_incident_decision(
            {"decision": contract_to_dict(decision(action))}, guard
        )
        assert result == {
            "schema": supervisor_app.INCIDENT_APPLICATION_DISPOSITION_SCHEMA,
            "applied": True,
            "disposition": "park",
            "verification_identity": (
                f"deterministic-incident-disposition:incident-disposition-{action}:park"
            ),
        }
        assert "verification_passed" not in result and guard.checks == 2

    release = supervisor_app._apply_incident_decision(
        {
            "decision": contract_to_dict(decision("verify")),
            "remediation": {
                "schema": "dev-control-plane/release-incident-remediation/v2",
                "kind": "release_action",
            },
        },
        FakeGuard(),
    )
    assert release["disposition"] == "dispatch_release_once"
    lane = supervisor_app._apply_incident_decision(
        {
            "decision": contract_to_dict(decision("verify")),
            "remediation": {
                "schema": "dev-control-plane/target-lane-incident-remediation/v2",
                "kind": "target_lane_closure",
            },
        },
        FakeGuard(),
    )
    assert lane["disposition"] == "dispatch_target_lane_once"
    waited = supervisor_app._apply_incident_decision(
        {
            "decision": contract_to_dict(decision("wait")),
            "remediation": {
                "schema": "dev-control-plane/release-incident-remediation/v2",
                "kind": "release_action",
            },
        },
        FakeGuard(),
    )
    assert waited["disposition"] == "park"


def _parked_admission_lane_composition_smoke() -> None:
    admitted_passport = _runtime_passport(
        target=supervisor_app.WB_CORE_REPOSITORY,
        contour="release:done",
        task_id=TASK,
        workstream_id=REQUEST.workstream_id,
        revision=1,
        files=("apps/parked_lane.py",),
    )
    passport = replace(admitted_passport, revision=2)
    assert passport.release_manifest is None
    historical_request = replace(
        REQUEST,
        task_revision=1,
        workstream_revision=1,
        passport_digest=contract_digest(admitted_passport),
    )
    api = BindingChainApi(historical_request)
    admitted = WbCoreReleaseAdapter(
        api,
        fence_guard=lambda _boundary, _request: None,
        max_polls=2,
    ).advance(historical_request)
    assert admitted.status == "admitted" and admitted.admission_binding is not None
    observation = wb_core_runtime_result(
        admitted,
        observed_at="2026-08-05T00:00:01Z",
    )
    binding = admitted.admission_binding
    assert wb_core_admission_binding_from_mapping(
        observation["admission_binding"]
    ) == binding

    candidate = {
        **_resolver_candidate(
            admitted_passport,
            HEAD,
            workstream_revision=historical_request.workstream_revision,
        ),
        "candidate_id": historical_request.candidate_id,
    }
    release_action_event_id = "release-action-parked-admission-smoke"
    observation_event_id = "release-observation-parked-admission-smoke"
    observation_event = {
        "event_id": observation_event_id,
        "event_type": "release_action_observed",
        "task_id": passport.task_id,
        "workstream_id": passport.workstream_ids[0],
        "payload": {
            "schema": "dev-control-plane/release-action-observed-event/v2",
            "release_action_event_id": release_action_event_id,
            "target_adapter": supervisor_app.WB_CORE_TARGET_ADAPTER,
            "observation": observation,
        },
    }
    observation_digest = supervisor_app._sha256_mapping(
        {
            "event_id": observation_event["event_id"],
            "event_type": observation_event["event_type"],
            "payload": observation_event["payload"],
        }
    )
    parked_event = {
        "event_id": "incident-parked-admission-smoke",
        "event_type": "incident_policy",
        "task_id": passport.task_id,
        "workstream_id": passport.workstream_ids[0],
        "payload": {
            "schema": "dev-control-plane/incident-state-event/v2",
            "status": "parked",
        },
    }
    parked_digest = supervisor_app._sha256_mapping(
        {
            "event_id": parked_event["event_id"],
            "event_type": parked_event["event_type"],
            "payload": parked_event["payload"],
        }
    )
    release_action = {
        "event_id": release_action_event_id,
        "kind": "release_action",
        "payload": {
            "target_adapter": supervisor_app.WB_CORE_TARGET_ADAPTER,
            "candidate": candidate,
            "release_candidate": {
                "lane_id": candidate["logical_lane_id"],
                "task_id": passport.task_id,
                "workstream_id": passport.workstream_ids[0],
                "revision": admitted_passport.revision,
                "repo": supervisor_app.WB_CORE_REPOSITORY,
                "pr_number": REQUEST.pr_number,
                "expected_head_sha": HEAD,
                "base_ref": "main",
                "required_checks": ["baseline"],
                "declared_files": list(passport.files),
                "resources": ["resource:release-smoke"],
                "multi_pr": False,
            },
        },
    }
    registry = FakeRegistry(
        passport,
        workstream_revision=2,
        task_state="parked",
        workstream_state="parked",
        events=(observation_event, parked_event),
        outbox_records=(release_action,),
    )
    partial = {
        "schema": "dev-control-plane/target-lane-closure/v2",
        "binding_kind": "parked_admission",
        "closure_id": "closure-parked-admission-smoke",
        "supervisor_generation": 7,
        "task_id": passport.task_id,
        "task_revision": passport.revision,
        "workstream_id": passport.workstream_ids[0],
        "workstream_revision": 2,
        "target_id": supervisor_app.WB_CORE_REPOSITORY,
        "logical_lane_id": candidate["logical_lane_id"],
        "contour": passport.contour,
        "outcome": "parked",
        "parked_admission": {
            "schema": supervisor_app.PARKED_TARGET_LANE_ADMISSION_SCHEMA,
            "target_adapter": supervisor_app.WB_CORE_TARGET_ADAPTER,
            "candidate_id": candidate["candidate_id"],
            "pr_number": REQUEST.pr_number,
            "expected_head_sha": HEAD,
            "admission_task_revision": admitted_passport.revision,
            "admission_workstream_revision": historical_request.workstream_revision,
            "release_action_event_id": release_action_event_id,
            "observation_event_id": observation_event_id,
            "observation_event_digest": observation_digest,
            "admission_binding": asdict(binding),
        },
        "closure_event_id": parked_event["event_id"],
        "closure_event_type": parked_event["event_type"],
        "closure_event_digest": parked_digest,
    }
    fence = SimpleNamespace(generation=7, owner_id=registry.owner_id)
    executor = supervisor_app._TargetLaneClosureExecutor(
        registry=registry,
        fence=fence,
        wb_core_api=api,
    )
    receipt = executor(partial, FakeGuard())
    assert receipt["status"] == "parked" and api.lane_submissions == 1
    assert executor._anchor_pr(partial) == binding.owner_pr

    for invalid in (
        {**partial, "target_id": supervisor_app.SELF_REPO},
        {**partial, "outcome": "completed"},
        {
            **partial,
            "parked_admission": {
                **partial["parked_admission"],
                "expected_head_sha": DRIFT_HEAD,
            },
        },
    ):
        try:
            executor._authorize(invalid, FakeGuard())
        except RuntimeError:
            pass
        else:
            raise AssertionError("invalid parked admission crossed the lane boundary")


def _admission_binding_chain_e2e_smoke() -> None:
    r1 = _runtime_passport(
        target=supervisor_app.WB_CORE_REPOSITORY,
        contour="release:done",
        task_id="task:wb-binding:0001",
        workstream_id="workstream-wb-binding-1",
        revision=1,
        files=("apps/example.py",),
    )
    request = WbCoreReleaseRequest(
        candidate_id="candidate-wb-binding-1",
        task_id=r1.task_id,
        target_task_id=derive_wb_core_target_task_id(r1.task_id),
        workstream_id=r1.workstream_ids[0],
        task_revision=1,
        workstream_revision=1,
        passport_digest=contract_digest(r1),
        pr_number=PR,
        expected_head_sha=HEAD,
        contour=r1.contour,
    )
    api = BindingChainApi(request)
    adapter = WbCoreReleaseAdapter(
        api,
        fence_guard=lambda _boundary, _request: None,
        max_polls=2,
    )
    admitted = adapter.advance(request)
    assert admitted.status == "admitted" and api.submissions == 1
    assert admitted.admission_binding == WbCoreAdmissionBinding.from_proof(
        api.pull.admission_proofs[0]
    )
    api.make_terminal()
    terminal_outcome = adapter.advance(request)
    assert terminal_outcome.status == "terminal"
    assert wb_core_release_outcome_from_mapping(
        terminal_outcome.to_mapping()
    ) == terminal_outcome
    receipt = wb_core_runtime_result(
        terminal_outcome,
        completed_at="2026-08-05T00:00:02Z",
    )
    binding = wb_core_admission_binding_from_mapping(receipt["admission_binding"])
    assert binding.task_revision == 1
    assert receipt["contour"] == "release:done"
    assert receipt["deploy_identity"] is None

    pr_identity = terminal_outcome.pr_identity
    assert pr_identity is not None
    manifest = ReleaseClosureManifest(
        logical_lane_id="lane-wb-binding-1",
        pr_identities=(pr_identity,),
        deploy_identities=(),
        finalized_at="2026-08-05T00:00:03Z",
    )
    r2 = replace(r1, revision=2, release_manifest=manifest)
    terminal = TerminalEvidence(
        terminal_id="terminal-wb-binding-r2",
        event_id="terminal-event-wb-binding-r2",
        task_id=r2.task_id,
        task_revision=2,
        workstream_id=r2.workstream_ids[0],
        workstream_revision=2,
        executor_generation=1,
        executor=r2.executor,
        closure_kind=r2.contour,
        summary_ru="Финальный r2 manifest связан с неизменяемым admission r1.",
        evidence=("release:receipt",),
        checks=("release:terminal",),
        pr_identities=(pr_identity,),
        deploy_identities=(),
        owner_acceptance_required=True,
        created_at="2026-08-05T00:00:04Z",
    )
    release_event = {
        "event_id": "release-completed-wb-binding-r1",
        "event_type": "release_completed",
        "task_id": r2.task_id,
        "workstream_id": r2.workstream_ids[0],
        "payload": {
            "schema": "dev-control-plane/release-result-event/v2",
            "release_action_event_id": "release-action-wb-binding-r1",
            "receipt": receipt,
            "target_adapter": supervisor_app.WB_CORE_TARGET_ADAPTER,
        },
    }
    registry = FakeRegistry(
        r2,
        workstream_revision=2,
        workstream_state="acceptance_pending",
        events=(release_event,),
    )
    resolver = supervisor_app._WbCoreAdmissionBindingResolver(registry)
    # A new resolver instance proves restart recovery from durable events only.
    assert resolver(r2, terminal, pr_identity) == binding
    assert supervisor_app._WbCoreAdmissionBindingResolver(registry)(
        r2, terminal, pr_identity
    ) == binding
    terminal_request = wb_core_terminal_request_from_contracts(
        candidate_id="candidate-wb-binding-terminal",
        passport=r2,
        terminal=terminal,
        pr_identity=pr_identity,
        admission_binding=binding,
    )
    assert wb_core_release_request_from_mapping(
        asdict(terminal_request)
    ) == terminal_request
    proof = WbCoreContourAdapter(
        adapter,
        admission_binding_resolver=resolver,
        clock=lambda: 1_754_352_005.0,
    )(r2, terminal)
    assert proof.passed is True
    assert "wb_core_exact_admission_proved" in proof.checks

    technical_event = {
        "event_id": "technical-terminal-wb-binding-r2",
        "event_type": "technical_terminal",
        "task_id": r2.task_id,
        "workstream_id": r2.workstream_ids[0],
        "payload": {
            "schema": "dev-control-plane/technical-terminal-event/v2",
            "closure_barrier": True,
        },
    }
    registry.events.append(technical_event)
    closure_digest = supervisor_app._sha256_mapping(
        {
            "event_id": technical_event["event_id"],
            "event_type": technical_event["event_type"],
            "payload": technical_event["payload"],
        }
    )
    closure = _closure_action(
        target=supervisor_app.WB_CORE_REPOSITORY,
        task_id=r2.task_id,
        workstream_id=r2.workstream_ids[0],
        task_revision=2,
        workstream_revision=2,
        pr_identity=pr_identity,
        logical_lane_id=manifest.logical_lane_id,
        release_manifest_digest=contract_digest(manifest),
        closure_event_id=technical_event["event_id"],
        closure_event_type=technical_event["event_type"],
        closure_event_digest=closure_digest,
    )
    fence = SimpleNamespace(generation=7, owner_id=registry.owner_id)
    lane_executor = supervisor_app._TargetLaneClosureExecutor(
        registry=registry,
        fence=fence,
        wb_core_api=api,
    )
    lane_receipt = lane_executor(closure, FakeGuard())
    assert lane_receipt["status"] == "released"
    assert api.lane_submissions == 1
    repeated = lane_executor(closure, FakeGuard())
    assert repeated["status"] == "released" and api.lane_submissions == 1


def _runtime_passport(
    *,
    target: str,
    contour: str,
    task_id: str,
    workstream_id: str,
    revision: int,
    files: Sequence[str],
) -> TaskPassport:
    if target == supervisor_app.SELF_REPO:
        allowed = ["github_readback", "self_merge", "target_lane_release"]
        if contour == "release:production":
            allowed.append("self_hosted_deploy")
        prohibited = ["wb_github_command", "target_release_command"]
        if contour == "release:done":
            prohibited.append("self_hosted_deploy")
    else:
        allowed = ["github_readback", "wb_github_command", "target_lane_release"]
        prohibited = ["self_merge", "self_hosted_deploy", "target_release_command"]
    lane_id = (
        "lane-wb-binding-1"
        if task_id == "task:wb-binding:0001"
        else f"lane-{task_id.replace(':', '-')}"
    )
    return TaskPassport(
        task_id=task_id,
        revision=revision,
        title="Production composition smoke",
        objective="Prove exact release composition without a live mutation.",
        expected_result="Typed immutable release evidence.",
        contour=contour,
        included_scope=("registered release adapter",),
        excluded_scope=("unregistered mutation",),
        constraints=("exact fake transport",),
        acceptance=("immutable readback",),
        closure=("owner acceptance remains explicit",),
        autonomy=AutonomyEnvelope(
            allowed_actions=tuple(allowed),
            prohibited_actions=tuple(prohibited),
        ),
        workstream_ids=(workstream_id,),
        release_manifest=None,
        resources=(
            f"target:{target}",
            f"release-lane:{lane_id}",
            "resource:release-smoke",
        ),
        modules=("module:release-smoke",),
        files=tuple(files),
        dependencies=(),
        multi_pr_intent=False,
        multi_deploy_intent=False,
        curator=CuratorIdentity("curator-thread-smoke", "desktop-host-smoke"),
        executor=ExecutorIdentity(
            "executor-thread-smoke",
            "desktop-host-smoke",
            "gpt-5.6-sol",
            "ultra",
        ),
        created_at="2026-08-05T00:00:00Z",
    )


def _github_truth(
    *,
    target: str,
    pr_number: int,
    files: Sequence[str],
    checks: Mapping[str, str],
    state: str = "OPEN",
) -> PullRequestTruth:
    return PullRequestTruth(
        number=pr_number,
        state=state,
        is_draft=False,
        head_ref="codex/release-smoke",
        head_sha=HEAD,
        base_ref="main",
        mergeable=("MERGEABLE" if state == "OPEN" else "UNKNOWN"),
        merge_state=("CLEAN" if state == "OPEN" else "UNKNOWN"),
        url=f"https://github.com/{target}/pull/{pr_number}",
        files=tuple(files),
        checks=dict(checks),
        merge_commit_sha=(MERGE if state == "MERGED" else None),
    )


def _resolver_reader(
    target: str,
    truth: PullRequestTruth,
    *,
    labels: Sequence[str] = (),
    discovery_state: str | None = None,
) -> Any:
    def read(command: Sequence[str], **_kwargs: Any) -> Any:
        if len(command) > 1 and command[1] == "pr":
            return {"labels": [{"name": label} for label in labels]}
        observed_state = discovery_state or truth.state
        return [
            {
                "number": truth.number,
                "state": "open" if observed_state == "OPEN" else "closed",
                "merged_at": (
                    None if observed_state == "OPEN" else "2026-08-05T00:00:00Z"
                ),
                "head": {"sha": truth.head_sha, "repo": {"full_name": target}},
                "base": {"ref": "main"},
            }
        ]

    return read


def _resolver_candidate(
    passport: TaskPassport,
    head_sha: str,
    *,
    workstream_revision: int,
) -> Mapping[str, Any]:
    target = next(
        item.removeprefix("target:")
        for item in passport.resources
        if item.startswith("target:")
    )
    lane = next(
        item.removeprefix("release-lane:")
        for item in passport.resources
        if item.startswith("release-lane:")
    )
    return {
        "candidate_id": f"candidate-{passport.task_id.replace(':', '-')}",
        "logical_lane_id": lane,
        "task_id": passport.task_id,
        "workstream_id": passport.workstream_ids[0],
        "task_revision": passport.revision,
        "workstream_revision": workstream_revision,
        "target_id": target,
        "pr_head_sha": head_sha,
        "passport_files": list(passport.files),
        "diff_files": [],
        "resources": ["resource:release-smoke"],
        "multi_pr_intent": passport.multi_pr_intent,
    }


def _self_action_payload(
    passport: TaskPassport,
    *,
    pr_number: int,
    workstream_revision: int,
) -> Mapping[str, Any]:
    candidate = _resolver_candidate(
        passport,
        HEAD,
        workstream_revision=workstream_revision,
    )
    return {
        "target_adapter": supervisor_app.SELF_HOSTED_ADAPTER,
        "candidate": candidate,
        "release_candidate": {
            "lane_id": candidate["logical_lane_id"],
            "task_id": passport.task_id,
            "workstream_id": passport.workstream_ids[0],
            "revision": passport.revision,
            "repo": supervisor_app.SELF_REPO,
            "pr_number": pr_number,
            "expected_head_sha": HEAD,
            "base_ref": "main",
            "required_checks": ["v2-suite", "self-closure"],
            "declared_files": list(passport.files),
            "resources": ["resource:release-smoke"],
            "multi_pr": False,
        },
    }


def _closure_action(
    *,
    target: str,
    task_id: str,
    workstream_id: str,
    task_revision: int,
    workstream_revision: int,
    pr_identity: str,
    logical_lane_id: str = "lane-smoke",
    release_manifest_digest: str = "f" * 64,
    closure_event_id: str = "closure-event-smoke",
    closure_event_type: str = "technical_terminal",
    closure_event_digest: str = "e" * 64,
) -> Mapping[str, Any]:
    return {
        "schema": "dev-control-plane/target-lane-closure/v2",
        "binding_kind": "final_manifest",
        "closure_id": "closure-binding-smoke",
        "supervisor_generation": 7,
        "task_id": task_id,
        "task_revision": task_revision,
        "workstream_id": workstream_id,
        "workstream_revision": workstream_revision,
        "target_id": target,
        "logical_lane_id": logical_lane_id,
        "contour": "release:done",
        "outcome": "completed",
        "ordered_pr_identities": [pr_identity],
        "anchor_pr_identity": pr_identity,
        "release_manifest_digest": release_manifest_digest,
        "closure_event_id": closure_event_id,
        "closure_event_type": closure_event_type,
        "closure_event_digest": closure_event_digest,
    }


def _staged_pull() -> WbCorePullReadback:
    return WbCorePullReadback(
        number=PR,
        state="OPEN",
        is_draft=False,
        head_sha=HEAD,
        base_ref="main",
        labels=("task:standard", "scope:repo-only", "release:staged"),
        url=f"https://github.com/orenvlad-ai/wb-core/pull/{PR}",
    )


def _admission() -> WbCoreAdmissionProof:
    return WbCoreAdmissionProof(
        pr_number=PR,
        owner_pr=PR,
        head_sha=HEAD,
        target_task_id=TARGET_TASK,
        task_revision=REQUEST.task_revision,
        passport_digest=PASSPORT,
    )


def _queue(
    *,
    lane_status: str = "idle",
    owner_pr: int | None = None,
    task_id: str | None = None,
    revision: int | None = None,
    queue_status: str = "idle",
    active_prs: tuple[int, ...] = (),
    integrity: str = "ok",
    signals: tuple[str, ...] = (),
    release_proofs: tuple[WbCoreLaneReleaseProof, ...] = (),
) -> WbCoreQueueReadback:
    if lane_status == "owned" and owner_pr is not None and owner_pr not in active_prs:
        active_prs = (*active_prs, owner_pr)
    return WbCoreQueueReadback(
        queue_status=queue_status,
        lane_status=lane_status,
        integrity_status=integrity,
        lane_owner_pr=owner_pr,
        lane_task_id=task_id,
        lane_revision=revision,
        integrity_signals=signals,
        active_prs=active_prs,
        release_proofs=release_proofs,
    )


if __name__ == "__main__":
    main()
