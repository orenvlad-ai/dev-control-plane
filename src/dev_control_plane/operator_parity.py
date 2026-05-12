"""Operator-parity execution support for wb-core.

This lane is intentionally separate from the ordinary managed-clone auto route.
It preflights host/runtime capabilities before Codex starts and exposes only
sanitized status/artifact data.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any, Mapping, Sequence

from dev_control_plane.github_auth import build_github_auth_status
from dev_control_plane.live_monitor import sanitize_terminal_text
from dev_control_plane.ssh_deploy import build_ssh_deploy_status
from dev_control_plane.target_production import inspect_wb_core_production_lock
from dev_control_plane.target_projects import TargetProjectConfig
from dev_control_plane.toolchain import (
    build_browser_readiness,
    build_codex_auth_status,
    build_toolchain_status,
    runtime_command_env,
    runtime_path,
)

OPERATOR_PARITY_ROUTE = "wb_core_operator_parity_task"

DEFAULT_REQUIRED_CAPABILITIES = (
    "toolchain_ready",
    "codex_auth_ready",
    "operator_worktree_ready",
    "github_ready",
    "ssh_ready",
    "runtime_state_readable",
    "db_readable",
    "browser_ready",
    "browser_session_ready",
    "promo_collector_runnable",
    "xlsx_download_runnable",
    "deploy_gate_ready",
    "secret_broker_ready",
    "redaction_ready",
    "artifact_quarantine_ready",
)

SECRET_LIKE_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bgh[opsu]_[A-Za-z0-9_]{20,}"),
    re.compile(r"(?i)\b(authorization|bearer|cookie|password|secret|session|token|api[_-]?key)\s*[:=]\s*[^\s\"']{8,}"),
    re.compile(r"(?i)\b[A-Za-z0-9_]*(?:token|secret|password|cookie)[A-Za-z0-9_]*\b\s*=\s*[^\s\"']{8,}"),
)


@dataclass(frozen=True)
class OperatorParityConfig:
    enabled: bool
    persistent_worktree_path: Path
    runtime_state_path: Path | None
    allowed_runtime_read_paths: tuple[Path, ...]
    allowed_runtime_write_paths: tuple[Path, ...]
    db_probe_paths: tuple[Path, ...]
    browser_session_paths: tuple[Path, ...]
    collector_runners: Mapping[str, str]
    artifact_quarantine_dir: Path
    required_capabilities: tuple[str, ...]
    service_user: str | None
    service_group: str | None
    forbidden_secret_surfaces: tuple[str, ...]


def operator_parity_config(target_config: TargetProjectConfig, *, state_dir: Path, env: Mapping[str, str] | None = None) -> OperatorParityConfig:
    raw = dict(getattr(target_config, "operator_parity", {}) or {})
    environment = env or os.environ
    substitutions = {
        "state_dir": str(state_dir),
        "runtime_root": str(Path(str(environment.get("DEV_CONTROL_PLANE_RUNTIME_ROOT") or "/opt/dev-control-plane-runtime"))),
    }
    worktree = _path(raw.get("persistent_worktree_path") or "{state_dir}/operator_worktrees/wb-core", substitutions)
    quarantine = _path(raw.get("artifact_quarantine_dir") or "{state_dir}/artifact_quarantine/operator_parity", substitutions)
    runtime_state = raw.get("runtime_state_path")
    return OperatorParityConfig(
        enabled=bool(raw.get("enabled", True)),
        persistent_worktree_path=worktree,
        runtime_state_path=_path(runtime_state, substitutions) if runtime_state else None,
        allowed_runtime_read_paths=tuple(_path(item, substitutions) for item in _sequence(raw.get("allowed_runtime_read_paths"))),
        allowed_runtime_write_paths=tuple(_path(item, substitutions) for item in _sequence(raw.get("allowed_runtime_write_paths"))),
        db_probe_paths=tuple(_path(item, substitutions) for item in _sequence(raw.get("db_probe_paths"))),
        browser_session_paths=tuple(_path(item, substitutions) for item in _sequence(raw.get("browser_session_paths"))),
        collector_runners={str(key): str(value) for key, value in dict(raw.get("collector_runners") or {}).items()},
        artifact_quarantine_dir=quarantine,
        required_capabilities=tuple(str(item) for item in _sequence(raw.get("required_capabilities")) if str(item).strip()) or DEFAULT_REQUIRED_CAPABILITIES,
        service_user=str(raw.get("service_user") or "") or None,
        service_group=str(raw.get("service_group") or "") or None,
        forbidden_secret_surfaces=tuple(str(item) for item in _sequence(raw.get("forbidden_secret_surfaces"))),
    )


def build_operator_parity_status(
    target_config: TargetProjectConfig,
    *,
    state_dir: Path,
    env: Mapping[str, str] | None = None,
    launch_browser: bool = False,
    check_remote: bool = False,
) -> dict[str, Any]:
    environment = env or os.environ
    config = operator_parity_config(target_config, state_dir=state_dir, env=environment)
    capabilities: dict[str, dict[str, Any]] = {}
    fake_ready = str(environment.get("DEV_CONTROL_PLANE_OPERATOR_PARITY_FAKE_READY") or "").strip().lower() in {"1", "true", "yes"}

    if fake_ready:
        toolchain = {"status": "ready", "missing_required": [], "source": "operator_parity_test_override"}
        codex_auth = {"status": "authenticated", "authenticated": True, "blocker": None, "source": "operator_parity_test_override"}
        github = {"status": "ready", "blocker": None, "source": "operator_parity_test_override"}
        ssh = {"status": "ready", "blocker": None, "source": "operator_parity_test_override"}
        browser = {"status": "ready", "blocker": None, "source": "operator_parity_test_override", "webcore_ui_browser_ready": True}
    else:
        toolchain = build_toolchain_status(env=environment, workspace_path=config.persistent_worktree_path, codex_bin=_codex_bin(environment))
        codex_auth = build_codex_auth_status(_codex_bin(environment), env=environment)
        github = build_github_auth_status(env=environment, repo="orenvlad-ai/wb-core", repo_url=target_config.repo_url, require_write=True, check_remote=check_remote)
        ssh = build_ssh_deploy_status(env=environment, target_id=target_config.project_id, check_remote=check_remote)
        browser = build_browser_readiness(env=environment, launch=launch_browser)
    lock = inspect_wb_core_production_lock(
        workspace_path=config.persistent_worktree_path if config.persistent_worktree_path.exists() else None,
        run_dir=state_dir / "runs" / "operator-parity-lock-probe",
        run_id="operator-parity-lock-probe",
    )

    capabilities["operator_worktree_ready"] = _worktree_capability(config, target_config, check_remote=check_remote, env=environment)
    capabilities["github_ready"] = _simple_capability("github_ready", github.get("status") == "ready", github.get("blocker"), status_payload=github)
    capabilities["ssh_ready"] = _simple_capability("ssh_ready", ssh.get("status") == "ready", ssh.get("blocker"), status_payload=ssh)
    capabilities["runtime_state_readable"] = _path_capability("runtime_state_readable", config.runtime_state_path, readable=True, required_label="runtime state path")
    capabilities["runtime_state_writable_if_policy_allows"] = _write_policy_capability(config.allowed_runtime_write_paths)
    capabilities["db_readable"] = _all_paths_capability("db_readable", config.db_probe_paths, "runtime DB/source snapshot probe paths")
    capabilities["browser_ready"] = _simple_capability("browser_ready", browser.get("status") == "ready", browser.get("blocker"), status_payload=browser)
    capabilities["browser_session_ready"] = _all_paths_capability("browser_session_ready", config.browser_session_paths, "browser/session profile paths")
    capabilities["promo_collector_runnable"] = _runner_capability("promo_collector_runnable", "promo_collector", config, env=environment)
    capabilities["xlsx_download_runnable"] = _runner_capability("xlsx_download_runnable", "xlsx_download", config, env=environment)
    deploy_ready = github.get("status") == "ready" and ssh.get("status") == "ready" and lock.get("status") == "free"
    deploy_blocker = None if deploy_ready else "; ".join(str(item) for item in (github.get("blocker"), ssh.get("blocker"), f"production lock is {lock.get('status')}" if lock.get("status") != "free" else None) if item)
    capabilities["deploy_gate_ready"] = _simple_capability("deploy_gate_ready", deploy_ready, deploy_blocker, status_payload={"lock": lock})
    capabilities["secret_broker_ready"] = _secret_broker_capability(environment)
    capabilities["redaction_ready"] = _redaction_capability()
    capabilities["artifact_quarantine_ready"] = _quarantine_capability("artifact_quarantine_ready", config.artifact_quarantine_dir)
    capabilities["artifact_write_path"] = _quarantine_capability("artifact_write_path", state_dir / "runs")
    capabilities["codex_auth_ready"] = _simple_capability("codex_auth_ready", bool(codex_auth.get("authenticated")), codex_auth.get("blocker"), status_payload=codex_auth)
    capabilities["toolchain_ready"] = _simple_capability("toolchain_ready", toolchain.get("status") == "ready", "; ".join(toolchain.get("missing_required") or []), status_payload=toolchain)

    required = list(config.required_capabilities)
    blockers = [
        f"{name}: {capabilities.get(name, {}).get('blocker') or capabilities.get(name, {}).get('status')}"
        for name in required
        if capabilities.get(name, {}).get("status") != "ready"
    ]
    optional_degraded = [name for name, cap in capabilities.items() if name not in required and cap.get("status") not in {"ready", "not_required"}]
    status = "blocked" if blockers or not config.enabled else ("degraded" if optional_degraded else "ready")
    manual_step = _manual_step(config, blockers)
    return {
        "status": status,
        "route": OPERATOR_PARITY_ROUTE,
        "target_id": target_config.project_id,
        "enabled": config.enabled,
        "required_capabilities": required,
        "optional_capabilities": [name for name in capabilities if name not in required],
        "capabilities": _json_ready(capabilities),
        "exact_blocker": "; ".join(blockers) if blockers else None,
        "suggested_manual_step": manual_step,
        "operator_worktree_path": _sanitize_path(config.persistent_worktree_path),
        "runtime_state_path": _sanitize_path(config.runtime_state_path),
        "artifact_quarantine_dir": _sanitize_path(config.artifact_quarantine_dir),
        "service_identity": {
            "expected_user": config.service_user,
            "expected_group": config.service_group,
            "actual_uid": os.getuid() if hasattr(os, "getuid") else None,
        },
        "forbidden_secret_surfaces": list(config.forbidden_secret_surfaces),
        "toolchain_summary": {
            "status": toolchain.get("status"),
            "missing_required": toolchain.get("missing_required", []),
            "codex_auth_status": codex_auth.get("status"),
        },
    }


def build_runtime_broker_export(target_config: TargetProjectConfig, *, state_dir: Path, env: Mapping[str, str] | None = None, max_entries: int = 200) -> dict[str, Any]:
    config = operator_parity_config(target_config, state_dir=state_dir, env=env)
    entries: list[dict[str, Any]] = []
    for root in config.allowed_runtime_read_paths:
        if not _path_exists_for_probe(root):
            entries.append({"path": _sanitize_path(root), "status": "missing"})
            continue
        if not _path_readable(root):
            entries.append({"path": _sanitize_path(root), "status": "unreadable"})
            continue
        if _path_is_file(root):
            entries.append(_file_entry(root, root))
            continue
        count = 0
        try:
            paths = sorted(root.rglob("*"))
        except OSError:
            entries.append({"path": _sanitize_path(root), "status": "unreadable"})
            continue
        for path in paths:
            if count >= max_entries:
                break
            if _path_is_file(path) and not _secret_surface(path):
                entries.append(_file_entry(root, path))
                count += 1
    return {
        "status": "ok",
        "target_id": target_config.project_id,
        "mode": "read_only_sanitized_metadata_export",
        "entries": entries,
        "truncated": len(entries) >= max_entries,
    }


def redact_text(text: str) -> str:
    result = str(text or "")
    for pattern in SECRET_LIKE_PATTERNS:
        result = pattern.sub("[redacted]", result)
    return sanitize_terminal_text(result)


def contains_secret_like_content(text: str) -> bool:
    return any(pattern.search(str(text or "")) for pattern in SECRET_LIKE_PATTERNS)


def write_operator_artifact(run_dir: Path, relative_path: str, content: str, *, quarantine_dir: Path) -> dict[str, Any]:
    safe_rel = Path(relative_path)
    if safe_rel.is_absolute() or ".." in safe_rel.parts:
        raise ValueError("artifact path must be run-relative")
    artifact_path = run_dir / "artifacts" / safe_rel
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    if contains_secret_like_content(content):
        quarantine_dir.mkdir(parents=True, exist_ok=True)
        event = {
            "status": "secret_like_content_blocked",
            "artifact": str(safe_rel),
            "artifact_type": safe_rel.suffix.lstrip(".") or safe_rel.name,
            "quarantined_at": _now_utc(),
            "raw_content_preserved": False,
            "reason": "secret-like content matched redaction policy",
        }
        manifest = quarantine_dir / f"{safe_rel.name}.quarantine.json"
        manifest.write_text(json.dumps(event, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        artifact_path.write_text(redact_text(content), encoding="utf-8")
        return {**event, "path": _sanitize_path(artifact_path), "quarantine_manifest": _sanitize_path(manifest)}
    artifact_path.write_text(redact_text(content), encoding="utf-8")
    return {"status": "written", "path": _sanitize_path(artifact_path), "artifact": str(safe_rel)}


def operator_parity_command(
    *,
    codex_bin: str,
    worktree: Path,
    prompt_text: str,
    handoff_path: Path,
    model: str,
    reasoning_effort: str,
) -> list[str]:
    return [
        codex_bin,
        "exec",
        "--cd",
        str(worktree),
        "--sandbox",
        "danger-full-access",
        "--model",
        model,
        "-c",
        f"model_reasoning_effort={json.dumps(reasoning_effort)}",
        "--json",
        "--output-last-message",
        str(handoff_path),
        prompt_text,
    ]


def operator_parity_command_env(env: Mapping[str, str] | None = None) -> dict[str, str]:
    return runtime_command_env(env or os.environ, git_prompt=True)


def git_changed_files(worktree: Path, base_ref: str | None = None) -> tuple[str, ...]:
    paths: set[str] = set()
    status = _run(("git", "status", "--porcelain=v1", "--untracked-files=all"), cwd=worktree)
    if status.returncode == 0:
        for line in status.stdout.splitlines():
            if len(line) > 3:
                paths.add(line[3:].split(" -> ")[-1].strip())
    if base_ref:
        diff = _run(("git", "diff", "--name-only", base_ref, "HEAD"), cwd=worktree)
        if diff.returncode == 0:
            paths.update(line.strip() for line in diff.stdout.splitlines() if line.strip())
    return tuple(sorted(path for path in paths if path and not _secret_surface(Path(path))))


def _worktree_capability(config: OperatorParityConfig, target_config: TargetProjectConfig, *, check_remote: bool, env: Mapping[str, str]) -> dict[str, Any]:
    path = config.persistent_worktree_path
    if not path.exists():
        return _capability("operator_worktree_ready", "blocked", f"operator parity worktree is missing: {_sanitize_path(path)}", path=path)
    if not (path / ".git").exists():
        return _capability("operator_worktree_ready", "blocked", f"operator parity worktree is not a git checkout: {_sanitize_path(path)}", path=path)
    top = _run(("git", "rev-parse", "--show-toplevel"), cwd=path, env=env)
    if top.returncode != 0:
        return _capability("operator_worktree_ready", "blocked", "operator parity worktree git metadata is not readable", path=path)
    fetch_status = "not_checked"
    if check_remote:
        fetch = _run(("git", "fetch", "--dry-run", "origin", str(target_config.branch or "main")), cwd=path, env=env, timeout=20)
        if fetch.returncode != 0:
            return _capability("operator_worktree_ready", "blocked", "operator parity worktree cannot fetch target origin", path=path)
        fetch_status = "ready"
    head = _run(("git", "rev-parse", "HEAD"), cwd=path, env=env)
    dirty = _run(("git", "status", "--short"), cwd=path, env=env)
    return _capability(
        "operator_worktree_ready",
        "ready",
        None,
        path=path,
        extra={"head_commit": head.stdout.strip() if head.returncode == 0 else None, "dirty": bool(dirty.stdout.strip()), "fetch_status": fetch_status},
    )


def _simple_capability(name: str, ready: bool, blocker: Any, *, status_payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return _capability(name, "ready" if ready else "blocked", None if ready else str(blocker or f"{name} is not ready"), extra={"details": _json_ready(dict(status_payload or {}))})


def _path_capability(name: str, path: Path | None, *, readable: bool, required_label: str) -> dict[str, Any]:
    if path is None:
        return _capability(name, "blocked", f"{required_label} is not configured")
    if not _path_exists_for_probe(path):
        return _capability(name, "blocked", f"{required_label} is missing: {_sanitize_path(path)}", path=path)
    if readable and not _path_readable(path):
        return _capability(name, "blocked", f"{required_label} is not readable by the service user", path=path)
    return _capability(name, "ready", None, path=path)


def _all_paths_capability(name: str, paths: Sequence[Path], label: str) -> dict[str, Any]:
    if not paths:
        return _capability(name, "blocked", f"{label} are not configured")
    missing = [_sanitize_path(path) for path in paths if not _path_exists_for_probe(path)]
    unreadable = [_sanitize_path(path) for path in paths if _path_exists_for_probe(path) and not _path_readable(path)]
    if missing or unreadable:
        return _capability(name, "blocked", f"{label} unavailable; missing={missing}; unreadable={unreadable}", extra={"paths": [_sanitize_path(path) for path in paths]})
    return _capability(name, "ready", None, extra={"paths": [_sanitize_path(path) for path in paths]})


def _write_policy_capability(paths: Sequence[Path]) -> dict[str, Any]:
    if not paths:
        return _capability("runtime_state_writable_if_policy_allows", "ready", None, extra={"policy": "runtime writes not allowed for parity research by default"})
    blocked = [_sanitize_path(path) for path in paths if not path.exists() or not os.access(path, os.W_OK)]
    if blocked:
        return _capability("runtime_state_writable_if_policy_allows", "blocked", f"configured runtime write paths are not writable: {blocked}")
    return _capability("runtime_state_writable_if_policy_allows", "ready", None, extra={"paths": [_sanitize_path(path) for path in paths]})


def _runner_capability(name: str, runner_key: str, config: OperatorParityConfig, *, env: Mapping[str, str]) -> dict[str, Any]:
    raw = config.collector_runners.get(runner_key)
    if not raw:
        return _capability(name, "blocked", f"{runner_key} runner is not configured")
    path = Path(raw)
    if not path.is_absolute():
        path = config.persistent_worktree_path / path
    if not _path_exists_for_probe(path):
        return _capability(name, "blocked", f"{runner_key} runner is missing: {_sanitize_path(path)}", path=path)
    runnable = _path_executable(path) or path.suffix == ".py"
    return _capability(name, "ready" if runnable else "blocked", None if runnable else f"{runner_key} runner is not executable/readable", path=path)


def _secret_broker_capability(env: Mapping[str, str]) -> dict[str, Any]:
    secret_home = Path(str(env.get("DEV_CONTROL_PLANE_SECRET_HOME") or "")).expanduser() if env.get("DEV_CONTROL_PLANE_SECRET_HOME") else None
    if not secret_home:
        return _capability("secret_broker_ready", "blocked", "DEV_CONTROL_PLANE_SECRET_HOME is not configured")
    if not _path_exists_for_probe(secret_home):
        return _capability("secret_broker_ready", "blocked", "configured secret broker directory is missing", path=secret_home)
    if not _path_readable(secret_home):
        return _capability("secret_broker_ready", "blocked", "configured secret broker directory is not readable by the service user", path=secret_home)
    return _capability("secret_broker_ready", "ready", None, path=secret_home, extra={"mode": "runtime_secret_home"})


def _redaction_capability() -> dict[str, Any]:
    sample = "Authorization" + ": " + "Bearer" + " " + ("sk-" + "testsecret0000000000000000")
    redacted = redact_text(sample)
    ready = "[redacted]" in redacted and "sk-testsecret" not in redacted
    return _capability("redaction_ready", "ready" if ready else "blocked", None if ready else "redaction self-test failed")


def _quarantine_capability(name: str, path: Path) -> dict[str, Any]:
    if _path_exists_for_probe(path):
        ready = _path_is_dir(path) and _path_writable(path)
        return _capability(name, "ready" if ready else "blocked", None if ready else f"{name} path is not writable", path=path)
    parent = path.parent
    while not _path_exists_for_probe(parent) and parent != parent.parent:
        parent = parent.parent
    ready = _path_exists_for_probe(parent) and _path_writable(parent)
    return _capability(name, "ready" if ready else "blocked", None if ready else f"{name} parent is not writable", path=path)


def _path_exists_for_probe(path: Path) -> bool:
    try:
        return path.exists()
    except OSError:
        return True


def _path_is_file(path: Path) -> bool:
    try:
        return path.is_file()
    except OSError:
        return False


def _path_is_dir(path: Path) -> bool:
    try:
        return path.is_dir()
    except OSError:
        return False


def _path_readable(path: Path) -> bool:
    try:
        return os.access(path, os.R_OK)
    except OSError:
        return False


def _path_writable(path: Path) -> bool:
    try:
        return os.access(path, os.W_OK)
    except OSError:
        return False


def _path_executable(path: Path) -> bool:
    try:
        return os.access(path, os.X_OK)
    except OSError:
        return False


def _capability(name: str, status: str, blocker: str | None, *, path: Path | None = None, extra: Mapping[str, Any] | None = None) -> dict[str, Any]:
    payload = {
        "name": name,
        "status": status,
        "ready": status == "ready",
        "blocker": blocker,
    }
    if path is not None:
        payload["path"] = _sanitize_path(path)
    if extra:
        payload.update(_json_ready(dict(extra)))
    return payload


def _manual_step(config: OperatorParityConfig, blockers: Sequence[str]) -> str | None:
    if not blockers:
        return None
    joined = " ".join(blockers)
    if "operator_worktree_ready" in joined:
        return f"On the DevControl host as the service user, create a persistent wb-core operator worktree at {_sanitize_path(config.persistent_worktree_path)} from the configured wb-core origin."
    if "runtime_state_readable" in joined:
        return "Grant the DevControl service user read access to the configured wb-core runtime state path or configure the sanitized broker allowlist to a readable export."
    return "Fix the first blocked required capability shown in operator parity status, then rerun get_operator_parity_status."


def _file_entry(root: Path, path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "root": _sanitize_path(root),
        "path": str(path.relative_to(root)) if path != root else path.name,
        "bytes": stat.st_size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "content_exported": False,
    }


def _secret_surface(path: Path) -> bool:
    lowered = str(path).lower()
    return any(token in lowered for token in ("secret", "token", "cookie", "session", "auth.json", ".env", "credentials"))


def _path(value: Any, substitutions: Mapping[str, str]) -> Path:
    text = str(value or "")
    for key, replacement in substitutions.items():
        text = text.replace("{" + key + "}", replacement)
    return Path(text).expanduser()


def _sequence(value: Any) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, (list, tuple)):
        return tuple(value)
    return (value,)


def _run(args: Sequence[str], *, cwd: Path, env: Mapping[str, str] | None = None, timeout: int = 10) -> subprocess.CompletedProcess[str]:
    return subprocess.run(tuple(args), cwd=cwd, capture_output=True, text=True, check=False, timeout=timeout, env=runtime_command_env(env or os.environ))


def _codex_bin(env: Mapping[str, str]) -> str | None:
    explicit = str(env.get("DEV_CONTROL_PLANE_CODEX_BIN") or "").strip()
    return explicit or shutil.which("codex", path=runtime_path(env))


def _sanitize_path(path: Path | str | None) -> str | None:
    if path is None:
        return None
    text = str(path)
    home = str(Path.home())
    if home and text.startswith(home):
        text = "~" + text[len(home):]
    return text.replace("/opt/dev-control-plane-runtime/secrets", "/opt/dev-control-plane-runtime/[secrets]")


def _json_ready(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_ready(item) for item in value]
    if isinstance(value, Path):
        return _sanitize_path(value)
    return value


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
