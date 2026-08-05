"""Bounded official Codex App Server adapter for Supervisor-owned threads.

The adapter deliberately owns one ``codex app-server`` child over stdio.  It
does not attach to the Desktop process, expose a socket, use the Codex SDK, or
read Codex's internal SQLite schema.  Orchestration truth remains outside this
module; this transport only validates identity, serializes turns and exposes
structural lifecycle evidence.
"""

from __future__ import annotations

from collections import deque
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict, dataclass, field
import json
import os
import random
import re
import signal
import subprocess
import threading
import time
from typing import Any, Callable, Iterable, Iterator, Literal, Mapping, Sequence


CODEX_APP_SERVER_MODEL = "gpt-5.6-sol"
CODEX_APP_SERVER_REASONING_EFFORT = "ultra"
CHECKPOINT_SCHEMA_VERSION = "dev-control-plane.codex-checkpoint.v1"
TERMINAL_SCHEMA_VERSION = "dev-control-plane.codex-terminal.v1"

DEFAULT_REQUEST_TIMEOUT_SECONDS = 30.0
DEFAULT_TURN_TIMEOUT_SECONDS = 3 * 60 * 60.0
DEFAULT_SHUTDOWN_TIMEOUT_SECONDS = 5.0
DEFAULT_MAX_RECONNECT_ATTEMPTS = 2
DEFAULT_RECONNECT_BACKOFF_SECONDS = 0.25
MAX_JSON_LINE_CHARS = 32 * 1024 * 1024
MAX_REQUEST_CHARS = 2 * 1024 * 1024
MAX_STDERR_LINE_CHARS = 2_000
MAX_STDERR_LINES = 100
MAX_LIFECYCLE_EVENTS = 10_000
MAX_TURN_EVENTS = 1_000
MAX_RECOVERY_BASELINE_TURNS = 50_000
MAX_RECOVERY_ITEMS = 50_000

# The executor may invoke workspace tools, but it must not inherit ambient
# provider/GitHub/SSH credentials from the Supervisor process.  Codex Desktop
# subscription auth is discovered through HOME/CODEX_HOME, both of which are
# paths rather than bearer values.  Tests may still pass an explicit bounded
# environment to the adapter; production callers do not use that escape hatch.
_INHERITED_ENV_ALLOWLIST = frozenset(
    {
        "CODEX_HOME",
        "HOME",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "LOGNAME",
        "PATH",
        "SHELL",
        "SSL_CERT_DIR",
        "SSL_CERT_FILE",
        "TEMP",
        "TMP",
        "TMPDIR",
        "USER",
        "XDG_CACHE_HOME",
        "XDG_CONFIG_HOME",
    }
)

CheckpointStage = Literal[
    "started",
    "preflight",
    "implementation",
    "diff_ready",
    "initial_checks",
    "full_checks",
    "pr",
    "release",
    "deployed",
    "recovery",
    "blocked",
]
TerminalStatus = Literal["completed", "blocked", "failed"]
TerminalCheckStatus = Literal["passed", "failed", "blocked", "skipped"]
OutputContract = Literal["checkpoint", "terminal"]
LifecycleEvidenceSource = Literal["notification", "thread_read_snapshot"]
SandboxMode = Literal["read-only", "workspace-write", "danger-full-access"]
ApprovalPolicy = Literal["untrusted", "on-request", "never"]

CANONICAL_PROGRESS_VALUES = frozenset({5, 15, 25, 40, 55, 65, 72, 80, 88, 95, 100})
CHECKPOINT_PROGRESS_VALUES = CANONICAL_PROGRESS_VALUES - {100}
CHECKPOINT_STAGES = frozenset(
    {
        "started",
        "preflight",
        "implementation",
        "diff_ready",
        "initial_checks",
        "full_checks",
        "pr",
        "release",
        "deployed",
        "recovery",
        "blocked",
    }
)
TERMINAL_STATUSES = frozenset({"completed", "blocked", "failed"})
TERMINAL_CHECK_STATUSES = frozenset({"passed", "failed", "blocked", "skipped"})
SANDBOX_MODES = frozenset({"read-only", "workspace-write", "danger-full-access"})
APPROVAL_POLICIES = frozenset({"untrusted", "on-request", "never"})
APPROVALS_REVIEWER = "user"
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$")
_ANSI_RE = re.compile(r"\x1b(?:[@-_][0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")
_SECRET_PATTERNS = (
    (re.compile(r"(Authorization\s*:\s*Bearer\s+)\S+", re.IGNORECASE), r"\1[REDACTED]"),
    (re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}", re.IGNORECASE), "Bearer [REDACTED]"),
    (
        re.compile(
            r"\b(api[_-]?key|access[_-]?token|refresh[_-]?token|id[_-]?token|client[_-]?secret)"
            r"\s*[:=]\s*[^\s,;]+",
            re.IGNORECASE,
        ),
        r"\1=[REDACTED]",
    ),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{8,}"), "[REDACTED]"),
)


class CodexAppServerError(RuntimeError):
    """Base class for bounded App Server failures."""


class CodexProtocolError(CodexAppServerError):
    """The peer violated the expected JSON-RPC or lifecycle contract."""


class CodexRemoteError(CodexAppServerError):
    """The App Server returned a JSON-RPC error."""

    def __init__(self, method: str, code: int | None, message: str) -> None:
        self.method = method
        self.code = code
        super().__init__(f"Codex App Server {method} failed ({code}): {_sanitize_text(message, 500)}")


class CodexRequestTimeout(CodexAppServerError):
    """A bounded JSON-RPC request or serialization wait expired."""


class CodexTurnTimeout(CodexAppServerError):
    """A turn did not reach a terminal lifecycle notification in time."""


class CodexDisconnectedError(CodexAppServerError):
    """The owned stdio child disconnected."""


class CodexAmbiguousOutcomeError(CodexDisconnectedError):
    """A mutating request disconnected and must be reconciled, not retried."""


class CodexIdentityMismatchError(CodexAppServerError):
    """The observed model identity does not match the required identity."""


class CodexThreadOwnershipError(CodexAppServerError):
    """A mutating thread operation targeted a non-Supervisor-owned id."""


class CodexStaleGenerationError(CodexAppServerError):
    """The adapter generation has been fenced as stale."""


class CodexContractError(CodexAppServerError):
    """Schema-bound checkpoint or terminal evidence is invalid."""


class CodexTurnFailedError(CodexAppServerError):
    """Codex completed the transport turn with a non-success status."""


@dataclass(frozen=True)
class CodexCheckpoint:
    schema_version: str
    kind: Literal["checkpoint"]
    task_id: str
    workstream_id: str
    generation: int
    stage: CheckpointStage
    progress_percent: int
    delta: str
    current_action: str
    evidence: tuple[str, ...]
    causal_fingerprint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CodexTerminalCheck:
    name: str
    status: TerminalCheckStatus
    evidence: str


@dataclass(frozen=True)
class CodexTerminalEvidence:
    schema_version: str
    kind: Literal["terminal"]
    task_id: str
    workstream_id: str
    generation: int
    status: TerminalStatus
    summary: str
    checks: tuple[CodexTerminalCheck, ...]
    artifacts: tuple[str, ...]
    limitations: tuple[str, ...]
    blocker: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CodexModelAttestation:
    model: str
    reasoning_effort: str
    supported_reasoning_efforts: tuple[str, ...]
    connection_epoch: int


@dataclass(frozen=True)
class CodexThreadIdentity:
    thread_id: str
    session_id: str | None
    model_provider: str | None
    source: str | None
    status: str | None
    ephemeral: bool


@dataclass(frozen=True)
class CodexLifecycleEvent:
    method: str
    thread_id: str | None
    turn_id: str | None
    item_id: str | None
    item_type: str | None
    status: str | None
    connection_epoch: int
    evidence_source: LifecycleEvidenceSource = "notification"

    @property
    def dedupe_key(self) -> tuple[str, str, str, str, str]:
        return (
            self.method,
            self.thread_id or "",
            self.turn_id or "",
            self.item_id or "",
            self.status or "",
        )


@dataclass(frozen=True)
class CodexTurnResult:
    thread_id: str
    turn_id: str
    status: str
    contract: CodexCheckpoint | CodexTerminalEvidence
    events: tuple[CodexLifecycleEvent, ...]


@dataclass(frozen=True)
class CodexReconciliation:
    thread_id: str
    thread_status: str | None
    new_turn_ids: tuple[str, ...]
    new_item_ids: tuple[str, ...]
    terminal_turn_ids: tuple[str, ...]


@dataclass
class _PendingResponse:
    event: threading.Event = field(default_factory=threading.Event)
    response: Mapping[str, Any] | None = None
    error: BaseException | None = None


def checkpoint_output_schema() -> dict[str, Any]:
    """Return a fresh JSON Schema for a durable progress checkpoint."""

    return deepcopy(_CHECKPOINT_OUTPUT_SCHEMA)


def terminal_output_schema() -> dict[str, Any]:
    """Return a fresh JSON Schema for terminal technical evidence."""

    return deepcopy(_TERMINAL_OUTPUT_SCHEMA)


