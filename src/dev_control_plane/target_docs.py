"""Read-only target documentation access for authenticated MCP sessions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import fnmatch
import json
import os
from pathlib import Path
import re
import subprocess
import time
from typing import Any, Mapping, Sequence

from dev_control_plane.state_layout import safe_state_component
from dev_control_plane.target_projects import TargetProjectConfig

TARGET_DOC_TOOL_NAMES = ("list_target_docs", "search_target_docs", "get_target_doc")

TARGET_DOC_ALLOWED_EXACT = {"README.md", "AGENTS.md"}
TARGET_DOC_ALLOWED_PREFIXES = ("docs/architecture/", "docs/modules/", "migration/")
TARGET_DOC_FORBIDDEN_GLOBS = (
    "wb_core_docs_master/**",
    "99_MANIFEST__DOCSET_VERSION.md",
    "runtime/**",
    "deploy/**",
    "infra/**",
    "artifacts/**",
    "**/.env",
    ".env",
    "*.env",
    "**/*.env",
    "**/secrets/**",
    "**/secret/**",
    "**/.ssh/**",
)
TARGET_DOC_TEXT_SUFFIXES = {".md", ".txt", ".rst", ".sql", ".json", ".toml", ".yaml", ".yml"}
TARGET_DOC_DEFAULT_MAX_RESULTS = 10
TARGET_DOC_MAX_RESULTS = 50
TARGET_DOC_DEFAULT_MAX_BYTES = 24_000
TARGET_DOC_MAX_BYTES = 64_000
TARGET_DOC_MAX_LINE_COUNT = 600
TARGET_DOC_SEARCH_FILE_BYTES = 128_000
TARGET_DOC_ABSOLUTE_FILE_BYTES = 1_000_000
TARGET_DOC_FETCH_TTL_SECONDS = 300

_SECRET_TEXT_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"Authorization\s*:\s*Bearer\s+\S+", re.I),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]{20,}", re.I),
    re.compile(r"Cookie\s*:\s*\S+", re.I),
    re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY"),
    re.compile(r"/opt/dev-control-plane-runtime/(?:secrets|\.codex)/[^\s:]+"),
    re.compile(r"(?i)(identity file\s+)[^\s]+"),
    re.compile(r"(?i)(api[_-]?key|token|password|secret)\s*[:=]\s*[^\s]+"),
)


@dataclass(frozen=True)
class _Snapshot:
    kind: str
    target_id: str
    branch: str
    commit: str
    source_mode: str
    git_dir: Path | None = None
    repo_path: Path | None = None
    cache_dir: Path | None = None
    fetched_at: str | None = None


class TargetDocsError(ValueError):
    """Controlled target docs error safe to expose after sanitization."""


def build_target_docs_readiness(configs: Sequence[TargetProjectConfig], state_dir: Path) -> dict[str, Any]:
    """Return cheap sanitized target-docs diagnostics for get_status."""

    targets: list[dict[str, Any]] = []
    for config in configs:
        status = "configured"
        blockers: list[str] = []
        if config.source_mode == "remote_managed_clone" and not config.repo_url:
            status = "blocked"
            blockers.append("repo_url is required for remote target docs reads")
        if config.source_mode == "local_path" and not Path(config.repo_path).expanduser().exists():
            status = "blocked"
            blockers.append("repo_path is missing for local target docs reads")
        if _git_version().get("status") != "ready":
            status = "blocked"
            blockers.append("git is required for target docs reads")
        cache = _cache_dir(state_dir, config.project_id) / "source.git"
        commit = _cached_commit(cache, config.branch) if cache.exists() else None
        targets.append(
            {
                "target_id": config.project_id,
                "source_mode": config.source_mode,
                "branch": config.branch,
                "status": status,
                "cache_status": "present" if cache.exists() else "not_initialized",
                "cached_commit": commit,
                "allowed_paths": sorted((*TARGET_DOC_ALLOWED_EXACT, *TARGET_DOC_ALLOWED_PREFIXES)),
                "forbidden_paths_enforced": True,
                "blockers": blockers,
            }
        )
    return {
        "status": "ok" if all(item["status"] != "blocked" for item in targets) else "blocked",
        "access_mode": "oauth_session_required",
        "read_only": True,
        "tools": list(TARGET_DOC_TOOL_NAMES),
        "targets": targets,
    }


def list_target_docs(config: TargetProjectConfig, *, state_dir: Path) -> dict[str, Any]:
    snapshot = _ensure_snapshot(config, state_dir=state_dir)
    paths = _list_allowed_paths(snapshot, config)
    return {
        "status": "ok",
        "target_id": config.project_id,
        "ref": _ref_payload(snapshot),
        "docs": [
            {
                "path": path,
                "doc_type": _doc_type(path),
            }
            for path in paths
        ],
        "allowlist": {
            "exact": sorted(TARGET_DOC_ALLOWED_EXACT),
            "prefixes": list(TARGET_DOC_ALLOWED_PREFIXES),
        },
    }


def search_target_docs(
    config: TargetProjectConfig,
    *,
    state_dir: Path,
    query: str,
    max_results: int | None = None,
    path_prefix: str | None = None,
) -> dict[str, Any]:
    normalized_query = str(query or "").strip()
    if not normalized_query:
        raise TargetDocsError("query is required")
    limit = _clamped_int(max_results, TARGET_DOC_DEFAULT_MAX_RESULTS, 1, TARGET_DOC_MAX_RESULTS)
    prefix = _normalize_path_prefix(path_prefix) if path_prefix else None
    snapshot = _ensure_snapshot(config, state_dir=state_dir)
    paths = _list_allowed_paths(snapshot, config)
    if prefix:
        paths = tuple(path for path in paths if path == prefix or path.startswith(prefix.rstrip("/") + "/"))
    lowered = normalized_query.lower()
    results: list[dict[str, Any]] = []
    for path in paths:
        text, truncated = _show_text(snapshot, path, max_bytes=TARGET_DOC_SEARCH_FILE_BYTES)
        lines = text.splitlines()
        for index, line in enumerate(lines):
            if lowered not in line.lower():
                continue
            start = max(1, index)
            end = min(len(lines), index + 2)
            snippet = "\n".join(lines[start - 1 : end])
            results.append(
                {
                    "path": path,
                    "line_start": start,
                    "line_end": end,
                    "text": _sanitize_text(snippet),
                    "ref": _ref_payload(snapshot),
                    "file_truncated_for_search": truncated,
                }
            )
            if len(results) >= limit:
                return {
                    "status": "ok",
                    "target_id": config.project_id,
                    "query": normalized_query,
                    "max_results": limit,
                    "path_prefix": prefix,
                    "results": results,
                }
    return {
        "status": "ok",
        "target_id": config.project_id,
        "query": normalized_query,
        "max_results": limit,
        "path_prefix": prefix,
        "results": results,
    }


def get_target_doc(
    config: TargetProjectConfig,
    *,
    state_dir: Path,
    path: str,
    line_start: int | None = None,
    line_end: int | None = None,
    max_bytes: int | None = None,
) -> dict[str, Any]:
    doc_path = normalize_target_doc_path(path)
    _assert_allowed_doc_path(doc_path, config)
    limit = _clamped_int(max_bytes, TARGET_DOC_DEFAULT_MAX_BYTES, 1000, TARGET_DOC_MAX_BYTES)
    snapshot = _ensure_snapshot(config, state_dir=state_dir)
    bytes_total = _object_size(snapshot, doc_path)
    if bytes_total > TARGET_DOC_ABSOLUTE_FILE_BYTES:
        raise TargetDocsError("target doc is too large for MCP reads")
    text, byte_truncated = _show_text(snapshot, doc_path, max_bytes=max(bytes_total, limit))
    lines = text.splitlines()
    selected_start = _optional_positive_int(line_start) or 1
    requested_end = _optional_positive_int(line_end)
    if requested_end is None:
        selected_end = len(lines) if selected_start == 1 else selected_start + TARGET_DOC_MAX_LINE_COUNT - 1
    else:
        selected_end = requested_end
    selected_end = max(selected_start, min(selected_end, len(lines) or 1))
    if selected_end - selected_start + 1 > TARGET_DOC_MAX_LINE_COUNT:
        selected_end = selected_start + TARGET_DOC_MAX_LINE_COUNT - 1
    selected_lines = lines[selected_start - 1 : selected_end]
    selected_text = "\n".join(selected_lines)
    sanitized = _sanitize_text(selected_text)
    encoded = sanitized.encode("utf-8")
    content_truncated = len(encoded) > limit
    if content_truncated:
        sanitized = encoded[:limit].decode("utf-8", errors="replace") + "\n\n[truncated]"
    return {
        "status": "ok",
        "target_id": config.project_id,
        "path": doc_path,
        "ref": _ref_payload(snapshot),
        "line_start": selected_start,
        "line_end": selected_end,
        "max_bytes": limit,
        "bytes_total": bytes_total,
        "content": sanitized,
        "truncated": bool(byte_truncated or content_truncated or selected_end < len(lines)),
    }


def normalize_target_doc_path(path: str) -> str:
    text = str(path or "").strip()
    if not text:
        raise TargetDocsError("path is required")
    if "\x00" in text or "\\" in text:
        raise TargetDocsError("target doc path contains an invalid character")
    if text.startswith("/") or text.startswith("~"):
        raise TargetDocsError("absolute target doc paths are not allowed")
    parts = text.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise TargetDocsError("target doc path traversal is not allowed")
    return "/".join(parts)


def _ensure_snapshot(config: TargetProjectConfig, *, state_dir: Path) -> _Snapshot:
    if config.source_mode == "remote_managed_clone":
        if not config.repo_url:
            raise TargetDocsError("repo_url is required for remote target docs reads")
        cache = _cache_dir(state_dir, config.project_id)
        git_dir = cache / "source.git"
        cache.mkdir(parents=True, exist_ok=True)
        if not git_dir.exists():
            _git_checked(
                ("git", "clone", "--bare", "--no-tags", "--single-branch", "--branch", config.branch, config.repo_url, str(git_dir)),
                cwd=cache,
                timeout=60,
            )
            _write_cache_meta(cache)
        elif _should_refresh(cache):
            _git_checked(
                ("git", f"--git-dir={git_dir}", "fetch", "--quiet", "--no-tags", "origin", f"{config.branch}:refs/heads/{config.branch}"),
                timeout=60,
            )
            _write_cache_meta(cache)
        commit = _git_text(("git", f"--git-dir={git_dir}", "rev-parse", f"refs/heads/{config.branch}"))
        if not commit:
            raise TargetDocsError("target docs git snapshot has no readable branch commit")
        return _Snapshot(
            kind="bare",
            target_id=config.project_id,
            branch=config.branch,
            commit=commit,
            source_mode=config.source_mode,
            git_dir=git_dir,
            cache_dir=cache,
            fetched_at=_read_cache_meta(cache).get("fetched_at"),
        )
    repo_path = Path(config.repo_path).expanduser().resolve()
    if not repo_path.exists():
        raise TargetDocsError("local target repo path is missing")
    commit = _git_text(("git", "-C", str(repo_path), "rev-parse", config.branch or "HEAD")) or _git_text(("git", "-C", str(repo_path), "rev-parse", "HEAD"))
    if not commit:
        raise TargetDocsError("local target repo has no readable commit")
    return _Snapshot(
        kind="local",
        target_id=config.project_id,
        branch=config.branch,
        commit=commit,
        source_mode=config.source_mode,
        repo_path=repo_path,
    )


def _list_allowed_paths(snapshot: _Snapshot, config: TargetProjectConfig) -> tuple[str, ...]:
    output = _git_text(_git_args(snapshot, "ls-tree", "-r", "--name-only", snapshot.commit))
    paths = []
    for raw in output.splitlines():
        path = raw.strip()
        if not path:
            continue
        try:
            normalized = normalize_target_doc_path(path)
            _assert_allowed_doc_path(normalized, config)
        except TargetDocsError:
            continue
        paths.append(normalized)
    return tuple(sorted(dict.fromkeys(paths)))


def _assert_allowed_doc_path(path: str, config: TargetProjectConfig) -> None:
    normalized = normalize_target_doc_path(path)
    forbidden = tuple(config.default_forbidden_paths or ()) + TARGET_DOC_FORBIDDEN_GLOBS
    if any(_path_matches(normalized, pattern) for pattern in forbidden):
        raise TargetDocsError("target doc path is outside the allowed documentation boundary")
    name = Path(normalized).name.lower()
    if name in {"auth.json", "credentials.json", "secrets.json"} or name.endswith((".pem", ".key", ".p12", ".pfx")):
        raise TargetDocsError("target doc path is secret-like and denied")
    if normalized in TARGET_DOC_ALLOWED_EXACT:
        return
    if normalized.startswith(TARGET_DOC_ALLOWED_PREFIXES) and Path(normalized).suffix.lower() in TARGET_DOC_TEXT_SUFFIXES:
        return
    raise TargetDocsError("target doc path is outside the allowed documentation boundary")


def _normalize_path_prefix(prefix: str | None) -> str | None:
    if prefix is None:
        return None
    normalized = normalize_target_doc_path(prefix)
    if normalized in TARGET_DOC_ALLOWED_EXACT:
        return normalized
    if normalized.rstrip("/") in tuple(item.rstrip("/") for item in TARGET_DOC_ALLOWED_PREFIXES):
        return normalized.rstrip("/")
    if normalized.startswith(TARGET_DOC_ALLOWED_PREFIXES):
        return normalized.rstrip("/")
    raise TargetDocsError("path_prefix is outside the allowed documentation boundary")


def _show_text(snapshot: _Snapshot, path: str, *, max_bytes: int) -> tuple[str, bool]:
    completed = _git(_git_args(snapshot, "show", f"{snapshot.commit}:{path}"), timeout=20)
    if completed.returncode != 0:
        raise TargetDocsError("target doc path was not found in the target snapshot")
    raw = completed.stdout.encode("utf-8", errors="replace")
    truncated = len(raw) > max_bytes
    text = raw[:max_bytes].decode("utf-8", errors="replace")
    return text, truncated


def _object_size(snapshot: _Snapshot, path: str) -> int:
    output = _git_text(_git_args(snapshot, "cat-file", "-s", f"{snapshot.commit}:{path}"))
    try:
        return int(output.strip())
    except ValueError:
        raise TargetDocsError("target doc path was not found in the target snapshot") from None


def _git_args(snapshot: _Snapshot, *args: str) -> tuple[str, ...]:
    if snapshot.kind == "bare":
        if snapshot.git_dir is None:
            raise TargetDocsError("target docs cache is unavailable")
        return ("git", f"--git-dir={snapshot.git_dir}", *args)
    if snapshot.repo_path is None:
        raise TargetDocsError("target repo path is unavailable")
    return ("git", "-C", str(snapshot.repo_path), *args)


def _git(command: Sequence[str], *, cwd: Path | None = None, timeout: int = 20) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            tuple(command),
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
            env=_safe_git_env(),
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return subprocess.CompletedProcess(tuple(command), 124, stdout, stderr or "git command timed out")


def _git_checked(command: Sequence[str], *, cwd: Path | None = None, timeout: int = 20) -> None:
    completed = _git(command, cwd=cwd, timeout=timeout)
    if completed.returncode != 0:
        raise TargetDocsError(_safe_git_error(completed))


def _git_text(command: Sequence[str]) -> str:
    completed = _git(command)
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()


def _git_version() -> dict[str, Any]:
    completed = _git(("git", "--version"), timeout=5)
    return {"status": "ready" if completed.returncode == 0 else "missing"}


def _safe_git_env() -> dict[str, str]:
    env: dict[str, str] = {"GIT_TERMINAL_PROMPT": "0"}
    for key in ("PATH", "HOME", "LANG", "LC_ALL", "XDG_CONFIG_HOME"):
        value = os.environ.get(key)
        if value:
            env[key] = value
    return env


def _safe_git_error(completed: subprocess.CompletedProcess[str]) -> str:
    text = "\n".join(part.strip() for part in (completed.stdout, completed.stderr) if part and part.strip())
    if not text:
        text = f"git exited with status {completed.returncode}"
    return _truncate(_sanitize_text(text.replace("\n", " ")), 500)


def _cache_dir(state_dir: Path, target_id: str) -> Path:
    return Path(state_dir).resolve() / "target_docs" / safe_state_component(target_id, "target_id")


def _should_refresh(cache: Path) -> bool:
    meta = _read_cache_meta(cache)
    fetched = float(meta.get("fetched_epoch") or 0)
    ttl = _clamped_int(os.environ.get("DEV_CONTROL_PLANE_TARGET_DOCS_FETCH_TTL_SECONDS"), TARGET_DOC_FETCH_TTL_SECONDS, 30, 3600)
    return time.time() - fetched > ttl


def _write_cache_meta(cache: Path) -> None:
    payload = {"fetched_at": _now_utc(), "fetched_epoch": time.time()}
    (cache / "metadata.json").write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _read_cache_meta(cache: Path) -> dict[str, Any]:
    try:
        payload = json.loads((cache / "metadata.json").read_text(encoding="utf-8"))
    except Exception:
        return {}
    return dict(payload) if isinstance(payload, Mapping) else {}


def _cached_commit(cache_git_dir: Path, branch: str) -> str | None:
    commit = _git_text(("git", f"--git-dir={cache_git_dir}", "rev-parse", f"refs/heads/{branch}"))
    return commit or None


def _path_matches(path: str, pattern: str) -> bool:
    normalized_pattern = str(pattern or "").strip().replace("\\", "/").lstrip("./")
    if not normalized_pattern:
        return False
    if normalized_pattern.endswith("/"):
        normalized_pattern += "**"
    return fnmatch.fnmatchcase(path, normalized_pattern)


def _doc_type(path: str) -> str:
    if path == "README.md":
        return "readme"
    if path == "AGENTS.md":
        return "agents"
    if path.startswith("docs/architecture/"):
        return "architecture"
    if path.startswith("docs/modules/"):
        return "modules"
    if path.startswith("migration/"):
        return "migration"
    return "doc"


def _ref_payload(snapshot: _Snapshot) -> dict[str, Any]:
    return {
        "branch": snapshot.branch,
        "commit": snapshot.commit,
        "source_mode": snapshot.source_mode,
        "cache_fetched_at": snapshot.fetched_at,
    }


def _sanitize_text(text: str) -> str:
    result = str(text)
    for pattern in _SECRET_TEXT_PATTERNS:
        result = pattern.sub("[redacted]", result)
    return result


def _clamped_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _optional_positive_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _truncate(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[: limit - 15] + "...[truncated]"


def _now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
