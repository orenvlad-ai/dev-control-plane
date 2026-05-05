"""Local secret storage for Development Control Plane.

The store is intentionally outside the repository. It is a local operator
convenience for development credentials, not a production secret manager.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
from typing import Any, Mapping

from dev_control_plane.runtime_config import explicit_runtime_config_exists, load_runtime_config

SECRET_HOME_ENV = "DEV_CONTROL_PLANE_SECRET_HOME"
DEFAULT_SECRET_DIRNAME = ".dev-control-plane"
SECRET_FILE_NAME = "secrets.json"
DEFAULT_OPENAI_REASONING_EFFORT = "xhigh"
OPENAI_REASONING_EFFORT_ENV = "CURATOR_COCKPIT_OPENAI_REASONING_EFFORT"
OPENAI_REASONING_EFFORT_VALUES = ("none", "low", "medium", "high", "xhigh")


@dataclass(frozen=True)
class OpenAICredentials:
    api_key: str
    model: str
    reasoning_effort: str
    source: str


def get_secret_store_path(env: Mapping[str, str] | None = None) -> Path:
    environment = env if env is not None else os.environ
    override = environment.get(SECRET_HOME_ENV)
    if override:
        return Path(override).expanduser().resolve() / SECRET_FILE_NAME
    return Path.home().resolve() / DEFAULT_SECRET_DIRNAME / SECRET_FILE_NAME


def set_openai_credentials(
    api_key: str,
    model: str,
    reasoning_effort: str = DEFAULT_OPENAI_REASONING_EFFORT,
) -> dict[str, Any]:
    api_key = str(api_key or "").strip()
    model = str(model or "").strip()
    reasoning_effort = _normalize_reasoning_effort(reasoning_effort, strict=True)
    if not api_key:
        raise SecretStoreError("OpenAI API key is required")
    if not model:
        raise SecretStoreError("OpenAI model is required")
    path = get_secret_store_path()
    if _is_inside_repo(path):
        raise SecretStoreError(f"refusing to store secrets inside repository: {path}")
    payload = _read_secret_payload()
    payload["openai"] = {"api_key": api_key, "model": model, "reasoning_effort": reasoning_effort}
    _write_secret_payload(payload)
    return {
        "status": "saved",
        "store": _display_path(path),
        "model": model,
        "reasoning_effort": reasoning_effort,
        "key_saved": True,
    }


def get_openai_credentials(env: Mapping[str, str] | None = None) -> OpenAICredentials | None:
    environment = env if env is not None else os.environ
    runtime_config = load_runtime_config(env=environment)
    runtime_override = explicit_runtime_config_exists(env=environment)
    env_has_api_key = "OPENAI_API_KEY" in environment and bool(str(environment.get("OPENAI_API_KEY") or "").strip())
    env_has_model = "CURATOR_COCKPIT_OPENAI_MODEL" in environment and bool(
        str(environment.get("CURATOR_COCKPIT_OPENAI_MODEL") or "").strip()
    )
    if env_has_api_key or env_has_model:
        env_model = str(environment.get("CURATOR_COCKPIT_OPENAI_MODEL") or "").strip()
        model = env_model or (runtime_config.openai.model if runtime_override else "")
        effort = environment.get(OPENAI_REASONING_EFFORT_ENV) or (
            runtime_config.openai.reasoning_effort if runtime_override else None
        )
        return OpenAICredentials(
            api_key=str(environment.get("OPENAI_API_KEY") or "").strip(),
            model=model,
            reasoning_effort=_normalize_reasoning_effort(effort),
            source="runtime_config+env" if runtime_override and not env_has_model else "env",
        )

    payload = _read_secret_payload(env=environment)
    openai = payload.get("openai")
    if not isinstance(openai, Mapping):
        return None
    api_key = str(openai.get("api_key") or "").strip()
    model = str(openai.get("model") or "").strip()
    if runtime_override:
        model = runtime_config.openai.model
    reasoning_effort = _normalize_reasoning_effort(
        runtime_config.openai.reasoning_effort if runtime_override else openai.get("reasoning_effort")
    )
    if not api_key and not model:
        return None
    source = "runtime_config+file" if runtime_override else "file"
    return OpenAICredentials(api_key=api_key, model=model, reasoning_effort=reasoning_effort, source=source)


def get_openai_status(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    credentials = get_openai_credentials(env=env)
    path = get_secret_store_path(env=env)
    if credentials is None:
        return {
            "configured": False,
            "source": "missing",
            "model": None,
            "reasoning_effort": None,
            "store": _display_path(path),
            "store_exists": path.exists(),
        }
    return {
        "configured": bool(credentials.api_key and credentials.model),
        "source": credentials.source,
        "model": credentials.model or None,
        "reasoning_effort": credentials.reasoning_effort or None,
        "store": _display_path(path),
        "store_exists": path.exists(),
    }


def delete_openai_credentials() -> dict[str, Any]:
    payload = _read_secret_payload()
    had_openai = isinstance(payload.get("openai"), Mapping)
    payload.pop("openai", None)
    path = get_secret_store_path()
    if payload:
        _write_secret_payload(payload)
    elif path.exists():
        path.unlink()
    return {
        "status": "deleted" if had_openai else "missing",
        "store": _display_path(path),
        "openai_deleted": had_openai,
    }


def mask_secret(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 8:
        return "***"
    return f"{value[:3]}...{value[-4:]}"


def openai_credentials_to_dict(credentials: OpenAICredentials) -> dict[str, Any]:
    payload = asdict(credentials)
    payload.pop("api_key", None)
    return payload


class SecretStoreError(RuntimeError):
    """Raised when local secret storage cannot continue safely."""


def _normalize_reasoning_effort(value: Any, *, strict: bool = False) -> str:
    effort = str(value or "").strip().lower() or DEFAULT_OPENAI_REASONING_EFFORT
    if effort not in OPENAI_REASONING_EFFORT_VALUES:
        if not strict:
            return DEFAULT_OPENAI_REASONING_EFFORT
        raise SecretStoreError(
            f"unsupported OpenAI reasoning effort {effort!r}; expected one of {', '.join(OPENAI_REASONING_EFFORT_VALUES)}"
        )
    return effort


def _read_secret_payload(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    path = get_secret_store_path(env=env)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    return payload


def _write_secret_payload(payload: Mapping[str, Any]) -> None:
    path = get_secret_store_path()
    directory = path.parent
    directory.mkdir(parents=True, exist_ok=True)
    _chmod_best_effort(directory, 0o700)
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(encoded)
    finally:
        _chmod_best_effort(path, 0o600)


def _chmod_best_effort(path: Path, mode: int) -> None:
    try:
        path.chmod(mode)
    except OSError:
        return


def _display_path(path: Path) -> str:
    home = Path.home().resolve()
    try:
        rel = path.resolve().relative_to(home)
    except ValueError:
        return str(path)
    return f"~/{rel.as_posix()}"


def _is_inside_repo(path: Path) -> bool:
    repo_root = Path(__file__).resolve().parents[2]
    try:
        path.resolve().relative_to(repo_root)
        return True
    except ValueError:
        return False
