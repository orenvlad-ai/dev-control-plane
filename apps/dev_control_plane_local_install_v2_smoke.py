"""Filesystem/fake-launchd smoke for safe local Supervisor v2 lifecycle."""

from __future__ import annotations

import ast
from dataclasses import asdict
import fcntl
import hashlib
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
from typing import Any
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (SRC, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dev_control_plane.local_install import (  # noqa: E402
    LocalInstallError,
    LocalInstaller,
    LocalInstallLayout,
    verify_preactivation_recovery_receipt,
)
import dev_control_plane.local_install as local_install_module  # noqa: E402
from dev_control_plane.migration import (  # noqa: E402
    archive_legacy_monitor,
    prove_legacy_absence,
)
from dev_control_plane.v2_suite_contract import (  # noqa: E402
    AUTHORITATIVE_CHECK_COUNT,
    AUTHORITATIVE_SMOKES,
)
from dev_control_plane.supervisor_registry import SupervisorRegistry  # noqa: E402
from apps.dev_control_plane_supervisor_v2 import _read_activation_nonce  # noqa: E402


APPROVED_ORIGIN = "https://github.com/orenvlad-ai/dev-control-plane.git"


class FakeLaunchctl:
    def __init__(self) -> None:
        self.loaded = False
        self.pid = 4242
        self.generation = 0
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, arguments: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        command = tuple(str(item) for item in arguments)
        self.calls.append(command)
        action = command[1] if len(command) > 1 else ""
        if action == "print":
            stdout = f"pid = {self.pid}\n" if self.loaded else ""
            return subprocess.CompletedProcess(command, 0 if self.loaded else 113, stdout, "")
        if action == "bootout":
            self.loaded = False
            return subprocess.CompletedProcess(command, 0, "", "")
        if action == "bootstrap":
            self.loaded = True
            self.generation += 1
            return subprocess.CompletedProcess(command, 0, "", "")
        if action == "kickstart":
            return subprocess.CompletedProcess(command, 0 if self.loaded else 113, "", "")
        raise AssertionError(f"unexpected command: {command}")


class AdvancingClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        self.value += 0.02
        return self.value


class ReleaseAwareReadiness:
    def __init__(self, layout: LocalInstallLayout, launchctl: FakeLaunchctl) -> None:
        self.layout = layout
        self.launchctl = launchctl
        self.current_link = layout.current
        self.failed_release: str | None = None
        self.saw_failed_release = False

    def __call__(self) -> dict[str, Any] | None:
        if not self.current_link.is_symlink():
            return None
        release = Path(os.readlink(self.current_link)).name
        if release == self.failed_release:
            self.saw_failed_release = True
            return None
        release_path = Path(os.readlink(self.current_link))
        generation = self.launchctl.generation
        nonce = self.layout.activation_nonce.read_bytes()
        return {
            "ready": True,
            "service_role": "local_supervisor_v2",
            "generation": generation,
            "single_writer": True,
            "activation_identity": {
                "schema": "dev-control-plane/runtime-activation/v2",
                "release_sha": release,
                "activation_nonce_sha256": hashlib.sha256(nonce).hexdigest(),
                "pid": 4242,
                "python_executable": str(Path(sys.executable).resolve()),
                "entrypoint": str((release_path / "apps" / "dev_control_plane_supervisor_v2.py").resolve()),
                "bind_host": "127.0.0.1",
                "bind_port": 8766,
                "supervisor_generation": generation,
                "supervisor_owner_id": f"fake-owner-{generation}",
            },
        }


class DriftAfterGateInstaller(LocalInstaller):
    """Inject working-tree drift after the first source gate."""

    def _copy_release(self, source: Path, release: Path, sha: str) -> None:
        super()._copy_release(source, release, sha)
        (source / "README.md").write_text("uncommitted drift after source gate\n", encoding="utf-8")


class SimulatedProcessCrash(BaseException):
    """Bypass normal Exception rollback to exercise next-process recovery."""


def _git(path: Path, *args: str) -> str:
    completed = subprocess.run(["git", *args], cwd=path, check=True, capture_output=True, text=True)
    return completed.stdout.strip()


def _commit(source: Path, value: int, *, publish: bool = True) -> str:
    (source / "src" / "fixture.py").write_text(f"VALUE = {value}\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=source, check=True)
    subprocess.run(["git", "commit", "-qm", f"fixture-{value}"], cwd=source, check=True)
    sha = _git(source, "rev-parse", "HEAD")
    if publish:
        subprocess.run(
            ["git", "push", "--quiet", "--force", "origin", f"{sha}:refs/heads/main"],
            cwd=source,
            check=True,
        )
    return sha


def _expect_local_error(callable_value: Any, expected_fragment: str) -> None:
    try:
        callable_value()
    except LocalInstallError as exc:
        if expected_fragment not in str(exc):
            raise AssertionError(f"unexpected LocalInstallError: {exc}") from exc
    else:
        raise AssertionError(f"expected LocalInstallError containing {expected_fragment!r}")


def _expect_runtime_error(callable_value: Any, expected_fragment: str) -> None:
    try:
        callable_value()
    except RuntimeError as exc:
        if expected_fragment not in str(exc):
            raise AssertionError(f"unexpected RuntimeError: {exc}") from exc
    else:
        raise AssertionError(f"expected RuntimeError containing {expected_fragment!r}")


def _qualification(
    layout: LocalInstallLayout,
    sha: str,
    *,
    supervisor_generation: int = 7,
    include_preactivation_recovery: bool = False,
) -> Path:
    layout.qualifications.mkdir(parents=True, exist_ok=True, mode=0o700)
    evidence: dict[str, tuple[str, bytes]] = {}
    legacy_source = layout.root / f"legacy-{sha}.sqlite3"
    legacy_connection = sqlite3.connect(legacy_source)
    legacy_connection.execute(
        "CREATE TABLE sessions (alive INTEGER, hidden INTEGER, monitoring INTEGER, pr_state TEXT, repository TEXT)"
    )
    legacy_connection.execute("INSERT INTO sessions VALUES (0, 0, 1, 'MERGED', 'owner/repo')")
    legacy_connection.commit()
    legacy_connection.close()
    legacy_source.chmod(0o600)
    with mock.patch(
        "dev_control_plane.migration.inspect_launchd",
        return_value={"loaded": False, "pid": None},
    ):
        archive = archive_legacy_monitor(
            destination=layout.backups / sha,
            source_db=legacy_source,
            label="com.orenvlad.codex-session-monitor",
        )
    observed = datetime.now(timezone.utc)
    now = observed.isoformat().replace("+00:00", "Z")
    activation = {
        "schema": "dev-control-plane/runtime-activation/v2",
        "release_sha": sha,
        "activation_nonce_sha256": hashlib.sha256(layout.activation_nonce.read_bytes()).hexdigest(),
        "pid": 4242,
        "python_executable": str(Path(sys.executable).resolve()),
        "entrypoint": str(
            (layout.releases / sha / "apps" / "dev_control_plane_supervisor_v2.py").resolve()
        ),
        "bind_host": "127.0.0.1",
        "bind_port": 8766,
        "supervisor_generation": supervisor_generation,
        "supervisor_owner_id": f"smoke-owner-{supervisor_generation}",
    }
    runtime_evidence = {
        "schema": "dev-control-plane/runtime-qualification-evidence/v2",
        "status": "passed",
        "release_sha": sha,
        "observed_at": now,
        "app_server_canary": {
            "schema": "dev-control-plane/app-server-canary-evidence/v2",
            "status": "passed",
            "supervisor_generation": supervisor_generation,
            "supervisor_host": "smoke-mac-host",
            "binary": "/Applications/ChatGPT.app/Contents/Resources/codex",
            "transport": "stdio",
            "websocket_used": False,
            "task_id": "task-smoke-pilot",
            "workstream_id": "workstream-smoke-pilot",
            "thread_id": "thread-smoke-pilot",
            "model": "gpt-5.6-sol",
            "reasoning": "ultra",
            "executor_generation": 1,
            "turn_ids": ["turn-smoke-pilot"],
            "item_ids": ["item-smoke-pilot"],
            "lifecycle_event_count": 3,
            "lifecycle_digest": "b" * 64,
            "terminal_turn_ids": ["turn-smoke-pilot"],
            "model_attempt_count": 1,
            "model_call_count": 1,
            "single_attempt_canary": True,
            "contract_kind": "checkpoint",
            "progress_percent": 40,
            "checkpoint_event_id": "checkpoint-smoke-pilot",
            "checkpoint_payload_sha256": "c" * 64,
        },
        "staged_runtime": {
            "schema": "dev-control-plane/staged-runtime-evidence/v2",
            "status": "passed",
            "private_socket": True,
            "socket_mode": "0600",
            "socket_owner_uid": os.geteuid(),
            "single_writer": True,
            "supervisor_generation": supervisor_generation,
            "supervisor_owner_id": f"smoke-owner-{supervisor_generation}",
            "lease_expires_at_epoch": observed.timestamp() + 600,
            "final_attention_deferred": True,
            "additional_model_calls": 0,
            "activation_identity": activation,
        },
    }
    runtime_material = json.dumps(
        {"qualification_evidence": runtime_evidence}, sort_keys=True
    ).encode()
    materials = {
        "suite": (
            json.dumps(
                {
                    "schema": "dev-control-plane/v2-suite-evidence/v2",
                    "status": "passed",
                    "suite": "orchestrator_v2",
                    "commit_sha": sha,
                    "generated_at": now,
                    "checks": AUTHORITATIVE_CHECK_COUNT,
                    "smokes": [
                        {"path": path, "status": "passed", "seconds": 0.01}
                        for path in AUTHORITATIVE_SMOKES
                    ],
                    "seconds": 0.1,
                    "real_model_calls": 0,
                },
                sort_keys=True,
            )
            + "\n"
        ).encode(),
        "shadow": (
            "\n".join(
                json.dumps(item, sort_keys=True)
                for item in (
                    asdict(archive),
                    {
                        "schema": "dev-control-plane/legacy-retirement/v2",
                        "status": "retired",
                        "label": "com.orenvlad.codex-session-monitor",
                        "was_loaded": False,
                        "loaded_after": False,
                        "backup_sha256": archive.backup_sha256,
                        "plist_preserved": True,
                        "source_state_preserved": True,
                        "retired_at": now,
                    },
                    {
                        "schema": "dev-control-plane/legacy-shadow/v2",
                        "available": True,
                        "authoritative": False,
                        "integrity": "ok",
                        "active_observed_sessions": 0,
                        "open_pr_observations": 0,
                        "active_repository_count": 0,
                        "captured_at": now,
                    },
                )
            )
            + "\n"
        ).encode(),
        "canary": runtime_material,
        "staged": runtime_material,
    }
    for name, material in materials.items():
        filename = f"{sha}.{name}.json"
        path = layout.qualifications / filename
        path.write_bytes(material)
        path.chmod(0o600)
        evidence[name] = (filename, material)
    if include_preactivation_recovery:
        recovery_path = (
            layout.qualifications / f"{sha}.preactivation-recovery.json"
        )
        recovery_material = recovery_path.read_bytes()
        evidence["recovery"] = (recovery_path.name, recovery_material)

    def binding(name: str) -> dict[str, Any]:
        filename, material = evidence[name]
        return {
            "status": "passed",
            "evidence_file": filename,
            "evidence_sha256": hashlib.sha256(material).hexdigest(),
        }

    payload = {
        "schema": "dev-control-plane/local-qualification/v2",
        "commit_sha": sha,
        "created_at": now,
        "suite": {**binding("suite"), "real_model_calls": 0},
        "shadow": {
            **binding("shadow"),
            "authoritative": False,
            "legacy_mutation_authority": "stopped",
            "real_model_calls": 0,
        },
        "app_server_canary": {
            **binding("canary"),
            "binary": "/Applications/ChatGPT.app/Contents/Resources/codex",
            "transport": "stdio",
            "websocket_used": False,
            "model": "gpt-5.6-sol",
            "reasoning": "ultra",
            "exact_thread_event_control": True,
            "contract_kind": "checkpoint",
            "progress_percent": 40,
            "model_attempt_count": 1,
            "model_call_count": 1,
            "single_attempt_canary": True,
            "real_model_calls": 1,
        },
        "staged_runtime": {
            **binding("staged"),
            "private_socket": True,
            "single_writer": True,
            "final_attention_deferred": True,
            "real_model_calls": 0,
        },
    }
    if include_preactivation_recovery:
        payload["preactivation_recovery"] = {
            **binding("recovery"),
            "source_release_sha": local_install_module.PREACTIVATION_SOURCE_RELEASE_SHA,
            "one_shot": True,
            "active_task_registry_empty": True,
            "real_model_calls": 0,
        }
    manifest = layout.qualifications / f"{sha}.qualification.json"
    manifest.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    manifest.chmod(0o600)
    return manifest


def _release_digest_without_manifest(release: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in release.rglob("*") if item.is_file() and item.name != "release.json"):
        digest.update(path.relative_to(release).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _failed_preactivation_registry_fixture(
    state: Path,
) -> None:
    """Build the exact sanitized shape of the stopped e0 bootstrap aggregate."""

    task_id = local_install_module.PREACTIVATION_SOURCE_TASK_ID
    workstream_id = local_install_module.PREACTIVATION_SOURCE_WORKSTREAM_ID
    failed_sha = local_install_module.PREACTIVATION_SOURCE_RELEASE_SHA
    fingerprint = local_install_module.PREACTIVATION_SOURCE_CAUSAL_FINGERPRINT
    thread_id = "019fd08c-6288-7cb2-a464-57de059c4f06"
    host_id = "mac-host:fixture"
    state.mkdir(parents=True, mode=0o700, exist_ok=True)
    state.chmod(0o700)
    workspace_root = state / "managed_workspaces"
    workspace_root.mkdir(mode=0o700, exist_ok=True)
    workspace = workspace_root / "rollout-pilot"
    workspace.mkdir(mode=0o700)
    database = state / "supervisor.sqlite3"
    SupervisorRegistry(database)
    now = 1_785_910_000.0
    connection = sqlite3.connect(database)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            "UPDATE supervisor_lease SET generation=1, owner_id=NULL, lease_token=NULL, expires_at=0, updated_at=? WHERE singleton=1",
            (now,),
        )
        connection.execute(
            "UPDATE projection_transport_state SET generation=1, sequence=5, revision=5, updated_at=? WHERE singleton=1",
            (now,),
        )
        passport_json = json.dumps(
            {
                "task_id": task_id,
                "revision": 2,
                "workstream_ids": [workstream_id],
                "resources": [f"qualification:{failed_sha}"],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        connection.execute(
            "INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?)",
            (
                task_id,
                2,
                "parked",
                passport_json,
                hashlib.sha256(passport_json.encode()).hexdigest(),
                now,
                now,
                1,
            ),
        )
        contract_json = json.dumps(
            {"schema": "dev-control-plane/workstream/v2", "workstream_id": workstream_id},
            sort_keys=True,
            separators=(",", ":"),
        )
        connection.execute(
            "INSERT INTO workstreams VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                workstream_id,
                1,
                task_id,
                2,
                "parked",
                contract_json,
                hashlib.sha256(contract_json.encode()).hexdigest(),
                1,
                now,
                now,
                1,
            ),
        )
        connection.execute(
            "INSERT INTO executor_bindings VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                task_id,
                workstream_id,
                1,
                thread_id,
                host_id,
                "gpt-5.6-sol",
                "ultra",
                "active",
                None,
                "6ae38c72fe42d95c0b88452c6d71d1185cae114bb2fb9c695ae1aa612f4704ae",
                None,
                now,
                now,
                1,
            ),
        )
        connection.execute(
            "INSERT INTO workspace_bindings VALUES (?,?,?,?,?,?)",
            (
                task_id,
                workstream_id,
                str(workspace),
                hashlib.sha256(str(workspace).encode()).hexdigest(),
                now,
                1,
            ),
        )

        def event(
            event_id: str,
            event_type: str,
            payload: dict[str, Any],
            created_at: float,
        ) -> None:
            payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
            connection.execute(
                "INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    event_id,
                    task_id,
                    workstream_id,
                    event_type,
                    payload_json,
                    hashlib.sha256(payload_json.encode()).hexdigest(),
                    1,
                    1,
                    created_at,
                ),
            )
        event(
            "incident-one",
            "incident_policy",
            {
                "attempt": 1,
                "decision": "retry_current_executor",
                "status": "retrying",
                "error_code": "codex_remote_error",
                "fingerprint": fingerprint,
            },
            now + 1,
        )
        event(
            "incident-two",
            "incident_policy",
            {
                "attempt": 2,
                "decision": "park_workstream",
                "status": "missing_verified_checkpoint",
                "error_code": "codex_remote_error",
                "fingerprint": fingerprint,
            },
            now + 2,
        )
        for index, event_type in enumerate(
            (
                "executor_started",
                "release_candidate_admitted",
                "release_candidate_registered",
                "release_wait",
                "target_lane_closure_completed",
                "target_lane_closure_pending",
            ),
            start=3,
        ):
            event(
                f"source-event-{index}",
                event_type,
                {"event_type": event_type, "fixture": True},
                now + index,
            )

        inbox_sources = (
            "codex-thread-start-worker",
            "codex-worker",
            "codex-worker",
            "deterministic-scheduler",
            "private-unix-command:codex-followup",
            "private-unix-command:release-candidate-registration",
            "private-unix-command:start-executor",
            "supervisor-release-candidate-intake",
            "supervisor-target-lane-closure-reconciler",
            "supervisor-target-lane-closure-worker",
        )
        for index, source_name in enumerate(inbox_sources):
            payload_json = json.dumps(
                {"fixture": True, "index": index, "source": source_name},
                sort_keys=True,
                separators=(",", ":"),
            )
            connection.execute(
                "INSERT INTO inbox VALUES (?,?,?,?,?,?,?,?)",
                (
                    f"source-message-{index}",
                    source_name,
                    payload_json,
                    hashlib.sha256(payload_json.encode()).hexdigest(),
                    "processed",
                    1,
                    now + index,
                    now + index + 0.5,
                ),
            )

        def outbox(
            event_id: str,
            kind: str,
            payload: dict[str, Any],
            *,
            state_value: str,
            attempts: int,
            last_error: str | None,
            created_at: float,
            task_owner: str | None = task_id,
        ) -> None:
            payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
            connection.execute(
                "INSERT INTO outbox(event_id,kind,payload_json,payload_digest,task_id,coalescible,coalesce_key,state,attempts,available_at,claim_token,claimed_by,claimed_generation,claimed_until,delivered_at,last_error,writer_generation,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    event_id,
                    kind,
                    payload_json,
                    hashlib.sha256(payload_json.encode()).hexdigest(),
                    task_owner,
                    0,
                    None,
                    state_value,
                    attempts,
                    now,
                    None,
                    None,
                    None,
                    None,
                    now if state_value == "delivered" else None,
                    last_error,
                    1,
                    created_at,
                    created_at,
                ),
            )

        outbox(
            "thread-start",
            "codex_thread_start",
            {
                "schema": "dev-control-plane/codex-thread-start/v2",
                "task_id": task_id,
                "workstream_id": workstream_id,
                "thread_id": thread_id,
                "host_id": host_id,
            },
            state_value="delivered",
            attempts=1,
            last_error=None,
            created_at=now,
        )
        outbox(
            "canary-followup",
            "codex_followup",
            {
                "call_policy": "single_attempt_canary",
                "output_contract": "checkpoint",
                "model_attempt_count": 0,
                "call_intent": None,
                "task_id": task_id,
                "workstream_id": workstream_id,
                "thread_id": thread_id,
                "host_id": host_id,
                "causal_fingerprint": fingerprint,
            },
            state_value="delivered",
            attempts=2,
            last_error="codex_remote_error",
            created_at=now + 1,
        )
        outbox(
            "serious-stall",
            "curator_attention",
            {
                "kind": "serious_stall",
                "task_id": task_id,
                "workstream_id": workstream_id,
            },
            state_value="pending",
            attempts=0,
            last_error=None,
            created_at=now + 2,
        )
        for index in range(4):
            outbox(
                f"projection-dirty-delivered-{index}",
                "projection_dirty",
                {"fixture": True, "index": index, "state": "delivered"},
                state_value="delivered",
                attempts=1,
                last_error=None,
                created_at=now + 10 + index,
            )
            outbox(
                f"projection-dirty-superseded-{index}",
                "projection_dirty",
                {"fixture": True, "index": index, "state": "superseded"},
                state_value="superseded",
                attempts=0,
                last_error=None,
                created_at=now + 20 + index,
            )
        for index in range(5):
            outbox(
                f"projection-snapshot-{index}",
                "projection_snapshot",
                {"fixture": True, "revision": index + 1},
                state_value="delivered",
                attempts=1,
                last_error=None,
                created_at=now + 30 + index,
                task_owner=None,
            )
        outbox(
            "release-candidate-intake",
            "release_candidate_intake",
            {"fixture": True, "kind": "release_candidate_intake"},
            state_value="delivered",
            attempts=1,
            last_error=None,
            created_at=now + 40,
        )
        outbox(
            "target-lane-closure",
            "target_lane_closure",
            {"fixture": True, "kind": "target_lane_closure"},
            state_value="delivered",
            attempts=1,
            last_error=None,
            created_at=now + 41,
        )
        connection.commit()
    finally:
        connection.close()
    database.chmod(0o600)


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        temp = Path(temporary)
        absence_source = temp / "clean-mac" / "monitor.sqlite3"
        absence_plist = temp / "clean-mac" / "legacy.plist"
        with mock.patch(
            "dev_control_plane.migration.inspect_launchd",
            return_value={"loaded": False, "pid": None},
        ):
            absence = prove_legacy_absence(
                destination=temp / "absence-backups" / "fixture",
                source_db=absence_source,
                plist_path=absence_plist,
            )
        absence_raw = (json.dumps(asdict(absence), sort_keys=True) + "\n").encode()
        absence_observed = datetime.now(timezone.utc)
        with (
            mock.patch.object(local_install_module, "LEGACY_MONITOR_DB", absence_source),
            mock.patch.object(local_install_module, "LEGACY_MONITOR_PLIST", absence_plist),
        ):
            assert local_install_module._validate_shadow_qualification_evidence(
                absence_raw,
                backups_root=(temp / "absence-backups").resolve(),
                qualification_created_at=absence_observed,
                validation_now=absence_observed,
                require_fresh=True,
            ) is True
        nonce_fixture = temp / "activation-nonce.bin"
        nonce_fixture.write_bytes(b"n" * 64)
        nonce_fixture.chmod(0o600)
        nonce_fixture = nonce_fixture.resolve()
        assert _read_activation_nonce(nonce_fixture) == b"n" * 64
        nonce_hardlink = temp / "activation-nonce-hardlink.bin"
        os.link(nonce_fixture, nonce_hardlink)
        _expect_runtime_error(
            lambda: _read_activation_nonce(nonce_fixture),
            "missing or not private",
        )
        nonce_hardlink.unlink()
        origin_store = temp / "origin.git"
        subprocess.run(["git", "init", "--bare", "-q", str(origin_store)], check=True)
        source = temp / "source"
        source.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=source, check=True)
        subprocess.run(["git", "config", "user.email", "smoke@example.invalid"], cwd=source, check=True)
        subprocess.run(["git", "config", "user.name", "Smoke"], cwd=source, check=True)
        subprocess.run(["git", "remote", "add", "origin", APPROVED_ORIGIN], cwd=source, check=True)
        # Keep the production allowlisted origin string while routing this
        # hermetic smoke's Git transport to a local bare remote.
        subprocess.run(
            [
                "git",
                "config",
                f"url.{origin_store.resolve().as_uri()}.insteadOf",
                APPROVED_ORIGIN,
            ],
            cwd=source,
            check=True,
        )
        for directory in ("apps", "src", "docs", "configs", "deploy"):
            (source / directory).mkdir()
        (source / "apps" / "dev_control_plane_supervisor_v2.py").write_text("print('fixture')\n", encoding="utf-8")
        (source / "AGENTS.md").write_text("fixture\n", encoding="utf-8")
        (source / "README.md").write_text("fixture\n", encoding="utf-8")
        first_sha = _commit(source, 1)

        victim_runtime = temp / "victim-runtime"
        victim_runtime.mkdir(mode=0o755)
        linked_runtime = temp / "linked-runtime"
        linked_runtime.symlink_to(victim_runtime, target_is_directory=True)
        _expect_local_error(
            lambda: LocalInstallLayout.resolve(
                linked_runtime,
                launch_agents_dir=temp / "safe-agents",
            ),
            "runtime root must not be a symlink",
        )
        assert stat.S_IMODE(victim_runtime.stat().st_mode) == 0o755
        assert not (victim_runtime / "releases").exists()

        victim_agents = temp / "victim-agents"
        victim_agents.mkdir(mode=0o755)
        linked_agents = temp / "linked-agents"
        linked_agents.symlink_to(victim_agents, target_is_directory=True)
        _expect_local_error(
            lambda: LocalInstallLayout.resolve(
                temp / "safe-runtime",
                launch_agents_dir=linked_agents,
            ),
            "LaunchAgents directory must not be a symlink",
        )
        assert stat.S_IMODE(victim_agents.stat().st_mode) == 0o755

        def hermetic_source_gate(
            observed_source: Path,
            *,
            expected_sha: str | None,
            require_origin_main: bool,
        ) -> str:
            if _git(observed_source, "status", "--porcelain"):
                raise LocalInstallError("source working tree is not clean")
            sha = _git(observed_source, "rev-parse", "HEAD")
            if expected_sha and sha != expected_sha:
                raise LocalInstallError("source HEAD does not match expected merged SHA")
            if require_origin_main:
                completed = subprocess.run(
                    ["git", "--git-dir", str(origin_store), "rev-parse", "refs/heads/main"],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                if completed.returncode != 0:
                    raise LocalInstallError("Git source gate failed: fetch")
                if sha != completed.stdout.strip():
                    raise LocalInstallError("source HEAD is not exact origin/main")
            return sha

        # The only supported preactivation recovery archives the exact legacy
        # zero-call pilot and seeds monotonic transport/fencing watermarks into
        # an otherwise pristine registry.  It does not touch launchd or the
        # stopped legacy observer.
        recovery_layout = LocalInstallLayout.resolve(
            temp / "preactivation-runtime",
            launch_agents_dir=temp / "preactivation-agents",
        )
        recovery_launchctl = FakeLaunchctl()
        recovery_installer = LocalInstaller(
            recovery_layout,
            command_runner=recovery_launchctl,
            source_gate=hermetic_source_gate,
            readiness_probe=lambda: None,
        )
        recovery_installer.install(
            source_root=source,
            expected_sha=first_sha,
            require_origin_main=True,
            activate=False,
        )
        failed_sha = local_install_module.PREACTIVATION_SOURCE_RELEASE_SHA
        _failed_preactivation_registry_fixture(recovery_layout.state)

        def attempt_supervisor_start_guard() -> None:
            with local_install_module.preactivation_supervisor_start_guard(
                recovery_layout.state
            ):
                pass

        with local_install_module._preactivation_lifecycle_lock(
            recovery_layout.root,
            nonblocking=False,
            reject_active_journal=False,
        ):
            _expect_local_error(
                attempt_supervisor_start_guard,
                "preactivation recovery excludes Supervisor startup",
            )
        recovery_layout.preactivation_recovery_journal.write_text(
            "{}\n", encoding="utf-8"
        )
        recovery_layout.preactivation_recovery_journal.chmod(0o600)
        _expect_local_error(
            attempt_supervisor_start_guard,
            "Supervisor startup is blocked by preactivation recovery",
        )
        recovery_layout.preactivation_recovery_journal.unlink()

        legacy_sentinel = temp / "legacy-monitor-untouched"
        legacy_sentinel.write_bytes(b"legacy remains stopped and preserved")
        legacy_sentinel.chmod(0o600)
        recovered = recovery_installer.recover_preactivation(
            source_root=source,
            expected_sha=first_sha,
        )
        assert recovered.status == "recovered"
        assert recovered.failed_release_sha == failed_sha
        assert recovered.replacement_sha == first_sha
        assert recovered.model_attempt_count == 0 and recovered.model_call_count == 0
        assert recovered.legacy_monitor_touched is False
        archive_dir = Path(recovered.archive_dir)
        archive_state = archive_dir / "state"
        assert (archive_state / "supervisor.sqlite3").is_file()
        assert (archive_state / "managed_workspaces" / "rollout-pilot").is_dir()
        backup = Path(recovered.backup_path)
        assert backup.stat().st_mode & 0o777 == 0o600
        assert hashlib.sha256(backup.read_bytes()).hexdigest() == recovered.backup_sha256
        backup_connection = sqlite3.connect(f"file:{backup}?mode=ro", uri=True)
        try:
            assert backup_connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert backup_connection.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 1
        finally:
            backup_connection.close()
        verified_recovery = verify_preactivation_recovery_receipt(
            recovery_layout.preactivation_recovery_receipt,
            expected_replacement_sha=first_sha,
            runtime_root=recovery_layout.root,
        )
        assert verified_recovery["backup_sha256"] == recovered.backup_sha256
        qualification_recovery = (
            recovery_layout.qualifications
            / f"{first_sha}.preactivation-recovery.json"
        )
        qualification_metadata = qualification_recovery.lstat()
        assert (
            stat.S_ISREG(qualification_metadata.st_mode)
            and not qualification_recovery.is_symlink()
            and qualification_metadata.st_uid == os.geteuid()
            and stat.S_IMODE(qualification_metadata.st_mode) == 0o600
            and qualification_metadata.st_nlink == 1
            and qualification_recovery.read_bytes()
            == recovery_layout.preactivation_recovery_receipt.read_bytes()
        )
        fresh_connection = sqlite3.connect(recovery_layout.state / "supervisor.sqlite3")
        try:
            assert fresh_connection.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0
            assert fresh_connection.execute(
                "SELECT generation,owner_id,lease_token,expires_at FROM supervisor_lease"
            ).fetchone() == (1, None, None, 0.0)
            assert fresh_connection.execute(
                "SELECT generation,sequence,revision FROM projection_transport_state"
            ).fetchone() == (1, 5, 5)
        finally:
            fresh_connection.close()
        repeated = recovery_installer.recover_preactivation(
            source_root=source,
            expected_sha=first_sha,
        )
        assert repeated.status == "already_recovered"
        fresh_registry = SupervisorRegistry(recovery_layout.state / "supervisor.sqlite3")
        next_fence = fresh_registry.acquire_generation("post-recovery-smoke")
        assert next_fence.generation == 2
        recovered_projection = fresh_registry.reserve_projection_snapshot(
            supervisor_id="preactivation-recovery-smoke",
            projection={
                "tasks": [],
                "workstreams": [],
                "incidents": [],
                "attention": [],
                "release_lanes": [],
                "acceptance": [],
            },
            event_id="preactivation-recovery-empty-projection",
            idempotency_key="preactivation-recovery-empty-projection-idem",
            fence=next_fence,
        )
        assert recovered_projection == {"generation": 2, "sequence": 1, "revision": 6}
        fresh_registry.release_generation(next_fence)
        recovery_qualification = _qualification(
            recovery_layout,
            first_sha,
            supervisor_generation=2,
            include_preactivation_recovery=True,
        )
        recovery_installer._validate_qualification(
            recovery_qualification,
            expected_sha=first_sha,
            validation_now=datetime.now(timezone.utc),
        )
        recovery_installer._accept_qualification(
            first_sha,
            recovery_qualification.read_bytes(),
            release=recovery_layout.releases / first_sha,
            supervisor_generation=2,
            activation_nonce_sha256=hashlib.sha256(
                recovery_layout.activation_nonce.read_bytes()
            ).hexdigest(),
        )
        recovery_layout.current.symlink_to(recovery_layout.releases / first_sha)
        with sqlite3.connect(recovery_layout.state / "supervisor.sqlite3") as connection:
            connection.execute("DELETE FROM outbox WHERE kind = 'projection_snapshot'")
            connection.commit()
        verify_preactivation_recovery_receipt(
            recovery_layout.preactivation_recovery_receipt,
            expected_replacement_sha=first_sha,
            runtime_root=recovery_layout.root,
            require_pristine=False,
            require_empty_projection=False,
        )
        _expect_local_error(
            lambda: verify_preactivation_recovery_receipt(
                recovery_layout.preactivation_recovery_receipt,
                expected_replacement_sha=first_sha,
                runtime_root=recovery_layout.root,
                require_pristine=False,
                require_empty_projection=True,
            ),
            "first projection",
        )
        future_sha = "2" * 40
        shutil.copytree(
            recovery_layout.releases / first_sha,
            recovery_layout.releases / future_sha,
        )
        future_qualification = _qualification(
            recovery_layout,
            future_sha,
            supervisor_generation=9,
        )
        recovery_installer._validate_qualification(
            future_qualification,
            expected_sha=future_sha,
            validation_now=datetime.now(timezone.utc),
        )
        recovery_acceptance = (
            recovery_layout.qualifications / f"{first_sha}.acceptance-receipt.json"
        )
        recovery_acceptance_bytes = recovery_acceptance.read_bytes()
        recovery_acceptance.write_bytes(b"{}")
        recovery_acceptance.chmod(0o600)
        _expect_local_error(
            lambda: recovery_installer._validate_qualification(
                future_qualification,
                expected_sha=future_sha,
                validation_now=datetime.now(timezone.utc),
            ),
            "receipt fields",
        )
        recovery_acceptance.write_bytes(recovery_acceptance_bytes)
        recovery_acceptance.chmod(0o600)
        assert legacy_sentinel.read_bytes() == b"legacy remains stopped and preserved"
        assert recovery_layout.staged.resolve() == recovery_layout.releases / first_sha
        assert not any(
            call[1] in {"bootout", "bootstrap", "kickstart"}
            for call in recovery_launchctl.calls
        )
        assert not recovery_layout.preactivation_recovery_journal.exists()

        # Every durable preactivation transaction boundary converges in a new
        # process without selecting a second archive or losing the canonical
        # receipt.  BaseException models abrupt process death, bypassing normal
        # in-process exception handling.
        crash_boundaries = (
            "after_preactivation_recovery_intent",
            "after_preactivation_recovery_journal",
            "after_preactivation_old_state_archive",
            "after_preactivation_fresh_state_install",
            "after_preactivation_recovery_receipt",
        )
        for boundary in crash_boundaries:
            crash_layout = LocalInstallLayout.resolve(
                temp / f"preactivation-crash-{boundary}",
                launch_agents_dir=temp / f"preactivation-agents-{boundary}",
            )
            crash_launchctl = FakeLaunchctl()

            def fault_injector(observed: str, *, expected: str = boundary) -> None:
                if observed == expected:
                    raise SimulatedProcessCrash(expected)

            crashing_installer = LocalInstaller(
                crash_layout,
                command_runner=crash_launchctl,
                source_gate=hermetic_source_gate,
                readiness_probe=lambda: None,
                fault_injector=fault_injector,
            )
            crashing_installer.install(
                source_root=source,
                expected_sha=first_sha,
                require_origin_main=True,
                activate=False,
            )
            _failed_preactivation_registry_fixture(crash_layout.state)
            try:
                crashing_installer.recover_preactivation(
                    source_root=source,
                    expected_sha=first_sha,
                )
            except SimulatedProcessCrash as exc:
                assert str(exc) == boundary
            else:
                raise AssertionError(
                    f"preactivation recovery did not crash at {boundary}"
                )
            assert crash_layout.preactivation_recovery_journal.is_file()
            resumed_installer = LocalInstaller(
                crash_layout,
                command_runner=crash_launchctl,
                source_gate=hermetic_source_gate,
                readiness_probe=lambda: None,
            )
            resumed = resumed_installer.recover_preactivation(
                source_root=source,
                expected_sha=first_sha,
            )
            assert resumed.status in {"recovered", "already_recovered"}
            assert not crash_layout.preactivation_recovery_journal.exists()
            assert len(tuple(crash_layout.preactivation_recoveries.iterdir())) == 1
            verify_preactivation_recovery_receipt(
                crash_layout.preactivation_recovery_receipt,
                expected_replacement_sha=first_sha,
                runtime_root=crash_layout.root,
            )
            with sqlite3.connect(
                crash_layout.state / "supervisor.sqlite3"
            ) as crash_connection:
                assert crash_connection.execute(
                    "SELECT COUNT(*) FROM tasks"
                ).fetchone()[0] == 0

        rewrite_layout = LocalInstallLayout.resolve(
            temp / "rewrite-runtime",
            launch_agents_dir=temp / "rewrite-agents",
        )
        _expect_local_error(
            lambda: LocalInstaller(rewrite_layout).install(
                source_root=source,
                expected_sha=first_sha,
                require_origin_main=True,
                activate=False,
            ),
            "URL rewrite configuration is forbidden",
        )

        drift_layout = LocalInstallLayout.resolve(
            temp / "drift-runtime",
            launch_agents_dir=temp / "drift-agents",
        )
        drift_installer = DriftAfterGateInstaller(drift_layout, source_gate=hermetic_source_gate)
        _expect_local_error(
            lambda: drift_installer.install(
                source_root=source,
                expected_sha=first_sha,
                require_origin_main=True,
                activate=False,
            ),
            "source working tree is not clean",
        )
        packaged_readme = drift_layout.releases / first_sha / "README.md"
        assert packaged_readme.read_text(encoding="utf-8") == "fixture\n"
        assert not drift_layout.staged.exists() and not drift_layout.current.exists()
        subprocess.run(["git", "restore", "README.md"], cwd=source, check=True)

        # A pre-existing tree cannot reseal changed bytes under a trusted SHA:
        # exact Git blob readback defeats a self-authored replacement digest.
        tamper_layout = LocalInstallLayout.resolve(
            temp / "tamper-runtime",
            launch_agents_dir=temp / "tamper-agents",
        )
        tamper_installer = LocalInstaller(tamper_layout, source_gate=hermetic_source_gate)
        tamper_installer.install(
            source_root=source,
            expected_sha=first_sha,
            require_origin_main=True,
            activate=False,
        )
        tamper_release = tamper_layout.releases / first_sha
        tamper_file = tamper_release / "src" / "fixture.py"
        tamper_manifest = tamper_release / "release.json"
        tamper_file.chmod(0o644)
        tamper_manifest.chmod(0o644)
        tamper_file.write_text("VALUE = 999\n", encoding="utf-8")
        manifest_payload = json.loads(tamper_manifest.read_text(encoding="utf-8"))
        manifest_payload["tree_digest"] = _release_digest_without_manifest(tamper_release)
        tamper_manifest.write_text(json.dumps(manifest_payload, sort_keys=True), encoding="utf-8")
        tamper_file.chmod(0o444)
        tamper_manifest.chmod(0o444)
        _expect_local_error(
            lambda: tamper_installer.install(
                source_root=source,
                expected_sha=first_sha,
                require_origin_main=True,
                activate=False,
            ),
            "blob differs from the exact Git object",
        )

        # The root-owned flock is a single-operation gate across processes;
        # contention and a substituted lock path both fail before packaging or
        # staged/current pointer mutation.
        concurrent_layout = LocalInstallLayout.resolve(
            temp / "concurrent-runtime",
            launch_agents_dir=temp / "concurrent-agents",
        )
        concurrent_installer = LocalInstaller(
            concurrent_layout,
            source_gate=hermetic_source_gate,
        )
        concurrent_installer._ensure_layout()
        lock_descriptor = os.open(
            concurrent_layout.operation_lock,
            os.O_RDWR | os.O_CREAT,
            0o600,
        )
        try:
            fcntl.flock(lock_descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            _expect_local_error(
                lambda: concurrent_installer.install(
                    source_root=source,
                    expected_sha=first_sha,
                    require_origin_main=False,
                ),
                "another local install operation is active",
            )
            assert not (concurrent_layout.releases / first_sha).exists()
            assert not concurrent_layout.staged.exists()
        finally:
            fcntl.flock(lock_descriptor, fcntl.LOCK_UN)
            os.close(lock_descriptor)
        concurrent_layout.operation_lock.unlink()
        lock_victim = temp / "lock-victim"
        lock_victim.write_bytes(b"unchanged")
        lock_victim.chmod(0o600)
        concurrent_layout.operation_lock.symlink_to(lock_victim)
        _expect_local_error(
            lambda: concurrent_installer.install(
                source_root=source,
                expected_sha=first_sha,
                require_origin_main=False,
            ),
            "operation lock could not be opened safely",
        )
        assert lock_victim.read_bytes() == b"unchanged"

        quarantine_layout = LocalInstallLayout.resolve(
            temp / "quarantine-runtime",
            launch_agents_dir=temp / "quarantine-agents",
        )
        quarantine_launchctl = FakeLaunchctl()
        quarantine_launchctl.loaded = True
        quarantine_installer = LocalInstaller(
            quarantine_layout,
            command_runner=quarantine_launchctl,
            source_gate=hermetic_source_gate,
        )
        quarantine_installer._ensure_layout()
        quarantine_layout.active_transaction.mkdir(mode=0o700)
        (quarantine_layout.active_transaction / "journal.json").write_bytes(b"not-json")
        (quarantine_layout.active_transaction / "journal.json").chmod(0o600)
        quarantine_layout.launch_agent.write_bytes(b"unsafe-to-load-after-recovery-failure")
        quarantine_layout.launch_agent.chmod(0o600)
        _expect_local_error(
            lambda: quarantine_installer.install(
                source_root=source,
                expected_sha=first_sha,
                require_origin_main=False,
            ),
            "quarantined",
        )
        assert quarantine_launchctl.loaded is False
        assert not quarantine_layout.launch_agent.exists()
        assert (quarantine_layout.transactions / "quarantined-launch-agent.plist").is_file()
        assert quarantine_layout.transaction_quarantine.is_file()
        assert quarantine_layout.transaction_quarantine.stat().st_mode & 0o777 == 0o600
        quarantine_payload = json.loads(
            quarantine_layout.transaction_quarantine.read_text(encoding="utf-8")
        )
        assert quarantine_payload["mutation_enabled"] is False
        _expect_local_error(
            lambda: quarantine_installer.install(
                source_root=source,
                expected_sha=first_sha,
                require_origin_main=False,
            ),
            "automatic mutation is disabled",
        )

        layout = LocalInstallLayout.resolve(temp / "runtime", launch_agents_dir=temp / "agents")
        launchctl = FakeLaunchctl()
        readiness = ReleaseAwareReadiness(layout, launchctl)
        process_identity = {"matches": False}
        legacy_absence = {"proven": True, "calls": 0}

        def legacy_launchd_probe(label: str) -> bool:
            assert label == "com.orenvlad.codex-session-monitor"
            legacy_absence["calls"] += 1
            return bool(legacy_absence["proven"])

        def make_installer(
            *,
            fault_injector: Any = None,
        ) -> LocalInstaller:
            return LocalInstaller(
                layout,
                command_runner=launchctl,
                source_gate=hermetic_source_gate,
                process_identity_probe=lambda *_args: process_identity["matches"],
                legacy_launchd_probe=legacy_launchd_probe,
                readiness_probe=readiness,
                sleep_fn=lambda _seconds: None,
                monotonic_fn=AdvancingClock(),
                activation_timeout_seconds=0.05,
                fault_injector=fault_injector,
            )

        installer = make_installer()
        _expect_local_error(
            lambda: installer.install(
                source_root=source,
                expected_sha=first_sha,
                require_origin_main=True,
                activate=True,
            ),
            "qualification manifest",
        )
        assert not layout.current.exists() and not launchctl.loaded
        first_qualification = _qualification(layout, first_sha)
        fresh_manifest_before = first_qualification.read_bytes()
        fresh_manifest_payload = json.loads(fresh_manifest_before)
        suite_path = layout.qualifications / fresh_manifest_payload["suite"]["evidence_file"]
        suite_before = suite_path.read_bytes()
        stale_suite = json.loads(suite_before)
        stale_suite["generated_at"] = (
            datetime.now(timezone.utc) - timedelta(hours=25)
        ).isoformat().replace("+00:00", "Z")
        suite_path.write_text(json.dumps(stale_suite, sort_keys=True), encoding="utf-8")
        suite_path.chmod(0o600)
        fresh_manifest_payload["suite"]["evidence_sha256"] = hashlib.sha256(
            suite_path.read_bytes()
        ).hexdigest()
        first_qualification.write_text(json.dumps(fresh_manifest_payload, sort_keys=True), encoding="utf-8")
        first_qualification.chmod(0o600)
        _expect_local_error(
            lambda: installer.install(
                source_root=source,
                expected_sha=first_sha,
                require_origin_main=True,
                activate=True,
                qualification_manifest=first_qualification,
            ),
            "older than 24 hours",
        )
        suite_path.write_bytes(suite_before)
        suite_path.chmod(0o600)
        first_qualification.write_bytes(fresh_manifest_before)
        first_qualification.chmod(0o600)
        unknown_suite = json.loads(suite_before)
        unknown_suite["smokes"][-1]["path"] = "apps/unknown-authoritative-smoke.py"
        suite_path.write_text(json.dumps(unknown_suite, sort_keys=True), encoding="utf-8")
        suite_path.chmod(0o600)
        unknown_manifest = json.loads(fresh_manifest_before)
        unknown_manifest["suite"]["evidence_sha256"] = hashlib.sha256(
            suite_path.read_bytes()
        ).hexdigest()
        first_qualification.write_text(json.dumps(unknown_manifest, sort_keys=True), encoding="utf-8")
        first_qualification.chmod(0o600)
        _expect_local_error(
            lambda: installer.install(
                source_root=source,
                expected_sha=first_sha,
                require_origin_main=True,
                activate=True,
                qualification_manifest=first_qualification,
            ),
            "suite membership differs",
        )
        suite_path.write_bytes(suite_before)
        suite_path.chmod(0o600)
        first_qualification.write_bytes(fresh_manifest_before)
        first_qualification.chmod(0o600)
        legacy_absence["proven"] = False
        launch_calls_before_legacy_denial = len(launchctl.calls)
        _expect_local_error(
            lambda: installer.install(
                source_root=source,
                expected_sha=first_sha,
                require_origin_main=True,
                activate=True,
                qualification_manifest=first_qualification,
            ),
            "previous release and service were restored",
        )
        assert not launchctl.loaded
        denied_calls = launchctl.calls[launch_calls_before_legacy_denial:]
        assert not any(call[1] == "bootstrap" for call in denied_calls)
        legacy_absence["proven"] = True
        # Re-sealing structurally plausible but false runtime evidence is not
        # enough.  Initial activation accepts one checkpoint turn only and
        # explicitly defers final task closure/attention until after cutover.
        qualification_before = first_qualification.read_bytes()

        def reject_runtime_evidence(
            *,
            binding_name: str,
            section_name: str,
            changes: dict[str, Any],
            expected_error: str,
        ) -> None:
            qualification_payload = json.loads(qualification_before)
            evidence_path = (
                layout.qualifications
                / qualification_payload[binding_name]["evidence_file"]
            )
            evidence_before = evidence_path.read_bytes()
            forged = json.loads(evidence_before)
            forged["qualification_evidence"][section_name].update(changes)
            evidence_path.write_text(json.dumps(forged, sort_keys=True), encoding="utf-8")
            evidence_path.chmod(0o600)
            qualification_payload[binding_name]["evidence_sha256"] = hashlib.sha256(
                evidence_path.read_bytes()
            ).hexdigest()
            first_qualification.write_text(
                json.dumps(qualification_payload, sort_keys=True), encoding="utf-8"
            )
            first_qualification.chmod(0o600)
            try:
                _expect_local_error(
                    lambda: installer.install(
                        source_root=source,
                        expected_sha=first_sha,
                        require_origin_main=True,
                        activate=True,
                        qualification_manifest=first_qualification,
                    ),
                    expected_error,
                )
            finally:
                evidence_path.write_bytes(evidence_before)
                evidence_path.chmod(0o600)
                first_qualification.write_bytes(qualification_before)
                first_qualification.chmod(0o600)

        reject_runtime_evidence(
            binding_name="app_server_canary",
            section_name="app_server_canary",
            changes={"model_attempt_count": 0},
            expected_error="one exact nonterminal stdio Sol Ultra checkpoint turn",
        )
        reject_runtime_evidence(
            binding_name="app_server_canary",
            section_name="app_server_canary",
            changes={"model_call_count": 0},
            expected_error="one exact nonterminal stdio Sol Ultra checkpoint turn",
        )
        reject_runtime_evidence(
            binding_name="app_server_canary",
            section_name="app_server_canary",
            changes={"single_attempt_canary": False},
            expected_error="one exact nonterminal stdio Sol Ultra checkpoint turn",
        )
        reject_runtime_evidence(
            binding_name="app_server_canary",
            section_name="app_server_canary",
            changes={"contract_kind": "terminal"},
            expected_error="one exact nonterminal stdio Sol Ultra checkpoint turn",
        )
        reject_runtime_evidence(
            binding_name="app_server_canary",
            section_name="app_server_canary",
            changes={"progress_percent": 100},
            expected_error="one exact nonterminal stdio Sol Ultra checkpoint turn",
        )
        reject_runtime_evidence(
            binding_name="app_server_canary",
            section_name="app_server_canary",
            changes={"progress_percent": []},
            expected_error="one exact nonterminal stdio Sol Ultra checkpoint turn",
        )
        reject_runtime_evidence(
            binding_name="staged_runtime",
            section_name="staged_runtime",
            changes={"final_attention_deferred": False},
            expected_error="staged single writer with final attention deferred",
        )
        reject_runtime_evidence(
            binding_name="app_server_canary",
            section_name="app_server_canary",
            changes={"terminal_event_id": "forbidden-terminal-event"},
            expected_error="runtime sections are invalid",
        )
        reject_runtime_evidence(
            binding_name="staged_runtime",
            section_name="staged_runtime",
            changes={"attention_event_id": "forbidden-attention-event"},
            expected_error="runtime sections are invalid",
        )
        for section_name, changes, expected_error in (
            (
                "app_server_canary",
                {"contract_kind": "terminal"},
                "exact supported surface",
            ),
            (
                "app_server_canary",
                {"progress_percent": 100},
                "exact supported surface",
            ),
            (
                "staged_runtime",
                {"final_attention_deferred": False},
                "staged runtime proof is incomplete",
            ),
            (
                "staged_runtime",
                {"terminal_attention": True},
                "qualification section staged_runtime is incomplete",
            ),
        ):
            forged_manifest = json.loads(qualification_before)
            forged_manifest[section_name].update(changes)
            first_qualification.write_text(
                json.dumps(forged_manifest, sort_keys=True), encoding="utf-8"
            )
            first_qualification.chmod(0o600)
            try:
                _expect_local_error(
                    lambda: installer.install(
                        source_root=source,
                        expected_sha=first_sha,
                        require_origin_main=True,
                        activate=True,
                        qualification_manifest=first_qualification,
                    ),
                    expected_error,
                )
            finally:
                first_qualification.write_bytes(qualification_before)
                first_qualification.chmod(0o600)
        _expect_local_error(
            lambda: installer.install(
                source_root=source,
                expected_sha=first_sha,
                require_origin_main=True,
                activate=True,
                qualification_manifest=first_qualification,
            ),
            "previous release and service were restored",
        )
        assert not layout.current.exists() and not launchctl.loaded
        process_identity["matches"] = True
        first = installer.install(
            source_root=source,
            expected_sha=first_sha,
            require_origin_main=True,
            activate=True,
            qualification_manifest=first_qualification,
        )
        assert first.activated is True and launchctl.loaded is True
        assert Path(first.current_release).name == first_sha
        assert layout.projection_key.stat().st_mode & 0o777 == 0o600
        assert layout.install_acceptance_key.stat().st_mode & 0o777 == 0o600
        assert layout.install_acceptance_key.read_bytes() != layout.projection_key.read_bytes()
        assert layout.state.stat().st_mode & 0o777 == 0o700
        assert layout.launch_agent.stat().st_mode & 0o777 == 0o600
        key = layout.projection_key.read_bytes()
        first_accepted = layout.qualifications / f"{first_sha}.accepted.json"
        first_receipt = layout.qualifications / f"{first_sha}.acceptance-receipt.json"
        assert first_accepted.is_file() and first_receipt.is_file()
        assert first_accepted.stat().st_mode & 0o777 == 0o600
        assert first_receipt.stat().st_mode & 0o777 == 0o600
        receipt_payload = json.loads(first_receipt.read_text(encoding="utf-8"))
        assert receipt_payload["commit_sha"] == first_sha
        assert receipt_payload["supervisor_generation"] == launchctl.generation
        assert len(receipt_payload["hmac_sha256"]) == 64

        accepted_before = first_accepted.read_bytes()
        receipt_before = first_receipt.read_bytes()
        forged_accepted = json.loads(accepted_before)
        forged_accepted["created_at"] = "2000-01-01T00:00:00Z"
        first_accepted.write_text(json.dumps(forged_accepted, sort_keys=True), encoding="utf-8")
        first_accepted.chmod(0o600)
        _expect_local_error(
            lambda: installer.install(
                source_root=source,
                expected_sha=first_sha,
                require_origin_main=True,
                activate=True,
                qualification_manifest=first_accepted,
            ),
            "receipt signature or binding is invalid",
        )
        first_accepted.write_bytes(accepted_before)
        first_accepted.chmod(0o600)
        forged_receipt = json.loads(receipt_before)
        forged_receipt["supervisor_generation"] = int(forged_receipt["supervisor_generation"]) + 1
        first_receipt.write_text(json.dumps(forged_receipt, sort_keys=True), encoding="utf-8")
        first_receipt.chmod(0o600)
        _expect_local_error(
            lambda: installer.install(
                source_root=source,
                expected_sha=first_sha,
                require_origin_main=True,
                activate=True,
                qualification_manifest=first_accepted,
            ),
            "receipt signature or binding is invalid",
        )
        first_receipt.write_bytes(receipt_before)
        first_receipt.chmod(0o600)
        first_plist = layout.launch_agent.read_bytes()

        # A new release that never proves readiness is rolled back atomically,
        # including the previous link, manifest and previously loaded service.
        second_sha = _commit(source, 2)
        staged_for_crash = installer.install(
            source_root=source,
            expected_sha=second_sha,
            require_origin_main=False,
            activate=False,
        )
        assert Path(staged_for_crash.staged_release or "").name == second_sha
        second_qualification = _qualification(layout, second_sha)

        # A hard process death is intentionally outside Exception handling.
        # Every pre-commit boundary must leave a durable private journal that a
        # fresh installer uses to restore the exact prior links, files,
        # qualification receipts and launchd activation before allowing retry.
        crash_baseline = {
            "manifest": layout.manifest.read_bytes(),
            "plist": layout.launch_agent.read_bytes(),
            "nonce": layout.activation_nonce.read_bytes(),
            "staged_manifest": layout.staged_manifest.read_bytes(),
        }
        crash_boundaries = (
            "after_transaction_journal",
            "after_previous_pointer",
            "after_current_pointer",
            "after_activation_nonce",
            "after_launch_agent",
            "after_install_manifest",
            "after_launchd_activation",
            "after_qualification_acceptance",
            "after_staged_clear",
        )
        receipt_count_before = len(tuple(layout.transaction_receipts.iterdir()))
        for boundary in crash_boundaries:
            def inject_crash(observed: str, *, expected: str = boundary) -> None:
                if observed == expected:
                    raise SimulatedProcessCrash(expected)

            crashing_installer = make_installer(fault_injector=inject_crash)
            try:
                crashing_installer.install(
                    source_root=source,
                    expected_sha=second_sha,
                    require_origin_main=True,
                    activate=True,
                    qualification_manifest=second_qualification,
                )
            except SimulatedProcessCrash as exc:
                assert str(exc) == boundary
            else:
                raise AssertionError(f"fault boundary did not crash: {boundary}")
            assert layout.active_transaction.is_dir()
            assert layout.active_transaction.stat().st_mode & 0o777 == 0o700
            assert (layout.active_transaction / "journal.json").stat().st_mode & 0o777 == 0o600
            _expect_local_error(
                lambda: make_installer().install(
                    source_root=source,
                    expected_sha=second_sha,
                    require_origin_main=False,
                    activate=False,
                ),
                "was restored; rerun",
            )
            assert not layout.active_transaction.exists()
            assert not layout.transaction_quarantine.exists()
            assert Path(os.readlink(layout.current)).name == first_sha
            assert not layout.previous.exists() and not layout.previous.is_symlink()
            assert Path(os.readlink(layout.staged)).name == second_sha
            assert layout.manifest.read_bytes() == crash_baseline["manifest"]
            assert layout.launch_agent.read_bytes() == crash_baseline["plist"]
            assert layout.activation_nonce.read_bytes() == crash_baseline["nonce"]
            assert layout.staged_manifest.read_bytes() == crash_baseline["staged_manifest"]
            assert not (layout.qualifications / f"{second_sha}.accepted.json").exists()
            assert not (layout.qualifications / f"{second_sha}.acceptance-receipt.json").exists()
            assert launchctl.loaded is True
        assert len(tuple(layout.transaction_receipts.iterdir())) == (
            receipt_count_before + len(crash_boundaries)
        )
        assert all(
            not any(path.name == "activation_nonce.bin" for path in receipt.rglob("*"))
            for receipt in layout.transaction_receipts.iterdir()
        )

        forged_fresh_accepted = layout.qualifications / f"{second_sha}.accepted.json"
        forged_fresh_accepted.write_bytes(second_qualification.read_bytes())
        forged_fresh_accepted.chmod(0o600)
        _expect_local_error(
            lambda: installer.install(
                source_root=source,
                expected_sha=second_sha,
                require_origin_main=True,
                activate=True,
                qualification_manifest=forged_fresh_accepted,
            ),
            "fresh activation requires .qualification.json",
        )
        forged_fresh_accepted.unlink()
        readiness.failed_release = second_sha
        _expect_local_error(
            lambda: installer.install(
                source_root=source,
                expected_sha=second_sha,
                require_origin_main=True,
                activate=True,
                qualification_manifest=second_qualification,
            ),
            "previous release and service were restored",
        )
        assert Path(os.readlink(layout.current)).name == first_sha
        assert not layout.previous.exists() and not layout.previous.is_symlink()
        assert json.loads(layout.manifest.read_text(encoding="utf-8"))["commit_sha"] == first_sha
        assert layout.launch_agent.read_bytes() == first_plist
        assert launchctl.loaded is True
        assert any(call[1:3] == ("bootout", f"gui/{os.getuid()}/com.orenvlad.dev-control-plane-v2") for call in launchctl.calls)

        # Inactive staging must never change the active symlinks, plist or
        # manifest: a later KeepAlive restart may load only an activated and
        # readiness-proven release.
        active_manifest = layout.manifest.read_bytes()
        active_plist = layout.launch_agent.read_bytes()
        second = installer.install(
            source_root=source,
            expected_sha=second_sha,
            require_origin_main=False,
            activate=False,
        )
        assert second.status == "staged" and second.activated is False
        assert Path(second.current_release or "").name == first_sha
        assert second.previous_release is None
        assert Path(second.staged_release or "").name == second_sha
        assert Path(os.readlink(layout.current)).name == first_sha
        assert not layout.previous.exists() and not layout.previous.is_symlink()
        assert Path(os.readlink(layout.staged)).name == second_sha
        assert layout.manifest.read_bytes() == active_manifest
        assert layout.launch_agent.read_bytes() == active_plist
        assert layout.projection_key.read_bytes() == key

        # A non-activated rollback is likewise inert. Seed a valid recoverable
        # previous pointer, then prove only the staged pointer changes.
        os.symlink(layout.releases / second_sha, layout.previous)
        rolled = installer.rollback()
        assert rolled.status == "rollback_staged" and rolled.activated is False
        assert Path(rolled.current_release or "").name == first_sha
        assert Path(rolled.staged_release or "").name == second_sha
        assert Path(os.readlink(layout.current)).name == first_sha
        assert Path(os.readlink(layout.previous)).name == second_sha
        assert layout.manifest.read_bytes() == active_manifest
        assert layout.launch_agent.read_bytes() == active_plist
        assert installer.status()["commit_sha"] == first_sha
        assert not any(path.name == ".git" for path in Path(rolled.current_release or "").rglob(".git"))

        # A second proven activation creates its own signed receipt; an
        # activated rollback may then consume only the first release's valid
        # historical accepted artifact plus receipt.
        readiness.failed_release = None
        activated_second = installer.install(
            source_root=source,
            expected_sha=second_sha,
            require_origin_main=True,
            activate=True,
            qualification_manifest=second_qualification,
        )
        assert activated_second.activated is True
        assert Path(os.readlink(layout.current)).name == second_sha
        assert Path(os.readlink(layout.previous)).name == first_sha
        assert (layout.qualifications / f"{second_sha}.acceptance-receipt.json").is_file()
        activated_rollback = installer.rollback(activate=True)
        assert activated_rollback.status == "rolled_back" and activated_rollback.activated is True
        assert Path(os.readlink(layout.current)).name == first_sha
        assert Path(os.readlink(layout.previous)).name == second_sha
        refreshed_first_receipt = json.loads(first_receipt.read_text(encoding="utf-8"))
        assert refreshed_first_receipt["supervisor_generation"] == launchctl.generation
        forward_restored = installer.install(
            source_root=source,
            expected_sha=second_sha,
            require_origin_main=True,
            activate=True,
            qualification_manifest=layout.qualifications / f"{second_sha}.accepted.json",
        )
        assert forward_restored.activated is True
        assert Path(os.readlink(layout.current)).name == second_sha
        assert Path(os.readlink(layout.previous)).name == first_sha

        # Once the commit marker itself is durable, a crash may leave receipt
        # archival pending but must not roll the newly qualified activation
        # back.  The next locked operation archives that transaction first.
        def crash_after_commit(observed: str) -> None:
            if observed == "after_commit_marker":
                raise SimulatedProcessCrash(observed)

        try:
            make_installer(fault_injector=crash_after_commit).rollback(activate=True)
        except SimulatedProcessCrash as exc:
            assert str(exc) == "after_commit_marker"
        else:
            raise AssertionError("committed rollback did not hit the injected process crash")
        committed_journal = json.loads(
            (layout.active_transaction / "journal.json").read_text(encoding="utf-8")
        )
        assert committed_journal["phase"] == "committed"
        assert Path(os.readlink(layout.current)).name == first_sha
        committed_recovery = make_installer().install(
            source_root=source,
            expected_sha=second_sha,
            require_origin_main=False,
            activate=False,
        )
        assert committed_recovery.status == "staged"
        assert Path(os.readlink(layout.current)).name == first_sha
        assert not layout.active_transaction.exists()
        assert launchctl.loaded is True

        _expect_local_error(
            lambda: installer.install(
                source_root=source,
                expected_sha=second_sha,
                require_origin_main=False,
                activate=True,
            ),
            "activation requires exact origin/main",
        )

        # Existing keys fail closed on symlink or permission weakness; the
        # installer never chmods or follows the attacker-controlled target.
        key_mode_before = layout.projection_key.stat().st_mode & 0o777
        victim = temp / "victim.key"
        victim.write_bytes(b"v" * 64)
        victim.chmod(0o600)
        layout.projection_key.unlink()
        os.symlink(victim, layout.projection_key)
        _expect_local_error(
            lambda: installer.install(
                source_root=source,
                expected_sha=second_sha,
                require_origin_main=False,
            ),
            "regular non-symlink",
        )
        assert victim.stat().st_mode & 0o777 == 0o600
        layout.projection_key.unlink()
        layout.projection_key.write_bytes(key)
        layout.projection_key.chmod(0o644)
        _expect_local_error(
            lambda: installer.install(
                source_root=source,
                expected_sha=second_sha,
                require_origin_main=False,
            ),
            "exactly 0600",
        )
        layout.projection_key.chmod(key_mode_before)
        with mock.patch(
            "dev_control_plane.local_install.os.geteuid",
            return_value=os.geteuid() + 1,
        ):
            _expect_local_error(
                installer._ensure_projection_key,
                "owner does not match",
            )

        # A locally forged/stale origin/main ref cannot pass: production gates
        # fetch the remote immediately before comparing the exact commit.
        third_sha = _commit(source, 3, publish=False)
        subprocess.run(
            ["git", "update-ref", "refs/remotes/origin/main", third_sha],
            cwd=source,
            check=True,
        )
        _expect_local_error(
            lambda: installer.install(
                source_root=source,
                expected_sha=third_sha,
                require_origin_main=True,
            ),
            "source HEAD is not exact origin/main",
        )

        # A production install also fails closed when current origin/main cannot
        # be fetched; it never trusts a previously cached remote-tracking ref.
        unavailable_origin = temp / "origin.unavailable"
        origin_store.rename(unavailable_origin)
        try:
            _expect_local_error(
                lambda: installer.install(
                    source_root=source,
                    expected_sha=third_sha,
                    require_origin_main=True,
                ),
                "Git source gate failed: fetch",
            )
        finally:
            unavailable_origin.rename(origin_store)

        # Both release pointers reject escape outside runtime/releases even when
        # the external directory name looks like an immutable SHA.
        safe_current = Path(os.readlink(layout.current))
        external = temp / first_sha
        external.mkdir()
        layout.current.unlink()
        os.symlink(external, layout.current)
        _expect_local_error(installer.status, "outside the direct immutable releases lane")
        layout.current.unlink()
        os.symlink(safe_current, layout.current)
        layout.previous.unlink()
        os.symlink(external, layout.previous)
        _expect_local_error(installer.rollback, "outside the direct immutable releases lane")

        cli_root = temp / "forbidden-cli-runtime"
        cli = subprocess.run(
            [
                sys.executable,
                str(ROOT / "apps" / "dev_control_plane_local_install_v2.py"),
                "--runtime-root",
                str(cli_root),
                "--launch-agents-dir",
                str(temp / "forbidden-cli-agents"),
                "install",
                "--source",
                str(source),
                "--allow-non-main",
                "--activate",
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        assert cli.returncode == 1, cli
        assert "--allow-non-main cannot be combined with --activate" in cli.stdout
        assert not cli_root.exists()

        production_source = (SRC / "dev_control_plane" / "local_install.py").read_text(
            encoding="utf-8"
        )
        production_tree = ast.parse(production_source)
        assert not any(isinstance(node, ast.Assert) for node in ast.walk(production_tree))
        optimized_guard = subprocess.run(
            [
                sys.executable,
                "-O",
                "-c",
                """
import os
from pathlib import Path
import tempfile
from dev_control_plane.local_install import LocalInstallError, LocalInstallLayout
with tempfile.TemporaryDirectory() as value:
    root = Path(value)
    victim = root / "victim"
    victim.mkdir()
    linked = root / "linked"
    linked.symlink_to(victim, target_is_directory=True)
    try:
        LocalInstallLayout.resolve(linked, launch_agents_dir=root / "agents")
    except LocalInstallError:
        pass
    else:
        raise SystemExit("optimized runtime followed a forbidden root symlink")
""",
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": str(SRC)},
        )
        assert optimized_guard.returncode == 0, optimized_guard
    print("local install v2 smoke: ok")


if __name__ == "__main__":
    main()
