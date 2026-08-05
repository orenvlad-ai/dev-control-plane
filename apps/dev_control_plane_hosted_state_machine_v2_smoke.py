"""Executable hosted projection-v2 state-machine smoke.

The generated quarantine/supersession verifier runs only against an isolated
temporary filesystem. This smoke never uses SSH, DNS, root, or the network.
"""

from __future__ import annotations

from contextlib import contextmanager
import grp
import hashlib
import importlib.util
import os
from pathlib import Path
import pwd
import subprocess
import sys
import tempfile
from typing import Any, Iterator


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "apps" / "dev_control_plane_hosted_deploy.py"
FAILED_SHA = "a" * 40
REPLACEMENT_SHA = "b" * 40
SUCCESSOR_SHA = "c" * 40
DANGLING_SHA = "d" * 40
LATER_SHA = "f" * 40
ATTEMPT_ID = "1" * 32
SNAPSHOT_SHA256 = "e" * 64


def main() -> None:
    deploy = _load_runner()
    _assert_supersession_trace(deploy)
    _assert_quarantine_chain_trace(deploy)
    _assert_dangling_markers_fail_closed(deploy)
    _assert_process_binding_conditional_fail_closed(deploy)
    _assert_generated_probe_helpers_fail_closed(deploy)
    _assert_orphan_and_normalization_contracts(deploy)
    print("dev-control-plane-hosted-state-machine-v2-smoke passed")


