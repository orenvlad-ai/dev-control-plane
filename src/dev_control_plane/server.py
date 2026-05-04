"""Local-only development control-plane MVP prototype server.

This server is intentionally a repo-only/local prototype. It does not register
production routes, does not call OpenAI unless explicitly selected, and does
not run Codex.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
from typing import Any, Mapping
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
for path in (SRC, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dev_control_plane.contracts import (  # noqa: E402
    ControlPlaneValidationError,
    build_codex_prompt,
    freeze_task_spec,
    sprint_steps_from_task_spec_mapping,
    task_spec_from_mapping,
    task_spec_to_dict,
    validate_sprint_step,
    validate_task_spec,
)
from dev_control_plane.ai import (  # noqa: E402
    CuratorDraftRequest,
    curator_draft_result_to_dict,
    draft_task_spec,
)
from dev_control_plane.execution import (  # noqa: E402
    ControlPlaneExecutionError,
    cleanup_run_worktree,
    load_run_record,
    prepare_run,
    run_result_to_dict,
    run_step,
    verifier_result_to_dict,
    verify_run,
)
from dev_control_plane.target_projects import (  # noqa: E402
    build_target_context_snapshot,
    build_target_context_summary,
    load_target_project_configs,
    merge_target_defaults_into_task_spec_payload,
    target_context_summary_to_dict,
    target_project_config_to_dict,
    target_project_defaults,
    target_project_validation_result_to_dict,
    validate_target_project,
)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_STATE_DIR = Path("/tmp/development-control-plane-state")
EXAMPLE_TASK_SPEC = ROOT / "artifacts" / "input" / "example_task_spec.json"
TARGET_CONFIG_DIR = ROOT / "configs" / "target_projects"
LOCAL_ONLY_NOTICE = "Local-only Development Control Plane prototype: optional OpenAI intake, UI fake-only execution, no live/deploy/public route."

EXPOSED_ROUTES = (
    "GET /",
    "GET /api/state",
    "GET /api/example-task-spec",
    "GET /api/target-projects",
    "GET /api/target-projects/{id}",
    "GET /api/target-projects/{id}/summary",
    "GET /api/targets",
    "GET /api/targets/{id}/summary",
    "GET /api/task-specs/{id}",
    "GET /api/prompts/{prompt_id}",
    "GET /api/runs/{id}",
    "GET /api/runs/{id}/summary",
    "POST /api/discussions",
    "POST /api/discussions/{id}/messages",
    "POST /api/discussions/{id}/draft-task-spec",
    "POST /api/task-specs",
    "POST /api/task-specs/{id}/freeze",
    "POST /api/task-specs/{id}/generate-prompt",
    "POST /api/task-specs/{id}/prepare-run",
    "POST /api/task-specs/{id}/run-fake",
    "POST /api/guided-safe-fake-run",
    "POST /api/runs/{id}/verify",
    "POST /api/runs/{id}/cleanup",
)


@dataclass(frozen=True)
class CockpitServerConfig:
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    state_dir: Path = DEFAULT_STATE_DIR
    target_config_dir: Path = TARGET_CONFIG_DIR


class CockpitStateStore:
    def __init__(self, state_dir: Path, target_config_dir: Path) -> None:
        self.state_dir = state_dir
        self.prompts_dir = state_dir / "prompts"
        self.target_config_dir = target_config_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.prompts_dir.mkdir(parents=True, exist_ok=True)

    def summary(self, config: CockpitServerConfig) -> dict[str, Any]:
        discussions = self._read_collection("discussions")
        task_specs = self._read_collection("task_specs")
        prompts = self._read_collection("prompts")
        runs = self._read_collection("runs")
        targets = self._target_summaries()
        return {
            "status": "ok",
            "local_only": True,
            "host": config.host,
            "port": config.port,
            "state_dir": str(self.state_dir),
            "target_config_dir": str(self.target_config_dir),
            "counts": {
                "discussions": len(discussions),
                "messages": sum(len(item.get("messages", [])) for item in discussions.values()),
                "task_specs": len(task_specs),
                "prompts": len(prompts),
                "runs": len(runs),
            },
            "discussions": sorted(discussions),
            "task_specs": sorted(task_specs),
            "prompts": sorted(prompts),
            "runs": sorted(runs),
            "target_projects": [item["project_id"] for item in targets],
            "target_project_count": len(targets),
            "exposed_routes": list(EXPOSED_ROUTES),
            "live_deploy_enabled": False,
            "public_routes_enabled": False,
            "codex_runner_enabled": False,
            "fake_executor_enabled": True,
            "real_executor_enabled": False,
            "ai_curator_enabled": True,
            "openai_curator_optional": True,
            "openai_api_enabled": False,
            "notice": LOCAL_ONLY_NOTICE,
        }

    def create_discussion(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        discussions = self._read_collection("discussions")
        discussion_id = _new_id("discussion", discussions)
        discussion = {
            "id": discussion_id,
            "status": "open",
            "title": str(payload.get("title") or "Local curator discussion"),
            "created_at": _now_utc(),
            "messages": [],
        }
        discussions[discussion_id] = discussion
        self._write_collection("discussions", discussions)
        return discussion

    def add_message(self, discussion_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        discussions = self._read_collection("discussions")
        discussion = discussions.get(discussion_id)
        if discussion is None:
            raise NotFoundError(f"discussion not found: {discussion_id}")
        role = str(payload.get("role") or "operator")
        content = str(payload.get("content") or "").strip()
        if role not in {"operator", "curator"}:
            raise BadRequestError("message role must be operator or curator")
        if not content:
            raise BadRequestError("message content is required")

        messages = list(discussion.get("messages") or [])
        messages.append(
            {
                "id": f"msg-{len(messages) + 1:03d}",
                "role": role,
                "content": content,
                "created_at": _now_utc(),
            }
        )
        if role == "operator":
            messages.append(
                {
                    "id": f"msg-{len(messages) + 1:03d}",
                    "role": "curator",
                    "content": "curator API not connected in MVP; edit and save a task spec manually.",
                    "created_at": _now_utc(),
                }
            )
        discussion["messages"] = messages
        discussion["updated_at"] = _now_utc()
        discussions[discussion_id] = discussion
        self._write_collection("discussions", discussions)
        return discussion

    def draft_task_spec_from_discussion(self, discussion_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        discussion = self._get_discussion(discussion_id)
        target_project_id = _optional_str(payload.get("target_project_id"))
        target_defaults = None
        repo_context_summary = _optional_str(payload.get("repo_context_summary"))
        if target_project_id:
            target = self._target_config_by_id(target_project_id)
            validation = validate_target_project(target)
            if validation.status == "blocked":
                return {
                    "status": "blocked",
                    "task_spec_id": None,
                    "validation_ok": False,
                    "errors": [],
                    "warnings": list(validation.warnings),
                    "provider": str(payload.get("mode") or "fake"),
                    "model": None,
                    "blocked_reason": "; ".join(validation.blockers),
                }
            target_defaults = target_project_defaults(target)
            if not repo_context_summary:
                try:
                    snapshot = build_target_context_snapshot(target, max_bytes_per_file=2000)
                    repo_context_summary = _compact_target_context_for_intake(
                        target_context_summary_to_dict(build_target_context_summary(target)),
                        snapshot.source_summary,
                    )
                except Exception:
                    repo_context_summary = "; ".join(validation.warnings)
        result = draft_task_spec(
            CuratorDraftRequest(
                discussion_id=discussion_id,
                messages=tuple(_safe_messages(discussion.get("messages", []))),
                existing_task_spec=_optional_mapping(payload.get("existing_task_spec")),
                repo_context_summary=repo_context_summary,
                target_project_id=target_project_id,
                target_defaults=target_defaults,
                mode=str(payload.get("mode") or "fake"),
            )
        )
        result_payload = curator_draft_result_to_dict(result)
        if result.status != "success" or not result.task_spec:
            return {
                "status": result.status,
                "task_spec_id": None,
                "validation_ok": False,
                "errors": result_payload["errors"],
                "warnings": result_payload["warnings"],
                "provider": result.provider,
                "model": result.model,
                "blocked_reason": result.blocked_reason,
            }

        saved = self.create_task_spec(result.task_spec)
        target_summary = self._target_summary_for_payload(saved)
        return {
            "status": "drafted",
            "task_spec_id": saved["id"],
            "task_spec": saved,
            "task_card": _task_card_summary(saved),
            "target_summary": target_summary,
            "next_recommended_action": _next_action_for_spec(saved),
            "validation_ok": True,
            "errors": [],
            "warnings": result_payload["warnings"],
            "provider": result.provider,
            "model": result.model,
            "blocked_reason": None,
        }

    def create_task_spec(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        task_specs = self._read_collection("task_specs")
        target_project_id = _optional_str(payload.get("target_project_id"))
        normalized_payload = _json_ready(dict(payload))
        if target_project_id:
            normalized_payload = merge_target_defaults_into_task_spec_payload(
                normalized_payload,
                self._target_config_by_id(target_project_id),
            )
        task_spec = task_spec_from_mapping(normalized_payload)
        validate_task_spec(task_spec)
        steps = sprint_steps_from_task_spec_mapping(normalized_payload, task_spec)
        for step in steps:
            validate_sprint_step(step)
        stored = _json_ready(dict(normalized_payload))
        stored["id"] = task_spec.id
        stored["status"] = task_spec.status
        stored["forbidden_paths"] = list(task_spec.forbidden_paths)
        stored["forbidden_actions"] = list(task_spec.forbidden_actions)
        stored["required_smokes"] = list(task_spec.required_smokes)
        if target_project_id:
            stored["target_context_summary"] = target_context_summary_to_dict(
                build_target_context_summary(self._target_config_by_id(target_project_id))
            )
        stored["saved_at"] = _now_utc()
        task_specs[task_spec.id] = stored
        self._write_collection("task_specs", task_specs)
        return stored

    def get_task_spec(self, task_spec_id: str) -> dict[str, Any]:
        task_specs = self._read_collection("task_specs")
        task_spec = task_specs.get(task_spec_id)
        if task_spec is None:
            raise NotFoundError(f"task spec not found: {task_spec_id}")
        return task_spec

    def freeze_task_spec(self, task_spec_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        task_specs = self._read_collection("task_specs")
        existing = task_specs.get(task_spec_id)
        if existing is None:
            raise NotFoundError(f"task spec not found: {task_spec_id}")
        task_spec = task_spec_from_mapping(existing)
        if task_spec.status != "draft":
            raise BadRequestError("task spec is already frozen")
        frozen = freeze_task_spec(task_spec, frozen_at=_optional_str(payload.get("frozen_at")))
        frozen_payload = task_spec_to_dict(frozen)
        for key in ("sprint_steps", "target_project_id", "target_project", "target_context_summary"):
            if key in existing:
                frozen_payload[key] = existing[key]
        frozen_payload["saved_at"] = _now_utc()
        task_specs[task_spec_id] = frozen_payload
        self._write_collection("task_specs", task_specs)
        return frozen_payload

    def generate_prompt(self, task_spec_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        task_spec_payload = self.get_task_spec(task_spec_id)
        task_spec = task_spec_from_mapping(task_spec_payload)
        validate_task_spec(task_spec, require_frozen=True)
        steps = sprint_steps_from_task_spec_mapping(task_spec_payload, task_spec)
        step_id = str(payload.get("step_id") or steps[0].id)
        step = _select_step(steps, step_id)
        prompt = build_codex_prompt(task_spec, step)

        prompts = self._read_collection("prompts")
        prompt_id = f"prompt-{task_spec.id}-{step.id}-{(task_spec.spec_hash or 'nohash')[:12]}"
        prompt_path = self.prompts_dir / f"{prompt_id}.txt"
        prompt_path.write_text(prompt, encoding="utf-8")
        prompt_summary = {
            "id": prompt_id,
            "task_spec_id": task_spec.id,
            "task_class": task_spec.task_class,
            "step_id": step.id,
            "path": str(prompt_path),
            "created_at": _now_utc(),
            "mandatory_blocks_present": all(
                token in prompt
                for token in (
                    "Класс задачи:",
                    "Причина классификации:",
                    "Режим выполнения:",
                    "=== ДЛЯ КУРАТОРА ===",
                    "=== СЖАТАЯ ПРОВЕРКА ===",
                )
            ),
        }
        prompts[prompt_id] = prompt_summary
        self._write_collection("prompts", prompts)
        return prompt_summary

    def get_prompt_text(self, prompt_id: str) -> str:
        prompts = self._read_collection("prompts")
        prompt = prompts.get(prompt_id)
        if prompt is None:
            raise NotFoundError(f"prompt not found: {prompt_id}")
        return Path(str(prompt["path"])).read_text(encoding="utf-8")

    def prepare_run(self, task_spec_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        task_spec_payload = self.get_task_spec(task_spec_id)
        step_id = self._step_id_from_payload(task_spec_payload, payload)
        result = prepare_run(
            task_spec_payload,
            step_id=step_id,
            repo_root=ROOT,
            state_dir=self.state_dir,
            executor_mode="fake",
        )
        summary = _run_summary_from_result(result, verifier=None)
        _decorate_run_summary(summary, task_spec_payload)
        self._remember_run(summary)
        return summary

    def run_fake(self, task_spec_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        task_spec_payload = self.get_task_spec(task_spec_id)
        step_id = self._step_id_from_payload(task_spec_payload, payload)
        result = run_step(
            task_spec_payload,
            step_id=step_id,
            repo_root=ROOT,
            state_dir=self.state_dir,
            executor_mode="fake",
        )
        record = load_run_record(Path(result.run_dir))
        summary = _run_summary_from_record(record)
        _decorate_run_summary(summary, task_spec_payload)
        self._remember_run(summary)
        return summary

    def get_run(self, run_id: str) -> dict[str, Any]:
        run_dir = self._run_dir_for_id(run_id)
        record = load_run_record(run_dir)
        summary = _run_summary_from_record(record)
        _decorate_run_summary(summary, record.get("task_spec", {}))
        result = record.get("result", {})
        summary["metadata"] = record
        summary["prompt_text"] = _read_run_artifact_preview(run_dir, result.get("prompt_path"))
        summary["handoff_text"] = _read_run_artifact_preview(run_dir, result.get("handoff_path"))
        summary["run_result_summary"] = _compact_run_result_summary(summary)
        summary["blocker"] = _blocker_summary(summary)
        return summary

    def get_run_summary(self, run_id: str) -> dict[str, Any]:
        return self.get_run(run_id)["run_result_summary"]

    def verify_run(self, run_id: str) -> dict[str, Any]:
        run_dir = self._run_dir_for_id(run_id)
        verifier = verify_run(run_dir)
        record = load_run_record(run_dir)
        summary = _run_summary_from_record(record)
        summary["verifier"] = verifier_result_to_dict(verifier)
        _decorate_run_summary(summary, record.get("task_spec", {}))
        self._remember_run(summary)
        return summary

    def cleanup_run(self, run_id: str) -> dict[str, Any]:
        run_dir = self._run_dir_for_id(run_id)
        cleanup = cleanup_run_worktree(run_dir)
        record = load_run_record(run_dir)
        summary = _run_summary_from_record(record)
        summary["cleanup"] = cleanup
        _decorate_run_summary(summary, record.get("task_spec", {}))
        self._remember_run(summary)
        return summary

    def guided_safe_fake_run(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        task_spec_id = str(payload.get("task_spec_id") or "")
        if not task_spec_id:
            raise BadRequestError("task_spec_id is required")
        task_spec_payload = self.get_task_spec(task_spec_id)
        step_id = self._step_id_from_payload(task_spec_payload, payload)
        prompt_summary = self.generate_prompt(task_spec_id, {"step_id": step_id})
        prepared = self.prepare_run(task_spec_id, {"step_id": step_id})
        fake_run = self.run_fake(task_spec_id, {"step_id": step_id})
        verified = self.verify_run(str(fake_run["run_id"]))
        summary = {
            "status": "verifier_passed" if verified.get("verifier_status") == "passed" else "failed",
            "task_spec_id": task_spec_id,
            "step_id": step_id,
            "target_project_id": task_spec_payload.get("target_project_id"),
            "prompt_id": prompt_summary["id"],
            "prepared_run_id": prepared["run_id"],
            "run_id": fake_run["run_id"],
            "prompt_path": fake_run["prompt_path"],
            "handoff_path": fake_run["handoff_path"],
            "worktree_path": fake_run["worktree_path"],
            "verifier_status": verified.get("verifier_status"),
            "blocker_reason": verified.get("blocker_reason"),
            "mandatory_handoff_blocks_present": verified.get("mandatory_handoff_blocks_present"),
            "errors": [],
        }
        summary["run_result_summary"] = _compact_run_result_summary({**verified, **summary})
        summary["blocker"] = _blocker_summary({**verified, **summary})
        return summary

    def _read_collection(self, name: str) -> dict[str, Any]:
        path = self.state_dir / f"{name}.json"
        if not path.exists():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise BadRequestError(f"state collection is not an object: {name}")
        return payload

    def _write_collection(self, name: str, payload: Mapping[str, Any]) -> None:
        path = self.state_dir / f"{name}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _remember_run(self, summary: Mapping[str, Any]) -> None:
        run_id = str(summary.get("run_id") or "")
        if not run_id:
            raise BadRequestError("run summary is missing run_id")
        runs = self._read_collection("runs")
        runs[run_id] = _json_ready(dict(summary))
        self._write_collection("runs", runs)

    def _run_dir_for_id(self, run_id: str) -> Path:
        if "/" in run_id or "\\" in run_id or ".." in run_id:
            raise BadRequestError(f"invalid run id: {run_id}")
        runs = self._read_collection("runs")
        run = runs.get(run_id)
        if isinstance(run, Mapping) and run.get("run_dir"):
            run_dir = Path(str(run["run_dir"])).resolve()
        else:
            run_dir = (self.state_dir / "runs" / run_id).resolve()
        if not _is_relative_to(run_dir, self.state_dir.resolve()):
            raise BadRequestError(f"run dir is outside local state dir: {run_dir}")
        if not run_dir.exists():
            raise NotFoundError(f"run not found: {run_id}")
        return run_dir

    def _step_id_from_payload(self, task_spec_payload: Mapping[str, Any], payload: Mapping[str, Any]) -> str:
        if payload.get("step_id"):
            return str(payload["step_id"])
        task_spec = task_spec_from_mapping(task_spec_payload)
        steps = sprint_steps_from_task_spec_mapping(task_spec_payload, task_spec)
        return steps[0].id

    def _get_discussion(self, discussion_id: str) -> Mapping[str, Any]:
        discussions = self._read_collection("discussions")
        discussion = discussions.get(discussion_id)
        if not isinstance(discussion, Mapping):
            raise NotFoundError(f"discussion not found: {discussion_id}")
        return discussion

    def list_target_projects(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "targets": self._target_summaries(),
        }

    def get_target_project(self, project_id: str) -> dict[str, Any]:
        config = self._target_config_by_id(project_id)
        validation = validate_target_project(config)
        summary = build_target_context_summary(config)
        return {
            "status": validation.status,
            "target": target_project_config_to_dict(config),
            "validation": target_project_validation_result_to_dict(validation),
            "summary": target_context_summary_to_dict(summary),
        }

    def _target_summaries(self) -> list[dict[str, Any]]:
        summaries: list[dict[str, Any]] = []
        for config in load_target_project_configs(self.target_config_dir):
            validation = validate_target_project(config)
            target_summary = build_target_context_summary(config)
            summaries.append(
                {
                    "project_id": config.project_id,
                    "display_name": config.display_name,
                    "repo_path": config.repo_path,
                    "target_readonly_by_default": config.target_readonly_by_default,
                    "validation_status": validation.status,
                    "repo_exists": validation.repo_exists,
                    "is_git_repo": validation.is_git_repo,
                    "current_branch": validation.current_branch,
                    "head_commit": validation.head_commit,
                    "source_of_truth_paths_found": list(target_summary.source_of_truth_paths_found),
                    "missing_source_paths": list(target_summary.missing_source_paths),
                    "derived_secondary_paths": list(target_summary.derived_secondary_paths),
                    "default_forbidden_paths": list(target_summary.default_forbidden_paths),
                    "default_forbidden_actions": list(target_summary.default_forbidden_actions),
                    "default_required_smokes": list(target_summary.default_required_smokes),
                    "workflow_notes": list(target_summary.workflow_notes),
                    "warnings": list(validation.warnings),
                    "blockers": list(validation.blockers),
                }
            )
        return summaries

    def _target_config_by_id(self, project_id: str):
        for config in load_target_project_configs(self.target_config_dir):
            if config.project_id == project_id:
                return config
        raise NotFoundError(f"target project not found: {project_id}")

    def _target_summary_for_payload(self, payload: Mapping[str, Any]) -> dict[str, Any] | None:
        target_project_id = _optional_str(payload.get("target_project_id"))
        if not target_project_id:
            return None
        return target_context_summary_to_dict(build_target_context_summary(self._target_config_by_id(target_project_id)))


class CockpitRequestHandler(BaseHTTPRequestHandler):
    server: "CockpitHTTPServer"

    def do_GET(self) -> None:  # noqa: N802
        path = _route_path(self.path)
        try:
            if path == "/":
                self._send_html(_render_html())
                return
            if path == "/api/state":
                self._send_json(self.server.store.summary(self.server.config))
                return
            if path == "/api/example-task-spec":
                self._send_json(_read_json(EXAMPLE_TASK_SPEC))
                return
            if path in {"/api/target-projects", "/api/targets"}:
                self._send_json(self.server.store.list_target_projects())
                return
            parts = _split_path(path)
            if len(parts) == 3 and parts[:2] == ["api", "target-projects"]:
                self._send_json(self.server.store.get_target_project(parts[2]))
                return
            if len(parts) == 4 and parts[:2] == ["api", "target-projects"] and parts[3] == "summary":
                self._send_json(self.server.store.get_target_project(parts[2]))
                return
            if len(parts) == 4 and parts[:2] == ["api", "targets"] and parts[3] == "summary":
                self._send_json(self.server.store.get_target_project(parts[2]))
                return
            if len(parts) == 3 and parts[:2] == ["api", "task-specs"]:
                self._send_json(self.server.store.get_task_spec(parts[2]))
                return
            if len(parts) == 3 and parts[:2] == ["api", "prompts"]:
                self._send_text(self.server.store.get_prompt_text(parts[2]))
                return
            if len(parts) == 3 and parts[:2] == ["api", "runs"]:
                self._send_json(self.server.store.get_run(parts[2]))
                return
            if len(parts) == 4 and parts[:2] == ["api", "runs"] and parts[3] == "summary":
                self._send_json(self.server.store.get_run_summary(parts[2]))
                return
            self._send_error(HTTPStatus.NOT_FOUND, "route not found")
        except RequestError as exc:
            self._send_error(exc.status, str(exc))
        except Exception as exc:
            self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def do_POST(self) -> None:  # noqa: N802
        path = _route_path(self.path)
        try:
            payload = self._read_json_body()
            if path == "/api/discussions":
                self._send_json(self.server.store.create_discussion(payload), HTTPStatus.CREATED)
                return
            if path == "/api/task-specs":
                self._send_json(self.server.store.create_task_spec(payload), HTTPStatus.CREATED)
                return
            if path == "/api/guided-safe-fake-run":
                self._send_json(self.server.store.guided_safe_fake_run(payload), HTTPStatus.CREATED)
                return
            if path == "/api/draft-task-spec":
                discussion_id = str(payload.get("discussion_id") or "")
                if not discussion_id:
                    raise BadRequestError("discussion_id is required")
                self._send_json(self.server.store.draft_task_spec_from_discussion(discussion_id, payload), HTTPStatus.CREATED)
                return
            parts = _split_path(path)
            if len(parts) == 4 and parts[:2] == ["api", "discussions"] and parts[3] == "messages":
                self._send_json(self.server.store.add_message(parts[2], payload))
                return
            if len(parts) == 4 and parts[:2] == ["api", "discussions"] and parts[3] == "draft-task-spec":
                self._send_json(self.server.store.draft_task_spec_from_discussion(parts[2], payload), HTTPStatus.CREATED)
                return
            if len(parts) == 4 and parts[:2] == ["api", "task-specs"] and parts[3] == "freeze":
                frozen = self.server.store.freeze_task_spec(parts[2], payload)
                self._send_json(
                    {
                        "status": "frozen",
                        "task_spec_id": frozen["id"],
                        "spec_hash": frozen["spec_hash"],
                        "frozen_at": frozen["frozen_at"],
                    }
                )
                return
            if len(parts) == 4 and parts[:2] == ["api", "task-specs"] and parts[3] == "generate-prompt":
                self._send_json(self.server.store.generate_prompt(parts[2], payload), HTTPStatus.CREATED)
                return
            if len(parts) == 4 and parts[:2] == ["api", "task-specs"] and parts[3] == "prepare-run":
                self._send_json(self.server.store.prepare_run(parts[2], payload), HTTPStatus.CREATED)
                return
            if len(parts) == 4 and parts[:2] == ["api", "task-specs"] and parts[3] == "run-fake":
                self._send_json(self.server.store.run_fake(parts[2], payload), HTTPStatus.CREATED)
                return
            if len(parts) == 4 and parts[:2] == ["api", "runs"] and parts[3] == "verify":
                self._send_json(self.server.store.verify_run(parts[2]))
                return
            if len(parts) == 4 and parts[:2] == ["api", "runs"] and parts[3] == "cleanup":
                self._send_json(self.server.store.cleanup_run(parts[2]))
                return
            self._send_error(HTTPStatus.NOT_FOUND, "route not found")
        except RequestError as exc:
            self._send_error(exc.status, str(exc))
        except ControlPlaneValidationError as exc:
            self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
        except ControlPlaneExecutionError as exc:
            self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
        except Exception as exc:
            self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def log_message(self, format: str, *args: object) -> None:
        return

    def _read_json_body(self) -> Mapping[str, Any]:
        length = int(self.headers.get("Content-Length") or "0")
        if length == 0:
            return {}
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(payload, Mapping):
            raise BadRequestError("JSON body must be an object")
        return payload

    def _send_json(self, payload: Mapping[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, text: str) -> None:
        body = text.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, status: HTTPStatus, message: str) -> None:
        self._send_json({"status": "error", "error": message}, status)


class CockpitHTTPServer(ThreadingHTTPServer):
    def __init__(self, config: CockpitServerConfig) -> None:
        if config.host != "127.0.0.1":
            raise ValueError("Development Control Plane server is local-only and must bind 127.0.0.1")
        self.config = config
        self.store = CockpitStateStore(config.state_dir, config.target_config_dir)
        super().__init__((config.host, config.port), CockpitRequestHandler)


class RequestError(Exception):
    status = HTTPStatus.BAD_REQUEST


class BadRequestError(RequestError):
    status = HTTPStatus.BAD_REQUEST


class NotFoundError(RequestError):
    status = HTTPStatus.NOT_FOUND


def build_server(config: CockpitServerConfig) -> CockpitHTTPServer:
    return CockpitHTTPServer(config)


def _run_summary_from_result(result, verifier: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = run_result_to_dict(result)
    return {
        "status": payload["status"],
        "run_id": payload["id"],
        "task_spec_id": payload["task_spec_id"],
        "step_id": payload["step_id"],
        "branch_name": payload["branch_name"],
        "run_dir": payload["run_dir"],
        "worktree_path": payload["worktree_path"],
        "prompt_path": payload["prompt_path"],
        "handoff_path": payload["handoff_path"],
        "log_path": payload["log_path"],
        "changed_files": payload["changed_files"],
        "check_results": payload["check_results"],
        "blocker_reason": payload["blocker_reason"],
        "next_manual_step": payload["next_manual_step"],
        "verifier_status": None if verifier is None else verifier.get("status"),
        "mandatory_handoff_blocks_present": False if verifier is None else bool(verifier.get("mandatory_handoff_blocks_present")),
        "errors": [],
    }


def _run_summary_from_record(record: Mapping[str, Any]) -> dict[str, Any]:
    result = record.get("result")
    if not isinstance(result, Mapping):
        raise BadRequestError("run record missing result object")
    verifier = record.get("verifier")
    if verifier is not None and not isinstance(verifier, Mapping):
        verifier = None
    return {
        "status": result.get("status"),
        "run_id": result.get("id"),
        "task_spec_id": result.get("task_spec_id"),
        "step_id": result.get("step_id"),
        "branch_name": result.get("branch_name"),
        "run_dir": result.get("run_dir"),
        "worktree_path": result.get("worktree_path"),
        "prompt_path": result.get("prompt_path"),
        "handoff_path": result.get("handoff_path"),
        "log_path": result.get("log_path"),
        "changed_files": result.get("changed_files", []),
        "check_results": result.get("check_results", []),
        "blocker_reason": result.get("blocker_reason"),
        "next_manual_step": result.get("next_manual_step"),
        "verifier_status": None if verifier is None else verifier.get("status"),
        "mandatory_handoff_blocks_present": False if verifier is None else bool(verifier.get("mandatory_handoff_blocks_present")),
        "errors": [],
    }


def _decorate_run_summary(summary: dict[str, Any], task_spec_payload: Mapping[str, Any]) -> None:
    target_project_id = task_spec_payload.get("target_project_id")
    summary["target_project_id"] = target_project_id
    summary["changed_files_count"] = len(summary.get("changed_files") or [])
    summary["prompt_available"] = bool(summary.get("prompt_path"))
    summary["handoff_available"] = bool(summary.get("handoff_path"))
    summary["cleanup_available"] = bool(summary.get("worktree_path"))
    summary["blocker"] = _blocker_summary(summary)
    summary["run_result_summary"] = _compact_run_result_summary(summary)


def _compact_run_result_summary(summary: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": _operator_status(summary),
        "raw_status": summary.get("status"),
        "verifier_status": summary.get("verifier_status"),
        "target_project_id": summary.get("target_project_id"),
        "run_id": summary.get("run_id"),
        "changed_files_count": len(summary.get("changed_files") or []),
        "blocker_reason": summary.get("blocker_reason"),
        "next_manual_step": summary.get("next_manual_step"),
        "prompt_available": bool(summary.get("prompt_path")),
        "handoff_available": bool(summary.get("handoff_path")),
        "cleanup_available": bool(summary.get("worktree_path")),
    }


def _blocker_summary(summary: Mapping[str, Any]) -> dict[str, Any]:
    reason = summary.get("blocker_reason")
    if not reason:
        return {
            "status": "none",
            "reason": None,
            "next_manual_step": None,
            "source": None,
            "technical_details": {},
        }
    verifier_status = summary.get("verifier_status")
    source = "verifier" if verifier_status in {"failed", "blocked"} else "execution"
    return {
        "status": "present",
        "reason": reason,
        "next_manual_step": summary.get("next_manual_step") or "Inspect run artifacts and verifier output.",
        "source": source,
        "technical_details": {
            "run_id": summary.get("run_id"),
            "verifier_status": verifier_status,
            "check_results": summary.get("check_results") or [],
        },
    }


def _operator_status(summary: Mapping[str, Any]) -> str:
    status = str(summary.get("status") or "")
    verifier_status = str(summary.get("verifier_status") or "")
    if status == "verifier_passed" or verifier_status == "passed":
        return "Passed"
    if status == "blocked" or verifier_status == "blocked":
        return "Blocked"
    if status == "human_gate_required":
        return "Human gate required"
    if status == "failed" or verifier_status == "failed":
        return "Failed"
    if status == "prepared":
        return "Prepared"
    return status or "Unknown"


def _task_card_summary(spec: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "title": spec.get("title"),
        "target_project": spec.get("target_project_id"),
        "class": spec.get("task_class"),
        "goal": spec.get("goal"),
        "scope": spec.get("scope", []),
        "not_in_scope": spec.get("not_in_scope", []),
        "acceptance_criteria": spec.get("acceptance_criteria", []),
        "required_smokes": spec.get("required_smokes", []),
        "forbidden_paths": spec.get("forbidden_paths", []),
        "forbidden_actions": spec.get("forbidden_actions", []),
        "human_gates": spec.get("human_gates", []),
        "warnings": _target_warnings_from_spec(spec),
        "next_recommended_action": _next_action_for_spec(spec),
    }


def _target_warnings_from_spec(spec: Mapping[str, Any]) -> list[str]:
    summary = spec.get("target_context_summary")
    if isinstance(summary, Mapping):
        warnings = summary.get("warnings", [])
        if isinstance(warnings, list):
            return [str(item) for item in warnings]
    return []


def _next_action_for_spec(spec: Mapping[str, Any]) -> str:
    if not spec:
        return "Draft Task Spec from Discussion"
    if spec.get("status") != "frozen":
        return "Freeze Task"
    return "Run Safe Fake Flow"


def _compact_target_context_for_intake(summary: Mapping[str, Any], source_summary: str) -> str:
    payload = {
        "project_id": summary.get("project_id"),
        "display_name": summary.get("display_name"),
        "validation_status": summary.get("validation_status"),
        "current_branch": summary.get("current_branch"),
        "head_commit": summary.get("head_commit"),
        "source_of_truth_paths_found": summary.get("source_of_truth_paths_found", []),
        "missing_source_paths": summary.get("missing_source_paths", []),
        "derived_secondary_paths": summary.get("derived_secondary_paths", []),
        "default_forbidden_paths": summary.get("default_forbidden_paths", []),
        "default_forbidden_actions": summary.get("default_forbidden_actions", []),
        "default_required_smokes": summary.get("default_required_smokes", []),
        "workflow_notes": summary.get("workflow_notes", []),
        "warnings": summary.get("warnings", []),
        "source_summary": source_summary,
        "source_of_truth_note": "Target context is read-only evidence, not source of truth.",
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local-only Development Control Plane prototype.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", default=DEFAULT_PORT, type=int)
    parser.add_argument("--state-dir", default=DEFAULT_STATE_DIR, type=Path)
    parser.add_argument("--target-config-dir", default=TARGET_CONFIG_DIR, type=Path)
    args = parser.parse_args(argv)

    config = CockpitServerConfig(
        host=args.host,
        port=args.port,
        state_dir=args.state_dir,
        target_config_dir=args.target_config_dir,
    )
    server = build_server(config)
    print(
        json.dumps(
            {
                "status": "serving",
                "host": config.host,
                "port": server.server_port,
                "state_dir": str(config.state_dir),
                "target_config_dir": str(config.target_config_dir),
                "local_only": True,
                "notice": LOCAL_ONLY_NOTICE,
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    return 0


def _render_html() -> str:
    example = escape(EXAMPLE_TASK_SPEC.read_text(encoding="utf-8"))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Development Control Plane</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 0; background: #f7f7f5; color: #202124; }}
    header {{ padding: 18px 24px; background: #17202a; color: white; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 20px; display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
    section {{ background: white; border: 1px solid #d9d9d4; border-radius: 6px; padding: 14px; }}
    h1 {{ margin: 0; font-size: 22px; }}
    h2 {{ margin: 0 0 10px; font-size: 16px; }}
    textarea, input, select {{ width: 100%; box-sizing: border-box; border: 1px solid #c8c8c2; border-radius: 4px; padding: 8px; font: 13px ui-monospace, SFMono-Regular, Menlo, monospace; }}
    textarea {{ min-height: 150px; resize: vertical; }}
    button {{ margin: 8px 8px 0 0; border: 1px solid #2f5f8f; background: #2f6fab; color: white; border-radius: 4px; padding: 7px 10px; cursor: pointer; }}
    button.secondary {{ background: #f4f4f0; color: #202124; border-color: #b7b7b0; }}
    pre {{ white-space: pre-wrap; overflow-wrap: anywhere; background: #f3f3ef; padding: 10px; border-radius: 4px; max-height: 360px; overflow: auto; }}
    .full {{ grid-column: 1 / -1; }}
    .muted {{ color: #666; font-size: 13px; }}
  </style>
</head>
<body>
  <header>
    <h1>Development Control Plane</h1>
    <div class="muted">{escape(LOCAL_ONLY_NOTICE)}</div>
  </header>
  <main>
    <section class="full">
      <h2>Target Project</h2>
      <select id="targetProjectInput" onchange="selectTargetProject()">
        <option value="">No target selected</option>
      </select>
      <button class="secondary" onclick="loadTargets()">Refresh targets</button>
      <pre id="targetStatus">Target repos are external and read-only by default.</pre>
    </section>
    <section>
      <h2>Discuss</h2>
      <textarea id="messageInput" placeholder="Operator message"></textarea>
      <button onclick="addMessage()">Add message</button>
      <select id="curatorModeInput">
        <option value="fake">Fake curator</option>
        <option value="openai">OpenAI curator</option>
      </select>
      <button onclick="draftTaskSpec()">Draft Task Spec from Discussion</button>
      <pre id="messages">No discussion yet.</pre>
      <pre id="draftStatus">No draft requested.</pre>
    </section>
    <section>
      <h2>Human Gates</h2>
      <pre id="humanGates">No human gates for this spec.</pre>
    </section>
    <section class="full">
      <h2>Task Spec</h2>
      <h3>Task Card</h3>
      <pre id="taskSpecSummary">No task spec yet.</pre>
      <h3>Next recommended action</h3>
      <pre id="nextAction">Draft Task Spec from Discussion</pre>
      <details>
        <summary>Advanced / Raw JSON</summary>
        <textarea id="taskSpecInput">{example}</textarea>
        <button class="secondary" onclick="loadExample()">Load example task spec</button>
      </details>
      <button onclick="saveDraft()">Validate / Save Draft</button>
      <button onclick="freezeTask()">Freeze Task</button>
      <pre id="taskSpecStatus">Ready.</pre>
    </section>
    <section>
      <h2>Sprint Plan</h2>
      <pre id="sprintPlan">No saved task spec.</pre>
    </section>
    <section>
      <h2>Prompt</h2>
      <input id="stepIdInput" value="step-001">
      <button onclick="generatePrompt()">Generate Codex Prompt</button>
      <pre id="promptOutput">No prompt generated.</pre>
    </section>
    <section class="full">
      <h2>Run</h2>
      <div class="muted">Fake executor only in UI. Real Codex execution is CLI-only and disabled in UI for MVP-2.0. No live/deploy/public route.</div>
      <button onclick="runSafeFakeFlow()">Run Safe Fake Flow</button>
      <button class="secondary" onclick="cleanupRun()">Cleanup Run</button>
      <details>
        <summary>Advanced run controls</summary>
        <button onclick="prepareRun()">Prepare Run</button>
        <button onclick="runFake()">Run Fake Executor</button>
        <button onclick="verifyRun()">Verify Run</button>
      </details>
      <h3>Result summary</h3>
      <pre id="runStatus">No run yet.</pre>
      <h3>Blocker</h3>
      <pre id="blockerStatus">No blocker</pre>
      <details>
        <summary>Prompt preview</summary>
        <pre id="runPrompt">No run prompt.</pre>
      </details>
      <details>
        <summary>Handoff preview</summary>
        <pre id="runHandoff">No handoff.</pre>
      </details>
    </section>
  </main>
  <script>
    let discussionId = null;
    let taskSpecId = null;
    let currentRunId = null;
    let selectedTargetProjectId = null;

    async function request(path, options = {{}}) {{
      const response = await fetch(path, options);
      const text = await response.text();
      const data = text ? JSON.parse(text) : {{}};
      if (!response.ok) throw new Error(data.error || response.statusText);
      return data;
    }}

    async function loadExample() {{
      const data = await request('/api/example-task-spec');
      document.getElementById('taskSpecInput').value = JSON.stringify(data, null, 2);
    }}

    async function loadTargets() {{
      const data = await request('/api/target-projects');
      const select = document.getElementById('targetProjectInput');
      const current = select.value;
      select.innerHTML = '<option value="">No target selected</option>';
      for (const target of data.targets || []) {{
        const option = document.createElement('option');
        option.value = target.project_id;
        option.textContent = `${{target.display_name}} (${{target.validation_status}})`;
        select.appendChild(option);
      }}
      if (current) select.value = current;
      selectedTargetProjectId = select.value || null;
      document.getElementById('targetStatus').textContent = JSON.stringify(data.targets || [], null, 2);
    }}

    async function selectTargetProject() {{
      selectedTargetProjectId = document.getElementById('targetProjectInput').value || null;
      if (!selectedTargetProjectId) {{
        document.getElementById('targetStatus').textContent = 'No target selected. Generic defaults will be used.';
        return;
      }}
      const data = await request(`/api/target-projects/${{selectedTargetProjectId}}`);
      document.getElementById('targetStatus').textContent = JSON.stringify(data, null, 2);
    }}

    async function addMessage() {{
      if (!discussionId) {{
        const discussion = await request('/api/discussions', {{method: 'POST', body: '{{}}'}});
        discussionId = discussion.id;
      }}
      const content = document.getElementById('messageInput').value;
      const discussion = await request(`/api/discussions/${{discussionId}}/messages`, {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{role: 'operator', content}})
      }});
      document.getElementById('messages').textContent = JSON.stringify(discussion.messages, null, 2);
    }}

    async function draftTaskSpec() {{
      try {{
        if (!discussionId) {{
          const discussion = await request('/api/discussions', {{method: 'POST', body: '{{}}'}});
          discussionId = discussion.id;
        }}
        const mode = document.getElementById('curatorModeInput').value || 'fake';
        const result = await request(`/api/discussions/${{discussionId}}/draft-task-spec`, {{
          method: 'POST',
          headers: {{'Content-Type': 'application/json'}},
          body: JSON.stringify({{mode, target_project_id: selectedTargetProjectId}})
        }});
        document.getElementById('draftStatus').textContent = JSON.stringify(result, null, 2);
        if (result.task_spec) {{
          taskSpecId = result.task_spec_id;
          document.getElementById('taskSpecInput').value = JSON.stringify(result.task_spec, null, 2);
          renderSpec(result.task_spec);
          if (result.target_summary) {{
            document.getElementById('targetStatus').textContent = JSON.stringify(result.target_summary, null, 2);
          }}
        }}
      }} catch (error) {{
        document.getElementById('draftStatus').textContent = String(error);
      }}
    }}

    async function saveDraft() {{
      try {{
        const payload = JSON.parse(document.getElementById('taskSpecInput').value);
        if (selectedTargetProjectId && !payload.target_project_id) payload.target_project_id = selectedTargetProjectId;
        const saved = await request('/api/task-specs', {{
          method: 'POST',
          headers: {{'Content-Type': 'application/json'}},
          body: JSON.stringify(payload)
        }});
        taskSpecId = saved.id;
        renderSpec(saved);
      }} catch (error) {{
        document.getElementById('taskSpecStatus').textContent = String(error);
      }}
    }}

    async function freezeTask() {{
      if (!taskSpecId) await saveDraft();
      const result = await request(`/api/task-specs/${{taskSpecId}}/freeze`, {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: '{{}}'
      }});
      const spec = await request(`/api/task-specs/${{taskSpecId}}`);
      renderSpec(spec);
      document.getElementById('taskSpecStatus').textContent = JSON.stringify(result, null, 2);
    }}

    async function generatePrompt() {{
      const stepId = document.getElementById('stepIdInput').value || 'step-001';
      const summary = await request(`/api/task-specs/${{taskSpecId}}/generate-prompt`, {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{step_id: stepId}})
      }});
      const response = await fetch(`/api/prompts/${{summary.id}}`);
      document.getElementById('promptOutput').textContent = await response.text();
    }}

    async function runSafeFakeFlow() {{
      try {{
        const stepId = document.getElementById('stepIdInput').value || 'step-001';
        const summary = await request('/api/guided-safe-fake-run', {{
          method: 'POST',
          headers: {{'Content-Type': 'application/json'}},
          body: JSON.stringify({{task_spec_id: taskSpecId, step_id: stepId}})
        }});
        currentRunId = summary.run_id;
        renderRun(summary);
        await loadRun(currentRunId);
      }} catch (error) {{
        document.getElementById('runStatus').textContent = String(error);
      }}
    }}

    async function prepareRun() {{
      const stepId = document.getElementById('stepIdInput').value || 'step-001';
      const summary = await request(`/api/task-specs/${{taskSpecId}}/prepare-run`, {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{step_id: stepId}})
      }});
      currentRunId = summary.run_id;
      renderRun(summary);
      await loadRun(currentRunId);
    }}

    async function runFake() {{
      const stepId = document.getElementById('stepIdInput').value || 'step-001';
      const summary = await request(`/api/task-specs/${{taskSpecId}}/run-fake`, {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{step_id: stepId}})
      }});
      currentRunId = summary.run_id;
      renderRun(summary);
      await loadRun(currentRunId);
    }}

    async function verifyRun() {{
      if (!currentRunId) return;
      const summary = await request(`/api/runs/${{currentRunId}}/verify`, {{method: 'POST', body: '{{}}'}});
      renderRun(summary);
      await loadRun(currentRunId);
    }}

    async function cleanupRun() {{
      if (!currentRunId) return;
      const summary = await request(`/api/runs/${{currentRunId}}/cleanup`, {{method: 'POST', body: '{{}}'}});
      renderRun(summary);
    }}

    async function loadRun(runId) {{
      const run = await request(`/api/runs/${{runId}}`);
      renderRun(run);
      document.getElementById('runPrompt').textContent = run.prompt_text || 'No run prompt.';
      document.getElementById('runHandoff').textContent = run.handoff_text || 'No handoff.';
    }}

    function renderSpec(spec) {{
      document.getElementById('taskSpecStatus').textContent = JSON.stringify({{id: spec.id, status: spec.status, spec_hash: spec.spec_hash}}, null, 2);
      document.getElementById('taskSpecSummary').textContent = formatTaskCard(spec);
      document.getElementById('nextAction').textContent = nextActionForSpec(spec);
      document.getElementById('sprintPlan').textContent = JSON.stringify(spec.sprint_steps || [], null, 2);
      const gates = spec.human_gates || [];
      document.getElementById('humanGates').textContent = gates.length ? gates.map((gate) => `- ${{gate}}`).join('\\n') : 'No human gates for this spec.';
    }}

    function renderRun(run) {{
      const view = run.run_result_summary || {{
        status: run.status,
        verifier_status: run.verifier_status,
        target_project_id: run.target_project_id || null,
        run_id: run.run_id,
        changed_files_count: (run.changed_files || []).length,
        blocker_reason: run.blocker_reason || null,
        next_manual_step: run.next_manual_step || null,
        prompt_available: Boolean(run.prompt_path),
        handoff_available: Boolean(run.handoff_path),
        cleanup_available: Boolean(run.worktree_path)
      }};
      document.getElementById('runStatus').textContent = JSON.stringify(view, null, 2);
      const blocker = run.blocker || (run.blocker_reason ? {{
        status: 'present',
        reason: run.blocker_reason,
        next_manual_step: run.next_manual_step || 'Inspect run artifacts and verifier output.',
        source: 'verifier'
      }} : {{status: 'none', reason: null, next_manual_step: null, source: null}});
      document.getElementById('blockerStatus').textContent = blocker.status === 'none'
        ? 'No blocker'
        : JSON.stringify(blocker, null, 2);
    }}

    function nextActionForSpec(spec) {{
      if (!spec || !spec.id) return 'Draft Task Spec from Discussion';
      if (spec.status !== 'frozen') return 'Freeze Task';
      return 'Run Safe Fake Flow';
    }}

    function formatTaskCard(spec) {{
      const target = spec.target_project_id || 'none';
      const targetSummary = spec.target_context_summary || {{}};
      const warnings = targetSummary.warnings || [];
      return [
        `Title: ${{spec.title || ''}}`,
        `Target project: ${{target}}`,
        `Class: ${{spec.task_class || ''}}`,
        '',
        `Goal:\\n${{spec.goal || ''}}`,
        '',
        `Scope:\\n${{formatList(spec.scope)}}`,
        '',
        `Not in scope:\\n${{formatList(spec.not_in_scope)}}`,
        '',
        `Acceptance criteria:\\n${{formatList(spec.acceptance_criteria)}}`,
        '',
        `Required smokes:\\n${{formatList(spec.required_smokes)}}`,
        '',
        `Forbidden paths:\\n${{formatList(spec.forbidden_paths)}}`,
        '',
        `Forbidden actions:\\n${{formatList(spec.forbidden_actions)}}`,
        '',
        `Human gates:\\n${{formatList(spec.human_gates) || 'No human gates for this spec.'}}`,
        '',
        `Warnings:\\n${{formatList(warnings) || 'No warnings'}}`
      ].join('\\n');
    }}

    function formatList(value) {{
      if (!Array.isArray(value) || value.length === 0) return '';
      return value.map((item) => `- ${{item}}`).join('\\n');
    }}

    loadTargets().catch((error) => {{
      document.getElementById('targetStatus').textContent = String(error);
    }});
  </script>
</body>
</html>"""


