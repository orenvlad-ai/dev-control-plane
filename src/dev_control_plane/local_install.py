"""Safe, versioned macOS installation for the local Orchestrator v2 service."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import errno
import fcntl
import hashlib
import hmac
import http.client
import json
import math
import os
from pathlib import Path
from pathlib import PurePosixPath
import plistlib
import re
import secrets
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable, Mapping

from .migration import (
    LEGACY_MONITOR_DB,
    LEGACY_MONITOR_LABEL,
    LEGACY_MONITOR_PLIST,
    MigrationError,
    verify_legacy_absence_manifest,
    verify_legacy_archive_manifest,
)
from .orchestration_contracts import (
    OrchestrationValidationError,
    checkpoint_from_mapping,
    contract_digest,
    contract_to_dict,
    task_passport_from_mapping,
    validate_workstream_against_passport,
    workstream_from_mapping,
)
from .v2_suite_contract import AUTHORITATIVE_CHECK_COUNT, AUTHORITATIVE_SMOKES
from .supervisor_registry import (
    PREACTIVATION_CAUSAL_READ_KIND,
    PREACTIVATION_CAUSAL_REMEDIATION_EXPECTED_OUTPUT_GENERATION,
    PREACTIVATION_CAUSAL_REMEDIATION_PR92_HEAD_SHA,
    PREACTIVATION_CAUSAL_REMEDIATION_PR92_MERGE_SHA,
    PREACTIVATION_CAUSAL_REMEDIATION_SOURCE_EXECUTOR_GENERATION,
    PREACTIVATION_CAUSAL_REMEDIATION_SOURCE_TASK_REVISION,
    PREACTIVATION_CAUSAL_REMEDIATION_SOURCE_WORKSTREAM_GENERATION,
    PREACTIVATION_CAUSAL_REMEDIATION_SOURCE_WORKSTREAM_REVISION,
    PREACTIVATION_CAUSAL_REMEDIATION_STRATEGY_RESOURCE,
    PREACTIVATION_CAUSAL_REMEDIATION_SUCCESSOR_EXECUTOR_GENERATION,
    PREACTIVATION_CAUSAL_REMEDIATION_SUCCESSOR_TASK_REVISION,
    PREACTIVATION_CAUSAL_REMEDIATION_SUCCESSOR_WORKSTREAM_GENERATION,
    PREACTIVATION_CAUSAL_SUCCESSOR_KIND,
    PREACTIVATION_ORDINARY_POLICY_OUTBOX_KINDS,
    PREACTIVATION_STRUCTURAL_REPAIR_CANONICAL_TARGET,
    PREACTIVATION_STRUCTURAL_REPAIR_PREDECESSOR_SHA,
    PREACTIVATION_STRUCTURAL_REPAIR_TASK_ID,
    PREACTIVATION_STRUCTURAL_REPAIR_WORKSTREAM_ID,
    SupervisorRegistry,
)


LAUNCHD_LABEL = "com.orenvlad.dev-control-plane-v2"
DEFAULT_PORT = 8766
RUNTIME_DIR_NAME = ".dev-control-plane-v2"
ACTIVATION_TIMEOUT_SECONDS = 30.0
ACTIVATION_POLL_SECONDS = 0.25
MAX_READINESS_BYTES = 64 * 1024
LOCAL_QUALIFICATION_SCHEMA = "dev-control-plane/local-qualification/v2"
LOCAL_QUALIFICATION_MAX_AGE = timedelta(hours=24)
DESKTOP_CODEX_BINARY = "/Applications/ChatGPT.app/Contents/Resources/codex"
LOCAL_ACCEPTANCE_SCHEMA = "dev-control-plane/local-activation-acceptance/v2"
LOCAL_INSTALL_TRANSACTION_SCHEMA = "dev-control-plane/local-install-transaction/v2"
LOCAL_INSTALL_TRANSACTION_RESULT_SCHEMA = "dev-control-plane/local-install-transaction-result/v2"
LOCAL_INSTALL_QUARANTINE_SCHEMA = "dev-control-plane/local-install-quarantine/v2"
RUNTIME_QUALIFICATION_SCHEMA = "dev-control-plane/runtime-qualification-evidence/v2"
APP_SERVER_CANARY_EVIDENCE_SCHEMA = "dev-control-plane/app-server-canary-evidence/v2"
STAGED_RUNTIME_EVIDENCE_SCHEMA = "dev-control-plane/staged-runtime-evidence/v2"
PREACTIVATION_RECOVERY_SCHEMA = "dev-control-plane/preactivation-recovery/v2"
PREACTIVATION_RECOVERY_RECEIPT_SCHEMA = (
    "dev-control-plane/preactivation-recovery-receipt/v2"
)
PREACTIVATION_RECOVERY_JOURNAL_SCHEMA = (
    "dev-control-plane/preactivation-recovery-journal/v2"
)
PREACTIVATION_REMEDIATION_EVIDENCE_SCHEMA = (
    "dev-control-plane/preactivation-remediation-evidence/v2"
)
PREACTIVATION_CAUSAL_REMEDIATION_EVIDENCE_SCHEMA = (
    "dev-control-plane/preactivation-causal-qualification-evidence/v3"
)
PREACTIVATION_STRUCTURAL_REPAIR_SCHEMA = (
    "dev-control-plane/preactivation-structural-repair/v2"
)
PREACTIVATION_STRUCTURAL_REPAIR_COMPLETION_SCHEMA = (
    "dev-control-plane/preactivation-structural-repair-completion/v2"
)
PREACTIVATION_STRUCTURAL_REPAIR_EVENT_TYPE = "preactivation_structural_repair"
PREACTIVATION_STRUCTURAL_REPAIR_COMPLETION_EVENT_TYPE = (
    "preactivation_structural_repair_completed"
)
PREACTIVATION_STRUCTURAL_SUCCESSOR_KIND = "codex_preactivation_successor_start"
PREACTIVATION_CAUSAL_REMEDIATION_SCHEMA = (
    "dev-control-plane/preactivation-causal-remediation/v3"
)
PREACTIVATION_CAUSAL_ATTESTATION_SCHEMA = (
    "dev-control-plane/preactivation-causal-attestation/v3"
)
PREACTIVATION_CAUSAL_COMPLETION_SCHEMA = (
    "dev-control-plane/preactivation-causal-remediation-completion/v3"
)
PREACTIVATION_CAUSAL_REMEDIATION_EVENT_TYPE = (
    "preactivation_causal_remediation"
)
PREACTIVATION_CAUSAL_ATTESTATION_EVENT_TYPE = (
    "preactivation_causal_attestation"
)
PREACTIVATION_CAUSAL_COMPLETION_EVENT_TYPE = (
    "preactivation_causal_remediation_completed"
)
PREACTIVATION_CAUSAL_RESTART_ATTESTATION_SCHEMA = (
    "dev-control-plane/preactivation-causal-restart-attestation/v3"
)
PREACTIVATION_CAUSAL_RESTART_ATTESTATION_EVENT_TYPE = (
    "preactivation_causal_restart_attested"
)
PREACTIVATION_CAUSAL_TURN_RECOVERY_SCHEMA = (
    "dev-control-plane/preactivation-causal-canary-turn-recovery/v3"
)
PREACTIVATION_CAUSAL_TURN_RECOVERY_EVENT_TYPE = (
    "preactivation_causal_canary_turn_recovered"
)
PREACTIVATION_RELEASE_ADMISSION_SCHEMA = (
    "dev-control-plane/release-candidate-admission/v2"
)
PREACTIVATION_PR91_HEAD_SHA = "958054318a1b5eecd6550e61f7f834872014f96b"
PREACTIVATION_SOURCE_RELEASE_SHA = "e0a4528506a27b8c351e0cc4e71576b7ee017800"
PREACTIVATION_SOURCE_TASK_ID = "orchestrator-v2-bootstrap-e0a45285"
PREACTIVATION_SOURCE_WORKSTREAM_ID = "orchestrator-v2-bootstrap-release"
PREACTIVATION_SOURCE_CAUSAL_FINGERPRINT = (
    "fc2d6187211e692f0813bc8b3a977f455f54bb682f59f8582a4e5fbe8aa66c30"
)
CHECKPOINT_PROGRESS_STAGES = frozenset({5, 15, 25, 40, 55, 65, 72, 80, 88, 95})
_COPY_DIRS = ("apps", "configs", "deploy", "docs", "src")
_COPY_FILES = ("AGENTS.md", "README.md")


class LocalInstallError(RuntimeError):
    """Raised when install/update/rollback cannot be proven safe."""


@dataclass(frozen=True)
class LocalInstallLayout:
    root: Path
    releases: Path
    state: Path
    logs: Path
    secrets: Path
    backups: Path
    qualifications: Path
    transactions: Path
    transaction_receipts: Path
    active_transaction: Path
    transaction_quarantine: Path
    operation_lock: Path
    current: Path
    previous: Path
    staged: Path
    manifest: Path
    staged_manifest: Path
    projection_key: Path
    owner_acceptance_key: Path
    install_acceptance_key: Path
    activation_nonce: Path
    launch_agent: Path
    preactivation_recoveries: Path
    preactivation_recovery_journal: Path
    preactivation_recovery_receipt: Path

    @classmethod
    def resolve(
        cls,
        root: Path | None = None,
        *,
        launch_agents_dir: Path | None = None,
    ) -> "LocalInstallLayout":
        home = Path.home().resolve()
        runtime_root = _layout_path_without_following_final(
            root or home / RUNTIME_DIR_NAME
        )
        if runtime_root in {Path("/"), home}:
            raise LocalInstallError("runtime root is too broad")
        if runtime_root.is_symlink():
            raise LocalInstallError("local runtime root must not be a symlink")
        agents = _layout_path_without_following_final(
            launch_agents_dir or home / "Library" / "LaunchAgents"
        )
        if agents.is_symlink():
            raise LocalInstallError("LaunchAgents directory must not be a symlink")
        return cls(
            root=runtime_root,
            releases=runtime_root / "releases",
            state=runtime_root / "state",
            logs=runtime_root / "logs",
            secrets=runtime_root / "secrets",
            backups=runtime_root / "backups",
            qualifications=runtime_root / "qualifications",
            transactions=runtime_root / "install-transactions",
            transaction_receipts=runtime_root / "install-transactions" / "receipts",
            active_transaction=runtime_root / "install-transactions" / "active",
            transaction_quarantine=runtime_root / "install-transactions" / "QUARANTINED.json",
            operation_lock=runtime_root / ".install.lock",
            current=runtime_root / "current",
            previous=runtime_root / "previous",
            staged=runtime_root / "staged",
            manifest=runtime_root / "install.json",
            staged_manifest=runtime_root / "staged.json",
            projection_key=runtime_root / "secrets" / "projection_hmac.key",
            owner_acceptance_key=runtime_root / "secrets" / "owner_acceptance_hmac.key",
            install_acceptance_key=runtime_root / "secrets" / "install_acceptance_hmac.key",
            activation_nonce=runtime_root / "secrets" / "activation_nonce.bin",
            launch_agent=agents / f"{LAUNCHD_LABEL}.plist",
            preactivation_recoveries=runtime_root / "backups" / "preactivation-recoveries",
            preactivation_recovery_journal=(
                runtime_root / "install-transactions" / "preactivation-recovery-active.json"
            ),
            preactivation_recovery_receipt=runtime_root / "preactivation-recovery.json",
        )


def _layout_path_without_following_final(value: Path) -> Path:
    candidate = Path(os.path.abspath(value.expanduser()))
    return candidate.parent.resolve() / candidate.name


@contextmanager
def _preactivation_lifecycle_lock(
    runtime_root: Path,
    *,
    nonblocking: bool,
    reject_active_journal: bool,
) -> Any:
    """Exclude Supervisor startup from the one preactivation state swap."""

    root = Path(os.path.abspath(runtime_root))
    transactions = root / "install-transactions"
    if root.is_symlink() or transactions.is_symlink():
        raise LocalInstallError("preactivation lifecycle lock parent is unsafe")
    transactions.mkdir(parents=True, exist_ok=True, mode=0o700)
    transactions.chmod(0o700)
    lock_path = transactions / "preactivation-recovery.lock"
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError as exc:
        raise LocalInstallError(
            "preactivation lifecycle lock could not be opened safely"
        ) from exc
    locked = False
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_nlink != 1
        ):
            raise LocalInstallError("preactivation lifecycle lock shape is unsafe")
        operation = fcntl.LOCK_EX | (fcntl.LOCK_NB if nonblocking else 0)
        try:
            fcntl.flock(descriptor, operation)
            locked = True
        except OSError as exc:
            if exc.errno in {errno.EACCES, errno.EAGAIN}:
                raise LocalInstallError(
                    "preactivation recovery excludes Supervisor startup"
                ) from exc
            raise LocalInstallError(
                "preactivation lifecycle lock could not be acquired"
            ) from exc
        if reject_active_journal and os.path.lexists(
            transactions / "preactivation-recovery-active.json"
        ):
            raise LocalInstallError(
                "Supervisor startup is blocked by preactivation recovery"
            )
        yield
    finally:
        if locked:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


@contextmanager
def preactivation_supervisor_start_guard(state_dir: Path) -> Any:
    """Guard the generation acquisition against a concurrent recovery swap."""

    state = Path(os.path.abspath(state_dir))
    if state.name != "state":
        raise LocalInstallError("Supervisor state directory is not the canonical runtime state")
    with _preactivation_lifecycle_lock(
        state.parent,
        nonblocking=True,
        reject_active_journal=True,
    ):
        yield


@dataclass(frozen=True)
class LocalInstallResult:
    status: str
    commit_sha: str
    release_dir: str
    current_release: str | None
    previous_release: str | None
    staged_release: str | None
    launch_agent: str
    activated: bool
    projection_key_present: bool


@dataclass(frozen=True)
class PreActivationRecoveryResult:
    status: str
    replacement_sha: str
    failed_release_sha: str
    recovery_id: str
    archive_dir: str
    manifest_path: str
    backup_path: str
    backup_sha256: str
    prior_supervisor_generation: int
    prior_projection_generation: int
    prior_projection_sequence: int
    prior_projection_revision: int
    model_attempt_count: int
    model_call_count: int
    legacy_monitor_touched: bool


@dataclass(frozen=True)
class _InstallSnapshot:
    target_sha: str
    current: Path | None
    previous: Path | None
    staged: Path | None
    launch_agent: bytes | None
    manifest: bytes | None
    staged_manifest: bytes | None
    activation_nonce: bytes | None
    accepted_qualification: bytes | None
    acceptance_receipt: bytes | None
    python_executable: str | None
    activation_nonce_digest: str | None
    service_loaded: bool
    readiness_generation: int | None


class LocalInstaller:
    def __init__(
        self,
        layout: LocalInstallLayout,
        *,
        command_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
        source_gate: Callable[..., str] | None = None,
        process_identity_probe: Callable[[int, Path, Path, str, int], bool] | None = None,
        legacy_launchd_probe: Callable[[str], bool] | None = None,
        legacy_artifact_probe: Callable[[], bool] | None = None,
        readiness_probe: Callable[[], Mapping[str, Any] | None] | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
        monotonic_fn: Callable[[], float] = time.monotonic,
        activation_timeout_seconds: float = ACTIVATION_TIMEOUT_SECONDS,
        fault_injector: Callable[[str], None] | None = None,
    ) -> None:
        if activation_timeout_seconds <= 0:
            raise ValueError("activation_timeout_seconds must be positive")
        self.layout = layout
        self._command_runner = command_runner
        self._source_gate = source_gate or _source_gate
        self._process_identity_probe = process_identity_probe or _process_identity_probe
        self._legacy_launchd_probe = legacy_launchd_probe or _legacy_launchd_absent_probe
        self._legacy_artifact_probe = legacy_artifact_probe or _legacy_artifacts_absent_probe
        self._readiness_probe = readiness_probe or _http_readiness_probe
        self._sleep_fn = sleep_fn
        self._monotonic_fn = monotonic_fn
        self._activation_timeout_seconds = float(activation_timeout_seconds)
        self._fault_injector = fault_injector

    def install(
        self,
        *,
        source_root: Path,
        expected_sha: str | None = None,
        require_origin_main: bool = True,
        activate: bool = False,
        python_binary: Path | None = None,
        qualification_manifest: Path | None = None,
    ) -> LocalInstallResult:
        if activate and not require_origin_main:
            raise LocalInstallError("activation requires exact origin/main; non-main installs must remain inactive")
        self._ensure_layout()
        with self._operation_lock():
            self._recover_interrupted_transaction()
            return self._install_locked(
                source_root=source_root,
                expected_sha=expected_sha,
                require_origin_main=require_origin_main,
                activate=activate,
                python_binary=python_binary,
                qualification_manifest=qualification_manifest,
            )

    def _install_locked(
        self,
        *,
        source_root: Path,
        expected_sha: str | None,
        require_origin_main: bool,
        activate: bool,
        python_binary: Path | None,
        qualification_manifest: Path | None,
    ) -> LocalInstallResult:
        source = source_root.resolve()
        sha = self._source_gate(source, expected_sha=expected_sha, require_origin_main=require_origin_main)
        release = self.layout.releases / sha
        if not (release.exists() or release.is_symlink()):
            self._copy_release(source, release, sha)
        self._verify_release(release, sha, source=source)
        # The release bytes came from the immutable Git object, but activation
        # must also prove that the source checkout and freshly fetched
        # origin/main still identify that exact object after packaging.
        repeated_sha = self._source_gate(
            source,
            expected_sha=sha,
            require_origin_main=require_origin_main,
        )
        if repeated_sha != sha:
            raise LocalInstallError("source identity changed while packaging the release")
        self._ensure_projection_key()
        self._ensure_owner_acceptance_key()
        self._ensure_install_acceptance_key()
        self._ensure_activation_nonce()
        if not activate:
            current = self._release_link_target(self.layout.current)
            previous = self._release_link_target(self.layout.previous)
            self._stage_release(release, sha=sha, operation="install")
            return LocalInstallResult(
                status="staged",
                commit_sha=sha,
                release_dir=str(release),
                current_release=str(current) if current else None,
                previous_release=str(previous) if previous else None,
                staged_release=str(release),
                launch_agent=str(self.layout.launch_agent),
                activated=False,
                projection_key_present=self._projection_key_is_safe(),
            )
        validation_now = datetime.now(timezone.utc)
        qualification_bytes, qualification_digest, legacy_absence = self._validate_qualification(
            qualification_manifest,
            expected_sha=sha,
            validation_now=validation_now,
            source_root=source,
        )
        snapshot = self._capture_snapshot(target_sha=sha)
        transaction_id = self._begin_transaction(
            operation="install",
            target_sha=sha,
            snapshot=snapshot,
        )
        old_current: Path | None = None
        next_previous: Path | None = None
        try:
            self._fault_boundary("after_transaction_journal")
            old_current = self._release_link_target(self.layout.current)
            old_previous = self._release_link_target(self.layout.previous)
            next_previous = old_current if old_current and old_current != release else old_previous
            if next_previous is not None:
                _atomic_symlink(next_previous, self.layout.previous)
            self._fault_boundary("after_previous_pointer")
            _atomic_symlink(release, self.layout.current)
            self._fault_boundary("after_current_pointer")
            executable = python_binary or Path(sys.executable).resolve()
            nonce_digest = self._rotate_activation_nonce()
            self._fault_boundary("after_activation_nonce")
            plist = _launchd_payload(self.layout, executable, release=release)
            _atomic_write_bytes(self.layout.launch_agent, plistlib.dumps(plist), mode=0o600)
            self._fault_boundary("after_launch_agent")
            manifest = {
                "schema": "dev-control-plane/local-install/v2",
                "commit_sha": sha,
                "release_dir": str(release),
                "current_release": str(release),
                "previous_release": str(next_previous) if next_previous else None,
                "launchd_label": LAUNCHD_LABEL,
                "port": DEFAULT_PORT,
                "qualification_digest": qualification_digest,
                "activation_nonce_sha256": nonce_digest,
            }
            _atomic_write_json(self.layout.manifest, manifest, mode=0o600)
            self._fault_boundary("after_install_manifest")
            self._set_transaction_phase(transaction_id, "launching")
            activation = self._activate_launchd(
                expected_release=release,
                previous_generation=snapshot.readiness_generation,
                expected_python=executable,
                expected_nonce_digest=nonce_digest,
                require_legacy_artifact_absence=legacy_absence,
            )
            self._fault_boundary("after_launchd_activation")
            self._accept_qualification(
                sha,
                qualification_bytes,
                release=release,
                supervisor_generation=int(activation["supervisor_generation"]),
                activation_nonce_sha256=nonce_digest,
            )
            self._fault_boundary("after_qualification_acceptance")
            self._clear_staged(expected_release=release)
            self._fault_boundary("after_staged_clear")
            self._set_transaction_phase(transaction_id, "committed")
            self._fault_boundary("after_commit_marker")
            self._archive_transaction(transaction_id, outcome="COMMITTED")
        except Exception as exc:
            if self._transaction_is_committed(transaction_id):
                raise LocalInstallError(
                    "local activation committed; durable receipt archival is pending recovery"
                ) from exc
            self._rollback_failed_activation(
                snapshot,
                transaction_id=transaction_id,
                activation_error=exc,
            )
        return LocalInstallResult(
            status="installed",
            commit_sha=sha,
            release_dir=str(release),
            current_release=str(release),
            previous_release=str(next_previous) if next_previous else None,
            staged_release=None,
            launch_agent=str(self.layout.launch_agent),
            activated=activate,
            projection_key_present=self._projection_key_is_safe(),
        )

    def rollback(self, *, activate: bool = False) -> LocalInstallResult:
        self._ensure_layout()
        with self._operation_lock():
            self._recover_interrupted_transaction()
            return self._rollback_locked(activate=activate)

    def _rollback_locked(self, *, activate: bool) -> LocalInstallResult:
        self._ensure_projection_key()
        self._ensure_owner_acceptance_key()
        self._ensure_install_acceptance_key()
        self._ensure_activation_nonce()
        previous = self._release_link_target(self.layout.previous)
        current = self._release_link_target(self.layout.current)
        if previous is None:
            raise LocalInstallError("no recoverable previous release is recorded")
        self._verify_release(previous, previous.name)
        if not activate:
            self._stage_release(previous, sha=previous.name, operation="rollback")
            return LocalInstallResult(
                status="rollback_staged",
                commit_sha=previous.name,
                release_dir=str(previous),
                current_release=str(current) if current else None,
                previous_release=str(previous),
                staged_release=str(previous),
                launch_agent=str(self.layout.launch_agent),
                activated=False,
                projection_key_present=self._projection_key_is_safe(),
            )
        if current is None or current == previous:
            raise LocalInstallError(
                "live local rollback requires two distinct accepted v2 releases"
            )
        self._verify_release(current, current.name)
        validation_now = datetime.now(timezone.utc)
        self._validate_qualification(
            self.layout.qualifications / f"{current.name}.accepted.json",
            expected_sha=current.name,
            validation_now=validation_now,
        )
        qualification_bytes, qualification_digest, legacy_absence = self._validate_qualification(
            self.layout.qualifications / f"{previous.name}.accepted.json",
            expected_sha=previous.name,
            validation_now=validation_now,
        )
        snapshot = self._capture_snapshot(target_sha=previous.name)
        manifest = _read_json(self.layout.manifest)
        manifest.update(
            {
                "commit_sha": previous.name,
                "release_dir": str(previous),
                "current_release": str(previous),
                "previous_release": str(current) if current and current != previous else None,
                "rollback_applied": True,
                "qualification_digest": qualification_digest,
            }
        )
        transaction_id = self._begin_transaction(
            operation="rollback",
            target_sha=previous.name,
            snapshot=snapshot,
        )
        try:
            self._fault_boundary("after_transaction_journal")
            if current and current != previous:
                _atomic_symlink(current, self.layout.previous)
            self._fault_boundary("after_previous_pointer")
            _atomic_symlink(previous, self.layout.current)
            self._fault_boundary("after_current_pointer")
            executable = Path(sys.executable).resolve()
            nonce_digest = self._rotate_activation_nonce()
            self._fault_boundary("after_activation_nonce")
            manifest["activation_nonce_sha256"] = nonce_digest
            _atomic_write_bytes(
                self.layout.launch_agent,
                plistlib.dumps(_launchd_payload(self.layout, executable, release=previous)),
                mode=0o600,
            )
            self._fault_boundary("after_launch_agent")
            _atomic_write_json(self.layout.manifest, manifest, mode=0o600)
            self._fault_boundary("after_install_manifest")
            self._set_transaction_phase(transaction_id, "launching")
            activation = self._activate_launchd(
                expected_release=previous,
                previous_generation=snapshot.readiness_generation,
                expected_python=executable,
                expected_nonce_digest=nonce_digest,
                require_legacy_artifact_absence=legacy_absence,
            )
            self._fault_boundary("after_launchd_activation")
            self._accept_qualification(
                previous.name,
                qualification_bytes,
                release=previous,
                supervisor_generation=int(activation["supervisor_generation"]),
                activation_nonce_sha256=nonce_digest,
            )
            self._fault_boundary("after_qualification_acceptance")
            self._clear_staged(expected_release=previous)
            self._fault_boundary("after_staged_clear")
            self._set_transaction_phase(transaction_id, "committed")
            self._fault_boundary("after_commit_marker")
            self._archive_transaction(transaction_id, outcome="COMMITTED")
        except Exception as exc:
            if self._transaction_is_committed(transaction_id):
                raise LocalInstallError(
                    "local rollback committed; durable receipt archival is pending recovery"
                ) from exc
            self._rollback_failed_activation(
                snapshot,
                transaction_id=transaction_id,
                activation_error=exc,
            )
        return LocalInstallResult(
            status="rolled_back",
            commit_sha=previous.name,
            release_dir=str(previous),
            current_release=str(previous),
            previous_release=str(current) if current and current != previous else None,
            staged_release=None,
            launch_agent=str(self.layout.launch_agent),
            activated=activate,
            projection_key_present=self._projection_key_is_safe(),
        )

    def recover_preactivation(
        self,
        *,
        source_root: Path,
        expected_sha: str,
    ) -> PreActivationRecoveryResult:
        """Archive one exact zero-call bootstrap failure before first activation.

        This is intentionally not a generic reset path.  It accepts only the
        historical first-pilot failure caused by ``thread/read`` preceding the
        durable model-call intent.  The complete old state tree remains in a
        private archive, while the new registry carries forward only monotonic
        fencing and projection watermarks.
        """

        self._ensure_preactivation_parent_layout()
        with self._operation_lock(), _preactivation_lifecycle_lock(
            self.layout.root,
            nonblocking=False,
            reject_active_journal=False,
        ):
            source = source_root.resolve()
            sha = self._source_gate(
                source,
                expected_sha=expected_sha,
                require_origin_main=True,
            )
            if sha != expected_sha:
                raise LocalInstallError("preactivation recovery source identity mismatch")
            existing = _read_optional_regular_file(
                self.layout.preactivation_recovery_receipt,
                max_bytes=1_000_000,
            )
            if existing is not None:
                result = verify_preactivation_recovery_receipt(
                    self.layout.preactivation_recovery_receipt,
                    expected_replacement_sha=sha,
                    runtime_root=self.layout.root,
                )
                self._clear_completed_preactivation_recovery_journal(result)
                return PreActivationRecoveryResult(
                    status="already_recovered",
                    **{
                        key: result[key]
                        for key in PreActivationRecoveryResult.__dataclass_fields__
                        if key != "status"
                    },
                )
            journal_raw = _read_optional_regular_file(
                self.layout.preactivation_recovery_journal,
                max_bytes=1_000_000,
            )
            if journal_raw is not None:
                journal = _decode_preactivation_journal(journal_raw)
                if journal["replacement_sha"] != sha:
                    raise LocalInstallError(
                        "active preactivation recovery is bound to another replacement"
                    )
                return self._resume_preactivation_recovery(journal)

            if tuple(self.layout.preactivation_recoveries.iterdir()) or tuple(
                self.layout.root.glob(".state.preactivation.*")
            ):
                raise LocalInstallError(
                    "preactivation recovery found an unbound prior archive attempt"
                )

            self._ensure_layout()
            self._assert_preactivation_recovery_source(source, sha)
            report = _inspect_failed_preactivation_registry(
                self.layout.state,
                expected_replacement_sha=sha,
            )
            recovery_id = (
                datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
                + "-"
                + secrets.token_hex(4)
            )
            archive_dir = self.layout.preactivation_recoveries / recovery_id
            fresh_state = self.layout.root / f".state.preactivation.{recovery_id}"
            old_metadata = self.layout.state.lstat()
            manifest_path = archive_dir / "manifest.json"
            journal = {
                "schema": PREACTIVATION_RECOVERY_JOURNAL_SCHEMA,
                "recovery_id": recovery_id,
                "phase": "allocating",
                "replacement_sha": sha,
                "failed_release_sha": report["failed_release_sha"],
                "archive_dir": str(archive_dir),
                "archive_state": str(archive_dir / "state"),
                "fresh_state": str(fresh_state),
                "backup_path": str(archive_dir / "supervisor.sqlite3"),
                "backup_sha256": "0" * 64,
                "source_registry_digest": report["registry_digest"],
                "source_table_counts": report["table_counts"],
                "source_task_id": report["source_task_id"],
                "source_workstream_id": report["source_workstream_id"],
                "source_executor_generation": report["source_executor_generation"],
                "source_thread_id": report["source_thread_id"],
                "source_host_id": report["source_host_id"],
                "source_failure_event_ids": report["source_failure_event_ids"],
                "source_followup_event_id": report["source_followup_event_id"],
                "source_attention_event_id": report["source_attention_event_id"],
                "source_causal_fingerprint": report["source_causal_fingerprint"],
                "manifest_path": str(manifest_path),
                "old_state_dev": int(old_metadata.st_dev),
                "old_state_ino": int(old_metadata.st_ino),
                "fresh_state_dev": 0,
                "fresh_state_ino": 0,
                "prior_supervisor_generation": report["supervisor_generation"],
                "prior_projection_generation": report["projection_generation"],
                "prior_projection_sequence": report["projection_sequence"],
                "prior_projection_revision": report["projection_revision"],
                "model_attempt_count": 0,
                "model_call_count": 0,
                "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            }
            _atomic_write_json(
                self.layout.preactivation_recovery_journal,
                journal,
                mode=0o600,
            )
            self._fault_boundary("after_preactivation_recovery_intent")
            return self._resume_preactivation_recovery(journal)

    def _clear_completed_preactivation_recovery_journal(
        self,
        verified_receipt: Mapping[str, Any],
    ) -> None:
        raw = _read_optional_regular_file(
            self.layout.preactivation_recovery_journal,
            max_bytes=1_000_000,
        )
        if raw is None:
            return
        journal = _validated_preactivation_journal(
            _decode_preactivation_journal(raw),
            self.layout,
        )
        if (
            journal["replacement_sha"] != verified_receipt["replacement_sha"]
            or journal["recovery_id"] != verified_receipt["recovery_id"]
            or journal["backup_sha256"] != verified_receipt["backup_sha256"]
            or journal["archive_dir"] != verified_receipt["archive_dir"]
        ):
            raise LocalInstallError(
                "completed preactivation receipt does not bind the active journal"
            )
        self.layout.preactivation_recovery_journal.unlink()
        _fsync_directory(self.layout.preactivation_recovery_journal.parent)

    def _resume_preactivation_recovery(
        self,
        journal: Mapping[str, Any],
    ) -> PreActivationRecoveryResult:
        journal = _validated_preactivation_journal(journal, self.layout)
        self._assert_preactivation_service_absent()
        phase = str(journal["phase"])
        archive_state = Path(str(journal["archive_state"]))
        fresh_state = Path(str(journal["fresh_state"]))
        if phase == "allocating":
            _require_directory_identity(
                self.layout.state,
                int(journal["old_state_dev"]),
                int(journal["old_state_ino"]),
                "preactivation source state",
            )
            archive_dir = Path(str(journal["archive_dir"]))
            if not os.path.lexists(archive_dir):
                archive_dir.mkdir(mode=0o700)
                archive_dir.chmod(0o700)
                _fsync_directory(archive_dir.parent)
            else:
                metadata = archive_dir.lstat()
                if (
                    not stat.S_ISDIR(metadata.st_mode)
                    or archive_dir.is_symlink()
                    or metadata.st_uid != os.geteuid()
                    or stat.S_IMODE(metadata.st_mode) != 0o700
                ):
                    raise LocalInstallError(
                        "preactivation preparation archive directory is unsafe"
                    )
            for partial in archive_dir.glob(".preactivation.*.sqlite3"):
                _private_regular_metadata(partial)
                partial.unlink()
            _fsync_directory(archive_dir)
            unexpected_archive_entries = {
                path.name
                for path in archive_dir.iterdir()
                if path.name != "supervisor.sqlite3"
            }
            if unexpected_archive_entries:
                raise LocalInstallError(
                    "preactivation preparation archive contains unbound artifacts"
                )

            backup = Path(str(journal["backup_path"]))
            if os.path.lexists(backup):
                backup_sha256 = _secure_file_sha256(backup)
                backup_registry_digest = _sqlite_logical_digest(
                    connection_path=backup
                )
                backup_connection = sqlite3.connect(
                    _sqlite_readonly_uri(backup), uri=True, timeout=10
                )
                try:
                    table_counts = _sqlite_table_counts(backup_connection)
                finally:
                    backup_connection.close()
            else:
                (
                    backup,
                    backup_sha256,
                    table_counts,
                    backup_registry_digest,
                ) = _secure_sqlite_archive(
                    self.layout.state / "supervisor.sqlite3",
                    backup,
                )
            if (
                table_counts != journal["source_table_counts"]
                or backup_registry_digest != journal["source_registry_digest"]
            ):
                raise LocalInstallError(
                    "preactivation preparation backup differs from its intent"
                )

            if not os.path.lexists(fresh_state):
                fresh_state.mkdir(mode=0o700)
            fresh_metadata = fresh_state.lstat()
            if (
                not stat.S_ISDIR(fresh_metadata.st_mode)
                or fresh_state.is_symlink()
                or fresh_metadata.st_uid != os.geteuid()
                or stat.S_IMODE(fresh_metadata.st_mode) != 0o700
            ):
                raise LocalInstallError(
                    "preactivation prepared state directory is unsafe"
                )
            workspace_root = fresh_state / "managed_workspaces"
            workspace_root.mkdir(mode=0o700, exist_ok=True)
            workspace_root.chmod(0o700)
            fresh_registry = SupervisorRegistry(fresh_state / "supervisor.sqlite3")
            if (
                fresh_registry.current_generation().get("generation") == 0
                and fresh_registry.projection_transport_state()
                == {"generation": 0, "sequence": 0, "revision": 0}
            ):
                fresh_registry.seed_pristine_preactivation_recovery_watermarks(
                    archived_supervisor_generation=int(
                        journal["prior_supervisor_generation"]
                    ),
                    archived_projection_generation=int(
                        journal["prior_projection_generation"]
                    ),
                    archived_projection_sequence=int(
                        journal["prior_projection_sequence"]
                    ),
                    archived_projection_revision=int(
                        journal["prior_projection_revision"]
                    ),
                )
            _verify_fresh_recovery_state(
                fresh_state,
                expected={
                    "supervisor_generation": journal["prior_supervisor_generation"],
                    "projection_generation": journal["prior_projection_generation"],
                    "projection_sequence": journal["prior_projection_sequence"],
                    "projection_revision": journal["prior_projection_revision"],
                },
            )
            _seal_prepared_recovery_state(fresh_state)
            fresh_metadata = fresh_state.lstat()
            journal = {
                **journal,
                "phase": "prepared",
                "backup_sha256": backup_sha256,
                "fresh_state_dev": int(fresh_metadata.st_dev),
                "fresh_state_ino": int(fresh_metadata.st_ino),
            }
            _atomic_write_json(
                self.layout.preactivation_recovery_journal,
                dict(journal),
                mode=0o600,
            )
            self._fault_boundary("after_preactivation_recovery_journal")
            phase = "prepared"
        if phase == "prepared":
            if os.path.lexists(archive_state):
                _require_directory_identity(
                    archive_state,
                    int(journal["old_state_dev"]),
                    int(journal["old_state_ino"]),
                    "archived preactivation state",
                )
            else:
                _require_directory_identity(
                    self.layout.state,
                    int(journal["old_state_dev"]),
                    int(journal["old_state_ino"]),
                    "preactivation source state",
                )
                os.replace(self.layout.state, archive_state)
                _fsync_directory(self.layout.root)
                _fsync_directory(archive_state.parent)
            journal = {**journal, "phase": "old_state_archived"}
            _atomic_write_json(
                self.layout.preactivation_recovery_journal,
                dict(journal),
                mode=0o600,
            )
            self._fault_boundary("after_preactivation_old_state_archive")
            phase = "old_state_archived"

        if phase == "old_state_archived":
            _require_directory_identity(
                archive_state,
                int(journal["old_state_dev"]),
                int(journal["old_state_ino"]),
                "archived preactivation state",
            )
            if os.path.lexists(fresh_state):
                if os.path.lexists(self.layout.state):
                    raise LocalInstallError(
                        "both canonical and prepared preactivation states exist"
                    )
                _require_directory_identity(
                    fresh_state,
                    int(journal["fresh_state_dev"]),
                    int(journal["fresh_state_ino"]),
                    "prepared preactivation state",
                )
                os.replace(fresh_state, self.layout.state)
                _fsync_directory(self.layout.root)
            else:
                _require_directory_identity(
                    self.layout.state,
                    int(journal["fresh_state_dev"]),
                    int(journal["fresh_state_ino"]),
                    "installed preactivation state",
                )
            journal = {**journal, "phase": "fresh_state_installed"}
            _atomic_write_json(
                self.layout.preactivation_recovery_journal,
                dict(journal),
                mode=0o600,
            )
            self._fault_boundary("after_preactivation_fresh_state_install")
            phase = "fresh_state_installed"

        if phase != "fresh_state_installed":
            raise LocalInstallError("preactivation recovery journal phase is not resumable")
        _require_directory_identity(
            archive_state,
            int(journal["old_state_dev"]),
            int(journal["old_state_ino"]),
            "archived preactivation state",
        )
        _require_directory_identity(
            self.layout.state,
            int(journal["fresh_state_dev"]),
            int(journal["fresh_state_ino"]),
            "installed preactivation state",
        )
        expected = {
            "supervisor_generation": int(journal["prior_supervisor_generation"]),
            "projection_generation": int(journal["prior_projection_generation"]),
            "projection_sequence": int(journal["prior_projection_sequence"]),
            "projection_revision": int(journal["prior_projection_revision"]),
        }
        _verify_fresh_recovery_state(self.layout.state, expected=expected)
        backup = Path(str(journal["backup_path"]))
        if _secure_file_sha256(backup) != journal["backup_sha256"]:
            raise LocalInstallError("preactivation recovery backup digest changed")
        if (
            _sqlite_logical_digest(connection_path=backup)
            != journal["source_registry_digest"]
            or _sqlite_logical_digest(
                connection_path=archive_state / "supervisor.sqlite3"
            )
            != journal["source_registry_digest"]
        ):
            raise LocalInstallError("preactivation archived registry content changed")
        manifest = {
            "schema": PREACTIVATION_RECOVERY_SCHEMA,
            "status": "recovered",
            "recovery_id": journal["recovery_id"],
            "replacement_sha": journal["replacement_sha"],
            "failed_release_sha": journal["failed_release_sha"],
            "archive_dir": journal["archive_dir"],
            "archive_state": journal["archive_state"],
            "backup_path": journal["backup_path"],
            "backup_sha256": journal["backup_sha256"],
            "source_registry_digest": journal["source_registry_digest"],
            "source_table_counts": journal["source_table_counts"],
            "source_task_id": journal["source_task_id"],
            "source_workstream_id": journal["source_workstream_id"],
            "source_executor_generation": journal["source_executor_generation"],
            "source_thread_id": journal["source_thread_id"],
            "source_host_id": journal["source_host_id"],
            "source_failure_event_ids": journal["source_failure_event_ids"],
            "source_followup_event_id": journal["source_followup_event_id"],
            "source_attention_event_id": journal["source_attention_event_id"],
            "source_causal_fingerprint": journal["source_causal_fingerprint"],
            "prior_supervisor_generation": journal["prior_supervisor_generation"],
            "prior_projection_generation": journal["prior_projection_generation"],
            "prior_projection_sequence": journal["prior_projection_sequence"],
            "prior_projection_revision": journal["prior_projection_revision"],
            "model_attempt_count": 0,
            "model_call_count": 0,
            "cause_code": "legacy_empty_thread_read_before_call_intent",
            "old_registry_archived": True,
            "fresh_registry_task_count": 0,
            "active_task_registry_empty": True,
            "one_shot": True,
            "real_model_calls": 0,
            "legacy_monitor_touched": False,
            "recovered_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        manifest_path = Path(str(journal["manifest_path"]))
        _atomic_write_json(manifest_path, manifest, mode=0o600)
        manifest_sha256 = _secure_file_sha256(manifest_path)
        receipt = {
            "schema": PREACTIVATION_RECOVERY_RECEIPT_SCHEMA,
            **manifest,
            "manifest_path": str(manifest_path),
            "manifest_sha256": manifest_sha256,
            "receipt_path": str(self.layout.preactivation_recovery_receipt),
        }
        receipt.pop("schema")
        receipt["schema"] = PREACTIVATION_RECOVERY_RECEIPT_SCHEMA
        qualification_recovery = (
            self.layout.qualifications
            / f"{journal['replacement_sha']}.preactivation-recovery.json"
        )
        committed_journal = {**journal, "phase": "committed"}
        _atomic_write_json(
            Path(str(journal["archive_dir"])) / "transaction.json",
            dict(committed_journal),
            mode=0o600,
        )
        _atomic_write_json(
            qualification_recovery,
            receipt,
            mode=0o600,
        )
        _atomic_write_json(
            self.layout.preactivation_recovery_receipt,
            receipt,
            mode=0o600,
        )
        self._fault_boundary("after_preactivation_recovery_receipt")
        self.layout.preactivation_recovery_journal.unlink()
        _fsync_directory(self.layout.preactivation_recovery_journal.parent)
        verified = verify_preactivation_recovery_receipt(
            self.layout.preactivation_recovery_receipt,
            expected_replacement_sha=str(journal["replacement_sha"]),
            runtime_root=self.layout.root,
        )
        return PreActivationRecoveryResult(
            status="recovered",
            **{
                key: verified[key]
                for key in PreActivationRecoveryResult.__dataclass_fields__
                if key != "status"
            },
        )

    def _ensure_preactivation_parent_layout(self) -> None:
        for path in (
            self.layout.root,
            self.layout.backups,
            self.layout.preactivation_recoveries,
            self.layout.transactions,
            self.layout.launch_agent.parent,
        ):
            if path.is_symlink():
                raise LocalInstallError(
                    f"preactivation recovery directory must not be a symlink: {path}"
                )
            path.mkdir(parents=True, exist_ok=True)
            metadata = path.lstat()
            if not stat.S_ISDIR(metadata.st_mode):
                raise LocalInstallError(
                    f"preactivation recovery path is not a directory: {path}"
                )
            if path != self.layout.launch_agent.parent:
                path.chmod(0o700)

    def _assert_preactivation_recovery_source(
        self,
        source: Path,
        sha: str,
    ) -> None:
        if any(
            os.path.lexists(path)
            for path in (
                self.layout.current,
                self.layout.previous,
                self.layout.manifest,
                self.layout.launch_agent,
                self.layout.active_transaction,
                self.layout.transaction_quarantine,
            )
        ):
            raise LocalInstallError(
                "preactivation recovery requires an untouched first-install boundary"
            )
        if tuple(self.layout.qualifications.glob("*.acceptance-receipt.json")) or tuple(
            self.layout.qualifications.glob("*.accepted.json")
        ):
            raise LocalInstallError(
                "preactivation recovery is forbidden after an activation acceptance"
            )
        release = self.layout.releases / sha
        staged = self._release_link_target(self.layout.staged)
        if staged != release:
            raise LocalInstallError(
                "preactivation recovery replacement is not the exact staged release"
            )
        self._verify_release(release, sha, source=source)
        staged_manifest = _read_json(self.layout.staged_manifest)
        if staged_manifest != {
            "schema": "dev-control-plane/local-staged-release/v2",
            "operation": "install",
            "commit_sha": sha,
            "release_dir": str(release),
        }:
            raise LocalInstallError("preactivation staged manifest binding is invalid")
        repeated = self._source_gate(
            source,
            expected_sha=sha,
            require_origin_main=True,
        )
        if repeated != sha:
            raise LocalInstallError("preactivation source changed during validation")
        self._assert_preactivation_service_absent()

    def _assert_preactivation_service_absent(self) -> None:
        if self._service_loaded():
            raise LocalInstallError("preactivation recovery requires v2 launchd to be unloaded")
        if self._readiness_probe() is not None:
            raise LocalInstallError("preactivation recovery found a live v2 readiness endpoint")
        socket_path = self.layout.state / "supervisor.sock"
        if os.path.lexists(socket_path):
            raise LocalInstallError("preactivation recovery found a Supervisor command socket")

    def status(self) -> dict[str, Any]:
        current = self._release_link_target(self.layout.current)
        previous = self._release_link_target(self.layout.previous)
        staged = self._release_link_target(self.layout.staged)
        manifest = _read_json(self.layout.manifest) if self.layout.manifest.is_file() else {}
        return {
            "status": "installed" if current and current.is_dir() else "not_installed",
            "launchd_label": LAUNCHD_LABEL,
            "current_release": str(current) if current else None,
            "previous_release": str(previous) if previous else None,
            "staged_release": str(staged) if staged else None,
            "commit_sha": manifest.get("commit_sha"),
            "state_dir": str(self.layout.state),
            "projection_key_present": self._projection_key_is_safe(),
            "launch_agent_present": self.layout.launch_agent.is_file(),
            "install_transaction_pending": os.path.lexists(self.layout.active_transaction),
            "install_quarantined": os.path.lexists(self.layout.transaction_quarantine),
            "preactivation_recovered": self.layout.preactivation_recovery_receipt.is_file(),
            "preactivation_recovery_pending": self.layout.preactivation_recovery_journal.is_file(),
        }

    def _stage_release(self, release: Path, *, sha: str, operation: str) -> None:
        """Record an inert candidate without changing any active launchd input."""

        _atomic_symlink(release, self.layout.staged)
        _atomic_write_json(
            self.layout.staged_manifest,
            {
                "schema": "dev-control-plane/local-staged-release/v2",
                "operation": operation,
                "commit_sha": sha,
                "release_dir": str(release),
            },
            mode=0o600,
        )

    def _clear_staged(self, *, expected_release: Path) -> None:
        staged = self._release_link_target(self.layout.staged)
        if staged is not None and staged != expected_release:
            return
        if self.layout.staged.is_symlink():
            self.layout.staged.unlink()
            _fsync_directory(self.layout.staged.parent)
        elif self.layout.staged.exists():
            raise LocalInstallError("staged release pointer is not a symlink")
        _restore_optional_regular_file(self.layout.staged_manifest, None, mode=0o600)

    def _ensure_layout(self) -> None:
        for path in (
            self.layout.root,
            self.layout.releases,
            self.layout.state,
            self.layout.logs,
            self.layout.secrets,
            self.layout.backups,
            self.layout.preactivation_recoveries,
            self.layout.qualifications,
            self.layout.transactions,
            self.layout.transaction_receipts,
            self.layout.state / "managed_workspaces",
            self.layout.launch_agent.parent,
        ):
            if path.is_symlink():
                raise LocalInstallError(f"local runtime directory must not be a symlink: {path}")
            path.mkdir(parents=True, exist_ok=True)
            metadata = path.lstat()
            if not stat.S_ISDIR(metadata.st_mode):
                raise LocalInstallError(f"local runtime path is not a directory: {path}")
        for path in (
            self.layout.root,
            self.layout.releases,
            self.layout.state,
            self.layout.logs,
            self.layout.secrets,
            self.layout.backups,
            self.layout.preactivation_recoveries,
            self.layout.qualifications,
            self.layout.transactions,
            self.layout.transaction_receipts,
            self.layout.state / "managed_workspaces",
        ):
            path.chmod(0o700)

    @contextmanager
    def _operation_lock(self) -> Any:
        """Serialize every installer mutation across processes."""

        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0)
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        created = not os.path.lexists(self.layout.operation_lock)
        try:
            descriptor = os.open(self.layout.operation_lock, flags, 0o600)
        except OSError as exc:
            raise LocalInstallError("local install operation lock could not be opened safely") from exc
        locked = False
        try:
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.geteuid()
                or stat.S_IMODE(metadata.st_mode) != 0o600
                or metadata.st_nlink != 1
            ):
                raise LocalInstallError("local install operation lock permissions or shape are unsafe")
            if created:
                _fsync_directory(self.layout.root)
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
            except OSError as exc:
                if exc.errno in {errno.EACCES, errno.EAGAIN}:
                    raise LocalInstallError("another local install operation is active") from exc
                raise LocalInstallError("local install operation lock could not be acquired") from exc
            yield
        finally:
            if locked:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    def _fault_boundary(self, boundary: str) -> None:
        if self._fault_injector is not None:
            self._fault_injector(boundary)

    def _begin_transaction(
        self,
        *,
        operation: str,
        target_sha: str,
        snapshot: _InstallSnapshot,
    ) -> str:
        if operation not in {"install", "rollback"}:
            raise LocalInstallError("local install transaction operation is invalid")
        if snapshot.target_sha != target_sha or not _lower_hex(target_sha, 40):
            raise LocalInstallError("local install transaction target binding is invalid")
        if os.path.lexists(self.layout.transaction_quarantine):
            raise LocalInstallError("local installer is quarantined; automatic mutation is disabled")
        if os.path.lexists(self.layout.active_transaction):
            raise LocalInstallError("an unresolved local install transaction already exists")
        transaction_id = secrets.token_hex(16)
        staging = self.layout.transactions / f".prepare-{transaction_id}"
        if os.path.lexists(staging):
            raise LocalInstallError("local install transaction staging path already exists")
        staging.mkdir(mode=0o700)
        staging.chmod(0o700)
        files = {
            "launch_agent": snapshot.launch_agent,
            "manifest": snapshot.manifest,
            "staged_manifest": snapshot.staged_manifest,
            "activation_nonce": snapshot.activation_nonce,
            "accepted_qualification": snapshot.accepted_qualification,
            "acceptance_receipt": snapshot.acceptance_receipt,
        }
        file_manifest: dict[str, dict[str, Any]] = {}
        try:
            for name, payload in files.items():
                blob_name = f"{name}.bin"
                if payload is None:
                    file_manifest[name] = {
                        "present": False,
                        "sha256": None,
                        "blob": blob_name,
                    }
                    continue
                _atomic_write_bytes(staging / blob_name, payload, mode=0o600)
                file_manifest[name] = {
                    "present": True,
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "blob": blob_name,
                }
            journal = {
                "schema": LOCAL_INSTALL_TRANSACTION_SCHEMA,
                "transaction_id": transaction_id,
                "operation": operation,
                "target_sha": target_sha,
                "phase": "prepared",
                "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "snapshot": {
                    "current_sha": snapshot.current.name if snapshot.current else None,
                    "previous_sha": snapshot.previous.name if snapshot.previous else None,
                    "staged_sha": snapshot.staged.name if snapshot.staged else None,
                    "service_loaded": snapshot.service_loaded,
                    "readiness_generation": snapshot.readiness_generation,
                    "python_executable": snapshot.python_executable,
                    "activation_nonce_digest": snapshot.activation_nonce_digest,
                    "files": file_manifest,
                },
            }
            _atomic_write_json(staging / "journal.json", journal, mode=0o600)
            _fsync_directory(staging)
            os.replace(staging, self.layout.active_transaction)
            _fsync_directory(self.layout.transactions)
        except Exception:
            if staging.is_dir() and not staging.is_symlink():
                shutil.rmtree(staging)
                _fsync_directory(self.layout.transactions)
            raise
        return transaction_id

    def _read_transaction_journal(self) -> dict[str, Any]:
        active = self.layout.active_transaction
        try:
            metadata = active.lstat()
        except OSError as exc:
            raise LocalInstallError("local install transaction journal is unavailable") from exc
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) != 0o700
        ):
            raise LocalInstallError("local install transaction directory is unsafe")
        raw = _read_private_proof_file(active / "journal.json", max_bytes=256 * 1024)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise LocalInstallError("local install transaction journal is invalid JSON") from exc
        expected = {
            "schema", "transaction_id", "operation", "target_sha", "phase", "created_at", "snapshot",
        }
        if not isinstance(payload, dict) or set(payload) != expected:
            raise LocalInstallError("local install transaction journal fields are invalid")
        if (
            payload.get("schema") != LOCAL_INSTALL_TRANSACTION_SCHEMA
            or not _lower_hex(payload.get("transaction_id"), 32)
            or payload.get("operation") not in {"install", "rollback"}
            or not _lower_hex(payload.get("target_sha"), 40)
            or payload.get("phase") not in {"prepared", "launching", "committed", "restored"}
            or not isinstance(payload.get("created_at"), str)
            or not isinstance(payload.get("snapshot"), dict)
        ):
            raise LocalInstallError("local install transaction journal bindings are invalid")
        return payload

    def _set_transaction_phase(self, transaction_id: str, phase: str) -> None:
        if phase not in {"launching", "committed", "restored"}:
            raise LocalInstallError("local install transaction phase is invalid")
        journal = self._read_transaction_journal()
        if journal.get("transaction_id") != transaction_id:
            raise LocalInstallError("local install transaction generation changed")
        journal["phase"] = phase
        _atomic_write_json(
            self.layout.active_transaction / "journal.json",
            journal,
            mode=0o600,
        )

    def _transaction_is_committed(self, transaction_id: str) -> bool:
        try:
            journal = self._read_transaction_journal()
        except LocalInstallError:
            return False
        return journal.get("transaction_id") == transaction_id and journal.get("phase") == "committed"

    def _snapshot_from_transaction(self, journal: Mapping[str, Any]) -> _InstallSnapshot:
        snapshot = journal.get("snapshot")
        expected_snapshot = {
            "current_sha", "previous_sha", "staged_sha", "service_loaded",
            "readiness_generation", "python_executable", "activation_nonce_digest", "files",
        }
        if not isinstance(snapshot, Mapping) or set(snapshot) != expected_snapshot:
            raise LocalInstallError("local install transaction snapshot fields are invalid")
        target_sha = journal.get("target_sha")
        if not isinstance(target_sha, str):
            raise LocalInstallError("local install transaction target is invalid")

        def release_for(value: Any) -> Path | None:
            if value is None:
                return None
            if not _lower_hex(value, 40):
                raise LocalInstallError("local install transaction release binding is invalid")
            release = self.layout.releases / str(value)
            self._verify_release(release, str(value))
            return release

        files = snapshot.get("files")
        expected_files = {
            "launch_agent", "manifest", "staged_manifest", "activation_nonce",
            "accepted_qualification", "acceptance_receipt",
        }
        if not isinstance(files, Mapping) or set(files) != expected_files:
            raise LocalInstallError("local install transaction file bindings are invalid")

        def blob(name: str) -> bytes | None:
            binding = files.get(name)
            if not isinstance(binding, Mapping) or set(binding) != {"present", "sha256", "blob"}:
                raise LocalInstallError("local install transaction blob binding is invalid")
            expected_blob = f"{name}.bin"
            if binding.get("blob") != expected_blob or not isinstance(binding.get("present"), bool):
                raise LocalInstallError("local install transaction blob name is invalid")
            present = bool(binding["present"])
            digest = binding.get("sha256")
            if not present:
                if digest is not None or os.path.lexists(self.layout.active_transaction / expected_blob):
                    raise LocalInstallError("local install transaction absent blob binding is invalid")
                return None
            if not _lower_hex(digest, 64):
                raise LocalInstallError("local install transaction blob digest is invalid")
            payload = _read_private_proof_file(
                self.layout.active_transaction / expected_blob,
                max_bytes=2_000_000,
            )
            if not hmac.compare_digest(hashlib.sha256(payload).hexdigest(), str(digest)):
                raise LocalInstallError("local install transaction blob digest changed")
            return payload

        service_loaded = snapshot.get("service_loaded")
        readiness_generation = snapshot.get("readiness_generation")
        python_executable = snapshot.get("python_executable")
        nonce_digest = snapshot.get("activation_nonce_digest")
        if not isinstance(service_loaded, bool):
            raise LocalInstallError("local install transaction service state is invalid")
        if readiness_generation is not None and not _positive_integer(readiness_generation):
            raise LocalInstallError("local install transaction readiness generation is invalid")
        if python_executable is not None and (
            not isinstance(python_executable, str) or not Path(python_executable).is_absolute()
        ):
            raise LocalInstallError("local install transaction executable binding is invalid")
        if nonce_digest is not None and not _lower_hex(nonce_digest, 64):
            raise LocalInstallError("local install transaction nonce binding is invalid")
        return _InstallSnapshot(
            target_sha=target_sha,
            current=release_for(snapshot.get("current_sha")),
            previous=release_for(snapshot.get("previous_sha")),
            staged=release_for(snapshot.get("staged_sha")),
            launch_agent=blob("launch_agent"),
            manifest=blob("manifest"),
            staged_manifest=blob("staged_manifest"),
            activation_nonce=blob("activation_nonce"),
            accepted_qualification=blob("accepted_qualification"),
            acceptance_receipt=blob("acceptance_receipt"),
            python_executable=python_executable,
            activation_nonce_digest=nonce_digest,
            service_loaded=service_loaded,
            readiness_generation=readiness_generation,
        )

    def _recover_interrupted_transaction(self) -> None:
        if os.path.lexists(self.layout.transaction_quarantine):
            raise LocalInstallError("local installer is quarantined; automatic mutation is disabled")
        for candidate in self.layout.transactions.glob(".prepare-*"):
            try:
                metadata = candidate.lstat()
            except OSError as exc:
                self._quarantine_failed_recovery("unsafe_prepare_marker")
                raise LocalInstallError("local installer recovery was quarantined") from exc
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                self._quarantine_failed_recovery("unsafe_prepare_marker")
                raise LocalInstallError("local installer recovery was quarantined")
            shutil.rmtree(candidate)
            _fsync_directory(self.layout.transactions)
        if not os.path.lexists(self.layout.active_transaction):
            return
        try:
            journal = self._read_transaction_journal()
            transaction_id = str(journal["transaction_id"])
            phase = journal["phase"]
            if phase == "committed":
                self._archive_transaction(transaction_id, outcome="COMMITTED")
                return
            if phase == "restored":
                self._archive_transaction(transaction_id, outcome="RESTORED")
                raise LocalInstallError(
                    "an interrupted local activation was restored; rerun the requested operation"
                )
            snapshot = self._snapshot_from_transaction(journal)
            self._restore_snapshot(snapshot)
            self._set_transaction_phase(transaction_id, "restored")
            self._archive_transaction(transaction_id, outcome="RESTORED")
        except LocalInstallError as exc:
            if "was restored; rerun" in str(exc):
                raise
            self._quarantine_failed_recovery("transaction_recovery_failed")
            raise LocalInstallError(
                "local installer recovery failed and v2 activation was quarantined"
            ) from exc
        raise LocalInstallError(
            "an interrupted local activation was restored; rerun the requested operation"
        )

    def _archive_transaction(self, transaction_id: str, *, outcome: str) -> None:
        if outcome not in {"COMMITTED", "RESTORED"}:
            raise LocalInstallError("local install transaction outcome is invalid")
        journal = self._read_transaction_journal()
        if journal.get("transaction_id") != transaction_id:
            raise LocalInstallError("local install transaction generation changed before receipt")
        expected_phase = outcome.lower()
        if journal.get("phase") != expected_phase:
            raise LocalInstallError("local install transaction phase does not match its receipt")
        result = {
            "schema": LOCAL_INSTALL_TRANSACTION_RESULT_SCHEMA,
            "transaction_id": transaction_id,
            "operation": journal["operation"],
            "target_sha": journal["target_sha"],
            "outcome": outcome,
            "journal_sha256": hashlib.sha256(
                (json.dumps(journal, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
            ).hexdigest(),
            "recorded_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        _atomic_write_json(self.layout.active_transaction / "result.json", result, mode=0o600)
        for name in (
            "launch_agent", "manifest", "staged_manifest", "activation_nonce",
            "accepted_qualification", "acceptance_receipt",
        ):
            blob_path = self.layout.active_transaction / f"{name}.bin"
            if blob_path.is_file() and not blob_path.is_symlink():
                blob_path.unlink()
            elif os.path.lexists(blob_path):
                raise LocalInstallError("local install transaction contains an unsafe snapshot blob")
        _fsync_directory(self.layout.active_transaction)
        destination = self.layout.transaction_receipts / f"{transaction_id}.{outcome.lower()}"
        if os.path.lexists(destination):
            raise LocalInstallError("local install transaction receipt already exists")
        os.replace(self.layout.active_transaction, destination)
        _fsync_directory(self.layout.transactions)
        _fsync_directory(self.layout.transaction_receipts)

    def _quarantine_failed_recovery(self, reason_code: str) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9_]{2,63}", reason_code):
            reason_code = "unsafe_recovery_failure"
        domain = f"gui/{os.getuid()}"
        self._command_runner(
            ["launchctl", "bootout", f"{domain}/{LAUNCHD_LABEL}"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            metadata = self.layout.launch_agent.lstat()
        except FileNotFoundError:
            metadata = None
        if metadata is not None:
            if stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
                disabled = self.layout.transactions / "quarantined-launch-agent.plist"
                if os.path.lexists(disabled):
                    raise LocalInstallError("local quarantine launch-agent destination already exists")
                os.replace(self.layout.launch_agent, disabled)
                _fsync_directory(self.layout.launch_agent.parent)
                _fsync_directory(self.layout.transactions)
            else:
                reason_code = "unsafe_launch_agent_shape"
        marker = {
            "schema": LOCAL_INSTALL_QUARANTINE_SCHEMA,
            "reason_code": reason_code,
            "mutation_enabled": False,
            "launchd_label": LAUNCHD_LABEL,
            "recorded_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        _atomic_write_json(self.layout.transaction_quarantine, marker, mode=0o600)
        if self._service_loaded():
            raise LocalInstallError("v2 service remained loaded after local installer quarantine")

    def _validate_qualification(
        self,
        manifest_path: Path | None,
        *,
        expected_sha: str,
        validation_now: datetime,
        source_root: Path | None = None,
    ) -> tuple[bytes, str, bool]:
        if manifest_path is None:
            raise LocalInstallError("activation requires a commit-bound qualification manifest")
        manifest = Path(os.path.abspath(manifest_path.expanduser()))
        qualification_root = Path(os.path.abspath(self.layout.qualifications))
        accepted_name = f"{expected_sha}.accepted.json"
        qualification_name = f"{expected_sha}.qualification.json"
        if manifest.parent != qualification_root or manifest.name not in {qualification_name, accepted_name}:
            raise LocalInstallError("qualification manifest must be a direct commit-bound runtime artifact")
        accepted = manifest.name == accepted_name
        raw = _read_private_proof_file(manifest, max_bytes=1_000_000)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise LocalInstallError("qualification manifest is invalid JSON") from exc
        base_fields = {
            "schema", "commit_sha", "created_at", "suite", "shadow", "app_server_canary", "staged_runtime"
        }
        remediation_requested = (
            isinstance(payload, Mapping) and "preactivation_remediation" in payload
        )
        causal_remediation_requested = (
            isinstance(payload, Mapping)
            and "preactivation_causal_remediation" in payload
        )
        recovery_receipt_raw = _read_optional_regular_file(
            self.layout.preactivation_recovery_receipt,
            max_bytes=1_000_000,
        )
        recovery_required = False
        remediation_required = False
        causal_remediation_required = False
        recovery_identity: Mapping[str, Any] | None = None
        if recovery_receipt_raw is not None:
            try:
                recovery_identity = json.loads(recovery_receipt_raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise LocalInstallError(
                    "preactivation recovery trust anchor is invalid JSON"
                ) from exc
            if (
                not isinstance(recovery_identity, Mapping)
                or recovery_identity.get("schema")
                != PREACTIVATION_RECOVERY_RECEIPT_SCHEMA
                or not _lower_hex(recovery_identity.get("replacement_sha"), 40)
            ):
                raise LocalInstallError(
                    "preactivation recovery trust anchor identity is invalid"
                )
            recovery_sha = str(recovery_identity["replacement_sha"])
            if (
                (remediation_requested or causal_remediation_requested)
                and recovery_sha
                != PREACTIVATION_STRUCTURAL_REPAIR_PREDECESSOR_SHA
            ):
                raise LocalInstallError(
                    "preactivation remediation root is not the exact merged PR91 release"
                )
            if recovery_sha == expected_sha:
                if remediation_requested or causal_remediation_requested:
                    raise LocalInstallError(
                        "the root preactivation replacement cannot claim descendant remediation"
                    )
                recovery_required = True
                raise LocalInstallError(
                    "the unaccepted PR91 recovery replacement cannot become a local activation anchor"
                )
            elif causal_remediation_requested:
                if not remediation_requested:
                    raise LocalInstallError(
                        "PR93 causal remediation must preserve the historical PR92 structural bridge"
                    )
                recovery_required = True
                remediation_required = True
                causal_remediation_required = True
                if expected_sha == PREACTIVATION_CAUSAL_REMEDIATION_PR92_MERGE_SHA:
                    raise LocalInstallError(
                        "the unaccepted PR92 structural bridge cannot become a local activation anchor"
                    )
                if not accepted:
                    self._assert_fresh_preactivation_remediation_boundary(
                        expected_sha=expected_sha,
                    )
                    if source_root is None:
                        raise LocalInstallError(
                            "fresh preactivation remediation requires the exact source checkout"
                        )
                    _verify_git_descendant(
                        Path(source_root),
                        ancestor_sha=PREACTIVATION_CAUSAL_REMEDIATION_PR92_MERGE_SHA,
                        descendant_sha=expected_sha,
                    )
            elif remediation_requested:
                raise LocalInstallError(
                    "the unaccepted PR92 structural bridge cannot become a local activation anchor"
                )
            else:
                self._validate_recovery_provenance_chain(
                    recovery_identity,
                    validation_now=validation_now,
                )
        elif remediation_requested or causal_remediation_requested:
            raise LocalInstallError(
                "preactivation remediation requires the immutable root recovery receipt"
            )
        expected_fields = base_fields | (
            {"preactivation_recovery"} if recovery_required else set()
        ) | ({"preactivation_remediation"} if remediation_required else set())
        expected_fields |= (
            {"preactivation_causal_remediation"}
            if causal_remediation_required
            else set()
        )
        if not isinstance(payload, Mapping) or set(payload) != expected_fields:
            raise LocalInstallError("qualification manifest fields are invalid")
        if payload.get("schema") != LOCAL_QUALIFICATION_SCHEMA or payload.get("commit_sha") != expected_sha:
            raise LocalInstallError("qualification manifest is stale or bound to another commit")
        created_at = _qualification_timestamp(payload.get("created_at"))
        if created_at > validation_now + timedelta(minutes=5):
            raise LocalInstallError("qualification manifest timestamp is in the future")
        if not accepted:
            if validation_now - created_at > LOCAL_QUALIFICATION_MAX_AGE:
                raise LocalInstallError("qualification manifest is not fresh enough for initial activation")
        else:
            self._validate_acceptance_receipt(
                expected_sha=expected_sha,
                qualification_payload=raw,
                validation_now=validation_now,
            )
        sections = {
            "suite": (0, {"real_model_calls"}),
            "shadow": (0, {"authoritative", "legacy_mutation_authority", "real_model_calls"}),
            "app_server_canary": (
                1,
                {
                    "binary", "transport", "websocket_used", "model", "reasoning",
                    "exact_thread_event_control", "contract_kind", "progress_percent",
                    "model_attempt_count", "model_call_count", "single_attempt_canary",
                    "real_model_calls",
                },
            ),
            "staged_runtime": (
                0,
                {
                    "private_socket", "single_writer", "final_attention_deferred",
                    "real_model_calls",
                },
            ),
        }
        if recovery_required:
            sections["preactivation_recovery"] = (
                0,
                {
                    "source_release_sha", "one_shot",
                    "active_task_registry_empty", "real_model_calls",
                },
            )
        if remediation_required:
            sections["preactivation_remediation"] = (
                0,
                {
                    "root_replacement_sha", "one_shot",
                    "structural_thread_start_only", "real_model_calls",
                },
            )
        if causal_remediation_required:
            sections["preactivation_causal_remediation"] = (
                1,
                {
                    "structural_bridge_sha",
                    "strategy_resource",
                    "prior_model_attempt_count",
                    "prior_completed_turn_count",
                    "prior_turn_receipt_count",
                    "prior_real_model_invocation_count",
                    "current_model_attempt_count",
                    "current_completed_turn_count",
                    "current_turn_receipt_count",
                    "current_real_model_invocation_count",
                    "cumulative_real_model_invocation_count",
                    "real_model_calls",
                },
            )
        common = {"status", "evidence_file", "evidence_sha256"}
        evidence_payloads: dict[str, bytes] = {}
        for name, (model_calls, extra) in sections.items():
            section = payload.get(name)
            if not isinstance(section, Mapping) or set(section) != common | extra or section.get("status") != "passed":
                raise LocalInstallError(f"qualification section {name} is incomplete")
            if section.get("real_model_calls") != model_calls:
                raise LocalInstallError(f"qualification section {name} has an invalid model-call budget")
            evidence_name = section.get("evidence_file")
            digest = section.get("evidence_sha256")
            if (
                not isinstance(evidence_name, str)
                or not evidence_name
                or Path(evidence_name).name != evidence_name
                or evidence_name == manifest.name
                or not isinstance(digest, str)
                or len(digest) != 64
                or any(character not in "0123456789abcdef" for character in digest)
            ):
                raise LocalInstallError(f"qualification section {name} evidence binding is invalid")
            evidence = _read_private_proof_file(qualification_root / evidence_name, max_bytes=2_000_000)
            if hashlib.sha256(evidence).hexdigest() != digest:
                raise LocalInstallError(f"qualification section {name} evidence digest changed")
            evidence_payloads[name] = evidence
        fresh = not accepted
        _validate_suite_qualification_evidence(
            evidence_payloads["suite"],
            expected_sha=expected_sha,
            qualification_created_at=created_at,
            validation_now=validation_now,
            require_fresh=fresh,
        )
        legacy_absence = _validate_shadow_qualification_evidence(
            evidence_payloads["shadow"],
            backups_root=self.layout.backups,
            qualification_created_at=created_at,
            validation_now=validation_now,
            require_fresh=fresh,
        )
        nonce = _read_private_proof_file(self.layout.activation_nonce, max_bytes=4_096)
        runtime_canary = _validate_runtime_qualification_evidence(
            evidence_payloads["app_server_canary"],
            expected_sha=expected_sha,
            expected_release=self.layout.releases / expected_sha,
            expected_nonce_sha256=hashlib.sha256(nonce).hexdigest() if fresh else None,
            qualification_created_at=created_at,
            validation_now=validation_now,
            require_fresh=fresh,
            label="App Server canary",
        )
        runtime_staged = _validate_runtime_qualification_evidence(
            evidence_payloads["staged_runtime"],
            expected_sha=expected_sha,
            expected_release=self.layout.releases / expected_sha,
            expected_nonce_sha256=hashlib.sha256(nonce).hexdigest() if fresh else None,
            qualification_created_at=created_at,
            validation_now=validation_now,
            require_fresh=fresh,
            label="staged runtime",
        )
        if _runtime_qualification_binding(runtime_canary) != _runtime_qualification_binding(runtime_staged):
            raise LocalInstallError("qualification runtime evidence observations do not bind the same pilot")
        runtime_causal_summary = runtime_canary.get("causal_remediation")
        if causal_remediation_required and not isinstance(
            runtime_causal_summary, Mapping
        ):
            raise LocalInstallError(
                "PR93 runtime evidence is missing its causal remediation summary"
            )
        if not causal_remediation_required and runtime_causal_summary is not None:
            raise LocalInstallError(
                "ordinary runtime evidence must not carry bootstrap causal remediation"
            )
        if recovery_required:
            _validate_preactivation_recovery_qualification_evidence(
                evidence_payloads["preactivation_recovery"],
                expected_replacement_sha=str(recovery_identity["replacement_sha"]),
                runtime_root=self.layout.root,
                expected_supervisor_generation=int(
                    runtime_canary["staged_runtime"]["supervisor_generation"]
                ),
                qualification_created_at=created_at,
                validation_now=validation_now,
                require_fresh=fresh and not remediation_required,
                require_immediate_successor=not remediation_required,
            )
            recovery_section = payload["preactivation_recovery"]
            if (
                recovery_section.get("source_release_sha")
                != PREACTIVATION_SOURCE_RELEASE_SHA
                or recovery_section.get("one_shot") is not True
                or recovery_section.get("active_task_registry_empty") is not True
            ):
                raise LocalInstallError(
                    "qualification preactivation recovery proof is incomplete"
                )
        if remediation_required:
            remediation_section = payload["preactivation_remediation"]
            recovery_sha = str(recovery_identity["replacement_sha"])
            if (
                remediation_section.get("root_replacement_sha") != recovery_sha
                or remediation_section.get("one_shot") is not True
                or remediation_section.get("structural_thread_start_only") is not True
            ):
                raise LocalInstallError(
                    "qualification preactivation remediation proof is incomplete"
                )
            _validate_preactivation_remediation_qualification_evidence(
                evidence_payloads["preactivation_remediation"],
                expected_sha=PREACTIVATION_CAUSAL_REMEDIATION_PR92_MERGE_SHA,
                expected_root_replacement_sha=recovery_sha,
                runtime_root=self.layout.root,
                expected_supervisor_generation=(
                    PREACTIVATION_CAUSAL_REMEDIATION_EXPECTED_OUTPUT_GENERATION
                ),
                qualification_created_at=created_at,
                validation_now=validation_now,
                require_fresh=False,
                boundary_recheck=None,
            )
        if causal_remediation_required:
            causal_section = payload["preactivation_causal_remediation"]
            if (
                causal_section.get("structural_bridge_sha")
                != PREACTIVATION_CAUSAL_REMEDIATION_PR92_MERGE_SHA
                or causal_section.get("strategy_resource")
                != PREACTIVATION_CAUSAL_REMEDIATION_STRATEGY_RESOURCE
                or causal_section.get("prior_model_attempt_count") != 1
                or causal_section.get("prior_completed_turn_count") != 1
                or causal_section.get("prior_turn_receipt_count") != 0
                or causal_section.get("prior_real_model_invocation_count") != 1
                or causal_section.get("current_model_attempt_count") != 1
                or causal_section.get("current_completed_turn_count") != 1
                or causal_section.get("current_turn_receipt_count") != 1
                or causal_section.get("current_real_model_invocation_count") != 1
                or causal_section.get("cumulative_real_model_invocation_count") != 2
            ):
                raise LocalInstallError(
                    "qualification preactivation causal remediation counters are invalid"
                )
            _validate_preactivation_causal_remediation_qualification_evidence(
                evidence_payloads["preactivation_causal_remediation"],
                expected_sha=expected_sha,
                expected_root_replacement_sha=recovery_sha,
                expected_structural_bridge_sha=(
                    PREACTIVATION_CAUSAL_REMEDIATION_PR92_MERGE_SHA
                ),
                runtime_root=self.layout.root,
                expected_canary=runtime_canary["app_server_canary"],
                expected_runtime_causal_summary=runtime_causal_summary,
                qualification_created_at=created_at,
                validation_now=validation_now,
                require_fresh=fresh,
                boundary_recheck=(
                    self._assert_preactivation_service_absent if fresh else None
                ),
            )
            if accepted:
                anchors = self._signed_preactivation_causal_anchors(
                    validation_now=validation_now,
                )
                if tuple(item[0] for item in anchors) != (expected_sha,):
                    raise LocalInstallError(
                        "accepted PR93 causal remediation is not the unique signed anchor"
                    )
                current = self._release_link_target(self.layout.current)
                if current is not None and current.name != expected_sha:
                    current_sha = current.name
                    if current.parent != self.layout.releases or not _lower_hex(
                        current_sha, 40
                    ):
                        raise LocalInstallError(
                            "installed release identity is invalid"
                        )
                    current_payload = _read_private_proof_file(
                        self.layout.qualifications
                        / f"{current_sha}.accepted.json",
                        max_bytes=1_000_000,
                    )
                    self._validate_acceptance_receipt(
                        expected_sha=current_sha,
                        qualification_payload=current_payload,
                        validation_now=validation_now,
                    )
        shadow = payload["shadow"]
        if shadow.get("authoritative") is not False or shadow.get("legacy_mutation_authority") != "stopped":
            raise LocalInstallError("qualification shadow did not prove legacy authority stopped")
        canary = payload["app_server_canary"]
        if (
            canary.get("binary") != DESKTOP_CODEX_BINARY
            or canary.get("transport") != "stdio"
            or canary.get("websocket_used") is not False
            or canary.get("model") != "gpt-5.6-sol"
            or canary.get("reasoning") != "ultra"
            or canary.get("exact_thread_event_control") is not True
            or canary.get("contract_kind") != "checkpoint"
            or not _checkpoint_progress(canary.get("progress_percent"))
            or canary.get("model_attempt_count") != 1
            or canary.get("model_call_count") != 1
            or canary.get("single_attempt_canary") is not True
        ):
            raise LocalInstallError("qualification App Server canary did not prove the exact supported surface")
        staged = payload["staged_runtime"]
        if any(
            staged.get(field) is not True
            for field in ("private_socket", "single_writer", "final_attention_deferred")
        ):
            raise LocalInstallError("qualification staged runtime proof is incomplete")
        if causal_remediation_required and fresh:
            self._assert_fresh_preactivation_remediation_boundary(
                expected_sha=expected_sha,
            )
        return raw, hashlib.sha256(raw).hexdigest(), legacy_absence

    def _assert_fresh_preactivation_remediation_boundary(
        self,
        *,
        expected_sha: str,
    ) -> None:
        if any(
            os.path.lexists(path)
            for path in (
                self.layout.current,
                self.layout.previous,
                self.layout.manifest,
                self.layout.launch_agent,
                self.layout.active_transaction,
                self.layout.transaction_quarantine,
            )
        ):
            raise LocalInstallError(
                "preactivation remediation requires the untouched first-activation boundary"
            )
        if tuple(self.layout.qualifications.glob("*.acceptance-receipt.json")) or tuple(
            self.layout.qualifications.glob("*.accepted.json")
        ):
            raise LocalInstallError(
                "preactivation remediation is forbidden after an activation acceptance"
            )
        release = self.layout.releases / expected_sha
        staged = self._release_link_target(self.layout.staged)
        if staged != release:
            raise LocalInstallError(
                "preactivation remediation candidate is not the exact staged release"
            )
        staged_manifest = _read_json(self.layout.staged_manifest)
        if staged_manifest != {
            "schema": "dev-control-plane/local-staged-release/v2",
            "operation": "install",
            "commit_sha": expected_sha,
            "release_dir": str(release),
        }:
            raise LocalInstallError(
                "preactivation remediation staged manifest binding is invalid"
            )
        self._assert_preactivation_service_absent()

    def _signed_preactivation_causal_anchors(
        self,
        *,
        validation_now: datetime,
    ) -> tuple[tuple[str, Path], ...]:
        anchors: list[tuple[str, Path]] = []
        suffix = ".accepted.json"
        for path in sorted(self.layout.qualifications.glob(f"*{suffix}")):
            name = path.name
            sha = name[: -len(suffix)]
            if not _lower_hex(sha, 40):
                raise LocalInstallError(
                    "accepted qualification has an invalid commit-bound filename"
                )
            raw = _read_private_proof_file(path, max_bytes=1_000_000)
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise LocalInstallError(
                    "accepted qualification is invalid JSON"
                ) from exc
            if not isinstance(payload, Mapping):
                raise LocalInstallError("accepted qualification is not an object")
            bootstrap_sections = {
                "preactivation_recovery",
                "preactivation_remediation",
                "preactivation_causal_remediation",
            } & set(payload)
            if not bootstrap_sections:
                continue
            if bootstrap_sections != {
                "preactivation_recovery",
                "preactivation_remediation",
                "preactivation_causal_remediation",
            }:
                raise LocalInstallError(
                    "accepted PR91 or PR92 bootstrap qualification is forbidden"
                )
            self._validate_acceptance_receipt(
                expected_sha=sha,
                qualification_payload=raw,
                validation_now=validation_now,
            )
            anchors.append((sha, path))
        if len(anchors) > 1:
            raise LocalInstallError(
                "multiple signed PR93 causal remediation anchors are forbidden"
            )
        return tuple(anchors)

    def _validate_recovery_provenance_chain(
        self,
        recovery_identity: Mapping[str, Any],
        *,
        validation_now: datetime,
    ) -> None:
        recovery_sha = str(recovery_identity["replacement_sha"])
        verify_preactivation_recovery_receipt(
            self.layout.preactivation_recovery_receipt,
            expected_replacement_sha=recovery_sha,
            runtime_root=self.layout.root,
            require_pristine=False,
            require_empty_projection=False,
        )
        anchors = self._signed_preactivation_causal_anchors(
            validation_now=validation_now,
        )
        if len(anchors) != 1:
            raise LocalInstallError(
                "post-recovery update requires the unique signed PR93 causal anchor"
            )
        anchor_sha, anchor_path = anchors[0]
        if anchor_sha in {
            recovery_sha,
            PREACTIVATION_CAUSAL_REMEDIATION_PR92_MERGE_SHA,
        }:
            raise LocalInstallError(
                "PR93 causal anchor must be distinct from unaccepted PR91 and PR92"
            )
        self._validate_qualification(
            anchor_path,
            expected_sha=anchor_sha,
            validation_now=validation_now,
        )
        trusted_sha = anchor_sha
        current = self._release_link_target(self.layout.current)
        if current is None or current.parent != self.layout.releases:
            raise LocalInstallError(
                "post-recovery update requires an accepted installed release"
            )
        current_sha = current.name
        if not _lower_hex(current_sha, 40):
            raise LocalInstallError("installed release identity is invalid")
        if current_sha != trusted_sha:
            current_payload = _read_private_proof_file(
                self.layout.qualifications / f"{current_sha}.accepted.json",
                max_bytes=1_000_000,
            )
            self._validate_acceptance_receipt(
                expected_sha=current_sha,
                qualification_payload=current_payload,
                validation_now=validation_now,
            )

    def _accept_qualification(
        self,
        sha: str,
        payload: bytes,
        *,
        release: Path,
        supervisor_generation: int,
        activation_nonce_sha256: str,
    ) -> None:
        _atomic_write_bytes(
            self.layout.qualifications / f"{sha}.accepted.json",
            payload,
            mode=0o600,
        )
        receipt = {
            "schema": LOCAL_ACCEPTANCE_SCHEMA,
            "commit_sha": sha,
            "qualification_sha256": hashlib.sha256(payload).hexdigest(),
            "release_manifest_sha256": _release_manifest_digest(release),
            "supervisor_generation": supervisor_generation,
            "activation_nonce_sha256": activation_nonce_sha256,
            "accepted_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        receipt["hmac_sha256"] = hmac.new(
            self._install_acceptance_key_material(),
            _canonical_receipt_bytes(receipt),
            hashlib.sha256,
        ).hexdigest()
        _atomic_write_json(
            self._acceptance_receipt_path(sha),
            receipt,
            mode=0o600,
        )

    def _acceptance_receipt_path(self, sha: str) -> Path:
        return self.layout.qualifications / f"{sha}.acceptance-receipt.json"

    def _validate_acceptance_receipt(
        self,
        *,
        expected_sha: str,
        qualification_payload: bytes,
        validation_now: datetime,
    ) -> None:
        try:
            raw = _read_private_proof_file(
                self._acceptance_receipt_path(expected_sha),
                max_bytes=64 * 1024,
            )
        except LocalInstallError as exc:
            raise LocalInstallError(
                "fresh activation requires .qualification.json; historical .accepted.json requires a valid receipt"
            ) from exc
        try:
            receipt = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise LocalInstallError("activation acceptance receipt is invalid JSON") from exc
        expected_fields = {
            "schema", "commit_sha", "qualification_sha256", "release_manifest_sha256",
            "supervisor_generation", "activation_nonce_sha256", "accepted_at", "hmac_sha256",
        }
        if not isinstance(receipt, Mapping) or set(receipt) != expected_fields:
            raise LocalInstallError("activation acceptance receipt fields are invalid")
        signature = receipt.get("hmac_sha256")
        unsigned = {key: value for key, value in receipt.items() if key != "hmac_sha256"}
        expected_signature = hmac.new(
            self._install_acceptance_key_material(),
            _canonical_receipt_bytes(unsigned),
            hashlib.sha256,
        ).hexdigest()
        accepted_at = _qualification_timestamp(receipt.get("accepted_at"))
        if (
            receipt.get("schema") != LOCAL_ACCEPTANCE_SCHEMA
            or receipt.get("commit_sha") != expected_sha
            or receipt.get("qualification_sha256") != hashlib.sha256(qualification_payload).hexdigest()
            or receipt.get("release_manifest_sha256")
            != _release_manifest_digest(self.layout.releases / expected_sha)
            or not _positive_integer(receipt.get("supervisor_generation"))
            or not _lower_hex(receipt.get("activation_nonce_sha256"), 64)
            or accepted_at > validation_now + timedelta(minutes=5)
            or not _lower_hex(signature, 64)
            or not hmac.compare_digest(str(signature), expected_signature)
        ):
            raise LocalInstallError("activation acceptance receipt signature or binding is invalid")

    def _install_acceptance_key_material(self) -> bytes:
        _validate_projection_key(self.layout.install_acceptance_key)
        return _read_private_key_file(self.layout.install_acceptance_key)

    def _copy_release(self, source: Path, release: Path, sha: str) -> None:
        staging = Path(tempfile.mkdtemp(prefix=f".{sha}.", dir=self.layout.releases))
        try:
            entries = _git_release_entries(source, sha)
            if not entries:
                raise LocalInstallError("verified Git release contains no packaged files")
            for relative, blob_sha, executable in entries:
                destination = staging.joinpath(*PurePosixPath(relative).parts)
                destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                blob = _git_blob(source, blob_sha)
                descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o700 if executable else 0o600)
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(blob)
                    handle.flush()
                    os.fsync(handle.fileno())
            digest = _release_digest(staging)
            _atomic_write_json(
                staging / "release.json",
                {
                    "schema": "dev-control-plane/local-release/v2",
                    "commit_sha": sha,
                    "git_tree_sha": _git(source, "rev-parse", f"{sha}^{{tree}}").strip(),
                    "entries": [
                        {"path": relative, "blob_sha": blob_sha, "executable": executable}
                        for relative, blob_sha, executable in entries
                    ],
                    "tree_digest": digest,
                },
                mode=0o600,
            )
            _seal_release_tree(staging, entries=entries)
            os.replace(staging, release)
            _fsync_directory(self.layout.releases)
        finally:
            if staging.exists():
                _make_tree_owner_writable(staging)
                shutil.rmtree(staging)

    def _ensure_projection_key(self) -> None:
        try:
            self.layout.projection_key.lstat()
        except FileNotFoundError:
            pass
        else:
            _validate_projection_key(self.layout.projection_key)
            return
        # Textual hex avoids newline trimming ambiguity across local/hosted key loaders.
        _atomic_write_bytes(self.layout.projection_key, secrets.token_hex(32).encode("ascii"), mode=0o600)
        _validate_projection_key(self.layout.projection_key)

    def _projection_key_is_safe(self) -> bool:
        try:
            _validate_projection_key(self.layout.projection_key)
        except LocalInstallError:
            return False
        return True

    def _ensure_owner_acceptance_key(self) -> None:
        try:
            self.layout.owner_acceptance_key.lstat()
        except FileNotFoundError:
            pass
        else:
            _validate_projection_key(self.layout.owner_acceptance_key)
            return
        # Independent from projection ingestion: the stateless exact-chat
        # delivery bridge receives only this restricted receipt key.
        _atomic_write_bytes(
            self.layout.owner_acceptance_key,
            secrets.token_hex(32).encode("ascii"),
            mode=0o600,
        )
        _validate_projection_key(self.layout.owner_acceptance_key)

    def _ensure_install_acceptance_key(self) -> None:
        try:
            self.layout.install_acceptance_key.lstat()
        except FileNotFoundError:
            pass
        else:
            _validate_projection_key(self.layout.install_acceptance_key)
            return
        _atomic_write_bytes(
            self.layout.install_acceptance_key,
            secrets.token_hex(32).encode("ascii"),
            mode=0o600,
        )
        _validate_projection_key(self.layout.install_acceptance_key)

    def _ensure_activation_nonce(self) -> None:
        try:
            self.layout.activation_nonce.lstat()
        except FileNotFoundError:
            pass
        else:
            _validate_projection_key(self.layout.activation_nonce)
            return
        self._rotate_activation_nonce()

    def _rotate_activation_nonce(self) -> str:
        material = secrets.token_hex(32).encode("ascii")
        _atomic_write_bytes(self.layout.activation_nonce, material, mode=0o600)
        _validate_projection_key(self.layout.activation_nonce)
        return hashlib.sha256(material).hexdigest()

    def _verify_release(self, release: Path, sha: str, *, source: Path | None = None) -> None:
        _validate_release_directory(release, self.layout.releases, expected_sha=sha)
        _verify_release_manifest(release, sha)
        if source is not None:
            _verify_release_against_git(release, source=source, sha=sha)

    def _release_link_target(self, link: Path) -> Path | None:
        target = _symlink_target(link)
        if target is None:
            return None
        _validate_release_directory(target, self.layout.releases, expected_sha=target.name)
        return target

    def _capture_snapshot(self, *, target_sha: str) -> _InstallSnapshot:
        if not _lower_hex(target_sha, 40):
            raise LocalInstallError("local activation snapshot target is invalid")
        loaded = self._service_loaded()
        readiness = self._readiness_probe() if loaded else None
        generation = _readiness_generation(readiness)
        activation = readiness.get("activation_identity") if isinstance(readiness, Mapping) else None
        nonce = _read_optional_regular_file(self.layout.activation_nonce, max_bytes=4_096)
        if loaded:
            _validate_projection_key(self.layout.activation_nonce)
            if (
                nonce is None
                or not isinstance(activation, Mapping)
                or activation.get("activation_nonce_sha256") != hashlib.sha256(nonce).hexdigest()
                or generation is None
            ):
                raise LocalInstallError("loaded v2 service activation nonce is not recoverably attested")
        return _InstallSnapshot(
            target_sha=target_sha,
            current=self._release_link_target(self.layout.current),
            previous=self._release_link_target(self.layout.previous),
            staged=self._release_link_target(self.layout.staged),
            launch_agent=_read_optional_regular_file(self.layout.launch_agent, max_bytes=1_000_000),
            manifest=_read_optional_regular_file(self.layout.manifest, max_bytes=1_000_000),
            staged_manifest=_read_optional_regular_file(
                self.layout.staged_manifest,
                max_bytes=1_000_000,
            ),
            activation_nonce=nonce,
            accepted_qualification=_read_optional_regular_file(
                self.layout.qualifications / f"{target_sha}.accepted.json",
                max_bytes=1_000_000,
            ),
            acceptance_receipt=_read_optional_regular_file(
                self._acceptance_receipt_path(target_sha),
                max_bytes=64 * 1024,
            ),
            python_executable=(
                str(activation.get("python_executable"))
                if isinstance(activation, Mapping) and isinstance(activation.get("python_executable"), str)
                else None
            ),
            activation_nonce_digest=(
                str(activation.get("activation_nonce_sha256"))
                if isinstance(activation, Mapping) and isinstance(activation.get("activation_nonce_sha256"), str)
                else None
            ),
            service_loaded=loaded,
            readiness_generation=generation,
        )

    def _activate_launchd(
        self,
        *,
        expected_release: Path,
        previous_generation: int | None,
        expected_python: Path,
        expected_nonce_digest: str,
        require_legacy_artifact_absence: bool,
    ) -> Mapping[str, Any]:
        if self._legacy_launchd_probe(LEGACY_MONITOR_LABEL) is not True:
            raise LocalInstallError("exact legacy launchd label is still loaded immediately before activation")
        if require_legacy_artifact_absence and self._legacy_artifact_probe() is not True:
            raise LocalInstallError("legacy artifacts appeared after their exact absence proof")
        domain = f"gui/{os.getuid()}"
        self._command_runner(
            ["launchctl", "bootout", domain, str(self.layout.launch_agent)],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        completed = self._command_runner(
            ["launchctl", "bootstrap", domain, str(self.layout.launch_agent)],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise LocalInstallError(f"launchd bootstrap failed with exit {completed.returncode}")
        self._kickstart_launchd()
        activation = self._wait_for_readiness(
            expected_release,
            previous_generation=previous_generation,
            expected_python=expected_python,
            expected_nonce_digest=expected_nonce_digest,
        )
        if self._legacy_launchd_probe(LEGACY_MONITOR_LABEL) is not True:
            raise LocalInstallError("legacy launchd label reappeared during v2 activation")
        if require_legacy_artifact_absence and self._legacy_artifact_probe() is not True:
            raise LocalInstallError("legacy artifacts appeared during v2 activation")
        return activation

    def _kickstart_launchd(self) -> None:
        completed = self._command_runner(
            ["launchctl", "kickstart", "-k", f"gui/{os.getuid()}/{LAUNCHD_LABEL}"],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise LocalInstallError(f"launchd kickstart failed with exit {completed.returncode}")

    def _service_loaded(self) -> bool:
        completed = self._command_runner(
            ["launchctl", "print", f"gui/{os.getuid()}/{LAUNCHD_LABEL}"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if completed.returncode == 0:
            return True
        if completed.returncode == 113:
            return False
        raise LocalInstallError(
            f"launchd service state could not be proven (exit {completed.returncode})"
        )

    def _service_pid(self) -> int | None:
        completed = self._command_runner(
            ["launchctl", "print", f"gui/{os.getuid()}/{LAUNCHD_LABEL}"],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            return None
        for line in completed.stdout.splitlines():
            match = re.fullmatch(r"\s*pid\s*=\s*([1-9][0-9]*)\s*", line)
            if match:
                return int(match.group(1))
        return None

    def _wait_for_readiness(
        self,
        expected_release: Path,
        *,
        previous_generation: int | None,
        expected_python: Path,
        expected_nonce_digest: str,
    ) -> Mapping[str, Any]:
        deadline = self._monotonic_fn() + self._activation_timeout_seconds
        expected_entrypoint = expected_release / "apps" / "dev_control_plane_supervisor_v2.py"
        while True:
            active_release = self._release_link_target(self.layout.current)
            payload = self._readiness_probe()
            generation = _readiness_generation(payload)
            generation_advanced = previous_generation is None or (
                generation is not None and generation > previous_generation
            )
            activation = payload.get("activation_identity") if isinstance(payload, Mapping) else None
            launchd_pid = self._service_pid()
            activation_matches = (
                isinstance(activation, Mapping)
                and set(activation) == {
                    "schema", "release_sha", "activation_nonce_sha256", "pid", "python_executable",
                    "entrypoint", "bind_host", "bind_port", "supervisor_generation", "supervisor_owner_id",
                }
                and activation.get("schema") == "dev-control-plane/runtime-activation/v2"
                and activation.get("release_sha") == expected_release.name
                and activation.get("activation_nonce_sha256") == expected_nonce_digest
                and activation.get("python_executable") == str(expected_python.resolve())
                and activation.get("entrypoint") == str(expected_entrypoint.resolve())
                and activation.get("bind_host") == "127.0.0.1"
                and activation.get("bind_port") == DEFAULT_PORT
                and activation.get("supervisor_generation") == generation
                and isinstance(activation.get("supervisor_owner_id"), str)
                and bool(activation.get("supervisor_owner_id"))
                and isinstance(activation.get("pid"), int)
                and not isinstance(activation.get("pid"), bool)
                and activation.get("pid") == launchd_pid
            )
            process_matches = bool(
                activation_matches
                and launchd_pid is not None
                and self._process_identity_probe(
                    launchd_pid,
                    expected_python.resolve(),
                    expected_entrypoint.resolve(),
                    "127.0.0.1",
                    DEFAULT_PORT,
                )
            )
            if (
                active_release == expected_release
                and payload is not None
                and payload.get("ready") is True
                and payload.get("service_role") == "local_supervisor_v2"
                and payload.get("single_writer") is True
                and generation is not None
                and generation_advanced
                and self._service_loaded()
                and activation_matches
                and process_matches
            ):
                if not isinstance(activation, Mapping):
                    raise LocalInstallError("readiness activation identity disappeared during validation")
                return dict(activation)
            if self._monotonic_fn() >= deadline:
                raise LocalInstallError("launchd activation did not prove a fresh single-writer readiness generation")
            self._sleep_fn(ACTIVATION_POLL_SECONDS)

    def _restore_snapshot(self, snapshot: _InstallSnapshot) -> None:
        domain = f"gui/{os.getuid()}"
        self._command_runner(
            ["launchctl", "bootout", f"{domain}/{LAUNCHD_LABEL}"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if self._service_loaded():
            raise LocalInstallError("automatic rollback could not fence the failed v2 activation")
        _restore_release_link(self.layout.current, snapshot.current)
        _restore_release_link(self.layout.previous, snapshot.previous)
        _restore_release_link(self.layout.staged, snapshot.staged)
        _restore_optional_regular_file(self.layout.launch_agent, snapshot.launch_agent, mode=0o600)
        _restore_optional_regular_file(self.layout.manifest, snapshot.manifest, mode=0o600)
        _restore_optional_regular_file(
            self.layout.staged_manifest,
            snapshot.staged_manifest,
            mode=0o600,
        )
        _restore_optional_regular_file(
            self.layout.activation_nonce,
            snapshot.activation_nonce,
            mode=0o600,
        )
        _restore_optional_regular_file(
            self.layout.qualifications / f"{snapshot.target_sha}.accepted.json",
            snapshot.accepted_qualification,
            mode=0o600,
        )
        _restore_optional_regular_file(
            self._acceptance_receipt_path(snapshot.target_sha),
            snapshot.acceptance_receipt,
            mode=0o600,
        )
        if snapshot.service_loaded:
            if (
                snapshot.current is None
                or snapshot.launch_agent is None
                or snapshot.activation_nonce is None
                or snapshot.python_executable is None
                or snapshot.activation_nonce_digest is None
            ):
                raise LocalInstallError("previous launchd state lacks a recoverable release or plist")
            completed = self._command_runner(
                ["launchctl", "bootstrap", domain, str(self.layout.launch_agent)],
                check=False,
                capture_output=True,
                text=True,
            )
            if completed.returncode != 0:
                raise LocalInstallError("automatic rollback could not bootstrap the previous service")
            self._kickstart_launchd()
            self._wait_for_readiness(
                snapshot.current,
                previous_generation=snapshot.readiness_generation,
                expected_python=Path(snapshot.python_executable),
                expected_nonce_digest=snapshot.activation_nonce_digest,
            )
        self._verify_restored_snapshot(snapshot)

    def _verify_restored_snapshot(self, snapshot: _InstallSnapshot) -> None:
        if self._release_link_target(self.layout.current) != snapshot.current:
            raise LocalInstallError("restored current release does not match the durable snapshot")
        if self._release_link_target(self.layout.previous) != snapshot.previous:
            raise LocalInstallError("restored previous release does not match the durable snapshot")
        if self._release_link_target(self.layout.staged) != snapshot.staged:
            raise LocalInstallError("restored staged release does not match the durable snapshot")
        exact_files = (
            (self.layout.launch_agent, snapshot.launch_agent, 1_000_000),
            (self.layout.manifest, snapshot.manifest, 1_000_000),
            (self.layout.staged_manifest, snapshot.staged_manifest, 1_000_000),
            (self.layout.activation_nonce, snapshot.activation_nonce, 4_096),
            (
                self.layout.qualifications / f"{snapshot.target_sha}.accepted.json",
                snapshot.accepted_qualification,
                1_000_000,
            ),
            (self._acceptance_receipt_path(snapshot.target_sha), snapshot.acceptance_receipt, 64 * 1024),
        )
        for path, expected, max_bytes in exact_files:
            if _read_optional_regular_file(path, max_bytes=max_bytes) != expected:
                raise LocalInstallError("restored local activation metadata differs from its durable snapshot")
        if self._service_loaded() is not snapshot.service_loaded:
            raise LocalInstallError("restored launchd state differs from its durable snapshot")

    def _rollback_failed_activation(
        self,
        snapshot: _InstallSnapshot,
        *,
        transaction_id: str,
        activation_error: Exception,
    ) -> None:
        try:
            self._restore_snapshot(snapshot)
            self._set_transaction_phase(transaction_id, "restored")
            self._archive_transaction(transaction_id, outcome="RESTORED")
        except Exception as rollback_error:
            try:
                self._quarantine_failed_recovery("activation_rollback_failed")
            except Exception as quarantine_error:
                raise LocalInstallError(
                    "launchd activation failed; rollback and quarantine could not be proven"
                ) from quarantine_error
            raise LocalInstallError(
                "launchd activation failed; recovery was quarantined with v2 mutation disabled"
            ) from rollback_error
        raise LocalInstallError("launchd activation failed; previous release and service were restored") from activation_error


def result_to_dict(
    result: LocalInstallResult | PreActivationRecoveryResult,
) -> dict[str, Any]:
    return asdict(result)


def _canonical_receipt_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(payload),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _release_manifest_digest(release: Path) -> str:
    path = release / "release.json"
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise LocalInstallError("sealed release manifest is unavailable") from exc
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) != 0o444
        or metadata.st_nlink != 1
        or metadata.st_size > 2_000_000
    ):
        raise LocalInstallError("sealed release manifest permissions or shape are unsafe")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        try:
            opened = os.fstat(descriptor)
            payload = os.read(descriptor, 2_000_001)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise LocalInstallError("sealed release manifest could not be read safely") from exc
    try:
        repeated = path.lstat()
    except OSError as exc:
        raise LocalInstallError("sealed release manifest changed during secure read") from exc
    if (
        (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
            opened.st_uid,
            stat.S_IMODE(opened.st_mode),
            opened.st_nlink,
        )
        != (metadata.st_dev, metadata.st_ino, metadata.st_size, metadata.st_uid, 0o444, 1)
        or (
            repeated.st_dev,
            repeated.st_ino,
            repeated.st_size,
            repeated.st_uid,
            stat.S_IMODE(repeated.st_mode),
            repeated.st_nlink,
        )
        != (metadata.st_dev, metadata.st_ino, metadata.st_size, metadata.st_uid, 0o444, 1)
        or len(payload) != metadata.st_size
        or len(payload) > 2_000_000
    ):
        raise LocalInstallError("sealed release manifest changed during secure read")
    return hashlib.sha256(payload).hexdigest()


def _source_gate(source: Path, *, expected_sha: str | None, require_origin_main: bool) -> str:
    if not (source / ".git").exists() and not _is_git_worktree(source):
        raise LocalInstallError("source is not a Git checkout")
    status = _git(source, "status", "--porcelain")
    if status.strip():
        raise LocalInstallError("source working tree is not clean")
    sha = _git(source, "rev-parse", "HEAD").strip()
    if len(sha) != 40 or any(char not in "0123456789abcdef" for char in sha):
        raise LocalInstallError("source HEAD is not a full Git SHA")
    if expected_sha and sha != expected_sha:
        raise LocalInstallError("source HEAD does not match expected merged SHA")
    if require_origin_main:
        origin = _git(source, "config", "--get", "remote.origin.url").strip()
        canonical_origin = "https://github.com/orenvlad-ai/dev-control-plane.git"
        if origin != canonical_origin:
            raise LocalInstallError("source origin is not orenvlad-ai/dev-control-plane")
        rewrites = _git_optional(source, "config", "--show-origin", "--get-regexp", r"^url\..*\.insteadof$")
        if rewrites.strip():
            raise LocalInstallError("Git URL rewrite configuration is forbidden for production source attestation")
        _git(
            source,
            "fetch",
            "--quiet",
            "--no-tags",
            canonical_origin,
            "+refs/heads/main:refs/remotes/origin/main",
        )
        origin_main = _git(source, "rev-parse", "origin/main").strip()
        if sha != origin_main:
            raise LocalInstallError("source HEAD is not exact origin/main")
    return sha


def _is_git_worktree(source: Path) -> bool:
    marker = source / ".git"
    return marker.is_file()


def _git(source: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=source,
        check=False,
        capture_output=True,
        text=True,
        env=_isolated_git_environment(),
        timeout=30,
    )
    if completed.returncode != 0:
        raise LocalInstallError(f"Git source gate failed: {' '.join(arguments)}")
    return completed.stdout


def _git_optional(source: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=source,
        check=False,
        capture_output=True,
        text=True,
        env=_isolated_git_environment(),
        timeout=30,
    )
    if completed.returncode not in {0, 1}:
        raise LocalInstallError(f"Git source gate failed: {' '.join(arguments)}")
    return completed.stdout


def _verify_git_descendant(
    source: Path,
    *,
    ancestor_sha: str,
    descendant_sha: str,
) -> None:
    if (
        not _lower_hex(ancestor_sha, 40)
        or not _lower_hex(descendant_sha, 40)
        or ancestor_sha == descendant_sha
    ):
        raise LocalInstallError(
            "preactivation remediation requires a distinct full-SHA descendant"
        )
    observed = _git(source, "rev-parse", "HEAD").strip()
    if observed != descendant_sha:
        raise LocalInstallError(
            "preactivation remediation source is not the exact candidate SHA"
        )
    completed = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor_sha, descendant_sha],
        cwd=source,
        check=False,
        capture_output=True,
        text=True,
        env=_isolated_git_environment(),
        timeout=30,
    )
    if completed.returncode != 0:
        raise LocalInstallError(
            "preactivation remediation candidate is not a descendant of the recovery replacement"
        )


def _isolated_git_environment() -> dict[str, str]:
    return {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("GIT_")
    }


def _git_release_entries(source: Path, sha: str) -> tuple[tuple[str, str, bool], ...]:
    command = [
        "git",
        "ls-tree",
        "-r",
        "-z",
        sha,
        "--",
        *_COPY_DIRS,
        *_COPY_FILES,
    ]
    completed = subprocess.run(
        command,
        cwd=source,
        check=False,
        capture_output=True,
        env=_isolated_git_environment(),
        timeout=30,
    )
    if completed.returncode != 0:
        raise LocalInstallError("Git object release listing failed")
    allowed_roots = set(_COPY_DIRS)
    allowed_files = set(_COPY_FILES)
    rows: list[tuple[str, str, bool]] = []
    for raw_entry in completed.stdout.split(b"\0"):
        if not raw_entry:
            continue
        try:
            metadata, raw_path = raw_entry.split(b"\t", 1)
            mode, object_type, blob_sha = metadata.decode("ascii").split(" ")
            relative = raw_path.decode("utf-8", errors="strict")
        except (ValueError, UnicodeDecodeError) as exc:
            raise LocalInstallError("Git object release listing is malformed") from exc
        parts = PurePosixPath(relative).parts
        if (
            not parts
            or PurePosixPath(relative).is_absolute()
            or ".." in parts
            or (parts[0] not in allowed_roots and relative not in allowed_files)
            or object_type != "blob"
            or mode not in {"100644", "100755"}
            or len(blob_sha) != 40
            or any(character not in "0123456789abcdef" for character in blob_sha)
        ):
            raise LocalInstallError("Git object release contains an unsafe path or file mode")
        rows.append((relative, blob_sha, mode == "100755"))
    return tuple(sorted(rows))


def _git_blob(source: Path, blob_sha: str) -> bytes:
    completed = subprocess.run(
        ["git", "cat-file", "blob", blob_sha],
        cwd=source,
        check=False,
        capture_output=True,
        env=_isolated_git_environment(),
        timeout=30,
    )
    if completed.returncode != 0:
        raise LocalInstallError("Git release blob could not be read")
    if len(completed.stdout) > 25 * 1024 * 1024:
        raise LocalInstallError("Git release blob exceeds the local package limit")
    return completed.stdout


def _launchd_payload(
    layout: LocalInstallLayout,
    python_binary: Path,
    *,
    release: Path,
) -> dict[str, Any]:
    entrypoint = release / "apps" / "dev_control_plane_supervisor_v2.py"
    return {
        "Label": LAUNCHD_LABEL,
        "ProgramArguments": [
            str(python_binary),
            str(entrypoint),
            "serve",
            "--state-dir",
            str(layout.state),
            "--host",
            "127.0.0.1",
            "--port",
            str(DEFAULT_PORT),
            "--workspace-root",
            str(layout.state / "managed_workspaces"),
            "--codex-bin",
            "/Applications/ChatGPT.app/Contents/Resources/codex",
            "--release-sha",
            release.name,
            "--activation-nonce-file",
            str(layout.activation_nonce),
        ],
        "RunAtLoad": True,
        "KeepAlive": {"SuccessfulExit": False},
        "ProcessType": "Background",
        "WorkingDirectory": str(release),
        "Umask": 0o077,
        "StandardOutPath": str(layout.logs / "supervisor.stdout.log"),
        "StandardErrorPath": str(layout.logs / "supervisor.stderr.log"),
        "EnvironmentVariables": {
            "DEV_CONTROL_PLANE_AUTHORITY_ROLE": "local_supervisor_v2",
            "DEV_CONTROL_PLANE_V2_RUNTIME_ROOT": str(layout.root),
            "DEV_CONTROL_PLANE_CODEX_BIN": "/Applications/ChatGPT.app/Contents/Resources/codex",
            "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
            "PYTHONUNBUFFERED": "1",
        },
        "ThrottleInterval": 10,
    }


def _release_digest(release: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in release.rglob("*") if item.is_file()):
        relative = path.relative_to(release).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
    return digest.hexdigest()


def _verify_release_manifest(release: Path, sha: str) -> None:
    payload = _read_json(release / "release.json")
    if set(payload) != {"schema", "commit_sha", "git_tree_sha", "entries", "tree_digest"}:
        raise LocalInstallError("release manifest fields are invalid")
    if payload.get("schema") != "dev-control-plane/local-release/v2":
        raise LocalInstallError("release manifest schema mismatch")
    if payload.get("commit_sha") != sha:
        raise LocalInstallError("release manifest commit mismatch")
    tree_sha = payload.get("git_tree_sha")
    if not isinstance(tree_sha, str) or len(tree_sha) != 40 or any(char not in "0123456789abcdef" for char in tree_sha):
        raise LocalInstallError("release manifest Git tree identity is invalid")
    entries = payload.get("entries")
    if not isinstance(entries, list) or not entries:
        raise LocalInstallError("release manifest has no Git entries")
    normalized: list[tuple[str, str, bool]] = []
    for item in entries:
        if not isinstance(item, Mapping) or set(item) != {"path", "blob_sha", "executable"}:
            raise LocalInstallError("release manifest Git entry is invalid")
        relative = item.get("path")
        blob_sha = item.get("blob_sha")
        executable = item.get("executable")
        if (
            not isinstance(relative, str)
            or not isinstance(blob_sha, str)
            or len(blob_sha) != 40
            or any(char not in "0123456789abcdef" for char in blob_sha)
            or not isinstance(executable, bool)
        ):
            raise LocalInstallError("release manifest Git entry identity is invalid")
        parts = PurePosixPath(relative).parts
        if not parts or PurePosixPath(relative).is_absolute() or ".." in parts:
            raise LocalInstallError("release manifest Git entry path is unsafe")
        normalized.append((relative, blob_sha, executable))
    if normalized != sorted(normalized) or len({item[0] for item in normalized}) != len(normalized):
        raise LocalInstallError("release manifest Git entries are not canonical")
    _verify_sealed_release_topology(release, entries=tuple(normalized))
    expected = str(payload.get("tree_digest") or "")
    actual = _release_digest_without_manifest(release)
    if not secrets.compare_digest(expected, actual):
        raise LocalInstallError("release tree digest mismatch")


def _verify_release_against_git(release: Path, *, source: Path, sha: str) -> None:
    expected_entries = _git_release_entries(source, sha)
    manifest = _read_json(release / "release.json")
    observed_entries = tuple(
        (str(item["path"]), str(item["blob_sha"]), bool(item["executable"]))
        for item in manifest["entries"]
    )
    if observed_entries != expected_entries:
        raise LocalInstallError("immutable release topology differs from the exact Git object")
    if manifest.get("git_tree_sha") != _git(source, "rev-parse", f"{sha}^{{tree}}").strip():
        raise LocalInstallError("immutable release Git tree differs from the exact commit")
    for relative, blob_sha, _executable in expected_entries:
        path = release.joinpath(*PurePosixPath(relative).parts)
        if path.read_bytes() != _git_blob(source, blob_sha):
            raise LocalInstallError("immutable release blob differs from the exact Git object")


def _seal_release_tree(release: Path, *, entries: tuple[tuple[str, str, bool], ...]) -> None:
    executable = {relative for relative, _blob, is_executable in entries if is_executable}
    for relative, _blob, _is_executable in entries:
        path = release.joinpath(*PurePosixPath(relative).parts)
        path.chmod(0o555 if relative in executable else 0o444)
    (release / "release.json").chmod(0o444)
    directories = [release]
    for current, names, _files in os.walk(release, topdown=False, followlinks=False):
        current_path = Path(current)
        for name in names:
            candidate = current_path / name
            if candidate.is_symlink():
                raise LocalInstallError("immutable release contains a symlink directory")
            directories.append(candidate)
    for directory in directories:
        directory.chmod(0o555)


def _make_tree_owner_writable(root: Path) -> None:
    for current, names, files in os.walk(root, topdown=False, followlinks=False):
        current_path = Path(current)
        for name in files:
            candidate = current_path / name
            if not candidate.is_symlink():
                candidate.chmod(0o600)
        for name in names:
            candidate = current_path / name
            if not candidate.is_symlink():
                candidate.chmod(0o700)
        current_path.chmod(0o700)


def _verify_sealed_release_topology(
    release: Path,
    *,
    entries: tuple[tuple[str, str, bool], ...],
) -> None:
    expected_files = {relative: executable for relative, _blob, executable in entries}
    expected_files["release.json"] = False
    observed_files: dict[str, int] = {}
    observed_directories: list[Path] = []
    for current, names, files in os.walk(release, topdown=True, followlinks=False):
        current_path = Path(current)
        current_metadata = current_path.lstat()
        if stat.S_ISLNK(current_metadata.st_mode) or not stat.S_ISDIR(current_metadata.st_mode):
            raise LocalInstallError("immutable release contains an unsafe directory")
        observed_directories.append(current_path)
        for name in names:
            candidate = current_path / name
            metadata = candidate.lstat()
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                raise LocalInstallError("immutable release contains an unsafe directory entry")
        for name in files:
            candidate = current_path / name
            metadata = candidate.lstat()
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                raise LocalInstallError("immutable release contains an unsafe file entry")
            observed_files[candidate.relative_to(release).as_posix()] = stat.S_IMODE(metadata.st_mode)
    if set(observed_files) != set(expected_files):
        raise LocalInstallError("immutable release contains missing or extra paths")
    for relative, is_executable in expected_files.items():
        expected_mode = 0o555 if is_executable else 0o444
        if observed_files[relative] != expected_mode:
            raise LocalInstallError("immutable release file mode differs from the sealed Git mode")
    if any(stat.S_IMODE(path.lstat().st_mode) != 0o555 for path in observed_directories):
        raise LocalInstallError("immutable release directory is not sealed read-only")


def _release_digest_without_manifest(release: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in release.rglob("*") if item.is_file() and item.name != "release.json"):
        relative = path.relative_to(release).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
    return digest.hexdigest()


def _symlink_target(path: Path) -> Path | None:
    if not path.is_symlink():
        if path.exists():
            raise LocalInstallError(f"expected symlink but found another path: {path}")
        return None
    target = Path(os.readlink(path))
    candidate = target if target.is_absolute() else path.parent / target
    return Path(os.path.abspath(candidate))


def _atomic_symlink(target: Path, link: Path) -> None:
    temporary = link.with_name(f".{link.name}.{secrets.token_hex(6)}")
    try:
        os.symlink(str(target), temporary)
        os.replace(temporary, link)
        _fsync_directory(link.parent)
    finally:
        if temporary.is_symlink():
            temporary.unlink()
            _fsync_directory(link.parent)


def _restore_release_link(link: Path, target: Path | None) -> None:
    if target is not None:
        _atomic_symlink(target, link)
        return
    if link.is_symlink():
        link.unlink()
        _fsync_directory(link.parent)
    elif link.exists():
        raise LocalInstallError(f"automatic rollback found an unsafe non-symlink path: {link}")


def _validate_release_directory(release: Path, releases: Path, *, expected_sha: str) -> None:
    root = Path(os.path.abspath(releases))
    candidate = Path(os.path.abspath(release))
    try:
        root_metadata = root.lstat()
    except OSError as exc:
        raise LocalInstallError("immutable releases directory is unavailable") from exc
    if stat.S_ISLNK(root_metadata.st_mode) or not stat.S_ISDIR(root_metadata.st_mode):
        raise LocalInstallError("immutable releases root must be a non-symlink directory")
    if (
        candidate.parent != root
        or candidate.name != expected_sha
        or len(expected_sha) != 40
        or any(character not in "0123456789abcdef" for character in expected_sha)
    ):
        raise LocalInstallError("release target is outside the direct immutable releases lane")
    try:
        metadata = candidate.lstat()
    except OSError as exc:
        raise LocalInstallError("immutable release target is unavailable") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise LocalInstallError("immutable release target must be a non-symlink directory")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise LocalInstallError("immutable release target cannot be resolved safely") from exc
    if resolved != candidate:
        raise LocalInstallError("immutable release target traverses a symlink")


def _validate_projection_key(path: Path) -> None:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise LocalInstallError("projection key is unavailable") from exc
    mode = stat.S_IMODE(metadata.st_mode)
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise LocalInstallError("projection key must be a regular non-symlink file")
    if metadata.st_uid != os.geteuid():
        raise LocalInstallError("projection key owner does not match the local service user")
    if mode != 0o600:
        raise LocalInstallError("projection key permissions must be exactly 0600")
    if metadata.st_nlink != 1:
        raise LocalInstallError("projection key must not have hard links")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
        try:
            opened = os.fstat(descriptor)
            material = os.read(descriptor, 4097).rstrip(b"\r\n")
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise LocalInstallError("projection key could not be opened safely") from exc
    if (
        opened.st_dev != metadata.st_dev
        or opened.st_ino != metadata.st_ino
        or not stat.S_ISREG(opened.st_mode)
        or opened.st_uid != os.geteuid()
        or stat.S_IMODE(opened.st_mode) != 0o600
    ):
        raise LocalInstallError("projection key changed during secure validation")
    if not 32 <= len(material) <= 4096:
        raise LocalInstallError("projection key material must contain 32-4096 bytes")


def _atomic_write_json(path: Path, payload: dict[str, Any], *, mode: int) -> None:
    _atomic_write_bytes(
        path,
        (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        mode=mode,
    )


def _atomic_write_bytes(path: Path, payload: bytes, *, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        existing = path.lstat()
    except FileNotFoundError:
        existing = None
    if existing is not None and (stat.S_ISLNK(existing.st_mode) or not stat.S_ISREG(existing.st_mode)):
        raise LocalInstallError(f"refusing to replace unsafe local metadata path: {path}")
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(6)}")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        if temporary.exists():
            temporary.unlink()
            _fsync_directory(path.parent)


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    try:
        descriptor = os.open(path, flags)
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISDIR(metadata.st_mode):
                raise LocalInstallError(f"durability target is not a directory: {path}")
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise LocalInstallError(f"could not durably sync local metadata directory: {path}") from exc


def _read_private_proof_file(path: Path, *, max_bytes: int) -> bytes:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise LocalInstallError(f"qualification evidence is unavailable: {path.name}") from exc
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_nlink != 1
        or metadata.st_size > max_bytes
    ):
        raise LocalInstallError(f"qualification evidence permissions or shape are unsafe: {path.name}")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
        try:
            opened = os.fstat(descriptor)
            payload = os.read(descriptor, max_bytes + 1)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise LocalInstallError(f"qualification evidence could not be read safely: {path.name}") from exc
    try:
        repeated = path.lstat()
    except OSError as exc:
        raise LocalInstallError(f"qualification evidence changed during secure read: {path.name}") from exc
    if (
        opened.st_dev != metadata.st_dev
        or opened.st_ino != metadata.st_ino
        or opened.st_size != metadata.st_size
        or not stat.S_ISREG(opened.st_mode)
        or opened.st_uid != os.geteuid()
        or stat.S_IMODE(opened.st_mode) != 0o600
        or opened.st_nlink != 1
        or len(payload) != metadata.st_size
        or len(payload) > max_bytes
        or (
            repeated.st_dev,
            repeated.st_ino,
            repeated.st_size,
            repeated.st_uid,
            stat.S_IMODE(repeated.st_mode),
            repeated.st_nlink,
        )
        != (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_size,
            metadata.st_uid,
            0o600,
            1,
        )
    ):
        raise LocalInstallError(f"qualification evidence changed during secure read: {path.name}")
    return payload


def _read_private_key_file(path: Path) -> bytes:
    material = _read_private_proof_file(path, max_bytes=4_096).rstrip(b"\r\n")
    if not 32 <= len(material) <= 4_096:
        raise LocalInstallError("installer acceptance key material is invalid")
    return material


def _validate_suite_qualification_evidence(
    raw: bytes,
    *,
    expected_sha: str,
    qualification_created_at: datetime,
    validation_now: datetime,
    require_fresh: bool,
) -> None:
    records = _json_line_objects(raw, ignore_non_json=True)
    matches = [item for item in records if item.get("schema") == "dev-control-plane/v2-suite-evidence/v2"]
    if len(matches) != 1 or len(records) != 1:
        raise LocalInstallError("qualification suite evidence must contain one authoritative result")
    payload = matches[0]
    expected_fields = {
        "schema", "status", "suite", "commit_sha", "generated_at", "checks",
        "smokes", "seconds", "real_model_calls",
    }
    suite_seconds = payload.get("seconds")
    if (
        set(payload) != expected_fields
        or payload.get("status") != "passed"
        or payload.get("suite") != "orchestrator_v2"
        or payload.get("commit_sha") != expected_sha
        or payload.get("real_model_calls") != 0
        or isinstance(payload.get("checks"), bool)
        or not isinstance(payload.get("checks"), int)
        or int(payload["checks"]) != AUTHORITATIVE_CHECK_COUNT
        or isinstance(suite_seconds, bool)
        or not isinstance(suite_seconds, (int, float))
        or not math.isfinite(float(suite_seconds))
        or float(suite_seconds) < 0
    ):
        raise LocalInstallError("qualification suite evidence is stale or incomplete")
    smokes = payload.get("smokes")
    if not isinstance(smokes, list) or len(smokes) != len(AUTHORITATIVE_SMOKES):
        raise LocalInstallError("qualification suite evidence has no smoke receipts")
    observed_paths: list[str] = []
    for item in smokes:
        seconds = item.get("seconds") if isinstance(item, Mapping) else None
        if (
            not isinstance(item, Mapping)
            or set(item) != {"path", "status", "seconds"}
            or item.get("status") != "passed"
            or not isinstance(item.get("path"), str)
            or isinstance(seconds, bool)
            or not isinstance(seconds, (int, float))
            or not math.isfinite(float(seconds))
            or float(seconds) < 0
        ):
            raise LocalInstallError("qualification suite evidence has an invalid smoke receipt")
        observed_paths.append(str(item["path"]))
    if tuple(observed_paths) != AUTHORITATIVE_SMOKES or len(set(observed_paths)) != len(observed_paths):
        raise LocalInstallError("qualification suite membership differs from the authoritative contract")
    generated_at = _qualification_timestamp(payload.get("generated_at"))
    _validate_evidence_time(
        generated_at,
        qualification_created_at=qualification_created_at,
        validation_now=validation_now,
        require_fresh=require_fresh,
        label="suite",
    )


def _validate_shadow_qualification_evidence(
    raw: bytes,
    *,
    backups_root: Path,
    qualification_created_at: datetime,
    validation_now: datetime,
    require_fresh: bool,
) -> bool:
    records = _json_line_objects(raw, ignore_non_json=False)
    absences = [item for item in records if item.get("schema") == "dev-control-plane/legacy-absence/v2"]
    if absences:
        if len(absences) != 1 or len(records) != 1:
            raise LocalInstallError("qualification shadow absence proof is ambiguous")
        absence = absences[0]
        manifest_value = absence.get("manifest_path")
        if not isinstance(manifest_value, str) or not manifest_value:
            raise LocalInstallError("qualification shadow absence has no direct manifest binding")
        manifest = Path(os.path.abspath(Path(manifest_value).expanduser()))
        allowed_root = Path(os.path.abspath(backups_root))
        if (
            manifest.name != "absence.json"
            or manifest.parent.parent != allowed_root
            or manifest.parent.name in {"", ".", ".."}
        ):
            raise LocalInstallError("qualification shadow absence is outside the private backup lane")
        try:
            verified_absence = verify_legacy_absence_manifest(
                manifest,
                expected_label=LEGACY_MONITOR_LABEL,
                expected_source=LEGACY_MONITOR_DB,
                expected_plist=LEGACY_MONITOR_PLIST,
            )
        except MigrationError as exc:
            raise LocalInstallError("qualification shadow absence failed direct verification") from exc
        if asdict(verified_absence) != dict(absence):
            raise LocalInstallError("qualification shadow absence differs from its exact manifest")
        captured_at = _qualification_timestamp(absence.get("captured_at"))
        _validate_evidence_time(
            captured_at,
            qualification_created_at=qualification_created_at,
            validation_now=validation_now,
            require_fresh=require_fresh,
            label="legacy absence",
        )
        return True
    archives = [item for item in records if item.get("schema") == "dev-control-plane/legacy-archive/v2"]
    retirements = [item for item in records if item.get("schema") == "dev-control-plane/legacy-retirement/v2"]
    shadows = [item for item in records if item.get("schema") == "dev-control-plane/legacy-shadow/v2"]
    if (
        len(archives) != 1
        or len(retirements) != 1
        or not shadows
        or len(archives) + len(retirements) + len(shadows) != len(records)
    ):
        raise LocalInstallError("qualification shadow evidence lacks archive/retirement/shadow proof")
    archive = archives[0]
    retirement = retirements[0]
    shadow = shadows[-1]
    retirement_fields = {
        "schema", "status", "label", "was_loaded", "loaded_after", "backup_sha256",
        "plist_preserved", "source_state_preserved", "retired_at",
    }
    shadow_fields = {
        "schema", "available", "authoritative", "integrity", "active_observed_sessions",
        "open_pr_observations", "active_repository_count", "captured_at",
    }
    archive_digest = archive.get("backup_sha256")
    archive_manifest_value = archive.get("manifest_path")
    if not isinstance(archive_manifest_value, str) or not archive_manifest_value:
        raise LocalInstallError("qualification shadow archive has no direct manifest binding")
    archive_manifest = Path(os.path.abspath(Path(archive_manifest_value).expanduser()))
    allowed_root = Path(os.path.abspath(backups_root))
    if (
        archive_manifest.name != "manifest.json"
        or archive_manifest.parent.parent != allowed_root
        or archive_manifest.parent.name in {"", ".", ".."}
    ):
        raise LocalInstallError("qualification shadow archive is outside the private backup lane")
    try:
        verified_archive = verify_legacy_archive_manifest(
            archive_manifest,
            expected_label=LEGACY_MONITOR_LABEL,
        )
    except MigrationError as exc:
        raise LocalInstallError("qualification shadow archive failed direct SQLite verification") from exc
    if asdict(verified_archive) != dict(archive):
        raise LocalInstallError("qualification shadow archive evidence differs from its exact manifest")
    if (
        archive.get("label") != LEGACY_MONITOR_LABEL
        or archive.get("source_present") is not True
        or archive.get("integrity") != "ok"
        or not isinstance(archive_digest, str)
        or not re.fullmatch(r"[0-9a-f]{64}", archive_digest)
        or set(retirement) != retirement_fields
        or retirement.get("status") != "retired"
        or retirement.get("label") != archive.get("label")
        or not isinstance(retirement.get("was_loaded"), bool)
        or retirement.get("was_loaded") != archive.get("legacy_launchd_loaded")
        or retirement.get("loaded_after") is not False
        or retirement.get("backup_sha256") != archive_digest
        or retirement.get("plist_preserved") is not True
        or retirement.get("source_state_preserved") is not True
        or shadow.get("available") is not True
        or shadow.get("authoritative") is not False
        or shadow.get("integrity") != "ok"
    ):
        raise LocalInstallError("qualification shadow evidence did not prove stopped recoverable legacy authority")
    retired_at = _qualification_timestamp(retirement.get("retired_at"))
    archived_at = _qualification_timestamp(archive.get("archived_at"))
    shadow_times: list[datetime] = []
    for shadow_record in shadows:
        if (
            set(shadow_record) != shadow_fields
            or shadow_record.get("available") is not True
            or shadow_record.get("authoritative") is not False
            or shadow_record.get("integrity") != "ok"
            or any(
                isinstance(shadow_record.get(field), bool)
                or not isinstance(shadow_record.get(field), int)
                or int(shadow_record[field]) < 0
                for field in (
                    "active_observed_sessions",
                    "open_pr_observations",
                    "active_repository_count",
                )
            )
        ):
            raise LocalInstallError("qualification shadow record is not a healthy non-authoritative proof")
        shadow_time = _qualification_timestamp(shadow_record.get("captured_at"))
        shadow_times.append(shadow_time)
        _validate_evidence_time(
            shadow_time,
            qualification_created_at=qualification_created_at,
            validation_now=validation_now,
            require_fresh=require_fresh,
            label="shadow",
        )
    captured_at = shadow_times[-1]
    if retired_at < archived_at or captured_at < retired_at:
        raise LocalInstallError("qualification shadow archive/retirement ordering is invalid")
    _validate_evidence_time(
        archived_at,
        qualification_created_at=qualification_created_at,
        validation_now=validation_now,
        require_fresh=require_fresh,
        label="legacy archive",
    )
    _validate_evidence_time(
        retired_at,
        qualification_created_at=qualification_created_at,
        validation_now=validation_now,
        require_fresh=require_fresh,
        label="legacy retirement",
    )
    return False


def _validate_runtime_qualification_evidence(
    raw: bytes,
    *,
    expected_sha: str,
    expected_release: Path,
    expected_nonce_sha256: str | None,
    qualification_created_at: datetime,
    validation_now: datetime,
    require_fresh: bool,
    label: str,
) -> dict[str, Any]:
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LocalInstallError(f"qualification {label} evidence is not one JSON object") from exc
    if not isinstance(document, Mapping):
        raise LocalInstallError(f"qualification {label} evidence is not an object")
    candidate = document.get("qualification_evidence", document)
    top_fields = {
        "schema", "status", "release_sha", "observed_at",
        "app_server_canary", "staged_runtime",
    }
    causal_summary_present = (
        isinstance(candidate, Mapping) and "causal_remediation" in candidate
    )
    if causal_summary_present:
        top_fields.add("causal_remediation")
    if (
        not isinstance(candidate, Mapping)
        or set(candidate) != top_fields
        or candidate.get("schema") != RUNTIME_QUALIFICATION_SCHEMA
        or candidate.get("status") != "passed"
        or candidate.get("release_sha") != expected_sha
    ):
        raise LocalInstallError(f"qualification {label} runtime envelope is invalid")

    observed_at = _qualification_timestamp(candidate.get("observed_at"))
    _validate_evidence_time(
        observed_at,
        qualification_created_at=qualification_created_at,
        validation_now=validation_now,
        require_fresh=require_fresh,
        label=label,
    )
    canary = candidate.get("app_server_canary")
    staged = candidate.get("staged_runtime")
    canary_fields = {
        "schema", "status", "supervisor_generation", "supervisor_host", "binary",
        "transport", "websocket_used", "task_id", "workstream_id", "thread_id",
        "model", "reasoning", "executor_host_id", "executor_generation",
        "turn_ids", "item_ids",
        "lifecycle_event_count", "lifecycle_digest", "terminal_turn_ids",
        "model_attempt_count", "model_call_count", "single_attempt_canary",
        "contract_kind", "progress_percent",
        "checkpoint_event_id", "checkpoint_payload_sha256",
    }
    staged_fields = {
        "schema", "status", "private_socket", "socket_mode", "socket_owner_uid",
        "single_writer", "supervisor_generation", "supervisor_owner_id",
        "lease_expires_at_epoch", "final_attention_deferred", "additional_model_calls",
        "activation_identity",
    }
    if (
        not isinstance(canary, Mapping)
        or set(canary) != canary_fields
        or canary.get("schema") != APP_SERVER_CANARY_EVIDENCE_SCHEMA
        or canary.get("status") != "passed"
        or not isinstance(staged, Mapping)
        or set(staged) != staged_fields
        or staged.get("schema") != STAGED_RUNTIME_EVIDENCE_SCHEMA
        or staged.get("status") != "passed"
    ):
        raise LocalInstallError(f"qualification {label} runtime sections are invalid")

    canary_generation = canary.get("supervisor_generation")
    live_generation = staged.get("supervisor_generation")
    executor_generation = canary.get("executor_generation")
    if (
        not _positive_integer(canary_generation)
        or not _positive_integer(live_generation)
        or not _positive_integer(executor_generation)
    ):
        raise LocalInstallError(f"qualification {label} generation identity is invalid")
    causal_summary = candidate.get("causal_remediation")
    if causal_summary_present:
        _validate_runtime_causal_remediation_summary(
            causal_summary,
            canary=canary,
            staged=staged,
            label=label,
        )
    if (
        (
            not causal_summary_present
            and live_generation != canary_generation
        )
        or int(live_generation) < int(canary_generation)
        or not _bounded_evidence_id(canary.get("supervisor_host"))
        or not _bounded_evidence_id(canary.get("executor_host_id"))
        or not _bounded_evidence_id(staged.get("supervisor_owner_id"))
    ):
        raise LocalInstallError(f"qualification {label} single-writer binding is invalid")

    turn_ids = canary.get("turn_ids")
    terminal_turn_ids = canary.get("terminal_turn_ids")
    item_ids = canary.get("item_ids")
    if (
        canary.get("binary") != DESKTOP_CODEX_BINARY
        or canary.get("transport") != "stdio"
        or canary.get("websocket_used") is not False
        or canary.get("model") != "gpt-5.6-sol"
        or canary.get("reasoning") != "ultra"
        or canary.get("model_attempt_count") != 1
        or canary.get("model_call_count") != 1
        or canary.get("single_attempt_canary") is not True
        or canary.get("contract_kind") != "checkpoint"
        or not _checkpoint_progress(canary.get("progress_percent"))
        or not isinstance(turn_ids, list)
        or len(turn_ids) != 1
        or not _bounded_evidence_id(turn_ids[0])
        or terminal_turn_ids != turn_ids
        or not isinstance(item_ids, list)
        or not item_ids
        or any(not _bounded_evidence_id(item) for item in item_ids)
        or len(set(item_ids)) != len(item_ids)
        or not _positive_integer(canary.get("lifecycle_event_count"))
        or int(canary["lifecycle_event_count"]) < 2
        or not _lower_hex(canary.get("lifecycle_digest"), 64)
    ):
        raise LocalInstallError(
            f"qualification {label} did not prove one exact nonterminal stdio Sol Ultra checkpoint turn"
        )
    for field in (
        "task_id", "workstream_id", "thread_id", "checkpoint_event_id",
    ):
        if not _bounded_evidence_id(canary.get(field)):
            raise LocalInstallError(f"qualification {label} {field} is invalid")
    for field in ("checkpoint_payload_sha256",):
        if not _lower_hex(canary.get(field), 64):
            raise LocalInstallError(f"qualification {label} {field} is invalid")

    lease_expiry = staged.get("lease_expires_at_epoch")
    if (
        staged.get("private_socket") is not True
        or staged.get("socket_mode") != "0600"
        or staged.get("socket_owner_uid") != os.geteuid()
        or staged.get("single_writer") is not True
        or staged.get("final_attention_deferred") is not True
        or staged.get("additional_model_calls") != 0
        or isinstance(lease_expiry, bool)
        or not isinstance(lease_expiry, (int, float))
        or float(lease_expiry) <= observed_at.timestamp()
    ):
        raise LocalInstallError(
            f"qualification {label} did not prove the staged single writer with final attention deferred"
        )

    activation = staged.get("activation_identity")
    activation_fields = {
        "schema", "release_sha", "activation_nonce_sha256", "pid", "python_executable",
        "entrypoint", "bind_host", "bind_port", "supervisor_generation", "supervisor_owner_id",
    }
    expected_entrypoint = (expected_release / "apps" / "dev_control_plane_supervisor_v2.py").resolve()
    if (
        not isinstance(activation, Mapping)
        or set(activation) != activation_fields
        or activation.get("schema") != "dev-control-plane/runtime-activation/v2"
        or activation.get("release_sha") != expected_sha
        or not _lower_hex(activation.get("activation_nonce_sha256"), 64)
        or (
            expected_nonce_sha256 is not None
            and activation.get("activation_nonce_sha256") != expected_nonce_sha256
        )
        or not _positive_integer(activation.get("pid"))
        or activation.get("python_executable") != str(Path(sys.executable).resolve())
        or activation.get("entrypoint") != str(expected_entrypoint)
        or activation.get("bind_host") != "127.0.0.1"
        or activation.get("bind_port") != DEFAULT_PORT
        or activation.get("supervisor_generation") != live_generation
        or activation.get("supervisor_owner_id") != staged.get("supervisor_owner_id")
    ):
        raise LocalInstallError(f"qualification {label} activation identity is invalid")
    return dict(candidate)


def _validate_runtime_causal_remediation_summary(
    raw: Any,
    *,
    canary: Mapping[str, Any],
    staged: Mapping[str, Any],
    label: str,
) -> dict[str, Any]:
    fields = {
        "schema", "status", "observed_at", "root_replacement_sha",
        "structural_bridge_sha", "activation_release_sha",
        "expected_pr_head_sha", "task_id", "workstream_id", "supervisor_id",
        "causal_writer_generation", "successor_writer_generation",
        "admission_writer_generation", "canary_writer_generation",
        "checkpoint_writer_generation", "receipt_writer_generation",
        "contract_supervisor_generation",
        "source_failure_event_id", "source_failure_event_sha256",
        "source_followup_event_id", "source_followup_payload_sha256",
        "causal_read_event_id", "causal_read_payload_sha256",
        "causal_attestation_event_id", "causal_attestation_event_sha256",
        "causal_attestation_digest", "observed_contract_generation",
        "required_historical_supervisor_generation", "mismatched_fields",
        "remediation_event_id", "remediation_event_sha256",
        "completion_event_id", "completion_event_sha256",
        "successor_event_id", "successor_payload_sha256",
        "current_followup_event_id", "current_followup_payload_sha256",
        "current_checkpoint_event_id", "current_checkpoint_event_sha256",
        "current_turn_receipt_event_id", "current_turn_receipt_event_sha256",
        "predecessor_executor_generation", "successor_executor_generation",
        "predecessor_thread_id", "predecessor_host_id",
        "successor_thread_id", "successor_host_id", "strategy_resource",
        "strategy_digest", "same_app_server_epoch", "raw_provider_body_stored",
        "prior_model_attempt_count", "prior_completed_turn_count",
        "prior_turn_receipt_count", "prior_real_model_invocation_count",
        "current_model_attempt_count", "current_completed_turn_count",
        "current_turn_receipt_count", "current_real_model_invocation_count",
        "cumulative_real_model_invocation_count",
        "completed_restart_recovered", "restart_attestation_event_id",
        "restart_attestation_writer_generation", "empty_thread_snapshot_digest",
        "durable_canary_recovered", "turn_receipt_recovered",
        "turn_recovery_event_id", "turn_recovery_writer_generation",
        "recovery_supervisor_generation",
    }
    if (
        not isinstance(raw, Mapping)
        or set(raw) != fields
        or raw.get("schema")
        != PREACTIVATION_CAUSAL_REMEDIATION_EVIDENCE_SCHEMA
        or raw.get("status") != "passed"
    ):
        raise LocalInstallError(
            f"qualification {label} causal remediation summary is invalid"
        )
    _qualification_timestamp(raw.get("observed_at"))
    identity_fields = {
        field
        for field in fields
        if field.endswith("_event_id") or field.endswith("_thread_id")
    } | {
        "predecessor_host_id", "successor_host_id", "supervisor_id",
        "task_id", "workstream_id",
    }
    identity_fields.remove("restart_attestation_event_id")
    identity_fields.remove("turn_recovery_event_id")
    digest_fields = {
        field for field in fields if field.endswith("_sha256")
    } | {"causal_attestation_digest", "strategy_digest"}
    if any(
        not _bounded_evidence_id(raw.get(field)) for field in identity_fields
    ):
        raise LocalInstallError(
            f"qualification {label} causal remediation identity is invalid"
        )
    if any(not _lower_hex(raw.get(field), 64) for field in digest_fields):
        raise LocalInstallError(
            f"qualification {label} causal remediation digest is invalid"
        )
    causal_generation = raw.get("causal_writer_generation")
    successor_generation = raw.get("successor_writer_generation")
    admission_generation = raw.get("admission_writer_generation")
    canary_generation = raw.get("canary_writer_generation")
    checkpoint_generation = raw.get("checkpoint_writer_generation")
    receipt_generation = raw.get("receipt_writer_generation")
    contract_generation = raw.get("contract_supervisor_generation")
    live_generation = staged.get("supervisor_generation")
    if (
        any(
            not _positive_integer(value)
            for value in (
                causal_generation,
                successor_generation,
                admission_generation,
                canary_generation,
                checkpoint_generation,
                receipt_generation,
                contract_generation,
                live_generation,
            )
        )
        or not (
            PREACTIVATION_CAUSAL_REMEDIATION_EXPECTED_OUTPUT_GENERATION
            < int(causal_generation)
            <= int(successor_generation)
            <= int(admission_generation)
            <= int(canary_generation)
            <= int(checkpoint_generation)
            <= int(receipt_generation)
            <= int(live_generation)
        )
        or contract_generation != canary_generation
        or canary.get("supervisor_generation") != canary_generation
        or canary.get("supervisor_host") != raw.get("supervisor_id")
        or raw.get("observed_contract_generation")
        != PREACTIVATION_CAUSAL_REMEDIATION_SOURCE_EXECUTOR_GENERATION
        or raw.get("required_historical_supervisor_generation")
        != PREACTIVATION_CAUSAL_REMEDIATION_EXPECTED_OUTPUT_GENERATION
        or raw.get("mismatched_fields") != ["generation"]
        or tuple(
            raw.get(field)
            for field in (
                "prior_model_attempt_count", "prior_completed_turn_count",
                "prior_turn_receipt_count", "prior_real_model_invocation_count",
                "current_model_attempt_count", "current_completed_turn_count",
                "current_turn_receipt_count", "current_real_model_invocation_count",
                "cumulative_real_model_invocation_count",
            )
        ) != (1, 1, 0, 1, 1, 1, 1, 1, 2)
        or raw.get("raw_provider_body_stored") is not False
    ):
        raise LocalInstallError(
            f"qualification {label} causal remediation lineage is invalid"
        )
    turn_receipt_recovered = raw.get("turn_receipt_recovered")
    turn_recovery_event_id = raw.get("turn_recovery_event_id")
    turn_recovery_writer_generation = raw.get(
        "turn_recovery_writer_generation"
    )
    if turn_receipt_recovered is True:
        if (
            not _bounded_evidence_id(turn_recovery_event_id)
            or receipt_generation <= canary_generation
            or checkpoint_generation not in {
                canary_generation,
                receipt_generation,
            }
            or turn_recovery_writer_generation != receipt_generation
            or raw.get("same_app_server_epoch") is not False
        ):
            raise LocalInstallError(
                f"qualification {label} recovered turn receipt lineage is invalid"
            )
    elif turn_receipt_recovered is False:
        if (
            turn_recovery_event_id != ""
            or turn_recovery_writer_generation is not None
            or checkpoint_generation != canary_generation
            or receipt_generation != canary_generation
            or raw.get("same_app_server_epoch") is not True
        ):
            raise LocalInstallError(
                f"qualification {label} live turn receipt lineage is invalid"
            )
    else:
        raise LocalInstallError(
            f"qualification {label} turn receipt recovery flag is invalid"
        )
    durable_recovered = raw.get("durable_canary_recovered")
    recovery_generation = raw.get("recovery_supervisor_generation")
    if int(live_generation) > int(canary_generation):
        if (
            durable_recovered is not True
            or recovery_generation != live_generation
        ):
            raise LocalInstallError(
                f"qualification {label} durable canary recovery is missing"
            )
    elif (
        durable_recovered is not False
        or recovery_generation is not None
    ):
        raise LocalInstallError(
            f"qualification {label} same-generation canary claims recovery"
        )
    completed_restart = raw.get("completed_restart_recovered")
    restart_event_id = raw.get("restart_attestation_event_id")
    restart_writer_generation = raw.get(
        "restart_attestation_writer_generation"
    )
    snapshot_digest = raw.get("empty_thread_snapshot_digest")
    if int(canary_generation) > int(successor_generation):
        if (
            completed_restart is not True
            or not _bounded_evidence_id(restart_event_id)
            or restart_writer_generation != canary_generation
            or not _lower_hex(snapshot_digest, 64)
        ):
            raise LocalInstallError(
                f"qualification {label} completed restart evidence is invalid"
            )
    elif (
        completed_restart is not False
        or restart_event_id != ""
        or restart_writer_generation is not None
        or snapshot_digest is not None
    ):
        raise LocalInstallError(
            f"qualification {label} uninterrupted canary claims restart"
        )
    return dict(raw)


def _runtime_qualification_binding(payload: Mapping[str, Any]) -> tuple[Any, ...]:
    canary = payload["app_server_canary"]
    staged = payload["staged_runtime"]
    activation = staged["activation_identity"]
    causal = payload.get("causal_remediation")
    causal_binding = (
        tuple(sorted(causal.items()))
        if isinstance(causal, Mapping)
        else None
    )
    return (
        payload["release_sha"],
        canary["supervisor_generation"],
        canary["supervisor_host"],
        canary["task_id"],
        canary["workstream_id"],
        canary["thread_id"],
        canary["executor_host_id"],
        canary["executor_generation"],
        canary["contract_kind"],
        canary["progress_percent"],
        tuple(canary["turn_ids"]),
        tuple(canary["item_ids"]),
        canary["lifecycle_digest"],
        canary["checkpoint_event_id"],
        canary["checkpoint_payload_sha256"],
        staged["final_attention_deferred"],
        staged["supervisor_owner_id"],
        activation["activation_nonce_sha256"],
        activation["pid"],
        activation["python_executable"],
        activation["entrypoint"],
        causal_binding,
    )


def _validate_preactivation_recovery_qualification_evidence(
    raw: bytes,
    *,
    expected_replacement_sha: str,
    runtime_root: Path,
    expected_supervisor_generation: int,
    qualification_created_at: datetime,
    validation_now: datetime,
    require_fresh: bool,
    require_immediate_successor: bool,
) -> None:
    root = Path(os.path.abspath(runtime_root))
    canonical = root / "preactivation-recovery.json"
    if raw != _read_private_proof_file(canonical, max_bytes=1_000_000):
        raise LocalInstallError(
            "qualification preactivation recovery evidence is not the canonical receipt"
        )
    verified = verify_preactivation_recovery_receipt(
        canonical,
        expected_replacement_sha=expected_replacement_sha,
        runtime_root=root,
        require_pristine=False,
        require_empty_projection=require_fresh,
    )
    if require_immediate_successor and (
        expected_supervisor_generation
        != int(verified["prior_supervisor_generation"]) + 1
    ):
        raise LocalInstallError(
            "qualification pilot is not the immediate successor of the archived generation"
        )
    current_generation = int(verified["current_supervisor_generation"])
    if (
        current_generation < expected_supervisor_generation
        or (require_fresh and current_generation != expected_supervisor_generation)
        or (require_fresh and verified["current_supervisor_active"] is not False)
        or int(verified["current_projection_generation"])
        < expected_supervisor_generation
        or int(verified["current_projection_revision"])
        <= int(verified["prior_projection_revision"])
        or int(verified["current_projection_sequence"]) < 1
    ):
        raise LocalInstallError(
            "qualification recovery watermarks do not bind the observed Supervisor generation"
        )
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LocalInstallError(
            "qualification preactivation recovery evidence is invalid JSON"
        ) from exc
    if not isinstance(document, Mapping):
        raise LocalInstallError(
            "qualification preactivation recovery evidence is not an object"
        )
    recovered_at = _qualification_timestamp(document.get("recovered_at"))
    _validate_evidence_time(
        recovered_at,
        qualification_created_at=qualification_created_at,
        validation_now=validation_now,
        require_fresh=require_fresh,
        label="preactivation recovery",
    )


def _validate_preactivation_remediation_qualification_evidence(
    raw: bytes,
    *,
    expected_sha: str,
    expected_root_replacement_sha: str,
    runtime_root: Path,
    expected_supervisor_generation: int,
    qualification_created_at: datetime,
    validation_now: datetime,
    require_fresh: bool,
    boundary_recheck: Callable[[], None] | None,
) -> None:
    try:
        evidence = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LocalInstallError(
            "qualification preactivation remediation evidence is invalid JSON"
        ) from exc
    fields = {
        "schema", "status", "observed_at", "root_replacement_sha",
        "activation_release_sha", "expected_pr_head_sha", "repair_event_id",
        "repair_event_sha256", "completion_event_id",
        "completion_event_sha256", "task_id",
        "workstream_id", "predecessor_executor_generation",
        "successor_executor_generation", "predecessor_thread_id",
        "predecessor_host_id", "successor_thread_id", "successor_host_id",
        "structural_thread_start_only", "same_app_server_epoch",
        "model_attempt_count", "model_call_count", "real_model_calls",
    }
    if not isinstance(evidence, Mapping) or set(evidence) != fields:
        raise LocalInstallError(
            "qualification preactivation remediation evidence fields are invalid"
        )
    observed_at = _qualification_timestamp(evidence.get("observed_at"))
    _validate_evidence_time(
        observed_at,
        qualification_created_at=qualification_created_at,
        validation_now=validation_now,
        require_fresh=require_fresh,
        label="preactivation remediation",
    )
    predecessor_generation = evidence.get("predecessor_executor_generation")
    successor_generation = evidence.get("successor_executor_generation")
    if (
        evidence.get("schema") != PREACTIVATION_REMEDIATION_EVIDENCE_SCHEMA
        or evidence.get("status") != "passed"
        or evidence.get("root_replacement_sha")
        != expected_root_replacement_sha
        or evidence.get("activation_release_sha") != expected_sha
        or not _lower_hex(evidence.get("expected_pr_head_sha"), 40)
        or evidence.get("expected_pr_head_sha")
        in {expected_sha, expected_root_replacement_sha}
        or expected_sha == expected_root_replacement_sha
        or evidence.get("task_id") != PREACTIVATION_STRUCTURAL_REPAIR_TASK_ID
        or evidence.get("workstream_id")
        != PREACTIVATION_STRUCTURAL_REPAIR_WORKSTREAM_ID
        or not _positive_integer(predecessor_generation)
        or successor_generation != int(predecessor_generation) + 1
        or evidence.get("structural_thread_start_only") is not True
        or evidence.get("same_app_server_epoch") is not True
        or evidence.get("model_attempt_count") != 0
        or evidence.get("model_call_count") != 0
        or evidence.get("real_model_calls") != 0
    ):
        raise LocalInstallError(
            "qualification preactivation remediation identity is invalid"
        )
    for field in (
        "repair_event_id", "completion_event_id", "task_id", "workstream_id",
        "predecessor_thread_id", "predecessor_host_id", "successor_thread_id",
        "successor_host_id",
    ):
        if not _bounded_evidence_id(evidence.get(field)):
            raise LocalInstallError(
                f"qualification preactivation remediation {field} is invalid"
            )
    for field in ("repair_event_sha256", "completion_event_sha256"):
        if not _lower_hex(evidence.get(field), 64):
            raise LocalInstallError(
                f"qualification preactivation remediation {field} is invalid"
            )

    root = Path(os.path.abspath(runtime_root))
    database = root / "state" / "supervisor.sqlite3"
    if boundary_recheck is not None:
        boundary_recheck()
    database_before = _private_regular_metadata(database)
    connection = sqlite3.connect(
        _sqlite_readonly_uri(database), uri=True, timeout=10
    )
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only = ON")
        connection.execute("BEGIN")
        if str(connection.execute("PRAGMA quick_check").fetchone()[0]) != "ok":
            raise LocalInstallError(
                "preactivation remediation registry integrity check failed"
            )
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise LocalInstallError(
                "preactivation remediation registry foreign keys are inconsistent"
            )
        repair = _preactivation_registry_event(
            connection,
            event_id=str(evidence["repair_event_id"]),
            event_type=PREACTIVATION_STRUCTURAL_REPAIR_EVENT_TYPE,
            expected_digest=str(evidence["repair_event_sha256"]),
        )
        completion = _preactivation_registry_event(
            connection,
            event_id=str(evidence["completion_event_id"]),
            event_type=PREACTIVATION_STRUCTURAL_REPAIR_COMPLETION_EVENT_TYPE,
            expected_digest=str(evidence["completion_event_sha256"]),
        )
        if connection.execute(
            "SELECT COUNT(*) FROM events WHERE event_type = ?",
            (PREACTIVATION_STRUCTURAL_REPAIR_EVENT_TYPE,),
        ).fetchone()[0] != 1 or connection.execute(
            "SELECT COUNT(*) FROM events WHERE event_type = ?",
            (PREACTIVATION_STRUCTURAL_REPAIR_COMPLETION_EVENT_TYPE,),
        ).fetchone()[0] != 1:
            raise LocalInstallError(
                "preactivation remediation is not the unique structural repair"
            )
        repair_payload = repair["payload"]
        completion_payload = completion["payload"]
        predecessor_state = _validate_preactivation_structural_repair_payload(
            repair_payload,
            expected_sha=expected_sha,
            evidence=evidence,
            runtime_root=root,
            qualification_created_at=qualification_created_at,
            validation_now=validation_now,
            require_fresh=require_fresh,
        )
        _validate_preactivation_structural_completion_payload(
            completion_payload,
            expected_sha=expected_sha,
            evidence=evidence,
            repair_payload=repair_payload,
            qualification_created_at=qualification_created_at,
            validation_now=validation_now,
            require_fresh=require_fresh,
        )
        if (
            repair["task_id"] != evidence["task_id"]
            or repair["workstream_id"] != evidence["workstream_id"]
            or repair["executor_generation"] != predecessor_generation
            or completion["task_id"] != evidence["task_id"]
            or completion["workstream_id"] != evidence["workstream_id"]
            or completion["executor_generation"] != successor_generation
            or repair["writer_generation"] != expected_supervisor_generation
            or completion["writer_generation"] != expected_supervisor_generation
            or predecessor_state["supervisor_generation"]
            != repair["writer_generation"]
        ):
            raise LocalInstallError(
                "preactivation remediation event coordinates changed"
            )
        _validate_preactivation_structural_successor_outbox(
            connection,
            repair_payload=repair_payload,
            completion_payload=completion_payload,
            evidence=evidence,
            expected_supervisor_generation=expected_supervisor_generation,
        )
        _validate_preactivation_resolved_attention(
            connection,
            repair_payload=repair_payload,
            task_id=str(evidence["task_id"]),
            require_fresh=require_fresh,
        )
        _validate_preactivation_resolved_incidents(
            connection,
            repair_payload=repair_payload,
            task_id=str(evidence["task_id"]),
            workstream_id=str(evidence["workstream_id"]),
            repair_event_id=str(evidence["repair_event_id"]),
        )
        _validate_preactivation_structural_release_intake(
            connection,
            completion_payload=completion_payload,
            activation_release_sha=expected_sha,
            expected_pr_head_sha=str(evidence["expected_pr_head_sha"]),
            task_id=str(evidence["task_id"]),
            workstream_id=str(evidence["workstream_id"]),
            expected_supervisor_generation=expected_supervisor_generation,
            current_state=None,
            expected_pr_number=92,
        )
        connection.execute("COMMIT")
    finally:
        connection.close()
    database_after = _private_regular_metadata(database)
    if (
        database_before.st_dev,
        database_before.st_ino,
        database_before.st_uid,
        database_before.st_mode,
        database_before.st_nlink,
    ) != (
        database_after.st_dev,
        database_after.st_ino,
        database_after.st_uid,
        database_after.st_mode,
        database_after.st_nlink,
    ):
        raise LocalInstallError(
            "preactivation remediation registry identity changed during validation"
        )
    if require_fresh and (
        database_before.st_size,
        database_before.st_mtime_ns,
    ) != (
        database_after.st_size,
        database_after.st_mtime_ns,
    ):
        raise LocalInstallError(
            "fresh preactivation remediation registry changed during validation"
        )
    if boundary_recheck is not None:
        boundary_recheck()


def _validate_preactivation_causal_remediation_qualification_evidence(
    raw: bytes,
    *,
    expected_sha: str,
    expected_root_replacement_sha: str,
    expected_structural_bridge_sha: str,
    runtime_root: Path,
    expected_canary: Mapping[str, Any],
    expected_runtime_causal_summary: Mapping[str, Any],
    qualification_created_at: datetime,
    validation_now: datetime,
    require_fresh: bool,
    boundary_recheck: Callable[[], None] | None,
) -> None:
    try:
        evidence = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LocalInstallError(
            "qualification preactivation causal remediation evidence is invalid JSON"
        ) from exc
    fields = {
        "schema", "status", "observed_at", "root_replacement_sha",
        "structural_bridge_sha", "activation_release_sha",
        "expected_pr_head_sha", "task_id", "workstream_id", "supervisor_id",
        "causal_writer_generation", "successor_writer_generation",
        "admission_writer_generation", "canary_writer_generation",
        "checkpoint_writer_generation", "receipt_writer_generation",
        "contract_supervisor_generation",
        "source_failure_event_id", "source_failure_event_sha256",
        "source_followup_event_id", "source_followup_payload_sha256",
        "causal_read_event_id", "causal_read_payload_sha256",
        "causal_attestation_event_id", "causal_attestation_event_sha256",
        "causal_attestation_digest", "observed_contract_generation",
        "required_historical_supervisor_generation", "mismatched_fields",
        "remediation_event_id", "remediation_event_sha256",
        "completion_event_id", "completion_event_sha256",
        "successor_event_id", "successor_payload_sha256",
        "current_followup_event_id", "current_followup_payload_sha256",
        "current_checkpoint_event_id", "current_checkpoint_event_sha256",
        "current_turn_receipt_event_id", "current_turn_receipt_event_sha256",
        "predecessor_executor_generation", "successor_executor_generation",
        "predecessor_thread_id", "predecessor_host_id",
        "successor_thread_id", "successor_host_id", "strategy_resource",
        "strategy_digest", "same_app_server_epoch", "raw_provider_body_stored",
        "prior_model_attempt_count", "prior_completed_turn_count",
        "prior_turn_receipt_count", "prior_real_model_invocation_count",
        "current_model_attempt_count", "current_completed_turn_count",
        "current_turn_receipt_count", "current_real_model_invocation_count",
        "cumulative_real_model_invocation_count",
        "completed_restart_recovered", "restart_attestation_event_id",
        "restart_attestation_writer_generation", "empty_thread_snapshot_digest",
        "durable_canary_recovered", "turn_receipt_recovered",
        "turn_recovery_event_id", "turn_recovery_writer_generation",
        "recovery_supervisor_generation",
    }
    if not isinstance(evidence, Mapping) or set(evidence) != fields:
        raise LocalInstallError(
            "qualification preactivation causal remediation evidence fields are invalid"
        )
    if dict(evidence) != dict(expected_runtime_causal_summary):
        raise LocalInstallError(
            "qualification causal evidence differs from the runtime summary"
        )
    observed_at = _qualification_timestamp(evidence.get("observed_at"))
    _validate_evidence_time(
        observed_at,
        qualification_created_at=qualification_created_at,
        validation_now=validation_now,
        require_fresh=require_fresh,
        label="preactivation causal remediation",
    )
    if (
        evidence.get("schema") != PREACTIVATION_CAUSAL_REMEDIATION_EVIDENCE_SCHEMA
        or evidence.get("status") != "passed"
        or evidence.get("root_replacement_sha") != expected_root_replacement_sha
        or evidence.get("structural_bridge_sha") != expected_structural_bridge_sha
        or evidence.get("activation_release_sha") != expected_sha
        or not _lower_hex(evidence.get("expected_pr_head_sha"), 40)
        or evidence.get("expected_pr_head_sha")
        in {expected_root_replacement_sha, expected_structural_bridge_sha, expected_sha}
        or evidence.get("task_id") != PREACTIVATION_STRUCTURAL_REPAIR_TASK_ID
        or evidence.get("workstream_id")
        != PREACTIVATION_STRUCTURAL_REPAIR_WORKSTREAM_ID
        or not _bounded_evidence_id(evidence.get("supervisor_id"))
        or not _positive_integer(evidence.get("causal_writer_generation"))
        or not _positive_integer(evidence.get("successor_writer_generation"))
        or not _positive_integer(evidence.get("admission_writer_generation"))
        or not _positive_integer(evidence.get("canary_writer_generation"))
        or not _positive_integer(evidence.get("checkpoint_writer_generation"))
        or not _positive_integer(evidence.get("receipt_writer_generation"))
        or not _positive_integer(evidence.get("contract_supervisor_generation"))
        or int(evidence["causal_writer_generation"])
        <= PREACTIVATION_CAUSAL_REMEDIATION_EXPECTED_OUTPUT_GENERATION
        or int(evidence["successor_writer_generation"])
        < int(evidence["causal_writer_generation"])
        or int(evidence["admission_writer_generation"])
        < int(evidence["successor_writer_generation"])
        or int(evidence["canary_writer_generation"])
        < int(evidence["admission_writer_generation"])
        or int(evidence["checkpoint_writer_generation"])
        < int(evidence["canary_writer_generation"])
        or int(evidence["receipt_writer_generation"])
        < int(evidence["checkpoint_writer_generation"])
        or evidence.get("contract_supervisor_generation")
        != evidence.get("canary_writer_generation")
        or evidence.get("predecessor_executor_generation")
        != PREACTIVATION_CAUSAL_REMEDIATION_SOURCE_EXECUTOR_GENERATION
        or evidence.get("successor_executor_generation")
        != PREACTIVATION_CAUSAL_REMEDIATION_SUCCESSOR_EXECUTOR_GENERATION
        or evidence.get("strategy_resource")
        != PREACTIVATION_CAUSAL_REMEDIATION_STRATEGY_RESOURCE
        or evidence.get("strategy_digest")
        != hashlib.sha256(
            PREACTIVATION_CAUSAL_REMEDIATION_STRATEGY_RESOURCE.encode("utf-8")
        ).hexdigest()
        or evidence.get("raw_provider_body_stored") is not False
        or tuple(
            evidence.get(field)
            for field in (
                "prior_model_attempt_count",
                "prior_completed_turn_count",
                "prior_turn_receipt_count",
                "prior_real_model_invocation_count",
                "current_model_attempt_count",
                "current_completed_turn_count",
                "current_turn_receipt_count",
                "current_real_model_invocation_count",
                "cumulative_real_model_invocation_count",
            )
        ) != (1, 1, 0, 1, 1, 1, 1, 1, 2)
    ):
        raise LocalInstallError(
            "qualification preactivation causal remediation identity or counters are invalid"
        )
    id_fields = {
        field
        for field in fields
        if field.endswith("_event_id") or field.endswith("_thread_id")
    } | {"predecessor_host_id", "successor_host_id"}
    id_fields.remove("restart_attestation_event_id")
    id_fields.remove("turn_recovery_event_id")
    digest_fields = {
        field
        for field in fields
        if field.endswith("_sha256") or field == "strategy_digest"
    }
    if any(not _bounded_evidence_id(evidence.get(field)) for field in id_fields):
        raise LocalInstallError(
            "qualification preactivation causal remediation identity is unbounded"
        )
    if any(not _lower_hex(evidence.get(field), 64) for field in digest_fields):
        raise LocalInstallError(
            "qualification preactivation causal remediation digest is invalid"
        )
    causal_writer_generation = int(evidence["causal_writer_generation"])
    successor_writer_generation = int(evidence["successor_writer_generation"])
    admission_writer_generation = int(evidence["admission_writer_generation"])
    canary_writer_generation = int(evidence["canary_writer_generation"])
    checkpoint_writer_generation = int(evidence["checkpoint_writer_generation"])
    receipt_writer_generation = int(evidence["receipt_writer_generation"])
    contract_supervisor_generation = int(
        evidence["contract_supervisor_generation"]
    )
    turn_receipt_recovered = evidence.get("turn_receipt_recovered")
    turn_recovery_event_id = evidence.get("turn_recovery_event_id")
    turn_recovery_writer_generation = evidence.get(
        "turn_recovery_writer_generation"
    )
    if turn_receipt_recovered is True:
        if (
            not _bounded_evidence_id(turn_recovery_event_id)
            or receipt_writer_generation <= canary_writer_generation
            or checkpoint_writer_generation not in {
                canary_writer_generation,
                receipt_writer_generation,
            }
            or turn_recovery_writer_generation != receipt_writer_generation
            or evidence.get("same_app_server_epoch") is not False
        ):
            raise LocalInstallError(
                "PR93 recovered turn receipt lineage is invalid"
            )
    elif turn_receipt_recovered is False:
        if (
            turn_recovery_event_id != ""
            or turn_recovery_writer_generation is not None
            or checkpoint_writer_generation != canary_writer_generation
            or receipt_writer_generation != canary_writer_generation
            or evidence.get("same_app_server_epoch") is not True
        ):
            raise LocalInstallError(
                "PR93 live turn receipt lineage is invalid"
            )
    else:
        raise LocalInstallError("PR93 turn receipt recovery flag is invalid")
    completed_restart_recovered = evidence.get("completed_restart_recovered")
    restart_attestation_event_id = evidence.get("restart_attestation_event_id")
    restart_attestation_writer_generation = evidence.get(
        "restart_attestation_writer_generation"
    )
    empty_thread_snapshot_digest = evidence.get("empty_thread_snapshot_digest")
    restart_required = canary_writer_generation > successor_writer_generation
    if restart_required and (
        completed_restart_recovered is not True
        or not _bounded_evidence_id(restart_attestation_event_id)
        or restart_attestation_writer_generation != canary_writer_generation
        or not _lower_hex(empty_thread_snapshot_digest, 64)
    ):
        raise LocalInstallError(
            "PR93 canary restart recovery evidence is invalid"
        )
    if not restart_required and (
        completed_restart_recovered is not False
        or restart_attestation_event_id != ""
        or restart_attestation_writer_generation is not None
        or empty_thread_snapshot_digest is not None
    ):
        raise LocalInstallError(
            "PR93 same-generation canary claims a restart recovery"
        )
    current_supervisor_generation = expected_canary.get("supervisor_generation")
    canary_binding = (
        current_supervisor_generation,
        expected_canary.get("task_id"),
        expected_canary.get("workstream_id"),
        expected_canary.get("thread_id"),
        expected_canary.get("executor_host_id"),
        expected_canary.get("supervisor_host"),
        expected_canary.get("executor_generation"),
        expected_canary.get("model"),
        expected_canary.get("reasoning"),
        expected_canary.get("model_attempt_count"),
        expected_canary.get("model_call_count"),
        expected_canary.get("checkpoint_event_id"),
        expected_canary.get("checkpoint_payload_sha256"),
    )
    if canary_binding != (
        canary_writer_generation,
        evidence["task_id"], evidence["workstream_id"],
        evidence["successor_thread_id"], evidence["successor_host_id"],
        evidence["supervisor_id"],
        evidence["successor_executor_generation"], "gpt-5.6-sol", "ultra",
        1, 1, evidence["current_checkpoint_event_id"],
        evidence["current_checkpoint_event_sha256"],
    ):
        raise LocalInstallError(
            "qualification PR93 canary is not bound to the causal successor"
        )

    root = Path(os.path.abspath(runtime_root))
    database = root / "state" / "supervisor.sqlite3"
    if boundary_recheck is not None:
        boundary_recheck()
    before = _private_regular_metadata(database)
    connection = sqlite3.connect(_sqlite_readonly_uri(database), uri=True, timeout=10)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only = ON")
        connection.execute("BEGIN")
        if str(connection.execute("PRAGMA quick_check").fetchone()[0]) != "ok":
            raise LocalInstallError(
                "preactivation causal remediation registry integrity check failed"
            )
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise LocalInstallError(
                "preactivation causal remediation registry foreign keys are inconsistent"
            )

        failure = _preactivation_registry_event(
            connection,
            event_id=str(evidence["source_failure_event_id"]),
            event_type="qualification_canary_failed",
            expected_digest=str(evidence["source_failure_event_sha256"]),
        )
        attestation = _preactivation_registry_event(
            connection,
            event_id=str(evidence["causal_attestation_event_id"]),
            event_type=PREACTIVATION_CAUSAL_ATTESTATION_EVENT_TYPE,
            expected_digest=str(evidence["causal_attestation_event_sha256"]),
        )
        remediation = _preactivation_registry_event(
            connection,
            event_id=str(evidence["remediation_event_id"]),
            event_type=PREACTIVATION_CAUSAL_REMEDIATION_EVENT_TYPE,
            expected_digest=str(evidence["remediation_event_sha256"]),
        )
        completion = _preactivation_registry_event(
            connection,
            event_id=str(evidence["completion_event_id"]),
            event_type=PREACTIVATION_CAUSAL_COMPLETION_EVENT_TYPE,
            expected_digest=str(evidence["completion_event_sha256"]),
        )
        checkpoint = _preactivation_registry_event(
            connection,
            event_id=str(evidence["current_checkpoint_event_id"]),
            event_type="checkpoint",
            expected_digest=str(evidence["current_checkpoint_event_sha256"]),
        )
        receipt = _preactivation_registry_event(
            connection,
            event_id=str(evidence["current_turn_receipt_event_id"]),
            event_type="codex_turn_receipt",
            expected_digest=str(evidence["current_turn_receipt_event_sha256"]),
        )
        restart_attestation = (
            _preactivation_registry_event(
                connection,
                event_id=str(restart_attestation_event_id),
                event_type=PREACTIVATION_CAUSAL_RESTART_ATTESTATION_EVENT_TYPE,
                expected_digest=None,
            )
            if restart_required
            else None
        )
        turn_recovery = (
            _preactivation_registry_event(
                connection,
                event_id=str(turn_recovery_event_id),
                event_type=PREACTIVATION_CAUSAL_TURN_RECOVERY_EVENT_TYPE,
                expected_digest=None,
            )
            if turn_receipt_recovered
            else None
        )
        for event_type in (
            PREACTIVATION_CAUSAL_ATTESTATION_EVENT_TYPE,
            PREACTIVATION_CAUSAL_REMEDIATION_EVENT_TYPE,
            PREACTIVATION_CAUSAL_COMPLETION_EVENT_TYPE,
            "qualification_canary_failed", "checkpoint", "codex_turn_receipt",
        ):
            if connection.execute(
                "SELECT COUNT(*) FROM events WHERE event_type = ?", (event_type,)
            ).fetchone()[0] != 1:
                raise LocalInstallError(
                    "preactivation causal remediation event history is not unique"
                )
        restart_attestation_count = connection.execute(
            "SELECT COUNT(*) FROM events WHERE event_type = ?",
            (PREACTIVATION_CAUSAL_RESTART_ATTESTATION_EVENT_TYPE,),
        ).fetchone()[0]
        if restart_attestation_count != (1 if restart_required else 0):
            raise LocalInstallError(
                "preactivation causal restart attestation history is invalid"
            )
        turn_recovery_count = connection.execute(
            "SELECT COUNT(*) FROM events WHERE event_type = ?",
            (PREACTIVATION_CAUSAL_TURN_RECOVERY_EVENT_TYPE,),
        ).fetchone()[0]
        if turn_recovery_count != (1 if turn_receipt_recovered else 0):
            raise LocalInstallError(
                "preactivation causal turn recovery history is invalid"
            )
        if connection.execute(
            "SELECT 1 FROM events WHERE event_type IN ('preactivation_causal_remediation_failed','preactivation_structural_repair_failed') LIMIT 1"
        ).fetchone() is not None:
            raise LocalInstallError(
                "preactivation causal remediation contains a terminal repair failure"
            )

        def outbox(event_id: str, kind: str, digest: str) -> tuple[sqlite3.Row, dict[str, Any]]:
            row = connection.execute(
                "SELECT * FROM outbox WHERE event_id = ?", (event_id,)
            ).fetchone()
            if row is None or row["kind"] != kind:
                raise LocalInstallError(
                    "preactivation causal remediation durable outbox item is missing"
                )
            payload = _validated_registry_json_mapping(
                row["payload_json"], row["payload_digest"],
                label="preactivation causal remediation outbox",
            )
            if row["payload_digest"] != digest:
                raise LocalInstallError(
                    "preactivation causal remediation outbox digest changed"
                )
            return row, payload

        source_followup_row, source_followup = outbox(
            str(evidence["source_followup_event_id"]), "codex_followup",
            str(evidence["source_followup_payload_sha256"]),
        )
        read_row, read_payload = outbox(
            str(evidence["causal_read_event_id"]), PREACTIVATION_CAUSAL_READ_KIND,
            str(evidence["causal_read_payload_sha256"]),
        )
        successor_row, successor_payload = outbox(
            str(evidence["successor_event_id"]), PREACTIVATION_CAUSAL_SUCCESSOR_KIND,
            str(evidence["successor_payload_sha256"]),
        )
        current_followup_row, current_followup = outbox(
            str(evidence["current_followup_event_id"]), "codex_followup",
            str(evidence["current_followup_payload_sha256"]),
        )
        if (
            source_followup_row["state"] != "delivered"
            or int(source_followup_row["attempts"]) != 1
            or source_followup_row["writer_generation"]
            != PREACTIVATION_CAUSAL_REMEDIATION_EXPECTED_OUTPUT_GENERATION
            or current_followup_row["state"] != "delivered"
            or int(current_followup_row["attempts"]) not in {1, 2}
            or current_followup_row["writer_generation"]
            != canary_writer_generation
            or successor_row["state"] != "delivered"
            or int(successor_row["attempts"]) not in {1, 2}
            or successor_row["writer_generation"] != successor_writer_generation
            or read_row["state"] != "delivered"
            or int(read_row["attempts"]) not in {1, 2}
            or read_row["writer_generation"] != causal_writer_generation
            or connection.execute(
                "SELECT COUNT(*) FROM outbox WHERE kind = 'codex_followup'"
            ).fetchone()[0] != 2
        ):
            raise LocalInstallError(
                "preactivation causal remediation model invocation budget is invalid"
            )

        failure_payload = failure["payload"]
        failure_fields = {
            "schema", "status", "decision", "followup_event_id", "error_code",
            "call_policy", "model_attempt_count", "call_intent_present",
            "worker_claim_count", "retry_allowed", "successor_allowed",
            "arbiter_allowed", "attention_created", "updated_at",
        }
        if (
            set(failure_payload) != failure_fields
            or failure_payload.get("schema")
            != "dev-control-plane/qualification-canary-failure/v2"
            or failure_payload.get("status") != "failed"
            or failure_payload.get("decision") != "stop_qualification"
            or failure_payload.get("followup_event_id")
            != evidence["source_followup_event_id"]
            or failure_payload.get("call_policy") != "single_attempt_canary"
            or failure_payload.get("model_attempt_count") != 1
            or failure_payload.get("call_intent_present") is not True
            or failure_payload.get("worker_claim_count") != 1
            or any(failure_payload.get(field) is not False for field in (
                "retry_allowed", "successor_allowed", "arbiter_allowed",
                "attention_created",
            ))
            or failure["executor_generation"]
            != PREACTIVATION_CAUSAL_REMEDIATION_SOURCE_EXECUTOR_GENERATION
            or failure["writer_generation"]
            != PREACTIVATION_CAUSAL_REMEDIATION_EXPECTED_OUTPUT_GENERATION
        ):
            raise LocalInstallError(
                "preactivation PR92 failed-canary attestation is invalid"
            )
        _qualification_timestamp(failure_payload.get("updated_at"))
        source_intent = source_followup.get("call_intent")
        if (
            source_followup.get("schema") != "dev-control-plane/codex-followup/v2"
            or source_followup.get("task_revision")
            != PREACTIVATION_CAUSAL_REMEDIATION_SOURCE_TASK_REVISION
            or source_followup.get("workstream_generation", PREACTIVATION_CAUSAL_REMEDIATION_SOURCE_WORKSTREAM_GENERATION)
            != PREACTIVATION_CAUSAL_REMEDIATION_SOURCE_WORKSTREAM_GENERATION
            or source_followup.get("workstream_revision")
            != PREACTIVATION_CAUSAL_REMEDIATION_SOURCE_WORKSTREAM_REVISION
            or source_followup.get("executor_generation")
            != PREACTIVATION_CAUSAL_REMEDIATION_SOURCE_EXECUTOR_GENERATION
            or source_followup.get("thread_id") != evidence["predecessor_thread_id"]
            or source_followup.get("host_id") != evidence["predecessor_host_id"]
            or source_followup.get("call_policy") != "single_attempt_canary"
            or source_followup.get("model_attempt_count") != 1
            or not isinstance(source_intent, Mapping)
            or source_intent.get("supervisor_generation")
            != PREACTIVATION_CAUSAL_REMEDIATION_EXPECTED_OUTPUT_GENERATION
            or source_intent.get("baseline_turn_ids") != []
        ):
            raise LocalInstallError(
                "preactivation PR92 source followup binding changed"
            )

        attestation_payload = attestation["payload"]
        durable_attestation_fields = {
            "schema", "status", "read_method", "causal_read_event_id",
            "source_failure_event_id", "source_followup_event_id", "thread_id",
            "turn_id", "output_item_id", "thread_snapshot_digest", "turn_digest",
            "output_item_digest", "contract_digest", "turn_status", "turn_count",
            "observed_identity", "expected_identity", "mismatched_fields",
            "raw_provider_body_stored", "attestation_digest",
            "attested_writer_generation", "attested_at",
        }
        attestation_base = {
            key: value for key, value in attestation_payload.items()
            if key not in {"attestation_digest", "attested_writer_generation", "attested_at"}
        }
        if (
            set(attestation_payload) != durable_attestation_fields
            or attestation_payload.get("schema") != PREACTIVATION_CAUSAL_ATTESTATION_SCHEMA
            or attestation_payload.get("status") != "generation_mismatch_proven"
            or attestation_payload.get("read_method") != "thread/read"
            or attestation_payload.get("causal_read_event_id")
            != evidence["causal_read_event_id"]
            or attestation_payload.get("source_failure_event_id")
            != evidence["source_failure_event_id"]
            or attestation_payload.get("source_followup_event_id")
            != evidence["source_followup_event_id"]
            or attestation_payload.get("thread_id") != evidence["predecessor_thread_id"]
            or attestation_payload.get("turn_status") != "completed"
            or attestation_payload.get("turn_count") != 1
            or attestation_payload.get("observed_identity") != {
                "generation": PREACTIVATION_CAUSAL_REMEDIATION_SOURCE_EXECUTOR_GENERATION,
                "task_id": evidence["task_id"], "workstream_id": evidence["workstream_id"],
            }
            or attestation_payload.get("expected_identity") != {
                "generation": PREACTIVATION_CAUSAL_REMEDIATION_EXPECTED_OUTPUT_GENERATION,
                "task_id": evidence["task_id"], "workstream_id": evidence["workstream_id"],
            }
            or attestation_payload.get("mismatched_fields") != ["generation"]
            or attestation_payload.get("raw_provider_body_stored") is not False
            or attestation_payload.get("attestation_digest")
            != _canonical_mapping_sha256(attestation_base)
            or attestation_payload.get("attested_writer_generation")
            != causal_writer_generation
            or read_payload.get("observed_attestation") != attestation_base
        ):
            raise LocalInstallError(
                "preactivation causal attestation is not the sole generation mismatch"
            )
        _qualification_timestamp(attestation_payload.get("attested_at"))

        remediation_payload = remediation["payload"]
        remediation_fields = {
            "schema", "status", "task_id", "prior_task_revision", "task_revision",
            "workstream_id", "prior_workstream_generation",
            "prior_workstream_revision", "workstream_generation",
            "workstream_revision", "predecessor_executor_generation",
            "successor_executor_generation", "source_pr92_activation_release_sha",
            "source_pr92_expected_head_sha", "activation_release_sha",
            "expected_pr_head_sha", "source_failure_event_id",
            "source_failure_payload_digest", "source_followup_event_id",
            "source_followup_payload_digest", "causal_read_event_id",
            "causal_attestation_event_id", "causal_attestation_digest",
            "replacement_passport_digest", "replacement_workstream_digest",
            "strategy_resource", "strategy_digest", "backup_path", "backup_sha256",
            "successor_event_id", "completion_event_id", "source_model_attempt_count",
            "additional_model_attempt_count", "raw_provider_body_stored",
            "causal_read_claim_count", "causal_read_reclaimed",
            "remediation_writer_generation", "updated_at",
        }
        if (
            set(remediation_payload) != remediation_fields
            or remediation_payload.get("schema") != PREACTIVATION_CAUSAL_REMEDIATION_SCHEMA
            or remediation_payload.get("status") != "successor_reserved"
            or remediation_payload.get("prior_task_revision")
            != PREACTIVATION_CAUSAL_REMEDIATION_SOURCE_TASK_REVISION
            or remediation_payload.get("task_revision")
            != PREACTIVATION_CAUSAL_REMEDIATION_SUCCESSOR_TASK_REVISION
            or remediation_payload.get("prior_workstream_generation")
            != PREACTIVATION_CAUSAL_REMEDIATION_SOURCE_WORKSTREAM_GENERATION
            or remediation_payload.get("prior_workstream_revision")
            != PREACTIVATION_CAUSAL_REMEDIATION_SOURCE_WORKSTREAM_REVISION
            or remediation_payload.get("workstream_generation")
            != PREACTIVATION_CAUSAL_REMEDIATION_SUCCESSOR_WORKSTREAM_GENERATION
            or remediation_payload.get("workstream_revision") != 1
            or remediation_payload.get("predecessor_executor_generation")
            != evidence["predecessor_executor_generation"]
            or remediation_payload.get("successor_executor_generation")
            != evidence["successor_executor_generation"]
            or remediation_payload.get("source_pr92_activation_release_sha")
            != expected_structural_bridge_sha
            or remediation_payload.get("source_pr92_expected_head_sha")
            != PREACTIVATION_CAUSAL_REMEDIATION_PR92_HEAD_SHA
            or remediation_payload.get("activation_release_sha") != expected_sha
            or remediation_payload.get("expected_pr_head_sha")
            != evidence["expected_pr_head_sha"]
            or remediation_payload.get("source_failure_event_id")
            != evidence["source_failure_event_id"]
            or remediation_payload.get("source_failure_payload_digest")
            != evidence["source_failure_event_sha256"]
            or remediation_payload.get("source_followup_event_id")
            != evidence["source_followup_event_id"]
            or remediation_payload.get("source_followup_payload_digest")
            != evidence["source_followup_payload_sha256"]
            or remediation_payload.get("causal_read_event_id")
            != evidence["causal_read_event_id"]
            or remediation_payload.get("causal_attestation_event_id")
            != evidence["causal_attestation_event_id"]
            or remediation_payload.get("causal_attestation_digest")
            != attestation_payload["attestation_digest"]
            or remediation_payload.get("strategy_resource")
            != evidence["strategy_resource"]
            or remediation_payload.get("strategy_digest") != evidence["strategy_digest"]
            or remediation_payload.get("successor_event_id") != evidence["successor_event_id"]
            or remediation_payload.get("completion_event_id") != evidence["completion_event_id"]
            or remediation_payload.get("source_model_attempt_count") != 1
            or remediation_payload.get("additional_model_attempt_count") != 0
            or remediation_payload.get("raw_provider_body_stored") is not False
            or remediation_payload.get("causal_read_claim_count")
            != int(read_row["attempts"])
            or remediation_payload.get("causal_read_reclaimed")
            is not (int(read_row["attempts"]) == 2)
            or remediation_payload.get("remediation_writer_generation")
            != causal_writer_generation
        ):
            raise LocalInstallError(
                "preactivation causal remediation transition binding is invalid"
            )
        backup = Path(os.path.abspath(str(remediation_payload.get("backup_path") or "")))
        if (
            backup
            != root
            / "state"
            / "backups"
            / "supervisor.before-pr93-causal-remediation.sqlite3"
            or _secure_file_sha256(backup) != remediation_payload.get("backup_sha256")
        ):
            raise LocalInstallError(
                "preactivation causal remediation backup binding is invalid"
            )
        backup_before = _private_regular_metadata(backup)
        backup_connection = sqlite3.connect(
            _sqlite_readonly_uri(backup), uri=True, timeout=10
        )
        backup_connection.row_factory = sqlite3.Row
        try:
            backup_connection.execute("PRAGMA query_only = ON")
            backup_connection.execute("BEGIN")
            source_task = backup_connection.execute(
                "SELECT revision,state,writer_generation FROM tasks WHERE task_id=?",
                (evidence["task_id"],),
            ).fetchone()
            source_workstream = backup_connection.execute(
                "SELECT generation,revision,state,is_current,writer_generation FROM workstreams WHERE task_id=? AND workstream_id=? AND is_current=1",
                (evidence["task_id"], evidence["workstream_id"]),
            ).fetchone()
            source_executor = backup_connection.execute(
                "SELECT executor_generation,state,thread_id,host_id FROM executor_bindings WHERE task_id=? AND workstream_id=? AND state='active'",
                (evidence["task_id"], evidence["workstream_id"]),
            ).fetchone()
            backup_failure = backup_connection.execute(
                "SELECT payload_digest FROM events WHERE event_id=? AND event_type='qualification_canary_failed'",
                (evidence["source_failure_event_id"],),
            ).fetchone()
            backup_followup = backup_connection.execute(
                "SELECT payload_digest,state,attempts FROM outbox WHERE event_id=? AND kind='codex_followup'",
                (evidence["source_followup_event_id"],),
            ).fetchone()
            if (
                str(backup_connection.execute("PRAGMA quick_check").fetchone()[0])
                != "ok"
                or backup_connection.execute("PRAGMA foreign_key_check").fetchone()
                is not None
                or source_task is None
                or tuple(source_task)
                != (
                    PREACTIVATION_CAUSAL_REMEDIATION_SOURCE_TASK_REVISION,
                    "waiting_release",
                    PREACTIVATION_CAUSAL_REMEDIATION_EXPECTED_OUTPUT_GENERATION,
                )
                or source_workstream is None
                or tuple(source_workstream)
                != (
                    PREACTIVATION_CAUSAL_REMEDIATION_SOURCE_WORKSTREAM_GENERATION,
                    PREACTIVATION_CAUSAL_REMEDIATION_SOURCE_WORKSTREAM_REVISION,
                    "waiting_release",
                    1,
                    PREACTIVATION_CAUSAL_REMEDIATION_EXPECTED_OUTPUT_GENERATION,
                )
                or source_executor is None
                or tuple(source_executor)
                != (
                    PREACTIVATION_CAUSAL_REMEDIATION_SOURCE_EXECUTOR_GENERATION,
                    "active",
                    evidence["predecessor_thread_id"],
                    evidence["predecessor_host_id"],
                )
                or backup_failure is None
                or backup_failure["payload_digest"]
                != evidence["source_failure_event_sha256"]
                or backup_followup is None
                or tuple(backup_followup)
                != (
                    evidence["source_followup_payload_sha256"],
                    "delivered",
                    1,
                )
                or backup_connection.execute(
                    "SELECT 1 FROM events WHERE event_type IN ('checkpoint','codex_turn_receipt','preactivation_causal_attestation','preactivation_causal_remediation','preactivation_causal_remediation_completed') LIMIT 1"
                ).fetchone()
                is not None
            ):
                raise LocalInstallError(
                    "preactivation causal remediation backup is not the exact PR92 source"
                )
            backup_connection.execute("COMMIT")
        finally:
            backup_connection.close()
        backup_after = _private_regular_metadata(backup)
        if (
            backup_before.st_dev,
            backup_before.st_ino,
            backup_before.st_size,
            backup_before.st_mtime_ns,
        ) != (
            backup_after.st_dev,
            backup_after.st_ino,
            backup_after.st_size,
            backup_after.st_mtime_ns,
        ):
            raise LocalInstallError(
                "preactivation causal remediation backup changed during validation"
            )
        _qualification_timestamp(remediation_payload.get("updated_at"))

        completion_payload = completion["payload"]
        completion_fields = {
            "schema", "status", "remediation_event_id", "causal_read_event_id",
            "causal_attestation_event_id", "successor_event_id", "task_id",
            "task_revision", "workstream_id", "workstream_generation",
            "workstream_revision", "predecessor_executor_generation",
            "successor_executor_generation", "predecessor_thread_id",
            "predecessor_host_id", "successor_thread_id", "successor_host_id",
            "model", "reasoning", "source_pr92_activation_release_sha",
            "source_pr92_expected_head_sha", "activation_release_sha",
            "expected_pr_head_sha", "source_failure_event_id",
            "source_failure_payload_digest", "source_followup_event_id",
            "source_followup_payload_digest", "causal_attestation_digest",
            "replacement_passport_digest", "replacement_workstream_digest",
            "strategy_resource", "strategy_digest", "backup_sha256",
            "app_server_connection_epoch", "same_process_epoch",
            "source_model_attempt_count", "additional_model_attempt_count",
            "causal_read_claim_count", "successor_start_claim_count",
            "successor_start_reclaimed",
            "release_registration_event_id", "release_intake_event_id",
            "completion_writer_generation", "completed_at",
        }
        if (
            set(completion_payload) != completion_fields
            or completion_payload.get("schema") != PREACTIVATION_CAUSAL_COMPLETION_SCHEMA
            or completion_payload.get("status") != "passed"
            or completion_payload.get("remediation_event_id") != evidence["remediation_event_id"]
            or completion_payload.get("causal_read_event_id") != evidence["causal_read_event_id"]
            or completion_payload.get("causal_attestation_event_id")
            != evidence["causal_attestation_event_id"]
            or completion_payload.get("successor_event_id") != evidence["successor_event_id"]
            or completion_payload.get("task_revision")
            != PREACTIVATION_CAUSAL_REMEDIATION_SUCCESSOR_TASK_REVISION
            or completion_payload.get("workstream_generation")
            != PREACTIVATION_CAUSAL_REMEDIATION_SUCCESSOR_WORKSTREAM_GENERATION
            or completion_payload.get("workstream_revision") != 2
            or completion_payload.get("predecessor_executor_generation")
            != evidence["predecessor_executor_generation"]
            or completion_payload.get("successor_executor_generation")
            != evidence["successor_executor_generation"]
            or completion_payload.get("predecessor_thread_id") != evidence["predecessor_thread_id"]
            or completion_payload.get("predecessor_host_id") != evidence["predecessor_host_id"]
            or completion_payload.get("successor_thread_id") != evidence["successor_thread_id"]
            or completion_payload.get("successor_host_id") != evidence["successor_host_id"]
            or completion_payload.get("model") != "gpt-5.6-sol"
            or completion_payload.get("reasoning") != "ultra"
            or completion_payload.get("source_pr92_activation_release_sha")
            != expected_structural_bridge_sha
            or completion_payload.get("source_pr92_expected_head_sha")
            != PREACTIVATION_CAUSAL_REMEDIATION_PR92_HEAD_SHA
            or completion_payload.get("activation_release_sha") != expected_sha
            or completion_payload.get("expected_pr_head_sha") != evidence["expected_pr_head_sha"]
            or completion_payload.get("source_failure_event_id")
            != evidence["source_failure_event_id"]
            or completion_payload.get("source_failure_payload_digest")
            != evidence["source_failure_event_sha256"]
            or completion_payload.get("source_followup_event_id")
            != evidence["source_followup_event_id"]
            or completion_payload.get("source_followup_payload_digest")
            != evidence["source_followup_payload_sha256"]
            or completion_payload.get("causal_attestation_digest")
            != attestation_payload["attestation_digest"]
            or completion_payload.get("strategy_resource")
            != evidence["strategy_resource"]
            or completion_payload.get("strategy_digest") != evidence["strategy_digest"]
            or completion_payload.get("backup_sha256")
            != remediation_payload["backup_sha256"]
            or not _positive_integer(completion_payload.get("app_server_connection_epoch"))
            or completion_payload.get("same_process_epoch") is not True
            or completion_payload.get("source_model_attempt_count") != 1
            or completion_payload.get("additional_model_attempt_count") != 0
            or completion_payload.get("causal_read_claim_count")
            != int(read_row["attempts"])
            or completion_payload.get("successor_start_claim_count")
            != int(successor_row["attempts"])
            or completion_payload.get("successor_start_reclaimed")
            is not (int(successor_row["attempts"]) == 2)
            or completion_payload.get("completion_writer_generation")
            != successor_writer_generation
        ):
            raise LocalInstallError(
                "preactivation causal remediation completion binding is invalid"
            )
        _qualification_timestamp(completion_payload.get("completed_at"))

        restart_payload = (
            restart_attestation["payload"]
            if restart_attestation is not None
            else None
        )
        restart_fields = {
            "schema", "status", "completion_event_id", "task_id",
            "workstream_id", "executor_generation", "thread_id", "host_id",
            "model", "reasoning", "read_method", "resume_method", "turn_count",
            "thread_snapshot_digest", "app_server_connection_epoch",
            "supervisor_generation", "thread_start_performed",
            "model_call_performed", "raw_provider_body_stored",
        }
        if restart_required and (
            not isinstance(restart_payload, Mapping)
            or set(restart_payload) != restart_fields
            or restart_payload.get("schema")
            != PREACTIVATION_CAUSAL_RESTART_ATTESTATION_SCHEMA
            or restart_payload.get("status") != "empty_successor_recovered"
            or restart_payload.get("completion_event_id")
            != evidence["completion_event_id"]
            or restart_payload.get("task_id") != evidence["task_id"]
            or restart_payload.get("workstream_id") != evidence["workstream_id"]
            or restart_payload.get("executor_generation")
            != evidence["successor_executor_generation"]
            or restart_payload.get("thread_id") != evidence["successor_thread_id"]
            or restart_payload.get("host_id") != evidence["successor_host_id"]
            or restart_payload.get("model") != "gpt-5.6-sol"
            or restart_payload.get("reasoning") != "ultra"
            or restart_payload.get("read_method") != "thread/read"
            or restart_payload.get("resume_method") != "thread/resume"
            or restart_payload.get("turn_count") != 0
            or restart_payload.get("thread_snapshot_digest")
            != empty_thread_snapshot_digest
            or not _positive_integer(
                restart_payload.get("app_server_connection_epoch")
            )
            or restart_payload.get("supervisor_generation")
            != canary_writer_generation
            or restart_payload.get("thread_start_performed") is not False
            or restart_payload.get("model_call_performed") is not False
            or restart_payload.get("raw_provider_body_stored") is not False
            or restart_attestation["task_id"] != evidence["task_id"]
            or restart_attestation["workstream_id"] != evidence["workstream_id"]
            or restart_attestation["executor_generation"]
            != evidence["successor_executor_generation"]
            or restart_attestation["writer_generation"]
            != canary_writer_generation
        ):
            raise LocalInstallError(
                "preactivation causal restart attestation binding is invalid"
            )

        if (
            failure["task_id"] != evidence["task_id"]
            or failure["workstream_id"] != evidence["workstream_id"]
            or attestation["executor_generation"] != evidence["predecessor_executor_generation"]
            or remediation["executor_generation"] != evidence["predecessor_executor_generation"]
            or completion["executor_generation"] != evidence["successor_executor_generation"]
            or checkpoint["executor_generation"] != evidence["successor_executor_generation"]
            or receipt["executor_generation"] != evidence["successor_executor_generation"]
            or (
                turn_recovery is not None
                and (
                    turn_recovery["task_id"] != evidence["task_id"]
                    or turn_recovery["workstream_id"]
                    != evidence["workstream_id"]
                    or turn_recovery["executor_generation"]
                    != evidence["successor_executor_generation"]
                    or turn_recovery["writer_generation"]
                    != receipt_writer_generation
                )
            )
            or any(
                item["writer_generation"] != causal_writer_generation
                for item in (attestation, remediation)
            )
            or completion["writer_generation"] != successor_writer_generation
            or checkpoint["writer_generation"]
            != checkpoint_writer_generation
            or receipt["writer_generation"] != receipt_writer_generation
        ):
            raise LocalInstallError(
                "preactivation causal remediation event coordinates changed"
            )

        task_row = connection.execute(
            "SELECT * FROM tasks WHERE task_id = ?", (evidence["task_id"],)
        ).fetchone()
        workstream_row = connection.execute(
            "SELECT * FROM workstreams WHERE task_id = ? AND workstream_id = ? AND is_current = 1",
            (evidence["task_id"], evidence["workstream_id"]),
        ).fetchone()
        active_executor = connection.execute(
            "SELECT * FROM executor_bindings WHERE task_id = ? AND workstream_id = ? AND state = 'active'",
            (evidence["task_id"], evidence["workstream_id"]),
        ).fetchone()
        predecessor_executor = connection.execute(
            "SELECT * FROM executor_bindings WHERE task_id = ? AND workstream_id = ? AND executor_generation = ?",
            (evidence["task_id"], evidence["workstream_id"], evidence["predecessor_executor_generation"]),
        ).fetchone()
        if task_row is None or workstream_row is None or active_executor is None or predecessor_executor is None:
            raise LocalInstallError("preactivation causal remediation current state is incomplete")
        passport_raw = _validated_registry_json_mapping(
            task_row["passport_json"], task_row["passport_digest"],
            label="preactivation causal replacement Passport",
        )
        workstream_raw = _validated_registry_json_mapping(
            workstream_row["contract_json"], workstream_row["contract_digest"],
            label="preactivation causal replacement workstream",
        )
        try:
            passport = task_passport_from_mapping(passport_raw)
            workstream = workstream_from_mapping(workstream_raw)
            validate_workstream_against_passport(workstream, passport)
        except (OrchestrationValidationError, TypeError, ValueError) as exc:
            raise LocalInstallError(
                "preactivation causal replacement contracts are invalid"
            ) from exc
        manifest = passport_raw.get("release_manifest")
        resources = set(passport.resources)
        expected_prs = [
            "github-pr-v1:orenvlad-ai/dev-control-plane:91:"
            + PREACTIVATION_PR91_HEAD_SHA + ":" + expected_root_replacement_sha,
            "github-pr-v1:orenvlad-ai/dev-control-plane:92:"
            + PREACTIVATION_CAUSAL_REMEDIATION_PR92_HEAD_SHA + ":"
            + expected_structural_bridge_sha,
            "github-pr-v1:orenvlad-ai/dev-control-plane:93:"
            + str(evidence["expected_pr_head_sha"]) + ":" + expected_sha,
        ]
        expected_deploys = [
            "hosted-release-v1:wb-core-eu-root:devcontrol.pro:" + sha
            for sha in (expected_root_replacement_sha, expected_structural_bridge_sha, expected_sha)
        ]
        if (
            int(task_row["revision"]) != PREACTIVATION_CAUSAL_REMEDIATION_SUCCESSOR_TASK_REVISION
            or task_row["state"] != "waiting_release"
            or int(task_row["writer_generation"])
            != successor_writer_generation
            or int(workstream_row["generation"])
            != PREACTIVATION_CAUSAL_REMEDIATION_SUCCESSOR_WORKSTREAM_GENERATION
            or int(workstream_row["revision"]) != 2
            or workstream_row["state"] != "waiting_release"
            or workstream.corrective_of_generation
            != PREACTIVATION_CAUSAL_REMEDIATION_SOURCE_WORKSTREAM_GENERATION
            or active_executor["executor_generation"]
            != PREACTIVATION_CAUSAL_REMEDIATION_SUCCESSOR_EXECUTOR_GENERATION
            or active_executor["thread_id"] != evidence["successor_thread_id"]
            or active_executor["host_id"] != evidence["successor_host_id"]
            or int(active_executor["writer_generation"])
            != successor_writer_generation
            or int(workstream_row["writer_generation"])
            != successor_writer_generation
            or predecessor_executor["state"] != "stale"
            or PREACTIVATION_CAUSAL_REMEDIATION_STRATEGY_RESOURCE not in resources
            or sorted(item for item in resources if item.startswith("qualification:"))
            != [f"qualification:{expected_sha}"]
            or not isinstance(manifest, Mapping)
            or manifest.get("pr_identities") != expected_prs
            or manifest.get("deploy_identities") != expected_deploys
        ):
            raise LocalInstallError(
                "preactivation causal replacement lost the PR91/PR92/PR93 chain"
            )
        if (
            remediation_payload.get("replacement_passport_digest") != task_row["passport_digest"]
            or completion_payload.get("replacement_passport_digest") != task_row["passport_digest"]
            or remediation_payload.get("replacement_workstream_digest")
            != contract_digest(workstream_from_mapping({**workstream_raw, "revision": 1, "state": "recovering", "executor": None}))
            or completion_payload.get("replacement_workstream_digest")
            != remediation_payload.get("replacement_workstream_digest")
        ):
            raise LocalInstallError(
                "preactivation causal replacement contract digests changed"
            )

        contract_payload = checkpoint["payload"].get("contract")
        try:
            checkpoint_contract = checkpoint_from_mapping(contract_payload)
        except (OrchestrationValidationError, TypeError, ValueError) as exc:
            raise LocalInstallError("preactivation PR93 checkpoint contract is invalid") from exc
        receipt_payload = receipt["payload"]
        current_call_intent = current_followup.get("call_intent")
        receipt_fields = {
            "schema", "followup_event_id", "contract_event_id",
            "contract_digest", "output_contract", "thread_id", "turn_id",
            "turn_status", "lifecycle_event_count", "lifecycle_digest",
            "lifecycle_methods", "structural_lifecycle_methods",
            "notification_lifecycle_methods", "snapshot_lifecycle_methods",
            "lifecycle_evidence_sources", "item_ids", "terminal_turn_ids",
            "model_attempt_count", "model_call_count",
            "recovery_model_call_count", "receipt_source", "call_policy",
            "transport", "websocket_used", "binary", "model", "reasoning",
            "contract_supervisor_generation", "supervisor_generation",
            "task_revision", "workstream_revision", "executor_generation",
            "created_at",
        }
        receipt_turn_id = receipt_payload.get("turn_id")
        receipt_item_ids = receipt_payload.get("item_ids")
        receipt_lifecycle_methods = receipt_payload.get("lifecycle_methods")
        turn_recovery_payload = (
            turn_recovery["payload"] if turn_recovery is not None else None
        )
        if (
            set(receipt_payload) != receipt_fields
            or checkpoint_contract.task_id != evidence["task_id"]
            or checkpoint_contract.task_revision
            != PREACTIVATION_CAUSAL_REMEDIATION_SUCCESSOR_TASK_REVISION
            or checkpoint_contract.workstream_id != evidence["workstream_id"]
            or checkpoint_contract.workstream_revision != 2
            or checkpoint_contract.executor_generation
            != evidence["successor_executor_generation"]
            or checkpoint_contract.executor.thread_id != evidence["successor_thread_id"]
            or checkpoint_contract.executor.host_id != evidence["successor_host_id"]
            or checkpoint_contract.executor.model != "gpt-5.6-sol"
            or checkpoint_contract.executor.reasoning != "ultra"
            or receipt_payload.get("schema") != "dev-control-plane/codex-turn-receipt/v2"
            or receipt_payload.get("followup_event_id") != evidence["current_followup_event_id"]
            or receipt_payload.get("contract_event_id") != evidence["current_checkpoint_event_id"]
            or receipt_payload.get("contract_digest")
            != _canonical_mapping_sha256(contract_payload)
            or receipt_payload.get("output_contract") != "checkpoint"
            or receipt_payload.get("thread_id") != evidence["successor_thread_id"]
            or not _bounded_evidence_id(receipt_turn_id)
            or receipt_payload.get("turn_status") != "completed"
            or not _positive_integer(receipt_payload.get("lifecycle_event_count"))
            or not _lower_hex(receipt_payload.get("lifecycle_digest"), 64)
            or not isinstance(receipt_item_ids, list)
            or not receipt_item_ids
            or len(set(receipt_item_ids)) != len(receipt_item_ids)
            or any(not _bounded_evidence_id(item) for item in receipt_item_ids)
            or receipt_payload.get("terminal_turn_ids") != [receipt_turn_id]
            or receipt_payload.get("model_attempt_count") != 1
            or receipt_payload.get("model_call_count") != 1
            or receipt_payload.get("recovery_model_call_count") != 0
            or receipt_payload.get("call_policy") != "single_attempt_canary"
            or receipt_payload.get("transport") != "stdio"
            or receipt_payload.get("websocket_used") is not False
            or receipt_payload.get("binary") != DESKTOP_CODEX_BINARY
            or receipt_payload.get("model") != "gpt-5.6-sol"
            or receipt_payload.get("reasoning") != "ultra"
            or receipt_payload.get("contract_supervisor_generation")
            != contract_supervisor_generation
            or receipt_payload.get("contract_supervisor_generation")
            != canary_writer_generation
            or receipt_payload.get("supervisor_generation")
            != receipt_writer_generation
            or receipt_payload.get("task_revision")
            != PREACTIVATION_CAUSAL_REMEDIATION_SUCCESSOR_TASK_REVISION
            or receipt_payload.get("workstream_revision") != 2
            or receipt_payload.get("executor_generation")
            != evidence["successor_executor_generation"]
            or current_followup.get("task_revision")
            != PREACTIVATION_CAUSAL_REMEDIATION_SUCCESSOR_TASK_REVISION
            or current_followup.get("workstream_revision") != 2
            or current_followup.get("executor_generation")
            != evidence["successor_executor_generation"]
            or current_followup.get("thread_id") != evidence["successor_thread_id"]
            or current_followup.get("call_policy") != "single_attempt_canary"
            or current_followup.get("model_attempt_count") != 1
            or not isinstance(current_call_intent, Mapping)
            or current_call_intent.get("supervisor_generation")
            != canary_writer_generation
            or current_call_intent.get("baseline_turn_ids") != []
            or expected_canary.get("turn_ids") != [receipt_turn_id]
            or expected_canary.get("terminal_turn_ids") != [receipt_turn_id]
            or expected_canary.get("item_ids") != receipt_item_ids
            or expected_canary.get("lifecycle_event_count")
            != receipt_payload.get("lifecycle_event_count")
            or expected_canary.get("lifecycle_digest")
            != receipt_payload.get("lifecycle_digest")
        ):
            raise LocalInstallError(
                "preactivation PR93 canary receipt binding is invalid"
            )
        live_turn_receipt_valid = bool(
            turn_receipt_recovered is False
            and turn_recovery is None
            and receipt_payload.get("receipt_source") == "live_notification"
            and checkpoint_writer_generation == canary_writer_generation
            and receipt_writer_generation == canary_writer_generation
            and isinstance(receipt_lifecycle_methods, list)
            and {"turn/started", "turn/completed"}.issubset(
                set(receipt_lifecycle_methods)
            )
        )
        turn_recovery_fields = {
            "schema", "status", "completion_event_id", "followup_event_id",
            "checkpoint_event_id", "turn_receipt_event_id", "task_id",
            "workstream_id", "executor_generation", "thread_id", "turn_id",
            "output_item_id", "thread_snapshot_digest", "contract_digest",
            "contract_supervisor_generation", "recovery_writer_generation",
            "read_method", "turn_count", "model_call_performed",
            "raw_provider_body_stored",
        }
        recovered_turn_receipt_valid = bool(
            turn_receipt_recovered is True
            and isinstance(turn_recovery_payload, Mapping)
            and set(turn_recovery_payload) == turn_recovery_fields
            and receipt_payload.get("receipt_source") == "thread_read_recovery"
            and receipt_writer_generation > canary_writer_generation
            and checkpoint_writer_generation
            in {canary_writer_generation, receipt_writer_generation}
            and receipt_lifecycle_methods == []
            and receipt_payload.get("structural_lifecycle_methods")
            == ["item/completed", "turn/completed"]
            and receipt_payload.get("notification_lifecycle_methods") == []
            and receipt_payload.get("snapshot_lifecycle_methods")
            == ["item/completed", "turn/completed"]
            and receipt_payload.get("lifecycle_evidence_sources")
            == ["thread_read_snapshot"]
            and receipt_payload.get("lifecycle_event_count") == 2
            and len(receipt_item_ids) == 1
            and turn_recovery_payload.get("schema")
            == PREACTIVATION_CAUSAL_TURN_RECOVERY_SCHEMA
            and turn_recovery_payload.get("status") == "recovered"
            and turn_recovery_payload.get("completion_event_id")
            == evidence["completion_event_id"]
            and turn_recovery_payload.get("followup_event_id")
            == evidence["current_followup_event_id"]
            and turn_recovery_payload.get("checkpoint_event_id")
            == evidence["current_checkpoint_event_id"]
            and turn_recovery_payload.get("turn_receipt_event_id")
            == evidence["current_turn_receipt_event_id"]
            and turn_recovery_payload.get("task_id") == evidence["task_id"]
            and turn_recovery_payload.get("workstream_id")
            == evidence["workstream_id"]
            and turn_recovery_payload.get("executor_generation")
            == evidence["successor_executor_generation"]
            and turn_recovery_payload.get("thread_id")
            == evidence["successor_thread_id"]
            and turn_recovery_payload.get("turn_id") == receipt_turn_id
            and turn_recovery_payload.get("output_item_id") in receipt_item_ids
            and turn_recovery_payload.get("contract_digest")
            == receipt_payload.get("contract_digest")
            and turn_recovery_payload.get("contract_supervisor_generation")
            == canary_writer_generation
            and turn_recovery_payload.get("recovery_writer_generation")
            == receipt_writer_generation
            and turn_recovery_payload.get("read_method") == "thread/read"
            and turn_recovery_payload.get("turn_count") == 1
            and _lower_hex(
                turn_recovery_payload.get("thread_snapshot_digest"), 64
            )
            and turn_recovery_payload.get("model_call_performed") is False
            and turn_recovery_payload.get("raw_provider_body_stored") is False
        )
        if not (live_turn_receipt_valid or recovered_turn_receipt_valid):
            raise LocalInstallError(
                "preactivation PR93 canary turn recovery binding is invalid"
            )
        _qualification_timestamp(receipt_payload.get("created_at"))

        read_fields = {
            "schema", "task_id", "task_revision", "workstream_id",
            "workstream_generation", "workstream_revision",
            "executor_generation", "thread_id", "host_id",
            "source_failure_event_id", "source_failure_payload_digest",
            "source_followup_event_id", "source_followup_payload_digest",
            "source_call_intent_digest", "observed_generation",
            "expected_supervisor_generation", "activation_release_sha",
            "expected_pr_head_sha", "backup_path", "backup_sha256",
            "strategy_digest", "justification_digest", "replacement_passport",
            "corrective_workstream", "replacement_passport_digest",
            "replacement_workstream_digest", "causal_read_event_id",
            "causal_attestation_event_id", "remediation_event_id",
            "successor_event_id", "completion_event_id", "projection_event_id",
            "successor_payload", "read_intent", "observed_attestation",
        }
        successor_fields = {
            "schema", "task_id", "task_revision", "workstream_id",
            "workstream_generation", "workstream_revision",
            "predecessor_generation", "successor_generation", "cwd",
            "source_pr92_activation_release_sha",
            "source_pr92_expected_head_sha", "activation_release_sha",
            "expected_pr_head_sha", "causal_read_event_id",
            "causal_attestation_event_id", "remediation_event_id",
            "completion_event_id", "source_failure_event_id",
            "source_followup_event_id", "replacement_passport_digest",
            "replacement_workstream_digest", "strategy_digest", "start_intent",
            "started_thread",
        }
        read_intent = read_payload.get("read_intent")
        successor_start_intent = successor_payload.get("start_intent")
        started_thread = successor_payload.get("started_thread")
        expected_corrective_workstream = {
            **workstream_raw,
            "revision": 1,
            "state": "recovering",
            "executor": None,
        }
        reserved_successor_payload = dict(successor_payload)
        reserved_successor_payload.update(
            {"start_intent": None, "started_thread": None}
        )
        if (
            set(read_payload) != read_fields
            or read_payload.get("schema")
            != "dev-control-plane/codex-preactivation-causal-read/v3"
            or read_payload.get("task_id") != evidence["task_id"]
            or read_payload.get("task_revision")
            != PREACTIVATION_CAUSAL_REMEDIATION_SOURCE_TASK_REVISION
            or read_payload.get("workstream_id") != evidence["workstream_id"]
            or read_payload.get("workstream_generation")
            != PREACTIVATION_CAUSAL_REMEDIATION_SOURCE_WORKSTREAM_GENERATION
            or read_payload.get("workstream_revision")
            != PREACTIVATION_CAUSAL_REMEDIATION_SOURCE_WORKSTREAM_REVISION
            or read_payload.get("executor_generation")
            != evidence["predecessor_executor_generation"]
            or read_payload.get("thread_id") != evidence["predecessor_thread_id"]
            or read_payload.get("host_id") != evidence["predecessor_host_id"]
            or read_payload.get("source_failure_event_id")
            != evidence["source_failure_event_id"]
            or read_payload.get("source_failure_payload_digest")
            != evidence["source_failure_event_sha256"]
            or read_payload.get("source_followup_event_id")
            != evidence["source_followup_event_id"]
            or read_payload.get("source_followup_payload_digest")
            != evidence["source_followup_payload_sha256"]
            or read_payload.get("source_call_intent_digest")
            != _canonical_mapping_sha256(source_intent)
            or read_payload.get("observed_generation")
            != PREACTIVATION_CAUSAL_REMEDIATION_SOURCE_EXECUTOR_GENERATION
            or read_payload.get("expected_supervisor_generation")
            != PREACTIVATION_CAUSAL_REMEDIATION_EXPECTED_OUTPUT_GENERATION
            or read_payload.get("activation_release_sha") != expected_sha
            or read_payload.get("expected_pr_head_sha")
            != evidence["expected_pr_head_sha"]
            or Path(os.path.abspath(str(read_payload.get("backup_path") or "")))
            != backup
            or read_payload.get("backup_sha256")
            != remediation_payload["backup_sha256"]
            or read_payload.get("strategy_digest") != evidence["strategy_digest"]
            or not _lower_hex(read_payload.get("justification_digest"), 64)
            or read_payload.get("replacement_passport") != passport_raw
            or read_payload.get("corrective_workstream")
            != expected_corrective_workstream
            or read_payload.get("replacement_passport_digest")
            != task_row["passport_digest"]
            or read_payload.get("replacement_workstream_digest")
            != remediation_payload["replacement_workstream_digest"]
            or read_payload.get("causal_read_event_id")
            != evidence["causal_read_event_id"]
            or read_payload.get("causal_attestation_event_id")
            != evidence["causal_attestation_event_id"]
            or read_payload.get("remediation_event_id")
            != evidence["remediation_event_id"]
            or read_payload.get("successor_event_id")
            != evidence["successor_event_id"]
            or read_payload.get("completion_event_id")
            != evidence["completion_event_id"]
            or not _bounded_evidence_id(read_payload.get("projection_event_id"))
            or read_payload.get("successor_payload") != reserved_successor_payload
            or not isinstance(read_intent, Mapping)
            or set(read_intent) != {"supervisor_generation", "started_at"}
            or read_intent.get("supervisor_generation")
            != causal_writer_generation
            or read_payload.get("observed_attestation") != attestation_base
            or set(successor_payload) != successor_fields
            or successor_payload.get("schema")
            != "dev-control-plane/codex-preactivation-causal-successor-start/v3"
            or successor_payload.get("task_id") != evidence["task_id"]
            or successor_payload.get("task_revision")
            != PREACTIVATION_CAUSAL_REMEDIATION_SUCCESSOR_TASK_REVISION
            or successor_payload.get("workstream_id") != evidence["workstream_id"]
            or successor_payload.get("workstream_generation")
            != PREACTIVATION_CAUSAL_REMEDIATION_SUCCESSOR_WORKSTREAM_GENERATION
            or successor_payload.get("workstream_revision") != 1
            or successor_payload.get("predecessor_generation")
            != evidence["predecessor_executor_generation"]
            or successor_payload.get("successor_generation")
            != evidence["successor_executor_generation"]
            or successor_payload.get("cwd") != source_followup.get("cwd")
            or successor_payload.get("source_pr92_activation_release_sha")
            != expected_structural_bridge_sha
            or successor_payload.get("source_pr92_expected_head_sha")
            != PREACTIVATION_CAUSAL_REMEDIATION_PR92_HEAD_SHA
            or successor_payload.get("activation_release_sha") != expected_sha
            or successor_payload.get("expected_pr_head_sha")
            != evidence["expected_pr_head_sha"]
            or successor_payload.get("causal_read_event_id")
            != evidence["causal_read_event_id"]
            or successor_payload.get("causal_attestation_event_id")
            != evidence["causal_attestation_event_id"]
            or successor_payload.get("remediation_event_id")
            != evidence["remediation_event_id"]
            or successor_payload.get("completion_event_id")
            != evidence["completion_event_id"]
            or successor_payload.get("source_failure_event_id")
            != evidence["source_failure_event_id"]
            or successor_payload.get("source_followup_event_id")
            != evidence["source_followup_event_id"]
            or successor_payload.get("replacement_passport_digest")
            != task_row["passport_digest"]
            or successor_payload.get("replacement_workstream_digest")
            != remediation_payload["replacement_workstream_digest"]
            or successor_payload.get("strategy_digest") != evidence["strategy_digest"]
            or not isinstance(successor_start_intent, Mapping)
            or set(successor_start_intent)
            != {
                "supervisor_generation", "started_at",
                "app_server_connection_epoch",
            }
            or successor_start_intent.get("supervisor_generation")
            != successor_writer_generation
            or successor_start_intent.get("app_server_connection_epoch")
            != completion_payload["app_server_connection_epoch"]
            or not isinstance(started_thread, Mapping)
            or set(started_thread)
            != {"thread_id", "session_id", "host_id", "model", "reasoning", "ephemeral"}
            or started_thread.get("thread_id") != evidence["successor_thread_id"]
            or not _bounded_evidence_id(started_thread.get("session_id"))
            or started_thread.get("host_id") != evidence["successor_host_id"]
            or started_thread.get("model") != "gpt-5.6-sol"
            or started_thread.get("reasoning") != "ultra"
            or started_thread.get("ephemeral") is not False
        ):
            raise LocalInstallError(
                "preactivation causal read/successor binding is invalid"
            )
        _qualification_timestamp(read_intent.get("started_at"))
        _qualification_timestamp(successor_start_intent.get("started_at"))

        _validate_preactivation_structural_release_intake(
            connection,
            completion_payload=completion_payload,
            activation_release_sha=expected_sha,
            expected_pr_head_sha=str(evidence["expected_pr_head_sha"]),
            task_id=str(evidence["task_id"]),
            workstream_id=str(evidence["workstream_id"]),
            expected_supervisor_generation=successor_writer_generation,
            expected_processing_generation=admission_writer_generation,
            current_state={"passport": passport},
            expected_pr_number=93,
        )
        connection.execute("COMMIT")
    finally:
        connection.close()
    after = _private_regular_metadata(database)
    if (
        before.st_dev, before.st_ino, before.st_uid, before.st_mode, before.st_nlink
    ) != (
        after.st_dev, after.st_ino, after.st_uid, after.st_mode, after.st_nlink
    ) or require_fresh and (
        before.st_size, before.st_mtime_ns
    ) != (
        after.st_size, after.st_mtime_ns
    ):
        raise LocalInstallError(
            "preactivation causal remediation registry changed during validation"
        )
    if boundary_recheck is not None:
        boundary_recheck()


def _preactivation_registry_event(
    connection: sqlite3.Connection,
    *,
    event_id: str,
    event_type: str,
    expected_digest: str | None,
) -> dict[str, Any]:
    row = connection.execute(
        """
        SELECT event_id,event_type,payload_json,payload_digest,task_id,
               workstream_id,executor_generation,writer_generation
        FROM events WHERE event_id = ?
        """,
        (event_id,),
    ).fetchone()
    if row is None or row["event_type"] != event_type:
        raise LocalInstallError(
            "preactivation remediation durable event is missing or mistyped"
        )
    try:
        payload = json.loads(str(row["payload_json"]))
    except json.JSONDecodeError as exc:
        raise LocalInstallError(
            "preactivation remediation durable event is invalid JSON"
        ) from exc
    digest = _canonical_mapping_sha256(payload)
    if (
        not isinstance(payload, Mapping)
        or row["payload_digest"] != digest
        or (expected_digest is not None and digest != expected_digest)
    ):
        raise LocalInstallError(
            "preactivation remediation durable event digest changed"
        )
    return {
        "payload": dict(payload),
        "task_id": row["task_id"],
        "workstream_id": row["workstream_id"],
        "executor_generation": row["executor_generation"],
        "writer_generation": int(row["writer_generation"]),
    }


def _validate_preactivation_structural_repair_payload(
    payload: Mapping[str, Any],
    *,
    expected_sha: str,
    evidence: Mapping[str, Any],
    runtime_root: Path,
    qualification_created_at: datetime,
    validation_now: datetime,
    require_fresh: bool,
) -> dict[str, Any]:
    fields = {
        "schema", "status", "task_id", "workstream_id", "prior_task_revision",
        "task_revision", "prior_workstream_generation",
        "prior_workstream_revision", "workstream_generation",
        "workstream_revision", "predecessor_executor_generation",
        "successor_executor_generation", "activation_release_sha",
        "expected_pr_head_sha", "replacement_passport_digest",
        "replacement_workstream_digest", "backup_path", "backup_sha256",
        "successor_event_id", "completion_event_id",
        "superseded_outbox_count", "superseded_attention_event_ids",
        "resolved_causal_fingerprints", "model_attempt_count",
        "model_call_count", "real_model_calls", "structural_thread_start_only",
        "justification_digest", "updated_at",
    }
    if set(payload) != fields:
        raise LocalInstallError(
            "preactivation structural repair event fields are invalid"
        )
    prior_task_revision = payload.get("prior_task_revision")
    task_revision = payload.get("task_revision")
    prior_workstream_generation = payload.get("prior_workstream_generation")
    workstream_generation = payload.get("workstream_generation")
    prior_workstream_revision = payload.get("prior_workstream_revision")
    workstream_revision = payload.get("workstream_revision")
    predecessor = payload.get("predecessor_executor_generation")
    successor = payload.get("successor_executor_generation")
    if (
        payload.get("schema") != PREACTIVATION_STRUCTURAL_REPAIR_SCHEMA
        or payload.get("status") != "successor_reserved"
        or payload.get("task_id") != evidence["task_id"]
        or payload.get("workstream_id") != evidence["workstream_id"]
        or not _positive_integer(prior_task_revision)
        or task_revision != int(prior_task_revision) + 1
        or not _positive_integer(prior_workstream_generation)
        or workstream_generation != int(prior_workstream_generation) + 1
        or not _positive_integer(prior_workstream_revision)
        or workstream_revision != 1
        or predecessor != evidence["predecessor_executor_generation"]
        or successor != evidence["successor_executor_generation"]
        or payload.get("activation_release_sha") != expected_sha
        or payload.get("expected_pr_head_sha")
        != evidence["expected_pr_head_sha"]
        or payload.get("completion_event_id") != evidence["completion_event_id"]
        or payload.get("model_attempt_count") != 0
        or payload.get("model_call_count") != 0
        or payload.get("real_model_calls") != 0
        or payload.get("structural_thread_start_only") is not True
    ):
        raise LocalInstallError(
            "preactivation structural repair event binding is invalid"
        )
    for field in (
        "replacement_passport_digest", "replacement_workstream_digest",
        "backup_sha256", "justification_digest",
    ):
        if not _lower_hex(payload.get(field), 64):
            raise LocalInstallError(
                f"preactivation structural repair {field} is invalid"
            )
    for field in ("successor_event_id", "completion_event_id"):
        if not _bounded_evidence_id(payload.get(field)):
            raise LocalInstallError(
                f"preactivation structural repair {field} is invalid"
            )
    superseded_count = payload.get("superseded_outbox_count")
    attention_ids = payload.get("superseded_attention_event_ids")
    fingerprints = payload.get("resolved_causal_fingerprints")
    if (
        isinstance(superseded_count, bool)
        or not isinstance(superseded_count, int)
        or superseded_count < 0
        or not isinstance(attention_ids, list)
        or not attention_ids
        or attention_ids != sorted(set(attention_ids))
        or any(not _bounded_evidence_id(item) for item in attention_ids)
        or not isinstance(fingerprints, list)
        or not fingerprints
        or fingerprints != sorted(set(fingerprints))
        or any(not _lower_hex(item, 64) for item in fingerprints)
    ):
        raise LocalInstallError(
            "preactivation structural repair resolution set is invalid"
        )
    backup = Path(os.path.abspath(str(payload.get("backup_path") or "")))
    backup_root = runtime_root / "state" / "backups"
    if backup.parent != backup_root or _secure_file_sha256(backup) != payload["backup_sha256"]:
        raise LocalInstallError(
            "preactivation structural repair backup binding is invalid"
        )
    updated_at = _qualification_timestamp(payload.get("updated_at"))
    _validate_evidence_time(
        updated_at,
        qualification_created_at=qualification_created_at,
        validation_now=validation_now,
        require_fresh=require_fresh,
        label="preactivation structural repair",
    )
    return _validate_preactivation_structural_backup(
        backup,
        repair_payload=payload,
        evidence=evidence,
    )


def _validate_preactivation_structural_backup(
    backup: Path,
    *,
    repair_payload: Mapping[str, Any],
    evidence: Mapping[str, Any],
) -> dict[str, Any]:
    before = _private_regular_metadata(backup)
    connection = sqlite3.connect(_sqlite_readonly_uri(backup), uri=True, timeout=10)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only = ON")
        connection.execute("BEGIN")
        if str(connection.execute("PRAGMA integrity_check").fetchone()[0]) != "ok":
            raise LocalInstallError(
                "preactivation structural repair backup integrity failed"
            )
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise LocalInstallError(
                "preactivation structural repair backup foreign keys changed"
            )
        versions = tuple(
            int(row[0])
            for row in connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
        )
        lease = connection.execute(
            "SELECT * FROM supervisor_lease WHERE singleton = 1"
        ).fetchone()
        if (
            int(connection.execute("PRAGMA user_version").fetchone()[0]) != 3
            or versions != (1, 2, 3)
            or lease is None
            or not _positive_integer(int(lease["generation"]))
        ):
            raise LocalInstallError(
                "preactivation structural repair backup schema/fence differs"
            )
        table_counts = _sqlite_table_counts(connection)
        if set(table_counts) != set(_PREACTIVATION_SOURCE_TABLE_COUNTS):
            raise LocalInstallError(
                "preactivation structural repair backup schema differs"
            )
        singleton = (
            table_counts["tasks"],
            int(
                connection.execute(
                    "SELECT COUNT(*) FROM workstreams WHERE is_current = 1"
                ).fetchone()[0]
            ),
            table_counts["executor_bindings"],
        )
        if singleton != (1, 1, 1):
            raise LocalInstallError(
                "preactivation structural repair backup is not the singleton parked PR91 aggregate"
            )
        task = connection.execute(
            "SELECT * FROM tasks WHERE task_id = ?",
            (evidence["task_id"],),
        ).fetchone()
        workstream = connection.execute(
            """
            SELECT * FROM workstreams
            WHERE task_id = ? AND workstream_id = ? AND is_current = 1
            """,
            (evidence["task_id"], evidence["workstream_id"]),
        ).fetchone()
        executor = connection.execute(
            """
            SELECT * FROM executor_bindings
            WHERE task_id = ? AND workstream_id = ? AND state = 'active'
            """,
            (evidence["task_id"], evidence["workstream_id"]),
        ).fetchone()
        workspace = connection.execute(
            """
            SELECT * FROM workspace_bindings
            WHERE task_id = ? AND workstream_id = ?
            """,
            (evidence["task_id"], evidence["workstream_id"]),
        ).fetchone()
        if (
            task is None
            or int(task["revision"]) != repair_payload["prior_task_revision"]
            or task["state"] != "parked"
            or workstream is None
            or int(workstream["generation"])
            != repair_payload["prior_workstream_generation"]
            or int(workstream["revision"])
            != repair_payload["prior_workstream_revision"]
            or workstream["state"] != "parked"
            or int(workstream["is_current"]) != 1
            or executor is None
            or int(executor["executor_generation"])
            != repair_payload["predecessor_executor_generation"]
            or executor["thread_id"] != evidence["predecessor_thread_id"]
            or executor["host_id"] != evidence["predecessor_host_id"]
            or executor["model"] != "gpt-5.6-sol"
            or executor["reasoning"] != "ultra"
            or executor["proof_event_id"] is not None
            or workspace is None
            or not isinstance(workspace["canonical_path"], str)
            or not str(workspace["canonical_path"]).startswith("/")
            or hashlib.sha256(
                str(workspace["canonical_path"]).encode("utf-8")
            ).hexdigest()
            != workspace["path_digest"]
        ):
            raise LocalInstallError(
                "preactivation structural repair backup parked binding differs"
            )
        for table in ("events", "inbox", "outbox"):
            for row in connection.execute(
                f'SELECT payload_json,payload_digest FROM "{table}"'
            ):
                _validated_registry_json_mapping(
                    row["payload_json"],
                    row["payload_digest"],
                    label=f"preactivation structural repair backup {table} row",
                )
        passport_raw = _validated_registry_json_mapping(
            task["passport_json"],
            task["passport_digest"],
            label="preactivation structural repair backup Passport",
        )
        workstream_raw = _validated_registry_json_mapping(
            workstream["contract_json"],
            workstream["contract_digest"],
            label="preactivation structural repair backup workstream",
        )
        passport_normalized = _normalize_preactivation_legacy_target(
            passport_raw,
            label="preactivation structural repair backup Passport",
        )
        workstream_normalized = _normalize_preactivation_legacy_target(
            workstream_raw,
            label="preactivation structural repair backup workstream",
        )
        try:
            predecessor_passport = task_passport_from_mapping(passport_normalized)
            predecessor_workstream = workstream_from_mapping(workstream_normalized)
            validate_workstream_against_passport(
                predecessor_workstream,
                predecessor_passport,
            )
        except (OrchestrationValidationError, TypeError, ValueError) as exc:
            raise LocalInstallError(
                "preactivation structural repair backup contracts are invalid"
            ) from exc
        manifest = passport_raw.get("release_manifest")
        resources = passport_raw.get("resources")
        if (
            passport_raw.get("task_id") != evidence["task_id"]
            or passport_raw.get("revision") != repair_payload["prior_task_revision"]
            or passport_raw.get("workstream_ids") != [evidence["workstream_id"]]
            or passport_raw.get("multi_pr_intent") is not False
            or passport_raw.get("multi_deploy_intent") is not False
            or not isinstance(resources, list)
            or resources.count("target:dev-control-plane") != 1
            or any(
                isinstance(item, str)
                and item.startswith("qualification:")
                for item in resources
            )
            or not isinstance(manifest, Mapping)
            or manifest.get("pr_identities")
            != [
                "github-pr-v1:orenvlad-ai/dev-control-plane:91:"
                + PREACTIVATION_PR91_HEAD_SHA
                + ":"
                + PREACTIVATION_STRUCTURAL_REPAIR_PREDECESSOR_SHA
            ]
            or manifest.get("deploy_identities")
            != [
                "hosted-release-v1:wb-core-eu-root:devcontrol.pro:"
                + PREACTIVATION_STRUCTURAL_REPAIR_PREDECESSOR_SHA
            ]
        ):
            raise LocalInstallError(
                "preactivation structural repair backup is not exact PR91"
            )
        forbidden_events = (
            "checkpoint",
            "codex_turn_receipt",
            "technical_terminal",
            "owner_accepted",
            "owner_acceptance",
            "qualification_canary_failed",
            PREACTIVATION_STRUCTURAL_REPAIR_EVENT_TYPE,
            PREACTIVATION_STRUCTURAL_REPAIR_COMPLETION_EVENT_TYPE,
        )
        placeholders = ",".join("?" for _ in forbidden_events)
        if connection.execute(
            f"SELECT 1 FROM events WHERE event_type IN ({placeholders}) LIMIT 1",
            forbidden_events,
        ).fetchone() is not None or connection.execute(
            """
            SELECT 1 FROM outbox
            WHERE kind IN (
                'codex_followup','codex_successor_start',
                'codex_preactivation_successor_start','release_action'
            ) LIMIT 1
            """
        ).fetchone() is not None:
            raise LocalInstallError(
                "preactivation structural repair backup already consumed a model or release action"
            )
        starts = connection.execute(
            "SELECT state,attempts FROM outbox WHERE kind = 'codex_thread_start'"
        ).fetchall()
        if (
            len(starts) != 1
            or starts[0]["state"] != "delivered"
            or int(starts[0]["attempts"]) != 1
            or connection.execute(
                "SELECT 1 FROM outbox WHERE state = 'inflight' LIMIT 1"
            ).fetchone()
            is not None
        ):
            raise LocalInstallError(
                "preactivation structural repair backup executor budget differs"
            )
        attention_ids = [
            str(row[0])
            for row in connection.execute(
                """
                SELECT event_id FROM outbox
                WHERE task_id = ? AND kind = 'curator_attention'
                    AND state IN ('pending','delivered')
                ORDER BY event_id
                """,
                (evidence["task_id"],),
            )
        ]
        policy_placeholders = ",".join(
            "?" for _ in PREACTIVATION_ORDINARY_POLICY_OUTBOX_KINDS
        )
        pending_count = int(
            connection.execute(
                f"""
                SELECT COUNT(*) FROM outbox
                WHERE state = 'pending' AND (
                    task_id = ? OR kind IN ({policy_placeholders})
                )
                """,
                (
                    evidence["task_id"],
                    *PREACTIVATION_ORDINARY_POLICY_OUTBOX_KINDS,
                ),
            ).fetchone()[0]
        )
        incident_fingerprints: set[str] = set()
        for row in connection.execute(
            """
            SELECT payload_json,payload_digest FROM events
            WHERE task_id = ? AND workstream_id = ?
                AND event_type = 'incident_policy'
            """,
            (evidence["task_id"], evidence["workstream_id"]),
        ):
            incident = _validated_registry_json_mapping(
                row["payload_json"],
                row["payload_digest"],
                label="preactivation structural repair backup incident",
            )
            fingerprint = incident.get("fingerprint")
            if _lower_hex(fingerprint, 64):
                incident_fingerprints.add(str(fingerprint))
        if (
            attention_ids
            != repair_payload["superseded_attention_event_ids"]
            or pending_count != repair_payload["superseded_outbox_count"]
            or sorted(incident_fingerprints)
            != repair_payload["resolved_causal_fingerprints"]
        ):
            raise LocalInstallError(
                "preactivation structural repair backup resolution set differs"
            )
        connection.execute("COMMIT")
    finally:
        connection.close()
    after = _private_regular_metadata(backup)
    if (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    ) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ):
        raise LocalInstallError(
            "preactivation structural repair backup changed during validation"
        )
    return {
        "passport": passport_raw,
        "workstream": workstream_raw,
        "workspace": str(workspace["canonical_path"]),
        "supervisor_generation": int(lease["generation"]),
    }


def _validated_registry_json_mapping(
    raw: Any,
    expected_digest: Any,
    *,
    label: str,
) -> dict[str, Any]:
    if not isinstance(raw, str):
        raise LocalInstallError(f"{label} is not serialized JSON")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LocalInstallError(f"{label} is invalid JSON") from exc
    if (
        not isinstance(payload, Mapping)
        or raw
        != json.dumps(
            dict(payload),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        or hashlib.sha256(raw.encode("utf-8")).hexdigest() != expected_digest
    ):
        raise LocalInstallError(f"{label} digest or canonical form changed")
    return dict(payload)


def _normalize_preactivation_legacy_target(
    payload: Mapping[str, Any],
    *,
    label: str,
) -> dict[str, Any]:
    normalized = json.loads(json.dumps(dict(payload)))
    resources = normalized.get("resources")
    if not isinstance(resources, list) or resources.count("target:dev-control-plane") != 1:
        raise LocalInstallError(f"{label} lacks the unique deprecated PR91 target")
    normalized["resources"] = [
        (
            f"target:{PREACTIVATION_STRUCTURAL_REPAIR_CANONICAL_TARGET}"
            if item == "target:dev-control-plane"
            else item
        )
        for item in resources
    ]
    return normalized


def _validate_preactivation_structural_completion_payload(
    payload: Mapping[str, Any],
    *,
    expected_sha: str,
    evidence: Mapping[str, Any],
    repair_payload: Mapping[str, Any],
    qualification_created_at: datetime,
    validation_now: datetime,
    require_fresh: bool,
) -> None:
    fields = {
        "schema", "status", "repair_event_id", "successor_event_id", "task_id",
        "workstream_id", "task_revision", "workstream_generation",
        "workstream_revision", "predecessor_executor_generation",
        "successor_executor_generation", "predecessor_thread_id",
        "predecessor_host_id", "successor_thread_id", "successor_host_id",
        "model", "reasoning", "activation_release_sha", "expected_pr_head_sha",
        "replacement_passport_digest", "replacement_workstream_digest",
        "app_server_connection_epoch", "same_process_epoch",
        "structural_thread_start_only", "model_attempt_count", "model_call_count",
        "real_model_calls", "release_registration_event_id",
        "release_intake_event_id", "completed_at",
    }
    if set(payload) != fields:
        raise LocalInstallError(
            "preactivation structural repair completion fields are invalid"
        )
    if (
        payload.get("schema")
        != PREACTIVATION_STRUCTURAL_REPAIR_COMPLETION_SCHEMA
        or payload.get("status") != "passed"
        or payload.get("repair_event_id") != evidence["repair_event_id"]
        or payload.get("successor_event_id") != repair_payload["successor_event_id"]
        or payload.get("task_id") != evidence["task_id"]
        or payload.get("workstream_id") != evidence["workstream_id"]
        or payload.get("task_revision") != repair_payload["task_revision"]
        or payload.get("workstream_generation")
        != repair_payload["workstream_generation"]
        or payload.get("workstream_revision") != 2
        or payload.get("predecessor_executor_generation")
        != evidence["predecessor_executor_generation"]
        or payload.get("successor_executor_generation")
        != evidence["successor_executor_generation"]
        or payload.get("predecessor_thread_id") != evidence["predecessor_thread_id"]
        or payload.get("predecessor_host_id") != evidence["predecessor_host_id"]
        or payload.get("successor_thread_id") != evidence["successor_thread_id"]
        or payload.get("successor_host_id") != evidence["successor_host_id"]
        or payload.get("model") != "gpt-5.6-sol"
        or payload.get("reasoning") != "ultra"
        or payload.get("activation_release_sha") != expected_sha
        or payload.get("expected_pr_head_sha")
        != evidence["expected_pr_head_sha"]
        or payload.get("replacement_passport_digest")
        != repair_payload["replacement_passport_digest"]
        or payload.get("replacement_workstream_digest")
        != repair_payload["replacement_workstream_digest"]
        or not _positive_integer(payload.get("app_server_connection_epoch"))
        or payload.get("same_process_epoch") is not True
        or payload.get("structural_thread_start_only") is not True
        or payload.get("model_attempt_count") != 0
        or payload.get("model_call_count") != 0
        or payload.get("real_model_calls") != 0
    ):
        raise LocalInstallError(
            "preactivation structural repair completion binding is invalid"
        )
    for field in ("release_registration_event_id", "release_intake_event_id"):
        if not _bounded_evidence_id(payload.get(field)):
            raise LocalInstallError(
                f"preactivation structural repair completion {field} is invalid"
            )
    completed_at = _qualification_timestamp(payload.get("completed_at"))
    _validate_evidence_time(
        completed_at,
        qualification_created_at=qualification_created_at,
        validation_now=validation_now,
        require_fresh=require_fresh,
        label="preactivation structural repair completion",
    )


def _validate_preactivation_structural_successor_outbox(
    connection: sqlite3.Connection,
    *,
    repair_payload: Mapping[str, Any],
    completion_payload: Mapping[str, Any],
    evidence: Mapping[str, Any],
    expected_supervisor_generation: int,
) -> None:
    rows = connection.execute(
        """
        SELECT event_id,kind,payload_json,payload_digest,state,task_id
        FROM outbox WHERE kind = ?
        """,
        (PREACTIVATION_STRUCTURAL_SUCCESSOR_KIND,),
    ).fetchall()
    if len(rows) != 1:
        raise LocalInstallError(
            "preactivation structural successor outbox is not unique"
        )
    row = rows[0]
    try:
        payload = json.loads(str(row["payload_json"]))
    except json.JSONDecodeError as exc:
        raise LocalInstallError(
            "preactivation structural successor outbox is invalid JSON"
        ) from exc
    fields = {
        "schema", "task_id", "task_revision", "workstream_id",
        "workstream_generation", "workstream_revision", "predecessor_generation",
        "successor_generation", "cwd", "activation_release_sha",
        "expected_pr_head_sha", "repair_event_id", "completion_event_id",
        "replacement_passport_digest", "replacement_workstream_digest",
        "start_intent", "started_thread",
    }
    start_intent = payload.get("start_intent") if isinstance(payload, Mapping) else None
    started = payload.get("started_thread") if isinstance(payload, Mapping) else None
    if (
        not isinstance(payload, Mapping)
        or set(payload) != fields
        or row["event_id"] != repair_payload["successor_event_id"]
        or row["kind"] != PREACTIVATION_STRUCTURAL_SUCCESSOR_KIND
        or row["state"] != "delivered"
        or row["task_id"] != evidence["task_id"]
        or row["payload_digest"] != _canonical_mapping_sha256(payload)
        or payload.get("schema")
        != "dev-control-plane/codex-preactivation-successor-start/v2"
        or payload.get("task_id") != evidence["task_id"]
        or payload.get("task_revision") != repair_payload["task_revision"]
        or payload.get("workstream_id") != evidence["workstream_id"]
        or payload.get("workstream_generation")
        != repair_payload["workstream_generation"]
        or payload.get("workstream_revision") != repair_payload["workstream_revision"]
        or payload.get("predecessor_generation")
        != evidence["predecessor_executor_generation"]
        or payload.get("successor_generation")
        != evidence["successor_executor_generation"]
        or payload.get("activation_release_sha")
        != evidence["activation_release_sha"]
        or payload.get("expected_pr_head_sha")
        != evidence["expected_pr_head_sha"]
        or payload.get("repair_event_id") != evidence["repair_event_id"]
        or payload.get("completion_event_id") != evidence["completion_event_id"]
        or payload.get("replacement_passport_digest")
        != repair_payload["replacement_passport_digest"]
        or payload.get("replacement_workstream_digest")
        != repair_payload["replacement_workstream_digest"]
        or not isinstance(start_intent, Mapping)
        or set(start_intent)
        != {"supervisor_generation", "started_at", "app_server_connection_epoch"}
        or not _positive_integer(start_intent.get("supervisor_generation"))
        or start_intent.get("supervisor_generation")
        != expected_supervisor_generation
        or not _positive_integer(start_intent.get("app_server_connection_epoch"))
        or start_intent.get("app_server_connection_epoch")
        != completion_payload["app_server_connection_epoch"]
        or not isinstance(started, Mapping)
        or set(started)
        != {"thread_id", "session_id", "host_id", "model", "reasoning", "ephemeral"}
        or started.get("thread_id") != evidence["successor_thread_id"]
        or started.get("host_id") != evidence["successor_host_id"]
        or started.get("model") != "gpt-5.6-sol"
        or started.get("reasoning") != "ultra"
        or started.get("ephemeral") is not False
        or not _bounded_evidence_id(started.get("session_id"))
    ):
        raise LocalInstallError(
            "preactivation structural successor outbox binding is invalid"
        )
    _qualification_timestamp(start_intent.get("started_at"))


def _validate_preactivation_structural_release_intake(
    connection: sqlite3.Connection,
    *,
    completion_payload: Mapping[str, Any],
    activation_release_sha: str,
    expected_pr_head_sha: str,
    task_id: str,
    workstream_id: str,
    expected_supervisor_generation: int,
    expected_processing_generation: int | None = None,
    current_state: Mapping[str, Any] | None,
    expected_pr_number: int,
) -> None:
    processing_generation = (
        expected_supervisor_generation
        if expected_processing_generation is None
        else expected_processing_generation
    )
    registration = connection.execute(
        "SELECT event_type,payload_json,payload_digest,task_id,workstream_id,executor_generation,writer_generation FROM events WHERE event_id = ?",
        (completion_payload["release_registration_event_id"],),
    ).fetchone()
    intake = connection.execute(
        """
        SELECT kind,payload_json,payload_digest,state,task_id,writer_generation,
               attempts,claim_token,claimed_by,claimed_generation,
               claimed_until,delivered_at,last_error
        FROM outbox WHERE event_id = ?
        """,
        (completion_payload["release_intake_event_id"],),
    ).fetchone()
    if registration is None or intake is None:
        raise LocalInstallError(
            "preactivation remediation release registration is incomplete"
        )
    try:
        registration_payload = json.loads(str(registration["payload_json"]))
        intake_payload = json.loads(str(intake["payload_json"]))
    except json.JSONDecodeError as exc:
        raise LocalInstallError(
            "preactivation remediation release registration is invalid JSON"
        ) from exc
    registration_fields = {
        "schema", "task_id", "task_revision", "workstream_id",
        "workstream_revision", "expected_pr_head_sha", "target_id",
    }
    intake_fields = {
        "schema", "registration_event_id", "task_id", "workstream_id",
        "expected_pr_head_sha",
    }
    if (
        registration["event_type"] != "release_candidate_registered"
        or not isinstance(registration_payload, Mapping)
        or set(registration_payload) != registration_fields
        or registration["payload_digest"]
        != _canonical_mapping_sha256(registration_payload)
        or registration["task_id"] != task_id
        or registration["workstream_id"] != workstream_id
        or registration["executor_generation"] is not None
        or registration["writer_generation"] != expected_supervisor_generation
        or registration_payload.get("schema")
        != "dev-control-plane/release-candidate-registration/v2"
        or registration_payload.get("task_id") != task_id
        or registration_payload.get("task_revision")
        != completion_payload["task_revision"]
        or registration_payload.get("workstream_id") != workstream_id
        or registration_payload.get("workstream_revision")
        != completion_payload["workstream_revision"]
        or registration_payload.get("expected_pr_head_sha")
        != expected_pr_head_sha
        or registration_payload.get("target_id")
        != PREACTIVATION_STRUCTURAL_REPAIR_CANONICAL_TARGET
        or intake["kind"] != "release_candidate_intake"
        or not isinstance(intake_payload, Mapping)
        or set(intake_payload) != intake_fields
        or intake["payload_digest"] != _canonical_mapping_sha256(intake_payload)
        or intake["task_id"] != task_id
        or intake["writer_generation"] != processing_generation
        or intake["state"] != "delivered"
        or int(intake["attempts"]) != 1
        or intake["delivered_at"] is None
        or any(
            intake[field] is not None
            for field in (
                "claim_token",
                "claimed_by",
                "claimed_generation",
                "claimed_until",
                "last_error",
            )
        )
        or intake_payload.get("schema")
        != "dev-control-plane/release-candidate-intake/v2"
        or intake_payload.get("registration_event_id")
        != completion_payload["release_registration_event_id"]
        or intake_payload.get("task_id") != task_id
        or intake_payload.get("workstream_id") != workstream_id
        or intake_payload.get("expected_pr_head_sha") != expected_pr_head_sha
    ):
        raise LocalInstallError(
            "preactivation remediation release registration binding is invalid"
        )

    admission_rows: list[tuple[sqlite3.Row, dict[str, Any]]] = []
    for row in connection.execute(
        """
        SELECT event_id,event_type,payload_json,payload_digest,task_id,
               workstream_id,executor_generation,writer_generation
        FROM events WHERE event_type = 'release_candidate_admitted'
        """
    ):
        payload = _validated_registry_json_mapping(
            row["payload_json"],
            row["payload_digest"],
            label="preactivation proof-only GitHub admission",
        )
        if payload.get("source_event_id") == completion_payload[
            "release_registration_event_id"
        ]:
            admission_rows.append((row, payload))
    if len(admission_rows) != 1:
        raise LocalInstallError(
            "preactivation proof-only GitHub admission is missing or ambiguous"
        )
    admission_row, admission = admission_rows[0]
    admission_fields = {
        "schema",
        "source_event_id",
        "candidate",
        "release_candidate",
        "target_adapter",
        "scheduler_truth",
        "proof_only",
    }
    candidate = admission.get("candidate")
    release_candidate = admission.get("release_candidate")
    truth = admission.get("scheduler_truth")
    if (
        set(admission) != admission_fields
        or admission.get("schema") != PREACTIVATION_RELEASE_ADMISSION_SCHEMA
        or admission.get("proof_only") is not True
        or admission.get("target_adapter") != "dev-control-plane-hosted-v2"
        or admission_row["task_id"] != task_id
        or admission_row["workstream_id"] != workstream_id
        or admission_row["executor_generation"] is not None
        or admission_row["writer_generation"] != processing_generation
        or not isinstance(candidate, Mapping)
        or not isinstance(release_candidate, Mapping)
        or not isinstance(truth, Mapping)
    ):
        raise LocalInstallError(
            "preactivation proof-only GitHub admission binding is invalid"
        )
    truth_fields = {
        "task_revision",
        "workstream_revision",
        "pr_head_sha",
        "target_id",
        "pr_state",
        "merge_commit_sha",
        "diff_files",
        "checks_green",
        "admission_ready",
        "merge_conflict",
        "passport_diff_mismatch",
        "unknown_classification",
    }
    diff_files = truth.get("diff_files")
    if (
        set(truth) != truth_fields
        or truth.get("task_revision") != completion_payload["task_revision"]
        or truth.get("workstream_revision")
        != completion_payload["workstream_revision"]
        or truth.get("pr_head_sha") != expected_pr_head_sha
        or truth.get("target_id")
        != PREACTIVATION_STRUCTURAL_REPAIR_CANONICAL_TARGET
        or truth.get("pr_state") != "MERGED"
        or truth.get("merge_commit_sha") != activation_release_sha
        or not isinstance(diff_files, list)
        or not diff_files
        or diff_files != list(dict.fromkeys(diff_files))
        or any(
            not isinstance(item, str)
            or not item
            or len(item) > 2_000
            or Path(item).is_absolute()
            or ".." in PurePosixPath(item).parts
            for item in diff_files
        )
        or truth.get("checks_green") is not True
        or truth.get("admission_ready") is not False
        or any(
            truth.get(field) is not False
            for field in (
                "merge_conflict",
                "passport_diff_mismatch",
                "unknown_classification",
            )
        )
    ):
        raise LocalInstallError(
        f"preactivation GitHub admission is not the exact merged PR{expected_pr_number} wait"
        )
    candidate_fields = {
        "candidate_id",
        "task_id",
        "workstream_id",
        "logical_lane_id",
        "target_id",
        "task_revision",
        "workstream_revision",
        "pr_head_sha",
        "resources",
        "passport_files",
        "diff_files",
        "modules",
        "databases",
        "schemas",
        "migrations",
        "shared_contracts",
        "dependencies",
        "owner_priority",
        "critical_path_value",
        "unblock_value",
        "risk_score",
        "fairness_credit",
        "ready_since",
        "created_at",
        "checks_green",
        "admission_ready",
        "merge_conflict",
        "passport_diff_mismatch",
        "unknown_classification",
        "holds_logical_lane",
        "lane_healthy",
        "multi_pr_intent",
        "multiple_safe_orders",
    }
    expected_candidate_id = (
        "release-candidate:"
        + hashlib.sha256(
            (
                PREACTIVATION_STRUCTURAL_REPAIR_CANONICAL_TARGET
                + "|"
                + task_id
                + "|"
                + workstream_id
                + "|"
                + expected_pr_head_sha
            ).encode("utf-8")
        ).hexdigest()[:48]
    )
    if (
        set(candidate) != candidate_fields
        or candidate.get("candidate_id") != expected_candidate_id
        or candidate.get("task_id") != task_id
        or candidate.get("workstream_id") != workstream_id
        or candidate.get("target_id")
        != PREACTIVATION_STRUCTURAL_REPAIR_CANONICAL_TARGET
        or candidate.get("task_revision") != completion_payload["task_revision"]
        or candidate.get("workstream_revision")
        != completion_payload["workstream_revision"]
        or candidate.get("pr_head_sha") != expected_pr_head_sha
        or candidate.get("diff_files") != diff_files
        or candidate.get("checks_green") is not True
        or candidate.get("admission_ready") is not False
        or any(
            candidate.get(field) is not False
            for field in (
                "merge_conflict",
                "passport_diff_mismatch",
                "unknown_classification",
                "multiple_safe_orders",
            )
        )
        or candidate.get("lane_healthy") is not True
        or candidate.get("multi_pr_intent") is not True
    ):
        raise LocalInstallError(
            "preactivation proof-only scheduler candidate binding is invalid"
        )
    release_fields = {
        "lane_id",
        "task_id",
        "workstream_id",
        "revision",
        "repo",
        "pr_number",
        "expected_head_sha",
        "base_ref",
        "required_checks",
        "declared_files",
        "resources",
        "multi_pr",
    }
    if (
        set(release_candidate) != release_fields
        or release_candidate.get("lane_id") != candidate.get("logical_lane_id")
        or release_candidate.get("task_id") != task_id
        or release_candidate.get("workstream_id") != workstream_id
        or release_candidate.get("revision") != completion_payload["task_revision"]
        or release_candidate.get("repo")
        != PREACTIVATION_STRUCTURAL_REPAIR_CANONICAL_TARGET
        or release_candidate.get("pr_number") != expected_pr_number
        or release_candidate.get("expected_head_sha") != expected_pr_head_sha
        or release_candidate.get("base_ref") != "main"
        or release_candidate.get("required_checks")
        != ["v2-suite", "self-closure"]
        or release_candidate.get("declared_files")
        != candidate.get("passport_files")
        or release_candidate.get("resources") != candidate.get("resources")
        or release_candidate.get("multi_pr") is not True
    ):
        raise LocalInstallError(
            "preactivation proof-only Release Train readback is invalid"
        )
    if current_state is not None:
        passport = current_state["passport"]
        scheduler_resources = [
            item
            for item in passport.resources
            if not item.startswith(("target:", "release-lane:", "owner-priority:"))
        ]
        lanes = [
            item.removeprefix("release-lane:")
            for item in passport.resources
            if item.startswith("release-lane:")
        ]
        owner_priorities = [
            item.removeprefix("owner-priority:")
            for item in passport.resources
            if item.startswith("owner-priority:")
        ]
        owner_priority = (
            int(owner_priorities[0])
            if len(owner_priorities) == 1
            and re.fullmatch(r"[0-9]{1,9}", owner_priorities[0])
            else None
        )
        derived = {
            "databases": sorted(
                item.removeprefix("database:")
                for item in scheduler_resources
                if item.startswith("database:")
            ),
            "schemas": sorted(
                item.removeprefix("schema:")
                for item in scheduler_resources
                if item.startswith("schema:")
            ),
            "migrations": sorted(
                item.removeprefix("migration:")
                for item in scheduler_resources
                if item.startswith("migration:")
            ),
            "shared_contracts": sorted(
                {
                    item.removeprefix("contract:")
                    for item in scheduler_resources
                    if item.startswith("contract:")
                }
                | {
                    item.removeprefix("shared-contract:")
                    for item in scheduler_resources
                    if item.startswith("shared-contract:")
                }
            ),
        }
        base_risk = sum(
            item.startswith(
                (
                    "database:",
                    "schema:",
                    "migration:",
                    "contract:",
                    "shared-contract:",
                )
            )
            for item in scheduler_resources
        )
        if (
            lanes != [candidate.get("logical_lane_id")]
            or (bool(owner_priorities) and owner_priority is None)
            or candidate.get("resources") != scheduler_resources
            or candidate.get("passport_files") != list(passport.files)
            or candidate.get("modules") != list(passport.modules)
            or candidate.get("dependencies") != list(passport.dependencies)
            or candidate.get("created_at") != passport.created_at
            or any(candidate.get(field) != value for field, value in derived.items())
            or candidate.get("owner_priority") != owner_priority
            or candidate.get("critical_path_value") != 0
            or candidate.get("unblock_value") != 0
            or candidate.get("risk_score") != base_risk + len(diff_files)
            or candidate.get("fairness_credit") != 0
            or candidate.get("holds_logical_lane") is not False
            or not set(diff_files).issubset(set(passport.files))
        ):
            raise LocalInstallError(
                "preactivation GitHub admission differs from the current Passport"
            )
        _qualification_timestamp(candidate.get("ready_since"))

    admission_digest = _canonical_mapping_sha256(admission)
    admission_receipts = []
    for row in connection.execute(
        """
        SELECT source,payload_json,payload_digest,state,processed_at,writer_generation
        FROM inbox WHERE source = 'supervisor-release-candidate-intake'
        """
    ):
        payload = _validated_registry_json_mapping(
            row["payload_json"],
            row["payload_digest"],
            label="preactivation GitHub admission inbox receipt",
        )
        if payload.get("admission_digest") == admission_digest:
            admission_receipts.append((row, payload))
    if len(admission_receipts) != 1:
        raise LocalInstallError(
            "preactivation GitHub admission inbox receipt is missing or ambiguous"
        )
    admission_receipt, admission_input = admission_receipts[0]
    if (
        set(admission_input)
        != {"source_event_id", "candidate_id", "pr_head_sha", "admission_digest"}
        or admission_input.get("source_event_id")
        != completion_payload["release_registration_event_id"]
        or admission_input.get("candidate_id") != expected_candidate_id
        or admission_input.get("pr_head_sha") != expected_pr_head_sha
        or admission_receipt["state"] != "processed"
        or admission_receipt["processed_at"] is None
        or admission_receipt["writer_generation"] != processing_generation
    ):
        raise LocalInstallError(
            "preactivation GitHub admission inbox receipt binding is invalid"
        )

    waits: list[tuple[sqlite3.Row, dict[str, Any]]] = []
    for row in connection.execute(
        """
        SELECT payload_json,payload_digest,writer_generation FROM events
        WHERE task_id = ? AND workstream_id = ? AND event_type = 'release_wait'
        """,
        (task_id, workstream_id),
    ):
        payload = _validated_registry_json_mapping(
            row["payload_json"],
            row["payload_digest"],
            label="preactivation proof-only release wait",
        )
        if payload.get("candidates") == [dict(candidate)]:
            waits.append((row, payload))
    if len(waits) != 1:
        raise LocalInstallError(
            "preactivation proof-only release wait is missing or ambiguous"
        )
    wait_row, wait = waits[0]
    if (
        set(wait) != {"schema", "decision", "candidates", "created_at"}
        or wait.get("schema") != "dev-control-plane/supervisor-event/v2"
        or wait.get("decision")
        != {
            "kind": "wait",
            "candidate_ids": [],
            "reason": "dependencies_not_complete",
            "semantic_case": None,
        }
        or wait_row["writer_generation"] != processing_generation
    ):
        raise LocalInstallError(
            "preactivation proof-only release wait binding is invalid"
        )
    _qualification_timestamp(wait.get("created_at"))
    if connection.execute(
        """
        SELECT 1 FROM outbox
        WHERE task_id = ? AND kind IN ('release_candidate_resolution','release_action')
        LIMIT 1
        """,
        (task_id,),
    ).fetchone() is not None:
        raise LocalInstallError(
            "preactivation proof-only wait unexpectedly authorized a release action"
        )
    for row in connection.execute(
        """
        SELECT event_type,payload_json FROM events
        WHERE task_id = ? AND event_type IN ('release_completed','release_proof_only')
        """,
        (task_id,),
    ):
        if expected_pr_head_sha in str(row["payload_json"]):
            raise LocalInstallError(
                "preactivation initial merged admission used a release action path"
            )
    if current_state is not None and connection.execute(
        "SELECT 1 FROM locks WHERE owner_task_id = ? LIMIT 1",
        (task_id,),
    ).fetchone() is not None:
        raise LocalInstallError(
            "fresh preactivation proof-only wait retained a release reservation"
        )


def _validate_preactivation_resolved_attention(
    connection: sqlite3.Connection,
    *,
    repair_payload: Mapping[str, Any],
    task_id: str,
    require_fresh: bool,
) -> None:
    expected = tuple(repair_payload["superseded_attention_event_ids"])
    rows = connection.execute(
        "SELECT event_id,state FROM outbox WHERE task_id = ? AND kind = 'curator_attention' ORDER BY event_id",
        (task_id,),
    ).fetchall()
    states = {str(row["event_id"]): str(row["state"]) for row in rows}
    if any(states.get(event_id) not in {"superseded", "delivered"} for event_id in expected):
        raise LocalInstallError(
            "preactivation remediation attention resolution changed"
        )
    repair_event_rows = connection.execute(
        """
        SELECT event_id FROM events
        WHERE event_type = ? AND task_id = ?
        """,
        (PREACTIVATION_STRUCTURAL_REPAIR_EVENT_TYPE, task_id),
    ).fetchall()
    if len(repair_event_rows) != 1:
        raise LocalInstallError("preactivation attention repair event is ambiguous")
    repair_event_id = str(repair_event_rows[0]["event_id"])
    resolutions: dict[str, int] = {event_id: 0 for event_id in expected}
    for row in connection.execute(
        """
        SELECT payload_json,payload_digest FROM events
        WHERE task_id = ? AND event_type = 'attention_resolved'
        """,
        (task_id,),
    ):
        payload = _validated_registry_json_mapping(
            row["payload_json"],
            row["payload_digest"],
            label="preactivation attention resolution",
        )
        resolved_id = payload.get("resolved_attention_event_id")
        if resolved_id not in resolutions or (
            set(payload)
            != {
                "schema",
                "status",
                "resolved_attention_event_id",
                "repair_event_id",
                "updated_at",
            }
            or payload.get("schema")
            != "dev-control-plane/attention-resolution/v2"
            or payload.get("status") != "resolved"
            or payload.get("repair_event_id") != repair_event_id
        ):
            raise LocalInstallError(
                "preactivation attention resolution is not bound to the repair"
            )
        resolutions[str(resolved_id)] += 1
        _qualification_timestamp(payload.get("updated_at"))
    if any(count != 1 for count in resolutions.values()):
        raise LocalInstallError(
            "preactivation attention resolution is missing or duplicated"
        )
    if require_fresh and tuple(sorted(states)) != expected:
        raise LocalInstallError(
            "fresh preactivation remediation has unresolved curator attention"
        )


def _validate_preactivation_resolved_incidents(
    connection: sqlite3.Connection,
    *,
    repair_payload: Mapping[str, Any],
    task_id: str,
    workstream_id: str,
    repair_event_id: str,
) -> None:
    expected = {
        str(fingerprint): 0
        for fingerprint in repair_payload["resolved_causal_fingerprints"]
    }
    for row in connection.execute(
        """
        SELECT payload_json,payload_digest FROM events
        WHERE task_id = ? AND workstream_id = ?
            AND event_type = 'incident_policy'
        """,
        (task_id, workstream_id),
    ):
        payload = _validated_registry_json_mapping(
            row["payload_json"],
            row["payload_digest"],
            label="preactivation incident resolution",
        )
        fingerprint = payload.get("fingerprint")
        if fingerprint not in expected or payload.get("status") != "resolved":
            continue
        if (
            set(payload)
            != {
                "schema",
                "revision",
                "status",
                "fingerprint",
                "summary",
                "decision",
                "attempt",
                "error_code",
                "repair_event_id",
                "updated_at",
            }
            or payload.get("schema")
            != "dev-control-plane/incident-state-event/v2"
            or payload.get("revision") != repair_payload["task_revision"]
            or payload.get("decision") != PREACTIVATION_STRUCTURAL_REPAIR_EVENT_TYPE
            or payload.get("attempt") != 0
            or payload.get("error_code") != "none"
            or payload.get("repair_event_id") != repair_event_id
            or not isinstance(payload.get("summary"), str)
            or not payload["summary"]
        ):
            raise LocalInstallError(
                "preactivation incident resolution is not bound to the repair"
            )
        expected[str(fingerprint)] += 1
        _qualification_timestamp(payload.get("updated_at"))
    if any(count != 1 for count in expected.values()):
        raise LocalInstallError(
            "preactivation incident resolution is missing or duplicated"
        )


def _validate_preactivation_current_successor(
    connection: sqlite3.Connection,
    *,
    completion_payload: Mapping[str, Any],
    evidence: Mapping[str, Any],
    repair_payload: Mapping[str, Any],
    predecessor_state: Mapping[str, Any],
) -> dict[str, Any]:
    singleton_counts = (
        int(connection.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]),
        int(
            connection.execute(
                "SELECT COUNT(*) FROM workstreams WHERE is_current = 1"
            ).fetchone()[0]
        ),
        int(
            connection.execute(
                "SELECT COUNT(*) FROM executor_bindings"
            ).fetchone()[0]
        ),
        int(
            connection.execute(
                "SELECT COUNT(*) FROM executor_bindings WHERE state = 'active'"
            ).fetchone()[0]
        ),
        int(
            connection.execute(
                "SELECT COUNT(*) FROM executor_bindings WHERE state = 'pending'"
            ).fetchone()[0]
        ),
        int(connection.execute("SELECT COUNT(*) FROM workspace_bindings").fetchone()[0]),
    )
    if singleton_counts != (1, 1, 2, 1, 0, 1):
        raise LocalInstallError(
            "fresh preactivation remediation is not the singleton successor"
        )
    task = connection.execute(
        "SELECT * FROM tasks WHERE task_id = ?",
        (evidence["task_id"],),
    ).fetchone()
    workstream = connection.execute(
        """
        SELECT * FROM workstreams
        WHERE task_id = ? AND workstream_id = ? AND is_current = 1
        """,
        (evidence["task_id"], evidence["workstream_id"]),
    ).fetchone()
    executor = connection.execute(
        """
        SELECT executor_generation,thread_id,host_id,model,reasoning,state,proof_event_id
        FROM executor_bindings
        WHERE task_id = ? AND workstream_id = ? AND state = 'active'
        """,
        (evidence["task_id"], evidence["workstream_id"]),
    ).fetchone()
    predecessor = connection.execute(
        """
        SELECT executor_generation,thread_id,host_id,model,reasoning,state,proof_event_id
        FROM executor_bindings
        WHERE task_id = ? AND workstream_id = ? AND executor_generation = ?
        """,
        (
            evidence["task_id"],
            evidence["workstream_id"],
            evidence["predecessor_executor_generation"],
        ),
    ).fetchone()
    workspace = connection.execute(
        """
        SELECT canonical_path,path_digest FROM workspace_bindings
        WHERE task_id = ? AND workstream_id = ?
        """,
        (evidence["task_id"], evidence["workstream_id"]),
    ).fetchone()
    if (
        task is None
        or int(task["revision"]) != int(completion_payload["task_revision"])
        or task["state"] != "waiting_release"
        or workstream is None
        or int(workstream["generation"])
        != int(completion_payload["workstream_generation"])
        or int(workstream["revision"])
        != int(completion_payload["workstream_revision"])
        or workstream["state"] != "waiting_release"
        or executor is None
        or int(executor["executor_generation"])
        != evidence["successor_executor_generation"]
        or executor["thread_id"] != evidence["successor_thread_id"]
        or executor["host_id"] != evidence["successor_host_id"]
        or executor["model"] != "gpt-5.6-sol"
        or executor["reasoning"] != "ultra"
        or executor["state"] != "active"
        or executor["proof_event_id"] != evidence["completion_event_id"]
        or predecessor is None
        or predecessor["thread_id"] != evidence["predecessor_thread_id"]
        or predecessor["host_id"] != evidence["predecessor_host_id"]
        or predecessor["model"] != "gpt-5.6-sol"
        or predecessor["reasoning"] != "ultra"
        or predecessor["state"] != "stale"
        or workspace is None
        or hashlib.sha256(str(workspace["canonical_path"]).encode("utf-8")).hexdigest()
        != workspace["path_digest"]
    ):
        raise LocalInstallError(
            "fresh preactivation remediation successor is no longer current"
        )
    passport_raw = _validated_registry_json_mapping(
        task["passport_json"],
        task["passport_digest"],
        label="current preactivation replacement Passport",
    )
    workstream_raw = _validated_registry_json_mapping(
        workstream["contract_json"],
        workstream["contract_digest"],
        label="current preactivation successor workstream",
    )
    try:
        passport = task_passport_from_mapping(passport_raw)
        current_workstream = workstream_from_mapping(workstream_raw)
        validate_workstream_against_passport(current_workstream, passport)
    except (OrchestrationValidationError, TypeError, ValueError) as exc:
        raise LocalInstallError(
            "current preactivation successor contracts are invalid"
        ) from exc
    if (
        contract_to_dict(passport) != passport_raw
        or contract_digest(passport) != task["passport_digest"]
        or task["passport_digest"]
        != repair_payload["replacement_passport_digest"]
        or passport.task_id != task["task_id"]
        or passport.revision != int(task["revision"])
        or contract_to_dict(current_workstream) != workstream_raw
        or contract_digest(current_workstream) != workstream["contract_digest"]
        or current_workstream.task_id != workstream["task_id"]
        or current_workstream.workstream_id != workstream["workstream_id"]
        or current_workstream.generation != int(workstream["generation"])
        or current_workstream.revision != int(workstream["revision"])
        or current_workstream.state != workstream["state"]
    ):
        raise LocalInstallError(
            "current preactivation successor contract digest binding changed"
        )
    initial_workstream_raw = dict(workstream_raw)
    initial_workstream_raw.update(
        {
            "revision": repair_payload["workstream_revision"],
            "state": "recovering",
            "executor": None,
        }
    )
    try:
        initial_workstream = workstream_from_mapping(initial_workstream_raw)
        validate_workstream_against_passport(initial_workstream, passport)
    except (OrchestrationValidationError, TypeError, ValueError) as exc:
        raise LocalInstallError(
            "preactivation corrective workstream reconstruction is invalid"
        ) from exc
    if contract_digest(initial_workstream) != repair_payload[
        "replacement_workstream_digest"
    ]:
        raise LocalInstallError(
            "preactivation corrective workstream digest changed"
        )

    resources = set(passport.resources)
    qualification_resources = sorted(
        item for item in resources if item.startswith("qualification:")
    )
    manifest = passport_raw.get("release_manifest")
    expected_pr91_pr = (
        "github-pr-v1:orenvlad-ai/dev-control-plane:91:"
        + PREACTIVATION_PR91_HEAD_SHA
        + ":"
        + PREACTIVATION_STRUCTURAL_REPAIR_PREDECESSOR_SHA
    )
    expected_pr92_pr = (
        "github-pr-v1:orenvlad-ai/dev-control-plane:92:"
        + str(evidence["expected_pr_head_sha"])
        + ":"
        + str(evidence["activation_release_sha"])
    )
    expected_pr91_deploy = (
        "hosted-release-v1:wb-core-eu-root:devcontrol.pro:"
        + PREACTIVATION_STRUCTURAL_REPAIR_PREDECESSOR_SHA
    )
    expected_pr92_deploy = (
        "hosted-release-v1:wb-core-eu-root:devcontrol.pro:"
        + str(evidence["activation_release_sha"])
    )
    if (
        f"target:{PREACTIVATION_STRUCTURAL_REPAIR_CANONICAL_TARGET}"
        not in resources
        or "target:dev-control-plane" in resources
        or qualification_resources
        != [f"qualification:{evidence['activation_release_sha']}"]
        or passport.multi_pr_intent is not True
        or passport.multi_deploy_intent is not True
        or "codex_workspace_mutation" not in passport.autonomy.allowed_actions
        or not isinstance(manifest, Mapping)
        or manifest.get("pr_identities") != [expected_pr91_pr, expected_pr92_pr]
        or manifest.get("deploy_identities")
        != [expected_pr91_deploy, expected_pr92_deploy]
        or set(current_workstream.resources) != resources
    ):
        raise LocalInstallError(
            "current preactivation successor is not the exact PR92 contract"
        )
    predecessor_passport = predecessor_state["passport"]
    predecessor_workstream = predecessor_state["workstream"]
    for invariant in (
        "task_id",
        "title",
        "objective",
        "expected_result",
        "contour",
        "excluded_scope",
        "acceptance",
        "closure",
        "autonomy",
        "workstream_ids",
        "dependencies",
        "curator",
        "executor",
        "created_at",
    ):
        if predecessor_passport.get(invariant) != passport_raw.get(invariant):
            raise LocalInstallError(
                f"preactivation replacement changed immutable Passport field {invariant}"
            )
    for extensible in ("included_scope", "constraints", "modules", "files"):
        old_values = predecessor_passport.get(extensible)
        new_values = passport_raw.get(extensible)
        if (
            not isinstance(old_values, list)
            or not isinstance(new_values, list)
            or not set(old_values).issubset(set(new_values))
        ):
            raise LocalInstallError(
                f"preactivation replacement removed Passport {extensible}"
            )
    old_nonrouting = {
        item
        for item in predecessor_passport["resources"]
        if not str(item).startswith("target:")
    }
    new_nonrouting = {
        item
        for item in passport.resources
        if not item.startswith(("target:", "qualification:"))
    }
    if old_nonrouting != new_nonrouting:
        raise LocalInstallError(
            "preactivation replacement changed unrelated Passport resources"
        )
    for invariant in (
        "workstream_id",
        "task_id",
        "root_workstream_id",
        "title",
        "objective",
        "dependencies",
        "created_at",
    ):
        if predecessor_workstream.get(invariant) != workstream_raw.get(invariant):
            raise LocalInstallError(
                f"preactivation replacement changed immutable workstream field {invariant}"
            )
    expected_executor = {
        "thread_id": evidence["successor_thread_id"],
        "host_id": evidence["successor_host_id"],
        "model": "gpt-5.6-sol",
        "reasoning": "ultra",
    }
    if (
        workstream_raw.get("executor") != expected_executor
        or predecessor_state["workspace"] != str(workspace["canonical_path"])
    ):
        raise LocalInstallError(
            "preactivation successor executor/workspace binding changed"
        )
    return {
        "passport": passport,
        "passport_raw": passport_raw,
        "workstream": current_workstream,
        "workstream_raw": workstream_raw,
    }


def _canonical_mapping_sha256(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            dict(payload),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _positive_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _checkpoint_progress(value: Any) -> bool:
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and value in CHECKPOINT_PROGRESS_STAGES
    )


def _bounded_evidence_id(value: Any) -> bool:
    return (
        isinstance(value, str)
        and 1 <= len(value) <= 512
        and value == value.strip()
        and "\x00" not in value
        and "\n" not in value
        and "\r" not in value
    )


def _lower_hex(value: Any, length: int) -> bool:
    return isinstance(value, str) and re.fullmatch(rf"[0-9a-f]{{{length}}}", value) is not None


def _json_line_objects(raw: bytes, *, ignore_non_json: bool) -> list[dict[str, Any]]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise LocalInstallError("qualification evidence is not UTF-8 JSON") from exc
    records: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            if ignore_non_json:
                continue
            raise LocalInstallError("qualification evidence contains a malformed JSON record")
        if not isinstance(value, dict):
            raise LocalInstallError("qualification evidence record is not an object")
        records.append(value)
    return records


def _validate_evidence_time(
    observed: datetime,
    *,
    qualification_created_at: datetime,
    validation_now: datetime,
    require_fresh: bool,
    label: str,
) -> None:
    if observed > qualification_created_at + timedelta(minutes=5):
        raise LocalInstallError(f"qualification {label} evidence postdates its manifest")
    if observed > validation_now + timedelta(minutes=5):
        raise LocalInstallError(f"qualification {label} evidence timestamp is in the future")
    if require_fresh and validation_now - observed > LOCAL_QUALIFICATION_MAX_AGE:
        raise LocalInstallError(f"qualification {label} evidence is older than 24 hours")


def _qualification_timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not value or value != value.strip():
        raise LocalInstallError("qualification timestamp is invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise LocalInstallError("qualification timestamp is invalid") from exc
    if parsed.tzinfo is None:
        raise LocalInstallError("qualification timestamp must include timezone")
    return parsed.astimezone(timezone.utc)


_PREACTIVATION_BUSINESS_TABLES = (
    "tasks",
    "workstreams",
    "executor_bindings",
    "events",
    "inbox",
    "outbox",
    "locks",
    "idempotency_keys",
    "workspace_bindings",
)
_PREACTIVATION_SOURCE_TABLE_COUNTS = {
    "events": 8,
    "executor_bindings": 1,
    "idempotency_keys": 0,
    "inbox": 10,
    "locks": 0,
    "outbox": 18,
    "projection_transport_state": 1,
    "schema_migrations": 3,
    "supervisor_lease": 1,
    "tasks": 1,
    "workspace_bindings": 1,
    "workstreams": 1,
}
_PREACTIVATION_SOURCE_EVENT_COUNTS = {
    "executor_started": 1,
    "incident_policy": 2,
    "release_candidate_admitted": 1,
    "release_candidate_registered": 1,
    "release_wait": 1,
    "target_lane_closure_completed": 1,
    "target_lane_closure_pending": 1,
}
_PREACTIVATION_SOURCE_OUTBOX_COUNTS = {
    ("codex_followup", "delivered", 2): 1,
    ("codex_thread_start", "delivered", 1): 1,
    ("curator_attention", "pending", 0): 1,
    ("projection_dirty", "delivered", 1): 4,
    ("projection_dirty", "superseded", 0): 4,
    ("projection_snapshot", "delivered", 1): 5,
    ("release_candidate_intake", "delivered", 1): 1,
    ("target_lane_closure", "delivered", 1): 1,
}
_PREACTIVATION_SOURCE_INBOX_COUNTS = {
    "codex-thread-start-worker": 1,
    "codex-worker": 2,
    "deterministic-scheduler": 1,
    "private-unix-command:codex-followup": 1,
    "private-unix-command:release-candidate-registration": 1,
    "private-unix-command:start-executor": 1,
    "supervisor-release-candidate-intake": 1,
    "supervisor-target-lane-closure-reconciler": 1,
    "supervisor-target-lane-closure-worker": 1,
}
_PREACTIVATION_JOURNAL_FIELDS = {
    "schema", "recovery_id", "phase", "replacement_sha", "failed_release_sha",
    "archive_dir", "archive_state", "fresh_state", "backup_path",
    "backup_sha256", "source_registry_digest", "source_table_counts",
    "source_task_id", "source_workstream_id", "source_executor_generation",
    "source_thread_id", "source_host_id", "source_failure_event_ids",
    "source_followup_event_id", "source_attention_event_id",
    "source_causal_fingerprint", "manifest_path", "old_state_dev", "old_state_ino",
    "fresh_state_dev", "fresh_state_ino", "prior_supervisor_generation",
    "prior_projection_generation", "prior_projection_sequence",
    "prior_projection_revision", "model_attempt_count", "model_call_count",
    "created_at",
}


def _inspect_failed_preactivation_registry(
    state_dir: Path,
    *,
    expected_replacement_sha: str,
) -> dict[str, Any]:
    state = Path(os.path.abspath(state_dir))
    metadata = state.lstat()
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
        or state.is_symlink()
    ):
        raise LocalInstallError("preactivation state directory is not private and direct")
    database = state / "supervisor.sqlite3"
    database_metadata = _private_regular_metadata(database)
    workspace_root = state / "managed_workspaces"
    workspace = workspace_root / "rollout-pilot"
    for path in (workspace_root, workspace):
        item = path.lstat()
        if (
            not stat.S_ISDIR(item.st_mode)
            or item.st_uid != os.geteuid()
            or path.is_symlink()
            or stat.S_IMODE(item.st_mode) != 0o700
        ):
            raise LocalInstallError("preactivation pilot workspace is not private and direct")
    if tuple(workspace.iterdir()) or tuple(workspace_root.iterdir()) != (workspace,):
        raise LocalInstallError("preactivation pilot workspace is not exactly empty")

    connection = sqlite3.connect(_sqlite_readonly_uri(database), uri=True, timeout=10)
    connection.row_factory = sqlite3.Row
    try:
        if str(connection.execute("PRAGMA quick_check").fetchone()[0]) != "ok":
            raise LocalInstallError("preactivation registry integrity check failed")
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise LocalInstallError("preactivation registry foreign keys are inconsistent")
        if (
            int(connection.execute("PRAGMA user_version").fetchone()[0]) != 3
            or str(connection.execute("PRAGMA journal_mode").fetchone()[0]).lower() != "wal"
            or int(connection.execute("PRAGMA synchronous").fetchone()[0]) != 2
        ):
            raise LocalInstallError("preactivation registry durability/schema contract differs")
        versions = tuple(
            int(row[0])
            for row in connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
        )
        if versions != (1, 2, 3):
            raise LocalInstallError("preactivation registry migration history is incomplete")
        table_counts = _sqlite_table_counts(connection)
        lease_rows = connection.execute("SELECT * FROM supervisor_lease").fetchall()
        projection_rows = connection.execute(
            "SELECT * FROM projection_transport_state"
        ).fetchall()
        if len(lease_rows) != 1 or len(projection_rows) != 1:
            raise LocalInstallError("preactivation singleton state is ambiguous")
        lease = lease_rows[0]
        projection = projection_rows[0]
        if (
            int(lease["singleton"]) != 1
            or int(lease["generation"]) != 1
            or lease["owner_id"] is not None
            or lease["lease_token"] is not None
            or float(lease["expires_at"]) != 0.0
        ):
            raise LocalInstallError("preactivation Supervisor lease is not the stopped first pilot")
        if (
            int(projection["singleton"]) != 1
            or int(projection["generation"]) != 1
            or int(projection["sequence"]) != 5
            or int(projection["revision"]) != 5
        ):
            raise LocalInstallError("preactivation projection watermark is invalid")
        if table_counts != _PREACTIVATION_SOURCE_TABLE_COUNTS:
            raise LocalInstallError("preactivation registry aggregate shape differs")
        event_counts = {
            str(row[0]): int(row[1])
            for row in connection.execute(
                "SELECT event_type,COUNT(*) FROM events GROUP BY event_type"
            )
        }
        outbox_counts = {
            (str(row[0]), str(row[1]), int(row[2])): int(row[3])
            for row in connection.execute(
                "SELECT kind,state,attempts,COUNT(*) FROM outbox GROUP BY kind,state,attempts"
            )
        }
        inbox_counts = {
            str(row[0]): int(row[1])
            for row in connection.execute(
                "SELECT source,COUNT(*) FROM inbox GROUP BY source"
            )
        }
        if (
            event_counts != _PREACTIVATION_SOURCE_EVENT_COUNTS
            or outbox_counts != _PREACTIVATION_SOURCE_OUTBOX_COUNTS
            or inbox_counts != _PREACTIVATION_SOURCE_INBOX_COUNTS
            or connection.execute(
                "SELECT 1 FROM inbox WHERE state != 'processed' OR writer_generation != 1 LIMIT 1"
            ).fetchone()
        ):
            raise LocalInstallError("preactivation aggregate distributions differ")
        task = connection.execute("SELECT * FROM tasks").fetchone()
        workstream = connection.execute("SELECT * FROM workstreams").fetchone()
        executor = connection.execute("SELECT * FROM executor_bindings").fetchone()
        binding = connection.execute("SELECT * FROM workspace_bindings").fetchone()
        if task is None or workstream is None or executor is None or binding is None:
            raise LocalInstallError("preactivation registry bindings are missing")
        if (
            task["task_id"] != PREACTIVATION_SOURCE_TASK_ID
            or int(task["revision"]) != 2
            or task["state"] != "parked"
            or int(task["writer_generation"]) != 1
            or workstream["workstream_id"] != PREACTIVATION_SOURCE_WORKSTREAM_ID
            or workstream["task_id"] != PREACTIVATION_SOURCE_TASK_ID
            or workstream["state"] != "parked"
            or int(workstream["generation"]) != 1
            or int(workstream["revision"]) != 2
            or int(workstream["is_current"]) != 1
            or int(workstream["writer_generation"]) != 1
            or executor["task_id"] != PREACTIVATION_SOURCE_TASK_ID
            or executor["workstream_id"] != PREACTIVATION_SOURCE_WORKSTREAM_ID
            or executor["state"] != "active"
            or int(executor["executor_generation"]) != 1
            or executor["model"] != "gpt-5.6-sol"
            or executor["reasoning"] != "ultra"
            or not _bounded_evidence_id(executor["thread_id"])
            or not _bounded_evidence_id(executor["host_id"])
            or not _lower_hex(executor["checkpoint_digest"], 64)
            or executor["proof_event_id"] is not None
            or int(executor["writer_generation"]) != 1
            or binding["task_id"] != PREACTIVATION_SOURCE_TASK_ID
            or binding["workstream_id"] != PREACTIVATION_SOURCE_WORKSTREAM_ID
            or binding["canonical_path"] != str(workspace)
            or int(binding["writer_generation"]) != 1
        ):
            raise LocalInstallError("preactivation pilot identity/state differs")
        if (
            hashlib.sha256(str(task["passport_json"]).encode("utf-8")).hexdigest()
            != task["passport_digest"]
            or hashlib.sha256(str(workstream["contract_json"]).encode("utf-8")).hexdigest()
            != workstream["contract_digest"]
            or hashlib.sha256(str(binding["canonical_path"]).encode("utf-8")).hexdigest()
            != binding["path_digest"]
            or any(
                hashlib.sha256(str(row["payload_json"]).encode("utf-8")).hexdigest()
                != row["payload_digest"]
                for table in ("events", "inbox", "outbox")
                for row in connection.execute(f'SELECT * FROM "{table}"')
            )
            or any(
                int(row[0]) != 1
                for table in ("events", "inbox", "outbox")
                for row in connection.execute(
                    f'SELECT writer_generation FROM "{table}"'
                )
            )
        ):
            raise LocalInstallError("preactivation aggregate digest bindings differ")
        if connection.execute(
            """
            SELECT 1 FROM events
            WHERE task_id IS NULL OR task_id <> ?
               OR workstream_id IS NULL OR workstream_id <> ?
            LIMIT 1
            """,
            (PREACTIVATION_SOURCE_TASK_ID, PREACTIVATION_SOURCE_WORKSTREAM_ID),
        ).fetchone():
            raise LocalInstallError("preactivation event ownership differs")
        if connection.execute(
            """
            SELECT 1 FROM outbox
            WHERE (kind = 'projection_snapshot' AND task_id IS NOT NULL)
               OR (kind != 'projection_snapshot' AND (task_id IS NULL OR task_id <> ?))
            LIMIT 1
            """,
            (PREACTIVATION_SOURCE_TASK_ID,),
        ).fetchone():
            raise LocalInstallError("preactivation outbox ownership differs")
        try:
            passport = json.loads(str(task["passport_json"]))
        except json.JSONDecodeError as exc:
            raise LocalInstallError("preactivation pilot Passport is invalid") from exc
        resources = passport.get("resources") if isinstance(passport, Mapping) else None
        qualification_shas = (
            sorted(
                item.partition(":")[2]
                for item in resources
                if isinstance(item, str)
                and re.fullmatch(r"qualification:[0-9a-f]{40}", item)
            )
            if isinstance(resources, list)
            else []
        )
        if (
            task["task_id"] != passport.get("task_id")
            or passport.get("revision") != 2
            or passport.get("workstream_ids") != [PREACTIVATION_SOURCE_WORKSTREAM_ID]
            or qualification_shas != [PREACTIVATION_SOURCE_RELEASE_SHA]
            or expected_replacement_sha == PREACTIVATION_SOURCE_RELEASE_SHA
        ):
            raise LocalInstallError("preactivation failed/replacement release binding is invalid")
        followups = connection.execute(
            "SELECT * FROM outbox WHERE kind = 'codex_followup'"
        ).fetchall()
        starts = connection.execute(
            "SELECT * FROM outbox WHERE kind = 'codex_thread_start'"
        ).fetchall()
        if len(followups) != 1 or len(starts) != 1:
            raise LocalInstallError("preactivation Codex queue shape differs")
        followup = followups[0]
        start = starts[0]
        try:
            followup_payload = json.loads(str(followup["payload_json"]))
        except json.JSONDecodeError as exc:
            raise LocalInstallError("preactivation follow-up payload is invalid") from exc
        if (
            followup["state"] != "delivered"
            or int(followup["attempts"]) != 2
            or followup["last_error"] != "codex_remote_error"
            or followup_payload.get("call_policy") != "single_attempt_canary"
            or followup_payload.get("output_contract") != "checkpoint"
            or followup_payload.get("model_attempt_count") != 0
            or followup_payload.get("call_intent") is not None
            or followup_payload.get("task_id") != PREACTIVATION_SOURCE_TASK_ID
            or followup_payload.get("workstream_id") != PREACTIVATION_SOURCE_WORKSTREAM_ID
            or followup_payload.get("thread_id") != executor["thread_id"]
            or followup_payload.get("host_id") != executor["host_id"]
            or followup_payload.get("causal_fingerprint")
            != PREACTIVATION_SOURCE_CAUSAL_FINGERPRINT
            or start["state"] != "delivered"
            or int(start["attempts"]) != 1
        ):
            raise LocalInstallError("preactivation failure is not the exact zero-call defect")
        incidents = connection.execute(
            "SELECT * FROM events WHERE event_type = 'incident_policy' ORDER BY created_at,event_id"
        ).fetchall()
        if len(incidents) != 2:
            raise LocalInstallError("preactivation incident history differs")
        incident_payloads = [json.loads(str(row["payload_json"])) for row in incidents]
        if (
            incident_payloads[0].get("attempt") != 1
            or incident_payloads[0].get("decision") != "retry_current_executor"
            or incident_payloads[0].get("error_code") != "codex_remote_error"
            or incident_payloads[1].get("attempt") != 2
            or incident_payloads[1].get("decision") != "park_workstream"
            or incident_payloads[1].get("status") != "missing_verified_checkpoint"
            or incident_payloads[1].get("error_code") != "codex_remote_error"
            or incident_payloads[0].get("fingerprint") != incident_payloads[1].get("fingerprint")
            or incident_payloads[0].get("fingerprint")
            != PREACTIVATION_SOURCE_CAUSAL_FINGERPRINT
        ):
            raise LocalInstallError("preactivation anti-loop history is not the known defect")
        pending = connection.execute(
            "SELECT * FROM outbox WHERE state IN ('pending','inflight')"
        ).fetchall()
        if len(pending) != 1 or pending[0]["kind"] != "curator_attention" or pending[0]["state"] != "pending":
            raise LocalInstallError("preactivation pending queue is not the known undelivered attention")
        try:
            attention = json.loads(str(pending[0]["payload_json"]))
        except json.JSONDecodeError as exc:
            raise LocalInstallError("preactivation attention payload is invalid") from exc
        if (
            attention.get("kind") != "serious_stall"
            or attention.get("task_id") != PREACTIVATION_SOURCE_TASK_ID
            or attention.get("workstream_id") != PREACTIVATION_SOURCE_WORKSTREAM_ID
        ):
            raise LocalInstallError("preactivation pending attention kind differs")
        if connection.execute("SELECT 1 FROM inbox WHERE state != 'processed' LIMIT 1").fetchone():
            raise LocalInstallError("preactivation inbox still has unprocessed input")
        forbidden_events = {
            "checkpoint", "codex_turn_receipt", "technical_terminal", "owner_accepted",
            "owner_acceptance", "incident_arbiter_decided", "incident_arbiter_applied",
        }
        placeholders = ",".join("?" for _ in forbidden_events)
        if connection.execute(
            f"SELECT 1 FROM events WHERE event_type IN ({placeholders}) LIMIT 1",
            tuple(sorted(forbidden_events)),
        ).fetchone():
            raise LocalInstallError("preactivation registry contains model/terminal/acceptance evidence")
        if connection.execute("SELECT 1 FROM outbox WHERE kind = 'release_action' LIMIT 1").fetchone():
            raise LocalInstallError("preactivation registry contains a release mutation action")
    finally:
        connection.close()
    repeated = _private_regular_metadata(database)
    if (repeated.st_dev, repeated.st_ino) != (
        database_metadata.st_dev,
        database_metadata.st_ino,
    ):
        raise LocalInstallError("preactivation registry identity changed during validation")
    return {
        "failed_release_sha": qualification_shas[0],
        "supervisor_generation": int(lease["generation"]),
        "projection_generation": int(projection["generation"]),
        "projection_sequence": int(projection["sequence"]),
        "projection_revision": int(projection["revision"]),
        "table_counts": table_counts,
        "registry_digest": _sqlite_logical_digest(connection_path=database),
        "source_task_id": PREACTIVATION_SOURCE_TASK_ID,
        "source_workstream_id": PREACTIVATION_SOURCE_WORKSTREAM_ID,
        "source_executor_generation": int(executor["executor_generation"]),
        "source_thread_id": str(executor["thread_id"]),
        "source_host_id": str(executor["host_id"]),
        "source_failure_event_ids": [str(row["event_id"]) for row in incidents],
        "source_followup_event_id": str(followup["event_id"]),
        "source_attention_event_id": str(pending[0]["event_id"]),
        "source_causal_fingerprint": PREACTIVATION_SOURCE_CAUSAL_FINGERPRINT,
    }


def _secure_sqlite_archive(
    source: Path,
    destination: Path,
) -> tuple[Path, str, dict[str, int], str]:
    source_metadata = _private_regular_metadata(source)
    if os.path.lexists(destination):
        raise LocalInstallError("preactivation SQLite archive already exists")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".preactivation.",
        suffix=".sqlite3",
        dir=destination.parent,
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        source_connection = sqlite3.connect(
            _sqlite_readonly_uri(source),
            uri=True,
            timeout=10,
        )
        destination_connection = sqlite3.connect(temporary, timeout=10)
        try:
            if str(source_connection.execute("PRAGMA quick_check").fetchone()[0]) != "ok":
                raise LocalInstallError("preactivation SQLite source integrity failed")
            source_connection.backup(destination_connection)
            destination_connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            if str(destination_connection.execute("PRAGMA integrity_check").fetchone()[0]) != "ok":
                raise LocalInstallError("preactivation SQLite archive integrity failed")
            counts = _sqlite_table_counts(destination_connection)
        finally:
            destination_connection.close()
            source_connection.close()
        repeated = _private_regular_metadata(source)
        if (repeated.st_dev, repeated.st_ino) != (
            source_metadata.st_dev,
            source_metadata.st_ino,
        ):
            raise LocalInstallError("preactivation SQLite source changed during archive")
        temporary.chmod(0o600)
        _fsync_path(temporary)
        os.replace(temporary, destination)
        _fsync_directory(destination.parent)
    finally:
        if temporary.exists():
            temporary.unlink()
    _private_regular_metadata(destination)
    connection = sqlite3.connect(_sqlite_readonly_uri(destination), uri=True, timeout=10)
    try:
        if str(connection.execute("PRAGMA integrity_check").fetchone()[0]) != "ok":
            raise LocalInstallError("sealed preactivation archive integrity failed")
        verified_counts = _sqlite_table_counts(connection)
    finally:
        connection.close()
    if verified_counts != counts:
        raise LocalInstallError("sealed preactivation archive counts changed")
    return (
        destination,
        _secure_file_sha256(destination),
        counts,
        _sqlite_logical_digest(connection_path=destination),
    )


def _sqlite_logical_digest(*, connection_path: Path) -> str:
    """Digest every schema-owned row without depending on SQLite file layout."""

    database = Path(os.path.abspath(connection_path))
    _private_regular_metadata(database)
    connection = sqlite3.connect(_sqlite_readonly_uri(database), uri=True, timeout=10)
    connection.row_factory = sqlite3.Row
    digest = hashlib.sha256()
    try:
        table_names = [
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        for table in table_names:
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table):
                raise LocalInstallError("preactivation registry table name is unsafe")
            columns = [
                str(row[1])
                for row in connection.execute(f'PRAGMA table_info("{table}")')
            ]
            digest.update(
                json.dumps(
                    {"table": table, "columns": columns},
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            )
            for row in connection.execute(f'SELECT * FROM "{table}" ORDER BY rowid'):
                values = [row[column] for column in columns]
                if any(isinstance(value, bytes) for value in values):
                    raise LocalInstallError("preactivation registry contains unsupported blobs")
                digest.update(
                    json.dumps(
                        values,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ).encode("utf-8")
                )
    finally:
        connection.close()
    return digest.hexdigest()


def _verify_fresh_recovery_state(
    state_dir: Path,
    *,
    expected: Mapping[str, Any],
) -> None:
    state = Path(os.path.abspath(state_dir))
    metadata = state.lstat()
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
        or state.is_symlink()
    ):
        raise LocalInstallError("fresh preactivation state is not private")
    database = state / "supervisor.sqlite3"
    _private_regular_metadata(database)
    connection = sqlite3.connect(_sqlite_readonly_uri(database), uri=True, timeout=10)
    connection.row_factory = sqlite3.Row
    try:
        if str(connection.execute("PRAGMA quick_check").fetchone()[0]) != "ok":
            raise LocalInstallError("fresh preactivation registry integrity failed")
        for table in _PREACTIVATION_BUSINESS_TABLES:
            if int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]) != 0:
                raise LocalInstallError("fresh preactivation registry contains business state")
        lease = connection.execute("SELECT * FROM supervisor_lease").fetchone()
        projection = connection.execute("SELECT * FROM projection_transport_state").fetchone()
        if (
            lease is None
            or int(lease["generation"]) != int(expected["supervisor_generation"])
            or lease["owner_id"] is not None
            or lease["lease_token"] is not None
            or float(lease["expires_at"]) != 0.0
            or projection is None
            or int(projection["generation"]) != int(expected["projection_generation"])
            or int(projection["sequence"]) != int(expected["projection_sequence"])
            or int(projection["revision"]) != int(expected["projection_revision"])
        ):
            raise LocalInstallError("fresh preactivation watermarks differ from archive")
    finally:
        connection.close()
    workspace_root = state / "managed_workspaces"
    if (
        not workspace_root.is_dir()
        or workspace_root.is_symlink()
        or tuple(workspace_root.iterdir())
        or stat.S_IMODE(workspace_root.stat().st_mode) != 0o700
    ):
        raise LocalInstallError("fresh preactivation workspace root is not empty/private")


def _seal_prepared_recovery_state(state_dir: Path) -> None:
    """Place a power-loss durability barrier before journaling ``prepared``."""

    state = Path(os.path.abspath(state_dir))
    database = state / "supervisor.sqlite3"
    connection = sqlite3.connect(database, timeout=10)
    try:
        result = connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        if result is None or int(result[0]) != 0:
            raise LocalInstallError(
                "preactivation fresh registry checkpoint did not complete"
            )
    finally:
        connection.close()
    for path in (
        database,
        database.with_name(database.name + "-wal"),
        database.with_name(database.name + "-shm"),
    ):
        if os.path.lexists(path):
            _private_regular_metadata(path)
            _fsync_path(path)
    _fsync_directory(state / "managed_workspaces")
    _fsync_directory(state)
    _fsync_directory(state.parent)


def _verify_recovered_watermarks_not_regressed(
    state_dir: Path,
    *,
    expected: Mapping[str, Any],
    require_empty_projection: bool,
) -> dict[str, int]:
    state = Path(os.path.abspath(state_dir))
    metadata = state.lstat()
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
        or state.is_symlink()
    ):
        raise LocalInstallError("recovered preactivation state is not private")
    database = state / "supervisor.sqlite3"
    _private_regular_metadata(database)
    connection = sqlite3.connect(_sqlite_readonly_uri(database), uri=True, timeout=10)
    connection.row_factory = sqlite3.Row
    try:
        if str(connection.execute("PRAGMA quick_check").fetchone()[0]) != "ok":
            raise LocalInstallError("recovered preactivation registry integrity failed")
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise LocalInstallError("recovered preactivation registry foreign keys changed")
        lease_rows = connection.execute("SELECT * FROM supervisor_lease").fetchall()
        projection_rows = connection.execute(
            "SELECT * FROM projection_transport_state"
        ).fetchall()
        if len(lease_rows) != 1 or len(projection_rows) != 1:
            raise LocalInstallError("recovered preactivation singleton state is ambiguous")
        lease = lease_rows[0]
        projection = projection_rows[0]
        supervisor_generation = int(lease["generation"])
        projection_generation = int(projection["generation"])
        projection_sequence = int(projection["sequence"])
        projection_revision = int(projection["revision"])
        prior_supervisor = int(expected["supervisor_generation"])
        prior_projection_generation = int(expected["projection_generation"])
        prior_projection_sequence = int(expected["projection_sequence"])
        prior_projection_revision = int(expected["projection_revision"])
        inactive = lease["owner_id"] is None
        if (
            int(lease["singleton"]) != 1
            or supervisor_generation < prior_supervisor
            or (
                inactive
                and (
                    lease["lease_token"] is not None
                    or float(lease["expires_at"]) != 0.0
                )
            )
            or (
                not inactive
                and (
                    not isinstance(lease["owner_id"], str)
                    or not lease["owner_id"]
                    or not isinstance(lease["lease_token"], str)
                    or not lease["lease_token"]
                    or float(lease["expires_at"]) <= 0.0
                )
            )
            or int(projection["singleton"]) != 1
            or projection_generation <= prior_projection_generation
            or projection_generation > supervisor_generation
            or projection_revision <= prior_projection_revision
            or projection_sequence < 1
        ):
            raise LocalInstallError("recovered preactivation watermarks regressed")
        empty_projection_proven = False
        for row in connection.execute(
            "SELECT payload_json FROM outbox WHERE kind = 'projection_snapshot'"
        ):
            try:
                payload = json.loads(str(row[0]))
            except json.JSONDecodeError as exc:
                raise LocalInstallError(
                    "recovered preactivation projection evidence is invalid"
                ) from exc
            projection_payload = payload.get("projection") if isinstance(payload, Mapping) else None
            if (
                payload.get("generation") == prior_supervisor + 1
                and payload.get("sequence") == 1
                and payload.get("revision") == prior_projection_revision + 1
                and isinstance(projection_payload, Mapping)
                and projection_payload.get("tasks") == []
                and projection_payload.get("workstreams") == []
                and projection_payload.get("attention") == []
                and projection_payload.get("incidents") == []
                and projection_payload.get("release_lanes") == []
                and projection_payload.get("acceptance") == []
            ):
                empty_projection_proven = True
        if require_empty_projection and not empty_projection_proven:
            raise LocalInstallError(
                "recovered preactivation first projection did not prove an empty registry"
            )
    finally:
        connection.close()
    return {
        "current_supervisor_generation": supervisor_generation,
        "current_supervisor_active": not inactive,
        "current_projection_generation": projection_generation,
        "current_projection_sequence": projection_sequence,
        "current_projection_revision": projection_revision,
        "empty_projection_proven": empty_projection_proven,
    }


def _decode_preactivation_journal(raw: bytes) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LocalInstallError("preactivation recovery journal is invalid JSON") from exc
    if not isinstance(value, dict):
        raise LocalInstallError("preactivation recovery journal is not an object")
    return value


def _validated_preactivation_journal(
    value: Mapping[str, Any],
    layout: LocalInstallLayout,
) -> dict[str, Any]:
    if set(value) != _PREACTIVATION_JOURNAL_FIELDS or value.get("schema") != PREACTIVATION_RECOVERY_JOURNAL_SCHEMA:
        raise LocalInstallError("preactivation recovery journal fields are invalid")
    if value.get("phase") not in {
        "allocating", "prepared", "old_state_archived", "fresh_state_installed",
        "committed",
    }:
        raise LocalInstallError("preactivation recovery journal phase is invalid")
    for key in ("replacement_sha", "failed_release_sha"):
        if not isinstance(value.get(key), str) or not re.fullmatch(r"[0-9a-f]{40}", str(value[key])):
            raise LocalInstallError("preactivation recovery SHA binding is invalid")
    if value["replacement_sha"] == value["failed_release_sha"]:
        raise LocalInstallError("preactivation recovery replacement did not change")
    if value["failed_release_sha"] != PREACTIVATION_SOURCE_RELEASE_SHA:
        raise LocalInstallError("preactivation recovery source release is not the exact pilot")
    recovery_id = value.get("recovery_id")
    if not isinstance(recovery_id, str) or not re.fullmatch(r"[0-9]{8}T[0-9]{12}Z-[0-9a-f]{8}", recovery_id):
        raise LocalInstallError("preactivation recovery id is invalid")
    archive_dir = Path(os.path.abspath(str(value["archive_dir"])))
    expected_archive = layout.preactivation_recoveries / recovery_id
    if archive_dir != expected_archive:
        raise LocalInstallError("preactivation archive path is outside the bounded lane")
    expected_paths = {
        "archive_state": archive_dir / "state",
        "backup_path": archive_dir / "supervisor.sqlite3",
        "manifest_path": archive_dir / "manifest.json",
    }
    for key, expected_path in expected_paths.items():
        if Path(os.path.abspath(str(value[key]))) != expected_path:
            raise LocalInstallError(f"preactivation {key} path is not canonical")
    fresh = Path(os.path.abspath(str(value["fresh_state"])))
    if fresh.parent != layout.root or fresh.name != f".state.preactivation.{recovery_id}":
        raise LocalInstallError("preactivation fresh state path is not canonical")
    for key in (
        "old_state_dev", "old_state_ino", "fresh_state_dev", "fresh_state_ino",
        "prior_supervisor_generation", "prior_projection_generation",
        "prior_projection_sequence", "prior_projection_revision",
    ):
        if isinstance(value.get(key), bool) or not isinstance(value.get(key), int) or int(value[key]) < 0:
            raise LocalInstallError("preactivation recovery numeric binding is invalid")
    if value.get("model_attempt_count") != 0 or value.get("model_call_count") != 0:
        raise LocalInstallError("preactivation recovery is not zero-call")
    digest = value.get("backup_sha256")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise LocalInstallError("preactivation recovery backup digest is invalid")
    if value.get("phase") != "allocating" and (
        digest == "0" * 64
        or int(value["fresh_state_dev"]) <= 0
        or int(value["fresh_state_ino"]) <= 0
    ):
        raise LocalInstallError("prepared preactivation recovery identity is incomplete")
    source_digest = value.get("source_registry_digest")
    if not isinstance(source_digest, str) or not re.fullmatch(
        r"[0-9a-f]{64}", source_digest
    ):
        raise LocalInstallError("preactivation source registry digest is invalid")
    if value.get("source_table_counts") != _PREACTIVATION_SOURCE_TABLE_COUNTS:
        raise LocalInstallError("preactivation source table counts differ")
    if (
        value.get("source_task_id") != PREACTIVATION_SOURCE_TASK_ID
        or value.get("source_workstream_id") != PREACTIVATION_SOURCE_WORKSTREAM_ID
        or value.get("source_executor_generation") != 1
        or not _bounded_evidence_id(value.get("source_thread_id"))
        or not _bounded_evidence_id(value.get("source_host_id"))
        or value.get("source_causal_fingerprint")
        != PREACTIVATION_SOURCE_CAUSAL_FINGERPRINT
        or not _bounded_evidence_id(value.get("source_followup_event_id"))
        or not _bounded_evidence_id(value.get("source_attention_event_id"))
    ):
        raise LocalInstallError("preactivation source aggregate identity differs")
    failure_ids = value.get("source_failure_event_ids")
    if (
        not isinstance(failure_ids, list)
        or len(failure_ids) != 2
        or len(set(failure_ids)) != 2
        or any(not _bounded_evidence_id(item) for item in failure_ids)
    ):
        raise LocalInstallError("preactivation source failure identities differ")
    _qualification_timestamp(value.get("created_at"))
    return dict(value)


def _require_directory_identity(
    path: Path,
    expected_dev: int,
    expected_ino: int,
    label: str,
) -> None:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise LocalInstallError(f"{label} is unavailable") from exc
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or path.is_symlink()
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
        or (metadata.st_dev, metadata.st_ino) != (expected_dev, expected_ino)
    ):
        raise LocalInstallError(f"{label} identity changed")


def _private_regular_metadata(path: Path) -> os.stat_result:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise LocalInstallError(f"private recovery file is unavailable: {path}") from exc
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_nlink != 1
    ):
        raise LocalInstallError(f"private recovery file shape is unsafe: {path}")
    return metadata


def _secure_file_sha256(path: Path) -> str:
    before = _private_regular_metadata(path)
    digest = hashlib.sha256()
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        while True:
            block = os.read(descriptor, 1024 * 1024)
            if not block:
                break
            digest.update(block)
    finally:
        os.close(descriptor)
    after = _private_regular_metadata(path)
    identity = (before.st_dev, before.st_ino, before.st_size)
    if identity != (opened.st_dev, opened.st_ino, opened.st_size) or identity != (
        after.st_dev,
        after.st_ino,
        after.st_size,
    ):
        raise LocalInstallError("private recovery file changed during digest")
    return digest.hexdigest()


def _sqlite_readonly_uri(path: Path) -> str:
    from urllib.parse import quote

    return f"file:{quote(str(Path(os.path.abspath(path))), safe='/')}?mode=ro"


def _sqlite_table_counts(connection: sqlite3.Connection) -> dict[str, int]:
    names = [
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]
    if any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) for name in names):
        raise LocalInstallError("SQLite archive contains an unsafe table name")
    return {
        name: int(connection.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0])
        for name in names
    }


def _fsync_path(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def verify_preactivation_recovery_receipt(
    receipt_path: Path,
    *,
    expected_replacement_sha: str,
    runtime_root: Path,
    require_pristine: bool = True,
    require_empty_projection: bool = True,
) -> dict[str, Any]:
    root = Path(os.path.abspath(runtime_root))
    canonical_receipt = root / "preactivation-recovery.json"
    candidate = Path(os.path.abspath(receipt_path))
    if candidate != canonical_receipt:
        raise LocalInstallError("preactivation recovery receipt is not canonical")
    raw = _read_private_proof_file(candidate, max_bytes=1_000_000)
    try:
        receipt = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LocalInstallError("preactivation recovery receipt is invalid JSON") from exc
    expected_fields = {
        "schema", "status", "recovery_id", "replacement_sha", "failed_release_sha",
        "archive_dir", "archive_state", "backup_path", "backup_sha256",
        "source_registry_digest", "source_table_counts", "source_task_id",
        "source_workstream_id", "source_executor_generation", "source_thread_id",
        "source_host_id", "source_failure_event_ids", "source_followup_event_id",
        "source_attention_event_id", "source_causal_fingerprint",
        "prior_supervisor_generation", "prior_projection_generation",
        "prior_projection_sequence", "prior_projection_revision", "model_attempt_count",
        "model_call_count", "cause_code", "old_registry_archived",
        "fresh_registry_task_count", "active_task_registry_empty", "one_shot",
        "real_model_calls", "legacy_monitor_touched", "recovered_at",
        "manifest_path", "manifest_sha256", "receipt_path",
    }
    if not isinstance(receipt, dict) or set(receipt) != expected_fields:
        raise LocalInstallError("preactivation recovery receipt fields are invalid")
    recovery_id = receipt.get("recovery_id")
    if (
        receipt.get("schema") != PREACTIVATION_RECOVERY_RECEIPT_SCHEMA
        or receipt.get("status") != "recovered"
        or receipt.get("replacement_sha") != expected_replacement_sha
        or not isinstance(recovery_id, str)
        or not re.fullmatch(r"[0-9]{8}T[0-9]{12}Z-[0-9a-f]{8}", recovery_id)
        or receipt.get("failed_release_sha") != PREACTIVATION_SOURCE_RELEASE_SHA
        or receipt.get("source_task_id") != PREACTIVATION_SOURCE_TASK_ID
        or receipt.get("source_workstream_id") != PREACTIVATION_SOURCE_WORKSTREAM_ID
        or receipt.get("source_executor_generation") != 1
        or not _bounded_evidence_id(receipt.get("source_thread_id"))
        or not _bounded_evidence_id(receipt.get("source_host_id"))
        or receipt.get("source_causal_fingerprint")
        != PREACTIVATION_SOURCE_CAUSAL_FINGERPRINT
        or not _lower_hex(receipt.get("source_registry_digest"), 64)
        or receipt.get("source_table_counts") != _PREACTIVATION_SOURCE_TABLE_COUNTS
        or receipt.get("model_attempt_count") != 0
        or receipt.get("model_call_count") != 0
        or receipt.get("cause_code") != "legacy_empty_thread_read_before_call_intent"
        or receipt.get("old_registry_archived") is not True
        or receipt.get("fresh_registry_task_count") != 0
        or receipt.get("active_task_registry_empty") is not True
        or receipt.get("one_shot") is not True
        or receipt.get("real_model_calls") != 0
        or receipt.get("legacy_monitor_touched") is not False
        or receipt.get("receipt_path") != str(canonical_receipt)
    ):
        raise LocalInstallError("preactivation recovery receipt identity is invalid")
    failure_ids = receipt.get("source_failure_event_ids")
    if (
        not isinstance(failure_ids, list)
        or len(failure_ids) != 2
        or len(set(failure_ids)) != 2
        or any(not _bounded_evidence_id(item) for item in failure_ids)
        or not _bounded_evidence_id(receipt.get("source_followup_event_id"))
        or not _bounded_evidence_id(receipt.get("source_attention_event_id"))
    ):
        raise LocalInstallError("preactivation recovery source event binding is invalid")
    _qualification_timestamp(receipt.get("recovered_at"))
    archive_dir = root / "backups" / "preactivation-recoveries" / recovery_id
    archive_state = archive_dir / "state"
    backup = archive_dir / "supervisor.sqlite3"
    manifest = archive_dir / "manifest.json"
    if (
        receipt.get("archive_dir") != str(archive_dir)
        or receipt.get("archive_state") != str(archive_state)
        or receipt.get("backup_path") != str(backup)
        or receipt.get("manifest_path") != str(manifest)
    ):
        raise LocalInstallError("preactivation recovery receipt paths are outside the archive lane")
    archive_metadata = archive_dir.lstat()
    state_metadata = archive_state.lstat()
    if (
        not stat.S_ISDIR(archive_metadata.st_mode)
        or archive_metadata.st_uid != os.geteuid()
        or stat.S_IMODE(archive_metadata.st_mode) != 0o700
        or not stat.S_ISDIR(state_metadata.st_mode)
        or state_metadata.st_uid != os.geteuid()
        or stat.S_IMODE(state_metadata.st_mode) != 0o700
        or archive_dir.is_symlink()
        or archive_state.is_symlink()
    ):
        raise LocalInstallError("preactivation recovery archive is not private")
    if _secure_file_sha256(backup) != receipt.get("backup_sha256"):
        raise LocalInstallError("preactivation recovery backup digest mismatch")
    if (
        _sqlite_logical_digest(connection_path=backup)
        != receipt.get("source_registry_digest")
        or _sqlite_logical_digest(
            connection_path=archive_state / "supervisor.sqlite3"
        )
        != receipt.get("source_registry_digest")
    ):
        raise LocalInstallError("preactivation recovery source registry digest mismatch")
    if _secure_file_sha256(manifest) != receipt.get("manifest_sha256"):
        raise LocalInstallError("preactivation recovery manifest digest mismatch")
    manifest_payload = _read_json(manifest)
    expected_manifest = {
        key: value
        for key, value in receipt.items()
        if key not in {"schema", "manifest_path", "manifest_sha256", "receipt_path"}
    }
    expected_manifest["schema"] = PREACTIVATION_RECOVERY_SCHEMA
    if manifest_payload != expected_manifest:
        raise LocalInstallError("preactivation recovery manifest differs from receipt")
    transaction = _validated_preactivation_journal(
        _read_json(archive_dir / "transaction.json"),
        LocalInstallLayout.resolve(root),
    )
    if (
        transaction.get("phase") != "committed"
        or transaction.get("recovery_id") != recovery_id
        or transaction.get("replacement_sha") != expected_replacement_sha
        or transaction.get("backup_sha256") != receipt.get("backup_sha256")
        or transaction.get("source_registry_digest")
        != receipt.get("source_registry_digest")
    ):
        raise LocalInstallError("preactivation recovery transaction is not committed")
    expected = {
        "supervisor_generation": receipt["prior_supervisor_generation"],
        "projection_generation": receipt["prior_projection_generation"],
        "projection_sequence": receipt["prior_projection_sequence"],
        "projection_revision": receipt["prior_projection_revision"],
    }
    if require_pristine:
        _verify_fresh_recovery_state(root / "state", expected=expected)
        current_watermarks = {
            "current_supervisor_generation": int(receipt["prior_supervisor_generation"]),
            "current_projection_generation": int(receipt["prior_projection_generation"]),
            "current_projection_sequence": int(receipt["prior_projection_sequence"]),
            "current_projection_revision": int(receipt["prior_projection_revision"]),
        }
    else:
        current_watermarks = _verify_recovered_watermarks_not_regressed(
            root / "state",
            expected=expected,
            require_empty_projection=require_empty_projection,
        )
    qualification_copy = (
        root
        / "qualifications"
        / f"{expected_replacement_sha}.preactivation-recovery.json"
    )
    if _read_private_proof_file(qualification_copy, max_bytes=1_000_000) != raw:
        raise LocalInstallError(
            "preactivation recovery qualification copy differs from canonical receipt"
        )
    return {
        "replacement_sha": receipt["replacement_sha"],
        "failed_release_sha": receipt["failed_release_sha"],
        "recovery_id": receipt["recovery_id"],
        "archive_dir": receipt["archive_dir"],
        "manifest_path": receipt["manifest_path"],
        "backup_path": receipt["backup_path"],
        "backup_sha256": receipt["backup_sha256"],
        "prior_supervisor_generation": receipt["prior_supervisor_generation"],
        "prior_projection_generation": receipt["prior_projection_generation"],
        "prior_projection_sequence": receipt["prior_projection_sequence"],
        "prior_projection_revision": receipt["prior_projection_revision"],
        "model_attempt_count": 0,
        "model_call_count": 0,
        "legacy_monitor_touched": False,
        **current_watermarks,
    }


def _read_json(path: Path) -> dict[str, Any]:
    try:
        raw = _read_optional_regular_file(path, max_bytes=1_000_000)
        if raw is None:
            raise LocalInstallError(f"local install metadata is missing: {path}")
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LocalInstallError(f"invalid local install metadata: {path}") from exc
    if not isinstance(payload, dict):
        raise LocalInstallError(f"local install metadata is not an object: {path}")
    return payload


def _read_optional_regular_file(path: Path, *, max_bytes: int) -> bytes | None:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise LocalInstallError(f"local metadata path is unavailable: {path}") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise LocalInstallError(f"local metadata path must be a regular non-symlink file: {path}")
    if metadata.st_uid != os.geteuid() or metadata.st_size > max_bytes:
        raise LocalInstallError(f"local metadata ownership or size is unsafe: {path}")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
        try:
            opened = os.fstat(descriptor)
            payload = os.read(descriptor, max_bytes + 1)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise LocalInstallError(f"local metadata could not be read safely: {path}") from exc
    if (
        opened.st_dev != metadata.st_dev
        or opened.st_ino != metadata.st_ino
        or opened.st_uid != os.geteuid()
        or len(payload) > max_bytes
    ):
        raise LocalInstallError(f"local metadata changed during secure read: {path}")
    return payload


def _restore_optional_regular_file(path: Path, payload: bytes | None, *, mode: int) -> None:
    if payload is not None:
        _atomic_write_bytes(path, payload, mode=mode)
        return
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise LocalInstallError(f"automatic rollback found unsafe local metadata: {path}")
    path.unlink()
    _fsync_directory(path.parent)


def _readiness_generation(payload: Mapping[str, Any] | None) -> int | None:
    if payload is None:
        return None
    generation = payload.get("generation")
    if isinstance(generation, bool) or not isinstance(generation, int) or generation < 1:
        return None
    return generation


def _legacy_launchd_absent_probe(label: str) -> bool:
    if label != LEGACY_MONITOR_LABEL:
        return False
    try:
        completed = subprocess.run(
            ["/bin/launchctl", "print", f"gui/{os.getuid()}/{label}"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    # macOS launchctl uses ESRCH (113) for an absent service.  Authentication,
    # domain and transport failures are not absence proof.
    return completed.returncode == 113


def _legacy_artifacts_absent_probe() -> bool:
    # lexists rejects a broken symlink as well as a regular file.  An absence
    # qualification must never let a newly introduced legacy launch artifact
    # coexist with the activated v2 writer.
    return not os.path.lexists(LEGACY_MONITOR_DB) and not os.path.lexists(LEGACY_MONITOR_PLIST)


def _process_identity_probe(
    pid: int,
    expected_python: Path,
    expected_entrypoint: Path,
    expected_host: str,
    expected_port: int,
) -> bool:
    if pid < 1 or expected_host != "127.0.0.1" or expected_port != DEFAULT_PORT:
        return False
    try:
        command = subprocess.run(
            ["/bin/ps", "-ww", "-p", str(pid), "-o", "command="],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if command.returncode != 0:
            return False
        command_line = command.stdout.strip()
        if str(expected_python) not in command_line or str(expected_entrypoint) not in command_line:
            return False
        lsof = Path("/usr/sbin/lsof")
        if not lsof.is_file():
            return False
        listener = subprocess.run(
            [
                str(lsof), "-nP", "-a", "-p", str(pid),
                f"-iTCP:{expected_port}", "-sTCP:LISTEN", "-Fpn",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        listener_lines = set(listener.stdout.splitlines())
        if listener.returncode != 0 or f"p{pid}" not in listener_lines or not any(
            line.startswith(f"n{expected_host}:{expected_port}") for line in listener_lines
        ):
            return False
        cwd = subprocess.run(
            [str(lsof), "-nP", "-a", "-p", str(pid), "-d", "cwd", "-Fn"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if cwd.returncode != 0 or f"n{expected_entrypoint.parents[1]}" not in set(cwd.stdout.splitlines()):
            return False
    except (OSError, subprocess.SubprocessError):
        return False
    return True


def _http_readiness_probe() -> Mapping[str, Any] | None:
    connection = http.client.HTTPConnection("127.0.0.1", DEFAULT_PORT, timeout=1.0)
    try:
        connection.request("GET", "/api/v2/readiness", headers={"Accept": "application/json"})
        response = connection.getresponse()
        payload = response.read(MAX_READINESS_BYTES + 1)
        if response.status != 200 or len(payload) > MAX_READINESS_BYTES:
            return None
        decoded = json.loads(payload.decode("utf-8"))
        return decoded if isinstance(decoded, Mapping) else None
    except (OSError, http.client.HTTPException, UnicodeDecodeError, json.JSONDecodeError):
        return None
    finally:
        connection.close()
