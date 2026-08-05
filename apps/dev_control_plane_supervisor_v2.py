"""Single-writer local Orchestrator v2 daemon and private-socket client CLI."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Callable, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (SRC, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dev_control_plane.arbiter import ArbiterCase, FreshSolArbiter  # noqa: E402
from dev_control_plane.codex_app_server import CodexAppServerClient  # noqa: E402
from dev_control_plane.contour_verifier import (  # noqa: E402
    HOSTED_DOMAIN,
    HOSTED_TARGET,
    build_dev_control_plane_contour_verifier,
)
from dev_control_plane.curator_delivery import (  # noqa: E402
    OwnerAcceptanceSourceVerifier,
    OwnerActionAttestationVerifier,
)
from dev_control_plane.orchestration_contracts import (  # noqa: E402
    ArbiterDecision,
    RevisionBinding,
    arbiter_decision_from_mapping,
    contract_digest,
    required_release_actions,
    require_passport_action,
    task_passport_from_mapping,
)
from dev_control_plane.projection_client import (  # noqa: E402
    PRODUCTION_PROJECTION_ENDPOINT,
    ProjectionPublisher,
)
from dev_control_plane.release_train import (  # noqa: E402
    GitHubClient,
    MechanicalReleaseTrain,
    ReleaseCandidate as ReleaseTrainCandidate,
)
from dev_control_plane.local_install import (  # noqa: E402
    LocalInstallError,
    preactivation_supervisor_start_guard,
)
from dev_control_plane.supervisor import (  # noqa: E402
    LOCAL_HOST,
    SERVICE_ROLE,
    SupervisorEngine,
    SupervisorHTTPServer,
    stable_supervisor_id,
)
from dev_control_plane.supervisor_registry import SupervisorRegistry  # noqa: E402
from dev_control_plane.supervisor_runtime import (  # noqa: E402
    DEFAULT_DESKTOP_CODEX_BIN,
    RuntimeActionGuard,
    SecurityPermissionChangeRequiresOwner,
    SupervisorCommandClient,
    SupervisorCommandServer,
    SupervisorRuntime,
    SupervisorRuntimeLoop,
    default_socket_path,
)
from dev_control_plane.wb_core_release_adapter import (  # noqa: E402
    GhWbCoreReleaseTrainApi,
    WB_CORE_REPOSITORY,
    WB_CORE_TARGET_ADAPTER,
    WbCoreAdmissionBinding,
    WbCoreContourAdapter,
    WbCoreLaneReleaseRequest,
    WbCoreReleaseAdapter,
    WbCoreReleaseLaneAdapter,
    WbCoreReleaseRequest,
    derive_wb_core_target_task_id,
    wb_core_admission_binding_from_mapping,
    wb_core_runtime_result,
)

MAX_JSON_BYTES = 1_000_000
SELF_HOSTED_ADAPTER = "dev-control-plane-hosted-v2"
SELF_REPO = "orenvlad-ai/dev-control-plane"
WB_CORE_REMOTE = "https://github.com/orenvlad-ai/wb-core.git"
_WB_CORE_QUEUE_MAX_BYTES = 16_000_000
_WB_CORE_PR_IDENTITY_RE = re.compile(
    r"^github-pr-v1:orenvlad-ai/wb-core:"
    r"(?P<number>[1-9][0-9]*):[0-9a-f]{40}:[0-9a-f]{40}$"
)
INCIDENT_APPLICATION_DISPOSITION_SCHEMA = (
    "dev-control-plane/incident-application-disposition/v2"
)
PARKED_TARGET_LANE_ADMISSION_SCHEMA = (
    "dev-control-plane/parked-target-lane-admission/v2"
)


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    role = os.environ.get("DEV_CONTROL_PLANE_AUTHORITY_ROLE")
    if role not in {None, "", SERVICE_ROLE}:
        parser.error(f"authority role must be {SERVICE_ROLE}")
    if args.command == "serve":
        return _serve(args)
    result = _socket_dispatch(args)
    _print_json(result)
    return 0


def _serve(
    args: argparse.Namespace,
    *,
    codex_client_factory: Callable[..., CodexAppServerClient] = CodexAppServerClient,
    release_executor: Callable[[Mapping[str, Any], RuntimeActionGuard], Mapping[str, Any]] | None = None,
    release_candidate_resolver: Callable[[Mapping[str, Any], RuntimeActionGuard], Mapping[str, Any]] | None = None,
    release_arbiter_executor: Callable[[Mapping[str, Any], RuntimeActionGuard], ArbiterDecision] | None = None,
    incident_arbiter_executor: Callable[[Mapping[str, Any], RuntimeActionGuard], ArbiterDecision] | None = None,
    incident_application_executor: Callable[[Mapping[str, Any], RuntimeActionGuard], Mapping[str, Any]] | None = None,
    target_lane_closure_executor: Callable[
        [Mapping[str, Any], RuntimeActionGuard], Mapping[str, Any]
    ]
    | None = None,
    owner_acceptance_verifier: Callable[[Any, Mapping[str, Any]], bool] | None = None,
    owner_action_verifier: Callable[
        [Mapping[str, Any], Mapping[str, Any]], bool
    ]
    | None = None,
) -> int:
    """Acquire the only generation and compose every long-lived worker."""

    if args.host != "127.0.0.1" or args.port != 8766:
        raise RuntimeError("Supervisor production HTTP must bind exact 127.0.0.1:8766")
    state_dir = Path(args.state_dir).expanduser().resolve()
    workspace_root = Path(args.workspace_root or state_dir / "managed_workspaces").expanduser().resolve()
    activation_identity = _activation_identity(args)
    codex_bin = Path(args.codex_bin).expanduser().resolve(strict=True)
    if not codex_bin.is_file() or not os.access(codex_bin, os.X_OK):
        raise RuntimeError("configured Codex binary is unavailable")
    publisher = _publisher(args, state_dir)
    if publisher is None:
        raise RuntimeError("production projection publisher key is unavailable")
    try:
        with preactivation_supervisor_start_guard(state_dir):
            registry = SupervisorRegistry(state_dir / "supervisor.sqlite3")
            fence = registry.acquire_generation(
                f"supervisor-daemon:{os.getpid()}:{time.time_ns()}"
            )
    except LocalInstallError as exc:
        raise RuntimeError("Supervisor startup is fenced by local lifecycle state") from exc
    runtime: SupervisorRuntime | None = None
    try:
        gh_binary = _gh_binary()
        wb_queue_reader = _WbCoreManagedQueueReader(
            workspace_root=workspace_root,
            gh_binary=gh_binary,
        )
        wb_api = GhWbCoreReleaseTrainApi(
            queue_snapshot_reader=wb_queue_reader,
            gh_binary=gh_binary,
        )
        wb_read_adapter = WbCoreReleaseAdapter(
            wb_api,
            fence_guard=lambda _boundary, _request: _assert_registry_fence(
                registry, fence
            ),
        )
        contour_verifier = build_dev_control_plane_contour_verifier()
        wb_contour_adapter = WbCoreContourAdapter(
            wb_read_adapter,
            admission_binding_resolver=_WbCoreAdmissionBindingResolver(registry),
        )
        contour_verifier.register(
            contour="release:done",
            target=WB_CORE_REPOSITORY,
            adapter=wb_contour_adapter,
        )
        contour_verifier.register(
            contour="release:production",
            target=WB_CORE_REPOSITORY,
            adapter=wb_contour_adapter,
        )
        release_worker = release_executor or _CompositeReleaseExecutor(
            self_executor=_SelfHostedReleaseExecutor(
                registry=registry,
                workspace_root=workspace_root,
                projection_key_file=_projection_key_path(args, state_dir),
            ),
            wb_core_executor=_WbCoreReleaseExecutor(
                registry=registry,
                api=wb_api,
            ),
        )
        release_resolver = release_candidate_resolver or _ReleaseCandidateResolver(
            registry=registry,
            gh_binary=gh_binary,
        )
        release_arbiter = release_arbiter_executor or _ReleaseArbiterExecutor(
            codex_bin=codex_bin,
            workspace_root=workspace_root,
        )
        incident_worker = incident_arbiter_executor or _IncidentArbiterExecutor(
            codex_bin=codex_bin,
            workspace_root=workspace_root,
        )
        application_worker = incident_application_executor or _apply_incident_decision
        lane_closure_worker = target_lane_closure_executor or _TargetLaneClosureExecutor(
            registry=registry,
            fence=fence,
            wb_core_api=wb_api,
        )
        owner_key = state_dir.parent / "secrets" / "owner_acceptance_hmac.key"
        acceptance_verifier = owner_acceptance_verifier or OwnerAcceptanceSourceVerifier(
            owner_key
        )
        action_verifier = owner_action_verifier or OwnerActionAttestationVerifier(
            owner_key
        )
        engine = SupervisorEngine(
            registry,
            fence,
            supervisor_id=stable_supervisor_id(str(state_dir)),
            publisher=publisher,
            contour_verifier=contour_verifier,
        )
        runtime = SupervisorRuntime(
            engine,
            allowed_workspace_root=workspace_root,
            codex_client_factory=codex_client_factory,
            codex_bin=codex_bin,
            release_executor=release_worker,
            release_candidate_resolver=release_resolver,
            release_arbiter_executor=release_arbiter,
            incident_arbiter_executor=incident_worker,
            incident_application_executor=application_worker,
            target_lane_closure_executor=lane_closure_worker,
            owner_acceptance_verifier=acceptance_verifier,
            owner_action_verifier=action_verifier,
            activation_identity=activation_identity,
        )
        command_server = SupervisorCommandServer(runtime, default_socket_path(state_dir))
        loop = SupervisorRuntimeLoop(
            runtime,
            maintenance_interval_seconds=args.interval,
            codex_poll_seconds=args.worker_poll,
        )
        http_server = SupervisorHTTPServer(runtime.http_engine, args.host, args.port)
    except Exception:
        if runtime is not None:
            runtime.close()
        registry.release_generation(fence)
        raise
    try:
        runtime.resume_owned_threads()
        runtime.renew_generation_lease()
        command_server.start()
        loop.start()
        readiness = runtime.readiness()
        if not readiness["ready"]:
            raise RuntimeError("Supervisor runtime composition is not ready")
        _print_json(
            {
                "status": "ready",
                "service_role": SERVICE_ROLE,
                "host": args.host,
                "port": http_server.server_address[1],
                "generation": engine.fence.generation,
                "command_socket": str(default_socket_path(state_dir)),
                "http_mutation_enabled": False,
            }
        )
        http_server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        return 0
    finally:
        http_server.server_close()
        try:
            loop.stop()
        finally:
            try:
                command_server.stop()
            finally:
                runtime.close()
                try:
                    registry.release_generation(engine.fence)
                except Exception:
                    pass
    return 0


def _socket_dispatch(args: argparse.Namespace) -> Any:
    state_dir = Path(args.state_dir).expanduser().resolve()
    client = SupervisorCommandClient(default_socket_path(state_dir), timeout_seconds=args.timeout)
    if args.command == "command":
        payload = {} if args.input is None else _read_json(args.input)
        return client.request(args.name, payload, request_id=args.request_id)
    name = {"health": "runtime_health", "state": "runtime_state", "tick": "tick"}[args.command]
    return client.request(name, {}, request_id=args.request_id)


class _IncidentArbiterExecutor:
    def __init__(self, *, codex_bin: Path, workspace_root: Path) -> None:
        self.arbiter = FreshSolArbiter(codex_bin=str(codex_bin))
        self.workspace_root = workspace_root

    def __call__(self, payload: Mapping[str, Any], guard: RuntimeActionGuard) -> ArbiterDecision:
        binding = _mapping(payload, "binding")
        case = ArbiterCase(
            kind="incident",
            case_id=str(payload["case_id"]),
            case_digest=str(payload["case_digest"]),
            bindings=(
                RevisionBinding(
                    task_id=str(binding["task_id"]),
                    task_revision=int(binding["task_revision"]),
                    workstream_id=str(binding["workstream_id"]),
                    workstream_revision=int(binding["workstream_revision"]),
                    pr_head_sha=str(binding["pr_head_sha"]),
                    resources=tuple(binding["resources"]),
                ),
            ),
            snapshot={"incident_state": payload["incident_state"], "binding": dict(binding)},
        )
        guard.checkpoint()
        decision = self.arbiter.decide(case, cwd=self.workspace_root)
        guard.assert_current()
        return decision


class _ReleaseArbiterExecutor:
    """One fresh schema-bound Sol invocation for an immutable RELEASE_PLAN."""

    def __init__(self, *, codex_bin: Path, workspace_root: Path) -> None:
        self.arbiter = FreshSolArbiter(codex_bin=str(codex_bin))
        self.workspace_root = workspace_root

    def __call__(self, payload: Mapping[str, Any], guard: RuntimeActionGuard) -> ArbiterDecision:
        semantic = _mapping(payload, "semantic_case")
        candidates = semantic.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            raise RuntimeError("release arbiter case has no candidates")
        bindings = tuple(
            RevisionBinding(
                task_id=str(candidate["task_id"]),
                task_revision=int(candidate["task_revision"]),
                workstream_id=str(candidate["workstream_id"]),
                workstream_revision=int(candidate["workstream_revision"]),
                pr_head_sha=str(candidate["pr_head_sha"]),
                resources=tuple(candidate["resources"]),
            )
            for candidate in candidates
            if isinstance(candidate, Mapping)
        )
        if len(bindings) != len(candidates):
            raise RuntimeError("release arbiter candidate binding is malformed")
        case = ArbiterCase(
            kind="release_plan",
            case_id=str(semantic["case_id"]),
            case_digest=str(semantic["case_digest"]),
            bindings=bindings,
            snapshot={"semantic_case": dict(semantic)},
        )
        guard.checkpoint()
        decision = self.arbiter.decide(case, cwd=self.workspace_root)
        guard.assert_current()
        return decision


class _ReleaseCandidateResolver:
    """Resolve exact self/wb-core PR truth without choosing release order."""

    _WB_TASK_LABELS = frozenset({"task:standard", "task:loop"})
    _WB_SCOPE_LABELS = frozenset(
        {"scope:repo-only", "scope:live-runtime", "scope:production-mutation"}
    )
    _WB_PRIMARY_STATES = frozenset(
        {
            "release:staged",
            "release:ready",
            "release:running",
            "release:awaiting-agent",
            "release:awaiting-ui",
            "release:blocked",
            "release:halted",
            "release:done",
            "release:production",
            "release:superseded",
            "release:retired",
        }
    )
    _WB_ACTIVE_STANDARD_STATES = frozenset(
        {
            frozenset({"release:staged"}),
            frozenset({"release:ready"}),
            frozenset({"release:ready", "release:running"}),
        }
    )

    def __init__(
        self,
        *,
        registry: SupervisorRegistry,
        gh_binary: str | None = None,
        github: Any | None = None,
        json_reader: Callable[..., Any] | None = None,
    ) -> None:
        self.registry = registry
        self.gh_binary = gh_binary or _gh_binary()
        self.github = github or GitHubClient(gh_binary=self.gh_binary)
        self.json_reader = json_reader or _run_json_value

    def __call__(self, payload: Mapping[str, Any], guard: RuntimeActionGuard) -> Mapping[str, Any]:
        candidate = _mapping(payload, "candidate")
        target_id = str(candidate.get("target_id") or "")
        if target_id not in {SELF_REPO, WB_CORE_REPOSITORY}:
            raise RuntimeError("release target has no registered candidate resolver")
        passport = self._current_passport(candidate)
        passport_binding = contract_digest(passport)
        head_sha = str(candidate["pr_head_sha"])
        guard.checkpoint()
        raw = self.json_reader(
            [
                self.gh_binary,
                "api",
                "-H",
                "Accept: application/vnd.github+json",
                f"repos/{target_id}/commits/{head_sha}/pulls",
            ],
            cwd=ROOT,
            timeout=60,
        )
        if not isinstance(raw, list):
            raise RuntimeError("GitHub commit-to-PR readback returned a non-array")
        guard.checkpoint()
        matches = [
            item
            for item in raw
            if isinstance(item, Mapping)
            and (
                item.get("state") == "open"
                or (
                    item.get("state") == "closed"
                    and isinstance(item.get("merged_at"), str)
                    and bool(item.get("merged_at"))
                )
            )
            and isinstance(item.get("head"), Mapping)
            and item["head"].get("sha") == head_sha
            and isinstance(item["head"].get("repo"), Mapping)
            and item["head"]["repo"].get("full_name") == target_id
            and isinstance(item.get("base"), Mapping)
            and item["base"].get("ref") == "main"
        ]
        if (
            len(matches) != 1
            or isinstance(matches[0].get("number"), bool)
            or not isinstance(matches[0].get("number"), int)
            or int(matches[0]["number"]) < 1
        ):
            raise RuntimeError(
                "scheduler head does not resolve to one exact open/merged main PR"
            )
        pr_number = matches[0]["number"]
        discovery_state = (
            "OPEN" if matches[0].get("state") == "open" else "MERGED"
        )
        guard.checkpoint()
        truth = self.github.read_pr(repo=target_id, pr_number=pr_number)
        guard.checkpoint()
        if target_id == WB_CORE_REPOSITORY:
            guard.checkpoint()
        labels = (
            self._read_labels(target_id, pr_number)
            if target_id == WB_CORE_REPOSITORY
            else frozenset()
        )
        guard.checkpoint()
        if (
            truth.state not in {"OPEN", "MERGED"}
            or (discovery_state == "MERGED" and truth.state != "MERGED")
            or (truth.state == "OPEN" and truth.is_draft)
            or truth.head_sha != head_sha
            or truth.base_ref != "main"
            or (
                bool(candidate["diff_files"])
                and set(truth.files) != set(candidate["diff_files"])
            )
        ):
            raise RuntimeError("GitHub PR truth differs from the immutable scheduler snapshot")
        if contract_digest(self._current_passport(candidate)) != passport_binding:
            raise RuntimeError("Task Passport changed during GitHub release readback")
        protected = tuple(
            path
            for path in truth.files
            if target_id == SELF_REPO and _is_protected_self_governance_path(path)
        )
        if protected and truth.state == "OPEN":
            raise SecurityPermissionChangeRequiresOwner(
                expected_head_sha=head_sha,
                evidence=_protected_governance_evidence(head_sha, protected),
            )

        if target_id == WB_CORE_REPOSITORY:
            required_checks = ("baseline",)
            checks_green = all(
                truth.checks.get(check_name) == "SUCCESS"
                for check_name in required_checks
            )
            classification_ready = self._wb_classification_ready(
                passport.contour,
                truth.state,
                labels,
            ) and _passport_release_actions_ready(passport, target_id)
            target_adapter = WB_CORE_TARGET_ADAPTER
        else:
            required_checks = ("v2-suite", "self-closure")
            checks_green = all(
                truth.checks.get(check_name) == "SUCCESS"
                for check_name in required_checks
            )
            classification_ready = (
                not _passport_has_no_auto_merge(passport)
                and _passport_release_actions_ready(passport, target_id)
            )
            target_adapter = SELF_HOSTED_ADAPTER

        unsafe = any(
            Path(path).is_absolute()
            or ".." in Path(path).parts
            or path.startswith(".git/")
            for path in truth.files
        )
        admission_ready = (
            truth.state == "OPEN"
            and not truth.is_draft
            and truth.head_sha == head_sha
            and truth.base_ref == "main"
            and bool(truth.files)
            and checks_green
            and classification_ready
        )
        resolved = ReleaseTrainCandidate(
            lane_id=str(candidate["logical_lane_id"]),
            task_id=str(candidate["task_id"]),
            workstream_id=str(candidate["workstream_id"]),
            revision=int(candidate["task_revision"]),
            repo=target_id,
            pr_number=pr_number,
            expected_head_sha=head_sha,
            base_ref="main",
            required_checks=required_checks,
            declared_files=tuple(candidate["passport_files"]),
            resources=tuple(candidate["resources"]),
            multi_pr=bool(candidate["multi_pr_intent"]),
        )
        return {
            "release_candidate": asdict(resolved),
            "target_adapter": target_adapter,
            "scheduler_truth": {
                "task_revision": candidate["task_revision"],
                "workstream_revision": candidate["workstream_revision"],
                "pr_head_sha": head_sha,
                "target_id": target_id,
                "pr_state": truth.state,
                "merge_commit_sha": truth.merge_commit_sha,
                "diff_files": list(truth.files),
                "checks_green": checks_green,
                "admission_ready": admission_ready,
                "merge_conflict": (
                    truth.state == "OPEN"
                    and (
                        truth.mergeable != "MERGEABLE"
                        or truth.merge_state not in {"CLEAN", "HAS_HOOKS", "UNSTABLE"}
                    )
                ),
                "passport_diff_mismatch": not set(truth.files).issubset(set(candidate["passport_files"])),
                "unknown_classification": unsafe or not classification_ready,
            },
        }

    def _current_passport(self, candidate: Mapping[str, Any]) -> Any:
        task_id = str(candidate["task_id"])
        workstream_id = str(candidate["workstream_id"])
        task = self.registry.get_task(task_id)
        workstream = self.registry.get_workstream(workstream_id)
        if (
            task is None
            or workstream is None
            or workstream.task_id != task_id
            or task.revision != candidate["task_revision"]
            or workstream.revision != candidate["workstream_revision"]
            or task.state in {"accepted", "parked"}
            or workstream.state != "waiting_release"
        ):
            raise RuntimeError("release candidate is not bound to a current Passport")
        passport = task_passport_from_mapping(task.passport)
        targets = tuple(
            item.removeprefix("target:")
            for item in passport.resources
            if item.startswith("target:")
        )
        if (
            targets != (candidate["target_id"],)
            or passport.task_id != task_id
            or passport.revision != candidate["task_revision"]
            or passport.contour not in {"release:done", "release:production"}
        ):
            raise RuntimeError("release candidate target/contour differs from current Passport")
        return passport

    def _read_labels(self, repository: str, pr_number: int) -> frozenset[str]:
        raw = self.json_reader(
            [
                self.gh_binary,
                "pr",
                "view",
                str(pr_number),
                "--repo",
                repository,
                "--json",
                "labels",
            ],
            cwd=ROOT,
            timeout=60,
        )
        if not isinstance(raw, Mapping):
            raise RuntimeError("GitHub PR label readback returned a non-object")
        values = raw.get("labels")
        if not isinstance(values, list) or len(values) > 256:
            raise RuntimeError("GitHub PR label readback is malformed")
        labels: list[str] = []
        for item in values:
            if (
                not isinstance(item, Mapping)
                or not isinstance(item.get("name"), str)
                or not item["name"]
                or len(item["name"]) > 100
            ):
                raise RuntimeError("GitHub PR label readback is malformed")
            if item["name"] not in labels:
                labels.append(item["name"])
        return frozenset(labels)

    def _wb_classification_ready(
        self,
        contour: str,
        pr_state: str,
        labels: frozenset[str],
    ) -> bool:
        expected_scope = (
            "scope:repo-only" if contour == "release:done" else "scope:live-runtime"
        )
        if (
            labels & self._WB_TASK_LABELS != {"task:standard"}
            or labels & self._WB_SCOPE_LABELS != {expected_scope}
        ):
            return False
        primary = frozenset(labels & self._WB_PRIMARY_STATES)
        if pr_state == "OPEN":
            return primary in self._WB_ACTIVE_STANDARD_STATES
        expected_terminal = (
            "release:done" if contour == "release:done" else "release:production"
        )
        return (
            primary == frozenset({expected_terminal})
            or primary in self._WB_ACTIVE_STANDARD_STATES
        )


def _apply_incident_decision(
    payload: Mapping[str, Any],
    guard: RuntimeActionGuard,
) -> Mapping[str, Any]:
    """Return one fail-closed disposition; never synthesize verification.

    The application adapter does not own a release actuator or an independent
    verifier.  It may therefore reserve exactly one downstream durable action,
    or park.  A later exact actuator receipt is the only surface allowed to
    turn a dispatched incident into a verified resolution.
    """

    decision = arbiter_decision_from_mapping(_mapping(payload, "decision"))
    if len(decision.steps) != 1:
        raise RuntimeError("incident decision must contain exactly one bounded step")
    action = decision.steps[0].action
    guard.checkpoint()
    if action not in {"wait", "verify", "park_workstream"}:
        raise RuntimeError("incident decision requires an unavailable governed remediation adapter")
    disposition = "park"
    remediation = payload.get("remediation")
    if remediation is not None:
        raw = _mapping(payload, "remediation")
        remediation_kind = (raw.get("schema"), raw.get("kind"))
        if remediation_kind == (
            "dev-control-plane/release-incident-remediation/v2",
            "release_action",
        ):
            if action == "verify":
                disposition = "dispatch_release_once"
        elif remediation_kind == (
            "dev-control-plane/target-lane-incident-remediation/v2",
            "target_lane_closure",
        ):
            if action == "verify":
                disposition = "dispatch_target_lane_once"
        else:
            raise RuntimeError("incident remediation adapter is not registered")
    guard.checkpoint()
    return {
        "schema": INCIDENT_APPLICATION_DISPOSITION_SCHEMA,
        "applied": True,
        "disposition": disposition,
        "verification_identity": (
            "deterministic-incident-disposition:"
            + decision.decision_id
            + ":"
            + disposition
        ),
    }


class _CompositeReleaseExecutor:
    """Dispatch only to one statically registered target adapter."""

    def __init__(
        self,
        *,
        self_executor: Callable[[Mapping[str, Any], RuntimeActionGuard], Mapping[str, Any]],
        wb_core_executor: Callable[[Mapping[str, Any], RuntimeActionGuard], Mapping[str, Any]],
    ) -> None:
        self.self_executor = self_executor
        self.wb_core_executor = wb_core_executor

    def __call__(
        self,
        payload: Mapping[str, Any],
        guard: RuntimeActionGuard,
    ) -> Mapping[str, Any]:
        adapter = str(payload.get("target_adapter") or "")
        if adapter == SELF_HOSTED_ADAPTER:
            return self.self_executor(payload, guard)
        if adapter == WB_CORE_TARGET_ADAPTER:
            return self.wb_core_executor(payload, guard)
        raise RuntimeError("release target has no registered local adapter")


class _WbCoreReleaseExecutor:
    """Bind current Passport truth to the external target Release Train."""

    def __init__(self, *, registry: SupervisorRegistry, api: Any) -> None:
        self.registry = registry
        self.api = api

    def __call__(
        self,
        payload: Mapping[str, Any],
        guard: RuntimeActionGuard,
    ) -> Mapping[str, Any]:
        if payload.get("target_adapter") != WB_CORE_TARGET_ADAPTER:
            raise RuntimeError("wb-core executor received another target adapter")
        scheduler = _mapping(payload, "candidate")
        release = _mapping(payload, "release_candidate")
        if (
            scheduler.get("target_id") != WB_CORE_REPOSITORY
            or release.get("repo") != WB_CORE_REPOSITORY
            or release.get("base_ref") != "main"
            or tuple(release.get("required_checks") or ()) != ("baseline",)
            or release.get("expected_head_sha") != scheduler.get("pr_head_sha")
            or release.get("task_id") != scheduler.get("task_id")
            or release.get("workstream_id") != scheduler.get("workstream_id")
            or release.get("revision") != scheduler.get("task_revision")
        ):
            raise RuntimeError("wb-core release action binding is stale")
        guard.checkpoint()
        task = self.registry.get_task(str(scheduler["task_id"]))
        workstream = self.registry.get_workstream(str(scheduler["workstream_id"]))
        if (
            task is None
            or workstream is None
            or workstream.task_id != task.task_id
            or task.revision != scheduler["task_revision"]
            or workstream.revision != scheduler["workstream_revision"]
            or task.state in {"accepted", "parked"}
            or workstream.state != "waiting_release"
        ):
            raise RuntimeError("wb-core release action lost its current Passport binding")
        passport = task_passport_from_mapping(task.passport)
        targets = tuple(
            item.removeprefix("target:")
            for item in passport.resources
            if item.startswith("target:")
        )
        if (
            targets != (WB_CORE_REPOSITORY,)
            or passport.task_id != scheduler["task_id"]
            or passport.revision != scheduler["task_revision"]
            or passport.contour not in {"release:done", "release:production"}
        ):
            raise RuntimeError("wb-core current Passport target/contour is invalid")
        passport_digest = contract_digest(passport)
        require_passport_action(passport, "wb_github_command")
        request = WbCoreReleaseRequest(
            candidate_id=str(scheduler["candidate_id"]),
            task_id=passport.task_id,
            target_task_id=derive_wb_core_target_task_id(passport.task_id),
            workstream_id=str(scheduler["workstream_id"]),
            task_revision=passport.revision,
            workstream_revision=int(scheduler["workstream_revision"]),
            passport_digest=passport_digest,
            pr_number=int(release["pr_number"]),
            expected_head_sha=str(release["expected_head_sha"]),
            contour=passport.contour,
        )

        def exact_fence(boundary: str, _request: WbCoreReleaseRequest) -> None:
            guard.checkpoint()
            if boundary == "before_admission_command":
                current = self.registry.get_task(passport.task_id)
                if current is None:
                    raise RuntimeError("wb-core mutation lost its current Passport")
                observed = task_passport_from_mapping(current.passport)
                if (
                    current.revision != passport.revision
                    or contract_digest(observed) != passport_digest
                ):
                    raise RuntimeError("wb-core mutation Passport changed")
                require_passport_action(observed, "wb_github_command")

        adapter = WbCoreReleaseAdapter(
            self.api,
            fence_guard=exact_fence,
        )
        return wb_core_runtime_result(adapter.advance(request))


class _WbCoreAdmissionBindingResolver:
    """Resolve only a durable target-owned r1 proof for final rN verification."""

    def __init__(self, registry: SupervisorRegistry) -> None:
        self.registry = registry

    def __call__(
        self,
        passport: Any,
        terminal: Any,
        pr_identity: str,
    ) -> WbCoreAdmissionBinding:
        match = _WB_CORE_PR_IDENTITY_RE.fullmatch(pr_identity)
        if match is None:
            raise RuntimeError("wb-core durable admission PR identity is malformed")
        pr_number = int(match.group("number"))
        head_sha, merge_sha = pr_identity.rsplit(":", 2)[-2:]
        exact_url = f"https://github.com/{WB_CORE_REPOSITORY}/pull/{pr_number}"
        matches: dict[str, WbCoreAdmissionBinding] = {}
        for event in self.registry.list_events(
            task_id=passport.task_id,
            event_types=("release_completed",),
        ):
            payload = event.get("payload")
            if (
                not isinstance(payload, Mapping)
                or payload.get("target_adapter") != WB_CORE_TARGET_ADAPTER
                or event.get("workstream_id") != terminal.workstream_id
            ):
                continue
            receipt = payload.get("receipt")
            if (
                not isinstance(receipt, Mapping)
                or receipt.get("task_id") != passport.task_id
                or receipt.get("workstream_id") != terminal.workstream_id
                or receipt.get("contour") != passport.contour
                or receipt.get("pr_url") != exact_url
                or receipt.get("pr_head_sha") != head_sha
                or receipt.get("merge_sha") != merge_sha
            ):
                continue
            raw_binding = receipt.get("admission_binding")
            try:
                binding = wb_core_admission_binding_from_mapping(raw_binding)
            except (TypeError, ValueError) as exc:
                raise RuntimeError(
                    "wb-core durable admission receipt is malformed"
                ) from exc
            if (
                binding.pr_number != pr_number
                or binding.head_sha != head_sha
                or binding.target_task_id
                != derive_wb_core_target_task_id(passport.task_id)
                or receipt.get("task_revision") != binding.task_revision
                or binding.task_revision > passport.revision
            ):
                raise RuntimeError("wb-core durable admission receipt is cross-bound")
            digest = _sha256_mapping(asdict(binding))
            matches[digest] = binding
        if len(matches) != 1:
            raise RuntimeError("wb-core durable admission binding is missing or conflicting")
        return next(iter(matches.values()))


class _TargetLaneClosureExecutor:
    """Close a local self lane or invoke wb-core's exact trusted command."""

    _COMMON_ACTION_FIELDS = frozenset(
        {
            "schema",
            "binding_kind",
            "closure_id",
            "supervisor_generation",
            "task_id",
            "task_revision",
            "workstream_id",
            "workstream_revision",
            "target_id",
            "logical_lane_id",
            "contour",
            "outcome",
            "closure_event_id",
            "closure_event_type",
            "closure_event_digest",
        }
    )
    _FINAL_ACTION_FIELDS = _COMMON_ACTION_FIELDS | frozenset(
        {
            "ordered_pr_identities",
            "anchor_pr_identity",
            "release_manifest_digest",
        }
    )
    _PARKED_ADMISSION_ACTION_FIELDS = _COMMON_ACTION_FIELDS | frozenset(
        {"parked_admission"}
    )
    _PARKED_ADMISSION_FIELDS = frozenset(
        {
            "schema",
            "target_adapter",
            "candidate_id",
            "pr_number",
            "expected_head_sha",
            "admission_task_revision",
            "admission_workstream_revision",
            "release_action_event_id",
            "observation_event_id",
            "observation_event_digest",
            "admission_binding",
        }
    )

    def __init__(
        self,
        *,
        registry: SupervisorRegistry,
        fence: Any,
        wb_core_api: Any,
    ) -> None:
        self.registry = registry
        self.fence = fence
        self.wb_core_api = wb_core_api

    def __call__(
        self,
        action: Mapping[str, Any],
        guard: RuntimeActionGuard,
    ) -> Mapping[str, Any]:
        target = str(action.get("target_id") or "")
        if target == SELF_REPO:
            self._authorize(action, guard)
            evidence_digest = _sha256_mapping(action)
            self._authorize(action, guard)
            return self._receipt(
                action,
                status=("parked" if action["outcome"] == "parked" else "released"),
                reason_code="local_logical_lane_closed",
                evidence_digest=evidence_digest,
                retry_after_seconds=None,
            )
        if target != WB_CORE_REPOSITORY:
            raise RuntimeError("target lane closure has no registered target adapter")
        self._authorize(action, guard)
        anchor_pr = self._anchor_pr(action)
        request = WbCoreLaneReleaseRequest(
            closure_event_id=str(action["closure_event_id"]),
            task_id=str(action["task_id"]),
            target_task_id=derive_wb_core_target_task_id(str(action["task_id"])),
            task_revision=int(action["task_revision"]),
            anchor_pr=anchor_pr,
            outcome=str(action["outcome"]),
            evidence_digest=str(action["closure_event_digest"]),
        )
        adapter = WbCoreReleaseLaneAdapter(
            self.wb_core_api,
            fence_guard=lambda _boundary, _request: guard.checkpoint(),
            authorization_guard=lambda observed: self._authorize_wb(
                action, observed, guard
            ),
        )
        outcome = adapter.advance(request)
        if outcome.status == "release_submitted":
            return self._receipt(
                action,
                status="submitted",
                reason_code=outcome.reason_code,
                evidence_digest=(
                    outcome.release_proof_digest or outcome.command_digest
                ),
                retry_after_seconds=outcome.next_poll_after_seconds,
            )
        if outcome.status != "released" or outcome.release_proof_digest is None:
            raise RuntimeError(outcome.reason_code)
        return self._receipt(
            action,
            status=("parked" if action["outcome"] == "parked" else "released"),
            reason_code=outcome.reason_code,
            evidence_digest=outcome.release_proof_digest,
            retry_after_seconds=None,
        )

    def _authorize_wb(
        self,
        action: Mapping[str, Any],
        request: WbCoreLaneReleaseRequest,
        guard: RuntimeActionGuard,
    ) -> None:
        self._authorize(action, guard)
        expected = (
            action["closure_event_id"],
            action["task_id"],
            derive_wb_core_target_task_id(str(action["task_id"])),
            action["task_revision"],
            self._anchor_pr(action),
            action["outcome"],
            action["closure_event_digest"],
            action["target_id"],
        )
        observed = (
            request.closure_event_id,
            request.task_id,
            request.target_task_id,
            request.task_revision,
            request.anchor_pr,
            request.outcome,
            request.evidence_digest,
            request.target_id,
        )
        if observed != expected:
            raise RuntimeError("wb-core lane release lost its durable closure binding")

    def _authorize(
        self,
        action: Mapping[str, Any],
        guard: RuntimeActionGuard,
    ) -> None:
        guard.checkpoint()
        binding_kind = action.get("binding_kind")
        expected_fields = (
            self._FINAL_ACTION_FIELDS
            if binding_kind == "final_manifest"
            else self._PARKED_ADMISSION_ACTION_FIELDS
            if binding_kind == "parked_admission"
            else frozenset()
        )
        if not expected_fields or set(action) != expected_fields:
            raise RuntimeError("target lane closure action fields are invalid")
        if (
            action.get("schema") != "dev-control-plane/target-lane-closure/v2"
            or action.get("supervisor_generation") != self.fence.generation
            or action.get("target_id") not in {SELF_REPO, WB_CORE_REPOSITORY}
            or action.get("contour") not in {"release:done", "release:production"}
            or action.get("outcome") not in {"completed", "parked"}
        ):
            raise RuntimeError("target lane closure action binding is invalid")
        _assert_registry_fence(self.registry, self.fence)
        task = self.registry.get_task(str(action["task_id"]))
        workstream = self.registry.get_workstream(str(action["workstream_id"]))
        if (
            task is None
            or workstream is None
            or workstream.task_id != task.task_id
            or task.revision != action["task_revision"]
            or workstream.revision != action["workstream_revision"]
            or (action["outcome"] == "parked") != (task.state == "parked")
        ):
            raise RuntimeError("target lane closure current revision/outcome changed")
        passport = task_passport_from_mapping(task.passport)
        targets = tuple(
            item.removeprefix("target:")
            for item in passport.resources
            if item.startswith("target:")
        )
        lanes = tuple(
            item.removeprefix("release-lane:")
            for item in passport.resources
            if item.startswith("release-lane:")
        )
        if (
            passport.contour != action["contour"]
            or targets != (action["target_id"],)
            or lanes != (action["logical_lane_id"],)
        ):
            raise RuntimeError("target lane closure current Passport changed")
        manifest = passport.release_manifest
        if binding_kind == "final_manifest":
            if (
                manifest is None
                or manifest.logical_lane_id != action["logical_lane_id"]
                or tuple(manifest.pr_identities)
                != tuple(action["ordered_pr_identities"])
                or manifest.pr_identities[0] != action["anchor_pr_identity"]
                or contract_digest(manifest) != action["release_manifest_digest"]
            ):
                raise RuntimeError("target lane final manifest binding changed")
        else:
            if (
                manifest is not None
                or action["outcome"] != "parked"
                or action["target_id"] != WB_CORE_REPOSITORY
            ):
                raise RuntimeError(
                    "partial target lane binding is only valid for a parked wb-core task without a final manifest"
                )
            self._validate_parked_admission(action)
        require_passport_action(passport, "target_lane_release")
        if action["target_id"] == WB_CORE_REPOSITORY:
            require_passport_action(passport, "wb_github_command")
        source = self.registry.get_event(str(action["closure_event_id"]))
        if (
            source is None
            or source.get("event_id") != action["closure_event_id"]
            or source.get("event_type") != action["closure_event_type"]
            or source.get("task_id") != action["task_id"]
            or source.get("workstream_id") != action["workstream_id"]
            or _sha256_mapping(
                {
                    "event_id": source.get("event_id"),
                    "event_type": source.get("event_type"),
                    "payload": source.get("payload"),
                }
            )
            != action["closure_event_digest"]
        ):
            raise RuntimeError("target lane closure durable source changed")
        if action["outcome"] == "completed":
            if (
                source.get("event_type") != "technical_terminal"
                or source.get("payload", {}).get("closure_barrier") is not True
            ):
                raise RuntimeError("target lane closure barrier is not proven")
        elif source.get("event_type") == "release_stalled":
            if source.get("payload", {}).get("status") != "parked":
                raise RuntimeError("target lane parked release proof changed")
        elif source.get("event_type") == "incident_policy":
            if source.get("payload", {}).get("status") not in {
                "parked",
                "ambiguous_turn_parked",
                "missing_verified_checkpoint",
                "application_failed_fail_closed",
                "arbiter_failed_fail_closed",
                "parked_fail_closed",
                "human_gate",
            }:
                raise RuntimeError("target lane parked incident proof changed")
        else:
            raise RuntimeError("target lane parked source is invalid")

    def _anchor_pr(self, action: Mapping[str, Any]) -> int:
        if action.get("binding_kind") == "final_manifest":
            match = _WB_CORE_PR_IDENTITY_RE.fullmatch(
                str(action.get("anchor_pr_identity") or "")
            )
            if match is None:
                raise RuntimeError("wb-core target lane anchor identity is malformed")
            return int(match.group("number"))
        raw = _mapping(action, "parked_admission")
        binding = wb_core_admission_binding_from_mapping(
            _mapping(raw, "admission_binding")
        )
        return binding.owner_pr

    def _validate_parked_admission(self, action: Mapping[str, Any]) -> None:
        raw = _mapping(action, "parked_admission")
        if set(raw) != self._PARKED_ADMISSION_FIELDS:
            raise RuntimeError("parked target lane admission fields are invalid")
        if (
            raw.get("schema") != PARKED_TARGET_LANE_ADMISSION_SCHEMA
            or raw.get("target_adapter") != WB_CORE_TARGET_ADAPTER
        ):
            raise RuntimeError("parked target lane admission schema is invalid")
        candidate_id = raw.get("candidate_id")
        release_action_event_id = raw.get("release_action_event_id")
        observation_event_id = raw.get("observation_event_id")
        for name, value in (
            ("candidate_id", candidate_id),
            ("release_action_event_id", release_action_event_id),
            ("observation_event_id", observation_event_id),
        ):
            if (
                not isinstance(value, str)
                or not value
                or len(value) > 300
                or any(character.isspace() for character in value)
            ):
                raise RuntimeError(f"parked target lane {name} is invalid")
        pr_number = raw.get("pr_number")
        if isinstance(pr_number, bool) or not isinstance(pr_number, int) or pr_number < 1:
            raise RuntimeError("parked target lane PR number is invalid")
        admission_task_revision = raw.get("admission_task_revision")
        admission_workstream_revision = raw.get("admission_workstream_revision")
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 1
            for value in (admission_task_revision, admission_workstream_revision)
        ) or (
            admission_task_revision > int(action["task_revision"])
            or admission_workstream_revision > int(action["workstream_revision"])
        ):
            raise RuntimeError("parked target lane historical revisions are invalid")
        expected_head = raw.get("expected_head_sha")
        observation_digest = raw.get("observation_event_digest")
        if not isinstance(expected_head, str) or not re.fullmatch(r"[0-9a-f]{40}", expected_head):
            raise RuntimeError("parked target lane head is invalid")
        if not isinstance(observation_digest, str) or not re.fullmatch(
            r"[0-9a-f]{64}", observation_digest
        ):
            raise RuntimeError("parked target lane observation digest is invalid")
        try:
            binding = wb_core_admission_binding_from_mapping(
                _mapping(raw, "admission_binding")
            )
        except (TypeError, ValueError) as exc:
            raise RuntimeError("parked target lane admission proof is malformed") from exc
        if (
            binding.target_id != WB_CORE_REPOSITORY
            or binding.pr_number != pr_number
            or binding.head_sha != expected_head
            or binding.target_task_id
            != derive_wb_core_target_task_id(str(action["task_id"]))
            or binding.task_revision != admission_task_revision
        ):
            raise RuntimeError("parked target lane admission proof is cross-bound")

        observation_event = self.registry.get_event(str(observation_event_id))
        if (
            observation_event is None
            or observation_event.get("event_type") != "release_action_observed"
            or observation_event.get("task_id") != action["task_id"]
            or observation_event.get("workstream_id") != action["workstream_id"]
            or _sha256_mapping(
                {
                    "event_id": observation_event.get("event_id"),
                    "event_type": observation_event.get("event_type"),
                    "payload": observation_event.get("payload"),
                }
            )
            != observation_digest
        ):
            raise RuntimeError("parked target lane admission observation changed")
        observation_payload = observation_event.get("payload")
        if not isinstance(observation_payload, Mapping):
            raise RuntimeError("parked target lane observation payload is invalid")
        observation = observation_payload.get("observation")
        if not isinstance(observation, Mapping):
            raise RuntimeError("parked target lane observation receipt is invalid")
        if (
            observation_payload.get("target_adapter") != WB_CORE_TARGET_ADAPTER
            or observation_payload.get("release_action_event_id")
            != release_action_event_id
            or observation.get("status") not in {"admitted", "waiting_release"}
            or observation.get("candidate_id") != candidate_id
            or observation.get("task_id") != action["task_id"]
            or observation.get("workstream_id") != action["workstream_id"]
            or observation.get("task_revision") != admission_task_revision
            or observation.get("workstream_revision")
            != admission_workstream_revision
            or observation.get("expected_head_sha") != expected_head
            or observation.get("observed_head_sha") != expected_head
            or observation.get("admission_binding") != dict(_mapping(raw, "admission_binding"))
            or f"admission:sha256:{binding.proof_digest}"
            not in tuple(observation.get("evidence") or ())
        ):
            raise RuntimeError("parked target lane observation is not exact admission proof")

        records = tuple(
            item
            for item in self.registry.list_outbox_records(kinds=("release_action",))
            if item.get("event_id") == release_action_event_id
        )
        if len(records) != 1:
            raise RuntimeError("parked target lane release action binding is missing")
        action_payload = records[0].get("payload")
        if not isinstance(action_payload, Mapping):
            raise RuntimeError("parked target lane release action payload is invalid")
        candidate = action_payload.get("candidate")
        release_candidate = action_payload.get("release_candidate")
        if not isinstance(candidate, Mapping) or not isinstance(
            release_candidate, Mapping
        ):
            raise RuntimeError("parked target lane candidate binding is invalid")
        if (
            action_payload.get("target_adapter") != WB_CORE_TARGET_ADAPTER
            or candidate.get("candidate_id") != candidate_id
            or candidate.get("task_id") != action["task_id"]
            or candidate.get("workstream_id") != action["workstream_id"]
            or candidate.get("task_revision") != admission_task_revision
            or candidate.get("workstream_revision")
            != admission_workstream_revision
            or candidate.get("target_id") != WB_CORE_REPOSITORY
            or candidate.get("logical_lane_id") != action["logical_lane_id"]
            or candidate.get("pr_head_sha") != expected_head
            or release_candidate.get("repo") != WB_CORE_REPOSITORY
            or release_candidate.get("pr_number") != pr_number
            or release_candidate.get("expected_head_sha") != expected_head
            or release_candidate.get("task_id") != action["task_id"]
            or release_candidate.get("workstream_id") != action["workstream_id"]
            or release_candidate.get("revision") != admission_task_revision
        ):
            raise RuntimeError("parked target lane candidate/admission binding changed")

    def _receipt(
        self,
        action: Mapping[str, Any],
        *,
        status: str,
        reason_code: str,
        evidence_digest: str,
        retry_after_seconds: float | None,
    ) -> Mapping[str, Any]:
        return {
            "schema": "dev-control-plane/target-lane-closure-receipt/v2",
            "status": status,
            "closure_id": action["closure_id"],
            "supervisor_generation": action["supervisor_generation"],
            "task_id": action["task_id"],
            "task_revision": action["task_revision"],
            "workstream_id": action["workstream_id"],
            "workstream_revision": action["workstream_revision"],
            "target_id": action["target_id"],
            "logical_lane_id": action["logical_lane_id"],
            "outcome": action["outcome"],
            "closure_event_id": action["closure_event_id"],
            "closure_event_digest": action["closure_event_digest"],
            "reason_code": reason_code,
            "evidence_digest": evidence_digest,
            "retry_after_seconds": retry_after_seconds,
            "observed_at": datetime.now(timezone.utc).isoformat().replace(
                "+00:00", "Z"
            ),
        }


