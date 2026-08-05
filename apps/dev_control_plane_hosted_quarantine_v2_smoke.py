"""Deterministic smoke for hosted projection-v2 quarantine recovery contracts.

The smoke imports the deploy runner as a module and replaces every transport
boundary.  It must never resolve DNS, open SSH, or mutate a remote host.
"""

from __future__ import annotations

from contextlib import contextmanager, redirect_stderr
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from typing import Any, Callable, Iterator


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "apps" / "dev_control_plane_hosted_deploy.py"
FAILED_SHA = "a" * 40
REPLACEMENT_SHA = "b" * 40
PRIOR_SHA = "c" * 40
SNAPSHOT_SHA256 = "d" * 64
QUARANTINE_RECEIPT_SHA256 = "e" * 64
REPLACEMENT_ANCHOR_SHA256 = "9" * 64
ATTEMPT_ID = "1" * 32
SENSITIVE_SENTINEL = "raw-provider-token-must-not-escape"


def main() -> None:
    deploy = _load_runner()
    _assert_cli_parser_wiring(deploy)
    _assert_status_parser_and_sanitization(deploy)
    _assert_status_handler_gates(deploy)
    _assert_resolve_identity_and_gate_matrix(deploy)
    _assert_resolve_cas_and_idempotency(deploy)
    _assert_generated_script_safety_and_ordering(deploy)
    print("dev-control-plane-hosted-quarantine-v2-smoke passed")


def _assert_cli_parser_wiring(deploy: Any) -> None:
    calls: list[tuple[str, Any]] = []

    def status_handler(args: Any) -> int:
        calls.append(("status", args))
        return 17

    def resolve_handler(args: Any) -> int:
        calls.append(("resolve", args))
        return 19

    with _patched(
        deploy,
        _handle_quarantine_status=status_handler,
        _handle_quarantine_resolve=resolve_handler,
    ):
        assert deploy.main(["quarantine-status", "--release-sha", FAILED_SHA]) == 17
        assert calls[-1][0] == "status"
        assert calls[-1][1].release_sha == FAILED_SHA

        assert deploy.main(
            [
                "quarantine-resolve",
                "--release-sha",
                FAILED_SHA,
                "--snapshot-sha256",
                SNAPSHOT_SHA256,
                "--replacement-sha",
                REPLACEMENT_SHA,
                "--dry-run",
            ]
        ) == 19
        resolve_args = calls[-1][1]
        assert calls[-1][0] == "resolve"
        assert resolve_args.dry_run is True and resolve_args.live is False
        assert resolve_args.release_sha == FAILED_SHA
        assert resolve_args.snapshot_sha256 == SNAPSHOT_SHA256
        assert resolve_args.replacement_sha == REPLACEMENT_SHA

        error_output = io.StringIO()
        with redirect_stderr(error_output):
            try:
                deploy.main(
                    [
                        "quarantine-resolve",
                        "--release-sha",
                        FAILED_SHA,
                        "--snapshot-sha256",
                        SNAPSHOT_SHA256,
                        "--replacement-sha",
                        REPLACEMENT_SHA,
                    ]
                )
            except SystemExit as exc:
                assert exc.code == 2
            else:
                raise AssertionError("quarantine-resolve accepted no execution mode")

        with redirect_stderr(io.StringIO()):
            try:
                deploy.main(
                    [
                        "quarantine-resolve",
                        "--release-sha",
                        FAILED_SHA,
                        "--snapshot-sha256",
                        SNAPSHOT_SHA256,
                        "--replacement-sha",
                        REPLACEMENT_SHA,
                        "--dry-run",
                        "--live",
                    ]
                )
            except SystemExit as exc:
                assert exc.code == 2
            else:
                raise AssertionError("quarantine-resolve accepted both execution modes")


