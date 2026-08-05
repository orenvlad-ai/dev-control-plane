"""Stateless delivery-only adapter for one durable curator attention event.

This adapter does not monitor tasks, choose work, or own a queue.  A supported
Desktop/delegation bridge may call :meth:`prepare_one`, deliver exactly the
returned handoff, and then provide one bound receipt to ``ack`` or ``nack``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import hmac
import json
from pathlib import Path
import os
import stat
import time
from typing import Any, Mapping

from .supervisor_registry import OutboxMessage, SupervisorFence, SupervisorRegistry

ATTENTION_SCHEMA = "dev-control-plane/curator-attention/v2"
OWNER_SOURCE_SCHEMA = "dev-control-plane/owner-acceptance-source/v2"
OWNER_ACTION_ATTESTATION_SCHEMA = "dev-control-plane/owner-action-attestation/v2"
OWNER_ACTION_ATTESTATION_FIELDS = frozenset(
    {
        "schema",
        "trigger_event_id",
        "trigger_event_digest",
        "task_id",
        "task_revision",
        "workstream_id",
        "workstream_generation",
        "workstream_revision",
        "curator_thread_id",
        "requested_action",
        "action_sha256",
        "source_message_id",
        "observed_at_epoch",
        "signature",
    }
)
ATTENTION_FIELDS = frozenset(
    {
        "schema",
        "attention_id",
        "task_id",
        "workstream_id",
        "curator_thread_id",
        "kind",
        "handoff_ru",
        "required_action",
        "created_at",
    }
)


class CuratorDeliveryError(RuntimeError):
    """A durable attention payload or delivery receipt is invalid."""


@dataclass(frozen=True)
class PreparedAttention:
    event_id: str
    attention_id: str
    task_id: str
    workstream_id: str
    curator_thread_id: str
    kind: str
    handoff_ru: str
    required_action: str
    attempt: int
    payload_digest: str
    claim_token: str = field(repr=False)


@dataclass(frozen=True)
class DeliveryReceipt:
    event_id: str
    attention_id: str
    curator_thread_id: str
    payload_digest: str
    claim_token: str = field(repr=False)


class CuratorDelivery:
    """Prepare and receipt one message; it deliberately has no background loop."""

    def __init__(self, registry: SupervisorRegistry, fence: SupervisorFence) -> None:
        self.registry = registry
        self.fence = fence

    def prepare_one(self, *, visibility_timeout: float = 120.0) -> PreparedAttention | None:
        claimed = self.registry.claim_outbox(
            self.fence,
            worker_id="curator-delivery-only",
            limit=1,
            visibility_timeout=visibility_timeout,
            kinds=("curator_attention",),
        )
        if not claimed:
            return None
        try:
            return _prepared_from_message(claimed[0])
        except Exception:
            self.registry.nack_outbox(
                claimed[0].event_id,
                claimed[0].claim_token,
                self.fence,
                retry_at=time.time() + 300,
                sanitized_error="curator_attention_contract_invalid",
            )
            raise

    @staticmethod
    def receipt(prepared: PreparedAttention) -> DeliveryReceipt:
        return DeliveryReceipt(
            event_id=prepared.event_id,
            attention_id=prepared.attention_id,
            curator_thread_id=prepared.curator_thread_id,
            payload_digest=prepared.payload_digest,
            claim_token=prepared.claim_token,
        )

    def ack(self, receipt: DeliveryReceipt) -> None:
        _validate_receipt(receipt)
        self._validate_bound_receipt(receipt)
        self.registry.ack_outbox(receipt.event_id, receipt.claim_token, self.fence)

    def nack(
        self,
        receipt: DeliveryReceipt,
        *,
        retry_at: float,
        reason_code: str,
    ) -> None:
        _validate_receipt(receipt)
        self._validate_bound_receipt(receipt)
        if retry_at <= time.time():
            raise CuratorDeliveryError("retry_at must be in the future")
        sanitized = _bounded_machine("reason_code", reason_code)
        self.registry.nack_outbox(
            receipt.event_id,
            receipt.claim_token,
            self.fence,
            retry_at=retry_at,
            sanitized_error=sanitized,
        )

    def _validate_bound_receipt(self, receipt: DeliveryReceipt) -> None:
        record = next(
            (
                item
                for item in self.registry.list_outbox_records(kinds=("curator_attention",))
                if item["event_id"] == receipt.event_id
            ),
            None,
        )
        if record is None or record["state"] != "inflight":
            raise CuratorDeliveryError("delivery receipt does not name one inflight attention")
        payload = record["payload"]
        if (
            record["payload_digest"] != receipt.payload_digest
            or payload.get("attention_id") != receipt.attention_id
            or payload.get("curator_thread_id") != receipt.curator_thread_id
        ):
            raise CuratorDeliveryError("delivery receipt is not bound to the durable attention payload")


class OwnerAcceptanceSourceVerifier:
    """Verify an exact curator-message attestation from a delivery-only bridge."""

    def __init__(self, key_file: Path | str, *, max_age_seconds: float = 7 * 24 * 60 * 60) -> None:
        path = Path(os.path.abspath(Path(key_file).expanduser()))
        key = _read_owner_acceptance_key(path)
        if len(key) < 32 or len(key) > 4_096:
            raise CuratorDeliveryError("owner acceptance key has invalid length")
        if max_age_seconds <= 0:
            raise ValueError("owner source attestation max age must be positive")
        self._key = key
        self.max_age_seconds = float(max_age_seconds)

    def __call__(self, receipt: Any, attestation: Mapping[str, Any]) -> bool:
        try:
            observed_at = float(attestation["observed_at_epoch"])
            now = time.time()
            if observed_at > now + 120 or now - observed_at > self.max_age_seconds:
                return False
            reply_digest = hashlib.sha256(str(receipt.reply).encode("utf-8")).hexdigest()
            if attestation.get("reply_sha256") != reply_digest:
                return False
            supplied = str(attestation["signature"])
            if len(supplied) != 64 or any(char not in "0123456789abcdef" for char in supplied):
                return False
            expected = owner_acceptance_source_signature(self._key, receipt, attestation)
            return hmac.compare_digest(supplied, expected)
        except (KeyError, TypeError, ValueError, AttributeError):
            return False


class OwnerActionAttestationVerifier:
    """Verify a HumanGate action observed in the exact curator thread."""

    def __init__(self, key_file: Path | str, *, max_age_seconds: float = 7 * 24 * 60 * 60) -> None:
        path = Path(os.path.abspath(Path(key_file).expanduser()))
        key = _read_owner_acceptance_key(path)
        if len(key) < 32 or len(key) > 4_096:
            raise CuratorDeliveryError("owner action key has invalid length")
        if max_age_seconds <= 0:
            raise ValueError("owner action attestation max age must be positive")
        self._key = key
        self.max_age_seconds = float(max_age_seconds)

    def __call__(
        self, expected_binding: Mapping[str, Any], attestation: Mapping[str, Any]
    ) -> bool:
        try:
            if set(attestation) != OWNER_ACTION_ATTESTATION_FIELDS:
                return False
            if attestation.get("schema") != OWNER_ACTION_ATTESTATION_SCHEMA:
                return False
            observed_at = float(attestation["observed_at_epoch"])
            now = time.time()
            if observed_at > now + 120 or now - observed_at > self.max_age_seconds:
                return False
            for key in OWNER_ACTION_ATTESTATION_FIELDS - {
                "schema", "source_message_id", "observed_at_epoch", "signature"
            }:
                if attestation.get(key) != expected_binding.get(key):
                    return False
            _bounded_machine("source_message_id", attestation["source_message_id"])
            action_sha = hashlib.sha256(
                str(attestation["requested_action"]).encode("utf-8")
            ).hexdigest()
            if attestation.get("action_sha256") != action_sha:
                return False
            supplied = str(attestation["signature"])
            if len(supplied) != 64 or any(
                char not in "0123456789abcdef" for char in supplied
            ):
                return False
            expected = owner_action_attestation_signature(self._key, attestation)
            return hmac.compare_digest(supplied, expected)
        except (KeyError, TypeError, ValueError, AttributeError):
            return False


def owner_action_attestation_signature(
    key: bytes, attestation: Mapping[str, Any]
) -> str:
    """Domain-separated signature for one exact HumanGate action receipt."""

    payload = {
        name: attestation[name]
        for name in OWNER_ACTION_ATTESTATION_FIELDS
        if name != "signature"
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hmac.new(
        key,
        b"dev-control-plane/owner-action-attestation/v2\x00" + encoded,
        hashlib.sha256,
    ).hexdigest()


def owner_acceptance_source_signature(
    key: bytes,
    receipt: Any,
    attestation: Mapping[str, Any],
) -> str:
    """Canonical signature contract used only by a supported exact-chat bridge."""

    payload = {
        "schema": OWNER_SOURCE_SCHEMA,
        "receipt_id": receipt.receipt_id,
        "task_id": receipt.task_id,
        "task_revision": receipt.task_revision,
        "curator_thread_id": receipt.curator_thread_id,
        "reply": receipt.reply,
        "receipt_created_at": receipt.created_at,
        "source_message_id": attestation["source_message_id"],
        "attention_event_id": attestation["attention_event_id"],
        "observed_at_epoch": attestation["observed_at_epoch"],
        "reply_sha256": attestation["reply_sha256"],
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hmac.new(key, encoded, hashlib.sha256).hexdigest()


def _prepared_from_message(message: OutboxMessage) -> PreparedAttention:
    payload = message.payload
    if not isinstance(payload, Mapping) or set(payload) != ATTENTION_FIELDS:
        raise CuratorDeliveryError("curator attention fields are invalid")
    if payload.get("schema") != ATTENTION_SCHEMA:
        raise CuratorDeliveryError("curator attention schema is invalid")
    kind = _bounded_machine("kind", payload.get("kind"))
    if kind not in {"terminal", "human_gate", "serious_stall"}:
        raise CuratorDeliveryError("curator attention kind is invalid")
    handoff = _bounded_text("handoff_ru", payload.get("handoff_ru"), 8_000)
    action = _bounded_text("required_action", payload.get("required_action"), 500)
    return PreparedAttention(
        event_id=message.event_id,
        attention_id=_bounded_machine("attention_id", payload.get("attention_id")),
        task_id=_bounded_machine("task_id", payload.get("task_id")),
        workstream_id=_bounded_machine("workstream_id", payload.get("workstream_id")),
        curator_thread_id=_bounded_machine("curator_thread_id", payload.get("curator_thread_id")),
        kind=kind,
        handoff_ru=handoff,
        required_action=action,
        attempt=message.attempts,
        payload_digest=hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        claim_token=message.claim_token,
    )


def _validate_receipt(receipt: DeliveryReceipt) -> None:
    for name in ("event_id", "attention_id", "curator_thread_id", "claim_token"):
        _bounded_machine(name, getattr(receipt, name))
    if not isinstance(receipt.payload_digest, str) or len(receipt.payload_digest) != 64 or any(
        character not in "0123456789abcdef" for character in receipt.payload_digest
    ):
        raise CuratorDeliveryError("payload_digest must be a sha256 digest")


def _read_owner_acceptance_key(path: Path) -> bytes:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise CuratorDeliveryError("owner acceptance key is unavailable") from exc
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_uid != os.geteuid()
        or metadata.st_nlink != 1
        or not 32 <= metadata.st_size <= 4_096
    ):
        raise CuratorDeliveryError("owner acceptance key must be an owner-only 0600 regular file")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
        try:
            opened = os.fstat(descriptor)
            key = os.read(descriptor, 4_097)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise CuratorDeliveryError("owner acceptance key could not be opened safely") from exc
    if (
        opened.st_dev != metadata.st_dev
        or opened.st_ino != metadata.st_ino
        or not stat.S_ISREG(opened.st_mode)
        or stat.S_IMODE(opened.st_mode) != 0o600
        or opened.st_uid != os.geteuid()
        or opened.st_nlink != 1
        or not 32 <= len(key) <= 4_096
    ):
        raise CuratorDeliveryError("owner acceptance key changed during secure validation")
    return key


def _bounded_machine(label: str, value: Any) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > 256
        or any(ord(character) < 33 for character in value)
    ):
        raise CuratorDeliveryError(f"{label} must be a bounded machine value")
    return value


def _bounded_text(label: str, value: Any, limit: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise CuratorDeliveryError(f"{label} must be bounded non-empty text")
    return value.strip()
