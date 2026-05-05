"""Smoke-check hosted Codex sandbox/model runtime config without real Codex."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (SRC, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dev_control_plane.execution import run_codex_cli  # noqa: E402
from dev_control_plane.runtime_config import load_runtime_config, runtime_config_public_dict, save_runtime_config  # noqa: E402
from dev_control_plane.secrets import get_openai_credentials  # noqa: E402
from dev_control_plane.target_projects import load_target_project_config  # noqa: E402


def main() -> None:
    with TemporaryDirectory(prefix="dev-control-plane-sandbox-model-") as tmp_raw:
        tmp = Path(tmp_raw)
        env = {
            "DEV_CONTROL_PLANE_STATE_DIR": str(tmp / "state"),
            "DEV_CONTROL_PLANE_RUNTIME_PROFILE": "hosted",
            "DEV_CONTROL_PLANE_RUNTIME_CONFIG_DIR": str(tmp / "config"),
        }
        config = load_runtime_config(env=env)
        if config.codex.sandbox_mode != "danger-full-access" or config.codex.sandbox_source != "hosted_default":
            raise AssertionError(f"hosted default must use explicit compatible sandbox: {config}")
        public = runtime_config_public_dict(config)
        serialized = json.dumps(public, ensure_ascii=False)
        for forbidden in ("OPENAI_API_KEY", "auth.json", "Bearer ", "test-key-secret"):
            if forbidden in serialized:
                raise AssertionError(f"runtime config status leaked secret marker {forbidden}: {public}")

        saved = save_runtime_config(
            {
                "profile": "fast",
                "codex": {"sandbox_mode": "danger-full-access"},
            },
            env=env,
        )
        if saved.openai.model != "gpt-5.4-mini" or saved.openai.reasoning_effort != "medium":
            raise AssertionError(f"fast profile must select lighter OpenAI config: {saved}")
        if saved.codex.model != "gpt-5.3-codex-spark" or saved.codex.reasoning_effort != "medium":
            raise AssertionError(f"fast profile must select lighter Codex config: {saved}")
        path = tmp / "config" / "runtime_config.json"
        if not path.exists() or path.stat().st_mode & 0o077:
            raise AssertionError(f"runtime config must be stored outside repo with safe mode: {oct(path.stat().st_mode)}")
        try:
            save_runtime_config({"openai": {"model": "not-a-real-model"}}, env=env)
        except Exception as exc:
            if "unsupported OpenAI model" not in str(exc):
                raise AssertionError(f"unsupported model must return controlled blocker: {exc}") from exc
        else:
            raise AssertionError("unsupported model must not be accepted")

        openai_env = {
            **env,
            "OPENAI_API_KEY": "test-key-secret",
        }
        credentials = get_openai_credentials(env=openai_env)
        if not credentials or credentials.model != "gpt-5.4-mini" or credentials.reasoning_effort != "medium":
            raise AssertionError(f"OpenAI credentials must use runtime model override without leaking key: {credentials}")

        _exercise_preflight_blocker(tmp, env)

    print("dev-control-plane-sandbox-model-smoke passed")


def _exercise_preflight_blocker(tmp: Path, env: Mapping[str, str]) -> None:
    target_repo = tmp / "target"
    config_path = tmp / "target.json"
    fake_codex = tmp / "fake-codex"
    bin_dir = tmp / "bin-no-rg"
    _create_target_repo(target_repo)
    _write_target_config(config_path, target_repo)
    _write_fake_codex(fake_codex)
    bin_dir.mkdir()
    _symlink_tool("git", bin_dir / "git")
    _symlink_tool("pwd", bin_dir / "pwd")
    old_values = {
        key: os.environ.get(key)
        for key in (
            "PATH",
            "DEV_CONTROL_PLANE_STATE_DIR",
            "DEV_CONTROL_PLANE_RUNTIME_PROFILE",
            "DEV_CONTROL_PLANE_RUNTIME_CONFIG_DIR",
            "DEV_CONTROL_PLANE_CODEX_BIN",
        )
    }
    try:
        os.environ.update(env)
        os.environ["PATH"] = str(bin_dir)
        os.environ["DEV_CONTROL_PLANE_CODEX_BIN"] = str(fake_codex)
        result = run_codex_cli(
            _task_spec(),
            target_config=load_target_project_config(config_path),
            step_id="step-001",
            state_dir=tmp / "state",
            allow_real_codex=True,
            codex_bin=str(fake_codex),
        )
    finally:
        for key, value in old_values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    if result.status != "blocked" or "managed workspace preflight failed" not in str(result.blocker_reason):
        raise AssertionError(f"missing rg must block before fake Codex execution: {result}")
    if (Path(result.workspace_path or "") / "SHOULD_NOT_EXIST.md").exists():
        raise AssertionError("preflight blocker must prevent Codex execution")


def _create_target_repo(repo: Path) -> None:
    (repo / "docs").mkdir(parents=True)
    (repo / "docs" / "existing.md").write_text("existing\n", encoding="utf-8")
    _git_checked(repo.parent, "init", str(repo))
    _git_checked(repo, "config", "user.email", "smoke@example.invalid")
    _git_checked(repo, "config", "user.name", "Smoke Test")
    _git_checked(repo, "add", ".")
    _git_checked(repo, "commit", "-m", "Initial target")


def _write_target_config(path: Path, repo: Path) -> None:
    payload = {
        "project_id": "sandbox-smoke",
        "display_name": "sandbox-smoke",
        "repo_path": str(repo),
        "source_of_truth_paths": ["docs/"],
        "derived_secondary_paths": ["derived_project_pack/"],
        "default_forbidden_paths": ["derived_project_pack/**"],
        "default_forbidden_actions": ["live_deploy", "ssh", "root_shell", "public_route_change"],
        "default_required_smokes": ["git diff --check"],
        "target_readonly_by_default": True,
        "execution_policy": {
            "allow_managed_clone_execution": True,
            "allow_direct_target_mutation": False,
            "allow_live_deploy": False,
            "allow_auto_merge": False,
            "require_explicit_real_codex_flag": True,
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _task_spec() -> dict[str, Any]:
    return {
        "id": "sandbox-preflight-smoke",
        "version": "1.0",
        "status": "frozen",
        "title": "Sandbox preflight smoke",
        "goal": "Block before Codex when managed workspace tools are unavailable.",
        "scope": ["docs/SHOULD_NOT_EXIST.md"],
        "not_in_scope": ["no target mutation"],
        "task_class": "L3",
        "class_reason": "Real Codex runner preflight gate.",
        "risks": ["sandbox/config regression"],
        "acceptance_criteria": ["preflight blocks before Codex"],
        "required_smokes": ["git diff --check"],
        "allowed_paths": ["docs/SHOULD_NOT_EXIST.md"],
        "forbidden_paths": ["derived_project_pack/**"],
        "allowed_actions": [],
        "forbidden_actions": [
            "live_deploy",
            "ssh",
            "root_shell",
            "public_route_change",
            "direct_target_mutation",
            "auto_merge",
            "execution_from_discussion",
        ],
        "human_gates": [],
        "target_project_id": "sandbox-smoke",
        "explicit_policy_note": "controlled smoke allows real Codex runner gate with fake binary",
        "sprint_steps": [
            {
                "id": "step-001",
                "sequence": 1,
                "title": "Preflight blocks",
                "goal": "Do not reach fake Codex when rg is missing.",
                "task_class": "L3",
                "scope": ["docs/SHOULD_NOT_EXIST.md"],
                "acceptance_criteria": ["preflight blocker returned"],
                "required_smokes": ["git diff --check"],
                "stop_conditions": ["stop on preflight failure"],
            }
        ],
    }


def _write_fake_codex(path: Path) -> None:
    path.write_text(
        "#!/usr/bin/env python3\n"
        "from pathlib import Path\n"
        "import sys\n"
        "workspace = Path(sys.argv[sys.argv.index('--cd') + 1])\n"
        "(workspace / 'SHOULD_NOT_EXIST.md').write_text('bad\\n', encoding='utf-8')\n"
        "raise SystemExit(0)\n",
        encoding="utf-8",
    )
    path.chmod(0o700)


def _symlink_tool(name: str, dest: Path) -> None:
    source = shutil.which(name)
    if not source:
        raise AssertionError(f"required smoke tool missing: {name}")
    dest.symlink_to(source)


def _git_checked(cwd: Path, *args: str) -> None:
    completed = subprocess.run(("git", *args), cwd=cwd, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise AssertionError(completed.stderr or completed.stdout)


if __name__ == "__main__":
    main()
