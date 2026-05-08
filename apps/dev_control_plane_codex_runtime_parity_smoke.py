"""Smoke-check hosted Codex runtime parity, auth blockers and browser readiness."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (SRC, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dev_control_plane.execution import _prompt_consistency_gate, _run_codex_workspace_preflight  # noqa: E402
from dev_control_plane.toolchain import build_codex_runtime_parity_status  # noqa: E402


def main() -> None:
    with TemporaryDirectory(prefix="dev-control-plane-runtime-parity-") as tmp_raw:
        tmp = Path(tmp_raw)
        bin_dir = tmp / "tools" / "bin"
        bin_dir.mkdir(parents=True)
        workspace = tmp / "workspace"
        _create_git_workspace(workspace)
        _populate_tools(bin_dir, auth_mode="expired", fake_browser_ready=True)
        env = _hosted_env(tmp, bin_dir)

        old_values = {key: os.environ.get(key) for key in env}
        try:
            os.environ.update(env)
            checks = _run_codex_workspace_preflight(
                workspace,
                tmp / "run-expired",
                codex_bin=str(bin_dir / "codex"),
                target_id="wb-core",
                base_commit="base123",
                prompt_text="Run a repo-only docs task.",
                codex_model="gpt-5.5",
                codex_reasoning_effort="xhigh",
            )
        finally:
            for key, value in old_values.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        auth_check = _check_named(checks, "preflight_codex_authenticated")
        if auth_check.status != "failed" or "device-auth" not in str(auth_check.reason):
            raise AssertionError(f"expired Codex auth must block before Codex starts: {checks}")
        artifact_path = tmp / "run-expired" / "artifacts" / "environment_parity.json"
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        if artifact.get("codex", {}).get("auth_status") != "expired":
            raise AssertionError(f"environment parity artifact must record sanitized expired auth: {artifact}")

        _populate_tools(bin_dir, auth_mode="authenticated", fake_browser_ready=True)
        parity = build_codex_runtime_parity_status(
            env=env,
            workspace_path=workspace,
            codex_bin=str(bin_dir / "codex"),
            target_id="wb-core",
            prompt_text="Run Playwright browser smoke for WebCore UI.",
            codex_model="gpt-5.5",
            codex_reasoning_effort="xhigh",
            require_browser=True,
            launch_browser=True,
        )
        if parity.get("status") != "ready" or parity.get("webcore_ui_browser_ready") is not True:
            raise AssertionError(f"browser-ready hosted parity should pass with fake browser runtime: {parity}")
        default_prompt_gate = _prompt_consistency_gate(
            "Режим выполнения: repo-only, no live/deploy, no API endpoints, no UI, no Codex worker run\n"
            "Task: managed clone docs-only smoke.",
            execution_mode="repo-only, no live/deploy, no API endpoints, no UI, no Codex worker run",
            codex_run=True,
        )
        if default_prompt_gate.status != "passed":
            raise AssertionError(f"default execution-mode line alone must not block managed Codex smoke: {default_prompt_gate}")
        conflicting_prompt_gate = _prompt_consistency_gate(
            "Task: production lane patch.\nConstraint: no deploy.",
            execution_mode="production_lane",
            codex_run=True,
        )
        if conflicting_prompt_gate.status != "failed" or "production_lane conflicts" not in str(conflicting_prompt_gate.reason):
            raise AssertionError(f"production-lane/no-deploy conflict must block before Codex: {conflicting_prompt_gate}")
        serialized = json.dumps(parity, ensure_ascii=False, sort_keys=True)
        for forbidden in ("Authorization", "Bearer ", "auth.json", "sk-", "refresh-secret"):
            if forbidden in serialized:
                raise AssertionError(f"runtime parity leaked secret marker {forbidden}: {parity}")

    print("dev-control-plane-codex-runtime-parity-smoke passed")


def _hosted_env(tmp: Path, bin_dir: Path) -> dict[str, str]:
    return {
        "DEV_CONTROL_PLANE_STATE_DIR": str(tmp / "state"),
        "DEV_CONTROL_PLANE_RUNTIME_PROFILE": "hosted",
        "DEV_CONTROL_PLANE_TOOLCHAIN_BIN_DIR": str(bin_dir),
        "DEV_CONTROL_PLANE_CODEX_BIN": str(bin_dir / "codex"),
        "PATH": str(bin_dir),
        "HOME": str(tmp / "home"),
        "CODEX_HOME": str(tmp / "home" / ".codex"),
    }


def _populate_tools(bin_dir: Path, *, auth_mode: str, fake_browser_ready: bool) -> None:
    for item in bin_dir.iterdir():
        item.unlink()
    _write_fake_codex(bin_dir / "codex", auth_mode=auth_mode)
    for name in ("git", "pwd"):
        source = shutil.which(name)
        if not source:
            raise AssertionError(f"smoke host missing required tool: {name}")
        (bin_dir / name).symlink_to(source)
    _write_fake_python(bin_dir / "python3", fake_browser_ready=fake_browser_ready)
    for name in ("rg", "pip", "jq", "bash", "sh", "sed", "awk", "grep", "find", "xargs", "tar", "gzip", "unzip", "timeout", "node", "npm", "corepack", "pnpm", "yarn", "gh"):
        _write_stub(bin_dir / name, f"{name} smoke-version")


def _write_fake_codex(path: Path, *, auth_mode: str) -> None:
    if auth_mode == "authenticated":
        status_text = "Logged in using ChatGPT"
        code = 0
    else:
        status_text = "error: refresh_token_reused"
        code = 1
    path.write_text(
        f"#!{sys.executable}\n"
        "import sys\n"
        "if sys.argv[1:] == ['--version']:\n"
        "    print('codex-cli 0.128.0')\n"
        "    raise SystemExit(0)\n"
        "if sys.argv[1:] == ['login', 'status']:\n"
        f"    print({status_text!r})\n"
        f"    raise SystemExit({code})\n"
        "raise SystemExit('fake codex should not execute during parity smoke')\n",
        encoding="utf-8",
    )
    path.chmod(0o700)


def _write_fake_python(path: Path, *, fake_browser_ready: bool) -> None:
    browser_json = json.dumps(
        {
            "chromium_executable": "/tmp/dev-control-plane-smoke-chromium",
            "executable_exists": True,
            "launch_ok": True if fake_browser_ready else None,
        },
        sort_keys=True,
    )
    path.write_text(
        f"#!{sys.executable}\n"
        "import sys\n"
        "if sys.argv[1:] == ['--version']:\n"
        "    print('Python 3.12.0')\n"
        "    raise SystemExit(0)\n"
        "if sys.argv[1:3] == ['-m', 'venv']:\n"
        "    raise SystemExit(0)\n"
        "if sys.argv[1:2] == ['-c']:\n"
        "    script = sys.argv[2]\n"
        "    if 'import playwright' in script and 'sync_playwright' not in script:\n"
        "        print('playwright import ok')\n"
        "        raise SystemExit(0)\n"
        "    if 'sync_playwright' in script:\n"
        f"        print({browser_json!r})\n"
        "        raise SystemExit(0)\n"
        "print('Python 3.12.0')\n",
        encoding="utf-8",
    )
    path.chmod(0o700)


def _write_stub(path: Path, version: str) -> None:
    path.write_text(
        "#!/bin/sh\n"
        "case \"$1\" in\n"
        "  --version|-V|-v) echo \"$TOOL_VERSION\"; exit 0 ;;\n"
        "  -c) shift; exec /bin/sh -c \"$1\" ;;\n"
        "  *) echo \"$TOOL_VERSION\"; exit 0 ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    path.chmod(0o700)
    path.write_text(path.read_text(encoding="utf-8").replace("$TOOL_VERSION", version), encoding="utf-8")


def _create_git_workspace(path: Path) -> None:
    path.mkdir(parents=True)
    (path / "README.md").write_text("workspace\n", encoding="utf-8")
    _git(path, "init")
    _git(path, "config", "user.email", "smoke@example.invalid")
    _git(path, "config", "user.name", "Smoke Test")
    _git(path, "add", ".")
    _git(path, "commit", "-m", "Initial workspace")


def _git(cwd: Path, *args: str) -> None:
    completed = subprocess.run(("git", *args), cwd=cwd, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {completed.stdout}\n{completed.stderr}")


def _check_named(checks: object, name: str):
    for check in checks:
        if getattr(check, "name", None) == name:
            return check
    raise AssertionError(f"check {name!r} missing: {checks}")


if __name__ == "__main__":
    main()
