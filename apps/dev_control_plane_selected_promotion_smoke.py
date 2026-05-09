"""Smoke-check deterministic selected Merge & Deploy planning."""

from __future__ import annotations

from pathlib import Path
import json
import os
import socket
import subprocess
import sys
import time
from tempfile import TemporaryDirectory
from typing import Any, Mapping
from urllib import request as urllib_request

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (SRC, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dev_control_plane.selected_promotion import SelectedPromotionCandidate, plan_selected_promotion  # noqa: E402

SERVER = ROOT / "apps" / "dev_control_plane_server.py"


def main() -> None:
    _planner_smoke()
    _server_selected_promotion_smoke()
    print("dev-control-plane-selected-promotion-smoke passed")


def _planner_smoke() -> None:
    docs = _candidate("task-docs", ["docs/architecture/01_control_plane_mvp.md"], finished_at="2026-05-09T08:30:00Z")
    ui = _candidate("task-ui", ["src/dev_control_plane/server.py"], finished_at="2026-05-09T08:31:00Z")
    broad = _candidate("task-broad", ["src/dev_control_plane/server.py", "src/dev_control_plane/mcp.py"], finished_at="2026-05-09T08:32:00Z")
    failed = _candidate("task-failed", [], lifecycle_status="failed")
    frozen = _candidate("task-frozen", ["README.md"], lifecycle_status="refresh_required", status="refresh_required")

    plan = plan_selected_promotion([broad, docs, ui, failed, frozen], target_id="wb-core")
    ordered_ids = [candidate.candidate_id for candidate in plan.ordered]
    if ordered_ids != ["task-docs", "task-ui"]:
        raise AssertionError(f"planner should order low-risk non-overlapping candidates deterministically: {plan.to_dict()}")
    if [candidate.candidate_id for candidate in plan.refresh_required] != ["task-frozen", "task-broad"]:
        raise AssertionError(f"frozen and same-file overlap candidates must require refresh: {plan.to_dict()}")
    if [candidate.candidate_id for candidate in plan.blocked] != ["task-failed"]:
        raise AssertionError(f"failed candidate must be blocked: {plan.to_dict()}")
    if "production lane remains serial" not in " ".join(plan.reasons):
        raise AssertionError(f"planner should document serial production semantics: {plan.to_dict()}")

    mismatch = _candidate("task-other-target", ["README.md"], target_id="other")
    mismatch_plan = plan_selected_promotion([mismatch], target_id="wb-core")
    if mismatch_plan.status != "blocked" or not mismatch_plan.blocked:
        raise AssertionError(f"target mismatch must fail closed: {mismatch_plan.to_dict()}")


def _candidate(
    candidate_id: str,
    files: list[str],
    *,
    target_id: str = "wb-core",
    lifecycle_status: str = "ready_for_promotion",
    status: str = "verifier_passed",
    finished_at: str = "2026-05-09T08:00:00Z",
) -> SelectedPromotionCandidate:
    return SelectedPromotionCandidate(
        candidate_id=candidate_id,
        selected_id=candidate_id,
        selection_type="task_id",
        target_id=target_id,
        source_kind="parallel_task",
        status=status,
        lifecycle_status=lifecycle_status,
        task_id=candidate_id,
        changed_files=tuple(files),
        finished_at=finished_at,
    )


def _server_selected_promotion_smoke() -> None:
    port = _free_port()
    with TemporaryDirectory(prefix="dev-control-plane-selected-promotion-") as tmp_raw:
        tmp = Path(tmp_raw)
        state_dir = tmp / "state"
        process = subprocess.Popen(
            [
                sys.executable,
                str(SERVER),
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--state-dir",
                str(state_dir),
            ],
            cwd=ROOT,
            env=_server_env(tmp),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            base_url = f"http://127.0.0.1:{port}"
            _wait_ready(base_url)
            first = _ready_task(base_url, "Исправить кнопку без заливки и проверить мониторинг", ["templates/button.html"])
            second = _ready_task(base_url, "Sticky группы таблицы в мониторинге", ["templates/sticky.html"])

            single = _post_json(
                base_url + "/api/parallel-selection/promote",
                {
                    "target_id": "wb-core",
                    "selected_ids": [first],
                    "selection_type": "task_id",
                    "confirm_merge_deploy": True,
                    "allow_auto_first_promotion": True,
                    "allow_real_production_promotion": True,
                },
            )
            if single.get("status") != "blocked" or single.get("group_created") is not False:
                raise AssertionError(f"single selected promotion must fail closed visibly, without group block: {single}")
            if "RunArtifactPromotionAdapter" not in str(single.get("blocker") or "") and "disabled" not in str(single.get("blocker") or ""):
                raise AssertionError(f"single selected promotion must return exact bridge blocker: {single}")

            live_after_single = _get_json(base_url + "/api/runs/live")
            first_card = next(run for run in live_after_single.get("runs", []) if run.get("run_id") == first)
            if first_card.get("status") != "blocked" or not first_card.get("blocker"):
                raise AssertionError(f"single selected blocker must be visible on the original card: {first_card}")
            title = str(first_card.get("task_title") or "")
            if title.startswith("pt-") or len(title.split()) > 5 or "кнопку" not in title:
                raise AssertionError(f"card title should be human-readable fallback, not task_id: {first_card}")

            group = _post_json(
                base_url + "/api/parallel-selection/promote",
                {
                    "target_id": "wb-core",
                    "selected_ids": [first, second],
                    "selection_type": "task_id",
                    "mode": "auto_order",
                    "confirm_merge_deploy": True,
                    "allow_auto_first_promotion": True,
                    "allow_real_production_promotion": True,
                },
            )
            group_id = str(group.get("group_id") or "")
            if group.get("status") != "blocked" or group.get("group_created") is not True or not group_id:
                raise AssertionError(f"group selected promotion must create blocked inspectable group when bridge disabled: {group}")
            fetched_group = _get_json(base_url + f"/api/parallel-promotion-groups/{group_id}")
            if fetched_group.get("group", {}).get("status") != "blocked":
                raise AssertionError(f"group status must be readable from backend storage: {fetched_group}")
            group_detail = _get_json(base_url + f"/api/runs/{group_id}/live")
            if group_detail.get("status") != "ok" or group_detail.get("report", {}).get("promotion_group", {}).get("status") != "blocked":
                raise AssertionError(f"group should be inspectable as monitor detail: {group_detail}")
            group_tail = _get_json(base_url + f"/api/runs/{group_id}/log-tail")
            if "RunArtifactPromotionAdapter" not in str(group_tail.get("plain_text") or ""):
                raise AssertionError(f"group terminal tail should explain blocker: {group_tail}")
            mcp_group_status = _mcp(base_url, "tools/call", {"name": "get_run_status", "arguments": {"run_id": group_id}})
            structured = mcp_group_status.get("structuredContent") or {}
            if structured.get("status") != "blocked" or structured.get("run_type") != "group_promotion":
                raise AssertionError(f"MCP get_run_status should understand promotion groups: {mcp_group_status}")

            cancelled = _post_json(base_url + f"/api/runs/{group_id}/cancel", {"reason": "selected promotion smoke cancel"})
            if cancelled.get("status") != "cancelled":
                raise AssertionError(f"Stop/cancel must update promotion group state: {cancelled}")
            cancelled_group = _get_json(base_url + f"/api/parallel-promotion-groups/{group_id}")
            if cancelled_group.get("group", {}).get("status") != "cancelled":
                raise AssertionError(f"cancelled group must stay cancelled in backend: {cancelled_group}")

            ghost_id = "promotion-group-20260509T135513Z-smokeghost"
            _write_groups(
                state_dir,
                {
                    ghost_id: {
                        "group_id": ghost_id,
                        "target_id": "wb-core",
                        "selected_ids": [first, second],
                        "selection_type": "task_id",
                        "mode": "auto_order",
                        "status": "planned",
                        "current_step": "plan_ready",
                        "created_at": "2000-01-01T00:00:00Z",
                        "updated_at": "2000-01-01T00:00:00Z",
                        "planned_order": [first, second],
                        "per_task_status": {first: "planned", second: "planned"},
                    }
                },
            )
            live_after_ghost = _get_json(base_url + "/api/runs/live")
            ghost = next(run for run in live_after_ghost.get("runs", []) if run.get("run_id") == ghost_id)
            if ghost.get("active") is True or ghost.get("status") not in {"expired", "blocked"}:
                raise AssertionError(f"stale ghost group must not remain active/blinking: {ghost}")

            page = _get_text(base_url + "/runs/live")
            for token in ("task-title", "shortRunTitle", "observeRunStatusChanges", "notificationCount", "🔔", "#timelineList li", "lastPromptText"):
                if token not in page:
                    raise AssertionError(f"monitor page must include selected-promotion UI hardening token: {token}")
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def _ready_task(base_url: str, text: str, files: list[str]) -> str:
    submitted = _post_json(base_url + "/api/parallel-tasks", {"target_id": "wb-core", "task_text": text, "source": "smoke"})
    task_id = str(submitted.get("task_id") or "")
    if not task_id:
        raise AssertionError(f"submit must return task_id: {submitted}")
    _post_json(base_url + f"/api/parallel-tasks/{task_id}/start-execution", {"starter_mode": "fake"})
    reconciled = _post_json(
        base_url + f"/api/parallel-tasks/{task_id}/reconcile",
        {
            "run_status": "passed",
            "verifier_status": "passed",
            "changed_files": files,
            "verifier_summary": {"forbidden_paths_clean": True, "source": "selected-promotion-smoke"},
        },
    )
    if reconciled.get("status") != "verifier_passed":
        raise AssertionError(f"task must become verifier_passed: {reconciled}")
    return task_id


def _mcp(base_url: str, method: str, params: Mapping[str, Any]) -> dict[str, Any]:
    body = json.dumps({"jsonrpc": "2.0", "id": f"smoke-{time.time_ns()}", "method": method, "params": params}).encode("utf-8")
    req = urllib_request.Request(base_url + "/mcp", data=body, method="POST", headers={"Content-Type": "application/json"})
    with urllib_request.urlopen(req, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if "error" in payload:
        raise AssertionError(f"MCP error for {method}: {payload}")
    return payload.get("result") or {}


def _get_text(url: str) -> str:
    with urllib_request.urlopen(url, timeout=10) as response:
        return response.read().decode("utf-8")


def _get_json(url: str) -> dict[str, Any]:
    return json.loads(_get_text(url))


def _post_json(url: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    body = json.dumps(dict(payload)).encode("utf-8")
    request = urllib_request.Request(url, data=body, method="POST", headers={"Content-Type": "application/json"})
    with urllib_request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _write_groups(state_dir: Path, groups: Mapping[str, Mapping[str, Any]]) -> None:
    path = state_dir / "collections" / "parallel_promotion_groups.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if not isinstance(existing, dict):
        existing = {}
    existing.update({key: dict(value) for key, value in groups.items()})
    path.write_text(json.dumps(existing, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _wait_ready(base_url: str) -> None:
    deadline = time.time() + 10
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            _get_json(base_url + "/api/state")
            return
        except Exception as exc:
            last_error = exc
            time.sleep(0.1)
    raise AssertionError(f"server did not become ready: {last_error}")


def _server_env(tmp: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("OPENAI_API_KEY", None)
    env.pop("DEV_CONTROL_PLANE_PARALLEL_PRODUCTION_BRIDGE_MODE", None)
    env["DEV_CONTROL_PLANE_SECRET_HOME"] = str(tmp / "secrets")
    return env


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


if __name__ == "__main__":
    main()
