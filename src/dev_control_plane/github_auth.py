"""Sanitized GitHub auth readiness checks for hosted production-lane gates."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
import json
from pathlib import Path
import shutil
import subprocess
from typing import Any

from dev_control_plane.secrets import get_github_credentials, get_github_secret_status
from dev_control_plane.toolchain import runtime_command_env, runtime_path

GITHUB_HOST = "github.com"
DEFAULT_TARGET_REPO = "orenvlad-ai/wb-core"
DEFAULT_TARGET_REPO_URL = f"https://{GITHUB_HOST}/{DEFAULT_TARGET_REPO}.git"
WRITE_PERMISSIONS = {"ADMIN", "MAINTAIN", "WRITE"}
CommandRunner = Callable[[Sequence[str], Path | None, Mapping[str, str]], subprocess.CompletedProcess[str]]


def build_github_auth_status(
    *,
    env: Mapping[str, str] | None = None,
    repo: str = DEFAULT_TARGET_REPO,
    repo_url: str = DEFAULT_TARGET_REPO_URL,
    require_write: bool = True,
    check_remote: bool = True,
    askpass_dir: Path | None = None,
    runner: CommandRunner | None = None,
) -> dict[str, Any]:
    """Return sanitized GitHub readiness for production-lane Git/gh operations."""

    environment = env if env is not None else None
    credentials = get_github_credentials(env=environment)
    secret_status = get_github_secret_status(env=environment)
    gh_path = shutil.which("gh", path=runtime_path(environment))
    checks: list[dict[str, Any]] = []
    blockers: list[str] = []

    if not gh_path:
        blockers.append("GitHub CLI `gh` is missing from the hosted runtime PATH")
        checks.append({"name": "gh_installed", "status": "blocked"})
    else:
        checks.append({"name": "gh_installed", "status": "ready", "path": gh_path})

    if credentials is None:
        blockers.append(
            "GitHub runtime token is missing; configure it outside the repo with `dev_control_plane_setup.py github-token`"
        )
        checks.append({"name": "runtime_secret_token", "status": "missing"})
        return _status_payload(
            blockers=blockers,
            checks=checks,
            repo=repo,
            secret_status=secret_status,
            gh_path=gh_path,
            permission=None,
            git_https_auth_ready=False,
        )

    checks.append({"name": "runtime_secret_token", "status": "ready", "source": secret_status.get("source")})
    if not gh_path:
        return _status_payload(
            blockers=blockers,
            checks=checks,
            repo=repo,
            secret_status=secret_status,
            gh_path=gh_path,
            permission=None,
            git_https_auth_ready=False,
        )

    command_env = github_command_env(env=environment, askpass_dir=askpass_dir)
    command_runner = runner or _run_command
    gh_auth = command_runner((gh_path, "auth", "status", "--hostname", GITHUB_HOST), None, command_env)
    if gh_auth.returncode != 0:
        blockers.append("GitHub token was rejected by `gh auth status`")
        checks.append({"name": "gh_auth_status", "status": "blocked"})
    else:
        checks.append({"name": "gh_auth_status", "status": "ready"})

    permission: str | None = None
    git_https_auth_ready = False
    if check_remote:
        repo_view = command_runner((gh_path, "repo", "view", repo, "--json", "nameWithOwner,viewerPermission"), None, command_env)
        if repo_view.returncode != 0:
            blockers.append(f"GitHub repo access check failed for {repo}")
            checks.append({"name": "repo_access", "status": "blocked", "repo": repo})
        else:
            payload = _parse_json_object(repo_view.stdout)
            permission = str(payload.get("viewerPermission") or "").upper() if payload else ""
            checks.append({"name": "repo_access", "status": "ready", "repo": repo, "viewer_permission": permission or "unknown"})
            if require_write and permission not in WRITE_PERMISSIONS:
                blockers.append(f"GitHub token does not have write/maintain/admin permission for {repo}")

        ls_remote = command_runner(("git", "ls-remote", repo_url, "refs/heads/main"), None, command_env)
        if ls_remote.returncode != 0:
            blockers.append(f"Git HTTPS auth check failed for {repo}")
            checks.append({"name": "git_https_auth", "status": "blocked", "repo": repo})
        else:
            git_https_auth_ready = True
            checks.append({"name": "git_https_auth", "status": "ready", "repo": repo})
    else:
        checks.append({"name": "repo_access", "status": "not_checked", "repo": repo})
        checks.append({"name": "git_https_auth", "status": "not_checked", "repo": repo})

    return _status_payload(
        blockers=blockers,
        checks=checks,
        repo=repo,
        secret_status=secret_status,
        gh_path=gh_path,
        permission=permission,
        git_https_auth_ready=git_https_auth_ready,
    )


def github_command_env(*, env: Mapping[str, str] | None = None, askpass_dir: Path | None = None) -> dict[str, str]:
    credentials = get_github_credentials(env=env)
    if credentials is None:
        raise RuntimeError("GitHub runtime token is missing")
    result = runtime_command_env(env)
    result["GH_TOKEN"] = credentials.token
    result["GITHUB_TOKEN"] = credentials.token
    result["DEV_CONTROL_PLANE_GITHUB_TOKEN"] = credentials.token
    result["DEV_CONTROL_PLANE_GITHUB_USERNAME"] = credentials.username
    result["GIT_TERMINAL_PROMPT"] = "0"
    if askpass_dir is not None:
        result["GIT_ASKPASS"] = str(write_git_askpass_script(askpass_dir))
    return result


def write_git_askpass_script(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "git-askpass.sh"
    path.write_text(
        "#!/bin/sh\n"
        "case \"$1\" in\n"
        "  *Username*) printf '%s\\n' \"${DEV_CONTROL_PLANE_GITHUB_USERNAME:-x-access-token}\" ;;\n"
        "  *Password*) printf '%s\\n' \"${DEV_CONTROL_PLANE_GITHUB_TOKEN:?}\" ;;\n"
        "  *) printf '\\n' ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    path.chmod(0o700)
    return path


def _status_payload(
    *,
    blockers: Sequence[str],
    checks: Sequence[Mapping[str, Any]],
    repo: str,
    secret_status: Mapping[str, Any],
    gh_path: str | None,
    permission: str | None,
    git_https_auth_ready: bool,
) -> dict[str, Any]:
    return {
        "status": "ready" if not blockers else ("missing" if not secret_status.get("configured") else "blocked"),
        "configured": bool(secret_status.get("configured")),
        "auth_mode": "runtime_secret_token",
        "source": secret_status.get("source"),
        "store": secret_status.get("store"),
        "store_exists": bool(secret_status.get("store_exists")),
        "token_present": bool(secret_status.get("token_present")),
        "username_configured": bool(secret_status.get("username_configured")),
        "gh_installed": bool(gh_path),
        "gh_path": gh_path,
        "repo": repo,
        "repo_write_permission": permission in WRITE_PERMISSIONS if permission else False,
        "viewer_permission": permission,
        "git_https_auth_ready": git_https_auth_ready,
        "checks": [dict(check) for check in checks],
        "blocker": "; ".join(blockers) if blockers else None,
        "blockers": list(blockers),
    }


def _run_command(command: Sequence[str], cwd: Path | None, env: Mapping[str, str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(tuple(command), cwd=cwd, capture_output=True, text=True, check=False, timeout=12, env=dict(env))
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(args=tuple(command), returncode=124, stdout="", stderr="command timed out")


def _parse_json_object(raw: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None
