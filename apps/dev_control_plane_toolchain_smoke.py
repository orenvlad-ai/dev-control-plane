"""Smoke-check hosted toolchain diagnostics and managed workspace preflight."""

from __future__ import annotations

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

from dev_control_plane.execution import _run_codex_workspace_preflight  # noqa: E402
from dev_control_plane.toolchain import REQUIRE_GITHUB_CLI_ENV, build_toolchain_status, runtime_path  # noqa: E402


def main() -> None:
    with TemporaryDirectory(prefix="dev-control-plane-toolchain-") as tmp_raw:
        tmp = Path(tmp_raw)
        bin_dir = tmp / "state" / "../tools/bin"
        bin_dir = bin_dir.resolve()
        bin_dir.mkdir(parents=True)
        codex = bin_dir / "codex"
        _write_stub(codex, "codex-cli 0.128.0")
        _populate_required_tools(bin_dir, codex)
        env = {
            "DEV_CONTROL_PLANE_STATE_DIR": str(tmp / "state"),
            "DEV_CONTROL_PLANE_RUNTIME_PROFILE": "hosted",
            "DEV_CONTROL_PLANE_TOOLCHAIN_BIN_DIR": str(bin_dir),
            "DEV_CONTROL_PLANE_CODEX_BIN": str(codex),
            "PATH": str(bin_dir),
            "HOME": str(tmp / "home"),
            "CODEX_HOME": str(tmp / "home" / ".codex"),
        }
        workspace = tmp / "workspace"
        _create_git_workspace(workspace)

        status = build_toolchain_status(env=env, workspace_path=workspace, codex_bin=str(codex))
        if status.get("status") != "ready" or status.get("missing_required"):
            raise AssertionError(f"complete required toolchain must be ready: {status}")
        if str(bin_dir) not in runtime_path(env).split(os.pathsep):
            raise AssertionError(f"runtime PATH must include runtime-local tools dir: {runtime_path(env)}")
        prod_status = build_toolchain_status(env=env, workspace_path=workspace, codex_bin=str(codex), require_github_cli=True)
        gh_status = _tool_status(prod_status, "gh")
        if prod_status.get("status") != "ready" or prod_status.get("production_lane_github_cli_required") is not True:
            raise AssertionError(f"production-lane toolchain must be ready when gh is present: {prod_status}")
        if not gh_status.get("required") or gh_status.get("status") != "ready":
            raise AssertionError(f"gh must be required and ready for production-lane status: {prod_status}")
        serialized = str(status)
        for forbidden in ("OPENAI_API_KEY", "Bearer ", "auth.json", "sk-test", "Authorization"):
            if forbidden in serialized:
                raise AssertionError(f"toolchain diagnostics leaked secret marker {forbidden}: {status}")

        run_dir = tmp / "run"
        checks = _run_codex_workspace_preflight(workspace, run_dir, codex_bin=str(codex))
        failed = [check for check in checks if check.status == "failed"]
        if failed:
            raise AssertionError(f"preflight must pass when required tools are present: {failed}")
        if not (run_dir / "verifier" / "preflight" / "toolchain.json").exists():
            raise AssertionError("preflight must persist sanitized toolchain diagnostics")
        if not any(check.name == "preflight_workspace_write" and check.status == "passed" for check in checks):
            raise AssertionError(f"preflight must verify workspace-local writes: {checks}")

        no_rg_dir = _copy_without(bin_dir, tmp / "bin-no-rg", "rg")
        missing_rg_env = {
            **env,
            "DEV_CONTROL_PLANE_STATE_DIR": str(tmp / "missing-rg-state" / "state"),
            "DEV_CONTROL_PLANE_TOOLCHAIN_BIN_DIR": str(no_rg_dir),
            "DEV_CONTROL_PLANE_CODEX_BIN": str(no_rg_dir / "codex"),
            "PATH": str(no_rg_dir),
        }
        missing_rg = build_toolchain_status(env=missing_rg_env, workspace_path=workspace, codex_bin=str(no_rg_dir / "codex"))
        if "rg" not in missing_rg.get("missing_required", []):
            raise AssertionError(f"missing rg must be a controlled required-tool blocker: {missing_rg}")

        no_gh_dir = _copy_without(bin_dir, tmp / "bin-no-gh", "gh")
        missing_gh_env = {
            **env,
            "DEV_CONTROL_PLANE_STATE_DIR": str(tmp / "missing-gh-state" / "state"),
            "DEV_CONTROL_PLANE_TOOLCHAIN_BIN_DIR": str(no_gh_dir),
            "DEV_CONTROL_PLANE_CODEX_BIN": str(no_gh_dir / "codex"),
            "PATH": str(no_gh_dir),
        }
        missing_gh = build_toolchain_status(
            env=missing_gh_env,
            workspace_path=workspace,
            codex_bin=str(no_gh_dir / "codex"),
            require_github_cli=True,
        )
        if "gh" not in missing_gh.get("missing_required", []):
            raise AssertionError(f"production-lane preflight must require gh: {missing_gh}")
        env_required_gh = build_toolchain_status(
            env={**missing_gh_env, REQUIRE_GITHUB_CLI_ENV: "1"},
            workspace_path=workspace,
            codex_bin=str(no_gh_dir / "codex"),
        )
        if "gh" not in env_required_gh.get("missing_required", []):
            raise AssertionError(f"env-required production-lane preflight must require gh: {env_required_gh}")

        js_workspace = tmp / "js-workspace"
        _create_git_workspace(js_workspace)
        (js_workspace / "package.json").write_text('{"scripts":{"test":"echo ok"}}\n', encoding="utf-8")
        no_node_dir = _copy_without(bin_dir, tmp / "bin-no-node", "node", "npm")
        no_node_env = {
            **env,
            "DEV_CONTROL_PLANE_STATE_DIR": str(tmp / "missing-node-state" / "state"),
            "DEV_CONTROL_PLANE_TOOLCHAIN_BIN_DIR": str(no_node_dir),
            "DEV_CONTROL_PLANE_CODEX_BIN": str(no_node_dir / "codex"),
            "PATH": str(no_node_dir),
        }
        js_status = build_toolchain_status(env=no_node_env, workspace_path=js_workspace, codex_bin=str(no_node_dir / "codex"))
        if "node" not in js_status.get("missing_required", []) or "npm" not in js_status.get("missing_required", []):
            raise AssertionError(f"JS target must require node/npm: {js_status}")

    print("dev-control-plane-toolchain-smoke passed")


