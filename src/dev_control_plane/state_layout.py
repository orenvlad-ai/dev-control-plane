"""State and workspace layout resolver for hosted-ready control-plane runs."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
from typing import Mapping

STATE_DIR_ENV = "DEV_CONTROL_PLANE_STATE_DIR"
DEFAULT_STATE_DIR = Path("/tmp/development-control-plane-state")
_SAFE_COMPONENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class StateLayoutError(ValueError):
    """Raised when state or workspace paths cannot be owned safely."""


@dataclass(frozen=True)
class ControlPlaneRunLayout:
    state_root: Path
    run_id: str
    run_dir: Path
    artifacts_dir: Path
    logs_dir: Path
    verifier_dir: Path
    checks_dir: Path
    workspace_root: Path

    @property
    def prompt_path(self) -> Path:
        return self.artifacts_dir / "prompt.md"

    @property
    def handoff_path(self) -> Path:
        return self.artifacts_dir / "handoff.md"

    @property
    def diff_path(self) -> Path:
        return self.artifacts_dir / "diff.patch"

    @property
    def executor_log_path(self) -> Path:
        return self.logs_dir / "executor.log"

    @property
    def codex_log_path(self) -> Path:
        return self.logs_dir / "codex.log"

    @property
    def metadata_path(self) -> Path:
        return self.run_dir / "run.json"

    @property
    def managed_workspace_metadata_path(self) -> Path:
        return self.run_dir / "managed_workspace.json"

    @property
    def verifier_path(self) -> Path:
        return self.verifier_dir / "verifier.json"

    def ensure_dirs(self) -> None:
        for path in (
            self.run_dir,
            self.artifacts_dir,
            self.logs_dir,
            self.verifier_dir,
            self.checks_dir,
            self.workspace_root,
        ):
            path.mkdir(parents=True, exist_ok=True)

    def workspace_dir(self, workspace_id: str) -> Path:
        component = safe_state_component(workspace_id, "workspace_id")
        return _owned_path(self.workspace_root, component, owner=self.workspace_root, label="workspace_path")


@dataclass(frozen=True)
class ControlPlaneStateLayout:
    state_root: Path
    runs_dir: Path
    workspaces_dir: Path
    artifacts_dir: Path
    logs_dir: Path
    verifier_dir: Path
    collections_dir: Path

    @classmethod
    def from_path(cls, state_dir: Path | str | None = None) -> "ControlPlaneStateLayout":
        root = resolve_state_root(Path(state_dir) if state_dir is not None else None)
        return cls(
            state_root=root,
            runs_dir=_owned_path(root, "runs", owner=root, label="runs_dir"),
            workspaces_dir=_owned_path(root, "workspaces", owner=root, label="workspaces_dir"),
            artifacts_dir=_owned_path(root, "artifacts", owner=root, label="artifacts_dir"),
            logs_dir=_owned_path(root, "logs", owner=root, label="logs_dir"),
            verifier_dir=_owned_path(root, "verifier", owner=root, label="verifier_dir"),
            collections_dir=_owned_path(root, "collections", owner=root, label="collections_dir"),
        )

    def ensure_base_dirs(self) -> None:
        for path in (
            self.state_root,
            self.runs_dir,
            self.workspaces_dir,
            self.artifacts_dir,
            self.logs_dir,
            self.verifier_dir,
            self.collections_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)

    def run_layout(self, run_id: str) -> ControlPlaneRunLayout:
        component = safe_state_component(run_id, "run_id")
        run_dir = _owned_path(self.runs_dir, component, owner=self.runs_dir, label="run_dir")
        workspace_root = _owned_path(self.workspaces_dir, component, owner=self.workspaces_dir, label="run_workspace_root")
        return ControlPlaneRunLayout(
            state_root=self.state_root,
            run_id=component,
            run_dir=run_dir,
            artifacts_dir=_owned_path(run_dir, "artifacts", owner=run_dir, label="run_artifacts_dir"),
            logs_dir=_owned_path(run_dir, "logs", owner=run_dir, label="run_logs_dir"),
            verifier_dir=_owned_path(run_dir, "verifier", owner=run_dir, label="run_verifier_dir"),
            checks_dir=_owned_path(run_dir / "verifier", "checks", owner=run_dir, label="run_checks_dir"),
            workspace_root=workspace_root,
        )

    def collection_path(self, name: str) -> Path:
        component = safe_state_component(name, "collection_name")
        return _owned_path(self.collections_dir, f"{component}.json", owner=self.collections_dir, label="collection_path")

    def prompt_artifact_path(self, prompt_id: str) -> Path:
        prompt_component = safe_state_component(prompt_id, "prompt_id")
        prompt_dir = _owned_path(self.artifacts_dir, "prompts", owner=self.artifacts_dir, label="prompts_dir")
        return _owned_path(prompt_dir, f"{prompt_component}.txt", owner=prompt_dir, label="prompt_path")


def resolve_state_root(
    explicit: Path | str | None = None,
    *,
    env: Mapping[str, str] | None = None,
    default: Path = DEFAULT_STATE_DIR,
) -> Path:
    source_env = os.environ if env is None else env
    raw = explicit if explicit is not None else source_env.get(STATE_DIR_ENV)
    candidate = default if raw is None or str(raw).strip() == "" else Path(str(raw)).expanduser()
    return candidate.resolve()


def safe_state_component(value: str, label: str) -> str:
    component = str(value).strip()
    if not component:
        raise StateLayoutError(f"{label} must not be empty")
    if component in {".", ".."} or "/" in component or "\\" in component:
        raise StateLayoutError(f"{label} contains unsafe path separators or traversal")
    if not _SAFE_COMPONENT_RE.fullmatch(component):
        raise StateLayoutError(f"{label} contains unsafe characters")
    return component


def slug_state_component(value: str, *, fallback: str = "item") -> str:
    slug = "".join(char.lower() if char.isascii() and char.isalnum() else "-" for char in str(value)).strip("-")
    slug = re.sub(r"-+", "-", slug)
    if not slug:
        slug = fallback
    return safe_state_component(slug[:128], "slug")


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _owned_path(parent: Path, *parts: str, owner: Path, label: str) -> Path:
    path = parent.joinpath(*parts).resolve()
    if not is_relative_to(path, owner):
        raise StateLayoutError(f"{label} escapes owned state root")
    return path