def _assert_supersession_trace(deploy: Any) -> None:
    with tempfile.TemporaryDirectory(prefix="dcp-hosted-smoke-") as raw:
        root = Path(raw)
        with _temporary_remote_paths(deploy, root):
            deploy.ARCHIVE_DIR.mkdir(parents=True, mode=0o700)
            deploy.RELEASES_DIR.mkdir(parents=True, mode=0o755)
            stat_shim = _install_stat_shim(root)
            quarantine, disposition = _make_resolved_quarantine(
                deploy, FAILED_SHA, REPLACEMENT_SHA
            )
            guard = _generated_guard_for_current_user(deploy)

            output = _run_guard(
                guard,
                stat_shim,
                f"""
read -r tip anchor visited <<DCP_TIP
$(quarantine_declared_tip '{quarantine}')
DCP_TIP
test "$tip" = '{REPLACEMENT_SHA}'
test "$anchor" = '{disposition}'
case "$visited" in *:'{REPLACEMENT_SHA}':*) ;; *) exit 71 ;; esac
verify_no_unresolved_rollout_markers none '{REPLACEMENT_SHA}'
printf 'initial_tip=ok\\n'
""",
            )
            assert output.strip() == "initial_tip=ok"

            successor = _make_supersession(
                deploy,
                root_failed_sha=FAILED_SHA,
                prior_tip_sha=REPLACEMENT_SHA,
                successor_sha=SUCCESSOR_SHA,
                predecessor=disposition,
            )
            output = _run_guard(
                guard,
                stat_shim,
                f"""
read -r tip anchor visited <<DCP_TIP
$(quarantine_declared_tip '{quarantine}')
DCP_TIP
test "$tip" = '{SUCCESSOR_SHA}'
test "$anchor" = '{successor}'
case "$visited" in *:'{REPLACEMENT_SHA}':*) ;; *) exit 72 ;; esac
case "$visited" in *:'{SUCCESSOR_SHA}':*) ;; *) exit 72 ;; esac
if verify_no_unresolved_rollout_markers none '{REPLACEMENT_SHA}'; then exit 73; fi
verify_no_unresolved_rollout_markers none '{SUCCESSOR_SHA}'
printf 'superseded_tip=ok\\n'
""",
            )
            assert output.strip() == "superseded_tip=ok"

            output = _run_guard(
                guard,
                stat_shim,
                f"""
read -r tip anchor visited <<DCP_TIP
$(quarantine_declared_tip '{quarantine}')
DCP_TIP
test "$tip" = '{SUCCESSOR_SHA}'
case "$visited" in *:'{REPLACEMENT_SHA}':*) printf 'cycle_guard=ok\\n' ;; *) exit 74 ;; esac
""",
            )
            assert output.strip() == "cycle_guard=ok"

            cycle = _make_supersession(
                deploy,
                root_failed_sha=FAILED_SHA,
                prior_tip_sha=SUCCESSOR_SHA,
                successor_sha=REPLACEMENT_SHA,
                predecessor=successor,
            )
            output = _run_guard(
                guard,
                stat_shim,
                f"""
if quarantine_declared_tip '{quarantine}' >/dev/null; then exit 75; fi
printf 'cycle_chain_rejected=ok\\n'
""",
            )
            assert output.strip() == "cycle_chain_rejected=ok"
            cycle.unlink()

            deployed = _make_deployed(deploy, SUCCESSOR_SHA)
            remediation = _make_remediation(
                deploy,
                failed_sha=FAILED_SHA,
                initial_replacement_sha=REPLACEMENT_SHA,
                deployed_sha=SUCCESSOR_SHA,
                terminal_anchor=successor,
            )
            output = _run_guard(
                guard,
                stat_shim,
                """
verify_no_unresolved_rollout_markers none none
printf 'four_line_remediation=ok\\n'
""",
            )
            assert output.strip() == "four_line_remediation=ok"

            successor.unlink()
            output = _run_guard(
                guard,
                stat_shim,
                """
if verify_no_unresolved_rollout_markers none none; then exit 75; fi
printf 'missing_terminal_anchor_rejected=ok\\n'
""",
            )
            assert output.strip() == "missing_terminal_anchor_rejected=ok"
            successor = _make_supersession(
                deploy,
                root_failed_sha=FAILED_SHA,
                prior_tip_sha=REPLACEMENT_SHA,
                successor_sha=SUCCESSOR_SHA,
                predecessor=disposition,
            )
            successor.chmod(0o644)
            output = _run_guard(
                guard,
                stat_shim,
                """
if verify_no_unresolved_rollout_markers none none; then exit 75; fi
printf 'corrupt_terminal_anchor_rejected=ok\\n'
""",
            )
            assert output.strip() == "corrupt_terminal_anchor_rejected=ok"
            successor.chmod(0o444)

            _make_deployed(deploy, LATER_SHA)
            output = _run_generated_shell(
                guard + "\n" + deploy._remote_quarantine_remediation_function(LATER_SHA),
                stat_shim,
                """
seal_quarantine_remediations
printf 'later_deploy_preserves_remediation=ok\\n'
""",
            )
            assert output.strip() == "later_deploy_preserves_remediation=ok"

            # Production calls these functions in shell conditionals, where
            # bash suppresses errexit. Every failed invariant must therefore
            # be propagated explicitly by the generated verifier.
            quarantine.chmod(0o644)
            output = _run_guard(
                guard,
                stat_shim,
                """
if verify_no_unresolved_rollout_markers none none; then exit 76; fi
printf 'tampered_mode_rejected=ok\\n'
""",
            )
            assert output.strip() == "tampered_mode_rejected=ok"
            quarantine.chmod(0o444)

            _write_lines(
                deployed,
                (
                    "schema=dev-control-plane/hosted-rollout-receipt/v2",
                    f"release_sha={SUCCESSOR_SHA}",
                    "outcome=deployed",
                    "unit_sha256=invalid",
                ),
                0o444,
            )
            _make_remediation(
                deploy,
                failed_sha=FAILED_SHA,
                initial_replacement_sha=REPLACEMENT_SHA,
                deployed_sha=SUCCESSOR_SHA,
                terminal_anchor=successor,
                destination=remediation,
            )
            output = _run_guard(
                guard,
                stat_shim,
                """
if verify_no_unresolved_rollout_markers none none; then exit 77; fi
printf 'invalid_unit_digest_rejected=ok\\n'
""",
            )
            assert output.strip() == "invalid_unit_digest_rejected=ok"


