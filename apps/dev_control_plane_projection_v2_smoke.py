"""Deterministic smoke coverage for the isolated hosted projection v2 service."""

from __future__ import annotations

import argparse
import ast
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from http import HTTPStatus
import json
import os
from pathlib import Path
import socket
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (SRC, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dev_control_plane.projection_server import (  # noqa: E402
    ProjectionServerConfigError,
    SignedMetadata,
    load_hmac_key,
    signed_headers,
)
from dev_control_plane.projection_store import (  # noqa: E402
    CURRENT_SCHEMA_VERSION,
    MIGRATIONS,
    PROJECTION_CONTRACT,
    ProjectionConflictError,
    ProjectionStore,
    ProjectionStoreError,
    projection_envelope_from_mapping,
)


CURATOR_THREAD_ID = "curator-thread-private-fixture"
SUPERVISOR_ID = "mac-supervisor-canary"
KEY = b"projection-v2-smoke-key-material-32-bytes-minimum"


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _projection(revision: int, *, phase: str = "working") -> dict[str, list[dict[str, Any]]]:
    now = _iso_now()
    if phase == "working":
        task_status = "working"
        workstream_status = "working"
        progress = 40
        task_active = True
        task_accepted = False
        workstream_active = True
        acceptance_status = "not_ready"
        technical_complete = False
        owner_accepted = False
        requested_at = ""
        accepted_at = ""
        attention_status = "pending"
    elif phase == "awaiting_owner":
        task_status = "awaiting_acceptance"
        workstream_status = "awaiting_acceptance"
        progress = 100
        task_active = True
        task_accepted = False
        workstream_active = True
        acceptance_status = "awaiting_owner"
        technical_complete = True
        owner_accepted = False
        requested_at = now
        accepted_at = ""
        attention_status = "pending"
    elif phase == "accepted":
        task_status = "accepted"
        workstream_status = "completed"
        progress = 100
        task_active = False
        task_accepted = True
        workstream_active = False
        acceptance_status = "accepted"
        technical_complete = True
        owner_accepted = True
        requested_at = now
        accepted_at = now
        attention_status = "resolved"
    else:
        raise AssertionError(f"unsupported fixture phase: {phase}")

    tasks = [
        {
            "task_id": "task-1",
            "revision": revision,
            "title": "Оркестратор Codex v2",
            "status": task_status,
            "objective": "Безопасный единственный локальный центр управления",
            "active": task_active,
            "accepted": task_accepted,
            "created_at": now,
            "updated_at": now,
        }
    ]
    workstreams = [
        {
            "workstream_id": "workstream-1",
            "task_id": "task-1",
            "revision": revision,
            "title": "Hosted read-only projection",
            "status": workstream_status,
            "progress": progress,
            "remaining_range": "30–60 мин" if phase == "working" else "0 мин",
            "delta": "Подписанная проекция сохранена транзакционно",
            "current_action": "Проверяется read-only граница",
            "blocker": "",
            "active": workstream_active,
            "updated_at": now,
        }
    ]
    release_lanes = [
        {
            "release_id": "release-1",
            "task_id": "task-1",
            "workstream_id": "workstream-1",
            "revision": revision,
            "status": "pr_open" if phase == "working" else "production",
            "pr_url": "https://github.com/orenvlad-ai/dev-control-plane/pull/123",
            "pr_number": 123,
            "head_sha": "a" * 40,
            "merge_sha": "" if phase == "working" else "b" * 40,
            "environment": "production",
            "deploy_status": "pending" if phase == "working" else "deployed",
            "verification_status": "pending" if phase == "working" else "passed",
            "updated_at": now,
        }
    ]
    incidents = [
        {
            "incident_id": "incident-1",
            "task_id": "task-1",
            "workstream_id": "workstream-1",
            "revision": revision,
            "status": "investigating" if phase == "working" else "resolved",
            "fingerprint": "projection-fixture",
            "summary": "Проверяется восстановление после потери сети",
            "decision": "" if phase == "working" else "Проверка завершена",
            "attempt": 1,
            "updated_at": now,
        }
    ]
    attention = [
        {
            "attention_id": "attention-1",
            "task_id": "task-1",
            "workstream_id": "workstream-1",
            "revision": revision,
            "kind": "acceptance",
            "status": attention_status,
            "summary": "После технического closure нужна приёмка владельца",
            "required_action": "Ответить ровно «Задача принята» после проверки",
            "created_at": now,
            "updated_at": now,
        }
    ]
    acceptance = [
        {
            "acceptance_id": "acceptance-1",
            "task_id": "task-1",
            "revision": revision,
            "status": acceptance_status,
            "technical_complete": technical_complete,
            "owner_accepted": owner_accepted,
            "requested_at": requested_at,
            "accepted_at": accepted_at,
            "summary": "Owner acceptance не выполняется автоматически",
            "updated_at": now,
        }
    ]

    if phase == "accepted":
        tasks.append(
            {
                "task_id": "task-2",
                "revision": revision,
                "title": "Следующая активная задача",
                "status": "working",
                "objective": "Доказать отсутствие шума от принятой задачи",
                "active": True,
                "accepted": False,
                "created_at": now,
                "updated_at": now,
            }
        )
        workstreams.append(
            {
                "workstream_id": "workstream-2",
                "task_id": "task-2",
                "revision": revision,
                "title": "Активный контур",
                "status": "working",
                "progress": 15,
                "remaining_range": "1–2 ч",
                "delta": "Новая задача зарегистрирована",
                "current_action": "Выполняется preflight",
                "blocker": "",
                "active": True,
                "updated_at": now,
            }
        )
        acceptance.append(
            {
                "acceptance_id": "acceptance-2",
                "task_id": "task-2",
                "revision": revision,
                "status": "not_ready",
                "technical_complete": False,
                "owner_accepted": False,
                "requested_at": "",
                "accepted_at": "",
                "summary": "Техническая работа продолжается",
                "updated_at": now,
            }
        )

    return {
        "tasks": tasks,
        "workstreams": workstreams,
        "release_lanes": release_lanes,
        "incidents": incidents,
        "attention": attention,
        "acceptance": acceptance,
    }


def _metadata(
    *,
    generation: int,
    sequence: int,
    revision: int,
    event_id: str,
    idempotency_key: str,
    timestamp: int | None = None,
    supervisor_id: str = SUPERVISOR_ID,
) -> SignedMetadata:
    return SignedMetadata(
        timestamp=int(time.time()) if timestamp is None else timestamp,
        supervisor_id=supervisor_id,
        generation=generation,
        sequence=sequence,
        revision=revision,
        event_id=event_id,
        idempotency_key=idempotency_key,
    )


def _body(metadata: SignedMetadata, projection: Mapping[str, Any]) -> bytes:
    payload = {
        "contract": PROJECTION_CONTRACT,
        "supervisor_id": metadata.supervisor_id,
        "generation": metadata.generation,
        "sequence": metadata.sequence,
        "revision": metadata.revision,
        "event_id": metadata.event_id,
        "idempotency_key": metadata.idempotency_key,
        "timestamp": metadata.timestamp,
        "projection": projection,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _http(
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    body: bytes | None = None,
    headers: Mapping[str, str] | None = None,
) -> tuple[int, Mapping[str, str], bytes]:
    request = Request(base_url + path, data=body, headers=dict(headers or {}), method=method)
    try:
        with urlopen(request, timeout=3) as response:
            return int(response.status), response.headers, response.read()
    except HTTPError as exc:
        return int(exc.code), exc.headers, exc.read()


def _json_response(result: tuple[int, Mapping[str, str], bytes]) -> tuple[int, dict[str, Any]]:
    status, _headers, raw = result
    decoded = json.loads(raw.decode("utf-8"))
    assert isinstance(decoded, dict)
    return status, decoded


def _post_signed(
    base_url: str,
    metadata: SignedMetadata,
    projection: Mapping[str, Any],
    *,
    signing_metadata: SignedMetadata | None = None,
    signing_body: bytes | None = None,
) -> tuple[int, dict[str, Any]]:
    body = _body(metadata, projection)
    headers = signed_headers(KEY, signing_body if signing_body is not None else body, signing_metadata or metadata)
    return _json_response(_http(base_url, "/api/v2/ingest", method="POST", body=body, headers=headers))


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_ready(base_url: str, process: subprocess.Popen[str]) -> dict[str, Any]:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if process.poll() is not None:
            stdout, stderr = process.communicate(timeout=1)
            raise AssertionError(f"projection server exited early: stdout={stdout!r} stderr={stderr!r}")
        try:
            status, payload = _json_response(_http(base_url, "/api/v2/health"))
            if status == HTTPStatus.OK:
                return payload
        except (URLError, ConnectionError, TimeoutError):
            pass
        time.sleep(0.05)
    raise AssertionError("projection server did not become ready")


def _assert_rejected_without_write(
    store: ProjectionStore,
    expected_digest: str,
    result: tuple[int, dict[str, Any]],
    *,
    expected_status: int,
    expected_reason: str,
) -> None:
    status, payload = result
    assert status == expected_status, (status, payload)
    assert payload.get("reason_code") == expected_reason, payload
    assert store.logical_digest() == expected_digest


def _assert_source_isolation() -> None:
    source_path = SRC / "dev_control_plane" / "projection_server.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    forbidden = {
        "dev_control_plane.server",
        "dev_control_plane.mcp_server",
        "dev_control_plane.execution",
        "dev_control_plane.target_production",
        "server",
        "mcp_server",
        "execution",
        "target_production",
    }
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    assert not imports.intersection(forbidden), imports.intersection(forbidden)


def _projection_rebuild_retention_smoke(temp: Path) -> None:
    database = temp / "rebuild-at-n" / "projection.sqlite3"
    store = ProjectionStore(database, receipt_retention=2)

    def ingest(metadata: SignedMetadata) -> object:
        projection = _projection(metadata.revision)
        body = _body(metadata, projection)
        envelope = projection_envelope_from_mapping(json.loads(body.decode("utf-8")))
        return store.ingest(
            envelope,
            body_sha256=hashlib.sha256(body).hexdigest(),
            received_at_epoch=float(metadata.timestamp),
        )

    baseline = _metadata(
        generation=7,
        sequence=37,
        revision=812,
        event_id="rebuild-at-n-37",
        idempotency_key="rebuild-at-n-idem-37",
    )
    receipt = ingest(baseline)
    if not receipt.applied or receipt.duplicate:
        raise AssertionError("fresh hosted projection did not bind an authenticated full snapshot at N")
    next_snapshot = _metadata(
        generation=7,
        sequence=38,
        revision=813,
        event_id="rebuild-at-n-38",
        idempotency_key="rebuild-at-n-idem-38",
    )
    if not ingest(next_snapshot).applied:
        raise AssertionError("hosted projection did not require/accept strict N+1 after rebuild binding")
    before_gap = store.logical_digest()
    gap = _metadata(
        generation=7,
        sequence=40,
        revision=814,
        event_id="rebuild-at-n-gap",
        idempotency_key="rebuild-at-n-idem-gap",
    )
    try:
        ingest(gap)
    except ProjectionConflictError as exc:
        if exc.code != "sequence_gap":
            raise AssertionError(f"unexpected rebuild gap reason: {exc.code}") from exc
    else:
        raise AssertionError("hosted projection accepted a sequence gap after rebuild binding")
    if store.logical_digest() != before_gap:
        raise AssertionError("rejected rebuild gap mutated hosted projection state")

    retained = _metadata(
        generation=7,
        sequence=39,
        revision=814,
        event_id="rebuild-at-n-39",
        idempotency_key="rebuild-at-n-idem-39",
    )
    if not ingest(retained).applied:
        raise AssertionError("hosted projection failed to apply the next retained snapshot")
    with sqlite3.connect(database) as connection:
        receipt_ids = tuple(
            row[0]
            for row in connection.execute("SELECT event_id FROM ingest_receipts ORDER BY rowid")
        )
    if receipt_ids != ("rebuild-at-n-38", "rebuild-at-n-39"):
        raise AssertionError(f"hosted receipt retention was not bounded: {receipt_ids}")

    # Once an old receipt is compacted, monotonic meta remains the replay
    # barrier. The old body must still be rejected without a write.
    compacted_replay_digest = store.logical_digest()
    try:
        ingest(baseline)
    except ProjectionConflictError as exc:
        if exc.code != "stale_sequence":
            raise AssertionError(f"unexpected compacted replay reason: {exc.code}") from exc
    else:
        raise AssertionError("compacted hosted receipt allowed a stale replay")
    if store.logical_digest() != compacted_replay_digest:
        raise AssertionError("compacted hosted replay mutated projection state")

    restored_path = temp / "rebuild-at-n-restored" / "projection.sqlite3"
    restored_path.parent.mkdir(parents=True)
    with sqlite3.connect(database) as source, sqlite3.connect(restored_path) as target:
        source.backup(target)
    restored = ProjectionStore(restored_path, receipt_retention=2)
    restored_meta = restored.health()["source"]
    if restored_meta != {
        "supervisor_id": SUPERVISOR_ID,
        "generation": 7,
        "sequence": 39,
        "revision": 814,
        "last_event_id": "rebuild-at-n-39",
        "source_timestamp": retained.timestamp,
    }:
        raise AssertionError(f"hosted backup/restore lost monotonic binding: {restored_meta}")
    restored_next = _metadata(
        generation=7,
        sequence=40,
        revision=815,
        event_id="rebuild-at-n-restored-40",
        idempotency_key="rebuild-at-n-restored-idem-40",
    )
    restored_body = _body(restored_next, _projection(restored_next.revision))
    restored_envelope = projection_envelope_from_mapping(json.loads(restored_body.decode("utf-8")))
    restored_receipt = restored.ingest(
        restored_envelope,
        body_sha256=hashlib.sha256(restored_body).hexdigest(),
        received_at_epoch=float(restored_next.timestamp),
    )
    if not restored_receipt.applied:
        raise AssertionError("restored hosted projection did not continue at strict N+1")
    with sqlite3.connect(restored_path) as connection:
        if int(connection.execute("SELECT COUNT(*) FROM ingest_receipts").fetchone()[0]) != 2:
            raise AssertionError("hosted receipt retention changed after backup/restore")


def _v2_curator_redaction_migration_smoke(temp: Path) -> None:
    legacy_root = temp / "projection-v2-upgrade"
    legacy_root.mkdir(mode=0o700)
    database = legacy_root / "projection.sqlite3"
    connection = sqlite3.connect(database)
    try:
        connection.execute(
            "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        for version, script in MIGRATIONS:
            if version > 2:
                break
            connection.executescript(script)
            connection.execute(
                "INSERT INTO schema_migrations(version,applied_at) VALUES (?,?)",
                (version, _iso_now()),
            )
            connection.execute(f"PRAGMA user_version={version}")
        now = _iso_now()
        connection.execute(
            "INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                "legacy-task",
                1,
                "Legacy projection task",
                "working",
                "Preserve non-private projection data",
                CURATOR_THREAD_ID,
                1,
                0,
                now,
                now,
            ),
        )
        connection.commit()
    finally:
        connection.close()
    database.chmod(0o600)

    upgraded = ProjectionStore(database)
    assert upgraded.health()["schema_version"] == CURRENT_SCHEMA_VERSION
    with sqlite3.connect(database) as readback:
        columns = {str(row[1]) for row in readback.execute("PRAGMA table_info(tasks)")}
        assert "curator_thread_id" not in columns
        row = readback.execute(
            "SELECT task_id,title,objective FROM tasks WHERE task_id='legacy-task'"
        ).fetchone()
        assert row == (
            "legacy-task",
            "Legacy projection task",
            "Preserve non-private projection data",
        )
        assert CURATOR_THREAD_ID not in json.dumps(
            list(readback.execute("SELECT * FROM tasks").fetchone()),
            ensure_ascii=False,
        )


def run_smoke() -> None:
    _assert_source_isolation()
    with tempfile.TemporaryDirectory(prefix="dcp-projection-v2-") as raw_temp:
        temp = Path(raw_temp)
        _projection_rebuild_retention_smoke(temp)
        _v2_curator_redaction_migration_smoke(temp)
        legacy = temp / "legacy-state.json"
        legacy.write_text('{"legacy":"preserve exactly"}\n', encoding="utf-8")
        legacy_before = hashlib.sha256(legacy.read_bytes()).hexdigest()

        key_file = temp / "projection.hmac"
        key_file.write_bytes(KEY + b"\n")
        key_file.chmod(0o600)
        assert load_hmac_key(key_file) == KEY
        insecure_key = temp / "insecure.hmac"
        insecure_key.write_bytes(KEY)
        insecure_key.chmod(0o644)
        try:
            load_hmac_key(insecure_key)
        except ProjectionServerConfigError:
            pass
        else:
            raise AssertionError("insecure HMAC key permissions were accepted")
        linked_key = temp / "linked.hmac"
        linked_alias = temp / "linked-alias.hmac"
        linked_key.write_bytes(KEY)
        linked_key.chmod(0o600)
        os.link(linked_key, linked_alias)
        try:
            load_hmac_key(linked_key)
        except ProjectionServerConfigError:
            pass
        else:
            raise AssertionError("hard-linked HMAC key was accepted")

        symlink_dir = temp / "projection-symlink"
        symlink_dir.mkdir(mode=0o700)
        symlink_target = temp / "must-remain-plain.txt"
        symlink_target.write_text("do-not-touch", encoding="utf-8")
        symlink_database = symlink_dir / "projection.sqlite3"
        symlink_database.symlink_to(symlink_target)
        try:
            ProjectionStore(symlink_database)
        except ProjectionStoreError as exc:
            assert exc.code == "unsafe_database_path"
        else:
            raise AssertionError("projection store followed a database symlink")
        assert symlink_target.read_text(encoding="utf-8") == "do-not-touch"

        database = temp / "projection-private" / "projection.sqlite3"
        port = _free_port()
        base_url = f"http://127.0.0.1:{port}"
        process = subprocess.Popen(
            [
                sys.executable,
                str(ROOT / "apps" / "dev_control_plane_projection_v2.py"),
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--database",
                str(database),
                "--hmac-key-file",
                str(key_file),
                "--max-skew-seconds",
                "30",
                "--stale-after-seconds",
                "1",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            initial_health = _wait_ready(base_url, process)
            assert initial_health["service_role"] == "hosted_projection_v2"
            assert initial_health["control_authority"] is False
            assert initial_health["mutation_routes_enabled"] is False
            assert initial_health["projection_ingestion_enabled"] is True
            assert initial_health["bound"] is False
            assert initial_health["stale"] is True
            assert initial_health["database"] == {
                "schema_version": CURRENT_SCHEMA_VERSION,
                "journal_mode": "wal",
                "synchronous": "full",
                "integrity": "ok",
                "rebuildable": True,
            }
            store = ProjectionStore(database)

            metadata_1 = _metadata(
                generation=7,
                sequence=1,
                revision=10,
                event_id="event-41",
                idempotency_key="idem-41",
            )
            body_1 = _body(metadata_1, _projection(10))
            assert CURATOR_THREAD_ID.encode("utf-8") not in body_1
            assert b'"curator_thread_id"' not in body_1
            status, ack = _json_response(
                _http(
                    base_url,
                    "/api/v2/ingest",
                    method="POST",
                    body=body_1,
                    headers=signed_headers(KEY, body_1, metadata_1),
                )
            )
            assert status == HTTPStatus.OK, ack
            assert set(ack) == {
                "status",
                "applied",
                "duplicate",
                "supervisor_id",
                "generation",
                "sequence",
                "revision",
                "event_id",
                "idempotency_key",
            }
            assert ack["status"] == "ack" and ack["applied"] is True and ack["duplicate"] is False
            assert not {"command", "instructions", "next_action", "control"}.intersection(ack)

            status, state = _json_response(_http(base_url, "/api/v2/state"))
            assert status == HTTPStatus.OK
            assert state["control_authority"] is False
            assert state["mutation_routes_enabled"] is False
            assert state["source"] == {
                "supervisor_id": SUPERVISOR_ID,
                "generation": 7,
                "sequence": 1,
                "revision": 10,
                "last_event_id": "event-41",
                "source_timestamp": metadata_1.timestamp,
            }
            assert state["counts"] == {
                "active_tasks": 1,
                "active_workstreams": 1,
                "pending_attention": 1,
                "open_incidents": 1,
                "awaiting_acceptance": 0,
                "accepted_tasks": 0,
            }
            task = state["tasks"][0]
            assert task["task_id"] == "task-1"
            public_state_text = json.dumps(state, ensure_ascii=False, sort_keys=True)
            assert CURATOR_THREAD_ID not in public_state_text
            assert "curator_thread_id" not in public_state_text
            assert len(task["workstreams"]) == 1
            assert len(task["release_lanes"]) == 1
            assert len(task["incidents"]) == 1
            assert len(task["attention"]) == 1
            assert task["acceptance"]["status"] == "not_ready"

            for dashboard_path in ("/", "/runs/live"):
                dashboard_status, dashboard_headers, dashboard_raw = _http(base_url, dashboard_path)
                dashboard = dashboard_raw.decode("utf-8")
                assert dashboard_status == HTTPStatus.OK
                assert dashboard_headers.get_content_type() == "text/html"
                for label in (
                    "Статус:",
                    "Задача:",
                    "Прогресс:",
                    "С прошлого отчёта:",
                    "Сейчас:",
                    "Выпуск:",
                    "Инцидент:",
                    "Требует внимания:",
                    "Приёмка:",
                    "last_seen",
                ):
                    assert label in dashboard, label
                assert "<pre" not in dashboard
                assert "fetch(" not in dashboard
                assert '"task_id"' not in dashboard
                assert "application/json" not in dashboard
                assert CURATOR_THREAD_ID not in dashboard

            duplicate_before = store.logical_digest()
            duplicate_status, duplicate_ack = _json_response(
                _http(
                    base_url,
                    "/api/v2/ingest",
                    method="POST",
                    body=body_1,
                    headers=signed_headers(KEY, body_1, metadata_1),
                )
            )
            assert duplicate_status == HTTPStatus.OK
            assert duplicate_ack["duplicate"] is True and duplicate_ack["applied"] is False
            assert store.logical_digest() == duplicate_before

            tampered = json.loads(body_1.decode("utf-8"))
            tampered["projection"]["tasks"][0]["title"] = "Подменённая задача"
            tampered_body = json.dumps(tampered, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
            _assert_rejected_without_write(
                store,
                duplicate_before,
                _json_response(
                    _http(
                        base_url,
                        "/api/v2/ingest",
                        method="POST",
                        body=tampered_body,
                        headers=signed_headers(KEY, body_1, metadata_1),
                    )
                ),
                expected_status=HTTPStatus.UNAUTHORIZED,
                expected_reason="invalid_signature",
            )

            stale_time = _metadata(
                generation=7,
                sequence=2,
                revision=11,
                event_id="event-stale-time",
                idempotency_key="idem-stale-time",
                timestamp=int(time.time()) - 120,
            )
            _assert_rejected_without_write(
                store,
                duplicate_before,
                _post_signed(base_url, stale_time, _projection(11)),
                expected_status=HTTPStatus.UNAUTHORIZED,
                expected_reason="timestamp_out_of_range",
            )

            body_metadata = _metadata(
                generation=7,
                sequence=2,
                revision=11,
                event_id="event-metadata-body",
                idempotency_key="idem-metadata-body",
            )
            header_metadata = _metadata(
                generation=7,
                sequence=2,
                revision=12,
                event_id="event-metadata-header",
                idempotency_key="idem-metadata-header",
                timestamp=body_metadata.timestamp,
            )
            mismatch_body = _body(body_metadata, _projection(11))
            _assert_rejected_without_write(
                store,
                duplicate_before,
                _json_response(
                    _http(
                        base_url,
                        "/api/v2/ingest",
                        method="POST",
                        body=mismatch_body,
                        headers=signed_headers(KEY, mismatch_body, header_metadata),
                    )
                ),
                expected_status=HTTPStatus.BAD_REQUEST,
                expected_reason="metadata_mismatch",
            )

            conflict_cases = (
                (
                    _metadata(
                        generation=7,
                        sequence=2,
                        revision=11,
                        event_id="event-idem-conflict",
                        idempotency_key="idem-41",
                    ),
                    HTTPStatus.CONFLICT,
                    "idempotency_conflict",
                ),
                (
                    _metadata(
                        generation=7,
                        sequence=1,
                        revision=11,
                        event_id="event-replay",
                        idempotency_key="idem-replay",
                    ),
                    HTTPStatus.CONFLICT,
                    "stale_sequence",
                ),
                (
                    _metadata(
                        generation=7,
                        sequence=3,
                        revision=11,
                        event_id="event-gap",
                        idempotency_key="idem-gap",
                    ),
                    HTTPStatus.CONFLICT,
                    "sequence_gap",
                ),
                (
                    _metadata(
                        generation=7,
                        sequence=2,
                        revision=10,
                        event_id="event-old-revision",
                        idempotency_key="idem-old-revision",
                    ),
                    HTTPStatus.CONFLICT,
                    "stale_revision",
                ),
                (
                    _metadata(
                        generation=6,
                        sequence=2,
                        revision=11,
                        event_id="event-old-generation",
                        idempotency_key="idem-old-generation",
                    ),
                    HTTPStatus.CONFLICT,
                    "stale_generation",
                ),
                (
                    _metadata(
                        generation=8,
                        sequence=2,
                        revision=11,
                        event_id="event-successor-sequence",
                        idempotency_key="idem-successor-sequence",
                    ),
                    HTTPStatus.CONFLICT,
                    "generation_sequence_invalid",
                ),
                (
                    _metadata(
                        generation=7,
                        sequence=2,
                        revision=11,
                        event_id="event-supervisor-mismatch",
                        idempotency_key="idem-supervisor-mismatch",
                        supervisor_id="different-supervisor",
                    ),
                    HTTPStatus.CONFLICT,
                    "supervisor_mismatch",
                ),
            )
            for candidate, expected_status, expected_reason in conflict_cases:
                _assert_rejected_without_write(
                    store,
                    duplicate_before,
                    _post_signed(base_url, candidate, _projection(candidate.revision)),
                    expected_status=expected_status,
                    expected_reason=expected_reason,
                )

            secret_metadata = _metadata(
                generation=7,
                sequence=2,
                revision=11,
                event_id="event-secret-like",
                idempotency_key="idem-secret-like",
            )
            secret_projection = deepcopy(_projection(11))
            secret_projection["tasks"][0]["objective"] = "password=must-not-cross-boundary"
            _assert_rejected_without_write(
                store,
                duplicate_before,
                _post_signed(base_url, secret_metadata, secret_projection),
                expected_status=HTTPStatus.UNPROCESSABLE_ENTITY,
                expected_reason="sanitized_payload_rejected",
            )

            before_legacy_denials = store.logical_digest()
            denied_paths = (
                "/mcp",
                "/mcp/stream",
                "/oauth/register",
                "/oauth/token",
                "/oauth/authorize",
                "/api/task-specs",
                "/api/runtime-config",
                "/api/runs/example/cancel",
                "/api/target-production/plan",
                "/api/v2/unknown",
            )
            for path in denied_paths:
                denied_status, denied = _json_response(
                    _http(
                        base_url,
                        path,
                        method="POST",
                        body=b"{}",
                        headers={"Content-Type": "application/json"},
                    )
                )
                assert denied_status == HTTPStatus.METHOD_NOT_ALLOWED, (path, denied_status, denied)
                assert denied["reason_code"] == "hosted_projection_read_only"
            for method in ("PUT", "PATCH", "DELETE", "OPTIONS"):
                denied_status, denied = _json_response(
                    _http(base_url, "/api/v2/ingest", method=method, body=b"{}")
                )
                assert denied_status == HTTPStatus.METHOD_NOT_ALLOWED
                assert denied["reason_code"] == "hosted_projection_read_only"
            assert store.logical_digest() == before_legacy_denials

            # Source time is immutable and may be far outside transport skew after
            # an offline period.  A fresh signed header time admits the exact body;
            # an ACK-loss retry keeps that body/idempotency digest and signs a new
            # fresh header timestamp, so the store returns an exact duplicate ACK.
            offline_body_metadata = _metadata(
                generation=7,
                sequence=2,
                revision=11,
                event_id="event-offline-replay",
                idempotency_key="idem-offline-replay",
                timestamp=int(time.time()) - 3_600,
            )
            offline_body = _body(offline_body_metadata, _projection(11))
            fresh_header = _metadata(
                generation=7,
                sequence=2,
                revision=11,
                event_id="event-offline-replay",
                idempotency_key="idem-offline-replay",
                timestamp=int(time.time()),
            )
            offline_status, offline_ack = _json_response(
                _http(
                    base_url,
                    "/api/v2/ingest",
                    method="POST",
                    body=offline_body,
                    headers=signed_headers(KEY, offline_body, fresh_header),
                )
            )
            assert offline_status == HTTPStatus.OK and offline_ack["applied"] is True
            after_offline_apply = store.logical_digest()
            retry_header = _metadata(
                generation=7,
                sequence=2,
                revision=11,
                event_id="event-offline-replay",
                idempotency_key="idem-offline-replay",
                timestamp=int(time.time()),
            )
            retry_status, retry_ack = _json_response(
                _http(
                    base_url,
                    "/api/v2/ingest",
                    method="POST",
                    body=offline_body,
                    headers=signed_headers(KEY, offline_body, retry_header),
                )
            )
            assert retry_status == HTTPStatus.OK
            assert retry_ack["duplicate"] is True and retry_ack["applied"] is False
            assert store.logical_digest() == after_offline_apply

            successor = _metadata(
                generation=11,
                sequence=1,
                revision=12,
                event_id="event-successor",
                idempotency_key="idem-successor",
            )
            successor_status, successor_ack = _post_signed(
                base_url, successor, _projection(12, phase="awaiting_owner")
            )
            assert successor_status == HTTPStatus.OK, successor_ack
            assert successor_ack["applied"] is True
            status, awaiting_state = _json_response(_http(base_url, "/api/v2/state"))
            assert status == HTTPStatus.OK
            assert awaiting_state["source"]["generation"] == 11
            assert awaiting_state["source"]["sequence"] == 1
            assert awaiting_state["counts"]["awaiting_acceptance"] == 1
            assert awaiting_state["tasks"][0]["acceptance"]["owner_accepted"] == 0

            accepted = _metadata(
                generation=11,
                sequence=2,
                revision=13,
                event_id="event-accepted",
                idempotency_key="idem-accepted",
            )
            accepted_status, accepted_ack = _post_signed(
                base_url, accepted, _projection(13, phase="accepted")
            )
            assert accepted_status == HTTPStatus.OK, accepted_ack
            status, final_state = _json_response(_http(base_url, "/api/v2/state"))
            assert status == HTTPStatus.OK
            assert final_state["counts"]["accepted_tasks"] == 1
            assert final_state["counts"]["active_tasks"] == 1
            assert [item["task_id"] for item in final_state["tasks"]] == ["task-2"]
            final_dashboard = _http(base_url, "/")[2].decode("utf-8")
            assert "Следующая активная задача" in final_dashboard
            assert "Оркестратор Codex v2" not in final_dashboard

            connection = sqlite3.connect(database)
            try:
                assert str(connection.execute("PRAGMA journal_mode").fetchone()[0]).lower() == "wal"
                assert int(connection.execute("PRAGMA synchronous").fetchone()[0]) == 2
                assert int(connection.execute("PRAGMA user_version").fetchone()[0]) == CURRENT_SCHEMA_VERSION
                assert str(connection.execute("PRAGMA quick_check").fetchone()[0]) == "ok"
                task_columns = {
                    str(row[1])
                    for row in connection.execute("PRAGMA table_info(tasks)")
                }
                assert "curator_thread_id" not in task_columns
                tables = {
                    str(row[0])
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                    )
                }
                assert {
                    "schema_migrations",
                    "projection_meta",
                    "ingest_receipts",
                    "tasks",
                    "workstreams",
                    "release_lanes",
                    "incidents",
                    "attention",
                    "acceptance",
                }.issubset(tables)
            finally:
                connection.close()
            assert stat.S_IMODE(database.parent.stat().st_mode) == 0o700
            for private_path in (database, Path(str(database) + "-wal"), Path(str(database) + "-shm")):
                if private_path.exists():
                    assert stat.S_IMODE(private_path.stat().st_mode) == 0o600

            time.sleep(2.1)
            stale_status, stale_health = _json_response(_http(base_url, "/api/v2/health"))
            assert stale_status == HTTPStatus.OK
            assert stale_health["stale"] is True
            assert stale_health["last_seen_age_seconds"] >= 2

            assert hashlib.sha256(legacy.read_bytes()).hexdigest() == legacy_before
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            stdout, stderr = process.communicate(timeout=1)
            assert "hosted_projection_v2" in stdout, stdout
            assert stderr == "", stderr


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Smoke-test hosted projection v2")
    parser.parse_args(argv)
    run_smoke()
    print("dev-control-plane-projection-v2-smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
