"""Hosted runtime toolchain diagnostics for managed Codex runs."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any, Mapping, Sequence

STATE_DIR_ENV = "DEV_CONTROL_PLANE_STATE_DIR"
RUNTIME_PROFILE_ENV = "DEV_CONTROL_PLANE_RUNTIME_PROFILE"
CODEX_BIN_ENV = "DEV_CONTROL_PLANE_CODEX_BIN"
TOOLCHAIN_BIN_DIR_ENV = "DEV_CONTROL_PLANE_TOOLCHAIN_BIN_DIR"
REQUIRE_GITHUB_CLI_ENV = "DEV_CONTROL_PLANE_REQUIRE_GITHUB_CLI"
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
HOSTED_PACKAGE_MANAGER_BASELINE_TOOLS = ("node", "npm", "corepack", "pnpm", "yarn")
UI_BROWSER_HINTS = (
    "browser smoke",
    "browser_smoke",
    "playwright",
    "chromium",
    "headless",
    "web-vitrina",
    "sheet-vitrina",
    "sheet_vitrina",
    "/sheet-vitrina",
    "operator ui",
    "browser/ui",
    "ui/browser",
    "frontend",
    "витрина",
    "интерфейс",
)
CODEX_AUTH_EXPIRED_MARKERS = (
    "refresh_token_reused",
    "token_expired",
    "expired",
    "invalid_grant",
    "reauth",
)
TRUTHY_VALUES = {"1", "true", "yes", "on"}


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
        dirs.append(runtime_root / "tools" / "bin")
    dirs.append(DEFAULT_RUNTIME_ROOT / "tools" / "bin")
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
    for key in (
        "LANG",
        "LC_ALL",
        "HOME",
        "CODEX_HOME",
        "XDG_CACHE_HOME",
        "PLAYWRIGHT_BROWSERS_PATH",
        "COREPACK_HOME",
        "NPM_CONFIG_PREFIX",
        STATE_DIR_ENV,
        RUNTIME_PROFILE_ENV,
        CODEX_BIN_ENV,
        TOOLCHAIN_BIN_DIR_ENV,
    ):
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
    require_github_cli: bool = False,
) -> dict[str, Any]:
    environment = env or os.environ
    requirements = inspect_target_requirements(workspace_path)
    github_required = require_github_cli or str(environment.get(REQUIRE_GITHUB_CLI_ENV) or "").strip().lower() in {"1", "true", "yes", "on"}
    tool_requirements = _tool_requirements(requirements, env=environment, require_github_cli=github_required)
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
        "production_lane_github_cli_required": github_required,
        "missing_required": list(missing_required),
        "warnings": list(warnings),
        "tools": [tool_status_to_dict(status) for status in statuses],
    }


def build_codex_auth_status(codex_bin: str | None, *, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Return sanitized Codex auth readiness without exposing auth material."""

    instructions = ["codex login", "codex login --device-auth"]
    if not codex_bin:
        return {
            "authenticated": False,
            "status": "missing",
            "blocker": "Codex CLI binary is missing.",
            "instructions": instructions,
            "headless_instruction": "Hosted/headless servers should use `codex login --device-auth` as the service user.",
        }
    try:
        result = subprocess.run(
            [codex_bin, "login", "status"],
            capture_output=True,
            text=True,
            check=False,
            timeout=8,
            env=runtime_command_env(env, git_prompt=False),
        )
    except subprocess.TimeoutExpired:
        return {
            "authenticated": False,
            "status": "unknown",
            "blocker": "Codex auth status check timed out.",
            "instructions": instructions,
            "headless_instruction": "Hosted/headless servers should use `codex login --device-auth` as the service user.",
        }
    except Exception:
        return {
            "authenticated": False,
            "status": "unknown",
            "blocker": "Codex auth status check failed.",
            "instructions": instructions,
            "headless_instruction": "Hosted/headless servers should use `codex login --device-auth` as the service user.",
        }
    text = f"{result.stdout or ''}\n{result.stderr or ''}".strip().lower()
    if result.returncode == 0 and "logged in" in text:
        return {
            "authenticated": True,
            "status": "authenticated",
            "blocker": None,
            "instructions": instructions,
            "headless_instruction": "Hosted/headless servers should use `codex login --device-auth` as the service user.",
        }
    expired = any(marker in text for marker in CODEX_AUTH_EXPIRED_MARKERS)
    status = "expired" if expired else "not_authenticated"
    blocker = (
        "Codex auth appears expired or invalid; run terminal-only `codex login --device-auth` as the service user."
        if expired
        else "Codex CLI is not authenticated; run terminal-only `codex login --device-auth` as the service user."
    )
    return {
        "authenticated": False,
        "status": status,
        "blocker": blocker,
        "instructions": instructions,
        "headless_instruction": "Hosted/headless servers should use `codex login --device-auth` as the service user.",
    }