def _assert_quarantine_chain_trace(deploy: Any) -> None:
    with tempfile.TemporaryDirectory(prefix="dcp-hosted-chain-") as raw:
        root = Path(raw)
        with _temporary_remote_paths(deploy, root):
            deploy.ARCHIVE_DIR.mkdir(parents=True, mode=0o700)
            deploy.RELEASES_DIR.mkdir(parents=True, mode=0o755)
            stat_shim = _install_stat_shim(root)
            quarantine, _ = _make_resolved_quarantine(
                deploy, FAILED_SHA, REPLACEMENT_SHA
            )
            _make_resolved_quarantine(deploy, REPLACEMENT_SHA, SUCCESSOR_SHA)
            output = _run_guard(
                _generated_guard_for_current_user(deploy),
                stat_shim,
                f"""
if verify_no_unresolved_rollout_markers none '{REPLACEMENT_SHA}'; then exit 81; fi
verify_no_unresolved_rollout_markers none '{SUCCESSOR_SHA}'
verify_quarantine_permits_release '{quarantine}' '{SUCCESSOR_SHA}'
printf 'transitive_quarantine_chain=ok\\n'
""",
            )
            assert output.strip() == "transitive_quarantine_chain=ok"


def _assert_dangling_markers_fail_closed(deploy: Any) -> None:
    with tempfile.TemporaryDirectory(prefix="dcp-hosted-dangling-") as raw:
        root = Path(raw)
        with _temporary_remote_paths(deploy, root):
            deploy.ARCHIVE_DIR.mkdir(parents=True, mode=0o700)
            deploy.RELEASES_DIR.mkdir(parents=True, mode=0o755)
            stat_shim = _install_stat_shim(root)
            guard = _generated_guard_for_current_user(deploy)

            activating = (
                deploy.ARCHIVE_DIR / f"projection-v2-{DANGLING_SHA}.ACTIVATING"
            )
            activating.symlink_to(root / "missing-activation-target")
            output = _run_guard(
                guard,
                stat_shim,
                """
if verify_no_unresolved_rollout_markers none none; then exit 82; fi
printf 'dangling_activation_rejected=ok\\n'
""",
            )
            assert output.strip() == "dangling_activation_rejected=ok"
            activating.unlink()

            quarantine = (
                deploy.ARCHIVE_DIR / f"projection-v2-{DANGLING_SHA}.QUARANTINED"
            )
            quarantine.symlink_to(root / "missing-quarantine-target")
            output = _run_guard(
                guard,
                stat_shim,
                """
if verify_no_unresolved_rollout_markers none none; then exit 83; fi
printf 'dangling_quarantine_rejected=ok\\n'
""",
            )
            assert output.strip() == "dangling_quarantine_rejected=ok"


def _assert_process_binding_conditional_fail_closed(deploy: Any) -> None:
    with tempfile.TemporaryDirectory(prefix="dcp-hosted-process-") as raw:
        root = Path(raw).resolve()
        with _temporary_process_paths(deploy, root):
            deploy.ARCHIVE_DIR.mkdir(parents=True, mode=0o700)
            deploy.RELEASES_DIR.mkdir(parents=True, mode=0o755)
            release = deploy.RELEASES_DIR / REPLACEMENT_SHA
            release.mkdir(mode=0o755)
            deploy.APP_DIR.parent.mkdir(parents=True, exist_ok=True)
            deploy.APP_DIR.symlink_to(release)
            deploy.SYSTEMD_UNIT_FILE.parent.mkdir(parents=True, exist_ok=True)
            _write_bytes(
                deploy.SYSTEMD_UNIT_FILE,
                deploy._systemd_unit().encode(),
                0o644,
            )
            deployed = deploy.ARCHIVE_DIR / (
                f"projection-v2-{REPLACEMENT_SHA}.DEPLOYED"
            )
            _write_lines(
                deployed,
                (
                    "schema=dev-control-plane/hosted-rollout-receipt/v2",
                    f"release_sha={REPLACEMENT_SHA}",
                    "outcome=deployed",
                    f"unit_sha256={_sha256(deploy.SYSTEMD_UNIT_FILE)}",
                ),
                0o444,
            )
            proc_root = root / "proc"
            process = proc_root / "42"
            process.mkdir(parents=True)
            (process / "cwd").symlink_to(release)
            _write_bytes(
                process / "cmdline",
                (
                    f"/usr/bin/python3 {deploy.APP_DIR}/apps/"
                    "dev_control_plane_projection_v2.py"
                ).encode()
                + b"\0",
                0o600,
            )
            _write_bytes(
                process / "cgroup",
                f"0::/{deploy.SERVICE_NAME}\n".encode(),
                0o600,
            )
            key_in_process = Path(
                f"{process}/root{deploy.PROJECTION_KEY_DEST}"
            )
            _write_bytes(key_in_process, b"test-key\n", 0o400)
            tool_shims = _install_process_shims(deploy, root)
            binding = _generated_binding_for_current_user(deploy, proc_root)

            output = _run_generated_shell(
                binding,
                tool_shims,
                f"""
verify_candidate_projection_unit
verify_prior_projection_unit '{REPLACEMENT_SHA}'
verify_projection_process '{release}' >/dev/null
printf 'process_binding=ok\\n'
""",
            )
            assert output.strip() == "process_binding=ok"

            deployed.chmod(0o644)
            output = _run_generated_shell(
                binding,
                tool_shims,
                f"""
if verify_prior_projection_unit '{REPLACEMENT_SHA}'; then exit 91; fi
printf 'conditional_receipt_mode_rejected=ok\\n'
""",
            )
            assert output.strip() == "conditional_receipt_mode_rejected=ok"
            deployed.chmod(0o444)

            deploy.SYSTEMD_UNIT_FILE.chmod(0o600)
            output = _run_generated_shell(
                binding,
                tool_shims,
                f"""
if verify_projection_process '{release}' >/dev/null; then exit 92; fi
printf 'conditional_unit_mode_rejected=ok\\n'
""",
            )
            assert output.strip() == "conditional_unit_mode_rejected=ok"