def _assert_status_parser_and_sanitization(deploy: Any) -> None:
    commands: list[str] = []

    def successful_ssh(command: str) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return subprocess.CompletedProcess(
            ["ssh"],
            0,
            _status_stdout(),
            SENSITIVE_SENTINEL,
        )

    with _patched(deploy, _ssh=successful_ssh):
        evidence = deploy._remote_quarantine_status(FAILED_SHA)

    assert len(commands) == 1
    status_script = commands[0]
    assert "flock -w 30 -s 9" in status_script
    for forbidden in (
        "systemctl start",
        "systemctl stop",
        "systemctl enable",
        "systemctl disable",
        "mv -Tf",
        "unlink ",
        "rm -",
    ):
        assert forbidden not in status_script, forbidden
    assert evidence == _expected_evidence()
    assert SENSITIVE_SENTINEL not in json.dumps(evidence, sort_keys=True)
    assert evidence["raw_remote_payload_exposed"] is False
    assert evidence["failed_release_layout"] == "absent"
    assert evidence["legacy_layout"] == "legacy_directory_pending_archive"
    assert evidence["app_present"] is True
    assert evidence["legacy_archive_present"] is False
    assert evidence["legacy_normalization_required"] is True

    archived_stdout = _status_stdout(legacy_layout="archived_absent_pointer")
    with _patched(
        deploy,
        _ssh=lambda _command: subprocess.CompletedProcess(
            ["ssh"], 0, archived_stdout, SENSITIVE_SENTINEL
        ),
    ):
        archived = deploy._remote_quarantine_status(FAILED_SHA)
    assert archived == _expected_evidence(legacy_layout="archived_absent_pointer")
    assert archived["app_present"] is False
    assert archived["legacy_archive_present"] is True
    assert archived["legacy_normalization_required"] is False

    resolved_stdout = _status_stdout(
        legacy_layout="archived_absent_pointer",
        disposition="resolved_safe_disabled",
        replacement_sha=REPLACEMENT_SHA,
    )
    with _patched(
        deploy,
        _ssh=lambda _command: subprocess.CompletedProcess(
            ["ssh"], 0, resolved_stdout, SENSITIVE_SENTINEL
        ),
    ):
        resolved = deploy._remote_quarantine_status(FAILED_SHA)
    assert resolved["disposition"] == "resolved_safe_disabled"
    assert resolved["replacement_sha"] == REPLACEMENT_SHA
    assert resolved["replacement_anchor_sha256"] == REPLACEMENT_ANCHOR_SHA256
    assert resolved["replacement_supersession_eligible"] is True

    legacy_unfenced_stdout = _status_stdout(attempt_id="none")
    with _patched(
        deploy,
        _ssh=lambda _command: subprocess.CompletedProcess(
            ["ssh"], 0, legacy_unfenced_stdout, SENSITIVE_SENTINEL
        ),
    ):
        legacy_unfenced = deploy._remote_quarantine_status(FAILED_SHA)
    assert legacy_unfenced == _expected_evidence(attempt_id=None)

    invalid_payloads = (
        _status_stdout(release_sha=REPLACEMENT_SHA),
        _status_stdout(snapshot_sha256="f" * 63),
        _status_stdout(attempt_id="unsafe-attempt"),
        _status_stdout(failed_release_layout="unsafe"),
        _status_stdout(prior_kind="legacy", prior_release_sha=PRIOR_SHA),
        _status_stdout(last_stage="unsafe/stage"),
        _status_stdout(disposition="unresolved", replacement_sha=REPLACEMENT_SHA),
        _status_stdout(disposition="resolved_safe_disabled", replacement_sha="none"),
        _status_stdout(
            replacement_anchor_sha256=REPLACEMENT_ANCHOR_SHA256,
        ),
        _status_stdout(replacement_supersession_eligible="yes"),
        _status_stdout(
            disposition="resolved_safe_disabled",
            replacement_sha=REPLACEMENT_SHA,
            replacement_anchor_sha256="f" * 63,
        ),
        _status_stdout(
            disposition="resolved_safe_disabled",
            replacement_sha=REPLACEMENT_SHA,
            replacement_supersession_eligible="unsafe",
        ),
        _status_stdout(
            legacy_layout="legacy_directory_pending_archive",
            current_app_present="no",
        ),
        _status_stdout(
            legacy_layout="archived_absent_pointer",
            current_app_present="yes",
        ),
        _status_stdout(legacy_layout="unsafe_layout"),
        _status_stdout(extra_line="raw_payload=provider-secret"),
        _status_stdout() + f"release_sha={FAILED_SHA}\n",
    )
    for payload in invalid_payloads:
        with _patched(
            deploy,
            _ssh=lambda _command, value=payload: subprocess.CompletedProcess(
                ["ssh"], 0, value, SENSITIVE_SENTINEL
            ),
        ):
            _expect_runtime(
                "quarantine_status_receipt_invalid",
                lambda: deploy._remote_quarantine_status(FAILED_SHA),
            )

    with _patched(
        deploy,
        _ssh=lambda _command: subprocess.CompletedProcess(
            ["ssh"], 255, "", SENSITIVE_SENTINEL
        ),
    ):
        _expect_runtime(
            "quarantine_status_unavailable_or_unsafe",
            lambda: deploy._remote_quarantine_status(FAILED_SHA),
        )

    _expect_runtime(
        "quarantine_status_release_identity_invalid",
        lambda: deploy._remote_quarantine_status_script("../unsafe"),
    )


def _assert_status_handler_gates(deploy: Any) -> None:
    payloads: list[dict[str, Any]] = []
    remote_calls: list[str] = []
    target_calls: list[str] = []

    def target_gate() -> dict[str, Any]:
        target_calls.append("target")
        return {"status": "passed", "blockers": []}

    def remote_status(release_sha: str) -> dict[str, Any]:
        remote_calls.append(release_sha)
        return _expected_evidence()

    with _patched(
        deploy,
        _local_ssh_target_gate=target_gate,
        _remote_quarantine_status=remote_status,
        _print_json=lambda payload: payloads.append(payload),
    ):
        result = deploy._handle_quarantine_status(SimpleNamespace(release_sha="bad"))
        assert result == 1
        assert payloads[-1] == {
            "status": "blocked",
            "blockers": ["invalid_quarantine_release_sha"],
        }
        assert not target_calls and not remote_calls

        result = deploy._handle_quarantine_status(SimpleNamespace(release_sha=FAILED_SHA))
        assert result == 0
        assert target_calls == ["target"] and remote_calls == [FAILED_SHA]
        assert payloads[-1] == {
            "status": "quarantined_safe_disabled",
            "evidence": _expected_evidence(),
        }

    payloads.clear()
    with _patched(
        deploy,
        _local_ssh_target_gate=lambda: {
            "status": "blocked",
            "blockers": ["ssh_alias_target_ip_mismatch"],
        },
        _remote_quarantine_status=lambda _sha: (_ for _ in ()).throw(
            AssertionError("status handler crossed a blocked SSH target gate")
        ),
        _print_json=lambda payload: payloads.append(payload),
    ):
        assert deploy._handle_quarantine_status(SimpleNamespace(release_sha=FAILED_SHA)) == 1
        assert payloads[-1]["blockers"] == ["ssh_alias_target_ip_mismatch"]


