"""Runtime model and sandbox configuration stored outside the repo."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any, Mapping

STATE_DIR_ENV = "DEV_CONTROL_PLANE_STATE_DIR"
RUNTIME_PROFILE_ENV = "DEV_CONTROL_PLANE_RUNTIME_PROFILE"
RUNTIME_CONFIG_DIR_ENV = "DEV_CONTROL_PLANE_RUNTIME_CONFIG_DIR"
RUNTIME_CONFIG_FILE = "runtime_config.json"
HOSTED_PROFILE = "hosted"

DEFAULT_OPENAI_MODEL = "gpt-5.5"
DEFAULT_CODEX_MODEL = "gpt-5.5"
DEFAULT_REASONING_EFFORT = "xhigh"
DEFAULT_LOCAL_CODEX_SANDBOX = "workspace-write"
DEFAULT_HOSTED_CODEX_SANDBOX = "danger-full-access"

REASONING_OPTIONS = ("low", "medium", "high", "xhigh")
CODEX_SANDBOX_OPTIONS = ("workspace-write", "danger-full-access")

OPENAI_MODEL_OPTIONS = (
    {
        "id": "gpt-5.5",
        "label": "GPT-5.5",
        "source": "confirmed by Codex CLI 0.128.0 debug catalog as supported_in_api",
    },
    {
        "id": "gpt-5.4",
        "label": "GPT-5.4",
        "source": "confirmed by Codex CLI 0.128.0 debug catalog as supported_in_api",
    },
    {
        "id": "gpt-5.4-mini",
        "label": "GPT-5.4 Mini",
        "source": "confirmed by Codex CLI 0.128.0 debug catalog as supported_in_api",
    },
    {
        "id": "gpt-5.2",
        "label": "GPT-5.2",
        "source": "confirmed by Codex CLI 0.128.0 debug catalog as supported_in_api",
    },
)

CODEX_MODEL_OPTIONS = (
    {"id": "gpt-5.5", "label": "GPT-5.5", "source": "confirmed by Codex CLI 0.128.0 debug catalog"},
    {"id": "gpt-5.4", "label": "GPT-5.4", "source": "confirmed by Codex CLI 0.128.0 debug catalog"},
    {"id": "gpt-5.4-mini", "label": "GPT-5.4 Mini", "source": "confirmed by Codex CLI 0.128.0 debug catalog"},
    {"id": "gpt-5.3-codex", "label": "GPT-5.3 Codex", "source": "confirmed by Codex CLI 0.128.0 debug catalog"},
    {
        "id": "gpt-5.3-codex-spark",
        "label": "GPT-5.3 Codex Spark",
        "source": "confirmed by Codex CLI 0.128.0 debug catalog",
    },
)

@dataclass(frozen=True)
class RuntimeSettings:
    model: str
    reasoning_effort: str
    source: str


@dataclass(frozen=True)
class CodexRuntimeSettings(RuntimeSettings):
    sandbox_mode: str
    sandbox_source: str


@dataclass(frozen=True)
class RuntimeConfig:
    openai: RuntimeSettings
    codex: CodexRuntimeSettings
    path: Path
    exists: bool
    warnings: tuple[str, ...]


class RuntimeConfigError(ValueError):
    pass


def load_runtime_config(env: Mapping[str, str] | None = None) -> RuntimeConfig:
    environment = env or os.environ
    path = runtime_config_path(environment)
    payload, warnings = _read_payload(path)
    runtime_profile = str(environment.get(RUNTIME_PROFILE_ENV) or "").strip().lower()
    hosted = runtime_profile == HOSTED_PROFILE
    default_sandbox = DEFAULT_HOSTED_CODEX_SANDBOX if hosted else DEFAULT_LOCAL_CODEX_SANDBOX
    openai_payload = payload.get("openai") if isinstance(payload.get("openai"), Mapping) else {}
    codex_payload = payload.get("codex") if isinstance(payload.get("codex"), Mapping) else {}
    return RuntimeConfig(
        openai=RuntimeSettings(
            model=_validated_model(
                openai_payload.get("model"),
                allowed=_model_ids(OPENAI_MODEL_OPTIONS),
                default=DEFAULT_OPENAI_MODEL,
                label="OpenAI model",
            ),
            reasoning_effort=_validated_choice(
                openai_payload.get("reasoning_effort"),
                allowed=REASONING_OPTIONS,
                default=DEFAULT_REASONING_EFFORT,
                label="OpenAI reasoning effort",
            ),
            source="runtime_config" if path.exists() and openai_payload else "default",
        ),
        codex=CodexRuntimeSettings(
            model=_validated_model(
                codex_payload.get("model"),
                allowed=_model_ids(CODEX_MODEL_OPTIONS),
                default=DEFAULT_CODEX_MODEL,
                label="Codex model",
            ),
            reasoning_effort=_validated_choice(
                codex_payload.get("reasoning_effort"),
                allowed=REASONING_OPTIONS,
                default=DEFAULT_REASONING_EFFORT,
                label="Codex reasoning effort",
            ),
            source="runtime_config" if path.exists() and codex_payload else "default",
            sandbox_mode=_validated_choice(
                codex_payload.get("sandbox_mode"),
                allowed=CODEX_SANDBOX_OPTIONS,
                default=default_sandbox,
                label="Codex sandbox mode",
            ),
            sandbox_source="runtime_config" if path.exists() and codex_payload.get("sandbox_mode") else (
                "hosted_default" if hosted else "local_default"
            ),
        ),
        path=path,
        exists=path.exists(),
        warnings=tuple(warnings),
    )


def save_runtime_config(payload: Mapping[str, Any], env: Mapping[str, str] | None = None) -> RuntimeConfig:
    current = load_runtime_config(env=env)
    openai_payload = payload.get("openai") if isinstance(payload.get("openai"), Mapping) else {}
    codex_payload = payload.get("codex") if isinstance(payload.get("codex"), Mapping) else {}
    saved = {
        "openai": {
            "model": _validated_model(
                openai_payload.get("model", current.openai.model),
                allowed=_model_ids(OPENAI_MODEL_OPTIONS),
                default=current.openai.model,
                label="OpenAI model",
                strict=True,
            ),
            "reasoning_effort": _validated_choice(
                openai_payload.get("reasoning_effort", current.openai.reasoning_effort),
                allowed=REASONING_OPTIONS,
                default=current.openai.reasoning_effort,
                label="OpenAI reasoning effort",
                strict=True,
            ),
        },
        "codex": {
            "model": _validated_model(
                codex_payload.get("model", current.codex.model),
                allowed=_model_ids(CODEX_MODEL_OPTIONS),
                default=current.codex.model,
                label="Codex model",
                strict=True,
            ),
            "reasoning_effort": _validated_choice(
                codex_payload.get("reasoning_effort", current.codex.reasoning_effort),
                allowed=REASONING_OPTIONS,
                default=current.codex.reasoning_effort,
                label="Codex reasoning effort",
                strict=True,
            ),
            "sandbox_mode": _validated_choice(
                codex_payload.get("sandbox_mode", current.codex.sandbox_mode),
                allowed=CODEX_SANDBOX_OPTIONS,
                default=current.codex.sandbox_mode,
                label="Codex sandbox mode",
                strict=True,
            ),
        },
    }
    path = runtime_config_path(env or os.environ)
    if _is_inside_repo(path):
        raise RuntimeConfigError(f"refusing to store runtime config inside repository: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    _chmod_best_effort(path.parent, 0o700)
    encoded = json.dumps(saved, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(encoded)
    finally:
        _chmod_best_effort(path, 0o600)
    return load_runtime_config(env=env)


def runtime_config_public_dict(config: RuntimeConfig | None = None, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    config = config or load_runtime_config(env=env)
    return {
        "status": "ok",
        "path": _display_path(config.path),
        "exists": config.exists,
        "openai": {
            "model": config.openai.model,
            "reasoning_effort": config.openai.reasoning_effort,
            "source": config.openai.source,
        },
        "codex": {
            "model": config.codex.model,
            "reasoning_effort": config.codex.reasoning_effort,
            "source": config.codex.source,
            "sandbox_mode": config.codex.sandbox_mode,
            "sandbox_source": config.codex.sandbox_source,
            "sandbox_warning": _sandbox_warning(config.codex.sandbox_mode),
        },
        "options": {
            "openai_models": list(OPENAI_MODEL_OPTIONS),
            "codex_models": list(CODEX_MODEL_OPTIONS),
            "reasoning_efforts": list(REASONING_OPTIONS),
            "codex_sandbox_modes": list(CODEX_SANDBOX_OPTIONS),
        },
        "warnings": list(config.warnings),
    }


def runtime_config_path(env: Mapping[str, str]) -> Path:
    override = str(env.get(RUNTIME_CONFIG_DIR_ENV) or "").strip()
    if override:
        return Path(override).expanduser().resolve() / RUNTIME_CONFIG_FILE
    state_dir = str(env.get(STATE_DIR_ENV) or "").strip()
    if state_dir:
        state = Path(state_dir).expanduser().resolve()
        if state.name == "state":
            return state.parent / "config" / RUNTIME_CONFIG_FILE
    return Path.home().resolve() / ".dev-control-plane" / "config" / RUNTIME_CONFIG_FILE


def explicit_runtime_config_exists(env: Mapping[str, str] | None = None) -> bool:
    return runtime_config_path(env or os.environ).exists()


def _read_payload(path: Path) -> tuple[dict[str, Any], list[str]]:
    if not path.exists():
        return {}, []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}, ["runtime config parse failed; using defaults"]
    if not isinstance(payload, dict):
        return {}, ["runtime config root is not an object; using defaults"]
    return payload, []


def _validated_model(value: Any, *, allowed: set[str], default: str, label: str, strict: bool = False) -> str:
    text = str(value or "").strip() or default
    if text not in allowed:
        if strict:
            raise RuntimeConfigError(f"unsupported {label}: {text}")
        return default
    return text


def _validated_choice(value: Any, *, allowed: tuple[str, ...], default: str, label: str, strict: bool = False) -> str:
    text = str(value or "").strip().lower() or default
    if text not in allowed:
        if strict:
            raise RuntimeConfigError(f"unsupported {label}: {text}")
        return default
    return text


def _model_ids(options: tuple[Mapping[str, str], ...]) -> set[str]:
    return {str(item["id"]) for item in options}


def _sandbox_warning(mode: str) -> str | None:
    if mode != "danger-full-access":
        return None
    return (
        "Codex CLI sandbox uses danger-full-access only inside the managed clone because hosted "
        "bubblewrap workspace-write fails before shell commands; DCP forbidden paths/actions, "
        "original-target unchanged and no PR/deploy gates remain active."
    )


def _display_path(path: Path) -> str:
    home = Path.home().resolve()
    try:
        rel = path.resolve().relative_to(home)
    except ValueError:
        return str(path)
    return f"~/{rel.as_posix()}"


def _chmod_best_effort(path: Path, mode: int) -> None:
    try:
        path.chmod(mode)
    except OSError:
        return


def _is_inside_repo(path: Path) -> bool:
    repo_root = Path(__file__).resolve().parents[2]
    try:
        path.resolve().relative_to(repo_root)
        return True
    except ValueError:
        return False