def validate_checkpoint_payload(
    payload: Mapping[str, Any],
    *,
    expected_generation: int | None = None,
    expected_task_id: str | None = None,
    expected_workstream_id: str | None = None,
) -> CodexCheckpoint:
    _require_mapping(payload, "checkpoint")
    _require_exact_keys(
        payload,
        required={
            "schema_version",
            "kind",
            "task_id",
            "workstream_id",
            "generation",
            "stage",
            "progress_percent",
            "delta",
            "current_action",
            "evidence",
            "causal_fingerprint",
        },
        optional=set(),
        label="checkpoint",
    )
    if payload.get("schema_version") != CHECKPOINT_SCHEMA_VERSION or payload.get("kind") != "checkpoint":
        raise CodexContractError("checkpoint schema identity mismatch")
    task_id = _validated_id(payload.get("task_id"), "checkpoint.task_id")
    workstream_id = _validated_id(payload.get("workstream_id"), "checkpoint.workstream_id")
    generation = _contract_positive_int(payload.get("generation"), "checkpoint.generation")
    stage = str(payload.get("stage") or "")
    if stage not in CHECKPOINT_STAGES:
        raise CodexContractError("checkpoint.stage is not canonical")
    progress = payload.get("progress_percent")
    if type(progress) is not int or progress not in CHECKPOINT_PROGRESS_VALUES:
        raise CodexContractError("checkpoint.progress_percent must be a canonical non-terminal stage")
    delta = _contract_text(payload.get("delta"), "checkpoint.delta", 2_000)
    current_action = _contract_text(payload.get("current_action"), "checkpoint.current_action", 2_000)
    evidence = _bounded_text_sequence(payload.get("evidence"), "checkpoint.evidence", max_items=64, max_chars=2_000)
    fingerprint_value = payload.get("causal_fingerprint")
    fingerprint = (
        None
        if fingerprint_value is None
        else _contract_text(fingerprint_value, "checkpoint.causal_fingerprint", 500)
    )
    _validate_expected_identity(
        generation=generation,
        task_id=task_id,
        workstream_id=workstream_id,
        expected_generation=expected_generation,
        expected_task_id=expected_task_id,
        expected_workstream_id=expected_workstream_id,
    )
    return CodexCheckpoint(
        schema_version=CHECKPOINT_SCHEMA_VERSION,
        kind="checkpoint",
        task_id=task_id,
        workstream_id=workstream_id,
        generation=generation,
        stage=stage,  # type: ignore[arg-type]
        progress_percent=progress,
        delta=delta,
        current_action=current_action,
        evidence=evidence,
        causal_fingerprint=fingerprint,
    )


def validate_terminal_payload(
    payload: Mapping[str, Any],
    *,
    expected_generation: int | None = None,
    expected_task_id: str | None = None,
    expected_workstream_id: str | None = None,
) -> CodexTerminalEvidence:
    _require_mapping(payload, "terminal")
    _require_exact_keys(
        payload,
        required={
            "schema_version",
            "kind",
            "task_id",
            "workstream_id",
            "generation",
            "status",
            "summary",
            "checks",
            "artifacts",
            "limitations",
            "blocker",
        },
        optional=set(),
        label="terminal",
    )
    if payload.get("schema_version") != TERMINAL_SCHEMA_VERSION or payload.get("kind") != "terminal":
        raise CodexContractError("terminal schema identity mismatch")
    task_id = _validated_id(payload.get("task_id"), "terminal.task_id")
    workstream_id = _validated_id(payload.get("workstream_id"), "terminal.workstream_id")
    generation = _contract_positive_int(payload.get("generation"), "terminal.generation")
    status = str(payload.get("status") or "")
    if status not in TERMINAL_STATUSES:
        raise CodexContractError("terminal.status is invalid")
    summary = _contract_text(payload.get("summary"), "terminal.summary", 4_000)
    checks_raw = payload.get("checks")
    if not isinstance(checks_raw, list) or len(checks_raw) > 128:
        raise CodexContractError("terminal.checks must be a bounded array")
    checks: list[CodexTerminalCheck] = []
    for index, raw_check in enumerate(checks_raw):
        _require_mapping(raw_check, f"terminal.checks[{index}]")
        _require_exact_keys(
            raw_check,
            required={"name", "status", "evidence"},
            optional=set(),
            label=f"terminal.checks[{index}]",
        )
        check_status = str(raw_check.get("status") or "")
        if check_status not in TERMINAL_CHECK_STATUSES:
            raise CodexContractError(f"terminal.checks[{index}].status is invalid")
        checks.append(
            CodexTerminalCheck(
                name=_contract_text(raw_check.get("name"), f"terminal.checks[{index}].name", 300),
                status=check_status,  # type: ignore[arg-type]
                evidence=_contract_text(
                    raw_check.get("evidence"),
                    f"terminal.checks[{index}].evidence",
                    2_000,
                ),
            )
        )
    artifacts = _bounded_text_sequence(payload.get("artifacts"), "terminal.artifacts", max_items=128, max_chars=2_000)
    limitations = _bounded_text_sequence(payload.get("limitations"), "terminal.limitations", max_items=64, max_chars=2_000)
    blocker_value = payload.get("blocker")
    blocker = None if blocker_value is None else _contract_text(blocker_value, "terminal.blocker", 2_000)
    if status == "completed" and blocker is not None:
        raise CodexContractError("completed terminal evidence cannot include a blocker")
    if status in {"blocked", "failed"} and blocker is None:
        raise CodexContractError("blocked or failed terminal evidence requires blocker")
    _validate_expected_identity(
        generation=generation,
        task_id=task_id,
        workstream_id=workstream_id,
        expected_generation=expected_generation,
        expected_task_id=expected_task_id,
        expected_workstream_id=expected_workstream_id,
    )
    return CodexTerminalEvidence(
        schema_version=TERMINAL_SCHEMA_VERSION,
        kind="terminal",
        task_id=task_id,
        workstream_id=workstream_id,
        generation=generation,
        status=status,  # type: ignore[arg-type]
        summary=summary,
        checks=tuple(checks),
        artifacts=artifacts,
        limitations=limitations,
        blocker=blocker,
    )


