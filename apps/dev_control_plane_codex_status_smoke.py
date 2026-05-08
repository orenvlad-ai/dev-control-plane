"""Smoke-check sanitized Codex CLI status diagnostics without real Codex runs."""

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

from dev_control_plane.server import build_connections_status  # noqa: E402


def main() -> None:
    with TemporaryDirectory(prefix="dev-control-plane-codex-status-") as tmp:
        root = Path(tmp)
        fake_codex = root / "codex"
        _write_fake_codex(fake_codex, authenticated=True)
        _with_env(root, fake_codex, _assert_authenticated_status)

        _write_fake_codex(fake_codex, authenticated=False)
        _with_env(root, fake_codex, _assert_unauthenticated_status)

        _assert_missing_status(root)

    print("dev-control-plane-codex-status-smoke passed")


def _assert_authenticated_status() -> None:
    status = build_connections_status()
    codex = status.get("codex", {})
    if codex.get("installed") is not True:
        raise AssertionError(f"fake Codex should be installed: {status}")
    if codex.get("version") != "codex-cli 0.128.0":
        raise AssertionError(f"Codex version should be sanitized and deterministic: {status}")
    if codex.get("auth_check_supported") is not True:
        raise AssertionError(f"Codex auth check should be supported when binary exists: {status}")
    if codex.get("authenticated") is not True or codex.get("auth_status") != "authenticated":
        raise AssertionError(f"Codex auth status should be authenticated: {status}")
    instructions = codex.get("instructions") or []
    if "codex --login" in instructions or "codex login --device-auth" not in instructions:
        raise AssertionError(f"Codex login instructions must use current CLI syntax: {codex}")
    if (
        codex.get("config_status") != "present"
        or codex.get("model") != "gpt-5.5"
        or codex.get("model_reasoning_effort") != "xhigh"
    ):
        raise AssertionError(f"Codex model config should be sanitized and visible: {status}")
    _assert_no_secret_material(status)


def _assert_unauthenticated_status() -> None:
    status = build_connections_status()
    codex = status.get("codex", {})
    if codex.get("installed") is not True:
        raise AssertionError(f"fake Codex should still be installed: {status}")
    if codex.get("authenticated") is not False or codex.get("auth_status") != "not_authenticated":
        raise AssertionError(f"Codex auth status should be sanitized unauthenticated: {status}")
    instructions = codex.get("instructions") or []
    if "codex --login" in instructions or "codex login" not in instructions:
        raise AssertionError(f"Codex unauthenticated instructions must use current CLI syntax: {codex}")
    _assert_no_secret_material(status)


def _assert_missing_status(root: Path) -> None:
    old_values = {key: os.environ.get(key) for key in ("PATH", "HOME", "CODEX_HOME", "DEV_CONTROL_PLANE_CODEX_BIN")}
    try:
        os.environ["PATH"] = str(root / "empty-bin")
        os.environ["HOME"] = str(root / "empty-home")
        os.environ["CODEX_HOME"] = str(root / "empty-codex-home")
        os.environ.pop("DEV_CONTROL_PLANE_CODEX_BIN", None)
        status = build_connections_status()
    finally:
        for key, value in old_values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    codex = status.get("codex", {})
    if codex.get("installed") is not False or codex.get("auth_status") != "missing":
        raise AssertionError(f"missing Codex should be reported without auth probing: {status}")
    _assert_no_secret_material(status)


def _with_env(root: Path, codex_bin: Path, assertion) -> None:
    home = root / "home"
    codex_home = home / ".codex"
    codex_home.mkdir(parents=True, exist_ok=True)
    auth_file = codex_home / "auth.json"
    auth_file.write_text('{"session":"fake-secret-must-not-leak"}\n', encoding="utf-8")
    auth_file.chmod(0o600)
    (codex_home / "config.toml").write_text(
        'model = "gpt-5.5"\nmodel_reasoning_effort = "xhigh"\n',
        encoding="utf-8",
    )

    old_values = {key: os.environ.get(key) for key in ("PATH", "HOME", "CODEX_HOME", "DEV_CONTROL_PLANE_CODEX_BIN")}
    try:
        os.environ["PATH"] = f"{codex_bin.parent}{os.pathsep}{old_values.get('PATH') or ''}"
        os.environ["HOME"] = str(home)
        os.environ["CODEX_HOME"] = str(codex_home)
        os.environ["DEV_CONTROL_PLANE_CODEX_BIN"] = str(codex_bin)
        assertion()
    finally:
        for key, value in old_values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _write_fake_codex(path: Path, *, authenticated: bool) -> None:
    login_status = "Logged in using ChatGPT" if authenticated else "Not logged in"
    login_code = 0 if authenticated else 1
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "if sys.argv[1:] == ['--version']:\n"
        "    print('codex-cli 0.128.0')\n"
        "    raise SystemExit(0)\n"
        "if sys.argv[1:] == ['login', 'status']:\n"
        f"    print({login_status!r})\n"
        f"    raise SystemExit({login_code})\n"
        "raise SystemExit(2)\n",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _assert_no_secret_material(payload: dict) -> None:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    for forbidden in ("fake-secret", "session", "auth.json", "Authorization", "Bearer"):
        if forbidden in serialized:
            raise AssertionError(f"Codex status leaked secret material {forbidden!r}: {payload}")


if __name__ == "__main__":
    main()
