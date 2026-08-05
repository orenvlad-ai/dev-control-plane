"""Single-process runtime composition for the local Orchestrator v2 Supervisor.

The deterministic :mod:`dev_control_plane.supervisor` engine deliberately has
no transport or model lifecycle policy.  This module composes that engine into
one daemon process:

* every command mutation enters through a private Unix-domain command socket;
* Codex work is reserved in SQLite before an external App Server call;
* no registry transaction spans an App Server, HTTPS, or delivery wait;
* exact owned threads are resumed after a Supervisor restart; and
* durable receipts make a lost local acknowledgement idempotent.

The loopback HTTP server remains a read-only view. Registered in-process
Release Train and incident adapters are invoked only from fenced durable work.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import socketserver
import stat
import threading
import time
from typing import Any, Callable, Mapping, Sequence

from .codex_app_server import (
    CODEX_APP_SERVER_MODEL,
    CODEX_APP_SERVER_REASONING_EFFORT,
    CodexAmbiguousOutcomeError,
    CodexAppServerClient,
    CodexCheckpoint,
    CodexContractError,
    CodexDisconnectedError,
    CodexIdentityMismatchError,
    CodexProtocolError,
    CodexRequestTimeout,
    CodexStaleGenerationError,
    CodexTerminalEvidence,
    CodexThreadOwnershipError,
    CodexThreadIdentity,
    CodexTurnTimeout,
    CodexTurnResult,
    _parse_contract_json,
    _validated_recovery_items,
    validate_checkpoint_payload,
)
from .curator_delivery import (
    OWNER_ACTION_ATTESTATION_SCHEMA,
    CuratorDelivery,
    DeliveryReceipt,
)
from .incident_policy import (
    CausalFailure,
    HumanGateRequest,
    IncidentContext,
    IncidentState,
    begin_incident_budget,
    escalate_failed_successor,
    observe_same_failure,
    record_arbiter_application,
    record_incident_arbiter_decision,
    record_independent_verification,
    record_successor_proof,
    renew_incident_budget,
    validate_human_gate,
)
from .orchestration_contracts import (
    ArbiterDecision,
    Checkpoint,
    ExecutorIdentity,
    OrchestrationValidationError,
    ReleaseClosureManifest,
    TaskPassport,
    TerminalEvidence,
    contract_digest,
    contract_to_dict,
    arbiter_decision_from_mapping,
    require_passport_action,
    required_release_actions,
    task_passport_from_mapping,
    workstream_from_mapping,
)
from .release_train import ReleaseCandidate as ReleaseTrainCandidate
from .release_scheduler import (
    ReleaseCandidate as SchedulerReleaseCandidate,
    SemanticReleaseCase,
    StaleArbiterDecision,
    revalidate_case_against_candidates,
    validate_arbiter_release_decision,
)
from .supervisor import (
    SupervisorEngine,
    SupervisorError,
    owner_acceptance_from_mapping,
    release_candidate_from_mapping,
)
from .supervisor_registry import (
    LockConflict,
    LockGrant,
    OutboxMessage,
    PREACTIVATION_CAUSAL_REMEDIATION_EXPECTED_OUTPUT_GENERATION,
    PREACTIVATION_CAUSAL_REMEDIATION_PR92_HEAD_SHA,
    PREACTIVATION_CAUSAL_REMEDIATION_PR92_MERGE_SHA,
    PREACTIVATION_CAUSAL_REMEDIATION_SOURCE_EXECUTOR_GENERATION,
    PREACTIVATION_CAUSAL_REMEDIATION_SOURCE_TASK_REVISION,
    PREACTIVATION_CAUSAL_REMEDIATION_SOURCE_WORKSTREAM_GENERATION,
    PREACTIVATION_CAUSAL_REMEDIATION_SOURCE_WORKSTREAM_REVISION,
    PREACTIVATION_CAUSAL_REMEDIATION_STRATEGY_RESOURCE,
    PREACTIVATION_CAUSAL_REMEDIATION_SUCCESSOR_EXECUTOR_GENERATION,
    PREACTIVATION_CAUSAL_REMEDIATION_SUCCESSOR_TASK_REVISION,
    PREACTIVATION_CAUSAL_REMEDIATION_SUCCESSOR_WORKSTREAM_GENERATION,
    PREACTIVATION_ORDINARY_POLICY_OUTBOX_KINDS,
    PREACTIVATION_STRUCTURAL_REPAIR_CANONICAL_TARGET,
    PREACTIVATION_STRUCTURAL_REPAIR_LEGACY_TARGET,
    PREACTIVATION_STRUCTURAL_REPAIR_PREDECESSOR_SHA,
    PREACTIVATION_STRUCTURAL_REPAIR_TASK_ID,
    PREACTIVATION_STRUCTURAL_REPAIR_WORKSTREAM_ID,
    RegistryValidationError,
    StaleGenerationError,
    SupervisorRegistry,
)
from .wb_core_release_adapter import (
    WB_CORE_REPOSITORY,
    WB_CORE_TARGET_ADAPTER,
    derive_wb_core_target_task_id,
    wb_core_admission_binding_from_mapping,
)


COMMAND_CONTRACT = "dev-control-plane/supervisor-command/v2"
RECEIPT_CONTRACT = "dev-control-plane/supervisor-command-receipt/v2"
THREAD_START_SCHEMA = "dev-control-plane/codex-thread-start/v2"
FOLLOWUP_SCHEMA = "dev-control-plane/codex-followup/v2"
SUCCESSOR_SCHEMA = "dev-control-plane/codex-successor-start/v2"
PREACTIVATION_STRUCTURAL_REPAIR_SCHEMA = (
    "dev-control-plane/preactivation-structural-repair/v2"
)
PREACTIVATION_STRUCTURAL_REPAIR_COMPLETION_SCHEMA = (
    "dev-control-plane/preactivation-structural-repair-completion/v2"
)
PREACTIVATION_SUCCESSOR_SCHEMA = (
    "dev-control-plane/codex-preactivation-successor-start/v2"
)
PREACTIVATION_CAUSAL_REMEDIATION_SCHEMA = (
    "dev-control-plane/preactivation-causal-remediation/v3"
)
PREACTIVATION_CAUSAL_READ_SCHEMA = (
    "dev-control-plane/codex-preactivation-causal-read/v3"
)
PREACTIVATION_CAUSAL_ATTESTATION_SCHEMA = (
    "dev-control-plane/preactivation-causal-attestation/v3"
)
PREACTIVATION_CAUSAL_SUCCESSOR_SCHEMA = (
    "dev-control-plane/codex-preactivation-causal-successor-start/v3"
)
PREACTIVATION_CAUSAL_COMPLETION_SCHEMA = (
    "dev-control-plane/preactivation-causal-remediation-completion/v3"
)
PREACTIVATION_CAUSAL_STRATEGY_RESOURCE = (
    "strategy:supervisor-generation-bound-checkpoint-v2"
)
TERMINAL_CONTEXT_SCHEMA = "dev-control-plane/terminal-context/v2"
RELEASE_CANDIDATE_REGISTRATION_SCHEMA = "dev-control-plane/release-candidate-registration/v2"
RELEASE_CANDIDATE_INTAKE_SCHEMA = "dev-control-plane/release-candidate-intake/v2"
RELEASE_CANDIDATE_INTAKE_RESOLUTION_SCHEMA = "dev-control-plane/release-candidate-intake-resolution/v2"
RELEASE_CANDIDATE_ADMISSION_SCHEMA = "dev-control-plane/release-candidate-admission/v2"
TARGET_LANE_CLOSURE_SCHEMA = "dev-control-plane/target-lane-closure/v2"
TARGET_LANE_CLOSURE_RECEIPT_SCHEMA = "dev-control-plane/target-lane-closure-receipt/v2"
INCIDENT_APPLICATION_DISPOSITION_SCHEMA = (
    "dev-control-plane/incident-application-disposition/v2"
)
INCIDENT_TARGET_LANE_DISPATCH_SCHEMA = (
    "dev-control-plane/incident-target-lane-dispatch/v2"
)
TARGET_LANE_INCIDENT_REMEDIATION_SCHEMA = (
    "dev-control-plane/target-lane-incident-remediation/v2"
)
PARKED_TARGET_LANE_ADMISSION_SCHEMA = (
    "dev-control-plane/parked-target-lane-admission/v2"
)
CAUSAL_BINDING_SCHEMA = "dev-control-plane/causal-failure-binding/v2"
MAX_COMMAND_BYTES = 1_000_000
MAX_PROMPT_CHARS = 240_000
DEFAULT_SOCKET_NAME = "supervisor.sock"
DEFAULT_VISIBILITY_TIMEOUT_SECONDS = 45.0
DEFAULT_RETRY_DELAY_SECONDS = 5.0
DEFAULT_DESKTOP_CODEX_BIN = "/Applications/ChatGPT.app/Contents/Resources/codex"
DEFAULT_EXECUTION_LOCK_TTL_SECONDS = 60.0
DEFAULT_RELEASE_RESERVATION_TTL_SECONDS = 300.0
CALL_POLICY_STANDARD = "standard"
CALL_POLICY_SINGLE_ATTEMPT_CANARY = "single_attempt_canary"

_MACHINE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}$")
_CREDENTIAL_RE = re.compile(
    r"(?:Authorization\s*:\s*Bearer\s+\S+|github_pat_[A-Za-z0-9_]{16,}|"
    r"gh[opsu]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{20,}|"
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)",
    re.IGNORECASE,
)


class SupervisorRuntimeError(RuntimeError):
    """A bounded daemon composition or command protocol failure."""


class SupervisorCommandError(SupervisorRuntimeError):
    """A private-socket command is malformed or rejected."""


class SecurityPermissionChangeRequiresOwner(SupervisorRuntimeError):
    """Typed self-release stop for an exact protected controller diff."""

    reason_code = "security_permission_change"
    requested_action = (
        "Authorize this exact head-bound controller/governance change through a new "
        "governed two-phase update."
    )

    def __init__(self, *, expected_head_sha: str, evidence: Sequence[str]) -> None:
        if not isinstance(expected_head_sha, str) or not re.fullmatch(
            r"[0-9a-f]{40}", expected_head_sha
        ):
            raise ValueError("protected controller gate requires an exact head SHA")
        normalized = _bounded_strings(
            "security_permission_change.evidence", evidence, required=True
        )
        super().__init__("security_permission_change_requires_owner")
        self.expected_head_sha = expected_head_sha
        self.evidence = normalized


class _TargetLaneClosureStale(SupervisorRuntimeError):
    """A durable lane-closure action no longer has its exact current binding."""


@dataclass(frozen=True)
class RuntimeWorkerResult:
    kind: str
    event_id: str | None
    status: str
    detail: str


class RuntimeActionGuard:
    """Live generation/reservation guard passed to registered mutating adapters."""

    def __init__(self, runtime: "SupervisorRuntime", action: Mapping[str, Any], *, release: bool) -> None:
        self.runtime = runtime
        self.action = dict(action)
        self.release = release
        self.callback_checks = 0

    def assert_current(self) -> None:
        current = self.runtime.registry.current_generation()
        if (
            current.get("generation") != self.runtime.engine.fence.generation
            or current.get("owner_id") != self.runtime.engine.fence.owner_id
            or float(current.get("expires_at") or 0) <= self.runtime.clock()
        ):
            raise SupervisorRuntimeError("external action lost the Supervisor generation fence")
        if self.release:
            self.runtime._validate_release_reservation(self.action, renew=False)

    def checkpoint(self) -> None:
        """Registered adapter calls this before each mutation/readback boundary."""

        self.assert_current()
        self.callback_checks += 1


class _ExecutionReservationLease:
    """Keep one atomic model-turn reservation live during an unbounded wait."""

    def __init__(
        self,
        runtime: "SupervisorRuntime",
        grants: Sequence[LockGrant],
        *,
        ttl_seconds: float,
    ) -> None:
        self.runtime = runtime
        self._grants = tuple(grants)
        self.ttl_seconds = ttl_seconds
        self._stop = threading.Event()
        self._lost = threading.Event()
        self._error_code: str | None = None
        self._thread = threading.Thread(
            target=self._renew_loop,
            name="dcp-v2-execution-lock-renewer",
            daemon=True,
        )
        self._guard = threading.Lock()

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=max(5.0, self.ttl_seconds))
        if self._thread.is_alive():
            self._lost.set()
            self._error_code = "execution_lock_renewer_stuck"

    def assert_current(self) -> None:
        if self._lost.is_set():
            raise CodexAmbiguousOutcomeError(
                "execution reservation was lost while the App Server turn was active"
            )
        try:
            with self._guard:
                self._grants = self.runtime.registry.renew_execution_reservation(
                    self._grants,
                    self.runtime.engine.fence,
                    ttl=self.ttl_seconds,
                )
        except Exception as exc:
            self._error_code = _error_code(exc)
            self._lost.set()
            raise CodexAmbiguousOutcomeError(
                "execution reservation could not be re-attested after the App Server turn"
            ) from exc

    def _renew_loop(self) -> None:
        interval = max(0.05, min(10.0, self.ttl_seconds / 3.0))
        while not self._stop.wait(interval):
            try:
                with self._guard:
                    self._grants = self.runtime.registry.renew_execution_reservation(
                        self._grants,
                        self.runtime.engine.fence,
                        ttl=self.ttl_seconds,
                    )
            except Exception as exc:
                self._error_code = _error_code(exc)
                self._lost.set()
                return


class _ReleaseReservationLease:
    """Renew an exact scheduler reservation during merge/deploy/readback waits."""

    def __init__(self, runtime: "SupervisorRuntime", action: Mapping[str, Any]) -> None:
        self.runtime = runtime
        self.action = dict(action)
        self._stop = threading.Event()
        self._lost = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name="dcp-v2-release-reservation-renewer",
            daemon=True,
        )

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=max(5.0, self.runtime.release_reservation_ttl_seconds))
        if self._thread.is_alive():
            self._lost.set()

    def assert_current(self) -> None:
        if self._lost.is_set():
            raise SupervisorRuntimeError("release reservation renewal was lost")
        try:
            self._renew()
        except Exception as exc:
            self._lost.set()
            raise SupervisorRuntimeError("release reservation cannot be re-attested") from exc

    def _run(self) -> None:
        interval = max(0.05, min(30.0, self.runtime.release_reservation_ttl_seconds / 3.0))
        while not self._stop.wait(interval):
            try:
                self._renew()
            except Exception:
                self._lost.set()
                return

    def _renew(self) -> None:
        if isinstance(self.action.get("release_candidate"), Mapping):
            self.runtime._validate_release_reservation(self.action, renew=True)
            return
        candidate = release_candidate_from_mapping(_mapping(self.action, "candidate"))
        self.runtime._validate_release_candidate_reservation(candidate, renew=True)


class SupervisorRuntime:
    """Compose one fenced engine, one owned App Server child and its workers."""

    def __init__(
        self,
        engine: SupervisorEngine,
        *,
        allowed_workspace_root: Path | str,
        codex_client_factory: Callable[..., CodexAppServerClient] = CodexAppServerClient,
        codex_bin: Path | str | None = None,
        release_executor: Callable[[Mapping[str, Any], RuntimeActionGuard], Mapping[str, Any]] | None = None,
        release_candidate_resolver: Callable[
            [Mapping[str, Any], RuntimeActionGuard], Mapping[str, Any]
        ] | None = None,
        release_arbiter_executor: Callable[
            [Mapping[str, Any], RuntimeActionGuard], ArbiterDecision
        ] | None = None,
        incident_arbiter_executor: Callable[[Mapping[str, Any], RuntimeActionGuard], ArbiterDecision] | None = None,
        incident_application_executor: Callable[[Mapping[str, Any], RuntimeActionGuard], Mapping[str, Any]] | None = None,
        target_lane_closure_executor: Callable[
            [Mapping[str, Any], RuntimeActionGuard], Mapping[str, Any]
        ] | None = None,
        require_automation_workers: bool = True,
        allow_external_policy_adapters: bool = False,
        owner_acceptance_verifier: Callable[[Any, Mapping[str, Any]], bool] | None = None,
        owner_action_verifier: Callable[
            [Mapping[str, Any], Mapping[str, Any]], bool
        ]
        | None = None,
        clock: Callable[[], float] = time.time,
        retry_delay_seconds: float = DEFAULT_RETRY_DELAY_SECONDS,
        visibility_timeout_seconds: float = DEFAULT_VISIBILITY_TIMEOUT_SECONDS,
        execution_lock_ttl_seconds: float = DEFAULT_EXECUTION_LOCK_TTL_SECONDS,
        release_reservation_ttl_seconds: float = DEFAULT_RELEASE_RESERVATION_TTL_SECONDS,
        after_turn_completed: Callable[[OutboxMessage, CodexTurnResult], None] | None = None,
        after_checkpoint_persisted: Callable[[OutboxMessage, CodexTurnResult], None] | None = None,
        after_result_persisted: Callable[[OutboxMessage, CodexTurnResult], None] | None = None,
        activation_identity: Mapping[str, Any] | None = None,
        preactivation_repair_mode: bool = False,
        preactivation_causal_remediation_mode: bool = False,
    ) -> None:
        self.engine = engine
        self.registry = engine.registry
        self.clock = clock
        self.allowed_workspace_root = Path(allowed_workspace_root).expanduser().absolute()
        self.allowed_workspace_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.allowed_workspace_root, 0o700)
        if retry_delay_seconds < 0:
            raise SupervisorRuntimeError("retry delay cannot be negative")
        if visibility_timeout_seconds <= 0:
            raise SupervisorRuntimeError("visibility timeout must be positive")
        if execution_lock_ttl_seconds <= 0:
            raise SupervisorRuntimeError("execution lock ttl must be positive")
        if release_reservation_ttl_seconds <= 0:
            raise SupervisorRuntimeError("release reservation ttl must be positive")
        self.retry_delay_seconds = float(retry_delay_seconds)
        self.visibility_timeout_seconds = float(visibility_timeout_seconds)
        self.execution_lock_ttl_seconds = float(execution_lock_ttl_seconds)
        self.release_reservation_ttl_seconds = float(release_reservation_ttl_seconds)
        self._codex_client_factory = codex_client_factory
        self.codex_bin = _validated_codex_binary(codex_bin)
        self.release_executor = release_executor
        self.release_candidate_resolver = release_candidate_resolver
        self.release_arbiter_executor = release_arbiter_executor
        self.incident_arbiter_executor = incident_arbiter_executor
        self.incident_application_executor = incident_application_executor
        self.target_lane_closure_executor = target_lane_closure_executor
        self.require_automation_workers = bool(require_automation_workers)
        self.allow_external_policy_adapters = bool(allow_external_policy_adapters)
        self.owner_acceptance_verifier = owner_acceptance_verifier
        self.owner_action_verifier = owner_action_verifier
        self._after_turn_completed = after_turn_completed
        self._after_checkpoint_persisted = after_checkpoint_persisted
        self._after_result_persisted = after_result_persisted
        self.activation_identity = self._validated_activation_identity(activation_identity)
        self.preactivation_repair_mode = bool(preactivation_repair_mode)
        self.preactivation_causal_remediation_mode = bool(
            preactivation_causal_remediation_mode
        )
        if (
            self.preactivation_repair_mode
            and self.preactivation_causal_remediation_mode
        ):
            raise SupervisorRuntimeError(
                "preactivation repair and causal remediation modes are mutually exclusive"
            )
        self._preactivation_qualification_mode = bool(
            self.preactivation_repair_mode
            or self.preactivation_causal_remediation_mode
        )
        self._mutation_lock = threading.RLock()
        self._client_lock = threading.RLock()
        self._codex_client: CodexAppServerClient | None = None
        # App Server loaded-thread ownership is connection-local.  Binding a
        # resume to the initialized connection epoch prevents an internal
        # reconnect from making a stale process-local set look authoritative.
        self._resumed_threads: dict[str, int] = {}
        self._fresh_thread_epochs: dict[str, int] = {}
        self._last_codex_error: str | None = None
        self._closed = False
        self._prepared_policy_claims: dict[str, tuple[str, dict[str, Any]]] = {}
        self._prepared_release_claims: dict[str, tuple[str, dict[str, Any]]] = {}
        self._prepared_attention_claims: dict[str, dict[str, Any]] = {}
        self._preactivation_repair_complete = threading.Event()
        self._preactivation_release_admission_complete = threading.Event()
        self._preactivation_canary_complete = threading.Event()
        self._preactivation_repair_failure_code: str | None = None
        self._preactivation_causal_completed_restart = False
        self._preactivation_recovered_empty_thread_epochs: dict[str, int] = {}
        self._preactivation_recovered_snapshot_digest: str | None = None
        self._preactivation_restart_attestation_event_id: str | None = None
        self._preactivation_durable_canary_recovered = False
        self._preactivation_canary_writer_generation: int | None = None
        self._preactivation_turn_recovery_event_id: str | None = None
        self._preactivation_causal_turn_recovery_pending = False
        if self.preactivation_repair_mode:
            repair_state = self.registry.preactivation_structural_repair_state()
            if repair_state["status"] == "completed":
                parked = self.registry.park_completed_preactivation_repair_epoch_loss(
                    fence=self.engine.fence,
                )
                self._preactivation_repair_failure_code = str(
                    parked["error_code"]
                )
            elif repair_state["status"] == "parked":
                self._preactivation_repair_failure_code = str(
                    repair_state.get("error_code") or "preactivation_repair_parked"
                )
        elif self.preactivation_causal_remediation_mode:
            remediation_state = (
                self.registry.preactivation_causal_remediation_state()
            )
            if remediation_state["status"] == "completed":
                recovered_canary = self._causal_completed_canary_evidence()
                if recovered_canary is None:
                    pending_receipt = self._causal_completed_canary_evidence(
                        allow_pending_receipt=True
                    )
                    if (
                        pending_receipt is not None
                        and pending_receipt.get("outbox_state") == "pending"
                    ):
                        self.registry.reconcile_preactivation_causal_canary_receipt(
                            followup_event_id=str(
                                pending_receipt["followup_event_id"]
                            ),
                            checkpoint_event_id=str(
                                pending_receipt["checkpoint_event_id"]
                            ),
                            turn_receipt_event_id=str(
                                pending_receipt["turn_receipt_event_id"]
                            ),
                            canary_writer_generation=int(
                                pending_receipt["canary_writer_generation"]
                            ),
                            fence=self.engine.fence,
                        )
                        recovered_canary = (
                            self._causal_completed_canary_evidence()
                        )
                if recovered_canary is not None:
                    self._activate_causal_completed_canary(recovered_canary)
                elif self._causal_completed_turn_recovery_is_pending():
                    # App Server I/O is forbidden in construction: the runtime
                    # loop starts its independent lease renewer before this
                    # exact worker path performs thread/read.
                    self._preactivation_causal_turn_recovery_pending = True
                    self._preactivation_release_admission_complete.set()
                elif self._causal_completed_restart_is_safe():
                    self._preactivation_causal_completed_restart = True
                    self._preactivation_repair_complete.set()
                    if self._causal_completed_admission_is_durable():
                        self._preactivation_release_admission_complete.set()
                else:
                    parked = self.registry.park_completed_preactivation_causal_remediation_epoch_loss(
                        fence=self.engine.fence,
                    )
                    self._preactivation_repair_failure_code = str(
                        parked["error_code"]
                    )
            elif remediation_state["status"] == "parked":
                self._preactivation_repair_failure_code = str(
                    remediation_state.get("error_code")
                    or "preactivation_causal_remediation_parked"
                )

    @property
    def http_engine(self) -> "RuntimeEngineView":
        return RuntimeEngineView(self)

    def handle_command(self, request: Mapping[str, Any]) -> dict[str, Any]:
        """Validate and execute one exact private-socket request."""

        _exact_fields(request, {"contract", "command", "request_id", "payload"}, "command request")
        if request.get("contract") != COMMAND_CONTRACT:
            raise SupervisorCommandError("command contract mismatch")
        command = _machine("command", request.get("command"))
        request_id = _machine("request_id", request.get("request_id"))
        payload = request.get("payload")
        if not isinstance(payload, Mapping):
            raise SupervisorCommandError("command payload must be an object")

        dispatch: dict[str, Callable[[Mapping[str, Any]], Any]] = {
            "register": self._command_register,
            "checkpoint": self._command_checkpoint,
            "terminal": self._command_terminal,
            "owner_acceptance": self._command_owner_acceptance,
            "register_release_candidate": self._command_register_release_candidate,
            "revise_release_manifest": self._command_revise_release_manifest,
            "tick": self._command_tick,
            "start_executor": self._command_start_executor,
            "reconcile_unbound_start": self._command_reconcile_unbound_start,
            "apply_corrective_generation": self._command_apply_corrective_generation,
            "apply_preactivation_structural_repair": (
                self._command_apply_preactivation_structural_repair
            ),
            "apply_preactivation_causal_remediation": (
                self._command_apply_preactivation_causal_remediation
            ),
            "preactivation_repair_state": self._command_preactivation_repair_state,
            "preactivation_causal_remediation_state": (
                self._command_preactivation_causal_remediation_state
            ),
            "codex_followup": self._command_followup,
            "prepare_attention": self._command_prepare_attention,
            "ack_attention": self._command_ack_attention,
            "nack_attention": self._command_nack_attention,
            "human_gate": self._command_human_gate,
            "prepare_incident_arbiter": self._command_prepare_incident_arbiter,
            "record_incident_arbiter": self._command_record_incident_arbiter,
            "prepare_incident_application": self._command_prepare_incident_application,
            "complete_incident_application": self._command_complete_incident_application,
            "runtime_health": self._command_runtime_health,
            "runtime_state": self._command_runtime_state,
        }
        if self.preactivation_causal_remediation_mode:
            if not self._preactivation_repair_complete.is_set():
                allowed_commands = (
                    "apply_preactivation_causal_remediation",
                    "preactivation_causal_remediation_state",
                    "runtime_health",
                )
            elif not self._preactivation_canary_complete.is_set():
                allowed_commands = (
                    "apply_preactivation_causal_remediation",
                    "preactivation_causal_remediation_state",
                    "codex_followup",
                    "runtime_health",
                    "runtime_state",
                )
            else:
                allowed_commands = (
                    "preactivation_causal_remediation_state",
                    "runtime_health",
                    "runtime_state",
                )
            dispatch = {name: dispatch[name] for name in allowed_commands}
        elif self.preactivation_repair_mode:
            if not self._preactivation_repair_complete.is_set():
                allowed_commands = (
                    "apply_preactivation_structural_repair",
                    "preactivation_repair_state",
                    "runtime_health",
                )
            elif not self._preactivation_canary_complete.is_set():
                allowed_commands = (
                    "apply_preactivation_structural_repair",
                    "preactivation_repair_state",
                    "codex_followup",
                    "runtime_health",
                    "runtime_state",
                )
            else:
                # The bounded repair process never becomes a normal mutation
                # authority.  launchd must start a fresh ordinary process only
                # after the installer accepts the qualification evidence.
                allowed_commands = (
                    "preactivation_repair_state",
                    "runtime_health",
                    "runtime_state",
                )
            dispatch = {name: dispatch[name] for name in allowed_commands}
        elif self.allow_external_policy_adapters:
            dispatch.update(
                {
                    "queue_release_action": self._command_queue_release_action,
                    "prepare_release_action": self._command_prepare_release_action,
                    "ack_release_action": self._command_ack_release_action,
                    "nack_release_action": self._command_nack_release_action,
                }
            )
        handler = dispatch.get(command)
        if handler is None:
            raise SupervisorCommandError("unsupported command")
        result = handler(payload)
        return {
            "contract": RECEIPT_CONTRACT,
            "request_id": request_id,
            "ok": True,
            "result": result,
            "error": None,
        }

    def resume_owned_threads(self) -> tuple[str, ...]:
        """Resume every exact active executor thread known by the registry."""

        if (
            self._preactivation_qualification_mode
            and not self._preactivation_repair_complete.is_set()
        ):
            raise SupervisorRuntimeError(
                "owned-thread resume is disabled before preactivation repair"
            )
        thread_ids = self._active_thread_ids()
        if not thread_ids:
            return ()
        client = self._client(extra_owned=thread_ids)
        resumed: list[str] = []
        for thread_id in thread_ids:
            try:
                self._ensure_thread_resumed(client, thread_id)
            except Exception as exc:
                self._last_codex_error = _error_code(exc)
                continue
            if self._resumed_threads.get(thread_id) == client.connection_epoch:
                resumed.append(thread_id)
                continue
        if len(resumed) == len(thread_ids):
            self._last_codex_error = None
        return tuple(resumed)

    def maintenance_tick(self) -> None:
        """Run projection/recovery maintenance outside the lease-renew worker."""

        if self._preactivation_qualification_mode:
            # Qualification is intentionally quieter than the installed
            # runtime: no projection publication, heartbeat, reservation
            # recovery, release reconciliation or incident reconciliation is
            # allowed from this short-lived process.
            return
        with self._mutation_lock:
            self._reconcile_release_orchestration()
            self._reconcile_target_lane_closures()
            self._reconcile_incident_applications()
            self.engine.tick()

    def renew_generation_lease(self) -> None:
        """Renew only the singleton generation; never wait on model/HTTPS work."""

        self.engine.renew_lease()

    def process_codex_once(self) -> RuntimeWorkerResult:
        """Process at most one thread-start or follow-up outbox item."""

        if (
            self._preactivation_qualification_mode
            and not self._preactivation_repair_complete.is_set()
        ):
            return RuntimeWorkerResult(
                "none", None, "disabled", "preactivation_repair_pending"
            )
        if self._preactivation_qualification_mode:
            if self._preactivation_canary_complete.is_set():
                return RuntimeWorkerResult(
                    "codex_followup",
                    None,
                    "disabled",
                    "preactivation_qualification_complete",
                )
            if not self._preactivation_release_admission_complete.is_set():
                return RuntimeWorkerResult(
                    "codex_followup",
                    None,
                    "disabled",
                    "preactivation_release_admission_pending",
                )
            with self._mutation_lock:
                claimed_canary = self._claim_current_preactivation_canary()
            if claimed_canary is None:
                return RuntimeWorkerResult(
                    "codex_followup", None, "idle", "no_preactivation_canary"
                )
            result = self._process_followup(claimed_canary)
            if result.status == "delivered":
                self._preactivation_canary_complete.set()
            elif result.status == "qualification_failed":
                self._preactivation_repair_failure_code = (
                    "preactivation_canary_failed"
                )
            return result
        with self._mutation_lock:
            starts = self.registry.claim_outbox(
                self.engine.fence,
                worker_id="supervisor-codex-thread-start",
                limit=1,
                visibility_timeout=self.visibility_timeout_seconds,
                kinds=("codex_thread_start",),
            )
        if starts:
            return self._process_thread_start(starts[0])
        with self._mutation_lock:
            successors = self.registry.claim_outbox(
                self.engine.fence,
                worker_id="supervisor-codex-successor",
                limit=1,
                visibility_timeout=self.visibility_timeout_seconds,
                kinds=("codex_successor_start",),
            )
        if successors:
            return self._process_successor(successors[0])
        with self._mutation_lock:
            followups = self.registry.claim_outbox(
                self.engine.fence,
                worker_id="supervisor-codex-followup",
                limit=1,
                visibility_timeout=self.visibility_timeout_seconds,
                kinds=("codex_followup",),
            )
        if followups:
            return self._process_followup(followups[0])
        return RuntimeWorkerResult("none", None, "idle", "no_codex_work")

    def _claim_current_preactivation_canary(self) -> OutboxMessage | None:
        """Claim only the current qualified scope, never a stale PR92 row."""

        task = self.registry.get_task(PREACTIVATION_STRUCTURAL_REPAIR_TASK_ID)
        workstream = self.registry.get_workstream(
            PREACTIVATION_STRUCTURAL_REPAIR_WORKSTREAM_ID
        )
        executor = self.registry.current_executor(
            PREACTIVATION_STRUCTURAL_REPAIR_TASK_ID,
            PREACTIVATION_STRUCTURAL_REPAIR_WORKSTREAM_ID,
        )
        if task is None or workstream is None or executor is None:
            raise SupervisorRuntimeError(
                "preactivation canary lacks its current task/workstream/executor"
            )
        passport = task_passport_from_mapping(task.passport)
        workstream_contract = workstream_from_mapping(workstream.contract)
        activation_release_sha = (
            self.activation_identity.get("release_sha")
            if isinstance(self.activation_identity, Mapping)
            else None
        )
        qualification_resource = (
            f"qualification:{activation_release_sha}"
            if isinstance(activation_release_sha, str)
            else None
        )
        if (
            not isinstance(qualification_resource, str)
            or qualification_resource not in passport.resources
            or qualification_resource not in workstream_contract.resources
            or (
                self.preactivation_causal_remediation_mode
                and (
                    task.revision
                    != PREACTIVATION_CAUSAL_REMEDIATION_SUCCESSOR_TASK_REVISION
                    or workstream.generation
                    != PREACTIVATION_CAUSAL_REMEDIATION_SUCCESSOR_WORKSTREAM_GENERATION
                    or workstream.revision != 2
                    or executor.executor_generation
                    != PREACTIVATION_CAUSAL_REMEDIATION_SUCCESSOR_EXECUTOR_GENERATION
                    or PREACTIVATION_CAUSAL_STRATEGY_RESOURCE
                    not in passport.resources
                    or PREACTIVATION_CAUSAL_STRATEGY_RESOURCE
                    not in workstream_contract.resources
                )
            )
        ):
            raise SupervisorRuntimeError(
                "preactivation canary current qualification binding changed"
            )
        records = [
            record
            for record in self.registry.list_outbox_records(
                kinds=("codex_followup",), states=("pending", "inflight")
            )
            if isinstance(record.get("payload"), Mapping)
            and record["payload"].get("schema") == FOLLOWUP_SCHEMA
            and record["payload"].get("call_policy")
            == CALL_POLICY_SINGLE_ATTEMPT_CANARY
            and record["payload"].get("task_id") == task.task_id
            and record["payload"].get("task_revision") == task.revision
            and record["payload"].get("workstream_id")
            == workstream.workstream_id
            and record["payload"].get("workstream_revision")
            == workstream.revision
            and record["payload"].get("executor_generation")
            == executor.executor_generation
            and record["payload"].get("thread_id") == executor.thread_id
        ]
        if len(records) > 1:
            raise SupervisorRuntimeError(
                "preactivation canary current durable scope is ambiguous"
            )
        if not records:
            return None
        event_id = records[0].get("event_id")
        if not isinstance(event_id, str):
            raise SupervisorRuntimeError(
                "preactivation canary event identity is invalid"
            )
        return self.registry.claim_outbox_event(
            event_id,
            worker_id="supervisor-preactivation-canary",
            visibility_timeout=self.visibility_timeout_seconds,
            fence=self.engine.fence,
        )

    def process_preactivation_repair_once(self) -> RuntimeWorkerResult:
        """Process only the exact structural successor, without a model turn."""

        if self.preactivation_causal_remediation_mode:
            return self._process_preactivation_causal_remediation_once()
        if not self._preactivation_qualification_mode:
            return RuntimeWorkerResult(
                "codex_preactivation_successor_start",
                None,
                "disabled",
                "preactivation_repair_mode_disabled",
            )
        if self._preactivation_repair_complete.is_set():
            return RuntimeWorkerResult(
                "codex_preactivation_successor_start",
                None,
                "idle",
                "preactivation_repair_completed",
            )
        with self._mutation_lock:
            messages = self.registry.claim_outbox(
                self.engine.fence,
                worker_id="supervisor-preactivation-structural-successor",
                limit=1,
                visibility_timeout=self.visibility_timeout_seconds,
                kinds=("codex_preactivation_successor_start",),
            )
        if not messages:
            return RuntimeWorkerResult(
                "codex_preactivation_successor_start",
                None,
                "idle",
                "no_preactivation_repair_work",
            )
        message = messages[0]
        try:
            repair_state = self.registry.preactivation_structural_repair_state()
            if (
                repair_state.get("status") == "successor_reserved"
                and repair_state.get("repair_writer_generation")
                != self.engine.fence.generation
            ):
                with self._mutation_lock:
                    self.registry.fail_preactivation_structural_repair(
                        claimed_outbox_event_id=message.event_id,
                        claim_token=message.claim_token,
                        error_code="preactivation_repair_process_generation_lost",
                        fence=self.engine.fence,
                    )
                self._preactivation_repair_failure_code = (
                    "preactivation_repair_process_generation_lost"
                )
                self._last_codex_error = (
                    "preactivation_repair_process_generation_lost"
                )
                return RuntimeWorkerResult(
                    "codex_preactivation_successor_start",
                    message.event_id,
                    "parked",
                    "preactivation_repair_process_generation_lost",
                )
            payload = self._validated_preactivation_successor_payload(
                message.payload
            )
            started = payload["started_thread"]
            client: CodexAppServerClient
            if started is None:
                if payload["start_intent"] is not None:
                    raise CodexAmbiguousOutcomeError(
                        "preactivation successor has an unreceipted thread/start"
                    )
                client = self._client()
                client.connect()
                epoch = client.connection_epoch
                if epoch < 1:
                    raise SupervisorRuntimeError(
                        "preactivation successor App Server epoch is unavailable"
                    )
                payload["start_intent"] = {
                    "supervisor_generation": self.engine.fence.generation,
                    "started_at": _iso(self.clock()),
                    "app_server_connection_epoch": epoch,
                }
                with self._mutation_lock:
                    message = self.registry.replace_claimed_outbox_payload(
                        message.event_id,
                        message.claim_token,
                        payload,
                        self.engine.fence,
                    )
                try:
                    identity = client.start_thread(
                        cwd=str(payload["cwd"]),
                        ephemeral=False,
                        required_connection_epoch=epoch,
                    )
                except Exception as exc:
                    raise CodexAmbiguousOutcomeError(
                        "preactivation successor thread/start failed after durable intent"
                    ) from exc
                started = self._started_identity(identity)
                persisted = dict(payload)
                persisted["started_thread"] = started
                try:
                    with self._mutation_lock:
                        message = self.registry.replace_claimed_outbox_payload(
                            message.event_id,
                            message.claim_token,
                            persisted,
                            self.engine.fence,
                        )
                except Exception as exc:
                    raise CodexAmbiguousOutcomeError(
                        "preactivation successor identity was not durably receipted"
                    ) from exc
                payload = persisted
                self._resumed_threads[identity.thread_id] = epoch
                self._fresh_thread_epochs[identity.thread_id] = epoch
            else:
                # A started successor is usable only in the process/connection
                # that created it.  Resuming it would destroy the one-canary
                # empty-thread shortcut and is therefore fail-closed.
                thread_id = str(started["thread_id"])
                client = self._codex_client  # type: ignore[assignment]
                intent = payload["start_intent"]
                if (
                    client is None
                    or not isinstance(intent, Mapping)
                    or self._fresh_thread_epochs.get(thread_id)
                    != client.connection_epoch
                    or self._resumed_threads.get(thread_id)
                    != client.connection_epoch
                    or intent.get("app_server_connection_epoch")
                    != client.connection_epoch
                ):
                    raise CodexAmbiguousOutcomeError(
                        "preactivation successor lost its same-process App Server epoch"
                    )
            successor = ExecutorIdentity(
                thread_id=str(started["thread_id"]),
                host_id=str(started["host_id"]),
                model=str(started["model"]),
                reasoning=str(started["reasoning"]),
            )
            epoch = int(payload["start_intent"]["app_server_connection_epoch"])
            if client.connection_epoch != epoch:
                raise CodexAmbiguousOutcomeError(
                    "preactivation successor App Server epoch changed before commit"
                )
            with client.pin_connection_epoch(epoch):
                with self._mutation_lock:
                    completion = self.registry.complete_preactivation_structural_repair(
                        claimed_outbox_event_id=message.event_id,
                        claim_token=message.claim_token,
                        successor=successor,
                        app_server_connection_epoch=epoch,
                        fence=self.engine.fence,
                    )
            self._preactivation_repair_complete.set()
            self._preactivation_repair_failure_code = None
            self._last_codex_error = None
            return RuntimeWorkerResult(
                "codex_preactivation_successor_start",
                message.event_id,
                "successor_proven",
                str(payload["completion_event_id"]),
            )
        except Exception as exc:
            self._last_codex_error = _error_code(exc)
            self._preactivation_repair_failure_code = _error_code(exc)
            try:
                with self._mutation_lock:
                    self.registry.fail_preactivation_structural_repair(
                        claimed_outbox_event_id=message.event_id,
                        claim_token=message.claim_token,
                        error_code=_error_code(exc),
                        fence=self.engine.fence,
                    )
            except Exception:
                pass
            return RuntimeWorkerResult(
                "codex_preactivation_successor_start",
                message.event_id,
                "parked",
                _error_code(exc),
            )

    def _process_preactivation_causal_remediation_once(
        self,
    ) -> RuntimeWorkerResult:
        """Advance exactly one PR93 causal-read or structural-start phase."""

        if not self.preactivation_causal_remediation_mode:
            return RuntimeWorkerResult(
                "preactivation_causal_remediation",
                None,
                "disabled",
                "preactivation_causal_remediation_mode_disabled",
            )
        if self._preactivation_causal_turn_recovery_pending:
            if self._recover_preactivation_causal_completed_turn():
                recovered_canary = self._causal_completed_canary_evidence()
                if recovered_canary is not None:
                    self._activate_causal_completed_canary(recovered_canary)
                    return RuntimeWorkerResult(
                        "preactivation_causal_canary_recovery",
                        str(recovered_canary["followup_event_id"]),
                        "canary_recovered",
                        str(recovered_canary["turn_receipt_event_id"]),
                    )
            parked = (
                self.registry.park_completed_preactivation_causal_remediation_epoch_loss(
                    fence=self.engine.fence,
                )
            )
            self._preactivation_causal_turn_recovery_pending = False
            self._preactivation_repair_failure_code = str(parked["error_code"])
            self._last_codex_error = self._preactivation_repair_failure_code
            return RuntimeWorkerResult(
                "preactivation_causal_canary_recovery",
                None,
                "parked",
                self._preactivation_repair_failure_code,
            )
        if self._preactivation_repair_complete.is_set():
            return RuntimeWorkerResult(
                "preactivation_causal_remediation",
                None,
                "idle",
                "preactivation_causal_remediation_completed",
            )
        state = self.registry.preactivation_causal_remediation_state()
        if state.get("status") == "parked":
            self._preactivation_repair_failure_code = str(
                state.get("error_code") or "preactivation_causal_remediation_parked"
            )
            return RuntimeWorkerResult(
                "preactivation_causal_remediation",
                None,
                "idle",
                self._preactivation_repair_failure_code,
            )
        if state.get("status") == "causal_read_reserved":
            read_event_id = state.get("causal_read_event_id")
            if not isinstance(read_event_id, str) or not read_event_id:
                raise SupervisorRuntimeError(
                    "preactivation causal read state lacks its exact event"
                )
            with self._mutation_lock:
                read_message = self.registry.claim_outbox_event(
                    read_event_id,
                    worker_id="supervisor-preactivation-causal-read",
                    visibility_timeout=self.visibility_timeout_seconds,
                    fence=self.engine.fence,
                )
            if read_message is not None:
                return self._process_preactivation_causal_read(read_message)
            return RuntimeWorkerResult(
                "codex_preactivation_causal_read",
                read_event_id,
                "idle",
                "preactivation_causal_read_claim_unavailable",
            )
        if state.get("status") == "successor_reserved":
            successor_event_id = state.get("successor_event_id")
            if not isinstance(successor_event_id, str) or not successor_event_id:
                raise SupervisorRuntimeError(
                    "preactivation causal successor state lacks its exact event"
                )
            with self._mutation_lock:
                successor_message = self.registry.claim_outbox_event(
                    successor_event_id,
                    worker_id="supervisor-preactivation-causal-successor",
                    visibility_timeout=self.visibility_timeout_seconds,
                    fence=self.engine.fence,
                )
            if successor_message is None:
                return RuntimeWorkerResult(
                    "codex_preactivation_causal_successor_start",
                    successor_event_id,
                    "idle",
                    "preactivation_causal_successor_claim_unavailable",
                )
            if (
                state.get("remediation_writer_generation")
                != self.engine.fence.generation
                and (
                    state.get("start_intent_present") is True
                    or state.get("started_thread_receipted") is True
                )
            ):
                code = "preactivation_causal_process_generation_lost"
                with self._mutation_lock:
                    self.registry.fail_preactivation_causal_successor_start(
                        claimed_outbox_event_id=successor_message.event_id,
                        claim_token=successor_message.claim_token,
                        error_code=code,
                        fence=self.engine.fence,
                    )
                self._preactivation_repair_failure_code = code
                self._last_codex_error = code
                return RuntimeWorkerResult(
                    "codex_preactivation_causal_successor_start",
                    successor_message.event_id,
                    "parked",
                    code,
                )
            return self._process_preactivation_causal_successor(
                successor_message
            )
        if state.get("status") == "completed":
            # Only the process that committed completion sets the in-memory
            # event. Constructor-time completed state is parked immediately.
            raise SupervisorRuntimeError(
                "preactivation causal completion lost its process-local event"
            )
        if state.get("status") != "awaiting_remediation_command":
            raise SupervisorRuntimeError(
                "preactivation causal remediation state is invalid"
            )
        return RuntimeWorkerResult(
            "preactivation_causal_remediation",
            None,
            "idle",
            "no_preactivation_causal_remediation_work",
        )

    def _process_preactivation_causal_read(
        self, message: OutboxMessage
    ) -> RuntimeWorkerResult:
        try:
            payload = self._validated_preactivation_causal_read_payload(
                message.payload
            )
            intent = payload["read_intent"]
            if intent is None or intent.get("supervisor_generation") != (
                self.engine.fence.generation
            ):
                payload["read_intent"] = {
                    "supervisor_generation": self.engine.fence.generation,
                    "started_at": _iso(self.clock()),
                }
                with self._mutation_lock:
                    message = self.registry.replace_claimed_outbox_payload(
                        message.event_id,
                        message.claim_token,
                        payload,
                        self.engine.fence,
                    )
            client = self._client(extra_owned=(str(payload["thread_id"]),))
            # Official thread/read is intentionally outside every SQLite
            # transaction and never resumes, loads or mutates the old thread.
            snapshot = client.read_thread_snapshot(
                str(payload["thread_id"]), include_turns=True
            )
            attestation = self._attest_preactivation_causal_snapshot(
                snapshot,
                thread_id=str(payload["thread_id"]),
                task_id=str(payload["task_id"]),
                workstream_id=str(payload["workstream_id"]),
                causal_read_event_id=str(payload["causal_read_event_id"]),
                source_failure_event_id=str(payload["source_failure_event_id"]),
                source_followup_event_id=str(payload["source_followup_event_id"]),
            )
            prior = payload.get("observed_attestation")
            if prior is not None and prior != attestation:
                raise CodexAmbiguousOutcomeError(
                    "preactivation causal read changed after its durable observation"
                )
            payload["observed_attestation"] = attestation
            with self._mutation_lock:
                message = self.registry.replace_claimed_outbox_payload(
                    message.event_id,
                    message.claim_token,
                    payload,
                    self.engine.fence,
                )
                completed = self.registry.complete_preactivation_causal_read(
                    claimed_outbox_event_id=message.event_id,
                    claim_token=message.claim_token,
                    attestation=attestation,
                    fence=self.engine.fence,
                )
            self._preactivation_repair_failure_code = None
            self._last_codex_error = None
            return RuntimeWorkerResult(
                "codex_preactivation_causal_read",
                message.event_id,
                "causal_attested",
                str(completed["causal_attestation_event_id"]),
            )
        except Exception as exc:
            code = _error_code(exc)
            self._last_codex_error = code
            self._preactivation_repair_failure_code = code
            try:
                with self._mutation_lock:
                    self.registry.fail_preactivation_causal_read(
                        claimed_outbox_event_id=message.event_id,
                        claim_token=message.claim_token,
                        error_code=code,
                        fence=self.engine.fence,
                    )
            except Exception:
                pass
            return RuntimeWorkerResult(
                "codex_preactivation_causal_read",
                message.event_id,
                "parked",
                code,
            )

    def _process_preactivation_causal_successor(
        self, message: OutboxMessage
    ) -> RuntimeWorkerResult:
        try:
            payload = self._validated_preactivation_causal_successor_payload(
                message.payload
            )
            started = payload["started_thread"]
            client: CodexAppServerClient
            if started is None:
                if payload["start_intent"] is not None:
                    raise CodexAmbiguousOutcomeError(
                        "preactivation causal successor has an unreceipted thread/start"
                    )
                client = self._client()
                client.connect()
                epoch = client.connection_epoch
                if epoch < 1:
                    raise SupervisorRuntimeError(
                        "preactivation causal successor App Server epoch is unavailable"
                    )
                payload["start_intent"] = {
                    "supervisor_generation": self.engine.fence.generation,
                    "started_at": _iso(self.clock()),
                    "app_server_connection_epoch": epoch,
                }
                with self._mutation_lock:
                    message = self.registry.replace_claimed_outbox_payload(
                        message.event_id,
                        message.claim_token,
                        payload,
                        self.engine.fence,
                    )
                try:
                    identity = client.start_thread(
                        cwd=str(payload["cwd"]),
                        ephemeral=False,
                        required_connection_epoch=epoch,
                    )
                except Exception as exc:
                    raise CodexAmbiguousOutcomeError(
                        "preactivation causal successor thread/start failed after durable intent"
                    ) from exc
                started = self._started_identity(identity)
                persisted = dict(payload)
                persisted["started_thread"] = started
                try:
                    with self._mutation_lock:
                        message = self.registry.replace_claimed_outbox_payload(
                            message.event_id,
                            message.claim_token,
                            persisted,
                            self.engine.fence,
                        )
                except Exception as exc:
                    raise CodexAmbiguousOutcomeError(
                        "preactivation causal successor identity was not durably receipted"
                    ) from exc
                payload = persisted
                self._resumed_threads[identity.thread_id] = epoch
                self._fresh_thread_epochs[identity.thread_id] = epoch
            else:
                thread_id = str(started["thread_id"])
                client = self._codex_client  # type: ignore[assignment]
                intent = payload["start_intent"]
                if (
                    client is None
                    or not isinstance(intent, Mapping)
                    or self._fresh_thread_epochs.get(thread_id)
                    != client.connection_epoch
                    or self._resumed_threads.get(thread_id)
                    != client.connection_epoch
                    or intent.get("app_server_connection_epoch")
                    != client.connection_epoch
                ):
                    raise CodexAmbiguousOutcomeError(
                        "preactivation causal successor lost its same-process App Server epoch"
                    )
            successor = ExecutorIdentity(
                thread_id=str(started["thread_id"]),
                host_id=str(started["host_id"]),
                model=str(started["model"]),
                reasoning=str(started["reasoning"]),
            )
            epoch = int(payload["start_intent"]["app_server_connection_epoch"])
            if client.connection_epoch != epoch:
                raise CodexAmbiguousOutcomeError(
                    "preactivation causal successor App Server epoch changed before commit"
                )
            with client.pin_connection_epoch(epoch):
                with self._mutation_lock:
                    completion = (
                        self.registry.complete_preactivation_causal_remediation(
                            claimed_outbox_event_id=message.event_id,
                            claim_token=message.claim_token,
                            successor=successor,
                            app_server_connection_epoch=epoch,
                            fence=self.engine.fence,
                        )
                    )
            self._preactivation_repair_complete.set()
            self._preactivation_repair_failure_code = None
            self._last_codex_error = None
            return RuntimeWorkerResult(
                "codex_preactivation_causal_successor_start",
                message.event_id,
                "successor_proven",
                str(payload["completion_event_id"]),
            )
        except Exception as exc:
            code = _error_code(exc)
            self._last_codex_error = code
            self._preactivation_repair_failure_code = code
            try:
                with self._mutation_lock:
                    self.registry.fail_preactivation_causal_successor_start(
                        claimed_outbox_event_id=message.event_id,
                        claim_token=message.claim_token,
                        error_code=code,
                        fence=self.engine.fence,
                    )
            except Exception:
                pass
            return RuntimeWorkerResult(
                "codex_preactivation_causal_successor_start",
                message.event_id,
                "parked",
                code,
            )

    def process_release_once(self) -> RuntimeWorkerResult:
        if (
            self._preactivation_qualification_mode
            and not self._preactivation_repair_complete.is_set()
        ):
            return RuntimeWorkerResult(
                "release_action", None, "disabled", "preactivation_repair_pending"
            )
        if self._preactivation_qualification_mode:
            if self._preactivation_canary_complete.is_set():
                return RuntimeWorkerResult(
                    "release_action",
                    None,
                    "disabled",
                    "preactivation_qualification_complete",
                )
            if self._preactivation_release_admission_complete.is_set():
                return RuntimeWorkerResult(
                    "release_candidate_intake",
                    None,
                    "idle",
                    "preactivation_proof_only_admission_complete",
                )
            if self._preactivation_repair_failure_code:
                return RuntimeWorkerResult(
                    "release_candidate_intake",
                    None,
                    "disabled",
                    self._preactivation_repair_failure_code,
                )
            with self._mutation_lock:
                intakes = self.registry.claim_outbox(
                    self.engine.fence,
                    worker_id="supervisor-preactivation-release-admission",
                    limit=1,
                    visibility_timeout=300,
                    kinds=("release_candidate_intake",),
                )
            if not intakes:
                return RuntimeWorkerResult(
                    "release_candidate_intake",
                    None,
                    "idle",
                    "no_preactivation_release_admission",
                )
            result = self._execute_release_candidate_intake(
                intakes[0], preactivation_safe=True
            )
            if result.status == "proof_only_wait":
                self._preactivation_release_admission_complete.set()
            elif result.status != "retry_scheduled":
                self._preactivation_repair_failure_code = (
                    "preactivation_release_admission_failed"
                )
            return result
        if self.target_lane_closure_executor is not None:
            with self._mutation_lock:
                closures = self.registry.claim_outbox(
                    self.engine.fence,
                    worker_id="supervisor-target-lane-closure",
                    limit=1,
                    visibility_timeout=300,
                    kinds=("target_lane_closure",),
                )
            if closures:
                return self._execute_target_lane_closure(closures[0])
        if self.release_arbiter_executor is not None:
            with self._mutation_lock:
                cases = self.registry.claim_outbox(
                    self.engine.fence,
                    worker_id="supervisor-fresh-release-arbiter",
                    limit=1,
                    visibility_timeout=900,
                    kinds=("release_arbiter_case",),
                )
            if cases:
                return self._execute_release_arbiter(cases[0])
        if self.release_candidate_resolver is not None:
            with self._mutation_lock:
                intakes = self.registry.claim_outbox(
                    self.engine.fence,
                    worker_id="supervisor-release-candidate-intake",
                    limit=1,
                    visibility_timeout=300,
                    kinds=("release_candidate_intake",),
                )
            if intakes:
                return self._execute_release_candidate_intake(intakes[0])
            with self._mutation_lock:
                resolutions = self.registry.claim_outbox(
                    self.engine.fence,
                    worker_id="supervisor-release-candidate-resolver",
                    limit=1,
                    visibility_timeout=300,
                    kinds=("release_candidate_resolution",),
                )
            if resolutions:
                return self._execute_release_resolution(resolutions[0])
        if self.release_executor is None:
            return RuntimeWorkerResult("release_action", None, "disabled", "release_executor_unavailable")
        with self._mutation_lock:
            messages = self.registry.claim_outbox(
                self.engine.fence,
                worker_id="supervisor-release-train",
                limit=1,
                visibility_timeout=300,
                kinds=("release_action",),
            )
        if not messages:
            return RuntimeWorkerResult("release_action", None, "idle", "no_release_work")
        message = messages[0]
        result_event_id = _event_id("release-result", message.event_id)
        with self._mutation_lock:
            if self.registry.get_event(result_event_id) is not None:
                self.registry.ack_outbox(message.event_id, message.claim_token, self.engine.fence)
                self._reconcile_incident_applications()
                return RuntimeWorkerResult("release_action", message.event_id, "deduped", result_event_id)
        reservation_lease: _ReleaseReservationLease | None = None
        try:
            # GitHub/deploy/verify are wholly outside registry transactions.
            candidate = release_candidate_from_mapping(_mapping(message.payload, "candidate"))
            self._ensure_release_candidate_reservation(candidate)
            self._require_release_actuator_authorization(
                candidate.task_id,
                include_lane_release=False,
            )
            reservation_lease = _ReleaseReservationLease(self, message.payload)
            reservation_lease.start()
            guard = RuntimeActionGuard(self, message.payload, release=True)
            guard.assert_current()
            raw_result = self.release_executor(dict(message.payload), guard)
            guard.assert_current()
            if guard.callback_checks < 2:
                raise SupervisorRuntimeError("release adapter omitted required mutation/readback fence checkpoints")
            reservation_lease.assert_current()
            if raw_result.get("schema") == "dev-control-plane/release-action-observation/v2":
                observation = _validated_release_observation(raw_result)
                self._validate_release_observation_binding(message.payload, observation)
                reservation_lease.stop()
                reservation_lease = None
                return self._persist_release_observation(message, observation)
            receipt = _validated_release_receipt(raw_result)
            self._persist_release_result(message, receipt)
            reservation_lease.stop()
            reservation_lease = None
            with self._mutation_lock:
                self._reconcile_incident_applications()
                self._reconcile_release_orchestration()
            return RuntimeWorkerResult("release_action", message.event_id, "delivered", result_event_id)
        except SecurityPermissionChangeRequiresOwner as exc:
            if reservation_lease is not None:
                reservation_lease.stop()
            candidate = release_candidate_from_mapping(_mapping(message.payload, "candidate"))
            remediation_decision_id = message.payload.get("remediation_decision_id")
            if isinstance(remediation_decision_id, str):
                return self._fail_incident_dispatch(
                    message,
                    remediation_decision_id,
                    exc,
                    verification_identity="release-authorization-failed-after-arbiter",
                )
            return self._persist_release_human_gate(message, candidate, exc)
        except Exception as exc:
            if reservation_lease is not None:
                reservation_lease.stop()
            candidate = release_candidate_from_mapping(_mapping(message.payload, "candidate"))
            remediation_decision_id = message.payload.get("remediation_decision_id")
            if isinstance(remediation_decision_id, str):
                return self._fail_incident_dispatch(
                    message,
                    remediation_decision_id,
                    exc,
                    verification_identity="release-actuator-failed-after-arbiter",
                )
            fingerprint = self._release_failure_fingerprint(candidate, exc, stage="release_action")
            if self._release_incident_was_applied(candidate, fingerprint):
                return self._park_release_policy_message(
                    message,
                    (candidate,),
                    exc,
                    phase="same_failure_after_release_arbiter",
                )
            failure_count = self._record_release_failure_observation(
                message,
                candidate,
                fingerprint=fingerprint,
                stage="release_action",
                exc=exc,
            )
            if failure_count == 1:
                with self._mutation_lock:
                    self.registry.nack_outbox(
                        message.event_id,
                        message.claim_token,
                        self.engine.fence,
                        retry_at=self.clock() + self.retry_delay_seconds,
                        sanitized_error=_error_code(exc),
                    )
                return RuntimeWorkerResult(
                    "release_action", message.event_id, "retry_scheduled", _error_code(exc)
                )
            return self._route_release_incident(message, candidate, exc, fingerprint=fingerprint)

    def process_incident_policy_once(self) -> RuntimeWorkerResult:
        if self._preactivation_qualification_mode:
            return RuntimeWorkerResult(
                "incident_policy",
                None,
                "disabled",
                "preactivation_qualification_only",
            )
        if self.incident_arbiter_executor is not None:
            with self._mutation_lock:
                cases = self.registry.claim_outbox(
                    self.engine.fence,
                    worker_id="supervisor-fresh-incident-arbiter",
                    limit=1,
                    visibility_timeout=900,
                    kinds=("incident_arbiter_case",),
                )
            if cases:
                return self._execute_incident_arbiter(cases[0])
        if self.incident_application_executor is not None:
            with self._mutation_lock:
                applications = self.registry.claim_outbox(
                    self.engine.fence,
                    worker_id="supervisor-incident-application",
                    limit=1,
                    visibility_timeout=900,
                    kinds=("incident_arbiter_application",),
                )
            if applications:
                return self._execute_incident_application(applications[0])
        return RuntimeWorkerResult("incident_policy", None, "idle", "no_incident_policy_work")

    def health(self) -> dict[str, Any]:
        base = self.engine.health()
        if (
            self._preactivation_qualification_mode
            and not self._preactivation_repair_complete.is_set()
        ):
            repair = (
                self.registry.preactivation_causal_remediation_state()
                if self.preactivation_causal_remediation_mode
                else self.registry.preactivation_structural_repair_state()
            )
            return {
                **base,
                "status": "not_ready",
                "codex_runtime": {
                    "status": "repair_only",
                    "required_model": CODEX_APP_SERVER_MODEL,
                    "required_reasoning": CODEX_APP_SERVER_REASONING_EFFORT,
                    "active_owned_threads": 0,
                    "resumed_owned_threads": 0,
                    "last_error_code": self._last_codex_error,
                },
                "command_socket_mutation_only": True,
                "automation_workers": {
                    "ready": False,
                    "release_train": False,
                    "release_candidate_resolver": False,
                    "release_arbiter": False,
                    "incident_arbiter": False,
                    "incident_application": False,
                },
                **{
                    (
                        "preactivation_causal_remediation"
                        if self.preactivation_causal_remediation_mode
                        else "preactivation_repair"
                    ): {
                        **repair,
                        "same_process_completion": False,
                        "worker_failure_code": (
                            self._preactivation_repair_failure_code or ""
                        ),
                        "http_ready": False,
                    }
                },
                "activation_identity": (
                    {
                        **self.activation_identity,
                        "supervisor_generation": self.engine.fence.generation,
                        "supervisor_owner_id": self.engine.fence.owner_id,
                    }
                    if self.activation_identity is not None
                    else None
                ),
            }
        active_threads = self._active_thread_ids()
        client_epoch = self._codex_client.connection_epoch if self._codex_client is not None else 0
        resumed_now = {
            thread_id
            for thread_id in active_threads
            if client_epoch > 0 and self._resumed_threads.get(thread_id) == client_epoch
        }
        resume_complete = not active_threads or set(active_threads) <= resumed_now
        codex_status = "dormant" if not active_threads and self._codex_client is None else (
            "ready" if resume_complete and self._last_codex_error is None else "degraded"
        )
        automation_configured = all(
            worker is not None
            for worker in (
                self.release_executor,
                self.release_candidate_resolver,
                self.release_arbiter_executor,
                self.incident_arbiter_executor,
                self.incident_application_executor,
                self.target_lane_closure_executor,
            )
        )
        qualification_only = self._preactivation_qualification_mode
        automation_ready = automation_configured and not qualification_only
        ready = (
            base["status"] == "ready"
            and codex_status != "degraded"
            and (
                automation_ready
                or qualification_only
                or not self.require_automation_workers
            )
        )
        return {
            **base,
            "status": "ready" if ready else "not_ready",
            "codex_runtime": {
                "status": codex_status,
                "required_model": CODEX_APP_SERVER_MODEL,
                "required_reasoning": CODEX_APP_SERVER_REASONING_EFFORT,
                "active_owned_threads": len(active_threads),
                "resumed_owned_threads": len(resumed_now),
                "last_error_code": self._last_codex_error,
            },
            "command_socket_mutation_only": True,
            "automation_workers": {
                "ready": automation_ready,
                "release_train": self.release_executor is not None and not qualification_only,
                "release_candidate_resolver": (
                    self.release_candidate_resolver is not None
                    and not qualification_only
                ),
                "release_arbiter": (
                    self.release_arbiter_executor is not None
                    and not qualification_only
                ),
                "incident_arbiter": (
                    self.incident_arbiter_executor is not None
                    and not qualification_only
                ),
                "incident_application": (
                    self.incident_application_executor is not None
                    and not qualification_only
                ),
            },
            "preactivation_qualification_only": qualification_only,
            "preactivation_release_admission_complete": (
                self._preactivation_release_admission_complete.is_set()
            ),
            "preactivation_canary_complete": (
                self._preactivation_canary_complete.is_set()
            ),
            "activation_identity": (
                {
                    **self.activation_identity,
                    "supervisor_generation": self.engine.fence.generation,
                    "supervisor_owner_id": self.engine.fence.owner_id,
                }
                if self.activation_identity is not None
                else None
            ),
        }

    def readiness(self) -> dict[str, Any]:
        health = self.health()
        return {
            "ready": health["status"] == "ready",
            "service_role": health["service_role"],
            "generation": self.engine.fence.generation,
            "single_writer": health["lease_live"],
            "codex_runtime_status": health["codex_runtime"]["status"],
            "activation_identity": health["activation_identity"],
        }

    @property
    def preactivation_repair_complete(self) -> bool:
        return self._preactivation_repair_complete.is_set()

    @property
    def preactivation_repair_failed(self) -> bool:
        return bool(
            self._preactivation_repair_failure_code
            and not self._preactivation_repair_complete.is_set()
        )

    @property
    def preactivation_release_admission_complete(self) -> bool:
        return self._preactivation_release_admission_complete.is_set()

    @property
    def preactivation_canary_complete(self) -> bool:
        return self._preactivation_canary_complete.is_set()

    def wait_for_preactivation_repair(self, timeout: float) -> bool:
        if timeout < 0:
            raise SupervisorRuntimeError(
                "preactivation repair wait timeout cannot be negative"
            )
        return self._preactivation_repair_complete.wait(timeout)

    def _activate_causal_completed_canary(
        self, recovered_canary: Mapping[str, Any]
    ) -> None:
        self._preactivation_durable_canary_recovered = True
        self._preactivation_canary_writer_generation = int(
            recovered_canary["canary_writer_generation"]
        )
        self._preactivation_turn_recovery_event_id = (
            str(recovered_canary["turn_recovery_event_id"])
            if recovered_canary.get("turn_recovery_event_id")
            else None
        )
        self._preactivation_causal_completed_restart = bool(
            recovered_canary["completed_restart_recovered"]
        )
        self._preactivation_restart_attestation_event_id = (
            str(recovered_canary["restart_attestation_event_id"])
            if recovered_canary["completed_restart_recovered"]
            else None
        )
        self._preactivation_recovered_snapshot_digest = (
            str(recovered_canary["empty_thread_snapshot_digest"])
            if recovered_canary["completed_restart_recovered"]
            else None
        )
        self._preactivation_causal_turn_recovery_pending = False
        self._preactivation_repair_complete.set()
        self._preactivation_release_admission_complete.set()
        self._preactivation_canary_complete.set()

    def _causal_completed_turn_recovery_is_pending(self) -> bool:
        """Recognize A/B process loss from SQLite without touching App Server."""

        try:
            if not self._causal_completed_admission_is_durable():
                return False
            state = self.registry.preactivation_causal_remediation_state()
            if state.get("status") != "completed":
                return False
            task_id = PREACTIVATION_STRUCTURAL_REPAIR_TASK_ID
            workstream_id = PREACTIVATION_STRUCTURAL_REPAIR_WORKSTREAM_ID
            task = self.registry.get_task(task_id)
            workstream = self.registry.get_workstream(workstream_id)
            executor = self.registry.current_executor(task_id, workstream_id)
            if (
                task is None
                or task.revision
                != PREACTIVATION_CAUSAL_REMEDIATION_SUCCESSOR_TASK_REVISION
                or workstream is None
                or workstream.generation
                != PREACTIVATION_CAUSAL_REMEDIATION_SUCCESSOR_WORKSTREAM_GENERATION
                or workstream.revision != 2
                or executor is None
                or executor.executor_generation
                != PREACTIVATION_CAUSAL_REMEDIATION_SUCCESSOR_EXECUTOR_GENERATION
            ):
                return False
            followups = [
                record
                for record in self.registry.list_outbox_records(
                    kinds=("codex_followup",)
                )
                if isinstance(record.get("payload"), Mapping)
                and record["payload"].get("task_id") == task_id
                and record["payload"].get("workstream_id") == workstream_id
                and record["payload"].get("task_revision")
                == PREACTIVATION_CAUSAL_REMEDIATION_SUCCESSOR_TASK_REVISION
                and record["payload"].get("workstream_revision") == 2
                and record["payload"].get("executor_generation")
                == PREACTIVATION_CAUSAL_REMEDIATION_SUCCESSOR_EXECUTOR_GENERATION
            ]
            if len(followups) != 1:
                return False
            current = followups[0]
            payload = self._validated_followup_payload(_mapping(current, "payload"))
            call_intent = payload.get("call_intent")
            canary_writer = current.get("writer_generation")
            if (
                current.get("state") != "pending"
                or int(current.get("attempts") or 0) not in {1, 2}
                or current.get("claim_token") is not None
                or current.get("claimed_generation") is not None
                or isinstance(canary_writer, bool)
                or not isinstance(canary_writer, int)
                or canary_writer >= self.engine.fence.generation
                or payload.get("call_policy") != CALL_POLICY_SINGLE_ATTEMPT_CANARY
                or payload.get("output_contract") != "checkpoint"
                or payload.get("model_attempt_count") != 1
                or payload.get("thread_id") != executor.thread_id
                or payload.get("host_id") != executor.host_id
                or payload.get("model") != CODEX_APP_SERVER_MODEL
                or payload.get("reasoning") != CODEX_APP_SERVER_REASONING_EFFORT
                or not isinstance(call_intent, Mapping)
                or call_intent.get("supervisor_generation") != canary_writer
                or call_intent.get("baseline_turn_ids") != []
            ):
                return False
            result_event_id = _event_id(
                "codex-result", str(current["event_id"])
            )
            checkpoints = self.registry.list_events(
                task_id=task_id, event_types=("checkpoint",)
            )
            if len(checkpoints) > 1 or (
                checkpoints
                and (
                    checkpoints[0].get("event_id") != result_event_id
                    or checkpoints[0].get("writer_generation") != canary_writer
                    or checkpoints[0].get("executor_generation")
                    != executor.executor_generation
                )
            ):
                return False
            return not (
                self.registry.list_events(
                    task_id=task_id, event_types=("codex_turn_receipt",)
                )
                or self.registry.list_events(
                    task_id=task_id,
                    event_types=("preactivation_causal_canary_turn_recovered",),
                )
                or self.registry.get_event(
                    _event_id(
                        "qualification-canary-failed", str(current["event_id"])
                    )
                )
            )
        except Exception:
            return False

    def _recover_preactivation_causal_completed_turn(self) -> bool:
        """Recover the one PR93 canary turn by an official read-only snapshot.

        This path is available only after a process boundary reclaimed the
        historical canary claim.  The raw checkpoint stays bound to the
        historical call-intent generation, while every newly persisted receipt
        is fenced by the current writer generation.  No resume or model call is
        permitted here; ambiguity falls through to the completed-epoch park.
        """

        try:
            if not self._causal_completed_admission_is_durable():
                return False
            state = self.registry.preactivation_causal_remediation_state()
            completion_id = state.get("completion_event_id")
            completion = (
                self.registry.get_event(str(completion_id))
                if isinstance(completion_id, str) and completion_id
                else None
            )
            completion_payload = (
                completion.get("payload") if completion is not None else None
            )
            task_id = PREACTIVATION_STRUCTURAL_REPAIR_TASK_ID
            workstream_id = PREACTIVATION_STRUCTURAL_REPAIR_WORKSTREAM_ID
            task = self.registry.get_task(task_id)
            workstream = self.registry.get_workstream(workstream_id)
            executor = self.registry.current_executor(task_id, workstream_id)
            if (
                state.get("status") != "completed"
                or completion is None
                or completion.get("event_type")
                != "preactivation_causal_remediation_completed"
                or not isinstance(completion_payload, Mapping)
                or task is None
                or task.revision
                != PREACTIVATION_CAUSAL_REMEDIATION_SUCCESSOR_TASK_REVISION
                or workstream is None
                or workstream.generation
                != PREACTIVATION_CAUSAL_REMEDIATION_SUCCESSOR_WORKSTREAM_GENERATION
                or workstream.revision != 2
                or executor is None
                or executor.executor_generation
                != PREACTIVATION_CAUSAL_REMEDIATION_SUCCESSOR_EXECUTOR_GENERATION
                or completion_payload.get("successor_thread_id")
                != executor.thread_id
                or completion_payload.get("successor_host_id") != executor.host_id
                or completion_payload.get("model") != CODEX_APP_SERVER_MODEL
                or completion_payload.get("reasoning")
                != CODEX_APP_SERVER_REASONING_EFFORT
            ):
                return False

            all_followups = list(
                self.registry.list_outbox_records(kinds=("codex_followup",))
            )
            source_followup_id = completion_payload.get("source_followup_event_id")
            source_followups = [
                record
                for record in all_followups
                if record.get("event_id") == source_followup_id
            ]
            current_followups = [
                record
                for record in all_followups
                if isinstance(record.get("payload"), Mapping)
                and record["payload"].get("task_id") == task_id
                and record["payload"].get("workstream_id") == workstream_id
                and record["payload"].get("task_revision")
                == PREACTIVATION_CAUSAL_REMEDIATION_SUCCESSOR_TASK_REVISION
                and record["payload"].get("workstream_revision") == 2
                and record["payload"].get("executor_generation")
                == PREACTIVATION_CAUSAL_REMEDIATION_SUCCESSOR_EXECUTOR_GENERATION
            ]
            if (
                len(all_followups) != 2
                or len(source_followups) != 1
                or len(current_followups) != 1
                or source_followups[0].get("state") != "delivered"
                or int(source_followups[0].get("attempts") or 0) != 1
                or source_followups[0].get("writer_generation")
                != PREACTIVATION_CAUSAL_REMEDIATION_EXPECTED_OUTPUT_GENERATION
            ):
                return False
            current = current_followups[0]
            payload = self._validated_followup_payload(_mapping(current, "payload"))
            call_intent = payload.get("call_intent")
            canary_writer = current.get("writer_generation")
            if (
                current.get("state") != "pending"
                or int(current.get("attempts") or 0) not in {1, 2}
                or current.get("claim_token") is not None
                or current.get("claimed_generation") is not None
                or isinstance(canary_writer, bool)
                or not isinstance(canary_writer, int)
                or canary_writer < int(completion["writer_generation"])
                or canary_writer >= self.engine.fence.generation
                or payload.get("schema") != FOLLOWUP_SCHEMA
                or payload.get("call_policy") != CALL_POLICY_SINGLE_ATTEMPT_CANARY
                or payload.get("output_contract") != "checkpoint"
                or payload.get("model_attempt_count") != 1
                or payload.get("thread_id") != executor.thread_id
                or payload.get("host_id") != executor.host_id
                or payload.get("model") != CODEX_APP_SERVER_MODEL
                or payload.get("reasoning") != CODEX_APP_SERVER_REASONING_EFFORT
                or payload.get("causal_fingerprint") is not None
                or payload.get("causal_binding") is not None
                or not isinstance(call_intent, Mapping)
                or call_intent.get("supervisor_generation") != canary_writer
                or call_intent.get("baseline_turn_ids") != []
            ):
                return False

            result_event_id = _event_id("codex-result", str(current["event_id"]))
            checkpoint_events = self.registry.list_events(
                task_id=task_id, event_types=("checkpoint",)
            )
            existing_result = self.registry.get_event(result_event_id)
            if (
                len(checkpoint_events) not in {0, 1}
                or (
                    len(checkpoint_events) == 1
                    and checkpoint_events[0].get("event_id") != result_event_id
                )
                or (existing_result is None) != (len(checkpoint_events) == 0)
                or self.registry.list_events(
                    task_id=task_id, event_types=("codex_turn_receipt",)
                )
                or self.registry.list_events(
                    task_id=task_id,
                    event_types=("preactivation_causal_canary_turn_recovered",),
                )
                or self.registry.get_event(
                    _event_id(
                        "qualification-canary-failed", str(current["event_id"])
                    )
                )
                is not None
            ):
                return False

            created_at_override: str | None = None
            if existing_result is not None:
                if (
                    existing_result.get("event_type") != "checkpoint"
                    or existing_result.get("task_id") != task_id
                    or existing_result.get("workstream_id") != workstream_id
                    or existing_result.get("executor_generation")
                    != executor.executor_generation
                    or existing_result.get("writer_generation") != canary_writer
                ):
                    return False
                created_at_override = self._persisted_result_created_at(
                    existing_result
                )

            # The only external operation in this recovery path is an official
            # retry-safe thread/read.  It occurs outside every registry
            # transaction and does not load or resume the historical thread.
            client = self._client(extra_owned=(executor.thread_id,))
            turn = client.recover_lost_turn_receipt(
                executor.thread_id,
                baseline_turn_ids=call_intent["baseline_turn_ids"],
                output_contract="checkpoint",
                expected_task_id=task_id,
                expected_workstream_id=workstream_id,
                expected_contract_generation=canary_writer,
            )
            turn_id = _machine("turn_id", turn.turn_id)
            lifecycle = tuple(turn.events)
            output_events = [
                event
                for event in lifecycle
                if event.method == "item/completed"
                and event.item_type == "agentMessage"
                and event.item_id is not None
            ]
            if (
                turn.thread_id != executor.thread_id
                or turn.status != "completed"
                or not isinstance(turn.contract, CodexCheckpoint)
                or len(lifecycle) != 2
                or {event.method for event in lifecycle}
                != {"item/completed", "turn/completed"}
                or {event.evidence_source for event in lifecycle}
                != {"thread_read_snapshot"}
                or any(event.thread_id != executor.thread_id for event in lifecycle)
                or any(event.turn_id != turn_id for event in lifecycle)
                or len(output_events) != 1
            ):
                return False
            output_item_id = _machine("item_id", output_events[0].item_id)
            canonical = self._canonical_result(
                turn,
                payload,
                task_revision=task.revision,
                workstream_revision=workstream.revision,
                executor_generation=executor.executor_generation,
                executor=ExecutorIdentity(
                    executor.thread_id,
                    executor.host_id,
                    executor.model,
                    executor.reasoning,
                ),
                result_event_id=result_event_id,
                created_at_override=created_at_override,
            )
            if not isinstance(canonical, Checkpoint):
                return False
            checkpoint_contract = contract_to_dict(canonical)
            checkpoint_payload = {
                "schema": "dev-control-plane/supervisor-event/v2",
                "contract": checkpoint_contract,
                "progress": canonical.progress_stage,
                "delta_ru": canonical.delta_ru,
                "current_ru": canonical.current_ru,
                "objective_invalidated": any(
                    item.startswith("objective_invalidation:")
                    for item in canonical.evidence
                ),
                "task_revision": canonical.task_revision,
                "workstream_revision": canonical.workstream_revision,
                "executor_generation": canonical.executor_generation,
                "created_at": canonical.created_at,
            }
            if (
                existing_result is not None
                and dict(existing_result.get("payload") or {})
                != checkpoint_payload
            ):
                return False

            lifecycle_payload = [
                {
                    "method": event.method,
                    "thread_id": event.thread_id,
                    "turn_id": event.turn_id,
                    "item_id": event.item_id,
                    "item_type": event.item_type,
                    "status": event.status,
                    "connection_epoch": event.connection_epoch,
                    "evidence_source": event.evidence_source,
                }
                for event in lifecycle
            ]
            lifecycle_digest = _sha256(
                json.dumps(
                    lifecycle_payload,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
            turn_receipt_event_id = _event_id("codex-turn-receipt", turn_id)
            turn_receipt_payload = {
                "schema": "dev-control-plane/codex-turn-receipt/v2",
                "followup_event_id": str(current["event_id"]),
                "contract_event_id": result_event_id,
                "contract_digest": _sha256(
                    json.dumps(
                        checkpoint_contract,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                ),
                "output_contract": "checkpoint",
                "thread_id": executor.thread_id,
                "turn_id": turn_id,
                "turn_status": "completed",
                "lifecycle_event_count": 2,
                "lifecycle_digest": lifecycle_digest,
                "lifecycle_methods": [],
                "structural_lifecycle_methods": [
                    "item/completed",
                    "turn/completed",
                ],
                "notification_lifecycle_methods": [],
                "snapshot_lifecycle_methods": [
                    "item/completed",
                    "turn/completed",
                ],
                "lifecycle_evidence_sources": ["thread_read_snapshot"],
                "item_ids": [output_item_id],
                "terminal_turn_ids": [turn_id],
                "model_attempt_count": 1,
                "model_call_count": 1,
                "recovery_model_call_count": 0,
                "receipt_source": "thread_read_recovery",
                "call_policy": CALL_POLICY_SINGLE_ATTEMPT_CANARY,
                "transport": "stdio",
                "websocket_used": False,
                "binary": str(self.codex_bin),
                "model": CODEX_APP_SERVER_MODEL,
                "reasoning": CODEX_APP_SERVER_REASONING_EFFORT,
                "contract_supervisor_generation": canary_writer,
                "supervisor_generation": self.engine.fence.generation,
                "task_revision": task.revision,
                "workstream_revision": workstream.revision,
                "executor_generation": executor.executor_generation,
                "created_at": canonical.created_at,
            }
            snapshot_digest = _sha256(
                json.dumps(
                    {
                        "thread_id": executor.thread_id,
                        "turn_id": turn_id,
                        "turn_status": turn.status,
                        "output_item_id": output_item_id,
                        "contract_digest": turn_receipt_payload[
                            "contract_digest"
                        ],
                        "lifecycle_digest": lifecycle_digest,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
            recovery_event_id = _event_id(
                "preactivation-causal-canary-turn-recovery",
                str(current["event_id"]),
            )
            recovery_payload = {
                "schema": (
                    "dev-control-plane/preactivation-causal-canary-turn-recovery/v3"
                ),
                "status": "recovered",
                "completion_event_id": str(completion_id),
                "followup_event_id": str(current["event_id"]),
                "checkpoint_event_id": result_event_id,
                "turn_receipt_event_id": turn_receipt_event_id,
                "task_id": task_id,
                "workstream_id": workstream_id,
                "executor_generation": executor.executor_generation,
                "thread_id": executor.thread_id,
                "turn_id": turn_id,
                "output_item_id": output_item_id,
                "thread_snapshot_digest": snapshot_digest,
                "contract_digest": turn_receipt_payload["contract_digest"],
                "contract_supervisor_generation": canary_writer,
                "recovery_writer_generation": self.engine.fence.generation,
                "read_method": "thread/read",
                "turn_count": 1,
                "model_call_performed": False,
                "raw_provider_body_stored": False,
            }
            self.registry.recover_preactivation_causal_canary_turn(
                followup_event_id=str(current["event_id"]),
                canary_writer_generation=canary_writer,
                checkpoint_event_id=result_event_id,
                checkpoint_payload=checkpoint_payload,
                turn_receipt_event_id=turn_receipt_event_id,
                turn_receipt_payload=turn_receipt_payload,
                recovery_event_id=recovery_event_id,
                recovery_payload=recovery_payload,
                fence=self.engine.fence,
            )
            return True
        except Exception:
            return False

    def _causal_completed_canary_evidence(
        self, *, allow_pending_receipt: bool = False
    ) -> dict[str, Any] | None:
        """Recover an already-receipted PR93 canary without touching Codex.

        This is intentionally a read-only fold.  A new Supervisor generation
        may observe the exact prior receipt repeatedly, but it may never turn
        that observation into a second thread read, resume, start, or model
        call.  Any ambiguity falls through to the existing fail-closed epoch
        loss park.
        """

        try:
            if not self._causal_completed_admission_is_durable():
                return None
            state = self.registry.preactivation_causal_remediation_state()
            completion_id = state.get("completion_event_id")
            completion = (
                self.registry.get_event(str(completion_id))
                if isinstance(completion_id, str) and completion_id
                else None
            )
            completion_payload = (
                completion.get("payload") if completion is not None else None
            )
            task_id = PREACTIVATION_STRUCTURAL_REPAIR_TASK_ID
            workstream_id = PREACTIVATION_STRUCTURAL_REPAIR_WORKSTREAM_ID
            task = self.registry.get_task(task_id)
            workstream = self.registry.get_workstream(workstream_id)
            executor = self.registry.current_executor(task_id, workstream_id)
            if (
                state.get("status") != "completed"
                or completion is None
                or completion.get("event_type")
                != "preactivation_causal_remediation_completed"
                or not isinstance(completion_payload, Mapping)
                or task is None
                or task.revision
                != PREACTIVATION_CAUSAL_REMEDIATION_SUCCESSOR_TASK_REVISION
                or workstream is None
                or workstream.generation
                != PREACTIVATION_CAUSAL_REMEDIATION_SUCCESSOR_WORKSTREAM_GENERATION
                or workstream.revision != 2
                or executor is None
                or executor.executor_generation
                != PREACTIVATION_CAUSAL_REMEDIATION_SUCCESSOR_EXECUTOR_GENERATION
                or completion_payload.get("successor_thread_id")
                != executor.thread_id
                or completion_payload.get("successor_host_id") != executor.host_id
                or completion_payload.get("model") != CODEX_APP_SERVER_MODEL
                or completion_payload.get("reasoning")
                != CODEX_APP_SERVER_REASONING_EFFORT
            ):
                return None

            all_followups = list(
                self.registry.list_outbox_records(kinds=("codex_followup",))
            )
            source_followup_id = completion_payload.get(
                "source_followup_event_id"
            )
            source_followups = [
                record
                for record in all_followups
                if record.get("event_id") == source_followup_id
            ]
            current_followups = [
                record
                for record in all_followups
                if isinstance(record.get("payload"), Mapping)
                and record["payload"].get("task_id") == task_id
                and record["payload"].get("workstream_id") == workstream_id
                and record["payload"].get("task_revision")
                == PREACTIVATION_CAUSAL_REMEDIATION_SUCCESSOR_TASK_REVISION
                and record["payload"].get("workstream_revision") == 2
                and record["payload"].get("executor_generation")
                == PREACTIVATION_CAUSAL_REMEDIATION_SUCCESSOR_EXECUTOR_GENERATION
            ]
            if (
                len(all_followups) != 2
                or len(source_followups) != 1
                or len(current_followups) != 1
                or source_followups[0].get("state") != "delivered"
                or int(source_followups[0].get("attempts") or 0) != 1
                or source_followups[0].get("writer_generation")
                != PREACTIVATION_CAUSAL_REMEDIATION_EXPECTED_OUTPUT_GENERATION
            ):
                return None
            current = current_followups[0]
            current_payload = self._validated_followup_payload(
                _mapping(current, "payload")
            )
            canary_writer = current.get("writer_generation")
            call_intent = current_payload.get("call_intent")
            if (
                current.get("state")
                not in (
                    {"delivered", "pending"}
                    if allow_pending_receipt
                    else {"delivered"}
                )
                or int(current.get("attempts") or 0) not in {1, 2}
                or isinstance(canary_writer, bool)
                or not isinstance(canary_writer, int)
                or canary_writer < int(completion["writer_generation"])
                or canary_writer >= self.engine.fence.generation
                or current_payload.get("schema") != FOLLOWUP_SCHEMA
                or current_payload.get("call_policy")
                != CALL_POLICY_SINGLE_ATTEMPT_CANARY
                or current_payload.get("output_contract") != "checkpoint"
                or current_payload.get("model_attempt_count") != 1
                or current_payload.get("thread_id") != executor.thread_id
                or current_payload.get("host_id") != executor.host_id
                or current_payload.get("model") != CODEX_APP_SERVER_MODEL
                or current_payload.get("reasoning")
                != CODEX_APP_SERVER_REASONING_EFFORT
                or current_payload.get("causal_fingerprint") is not None
                or current_payload.get("causal_binding") is not None
                or not isinstance(call_intent, Mapping)
                or call_intent.get("supervisor_generation") != canary_writer
                or call_intent.get("baseline_turn_ids") != []
            ):
                return None

            result_event_id = _event_id(
                "codex-result", str(current["event_id"])
            )
            checkpoint_event = self.registry.get_event(result_event_id)
            checkpoint_payload = (
                checkpoint_event.get("payload")
                if checkpoint_event is not None
                else None
            )
            contract_payload = (
                checkpoint_payload.get("contract")
                if isinstance(checkpoint_payload, Mapping)
                else None
            )
            if not isinstance(contract_payload, Mapping):
                return None
            from .orchestration_contracts import checkpoint_from_mapping

            checkpoint = checkpoint_from_mapping(contract_payload)
            checkpoint_writer = (
                checkpoint_event.get("writer_generation")
                if checkpoint_event is not None
                else None
            )
            if (
                checkpoint_event is None
                or checkpoint_event.get("event_type") != "checkpoint"
                or checkpoint_event.get("task_id") != task_id
                or checkpoint_event.get("workstream_id") != workstream_id
                or checkpoint_event.get("executor_generation")
                != executor.executor_generation
                or isinstance(checkpoint_writer, bool)
                or not isinstance(checkpoint_writer, int)
                or checkpoint_writer < canary_writer
                or checkpoint_writer > self.engine.fence.generation
                or checkpoint.event_id != result_event_id
                or checkpoint.task_id != task_id
                or checkpoint.task_revision != task.revision
                or checkpoint.workstream_id != workstream_id
                or checkpoint.workstream_revision != workstream.revision
                or checkpoint.executor_generation != executor.executor_generation
                or checkpoint.executor.thread_id != executor.thread_id
                or checkpoint.executor.host_id != executor.host_id
                or checkpoint.executor.model != CODEX_APP_SERVER_MODEL
                or checkpoint.executor.reasoning
                != CODEX_APP_SERVER_REASONING_EFFORT
            ):
                return None
            synthetic_message = OutboxMessage(
                event_id=str(current["event_id"]),
                kind="codex_followup",
                payload=dict(current_payload),
                task_id=task_id,
                coalescible=False,
                coalesce_key=None,
                attempts=int(current["attempts"]),
                claim_token="durable-read-only",
                claimed_generation=canary_writer,
                writer_generation=canary_writer,
            )
            receipts = self._turn_receipts_for_followup(
                synthetic_message, result_event_id
            )
            all_checkpoints = self.registry.list_events(
                task_id=task_id, event_types=("checkpoint",)
            )
            all_receipts = self.registry.list_events(
                task_id=task_id, event_types=("codex_turn_receipt",)
            )
            if (
                len(receipts) != 1
                or len(all_checkpoints) != 1
                or len(all_receipts) != 1
            ):
                return None
            receipt = receipts[0]
            receipt_payload = receipt["payload"]
            lifecycle_methods = receipt_payload.get("lifecycle_methods")
            turn_id = receipt_payload.get("turn_id")
            item_ids = receipt_payload.get("item_ids")
            receipt_writer = receipt.get("writer_generation")
            receipt_source = receipt_payload.get("receipt_source")
            recovery_events = self.registry.list_events(
                task_id=task_id,
                event_types=("preactivation_causal_canary_turn_recovered",),
            )
            live_receipt = bool(
                receipt_source == "live_notification"
                and receipt_writer == canary_writer
                and checkpoint_writer == canary_writer
                and isinstance(lifecycle_methods, list)
                and {"turn/started", "turn/completed"}.issubset(
                    set(lifecycle_methods)
                )
                and not recovery_events
            )
            recovery_event = (
                recovery_events[0] if len(recovery_events) == 1 else None
            )
            recovery_payload = (
                recovery_event.get("payload")
                if recovery_event is not None
                else None
            )
            recovered_receipt = bool(
                receipt_source == "thread_read_recovery"
                and isinstance(receipt_writer, int)
                and receipt_writer > canary_writer
                and checkpoint_writer in {canary_writer, receipt_writer}
                and lifecycle_methods == []
                and receipt_payload.get("notification_lifecycle_methods") == []
                and set(receipt_payload.get("snapshot_lifecycle_methods") or ())
                == {"item/completed", "turn/completed"}
                and receipt_payload.get("lifecycle_evidence_sources")
                == ["thread_read_snapshot"]
                and isinstance(recovery_payload, Mapping)
                and recovery_event.get("writer_generation") == receipt_writer
                and recovery_event.get("executor_generation")
                == executor.executor_generation
                and recovery_payload.get("schema")
                == "dev-control-plane/preactivation-causal-canary-turn-recovery/v3"
                and recovery_payload.get("status") == "recovered"
                and recovery_payload.get("completion_event_id") == completion_id
                and recovery_payload.get("followup_event_id")
                == current.get("event_id")
                and recovery_payload.get("checkpoint_event_id") == result_event_id
                and recovery_payload.get("turn_receipt_event_id")
                == receipt.get("event_id")
                and recovery_payload.get("task_id") == task_id
                and recovery_payload.get("workstream_id") == workstream_id
                and recovery_payload.get("executor_generation")
                == executor.executor_generation
                and recovery_payload.get("thread_id") == executor.thread_id
                and recovery_payload.get("turn_id") == turn_id
                and recovery_payload.get("output_item_id") in set(item_ids or ())
                and recovery_payload.get("contract_digest")
                == receipt_payload.get("contract_digest")
                and recovery_payload.get("contract_supervisor_generation")
                == canary_writer
                and recovery_payload.get("recovery_writer_generation")
                == receipt_writer
                and recovery_payload.get("read_method") == "thread/read"
                and recovery_payload.get("turn_count") == 1
                and isinstance(
                    recovery_payload.get("thread_snapshot_digest"), str
                )
                and re.fullmatch(
                    r"[0-9a-f]{64}",
                    str(recovery_payload.get("thread_snapshot_digest")),
                )
                is not None
                and recovery_payload.get("model_call_performed") is False
                and recovery_payload.get("raw_provider_body_stored") is False
            )
            if (
                isinstance(receipt_writer, bool)
                or not isinstance(receipt_writer, int)
                or receipt_writer < checkpoint_writer
                or receipt_writer > self.engine.fence.generation
                or receipt.get("executor_generation")
                != executor.executor_generation
                or receipt_payload.get("contract_supervisor_generation")
                != canary_writer
                or receipt_payload.get("supervisor_generation") != receipt_writer
                or receipt_payload.get("binary") != str(self.codex_bin)
                or not (live_receipt or recovered_receipt)
                or not isinstance(turn_id, str)
                or receipt_payload.get("terminal_turn_ids") != [turn_id]
                or not isinstance(item_ids, list)
                or not item_ids
                or int(receipt_payload.get("lifecycle_event_count") or 0) < 2
            ):
                return None

            failure_events = self.registry.list_events(
                task_id=task_id,
                event_types=("qualification_canary_failed",),
            )
            if (
                len(failure_events) != 1
                or failure_events[0].get("event_id")
                != completion_payload.get("source_failure_event_id")
                or any(
                    event.get("event_id")
                    == _event_id(
                        "qualification-canary-failed", str(current["event_id"])
                    )
                    for event in failure_events
                )
                or self.registry.list_events(
                    task_id=task_id,
                    event_types=(
                        "technical_terminal",
                        "owner_accepted",
                        "owner_acceptance",
                        "release_reserved",
                        "release_head_reserved",
                        "release_candidate_resolved",
                        "release_action_observed",
                        "release_completed",
                        "release_proof_only",
                    ),
                )
                or any(
                    record.get("task_id") == task_id
                    for record in self.registry.list_outbox_records(
                        kinds=PREACTIVATION_ORDINARY_POLICY_OUTBOX_KINDS
                    )
                )
                or any(
                    lock.owner_task_id == task_id
                    for lock in self.registry.inspect_locks()
                )
            ):
                return None

            restart_event_id = state.get("restart_attestation_event_id")
            restart_event = (
                self.registry.get_event(str(restart_event_id))
                if isinstance(restart_event_id, str) and restart_event_id
                else None
            )
            completed_restart = restart_event is not None
            snapshot_digest: str | None = None
            if completed_restart:
                restart_payload = restart_event.get("payload")
                if not isinstance(restart_payload, Mapping):
                    return None
                snapshot_digest = restart_payload.get("thread_snapshot_digest")
                if (
                    restart_event.get("event_type")
                    != "preactivation_causal_restart_attested"
                    or restart_event.get("task_id") != task_id
                    or restart_event.get("workstream_id") != workstream_id
                    or restart_event.get("executor_generation")
                    != executor.executor_generation
                    or restart_event.get("writer_generation") != canary_writer
                    or restart_payload.get("schema")
                    != "dev-control-plane/preactivation-causal-restart-attestation/v3"
                    or restart_payload.get("status")
                    != "empty_successor_recovered"
                    or restart_payload.get("completion_event_id") != completion_id
                    or restart_payload.get("task_id") != task_id
                    or restart_payload.get("workstream_id") != workstream_id
                    or restart_payload.get("executor_generation")
                    != executor.executor_generation
                    or restart_payload.get("thread_id") != executor.thread_id
                    or restart_payload.get("host_id") != executor.host_id
                    or restart_payload.get("model") != CODEX_APP_SERVER_MODEL
                    or restart_payload.get("reasoning")
                    != CODEX_APP_SERVER_REASONING_EFFORT
                    or restart_payload.get("read_method") != "thread/read"
                    or restart_payload.get("resume_method") != "thread/resume"
                    or restart_payload.get("turn_count") != 0
                    or not isinstance(snapshot_digest, str)
                    or re.fullmatch(r"[0-9a-f]{64}", snapshot_digest) is None
                    or restart_payload.get("supervisor_generation")
                    != canary_writer
                    or restart_payload.get("thread_start_performed") is not False
                    or restart_payload.get("model_call_performed") is not False
                    or restart_payload.get("raw_provider_body_stored") is not False
                ):
                    return None
            elif canary_writer != completion.get("writer_generation"):
                return None

            return {
                "canary_writer_generation": canary_writer,
                "checkpoint_writer_generation": checkpoint_writer,
                "receipt_writer_generation": receipt_writer,
                "outbox_state": str(current["state"]),
                "followup_event_id": str(current["event_id"]),
                "checkpoint_event_id": result_event_id,
                "turn_receipt_event_id": str(receipt["event_id"]),
                "completed_restart_recovered": completed_restart,
                "restart_attestation_event_id": (
                    str(restart_event_id) if completed_restart else ""
                ),
                "empty_thread_snapshot_digest": snapshot_digest,
                "turn_recovery_event_id": (
                    str(recovery_event["event_id"])
                    if recovery_event is not None
                    else ""
                ),
                "turn_recovery_writer_generation": (
                    int(recovery_event["writer_generation"])
                    if recovery_event is not None
                    else None
                ),
            }
        except Exception:
            return None

    def _causal_completed_restart_is_safe(self) -> bool:
        """Prove no executor3 call budget was consumed before a restart."""

        state = self.registry.preactivation_causal_remediation_state()
        completion_id = state.get("completion_event_id")
        completion = (
            self.registry.get_event(str(completion_id))
            if isinstance(completion_id, str) and completion_id
            else None
        )
        completion_payload = (
            completion.get("payload") if completion is not None else None
        )
        task = self.registry.get_task(PREACTIVATION_STRUCTURAL_REPAIR_TASK_ID)
        workstream = self.registry.get_workstream(
            PREACTIVATION_STRUCTURAL_REPAIR_WORKSTREAM_ID
        )
        executor = self.registry.current_executor(
            PREACTIVATION_STRUCTURAL_REPAIR_TASK_ID,
            PREACTIVATION_STRUCTURAL_REPAIR_WORKSTREAM_ID,
        )
        if (
            state.get("status") != "completed"
            or bool(state.get("restart_attestation_event_id"))
            or completion is None
            or completion.get("event_type")
            != "preactivation_causal_remediation_completed"
            or not isinstance(completion_payload, Mapping)
            or task is None
            or task.revision
            != PREACTIVATION_CAUSAL_REMEDIATION_SUCCESSOR_TASK_REVISION
            or workstream is None
            or workstream.generation
            != PREACTIVATION_CAUSAL_REMEDIATION_SUCCESSOR_WORKSTREAM_GENERATION
            or workstream.revision != 2
            or executor is None
            or executor.executor_generation
            != PREACTIVATION_CAUSAL_REMEDIATION_SUCCESSOR_EXECUTOR_GENERATION
            or completion_payload.get("successor_thread_id") != executor.thread_id
            or completion_payload.get("same_process_epoch") is not True
        ):
            return False
        canaries = [
            record
            for record in self.registry.list_outbox_records(
                kinds=("codex_followup",)
            )
            if isinstance(record.get("payload"), Mapping)
            and record["payload"].get("call_policy")
            == CALL_POLICY_SINGLE_ATTEMPT_CANARY
            and record["payload"].get("task_revision") == task.revision
            and record["payload"].get("workstream_revision")
            == workstream.revision
            and record["payload"].get("executor_generation")
            == executor.executor_generation
        ]
        if len(canaries) > 1 or any(
            int(record.get("attempts") or 0) > 1
            or int(record.get("payload", {}).get("model_attempt_count") or 0)
            > 0
            or record.get("payload", {}).get("call_intent") is not None
            or record.get("state") == "delivered"
            for record in canaries
        ):
            return False
        consumed_events = tuple(
            event
            for event in self.registry.list_events(
                task_id=PREACTIVATION_STRUCTURAL_REPAIR_TASK_ID,
                event_types=(
                    "checkpoint",
                    "codex_turn_receipt",
                    "qualification_canary_failed",
                    "technical_terminal",
                    "owner_accepted",
                    "owner_acceptance",
                ),
            )
            if event.get("executor_generation")
            == PREACTIVATION_CAUSAL_REMEDIATION_SUCCESSOR_EXECUTOR_GENERATION
        )
        return not consumed_events

    def _causal_completed_admission_is_durable(self) -> bool:
        """Rebuild only the exact already-admitted PR93 proof-only wait."""

        try:
            state = self.registry.preactivation_causal_remediation_state()
            completion = self.registry.get_event(
                str(state.get("completion_event_id") or "")
            )
            payload = completion.get("payload") if completion is not None else None
            if (
                state.get("status") != "completed"
                or completion is None
                or completion.get("event_type")
                != "preactivation_causal_remediation_completed"
                or not isinstance(payload, Mapping)
            ):
                return False
            task_id = PREACTIVATION_STRUCTURAL_REPAIR_TASK_ID
            workstream_id = PREACTIVATION_STRUCTURAL_REPAIR_WORKSTREAM_ID
            expected_head = payload.get("expected_pr_head_sha")
            merge_sha = payload.get("activation_release_sha")
            registration_id = payload.get("release_registration_event_id")
            intake_id = payload.get("release_intake_event_id")
            completion_writer = completion.get("writer_generation")
            if (
                payload.get("task_id") != task_id
                or payload.get("task_revision")
                != PREACTIVATION_CAUSAL_REMEDIATION_SUCCESSOR_TASK_REVISION
                or payload.get("workstream_id") != workstream_id
                or payload.get("workstream_generation")
                != PREACTIVATION_CAUSAL_REMEDIATION_SUCCESSOR_WORKSTREAM_GENERATION
                or payload.get("workstream_revision") != 2
                or not isinstance(expected_head, str)
                or not re.fullmatch(r"[0-9a-f]{40}", expected_head)
                or not isinstance(merge_sha, str)
                or not re.fullmatch(r"[0-9a-f]{40}", merge_sha)
                or not isinstance(registration_id, str)
                or not registration_id
                or not isinstance(intake_id, str)
                or not intake_id
                or isinstance(completion_writer, bool)
                or not isinstance(completion_writer, int)
            ):
                return False

            registration = self.registry.get_event(registration_id)
            registration_payload = (
                registration.get("payload") if registration is not None else None
            )
            if (
                registration is None
                or registration.get("event_type") != "release_candidate_registered"
                or registration.get("task_id") != task_id
                or registration.get("workstream_id") != workstream_id
                or registration.get("executor_generation") is not None
                or registration.get("writer_generation") != completion_writer
                or not isinstance(registration_payload, Mapping)
                or set(registration_payload)
                != {
                    "schema",
                    "task_id",
                    "task_revision",
                    "workstream_id",
                    "workstream_revision",
                    "expected_pr_head_sha",
                    "target_id",
                }
                or registration_payload
                != {
                    "schema": RELEASE_CANDIDATE_REGISTRATION_SCHEMA,
                    "task_id": task_id,
                    "task_revision": PREACTIVATION_CAUSAL_REMEDIATION_SUCCESSOR_TASK_REVISION,
                    "workstream_id": workstream_id,
                    "workstream_revision": 2,
                    "expected_pr_head_sha": expected_head,
                    "target_id": PREACTIVATION_STRUCTURAL_REPAIR_CANONICAL_TARGET,
                }
            ):
                return False

            intake_rows = [
                record
                for record in self.registry.list_outbox_records(
                    kinds=("release_candidate_intake",)
                )
                if record.get("event_id") == intake_id
            ]
            if len(intake_rows) != 1:
                return False
            intake = intake_rows[0]
            if (
                intake.get("task_id") != task_id
                or intake.get("state") != "delivered"
                or int(intake.get("attempts") or 0) != 1
                or intake.get("payload")
                != {
                    "schema": RELEASE_CANDIDATE_INTAKE_SCHEMA,
                    "registration_event_id": registration_id,
                    "task_id": task_id,
                    "workstream_id": workstream_id,
                    "expected_pr_head_sha": expected_head,
                }
            ):
                return False
            admission_events = [
                event
                for event in self.registry.list_events(
                    task_id=task_id,
                    workstream_id=workstream_id,
                    event_types=("release_candidate_admitted",),
                )
                if isinstance(event.get("payload"), Mapping)
                and event["payload"].get("source_event_id") == registration_id
            ]
            if len(admission_events) != 1:
                return False
            admission_event = admission_events[0]
            admission = admission_event["payload"]
            if (
                admission_event.get("executor_generation") is not None
                or admission_event.get("writer_generation")
                != intake.get("writer_generation")
                or set(admission)
                != {
                    "schema",
                    "source_event_id",
                    "candidate",
                    "release_candidate",
                    "target_adapter",
                    "scheduler_truth",
                    "proof_only",
                }
                or admission.get("schema") != RELEASE_CANDIDATE_ADMISSION_SCHEMA
                or admission.get("proof_only") is not True
                or admission.get("target_adapter")
                != "dev-control-plane-hosted-v2"
            ):
                return False
            candidate_raw = admission.get("candidate")
            release_raw = admission.get("release_candidate")
            truth = admission.get("scheduler_truth")
            if (
                not isinstance(candidate_raw, Mapping)
                or not isinstance(release_raw, Mapping)
                or not isinstance(truth, Mapping)
            ):
                return False
            candidate = release_candidate_from_mapping(candidate_raw)
            release_candidate = _release_train_candidate_from_mapping(release_raw)
            if (
                candidate.task_id != task_id
                or candidate.workstream_id != workstream_id
                or candidate.task_revision
                != PREACTIVATION_CAUSAL_REMEDIATION_SUCCESSOR_TASK_REVISION
                or candidate.workstream_revision != 2
                or candidate.target_id
                != PREACTIVATION_STRUCTURAL_REPAIR_CANONICAL_TARGET
                or candidate.pr_head_sha != expected_head
                or candidate.checks_green is not True
                or candidate.admission_ready is not False
                or candidate.merge_conflict
                or candidate.passport_diff_mismatch
                or candidate.unknown_classification
                or candidate.multiple_safe_orders
                or not candidate.multi_pr_intent
                or release_candidate.repo
                != PREACTIVATION_STRUCTURAL_REPAIR_CANONICAL_TARGET
                or release_candidate.pr_number != 93
                or release_candidate.base_ref != "main"
                or tuple(release_candidate.required_checks)
                != ("v2-suite", "self-closure")
            ):
                return False
            self._assert_registered_candidate_current(candidate)
            self._validate_resolved_release_candidate(candidate, release_candidate)
            validated_truth = self._validated_intake_scheduler_truth(candidate, truth)
            if (
                validated_truth.get("pr_state") != "MERGED"
                or validated_truth.get("merge_commit_sha") != merge_sha
                or validated_truth.get("checks_green") is not True
                or validated_truth.get("admission_ready") is not False
                or any(
                    validated_truth.get(field) is not False
                    for field in (
                        "merge_conflict",
                        "passport_diff_mismatch",
                        "unknown_classification",
                    )
                )
            ):
                return False
            admission_digest = _sha256(
                json.dumps(
                    admission,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
            if not self.registry.preactivation_causal_admission_receipt_is_processed(
                source_event_id=registration_id,
                candidate_id=candidate.candidate_id,
                pr_head_sha=expected_head,
                admission_digest=admission_digest,
                writer_generation=int(admission_event["writer_generation"]),
            ):
                return False
            waits = [
                event
                for event in self.registry.list_events(
                    task_id=task_id,
                    workstream_id=workstream_id,
                    event_types=("release_wait",),
                )
                if isinstance(event.get("payload"), Mapping)
                and event["payload"].get("candidates") == [dict(candidate_raw)]
            ]
            if len(waits) != 1:
                return False
            wait = waits[0]
            if (
                wait.get("executor_generation") is not None
                or wait.get("writer_generation")
                != admission_event.get("writer_generation")
                or set(wait["payload"])
                != {"schema", "decision", "candidates", "created_at"}
                or wait["payload"].get("schema")
                != "dev-control-plane/supervisor-event/v2"
                or wait["payload"].get("decision")
                != {
                    "kind": "wait",
                    "candidate_ids": [],
                    "reason": "dependencies_not_complete",
                    "semantic_case": None,
                }
            ):
                return False
            if any(
                record.get("task_id") == task_id
                for record in self.registry.list_outbox_records(
                    kinds=("release_candidate_resolution", "release_action")
                )
            ):
                return False
            if self.registry.list_events(
                task_id=task_id,
                event_types=(
                    "release_reserved",
                    "release_head_reserved",
                    "release_candidate_resolved",
                    "release_action_observed",
                    "release_completed",
                    "release_proof_only",
                ),
            ):
                return False
            if any(
                lock.owner_task_id == task_id for lock in self.registry.inspect_locks()
            ):
                return False
            return True
        except Exception:
            return False

    def _validated_activation_identity(
        self,
        identity: Mapping[str, Any] | None,
    ) -> dict[str, Any] | None:
        if identity is None:
            return None
        expected = {
            "schema", "release_sha", "activation_nonce_sha256", "pid",
            "python_executable", "entrypoint", "bind_host", "bind_port",
        }
        if set(identity) != expected or identity.get("schema") != "dev-control-plane/runtime-activation/v2":
            raise SupervisorRuntimeError("runtime activation identity fields are invalid")
        for key in ("release_sha", "activation_nonce_sha256"):
            value = identity.get(key)
            length = 40 if key == "release_sha" else 64
            if not isinstance(value, str) or not re.fullmatch(rf"[0-9a-f]{{{length}}}", value):
                raise SupervisorRuntimeError(f"runtime activation {key} is invalid")
        if identity.get("pid") != os.getpid():
            raise SupervisorRuntimeError("runtime activation PID is not this process")
        if identity.get("bind_host") != "127.0.0.1" or identity.get("bind_port") != 8766:
            raise SupervisorRuntimeError("runtime activation bind identity is outside the approved loopback")
        for key in ("python_executable", "entrypoint"):
            value = identity.get(key)
            if not isinstance(value, str) or not Path(value).is_absolute():
                raise SupervisorRuntimeError(f"runtime activation {key} is invalid")
        return dict(identity)

    def local_state(self) -> dict[str, Any]:
        state = self.engine.local_state()
        queues = self.registry.list_outbox_summaries(kinds=("codex_thread_start", "codex_followup"))
        return {
            **state,
            "runtime": {
                "command_transport": "private_unix_socket",
                "http_mutation_enabled": False,
                "codex_queue_pending": sum(item["state"] == "pending" for item in queues),
                "codex_queue_inflight": sum(item["state"] == "inflight" for item in queues),
                "codex_queue_delivered": sum(item["state"] == "delivered" for item in queues),
                "codex": self.health()["codex_runtime"],
            },
            "qualification_evidence": self._qualification_evidence(),
        }

    def _qualification_evidence(self) -> dict[str, Any]:
        activation = self.health().get("activation_identity")
        release_sha = activation.get("release_sha") if isinstance(activation, Mapping) else None
        qualification_resource = (
            f"qualification:{release_sha}" if isinstance(release_sha, str) else None
        )
        receipts: list[Mapping[str, Any]] = []
        for event in self.registry.list_events(event_types=("codex_turn_receipt",)):
            payload = event.get("payload", {})
            provenance_generation = event.get("writer_generation")
            if (
                not isinstance(payload, Mapping)
                or type(provenance_generation) is not int
                or not 1 <= provenance_generation <= self.engine.fence.generation
                or payload.get("supervisor_generation") != provenance_generation
                or not isinstance(qualification_resource, str)
            ):
                continue
            task_id = event.get("task_id")
            workstream_id = event.get("workstream_id")
            if not isinstance(task_id, str) or not isinstance(workstream_id, str):
                continue
            task = self.registry.get_task(task_id)
            workstream = self.registry.get_workstream(workstream_id)
            if task is None or workstream is None or workstream.task_id != task_id:
                continue
            passport = task_passport_from_mapping(task.passport)
            workstream_contract = workstream_from_mapping(workstream.contract)
            executor = self.registry.current_executor(task_id, workstream_id)
            if (
                task.revision != payload.get("task_revision")
                or workstream.revision != payload.get("workstream_revision")
                or qualification_resource not in passport.resources
                or qualification_resource not in workstream_contract.resources
                or executor is None
                or event.get("executor_generation") != executor.executor_generation
                or payload.get("executor_generation") != executor.executor_generation
                or payload.get("thread_id") != executor.thread_id
                or payload.get("model") != executor.model
                or payload.get("reasoning") != executor.reasoning
            ):
                continue
            receipts.append(event)
        checkpoint_receipts = [
            event for event in receipts
            if event.get("payload", {}).get("output_contract") == "checkpoint"
        ]
        total_model_calls = sum(
            int(event.get("payload", {}).get("model_call_count") or 0) for event in receipts
        )
        unsafe_policy_work = tuple(
            record
            for record in self.registry.list_outbox_records(
                kinds=PREACTIVATION_ORDINARY_POLICY_OUTBOX_KINDS
            )
            if record.get("state") in {"pending", "inflight"}
            or (
                record.get("state") == "delivered"
                and record.get("writer_generation")
                == self.engine.fence.generation
            )
        )
        arbiter_attempts = tuple(
            record
            for record in unsafe_policy_work
            if record.get("kind")
            in {"release_arbiter_case", "incident_arbiter_case"}
            and int(record.get("attempts") or 0) > 0
        )
        canary_records: list[Mapping[str, Any]] = []
        if isinstance(qualification_resource, str):
            for record in self.registry.list_outbox_records(kinds=("codex_followup",)):
                payload = record.get("payload")
                provenance_generation = record.get("writer_generation")
                if (
                    not isinstance(payload, Mapping)
                    or type(provenance_generation) is not int
                    or not 1 <= provenance_generation <= self.engine.fence.generation
                    or payload.get("schema") != FOLLOWUP_SCHEMA
                    or payload.get("call_policy") != CALL_POLICY_SINGLE_ATTEMPT_CANARY
                ):
                    continue
                task_id = payload.get("task_id")
                workstream_id = payload.get("workstream_id")
                if not isinstance(task_id, str) or not isinstance(workstream_id, str):
                    continue
                task = self.registry.get_task(task_id)
                workstream = self.registry.get_workstream(workstream_id)
                if task is None or workstream is None or workstream.task_id != task_id:
                    continue
                passport = task_passport_from_mapping(task.passport)
                contract = workstream_from_mapping(workstream.contract)
                executor = self.registry.current_executor(task_id, workstream_id)
                if (
                    payload.get("task_revision") != task.revision
                    or payload.get("workstream_revision") != workstream.revision
                    or qualification_resource not in passport.resources
                    or qualification_resource not in contract.resources
                    or executor is None
                    or payload.get("executor_generation") != executor.executor_generation
                    or payload.get("thread_id") != executor.thread_id
                    or payload.get("model") != executor.model
                    or payload.get("reasoning") != executor.reasoning
                ):
                    continue
                canary_records.append(record)
        attempt_records = [
            record
            for record in canary_records
            if isinstance(record.get("payload", {}).get("call_intent"), Mapping)
            and record["payload"]["call_intent"].get("supervisor_generation")
            == record.get("writer_generation")
        ]
        total_model_attempts = sum(
            int(record.get("payload", {}).get("model_attempt_count") or 0)
            for record in attempt_records
        )
        qualification_failure_events: list[Mapping[str, Any]] = []
        for record in canary_records:
            followup_event_id = record.get("event_id")
            if not isinstance(followup_event_id, str):
                continue
            failure = self.registry.get_event(
                _event_id("qualification-canary-failed", followup_event_id)
            )
            failure_payload = failure.get("payload") if failure is not None else None
            attempt_payload = record.get("payload")
            if (
                failure is not None
                and isinstance(failure_payload, Mapping)
                and isinstance(attempt_payload, Mapping)
                and failure.get("task_id") == attempt_payload.get("task_id")
                and failure.get("workstream_id") == attempt_payload.get("workstream_id")
                and failure.get("executor_generation")
                == attempt_payload.get("executor_generation")
                and failure_payload.get("followup_event_id") == followup_event_id
                and failure_payload.get("decision") == "stop_qualification"
            ):
                qualification_failure_events.append(failure)
        selected_receipt = checkpoint_receipts[0] if len(checkpoint_receipts) == 1 else None
        checkpoint_event: Mapping[str, Any] | None = None
        selected_attempt: Mapping[str, Any] | None = None
        executor: Any | None = None
        if selected_receipt is not None:
            receipt_payload = selected_receipt["payload"]
            checkpoint_event = self.registry.get_event(str(receipt_payload["contract_event_id"]))
            selected_attempts = [
                record
                for record in attempt_records
                if record.get("event_id") == receipt_payload.get("followup_event_id")
            ]
            selected_attempt = selected_attempts[0] if len(selected_attempts) == 1 else None
            executor = self.registry.current_executor(
                str(selected_receipt["task_id"]),
                str(selected_receipt["workstream_id"]),
            )
        receipt_payload = selected_receipt.get("payload", {}) if selected_receipt is not None else {}
        checkpoint_payload = checkpoint_event.get("payload", {}) if checkpoint_event is not None else {}
        selected_canary_writer_generation = (
            selected_attempt.get("writer_generation")
            if selected_attempt is not None
            else None
        )
        selected_checkpoint_writer_generation = (
            checkpoint_event.get("writer_generation")
            if checkpoint_event is not None
            else None
        )
        selected_receipt_writer_generation = (
            selected_receipt.get("writer_generation")
            if selected_receipt is not None
            else None
        )
        socket_path = default_socket_path(self.registry.db_path.parent)
        try:
            socket_metadata = socket_path.lstat()
            socket_private = (
                stat.S_ISSOCK(socket_metadata.st_mode)
                and stat.S_IMODE(socket_metadata.st_mode) == 0o600
                and socket_metadata.st_uid == os.getuid()
            )
            socket_mode = format(stat.S_IMODE(socket_metadata.st_mode), "04o")
            socket_owner_uid: int | None = socket_metadata.st_uid
        except OSError:
            socket_private = False
            socket_mode = ""
            socket_owner_uid = None
        generation = self.registry.current_generation()
        lease_live = (
            generation.get("generation") == self.engine.fence.generation
            and generation.get("owner_id") == self.engine.fence.owner_id
            and float(generation.get("expires_at") or 0) > self.clock()
        )
        lifecycle_methods = receipt_payload.get("lifecycle_methods")
        live_lifecycle_ok = (
            receipt_payload.get("receipt_source") == "live_notification"
            and isinstance(lifecycle_methods, list)
            and {"turn/started", "turn/completed"}.issubset(set(lifecycle_methods))
            and receipt_payload.get("turn_id") in set(receipt_payload.get("terminal_turn_ids") or ())
            and int(receipt_payload.get("lifecycle_event_count") or 0) >= 2
        )
        recovered_lifecycle_ok = (
            receipt_payload.get("receipt_source") == "thread_read_recovery"
            and lifecycle_methods == []
            and receipt_payload.get("notification_lifecycle_methods") == []
            and set(receipt_payload.get("snapshot_lifecycle_methods") or ())
            == {"item/completed", "turn/completed"}
            and receipt_payload.get("lifecycle_evidence_sources")
            == ["thread_read_snapshot"]
            and receipt_payload.get("turn_id")
            in set(receipt_payload.get("terminal_turn_ids") or ())
            and int(receipt_payload.get("lifecycle_event_count") or 0) == 2
        )
        lifecycle_ok = live_lifecycle_ok or recovered_lifecycle_ok
        selected_task_id = selected_receipt.get("task_id") if selected_receipt else None
        terminal_events = (
            self.registry.list_events(
                task_id=str(selected_task_id),
                event_types=("technical_terminal",),
            )
            if isinstance(selected_task_id, str)
            else ()
        )
        resolved_attention_ids = {
            str(payload["resolved_attention_event_id"])
            for event in self.registry.list_events(
                task_id=str(selected_task_id) if isinstance(selected_task_id, str) else None,
                event_types=("attention_resolved",),
            )
            for payload in (event.get("payload"),)
            if isinstance(payload, Mapping)
            and payload.get("schema") == "dev-control-plane/attention-resolution/v2"
            and payload.get("status") == "resolved"
            and isinstance(payload.get("resolved_attention_event_id"), str)
        }
        attention_records = tuple(
            item
            for item in self.registry.list_outbox_records(kinds=("curator_attention",))
            if item.get("task_id") == selected_task_id
            and item.get("state") != "superseded"
            and item.get("event_id") not in resolved_attention_ids
        )
        final_attention_deferred = not terminal_events and not attention_records
        progress = checkpoint_payload.get("progress")
        checkpoint_digest = (
            _sha256(
                json.dumps(
                    checkpoint_payload,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
            if checkpoint_event is not None
            else None
        )
        attempt_payload = selected_attempt.get("payload", {}) if selected_attempt is not None else {}
        single_attempt_canary = (
            attempt_payload.get("call_policy") == CALL_POLICY_SINGLE_ATTEMPT_CANARY
            and receipt_payload.get("call_policy") == CALL_POLICY_SINGLE_ATTEMPT_CANARY
        )
        turn_recovery_events = [
            event
            for event in self.registry.list_events(
                task_id=(
                    str(selected_task_id)
                    if isinstance(selected_task_id, str)
                    else None
                ),
                event_types=("preactivation_causal_canary_turn_recovered",),
            )
            if isinstance(event.get("payload"), Mapping)
            and selected_attempt is not None
            and event["payload"].get("followup_event_id")
            == selected_attempt.get("event_id")
        ]
        turn_recovery_event = (
            turn_recovery_events[0] if len(turn_recovery_events) == 1 else None
        )
        turn_recovery_payload = (
            turn_recovery_event.get("payload")
            if turn_recovery_event is not None
            else None
        )
        live_turn_receipt_valid = bool(
            live_lifecycle_ok
            and (
                receipt_payload.get("contract_supervisor_generation")
                == selected_canary_writer_generation
                or (
                    not self.preactivation_causal_remediation_mode
                    and receipt_payload.get("contract_supervisor_generation")
                    is None
                )
            )
            and selected_checkpoint_writer_generation
            == selected_canary_writer_generation
            and selected_receipt_writer_generation
            == selected_canary_writer_generation
            and not turn_recovery_events
            and self._preactivation_turn_recovery_event_id is None
        )
        recovered_turn_receipt_valid = bool(
            recovered_lifecycle_ok
            and isinstance(selected_canary_writer_generation, int)
            and isinstance(selected_checkpoint_writer_generation, int)
            and isinstance(selected_receipt_writer_generation, int)
            and selected_canary_writer_generation
            < selected_receipt_writer_generation
            and selected_checkpoint_writer_generation
            in {
                selected_canary_writer_generation,
                selected_receipt_writer_generation,
            }
            and receipt_payload.get("contract_supervisor_generation")
            == selected_canary_writer_generation
            and isinstance(turn_recovery_payload, Mapping)
            and turn_recovery_event.get("writer_generation")
            == selected_receipt_writer_generation
            and self._preactivation_turn_recovery_event_id
            == turn_recovery_event.get("event_id")
            and turn_recovery_payload.get("schema")
            == "dev-control-plane/preactivation-causal-canary-turn-recovery/v3"
            and turn_recovery_payload.get("status") == "recovered"
            and turn_recovery_payload.get("followup_event_id")
            == selected_attempt.get("event_id")
            and turn_recovery_payload.get("checkpoint_event_id")
            == receipt_payload.get("contract_event_id")
            and turn_recovery_payload.get("turn_receipt_event_id")
            == selected_receipt.get("event_id")
            and turn_recovery_payload.get("task_id") == selected_task_id
            and turn_recovery_payload.get("workstream_id")
            == selected_receipt.get("workstream_id")
            and turn_recovery_payload.get("executor_generation")
            == receipt_payload.get("executor_generation")
            and turn_recovery_payload.get("thread_id")
            == receipt_payload.get("thread_id")
            and turn_recovery_payload.get("turn_id")
            == receipt_payload.get("turn_id")
            and turn_recovery_payload.get("output_item_id")
            in set(receipt_payload.get("item_ids") or ())
            and turn_recovery_payload.get("contract_digest")
            == receipt_payload.get("contract_digest")
            and turn_recovery_payload.get("contract_supervisor_generation")
            == selected_canary_writer_generation
            and turn_recovery_payload.get("recovery_writer_generation")
            == selected_receipt_writer_generation
            and turn_recovery_payload.get("read_method") == "thread/read"
            and turn_recovery_payload.get("turn_count") == 1
            and isinstance(
                turn_recovery_payload.get("thread_snapshot_digest"), str
            )
            and re.fullmatch(
                r"[0-9a-f]{64}",
                str(turn_recovery_payload.get("thread_snapshot_digest")),
            )
            is not None
            and turn_recovery_payload.get("model_call_performed") is False
            and turn_recovery_payload.get("raw_provider_body_stored") is False
        )
        causal_remediation_evidence: dict[str, Any] | None = None
        causal_remediation_passed = not self.preactivation_causal_remediation_mode
        if self.preactivation_causal_remediation_mode:
            causal_state = self.registry.preactivation_causal_remediation_state()
            remediation_event_id = causal_state.get("remediation_event_id")
            completion_event_id = causal_state.get("completion_event_id")
            attestation_event_id = causal_state.get("causal_attestation_event_id")
            remediation_event = (
                self.registry.get_event(str(remediation_event_id))
                if isinstance(remediation_event_id, str) and remediation_event_id
                else None
            )
            completion_event = (
                self.registry.get_event(str(completion_event_id))
                if isinstance(completion_event_id, str) and completion_event_id
                else None
            )
            attestation_event = (
                self.registry.get_event(str(attestation_event_id))
                if isinstance(attestation_event_id, str) and attestation_event_id
                else None
            )
            remediation_payload = (
                remediation_event.get("payload")
                if remediation_event is not None
                and remediation_event.get("event_type")
                == "preactivation_causal_remediation"
                else None
            )
            completion_payload = (
                completion_event.get("payload")
                if completion_event is not None
                and completion_event.get("event_type")
                == "preactivation_causal_remediation_completed"
                else None
            )
            durable_attestation = (
                attestation_event.get("payload")
                if attestation_event is not None
                and attestation_event.get("event_type")
                == "preactivation_causal_attestation"
                else None
            )
            causal_read_event_id = causal_state.get("causal_read_event_id")
            successor_event_id = causal_state.get("successor_event_id")
            causal_read_records = [
                record
                for record in self.registry.list_outbox_records(
                    kinds=("codex_preactivation_causal_read",)
                )
                if record.get("event_id") == causal_read_event_id
            ]
            successor_records = [
                record
                for record in self.registry.list_outbox_records(
                    kinds=("codex_preactivation_causal_successor_start",)
                )
                if record.get("event_id") == successor_event_id
            ]
            source_failure_event = (
                self.registry.get_event(
                    str(remediation_payload.get("source_failure_event_id"))
                )
                if isinstance(remediation_payload, Mapping)
                and isinstance(
                    remediation_payload.get("source_failure_event_id"), str
                )
                else None
            )
            source_followup_records = [
                record
                for record in self.registry.list_outbox_records(
                    kinds=("codex_followup",)
                )
                if isinstance(remediation_payload, Mapping)
                and record.get("event_id")
                == remediation_payload.get("source_followup_event_id")
            ]
            registration_event_id = (
                completion_payload.get("release_registration_event_id")
                if isinstance(completion_payload, Mapping)
                else None
            )
            admission_events = [
                event
                for event in self.registry.list_events(
                    task_id=PREACTIVATION_STRUCTURAL_REPAIR_TASK_ID,
                    workstream_id=PREACTIVATION_STRUCTURAL_REPAIR_WORKSTREAM_ID,
                    event_types=("release_candidate_admitted",),
                )
                if isinstance(event.get("payload"), Mapping)
                and event["payload"].get("source_event_id")
                == registration_event_id
            ]
            causal_read_record = (
                causal_read_records[0] if len(causal_read_records) == 1 else None
            )
            successor_record = (
                successor_records[0] if len(successor_records) == 1 else None
            )
            source_followup_record = (
                source_followup_records[0]
                if len(source_followup_records) == 1
                else None
            )
            admission_event = (
                admission_events[0] if len(admission_events) == 1 else None
            )
            causal_writer_generation = (
                remediation_event.get("writer_generation")
                if remediation_event is not None
                else None
            )
            successor_writer_generation = (
                completion_event.get("writer_generation")
                if completion_event is not None
                else None
            )
            admission_writer_generation = (
                admission_event.get("writer_generation")
                if admission_event is not None
                else None
            )
            canary_writer_generation = selected_canary_writer_generation

            def evidence_digest(value: Any) -> str | None:
                if not isinstance(value, Mapping):
                    return None
                return _sha256(
                    json.dumps(
                        value,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                )
            attestation_digest: str | None = None
            base_attestation: Mapping[str, Any] | None = None
            attestation_valid = False
            if isinstance(durable_attestation, Mapping):
                base_attestation = {
                    key: value
                    for key, value in durable_attestation.items()
                    if key
                    not in {
                        "attestation_digest",
                        "attested_writer_generation",
                        "attested_at",
                    }
                }
                try:
                    self._validated_preactivation_causal_attestation(
                        base_attestation
                    )
                except Exception:
                    attestation_valid = False
                else:
                    attestation_digest = _sha256(
                        json.dumps(
                            base_attestation,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                    )
                    attestation_valid = (
                        durable_attestation.get("attestation_digest")
                        == attestation_digest
                    )
            prior_model_attempt_count = (
                1
                if isinstance(remediation_payload, Mapping)
                and remediation_payload.get("source_model_attempt_count") == 1
                else 0
            )
            prior_completed_turn_count = (
                1
                if isinstance(base_attestation, Mapping)
                and base_attestation.get("turn_count") == 1
                and base_attestation.get("turn_status") == "completed"
                else 0
            )
            # Registry admission proves there was no PR92 turn receipt.  The
            # official completed thread/read proves the real invocation even
            # though the old receipt-derived counter is necessarily zero.
            prior_turn_receipt_count = 0
            prior_real_model_invocation_count = (
                1
                if prior_model_attempt_count == 1
                and prior_completed_turn_count == 1
                and attestation_valid
                else 0
            )
            current_model_attempt_count = total_model_attempts
            current_completed_turn_count = (
                1 if receipt_payload.get("turn_status") == "completed" else 0
            )
            current_turn_receipt_count = len(receipts)
            current_real_model_invocation_count = total_model_calls
            cumulative_real_model_invocation_count = (
                prior_real_model_invocation_count
                + current_real_model_invocation_count
            )
            restart_attestation_event_id = causal_state.get(
                "restart_attestation_event_id"
            )
            restart_attestation = (
                self.registry.get_event(str(restart_attestation_event_id))
                if isinstance(restart_attestation_event_id, str)
                and restart_attestation_event_id
                else None
            )
            restart_payload = (
                restart_attestation.get("payload")
                if restart_attestation is not None
                and restart_attestation.get("event_type")
                == "preactivation_causal_restart_attested"
                else None
            )
            restart_attestation_valid = (
                not self._preactivation_causal_completed_restart
                and restart_attestation is None
                and not restart_attestation_event_id
                and self._preactivation_restart_attestation_event_id is None
                and self._preactivation_recovered_snapshot_digest is None
            ) or bool(
                self._preactivation_causal_completed_restart
                and isinstance(restart_payload, Mapping)
                and restart_attestation_event_id
                == self._preactivation_restart_attestation_event_id
                and restart_payload.get("schema")
                == "dev-control-plane/preactivation-causal-restart-attestation/v3"
                and restart_payload.get("status")
                == "empty_successor_recovered"
                and restart_payload.get("completion_event_id")
                == completion_event_id
                and restart_payload.get("thread_id")
                == receipt_payload.get("thread_id")
                and restart_payload.get("executor_generation")
                == PREACTIVATION_CAUSAL_REMEDIATION_SUCCESSOR_EXECUTOR_GENERATION
                and restart_payload.get("model") == CODEX_APP_SERVER_MODEL
                and restart_payload.get("reasoning")
                == CODEX_APP_SERVER_REASONING_EFFORT
                and restart_payload.get("read_method") == "thread/read"
                and restart_payload.get("resume_method") == "thread/resume"
                and restart_payload.get("turn_count") == 0
                and restart_payload.get("thread_snapshot_digest")
                == self._preactivation_recovered_snapshot_digest
                and restart_payload.get("supervisor_generation")
                == canary_writer_generation
                and restart_payload.get("thread_start_performed") is False
                and restart_payload.get("model_call_performed") is False
                and restart_payload.get("raw_provider_body_stored") is False
                and restart_attestation.get("writer_generation")
                == canary_writer_generation
                and isinstance(canary_writer_generation, int)
                and canary_writer_generation <= self.engine.fence.generation
            )
            durable_canary_recovery_valid = (
                self._preactivation_durable_canary_recovered
                and self._preactivation_canary_complete.is_set()
                and self._preactivation_canary_writer_generation
                == canary_writer_generation
                and isinstance(canary_writer_generation, int)
                and canary_writer_generation < self.engine.fence.generation
            ) or (
                not self._preactivation_durable_canary_recovered
                and self._preactivation_canary_writer_generation is None
                and canary_writer_generation == self.engine.fence.generation
            )
            causal_remediation_passed = bool(
                causal_state.get("status") == "completed"
                and isinstance(remediation_payload, Mapping)
                and isinstance(completion_payload, Mapping)
                and isinstance(causal_writer_generation, int)
                and isinstance(successor_writer_generation, int)
                and isinstance(admission_writer_generation, int)
                and isinstance(canary_writer_generation, int)
                and isinstance(selected_checkpoint_writer_generation, int)
                and isinstance(selected_receipt_writer_generation, int)
                and PREACTIVATION_CAUSAL_REMEDIATION_EXPECTED_OUTPUT_GENERATION
                < causal_writer_generation
                <= successor_writer_generation
                <= admission_writer_generation
                <= canary_writer_generation
                <= selected_checkpoint_writer_generation
                <= selected_receipt_writer_generation
                <= self.engine.fence.generation
                and causal_read_record is not None
                and causal_read_record.get("state") == "delivered"
                and int(causal_read_record.get("attempts") or 0) in {1, 2}
                and causal_read_record.get("writer_generation")
                == causal_writer_generation
                and successor_record is not None
                and successor_record.get("state") == "delivered"
                and int(successor_record.get("attempts") or 0) in {1, 2}
                and successor_record.get("writer_generation")
                == successor_writer_generation
                and attestation_event is not None
                and attestation_event.get("writer_generation")
                == causal_writer_generation
                and remediation_event is not None
                and remediation_event.get("writer_generation")
                == causal_writer_generation
                and completion_event is not None
                and completion_event.get("writer_generation")
                == successor_writer_generation
                and admission_event is not None
                and selected_attempt is not None
                and selected_attempt.get("state") == "delivered"
                and int(selected_attempt.get("attempts") or 0) in {1, 2}
                and selected_attempt.get("writer_generation")
                == canary_writer_generation
                and selected_receipt is not None
                and checkpoint_event is not None
                and (live_turn_receipt_valid or recovered_turn_receipt_valid)
                and source_failure_event is not None
                and source_followup_record is not None
                and attestation_valid
                and remediation_payload.get("causal_attestation_digest")
                == attestation_digest
                and completion_payload.get("causal_attestation_digest")
                == attestation_digest
                and completion_payload.get("remediation_event_id")
                == remediation_event_id
                and completion_payload.get("causal_attestation_event_id")
                == attestation_event_id
                and completion_payload.get("source_failure_event_id")
                == remediation_payload.get("source_failure_event_id")
                and completion_payload.get("source_followup_event_id")
                == remediation_payload.get("source_followup_event_id")
                and completion_payload.get("strategy_resource")
                == PREACTIVATION_CAUSAL_STRATEGY_RESOURCE
                and completion_payload.get("strategy_digest")
                == _sha256(PREACTIVATION_CAUSAL_STRATEGY_RESOURCE)
                and prior_model_attempt_count == 1
                and prior_completed_turn_count == 1
                and prior_turn_receipt_count == 0
                and prior_real_model_invocation_count == 1
                and current_model_attempt_count == 1
                and current_completed_turn_count == 1
                and current_turn_receipt_count == 1
                and current_real_model_invocation_count == 1
                and cumulative_real_model_invocation_count == 2
                and restart_attestation_valid
                and durable_canary_recovery_valid
                and self._causal_completed_admission_is_durable()
                and (
                    not self._preactivation_causal_completed_restart
                    or (
                        isinstance(
                            self._preactivation_recovered_snapshot_digest, str
                        )
                        and re.fullmatch(
                            r"[0-9a-f]{64}",
                            self._preactivation_recovered_snapshot_digest,
                        )
                        is not None
                    )
                )
            )
            causal_remediation_evidence = {
                "schema": (
                    "dev-control-plane/preactivation-causal-qualification-evidence/v3"
                ),
                "status": "passed" if causal_remediation_passed else "blocked",
                "observed_at": _iso(self.clock()),
                "root_replacement_sha": (
                    PREACTIVATION_STRUCTURAL_REPAIR_PREDECESSOR_SHA
                ),
                "structural_bridge_sha": (
                    PREACTIVATION_CAUSAL_REMEDIATION_PR92_MERGE_SHA
                ),
                "activation_release_sha": (
                    completion_payload.get("activation_release_sha")
                    if isinstance(completion_payload, Mapping)
                    else None
                ),
                "expected_pr_head_sha": (
                    completion_payload.get("expected_pr_head_sha")
                    if isinstance(completion_payload, Mapping)
                    else None
                ),
                "task_id": PREACTIVATION_STRUCTURAL_REPAIR_TASK_ID,
                "workstream_id": PREACTIVATION_STRUCTURAL_REPAIR_WORKSTREAM_ID,
                "supervisor_id": self.engine.supervisor_id,
                "causal_writer_generation": causal_writer_generation,
                "successor_writer_generation": successor_writer_generation,
                "admission_writer_generation": admission_writer_generation,
                "canary_writer_generation": canary_writer_generation,
                "checkpoint_writer_generation": (
                    selected_checkpoint_writer_generation
                ),
                "receipt_writer_generation": selected_receipt_writer_generation,
                "contract_supervisor_generation": receipt_payload.get(
                    "contract_supervisor_generation"
                ),
                "source_failure_event_id": (
                    remediation_payload.get("source_failure_event_id")
                    if isinstance(remediation_payload, Mapping)
                    else None
                ),
                "source_failure_event_sha256": evidence_digest(
                    source_failure_event.get("payload")
                    if source_failure_event is not None
                    else None
                ),
                "source_followup_event_id": (
                    remediation_payload.get("source_followup_event_id")
                    if isinstance(remediation_payload, Mapping)
                    else None
                ),
                "source_followup_payload_sha256": (
                    source_followup_record.get("payload_digest")
                    if source_followup_record is not None
                    else None
                ),
                "causal_read_event_id": causal_read_event_id,
                "causal_read_payload_sha256": (
                    causal_read_record.get("payload_digest")
                    if causal_read_record is not None
                    else None
                ),
                "causal_attestation_event_id": attestation_event_id,
                "causal_attestation_event_sha256": evidence_digest(
                    durable_attestation
                ),
                "causal_attestation_digest": attestation_digest,
                "observed_contract_generation": (
                    base_attestation.get("observed_identity", {}).get(
                        "generation"
                    )
                    if isinstance(base_attestation, Mapping)
                    and isinstance(
                        base_attestation.get("observed_identity"), Mapping
                    )
                    else None
                ),
                "required_historical_supervisor_generation": (
                    base_attestation.get("expected_identity", {}).get(
                        "generation"
                    )
                    if isinstance(base_attestation, Mapping)
                    and isinstance(
                        base_attestation.get("expected_identity"), Mapping
                    )
                    else None
                ),
                "mismatched_fields": (
                    list(base_attestation.get("mismatched_fields") or ())
                    if isinstance(base_attestation, Mapping)
                    else []
                ),
                "remediation_event_id": remediation_event_id,
                "remediation_event_sha256": evidence_digest(
                    remediation_payload
                ),
                "completion_event_id": completion_event_id,
                "completion_event_sha256": evidence_digest(completion_payload),
                "successor_event_id": successor_event_id,
                "successor_payload_sha256": (
                    successor_record.get("payload_digest")
                    if successor_record is not None
                    else None
                ),
                "current_followup_event_id": (
                    selected_attempt.get("event_id")
                    if selected_attempt is not None
                    else None
                ),
                "current_followup_payload_sha256": (
                    selected_attempt.get("payload_digest")
                    if selected_attempt is not None
                    else None
                ),
                "current_checkpoint_event_id": (
                    checkpoint_event.get("event_id")
                    if checkpoint_event is not None
                    else None
                ),
                "current_checkpoint_event_sha256": evidence_digest(
                    checkpoint_event.get("payload")
                    if checkpoint_event is not None
                    else None
                ),
                "current_turn_receipt_event_id": (
                    selected_receipt.get("event_id")
                    if selected_receipt is not None
                    else None
                ),
                "current_turn_receipt_event_sha256": evidence_digest(
                    selected_receipt.get("payload")
                    if selected_receipt is not None
                    else None
                ),
                "predecessor_executor_generation": (
                    completion_payload.get("predecessor_executor_generation")
                    if isinstance(completion_payload, Mapping)
                    else None
                ),
                "successor_executor_generation": (
                    completion_payload.get("successor_executor_generation")
                    if isinstance(completion_payload, Mapping)
                    else None
                ),
                "predecessor_thread_id": (
                    completion_payload.get("predecessor_thread_id")
                    if isinstance(completion_payload, Mapping)
                    else None
                ),
                "predecessor_host_id": (
                    completion_payload.get("predecessor_host_id")
                    if isinstance(completion_payload, Mapping)
                    else None
                ),
                "successor_thread_id": (
                    completion_payload.get("successor_thread_id")
                    if isinstance(completion_payload, Mapping)
                    else None
                ),
                "successor_host_id": (
                    completion_payload.get("successor_host_id")
                    if isinstance(completion_payload, Mapping)
                    else None
                ),
                "strategy_resource": PREACTIVATION_CAUSAL_STRATEGY_RESOURCE,
                "strategy_digest": _sha256(
                    PREACTIVATION_CAUSAL_STRATEGY_RESOURCE
                ),
                "same_app_server_epoch": bool(
                    isinstance(completion_payload, Mapping)
                    and completion_payload.get("same_process_epoch") is True
                    and restart_attestation_valid
                    and live_turn_receipt_valid
                ),
                "raw_provider_body_stored": False,
                "prior_model_attempt_count": prior_model_attempt_count,
                "prior_completed_turn_count": prior_completed_turn_count,
                "prior_turn_receipt_count": prior_turn_receipt_count,
                "prior_real_model_invocation_count": (
                    prior_real_model_invocation_count
                ),
                "current_model_attempt_count": current_model_attempt_count,
                "current_completed_turn_count": current_completed_turn_count,
                "current_turn_receipt_count": current_turn_receipt_count,
                "current_real_model_invocation_count": (
                    current_real_model_invocation_count
                ),
                "cumulative_real_model_invocation_count": (
                    cumulative_real_model_invocation_count
                ),
                "completed_restart_recovered": (
                    self._preactivation_causal_completed_restart
                ),
                "restart_attestation_event_id": (
                    str(restart_attestation_event_id)
                    if restart_attestation_event_id
                    else ""
                ),
                "restart_attestation_writer_generation": (
                    restart_attestation.get("writer_generation")
                    if restart_attestation is not None
                    else None
                ),
                "empty_thread_snapshot_digest": (
                    self._preactivation_recovered_snapshot_digest
                ),
                "durable_canary_recovered": (
                    self._preactivation_durable_canary_recovered
                ),
                "turn_receipt_recovered": recovered_turn_receipt_valid,
                "turn_recovery_event_id": (
                    str(turn_recovery_event["event_id"])
                    if turn_recovery_event is not None
                    else ""
                ),
                "turn_recovery_writer_generation": (
                    turn_recovery_event.get("writer_generation")
                    if turn_recovery_event is not None
                    else None
                ),
                "recovery_supervisor_generation": (
                    self.engine.fence.generation
                    if self._preactivation_durable_canary_recovered
                    else None
                ),
            }
        canary_passed = (
            activation is not None
            and causal_remediation_passed
            and len(receipts) == 1
            and len(checkpoint_receipts) == 1
            and len(canary_records) == 1
            and len(attempt_records) == 1
            and total_model_attempts == 1
            and total_model_calls == 1
            and not unsafe_policy_work
            and executor is not None
            and executor.thread_id == receipt_payload.get("thread_id")
            and executor.model == CODEX_APP_SERVER_MODEL
            and executor.reasoning == CODEX_APP_SERVER_REASONING_EFFORT
            and receipt_payload.get("binary") == str(self.codex_bin)
            and receipt_payload.get("transport") == "stdio"
            and receipt_payload.get("websocket_used") is False
            and receipt_payload.get("turn_status") == "completed"
            and receipt_payload.get("model_attempt_count") == 1
            and lifecycle_ok
            and (live_turn_receipt_valid or recovered_turn_receipt_valid)
            and single_attempt_canary
            and not qualification_failure_events
            and checkpoint_event is not None
            and checkpoint_event.get("event_type") == "checkpoint"
            and selected_attempt is not None
            and checkpoint_event.get("task_id") == selected_receipt.get("task_id")
            and checkpoint_event.get("workstream_id") == selected_receipt.get("workstream_id")
            and isinstance(progress, int)
            and not isinstance(progress, bool)
            and progress in {5, 15, 25, 40, 55, 65, 72, 80, 88, 95}
            and final_attention_deferred
        )
        staged_passed = (
            activation is not None
            and causal_remediation_passed
            and socket_private
            and lease_live
            and final_attention_deferred
            and total_model_attempts == 1
            and total_model_calls == 1
            and not unsafe_policy_work
        )
        return {
            "schema": "dev-control-plane/runtime-qualification-evidence/v2",
            "status": "passed" if canary_passed and staged_passed else "blocked",
            "release_sha": activation.get("release_sha") if isinstance(activation, Mapping) else None,
            "observed_at": _iso(self.clock()),
            "app_server_canary": {
                "schema": "dev-control-plane/app-server-canary-evidence/v2",
                "status": "passed" if canary_passed else "blocked",
                # A post-receipt restart may observe this immutable canary
                # from a newer live fence.  Preserve the actual call/receipt
                # writer; staged_runtime below reports the observing fence.
                "supervisor_generation": selected_canary_writer_generation,
                "supervisor_host": self.engine.supervisor_id,
                "binary": str(self.codex_bin),
                "transport": "stdio",
                "websocket_used": False,
                "task_id": selected_receipt.get("task_id") if selected_receipt else None,
                "workstream_id": selected_receipt.get("workstream_id") if selected_receipt else None,
                "thread_id": receipt_payload.get("thread_id"),
                "model": getattr(executor, "model", None),
                "reasoning": getattr(executor, "reasoning", None),
                "executor_host_id": getattr(executor, "host_id", None),
                "executor_generation": getattr(executor, "executor_generation", None),
                "turn_ids": [receipt_payload["turn_id"]] if receipt_payload.get("turn_id") else [],
                "item_ids": list(receipt_payload.get("item_ids") or ()),
                "lifecycle_event_count": int(receipt_payload.get("lifecycle_event_count") or 0),
                "lifecycle_digest": receipt_payload.get("lifecycle_digest"),
                "terminal_turn_ids": list(receipt_payload.get("terminal_turn_ids") or ()),
                "model_attempt_count": total_model_attempts,
                "model_call_count": total_model_calls,
                "single_attempt_canary": single_attempt_canary,
                "contract_kind": "checkpoint" if selected_receipt is not None else None,
                "progress_percent": progress,
                "checkpoint_event_id": (
                    checkpoint_event.get("event_id") if checkpoint_event is not None else None
                ),
                "checkpoint_payload_sha256": checkpoint_digest,
            },
            "staged_runtime": {
                "schema": "dev-control-plane/staged-runtime-evidence/v2",
                "status": "passed" if staged_passed else "blocked",
                "private_socket": socket_private,
                "socket_mode": socket_mode,
                "socket_owner_uid": socket_owner_uid,
                "single_writer": lease_live,
                "supervisor_generation": self.engine.fence.generation,
                "supervisor_owner_id": self.engine.fence.owner_id,
                "lease_expires_at_epoch": generation.get("expires_at"),
                "final_attention_deferred": final_attention_deferred,
                "additional_model_calls": max(
                    0,
                    total_model_calls - 1,
                    len(arbiter_attempts),
                ),
                "activation_identity": activation,
            },
            **(
                {"causal_remediation": causal_remediation_evidence}
                if causal_remediation_evidence is not None
                else {}
            ),
        }

    def close(self) -> None:
        self._closed = True
        with self._client_lock:
            if self._codex_client is not None:
                self._codex_client.shutdown()
                self._codex_client = None
            self._resumed_threads.clear()
            self._fresh_thread_epochs.clear()
            self._preactivation_recovered_empty_thread_epochs.clear()

    def _command_register(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        _exact_fields(payload, {"passport", "workstream", "message_id"}, "register payload")
        passport_raw = _mapping(payload, "passport")
        workstream_raw = _mapping(payload, "workstream")
        message_id = _machine("message_id", payload.get("message_id"))
        with self._mutation_lock:
            return self.engine.register(
                task_passport_from_mapping(passport_raw),
                workstream_from_mapping(workstream_raw),
                message_id=message_id,
                source="private-unix-command",
            )

    def _command_checkpoint(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        from .orchestration_contracts import checkpoint_from_mapping

        _exact_fields(payload, {"checkpoint", "message_id"}, "checkpoint payload")
        with self._mutation_lock:
            return self.engine.import_checkpoint(
                checkpoint_from_mapping(_mapping(payload, "checkpoint")),
                message_id=_machine("message_id", payload.get("message_id")),
                source="private-unix-command",
            )

    def _command_terminal(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        from .orchestration_contracts import terminal_evidence_from_mapping

        _exact_fields(payload, {"terminal", "message_id"}, "terminal payload")
        terminal = terminal_evidence_from_mapping(_mapping(payload, "terminal"))
        with self._mutation_lock:
            return self.engine.import_terminal(
                terminal,
                message_id=_machine("message_id", payload.get("message_id")),
                source="private-unix-command",
            )

    def _command_owner_acceptance(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        _exact_fields(payload, {"receipt", "source_attestation", "message_id"}, "owner acceptance payload")
        if self.owner_acceptance_verifier is None:
            raise SupervisorCommandError("owner acceptance bridge is unavailable; acceptance remains pending")
        receipt = owner_acceptance_from_mapping(_mapping(payload, "receipt"))
        attestation = _mapping(payload, "source_attestation")
        _exact_fields(
            attestation,
            {
                "schema", "curator_thread_id", "source_message_id", "attention_event_id",
                "observed_at_epoch", "reply_sha256", "signature",
            },
            "owner acceptance source attestation",
        )
        if attestation.get("schema") != "dev-control-plane/owner-acceptance-source/v2":
            raise SupervisorCommandError("owner acceptance source schema mismatch")
        for key in ("curator_thread_id", "source_message_id", "attention_event_id"):
            _machine(key, attestation.get(key))
        observed_at = attestation.get("observed_at_epoch")
        if isinstance(observed_at, bool) or not isinstance(observed_at, (int, float)):
            raise SupervisorCommandError("owner acceptance observation timestamp is invalid")
        for key in ("reply_sha256", "signature"):
            value = attestation.get(key)
            if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
                raise SupervisorCommandError(f"owner acceptance {key} is invalid")
        if attestation["curator_thread_id"] != receipt.curator_thread_id:
            raise SupervisorCommandError("owner acceptance source thread mismatch")
        # The supported bridge verifier is external to SQLite and receives no
        # authority to mutate the registry.
        if self.owner_acceptance_verifier(receipt, attestation) is not True:
            raise SupervisorCommandError("owner acceptance source was not independently attested")
        with self._mutation_lock:
            task = self.registry.get_task(receipt.task_id)
            if task is None or task.revision != receipt.task_revision:
                raise SupervisorCommandError("owner acceptance task revision is stale")
            # Reuse the engine's current-revision/current-generation closure
            # barrier fold. A multi-workstream task has several terminal
            # events, but exactly one of them owns the task-level attention.
            terminals = self.engine._technical_closure_events(task)
            barriers = [
                item for item in terminals
                if item.get("payload", {}).get("closure_barrier") is True
            ]
            if len(barriers) != 1:
                raise SupervisorCommandError(
                    "owner acceptance requires exactly one current task-level closure barrier"
                )
            attention_event_id = _machine(
                "attention_event_id",
                barriers[0].get("payload", {}).get("curator_event_id"),
            )
            attention = next(
                (
                    item
                    for item in self.registry.list_outbox_summaries(kinds=("curator_attention",))
                    if item["event_id"] == attention_event_id
                ),
                None,
            )
            if (
                attestation["attention_event_id"] != attention_event_id
                or attention is None
                or attention["state"] != "delivered"
            ):
                raise SupervisorCommandError("owner acceptance is not bound to a delivered pending attention")
            if not self._target_lane_ready_for_attention(task.task_id, task.revision):
                raise SupervisorCommandError(
                    "owner acceptance is waiting for exact target lane closure readback"
                )
            return self.engine.owner_accept(
                receipt,
                message_id=_machine("message_id", payload.get("message_id")),
                source="private-unix-command",
            )

    def _command_register_release_candidate(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Persist only an immutable PR-head registration supplied by a caller.

        Scheduler policy fields are deliberately absent from this command. The
        intake worker derives them from current registry/Passport state and an
        exact registered GitHub resolver after this durable receipt exists.
        """

        _exact_fields(
            payload,
            {"task_id", "workstream_id", "expected_pr_head_sha", "message_id"},
            "release candidate registration payload",
        )
        task_id = _machine("task_id", payload.get("task_id"))
        workstream_id = _machine("workstream_id", payload.get("workstream_id"))
        expected_head = payload.get("expected_pr_head_sha")
        if not isinstance(expected_head, str) or not re.fullmatch(r"[0-9a-f]{40}", expected_head):
            raise SupervisorCommandError("expected_pr_head_sha must be an exact lowercase Git SHA")
        message_id = _machine("message_id", payload.get("message_id"))
        with self._mutation_lock:
            task = self.registry.get_task(task_id)
            workstream = self.registry.get_workstream(workstream_id)
            if task is None or workstream is None or workstream.task_id != task_id:
                raise SupervisorCommandError("release candidate is not a current registered workstream")
            passport = task_passport_from_mapping(task.passport)
            if (
                task.state in {"accepted", "parked"}
                or workstream.state != "waiting_release"
                or not passport.contour.startswith("release:")
            ):
                raise SupervisorCommandError("release candidate workstream is not waiting for release")
            target_id = self._passport_release_target(passport)
            registration = {
                "schema": RELEASE_CANDIDATE_REGISTRATION_SCHEMA,
                "task_id": task_id,
                "task_revision": task.revision,
                "workstream_id": workstream_id,
                "workstream_revision": workstream.revision,
                "expected_pr_head_sha": expected_head,
                "target_id": target_id,
            }
            event_id = _event_id(
                "release-candidate-registration",
                json.dumps(registration, sort_keys=True, separators=(",", ":")),
            )
            intake_event_id = _event_id("release-candidate-intake", event_id)
            created = self.registry.record_input_event_outbox(
                message_id=message_id,
                source="private-unix-command:release-candidate-registration",
                input_payload={
                    "task_id": task_id,
                    "workstream_id": workstream_id,
                    "expected_pr_head_sha": expected_head,
                },
                event_id=event_id,
                event_type="release_candidate_registered",
                event_payload=registration,
                outbox_items=(
                    {
                        "event_id": intake_event_id,
                        "kind": "release_candidate_intake",
                        "payload": {
                            "schema": RELEASE_CANDIDATE_INTAKE_SCHEMA,
                            "registration_event_id": event_id,
                            "task_id": task_id,
                            "workstream_id": workstream_id,
                            "expected_pr_head_sha": expected_head,
                        },
                        "task_id": task_id,
                        "coalescible": False,
                        "coalesce_key": None,
                    },
                    self._dirty_item(event_id, task_id),
                ),
                fence=self.engine.fence,
                task_id=task_id,
                workstream_id=workstream_id,
            )
        return {
            "created": created,
            "registration_event_id": event_id,
            "intake_event_id": intake_event_id,
            "task_id": task_id,
            "workstream_id": workstream_id,
            "expected_pr_head_sha": expected_head,
        }

    def _command_revise_release_manifest(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Finalize or append only the immutable release chain of one Passport."""

        _exact_fields(
            payload,
            {"task_id", "expected_revision", "release_manifest", "message_id"},
            "release manifest revision payload",
        )
        task_id = _machine("task_id", payload.get("task_id"))
        expected_revision = payload.get("expected_revision")
        if (
            isinstance(expected_revision, bool)
            or not isinstance(expected_revision, int)
            or expected_revision < 1
        ):
            raise SupervisorCommandError("release manifest expected_revision must be positive")
        manifest_raw = _mapping(payload, "release_manifest")
        _exact_fields(
            manifest_raw,
            set(ReleaseClosureManifest.__dataclass_fields__),
            "release closure manifest",
        )
        try:
            manifest = ReleaseClosureManifest(**dict(manifest_raw))
        except Exception as exc:
            raise SupervisorCommandError("release closure manifest is invalid") from exc
        message_id = _machine("message_id", payload.get("message_id"))
        with self._mutation_lock:
            task = self.registry.get_task(task_id)
            if task is None:
                raise SupervisorCommandError("release manifest task is unknown")
            passport = task_passport_from_mapping(task.passport)
            if task.state in {"accepted", "parked"}:
                raise SupervisorCommandError("release manifest cannot revise an accepted or parked task")
            if task.revision != expected_revision:
                # An exact replay is admitted below by its durable event even
                # after later revisions; any new stale request fails closed.
                event_id = _event_id(
                    "passport-release-manifest-revised",
                    f"{task_id}|r{expected_revision + 1}|{_manifest_digest(manifest)}",
                )
                existing = self.registry.get_event(event_id)
                if (
                    existing is not None
                    and existing.get("payload", {}).get("release_manifest")
                    == contract_to_dict(manifest)
                ):
                    return {
                        "created": False,
                        "task_id": task_id,
                        "revision": expected_revision + 1,
                        "superseded_release_outbox": int(
                            existing["payload"].get("superseded_release_outbox") or 0
                        ),
                        "released_reservation_locks": int(
                            existing["payload"].get("released_reservation_locks") or 0
                        ),
                        "event_id": event_id,
                    }
                raise SupervisorCommandError("release manifest revision is stale")
            current_terminals = tuple(
                event
                for event in self.registry.list_events(
                    task_id=task_id,
                    event_types=("technical_terminal",),
                )
                if isinstance(event.get("payload"), Mapping)
                and isinstance(event["payload"].get("contract"), Mapping)
                and event["payload"]["contract"].get("task_revision")
                == task.revision
            )
            if current_terminals or task.state == "acceptance_pending":
                raise SupervisorCommandError(
                    "release manifest cannot revise after current terminal evidence"
                )
            if not passport.contour.startswith("release:"):
                raise SupervisorCommandError("non-release task cannot receive a release manifest")
            previous = passport.release_manifest
            if previous is not None:
                if previous.logical_lane_id != manifest.logical_lane_id:
                    raise SupervisorCommandError("release manifest logical lane cannot change")
                if tuple(manifest.pr_identities[: len(previous.pr_identities)]) != tuple(
                    previous.pr_identities
                ) or len(manifest.pr_identities) < len(previous.pr_identities):
                    raise SupervisorCommandError("release manifest PR chain must be append-only")
                if tuple(manifest.deploy_identities[: len(previous.deploy_identities)]) != tuple(
                    previous.deploy_identities
                ) or len(manifest.deploy_identities) < len(previous.deploy_identities):
                    raise SupervisorCommandError("release manifest deploy chain must be append-only")
                previous_time = datetime.fromisoformat(previous.finalized_at.replace("Z", "+00:00"))
                new_time = datetime.fromisoformat(manifest.finalized_at.replace("Z", "+00:00"))
                if new_time <= previous_time:
                    raise SupervisorCommandError("release manifest finalized_at must advance")
            revised = replace(
                passport,
                revision=expected_revision + 1,
                release_manifest=manifest,
            )
            manifest_digest = _manifest_digest(manifest)
            event_id = _event_id(
                "passport-release-manifest-revised",
                f"{task_id}|r{revised.revision}|{manifest_digest}",
            )
            event_payload = {
                "schema": "dev-control-plane/passport-revised/v2",
                "task_id": task_id,
                "old_revision": expected_revision,
                "new_revision": revised.revision,
                "release_manifest": contract_to_dict(manifest),
                "release_manifest_digest": manifest_digest,
                "revised_at": _iso(self.clock()),
            }
            result = self.registry.replace_task_passport_with_event(
                revised,
                expected_revision=expected_revision,
                message_id=message_id,
                source="private-unix-command:release-manifest-revision",
                input_payload={
                    "task_id": task_id,
                    "expected_revision": expected_revision,
                    "release_manifest": contract_to_dict(manifest),
                },
                event_id=event_id,
                event_payload=event_payload,
                outbox_items=(self._dirty_item(event_id, task_id),),
                fence=self.engine.fence,
            )
        return result

    def _passport_release_target(self, passport: TaskPassport) -> str:
        targets = tuple(
            item.removeprefix("target:")
            for item in passport.resources
            if item.startswith("target:")
        )
        if len(targets) != 1 or not targets[0]:
            raise SupervisorCommandError(
                "release Passport must declare exactly one target:<target-id> resource"
            )
        return targets[0]

    def _passport_logical_lane(self, passport: TaskPassport, workstream_id: str, target_id: str) -> str:
        declared = tuple(
            item.removeprefix("release-lane:")
            for item in passport.resources
            if item.startswith("release-lane:")
        )
        if len(declared) != 1 or not declared[0]:
            raise SupervisorRuntimeError("Passport release lane declaration is not exact")
        return declared[0]

    def _require_release_actuator_authorization(
        self,
        task_id: str,
        *,
        include_lane_release: bool,
    ) -> TaskPassport:
        task = self.registry.get_task(task_id)
        if task is None:
            raise SupervisorRuntimeError("release actuator task disappeared")
        passport = task_passport_from_mapping(task.passport)
        target_id = self._passport_release_target(passport)
        actions = set(required_release_actions(passport.contour, target_id))
        if not include_lane_release:
            actions.discard("target_lane_release")
        for action in sorted(actions):
            require_passport_action(passport, action)
        return passport

    def _passport_owner_priority(self, passport: TaskPassport) -> int | None:
        values = tuple(
            item.removeprefix("owner-priority:")
            for item in passport.resources
            if item.startswith("owner-priority:")
        )
        if not values:
            return None
        if len(values) != 1 or not re.fullmatch(r"[0-9]{1,9}", values[0]):
            raise SupervisorRuntimeError("Passport owner priority declaration is invalid")
        return int(values[0])

    def _passport_scheduler_resources(self, passport: TaskPassport) -> tuple[str, ...]:
        resources = tuple(
            item
            for item in passport.resources
            if not item.startswith(("target:", "release-lane:", "owner-priority:"))
        )
        if not resources:
            raise SupervisorRuntimeError(
                "release Passport has no classified scheduler resource beyond routing metadata"
            )
        return resources

    def _execute_release_candidate_intake(
        self,
        message: OutboxMessage,
        *,
        preactivation_safe: bool = False,
    ) -> RuntimeWorkerResult:
        base_fields = {
            "schema", "registration_event_id", "task_id", "workstream_id",
            "expected_pr_head_sha",
        }
        refresh_fields = {
            "semantic_case_id", "semantic_case_digest", "refresh_cycle",
        }
        observed_fields = set(message.payload)
        if observed_fields not in {frozenset(base_fields), frozenset(base_fields | refresh_fields)}:
            raise SupervisorRuntimeError("release candidate intake fields are not exact")
        if refresh_fields <= observed_fields:
            _machine("semantic_case_id", message.payload.get("semantic_case_id"))
            _digest_value(
                "semantic_case_digest", message.payload.get("semantic_case_digest")
            )
            refresh_cycle = message.payload.get("refresh_cycle")
            if (
                isinstance(refresh_cycle, bool)
                or not isinstance(refresh_cycle, int)
                or refresh_cycle < 1
            ):
                raise SupervisorRuntimeError(
                    "release plan refresh cycle must be positive"
                )
        if message.payload.get("schema") != RELEASE_CANDIDATE_INTAKE_SCHEMA:
            raise SupervisorRuntimeError("release candidate intake schema mismatch")
        registration_event_id = _machine(
            "registration_event_id", message.payload.get("registration_event_id")
        )
        registration_event = self.registry.get_event(registration_event_id)
        if (
            registration_event is None
            or registration_event.get("event_type") != "release_candidate_registered"
            or registration_event.get("task_id") != message.payload.get("task_id")
            or registration_event.get("workstream_id") != message.payload.get("workstream_id")
            or registration_event.get("payload", {}).get("expected_pr_head_sha")
            != message.payload.get("expected_pr_head_sha")
        ):
            raise SupervisorRuntimeError("release candidate intake lost its durable registration")

        failing_candidate: SchedulerReleaseCandidate | None = None
        try:
            registered = self._current_registered_release_candidates()
            admitted: list[SchedulerReleaseCandidate] = []
            admissions: list[dict[str, Any]] = []
            proof_only = 0
            for candidate, source_event_id in registered:
                failing_candidate = candidate
                resolved_candidate, admission = self._resolve_registered_release_candidate(
                    candidate,
                    source_event_id=source_event_id,
                )
                admitted.append(resolved_candidate)
                admissions.append(admission)
                if admission["proof_only"] is True:
                    proof_only += 1

            if preactivation_safe:
                if len(admitted) != 1 or len(admissions) != 1:
                    raise SupervisorRuntimeError(
                        "preactivation admission requires one exact release candidate"
                    )
                candidate = admitted[0]
                admission = admissions[0]
                scheduler_truth = _mapping(admission, "scheduler_truth")
                causal_remediation = self.preactivation_causal_remediation_mode
                repair_state = (
                    self.registry.preactivation_causal_remediation_state()
                    if causal_remediation
                    else self.registry.preactivation_structural_repair_state()
                )
                repair_event_id = repair_state.get(
                    "remediation_event_id"
                    if causal_remediation
                    else "repair_event_id"
                )
                repair_event = (
                    self.registry.get_event(str(repair_event_id))
                    if isinstance(repair_event_id, str) and repair_event_id
                    else None
                )
                completion_event_id = repair_state.get("completion_event_id")
                completion_event = (
                    self.registry.get_event(str(completion_event_id))
                    if isinstance(completion_event_id, str)
                    and completion_event_id
                    else None
                )
                expected_repair_event_type = (
                    "preactivation_causal_remediation"
                    if causal_remediation
                    else "preactivation_structural_repair"
                )
                expected_completion_event_type = (
                    "preactivation_causal_remediation_completed"
                    if causal_remediation
                    else "preactivation_structural_repair_completed"
                )
                expected_pr_number = 93 if causal_remediation else 92
                repair_payload = (
                    repair_event.get("payload")
                    if repair_event is not None
                    and repair_event.get("event_type")
                    == expected_repair_event_type
                    else None
                )
                completion_payload = (
                    completion_event.get("payload")
                    if completion_event is not None
                    and completion_event.get("event_type")
                    == expected_completion_event_type
                    else None
                )
                causal_attestation_valid = not causal_remediation
                if (
                    causal_remediation
                    and isinstance(repair_payload, Mapping)
                    and isinstance(completion_payload, Mapping)
                ):
                    attestation_id = repair_payload.get(
                        "causal_attestation_event_id"
                    )
                    attestation_event = (
                        self.registry.get_event(str(attestation_id))
                        if isinstance(attestation_id, str) and attestation_id
                        else None
                    )
                    durable_attestation = (
                        attestation_event.get("payload")
                        if attestation_event is not None
                        and attestation_event.get("event_type")
                        == "preactivation_causal_attestation"
                        else None
                    )
                    if isinstance(durable_attestation, Mapping):
                        base_attestation = {
                            key: value
                            for key, value in durable_attestation.items()
                            if key
                            not in {
                                "attestation_digest",
                                "attested_writer_generation",
                                "attested_at",
                            }
                        }
                        try:
                            self._validated_preactivation_causal_attestation(
                                base_attestation
                            )
                        except Exception:
                            causal_attestation_valid = False
                        else:
                            attestation_digest = _sha256(
                                json.dumps(
                                    base_attestation,
                                    ensure_ascii=False,
                                    sort_keys=True,
                                    separators=(",", ":"),
                                )
                            )
                            causal_attestation_valid = bool(
                                durable_attestation.get("attestation_digest")
                                == attestation_digest
                                and repair_payload.get(
                                    "causal_attestation_digest"
                                )
                                == attestation_digest
                                and completion_payload.get(
                                    "causal_attestation_event_id"
                                )
                                == attestation_id
                                and completion_payload.get(
                                    "causal_read_event_id"
                                )
                                == repair_payload.get("causal_read_event_id")
                                and completion_payload.get(
                                    "remediation_event_id"
                                )
                                == repair_event_id
                                and repair_payload.get("strategy_resource")
                                == PREACTIVATION_CAUSAL_STRATEGY_RESOURCE
                                and repair_payload.get("strategy_digest")
                                == _sha256(PREACTIVATION_CAUSAL_STRATEGY_RESOURCE)
                                and repair_payload.get(
                                    "source_model_attempt_count"
                                )
                                == 1
                                and repair_payload.get(
                                    "additional_model_attempt_count"
                                )
                                == 0
                                and durable_attestation.get(
                                    "raw_provider_body_stored"
                                )
                                is False
                                and attestation_event.get(
                                    "executor_generation"
                                )
                                == PREACTIVATION_CAUSAL_REMEDIATION_SOURCE_EXECUTOR_GENERATION
                                and completion_event.get(
                                    "executor_generation"
                                )
                                == PREACTIVATION_CAUSAL_REMEDIATION_SUCCESSOR_EXECUTOR_GENERATION
                            )
                activation_release_sha = (
                    self.activation_identity.get("release_sha")
                    if isinstance(self.activation_identity, Mapping)
                    else None
                )
                release_candidate = admission.get("release_candidate")
                diff_files = scheduler_truth.get("diff_files")
                if (
                    repair_state.get("status") != "completed"
                    or not causal_attestation_valid
                    or not isinstance(repair_payload, Mapping)
                    or not isinstance(completion_payload, Mapping)
                    or not isinstance(release_candidate, Mapping)
                    or admission.get("proof_only") is not True
                    or admission.get("target_adapter")
                    != "dev-control-plane-hosted-v2"
                    or candidate.task_id
                    != PREACTIVATION_STRUCTURAL_REPAIR_TASK_ID
                    or candidate.workstream_id
                    != PREACTIVATION_STRUCTURAL_REPAIR_WORKSTREAM_ID
                    or candidate.logical_lane_id
                    != PREACTIVATION_STRUCTURAL_REPAIR_WORKSTREAM_ID
                    or candidate.target_id
                    != PREACTIVATION_STRUCTURAL_REPAIR_CANONICAL_TARGET
                    or candidate.task_revision
                    != completion_payload.get("task_revision")
                    or candidate.workstream_revision
                    != completion_payload.get("workstream_revision")
                    or candidate.pr_head_sha
                    != repair_payload.get("expected_pr_head_sha")
                    or candidate.pr_head_sha
                    != completion_payload.get("expected_pr_head_sha")
                    or activation_release_sha
                    != repair_payload.get("activation_release_sha")
                    or activation_release_sha
                    != completion_payload.get("activation_release_sha")
                    or scheduler_truth.get("pr_state") != "MERGED"
                    or scheduler_truth.get("merge_commit_sha")
                    != activation_release_sha
                    or scheduler_truth.get("task_revision")
                    != candidate.task_revision
                    or scheduler_truth.get("workstream_revision")
                    != candidate.workstream_revision
                    or scheduler_truth.get("pr_head_sha")
                    != candidate.pr_head_sha
                    or scheduler_truth.get("target_id")
                    != candidate.target_id
                    or not isinstance(diff_files, list)
                    or not diff_files
                    or candidate.diff_files != tuple(diff_files)
                    or scheduler_truth.get("checks_green") is not True
                    or scheduler_truth.get("admission_ready") is not False
                    or any(
                        scheduler_truth.get(field) is not False
                        for field in (
                            "merge_conflict",
                            "passport_diff_mismatch",
                            "unknown_classification",
                        )
                    )
                    or candidate.checks_green is not True
                    or candidate.admission_ready is not False
                    or candidate.merge_conflict
                    or candidate.passport_diff_mismatch
                    or candidate.unknown_classification
                    or candidate.multiple_safe_orders
                    or not candidate.lane_healthy
                    or not candidate.multi_pr_intent
                    or release_candidate.get("lane_id")
                    != candidate.logical_lane_id
                    or release_candidate.get("task_id") != candidate.task_id
                    or release_candidate.get("workstream_id")
                    != candidate.workstream_id
                    or release_candidate.get("revision")
                    != candidate.task_revision
                    or release_candidate.get("repo")
                    != PREACTIVATION_STRUCTURAL_REPAIR_CANONICAL_TARGET
                    or release_candidate.get("pr_number") != expected_pr_number
                    or release_candidate.get("expected_head_sha")
                    != candidate.pr_head_sha
                    or release_candidate.get("base_ref") != "main"
                    or tuple(release_candidate.get("required_checks") or ())
                    != ("v2-suite", "self-closure")
                    or tuple(release_candidate.get("declared_files") or ())
                    != candidate.passport_files
                    or tuple(release_candidate.get("resources") or ())
                    != candidate.resources
                    or release_candidate.get("multi_pr") is not True
                ):
                    raise SupervisorRuntimeError(
                        "preactivation proof-only admission differs from the activated release"
                    )

            active_lane = self._active_logical_lane_from_events()
            candidates = tuple(
                replace(
                    candidate,
                    holds_logical_lane=(candidate.logical_lane_id == active_lane),
                    lane_healthy=(candidate.logical_lane_id == active_lane if active_lane else True),
                )
                for candidate in admitted
            )
            for candidate, admission in zip(candidates, admissions):
                durable_admission = dict(admission)
                durable_admission["candidate"] = asdict(candidate)
                self._persist_release_candidate_admission(durable_admission)
            dependency_ids = {
                dependency for candidate in candidates for dependency in candidate.dependencies
            }
            completed = tuple(
                sorted(
                    task.task_id
                    for task in self.registry.list_tasks()
                    if task.task_id in dependency_ids and task.state == "accepted"
                )
            )
            snapshot = {
                "candidates": [asdict(candidate) for candidate in candidates],
                "completed_task_ids": list(completed),
                "active_logical_lane_id": active_lane,
            }
            schedule_message_id = _event_id(
                "release-candidate-snapshot",
                json.dumps(snapshot, sort_keys=True, separators=(",", ":")),
            )
            with self._mutation_lock:
                for candidate in candidates:
                    self._assert_registered_candidate_current(candidate)
                if not preactivation_safe:
                    self._prepare_multi_pr_continuation(candidates)
                decision = self.engine.schedule(
                    candidates,
                    message_id=schedule_message_id,
                    completed_task_ids=completed,
                    active_logical_lane_id=active_lane,
                )
                if preactivation_safe:
                    if (
                        decision.get("kind") != "wait"
                        or decision.get("reservation") is not None
                    ):
                        raise SupervisorRuntimeError(
                            "preactivation proof-only admission did not produce an exact wait"
                        )
                    unsafe_work = tuple(
                        record
                        for record in self.registry.list_outbox_records(
                            kinds=PREACTIVATION_ORDINARY_POLICY_OUTBOX_KINDS,
                            states=("pending", "inflight", "delivered"),
                        )
                        if record.get("state") in {"pending", "inflight"}
                        or (
                            record.get("state") == "delivered"
                            and record.get("writer_generation")
                            == self.engine.fence.generation
                        )
                    )
                    if unsafe_work:
                        raise SupervisorRuntimeError(
                            "preactivation admission produced ordinary policy work"
                        )
                else:
                    self._reconcile_release_orchestration()
                poll_wait = (
                    bool(candidates)
                    and decision.get("kind") == "wait"
                    and proof_only != len(candidates)
                )
                if poll_wait:
                    self.registry.nack_outbox(
                        message.event_id,
                        message.claim_token,
                        self.engine.fence,
                        retry_at=self.clock() + max(1.0, self.retry_delay_seconds),
                        sanitized_error="release_candidate_waiting",
                    )
                else:
                    self.registry.ack_outbox(
                        message.event_id, message.claim_token, self.engine.fence
                    )
            status = (
                "proof_only_wait"
                if candidates and proof_only == len(candidates) and decision.get("kind") == "wait"
                else ("waiting_candidate" if poll_wait else "scheduled")
            )
            return RuntimeWorkerResult(
                message.kind,
                message.event_id,
                status,
                str(decision.get("kind") or "wait"),
            )
        except SecurityPermissionChangeRequiresOwner as exc:
            if failing_candidate is None:
                raise SupervisorRuntimeError(
                    "protected controller HumanGate lacks a bound release candidate"
                ) from exc
            return self._persist_release_human_gate(message, failing_candidate, exc)
        except Exception as exc:
            if failing_candidate is None:
                with self._mutation_lock:
                    self.registry.ack_outbox(message.event_id, message.claim_token, self.engine.fence)
                return RuntimeWorkerResult(
                    message.kind, message.event_id, "stale_registration", _error_code(exc)
                )
            fingerprint = self._release_failure_fingerprint(
                failing_candidate,
                exc,
                stage="candidate_intake",
            )
            if self._release_incident_was_applied(failing_candidate, fingerprint):
                return self._park_release_policy_message(
                    message,
                    (failing_candidate,),
                    exc,
                    phase="same_intake_failure_after_release_arbiter",
                )
            failure_count = self._record_release_failure_observation(
                message,
                failing_candidate,
                fingerprint=fingerprint,
                stage="candidate_intake",
                exc=exc,
            )
            if failure_count == 1:
                with self._mutation_lock:
                    self.registry.nack_outbox(
                        message.event_id,
                        message.claim_token,
                        self.engine.fence,
                        retry_at=self.clock() + self.retry_delay_seconds,
                        sanitized_error=_error_code(exc),
                    )
                return RuntimeWorkerResult(
                    message.kind, message.event_id, "retry_scheduled", _error_code(exc)
                )
            if preactivation_safe:
                # The qualification harness gets the ordinary first bounded
                # readback retry, but it never opens a Fresh Sol incident or
                # release arbiter before the single canary is receipted.
                return self._park_release_policy_message(
                    message,
                    (failing_candidate,),
                    exc,
                    phase="preactivation_admission_fail_closed",
                )
            return self._route_release_incident(
                message,
                failing_candidate,
                exc,
                fingerprint=fingerprint,
            )

    def _current_registered_release_candidates(
        self,
    ) -> tuple[tuple[SchedulerReleaseCandidate, str], ...]:
        latest: dict[tuple[str, str], Mapping[str, Any]] = {}
        for event in self.registry.list_events(event_types=("release_candidate_registered",)):
            payload = event.get("payload")
            if not isinstance(payload, Mapping):
                raise SupervisorRuntimeError("release candidate registration payload is invalid")
            _exact_fields(
                payload,
                {
                    "schema", "task_id", "task_revision", "workstream_id",
                    "workstream_revision", "expected_pr_head_sha", "target_id",
                },
                "release candidate registration event",
            )
            if payload.get("schema") != RELEASE_CANDIDATE_REGISTRATION_SCHEMA:
                raise SupervisorRuntimeError("release candidate registration schema mismatch")
            key = (str(payload["task_id"]), str(payload["workstream_id"]))
            latest[key] = event

        prepared: list[tuple[Mapping[str, Any], Any, Any, TaskPassport, Any]] = []
        for event in latest.values():
            payload = event["payload"]
            task = self.registry.get_task(str(payload["task_id"]))
            workstream = self.registry.get_workstream(str(payload["workstream_id"]))
            if (
                task is None
                or workstream is None
                or workstream.task_id != task.task_id
                or task.revision != payload["task_revision"]
                or workstream.revision != payload["workstream_revision"]
                or task.state in {"accepted", "parked"}
                or workstream.state != "waiting_release"
            ):
                continue
            passport = task_passport_from_mapping(task.passport)
            workstream_contract = workstream_from_mapping(workstream.contract)
            if (
                self._passport_release_target(passport) != payload["target_id"]
                or set(workstream_contract.resources) - set(passport.resources)
                or not passport.files
            ):
                raise SupervisorRuntimeError(
                    "release candidate registration differs from current Passport truth"
                )
            prepared.append((event, task, workstream, passport, workstream_contract))

        registered_task_ids = {item[1].task_id for item in prepared}
        all_active_passports = tuple(
            task_passport_from_mapping(task.passport)
            for task in self.registry.list_tasks()
            if task.state not in {"accepted", "parked"}
        )
        completed_or_stalled = self._completed_or_stalled_release_heads()
        result: list[tuple[SchedulerReleaseCandidate, str]] = []
        for event, task, workstream, passport, _workstream_contract in prepared:
            payload = event["payload"]
            target_id = str(payload["target_id"])
            head = str(payload["expected_pr_head_sha"])
            candidate_id = _event_id(
                "release-candidate",
                f"{target_id}|{task.task_id}|{workstream.workstream_id}|{head}",
            )
            if (candidate_id, head) in completed_or_stalled:
                continue
            downstream_all = sum(
                task.task_id in other.dependencies for other in all_active_passports
            )
            downstream_registered = sum(
                task.task_id in other.dependencies
                for other in all_active_passports
                if other.task_id in registered_task_ids
            )
            resources = self._passport_scheduler_resources(passport)
            risk_score = sum(
                item.startswith(("database:", "schema:", "migration:", "contract:", "shared-contract:"))
                for item in resources
            )
            candidate = SchedulerReleaseCandidate(
                candidate_id=candidate_id,
                task_id=task.task_id,
                workstream_id=workstream.workstream_id,
                logical_lane_id=self._passport_logical_lane(
                    passport, workstream.workstream_id, target_id
                ),
                target_id=target_id,
                task_revision=task.revision,
                workstream_revision=workstream.revision,
                pr_head_sha=head,
                resources=resources,
                passport_files=tuple(passport.files),
                diff_files=(),
                modules=tuple(passport.modules),
                databases=self._resource_suffixes(resources, "database:"),
                schemas=self._resource_suffixes(resources, "schema:"),
                migrations=self._resource_suffixes(resources, "migration:"),
                shared_contracts=tuple(
                    sorted(
                        set(self._resource_suffixes(resources, "contract:"))
                        | set(self._resource_suffixes(resources, "shared-contract:"))
                    )
                ),
                dependencies=tuple(passport.dependencies),
                owner_priority=self._passport_owner_priority(passport),
                critical_path_value=downstream_all,
                unblock_value=downstream_registered,
                risk_score=risk_score,
                fairness_credit=0,
                ready_since=_iso(float(event["created_at"])),
                created_at=passport.created_at,
                checks_green=False,
                admission_ready=False,
                merge_conflict=False,
                passport_diff_mismatch=False,
                unknown_classification=False,
                holds_logical_lane=False,
                lane_healthy=True,
                multi_pr_intent=passport.multi_pr_intent,
                multiple_safe_orders=False,
            )
            result.append((candidate, str(event["event_id"])))
        return tuple(sorted(result, key=lambda item: item[0].candidate_id))

    def _resource_suffixes(self, resources: Sequence[str], prefix: str) -> tuple[str, ...]:
        return tuple(sorted(item.removeprefix(prefix) for item in resources if item.startswith(prefix)))

    def _completed_or_stalled_release_heads(self) -> set[tuple[str, str]]:
        identities: set[tuple[str, str]] = set()
        for event in self.registry.list_events(
            event_types=(
                "release_completed", "release_stalled", "release_superseded", "release_proof_only"
            )
        ):
            payload = event.get("payload", {})
            if event.get("event_type") == "release_completed":
                payload = payload.get("receipt", {}) if isinstance(payload, Mapping) else {}
            elif event.get("event_type") == "release_proof_only":
                payload = payload.get("candidate", {}) if isinstance(payload, Mapping) else {}
            if not isinstance(payload, Mapping):
                continue
            candidate_id = payload.get("candidate_id")
            head = payload.get("pr_head_sha")
            if isinstance(candidate_id, str) and isinstance(head, str):
                identities.add((candidate_id, head))
        return identities

    def _resolve_registered_release_candidate(
        self,
        candidate: SchedulerReleaseCandidate,
        *,
        source_event_id: str,
    ) -> tuple[SchedulerReleaseCandidate, dict[str, Any]]:
        if self.release_candidate_resolver is None:
            raise SupervisorRuntimeError("release candidate resolver is unavailable")
        request = {
            "schema": RELEASE_CANDIDATE_INTAKE_RESOLUTION_SCHEMA,
            "candidate": asdict(candidate),
            "source_event_id": source_event_id,
            "remediation_decision_id": None,
        }
        guard = RuntimeActionGuard(self, request, release=False)
        guard.assert_current()
        resolved = self.release_candidate_resolver(request, guard)
        guard.assert_current()
        if guard.callback_checks < 1:
            raise SupervisorRuntimeError(
                "release intake resolver omitted exact GitHub readback checkpoint"
            )
        _exact_fields(
            resolved,
            {"release_candidate", "target_adapter", "scheduler_truth"},
            "release intake resolver receipt",
        )
        release_raw = dict(_mapping(resolved, "release_candidate"))
        release_candidate = _release_train_candidate_from_mapping(release_raw)
        self._validate_resolved_release_candidate(candidate, release_candidate)
        target_adapter = _machine("target_adapter", resolved.get("target_adapter"))
        truth = self._validated_intake_scheduler_truth(
            candidate,
            _mapping(resolved, "scheduler_truth"),
        )
        proof_only = truth["pr_state"] == "MERGED"
        admitted = replace(
            candidate,
            diff_files=tuple(truth["diff_files"]),
            checks_green=bool(truth["checks_green"]),
            admission_ready=(bool(truth["admission_ready"]) and not proof_only),
            merge_conflict=bool(truth["merge_conflict"]),
            passport_diff_mismatch=bool(truth["passport_diff_mismatch"]),
            unknown_classification=bool(truth["unknown_classification"]),
            risk_score=candidate.risk_score + min(len(truth["diff_files"]), 3_000),
        )
        admission = {
            "schema": RELEASE_CANDIDATE_ADMISSION_SCHEMA,
            "source_event_id": source_event_id,
            "candidate": asdict(admitted),
            "release_candidate": release_raw,
            "target_adapter": target_adapter,
            "scheduler_truth": truth,
            "proof_only": proof_only,
        }
        return admitted, admission

    def _validated_intake_scheduler_truth(
        self,
        candidate: SchedulerReleaseCandidate,
        truth: Mapping[str, Any],
    ) -> dict[str, Any]:
        expected = {
            "task_revision", "workstream_revision", "pr_head_sha", "target_id",
            "pr_state", "merge_commit_sha", "diff_files", "checks_green",
            "admission_ready", "merge_conflict", "passport_diff_mismatch",
            "unknown_classification",
        }
        _exact_fields(truth, expected, "release intake scheduler truth")
        if (
            truth.get("task_revision") != candidate.task_revision
            or truth.get("workstream_revision") != candidate.workstream_revision
            or truth.get("pr_head_sha") != candidate.pr_head_sha
            or truth.get("target_id") != candidate.target_id
        ):
            raise SupervisorRuntimeError("release intake GitHub truth binding is stale")
        state = truth.get("pr_state")
        merge_sha = truth.get("merge_commit_sha")
        if state == "OPEN":
            if merge_sha is not None:
                raise SupervisorRuntimeError("open release intake unexpectedly has a merge commit")
        elif state == "MERGED":
            if not isinstance(merge_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", merge_sha):
                raise SupervisorRuntimeError("merged release intake lacks immutable merge proof")
        else:
            raise SupervisorRuntimeError("release intake PR state is not admitted")
        diff_files = truth.get("diff_files")
        if (
            not isinstance(diff_files, list)
            or not 1 <= len(diff_files) <= 3_000
            or not all(isinstance(item, str) and item and len(item) <= 2_000 for item in diff_files)
            or len(set(diff_files)) != len(diff_files)
        ):
            raise SupervisorRuntimeError("release intake GitHub diff is invalid or incomplete")
        for key in (
            "checks_green", "admission_ready", "merge_conflict",
            "passport_diff_mismatch", "unknown_classification",
        ):
            if not isinstance(truth.get(key), bool):
                raise SupervisorRuntimeError(f"release intake scheduler field {key} is invalid")
        derived_mismatch = not set(diff_files).issubset(set(candidate.passport_files))
        if truth["passport_diff_mismatch"] is not derived_mismatch:
            raise SupervisorRuntimeError("release intake Passport/diff mismatch was not derived")
        return dict(truth)

    def _persist_release_candidate_admission(self, admission: Mapping[str, Any]) -> None:
        digest = _sha256(
            json.dumps(admission, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        )
        candidate = release_candidate_from_mapping(_mapping(admission, "candidate"))
        event_id = _event_id("release-candidate-admitted", digest)
        with self._mutation_lock:
            self.registry.record_input_event_outbox(
                message_id=_event_id("release-candidate-admission-receipt", digest),
                source="supervisor-release-candidate-intake",
                input_payload={
                    "source_event_id": admission["source_event_id"],
                    "candidate_id": candidate.candidate_id,
                    "pr_head_sha": candidate.pr_head_sha,
                    "admission_digest": digest,
                },
                event_id=event_id,
                event_type="release_candidate_admitted",
                event_payload=dict(admission),
                outbox_items=(self._dirty_item(event_id, candidate.task_id),),
                fence=self.engine.fence,
                task_id=candidate.task_id,
                workstream_id=candidate.workstream_id,
            )

    def _assert_registered_candidate_current(self, candidate: SchedulerReleaseCandidate) -> None:
        task = self.registry.get_task(candidate.task_id)
        workstream = self.registry.get_workstream(candidate.workstream_id)
        if (
            task is None
            or workstream is None
            or workstream.task_id != candidate.task_id
            or task.revision != candidate.task_revision
            or workstream.revision != candidate.workstream_revision
            or task.state in {"accepted", "parked"}
            or workstream.state != "waiting_release"
        ):
            raise SupervisorRuntimeError("release candidate changed after GitHub readback")
        passport = task_passport_from_mapping(task.passport)
        if (
            self._passport_release_target(passport) != candidate.target_id
            or set(self._passport_scheduler_resources(passport)) != set(candidate.resources)
            or set(passport.files) != set(candidate.passport_files)
            or set(passport.modules) != set(candidate.modules)
            or set(passport.dependencies) != set(candidate.dependencies)
            or passport.multi_pr_intent != candidate.multi_pr_intent
        ):
            raise SupervisorRuntimeError("release candidate Passport binding changed after GitHub readback")

    def _active_logical_lane_from_events(self) -> str | None:
        events = self.registry.list_events(
            event_types=(
                "release_reserved", "release_completed",
                "release_proof_only", "release_stalled",
                "target_lane_closure_completed",
            )
        )
        active: str | None = None
        for event in events:
            event_type = event.get("event_type")
            payload = event.get("payload", {})
            candidate: SchedulerReleaseCandidate | None = None
            if event_type == "release_reserved" and isinstance(payload, Mapping):
                decision = payload.get("decision")
                raw_candidates = payload.get("candidates")
                candidate_ids = decision.get("candidate_ids") if isinstance(decision, Mapping) else None
                if isinstance(raw_candidates, list) and isinstance(candidate_ids, list) and candidate_ids:
                    selected_id = str(candidate_ids[0])
                    for raw in raw_candidates:
                        if isinstance(raw, Mapping) and raw.get("candidate_id") == selected_id:
                            candidate = release_candidate_from_mapping(raw)
                            break
                if candidate is not None:
                    active = candidate.logical_lane_id
                continue
            if event_type == "release_completed" and isinstance(payload, Mapping):
                receipt = payload.get("receipt")
                if isinstance(receipt, Mapping):
                    candidate = self._scheduled_candidate_by_identity(
                        events,
                        str(receipt.get("candidate_id") or ""),
                        str(receipt.get("pr_head_sha") or ""),
                    )
                if candidate is not None:
                    active = candidate.logical_lane_id
                continue
            if event_type == "release_proof_only" and isinstance(payload, Mapping):
                raw_candidate = payload.get("candidate")
                if isinstance(raw_candidate, Mapping):
                    candidate = release_candidate_from_mapping(raw_candidate)
                    active = candidate.logical_lane_id
                continue
            if event_type == "release_stalled" and isinstance(payload, Mapping):
                candidate = self._scheduled_candidate_by_identity(
                    events,
                    str(payload.get("candidate_id") or ""),
                    str(payload.get("pr_head_sha") or ""),
                )
                if candidate is not None:
                    active = candidate.logical_lane_id
                continue
            if event_type == "target_lane_closure_completed" and isinstance(payload, Mapping):
                action = payload.get("action")
                receipt = payload.get("receipt")
                if (
                    isinstance(action, Mapping)
                    and isinstance(receipt, Mapping)
                    and receipt.get("closure_id") == action.get("closure_id")
                    and receipt.get("status") in {"released", "parked"}
                    and action.get("logical_lane_id") == active
                ):
                    active = None
        return active

    def _prepare_multi_pr_continuation(
        self,
        candidates: Sequence[Any],
        *,
        enqueue_continuation: bool = False,
    ) -> None:
        """Release the retained lane only for a proved next PR of that lane.

        A successful multi-PR release intentionally keeps its logical lane.
        The lane is handed to a new admitted head only when a durable completed
        predecessor belongs to the same task and logical lane.  Workstreams may
        differ because parallel parts of one acceptance envelope are first-class.
        """

        completed = self.registry.list_events(
            event_types=("release_completed", "release_proof_only")
        )
        scheduled = self.registry.list_events(
            event_types=(
                "release_reserved",
                "release_head_reserved",
                "semantic_release_case",
                "release_plan_decision",
            )
        )
        for candidate in candidates:
            if (
                not candidate.multi_pr_intent
                or not candidate.checks_green
                or not candidate.admission_ready
            ):
                continue
            predecessors: dict[
                tuple[str, str], tuple[SchedulerReleaseCandidate, str]
            ] = {}
            for event in completed:
                payload = event.get("payload", {})
                binding = (
                    payload.get("receipt", {})
                    if event.get("event_type") == "release_completed"
                    else payload.get("candidate", {})
                )
                if not isinstance(binding, Mapping):
                    continue
                predecessor = self._scheduled_candidate_by_identity(
                    scheduled,
                    str(binding.get("candidate_id") or ""),
                    str(binding.get("pr_head_sha") or ""),
                )
                if (
                    predecessor is not None
                    and predecessor.task_id == candidate.task_id
                    and predecessor.logical_lane_id == candidate.logical_lane_id
                    and predecessor.pr_head_sha != candidate.pr_head_sha
                    and predecessor.multi_pr_intent
                ):
                    predecessors[(
                        predecessor.task_id, predecessor.workstream_id
                    )] = (predecessor, str(event["event_id"]))
            for predecessor, _completion_event_id in predecessors.values():
                self.registry.release_scheduler_reservation_owner(
                    task_id=predecessor.task_id,
                    workstream_id=predecessor.workstream_id,
                    fence=self.engine.fence,
                )
            if enqueue_continuation and predecessors:
                source_event_id = sorted(
                    event_id for _predecessor, event_id in predecessors.values()
                )[-1]
                self._reserve_and_enqueue_release_resolution(
                    candidate,
                    source_event_id=source_event_id,
                )

    def _reconcile_release_orchestration(self) -> None:
        """Materialize the next mechanical release step from durable truth.

        This fold is deterministic and restart-safe. It never calls GitHub or a
        model; it only reserves a bound candidate and emits one durable work
        item. External reads and mutations happen in the dedicated workers.
        """

        events = self.registry.list_events(
            event_types=(
                "release_reserved",
                "release_head_reserved",
                "semantic_release_case",
                "release_plan_decision",
                "release_completed",
                "release_proof_only",
                "release_stalled",
                "release_superseded",
                "release_plan_superseded",
            )
        )
        completed: set[tuple[str, str]] = set()
        for event in events:
            payload = event.get("payload", {})
            if event.get("event_type") == "release_completed":
                binding = payload.get("receipt", {}) if isinstance(payload, Mapping) else {}
            elif event.get("event_type") == "release_proof_only":
                binding = payload.get("candidate", {}) if isinstance(payload, Mapping) else {}
            else:
                continue
            if isinstance(binding, Mapping):
                completed.add(
                    (
                        str(binding.get("candidate_id") or ""),
                        str(binding.get("pr_head_sha") or ""),
                    )
                )
        stalled = {
            (
                str(event.get("payload", {}).get("candidate_id") or ""),
                str(event.get("payload", {}).get("pr_head_sha") or ""),
            )
            for event in events
            if event.get("event_type") in {"release_stalled", "release_superseded"}
        }

        admitted_now, _registrations_now, _admission_complete = (
            self._current_admitted_release_snapshot()
        )
        self._prepare_multi_pr_continuation(
            admitted_now, enqueue_continuation=True
        )

        for event in events:
            if event.get("event_type") != "release_reserved":
                continue
            raw_candidates = event.get("payload", {}).get("candidates")
            ordered_ids = event.get("payload", {}).get("decision", {}).get("candidate_ids")
            if not isinstance(raw_candidates, list) or not isinstance(ordered_ids, list):
                continue
            by_id = {
                candidate.candidate_id: candidate
                for candidate in (
                    release_candidate_from_mapping(_mapping_value(raw, "release candidate"))
                    for raw in raw_candidates
                )
            }
            for candidate_id in ordered_ids:
                candidate = by_id.get(str(candidate_id))
                if candidate is None:
                    raise SupervisorRuntimeError("release sequence refers to a missing candidate")
                identity = (candidate.candidate_id, candidate.pr_head_sha)
                if identity in stalled:
                    break
                if identity in completed:
                    continue
                self._reserve_and_enqueue_release_resolution(candidate, source_event_id=str(event["event_id"]))
                break

        plan_events = {
            str(event.get("payload", {}).get("semantic_case", {}).get("case_id") or ""): event
            for event in events
            if event.get("event_type") == "release_plan_decision"
        }
        superseded_plan_ids = {
            str(event.get("payload", {}).get("case_id") or "")
            for event in events
            if event.get("event_type") == "release_plan_superseded"
        }
        for event in events:
            if event.get("event_type") != "semantic_release_case":
                continue
            semantic_case = self._semantic_case_from_payload(event["payload"])
            if semantic_case.case_id not in plan_events:
                self.registry.enqueue_outbox(
                    _event_id("release-arbiter-case", semantic_case.case_id),
                    "release_arbiter_case",
                    {
                        "schema": "dev-control-plane/release-arbiter-case/v2",
                        "source_event_id": event["event_id"],
                        "semantic_case": self._semantic_case_payload(semantic_case),
                    },
                    self.engine.fence,
                    task_id=None,
                    coalescible=False,
                )

        for event in plan_events.values():
            payload = event.get("payload", {})
            semantic_case = self._semantic_case_from_decision_payload(payload)
            if semantic_case.case_id in superseded_plan_ids:
                continue
            current_candidates, current_registrations, admission_complete = (
                self._current_admitted_release_snapshot()
            )
            eligible = tuple(
                candidate
                for candidate in current_candidates
                if candidate.checks_green and candidate.admission_ready
            )
            try:
                if not admission_complete:
                    raise SupervisorRuntimeError(
                        "semantic release plan has an unadmitted current registration"
                    )
                revalidate_case_against_candidates(semantic_case, eligible)
            except Exception:
                self._supersede_semantic_release_plan(
                    semantic_case,
                    current_candidates=current_candidates,
                    current_registrations=current_registrations,
                    source_event_id=str(event["event_id"]),
                )
                continue
            decision = arbiter_decision_from_mapping(_mapping_value(payload.get("decision"), "release decision"))
            order = validate_arbiter_release_decision(semantic_case, decision)
            if decision.steps and all(step.action == "wait" for step in decision.steps):
                self._ensure_semantic_release_plan_refresh(
                    semantic_case,
                    current_registrations=current_registrations,
                )
                continue
            steps = {step.step_id: step for step in decision.steps}
            candidates = {
                (item.task_id, item.workstream_id): item for item in semantic_case.candidates
            }
            completed_steps = {
                step.step_id
                for step in decision.steps
                if step.action == "release"
                and (
                    candidates[(step.task_id, step.workstream_id)].candidate_id,
                    candidates[(step.task_id, step.workstream_id)].pr_head_sha,
                )
                in completed
            }
            for step_id in order:
                step = steps[step_id]
                candidate = candidates[(step.task_id, step.workstream_id)]
                identity = (candidate.candidate_id, candidate.pr_head_sha)
                if identity in stalled or step.action == "wait" or step_id in completed_steps:
                    continue
                if not set(step.depends_on).issubset(completed_steps):
                    continue
                self._reserve_and_enqueue_release_resolution(
                    candidate,
                    source_event_id=str(event["event_id"]),
                )
                break

    def _ensure_semantic_release_plan_refresh(
        self,
        semantic_case: SemanticReleaseCase,
        *,
        current_registrations: Sequence[
            tuple[SchedulerReleaseCandidate, str]
        ],
    ) -> None:
        """Poll immutable GitHub admissions for an all-wait plan without Sol.

        The decision remains bound to its case while truth is unchanged.  One
        delayed durable intake re-runs only registered readbacks; a changed
        snapshot naturally supersedes/replans the case.
        """

        records = tuple(
            item
            for item in self.registry.list_outbox_records(
                kinds=("release_candidate_intake",)
            )
            if item.get("payload", {}).get("semantic_case_id")
            == semantic_case.case_id
            and item.get("payload", {}).get("semantic_case_digest")
            == semantic_case.case_digest
        )
        if any(item["state"] in {"pending", "inflight"} for item in records):
            return
        case_bindings = {
            (candidate.candidate_id, candidate.pr_head_sha)
            for candidate in semantic_case.candidates
        }
        eligible_registrations = sorted(
            (
                (candidate, registration_event_id)
                for candidate, registration_event_id in current_registrations
                if (candidate.candidate_id, candidate.pr_head_sha) in case_bindings
            ),
            key=lambda item: (item[0].candidate_id, item[1]),
        )
        if not eligible_registrations:
            return
        cycle = (
            max(
                (
                    int(item.get("payload", {}).get("refresh_cycle") or 0)
                    for item in records
                ),
                default=0,
            )
            + 1
        )
        candidate, registration_event_id = eligible_registrations[0]
        event_id = _event_id(
            "release-plan-refresh",
            f"{semantic_case.case_id}:{semantic_case.case_digest}:{cycle}:{registration_event_id}",
        )
        self.registry.enqueue_outbox(
            event_id,
            "release_candidate_intake",
            {
                "schema": RELEASE_CANDIDATE_INTAKE_SCHEMA,
                "registration_event_id": registration_event_id,
                "task_id": candidate.task_id,
                "workstream_id": candidate.workstream_id,
                "expected_pr_head_sha": candidate.pr_head_sha,
                "semantic_case_id": semantic_case.case_id,
                "semantic_case_digest": semantic_case.case_digest,
                "refresh_cycle": cycle,
            },
            self.engine.fence,
            task_id=candidate.task_id,
            coalescible=False,
            available_at=self.clock() + max(1.0, self.retry_delay_seconds),
        )

    def _current_admitted_release_snapshot(
        self,
    ) -> tuple[
        tuple[SchedulerReleaseCandidate, ...],
        tuple[tuple[SchedulerReleaseCandidate, str], ...],
        bool,
    ]:
        """Bind a plan to latest registration plus durable GitHub admission."""

        registrations = self._current_registered_release_candidates()
        admissions = self.registry.list_events(
            event_types=("release_candidate_admitted",)
        )
        current: list[SchedulerReleaseCandidate] = []
        complete = True
        active_lane = self._active_logical_lane_from_events()
        for registered, source_event_id in registrations:
            matched: SchedulerReleaseCandidate | None = None
            for event in reversed(admissions):
                payload = event.get("payload", {})
                if payload.get("source_event_id") != source_event_id:
                    continue
                raw = payload.get("candidate")
                if not isinstance(raw, Mapping):
                    continue
                candidate = release_candidate_from_mapping(raw)
                if (
                    candidate.candidate_id == registered.candidate_id
                    and candidate.pr_head_sha == registered.pr_head_sha
                ):
                    matched = candidate
                    break
            if matched is None:
                complete = False
                continue
            matched = replace(
                matched,
                holds_logical_lane=(matched.logical_lane_id == active_lane),
                lane_healthy=(
                    matched.logical_lane_id == active_lane
                    if active_lane
                    else True
                ),
            )
            self._assert_registered_candidate_current(matched)
            current.append(matched)
        return (
            tuple(sorted(current, key=lambda item: item.candidate_id)),
            registrations,
            complete,
        )

    def _supersede_semantic_release_plan(
        self,
        semantic_case: SemanticReleaseCase,
        *,
        current_candidates: Sequence[SchedulerReleaseCandidate],
        current_registrations: Sequence[tuple[SchedulerReleaseCandidate, str]],
        source_event_id: str,
    ) -> None:
        """Retire one stale immutable plan and durably request fresh intake."""

        snapshot = [asdict(item) for item in current_candidates]
        snapshot_digest = _sha256(
            json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
        )
        event_id = _event_id(
            "release-plan-superseded",
            f"{semantic_case.case_id}:{snapshot_digest}",
        )
        if self.registry.get_event(event_id) is not None:
            return
        refresh_items: list[dict[str, Any]] = []
        existing_resolutions = {
            item["event_id"]
            for item in self.registry.list_outbox_summaries(
                kinds=("release_candidate_resolution",)
            )
        }
        for candidate, registration_event_id in current_registrations:
            resolution_event_id = _event_id(
                "release-resolution",
                f"{candidate.candidate_id}:{candidate.pr_head_sha}",
            )
            if resolution_event_id in existing_resolutions:
                continue
            refresh_items.append(
                {
                    "event_id": _event_id(
                        "release-candidate-intake-refresh",
                        f"{event_id}:{registration_event_id}",
                    ),
                    "kind": "release_candidate_intake",
                    "payload": {
                        "schema": RELEASE_CANDIDATE_INTAKE_SCHEMA,
                        "registration_event_id": registration_event_id,
                        "task_id": candidate.task_id,
                        "workstream_id": candidate.workstream_id,
                        "expected_pr_head_sha": candidate.pr_head_sha,
                    },
                    "task_id": candidate.task_id,
                    "coalescible": False,
                    "coalesce_key": None,
                }
            )
        self.registry.record_input_event_outbox(
            message_id=_event_id("release-plan-superseded-receipt", event_id),
            source="supervisor-release-plan-revalidator",
            input_payload={
                "source_event_id": source_event_id,
                "case_id": semantic_case.case_id,
                "current_snapshot_digest": snapshot_digest,
            },
            event_id=event_id,
            event_type="release_plan_superseded",
            event_payload={
                "schema": "dev-control-plane/release-plan-superseded/v2",
                "case_id": semantic_case.case_id,
                "case_digest": semantic_case.case_digest,
                "source_event_id": source_event_id,
                "current_snapshot_digest": snapshot_digest,
                "current_candidates": snapshot,
                "superseded_at": _iso(self.clock()),
            },
            outbox_items=tuple(
                refresh_items + [self._dirty_item(event_id, None)]
            ),
            fence=self.engine.fence,
            task_id=None,
            workstream_id=None,
        )

    def _reconcile_target_lane_closures(self) -> None:
        """Queue one task-level target lane closure from durable local truth.

        A PR receipt is deliberately insufficient.  Completed work is admitted
        only by the one task-level technical closure barrier; a parked outcome
        is admitted only by a durable parked release/incident event.  The
        current Passport supplies the immutable ordered PR chain and lane.
        """

        terminal_closures = {
            str(event.get("payload", {}).get("receipt", {}).get("closure_id") or "")
            for event in self.registry.list_events(
                event_types=("target_lane_closure_completed", "target_lane_closure_stalled")
            )
        }
        terminal_closures.discard("")
        generation = self.engine.fence.generation
        for task in self.registry.list_tasks():
            passport = task_passport_from_mapping(task.passport)
            if not passport.contour.startswith("release:"):
                continue
            if self._target_lane_incident_exhausted(
                task.task_id, task_revision=task.revision
            ):
                continue
            source = self._target_lane_closure_source(task)
            if source is None:
                continue
            outcome = "parked" if task.state == "parked" else "completed"
            workstream_id = str(source.get("workstream_id") or "")
            workstream = self.registry.get_workstream(workstream_id)
            if workstream is None or workstream.task_id != task.task_id:
                continue
            closure_event_digest = self._target_lane_closure_event_digest(source)
            target_id = self._passport_release_target(passport)
            logical_lane_id = self._passport_logical_lane(
                passport, workstream_id, target_id
            )
            manifest = passport.release_manifest
            binding: dict[str, Any]
            if manifest is not None:
                manifest_payload = contract_to_dict(manifest)
                manifest_digest = _sha256(
                    json.dumps(
                        manifest_payload,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                )
                binding = {
                    "binding_kind": "final_manifest",
                    "ordered_pr_identities": list(manifest.pr_identities),
                    "anchor_pr_identity": manifest.pr_identities[0],
                    "release_manifest_digest": manifest_digest,
                }
                binding_digest = manifest_digest
            else:
                if outcome != "parked" or target_id != WB_CORE_REPOSITORY:
                    continue
                parked_admission = self._parked_target_lane_admission(
                    task_id=task.task_id,
                    workstream_id=workstream_id,
                    task_revision=task.revision,
                    workstream_revision=workstream.revision,
                    logical_lane_id=logical_lane_id,
                )
                if parked_admission is None:
                    continue
                binding = {
                    "binding_kind": "parked_admission",
                    "parked_admission": parked_admission,
                }
                binding_digest = _sha256(
                    json.dumps(
                        parked_admission,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                )
            closure_id = _event_id(
                "target-lane-closure-binding",
                "|".join(
                    (
                        task.task_id,
                        target_id,
                        logical_lane_id,
                        outcome,
                        str(source["event_id"]),
                        closure_event_digest,
                        binding_digest,
                    )
                ),
            )
            if closure_id in terminal_closures:
                continue
            action = {
                "schema": TARGET_LANE_CLOSURE_SCHEMA,
                "closure_id": closure_id,
                "supervisor_generation": generation,
                "task_id": task.task_id,
                "task_revision": task.revision,
                "workstream_id": workstream_id,
                "workstream_revision": workstream.revision,
                "target_id": target_id,
                "logical_lane_id": logical_lane_id,
                "contour": passport.contour,
                "outcome": outcome,
                "closure_event_id": str(source["event_id"]),
                "closure_event_type": str(source["event_type"]),
                "closure_event_digest": closure_event_digest,
                **binding,
            }
            action_event_id = _event_id(
                "target-lane-closure",
                f"{closure_id}|g{generation}|tr{task.revision}|wr{workstream.revision}",
            )
            pending_event_id = _event_id("target-lane-closure-pending", action_event_id)
            self.registry.record_input_event_outbox(
                message_id=_event_id("target-lane-closure-reconcile", action_event_id),
                source="supervisor-target-lane-closure-reconciler",
                input_payload={
                    "closure_id": closure_id,
                    "supervisor_generation": generation,
                    "task_revision": task.revision,
                    "workstream_revision": workstream.revision,
                },
                event_id=pending_event_id,
                event_type="target_lane_closure_pending",
                event_payload=action,
                outbox_items=(
                    {
                        "event_id": action_event_id,
                        "kind": "target_lane_closure",
                        "payload": action,
                        "task_id": task.task_id,
                        "coalescible": False,
                        "coalesce_key": None,
                    },
                    self._dirty_item(pending_event_id, task.task_id),
                ),
                fence=self.engine.fence,
                task_id=task.task_id,
                workstream_id=workstream_id,
            )

    def _target_lane_incident_exhausted(
        self, task_id: str, *, task_revision: int
    ) -> bool:
        """Return whether one incident already owns this exact lane scope.

        Opening the incident is the durable hand-off from the base closure
        worker to the one-shot incident policy.  Waiting for a decision-bearing
        application is too late: a pre-decision arbiter failure parks the task
        and otherwise becomes a fresh closure source on every maintenance tick.
        Historical incidents from an older Passport revision do not consume a
        materially revised task's budget.
        """

        applications: dict[str, Mapping[str, Any]] = {}
        parked_decisions: set[str] = set()
        for event in self.registry.list_events(
            task_id=task_id, event_types=("incident_policy",)
        ):
            payload = event.get("payload")
            if not isinstance(payload, Mapping):
                continue
            state_raw = payload.get("incident_state")
            if not isinstance(state_raw, Mapping):
                continue
            state = _incident_state_from_mapping(state_raw)
            # Parking a previously completed envelope consumes one ordinary
            # state CAS revision after the incident-open event.  That state-only
            # increment must not mint another closure budget; a corrective
            # generation increments the Passport again and therefore escapes
            # this two-coordinate window.
            if state.context.passport_revision not in {
                task_revision,
                task_revision - 1,
            }:
                continue
            if payload.get("actor") == "mechanical_target_lane_closure":
                return True
            decision_id = payload.get("remediation_decision_id")
            if not isinstance(decision_id, str):
                continue
            if payload.get("status") == "application_pending":
                applications[decision_id] = payload
            elif payload.get("status") == "parked":
                parked_decisions.add(decision_id)
        return any(
            decision_id in parked_decisions
            and payload.get("disposition") == "dispatch_target_lane_once"
            for decision_id, payload in applications.items()
        )

    def _parked_target_lane_admission(
        self,
        *,
        task_id: str,
        workstream_id: str,
        task_revision: int,
        workstream_revision: int,
        logical_lane_id: str,
    ) -> dict[str, Any] | None:
        """Recover one immutable wb-core admission from historical r1 truth."""

        action_records = {
            str(item["event_id"]): item
            for item in self.registry.list_outbox_records(
                kinds=("release_action",), states=("pending", "delivered")
            )
            if item.get("task_id") == task_id
        }
        matches: dict[str, dict[str, Any]] = {}
        for event in self.registry.list_events(
            task_id=task_id,
            workstream_id=workstream_id,
            event_types=("release_action_observed",),
        ):
            payload = event.get("payload")
            observation = payload.get("observation") if isinstance(payload, Mapping) else None
            release_action_event_id = (
                payload.get("release_action_event_id")
                if isinstance(payload, Mapping)
                else None
            )
            if (
                not isinstance(observation, Mapping)
                or payload.get("target_adapter") != WB_CORE_TARGET_ADAPTER
                or observation.get("status") not in {"admitted", "waiting_release"}
                or not isinstance(release_action_event_id, str)
            ):
                continue
            try:
                binding = wb_core_admission_binding_from_mapping(
                    _mapping(observation, "admission_binding")
                )
            except (TypeError, ValueError, SupervisorRuntimeError):
                continue
            admission_task_revision = observation.get("task_revision")
            admission_workstream_revision = observation.get("workstream_revision")
            if (
                isinstance(admission_task_revision, bool)
                or not isinstance(admission_task_revision, int)
                or isinstance(admission_workstream_revision, bool)
                or not isinstance(admission_workstream_revision, int)
                or admission_task_revision < 1
                or admission_workstream_revision < 1
                or admission_task_revision > task_revision
                or admission_workstream_revision > workstream_revision
                or binding.target_id != WB_CORE_REPOSITORY
                or binding.target_task_id != derive_wb_core_target_task_id(task_id)
                or binding.task_revision != admission_task_revision
                or observation.get("task_id") != task_id
                or observation.get("workstream_id") != workstream_id
                or observation.get("expected_head_sha") != binding.head_sha
                or observation.get("observed_head_sha") != binding.head_sha
                or f"admission:sha256:{binding.proof_digest}"
                not in tuple(observation.get("evidence") or ())
            ):
                continue
            action_record = action_records.get(release_action_event_id)
            action_payload = (
                action_record.get("payload")
                if isinstance(action_record, Mapping)
                else None
            )
            if not isinstance(action_payload, Mapping):
                continue
            try:
                candidate = release_candidate_from_mapping(
                    _mapping(action_payload, "candidate")
                )
                release_candidate = _release_train_candidate_from_mapping(
                    _mapping(action_payload, "release_candidate")
                )
            except Exception:
                continue
            if (
                action_payload.get("target_adapter") != WB_CORE_TARGET_ADAPTER
                or candidate.candidate_id != observation.get("candidate_id")
                or candidate.task_id != task_id
                or candidate.workstream_id != workstream_id
                or candidate.task_revision != admission_task_revision
                or candidate.workstream_revision != admission_workstream_revision
                or candidate.target_id != WB_CORE_REPOSITORY
                or candidate.logical_lane_id != logical_lane_id
                or candidate.pr_head_sha != binding.head_sha
                or release_candidate.repo != WB_CORE_REPOSITORY
                or release_candidate.pr_number != binding.pr_number
                or release_candidate.expected_head_sha != binding.head_sha
                or release_candidate.task_id != task_id
                or release_candidate.workstream_id != workstream_id
                or release_candidate.revision != admission_task_revision
            ):
                continue
            parked = {
                "schema": PARKED_TARGET_LANE_ADMISSION_SCHEMA,
                "target_adapter": WB_CORE_TARGET_ADAPTER,
                "candidate_id": candidate.candidate_id,
                "pr_number": binding.pr_number,
                "expected_head_sha": binding.head_sha,
                "admission_task_revision": admission_task_revision,
                "admission_workstream_revision": admission_workstream_revision,
                "release_action_event_id": release_action_event_id,
                "observation_event_id": str(event["event_id"]),
                "observation_event_digest": self._target_lane_closure_event_digest(event),
                "admission_binding": dict(_mapping(observation, "admission_binding")),
            }
            immutable_key = _sha256(
                json.dumps(
                    {
                        "candidate_id": candidate.candidate_id,
                        "release_action_event_id": release_action_event_id,
                        "admission_binding": parked["admission_binding"],
                        "admission_task_revision": admission_task_revision,
                        "admission_workstream_revision": admission_workstream_revision,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
            # Repeated polls may produce several observations of the same
            # immutable admission.  Bind the closure to the newest exact
            # observation, but reject genuinely conflicting admission truth.
            matches[immutable_key] = parked
        if not matches:
            return None
        if len(matches) != 1:
            raise SupervisorRuntimeError(
                "parked wb-core task has conflicting durable admission bindings"
            )
        return next(iter(matches.values()))

    def _target_lane_closure_source(self, task: Any) -> Mapping[str, Any] | None:
        if task.state == "parked":
            parked = []
            for event in self.registry.list_events(
                task_id=task.task_id,
                event_types=("release_stalled", "incident_policy"),
            ):
                payload = event.get("payload")
                if not isinstance(payload, Mapping):
                    continue
                if event.get("event_type") == "release_stalled" and payload.get("status") == "parked":
                    parked.append(event)
                elif event.get("event_type") == "incident_policy" and payload.get("status") in {
                    "parked",
                    "ambiguous_turn_parked",
                    "missing_verified_checkpoint",
                    "application_failed_fail_closed",
                    "arbiter_failed_fail_closed",
                    "parked_fail_closed",
                    "human_gate",
                }:
                    parked.append(event)
            return parked[-1] if parked else None
        barriers = [
            event
            for event in self.registry.list_events(
                task_id=task.task_id,
                event_types=("technical_terminal",),
            )
            if event.get("payload", {}).get("closure_barrier") is True
        ]
        return barriers[-1] if barriers else None

    def _target_lane_closure_event_digest(self, event: Mapping[str, Any]) -> str:
        return _sha256(
            json.dumps(
                {
                    "event_id": event.get("event_id"),
                    "event_type": event.get("event_type"),
                    "payload": event.get("payload"),
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        )

    def _validate_target_lane_closure(self, action: Mapping[str, Any]) -> None:
        common_fields = {
            "schema", "binding_kind", "closure_id", "supervisor_generation",
            "task_id", "task_revision", "workstream_id", "workstream_revision",
            "target_id", "logical_lane_id", "contour", "outcome",
            "closure_event_id", "closure_event_type", "closure_event_digest",
        }
        binding_kind = action.get("binding_kind")
        expected_fields = (
            common_fields
            | {"ordered_pr_identities", "anchor_pr_identity", "release_manifest_digest"}
            if binding_kind == "final_manifest"
            else common_fields | {"parked_admission"}
            if binding_kind == "parked_admission"
            else set()
        )
        _exact_fields(
            action,
            expected_fields,
            "target lane closure",
        )
        if action.get("schema") != TARGET_LANE_CLOSURE_SCHEMA:
            raise SupervisorRuntimeError("target lane closure schema mismatch")
        for name in (
            "closure_id", "task_id", "workstream_id", "logical_lane_id",
            "closure_event_id", "closure_event_type",
        ):
            _machine(name, action.get(name))
        target_id = action.get("target_id")
        if (
            not isinstance(target_id, str)
            or not target_id
            or len(target_id) > 200
            or any(character.isspace() or ord(character) < 33 for character in target_id)
            or _CREDENTIAL_RE.search(target_id)
        ):
            raise SupervisorRuntimeError("target lane closure target_id is invalid")
        closure_digest = action.get("closure_event_digest")
        if not isinstance(closure_digest, str) or not re.fullmatch(
            r"[0-9a-f]{64}", closure_digest
        ):
            raise SupervisorRuntimeError(
                "target lane closure closure_event_digest is invalid"
            )
        if action.get("contour") not in {"release:done", "release:production"}:
            raise SupervisorRuntimeError("target lane closure contour is invalid")
        if action.get("outcome") not in {"completed", "parked"}:
            raise SupervisorRuntimeError("target lane closure outcome is invalid")
        generation = action.get("supervisor_generation")
        if generation != self.engine.fence.generation:
            raise _TargetLaneClosureStale("target lane closure belongs to a stale Supervisor generation")
        task = self.registry.get_task(str(action["task_id"]))
        workstream = self.registry.get_workstream(str(action["workstream_id"]))
        if (
            task is None
            or workstream is None
            or workstream.task_id != action["task_id"]
            or task.revision != action.get("task_revision")
            or workstream.revision != action.get("workstream_revision")
        ):
            raise _TargetLaneClosureStale("target lane closure revision binding is stale")
        if (action["outcome"] == "parked") != (task.state == "parked"):
            raise _TargetLaneClosureStale("target lane closure task outcome changed")
        passport = task_passport_from_mapping(task.passport)
        manifest = passport.release_manifest
        if (
            passport.contour != action["contour"]
            or self._passport_release_target(passport) != action["target_id"]
            or self._passport_logical_lane(
                passport, workstream.workstream_id, str(action["target_id"])
            )
            != action["logical_lane_id"]
        ):
            raise _TargetLaneClosureStale("target lane closure Passport binding is stale")
        if binding_kind == "final_manifest":
            if manifest is None:
                raise _TargetLaneClosureStale(
                    "target lane closure manifest disappeared"
                )
            ordered_pr_identities = _bounded_strings(
                "ordered_pr_identities",
                action.get("ordered_pr_identities"),
                required=True,
            )
            if len(set(ordered_pr_identities)) != len(ordered_pr_identities):
                raise SupervisorRuntimeError(
                    "target lane closure PR identities are duplicated"
                )
            if action.get("anchor_pr_identity") != ordered_pr_identities[0]:
                raise SupervisorRuntimeError(
                    "target lane closure anchor PR is not the first manifest PR"
                )
            manifest_digest = _sha256(
                json.dumps(
                    contract_to_dict(manifest),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
            if (
                list(manifest.pr_identities) != list(ordered_pr_identities)
                or manifest.pr_identities[0] != action["anchor_pr_identity"]
                or manifest.logical_lane_id != action["logical_lane_id"]
                or manifest_digest != action.get("release_manifest_digest")
            ):
                raise _TargetLaneClosureStale(
                    "target lane closure final manifest binding is stale"
                )
        else:
            if (
                manifest is not None
                or action["outcome"] != "parked"
                or action["target_id"] != WB_CORE_REPOSITORY
            ):
                raise _TargetLaneClosureStale(
                    "partial target lane binding is only valid for a parked wb-core task without a final manifest"
                )
            self._validate_parked_target_lane_admission(action)
        source = self.registry.get_event(str(action["closure_event_id"]))
        if (
            source is None
            or source.get("task_id") != task.task_id
            or source.get("workstream_id") != workstream.workstream_id
            or source.get("event_type") != action["closure_event_type"]
            or self._target_lane_closure_event_digest(source) != action["closure_event_digest"]
        ):
            raise _TargetLaneClosureStale("target lane closure source event is stale")
        if action["outcome"] == "completed":
            if source.get("event_type") != "technical_terminal" or source.get("payload", {}).get("closure_barrier") is not True:
                raise _TargetLaneClosureStale("target lane closure lacks a task-level closure barrier")
        elif source.get("event_type") == "release_stalled":
            if source.get("payload", {}).get("status") != "parked":
                raise _TargetLaneClosureStale("target lane closure parked proof changed")
        elif source.get("event_type") == "incident_policy":
            if source.get("payload", {}).get("status") not in {
                "parked", "ambiguous_turn_parked", "missing_verified_checkpoint",
                "application_failed_fail_closed", "arbiter_failed_fail_closed", "parked_fail_closed",
                "human_gate",
            }:
                raise _TargetLaneClosureStale("target lane closure incident proof changed")
        else:
            raise _TargetLaneClosureStale("target lane closure parked source is invalid")

    def _validate_parked_target_lane_admission(
        self, action: Mapping[str, Any]
    ) -> None:
        raw = _mapping(action, "parked_admission")
        _exact_fields(
            raw,
            {
                "schema", "target_adapter", "candidate_id", "pr_number",
                "expected_head_sha", "admission_task_revision",
                "admission_workstream_revision", "release_action_event_id",
                "observation_event_id", "observation_event_digest",
                "admission_binding",
            },
            "parked target lane admission",
        )
        if (
            raw.get("schema") != PARKED_TARGET_LANE_ADMISSION_SCHEMA
            or raw.get("target_adapter") != WB_CORE_TARGET_ADAPTER
        ):
            raise SupervisorRuntimeError(
                "parked target lane admission schema is invalid"
            )
        for name in (
            "candidate_id", "release_action_event_id", "observation_event_id"
        ):
            value = raw.get(name)
            if (
                not isinstance(value, str)
                or not value
                or len(value) > 300
                or any(character.isspace() for character in value)
            ):
                raise SupervisorRuntimeError(
                    f"parked target lane {name} is invalid"
                )
        pr_number = raw.get("pr_number")
        admission_task_revision = raw.get("admission_task_revision")
        admission_workstream_revision = raw.get("admission_workstream_revision")
        if (
            isinstance(pr_number, bool)
            or not isinstance(pr_number, int)
            or pr_number < 1
            or any(
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 1
                for value in (
                    admission_task_revision,
                    admission_workstream_revision,
                )
            )
            or int(admission_task_revision) > int(action["task_revision"])
            or int(admission_workstream_revision)
            > int(action["workstream_revision"])
        ):
            raise SupervisorRuntimeError(
                "parked target lane historical revisions are invalid"
            )
        expected_head = raw.get("expected_head_sha")
        observation_digest = raw.get("observation_event_digest")
        if not isinstance(expected_head, str) or not re.fullmatch(
            r"[0-9a-f]{40}", expected_head
        ):
            raise SupervisorRuntimeError("parked target lane head is invalid")
        if not isinstance(observation_digest, str) or not re.fullmatch(
            r"[0-9a-f]{64}", observation_digest
        ):
            raise SupervisorRuntimeError(
                "parked target lane observation digest is invalid"
            )
        try:
            binding = wb_core_admission_binding_from_mapping(
                _mapping(raw, "admission_binding")
            )
        except (TypeError, ValueError) as exc:
            raise SupervisorRuntimeError(
                "parked target lane admission proof is malformed"
            ) from exc
        if (
            binding.target_id != WB_CORE_REPOSITORY
            or binding.pr_number != pr_number
            or binding.head_sha != expected_head
            or binding.target_task_id
            != derive_wb_core_target_task_id(str(action["task_id"]))
            or binding.task_revision != admission_task_revision
        ):
            raise SupervisorRuntimeError(
                "parked target lane admission proof is cross-bound"
            )
        observation_event = self.registry.get_event(str(raw["observation_event_id"]))
        if (
            observation_event is None
            or observation_event.get("event_type") != "release_action_observed"
            or observation_event.get("task_id") != action["task_id"]
            or observation_event.get("workstream_id") != action["workstream_id"]
            or self._target_lane_closure_event_digest(observation_event)
            != observation_digest
        ):
            raise _TargetLaneClosureStale(
                "parked target lane admission observation changed"
            )
        observation_payload = observation_event.get("payload")
        observation = (
            observation_payload.get("observation")
            if isinstance(observation_payload, Mapping)
            else None
        )
        if (
            not isinstance(observation, Mapping)
            or observation_payload.get("target_adapter") != WB_CORE_TARGET_ADAPTER
            or observation_payload.get("release_action_event_id")
            != raw["release_action_event_id"]
            or observation.get("status") not in {"admitted", "waiting_release"}
            or observation.get("candidate_id") != raw["candidate_id"]
            or observation.get("task_id") != action["task_id"]
            or observation.get("workstream_id") != action["workstream_id"]
            or observation.get("task_revision") != admission_task_revision
            or observation.get("workstream_revision")
            != admission_workstream_revision
            or observation.get("expected_head_sha") != expected_head
            or observation.get("observed_head_sha") != expected_head
            or observation.get("admission_binding")
            != dict(_mapping(raw, "admission_binding"))
            or f"admission:sha256:{binding.proof_digest}"
            not in tuple(observation.get("evidence") or ())
        ):
            raise _TargetLaneClosureStale(
                "parked target lane observation is not exact admission proof"
            )
        records = tuple(
            item
            for item in self.registry.list_outbox_records(kinds=("release_action",))
            if item.get("event_id") == raw["release_action_event_id"]
        )
        if len(records) != 1:
            raise _TargetLaneClosureStale(
                "parked target lane release action binding is missing"
            )
        action_payload = records[0].get("payload")
        if not isinstance(action_payload, Mapping):
            raise _TargetLaneClosureStale(
                "parked target lane release action payload is invalid"
            )
        candidate = release_candidate_from_mapping(
            _mapping(action_payload, "candidate")
        )
        release_candidate = _release_train_candidate_from_mapping(
            _mapping(action_payload, "release_candidate")
        )
        if (
            action_payload.get("target_adapter") != WB_CORE_TARGET_ADAPTER
            or candidate.candidate_id != raw["candidate_id"]
            or candidate.task_id != action["task_id"]
            or candidate.workstream_id != action["workstream_id"]
            or candidate.task_revision != admission_task_revision
            or candidate.workstream_revision != admission_workstream_revision
            or candidate.target_id != WB_CORE_REPOSITORY
            or candidate.logical_lane_id != action["logical_lane_id"]
            or candidate.pr_head_sha != expected_head
            or release_candidate.repo != WB_CORE_REPOSITORY
            or release_candidate.pr_number != pr_number
            or release_candidate.expected_head_sha != expected_head
            or release_candidate.task_id != action["task_id"]
            or release_candidate.workstream_id != action["workstream_id"]
            or release_candidate.revision != admission_task_revision
        ):
            raise _TargetLaneClosureStale(
                "parked target lane candidate/admission binding changed"
            )

    def _target_lane_action(
        self, payload: Mapping[str, Any]
    ) -> tuple[dict[str, Any], str | None]:
        if payload.get("schema") != INCIDENT_TARGET_LANE_DISPATCH_SCHEMA:
            return dict(payload), None
        _exact_fields(
            payload,
            {"schema", "remediation_decision_id", "action"},
            "incident target lane dispatch",
        )
        decision_id = _machine(
            "remediation_decision_id", payload.get("remediation_decision_id")
        )
        return dict(_mapping(payload, "action")), decision_id

    def _execute_target_lane_closure(self, message: OutboxMessage) -> RuntimeWorkerResult:
        if self.target_lane_closure_executor is None:
            raise SupervisorRuntimeError("target lane closure executor is unavailable")
        try:
            action, remediation_decision_id = self._target_lane_action(message.payload)
        except Exception as exc:
            return self._park_failed_policy_action_from_dispatch(message, exc)
        result_event_id = _event_id(
            "target-lane-closure-result", str(action.get("closure_id") or "")
        )
        with self._mutation_lock:
            if self.registry.get_event(result_event_id) is not None:
                self.registry.ack_outbox(message.event_id, message.claim_token, self.engine.fence)
                self.engine._release_task_scheduler_reservations(
                    str(action.get("task_id") or "")
                )
                self._reconcile_incident_applications()
                return RuntimeWorkerResult(message.kind, message.event_id, "deduped", result_event_id)
        try:
            self._validate_target_lane_closure(action)
            if (
                remediation_decision_id is None
                and self._target_lane_incident_exhausted(
                    str(action["task_id"]),
                    task_revision=int(action["task_revision"]),
                )
            ):
                raise _TargetLaneClosureStale(
                    "target lane closure is already owned by its current incident"
                )
            self._require_release_actuator_authorization(
                str(action["task_id"]),
                include_lane_release=True,
            )
        except _TargetLaneClosureStale as exc:
            if remediation_decision_id is not None:
                return self._fail_incident_dispatch(
                    message,
                    remediation_decision_id,
                    exc,
                    verification_identity="target-lane-stale-after-arbiter",
                )
            return self._supersede_target_lane_closure(message, exc)
        try:
            guard = RuntimeActionGuard(self, action, release=False)
            guard.assert_current()
            raw = self.target_lane_closure_executor(dict(action), guard)
            guard.assert_current()
            if guard.callback_checks < 2:
                raise SupervisorRuntimeError(
                    "target lane closure adapter omitted mutation/readback fence checkpoints"
                )
            self._validate_target_lane_closure(action)
            receipt = _validated_target_lane_closure_receipt(raw, action)
            if receipt["status"] == "submitted":
                return self._persist_target_lane_closure_submission(
                    message, receipt, action=action
                )
            with self._mutation_lock:
                self.registry.record_input_event_outbox(
                    message_id=_event_id("target-lane-closure-result-receipt", message.event_id),
                    source="supervisor-target-lane-closure-worker",
                    input_payload={
                        "target_lane_closure_event_id": message.event_id,
                        "receipt": receipt,
                    },
                    event_id=result_event_id,
                    event_type="target_lane_closure_completed",
                    event_payload={
                        "schema": "dev-control-plane/target-lane-closure-result-event/v2",
                        "action": dict(action),
                        "receipt": receipt,
                        "remediation_decision_id": remediation_decision_id,
                    },
                    outbox_items=(self._dirty_item(result_event_id, str(receipt["task_id"])),),
                    fence=self.engine.fence,
                    task_id=str(receipt["task_id"]),
                    workstream_id=str(receipt["workstream_id"]),
                )
                self.registry.ack_outbox(message.event_id, message.claim_token, self.engine.fence)
                self._reconcile_incident_applications()
            return RuntimeWorkerResult(message.kind, message.event_id, str(receipt["status"]), result_event_id)
        except _TargetLaneClosureStale as exc:
            if remediation_decision_id is not None:
                return self._fail_incident_dispatch(
                    message,
                    remediation_decision_id,
                    exc,
                    verification_identity="target-lane-stale-after-arbiter",
                )
            return self._supersede_target_lane_closure(message, exc)
        except Exception as exc:
            occurrence, fingerprint = self._record_target_lane_closure_failure(
                message, exc, action=action
            )
            if remediation_decision_id is not None:
                return self._fail_incident_dispatch(
                    message,
                    remediation_decision_id,
                    exc,
                    verification_identity="target-lane-actuator-failed-after-arbiter",
                )
            if occurrence == 1:
                with self._mutation_lock:
                    self.registry.nack_outbox(
                        message.event_id,
                        message.claim_token,
                        self.engine.fence,
                        retry_at=self.clock() + self.retry_delay_seconds,
                        sanitized_error=_error_code(exc),
                    )
                return RuntimeWorkerResult(message.kind, message.event_id, "retry_scheduled", _error_code(exc))
            return self._route_target_lane_incident(
                message, action, exc, fingerprint=fingerprint
            )

    def _persist_target_lane_closure_submission(
        self,
        message: OutboxMessage,
        receipt: Mapping[str, Any],
        *,
        action: Mapping[str, Any],
    ) -> RuntimeWorkerResult:
        event_id = _event_id(
            "target-lane-closure-submitted",
            f"{message.event_id}|{receipt['evidence_digest']}",
        )
        with self._mutation_lock:
            if self.registry.get_event(event_id) is None:
                self.registry.record_input_event_outbox(
                    message_id=_event_id("target-lane-closure-submission-receipt", event_id),
                    source="supervisor-target-lane-closure-worker",
                    input_payload={
                        "target_lane_closure_event_id": message.event_id,
                        "evidence_digest": receipt["evidence_digest"],
                    },
                    event_id=event_id,
                    event_type="target_lane_closure_observed",
                    event_payload={
                        "schema": "dev-control-plane/target-lane-closure-observed-event/v2",
                        "action": dict(action),
                        "receipt": dict(receipt),
                        "remediation_decision_id": message.payload.get(
                            "remediation_decision_id"
                        ),
                    },
                    outbox_items=(self._dirty_item(event_id, str(receipt["task_id"])),),
                    fence=self.engine.fence,
                    task_id=str(receipt["task_id"]),
                    workstream_id=str(receipt["workstream_id"]),
                )
            self.registry.nack_outbox(
                message.event_id,
                message.claim_token,
                self.engine.fence,
                retry_at=self.clock() + float(receipt["retry_after_seconds"]),
                sanitized_error=str(receipt["reason_code"]),
            )
        return RuntimeWorkerResult(message.kind, message.event_id, "submitted", str(receipt["reason_code"]))

    def _supersede_target_lane_closure(
        self,
        message: OutboxMessage,
        exc: Exception,
    ) -> RuntimeWorkerResult:
        action, _decision_id = self._target_lane_action(message.payload)
        event_id = _event_id("target-lane-closure-superseded", message.event_id)
        with self._mutation_lock:
            if self.registry.get_event(event_id) is None:
                self.registry.record_input_event_outbox(
                    message_id=_event_id("target-lane-closure-superseded-receipt", event_id),
                    source="supervisor-target-lane-closure-reconciler",
                    input_payload={
                        "target_lane_closure_event_id": message.event_id,
                        "reason_code": _error_code(exc),
                    },
                    event_id=event_id,
                    event_type="target_lane_closure_superseded",
                    event_payload={
                        "schema": "dev-control-plane/target-lane-closure-superseded/v2",
                        "closure_id": action.get("closure_id"),
                        "task_revision": action.get("task_revision"),
                        "workstream_revision": action.get("workstream_revision"),
                        "reason_code": _error_code(exc),
                        "observed_at": _iso(self.clock()),
                    },
                    outbox_items=(self._dirty_item(event_id, message.task_id),),
                    fence=self.engine.fence,
                    task_id=message.task_id,
                    workstream_id=str(action.get("workstream_id") or "") or None,
                )
            self.registry.ack_outbox(message.event_id, message.claim_token, self.engine.fence)
        return RuntimeWorkerResult(message.kind, message.event_id, "stale_discarded", _error_code(exc))

    def _record_target_lane_closure_failure(
        self,
        message: OutboxMessage,
        exc: Exception,
        *,
        action: Mapping[str, Any],
    ) -> tuple[int, str]:
        closure_id = str(action.get("closure_id") or "")
        fingerprint = _sha256(
            f"{closure_id}|{_error_code(exc)}|{_sha256(str(exc)[:1_000])}"
        )
        prior = self.registry.list_events(
            task_id=message.task_id,
            workstream_id=str(action.get("workstream_id") or "") or None,
            event_types=("target_lane_closure_failure_observed",),
        )
        occurrence = 1 + sum(
            event.get("payload", {}).get("closure_id") == closure_id
            and event.get("payload", {}).get("fingerprint") == fingerprint
            for event in prior
        )
        event_id = _event_id(
            "target-lane-closure-failure",
            f"{closure_id}|{fingerprint}|{occurrence}",
        )
        with self._mutation_lock:
            self.registry.record_input_event_outbox(
                message_id=_event_id("target-lane-closure-failure-receipt", event_id),
                source="supervisor-target-lane-closure-worker",
                input_payload={
                    "target_lane_closure_event_id": message.event_id,
                    "closure_id": closure_id,
                    "fingerprint": fingerprint,
                    "occurrence": occurrence,
                },
                event_id=event_id,
                event_type="target_lane_closure_failure_observed",
                event_payload={
                    "schema": "dev-control-plane/target-lane-closure-failure/v2",
                    "closure_id": closure_id,
                    "task_revision": action.get("task_revision"),
                    "workstream_revision": action.get("workstream_revision"),
                    "fingerprint": fingerprint,
                    "occurrence": occurrence,
                    "error_code": _error_code(exc),
                    "observed_at": _iso(self.clock()),
                },
                outbox_items=(self._dirty_item(event_id, message.task_id),),
                fence=self.engine.fence,
                task_id=message.task_id,
                workstream_id=str(action.get("workstream_id") or "") or None,
            )
        return occurrence, fingerprint

    def _route_target_lane_incident(
        self,
        message: OutboxMessage,
        action: Mapping[str, Any],
        exc: Exception,
        *,
        fingerprint: str,
    ) -> RuntimeWorkerResult:
        """Open the one fresh incident after one exact target-lane retry."""

        task_id = str(action["task_id"])
        workstream_id = str(action["workstream_id"])
        task = self.registry.get_task(task_id)
        workstream = self.registry.get_workstream(workstream_id)
        executor = self.registry.current_executor(task_id, workstream_id)
        if task is None or workstream is None or executor is None:
            return self._park_target_lane_closure(message, exc)
        latest = self._latest_incident_state(task_id, workstream_id, fingerprint)
        if latest is not None and (
            latest.incident_case_id is not None
            or latest.arbiter_applied
            or latest.parked
            or latest.resolved
        ):
            if latest.arbiter_decision_id and latest.arbiter_applied:
                return self._fail_incident_dispatch(
                    message,
                    latest.arbiter_decision_id,
                    exc,
                    verification_identity="target-lane-recurrence-after-arbiter",
                )
            with self._mutation_lock:
                self.registry.ack_outbox(
                    message.event_id, message.claim_token, self.engine.fence
                )
            return RuntimeWorkerResult(
                message.kind,
                message.event_id,
                "incident_open",
                latest.incident_case_id or fingerprint,
            )
        evidence_digest = _sha256(
            f"{action['closure_id']}|{fingerprint}|{_error_code(exc)}"
        )
        case_digest = _sha256(
            f"target-lane-incident|{fingerprint}|{task.revision}|"
            f"{workstream.revision}|{executor.executor_generation}|{evidence_digest}"
        )
        state = IncidentState(
            task_id=task_id,
            workstream_id=workstream_id,
            fingerprint=fingerprint,
            context=IncidentContext(
                passport_revision=task.revision,
                strategy_digest=_sha256("mechanical-target-lane-closure-v2"),
                causal_evidence_digest=evidence_digest,
                verified_checkpoint_id=self._incident_checkpoint_id(
                    task_id, workstream_id, executor.executor_generation
                ),
            ),
            failure_count=3,
            current_executor_generation=executor.executor_generation,
            retry_used=True,
            incident_case_id=f"incident:{case_digest[:24]}",
            incident_case_digest=case_digest,
        )
        incident_item = self._incident_arbiter_item(state)
        incident_item["payload"]["binding"]["pr_head_sha"] = (
            self._target_lane_action_head(action)
        )
        incident_item["payload"]["remediation"] = {
            "schema": TARGET_LANE_INCIDENT_REMEDIATION_SCHEMA,
            "kind": "target_lane_closure",
            "action": dict(action),
            "prior_action_event_id": message.event_id,
            "fingerprint": fingerprint,
        }
        event_id = _event_id(
            "target-lane-incident", f"{action['closure_id']}:{fingerprint}"
        )
        with self._mutation_lock:
            self.registry.record_input_event_outbox(
                message_id=_event_id(
                    "target-lane-incident-receipt", message.event_id
                ),
                source="supervisor-target-lane-closure-worker",
                input_payload={
                    "target_lane_closure_event_id": message.event_id,
                    "closure_id": action["closure_id"],
                    "fingerprint": fingerprint,
                    "error_code": _error_code(exc),
                },
                event_id=event_id,
                event_type="incident_policy",
                event_payload={
                    **self._incident_event_payload(
                        state,
                        action="invoke_incident_arbiter",
                        status="incident_open",
                        attempt=state.failure_count,
                        error_code=_error_code(exc),
                    ),
                    "actor": "mechanical_target_lane_closure",
                    "successor_applicable": False,
                    "closure_id": action["closure_id"],
                },
                outbox_items=(
                    incident_item,
                    self._dirty_item(event_id, task_id),
                ),
                fence=self.engine.fence,
                task_id=task_id,
                workstream_id=workstream_id,
                executor_generation=executor.executor_generation,
            )
            self.registry.ack_outbox(
                message.event_id, message.claim_token, self.engine.fence
            )
        return RuntimeWorkerResult(
            message.kind,
            message.event_id,
            "incident_open",
            state.incident_case_id or "",
        )

    def _target_lane_action_head(self, action: Mapping[str, Any]) -> str:
        if action.get("binding_kind") == "parked_admission":
            head = _mapping(action, "parked_admission").get("expected_head_sha")
        else:
            identity = str(action.get("anchor_pr_identity") or "")
            match = re.search(r":(?P<head>[0-9a-f]{40}):[0-9a-f]{40}$", identity)
            head = match.group("head") if match is not None else None
        if not isinstance(head, str) or not re.fullmatch(r"[0-9a-f]{40}", head):
            raise SupervisorRuntimeError(
                "target lane incident lacks an immutable PR head"
            )
        return head

    def _park_target_lane_closure(
        self,
        message: OutboxMessage,
        exc: Exception,
    ) -> RuntimeWorkerResult:
        closure_id = str(message.payload.get("closure_id") or "")
        event_id = _event_id("target-lane-closure-stalled", closure_id)
        task = self.registry.get_task(str(message.payload.get("task_id") or ""))
        if task is None:
            raise SupervisorRuntimeError("target lane closure task disappeared")
        passport = task_passport_from_mapping(task.passport)
        attention_event_id = _event_id("curator-target-lane-closure-stall", closure_id)
        with self._mutation_lock:
            if self.registry.get_event(event_id) is None:
                self.registry.record_input_event_outbox(
                    message_id=_event_id("target-lane-closure-stalled-receipt", closure_id),
                    source="supervisor-target-lane-closure-worker",
                    input_payload={
                        "target_lane_closure_event_id": message.event_id,
                        "closure_id": closure_id,
                        "error_code": _error_code(exc),
                    },
                    event_id=event_id,
                    event_type="target_lane_closure_stalled",
                    event_payload={
                        "schema": "dev-control-plane/target-lane-closure-stalled/v2",
                        "action": dict(message.payload),
                        "receipt": {
                            "closure_id": closure_id,
                            "status": "parked",
                            "task_id": message.payload.get("task_id"),
                            "task_revision": message.payload.get("task_revision"),
                            "workstream_id": message.payload.get("workstream_id"),
                            "workstream_revision": message.payload.get("workstream_revision"),
                            "target_id": message.payload.get("target_id"),
                            "logical_lane_id": message.payload.get("logical_lane_id"),
                            "outcome": message.payload.get("outcome"),
                            "closure_event_id": message.payload.get("closure_event_id"),
                            "closure_event_digest": message.payload.get("closure_event_digest"),
                            "reason_code": _error_code(exc),
                            "observed_at": _iso(self.clock()),
                        },
                    },
                    outbox_items=(
                        {
                            "event_id": attention_event_id,
                            "kind": "curator_attention",
                            "payload": {
                                "schema": "dev-control-plane/curator-attention/v2",
                                "attention_id": _event_id("target-lane-closure-attention", closure_id),
                                "task_id": task.task_id,
                                "workstream_id": message.payload.get("workstream_id"),
                                "curator_thread_id": passport.curator.thread_id,
                                "kind": "serious_stall",
                                "handoff_ru": (
                                    "Статус: Блокер\n"
                                    f"Задача: {passport.title}\n"
                                    "Доказательство: target release lane не закрылась после одного bounded retry.\n"
                                    "Сейчас: закрытие припарковано без бесконечных повторов."
                                ),
                                "required_action": "Измените Passport/стратегию или устраните доказанную причину target lane closure.",
                                "created_at": _iso(self.clock()),
                            },
                            "task_id": task.task_id,
                            "coalescible": False,
                            "coalesce_key": None,
                        },
                        self._dirty_item(event_id, task.task_id),
                    ),
                    fence=self.engine.fence,
                    task_id=task.task_id,
                    workstream_id=str(message.payload.get("workstream_id") or "") or None,
                )
            self.registry.ack_outbox(message.event_id, message.claim_token, self.engine.fence)
        return RuntimeWorkerResult(message.kind, message.event_id, "parked", _error_code(exc))

    def _scheduled_candidate_by_identity(
        self,
        events: Sequence[Mapping[str, Any]],
        candidate_id: str,
        pr_head_sha: str,
    ) -> Any | None:
        for event in reversed(events):
            if event.get("event_type") not in {
                "release_reserved", "release_head_reserved",
                "semantic_release_case", "release_plan_decision",
            }:
                continue
            if event.get("event_type") == "release_head_reserved":
                raw_candidate = event.get("payload", {}).get("candidate")
                candidates = [raw_candidate] if isinstance(raw_candidate, Mapping) else None
            else:
                candidates = event.get("payload", {}).get("candidates")
            if not isinstance(candidates, list):
                semantic = event.get("payload", {}).get("semantic_case")
                candidates = semantic.get("candidates") if isinstance(semantic, Mapping) else None
            if not isinstance(candidates, list):
                continue
            for raw in candidates:
                if (
                    isinstance(raw, Mapping)
                    and raw.get("candidate_id") == candidate_id
                    and raw.get("pr_head_sha") == pr_head_sha
                ):
                    return release_candidate_from_mapping(raw)
        return None

    def _reserve_and_enqueue_release_resolution(self, candidate: Any, *, source_event_id: str) -> None:
        identity = f"{candidate.candidate_id}:{candidate.pr_head_sha}"
        event_id = _event_id("release-resolution", identity)
        reservation_event_id = _event_id("release-head-reserved", identity)
        if any(
            item["event_id"] == event_id
            for item in self.registry.list_outbox_summaries(kinds=("release_candidate_resolution",))
        ):
            return
        task = self.registry.get_task(candidate.task_id)
        workstream = self.registry.get_workstream(candidate.workstream_id)
        if (
            task is None
            or workstream is None
            or task.revision != candidate.task_revision
            or workstream.revision != candidate.workstream_revision
            or task.state in {"parked", "accepted"}
            or workstream.state == "parked"
        ):
            raise SupervisorRuntimeError("release candidate changed before reservation")
        acquired = False
        try:
            self._validate_release_candidate_reservation(candidate, renew=True)
        except LockConflict:
            try:
                self.registry.acquire_scheduler_reservation(
                    task_id=candidate.task_id,
                    workstream_id=candidate.workstream_id,
                    target_id=candidate.target_id,
                    resources=candidate.resources,
                    fence=self.engine.fence,
                    ttl=self.release_reservation_ttl_seconds,
                )
                acquired = True
            except LockConflict:
                return
        try:
            self.registry.record_input_event_outbox(
                message_id=_event_id(
                    "release-head-reservation-receipt", reservation_event_id
                ),
                source="supervisor-release-orchestration-fold",
                input_payload={
                    "source_event_id": source_event_id,
                    "candidate_id": candidate.candidate_id,
                    "pr_head_sha": candidate.pr_head_sha,
                },
                event_id=reservation_event_id,
                event_type="release_head_reserved",
                event_payload={
                    "schema": "dev-control-plane/release-head-reserved/v2",
                    "candidate": asdict(candidate),
                    "source_event_id": source_event_id,
                },
                outbox_items=(
                    {
                        "event_id": event_id,
                        "kind": "release_candidate_resolution",
                        "payload": {
                            "schema": "dev-control-plane/release-candidate-resolution/v2",
                            "candidate": asdict(candidate),
                            "source_event_id": source_event_id,
                            "remediation_decision_id": None,
                        },
                        "task_id": candidate.task_id,
                        "coalescible": False,
                        "coalesce_key": None,
                    },
                    self._dirty_item(reservation_event_id, candidate.task_id),
                ),
                fence=self.engine.fence,
                task_id=candidate.task_id,
                workstream_id=candidate.workstream_id,
            )
        except Exception:
            if acquired:
                self.registry.release_scheduler_reservation_owner(
                    task_id=candidate.task_id,
                    workstream_id=candidate.workstream_id,
                    fence=self.engine.fence,
                )
            raise

    def _ensure_release_candidate_reservation(
        self, candidate: SchedulerReleaseCandidate
    ) -> None:
        """Attest or reconstruct one current reservation after restart."""

        try:
            self._validate_release_candidate_reservation(candidate, renew=True)
            return
        except LockConflict:
            pass
        self._assert_registered_candidate_current(candidate)
        current = {
            (item.candidate_id, item.pr_head_sha)
            for item, _source_event_id in self._current_registered_release_candidates()
        }
        if (candidate.candidate_id, candidate.pr_head_sha) not in current:
            raise LockConflict("release candidate registration is no longer current")
        self.registry.acquire_scheduler_reservation(
            task_id=candidate.task_id,
            workstream_id=candidate.workstream_id,
            target_id=candidate.target_id,
            resources=candidate.resources,
            fence=self.engine.fence,
            ttl=self.release_reservation_ttl_seconds,
        )
        self._validate_release_candidate_reservation(candidate, renew=True)

    def _semantic_case_from_payload(self, payload: Mapping[str, Any]) -> SemanticReleaseCase:
        decision = _mapping_value(payload.get("decision"), "schedule decision")
        metadata = _mapping_value(decision.get("semantic_case"), "semantic release case")
        candidates_raw = payload.get("candidates")
        if not isinstance(candidates_raw, list):
            raise SupervisorRuntimeError("semantic release case candidates are missing")
        return SemanticReleaseCase(
            case_id=str(metadata["case_id"]),
            case_digest=str(metadata["case_digest"]),
            reasons=tuple(metadata["reasons"]),
            candidates=tuple(release_candidate_from_mapping(_mapping_value(item, "release candidate")) for item in candidates_raw),
            created_at=str(metadata["created_at"]),
        )

    def _semantic_case_from_decision_payload(self, payload: Mapping[str, Any]) -> SemanticReleaseCase:
        semantic = _mapping_value(payload.get("semantic_case"), "semantic release case")
        candidates = semantic.get("candidates")
        if not isinstance(candidates, list):
            raise SupervisorRuntimeError("release plan lost its candidate snapshot")
        return SemanticReleaseCase(
            case_id=str(semantic["case_id"]),
            case_digest=str(semantic["case_digest"]),
            reasons=tuple(semantic["reasons"]),
            candidates=tuple(release_candidate_from_mapping(_mapping_value(item, "release candidate")) for item in candidates),
            created_at=str(semantic["created_at"]),
        )

    def _semantic_case_payload(self, semantic_case: SemanticReleaseCase) -> dict[str, Any]:
        return {
            "case_id": semantic_case.case_id,
            "case_digest": semantic_case.case_digest,
            "reasons": list(semantic_case.reasons),
            "candidates": [asdict(candidate) for candidate in semantic_case.candidates],
            "created_at": semantic_case.created_at,
        }

    def _command_tick(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        _exact_fields(payload, set(), "tick payload")
        with self._mutation_lock:
            result = self.engine.tick()
        return {
            "projection_reserved": result.projection_reserved,
            "projection_event_id": result.projection_event_id,
            "publish_results": [asdict(item) for item in result.publish_results],
        }

    def _command_start_executor(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        _exact_fields(payload, {"passport", "workstream", "cwd", "message_id"}, "start executor payload")
        passport_raw = dict(_mapping(payload, "passport"))
        workstream_raw = dict(_mapping(payload, "workstream"))
        passport = task_passport_from_mapping(passport_raw)
        workstream = workstream_from_mapping(workstream_raw)
        if passport.executor is not None:
            raise SupervisorCommandError("start_executor requires an unbound Passport executor")
        if getattr(workstream, "executor", None) is not None:
            raise SupervisorCommandError("start_executor requires an unbound workstream executor")
        if workstream.task_id != passport.task_id:
            raise SupervisorCommandError("workstream task does not match Passport")
        cwd = self._workspace(payload.get("cwd"))
        message_id = _machine("message_id", payload.get("message_id"))
        event_id = _event_id("codex-start", message_id)
        semantic_passport = contract_to_dict(passport)
        for cosmetic in ("revision", "title", "created_at", "executor"):
            semantic_passport.pop(cosmetic, None)
        strategy_digest = _sha256(
            "initial-unbound-start|"
            + json.dumps(
                semantic_passport,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        outbox_payload = {
            "schema": THREAD_START_SCHEMA,
            "passport": passport_raw,
            "workstream": workstream_raw,
            "cwd": str(cwd),
            "message_id": message_id,
            "strategy_digest": strategy_digest,
            "reconciliation_event_id": None,
            "started_thread": None,
            "start_intent": None,
        }
        with self._mutation_lock:
            # An unbound start may have reached App Server before its local
            # identity receipt.  That ambiguous durable intent is replayable
            # only under the exact original message; a new message must never
            # blind-create a second executor for the same binding.
            prior_starts = self.registry.list_outbox_records(
                kinds=("codex_thread_start",)
            )
            for prior in prior_starts:
                prior_payload = prior.get("payload")
                if not isinstance(prior_payload, Mapping):
                    continue
                prior_passport = prior_payload.get("passport")
                prior_workstream = prior_payload.get("workstream")
                if not isinstance(prior_passport, Mapping) or not isinstance(
                    prior_workstream, Mapping
                ):
                    continue
                if (
                    prior_passport.get("task_id") == passport.task_id
                    and prior_workstream.get("workstream_id")
                    == workstream.workstream_id
                    and prior_payload.get("message_id") != message_id
                ):
                    raise SupervisorCommandError(
                        "executor start binding already has a durable intent; use corrective recovery"
                    )
            created = self.registry.reserve_initial_executor_start(
                passport,
                workstream,
                canonical_workspace=str(cwd),
                message_id=message_id,
                source="private-unix-command:start-executor",
                inbox_payload={"passport": passport_raw, "workstream": workstream_raw, "cwd": str(cwd)},
                outbox_event_id=event_id,
                outbox_payload=outbox_payload,
                fence=self.engine.fence,
            )
        return {"queued": created, "event_id": event_id, "task_id": passport.task_id}

    def _command_reconcile_unbound_start(
        self, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        _exact_fields(
            payload,
            {
                "task_id",
                "expected_task_revision",
                "workstream_id",
                "expected_workstream_revision",
                "failed_event_id",
                "failed_event_digest",
                "replacement_passport",
                "replacement_workstream",
                "strategy_digest",
                "justification",
                "cwd",
                "message_id",
            },
            "unbound start reconciliation payload",
        )
        task_id = _machine("task_id", payload.get("task_id"))
        workstream_id = _machine("workstream_id", payload.get("workstream_id"))
        failed_event_id = _machine(
            "failed_event_id", payload.get("failed_event_id")
        )
        failed_event_digest = _digest_value(
            "failed_event_digest", payload.get("failed_event_digest")
        )
        strategy_digest = _digest_value(
            "strategy_digest", payload.get("strategy_digest")
        )
        message_id = _machine("message_id", payload.get("message_id"))
        expected_task_revision = payload.get("expected_task_revision")
        expected_workstream_revision = payload.get("expected_workstream_revision")
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 1
            for value in (expected_task_revision, expected_workstream_revision)
        ):
            raise SupervisorCommandError(
                "unbound reconciliation revisions must be positive"
            )
        justification = payload.get("justification")
        if (
            not isinstance(justification, str)
            or not justification.strip()
            or len(justification) > 2_000
            or "\n" in justification
            or _CREDENTIAL_RE.search(justification)
        ):
            raise SupervisorCommandError(
                "unbound reconciliation justification must be one sanitized line"
            )
        cwd = self._workspace(payload.get("cwd"))
        passport_raw = dict(_mapping(payload, "replacement_passport"))
        workstream_raw = dict(_mapping(payload, "replacement_workstream"))
        passport = task_passport_from_mapping(passport_raw)
        workstream = workstream_from_mapping(workstream_raw)
        if (
            passport.task_id != task_id
            or passport.revision != expected_task_revision + 1
            or passport.executor is not None
            or workstream.task_id != task_id
            or workstream.workstream_id != workstream_id
            or workstream.generation != 1
            or workstream.revision != expected_workstream_revision + 1
            or workstream.state != "started"
            or workstream.executor is not None
        ):
            raise SupervisorCommandError(
                "unbound reconciliation replacement contracts are stale"
            )
        require_passport_action(passport, "codex_workspace_mutation")
        with self._mutation_lock:
            task = self.registry.get_task(task_id)
            current_workstream = self.registry.get_workstream(workstream_id)
            failed_event = self.registry.get_event(failed_event_id)
            if (
                task is None
                or current_workstream is None
            ):
                raise SupervisorCommandError(
                    "unbound reconciliation binding is unknown"
                )
            self._assert_workspace_binding(task_id, workstream_id, cwd)
            if (
                failed_event is None
                or failed_event.get("task_id") != task_id
                or failed_event.get("workstream_id") != workstream_id
                or _sha256(
                    json.dumps(
                        failed_event.get("payload"),
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                )
                != failed_event_digest
            ):
                raise SupervisorCommandError(
                    "unbound reconciliation failure binding is stale"
                )
            reconciliation_event_id = _event_id(
                "unbound-start-reconciled", failed_event_id + "|" + message_id
            )
            start_event_id = _event_id("codex-start", message_id)
            start_payload = {
                "schema": THREAD_START_SCHEMA,
                "passport": passport_raw,
                "workstream": workstream_raw,
                "cwd": str(cwd),
                "message_id": message_id,
                "strategy_digest": strategy_digest,
                "reconciliation_event_id": reconciliation_event_id,
                "started_thread": None,
                "start_intent": None,
            }
            result = self.registry.reconcile_unbound_executor_start(
                passport,
                workstream,
                expected_task_revision=expected_task_revision,
                expected_workstream_revision=expected_workstream_revision,
                failed_event_id=failed_event_id,
                failed_event_digest=failed_event_digest,
                strategy_digest=strategy_digest,
                canonical_workspace=str(cwd),
                message_id=message_id,
                source="private-unix-command:reconcile-unbound-start",
                input_payload={
                    **dict(payload),
                    "justification": _sha256(justification.strip()),
                },
                reconciliation_event_id=reconciliation_event_id,
                reconciliation_payload={
                    "schema": "dev-control-plane/unbound-start-reconciliation/v2",
                    "status": "replacement_start_reserved",
                    "task_revision": passport.revision,
                    "workstream_revision": workstream.revision,
                    "justification_digest": _sha256(justification.strip()),
                    "updated_at": _iso(self.clock()),
                },
                start_event_id=start_event_id,
                start_payload=start_payload,
                projection_event_id=_event_id("dirty", reconciliation_event_id),
                fence=self.engine.fence,
            )
        return result

    def _command_apply_corrective_generation(
        self, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Consume one exact parked cause and reserve one proven successor."""

        required = {
            "task_id",
            "expected_task_revision",
            "workstream_id",
            "expected_workstream_generation",
            "expected_workstream_revision",
            "expected_executor_generation",
            "trigger_event_id",
            "trigger_event_digest",
            "replacement_passport",
            "corrective_workstream",
            "strategy_digest",
            "causal_evidence_digest",
            "justification",
            "cwd",
            "prompt",
            "owner_action_attestation",
            "message_id",
        }
        _exact_fields(payload, required, "corrective generation payload")
        task_id = _machine("task_id", payload.get("task_id"))
        workstream_id = _machine(
            "workstream_id", payload.get("workstream_id")
        )
        message_id = _machine("message_id", payload.get("message_id"))
        trigger_event_id = _machine(
            "trigger_event_id", payload.get("trigger_event_id")
        )
        trigger_event_digest = _digest_value(
            "trigger_event_digest", payload.get("trigger_event_digest")
        )
        strategy_digest = _digest_value(
            "strategy_digest", payload.get("strategy_digest")
        )
        causal_evidence_digest = _digest_value(
            "causal_evidence_digest", payload.get("causal_evidence_digest")
        )
        coordinates: dict[str, int] = {}
        for name in (
            "expected_task_revision",
            "expected_workstream_generation",
            "expected_workstream_revision",
            "expected_executor_generation",
        ):
            value = payload.get(name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise SupervisorCommandError(f"{name} must be positive")
            coordinates[name] = value
        justification = payload.get("justification")
        if (
            not isinstance(justification, str)
            or not justification.strip()
            or len(justification) > 2_000
            or "\n" in justification
            or _CREDENTIAL_RE.search(justification)
        ):
            raise SupervisorCommandError(
                "corrective justification must be one bounded sanitized line"
            )
        justification = justification.strip()
        prompt = _prompt(payload.get("prompt"))
        cwd = self._workspace(payload.get("cwd"))
        replacement_raw = dict(_mapping(payload, "replacement_passport"))
        corrective_raw = dict(_mapping(payload, "corrective_workstream"))
        replacement = task_passport_from_mapping(replacement_raw)
        corrective = workstream_from_mapping(corrective_raw)
        if (
            replacement.task_id != task_id
            or replacement.revision
            != coordinates["expected_task_revision"] + 1
            or replacement.executor is not None
        ):
            raise SupervisorCommandError(
                "replacement Passport has a stale identity, revision or executor"
            )
        if (
            corrective.task_id != task_id
            or corrective.workstream_id != workstream_id
            or corrective.generation
            != coordinates["expected_workstream_generation"] + 1
            or corrective.corrective_of_generation
            != coordinates["expected_workstream_generation"]
            or corrective.revision != 1
            or corrective.state != "recovering"
            or corrective.executor is not None
        ):
            raise SupervisorCommandError(
                "corrective workstream generation contract is not exact"
            )
        try:
            require_passport_action(replacement, "codex_workspace_mutation")
        except Exception as exc:
            raise SupervisorCommandError(
                "replacement Passport does not authorize executor recovery"
            ) from exc

        with self._mutation_lock:
            task = self.registry.get_task(task_id)
            workstream = self.registry.get_workstream(workstream_id)
            executor = self.registry.current_executor(task_id, workstream_id)
            trigger = self.registry.get_event(trigger_event_id)
            if (
                task is None
                or workstream is None
                or executor is None
                or workstream.task_id != task_id
            ):
                raise SupervisorCommandError(
                    "corrective recovery binding is unknown"
                )
            if (
                task.revision != coordinates["expected_task_revision"]
                or workstream.generation
                != coordinates["expected_workstream_generation"]
                or workstream.revision
                != coordinates["expected_workstream_revision"]
                or executor.executor_generation
                != coordinates["expected_executor_generation"]
            ):
                raise SupervisorCommandError(
                    "corrective recovery CAS coordinates are stale"
                )
            try:
                self._assert_workspace_binding(task_id, workstream_id, cwd)
            except SupervisorRuntimeError as exc:
                raise SupervisorCommandError(
                    "corrective cwd differs from the immutable executor workspace"
                ) from exc
            if (
                trigger is None
                or trigger.get("task_id") != task_id
                or trigger.get("workstream_id") != workstream_id
                or _sha256(
                    json.dumps(
                        trigger.get("payload"),
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                )
                != trigger_event_digest
            ):
                raise SupervisorCommandError(
                    "corrective trigger identity or digest is stale"
                )
            checkpoint_event = self._latest_verified_checkpoint(
                task_id,
                workstream_id,
                coordinates["expected_executor_generation"],
            )
            if checkpoint_event is None:
                raise SupervisorCommandError(
                    "corrective recovery requires the latest verified checkpoint"
                )
            checkpoint_contract = dict(
                _mapping(checkpoint_event.get("payload", {}), "contract")
            )
            checkpoint_digest = _sha256(
                json.dumps(
                    checkpoint_contract,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )

            old_semantic = dict(task.passport)
            new_semantic = contract_to_dict(replacement)
            for item in (old_semantic, new_semantic):
                for cosmetic in ("revision", "title", "created_at", "executor"):
                    item.pop(cosmetic, None)
            passport_material = old_semantic != new_semantic
            trigger_payload = _mapping_value(
                trigger.get("payload"), "corrective trigger payload"
            )
            state_raw = trigger_payload.get("incident_state")
            human_gate = (
                trigger.get("event_type") == "incident_policy"
                and trigger_payload.get("status") == "human_gate"
            )
            if isinstance(state_raw, Mapping):
                prior_state = _incident_state_from_mapping(state_raw)
                if (
                    prior_state.task_id != task_id
                    or prior_state.workstream_id != workstream_id
                    or prior_state.current_executor_generation
                    != coordinates["expected_executor_generation"]
                ):
                    raise SupervisorCommandError(
                        "corrective incident state binding is stale"
                    )
                strategy_material = (
                    strategy_digest != prior_state.context.strategy_digest
                )
                evidence_material = (
                    causal_evidence_digest
                    != prior_state.context.causal_evidence_digest
                )
                fingerprint = prior_state.fingerprint
            else:
                fingerprint_value = trigger_payload.get("fingerprint")
                fingerprint = (
                    str(fingerprint_value)
                    if isinstance(fingerprint_value, str)
                    and re.fullmatch(r"[0-9a-f]{64}", fingerprint_value)
                    else _sha256(trigger_event_id + "|" + trigger_event_digest)
                )
                prior_state = IncidentState(
                    task_id=task_id,
                    workstream_id=workstream_id,
                    fingerprint=fingerprint,
                    context=IncidentContext(
                        passport_revision=task.revision,
                        strategy_digest=strategy_digest,
                        causal_evidence_digest=causal_evidence_digest,
                        verified_checkpoint_id=str(checkpoint_event["event_id"]),
                    ),
                    current_executor_generation=coordinates[
                        "expected_executor_generation"
                    ],
                )
                strategy_material = False
                evidence_material = False

            owner_attestation_raw = payload.get("owner_action_attestation")
            owner_attestation_digest: str | None = None
            owner_material = False
            if human_gate:
                if self.owner_action_verifier is None or not isinstance(
                    owner_attestation_raw, Mapping
                ):
                    raise SupervisorCommandError(
                        "HumanGate recovery requires an exact-curator action verifier"
                    )
                requested_action = str(trigger_payload.get("requested_action") or "")
                expected_attestation = {
                    "trigger_event_id": trigger_event_id,
                    "trigger_event_digest": trigger_event_digest,
                    "task_id": task_id,
                    "task_revision": task.revision,
                    "workstream_id": workstream_id,
                    "workstream_generation": workstream.generation,
                    "workstream_revision": workstream.revision,
                    "curator_thread_id": replacement.curator.thread_id,
                    "requested_action": requested_action,
                    "action_sha256": _sha256(requested_action),
                }
                owner_attestation = dict(owner_attestation_raw)
                if (
                    owner_attestation.get("schema")
                    != OWNER_ACTION_ATTESTATION_SCHEMA
                    or self.owner_action_verifier(
                        expected_attestation, owner_attestation
                    )
                    is not True
                ):
                    raise SupervisorCommandError(
                        "HumanGate recovery lacks a valid exact-curator action attestation"
                    )
                owner_attestation_digest = _sha256(
                    json.dumps(
                        owner_attestation,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                )
                owner_material = True
            elif owner_attestation_raw is not None:
                raise SupervisorCommandError(
                    "owner_action_attestation is allowed only for a HumanGate trigger"
                )
            resolved_attention_event_id: str | None = None
            if human_gate:
                resolved_attention_event_id = _machine(
                    "attention_event_id",
                    trigger_payload.get("attention_event_id"),
                )
            elif isinstance(state_raw, Mapping):
                attention_id = _event_id(
                    "serious-stall",
                    prior_state.incident_case_id or prior_state.fingerprint,
                )
                resolved_attention_event_id = _event_id(
                    "curator-serious-stall", attention_id
                )
            if resolved_attention_event_id is not None:
                attention_record = next(
                    (
                        item
                        for item in self.registry.list_outbox_records(
                            kinds=("curator_attention",)
                        )
                        if item["event_id"] == resolved_attention_event_id
                    ),
                    None,
                )
                expected_kind = "human_gate" if human_gate else "serious_stall"
                if (
                    attention_record is None
                    or attention_record.get("task_id") != task_id
                    or attention_record.get("payload", {}).get("workstream_id")
                    != workstream_id
                    or attention_record.get("payload", {}).get("kind")
                    != expected_kind
                ):
                    raise SupervisorCommandError(
                        "corrective recovery lacks its exact durable attention binding"
                    )
            if not (
                passport_material
                or strategy_material
                or evidence_material
                or owner_material
            ):
                raise SupervisorCommandError(
                    "new retry budget requires a material Passport, strategy or causal-evidence change"
                )
            new_context = IncidentContext(
                passport_revision=replacement.revision,
                strategy_digest=strategy_digest,
                causal_evidence_digest=causal_evidence_digest,
                verified_checkpoint_id=str(checkpoint_event["event_id"]),
            )
            renewed = renew_incident_budget(
                prior_state,
                new_fingerprint=fingerprint,
                new_context=new_context,
                justification=justification,
            )
            renewed = replace(
                renewed,
                current_executor_generation=coordinates[
                    "expected_executor_generation"
                ],
                successor_generation=coordinates[
                    "expected_executor_generation"
                ]
                + 1,
            )
            causal_binding = {
                "schema": CAUSAL_BINDING_SCHEMA,
                "stage": "corrective_recovery",
                "check_kind": "checkpoint_contract",
                "error_code": "parked_recovery",
                "normalized_cause_code": "material_corrective_generation",
                "fingerprint": fingerprint,
            }
            followup_message_id = _event_id(
                "corrective-followup-message", message_id
            )
            original_followup = {
                "schema": FOLLOWUP_SCHEMA,
                "task_id": task_id,
                "task_revision": replacement.revision,
                "workstream_id": workstream_id,
                "workstream_revision": corrective.revision,
                "executor_generation": executor.executor_generation,
                "thread_id": executor.thread_id,
                "host_id": executor.host_id,
                "model": executor.model,
                "reasoning": executor.reasoning,
                "prompt": prompt,
                "output_contract": "checkpoint",
                "cwd": str(cwd),
                "terminal_context": None,
                "causal_fingerprint": fingerprint,
                "causal_binding": causal_binding,
                "call_intent": None,
                "call_policy": CALL_POLICY_STANDARD,
                "model_attempt_count": 0,
                "message_id": followup_message_id,
            }
            successor_event_id = _event_id(
                "codex-corrective-successor", trigger_event_id + "|" + message_id
            )
            successor_payload = {
                "schema": SUCCESSOR_SCHEMA,
                "task_id": task_id,
                "task_revision": replacement.revision,
                "workstream_id": workstream_id,
                "workstream_revision": corrective.revision,
                "predecessor_generation": executor.executor_generation,
                "successor_generation": executor.executor_generation + 1,
                "causal_fingerprint": fingerprint,
                "causal_binding": causal_binding,
                "cwd": str(cwd),
                "verified_checkpoint_id": str(checkpoint_event["event_id"]),
                "verified_checkpoint_digest": checkpoint_digest,
                "verified_checkpoint": checkpoint_contract,
                "original_followup": original_followup,
                "started_thread": None,
                "start_intent": None,
                "proof_intent": None,
                "proof_contract": None,
            }
            recovery_event_id = _event_id(
                "corrective-generation", trigger_event_id + "|" + message_id
            )
            recovery_event_payload = {
                "schema": "dev-control-plane/incident-state-event/v2",
                "revision": replacement.revision,
                "status": "corrective_generation_applied",
                "fingerprint": fingerprint,
                "summary": "Применена материально изменённая corrective generation.",
                "decision": "start_successor_executor",
                "attempt": 0,
                "error_code": "none",
                "incident_state": _incident_state_to_dict(renewed),
                "material_change": {
                    "passport": passport_material,
                    "strategy": strategy_material,
                    "causal_evidence": evidence_material,
                    "owner_action": owner_material,
                },
                "justification_digest": _sha256(justification),
                "owner_action_attestation_digest": owner_attestation_digest,
                "resolved_attention_event_id": resolved_attention_event_id,
                "updated_at": _iso(self.clock()),
            }
            sanitized_input = dict(payload)
            sanitized_input["owner_action_attestation"] = (
                None
                if owner_attestation_digest is None
                else {
                    "schema": OWNER_ACTION_ATTESTATION_SCHEMA,
                    "digest": owner_attestation_digest,
                }
            )
            result = self.registry.apply_corrective_generation(
                replacement,
                corrective,
                expected_task_revision=coordinates["expected_task_revision"],
                expected_workstream_generation=coordinates[
                    "expected_workstream_generation"
                ],
                expected_workstream_revision=coordinates[
                    "expected_workstream_revision"
                ],
                expected_executor_generation=coordinates[
                    "expected_executor_generation"
                ],
                trigger_event_id=trigger_event_id,
                trigger_event_digest=trigger_event_digest,
                verified_checkpoint_id=str(checkpoint_event["event_id"]),
                verified_checkpoint_digest=checkpoint_digest,
                canonical_workspace=str(cwd),
                message_id=message_id,
                source="private-unix-command:apply-corrective-generation",
                input_payload=sanitized_input,
                recovery_event_id=recovery_event_id,
                recovery_event_payload=recovery_event_payload,
                successor_event_id=successor_event_id,
                successor_payload=successor_payload,
                projection_event_id=_event_id("dirty", recovery_event_id),
                fence=self.engine.fence,
            )
        return result

    def _command_apply_preactivation_structural_repair(
        self, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Reserve the exact PR91 zero-turn structural successor.

        The command intentionally cannot parse the stored legacy Passport.
        Only the replacement contracts are parsed; the registry independently
        proves the exact legacy aggregate and zero-call invariants inside the
        fenced transaction.
        """

        if not self.preactivation_repair_mode:
            raise SupervisorCommandError(
                "preactivation structural repair requires explicit startup mode"
            )
        required = {
            "task_id",
            "expected_task_revision",
            "workstream_id",
            "expected_workstream_generation",
            "expected_workstream_revision",
            "expected_executor_generation",
            "replacement_passport",
            "corrective_workstream",
            "cwd",
            "expected_pr_head_sha",
            "justification",
            "message_id",
        }
        _exact_fields(payload, required, "preactivation structural repair payload")
        task_id = _machine("task_id", payload.get("task_id"))
        workstream_id = _machine("workstream_id", payload.get("workstream_id"))
        message_id = _machine("message_id", payload.get("message_id"))
        if (
            task_id != PREACTIVATION_STRUCTURAL_REPAIR_TASK_ID
            or workstream_id != PREACTIVATION_STRUCTURAL_REPAIR_WORKSTREAM_ID
        ):
            raise SupervisorCommandError(
                "preactivation structural repair is bound only to the PR91 pilot"
            )
        coordinates: dict[str, int] = {}
        for name in (
            "expected_task_revision",
            "expected_workstream_generation",
            "expected_workstream_revision",
            "expected_executor_generation",
        ):
            value = payload.get(name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise SupervisorCommandError(f"{name} must be positive")
            coordinates[name] = value
        if coordinates != {
            "expected_task_revision": 2,
            "expected_workstream_generation": 1,
            "expected_workstream_revision": 2,
            "expected_executor_generation": 1,
        }:
            raise SupervisorCommandError(
                "preactivation structural repair CAS is not exact PR91"
            )
        expected_pr_head_sha = payload.get("expected_pr_head_sha")
        if (
            not isinstance(expected_pr_head_sha, str)
            or not re.fullmatch(r"[0-9a-f]{40}", expected_pr_head_sha)
        ):
            raise SupervisorCommandError(
                "preactivation replacement head must be an exact Git SHA"
            )
        justification = payload.get("justification")
        if (
            not isinstance(justification, str)
            or not justification.strip()
            or len(justification) > 2_000
            or "\n" in justification
            or _CREDENTIAL_RE.search(justification)
        ):
            raise SupervisorCommandError(
                "preactivation repair justification must be one sanitized line"
            )
        justification = justification.strip()
        replacement_raw = dict(_mapping(payload, "replacement_passport"))
        corrective_raw = dict(_mapping(payload, "corrective_workstream"))
        replacement = task_passport_from_mapping(replacement_raw)
        corrective = workstream_from_mapping(corrective_raw)
        if (
            replacement.task_id != task_id
            or replacement.revision
            != coordinates["expected_task_revision"] + 1
            or replacement.executor is not None
            or corrective.task_id != task_id
            or corrective.workstream_id != workstream_id
            or corrective.generation
            != coordinates["expected_workstream_generation"] + 1
            or corrective.corrective_of_generation
            != coordinates["expected_workstream_generation"]
            or corrective.revision != 1
            or corrective.state != "recovering"
            or corrective.executor is not None
        ):
            raise SupervisorCommandError(
                "preactivation replacement contracts are not the exact successor"
            )
        try:
            require_passport_action(replacement, "codex_workspace_mutation")
        except Exception as exc:
            raise SupervisorCommandError(
                "preactivation replacement lacks Codex workspace authorization"
            ) from exc
        cwd = self._workspace(payload.get("cwd"))
        if self.activation_identity is None:
            raise SupervisorCommandError(
                "preactivation repair requires an immutable activation identity"
            )
        activation_release_sha = str(self.activation_identity["release_sha"])
        if activation_release_sha == PREACTIVATION_STRUCTURAL_REPAIR_PREDECESSOR_SHA:
            raise SupervisorCommandError(
                "preactivation repair cannot reuse the failed PR91 release"
            )
        qualification = [
            item
            for item in replacement.resources
            if item.startswith("qualification:")
        ]
        if qualification != [f"qualification:{activation_release_sha}"]:
            raise SupervisorCommandError(
                "preactivation replacement qualification differs from activation"
            )
        manifest = replacement.release_manifest
        if (
            manifest is None
            or not manifest.pr_identities
            or manifest.pr_identities[-1]
            != (
                "github-pr-v1:orenvlad-ai/dev-control-plane:92:"
                f"{expected_pr_head_sha}:{activation_release_sha}"
            )
        ):
            raise SupervisorCommandError(
                "preactivation replacement manifest lacks exact PR92 identity"
            )
        passport_digest = contract_digest(replacement)
        workstream_digest = contract_digest(corrective)
        repair_event_id = _event_id(
            "preactivation-structural-repair",
            message_id + "|" + activation_release_sha,
        )
        successor_event_id = _event_id(
            "codex-preactivation-successor", repair_event_id
        )
        completion_event_id = _event_id(
            "preactivation-structural-repair-completed", successor_event_id
        )
        backup_path = (
            self.registry.backup_dir
            / (
                "supervisor.preactivation-structural-repair."
                + _sha256(message_id)[:24]
                + ".sqlite3"
            )
        )
        with self._mutation_lock:
            repair_state = self.registry.preactivation_structural_repair_state()
            repair_status = str(repair_state.get("status") or "")
            if (
                repair_status != "awaiting_repair_command"
                and repair_state.get("repair_event_id") != repair_event_id
            ):
                raise SupervisorCommandError(
                    "preactivation repair is already bound to another message"
                )
            bounded_backups = tuple(
                sorted(
                    self.registry.backup_dir.glob(
                        "supervisor.preactivation-structural-repair.*.sqlite3"
                    )
                )
            )
            if repair_status == "awaiting_repair_command":
                if bounded_backups and bounded_backups != (backup_path,):
                    raise SupervisorCommandError(
                        "preactivation repair found an unbound prior backup"
                    )
                if not backup_path.exists():
                    self.registry.backup(backup_path)
            elif not backup_path.exists():
                raise SupervisorCommandError(
                    "preactivation repair lost its deterministic backup"
                )
            backup_sha256 = _private_file_sha256(
                backup_path,
                expected_parent=self.registry.backup_dir,
            )
            successor_payload = {
                "schema": PREACTIVATION_SUCCESSOR_SCHEMA,
                "task_id": task_id,
                "task_revision": replacement.revision,
                "workstream_id": workstream_id,
                "workstream_generation": corrective.generation,
                "workstream_revision": corrective.revision,
                "predecessor_generation": coordinates[
                    "expected_executor_generation"
                ],
                "successor_generation": coordinates[
                    "expected_executor_generation"
                ]
                + 1,
                "cwd": str(cwd),
                "activation_release_sha": activation_release_sha,
                "expected_pr_head_sha": expected_pr_head_sha,
                "repair_event_id": repair_event_id,
                "completion_event_id": completion_event_id,
                "replacement_passport_digest": passport_digest,
                "replacement_workstream_digest": workstream_digest,
                "start_intent": None,
                "started_thread": None,
            }
            result = self.registry.apply_preactivation_structural_repair(
                replacement,
                corrective,
                expected_task_revision=coordinates["expected_task_revision"],
                expected_workstream_generation=coordinates[
                    "expected_workstream_generation"
                ],
                expected_workstream_revision=coordinates[
                    "expected_workstream_revision"
                ],
                expected_executor_generation=coordinates[
                    "expected_executor_generation"
                ],
                canonical_workspace=str(cwd),
                activation_release_sha=activation_release_sha,
                expected_pr_head_sha=expected_pr_head_sha,
                backup_path=str(backup_path),
                backup_sha256=backup_sha256,
                justification_digest=_sha256(justification),
                message_id=message_id,
                source="private-unix-command:preactivation-structural-repair",
                input_payload={
                    **dict(payload),
                    "justification": _sha256(justification),
                },
                repair_event_id=repair_event_id,
                successor_event_id=successor_event_id,
                completion_event_id=completion_event_id,
                successor_payload=successor_payload,
                projection_event_id=_event_id("dirty", repair_event_id),
                fence=self.engine.fence,
            )
        return result

    def _command_apply_preactivation_causal_remediation(
        self, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Reserve the sole PR93 causal read and one corrective successor."""

        if not self.preactivation_causal_remediation_mode:
            raise SupervisorCommandError(
                "preactivation causal remediation requires explicit startup mode"
            )
        required = {
            "task_id",
            "expected_task_revision",
            "workstream_id",
            "expected_workstream_generation",
            "expected_workstream_revision",
            "expected_executor_generation",
            "replacement_passport",
            "corrective_workstream",
            "cwd",
            "expected_pr_head_sha",
            "strategy_digest",
            "justification",
            "message_id",
        }
        _exact_fields(
            payload, required, "preactivation causal remediation payload"
        )
        task_id = _machine("task_id", payload.get("task_id"))
        workstream_id = _machine("workstream_id", payload.get("workstream_id"))
        message_id = _machine("message_id", payload.get("message_id"))
        if (
            task_id != PREACTIVATION_STRUCTURAL_REPAIR_TASK_ID
            or workstream_id != PREACTIVATION_STRUCTURAL_REPAIR_WORKSTREAM_ID
        ):
            raise SupervisorCommandError(
                "preactivation causal remediation is bound only to the PR92 pilot"
            )
        coordinates: dict[str, int] = {}
        for name in (
            "expected_task_revision",
            "expected_workstream_generation",
            "expected_workstream_revision",
            "expected_executor_generation",
        ):
            value = payload.get(name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise SupervisorCommandError(f"{name} must be positive")
            coordinates[name] = value
        if coordinates != {
            "expected_task_revision": (
                PREACTIVATION_CAUSAL_REMEDIATION_SOURCE_TASK_REVISION
            ),
            "expected_workstream_generation": (
                PREACTIVATION_CAUSAL_REMEDIATION_SOURCE_WORKSTREAM_GENERATION
            ),
            "expected_workstream_revision": (
                PREACTIVATION_CAUSAL_REMEDIATION_SOURCE_WORKSTREAM_REVISION
            ),
            "expected_executor_generation": (
                PREACTIVATION_CAUSAL_REMEDIATION_SOURCE_EXECUTOR_GENERATION
            ),
        }:
            raise SupervisorCommandError(
                "preactivation causal remediation CAS is not exact failed PR92"
            )
        expected_pr_head_sha = payload.get("expected_pr_head_sha")
        if (
            not isinstance(expected_pr_head_sha, str)
            or not re.fullmatch(r"[0-9a-f]{40}", expected_pr_head_sha)
            or expected_pr_head_sha
            == PREACTIVATION_CAUSAL_REMEDIATION_PR92_HEAD_SHA
        ):
            raise SupervisorCommandError(
                "preactivation causal remediation requires a distinct exact PR93 head"
            )
        strategy_digest = _digest_value(
            "strategy_digest", payload.get("strategy_digest")
        )
        if strategy_digest != _sha256(PREACTIVATION_CAUSAL_STRATEGY_RESOURCE):
            raise SupervisorCommandError(
                "preactivation causal remediation strategy digest is not exact"
            )
        if (
            PREACTIVATION_CAUSAL_STRATEGY_RESOURCE
            != PREACTIVATION_CAUSAL_REMEDIATION_STRATEGY_RESOURCE
        ):
            raise SupervisorRuntimeError(
                "preactivation causal strategy catalog mismatch"
            )
        justification = payload.get("justification")
        if (
            not isinstance(justification, str)
            or not justification.strip()
            or len(justification) > 2_000
            or "\n" in justification
            or _CREDENTIAL_RE.search(justification)
        ):
            raise SupervisorCommandError(
                "preactivation causal remediation justification must be one sanitized line"
            )
        justification = justification.strip()
        replacement = task_passport_from_mapping(
            dict(_mapping(payload, "replacement_passport"))
        )
        corrective = workstream_from_mapping(
            dict(_mapping(payload, "corrective_workstream"))
        )
        if (
            replacement.task_id != task_id
            or replacement.revision
            != PREACTIVATION_CAUSAL_REMEDIATION_SUCCESSOR_TASK_REVISION
            or replacement.executor is not None
            or corrective.task_id != task_id
            or corrective.workstream_id != workstream_id
            or corrective.generation
            != PREACTIVATION_CAUSAL_REMEDIATION_SUCCESSOR_WORKSTREAM_GENERATION
            or corrective.corrective_of_generation
            != PREACTIVATION_CAUSAL_REMEDIATION_SOURCE_WORKSTREAM_GENERATION
            or corrective.revision != 1
            or corrective.state != "recovering"
            or corrective.executor is not None
        ):
            raise SupervisorCommandError(
                "preactivation causal replacement contracts are not the exact successor"
            )
        try:
            require_passport_action(replacement, "codex_workspace_mutation")
        except Exception as exc:
            raise SupervisorCommandError(
                "preactivation causal replacement lacks Codex workspace authorization"
            ) from exc
        cwd = self._workspace(payload.get("cwd"))
        if self.activation_identity is None:
            raise SupervisorCommandError(
                "preactivation causal remediation requires an immutable activation identity"
            )
        activation_release_sha = str(self.activation_identity["release_sha"])
        if activation_release_sha in {
            PREACTIVATION_STRUCTURAL_REPAIR_PREDECESSOR_SHA,
            PREACTIVATION_CAUSAL_REMEDIATION_PR92_MERGE_SHA,
        }:
            raise SupervisorCommandError(
                "preactivation causal remediation cannot reuse a prior release"
            )
        qualification = sorted(
            item
            for item in replacement.resources
            if item.startswith("qualification:")
        )
        if qualification != [f"qualification:{activation_release_sha}"]:
            raise SupervisorCommandError(
                "preactivation causal qualification differs from activation"
            )
        if (
            replacement.resources.count(PREACTIVATION_CAUSAL_STRATEGY_RESOURCE)
            != 1
            or corrective.resources.count(PREACTIVATION_CAUSAL_STRATEGY_RESOURCE)
            != 1
            or set(corrective.resources) != set(replacement.resources)
        ):
            raise SupervisorCommandError(
                "preactivation causal replacement lacks its exact material strategy"
            )
        manifest = replacement.release_manifest
        if (
            manifest is None
            or len(manifest.pr_identities) != 3
            or len(manifest.deploy_identities) != 3
            or manifest.pr_identities[-1]
            != (
                "github-pr-v1:orenvlad-ai/dev-control-plane:93:"
                f"{expected_pr_head_sha}:{activation_release_sha}"
            )
            or manifest.deploy_identities[-1]
            != (
                "hosted-release-v1:wb-core-eu-root:devcontrol.pro:"
                f"{activation_release_sha}"
            )
        ):
            raise SupervisorCommandError(
                "preactivation causal replacement manifest lacks exact PR93 identity"
            )

        remediation_event_id = _event_id(
            "preactivation-causal-remediation",
            message_id + "|" + activation_release_sha,
        )
        causal_read_event_id = _event_id(
            "codex-preactivation-causal-read", remediation_event_id
        )
        causal_attestation_event_id = _event_id(
            "preactivation-causal-attestation", causal_read_event_id
        )
        successor_event_id = _event_id(
            "codex-preactivation-causal-successor",
            causal_attestation_event_id,
        )
        completion_event_id = _event_id(
            "preactivation-causal-remediation-completed", successor_event_id
        )
        backup_path = self.registry.preactivation_causal_remediation_backup_path()
        with self._mutation_lock:
            remediation_state = (
                self.registry.preactivation_causal_remediation_state()
            )
            status = str(remediation_state.get("status") or "")
            bound_event_id = remediation_state.get("remediation_event_id")
            if (
                status != "awaiting_remediation_command"
                and bound_event_id != remediation_event_id
            ):
                raise SupervisorCommandError(
                    "preactivation causal remediation is already bound to another message"
                )
            if not backup_path.exists():
                self.registry.backup(backup_path)
            backup_sha256 = _private_file_sha256(
                backup_path,
                expected_parent=self.registry.backup_dir,
            )
            result = self.registry.reserve_preactivation_causal_remediation(
                replacement,
                corrective,
                expected_task_revision=coordinates["expected_task_revision"],
                expected_workstream_generation=coordinates[
                    "expected_workstream_generation"
                ],
                expected_workstream_revision=coordinates[
                    "expected_workstream_revision"
                ],
                expected_executor_generation=coordinates[
                    "expected_executor_generation"
                ],
                canonical_workspace=str(cwd),
                activation_release_sha=activation_release_sha,
                expected_pr_head_sha=expected_pr_head_sha,
                backup_path=str(backup_path),
                backup_sha256=backup_sha256,
                strategy_digest=strategy_digest,
                justification_digest=_sha256(justification),
                message_id=message_id,
                source="private-unix-command:preactivation-causal-remediation",
                input_payload={
                    **dict(payload),
                    "justification": _sha256(justification),
                },
                remediation_event_id=remediation_event_id,
                causal_read_event_id=causal_read_event_id,
                causal_attestation_event_id=causal_attestation_event_id,
                successor_event_id=successor_event_id,
                completion_event_id=completion_event_id,
                projection_event_id=_event_id("dirty", remediation_event_id),
                fence=self.engine.fence,
            )
        return result

    def _command_preactivation_causal_remediation_state(
        self, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        _exact_fields(
            payload, set(), "preactivation causal remediation state payload"
        )
        state = self.registry.preactivation_causal_remediation_state()
        return {
            **state,
            "startup_mode": self.preactivation_causal_remediation_mode,
            "same_process_completion": self._preactivation_repair_complete.is_set(),
            "worker_failure_code": self._preactivation_repair_failure_code or "",
            "http_ready": False
            if not self._preactivation_repair_complete.is_set()
            else self.readiness()["ready"],
        }

    def _command_preactivation_repair_state(
        self, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        _exact_fields(payload, set(), "preactivation repair state payload")
        state = self.registry.preactivation_structural_repair_state()
        return {
            **state,
            "startup_mode": self.preactivation_repair_mode,
            "same_process_completion": self._preactivation_repair_complete.is_set(),
            "worker_failure_code": self._preactivation_repair_failure_code or "",
            "http_ready": False
            if not self._preactivation_repair_complete.is_set()
            else self.readiness()["ready"],
        }

    def _command_followup(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        _exact_fields(
            payload,
            {
                "task_id", "workstream_id", "prompt", "output_contract", "cwd",
                "terminal_context", "call_policy", "message_id",
            },
            "Codex follow-up payload",
        )
        task_id = _machine("task_id", payload.get("task_id"))
        workstream_id = _machine("workstream_id", payload.get("workstream_id"))
        prompt = _prompt(payload.get("prompt"))
        output_contract = payload.get("output_contract")
        if output_contract not in {"checkpoint", "terminal"}:
            raise SupervisorCommandError("output_contract must be checkpoint or terminal")
        call_policy = payload.get("call_policy")
        if call_policy not in {CALL_POLICY_STANDARD, CALL_POLICY_SINGLE_ATTEMPT_CANARY}:
            raise SupervisorCommandError("call_policy must be standard or single_attempt_canary")
        if call_policy == CALL_POLICY_SINGLE_ATTEMPT_CANARY and output_contract != "checkpoint":
            raise SupervisorCommandError("single_attempt_canary requires a checkpoint output contract")
        if (
            self._preactivation_qualification_mode
            and self._preactivation_repair_complete.is_set()
            and not self._preactivation_canary_complete.is_set()
        ):
            if self._preactivation_repair_failure_code:
                raise SupervisorCommandError(
                    "preactivation qualification is fail-closed"
                )
            if not self._preactivation_release_admission_complete.is_set():
                raise SupervisorCommandError(
                    "preactivation canary requires durable proof-only admission"
                )
            if (
                task_id != PREACTIVATION_STRUCTURAL_REPAIR_TASK_ID
                or workstream_id
                != PREACTIVATION_STRUCTURAL_REPAIR_WORKSTREAM_ID
                or call_policy != CALL_POLICY_SINGLE_ATTEMPT_CANARY
                or output_contract != "checkpoint"
                or payload.get("terminal_context") is not None
            ):
                raise SupervisorCommandError(
                    "preactivation mode permits only the exact single checkpoint canary"
                )
        cwd = self._workspace(payload.get("cwd"))
        terminal_context = self._terminal_context(payload.get("terminal_context"), required=output_contract == "terminal")
        message_id = _machine("message_id", payload.get("message_id"))
        with self._mutation_lock:
            task = self.registry.get_task(task_id)
            workstream = self.registry.get_workstream(workstream_id)
            executor = self.registry.current_executor(task_id, workstream_id)
            if task is None or workstream is None or workstream.task_id != task_id or executor is None:
                raise SupervisorCommandError("follow-up binding is unknown")
            try:
                self._assert_workspace_binding(task_id, workstream_id, cwd)
            except SupervisorRuntimeError as exc:
                raise SupervisorCommandError(
                    "follow-up cwd differs from the immutable executor workspace"
                ) from exc
            passport = task_passport_from_mapping(task.passport)
            try:
                require_passport_action(passport, "codex_workspace_mutation")
            except Exception as exc:
                raise SupervisorCommandError(
                    "Passport does not authorize a Codex workspace mutation"
                ) from exc
            if self.preactivation_causal_remediation_mode:
                workstream_contract = workstream_from_mapping(workstream.contract)
                activation_release_sha = (
                    self.activation_identity.get("release_sha")
                    if isinstance(self.activation_identity, Mapping)
                    else None
                )
                qualification_resources = sorted(
                    item
                    for item in passport.resources
                    if item.startswith("qualification:")
                )
                if (
                    task.revision
                    != PREACTIVATION_CAUSAL_REMEDIATION_SUCCESSOR_TASK_REVISION
                    or workstream.generation
                    != PREACTIVATION_CAUSAL_REMEDIATION_SUCCESSOR_WORKSTREAM_GENERATION
                    or workstream.revision != 2
                    or executor.executor_generation
                    != PREACTIVATION_CAUSAL_REMEDIATION_SUCCESSOR_EXECUTOR_GENERATION
                    or qualification_resources
                    != [f"qualification:{activation_release_sha}"]
                    or PREACTIVATION_CAUSAL_STRATEGY_RESOURCE
                    not in passport.resources
                    or set(workstream_contract.resources)
                    != set(passport.resources)
                ):
                    raise SupervisorCommandError(
                        "preactivation causal canary binding is not exact PR93"
                    )
            event_id = _event_id("codex-followup", message_id)
            outbox_payload = {
                "schema": FOLLOWUP_SCHEMA,
                "task_id": task_id,
                "task_revision": task.revision,
                "workstream_id": workstream_id,
                "workstream_revision": workstream.revision,
                "executor_generation": executor.executor_generation,
                "thread_id": executor.thread_id,
                "host_id": executor.host_id,
                "model": executor.model,
                "reasoning": executor.reasoning,
                "prompt": prompt,
                "output_contract": output_contract,
                "cwd": str(cwd),
                "terminal_context": terminal_context,
                "causal_fingerprint": None,
                "causal_binding": None,
                "call_intent": None,
                "call_policy": call_policy,
                "model_attempt_count": 0,
                "message_id": message_id,
            }
            if call_policy == CALL_POLICY_SINGLE_ATTEMPT_CANARY:
                self._assert_canary_intake_budget(event_id, outbox_payload)
            created = self.registry.accept_inbox_and_enqueue(
                message_id=message_id,
                source="private-unix-command:codex-followup",
                inbox_payload=dict(outbox_payload),
                outbox_event_id=event_id,
                outbox_kind="codex_followup",
                outbox_payload=outbox_payload,
                fence=self.engine.fence,
                task_id=task_id,
            )
        return {"queued": created, "event_id": event_id, "task_id": task_id, "workstream_id": workstream_id}

    def _assert_canary_intake_budget(
        self,
        event_id: str,
        payload: Mapping[str, Any],
    ) -> None:
        conflicting = [
            record
            for record in self._canary_scope_records(payload)
            if record.get("event_id") != event_id
        ]
        if conflicting:
            raise SupervisorCommandError(
                "single_attempt_canary budget is already reserved for this task revision"
            )

    def _assert_canary_worker_budget(
        self,
        message: OutboxMessage,
        payload: Mapping[str, Any],
    ) -> None:
        records = self._canary_scope_records(payload)
        current = next(
            (record for record in records if record.get("event_id") == message.event_id),
            None,
        )
        if current is None:
            raise SupervisorRuntimeError(
                "single-attempt canary is absent from its durable budget scope"
            )
        owner = min(
            records,
            key=lambda record: (
                float(record.get("created_at") or 0),
                str(record.get("event_id") or ""),
            ),
        )
        if owner.get("event_id") != message.event_id:
            raise SupervisorRuntimeError(
                "single-attempt canary budget is owned by an earlier durable request"
            )
        for record in records:
            record_event_id = record.get("event_id")
            if not isinstance(record_event_id, str) or record_event_id == message.event_id:
                continue
            record_payload = record.get("payload")
            if (
                isinstance(record_payload, Mapping)
                and (
                    int(record_payload.get("model_attempt_count") or 0) > 0
                    or record_payload.get("call_intent") is not None
                )
            ) or self.registry.get_event(
                _event_id("qualification-canary-failed", record_event_id)
            ) is not None:
                raise SupervisorRuntimeError(
                    "single-attempt canary budget was consumed by another durable request"
                )

    def _canary_scope_records(
        self,
        payload: Mapping[str, Any],
    ) -> tuple[Mapping[str, Any], ...]:
        scope_fields = (
            "task_id",
            "task_revision",
            "workstream_id",
            "workstream_revision",
            "executor_generation",
        )
        return tuple(
            record
            for record in self.registry.list_outbox_records(kinds=("codex_followup",))
            if isinstance(record.get("payload"), Mapping)
            and record["payload"].get("call_policy")
            == CALL_POLICY_SINGLE_ATTEMPT_CANARY
            and all(
                record["payload"].get(field) == payload.get(field)
                for field in scope_fields
            )
        )

    def _command_prepare_attention(self, payload: Mapping[str, Any]) -> dict[str, Any] | None:
        _exact_fields(payload, {"visibility_timeout"}, "prepare attention payload")
        visibility = payload.get("visibility_timeout")
        if isinstance(visibility, bool) or not isinstance(visibility, (int, float)) or not 5 <= float(visibility) <= 900:
            raise SupervisorCommandError("attention visibility timeout is out of bounds")
        delivery = CuratorDelivery(self.registry, self.engine.fence)
        # A release-terminal attention is immutable.  Do not let it leave the
        # durable queue before the asynchronous target lane actuator has an
        # exact completed readback.  Deferred terminal rows are nacked briefly
        # so a later HumanGate/serious-stall attention is not starved.
        limit = len(
            self.registry.list_outbox_records(
                kinds=("curator_attention",), states=("pending",)
            )
        )
        for _ in range(max(1, limit)):
            with self._mutation_lock:
                prepared = delivery.prepare_one(visibility_timeout=float(visibility))
                if prepared is None:
                    return None
                if (
                    prepared.kind != "terminal"
                    or self._target_lane_ready_for_attention(
                        prepared.task_id,
                        self.registry.get_task(prepared.task_id).revision
                        if self.registry.get_task(prepared.task_id) is not None
                        else -1,
                    )
                ):
                    result = asdict(prepared)
                    self._prepared_attention_claims[prepared.event_id] = dict(result)
                    return result
                self.registry.nack_outbox(
                    prepared.event_id,
                    prepared.claim_token,
                    self.engine.fence,
                    retry_at=self.clock() + max(5.0, self.retry_delay_seconds),
                    sanitized_error="target_lane_closure_pending",
                )
        return None

    def _target_lane_ready_for_attention(self, task_id: str, task_revision: int) -> bool:
        task = self.registry.get_task(task_id)
        if task is None or task.revision != task_revision:
            return False
        passport = task_passport_from_mapping(task.passport)
        if not passport.contour.startswith("release:"):
            return True
        outstanding = tuple(
            item
            for item in self.registry.list_outbox_records(
                kinds=("target_lane_closure",), states=("pending", "inflight")
            )
            if item.get("task_id") == task_id
        )
        if outstanding:
            return False
        matches = []
        for event in self.registry.list_events(
            task_id=task_id,
            event_types=("target_lane_closure_completed",),
        ):
            payload = event.get("payload")
            action = payload.get("action") if isinstance(payload, Mapping) else None
            receipt = payload.get("receipt") if isinstance(payload, Mapping) else None
            if (
                isinstance(action, Mapping)
                and isinstance(receipt, Mapping)
                and action.get("task_id") == task_id
                and action.get("task_revision") == task_revision
                and receipt.get("closure_id") == action.get("closure_id")
                and receipt.get("status") in {"released", "parked"}
            ):
                matches.append(event)
        return len(matches) == 1

    def _command_ack_attention(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        _exact_fields(
            payload,
            {"event_id", "attention_id", "curator_thread_id", "payload_digest", "claim_token"},
            "attention ACK",
        )
        receipt = DeliveryReceipt(
            event_id=_machine("event_id", payload.get("event_id")),
            attention_id=_machine("attention_id", payload.get("attention_id")),
            curator_thread_id=_machine("curator_thread_id", payload.get("curator_thread_id")),
            payload_digest=_digest_value("payload_digest", payload.get("payload_digest")),
            claim_token=_claim_token(payload.get("claim_token")),
        )
        with self._mutation_lock:
            summary = next(
                (item for item in self.registry.list_outbox_summaries(kinds=("curator_attention",)) if item["event_id"] == receipt.event_id),
                None,
            )
            if summary is not None and summary["state"] == "delivered":
                try:
                    self.registry.receipt_prior_generation_curator_attention(
                        event_id=receipt.event_id,
                        claim_token=receipt.claim_token,
                        attention_id=receipt.attention_id,
                        curator_thread_id=receipt.curator_thread_id,
                        payload_digest=receipt.payload_digest,
                        fence=self.engine.fence,
                    )
                except (RegistryValidationError, StaleGenerationError) as exc:
                    raise SupervisorCommandError(
                        "attention ACK is not bound to the delivered durable payload"
                    ) from exc
                return {"delivered": True, "idempotent": True, "event_id": receipt.event_id}
            prepared = self._prepared_attention_claims.get(receipt.event_id)
            if prepared is None:
                try:
                    self.registry.receipt_prior_generation_curator_attention(
                        event_id=receipt.event_id,
                        claim_token=receipt.claim_token,
                        attention_id=receipt.attention_id,
                        curator_thread_id=receipt.curator_thread_id,
                        payload_digest=receipt.payload_digest,
                        fence=self.engine.fence,
                    )
                except (RegistryValidationError, StaleGenerationError) as exc:
                    raise SupervisorCommandError(
                        "attention ACK is not bound to the prepared durable payload"
                    ) from exc
                return {
                    "delivered": True,
                    "idempotent": False,
                    "event_id": receipt.event_id,
                    "prior_generation_receipt": True,
                }
            if (
                prepared.get("claim_token") != receipt.claim_token
                or prepared.get("attention_id") != receipt.attention_id
                or prepared.get("curator_thread_id") != receipt.curator_thread_id
                or prepared.get("payload_digest") != receipt.payload_digest
            ):
                raise SupervisorCommandError("attention ACK is not bound to the prepared durable payload")
            CuratorDelivery(self.registry, self.engine.fence).ack(receipt)
            self._prepared_attention_claims.pop(receipt.event_id, None)
        return {"delivered": True, "idempotent": False, "event_id": receipt.event_id}

    def _command_nack_attention(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        _exact_fields(
            payload,
            {
                "event_id", "attention_id", "curator_thread_id", "payload_digest", "claim_token",
                "retry_at", "reason_code",
            },
            "attention NACK",
        )
        receipt = DeliveryReceipt(
            event_id=_machine("event_id", payload.get("event_id")),
            attention_id=_machine("attention_id", payload.get("attention_id")),
            curator_thread_id=_machine("curator_thread_id", payload.get("curator_thread_id")),
            payload_digest=_digest_value("payload_digest", payload.get("payload_digest")),
            claim_token=_claim_token(payload.get("claim_token")),
        )
        retry_at = payload.get("retry_at")
        if isinstance(retry_at, bool) or not isinstance(retry_at, (int, float)):
            raise SupervisorCommandError("retry_at must be a timestamp")
        if float(retry_at) <= self.clock():
            raise SupervisorCommandError("retry_at must be in the future")
        with self._mutation_lock:
            prepared = self._prepared_attention_claims.get(receipt.event_id)
            reason_code = _machine("reason_code", payload.get("reason_code"))
            if prepared is None:
                try:
                    self.registry.receipt_prior_generation_curator_attention(
                        event_id=receipt.event_id,
                        claim_token=receipt.claim_token,
                        attention_id=receipt.attention_id,
                        curator_thread_id=receipt.curator_thread_id,
                        payload_digest=receipt.payload_digest,
                        fence=self.engine.fence,
                        retry_at=float(retry_at),
                        sanitized_error=reason_code,
                    )
                except (RegistryValidationError, StaleGenerationError) as exc:
                    raise SupervisorCommandError(
                        "attention NACK is not bound to the prepared durable payload"
                    ) from exc
                return {
                    "pending": True,
                    "event_id": receipt.event_id,
                    "prior_generation_receipt": True,
                }
            if (
                prepared.get("claim_token") != receipt.claim_token
                or prepared.get("attention_id") != receipt.attention_id
                or prepared.get("curator_thread_id") != receipt.curator_thread_id
                or prepared.get("payload_digest") != receipt.payload_digest
            ):
                raise SupervisorCommandError("attention NACK is not bound to the prepared durable payload")
            CuratorDelivery(self.registry, self.engine.fence).nack(
                receipt,
                retry_at=float(retry_at),
                reason_code=reason_code,
            )
            self._prepared_attention_claims.pop(receipt.event_id, None)
        return {"pending": True, "event_id": receipt.event_id}

    def _command_human_gate(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        _exact_fields(payload, {"request", "message_id", "created_at"}, "HumanGate payload")
        request_raw = _mapping(payload, "request")
        _exact_fields(request_raw, set(HumanGateRequest.__dataclass_fields__), "HumanGate request")
        request = validate_human_gate(HumanGateRequest(**dict(request_raw)))
        message_id = _machine("message_id", payload.get("message_id"))
        created_at = _rfc3339(payload.get("created_at"))
        with self._mutation_lock:
            task = self.registry.get_task(request.task_id)
            workstream = self.registry.get_workstream(request.workstream_id)
            if task is None or workstream is None or workstream.task_id != request.task_id:
                raise SupervisorCommandError("HumanGate binding is unknown")
            passport = task_passport_from_mapping(task.passport)
            if request.reason_code not in passport.autonomy.human_gate_reasons:
                raise SupervisorCommandError("HumanGate reason is outside the Passport envelope")
            prerequisite = self._human_gate_prerequisite_event(request)
            active_siblings = tuple(
                item
                for item in self.registry.list_workstreams()
                if item.task_id == request.task_id
                and item.workstream_id != request.workstream_id
                and item.current
                and item.state not in {"technical_complete", "acceptance_pending", "accepted", "blocked", "parked"}
            )
            if active_siblings:
                raise SupervisorCommandError(
                    "HumanGate cannot interrupt independent safe workstreams"
                )
            event_id = _event_id("human-gate", request.gate_id)
            attention_event_id = _event_id("curator-human-gate", request.gate_id)
            action = request.requested_actions[0]
            handoff = (
                "Статус: Блокер\n"
                f"Задача: {passport.title}\n"
                f"Причина: {request.reason_code}\n"
                f"Доказательство: {request.evidence[0]}\n"
                f"Требуется одно действие: {action}"
            )
            attention = {
                "schema": "dev-control-plane/curator-attention/v2",
                "attention_id": request.gate_id,
                "task_id": request.task_id,
                "workstream_id": request.workstream_id,
                "curator_thread_id": passport.curator.thread_id,
                "kind": "human_gate",
                "handoff_ru": handoff,
                "required_action": action,
                "created_at": created_at,
            }
            event_payload = {
                "schema": "dev-control-plane/human-gate-event/v2",
                "revision": task.revision,
                "status": "human_gate",
                "fingerprint": _sha256(request.reason_code + "|" + action),
                "summary": "Доказан один human-exclusive blocker.",
                "decision": "park_workstream",
                "attempt": 1,
                "reason_code": request.reason_code,
                "requested_action": action,
                "attention_event_id": attention_event_id,
                "prerequisite_event_id": prerequisite["event_id"],
                "updated_at": created_at,
            }
            created = self.registry.record_input_event_outbox(
                message_id=message_id,
                source="private-unix-command:human-gate",
                input_payload={"request": dict(request_raw), "created_at": created_at},
                event_id=event_id,
                event_type="incident_policy",
                event_payload=event_payload,
                outbox_items=(
                    {
                        "event_id": attention_event_id,
                        "kind": "curator_attention",
                        "payload": attention,
                        "task_id": request.task_id,
                        "coalescible": False,
                        "coalesce_key": None,
                    },
                    {
                        "event_id": _event_id("dirty", event_id),
                        "kind": "projection_dirty",
                        "payload": {"trigger_event_id": event_id},
                        "task_id": request.task_id,
                        "coalescible": True,
                        "coalesce_key": "global-projection",
                    },
                ),
                fence=self.engine.fence,
                task_id=request.task_id,
                workstream_id=request.workstream_id,
            )
            current_task = self.registry.get_task(request.task_id)
            current_workstream = self.registry.get_workstream(request.workstream_id)
            if current_task is not None and current_task.state != "parked":
                self.registry.update_task_state(
                    request.task_id,
                    expected_revision=current_task.revision,
                    new_state="parked",
                    fence=self.engine.fence,
                )
            if current_workstream is not None and current_workstream.state != "blocked":
                self.registry.update_workstream_state(
                    request.workstream_id,
                    current_workstream.generation,
                    expected_revision=current_workstream.revision,
                    new_state="blocked",
                    fence=self.engine.fence,
                )
        return {"created": created, "gate_id": request.gate_id, "attention_event_id": attention_event_id}

    def _human_gate_prerequisite_event(self, request: HumanGateRequest) -> Mapping[str, Any]:
        events = self.registry.list_events(
            task_id=request.task_id,
            workstream_id=request.workstream_id,
            event_types=("incident_policy",),
        )
        evidence = set(request.evidence)
        admitted_statuses = {
            "parked",
            "ambiguous_turn_parked",
            "missing_verified_checkpoint",
            "application_failed_fail_closed",
            "arbiter_failed_fail_closed",
            "parked_fail_closed",
        }
        for event in reversed(events):
            status = str(event.get("payload", {}).get("status") or "")
            if status in admitted_statuses and (
                event["event_id"] in evidence or f"event:{event['event_id']}" in evidence
            ):
                return event
        raise SupervisorCommandError(
            "HumanGate lacks durable proof that repo-owned remediation and bounded policy are exhausted"
        )

    def _command_queue_release_action(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        self._require_external_policy_adapter_mode()
        _exact_fields(
            payload,
            {"candidate", "release_candidate", "target_adapter", "message_id"},
            "release action payload",
        )
        candidate_raw = dict(_mapping(payload, "candidate"))
        candidate = release_candidate_from_mapping(candidate_raw)
        release_raw = dict(_mapping(payload, "release_candidate"))
        release_candidate = _release_train_candidate_from_mapping(release_raw)
        target_adapter = _machine("target_adapter", payload.get("target_adapter"))
        if (
            release_candidate.task_id != candidate.task_id
            or release_candidate.workstream_id != candidate.workstream_id
            or release_candidate.revision != candidate.task_revision
            or release_candidate.expected_head_sha != candidate.pr_head_sha
            or set(release_candidate.resources) != set(candidate.resources)
        ):
            raise SupervisorCommandError("Release Train candidate is stale for the scheduler reservation")
        message_id = _machine("message_id", payload.get("message_id"))
        with self._mutation_lock:
            matching_event = None
            for event in reversed(self.registry.list_events(task_id=candidate.task_id, event_types=("release_reserved",))):
                candidates = event["payload"].get("candidates")
                if isinstance(candidates, list) and candidate_raw in candidates:
                    matching_event = event
                    break
            if matching_event is None:
                raise SupervisorCommandError("release action lacks a matching deterministic reservation")
            self._ensure_release_candidate_reservation(candidate)
            event_id = _event_id("release-action", f"{candidate.candidate_id}:{candidate.pr_head_sha}")
            action_payload = {
                "schema": "dev-control-plane/release-action/v2",
                "candidate": candidate_raw,
                "release_candidate": release_raw,
                "target_adapter": target_adapter,
                "reservation_event_id": matching_event["event_id"],
                "task_revision": candidate.task_revision,
                "workstream_revision": candidate.workstream_revision,
                "pr_head_sha": candidate.pr_head_sha,
            }
            created = self.registry.accept_inbox_and_enqueue(
                message_id=message_id,
                source="private-unix-command:release-action",
                inbox_payload=action_payload,
                outbox_event_id=event_id,
                outbox_kind="release_action",
                outbox_payload=action_payload,
                fence=self.engine.fence,
                task_id=candidate.task_id,
                coalescible=False,
            )
        return {"queued": created, "event_id": event_id, "candidate_id": candidate.candidate_id}

    def _command_prepare_release_action(self, payload: Mapping[str, Any]) -> dict[str, Any] | None:
        self._require_external_policy_adapter_mode()
        _exact_fields(payload, {"visibility_timeout"}, "prepare release action payload")
        visibility = payload.get("visibility_timeout")
        if isinstance(visibility, bool) or not isinstance(visibility, (int, float)) or not 5 <= float(visibility) <= 900:
            raise SupervisorCommandError("release visibility timeout is out of bounds")
        with self._mutation_lock:
            claimed = self.registry.claim_outbox(
                self.engine.fence,
                worker_id="registered-release-train-adapter",
                limit=1,
                visibility_timeout=float(visibility),
                kinds=("release_action",),
            )
        if not claimed:
            return None
        message = claimed[0]
        with self._mutation_lock:
            self._prepared_release_claims[message.event_id] = (message.claim_token, dict(message.payload))
        return {
            "event_id": message.event_id,
            "payload": message.payload,
            "attempt": message.attempts,
            "claim_token": message.claim_token,
        }

    def _command_ack_release_action(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        self._require_external_policy_adapter_mode()
        _exact_fields(payload, {"event_id", "claim_token", "receipt", "message_id"}, "release action ACK")
        event_id = _machine("event_id", payload.get("event_id"))
        claim_token = _claim_token(payload.get("claim_token"))
        message_id = _machine("message_id", payload.get("message_id"))
        receipt = _validated_release_receipt(_mapping(payload, "receipt"))
        with self._mutation_lock:
            summary = next(
                (item for item in self.registry.list_outbox_summaries(kinds=("release_action",)) if item["event_id"] == event_id),
                None,
            )
            if summary is not None and summary["state"] == "delivered":
                result_event_id = _event_id("release-result", event_id)
                existing = self.registry.get_event(result_event_id)
                if existing is None or existing["payload"].get("receipt") != receipt:
                    raise SupervisorCommandError("delivered release action has a different durable receipt")
                return {"delivered": True, "idempotent": True, "event_id": event_id}
            prepared = self._prepared_release_claims.get(event_id)
            if prepared is None or prepared[0] != claim_token:
                raise SupervisorCommandError("release action was not prepared by this daemon generation")
            action_payload = prepared[1]
            scheduler_candidate = _mapping(action_payload, "candidate")
            release_candidate = _mapping(action_payload, "release_candidate")
            expected = (
                scheduler_candidate["candidate_id"],
                scheduler_candidate["task_id"],
                scheduler_candidate["workstream_id"],
                scheduler_candidate["task_revision"],
                scheduler_candidate["workstream_revision"],
                scheduler_candidate["pr_head_sha"],
            )
            observed = (
                receipt["candidate_id"],
                receipt["task_id"],
                receipt["workstream_id"],
                receipt["task_revision"],
                receipt["workstream_revision"],
                receipt["pr_head_sha"],
            )
            if expected != observed or release_candidate["expected_head_sha"] != receipt["pr_head_sha"]:
                raise SupervisorCommandError("release receipt is stale or bound to another candidate")
            self._validate_release_receipt_passport_binding(receipt)
            result_event_id = _event_id("release-result", event_id)
            self.registry.record_input_event_outbox(
                message_id=message_id,
                source="registered-release-train-adapter",
                input_payload={"release_action_event_id": event_id, "receipt": receipt},
                event_id=result_event_id,
                event_type="release_completed",
                event_payload={
                    "schema": "dev-control-plane/release-result-event/v2",
                    "release_action_event_id": event_id,
                    "receipt": receipt,
                    "target_adapter": action_payload["target_adapter"],
                },
                outbox_items=(self._dirty_item(result_event_id, receipt["task_id"]),),
                fence=self.engine.fence,
                task_id=receipt["task_id"],
                workstream_id=receipt["workstream_id"],
            )
            self.registry.ack_outbox(event_id, claim_token, self.engine.fence)
            self._prepared_release_claims.pop(event_id, None)
        return {"delivered": True, "idempotent": False, "event_id": event_id}

    def _command_nack_release_action(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        self._require_external_policy_adapter_mode()
        _exact_fields(payload, {"event_id", "claim_token", "retry_at", "reason_code"}, "release action NACK")
        event_id = _machine("event_id", payload.get("event_id"))
        claim_token = _claim_token(payload.get("claim_token"))
        retry_at = payload.get("retry_at")
        if isinstance(retry_at, bool) or not isinstance(retry_at, (int, float)) or float(retry_at) <= self.clock():
            raise SupervisorCommandError("release retry_at must be in the future")
        with self._mutation_lock:
            self.registry.nack_outbox(
                event_id,
                claim_token,
                self.engine.fence,
                retry_at=float(retry_at),
                sanitized_error=_machine("reason_code", payload.get("reason_code")),
            )
            self._prepared_release_claims.pop(event_id, None)
        return {"pending": True, "event_id": event_id}

    def _command_prepare_incident_arbiter(self, payload: Mapping[str, Any]) -> dict[str, Any] | None:
        self._require_external_policy_adapter_mode()
        return self._prepare_policy_action(payload, kind="incident_arbiter_case", worker="fresh-incident-arbiter")

    def _command_prepare_incident_application(self, payload: Mapping[str, Any]) -> dict[str, Any] | None:
        self._require_external_policy_adapter_mode()
        return self._prepare_policy_action(
            payload,
            kind="incident_arbiter_application",
            worker="registered-incident-application-adapter",
        )

    def _command_record_incident_arbiter(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        self._require_external_policy_adapter_mode()
        _exact_fields(payload, {"event_id", "claim_token", "decision", "message_id"}, "incident arbiter receipt")
        event_id = _machine("event_id", payload.get("event_id"))
        claim_token = _claim_token(payload.get("claim_token"))
        decision = arbiter_decision_from_mapping(_mapping(payload, "decision"))
        message_id = _machine("message_id", payload.get("message_id"))
        with self._mutation_lock:
            claimed = self._claimed_policy_message(event_id, claim_token, "incident_arbiter_case")
            state = _incident_state_from_mapping(_mapping(claimed, "incident_state"))
            updated = record_incident_arbiter_decision(state, decision)
            state_event_id = _event_id("incident-arbiter-decision", decision.decision_id)
            application_event_id = _event_id("incident-application", decision.decision_id)
            created = self.registry.record_input_event_outbox(
                message_id=message_id,
                source="private-unix-command:incident-arbiter",
                input_payload={"case_event_id": event_id, "decision": contract_to_dict(decision)},
                event_id=state_event_id,
                event_type="incident_policy",
                event_payload=self._incident_event_payload(
                    updated,
                    action="apply_arbiter_decision",
                    status="arbiter_decided",
                    attempt=updated.failure_count,
                ),
                outbox_items=(
                    {
                        "event_id": application_event_id,
                        "kind": "incident_arbiter_application",
                        "payload": {
                            "schema": "dev-control-plane/incident-application/v2",
                            "incident_state": _incident_state_to_dict(updated),
                            "decision": contract_to_dict(decision),
                        },
                        "task_id": updated.task_id,
                        "coalescible": False,
                        "coalesce_key": None,
                    },
                    self._dirty_item(state_event_id, updated.task_id),
                ),
                fence=self.engine.fence,
                task_id=updated.task_id,
                workstream_id=updated.workstream_id,
                executor_generation=updated.current_executor_generation,
            )
            self.registry.ack_outbox(event_id, claim_token, self.engine.fence)
            self._prepared_policy_claims.pop(event_id, None)
        return {"created": created, "application_event_id": application_event_id, "decision_id": decision.decision_id}

    def _command_complete_incident_application(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        self._require_external_policy_adapter_mode()
        _exact_fields(
            payload,
            {"event_id", "claim_token", "decision_id", "applied", "verification_passed", "message_id", "created_at"},
            "incident application receipt",
        )
        event_id = _machine("event_id", payload.get("event_id"))
        claim_token = _claim_token(payload.get("claim_token"))
        decision_id = _machine("decision_id", payload.get("decision_id"))
        if payload.get("applied") is not True or not isinstance(payload.get("verification_passed"), bool):
            raise SupervisorCommandError("incident application requires one applied decision and typed verification")
        message_id = _machine("message_id", payload.get("message_id"))
        created_at = _rfc3339(payload.get("created_at"))
        with self._mutation_lock:
            claimed = self._claimed_policy_message(event_id, claim_token, "incident_arbiter_application")
            state = _incident_state_from_mapping(_mapping(claimed, "incident_state"))
            applied = record_arbiter_application(state, decision_id=decision_id).state
            transition = record_independent_verification(applied, passed=bool(payload["verification_passed"]))
            updated = transition.state
            result_event_id = _event_id("incident-verification", event_id)
            outbox_items: list[dict[str, Any]] = [self._dirty_item(result_event_id, updated.task_id)]
            if transition.action == "park_workstream":
                outbox_items.append(self._serious_stall_attention(updated, created_at))
            created = self.registry.record_input_event_outbox(
                message_id=message_id,
                source="private-unix-command:incident-application",
                input_payload={
                    "application_event_id": event_id,
                    "decision_id": decision_id,
                    "verification_passed": payload["verification_passed"],
                },
                event_id=result_event_id,
                event_type="incident_policy",
                event_payload=self._incident_event_payload(
                    updated,
                    action=transition.action,
                    status="resolved" if updated.resolved else "parked",
                    attempt=updated.failure_count,
                ),
                outbox_items=tuple(outbox_items),
                fence=self.engine.fence,
                task_id=updated.task_id,
                workstream_id=updated.workstream_id,
                executor_generation=updated.current_executor_generation,
            )
            if updated.parked:
                self._park_incident_binding(updated)
            self.registry.ack_outbox(event_id, claim_token, self.engine.fence)
            self._prepared_policy_claims.pop(event_id, None)
        return {"created": created, "status": "resolved" if updated.resolved else "parked", "action": transition.action}

    def _command_runtime_health(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        _exact_fields(payload, set(), "runtime health payload")
        return self.health()

    def _require_external_policy_adapter_mode(self) -> None:
        if not self.allow_external_policy_adapters:
            raise SupervisorCommandError("external release/incident consumers are disabled; internal workers own the queue")

    def _command_runtime_state(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        _exact_fields(payload, set(), "runtime state payload")
        state = self.local_state()
        executors: list[dict[str, Any]] = []
        for workstream in self.registry.list_workstreams():
            executor = self.registry.current_executor(workstream.task_id, workstream.workstream_id)
            if executor is None:
                continue
            executors.append(
                {
                    "task_id": executor.task_id,
                    "workstream_id": executor.workstream_id,
                    "executor_generation": executor.executor_generation,
                    "thread_id": executor.thread_id,
                    "host_id": executor.host_id,
                    "model": executor.model,
                    "reasoning": executor.reasoning,
                    "state": executor.state,
                    "predecessor_generation": executor.predecessor_generation,
                    "proof_event_id": executor.proof_event_id,
                }
            )
        return {**state, "executors": executors}

    def _validate_release_candidate_reservation(self, candidate: Any, *, renew: bool) -> None:
        task = self.registry.get_task(candidate.task_id)
        workstream = self.registry.get_workstream(candidate.workstream_id)
        if (
            task is None
            or workstream is None
            or workstream.task_id != candidate.task_id
            or task.revision != candidate.task_revision
            or workstream.revision != candidate.workstream_revision
        ):
            raise SupervisorRuntimeError("release candidate revisions are stale")
        if renew:
            self.registry.validate_and_renew_scheduler_reservation(
                task_id=candidate.task_id,
                workstream_id=candidate.workstream_id,
                target_id=candidate.target_id,
                resources=candidate.resources,
                fence=self.engine.fence,
                ttl=self.release_reservation_ttl_seconds,
            )
            return
        expected = {
            ("task", candidate.task_id),
            ("release_lane", candidate.target_id),
            *(("resource", resource) for resource in candidate.resources),
        }
        now = self.clock()
        observed = {
            (item["lock_kind"], item["lock_key"])
            for item in self.registry.inspect_locks()
            if item["owner_task_id"] == candidate.task_id
            and item["owner_workstream_id"] == candidate.workstream_id
            and item["writer_generation"] == self.engine.fence.generation
            and item["expires_at"] > now
        }
        if not expected <= observed:
            raise SupervisorRuntimeError("release reservation is no longer exact and live")

    def _validate_release_reservation(self, action: Mapping[str, Any], *, renew: bool) -> None:
        candidate = release_candidate_from_mapping(_mapping(action, "candidate"))
        release_candidate = _release_train_candidate_from_mapping(_mapping(action, "release_candidate"))
        if release_candidate.expected_head_sha != candidate.pr_head_sha:
            raise SupervisorRuntimeError("release action head binding changed")
        self._validate_release_candidate_reservation(candidate, renew=renew)

    def _validate_incident_binding(self, payload: Mapping[str, Any]) -> None:
        binding = _mapping(payload, "binding")
        _exact_fields(
            binding,
            {
                "task_id", "task_revision", "workstream_id", "workstream_revision",
                "executor_generation", "pr_head_sha", "resources",
            },
            "incident immutable binding",
        )
        task_id = _machine("task_id", binding.get("task_id"))
        workstream_id = _machine("workstream_id", binding.get("workstream_id"))
        task = self.registry.get_task(task_id)
        workstream = self.registry.get_workstream(workstream_id)
        executor = self.registry.current_executor(task_id, workstream_id)
        if task is None or workstream is None or executor is None:
            raise SupervisorRuntimeError("incident binding disappeared")
        expected = (
            binding.get("task_revision"),
            binding.get("workstream_revision"),
            binding.get("executor_generation"),
        )
        observed = (task.revision, workstream.revision, executor.executor_generation)
        if observed != expected:
            raise SupervisorRuntimeError("incident recommendation binding is stale")
        head = binding.get("pr_head_sha")
        if not isinstance(head, str) or not re.fullmatch(r"[0-9a-f]{40,64}", head):
            raise SupervisorRuntimeError("incident recommendation immutable source is invalid")
        passport = task_passport_from_mapping(task.passport)
        resources = binding.get("resources")
        if not isinstance(resources, list) or tuple(sorted(set(resources))) != tuple(sorted(passport.resources)):
            raise SupervisorRuntimeError("incident recommendation resources changed")

    def _acquire_execution_locks(
        self,
        payload: Mapping[str, Any],
        *,
        thread_id: str | None = None,
    ) -> tuple[LockGrant, ...]:
        task = self.registry.get_task(str(payload["task_id"]))
        if task is None:
            raise SupervisorRuntimeError("execution lock task disappeared")
        self._assert_workspace_binding(
            str(payload["task_id"]),
            str(payload["workstream_id"]),
            Path(str(payload["cwd"])),
        )
        passport = task_passport_from_mapping(task.passport)
        workspace_id = _event_id("workspace", str(payload["cwd"]))
        exact_thread = thread_id or str(payload["thread_id"])
        with self._mutation_lock:
            return self.registry.acquire_execution_reservation(
                task_id=passport.task_id,
                workstream_id=str(payload["workstream_id"]),
                thread_id=exact_thread,
                workspace_id=workspace_id,
                resources=passport.resources,
                fence=self.engine.fence,
                ttl=self.execution_lock_ttl_seconds,
            )

    def _release_execution_locks(self, grants: Sequence[LockGrant]) -> None:
        with self._mutation_lock:
            try:
                self.registry.release_execution_reservation(tuple(grants), self.engine.fence)
            except Exception:
                # A stale generation cannot use the result; do not mask the
                # original model/transport failure with cleanup noise.
                pass

    def _start_execution_lease(
        self,
        payload: Mapping[str, Any],
        *,
        thread_id: str | None = None,
    ) -> tuple[tuple[LockGrant, ...], _ExecutionReservationLease]:
        grants = self._acquire_execution_locks(payload, thread_id=thread_id)
        lease = _ExecutionReservationLease(
            self,
            grants,
            ttl_seconds=self.execution_lock_ttl_seconds,
        )
        lease.start()
        return grants, lease

    def _validate_release_observation_binding(
        self,
        action: Mapping[str, Any],
        observation: Mapping[str, Any],
    ) -> None:
        candidate = release_candidate_from_mapping(_mapping(action, "candidate"))
        expected = (
            candidate.candidate_id,
            candidate.task_id,
            candidate.workstream_id,
            candidate.task_revision,
            candidate.workstream_revision,
            candidate.pr_head_sha,
        )
        observed = (
            observation["candidate_id"],
            observation["task_id"],
            observation["workstream_id"],
            observation["task_revision"],
            observation["workstream_revision"],
            observation["expected_head_sha"],
        )
        if observed != expected:
            raise SupervisorRuntimeError("release executor returned a stale nonterminal observation")
        admission = observation.get("admission_binding")
        if candidate.target_id == WB_CORE_REPOSITORY:
            if observation["status"] == "admitted" or (
                observation["status"] == "waiting_release"
                and observation["reason_code"] != "exact_admission_not_submitted"
            ):
                if not isinstance(admission, Mapping):
                    raise SupervisorRuntimeError(
                        "wb-core admitted observation lacks immutable admission binding"
                    )
        elif admission is not None:
            raise SupervisorRuntimeError(
                "non-wb release observation cannot claim a wb-core admission binding"
            )
        if observation["status"] == "readmission_required":
            if observation["observed_head_sha"] == candidate.pr_head_sha:
                raise SupervisorRuntimeError("release readmission did not observe a new exact head")
        elif observation["observed_head_sha"] != candidate.pr_head_sha:
            raise SupervisorRuntimeError("nonterminal release observation changed the exact PR head")

    def _persist_release_observation(
        self,
        message: OutboxMessage,
        observation: Mapping[str, Any],
    ) -> RuntimeWorkerResult:
        candidate = release_candidate_from_mapping(_mapping(message.payload, "candidate"))
        observation_identity = "|".join(
            (
                message.event_id,
                str(observation["status"]),
                str(observation["reason_code"]),
                str(observation["observed_head_sha"]),
                _sha256(
                    json.dumps(
                        observation.get("admission_binding"),
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                ),
            )
        )
        event_id = _event_id("release-action-observation", observation_identity)
        remediation_decision_id = message.payload.get("remediation_decision_id")
        with self._mutation_lock:
            if self.registry.get_event(event_id) is None:
                self.registry.record_input_event_outbox(
                    message_id=_event_id("release-action-observation-receipt", event_id),
                    source="supervisor-release-train-observer",
                    input_payload={
                        "release_action_event_id": message.event_id,
                        "status": observation["status"],
                        "reason_code": observation["reason_code"],
                        "observed_head_sha": observation["observed_head_sha"],
                    },
                    event_id=event_id,
                    event_type="release_action_observed",
                    event_payload={
                        "schema": "dev-control-plane/release-action-observed-event/v2",
                        "release_action_event_id": message.event_id,
                        "target_adapter": message.payload["target_adapter"],
                        "observation": dict(observation),
                    },
                    outbox_items=(self._dirty_item(event_id, candidate.task_id),),
                    fence=self.engine.fence,
                    task_id=candidate.task_id,
                    workstream_id=candidate.workstream_id,
                )
            if observation["status"] == "readmission_required":
                if isinstance(remediation_decision_id, str):
                    # A changed head after the one arbiter-authorized dispatch
                    # is failed independent verification, not a fresh retry
                    # budget or another semantic decision.
                    pass
                else:
                    registration_event_id = self._enqueue_internal_release_readmission(
                        candidate,
                        observed_head_sha=str(observation["observed_head_sha"]),
                        observation_event_id=event_id,
                    )
                    self.registry.ack_outbox(message.event_id, message.claim_token, self.engine.fence)
                    self.registry.release_scheduler_reservation_owner(
                        task_id=candidate.task_id,
                        workstream_id=candidate.workstream_id,
                        fence=self.engine.fence,
                    )
                    return RuntimeWorkerResult(
                        message.kind,
                        message.event_id,
                        "readmission_queued",
                        registration_event_id,
                    )
            else:
                self.registry.nack_outbox(
                    message.event_id,
                    message.claim_token,
                    self.engine.fence,
                    retry_at=self.clock() + float(observation["retry_after_seconds"]),
                    sanitized_error=str(observation["reason_code"]),
                )
        if observation["status"] == "readmission_required" and isinstance(
            remediation_decision_id, str
        ):
            return self._fail_incident_dispatch(
                message,
                remediation_decision_id,
                SupervisorRuntimeError("release head changed after arbiter dispatch"),
                verification_identity="release-head-changed-after-arbiter",
            )
        return RuntimeWorkerResult(
            message.kind,
            message.event_id,
            str(observation["status"]),
            str(observation["reason_code"]),
        )

    def _enqueue_internal_release_readmission(
        self,
        candidate: SchedulerReleaseCandidate,
        *,
        observed_head_sha: str,
        observation_event_id: str,
    ) -> str:
        task = self.registry.get_task(candidate.task_id)
        workstream = self.registry.get_workstream(candidate.workstream_id)
        if (
            task is None
            or workstream is None
            or task.revision != candidate.task_revision
            or workstream.revision != candidate.workstream_revision
            or workstream.state != "waiting_release"
            or task.state in {"accepted", "parked"}
        ):
            raise SupervisorRuntimeError("release readmission binding changed before durable intake")
        passport = task_passport_from_mapping(task.passport)
        target_id = self._passport_release_target(passport)
        registration = {
            "schema": RELEASE_CANDIDATE_REGISTRATION_SCHEMA,
            "task_id": candidate.task_id,
            "task_revision": task.revision,
            "workstream_id": candidate.workstream_id,
            "workstream_revision": workstream.revision,
            "expected_pr_head_sha": observed_head_sha,
            "target_id": target_id,
        }
        registration_event_id = _event_id(
            "release-candidate-registration",
            json.dumps(registration, sort_keys=True, separators=(",", ":")),
        )
        intake_event_id = _event_id("release-candidate-intake", registration_event_id)
        self.registry.record_input_event_outbox(
            message_id=_event_id("release-readmission-input", observation_event_id),
            source="supervisor-release-train-readmission",
            input_payload={
                "task_id": candidate.task_id,
                "workstream_id": candidate.workstream_id,
                "expected_pr_head_sha": observed_head_sha,
                "observation_event_id": observation_event_id,
            },
            event_id=registration_event_id,
            event_type="release_candidate_registered",
            event_payload=registration,
            outbox_items=(
                {
                    "event_id": intake_event_id,
                    "kind": "release_candidate_intake",
                    "payload": {
                        "schema": RELEASE_CANDIDATE_INTAKE_SCHEMA,
                        "registration_event_id": registration_event_id,
                        "task_id": candidate.task_id,
                        "workstream_id": candidate.workstream_id,
                        "expected_pr_head_sha": observed_head_sha,
                    },
                    "task_id": candidate.task_id,
                    "coalescible": False,
                    "coalesce_key": None,
                },
                self._dirty_item(registration_event_id, candidate.task_id),
            ),
            fence=self.engine.fence,
            task_id=candidate.task_id,
            workstream_id=candidate.workstream_id,
        )
        superseded_event_id = _event_id(
            "release-superseded",
            f"{candidate.candidate_id}|{candidate.pr_head_sha}|{observed_head_sha}",
        )
        self.registry.record_input_event_outbox(
            message_id=_event_id("release-superseded-receipt", superseded_event_id),
            source="supervisor-release-train-readmission",
            input_payload={
                "observation_event_id": observation_event_id,
                "candidate_id": candidate.candidate_id,
                "old_head_sha": candidate.pr_head_sha,
                "new_head_sha": observed_head_sha,
            },
            event_id=superseded_event_id,
            event_type="release_superseded",
            event_payload={
                "schema": "dev-control-plane/release-superseded/v2",
                "candidate_id": candidate.candidate_id,
                "task_revision": candidate.task_revision,
                "workstream_revision": candidate.workstream_revision,
                "pr_head_sha": candidate.pr_head_sha,
                "replacement_head_sha": observed_head_sha,
                "observation_event_id": observation_event_id,
            },
            outbox_items=(self._dirty_item(superseded_event_id, candidate.task_id),),
            fence=self.engine.fence,
            task_id=candidate.task_id,
            workstream_id=candidate.workstream_id,
        )
        return registration_event_id

    def _persist_release_result(self, message: OutboxMessage, receipt: Mapping[str, Any]) -> None:
        action_payload = message.payload
        scheduler_candidate = _mapping(action_payload, "candidate")
        expected = (
            scheduler_candidate["candidate_id"],
            scheduler_candidate["task_id"],
            scheduler_candidate["workstream_id"],
            scheduler_candidate["task_revision"],
            scheduler_candidate["workstream_revision"],
            scheduler_candidate["pr_head_sha"],
        )
        observed = (
            receipt["candidate_id"], receipt["task_id"], receipt["workstream_id"],
            receipt["task_revision"], receipt["workstream_revision"], receipt["pr_head_sha"],
        )
        if expected != observed:
            raise SupervisorRuntimeError("release executor returned a stale receipt")
        self._validate_release_receipt_passport_binding(receipt)
        result_event_id = _event_id("release-result", message.event_id)
        with self._mutation_lock:
            self.registry.record_input_event_outbox(
                message_id=_event_id("release-result-receipt", message.event_id),
                source="supervisor-release-train-worker",
                input_payload={"release_action_event_id": message.event_id, "receipt": dict(receipt)},
                event_id=result_event_id,
                event_type="release_completed",
                event_payload={
                    "schema": "dev-control-plane/release-result-event/v2",
                    "release_action_event_id": message.event_id,
                    "receipt": dict(receipt),
                    "target_adapter": action_payload["target_adapter"],
                },
                outbox_items=(self._dirty_item(result_event_id, str(receipt["task_id"])),),
                fence=self.engine.fence,
                task_id=str(receipt["task_id"]),
                workstream_id=str(receipt["workstream_id"]),
            )
            self.registry.ack_outbox(message.event_id, message.claim_token, self.engine.fence)

    def _validate_release_receipt_passport_binding(
        self, receipt: Mapping[str, Any]
    ) -> None:
        task = self.registry.get_task(str(receipt["task_id"]))
        workstream = self.registry.get_workstream(str(receipt["workstream_id"]))
        if (
            task is None
            or workstream is None
            or workstream.task_id != receipt["task_id"]
            or task.revision != receipt["task_revision"]
            or workstream.revision != receipt["workstream_revision"]
        ):
            raise SupervisorRuntimeError("release receipt current revision is stale")
        passport = task_passport_from_mapping(task.passport)
        if passport.contour != receipt["contour"]:
            raise SupervisorRuntimeError("release receipt contour differs from Passport")
        target_id = self._passport_release_target(passport)
        admission = receipt.get("admission_binding")
        if target_id == "orenvlad-ai/wb-core":
            if not isinstance(admission, Mapping):
                raise SupervisorRuntimeError(
                    "wb-core release receipt lacks immutable admission binding"
                )
        elif admission is not None:
            raise SupervisorRuntimeError(
                "non-wb release receipt cannot claim a wb-core admission binding"
            )

    def _execute_release_resolution(self, message: OutboxMessage) -> RuntimeWorkerResult:
        if self.release_candidate_resolver is None:
            raise SupervisorRuntimeError("release candidate resolver is unavailable")
        _exact_fields(
            message.payload,
            {"schema", "candidate", "source_event_id", "remediation_decision_id"},
            "release candidate resolution",
        )
        if message.payload.get("schema") != "dev-control-plane/release-candidate-resolution/v2":
            raise SupervisorRuntimeError("release candidate resolution schema mismatch")
        candidate = release_candidate_from_mapping(_mapping(message.payload, "candidate"))
        result_event_id = _event_id("release-candidate-resolved", message.event_id)
        with self._mutation_lock:
            if self.registry.get_event(result_event_id) is not None:
                self.registry.ack_outbox(message.event_id, message.claim_token, self.engine.fence)
                self._reconcile_incident_applications()
                return RuntimeWorkerResult(message.kind, message.event_id, "deduped", result_event_id)
        reservation_lease: _ReleaseReservationLease | None = None
        try:
            self._ensure_release_candidate_reservation(candidate)
            reservation_lease = _ReleaseReservationLease(self, message.payload)
            reservation_lease.start()
            guard = RuntimeActionGuard(self, message.payload, release=False)
            guard.assert_current()
            resolved = self.release_candidate_resolver(dict(message.payload), guard)
            guard.assert_current()
            if guard.callback_checks < 1:
                raise SupervisorRuntimeError("release resolver omitted its immutable readback checkpoint")
            reservation_lease.assert_current()
            _exact_fields(
                resolved,
                {"release_candidate", "target_adapter", "scheduler_truth"},
                "release resolution receipt",
            )
            release_raw = dict(_mapping(resolved, "release_candidate"))
            release_candidate = _release_train_candidate_from_mapping(release_raw)
            target_adapter = _machine("target_adapter", resolved.get("target_adapter"))
            self._validate_resolved_release_candidate(candidate, release_candidate)
            scheduler_truth = dict(_mapping(resolved, "scheduler_truth"))
            # A PR may merge after intake/reservation and before this exact
            # resolver readback. MERGED is immutable proof, never a causal
            # failure and never something the Supervisor may relabel OPEN.
            self._validate_scheduler_truth(candidate, scheduler_truth, allow_merged=True)
            self._validate_release_candidate_reservation(candidate, renew=True)
            if scheduler_truth["pr_state"] == "MERGED":
                proof_candidate = replace(
                    candidate,
                    checks_green=bool(scheduler_truth["checks_green"]),
                    admission_ready=False,
                    merge_conflict=bool(scheduler_truth["merge_conflict"]),
                    passport_diff_mismatch=bool(scheduler_truth["passport_diff_mismatch"]),
                    unknown_classification=bool(scheduler_truth["unknown_classification"]),
                )
                with self._mutation_lock:
                    self.registry.record_input_event_outbox(
                        message_id=_event_id("release-proof-only-receipt", message.event_id),
                        source="supervisor-release-candidate-resolver",
                        input_payload={
                            "resolution_event_id": message.event_id,
                            "candidate_id": candidate.candidate_id,
                            "pr_head_sha": candidate.pr_head_sha,
                            "merge_commit_sha": scheduler_truth["merge_commit_sha"],
                        },
                        event_id=result_event_id,
                        event_type="release_proof_only",
                        event_payload={
                            "schema": "dev-control-plane/release-proof-only/v2",
                            "candidate": asdict(proof_candidate),
                            "target_adapter": target_adapter,
                            "release_candidate": release_raw,
                            "scheduler_truth": scheduler_truth,
                            "proof_only": True,
                            "created_at": _iso(self.clock()),
                        },
                        outbox_items=(self._dirty_item(result_event_id, candidate.task_id),),
                        fence=self.engine.fence,
                        task_id=candidate.task_id,
                        workstream_id=candidate.workstream_id,
                    )
                    self.registry.ack_outbox(
                        message.event_id, message.claim_token, self.engine.fence
                    )
                    self._reconcile_incident_applications()
                reservation_lease.stop()
                reservation_lease = None
                return RuntimeWorkerResult(
                    message.kind, message.event_id, "proof_only_wait", result_event_id
                )
            action_event_id = _event_id(
                "release-action",
                f"{candidate.candidate_id}:{candidate.pr_head_sha}:"
                f"{message.payload.get('remediation_decision_id') or 'initial'}",
            )
            action_payload = {
                "schema": "dev-control-plane/release-action/v2",
                "candidate": asdict(candidate),
                "release_candidate": release_raw,
                "target_adapter": target_adapter,
                "reservation_event_id": message.payload["source_event_id"],
                "task_revision": candidate.task_revision,
                "workstream_revision": candidate.workstream_revision,
                "pr_head_sha": candidate.pr_head_sha,
                "remediation_decision_id": message.payload.get("remediation_decision_id"),
            }
            with self._mutation_lock:
                self.registry.record_input_event_outbox(
                    message_id=_event_id("release-resolution-receipt", message.event_id),
                    source="supervisor-release-candidate-resolver",
                    input_payload={
                        "resolution_event_id": message.event_id,
                        "candidate_id": candidate.candidate_id,
                        "pr_head_sha": candidate.pr_head_sha,
                        "target_adapter": target_adapter,
                    },
                    event_id=result_event_id,
                    event_type="release_candidate_resolved",
                    event_payload={
                        "schema": "dev-control-plane/release-candidate-resolved-event/v2",
                        "candidate": asdict(candidate),
                        "target_adapter": target_adapter,
                        "release_candidate": release_raw,
                    },
                    outbox_items=(
                        {
                            "event_id": action_event_id,
                            "kind": "release_action",
                            "payload": action_payload,
                            "task_id": candidate.task_id,
                            "coalescible": False,
                            "coalesce_key": None,
                        },
                        self._dirty_item(result_event_id, candidate.task_id),
                    ),
                    fence=self.engine.fence,
                    task_id=candidate.task_id,
                    workstream_id=candidate.workstream_id,
                )
                self.registry.ack_outbox(message.event_id, message.claim_token, self.engine.fence)
            reservation_lease.stop()
            reservation_lease = None
            return RuntimeWorkerResult(message.kind, message.event_id, "resolved", action_event_id)
        except SecurityPermissionChangeRequiresOwner as exc:
            if reservation_lease is not None:
                reservation_lease.stop()
            remediation_decision_id = message.payload.get("remediation_decision_id")
            if isinstance(remediation_decision_id, str):
                return self._fail_incident_dispatch(
                    message,
                    remediation_decision_id,
                    exc,
                    verification_identity="release-resolution-authorization-failed-after-arbiter",
                )
            return self._persist_release_human_gate(message, candidate, exc)
        except Exception as exc:
            if reservation_lease is not None:
                reservation_lease.stop()
            remediation_decision_id = message.payload.get("remediation_decision_id")
            if isinstance(remediation_decision_id, str):
                return self._fail_incident_dispatch(
                    message,
                    remediation_decision_id,
                    exc,
                    verification_identity="release-resolution-failed-after-arbiter",
                )
            with self._mutation_lock:
                if message.attempts == 1:
                    self.registry.nack_outbox(
                        message.event_id,
                        message.claim_token,
                        self.engine.fence,
                        retry_at=self.clock() + self.retry_delay_seconds,
                        sanitized_error=_error_code(exc),
                    )
                    return RuntimeWorkerResult(message.kind, message.event_id, "retry_scheduled", _error_code(exc))
            fingerprint = self._release_failure_fingerprint(
                candidate,
                exc,
                stage="candidate_resolution",
            )
            if self._release_incident_was_applied(candidate, fingerprint):
                return self._park_release_policy_message(
                    message,
                    (candidate,),
                    exc,
                    phase="same_resolution_failure_after_release_arbiter",
                )
            return self._route_release_incident(
                message,
                candidate,
                exc,
                fingerprint=fingerprint,
            )

    def _validate_resolved_release_candidate(
        self,
        candidate: Any,
        release_candidate: ReleaseTrainCandidate,
    ) -> None:
        expected = (
            candidate.logical_lane_id,
            candidate.task_id,
            candidate.workstream_id,
            candidate.task_revision,
            candidate.pr_head_sha,
            set(candidate.resources),
        )
        observed = (
            release_candidate.lane_id,
            release_candidate.task_id,
            release_candidate.workstream_id,
            release_candidate.revision,
            release_candidate.expected_head_sha,
            set(release_candidate.resources),
        )
        if observed != expected:
            raise SupervisorRuntimeError("resolved Release Train candidate changed immutable scheduler bindings")
        declared = set(release_candidate.declared_files)
        if declared != set(candidate.passport_files) or not set(candidate.diff_files).issubset(declared):
            raise SupervisorRuntimeError("resolved Release Train file contour differs from Passport and PR diff")
        if release_candidate.multi_pr != candidate.multi_pr_intent:
            raise SupervisorRuntimeError("resolved Release Train multi-PR intent changed")

    def _validate_scheduler_truth(
        self,
        candidate: Any,
        truth: Mapping[str, Any],
        *,
        allow_merged: bool = False,
    ) -> None:
        _exact_fields(
            truth,
            {
                "task_revision", "workstream_revision", "pr_head_sha", "target_id",
                "pr_state", "merge_commit_sha", "diff_files", "checks_green", "admission_ready", "merge_conflict",
                "passport_diff_mismatch", "unknown_classification",
            },
            "scheduler truth",
        )
        if (
            truth.get("task_revision") != candidate.task_revision
            or truth.get("workstream_revision") != candidate.workstream_revision
            or truth.get("pr_head_sha") != candidate.pr_head_sha
            or truth.get("target_id") != candidate.target_id
        ):
            raise SupervisorRuntimeError("scheduler GitHub truth binding is stale")
        state = truth.get("pr_state")
        merge_sha = truth.get("merge_commit_sha")
        if state == "OPEN":
            if merge_sha is not None:
                raise SupervisorRuntimeError("open scheduler truth unexpectedly has a merge commit")
        elif state == "MERGED" and allow_merged:
            if not isinstance(merge_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", merge_sha):
                raise SupervisorRuntimeError("merged scheduler truth lacks an immutable merge commit")
        else:
            raise SupervisorRuntimeError("scheduler PR state is not admitted for this release phase")
        diff_files = truth.get("diff_files")
        if (
            not isinstance(diff_files, list)
            or not all(isinstance(item, str) and item for item in diff_files)
            or tuple(sorted(set(diff_files))) != tuple(sorted(candidate.diff_files))
        ):
            raise SupervisorRuntimeError("scheduler PR diff was not derived from exact GitHub truth")
        for key in (
            "checks_green", "merge_conflict", "passport_diff_mismatch",
            "unknown_classification",
        ):
            if not isinstance(truth.get(key), bool) or truth[key] != getattr(candidate, key):
                raise SupervisorRuntimeError(f"scheduler field {key} differs from exact adapter truth")
        if not isinstance(truth.get("admission_ready"), bool) or (
            truth["admission_ready"] is not False
            if state == "MERGED"
            else truth["admission_ready"] != candidate.admission_ready
        ):
            raise SupervisorRuntimeError(
                "scheduler field admission_ready differs from exact adapter truth"
            )

    def _persist_release_human_gate(
        self,
        message: OutboxMessage,
        candidate: SchedulerReleaseCandidate,
        exc: SecurityPermissionChangeRequiresOwner,
    ) -> RuntimeWorkerResult:
        """Persist one exact protected-controller HumanGate without retry budget."""

        if candidate.pr_head_sha != exc.expected_head_sha:
            raise SupervisorRuntimeError("protected controller HumanGate head binding is stale")
        task = self.registry.get_task(candidate.task_id)
        workstream = self.registry.get_workstream(candidate.workstream_id)
        if (
            task is None
            or workstream is None
            or workstream.task_id != candidate.task_id
            or task.revision != candidate.task_revision
            or workstream.revision != candidate.workstream_revision
        ):
            raise SupervisorRuntimeError("protected controller HumanGate revision is stale")
        passport = task_passport_from_mapping(task.passport)
        # This internal stop is globally allowlisted security authority.  A
        # missing Passport reason proves the mutation was *not* pre-authorized;
        # it must therefore park and notify, never replay the claimed actuator.
        active_siblings = tuple(
            item
            for item in self.registry.list_workstreams()
            if item.task_id == candidate.task_id
            and item.workstream_id != candidate.workstream_id
            and item.current
            and item.state
            not in {
                "technical_complete",
                "acceptance_pending",
                "accepted",
                "blocked",
                "parked",
            }
        )
        if active_siblings:
            with self._mutation_lock:
                self.registry.nack_outbox(
                    message.event_id,
                    message.claim_token,
                    self.engine.fence,
                    retry_at=self.clock() + max(1.0, self.retry_delay_seconds),
                    sanitized_error="independent_safe_work_incomplete",
                )
            return RuntimeWorkerResult(
                message.kind,
                message.event_id,
                "human_gate_deferred",
                "independent_safe_work_incomplete",
            )
        evidence = tuple(exc.evidence) + (
            f"head:{candidate.pr_head_sha}",
            "read_only_checks_completed",
            "repo_owned_remediation_exhausted",
        )
        gate_id = _event_id(
            "security-permission-change",
            f"{candidate.task_id}|{candidate.workstream_id}|{candidate.pr_head_sha}",
        )
        request = validate_human_gate(
            HumanGateRequest(
                gate_id=gate_id,
                task_id=candidate.task_id,
                workstream_id=candidate.workstream_id,
                reason_code=exc.reason_code,
                requested_actions=(exc.requested_action,),
                human_exclusive=True,
                already_authorized_by_passport=False,
                independent_safe_work_complete=True,
                repo_owned_remediation_exhausted=True,
                evidence=evidence,
            )
        )
        created_at = _iso(self.clock())
        event_id = _event_id("human-gate", request.gate_id)
        attention_event_id = _event_id("curator-human-gate", request.gate_id)
        action = request.requested_actions[0]
        event_payload = {
            "schema": "dev-control-plane/human-gate-event/v2",
            "revision": task.revision,
            "status": "human_gate",
            "fingerprint": _sha256(request.reason_code + "|" + action),
            "summary": "Exact protected controller/governance diff requires owner authority.",
            "decision": "park_workstream",
            "attempt": 1,
            "reason_code": request.reason_code,
            "requested_action": action,
            "pr_head_sha": candidate.pr_head_sha,
            "updated_at": created_at,
        }
        attention = {
            "schema": "dev-control-plane/curator-attention/v2",
            "attention_id": request.gate_id,
            "task_id": request.task_id,
            "workstream_id": request.workstream_id,
            "curator_thread_id": passport.curator.thread_id,
            "kind": "human_gate",
            "handoff_ru": (
                "Статус: Блокер\n"
                f"Задача: {passport.title}\n"
                "Причина: изменение controller/governance затрагивает security/permission boundary.\n"
                f"Доказательство: exact head {candidate.pr_head_sha}; read-only checks завершены.\n"
                f"Требуется одно действие: {action}"
            ),
            "required_action": action,
            "created_at": created_at,
        }
        with self._mutation_lock:
            self.registry.record_input_event_outbox(
                message_id=_event_id("release-human-gate-receipt", message.event_id),
                source="supervisor-release-protected-controller-gate",
                input_payload={
                    "release_event_id": message.event_id,
                    "candidate_id": candidate.candidate_id,
                    "pr_head_sha": candidate.pr_head_sha,
                },
                event_id=event_id,
                event_type="incident_policy",
                event_payload=event_payload,
                outbox_items=(
                    {
                        "event_id": attention_event_id,
                        "kind": "curator_attention",
                        "payload": attention,
                        "task_id": candidate.task_id,
                        "coalescible": False,
                        "coalesce_key": None,
                    },
                    self._dirty_item(event_id, candidate.task_id),
                ),
                fence=self.engine.fence,
                task_id=candidate.task_id,
                workstream_id=candidate.workstream_id,
            )
            self.registry.ack_outbox(
                message.event_id, message.claim_token, self.engine.fence
            )
            current_task = self.registry.get_task(candidate.task_id)
            current_workstream = self.registry.get_workstream(candidate.workstream_id)
            if current_task is not None and current_task.state != "parked":
                self.registry.update_task_state(
                    candidate.task_id,
                    expected_revision=current_task.revision,
                    new_state="parked",
                    fence=self.engine.fence,
                )
            if current_workstream is not None and current_workstream.state != "blocked":
                self.registry.update_workstream_state(
                    candidate.workstream_id,
                    current_workstream.generation,
                    expected_revision=current_workstream.revision,
                    new_state="blocked",
                    fence=self.engine.fence,
                )
        return RuntimeWorkerResult(
            message.kind,
            message.event_id,
            "human_gate",
            attention_event_id,
        )

    def _release_failure_fingerprint(self, candidate: Any, exc: Exception, *, stage: str) -> str:
        return _sha256(
            "|".join(
                (
                    stage,
                    candidate.target_id,
                    candidate.task_id,
                    candidate.workstream_id,
                    candidate.pr_head_sha,
                    _error_code(exc),
                    _sha256(str(exc)[:1_000]),
                )
            )
        )

    def _record_release_failure_observation(
        self,
        message: OutboxMessage,
        candidate: SchedulerReleaseCandidate,
        *,
        fingerprint: str,
        stage: str,
        exc: Exception,
    ) -> int:
        """Count causal failures independently from successful wait-poll claims."""

        prior = tuple(
            event
            for event in self.registry.list_events(
                task_id=candidate.task_id,
                workstream_id=candidate.workstream_id,
                event_types=("release_failure_observed",),
            )
            if event.get("payload", {}).get("fingerprint") == fingerprint
            and event.get("payload", {}).get("stage") == stage
            and event.get("payload", {}).get("candidate_id") == candidate.candidate_id
            and event.get("payload", {}).get("pr_head_sha") == candidate.pr_head_sha
        )
        occurrence = len(prior) + 1
        event_id = _event_id(
            "release-failure-observed",
            f"{message.event_id}|{fingerprint}|{occurrence}",
        )
        with self._mutation_lock:
            self.registry.record_input_event_outbox(
                message_id=_event_id("release-failure-observed-receipt", event_id),
                source="supervisor-release-train-worker",
                input_payload={
                    "release_action_event_id": message.event_id,
                    "candidate_id": candidate.candidate_id,
                    "pr_head_sha": candidate.pr_head_sha,
                    "fingerprint": fingerprint,
                    "occurrence": occurrence,
                },
                event_id=event_id,
                event_type="release_failure_observed",
                event_payload={
                    "schema": "dev-control-plane/release-failure-observed/v2",
                    "release_action_event_id": message.event_id,
                    "candidate_id": candidate.candidate_id,
                    "task_revision": candidate.task_revision,
                    "workstream_revision": candidate.workstream_revision,
                    "pr_head_sha": candidate.pr_head_sha,
                    "fingerprint": fingerprint,
                    "stage": stage,
                    "occurrence": occurrence,
                    "error_code": _error_code(exc),
                    "observed_at": _iso(self.clock()),
                },
                outbox_items=(self._dirty_item(event_id, candidate.task_id),),
                fence=self.engine.fence,
                task_id=candidate.task_id,
                workstream_id=candidate.workstream_id,
            )
        return occurrence

    def _release_incident_was_applied(self, candidate: Any, fingerprint: str) -> bool:
        for event in reversed(
            self.registry.list_events(
                task_id=candidate.task_id,
                workstream_id=candidate.workstream_id,
                event_types=("incident_policy",),
            )
        ):
            payload = event.get("payload")
            state_raw = payload.get("incident_state") if isinstance(payload, Mapping) else None
            if not isinstance(state_raw, Mapping) or state_raw.get("fingerprint") != fingerprint:
                continue
            state = _incident_state_from_mapping(state_raw)
            return state.arbiter_applied or state.parked or state.resolved
        return False

    def _route_release_incident(
        self,
        message: OutboxMessage,
        candidate: Any,
        exc: Exception,
        *,
        fingerprint: str,
    ) -> RuntimeWorkerResult:
        """Skip executor succession for a mechanical actor and invoke one arbiter.

        The Release Train has no model executor context to replace. Its first
        failure already received one fresh-truth retry. The second identical
        failure therefore creates one immutable incident directly, explicitly
        recording that executor succession is inapplicable. One arbiter
        application may re-resolve/release once; recurrence then parks.
        """

        task = self.registry.get_task(candidate.task_id)
        workstream = self.registry.get_workstream(candidate.workstream_id)
        executor = self.registry.current_executor(candidate.task_id, candidate.workstream_id)
        if task is None or workstream is None or executor is None:
            return self._park_release_policy_message(
                message,
                (candidate,),
                exc,
                phase="release_incident_binding_missing",
            )
        evidence_digest = _sha256(
            f"{candidate.candidate_id}|{candidate.pr_head_sha}|{_error_code(exc)}"
        )
        case_digest = _sha256(
            f"release-incident|{fingerprint}|{candidate.task_revision}|"
            f"{candidate.workstream_revision}|{executor.executor_generation}|{evidence_digest}"
        )
        state = IncidentState(
            task_id=candidate.task_id,
            workstream_id=candidate.workstream_id,
            fingerprint=fingerprint,
            context=IncidentContext(
                passport_revision=task.revision,
                strategy_digest=_sha256("mechanical-release-train-v2"),
                causal_evidence_digest=evidence_digest,
                verified_checkpoint_id=self._incident_checkpoint_id(
                    candidate.task_id,
                    candidate.workstream_id,
                    executor.executor_generation,
                ),
            ),
            failure_count=3,
            current_executor_generation=executor.executor_generation,
            retry_used=True,
            incident_case_id=f"incident:{case_digest[:24]}",
            incident_case_digest=case_digest,
        )
        incident_item = self._incident_arbiter_item(state)
        source_event_id = (
            message.payload.get("reservation_event_id")
            or message.payload.get("source_event_id")
            or message.payload.get("registration_event_id")
        )
        incident_item["payload"]["remediation"] = {
            "schema": "dev-control-plane/release-incident-remediation/v2",
            "kind": "release_action",
            "candidate": asdict(candidate),
            "source_event_id": source_event_id,
            "prior_action_event_id": message.event_id,
            "fingerprint": fingerprint,
        }
        event_id = _event_id("release-incident", f"{candidate.candidate_id}:{fingerprint}")
        with self._mutation_lock:
            self.registry.record_input_event_outbox(
                message_id=_event_id("release-incident-receipt", message.event_id),
                source="supervisor-release-train-worker",
                input_payload={
                    "release_action_event_id": message.event_id,
                    "candidate_id": candidate.candidate_id,
                    "fingerprint": fingerprint,
                    "error_code": _error_code(exc),
                },
                event_id=event_id,
                event_type="incident_policy",
                event_payload={
                    **self._incident_event_payload(
                        state,
                        action="invoke_incident_arbiter",
                        status="incident_open",
                        attempt=state.failure_count,
                        error_code=_error_code(exc),
                    ),
                    "actor": "mechanical_release_train",
                    "successor_applicable": False,
                    "candidate_id": candidate.candidate_id,
                    "pr_head_sha": candidate.pr_head_sha,
                },
                outbox_items=(incident_item, self._dirty_item(event_id, candidate.task_id)),
                fence=self.engine.fence,
                task_id=candidate.task_id,
                workstream_id=candidate.workstream_id,
                executor_generation=executor.executor_generation,
            )
            self.registry.ack_outbox(message.event_id, message.claim_token, self.engine.fence)
        return RuntimeWorkerResult("release_action", message.event_id, "incident_open", state.incident_case_id or "")

    def _execute_release_arbiter(self, message: OutboxMessage) -> RuntimeWorkerResult:
        if self.release_arbiter_executor is None:
            raise SupervisorRuntimeError("release arbiter executor is unavailable")
        _exact_fields(
            message.payload,
            {"schema", "source_event_id", "semantic_case"},
            "release arbiter case",
        )
        if message.payload.get("schema") != "dev-control-plane/release-arbiter-case/v2":
            raise SupervisorRuntimeError("release arbiter case schema mismatch")
        semantic_case = self._semantic_case_from_decision_payload(
            {"semantic_case": _mapping(message.payload, "semantic_case")}
        )
        result_event_id = _event_id("release-plan-decision", semantic_case.case_id)
        with self._mutation_lock:
            if self.registry.get_event(result_event_id) is not None:
                self.registry.ack_outbox(message.event_id, message.claim_token, self.engine.fence)
                return RuntimeWorkerResult(message.kind, message.event_id, "deduped", result_event_id)
        try:
            self._validate_semantic_case_current(semantic_case)
            guard = RuntimeActionGuard(self, message.payload, release=False)
            guard.assert_current()
            decision = self.release_arbiter_executor(dict(message.payload), guard)
            guard.assert_current()
            if guard.callback_checks < 1:
                raise SupervisorRuntimeError("release arbiter omitted its generation checkpoint")
            if not isinstance(decision, ArbiterDecision):
                raise SupervisorRuntimeError("release arbiter returned no typed decision")
            self._validate_semantic_case_current(semantic_case)
            order = validate_arbiter_release_decision(semantic_case, decision)
            if len(decision.steps) != len(semantic_case.candidates):
                raise SupervisorRuntimeError("release plan must contain exactly one step per candidate")
            step_bindings = [(step.task_id, step.workstream_id) for step in decision.steps]
            if len(set(step_bindings)) != len(step_bindings):
                raise SupervisorRuntimeError("release plan contains multiple steps for one candidate")
            if any(step.action not in {"release", "wait"} for step in decision.steps):
                raise SupervisorRuntimeError("release plan contains a non-mechanical action")
            semantic_payload = self._semantic_case_payload(semantic_case)
            with self._mutation_lock:
                self.registry.record_input_event_outbox(
                    message_id=_event_id("release-arbiter-receipt", message.event_id),
                    source="supervisor-fresh-release-arbiter",
                    input_payload={
                        "case_event_id": message.event_id,
                        "decision": contract_to_dict(decision),
                    },
                    event_id=result_event_id,
                    event_type="release_plan_decision",
                    event_payload={
                        "schema": "dev-control-plane/release-plan-decision-event/v2",
                        "source_event_id": message.payload["source_event_id"],
                        "semantic_case": semantic_payload,
                        "candidates": semantic_payload["candidates"],
                        "decision": contract_to_dict(decision),
                        "topological_order": list(order),
                    },
                    outbox_items=(self._dirty_item(result_event_id, None),),
                    fence=self.engine.fence,
                    task_id=None,
                    workstream_id=None,
                )
                self.registry.ack_outbox(message.event_id, message.claim_token, self.engine.fence)
                self._reconcile_release_orchestration()
            return RuntimeWorkerResult(message.kind, message.event_id, "decided", decision.decision_id)
        except StaleArbiterDecision:
            with self._mutation_lock:
                current, registrations, _complete = (
                    self._current_admitted_release_snapshot()
                )
                self._supersede_semantic_release_plan(
                    semantic_case,
                    current_candidates=current,
                    current_registrations=registrations,
                    source_event_id=message.event_id,
                )
                self.registry.ack_outbox(
                    message.event_id, message.claim_token, self.engine.fence
                )
            return RuntimeWorkerResult(
                message.kind,
                message.event_id,
                "superseded",
                semantic_case.case_id,
            )
        except Exception as exc:
            # A RELEASE_PLAN is a one-shot fresh semantic decision. Even an
            # ambiguous provider outcome is never answered by a second model
            # invocation for the same immutable case.
            return self._park_release_policy_message(
                message,
                tuple(semantic_case.candidates),
                exc,
                phase="release_arbiter",
            )

    def _validate_semantic_case_current(self, semantic_case: SemanticReleaseCase) -> None:
        current: list[Any] = []
        for candidate in semantic_case.candidates:
            task = self.registry.get_task(candidate.task_id)
            workstream = self.registry.get_workstream(candidate.workstream_id)
            if (
                task is None
                or workstream is None
                or workstream.task_id != candidate.task_id
                or task.revision != candidate.task_revision
                or workstream.revision != candidate.workstream_revision
                or task.state in {"parked", "accepted"}
                or workstream.state == "parked"
            ):
                raise StaleArbiterDecision("semantic release case revision is stale")
            current.append(candidate)
        revalidate_case_against_candidates(semantic_case, tuple(current))

    def _park_release_policy_message(
        self,
        message: OutboxMessage,
        candidates: Sequence[Any],
        exc: Exception,
        *,
        phase: str,
    ) -> RuntimeWorkerResult:
        with self._mutation_lock:
            for candidate in candidates:
                event_id = _event_id(
                    "release-stalled",
                    f"{phase}:{message.event_id}:{candidate.candidate_id}",
                )
                self.registry.record_input_event_outbox(
                    message_id=_event_id(
                        "release-stalled-receipt",
                        f"{phase}:{message.event_id}:{candidate.candidate_id}",
                    ),
                    source="supervisor-release-policy-worker",
                    input_payload={
                        "policy_event_id": message.event_id,
                        "phase": phase,
                        "candidate_id": candidate.candidate_id,
                        "error_code": _error_code(exc),
                    },
                    event_id=event_id,
                    event_type="release_stalled",
                    event_payload={
                        "schema": "dev-control-plane/release-stalled/v2",
                        "status": "parked",
                        "phase": phase,
                        "error_code": _error_code(exc),
                        "attempt": message.attempts,
                        "candidate_id": candidate.candidate_id,
                        "task_revision": candidate.task_revision,
                        "workstream_revision": candidate.workstream_revision,
                        "pr_head_sha": candidate.pr_head_sha,
                    },
                    outbox_items=(
                        self._release_stall_attention(candidate, _iso(self.clock())),
                        self._dirty_item(event_id, candidate.task_id),
                    ),
                    fence=self.engine.fence,
                    task_id=candidate.task_id,
                    workstream_id=candidate.workstream_id,
                )
                self._park_release_binding(candidate)
            self.registry.ack_outbox(message.event_id, message.claim_token, self.engine.fence)
        return RuntimeWorkerResult(message.kind, message.event_id, "parked", _error_code(exc))

    def _execute_incident_arbiter(self, message: OutboxMessage) -> RuntimeWorkerResult:
        if self.incident_arbiter_executor is None:
            raise SupervisorRuntimeError("incident arbiter executor is unavailable")
        state = _incident_state_from_mapping(_mapping(message.payload, "incident_state"))
        try:
            # Fresh model invocation is outside every registry transaction.
            self._validate_incident_binding(message.payload)
            guard = RuntimeActionGuard(self, message.payload, release=False)
            guard.assert_current()
            decision = self.incident_arbiter_executor(dict(message.payload), guard)
            guard.assert_current()
            if guard.callback_checks < 1:
                raise SupervisorRuntimeError("incident arbiter omitted its generation checkpoint")
            self._validate_incident_binding(message.payload)
            if not isinstance(decision, ArbiterDecision):
                raise SupervisorRuntimeError("incident arbiter returned no typed decision")
            updated = record_incident_arbiter_decision(state, decision)
            decision_event_id = _event_id("incident-arbiter-decision", decision.decision_id)
            application_event_id = _event_id("incident-application", decision.decision_id)
            application_payload = {
                "schema": "dev-control-plane/incident-application/v2",
                "incident_state": _incident_state_to_dict(updated),
                "decision": contract_to_dict(decision),
                "binding": dict(_mapping(message.payload, "binding")),
            }
            remediation = message.payload.get("remediation")
            if remediation is not None:
                application_payload["remediation"] = dict(
                    _mapping_value(remediation, "incident remediation")
                )
            with self._mutation_lock:
                self.registry.record_input_event_outbox(
                    message_id=_event_id("incident-arbiter-receipt", message.event_id),
                    source="supervisor-fresh-incident-arbiter",
                    input_payload={"case_event_id": message.event_id, "decision": contract_to_dict(decision)},
                    event_id=decision_event_id,
                    event_type="incident_policy",
                    event_payload=self._incident_event_payload(
                        updated,
                        action="apply_arbiter_decision",
                        status="arbiter_decided",
                        attempt=updated.failure_count,
                    ),
                    outbox_items=(
                        {
                            "event_id": application_event_id,
                            "kind": "incident_arbiter_application",
                            "payload": application_payload,
                            "task_id": updated.task_id,
                            "coalescible": False,
                            "coalesce_key": None,
                        },
                        self._dirty_item(decision_event_id, updated.task_id),
                    ),
                    fence=self.engine.fence,
                    task_id=updated.task_id,
                    workstream_id=updated.workstream_id,
                    executor_generation=updated.current_executor_generation,
                )
                self.registry.ack_outbox(message.event_id, message.claim_token, self.engine.fence)
            return RuntimeWorkerResult("incident_arbiter_case", message.event_id, "decided", decision.decision_id)
        except Exception as exc:
            return self._park_failed_policy_action(message, state, exc, phase="arbiter")

    def _execute_incident_application(self, message: OutboxMessage) -> RuntimeWorkerResult:
        if self.incident_application_executor is None:
            raise SupervisorRuntimeError("incident application executor is unavailable")
        state = _incident_state_from_mapping(_mapping(message.payload, "incident_state"))
        decision = arbiter_decision_from_mapping(_mapping(message.payload, "decision"))
        result_event_id = _event_id("incident-application-result", message.event_id)
        with self._mutation_lock:
            existing = self.registry.get_event(result_event_id)
            if existing is not None:
                self.registry.ack_outbox(
                    message.event_id, message.claim_token, self.engine.fence
                )
                status = str(existing.get("payload", {}).get("status") or "deduped")
                return RuntimeWorkerResult(
                    message.kind, message.event_id, status, result_event_id
                )
        try:
            # The registered callback selects one bounded deterministic
            # disposition.  It does not claim actuator success: an exact
            # downstream receipt is reconciled separately.
            self._validate_incident_binding(message.payload)
            guard = RuntimeActionGuard(self, message.payload, release=False)
            guard.assert_current()
            receipt = self.incident_application_executor(dict(message.payload), guard)
            guard.assert_current()
            if guard.callback_checks < 2:
                raise SupervisorRuntimeError(
                    "incident application omitted mutation and independent-readback checkpoints"
                )
            self._validate_incident_binding(message.payload)
            _exact_fields(
                receipt,
                {
                    "schema", "applied", "disposition",
                    "verification_identity",
                },
                "incident application disposition",
            )
            disposition = receipt.get("disposition")
            if (
                receipt.get("schema") != INCIDENT_APPLICATION_DISPOSITION_SCHEMA
                or receipt.get("applied") is not True
                or disposition
                not in {
                    "park",
                    "dispatch_release_once",
                    "dispatch_target_lane_once",
                }
            ):
                raise SupervisorRuntimeError("incident application result is incomplete")
            verification_identity = receipt.get("verification_identity")
            if not isinstance(verification_identity, str) or not verification_identity.strip() or len(verification_identity) > 1_000:
                raise SupervisorRuntimeError("incident independent verification identity is missing")
            remediation = message.payload.get("remediation")
            applied = record_arbiter_application(state, decision_id=decision.decision_id).state
            outbox_items: list[dict[str, Any]]
            dispatched_event_id: str | None = None
            dispatched_kind: str | None = None
            persisted_remediation: dict[str, Any] | None = None
            if disposition == "dispatch_release_once":
                if remediation is None:
                    raise SupervisorRuntimeError(
                        "release incident disposition lacks remediation"
                    )
                remediation_raw = self._validated_release_incident_remediation(
                    _mapping_value(remediation, "incident remediation"),
                    state=state,
                )
                persisted_remediation = remediation_raw
                candidate = release_candidate_from_mapping(
                    _mapping(remediation_raw, "candidate")
                )
                self._validate_release_candidate_reservation(candidate, renew=True)
                dispatched_event_id = _event_id(
                    "release-resolution",
                    f"{candidate.candidate_id}:{candidate.pr_head_sha}:arbiter:{decision.decision_id}",
                )
                dispatched_kind = "release_candidate_resolution"
                outbox_items = [
                    {
                        "event_id": dispatched_event_id,
                        "kind": dispatched_kind,
                        "payload": {
                            "schema": "dev-control-plane/release-candidate-resolution/v2",
                            "candidate": asdict(candidate),
                            "source_event_id": remediation_raw["source_event_id"],
                            "remediation_decision_id": decision.decision_id,
                        },
                        "task_id": candidate.task_id,
                        "coalescible": False,
                        "coalesce_key": None,
                    }
                ]
            elif disposition == "dispatch_target_lane_once":
                if remediation is None:
                    raise SupervisorRuntimeError(
                        "target lane incident disposition lacks remediation"
                    )
                remediation_raw = self._validated_target_lane_incident_remediation(
                    _mapping_value(remediation, "incident remediation"),
                    state=state,
                )
                persisted_remediation = remediation_raw
                action = dict(_mapping(remediation_raw, "action"))
                dispatched_event_id = _event_id(
                    "target-lane-incident-dispatch",
                    f"{action['closure_id']}:{decision.decision_id}",
                )
                dispatched_kind = "target_lane_closure"
                outbox_items = [
                    {
                        "event_id": dispatched_event_id,
                        "kind": dispatched_kind,
                        "payload": {
                            "schema": INCIDENT_TARGET_LANE_DISPATCH_SCHEMA,
                            "remediation_decision_id": decision.decision_id,
                            "action": action,
                        },
                        "task_id": state.task_id,
                        "coalescible": False,
                        "coalesce_key": None,
                    }
                ]
            else:
                if remediation is not None:
                    raw_remediation = _mapping_value(
                        remediation, "incident remediation"
                    )
                    if raw_remediation.get("schema") == TARGET_LANE_INCIDENT_REMEDIATION_SCHEMA:
                        persisted_remediation = self._validated_target_lane_incident_remediation(
                            raw_remediation, state=state
                        )
                    else:
                        persisted_remediation = self._validated_release_incident_remediation(
                            raw_remediation, state=state
                        )
                transition = record_independent_verification(applied, passed=False)
                updated = transition.state
                outbox_items = [
                    self._serious_stall_attention(updated, _iso(self.clock()))
                ]
            updated = applied if disposition != "park" else updated
            status = "application_pending" if disposition != "park" else "parked"
            outbox_items.append(self._dirty_item(result_event_id, updated.task_id))
            with self._mutation_lock:
                self.registry.record_input_event_outbox(
                    message_id=_event_id("incident-application-receipt", message.event_id),
                    source="supervisor-incident-application",
                    input_payload={
                        "application_event_id": message.event_id,
                        "decision_id": decision.decision_id,
                        "verification_identity": verification_identity,
                        "disposition": disposition,
                        "dispatched_event_id": dispatched_event_id,
                    },
                    event_id=result_event_id,
                    event_type="incident_policy",
                    event_payload={
                        **self._incident_event_payload(
                            updated,
                            action=(
                                "park_workstream"
                                if disposition == "park"
                                else "verify_arbiter_application"
                            ),
                            status=status,
                            attempt=updated.failure_count,
                        ),
                        "verification_identity": verification_identity,
                        "remediation_decision_id": decision.decision_id,
                        "disposition": disposition,
                        "dispatched_event_id": dispatched_event_id,
                        "dispatched_kind": dispatched_kind,
                        "remediation": persisted_remediation,
                    },
                    outbox_items=tuple(outbox_items),
                    fence=self.engine.fence,
                    task_id=updated.task_id,
                    workstream_id=updated.workstream_id,
                    executor_generation=updated.current_executor_generation,
                )
                if disposition == "park":
                    self._park_incident_binding(updated)
                self.registry.ack_outbox(message.event_id, message.claim_token, self.engine.fence)
            return RuntimeWorkerResult(
                "incident_arbiter_application",
                message.event_id,
                "parked" if disposition == "park" else "dispatched",
                dispatched_event_id or "park_workstream",
            )
        except Exception as exc:
            return self._park_failed_policy_action(message, state, exc, phase="application")

    def _validated_release_incident_remediation(
        self,
        remediation: Mapping[str, Any],
        *,
        state: IncidentState,
    ) -> dict[str, Any]:
        _exact_fields(
            remediation,
            {
                "schema", "kind", "candidate", "source_event_id",
                "prior_action_event_id", "fingerprint",
            },
            "release incident remediation",
        )
        if (
            remediation.get("schema") != "dev-control-plane/release-incident-remediation/v2"
            or remediation.get("kind") != "release_action"
            or remediation.get("fingerprint") != state.fingerprint
        ):
            raise SupervisorRuntimeError("release incident remediation binding changed")
        _machine("source_event_id", remediation.get("source_event_id"))
        _machine("prior_action_event_id", remediation.get("prior_action_event_id"))
        candidate = release_candidate_from_mapping(_mapping(remediation, "candidate"))
        if (
            candidate.task_id != state.task_id
            or candidate.workstream_id != state.workstream_id
            or candidate.task_revision != state.context.passport_revision
        ):
            raise SupervisorRuntimeError("release incident remediation candidate is stale")
        return dict(remediation)

    def _validated_target_lane_incident_remediation(
        self,
        remediation: Mapping[str, Any],
        *,
        state: IncidentState,
    ) -> dict[str, Any]:
        _exact_fields(
            remediation,
            {
                "schema", "kind", "action", "prior_action_event_id",
                "fingerprint",
            },
            "target lane incident remediation",
        )
        if (
            remediation.get("schema") != TARGET_LANE_INCIDENT_REMEDIATION_SCHEMA
            or remediation.get("kind") != "target_lane_closure"
            or remediation.get("fingerprint") != state.fingerprint
        ):
            raise SupervisorRuntimeError(
                "target lane incident remediation binding changed"
            )
        _machine(
            "prior_action_event_id", remediation.get("prior_action_event_id")
        )
        action = _mapping(remediation, "action")
        self._validate_target_lane_closure(action)
        if (
            action.get("task_id") != state.task_id
            or action.get("workstream_id") != state.workstream_id
            or action.get("task_revision") != state.context.passport_revision
        ):
            raise SupervisorRuntimeError(
                "target lane incident remediation action is stale"
            )
        return dict(remediation)

    def _pending_incident_application(
        self, decision_id: str
    ) -> Mapping[str, Any] | None:
        for event in reversed(
            self.registry.list_events(event_types=("incident_policy",))
        ):
            payload = event.get("payload")
            if (
                isinstance(payload, Mapping)
                and payload.get("status") == "application_pending"
                and payload.get("remediation_decision_id") == decision_id
            ):
                return event
        return None

    def _finalize_incident_dispatch(
        self,
        *,
        decision_id: str,
        passed: bool,
        verification_identity: str,
        source_message: OutboxMessage | None = None,
        error_code: str | None = None,
    ) -> RuntimeWorkerResult:
        _machine("remediation_decision_id", decision_id)
        if (
            not isinstance(verification_identity, str)
            or not verification_identity
            or len(verification_identity) > 1_000
        ):
            raise SupervisorRuntimeError(
                "incident actuator verification identity is invalid"
            )
        event_id = _event_id("incident-independent-verification", decision_id)
        with self._mutation_lock:
            existing = self.registry.get_event(event_id)
            if existing is not None:
                payload = existing.get("payload", {})
                state_raw = (
                    payload.get("incident_state")
                    if isinstance(payload, Mapping)
                    else None
                )
                if isinstance(state_raw, Mapping):
                    existing_state = _incident_state_from_mapping(state_raw)
                    if existing_state.parked:
                        self._park_incident_binding(existing_state)
                if source_message is not None:
                    self.registry.ack_outbox(
                        source_message.event_id,
                        source_message.claim_token,
                        self.engine.fence,
                    )
                return RuntimeWorkerResult(
                    source_message.kind if source_message is not None else "incident_policy",
                    source_message.event_id if source_message is not None else event_id,
                    str(payload.get("status") or "deduped"),
                    event_id,
                )
            application = self._pending_incident_application(decision_id)
            if application is None:
                raise SupervisorRuntimeError(
                    "incident actuator receipt has no pending application"
                )
            application_payload = _mapping(application, "payload")
            if not self._incident_application_binding_current(application_payload):
                return self._supersede_incident_dispatch(
                    decision_id=decision_id,
                    application_payload=application_payload,
                    source_message=source_message,
                )
            state = _incident_state_from_mapping(
                _mapping(application_payload, "incident_state")
            )
            if (
                state.arbiter_decision_id != decision_id
                or not state.arbiter_applied
                or state.independent_verification is not None
            ):
                raise SupervisorRuntimeError(
                    "incident actuator receipt binding is not pending verification"
                )
            transition = record_independent_verification(state, passed=passed)
            updated = transition.state
            outbox_items: list[dict[str, Any]] = [
                self._dirty_item(event_id, updated.task_id)
            ]
            if updated.parked:
                outbox_items.insert(
                    0, self._serious_stall_attention(updated, _iso(self.clock()))
                )
            self.registry.record_input_event_outbox(
                message_id=_event_id("incident-independent-verification-receipt", decision_id),
                source="supervisor-incident-reconciler",
                input_payload={
                    "application_event_id": application["event_id"],
                    "decision_id": decision_id,
                    "dispatched_event_id": application_payload.get(
                        "dispatched_event_id"
                    ),
                    "verification_identity": verification_identity,
                    "verification_passed": passed,
                    "error_code": error_code or "none",
                },
                event_id=event_id,
                event_type="incident_policy",
                event_payload={
                    **self._incident_event_payload(
                        updated,
                        action=transition.action,
                        status="resolved" if updated.resolved else "parked",
                        attempt=updated.failure_count,
                        error_code=error_code,
                    ),
                    "verification_identity": verification_identity,
                    "remediation_decision_id": decision_id,
                    "dispatched_event_id": application_payload.get(
                        "dispatched_event_id"
                    ),
                },
                outbox_items=tuple(outbox_items),
                fence=self.engine.fence,
                task_id=updated.task_id,
                workstream_id=updated.workstream_id,
                executor_generation=updated.current_executor_generation,
            )
            if updated.parked:
                self._park_incident_binding(updated)
            if source_message is not None:
                self.registry.ack_outbox(
                    source_message.event_id,
                    source_message.claim_token,
                    self.engine.fence,
                )
        return RuntimeWorkerResult(
            source_message.kind if source_message is not None else "incident_policy",
            source_message.event_id if source_message is not None else event_id,
            "resolved" if passed else "parked",
            event_id,
        )

    def _fail_incident_dispatch(
        self,
        message: OutboxMessage,
        decision_id: str,
        exc: Exception,
        *,
        verification_identity: str,
    ) -> RuntimeWorkerResult:
        return self._finalize_incident_dispatch(
            decision_id=decision_id,
            passed=False,
            verification_identity=verification_identity,
            source_message=message,
            error_code=_error_code(exc),
        )

    def _park_failed_policy_action_from_dispatch(
        self, message: OutboxMessage, exc: Exception
    ) -> RuntimeWorkerResult:
        decision_id = message.payload.get("remediation_decision_id")
        if isinstance(decision_id, str) and _MACHINE_RE.fullmatch(decision_id):
            return self._fail_incident_dispatch(
                message,
                decision_id,
                exc,
                verification_identity="invalid-target-lane-dispatch-envelope",
            )
        raise SupervisorRuntimeError(
            "invalid target lane dispatch is not bound to an incident decision"
        ) from exc

    def _reconcile_incident_applications(self) -> None:
        """Fold exact actuator receipts into pending one-shot applications."""

        events = self.registry.list_events(event_types=("incident_policy",))
        latest_states: dict[tuple[str, str], IncidentState] = {}
        for event in events:
            payload = event.get("payload")
            state_raw = payload.get("incident_state") if isinstance(payload, Mapping) else None
            if not isinstance(state_raw, Mapping):
                continue
            state = _incident_state_from_mapping(state_raw)
            latest_states[(state.task_id, state.workstream_id)] = state
        for state in latest_states.values():
            task = self.registry.get_task(state.task_id)
            if (
                state.parked
                and task is not None
                and task.revision == state.context.passport_revision
            ):
                # Repair the narrow crash window between the durable failed
                # verification and the idempotent aggregate-state transition.
                # Historical incidents never re-park a newer Passport.
                self._park_incident_binding(state)
        for event in events:
            payload = event.get("payload")
            if (
                not isinstance(payload, Mapping)
                or payload.get("status") != "application_pending"
            ):
                continue
            decision_id = payload.get("remediation_decision_id")
            if not isinstance(decision_id, str):
                continue
            if self.registry.get_event(
                _event_id("incident-independent-verification", decision_id)
            ) is not None:
                continue
            if self.registry.get_event(
                _event_id("incident-application-superseded", decision_id)
            ) is not None:
                continue
            if not self._incident_application_binding_current(payload):
                self._supersede_incident_dispatch(
                    decision_id=decision_id,
                    application_payload=payload,
                    source_message=None,
                )
                continue
            evidence = self._incident_dispatch_success_evidence(payload)
            if evidence is not None:
                self._finalize_incident_dispatch(
                    decision_id=decision_id,
                    passed=True,
                    verification_identity=evidence,
                )
                continue
            dispatched_event_id = payload.get("dispatched_event_id")
            if not isinstance(dispatched_event_id, str):
                continue
            records = tuple(
                item
                for item in self.registry.list_outbox_records()
                if item.get("event_id") == dispatched_event_id
            )
            if len(records) == 1 and records[0].get("state") == "superseded":
                self._finalize_incident_dispatch(
                    decision_id=decision_id,
                    passed=False,
                    verification_identity="incident-dispatch-superseded",
                    error_code="stale_dispatch_binding",
                )

    def _incident_application_binding_current(
        self, application_payload: Mapping[str, Any]
    ) -> bool:
        state = _incident_state_from_mapping(
            _mapping(application_payload, "incident_state")
        )
        task = self.registry.get_task(state.task_id)
        workstream = self.registry.get_workstream(state.workstream_id)
        executor = self.registry.current_executor(state.task_id, state.workstream_id)
        if (
            task is None
            or workstream is None
            or executor is None
            or task.revision != state.context.passport_revision
            or executor.executor_generation != state.current_executor_generation
        ):
            return False
        remediation = application_payload.get("remediation")
        if not isinstance(remediation, Mapping):
            return False
        if remediation.get("schema") == "dev-control-plane/release-incident-remediation/v2":
            candidate = release_candidate_from_mapping(
                _mapping(remediation, "candidate")
            )
            return (
                candidate.task_id == task.task_id
                and candidate.workstream_id == workstream.workstream_id
                and candidate.task_revision == task.revision
                and candidate.workstream_revision == workstream.revision
            )
        if remediation.get("schema") == TARGET_LANE_INCIDENT_REMEDIATION_SCHEMA:
            action = _mapping(remediation, "action")
            return (
                action.get("task_id") == task.task_id
                and action.get("workstream_id") == workstream.workstream_id
                and action.get("task_revision") == task.revision
                and action.get("workstream_revision") == workstream.revision
            )
        return False

    def _supersede_incident_dispatch(
        self,
        *,
        decision_id: str,
        application_payload: Mapping[str, Any],
        source_message: OutboxMessage | None,
    ) -> RuntimeWorkerResult:
        state = _incident_state_from_mapping(
            _mapping(application_payload, "incident_state")
        )
        event_id = _event_id("incident-application-superseded", decision_id)
        with self._mutation_lock:
            if self.registry.get_event(event_id) is None:
                self.registry.record_input_event_outbox(
                    message_id=_event_id(
                        "incident-application-superseded-receipt", decision_id
                    ),
                    source="supervisor-incident-reconciler",
                    input_payload={
                        "decision_id": decision_id,
                        "dispatched_event_id": application_payload.get(
                            "dispatched_event_id"
                        ),
                    },
                    event_id=event_id,
                    event_type="incident_policy",
                    event_payload={
                        **self._incident_event_payload(
                            state,
                            action="verify_arbiter_application",
                            status="application_superseded",
                            attempt=state.failure_count,
                            error_code="stale_dispatch_binding",
                        ),
                        "remediation_decision_id": decision_id,
                        "dispatched_event_id": application_payload.get(
                            "dispatched_event_id"
                        ),
                    },
                    outbox_items=(self._dirty_item(event_id, state.task_id),),
                    fence=self.engine.fence,
                    task_id=state.task_id,
                    workstream_id=state.workstream_id,
                    executor_generation=state.current_executor_generation,
                )
            if source_message is not None:
                self.registry.ack_outbox(
                    source_message.event_id,
                    source_message.claim_token,
                    self.engine.fence,
                )
        return RuntimeWorkerResult(
            source_message.kind if source_message is not None else "incident_policy",
            source_message.event_id if source_message is not None else event_id,
            "stale_discarded",
            event_id,
        )

    def _incident_dispatch_success_evidence(
        self, application_payload: Mapping[str, Any]
    ) -> str | None:
        decision_id = str(application_payload.get("remediation_decision_id") or "")
        disposition = application_payload.get("disposition")
        dispatched_event_id = application_payload.get("dispatched_event_id")
        remediation = application_payload.get("remediation")
        if not isinstance(dispatched_event_id, str) or not isinstance(
            remediation, Mapping
        ):
            return None
        if disposition == "dispatch_release_once":
            candidate = release_candidate_from_mapping(
                _mapping(remediation, "candidate")
            )
            proof_event_id = _event_id(
                "release-candidate-resolved", dispatched_event_id
            )
            proof = self.registry.get_event(proof_event_id)
            proof_candidate = (
                proof.get("payload", {}).get("candidate")
                if proof is not None and proof.get("event_type") == "release_proof_only"
                else None
            )
            if (
                isinstance(proof_candidate, Mapping)
                and proof_candidate.get("candidate_id") == candidate.candidate_id
                and proof_candidate.get("task_id") == candidate.task_id
                and proof_candidate.get("workstream_id") == candidate.workstream_id
                and proof_candidate.get("pr_head_sha") == candidate.pr_head_sha
                and proof.get("payload", {}).get("proof_only") is True
            ):
                return f"release-proof-only:{proof_event_id}"
            matching_actions = tuple(
                item
                for item in self.registry.list_outbox_records(
                    kinds=("release_action",), states=("delivered",)
                )
                if item.get("payload", {}).get("remediation_decision_id")
                == decision_id
            )
            if len(matching_actions) != 1:
                return None
            action_event_id = str(matching_actions[0]["event_id"])
            result = self.registry.get_event(
                _event_id("release-result", action_event_id)
            )
            receipt = (
                result.get("payload", {}).get("receipt")
                if result is not None and result.get("event_type") == "release_completed"
                else None
            )
            if (
                isinstance(receipt, Mapping)
                and result.get("payload", {}).get("release_action_event_id")
                == action_event_id
                and receipt.get("status") == "passed"
                and receipt.get("candidate_id") == candidate.candidate_id
                and receipt.get("task_id") == candidate.task_id
                and receipt.get("workstream_id") == candidate.workstream_id
                and receipt.get("pr_head_sha") == candidate.pr_head_sha
            ):
                return f"release-completed:{result['event_id']}"
            return None
        if disposition == "dispatch_target_lane_once":
            action = _mapping(remediation, "action")
            records = tuple(
                item
                for item in self.registry.list_outbox_records(
                    kinds=("target_lane_closure",), states=("delivered",)
                )
                if item.get("event_id") == dispatched_event_id
                and item.get("payload", {}).get("remediation_decision_id")
                == decision_id
            )
            if len(records) != 1:
                return None
            result = self.registry.get_event(
                _event_id(
                    "target-lane-closure-result", str(action["closure_id"])
                )
            )
            result_payload = result.get("payload") if result is not None else None
            receipt = (
                result_payload.get("receipt")
                if isinstance(result_payload, Mapping)
                else None
            )
            if (
                result is not None
                and result.get("event_type") == "target_lane_closure_completed"
                and isinstance(result_payload, Mapping)
                and result_payload.get("action") == dict(action)
                and result_payload.get("remediation_decision_id") == decision_id
                and isinstance(receipt, Mapping)
                and receipt.get("closure_id") == action["closure_id"]
                and receipt.get("status") in {"released", "parked"}
            ):
                return f"target-lane-completed:{result['event_id']}"
        return None

    def _park_failed_policy_action(
        self,
        message: OutboxMessage,
        state: IncidentState,
        exc: Exception,
        *,
        phase: str,
    ) -> RuntimeWorkerResult:
        event_id = _event_id(f"incident-{phase}-failed", message.event_id)
        with self._mutation_lock:
            self.registry.record_input_event_outbox(
                message_id=_event_id(f"incident-{phase}-failure-receipt", message.event_id),
                source=f"supervisor-incident-{phase}",
                input_payload={"event_id": message.event_id, "error_code": _error_code(exc)},
                event_id=event_id,
                event_type="incident_policy",
                event_payload={
                    **self._incident_event_payload(
                        state,
                        action="park_workstream",
                        status=f"{phase}_failed_fail_closed",
                        attempt=state.failure_count,
                        error_code=_error_code(exc),
                    ),
                    "incident_state": _incident_state_to_dict(state),
                },
                outbox_items=(
                    self._serious_stall_attention(state, _iso(self.clock())),
                    self._dirty_item(event_id, state.task_id),
                ),
                fence=self.engine.fence,
                task_id=state.task_id,
                workstream_id=state.workstream_id,
                executor_generation=state.current_executor_generation,
            )
            self._park_incident_binding(state)
            self.registry.ack_outbox(message.event_id, message.claim_token, self.engine.fence)
        return RuntimeWorkerResult(message.kind, message.event_id, "parked", _error_code(exc))

    def _process_thread_start(self, message: OutboxMessage) -> RuntimeWorkerResult:
        try:
            payload = self._validated_thread_start_payload(message.payload)
            passport = task_passport_from_mapping(payload["passport"])
            workstream = workstream_from_mapping(payload["workstream"])
            self._assert_workspace_binding(
                passport.task_id,
                workstream.workstream_id,
                Path(str(payload["cwd"])),
            )
            with self._mutation_lock:
                existing = self.registry.current_executor(passport.task_id, workstream.workstream_id)
            if existing is not None:
                with self._mutation_lock:
                    self.registry.ack_outbox(message.event_id, message.claim_token, self.engine.fence)
                return RuntimeWorkerResult("codex_thread_start", message.event_id, "deduped", existing.thread_id)

            started = payload["started_thread"]
            fresh_thread_id: str | None = None
            if started is None:
                if payload["start_intent"] is not None:
                    raise CodexAmbiguousOutcomeError(
                        "a prior unreceipted thread/start may have created an executor"
                    )
                client = self._client()
                client.connect()
                payload["start_intent"] = self._new_start_intent()
                with self._mutation_lock:
                    message = self.registry.replace_claimed_outbox_payload(
                        message.event_id,
                        message.claim_token,
                        payload,
                        self.engine.fence,
                    )
                try:
                    identity = client.start_thread(cwd=payload["cwd"], ephemeral=False)
                except Exception as exc:
                    raise CodexAmbiguousOutcomeError(
                        "thread/start failed after its durable call intent"
                    ) from exc
                started = self._started_identity(identity)
                persisted = dict(payload)
                persisted["started_thread"] = started
                try:
                    with self._mutation_lock:
                        message = self.registry.replace_claimed_outbox_payload(
                            message.event_id,
                            message.claim_token,
                            persisted,
                            self.engine.fence,
                        )
                except Exception as exc:
                    raise CodexAmbiguousOutcomeError(
                        "started executor identity could not be durably receipted"
                    ) from exc
                self._resumed_threads[identity.thread_id] = client.connection_epoch
                fresh_thread_id = identity.thread_id
            else:
                thread_id = str(started["thread_id"])
                client = self._client(extra_owned=(thread_id,))
                self._ensure_thread_resumed(client, thread_id)

            executor = ExecutorIdentity(
                thread_id=str(started["thread_id"]),
                host_id=str(started["host_id"]),
                model=str(started["model"]),
                reasoning=str(started["reasoning"]),
            )
            bound_workstream = replace(workstream, executor=executor)
            registration_message = _event_id("codex-registration", payload["message_id"])
            with self._mutation_lock:
                self.engine.register(
                    passport,
                    bound_workstream,
                    message_id=registration_message,
                    source="codex-thread-start-worker",
                )
                self.registry.ack_outbox(message.event_id, message.claim_token, self.engine.fence)
                if fresh_thread_id is not None:
                    self._fresh_thread_epochs[fresh_thread_id] = client.connection_epoch
            self._last_codex_error = None
            return RuntimeWorkerResult("codex_thread_start", message.event_id, "registered", executor.thread_id)
        except Exception as exc:
            self._last_codex_error = _error_code(exc)
            return self._handle_unbound_start_failure(message, exc)

    def _process_successor(self, message: OutboxMessage) -> RuntimeWorkerResult:
        proof_event_id = _event_id("successor-proof", message.event_id)
        commit_grants: tuple[LockGrant, ...] = ()
        commit_lease: _ExecutionReservationLease | None = None
        try:
            payload = self._validated_successor_payload(message.payload)
            task_record = self.registry.get_task(str(payload["task_id"]))
            if task_record is None:
                raise SupervisorRuntimeError("successor task disappeared")
            require_passport_action(
                task_passport_from_mapping(task_record.passport),
                "codex_workspace_mutation",
            )
            with self._mutation_lock:
                current = self.registry.current_executor(payload["task_id"], payload["workstream_id"])
            if current is None:
                raise SupervisorRuntimeError("successor predecessor is missing")
            successor_generation = int(payload["successor_generation"])
            if current.executor_generation not in {payload["predecessor_generation"], successor_generation}:
                raise SupervisorRuntimeError("successor binding is stale")

            started = payload["started_thread"]
            if started is None:
                if payload["start_intent"] is not None:
                    raise CodexAmbiguousOutcomeError(
                        "a prior unreceipted successor thread/start may have created an executor"
                    )
                client = self._client()
                client.connect()
                payload["start_intent"] = self._new_start_intent()
                with self._mutation_lock:
                    message = self.registry.replace_claimed_outbox_payload(
                        message.event_id,
                        message.claim_token,
                        payload,
                        self.engine.fence,
                    )
                try:
                    identity = client.start_thread(cwd=payload["cwd"], ephemeral=False)
                except Exception as exc:
                    raise CodexAmbiguousOutcomeError(
                        "successor thread/start failed after its durable call intent"
                    ) from exc
                started = self._started_identity(identity)
                payload["started_thread"] = started
                try:
                    with self._mutation_lock:
                        message = self.registry.replace_claimed_outbox_payload(
                            message.event_id,
                            message.claim_token,
                            payload,
                            self.engine.fence,
                        )
                except Exception as exc:
                    raise CodexAmbiguousOutcomeError(
                        "successor identity could not be durably receipted"
                    ) from exc
                self._resumed_threads[identity.thread_id] = client.connection_epoch
                self._fresh_thread_epochs[identity.thread_id] = client.connection_epoch
            else:
                thread_id = str(started["thread_id"])
                client = self._client(extra_owned=(thread_id,))
                self._ensure_thread_resumed(client, thread_id)

            proof_raw = payload["proof_contract"]
            if proof_raw is None:
                proof_intent = payload["proof_intent"]
                if proof_intent is not None:
                    snapshot = client.read_thread_snapshot(str(started["thread_id"]), include_turns=True)
                    if _thread_turn_ids(snapshot) - set(proof_intent["baseline_turn_ids"]):
                        raise CodexAmbiguousOutcomeError(
                            "a prior unreceipted successor proof created a turn"
                        )
                    payload["proof_intent"] = None
                    with self._mutation_lock:
                        message = self.registry.replace_claimed_outbox_payload(
                            message.event_id,
                            message.claim_token,
                            payload,
                            self.engine.fence,
                        )
                proof_intent, fresh_baseline, proof_connection_epoch = self._new_call_intent_for_thread(
                    client,
                    str(started["thread_id"]),
                )
                payload["proof_intent"] = proof_intent
                with self._mutation_lock:
                    message = self.registry.replace_claimed_outbox_payload(
                        message.event_id,
                        message.claim_token,
                        payload,
                        self.engine.fence,
                    )
                if fresh_baseline:
                    self._consume_fresh_thread_baseline(
                        client,
                        str(started["thread_id"]),
                        required_connection_epoch=proof_connection_epoch,
                    )
                original = _mapping(payload, "original_followup")
                grants, execution_lease = self._start_execution_lease(
                    original,
                    thread_id=str(started["thread_id"]),
                )
                try:
                    proof_turn = client.run_turn(
                        str(started["thread_id"]),
                        self._successor_proof_prompt(payload),
                        output_contract="checkpoint",
                        expected_task_id=payload["task_id"],
                        expected_workstream_id=payload["workstream_id"],
                        cwd=payload["cwd"],
                        required_connection_epoch=proof_connection_epoch,
                    )
                    execution_lease.assert_current()
                    if not isinstance(proof_turn.contract, CodexCheckpoint):
                        raise SupervisorRuntimeError("successor proof did not return a checkpoint")
                    proof_raw = proof_turn.contract.to_dict()
                    payload["proof_contract"] = proof_raw
                    with self._mutation_lock:
                        execution_lease.assert_current()
                        message = self.registry.replace_claimed_outbox_payload(
                            message.event_id,
                            message.claim_token,
                            payload,
                            self.engine.fence,
                        )
                        # Validate the exact JSON-normalized durable receipt;
                        # dataclass tuples are arrays after persistence.
                        proof_raw = dict(
                            _mapping(message.payload, "proof_contract")
                        )
                finally:
                    execution_lease.stop()
                    self._release_execution_locks(grants)
            proof = validate_checkpoint_payload(
                proof_raw,
                expected_task_id=payload["task_id"],
                expected_workstream_id=payload["workstream_id"],
            )
            successor_identity = ExecutorIdentity(
                str(started["thread_id"]),
                str(started["host_id"]),
                str(started["model"]),
                str(started["reasoning"]),
            )
            commit_grants, commit_lease = self._start_execution_lease(
                _mapping(payload, "original_followup"),
                thread_id=successor_identity.thread_id,
            )
            commit_lease.assert_current()
            thread_grant = next(item for item in commit_grants if item.kind == "thread")
            with self._mutation_lock:
                commit_lease.assert_current()
                current = self.registry.current_executor(payload["task_id"], payload["workstream_id"])
                if current is None:
                    raise SupervisorRuntimeError("successor predecessor disappeared")
                task_now = self.registry.get_task(payload["task_id"])
                workstream_now = self.registry.get_workstream(payload["workstream_id"])
                corrective = (
                    task_now is not None
                    and workstream_now is not None
                    and task_now.state == "recovering"
                    and workstream_now.state == "recovering"
                )
                if corrective:
                    self._commit_corrective_successor(
                        message,
                        payload,
                        proof,
                        proof_raw,
                        successor_identity,
                        proof_event_id,
                        task_now,
                        workstream_now,
                    )
                else:
                    self._commit_standard_successor(
                        message,
                        payload,
                        proof,
                        proof_raw,
                        successor_identity,
                        proof_event_id,
                        thread_grant,
                    )
            commit_lease.stop()
            self._release_execution_locks(commit_grants)
            commit_lease = None
            commit_grants = ()
            return RuntimeWorkerResult("codex_successor_start", message.event_id, "successor_proven", proof_event_id)
        except Exception as exc:
            if commit_lease is not None:
                commit_lease.stop()
                self._release_execution_locks(commit_grants)
            self._last_codex_error = _error_code(exc)
            return self._handle_worker_failure(
                message,
                exc,
                task_id=str(message.payload.get("task_id") or message.task_id or "unknown-task"),
                workstream_id=str(message.payload.get("workstream_id") or "unknown-workstream"),
            )

    def _commit_corrective_successor(
        self,
        message: OutboxMessage,
        payload: Mapping[str, Any],
        proof: CodexCheckpoint,
        proof_raw: Mapping[str, Any],
        successor_identity: ExecutorIdentity,
        proof_event_id: str,
        task: Any,
        workstream: Any,
    ) -> None:
        successor_generation = int(payload["successor_generation"])
        state = self._latest_incident_state(
            str(payload["task_id"]),
            str(payload["workstream_id"]),
            str(payload["causal_fingerprint"]),
        )
        if state is None:
            raise SupervisorRuntimeError("corrective successor lacks durable incident state")
        proven = record_successor_proof(
            state,
            successor_generation=successor_generation,
            proof_event_id=proof_event_id,
        )
        next_task_revision = task.revision + 1
        next_workstream_revision = workstream.revision + 1
        canonical_proof = Checkpoint(
            checkpoint_id=_event_id("checkpoint", proof_event_id),
            event_id=proof_event_id,
            task_id=str(payload["task_id"]),
            task_revision=next_task_revision,
            workstream_id=str(payload["workstream_id"]),
            workstream_revision=next_workstream_revision,
            executor_generation=successor_generation,
            executor=successor_identity,
            progress_stage=proof.progress_percent,
            delta_ru=proof.delta,
            current_ru=proof.current_action,
            evidence=tuple(proof.evidence) + ("successor_startup_proof", "recovery_proven"),
            created_at=_iso(self.clock()),
        )
        canonical_payload = contract_to_dict(canonical_proof)
        checkpoint_event_payload = {
            "schema": "dev-control-plane/supervisor-event/v2",
            "contract": canonical_payload,
            "progress": canonical_proof.progress_stage,
            "delta_ru": canonical_proof.delta_ru,
            "current_ru": canonical_proof.current_ru,
            "objective_invalidated": False,
            "task_revision": next_task_revision,
            "workstream_revision": next_workstream_revision,
            "executor_generation": successor_generation,
            "created_at": canonical_proof.created_at,
        }
        incident_event_id = _event_id("recovery-proven", message.event_id)
        incident_payload = self._incident_event_payload(
            proven,
            action="await_successor_proof",
            status="recovery_proven",
            attempt=proven.failure_count,
        )
        followup_payload = dict(payload["original_followup"])
        followup_payload.update(
            {
                "task_revision": next_task_revision,
                "workstream_revision": next_workstream_revision,
                "executor_generation": successor_generation,
                "thread_id": successor_identity.thread_id,
                "host_id": successor_identity.host_id,
                "model": successor_identity.model,
                "reasoning": successor_identity.reasoning,
                "causal_fingerprint": payload["causal_fingerprint"],
                "causal_binding": payload["causal_binding"],
                "message_id": _event_id("successor-followup-message", message.event_id),
            }
        )
        followup_event_id = _event_id("successor-followup", message.event_id)
        self.registry.complete_corrective_successor(
            task_id=str(payload["task_id"]),
            workstream_id=str(payload["workstream_id"]),
            expected_task_revision=task.revision,
            expected_workstream_generation=workstream.generation,
            expected_workstream_revision=workstream.revision,
            predecessor_generation=int(payload["predecessor_generation"]),
            successor_generation=successor_generation,
            successor=successor_identity,
            checkpoint_digest=_sha256(
                json.dumps(proof_raw, sort_keys=True, separators=(",", ":"))
            ),
            proof_event_id=proof_event_id,
            checkpoint_event_payload=checkpoint_event_payload,
            incident_event_id=incident_event_id,
            incident_event_payload=incident_payload,
            followup_event_id=followup_event_id,
            followup_payload=followup_payload,
            projection_event_id=_event_id("dirty", incident_event_id),
            claimed_outbox_event_id=message.event_id,
            claim_token=message.claim_token,
            fence=self.engine.fence,
        )

    def _commit_standard_successor(
        self,
        message: OutboxMessage,
        payload: Mapping[str, Any],
        proof: CodexCheckpoint,
        proof_raw: Mapping[str, Any],
        successor_identity: ExecutorIdentity,
        proof_event_id: str,
        thread_grant: LockGrant,
    ) -> None:
        successor_generation = int(payload["successor_generation"])
        current = self.registry.current_executor(
            str(payload["task_id"]), str(payload["workstream_id"])
        )
        if current is None:
            raise SupervisorRuntimeError("successor predecessor disappeared")
        if current.executor_generation == payload["predecessor_generation"]:
            try:
                self.registry.activate_successor(
                    str(payload["task_id"]),
                    str(payload["workstream_id"]),
                    successor_generation,
                    proof_event_id=proof_event_id,
                    fence=self.engine.fence,
                )
            except Exception:
                self.registry.register_executor(
                    str(payload["task_id"]),
                    str(payload["workstream_id"]),
                    successor_identity,
                    expected_current_generation=int(payload["predecessor_generation"]),
                    checkpoint_digest=_sha256(
                        json.dumps(proof_raw, sort_keys=True, separators=(",", ":"))
                    ),
                    fence=self.engine.fence,
                )
                self.registry.activate_successor(
                    str(payload["task_id"]),
                    str(payload["workstream_id"]),
                    successor_generation,
                    proof_event_id=proof_event_id,
                    fence=self.engine.fence,
                )
        activated = self.registry.current_executor(
            str(payload["task_id"]), str(payload["workstream_id"])
        )
        if activated is None or activated.executor_generation != successor_generation:
            raise SupervisorRuntimeError("successor failed to activate after proof")
        canonical_proof = Checkpoint(
            checkpoint_id=_event_id("checkpoint", proof_event_id),
            event_id=proof_event_id,
            task_id=str(payload["task_id"]),
            task_revision=int(payload["task_revision"]),
            workstream_id=str(payload["workstream_id"]),
            workstream_revision=int(payload["workstream_revision"]),
            executor_generation=successor_generation,
            executor=successor_identity,
            progress_stage=proof.progress_percent,
            delta_ru=proof.delta,
            current_ru=proof.current_action,
            evidence=tuple(proof.evidence) + ("successor_startup_proof",),
            created_at=_iso(self.clock()),
        )
        self.engine.import_checkpoint(
            canonical_proof,
            message_id=_event_id("successor-proof-receipt", message.event_id),
            source="codex-successor-worker",
            preheld_thread_lock=thread_grant,
        )
        state = self._latest_incident_state(
            str(payload["task_id"]),
            str(payload["workstream_id"]),
            str(payload["causal_fingerprint"]),
        )
        if state is None:
            raise SupervisorRuntimeError("successor lacks durable incident state")
        proven = record_successor_proof(
            state,
            successor_generation=successor_generation,
            proof_event_id=proof_event_id,
        )
        incident_event_id = _event_id("incident-successor-proven", message.event_id)
        followup_payload = dict(payload["original_followup"])
        followup_payload.update(
            {
                "executor_generation": successor_generation,
                "thread_id": successor_identity.thread_id,
                "host_id": successor_identity.host_id,
                "model": successor_identity.model,
                "reasoning": successor_identity.reasoning,
                "causal_fingerprint": payload["causal_fingerprint"],
                "causal_binding": payload["causal_binding"],
                "message_id": _event_id("successor-followup-message", message.event_id),
            }
        )
        followup_event_id = _event_id("successor-followup", message.event_id)
        self.registry.record_input_event_outbox(
            message_id=_event_id("successor-state-receipt", message.event_id),
            source="codex-successor-worker",
            input_payload={"successor_event_id": message.event_id, "proof_event_id": proof_event_id},
            event_id=incident_event_id,
            event_type="incident_policy",
            event_payload=self._incident_event_payload(
                proven,
                action="await_successor_proof",
                status="successor_proven",
                attempt=proven.failure_count,
            ),
            outbox_items=(
                {
                    "event_id": followup_event_id,
                    "kind": "codex_followup",
                    "payload": followup_payload,
                    "task_id": payload["task_id"],
                    "coalescible": False,
                    "coalesce_key": None,
                },
                self._dirty_item(incident_event_id, str(payload["task_id"])),
            ),
            fence=self.engine.fence,
            task_id=str(payload["task_id"]),
            workstream_id=str(payload["workstream_id"]),
            executor_generation=successor_generation,
        )
        self.registry.ack_outbox(message.event_id, message.claim_token, self.engine.fence)

    def _process_followup(self, message: OutboxMessage) -> RuntimeWorkerResult:
        result_event_id = _event_id("codex-result", message.event_id)
        failure_event_id = _event_id("qualification-canary-failed", message.event_id)
        existing_result: Mapping[str, Any] | None = None
        existing_turn_receipts: tuple[Mapping[str, Any], ...] = ()
        with self._mutation_lock:
            existing_result = self.registry.get_event(result_event_id)
            if existing_result is not None:
                existing_turn_receipts = self._turn_receipts_for_followup(
                    message,
                    result_event_id,
                )
            if (
                existing_result is not None
                and len(existing_turn_receipts) == 1
                and isinstance(message.payload.get("call_intent"), Mapping)
                and message.payload.get("model_attempt_count") == 1
            ):
                self.registry.ack_outbox(message.event_id, message.claim_token, self.engine.fence)
                return RuntimeWorkerResult("codex_followup", message.event_id, "deduped", result_event_id)
            if (
                message.payload.get("call_policy") == CALL_POLICY_SINGLE_ATTEMPT_CANARY
                and self.registry.get_event(failure_event_id) is not None
            ):
                # Defensive recovery for a legacy/simulated split receipt: once
                # the durable stop event exists, this outbox item may only be
                # acknowledged.  It must never reach snapshot recovery or a
                # new model call.
                self.registry.ack_outbox(message.event_id, message.claim_token, self.engine.fence)
                return RuntimeWorkerResult(
                    "codex_followup",
                    message.event_id,
                    "qualification_failed",
                    failure_event_id,
                )
        try:
            payload = self._validated_followup_payload(message.payload)
            if payload["call_policy"] == CALL_POLICY_SINGLE_ATTEMPT_CANARY:
                self._assert_canary_worker_budget(message, payload)
            task, workstream, executor = self._validated_current_binding(payload)
            if existing_result is not None and (
                payload["call_intent"] is None
                or payload["model_attempt_count"] != 1
            ):
                raise CodexAmbiguousOutcomeError(
                    "persisted Codex result lacks its exact single-call intent receipt"
                )
            if existing_result is not None and len(existing_turn_receipts) > 1:
                raise CodexAmbiguousOutcomeError(
                    "persisted Codex result has multiple structural turn receipts"
                )
            single_attempt_canary = (
                payload["call_policy"] == CALL_POLICY_SINGLE_ATTEMPT_CANARY
            )
            preactivation_single_attempt_canary = (
                single_attempt_canary and self._preactivation_qualification_mode
            )
            client = self._client(extra_owned=(executor.thread_id,))
            required_fresh_epoch: int | None = None
            if preactivation_single_attempt_canary:
                required_fresh_epoch = self._preactivation_canary_epoch(
                    client,
                    executor.thread_id,
                    executor.executor_generation,
                )
            else:
                self._ensure_thread_resumed(client, executor.thread_id)
            if message.attempts > 2:
                raise CodexAmbiguousOutcomeError("follow-up exceeded its single bounded retry")
            call_intent = payload["call_intent"]
            turn_connection_epoch: int | None = None
            if call_intent is not None and payload["model_attempt_count"] < 1:
                raise CodexAmbiguousOutcomeError(
                    "durable follow-up call intent lacks its model-attempt receipt"
                )
            if call_intent is None:
                if (
                    payload["call_policy"] == CALL_POLICY_SINGLE_ATTEMPT_CANARY
                    and payload["model_attempt_count"] >= 1
                ):
                    raise CodexAmbiguousOutcomeError(
                        "single-attempt qualification canary model-call budget is exhausted"
                    )
                intent, fresh_baseline, turn_connection_epoch = self._new_call_intent_for_thread(
                    client,
                    executor.thread_id,
                    required_fresh_epoch=required_fresh_epoch,
                )
                payload["call_intent"] = intent
                payload["model_attempt_count"] = int(payload["model_attempt_count"]) + 1
                if preactivation_single_attempt_canary:
                    if not fresh_baseline or turn_connection_epoch is None:
                        raise CodexAmbiguousOutcomeError(
                            "preactivation canary lost its exact empty start epoch"
                        )
                    with client.pin_connection_epoch(turn_connection_epoch):
                        with self._mutation_lock:
                            message = self.registry.replace_claimed_outbox_payload(
                                message.event_id,
                                message.claim_token,
                                payload,
                                self.engine.fence,
                            )
                        self._consume_fresh_thread_baseline(
                            client,
                            executor.thread_id,
                            required_connection_epoch=turn_connection_epoch,
                        )
                else:
                    with self._mutation_lock:
                        message = self.registry.replace_claimed_outbox_payload(
                            message.event_id,
                            message.claim_token,
                            payload,
                            self.engine.fence,
                        )
                    if fresh_baseline:
                        self._consume_fresh_thread_baseline(
                            client,
                            executor.thread_id,
                            required_connection_epoch=turn_connection_epoch,
                        )
            prompt = self._bound_prompt(payload)
            # This is intentionally outside ``_mutation_lock`` and outside every
            # registry method. Codex may run for hours while lease renewal and
            # projection maintenance continue in the same sole-writer process.
            grants, execution_lease = self._start_execution_lease(payload)
            recovered_from_snapshot = call_intent is not None
            try:
                if call_intent is not None:
                    try:
                        turn = client.recover_lost_turn_receipt(
                            executor.thread_id,
                            baseline_turn_ids=call_intent["baseline_turn_ids"],
                            output_contract=payload["output_contract"],
                            expected_task_id=payload["task_id"],
                            expected_workstream_id=payload["workstream_id"],
                            expected_contract_generation=int(
                                call_intent["supervisor_generation"]
                            ),
                        )
                        self._ensure_thread_resumed(client, executor.thread_id)
                    except CodexAmbiguousOutcomeError:
                        raise
                    except Exception as exc:
                        raise CodexAmbiguousOutcomeError(
                            "persisted follow-up turn could not be recovered unambiguously"
                        ) from exc
                else:
                    try:
                        turn = client.run_turn(
                            executor.thread_id,
                            prompt,
                            output_contract=payload["output_contract"],
                            expected_task_id=payload["task_id"],
                            expected_workstream_id=payload["workstream_id"],
                            cwd=payload["cwd"],
                            required_connection_epoch=turn_connection_epoch,
                        )
                    except Exception as exc:
                        if (
                            payload["call_policy"] == CALL_POLICY_STANDARD
                            and not isinstance(exc, CodexAmbiguousOutcomeError)
                        ):
                            cleared = dict(message.payload)
                            cleared["call_intent"] = None
                            with self._mutation_lock:
                                message = self.registry.replace_claimed_outbox_payload(
                                    message.event_id,
                                    message.claim_token,
                                    cleared,
                                    self.engine.fence,
                                )
                        raise
                if self._after_turn_completed is not None:
                    self._after_turn_completed(message, turn)
                # A lost/expired reservation makes even valid typed output
                # unusable: another workspace mutator may have overlapped.
                execution_lease.assert_current()
                canonical = self._canonical_result(
                    turn,
                    payload,
                    task_revision=task.revision,
                    workstream_revision=workstream.revision,
                    executor_generation=executor.executor_generation,
                    executor=ExecutorIdentity(
                        executor.thread_id, executor.host_id, executor.model, executor.reasoning
                    ),
                    result_event_id=result_event_id,
                    created_at_override=self._persisted_result_created_at(existing_result),
                )
                if existing_result is not None:
                    stored_contract = _mapping(existing_result["payload"], "contract")
                    if contract_to_dict(canonical) != dict(stored_contract):
                        raise CodexAmbiguousOutcomeError(
                            "recovered Codex result differs from its durable contract"
                        )
                receipt_message = _event_id("codex-receipt", message.event_id)
                thread_grant = next(item for item in grants if item.kind == "thread")
                with self._mutation_lock:
                    # Re-read immediately before the receipt mutation. A stale
                    # executor or Passport revision can never land late output.
                    execution_lease.assert_current()
                    self._validated_current_binding(payload)
                    if isinstance(canonical, Checkpoint):
                        self.engine.import_checkpoint(
                            canonical,
                            message_id=receipt_message,
                            preheld_thread_lock=thread_grant,
                        )
                    else:
                        # ``SupervisorEngine`` invokes its independently registered
                        # contour verifier here. The command-supplied terminal
                        # context is evidence input, never a synthetic passed
                        # verifier receipt.
                        self.engine.import_terminal(
                            canonical,
                            message_id=receipt_message,
                            preheld_thread_lock=thread_grant,
                        )
                    if self._after_checkpoint_persisted is not None:
                        self._after_checkpoint_persisted(message, turn)
                    self._persist_codex_turn_receipt(
                        message,
                        turn,
                        canonical,
                        contract_event_id=result_event_id,
                        recovered_from_snapshot=recovered_from_snapshot,
                    )
                if self._after_result_persisted is not None:
                    self._after_result_persisted(message, turn)
                with self._mutation_lock:
                    self.registry.ack_outbox(message.event_id, message.claim_token, self.engine.fence)
            finally:
                execution_lease.stop()
                self._release_execution_locks(grants)
            self._last_codex_error = None
            return RuntimeWorkerResult("codex_followup", message.event_id, "delivered", result_event_id)
        except Exception as exc:
            if message.payload.get("call_policy") == CALL_POLICY_SINGLE_ATTEMPT_CANARY:
                self._last_codex_error = _error_code(exc)
                return self._handle_single_attempt_canary_failure(message, exc)
            self._last_codex_error = _error_code(exc)
            task_id = str(message.payload.get("task_id") or message.task_id or "unknown-task")
            workstream_id = str(message.payload.get("workstream_id") or "unknown-workstream")
            return self._handle_worker_failure(
                message,
                exc,
                task_id=task_id,
                workstream_id=workstream_id,
            )

    def _handle_single_attempt_canary_failure(
        self,
        message: OutboxMessage,
        exc: Exception,
    ) -> RuntimeWorkerResult:
        """Stop one qualification canary without entering incident automation."""

        payload = self._validated_followup_payload(message.payload)
        event_id = _event_id("qualification-canary-failed", message.event_id)
        event_payload = {
            "schema": "dev-control-plane/qualification-canary-failure/v2",
            "status": "failed",
            "decision": "stop_qualification",
            "followup_event_id": message.event_id,
            "error_code": _error_code(exc),
            "call_policy": CALL_POLICY_SINGLE_ATTEMPT_CANARY,
            "model_attempt_count": int(payload["model_attempt_count"]),
            "call_intent_present": payload["call_intent"] is not None,
            "worker_claim_count": int(message.attempts),
            "retry_allowed": False,
            "successor_allowed": False,
            "arbiter_allowed": False,
            "attention_created": False,
            "updated_at": _iso(self.clock()),
        }
        with self._mutation_lock:
            self.registry.record_input_event_outbox_and_ack_claimed(
                message_id=_event_id("qualification-canary-failure-receipt", message.event_id),
                source="codex-qualification-worker",
                input_payload={
                    "event_id": message.event_id,
                    "error_code": _error_code(exc),
                    "model_attempt_count": int(payload["model_attempt_count"]),
                },
                event_id=event_id,
                event_type="qualification_canary_failed",
                event_payload=event_payload,
                outbox_items=(self._dirty_item(event_id, str(payload["task_id"])),),
                claimed_event_id=message.event_id,
                claim_token=message.claim_token,
                fence=self.engine.fence,
                task_id=str(payload["task_id"]),
                workstream_id=str(payload["workstream_id"]),
                executor_generation=int(payload["executor_generation"]),
            )
        return RuntimeWorkerResult(
            message.kind,
            message.event_id,
            "qualification_failed",
            event_id,
        )

    def _turn_receipts_for_followup(
        self,
        message: OutboxMessage,
        result_event_id: str,
    ) -> tuple[Mapping[str, Any], ...]:
        expected = message.payload
        result = self.registry.get_event(result_event_id)
        result_payload = result.get("payload") if result is not None else None
        contract = (
            result_payload.get("contract")
            if isinstance(result_payload, Mapping)
            else None
        )
        contract_digest = (
            _sha256(
                json.dumps(
                    contract,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
            if isinstance(contract, Mapping)
            else None
        )
        return tuple(
            event
            for event in self.registry.list_events(event_types=("codex_turn_receipt",))
            if isinstance(event.get("payload"), Mapping)
            and event["payload"].get("schema")
            == "dev-control-plane/codex-turn-receipt/v2"
            and event["payload"].get("followup_event_id") == message.event_id
            and event["payload"].get("contract_event_id") == result_event_id
            and contract_digest is not None
            and event["payload"].get("contract_digest") == contract_digest
            and event["payload"].get("output_contract")
            == expected.get("output_contract")
            and event["payload"].get("thread_id") == expected.get("thread_id")
            and event["payload"].get("turn_status") == "completed"
            and event["payload"].get("model_attempt_count")
            == expected.get("model_attempt_count")
            and event["payload"].get("model_call_count") == 1
            and event["payload"].get("recovery_model_call_count") == 0
            and event["payload"].get("call_policy") == expected.get("call_policy")
            and event["payload"].get("transport") == "stdio"
            and event["payload"].get("websocket_used") is False
            and event["payload"].get("model") == expected.get("model")
            and event["payload"].get("reasoning") == expected.get("reasoning")
            and isinstance(expected.get("call_intent"), Mapping)
            and event["payload"].get("contract_supervisor_generation")
            == expected["call_intent"].get("supervisor_generation")
            and event["payload"].get("task_revision")
            == expected.get("task_revision")
            and event["payload"].get("workstream_revision")
            == expected.get("workstream_revision")
            and event["payload"].get("executor_generation")
            == expected.get("executor_generation")
            and event["payload"].get("supervisor_generation")
            == event.get("writer_generation")
            and event.get("task_id") == expected.get("task_id")
            and event.get("workstream_id") == expected.get("workstream_id")
            and event.get("executor_generation")
            == expected.get("executor_generation")
        )

    def _persisted_result_created_at(
        self,
        existing_result: Mapping[str, Any] | None,
    ) -> str | None:
        if existing_result is None:
            return None
        contract = _mapping(existing_result["payload"], "contract")
        created_at = contract.get("created_at")
        if not isinstance(created_at, str):
            raise CodexAmbiguousOutcomeError(
                "persisted Codex result lacks its canonical creation time"
            )
        return created_at

    def _persist_codex_turn_receipt(
        self,
        message: OutboxMessage,
        turn: CodexTurnResult,
        canonical: Checkpoint | TerminalEvidence,
        *,
        contract_event_id: str,
        recovered_from_snapshot: bool,
    ) -> None:
        lifecycle = [
            {
                "method": event.method,
                "thread_id": event.thread_id,
                "turn_id": event.turn_id,
                "item_id": event.item_id,
                "item_type": event.item_type,
                "status": event.status,
                "connection_epoch": event.connection_epoch,
                "evidence_source": event.evidence_source,
            }
            for event in turn.events
        ]
        lifecycle_digest = _sha256(
            json.dumps(lifecycle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        )
        item_ids = sorted(
            {str(item["item_id"]) for item in lifecycle if item.get("item_id") is not None}
        )
        terminal_turn_ids = sorted(
            {
                str(item["turn_id"])
                for item in lifecycle
                if item.get("method") == "turn/completed" and item.get("turn_id") is not None
            }
        )
        structural_methods = sorted({str(item["method"]) for item in lifecycle})
        notification_methods = sorted(
            {
                str(item["method"])
                for item in lifecycle
                if item.get("evidence_source") == "notification"
            }
        )
        snapshot_methods = sorted(
            {
                str(item["method"])
                for item in lifecycle
                if item.get("evidence_source") == "thread_read_snapshot"
            }
        )
        event_id = _event_id("codex-turn-receipt", turn.turn_id)
        self.registry.record_input_event_outbox(
            message_id=_event_id("codex-turn-receipt-input", message.event_id),
            source="codex-app-server-structural-receipt",
            input_payload={
                "followup_event_id": message.event_id,
                "turn_id": turn.turn_id,
                "lifecycle_digest": lifecycle_digest,
            },
            event_id=event_id,
            event_type="codex_turn_receipt",
            event_payload={
                "schema": "dev-control-plane/codex-turn-receipt/v2",
                "followup_event_id": message.event_id,
                "contract_event_id": contract_event_id,
                "contract_digest": _sha256(
                    json.dumps(
                        contract_to_dict(canonical),
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                ),
                "output_contract": "terminal" if isinstance(canonical, TerminalEvidence) else "checkpoint",
                "thread_id": turn.thread_id,
                "turn_id": turn.turn_id,
                "turn_status": turn.status,
                "lifecycle_event_count": len(lifecycle),
                "lifecycle_digest": lifecycle_digest,
                # Qualification consumes this legacy field. A recovery receipt
                # is deliberately never presented as a live-notification
                # canary, even if a partial old event buffer survived.
                "lifecycle_methods": [] if recovered_from_snapshot else notification_methods,
                "structural_lifecycle_methods": structural_methods,
                "notification_lifecycle_methods": notification_methods,
                "snapshot_lifecycle_methods": snapshot_methods,
                "lifecycle_evidence_sources": sorted(
                    {str(item["evidence_source"]) for item in lifecycle}
                ),
                "item_ids": item_ids,
                "terminal_turn_ids": terminal_turn_ids,
                "model_attempt_count": int(message.payload["model_attempt_count"]),
                "model_call_count": 1,
                "recovery_model_call_count": 0,
                "receipt_source": (
                    "thread_read_recovery"
                    if recovered_from_snapshot
                    else "live_notification"
                ),
                "call_policy": message.payload["call_policy"],
                "transport": "stdio",
                "websocket_used": False,
                "binary": str(self.codex_bin),
                "model": canonical.executor.model,
                "reasoning": canonical.executor.reasoning,
                "contract_supervisor_generation": int(
                    _mapping(message.payload, "call_intent")[
                        "supervisor_generation"
                    ]
                ),
                "supervisor_generation": self.engine.fence.generation,
                "task_revision": canonical.task_revision,
                "workstream_revision": canonical.workstream_revision,
                "executor_generation": canonical.executor_generation,
                "created_at": canonical.created_at,
            },
            outbox_items=(self._dirty_item(event_id, canonical.task_id),),
            fence=self.engine.fence,
            task_id=canonical.task_id,
            workstream_id=canonical.workstream_id,
            executor_generation=canonical.executor_generation,
        )

    def _handle_unbound_start_failure(
        self,
        message: OutboxMessage,
        exc: Exception,
    ) -> RuntimeWorkerResult:
        """Fail closed without inventing a second thread for an unbound Passport."""

        payload = self._validated_thread_start_payload(message.payload)
        passport = task_passport_from_mapping(_mapping(payload, "passport"))
        workstream = workstream_from_mapping(_mapping(payload, "workstream"))
        ambiguous = isinstance(exc, CodexAmbiguousOutcomeError) or (
            payload["start_intent"] is not None and payload["started_thread"] is None
        )
        retry = message.attempts == 1 and not ambiguous
        event_id = _event_id("codex-start-failure", f"{message.event_id}:{message.attempts}")
        now = _iso(self.clock())
        outbox_items: list[dict[str, Any]] = [self._dirty_item(event_id, passport.task_id)]
        attention_item: dict[str, Any] | None = None
        if not retry:
            attention_item = self._unbound_start_attention(
                passport, workstream, now, ambiguous=ambiguous
            )
            outbox_items.append(attention_item)
        with self._mutation_lock:
            self.registry.record_input_event_outbox(
                message_id=_event_id("codex-start-failure-receipt", f"{message.event_id}:{message.attempts}"),
                source="codex-thread-start-worker",
                input_payload={
                    "event_id": message.event_id,
                    "attempt": message.attempts,
                    "error_code": _error_code(exc),
                },
                event_id=event_id,
                event_type="incident_policy",
                event_payload={
                    "schema": "dev-control-plane/unbound-start-failure/v2",
                    "revision": passport.revision,
                    "status": "retrying" if retry else "parked_fail_closed",
                    "fingerprint": _failure_fingerprint(message, exc),
                    "summary": "Начальная регистрация Codex executor не получила безопасную durable квитанцию.",
                    "decision": "retry_thread_start" if retry else "park_unbound_start",
                    "attempt": message.attempts,
                    "error_code": _error_code(exc),
                    "ambiguous_provider_outcome": ambiguous,
                    "strategy_digest": payload["strategy_digest"],
                    "start_event_id": message.event_id,
                    "attention_event_id": (
                        attention_item["event_id"] if attention_item is not None else None
                    ),
                    "updated_at": now,
                },
                outbox_items=tuple(outbox_items),
                fence=self.engine.fence,
                task_id=passport.task_id,
                workstream_id=workstream.workstream_id,
            )
            if retry:
                self.registry.nack_outbox(
                    message.event_id,
                    message.claim_token,
                    self.engine.fence,
                    retry_at=self.clock() + self.retry_delay_seconds,
                    sanitized_error=_error_code(exc),
                )
                status = "retry_scheduled"
            else:
                self.registry.ack_outbox(message.event_id, message.claim_token, self.engine.fence)
                current_task = self.registry.get_task(passport.task_id)
                current_workstream = self.registry.get_workstream(
                    workstream.workstream_id
                )
                if current_task is not None and current_task.state != "parked":
                    self.registry.update_task_state(
                        passport.task_id,
                        expected_revision=current_task.revision,
                        new_state="parked",
                        fence=self.engine.fence,
                    )
                if (
                    current_workstream is not None
                    and current_workstream.state != "blocked"
                ):
                    self.registry.update_workstream_state(
                        workstream.workstream_id,
                        current_workstream.generation,
                        expected_revision=current_workstream.revision,
                        new_state="blocked",
                        fence=self.engine.fence,
                    )
                status = "parked"
        return RuntimeWorkerResult(message.kind, message.event_id, status, "park_unbound_start")

    def _handle_worker_failure(
        self,
        message: OutboxMessage,
        exc: Exception,
        *,
        task_id: str | None,
        workstream_id: str | None,
    ) -> RuntimeWorkerResult:
        safe_task = task_id if task_id and _MACHINE_RE.fullmatch(task_id) else None
        safe_stream = workstream_id if workstream_id and _MACHINE_RE.fullmatch(workstream_id) else None
        if safe_task is None or safe_stream is None:
            retry = message.attempts == 1 and not isinstance(exc, CodexAmbiguousOutcomeError)
            action = "retry_current_executor" if retry else "start_successor_executor"
            incident_state = None
        else:
            transition = self._advance_incident(message, exc, safe_task, safe_stream)
            if (
                message.kind == "codex_successor_start"
                and transition.action in {"await_successor_proof", "start_successor_executor"}
            ):
                transition = self._escalate_failed_successor(
                    message,
                    exc,
                    transition.state,
                    occurrence_already_counted=(
                        transition.action == "start_successor_executor"
                    ),
                )
            incident_state = transition.state
            action = transition.action
            retry = action == "retry_current_executor" or (
                action == "await_successor_proof" and message.kind == "codex_successor_start" and message.attempts == 1
            )
            if isinstance(exc, CodexAmbiguousOutcomeError):
                # An old exact turn may still be running or may have completed
                # without a persisted output. Starting a successor could create
                # two concurrent workspace mutators, so ambiguity parks safely.
                action = "park_workstream"
                retry = False
            if message.kind == "codex_followup":
                binding = _failure_binding(message, exc)
                persisted_payload = dict(message.payload)
                persisted_payload["causal_fingerprint"] = binding["fingerprint"]
                persisted_payload["causal_binding"] = binding
                if persisted_payload != dict(message.payload):
                    with self._mutation_lock:
                        message = self.registry.replace_claimed_outbox_payload(
                            message.event_id,
                            message.claim_token,
                            persisted_payload,
                            self.engine.fence,
                        )
        failure_event_id = _event_id("codex-failure", f"{message.event_id}:{message.attempts}")
        now = _iso(self.clock())
        event_payload = (
            self._incident_event_payload(
                incident_state,
                action=action,
                status="retrying" if retry else action,
                attempt=incident_state.failure_count,
                error_code=_error_code(exc),
            )
            if incident_state is not None
            else {
                "schema": "dev-control-plane/codex-worker-failure/v2",
                "revision": 1,
                "status": "retrying" if retry else "successor_required",
                "fingerprint": _failure_fingerprint(message, exc),
                "summary": "Codex App Server work failed at a bounded policy boundary.",
                "decision": action,
                "attempt": message.attempts,
                "error_code": _error_code(exc),
                "updated_at": now,
            }
        )
        outbox_items: list[dict[str, Any]] = [self._dirty_item(failure_event_id, safe_task)]
        park_binding = isinstance(exc, CodexAmbiguousOutcomeError) and incident_state is not None
        if park_binding and incident_state is not None:
            event_payload["status"] = "ambiguous_turn_parked"
            event_payload["decision"] = "park_workstream"
            outbox_items.append(self._serious_stall_attention(incident_state, now))
        if incident_state is not None and action == "start_successor_executor":
            if message.kind != "codex_followup":
                raise SupervisorRuntimeError("successor may start only from a failed bound follow-up")
            try:
                outbox_items.append(self._successor_item(message, incident_state))
            except SupervisorRuntimeError:
                action = "park_workstream"
                retry = False
                park_binding = True
                event_payload["status"] = "missing_verified_checkpoint"
                event_payload["decision"] = action
                outbox_items.append(self._serious_stall_attention(incident_state, now))
        elif incident_state is not None and action == "invoke_incident_arbiter":
            outbox_items.append(self._incident_arbiter_item(incident_state))
        elif incident_state is not None and action == "park_workstream":
            outbox_items.append(self._serious_stall_attention(incident_state, now))
        with self._mutation_lock:
            self.registry.record_input_event_outbox(
                message_id=_event_id("codex-failure-receipt", f"{message.event_id}:{message.attempts}"),
                source="codex-worker",
                input_payload={"event_id": message.event_id, "attempt": message.attempts, "error_code": _error_code(exc)},
                event_id=failure_event_id,
                event_type="incident_policy",
                event_payload=event_payload,
                outbox_items=tuple(outbox_items),
                fence=self.engine.fence,
                task_id=safe_task,
                workstream_id=safe_stream,
                executor_generation=(
                    int(message.payload["executor_generation"])
                    if isinstance(message.payload.get("executor_generation"), int)
                    else None
                ),
            )
            if retry:
                self.registry.nack_outbox(
                    message.event_id,
                    message.claim_token,
                    self.engine.fence,
                    retry_at=self.clock() + self.retry_delay_seconds,
                    sanitized_error=_error_code(exc),
                )
                status = "retry_scheduled"
            else:
                self.registry.ack_outbox(message.event_id, message.claim_token, self.engine.fence)
                status = action
            if park_binding and incident_state is not None:
                self._park_incident_binding(incident_state)
        return RuntimeWorkerResult(message.kind, message.event_id, status, action)

    def _advance_incident(
        self,
        message: OutboxMessage,
        exc: Exception,
        task_id: str,
        workstream_id: str,
    ) -> Any:
        binding = _failure_binding(message, exc)
        fingerprint = _failure_fingerprint(message, exc)
        generation = message.payload.get("executor_generation")
        if isinstance(generation, bool) or not isinstance(generation, int) or generation < 1:
            generation = 1
        task_revision = message.payload.get("task_revision")
        if isinstance(task_revision, bool) or not isinstance(task_revision, int) or task_revision < 1:
            task_revision = 1
        prompt = str(message.payload.get("prompt") or "bounded-worker")
        failure = CausalFailure(
            fingerprint=fingerprint,
            stage=str(binding["stage"]),
            error_code=str(binding["error_code"]),
            check_id=str(binding["check_kind"]),
            executor_generation=generation,
            evidence=("fresh_registry_binding_checked", "bounded_app_server_failure"),
            fresh_truth_verified=True,
        )
        context = IncidentContext(
            passport_revision=task_revision,
            strategy_digest=_sha256(prompt),
            causal_evidence_digest=_sha256(
                json.dumps(binding, sort_keys=True, separators=(",", ":"))
            ),
            verified_checkpoint_id=self._incident_checkpoint_id(task_id, workstream_id, generation),
        )
        state = self._latest_incident_state(task_id, workstream_id, fingerprint)
        if state is None:
            transition = begin_incident_budget(
                task_id=task_id,
                workstream_id=workstream_id,
                failure=failure,
                context=context,
            )
        else:
            transition = observe_same_failure(state, failure)
        return transition

    def _escalate_failed_successor(
        self,
        message: OutboxMessage,
        exc: Exception,
        state: IncidentState,
        *,
        occurrence_already_counted: bool,
    ) -> Any:
        binding = _failure_binding(message, exc)
        generation = message.payload.get("successor_generation")
        if isinstance(generation, bool) or not isinstance(generation, int) or generation < 1:
            generation = state.current_executor_generation
        failure = CausalFailure(
            fingerprint=state.fingerprint,
            stage=str(binding["stage"]),
            error_code=str(binding["error_code"]),
            check_id=str(binding["check_kind"]),
            executor_generation=generation,
            evidence=("fresh_registry_binding_checked", "single_successor_limit_enforced"),
            fresh_truth_verified=True,
        )
        return escalate_failed_successor(
            state,
            failure,
            occurrence_already_counted=occurrence_already_counted,
        )

    def _latest_incident_state(
        self,
        task_id: str,
        workstream_id: str,
        fingerprint: str,
    ) -> IncidentState | None:
        events = self.registry.list_events(
            task_id=task_id,
            workstream_id=workstream_id,
            event_types=("incident_policy",),
        )
        for event in reversed(events):
            payload = event.get("payload")
            raw_state = payload.get("incident_state") if isinstance(payload, Mapping) else None
            if isinstance(raw_state, Mapping) and raw_state.get("fingerprint") == fingerprint:
                return _incident_state_from_mapping(raw_state)
        return None

    def _latest_verified_checkpoint(
        self,
        task_id: str,
        workstream_id: str,
        executor_generation: int,
    ) -> Mapping[str, Any] | None:
        events = self.registry.list_events(
            task_id=task_id,
            workstream_id=workstream_id,
            event_types=("checkpoint",),
        )
        for event in reversed(events):
            if event.get("executor_generation") != executor_generation:
                continue
            contract = event.get("payload", {}).get("contract")
            if not isinstance(contract, Mapping):
                continue
            from .orchestration_contracts import checkpoint_from_mapping

            checkpoint = checkpoint_from_mapping(contract)
            if (
                checkpoint.task_id == task_id
                and checkpoint.workstream_id == workstream_id
                and checkpoint.executor_generation == executor_generation
                and checkpoint.event_id == event["event_id"]
            ):
                return event
        return None

    def _incident_checkpoint_id(self, task_id: str, workstream_id: str, executor_generation: int) -> str:
        checkpoint = self._latest_verified_checkpoint(task_id, workstream_id, executor_generation)
        if checkpoint is not None:
            return str(checkpoint["event_id"])
        return _event_id("checkpoint-unavailable", f"{task_id}:{workstream_id}:{executor_generation}")

    def _incident_event_payload(
        self,
        state: IncidentState,
        *,
        action: str,
        status: str,
        attempt: int,
        error_code: str | None = None,
    ) -> dict[str, Any]:
        return {
            "schema": "dev-control-plane/incident-state-event/v2",
            "revision": state.context.passport_revision,
            "status": status,
            "fingerprint": state.fingerprint,
            "summary": "Инцидент продвинут по детерминированной anti-loop политике.",
            "decision": action,
            "attempt": attempt,
            "error_code": error_code or "none",
            "incident_state": _incident_state_to_dict(state),
            "updated_at": _iso(self.clock()),
        }

    def _successor_item(self, message: OutboxMessage, state: IncidentState) -> dict[str, Any]:
        payload = self._validated_followup_payload(message.payload)
        checkpoint = self._latest_verified_checkpoint(
            state.task_id,
            state.workstream_id,
            state.current_executor_generation,
        )
        if checkpoint is None or checkpoint["event_id"] != state.context.verified_checkpoint_id:
            raise SupervisorRuntimeError("successor requires the exact latest verified checkpoint")
        checkpoint_contract = _mapping(checkpoint["payload"], "contract")
        checkpoint_digest = _sha256(
            json.dumps(checkpoint_contract, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        )
        event_id = _event_id("codex-successor", f"{state.task_id}:{state.workstream_id}:{state.fingerprint}")
        successor_payload = {
            "schema": SUCCESSOR_SCHEMA,
            "task_id": state.task_id,
            "task_revision": payload["task_revision"],
            "workstream_id": state.workstream_id,
            "workstream_revision": payload["workstream_revision"],
            "predecessor_generation": state.current_executor_generation,
            "successor_generation": state.successor_generation,
            "causal_fingerprint": state.fingerprint,
            "causal_binding": payload["causal_binding"],
            "cwd": payload["cwd"],
            "verified_checkpoint_id": state.context.verified_checkpoint_id,
            "verified_checkpoint_digest": checkpoint_digest,
            "verified_checkpoint": dict(checkpoint_contract),
            "original_followup": dict(payload),
            "started_thread": None,
            "start_intent": None,
            "proof_intent": None,
            "proof_contract": None,
        }
        return {
            "event_id": event_id,
            "kind": "codex_successor_start",
            "payload": successor_payload,
            "task_id": state.task_id,
            "coalescible": False,
            "coalesce_key": None,
        }

    def _incident_arbiter_item(self, state: IncidentState) -> dict[str, Any]:
        if state.incident_case_id is None or state.incident_case_digest is None:
            raise SupervisorRuntimeError("arbiter outbox requires an immutable incident case")
        task = self.registry.get_task(state.task_id)
        workstream = self.registry.get_workstream(state.workstream_id)
        if task is None or workstream is None:
            raise SupervisorRuntimeError("arbiter case binding disappeared")
        passport = task_passport_from_mapping(task.passport)
        payload = {
            "schema": "dev-control-plane/incident-arbiter-case/v2",
            "case_id": state.incident_case_id,
            "case_digest": state.incident_case_digest,
            "incident_state": _incident_state_to_dict(state),
            "binding": {
                "task_id": state.task_id,
                "task_revision": task.revision,
                "workstream_id": state.workstream_id,
                "workstream_revision": workstream.revision,
                "executor_generation": state.current_executor_generation,
                # Generic incident cases may not be tied to a GitHub PR, but
                # the shared immutable RevisionBinding still requires a
                # syntactically exact git SHA width. Release incidents replace
                # this with their read-back candidate head.
                "pr_head_sha": state.context.causal_evidence_digest[:40],
                "resources": list(passport.resources),
            },
        }
        return {
            "event_id": _event_id("incident-arbiter", state.incident_case_id),
            "kind": "incident_arbiter_case",
            "payload": payload,
            "task_id": state.task_id,
            "coalescible": False,
            "coalesce_key": None,
        }

    def _serious_stall_attention(self, state: IncidentState, created_at: str) -> dict[str, Any]:
        task = self.registry.get_task(state.task_id)
        if task is None:
            raise SupervisorRuntimeError("serious-stall task disappeared")
        passport = task_passport_from_mapping(task.passport)
        attention_id = _event_id("serious-stall", state.incident_case_id or state.fingerprint)
        if state.incident_case_id is None:
            proof = (
                "для successor отсутствует точный проверенный checkpoint; context-free замена запрещена"
            )
        else:
            proof = "та же причинная ошибка сохранилась после единственного arbiter-применения"
        return {
            "event_id": _event_id("curator-serious-stall", attention_id),
            "kind": "curator_attention",
            "payload": {
                "schema": "dev-control-plane/curator-attention/v2",
                "attention_id": attention_id,
                "task_id": state.task_id,
                "workstream_id": state.workstream_id,
                "curator_thread_id": passport.curator.thread_id,
                "kind": "serious_stall",
                "handoff_ru": (
                    "Статус: Блокер\n"
                    f"Задача: {passport.title}\n"
                    f"Доказательство: {proof}.\n"
                    "Сейчас: workstream безопасно припаркован без четвёртого retry."
                ),
                "required_action": "Измените Passport, стратегию или причинное доказательство для нового бюджета.",
                "created_at": created_at,
            },
            "task_id": state.task_id,
            "coalescible": False,
            "coalesce_key": None,
        }

    def _unbound_start_attention(
        self,
        passport: TaskPassport,
        workstream: Any,
        created_at: str,
        *,
        ambiguous: bool,
    ) -> dict[str, Any]:
        attention_id = _event_id(
            "unbound-start-stall",
            f"{passport.task_id}:{workstream.workstream_id}:r{passport.revision}",
        )
        proof = (
            "thread/start мог быть принят App Server, но exact thread id не был durably сохранён"
            if ambiguous
            else "bounded transport retry не создал доказанную exact executor identity"
        )
        return {
            "event_id": _event_id("curator-unbound-start-stall", attention_id),
            "kind": "curator_attention",
            "payload": {
                "schema": "dev-control-plane/curator-attention/v2",
                "attention_id": attention_id,
                "task_id": passport.task_id,
                "workstream_id": workstream.workstream_id,
                "curator_thread_id": passport.curator.thread_id,
                "kind": "serious_stall",
                "handoff_ru": (
                    "Статус: Блокер\n"
                    f"Задача: {passport.title}\n"
                    f"Доказательство: {proof}.\n"
                    "Сейчас: повторный executor не создан; bootstrap припаркован fail-closed."
                ),
                "required_action": (
                    "Проверьте exact Desktop thread capability/состояние и создайте новый Passport revision "
                    "только после исключения живого непривязанного executor."
                ),
                "created_at": created_at,
            },
            "task_id": passport.task_id,
            "coalescible": False,
            "coalesce_key": None,
        }

    def _release_stall_attention(self, candidate: Any, created_at: str) -> dict[str, Any]:
        task = self.registry.get_task(candidate.task_id)
        if task is None:
            raise SupervisorRuntimeError("release-stall task disappeared")
        passport = task_passport_from_mapping(task.passport)
        attention_id = _event_id("release-stall", candidate.candidate_id)
        return {
            "event_id": _event_id("curator-release-stall", candidate.candidate_id),
            "kind": "curator_attention",
            "payload": {
                "schema": "dev-control-plane/curator-attention/v2",
                "attention_id": attention_id,
                "task_id": candidate.task_id,
                "workstream_id": candidate.workstream_id,
                "curator_thread_id": passport.curator.thread_id,
                "kind": "serious_stall",
                "handoff_ru": (
                    "Статус: Блокер\n"
                    f"Задача: {passport.title}\n"
                    f"Доказательство: release candidate {candidate.candidate_id} не прошёл bounded actuator/readback.\n"
                    "Сейчас: логическая полоса припаркована; слепой повтор не выполняется."
                ),
                "required_action": "Измените Passport/стратегию или устраните доказанную внешнюю причину.",
                "created_at": created_at,
            },
            "task_id": candidate.task_id,
            "coalescible": False,
            "coalesce_key": None,
        }

    def _park_release_binding(self, candidate: Any) -> None:
        workstream = self.registry.get_workstream(candidate.workstream_id)
        if workstream is not None and workstream.state != "parked":
            self.registry.update_workstream_state(
                candidate.workstream_id,
                workstream.generation,
                expected_revision=workstream.revision,
                new_state="parked",
                fence=self.engine.fence,
            )
        self._reconcile_task_aggregate_after_park(candidate.task_id)

    def _park_incident_binding(self, state: IncidentState) -> None:
        workstream = self.registry.get_workstream(state.workstream_id)
        if workstream is not None and workstream.state != "parked":
            self.registry.update_workstream_state(
                state.workstream_id,
                workstream.generation,
                expected_revision=workstream.revision,
                new_state="parked",
                fence=self.engine.fence,
            )
        self._reconcile_task_aggregate_after_park(state.task_id)

    def _reconcile_task_aggregate_after_park(self, task_id: str) -> None:
        """Park the envelope only when no independently runnable sibling remains."""

        task = self.registry.get_task(task_id)
        if task is None:
            return
        streams = tuple(
            stream
            for stream in self.registry.list_workstreams()
            if stream.task_id == task_id and stream.current
        )
        terminal_states = {
            "technical_complete",
            "acceptance_pending",
            "accepted",
        }
        parked_states = {"blocked", "parked"}
        unresolved = tuple(
            stream
            for stream in streams
            if stream.state not in terminal_states | parked_states
        )
        if unresolved:
            aggregate = (
                "recovering"
                if any(stream.state == "recovering" for stream in unresolved)
                else "active"
            )
            if task.state != aggregate:
                self.registry.set_task_aggregate_state(
                    task_id,
                    expected_revision=task.revision,
                    new_state=aggregate,
                    fence=self.engine.fence,
                )
            return
        if task.state != "parked":
            self.registry.update_task_state(
                task_id,
                expected_revision=task.revision,
                new_state="parked",
                fence=self.engine.fence,
            )

    def _dirty_item(self, trigger_event_id: str, task_id: str | None) -> dict[str, Any]:
        return {
            "event_id": _event_id("dirty", trigger_event_id),
            "kind": "projection_dirty",
            "payload": {"trigger_event_id": trigger_event_id},
            "task_id": task_id,
            "coalescible": True,
            "coalesce_key": "global-projection",
        }

    def _prepare_policy_action(
        self,
        payload: Mapping[str, Any],
        *,
        kind: str,
        worker: str,
    ) -> dict[str, Any] | None:
        _exact_fields(payload, {"visibility_timeout"}, f"prepare {kind} payload")
        visibility = payload.get("visibility_timeout")
        if isinstance(visibility, bool) or not isinstance(visibility, (int, float)) or not 5 <= float(visibility) <= 900:
            raise SupervisorCommandError("policy action visibility timeout is out of bounds")
        with self._mutation_lock:
            messages = self.registry.claim_outbox(
                self.engine.fence,
                worker_id=worker,
                limit=1,
                visibility_timeout=float(visibility),
                kinds=(kind,),
            )
            if not messages:
                return None
            message = messages[0]
            self._prepared_policy_claims[message.event_id] = (message.claim_token, dict(message.payload))
        return {
            "event_id": message.event_id,
            "payload": message.payload,
            "attempt": message.attempts,
            "claim_token": message.claim_token,
        }

    def _claimed_policy_message(self, event_id: str, claim_token: str, kind: str) -> dict[str, Any]:
        claim = self._prepared_policy_claims.get(event_id)
        if claim is None or claim[0] != claim_token:
            raise SupervisorCommandError(f"{kind} was not prepared by this daemon generation")
        return claim[1]

    def _validated_successor_payload(self, value: Mapping[str, Any]) -> dict[str, Any]:
        required = {
            "schema", "task_id", "task_revision", "workstream_id", "workstream_revision",
            "predecessor_generation", "successor_generation", "causal_fingerprint",
            "causal_binding", "cwd",
            "verified_checkpoint_id", "verified_checkpoint_digest", "verified_checkpoint",
            "original_followup", "started_thread", "start_intent", "proof_intent", "proof_contract",
        }
        _exact_fields(value, required, "successor outbox")
        if value.get("schema") != SUCCESSOR_SCHEMA:
            raise SupervisorRuntimeError("successor schema mismatch")
        payload = dict(value)
        for key in ("task_id", "workstream_id", "verified_checkpoint_id"):
            _machine(key, payload[key])
        for key in ("task_revision", "workstream_revision", "predecessor_generation", "successor_generation"):
            if isinstance(payload[key], bool) or not isinstance(payload[key], int) or payload[key] < 1:
                raise SupervisorRuntimeError("successor numeric binding is invalid")
        if payload["successor_generation"] != payload["predecessor_generation"] + 1:
            raise SupervisorRuntimeError("successor generation is not exact")
        if not isinstance(payload["causal_fingerprint"], str) or not re.fullmatch(r"[0-9a-f]{64}", payload["causal_fingerprint"]):
            raise SupervisorRuntimeError("successor causal fingerprint is invalid")
        payload["causal_binding"] = _validated_causal_binding(
            payload["causal_binding"],
            fingerprint=payload["causal_fingerprint"],
        )
        if not isinstance(payload["verified_checkpoint_digest"], str) or not re.fullmatch(
            r"[0-9a-f]{64}", payload["verified_checkpoint_digest"]
        ):
            raise SupervisorRuntimeError("successor checkpoint digest is invalid")
        checkpoint_contract = _mapping(payload, "verified_checkpoint")
        actual_digest = _sha256(
            json.dumps(checkpoint_contract, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        )
        if actual_digest != payload["verified_checkpoint_digest"]:
            raise SupervisorRuntimeError("successor checkpoint digest mismatch")
        from .orchestration_contracts import checkpoint_from_mapping

        frozen = checkpoint_from_mapping(checkpoint_contract)
        if (
            frozen.event_id != payload["verified_checkpoint_id"]
            or frozen.task_id != payload["task_id"]
            or frozen.workstream_id != payload["workstream_id"]
            or frozen.executor_generation != payload["predecessor_generation"]
        ):
            raise SupervisorRuntimeError("successor checkpoint binding mismatch")
        self._workspace(payload["cwd"])
        payload["original_followup"] = self._validated_followup_payload(_mapping(payload, "original_followup"))
        if payload["original_followup"]["cwd"] != payload["cwd"]:
            raise SupervisorRuntimeError("successor cwd differs from its original follow-up")
        payload["start_intent"] = self._validated_start_intent(payload["start_intent"])
        payload["proof_intent"] = self._validated_call_intent(payload["proof_intent"], "successor proof intent")
        started = payload["started_thread"]
        if started is not None:
            _exact_fields(
                _mapping_value(started, "started_thread"),
                {"thread_id", "session_id", "host_id", "model", "reasoning", "ephemeral"},
                "successor thread identity",
            )
            if started.get("ephemeral") is not False or started.get("model") != CODEX_APP_SERVER_MODEL or started.get("reasoning") != CODEX_APP_SERVER_REASONING_EFFORT:
                raise SupervisorRuntimeError("successor thread identity mismatch")
        if payload["proof_contract"] is not None and not isinstance(payload["proof_contract"], Mapping):
            raise SupervisorRuntimeError("successor proof contract is invalid")
        return payload

    def _validated_preactivation_causal_read_payload(
        self, value: Mapping[str, Any]
    ) -> dict[str, Any]:
        required = {
            "schema",
            "task_id",
            "task_revision",
            "workstream_id",
            "workstream_generation",
            "workstream_revision",
            "executor_generation",
            "thread_id",
            "host_id",
            "source_failure_event_id",
            "source_failure_payload_digest",
            "source_followup_event_id",
            "source_followup_payload_digest",
            "source_call_intent_digest",
            "observed_generation",
            "expected_supervisor_generation",
            "activation_release_sha",
            "expected_pr_head_sha",
            "backup_path",
            "backup_sha256",
            "strategy_digest",
            "justification_digest",
            "replacement_passport",
            "corrective_workstream",
            "replacement_passport_digest",
            "replacement_workstream_digest",
            "causal_read_event_id",
            "causal_attestation_event_id",
            "remediation_event_id",
            "successor_event_id",
            "completion_event_id",
            "projection_event_id",
            "successor_payload",
            "read_intent",
            "observed_attestation",
        }
        _exact_fields(value, required, "preactivation causal read outbox")
        payload = dict(value)
        if (
            payload.get("schema") != PREACTIVATION_CAUSAL_READ_SCHEMA
            or payload.get("task_id")
            != PREACTIVATION_STRUCTURAL_REPAIR_TASK_ID
            or payload.get("task_revision")
            != PREACTIVATION_CAUSAL_REMEDIATION_SOURCE_TASK_REVISION
            or payload.get("workstream_id")
            != PREACTIVATION_STRUCTURAL_REPAIR_WORKSTREAM_ID
            or payload.get("workstream_generation")
            != PREACTIVATION_CAUSAL_REMEDIATION_SOURCE_WORKSTREAM_GENERATION
            or payload.get("workstream_revision")
            != PREACTIVATION_CAUSAL_REMEDIATION_SOURCE_WORKSTREAM_REVISION
            or payload.get("executor_generation")
            != PREACTIVATION_CAUSAL_REMEDIATION_SOURCE_EXECUTOR_GENERATION
            or payload.get("observed_generation")
            != PREACTIVATION_CAUSAL_REMEDIATION_SOURCE_EXECUTOR_GENERATION
            or payload.get("expected_supervisor_generation")
            != PREACTIVATION_CAUSAL_REMEDIATION_EXPECTED_OUTPUT_GENERATION
            or payload.get("activation_release_sha")
            != (
                self.activation_identity.get("release_sha")
                if isinstance(self.activation_identity, Mapping)
                else None
            )
            or payload.get("expected_pr_head_sha")
            == PREACTIVATION_CAUSAL_REMEDIATION_PR92_HEAD_SHA
        ):
            raise SupervisorRuntimeError(
                "preactivation causal read coordinates are not exact PR92"
            )
        for key in (
            "thread_id",
            "host_id",
            "source_failure_event_id",
            "source_followup_event_id",
            "causal_read_event_id",
            "causal_attestation_event_id",
            "remediation_event_id",
            "successor_event_id",
            "completion_event_id",
            "projection_event_id",
        ):
            _machine(key, payload.get(key))
        for key in (
            "source_failure_payload_digest",
            "source_followup_payload_digest",
            "source_call_intent_digest",
            "backup_sha256",
            "strategy_digest",
            "justification_digest",
            "replacement_passport_digest",
            "replacement_workstream_digest",
        ):
            _digest_value(key, payload.get(key))
        if payload.get("strategy_digest") != _sha256(
            PREACTIVATION_CAUSAL_STRATEGY_RESOURCE
        ):
            raise SupervisorRuntimeError(
                "preactivation causal read strategy binding changed"
            )
        backup = Path(str(payload.get("backup_path")))
        expected_backup = self.registry.preactivation_causal_remediation_backup_path()
        if backup != expected_backup:
            raise SupervisorRuntimeError(
                "preactivation causal read backup binding changed"
            )
        replacement = _mapping(payload, "replacement_passport")
        corrective = _mapping(payload, "corrective_workstream")
        for label, contract, digest_key in (
            ("replacement Passport", replacement, "replacement_passport_digest"),
            ("corrective workstream", corrective, "replacement_workstream_digest"),
        ):
            digest = _sha256(
                json.dumps(
                    contract,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
            if digest != payload.get(digest_key):
                raise SupervisorRuntimeError(
                    f"preactivation causal {label} digest changed"
                )
        if not isinstance(payload.get("successor_payload"), Mapping):
            raise SupervisorRuntimeError(
                "preactivation causal successor reservation is missing"
            )
        intent = payload.get("read_intent")
        if intent is not None:
            if not isinstance(intent, Mapping):
                raise SupervisorRuntimeError(
                    "preactivation causal read intent is invalid"
                )
            _exact_fields(
                intent,
                {"supervisor_generation", "started_at"},
                "preactivation causal read intent",
            )
            if (
                isinstance(intent.get("supervisor_generation"), bool)
                or not isinstance(intent.get("supervisor_generation"), int)
                or int(intent["supervisor_generation"]) < 1
                or not isinstance(intent.get("started_at"), str)
                or not intent.get("started_at")
            ):
                raise SupervisorRuntimeError(
                    "preactivation causal read intent is invalid"
                )
        observed = payload.get("observed_attestation")
        if observed is not None:
            self._validated_preactivation_causal_attestation(observed)
        return payload

    def _validated_preactivation_causal_attestation(
        self, value: object
    ) -> dict[str, Any]:
        if not isinstance(value, Mapping):
            raise SupervisorRuntimeError(
                "preactivation causal attestation is not an object"
            )
        required = {
            "schema",
            "status",
            "read_method",
            "causal_read_event_id",
            "source_failure_event_id",
            "source_followup_event_id",
            "thread_id",
            "turn_id",
            "output_item_id",
            "thread_snapshot_digest",
            "turn_digest",
            "output_item_digest",
            "contract_digest",
            "turn_status",
            "turn_count",
            "observed_identity",
            "expected_identity",
            "mismatched_fields",
            "raw_provider_body_stored",
        }
        _exact_fields(value, required, "preactivation causal attestation")
        payload = dict(value)
        expected_observed = {
            "generation": PREACTIVATION_CAUSAL_REMEDIATION_SOURCE_EXECUTOR_GENERATION,
            "task_id": PREACTIVATION_STRUCTURAL_REPAIR_TASK_ID,
            "workstream_id": PREACTIVATION_STRUCTURAL_REPAIR_WORKSTREAM_ID,
        }
        expected_required = {
            "generation": PREACTIVATION_CAUSAL_REMEDIATION_EXPECTED_OUTPUT_GENERATION,
            "task_id": PREACTIVATION_STRUCTURAL_REPAIR_TASK_ID,
            "workstream_id": PREACTIVATION_STRUCTURAL_REPAIR_WORKSTREAM_ID,
        }
        if (
            payload.get("schema") != PREACTIVATION_CAUSAL_ATTESTATION_SCHEMA
            or payload.get("status") != "generation_mismatch_proven"
            or payload.get("read_method") != "thread/read"
            or payload.get("turn_status") != "completed"
            or payload.get("turn_count") != 1
            or payload.get("observed_identity") != expected_observed
            or payload.get("expected_identity") != expected_required
            or payload.get("mismatched_fields") != ["generation"]
            or payload.get("raw_provider_body_stored") is not False
        ):
            raise SupervisorRuntimeError(
                "preactivation causal attestation is not generation-only"
            )
        for key in (
            "causal_read_event_id",
            "source_failure_event_id",
            "source_followup_event_id",
            "thread_id",
            "turn_id",
            "output_item_id",
        ):
            _machine(key, payload.get(key))
        for key in (
            "thread_snapshot_digest",
            "turn_digest",
            "output_item_digest",
            "contract_digest",
        ):
            _digest_value(key, payload.get(key))
        return payload

    def _validated_preactivation_causal_successor_payload(
        self, value: Mapping[str, Any]
    ) -> dict[str, Any]:
        required = {
            "schema",
            "task_id",
            "task_revision",
            "workstream_id",
            "workstream_generation",
            "workstream_revision",
            "predecessor_generation",
            "successor_generation",
            "cwd",
            "source_pr92_activation_release_sha",
            "source_pr92_expected_head_sha",
            "activation_release_sha",
            "expected_pr_head_sha",
            "causal_read_event_id",
            "causal_attestation_event_id",
            "remediation_event_id",
            "completion_event_id",
            "source_failure_event_id",
            "source_followup_event_id",
            "replacement_passport_digest",
            "replacement_workstream_digest",
            "strategy_digest",
            "start_intent",
            "started_thread",
        }
        _exact_fields(value, required, "preactivation causal successor outbox")
        payload = dict(value)
        if (
            payload.get("schema") != PREACTIVATION_CAUSAL_SUCCESSOR_SCHEMA
            or payload.get("task_id")
            != PREACTIVATION_STRUCTURAL_REPAIR_TASK_ID
            or payload.get("task_revision")
            != PREACTIVATION_CAUSAL_REMEDIATION_SUCCESSOR_TASK_REVISION
            or payload.get("workstream_id")
            != PREACTIVATION_STRUCTURAL_REPAIR_WORKSTREAM_ID
            or payload.get("workstream_generation")
            != PREACTIVATION_CAUSAL_REMEDIATION_SUCCESSOR_WORKSTREAM_GENERATION
            or payload.get("workstream_revision") != 1
            or payload.get("predecessor_generation")
            != PREACTIVATION_CAUSAL_REMEDIATION_SOURCE_EXECUTOR_GENERATION
            or payload.get("successor_generation")
            != PREACTIVATION_CAUSAL_REMEDIATION_SUCCESSOR_EXECUTOR_GENERATION
            or payload.get("source_pr92_activation_release_sha")
            != PREACTIVATION_CAUSAL_REMEDIATION_PR92_MERGE_SHA
            or payload.get("source_pr92_expected_head_sha")
            != PREACTIVATION_CAUSAL_REMEDIATION_PR92_HEAD_SHA
            or payload.get("activation_release_sha")
            != (
                self.activation_identity.get("release_sha")
                if isinstance(self.activation_identity, Mapping)
                else None
            )
            or payload.get("strategy_digest")
            != _sha256(PREACTIVATION_CAUSAL_STRATEGY_RESOURCE)
        ):
            raise SupervisorRuntimeError(
                "preactivation causal successor coordinates are invalid"
            )
        for key in (
            "causal_read_event_id",
            "causal_attestation_event_id",
            "remediation_event_id",
            "completion_event_id",
            "source_failure_event_id",
            "source_followup_event_id",
        ):
            _machine(key, payload.get(key))
        for key in (
            "activation_release_sha",
            "expected_pr_head_sha",
            "source_pr92_activation_release_sha",
            "source_pr92_expected_head_sha",
        ):
            value_sha = payload.get(key)
            if not isinstance(value_sha, str) or not re.fullmatch(
                r"[0-9a-f]{40}", value_sha
            ):
                raise SupervisorRuntimeError(
                    f"preactivation causal successor {key} is invalid"
                )
        for key in (
            "replacement_passport_digest",
            "replacement_workstream_digest",
            "strategy_digest",
        ):
            _digest_value(key, payload.get(key))
        self._workspace(payload.get("cwd"))
        intent = payload.get("start_intent")
        if intent is not None:
            if not isinstance(intent, Mapping):
                raise SupervisorRuntimeError(
                    "preactivation causal successor start intent is invalid"
                )
            _exact_fields(
                intent,
                {
                    "supervisor_generation",
                    "started_at",
                    "app_server_connection_epoch",
                },
                "preactivation causal successor start intent",
            )
            if (
                intent.get("supervisor_generation") != self.engine.fence.generation
                or isinstance(intent.get("app_server_connection_epoch"), bool)
                or not isinstance(intent.get("app_server_connection_epoch"), int)
                or int(intent["app_server_connection_epoch"]) < 1
            ):
                raise SupervisorRuntimeError(
                    "preactivation causal successor start intent is stale"
                )
        started = payload.get("started_thread")
        if started is not None:
            if not isinstance(started, Mapping):
                raise SupervisorRuntimeError(
                    "preactivation causal successor identity is invalid"
                )
            _exact_fields(
                started,
                {
                    "thread_id",
                    "session_id",
                    "host_id",
                    "model",
                    "reasoning",
                    "ephemeral",
                },
                "preactivation causal successor identity",
            )
            for key in ("thread_id", "session_id", "host_id"):
                _machine(key, started.get(key))
            if (
                started.get("model") != CODEX_APP_SERVER_MODEL
                or started.get("reasoning")
                != CODEX_APP_SERVER_REASONING_EFFORT
                or started.get("ephemeral") is not False
                or intent is None
            ):
                raise SupervisorRuntimeError(
                    "preactivation causal successor identity mismatch"
                )
        return payload

    def _validated_preactivation_successor_payload(
        self, value: Mapping[str, Any]
    ) -> dict[str, Any]:
        required = {
            "schema",
            "task_id",
            "task_revision",
            "workstream_id",
            "workstream_generation",
            "workstream_revision",
            "predecessor_generation",
            "successor_generation",
            "cwd",
            "activation_release_sha",
            "expected_pr_head_sha",
            "repair_event_id",
            "completion_event_id",
            "replacement_passport_digest",
            "replacement_workstream_digest",
            "start_intent",
            "started_thread",
        }
        _exact_fields(value, required, "preactivation successor outbox")
        payload = dict(value)
        if payload.get("schema") != PREACTIVATION_SUCCESSOR_SCHEMA:
            raise SupervisorRuntimeError(
                "preactivation successor schema mismatch"
            )
        if (
            payload.get("task_id") != PREACTIVATION_STRUCTURAL_REPAIR_TASK_ID
            or payload.get("workstream_id")
            != PREACTIVATION_STRUCTURAL_REPAIR_WORKSTREAM_ID
            or payload.get("task_revision") != 3
            or payload.get("workstream_generation") != 2
            or payload.get("workstream_revision") != 1
            or payload.get("predecessor_generation") != 1
            or payload.get("successor_generation") != 2
        ):
            raise SupervisorRuntimeError(
                "preactivation successor coordinates are not exact PR91"
            )
        for key, length in (
            ("activation_release_sha", 40),
            ("expected_pr_head_sha", 40),
            ("replacement_passport_digest", 64),
            ("replacement_workstream_digest", 64),
        ):
            observed = payload.get(key)
            if (
                not isinstance(observed, str)
                or len(observed) != length
                or any(character not in "0123456789abcdef" for character in observed)
            ):
                raise SupervisorRuntimeError(
                    f"preactivation successor {key} is invalid"
                )
        _machine("repair_event_id", payload.get("repair_event_id"))
        _machine("completion_event_id", payload.get("completion_event_id"))
        self._workspace(payload.get("cwd"))
        intent = payload.get("start_intent")
        if intent is not None:
            if not isinstance(intent, Mapping):
                raise SupervisorRuntimeError(
                    "preactivation successor start intent is invalid"
                )
            _exact_fields(
                intent,
                {
                    "supervisor_generation",
                    "started_at",
                    "app_server_connection_epoch",
                },
                "preactivation successor start intent",
            )
            if (
                intent.get("supervisor_generation") != self.engine.fence.generation
                or isinstance(intent.get("app_server_connection_epoch"), bool)
                or not isinstance(intent.get("app_server_connection_epoch"), int)
                or int(intent["app_server_connection_epoch"]) < 1
            ):
                raise SupervisorRuntimeError(
                    "preactivation successor start intent is stale"
                )
        started = payload.get("started_thread")
        if started is not None:
            if not isinstance(started, Mapping):
                raise SupervisorRuntimeError(
                    "preactivation successor started identity is invalid"
                )
            _exact_fields(
                started,
                {
                    "thread_id",
                    "session_id",
                    "host_id",
                    "model",
                    "reasoning",
                    "ephemeral",
                },
                "preactivation successor started identity",
            )
            for key in ("thread_id", "session_id", "host_id"):
                _machine(key, started.get(key))
            if (
                started.get("model") != CODEX_APP_SERVER_MODEL
                or started.get("reasoning")
                != CODEX_APP_SERVER_REASONING_EFFORT
                or started.get("ephemeral") is not False
                or intent is None
            ):
                raise SupervisorRuntimeError(
                    "preactivation successor identity mismatch"
                )
        return payload

    def _attest_preactivation_causal_snapshot(
        self,
        snapshot: Mapping[str, Any],
        *,
        thread_id: str,
        task_id: str,
        workstream_id: str,
        causal_read_event_id: str,
        source_failure_event_id: str,
        source_followup_event_id: str,
    ) -> dict[str, Any]:
        """Reduce one historical PR92 turn to IDs, digests and typed binding.

        The persisted attestation deliberately excludes the provider body and
        every user/model text field.  Re-validating a copy with only the raw
        ``generation`` corrected proves that generation is the sole contract
        mismatch; all other schema and identity fields must already be exact.
        """

        if not isinstance(snapshot, Mapping) or snapshot.get("id") != thread_id:
            raise CodexProtocolError(
                "preactivation causal read returned a different thread"
            )
        turns = snapshot.get("turns")
        if not isinstance(turns, list) or len(turns) != 1:
            raise CodexAmbiguousOutcomeError(
                "preactivation causal read requires exactly one persisted turn"
            )
        raw_turn = turns[0]
        if not isinstance(raw_turn, Mapping):
            raise CodexProtocolError(
                "preactivation causal read turn is not an object"
            )
        turn_id = _machine("causal_turn_id", raw_turn.get("id"))
        if raw_turn.get("status") != "completed":
            raise CodexAmbiguousOutcomeError(
                "preactivation causal read turn is not completed"
            )
        if raw_turn.get("itemsView") != "full":
            raise CodexProtocolError(
                "preactivation causal read requires itemsView=full"
            )
        items, output_item = _validated_recovery_items(raw_turn.get("items"))
        agent_items = [item for item in items if item.get("type") == "agentMessage"]
        if (
            len(agent_items) != 1
            or output_item is not agent_items[0]
            or output_item.get("phase") != "final_answer"
        ):
            raise CodexAmbiguousOutcomeError(
                "preactivation causal read requires one final schema-bound output"
            )
        raw_output = str(output_item["text"])
        contract_payload = _parse_contract_json(raw_output)
        observed = validate_checkpoint_payload(
            contract_payload,
            expected_generation=None,
            expected_task_id=task_id,
            expected_workstream_id=workstream_id,
        )
        if (
            observed.generation
            != PREACTIVATION_CAUSAL_REMEDIATION_SOURCE_EXECUTOR_GENERATION
            or PREACTIVATION_CAUSAL_REMEDIATION_EXPECTED_OUTPUT_GENERATION
            != PREACTIVATION_CAUSAL_REMEDIATION_SOURCE_EXECUTOR_GENERATION + 1
        ):
            raise CodexContractError(
                "preactivation causal read did not reproduce the exact PR92 generation mismatch"
            )
        corrected_payload = dict(contract_payload)
        corrected_payload["generation"] = (
            PREACTIVATION_CAUSAL_REMEDIATION_EXPECTED_OUTPUT_GENERATION
        )
        validate_checkpoint_payload(
            corrected_payload,
            expected_generation=(
                PREACTIVATION_CAUSAL_REMEDIATION_EXPECTED_OUTPUT_GENERATION
            ),
            expected_task_id=task_id,
            expected_workstream_id=workstream_id,
        )
        try:
            validate_checkpoint_payload(
                contract_payload,
                expected_generation=(
                    PREACTIVATION_CAUSAL_REMEDIATION_EXPECTED_OUTPUT_GENERATION
                ),
                expected_task_id=task_id,
                expected_workstream_id=workstream_id,
            )
        except CodexContractError as exc:
            if "generation" not in str(exc):
                raise CodexContractError(
                    "preactivation causal read mismatch is not generation-only"
                ) from exc
        else:
            raise CodexContractError(
                "preactivation causal read unexpectedly matches its required generation"
            )

        output_item_id = _machine("causal_output_item_id", output_item.get("id"))
        snapshot_json = json.dumps(
            snapshot,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        contract_json = json.dumps(
            contract_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        turn_json = json.dumps(
            raw_turn,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        output_item_json = json.dumps(
            output_item,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return {
            "schema": PREACTIVATION_CAUSAL_ATTESTATION_SCHEMA,
            "status": "generation_mismatch_proven",
            "read_method": "thread/read",
            "causal_read_event_id": _machine(
                "causal_read_event_id", causal_read_event_id
            ),
            "source_failure_event_id": _machine(
                "source_failure_event_id", source_failure_event_id
            ),
            "source_followup_event_id": _machine(
                "source_followup_event_id", source_followup_event_id
            ),
            "thread_id": thread_id,
            "turn_id": turn_id,
            "output_item_id": output_item_id,
            "thread_snapshot_digest": _sha256(snapshot_json),
            "turn_digest": _sha256(turn_json),
            "output_item_digest": _sha256(output_item_json),
            "contract_digest": _sha256(contract_json),
            "turn_status": "completed",
            "turn_count": 1,
            "observed_identity": {
                "generation": observed.generation,
                "task_id": task_id,
                "workstream_id": workstream_id,
            },
            "expected_identity": {
                "generation": (
                    PREACTIVATION_CAUSAL_REMEDIATION_EXPECTED_OUTPUT_GENERATION
                ),
                "task_id": task_id,
                "workstream_id": workstream_id,
            },
            "mismatched_fields": ["generation"],
            "raw_provider_body_stored": False,
        }

    def _successor_proof_prompt(self, payload: Mapping[str, Any]) -> str:
        envelope = {
            "task_id": payload["task_id"],
            "workstream_id": payload["workstream_id"],
            "supervisor_generation": self.engine.fence.generation,
            "successor_generation": payload["successor_generation"],
            "verified_checkpoint_id": payload["verified_checkpoint_id"],
            "verified_checkpoint_digest": payload["verified_checkpoint_digest"],
            "verified_checkpoint": payload["verified_checkpoint"],
            "required_result": "schema-bound checkpoint proving successor startup",
        }
        return "ORCHESTRATOR_V2_SUCCESSOR_PROOF\n" + json.dumps(
            envelope, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )

    def _canonical_result(
        self,
        turn: CodexTurnResult,
        payload: Mapping[str, Any],
        *,
        task_revision: int,
        workstream_revision: int,
        executor_generation: int,
        executor: ExecutorIdentity,
        result_event_id: str,
        created_at_override: str | None = None,
    ) -> Checkpoint | TerminalEvidence:
        created_at = created_at_override or _iso(self.clock())
        if isinstance(turn.contract, CodexCheckpoint):
            if payload["output_contract"] != "checkpoint":
                raise SupervisorRuntimeError("App Server returned the wrong output contract")
            return Checkpoint(
                checkpoint_id=_event_id("checkpoint", result_event_id),
                event_id=result_event_id,
                task_id=turn.contract.task_id,
                task_revision=task_revision,
                workstream_id=turn.contract.workstream_id,
                workstream_revision=workstream_revision,
                executor_generation=executor_generation,
                executor=executor,
                progress_stage=turn.contract.progress_percent,
                delta_ru=turn.contract.delta,
                current_ru=turn.contract.current_action,
                evidence=turn.contract.evidence,
                created_at=created_at,
            )
        if not isinstance(turn.contract, CodexTerminalEvidence) or payload["output_contract"] != "terminal":
            raise SupervisorRuntimeError("App Server returned the wrong output contract")
        if turn.contract.status != "completed":
            raise SupervisorRuntimeError("non-completed Codex output is not terminal technical closure")
        context = payload["terminal_context"]
        if not isinstance(context, Mapping):
            raise SupervisorRuntimeError("terminal closure lacks independently verified context")
        return TerminalEvidence(
            terminal_id=_event_id("terminal", result_event_id),
            event_id=result_event_id,
            task_id=turn.contract.task_id,
            task_revision=task_revision,
            workstream_id=turn.contract.workstream_id,
            workstream_revision=workstream_revision,
            executor_generation=executor_generation,
            executor=executor,
            closure_kind=str(context["closure_kind"]),
            summary_ru=turn.contract.summary,
            evidence=tuple(context["verified_evidence"]),
            checks=tuple(context["verified_checks"]),
            pr_identities=tuple(context["pr_identities"]),
            deploy_identities=tuple(context["deploy_identities"]),
            owner_acceptance_required=True,
            created_at=created_at,
        )

    def _validated_current_binding(self, payload: Mapping[str, Any]) -> tuple[Any, Any, Any]:
        with self._mutation_lock:
            task = self.registry.get_task(str(payload["task_id"]))
            workstream = self.registry.get_workstream(str(payload["workstream_id"]))
            executor = self.registry.current_executor(str(payload["task_id"]), str(payload["workstream_id"]))
        if task is None or workstream is None or executor is None:
            raise SupervisorRuntimeError("stale follow-up binding")
        observed = (
            task.revision,
            workstream.revision,
            executor.executor_generation,
            executor.thread_id,
            executor.host_id,
            executor.model,
            executor.reasoning,
        )
        expected = (
            payload["task_revision"],
            payload["workstream_revision"],
            payload["executor_generation"],
            payload["thread_id"],
            payload["host_id"],
            payload["model"],
            payload["reasoning"],
        )
        if observed != expected:
            raise SupervisorRuntimeError("stale follow-up binding")
        if executor.model != CODEX_APP_SERVER_MODEL or executor.reasoning != CODEX_APP_SERVER_REASONING_EFFORT:
            raise SupervisorRuntimeError("executor identity mismatch")
        return task, workstream, executor

    def _validated_thread_start_payload(self, value: Mapping[str, Any]) -> dict[str, Any]:
        required = {
            "schema", "passport", "workstream", "cwd", "message_id",
            "strategy_digest", "reconciliation_event_id", "started_thread", "start_intent"
        }
        _exact_fields(value, required, "thread start outbox")
        if value.get("schema") != THREAD_START_SCHEMA:
            raise SupervisorRuntimeError("thread start schema mismatch")
        payload = dict(value)
        payload["passport"] = dict(_mapping(value, "passport"))
        payload["workstream"] = dict(_mapping(value, "workstream"))
        self._workspace(value.get("cwd"))
        _machine("message_id", value.get("message_id"))
        _digest_value("strategy_digest", value.get("strategy_digest"))
        if value.get("reconciliation_event_id") is not None:
            _machine("reconciliation_event_id", value.get("reconciliation_event_id"))
        payload["start_intent"] = self._validated_start_intent(value.get("start_intent"))
        started = value.get("started_thread")
        if started is not None:
            _exact_fields(
                _mapping_value(started, "started_thread"),
                {"thread_id", "session_id", "host_id", "model", "reasoning", "ephemeral"},
                "started thread identity",
            )
            if started.get("model") != CODEX_APP_SERVER_MODEL or started.get("reasoning") != CODEX_APP_SERVER_REASONING_EFFORT:
                raise SupervisorRuntimeError("persisted thread identity mismatch")
            if started.get("ephemeral") is not False:
                raise SupervisorRuntimeError("executor thread must be persistent")
            _machine("thread_id", started.get("thread_id"))
            _machine("host_id", started.get("host_id"))
        return payload

    def _validated_followup_payload(self, value: Mapping[str, Any]) -> dict[str, Any]:
        required = {
            "schema", "task_id", "task_revision", "workstream_id", "workstream_revision",
            "executor_generation", "thread_id", "host_id", "model", "reasoning", "prompt",
            "output_contract", "cwd", "terminal_context", "causal_fingerprint", "message_id",
            "causal_binding", "call_intent", "call_policy", "model_attempt_count",
        }
        _exact_fields(value, required, "follow-up outbox")
        if value.get("schema") != FOLLOWUP_SCHEMA:
            raise SupervisorRuntimeError("follow-up schema mismatch")
        payload = dict(value)
        for key in ("task_id", "workstream_id", "thread_id", "host_id", "message_id"):
            _machine(key, payload[key])
        for key in ("task_revision", "workstream_revision", "executor_generation"):
            if isinstance(payload[key], bool) or not isinstance(payload[key], int) or payload[key] < 1:
                raise SupervisorRuntimeError(f"{key} must be positive")
        if payload["model"] != CODEX_APP_SERVER_MODEL or payload["reasoning"] != CODEX_APP_SERVER_REASONING_EFFORT:
            raise SupervisorRuntimeError("follow-up executor identity mismatch")
        if payload["causal_fingerprint"] is not None and (
            not isinstance(payload["causal_fingerprint"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", payload["causal_fingerprint"])
        ):
            raise SupervisorRuntimeError("follow-up causal fingerprint is invalid")
        if payload["causal_fingerprint"] is None:
            if payload["causal_binding"] is not None:
                raise SupervisorRuntimeError(
                    "follow-up causal binding requires a fingerprint"
                )
        else:
            payload["causal_binding"] = _validated_causal_binding(
                payload["causal_binding"],
                fingerprint=payload["causal_fingerprint"],
            )
        payload["call_intent"] = self._validated_call_intent(
            payload["call_intent"], "follow-up call intent"
        )
        if payload["call_policy"] not in {
            CALL_POLICY_STANDARD,
            CALL_POLICY_SINGLE_ATTEMPT_CANARY,
        }:
            raise SupervisorRuntimeError("follow-up call policy is invalid")
        attempts = payload["model_attempt_count"]
        if isinstance(attempts, bool) or not isinstance(attempts, int) or not 0 <= attempts <= 2:
            raise SupervisorRuntimeError("follow-up model attempt count is invalid")
        _prompt(payload["prompt"])
        workspace = self._workspace(payload["cwd"])
        self._assert_workspace_binding(
            str(payload["task_id"]), str(payload["workstream_id"]), workspace
        )
        if payload["output_contract"] not in {"checkpoint", "terminal"}:
            raise SupervisorRuntimeError("follow-up output contract mismatch")
        if (
            payload["call_policy"] == CALL_POLICY_SINGLE_ATTEMPT_CANARY
            and payload["output_contract"] != "checkpoint"
        ):
            raise SupervisorRuntimeError("single-attempt canary follow-up must be a checkpoint")
        payload["terminal_context"] = self._terminal_context(
            payload["terminal_context"], required=payload["output_contract"] == "terminal"
        )
        return payload

    def _assert_workspace_binding(
        self,
        task_id: str,
        workstream_id: str,
        workspace: Path,
    ) -> None:
        binding = self.registry.get_workspace_binding(task_id, workstream_id)
        if binding is None or binding.get("canonical_path") != str(workspace):
            raise SupervisorRuntimeError(
                "executor workspace is missing or differs from its immutable binding"
            )

    def _validated_start_intent(self, value: Any) -> dict[str, Any] | None:
        if value is None:
            return None
        intent = _mapping_value(value, "start_intent")
        _exact_fields(intent, {"supervisor_generation", "started_at"}, "thread start intent")
        generation = intent.get("supervisor_generation")
        if isinstance(generation, bool) or not isinstance(generation, int) or generation < 1:
            raise SupervisorRuntimeError("thread start intent generation is invalid")
        _rfc3339(intent.get("started_at"))
        return {
            "supervisor_generation": generation,
            "started_at": intent["started_at"],
        }

    def _validated_call_intent(self, value: Any, label: str) -> dict[str, Any] | None:
        if value is None:
            return None
        intent = _mapping_value(value, label)
        _exact_fields(intent, {"supervisor_generation", "started_at", "baseline_turn_ids"}, label)
        generation = intent.get("supervisor_generation")
        if isinstance(generation, bool) or not isinstance(generation, int) or generation < 1:
            raise SupervisorRuntimeError(f"{label} generation is invalid")
        _rfc3339(intent.get("started_at"))
        turns = intent.get("baseline_turn_ids")
        if not isinstance(turns, list) or len(turns) > 10_000:
            raise SupervisorRuntimeError(f"{label} turn baseline is invalid")
        for turn_id in turns:
            _machine("turn_id", turn_id)
        return {
            "supervisor_generation": generation,
            "started_at": intent["started_at"],
            "baseline_turn_ids": sorted(set(turns)),
        }

    def _terminal_context(self, value: Any, *, required: bool) -> dict[str, Any] | None:
        if value is None:
            if required:
                raise SupervisorCommandError("terminal follow-up requires independently verified terminal context")
            return None
        context = _mapping_value(value, "terminal_context")
        _exact_fields(
            context,
            {
                "schema", "closure_kind", "verification_source", "verified_evidence",
                "verified_checks", "pr_identities", "deploy_identities",
            },
            "terminal context",
        )
        if context.get("schema") != TERMINAL_CONTEXT_SCHEMA:
            raise SupervisorCommandError("terminal context schema mismatch")
        result = dict(context)
        for key in ("verified_evidence", "verified_checks", "pr_identities", "deploy_identities"):
            result[key] = list(_bounded_strings(key, context.get(key), required=key in {"verified_evidence", "verified_checks"}))
        closure = context.get("closure_kind")
        if closure not in {"release:done", "release:production", "diagnostic", "artifact"}:
            raise SupervisorCommandError("terminal context closure kind is invalid")
        if context.get("verification_source") not in {
            "github_release_train_readback",
            "diagnostic_verifier",
            "artifact_verifier",
        }:
            raise SupervisorCommandError("terminal verification source is not allowlisted")
        return result

    def _bound_prompt(self, payload: Mapping[str, Any]) -> str:
        required_contract_identity = {
            "task_id": payload["task_id"],
            "workstream_id": payload["workstream_id"],
            # The raw App Server checkpoint field named ``generation`` is the
            # Supervisor writer generation.  It is deliberately distinct from
            # the executor generation below; the per-turn output schema binds
            # the same three values with JSON-Schema ``const`` constraints.
            "generation": self.engine.fence.generation,
        }
        envelope = {
            "task_id": payload["task_id"],
            "task_revision": payload["task_revision"],
            "workstream_id": payload["workstream_id"],
            "workstream_revision": payload["workstream_revision"],
            "executor_generation": payload["executor_generation"],
            "supervisor_generation": self.engine.fence.generation,
            "required_contract_identity": required_contract_identity,
            "model": CODEX_APP_SERVER_MODEL,
            "reasoning": CODEX_APP_SERVER_REASONING_EFFORT,
            "output_contract": payload["output_contract"],
            "delivery_event_id": _event_id("bound-followup", payload["message_id"]),
        }
        return (
            "ORCHESTRATOR_V2_BOUND_ENVELOPE\n"
            + json.dumps(envelope, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            + "\nUNTRUSTED_TASK_INPUT\n"
            + str(payload["prompt"])
        )

    def _started_identity(self, identity: CodexThreadIdentity) -> dict[str, Any]:
        if identity.ephemeral:
            raise SupervisorRuntimeError("executor thread unexpectedly started ephemeral")
        return {
            "thread_id": identity.thread_id,
            "session_id": identity.session_id,
            "host_id": _event_id("mac-host", self.engine.supervisor_id),
            "model": CODEX_APP_SERVER_MODEL,
            "reasoning": CODEX_APP_SERVER_REASONING_EFFORT,
            "ephemeral": False,
        }

    def _new_start_intent(self) -> dict[str, Any]:
        return {
            "supervisor_generation": self.engine.fence.generation,
            "started_at": _iso(self.clock()),
        }

    def _new_call_intent(self, snapshot: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "supervisor_generation": self.engine.fence.generation,
            "started_at": _iso(self.clock()),
            "baseline_turn_ids": sorted(_thread_turn_ids(snapshot)),
        }

    def _new_call_intent_for_thread(
        self,
        client: CodexAppServerClient,
        thread_id: str,
        *,
        required_fresh_epoch: int | None = None,
    ) -> tuple[dict[str, Any], bool, int]:
        """Build a baseline, shortcutting only an exact same-epoch new thread."""

        epoch = client.connection_epoch
        if required_fresh_epoch is not None and (
            epoch != required_fresh_epoch
            or self._resumed_threads.get(thread_id) != required_fresh_epoch
        ):
            raise CodexAmbiguousOutcomeError(
                "preactivation canary cannot reconnect or resume its structural successor"
            )
        if (
            required_fresh_epoch is not None
            and self._preactivation_recovered_empty_thread_epochs.get(thread_id)
            == required_fresh_epoch
        ):
            return (
                {
                    "supervisor_generation": self.engine.fence.generation,
                    "started_at": _iso(self.clock()),
                    "baseline_turn_ids": [],
                },
                True,
                required_fresh_epoch,
            )
        if (
            epoch > 0
            and self._fresh_thread_epochs.get(thread_id) == epoch
            and self._resumed_threads.get(thread_id) == epoch
        ):
            baseline = client.fresh_empty_turn_baseline(thread_id)
            if baseline != ():
                error_type = (
                    CodexAmbiguousOutcomeError
                    if required_fresh_epoch is not None
                    else SupervisorRuntimeError
                )
                raise error_type(
                    "fresh thread baseline is unavailable on its start epoch"
                )
            return (
                {
                    "supervisor_generation": self.engine.fence.generation,
                    "started_at": _iso(self.clock()),
                    "baseline_turn_ids": [],
                },
                True,
                epoch,
            )
        if required_fresh_epoch is not None:
            raise CodexAmbiguousOutcomeError(
                "preactivation canary cannot fall back to thread history"
            )
        snapshot = client.read_thread_snapshot(thread_id, include_turns=True)
        self._ensure_thread_resumed(client, thread_id)
        return self._new_call_intent(snapshot), False, client.connection_epoch

    def _preactivation_canary_epoch(
        self,
        client: CodexAppServerClient,
        thread_id: str,
        executor_generation: int,
    ) -> int:
        """Return the immutable structural-start epoch without reconnecting."""

        if (
            not self._preactivation_qualification_mode
            or not self._preactivation_repair_complete.is_set()
            or self._preactivation_canary_complete.is_set()
        ):
            raise CodexAmbiguousOutcomeError(
                "single-attempt qualification canary is outside preactivation"
            )
        causal_remediation = self.preactivation_causal_remediation_mode
        state = (
            self.registry.preactivation_causal_remediation_state()
            if causal_remediation
            else self.registry.preactivation_structural_repair_state()
        )
        completion_id = state.get("completion_event_id")
        completion = (
            self.registry.get_event(str(completion_id))
            if isinstance(completion_id, str) and completion_id
            else None
        )
        payload = completion.get("payload") if completion is not None else None
        epoch = payload.get("app_server_connection_epoch") if isinstance(payload, Mapping) else None
        if (
            state.get("status") != "completed"
            or completion is None
            or completion.get("event_type")
            != (
                "preactivation_causal_remediation_completed"
                if causal_remediation
                else "preactivation_structural_repair_completed"
            )
            or not isinstance(payload, Mapping)
            or payload.get("successor_thread_id") != thread_id
            or payload.get("successor_executor_generation")
            != executor_generation
            or type(epoch) is not int
            or epoch < 1
        ):
            raise CodexAmbiguousOutcomeError(
                "preactivation canary lacks its exact structural completion epoch"
            )
        if self._preactivation_causal_completed_restart:
            snapshot = client.read_thread_snapshot(thread_id, include_turns=True)
            if (
                not isinstance(snapshot, Mapping)
                or snapshot.get("id") != thread_id
                or snapshot.get("turns") != []
            ):
                raise CodexAmbiguousOutcomeError(
                    "restarted preactivation canary requires an exact empty successor"
                )
            observed_epoch = client.connection_epoch
            if observed_epoch < 1:
                raise CodexAmbiguousOutcomeError(
                    "restarted preactivation canary read has no App Server epoch"
                )
            client.resume_thread(thread_id)
            if client.connection_epoch != observed_epoch:
                raise CodexAmbiguousOutcomeError(
                    "restarted preactivation canary changed epoch during resume"
                )
            self._resumed_threads[thread_id] = observed_epoch
            self._preactivation_recovered_empty_thread_epochs[
                thread_id
            ] = observed_epoch
            self._preactivation_recovered_snapshot_digest = _sha256(
                json.dumps(
                    snapshot,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
            executor = self.registry.current_executor(
                PREACTIVATION_STRUCTURAL_REPAIR_TASK_ID,
                PREACTIVATION_STRUCTURAL_REPAIR_WORKSTREAM_ID,
            )
            completion_event_id = state.get("completion_event_id")
            if (
                executor is None
                or executor.executor_generation != executor_generation
                or executor.thread_id != thread_id
                or not isinstance(completion_event_id, str)
                or not completion_event_id
            ):
                raise CodexAmbiguousOutcomeError(
                    "restarted preactivation canary executor binding changed"
                )
            restart_event_id = _event_id(
                "preactivation-causal-restart-attestation",
                completion_event_id + "|" + str(self.engine.fence.generation),
            )
            restart_attestation = {
                "schema": (
                    "dev-control-plane/preactivation-causal-restart-attestation/v3"
                ),
                "status": "empty_successor_recovered",
                "completion_event_id": completion_event_id,
                "task_id": PREACTIVATION_STRUCTURAL_REPAIR_TASK_ID,
                "workstream_id": PREACTIVATION_STRUCTURAL_REPAIR_WORKSTREAM_ID,
                "executor_generation": executor_generation,
                "thread_id": thread_id,
                "host_id": executor.host_id,
                "model": executor.model,
                "reasoning": executor.reasoning,
                "read_method": "thread/read",
                "resume_method": "thread/resume",
                "turn_count": 0,
                "thread_snapshot_digest": (
                    self._preactivation_recovered_snapshot_digest
                ),
                "app_server_connection_epoch": observed_epoch,
                "supervisor_generation": self.engine.fence.generation,
                "thread_start_performed": False,
                "model_call_performed": False,
                "raw_provider_body_stored": False,
            }
            with self._mutation_lock:
                restart_receipt = (
                    self.registry.record_preactivation_causal_restart_attestation(
                        event_id=restart_event_id,
                        attestation=restart_attestation,
                        fence=self.engine.fence,
                    )
                )
            self._preactivation_restart_attestation_event_id = str(
                restart_receipt["event_id"]
            )
            return observed_epoch
        return epoch

    def _consume_fresh_thread_baseline(
        self,
        client: CodexAppServerClient,
        thread_id: str,
        *,
        required_connection_epoch: int,
    ) -> None:
        epoch = client.connection_epoch
        if (
            self._preactivation_recovered_empty_thread_epochs.get(thread_id)
            == required_connection_epoch
            and epoch == required_connection_epoch
        ):
            self._preactivation_recovered_empty_thread_epochs.pop(
                thread_id, None
            )
            return
        if (
            self._fresh_thread_epochs.get(thread_id) != epoch
            or epoch != required_connection_epoch
        ):
            raise SupervisorRuntimeError(
                "fresh thread epoch changed before durable intent consumption"
            )
        client.consume_fresh_empty_turn_baseline(
            thread_id,
            required_connection_epoch=required_connection_epoch,
        )
        self._fresh_thread_epochs.pop(thread_id, None)

    def _ensure_thread_resumed(
        self,
        client: CodexAppServerClient,
        thread_id: str,
    ) -> None:
        client.connect()
        epoch = client.connection_epoch
        if epoch < 1:
            raise SupervisorRuntimeError("App Server connection epoch is unavailable")
        if self._resumed_threads.get(thread_id) == epoch:
            return
        client.resume_thread(thread_id)
        resumed_epoch = client.connection_epoch
        if resumed_epoch < epoch:
            raise SupervisorRuntimeError("App Server connection epoch regressed during resume")
        self._resumed_threads[thread_id] = resumed_epoch
        self._fresh_thread_epochs.pop(thread_id, None)

    def _client(self, *, extra_owned: Sequence[str] = ()) -> CodexAppServerClient:
        with self._client_lock:
            required = set(self._active_thread_ids()) | {str(item) for item in extra_owned}
            if self._codex_client is not None and not required <= set(self._codex_client.owned_thread_ids):
                self._codex_client.shutdown()
                self._codex_client = None
                self._resumed_threads.clear()
                self._fresh_thread_epochs.clear()
            if self._codex_client is None:
                self._codex_client = self._codex_client_factory(
                    generation=self.engine.fence.generation,
                    codex_bin=str(self.codex_bin),
                    model=CODEX_APP_SERVER_MODEL,
                    reasoning_effort=CODEX_APP_SERVER_REASONING_EFFORT,
                    sandbox="workspace-write",
                    approval_policy="never",
                    owned_thread_ids=tuple(sorted(required)),
                    is_stale_generation=self._is_stale_generation,
                )
            return self._codex_client

    def _is_stale_generation(self, generation: int) -> bool:
        current = self.registry.current_generation()
        return (
            generation != self.engine.fence.generation
            or current.get("generation") != self.engine.fence.generation
            or current.get("owner_id") != self.engine.fence.owner_id
            or float(current.get("expires_at") or 0) <= self.clock()
        )

    def _active_thread_ids(self) -> tuple[str, ...]:
        result: set[str] = set()
        for workstream in self.registry.list_workstreams():
            executor = self.registry.current_executor(workstream.task_id, workstream.workstream_id)
            if executor is not None:
                result.add(executor.thread_id)
        return tuple(sorted(result))

    def _workspace(self, value: Any) -> Path:
        if not isinstance(value, str) or not value or len(value) > 8_000:
            raise SupervisorCommandError("cwd must be a bounded workspace path")
        path = Path(value).expanduser()
        try:
            resolved = path.resolve(strict=True)
            root = self.allowed_workspace_root.resolve(strict=True)
        except OSError as exc:
            raise SupervisorCommandError("cwd is not an existing managed workspace") from exc
        if not resolved.is_dir() or (resolved != root and root not in resolved.parents):
            raise SupervisorCommandError("cwd is outside the managed workspace root")
        return resolved


class RuntimeEngineView:
    """Read-only HTTP-compatible view that includes runtime readiness."""

    def __init__(self, runtime: SupervisorRuntime) -> None:
        self.runtime = runtime

    def health(self) -> dict[str, Any]:
        return self.runtime.health()

    def readiness(self) -> dict[str, Any]:
        return self.runtime.readiness()

    def local_state(self) -> dict[str, Any]:
        return self.runtime.local_state()


class SupervisorRuntimeLoop:
    """Independent lease, projection, Codex, release and incident workers."""

    def __init__(
        self,
        runtime: SupervisorRuntime,
        *,
        maintenance_interval_seconds: float = 10.0,
        codex_poll_seconds: float = 1.0,
    ) -> None:
        if maintenance_interval_seconds <= 0 or codex_poll_seconds <= 0:
            raise SupervisorRuntimeError("runtime loop intervals must be positive")
        self.runtime = runtime
        self.maintenance_interval_seconds = float(maintenance_interval_seconds)
        self.codex_poll_seconds = float(codex_poll_seconds)
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    def start(self) -> None:
        if self._threads:
            raise SupervisorRuntimeError("runtime loop already started")
        self._threads = [
            threading.Thread(target=self._lease, name="dcp-v2-generation-lease", daemon=True),
            threading.Thread(target=self._maintenance, name="dcp-v2-maintenance", daemon=True),
            threading.Thread(target=self._codex, name="dcp-v2-codex-worker", daemon=True),
            threading.Thread(target=self._release, name="dcp-v2-release-worker", daemon=True),
            threading.Thread(target=self._incident, name="dcp-v2-incident-worker", daemon=True),
        ]
        for thread in self._threads:
            thread.start()

    def stop(self, *, timeout: float = 15.0) -> None:
        self._stop.set()
        for thread in self._threads:
            thread.join(timeout=timeout)
            if thread.is_alive():
                raise SupervisorRuntimeError("runtime worker did not stop")
        self._threads.clear()

    def _maintenance(self) -> None:
        while not self._stop.is_set():
            try:
                if not (
                    self.runtime._preactivation_qualification_mode
                    and not self.runtime.preactivation_repair_complete
                ):
                    self.runtime.maintenance_tick()
            except Exception as exc:
                self.runtime.engine._last_tick_error = _error_code(exc)
            self._stop.wait(self.maintenance_interval_seconds)

    def _lease(self) -> None:
        interval = max(0.05, min(5.0, self.runtime.registry.lease_seconds / 3.0))
        while not self._stop.is_set():
            try:
                self.runtime.renew_generation_lease()
            except Exception as exc:
                self.runtime.engine._last_tick_error = _error_code(exc)
            self._stop.wait(interval)

    def _codex(self) -> None:
        while not self._stop.is_set():
            try:
                if (
                    self.runtime._preactivation_qualification_mode
                    and not self.runtime.preactivation_repair_complete
                ):
                    result = self.runtime.process_preactivation_repair_once()
                else:
                    result = self.runtime.process_codex_once()
                delay = 0.01 if result.status not in {"idle", "disabled"} else self.codex_poll_seconds
            except Exception as exc:
                self.runtime._last_codex_error = _error_code(exc)
                delay = self.codex_poll_seconds
            self._stop.wait(delay)

    def _release(self) -> None:
        self._policy_worker(self.runtime.process_release_once)

    def _incident(self) -> None:
        self._policy_worker(self.runtime.process_incident_policy_once)

    def _policy_worker(self, worker: Callable[[], RuntimeWorkerResult]) -> None:
        while not self._stop.is_set():
            try:
                result = worker()
                delay = 0.01 if result.status not in {"idle", "disabled"} else self.codex_poll_seconds
            except Exception as exc:
                self.runtime.engine._last_tick_error = _error_code(exc)
                delay = self.codex_poll_seconds
            self._stop.wait(delay)


class _UnixCommandServer(socketserver.UnixStreamServer):
    allow_reuse_address = False

    def __init__(self, socket_path: Path, runtime: SupervisorRuntime) -> None:
        self.runtime = runtime
        self.socket_path = socket_path
        super().__init__(str(socket_path), _UnixCommandHandler, bind_and_activate=True)
        os.chmod(socket_path, 0o600)


class _UnixCommandHandler(socketserver.StreamRequestHandler):
    server: _UnixCommandServer

    def handle(self) -> None:
        raw = self.rfile.readline(MAX_COMMAND_BYTES + 1)
        request_id = "unknown"
        try:
            if not raw or len(raw) > MAX_COMMAND_BYTES or not raw.endswith(b"\n"):
                raise SupervisorCommandError("command frame is missing or oversized")
            request = json.loads(raw.decode("utf-8"))
            if not isinstance(request, Mapping):
                raise SupervisorCommandError("command frame must be an object")
            if isinstance(request.get("request_id"), str) and _MACHINE_RE.fullmatch(str(request["request_id"])):
                request_id = str(request["request_id"])
            response = self.server.runtime.handle_command(request)
        except Exception as exc:
            response = {
                "contract": RECEIPT_CONTRACT,
                "request_id": request_id,
                "ok": False,
                "result": None,
                "error": {"code": _error_code(exc), "message": "command rejected"},
            }
        body = json.dumps(response, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
        if len(body) <= MAX_COMMAND_BYTES:
            self.wfile.write(body)


class SupervisorCommandServer:
    """Lifecycle wrapper for the private 0600 mutation socket."""

    def __init__(self, runtime: SupervisorRuntime, socket_path: Path | str) -> None:
        path = Path(socket_path).expanduser().absolute()
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(path.parent, 0o700)
        if path.exists() or path.is_symlink():
            metadata = path.lstat()
            if not stat.S_ISSOCK(metadata.st_mode):
                raise SupervisorRuntimeError("command socket path is occupied by a non-socket")
            probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                probe.settimeout(0.2)
                probe.connect(str(path))
            except OSError:
                path.unlink()
            else:
                raise SupervisorRuntimeError("another command socket server is active")
            finally:
                probe.close()
        self.path = path
        self._server = _UnixCommandServer(path, runtime)
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            raise SupervisorRuntimeError("command socket server already started")
        self._thread = threading.Thread(target=self._server.serve_forever, name="dcp-v2-command-socket", daemon=True)
        self._thread.start()

    def stop(self, *, timeout: float = 10.0) -> None:
        if self._thread is not None:
            self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                raise SupervisorRuntimeError("command socket server did not stop")
            self._thread = None
        if self.path.exists() and stat.S_ISSOCK(self.path.lstat().st_mode):
            self.path.unlink()


class SupervisorCommandClient:
    """One-shot client used by the maintenance CLI and delivery bridge."""

    def __init__(self, socket_path: Path | str, *, timeout_seconds: float = 30.0) -> None:
        self.socket_path = Path(socket_path).expanduser().absolute()
        if timeout_seconds <= 0 or timeout_seconds > 300:
            raise SupervisorCommandError("command timeout is out of bounds")
        self.timeout_seconds = float(timeout_seconds)

    def request(self, command: str, payload: Mapping[str, Any], *, request_id: str) -> Any:
        _machine("command", command)
        _machine("request_id", request_id)
        if not isinstance(payload, Mapping):
            raise SupervisorCommandError("command payload must be an object")
        metadata = self.socket_path.lstat()
        if not stat.S_ISSOCK(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o600:
            raise SupervisorCommandError("command socket is missing or not private")
        if metadata.st_uid != os.getuid():
            raise SupervisorCommandError("command socket has a different owner")
        request = {
            "contract": COMMAND_CONTRACT,
            "command": command,
            "request_id": request_id,
            "payload": dict(payload),
        }
        body = json.dumps(request, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
        if len(body) > MAX_COMMAND_BYTES:
            raise SupervisorCommandError("command request exceeds the bounded frame")
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.settimeout(self.timeout_seconds)
        try:
            client.connect(str(self.socket_path))
            client.sendall(body)
            received = bytearray()
            while not received.endswith(b"\n"):
                chunk = client.recv(min(64 * 1024, MAX_COMMAND_BYTES + 1 - len(received)))
                if not chunk:
                    break
                received.extend(chunk)
                if len(received) > MAX_COMMAND_BYTES:
                    raise SupervisorCommandError("command receipt exceeds the bounded frame")
        finally:
            client.close()
        if not received.endswith(b"\n"):
            raise SupervisorCommandError("command server returned an incomplete receipt")
        response = json.loads(bytes(received).decode("utf-8"))
        _exact_fields(response, {"contract", "request_id", "ok", "result", "error"}, "command receipt")
        if response.get("contract") != RECEIPT_CONTRACT or response.get("request_id") != request_id:
            raise SupervisorCommandError("command receipt binding mismatch")
        if response.get("ok") is not True:
            error = response.get("error")
            code = str(error.get("code") if isinstance(error, Mapping) else "command_rejected")
            raise SupervisorCommandError(f"command rejected: {code}")
        if response.get("error") is not None:
            raise SupervisorCommandError("successful command receipt contains an error")
        return response.get("result")


def default_socket_path(state_dir: Path | str) -> Path:
    return Path(state_dir).expanduser().absolute() / DEFAULT_SOCKET_NAME


def _exact_fields(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    if not isinstance(value, Mapping) or set(value) != expected:
        raise SupervisorCommandError(f"{label} fields are invalid")


def _mapping(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    return _mapping_value(payload.get(key), key)


def _mapping_value(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SupervisorCommandError(f"{label} must be an object")
    return value


def _machine(label: str, value: Any) -> str:
    if not isinstance(value, str) or not _MACHINE_RE.fullmatch(value):
        raise SupervisorCommandError(f"{label} must be a bounded machine identifier")
    return value


def _claim_token(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{16,256}", value):
        raise SupervisorCommandError("claim_token must be one bounded opaque token")
    return value


def _digest_value(label: str, value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise SupervisorCommandError(f"{label} must be a sha256 digest")
    return value


def _prompt(value: Any) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_PROMPT_CHARS:
        raise SupervisorCommandError("prompt must be bounded non-empty text")
    if "\x00" in value or _CREDENTIAL_RE.search(value):
        raise SupervisorCommandError("prompt contains forbidden credential-shaped data")
    return value.strip()


def _bounded_strings(label: str, value: Any, *, required: bool) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)) or len(value) > 128:
        raise SupervisorCommandError(f"{label} must be a bounded array")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip() or len(item) > 2_000 or _CREDENTIAL_RE.search(item):
            raise SupervisorCommandError(f"{label} contains invalid text")
        result.append(item.strip())
    if required and not result:
        raise SupervisorCommandError(f"{label} must not be empty")
    return tuple(result)


def _incident_state_to_dict(state: IncidentState) -> dict[str, Any]:
    return asdict(state)


def _incident_state_from_mapping(value: Mapping[str, Any]) -> IncidentState:
    expected = set(IncidentState.__dataclass_fields__)
    _exact_fields(value, expected, "incident state")
    raw = dict(value)
    context_raw = _mapping(raw, "context")
    _exact_fields(context_raw, set(IncidentContext.__dataclass_fields__), "incident context")
    raw["context"] = IncidentContext(**dict(context_raw))
    return IncidentState(**raw)


def _release_train_candidate_from_mapping(value: Mapping[str, Any]) -> ReleaseTrainCandidate:
    expected = set(ReleaseTrainCandidate.__dataclass_fields__)
    _exact_fields(value, expected, "Release Train candidate")
    raw = dict(value)
    for key in ("required_checks", "declared_files", "resources"):
        raw[key] = _bounded_strings(key, raw[key], required=True)
    return ReleaseTrainCandidate(**raw)


def _validated_release_receipt(value: Mapping[str, Any]) -> dict[str, Any]:
    expected = {
        "schema", "status", "candidate_id", "task_id", "workstream_id", "task_revision",
        "workstream_revision", "pr_head_sha", "pr_url", "merge_sha", "deploy_identity",
        "contour", "verification_identity", "admission_binding", "completed_at",
    }
    _exact_fields(value, expected, "release receipt")
    if value.get("schema") != "dev-control-plane/release-action-receipt/v2" or value.get("status") != "passed":
        raise SupervisorCommandError("release receipt must prove a passed result")
    result = dict(value)
    for key in ("candidate_id", "task_id", "workstream_id"):
        _machine(key, result[key])
    for key in ("task_revision", "workstream_revision"):
        if isinstance(result[key], bool) or not isinstance(result[key], int) or result[key] < 1:
            raise SupervisorCommandError("release receipt revision is invalid")
    for key in ("pr_head_sha", "merge_sha"):
        if not isinstance(result[key], str) or not re.fullmatch(r"[0-9a-f]{40}", result[key]):
            raise SupervisorCommandError(f"release receipt {key} is invalid")
    if not isinstance(result["pr_url"], str) or not result["pr_url"].startswith("https://github.com/"):
        raise SupervisorCommandError("release receipt PR URL is invalid")
    contour = result.get("contour")
    deploy_identity = result.get("deploy_identity")
    if contour == "release:done":
        if deploy_identity is not None:
            raise SupervisorCommandError(
                "release:done receipt cannot claim a hosted deployment"
            )
    elif contour == "release:production":
        if (
            not isinstance(deploy_identity, str)
            or not deploy_identity.startswith("hosted-release-v1:")
            or len(deploy_identity) > 1_000
            or _CREDENTIAL_RE.search(deploy_identity)
        ):
            raise SupervisorCommandError(
                "release:production receipt requires an immutable hosted release"
            )
    else:
        raise SupervisorCommandError("release receipt contour is invalid")
    verification = result.get("verification_identity")
    if (
        not isinstance(verification, str)
        or not verification.strip()
        or len(verification) > 1_000
        or _CREDENTIAL_RE.search(verification)
    ):
        raise SupervisorCommandError("release receipt verification_identity is missing")
    admission = result.get("admission_binding")
    if admission is not None:
        expected_admission = {
            "schema",
            "target_id",
            "pr_number",
            "owner_pr",
            "head_sha",
            "target_task_id",
            "task_revision",
            "passport_digest",
            "proof_digest",
        }
        _exact_fields(admission, expected_admission, "release admission binding")
        if (
            admission.get("schema")
            != "dev-control-plane/wb-core-admission-binding/v2"
            or admission.get("target_id") != "orenvlad-ai/wb-core"
            or admission.get("head_sha") != result["pr_head_sha"]
            or admission.get("task_revision") != result["task_revision"]
        ):
            raise SupervisorCommandError("release admission binding is stale")
        for name in ("pr_number", "owner_pr", "task_revision"):
            item = admission.get(name)
            if isinstance(item, bool) or not isinstance(item, int) or item < 1:
                raise SupervisorCommandError(
                    "release admission binding numeric identity is invalid"
                )
        _machine("target_task_id", admission.get("target_task_id"))
        for name in ("head_sha",):
            if not isinstance(admission.get(name), str) or not re.fullmatch(
                r"[0-9a-f]{40}", str(admission.get(name))
            ):
                raise SupervisorCommandError(
                    "release admission binding head is invalid"
                )
        for name in ("passport_digest", "proof_digest"):
            if not isinstance(admission.get(name), str) or not re.fullmatch(
                r"[0-9a-f]{64}", str(admission.get(name))
            ):
                raise SupervisorCommandError(
                    "release admission binding digest is invalid"
                )
        result["admission_binding"] = dict(admission)
    _rfc3339(result["completed_at"])
    return result


def _validated_target_lane_closure_receipt(
    value: Mapping[str, Any],
    action: Mapping[str, Any],
) -> dict[str, Any]:
    expected_fields = {
        "schema", "status", "closure_id", "supervisor_generation", "task_id",
        "task_revision", "workstream_id", "workstream_revision", "target_id",
        "logical_lane_id", "outcome", "closure_event_id", "closure_event_digest",
        "reason_code", "evidence_digest", "retry_after_seconds", "observed_at",
    }
    _exact_fields(value, expected_fields, "target lane closure receipt")
    if value.get("schema") != TARGET_LANE_CLOSURE_RECEIPT_SCHEMA:
        raise SupervisorRuntimeError("target lane closure receipt schema mismatch")
    status = value.get("status")
    if status not in {"submitted", "released", "parked"}:
        raise SupervisorRuntimeError("target lane closure receipt status is invalid")
    if (status == "released" and action.get("outcome") != "completed") or (
        status == "parked" and action.get("outcome") != "parked"
    ):
        raise SupervisorRuntimeError("target lane closure receipt outcome/status mismatch")
    if status == "submitted":
        retry_after = value.get("retry_after_seconds")
        if (
            isinstance(retry_after, bool)
            or not isinstance(retry_after, (int, float))
            or not 1 <= float(retry_after) <= 3_600
        ):
            raise SupervisorRuntimeError("target lane closure submission retry is invalid")
    elif value.get("retry_after_seconds") is not None:
        raise SupervisorRuntimeError("terminal target lane closure cannot request a retry")
    for name in (
        "closure_id", "task_id", "workstream_id", "logical_lane_id", "outcome",
        "closure_event_id", "reason_code",
    ):
        _machine(name, value.get(name))
    target_id = value.get("target_id")
    if (
        not isinstance(target_id, str)
        or not target_id
        or len(target_id) > 200
        or any(character.isspace() or ord(character) < 33 for character in target_id)
        or _CREDENTIAL_RE.search(target_id)
    ):
        raise SupervisorRuntimeError("target lane closure receipt target_id is invalid")
    for name in ("closure_event_digest", "evidence_digest"):
        digest = value.get(name)
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise SupervisorRuntimeError(f"target lane closure receipt {name} is invalid")
    for name in ("supervisor_generation", "task_revision", "workstream_revision"):
        observed = value.get(name)
        if isinstance(observed, bool) or not isinstance(observed, int) or observed < 1:
            raise SupervisorRuntimeError(f"target lane closure receipt {name} is invalid")
    binding_fields = (
        "closure_id", "supervisor_generation", "task_id", "task_revision",
        "workstream_id", "workstream_revision", "target_id", "logical_lane_id",
        "outcome", "closure_event_id", "closure_event_digest",
    )
    if tuple(value.get(name) for name in binding_fields) != tuple(
        action.get(name) for name in binding_fields
    ):
        raise SupervisorRuntimeError("target lane closure receipt binding is stale")
    _rfc3339(value.get("observed_at"))
    return dict(value)


def _validated_release_observation(value: Mapping[str, Any]) -> dict[str, Any]:
    expected = {
        "schema", "status", "reason_code", "candidate_id", "task_id",
        "workstream_id", "task_revision", "workstream_revision", "expected_head_sha",
        "observed_head_sha", "retry_after_seconds", "observed_at", "evidence",
        "admission_binding",
    }
    _exact_fields(value, expected, "release observation")
    result = dict(value)
    statuses = {
        "admission_submitted", "admitted", "waiting_foreign_lane",
        "waiting_release", "readmission_required",
    }
    if (
        result.get("schema") != "dev-control-plane/release-action-observation/v2"
        or result.get("status") not in statuses
    ):
        raise SupervisorCommandError("release observation status is invalid")
    for key in ("reason_code", "candidate_id", "task_id", "workstream_id"):
        _machine(key, result.get(key))
    for key in ("task_revision", "workstream_revision"):
        if isinstance(result.get(key), bool) or not isinstance(result.get(key), int) or result[key] < 1:
            raise SupervisorCommandError("release observation revision is invalid")
    for key in ("expected_head_sha", "observed_head_sha"):
        if not isinstance(result.get(key), str) or not re.fullmatch(r"[0-9a-f]{40}", result[key]):
            raise SupervisorCommandError(f"release observation {key} is invalid")
    retry = result.get("retry_after_seconds")
    if result["status"] == "readmission_required":
        if retry is not None:
            raise SupervisorCommandError("release readmission cannot carry a polling delay")
    elif (
        isinstance(retry, bool)
        or not isinstance(retry, (int, float))
        or not 1 <= float(retry) <= 3_600
    ):
        raise SupervisorCommandError("release observation retry delay is out of bounds")
    _rfc3339(result.get("observed_at"))
    result["evidence"] = list(_bounded_strings("release observation evidence", result.get("evidence"), required=False))
    raw_admission = result.get("admission_binding")
    if raw_admission is None:
        pass
    else:
        if result["status"] not in {"admitted", "waiting_release"}:
            raise SupervisorCommandError(
                "pre-admission/readmission observation cannot carry admission binding"
            )
        try:
            admission = wb_core_admission_binding_from_mapping(
                _mapping(result, "admission_binding")
            )
        except (TypeError, ValueError) as exc:
            raise SupervisorCommandError(
                "release observation admission binding is malformed"
            ) from exc
        if (
            admission.target_id != WB_CORE_REPOSITORY
            or admission.head_sha != result["expected_head_sha"]
            or admission.head_sha != result["observed_head_sha"]
            or admission.target_task_id
            != derive_wb_core_target_task_id(str(result["task_id"]))
            or admission.task_revision != result["task_revision"]
            or f"admission:sha256:{admission.proof_digest}"
            not in tuple(result["evidence"])
        ):
            raise SupervisorCommandError(
                "release observation admission binding is stale or cross-bound"
            )
        result["admission_binding"] = dict(raw_admission)
    return result


def _rfc3339(value: Any) -> str:
    if not isinstance(value, str) or not value or len(value) > 100:
        raise SupervisorCommandError("timestamp must be RFC3339")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SupervisorCommandError("timestamp must be RFC3339") from exc
    if parsed.tzinfo is None:
        raise SupervisorCommandError("timestamp must include a timezone")
    return value


def _thread_turn_ids(snapshot: Mapping[str, Any]) -> set[str]:
    turns = snapshot.get("turns")
    if turns is None:
        return set()
    if not isinstance(turns, list) or len(turns) > 10_000:
        raise SupervisorRuntimeError("thread snapshot has an invalid turn history")
    result: set[str] = set()
    for turn in turns:
        if not isinstance(turn, Mapping):
            raise SupervisorRuntimeError("thread snapshot contains an invalid turn")
        result.add(_machine("turn_id", turn.get("id")))
    return result


def _event_id(prefix: str, value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.:-]+", "-", prefix).strip("-") or "event"
    return f"{normalized}:{_sha256(value)[:48]}"


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _private_file_sha256(path: Path, *, expected_parent: Path) -> str:
    """Hash one exact private regular file without following an alias."""

    candidate = Path(os.path.abspath(path))
    parent = Path(os.path.abspath(expected_parent)).resolve(strict=True)
    metadata = candidate.lstat()
    if (
        candidate.parent.resolve(strict=True) != parent
        or stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or metadata.st_nlink != 1
        or stat.S_IMODE(metadata.st_mode) != 0o600
    ):
        raise SupervisorCommandError(
            "preactivation repair backup lost private file identity"
        )
    digest = hashlib.sha256()
    with candidate.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    repeated = candidate.lstat()
    if (repeated.st_dev, repeated.st_ino, repeated.st_size) != (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
    ):
        raise SupervisorCommandError(
            "preactivation repair backup changed during hashing"
        )
    return digest.hexdigest()


def _manifest_digest(manifest: ReleaseClosureManifest) -> str:
    return _sha256(
        json.dumps(
            contract_to_dict(manifest),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )


def _validated_causal_binding(value: Any, *, fingerprint: str) -> dict[str, Any]:
    binding = _mapping_value(value, "causal_binding")
    expected = {
        "schema",
        "stage",
        "check_kind",
        "error_code",
        "normalized_cause_code",
        "fingerprint",
    }
    _exact_fields(binding, expected, "causal binding")
    if binding.get("schema") != CAUSAL_BINDING_SCHEMA:
        raise SupervisorRuntimeError("causal binding schema mismatch")
    result = dict(binding)
    for name in ("stage", "check_kind", "error_code", "normalized_cause_code"):
        _machine(name, result.get(name))
    if (
        result.get("fingerprint") != fingerprint
        or not isinstance(fingerprint, str)
        or not re.fullmatch(r"[0-9a-f]{64}", fingerprint)
    ):
        raise SupervisorRuntimeError("causal binding fingerprint mismatch")
    return result


def _normalized_cause_code(exc: BaseException) -> str:
    if isinstance(exc, CodexAmbiguousOutcomeError):
        return "ambiguous_provider_outcome"
    if isinstance(
        exc,
        (
            CodexDisconnectedError,
            CodexRequestTimeout,
            CodexTurnTimeout,
            ConnectionError,
            TimeoutError,
            BrokenPipeError,
        ),
    ):
        return "transport_unavailable"
    if isinstance(
        exc,
        (
            CodexIdentityMismatchError,
            CodexThreadOwnershipError,
            CodexStaleGenerationError,
        ),
    ):
        return "executor_identity_mismatch"
    if isinstance(
        exc,
        (CodexContractError, OrchestrationValidationError, SupervisorError),
    ):
        return "schema_or_contour_invalid"
    if isinstance(exc, CodexProtocolError):
        return "app_server_protocol_invalid"
    return "runtime_failure_" + _error_code(exc)


def _failure_binding(message: OutboxMessage, exc: BaseException) -> dict[str, Any]:
    task_id = str(message.payload.get("task_id") or message.task_id or "unknown-task")
    workstream_id = str(message.payload.get("workstream_id") or "unknown-workstream")
    if message.kind == "codex_successor_start":
        original = message.payload.get("original_followup")
        output_contract = (
            str(original.get("output_contract") or "none")
            if isinstance(original, Mapping)
            else "none"
        )
        stage = "codex_successor_proof"
    else:
        output_contract = str(message.payload.get("output_contract") or "none")
        stage = "codex_followup" if message.kind == "codex_followup" else message.kind
    core = {
        "schema": CAUSAL_BINDING_SCHEMA,
        "stage": stage,
        "check_kind": f"{output_contract}_contract",
        "error_code": _error_code(exc),
        "normalized_cause_code": _normalized_cause_code(exc),
    }
    inherited = message.payload.get("causal_binding")
    if message.kind == "codex_successor_start" and isinstance(inherited, Mapping):
        # The successor proof is a remediation stage, not a new causal root.
        # Preserve the exact root when the typed cause/error/check are equal;
        # a genuinely changed cause is fingerprinted below as a new budget.
        comparable = ("check_kind", "error_code", "normalized_cause_code")
        if all(inherited.get(name) == core[name] for name in comparable):
            inherited_fingerprint = inherited.get("fingerprint")
            if (
                inherited.get("schema") == CAUSAL_BINDING_SCHEMA
                and isinstance(inherited_fingerprint, str)
                and re.fullmatch(r"[0-9a-f]{64}", inherited_fingerprint)
            ):
                return dict(inherited)
    fingerprint = _sha256(
        json.dumps(
            {
                "task_id": task_id,
                "workstream_id": workstream_id,
                **core,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return {**core, "fingerprint": fingerprint}


def _failure_fingerprint(message: OutboxMessage, exc: Exception) -> str:
    observed = _failure_binding(message, exc)
    inherited = message.payload.get("causal_fingerprint")
    inherited_binding = message.payload.get("causal_binding")
    if (
        isinstance(inherited, str)
        and re.fullmatch(r"[0-9a-f]{64}", inherited)
        and isinstance(inherited_binding, Mapping)
        and dict(inherited_binding) == observed
        and inherited == observed["fingerprint"]
    ):
        return inherited
    return str(observed["fingerprint"])


def _error_code(exc: BaseException) -> str:
    name = type(exc).__name__
    code = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
    return code[:120] or "runtime_error"


def _iso(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat().replace("+00:00", "Z")


def _validated_codex_binary(explicit: Path | str | None) -> Path:
    configured = explicit or os.environ.get("DEV_CONTROL_PLANE_CODEX_BIN") or DEFAULT_DESKTOP_CODEX_BIN
    if not isinstance(configured, (str, os.PathLike)):
        raise SupervisorRuntimeError("Codex binary must be an absolute path")
    candidate = Path(configured).expanduser()
    if not candidate.is_absolute():
        raise SupervisorRuntimeError("Codex binary must be an absolute path")
    try:
        resolved = candidate.resolve(strict=True)
        metadata = resolved.stat()
    except OSError as exc:
        raise SupervisorRuntimeError("configured Codex binary is missing") from exc
    if not stat.S_ISREG(metadata.st_mode) or not os.access(resolved, os.X_OK):
        raise SupervisorRuntimeError("configured Codex binary is not an executable regular file")
    return resolved