def _assert_generated_probe_helpers_fail_closed(deploy: Any) -> None:
    generated = "\n".join(
        (
            deploy._remote_authority_state_guard_function(),
            deploy._remote_legacy_archive_guard_function(),
        )
    )
    with tempfile.TemporaryDirectory(prefix="dcp-hosted-probes-") as raw:
        root = Path(raw).resolve()
        source = root / "legacy-app"
        destination = root / "archive"
        source.mkdir()
        destination.mkdir()
        tool_shims = _install_probe_guard_shims(root)
        base_environment = {
            "DCP_SMOKE_SOURCE": str(source),
            "DCP_SMOKE_DESTINATION": str(destination),
            "DCP_SMOKE_SYSTEMCTL_FAIL": "no",
            "DCP_SMOKE_SS_FAIL": "no",
            "DCP_SMOKE_AWK_FAIL": "no",
            "DCP_SMOKE_CROSS_DEVICE": "no",
        }

        output = _run_generated_shell(
            generated,
            tool_shims,
            """
if require_unit_inactive smoke.service; then exit 101; fi
if require_unit_disabled smoke.service; then exit 102; fi
printf 'systemctl_show_failure_rejected=ok\n'
""",
            environment_overrides={
                **base_environment,
                "DCP_SMOKE_SYSTEMCTL_FAIL": "yes",
            },
        )
        assert output.strip() == "systemctl_show_failure_rejected=ok"

        output = _run_generated_shell(
            generated,
            tool_shims,
            """
if require_projection_port_free; then exit 103; fi
printf 'ss_failure_rejected=ok\n'
""",
            environment_overrides={
                **base_environment,
                "DCP_SMOKE_SS_FAIL": "yes",
            },
        )
        assert output.strip() == "ss_failure_rejected=ok"

        output = _run_generated_shell(
            generated,
            tool_shims,
            f"""
if require_no_mount_at_or_below '{source}'; then exit 104; fi
printf 'awk_failure_rejected=ok\n'
""",
            environment_overrides={
                **base_environment,
                "DCP_SMOKE_AWK_FAIL": "yes",
            },
        )
        assert output.strip() == "awk_failure_rejected=ok"

        output = _run_generated_shell(
            generated,
            tool_shims,
            f"""
if require_same_filesystem '{source}' '{destination}'; then exit 105; fi
printf 'cross_device_rejected=ok\n'
""",
            environment_overrides={
                **base_environment,
                "DCP_SMOKE_CROSS_DEVICE": "yes",
            },
        )
        assert output.strip() == "cross_device_rejected=ok"

        output = _run_generated_shell(
            generated,
            tool_shims,
            f"""
require_unit_inactive smoke.service
require_unit_disabled smoke.service
require_unit_main_pid_zero smoke.service
require_projection_port_free
require_no_mount_at_or_below '{source}'
require_same_filesystem '{source}' '{destination}'
printf 'valid_authority_and_archive_proofs=ok\n'
""",
            environment_overrides=base_environment,
        )
        assert output.strip() == "valid_authority_and_archive_proofs=ok"


