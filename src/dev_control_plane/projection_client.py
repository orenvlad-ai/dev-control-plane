"""Outbound-only HTTPS publisher for durable Supervisor projection snapshots."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import random
import shutil
import subprocess
import tempfile
import time
from typing import Any, Callable, Mapping

from .projection_server import SignedMetadata, load_hmac_key, signed_headers
from .projection_store import PROJECTION_CONTRACT, projection_envelope_from_mapping
from .supervisor_registry import SupervisorFence, SupervisorRegistry

MAX_ACK_BYTES = 64 * 1024
PRODUCTION_PROJECTION_ENDPOINT = "https://devcontrol.pro/api/v2/ingest"
ACK_FIELDS = frozenset(
    {
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
)


class ProjectionPublishError(RuntimeError):
    """A controlled outbound transport or exact-ACK failure."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class TransportResponse:
    status: int
    body: bytes


@dataclass(frozen=True)
class PublishResult:
    status: str
    event_id: str | None
    attempt: int
    retry_at: float | None = None
    reason_code: str | None = None


Transport = Callable[[str, bytes, Mapping[str, str], float], TransportResponse]


class ProjectionPublisher:
    """Claim one durable snapshot, call HTTPS, then persist only an exact receipt."""

    def __init__(
        self,
        *,
        endpoint: str,
        key: bytes | None = None,
        key_file: str | None = None,
        transport: Transport | None = None,
        timeout_seconds: float = 15.0,
        base_backoff_seconds: float = 2.0,
        max_backoff_seconds: float = 300.0,
        clock: Callable[[], float] = time.time,
        random_source: random.Random | None = None,
    ) -> None:
        self.endpoint = _validate_endpoint(endpoint)
        if (key is None) == (key_file is None):
            raise ProjectionPublishError("exactly_one_projection_key_source_required")
        self.key = bytes(key) if key is not None else load_hmac_key(str(key_file))
        if not 32 <= len(self.key) <= 4096:
            raise ProjectionPublishError("projection_key_length_invalid")
        if timeout_seconds <= 0 or base_backoff_seconds <= 0 or max_backoff_seconds < base_backoff_seconds:
            raise ProjectionPublishError("projection_transport_bounds_invalid")
        self.transport = transport or _https_transport
        self.timeout_seconds = float(timeout_seconds)
        self.base_backoff_seconds = float(base_backoff_seconds)
        self.max_backoff_seconds = float(max_backoff_seconds)
        self.clock = clock
        self.random_source = random_source or random.SystemRandom()

    def publish_one(self, registry: SupervisorRegistry, fence: SupervisorFence) -> PublishResult:
        claimed = registry.claim_outbox(
            fence,
            worker_id="projection-publisher",
            limit=1,
            visibility_timeout=max(30.0, self.timeout_seconds * 2),
            kinds=("projection_snapshot",),
        )
        if not claimed:
            return PublishResult("idle", None, 0)
        message = claimed[0]
        try:
            envelope = projection_envelope_from_mapping(message.payload)
            if envelope.contract != PROJECTION_CONTRACT or envelope.generation != fence.generation:
                raise ProjectionPublishError("stale_projection_generation")
            body = json.dumps(
                message.payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
            metadata = SignedMetadata(
                # Fresh transport time is signed on every attempt.  The body keeps
                # immutable source time so an ACK-loss replay has the same digest.
                timestamp=max(1, int(self.clock())),
                supervisor_id=envelope.supervisor_id,
                generation=envelope.generation,
                sequence=envelope.sequence,
                revision=envelope.revision,
                event_id=envelope.event_id,
                idempotency_key=envelope.idempotency_key,
            )
            headers = signed_headers(self.key, body, metadata)
            # No registry transaction is open across this external transport call.
            response = self.transport(self.endpoint, body, headers, self.timeout_seconds)
            acknowledgement = _parse_exact_ack(response, envelope)
            if acknowledgement["status"] != "ack":
                raise ProjectionPublishError("projection_ack_status_invalid")
            registry.ack_outbox(message.event_id, message.claim_token, fence)
            return PublishResult("delivered", message.event_id, message.attempts)
        except ProjectionPublishError as exc:
            return self._retry(registry, fence, message, exc.code)
        except (OSError, TimeoutError, ValueError, json.JSONDecodeError):
            return self._retry(registry, fence, message, "projection_transport_unavailable")

    def publish_available(
        self,
        registry: SupervisorRegistry,
        fence: SupervisorFence,
        *,
        limit: int = 10,
    ) -> tuple[PublishResult, ...]:
        if not 1 <= limit <= 100:
            raise ProjectionPublishError("publish_batch_limit_invalid")
        results: list[PublishResult] = []
        for _ in range(limit):
            result = self.publish_one(registry, fence)
            if result.status == "idle":
                break
            results.append(result)
            if result.status != "delivered":
                break
        return tuple(results)

    def _retry(
        self,
        registry: SupervisorRegistry,
        fence: SupervisorFence,
        message: OutboxMessage,
        reason_code: str,
    ) -> PublishResult:
        exponent = max(0, min(message.attempts - 1, 20))
        base = min(self.max_backoff_seconds, self.base_backoff_seconds * (2**exponent))
        jittered = max(self.base_backoff_seconds, base * self.random_source.uniform(0.8, 1.2))
        retry_at = self.clock() + min(self.max_backoff_seconds, jittered)
        registry.nack_outbox(
            message.event_id,
            message.claim_token,
            fence,
            retry_at=retry_at,
            sanitized_error=reason_code,
        )
        return PublishResult("retry_scheduled", message.event_id, message.attempts, retry_at, reason_code)


def _validate_endpoint(endpoint: str) -> str:
    if endpoint != PRODUCTION_PROJECTION_ENDPOINT:
        raise ProjectionPublishError("projection_destination_not_approved")
    return endpoint


def _https_transport(endpoint: str, body: bytes, headers: Mapping[str, str], timeout: float) -> TransportResponse:
    """Use macOS system curl/SecureTransport without putting signatures in argv."""

    if endpoint != PRODUCTION_PROJECTION_ENDPOINT:
        raise ProjectionPublishError("projection_destination_not_approved")
    temporary = Path(tempfile.mkdtemp(prefix="dev-control-plane-projection-"))
    try:
        temporary.chmod(0o700)
        body_path = temporary / "request.body"
        response_path = temporary / "response.body"
        config_path = temporary / "curl.config"
        _private_write(body_path, body)
        config_lines = [
            f'url = "{_curl_quote(endpoint)}"',
            'request = "POST"',
            'proto = "=https"',
            'tlsv1.2',
            'silent',
            'show-error',
            f'max-time = "{max(1, int(math.ceil(timeout)))}"',
            f'connect-timeout = "{max(1, min(10, int(math.ceil(timeout))))}"',
            f'max-filesize = "{MAX_ACK_BYTES}"',
            f'output = "{_curl_quote(str(response_path))}"',
            'write-out = "%{http_code}"',
            f'data-binary = "@{_curl_quote(str(body_path))}"',
        ]
        for name, value in sorted(headers.items()):
            if "\n" in name or "\r" in name or "\n" in value or "\r" in value:
                raise ProjectionPublishError("projection_header_invalid")
            config_lines.append(f'header = "{_curl_quote(name + ": " + value)}"')
        _private_write(config_path, ("\n".join(config_lines) + "\n").encode("utf-8"))
        completed = subprocess.run(
            ["/usr/bin/curl", "-q", "--config", str(config_path)],
            check=False,
            capture_output=True,
            timeout=timeout + 5,
            env={"HOME": str(temporary), "PATH": "/usr/bin:/bin"},
        )
        if completed.returncode != 0:
            raise ProjectionPublishError("projection_curl_failed")
        try:
            status = int(completed.stdout.decode("ascii").strip())
        except (UnicodeDecodeError, ValueError) as exc:
            raise ProjectionPublishError("projection_curl_status_invalid") from exc
        try:
            payload = response_path.read_bytes()
        except OSError as exc:
            raise ProjectionPublishError("projection_curl_response_missing") from exc
        if len(payload) > MAX_ACK_BYTES:
            raise ProjectionPublishError("projection_ack_too_large")
        return TransportResponse(status, payload)
    except subprocess.TimeoutExpired as exc:
        raise ProjectionPublishError("projection_curl_timeout") from exc
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def _private_write(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _curl_quote(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _parse_exact_ack(response: TransportResponse, envelope: Any) -> Mapping[str, Any]:
    if response.status != 200:
        raise ProjectionPublishError(f"projection_http_{response.status}")
    if len(response.body) > MAX_ACK_BYTES:
        raise ProjectionPublishError("projection_ack_too_large")
    try:
        payload = json.loads(response.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProjectionPublishError("projection_ack_invalid_json") from exc
    if not isinstance(payload, Mapping) or set(payload) != ACK_FIELDS:
        raise ProjectionPublishError("projection_ack_fields_invalid")
    if payload.get("status") != "ack":
        raise ProjectionPublishError("projection_ack_status_invalid")
    if not isinstance(payload.get("applied"), bool) or not isinstance(payload.get("duplicate"), bool):
        raise ProjectionPublishError("projection_ack_booleans_invalid")
    if bool(payload["applied"]) == bool(payload["duplicate"]):
        raise ProjectionPublishError("projection_ack_result_invalid")
    expected = {
        "supervisor_id": envelope.supervisor_id,
        "generation": envelope.generation,
        "sequence": envelope.sequence,
        "revision": envelope.revision,
        "event_id": envelope.event_id,
        "idempotency_key": envelope.idempotency_key,
    }
    if any(payload.get(name) != value for name, value in expected.items()):
        raise ProjectionPublishError("projection_ack_binding_mismatch")
    return payload
