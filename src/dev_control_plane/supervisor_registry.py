"""Durable single-writer registry for the local Orchestrator v2 Supervisor.

All mutating methods require a live :class:`SupervisorFence`.  Each method owns
one short SQLite transaction and returns before an external transport, model or
GitHub call can begin.  Callers must use reserve/call/receipt sequencing; this
module intentionally accepts no callbacks while a transaction is open.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import stat
import time
from typing import Any, Iterator, Mapping, Sequence

from .orchestration_contracts import (
    ExecutorIdentity,
    TaskPassport,
    Workstream,
    canonical_contract_json,
    contract_to_dict,
    validate_workstream_against_passport,
)

CURRENT_SCHEMA_VERSION = 3
DEFAULT_DELIVERED_PROJECTION_RETENTION = 512
NON_COALESCIBLE_OUTBOX_KINDS = frozenset(
    {
        "terminal",
        "human_gate",
        "attention",
        "curator_attention",
        "terminal_attention",
        "serious_stall",
    }
)
CORRECTIVE_TRIGGER_STATUSES = frozenset(
    {
        "parked",
        "ambiguous_turn_parked",
        "missing_verified_checkpoint",
        "application_failed_fail_closed",
        "arbiter_failed_fail_closed",
        "parked_fail_closed",
        "human_gate",
    }
)
CORRECTIVE_MUTATION_OUTBOX_KINDS = frozenset(
    {
        "codex_thread_start",
        "codex_followup",
        "codex_successor_start",
        "release_candidate_intake",
        "release_candidate_resolution",
        "release_action",
        "release_arbiter_case",
        "incident_arbiter_case",
        "incident_arbiter_application",
        "target_lane_closure",
    }
)
TASK_STATES = frozenset({"active", "waiting_release", "recovering", "parked", "acceptance_pending", "accepted"})
OUTBOX_STATES = frozenset({"pending", "inflight", "delivered", "superseded"})
_LOCK_KINDS = frozenset({"task", "resource", "release_lane", "thread", "workspace"})


class RegistryError(RuntimeError):
    """Base registry failure."""


class LeaseHeldError(RegistryError):
    """Another Supervisor generation still owns the durable lease."""


class StaleGenerationError(RegistryError):
    """A stale or expired Supervisor/executor generation attempted to mutate state."""


class CASConflict(RegistryError):
    """An optimistic revision no longer matches."""


class IdempotencyConflict(RegistryError):
    """An idempotency/event identifier was reused for different content."""


class LockConflict(RegistryError):
    """One or more requested locks are owned by another logical operation."""


class RegistryValidationError(RegistryError):
    """A registry operation violates a deterministic invariant."""


@dataclass(frozen=True)
class SupervisorFence:
    owner_id: str
    generation: int
    token: str = field(repr=False)
    expires_at: float


@dataclass(frozen=True)
class TaskRecord:
    task_id: str
    revision: int
    state: str
    passport: dict[str, Any]
    created_at: float
    updated_at: float


@dataclass(frozen=True)
class WorkstreamRecord:
    workstream_id: str
    task_id: str
    generation: int
    revision: int
    state: str
    contract: dict[str, Any]
    current: bool


@dataclass(frozen=True)
class ExecutorBinding:
    task_id: str
    workstream_id: str
    executor_generation: int
    thread_id: str
    host_id: str
    model: str
    reasoning: str
    state: str
    predecessor_generation: int | None
    proof_event_id: str | None


@dataclass(frozen=True)
class OutboxMessage:
    event_id: str
    kind: str
    payload: dict[str, Any]
    task_id: str | None
    coalescible: bool
    coalesce_key: str | None
    attempts: int
    claim_token: str = field(repr=False)
    claimed_generation: int
    writer_generation: int


@dataclass(frozen=True)
class LockGrant:
    kind: str
    keys: tuple[str, ...]
    owner_task_id: str
    owner_workstream_id: str | None
    token: str = field(repr=False)
    generation: int
    expires_at: float


_MIGRATION_1 = (
    """
    CREATE TABLE schema_migrations (
        version INTEGER PRIMARY KEY,
        applied_at TEXT NOT NULL,
        migration_digest TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE supervisor_lease (
        singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
        generation INTEGER NOT NULL CHECK(generation >= 0),
        owner_id TEXT,
        lease_token TEXT,
        expires_at REAL NOT NULL DEFAULT 0,
        updated_at REAL NOT NULL
    )
    """,
    """
    INSERT INTO supervisor_lease(singleton, generation, owner_id, lease_token, expires_at, updated_at)
    VALUES (1, 0, NULL, NULL, 0, 0)
    """,
    """
    CREATE TABLE tasks (
        task_id TEXT PRIMARY KEY,
        revision INTEGER NOT NULL CHECK(revision >= 1),
        state TEXT NOT NULL,
        passport_json TEXT NOT NULL,
        passport_digest TEXT NOT NULL,
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL,
        writer_generation INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE workstreams (
        workstream_id TEXT NOT NULL,
        generation INTEGER NOT NULL CHECK(generation >= 1),
        task_id TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE RESTRICT,
        revision INTEGER NOT NULL CHECK(revision >= 1),
        state TEXT NOT NULL,
        contract_json TEXT NOT NULL,
        contract_digest TEXT NOT NULL,
        is_current INTEGER NOT NULL CHECK(is_current IN (0, 1)),
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL,
        writer_generation INTEGER NOT NULL,
        PRIMARY KEY(workstream_id, generation)
    )
    """,
    """
    CREATE UNIQUE INDEX one_current_workstream_generation
    ON workstreams(workstream_id) WHERE is_current = 1
    """,
    """
    CREATE TABLE executor_bindings (
        task_id TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE RESTRICT,
        workstream_id TEXT NOT NULL,
        executor_generation INTEGER NOT NULL CHECK(executor_generation >= 1),
        thread_id TEXT NOT NULL,
        host_id TEXT NOT NULL,
        model TEXT NOT NULL,
        reasoning TEXT NOT NULL,
        state TEXT NOT NULL CHECK(state IN ('pending', 'active', 'stale')),
        predecessor_generation INTEGER,
        checkpoint_digest TEXT NOT NULL,
        proof_event_id TEXT,
        created_at REAL NOT NULL,
        activated_at REAL,
        writer_generation INTEGER NOT NULL,
        PRIMARY KEY(task_id, workstream_id, executor_generation)
    )
    """,
    """
    CREATE UNIQUE INDEX one_active_executor
    ON executor_bindings(task_id, workstream_id) WHERE state = 'active'
    """,
    """
    CREATE UNIQUE INDEX one_pending_successor
    ON executor_bindings(task_id, workstream_id) WHERE state = 'pending'
    """,
    """
    CREATE TABLE events (
        event_id TEXT PRIMARY KEY,
        task_id TEXT,
        workstream_id TEXT,
        event_type TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        payload_digest TEXT NOT NULL,
        executor_generation INTEGER,
        writer_generation INTEGER NOT NULL,
        created_at REAL NOT NULL
    )
    """,
    """
    CREATE INDEX events_task_created ON events(task_id, created_at, event_id)
    """,
    """
    CREATE TABLE inbox (
        message_id TEXT PRIMARY KEY,
        source TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        payload_digest TEXT NOT NULL,
        state TEXT NOT NULL CHECK(state IN ('received', 'processed')),
        writer_generation INTEGER NOT NULL,
        received_at REAL NOT NULL,
        processed_at REAL
    )
    """,
    """
    CREATE TABLE outbox (
        event_id TEXT PRIMARY KEY,
        kind TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        payload_digest TEXT NOT NULL,
        task_id TEXT,
        coalescible INTEGER NOT NULL CHECK(coalescible IN (0, 1)),
        coalesce_key TEXT,
        state TEXT NOT NULL CHECK(state IN ('pending', 'inflight', 'delivered', 'superseded')),
        attempts INTEGER NOT NULL DEFAULT 0,
        available_at REAL NOT NULL,
        claim_token TEXT,
        claimed_by TEXT,
        claimed_generation INTEGER,
        claimed_until REAL,
        delivered_at REAL,
        last_error TEXT,
        writer_generation INTEGER NOT NULL,
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    )
    """,
    """
    CREATE INDEX outbox_delivery_queue ON outbox(state, available_at, created_at, event_id)
    """,
    """
    CREATE UNIQUE INDEX one_pending_coalesced_projection
    ON outbox(kind, coalesce_key) WHERE state = 'pending' AND coalesce_key IS NOT NULL
    """,
    """
    CREATE TABLE locks (
        lock_kind TEXT NOT NULL,
        lock_key TEXT NOT NULL,
        owner_task_id TEXT NOT NULL,
        owner_workstream_id TEXT,
        lock_token TEXT NOT NULL,
        writer_generation INTEGER NOT NULL,
        acquired_at REAL NOT NULL,
        expires_at REAL NOT NULL,
        revision INTEGER NOT NULL CHECK(revision >= 1),
        PRIMARY KEY(lock_kind, lock_key)
    )
    """,
    """
    CREATE INDEX locks_owner ON locks(owner_task_id, owner_workstream_id, lock_kind)
    """,
    """
    CREATE TABLE idempotency_keys (
        scope TEXT NOT NULL,
        idempotency_key TEXT NOT NULL,
        request_digest TEXT NOT NULL,
        result_json TEXT NOT NULL,
        writer_generation INTEGER NOT NULL,
        created_at REAL NOT NULL,
        PRIMARY KEY(scope, idempotency_key)
    )
    """,
)

_MIGRATION_2 = (
    """
    CREATE TABLE projection_transport_state (
        singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
        generation INTEGER NOT NULL CHECK(generation >= 0),
        sequence INTEGER NOT NULL CHECK(sequence >= 0),
        revision INTEGER NOT NULL CHECK(revision >= 0),
        updated_at REAL NOT NULL,
        CHECK(
            (generation = 0 AND sequence = 0)
            OR (generation > 0 AND sequence > 0)
        )
    )
    """,
    """
    INSERT INTO projection_transport_state(singleton, generation, sequence, revision, updated_at)
    VALUES (1, 0, 0, 0, 0)
    """,
)

_MIGRATION_3 = (
    """
    CREATE TABLE workspace_bindings (
        task_id TEXT NOT NULL,
        workstream_id TEXT NOT NULL,
        canonical_path TEXT NOT NULL UNIQUE,
        path_digest TEXT NOT NULL,
        created_at REAL NOT NULL,
        writer_generation INTEGER NOT NULL,
        PRIMARY KEY(task_id, workstream_id)
    )
    """,
)


class SupervisorRegistry:
    """A process-independent SQLite registry fenced by one durable generation."""

    def __init__(
        self,
        db_path: Path | str,
        *,
        lease_seconds: float = 30.0,
        busy_timeout_ms: int = 5_000,
        delivered_projection_retention: int = DEFAULT_DELIVERED_PROJECTION_RETENTION,
        clock: Any = time.time,
    ) -> None:
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        if busy_timeout_ms < 1:
            raise ValueError("busy_timeout_ms must be positive")
        if not 1 <= delivered_projection_retention <= 100_000:
            raise ValueError("delivered_projection_retention must be between 1 and 100000")
        candidate = Path(db_path).expanduser()
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        candidate = Path(os.path.abspath(candidate))
        if candidate.name in {"", ".", ".."}:
            raise RegistryValidationError("registry database filename is invalid")
        if candidate.is_symlink():
            raise RegistryValidationError("registry database must not be a symlink")
        self.db_path = candidate
        self.backup_dir = self.db_path.parent / "backups"
        self.lease_seconds = float(lease_seconds)
        self.busy_timeout_ms = int(busy_timeout_ms)
        self.delivered_projection_retention = int(delivered_projection_retention)
        self._clock = clock
        self._prepare_private_paths()
        self._initialize()

    def _prepare_private_paths(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        resolved_parent = self.db_path.parent.resolve(strict=True)
        parent = resolved_parent.lstat()
        if not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.geteuid():
            raise RegistryValidationError(
                "registry state directory must be owned by the Supervisor user"
            )
        resolved_parent.chmod(0o700)
        self.db_path = resolved_parent / self.db_path.name
        self.backup_dir = resolved_parent / "backups"
        self._validate_private_file(self.db_path, required=False)
        if self.backup_dir.is_symlink():
            raise RegistryValidationError("registry backup directory must not be a symlink")
        self.backup_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        backup = self.backup_dir.lstat()
        if not stat.S_ISDIR(backup.st_mode) or backup.st_uid != os.geteuid():
            raise RegistryValidationError(
                "registry backup directory must be owned by the Supervisor user"
            )
        self.backup_dir.chmod(0o700)

    @contextmanager
    def _migration_guard(self) -> Iterator[None]:
        lock_path = self.db_path.with_suffix(self.db_path.suffix + ".migrate.lock")
        flags = os.O_CREAT | os.O_RDWR
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            fd = os.open(lock_path, flags, 0o600)
        except OSError as exc:
            raise RegistryValidationError(
                "registry migration lock could not be opened safely"
            ) from exc
        try:
            opened = os.fstat(fd)
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_uid != os.geteuid()
                or opened.st_nlink != 1
            ):
                raise RegistryValidationError(
                    "registry migration lock must be one private regular file"
                )
            os.fchmod(fd, 0o600)
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def _initialize(self) -> None:
        with self._migration_guard():
            existed = self.db_path.exists() and self.db_path.stat().st_size > 0
            connection = self._connect()
            try:
                observed = int(connection.execute("PRAGMA user_version").fetchone()[0])
                if observed > CURRENT_SCHEMA_VERSION:
                    raise RegistryError(
                        f"registry schema {observed} is newer than supported {CURRENT_SCHEMA_VERSION}"
                    )
                has_objects = bool(
                    connection.execute(
                        "SELECT 1 FROM sqlite_master WHERE type IN ('table', 'index') AND name NOT LIKE 'sqlite_%' LIMIT 1"
                    ).fetchone()
                )
                if observed < CURRENT_SCHEMA_VERSION and existed and has_objects:
                    self._backup_connection(connection, suffix=f"before-v{observed}-to-v{CURRENT_SCHEMA_VERSION}")
                if observed < 1:
                    connection.execute("BEGIN EXCLUSIVE")
                    try:
                        for statement in _MIGRATION_1:
                            connection.execute(statement)
                        digest = hashlib.sha256("\n".join(_MIGRATION_1).encode("utf-8")).hexdigest()
                        connection.execute(
                            "INSERT INTO schema_migrations(version, applied_at, migration_digest) VALUES (?, ?, ?)",
                            (1, _utc_now(), digest),
                        )
                        connection.execute("PRAGMA user_version = 1")
                        connection.commit()
                    except Exception:
                        connection.rollback()
                        raise
                if observed < 2:
                    connection.execute("BEGIN EXCLUSIVE")
                    try:
                        for statement in _MIGRATION_2:
                            connection.execute(statement)
                        generation, sequence, revision = _projection_transport_seed(connection)
                        connection.execute(
                            """
                            UPDATE projection_transport_state
                            SET generation = ?, sequence = ?, revision = ?, updated_at = ?
                            WHERE singleton = 1
                            """,
                            (generation, sequence, revision, self._now()),
                        )
                        digest = hashlib.sha256("\n".join(_MIGRATION_2).encode("utf-8")).hexdigest()
                        connection.execute(
                            "INSERT INTO schema_migrations(version, applied_at, migration_digest) VALUES (?, ?, ?)",
                            (2, _utc_now(), digest),
                        )
                        connection.execute("PRAGMA user_version = 2")
                        connection.commit()
                    except Exception:
                        connection.rollback()
                        raise
                if observed < 3:
                    connection.execute("BEGIN EXCLUSIVE")
                    try:
                        for statement in _MIGRATION_3:
                            connection.execute(statement)
                        digest = hashlib.sha256("\n".join(_MIGRATION_3).encode("utf-8")).hexdigest()
                        connection.execute(
                            "INSERT INTO schema_migrations(version, applied_at, migration_digest) VALUES (?, ?, ?)",
                            (3, _utc_now(), digest),
                        )
                        connection.execute("PRAGMA user_version = 3")
                        connection.commit()
                    except Exception:
                        connection.rollback()
                        raise
            finally:
                connection.close()
            self._enforce_private_files()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.db_path,
            timeout=self.busy_timeout_ms / 1000.0,
            isolation_level=None,
        )
        try:
            connection.row_factory = sqlite3.Row
            connection.execute(f"PRAGMA busy_timeout = {self.busy_timeout_ms}")
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = FULL")
            connection.execute("PRAGMA trusted_schema = OFF")
            self._enforce_private_files()
            return connection
        except Exception:
            connection.close()
            raise

    def _validate_private_file(self, path: Path, *, required: bool) -> None:
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            if required:
                raise RegistryValidationError("registry private file is unavailable")
            return
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or metadata.st_nlink != 1
        ):
            raise RegistryValidationError(
                "registry database files must be service-owned regular files without links"
            )

    def _enforce_private_files(self) -> None:
        parent = self.db_path.parent.lstat()
        if (
            not stat.S_ISDIR(parent.st_mode)
            or parent.st_uid != os.geteuid()
            or stat.S_IMODE(parent.st_mode) != 0o700
        ):
            raise RegistryValidationError("registry state directory lost private ownership")
        for path in (
            self.db_path,
            Path(str(self.db_path) + "-wal"),
            Path(str(self.db_path) + "-shm"),
        ):
            self._validate_private_file(path, required=path == self.db_path)
            if path.exists():
                path.chmod(0o600)

    @contextmanager
    def _transaction(self, fence: SupervisorFence | None = None) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            if fence is not None:
                self._assert_fence(connection, fence)
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @contextmanager
    def _reader(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            yield connection
        finally:
            connection.close()

    def acquire_generation(self, owner_id: str, *, now: float | None = None) -> SupervisorFence:
        owner = _machine_value("owner_id", owner_id)
        observed_now = self._now(now)
        with self._transaction() as connection:
            row = connection.execute("SELECT * FROM supervisor_lease WHERE singleton = 1").fetchone()
            if row is None:
                raise RegistryError("supervisor lease row is missing")
            if row["owner_id"] is not None and float(row["expires_at"]) > observed_now:
                raise LeaseHeldError(
                    f"Supervisor generation {row['generation']} is leased until {row['expires_at']:.6f}"
                )
            generation = int(row["generation"]) + 1
            token = secrets.token_urlsafe(32)
            expires_at = observed_now + self.lease_seconds
            connection.execute(
                """
                UPDATE supervisor_lease
                SET generation = ?, owner_id = ?, lease_token = ?, expires_at = ?, updated_at = ?
                WHERE singleton = 1
                """,
                (generation, owner, token, expires_at, observed_now),
            )
            # A new fenced generation is admitted only after the prior lease
            # is absent/expired.  Its locks and claims cannot be attested by
            # the new token, so reclaim them atomically for deterministic
            # event/outbox reconstruction.
            connection.execute(
                "DELETE FROM locks WHERE writer_generation < ?",
                (generation,),
            )
            connection.execute(
                """
                UPDATE outbox
                SET state = 'pending', claim_token = NULL, claimed_by = NULL,
                    claimed_generation = NULL, claimed_until = NULL,
                    available_at = ?, updated_at = ?
                WHERE state = 'inflight' AND claimed_generation < ?
                    AND kind != 'curator_attention'
                """,
                (observed_now, observed_now, generation),
            )
        return SupervisorFence(owner, generation, token, expires_at)

    def renew_generation(self, fence: SupervisorFence, *, now: float | None = None) -> SupervisorFence:
        observed_now = self._now(now)
        with self._transaction(fence) as connection:
            expires_at = observed_now + self.lease_seconds
            connection.execute(
                "UPDATE supervisor_lease SET expires_at = ?, updated_at = ? WHERE singleton = 1",
                (expires_at, observed_now),
            )
        return SupervisorFence(fence.owner_id, fence.generation, fence.token, expires_at)

    def release_generation(self, fence: SupervisorFence) -> None:
        with self._transaction(fence) as connection:
            connection.execute(
                """
                UPDATE supervisor_lease
                SET owner_id = NULL, lease_token = NULL, expires_at = 0, updated_at = ?
                WHERE singleton = 1
                """,
                (self._now(),),
            )

    def current_generation(self) -> dict[str, Any]:
        with self._reader() as connection:
            row = connection.execute("SELECT * FROM supervisor_lease WHERE singleton = 1").fetchone()
        if row is None:
            return {}
        return {
            "generation": int(row["generation"]),
            "owner_id": row["owner_id"],
            "expires_at": float(row["expires_at"]),
            "updated_at": float(row["updated_at"]),
        }

    def _assert_fence(self, connection: sqlite3.Connection, fence: SupervisorFence) -> None:
        row = connection.execute("SELECT * FROM supervisor_lease WHERE singleton = 1").fetchone()
        now = self._now()
        if (
            row is None
            or row["owner_id"] != fence.owner_id
            or int(row["generation"]) != fence.generation
            or row["lease_token"] != fence.token
            or float(row["expires_at"]) <= now
        ):
            raise StaleGenerationError("Supervisor generation is stale, expired or fenced out")

    def create_task(
        self,
        passport: TaskPassport,
        fence: SupervisorFence,
        *,
        idempotency_key: str,
    ) -> TaskRecord:
        if passport.revision != 1:
            raise RegistryValidationError("a new task passport must start at revision 1")
        key = _machine_value("idempotency_key", idempotency_key)
        payload_json = canonical_contract_json(passport)
        request_digest = _digest(payload_json)
        now = self._now()
        with self._transaction(fence) as connection:
            replay = self._idempotent_replay(connection, "create_task", key, request_digest)
            if replay is not None:
                return self._task_record(connection, passport.task_id)
            existing = connection.execute("SELECT passport_digest FROM tasks WHERE task_id = ?", (passport.task_id,)).fetchone()
            if existing is not None:
                raise IdempotencyConflict("task_id already exists under another operation")
            connection.execute(
                """
                INSERT INTO tasks(task_id, revision, state, passport_json, passport_digest, created_at, updated_at, writer_generation)
                VALUES (?, 1, 'active', ?, ?, ?, ?, ?)
                """,
                (passport.task_id, payload_json, request_digest, now, now, fence.generation),
            )
            result = {"task_id": passport.task_id, "revision": 1}
            self._record_idempotency(connection, "create_task", key, request_digest, result, fence, now)
            return self._task_record(connection, passport.task_id)

    def get_task(self, task_id: str) -> TaskRecord | None:
        with self._reader() as connection:
            row = connection.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        return _task_from_row(row) if row is not None else None

    def list_tasks(self) -> tuple[TaskRecord, ...]:
        with self._reader() as connection:
            rows = connection.execute("SELECT * FROM tasks ORDER BY created_at, task_id").fetchall()
        return tuple(_task_from_row(row) for row in rows)

    def get_workstream(self, workstream_id: str, *, generation: int | None = None) -> WorkstreamRecord | None:
        with self._reader() as connection:
            if generation is None:
                row = connection.execute(
                    "SELECT * FROM workstreams WHERE workstream_id = ? AND is_current = 1",
                    (workstream_id,),
                ).fetchone()
            else:
                row = connection.execute(
                    "SELECT * FROM workstreams WHERE workstream_id = ? AND generation = ?",
                    (workstream_id, generation),
                ).fetchone()
        return _workstream_from_row(row) if row is not None else None

    def list_workstreams(self, *, current_only: bool = True) -> tuple[WorkstreamRecord, ...]:
        with self._reader() as connection:
            where = "WHERE is_current = 1" if current_only else ""
            rows = connection.execute(
                f"SELECT * FROM workstreams {where} ORDER BY task_id, workstream_id, generation"
            ).fetchall()
        return tuple(_workstream_from_row(row) for row in rows)

    def bind_workspace(
        self,
        *,
        task_id: str,
        workstream_id: str,
        canonical_path: str,
        fence: SupervisorFence,
    ) -> bool:
        """Bind one immutable managed workspace before any executor call."""

        task = _machine_value("task_id", task_id)
        workstream = _machine_value("workstream_id", workstream_id)
        if (
            not isinstance(canonical_path, str)
            or not canonical_path.startswith("/")
            or canonical_path != canonical_path.strip()
            or len(canonical_path) > 8_000
        ):
            raise RegistryValidationError("canonical workspace path is invalid")
        with self._transaction(fence) as connection:
            return self._bind_workspace_tx(
                connection,
                task,
                workstream,
                canonical_path,
                fence,
                now=self._now(),
            )

    def _bind_workspace_tx(
        self,
        connection: sqlite3.Connection,
        task_id: str,
        workstream_id: str,
        canonical_path: str,
        fence: SupervisorFence,
        *,
        now: float,
    ) -> bool:
        if (
            not isinstance(canonical_path, str)
            or not canonical_path.startswith("/")
            or canonical_path != canonical_path.strip()
            or len(canonical_path) > 8_000
        ):
            raise RegistryValidationError("canonical workspace path is invalid")
        digest = _digest(canonical_path)
        current = connection.execute(
            "SELECT * FROM workspace_bindings WHERE task_id = ? AND workstream_id = ?",
            (task_id, workstream_id),
        ).fetchone()
        if current is not None:
            if (
                current["canonical_path"] == canonical_path
                and current["path_digest"] == digest
            ):
                return False
            raise IdempotencyConflict(
                "task/workstream is already bound to another managed workspace"
            )
        requested_path = Path(canonical_path)
        owners = connection.execute(
            "SELECT task_id,workstream_id,canonical_path FROM workspace_bindings"
        ).fetchall()
        for owner in owners:
            owned_path = Path(str(owner["canonical_path"]))
            if (
                requested_path == owned_path
                or requested_path in owned_path.parents
                or owned_path in requested_path.parents
            ):
                raise LockConflict(
                    "managed workspace overlaps another task/workstream binding"
                )
        connection.execute(
            """
            INSERT INTO workspace_bindings(
                task_id,workstream_id,canonical_path,path_digest,created_at,writer_generation
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (task_id, workstream_id, canonical_path, digest, now, fence.generation),
        )
        return True

    def get_workspace_binding(
        self, task_id: str, workstream_id: str
    ) -> dict[str, Any] | None:
        with self._reader() as connection:
            row = connection.execute(
                "SELECT * FROM workspace_bindings WHERE task_id = ? AND workstream_id = ?",
                (task_id, workstream_id),
            ).fetchone()
        if row is None:
            return None
        return {
            "task_id": str(row["task_id"]),
            "workstream_id": str(row["workstream_id"]),
            "canonical_path": str(row["canonical_path"]),
            "path_digest": str(row["path_digest"]),
            "created_at": float(row["created_at"]),
            "writer_generation": int(row["writer_generation"]),
        }

    def update_task_state(
        self,
        task_id: str,
        *,
        expected_revision: int,
        new_state: str,
        fence: SupervisorFence,
    ) -> TaskRecord:
        _machine_value("task_id", task_id)
        if new_state not in TASK_STATES:
            raise RegistryValidationError(f"unknown task state: {new_state!r}")
        with self._transaction(fence) as connection:
            current = connection.execute(
                "SELECT revision, passport_json FROM tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
            if current is None or int(current["revision"]) != expected_revision:
                raise CASConflict("task revision changed before state transition")
            passport_payload = json.loads(current["passport_json"])
            passport_payload["revision"] = expected_revision + 1
            passport_json = _canonical_json(passport_payload)
            cursor = connection.execute(
                """
                UPDATE tasks
                SET state = ?, revision = revision + 1, passport_json = ?, passport_digest = ?,
                    updated_at = ?, writer_generation = ?
                WHERE task_id = ? AND revision = ?
                """,
                (
                    new_state, passport_json, _digest(passport_json), self._now(), fence.generation,
                    task_id, expected_revision,
                ),
            )
            if cursor.rowcount != 1:
                raise CASConflict("task revision changed before state transition")
            return self._task_record(connection, task_id)

    def set_task_aggregate_state(
        self,
        task_id: str,
        *,
        expected_revision: int,
        new_state: str,
        fence: SupervisorFence,
    ) -> TaskRecord:
        """Change only aggregate runtime state without invalidating sibling work."""

        _machine_value("task_id", task_id)
        if new_state not in {"active", "recovering"}:
            raise RegistryValidationError(
                "non-revision aggregate state may only be active or recovering"
            )
        with self._transaction(fence) as connection:
            cursor = connection.execute(
                """
                UPDATE tasks
                SET state = ?, updated_at = ?, writer_generation = ?
                WHERE task_id = ? AND revision = ?
                """,
                (
                    new_state,
                    self._now(),
                    fence.generation,
                    task_id,
                    expected_revision,
                ),
            )
            if cursor.rowcount != 1:
                raise CASConflict("task changed before aggregate state update")
            return self._task_record(connection, task_id)

    def replace_task_passport(
        self,
        passport: TaskPassport,
        *,
        expected_revision: int,
        fence: SupervisorFence,
    ) -> TaskRecord:
        if passport.revision != expected_revision + 1:
            raise RegistryValidationError("replacement passport revision must increment exactly once")
        payload_json = canonical_contract_json(passport)
        with self._transaction(fence) as connection:
            cursor = connection.execute(
                """
                UPDATE tasks
                SET revision = ?, passport_json = ?, passport_digest = ?, updated_at = ?, writer_generation = ?
                WHERE task_id = ? AND revision = ?
                """,
                (
                    passport.revision,
                    payload_json,
                    _digest(payload_json),
                    self._now(),
                    fence.generation,
                    passport.task_id,
                    expected_revision,
                ),
            )
            if cursor.rowcount != 1:
                raise CASConflict("task revision changed before passport replacement")
            return self._task_record(connection, passport.task_id)

    def replace_task_passport_with_event(
        self,
        passport: TaskPassport,
        *,
        expected_revision: int,
        message_id: str,
        source: str,
        input_payload: Mapping[str, Any],
        event_id: str,
        event_payload: Mapping[str, Any],
        outbox_items: Sequence[Mapping[str, Any]],
        fence: SupervisorFence,
    ) -> dict[str, Any]:
        """Atomically revise a Passport and fence all old release actions."""

        if passport.revision != expected_revision + 1:
            raise RegistryValidationError("replacement passport revision must increment exactly once")
        message = _machine_value("message_id", message_id)
        source_name = _machine_value("source", source)
        event = _machine_value("event_id", event_id)
        input_json = _canonical_json(input_payload)
        input_digest = _digest(input_json)
        passport_json = canonical_contract_json(passport)
        now = self._now()
        with self._transaction(fence) as connection:
            existing_inbox = connection.execute(
                "SELECT * FROM inbox WHERE message_id = ?", (message,)
            ).fetchone()
            if existing_inbox is not None:
                if (
                    existing_inbox["payload_digest"] != input_digest
                    or existing_inbox["source"] != source_name
                ):
                    raise IdempotencyConflict("Passport revision message_id was reused")
                existing_event = connection.execute(
                    "SELECT payload_json FROM events WHERE event_id = ?", (event,)
                ).fetchone()
                if existing_event is None:
                    raise RegistryError("Passport revision inbox lacks its durable event")
                payload = json.loads(existing_event["payload_json"])
                return {
                    "created": False,
                    "task_id": passport.task_id,
                    "revision": int(payload["new_revision"]),
                    "superseded_release_outbox": int(payload["superseded_release_outbox"]),
                    "released_reservation_locks": int(payload["released_reservation_locks"]),
                    "event_id": event,
                }
            current = connection.execute(
                "SELECT revision FROM tasks WHERE task_id = ?", (passport.task_id,)
            ).fetchone()
            if current is None or int(current["revision"]) != expected_revision:
                raise CASConflict("task changed before Passport revision")
            # A manifest revision may invalidate queued release policy, but it
            # must never revoke a live executor or an in-flight actuator's
            # locks.  Expired rows are harmless; every live non-scheduler token
            # causes the entire revision transaction to fail closed.
            connection.execute(
                "DELETE FROM locks WHERE owner_task_id = ? AND expires_at <= ?",
                (passport.task_id, now),
            )
            mutation_kinds = (
                "codex_followup",
                "codex_successor_start",
                "release_candidate_resolution",
                "release_action",
                "release_arbiter_case",
                "incident_arbiter_case",
                "incident_arbiter_application",
                "target_lane_closure",
            )
            mutation_placeholders = ",".join("?" for _ in mutation_kinds)
            inflight = connection.execute(
                f"""
                SELECT kind FROM outbox
                WHERE task_id = ? AND state = 'inflight'
                    AND kind IN ({mutation_placeholders})
                LIMIT 1
                """,
                (passport.task_id, *mutation_kinds),
            ).fetchone()
            if inflight is not None:
                raise LockConflict(
                    "Passport revision cannot interrupt an in-flight mutation"
                )
            live_locks = connection.execute(
                """
                SELECT lock_kind, lock_key, owner_workstream_id, lock_token,
                       writer_generation
                FROM locks
                WHERE owner_task_id = ? AND expires_at > ?
                ORDER BY lock_token, lock_kind, lock_key
                """,
                (passport.task_id, now),
            ).fetchall()
            scheduler_groups: dict[tuple[str | None, str, int], list[sqlite3.Row]] = {}
            for row in live_locks:
                if row["lock_kind"] in {"thread", "workspace"}:
                    raise LockConflict(
                        "Passport revision cannot revoke a live execution reservation"
                    )
                key = (
                    row["owner_workstream_id"],
                    row["lock_token"],
                    int(row["writer_generation"]),
                )
                scheduler_groups.setdefault(key, []).append(row)
            for rows in scheduler_groups.values():
                kinds = {str(row["lock_kind"]) for row in rows}
                if (
                    not kinds <= {"task", "resource", "release_lane"}
                    or "release_lane" not in kinds
                    or "task" not in kinds
                ):
                    raise LockConflict(
                        "Passport revision found a live non-scheduler reservation"
                    )
            connection.execute(
                """
                INSERT INTO inbox(message_id, source, payload_json, payload_digest, state, writer_generation, received_at)
                VALUES (?, ?, ?, ?, 'received', ?, ?)
                """,
                (message, source_name, input_json, input_digest, fence.generation, now),
            )
            cursor = connection.execute(
                """
                UPDATE tasks
                SET revision = ?, passport_json = ?, passport_digest = ?, updated_at = ?, writer_generation = ?
                WHERE task_id = ? AND revision = ?
                """,
                (
                    passport.revision,
                    passport_json,
                    _digest(passport_json),
                    now,
                    fence.generation,
                    passport.task_id,
                    expected_revision,
                ),
            )
            if cursor.rowcount != 1:
                raise CASConflict("task changed before Passport revision")
            release_kinds = (
                "release_candidate_intake",
                "release_candidate_resolution",
                "release_action",
                "release_arbiter_case",
                "target_lane_closure",
            )
            placeholders = ",".join("?" for _ in release_kinds)
            superseded = connection.execute(
                f"""
                UPDATE outbox
                SET state = 'superseded', claim_token = NULL, claimed_by = NULL,
                    claimed_generation = NULL, claimed_until = NULL, updated_at = ?
                WHERE task_id = ? AND state IN ('pending','inflight')
                    AND kind IN ({placeholders})
                """,
                (now, passport.task_id, *release_kinds),
            ).rowcount
            released = 0
            for (owner_workstream_id, token, generation), rows in scheduler_groups.items():
                cursor = connection.execute(
                    """
                    DELETE FROM locks
                    WHERE owner_task_id = ? AND owner_workstream_id IS ?
                        AND lock_token = ? AND writer_generation = ?
                        AND lock_kind IN ('task','resource','release_lane')
                    """,
                    (
                        passport.task_id,
                        owner_workstream_id,
                        token,
                        generation,
                    ),
                )
                if cursor.rowcount != len(rows):
                    raise LockConflict(
                        "scheduler reservation changed during Passport revision"
                    )
                released += cursor.rowcount
            durable_payload = {
                **dict(event_payload),
                "superseded_release_outbox": superseded,
                "released_reservation_locks": released,
            }
            event_json = _canonical_json(durable_payload)
            self._append_event_tx(
                connection,
                event,
                "passport_revised",
                event_json,
                _digest(event_json),
                fence,
                task_id=passport.task_id,
                workstream_id=None,
                executor_generation=None,
                now=now,
            )
            allowed_keys = {
                "event_id", "kind", "payload", "task_id", "coalescible", "coalesce_key"
            }
            for item in outbox_items:
                if not isinstance(item, Mapping) or set(item) != allowed_keys:
                    raise RegistryValidationError("Passport revision outbox item fields are invalid")
                payload = item["payload"]
                if not isinstance(payload, Mapping) or not isinstance(item["coalescible"], bool):
                    raise RegistryValidationError("Passport revision outbox item payload is invalid")
                self._enqueue_outbox_tx(
                    connection,
                    str(item["event_id"]),
                    str(item["kind"]),
                    payload,
                    fence,
                    task_id=str(item["task_id"]) if item["task_id"] is not None else None,
                    coalescible=item["coalescible"],
                    coalesce_key=str(item["coalesce_key"]) if item["coalesce_key"] is not None else None,
                    now=now,
                )
            connection.execute(
                "UPDATE inbox SET state = 'processed', processed_at = ? WHERE message_id = ?",
                (now, message),
            )
            return {
                "created": True,
                "task_id": passport.task_id,
                "revision": passport.revision,
                "superseded_release_outbox": superseded,
                "released_reservation_locks": released,
                "event_id": event,
            }

    def apply_corrective_generation(
        self,
        replacement_passport: TaskPassport,
        corrective_workstream: Workstream,
        *,
        expected_task_revision: int,
        expected_workstream_generation: int,
        expected_workstream_revision: int,
        expected_executor_generation: int,
        trigger_event_id: str,
        trigger_event_digest: str,
        verified_checkpoint_id: str,
        verified_checkpoint_digest: str,
        canonical_workspace: str,
        message_id: str,
        source: str,
        input_payload: Mapping[str, Any],
        recovery_event_id: str,
        recovery_event_payload: Mapping[str, Any],
        successor_event_id: str,
        successor_payload: Mapping[str, Any],
        projection_event_id: str,
        fence: SupervisorFence,
    ) -> dict[str, Any]:
        """Atomically consume one parked cause and reserve one corrective successor.

        The predecessor remains the active executor until the separately
        receipted App Server startup proof.  This transition only changes
        durable local intent; it never performs transport or model work.
        """

        if replacement_passport.revision != expected_task_revision + 1:
            raise RegistryValidationError(
                "corrective Passport revision must increment exactly once"
            )
        if (
            corrective_workstream.revision != 1
            or corrective_workstream.generation != expected_workstream_generation + 1
            or corrective_workstream.corrective_of_generation
            != expected_workstream_generation
            or corrective_workstream.state != "recovering"
            or corrective_workstream.executor is not None
        ):
            raise RegistryValidationError(
                "corrective workstream must be the exact unbound recovering successor"
            )
        validate_workstream_against_passport(
            corrective_workstream, replacement_passport
        )
        if (
            isinstance(expected_executor_generation, bool)
            or expected_executor_generation < 1
            or isinstance(expected_workstream_revision, bool)
            or expected_workstream_revision < 1
        ):
            raise RegistryValidationError("corrective CAS coordinates are invalid")
        task_id = _machine_value("task_id", replacement_passport.task_id)
        workstream_id = _machine_value(
            "workstream_id", corrective_workstream.workstream_id
        )
        trigger = _machine_value("trigger_event_id", trigger_event_id)
        checkpoint = _machine_value("verified_checkpoint_id", verified_checkpoint_id)
        message = _machine_value("message_id", message_id)
        source_name = _machine_value("source", source)
        recovery_event = _machine_value("recovery_event_id", recovery_event_id)
        successor_event = _machine_value("successor_event_id", successor_event_id)
        projection_event = _machine_value("projection_event_id", projection_event_id)
        for label, value in (
            ("trigger_event_digest", trigger_event_digest),
            ("verified_checkpoint_digest", verified_checkpoint_digest),
        ):
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(character not in "0123456789abcdef" for character in value)
            ):
                raise RegistryValidationError(f"{label} must be sha256")
        if (
            not isinstance(canonical_workspace, str)
            or not canonical_workspace.startswith("/")
            or canonical_workspace != canonical_workspace.strip()
            or len(canonical_workspace) > 8_000
        ):
            raise RegistryValidationError("corrective workspace path is invalid")

        passport_json = canonical_contract_json(replacement_passport)
        workstream_json = canonical_contract_json(corrective_workstream)
        input_json = _canonical_json(input_payload)
        input_digest = _digest(input_json)
        base_recovery_payload = dict(recovery_event_payload)
        successor_json = _canonical_json(successor_payload)
        now = self._now()

        with self._transaction(fence) as connection:
            existing_inbox = connection.execute(
                "SELECT * FROM inbox WHERE message_id = ?", (message,)
            ).fetchone()
            if existing_inbox is not None:
                if (
                    existing_inbox["payload_digest"] != input_digest
                    or existing_inbox["source"] != source_name
                ):
                    raise IdempotencyConflict(
                        "corrective recovery message_id was reused"
                    )
                existing_event = connection.execute(
                    "SELECT payload_json FROM events WHERE event_id = ?",
                    (recovery_event,),
                ).fetchone()
                if existing_event is None:
                    raise RegistryError(
                        "corrective recovery inbox lacks its durable event"
                    )
                durable = json.loads(existing_event["payload_json"])
                return {
                    "created": False,
                    "task_id": task_id,
                    "task_revision": int(durable["task_revision"]),
                    "workstream_id": workstream_id,
                    "workstream_generation": int(
                        durable["workstream_generation"]
                    ),
                    "workstream_revision": int(
                        durable["workstream_revision"]
                    ),
                    "successor_event_id": str(durable["successor_event_id"]),
                    "recovery_event_id": recovery_event,
                }

            task = connection.execute(
                "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
            if (
                task is None
                or int(task["revision"]) != expected_task_revision
                or task["state"] not in {"parked", "active", "recovering"}
            ):
                raise CASConflict(
                    "corrective recovery requires an exact active aggregate task revision"
                )
            old_passport = json.loads(task["passport_json"])
            new_passport = contract_to_dict(replacement_passport)
            old_routing = sorted(
                item
                for item in old_passport.get("resources", [])
                if isinstance(item, str)
                and item.startswith(("target:", "release-lane:"))
            )
            new_routing = sorted(
                item
                for item in new_passport.get("resources", [])
                if isinstance(item, str)
                and item.startswith(("target:", "release-lane:"))
            )
            if (
                old_passport.get("task_id") != replacement_passport.task_id
                or old_passport.get("curator") != new_passport.get("curator")
                or old_passport.get("workstream_ids")
                != new_passport.get("workstream_ids")
                or old_passport.get("contour") != new_passport.get("contour")
                or old_passport.get("release_manifest")
                != new_passport.get("release_manifest")
                or old_passport.get("multi_pr_intent")
                != new_passport.get("multi_pr_intent")
                or old_passport.get("multi_deploy_intent")
                != new_passport.get("multi_deploy_intent")
                or old_routing != new_routing
            ):
                raise RegistryValidationError(
                    "corrective recovery cannot change curator, contour, closure manifest or routing"
                )

            old_workstream = connection.execute(
                """
                SELECT * FROM workstreams
                WHERE workstream_id = ? AND task_id = ? AND is_current = 1
                """,
                (workstream_id, task_id),
            ).fetchone()
            if (
                old_workstream is None
                or int(old_workstream["generation"])
                != expected_workstream_generation
                or int(old_workstream["revision"])
                != expected_workstream_revision
                or old_workstream["state"] not in {"blocked", "parked"}
            ):
                raise CASConflict(
                    "corrective recovery requires the exact parked workstream generation"
                )
            old_contract = json.loads(old_workstream["contract_json"])
            if (
                old_contract.get("root_workstream_id")
                != corrective_workstream.root_workstream_id
                or old_contract.get("workstream_id") != workstream_id
                or old_contract.get("task_id") != task_id
            ):
                raise RegistryValidationError(
                    "corrective workstream changed its root identity"
                )

            active_executor = connection.execute(
                """
                SELECT * FROM executor_bindings
                WHERE task_id = ? AND workstream_id = ? AND state = 'active'
                """,
                (task_id, workstream_id),
            ).fetchone()
            if (
                active_executor is None
                or int(active_executor["executor_generation"])
                != expected_executor_generation
            ):
                raise CASConflict(
                    "corrective recovery executor generation is stale"
                )
            if connection.execute(
                """
                SELECT 1 FROM executor_bindings
                WHERE task_id = ? AND workstream_id = ? AND state = 'pending'
                """,
                (task_id, workstream_id),
            ).fetchone() is not None:
                raise LockConflict(
                    "corrective recovery cannot create a second pending successor"
                )

            workspace = connection.execute(
                """
                SELECT canonical_path FROM workspace_bindings
                WHERE task_id = ? AND workstream_id = ?
                """,
                (task_id, workstream_id),
            ).fetchone()
            if (
                workspace is None
                or workspace["canonical_path"] != canonical_workspace
            ):
                raise CASConflict(
                    "corrective recovery workspace differs from its immutable binding"
                )

            checkpoint_row = connection.execute(
                """
                SELECT * FROM events
                WHERE event_id = ? AND task_id = ? AND workstream_id = ?
                    AND event_type = 'checkpoint' AND executor_generation = ?
                """,
                (
                    checkpoint,
                    task_id,
                    workstream_id,
                    expected_executor_generation,
                ),
            ).fetchone()
            if checkpoint_row is None:
                raise CASConflict(
                    "corrective recovery lacks its exact verified checkpoint"
                )
            checkpoint_payload = json.loads(checkpoint_row["payload_json"])
            checkpoint_contract = checkpoint_payload.get("contract")
            if (
                not isinstance(checkpoint_contract, Mapping)
                or _digest(_canonical_json(checkpoint_contract))
                != verified_checkpoint_digest
            ):
                raise CASConflict(
                    "corrective recovery checkpoint digest is stale"
                )
            newer_checkpoint = connection.execute(
                """
                SELECT 1 FROM events
                WHERE task_id = ? AND workstream_id = ? AND event_type = 'checkpoint'
                    AND executor_generation = ?
                    AND (created_at > ? OR (created_at = ? AND event_id > ?))
                LIMIT 1
                """,
                (
                    task_id,
                    workstream_id,
                    expected_executor_generation,
                    checkpoint_row["created_at"],
                    checkpoint_row["created_at"],
                    checkpoint,
                ),
            ).fetchone()
            if newer_checkpoint is not None:
                raise CASConflict(
                    "corrective recovery checkpoint is not the latest verified checkpoint"
                )

            eligible_trigger_rows = connection.execute(
                """
                SELECT * FROM events
                WHERE task_id = ? AND workstream_id = ?
                    AND event_type IN ('incident_policy', 'release_stalled')
                ORDER BY created_at, event_id
                """,
                (task_id, workstream_id),
            ).fetchall()
            eligible: list[sqlite3.Row] = []
            for row in eligible_trigger_rows:
                payload = json.loads(row["payload_json"])
                status = str(payload.get("status") or "")
                if (
                    row["event_type"] == "release_stalled"
                    and status == "parked"
                ) or (
                    row["event_type"] == "incident_policy"
                    and status in CORRECTIVE_TRIGGER_STATUSES
                ):
                    eligible.append(row)
            if not eligible or eligible[-1]["event_id"] != trigger:
                raise CASConflict(
                    "corrective recovery trigger is not the latest parked event"
                )
            trigger_row = eligible[-1]
            if trigger_row["payload_digest"] != trigger_event_digest:
                raise CASConflict("corrective recovery trigger digest is stale")
            trigger_payload = json.loads(trigger_row["payload_json"])
            attestation_digest = base_recovery_payload.get(
                "owner_action_attestation_digest"
            )
            if trigger_payload.get("status") == "human_gate":
                if (
                    not isinstance(attestation_digest, str)
                    or len(attestation_digest) != 64
                    or any(
                        character not in "0123456789abcdef"
                        for character in attestation_digest
                    )
                ):
                    raise RegistryValidationError(
                        "HumanGate recovery requires a verified attestation digest"
                    )
            elif attestation_digest is not None:
                raise RegistryValidationError(
                    "non-HumanGate recovery cannot consume an owner action attestation"
                )
            resolved_attention = base_recovery_payload.get(
                "resolved_attention_event_id"
            )
            if trigger_payload.get("status") == "human_gate" and not isinstance(
                resolved_attention, str
            ):
                raise RegistryValidationError(
                    "HumanGate recovery requires its exact attention binding"
                )
            if resolved_attention is not None:
                resolved_attention = _machine_value(
                    "resolved_attention_event_id", resolved_attention
                )
                attention_row = connection.execute(
                    """
                    SELECT task_id,payload_json,state FROM outbox
                    WHERE event_id = ? AND kind = 'curator_attention'
                    """,
                    (resolved_attention,),
                ).fetchone()
                if attention_row is None or attention_row["task_id"] != task_id:
                    raise CASConflict(
                        "corrective recovery attention binding disappeared"
                    )
                attention_payload = json.loads(attention_row["payload_json"])
                expected_attention_kind = (
                    "human_gate"
                    if trigger_payload.get("status") == "human_gate"
                    else "serious_stall"
                )
                if (
                    attention_payload.get("workstream_id") != workstream_id
                    or attention_payload.get("kind") != expected_attention_kind
                ):
                    raise CASConflict(
                        "corrective recovery attention binding is stale"
                    )
                if attention_row["state"] == "inflight":
                    raise LockConflict(
                        "corrective recovery cannot revoke inflight curator delivery"
                    )
                if attention_row["state"] == "pending":
                    connection.execute(
                        """
                        UPDATE outbox
                        SET state = 'superseded', updated_at = ?,
                            writer_generation = ?
                        WHERE event_id = ? AND state = 'pending'
                        """,
                        (now, fence.generation, resolved_attention),
                    )
                elif attention_row["state"] != "delivered":
                    raise CASConflict(
                        "corrective recovery attention was already superseded"
                    )

            consumed = connection.execute(
                """
                SELECT payload_json FROM events
                WHERE task_id = ? AND workstream_id = ?
                    AND event_type = 'incident_policy'
                ORDER BY created_at, event_id
                """,
                (task_id, workstream_id),
            ).fetchall()
            if any(
                json.loads(row["payload_json"]).get("trigger_event_id") == trigger
                for row in consumed
            ):
                raise IdempotencyConflict(
                    "corrective recovery trigger was already consumed"
                )

            mutation_kinds = tuple(sorted(CORRECTIVE_MUTATION_OUTBOX_KINDS))
            placeholders = ",".join("?" for _ in mutation_kinds)
            inflight = connection.execute(
                f"""
                SELECT kind FROM outbox
                WHERE task_id = ? AND state = 'inflight'
                    AND kind IN ({placeholders})
                LIMIT 1
                """,
                (task_id, *mutation_kinds),
            ).fetchone()
            if inflight is not None:
                raise LockConflict(
                    "corrective recovery cannot interrupt an in-flight mutation"
                )
            pending_start = connection.execute(
                """
                SELECT kind FROM outbox
                WHERE task_id = ? AND state = 'pending'
                    AND kind IN ('codex_thread_start', 'codex_successor_start')
                LIMIT 1
                """,
                (task_id,),
            ).fetchone()
            if pending_start is not None:
                raise LockConflict(
                    "corrective recovery cannot create a duplicate executor start"
                )

            connection.execute(
                "DELETE FROM locks WHERE owner_task_id = ? AND expires_at <= ?",
                (task_id, now),
            )
            live_execution_lock = connection.execute(
                """
                SELECT 1 FROM locks
                WHERE owner_task_id = ? AND expires_at > ?
                    AND lock_kind IN ('thread', 'workspace')
                LIMIT 1
                """,
                (task_id, now),
            ).fetchone()
            if live_execution_lock is not None:
                raise LockConflict(
                    "corrective recovery cannot revoke a live executor reservation"
                )
            released_scheduler_locks = connection.execute(
                """
                DELETE FROM locks
                WHERE owner_task_id = ? AND expires_at > ?
                    AND lock_kind IN ('task', 'resource', 'release_lane')
                """,
                (task_id, now),
            ).rowcount
            remaining_lock = connection.execute(
                "SELECT 1 FROM locks WHERE owner_task_id = ? AND expires_at > ? LIMIT 1",
                (task_id, now),
            ).fetchone()
            if remaining_lock is not None:
                raise LockConflict(
                    "corrective recovery found an unclassified live lock"
                )

            connection.execute(
                """
                INSERT INTO inbox(
                    message_id, source, payload_json, payload_digest, state,
                    writer_generation, received_at
                ) VALUES (?, ?, ?, ?, 'received', ?, ?)
                """,
                (
                    message,
                    source_name,
                    input_json,
                    input_digest,
                    fence.generation,
                    now,
                ),
            )
            task_update = connection.execute(
                """
                UPDATE tasks
                SET revision = ?, state = 'recovering', passport_json = ?,
                    passport_digest = ?, updated_at = ?, writer_generation = ?
                WHERE task_id = ? AND revision = ?
                    AND state IN ('parked','active','recovering')
                """,
                (
                    replacement_passport.revision,
                    passport_json,
                    _digest(passport_json),
                    now,
                    fence.generation,
                    task_id,
                    expected_task_revision,
                ),
            )
            if task_update.rowcount != 1:
                raise CASConflict("task changed during corrective recovery")
            workstream_update = connection.execute(
                """
                UPDATE workstreams
                SET is_current = 0, updated_at = ?, writer_generation = ?
                WHERE workstream_id = ? AND generation = ? AND revision = ?
                    AND is_current = 1
                """,
                (
                    now,
                    fence.generation,
                    workstream_id,
                    expected_workstream_generation,
                    expected_workstream_revision,
                ),
            )
            if workstream_update.rowcount != 1:
                raise CASConflict("workstream changed during corrective recovery")
            connection.execute(
                """
                INSERT INTO workstreams(
                    workstream_id, generation, task_id, revision, state,
                    contract_json, contract_digest, is_current, created_at,
                    updated_at, writer_generation
                ) VALUES (?, ?, ?, 1, 'recovering', ?, ?, 1, ?, ?, ?)
                """,
                (
                    workstream_id,
                    corrective_workstream.generation,
                    task_id,
                    workstream_json,
                    _digest(workstream_json),
                    now,
                    now,
                    fence.generation,
                ),
            )
            supersede_kinds = tuple(
                sorted(
                    CORRECTIVE_MUTATION_OUTBOX_KINDS
                    - {"codex_thread_start", "codex_successor_start"}
                )
            )
            supersede_placeholders = ",".join("?" for _ in supersede_kinds)
            superseded = connection.execute(
                f"""
                UPDATE outbox
                SET state = 'superseded', claim_token = NULL,
                    claimed_by = NULL, claimed_generation = NULL,
                    claimed_until = NULL, updated_at = ?, writer_generation = ?
                WHERE task_id = ? AND state = 'pending'
                    AND kind IN ({supersede_placeholders})
                """,
                (now, fence.generation, task_id, *supersede_kinds),
            ).rowcount

            durable_recovery = {
                **base_recovery_payload,
                "task_revision": replacement_passport.revision,
                "workstream_generation": corrective_workstream.generation,
                "workstream_revision": corrective_workstream.revision,
                "trigger_event_id": trigger,
                "trigger_event_digest": trigger_event_digest,
                "verified_checkpoint_id": checkpoint,
                "verified_checkpoint_digest": verified_checkpoint_digest,
                "successor_event_id": successor_event,
                "superseded_mutation_outbox": superseded,
                "released_scheduler_locks": released_scheduler_locks,
            }
            recovery_json = _canonical_json(durable_recovery)
            self._append_event_tx(
                connection,
                recovery_event,
                "incident_policy",
                recovery_json,
                _digest(recovery_json),
                fence,
                task_id=task_id,
                workstream_id=workstream_id,
                executor_generation=expected_executor_generation,
                now=now,
            )
            self._enqueue_outbox_tx(
                connection,
                successor_event,
                "codex_successor_start",
                json.loads(successor_json),
                fence,
                task_id=task_id,
                coalescible=False,
                coalesce_key=None,
                now=now,
            )
            self._enqueue_outbox_tx(
                connection,
                projection_event,
                "projection_dirty",
                {"trigger_event_id": recovery_event},
                fence,
                task_id=task_id,
                coalescible=True,
                coalesce_key="global-projection",
                now=now,
            )
            connection.execute(
                "UPDATE inbox SET state = 'processed', processed_at = ? WHERE message_id = ?",
                (now, message),
            )
            return {
                "created": True,
                "task_id": task_id,
                "task_revision": replacement_passport.revision,
                "workstream_id": workstream_id,
                "workstream_generation": corrective_workstream.generation,
                "workstream_revision": corrective_workstream.revision,
                "successor_event_id": successor_event,
                "recovery_event_id": recovery_event,
            }

    def create_workstream(self, workstream: Workstream, fence: SupervisorFence) -> WorkstreamRecord:
        with self._transaction(fence) as connection:
            task = self._task_record(connection, workstream.task_id)
            passport = _passport_for_validation(task.passport)
            validate_workstream_against_passport(workstream, passport)
            payload_json = _canonical_json(contract_to_dict(workstream))
            payload_digest = _digest(payload_json)
            exact = connection.execute(
                """
                SELECT contract_digest FROM workstreams
                WHERE workstream_id = ? AND generation = ?
                """,
                (workstream.workstream_id, workstream.generation),
            ).fetchone()
            if exact is not None:
                if exact["contract_digest"] != payload_digest:
                    raise IdempotencyConflict("workstream generation already exists with different content")
                return self._workstream_record(connection, workstream.workstream_id, workstream.generation)
            current = connection.execute(
                "SELECT generation FROM workstreams WHERE workstream_id = ? AND is_current = 1",
                (workstream.workstream_id,),
            ).fetchone()
            expected_previous = workstream.generation - 1
            if (current is None and workstream.generation != 1) or (
                current is not None and int(current["generation"]) != expected_previous
            ):
                raise CASConflict("workstream generation is not the successor of the current generation")
            if current is not None:
                connection.execute(
                    "UPDATE workstreams SET is_current = 0, updated_at = ?, writer_generation = ? WHERE workstream_id = ? AND is_current = 1",
                    (self._now(), fence.generation, workstream.workstream_id),
                )
            now = self._now()
            connection.execute(
                """
                INSERT INTO workstreams(
                    workstream_id, generation, task_id, revision, state, contract_json, contract_digest,
                    is_current, created_at, updated_at, writer_generation
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
                """,
                (
                    workstream.workstream_id, workstream.generation, workstream.task_id, workstream.revision,
                    workstream.state, payload_json, payload_digest, now, now, fence.generation,
                ),
            )
            return self._workstream_record(connection, workstream.workstream_id, workstream.generation)

    def update_workstream_state(
        self,
        workstream_id: str,
        generation: int,
        *,
        expected_revision: int,
        new_state: str,
        fence: SupervisorFence,
    ) -> WorkstreamRecord:
        from .orchestration_contracts import WORKSTREAM_STATES

        if new_state not in WORKSTREAM_STATES:
            raise RegistryValidationError(f"unknown workstream state: {new_state!r}")
        with self._transaction(fence) as connection:
            current = connection.execute(
                """
                SELECT revision, contract_json FROM workstreams
                WHERE workstream_id = ? AND generation = ? AND is_current = 1
                """,
                (workstream_id, generation),
            ).fetchone()
            if current is None or int(current["revision"]) != expected_revision:
                raise CASConflict("workstream revision/generation changed before transition")
            contract_payload = json.loads(current["contract_json"])
            contract_payload["revision"] = expected_revision + 1
            contract_payload["state"] = new_state
            contract_json = _canonical_json(contract_payload)
            cursor = connection.execute(
                """
                UPDATE workstreams
                SET state = ?, revision = revision + 1, contract_json = ?, contract_digest = ?,
                    updated_at = ?, writer_generation = ?
                WHERE workstream_id = ? AND generation = ? AND revision = ? AND is_current = 1
                """,
                (
                    new_state, contract_json, _digest(contract_json), self._now(), fence.generation,
                    workstream_id, generation, expected_revision,
                ),
            )
            if cursor.rowcount != 1:
                raise CASConflict("workstream revision/generation changed before transition")
            return self._workstream_record(connection, workstream_id, generation)

    def bind_initial_workstream_executor(
        self,
        workstream: Workstream,
        *,
        expected_revision: int,
        fence: SupervisorFence,
    ) -> WorkstreamRecord:
        """Bind an exact proven identity to one staged generation-one stream."""

        if workstream.executor is None or workstream.generation != 1:
            raise RegistryValidationError(
                "initial workstream binding requires an exact executor"
            )
        contract_json = canonical_contract_json(workstream)
        with self._transaction(fence) as connection:
            row = connection.execute(
                """
                SELECT * FROM workstreams
                WHERE workstream_id = ? AND generation = 1 AND is_current = 1
                """,
                (workstream.workstream_id,),
            ).fetchone()
            if row is None or int(row["revision"]) != expected_revision:
                raise CASConflict("staged workstream revision changed before executor binding")
            current_contract = json.loads(row["contract_json"])
            current_executor = current_contract.get("executor")
            expected_executor = contract_to_dict(workstream.executor)
            if current_executor is not None:
                if current_executor != expected_executor:
                    raise IdempotencyConflict(
                        "staged workstream is bound to another executor"
                    )
                return self._workstream_record(
                    connection, workstream.workstream_id, 1
                )
            expected_unbound = contract_to_dict(workstream)
            expected_unbound["executor"] = None
            if current_contract != expected_unbound:
                raise CASConflict(
                    "staged workstream contract changed before executor binding"
                )
            connection.execute(
                """
                UPDATE workstreams
                SET contract_json = ?, contract_digest = ?, updated_at = ?,
                    writer_generation = ?
                WHERE workstream_id = ? AND generation = 1 AND revision = ?
                    AND is_current = 1
                """,
                (
                    contract_json,
                    _digest(contract_json),
                    self._now(),
                    fence.generation,
                    workstream.workstream_id,
                    expected_revision,
                ),
            )
            return self._workstream_record(connection, workstream.workstream_id, 1)

    def register_executor(
        self,
        task_id: str,
        workstream_id: str,
        executor: ExecutorIdentity,
        *,
        expected_current_generation: int,
        checkpoint_digest: str,
        fence: SupervisorFence,
    ) -> ExecutorBinding:
        _machine_value("checkpoint_digest", checkpoint_digest)
        with self._transaction(fence) as connection:
            current = connection.execute(
                """
                SELECT * FROM executor_bindings
                WHERE task_id = ? AND workstream_id = ? AND state = 'active'
                """,
                (task_id, workstream_id),
            ).fetchone()
            observed = 0 if current is None else int(current["executor_generation"])
            if observed != expected_current_generation:
                raise CASConflict("current executor generation changed")
            pending = connection.execute(
                "SELECT 1 FROM executor_bindings WHERE task_id = ? AND workstream_id = ? AND state = 'pending'",
                (task_id, workstream_id),
            ).fetchone()
            if pending is not None:
                raise CASConflict("a successor executor is already pending proof")
            generation = observed + 1
            state = "active" if generation == 1 else "pending"
            now = self._now()
            connection.execute(
                """
                INSERT INTO executor_bindings(
                    task_id, workstream_id, executor_generation, thread_id, host_id, model, reasoning,
                    state, predecessor_generation, checkpoint_digest, proof_event_id, created_at,
                    activated_at, writer_generation
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)
                """,
                (
                    task_id, workstream_id, generation, executor.thread_id, executor.host_id,
                    executor.model, executor.reasoning, state, observed or None, checkpoint_digest,
                    now, now if state == "active" else None, fence.generation,
                ),
            )
            return self._executor_binding(connection, task_id, workstream_id, generation)

    def activate_successor(
        self,
        task_id: str,
        workstream_id: str,
        successor_generation: int,
        *,
        proof_event_id: str,
        fence: SupervisorFence,
    ) -> ExecutorBinding:
        proof_id = _machine_value("proof_event_id", proof_event_id)
        with self._transaction(fence) as connection:
            pending = connection.execute(
                """
                SELECT * FROM executor_bindings
                WHERE task_id = ? AND workstream_id = ? AND executor_generation = ? AND state = 'pending'
                """,
                (task_id, workstream_id, successor_generation),
            ).fetchone()
            if pending is None:
                raise CASConflict("successor is missing, stale, or already activated")
            predecessor = int(pending["predecessor_generation"])
            current = connection.execute(
                """
                SELECT executor_generation FROM executor_bindings
                WHERE task_id = ? AND workstream_id = ? AND state = 'active'
                """,
                (task_id, workstream_id),
            ).fetchone()
            if current is None or int(current["executor_generation"]) != predecessor:
                raise CASConflict("predecessor changed before successor proof")
            connection.execute(
                """
                UPDATE executor_bindings SET state = 'stale', writer_generation = ?
                WHERE task_id = ? AND workstream_id = ? AND executor_generation = ? AND state = 'active'
                """,
                (fence.generation, task_id, workstream_id, predecessor),
            )
            connection.execute(
                """
                UPDATE executor_bindings
                SET state = 'active', proof_event_id = ?, activated_at = ?, writer_generation = ?
                WHERE task_id = ? AND workstream_id = ? AND executor_generation = ? AND state = 'pending'
                """,
                (proof_id, self._now(), fence.generation, task_id, workstream_id, successor_generation),
            )
            return self._executor_binding(connection, task_id, workstream_id, successor_generation)

    def complete_corrective_successor(
        self,
        *,
        task_id: str,
        workstream_id: str,
        expected_task_revision: int,
        expected_workstream_generation: int,
        expected_workstream_revision: int,
        predecessor_generation: int,
        successor_generation: int,
        successor: ExecutorIdentity,
        checkpoint_digest: str,
        proof_event_id: str,
        checkpoint_event_payload: Mapping[str, Any],
        incident_event_id: str,
        incident_event_payload: Mapping[str, Any],
        followup_event_id: str,
        followup_payload: Mapping[str, Any],
        projection_event_id: str,
        claimed_outbox_event_id: str,
        claim_token: str,
        fence: SupervisorFence,
    ) -> dict[str, Any]:
        """Atomically prove a corrective successor and reopen its workstream."""

        task = _machine_value("task_id", task_id)
        workstream = _machine_value("workstream_id", workstream_id)
        proof = _machine_value("proof_event_id", proof_event_id)
        incident_event = _machine_value("incident_event_id", incident_event_id)
        followup_event = _machine_value("followup_event_id", followup_event_id)
        projection_event = _machine_value("projection_event_id", projection_event_id)
        claimed_event = _machine_value(
            "claimed_outbox_event_id", claimed_outbox_event_id
        )
        claim = _machine_value("claim_token", claim_token)
        if successor_generation != predecessor_generation + 1:
            raise RegistryValidationError("corrective successor generation is not exact")
        now = self._now()
        with self._transaction(fence) as connection:
            claimed = connection.execute(
                """
                SELECT kind FROM outbox
                WHERE event_id = ? AND kind = 'codex_successor_start'
                    AND state = 'inflight' AND claim_token = ?
                    AND claimed_generation = ?
                """,
                (claimed_event, claim, fence.generation),
            ).fetchone()
            if claimed is None:
                raise StaleGenerationError(
                    "corrective successor completion lost its exact outbox claim"
                )
            task_row = connection.execute(
                "SELECT * FROM tasks WHERE task_id = ?", (task,)
            ).fetchone()
            workstream_row = connection.execute(
                """
                SELECT * FROM workstreams
                WHERE workstream_id = ? AND task_id = ? AND is_current = 1
                """,
                (workstream, task),
            ).fetchone()
            if (
                task_row is None
                or task_row["state"] != "recovering"
                or int(task_row["revision"]) != expected_task_revision
                or workstream_row is None
                or workstream_row["state"] != "recovering"
                or int(workstream_row["generation"])
                != expected_workstream_generation
                or int(workstream_row["revision"])
                != expected_workstream_revision
            ):
                raise CASConflict(
                    "corrective successor proof lost its recovering revision binding"
                )
            active = connection.execute(
                """
                SELECT * FROM executor_bindings
                WHERE task_id = ? AND workstream_id = ? AND state = 'active'
                """,
                (task, workstream),
            ).fetchone()
            if (
                active is None
                or int(active["executor_generation"]) != predecessor_generation
            ):
                raise CASConflict(
                    "corrective predecessor changed before successor proof"
                )
            pending = connection.execute(
                """
                SELECT * FROM executor_bindings
                WHERE task_id = ? AND workstream_id = ? AND state = 'pending'
                """,
                (task, workstream),
            ).fetchone()
            identity_tuple = (
                successor.thread_id,
                successor.host_id,
                successor.model,
                successor.reasoning,
            )
            if pending is None:
                connection.execute(
                    """
                    INSERT INTO executor_bindings(
                        task_id, workstream_id, executor_generation, thread_id,
                        host_id, model, reasoning, state, predecessor_generation,
                        checkpoint_digest, proof_event_id, created_at,
                        activated_at, writer_generation
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, NULL, ?, NULL, ?)
                    """,
                    (
                        task,
                        workstream,
                        successor_generation,
                        *identity_tuple,
                        predecessor_generation,
                        checkpoint_digest,
                        now,
                        fence.generation,
                    ),
                )
            elif (
                int(pending["executor_generation"]) != successor_generation
                or (
                    pending["thread_id"],
                    pending["host_id"],
                    pending["model"],
                    pending["reasoning"],
                )
                != identity_tuple
            ):
                raise CASConflict("pending corrective successor identity changed")

            connection.execute(
                """
                UPDATE executor_bindings
                SET state = 'stale', writer_generation = ?
                WHERE task_id = ? AND workstream_id = ?
                    AND executor_generation = ? AND state = 'active'
                """,
                (fence.generation, task, workstream, predecessor_generation),
            )
            activated = connection.execute(
                """
                UPDATE executor_bindings
                SET state = 'active', proof_event_id = ?, activated_at = ?,
                    writer_generation = ?
                WHERE task_id = ? AND workstream_id = ?
                    AND executor_generation = ? AND state = 'pending'
                """,
                (
                    proof,
                    now,
                    fence.generation,
                    task,
                    workstream,
                    successor_generation,
                ),
            )
            if activated.rowcount != 1:
                raise CASConflict("corrective successor could not be activated")

            next_task_revision = expected_task_revision + 1
            passport = json.loads(task_row["passport_json"])
            passport["revision"] = next_task_revision
            passport_json = _canonical_json(passport)
            connection.execute(
                """
                UPDATE tasks
                SET revision = ?, state = 'active', passport_json = ?,
                    passport_digest = ?, updated_at = ?, writer_generation = ?
                WHERE task_id = ? AND revision = ? AND state = 'recovering'
                """,
                (
                    next_task_revision,
                    passport_json,
                    _digest(passport_json),
                    now,
                    fence.generation,
                    task,
                    expected_task_revision,
                ),
            )
            next_workstream_revision = expected_workstream_revision + 1
            workstream_contract = json.loads(workstream_row["contract_json"])
            workstream_contract.update(
                {
                    "revision": next_workstream_revision,
                    "state": "working",
                    "executor": contract_to_dict(successor),
                }
            )
            workstream_json = _canonical_json(workstream_contract)
            connection.execute(
                """
                UPDATE workstreams
                SET revision = ?, state = 'working', contract_json = ?,
                    contract_digest = ?, updated_at = ?, writer_generation = ?
                WHERE workstream_id = ? AND generation = ? AND revision = ?
                    AND is_current = 1 AND state = 'recovering'
                """,
                (
                    next_workstream_revision,
                    workstream_json,
                    _digest(workstream_json),
                    now,
                    fence.generation,
                    workstream,
                    expected_workstream_generation,
                    expected_workstream_revision,
                ),
            )
            checkpoint_json = _canonical_json(checkpoint_event_payload)
            self._append_event_tx(
                connection,
                proof,
                "checkpoint",
                checkpoint_json,
                _digest(checkpoint_json),
                fence,
                task_id=task,
                workstream_id=workstream,
                executor_generation=successor_generation,
                now=now,
            )
            incident_json = _canonical_json(incident_event_payload)
            self._append_event_tx(
                connection,
                incident_event,
                "incident_policy",
                incident_json,
                _digest(incident_json),
                fence,
                task_id=task,
                workstream_id=workstream,
                executor_generation=successor_generation,
                now=now,
            )
            self._enqueue_outbox_tx(
                connection,
                followup_event,
                "codex_followup",
                followup_payload,
                fence,
                task_id=task,
                coalescible=False,
                coalesce_key=None,
                now=now,
            )
            self._enqueue_outbox_tx(
                connection,
                projection_event,
                "projection_dirty",
                {"trigger_event_id": incident_event},
                fence,
                task_id=task,
                coalescible=True,
                coalesce_key="global-projection",
                now=now,
            )
            delivered = connection.execute(
                """
                UPDATE outbox
                SET state = 'delivered', delivered_at = ?, claim_token = NULL,
                    claimed_by = NULL, claimed_until = NULL, updated_at = ?,
                    writer_generation = ?
                WHERE event_id = ? AND state = 'inflight' AND claim_token = ?
                    AND claimed_generation = ?
                """,
                (
                    now,
                    now,
                    fence.generation,
                    claimed_event,
                    claim,
                    fence.generation,
                ),
            )
            if delivered.rowcount != 1:
                raise StaleGenerationError(
                    "corrective successor completion could not receipt its outbox"
                )
            return {
                "task_revision": next_task_revision,
                "workstream_revision": next_workstream_revision,
                "executor_generation": successor_generation,
                "proof_event_id": proof,
            }

    def current_executor(self, task_id: str, workstream_id: str) -> ExecutorBinding | None:
        with self._reader() as connection:
            row = connection.execute(
                "SELECT * FROM executor_bindings WHERE task_id = ? AND workstream_id = ? AND state = 'active'",
                (task_id, workstream_id),
            ).fetchone()
        return _executor_from_row(row) if row is not None else None

    def append_event(
        self,
        event_id: str,
        event_type: str,
        payload: Mapping[str, Any],
        fence: SupervisorFence,
        *,
        task_id: str | None = None,
        workstream_id: str | None = None,
        executor_generation: int | None = None,
    ) -> bool:
        event = _machine_value("event_id", event_id)
        event_kind = _machine_value("event_type", event_type)
        payload_json = _canonical_json(payload)
        digest = _digest(payload_json)
        with self._transaction(fence) as connection:
            return self._append_event_tx(
                connection,
                event,
                event_kind,
                payload_json,
                digest,
                fence,
                task_id=task_id,
                workstream_id=workstream_id,
                executor_generation=executor_generation,
            )

    def record_input_event_outbox(
        self,
        *,
        message_id: str,
        source: str,
        input_payload: Mapping[str, Any],
        event_id: str,
        event_type: str,
        event_payload: Mapping[str, Any],
        outbox_items: Sequence[Mapping[str, Any]],
        fence: SupervisorFence,
        task_id: str | None = None,
        workstream_id: str | None = None,
        executor_generation: int | None = None,
    ) -> bool:
        """Atomically persist one durable input, typed event and all resulting messages."""

        message = _machine_value("message_id", message_id)
        source_name = _machine_value("source", source)
        input_json = _canonical_json(input_payload)
        input_digest = _digest(input_json)
        event = _machine_value("event_id", event_id)
        event_kind = _machine_value("event_type", event_type)
        event_json = _canonical_json(event_payload)
        event_digest = _digest(event_json)
        now = self._now()
        with self._transaction(fence) as connection:
            existing = connection.execute("SELECT * FROM inbox WHERE message_id = ?", (message,)).fetchone()
            if existing is not None:
                if existing["payload_digest"] != input_digest or existing["source"] != source_name:
                    raise IdempotencyConflict("inbox message_id was reused for different content")
                return False
            connection.execute(
                """
                INSERT INTO inbox(message_id, source, payload_json, payload_digest, state, writer_generation, received_at)
                VALUES (?, ?, ?, ?, 'received', ?, ?)
                """,
                (message, source_name, input_json, input_digest, fence.generation, now),
            )
            self._append_event_tx(
                connection,
                event,
                event_kind,
                event_json,
                event_digest,
                fence,
                task_id=task_id,
                workstream_id=workstream_id,
                executor_generation=executor_generation,
                now=now,
            )
            allowed_keys = {"event_id", "kind", "payload", "task_id", "coalescible", "coalesce_key"}
            for item in outbox_items:
                if not isinstance(item, Mapping) or set(item) != allowed_keys:
                    raise RegistryValidationError("outbox item fields are invalid")
                payload = item["payload"]
                if not isinstance(payload, Mapping):
                    raise RegistryValidationError("outbox item payload must be an object")
                if not isinstance(item["coalescible"], bool):
                    raise RegistryValidationError("outbox item coalescible must be a boolean")
                self._enqueue_outbox_tx(
                    connection,
                    str(item["event_id"]),
                    str(item["kind"]),
                    payload,
                    fence,
                    task_id=str(item["task_id"]) if item["task_id"] is not None else None,
                    coalescible=item["coalescible"],
                    coalesce_key=str(item["coalesce_key"]) if item["coalesce_key"] is not None else None,
                    now=now,
                )
            connection.execute(
                "UPDATE inbox SET state = 'processed', processed_at = ? WHERE message_id = ?",
                (now, message),
            )
            return True

    def _append_event_tx(
        self,
        connection: sqlite3.Connection,
        event_id: str,
        event_type: str,
        payload_json: str,
        payload_digest: str,
        fence: SupervisorFence,
        *,
        task_id: str | None,
        workstream_id: str | None,
        executor_generation: int | None,
        now: float | None = None,
    ) -> bool:
        if executor_generation is not None:
            active = connection.execute(
                """
                SELECT executor_generation FROM executor_bindings
                WHERE task_id = ? AND workstream_id = ? AND state = 'active'
                """,
                (task_id, workstream_id),
            ).fetchone()
            if active is None or int(active["executor_generation"]) != executor_generation:
                raise StaleGenerationError("late executor event rejected by current executor generation")
        existing = connection.execute("SELECT * FROM events WHERE event_id = ?", (event_id,)).fetchone()
        if existing is not None:
            if existing["payload_digest"] == payload_digest and existing["event_type"] == event_type:
                return False
            raise IdempotencyConflict("event_id was reused for different content")
        connection.execute(
            """
            INSERT INTO events(
                event_id, task_id, workstream_id, event_type, payload_json, payload_digest,
                executor_generation, writer_generation, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id, task_id, workstream_id, event_type, payload_json, payload_digest,
                executor_generation, fence.generation, self._now(now),
            ),
        )
        return True

    def get_event(self, event_id: str) -> dict[str, Any] | None:
        with self._reader() as connection:
            row = connection.execute("SELECT * FROM events WHERE event_id = ?", (event_id,)).fetchone()
        return _event_from_row(row) if row is not None else None

    def list_events(
        self,
        *,
        task_id: str | None = None,
        workstream_id: str | None = None,
        event_types: Sequence[str] | None = None,
    ) -> tuple[dict[str, Any], ...]:
        clauses: list[str] = []
        parameters: list[Any] = []
        if task_id is not None:
            clauses.append("task_id = ?")
            parameters.append(task_id)
        if workstream_id is not None:
            clauses.append("workstream_id = ?")
            parameters.append(workstream_id)
        normalized_types = tuple(sorted({_machine_value("event_type", item) for item in (event_types or ())}))
        if normalized_types:
            placeholders = ",".join("?" for _ in normalized_types)
            clauses.append(f"event_type IN ({placeholders})")
            parameters.extend(normalized_types)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self._reader() as connection:
            rows = connection.execute(
                f"SELECT * FROM events{where} ORDER BY created_at, event_id", parameters
            ).fetchall()
        return tuple(_event_from_row(row) for row in rows)

    def reserve_initial_executor_start(
        self,
        passport: TaskPassport,
        workstream: Workstream,
        *,
        canonical_workspace: str,
        message_id: str,
        source: str,
        inbox_payload: Mapping[str, Any],
        outbox_event_id: str,
        outbox_payload: Mapping[str, Any],
        fence: SupervisorFence,
    ) -> bool:
        """Atomically stage a visible unbound task and its first start intent."""

        if (
            passport.revision != 1
            or workstream.revision != 1
            or workstream.generation != 1
            or passport.executor is not None
            or workstream.executor is not None
        ):
            raise RegistryValidationError(
                "initial executor start requires unbound revision/generation one contracts"
            )
        validate_workstream_against_passport(workstream, passport)
        message = _machine_value("message_id", message_id)
        source_name = _machine_value("source", source)
        event = _machine_value("outbox_event_id", outbox_event_id)
        inbox_json = _canonical_json(inbox_payload)
        inbox_digest = _digest(inbox_json)
        passport_json = canonical_contract_json(passport)
        workstream_json = canonical_contract_json(workstream)
        now = self._now()
        with self._transaction(fence) as connection:
            existing_inbox = connection.execute(
                "SELECT * FROM inbox WHERE message_id = ?", (message,)
            ).fetchone()
            if existing_inbox is not None:
                if (
                    existing_inbox["payload_digest"] != inbox_digest
                    or existing_inbox["source"] != source_name
                ):
                    raise IdempotencyConflict("initial start message_id was reused")
                return False
            if connection.execute(
                "SELECT 1 FROM tasks WHERE task_id = ?", (passport.task_id,)
            ).fetchone() is not None:
                raise IdempotencyConflict(
                    "task already exists; unbound restart requires typed reconciliation"
                )
            if connection.execute(
                "SELECT 1 FROM workstreams WHERE workstream_id = ?",
                (workstream.workstream_id,),
            ).fetchone() is not None:
                raise IdempotencyConflict("workstream already exists under another task")
            connection.execute(
                """
                INSERT INTO tasks(
                    task_id,revision,state,passport_json,passport_digest,
                    created_at,updated_at,writer_generation
                ) VALUES (?,1,'active',?,?,?,?,?)
                """,
                (
                    passport.task_id,
                    passport_json,
                    _digest(passport_json),
                    now,
                    now,
                    fence.generation,
                ),
            )
            connection.execute(
                """
                INSERT INTO workstreams(
                    workstream_id,generation,task_id,revision,state,
                    contract_json,contract_digest,is_current,created_at,
                    updated_at,writer_generation
                ) VALUES (?,1,?,1,?,?,?,1,?,?,?)
                """,
                (
                    workstream.workstream_id,
                    passport.task_id,
                    workstream.state,
                    workstream_json,
                    _digest(workstream_json),
                    now,
                    now,
                    fence.generation,
                ),
            )
            self._bind_workspace_tx(
                connection,
                passport.task_id,
                workstream.workstream_id,
                canonical_workspace,
                fence,
                now=now,
            )
            connection.execute(
                """
                INSERT INTO inbox(
                    message_id,source,payload_json,payload_digest,state,
                    writer_generation,received_at,processed_at
                ) VALUES (?,?,?,?,'processed',?,?,?)
                """,
                (
                    message,
                    source_name,
                    inbox_json,
                    inbox_digest,
                    fence.generation,
                    now,
                    now,
                ),
            )
            self._enqueue_outbox_tx(
                connection,
                event,
                "codex_thread_start",
                outbox_payload,
                fence,
                task_id=passport.task_id,
                coalescible=False,
                coalesce_key=None,
                now=now,
            )
            return True

    def reconcile_unbound_executor_start(
        self,
        replacement_passport: TaskPassport,
        replacement_workstream: Workstream,
        *,
        expected_task_revision: int,
        expected_workstream_revision: int,
        failed_event_id: str,
        failed_event_digest: str,
        strategy_digest: str,
        canonical_workspace: str,
        message_id: str,
        source: str,
        input_payload: Mapping[str, Any],
        reconciliation_event_id: str,
        reconciliation_payload: Mapping[str, Any],
        start_event_id: str,
        start_payload: Mapping[str, Any],
        projection_event_id: str,
        fence: SupervisorFence,
    ) -> dict[str, Any]:
        """Abandon one parked unbound intent and reserve exactly one replacement."""

        if (
            replacement_passport.revision != expected_task_revision + 1
            or replacement_passport.executor is not None
            or replacement_workstream.generation != 1
            or replacement_workstream.revision != expected_workstream_revision + 1
            or replacement_workstream.executor is not None
            or replacement_workstream.state != "started"
        ):
            raise RegistryValidationError(
                "unbound reconciliation contracts have stale revisions or state"
            )
        validate_workstream_against_passport(
            replacement_workstream, replacement_passport
        )
        task_id = replacement_passport.task_id
        workstream_id = replacement_workstream.workstream_id
        message = _machine_value("message_id", message_id)
        source_name = _machine_value("source", source)
        failed_event = _machine_value("failed_event_id", failed_event_id)
        reconciliation_event = _machine_value(
            "reconciliation_event_id", reconciliation_event_id
        )
        start_event = _machine_value("start_event_id", start_event_id)
        projection_event = _machine_value("projection_event_id", projection_event_id)
        for label, value in (
            ("failed_event_digest", failed_event_digest),
            ("strategy_digest", strategy_digest),
        ):
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(character not in "0123456789abcdef" for character in value)
            ):
                raise RegistryValidationError(f"{label} must be sha256")
        inbox_json = _canonical_json(input_payload)
        inbox_digest = _digest(inbox_json)
        passport_json = canonical_contract_json(replacement_passport)
        workstream_json = canonical_contract_json(replacement_workstream)
        now = self._now()
        with self._transaction(fence) as connection:
            existing_inbox = connection.execute(
                "SELECT * FROM inbox WHERE message_id = ?", (message,)
            ).fetchone()
            if existing_inbox is not None:
                if (
                    existing_inbox["payload_digest"] != inbox_digest
                    or existing_inbox["source"] != source_name
                ):
                    raise IdempotencyConflict(
                        "unbound reconciliation message_id was reused"
                    )
                return {
                    "created": False,
                    "task_id": task_id,
                    "workstream_id": workstream_id,
                    "start_event_id": start_event,
                    "reconciliation_event_id": reconciliation_event,
                }
            task = connection.execute(
                "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
            workstream = connection.execute(
                """
                SELECT * FROM workstreams
                WHERE workstream_id = ? AND task_id = ? AND generation = 1
                    AND is_current = 1
                """,
                (workstream_id, task_id),
            ).fetchone()
            if (
                task is None
                or task["state"] != "parked"
                or int(task["revision"]) != expected_task_revision
                or workstream is None
                or workstream["state"] != "blocked"
                or int(workstream["revision"]) != expected_workstream_revision
            ):
                raise CASConflict(
                    "unbound reconciliation requires the exact parked bootstrap binding"
                )
            if connection.execute(
                """
                SELECT 1 FROM executor_bindings
                WHERE task_id = ? AND workstream_id = ?
                    AND state IN ('active','pending')
                """,
                (task_id, workstream_id),
            ).fetchone() is not None:
                raise CASConflict(
                    "unbound reconciliation is forbidden after an executor identity exists"
                )
            workspace = connection.execute(
                """
                SELECT canonical_path FROM workspace_bindings
                WHERE task_id = ? AND workstream_id = ?
                """,
                (task_id, workstream_id),
            ).fetchone()
            if workspace is None or workspace["canonical_path"] != canonical_workspace:
                raise CASConflict("unbound reconciliation workspace changed")
            failures = connection.execute(
                """
                SELECT * FROM events
                WHERE task_id = ? AND workstream_id = ?
                    AND event_type = 'incident_policy'
                ORDER BY created_at,event_id
                """,
                (task_id, workstream_id),
            ).fetchall()
            parked_failures = [
                row
                for row in failures
                if json.loads(row["payload_json"]).get("status")
                == "parked_fail_closed"
                and json.loads(row["payload_json"]).get("schema")
                == "dev-control-plane/unbound-start-failure/v2"
            ]
            if not parked_failures or parked_failures[-1]["event_id"] != failed_event:
                raise CASConflict(
                    "unbound reconciliation failure is not the latest parked intent"
                )
            failed_row = parked_failures[-1]
            if failed_row["payload_digest"] != failed_event_digest:
                raise CASConflict("unbound reconciliation failure digest changed")
            failed_payload = json.loads(failed_row["payload_json"])
            if any(
                json.loads(row["payload_json"]).get("failed_event_id")
                == failed_event
                for row in failures
            ):
                raise IdempotencyConflict(
                    "unbound failure was already reconciled"
                )
            old_start_event = str(failed_payload.get("start_event_id") or "")
            old_start = connection.execute(
                "SELECT state FROM outbox WHERE event_id = ? AND kind = 'codex_thread_start'",
                (old_start_event,),
            ).fetchone()
            if old_start is None or old_start["state"] != "delivered":
                raise LockConflict(
                    "old unbound start intent is not durably abandoned"
                )
            if connection.execute(
                """
                SELECT 1 FROM outbox
                WHERE task_id = ? AND kind = 'codex_thread_start'
                    AND state IN ('pending','inflight')
                """,
                (task_id,),
            ).fetchone() is not None:
                raise LockConflict(
                    "an unbound replacement start is already pending"
                )
            old_passport = json.loads(task["passport_json"])
            new_passport = contract_to_dict(replacement_passport)
            for item in (old_passport, new_passport):
                for cosmetic in ("revision", "title", "created_at", "executor"):
                    item.pop(cosmetic, None)
            if (
                old_passport == new_passport
                and strategy_digest == failed_payload.get("strategy_digest")
            ):
                raise RegistryValidationError(
                    "unbound reconciliation requires a material Passport or strategy change"
                )
            attention_event_id = _machine_value(
                "attention_event_id", failed_payload.get("attention_event_id")
            )
            attention = connection.execute(
                "SELECT state FROM outbox WHERE event_id = ? AND kind = 'curator_attention'",
                (attention_event_id,),
            ).fetchone()
            if attention is None:
                raise CASConflict("unbound reconciliation attention disappeared")
            if attention["state"] == "inflight":
                raise LockConflict(
                    "unbound reconciliation cannot revoke inflight curator delivery"
                )
            if attention["state"] == "pending":
                connection.execute(
                    """
                    UPDATE outbox SET state = 'superseded', updated_at = ?,
                        writer_generation = ?
                    WHERE event_id = ? AND state = 'pending'
                    """,
                    (now, fence.generation, attention_event_id),
                )
            connection.execute(
                """
                INSERT INTO inbox(
                    message_id,source,payload_json,payload_digest,state,
                    writer_generation,received_at
                ) VALUES (?,?,?,?,'received',?,?)
                """,
                (
                    message,
                    source_name,
                    inbox_json,
                    inbox_digest,
                    fence.generation,
                    now,
                ),
            )
            connection.execute(
                """
                UPDATE tasks
                SET revision = ?,state = 'active',passport_json = ?,
                    passport_digest = ?,updated_at = ?,writer_generation = ?
                WHERE task_id = ? AND revision = ? AND state = 'parked'
                """,
                (
                    replacement_passport.revision,
                    passport_json,
                    _digest(passport_json),
                    now,
                    fence.generation,
                    task_id,
                    expected_task_revision,
                ),
            )
            connection.execute(
                """
                UPDATE workstreams
                SET revision = ?,state = 'started',contract_json = ?,
                    contract_digest = ?,updated_at = ?,writer_generation = ?
                WHERE workstream_id = ? AND generation = 1 AND revision = ?
                    AND is_current = 1 AND state = 'blocked'
                """,
                (
                    replacement_workstream.revision,
                    workstream_json,
                    _digest(workstream_json),
                    now,
                    fence.generation,
                    workstream_id,
                    expected_workstream_revision,
                ),
            )
            durable_reconciliation = {
                **dict(reconciliation_payload),
                "failed_event_id": failed_event,
                "failed_event_digest": failed_event_digest,
                "resolved_attention_event_id": attention_event_id,
                "start_event_id": start_event,
                "strategy_digest": strategy_digest,
            }
            reconciliation_json = _canonical_json(durable_reconciliation)
            self._append_event_tx(
                connection,
                reconciliation_event,
                "unbound_start_reconciled",
                reconciliation_json,
                _digest(reconciliation_json),
                fence,
                task_id=task_id,
                workstream_id=workstream_id,
                executor_generation=None,
                now=now,
            )
            self._enqueue_outbox_tx(
                connection,
                start_event,
                "codex_thread_start",
                start_payload,
                fence,
                task_id=task_id,
                coalescible=False,
                coalesce_key=None,
                now=now,
            )
            self._enqueue_outbox_tx(
                connection,
                projection_event,
                "projection_dirty",
                {"trigger_event_id": reconciliation_event},
                fence,
                task_id=task_id,
                coalescible=True,
                coalesce_key="global-projection",
                now=now,
            )
            connection.execute(
                "UPDATE inbox SET state = 'processed',processed_at = ? WHERE message_id = ?",
                (now, message),
            )
            return {
                "created": True,
                "task_id": task_id,
                "workstream_id": workstream_id,
                "start_event_id": start_event,
                "reconciliation_event_id": reconciliation_event,
            }

    def accept_inbox_and_enqueue(
        self,
        *,
        message_id: str,
        source: str,
        inbox_payload: Mapping[str, Any],
        outbox_event_id: str,
        outbox_kind: str,
        outbox_payload: Mapping[str, Any],
        fence: SupervisorFence,
        task_id: str | None = None,
        coalescible: bool = False,
        coalesce_key: str | None = None,
        workspace_binding: tuple[str, str, str] | None = None,
    ) -> bool:
        message = _machine_value("message_id", message_id)
        source_name = _machine_value("source", source)
        inbox_json = _canonical_json(inbox_payload)
        inbox_digest = _digest(inbox_json)
        with self._transaction(fence) as connection:
            existing = connection.execute("SELECT * FROM inbox WHERE message_id = ?", (message,)).fetchone()
            if existing is not None:
                if existing["payload_digest"] != inbox_digest or existing["source"] != source_name:
                    raise IdempotencyConflict("inbox message_id was reused for different content")
                if workspace_binding is not None:
                    task, workstream, path = workspace_binding
                    self._bind_workspace_tx(
                        connection,
                        _machine_value("task_id", task),
                        _machine_value("workstream_id", workstream),
                        path,
                        fence,
                        now=self._now(),
                    )
                return False
            now = self._now()
            if workspace_binding is not None:
                task, workstream, path = workspace_binding
                self._bind_workspace_tx(
                    connection,
                    _machine_value("task_id", task),
                    _machine_value("workstream_id", workstream),
                    path,
                    fence,
                    now=now,
                )
            connection.execute(
                """
                INSERT INTO inbox(message_id, source, payload_json, payload_digest, state, writer_generation, received_at)
                VALUES (?, ?, ?, ?, 'received', ?, ?)
                """,
                (message, source_name, inbox_json, inbox_digest, fence.generation, now),
            )
            self._enqueue_outbox_tx(
                connection, outbox_event_id, outbox_kind, outbox_payload, fence,
                task_id=task_id, coalescible=coalescible, coalesce_key=coalesce_key, now=now,
            )
            connection.execute(
                "UPDATE inbox SET state = 'processed', processed_at = ? WHERE message_id = ?",
                (now, message),
            )
            return True

    def enqueue_outbox(
        self,
        event_id: str,
        kind: str,
        payload: Mapping[str, Any],
        fence: SupervisorFence,
        *,
        task_id: str | None = None,
        coalescible: bool = False,
        coalesce_key: str | None = None,
        available_at: float | None = None,
    ) -> bool:
        with self._transaction(fence) as connection:
            return self._enqueue_outbox_tx(
                connection, event_id, kind, payload, fence, task_id=task_id,
                coalescible=coalescible, coalesce_key=coalesce_key,
                now=self._now(), available_at=available_at,
            )

    def reserve_projection_snapshot(
        self,
        *,
        supervisor_id: str,
        projection: Mapping[str, Any],
        event_id: str,
        idempotency_key: str,
        fence: SupervisorFence,
    ) -> dict[str, int]:
        """Allocate monotonic transport coordinates and enqueue one full snapshot atomically."""

        supervisor = _machine_value("supervisor_id", supervisor_id)
        event = _machine_value("event_id", event_id)
        idempotency = _machine_value("idempotency_key", idempotency_key)
        with self._transaction(fence) as connection:
            existing = connection.execute("SELECT payload_json FROM outbox WHERE event_id = ?", (event,)).fetchone()
            if existing is not None:
                payload = json.loads(existing["payload_json"])
                return {
                    "generation": int(payload["generation"]),
                    "sequence": int(payload["sequence"]),
                    "revision": int(payload["revision"]),
                }
            transport = connection.execute(
                "SELECT generation, sequence, revision FROM projection_transport_state WHERE singleton = 1"
            ).fetchone()
            if transport is None:
                raise RegistryError("projection transport state row is missing")
            transport_generation = int(transport["generation"])
            if transport_generation > fence.generation:
                raise StaleGenerationError("projection transport state belongs to a newer generation")
            sequence = int(transport["sequence"]) + 1 if transport_generation == fence.generation else 1
            revision = int(transport["revision"]) + 1
            now = self._now()
            connection.execute(
                """
                UPDATE projection_transport_state
                SET generation = ?, sequence = ?, revision = ?, updated_at = ?
                WHERE singleton = 1
                """,
                (fence.generation, sequence, revision, now),
            )
            envelope = {
                "contract": "dev_control_plane_projection_v2",
                "supervisor_id": supervisor,
                "generation": fence.generation,
                "sequence": sequence,
                "revision": revision,
                "event_id": event,
                "idempotency_key": idempotency,
                "timestamp": max(1, int(now)),
                "projection": projection,
            }
            self._enqueue_outbox_tx(
                connection,
                event,
                "projection_snapshot",
                envelope,
                fence,
                task_id=None,
                coalescible=False,
                coalesce_key=None,
                now=now,
            )
            return {"generation": fence.generation, "sequence": sequence, "revision": revision}

    def projection_transport_state(self) -> dict[str, int]:
        """Return sanitized durable coordinates, independent of retained outbox rows."""

        with self._reader() as connection:
            row = connection.execute(
                "SELECT generation, sequence, revision FROM projection_transport_state WHERE singleton = 1"
            ).fetchone()
        if row is None:
            raise RegistryError("projection transport state row is missing")
        return {
            "generation": int(row["generation"]),
            "sequence": int(row["sequence"]),
            "revision": int(row["revision"]),
        }

    def _enqueue_outbox_tx(
        self,
        connection: sqlite3.Connection,
        event_id: str,
        kind: str,
        payload: Mapping[str, Any],
        fence: SupervisorFence,
        *,
        task_id: str | None,
        coalescible: bool,
        coalesce_key: str | None,
        now: float,
        available_at: float | None = None,
    ) -> bool:
        event = _machine_value("outbox.event_id", event_id)
        event_kind = _machine_value("outbox.kind", kind)
        if event_kind in NON_COALESCIBLE_OUTBOX_KINDS and coalescible:
            raise RegistryValidationError(f"{event_kind} outbox events must never coalesce")
        if coalescible and not coalesce_key:
            raise RegistryValidationError("coalescible outbox events require a coalesce_key")
        if coalesce_key is not None:
            _machine_value("outbox.coalesce_key", coalesce_key)
        payload_json = _canonical_json(payload)
        digest = _digest(payload_json)
        existing = connection.execute("SELECT * FROM outbox WHERE event_id = ?", (event,)).fetchone()
        if existing is not None:
            if existing["payload_digest"] == digest and existing["kind"] == event_kind:
                return False
            raise IdempotencyConflict("outbox event_id was reused for different content")
        if coalescible:
            connection.execute(
                """
                UPDATE outbox
                SET state = 'superseded', updated_at = ?, writer_generation = ?
                WHERE kind = ? AND coalesce_key = ? AND state = 'pending'
                """,
                (now, fence.generation, event_kind, coalesce_key),
            )
        connection.execute(
            """
            INSERT INTO outbox(
                event_id, kind, payload_json, payload_digest, task_id, coalescible, coalesce_key,
                state, attempts, available_at, writer_generation, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', 0, ?, ?, ?, ?)
            """,
            (
                event, event_kind, payload_json, digest, task_id, int(coalescible), coalesce_key,
                now if available_at is None else float(available_at), fence.generation, now, now,
            ),
        )
        return True

    def replace_claimed_outbox_payload(
        self,
        event_id: str,
        claim_token: str,
        payload: Mapping[str, Any],
        fence: SupervisorFence,
    ) -> OutboxMessage:
        """CAS-replace a claimed payload before/after a bounded external call.

        The exact claim token, inflight state and Supervisor generation are the
        fence.  A later bounded retry may need to persist a fresh call intent or
        an immutable provider receipt, so the operation must not be restricted
        to attempt one.
        """

        payload_json = _canonical_json(payload)
        with self._transaction(fence) as connection:
            cursor = connection.execute(
                """
                UPDATE outbox
                SET payload_json = ?, payload_digest = ?, updated_at = ?, writer_generation = ?
                WHERE event_id = ? AND state = 'inflight' AND claim_token = ?
                    AND claimed_generation = ?
                """,
                (
                    payload_json, _digest(payload_json), self._now(), fence.generation,
                    event_id, claim_token, fence.generation,
                ),
            )
            if cursor.rowcount != 1:
                raise StaleGenerationError("claimed outbox payload cannot be rematerialized")
            row = connection.execute("SELECT * FROM outbox WHERE event_id = ?", (event_id,)).fetchone()
            if row is None:
                raise RegistryError("claimed outbox row disappeared")
            return _outbox_from_row(row)

    def list_outbox_summaries(
        self,
        *,
        kinds: Sequence[str] | None = None,
        states: Sequence[str] | None = None,
    ) -> tuple[dict[str, Any], ...]:
        clauses: list[str] = []
        parameters: list[Any] = []
        normalized_kinds = tuple(sorted({_machine_value("outbox.kind", item) for item in (kinds or ())}))
        normalized_states = tuple(sorted(set(states or ())))
        unknown_states = set(normalized_states) - OUTBOX_STATES
        if unknown_states:
            raise RegistryValidationError(f"unknown outbox states: {sorted(unknown_states)}")
        for column, values in (("kind", normalized_kinds), ("state", normalized_states)):
            if values:
                placeholders = ",".join("?" for _ in values)
                clauses.append(f"{column} IN ({placeholders})")
                parameters.extend(values)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self._reader() as connection:
            rows = connection.execute(
                f"SELECT event_id,kind,task_id,state,attempts,writer_generation,created_at,updated_at "
                f"FROM outbox{where} ORDER BY created_at,event_id",
                parameters,
            ).fetchall()
        return tuple(dict(row) for row in rows)

    def list_outbox_records(
        self,
        *,
        kinds: Sequence[str] | None = None,
        states: Sequence[str] | None = None,
    ) -> tuple[dict[str, Any], ...]:
        """Read decoded durable payloads for internal deterministic folding.

        Claim tokens/provider data are intentionally absent.  Callers must
        sanitize any projection they derive; this is not a public API surface.
        """

        clauses: list[str] = []
        parameters: list[Any] = []
        normalized_kinds = tuple(sorted({_machine_value("outbox.kind", item) for item in (kinds or ())}))
        normalized_states = tuple(sorted(set(states or ())))
        unknown_states = set(normalized_states) - OUTBOX_STATES
        if unknown_states:
            raise RegistryValidationError(f"unknown outbox states: {sorted(unknown_states)}")
        for column, values in (("kind", normalized_kinds), ("state", normalized_states)):
            if values:
                placeholders = ",".join("?" for _ in values)
                clauses.append(f"{column} IN ({placeholders})")
                parameters.extend(values)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self._reader() as connection:
            rows = connection.execute(
                f"SELECT event_id,kind,payload_json,payload_digest,task_id,state,attempts,coalescible,"
                f"writer_generation,created_at,updated_at FROM outbox{where} "
                f"ORDER BY created_at,event_id",
                parameters,
            ).fetchall()
        return tuple(
            {
                "event_id": row["event_id"],
                "kind": row["kind"],
                "payload": json.loads(row["payload_json"]),
                "payload_digest": row["payload_digest"],
                "task_id": row["task_id"],
                "state": row["state"],
                "attempts": int(row["attempts"]),
                "coalescible": bool(row["coalescible"]),
                "writer_generation": int(row["writer_generation"]),
                "created_at": float(row["created_at"]),
                "updated_at": float(row["updated_at"]),
            }
            for row in rows
        )

    def supersede_stale_projection_snapshots(self, fence: SupervisorFence) -> int:
        """Fence out unsent snapshots from older process generations on restart."""

        with self._transaction(fence) as connection:
            cursor = connection.execute(
                """
                UPDATE outbox
                SET state = 'superseded', claim_token = NULL, claimed_by = NULL,
                    claimed_generation = NULL, claimed_until = NULL,
                    updated_at = ?
                WHERE kind = 'projection_snapshot' AND state IN ('pending', 'inflight')
                    AND writer_generation < ?
                """,
                (self._now(), fence.generation),
            )
            return cursor.rowcount

    def claim_outbox(
        self,
        fence: SupervisorFence,
        *,
        worker_id: str,
        limit: int = 50,
        visibility_timeout: float = 30.0,
        now: float | None = None,
        kinds: Sequence[str] | None = None,
    ) -> tuple[OutboxMessage, ...]:
        worker = _machine_value("worker_id", worker_id)
        if not 1 <= limit <= 500 or visibility_timeout <= 0:
            raise RegistryValidationError("invalid outbox claim bounds")
        observed_now = self._now(now)
        claim_token = secrets.token_urlsafe(24)
        normalized_kinds = tuple(sorted({_machine_value("outbox.kind", item) for item in (kinds or ())}))
        with self._transaction(fence) as connection:
            connection.execute(
                """
                UPDATE outbox
                SET state = 'pending', claim_token = NULL, claimed_by = NULL, claimed_generation = NULL,
                    claimed_until = NULL, updated_at = ?
                WHERE state = 'inflight' AND claimed_until <= ?
                    AND kind != 'curator_attention'
                """,
                (observed_now, observed_now),
            )
            if normalized_kinds:
                kind_placeholders = ",".join("?" for _ in normalized_kinds)
                rows = connection.execute(
                    f"""
                    SELECT event_id FROM outbox
                    WHERE state = 'pending' AND available_at <= ? AND kind IN ({kind_placeholders})
                    ORDER BY created_at, event_id LIMIT ?
                    """,
                    (observed_now, *normalized_kinds, limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT event_id FROM outbox
                    WHERE state = 'pending' AND available_at <= ?
                    ORDER BY created_at, event_id LIMIT ?
                    """,
                    (observed_now, limit),
                ).fetchall()
            event_ids = [row["event_id"] for row in rows]
            if not event_ids:
                return ()
            placeholders = ",".join("?" for _ in event_ids)
            connection.execute(
                f"""
                UPDATE outbox
                SET state = 'inflight', attempts = attempts + 1, claim_token = ?, claimed_by = ?,
                    claimed_generation = ?, claimed_until = ?, updated_at = ?
                WHERE state = 'pending' AND event_id IN ({placeholders})
                """,
                (
                    claim_token, worker, fence.generation, observed_now + visibility_timeout,
                    observed_now, *event_ids,
                ),
            )
            claimed = connection.execute(
                f"SELECT * FROM outbox WHERE event_id IN ({placeholders}) ORDER BY created_at, event_id",
                event_ids,
            ).fetchall()
            return tuple(_outbox_from_row(row) for row in claimed)

    def ack_outbox(self, event_id: str, claim_token: str, fence: SupervisorFence) -> None:
        with self._transaction(fence) as connection:
            claimed = connection.execute(
                """
                SELECT kind FROM outbox
                WHERE event_id = ? AND state = 'inflight' AND claim_token = ? AND claimed_generation = ?
                """,
                (event_id, claim_token, fence.generation),
            ).fetchone()
            if claimed is None:
                raise StaleGenerationError("outbox receipt is stale or does not own the claim")
            now = self._now()
            if claimed["kind"] == "curator_attention":
                # Retain only the private claim token/generation as the exact
                # idempotent delivery-receipt binding. Public record readers do
                # not expose it and delivered rows are never reclaimable.
                cursor = connection.execute(
                    """
                    UPDATE outbox
                    SET state = 'delivered', delivered_at = ?, claimed_by = NULL,
                        claimed_until = NULL, updated_at = ?, writer_generation = ?
                    WHERE event_id = ? AND state = 'inflight' AND claim_token = ?
                        AND claimed_generation = ?
                    """,
                    (now, now, fence.generation, event_id, claim_token, fence.generation),
                )
            else:
                cursor = connection.execute(
                    """
                    UPDATE outbox
                    SET state = 'delivered', delivered_at = ?, claim_token = NULL,
                        claimed_by = NULL, claimed_until = NULL, updated_at = ?,
                        writer_generation = ?
                    WHERE event_id = ? AND state = 'inflight' AND claim_token = ?
                        AND claimed_generation = ?
                    """,
                    (now, now, fence.generation, event_id, claim_token, fence.generation),
                )
            if cursor.rowcount != 1:
                raise StaleGenerationError("outbox receipt is stale or does not own the claim")
            if claimed["kind"] == "projection_snapshot":
                connection.execute(
                    """
                    DELETE FROM outbox
                    WHERE kind = 'projection_snapshot' AND state = 'delivered'
                        AND event_id NOT IN (
                            SELECT event_id FROM outbox
                            WHERE kind = 'projection_snapshot' AND state = 'delivered'
                            ORDER BY delivered_at DESC, rowid DESC
                            LIMIT ?
                        )
                    """,
                    (self.delivered_projection_retention,),
                )

    def receipt_prior_generation_curator_attention(
        self,
        *,
        event_id: str,
        claim_token: str,
        attention_id: str,
        curator_thread_id: str,
        payload_digest: str,
        fence: SupervisorFence,
        retry_at: float | None = None,
        sanitized_error: str | None = None,
    ) -> bool:
        """Receipt one exact delivery-only claim after a Supervisor restart.

        This is deliberately not a generic claim rebind.  Only an already
        inflight ``curator_attention`` owned by an older generation can cross
        the fence, and every external receipt field is rebound to the durable
        payload inside the current writer transaction.
        """

        event = _machine_value("curator receipt event_id", event_id)
        token = _machine_value("curator receipt claim_token", claim_token)
        attention = _machine_value("curator receipt attention_id", attention_id)
        thread = _machine_value("curator receipt thread_id", curator_thread_id)
        if (
            not isinstance(payload_digest, str)
            or len(payload_digest) != 64
            or any(character not in "0123456789abcdef" for character in payload_digest)
        ):
            raise RegistryValidationError("curator receipt payload digest is invalid")
        if (retry_at is None) == (sanitized_error is not None):
            raise RegistryValidationError(
                "curator receipt must be exactly ACK or NACK"
            )
        error = None
        if retry_at is not None:
            if isinstance(retry_at, bool) or not isinstance(retry_at, (int, float)):
                raise RegistryValidationError("curator NACK retry_at is invalid")
            error = _machine_value(
                "curator NACK reason", sanitized_error
            )[:512]

        with self._transaction(fence) as connection:
            row = connection.execute(
                "SELECT * FROM outbox WHERE event_id = ?",
                (event,),
            ).fetchone()
            if (
                row is None
                or row["kind"] != "curator_attention"
                or row["claim_token"] != token
                or row["claimed_generation"] is None
                or row["state"] not in {"inflight", "delivered"}
            ):
                raise StaleGenerationError(
                    "curator attention receipt is not one exact prior-generation claim"
                )
            claimed_generation = int(row["claimed_generation"])
            if (
                row["state"] == "inflight"
                and claimed_generation >= fence.generation
            ) or (
                row["state"] == "delivered"
                and claimed_generation > fence.generation
            ):
                raise StaleGenerationError(
                    "curator attention receipt generation is not current or prior"
                )
            payload = json.loads(row["payload_json"])
            if (
                row["payload_digest"] != payload_digest
                or payload.get("schema")
                != "dev-control-plane/curator-attention/v2"
                or payload.get("attention_id") != attention
                or payload.get("curator_thread_id") != thread
            ):
                raise StaleGenerationError(
                    "curator attention receipt is cross-bound"
                )
            if row["state"] == "delivered":
                if retry_at is not None:
                    raise StaleGenerationError(
                        "delivered curator attention cannot be negatively receipted"
                    )
                return False
            now = self._now()
            if retry_at is None:
                cursor = connection.execute(
                    """
                    UPDATE outbox
                    SET state = 'delivered', delivered_at = ?, claimed_by = NULL,
                        claimed_until = NULL, updated_at = ?, writer_generation = ?
                    WHERE event_id = ? AND kind = 'curator_attention'
                        AND state = 'inflight' AND claim_token = ?
                        AND claimed_generation < ?
                    """,
                    (now, now, fence.generation, event, token, fence.generation),
                )
            else:
                cursor = connection.execute(
                    """
                    UPDATE outbox
                    SET state = 'pending', available_at = ?, claim_token = NULL,
                        claimed_by = NULL, claimed_generation = NULL,
                        claimed_until = NULL, last_error = ?, updated_at = ?,
                        writer_generation = ?
                    WHERE event_id = ? AND kind = 'curator_attention'
                        AND state = 'inflight' AND claim_token = ?
                        AND claimed_generation < ?
                    """,
                    (
                        float(retry_at), error, now, fence.generation,
                        event, token, fence.generation,
                    ),
                )
            if cursor.rowcount != 1:
                raise StaleGenerationError(
                    "curator attention receipt lost its prior-generation claim"
                )
            return True

    def nack_outbox(
        self,
        event_id: str,
        claim_token: str,
        fence: SupervisorFence,
        *,
        retry_at: float,
        sanitized_error: str,
    ) -> None:
        error = sanitized_error.strip()[:512]
        with self._transaction(fence) as connection:
            cursor = connection.execute(
                """
                UPDATE outbox
                SET state = 'pending', available_at = ?, claim_token = NULL, claimed_by = NULL,
                    claimed_generation = NULL, claimed_until = NULL, last_error = ?, updated_at = ?, writer_generation = ?
                WHERE event_id = ? AND state = 'inflight' AND claim_token = ? AND claimed_generation = ?
                """,
                (retry_at, error, self._now(), fence.generation, event_id, claim_token, fence.generation),
            )
            if cursor.rowcount != 1:
                raise StaleGenerationError("outbox negative receipt is stale or does not own the claim")

    def pending_outbox_count(self) -> int:
        with self._reader() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS total FROM outbox WHERE state IN ('pending', 'inflight')"
            ).fetchone()
        return int(row["total"])

    def accept_task_by_owner(
        self,
        *,
        message_id: str,
        source: str,
        receipt_payload: Mapping[str, Any],
        task_id: str,
        expected_revision: int,
        event_id: str,
        event_payload: Mapping[str, Any],
        outbox_items: Sequence[Mapping[str, Any]],
        fence: SupervisorFence,
    ) -> bool:
        """Atomically record an exact owner receipt and remove the task from active state."""

        message = _machine_value("message_id", message_id)
        source_name = _machine_value("source", source)
        event = _machine_value("event_id", event_id)
        receipt_json = _canonical_json(receipt_payload)
        receipt_digest = _digest(receipt_json)
        event_json = _canonical_json(event_payload)
        event_digest = _digest(event_json)
        now = self._now()
        with self._transaction(fence) as connection:
            existing = connection.execute("SELECT * FROM inbox WHERE message_id = ?", (message,)).fetchone()
            if existing is not None:
                if existing["payload_digest"] != receipt_digest or existing["source"] != source_name:
                    raise IdempotencyConflict("owner receipt message_id was reused for different content")
                return False
            current = connection.execute(
                "SELECT revision, state, passport_json FROM tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
            if current is None:
                raise RegistryValidationError("owner receipt references an unknown task")
            if current["state"] == "accepted":
                raise IdempotencyConflict("task already has a different owner acceptance receipt")
            if int(current["revision"]) != expected_revision:
                raise CASConflict("task changed before owner acceptance")
            connection.execute(
                """
                INSERT INTO inbox(message_id, source, payload_json, payload_digest, state, writer_generation, received_at)
                VALUES (?, ?, ?, ?, 'received', ?, ?)
                """,
                (message, source_name, receipt_json, receipt_digest, fence.generation, now),
            )
            passport_payload = json.loads(current["passport_json"])
            passport_payload["revision"] = expected_revision + 1
            passport_json = _canonical_json(passport_payload)
            cursor = connection.execute(
                """
                UPDATE tasks
                SET state = 'accepted', revision = revision + 1, passport_json = ?, passport_digest = ?,
                    updated_at = ?, writer_generation = ?
                WHERE task_id = ? AND revision = ? AND state != 'accepted'
                """,
                (
                    passport_json, _digest(passport_json), now, fence.generation,
                    task_id, expected_revision,
                ),
            )
            if cursor.rowcount != 1:
                raise CASConflict("task changed before owner acceptance")
            self._append_event_tx(
                connection,
                event,
                "owner_accepted",
                event_json,
                event_digest,
                fence,
                task_id=task_id,
                workstream_id=None,
                executor_generation=None,
                now=now,
            )
            allowed_keys = {"event_id", "kind", "payload", "task_id", "coalescible", "coalesce_key"}
            for item in outbox_items:
                if not isinstance(item, Mapping) or set(item) != allowed_keys:
                    raise RegistryValidationError("owner receipt outbox item fields are invalid")
                payload = item["payload"]
                if not isinstance(payload, Mapping) or not isinstance(item["coalescible"], bool):
                    raise RegistryValidationError("owner receipt outbox item payload is invalid")
                self._enqueue_outbox_tx(
                    connection,
                    str(item["event_id"]),
                    str(item["kind"]),
                    payload,
                    fence,
                    task_id=str(item["task_id"]) if item["task_id"] is not None else None,
                    coalescible=item["coalescible"],
                    coalesce_key=str(item["coalesce_key"]) if item["coalesce_key"] is not None else None,
                    now=now,
                )
            connection.execute(
                "UPDATE inbox SET state = 'processed', processed_at = ? WHERE message_id = ?",
                (now, message),
            )
            return True

    def acquire_task_lock(
        self,
        task_id: str,
        fence: SupervisorFence,
        *,
        owner_workstream_id: str | None = None,
        ttl: float = 60.0,
    ) -> LockGrant:
        return self._acquire_locks("task", (task_id,), task_id, owner_workstream_id, fence, ttl)

    def acquire_thread_lock(
        self,
        thread_id: str,
        owner_task_id: str,
        fence: SupervisorFence,
        *,
        owner_workstream_id: str | None = None,
        ttl: float = 60.0,
    ) -> LockGrant:
        return self._acquire_locks("thread", (thread_id,), owner_task_id, owner_workstream_id, fence, ttl)

    def acquire_resource_locks(
        self,
        resources: Sequence[str],
        owner_task_id: str,
        fence: SupervisorFence,
        *,
        owner_workstream_id: str | None = None,
        ttl: float = 60.0,
    ) -> LockGrant:
        return self._acquire_locks("resource", resources, owner_task_id, owner_workstream_id, fence, ttl)

    def acquire_release_lane(
        self,
        target_id: str,
        logical_task_id: str,
        fence: SupervisorFence,
        *,
        owner_workstream_id: str | None = None,
        ttl: float = 300.0,
    ) -> LockGrant:
        return self._acquire_locks(
            "release_lane", (target_id,), logical_task_id, owner_workstream_id, fence, ttl
        )

    def acquire_execution_reservation(
        self,
        *,
        task_id: str,
        workstream_id: str,
        thread_id: str,
        workspace_id: str,
        resources: Sequence[str],
        fence: SupervisorFence,
        ttl: float = 60.0,
    ) -> tuple[LockGrant, ...]:
        """Atomically reserve a model turn's complete mutation contour.

        Task, exact thread, managed workspace and all classified Passport
        resources share one token and one SQLite transaction.  This prevents a
        release lane or another executor from observing a partially acquired
        set.
        """

        if ttl <= 0:
            raise RegistryValidationError("execution reservation ttl must be positive")
        owner = _machine_value("task_id", task_id)
        workstream = _machine_value("workstream_id", workstream_id)
        thread = _machine_value("thread_id", thread_id)
        workspace = _machine_value("workspace_id", workspace_id)
        resource_keys = tuple(sorted({_machine_value("resource", item) for item in resources}))
        if not resource_keys:
            raise RegistryValidationError("execution reservation requires classified resources")
        requested = tuple(
            sorted(
                (
                    ("task", owner),
                    ("thread", thread),
                    ("workspace", workspace),
                    *(("resource", item) for item in resource_keys),
                ),
                key=lambda item: (item[0], item[1]),
            )
        )
        now = self._now()
        expires_at = now + ttl
        token = secrets.token_urlsafe(24)
        with self._transaction(fence) as connection:
            for kind, key in requested:
                connection.execute(
                    "DELETE FROM locks WHERE lock_kind = ? AND lock_key = ? AND expires_at <= ?",
                    (kind, key, now),
                )
            conflicts = tuple(
                f"{kind}:{key}"
                for kind, key in requested
                if connection.execute(
                    "SELECT 1 FROM locks WHERE lock_kind = ? AND lock_key = ?",
                    (kind, key),
                ).fetchone()
                is not None
            )
            if conflicts:
                raise LockConflict("atomic execution reservation conflicts on: " + ", ".join(conflicts))
            for kind, key in requested:
                connection.execute(
                    """
                    INSERT INTO locks(
                        lock_kind, lock_key, owner_task_id, owner_workstream_id, lock_token,
                        writer_generation, acquired_at, expires_at, revision
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
                    """,
                    (kind, key, owner, workstream, token, fence.generation, now, expires_at),
                )
        grants: list[LockGrant] = []
        for kind in ("task", "resource", "thread", "workspace"):
            keys = tuple(key for observed_kind, key in requested if observed_kind == kind)
            if keys:
                grants.append(LockGrant(kind, keys, owner, workstream, token, fence.generation, expires_at))
        return tuple(grants)

    def renew_execution_reservation(
        self,
        grants: Sequence[LockGrant],
        fence: SupervisorFence,
        *,
        ttl: float = 60.0,
    ) -> tuple[LockGrant, ...]:
        """Atomically attest and extend one exact execution reservation."""

        items = tuple(grants)
        if not items or ttl <= 0:
            raise RegistryValidationError("execution reservation renewal is invalid")
        token = items[0].token
        owner = items[0].owner_task_id
        workstream = items[0].owner_workstream_id
        if workstream is None or any(
            item.token != token
            or item.generation != fence.generation
            or item.owner_task_id != owner
            or item.owner_workstream_id != workstream
            or item.kind not in {"task", "resource", "thread", "workspace"}
            for item in items
        ):
            raise StaleGenerationError("execution reservation grants do not share one current fence")
        requested = tuple(sorted(
            ((item.kind, key) for item in items for key in item.keys),
            key=lambda item: (item[0], item[1]),
        ))
        if len(requested) != len(set(requested)):
            raise RegistryValidationError("execution reservation contains duplicate lock keys")
        now = self._now()
        expires_at = now + ttl
        with self._transaction(fence) as connection:
            for kind, key in requested:
                row = connection.execute(
                    """
                    SELECT owner_task_id,owner_workstream_id,lock_token,writer_generation,expires_at
                    FROM locks WHERE lock_kind = ? AND lock_key = ?
                    """,
                    (kind, key),
                ).fetchone()
                if (
                    row is None
                    or row["owner_task_id"] != owner
                    or row["owner_workstream_id"] != workstream
                    or row["lock_token"] != token
                    or int(row["writer_generation"]) != fence.generation
                    or float(row["expires_at"]) <= now
                ):
                    raise LockConflict("execution reservation is missing, stale, expired or reassigned")
            for kind, key in requested:
                cursor = connection.execute(
                    """
                    UPDATE locks SET expires_at = ?, revision = revision + 1
                    WHERE lock_kind = ? AND lock_key = ? AND owner_task_id = ?
                        AND owner_workstream_id = ? AND lock_token = ?
                        AND writer_generation = ? AND expires_at > ?
                    """,
                    (expires_at, kind, key, owner, workstream, token, fence.generation, now),
                )
                if cursor.rowcount != 1:
                    raise LockConflict("execution reservation changed during atomic renewal")
        return tuple(
            LockGrant(
                item.kind,
                item.keys,
                item.owner_task_id,
                item.owner_workstream_id,
                item.token,
                item.generation,
                expires_at,
            )
            for item in items
        )

    def release_execution_reservation(
        self,
        grants: Sequence[LockGrant],
        fence: SupervisorFence,
    ) -> None:
        """Release only the exact token shared by an execution reservation."""

        self.release_scheduler_reservation(grants, fence)

    def attest_lock_grant(
        self,
        grant: LockGrant,
        fence: SupervisorFence,
        *,
        expected_kind: str,
        expected_key: str,
        expected_task_id: str,
        expected_workstream_id: str | None,
    ) -> None:
        """Read back one exact, live pre-held grant without changing its TTL."""

        if (
            grant.kind != expected_kind
            or grant.keys != (expected_key,)
            or grant.owner_task_id != expected_task_id
            or grant.owner_workstream_id != expected_workstream_id
            or grant.generation != fence.generation
        ):
            raise LockConflict("pre-held lock grant is bound to another operation")
        now = self._now()
        with self._reader() as connection:
            self._assert_fence(connection, fence)
            row = connection.execute(
                """
                SELECT owner_task_id,owner_workstream_id,lock_token,writer_generation,expires_at
                FROM locks WHERE lock_kind = ? AND lock_key = ?
                """,
                (expected_kind, expected_key),
            ).fetchone()
        if (
            row is None
            or row["owner_task_id"] != expected_task_id
            or row["owner_workstream_id"] != expected_workstream_id
            or row["lock_token"] != grant.token
            or int(row["writer_generation"]) != fence.generation
            or float(row["expires_at"]) <= now
        ):
            raise LockConflict("pre-held lock grant is missing, stale, expired or reassigned")

    def acquire_scheduler_reservation(
        self,
        *,
        task_id: str,
        workstream_id: str,
        target_id: str,
        resources: Sequence[str],
        fence: SupervisorFence,
        ttl: float = 300.0,
    ) -> tuple[LockGrant, ...]:
        """Atomically reserve task, all sorted resources and the global target lane."""

        if ttl <= 0:
            raise RegistryValidationError("scheduler reservation ttl must be positive")
        owner = _machine_value("task_id", task_id)
        workstream = _machine_value("workstream_id", workstream_id)
        target = _machine_value("target_id", target_id)
        resource_keys = tuple(sorted({_machine_value("resource", item) for item in resources}))
        if not resource_keys:
            raise RegistryValidationError("scheduler reservation requires classified resources")
        requested = tuple(
            sorted(
                (("task", owner), ("release_lane", target), *(("resource", item) for item in resource_keys)),
                key=lambda item: (item[0], item[1]),
            )
        )
        now = self._now()
        expires_at = now + ttl
        token = secrets.token_urlsafe(24)
        with self._transaction(fence) as connection:
            for kind, key in requested:
                connection.execute(
                    "DELETE FROM locks WHERE lock_kind = ? AND lock_key = ? AND expires_at <= ?",
                    (kind, key, now),
                )
            conflicts: list[str] = []
            for kind, key in requested:
                row = connection.execute(
                    "SELECT owner_task_id FROM locks WHERE lock_kind = ? AND lock_key = ?",
                    (kind, key),
                ).fetchone()
                if row is not None:
                    conflicts.append(f"{kind}:{key}")
            if conflicts:
                raise LockConflict("atomic scheduler reservation conflicts on: " + ", ".join(conflicts))
            for kind, key in requested:
                connection.execute(
                    """
                    INSERT INTO locks(
                        lock_kind, lock_key, owner_task_id, owner_workstream_id, lock_token,
                        writer_generation, acquired_at, expires_at, revision
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
                    """,
                    (kind, key, owner, workstream, token, fence.generation, now, expires_at),
                )
        grants: list[LockGrant] = []
        for kind in ("task", "resource", "release_lane"):
            keys = tuple(key for observed_kind, key in requested if observed_kind == kind)
            if keys:
                grants.append(LockGrant(kind, keys, owner, workstream, token, fence.generation, expires_at))
        return tuple(grants)

    def validate_and_renew_scheduler_reservation(
        self,
        *,
        task_id: str,
        workstream_id: str,
        target_id: str,
        resources: Sequence[str],
        fence: SupervisorFence,
        ttl: float = 900.0,
    ) -> float:
        """Atomically attest and extend one exact live scheduler reservation.

        This method intentionally does not create missing locks. A release
        worker may only extend the exact task/resource/target-lane reservation
        produced by the scheduler in the same fenced Supervisor generation.
        """

        if ttl <= 0:
            raise RegistryValidationError("scheduler reservation renewal ttl must be positive")
        owner = _machine_value("task_id", task_id)
        workstream = _machine_value("workstream_id", workstream_id)
        target = _machine_value("target_id", target_id)
        resource_keys = tuple(sorted({_machine_value("resource", item) for item in resources}))
        if not resource_keys:
            raise RegistryValidationError("scheduler reservation renewal requires resources")
        expected = tuple(
            sorted(
                (("task", owner), ("release_lane", target), *(("resource", item) for item in resource_keys)),
                key=lambda item: (item[0], item[1]),
            )
        )
        now = self._now()
        expires_at = now + ttl
        with self._transaction(fence) as connection:
            observed: list[tuple[str, str]] = []
            for kind, key in expected:
                row = connection.execute(
                    """
                    SELECT owner_task_id, owner_workstream_id, writer_generation, expires_at
                    FROM locks WHERE lock_kind = ? AND lock_key = ?
                    """,
                    (kind, key),
                ).fetchone()
                if (
                    row is None
                    or row["owner_task_id"] != owner
                    or row["owner_workstream_id"] != workstream
                    or int(row["writer_generation"]) != fence.generation
                    or float(row["expires_at"]) <= now
                ):
                    raise LockConflict("scheduler reservation is missing, stale, expired or reassigned")
                observed.append((kind, key))
            if tuple(observed) != expected:
                raise LockConflict("scheduler reservation is incomplete")
            for kind, key in expected:
                cursor = connection.execute(
                    """
                    UPDATE locks SET expires_at = ?, revision = revision + 1
                    WHERE lock_kind = ? AND lock_key = ? AND owner_task_id = ?
                        AND owner_workstream_id = ? AND writer_generation = ? AND expires_at > ?
                    """,
                    (expires_at, kind, key, owner, workstream, fence.generation, now),
                )
                if cursor.rowcount != 1:
                    raise LockConflict("scheduler reservation changed during atomic renewal")
        return expires_at

    def renew_scheduler_reservation_owner(
        self,
        *,
        task_id: str,
        workstream_id: str,
        target_id: str,
        resources: Sequence[str],
        fence: SupervisorFence,
        ttl: float = 300.0,
    ) -> tuple[LockGrant, ...]:
        """Restart-safe adopt/renew of the locks proven by a durable reservation event."""

        if ttl <= 0:
            raise RegistryValidationError("scheduler reservation ttl must be positive")
        owner = _machine_value("task_id", task_id)
        workstream = _machine_value("workstream_id", workstream_id)
        target = _machine_value("target_id", target_id)
        resource_keys = tuple(sorted({_machine_value("resource", item) for item in resources}))
        requested = tuple(
            sorted(
                (("task", owner), ("release_lane", target), *(("resource", item) for item in resource_keys)),
                key=lambda item: (item[0], item[1]),
            )
        )
        now = self._now()
        expires_at = now + ttl
        token = secrets.token_urlsafe(24)
        with self._transaction(fence) as connection:
            for kind, key in requested:
                row = connection.execute(
                    "SELECT * FROM locks WHERE lock_kind = ? AND lock_key = ?",
                    (kind, key),
                ).fetchone()
                if row is not None and row["owner_task_id"] != owner and float(row["expires_at"]) > now:
                    raise LockConflict(f"scheduler reservation conflicts on {kind}:{key}")
                if row is not None and row["owner_task_id"] != owner:
                    connection.execute(
                        "DELETE FROM locks WHERE lock_kind = ? AND lock_key = ?", (kind, key)
                    )
                    row = None
                if row is None:
                    connection.execute(
                        """
                        INSERT INTO locks(
                            lock_kind, lock_key, owner_task_id, owner_workstream_id, lock_token,
                            writer_generation, acquired_at, expires_at, revision
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
                        """,
                        (kind, key, owner, workstream, token, fence.generation, now, expires_at),
                    )
                else:
                    connection.execute(
                        """
                        UPDATE locks SET owner_workstream_id = ?, lock_token = ?, writer_generation = ?,
                            expires_at = ?, revision = revision + 1
                        WHERE lock_kind = ? AND lock_key = ? AND owner_task_id = ?
                        """,
                        (workstream, token, fence.generation, expires_at, kind, key, owner),
                    )
        grants: list[LockGrant] = []
        for kind in ("task", "resource", "release_lane"):
            keys = tuple(key for observed_kind, key in requested if observed_kind == kind)
            if keys:
                grants.append(LockGrant(kind, keys, owner, workstream, token, fence.generation, expires_at))
        return tuple(grants)

    def release_scheduler_reservation_owner(
        self,
        *,
        task_id: str,
        workstream_id: str,
        fence: SupervisorFence,
    ) -> int:
        """Release only locks owned by one terminal logical workstream under the current fence."""

        with self._transaction(fence) as connection:
            cursor = connection.execute(
                """
                DELETE FROM locks
                WHERE owner_task_id = ? AND owner_workstream_id = ?
                    AND lock_kind IN ('task', 'resource', 'release_lane')
                """,
                (task_id, workstream_id),
            )
            return cursor.rowcount

    def release_scheduler_reservation(
        self,
        grants: Sequence[LockGrant],
        fence: SupervisorFence,
    ) -> None:
        items = tuple(grants)
        if not items:
            return
        token = items[0].token
        if any(item.token != token or item.generation != fence.generation for item in items):
            raise StaleGenerationError("scheduler reservation grants do not share one current fence")
        expected = sum(len(item.keys) for item in items)
        with self._transaction(fence) as connection:
            removed = 0
            for grant in items:
                placeholders = ",".join("?" for _ in grant.keys)
                cursor = connection.execute(
                    f"""
                    DELETE FROM locks WHERE lock_kind = ? AND lock_key IN ({placeholders})
                        AND lock_token = ? AND writer_generation = ?
                    """,
                    (grant.kind, *grant.keys, token, fence.generation),
                )
                removed += cursor.rowcount
            if removed != expected:
                raise StaleGenerationError("scheduler reservation is incomplete or already lost")

    def _acquire_locks(
        self,
        kind: str,
        keys: Sequence[str],
        owner_task_id: str,
        owner_workstream_id: str | None,
        fence: SupervisorFence,
        ttl: float,
    ) -> LockGrant:
        if kind not in _LOCK_KINDS or ttl <= 0:
            raise RegistryValidationError("invalid lock kind or ttl")
        normalized = tuple(sorted({_machine_value("lock_key", item) for item in keys}))
        if not normalized:
            raise RegistryValidationError("at least one lock key is required")
        owner = _machine_value("owner_task_id", owner_task_id)
        if owner_workstream_id is not None:
            _machine_value("owner_workstream_id", owner_workstream_id)
        now = self._now()
        expires_at = now + ttl
        token = secrets.token_urlsafe(24)
        with self._transaction(fence) as connection:
            placeholders = ",".join("?" for _ in normalized)
            connection.execute(
                f"DELETE FROM locks WHERE lock_kind = ? AND lock_key IN ({placeholders}) AND expires_at <= ?",
                (kind, *normalized, now),
            )
            conflicts = connection.execute(
                f"SELECT lock_key, owner_task_id FROM locks WHERE lock_kind = ? AND lock_key IN ({placeholders}) ORDER BY lock_key",
                (kind, *normalized),
            ).fetchall()
            if conflicts:
                names = ", ".join(row["lock_key"] for row in conflicts)
                raise LockConflict(f"atomic {kind} lock acquisition conflicts on: {names}")
            for key in normalized:
                connection.execute(
                    """
                    INSERT INTO locks(
                        lock_kind, lock_key, owner_task_id, owner_workstream_id, lock_token,
                        writer_generation, acquired_at, expires_at, revision
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
                    """,
                    (kind, key, owner, owner_workstream_id, token, fence.generation, now, expires_at),
                )
        return LockGrant(kind, normalized, owner, owner_workstream_id, token, fence.generation, expires_at)

    def renew_lock(self, grant: LockGrant, fence: SupervisorFence, *, ttl: float = 60.0) -> LockGrant:
        if ttl <= 0 or grant.generation != fence.generation:
            raise StaleGenerationError("lock grant belongs to a stale generation")
        expires_at = self._now() + ttl
        with self._transaction(fence) as connection:
            placeholders = ",".join("?" for _ in grant.keys)
            cursor = connection.execute(
                f"""
                UPDATE locks SET expires_at = ?, revision = revision + 1
                WHERE lock_kind = ? AND lock_key IN ({placeholders}) AND lock_token = ?
                    AND writer_generation = ? AND expires_at > ?
                """,
                (
                    expires_at, grant.kind, *grant.keys, grant.token, fence.generation, self._now(),
                ),
            )
            if cursor.rowcount != len(grant.keys):
                raise StaleGenerationError("lock grant is incomplete, expired or fenced out")
        return LockGrant(
            grant.kind, grant.keys, grant.owner_task_id, grant.owner_workstream_id,
            grant.token, grant.generation, expires_at,
        )

    def release_locks(self, grant: LockGrant, fence: SupervisorFence) -> None:
        if grant.generation != fence.generation:
            raise StaleGenerationError("lock grant belongs to a stale generation")
        with self._transaction(fence) as connection:
            placeholders = ",".join("?" for _ in grant.keys)
            cursor = connection.execute(
                f"""
                DELETE FROM locks
                WHERE lock_kind = ? AND lock_key IN ({placeholders})
                    AND lock_token = ? AND writer_generation = ?
                """,
                (grant.kind, *grant.keys, grant.token, fence.generation),
            )
            if cursor.rowcount != len(grant.keys):
                raise StaleGenerationError("lock grant is incomplete or already lost")

    def inspect_locks(self, *, kind: str | None = None) -> tuple[dict[str, Any], ...]:
        with self._reader() as connection:
            if kind is None:
                rows = connection.execute("SELECT * FROM locks ORDER BY lock_kind, lock_key").fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM locks WHERE lock_kind = ? ORDER BY lock_key", (kind,)
                ).fetchall()
        return tuple(
            {
                "lock_kind": row["lock_kind"],
                "lock_key": row["lock_key"],
                "owner_task_id": row["owner_task_id"],
                "owner_workstream_id": row["owner_workstream_id"],
                "writer_generation": int(row["writer_generation"]),
                "acquired_at": float(row["acquired_at"]),
                "expires_at": float(row["expires_at"]),
                "revision": int(row["revision"]),
            }
            for row in rows
        )

    def backup(self, destination: Path | str | None = None) -> Path:
        source = self._connect()
        try:
            if destination is None:
                return self._backup_connection(source, suffix="manual")
            target = Path(destination).expanduser().resolve()
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            if target.exists():
                raise RegistryValidationError("backup destination already exists")
            target_connection = sqlite3.connect(target)
            try:
                source.backup(target_connection)
            finally:
                target_connection.close()
            os.chmod(target, 0o600)
            return target
        finally:
            source.close()

    def _backup_connection(self, source: sqlite3.Connection, *, suffix: str) -> Path:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        target = self.backup_dir / f"{self.db_path.stem}.{suffix}.{timestamp}.{secrets.token_hex(4)}.sqlite3"
        target_connection = sqlite3.connect(target)
        try:
            source.backup(target_connection)
        finally:
            target_connection.close()
        os.chmod(target, 0o600)
        return target

    def pragmas(self) -> dict[str, Any]:
        with self._reader() as connection:
            return {
                "journal_mode": str(connection.execute("PRAGMA journal_mode").fetchone()[0]).lower(),
                "synchronous": int(connection.execute("PRAGMA synchronous").fetchone()[0]),
                "foreign_keys": int(connection.execute("PRAGMA foreign_keys").fetchone()[0]),
                "busy_timeout": int(connection.execute("PRAGMA busy_timeout").fetchone()[0]),
                "user_version": int(connection.execute("PRAGMA user_version").fetchone()[0]),
            }

    def health(self) -> dict[str, Any]:
        with self._reader() as connection:
            integrity = connection.execute("PRAGMA quick_check").fetchone()[0]
            lease = dict(connection.execute("SELECT * FROM supervisor_lease WHERE singleton = 1").fetchone())
        return {
            "ok": integrity == "ok",
            "integrity": integrity,
            "schema_version": CURRENT_SCHEMA_VERSION,
            "lease_generation": lease["generation"],
            "lease_active": bool(lease["owner_id"] and lease["expires_at"] > self._now()),
            "private_permissions": stat.S_IMODE(self.db_path.stat().st_mode) == 0o600,
        }

    def _task_record(self, connection: sqlite3.Connection, task_id: str) -> TaskRecord:
        row = connection.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        if row is None:
            raise RegistryValidationError(f"unknown task: {task_id}")
        return _task_from_row(row)

    def _workstream_record(
        self, connection: sqlite3.Connection, workstream_id: str, generation: int
    ) -> WorkstreamRecord:
        row = connection.execute(
            "SELECT * FROM workstreams WHERE workstream_id = ? AND generation = ?",
            (workstream_id, generation),
        ).fetchone()
        if row is None:
            raise RegistryValidationError("unknown workstream generation")
        return _workstream_from_row(row)

    def _executor_binding(
        self, connection: sqlite3.Connection, task_id: str, workstream_id: str, generation: int
    ) -> ExecutorBinding:
        row = connection.execute(
            """
            SELECT * FROM executor_bindings
            WHERE task_id = ? AND workstream_id = ? AND executor_generation = ?
            """,
            (task_id, workstream_id, generation),
        ).fetchone()
        if row is None:
            raise RegistryValidationError("unknown executor generation")
        return _executor_from_row(row)

    def _idempotent_replay(
        self, connection: sqlite3.Connection, scope: str, key: str, request_digest: str
    ) -> dict[str, Any] | None:
        row = connection.execute(
            "SELECT * FROM idempotency_keys WHERE scope = ? AND idempotency_key = ?", (scope, key)
        ).fetchone()
        if row is None:
            return None
        if row["request_digest"] != request_digest:
            raise IdempotencyConflict("idempotency key was reused for a different request")
        return json.loads(row["result_json"])

    def _record_idempotency(
        self,
        connection: sqlite3.Connection,
        scope: str,
        key: str,
        request_digest: str,
        result: Mapping[str, Any],
        fence: SupervisorFence,
        now: float,
    ) -> None:
        connection.execute(
            """
            INSERT INTO idempotency_keys(
                scope, idempotency_key, request_digest, result_json, writer_generation, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (scope, key, request_digest, _canonical_json(result), fence.generation, now),
        )

    def _now(self, explicit: float | None = None) -> float:
        return float(self._clock() if explicit is None else explicit)


def _projection_transport_seed(connection: sqlite3.Connection) -> tuple[int, int, int]:
    """Recover v1 transport coordinates before retention can remove snapshots."""

    rows = connection.execute(
        "SELECT event_id, payload_json FROM outbox WHERE kind = 'projection_snapshot' ORDER BY created_at, event_id"
    ).fetchall()
    if not rows:
        return 0, 0, 0
    coordinates: list[tuple[int, int, int]] = []
    generation_sequences: set[tuple[int, int]] = set()
    revisions: set[int] = set()
    for row in rows:
        try:
            payload = json.loads(row["payload_json"])
        except (TypeError, ValueError) as exc:
            raise RegistryError(
                f"projection transport migration found malformed JSON for event {row['event_id']}"
            ) from exc
        if not isinstance(payload, Mapping):
            raise RegistryError(
                f"projection transport migration found a non-object envelope for event {row['event_id']}"
            )
        values: list[int] = []
        for field_name in ("generation", "sequence", "revision"):
            value = payload.get(field_name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise RegistryError(
                    f"projection transport migration found invalid {field_name} for event {row['event_id']}"
                )
            values.append(value)
        generation, sequence, revision = values
        if (generation, sequence) in generation_sequences or revision in revisions:
            raise RegistryError("projection transport migration found duplicate monotonic coordinates")
        generation_sequences.add((generation, sequence))
        revisions.add(revision)
        coordinates.append((generation, sequence, revision))
    latest_generation = max(item[0] for item in coordinates)
    latest_sequence = max(item[1] for item in coordinates if item[0] == latest_generation)
    latest_revision = max(item[2] for item in coordinates)
    return latest_generation, latest_sequence, latest_revision


def _task_from_row(row: sqlite3.Row) -> TaskRecord:
    return TaskRecord(
        task_id=row["task_id"], revision=int(row["revision"]), state=row["state"],
        passport=json.loads(row["passport_json"]), created_at=float(row["created_at"]),
        updated_at=float(row["updated_at"]),
    )


def _workstream_from_row(row: sqlite3.Row) -> WorkstreamRecord:
    return WorkstreamRecord(
        workstream_id=row["workstream_id"], task_id=row["task_id"], generation=int(row["generation"]),
        revision=int(row["revision"]), state=row["state"], contract=json.loads(row["contract_json"]),
        current=bool(row["is_current"]),
    )


def _executor_from_row(row: sqlite3.Row) -> ExecutorBinding:
    return ExecutorBinding(
        task_id=row["task_id"], workstream_id=row["workstream_id"],
        executor_generation=int(row["executor_generation"]), thread_id=row["thread_id"],
        host_id=row["host_id"], model=row["model"], reasoning=row["reasoning"], state=row["state"],
        predecessor_generation=(
            int(row["predecessor_generation"]) if row["predecessor_generation"] is not None else None
        ),
        proof_event_id=row["proof_event_id"],
    )


def _outbox_from_row(row: sqlite3.Row) -> OutboxMessage:
    return OutboxMessage(
        event_id=row["event_id"], kind=row["kind"], payload=json.loads(row["payload_json"]),
        task_id=row["task_id"], coalescible=bool(row["coalescible"]), coalesce_key=row["coalesce_key"],
        attempts=int(row["attempts"]), claim_token=row["claim_token"],
        claimed_generation=int(row["claimed_generation"]), writer_generation=int(row["writer_generation"]),
    )


def _event_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "event_id": row["event_id"],
        "task_id": row["task_id"],
        "workstream_id": row["workstream_id"],
        "event_type": row["event_type"],
        "payload": json.loads(row["payload_json"]),
        "executor_generation": (
            int(row["executor_generation"]) if row["executor_generation"] is not None else None
        ),
        "writer_generation": int(row["writer_generation"]),
        "created_at": float(row["created_at"]),
    }


def _passport_for_validation(payload: Mapping[str, Any]) -> TaskPassport:
    from .orchestration_contracts import task_passport_from_mapping

    return task_passport_from_mapping(payload)


def _machine_value(label: str, value: Any) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 256
        or value != value.strip()
        or any(ord(character) < 33 for character in value)
    ):
        raise RegistryValidationError(f"{label} must be a bounded machine value")
    return value


def _canonical_json(payload: Any) -> str:
    try:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise RegistryValidationError("payload must be finite JSON data") from exc


def _digest(payload_json: str) -> str:
    return hashlib.sha256(payload_json.encode("utf-8")).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