class _SelfHostedReleaseExecutor:
    """Mechanical self-repo GitHub + exact hosted deploy-runner adapter."""

    def __init__(
        self,
        *,
        registry: SupervisorRegistry,
        workspace_root: Path,
        projection_key_file: Path,
        github: Any | None = None,
    ) -> None:
        self.registry = registry
        self.workspace_root = workspace_root
        self.projection_key_file = projection_key_file
        self.github = github or GitHubClient(gh_binary=_gh_binary())

    def __call__(self, payload: Mapping[str, Any], guard: RuntimeActionGuard) -> Mapping[str, Any]:
        target_adapter = str(payload.get("target_adapter") or "")
        if target_adapter != SELF_HOSTED_ADAPTER:
            raise RuntimeError("release target has no registered local actuator")
        raw = _mapping(payload, "release_candidate")
        candidate = ReleaseTrainCandidate(
            lane_id=str(raw["lane_id"]),
            task_id=str(raw["task_id"]),
            workstream_id=str(raw["workstream_id"]),
            revision=int(raw["revision"]),
            repo=str(raw["repo"]),
            pr_number=int(raw["pr_number"]),
            expected_head_sha=str(raw["expected_head_sha"]),
            base_ref=str(raw["base_ref"]),
            required_checks=tuple(raw["required_checks"]),
            declared_files=tuple(raw["declared_files"]),
            resources=tuple(raw["resources"]),
            multi_pr=bool(raw["multi_pr"]),
        )
        if (
            candidate.repo != SELF_REPO
            or candidate.required_checks != ("v2-suite", "self-closure")
        ):
            raise RuntimeError("self-hosted adapter refuses a target repository")
        scheduler = _mapping(payload, "candidate")
        passport = self._current_passport(scheduler, candidate)
        passport_digest = contract_digest(passport)
        if _passport_has_no_auto_merge(passport):
            raise RuntimeError("current Task Passport contains NO_AUTO_MERGE")
        for action in sorted(required_release_actions(passport.contour, SELF_REPO)):
            require_passport_action(passport, action)

        def exact_fence(stage: str, _candidate: ReleaseTrainCandidate) -> None:
            guard.checkpoint()
            current = self._current_passport(scheduler, candidate)
            if contract_digest(current) != passport_digest:
                raise RuntimeError("self release Passport changed at mutation boundary")
            if stage == "before_github_merge":
                require_passport_action(current, "self_merge")
                governance_truth = self.github.read_pr(
                    repo=candidate.repo,
                    pr_number=candidate.pr_number,
                )
                guard.checkpoint()
                protected = tuple(
                    path
                    for path in governance_truth.files
                    if _is_protected_self_governance_path(path)
                )
                if (
                    governance_truth.state != "OPEN"
                    or governance_truth.head_sha != candidate.expected_head_sha
                    or governance_truth.base_ref != candidate.base_ref
                    or protected
                ):
                    if protected:
                        raise SecurityPermissionChangeRequiresOwner(
                            expected_head_sha=candidate.expected_head_sha,
                            evidence=_protected_governance_evidence(
                                candidate.expected_head_sha,
                                protected,
                            ),
                        )
                    raise RuntimeError(
                        "self governance readback changed before merge"
                    )
            elif stage == "before_deploy":
                require_passport_action(current, "self_hosted_deploy")
                governance_truth = self.github.read_pr(
                    repo=candidate.repo,
                    pr_number=candidate.pr_number,
                )
                guard.checkpoint()
                protected = tuple(
                    path
                    for path in governance_truth.files
                    if _is_protected_self_governance_path(path)
                )
                if protected:
                    raise SecurityPermissionChangeRequiresOwner(
                        expected_head_sha=candidate.expected_head_sha,
                        evidence=_protected_governance_evidence(
                            candidate.expected_head_sha,
                            protected,
                        ),
                    )
                if (
                    governance_truth.state != "MERGED"
                    or governance_truth.head_sha != candidate.expected_head_sha
                    or governance_truth.base_ref != candidate.base_ref
                ):
                    raise RuntimeError(
                        "self governance readback changed before deploy"
                    )

        train = MechanicalReleaseTrain(
            self.github,
            fence_guard=exact_fence,
            deploy_adapters={SELF_HOSTED_ADAPTER: self._deploy},
            deploy_readback_adapters={SELF_HOSTED_ADAPTER: self._deploy_readback},
            verify_adapters={SELF_HOSTED_ADAPTER: self._verify},
        )
        if passport.contour == "release:done":
            pr_url, merge_sha = self._execute_repo_only(
                train,
                candidate,
                exact_fence=exact_fence,
            )
            deployed_identity = None
            verification_identity = f"github-merged-readback:{merge_sha}"
        elif passport.contour == "release:production":
            result = train.execute(candidate, target_adapter=SELF_HOSTED_ADAPTER)
            if (
                result.status != "passed"
                or not result.merge_commit_sha
                or not result.deployed_identity
            ):
                raise RuntimeError("mechanical self-hosted release did not pass")
            pr_url = result.pr_url
            merge_sha = result.merge_commit_sha
            deployed_identity = result.deployed_identity
            verification = result.verification or {}
            verification_identity = str(
                verification.get("identity") or "hosted-probes-passed"
            )
        else:
            raise RuntimeError("self release contour is not registered")
        return {
            "schema": "dev-control-plane/release-action-receipt/v2",
            "status": "passed",
            "candidate_id": scheduler["candidate_id"],
            "task_id": scheduler["task_id"],
            "workstream_id": scheduler["workstream_id"],
            "task_revision": scheduler["task_revision"],
            "workstream_revision": scheduler["workstream_revision"],
            "pr_head_sha": scheduler["pr_head_sha"],
            "pr_url": pr_url,
            "merge_sha": merge_sha,
            "contour": passport.contour,
            "deploy_identity": deployed_identity,
            "verification_identity": verification_identity,
            "admission_binding": None,
            "completed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }

    def _current_passport(
        self,
        scheduler: Mapping[str, Any],
        candidate: ReleaseTrainCandidate,
    ) -> Any:
        task = self.registry.get_task(candidate.task_id)
        workstream = self.registry.get_workstream(candidate.workstream_id)
        if (
            task is None
            or workstream is None
            or workstream.task_id != candidate.task_id
            or task.revision != candidate.revision
            or workstream.revision != scheduler.get("workstream_revision")
            or task.state in {"accepted", "parked"}
            or workstream.state != "waiting_release"
            or scheduler.get("task_id") != candidate.task_id
            or scheduler.get("workstream_id") != candidate.workstream_id
            or scheduler.get("task_revision") != candidate.revision
            or scheduler.get("pr_head_sha") != candidate.expected_head_sha
            or scheduler.get("target_id") != SELF_REPO
        ):
            raise RuntimeError("self release action lost its current revision binding")
        passport = task_passport_from_mapping(task.passport)
        targets = tuple(
            item.removeprefix("target:")
            for item in passport.resources
            if item.startswith("target:")
        )
        if (
            passport.task_id != candidate.task_id
            or passport.revision != candidate.revision
            or targets != (SELF_REPO,)
            or passport.contour not in {"release:done", "release:production"}
        ):
            raise RuntimeError("self release current Passport target/contour is invalid")
        return passport

    def _execute_repo_only(
        self,
        train: MechanicalReleaseTrain,
        candidate: ReleaseTrainCandidate,
        *,
        exact_fence: Callable[[str, ReleaseTrainCandidate], None],
    ) -> tuple[str, str]:
        exact_fence("before_github_readback", candidate)
        admission = train.admit(candidate)
        exact_fence("after_github_readback", candidate)
        if not admission.allowed:
            raise RuntimeError("mechanical self-repo release admission failed")
        truth = admission.truth
        if truth.state != "MERGED":
            exact_fence("before_github_merge", candidate)
            self.github.merge_pr(
                repo=candidate.repo,
                pr_number=candidate.pr_number,
                expected_head_sha=candidate.expected_head_sha,
            )
            exact_fence("after_github_merge", candidate)
            admission = train.admit(candidate)
            exact_fence("after_github_merge_readback", candidate)
            if not admission.allowed:
                raise RuntimeError("self-repo merge readback failed immutable admission")
            truth = admission.truth
        if truth.state != "MERGED" or not truth.merge_commit_sha:
            raise RuntimeError("self-repo release did not prove exact MERGED state")
        return truth.url, truth.merge_commit_sha

    def _deploy(self, candidate: ReleaseTrainCandidate, merge_sha: str) -> str:
        source = self._exact_source(merge_sha)
        runner = source / "apps" / "dev_control_plane_hosted_deploy.py"
        commands = (
            ("print-plan",),
            ("validate", "--projection-key-file", str(self.projection_key_file)),
            ("deploy", "--dry-run", "--projection-key-file", str(self.projection_key_file)),
            ("deploy", "--live", "--projection-key-file", str(self.projection_key_file)),
        )
        last: Mapping[str, Any] = {}
        for arguments in commands:
            last = _run_json([sys.executable, str(runner), *arguments], cwd=source, timeout=1_800)
        if last.get("status") != "deployed" or last.get("release_sha") != merge_sha:
            raise RuntimeError("hosted deploy runner did not attest the exact merge SHA")
        return f"hosted-release-v1:{HOSTED_TARGET}:{HOSTED_DOMAIN}:{merge_sha}"

    def _deploy_readback(self, candidate: ReleaseTrainCandidate, merge_sha: str) -> str | None:
        source = self._exact_source(merge_sha)
        runner = source / "apps" / "dev_control_plane_hosted_deploy.py"
        result = _run_json([sys.executable, str(runner), "loopback-probe"], cwd=source, timeout=180)
        health = result.get("health")
        if (
            result.get("status") == "passed"
            and isinstance(health, Mapping)
            and health.get("release_sha") == merge_sha
        ):
            return f"hosted-release-v1:{HOSTED_TARGET}:{HOSTED_DOMAIN}:{merge_sha}"
        return None

    def _verify(self, candidate: ReleaseTrainCandidate, deployed_identity: str) -> Mapping[str, Any]:
        merge_sha = deployed_identity.rsplit(":", 1)[-1]
        source = self._exact_source(merge_sha)
        runner = source / "apps" / "dev_control_plane_hosted_deploy.py"
        for arguments in (("loopback-probe",), ("public-probe",), ("webcore-probe",)):
            result = _run_json([sys.executable, str(runner), *arguments], cwd=source, timeout=180)
            if result.get("status") != "passed":
                raise RuntimeError("hosted post-deploy probe failed")
        return {"status": "passed", "identity": "hosted-readonly-probes:" + merge_sha}

    def _exact_source(self, merge_sha: str) -> Path:
        if len(merge_sha) != 40 or any(char not in "0123456789abcdef" for char in merge_sha):
            raise RuntimeError("release merge SHA is invalid")
        sources = self.workspace_root / "self_release_sources"
        sources.mkdir(parents=True, exist_ok=True, mode=0o700)
        sources_metadata = sources.lstat()
        if (
            not stat.S_ISDIR(sources_metadata.st_mode)
            or stat.S_ISLNK(sources_metadata.st_mode)
            or sources_metadata.st_uid != os.geteuid()
            or stat.S_IMODE(sources_metadata.st_mode) & 0o077
        ):
            raise RuntimeError("self release source root is not private")
        destination = sources / merge_sha
        if destination.is_dir():
            observed = _run_text(["/usr/bin/git", "rev-parse", "HEAD"], cwd=destination).strip()
            if observed == merge_sha:
                return destination
            raise RuntimeError("cached release source identity changed")
        temporary = Path(tempfile.mkdtemp(prefix="source-", dir=sources))
        try:
            _run_text(
                ["/usr/bin/git", "clone", "--no-checkout", "https://github.com/orenvlad-ai/dev-control-plane.git", str(temporary)],
                cwd=sources,
                timeout=300,
            )
            _run_text(["/usr/bin/git", "fetch", "--quiet", "origin", "main"], cwd=temporary, timeout=180)
            origin_main = _run_text(["/usr/bin/git", "rev-parse", "origin/main"], cwd=temporary).strip()
            if origin_main != merge_sha:
                raise RuntimeError("merged release is not exact origin/main")
            _run_text(["/usr/bin/git", "checkout", "--quiet", "--detach", merge_sha], cwd=temporary)
            if _run_text(["/usr/bin/git", "status", "--porcelain"], cwd=temporary).strip():
                raise RuntimeError("release source is dirty")
            temporary.replace(destination)
        except Exception:
            shutil.rmtree(temporary, ignore_errors=True)
            raise
        return destination


class _WbCoreManagedQueueReader:
    """Serialized exact-main source and read-only target queue command."""

    def __init__(
        self,
        *,
        workspace_root: Path,
        gh_binary: str,
        source_provider: Callable[[], Path] | None = None,
        command_runner: Callable[..., str] | None = None,
    ) -> None:
        self.workspace_root = workspace_root.expanduser().resolve()
        self.destination = self.workspace_root / "wb_core_release_train_main"
        self.gh_binary = str(Path(gh_binary).resolve())
        if (
            not Path(self.gh_binary).is_file()
            or not os.access(self.gh_binary, os.X_OK)
            or any(character.isspace() for character in self.gh_binary)
        ):
            raise RuntimeError("wb-core queue reader requires an allowlisted gh binary")
        self.source_provider = source_provider
        self.command_runner = command_runner or _run_text
        self._lock = threading.Lock()

    def __call__(self, release_proof_prs: Sequence[int]) -> Mapping[str, Any]:
        proof_prs: list[int] = []
        for value in release_proof_prs:
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise RuntimeError("wb-core release proof PR identity is invalid")
            if value not in proof_prs:
                proof_prs.append(value)
            if len(proof_prs) > 32:
                raise RuntimeError("wb-core release proof request is oversized")
        with self._lock:
            source = (
                self.source_provider().resolve()
                if self.source_provider is not None
                else self._prepare_source()
            )
            command = self._queue_command(source, proof_prs)
            raw = self.command_runner(
                command,
                cwd=source,
                timeout=180,
                env=self._queue_environment(),
                max_output_bytes=_WB_CORE_QUEUE_MAX_BYTES,
            )
        if not isinstance(raw, str):
            raise RuntimeError("wb-core queue command returned non-text output")
        try:
            if len(raw.encode("utf-8")) > _WB_CORE_QUEUE_MAX_BYTES:
                raise RuntimeError("wb-core queue command returned oversized output")
            payload = json.loads(raw)
        except (json.JSONDecodeError, UnicodeError) as exc:
            raise RuntimeError("wb-core queue command returned invalid JSON") from exc
        if not isinstance(payload, Mapping):
            raise RuntimeError("wb-core queue command returned a non-object")
        return dict(payload)

    def _prepare_source(self) -> Path:
        self.workspace_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        root_metadata = self.workspace_root.lstat()
        if (
            stat.S_ISLNK(root_metadata.st_mode)
            or not stat.S_ISDIR(root_metadata.st_mode)
            or root_metadata.st_uid != os.geteuid()
            or stat.S_IMODE(root_metadata.st_mode) & 0o077
        ):
            raise RuntimeError("managed workspace root is not a real directory")
        created = False
        if self.destination.exists() or self.destination.is_symlink():
            metadata = self.destination.lstat()
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                raise RuntimeError("wb-core managed source is not a real directory")
            source = self.destination
        else:
            temporary = Path(
                tempfile.mkdtemp(prefix=".wb-core-main-", dir=self.workspace_root)
            )
            try:
                self._git(
                    [
                        "clone",
                        "--quiet",
                        "--no-checkout",
                        "--origin",
                        "origin",
                        "--",
                        WB_CORE_REMOTE,
                        str(temporary),
                    ],
                    cwd=self.workspace_root,
                    timeout=300,
                )
                self._validate_repository(temporary)
                temporary.replace(self.destination)
                source = self.destination
                created = True
            except Exception:
                shutil.rmtree(temporary, ignore_errors=True)
                raise

        self._validate_repository(source)
        if not created:
            if self._git(["status", "--porcelain"], cwd=source).strip():
                raise RuntimeError("wb-core managed source is dirty")
            if self._git(["branch", "--show-current"], cwd=source).strip():
                raise RuntimeError("wb-core managed source is not detached")
        self._git(
            [
                "fetch",
                "--quiet",
                "--no-tags",
                "--force",
                "origin",
                "refs/heads/main:refs/remotes/origin/main",
            ],
            cwd=source,
            timeout=300,
        )
        origin_main = self._git(
            ["rev-parse", "--verify", "refs/remotes/origin/main^{commit}"],
            cwd=source,
        ).strip()
        if len(origin_main) != 40 or any(
            character not in "0123456789abcdef" for character in origin_main
        ):
            raise RuntimeError("wb-core origin/main identity is invalid")
        self._git(
            ["checkout", "--quiet", "--detach", "--force", origin_main],
            cwd=source,
            timeout=180,
        )
        if (
            self._git(["rev-parse", "HEAD"], cwd=source).strip() != origin_main
            or self._git(["status", "--porcelain"], cwd=source).strip()
            or self._git(["branch", "--show-current"], cwd=source).strip()
        ):
            raise RuntimeError("wb-core managed source failed exact-main checkout")
        return source

    def _validate_repository(self, source: Path) -> None:
        metadata = source.lstat()
        if (
            source.resolve() != source
            or stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISDIR(metadata.st_mode)
            or not (source / ".git").is_dir()
        ):
            raise RuntimeError("wb-core managed source boundary is invalid")
        remotes = tuple(
            item
            for item in self._git(["remote"], cwd=source).splitlines()
            if item
        )
        urls = tuple(
            item
            for item in self._git(
                ["remote", "get-url", "--all", "origin"], cwd=source
            ).splitlines()
            if item
        )
        if remotes != ("origin",) or urls != (WB_CORE_REMOTE,):
            raise RuntimeError("wb-core managed source remote is not canonical HTTPS")
        local_config = self._git(["config", "--local", "--list"], cwd=source)
        forbidden = (
            "url.",
            "include.",
            "includeif.",
            "credential.",
            "protocol.",
            "core.hookspath=",
            "core.sshcommand=",
            "remote.origin.proxy=",
            "remote.origin.uploadpack=",
            "remote.origin.receivepack=",
        )
        if any(line.casefold().startswith(forbidden) for line in local_config.splitlines()):
            raise RuntimeError("wb-core managed source contains unsafe local Git config")

    def _queue_command(self, source: Path, proof_prs: Sequence[int]) -> list[str]:
        runner = source / "apps" / "github_release_train.py"
        try:
            metadata = runner.lstat()
        except OSError as exc:
            raise RuntimeError("wb-core trusted-main queue runner is unavailable") from exc
        if (
            runner.resolve().parent.parent != source
            or stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISREG(metadata.st_mode)
        ):
            raise RuntimeError("wb-core trusted-main queue runner boundary is invalid")
        command = [sys.executable, str(runner), "queue-status"]
        for number in proof_prs:
            command.extend(("--release-proof-pr", str(number)))
        return command

    def _git(
        self,
        arguments: list[str],
        *,
        cwd: Path,
        timeout: float = 120,
    ) -> str:
        command = [
            "/usr/bin/git",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "credential.helper=",
            "-c",
            f"credential.helper=!{self.gh_binary} auth git-credential",
            "-c",
            "http.followRedirects=false",
            *arguments,
        ]
        return self.command_runner(
            command,
            cwd=cwd,
            timeout=timeout,
            env=self._git_environment(),
            max_output_bytes=2_000_000,
        )

    def _git_environment(self) -> dict[str, str]:
        environment = dict(os.environ)
        for key in tuple(environment):
            if key.startswith("GIT_CONFIG_") or key in {
                "GIT_ALLOW_PROTOCOL",
                "GIT_PROTOCOL_FROM_USER",
                "GIT_SSH",
                "GIT_SSH_COMMAND",
                "GIT_PROXY_COMMAND",
            }:
                environment.pop(key, None)
        environment.update(
            {
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": "/dev/null",
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_PROTOCOL_FROM_USER": "0",
                "GIT_ALLOW_PROTOCOL": "https",
            }
        )
        return environment

    def _queue_environment(self) -> dict[str, str]:
        environment = dict(os.environ)
        for key in (
            "GITHUB_TOKEN",
            "GH_TOKEN",
            "PYTHONHOME",
            "PYTHONPATH",
        ):
            environment.pop(key, None)
        environment.update(
            {
                "GITHUB_REPOSITORY": WB_CORE_REPOSITORY,
                "PYTHONDONTWRITEBYTECODE": "1",
                "PATH": f"{Path(self.gh_binary).parent}:/usr/bin:/bin",
            }
        )
        return environment


def _assert_registry_fence(registry: SupervisorRegistry, fence: Any) -> None:
    current = registry.current_generation()
    if (
        current.get("generation") != fence.generation
        or current.get("owner_id") != fence.owner_id
        or float(current.get("expires_at") or 0) <= time.time()
    ):
        raise RuntimeError("wb-core readback lost the Supervisor generation fence")


def _publisher(args: argparse.Namespace, state_dir: Path) -> ProjectionPublisher | None:
    key_file = _projection_key_path(args, state_dir)
    if not key_file.is_file():
        return None
    return ProjectionPublisher(endpoint=PRODUCTION_PROJECTION_ENDPOINT, key_file=str(key_file))


def _projection_key_path(args: argparse.Namespace, state_dir: Path) -> Path:
    explicit = getattr(args, "projection_key_file", None)
    return Path(explicit).expanduser().resolve() if explicit else state_dir.parent / "secrets" / "projection_hmac.key"


def _activation_identity(args: argparse.Namespace) -> Mapping[str, Any]:
    release_sha = str(args.release_sha)
    if len(release_sha) != 40 or any(character not in "0123456789abcdef" for character in release_sha):
        raise RuntimeError("runtime release SHA is invalid")
    if ROOT.name != release_sha:
        raise RuntimeError("runtime entrypoint is not inside the exact immutable release SHA")
    configured_nonce = Path(args.activation_nonce_file).expanduser()
    if not configured_nonce.is_absolute():
        raise RuntimeError("activation nonce path must be absolute")
    nonce = _read_activation_nonce(configured_nonce)
    return {
        "schema": "dev-control-plane/runtime-activation/v2",
        "release_sha": release_sha,
        "activation_nonce_sha256": hashlib.sha256(nonce).hexdigest(),
        "pid": os.getpid(),
        "python_executable": str(Path(sys.executable).resolve()),
        "entrypoint": str(Path(__file__).resolve()),
        "bind_host": args.host,
        "bind_port": args.port,
    }


def _read_activation_nonce(configured_nonce: Path) -> bytes:
    try:
        metadata = configured_nonce.lstat()
    except OSError as exc:
        raise RuntimeError("activation nonce file is unavailable") from exc
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_nlink != 1
        or not 32 <= metadata.st_size <= 4_096
    ):
        raise RuntimeError("activation nonce file is missing or not private")
    nonce_path = configured_nonce.resolve(strict=True)
    if nonce_path != configured_nonce.absolute():
        raise RuntimeError("activation nonce path traverses a symlink")
    descriptor = -1
    try:
        descriptor = os.open(nonce_path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        opened = os.fstat(descriptor)
        nonce = os.read(descriptor, 4_097)
    except OSError as exc:
        raise RuntimeError("activation nonce file could not be read safely") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    try:
        repeated = nonce_path.lstat()
    except OSError as exc:
        raise RuntimeError("activation nonce file changed while starting") from exc
    expected_identity = (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_uid,
        stat.S_IMODE(metadata.st_mode),
        metadata.st_nlink,
    )
    if (
        not stat.S_ISREG(opened.st_mode)
        or len(nonce) != metadata.st_size
        or (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
            opened.st_uid,
            stat.S_IMODE(opened.st_mode),
            opened.st_nlink,
        )
        != expected_identity
        or (
            repeated.st_dev,
            repeated.st_ino,
            repeated.st_size,
            repeated.st_uid,
            stat.S_IMODE(repeated.st_mode),
            repeated.st_nlink,
        )
        != expected_identity
    ):
        raise RuntimeError("activation nonce file changed while starting")
    return nonce


def _gh_binary() -> str:
    for candidate in (Path("/opt/homebrew/bin/gh"), Path("/usr/local/bin/gh"), Path("/usr/bin/gh")):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    raise RuntimeError("GitHub CLI is unavailable at an allowlisted absolute path")


def _run_text(
    command: list[str],
    *,
    cwd: Path,
    timeout: float = 120.0,
    env: Mapping[str, str] | None = None,
    max_output_bytes: int = 1_000_000,
) -> str:
    completed = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=None if env is None else dict(env),
    )
    if completed.returncode != 0:
        raise RuntimeError(f"registered command failed with exit {completed.returncode}")
    try:
        size = len(completed.stdout.encode("utf-8"))
    except UnicodeError as exc:
        raise RuntimeError("registered command returned invalid text") from exc
    if size > max_output_bytes:
        raise RuntimeError("registered command returned oversized output")
    return completed.stdout