class CodexAppServerClient:
    """Persistent, generation-fenced JSON-RPC client for one owned child."""

    def __init__(
        self,
        *,
        generation: int,
        codex_bin: str = "codex",
        model: str = CODEX_APP_SERVER_MODEL,
        reasoning_effort: str = CODEX_APP_SERVER_REASONING_EFFORT,
        sandbox: SandboxMode = "read-only",
        approval_policy: ApprovalPolicy = "never",
        owned_thread_ids: Iterable[str] = (),
        request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
        turn_timeout_seconds: float = DEFAULT_TURN_TIMEOUT_SECONDS,
        shutdown_timeout_seconds: float = DEFAULT_SHUTDOWN_TIMEOUT_SECONDS,
        max_reconnect_attempts: int = DEFAULT_MAX_RECONNECT_ATTEMPTS,
        reconnect_backoff_seconds: float = DEFAULT_RECONNECT_BACKOFF_SECONDS,
        is_stale_generation: Callable[[int], bool] | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
        jitter_fn: Callable[[float], float] | None = None,
        monotonic_fn: Callable[[], float] = time.monotonic,
        env: Mapping[str, str] | None = None,
        popen_factory: Callable[..., subprocess.Popen[str]] = subprocess.Popen,
    ) -> None:
        self.generation = _positive_int(generation, "generation")
        self.codex_bin = _bounded_text(codex_bin, "codex_bin", 2_000)
        self.model = _bounded_text(model, "model", 200)
        self.reasoning_effort = _bounded_text(reasoning_effort, "reasoning_effort", 50)
        if self.model != CODEX_APP_SERVER_MODEL or self.reasoning_effort != CODEX_APP_SERVER_REASONING_EFFORT:
            raise CodexIdentityMismatchError(
                f"adapter requires {CODEX_APP_SERVER_MODEL}/{CODEX_APP_SERVER_REASONING_EFFORT}"
            )
        if sandbox not in SANDBOX_MODES:
            raise ValueError("sandbox must be read-only, workspace-write, or danger-full-access")
        if approval_policy not in APPROVAL_POLICIES:
            raise ValueError("approval_policy must be untrusted, on-request, or never")
        self.sandbox: SandboxMode = sandbox
        self.approval_policy: ApprovalPolicy = approval_policy
        self.request_timeout_seconds = _positive_float(request_timeout_seconds, "request_timeout_seconds")
        self.turn_timeout_seconds = _positive_float(turn_timeout_seconds, "turn_timeout_seconds")
        self.shutdown_timeout_seconds = _positive_float(shutdown_timeout_seconds, "shutdown_timeout_seconds")
        if type(max_reconnect_attempts) is not int or not 0 <= max_reconnect_attempts <= 10:
            raise ValueError("max_reconnect_attempts must be between 0 and 10")
        self.max_reconnect_attempts = max_reconnect_attempts
        self.reconnect_backoff_seconds = _positive_float(reconnect_backoff_seconds, "reconnect_backoff_seconds")
        self._is_stale_generation_callback = is_stale_generation or (lambda _generation: False)
        self._sleep_fn = sleep_fn
        self._jitter_fn = jitter_fn or (lambda base: random.uniform(0.0, max(0.0, base * 0.25)))
        self._monotonic_fn = monotonic_fn
        self._env = {str(key): str(value) for key, value in (env or {}).items()}
        self._popen_factory = popen_factory

        self._state_condition = threading.Condition(threading.RLock())
        self._connect_lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._thread_locks_guard = threading.Lock()
        self._thread_locks: dict[str, threading.Lock] = {}
        self._pending: dict[int, _PendingResponse] = {}
        self._next_request_id = 1
        self._process: subprocess.Popen[str] | None = None
        self._stdout_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self._connection_epoch = 0
        self._last_initialized_connection_epoch = 0
        self._initialized = False
        self._closing = False
        self._fatal_error: BaseException | None = None
        self._attestation: CodexModelAttestation | None = None
        self._owned_thread_ids = {_validated_thread_id(value) for value in owned_thread_ids}
        self._loaded_thread_ids: set[str] = set()
        # ``thread/start`` creates an in-memory empty thread before there is a
        # persisted rollout for ``thread/read`` to discover.  This attestation
        # is deliberately process/connection-local: reconnect or resume must
        # always go through persisted-history reconciliation.
        self._fresh_empty_thread_epochs: dict[str, int] = {}
        self._tainted_thread_ids: set[str] = set()

        self._stderr_lines: deque[str] = deque(maxlen=MAX_STDERR_LINES)
        self._lifecycle_events: deque[CodexLifecycleEvent] = deque(maxlen=MAX_LIFECYCLE_EVENTS)
        self._turn_events: dict[str, list[CodexLifecycleEvent]] = {}
        self._seen_event_keys: set[tuple[str, str, str, str, str]] = set()
        self._seen_event_order: deque[tuple[str, str, str, str, str]] = deque()
        self._known_turn_ids: set[str] = set()
        self._known_item_ids: set[str] = set()
        self._completed_turns: dict[str, str] = {}
        self._agent_messages: dict[str, str] = {}
        self._thread_by_turn: dict[str, str] = {}

    def __enter__(self) -> CodexAppServerClient:
        self.connect()
        return self

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        self.shutdown()

    @property
    def spawn_args(self) -> tuple[str, ...]:
        return (
            self.codex_bin,
            "-c",
            f"model={json.dumps(self.model)}",
            "-c",
            f"model_reasoning_effort={json.dumps(self.reasoning_effort)}",
            "app-server",
            "--listen",
            "stdio://",
        )

    @property
    def model_attestation(self) -> CodexModelAttestation | None:
        return self._attestation

    @property
    def connection_epoch(self) -> int:
        """Return the latest successfully initialized transport epoch."""

        with self._state_condition:
            return self._last_initialized_connection_epoch

    @contextmanager
    def pin_connection_epoch(self, required_connection_epoch: int) -> Iterator[None]:
        """Hold an exact live stdio epoch across one short durable receipt.

        This guard never performs transport I/O.  It prevents the reader
        thread from publishing a disconnect between the caller's final live
        epoch check and its local SQLite commit.  The protected section must
        therefore stay bounded to that commit and must never contain a model
        or protocol wait.
        """

        self._ensure_fresh_generation()
        required_epoch = _positive_int(
            required_connection_epoch, "required_connection_epoch"
        )
        with self._state_condition:
            process = self._process
            if (
                self._connection_epoch != required_epoch
                or self._last_initialized_connection_epoch != required_epoch
                or not self._initialized
                or process is None
                or process.poll() is not None
                or isinstance(self._fatal_error, CodexDisconnectedError)
            ):
                raise CodexAmbiguousOutcomeError(
                    "Codex App Server connection epoch changed before durable receipt"
                )
            yield

    @property
    def owned_thread_ids(self) -> tuple[str, ...]:
        with self._state_condition:
            return tuple(sorted(self._owned_thread_ids))

    @property
    def stderr_tail(self) -> tuple[str, ...]:
        with self._state_condition:
            return tuple(self._stderr_lines)

    @property
    def is_running(self) -> bool:
        with self._state_condition:
            return bool(self._process is not None and self._process.poll() is None and self._initialized)

    def connect(self) -> CodexModelAttestation:
        self._ensure_fresh_generation()
        with self._connect_lock:
            with self._state_condition:
                if self._closing:
                    raise CodexDisconnectedError("Codex App Server client is shut down")
                if self._initialized and self._process is not None and self._process.poll() is None:
                    if self._attestation is None:
                        raise CodexProtocolError("connected App Server is missing model attestation")
                    return self._attestation
                fatal = self._fatal_error
            if fatal is not None and not isinstance(fatal, CodexDisconnectedError):
                raise fatal

            last_error: BaseException | None = None
            for attempt in range(self.max_reconnect_attempts + 1):
                if attempt:
                    self._sleep_before_retry(attempt)
                try:
                    return self._connect_once()
                except (CodexDisconnectedError, CodexRequestTimeout, OSError) as exc:
                    last_error = exc
                    self._dispose_current_process()
                    continue
                except BaseException:
                    self._dispose_current_process()
                    raise
            raise CodexDisconnectedError(
                f"unable to initialize owned Codex App Server after bounded retries: {_safe_exception(last_error)}"
            )

    def start_thread(
        self,
        *,
        cwd: str | None = None,
        ephemeral: bool = False,
        required_connection_epoch: int | None = None,
    ) -> CodexThreadIdentity:
        self._ensure_fresh_generation()
        if not isinstance(ephemeral, bool):
            raise ValueError("ephemeral must be a boolean")
        required_epoch = (
            None
            if required_connection_epoch is None
            else _positive_int(
                required_connection_epoch, "required_connection_epoch"
            )
        )
        params: dict[str, Any] = {
            "model": self.model,
            "serviceName": "dev-control-plane-supervisor-v2",
            "ephemeral": ephemeral,
            "sandbox": self.sandbox,
            "approvalPolicy": self.approval_policy,
            "approvalsReviewer": APPROVALS_REVIEWER,
        }
        if cwd is not None:
            params["cwd"] = _bounded_text(cwd, "cwd", 8_000)
        result = self._request(
            "thread/start",
            params,
            retry_safe=False,
            required_connection_epoch=required_epoch,
        )
        try:
            identity = self._thread_identity_from_result(
                result,
                expected_thread_id=None,
                expected_ephemeral=ephemeral,
            )
        except CodexIdentityMismatchError as exc:
            self._set_fatal(exc, self._connection_epoch)
            raise
        with self._state_condition:
            process = self._process
            if required_epoch is not None and (
                self._last_initialized_connection_epoch != required_epoch
                or self._connection_epoch != required_epoch
                or not self._initialized
                or process is None
                or process.poll() is not None
            ):
                raise CodexAmbiguousOutcomeError(
                    "thread/start connection epoch changed before identity receipt"
                )
            self._owned_thread_ids.add(identity.thread_id)
            self._loaded_thread_ids.add(identity.thread_id)
            self._fresh_empty_thread_epochs[identity.thread_id] = self._connection_epoch
        return identity

    def resume_thread(self, thread_id: str) -> CodexThreadIdentity:
        thread_id = _validated_thread_id(thread_id)
        self._assert_owned_thread(thread_id)
        self._ensure_fresh_generation()
        # A resume attempt crosses the narrow thread/start-only proof boundary,
        # even when App Server rejects the request definitively.  Consume the
        # marker before transport so timeout, disconnect and remote-error paths
        # cannot make the same thread look freshly created again.
        with self._state_condition:
            self._fresh_empty_thread_epochs.pop(thread_id, None)
        try:
            result = self._request(
                "thread/resume",
                {
                    "threadId": thread_id,
                    "model": self.model,
                    "sandbox": self.sandbox,
                    "approvalPolicy": self.approval_policy,
                    "approvalsReviewer": APPROVALS_REVIEWER,
                },
                retry_safe=False,
            )
            identity = self._thread_identity_from_result(
                result,
                expected_thread_id=thread_id,
                expected_ephemeral=None,
            )
        except (CodexAmbiguousOutcomeError, CodexIdentityMismatchError) as exc:
            with self._state_condition:
                self._tainted_thread_ids.add(thread_id)
                self._loaded_thread_ids.discard(thread_id)
            if isinstance(exc, CodexIdentityMismatchError):
                self._set_fatal(exc, self._connection_epoch)
            raise
        with self._state_condition:
            self._loaded_thread_ids.add(thread_id)
            self._tainted_thread_ids.discard(thread_id)
        return identity

    def fresh_empty_turn_baseline(self, thread_id: str) -> tuple[str, ...] | None:
        """Attest one new, still-empty thread on this exact transport epoch.

        The proof exists only after this client successfully performed
        ``thread/start``.  It is unavailable for constructor-owned ids,
        resumes, reconnects, tainted threads, or after the first turn intent
        is consumed.  Callers must durably receipt the returned empty baseline
        before invoking ``turn/start``.
        """

        thread_id = _validated_thread_id(thread_id)
        self._assert_owned_thread(thread_id)
        self._ensure_fresh_generation()
        with self._state_condition:
            epoch = self._fresh_empty_thread_epochs.get(thread_id)
            process = self._process
            if (
                epoch is None
                or epoch != self._last_initialized_connection_epoch
                or not self._initialized
                or process is None
                or process.poll() is not None
                or thread_id not in self._loaded_thread_ids
                or thread_id in self._tainted_thread_ids
            ):
                return None
            return ()

    def consume_fresh_empty_turn_baseline(
        self,
        thread_id: str,
        *,
        required_connection_epoch: int | None = None,
    ) -> None:
        """Consume the same-epoch empty-thread proof after durable CAS."""

        thread_id = _validated_thread_id(thread_id)
        self._assert_owned_thread(thread_id)
        self._ensure_fresh_generation()
        with self._state_condition:
            epoch = self._fresh_empty_thread_epochs.get(thread_id)
            required_epoch = (
                self._last_initialized_connection_epoch
                if required_connection_epoch is None
                else _positive_int(required_connection_epoch, "required_connection_epoch")
            )
            process = self._process
            if (
                epoch != required_epoch
                or required_epoch != self._last_initialized_connection_epoch
                or not self._initialized
                or process is None
                or process.poll() is not None
                or thread_id not in self._loaded_thread_ids
                or thread_id in self._tainted_thread_ids
            ):
                raise CodexProtocolError(
                    "fresh empty-thread attestation changed before durable call intent"
                )
            self._fresh_empty_thread_epochs.pop(thread_id, None)

    def read_thread_snapshot(
        self,
        thread_id: str,
        *,
        include_turns: bool = False,
        timeout_seconds: float | None = None,
    ) -> Mapping[str, Any]:
        """Read any exact local thread without loading or taking ownership of it."""

        thread_id = _validated_thread_id(thread_id)
        result = self._request(
            "thread/read",
            {"threadId": thread_id, "includeTurns": bool(include_turns)},
            timeout_seconds=timeout_seconds,
            retry_safe=True,
        )
        thread = result.get("thread")
        if not isinstance(thread, Mapping) or thread.get("id") != thread_id:
            raise CodexProtocolError("thread/read returned a different or missing thread id")
        self._attest_optional_identity_fields(thread, "thread/read")
        return thread

    def reconcile_thread(
        self,
        thread_id: str,
        *,
        timeout_seconds: float | None = None,
    ) -> CodexReconciliation:
        """Rebuild structural evidence using stable ``thread/read`` history."""

        thread_id = _validated_thread_id(thread_id)
        self._assert_owned_thread(thread_id)
        thread = self.read_thread_snapshot(thread_id, include_turns=True, timeout_seconds=timeout_seconds)
        turns = thread.get("turns")
        if turns is None:
            turns = []
        if not isinstance(turns, list):
            raise CodexProtocolError("thread/read turns must be an array")
        new_turn_ids: list[str] = []
        new_item_ids: list[str] = []
        terminal_turn_ids: list[str] = []
        with self._state_condition:
            for raw_turn in turns:
                if not isinstance(raw_turn, Mapping):
                    raise CodexProtocolError("thread/read contains an invalid turn")
                turn_id = _optional_protocol_id(raw_turn.get("id"), "turn.id")
                if turn_id is None:
                    raise CodexProtocolError("thread/read turn is missing id")
                if turn_id not in self._known_turn_ids:
                    self._known_turn_ids.add(turn_id)
                    new_turn_ids.append(turn_id)
                status = str(raw_turn.get("status") or "")
                if status in {"completed", "failed", "interrupted"}:
                    terminal_turn_ids.append(turn_id)
                    self._completed_turns.setdefault(turn_id, status)
                items = raw_turn.get("items")
                if items is None:
                    items = []
                if not isinstance(items, list):
                    raise CodexProtocolError("thread/read turn items must be an array")
                for raw_item in items:
                    if not isinstance(raw_item, Mapping):
                        raise CodexProtocolError("thread/read contains an invalid item")
                    item_id = _optional_protocol_id(raw_item.get("id"), "item.id")
                    if item_id and item_id not in self._known_item_ids:
                        self._known_item_ids.add(item_id)
                        new_item_ids.append(item_id)
            status_value = thread.get("status")
            thread_status = _status_type(status_value)
        return CodexReconciliation(
            thread_id=thread_id,
            thread_status=thread_status,
            new_turn_ids=tuple(new_turn_ids),
            new_item_ids=tuple(new_item_ids),
            terminal_turn_ids=tuple(dict.fromkeys(terminal_turn_ids)),
        )

    def recover_lost_turn_receipt(
        self,
        thread_id: str,
        *,
        baseline_turn_ids: Sequence[str],
        output_contract: OutputContract,
        expected_task_id: str,
        expected_workstream_id: str,
        timeout_seconds: float | None = None,
    ) -> CodexTurnResult:
        """Recover one schema-bound completed turn from persisted App Server history.

        ``thread/read(includeTurns=true)`` exposes full persisted turn items but
        does not replay the original notification stream.  Completion events
        derived from that snapshot are therefore tagged
        ``thread_read_snapshot``; any events actually observed before the lost
        receipt retain their ``notification`` provenance.  Snapshot recovery
        never invents ``turn/started`` or ``item/started`` notifications.
        """

        thread_id = _validated_thread_id(thread_id)
        self._assert_owned_thread(thread_id)
        self._ensure_fresh_generation()
        if output_contract not in {"checkpoint", "terminal"}:
            raise ValueError("output_contract must be checkpoint or terminal")
        expected_task_id = _validated_id(expected_task_id, "expected_task_id")
        expected_workstream_id = _validated_id(
            expected_workstream_id, "expected_workstream_id"
        )
        baseline = _validated_recovery_baseline(baseline_turn_ids)
        baseline_set = set(baseline)
        thread = self.read_thread_snapshot(
            thread_id,
            include_turns=True,
            timeout_seconds=timeout_seconds,
        )
        turns = thread.get("turns")
        if not isinstance(turns, list):
            raise CodexProtocolError("thread/read recovery requires a turns array")

        observed: dict[str, Mapping[str, Any]] = {}
        ordered_turn_ids: list[str] = []
        turn_positions: dict[str, int] = {}
        for index, raw_turn in enumerate(turns):
            if not isinstance(raw_turn, Mapping):
                raise CodexProtocolError(
                    f"thread/read recovery turn {index} is not an object"
                )
            turn_id = _optional_protocol_id(
                raw_turn.get("id"), f"thread/read turns[{index}].id"
            )
            if turn_id is None:
                raise CodexProtocolError("thread/read recovery turn is missing id")
            if turn_id in observed:
                raise CodexProtocolError("thread/read recovery contains duplicate turn ids")
            observed[turn_id] = raw_turn
            turn_positions[turn_id] = len(ordered_turn_ids)
            ordered_turn_ids.append(turn_id)

        missing_baseline = baseline_set - set(observed)
        if missing_baseline:
            raise CodexAmbiguousOutcomeError(
                "thread/read no longer contains the complete durable turn baseline"
            )
        new_turn_ids = [turn_id for turn_id in ordered_turn_ids if turn_id not in baseline_set]
        if len(new_turn_ids) != 1:
            raise CodexAmbiguousOutcomeError(
                "lost receipt recovery requires exactly one turn newer than the durable baseline"
            )

        turn_id = new_turn_ids[0]
        if baseline and turn_positions[turn_id] <= max(
            turn_positions[baseline_turn_id] for baseline_turn_id in baseline
        ):
            raise CodexAmbiguousOutcomeError(
                "the unmatched persisted turn is not newer than the durable baseline"
            )
        raw_turn = observed[turn_id]
        status = raw_turn.get("status")
        if status == "inProgress":
            raise CodexAmbiguousOutcomeError(
                "the only new persisted turn is still in progress"
            )
        if status in {"failed", "interrupted"}:
            raise CodexTurnFailedError(
                f"persisted turn {turn_id} has terminal status {status}"
            )
        if status != "completed":
            raise CodexProtocolError("thread/read recovery turn has an invalid status")
        items_view = raw_turn.get("itemsView", "full")
        if items_view != "full":
            raise CodexProtocolError(
                "thread/read recovery requires itemsView=full persisted history"
            )
        self._attest_optional_identity_fields(raw_turn, "thread/read recovery turn")
        items, output_item = _validated_recovery_items(raw_turn.get("items"))
        payload = _parse_contract_json(str(output_item["text"]))
        if output_contract == "checkpoint":
            contract: CodexCheckpoint | CodexTerminalEvidence = validate_checkpoint_payload(
                payload,
                expected_generation=self.generation,
                expected_task_id=expected_task_id,
                expected_workstream_id=expected_workstream_id,
            )
        else:
            contract = validate_terminal_payload(
                payload,
                expected_generation=self.generation,
                expected_task_id=expected_task_id,
                expected_workstream_id=expected_workstream_id,
            )

        with self._state_condition:
            live_events = tuple(self._turn_events.get(turn_id, ()))
            live_output = self._agent_messages.get(turn_id)
            if live_output is not None and live_output != output_item["text"]:
                raise CodexProtocolError(
                    "live and persisted schema-bound output evidence disagree"
                )
            for event in live_events:
                if event.thread_id not in {None, thread_id}:
                    raise CodexProtocolError(
                        "live lifecycle evidence belongs to a different thread"
                    )
                if event.method == "turn/completed" and event.status != "completed":
                    raise CodexProtocolError(
                        "live and persisted turn completion evidence disagree"
                    )
            events = list(live_events)
            output_item_id = str(output_item["id"])
            if not any(
                event.method == "item/completed"
                and event.item_id == output_item_id
                and event.item_type == "agentMessage"
                for event in events
            ):
                events.append(
                    CodexLifecycleEvent(
                        method="item/completed",
                        thread_id=thread_id,
                        turn_id=turn_id,
                        item_id=output_item_id,
                        item_type="agentMessage",
                        status=(
                            str(output_item["status"])
                            if isinstance(output_item.get("status"), str)
                            else None
                        ),
                        connection_epoch=self._last_initialized_connection_epoch,
                        evidence_source="thread_read_snapshot",
                    )
                )
            if not any(
                event.method == "turn/completed" and event.status == "completed"
                for event in events
            ):
                events.append(
                    CodexLifecycleEvent(
                        method="turn/completed",
                        thread_id=thread_id,
                        turn_id=turn_id,
                        item_id=None,
                        item_type=None,
                        status="completed",
                        connection_epoch=self._last_initialized_connection_epoch,
                        evidence_source="thread_read_snapshot",
                    )
                )
            self._known_turn_ids.add(turn_id)
            self._completed_turns.setdefault(turn_id, "completed")
            for item in items:
                self._known_item_ids.add(str(item["id"]))
            # Reaching this point proves one exact newer persisted turn, its
            # terminal lifecycle and its schema-bound identity.  That proof is
            # the explicit recovery boundary for a same-connection ambiguous
            # turn, so the thread may safely accept a later serialized turn.
            # Do not clear taint on any earlier or exceptional path.
            self._tainted_thread_ids.discard(thread_id)

        return CodexTurnResult(
            thread_id=thread_id,
            turn_id=turn_id,
            status="completed",
            contract=contract,
            events=tuple(events),
        )

    def run_turn(
        self,
        thread_id: str,
        input_value: str | Sequence[Mapping[str, Any]],
        *,
        output_contract: OutputContract,
        expected_task_id: str,
        expected_workstream_id: str,
        cwd: str | None = None,
        request_timeout_seconds: float | None = None,
        turn_timeout_seconds: float | None = None,
        serialization_timeout_seconds: float | None = None,
        required_connection_epoch: int | None = None,
    ) -> CodexTurnResult:
        """Start one explicit Sol/Ultra/schema turn and wait for completion.

        Holding the per-thread lock through ``turn/completed`` prevents a second
        turn from starting on the same thread while the first is active.
        """

        thread_id = _validated_thread_id(thread_id)
        self._assert_owned_thread(thread_id)
        self._ensure_fresh_generation()
        expected_task_id = _validated_id(expected_task_id, "expected_task_id")
        expected_workstream_id = _validated_id(expected_workstream_id, "expected_workstream_id")
        if output_contract not in {"checkpoint", "terminal"}:
            raise ValueError("output_contract must be checkpoint or terminal")
        required_epoch = (
            None
            if required_connection_epoch is None
            else _positive_int(required_connection_epoch, "required_connection_epoch")
        )
        lock = self._thread_lock(thread_id)
        lock_timeout = (
            self.request_timeout_seconds
            if serialization_timeout_seconds is None
            else _positive_float(serialization_timeout_seconds, "serialization_timeout_seconds")
        )
        if not lock.acquire(timeout=lock_timeout):
            raise CodexRequestTimeout(f"per-thread serialization timeout for {thread_id}")
        try:
            with self._state_condition:
                if thread_id in self._tainted_thread_ids:
                    raise CodexProtocolError(f"thread {thread_id} is tainted and requires explicit resume/recovery")
                if thread_id not in self._loaded_thread_ids:
                    raise CodexThreadOwnershipError(
                        f"Supervisor-owned thread {thread_id} must be started or resumed on this connection"
                    )
                if (
                    required_epoch is not None
                    and required_epoch != self._last_initialized_connection_epoch
                ):
                    raise CodexDisconnectedError(
                        "Codex App Server connection epoch changed before turn/start"
                    )
                # A direct adapter caller may not use the Supervisor's
                # durable-intent helper.  Starting any turn consumes the
                # process-local empty-thread proof before the mutating RPC.
                self._fresh_empty_thread_epochs.pop(thread_id, None)
            params: dict[str, Any] = {
                "threadId": thread_id,
                "input": _validated_turn_input(input_value),
                "model": self.model,
                "effort": self.reasoning_effort,
                "outputSchema": checkpoint_output_schema() if output_contract == "checkpoint" else terminal_output_schema(),
            }
            if cwd is not None:
                params["cwd"] = _bounded_text(cwd, "cwd", 8_000)
            try:
                result = self._request(
                    "turn/start",
                    params,
                    timeout_seconds=request_timeout_seconds,
                    retry_safe=False,
                    required_connection_epoch=required_epoch,
                )
            except CodexAmbiguousOutcomeError:
                with self._state_condition:
                    self._tainted_thread_ids.add(thread_id)
                raise
            turn = result.get("turn")
            if not isinstance(turn, Mapping):
                raise CodexProtocolError("turn/start response is missing turn")
            turn_id = _optional_protocol_id(turn.get("id"), "turn.id")
            if turn_id is None:
                raise CodexProtocolError("turn/start response is missing turn id")
            self._attest_optional_identity_fields(turn, "turn/start")
            with self._state_condition:
                self._thread_by_turn[turn_id] = thread_id
                self._known_turn_ids.add(turn_id)
            try:
                status = self._wait_for_turn(
                    turn_id,
                    self.turn_timeout_seconds
                    if turn_timeout_seconds is None
                    else _positive_float(turn_timeout_seconds, "turn_timeout_seconds"),
                )
            except CodexTurnTimeout:
                with self._state_condition:
                    self._tainted_thread_ids.add(thread_id)
                raise
            except CodexDisconnectedError as exc:
                with self._state_condition:
                    self._tainted_thread_ids.add(thread_id)
                raise CodexAmbiguousOutcomeError(
                    f"turn {turn_id} disconnected before terminal evidence; reconcile before retry"
                ) from exc
            self._ensure_fresh_generation()
            if status != "completed":
                raise CodexTurnFailedError(f"Codex turn {turn_id} completed with status {_sanitize_text(status, 100)}")
            with self._state_condition:
                raw_contract = self._agent_messages.pop(turn_id, None)
                events = tuple(self._turn_events.get(turn_id, ()))
            if raw_contract is None:
                raise CodexContractError(f"Codex turn {turn_id} completed without schema-bound agent output")
            payload = _parse_contract_json(raw_contract)
            if output_contract == "checkpoint":
                contract: CodexCheckpoint | CodexTerminalEvidence = validate_checkpoint_payload(
                    payload,
                    expected_generation=self.generation,
                    expected_task_id=expected_task_id,
                    expected_workstream_id=expected_workstream_id,
                )
            else:
                contract = validate_terminal_payload(
                    payload,
                    expected_generation=self.generation,
                    expected_task_id=expected_task_id,
                    expected_workstream_id=expected_workstream_id,
                )
            return CodexTurnResult(
                thread_id=thread_id,
                turn_id=turn_id,
                status=status,
                contract=contract,
                events=events,
            )
        finally:
            lock.release()

    def drain_lifecycle_events(self) -> tuple[CodexLifecycleEvent, ...]:
        with self._state_condition:
            events = tuple(self._lifecycle_events)
            self._lifecycle_events.clear()
            return events

    def shutdown(self) -> None:
        with self._state_condition:
            if self._closing:
                return
            self._closing = True
            shutdown_error = CodexDisconnectedError("Codex App Server client shut down")
            for pending in self._pending.values():
                pending.error = shutdown_error
                pending.event.set()
            self._pending.clear()
        self._dispose_current_process()

    close = shutdown

    def _connect_once(self) -> CodexModelAttestation:
        self._ensure_fresh_generation()
        self._dispose_current_process()
        spawn_env = {
            key: value
            for key, value in os.environ.items()
            if key in _INHERITED_ENV_ALLOWLIST
        }
        spawn_env.update(
            {
                "GIT_TERMINAL_PROMPT": "0",
                "NO_COLOR": "1",
            }
        )
        spawn_env.update(self._env)
        try:
            process = self._popen_factory(
                self.spawn_args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=spawn_env,
                start_new_session=True,
            )
        except OSError as exc:
            raise CodexDisconnectedError(f"unable to start Codex App Server: {_safe_exception(exc)}") from exc
        if process.stdin is None or process.stdout is None or process.stderr is None:
            process.terminate()
            raise CodexDisconnectedError("Codex App Server stdio pipes are unavailable")
        with self._state_condition:
            self._connection_epoch += 1
            epoch = self._connection_epoch
            self._process = process
            self._initialized = False
            self._fatal_error = None
            self._attestation = None
            self._loaded_thread_ids.clear()
            self._fresh_empty_thread_epochs.clear()
        stdout_thread = threading.Thread(
            target=self._stdout_loop,
            args=(process, epoch),
            name=f"codex-app-server-stdout-{epoch}",
            daemon=True,
        )
        stderr_thread = threading.Thread(
            target=self._stderr_loop,
            args=(process, epoch),
            name=f"codex-app-server-stderr-{epoch}",
            daemon=True,
        )
        self._stdout_thread = stdout_thread
        self._stderr_thread = stderr_thread
        stdout_thread.start()
        stderr_thread.start()

        initialize_result = self._request_once(
            "initialize",
            {
                "clientInfo": {
                    "name": "dev_control_plane_v2",
                    "title": "Development Control Plane Supervisor v2",
                    "version": "2",
                }
            },
            timeout_seconds=self.request_timeout_seconds,
        )
        if not isinstance(initialize_result, Mapping):
            raise CodexProtocolError("initialize result must be an object")
        self._send_notification("initialized", {})
        model_result = self._request_once(
            "model/list",
            {"limit": 100, "includeHidden": True},
            timeout_seconds=self.request_timeout_seconds,
        )
        attestation = self._attest_model_list(model_result, epoch)
        with self._state_condition:
            self._initialized = True
            self._attestation = attestation
            self._last_initialized_connection_epoch = epoch
        return attestation

    def _request(
        self,
        method: str,
        params: Mapping[str, Any],
        *,
        timeout_seconds: float | None = None,
        retry_safe: bool,
        required_connection_epoch: int | None = None,
    ) -> Mapping[str, Any]:
        timeout = self.request_timeout_seconds if timeout_seconds is None else _positive_float(timeout_seconds, "timeout_seconds")
        required_epoch = (
            None
            if required_connection_epoch is None
            else _positive_int(required_connection_epoch, "required_connection_epoch")
        )
        last_error: BaseException | None = None
        for attempt in range(self.max_reconnect_attempts + 1):
            self._ensure_fresh_generation()
            if required_epoch is None:
                self.connect()
            else:
                # An exact-epoch mutating request is a one-connection
                # capability.  Never create a replacement child merely to
                # discover that its epoch is stale.
                with self._state_condition:
                    process = self._process
                    if (
                        self._connection_epoch != required_epoch
                        or self._last_initialized_connection_epoch != required_epoch
                        or not self._initialized
                        or process is None
                        or process.poll() is not None
                    ):
                        raise CodexDisconnectedError(
                            f"{method} connection epoch changed before request"
                        )
            try:
                return self._request_once(
                    method,
                    params,
                    timeout_seconds=timeout,
                    required_connection_epoch=required_epoch,
                )
            except CodexRequestTimeout as exc:
                if not retry_safe:
                    raise CodexAmbiguousOutcomeError(
                        f"{method} timed out with ambiguous outcome; reconcile before retry"
                    ) from exc
                raise
            except CodexDisconnectedError as exc:
                last_error = exc
                if not retry_safe:
                    raise CodexAmbiguousOutcomeError(
                        f"{method} disconnected with ambiguous outcome; reconcile before retry"
                    ) from exc
                if attempt >= self.max_reconnect_attempts:
                    break
                self._sleep_before_retry(attempt + 1)
                self._dispose_current_process()
                continue
        raise CodexDisconnectedError(f"{method} failed after bounded reconnects: {_safe_exception(last_error)}")

    def _request_once(
        self,
        method: str,
        params: Mapping[str, Any],
        *,
        timeout_seconds: float,
        required_connection_epoch: int | None = None,
    ) -> Mapping[str, Any]:
        self._ensure_fresh_generation()
        with self._state_condition:
            fatal = self._fatal_error
            if fatal is not None:
                raise fatal
            process = self._process
            if process is None or process.poll() is not None:
                raise CodexDisconnectedError("Codex App Server is not running")
            request_id = self._next_request_id
            self._next_request_id += 1
            pending = _PendingResponse()
            self._pending[request_id] = pending
        try:
            self._send_message(
                {"method": method, "id": request_id, "params": dict(params)},
                required_connection_epoch=required_connection_epoch,
            )
        except BaseException:
            with self._state_condition:
                self._pending.pop(request_id, None)
            raise
        if not pending.event.wait(timeout_seconds):
            with self._state_condition:
                self._pending.pop(request_id, None)
            raise CodexRequestTimeout(f"Codex App Server {method} exceeded bounded request timeout")
        self._ensure_fresh_generation()
        if pending.error is not None:
            raise pending.error
        response = pending.response
        if not isinstance(response, Mapping):
            raise CodexProtocolError(f"Codex App Server {method} returned no response object")
        remote_error = response.get("error")
        if isinstance(remote_error, Mapping):
            code = remote_error.get("code")
            raise CodexRemoteError(
                method,
                code if type(code) is int else None,
                str(remote_error.get("message") or "remote error"),
            )
        result = response.get("result")
        if not isinstance(result, Mapping):
            raise CodexProtocolError(f"Codex App Server {method} result must be an object")
        return result

    def _send_notification(self, method: str, params: Mapping[str, Any]) -> None:
        self._send_message({"method": method, "params": dict(params)})

    def _send_message(
        self,
        payload: Mapping[str, Any],
        *,
        required_connection_epoch: int | None = None,
    ) -> None:
        serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        if len(serialized) > MAX_REQUEST_CHARS:
            raise CodexProtocolError("Codex App Server request exceeds bounded size")
        with self._write_lock:
            with self._state_condition:
                process = self._process
                epoch = self._connection_epoch
                if required_connection_epoch is not None and (
                    epoch != required_connection_epoch
                    or self._last_initialized_connection_epoch
                    != required_connection_epoch
                    or not self._initialized
                ):
                    raise CodexDisconnectedError(
                        "Codex App Server connection epoch changed before stdio send"
                    )
                if process is None or process.stdin is None or process.poll() is not None:
                    raise CodexDisconnectedError("Codex App Server stdin is unavailable")
                # Keep the state lock through the bounded pipe write so a
                # concurrent reconnect/dispose cannot swap or close the child
                # between the exact-epoch check and the mutating request.
                try:
                    process.stdin.write(serialized + "\n")
                    process.stdin.flush()
                except (BrokenPipeError, OSError, ValueError) as exc:
                    self._mark_disconnected(epoch, exc)
                    raise CodexDisconnectedError("Codex App Server stdin disconnected") from exc

    def _stdout_loop(self, process: subprocess.Popen[str], epoch: int) -> None:
        assert process.stdout is not None
        try:
            while True:
                line = process.stdout.readline(MAX_JSON_LINE_CHARS + 1)
                if not line:
                    break
                if len(line) > MAX_JSON_LINE_CHARS or not line.endswith("\n"):
                    self._set_fatal(CodexProtocolError("Codex App Server emitted an oversized JSON line"), epoch)
                    return
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    self._set_fatal(CodexProtocolError("Codex App Server emitted invalid JSON"), epoch)
                    return
                if not isinstance(message, Mapping):
                    self._set_fatal(CodexProtocolError("Codex App Server message must be an object"), epoch)
                    return
                try:
                    self._handle_message(message, epoch)
                except BaseException as exc:
                    self._set_fatal(
                        exc if isinstance(exc, CodexAppServerError) else CodexProtocolError(_safe_exception(exc)),
                        epoch,
                    )
                    return
        except (OSError, ValueError) as exc:
            self._mark_disconnected(epoch, exc)
            return
        self._mark_disconnected(epoch, None)

    def _stderr_loop(self, process: subprocess.Popen[str], epoch: int) -> None:
        assert process.stderr is not None
        try:
            while True:
                line = process.stderr.readline(MAX_STDERR_LINE_CHARS + 1)
                if not line:
                    break
                sanitized = _sanitize_text(line, MAX_STDERR_LINE_CHARS)
                if sanitized:
                    with self._state_condition:
                        if epoch == self._connection_epoch:
                            self._stderr_lines.append(sanitized)
        except (OSError, ValueError):
            return

    def _handle_message(self, message: Mapping[str, Any], epoch: int) -> None:
        if epoch != self._connection_epoch:
            return
        if "id" in message and "method" not in message:
            response_id = message.get("id")
            if type(response_id) is not int:
                self._set_fatal(CodexProtocolError("Codex App Server response id must be an integer"), epoch)
                return
            with self._state_condition:
                pending = self._pending.pop(response_id, None)
                if pending is not None:
                    pending.response = message
                    pending.event.set()
            return
        method = message.get("method")
        if not isinstance(method, str):
            self._set_fatal(CodexProtocolError("Codex App Server message is missing method or response id"), epoch)
            return
        if "id" in message:
            self._set_fatal(CodexProtocolError(f"unsupported App Server request: {_sanitize_text(method, 200)}"), epoch)
            return
        params = message.get("params")
        if params is None:
            params = {}
        if not isinstance(params, Mapping):
            self._set_fatal(CodexProtocolError("Codex App Server notification params must be an object"), epoch)
            return
        if self._generation_is_stale():
            self._set_fatal(CodexStaleGenerationError(f"Supervisor generation {self.generation} is stale"), epoch)
            return
        if method == "model/rerouted":
            from_model = _sanitize_text(str(params.get("fromModel") or "unknown"), 100)
            to_model = _sanitize_text(str(params.get("toModel") or "unknown"), 100)
            self._set_fatal(
                CodexIdentityMismatchError(f"model reroute is forbidden: {from_model} -> {to_model}"),
                epoch,
            )
            return
        event = _parse_lifecycle_event(method, params, epoch, self._thread_by_turn)
        if event is None:
            return
        with self._state_condition:
            if event.dedupe_key in self._seen_event_keys:
                return
            self._remember_event_key(event.dedupe_key)
            self._lifecycle_events.append(event)
            if event.turn_id:
                self._known_turn_ids.add(event.turn_id)
                bucket = self._turn_events.setdefault(event.turn_id, [])
                if len(bucket) < MAX_TURN_EVENTS:
                    bucket.append(event)
            if event.item_id:
                self._known_item_ids.add(event.item_id)
            if method == "item/completed" and event.turn_id and event.item_type == "agentMessage":
                item = params.get("item")
                if isinstance(item, Mapping) and isinstance(item.get("text"), str):
                    self._agent_messages[event.turn_id] = item["text"]
            if method == "turn/completed" and event.turn_id:
                self._completed_turns[event.turn_id] = event.status or "unknown"
            self._state_condition.notify_all()

    def _remember_event_key(self, key: tuple[str, str, str, str, str]) -> None:
        if len(self._seen_event_order) >= MAX_LIFECYCLE_EVENTS:
            oldest = self._seen_event_order.popleft()
            self._seen_event_keys.discard(oldest)
        self._seen_event_order.append(key)
        self._seen_event_keys.add(key)

    def _wait_for_turn(self, turn_id: str, timeout_seconds: float) -> str:
        deadline = self._monotonic_fn() + timeout_seconds
        with self._state_condition:
            while turn_id not in self._completed_turns:
                self._ensure_fresh_generation_locked()
                if self._fatal_error is not None:
                    raise self._fatal_error
                remaining = deadline - self._monotonic_fn()
                if remaining <= 0:
                    raise CodexTurnTimeout(f"Codex turn {turn_id} exceeded bounded turn timeout")
                self._state_condition.wait(min(remaining, 0.5))
            return self._completed_turns[turn_id]

    def _thread_identity_from_result(
        self,
        result: Mapping[str, Any],
        *,
        expected_thread_id: str | None,
        expected_ephemeral: bool | None,
    ) -> CodexThreadIdentity:
        self._attest_thread_response_identity(result)
        thread = result.get("thread")
        if not isinstance(thread, Mapping):
            raise CodexProtocolError("thread operation response is missing thread")
        thread_id = _optional_protocol_id(thread.get("id"), "thread.id")
        if thread_id is None:
            raise CodexProtocolError("thread operation response is missing thread id")
        if expected_thread_id is not None and thread_id != expected_thread_id:
            raise CodexThreadOwnershipError("thread/resume returned a different thread id")
        ephemeral = thread.get("ephemeral")
        if not isinstance(ephemeral, bool):
            raise CodexProtocolError("thread operation response is missing the required ephemeral flag")
        if expected_ephemeral is not None and ephemeral is not expected_ephemeral:
            raise CodexIdentityMismatchError("thread/start returned an unexpected ephemeral mode")
        self._attest_optional_identity_fields(thread, "thread operation")
        source_value = thread.get("source")
        source = source_value if isinstance(source_value, str) else None
        return CodexThreadIdentity(
            thread_id=thread_id,
            session_id=thread.get("sessionId") if isinstance(thread.get("sessionId"), str) else None,
            model_provider=thread.get("modelProvider") if isinstance(thread.get("modelProvider"), str) else None,
            source=source,
            status=_status_type(thread.get("status")),
            ephemeral=ephemeral,
        )

    def _attest_thread_response_identity(self, result: Mapping[str, Any]) -> None:
        """Fail closed on the stable ThreadStart/ResumeResponse identity fields."""

        observed_model = result.get("model")
        observed_effort = result.get("reasoningEffort")
        provider = result.get("modelProvider")
        if observed_model != self.model:
            raise CodexIdentityMismatchError("thread response did not attest the exact requested model")
        if observed_effort != self.reasoning_effort:
            raise CodexIdentityMismatchError(
                "thread response did not attest the exact requested reasoning effort"
            )
        if provider != "openai":
            raise CodexIdentityMismatchError("thread response did not attest the OpenAI model provider")
        if result.get("approvalPolicy") != self.approval_policy:
            raise CodexIdentityMismatchError("thread response did not attest the requested approval policy")
        if result.get("approvalsReviewer") != APPROVALS_REVIEWER:
            raise CodexIdentityMismatchError("thread response did not attest the bounded approvals reviewer")
        sandbox = result.get("sandbox")
        if not isinstance(sandbox, Mapping) or sandbox.get("type") != _sandbox_response_type(self.sandbox):
            raise CodexIdentityMismatchError("thread response did not attest the requested sandbox")
        if self.sandbox in {"read-only", "workspace-write"} and sandbox.get("networkAccess", False) is not False:
            raise CodexIdentityMismatchError(
                f"{self.sandbox} thread unexpectedly enabled network access"
            )
        self._attest_optional_identity_fields(result, "thread response")

    def _attest_model_list(self, result: Mapping[str, Any], epoch: int) -> CodexModelAttestation:
        rows = result.get("data")
        if not isinstance(rows, list):
            raise CodexIdentityMismatchError("model/list response is missing model data")
        matching: Mapping[str, Any] | None = None
        for row in rows:
            if (
                isinstance(row, Mapping)
                and row.get("id") == self.model
                and row.get("model") == self.model
            ):
                matching = row
                break
        if matching is None:
            raise CodexIdentityMismatchError(f"required model {self.model} is unavailable")
        efforts_raw = matching.get("supportedReasoningEfforts")
        if not isinstance(efforts_raw, list):
            raise CodexIdentityMismatchError("required model does not advertise reasoning efforts")
        efforts: list[str] = []
        for raw in efforts_raw:
            if isinstance(raw, str):
                efforts.append(raw)
            elif isinstance(raw, Mapping) and isinstance(raw.get("reasoningEffort"), str):
                efforts.append(raw["reasoningEffort"])
        if self.reasoning_effort not in efforts:
            raise CodexIdentityMismatchError(
                f"required effort {self.reasoning_effort} is unavailable for {self.model}"
            )
        return CodexModelAttestation(
            model=self.model,
            reasoning_effort=self.reasoning_effort,
            supported_reasoning_efforts=tuple(dict.fromkeys(efforts)),
            connection_epoch=epoch,
        )

    def _attest_optional_identity_fields(self, value: Mapping[str, Any], source: str) -> None:
        observed_model = value.get("model")
        if isinstance(observed_model, str) and observed_model != self.model:
            raise CodexIdentityMismatchError(f"{source} returned unexpected model {_sanitize_text(observed_model, 100)}")
        observed_effort = value.get("reasoningEffort", value.get("effort"))
        if isinstance(observed_effort, str) and observed_effort != self.reasoning_effort:
            raise CodexIdentityMismatchError(f"{source} returned unexpected reasoning effort")
        provider = value.get("modelProvider")
        if isinstance(provider, str) and provider != "openai":
            raise CodexIdentityMismatchError(f"{source} returned unexpected model provider")

    def _assert_owned_thread(self, thread_id: str) -> None:
        with self._state_condition:
            if thread_id not in self._owned_thread_ids:
                raise CodexThreadOwnershipError(f"thread {thread_id} is not Supervisor-owned")

    def _thread_lock(self, thread_id: str) -> threading.Lock:
        with self._thread_locks_guard:
            return self._thread_locks.setdefault(thread_id, threading.Lock())

    def _ensure_fresh_generation(self) -> None:
        if self._generation_is_stale():
            error = CodexStaleGenerationError(f"Supervisor generation {self.generation} is stale")
            self._set_fatal(error, self._connection_epoch)
            raise error

    def _ensure_fresh_generation_locked(self) -> None:
        if self._generation_is_stale():
            error = CodexStaleGenerationError(f"Supervisor generation {self.generation} is stale")
            self._fatal_error = error
            for pending in self._pending.values():
                pending.error = error
                pending.event.set()
            self._pending.clear()
            raise error

    def _generation_is_stale(self) -> bool:
        try:
            return bool(self._is_stale_generation_callback(self.generation))
        except Exception as exc:
            error = CodexProtocolError(f"stale-generation callback failed: {_safe_exception(exc)}")
            self._set_fatal(error, self._connection_epoch)
            raise error from exc

    def _set_fatal(self, error: BaseException, epoch: int) -> None:
        with self._state_condition:
            if epoch != self._connection_epoch:
                return
            self._fatal_error = error
            for pending in self._pending.values():
                pending.error = error
                pending.event.set()
            self._pending.clear()
            self._state_condition.notify_all()

    def _mark_disconnected(self, epoch: int, error: BaseException | None) -> None:
        with self._state_condition:
            if epoch != self._connection_epoch or self._closing:
                return
            disconnected = CodexDisconnectedError(
                "Codex App Server stdout disconnected"
                if error is None
                else f"Codex App Server stdio disconnected: {_safe_exception(error)}"
            )
            self._fatal_error = disconnected
            self._initialized = False
            self._loaded_thread_ids.clear()
            for pending in self._pending.values():
                pending.error = disconnected
                pending.event.set()
            self._pending.clear()
            self._state_condition.notify_all()

    def _dispose_current_process(self) -> None:
        with self._state_condition:
            process = self._process
            stdout_thread = self._stdout_thread
            stderr_thread = self._stderr_thread
            self._process = None
            self._stdout_thread = None
            self._stderr_thread = None
            self._initialized = False
            self._attestation = None
            self._loaded_thread_ids.clear()
        if process is None:
            return
        try:
            if process.stdin is not None:
                process.stdin.close()
        except (OSError, ValueError):
            pass
        if process.poll() is None:
            try:
                if os.name == "posix":
                    os.killpg(process.pid, signal.SIGTERM)
                else:
                    process.terminate()
                process.wait(timeout=self.shutdown_timeout_seconds)
            except subprocess.TimeoutExpired:
                if os.name == "posix":
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                else:
                    process.kill()
                try:
                    process.wait(timeout=self.shutdown_timeout_seconds)
                except subprocess.TimeoutExpired:
                    pass
            except (OSError, ProcessLookupError):
                pass
        current = threading.current_thread()
        for reader in (stdout_thread, stderr_thread):
            if reader is not None and reader is not current and reader.is_alive():
                reader.join(timeout=min(1.0, self.shutdown_timeout_seconds))

    def _sleep_before_retry(self, attempt: int) -> None:
        base = self.reconnect_backoff_seconds * (2 ** max(0, attempt - 1))
        try:
            jitter = max(0.0, float(self._jitter_fn(base)))
        except Exception as exc:
            raise CodexProtocolError(f"reconnect jitter callback failed: {_safe_exception(exc)}") from exc
        self._sleep_fn(base + jitter)


