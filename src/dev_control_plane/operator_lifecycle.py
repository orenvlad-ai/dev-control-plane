"""Operator-facing lifecycle semantics for DevControl run/task cards."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Mapping


@dataclass(frozen=True)
class OperatorLifecycle:
    status: str
    label: str
    tone: str
    selectable: bool = False
    selection_reason: str | None = None
    time_summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def operator_lifecycle_for(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Map raw control-plane fields to stable operator lifecycle semantics."""
    raw_status = _lower(payload.get("operator_lifecycle_status") or payload.get("effective_status") or payload.get("status"))
    stage = _lower(payload.get("current_stage"))
    mode = _lower(payload.get("execution_mode"))
    deploy_status = _lower(payload.get("deploy_status"))
    verifier = _lower(payload.get("verifier_status"))
    blocker = str(payload.get("blocker") or "").strip()
    refresh_required = bool(payload.get("refresh_required")) or raw_status in {
        "refresh_required",
        "frozen_base_stale",
        "conflict_detected",
        "blocked_by_conflict",
        "needs_rework",
    }
    production_report = payload.get("production_lane_report") if isinstance(payload.get("production_lane_report"), Mapping) else {}
    report_status = _lower(production_report.get("status") or production_report.get("deploy_status") or production_report.get("post_deploy_status"))

    if raw_status in {"partially_deployed", "partial_group_blocked", "partial_group_complete_with_blockers"}:
        lifecycle = OperatorLifecycle(
            status="partially_deployed",
            label="Задеплоено частично",
            tone="ready",
            selectable=False,
            selection_reason=str(payload.get("blocker") or "часть задач вынесена в отдельную выкладку"),
            time_summary=_time_summary(payload),
        )
    elif raw_status == "ready_for_separate_deploy":
        lifecycle = OperatorLifecycle(
            status="ready_for_separate_deploy",
            label="Готово к отдельной выкладке",
            tone="ready",
            selectable=True,
            selection_reason=str(payload.get("separate_deploy_reason") or ""),
            time_summary=_time_summary(payload),
        )
    elif raw_status in {"conflict_detected", "blocked_by_conflict"}:
        lifecycle = OperatorLifecycle(
            status="refresh_required",
            label="Конфликт после выкладки",
            tone="refresh",
            selectable=False,
            selection_reason=str(payload.get("blocker") or "candidate must be refreshed against current main"),
            time_summary=_time_summary(payload),
        )
    elif raw_status == "needs_rework":
        lifecycle = OperatorLifecycle(
            status="refresh_required",
            label="Требует доработки",
            tone="refresh",
            selectable=False,
            selection_reason=str(payload.get("blocker") or "candidate needs rework before promotion"),
            time_summary=_time_summary(payload),
        )
    elif refresh_required:
        lifecycle = OperatorLifecycle(
            status="refresh_required",
            label="Нужен refresh",
            tone="refresh",
            selectable=False,
            selection_reason="candidate is frozen/stale and requires refresh/reverify",
            time_summary=_time_summary(payload),
        )
    elif raw_status in {"blocked_by_operator", "cancelled"}:
        lifecycle = OperatorLifecycle(
            status="blocked",
            label="Остановлено",
            tone="bad",
            selectable=False,
            selection_reason=blocker or "operator stopped this item",
            time_summary=_time_summary(payload),
        )
    elif raw_status in {"blocked", "denied", "failed", "error"} or blocker:
        lifecycle = OperatorLifecycle(
            status="blocked" if raw_status in {"blocked", "denied"} or blocker else "failed",
            label="Блокер" if raw_status in {"blocked", "denied"} or blocker else "Ошибка",
            tone="bad",
            selectable=False,
            selection_reason=blocker or f"status is {raw_status}",
            time_summary=_time_summary(payload),
        )
    elif _production_complete(raw_status, deploy_status, report_status, production_report):
        lifecycle = OperatorLifecycle(
            status="production_complete",
            label="В проде",
            tone="ok",
            selectable=False,
            selection_reason="already production complete",
            time_summary=_time_summary(payload),
        )
    elif raw_status in {"production_lane_running", "auto_promoting_first"} or "deploy" in stage or "merge" in stage:
        lifecycle = OperatorLifecycle(
            status="promotion_running",
            label="Merge & Deploy",
            tone="running",
            selectable=False,
            selection_reason="promotion is already running",
            time_summary=_time_summary(payload),
        )
    elif _ready_for_promotion(raw_status, verifier, mode, deploy_status):
        lifecycle = OperatorLifecycle(
            status="ready_for_promotion",
            label="Готово к выкладке",
            tone="ready",
            selectable=True,
            time_summary=_time_summary(payload),
        )
    elif _running(raw_status, stage):
        lifecycle = OperatorLifecycle(
            status="running",
            label="В работе",
            tone="running",
            selectable=False,
            selection_reason="run is still active",
            time_summary=_time_summary(payload),
        )
    elif raw_status in {"submitted", "queued", "waiting", "waiting_for_target_lock", "promotion_queued"}:
        lifecycle = OperatorLifecycle(
            status="waiting",
            label="Ожидает",
            tone="neutral",
            selectable=False,
            selection_reason="not verifier-passed yet",
            time_summary=_time_summary(payload),
        )
    else:
        lifecycle = OperatorLifecycle(
            status="waiting",
            label="Ожидает",
            tone="neutral",
            selectable=False,
            selection_reason=f"status is {raw_status or 'unknown'}",
            time_summary=_time_summary(payload),
        )
    return lifecycle.to_dict()