def _assert_orphan_and_normalization_contracts(deploy: Any) -> None:
    stage = "certificate_refresh_started"
    recovery = deploy._remote_failed_rollout_recovery_script(
        FAILED_SHA,
        ATTEMPT_ID,
        expected_snapshot_sha256=SNAPSHOT_SHA256,
        expected_stage=stage,
        minimum_stage_age_seconds=deploy.MIN_ORPHAN_TRANSACTION_AGE_SECONDS,
    )
    _assert_in_order(
        recovery,
        (
            "flock -w 300 -x 9",
            f"grep -Fxq 'attempt_id={ATTEMPT_ID}'",
            f"grep -Fxq 'snapshot_sha256={SNAPSHOT_SHA256}'",
            f"grep -Fxq 'stage={stage}'",
            "activity_mtime=\"$(stat -c '%Y' \"$activity_path\")\"",
            f'test "$((now - activity_mtime))" -ge '
            f"'{deploy.MIN_ORPHAN_TRANSACTION_AGE_SECONDS}'",
        ),
    )
    status = deploy._remote_transaction_status_script(FAILED_SHA)
    for exact_guard in (
        "flock -w 30 -s 9",
        "stage_age_seconds=$((now - activity_mtime))",
        "prior_kind=",
        "prior_release_sha=",
    ):
        assert exact_guard in status, exact_guard

    start = recovery.index("quarantine_projection()")
    end = recovery.index('if [ "$prior_kind" = v2 ] && restore_snapshot;')
    quarantine = recovery[start:end]
    assert 'if [ "$prior_kind" = legacy ]; then' in quarantine
    assert "else\n      test ! -e '" in quarantine
    _assert_in_order(
        quarantine,
        (
            "unsafe_entries=",
            "linked_entries=",
            "require_no_mount_at_or_below '",
            "require_same_filesystem '",
            "mv -Tn '",
            "test -d '",
            "chown -R --no-dereference root:root",
            "chmod -R a-w",
            "owner_mismatch=",
            "sync -f",
            "DCP_FSYNC_LEGACY_QUARANTINE_ARCHIVE",
            "writable_entries=",
        ),
    )


def _make_resolved_quarantine(
    deploy: Any, failed_sha: str, replacement_sha: str
) -> tuple[Path, Path]:
    transaction = deploy.ARCHIVE_DIR / f"projection-v2-{failed_sha}.ROLLBACK"
    transaction.mkdir(parents=True, mode=0o700)
    snapshot = transaction / "pre-mutation.tar"
    _write_bytes(snapshot, f"snapshot:{failed_sha}\n".encode(), 0o600)
    snapshot_sha = _sha256(snapshot)
    _write_lines(
        transaction / "pre-mutation.state",
        (
            "schema=dev-control-plane/hosted-rollout-snapshot/v2",
            f"release_sha={failed_sha}",
            f"snapshot_sha256={snapshot_sha}",
        ),
        0o600,
    )
    quarantine = deploy.ARCHIVE_DIR / f"projection-v2-{failed_sha}.QUARANTINED"
    _write_lines(
        quarantine,
        (
            "schema=dev-control-plane/hosted-rollout-receipt/v2",
            f"release_sha={failed_sha}",
            "outcome=quarantined",
            "reason=no_previous_v2_or_restore_failed",
            "authority=disabled",
        ),
        0o444,
    )
    disposition = (
        deploy.ARCHIVE_DIR / f"projection-v2-{failed_sha}.QUARANTINE_RESOLVED"
    )
    _write_lines(
        disposition,
        (
            "schema=dev-control-plane/hosted-rollout-receipt/v2",
            f"release_sha={failed_sha}",
            "outcome=quarantine_resolved_safe_disabled",
            f"snapshot_sha256={snapshot_sha}",
            f"quarantine_receipt_sha256={_sha256(quarantine)}",
            f"replacement_sha={replacement_sha}",
            "failed_release_layout=absent",
            "legacy_layout=archived_absent_pointer",
            "authority=disabled_at_resolution",
            "next_action=full_validated_deploy_only",
        ),
        0o444,
    )
    return quarantine, disposition


