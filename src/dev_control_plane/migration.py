"""Non-destructive legacy evidence migration and shadow comparison helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import subprocess
import tempfile
from typing import Any
from urllib.parse import quote


LEGACY_MONITOR_LABEL = "com.orenvlad.codex-session-monitor"
LEGACY_MONITOR_DB = Path.home() / "Library" / "Application Support" / "CodexSessionMonitor" / "state" / "monitor.sqlite3"
LEGACY_MONITOR_PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LEGACY_MONITOR_LABEL}.plist"
_ARCHIVE_FIELDS = {
    "schema", "label", "archived_at", "source_present", "source_size",
    "backup_path", "backup_sha256", "integrity", "table_counts",
    "legacy_launchd_loaded", "legacy_launchd_pid", "manifest_path",
}
_ABSENCE_FIELDS = {
    "schema", "label", "captured_at", "authoritative", "source_path", "plist_path",
    "source_present", "plist_present", "launchd_loaded", "launchd_pid",
    "evidence_sha256", "manifest_path",
}


class MigrationError(RuntimeError):
    """Raised when legacy evidence cannot be preserved or verified safely."""


@dataclass(frozen=True)
class LegacyArchive:
    schema: str
    label: str
    archived_at: str
    source_present: bool
    source_size: int
    backup_path: str | None
    backup_sha256: str | None
    integrity: str | None
    table_counts: dict[str, int]
    legacy_launchd_loaded: bool
    legacy_launchd_pid: int | None
    manifest_path: str


@dataclass(frozen=True)
class LegacyAbsence:
    schema: str
    label: str
    captured_at: str
    authoritative: bool
    source_path: str
    plist_path: str
    source_present: bool
    plist_present: bool
    launchd_loaded: bool
    launchd_pid: int | None
    evidence_sha256: str
    manifest_path: str


def prove_legacy_absence(
    *,
    destination: Path,
    source_db: Path = LEGACY_MONITOR_DB,
    plist_path: Path = LEGACY_MONITOR_PLIST,
    label: str = LEGACY_MONITOR_LABEL,
) -> LegacyAbsence:
    """Seal machine-verifiable evidence for a Mac that never had the legacy watcher.

    This is deliberately distinct from an archive: it is valid only when the
    exact DB, plist and launchd label are all absent before and after the
    observation.  It never creates a fake backup or a recoverable legacy target.
    """

    root = Path(os.path.abspath(destination.expanduser()))
    if root.is_symlink():
        raise MigrationError("absence destination must not be a symlink")
    root.mkdir(parents=True, exist_ok=True)
    root = root.resolve(strict=True)
    root_metadata = root.lstat()
    if not stat.S_ISDIR(root_metadata.st_mode) or root_metadata.st_uid != os.geteuid():
        raise MigrationError("absence destination must be an owner-controlled directory")
    root.chmod(0o700)
    manifest_path = root / "absence.json"
    if os.path.lexists(manifest_path):
        raise MigrationError("legacy absence manifest already exists")
    source = Path(os.path.abspath(source_db.expanduser()))
    plist = Path(os.path.abspath(plist_path.expanduser()))
    if os.path.lexists(source) or os.path.lexists(plist):
        raise MigrationError("legacy absence requires both canonical artifacts to be absent")
    runtime = inspect_launchd(label)
    if runtime.get("loaded") is not False or runtime.get("pid") is not None:
        raise MigrationError("legacy absence requires the exact launchd label to be absent")
    if os.path.lexists(source) or os.path.lexists(plist):
        raise MigrationError("legacy artifacts appeared during absence proof")
    captured_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    identity = {
        "schema": "dev-control-plane/legacy-absence/v2",
        "label": label,
        "captured_at": captured_at,
        "authoritative": False,
        "source_path": str(source),
        "plist_path": str(plist),
        "source_present": False,
        "plist_present": False,
        "launchd_loaded": False,
        "launchd_pid": None,
    }
    result = LegacyAbsence(
        **identity,
        evidence_sha256=_mapping_digest(identity),
        manifest_path=str(manifest_path),
    )
    _write_manifest(manifest_path, asdict(result))
    return verify_legacy_absence_manifest(
        manifest_path,
        expected_label=label,
        expected_source=source,
        expected_plist=plist,
    )


def archive_legacy_monitor(
    *,
    destination: Path,
    source_db: Path = LEGACY_MONITOR_DB,
    label: str = LEGACY_MONITOR_LABEL,
) -> LegacyArchive:
    """Create an online SQLite backup and sanitized aggregate manifest.

    The live database and launch agent are not modified.  No event/session rows
    are copied into the manifest.
    """

    root = Path(os.path.abspath(destination.expanduser()))
    if root.is_symlink():
        raise MigrationError("archive destination must not be a symlink")
    root.mkdir(parents=True, exist_ok=True)
    root = root.resolve(strict=True)
    root_metadata = root.lstat()
    if not stat.S_ISDIR(root_metadata.st_mode) or root_metadata.st_uid != os.geteuid():
        raise MigrationError("archive destination must be an owner-controlled directory")
    root.chmod(0o700)
    runtime = inspect_launchd(label)
    archived_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    source = Path(os.path.abspath(source_db.expanduser()))
    try:
        source_metadata = _regular_file_metadata(source, private=True)
    except FileNotFoundError:
        result = LegacyArchive(
            schema="dev-control-plane/legacy-archive/v2",
            label=label,
            archived_at=archived_at,
            source_present=False,
            source_size=0,
            backup_path=None,
            backup_sha256=None,
            integrity=None,
            table_counts={},
            legacy_launchd_loaded=runtime["loaded"],
            legacy_launchd_pid=runtime["pid"],
            manifest_path=str(root / "manifest.json"),
        )
        _write_manifest(root / "manifest.json", asdict(result))
        return result
    source = source.resolve(strict=True)

    timestamp = archived_at.replace(":", "").replace("-", "").replace(".", "")
    backup = root / f"legacy-monitor-{timestamp}.sqlite3"
    if backup.exists():
        raise MigrationError("archive destination already exists")
    descriptor, temporary_name = tempfile.mkstemp(prefix=".legacy-monitor.", suffix=".sqlite3", dir=root)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        source_connection = sqlite3.connect(_sqlite_readonly_uri(source), uri=True, timeout=10)
        destination_connection = sqlite3.connect(temporary, timeout=10)
        try:
            source_integrity = str(source_connection.execute("PRAGMA quick_check").fetchone()[0])
            if source_integrity != "ok":
                raise MigrationError("legacy SQLite source integrity check failed")
            source_connection.backup(destination_connection)
            destination_connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            integrity_row = destination_connection.execute("PRAGMA integrity_check").fetchone()
            integrity = str(integrity_row[0]) if integrity_row else "missing"
            if integrity != "ok":
                raise MigrationError("legacy backup integrity check failed")
            table_counts = _table_counts(destination_connection)
        finally:
            destination_connection.close()
            source_connection.close()
        repeated_source = _regular_file_metadata(source, private=True)
        if (repeated_source.st_dev, repeated_source.st_ino) != (source_metadata.st_dev, source_metadata.st_ino):
            raise MigrationError("legacy SQLite source identity changed during online backup")
        temporary.chmod(0o600)
        _fsync_path(temporary)
        os.replace(temporary, backup)
        _fsync_directory(root)
    finally:
        if temporary.exists():
            temporary.unlink()
    backup_metadata = _regular_file_metadata(backup, private=True)
    if backup_metadata.st_size < 1:
        raise MigrationError("legacy SQLite backup is empty")
    verified_integrity, verified_counts = _sqlite_integrity_and_counts(backup)
    if verified_integrity != "ok" or verified_counts != table_counts:
        raise MigrationError("legacy SQLite backup changed after sealing")
    digest = _sha256(backup, private=True)
    result = LegacyArchive(
        schema="dev-control-plane/legacy-archive/v2",
        label=label,
        archived_at=archived_at,
        source_present=True,
        source_size=source_metadata.st_size,
        backup_path=str(backup),
        backup_sha256=digest,
        integrity="ok",
        table_counts=table_counts,
        legacy_launchd_loaded=runtime["loaded"],
        legacy_launchd_pid=runtime["pid"],
        manifest_path=str(root / "manifest.json"),
    )
    _write_manifest(root / "manifest.json", asdict(result))
    return verify_legacy_archive_manifest(root / "manifest.json", expected_label=label)


def shadow_snapshot(source_db: Path = LEGACY_MONITOR_DB) -> dict[str, Any]:
    """Return only aggregate, non-authoritative legacy observer truth."""

    source = Path(os.path.abspath(source_db.expanduser()))
    try:
        metadata = _regular_file_metadata(source, private=True)
    except FileNotFoundError:
        return {
            "schema": "dev-control-plane/legacy-shadow/v2",
            "available": False,
            "authoritative": False,
        }
    source = source.resolve(strict=True)
    connection = sqlite3.connect(_sqlite_readonly_uri(source), uri=True, timeout=10)
    try:
        columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(sessions)")}
        if not {"alive", "hidden", "monitoring", "pr_state", "repository"}.issubset(columns):
            raise MigrationError("legacy sessions schema is not recognized")
        active = int(
            connection.execute(
                "SELECT COUNT(*) FROM sessions WHERE alive = 1 AND hidden = 0 AND monitoring = 1"
            ).fetchone()[0]
        )
        open_prs = int(
            connection.execute(
                "SELECT COUNT(*) FROM sessions WHERE alive = 1 AND hidden = 0 AND UPPER(COALESCE(pr_state, '')) = 'OPEN'"
            ).fetchone()[0]
        )
        repositories = int(
            connection.execute(
                "SELECT COUNT(DISTINCT repository) FROM sessions WHERE alive = 1 AND hidden = 0 AND repository IS NOT NULL AND repository != ''"
            ).fetchone()[0]
        )
        integrity = str(connection.execute("PRAGMA quick_check").fetchone()[0])
        if integrity != "ok":
            raise MigrationError("legacy shadow SQLite integrity check failed")
        repeated = _regular_file_metadata(source, private=True)
        if (repeated.st_dev, repeated.st_ino) != (metadata.st_dev, metadata.st_ino):
            raise MigrationError("legacy shadow SQLite identity changed during read")
        return {
            "schema": "dev-control-plane/legacy-shadow/v2",
            "available": True,
            "authoritative": False,
            "integrity": integrity,
            "active_observed_sessions": active,
            "open_pr_observations": open_prs,
            "active_repository_count": repositories,
            "captured_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
    finally:
        connection.close()


def inspect_launchd(label: str = LEGACY_MONITOR_LABEL) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            ["/bin/launchctl", "print", f"gui/{os.getuid()}/{label}"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise MigrationError("legacy launchd status could not be read") from exc
    if completed.returncode == 113:
        return {"loaded": False, "pid": None}
    if completed.returncode != 0:
        raise MigrationError("legacy launchd status is unknown")
    pid: int | None = None
    for line in completed.stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith("pid ="):
            try:
                pid = int(stripped.partition("=")[2].strip())
            except ValueError:
                pid = None
            break
    return {"loaded": True, "pid": pid}


def verify_legacy_archive_manifest(
    archive_manifest: Path,
    *,
    expected_label: str = LEGACY_MONITOR_LABEL,
) -> LegacyArchive:
    """Securely bind one exact private manifest to its direct SQLite backup."""

    manifest_path = Path(os.path.abspath(archive_manifest.expanduser()))
    _regular_file_metadata(manifest_path, private=True, max_bytes=1_000_000)
    manifest_path = manifest_path.resolve(strict=True)
    directory = manifest_path.parent
    directory_metadata = directory.lstat()
    if (
        not stat.S_ISDIR(directory_metadata.st_mode)
        or directory_metadata.st_uid != os.geteuid()
        or stat.S_IMODE(directory_metadata.st_mode) != 0o700
    ):
        raise MigrationError("legacy archive directory is not private and direct")
    try:
        payload = json.loads(_read_regular_file(manifest_path, max_bytes=1_000_000).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MigrationError("legacy archive manifest is invalid JSON") from exc
    if not isinstance(payload, dict) or set(payload) != _ARCHIVE_FIELDS:
        raise MigrationError("legacy archive manifest fields are invalid")
    if (
        payload.get("schema") != "dev-control-plane/legacy-archive/v2"
        or payload.get("label") != expected_label
        or payload.get("source_present") is not True
        or payload.get("integrity") != "ok"
        or payload.get("manifest_path") != str(manifest_path)
        or isinstance(payload.get("source_size"), bool)
        or not isinstance(payload.get("source_size"), int)
        or int(payload["source_size"]) < 1
        or not isinstance(payload.get("legacy_launchd_loaded"), bool)
        or (
            payload.get("legacy_launchd_loaded") is False
            and payload.get("legacy_launchd_pid") is not None
        )
        or (
            payload.get("legacy_launchd_pid") is not None
            and (
                isinstance(payload.get("legacy_launchd_pid"), bool)
                or not isinstance(payload.get("legacy_launchd_pid"), int)
                or int(payload["legacy_launchd_pid"]) < 1
            )
        )
    ):
        raise MigrationError("legacy archive manifest identity is invalid")
    _parse_timestamp(payload.get("archived_at"))
    backup_value = payload.get("backup_path")
    digest = payload.get("backup_sha256")
    counts = payload.get("table_counts")
    if (
        not isinstance(backup_value, str)
        or not backup_value
        or not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
        or not isinstance(counts, dict)
        or any(
            not isinstance(name, str)
            or not name
            or isinstance(count, bool)
            or not isinstance(count, int)
            or count < 0
            for name, count in counts.items()
        )
    ):
        raise MigrationError("legacy archive manifest lacks a canonical SQLite binding")
    backup = Path(os.path.abspath(Path(backup_value).expanduser()))
    _regular_file_metadata(backup, private=True)
    backup = backup.resolve(strict=True)
    if backup.parent != directory or backup.suffix != ".sqlite3":
        raise MigrationError("legacy archive backup is not a direct private file")
    if _sha256(backup, private=True) != digest:
        raise MigrationError("legacy archive backup digest verification failed")
    integrity, actual_counts = _sqlite_integrity_and_counts(backup)
    if integrity != "ok" or actual_counts != counts:
        raise MigrationError("legacy archive backup SQLite proof differs from its manifest")
    return LegacyArchive(**payload)


def verify_legacy_absence_manifest(
    absence_manifest: Path,
    *,
    expected_label: str = LEGACY_MONITOR_LABEL,
    expected_source: Path = LEGACY_MONITOR_DB,
    expected_plist: Path = LEGACY_MONITOR_PLIST,
) -> LegacyAbsence:
    """Verify an exact private absence receipt without inventing an archive."""

    manifest_path = Path(os.path.abspath(absence_manifest.expanduser()))
    _regular_file_metadata(manifest_path, private=True, max_bytes=1_000_000)
    manifest_path = manifest_path.resolve(strict=True)
    directory = manifest_path.parent
    directory_metadata = directory.lstat()
    if (
        manifest_path.name != "absence.json"
        or not stat.S_ISDIR(directory_metadata.st_mode)
        or directory_metadata.st_uid != os.geteuid()
        or stat.S_IMODE(directory_metadata.st_mode) != 0o700
    ):
        raise MigrationError("legacy absence manifest is not private and direct")
    try:
        payload = json.loads(_read_regular_file(manifest_path, max_bytes=1_000_000).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MigrationError("legacy absence manifest is invalid JSON") from exc
    source = Path(os.path.abspath(expected_source.expanduser()))
    plist = Path(os.path.abspath(expected_plist.expanduser()))
    if not isinstance(payload, dict) or set(payload) != _ABSENCE_FIELDS:
        raise MigrationError("legacy absence manifest fields are invalid")
    identity = {key: payload[key] for key in _ABSENCE_FIELDS - {"evidence_sha256", "manifest_path"}}
    digest = payload.get("evidence_sha256")
    if (
        payload.get("schema") != "dev-control-plane/legacy-absence/v2"
        or payload.get("label") != expected_label
        or payload.get("authoritative") is not False
        or payload.get("source_path") != str(source)
        or payload.get("plist_path") != str(plist)
        or payload.get("source_present") is not False
        or payload.get("plist_present") is not False
        or payload.get("launchd_loaded") is not False
        or payload.get("launchd_pid") is not None
        or payload.get("manifest_path") != str(manifest_path)
        or not isinstance(digest, str)
        or not re.fullmatch(r"[0-9a-f]{64}", digest)
        or digest != _mapping_digest(identity)
    ):
        raise MigrationError("legacy absence manifest identity is invalid")
    _parse_timestamp(payload.get("captured_at"))
    if os.path.lexists(source) or os.path.lexists(plist):
        raise MigrationError("legacy absence evidence is no longer true")
    return LegacyAbsence(**payload)


def retire_legacy_monitor(*, archive_manifest: Path, label: str = LEGACY_MONITOR_LABEL) -> dict[str, Any]:
    """Unload the exact legacy observer only after verified recoverable backup."""

    if label != LEGACY_MONITOR_LABEL:
        raise MigrationError("only the exact archived legacy launchd label may be retired")
    verified = verify_legacy_archive_manifest(archive_manifest, expected_label=label)
    digest = str(verified.backup_sha256)
    before = inspect_launchd(label)
    if before["loaded"]:
        completed = subprocess.run(
            ["/bin/launchctl", "bootout", f"gui/{os.getuid()}", str(LEGACY_MONITOR_PLIST)],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if completed.returncode != 0:
            raise MigrationError(f"legacy launchd bootout failed with exit {completed.returncode}")
    after = inspect_launchd(label)
    if after["loaded"]:
        raise MigrationError("legacy launchd service remains loaded")
    return {
        "schema": "dev-control-plane/legacy-retirement/v2",
        "status": "retired",
        "label": label,
        "was_loaded": before["loaded"],
        "loaded_after": after["loaded"],
        "backup_sha256": digest,
        "plist_preserved": LEGACY_MONITOR_PLIST.is_file(),
        "source_state_preserved": LEGACY_MONITOR_DB.is_file(),
        "retired_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def _table_counts(connection: sqlite3.Connection) -> dict[str, int]:
    counts: dict[str, int] = {}
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    for (raw_name,) in rows:
        name = str(raw_name)
        quoted = '"' + name.replace('"', '""') + '"'
        counts[name] = int(connection.execute(f"SELECT COUNT(*) FROM {quoted}").fetchone()[0])
    return counts


def _write_manifest(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        if temporary.exists():
            temporary.unlink()


def _regular_file_metadata(
    path: Path,
    *,
    private: bool,
    max_bytes: int | None = None,
) -> os.stat_result:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise MigrationError("legacy evidence file is unavailable") from exc
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or metadata.st_nlink != 1
        or (private and stat.S_IMODE(metadata.st_mode) != 0o600)
        or (max_bytes is not None and metadata.st_size > max_bytes)
    ):
        raise MigrationError("legacy evidence file permissions or shape are unsafe")
    return metadata


def _read_regular_file(path: Path, *, max_bytes: int) -> bytes:
    metadata = _regular_file_metadata(path, private=True, max_bytes=max_bytes)
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        opened = os.fstat(descriptor)
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(1024 * 1024, max_bytes + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > max_bytes:
                raise MigrationError("legacy evidence file is oversized")
    except OSError as exc:
        raise MigrationError("legacy evidence file could not be read safely") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    repeated = _regular_file_metadata(path, private=True, max_bytes=max_bytes)
    if (
        (opened.st_dev, opened.st_ino, opened.st_uid, opened.st_nlink, stat.S_IMODE(opened.st_mode))
        != (metadata.st_dev, metadata.st_ino, metadata.st_uid, 1, 0o600)
        or (repeated.st_dev, repeated.st_ino) != (metadata.st_dev, metadata.st_ino)
    ):
        raise MigrationError("legacy evidence file changed during secure read")
    return b"".join(chunks)


def _sha256(path: Path, *, private: bool) -> str:
    metadata = _regular_file_metadata(path, private=private)
    digest = hashlib.sha256()
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        opened = os.fstat(descriptor)
        while chunk := os.read(descriptor, 1024 * 1024):
            digest.update(chunk)
    except OSError as exc:
        raise MigrationError("legacy backup could not be hashed safely") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    repeated = _regular_file_metadata(path, private=private)
    if (
        opened.st_dev != metadata.st_dev
        or opened.st_ino != metadata.st_ino
        or opened.st_uid != metadata.st_uid
        or opened.st_nlink != 1
        or (private and stat.S_IMODE(opened.st_mode) != 0o600)
        or (repeated.st_dev, repeated.st_ino) != (metadata.st_dev, metadata.st_ino)
    ):
        raise MigrationError("legacy backup changed during secure hashing")
    return digest.hexdigest()


def _mapping_digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _sqlite_integrity_and_counts(path: Path) -> tuple[str, dict[str, int]]:
    metadata = _regular_file_metadata(path, private=True)
    connection = sqlite3.connect(_sqlite_readonly_uri(path), uri=True, timeout=10)
    try:
        integrity_row = connection.execute("PRAGMA integrity_check").fetchone()
        integrity = str(integrity_row[0]) if integrity_row else "missing"
        counts = _table_counts(connection)
    finally:
        connection.close()
    repeated = _regular_file_metadata(path, private=True)
    if (repeated.st_dev, repeated.st_ino) != (metadata.st_dev, metadata.st_ino):
        raise MigrationError("legacy SQLite backup identity changed during verification")
    return integrity, counts


def _sqlite_readonly_uri(path: Path) -> str:
    return f"file:{quote(str(path), safe='/')}?mode=ro"


def _parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or value != value.strip() or not value:
        raise MigrationError("legacy archive timestamp is invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MigrationError("legacy archive timestamp is invalid") from exc
    if parsed.tzinfo is None:
        raise MigrationError("legacy archive timestamp lacks timezone")
    return parsed.astimezone(timezone.utc)


def _fsync_path(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