def decorate_operator_lifecycle(payload: dict[str, Any]) -> dict[str, Any]:
    lifecycle = operator_lifecycle_for(payload)
    payload["operator_lifecycle"] = lifecycle
    payload["operator_lifecycle_status"] = lifecycle["status"]
    payload["operator_lifecycle_label"] = lifecycle["label"]
    payload["operator_lifecycle_tone"] = lifecycle["tone"]
    payload["promotion_selectable"] = lifecycle["selectable"]
    payload["promotion_selection_reason"] = lifecycle.get("selection_reason")
    payload["operator_time_summary"] = lifecycle.get("time_summary") or ""
    return payload


def _ready_for_promotion(raw_status: str, verifier: str, mode: str, deploy_status: str) -> bool:
    if deploy_status and deploy_status not in {"none", "n/a", "blocked"}:
        return False
    if raw_status in {"verifier_passed", "promotion_queued", "passed"}:
        return True
    if verifier in {"passed", "ok", "success", "verifier_passed"} and "production" not in mode:
        return True
    return False


def _production_complete(raw_status: str, deploy_status: str, report_status: str, report: Mapping[str, Any]) -> bool:
    if raw_status in {"production_complete", "deploy_passed", "post_deploy_passed"}:
        return True
    if raw_status in {"completed", "passed"} and deploy_status in {"passed", "deploy_passed", "post_deploy_passed"}:
        return True
    if report_status in {"passed", "deploy_passed", "post_deploy_passed", "production_complete"}:
        return True
    return bool(report.get("merge_commit") and report.get("public_verify_status") in {"passed", "ok", "success"})


def _running(raw_status: str, stage: str) -> bool:
    if raw_status in {"running", "running_codex", "managed_run_running", "preparing", "queued"}:
        return True
    return any(token in stage for token in ("running", "codex", "verifier", "preparing", "queued"))


def _time_summary(payload: Mapping[str, Any]) -> str:
    started = _first(payload, "started_at", "codex_started_at", "created_at", "submitted_at")
    finished = _first(payload, "finished_at", "completed_at", "verifier_passed_at", "updated_at")
    created = _first(payload, "created_at", "submitted_at")
    if _running(_lower(payload.get("effective_status") or payload.get("status")), _lower(payload.get("current_stage"))):
        elapsed = _duration_seconds(started, _now())
        return f"старт {_clock(started)} · идёт {_compact_duration(elapsed)}" if started else "идёт"
    if started and finished and started != finished:
        return f"старт {_clock(started)} · финиш {_clock(finished)} · {_compact_duration(_duration_seconds(started, finished))}"
    if created:
        return f"создано {_clock(created)} · ожидает"
    return ""


def _first(payload: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = str(payload.get(key) or "").strip()
        if value:
            return value
    return ""


def _duration_seconds(start: str, end: str) -> int:
    parsed_start = _parse_time(start)
    parsed_end = _parse_time(end)
    if not parsed_start or not parsed_end:
        return 0
    return max(0, int((parsed_end - parsed_start).total_seconds()))


def _clock(value: str) -> str:
    parsed = _parse_time(value)
    if not parsed:
        return str(value or "")[:16]
    return parsed.strftime("%H:%M")


def _compact_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}с"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}м"
    return f"{minutes // 60}ч {minutes % 60}м"


def _parse_time(value: str) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _lower(value: Any) -> str:
    return str(value or "").strip().lower()
