"""Loopback-only, read-only hosted projection server for Supervisor v2.

The sole state-changing route is authenticated projection ingestion.  This
module intentionally has no dependency on the legacy cockpit, MCP, executor,
or target-production implementations.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from hmac import compare_digest, new as hmac_new
from html import escape
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import stat
import sys
import time
from typing import Any, Mapping
from urllib.parse import urlsplit

from .projection_store import (
    PROJECTION_CONTRACT,
    IngestReceipt,
    ProjectionConflictError,
    ProjectionStore,
    ProjectionStoreError,
    ProjectionValidationError,
    projection_envelope_from_mapping,
)


SERVICE_ROLE = "hosted_projection_v2"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8771
DEFAULT_DATABASE = Path("/tmp/development-control-plane-projection-v2/projection.sqlite3")
HOST_ENV = "DEV_CONTROL_PLANE_PROJECTION_V2_HOST"
PORT_ENV = "DEV_CONTROL_PLANE_PROJECTION_V2_PORT"
DATABASE_ENV = "DEV_CONTROL_PLANE_PROJECTION_V2_DB"
HMAC_KEY_FILE_ENV = "DEV_CONTROL_PLANE_PROJECTION_V2_HMAC_KEY_FILE"
MAX_SKEW_ENV = "DEV_CONTROL_PLANE_PROJECTION_V2_MAX_SKEW_SECONDS"
STALE_AFTER_ENV = "DEV_CONTROL_PLANE_PROJECTION_V2_STALE_AFTER_SECONDS"
INGEST_PATH = "/api/v2/ingest"
MAX_BODY_BYTES = 1_000_000
SIGNATURE_VERSION = "DCP-PROJECTION-V2"
SAFE_HEADER_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
SIGNATURE_RE = re.compile(r"^sha256=([0-9a-f]{64})$")

HEADER_TIMESTAMP = "X-DCP-Timestamp"
HEADER_SUPERVISOR = "X-DCP-Supervisor-ID"
HEADER_GENERATION = "X-DCP-Generation"
HEADER_SEQUENCE = "X-DCP-Sequence"
HEADER_REVISION = "X-DCP-Revision"
HEADER_EVENT = "X-DCP-Event-ID"
HEADER_IDEMPOTENCY = "X-DCP-Idempotency-Key"
HEADER_SIGNATURE = "X-DCP-Signature"


class ProjectionServerConfigError(ValueError):
    pass


class ProjectionSecurityError(ValueError):
    def __init__(self, message: str, *, code: str, status: HTTPStatus = HTTPStatus.UNAUTHORIZED) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class ProjectionServerConfig:
    host: str
    port: int
    database_path: Path
    hmac_key_file: Path
    max_skew_seconds: int = 300
    stale_after_seconds: int = 120


@dataclass(frozen=True)
class SignedMetadata:
    timestamp: int
    supervisor_id: str
    generation: int
    sequence: int
    revision: int
    event_id: str
    idempotency_key: str


class ProjectionHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, config: ProjectionServerConfig) -> None:
        if config.host != DEFAULT_HOST:
            raise ProjectionServerConfigError("projection v2 server must bind only to 127.0.0.1")
        self.config = config
        self.key = load_hmac_key(config.hmac_key_file)
        self.store = ProjectionStore(config.database_path)
        super().__init__((config.host, config.port), ProjectionRequestHandler)


class ProjectionRequestHandler(BaseHTTPRequestHandler):
    server: ProjectionHTTPServer

    def do_GET(self) -> None:  # noqa: N802
        path = _request_path(self.path)
        if path == "/api/v2/health":
            self._send_json(self._health_payload())
            return
        if path == "/api/v2/state":
            self._send_json(self._state_payload())
            return
        if path in {"/", "/runs/live"}:
            self._send_html(render_dashboard(self._state_payload()))
            return
        if path == "/favicon.ico":
            self._send_empty(HTTPStatus.NO_CONTENT)
            return
        self._send_json(
            {"status": "not_found", "reason_code": "route_not_found"},
            status=HTTPStatus.NOT_FOUND,
        )

    def do_POST(self) -> None:  # noqa: N802
        path = _request_path(self.path)
        if path != INGEST_PATH:
            self._send_json(
                {
                    "status": "denied",
                    "reason_code": "hosted_projection_read_only",
                    "service_role": SERVICE_ROLE,
                },
                status=HTTPStatus.METHOD_NOT_ALLOWED,
                extra_headers={"Allow": "GET"},
            )
            return
        try:
            body = self._read_bounded_json_body()
            metadata, body_digest = verify_signed_request(
                key=self.server.key,
                body=body,
                headers=self.headers,
                now_epoch=time.time(),
                max_skew_seconds=self.server.config.max_skew_seconds,
            )
            try:
                raw = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ProjectionSecurityError(
                    "signed request body is not valid JSON",
                    code="invalid_json",
                    status=HTTPStatus.BAD_REQUEST,
                ) from exc
            if not isinstance(raw, Mapping):
                raise ProjectionSecurityError(
                    "signed request body must be an object",
                    code="invalid_json_shape",
                    status=HTTPStatus.BAD_REQUEST,
                )
            envelope = projection_envelope_from_mapping(raw)
            _require_metadata_match(metadata, envelope)
            receipt = self.server.store.ingest(envelope, body_sha256=body_digest)
            self._send_json(_ack_payload(receipt))
        except ProjectionSecurityError as exc:
            self._send_json(
                {"status": "rejected", "reason_code": exc.code},
                status=exc.status,
            )
        except ProjectionValidationError as exc:
            self._send_json(
                {"status": "rejected", "reason_code": exc.code},
                status=HTTPStatus.UNPROCESSABLE_ENTITY,
            )
        except ProjectionConflictError as exc:
            self._send_json(
                {"status": "rejected", "reason_code": exc.code},
                status=HTTPStatus.CONFLICT,
            )
        except ProjectionStoreError:
            self._send_json(
                {"status": "error", "reason_code": "projection_store_unavailable"},
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )
        except Exception:
            self._send_json(
                {"status": "error", "reason_code": "unexpected_projection_error"},
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def do_PUT(self) -> None:  # noqa: N802
        self._method_denied()

    def do_PATCH(self) -> None:  # noqa: N802
        self._method_denied()

    def do_DELETE(self) -> None:  # noqa: N802
        self._method_denied()

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._method_denied()

    def _method_denied(self) -> None:
        self._send_json(
            {"status": "denied", "reason_code": "hosted_projection_read_only", "service_role": SERVICE_ROLE},
            status=HTTPStatus.METHOD_NOT_ALLOWED,
            extra_headers={"Allow": "GET, POST"},
        )

    def _read_bounded_json_body(self) -> bytes:
        if self.headers.get("Transfer-Encoding") is not None:
            raise ProjectionSecurityError(
                "transfer encoding is not accepted for signed ingestion",
                code="transfer_encoding_rejected",
                status=HTTPStatus.BAD_REQUEST,
            )
        content_type = str(self.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            raise ProjectionSecurityError(
                "ingestion requires application/json",
                code="content_type_required",
                status=HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
            )
        content_lengths = self.headers.get_all("Content-Length") or []
        if len(content_lengths) != 1 or "," in content_lengths[0]:
            raise ProjectionSecurityError(
                "one unambiguous Content-Length is required",
                code="content_length_required",
                status=HTTPStatus.LENGTH_REQUIRED,
            )
        raw_length = str(content_lengths[0]).strip()
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise ProjectionSecurityError(
                "valid Content-Length is required",
                code="content_length_required",
                status=HTTPStatus.LENGTH_REQUIRED,
            ) from exc
        if length <= 0:
            raise ProjectionSecurityError(
                "request body is required",
                code="empty_body",
                status=HTTPStatus.BAD_REQUEST,
            )
        if length > MAX_BODY_BYTES:
            raise ProjectionSecurityError(
                "request body exceeds projection limit",
                code="body_too_large",
                status=HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
            )
        body = self.rfile.read(length)
        if len(body) != length:
            raise ProjectionSecurityError(
                "request body was truncated",
                code="truncated_body",
                status=HTTPStatus.BAD_REQUEST,
            )
        return body

    def _health_payload(self) -> dict[str, Any]:
        health = self.server.store.health()
        stale = _stale_status(health.get("last_seen_epoch"), self.server.config.stale_after_seconds)
        return {
            "status": health["status"],
            "service_role": SERVICE_ROLE,
            "control_authority": False,
            "mutation_routes_enabled": False,
            "projection_ingestion_enabled": True,
            "database": {
                "schema_version": health["schema_version"],
                "journal_mode": health["journal_mode"],
                "synchronous": health["synchronous"],
                "integrity": health["integrity"],
                "rebuildable": True,
            },
            "bound": health["bound"],
            "last_seen": health["last_seen"],
            "stale": stale["stale"],
            "last_seen_age_seconds": stale["age_seconds"],
            "source": health["source"],
        }

    def _state_payload(self) -> dict[str, Any]:
        state = self.server.store.public_state()
        stale = _stale_status(state.get("last_seen_epoch"), self.server.config.stale_after_seconds)
        state.pop("last_seen_epoch", None)
        state["stale"] = stale["stale"]
        state["last_seen_age_seconds"] = stale["age_seconds"]
        return state

    def _send_json(
        self,
        payload: Mapping[str, Any],
        *,
        status: HTTPStatus = HTTPStatus.OK,
        extra_headers: Mapping[str, str] | None = None,
    ) -> None:
        body = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self._security_headers(content_type="application/json; charset=utf-8")
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self._security_headers(content_type="text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_empty(self, status: HTTPStatus) -> None:
        self.send_response(status)
        self._security_headers(content_type="text/plain; charset=utf-8")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _security_headers(self, *, content_type: str) -> None:
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'",
        )

    def log_message(self, format: str, *args: object) -> None:
        return


def build_server(config: ProjectionServerConfig) -> ProjectionHTTPServer:
    return ProjectionHTTPServer(config)


def load_hmac_key(path: Path | str) -> bytes:
    key_path = Path(path).expanduser()
    try:
        metadata = key_path.lstat()
    except OSError as exc:
        raise ProjectionServerConfigError("projection HMAC key file is unavailable") from exc
    mode = stat.S_IMODE(metadata.st_mode)
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise ProjectionServerConfigError("projection HMAC key must be a regular non-symlink file")
    if mode != 0o600 or metadata.st_nlink != 1:
        raise ProjectionServerConfigError("projection HMAC key file must be one private 0600 file")
    if metadata.st_uid != os.geteuid() and os.geteuid() != 0:
        raise ProjectionServerConfigError("projection HMAC key file owner does not match service user")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(key_path, flags)
        try:
            opened = os.fstat(descriptor)
            key = os.read(descriptor, 4097).rstrip(b"\r\n")
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise ProjectionServerConfigError("projection HMAC key could not be read safely") from exc
    if (
        opened.st_dev != metadata.st_dev
        or opened.st_ino != metadata.st_ino
        or not stat.S_ISREG(opened.st_mode)
        or stat.S_IMODE(opened.st_mode) != 0o600
        or opened.st_uid != metadata.st_uid
        or opened.st_nlink != 1
        or opened.st_size != metadata.st_size
    ):
        raise ProjectionServerConfigError("projection HMAC key changed during secure read")
    if len(key) < 32 or len(key) > 4096:
        raise ProjectionServerConfigError("projection HMAC key must contain 32-4096 bytes")
    return key


def verify_signed_request(
    *,
    key: bytes,
    body: bytes,
    headers: Mapping[str, str],
    now_epoch: float,
    max_skew_seconds: int,
) -> tuple[SignedMetadata, str]:
    metadata = SignedMetadata(
        timestamp=_header_positive_int(headers, HEADER_TIMESTAMP),
        supervisor_id=_header_safe_id(headers, HEADER_SUPERVISOR),
        generation=_header_positive_int(headers, HEADER_GENERATION),
        sequence=_header_positive_int(headers, HEADER_SEQUENCE),
        revision=_header_positive_int(headers, HEADER_REVISION),
        event_id=_header_safe_id(headers, HEADER_EVENT),
        idempotency_key=_header_safe_id(headers, HEADER_IDEMPOTENCY),
    )
    signature_header = str(headers.get(HEADER_SIGNATURE) or "").strip()
    match = SIGNATURE_RE.fullmatch(signature_header)
    if not match:
        raise ProjectionSecurityError("signature header is missing or invalid", code="invalid_signature")
    if abs(float(now_epoch) - metadata.timestamp) > max_skew_seconds:
        raise ProjectionSecurityError("signed timestamp is outside allowed skew", code="timestamp_out_of_range")
    body_digest = sha256(body).hexdigest()
    expected = hmac_new(key, canonical_signature_payload(metadata, body_digest), "sha256").hexdigest()
    if not compare_digest(match.group(1), expected):
        raise ProjectionSecurityError("request signature does not match", code="invalid_signature")
    return metadata, body_digest


def canonical_signature_payload(metadata: SignedMetadata, body_sha256: str) -> bytes:
    values = (
        SIGNATURE_VERSION,
        "POST",
        INGEST_PATH,
        str(metadata.timestamp),
        metadata.supervisor_id,
        str(metadata.generation),
        str(metadata.sequence),
        str(metadata.revision),
        metadata.event_id,
        metadata.idempotency_key,
        body_sha256,
    )
    return ("\n".join(values) + "\n").encode("utf-8")


def signed_headers(key: bytes, body: bytes, metadata: SignedMetadata) -> dict[str, str]:
    """Build exact transport headers; useful to the local outbound adapter and smokes."""
    body_digest = sha256(body).hexdigest()
    signature = hmac_new(key, canonical_signature_payload(metadata, body_digest), "sha256").hexdigest()
    return {
        "Content-Type": "application/json",
        HEADER_TIMESTAMP: str(metadata.timestamp),
        HEADER_SUPERVISOR: metadata.supervisor_id,
        HEADER_GENERATION: str(metadata.generation),
        HEADER_SEQUENCE: str(metadata.sequence),
        HEADER_REVISION: str(metadata.revision),
        HEADER_EVENT: metadata.event_id,
        HEADER_IDEMPOTENCY: metadata.idempotency_key,
        HEADER_SIGNATURE: "sha256=" + signature,
    }


def _require_metadata_match(metadata: SignedMetadata, envelope: Any) -> None:
    # The signed header timestamp is transport freshness.  The body timestamp is
    # immutable source time and intentionally survives offline/ACK-loss replay so
    # the body digest and idempotency receipt remain exact.  Every authority and
    # ordering field is still bound header-to-body below.
    expected = asdict(metadata)
    expected.pop("timestamp", None)
    actual = {
        "supervisor_id": envelope.supervisor_id,
        "generation": envelope.generation,
        "sequence": envelope.sequence,
        "revision": envelope.revision,
        "event_id": envelope.event_id,
        "idempotency_key": envelope.idempotency_key,
    }
    if actual != expected:
        raise ProjectionSecurityError(
            "signed transport metadata does not match body envelope",
            code="metadata_mismatch",
            status=HTTPStatus.BAD_REQUEST,
        )


def _ack_payload(receipt: IngestReceipt) -> dict[str, Any]:
    return {
        "status": "ack",
        "applied": receipt.applied,
        "duplicate": receipt.duplicate,
        "supervisor_id": receipt.supervisor_id,
        "generation": receipt.generation,
        "sequence": receipt.sequence,
        "revision": receipt.revision,
        "event_id": receipt.event_id,
        "idempotency_key": receipt.idempotency_key,
    }


def render_dashboard(state: Mapping[str, Any]) -> str:
    stale = bool(state.get("stale"))
    last_seen = escape(str(state.get("last_seen") or "нет данных"))
    age = state.get("last_seen_age_seconds")
    age_text = "—" if age is None else f"≈{int(age)} сек"
    tasks = state.get("tasks") if isinstance(state.get("tasks"), list) else []
    cards: list[str] = []
    for task in tasks:
        if not isinstance(task, Mapping):
            continue
        title = escape(str(task.get("title") or "Задача"))
        task_id = escape(str(task.get("task_id") or ""))
        releases = task.get("release_lanes") if isinstance(task.get("release_lanes"), list) else []
        incidents = task.get("incidents") if isinstance(task.get("incidents"), list) else []
        attention = task.get("attention") if isinstance(task.get("attention"), list) else []
        acceptance = task.get("acceptance") if isinstance(task.get("acceptance"), Mapping) else None
        release_html = _release_html(releases)
        incident_html = _incident_html(incidents)
        attention_html = _attention_html(attention)
        acceptance_html = _acceptance_html(acceptance)
        workstreams = task.get("workstreams") if isinstance(task.get("workstreams"), list) else []
        for workstream in workstreams:
            if not isinstance(workstream, Mapping):
                continue
            status = str(workstream.get("status") or "working")
            status_ru = _status_ru(status)
            progress = int(workstream.get("progress") or 5)
            remaining_raw = str(workstream.get("remaining_range") or "не определено")
            remaining = escape(
                remaining_raw if remaining_raw.startswith("≈") else f"≈{remaining_raw}"
            )
            blocker = str(workstream.get("blocker") or "").strip()
            blocker_html = (
                f'<div class="line blocker"><span>Блокер:</span> {escape(blocker)}</div>' if blocker else ""
            )
            cards.append(
                f"""
                <article class="card">
                  <div class="card-top"><div><div class="eyebrow">{escape(str(workstream.get('title') or 'Workstream'))}</div><h2>{title}</h2></div><span class="badge {_status_class(status)}">{escape(status_ru)}</span></div>
                  <div class="line"><span>Статус:</span> {escape(status_ru)}</div>
                  <div class="line"><span>Задача:</span> {title}</div>
                  <div class="line"><span>Прогресс:</span> ≈{progress}% · Осталось: {remaining}</div>
                  <div class="progress"><i style="width:{max(5, min(progress, 100))}%"></i></div>
                  <div class="line"><span>С прошлого отчёта:</span> {escape(str(workstream.get('delta') or 'Нет новой доказанной дельты'))}</div>
                  <div class="line"><span>Сейчас:</span> {escape(str(workstream.get('current_action') or 'Ожидание новой проекции'))}</div>
                  {blocker_html}
                  {release_html}{incident_html}{attention_html}{acceptance_html}
                  <div class="meta">{task_id} · обновлено {escape(str(workstream.get('updated_at') or '—'))}</div>
                </article>
                """
            )
    empty = "" if cards else '<section class="empty">Активных задач нет. Принятые задачи не показываются.</section>'
    stale_class = "stale" if stale else "fresh"
    stale_label = "Связь устарела" if stale else "Supervisor на связи"
    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>DevControl · Мониторинг</title>
  <style>
    :root{{--bg:#071018;--panel:#0d1a25;--panel2:#102332;--line:#20384a;--text:#edf6fb;--muted:#8ba4b4;--blue:#55b8ff;--green:#54d69c;--amber:#f3bf5b;--red:#ff7777}}
    *{{box-sizing:border-box}} body{{margin:0;background:linear-gradient(145deg,#061019,#0a1721 55%,#08131c);color:var(--text);font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;min-height:100vh}}
    header{{position:sticky;top:0;z-index:2;background:rgba(7,16,24,.94);backdrop-filter:blur(12px);border-bottom:1px solid var(--line)}}
    .wrap{{max-width:1160px;margin:auto;padding:18px 22px}} .header-row{{display:flex;gap:20px;align-items:center;justify-content:space-between;flex-wrap:wrap}}
    h1{{font-size:22px;margin:0}} .sub{{color:var(--muted);font-size:13px;margin-top:5px}} .connection{{border:1px solid var(--line);border-radius:999px;padding:9px 13px;font-size:13px}}
    .connection.fresh{{color:var(--green)}} .connection.stale{{color:var(--amber)}} main.wrap{{padding-top:26px;padding-bottom:60px}}
    .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,360px),1fr));gap:16px}} .card{{background:linear-gradient(165deg,var(--panel2),var(--panel));border:1px solid var(--line);border-radius:16px;padding:18px;box-shadow:0 12px 30px rgba(0,0,0,.18)}}
    .card-top{{display:flex;justify-content:space-between;gap:12px;align-items:start;margin-bottom:15px}} h2{{font-size:18px;margin:2px 0 0}} .eyebrow{{font-size:12px;color:var(--muted)}} .badge{{font-size:12px;border:1px solid currentColor;border-radius:999px;padding:5px 8px;white-space:nowrap}}
    .working{{color:var(--blue)}} .waiting{{color:var(--amber)}} .recovering{{color:var(--amber)}} .blocked{{color:var(--red)}} .complete{{color:var(--green)}}
    .line{{font-size:14px;line-height:1.5;margin:8px 0;color:#d7e5ed}} .line span{{color:var(--muted)}} .line.blocker{{border-left:3px solid var(--red);padding-left:9px;color:#ffd4d4}}
    .progress{{height:5px;background:#1c3343;border-radius:6px;overflow:hidden;margin:9px 0 13px}} .progress i{{display:block;height:100%;background:linear-gradient(90deg,var(--blue),var(--green))}}
    .detail{{margin-top:12px;padding-top:11px;border-top:1px solid var(--line);font-size:13px;color:#c6d8e2}} .detail b{{color:var(--muted);font-weight:600}} .meta{{margin-top:14px;color:#668090;font-size:11px;overflow-wrap:anywhere}}
    .empty{{border:1px dashed var(--line);border-radius:16px;color:var(--muted);padding:36px;text-align:center}}
    @media(max-width:600px){{.wrap{{padding-left:14px;padding-right:14px}}.connection{{width:100%}}.card{{padding:15px}}.badge{{white-space:normal;text-align:center}}}}
  </style>
</head>
<body>
  <header><div class="wrap header-row"><div><h1>Мониторинг задач</h1><div class="sub">Read-only проекция локального Supervisor</div></div><div class="connection {stale_class}">{stale_label} · last_seen {last_seen} · {age_text}</div></div></header>
  <main class="wrap"><div class="grid">{''.join(cards)}</div>{empty}</main>
</body>
</html>"""