def _assert_resolve_identity_and_gate_matrix(deploy: Any) -> None:
    base_args = {
        "release_sha": FAILED_SHA,
        "snapshot_sha256": SNAPSHOT_SHA256,
        "replacement_sha": REPLACEMENT_SHA,
        "dry_run": True,
        "live": False,
    }

    for override, reason in (
        ({"release_sha": "bad"}, "invalid_quarantine_release_sha"),
        ({"snapshot_sha256": "f" * 63}, "invalid_quarantine_snapshot_sha256"),
        ({"snapshot_sha256": "F" * 64}, "invalid_quarantine_snapshot_sha256"),
        ({"replacement_sha": "bad"}, "invalid_or_reused_quarantine_replacement_sha"),
        (
            {"replacement_sha": FAILED_SHA},
            "invalid_or_reused_quarantine_replacement_sha",
        ),
    ):
        payloads: list[dict[str, Any]] = []
        with _patched(
            deploy,
            _source_gate=lambda **_kwargs: (_ for _ in ()).throw(
                AssertionError("invalid identity reached source gate")
            ),
            _local_ssh_target_gate=lambda: (_ for _ in ()).throw(
                AssertionError("invalid identity reached SSH gate")
            ),
            _print_json=lambda payload: payloads.append(payload),
        ):
            args = SimpleNamespace(**(base_args | override))
            assert deploy._handle_quarantine_resolve(args) == 1
            assert payloads[-1]["blockers"] == [reason]
            assert payloads[-1]["live_executed"] is False

    for source_result in (
        _source_result(head_sha=PRIOR_SHA),
        _source_result(head_sha=REPLACEMENT_SHA, status="blocked"),
    ):
        payloads = []
        target_calls: list[str] = []
        with _patched(
            deploy,
            _source_gate=lambda **_kwargs: source_result,
            _local_ssh_target_gate=lambda: target_calls.append("target") or {
                "status": "passed",
                "blockers": [],
            },
            _print_json=lambda payload: payloads.append(payload),
        ):
            assert deploy._handle_quarantine_resolve(SimpleNamespace(**base_args)) == 1
            assert payloads[-1]["blockers"] == [
                "quarantine_replacement_not_exact_origin_main"
            ]
            assert not target_calls

    payloads.clear()
    source_calls: list[dict[str, Any]] = []
    with _patched(
        deploy,
        _source_gate=lambda **kwargs: source_calls.append(kwargs)
        or _source_result(head_sha=REPLACEMENT_SHA),
        _local_ssh_target_gate=lambda: {
            "status": "blocked",
            "blockers": ["ssh_trusted_host_key_missing"],
        },
        _remote_quarantine_status=lambda _sha: (_ for _ in ()).throw(
            AssertionError("blocked SSH target reached remote status")
        ),
        _print_json=lambda payload: payloads.append(payload),
    ):
        assert deploy._handle_quarantine_resolve(SimpleNamespace(**base_args)) == 1
        assert source_calls == [{"enforced": True, "fetch_origin": True}]
        assert payloads[-1]["blockers"] == ["ssh_trusted_host_key_missing"]

    _assert_resolve_dry_run_and_digest_cas(deploy, base_args)
    _assert_resolve_supersession_gates(deploy, base_args)
    _assert_resolve_live_readback_gates(deploy, base_args)


def _assert_resolve_dry_run_and_digest_cas(
    deploy: Any, base_args: dict[str, Any]
) -> None:
    payloads: list[dict[str, Any]] = []
    source_calls: list[dict[str, Any]] = []
    target_calls: list[str] = []
    resolve_calls: list[tuple[tuple[str, ...], dict[str, Any]]] = []

    with _patched(
        deploy,
        _source_gate=lambda **kwargs: source_calls.append(kwargs)
        or _source_result(head_sha=REPLACEMENT_SHA),
        _local_ssh_target_gate=lambda: target_calls.append("target") or {
            "status": "passed",
            "blockers": [],
        },
        _remote_quarantine_status=lambda _sha: _expected_evidence(),
        _resolve_remote_quarantine=lambda *args: resolve_calls.append(args),
        _print_json=lambda payload: payloads.append(payload),
    ):
        assert deploy._handle_quarantine_resolve(SimpleNamespace(**base_args)) == 0
        assert source_calls == [{"enforced": True, "fetch_origin": True}]
        assert target_calls == ["target"]
        assert not resolve_calls
        assert payloads[-1]["status"] == "dry_run_passed"
        assert payloads[-1]["live_executed"] is False
        assert payloads[-1]["replacement_sha"] == REPLACEMENT_SHA

    payloads.clear()
    mismatched = _expected_evidence() | {"snapshot_sha256": "f" * 64}
    with _patched(
        deploy,
        _source_gate=lambda **_kwargs: _source_result(head_sha=REPLACEMENT_SHA),
        _local_ssh_target_gate=lambda: {"status": "passed", "blockers": []},
        _remote_quarantine_status=lambda _sha: mismatched,
        _resolve_remote_quarantine=lambda *_args: (_ for _ in ()).throw(
            AssertionError("digest mismatch reached resolver")
        ),
        _print_json=lambda payload: payloads.append(payload),
    ):
        assert deploy._handle_quarantine_resolve(SimpleNamespace(**base_args)) == 1
        assert payloads[-1]["blockers"] == ["quarantine_snapshot_digest_mismatch"]
        assert payloads[-1]["live_executed"] is False