def sanitized_thread_snapshot(
    thread: Mapping[str, Any],
    *,
    model_attestation: CodexModelAttestation,
) -> dict[str, Any]:
    """Return the narrow, secret-free result used by the optional canary."""

    thread_id = _optional_protocol_id(thread.get("id"), "thread.id")
    if thread_id is None:
        raise CodexProtocolError("thread snapshot is missing id")
    return {
        "status": "ok",
        "transport": "stdio",
        "model": model_attestation.model,
        "reasoning_effort": model_attestation.reasoning_effort,
        "thread": {
            "id": thread_id,
            "session_id": thread.get("sessionId") if isinstance(thread.get("sessionId"), str) else None,
            "source": thread.get("source") if isinstance(thread.get("source"), str) else None,
            "model_provider": thread.get("modelProvider") if isinstance(thread.get("modelProvider"), str) else None,
            "cli_version": thread.get("cliVersion") if isinstance(thread.get("cliVersion"), str) else None,
            "status": _status_type(thread.get("status")),
            "archived": bool(thread.get("archived")) if "archived" in thread else None,
            "ephemeral": thread.get("ephemeral") if isinstance(thread.get("ephemeral"), bool) else None,
        },
    }


def _parse_lifecycle_event(
    method: str,
    params: Mapping[str, Any],
    epoch: int,
    thread_by_turn: Mapping[str, str],
) -> CodexLifecycleEvent | None:
    if method not in {
        "thread/started",
        "thread/closed",
        "thread/status/changed",
        "turn/started",
        "turn/completed",
        "item/started",
        "item/completed",
    }:
        return None
    thread_id = _optional_protocol_id(params.get("threadId"), "notification.threadId")
    turn_id = _optional_protocol_id(params.get("turnId"), "notification.turnId")
    item_id: str | None = None
    item_type: str | None = None
    status: str | None = None
    thread = params.get("thread")
    if isinstance(thread, Mapping):
        thread_id = thread_id or _optional_protocol_id(thread.get("id"), "notification.thread.id")
        status = _status_type(thread.get("status"))
    turn = params.get("turn")
    if isinstance(turn, Mapping):
        turn_id = turn_id or _optional_protocol_id(turn.get("id"), "notification.turn.id")
        thread_id = thread_id or _optional_protocol_id(turn.get("threadId"), "notification.turn.threadId")
        if turn.get("status") is not None:
            status = str(turn.get("status"))
    if turn_id and not thread_id:
        thread_id = thread_by_turn.get(turn_id)
    item = params.get("item")
    if isinstance(item, Mapping):
        item_id = _optional_protocol_id(item.get("id"), "notification.item.id")
        item_type = item.get("type") if isinstance(item.get("type"), str) else None
        if item.get("status") is not None:
            status = str(item.get("status"))
    if method == "thread/status/changed":
        status = _status_type(params.get("status"))
    if method.startswith("turn/") and turn_id is None:
        raise CodexProtocolError(f"{method} notification is missing turn id")
    if method.startswith("item/") and (turn_id is None or item_id is None):
        raise CodexProtocolError(f"{method} notification is missing turn or item id")
    return CodexLifecycleEvent(
        method=method,
        thread_id=thread_id,
        turn_id=turn_id,
        item_id=item_id,
        item_type=item_type,
        status=status,
        connection_epoch=epoch,
    )