def _release_html(items: list[Any]) -> str:
    if not items:
        return ""
    rows: list[str] = []
    for raw in items[:3]:
        item = raw if isinstance(raw, Mapping) else {}
        pr_url = str(item.get("pr_url") or "")
        pr = (
            f'<a href="{escape(pr_url, quote=True)}" rel="noreferrer">PR #{escape(str(item.get("pr_number") or ""))}</a>'
            if pr_url
            else "PR ещё не привязан"
        )
        status = _release_status_ru(str(item.get("status") or "none"))
        deploy = _release_deploy_status_ru(str(item.get("deploy_status") or ""))
        rows.append(f"{escape(status)} · {pr} · {escape(deploy)}")
    suffix = f" · ещё {len(items) - 3}" if len(items) > 3 else ""
    return '<div class="detail"><b>Выпуск:</b> ' + "<br>".join(rows) + escape(suffix) + "</div>"


def _release_status_ru(status: str) -> str:
    return {
        "none": "не запланирован",
        "planned": "ожидается план выпуска",
        "pr_open": "PR зарегистрирован",
        "checks_running": "проверки выполняются",
        "ready": "готов к выпуску",
        "merging": "выполняется слияние",
        "merged": "merge доказан",
        "deploying": "выполняется развёртывание",
        "verifying": "выполняется финальная проверка",
        "production": "production доказан",
        "blocked": "требуется повторный допуск",
        "failed": "выпуск припаркован",
    }.get(status, "состояние выпуска подтверждается")