def _assert_resolve_supersession_gates(
    deploy: Any, base_args: dict[str, Any]
) -> None:
    prior_evidence = _expected_evidence(
        disposition="resolved_safe_disabled",
        replacement_sha=PRIOR_SHA,
    )
    payloads: list[dict[str, Any]] = []

    with _patched(
        deploy,
        _source_gate=lambda **_kwargs: _source_result(head_sha=REPLACEMENT_SHA),
        _local_ssh_target_gate=lambda: {"status": "passed", "blockers": []},
        _remote_quarantine_status=lambda _sha: prior_evidence
        | {"replacement_supersession_eligible": False},
        _git_is_ancestor=lambda *_args: (_ for _ in ()).throw(
            AssertionError("ineligible replacement reached ancestry probe")
        ),
        _resolve_remote_quarantine=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("ineligible replacement reached resolver")
        ),
        _print_json=lambda payload: payloads.append(payload),
    ):
        assert deploy._handle_quarantine_resolve(SimpleNamespace(**base_args)) == 1
        assert payloads[-1]["blockers"] == [
            "quarantine_replacement_supersession_not_admitted"
        ]

    payloads.clear()
    ancestry_calls: list[tuple[str, str]] = []
    with _patched(
        deploy,
        _source_gate=lambda **_kwargs: _source_result(head_sha=REPLACEMENT_SHA),
        _local_ssh_target_gate=lambda: {"status": "passed", "blockers": []},
        _remote_quarantine_status=lambda _sha: prior_evidence,
        _git_is_ancestor=lambda prior, successor: ancestry_calls.append(
            (prior, successor)
        )
        or False,
        _resolve_remote_quarantine=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("non-descendant replacement reached resolver")
        ),
        _print_json=lambda payload: payloads.append(payload),
    ):
        assert deploy._handle_quarantine_resolve(SimpleNamespace(**base_args)) == 1
        assert ancestry_calls == [(PRIOR_SHA, REPLACEMENT_SHA)]
        assert payloads[-1]["blockers"] == [
            "quarantine_replacement_supersession_not_admitted"
        ]

    payloads.clear()
    ancestry_calls.clear()
    with _patched(
        deploy,
        _source_gate=lambda **_kwargs: _source_result(head_sha=REPLACEMENT_SHA),
        _local_ssh_target_gate=lambda: {"status": "passed", "blockers": []},
        _remote_quarantine_status=lambda _sha: prior_evidence,
        _git_is_ancestor=lambda prior, successor: ancestry_calls.append(
            (prior, successor)
        )
        or True,
        _resolve_remote_quarantine=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("dry-run reached resolver")
        ),
        _print_json=lambda payload: payloads.append(payload),
    ):
        assert deploy._handle_quarantine_resolve(SimpleNamespace(**base_args)) == 0
        assert ancestry_calls == [(PRIOR_SHA, REPLACEMENT_SHA)]
        assert payloads[-1]["status"] == "dry_run_passed"
        assert payloads[-1]["evidence"] == prior_evidence