def build_browser_readiness(
    *,
    env: Mapping[str, str] | None = None,
    launch: bool = False,
) -> dict[str, Any]:
    """Inspect Python Playwright/Chromium readiness with sanitized output."""

    environment = env or os.environ
    python = shutil.which("python3", path=runtime_path(environment))
    if not python:
        return {
            "status": "blocked",
            "playwright_import": "not_checked",
            "chromium": "not_checked",
            "launch_checked": bool(launch),
            "webcore_ui_browser_ready": False,
            "blocker": "python3 is missing; cannot inspect Playwright browser readiness.",
        }
    import_check = subprocess.run(
        [python, "-c", "import playwright; print('playwright import ok')"],
        capture_output=True,
        text=True,
        check=False,
        timeout=8,
        env=runtime_command_env(environment, git_prompt=False),
    )
    if import_check.returncode != 0:
        return {
            "status": "blocked",
            "playwright_import": "missing",
            "chromium": "not_checked",
            "launch_checked": bool(launch),
            "webcore_ui_browser_ready": False,
            "blocker": "Python Playwright package is missing from the hosted runtime.",
        }
    probe_script = r"""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

launch = __import__("os").environ.get("DEV_CONTROL_PLANE_BROWSER_LAUNCH_PROBE") == "1"
payload = {"chromium_executable": None, "executable_exists": False, "launch_ok": None}
with sync_playwright() as p:
    executable = p.chromium.executable_path
    payload["chromium_executable"] = executable
    payload["executable_exists"] = Path(executable).exists()
    if launch:
        browser = p.chromium.launch(headless=True)
        browser.close()
        payload["launch_ok"] = True
print(json.dumps(payload, sort_keys=True))
"""
    probe_env = runtime_command_env(environment, git_prompt=False)
    probe_env["DEV_CONTROL_PLANE_BROWSER_LAUNCH_PROBE"] = "1" if launch else "0"
    try:
        probe = subprocess.run(
            [python, "-c", probe_script],
            capture_output=True,
            text=True,
            check=False,
            timeout=20 if launch else 10,
            env=probe_env,
        )
    except subprocess.TimeoutExpired:
        return {
            "status": "blocked",
            "playwright_import": "ready",
            "chromium": "timeout",
            "launch_checked": bool(launch),
            "webcore_ui_browser_ready": False,
            "blocker": "Playwright Chromium readiness probe timed out.",
        }
    if probe.returncode != 0:
        return {
            "status": "blocked",
            "playwright_import": "ready",
            "chromium": "failed",
            "launch_checked": bool(launch),
            "webcore_ui_browser_ready": False,
            "blocker": "Playwright Chromium readiness probe failed under the service runtime.",
        }
    try:
        payload = json.loads((probe.stdout or "{}").strip().splitlines()[-1])
    except Exception:
        payload = {}
    executable = _sanitize_path_text(payload.get("chromium_executable"))
    executable_exists = bool(payload.get("executable_exists"))
    launch_ok = payload.get("launch_ok")
    ready = executable_exists and (not launch or launch_ok is True)
    return {
        "status": "ready" if ready else "blocked",
        "playwright_import": "ready",
        "chromium": "ready" if executable_exists else "missing",
        "chromium_executable": executable,
        "launch_checked": bool(launch),
        "launch_ok": launch_ok,
        "webcore_ui_browser_ready": ready,
        "blocker": None if ready else "Playwright Chromium executable is missing or cannot launch.",
    }