def _make_supersession(
    deploy: Any,
    *,
    root_failed_sha: str,
    prior_tip_sha: str,
    successor_sha: str,
    predecessor: Path,
) -> Path:
    root_disposition = (
        deploy.ARCHIVE_DIR
        / f"projection-v2-{root_failed_sha}.QUARANTINE_RESOLVED"
    )
    destination = (
        deploy.ARCHIVE_DIR
        / f"projection-v2-{root_failed_sha}-{prior_tip_sha}.SUPERSEDED"
    )
    _write_lines(
        destination,
        (
            "schema=dev-control-plane/hosted-rollout-supersession/v2",
            f"root_failed_sha={root_failed_sha}",
            f"root_disposition_sha256={_sha256(root_disposition)}",
            f"prior_tip_sha={prior_tip_sha}",
            f"prior_anchor_sha256={_sha256(predecessor)}",
            f"successor_sha={successor_sha}",
            "source_ref=refs/remotes/origin/main",
            "reason=origin_main_advanced_before_activation",
            "authority=disabled",
            "next_action=full_validated_deploy_only",
        ),
        0o444,
    )
    return destination


def _make_deployed(deploy: Any, release_sha: str) -> Path:
    destination = deploy.ARCHIVE_DIR / f"projection-v2-{release_sha}.DEPLOYED"
    _write_lines(
        destination,
        (
            "schema=dev-control-plane/hosted-rollout-receipt/v2",
            f"release_sha={release_sha}",
            "outcome=deployed",
            f"unit_sha256={'f' * 64}",
        ),
        0o444,
    )
    return destination


def _make_remediation(
    deploy: Any,
    *,
    failed_sha: str,
    initial_replacement_sha: str,
    deployed_sha: str,
    terminal_anchor: Path,
    destination: Path | None = None,
) -> Path:
    quarantine = deploy.ARCHIVE_DIR / f"projection-v2-{failed_sha}.QUARANTINED"
    disposition = (
        deploy.ARCHIVE_DIR / f"projection-v2-{failed_sha}.QUARANTINE_RESOLVED"
    )
    deployed = deploy.ARCHIVE_DIR / f"projection-v2-{deployed_sha}.DEPLOYED"
    destination = destination or (
        deploy.ARCHIVE_DIR / f"projection-v2-{failed_sha}.REMEDIATED"
    )
    _write_lines(
        destination,
        (
            "schema=dev-control-plane/hosted-rollout-receipt/v2",
            f"release_sha={failed_sha}",
            "outcome=quarantine_remediated",
            f"replacement_sha={initial_replacement_sha}",
            f"deployed_release_sha={deployed_sha}",
            f"terminal_chain_anchor_sha256={_sha256(terminal_anchor)}",
            f"quarantine_receipt_sha256={_sha256(quarantine)}",
            f"disposition_receipt_sha256={_sha256(disposition)}",
            f"deployment_receipt_sha256={_sha256(deployed)}",
        ),
        0o444,
    )
    return destination


def _generated_guard_for_current_user(deploy: Any) -> str:
    return deploy._remote_resolved_quarantine_guard_function().replace(
        "= '0:0'", f"= '{os.getuid()}:{os.getgid()}'"
    )


def _run_guard(guard: str, stat_shim: Path, body: str) -> str:
    script = f"""set -euo pipefail
verify_projection_release() {{ return 97; }}
{guard}
{body}
"""
    return _run_generated_shell(script, stat_shim, "")