def _assert_resolve_live_readback_gates(
    deploy: Any, base_args: dict[str, Any]
) -> None:
    live_args = SimpleNamespace(**(base_args | {"dry_run": False, "live": True}))

    payloads: list[dict[str, Any]] = []
    target_results = iter(
        (
            {"status": "passed", "blockers": []},
            {"status": "blocked", "blockers": ["changed"]},
        )
    )
    with _patched(
        deploy,
        _source_gate=lambda **_kwargs: _source_result(head_sha=REPLACEMENT_SHA),
        _local_ssh_target_gate=lambda: next(target_results),
        _remote_quarantine_status=lambda _sha: _expected_evidence(),
        _resolve_remote_quarantine=lambda *_args: (_ for _ in ()).throw(
            AssertionError("changed SSH gate reached resolver")
        ),
        _print_json=lambda payload: payloads.append(payload),
    ):
        assert deploy._handle_quarantine_resolve(live_args) == 1
        assert payloads[-1]["blockers"] == [
            "ssh_target_gate_changed_before_quarantine_resolution"
        ]

    payloads.clear()
    source_results = iter(
        (
            _source_result(head_sha=REPLACEMENT_SHA),
            _source_result(head_sha=PRIOR_SHA),
        )
    )
    with _patched(
        deploy,
        _source_gate=lambda **_kwargs: next(source_results),
        _local_ssh_target_gate=lambda: {"status": "passed", "blockers": []},
        _remote_quarantine_status=lambda _sha: _expected_evidence(),
        _resolve_remote_quarantine=lambda *_args: (_ for _ in ()).throw(
            AssertionError("changed source gate reached resolver")
        ),
        _print_json=lambda payload: payloads.append(payload),
    ):
        assert deploy._handle_quarantine_resolve(live_args) == 1
        assert payloads[-1]["blockers"] == ["source_changed_before_quarantine_resolution"]

    payloads.clear()
    source_calls: list[dict[str, Any]] = []
    target_calls: list[str] = []
    resolve_calls: list[tuple[tuple[str, ...], dict[str, Any]]] = []
    resolved = _expected_evidence(
        legacy_layout="archived_absent_pointer",
        disposition="resolved_safe_disabled",
        replacement_sha=REPLACEMENT_SHA,
    )
    prior_evidence = _expected_evidence(
        disposition="resolved_safe_disabled",
        replacement_sha=PRIOR_SHA,
    )

    def resolver(*args: str, **kwargs: Any) -> dict[str, Any]:
        resolve_calls.append((args, kwargs))
        return resolved

    with _patched(
        deploy,
        _source_gate=lambda **kwargs: source_calls.append(kwargs)
        or _source_result(head_sha=REPLACEMENT_SHA),
        _local_ssh_target_gate=lambda: target_calls.append("target") or {
            "status": "passed",
            "blockers": [],
        },
        _remote_quarantine_status=lambda _sha: prior_evidence,
        _git_is_ancestor=lambda prior, successor: (
            prior,
            successor,
        )
        == (PRIOR_SHA, REPLACEMENT_SHA),
        _resolve_remote_quarantine=resolver,
        _print_json=lambda payload: payloads.append(payload),
    ):
        assert deploy._handle_quarantine_resolve(live_args) == 0
        assert source_calls == [
            {"enforced": True, "fetch_origin": True},
            {"enforced": True, "fetch_origin": True},
        ]
        assert target_calls == ["target", "target"]
        assert resolve_calls == [
            (
                (FAILED_SHA, SNAPSHOT_SHA256, REPLACEMENT_SHA),
                {
                    "expected_prior_replacement": PRIOR_SHA,
                    "expected_prior_anchor_sha256": REPLACEMENT_ANCHOR_SHA256,
                },
            )
        ]
        assert payloads[-1]["status"] == "quarantine_resolved_safe_disabled"
        assert payloads[-1]["live_executed"] is True
        assert payloads[-1]["evidence"] == resolved


def _assert_resolve_cas_and_idempotency(deploy: Any) -> None:
    sealed = (
        "resolution=sealed\n"
        f"release_sha={FAILED_SHA}\n"
        f"snapshot_sha256={SNAPSHOT_SHA256}\n"
        f"replacement_sha={REPLACEMENT_SHA}\n"
        "authority=disabled\n"
    )
    resolved = _expected_evidence(
        legacy_layout="archived_absent_pointer",
        disposition="resolved_safe_disabled",
        replacement_sha=REPLACEMENT_SHA,
    )
    commands: list[str] = []

    def ssh(command: str) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return subprocess.CompletedProcess(["ssh"], 0, sealed, SENSITIVE_SENTINEL)

    with _patched(
        deploy,
        _ssh=ssh,
        _remote_quarantine_status=lambda _sha: resolved,
    ):
        first = deploy._resolve_remote_quarantine(
            FAILED_SHA, SNAPSHOT_SHA256, REPLACEMENT_SHA
        )
        second = deploy._resolve_remote_quarantine(
            FAILED_SHA, SNAPSHOT_SHA256, REPLACEMENT_SHA
        )
    assert first == resolved and second == resolved
    assert len(commands) == 2 and commands[0] == commands[1]
    assert "if [ -e" in commands[0]
    assert "verify_resolved_quarantine" in commands[0]
    assert f"snapshot_sha256={SNAPSHOT_SHA256}" in commands[0]
    assert f"replacement_sha={REPLACEMENT_SHA}" in commands[0]

    for invalid in (
        ("bad", SNAPSHOT_SHA256, REPLACEMENT_SHA),
        (FAILED_SHA, "f" * 63, REPLACEMENT_SHA),
        (FAILED_SHA, SNAPSHOT_SHA256, "bad"),
        (FAILED_SHA, SNAPSHOT_SHA256, FAILED_SHA),
    ):
        with _patched(
            deploy,
            _ssh=lambda _command: (_ for _ in ()).throw(
                AssertionError("invalid CAS identity reached SSH")
            ),
        ):
            _expect_runtime(
                "quarantine_resolution_identity_invalid",
                lambda values=invalid: deploy._resolve_remote_quarantine(*values),
            )

    with _patched(
        deploy,
        _ssh=lambda _command: subprocess.CompletedProcess(
            ["ssh"], 255, "", SENSITIVE_SENTINEL
        ),
    ):
        _expect_runtime(
            "quarantine_resolution_failed_safe_state_preserved",
            lambda: deploy._resolve_remote_quarantine(
                FAILED_SHA, SNAPSHOT_SHA256, REPLACEMENT_SHA
            ),
        )

    mismatched_receipt = sealed.replace(REPLACEMENT_SHA, PRIOR_SHA)
    with _patched(
        deploy,
        _ssh=lambda _command: subprocess.CompletedProcess(
            ["ssh"], 0, mismatched_receipt, SENSITIVE_SENTINEL
        ),
    ):
        _expect_runtime(
            "quarantine_resolution_receipt_invalid",
            lambda: deploy._resolve_remote_quarantine(
                FAILED_SHA, SNAPSHOT_SHA256, REPLACEMENT_SHA
            ),
        )

    bad_readback = resolved | {"replacement_sha": PRIOR_SHA}
    with _patched(
        deploy,
        _ssh=lambda _command: subprocess.CompletedProcess(["ssh"], 0, sealed, ""),
        _remote_quarantine_status=lambda _sha: bad_readback,
    ):
        _expect_runtime(
            "quarantine_resolution_readback_failed",
            lambda: deploy._resolve_remote_quarantine(
                FAILED_SHA, SNAPSHOT_SHA256, REPLACEMENT_SHA
            ),
        )