def _release_deploy_status_ru(status: str) -> str:
    return {
        "": "действие ещё не начато",
        "candidate_registered": "кандидат зарегистрирован",
        "awaiting_admission": "ожидается допуск",
        "candidate_admitted": "кандидат допущен",
        "admission_blocked": "допуск заблокирован",
        "proof_only": "действие Release Train не требуется",
        "semantic_plan_required": "требуется semantic release plan",
        "lane_reserved": "release lane зарезервирована",
        "admission_submitted": "допуск отправлен",
        "admitted": "допуск подтверждён",
        "waiting_foreign_lane": "ожидание внешней release lane",
        "waiting_release": "ожидание Release Train",
        "readmission_required": "требуется повторный допуск по новому PR head",
        "superseded_readmission": "старый PR head заменён; новый зарегистрирован",
        "lane_closure_pending": "закрытие target release lane подготовлено",
        "lane_closure_submitted": "закрытие target release lane отправлено",
        "lane_released": "target release lane освобождена",
        "lane_closure_parked": "закрытие target release lane припарковано",
        "repository_done": "repo-only выпуск подтверждён; deploy не выполнялся",
        "production": "развёртывание подтверждено",
        "parked": "Release Train припаркован",
    }.get(status, "состояние подтверждается")


def _incident_html(items: list[Any]) -> str:
    if not items:
        return ""
    item = items[0] if isinstance(items[0], Mapping) else {}
    return '<div class="detail"><b>Инцидент:</b> ' + escape(str(item.get("summary") or "")) + "</div>"