def _populate_required_tools(bin_dir: Path, codex: Path) -> None:
    real_required = {
        "git": "git",
        "python3": "python3",
        "python3-venv": "python3",
        "pwd": "pwd",
    }
    for dest_name, source_name in real_required.items():
        if dest_name == "python3-venv":
            continue
        source = shutil.which(source_name)
        if not source:
            raise AssertionError(f"smoke host missing required tool: {source_name}")
        (bin_dir / dest_name).symlink_to(source)
    for name in (
        "rg",
        "pip",
        "jq",
        "bash",
        "sh",
        "sed",
        "awk",
        "grep",
        "find",
        "xargs",
        "tar",
        "gzip",
        "unzip",
        "timeout",
        "node",
        "npm",
        "corepack",
        "pnpm",
        "yarn",
        "rsync",
        "ssh",
        "gh",
    ):
        if name == "codex":
            continue
        _write_stub(bin_dir / name, f"{name} smoke-version")
    if not codex.exists():
        _write_stub(codex, "codex-cli 0.128.0")


def _tool_status(status: dict, name: str) -> dict:
    for item in status.get("tools", []):
        if item.get("name") == name:
            return item
    raise AssertionError(f"tool {name!r} missing from status: {status}")


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
    _git(path.parent, "init", str(path))
    _git(path, "config", "user.email", "smoke@example.invalid")
    _git(path, "config", "user.name", "Smoke Test")
    _git(path, "add", ".")
    _git(path, "commit", "-m", "Initial workspace")


def _copy_without(source: Path, destination: Path, *excluded: str) -> Path:
    destination.mkdir(parents=True)
    for item in source.iterdir():
        if item.name in set(excluded):
            continue
        target = destination / item.name
        if item.is_symlink():
            target.symlink_to(os.readlink(item))
        else:
            shutil.copy2(item, target)
    return destination


def _git(cwd: Path, *args: str) -> None:
    completed = subprocess.run(("git", *args), cwd=cwd, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {completed.stdout}\n{completed.stderr}")


if __name__ == "__main__":
    main()