def _assert_generated_script_safety_and_ordering(deploy: Any) -> None:
    recovery = deploy._remote_failed_rollout_recovery_script(FAILED_SHA, ATTEMPT_ID)
    quarantine_start = recovery.index("quarantine_projection()")
    quarantine_end = recovery.index("if [ \"$prior_kind\" = v2 ] && restore_snapshot;")
    quarantine = recovery[quarantine_start:quarantine_end]
    receipt_write = quarantine.index("receipt_next=")
    for proof in (
        "systemctl stop 'dev-control-plane.service'",
        "systemctl disable 'dev-control-plane.service'",
        "systemctl stop certbot.timer",
        "require_unit_inactive 'dev-control-plane.service'",
        "require_unit_disabled 'dev-control-plane.service'",
        "require_unit_main_pid_zero 'dev-control-plane.service'",
        "require_unit_inactive certbot.timer",
        "require_projection_port_free",
        "test ! -e '/etc/nginx/sites-enabled/dev-control-plane'",
        "test ! -e '/opt/dev-control-plane-runtime/app'",
    ):
        assert quarantine.index(proof) < receipt_write, proof
    assert receipt_write < quarantine.index("mv -Tf \"$receipt_next\"")
    assert quarantine.index("mv -Tf \"$receipt_next\"") < quarantine.index(
        f"unlink '/opt/dev-control-plane-runtime/archive/projection-v2-{FAILED_SHA}.ACTIVATING'"
    )
    assert "systemctl start" not in quarantine

    # Legacy state is preserved as immutable evidence and is never restarted as
    # a fallback.  Snapshot restore is reachable only for a prior verified v2.
    assert 'if [ "$prior_kind" = v2 ] && restore_snapshot;' in recovery
    assert 'if [ "$prior_kind" = legacy ] && restore_snapshot;' not in recovery
    assert recovery.count("restore_snapshot;") == 1
    restore = recovery[
        recovery.index("restore_snapshot()") : recovery.index("quarantine_projection()")
    ]
    for exact_readback in (
        'restored_service_active="$(capture_unit_active_flag',
        'restored_service_enabled="$(capture_unit_enabled_flag',
        'restored_certbot_active="$(capture_unit_active_flag certbot.timer)',
        'restored_certbot_enabled="$(capture_unit_enabled_flag certbot.timer)',
        'test "$restored_service_active" = "$service_active"',
        'test "$restored_service_enabled" = "$service_enabled"',
        "require_unit_main_pid_zero 'dev-control-plane.service'",
        "require_projection_port_free",
    ):
        assert exact_readback in restore, exact_readback

    status = deploy._remote_quarantine_status_script(FAILED_SHA)
    resolution = deploy._remote_quarantine_resolution_script(
        FAILED_SHA, SNAPSHOT_SHA256, REPLACEMENT_SHA
    )
    binding = deploy._remote_process_binding_function()
    assert "verify_projection_unit_semantics()" in binding
    assert "verify_candidate_projection_unit()" in binding
    assert "verify_prior_projection_unit()" in binding
    assert 'case "$deployed_lines" in' in binding
    assert "3)\n      test \"$(grep -Ec '^unit_sha256='" in binding
    assert "return 1" in binding
    assert "4)" in binding and "unit_sha256=$(sha256sum" in binding
    assert "verify_prior_projection_unit \"$prior_release_sha\"" in recovery
    assert "flock -w 30 -s 9" in status
    assert "flock -w 300 -x 9" in resolution
    for script in (recovery, status, resolution):
        assert "for required_tool in find findmnt sync awk" in script
    assert "systemctl start" not in status + resolution
    assert "legacy-app-v1" in status
    assert "mv '/opt/dev-control-plane-runtime/archive/legacy-app-v1'" not in resolution
    assert "rm -rf" not in status + resolution
    assert "failed_release_layout=absent" in status
    assert "failed_release_layout=immutable" in status
    assert "failed_release_layout=absent" in resolution
    assert "failed_release_layout=immutable" in resolution
    assert "failed_release_layout=$failed_release_layout" in resolution

    disposition_write = resolution.index("disposition_next=")
    archive_guard = resolution.index(
        "if [ \"$prior_kind\" = legacy ]; then"
    )
    archive_absence_cas = resolution.index(
        "test ! -e '/opt/dev-control-plane-runtime/archive/legacy-app-v1'",
        archive_guard,
    )
    archive_move = resolution.index(
        "mv -Tn '/opt/dev-control-plane-runtime/app' '/opt/dev-control-plane-runtime/archive/legacy-app-v1'"
    )
    archive_chown = resolution.index(
        "chown -R --no-dereference root:root '/opt/dev-control-plane-runtime/archive/legacy-app-v1'"
    )
    archive_chmod = resolution.index(
        "chmod -R a-w '/opt/dev-control-plane-runtime/archive/legacy-app-v1'"
    )
    archive_fsync = resolution.index("DCP_FSYNC_RESOLVED_LEGACY_ARCHIVE")
    archive_immutable_proof = resolution.index(
        "writable_entries=\"$(find '/opt/dev-control-plane-runtime/archive/legacy-app-v1' -xdev -perm /222"
    )
    app_absent_proof = resolution.index(
        "test ! -e '/opt/dev-control-plane-runtime/app' && test ! -L '/opt/dev-control-plane-runtime/app'",
        archive_immutable_proof,
    )
    assert (
        archive_guard
        < archive_absence_cas
        < archive_move
        < archive_chown
        < archive_chmod
        < archive_fsync
        < archive_immutable_proof
        < app_absent_proof
        < disposition_write
    )
    for proof in (
        "grep -Fxq 'snapshot_sha256=",
        "require_unit_inactive 'dev-control-plane.service'",
        "require_unit_disabled 'dev-control-plane.service'",
        "require_unit_main_pid_zero 'dev-control-plane.service'",
        "require_unit_inactive certbot.timer",
        "test ! -e '/etc/nginx/sites-enabled/dev-control-plane'",
        "test ! -e '/opt/dev-control-plane-runtime/app'",
        "require_projection_port_free",
    ):
        assert resolution.index(proof) < disposition_write, proof
    assert disposition_write < resolution.index("DCP_FSYNC_DISPOSITION")
    assert resolution.index("DCP_FSYNC_DISPOSITION") < resolution.index(
        "mv -Tf \"$disposition_next\""
    )
    assert resolution.index("mv -Tf \"$disposition_next\"") < resolution.index(
        "DCP_FSYNC_DISPOSITION_DIR"
    )
    assert resolution.index("DCP_FSYNC_DISPOSITION_DIR") < resolution.rindex(
        f"verify_resolved_quarantine '/opt/dev-control-plane-runtime/archive/projection-v2-{FAILED_SHA}.QUARANTINED'"
    )
    assert "if [ -e '/opt/dev-control-plane-runtime/archive/projection-v2-" in resolution
    assert f"replacement_sha={REPLACEMENT_SHA}" in resolution
    assert "schema=dev-control-plane/hosted-rollout-supersession/v2" in resolution
    assert "legacy_layout=archived_absent_pointer" in resolution
    for hardened_guard in (
        "unsafe_entries=",
        "linked_entries=",
        "mount_targets=\"$(findmnt -rn -o TARGET)\"",
        "require_same_filesystem '/opt/dev-control-plane-runtime/app'",
        "sync -f '/opt/dev-control-plane-runtime/archive/legacy-app-v1'",
    ):
        assert hardened_guard in resolution, hardened_guard

    supersession = deploy._remote_quarantine_resolution_script(
        FAILED_SHA,
        SNAPSHOT_SHA256,
        REPLACEMENT_SHA,
        expected_prior_replacement=PRIOR_SHA,
        expected_prior_anchor_sha256=REPLACEMENT_ANCHOR_SHA256,
    )
    assert f"test \"$current_replacement\" = '{PRIOR_SHA}'" in supersession
    assert (
        f"test \"$(sha256sum \"$predecessor_receipt\" | awk '{{print $1}}')\" = "
        f"'{REPLACEMENT_ANCHOR_SHA256}'"
    ) in supersession
    assert f"successor_sha={REPLACEMENT_SHA}" in supersession
    assert "reason=origin_main_advanced_before_activation" in supersession

    quarantine_path = (
        f"/opt/dev-control-plane-runtime/archive/projection-v2-{FAILED_SHA}.QUARANTINED"
    )
    snapshot_path = (
        f"/opt/dev-control-plane-runtime/archive/projection-v2-{FAILED_SHA}.ROLLBACK/"
        "pre-mutation.tar"
    )
    assert quarantine_path in resolution and snapshot_path in resolution
    for preserved in (quarantine_path, snapshot_path):
        assert f"unlink '{preserved}'" not in resolution
        assert f'rm -f "{preserved}"' not in resolution
    assert "shutil.rmtree" not in resolution

    for values in (
        ("bad", SNAPSHOT_SHA256, REPLACEMENT_SHA),
        (FAILED_SHA, "bad", REPLACEMENT_SHA),
        (FAILED_SHA, SNAPSHOT_SHA256, FAILED_SHA),
    ):
        _expect_runtime(
            "quarantine_resolution_identity_invalid",
            lambda args=values: deploy._remote_quarantine_resolution_script(*args),
        )

    combined = "\n".join((recovery, status, resolution))
    syntax = subprocess.run(
        ["bash", "-n"],
        input=combined,
        text=True,
        capture_output=True,
        check=False,
    )
    assert syntax.returncode == 0, syntax.stderr


