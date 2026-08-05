"""Smoke for online legacy backup and sanitized shadow projection."""

from __future__ import annotations

from dataclasses import asdict
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from typing import Callable
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (SRC, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dev_control_plane.migration import (  # noqa: E402
    MigrationError,
    archive_legacy_monitor,
    prove_legacy_absence,
    shadow_snapshot,
    verify_legacy_absence_manifest,
    verify_legacy_archive_manifest,
)


def _expect_migration_error(callable_value: Callable[[], object], expected_fragment: str) -> None:
    try:
        callable_value()
    except MigrationError as exc:
        if expected_fragment not in str(exc):
            raise AssertionError(f"unexpected MigrationError: {exc}") from exc
    else:
        raise AssertionError(f"expected MigrationError containing {expected_fragment!r}")


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        source = root / "legacy.sqlite3"
        connection = sqlite3.connect(source)
        connection.execute(
            "CREATE TABLE sessions (alive INTEGER, hidden INTEGER, monitoring INTEGER, pr_state TEXT, repository TEXT, secret TEXT)"
        )
        connection.executemany(
            "INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?)",
            [
                (1, 0, 1, "OPEN", "owner/repo", "TOKEN_SHOULD_NOT_LEAK"),
                (0, 0, 1, "MERGED", "owner/repo", "another secret"),
            ],
        )
        connection.execute("CREATE TABLE events (payload TEXT)")
        connection.execute("INSERT INTO events VALUES ('private raw payload')")
        connection.commit()
        source.chmod(0o600)

        snapshot = shadow_snapshot(source)
        assert snapshot["active_observed_sessions"] == 1
        assert snapshot["open_pr_observations"] == 1
        assert snapshot["authoritative"] is False
        assert "TOKEN_SHOULD_NOT_LEAK" not in json.dumps(snapshot)

        with mock.patch(
            "dev_control_plane.migration.inspect_launchd",
            return_value={"loaded": False, "pid": None},
        ):
            archived = archive_legacy_monitor(destination=root / "archive", source_db=source, label="fixture")
        payload = asdict(archived)
        assert archived.integrity == "ok"
        assert archived.table_counts == {"events": 1, "sessions": 2}
        assert Path(archived.backup_path or "").stat().st_mode & 0o777 == 0o600
        manifest = Path(archived.manifest_path).read_text(encoding="utf-8")
        assert "private raw payload" not in manifest
        assert "TOKEN_SHOULD_NOT_LEAK" not in manifest
        assert payload["backup_sha256"] in manifest
        verified = verify_legacy_archive_manifest(Path(archived.manifest_path), expected_label="fixture")
        assert asdict(verified) == payload

        manifest_path = Path(archived.manifest_path)
        manifest_hardlink = root / "manifest-hardlink.json"
        os.link(manifest_path, manifest_hardlink)
        _expect_migration_error(
            lambda: verify_legacy_archive_manifest(manifest_path, expected_label="fixture"),
            "permissions or shape",
        )
        manifest_hardlink.unlink()
        manifest_symlink = root / "manifest-symlink.json"
        os.symlink(manifest_path, manifest_symlink)
        _expect_migration_error(
            lambda: verify_legacy_archive_manifest(manifest_symlink, expected_label="fixture"),
            "permissions or shape",
        )

        backup = Path(archived.backup_path or "")
        backup_before = backup.read_bytes()
        backup_hardlink = root / "backup-hardlink.sqlite3"
        os.link(backup, backup_hardlink)
        _expect_migration_error(
            lambda: verify_legacy_archive_manifest(manifest_path, expected_label="fixture"),
            "permissions or shape",
        )
        backup_hardlink.unlink()
        backup.write_bytes(backup_before + b"tamper")
        backup.chmod(0o600)
        _expect_migration_error(
            lambda: verify_legacy_archive_manifest(manifest_path, expected_label="fixture"),
            "digest verification failed",
        )
        backup.write_bytes(backup_before)
        backup.chmod(0o600)

        source_symlink = root / "source-symlink.sqlite3"
        os.symlink(source, source_symlink)
        _expect_migration_error(
            lambda: shadow_snapshot(source_symlink),
            "permissions or shape",
        )

        absent_source = root / "never-installed.sqlite3"
        absent_plist = root / "never-installed.plist"
        with mock.patch(
            "dev_control_plane.migration.inspect_launchd",
            return_value={"loaded": False, "pid": None},
        ):
            absence = prove_legacy_absence(
                destination=root / "absence",
                source_db=absent_source,
                plist_path=absent_plist,
                label="fixture-absent",
            )
        assert absence.authoritative is False
        assert absence.source_present is False and absence.plist_present is False
        assert len(absence.evidence_sha256) == 64
        verified_absence = verify_legacy_absence_manifest(
            Path(absence.manifest_path),
            expected_label="fixture-absent",
            expected_source=absent_source,
            expected_plist=absent_plist,
        )
        assert asdict(verified_absence) == asdict(absence)
        absent_source.write_bytes(b"appeared")
        absent_source.chmod(0o600)
        _expect_migration_error(
            lambda: verify_legacy_absence_manifest(
                Path(absence.manifest_path),
                expected_label="fixture-absent",
                expected_source=absent_source,
                expected_plist=absent_plist,
            ),
            "no longer true",
        )
        connection.close()
    print("migration v2 smoke: ok")


if __name__ == "__main__":
    main()
