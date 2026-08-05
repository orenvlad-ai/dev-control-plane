#!/usr/bin/env python3
"""Fake-first smoke for the bounded Codex App Server v2 adapter.

The default path starts only a temporary fake stdio server.  The optional
``--read-only-canary`` path performs initialize, model/list and thread/read;
it never starts or resumes a thread and never invokes a model turn.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import textwrap
import threading
import time
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (SRC, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dev_control_plane.codex_app_server import (  # noqa: E402
    CHECKPOINT_SCHEMA_VERSION,
    CODEX_APP_SERVER_MODEL,
    CODEX_APP_SERVER_REASONING_EFFORT,
    TERMINAL_SCHEMA_VERSION,
    CodexAmbiguousOutcomeError,
    CodexAppServerClient,
    CodexAppServerError,
    CodexContractError,
    CodexDisconnectedError,
    CodexIdentityMismatchError,
    CodexProtocolError,
    CodexRemoteError,
    CodexRequestTimeout,
    CodexStaleGenerationError,
    CodexThreadOwnershipError,
    CodexTurnFailedError,
    checkpoint_output_schema,
    sanitized_thread_snapshot,
    terminal_output_schema,
    validate_checkpoint_payload,
    validate_terminal_payload,
)


GENERATION = 7
TASK_ID = "task-smoke"
WORKSTREAM_ID = "workstream-smoke"
FAKE_STDERR_SECRET = "fake-super-secret-value-0123456789"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--read-only-canary",
        metavar="THREAD_ID",
        help="run initialize + model/list + exact thread/read only (no model turn)",
    )
    parser.add_argument("--codex-bin", default="codex", help="Codex binary for the explicit read-only canary")
    parser.add_argument("--output", type=Path, help="required sanitized JSON output path for --read-only-canary")
    args = parser.parse_args()
    if args.read_only_canary:
        if args.output is None:
            parser.error("--output is required with --read-only-canary")
        try:
            _run_read_only_canary(args.read_only_canary, codex_bin=args.codex_bin, output_path=args.output)
        except CodexAppServerError as exc:
            raise SystemExit(f"read-only canary failed safely: {exc}") from None
        return
    if args.output is not None:
        parser.error("--output is only valid with --read-only-canary")
    _run_fake_smoke()


def _run_fake_smoke() -> None:
    with TemporaryDirectory(prefix="dev-control-plane-codex-app-server-v2-") as tmp_raw:
        tmp = Path(tmp_raw)
        fake_codex = tmp / "fake-codex"
        fake_log = tmp / "fake-server.jsonl"
        reconnect_marker = tmp / "disconnect-once.marker"
        _write_fake_codex(fake_codex)
        base_env = {
            "DCP_FAKE_LOG": str(fake_log),
            "DCP_FAKE_RECONNECT_MARKER": str(reconnect_marker),
            "DCP_FAKE_GENERATION": str(GENERATION),
            "DCP_FAKE_TASK_ID": TASK_ID,
            "DCP_FAKE_WORKSTREAM_ID": WORKSTREAM_ID,
            "DCP_FAKE_STDERR_SECRET": FAKE_STDERR_SECRET,
            "DCP_EXPLICIT_ENV_PROBE": "present",
        }

        ambient_secret_key = "DCP_PARENT_SECRET_MUST_NOT_REACH_CODEX"
        previous_ambient_secret = os.environ.get(ambient_secret_key)
        os.environ[ambient_secret_key] = "ambient-fake-secret-value"
        client = _fake_client(fake_codex, base_env)
        try:
            client.connect()
        finally:
            if previous_ambient_secret is None:
                os.environ.pop(ambient_secret_key, None)
            else:
                os.environ[ambient_secret_key] = previous_ambient_secret
        attestation = client.model_attestation
        if (
            attestation is None
            or attestation.model != CODEX_APP_SERVER_MODEL
            or attestation.reasoning_effort != CODEX_APP_SERVER_REASONING_EFFORT
            or "ultra" not in attestation.supported_reasoning_efforts
        ):
            raise AssertionError(f"Sol/Ultra model attestation failed: {attestation}")

        try:
            client.resume_thread("not-owned-thread")
        except CodexThreadOwnershipError:
            pass
        else:
            raise AssertionError("thread/resume must reject non-Supervisor-owned ids before transport")

        start_epoch = client.connection_epoch
        identity = client.start_thread(
            cwd=str(tmp / "workspace"),
            required_connection_epoch=start_epoch,
        )
        if identity.thread_id not in client.owned_thread_ids or identity.ephemeral:
            raise AssertionError(f"thread/start must register ownership: {identity}")
        if client.fresh_empty_turn_baseline(identity.thread_id) != ():
            raise AssertionError("thread/start did not expose its same-epoch empty baseline")
        with client.pin_connection_epoch(start_epoch):
            if client.connection_epoch != start_epoch:
                raise AssertionError("pinned App Server epoch changed")
        try:
            with client.pin_connection_epoch(start_epoch + 1):
                raise AssertionError("unreachable stale epoch body")
        except CodexAmbiguousOutcomeError:
            pass
        else:
            raise AssertionError("stale App Server epoch was pin-able")
        try:
            client.start_thread(required_connection_epoch=start_epoch + 1)
        except CodexDisconnectedError:
            pass
        else:
            raise AssertionError(
                "thread/start accepted a stale required connection epoch"
            )
        ephemeral_identity = client.start_thread(ephemeral=True)
        if not ephemeral_identity.ephemeral:
            raise AssertionError(f"thread/start must attest requested ephemeral mode: {ephemeral_identity}")
        resumed = client.resume_thread(identity.thread_id)
        if resumed.thread_id != identity.thread_id:
            raise AssertionError(f"thread/resume must preserve exact id: {resumed}")
        if client.fresh_empty_turn_baseline(identity.thread_id) is not None:
            raise AssertionError("thread/resume retained a process-local empty baseline")

        checkpoint_result = client.run_turn(
            identity.thread_id,
            "Return the bounded checkpoint object.",
            output_contract="checkpoint",
            expected_task_id=TASK_ID,
            expected_workstream_id=WORKSTREAM_ID,
            turn_timeout_seconds=2,
        )
        if checkpoint_result.contract.schema_version != CHECKPOINT_SCHEMA_VERSION:
            raise AssertionError(f"checkpoint output was not schema-bound: {checkpoint_result}")
        if checkpoint_result.contract.generation != GENERATION or checkpoint_result.contract.progress_percent != 40:
            raise AssertionError(f"checkpoint identity/progress mismatch: {checkpoint_result.contract}")

        terminal_result = client.run_turn(
            identity.thread_id,
            "Return the bounded terminal object.",
            output_contract="terminal",
            expected_task_id=TASK_ID,
            expected_workstream_id=WORKSTREAM_ID,
            turn_timeout_seconds=2,
        )
        if terminal_result.contract.schema_version != TERMINAL_SCHEMA_VERSION:
            raise AssertionError(f"terminal output was not schema-bound: {terminal_result}")
        if terminal_result.contract.status != "completed" or terminal_result.contract.blocker is not None:
            raise AssertionError(f"terminal evidence must be completed and blocker-free: {terminal_result.contract}")

        lifecycle_methods = {event.method for event in client.drain_lifecycle_events()}
        for required in ("thread/started", "turn/started", "item/started", "item/completed", "turn/completed"):
            if required not in lifecycle_methods:
                raise AssertionError(f"missing structural lifecycle event {required}: {lifecycle_methods}")
        if sum(event.method == "item/completed" for event in checkpoint_result.events) != 1:
            raise AssertionError(f"duplicate item lifecycle notifications were not deduped: {checkpoint_result.events}")

        first_reconciliation = client.reconcile_thread(identity.thread_id)
        second_reconciliation = client.reconcile_thread(identity.thread_id)
        if first_reconciliation.new_turn_ids != ("historic-turn",):
            raise AssertionError(f"reconciliation must return only unseen persisted turns: {first_reconciliation}")
        if first_reconciliation.new_item_ids != ("historic-item",):
            raise AssertionError(f"reconciliation must return only unseen persisted items: {first_reconciliation}")
        if second_reconciliation.new_turn_ids or second_reconciliation.new_item_ids:
            raise AssertionError(f"repeated reconciliation must dedupe ids: {second_reconciliation}")

        serialization_results: list[object] = []
        serialization_errors: list[BaseException] = []
        start_barrier = threading.Barrier(3)

        def run_serialized_turn(index: int) -> None:
            start_barrier.wait()
            try:
                serialization_results.append(
                    client.run_turn(
                        identity.thread_id,
                        f"serialization-{index}",
                        output_contract="checkpoint",
                        expected_task_id=TASK_ID,
                        expected_workstream_id=WORKSTREAM_ID,
                        turn_timeout_seconds=2,
                        serialization_timeout_seconds=2,
                    )
                )
            except BaseException as exc:  # smoke captures worker failures for the main assertion
                serialization_errors.append(exc)

        workers = [threading.Thread(target=run_serialized_turn, args=(index,)) for index in (1, 2)]
        for worker in workers:
            worker.start()
        start_barrier.wait()
        for worker in workers:
            worker.join(timeout=5)
        if any(worker.is_alive() for worker in workers):
            raise AssertionError("serialized turn workers did not finish")
        if serialization_errors or len(serialization_results) != 2:
            raise AssertionError(f"serialized turns failed: results={serialization_results} errors={serialization_errors}")

        stderr_text = "\n".join(client.stderr_tail)
        if FAKE_STDERR_SECRET in stderr_text or "Authorization: Bearer fake-" in stderr_text:
            raise AssertionError(f"stderr sanitizer leaked a secret: {stderr_text}")
        if "[REDACTED]" not in stderr_text:
            raise AssertionError(f"fake secret did not exercise stderr redaction: {stderr_text}")

        process_before_shutdown = client._process  # smoke-only ownership proof
        client.shutdown()
        if client.is_running or process_before_shutdown is None or process_before_shutdown.poll() is None:
            raise AssertionError("shutdown must stop the exact owned App Server process")

        log_rows = _read_log(fake_log)
        _assert_spawn_and_turn_identity(log_rows)
        max_active = max(
            (int(row.get("active", 0)) for row in log_rows if row.get("event") == "turn_begin" and row.get("thread_id") == identity.thread_id),
            default=0,
        )
        if max_active != 1:
            raise AssertionError(f"per-thread serialization allowed overlap: max_active={max_active} rows={log_rows}")

        _assert_reroute_fail_closed(fake_codex, base_env)
        _assert_timeout_is_bounded(fake_codex, base_env)
        _assert_mutating_timeout_is_ambiguous(fake_codex, base_env)
        _assert_resume_timeout_is_ambiguous(fake_codex, base_env)
        _assert_resume_rejection_consumes_empty_baseline(fake_codex, base_env)
        _assert_fresh_turn_epoch_fenced(fake_codex, base_env, fake_log)
        _assert_reconnect_is_bounded(fake_codex, base_env, reconnect_marker)
        _assert_lost_receipt_recovery(fake_codex, base_env, fake_log)
        _assert_stale_generation_fail_closed(fake_codex, base_env, fake_log)
        _assert_identity_mismatch_fail_closed(fake_codex, base_env)
        _assert_thread_response_identity_mismatch_fail_closed(fake_codex, base_env)
        _assert_schema_bypass_fail_closed(fake_codex, base_env)
        _assert_validators_fail_closed()
        canary_output = tmp / "sanitized-read-only-canary.json"
        _run_read_only_canary(
            "canary-thread",
            codex_bin=str(fake_codex),
            output_path=canary_output,
            env=base_env,
            announce=False,
        )
        canary_payload = json.loads(canary_output.read_text(encoding="utf-8"))
        if canary_payload.get("thread", {}).get("id") != "canary-thread":
            raise AssertionError(f"read-only canary did not preserve the exact thread id: {canary_payload}")
        if canary_payload.get("model") != CODEX_APP_SERVER_MODEL or canary_payload.get("reasoning_effort") != "ultra":
            raise AssertionError(f"read-only canary did not attest Sol/Ultra: {canary_payload}")
        canary_text = json.dumps(canary_payload, ensure_ascii=False, sort_keys=True)
        if FAKE_STDERR_SECRET in canary_text or "Bearer " in canary_text or "Authorization" in canary_text:
            raise AssertionError(f"read-only canary leaked a secret: {canary_payload}")

        combined = json.dumps(
            {
                "stderr": stderr_text,
                "errors": [str(error) for error in serialization_errors],
                "attestation": attestation.__dict__,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        for forbidden in (FAKE_STDERR_SECRET, "Authorization: Bearer fake-", "refresh_token=fake-"):
            if forbidden in combined:
                raise AssertionError(f"sanitized adapter surface leaked secret marker {forbidden}")

    print("dev-control-plane-codex-app-server-v2-smoke passed")


def _assert_reroute_fail_closed(fake_codex: Path, base_env: dict[str, str]) -> None:
    with _fake_client(fake_codex, base_env) as client:
        identity = client.start_thread()
        try:
            client.run_turn(
                identity.thread_id,
                "REROUTE",
                output_contract="checkpoint",
                expected_task_id=TASK_ID,
                expected_workstream_id=WORKSTREAM_ID,
                turn_timeout_seconds=1,
            )
        except CodexIdentityMismatchError as exc:
            if "reroute" not in str(exc).lower():
                raise AssertionError(f"reroute failure must be explicit: {exc}") from exc
        else:
            raise AssertionError("model/rerouted must fail closed")
        try:
            client.read_thread_snapshot(identity.thread_id)
        except CodexIdentityMismatchError:
            pass
        else:
            raise AssertionError("identity failure must fence subsequent adapter requests")


def _assert_timeout_is_bounded(fake_codex: Path, base_env: dict[str, str]) -> None:
    client = _fake_client(fake_codex, base_env, request_timeout=0.05, reconnect_attempts=0)
    try:
        client.connect()
        started = time.monotonic()
        try:
            client.read_thread_snapshot("timeout-thread", timeout_seconds=0.05)
        except CodexRequestTimeout:
            pass
        else:
            raise AssertionError("slow JSON-RPC request must time out")
        if time.monotonic() - started > 0.5:
            raise AssertionError("request timeout was not bounded")
    finally:
        client.shutdown()


def _assert_mutating_timeout_is_ambiguous(fake_codex: Path, base_env: dict[str, str]) -> None:
    client = _fake_client(fake_codex, base_env, request_timeout=0.05, reconnect_attempts=0)
    try:
        client.connect()
        identity = client.start_thread()
        try:
            client.run_turn(
                identity.thread_id,
                "SLOW_REQUEST",
                output_contract="checkpoint",
                expected_task_id=TASK_ID,
                expected_workstream_id=WORKSTREAM_ID,
                request_timeout_seconds=0.05,
                turn_timeout_seconds=1,
            )
        except CodexAmbiguousOutcomeError:
            pass
        else:
            raise AssertionError("timed-out turn/start must report an ambiguous outcome without retry")
        try:
            client.run_turn(
                identity.thread_id,
                "must-not-start-after-ambiguity",
                output_contract="checkpoint",
                expected_task_id=TASK_ID,
                expected_workstream_id=WORKSTREAM_ID,
            )
        except CodexProtocolError as exc:
            if "tainted" not in str(exc):
                raise AssertionError(f"ambiguous turn must taint the thread until recovery: {exc}") from exc
        else:
            raise AssertionError("ambiguous turn allowed another turn before explicit recovery")
    finally:
        client.shutdown()


def _assert_resume_timeout_is_ambiguous(fake_codex: Path, base_env: dict[str, str]) -> None:
    slow_env = dict(base_env)
    slow_env["DCP_FAKE_SLOW_RESUME"] = "1"
    client = _fake_client(fake_codex, slow_env, request_timeout=0.05, reconnect_attempts=0)
    try:
        client.connect()
        identity = client.start_thread()
        try:
            client.resume_thread(identity.thread_id)
        except CodexAmbiguousOutcomeError:
            pass
        else:
            raise AssertionError("timed-out thread/resume must report an ambiguous outcome")
        try:
            client.run_turn(
                identity.thread_id,
                "must-not-start-after-ambiguous-resume",
                output_contract="checkpoint",
                expected_task_id=TASK_ID,
                expected_workstream_id=WORKSTREAM_ID,
            )
        except CodexProtocolError as exc:
            if "tainted" not in str(exc):
                raise AssertionError(f"ambiguous resume failed closed for the wrong reason: {exc}") from exc
        else:
            raise AssertionError("ambiguous resume left the thread eligible for a turn")
    finally:
        client.shutdown()


def _assert_resume_rejection_consumes_empty_baseline(
    fake_codex: Path,
    base_env: dict[str, str],
) -> None:
    rejected_env = dict(base_env)
    rejected_env["DCP_FAKE_REJECT_RESUME"] = "1"
    client = _fake_client(fake_codex, rejected_env, reconnect_attempts=0)
    try:
        client.connect()
        identity = client.start_thread()
        if client.fresh_empty_turn_baseline(identity.thread_id) != ():
            raise AssertionError("fresh thread did not expose its initial empty baseline")
        try:
            client.resume_thread(identity.thread_id)
        except CodexRemoteError:
            pass
        else:
            raise AssertionError("fake App Server resume rejection was not propagated")
        if client.fresh_empty_turn_baseline(identity.thread_id) is not None:
            raise AssertionError("rejected resume retained the thread/start-only empty baseline")
    finally:
        client.shutdown()


def _assert_fresh_turn_epoch_fenced(
    fake_codex: Path,
    base_env: dict[str, str],
    fake_log: Path,
) -> None:
    before_turn_requests = sum(
        row.get("event") == "turn_request" for row in _read_log(fake_log)
    )
    client = _fake_client(fake_codex, base_env, reconnect_attempts=0)
    try:
        client.connect()
        identity = client.start_thread()
        epoch = client.connection_epoch
        if client.fresh_empty_turn_baseline(identity.thread_id) != ():
            raise AssertionError("fresh epoch fixture lacks an empty baseline")
        client.consume_fresh_empty_turn_baseline(
            identity.thread_id,
            required_connection_epoch=epoch,
        )
        original_request_once = client._request_once

        def reconnect_before_stdio_send(*args: Any, **kwargs: Any) -> Mapping[str, Any]:
            # Restore first so the replacement connection can initialize
            # normally.  The outer turn/start then reaches the exact-epoch
            # check only after `_request` performed its initial precheck.
            client._request_once = original_request_once
            client._dispose_current_process()  # smoke-only post-precheck disconnect
            client.connect()
            return original_request_once(*args, **kwargs)

        client._request_once = reconnect_before_stdio_send
        try:
            client.run_turn(
                identity.thread_id,
                "must-not-cross-connection-epoch",
                output_contract="checkpoint",
                expected_task_id=TASK_ID,
                expected_workstream_id=WORKSTREAM_ID,
                required_connection_epoch=epoch,
            )
        except CodexDisconnectedError:
            pass
        else:
            raise AssertionError("fresh empty proof crossed an App Server reconnect")
    finally:
        client.shutdown()

    consume_client = _fake_client(fake_codex, base_env, reconnect_attempts=0)
    try:
        consume_client.connect()
        identity = consume_client.start_thread()
        epoch = consume_client.connection_epoch
        if consume_client.fresh_empty_turn_baseline(identity.thread_id) != ():
            raise AssertionError("fresh consume fixture lacks an empty baseline")
        consume_client._dispose_current_process()  # smoke-only durable-intent gap
        try:
            consume_client.consume_fresh_empty_turn_baseline(
                identity.thread_id,
                required_connection_epoch=epoch,
            )
        except CodexProtocolError:
            pass
        else:
            raise AssertionError("disconnected fresh proof survived durable CAS consumption")
    finally:
        consume_client.shutdown()

    stale_start_client = _fake_client(
        fake_codex, base_env, reconnect_attempts=0
    )
    try:
        stale_start_client.connect()
        epoch = stale_start_client.connection_epoch
        stale_start_client._dispose_current_process()  # smoke-only dead epoch
        spawn_count_before_stale_start = sum(
            row.get("event") == "spawn" for row in _read_log(fake_log)
        )
        try:
            stale_start_client.start_thread(
                required_connection_epoch=epoch
            )
        except CodexDisconnectedError:
            pass
        else:
            raise AssertionError(
                "thread/start reconnected a dead required epoch"
            )
        spawn_count_after_stale_start = sum(
            row.get("event") == "spawn" for row in _read_log(fake_log)
        )
        if spawn_count_after_stale_start != spawn_count_before_stale_start:
            raise AssertionError(
                "required App Server epoch spawned a replacement child"
            )
    finally:
        stale_start_client.shutdown()

    after_turn_requests = sum(
        row.get("event") == "turn_request" for row in _read_log(fake_log)
    )
    if after_turn_requests != before_turn_requests:
        raise AssertionError("epoch-fenced failure emitted a turn/start request")


def _assert_reconnect_is_bounded(
    fake_codex: Path,
    base_env: dict[str, str],
    reconnect_marker: Path,
) -> None:
    reconnect_marker.unlink(missing_ok=True)
    sleeps: list[float] = []
    client = _fake_client(
        fake_codex,
        base_env,
        reconnect_attempts=1,
        sleep_fn=sleeps.append,
        jitter_fn=lambda _base: 0.01,
    )
    try:
        client.connect()
        first_epoch = client.connection_epoch
        if first_epoch <= 0 or client.model_attestation is None:
            raise AssertionError(f"initial connection epoch was not attested: {first_epoch}")
        if client.model_attestation.connection_epoch != first_epoch:
            raise AssertionError(
                f"public and attested connection epochs differ: {first_epoch} != {client.model_attestation}"
            )
        identity = client.start_thread()
        snapshot = client.read_thread_snapshot("reconnect-thread", timeout_seconds=1)
        if snapshot.get("id") != "reconnect-thread":
            raise AssertionError(f"safe read did not recover after reconnect: {snapshot}")
        if not sleeps or sleeps[0] <= 0.01:
            raise AssertionError(f"reconnect did not use injected backoff+jitter: {sleeps}")
        if client.model_attestation is None or client.connection_epoch <= first_epoch:
            raise AssertionError(f"reconnect did not reinitialize and re-attest: {client.model_attestation}")
        if client.model_attestation.connection_epoch != client.connection_epoch:
            raise AssertionError(
                "public connection epoch did not track the successfully reinitialized transport: "
                f"{client.connection_epoch} != {client.model_attestation}"
            )
        try:
            client.run_turn(
                identity.thread_id,
                "must-resume-after-reconnect",
                output_contract="checkpoint",
                expected_task_id=TASK_ID,
                expected_workstream_id=WORKSTREAM_ID,
            )
        except CodexThreadOwnershipError as exc:
            if "started or resumed on this connection" not in str(exc):
                raise AssertionError(f"reconnect cleared loaded state for the wrong reason: {exc}") from exc
        else:
            raise AssertionError("reconnect retained stale per-connection loaded-thread state")
    finally:
        client.shutdown()


def _assert_lost_receipt_recovery(
    fake_codex: Path,
    base_env: dict[str, str],
    fake_log: Path,
) -> None:
    recovery_threads = (
        "lost-checkpoint-thread",
        "lost-historical-thread",
        "lost-historical-model-thread",
        "lost-historical-reasoning-thread",
        "lost-historical-provider-thread",
        "lost-terminal-thread",
        "lost-tainted-thread",
        "lost-multiple-thread",
        "lost-incomplete-thread",
        "lost-failed-thread",
        "lost-malformed-thread",
        "lost-summary-thread",
        "lost-prose-after-contract-thread",
    )
    client = _fake_client(
        fake_codex,
        base_env,
        reconnect_attempts=0,
        owned_thread_ids=recovery_threads,
    )
    baseline = ("baseline-turn",)
    try:
        client.connect()
        checkpoint = client.recover_lost_turn_receipt(
            "lost-checkpoint-thread",
            baseline_turn_ids=baseline,
            output_contract="checkpoint",
            expected_task_id=TASK_ID,
            expected_workstream_id=WORKSTREAM_ID,
        )
        if checkpoint.turn_id != "lost-checkpoint-turn" or checkpoint.contract.kind != "checkpoint":
            raise AssertionError(f"checkpoint lost receipt was not reconstructed: {checkpoint}")
        if {event.method for event in checkpoint.events} != {"item/completed", "turn/completed"}:
            raise AssertionError(f"snapshot recovery lifecycle evidence is incomplete: {checkpoint.events}")
        if {event.evidence_source for event in checkpoint.events} != {"thread_read_snapshot"}:
            raise AssertionError(f"snapshot recovery provenance was not explicit: {checkpoint.events}")
        if any(event.connection_epoch != client.connection_epoch for event in checkpoint.events):
            raise AssertionError(f"snapshot evidence is not bound to its read connection: {checkpoint.events}")

        try:
            client.recover_lost_turn_receipt(
                "lost-historical-thread",
                baseline_turn_ids=baseline,
                output_contract="checkpoint",
                expected_task_id=TASK_ID,
                expected_workstream_id=WORKSTREAM_ID,
            )
        except CodexContractError:
            pass
        else:
            raise AssertionError(
                "historical recovery silently used the active generation"
            )
        historical = client.recover_lost_turn_receipt(
            "lost-historical-thread",
            baseline_turn_ids=baseline,
            output_contract="checkpoint",
            expected_task_id=TASK_ID,
            expected_workstream_id=WORKSTREAM_ID,
            expected_contract_generation=GENERATION - 1,
        )
        if historical.contract.generation != GENERATION - 1:
            raise AssertionError(
                f"historical generation was not preserved: {historical.contract}"
            )
        try:
            client.recover_lost_turn_receipt(
                "lost-historical-thread",
                baseline_turn_ids=baseline,
                output_contract="checkpoint",
                expected_task_id=TASK_ID,
                expected_workstream_id=WORKSTREAM_ID,
                expected_contract_generation=GENERATION + 1,
            )
        except CodexStaleGenerationError:
            pass
        else:
            raise AssertionError("future recovery contract generation was accepted")
        for identity_thread in (
            "lost-historical-model-thread",
            "lost-historical-reasoning-thread",
            "lost-historical-provider-thread",
        ):
            try:
                client.recover_lost_turn_receipt(
                    identity_thread,
                    baseline_turn_ids=baseline,
                    output_contract="checkpoint",
                    expected_task_id=TASK_ID,
                    expected_workstream_id=WORKSTREAM_ID,
                    expected_contract_generation=GENERATION - 1,
                )
            except CodexIdentityMismatchError:
                pass
            else:
                raise AssertionError(
                    f"historical recovery accepted identity mismatch: {identity_thread}"
                )

        terminal = client.recover_lost_turn_receipt(
            "lost-terminal-thread",
            baseline_turn_ids=baseline,
            output_contract="terminal",
            expected_task_id=TASK_ID,
            expected_workstream_id=WORKSTREAM_ID,
        )
        if terminal.turn_id != "lost-terminal-turn" or terminal.contract.kind != "terminal":
            raise AssertionError(f"terminal lost receipt was not reconstructed: {terminal}")

        tainted_thread_id = "lost-tainted-thread"
        client.resume_thread(tainted_thread_id)
        with client._state_condition:  # smoke-only injection of a same-epoch ambiguous turn
            client._tainted_thread_ids.add(tainted_thread_id)
        calls_before_recovery = len(
            [
                row
                for row in _read_log(fake_log)
                if row.get("event") == "turn_request"
                and row.get("thread_id") == tainted_thread_id
            ]
        )
        recovered_tainted = client.recover_lost_turn_receipt(
            tainted_thread_id,
            baseline_turn_ids=baseline,
            output_contract="checkpoint",
            expected_task_id=TASK_ID,
            expected_workstream_id=WORKSTREAM_ID,
        )
        if recovered_tainted.turn_id != "lost-tainted-turn":
            raise AssertionError(
                f"tainted lost receipt recovered the wrong turn: {recovered_tainted}"
            )
        if tainted_thread_id in client._tainted_thread_ids:
            raise AssertionError("successful exact recovery did not clear the thread taint")
        calls_after_recovery = len(
            [
                row
                for row in _read_log(fake_log)
                if row.get("event") == "turn_request"
                and row.get("thread_id") == tainted_thread_id
            ]
        )
        if calls_after_recovery != calls_before_recovery:
            raise AssertionError("lost receipt recovery unexpectedly repeated the model call")
        post_recovery = client.run_turn(
            tainted_thread_id,
            "post-recovery-serialized-turn",
            output_contract="checkpoint",
            expected_task_id=TASK_ID,
            expected_workstream_id=WORKSTREAM_ID,
            turn_timeout_seconds=2,
        )
        if post_recovery.contract.kind != "checkpoint":
            raise AssertionError(f"post-recovery serialized turn failed: {post_recovery}")

        failure_cases = (
            ("lost-multiple-thread", CodexAmbiguousOutcomeError, "checkpoint"),
            ("lost-incomplete-thread", CodexAmbiguousOutcomeError, "checkpoint"),
            ("lost-failed-thread", CodexTurnFailedError, "checkpoint"),
            ("lost-malformed-thread", CodexContractError, "checkpoint"),
            ("lost-summary-thread", CodexProtocolError, "checkpoint"),
            ("lost-prose-after-contract-thread", CodexContractError, "checkpoint"),
        )
        for thread_id, expected_error, output_contract in failure_cases:
            try:
                client.recover_lost_turn_receipt(
                    thread_id,
                    baseline_turn_ids=baseline,
                    output_contract=output_contract,
                    expected_task_id=TASK_ID,
                    expected_workstream_id=WORKSTREAM_ID,
                )
            except expected_error:
                pass
            else:
                raise AssertionError(
                    f"lost receipt recovery did not fail closed for {thread_id}"
                )

        for invalid_baseline in (
            ("baseline-turn", "lost-checkpoint-turn"),
            ("missing-baseline-turn",),
        ):
            try:
                client.recover_lost_turn_receipt(
                    "lost-checkpoint-thread",
                    baseline_turn_ids=invalid_baseline,
                    output_contract="checkpoint",
                    expected_task_id=TASK_ID,
                    expected_workstream_id=WORKSTREAM_ID,
                )
            except CodexAmbiguousOutcomeError:
                pass
            else:
                raise AssertionError(
                    f"lost receipt recovery accepted ambiguous baseline {invalid_baseline}"
                )
        try:
            client.recover_lost_turn_receipt(
                "lost-checkpoint-thread",
                baseline_turn_ids=("baseline-turn", "baseline-turn"),
                output_contract="checkpoint",
                expected_task_id=TASK_ID,
                expected_workstream_id=WORKSTREAM_ID,
            )
        except ValueError:
            pass
        else:
            raise AssertionError("lost receipt recovery accepted duplicate baseline ids")
    finally:
        client.shutdown()

    recovery_turn_requests = [
        row
        for row in _read_log(fake_log)
        if row.get("event") == "turn_request"
        and row.get("thread_id") in recovery_threads
        and row.get("thread_id") != "lost-tainted-thread"
    ]
    if recovery_turn_requests:
        raise AssertionError(
            f"lost receipt recovery unexpectedly invoked a model turn: {recovery_turn_requests}"
        )
    tainted_turn_requests = [
        row
        for row in _read_log(fake_log)
        if row.get("event") == "turn_request"
        and row.get("thread_id") == "lost-tainted-thread"
    ]
    if len(tainted_turn_requests) != 1:
        raise AssertionError(
            "same-connection recovery must make no model call and permit exactly "
            f"one later serialized turn: {tainted_turn_requests}"
        )


def _assert_stale_generation_fail_closed(
    fake_codex: Path,
    base_env: dict[str, str],
    fake_log: Path,
) -> None:
    stale = {"value": False}
    client = _fake_client(fake_codex, base_env, stale_callback=lambda _generation: stale["value"])
    failure: list[BaseException] = []
    try:
        client.connect()
        identity = client.start_thread()

        def run_turn() -> None:
            try:
                client.run_turn(
                    identity.thread_id,
                    "stale-generation",
                    output_contract="checkpoint",
                    expected_task_id=TASK_ID,
                    expected_workstream_id=WORKSTREAM_ID,
                    turn_timeout_seconds=2,
                )
            except BaseException as exc:  # smoke captures expected stale fence
                failure.append(exc)

        worker = threading.Thread(target=run_turn)
        worker.start()
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if any(row.get("event") == "turn_begin" and row.get("prompt") == "stale-generation" for row in _read_log(fake_log)):
                break
            time.sleep(0.01)
        else:
            raise AssertionError("fake stale-generation turn did not start")
        stale["value"] = True
        worker.join(timeout=3)
        if worker.is_alive():
            raise AssertionError("stale generation did not wake the active turn")
        if len(failure) != 1 or not isinstance(failure[0], CodexStaleGenerationError):
            raise AssertionError(f"stale generation did not fail closed: {failure}")
        late_methods = [event.method for event in client.drain_lifecycle_events() if event.item_id]
        if late_methods:
            raise AssertionError(f"late stale-generation item events were accepted: {late_methods}")
    finally:
        client.shutdown()


def _assert_identity_mismatch_fail_closed(fake_codex: Path, base_env: dict[str, str]) -> None:
    bad_env = dict(base_env)
    bad_env["DCP_FAKE_BAD_MODEL"] = "1"
    client = _fake_client(fake_codex, bad_env, reconnect_attempts=0)
    try:
        try:
            client.connect()
        except CodexIdentityMismatchError:
            pass
        else:
            raise AssertionError("model/list without exact Sol+Ultra must fail closed")
    finally:
        client.shutdown()


def _assert_thread_response_identity_mismatch_fail_closed(
    fake_codex: Path, base_env: dict[str, str]
) -> None:
    for mismatch in (
        "model",
        "provider",
        "effort",
        "effort_null",
        "effort_omitted",
        "effort_non_string",
        "sandbox",
        "network",
        "approval",
        "reviewer",
        "ephemeral",
    ):
        bad_env = dict(base_env)
        bad_env["DCP_FAKE_BAD_THREAD_IDENTITY"] = mismatch
        client = _fake_client(fake_codex, bad_env, reconnect_attempts=0)
        try:
            client.connect()
            try:
                client.start_thread(ephemeral=mismatch == "ephemeral")
            except CodexIdentityMismatchError:
                try:
                    client.read_thread_snapshot("must-remain-fenced")
                except CodexIdentityMismatchError:
                    pass
                else:
                    raise AssertionError(f"thread response {mismatch} mismatch did not fence the adapter")
            else:
                raise AssertionError(f"thread/start response {mismatch} mismatch must fail closed")
        finally:
            client.shutdown()

    for mismatch in ("effort", "effort_null", "effort_omitted", "effort_non_string"):
        bad_env = dict(base_env)
        bad_env["DCP_FAKE_BAD_THREAD_IDENTITY"] = mismatch
        client = _fake_client(
            fake_codex,
            bad_env,
            reconnect_attempts=0,
            owned_thread_ids=("resume-owned-thread",),
        )
        try:
            client.connect()
            try:
                client.resume_thread("resume-owned-thread")
            except CodexIdentityMismatchError:
                pass
            else:
                raise AssertionError(
                    f"thread/resume response {mismatch} must fail closed"
                )
        finally:
            client.shutdown()

    bad_env = dict(base_env)
    bad_env["DCP_FAKE_BAD_THREAD_IDENTITY"] = "network"
    workspace_client = _fake_client(
        fake_codex,
        bad_env,
        reconnect_attempts=0,
        sandbox="workspace-write",
    )
    try:
        workspace_client.connect()
        try:
            workspace_client.start_thread()
        except CodexIdentityMismatchError:
            pass
        else:
            raise AssertionError("workspace-write thread with network access must fail closed")
    finally:
        workspace_client.shutdown()

    # Stored thread snapshots do not guarantee an effort field.  Keep their
    # existing optional-field contract while still rejecting an observed
    # string mismatch.
    snapshot_attestor = CodexAppServerClient(generation=GENERATION)
    for snapshot in ({}, {"reasoningEffort": None}, {"reasoningEffort": 7}):
        snapshot_attestor._attest_optional_identity_fields(snapshot, "thread/read")
    try:
        snapshot_attestor._attest_optional_identity_fields(
            {"reasoningEffort": "high"}, "thread/read"
        )
    except CodexIdentityMismatchError:
        pass
    else:
        raise AssertionError("thread/read accepted an observed reasoning-effort mismatch")


def _assert_validators_fail_closed() -> None:
    for field, value in (("sandbox", "host-write"), ("approval_policy", "always")):
        try:
            CodexAppServerClient(generation=GENERATION, **{field: value})  # type: ignore[arg-type]
        except ValueError:
            pass
        else:
            raise AssertionError(f"adapter accepted unsupported {field}={value!r}")

    default_checkpoint_schema = checkpoint_output_schema()
    default_terminal_schema = terminal_output_schema()
    for label, schema in (
        ("checkpoint", default_checkpoint_schema),
        ("terminal", default_terminal_schema),
    ):
        properties = schema["properties"]
        for field in ("task_id", "workstream_id", "generation"):
            if "const" in properties[field]:
                raise AssertionError(
                    f"default {label} schema helper unexpectedly bound {field}"
                )
    default_checkpoint_schema["properties"]["task_id"]["const"] = "must-not-leak"
    if "const" in checkpoint_output_schema()["properties"]["task_id"]:
        raise AssertionError("default checkpoint schema helper did not return a fresh copy")

    for label, schema in (
        (
            "checkpoint",
            checkpoint_output_schema(
                task_id=TASK_ID,
                workstream_id=WORKSTREAM_ID,
                generation=GENERATION,
            ),
        ),
        (
            "terminal",
            terminal_output_schema(
                task_id=TASK_ID,
                workstream_id=WORKSTREAM_ID,
                generation=GENERATION,
            ),
        ),
    ):
        properties = schema["properties"]
        expected_identity = {
            "task_id": TASK_ID,
            "workstream_id": WORKSTREAM_ID,
            "generation": GENERATION,
        }
        for field, expected in expected_identity.items():
            if properties[field].get("const") != expected:
                raise AssertionError(
                    f"bound {label} schema did not const-bind {field}: {properties[field]}"
                )
    try:
        checkpoint_output_schema(task_id=TASK_ID)
    except ValueError:
        pass
    else:
        raise AssertionError("schema helper accepted a partially bound identity")

    checkpoint_progress_enum = checkpoint_output_schema()["properties"]["progress_percent"]["enum"]
    if 100 in checkpoint_progress_enum:
        raise AssertionError(f"checkpoint output schema exposed terminal progress: {checkpoint_progress_enum}")
    valid_checkpoint = {
        "schema_version": CHECKPOINT_SCHEMA_VERSION,
        "kind": "checkpoint",
        "task_id": TASK_ID,
        "workstream_id": WORKSTREAM_ID,
        "generation": GENERATION,
        "stage": "implementation",
        "progress_percent": 25,
        "delta": "bounded change",
        "current_action": "run checks",
        "evidence": ["diff exists"],
        "causal_fingerprint": None,
    }
    validate_checkpoint_payload(valid_checkpoint, expected_generation=GENERATION)
    invalid_checkpoint = dict(valid_checkpoint)
    invalid_checkpoint["unexpected"] = "field"
    try:
        validate_checkpoint_payload(invalid_checkpoint)
    except CodexContractError:
        pass
    else:
        raise AssertionError("checkpoint validator accepted an extra field")

    terminal_progress = dict(valid_checkpoint)
    terminal_progress["stage"] = "deployed"
    terminal_progress["progress_percent"] = 100
    try:
        validate_checkpoint_payload(terminal_progress)
    except CodexContractError:
        pass
    else:
        raise AssertionError("checkpoint validator accepted terminal progress 100")

    terminal_stage = dict(valid_checkpoint)
    terminal_stage["stage"] = "technical_complete"
    terminal_stage["progress_percent"] = 95
    try:
        validate_checkpoint_payload(terminal_stage)
    except CodexContractError:
        pass
    else:
        raise AssertionError("checkpoint validator accepted the terminal-only technical_complete stage")
    if "technical_complete" in checkpoint_output_schema()["properties"]["stage"]["enum"]:
        raise AssertionError("checkpoint output schema exposed the terminal-only technical_complete stage")

    invalid_terminal = {
        "schema_version": TERMINAL_SCHEMA_VERSION,
        "kind": "terminal",
        "task_id": TASK_ID,
        "workstream_id": WORKSTREAM_ID,
        "generation": GENERATION,
        "status": "completed",
        "summary": "done",
        "checks": [],
        "artifacts": [],
        "limitations": [],
        "blocker": "contradictory blocker",
    }
    try:
        validate_terminal_payload(invalid_terminal)
    except CodexContractError:
        pass
    else:
        raise AssertionError("terminal validator accepted completed+blocker contradiction")


def _assert_spawn_and_turn_identity(rows: list[dict[str, Any]]) -> None:
    spawn_rows = [row for row in rows if row.get("event") == "spawn"]
    if not spawn_rows:
        raise AssertionError("fake server did not record spawn arguments")
    first_args = spawn_rows[0].get("args")
    expected_fragments = (
        f'model="{CODEX_APP_SERVER_MODEL}"',
        f'model_reasoning_effort="{CODEX_APP_SERVER_REASONING_EFFORT}"',
        "app-server",
        "--listen",
        "stdio://",
    )
    if not isinstance(first_args, list) or any(fragment not in first_args for fragment in expected_fragments):
        raise AssertionError(f"spawn args did not pin stdio Sol/Ultra: {first_args}")
    if spawn_rows[0].get("ambient_secret_present") is not False:
        raise AssertionError("Codex child inherited an ambient Supervisor secret")
    if spawn_rows[0].get("explicit_env_probe") != "present":
        raise AssertionError("bounded explicit test environment was not forwarded")
    for forbidden in ("ws://", "daemon", "mcp-server"):
        if any(forbidden in str(value) for value in first_args):
            raise AssertionError(f"spawn args used forbidden transport/surface {forbidden}: {first_args}")

    thread_rows = [row for row in rows if row.get("event") in {"thread_start_request", "thread_resume_request"}]
    if not thread_rows:
        raise AssertionError("fake server did not observe thread/start or thread/resume")
    for row in thread_rows:
        if (
            row.get("sandbox") != "read-only"
            or row.get("approval_policy") != "never"
            or row.get("approvals_reviewer") != "user"
        ):
            raise AssertionError(f"thread operation inherited unsafe permission defaults: {row}")
    if not any(row.get("event") == "thread_start_request" and row.get("ephemeral") is True for row in thread_rows):
        raise AssertionError(f"thread/start did not transmit the explicit ephemeral flag: {thread_rows}")

    turn_rows = [row for row in rows if row.get("event") == "turn_request"]
    if not turn_rows:
        raise AssertionError("fake server did not observe turn/start")
    for row in turn_rows:
        if row.get("model") != CODEX_APP_SERVER_MODEL or row.get("effort") != CODEX_APP_SERVER_REASONING_EFFORT:
            raise AssertionError(f"turn/start did not pin exact model identity: {row}")
        if row.get("schema_kind") not in {"checkpoint", "terminal"}:
            raise AssertionError(f"turn/start did not include an outputSchema: {row}")
        expected_identity = {
            "schema_task_id": TASK_ID,
            "schema_workstream_id": WORKSTREAM_ID,
            "schema_generation": GENERATION,
        }
        for field, expected in expected_identity.items():
            if row.get(field) != expected:
                raise AssertionError(
                    f"turn/start did not const-bind exact contract identity: {row}"
                )


def _assert_schema_bypass_fail_closed(
    fake_codex: Path,
    base_env: dict[str, str],
) -> None:
    client = _fake_client(fake_codex, base_env)
    try:
        client.connect()
        identity = client.start_thread()
        cases = (
            (
                "BYPASS_SCHEMA_GENERATION",
                "checkpoint",
                "contract generation does not match active Supervisor generation",
            ),
            ("BYPASS_SCHEMA_TASK_ID", "checkpoint", "contract task id mismatch"),
            (
                "BYPASS_SCHEMA_WORKSTREAM_ID",
                "terminal",
                "contract workstream id mismatch",
            ),
        )
        for prompt, output_contract, expected_error in cases:
            try:
                client.run_turn(
                    identity.thread_id,
                    prompt,
                    output_contract=output_contract,  # type: ignore[arg-type]
                    expected_task_id=TASK_ID,
                    expected_workstream_id=WORKSTREAM_ID,
                    turn_timeout_seconds=2,
                )
            except CodexContractError as exc:
                if expected_error not in str(exc):
                    raise AssertionError(
                        f"schema bypass failed for the wrong reason: {exc}"
                    ) from exc
            else:
                raise AssertionError(
                    f"post-schema validation accepted {prompt} for {output_contract}"
                )
    finally:
        client.shutdown()


def _run_read_only_canary(
    thread_id: str,
    *,
    codex_bin: str,
    output_path: Path,
    env: Mapping[str, str] | None = None,
    announce: bool = True,
) -> None:
    client = CodexAppServerClient(
        generation=1,
        codex_bin=codex_bin,
        max_reconnect_attempts=0,
        request_timeout_seconds=15,
        env=env,
    )
    try:
        attestation = client.connect()
        thread = client.read_thread_snapshot(thread_id, include_turns=False, timeout_seconds=15)
        payload = sanitized_thread_snapshot(thread, model_attestation=attestation)
        payload["generated_at"] = datetime.now(timezone.utc).isoformat()
        output_path = output_path.expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.chmod(output_path, 0o600)
    finally:
        client.shutdown()
    if announce:
        print(f"read-only Codex App Server canary passed; sanitized result: {output_path}")


def _fake_client(
    fake_codex: Path,
    env: dict[str, str],
    *,
    request_timeout: float = 1.0,
    reconnect_attempts: int = 1,
    sleep_fn=time.sleep,
    jitter_fn=lambda _base: 0.0,
    stale_callback=lambda _generation: False,
    sandbox: str = "read-only",
    owned_thread_ids: tuple[str, ...] = (),
) -> CodexAppServerClient:
    return CodexAppServerClient(
        generation=GENERATION,
        codex_bin=str(fake_codex),
        request_timeout_seconds=request_timeout,
        turn_timeout_seconds=2,
        shutdown_timeout_seconds=0.5,
        max_reconnect_attempts=reconnect_attempts,
        reconnect_backoff_seconds=0.02,
        sleep_fn=sleep_fn,
        jitter_fn=jitter_fn,
        is_stale_generation=stale_callback,
        env=env,
        sandbox=sandbox,
        owned_thread_ids=owned_thread_ids,
    )


def _read_log(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise AssertionError(f"fake server wrote invalid log JSON: {line!r}") from exc
        if isinstance(value, dict):
            rows.append(value)
    return rows


def _write_fake_codex(path: Path) -> None:
    path.write_text(textwrap.dedent(FAKE_CODEX_SOURCE).lstrip(), encoding="utf-8")
    path.chmod(0o700)


FAKE_CODEX_SOURCE = r'''
#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import threading
import time

log_path = Path(os.environ["DCP_FAKE_LOG"])
reconnect_marker = Path(os.environ["DCP_FAKE_RECONNECT_MARKER"])
generation = int(os.environ["DCP_FAKE_GENERATION"])
task_id = os.environ["DCP_FAKE_TASK_ID"]
workstream_id = os.environ["DCP_FAKE_WORKSTREAM_ID"]
bad_model = os.environ.get("DCP_FAKE_BAD_MODEL") == "1"
bad_thread_identity = os.environ.get("DCP_FAKE_BAD_THREAD_IDENTITY", "")
slow_resume = os.environ.get("DCP_FAKE_SLOW_RESUME") == "1"
reject_resume = os.environ.get("DCP_FAKE_REJECT_RESUME") == "1"
stderr_secret = os.environ["DCP_FAKE_STDERR_SECRET"]

write_lock = threading.Lock()
log_lock = threading.Lock()
state_lock = threading.Lock()
thread_counter = 0
turn_counter = 0
active_by_thread = {}
turn_history = {}


def log(payload):
    with log_lock:
        with log_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, sort_keys=True) + "\n")


def send(payload):
    with write_lock:
        sys.stdout.write(json.dumps(payload, separators=(",", ":")) + "\n")
        sys.stdout.flush()


def response(request_id, result):
    send({"id": request_id, "result": result})


def error(request_id, message):
    send({"id": request_id, "error": {"code": -32000, "message": message}})


def prompt_text(params):
    values = []
    for item in params.get("input") or []:
        if isinstance(item, dict) and item.get("type") == "text":
            values.append(str(item.get("text") or ""))
    return "\n".join(values)


def contract_for(kind, prompt=""):
    if kind == "terminal":
        contract = {
            "schema_version": "dev-control-plane.codex-terminal.v1",
            "kind": "terminal",
            "task_id": task_id,
            "workstream_id": workstream_id,
            "generation": generation,
            "status": "completed",
            "summary": "fake terminal proof",
            "checks": [{"name": "fake-smoke", "status": "passed", "evidence": "fake stdio lifecycle completed"}],
            "artifacts": ["fake://artifact"],
            "limitations": ["fake transport only"],
            "blocker": None,
        }
    else:
        contract = {
            "schema_version": "dev-control-plane.codex-checkpoint.v1",
            "kind": "checkpoint",
            "task_id": task_id,
            "workstream_id": workstream_id,
            "generation": generation,
            "stage": "diff_ready",
            "progress_percent": 40,
            "delta": "fake bounded diff is ready",
            "current_action": "run fake checks",
            "evidence": ["fake item lifecycle"],
            "causal_fingerprint": None,
        }
    if "BYPASS_SCHEMA_TASK_ID" in prompt:
        contract["task_id"] = "wrong-task"
    if "BYPASS_SCHEMA_WORKSTREAM_ID" in prompt:
        contract["workstream_id"] = "wrong-workstream"
    if "BYPASS_SCHEMA_GENERATION" in prompt:
        contract["generation"] = generation + 1
    return contract


def recovery_snapshot_turns(thread_id):
    baseline = [{
        "id": "baseline-turn",
        "status": "completed",
        "itemsView": "full",
        "items": [],
    }]

    def turn(turn_id, *, status="completed", items_view="full", items=None):
        return {
            "id": turn_id,
            "status": status,
            "itemsView": items_view,
            "items": list(items or []),
        }

    checkpoint_item = {
        "id": "lost-checkpoint-item",
        "type": "agentMessage",
        "phase": "final_answer",
        "text": json.dumps(contract_for("checkpoint")),
    }
    historical_contract = contract_for("checkpoint")
    historical_contract["generation"] = generation - 1
    historical_item = {
        "id": "lost-historical-item",
        "type": "agentMessage",
        "phase": "final_answer",
        "text": json.dumps(historical_contract),
    }
    terminal_item = {
        "id": "lost-terminal-item",
        "type": "agentMessage",
        "phase": "final_answer",
        "text": json.dumps(contract_for("terminal")),
    }
    if thread_id == "lost-checkpoint-thread":
        return baseline + [turn(
            "lost-checkpoint-turn",
            items=[
                {
                    "id": "lost-checkpoint-commentary",
                    "type": "agentMessage",
                    "phase": "commentary",
                    "text": "progress prose is not the schema-bound output",
                },
                checkpoint_item,
            ],
        )]
    if thread_id == "lost-historical-thread":
        return baseline + [turn(
            "lost-historical-turn",
            items=[historical_item],
        )]
    if thread_id == "lost-historical-model-thread":
        return baseline + [{
            **turn(
                "lost-historical-model-turn",
                items=[dict(historical_item, id="lost-historical-model-item")],
            ),
            "model": "gpt-5.6-terra",
        }]
    if thread_id == "lost-historical-reasoning-thread":
        return baseline + [{
            **turn(
                "lost-historical-reasoning-turn",
                items=[dict(historical_item, id="lost-historical-reasoning-item")],
            ),
            "reasoningEffort": "high",
        }]
    if thread_id == "lost-historical-provider-thread":
        return baseline + [{
            **turn(
                "lost-historical-provider-turn",
                items=[dict(historical_item, id="lost-historical-provider-item")],
            ),
            "modelProvider": "unexpected-provider",
        }]
    if thread_id == "lost-terminal-thread":
        return baseline + [turn("lost-terminal-turn", items=[terminal_item])]
    if thread_id == "lost-tainted-thread":
        return baseline + [turn(
            "lost-tainted-turn",
            items=[dict(checkpoint_item, id="lost-tainted-item")],
        )]
    if thread_id == "lost-multiple-thread":
        return baseline + [
            turn("lost-multiple-turn-1", items=[checkpoint_item]),
            turn(
                "lost-multiple-turn-2",
                items=[dict(checkpoint_item, id="lost-checkpoint-item-2")],
            ),
        ]
    if thread_id == "lost-incomplete-thread":
        return baseline + [turn(
            "lost-incomplete-turn", status="inProgress", items=[checkpoint_item]
        )]
    if thread_id == "lost-failed-thread":
        return baseline + [turn(
            "lost-failed-turn", status="failed", items=[checkpoint_item]
        )]
    if thread_id == "lost-malformed-thread":
        return baseline + [turn(
            "lost-malformed-turn",
            items=[dict(checkpoint_item, id="lost-malformed-item", text="{not-json")],
        )]
    if thread_id == "lost-summary-thread":
        return baseline + [turn(
            "lost-summary-turn", items_view="summary", items=[checkpoint_item]
        )]
    if thread_id == "lost-prose-after-contract-thread":
        return baseline + [turn(
            "lost-prose-after-contract-turn",
            items=[
                dict(checkpoint_item, id="lost-early-contract-item", phase=None),
                {
                    "id": "lost-trailing-prose-item",
                    "type": "agentMessage",
                    "text": "arbitrary trailing prose must never be scanned as a contract",
                },
            ],
        )]
    return None


def sandbox_response(mode):
    if mode == "workspace-write":
        return {"type": "workspaceWrite", "networkAccess": False, "writableRoots": []}
    if mode == "danger-full-access":
        return {"type": "dangerFullAccess"}
    return {"type": "readOnly", "networkAccess": False}


def thread_payload(thread_id, *, cwd, ephemeral):
    return {
        "id": thread_id,
        "sessionId": thread_id,
        "cliVersion": "fake-1",
        "createdAt": 1,
        "updatedAt": 1,
        "cwd": cwd,
        "ephemeral": ephemeral,
        "modelProvider": "openai",
        "preview": "fake",
        "source": "appServer",
        "status": {"type": "idle"},
        "turns": [],
    }


def complete_turn(thread_id, turn_id, kind, prompt):
    send({"method": "turn/started", "params": {"threadId": thread_id, "turn": {"id": turn_id, "status": "inProgress", "items": []}}})
    time.sleep(0.08)
    item_id = "item-" + turn_id
    send({"method": "item/started", "params": {"threadId": thread_id, "turnId": turn_id, "startedAtMs": 1, "item": {"id": item_id, "type": "agentMessage", "text": "", "status": "inProgress"}}})
    contract = contract_for(kind, prompt)
    item_completed = {"method": "item/completed", "params": {"threadId": thread_id, "turnId": turn_id, "completedAtMs": 2, "item": {"id": item_id, "type": "agentMessage", "text": json.dumps(contract), "status": "completed"}}}
    send(item_completed)
    send(item_completed)
    turn_completed = {"method": "turn/completed", "params": {"threadId": thread_id, "turn": {"id": turn_id, "status": "completed", "items": []}}}
    send(turn_completed)
    send(turn_completed)
    with state_lock:
        turn_history.setdefault(thread_id, []).append({"id": turn_id, "status": "completed", "items": [{"id": item_id, "type": "agentMessage", "text": json.dumps(contract)}]})
        active_by_thread[thread_id] -= 1
        active = active_by_thread[thread_id]
    log({"event": "turn_end", "thread_id": thread_id, "turn_id": turn_id, "active": active})


log({
    "event": "spawn",
    "args": sys.argv[1:],
    "ambient_secret_present": "DCP_PARENT_SECRET_MUST_NOT_REACH_CODEX" in os.environ,
    "explicit_env_probe": os.environ.get("DCP_EXPLICIT_ENV_PROBE"),
})
print("Authorization: Bearer " + stderr_secret, file=sys.stderr, flush=True)
print("refresh_token=" + stderr_secret, file=sys.stderr, flush=True)

for line in sys.stdin:
    try:
        message = json.loads(line)
    except json.JSONDecodeError:
        continue
    method = message.get("method")
    request_id = message.get("id")
    params = message.get("params") or {}
    if method == "initialize":
        response(request_id, {"userAgent": "fake-codex-app-server", "platformFamily": "unix", "platformOs": "fake"})
    elif method == "initialized":
        continue
    elif method == "model/list":
        efforts = ["low", "medium", "high", "xhigh", "max"] if bad_model else ["low", "medium", "high", "xhigh", "max", "ultra"]
        response(request_id, {"data": [{
            "id": "gpt-5.6-sol",
            "model": "gpt-5.6-sol",
            "displayName": "GPT-5.6 Sol",
            "description": "fake exact model catalog row",
            "defaultReasoningEffort": "high",
            "hidden": False,
            "isDefault": False,
            "supportedReasoningEfforts": [{"reasoningEffort": value, "description": "fake effort"} for value in efforts],
        }], "nextCursor": None})
    elif method == "thread/start":
        log({"event": "thread_start_request", "sandbox": params.get("sandbox"), "approval_policy": params.get("approvalPolicy"), "approvals_reviewer": params.get("approvalsReviewer"), "ephemeral": params.get("ephemeral")})
        if params.get("model") != "gpt-5.6-sol" or params.get("sandbox") not in {"read-only", "workspace-write", "danger-full-access"} or params.get("approvalPolicy") not in {"untrusted", "on-request", "never"}:
            error(request_id, "thread identity or permission mismatch")
            continue
        thread_counter += 1
        thread_id = "fake-thread-" + str(thread_counter)
        requested_ephemeral = params.get("ephemeral") is True
        thread = thread_payload(thread_id, cwd=params.get("cwd") or os.getcwd(), ephemeral=(not requested_ephemeral if bad_thread_identity == "ephemeral" else requested_ephemeral))
        thread_response = {
            "thread": thread,
            "cwd": thread["cwd"],
            "model": "gpt-5.6-terra" if bad_thread_identity == "model" else "gpt-5.6-sol",
            "modelProvider": "local" if bad_thread_identity == "provider" else "openai",
            "approvalPolicy": "on-request" if bad_thread_identity == "approval" else params.get("approvalPolicy"),
            "approvalsReviewer": "auto_review" if bad_thread_identity == "reviewer" else params.get("approvalsReviewer"),
            "sandbox": (
                {"type": "dangerFullAccess"}
                if bad_thread_identity == "sandbox"
                else (
                    dict(sandbox_response(params.get("sandbox")), networkAccess=True)
                    if bad_thread_identity == "network"
                    else sandbox_response(params.get("sandbox"))
                )
            ),
        }
        if bad_thread_identity != "effort_omitted":
            thread_response["reasoningEffort"] = (
                "high"
                if bad_thread_identity == "effort"
                else None
                if bad_thread_identity == "effort_null"
                else {"unexpected": "ultra"}
                if bad_thread_identity == "effort_non_string"
                else "ultra"
            )
        response(request_id, thread_response)
        send({"method": "thread/started", "params": {"thread": thread}})
    elif method == "thread/resume":
        thread_id = params.get("threadId")
        log({"event": "thread_resume_request", "sandbox": params.get("sandbox"), "approval_policy": params.get("approvalPolicy"), "approvals_reviewer": params.get("approvalsReviewer")})
        if reject_resume:
            error(request_id, "empty thread has no persisted rollout")
            continue
        if slow_resume:
            time.sleep(0.20)
        thread = thread_payload(thread_id, cwd=params.get("cwd") or os.getcwd(), ephemeral=False)
        thread_response = {
            "thread": thread,
            "cwd": thread["cwd"],
            "model": "gpt-5.6-sol",
            "modelProvider": "openai",
            "approvalPolicy": params.get("approvalPolicy"),
            "approvalsReviewer": params.get("approvalsReviewer"),
            "sandbox": sandbox_response(params.get("sandbox")),
        }
        if bad_thread_identity != "effort_omitted":
            thread_response["reasoningEffort"] = (
                "high"
                if bad_thread_identity == "effort"
                else None
                if bad_thread_identity == "effort_null"
                else {"unexpected": "ultra"}
                if bad_thread_identity == "effort_non_string"
                else "ultra"
            )
        response(request_id, thread_response)
        send({"method": "thread/started", "params": {"thread": thread}})
    elif method == "turn/start":
        schema = params.get("outputSchema") or {}
        properties = schema.get("properties") or {}
        kind = (properties.get("kind") or {}).get("const")
        schema_task_id = (properties.get("task_id") or {}).get("const")
        schema_workstream_id = (properties.get("workstream_id") or {}).get("const")
        schema_generation = (properties.get("generation") or {}).get("const")
        prompt = prompt_text(params)
        log({"event": "turn_request", "thread_id": params.get("threadId"), "model": params.get("model"), "effort": params.get("effort"), "schema_kind": kind, "schema_task_id": schema_task_id, "schema_workstream_id": schema_workstream_id, "schema_generation": schema_generation})
        if (
            params.get("model") != "gpt-5.6-sol"
            or params.get("effort") != "ultra"
            or kind not in {"checkpoint", "terminal"}
            or schema_task_id != task_id
            or schema_workstream_id != workstream_id
            or schema_generation != generation
        ):
            error(request_id, "turn identity or schema mismatch")
            continue
        if "SLOW_REQUEST" in prompt:
            time.sleep(0.20)
        turn_counter += 1
        turn_id = "fake-turn-" + str(turn_counter)
        thread_id = params.get("threadId")
        with state_lock:
            active_by_thread[thread_id] = active_by_thread.get(thread_id, 0) + 1
            active = active_by_thread[thread_id]
        log({"event": "turn_begin", "thread_id": thread_id, "turn_id": turn_id, "active": active, "prompt": prompt})
        response(request_id, {"turn": {"id": turn_id, "status": "inProgress", "items": [], "model": "gpt-5.6-sol", "effort": "ultra"}})
        if "REROUTE" in prompt:
            send({"method": "model/rerouted", "params": {"threadId": thread_id, "turnId": turn_id, "fromModel": "gpt-5.6-sol", "toModel": "gpt-5.6-terra", "reason": "fake"}})
        else:
            threading.Thread(target=complete_turn, args=(thread_id, turn_id, kind, prompt), daemon=True).start()
    elif method == "thread/read":
        thread_id = params.get("threadId")
        if thread_id == "timeout-thread":
            time.sleep(0.30)
        if thread_id == "reconnect-thread" and not reconnect_marker.exists():
            reconnect_marker.write_text("disconnected", encoding="utf-8")
            os._exit(17)
        fixture_turns = recovery_snapshot_turns(thread_id)
        if fixture_turns is not None:
            turns = fixture_turns if params.get("includeTurns") else []
        else:
            with state_lock:
                turns = list(turn_history.get(thread_id, []))
            if params.get("includeTurns"):
                turns.append({"id": "historic-turn", "status": "completed", "items": [{"id": "historic-item", "type": "agentMessage", "text": "historic"}]})
        thread = thread_payload(thread_id, cwd=os.getcwd(), ephemeral=False)
        thread.update({"model": "gpt-5.6-sol", "reasoningEffort": "ultra", "turns": turns})
        response(request_id, {"thread": thread})
    else:
        error(request_id, "unsupported fake method")
'''


if __name__ == "__main__":
    main()