def _status_stdout(
    *,
    release_sha: str = FAILED_SHA,
    snapshot_sha256: str = SNAPSHOT_SHA256,
    attempt_id: str = ATTEMPT_ID,
    failed_release_layout: str = "absent",
    prior_kind: str = "legacy",
    prior_release_sha: str = "none",
    legacy_layout: str = "legacy_directory_pending_archive",
    current_app_present: str | None = None,
    legacy_archive_present: str | None = None,
    last_stage: str = "certificate_refresh_failed",
    disposition: str = "unresolved",
    replacement_sha: str = "none",
    replacement_anchor_sha256: str | None = None,
    replacement_supersession_eligible: str | None = None,
    extra_line: str | None = None,
) -> str:
    if current_app_present is None:
        current_app_present = (
            "yes" if legacy_layout == "legacy_directory_pending_archive" else "no"
        )
    if legacy_archive_present is None:
        legacy_archive_present = (
            "yes" if legacy_layout.startswith("archived_") else "no"
        )
    if replacement_anchor_sha256 is None:
        replacement_anchor_sha256 = (
            "none" if disposition == "unresolved" else REPLACEMENT_ANCHOR_SHA256
        )
    if replacement_supersession_eligible is None:
        replacement_supersession_eligible = (
            "no" if disposition == "unresolved" else "yes"
        )
    lines = [
        "quarantine=verified_safe_disabled",
        f"release_sha={release_sha}",
        f"snapshot_sha256={snapshot_sha256}",
        f"attempt_id={attempt_id}",
        f"quarantine_receipt_sha256={QUARANTINE_RECEIPT_SHA256}",
        f"failed_release_layout={failed_release_layout}",
        f"prior_kind={prior_kind}",
        f"prior_release_sha={prior_release_sha}",
        "prior_service_active=yes",
        "prior_service_enabled=yes",
        "current_service_active=no",
        "current_service_enabled=no",
        "current_site_enabled=no",
        f"current_app_present={current_app_present}",
        f"legacy_layout={legacy_layout}",
        "legacy_transition_safe=yes",
        "current_port_owner=free",
        "certbot_timer_active=no",
        f"legacy_archive_present={legacy_archive_present}",
        "legacy_state_present=yes",
        "projection_state_present=yes",
        "certificate_currently_valid=no",
        "certificate_covers_primary=yes",
        "certificate_covers_www=yes",
        f"last_stage={last_stage}",
        f"disposition={disposition}",
        f"replacement_sha={replacement_sha}",
        f"replacement_anchor_sha256={replacement_anchor_sha256}",
        f"replacement_supersession_eligible={replacement_supersession_eligible}",
    ]
    if extra_line is not None:
        lines.append(extra_line)
    return "\n".join(lines) + "\n"


