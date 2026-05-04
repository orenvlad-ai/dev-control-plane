"""Run timeline helpers for local control-plane execution views."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence

TimelineLevel = Literal["info", "success", "warning", "error"]
TimelinePhase = Literal[
    "queued",
    "preparing",
    "codex",
    "command",
    "file_change",
    "verifier",
    "complete",
    "blocked",
    "failed",
]
TimelineSource = Literal["system", "codex", "verifier"]

MAX_DETAIL_CHARS = 500
MAX_EVENTS = 120


@dataclass(frozen=True)
class RunTimelineEvent:
    id: str
    timestamp: str
    level: TimelineLevel
    phase: TimelinePhase
    title: str
    detail: str | None = None
    source: TimelineSource = "system"
    raw_ref: str | None = None


def make_timeline_event(
    *,
    event_id: str,
    phase: TimelinePhase,
    title: str,
    level: TimelineLevel = "info",
    detail: str | None = None,
    source: TimelineSource = "system",
    raw_ref: str | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    return asdict(
        RunTimelineEvent(
            id=event_id,
            timestamp=timestamp or _now_utc(),
            level=level,
            phase=phase,
            title=_truncate(title, 160),
            detail=_truncate(detail, MAX_DETAIL_CHARS) if detail else None,
            source=source,
            raw_ref=raw_ref,
        )
    )


def append_timeline_event(
    events: Sequence[Mapping[str, Any]],
    *,
    phase: TimelinePhase,
    title: str,
    level: TimelineLevel = "info",
    detail: str | None = None,
    source: TimelineSource = "system",
    raw_ref: str | None = None,
    timestamp: str | None = None,
) -> list[dict[str, Any]]:
    normalized = [dict(event) for event in events if isinstance(event, Mapping)]
    if normalized:
        last = normalized[-1]
        if last.get("phase") == phase and last.get("title") == title and last.get("level") == level:
            return normalized
    event_id = f"event-{len(normalized) + 1:03d}"
    normalized.append(
        make_timeline_event(
            event_id=event_id,
            phase=phase,
            title=title,
            level=level,
            detail=detail,
            source=source,
            raw_ref=raw_ref,
            timestamp=timestamp,
        )
    )
    return normalized[-MAX_EVENTS:]


def build_run_timeline(job: Mapping[str, Any], run_record: Mapping[str, Any] | None = None) -> dict[str, Any]:
    events = [dict(event) for event in job.get("timeline_events", []) if isinstance(event, Mapping)]
    run_id = str(job.get("run_id") or "")
    if run_record:
        result = run_record.get("result", {})
        if isinstance(result, Mapping):
            events = _append_changed_file_events(events, result.get("changed_files", []))
            log_path = result.get("log_path")
            if log_path:
                events.extend(parse_codex_jsonl_log(Path(str(log_path))))
        verifier = run_record.get("verifier")
        if isinstance(verifier, Mapping):
            events.extend(verifier_timeline_events(verifier))
    events = _dedupe_events(events)
    if not events:
        events = append_timeline_event((), phase="queued", title="Ожидаем старт выполнения...", source="system")
    return {
        "run_id": run_id or None,
        "events": events[-MAX_EVENTS:],
        "updated_at": _now_utc(),
    }


def parse_codex_jsonl_log(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
        stripped = line.strip()
        if not stripped or not stripped.startswith("{"):
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            events = append_timeline_event(
                events,
                phase="codex",
                level="warning",
                title="Codex log содержит строку не-JSON, она пропущена.",
                detail=f"line {line_number}",
                source="codex",
                raw_ref=f"{path.name}:{line_number}",
            )
            continue
        if isinstance(payload, Mapping):
            mapped = _codex_payload_to_event(payload, raw_ref=f"{path.name}:{line_number}")
            if mapped:
                events = append_timeline_event(events, **mapped)
    return events


def verifier_timeline_events(verifier: Mapping[str, Any]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for check in verifier.get("check_results", []):
        if not isinstance(check, Mapping):
            continue
        status = str(check.get("status") or "")
        level: TimelineLevel = "success" if status == "passed" else ("warning" if status == "skipped" else "error")
        name = str(check.get("name") or "verifier_check")
        title = _verifier_check_title(name, status, str(check.get("command") or ""))
        detail = str(check.get("reason") or "") or None
        events = append_timeline_event(
            events,
            phase="verifier",
            level=level,
            title=title,
            detail=detail,
            source="verifier",
        )
    final_status = str(verifier.get("status") or "")
    if final_status == "passed":
        events = append_timeline_event(events, phase="complete", level="success", title="Готово: verifier passed.", source="verifier")
    elif final_status == "blocked":
        events = append_timeline_event(
            events,
            phase="blocked",
            level="error",
            title="Блокер: verifier остановил run.",
            detail=str(verifier.get("blocker_reason") or ""),
            source="verifier",
        )
    elif final_status == "failed":
        events = append_timeline_event(
            events,
            phase="failed",
            level="error",
            title="Ошибка: verifier failed.",
            detail=str(verifier.get("blocker_reason") or ""),
            source="verifier",
        )
    return events


def _codex_payload_to_event(payload: Mapping[str, Any], *, raw_ref: str) -> dict[str, Any] | None:
    event_type = str(payload.get("type") or payload.get("event") or payload.get("name") or "")
    status = str(payload.get("status") or payload.get("state") or "")
    detail = _message_from_payload(payload)

    if event_type in {"thread.started", "thread_started"}:
        return {"phase": "codex", "title": "Codex начал работу...", "source": "codex", "raw_ref": raw_ref}
    if event_type in {"turn.started", "turn_started"}:
        return {"phase": "codex", "title": "Codex анализирует задачу...", "source": "codex", "detail": detail, "raw_ref": raw_ref}
    if event_type in {"agent_message", "agent.message", "message"}:
        return {"phase": "codex", "title": "Codex анализирует задачу...", "source": "codex", "detail": detail, "raw_ref": raw_ref}
    if event_type in {"file_change", "file.changed", "patch"}:
        path = _first_text(payload, ("path", "file_path", "file", "target_path")) or "unknown"
        return {"phase": "file_change", "title": f"Codex изменил файл: {path}", "source": "codex", "detail": detail, "raw_ref": raw_ref}
    if event_type in {"command_execution", "command.execution", "exec"}:
        command = _command_from_payload(payload)
        if status in {"completed", "success", "succeeded", "passed"}:
            return {"phase": "command", "level": "success", "title": f"Проверка прошла: {command}", "source": "codex", "detail": detail, "raw_ref": raw_ref}
        if status in {"failed", "error"}:
            return {"phase": "command", "level": "error", "title": f"Проверка упала: {command}", "source": "codex", "detail": detail, "raw_ref": raw_ref}
        return {"phase": "command", "title": f"Codex запустил проверку: {command}", "source": "codex", "detail": detail, "raw_ref": raw_ref}
    if event_type in {"turn.completed", "turn_completed"}:
        return {"phase": "codex", "level": "success", "title": "Codex завершил ход работы.", "source": "codex", "detail": detail, "raw_ref": raw_ref}
    return None


def _append_changed_file_events(events: list[dict[str, Any]], changed_files: Any) -> list[dict[str, Any]]:
    if not isinstance(changed_files, list):
        return events
    for path in changed_files:
        events = append_timeline_event(
            events,
            phase="file_change",
            title=f"Codex изменил файл: {path}",
            source="system",
        )
    return events


def _verifier_check_title(name: str, status: str, command: str) -> str:
    if name == "git_diff_check":
        return "Проверка прошла: git diff --check" if status == "passed" else "Проверка упала: git diff --check"
    if name == "target_repo_unchanged":
        return "Original target repo не изменён." if status == "passed" else "Original target repo изменился."
    if name == "handoff_mandatory_blocks":
        return "Handoff contract проверен." if status == "passed" else "Ошибка формата отчёта Codex."
    if name == "forbidden_paths":
        return "Verifier проверил forbidden paths." if status == "passed" else "Verifier нашёл forbidden path."
    if name == "allowed_paths":
        return "Verifier проверил allowed paths." if status == "passed" else "Verifier нашёл изменения вне allowed paths."
    if name == "codex_cli_exit":
        return "Codex CLI exited 0." if status == "passed" else "Codex CLI завершился с ошибкой."
    if command:
        return f"Verifier проверил: {command}"
    return f"Verifier check: {name} ({status})"


def _dedupe_events(events: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str | None]] = set()
    for index, event in enumerate(events, start=1):
        key = (str(event.get("phase")), str(event.get("title")), event.get("raw_ref"))
        if key in seen:
            continue
        seen.add(key)
        normalized = dict(event)
        normalized["id"] = str(normalized.get("id") or f"event-{index:03d}")
        deduped.append(normalized)
    return deduped[-MAX_EVENTS:]


def _command_from_payload(payload: Mapping[str, Any]) -> str:
    command = payload.get("command") or payload.get("cmd") or payload.get("argv")
    if isinstance(command, list):
        return _truncate(" ".join(str(item) for item in command), 160)
    if command:
        return _truncate(str(command), 160)
    return "unknown command"


def _message_from_payload(payload: Mapping[str, Any]) -> str | None:
    value = _first_text(payload, ("message", "text", "content", "output", "summary", "detail"))
    return _truncate(value, MAX_DETAIL_CHARS) if value else None


def _first_text(payload: Mapping[str, Any], keys: Sequence[str]) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _truncate(value: str | None, limit: int) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