def _validated_turn_input(value: str | Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(value, str):
        text = _bounded_text(value, "turn input", 200_000)
        return [{"type": "text", "text": text}]
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence) or not value:
        raise ValueError("turn input must be non-empty text or input items")
    items: list[dict[str, Any]] = []
    for index, raw in enumerate(value):
        if not isinstance(raw, Mapping):
            raise ValueError(f"turn input item {index} must be an object")
        item = dict(raw)
        if not isinstance(item.get("type"), str):
            raise ValueError(f"turn input item {index} is missing type")
        items.append(item)
    try:
        serialized = json.dumps(items, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("turn input items must be JSON serializable") from exc
    if len(serialized) > MAX_REQUEST_CHARS // 2:
        raise ValueError("turn input exceeds bounded size")
    return items


def _parse_contract_json(raw_text: str) -> Mapping[str, Any]:
    if len(raw_text) > 256_000:
        raise CodexContractError("schema-bound output exceeds bounded size")
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise CodexContractError("schema-bound output is not valid JSON") from exc
    if not isinstance(payload, Mapping):
        raise CodexContractError("schema-bound output root must be an object")
    return payload


def _validated_recovery_baseline(value: Sequence[str]) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError("baseline_turn_ids must be a sequence of exact turn ids")
    if len(value) > MAX_RECOVERY_BASELINE_TURNS:
        raise ValueError("baseline_turn_ids exceeds the bounded recovery limit")
    result: list[str] = []
    seen: set[str] = set()
    for index, raw_turn_id in enumerate(value):
        if not isinstance(raw_turn_id, str) or not _SAFE_ID_RE.fullmatch(raw_turn_id):
            raise ValueError(f"baseline_turn_ids[{index}] must be a safe bounded id")
        if raw_turn_id in seen:
            raise ValueError("baseline_turn_ids must not contain duplicates")
        seen.add(raw_turn_id)
        result.append(raw_turn_id)
    return tuple(result)


def _validated_recovery_items(
    value: object,
) -> tuple[tuple[Mapping[str, Any], ...], Mapping[str, Any]]:
    if not isinstance(value, list) or len(value) > MAX_RECOVERY_ITEMS:
        raise CodexProtocolError(
            "thread/read recovery requires a bounded full items array"
        )
    items: list[Mapping[str, Any]] = []
    seen_item_ids: set[str] = set()
    agent_messages: list[tuple[int, Mapping[str, Any]]] = []
    for index, raw_item in enumerate(value):
        if not isinstance(raw_item, Mapping):
            raise CodexProtocolError(
                f"thread/read recovery item {index} is not an object"
            )
        item_id = _optional_protocol_id(
            raw_item.get("id"), f"thread/read recovery items[{index}].id"
        )
        if item_id is None:
            raise CodexProtocolError("thread/read recovery item is missing id")
        if item_id in seen_item_ids:
            raise CodexProtocolError(
                "thread/read recovery contains duplicate item ids"
            )
        seen_item_ids.add(item_id)
        item_type = raw_item.get("type")
        if not isinstance(item_type, str) or not 1 <= len(item_type) <= 100:
            raise CodexProtocolError(
                "thread/read recovery item has an invalid type"
            )
        if item_type == "agentMessage":
            if not isinstance(raw_item.get("text"), str):
                raise CodexProtocolError(
                    "thread/read recovery agentMessage is missing text"
                )
            phase = raw_item.get("phase")
            if phase not in {None, "commentary", "final_answer"}:
                raise CodexProtocolError(
                    "thread/read recovery agentMessage has an invalid phase"
                )
            agent_messages.append((index, raw_item))
        items.append(raw_item)
    if not agent_messages:
        raise CodexContractError(
            "completed persisted turn has no schema-bound agentMessage"
        )
    final_messages = [entry for entry in agent_messages if entry[1].get("phase") == "final_answer"]
    if len(final_messages) > 1:
        raise CodexContractError(
            "completed persisted turn has multiple final agentMessage items"
        )
    selected_index, selected = final_messages[0] if final_messages else agent_messages[-1]
    if any(index > selected_index for index, _item in agent_messages):
        raise CodexContractError(
            "persisted final agentMessage is not the last assistant output"
        )
    return tuple(items), selected


def _validate_expected_identity(
    *,
    generation: int,
    task_id: str,
    workstream_id: str,
    expected_generation: int | None,
    expected_task_id: str | None,
    expected_workstream_id: str | None,
) -> None:
    if expected_generation is not None and generation != expected_generation:
        raise CodexContractError("contract generation does not match active Supervisor generation")
    if expected_task_id is not None and task_id != expected_task_id:
        raise CodexContractError("contract task id mismatch")
    if expected_workstream_id is not None and workstream_id != expected_workstream_id:
        raise CodexContractError("contract workstream id mismatch")


def _require_mapping(value: object, label: str) -> None:
    if not isinstance(value, Mapping):
        raise CodexContractError(f"{label} must be an object")


def _require_exact_keys(
    value: Mapping[str, Any],
    *,
    required: set[str],
    optional: set[str],
    label: str,
) -> None:
    keys = set(value)
    missing = required - keys
    extra = keys - required - optional
    if missing:
        raise CodexContractError(f"{label} is missing required fields: {', '.join(sorted(missing))}")
    if extra:
        raise CodexContractError(f"{label} contains unsupported fields: {', '.join(sorted(extra))}")


def _validated_id(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SAFE_ID_RE.fullmatch(value):
        raise CodexContractError(f"{label} must be a safe bounded id")
    return value


def _validated_thread_id(value: object) -> str:
    if not isinstance(value, str) or not _SAFE_ID_RE.fullmatch(value):
        raise ValueError("thread id must be a safe bounded id")
    return value


def _optional_protocol_id(value: object, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not _SAFE_ID_RE.fullmatch(value):
        raise CodexProtocolError(f"{label} must be a safe bounded id")
    return value


def _positive_int(value: object, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _positive_float(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or float(value) <= 0:
        raise ValueError(f"{label} must be positive")
    return float(value)


def _contract_positive_int(value: object, label: str) -> int:
    try:
        return _positive_int(value, label)
    except ValueError as exc:
        raise CodexContractError(str(exc)) from exc


def _bounded_text(value: object, label: str, max_chars: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text")
    text = value.strip()
    if not text or len(text) > max_chars:
        raise ValueError(f"{label} must contain 1..{max_chars} characters")
    return text


def _contract_text(value: object, label: str, max_chars: int) -> str:
    try:
        return _bounded_text(value, label, max_chars)
    except ValueError as exc:
        raise CodexContractError(str(exc)) from exc


def _bounded_text_sequence(
    value: object,
    label: str,
    *,
    max_items: int,
    max_chars: int,
) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > max_items:
        raise CodexContractError(f"{label} must be a bounded array")
    items: list[str] = []
    for index, item in enumerate(value):
        try:
            items.append(_bounded_text(item, f"{label}[{index}]", max_chars))
        except ValueError as exc:
            raise CodexContractError(str(exc)) from exc
    return tuple(items)


def _status_type(value: object) -> str | None:
    if isinstance(value, str):
        return _sanitize_text(value, 100)
    if isinstance(value, Mapping) and isinstance(value.get("type"), str):
        return _sanitize_text(value["type"], 100)
    return None


def _sandbox_response_type(mode: SandboxMode) -> str:
    return {
        "read-only": "readOnly",
        "workspace-write": "workspaceWrite",
        "danger-full-access": "dangerFullAccess",
    }[mode]


def _sanitize_text(value: object, max_chars: int) -> str:
    text = _ANSI_RE.sub("", str(value or ""))
    for pattern, replacement in _SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    text = "".join(char if char in "\t\n\r" or ord(char) >= 32 else "?" for char in text)
    text = text.strip()
    if len(text) > max_chars:
        text = text[: max(0, max_chars - 1)] + "…"
    return text


def _safe_exception(error: BaseException | None) -> str:
    if error is None:
        return "unknown disconnect"
    return _sanitize_text(str(error), 500) or error.__class__.__name__


_CHECKPOINT_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "schema_version": {"type": "string", "const": CHECKPOINT_SCHEMA_VERSION},
        "kind": {"type": "string", "const": "checkpoint"},
        "task_id": {"type": "string", "minLength": 1, "maxLength": 200},
        "workstream_id": {"type": "string", "minLength": 1, "maxLength": 200},
        "generation": {"type": "integer", "minimum": 1},
        "stage": {"type": "string", "enum": sorted(CHECKPOINT_STAGES)},
        "progress_percent": {"type": "integer", "enum": sorted(CHECKPOINT_PROGRESS_VALUES)},
        "delta": {"type": "string", "minLength": 1, "maxLength": 2_000},
        "current_action": {"type": "string", "minLength": 1, "maxLength": 2_000},
        "evidence": {
            "type": "array",
            "maxItems": 64,
            "items": {"type": "string", "minLength": 1, "maxLength": 2_000},
        },
        "causal_fingerprint": {"type": ["string", "null"], "minLength": 1, "maxLength": 500},
    },
    "required": [
        "schema_version",
        "kind",
        "task_id",
        "workstream_id",
        "generation",
        "stage",
        "progress_percent",
        "delta",
        "current_action",
        "evidence",
        "causal_fingerprint",
    ],
}

_TERMINAL_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "schema_version": {"type": "string", "const": TERMINAL_SCHEMA_VERSION},
        "kind": {"type": "string", "const": "terminal"},
        "task_id": {"type": "string", "minLength": 1, "maxLength": 200},
        "workstream_id": {"type": "string", "minLength": 1, "maxLength": 200},
        "generation": {"type": "integer", "minimum": 1},
        "status": {"type": "string", "enum": sorted(TERMINAL_STATUSES)},
        "summary": {"type": "string", "minLength": 1, "maxLength": 4_000},
        "checks": {
            "type": "array",
            "maxItems": 128,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string", "minLength": 1, "maxLength": 300},
                    "status": {"type": "string", "enum": sorted(TERMINAL_CHECK_STATUSES)},
                    "evidence": {"type": "string", "minLength": 1, "maxLength": 2_000},
                },
                "required": ["name", "status", "evidence"],
            },
        },
        "artifacts": {
            "type": "array",
            "maxItems": 128,
            "items": {"type": "string", "minLength": 1, "maxLength": 2_000},
        },
        "limitations": {
            "type": "array",
            "maxItems": 64,
            "items": {"type": "string", "minLength": 1, "maxLength": 2_000},
        },
        "blocker": {"type": ["string", "null"], "minLength": 1, "maxLength": 2_000},
    },
    "required": [
        "schema_version",
        "kind",
        "task_id",
        "workstream_id",
        "generation",
        "status",
        "summary",
        "checks",
        "artifacts",
        "limitations",
        "blocker",
    ],
}
