"""Read-only live monitor helpers for DevControl runs.

The browser-facing APIs must never stream raw logs. This module writes and
serves a sanitized terminal view that keeps safe ANSI SGR styling while
dropping terminal controls that can mutate browser/clipboard/title state.
"""

from __future__ import annotations

from collections.abc import Sequence as SequenceABC
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

MAX_LIVE_LOG_BYTES = 96_000
MAX_LIVE_TIMELINE_EVENTS = 240
LIVE_TIMELINE_NAME = "timeline.jsonl"
LIVE_TERMINAL_NAME = "terminal.log"

TERMINAL_STATUSES = {
    "completed",
    "completed_dry_run",
    "abandoned_by_operator",
    "archived",
    "blocked_by_conflict",
    "blocked_by_operator",
    "blocked",
    "cancelled",
    "conflict_detected",
    "decision_only",
    "denied",
    "expired",
    "failed",
    "needs_rework",
    "needs_verifier_after_control_error",
    "partially_deployed",
    "partial_group_blocked",
    "partial_group_complete_with_blockers",
    "passed",
    "ready_for_separate_deploy",
    "refresh_required",
    "stale_lost_process",
    "stale_timeout",
    "waiting_for_target_lock",
}

SECRET_PATTERNS = (
    re.compile(r"Authorization\s*:\s*Bearer\s+\S+", re.I),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{16,}", re.I),
    re.compile(r"\b(?:Cookie|Set-Cookie)\s*:\s*[^\r\n]+", re.I),
    re.compile(r"\b(?:X-Api-Key|api[_-]?key|OPENAI_API_KEY)\s*[:=]\s*[^\s,;]+", re.I),
    re.compile(r"\b[A-Z0-9_]*(?:SECRET|TOKEN|PASSWORD|SESSION|COOKIE)[A-Z0-9_]*\s*=\s*[^\s,;]+", re.I),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY"),
    re.compile(r"/opt/dev-control-plane-runtime/(?:secrets|\\.codex)/[^\s:]+"),
    re.compile(r"/opt/dev-control-plane-runtime/\\.codex/[^\s:]+"),
    re.compile(r"(?i)(identity file\s+)[^\s]+"),
    re.compile(r"~/.dev-control-plane/secrets\.json"),
    re.compile(r"/Users/[^/\s]+/\\.codex/[^\s:]+"),
)


def live_url(base_url: str | None, run_id: str | None = None) -> str:
    base = _base_url(base_url)
    if run_id:
        return f"{base}/runs/{run_id}/watch"
    return f"{base}/runs/live"


