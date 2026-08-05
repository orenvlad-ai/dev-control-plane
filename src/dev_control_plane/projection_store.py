"""Rebuildable, sanitized SQLite projection state for the hosted v2 viewer.

This module is deliberately independent from execution/orchestration code.  It
stores complete, sanitized snapshots received from the single Mac Supervisor;
it never decides work, invokes a model, or mutates a target repository.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import time
from typing import Any, Callable, Mapping, Sequence


PROJECTION_CONTRACT = "dev_control_plane_projection_v2"
CURRENT_SCHEMA_VERSION = 3
DEFAULT_INGEST_RECEIPT_RETENTION = 4_096
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
SHA_RE = re.compile(r"^[0-9a-f]{7,64}$")
SECRET_VALUE_RE = re.compile(
    r"(?i)(authorization\s*:|bearer\s+[A-Za-z0-9._~+\-/]+=*|"
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----|github_pat_[A-Za-z0-9_]+|"
    r"gh[opsu]_[A-Za-z0-9]+|sk-[A-Za-z0-9_-]{16,}|"
    r"(?:api[_ -]?key|password|cookie)\s*[:=])"
)
SECRET_KEY_RE = re.compile(
    r"(?i)(secret|token|password|authorization|cookie|private[_-]?key|raw[_-]?log|shell[_-]?command)"
)

TASK_STATUSES = {
    "working",
    "waiting_release",
    "recovering",
    "blocked",
    "awaiting_acceptance",
    "completed",
    "accepted",
    "parked",
}
WORKSTREAM_STATUSES = TASK_STATUSES - {"accepted"}
RELEASE_STATUSES = {
    "none",
    "planned",
    "pr_open",
    "checks_running",
    "ready",
    "merging",
    "merged",
    "deploying",
    "verifying",
    "production",
    "blocked",
    "failed",
}
INCIDENT_STATUSES = {"open", "investigating", "recovering", "parked", "resolved"}
ATTENTION_STATUSES = {"pending", "delivered", "acknowledged", "resolved"}
ATTENTION_KINDS = {"terminal", "human_gate", "serious_stall", "acceptance"}
ACCEPTANCE_STATUSES = {"not_ready", "awaiting_owner", "accepted"}

MAX_ITEMS = {
    "tasks": 500,
    "workstreams": 2_000,
    "release_lanes": 2_000,
    "incidents": 5_000,
    "attention": 5_000,
    "acceptance": 500,
}

ENTITY_ID_FIELDS = {
    "tasks": "task_id",
    "workstreams": "workstream_id",
    "release_lanes": "release_id",
    "incidents": "incident_id",
    "attention": "attention_id",
    "acceptance": "acceptance_id",
}


class ProjectionStoreError(RuntimeError):
    """Base class for controlled projection-store failures."""

    code = "projection_store_error"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        if code:
            self.code = code


class ProjectionValidationError(ProjectionStoreError):
    code = "projection_validation_failed"


class ProjectionConflictError(ProjectionStoreError):
    code = "projection_conflict"


@dataclass(frozen=True)
class ProjectionEnvelope:
    contract: str
    supervisor_id: str
    generation: int
    sequence: int
    revision: int
    event_id: str
    idempotency_key: str
    timestamp: int
    projection: Mapping[str, tuple[Mapping[str, Any], ...]]


@dataclass(frozen=True)
class IngestReceipt:
    applied: bool
    duplicate: bool
    supervisor_id: str
    generation: int
    sequence: int
    revision: int
    event_id: str
    idempotency_key: str


MIGRATIONS: tuple[tuple[int, str], ...] = (
    (
        1,
        """
        CREATE TABLE projection_meta (
            singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
            contract TEXT NOT NULL,
            supervisor_id TEXT NOT NULL,
            generation INTEGER NOT NULL CHECK (generation > 0),
            sequence INTEGER NOT NULL CHECK (sequence > 0),
            revision INTEGER NOT NULL CHECK (revision > 0),
            last_event_id TEXT NOT NULL,
            source_timestamp INTEGER NOT NULL,
            received_at TEXT NOT NULL,
            received_at_epoch REAL NOT NULL
        );

        CREATE TABLE ingest_receipts (
            event_id TEXT PRIMARY KEY,
            idempotency_key TEXT NOT NULL UNIQUE,
            supervisor_id TEXT NOT NULL,
            generation INTEGER NOT NULL,
            sequence INTEGER NOT NULL,
            revision INTEGER NOT NULL,
            body_sha256 TEXT NOT NULL,
            received_at TEXT NOT NULL
        );

        CREATE TABLE tasks (
            task_id TEXT PRIMARY KEY,
            revision INTEGER NOT NULL CHECK (revision > 0),
            title TEXT NOT NULL,
            status TEXT NOT NULL,
            objective TEXT NOT NULL,
            curator_thread_id TEXT NOT NULL,
            active INTEGER NOT NULL CHECK (active IN (0, 1)),
            accepted INTEGER NOT NULL CHECK (accepted IN (0, 1)),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE workstreams (
            workstream_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
            revision INTEGER NOT NULL CHECK (revision > 0),
            title TEXT NOT NULL,
            status TEXT NOT NULL,
            progress INTEGER NOT NULL CHECK (progress BETWEEN 5 AND 100),
            remaining_range TEXT NOT NULL,
            delta TEXT NOT NULL,
            current_action TEXT NOT NULL,
            blocker TEXT NOT NULL,
            active INTEGER NOT NULL CHECK (active IN (0, 1)),
            updated_at TEXT NOT NULL
        );

        CREATE TABLE release_lanes (
            release_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
            workstream_id TEXT REFERENCES workstreams(workstream_id) ON DELETE CASCADE,
            revision INTEGER NOT NULL CHECK (revision > 0),
            status TEXT NOT NULL,
            pr_url TEXT NOT NULL,
            pr_number INTEGER,
            head_sha TEXT NOT NULL,
            merge_sha TEXT NOT NULL,
            environment TEXT NOT NULL,
            deploy_status TEXT NOT NULL,
            verification_status TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE incidents (
            incident_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
            workstream_id TEXT REFERENCES workstreams(workstream_id) ON DELETE CASCADE,
            revision INTEGER NOT NULL CHECK (revision > 0),
            status TEXT NOT NULL,
            fingerprint TEXT NOT NULL,
            summary TEXT NOT NULL,
            decision TEXT NOT NULL,
            attempt INTEGER NOT NULL CHECK (attempt BETWEEN 1 AND 5),
            updated_at TEXT NOT NULL
        );

        CREATE TABLE attention (
            attention_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
            workstream_id TEXT REFERENCES workstreams(workstream_id) ON DELETE CASCADE,
            revision INTEGER NOT NULL CHECK (revision > 0),
            kind TEXT NOT NULL,
            status TEXT NOT NULL,
            summary TEXT NOT NULL,
            required_action TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE acceptance (
            acceptance_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL UNIQUE REFERENCES tasks(task_id) ON DELETE CASCADE,
            revision INTEGER NOT NULL CHECK (revision > 0),
            status TEXT NOT NULL,
            technical_complete INTEGER NOT NULL CHECK (technical_complete IN (0, 1)),
            owner_accepted INTEGER NOT NULL CHECK (owner_accepted IN (0, 1)),
            requested_at TEXT NOT NULL,
            accepted_at TEXT NOT NULL,
            summary TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """,
    ),
    (
        2,
        """
        CREATE INDEX workstreams_task_status_idx ON workstreams(task_id, active, status);
        CREATE INDEX release_lanes_task_idx ON release_lanes(task_id, workstream_id, status);
        CREATE INDEX incidents_task_status_idx ON incidents(task_id, status);
        CREATE INDEX attention_task_status_idx ON attention(task_id, status);
        CREATE INDEX receipts_supervisor_sequence_idx
            ON ingest_receipts(supervisor_id, generation, sequence);
        """,
    ),
    (
        3,
        """
        ALTER TABLE tasks DROP COLUMN curator_thread_id;
        """,
    ),
)


class ProjectionStore:
    """Transactional full-snapshot store for one fenced Supervisor source."""

    def __init__(
        self,
        database_path: Path | str,
        *,
        receipt_retention: int = DEFAULT_INGEST_RECEIPT_RETENTION,
    ) -> None:
        if not 1 <= receipt_retention <= 1_000_000:
            raise ValueError("receipt_retention must be between 1 and 1000000")
        expanded = Path(database_path).expanduser()
        if not expanded.is_absolute():
            expanded = Path.cwd() / expanded
        if expanded.name in {"", ".", ".."}:
            raise ProjectionStoreError(
                "projection database filename is invalid",
                code="unsafe_database_path",
            )
        self.path = Path(os.path.abspath(expanded))
        self.receipt_retention = int(receipt_retention)
        self._prepare_private_path()
        self._migrate()

    def _prepare_private_path(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        resolved_parent = self.path.parent.resolve(strict=True)
        parent_metadata = resolved_parent.lstat()
        if (
            not stat.S_ISDIR(parent_metadata.st_mode)
            or parent_metadata.st_uid != os.geteuid()
        ):
            raise ProjectionStoreError(
                "projection database directory must be owned by the service user",
                code="unsafe_database_path",
            )
        resolved_parent.chmod(0o700)
        self.path = resolved_parent / self.path.name
        try:
            metadata = self.path.lstat()
        except FileNotFoundError:
            return
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or metadata.st_nlink != 1
        ):
            raise ProjectionStoreError(
                "projection database must be one service-owned regular file",
                code="unsafe_database_path",
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=10000")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA trusted_schema=OFF")
        self._enforce_private_files()
        return connection

    def _migrate(self) -> None:
        connection = self._connect()
        try:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            applied = {
                int(row["version"])
                for row in connection.execute("SELECT version FROM schema_migrations ORDER BY version")
            }
            for version, script in MIGRATIONS:
                if version in applied:
                    continue
                applied_at = _now_iso()
                escaped_time = applied_at.replace("'", "''")
                connection.executescript(
                    "BEGIN IMMEDIATE;\n"
                    + script
                    + f"\nINSERT INTO schema_migrations(version, applied_at) VALUES ({version}, '{escaped_time}');\n"
                    + f"PRAGMA user_version={version};\nCOMMIT;"
                )
            current = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if current != CURRENT_SCHEMA_VERSION:
                raise ProjectionStoreError(
                    f"unsupported projection schema version: {current}",
                    code="schema_version_mismatch",
                )
        finally:
            connection.close()
            self._enforce_private_files()

    def ingest(
        self,
        envelope: ProjectionEnvelope,
        *,
        body_sha256: str,
        received_at_epoch: float | None = None,
    ) -> IngestReceipt:
        if not re.fullmatch(r"[0-9a-f]{64}", body_sha256):
            raise ProjectionValidationError("body_sha256 must be a lowercase SHA-256 digest")
        received_epoch = float(time.time() if received_at_epoch is None else received_at_epoch)
        received_at = datetime.fromtimestamp(received_epoch, tz=timezone.utc).isoformat().replace("+00:00", "Z")
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            duplicate = self._existing_receipt(connection, envelope, body_sha256)
            if duplicate:
                connection.execute("ROLLBACK")
                return IngestReceipt(
                    applied=False,
                    duplicate=True,
                    supervisor_id=envelope.supervisor_id,
                    generation=envelope.generation,
                    sequence=envelope.sequence,
                    revision=envelope.revision,
                    event_id=envelope.event_id,
                    idempotency_key=envelope.idempotency_key,
                )

            meta = connection.execute("SELECT * FROM projection_meta WHERE singleton=1").fetchone()
            self._validate_monotonic_state(meta, envelope)
            self._replace_projection(connection, envelope)
            connection.execute(
                "INSERT INTO ingest_receipts("
                "event_id,idempotency_key,supervisor_id,generation,sequence,revision,body_sha256,received_at"
                ") VALUES (?,?,?,?,?,?,?,?)",
                (
                    envelope.event_id,
                    envelope.idempotency_key,
                    envelope.supervisor_id,
                    envelope.generation,
                    envelope.sequence,
                    envelope.revision,
                    body_sha256,
                    received_at,
                ),
            )
            connection.execute(
                "INSERT INTO projection_meta("
                "singleton,contract,supervisor_id,generation,sequence,revision,last_event_id,"
                "source_timestamp,received_at,received_at_epoch"
                ") VALUES (1,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(singleton) DO UPDATE SET "
                "contract=excluded.contract,supervisor_id=excluded.supervisor_id,"
                "generation=excluded.generation,sequence=excluded.sequence,revision=excluded.revision,"
                "last_event_id=excluded.last_event_id,source_timestamp=excluded.source_timestamp,"
                "received_at=excluded.received_at,received_at_epoch=excluded.received_at_epoch",
                (
                    envelope.contract,
                    envelope.supervisor_id,
                    envelope.generation,
                    envelope.sequence,
                    envelope.revision,
                    envelope.event_id,
                    envelope.timestamp,
                    received_at,
                    received_epoch,
                ),
            )
            connection.execute(
                """
                DELETE FROM ingest_receipts
                WHERE rowid NOT IN (
                    SELECT rowid FROM ingest_receipts ORDER BY rowid DESC LIMIT ?
                )
                """,
                (self.receipt_retention,),
            )
            connection.execute("COMMIT")
            return IngestReceipt(
                applied=True,
                duplicate=False,
                supervisor_id=envelope.supervisor_id,
                generation=envelope.generation,
                sequence=envelope.sequence,
                revision=envelope.revision,
                event_id=envelope.event_id,
                idempotency_key=envelope.idempotency_key,
            )
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()
            self._enforce_private_files()

    def _existing_receipt(
        self,
        connection: sqlite3.Connection,
        envelope: ProjectionEnvelope,
        body_sha256: str,
    ) -> bool:
        event_row = connection.execute(
            "SELECT * FROM ingest_receipts WHERE event_id=?", (envelope.event_id,)
        ).fetchone()
        idempotency_row = connection.execute(
            "SELECT * FROM ingest_receipts WHERE idempotency_key=?", (envelope.idempotency_key,)
        ).fetchone()
        rows = [row for row in (event_row, idempotency_row) if row is not None]
        if not rows:
            return False
        expected = (
            envelope.event_id,
            envelope.idempotency_key,
            envelope.supervisor_id,
            envelope.generation,
            envelope.sequence,
            envelope.revision,
            body_sha256,
        )
        for row in rows:
            actual = (
                row["event_id"],
                row["idempotency_key"],
                row["supervisor_id"],
                int(row["generation"]),
                int(row["sequence"]),
                int(row["revision"]),
                row["body_sha256"],
            )
            if actual != expected:
                raise ProjectionConflictError(
                    "event_id or idempotency_key was already used for different content",
                    code="idempotency_conflict",
                )
        return True

    @staticmethod
    def _validate_monotonic_state(meta: sqlite3.Row | None, envelope: ProjectionEnvelope) -> None:
        if meta is None:
            # Every envelope is a complete snapshot.  A fresh/rebuilt hosted
            # copy can therefore bind at any authenticated positive coordinate;
            # after binding, strict +1 sequencing resumes below.
            return
        if envelope.supervisor_id != str(meta["supervisor_id"]):
            raise ProjectionConflictError("projection source supervisor does not match", code="supervisor_mismatch")
        current_generation = int(meta["generation"])
        current_sequence = int(meta["sequence"])
        current_revision = int(meta["revision"])
        if envelope.generation < current_generation:
            raise ProjectionConflictError("stale Supervisor generation", code="stale_generation")
        if envelope.generation > current_generation:
            if envelope.sequence != 1:
                raise ProjectionConflictError(
                    "newer Supervisor generation must begin at sequence 1",
                    code="generation_sequence_invalid",
                )
        else:
            if envelope.sequence <= current_sequence:
                raise ProjectionConflictError("stale or replayed sequence", code="stale_sequence")
            if envelope.sequence != current_sequence + 1:
                raise ProjectionConflictError("projection sequence gap", code="sequence_gap")
        if envelope.revision <= current_revision:
            raise ProjectionConflictError("stale projection revision", code="stale_revision")

    @staticmethod
    def _replace_projection(connection: sqlite3.Connection, envelope: ProjectionEnvelope) -> None:
        projection = envelope.projection
        connection.execute("DELETE FROM tasks")
        connection.executemany(
            "INSERT INTO tasks(task_id,revision,title,status,objective,active,accepted,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            [
                (
                    item["task_id"],
                    item["revision"],
                    item["title"],
                    item["status"],
                    item["objective"],
                    int(item["active"]),
                    int(item["accepted"]),
                    item["created_at"],
                    item["updated_at"],
                )
                for item in projection["tasks"]
            ],
        )
        connection.executemany(
            "INSERT INTO workstreams VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    item["workstream_id"],
                    item["task_id"],
                    item["revision"],
                    item["title"],
                    item["status"],
                    item["progress"],
                    item["remaining_range"],
                    item["delta"],
                    item["current_action"],
                    item["blocker"],
                    int(item["active"]),
                    item["updated_at"],
                )
                for item in projection["workstreams"]
            ],
        )
        connection.executemany(
            "INSERT INTO release_lanes VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    item["release_id"],
                    item["task_id"],
                    item["workstream_id"] or None,
                    item["revision"],
                    item["status"],
                    item["pr_url"],
                    item["pr_number"],
                    item["head_sha"],
                    item["merge_sha"],
                    item["environment"],
                    item["deploy_status"],
                    item["verification_status"],
                    item["updated_at"],
                )
                for item in projection["release_lanes"]
            ],
        )
        connection.executemany(
            "INSERT INTO incidents VALUES (?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    item["incident_id"],
                    item["task_id"],
                    item["workstream_id"] or None,
                    item["revision"],
                    item["status"],
                    item["fingerprint"],
                    item["summary"],
                    item["decision"],
                    item["attempt"],
                    item["updated_at"],
                )
                for item in projection["incidents"]
            ],
        )
        connection.executemany(
            "INSERT INTO attention VALUES (?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    item["attention_id"],
                    item["task_id"],
                    item["workstream_id"] or None,
                    item["revision"],
                    item["kind"],
                    item["status"],
                    item["summary"],
                    item["required_action"],
                    item["created_at"],
                    item["updated_at"],
                )
                for item in projection["attention"]
            ],
        )
        connection.executemany(
            "INSERT INTO acceptance VALUES (?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    item["acceptance_id"],
                    item["task_id"],
                    item["revision"],
                    item["status"],
                    int(item["technical_complete"]),
                    int(item["owner_accepted"]),
                    item["requested_at"],
                    item["accepted_at"],
                    item["summary"],
                    item["updated_at"],
                )
                for item in projection["acceptance"]
            ],
        )

    def health(self) -> dict[str, Any]:
        connection = self._connect()
        try:
            integrity = str(connection.execute("PRAGMA quick_check").fetchone()[0])
            meta = connection.execute("SELECT * FROM projection_meta WHERE singleton=1").fetchone()
            return {
                "status": "ready" if integrity == "ok" else "degraded",
                "schema_version": int(connection.execute("PRAGMA user_version").fetchone()[0]),
                "journal_mode": str(connection.execute("PRAGMA journal_mode").fetchone()[0]).lower(),
                "synchronous": _synchronous_name(int(connection.execute("PRAGMA synchronous").fetchone()[0])),
                "integrity": integrity,
                "bound": meta is not None,
                "last_seen": str(meta["received_at"]) if meta else None,
                "last_seen_epoch": float(meta["received_at_epoch"]) if meta else None,
                "source": _source_from_meta(meta),
                "rebuildable": True,
            }
        finally:
            connection.close()
            self._enforce_private_files()

    def public_state(self) -> dict[str, Any]:
        connection = self._connect()
        try:
            meta = connection.execute("SELECT * FROM projection_meta WHERE singleton=1").fetchone()
            active_tasks = connection.execute(
                "SELECT t.* FROM tasks t "
                "LEFT JOIN acceptance a ON a.task_id=t.task_id "
                "WHERE t.active=1 AND t.accepted=0 AND COALESCE(a.owner_accepted,0)=0 "
                "ORDER BY t.updated_at DESC, t.task_id"
            ).fetchall()
            tasks: list[dict[str, Any]] = []
            for task in active_tasks:
                task_id = str(task["task_id"])
                workstreams = [
                    dict(row)
                    for row in connection.execute(
                        "SELECT workstream_id,title,status,progress,remaining_range,delta,current_action,blocker,updated_at "
                        "FROM workstreams WHERE task_id=? AND active=1 ORDER BY updated_at DESC,workstream_id",
                        (task_id,),
                    )
                ]
                releases = [
                    dict(row)
                    for row in connection.execute(
                        "SELECT release_id,workstream_id,status,pr_url,pr_number,head_sha,merge_sha,environment,"
                        "deploy_status,verification_status,updated_at FROM release_lanes "
                        "WHERE task_id=? ORDER BY updated_at DESC,release_id",
                        (task_id,),
                    )
                ]
                incidents = [
                    dict(row)
                    for row in connection.execute(
                        "SELECT incident_id,workstream_id,status,fingerprint,summary,decision,attempt,updated_at "
                        "FROM incidents WHERE task_id=? AND status!='resolved' ORDER BY updated_at DESC,incident_id",
                        (task_id,),
                    )
                ]
                attention = [
                    dict(row)
                    for row in connection.execute(
                        "SELECT attention_id,workstream_id,kind,status,summary,required_action,created_at,updated_at "
                        "FROM attention WHERE task_id=? AND status IN ('pending','delivered') "
                        "ORDER BY created_at,attention_id",
                        (task_id,),
                    )
                ]
                acceptance_row = connection.execute(
                    "SELECT status,technical_complete,owner_accepted,requested_at,accepted_at,summary,updated_at "
                    "FROM acceptance WHERE task_id=?",
                    (task_id,),
                ).fetchone()
                tasks.append(
                    {
                        "task_id": task_id,
                        "title": str(task["title"]),
                        "status": str(task["status"]),
                        "objective": str(task["objective"]),
                        "updated_at": str(task["updated_at"]),
                        "workstreams": workstreams,
                        "release_lanes": releases,
                        "incidents": incidents,
                        "attention": attention,
                        "acceptance": dict(acceptance_row) if acceptance_row else None,
                    }
                )
            counts = {
                "active_tasks": len(tasks),
                "active_workstreams": int(
                    connection.execute("SELECT COUNT(*) FROM workstreams WHERE active=1").fetchone()[0]
                ),
                "pending_attention": int(
                    connection.execute("SELECT COUNT(*) FROM attention WHERE status IN ('pending','delivered')").fetchone()[0]
                ),
                "open_incidents": int(
                    connection.execute("SELECT COUNT(*) FROM incidents WHERE status!='resolved'").fetchone()[0]
                ),
                "awaiting_acceptance": int(
                    connection.execute("SELECT COUNT(*) FROM acceptance WHERE status='awaiting_owner'").fetchone()[0]
                ),
                "accepted_tasks": int(
                    connection.execute(
                        "SELECT COUNT(*) FROM tasks t LEFT JOIN acceptance a ON a.task_id=t.task_id "
                        "WHERE t.accepted=1 OR COALESCE(a.owner_accepted,0)=1"
                    ).fetchone()[0]
                ),
            }
            return {
                "contract": PROJECTION_CONTRACT,
                "service_role": "hosted_projection_v2",
                "control_authority": False,
                "mutation_routes_enabled": False,
                "rebuildable": True,
                "generated_at": _now_iso(),
                "last_seen": str(meta["received_at"]) if meta else None,
                "last_seen_epoch": float(meta["received_at_epoch"]) if meta else None,
                "source": _source_from_meta(meta),
                "counts": counts,
                "tasks": tasks,
            }
        finally:
            connection.close()
            self._enforce_private_files()

    def logical_digest(self) -> str:
        """Stable digest used by deterministic smokes to prove rejected calls do not write."""
        connection = self._connect()
        try:
            payload: dict[str, Any] = {}
            for table in (
                "projection_meta",
                "ingest_receipts",
                "tasks",
                "workstreams",
                "release_lanes",
                "incidents",
                "attention",
                "acceptance",
            ):
                rows = [dict(row) for row in connection.execute(f"SELECT * FROM {table} ORDER BY 1")]
                payload[table] = rows
            encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
            return hashlib.sha256(encoded).hexdigest()
        finally:
            connection.close()
            self._enforce_private_files()

    def _enforce_private_files(self) -> None:
        parent = self.path.parent.lstat()
        if (
            not stat.S_ISDIR(parent.st_mode)
            or parent.st_uid != os.geteuid()
            or stat.S_IMODE(parent.st_mode) != 0o700
        ):
            raise ProjectionStoreError(
                "projection database directory lost its private ownership",
                code="unsafe_database_path",
            )
        for path in (self.path, Path(str(self.path) + "-wal"), Path(str(self.path) + "-shm")):
            try:
                metadata = path.lstat()
            except FileNotFoundError:
                continue
            if (
                stat.S_ISLNK(metadata.st_mode)
                or not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.geteuid()
                or metadata.st_nlink != 1
            ):
                raise ProjectionStoreError(
                    "projection database file lost its private ownership",
                    code="unsafe_database_path",
                )
            path.chmod(0o600)


def projection_envelope_from_mapping(payload: Mapping[str, Any]) -> ProjectionEnvelope:
    expected = {
        "contract",
        "supervisor_id",
        "generation",
        "sequence",
        "revision",
        "event_id",
        "idempotency_key",
        "timestamp",
        "projection",
    }
    _exact_keys(payload, expected, "envelope")
    contract = _required_text(payload, "contract", 80)
    if contract != PROJECTION_CONTRACT:
        raise ProjectionValidationError("unsupported projection contract", code="contract_mismatch")
    envelope = ProjectionEnvelope(
        contract=contract,
        supervisor_id=_safe_id(payload.get("supervisor_id"), "supervisor_id"),
        generation=_positive_int(payload.get("generation"), "generation"),
        sequence=_positive_int(payload.get("sequence"), "sequence"),
        revision=_positive_int(payload.get("revision"), "revision"),
        event_id=_safe_id(payload.get("event_id"), "event_id"),
        idempotency_key=_safe_id(payload.get("idempotency_key"), "idempotency_key"),
        timestamp=_positive_int(payload.get("timestamp"), "timestamp"),
        projection=_normalize_projection(payload.get("projection")),
    )
    return envelope


def _normalize_projection(value: Any) -> Mapping[str, tuple[Mapping[str, Any], ...]]:
    if not isinstance(value, Mapping):
        raise ProjectionValidationError("projection must be an object")
    expected = set(MAX_ITEMS)
    _exact_keys(value, expected, "projection")
    normalizers: dict[str, Callable[[Mapping[str, Any]], Mapping[str, Any]]] = {
        "tasks": _normalize_task,
        "workstreams": _normalize_workstream,
        "release_lanes": _normalize_release,
        "incidents": _normalize_incident,
        "attention": _normalize_attention,
        "acceptance": _normalize_acceptance,
    }
    result: dict[str, tuple[Mapping[str, Any], ...]] = {}
    for name, normalizer in normalizers.items():
        raw_items = value.get(name)
        if not isinstance(raw_items, list):
            raise ProjectionValidationError(f"projection.{name} must be an array")
        if len(raw_items) > MAX_ITEMS[name]:
            raise ProjectionValidationError(f"projection.{name} exceeds item limit")
        items: list[Mapping[str, Any]] = []
        seen: set[str] = set()
        for raw in raw_items:
            if not isinstance(raw, Mapping):
                raise ProjectionValidationError(f"projection.{name} items must be objects")
            _ensure_sanitized(raw, f"projection.{name}")
            item = normalizer(raw)
            item_id = str(item[ENTITY_ID_FIELDS[name]])
            if item_id in seen:
                raise ProjectionValidationError(f"duplicate {name} id: {item_id}")
            seen.add(item_id)
            items.append(item)
        result[name] = tuple(items)
    _validate_relationships(result)
    return result


def _normalize_task(raw: Mapping[str, Any]) -> Mapping[str, Any]:
    _exact_keys(
        raw,
        {"task_id", "revision", "title", "status", "objective", "active", "accepted", "created_at", "updated_at"},
        "task",
    )
    status_value = _choice(raw.get("status"), TASK_STATUSES, "task.status")
    accepted = _boolean(raw.get("accepted"), "task.accepted")
    if accepted and status_value != "accepted":
        raise ProjectionValidationError("accepted task must use status=accepted")
    return {
        "task_id": _safe_id(raw.get("task_id"), "task_id"),
        "revision": _positive_int(raw.get("revision"), "task.revision"),
        "title": _required_text(raw, "title", 200),
        "status": status_value,
        "objective": _required_text(raw, "objective", 1_000),
        "active": _boolean(raw.get("active"), "task.active"),
        "accepted": accepted,
        "created_at": _timestamp_text(raw.get("created_at"), "task.created_at"),
        "updated_at": _timestamp_text(raw.get("updated_at"), "task.updated_at"),
    }


def _normalize_workstream(raw: Mapping[str, Any]) -> Mapping[str, Any]:
    _exact_keys(
        raw,
        {"workstream_id", "task_id", "revision", "title", "status", "progress", "remaining_range", "delta", "current_action", "blocker", "active", "updated_at"},
        "workstream",
    )
    status_value = _choice(raw.get("status"), WORKSTREAM_STATUSES, "workstream.status")
    blocker = _optional_text(raw.get("blocker"), "workstream.blocker", 500)
    if status_value == "blocked" and not blocker:
        raise ProjectionValidationError("blocked workstream requires a strict blocker")
    if status_value != "blocked" and blocker:
        raise ProjectionValidationError("workstream blocker is allowed only for status=blocked")
    progress = _bounded_int(raw.get("progress"), "workstream.progress", 5, 100)
    if status_value in {"completed", "awaiting_acceptance"} and progress != 100:
        raise ProjectionValidationError("completed/awaiting_acceptance workstream progress must be 100")
    return {
        "workstream_id": _safe_id(raw.get("workstream_id"), "workstream_id"),
        "task_id": _safe_id(raw.get("task_id"), "workstream.task_id"),
        "revision": _positive_int(raw.get("revision"), "workstream.revision"),
        "title": _required_text(raw, "title", 200),
        "status": status_value,
        "progress": progress,
        "remaining_range": _required_text(raw, "remaining_range", 80),
        "delta": _required_text(raw, "delta", 500),
        "current_action": _required_text(raw, "current_action", 500),
        "blocker": blocker,
        "active": _boolean(raw.get("active"), "workstream.active"),
        "updated_at": _timestamp_text(raw.get("updated_at"), "workstream.updated_at"),
    }


def _normalize_release(raw: Mapping[str, Any]) -> Mapping[str, Any]:
    _exact_keys(
        raw,
        {"release_id", "task_id", "workstream_id", "revision", "status", "pr_url", "pr_number", "head_sha", "merge_sha", "environment", "deploy_status", "verification_status", "updated_at"},
        "release_lane",
    )
    return {
        "release_id": _safe_id(raw.get("release_id"), "release_id"),
        "task_id": _safe_id(raw.get("task_id"), "release.task_id"),
        "workstream_id": _optional_id(raw.get("workstream_id"), "release.workstream_id"),
        "revision": _positive_int(raw.get("revision"), "release.revision"),
        "status": _choice(raw.get("status"), RELEASE_STATUSES, "release.status"),
        "pr_url": _https_url(raw.get("pr_url"), "release.pr_url"),
        "pr_number": _optional_positive_int(raw.get("pr_number"), "release.pr_number"),
        "head_sha": _optional_sha(raw.get("head_sha"), "release.head_sha"),
        "merge_sha": _optional_sha(raw.get("merge_sha"), "release.merge_sha"),
        "environment": _optional_text(raw.get("environment"), "release.environment", 80),
        "deploy_status": _optional_text(raw.get("deploy_status"), "release.deploy_status", 80),
        "verification_status": _optional_text(raw.get("verification_status"), "release.verification_status", 80),
        "updated_at": _timestamp_text(raw.get("updated_at"), "release.updated_at"),
    }


def _normalize_incident(raw: Mapping[str, Any]) -> Mapping[str, Any]:
    _exact_keys(
        raw,
        {"incident_id", "task_id", "workstream_id", "revision", "status", "fingerprint", "summary", "decision", "attempt", "updated_at"},
        "incident",
    )
    return {
        "incident_id": _safe_id(raw.get("incident_id"), "incident_id"),
        "task_id": _safe_id(raw.get("task_id"), "incident.task_id"),
        "workstream_id": _optional_id(raw.get("workstream_id"), "incident.workstream_id"),
        "revision": _positive_int(raw.get("revision"), "incident.revision"),
        "status": _choice(raw.get("status"), INCIDENT_STATUSES, "incident.status"),
        "fingerprint": _required_text(raw, "fingerprint", 128),
        "summary": _required_text(raw, "summary", 1_000),
        "decision": _optional_text(raw.get("decision"), "incident.decision", 1_000),
        "attempt": _bounded_int(raw.get("attempt"), "incident.attempt", 1, 5),
        "updated_at": _timestamp_text(raw.get("updated_at"), "incident.updated_at"),
    }


def _normalize_attention(raw: Mapping[str, Any]) -> Mapping[str, Any]:
    _exact_keys(
        raw,
        {"attention_id", "task_id", "workstream_id", "revision", "kind", "status", "summary", "required_action", "created_at", "updated_at"},
        "attention",
    )
    return {
        "attention_id": _safe_id(raw.get("attention_id"), "attention_id"),
        "task_id": _safe_id(raw.get("task_id"), "attention.task_id"),
        "workstream_id": _optional_id(raw.get("workstream_id"), "attention.workstream_id"),
        "revision": _positive_int(raw.get("revision"), "attention.revision"),
        "kind": _choice(raw.get("kind"), ATTENTION_KINDS, "attention.kind"),
        "status": _choice(raw.get("status"), ATTENTION_STATUSES, "attention.status"),
        "summary": _required_text(raw, "summary", 1_000),
        "required_action": _required_text(raw, "required_action", 500),
        "created_at": _timestamp_text(raw.get("created_at"), "attention.created_at"),
        "updated_at": _timestamp_text(raw.get("updated_at"), "attention.updated_at"),
    }


def _normalize_acceptance(raw: Mapping[str, Any]) -> Mapping[str, Any]:
    _exact_keys(
        raw,
        {"acceptance_id", "task_id", "revision", "status", "technical_complete", "owner_accepted", "requested_at", "accepted_at", "summary", "updated_at"},
        "acceptance",
    )
    status_value = _choice(raw.get("status"), ACCEPTANCE_STATUSES, "acceptance.status")
    technical_complete = _boolean(raw.get("technical_complete"), "acceptance.technical_complete")
    owner_accepted = _boolean(raw.get("owner_accepted"), "acceptance.owner_accepted")
    if owner_accepted != (status_value == "accepted"):
        raise ProjectionValidationError("owner_accepted must match acceptance status")
    if status_value in {"awaiting_owner", "accepted"} and not technical_complete:
        raise ProjectionValidationError("owner acceptance requires technical completion")
    return {
        "acceptance_id": _safe_id(raw.get("acceptance_id"), "acceptance_id"),
        "task_id": _safe_id(raw.get("task_id"), "acceptance.task_id"),
        "revision": _positive_int(raw.get("revision"), "acceptance.revision"),
        "status": status_value,
        "technical_complete": technical_complete,
        "owner_accepted": owner_accepted,
        "requested_at": _optional_timestamp_text(raw.get("requested_at"), "acceptance.requested_at"),
        "accepted_at": _optional_timestamp_text(raw.get("accepted_at"), "acceptance.accepted_at"),
        "summary": _required_text(raw, "summary", 1_000),
        "updated_at": _timestamp_text(raw.get("updated_at"), "acceptance.updated_at"),
    }


def _validate_relationships(projection: Mapping[str, tuple[Mapping[str, Any], ...]]) -> None:
    task_ids = {str(item["task_id"]) for item in projection["tasks"]}
    workstream_to_task = {
        str(item["workstream_id"]): str(item["task_id"]) for item in projection["workstreams"]
    }
    if len(task_ids) != len(projection["tasks"]):
        raise ProjectionValidationError("duplicate task_id")
    for item in projection["workstreams"]:
        if item["task_id"] not in task_ids:
            raise ProjectionValidationError("workstream references an unknown task")
    for name in ("release_lanes", "incidents", "attention"):
        for item in projection[name]:
            if item["task_id"] not in task_ids:
                raise ProjectionValidationError(f"{name} references an unknown task")
            workstream_id = str(item.get("workstream_id") or "")
            if workstream_id and workstream_to_task.get(workstream_id) != item["task_id"]:
                raise ProjectionValidationError(f"{name} references an unknown or cross-task workstream")
    acceptance_tasks: set[str] = set()
    for item in projection["acceptance"]:
        task_id = str(item["task_id"])
        if task_id not in task_ids:
            raise ProjectionValidationError("acceptance references an unknown task")
        if task_id in acceptance_tasks:
            raise ProjectionValidationError("task has multiple acceptance records")
        acceptance_tasks.add(task_id)


def _ensure_sanitized(value: Any, label: str) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key)
            if SECRET_KEY_RE.search(key_text):
                raise ProjectionValidationError(f"{label} contains a forbidden field", code="sanitized_payload_rejected")
            _ensure_sanitized(item, label)
    elif isinstance(value, list):
        for item in value:
            _ensure_sanitized(item, label)
    elif isinstance(value, str) and SECRET_VALUE_RE.search(value):
        raise ProjectionValidationError(f"{label} contains secret-like content", code="sanitized_payload_rejected")


def _exact_keys(payload: Mapping[str, Any], expected: set[str], label: str) -> None:
    actual = {str(key) for key in payload}
    missing = sorted(expected - actual)
    unknown = sorted(actual - expected)
    if missing or unknown:
        detail = []
        if missing:
            detail.append("missing=" + ",".join(missing))
        if unknown:
            detail.append("unknown=" + ",".join(unknown))
        raise ProjectionValidationError(f"{label} fields are invalid: {'; '.join(detail)}")


def _safe_id(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if not SAFE_ID_RE.fullmatch(text):
        raise ProjectionValidationError(f"{label} is not a safe identifier")
    return text


def _optional_id(value: Any, label: str) -> str:
    if value is None or str(value).strip() == "":
        return ""
    return _safe_id(value, label)


def _required_text(payload: Mapping[str, Any], key: str, limit: int) -> str:
    text = _clean_text(payload.get(key), f"{key}", limit)
    if not text:
        raise ProjectionValidationError(f"{key} must not be empty")
    return text


def _optional_text(value: Any, label: str, limit: int) -> str:
    return _clean_text(value, label, limit)


def _clean_text(value: Any, label: str, limit: int) -> str:
    text = " ".join(str(value or "").replace("\x00", " ").split())
    if len(text) > limit:
        raise ProjectionValidationError(f"{label} exceeds {limit} characters")
    if SECRET_VALUE_RE.search(text):
        raise ProjectionValidationError(f"{label} contains secret-like content", code="sanitized_payload_rejected")
    return text


def _positive_int(value: Any, label: str) -> int:
    return _bounded_int(value, label, 1, 2**63 - 1)


def _optional_positive_int(value: Any, label: str) -> int | None:
    if value is None or value == "":
        return None
    return _positive_int(value, label)


def _bounded_int(value: Any, label: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        raise ProjectionValidationError(f"{label} must be an integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ProjectionValidationError(f"{label} must be an integer") from exc
    if parsed < minimum or parsed > maximum:
        raise ProjectionValidationError(f"{label} is outside allowed range")
    return parsed


def _boolean(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise ProjectionValidationError(f"{label} must be a boolean")
    return value


def _choice(value: Any, choices: set[str], label: str) -> str:
    text = str(value or "").strip()
    if text not in choices:
        raise ProjectionValidationError(f"{label} is unsupported")
    return text


def _timestamp_text(value: Any, label: str) -> str:
    text = _optional_timestamp_text(value, label)
    if not text:
        raise ProjectionValidationError(f"{label} must not be empty")
    return text


def _optional_timestamp_text(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) > 40 or not re.fullmatch(r"[0-9TZ:+.\-]+", text):
        raise ProjectionValidationError(f"{label} is not a bounded timestamp")
    return text


def _https_url(value: Any, label: str) -> str:
    text = _optional_text(value, label, 500)
    if text and not text.startswith("https://"):
        raise ProjectionValidationError(f"{label} must use https")
    return text


def _optional_sha(value: Any, label: str) -> str:
    text = str(value or "").strip().lower()
    if text and not SHA_RE.fullmatch(text):
        raise ProjectionValidationError(f"{label} is not a commit SHA")
    return text


def _source_from_meta(meta: sqlite3.Row | None) -> dict[str, Any] | None:
    if meta is None:
        return None
    return {
        "supervisor_id": str(meta["supervisor_id"]),
        "generation": int(meta["generation"]),
        "sequence": int(meta["sequence"]),
        "revision": int(meta["revision"]),
        "last_event_id": str(meta["last_event_id"]),
        "source_timestamp": int(meta["source_timestamp"]),
    }


def _synchronous_name(value: int) -> str:
    return {0: "off", 1: "normal", 2: "full", 3: "extra"}.get(value, str(value))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def private_file_status(path: Path) -> dict[str, Any]:
    """Return sanitized permission diagnostics without reading file content."""
    raw = path.lstat()
    mode = stat.S_IMODE(raw.st_mode)
    return {
        "regular": stat.S_ISREG(raw.st_mode),
        "symlink": stat.S_ISLNK(raw.st_mode),
        "private": (mode & 0o077) == 0,
        "mode": f"{mode:04o}",
        "owner_matches_process": raw.st_uid == os.geteuid(),
    }