def _run_generated_shell(
    generated: str,
    tool_shims: Path,
    body: str,
    *,
    environment_overrides: dict[str, str] | None = None,
) -> str:
    script = f"""set -euo pipefail
{generated}
{body}
"""
    syntax = subprocess.run(
        ["bash", "-n"], input=script, text=True, capture_output=True, check=False
    )
    assert syntax.returncode == 0, syntax.stderr
    environment = dict(os.environ)
    environment["PATH"] = f"{tool_shims}:{environment.get('PATH', '')}"
    environment["LC_ALL"] = "C"
    if environment_overrides:
        environment.update(environment_overrides)
    completed = subprocess.run(
        ["bash"],
        input=script,
        text=True,
        capture_output=True,
        check=False,
        env=environment,
        timeout=20,
    )
    assert completed.returncode == 0, (
        completed.returncode,
        completed.stdout,
        completed.stderr,
    )
    return completed.stdout


def _install_stat_shim(root: Path) -> Path:
    directory = root / "bin"
    directory.mkdir(mode=0o700)
    shim = directory / "stat"
    shim.write_text(
        """#!/usr/bin/env python3
import os
from pathlib import Path
import stat
import sys

if len(sys.argv) != 4 or sys.argv[1] != "-c":
    raise SystemExit(64)
fmt = sys.argv[2]
metadata = os.lstat(Path(sys.argv[3]))
values = {
    "%a": f"{stat.S_IMODE(metadata.st_mode):o}",
    "%u:%g": f"{metadata.st_uid}:{metadata.st_gid}",
    "%h": str(metadata.st_nlink),
    "%Y": str(int(metadata.st_mtime)),
}
if fmt not in values:
    raise SystemExit(65)
print(values[fmt])
""",
        encoding="utf-8",
    )
    shim.chmod(0o700)
    wc_shim = directory / "wc"
    wc_shim.write_text(
        """#!/usr/bin/env python3
import sys

if sys.argv[1:] != ["-l"]:
    raise SystemExit(64)
print(sys.stdin.buffer.read().count(b"\\n"))
""",
        encoding="utf-8",
    )
    wc_shim.chmod(0o700)
    return directory


def _install_process_shims(deploy: Any, root: Path) -> Path:
    directory = _install_stat_shim(root)
    _write_executable(
        directory / "systemctl",
        f"""#!/bin/sh
case "$*" in
  "show -p FragmentPath --value {deploy.SERVICE_NAME}")
    printf '%s\\n' '{deploy.SYSTEMD_UNIT_FILE}' ;;
  "show -p DropInPaths --value {deploy.SERVICE_NAME}")
    printf '\\n' ;;
  "show -p MainPID --value {deploy.SERVICE_NAME}")
    printf '42\\n' ;;
  "is-active {deploy.SERVICE_NAME}")
    printf 'active\\n' ;;
  *) exit 64 ;;
esac
""",
    )
    _write_executable(
        directory / "ps",
        f"""#!/bin/sh
printf '%s\\n' '{deploy.PROJECTION_SERVICE_USER}'
""",
    )
    _write_executable(
        directory / "ss",
        """#!/bin/sh
printf 'State Recv-Q Send-Q Local Address:Port Peer Address:Port Process\\n'
printf 'LISTEN 0 10 127.0.0.1:8770 0.0.0.0:* users:((python3,pid=42,fd=3))\\n'
""",
    )
    return directory


