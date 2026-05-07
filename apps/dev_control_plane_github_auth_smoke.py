"""Smoke-check sanitized hosted GitHub auth readiness helpers."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from typing import Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (SRC, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dev_control_plane.github_auth import build_github_auth_status, github_command_env  # noqa: E402
from dev_control_plane.secrets import SECRET_HOME_ENV, set_github_token  # noqa: E402


def main() -> None:
    with TemporaryDirectory(prefix="dev-control-plane-github-auth-") as tmp_raw:
        tmp = Path(tmp_raw)
        secret_home = tmp / "secrets"
        env = _base_env(tmp, secret_home)
        missing = build_github_auth_status(env=env, check_remote=True, runner=_ready_runner())
        if missing.get("status") != "missing" or "GitHub runtime token is missing" not in str(missing.get("blocker")):
            raise AssertionError(f"missing GitHub token must be an exact preflight blocker: {missing}")
        _assert_no_secret(missing)

        old_secret_home = os.environ.get(SECRET_HOME_ENV)
        os.environ[SECRET_HOME_ENV] = str(secret_home)
        try:
            set_github_token("github_pat_smoke_secret_token_0123456789abcdef")
            ready = build_github_auth_status(env=env, askpass_dir=tmp / "askpass", runner=_ready_runner())
            if ready.get("status") != "ready" or ready.get("repo_write_permission") is not True:
                raise AssertionError(f"configured GitHub token must pass stubbed auth checks: {ready}")
            if ready.get("git_https_auth_ready") is not True:
                raise AssertionError(f"git HTTPS auth must be ready with askpass token env: {ready}")
            command_env = github_command_env(env=env, askpass_dir=tmp / "askpass-env")
            askpass = Path(command_env["GIT_ASKPASS"])
            if "github_pat_smoke_secret" in askpass.read_text(encoding="utf-8"):
                raise AssertionError("askpass helper must not write the token to disk")
            _assert_no_secret(ready)

            read_only = build_github_auth_status(env=env, askpass_dir=tmp / "askpass-read", runner=_ready_runner(permission="READ"))
            if read_only.get("status") != "blocked" or "write/maintain/admin permission" not in str(read_only.get("blocker")):
                raise AssertionError(f"read-only repo permission must block production-lane auth: {read_only}")
            _assert_no_secret(read_only)
        finally:
            if old_secret_home is None:
                os.environ.pop(SECRET_HOME_ENV, None)
            else:
                os.environ[SECRET_HOME_ENV] = old_secret_home

    print("dev-control-plane-github-auth-smoke passed")


def _base_env(tmp: Path, secret_home: Path) -> dict[str, str]:
    bin_dir = tmp / "bin"
    bin_dir.mkdir()
    _write_stub(bin_dir / "gh", "gh version smoke")
    git = _which("git")
    (bin_dir / "git").symlink_to(git)
    return {
        SECRET_HOME_ENV: str(secret_home),
        "DEV_CONTROL_PLANE_TOOLCHAIN_BIN_DIR": str(bin_dir),
        "PATH": str(bin_dir),
        "HOME": str(tmp / "home"),
    }


def _ready_runner(*, permission: str = "WRITE"):
    def _run(command: Sequence[str], _cwd: Path | None, _env: Mapping[str, str]) -> subprocess.CompletedProcess[str]:
        args = tuple(command)
        if args[:3] == ("gh", "auth", "status") or (len(args) >= 3 and args[1:3] == ("auth", "status")):
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")
        if "repo" in args and "view" in args:
            return subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout=json.dumps({"nameWithOwner": "orenvlad-ai/wb-core", "viewerPermission": permission}),
                stderr="",
            )
        if args[:2] == ("git", "ls-remote"):
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="abc\trefs/heads/main\n", stderr="")
        return subprocess.CompletedProcess(args=args, returncode=1, stdout="", stderr="unexpected command")

    return _run


def _write_stub(path: Path, version: str) -> None:
    path.write_text("#!/bin/sh\necho '%s'\n" % version, encoding="utf-8")
    path.chmod(0o700)


def _which(name: str) -> Path:
    path = os.environ.get("PATH", "")
    for item in path.split(os.pathsep):
        candidate = Path(item) / name
        if candidate.exists():
            return candidate
    raise AssertionError(f"smoke host missing required tool: {name}")


def _assert_no_secret(payload: Mapping[str, object]) -> None:
    serialized = json.dumps(payload, ensure_ascii=False)
    for forbidden in ("github_pat_smoke_secret", "Authorization", "Bearer "):
        if forbidden in serialized:
            raise AssertionError(f"GitHub auth status leaked secret material: {payload}")


if __name__ == "__main__":
    main()