def _expected_evidence(
    *,
    failed_release_layout: str = "absent",
    legacy_layout: str = "legacy_directory_pending_archive",
    disposition: str = "unresolved",
    replacement_sha: str | None = None,
    replacement_anchor_sha256: str | None = None,
    replacement_supersession_eligible: bool | None = None,
    attempt_id: str | None = ATTEMPT_ID,
) -> dict[str, Any]:
    pending = legacy_layout == "legacy_directory_pending_archive"
    if replacement_anchor_sha256 is None and disposition == "resolved_safe_disabled":
        replacement_anchor_sha256 = REPLACEMENT_ANCHOR_SHA256
    if replacement_supersession_eligible is None:
        replacement_supersession_eligible = disposition == "resolved_safe_disabled"
    return {
        "release_sha": FAILED_SHA,
        "snapshot_sha256": SNAPSHOT_SHA256,
        "attempt_id": attempt_id,
        "quarantine_receipt_sha256": QUARANTINE_RECEIPT_SHA256,
        "failed_release_layout": failed_release_layout,
        "prior_kind": "legacy",
        "prior_release_sha": None,
        "prior_service_active": True,
        "prior_service_enabled": True,
        "safe_disabled": True,
        "service_active": False,
        "service_enabled": False,
        "site_enabled": False,
        "app_present": pending,
        "port_8770_free": True,
        "certbot_timer_active": False,
        "legacy_archive_present": not pending,
        "legacy_state_present": True,
        "projection_state_present": True,
        "certificate_currently_valid": False,
        "certificate_covers_primary": True,
        "certificate_covers_www": True,
        "last_stage": "certificate_refresh_failed",
        "legacy_layout": legacy_layout,
        "legacy_transition_safe": True,
        "legacy_normalization_required": legacy_layout
        in {"legacy_directory_pending_archive", "archived_pending_normalization"},
        "disposition": disposition,
        "replacement_sha": replacement_sha,
        "replacement_anchor_sha256": replacement_anchor_sha256,
        "replacement_supersession_eligible": replacement_supersession_eligible,
        "raw_remote_payload_exposed": False,
    }


def _source_result(*, head_sha: str, status: str = "passed") -> Any:
    return SimpleNamespace(
        status=status,
        enforced=True,
        fetched_origin_main=True,
        exact_repository=True,
        clean=True,
        head_matches_origin_main=True,
        head_sha=head_sha,
        origin_main_sha=head_sha,
        branch="main",
        blockers=[],
        warnings=[],
    )


@contextmanager
def _patched(module: Any, **replacements: Any) -> Iterator[None]:
    originals = {name: getattr(module, name) for name in replacements}
    try:
        for name, value in replacements.items():
            setattr(module, name, value)
        yield
    finally:
        for name, value in originals.items():
            setattr(module, name, value)


def _expect_runtime(reason: str, call: Callable[[], Any]) -> None:
    try:
        call()
    except RuntimeError as exc:
        assert str(exc) == reason, (str(exc), reason)
    else:
        raise AssertionError(f"expected RuntimeError: {reason}")


def _load_runner() -> Any:
    module_name = "dev_control_plane_hosted_deploy_quarantine_smoke"
    spec = importlib.util.spec_from_file_location(module_name, RUNNER)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not import hosted deploy runner")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


if __name__ == "__main__":
    main()
