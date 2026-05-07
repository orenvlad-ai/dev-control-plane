"""Local secret storage for Development Control Plane.

The store is intentionally outside the repository. It is a local operator
convenience for development credentials, not a production secret manager.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets as token_secrets
from typing import Any, Mapping

from dev_control_plane.runtime_config import explicit_runtime_config_exists, load_runtime_config

SECRET_HOME_ENV = "DEV_CONTROL_PLANE_SECRET_HOME"
DEFAULT_SECRET_DIRNAME = ".dev-control-plane"
SECRET_FILE_NAME = "secrets.json"
DEFAULT_OPENAI_REASONING_EFFORT = "xhigh"
OPENAI_REASONING_EFFORT_ENV = "CURATOR_COCKPIT_OPENAI_REASONING_EFFORT"
OPENAI_REASONING_EFFORT_VALUES = ("none", "low", "medium", "high", "xhigh")
MCP_TOKEN_ENV = "DEV_CONTROL_PLANE_MCP_TOKEN"
MCP_TOKEN_MIN_LENGTH = 32
GITHUB_TOKEN_ENV = "DEV_CONTROL_PLANE_GITHUB_TOKEN"
GITHUB_TOKEN_MIN_LENGTH = 20
GITHUB_USERNAME_DEFAULT = "x-access-token"
WB_CORE_DEPLOY_SSH_ALIAS_ENV = "DEV_CONTROL_PLANE_WB_CORE_DEPLOY_SSH_ALIAS"
WB_CORE_DEPLOY_SSH_HOST_ENV = "DEV_CONTROL_PLANE_WB_CORE_DEPLOY_SSH_HOST"
WB_CORE_DEPLOY_SSH_USER_ENV = "DEV_CONTROL_PLANE_WB_CORE_DEPLOY_SSH_USER"
WB_CORE_DEPLOY_SSH_PORT_ENV = "DEV_CONTROL_PLANE_WB_CORE_DEPLOY_SSH_PORT"
WB_CORE_DEPLOY_SSH_IDENTITY_FILE_ENV = "DEV_CONTROL_PLANE_WB_CORE_DEPLOY_SSH_IDENTITY_FILE"
WB_CORE_DEPLOY_SSH_KNOWN_HOSTS_ENV = "DEV_CONTROL_PLANE_WB_CORE_DEPLOY_SSH_KNOWN_HOSTS"
WB_CORE_DEPLOY_SSH_TARGET_ID = "wb-core"
WB_CORE_DEPLOY_SSH_DEFAULT_PORT = 22


@dataclass(frozen=True)
class OpenAICredentials:
    api_key: str
    model: str
    reasoning_effort: str
    source: str


@dataclass(frozen=True)
class GitHubCredentials:
    token: str
    username: str
    source: str


@dataclass(frozen=True)
class WBCoreDeploySSHTarget:
    target_id: str
    alias: str
    host: str
    user: str
    port: int
    identity_file: str
    known_hosts_file: str
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


def generate_mcp_token() -> dict[str, Any]:
    token = token_secrets.token_urlsafe(48)
    summary = set_mcp_token(token)
    return {**summary, "token": token, "token_returned_once": True}


def set_mcp_token(token: str) -> dict[str, Any]:
    token = str(token or "").strip()
    _validate_mcp_token(token)
    path = get_secret_store_path()
    if _is_inside_repo(path):
        raise SecretStoreError(f"refusing to store secrets inside repository: {path}")
    payload = _read_secret_payload()
    payload["mcp"] = {
        "token_sha256": _sha256(token),
        "created_at": _now_utc(),
        "rotated_at": _now_utc(),
    }
    _write_secret_payload(payload)
    return {
        "status": "saved",
        "store": _display_path(path),
        "auth_mode": "bearer_token",
        "configured": True,
        "token_saved": True,
    }


def delete_mcp_token() -> dict[str, Any]:
    payload = _read_secret_payload()
    had_mcp = isinstance(payload.get("mcp"), Mapping)
    payload.pop("mcp", None)
    path = get_secret_store_path()
    if payload:
        _write_secret_payload(payload)
    elif path.exists():
        path.unlink()
    return {
        "status": "deleted" if had_mcp else "missing",
        "store": _display_path(path),
        "mcp_deleted": had_mcp,
    }


def set_github_token(token: str, *, username: str = GITHUB_USERNAME_DEFAULT) -> dict[str, Any]:
    token = str(token or "").strip()
    username = str(username or "").strip() or GITHUB_USERNAME_DEFAULT
    _validate_github_token(token)
    path = get_secret_store_path()
    if _is_inside_repo(path):
        raise SecretStoreError(f"refusing to store secrets inside repository: {path}")
    payload = _read_secret_payload()
    payload["github"] = {
        "token": token,
        "username": username,
        "created_at": _now_utc(),
        "rotated_at": _now_utc(),
    }
    _write_secret_payload(payload)
    return {
        "status": "saved",
        "store": _display_path(path),
        "auth_mode": "runtime_secret_token",
        "configured": True,
        "token_saved": True,
        "username_configured": bool(username),
    }


def delete_github_token() -> dict[str, Any]:
    payload = _read_secret_payload()
    had_github = isinstance(payload.get("github"), Mapping)
    payload.pop("github", None)
    path = get_secret_store_path()
    if payload:
        _write_secret_payload(payload)
    elif path.exists():
        path.unlink()
    return {
        "status": "deleted" if had_github else "missing",
        "store": _display_path(path),
        "github_deleted": had_github,
    }


def set_wb_core_deploy_ssh_target(
    *,
    alias: str = "",
    host: str = "",
    user: str = "",
    port: int | str = WB_CORE_DEPLOY_SSH_DEFAULT_PORT,
    identity_file: str = "",
    known_hosts_file: str = "",
) -> dict[str, Any]:
    alias = str(alias or "").strip()
    host = str(host or "").strip()
    user = str(user or "").strip()
    identity_file = str(identity_file or "").strip()
    known_hosts_file = str(known_hosts_file or "").strip()
    parsed_port = _parse_ssh_port(port)
    if not alias and not host:
        raise SecretStoreError("wb-core deploy SSH target requires an explicit host or service-user SSH alias")
    path = get_secret_store_path()
    if _is_inside_repo(path):
        raise SecretStoreError(f"refusing to store runtime configuration inside repository: {path}")
    payload = _read_secret_payload()
    payload["wb_core_deploy_ssh"] = {
        "target_id": WB_CORE_DEPLOY_SSH_TARGET_ID,
        "alias": alias,
        "host": host,
        "user": user,
        "port": parsed_port,
        "identity_file": identity_file,
        "known_hosts_file": known_hosts_file,
        "created_at": _now_utc(),
        "rotated_at": _now_utc(),
    }
    _write_secret_payload(payload)
    return {
        "status": "saved",
        "store": _display_path(path),
        "target_id": WB_CORE_DEPLOY_SSH_TARGET_ID,
        "configured": True,
        "alias_configured": bool(alias),
        "host_configured": bool(host),
        "user_configured": bool(user),
        "port": parsed_port,
        "identity_file_configured": bool(identity_file),
        "known_hosts_file_configured": bool(known_hosts_file),
        "private_key_saved": False,
        "known_hosts_policy": "strict_host_key_checking",
    }


def delete_wb_core_deploy_ssh_target() -> dict[str, Any]:
    payload = _read_secret_payload()
    had_target = isinstance(payload.get("wb_core_deploy_ssh"), Mapping)
    payload.pop("wb_core_deploy_ssh", None)
    path = get_secret_store_path()
    if payload:
        _write_secret_payload(payload)
    elif path.exists():
        path.unlink()
    return {
        "status": "deleted" if had_target else "missing",
        "store": _display_path(path),
        "wb_core_deploy_ssh_deleted": had_target,
    }


def get_wb_core_deploy_ssh_target(env: Mapping[str, str] | None = None) -> WBCoreDeploySSHTarget | None:
    environment = env if env is not None else os.environ
    env_alias = str(environment.get(WB_CORE_DEPLOY_SSH_ALIAS_ENV) or "").strip()
    env_host = str(environment.get(WB_CORE_DEPLOY_SSH_HOST_ENV) or "").strip()
    env_user = str(environment.get(WB_CORE_DEPLOY_SSH_USER_ENV) or "").strip()
    env_port = str(environment.get(WB_CORE_DEPLOY_SSH_PORT_ENV) or "").strip()
    env_identity = str(environment.get(WB_CORE_DEPLOY_SSH_IDENTITY_FILE_ENV) or "").strip()
    env_known_hosts = str(environment.get(WB_CORE_DEPLOY_SSH_KNOWN_HOSTS_ENV) or "").strip()
    if env_alias or env_host:
        return WBCoreDeploySSHTarget(
            target_id=WB_CORE_DEPLOY_SSH_TARGET_ID,
            alias=env_alias,
            host=env_host,
            user=env_user,
            port=_parse_ssh_port(env_port or WB_CORE_DEPLOY_SSH_DEFAULT_PORT),
            identity_file=env_identity,
            known_hosts_file=env_known_hosts,
            source="env",
        )

    payload = _read_secret_payload(env=environment)
    target = payload.get("wb_core_deploy_ssh")
    if not isinstance(target, Mapping):
        return None
    alias = str(target.get("alias") or "").strip()
    host = str(target.get("host") or "").strip()
    if not alias and not host:
        return None
    return WBCoreDeploySSHTarget(
        target_id=WB_CORE_DEPLOY_SSH_TARGET_ID,
        alias=alias,
        host=host,
        user=str(target.get("user") or "").strip(),
        port=_parse_ssh_port(target.get("port") or WB_CORE_DEPLOY_SSH_DEFAULT_PORT),
        identity_file=str(target.get("identity_file") or "").strip(),
        known_hosts_file=str(target.get("known_hosts_file") or "").strip(),
        source="file",
    )


def get_wb_core_deploy_ssh_secret_status(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    environment = env if env is not None else os.environ
    path = get_secret_store_path(env=environment)
    target = get_wb_core_deploy_ssh_target(env=environment)
    payload = _read_secret_payload(env=environment)
    stored = payload.get("wb_core_deploy_ssh")
    rotated_at = str(stored.get("rotated_at") or "") if isinstance(stored, Mapping) else None
    return {
        "configured": target is not None,
        "source": target.source if target else "missing",
        "store": _display_path(path),
        "store_exists": path.exists(),
        "target_id": WB_CORE_DEPLOY_SSH_TARGET_ID,
        "alias": target.alias if target and target.alias else None,
        "host": target.host if target and target.host else None,
        "port": target.port if target else None,
        "user_configured": bool(target.user) if target else False,
        "identity_file_configured": bool(target.identity_file) if target else False,
        "known_hosts_file_configured": bool(target.known_hosts_file) if target else False,
        "known_hosts_policy": "strict_host_key_checking",
        "private_key_saved": False,
        "rotated_at": rotated_at if target and target.source == "file" else None,
    }


def get_github_credentials(env: Mapping[str, str] | None = None) -> GitHubCredentials | None:
    environment = env if env is not None else os.environ
    for key in (GITHUB_TOKEN_ENV, "GH_TOKEN", "GITHUB_TOKEN"):
        token = str(environment.get(key) or "").strip()
        if token:
            username = str(environment.get("DEV_CONTROL_PLANE_GITHUB_USERNAME") or "").strip() or GITHUB_USERNAME_DEFAULT
            return GitHubCredentials(token=token, username=username, source=f"env:{key}")
    payload = _read_secret_payload(env=environment)
    github = payload.get("github")
    if not isinstance(github, Mapping):
        return None
    token = str(github.get("token") or "").strip()
    if not token:
        return None
    username = str(github.get("username") or "").strip() or GITHUB_USERNAME_DEFAULT
    return GitHubCredentials(token=token, username=username, source="file")


def get_github_secret_status(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    environment = env if env is not None else os.environ
    path = get_secret_store_path(env=environment)
    credentials = get_github_credentials(env=environment)
    payload = _read_secret_payload(env=environment)
    github = payload.get("github")
    rotated_at = str(github.get("rotated_at") or "") if isinstance(github, Mapping) else None
    return {
        "configured": credentials is not None,
        "auth_mode": "runtime_secret_token",
        "source": credentials.source if credentials else "missing",
        "store": _display_path(path),
        "store_exists": path.exists(),
        "token_present": credentials is not None,
        "username_configured": bool(credentials.username) if credentials else False,
        "rotated_at": rotated_at if credentials and credentials.source == "file" else None,
    }


def get_mcp_auth_status(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    environment = env if env is not None else os.environ
    path = get_secret_store_path(env=environment)
    env_token = str(environment.get(MCP_TOKEN_ENV) or "").strip()
    if env_token:
        return {
            "configured": True,
            "auth_mode": "bearer_token",
            "source": "env",
            "store": _display_path(path),
            "store_exists": path.exists(),
            "token_present": True,
        }
    payload = _read_secret_payload(env=environment)
    mcp = payload.get("mcp")
    configured = isinstance(mcp, Mapping) and bool(str(mcp.get("token_sha256") or "").strip())
    return {
        "configured": configured,
        "auth_mode": "bearer_token",
        "source": "file" if configured else "missing",
        "store": _display_path(path),
        "store_exists": path.exists(),
        "token_present": configured,
        "rotated_at": str(mcp.get("rotated_at") or "") if isinstance(mcp, Mapping) and configured else None,
    }


def verify_mcp_bearer_token(authorization_header: str | None, env: Mapping[str, str] | None = None) -> bool:
    token = _bearer_token_from_header(authorization_header)
    if not token:
        return False
    environment = env if env is not None else os.environ
    env_token = str(environment.get(MCP_TOKEN_ENV) or "").strip()
    if env_token:
        return hmac.compare_digest(token, env_token)
    payload = _read_secret_payload(env=environment)
    mcp = payload.get("mcp")
    if not isinstance(mcp, Mapping):
        return False
    expected = str(mcp.get("token_sha256") or "").strip()
    if not expected:
        return False
    return hmac.compare_digest(_sha256(token), expected)


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


def _validate_mcp_token(token: str) -> None:
    if len(token) < MCP_TOKEN_MIN_LENGTH:
        raise SecretStoreError(f"MCP bearer token must be at least {MCP_TOKEN_MIN_LENGTH} characters")
    lowered = token.lower()
    if "basic " in lowered or "bearer " in lowered:
        raise SecretStoreError("store only the raw MCP token, not an Authorization header")


def _validate_github_token(token: str) -> None:
    if len(token) < GITHUB_TOKEN_MIN_LENGTH:
        raise SecretStoreError(f"GitHub token must be at least {GITHUB_TOKEN_MIN_LENGTH} characters")
    lowered = token.lower()
    if "basic " in lowered or "bearer " in lowered or "authorization:" in lowered:
        raise SecretStoreError("store only the raw GitHub token, not an Authorization header")


def _parse_ssh_port(value: int | str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise SecretStoreError("wb-core deploy SSH port must be an integer") from None
    if parsed < 1 or parsed > 65535:
        raise SecretStoreError("wb-core deploy SSH port must be between 1 and 65535")
    return parsed


def _bearer_token_from_header(header: str | None) -> str | None:
    if not header:
        return None
    prefix = "Bearer "
    if not header.startswith(prefix):
        return None
    token = header[len(prefix) :].strip()
    return token or None


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _is_inside_repo(path: Path) -> bool:
    repo_root = Path(__file__).resolve().parents[2]
    try:
        path.resolve().relative_to(repo_root)
        return True
    except ValueError:
        return False
