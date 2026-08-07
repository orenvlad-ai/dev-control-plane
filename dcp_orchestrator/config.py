"""DCP-authored product identity and filesystem boundaries."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


PRODUCT_NAME = "DCP Orchestrator"
BUNDLE_ID = "pro.devcontrol.dcp-orchestrator"
PROCESS_ID = "dcp-orchestrator"
SERVICE_ID = "pro.devcontrol.dcp-orchestrator.lab"
IPC_NAMESPACE = "dcp-orchestrator"
ENV_PREFIX = "DCP_ORCHESTRATOR_"
TASK_ID = "dcp-lab-canary-001"
CANONICAL_PROMPT = "Запусти изолированный DCP canary"


class ConfigurationError(RuntimeError):
    """A configured path would weaken the DCP namespace boundary."""


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


@dataclass(frozen=True)
class RuntimePaths:
    app_root: Path
    state: Path
    data: Path
    cache: Path
    logs: Path
    lab: Path
    repository: Path
    worktrees: Path
    records: Path
    attempts: Path
    locks: Path
    source_root: Path

    @classmethod
    def from_environment(cls) -> "RuntimePaths":
        home = Path.home().resolve()
        source_root = Path(__file__).resolve().parents[1]
        override = os.environ.get(f"{ENV_PREFIX}ROOT")
        if override:
            candidate = Path(override).expanduser()
            if not candidate.is_absolute():
                raise ConfigurationError(f"{ENV_PREFIX}ROOT must be absolute")
            app_root = candidate.resolve()
        else:
            app_root = home / "Library" / "Application Support" / PRODUCT_NAME

        if app_root == source_root or _inside(app_root, source_root):
            raise ConfigurationError("runtime root must be outside the source repository")

        cache = home / "Library" / "Caches" / BUNDLE_ID
        logs = home / "Library" / "Logs" / PRODUCT_NAME
        if override:
            # Test/evidence overrides remain wholly inside their isolated root.
            cache = app_root / "cache"
            logs = app_root / "logs"

        data = app_root / "data"
        state = app_root / "state"
        lab = data / "lab"
        return cls(
            app_root=app_root,
            state=state,
            data=data,
            cache=cache,
            logs=logs,
            lab=lab,
            repository=lab / "repository",
            worktrees=lab / "worktrees",
            records=lab / "records",
            attempts=state / "attempts",
            locks=state / "locks",
            source_root=source_root,
        )

    def create(self) -> None:
        for path in (
            self.app_root,
            self.state,
            self.data,
            self.cache,
            self.logs,
            self.lab,
            self.worktrees,
            self.records,
            self.attempts,
            self.locks,
        ):
            path.mkdir(parents=True, exist_ok=True, mode=0o700)
            path.chmod(0o700)

    def assert_lab_containment(self, path: Path) -> Path:
        resolved = path.resolve()
        if not _inside(resolved, self.lab.resolve()):
            raise ConfigurationError("path escapes the DCP laboratory root")
        if _inside(resolved, self.source_root):
            raise ConfigurationError("laboratory path overlaps the source repository")
        return resolved

    def public_roots(self) -> dict[str, str]:
        return {
            "state": str(self.state),
            "data": str(self.data),
            "cache": str(self.cache),
            "logs": str(self.logs),
            "lab": str(self.lab),
        }