def _run_json(command: list[str], *, cwd: Path, timeout: float) -> Mapping[str, Any]:
    payload = _run_json_value(command, cwd=cwd, timeout=timeout)
    if not isinstance(payload, Mapping):
        raise RuntimeError("registered runner returned a non-object receipt")
    return payload


def _run_json_value(command: list[str], *, cwd: Path, timeout: float) -> Any:
    raw = _run_text(command, cwd=cwd, timeout=timeout)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("registered runner returned invalid JSON") from exc
    return payload


def _mapping(value: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    item = value.get(key)
    if not isinstance(item, Mapping):
        raise RuntimeError(f"{key} must be an object")
    return item


def _passport_has_no_auto_merge(passport: Any) -> bool:
    text_fields = (
        passport.title,
        passport.objective,
        passport.expected_result,
        *passport.included_scope,
        *passport.excluded_scope,
        *passport.constraints,
        *passport.acceptance,
        *passport.closure,
        *passport.autonomy.allowed_actions,
        *passport.autonomy.prohibited_actions,
    )
    return any("NO_AUTO_MERGE" in item.upper() for item in text_fields)


def _passport_release_actions_ready(passport: Any, target_id: str) -> bool:
    try:
        for action in sorted(required_release_actions(passport.contour, target_id)):
            require_passport_action(passport, action)
    except ValueError:
        return False
    return True


def _is_protected_self_governance_path(path: str) -> bool:
    normalized = str(path).replace("\\", "/")
    if (
        not normalized
        or normalized.startswith("/")
        or ".." in Path(normalized).parts
    ):
        return True
    if normalized == "AGENTS.md" or normalized.startswith(".github/"):
        return True
    # Every importable source path is authority-reachable.  Protect the whole
    # tree, including a newly added top-level module/package that could shadow
    # a stdlib import after the immutable release prepends ``release/src``.
    if normalized.startswith("src/"):
        return True
    importable_suffixes = (".py", ".pyi", ".pyc", ".so", ".dylib", ".pyd")
    if normalized.endswith(importable_suffixes):
        if normalized.startswith("apps/") and normalized.endswith("_smoke.py"):
            return False
        return True
    if normalized in {
        "pyproject.toml",
        "setup.cfg",
        "requirements.txt",
        "Pipfile",
        "Pipfile.lock",
        "poetry.lock",
    } or normalized.startswith("requirements-"):
        return True
    if (
        normalized in {"sitecustomize.py", "usercustomize.py"}
        or normalized.endswith(".pth")
    ):
        return True
    if normalized.startswith(
        (
            "deploy/examples/systemd/",
            "deploy/examples/reverse-proxy/",
            "configs/target_projects/",
        )
    ):
        return True
    return False


def _protected_governance_evidence(
    head_sha: str,
    paths: Sequence[str],
) -> tuple[str, ...]:
    protected = tuple(sorted(set(str(path) for path in paths)))
    return (
        f"head:{head_sha}",
        *(f"protected-path:{path}" for path in protected[:30]),
    )


def _sha256_mapping(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _read_json(raw_path: str) -> dict[str, Any]:
    path = Path(raw_path).expanduser()
    metadata = path.lstat()
    if path.is_symlink() or not path.is_file() or metadata.st_size > MAX_JSON_BYTES:
        raise ValueError("contract input must be a bounded regular non-symlink file")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("contract input must be a JSON object")
    return payload


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")), flush=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local deterministic Orchestrator v2 Supervisor")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve = subparsers.add_parser("serve", help="run the sole Supervisor generation")
    _state_argument(serve)
    serve.add_argument("--host", default=LOCAL_HOST)
    serve.add_argument("--port", type=int, default=8766)
    serve.add_argument("--interval", type=float, default=10.0)
    serve.add_argument("--worker-poll", type=float, default=1.0)
    serve.add_argument("--projection-key-file")
    serve.add_argument("--workspace-root")
    serve.add_argument("--codex-bin", default=os.environ.get("DEV_CONTROL_PLANE_CODEX_BIN", DEFAULT_DESKTOP_CODEX_BIN))
    serve.add_argument("--release-sha", required=True)
    serve.add_argument("--activation-nonce-file", required=True)

    command = subparsers.add_parser("command", help="send one exact private-socket command")
    _state_argument(command)
    command.add_argument("--name", required=True)
    command.add_argument("--input")
    command.add_argument("--request-id", required=True)
    command.add_argument("--timeout", type=float, default=30.0)

    for name in ("health", "state", "tick"):
        item = subparsers.add_parser(name)
        _state_argument(item)
        item.add_argument("--request-id", required=True)
        item.add_argument("--timeout", type=float, default=30.0)
    return parser


def _state_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--state-dir", required=True)


if __name__ == "__main__":
    raise SystemExit(main())
