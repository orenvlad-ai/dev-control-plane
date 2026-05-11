"""Smoke-check explicit wb-core production lane gates and dry-run plan."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
from tempfile import TemporaryDirectory
from typing import Any, Mapping
from urllib import request as urllib_request

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (SRC, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dev_control_plane.target_production import (  # noqa: E402
    ProductionDiffMismatchError,
    acquire_wb_core_production_lock,
    build_wb_core_production_plan,
    execute_wb_core_production_lane,
    inspect_wb_core_production_lock,
    release_wb_core_production_lock,
    _ensure_clean_expected_workspace,
    _git_changed_files,
    _prepare_workspace_for_verified_diff,
    _production_lane_toolchain_preflight,
    _safe_command_output,
    _verify_public_operator_label,
    normalize_changed_files,
)

RUNNER = ROOT / "apps" / "dev_control_plane_runner.py"
SERVER = ROOT / "apps" / "dev_control_plane_server.py"
TEMPLATE_PATH = "packages/adapters/templates/sheet_vitrina_v1_web_vitrina.html"


def main() -> None:
    with TemporaryDirectory(prefix="dev-control-plane-target-production-") as tmp_raw:
        tmp = Path(tmp_raw)
        workspace = tmp / "state" / "workspaces" / "run-prod-smoke" / "wb-core"
        run_dir = tmp / "state" / "runs" / "run-prod-smoke"
        _create_workspace(workspace)
        payload = _clean_payload(workspace, run_dir)

        plan = build_wb_core_production_plan(payload)
        if not plan.allowed:
            raise AssertionError(f"clean production lane plan must be allowed: {plan}")
        if plan.plan.get("branch_name", "").startswith("devcp/") is False:
            raise AssertionError(f"branch must use devcp prefix: {plan}")
        if plan.plan.get("rollback_plan", {}).get("commands") is None:
            raise AssertionError(f"rollback plan is required: {plan}")
        if not plan.plan.get("target_rules", {}).get("rules_loaded_into_context"):
            raise AssertionError(f"target rules must be loaded: {plan}")
        if plan.plan.get("execution_mode") != "production_lane" or plan.plan.get("apply_mode") != "target_pr_merge_deploy":
            raise AssertionError(f"production lane mode must be explicit: {plan}")
        if plan.plan.get("lock", {}).get("status") != "free":
            raise AssertionError(f"clean plan must expose free target lock: {plan}")
        if "deploy --dry-run" not in "\n".join(plan.plan.get("deploy_commands", [])):
            raise AssertionError(f"deploy dry-run must be part of plan: {plan}")
        if "wb-core PR" not in plan.plan.get("pr_title", ""):
            raise AssertionError(f"PR title must be Russian and task-specific: {plan}")

        dry_run = execute_wb_core_production_lane(payload, execute=False)
        if dry_run.status != "dry_run_ready" or not dry_run.rollback_plan_path:
            raise AssertionError(f"dry-run production lane must not mutate but must write rollback plan: {dry_run}")
        if "gh" not in json.dumps(dry_run.plan.get("execution_commands", []), ensure_ascii=False):
            raise AssertionError(f"dry-run must expose target PR commands: {dry_run}")
        if inspect_wb_core_production_lock(workspace_path=workspace, run_dir=run_dir, run_id=payload["run_id"])["status"] != "free":
            raise AssertionError("dry-run must not acquire production target lock")
        _assert_production_preflight_blocks_missing_gh(tmp, workspace, run_dir)
        _assert_production_preflight_blocks_missing_github_auth(tmp, workspace, run_dir)
        _assert_production_preflight_blocks_missing_ssh_target(tmp, workspace, run_dir)
        _assert_production_preflight_accepts_stubbed_github_auth(tmp, workspace, run_dir)
        _assert_path_normalization_is_shared()
        _assert_promotion_workspace_diff_match_passes(tmp, workspace)
        _assert_promotion_workspace_diff_mismatch_blocks(tmp, workspace)
        _assert_verified_diff_artifact_prepares_dirty_workspace(tmp, workspace)
        _assert_verified_workspace_source_does_not_require_patch_transport(tmp, payload)

        _assert_denied({**payload, "verifier_status": "failed"}, "verifier")
        _assert_denied({**payload, "changed_files": ["runtime/unsafe.py"]}, "protected/forbidden")
        _assert_denied({**payload, "secrets_scan_status": "failed"}, "secrets")
        _assert_denied({**payload, "push_to_main": True}, "direct push")
        _assert_denied({**payload, "commit_message": "DevControl change"}, "Russian")
        _assert_denied({**payload, "execution_mode": "managed_clone_only"}, "production-lane endpoint")
        _assert_denied({**payload, "production_lane": False}, "production_lane flag")
        auth_aware_probe = {
            "ok": True,
            "auth": {"mode": "app_session_cookie", "cookie_configured": True},
            "routes": [
                {"route": "operator_ui", "body_excerpt": "<button>Витрина 2</button>"},
            ],
        }
        if _verify_public_operator_label("Витрина 2", auth_aware_probe) != "passed":
            raise AssertionError("post-deploy verify must accept auth-aware public-probe payload")
        if _verify_public_operator_label("Другая строка", auth_aware_probe) != "failed":
            raise AssertionError("post-deploy verify must still check expected public marker")
        failed_probe_output = subprocess.CompletedProcess(
            args=("python3", "runner.py", "loopback-probe"),
            returncode=1,
            stdout=json.dumps(
                {
                    "ok": False,
                    "target_id": "wb-core",
                    "base_url": "http://127.0.0.1:8765",
                    "routes": [
                        {
                            "route": "web_vitrina_page",
                            "http_status": 200,
                            "ok": False,
                            "detail": "expected tokens missing=['data-top-panel']",
                            "body_excerpt": "<html>ok body tail must not hide failure</html>",
                        },
                        {
                            "route": "status",
                            "http_status": 200,
                            "ok": True,
                            "detail": "200 JSON shape ok",
                            "body_excerpt": "large successful route body",
                        },
                    ],
                },
                ensure_ascii=False,
            ),
            stderr="",
        )
        summarized_probe = _safe_command_output(failed_probe_output)
        if "route=web_vitrina_page" not in summarized_probe or "data-top-panel" not in summarized_probe:
            raise AssertionError(f"failed probe output must preserve failing route detail: {summarized_probe}")
        if "large successful route body" in summarized_probe:
            raise AssertionError(f"failed probe output must not be replaced by successful route body tail: {summarized_probe}")

        lock = acquire_wb_core_production_lock(workspace_path=workspace, run_dir=run_dir, run_id="active-smoke")
        try:
            locked = build_wb_core_production_plan(payload)
            if locked.allowed or not any("locked by active run" in blocker for blocker in locked.blockers):
                raise AssertionError(f"active target lock must block production lane: {locked}")
        finally:
            release_wb_core_production_lock(lock)
        if inspect_wb_core_production_lock(workspace_path=workspace, run_dir=run_dir, run_id=payload["run_id"])["status"] != "free":
            raise AssertionError("target lock must be released after success/fail path")

        missing_docs = tmp / "state" / "workspaces" / "run-missing-docs" / "wb-core"
        _create_workspace(missing_docs, docs=False)
        _assert_denied({**payload, "workspace_path": str(missing_docs)}, "target rules")

        payload_path = tmp / "payload.json"
        _write_json(payload_path, payload)
        runner_plan = _run_json([sys.executable, str(RUNNER), "target-production-plan", "--input", str(payload_path)])
        if runner_plan.get("status") != "allowed":
            raise AssertionError(f"runner production plan must use helper: {runner_plan}")
        runner_dry = _run_json([sys.executable, str(RUNNER), "target-production-run", "--input", str(payload_path)])
        if runner_dry.get("status") != "dry_run_ready":
            raise AssertionError(f"runner dry-run must not execute mutation: {runner_dry}")

        server = subprocess.Popen(
            [
                sys.executable,
                str(SERVER),
                "--host",
                "127.0.0.1",
                "--port",
                "0",
                "--state-dir",
                str(tmp / "server-state"),
            ],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            started = json.loads(server.stdout.readline())
            base_url = f"http://127.0.0.1:{started['port']}"
            _wait_ready(base_url)
            state = _get_json(base_url + "/api/state")
            if state.get("target_production_lane_enabled") is not True:
                raise AssertionError(f"server must expose production lane policy: {state}")
            server_plan = _post_json(base_url + "/api/target-production/plan", payload)
            if server_plan.get("status") != "allowed":
                raise AssertionError(f"server production endpoint must use helper: {server_plan}")
        finally:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()

    print("dev-control-plane-target-production-smoke passed")


def _clean_payload(workspace: Path, run_dir: Path) -> dict[str, Any]:
    return {
        "target_project_id": "wb-core",
        "target_repo": "orenvlad-ai/wb-core",
        "target_repo_url": "https://github.com/orenvlad-ai/wb-core.git",
        "base_branch": "main",
        "run_id": "run-prod-smoke",
        "run_dir": str(run_dir),
        "workspace_path": str(workspace),
        "task_spec_id": "task-prod-smoke",
        "task_summary": "Микрозадача: заменить видимый label «Витрина» на «Витрина 2».",
        "changed_files": [TEMPLATE_PATH],
        "verifier_status": "passed",
        "forbidden_path_hits": [],
        "secrets_scan_status": "passed",
        "docs_update_status": "not_required",
        "expected_public_label": "Витрина 2",
        "commit_message": "Изменить label Витрина через DevControl (run-prod-smoke)",
        "pr_title": "Изменить wb-core PR label Витрина через DevControl",
    }


def _create_workspace(workspace: Path, *, docs: bool = True) -> None:
    (workspace / "packages" / "adapters" / "templates").mkdir(parents=True)
    (workspace / TEMPLATE_PATH).write_text("<button>Витрина 2</button>\n", encoding="utf-8")
    (workspace / "README.md").write_text("# wb-core fixture\n", encoding="utf-8")
    if docs:
        (workspace / "docs" / "architecture").mkdir(parents=True)
        (workspace / "docs" / "architecture" / "01.md").write_text("architecture\n", encoding="utf-8")
        (workspace / "docs" / "modules").mkdir(parents=True)
        (workspace / "docs" / "modules" / "01.md").write_text("module\n", encoding="utf-8")
        (workspace / "migration").mkdir(parents=True)
        (workspace / "migration" / "README.md").write_text("migration\n", encoding="utf-8")
    runner = workspace / "apps" / "registry_upload_http_entrypoint_hosted_runtime.py"
    runner.parent.mkdir(parents=True)
    runner.write_text("# deploy runner fixture\n", encoding="utf-8")
    target = workspace / "artifacts" / "registry_upload_http_entrypoint" / "input" / "hosted_runtime_target__europe_api.json"
    target.parent.mkdir(parents=True)
    target.write_text("{}\n", encoding="utf-8")
    _git(workspace.parent, "init", str(workspace))
    _git(workspace, "config", "user.email", "smoke@example.invalid")
    _git(workspace, "config", "user.name", "Smoke Test")
    _git(workspace, "add", ".")
    _git(workspace, "commit", "-m", "Initial fixture")
    (workspace / TEMPLATE_PATH).write_text("<button>Витрина 2</button>\n", encoding="utf-8")


def _assert_denied(payload: Mapping[str, Any], token: str) -> None:
    decision = build_wb_core_production_plan(payload)
    if decision.allowed or not any(token in blocker for blocker in decision.blockers):
        raise AssertionError(f"production lane must be denied by {token}: {decision}")


def _assert_promotion_workspace_diff_mismatch_blocks(tmp: Path, source_workspace: Path) -> None:
    mismatch = tmp / "state" / "workspaces" / "run-prod-mismatch" / "wb-core"
    shutil.copytree(source_workspace, mismatch, ignore=shutil.ignore_patterns(".git"))
    _git(mismatch.parent, "init", str(mismatch))
    _git(mismatch, "config", "user.email", "smoke@example.invalid")
    _git(mismatch, "config", "user.name", "Smoke Test")
    _git(mismatch, "add", ".")
    _git(mismatch, "commit", "-m", "Initial mismatch fixture")
    (mismatch / TEMPLATE_PATH).write_text("<button>Витрина 3</button>\n", encoding="utf-8")
    expected = [TEMPLATE_PATH, "docs/new_untracked_from_verifier.md"]
    try:
        _ensure_clean_expected_workspace(mismatch, expected)
    except ProductionDiffMismatchError as exc:
        text = str(exc)
        if text != "promotion workspace diff does not match verified diff; do not deploy":
            raise AssertionError(f"diff mismatch blocker must be exact: {exc}") from exc
        diagnostics = exc.diagnostics
        if "docs/new_untracked_from_verifier.md" not in diagnostics.get("missing_from_promotion", []):
            raise AssertionError(f"diff mismatch diagnostics must include missing expected file: {diagnostics}")
        if diagnostics.get("verifier_changed_files") != list(normalize_changed_files(expected)):
            raise AssertionError(f"diagnostics must expose normalized verifier files: {diagnostics}")
    else:
        raise AssertionError("promotion diff mismatch must block before merge/deploy")
    extra = mismatch / "docs" / "unexpected_extra.md"
    extra.write_text("extra\n", encoding="utf-8")
    try:
        _ensure_clean_expected_workspace(mismatch, [TEMPLATE_PATH])
    except ProductionDiffMismatchError as exc:
        diagnostics = exc.diagnostics
        if "docs/unexpected_extra.md" not in diagnostics.get("extra_in_promotion", []):
            raise AssertionError(f"diff mismatch diagnostics must include extra untracked file: {diagnostics}")
        if "docs/unexpected_extra.md" not in diagnostics.get("untracked_files", []):
            raise AssertionError(f"diff mismatch diagnostics must expose untracked files: {diagnostics}")
        if not diagnostics.get("promotion_workspace_changed_files"):
            raise AssertionError(f"diagnostics must expose promotion workspace files: {diagnostics}")
    else:
        raise AssertionError("extra untracked file must block promotion diff gate")


def _assert_promotion_workspace_diff_match_passes(tmp: Path, source_workspace: Path) -> None:
    match = tmp / "state" / "workspaces" / "run-prod-match" / "wb-core"
    shutil.copytree(source_workspace, match, ignore=shutil.ignore_patterns(".git"))
    _git(match.parent, "init", str(match))
    _git(match, "config", "user.email", "smoke@example.invalid")
    _git(match, "config", "user.name", "Smoke Test")
    _git(match, "add", ".")
    _git(match, "commit", "-m", "Initial match fixture")
    (match / TEMPLATE_PATH).write_text("<button>Витрина 4</button>\n", encoding="utf-8")
    _ensure_clean_expected_workspace(match, [TEMPLATE_PATH])


def _assert_path_normalization_is_shared() -> None:
    raw = ["./packages/application/example.py", "packages\\application\\example.py", "/apps/example_smoke.py"]
    normalized = normalize_changed_files(raw)
    if normalized != ("apps/example_smoke.py", "packages/application/example.py"):
        raise AssertionError(f"changed_files normalization must be deterministic and repo-relative: {normalized}")


def _assert_verified_diff_artifact_prepares_dirty_workspace(tmp: Path, source_workspace: Path) -> None:
    fixture = tmp / "state" / "workspaces" / "run-prod-diff-artifact" / "wb-core"
    shutil.copytree(source_workspace, fixture, ignore=shutil.ignore_patterns(".git"))
    _git(fixture.parent, "init", str(fixture))
    _git(fixture, "config", "user.email", "smoke@example.invalid")
    _git(fixture, "config", "user.name", "Smoke Test")
    _git(fixture, "add", ".")
    _git(fixture, "commit", "-m", "Initial diff artifact fixture")
    base = _git(fixture, "rev-parse", "HEAD").strip()
    (fixture / TEMPLATE_PATH).write_text("<button>Витрина artifact</button>\n", encoding="utf-8")
    diff_path = tmp / "verified.patch"
    diff_path.write_text(_git(fixture, "diff", "--binary", "HEAD", "--", "."), encoding="utf-8")
    _git(fixture, "reset", "--hard", "HEAD")
    (fixture / "docs" / "stale_untracked.md").write_text("stale\n", encoding="utf-8")
    plan = {
        "changed_files": [TEMPLATE_PATH],
        "diff_artifact_path": str(diff_path),
        "run_start_base_ref": base,
        "verifier_base_commit": base,
    }
    _prepare_workspace_for_verified_diff(fixture, plan, run_dir=tmp)
    if "docs/stale_untracked.md" in _git_changed_files(fixture):
        raise AssertionError("production workspace preparation must clean stale untracked files before applying verified diff")
    if _git_changed_files(fixture) != (TEMPLATE_PATH,):
        raise AssertionError(f"verified diff artifact must reproduce verifier changed_files exactly: {_git_changed_files(fixture)}")
    if plan.get("diff_apply_status") != "applied":
        raise AssertionError(f"diff apply status must be recorded: {plan}")


def _assert_verified_workspace_source_does_not_require_patch_transport(tmp: Path, payload: Mapping[str, Any]) -> None:
    corrupt = tmp / "corrupt.diff"
    corrupt.write_text("diff --git a/README.md b/README.md\ncorrupt patch\n", encoding="utf-8")
    direct = build_wb_core_production_plan(
        {
            **payload,
            "run_id": "run-prod-direct-workspace",
            "diff_path": str(corrupt),
            "verified_workspace_source": True,
        }
    )
    if not direct.allowed:
        raise AssertionError(f"verified workspace source must not be denied because diff.patch is audit-only: {direct}")
    if direct.plan.get("diff_artifact_transport_used") is not False or direct.plan.get("verified_workspace_source") is not True:
        raise AssertionError(f"ordinary direct lane must declare verified clone as source of truth: {direct.plan}")


def _assert_production_preflight_blocks_missing_gh(tmp: Path, workspace: Path, run_dir: Path) -> None:
    bin_dir = tmp / "bin-no-gh-production"
    bin_dir.mkdir()
    _symlink_required("git", bin_dir / "git")
    _symlink_required("python3", bin_dir / "python3")
    _write_stub(bin_dir / "rg", "rg smoke-version")
    _write_stub(bin_dir / "codex", "codex-cli smoke-version")
    env = {
        "DEV_CONTROL_PLANE_STATE_DIR": str(tmp / "missing-gh-state" / "state"),
        "DEV_CONTROL_PLANE_TOOLCHAIN_BIN_DIR": str(bin_dir),
        "DEV_CONTROL_PLANE_CODEX_BIN": str(bin_dir / "codex"),
        "PATH": str(bin_dir),
        "HOME": str(tmp / "home"),
        "CODEX_HOME": str(tmp / "home" / ".codex"),
    }
    artifacts_dir = run_dir / "artifacts" / "production_lane_missing_gh"
    try:
        _production_lane_toolchain_preflight(workspace=workspace, artifacts_dir=artifacts_dir, env=env)
    except RuntimeError as exc:
        if "gh" not in str(exc) or "production lane preflight failed" not in str(exc):
            raise AssertionError(f"missing gh blocker must be controlled and explicit: {exc}") from exc
    else:
        raise AssertionError("production-lane preflight must block when gh is missing")
    preflight_path = artifacts_dir / "preflight" / "production_lane_toolchain.json"
    if not preflight_path.exists():
        raise AssertionError("production-lane preflight must persist sanitized diagnostics")
    persisted = json.loads(preflight_path.read_text(encoding="utf-8"))
    if "gh" not in persisted.get("missing_required", []):
        raise AssertionError(f"persisted preflight diagnostics must show missing gh: {persisted}")
    if inspect_wb_core_production_lock(workspace_path=workspace, run_dir=run_dir, run_id="missing-gh-smoke")["status"] != "free":
        raise AssertionError("missing gh preflight must not acquire target production lock")


def _assert_production_preflight_blocks_missing_github_auth(tmp: Path, workspace: Path, run_dir: Path) -> None:
    bin_dir = _production_bin_dir(tmp, "bin-missing-github-auth")
    env = _ssh_ready_env(_production_preflight_env(tmp, bin_dir, "missing-github-auth-state"))
    artifacts_dir = run_dir / "artifacts" / "production_lane_missing_github_auth"
    try:
        _production_lane_toolchain_preflight(
            workspace=workspace,
            artifacts_dir=artifacts_dir,
            env=env,
            github_runner=_github_ready_runner(),
            ssh_runner=_ssh_ready_runner(),
        )
    except RuntimeError as exc:
        text = str(exc)
        if "GitHub runtime token is missing" not in text or "production lane preflight failed" not in text:
            raise AssertionError(f"missing GitHub auth blocker must be controlled and explicit: {exc}") from exc
    else:
        raise AssertionError("production-lane preflight must block before target commit when GitHub auth is missing")
    persisted = json.loads((artifacts_dir / "preflight" / "production_lane_toolchain.json").read_text(encoding="utf-8"))
    github = persisted.get("github_auth", {})
    if github.get("status") != "missing" or github.get("token_present") is not False:
        raise AssertionError(f"persisted preflight diagnostics must show missing GitHub auth: {persisted}")
    if "github_pat_" in json.dumps(persisted, ensure_ascii=False):
        raise AssertionError(f"persisted GitHub auth diagnostics must not leak tokens: {persisted}")
    if inspect_wb_core_production_lock(workspace_path=workspace, run_dir=run_dir, run_id="missing-github-auth-smoke")["status"] != "free":
        raise AssertionError("missing GitHub auth preflight must not acquire target production lock")


def _assert_production_preflight_blocks_missing_ssh_target(tmp: Path, workspace: Path, run_dir: Path) -> None:
    bin_dir = _production_bin_dir(tmp, "bin-missing-ssh-target")
    env = {
        **_production_preflight_env(tmp, bin_dir, "missing-ssh-target-state"),
        "DEV_CONTROL_PLANE_GITHUB_TOKEN": "github_pat_smoke_secret_token_0123456789abcdef",
    }
    artifacts_dir = run_dir / "artifacts" / "production_lane_missing_ssh_target"
    try:
        _production_lane_toolchain_preflight(
            workspace=workspace,
            artifacts_dir=artifacts_dir,
            env=env,
            github_runner=_github_ready_runner(),
            ssh_runner=_ssh_ready_runner(),
        )
    except RuntimeError as exc:
        text = str(exc)
        if "wb-core deploy SSH target is missing" not in text or "production lane preflight failed" not in text:
            raise AssertionError(f"missing SSH target blocker must be controlled and explicit: {exc}") from exc
    else:
        raise AssertionError("production-lane preflight must block before target commit when SSH target is missing")
    persisted = json.loads((artifacts_dir / "preflight" / "production_lane_toolchain.json").read_text(encoding="utf-8"))
    ssh = persisted.get("ssh_deploy", {})
    if ssh.get("status") != "missing" or ssh.get("configured") is not False:
        raise AssertionError(f"persisted preflight diagnostics must show missing SSH target: {persisted}")
    if "private-key" in json.dumps(persisted, ensure_ascii=False):
        raise AssertionError(f"persisted SSH diagnostics must not leak key paths/material: {persisted}")
    if inspect_wb_core_production_lock(workspace_path=workspace, run_dir=run_dir, run_id="missing-ssh-target-smoke")["status"] != "free":
        raise AssertionError("missing SSH target preflight must not acquire target production lock")


def _assert_production_preflight_accepts_stubbed_github_auth(tmp: Path, workspace: Path, run_dir: Path) -> None:
    bin_dir = _production_bin_dir(tmp, "bin-ready-github-auth")
    env = _ssh_ready_env(
        {
            **_production_preflight_env(tmp, bin_dir, "ready-github-auth-state"),
            "DEV_CONTROL_PLANE_GITHUB_TOKEN": "github_pat_smoke_secret_token_0123456789abcdef",
        }
    )
    artifacts_dir = run_dir / "artifacts" / "production_lane_ready_github_auth"
    status = _production_lane_toolchain_preflight(
        workspace=workspace,
        artifacts_dir=artifacts_dir,
        env=env,
        github_runner=_github_ready_runner(),
        ssh_runner=_ssh_ready_runner(),
    )
    github = status.get("github_auth", {})
    if github.get("status") != "ready" or github.get("repo_write_permission") is not True:
        raise AssertionError(f"stubbed GitHub auth preflight must pass: {status}")
    ssh = status.get("ssh_deploy", {})
    if ssh.get("status") != "ready" or ssh.get("remote_ready") is not True:
        raise AssertionError(f"stubbed SSH deploy preflight must pass: {status}")
    askpass = artifacts_dir / "preflight" / "git-askpass.sh"
    if not askpass.exists():
        raise AssertionError("GitHub auth preflight must create a token-free askpass helper for git push")
    if "github_pat_smoke_secret" in askpass.read_text(encoding="utf-8"):
        raise AssertionError("askpass helper must not write token content")
    serialized = json.dumps(status, ensure_ascii=False)
    if "github_pat_smoke_secret" in serialized:
        raise AssertionError(f"GitHub auth preflight status leaked token: {status}")
    if "private-key-smoke" in serialized:
        raise AssertionError(f"SSH preflight status leaked private key path: {status}")


def _production_bin_dir(tmp: Path, name: str) -> Path:
    bin_dir = tmp / name
    bin_dir.mkdir()
    _symlink_required("git", bin_dir / "git")
    _symlink_required("python3", bin_dir / "python3")
    for tool in ("rg", "codex", "gh", "ssh"):
        _write_stub(bin_dir / tool, f"{tool} smoke-version")
    return bin_dir


def _production_preflight_env(tmp: Path, bin_dir: Path, state_name: str) -> dict[str, str]:
    return {
        "DEV_CONTROL_PLANE_STATE_DIR": str(tmp / state_name / "state"),
        "DEV_CONTROL_PLANE_TOOLCHAIN_BIN_DIR": str(bin_dir),
        "DEV_CONTROL_PLANE_CODEX_BIN": str(bin_dir / "codex"),
        "PATH": str(bin_dir),
        "HOME": str(tmp / "home"),
        "CODEX_HOME": str(tmp / "home" / ".codex"),
    }


def _ssh_ready_env(env: Mapping[str, str]) -> dict[str, str]:
    return {
        **dict(env),
        "DEV_CONTROL_PLANE_WB_CORE_DEPLOY_SSH_ALIAS": "wb-core-eu-root",
        "DEV_CONTROL_PLANE_WB_CORE_DEPLOY_SSH_IDENTITY_FILE": "/tmp/private-key-smoke",
        "DEV_CONTROL_PLANE_WB_CORE_DEPLOY_SSH_KNOWN_HOSTS": "/tmp/known-hosts-smoke",
    }


def _github_ready_runner():
    def _run(command, _cwd, _env):
        args = tuple(command)
        if len(args) >= 3 and args[1:3] == ("auth", "status"):
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")
        if "repo" in args and "view" in args:
            return subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout=json.dumps({"nameWithOwner": "orenvlad-ai/wb-core", "viewerPermission": "WRITE"}),
                stderr="",
            )
        if args[:2] == ("git", "ls-remote"):
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="abc\trefs/heads/main\n", stderr="")
        return subprocess.CompletedProcess(args=args, returncode=1, stdout="", stderr="unexpected command")

    return _run


def _ssh_ready_runner():
    def _run(command, _cwd, _env):
        args = tuple(command)
        if args and str(args[0]).endswith("ssh") and args[-1] == "true":
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")
        return subprocess.CompletedProcess(args=args, returncode=1, stdout="", stderr="unexpected command")

    return _run


def _symlink_required(name: str, target: Path) -> None:
    source = shutil.which(name)
    if not source:
        raise AssertionError(f"smoke host missing required tool: {name}")
    target.symlink_to(source)


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


def _run_json(command: list[str]) -> dict[str, Any]:
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise AssertionError(f"command failed: {command}\nstdout={completed.stdout}\nstderr={completed.stderr}")
    return json.loads(completed.stdout)


def _git(cwd: Path, *args: str) -> str:
    completed = subprocess.run(("git", *args), cwd=cwd, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed\nstdout={completed.stdout}\nstderr={completed.stderr}")
    return completed.stdout


def _wait_ready(base_url: str) -> None:
    deadline = time.time() + 10
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            _get_json(base_url + "/api/state")
            return
        except Exception as exc:
            last_error = exc
            time.sleep(0.1)
    raise AssertionError(f"server did not become ready: {last_error}")


def _get_json(url: str) -> dict[str, Any]:
    with urllib_request.urlopen(url, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _post_json(url: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib_request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib_request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
