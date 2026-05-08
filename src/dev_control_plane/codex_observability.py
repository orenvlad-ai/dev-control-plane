"""Codex process supervision and non-secret run diagnostics."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import time
from typing import Any, Mapping, Sequence

CODEX_PROCESS_STATE_NAME = "codex_process.json"
DEFAULT_CODEX_IO_MODE = "auto"
CODEX_IO_MODES = {"auto", "event", "pty"}
DEFAULT_MAX_WALL_SECONDS = 3 * 60 * 60
DEFAULT_NO_OUTPUT_SECONDS = 45 * 60


def codex_observability_status(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    config = codex_supervision_config(env)
    return {
        "status": "ready",
        "raw_event_log": "logs/codex.log",
        "human_terminal_transcript": "logs/terminal.log",
        "process_state": f"logs/{CODEX_PROCESS_STATE_NAME}",
        "watchdog": {
            "enabled": True,
            "max_wall_seconds": config["max_wall_seconds"],
            "no_output_seconds": config["no_output_seconds"],
            "timeout_status": "stale_timeout",
            "lost_process_status": "stale_lost_process",
        },
        "cancel": {
            "enabled": True,
            "scope": "run_owned_process_group_only",
            "preserve_artifacts": True,
        },
        "io_mode": {
            "configured": config["io_mode"],
            "effective": config["effective_io_mode"],
            "pty_supported": False,
            "pty_reason": (
                "PTY capture is diagnostic-only in this build; event JSONL capture remains the safe default."
                if config["io_mode"] != "pty"
                else "PTY requested but not enabled because browser/API must stay read-only and event JSONL is safer."
            ),
        },
        "prompt_consistency_gate": {
            "enabled": True,
            "blocks": [
                "production_lane combined with repo-only/no live/deploy/no UI/no Codex worker run",
                "UI task combined with no UI",
                "Codex run combined with no Codex worker run",
            ],
        },
    }


def codex_supervision_config(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    environment = env or os.environ
    raw_mode = str(environment.get("DEV_CONTROL_PLANE_CODEX_IO_MODE") or DEFAULT_CODEX_IO_MODE).strip().lower()
    io_mode = raw_mode if raw_mode in CODEX_IO_MODES else DEFAULT_CODEX_IO_MODE
    return {
        "io_mode": io_mode,
        "effective_io_mode": "event",
        "max_wall_seconds": _positive_int(environment.get("DEV_CONTROL_PLANE_CODEX_MAX_WALL_SECONDS"), DEFAULT_MAX_WALL_SECONDS),
        "no_output_seconds": _positive_int(environment.get("DEV_CONTROL_PLANE_CODEX_NO_OUTPUT_SECONDS"), DEFAULT_NO_OUTPUT_SECONDS),
    }


def process_state_path(run_dir: Path) -> Path:
    return Path(run_dir).resolve() / "logs" / CODEX_PROCESS_STATE_NAME


def write_process_started(
    run_dir: Path,
    *,
    pid: int,
    pgid: int,
    command_preview: Sequence[str],
    io_mode: str,
    max_wall_seconds: int,
    no_output_seconds: int,
) -> dict[str, Any]:
    now = _now_utc()
    payload = {
        "status": "running",
        "pid": int(pid),
        "pgid": int(pgid),
        "run_owned_process_group": True,
        "started_at": now,
        "last_output_at": now,
        "last_event_at": now,
        "updated_at": now,
        "elapsed_seconds": 0,
        "io_mode": io_mode,
        "command_preview": [str(item) for item in command_preview],
        "max_wall_seconds": int(max_wall_seconds),
        "no_output_seconds": int(no_output_seconds),
        "timeout_reason": None,
        "exit_code": None,
    }
    _write_state(run_dir, payload)
    return payload


def update_process_activity(run_dir: Path, *, output: bool = False, event: bool = False) -> dict[str, Any]:
    payload = read_process_state(run_dir) or {}
    now = _now_utc()
    if output:
        payload["last_output_at"] = now
    if event or output:
        payload["last_event_at"] = now
    payload["updated_at"] = now
    payload["elapsed_seconds"] = elapsed_seconds(payload.get("started_at"))
    _write_state(run_dir, payload)
    return payload


def finalize_process_state(run_dir: Path, *, status: str, exit_code: int | None = None, timeout_reason: str | None = None) -> dict[str, Any]:
    payload = read_process_state(run_dir) or {}
    now = _now_utc()
    payload["status"] = status
    payload["exit_code"] = exit_code
    payload["timeout_reason"] = timeout_reason
    payload["updated_at"] = now
    payload["elapsed_seconds"] = elapsed_seconds(payload.get("started_at"))
    _write_state(run_dir, payload)
    return payload


def read_process_state(run_dir: Path) -> dict[str, Any] | None:
    path = process_state_path(run_dir)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"status": "invalid", "blocker": "codex process state is not valid JSON"}
    return payload if isinstance(payload, dict) else {"status": "invalid", "blocker": "codex process state is not an object"}


def codex_stale_assessment(run_dir: Path, *, now: float | None = None) -> dict[str, Any]:
    state = read_process_state(run_dir)
    if not state:
        return {"status": "missing", "blocker": "codex process state is missing"}
    current = time.time() if now is None else now
    started_at = _parse_ts(state.get("started_at"))
    last_output_at = _parse_ts(state.get("last_output_at") or state.get("last_event_at") or state.get("started_at"))
    elapsed = max(0, int(current - started_at)) if started_at else 0
    idle = max(0, int(current - last_output_at)) if last_output_at else elapsed
    max_wall = _positive_int(state.get("max_wall_seconds"), DEFAULT_MAX_WALL_SECONDS)
    no_output = _positive_int(state.get("no_output_seconds"), DEFAULT_NO_OUTPUT_SECONDS)
    pid = _int_or_none(state.get("pid"))
    alive = _pid_alive(pid) if pid else False
    status = str(state.get("status") or "")
    if status not in {"running", "started"}:
        return {"status": status or "not_running", "alive": alive, "elapsed_seconds": elapsed, "idle_seconds": idle}
    if pid and not alive:
        return {
            "status": "stale_lost_process",
            "alive": False,
            "elapsed_seconds": elapsed,
            "idle_seconds": idle,
            "blocker": "Codex process is no longer alive but run is still active.",
        }
    if max_wall and elapsed > max_wall:
        return {
            "status": "stale_timeout",
            "alive": alive,
            "elapsed_seconds": elapsed,
            "idle_seconds": idle,
            "blocker": f"Codex exceeded max wall time: {elapsed}s > {max_wall}s.",
        }
    if no_output and idle > no_output:
        return {
            "status": "stale_timeout",
            "alive": alive,
            "elapsed_seconds": elapsed,
            "idle_seconds": idle,
            "blocker": f"Codex produced no output/event for {idle}s > {no_output}s.",
        }
    return {"status": "running", "alive": alive, "elapsed_seconds": elapsed, "idle_seconds": idle}


def terminate_run_owned_process_group(run_dir: Path, *, reason: str) -> dict[str, Any]:
    state = read_process_state(run_dir)
    if not state:
        return {"status": "not_found", "blocker": "codex process state is missing"}
    if not state.get("run_owned_process_group"):
        return {"status": "denied", "blocker": "refusing to kill a process group not marked as run-owned"}
    pgid = _int_or_none(state.get("pgid"))
    pid = _int_or_none(state.get("pid"))
    if not pgid or not pid:
        return {"status": "not_found", "blocker": "codex pid/pgid is missing"}
    if not _pid_alive(pid):
        finalize_process_state(run_dir, status="stale_lost_process", timeout_reason="process already gone")
        return {"status": "stale_lost_process", "killed": False, "blocker": "Codex process is already gone"}
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    except PermissionError as exc:
        try:
            os.kill(pid, signal.SIGTERM)
        except Exception:
            return {"status": "denied", "blocker": str(exc)}
    finalize_process_state(run_dir, status="cancelled", timeout_reason=reason)
    return {"status": "cancelled", "killed": True, "reason": reason}


def elapsed_seconds(started_at: Any) -> int:
    parsed = _parse_ts(started_at)
    if not parsed:
        return 0
    return max(0, int(time.time() - parsed))


def _write_state(run_dir: Path, payload: Mapping[str, Any]) -> None:
    path = process_state_path(run_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _parse_ts(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        return default
    return parsed if parsed > 0 else default


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except Exception:
        return None


def _now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