def append_live_event(
    run_dir: Path,
    *,
    stage: str,
    title: str,
    status: str | None = None,
    level: str = "info",
    detail: str | None = None,
    source: str = "system",
    run_id: str | None = None,
    target_id: str | None = None,
) -> dict[str, Any]:
    event = {
        "id": f"event-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}",
        "timestamp": _now_utc(),
        "stage": _safe_text(stage, 80),
        "phase": _safe_text(stage, 80),
        "title": _safe_text(title, 180),
        "status": _safe_text(status or "", 80) or None,
        "level": level if level in {"info", "success", "warning", "error"} else "info",
        "detail": _safe_text(detail or "", 700) or None,
        "source": _safe_text(source, 80),
        "run_id": _safe_text(run_id or "", 140) or None,
        "target_id": _safe_text(target_id or "", 140) or None,
    }
    path = timeline_path(run_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
    return event


def append_terminal_output(run_dir: Path, text: str) -> None:
    sanitized = sanitize_terminal_text(terminalize_output(text))
    if not sanitized:
        return
    path = terminal_log_path(run_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(sanitized)


def timeline_path(run_dir: Path) -> Path:
    return Path(run_dir).resolve() / "logs" / LIVE_TIMELINE_NAME


def terminal_log_path(run_dir: Path) -> Path:
    return Path(run_dir).resolve() / "logs" / LIVE_TERMINAL_NAME


def read_live_timeline(run_dir: Path, *, fallback_events: Sequence[Mapping[str, Any]] = ()) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    path = timeline_path(run_dir)
    if path.exists():
        for line in _tail_text(path, max_bytes=128_000).splitlines():
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, Mapping):
                events.append(_sanitize_event(payload))
    for event in fallback_events:
        if isinstance(event, Mapping):
            events.append(_sanitize_event(event))
    return _dedupe_events(events)[-MAX_LIVE_TIMELINE_EVENTS:]


def read_terminal_tail(run_dir: Path, *, max_bytes: int = MAX_LIVE_LOG_BYTES, offset: int | None = None) -> dict[str, Any]:
    run_dir = Path(run_dir).resolve()
    source_path = _first_existing(
        (
            terminal_log_path(run_dir),
            run_dir / "logs" / "codex.log",
            run_dir / "logs" / "executor.log",
        )
    )
    if source_path is None:
        return {
            "status": "missing",
            "ansi_text": "",
            "plain_text": "",
            "bytes": 0,
            "offset": 0,
            "next_offset": 0,
            "truncated": False,
            "source": "none",
            "append": offset is not None,
        }
    size = source_path.stat().st_size
    start = _normalized_offset(offset, size, max_bytes)
    raw = _read_text_window(source_path, start=start, max_bytes=max_bytes)
    text = raw if source_path.name == LIVE_TERMINAL_NAME else terminalize_output(raw)
    sanitized = sanitize_terminal_text(text)
    return {
        "status": "ok",
        "ansi_text": sanitized,
        "plain_text": strip_sgr(apply_carriage_returns(sanitized)),
        "bytes": size,
        "offset": start,
        "next_offset": size,
        "truncated": start > 0,
        "source": source_path.name,
        "append": offset is not None,
    }


def sanitize_terminal_text(text: str) -> str:
    stripped = _strip_unsafe_ansi(str(text or ""))
    redacted = _redact_secrets(stripped)
    return _strip_unsafe_ansi(redacted)


def terminalize_output(text: str) -> str:
    """Convert common Codex JSONL/envelope output into terminal-facing text."""
    raw = str(text or "")
    if not raw:
        return ""
    pieces: list[str] = []
    for line in raw.splitlines(keepends=True):
        terminal_line = _terminalize_line(line)
        if terminal_line:
            pieces.append(terminal_line)
    return "".join(pieces)


def strip_sgr(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", str(text or ""))


def apply_carriage_returns(text: str) -> str:
    result_lines: list[str] = []
    for raw_line in str(text or "").split("\n"):
        if "\r" not in raw_line:
            result_lines.append(raw_line)
            continue
        current = ""
        for part in raw_line.split("\r"):
            current = _overlay_line(current, part)
        result_lines.append(current)
    return "\n".join(result_lines)


def is_terminal_status(status: str | None) -> bool:
    return str(status or "") in TERMINAL_STATUSES


def _strip_unsafe_ansi(text: str) -> str:
    output: list[str] = []
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char == "\x1b":
            kept, consumed = _consume_escape(text, index)
            if kept:
                output.append(kept)
            index += max(consumed, 1)
            continue
        code = ord(char)
        if char in {"\n", "\r", "\t"}:
            output.append(char)
        elif code < 32 or 0x80 <= code <= 0x9F:
            pass
        else:
            output.append(char)
        index += 1
    return "".join(output)


def _consume_escape(text: str, index: int) -> tuple[str, int]:
    if index + 1 >= len(text):
        return "", 1
    kind = text[index + 1]
    if kind == "[":
        end = index + 2
        while end < len(text) and end - index <= 96:
            final = text[end]
            if "@" <= final <= "~":
                sequence = text[index : end + 1]
                if final == "m" and _safe_sgr_params(sequence[2:-1]):
                    return sequence, len(sequence)
                return "", len(sequence)
            end += 1
        return "", min(len(text) - index, 96)
    if kind == "]":
        return "", _consume_until_st(text, index + 2)
    if kind in {"P", "_", "^"}:
        return "", _consume_until_st(text, index + 2)
    return "", 2


def _consume_until_st(text: str, start: int) -> int:
    cursor = start
    while cursor < len(text):
        if text[cursor] == "\x07":
            return cursor - start + 3
        if text[cursor] == "\x1b" and cursor + 1 < len(text) and text[cursor + 1] == "\\":
            return cursor - start + 4
        cursor += 1
    return len(text) - start + 2


def _safe_sgr_params(params: str) -> bool:
    if len(params) > 80:
        return False
    if params == "":
        return True
    return bool(re.fullmatch(r"[0-9;]*", params))


def _redact_secrets(text: str) -> str:
    result = text
    for pattern in SECRET_PATTERNS:
        result = pattern.sub("[redacted]", result)
    lines: list[str] = []
    suppress_traceback = False
    for line in result.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith("Traceback (most recent call last):"):
            lines.append("[redacted traceback]\n")
            suppress_traceback = True
            continue
        if suppress_traceback and (stripped.startswith('File "') or stripped.startswith("^") or stripped.startswith("raise ")):
            continue
        if suppress_traceback and stripped:
            suppress_traceback = False
        lines.append(line)
    return "".join(lines)


def _tail_text(path: Path, *, max_bytes: int) -> str:
    size = path.stat().st_size
    with path.open("rb") as handle:
        if size > max_bytes:
            handle.seek(max(0, size - max_bytes))
        raw = handle.read(max_bytes)
    return raw.decode("utf-8", errors="replace")


def _read_text_window(path: Path, *, start: int, max_bytes: int) -> str:
    with path.open("rb") as handle:
        handle.seek(max(0, start))
        raw = handle.read(max_bytes)
    return raw.decode("utf-8", errors="replace")


def _normalized_offset(offset: int | None, size: int, max_bytes: int) -> int:
    if offset is None:
        return max(0, size - max_bytes) if size > max_bytes else 0
    safe = max(0, int(offset))
    if safe > size:
        return max(0, size - max_bytes) if size > max_bytes else 0
    if size - safe > max_bytes:
        return max(0, size - max_bytes)
    return safe


def _first_existing(paths: Sequence[Path]) -> Path | None:
    for path in paths:
        if path.exists() and path.is_file():
            return path
    return None


def _sanitize_event(event: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": _safe_text(event.get("id") or "", 140),
        "timestamp": _safe_text(event.get("timestamp") or "", 80),
        "stage": _safe_text(event.get("stage") or event.get("phase") or "", 80),
        "phase": _safe_text(event.get("phase") or event.get("stage") or "", 80),
        "title": _safe_text(event.get("title") or "", 180),
        "status": _safe_text(event.get("status") or "", 80) or None,
        "level": str(event.get("level") or "info") if str(event.get("level") or "info") in {"info", "success", "warning", "error"} else "info",
        "detail": _safe_text(event.get("detail") or "", 700) or None,
        "source": _safe_text(event.get("source") or "", 80) or "system",
        "run_id": _safe_text(event.get("run_id") or "", 140) or None,
        "target_id": _safe_text(event.get("target_id") or "", 140) or None,
    }


def _dedupe_events(events: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for index, event in enumerate(events, start=1):
        normalized = _sanitize_event(event)
        key = (str(normalized.get("timestamp")), str(normalized.get("stage")), str(normalized.get("title")))
        if key in seen:
            continue
        seen.add(key)
        if not normalized.get("id"):
            normalized["id"] = f"event-{index:03d}"
        result.append(normalized)
    return result


def _overlay_line(current: str, update: str) -> str:
    plain_current = current
    if len(update) >= len(plain_current):
        return update
    return update + plain_current[len(update) :]


def _safe_text(value: Any, limit: int) -> str:
    text = strip_sgr(sanitize_terminal_text(str(value or ""))).replace("\r", " ").replace("\n", " ").strip()
    return text if len(text) <= limit else text[: limit - 15] + "...[truncated]"


def _base_url(base_url: str | None) -> str:
    raw = str(base_url or "").strip().rstrip("/")
    return raw or "https://devcontrol.pro"


def _now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _terminalize_line(line: str) -> str:
    ending = "\n" if line.endswith("\n") else ""
    body = line[:-1] if ending else line
    if not body.strip():
        return line
    decoded = _decode_json_string(body.strip())
    if decoded is not None:
        return decoded + ending
    payload = _decode_json_object(body.strip())
    if payload is None:
        return line
    rendered = _render_codex_event(payload)
    if not rendered:
        return ""
    return rendered if rendered.endswith(("\n", "\r")) else rendered + ending


def _decode_json_object(text: str) -> Mapping[str, Any] | None:
    if not (text.startswith("{") and text.endswith("}")):
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, Mapping) else None


def _decode_json_string(text: str) -> str | None:
    if len(text) < 2 or text[0] not in {"'", '"'}:
        return None
    try:
        decoded = json.loads(text)
    except json.JSONDecodeError:
        return None
    return decoded if isinstance(decoded, str) else None


def _render_codex_event(payload: Mapping[str, Any]) -> str:
    event_type = str(payload.get("type") or payload.get("event") or payload.get("name") or "").strip()
    lowered = event_type.lower()
    if lowered in {"item.started", "item_started"}:
        return _render_codex_item_event(payload, started=True)
    if lowered in {"item.completed", "item_completed"}:
        return _render_codex_item_event(payload, started=False)
    if lowered in {"command_execution", "command.execution", "exec"}:
        return _render_command_execution_event(payload)
    if lowered in {
        "turn.completed",
        "response.completed",
        "response.done",
        "token_usage",
        "usage",
        "metrics",
        "session.config",
    }:
        return ""
    text = _extract_event_text(payload)
    if text:
        prefix = _event_prefix(lowered, payload)
        suffix = "\x1b[0m" if prefix.startswith("\x1b[") and not text.endswith("\x1b[0m") else ""
        return f"{prefix}{text}{suffix}"
    if any(marker in lowered for marker in ("error", "failed", "blocked")):
        return f"\x1b[31m[codex] {event_type or 'error'}\x1b[0m"
    if any(marker in lowered for marker in ("started", "running", "command")):
        return f"\x1b[36m[codex] {event_type}\x1b[0m"
    if any(marker in lowered for marker in ("completed", "finished", "passed")):
        return f"\x1b[32m[codex] {event_type}\x1b[0m"
    if event_type:
        return f"\x1b[2m[codex] {event_type}\x1b[0m"
    return ""


def _render_codex_item_event(payload: Mapping[str, Any], *, started: bool) -> str:
    item = payload.get("item") if isinstance(payload.get("item"), Mapping) else payload
    item_type = str(item.get("type") or item.get("item_type") or payload.get("item_type") or "item")
    item_id = str(item.get("id") or payload.get("item_id") or "")
    timestamp = str(payload.get("timestamp") or payload.get("created_at") or "")
    command = _command_from_event(item) or _command_from_event(payload)
    status = str(payload.get("status") or item.get("status") or ("started" if started else "completed"))
    exit_code = payload.get("exit_code", item.get("exit_code"))
    duration = payload.get("duration_ms", item.get("duration_ms", payload.get("duration_seconds", item.get("duration_seconds"))))
    header_color = "\x1b[36m" if started else ("\x1b[32m" if status in {"completed", "success", "passed"} or exit_code in {0, "0"} else "\x1b[31m")
    parts = [f"{header_color}[codex] {timestamp + ' ' if timestamp else ''}{event_type_label(started)} {item_type}"]
    if item_id:
        parts.append(f" id={item_id}")
    if status:
        parts.append(f" status={status}")
    if exit_code is not None:
        parts.append(f" exit_code={exit_code}")
    if duration is not None:
        parts.append(f" duration={duration}")
    parts.append("\x1b[0m")
    if command:
        parts.append(f"\n\x1b[36m$ {command}\x1b[0m")
    output = _brief_event_output(payload) or _brief_event_output(item)
    if output:
        parts.append("\n" + output)
    return "".join(parts)


def _render_command_execution_event(payload: Mapping[str, Any]) -> str:
    command = _command_from_event(payload) or "command"
    status = str(payload.get("status") or payload.get("state") or "")
    exit_code = payload.get("exit_code", payload.get("returncode"))
    duration = payload.get("duration_ms", payload.get("duration_seconds"))
    color = "\x1b[32m" if status in {"completed", "success", "passed"} or exit_code in {0, "0"} else ("\x1b[31m" if status in {"failed", "error"} or (exit_code not in {None, 0, "0"}) else "\x1b[36m")
    header = f"{color}[codex] command_execution status={status or 'running'}"
    if exit_code is not None:
        header += f" exit_code={exit_code}"
    if duration is not None:
        header += f" duration={duration}"
    output = _brief_event_output(payload)
    return f"{header}\x1b[0m\n\x1b[36m$ {command}\x1b[0m" + (f"\n{output}" if output else "")


def event_type_label(started: bool) -> str:
    return "started" if started else "completed"


def _command_from_event(payload: Mapping[str, Any]) -> str:
    command = payload.get("command") or payload.get("cmd") or payload.get("argv")
    if isinstance(command, SequenceABC) and not isinstance(command, (str, bytes, bytearray)):
        return " ".join(str(item) for item in command)
    if command:
        return str(command)
    args = payload.get("args")
    if isinstance(args, SequenceABC) and not isinstance(args, (str, bytes, bytearray)):
        return " ".join(str(item) for item in args)
    return ""


def _brief_event_output(payload: Mapping[str, Any]) -> str:
    output = _extract_event_text(
        {
            "stdout": payload.get("stdout") or payload.get("aggregated_output"),
            "stderr": payload.get("stderr"),
            "output": payload.get("output"),
        }
    )
    output = strip_sgr(sanitize_terminal_text(output)).strip()
    if not output:
        return ""
    if len(output) > 2000:
        return output[:2000] + "\n...[truncated]"
    return output


def _event_prefix(event_type: str, payload: Mapping[str, Any]) -> str:
    if any(marker in event_type for marker in ("error", "failed", "blocked")):
        return "\x1b[31m"
    if any(marker in event_type for marker in ("warning", "warn")):
        return "\x1b[33m"
    if any(marker in event_type for marker in ("assistant", "message", "delta", "output")):
        return ""
    if "command" in event_type or payload.get("command"):
        return "\x1b[36m$ "
    return ""


def _extract_event_text(value: Any) -> str:
    if isinstance(value, str):
        return _decode_escaped_text(value)
    if isinstance(value, SequenceABC) and not isinstance(value, (str, bytes, bytearray)):
        parts = [_extract_event_text(item) for item in value]
        return "".join(part for part in parts if part)
    if not isinstance(value, Mapping):
        return ""
    for key in (
        "message",
        "content",
        "text",
        "delta",
        "output",
        "stdout",
        "stderr",
        "summary",
        "result",
        "handoff",
    ):
        if key in value:
            extracted = _extract_event_text(value.get(key))
            if extracted:
                return extracted
    if value.get("command"):
        return str(value.get("command"))
    return ""


def _decode_escaped_text(text: str) -> str:
    return str(text or "").replace("\\n", "\n").replace("\\r", "\r").replace("\\t", "\t")
