"""Smoke-check post-merge wb-core production-lane deploy resume flow."""

from __future__ import annotations

import json
from pathlib import Path
import os
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (SRC, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dev_control_plane.target_production import (  # noqa: E402
    DEFAULT_DEPLOY_RUNNER,
    DEFAULT_DEPLOY_TARGET_FILE,
    execute_wb_core_resume_deploy,
    target_production_resume_result_to_dict,
)

RUN_ID = "mcp-prod-20260507T162232Z-0d7bb0f7c4"
PR_URL = "https://github.com/orenvlad-ai/wb-core/pull/280"
PR_NUMBER = 280
MERGE_COMMIT = "f1dd35c427b5cda8907cb99a45343625166af735"
PRE_MERGE_MAIN = "8b781b25e788b73d4222724dd08a26cb3e717667"
CHANGED_FILE = "packages/adapters/templates/sheet_vitrina_v1_web_vitrina.html"


def main() -> None:
    with TemporaryDirectory(prefix="dev-control-plane-resume-deploy-") as tmp_raw:
        tmp = Path(tmp_raw)
        state_dir = tmp / "state"
        run_dir = state_dir / "runs" / RUN_ID
        workspace = state_dir / "workspaces" / RUN_ID / "wb-core"
        _create_workspace(workspace)
        _create_already_merged_run(run_dir, workspace)
        env = _ready_env(tmp, state_dir)
        github_runner = _github_ready_runner()
        ssh_runner = _ssh_ready_runner()

        dry_runner = _ResumeRunner()
        dry = execute_wb_core_resume_deploy(
            run_id=RUN_ID,
            state_dir=state_dir,
            execute=False,
            runner=dry_runner,
            env=env,
            github_runner=github_runner,
            ssh_runner=ssh_runner,
        )
        dry_payload = target_production_resume_result_to_dict(dry)
        if dry.status != "resume_dry_run_ready" or dry.blockers:
            raise AssertionError(f"resume dry-run eligibility must be ready: {dry_payload}")
        if "resume_preflight" not in dry.executed_steps or "merge_commit_verified" not in dry.executed_steps:
            raise AssertionError(f"dry-run must verify gates before deploy eligibility: {dry_payload}")
        if any(step in dry.executed_steps for step in ("target_lock_acquired", "backup_created", "deploy_live")):
            raise AssertionError(f"dry-run must not acquire lock, backup or deploy: {dry_payload}")
        dry_runner.assert_no_forbidden()
        _assert_artifact(run_dir / "artifacts" / "production_lane" / "resume_preflight" / "resume_deploy_preflight.json")
        _assert_artifact(run_dir / "artifacts" / "production_lane" / "resume_deploy_report.json")
        if (run_dir / "artifacts" / "production_lane" / "backup_result.json").exists():
            raise AssertionError("dry-run resume must not create backup_result artifact")

        no_codex_env = _ready_env(tmp, state_dir, bin_name="bin-no-codex", include_codex=False)
        no_codex = execute_wb_core_resume_deploy(
            run_id=RUN_ID,
            state_dir=state_dir,
            execute=False,
            runner=_ResumeRunner(),
            env=no_codex_env,
            github_runner=github_runner,
            ssh_runner=ssh_runner,
        )
        if no_codex.status != "resume_dry_run_ready" or "codex" in no_codex.plan.get("resume_preflight", {}).get("missing_required", []):
            raise AssertionError(
                "post-merge resume dry-run must not require Codex because it never reruns Codex: "
                f"{target_production_resume_result_to_dict(no_codex)}"
            )

        blocked_dir = state_dir / "runs" / "missing-merge"
        shutil.copytree(run_dir, blocked_dir)
        production_path = blocked_dir / "artifacts" / "production_lane" / "production_lane_result.json"
        blocked_payload = json.loads(production_path.read_text(encoding="utf-8"))
        blocked_payload["merge_commit"] = ""
        _write_json(production_path, blocked_payload)
        blocked = execute_wb_core_resume_deploy(
            run_id="missing-merge",
            state_dir=state_dir,
            execute=False,
            runner=_ResumeRunner(),
            env=env,
            github_runner=github_runner,
            ssh_runner=ssh_runner,
        )
        if blocked.status != "blocked" or "merge commit" not in " ".join(blocked.blockers):
            raise AssertionError(f"missing merge_commit must fail closed: {target_production_resume_result_to_dict(blocked)}")

        execute_runner = _ResumeRunner()
        executed = execute_wb_core_resume_deploy(
            run_id=RUN_ID,
            state_dir=state_dir,
            execute=True,
            runner=execute_runner,
            env=env,
            github_runner=github_runner,
            ssh_runner=ssh_runner,
        )
        executed_payload = target_production_resume_result_to_dict(executed)
        if executed.status != "post_deploy_passed" or executed.deploy_status != "passed":
            raise AssertionError(f"stubbed resume deploy must pass post-merge stages: {executed_payload}")
        for step in (
            "resume_preflight",
            "merge_commit_verified",
            "target_lock_acquired",
            "deploy_checkout",
            "backup_created",
            "deploy_dry_run",
            "deploy_live",
            "loopback_probe",
            "public_probe",
            "post_deploy_public_verify",
        ):
            if step not in executed.executed_steps:
                raise AssertionError(f"resume deploy missing step {step}: {executed_payload}")
        execute_runner.assert_no_forbidden()
        for artifact in (
            "backup_result.json",
            "deploy_result.json",
            "probe_result.json",
            "resume_deploy_result.json",
            "resume_deploy_report.json",
        ):
            _assert_artifact(run_dir / "artifacts" / "production_lane" / artifact)
        production_result = json.loads(
            (run_dir / "artifacts" / "production_lane" / "production_lane_result.json").read_text(encoding="utf-8")
        )
        if production_result.get("status") != "post_deploy_passed" or production_result.get("deploy_status") != "passed":
            raise AssertionError(f"resume result must be reflected in production report: {production_result}")
        _assert_no_secret(run_dir / "artifacts" / "production_lane")

    print("dev-control-plane-resume-production-deploy-smoke passed")


class _ResumeRunner:
    def __init__(self) -> None:
        self.commands: list[tuple[str, ...]] = []

    def __call__(self, command: Sequence[str], _cwd: Path | None) -> subprocess.CompletedProcess[str]:
        args = tuple(str(item) for item in command)
        self.commands.append(args)
        joined = " ".join(args)
        if args[:3] == ("git", "fetch", "origin"):
            return _ok(args)
        if args[:3] == ("git", "merge-base", "--is-ancestor"):
            return _ok(args)
        if args[:2] == ("git", "rev-parse"):
            return _ok(args, stdout=f"{MERGE_COMMIT}\n")
        if args[:3] == ("git", "checkout", "--detach") and args[3] == MERGE_COMMIT:
            return _ok(args)
        if args and args[0].endswith("ssh"):
            remote = args[-1]
            if "tar" in remote and "/opt/wb-core-runtime/backups/dev-control-plane" in remote:
                return _ok(args)
            return _fail(args, "unexpected ssh command")
        if args[:2] == ("python3", DEFAULT_DEPLOY_RUNNER):
            action = args[2] if len(args) > 2 else ""
            if action in {"print-plan", "deploy", "loopback-probe"}:
                return _ok(args, stdout="{\"ok\": true}\n")
            if action == "public-probe":
                return _ok(
                    args,
                    stdout=json.dumps(
                        {
                            "ok": True,
                            "routes": [
                                {"route": "operator_ui", "body_excerpt": "<button>Витрина 2</button>"},
                            ],
                        },
                        ensure_ascii=False,
                    )
                    + "\n",
                )
        return _fail(args, "unexpected command")

    def assert_no_forbidden(self) -> None:
        serialized = "\n".join(" ".join(command) for command in self.commands)
        forbidden = (
            " codex ",
            "gh pr create",
            "gh pr merge",
            "git commit",
            "git push",
            "checkout -B",
        )
        for token in forbidden:
            if token in f" {serialized} ":
                raise AssertionError(f"resume deploy must not run forbidden command {token!r}: {serialized}")


def _create_workspace(workspace: Path) -> None:
    (workspace / Path(CHANGED_FILE).parent).mkdir(parents=True)
    (workspace / CHANGED_FILE).write_text("<button>Витрина 2</button>\n", encoding="utf-8")
    (workspace / "README.md").write_text("# wb-core fixture\n", encoding="utf-8")
    (workspace / "AGENTS.md").write_text("Target rules fixture\n", encoding="utf-8")
    (workspace / "docs" / "architecture").mkdir(parents=True)
    (workspace / "docs" / "architecture" / "01.md").write_text("architecture\n", encoding="utf-8")
    (workspace / "docs" / "modules").mkdir(parents=True)
    (workspace / "docs" / "modules" / "01.md").write_text("module\n", encoding="utf-8")
    (workspace / "migration").mkdir(parents=True)
    (workspace / "migration" / "README.md").write_text("migration\n", encoding="utf-8")
    runner = workspace / DEFAULT_DEPLOY_RUNNER
    runner.parent.mkdir(parents=True)
    runner.write_text("# deploy runner fixture\n", encoding="utf-8")
    target = workspace / DEFAULT_DEPLOY_TARGET_FILE
    target.parent.mkdir(parents=True)
    target.write_text("{}\n", encoding="utf-8")
    _git(workspace.parent, "init", str(workspace))
    _git(workspace, "config", "user.email", "smoke@example.invalid")
    _git(workspace, "config", "user.name", "Smoke Test")
    _git(workspace, "add", ".")
    _git(workspace, "commit", "-m", "Initial fixture")


def _create_already_merged_run(run_dir: Path, workspace: Path) -> None:
    production_dir = run_dir / "artifacts" / "production_lane"
    production_dir.mkdir(parents=True)
    (run_dir / "verifier").mkdir(parents=True)
    rollback_plan = {
        "run_id": RUN_ID,
        "strategy": "git revert PR merge commit, then redeploy through approved WebCore runner",
        "rollback_base_commit": PRE_MERGE_MAIN,
        "merge_commit": MERGE_COMMIT,
        "target_branch": f"devcp/{RUN_ID}-fixture",
        "commands": [
            "git checkout main",
            "git pull --ff-only origin main",
            f"git revert -m 1 {MERGE_COMMIT}",
            "git push origin main  # only under explicit emergency rollback approval",
            f"WB_CORE_HOSTED_RUNTIME_TARGET_FILE={DEFAULT_DEPLOY_TARGET_FILE} python3 {DEFAULT_DEPLOY_RUNNER} deploy",
        ],
    }
    plan = {
        "target_project_id": "wb-core",
        "target_repo": "orenvlad-ai/wb-core",
        "target_repo_url": "https://github.com/orenvlad-ai/wb-core.git",
        "base_branch": "main",
        "source_mode": "remote_managed_clone",
        "execution_mode": "production_lane",
        "apply_mode": "target_pr_merge_deploy",
        "production_lane": True,
        "workspace_path": str(workspace),
        "run_dir": str(run_dir),
        "run_id": RUN_ID,
        "branch_name": f"devcp/{RUN_ID}-fixture",
        "changed_files": [CHANGED_FILE],
        "deploy_runner": DEFAULT_DEPLOY_RUNNER,
        "deploy_target_file": DEFAULT_DEPLOY_TARGET_FILE,
        "expected_public_label": "Витрина 2",
        "rollback_plan": rollback_plan,
    }
    production_result = {
        "status": "blocked",
        "allowed": True,
        "blockers": ["ssh: Could not resolve hostname wb-core-eu-root"],
        "warnings": [],
        "plan": plan,
        "executed_steps": [
            "production_toolchain_preflight",
            "target_lock_acquired",
            "target_commit",
            "target_push",
            "target_pr_created",
            "target_pr_merged",
        ],
        "target_branch": f"devcp/{RUN_ID}-fixture",
        "target_pr_url": PR_URL,
        "target_pr_number": PR_NUMBER,
        "pre_merge_main_commit": PRE_MERGE_MAIN,
        "merge_commit": MERGE_COMMIT,
        "backup_path": None,
        "deploy_status": "blocked",
        "public_verify_status": None,
        "rollback_plan_path": str(production_dir / "rollback_plan.json"),
    }
    run_record = {
        "run_id": RUN_ID,
        "target": "wb-core",
        "execution_mode": "production_lane",
        "status": "blocked",
        "result": {
            "verifier_status": "passed",
            "changed_files": [CHANGED_FILE],
            "target_pr_url": PR_URL,
            "merge_commit": MERGE_COMMIT,
        },
    }
    _write_json(production_dir / "rollback_plan.json", rollback_plan)
    _write_json(production_dir / "production_lane_result.json", production_result)
    _write_json(run_dir / "run.json", run_record)
    _write_json(run_dir / "verifier" / "verifier.json", {"status": "passed"})


def _ready_env(tmp: Path, state_dir: Path, *, bin_name: str = "bin", include_codex: bool = True) -> dict[str, str]:
    bin_dir = tmp / bin_name
    bin_dir.mkdir()
    for tool in ("git", "python3"):
        _symlink_required(tool, bin_dir / tool)
    for tool in ("rg", "gh", "ssh"):
        _write_stub(bin_dir / tool, f"{tool} smoke-version")
    if include_codex:
        _write_stub(bin_dir / "codex", "codex smoke-version")
    env = {
        "DEV_CONTROL_PLANE_STATE_DIR": str(state_dir),
        "DEV_CONTROL_PLANE_TOOLCHAIN_BIN_DIR": str(bin_dir),
        "DEV_CONTROL_PLANE_GITHUB_TOKEN": "github_pat_smoke_secret_token_0123456789abcdef",
        "DEV_CONTROL_PLANE_WB_CORE_DEPLOY_SSH_ALIAS": "wb-core-eu-root",
        "DEV_CONTROL_PLANE_WB_CORE_DEPLOY_SSH_IDENTITY_FILE": "/tmp/private-key-smoke",
        "DEV_CONTROL_PLANE_WB_CORE_DEPLOY_SSH_KNOWN_HOSTS": "/tmp/known-hosts-smoke",
        "PATH": str(bin_dir),
        "HOME": str(tmp / "home"),
        "CODEX_HOME": str(tmp / "home" / ".codex"),
    }
    if include_codex:
        env["DEV_CONTROL_PLANE_CODEX_BIN"] = str(bin_dir / "codex")
    return env


def _github_ready_runner():
    def _run(command: Sequence[str], _cwd: Path | None, _env: Mapping[str, str]) -> subprocess.CompletedProcess[str]:
        args = tuple(str(item) for item in command)
        if len(args) >= 3 and args[1:3] == ("auth", "status"):
            return _ok(args)
        if "repo" in args and "view" in args:
            return _ok(args, stdout=json.dumps({"nameWithOwner": "orenvlad-ai/wb-core", "viewerPermission": "WRITE"}))
        if args[:2] == ("git", "ls-remote"):
            return _ok(args, stdout=f"{MERGE_COMMIT}\trefs/heads/main\n")
        return _fail(args, "unexpected github auth command")

    return _run


def _ssh_ready_runner():
    def _run(command: Sequence[str], _cwd: Path | None, _env: Mapping[str, str]) -> subprocess.CompletedProcess[str]:
        args = tuple(str(item) for item in command)
        if args and args[0].endswith("ssh") and args[-1] == "true":
            return _ok(args)
        return _fail(args, "unexpected ssh readiness command")

    return _run


def _ok(args: Sequence[str], *, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=tuple(args), returncode=0, stdout=stdout, stderr=stderr)


def _fail(args: Sequence[str], stderr: str) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=tuple(args), returncode=1, stdout="", stderr=stderr)