def _attention_html(items: list[Any]) -> str:
    if not items:
        return ""
    item = items[0] if isinstance(items[0], Mapping) else {}
    return '<div class="detail"><b>Требует внимания:</b> ' + escape(str(item.get("summary") or "")) + "</div>"


def _acceptance_html(item: Mapping[str, Any] | None) -> str:
    if not item:
        return ""
    status = str(item.get("status") or "not_ready")
    label = {"not_ready": "не готова", "awaiting_owner": "требуется приёмка", "accepted": "принята"}.get(status, status)
    return '<div class="detail"><b>Приёмка:</b> ' + escape(label) + "</div>"


def _status_ru(status: str) -> str:
    return {
        "working": "В работе",
        "waiting_release": "Ожидание выпуска",
        "recovering": "Восстановление",
        "blocked": "Блокер",
        "awaiting_acceptance": "Завершена — требуется приёмка",
        "completed": "Завершена — требуется приёмка",
        "parked": "Блокер",
    }.get(status, "В работе")


def _status_class(status: str) -> str:
    return {
        "working": "working",
        "waiting_release": "waiting",
        "recovering": "recovering",
        "blocked": "blocked",
        "parked": "blocked",
        "awaiting_acceptance": "complete",
        "completed": "complete",
    }.get(status, "working")


