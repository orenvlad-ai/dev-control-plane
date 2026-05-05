"""Smoke-check local secret store without touching real user secrets."""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (SRC, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dev_control_plane.secrets import (  # noqa: E402
    SECRET_HOME_ENV,
    delete_openai_credentials,
    get_openai_credentials,
    get_openai_status,
    get_secret_store_path,
    set_openai_credentials,
)

SETUP = ROOT / "apps" / "dev_control_plane_setup.py"
PROBE = ROOT / "apps" / "dev_control_plane_openai_probe.py"


def main() -> None:
    with TemporaryDirectory(prefix="dev-control-plane-secrets-smoke-") as tmp:
        secret_home = Path(tmp) / "secret-home"
        old_secret_home = os.environ.get(SECRET_HOME_ENV)
        os.environ[SECRET_HOME_ENV] = str(secret_home)
        try:
            _exercise_secret_store(secret_home)
            _exercise_setup_cli(secret_home)
            _exercise_probe_reads_file_credentials(secret_home)
        finally:
            if old_secret_home is None:
                os.environ.pop(SECRET_HOME_ENV, None)
            else:
                os.environ[SECRET_HOME_ENV] = old_secret_home

    print("dev-control-plane-secrets-smoke passed")


def _exercise_secret_store(secret_home: Path) -> None:
    summary = set_openai_credentials("sk-smoke-secret", "gpt-smoke")
    path = get_secret_store_path()
    if not path.exists() or not _is_relative_to(path, secret_home.resolve()):
        raise AssertionError(f"secret file must be under smoke secret home: {path}")
    if _is_relative_to(path.resolve(), ROOT.resolve()):
        raise AssertionError(f"secret file must not be under repo: {path}")
    if "sk-smoke-secret" in json.dumps(summary, ensure_ascii=False):
        raise AssertionError(f"set summary leaked API key: {summary}")
    _assert_mode(path, 0o600)
    _assert_mode(path.parent, 0o700)

    status = get_openai_status()
    if (
        status.get("configured") is not True
        or status.get("source") != "file"
        or status.get("model") != "gpt-smoke"
        or status.get("reasoning_effort") != "xhigh"
    ):
        raise AssertionError(f"file credential status wrong: {status}")
    _assert_no_key(status)

    credentials = get_openai_credentials()
    if (
        not credentials
        or credentials.api_key != "sk-smoke-secret"
        or credentials.source != "file"
        or credentials.reasoning_effort != "xhigh"
    ):
        raise AssertionError(f"file credentials not loaded: {credentials}")

    env_credentials = get_openai_credentials(
        env={
            SECRET_HOME_ENV: str(secret_home),
            "OPENAI_API_KEY": "sk-env-secret",
            "CURATOR_COCKPIT_OPENAI_MODEL": "gpt-env",
            "CURATOR_COCKPIT_OPENAI_REASONING_EFFORT": "high",
        }
    )
    if (
        not env_credentials
        or env_credentials.api_key != "sk-env-secret"
        or env_credentials.source != "env"
        or env_credentials.reasoning_effort != "high"
    ):
        raise AssertionError(f"env credentials must override file: {env_credentials}")

    delete_summary = delete_openai_credentials()
    if delete_summary.get("openai_deleted") is not True or path.exists():
        raise AssertionError(f"delete-openai must remove stored credential: {delete_summary}")
    _assert_no_key(delete_summary)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not-json", encoding="utf-8")
    corrupt_status = get_openai_status()
    if corrupt_status.get("configured") is not False or corrupt_status.get("source") != "missing":
        raise AssertionError(f"corrupt secret file must fail closed as missing: {corrupt_status}")
    _assert_no_key(corrupt_status)
    path.unlink()


def _exercise_setup_cli(secret_home: Path) -> None:
    env = _smoke_env(secret_home)
    status = _run_json([str(SETUP), "status"], env=env, expect_success=True)
    if status.get("openai", {}).get("configured") is not False:
        raise AssertionError(f"setup status should be missing before save: {status}")
    _assert_no_key(status)

    set_openai_credentials("sk-setup-smoke", "gpt-setup-smoke")
    status = _run_json([str(SETUP), "status"], env=env, expect_success=True)
    if status.get("openai", {}).get("source") != "file" or status.get("openai", {}).get("model") != "gpt-setup-smoke":
        raise AssertionError(f"setup status must read local file credentials: {status}")
    if status.get("openai", {}).get("reasoning_effort") != "xhigh":
        raise AssertionError(f"setup status must report reasoning effort: {status}")
    _assert_no_key(status)

    deleted = _run_json([str(SETUP), "delete-openai"], env=env, expect_success=True)
    if deleted.get("openai_deleted") is not True:
        raise AssertionError(f"setup delete-openai should remove file credential: {deleted}")
    _assert_no_key(deleted)


def _exercise_probe_reads_file_credentials(secret_home: Path) -> None:
    set_openai_credentials("sk-probe-smoke", "gpt-probe-smoke")
    env = _smoke_env(secret_home)
    env["DEV_CONTROL_PLANE_OPENAI_PROBE_STUB"] = "1"
    completed = subprocess.run(
        [sys.executable, str(PROBE)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise AssertionError(f"stubbed probe should pass without real API\nstdout={completed.stdout}\nstderr={completed.stderr}")
    payload = json.loads(completed.stdout)
    if payload.get("status") != "ok" or payload.get("model") != "gpt-probe-smoke" or payload.get("configured") is not True:
        raise AssertionError(f"probe should use file-backed credentials before making request: {payload}")
    _assert_no_key(payload)
    delete_openai_credentials()


def _run_json(command: list[str], *, env: dict[str, str], expect_success: bool) -> dict:
    completed = subprocess.run(
        [sys.executable, *command],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if expect_success and completed.returncode != 0:
        raise AssertionError(f"command failed: {command}\nstdout={completed.stdout}\nstderr={completed.stderr}")
    return json.loads(completed.stdout)


def _smoke_env(secret_home: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("OPENAI_API_KEY", None)
    env.pop("CURATOR_COCKPIT_OPENAI_MODEL", None)
    env.pop("CURATOR_COCKPIT_OPENAI_REASONING_EFFORT", None)
    env.pop("DEV_CONTROL_PLANE_OPENAI_TIMEOUT_SECONDS", None)
    env.pop("DEV_CONTROL_PLANE_OPENAI_RETRY_COUNT", None)
    env.pop("DEV_CONTROL_PLANE_OPENAI_RETRY_BACKOFF_SECONDS", None)
    env[SECRET_HOME_ENV] = str(secret_home)
    return env


def _assert_no_key(payload) -> None:
    serialized = json.dumps(payload, ensure_ascii=False)
    for forbidden in ("sk-smoke", "sk-setup", "sk-probe", "api_key"):
        if forbidden in serialized:
            raise AssertionError(f"payload leaked secret material: {payload}")


def _assert_mode(path: Path, expected_mode: int) -> None:
    actual = stat.S_IMODE(path.stat().st_mode)
    if actual != expected_mode:
        raise AssertionError(f"expected {oct(expected_mode)} for {path}, got {oct(actual)}")


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


if __name__ == "__main__":
    main()
