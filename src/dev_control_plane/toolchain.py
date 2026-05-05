"""Hosted runtime toolchain diagnostics for managed Codex runs."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any, Mapping, Sequence

STATE_DIR_ENV = "DEV_CONTROL_PLANE_STATE_DIR"
RUNTIME_PROFILE_ENV = "DEV_CONTROL_PLANE_RUNTIME_PROFILE"
CODEX_BIN_ENV = "DEV_CONTROL_PLANE_CODEX_BIN"
TOOLCHAIN_BIN_DIR_ENV = "DEV_CONTROL_PLANE_TOOLCHAIN_BIN_DIR"
DEFAULT_RUNTIME_ROOT = Path("/opt/dev-control-plane-runtime")

LOCAL_REQUIRED_TOOLS = (
    "git",
    "rg",
    "python3",
    "codex",
)
HOSTED_REQUIRED_TOOLS = (
    *LOCAL_REQUIRED_TOOLS,
    "python3-venv",
    "pip",
    "jq",
    "bash",
    "sh",
    "sed",
    "awk",
    "grep",
    "find",
    "xargs",
    "tar",
    "gzip",
    "unzip",
    "timeout",
)
BASE_OPTIONAL_TOOLS = (
    "node",
    "npm",
    "corepack",
    "pnpm",
    "yarn",
    "rsync",
    "ssh",
    "gh",
)
JS_MANIFESTS = ("package.json", "pnpm-lock.yaml", "yarn.lock", "package-lock.json")
PYTHON_MANIFESTS = ("pyproject.toml", "requirements.txt", "pytest.ini", "setup.cfg", "tox.ini")


@dataclass(frozen=True)
class ToolRequirement:
    name: str
    required: bool
    reason: str


@dataclass(frozen=True)
class ToolStatus:
    name: str
    required: bool
    available: bool
    path: str | None
    version: str | None
    source: str
    status: str
    reason: str | None


def runtime_tool_bin_dirs(env: Mapping[str, str] | None = None) -> tuple[Path, ...]:
    environment = env or os.environ
    dirs: list[Path] = []
    explicit = str(environment.get(TOOLCHAIN_BIN_DIR_ENV) or "").strip()
    if explicit:
        dirs.append(Path(explicit).expanduser())
    state_dir = str(environment.get(STATE_DIR_ENV) or "").strip()
    if state_dir:
        state_path = Path(state_dir).expanduser()
        runtime_root = state_path.parent if state_path.name == "state" else state_path
        dirs.extend((runtime_root / "tools" / "bin", runtime_root / "tools" / "codex" / "bin"))
    codex_bin = str(environment.get(CODEX_BIN_ENV) or "").strip()
    if codex_bin:
        dirs.append(Path(codex_bin).expanduser().parent)
    dirs.extend((DEFAULT_RUNTIME_ROOT / "tools" / "bin", DEFAULT_RUNTIME_ROOT / "tools" / "codex" / "bin"))
    return _existing_unique_dirs(dirs)


def runtime_path(env: Mapping[str, str] | None = None) -> str:
    environment = env or os.environ
    base_path = str(environment.get("PATH") or os.defpath)
    parts = [str(path) for path in runtime_tool_bin_dirs(environment)]
    parts.extend(part for part in base_path.split(os.pathsep) if part)
    return os.pathsep.join(_dedupe(parts))


def runtime_command_env(env: Mapping[str, str] | None = None, *, git_prompt: bool = True) -> dict[str, str]:
    environment = env or os.environ
    result: dict[str, str] = {}
    for key in ("LANG", "LC_ALL", "HOME", "CODEX_HOME", STATE_DIR_ENV, CODEX_BIN_ENV):
        value = environment.get(key)
        if value:
            result[key] = str(value)
    result["PATH"] = runtime_path(environment)
    if git_prompt:
        result["GIT_TERMINAL_PROMPT"] = "0"
    return result


def inspect_target_requirements(workspace_path: Path | None = None) -> dict[str, Any]:
    manifests: list[str] = []
    if workspace_path and workspace_path.exists():
        root = workspace_path.resolve()
        for dirpath, dirnames, filenames in os.walk(root):
            current = Path(dirpath)
            rel = current.relative_to(root)
            depth = len(rel.parts)
            dirnames[:] = [
                item
                for item in dirnames
                if item not in {".git", "__pycache__", "node_modules", ".venv", "venv", "wb_core_docs_master"}
                and depth < 4
            ]
            for filename in filenames:
                if filename in JS_MANIFESTS or filename in PYTHON_MANIFESTS or filename == "Makefile":
                    path = str((current / filename).relative_to(root))
                    manifests.append(path)
    js_manifests = tuple(sorted(path for path in manifests if Path(path).name in JS_MANIFESTS))
    python_manifests = tuple(sorted(path for path in manifests if Path(path).name in PYTHON_MANIFESTS))
    package_managers: list[str] = []
    names = {Path(path).name for path in js_manifests}
    if "pnpm-lock.yaml" in names:
        package_managers.append("pnpm")
    if "yarn.lock" in names:
        package_managers.append("yarn")
    if "package-lock.json" in names:
        package_managers.append("npm")
    if "package.json" in names and not package_managers:
        package_managers.append("npm")
    return {
        "manifests": tuple(sorted(manifests)),
        "js_manifests": js_manifests,
        "python_manifests": python_manifests,
        "requires_node": bool(js_manifests),
        "required_package_managers": tuple(package_managers),
        "requires_python_project_tools": bool(python_manifests),
    }


def build_toolchain_status(
    *,
    env: Mapping[str, str] | None = None,
    workspace_path: Path | None = None,
    codex_bin: str | None = None,
) -> dict[str, Any]:
    environment = env or os.environ
    requirements = inspect_target_requirements(workspace_path)
    tool_requirements = _tool_requirements(requirements, env=environment)
    statuses = [
        _detect_tool(requirement, env=environment, codex_bin=codex_bin)
        for requirement in tool_requirements
    ]
    missing_required = tuple(status.name for status in statuses if status.required and not status.available)
    warnings = tuple(
        f"optional tool missing: {status.name}"
        for status in statuses
        if not status.required and not status.available
    )
    return {
        "status": "blocked" if missing_required else "ready",
        "path": runtime_path(environment),
        "runtime_tool_dirs": [str(path) for path in runtime_tool_bin_dirs(environment)],
        "workspace_path": str(workspace_path) if workspace_path else None,
        "target_requirements": requirements,
        "missing_required": list(missing_required),
        "warnings": list(warnings),
        "tools": [tool_status_to_dict(status) for status in statuses],
    }


def tool_status_to_dict(status: ToolStatus) -> dict[str, Any]:
    return {
        "name": status.name,
        "required": status.required,
        "available": status.available,
        "path": status.path,
        "version": status.version,
        "source": status.source,
        "status": status.status,
        "reason": status.reason,
    }


def _tool_requirements(target_requirements: Mapping[str, Any], *, env: Mapping[str, str]) -> tuple[ToolRequirement, ...]:
    hosted = str(env.get(RUNTIME_PROFILE_ENV) or "").strip().lower() == "hosted"
    required_tools = HOSTED_REQUIRED_TOOLS if hosted else LOCAL_REQUIRED_TOOLS
    requirements: list[ToolRequirement] = [
        ToolRequirement(name, True, "required for hosted managed-clone Codex runtime")
        for name in required_tools
    ]
    optional_names = set(BASE_OPTIONAL_TOOLS)
    if target_requirements.get("requires_node"):
        requirements.append(ToolRequirement("node", True, "target workspace contains JavaScript package manifests"))
        optional_names.discard("node")
    for manager in target_requirements.get("required_package_managers", ()):
        requirements.append(ToolRequirement(str(manager), True, "target workspace package manager lockfile"))
        optional_names.discard(str(manager))
    requirements.extend(ToolRequirement(name, False, "optional for future target workflows") for name in sorted(optional_names))
    return tuple(_dedupe_requirements(requirements))


def _detect_tool(requirement: ToolRequirement, *, env: Mapping[str, str], codex_bin: str | None) -> ToolStatus:
    name = requirement.name
    path = _tool_path(name, env=env, codex_bin=codex_bin)
    if not path:
        return ToolStatus(
            name=name,
            required=requirement.required,
            available=False,
            path=None,
            version=None,
            source="missing",
            status="blocked" if requirement.required else "warning",
            reason=f"missing required tool: {name}" if requirement.required else f"optional tool missing: {name}",
        )
    version = _tool_version(name, path, env)
    return ToolStatus(
        name=name,
        required=requirement.required,
        available=True,
        path=path,
        version=version,
        source=_tool_source(path, env),
        status="ready",
        reason=requirement.reason,
    )


def _tool_path(name: str, *, env: Mapping[str, str], codex_bin: str | None) -> str | None:
    if name == "codex":
        configured = str(codex_bin or env.get(CODEX_BIN_ENV) or "").strip()
        if configured and (Path(configured).exists() or shutil.which(configured, path=runtime_path(env))):
            return configured
    if name == "python3-venv":
        python = shutil.which("python3", path=runtime_path(env))
        return python if python and _python_venv_available(python, env) else None
    if name == "pip":
        return shutil.which("pip", path=runtime_path(env)) or shutil.which("pip3", path=runtime_path(env))
    return shutil.which(name, path=runtime_path(env))


def _tool_version(name: str, path: str, env: Mapping[str, str]) -> str | None:
    if name == "python3-venv":
        return "available"
    command = _version_command(name, path)
    if not command:
        return None
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
            env=runtime_command_env(env),
        )
    except Exception:
        return None
    text = "\n".join(part.strip() for part in (completed.stdout, completed.stderr) if part and part.strip())
    return text.splitlines()[0][:200] if text else None


def _version_command(name: str, path: str) -> Sequence[str] | None:
    if name in {"ssh"}:
        return (path, "-V")
    if name in {"sh"}:
        return (path, "-c", "echo sh available")
    if name in {"unzip"}:
        return (path, "-v")
    return (path, "--version")


def _python_venv_available(python_path: str, env: Mapping[str, str]) -> bool:
    try:
        completed = subprocess.run(
            (python_path, "-m", "venv", "--help"),
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
            env=runtime_command_env(env),
        )
    except Exception:
        return False
    return completed.returncode == 0


def _tool_source(path: str, env: Mapping[str, str]) -> str:
    tool_path = Path(path).resolve()
    for runtime_dir in runtime_tool_bin_dirs(env):
        try:
            if tool_path.is_relative_to(runtime_dir.resolve()):
                return "runtime-local"
        except OSError:
            continue
    return "system"


def _existing_unique_dirs(paths: Sequence[Path]) -> tuple[Path, ...]:
    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        key = str(resolved)
        if key in seen or not resolved.exists():
            continue
        seen.add(key)
        unique.append(resolved)
    return tuple(unique)


def _dedupe(values: Sequence[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _dedupe_requirements(requirements: Sequence[ToolRequirement]) -> tuple[ToolRequirement, ...]:
    result: list[ToolRequirement] = []
    seen: set[str] = set()
    for requirement in requirements:
        if requirement.name in seen:
            continue
        seen.add(requirement.name)
        result.append(requirement)
    return tuple(result)