def _header_positive_int(headers: Mapping[str, str], name: str) -> int:
    raw = str(headers.get(name) or "").strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ProjectionSecurityError("signed metadata header is invalid", code="invalid_signed_metadata") from exc
    if value <= 0 or value > 2**63 - 1:
        raise ProjectionSecurityError("signed metadata header is invalid", code="invalid_signed_metadata")
    return value


def _header_safe_id(headers: Mapping[str, str], name: str) -> str:
    value = str(headers.get(name) or "").strip()
    if not SAFE_HEADER_ID_RE.fullmatch(value):
        raise ProjectionSecurityError("signed metadata header is invalid", code="invalid_signed_metadata")
    return value


def _request_path(raw: str) -> str:
    return urlsplit(raw).path or "/"


def _stale_status(last_seen_epoch: Any, stale_after_seconds: int) -> dict[str, Any]:
    if last_seen_epoch is None:
        return {"stale": True, "age_seconds": None}
    age = max(0, int(time.time() - float(last_seen_epoch)))
    return {"stale": age > stale_after_seconds, "age_seconds": age}


def _positive_config_int(value: Any, label: str, *, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ProjectionServerConfigError(f"{label} must be an integer") from exc
    if parsed <= 0 or parsed > maximum:
        raise ProjectionServerConfigError(f"{label} is outside allowed range")
    return parsed


def config_from_args(args: argparse.Namespace) -> ProjectionServerConfig:
    host = str(args.host or os.environ.get(HOST_ENV) or DEFAULT_HOST).strip()
    if host != DEFAULT_HOST:
        raise ProjectionServerConfigError("projection v2 server must bind only to 127.0.0.1")
    port = _positive_config_int(args.port if args.port is not None else os.environ.get(PORT_ENV, DEFAULT_PORT), "port", maximum=65535)
    database_raw = args.database or os.environ.get(DATABASE_ENV) or DEFAULT_DATABASE
    key_raw = args.hmac_key_file or os.environ.get(HMAC_KEY_FILE_ENV)
    if not key_raw:
        raise ProjectionServerConfigError("projection HMAC key file is required")
    max_skew = _positive_config_int(
        args.max_skew_seconds if args.max_skew_seconds is not None else os.environ.get(MAX_SKEW_ENV, 300),
        "max_skew_seconds",
        maximum=3600,
    )
    stale_after = _positive_config_int(
        args.stale_after_seconds if args.stale_after_seconds is not None else os.environ.get(STALE_AFTER_ENV, 120),
        "stale_after_seconds",
        maximum=86_400,
    )
    return ProjectionServerConfig(
        host=host,
        port=port,
        # Preserve the final path component so ProjectionStore can reject a
        # database symlink instead of silently following it.
        database_path=Path(database_raw).expanduser(),
        hmac_key_file=Path(key_raw).expanduser(),
        max_skew_seconds=max_skew,
        stale_after_seconds=stale_after,
    )


def main(argv: list[str] | None = None) -> int:
    observed_role = os.environ.get("AUTHORITY_ROLE")
    parser = argparse.ArgumentParser(description="Read-only hosted projection v2 server")
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    parser.add_argument("--database", type=Path)
    parser.add_argument("--hmac-key-file", type=Path)
    parser.add_argument("--max-skew-seconds", type=int)
    parser.add_argument("--stale-after-seconds", type=int)
    args = parser.parse_args(argv)
    try:
        if observed_role not in {None, "", SERVICE_ROLE}:
            raise ProjectionServerConfigError("conflicting authority role")
        config = config_from_args(args)
        server = build_server(config)
    except (ProjectionServerConfigError, ProjectionStoreError) as exc:
        print(
            json.dumps(
                {"status": "blocked", "reason_code": "projection_v2_config_invalid", "service_role": SERVICE_ROLE},
                sort_keys=True,
            ),
            file=sys.stderr,
            flush=True,
        )
        return 2
    print(
        json.dumps(
            {
                "status": "serving",
                "service_role": SERVICE_ROLE,
                "host": config.host,
                "port": server.server_port,
                "control_authority": False,
                "mutation_routes_enabled": False,
                "projection_ingestion_enabled": True,
            },
            sort_keys=True,
        ),
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
