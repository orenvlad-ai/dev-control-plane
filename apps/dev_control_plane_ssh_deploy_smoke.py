"""Smoke-check sanitized wb-core deploy SSH readiness."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from typing import Mapping

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (SRC, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dev_control_plane.secrets import (  # noqa: E402
    SECRET_HOME_ENV,
    delete_wb_core_deploy_ssh_target,
    get_wb_core_deploy_ssh_secret_status,
    get_wb_core_deploy_ssh_target,
    set_wb_core_deploy_ssh_target,
)
from dev_control_plane.ssh_deploy import build_ssh_deploy_status, ssh_deploy_command  # noqa: E402


def main() -> None:
    with TemporaryDirectory(prefix="dev-control-plane-ssh-deploy-") as tmp_raw:
        tmp = Path(tmp_raw)
        secret_home = tmp / "secrets"
        env = {SECRET_HOME_ENV: str(secret_home), "PATH": "/usr/bin:/bin"}

        missing = build_ssh_deploy_status(env=env, runner=_ready_runner())
        if missing.get("status") != "missing" or "SSH target is missing" not in str(missing.get("blocker")):
            raise AssertionError(f"missing SSH target must be controlled: {missing}")

        with _patched_env(env):
            summary = set_wb_core_deploy_ssh_target(
                alias="wb-core-eu-root",
                host="89.191.226.88",
                user="dev-control-plane",
                port=22,
                identity_file="/tmp/private-key-smoke",
                known_hosts_file="/tmp/known-hosts-smoke",
            )
            if summary.get("private_key_saved") is not False:
                raise AssertionError(f"setup summary must not save private key material: {summary}")
            secret_status = get_wb_core_deploy_ssh_secret_status()
            if secret_status.get("identity_file_configured") is not True:
                raise AssertionError(f"secret status must show identity policy only: {secret_status}")
            if "private-key-smoke" in json.dumps(secret_status, ensure_ascii=False):
                raise AssertionError(f"secret status leaked private key path: {secret_status}")
            target = get_wb_core_deploy_ssh_target()
            if target is None or target.host != "89.191.226.88":
                raise AssertionError(f"stored SSH target must round-trip internally: {target}")

            ready = build_ssh_deploy_status(env=env, runner=_ready_runner())
            if ready.get("status") != "ready" or ready.get("remote_ready") is not True:
                raise AssertionError(f"stubbed SSH target must be ready: {ready}")
            serialized = json.dumps(ready, ensure_ascii=False)
            for forbidden in ("private-key-smoke", "known-hosts-smoke", "BEGIN OPENSSH", "Authorization", "Bearer "):
                if forbidden in serialized:
                    raise AssertionError(f"SSH status leaked sensitive material: {ready}")

            command = ssh_deploy_command("true", env=env)
            if "/tmp/private-key-smoke" not in command:
                raise AssertionError("internal SSH command should include configured identity file")
            if delete_wb_core_deploy_ssh_target().get("wb_core_deploy_ssh_deleted") is not True:
                raise AssertionError("delete_wb_core_deploy_ssh_target must remove stored config")

    print("dev-control-plane-ssh-deploy-smoke passed")


class _patched_env:
    def __init__(self, updates: Mapping[str, str]) -> None:
        self.updates = dict(updates)
        self.previous: dict[str, str | None] = {}

    def __enter__(self):
        import os

        for key, value in self.updates.items():
            self.previous[key] = os.environ.get(key)
            os.environ[key] = value
        return self

    def __exit__(self, *_exc):
        import os

        for key, value in self.previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _ready_runner():
    def _run(command, _cwd, _env):
        args = tuple(command)
        if args and str(args[0]).endswith("ssh") and args[-1] == "true":
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")
        return subprocess.CompletedProcess(args=args, returncode=1, stdout="", stderr="unexpected command")

    return _run


if __name__ == "__main__":
    main()