def _install_probe_guard_shims(root: Path) -> Path:
    directory = root / "probe-bin"
    directory.mkdir(mode=0o700)
    _write_executable(
        directory / "systemctl",
        """#!/bin/sh
if [ "${DCP_SMOKE_SYSTEMCTL_FAIL:-no}" = yes ]; then exit 73; fi
case "$*" in
  "show -p ActiveState --value smoke.service") printf 'inactive\n' ;;
  "show -p UnitFileState --value smoke.service") printf 'disabled\n' ;;
  "show -p MainPID --value smoke.service") printf '0\n' ;;
  *) exit 64 ;;
esac
""",
    )
    _write_executable(
        directory / "ss",
        """#!/bin/sh
if [ "${DCP_SMOKE_SS_FAIL:-no}" = yes ]; then exit 74; fi
exit 0
""",
    )
    _write_executable(
        directory / "findmnt",
        """#!/bin/sh
test "$*" = '-rn -o TARGET' || exit 64
printf '/\n'
""",
    )
    _write_executable(
        directory / "awk",
        """#!/bin/sh
if [ "${DCP_SMOKE_AWK_FAIL:-no}" = yes ]; then exit 75; fi
exec /usr/bin/awk "$@"
""",
    )
    _write_executable(
        directory / "stat",
        """#!/usr/bin/env python3
import os
from pathlib import Path
import sys

if sys.argv[1:3] != ["-c", "%d"] or len(sys.argv) != 4:
    raise SystemExit(64)
candidate = Path(sys.argv[3]).resolve()
source = Path(os.environ["DCP_SMOKE_SOURCE"]).resolve()
destination = Path(os.environ["DCP_SMOKE_DESTINATION"]).resolve()
if candidate == source:
    print("101")
elif candidate == destination:
    print("202" if os.environ.get("DCP_SMOKE_CROSS_DEVICE") == "yes" else "101")
else:
    raise SystemExit(65)
""",
    )
    return directory


def _generated_binding_for_current_user(deploy: Any, proc_root: Path) -> str:
    binding = deploy._remote_process_binding_function()
    binding = binding.replace(
        "= '0:0'", f"= '{os.getuid()}:{os.getgid()}'"
    )
    return binding.replace("/proc/$main_pid", f"{proc_root}/$main_pid")


def _write_executable(path: Path, payload: str) -> None:
    path.write_text(payload, encoding="utf-8")
    path.chmod(0o700)


def _write_lines(path: Path, lines: tuple[str, ...], mode: int) -> None:
    _write_bytes(path, ("\n".join(lines) + "\n").encode(), mode)


def _write_bytes(path: Path, payload: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.chmod(0o600)
    path.write_bytes(payload)
    path.chmod(mode)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _assert_in_order(text: str, fragments: tuple[str, ...]) -> None:
    cursor = -1
    for fragment in fragments:
        position = text.find(fragment, cursor + 1)
        assert position > cursor, fragment
        cursor = position


@contextmanager
def _temporary_remote_paths(deploy: Any, root: Path) -> Iterator[None]:
    original_archive = deploy.ARCHIVE_DIR
    original_releases = deploy.RELEASES_DIR
    deploy.ARCHIVE_DIR = root / "archive"
    deploy.RELEASES_DIR = root / "releases"
    try:
        yield
    finally:
        deploy.ARCHIVE_DIR = original_archive
        deploy.RELEASES_DIR = original_releases


@contextmanager
def _temporary_process_paths(deploy: Any, root: Path) -> Iterator[None]:
    runtime = root / "runtime"
    replacements = {
        "RUNTIME_ROOT": runtime,
        "APP_DIR": runtime / "app",
        "RELEASES_DIR": runtime / "releases",
        "ARCHIVE_DIR": runtime / "archive",
        "SYSTEMD_UNIT_FILE": root / "systemd" / deploy.SERVICE_NAME,
        "ENV_FILE": root / "etc" / "projection.env",
        "PROJECTION_STATE_DIR": runtime / "state" / "projection-v2",
        "LEGACY_STATE_DIR": runtime / "legacy-state",
        "PROJECTION_SECRETS_DIR": runtime / "projection-secrets",
        "PROJECTION_KEY_DEST": runtime / "projection-secrets" / "hmac.key",
        "PROJECTION_SERVICE_USER": pwd.getpwuid(os.getuid()).pw_name,
        "PROJECTION_SERVICE_GROUP": grp.getgrgid(os.getgid()).gr_name,
    }
    originals = {name: getattr(deploy, name) for name in replacements}
    for name, value in replacements.items():
        setattr(deploy, name, value)
    try:
        yield
    finally:
        for name, value in originals.items():
            setattr(deploy, name, value)


def _load_runner() -> Any:
    module_name = "dev_control_plane_hosted_deploy_state_machine_smoke"
    spec = importlib.util.spec_from_file_location(module_name, RUNNER)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not import hosted deploy runner")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


if __name__ == "__main__":
    main()
