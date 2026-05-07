"""Sanitized SSH deploy-target readiness for the wb-core production lane."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
import shutil
import subprocess
from typing import Any

from dev_control_plane.secrets import (
    WBCoreDeploySSHTarget,
    get_wb_core_deploy_ssh_secret_status,
    get_wb_core_deploy_ssh_target,
)
from dev_control_plane.toolchain import runtime_command_env, runtime_path

DEFAULT_TARGET_ID = "wb-core"
CommandRunner = Callable[[Sequence[str], Path | None, Mapping[str, str]], subprocess.CompletedProcess[str]]


def build_ssh_deploy_status(
    *,
    env: Mapping[str, str] | None = None,
    target_id: str = DEFAULT_TARGET_ID,
    check_remote: bool = True,
    runner: CommandRunner | None = None,
) -> dict[str, Any]:
    """Return sanitized SSH backup/deploy readiness.

    The readiness check intentionally does not return private key paths, key
    material, raw stderr/stdout or environment values. It only reports whether
    an explicit hosted/service-user target exists and whether BatchMode SSH can
    execute a no-op command with strict host-key checking enabled.
    """

    environment = env if env is not None else None
    configured = get_wb_core_deploy_ssh_target(env=environment)
    secret_status = get_wb_core_deploy_ssh_secret_status(env=environment)
    ssh_path = shutil.which("ssh", path=runtime_path(environment))
    checks: list[dict[str, Any]] = []
    blockers: list[str] = []

    if not ssh_path:
        blockers.append("OpenSSH client `ssh` is missing from the hosted runtime PATH")
        checks.append({"name": "ssh_installed", "status": "blocked"})
    else:
        checks.append({"name": "ssh_installed", "status": "ready", "path": ssh_path})

    if configured is None:
        blockers.append(
            "wb-core deploy SSH target is missing; configure it outside the repo with "
            "`dev_control_plane_setup.py wb-core-deploy-ssh-target`"
        )
        checks.append({"name": "runtime_ssh_target", "status": "missing"})
        return _status_payload(
            blockers=blockers,
            checks=checks,
            target_id=target_id,
            secret_status=secret_status,
            ssh_path=ssh_path,
            remote_ready=False,
            check_remote=check_remote,
        )

    checks.append({"name": "runtime_ssh_target", "status": "ready", "source": configured.source})
    if not ssh_path:
        return _status_payload(
            blockers=blockers,
            checks=checks,
            target_id=target_id,
            secret_status=secret_status,
            ssh_path=ssh_path,
            remote_ready=False,
            check_remote=check_remote,
        )

    if check_remote:
        command = ssh_command(configured, "true", ssh_path=ssh_path)
        command_runner = runner or _run_command
        completed = command_runner(command, None, ssh_command_env(env=environment))
        if completed.returncode != 0:
            blockers.append(
                "wb-core deploy SSH target check failed; verify service-user SSH config, host, key and known_hosts"
            )
            checks.append({"name": "ssh_batchmode_true", "status": "blocked", "returncode": completed.returncode})
        else:
            checks.append({"name": "ssh_batchmode_true", "status": "ready"})
    else:
        checks.append({"name": "ssh_batchmode_true", "status": "not_checked"})

    return _status_payload(
        blockers=blockers,
        checks=checks,
        target_id=target_id,
        secret_status=secret_status,
        ssh_path=ssh_path,
        remote_ready=check_remote and not blockers,
        check_remote=check_remote,
    )


def ssh_command_env(*, env: Mapping[str, str] | None = None) -> dict[str, str]:
    return runtime_command_env(env)


def ssh_command(config: WBCoreDeploySSHTarget, remote_command: str, *, ssh_path: str | None = None) -> tuple[str, ...]:
    target = _ssh_target(config)
    command: list[str] = [
        ssh_path or "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "LogLevel=ERROR",
    ]
    if config.known_hosts_file:
        command.extend(("-o", f"UserKnownHostsFile={config.known_hosts_file}"))
    if config.identity_file:
        command.extend(("-o", "IdentitiesOnly=yes", "-i", config.identity_file))
    if config.host and config.port:
        command.extend(("-p", str(config.port)))
    command.extend((target, remote_command))
    return tuple(command)


def ssh_deploy_command(
    remote_command: str,
    *,
    env: Mapping[str, str] | None = None,
    ssh_path: str | None = None,
) -> tuple[str, ...]:
    config = get_wb_core_deploy_ssh_target(env=env)
    if config is None:
        raise RuntimeError("wb-core deploy SSH target is missing")
    return ssh_command(config, remote_command, ssh_path=ssh_path)


def _status_payload(
    *,
    blockers: Sequence[str],
    checks: Sequence[Mapping[str, Any]],
    target_id: str,
    secret_status: Mapping[str, Any],
    ssh_path: str | None,
    remote_ready: bool,
    check_remote: bool,
) -> dict[str, Any]:
    configured = bool(secret_status.get("configured"))
    return {
        "status": "ready" if not blockers else ("missing" if not configured else "blocked"),
        "configured": configured,
        "target_id": target_id,
        "auth_mode": "service_user_ssh_config_or_explicit_runtime_target",
        "source": secret_status.get("source"),
        "store": secret_status.get("store"),
        "store_exists": bool(secret_status.get("store_exists")),
        "alias": secret_status.get("alias"),
        "host": secret_status.get("host"),
        "port": secret_status.get("port"),
        "user_configured": bool(secret_status.get("user_configured")),
        "identity_policy": "identity_file_configured" if secret_status.get("identity_file_configured") else "service_user_ssh_config_or_agent",
        "identity_file_configured": bool(secret_status.get("identity_file_configured")),
        "known_hosts_policy": "strict_host_key_checking",
        "known_hosts_file_configured": bool(secret_status.get("known_hosts_file_configured")),
        "private_key_saved": False,
        "ssh_installed": bool(ssh_path),
        "ssh_path": ssh_path,
        "remote_check": "checked" if check_remote else "not_checked",
        "remote_ready": remote_ready,
        "checks": [dict(check) for check in checks],
        "blocker": "; ".join(blockers) if blockers else None,
        "blockers": list(blockers),
    }


def _ssh_target(config: WBCoreDeploySSHTarget) -> str:
    if config.host:
        return f"{config.user}@{config.host}" if config.user else config.host
    return config.alias


def _run_command(command: Sequence[str], cwd: Path | None, env: Mapping[str, str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(tuple(command), cwd=cwd, capture_output=True, text=True, check=False, timeout=12, env=dict(env))
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(args=tuple(command), returncode=124, stdout="", stderr="command timed out")