def requires_webcore_ui_browser_tools(
    *,
    target_id: str | None = None,
    prompt_text: str | None = None,
) -> bool:
    lowered = str(prompt_text or "").replace("_", "-").lower()
    if any(hint in lowered for hint in UI_BROWSER_HINTS):
        return True
    return str(target_id or "").strip() == "wb-core" and any(hint in lowered for hint in ("browser", "playwright", "chromium", "ui"))


def build_codex_runtime_parity_status(
    *,
    env: Mapping[str, str] | None = None,
    workspace_path: Path | None = None,
    codex_bin: str | None = None,
    target_id: str | None = None,
    base_commit: str | None = None,
    prompt_text: str | None = None,
    codex_model: str | None = None,
    codex_reasoning_effort: str | None = None,
    require_browser: bool | None = None,
    launch_browser: bool = False,
    codex_auth: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    environment = env or os.environ
    hosted = str(environment.get(RUNTIME_PROFILE_ENV) or "").strip().lower() == "hosted"
    require_auth = hosted or _truthy(environment.get("DEV_CONTROL_PLANE_REQUIRE_CODEX_AUTH"))
    browser_required = hosted if require_browser is None else bool(require_browser)
    browser_required = browser_required or requires_webcore_ui_browser_tools(target_id=target_id, prompt_text=prompt_text)
    package_baseline_required = hosted or browser_required or _truthy(environment.get("DEV_CONTROL_PLANE_REQUIRE_PACKAGE_MANAGER_BASELINE"))
    toolchain = build_toolchain_status(env=environment, workspace_path=workspace_path, codex_bin=codex_bin)
    tools = {str(item.get("name")): item for item in toolchain.get("tools", []) if isinstance(item, Mapping)}
    missing_baseline = [
        name for name in HOSTED_PACKAGE_MANAGER_BASELINE_TOOLS if package_baseline_required and not bool(tools.get(name, {}).get("available"))
    ]
    missing_required = _dedupe([*toolchain.get("missing_required", []), *missing_baseline])
    missing_optional = [
        str(item.get("name"))
        for item in toolchain.get("tools", [])
        if isinstance(item, Mapping) and not item.get("required") and not item.get("available") and str(item.get("name")) not in missing_required
    ]
    auth = dict(codex_auth or build_codex_auth_status(codex_bin, env=environment))
    browser = (
        build_browser_readiness(env=environment, launch=launch_browser and browser_required)
        if browser_required
        else {
            "status": "not_required",
            "playwright_import": "not_checked",
            "chromium": "not_checked",
            "launch_checked": False,
            "webcore_ui_browser_ready": False,
            "blocker": None,
        }
    )
    blockers: list[str] = []
    if missing_required:
        blockers.append(f"missing required runtime tools: {', '.join(missing_required)}")
    if require_auth and not bool(auth.get("authenticated")):
        blockers.append(str(auth.get("blocker") or "Codex CLI is not authenticated."))
    if browser_required and browser.get("status") != "ready":
        blockers.append(str(browser.get("blocker") or "WebCore UI browser readiness is blocked."))
    return {
        "status": "blocked" if blockers else "ready",
        "runtime_profile": "hosted" if hosted else str(environment.get(RUNTIME_PROFILE_ENV) or "local"),
        "target_id": target_id,
        "base_commit": base_commit,
        "codex": {
            "binary": _sanitize_path_text(codex_bin),
            "version": tools.get("codex", {}).get("version"),
            "model": codex_model,
            "reasoning_effort": codex_reasoning_effort,
            "auth_required": require_auth,
            "auth_status": auth.get("status"),
            "authenticated": bool(auth.get("authenticated")),
            "auth_blocker": auth.get("blocker") if require_auth and not bool(auth.get("authenticated")) else None,
            "instructions": auth.get("instructions"),
            "headless_instruction": auth.get("headless_instruction"),
        },
        "node_package_manager_baseline_required": package_baseline_required,
        "required_package_managers": list(HOSTED_PACKAGE_MANAGER_BASELINE_TOOLS),
        "missing_required": missing_required,
        "missing_optional": missing_optional,
        "webcore_ui_browser_required": browser_required,
        "webcore_ui_browser_ready": bool(browser.get("webcore_ui_browser_ready")),
        "browser": browser,
        "tool_versions": {
            name: {
                "available": bool(tools.get(name, {}).get("available")),
                "version": tools.get(name, {}).get("version"),
                "source": tools.get(name, {}).get("source"),
                "path": _sanitize_path_text(tools.get(name, {}).get("path")),
            }
            for name in ("codex", "node", "npm", "corepack", "pnpm", "yarn", "python3", "pip", "git", "gh")
        },
        "path_sanitized": _sanitize_path_text(runtime_path(environment)),
        "runtime_tool_dirs": [_sanitize_path_text(path) for path in toolchain.get("runtime_tool_dirs", [])],
        "exact_blocker": "; ".join(blockers) if blockers else None,
    }


def build_environment_parity_artifact(
    *,
    env: Mapping[str, str] | None = None,
    workspace_path: Path | None,
    codex_bin: str | None,
    target_id: str,
    base_commit: str,
    prompt_text: str | None,
    codex_model: str | None,
    codex_reasoning_effort: str | None,
    launch_browser: bool = False,
) -> dict[str, Any]:
    parity = build_codex_runtime_parity_status(
        env=env,
        workspace_path=workspace_path,
        codex_bin=codex_bin,
        target_id=target_id,
        base_commit=base_commit,
        prompt_text=prompt_text,
        codex_model=codex_model,
        codex_reasoning_effort=codex_reasoning_effort,
        require_browser=requires_webcore_ui_browser_tools(target_id=target_id, prompt_text=prompt_text),
        launch_browser=launch_browser,
    )
    return {
        "schema_version": 1,
        "status": parity.get("status"),
        "target_id": target_id,
        "base_commit": base_commit,
        "runtime_profile": parity.get("runtime_profile"),
        "codex": parity.get("codex"),
        "tool_versions": parity.get("tool_versions"),
        "node_package_manager_baseline_required": parity.get("node_package_manager_baseline_required"),
        "webcore_ui_browser_required": parity.get("webcore_ui_browser_required"),
        "webcore_ui_browser_ready": parity.get("webcore_ui_browser_ready"),
        "browser": parity.get("browser"),
        "missing_required": parity.get("missing_required"),
        "missing_optional": parity.get("missing_optional"),
        "path_sanitized": parity.get("path_sanitized"),
        "runtime_tool_dirs": parity.get("runtime_tool_dirs"),
        "exact_blocker": parity.get("exact_blocker"),
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


def _tool_requirements(target_requirements: Mapping[str, Any], *, env: Mapping[str, str], require_github_cli: bool = False) -> tuple[ToolRequirement, ...]:
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
    if require_github_cli:
        requirements.append(ToolRequirement("gh", True, "required for wb-core production-lane PR/merge/delete-branch gates"))
        optional_names.discard("gh")
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
    configured_codex = str(env.get(CODEX_BIN_ENV) or "").strip()
    if configured_codex:
        try:
            runtime_root = DEFAULT_RUNTIME_ROOT.resolve()
            if tool_path == Path(configured_codex).resolve() and tool_path.is_relative_to(runtime_root):
                return "runtime-local"
        except OSError:
            pass
    return "system"


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in TRUTHY_VALUES


def _sanitize_path_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    if not text:
        return text
    parts = []
    for item in text.split(os.pathsep):
        lowered = item.lower()
        if any(marker in lowered for marker in ("secret", "token", "auth", ".codex", ".ssh")):
            parts.append("[redacted-path]")
        else:
            parts.append(item)
    return os.pathsep.join(parts)


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