def _route_path(raw_path: str) -> str:
    return urlparse(raw_path).path


def _split_path(path: str) -> list[str]:
    return [unquote(part) for part in path.split("/") if part]


def _read_json(path: Path) -> Mapping[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise BadRequestError("JSON root must be an object")
    return payload


def _read_run_artifact_preview(run_dir: Path, path: Any, limit: int = 20000) -> str | None:
    if not path:
        return None
    text_path = Path(str(path)).resolve()
    if not _is_relative_to(text_path, run_dir.resolve()):
        raise BadRequestError(f"run artifact path is outside run dir: {text_path}")
    if not text_path.exists():
        return None
    text = text_path.read_text(encoding="utf-8")
    return text[:limit]


def _select_step(steps, step_id: str):
    for step in steps:
        if step.id == step_id:
            return step
    raise BadRequestError(f"sprint step not found: {step_id}")


def _new_id(prefix: str, existing: Mapping[str, Any]) -> str:
    index = len(existing) + 1
    while f"{prefix}-{index:03d}" in existing:
        index += 1
    return f"{prefix}-{index:03d}"


def _now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _optional_mapping(value: Any) -> Mapping[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise BadRequestError("existing_task_spec must be an object when provided")
    return value


def _safe_messages(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    messages: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        messages.append(
            {
                "role": str(item.get("role") or "operator"),
                "content": str(item.get("content") or ""),
            }
        )
    return messages


def _json_ready(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    return value


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


if __name__ == "__main__":
    raise SystemExit(main())