def _assert_artifact(path: Path) -> None:
    if not path.exists():
        raise AssertionError(f"expected artifact missing: {path}")
    json.loads(path.read_text(encoding="utf-8"))


def _assert_no_secret(root: Path) -> None:
    serialized = "\n".join(path.read_text(encoding="utf-8") for path in root.rglob("*.json"))
    forbidden = (
        "github_pat_smoke_secret",
        "Authorization",
        "Bearer ",
        "BEGIN OPENSSH",
        "private-key-smoke",
        "known-hosts-smoke",
    )
    for token in forbidden:
        if token in serialized:
            raise AssertionError(f"resume artifacts leaked sensitive material token={token!r}")


def _symlink_required(name: str, target: Path) -> None:
    source = shutil.which(name)
    if not source:
        raise AssertionError(f"smoke host missing required tool: {name}")
    target.symlink_to(source)


def _write_stub(path: Path, version: str) -> None:
    path.write_text(
        "#!/bin/sh\n"
        "case \"$1\" in\n"
        "  --version|-V|-v) echo '%s'; exit 0 ;;\n"
        "  -c) shift; exec /bin/sh -c \"$1\" ;;\n"
        "  *) echo '%s'; exit 0 ;;\n"
        "esac\n" % (version, version),
        encoding="utf-8",
    )
    path.chmod(0o700)


def _git(cwd: Path, *args: str) -> None:
    completed = subprocess.run(("git", *args), cwd=cwd, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed\nstdout={completed.stdout}\nstderr={completed.stderr}")


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
