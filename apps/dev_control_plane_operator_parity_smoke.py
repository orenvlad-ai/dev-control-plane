"""Smoke-check the wb-core operator-parity MCP lane."""

from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from tempfile import TemporaryDirectory
from typing import Any, Mapping
from urllib import request as urllib_request

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "apps" / "dev_control_plane_server.py"
TOKEN = "operator-parity-smoke-token-0123456789abcdef"


def main() -> None:
    _blocked_missing_runtime_path()
    _ready_dry_run_and_fake_codex()
    print("dev-control-plane-operator-parity-smoke passed")


def _blocked_missing_runtime_path() -> None:
    with TemporaryDirectory(prefix="dev-control-plane-parity-blocked-") as tmp_raw:
        tmp = Path(tmp_raw)
        worktree = _create_worktree(tmp / "wb-core")
        config_dir = tmp / "target-configs"
        _write_target_config(config_dir, worktree=worktree, runtime_state=tmp / "missing-runtime-state")
        with _running_server(tmp, config_dir) as ctx:
            status = _tool(ctx.base_url, "get_operator_parity_status", {"target_id": "wb-core"})
            if status.get("status") != "blocked" or "runtime_state_readable" not in str(status.get("exact_blocker")):
                raise AssertionError(f"missing runtime path must block parity preflight: {status}")
            start = _tool(
                ctx.base_url,
                "start_wb_core_operator_parity_task",
                {"target_id": "wb-core", "task_text": "inspect runtime state", "dry_run": True},
                token=TOKEN,
            )
            if start.get("status") != "blocked" or start.get("codex_started") is not False or start.get("accepted") is not False:
                raise AssertionError(f"blocked preflight must fail before run/Codex creation: {start}")
            runs = _read_collection(ctx.state_dir, "mcp_runs")
            if runs:
                raise AssertionError(f"blocked parity preflight must not create a run: {runs}")


def _ready_dry_run_and_fake_codex() -> None:
    with TemporaryDirectory(prefix="dev-control-plane-parity-ready-") as tmp_raw:
        tmp = Path(tmp_raw)
        runtime_state = _create_runtime_state(tmp / "runtime-state")
        worktree = _create_worktree(tmp / "wb-core")
        config_dir = tmp / "target-configs"
        _write_target_config(config_dir, worktree=worktree, runtime_state=runtime_state)
        with _running_server(tmp, config_dir, unsafe_artifact=True) as ctx:
            public_tools = _mcp(ctx.base_url, "tools/list", {})
            public_names = {tool.get("name") for tool in public_tools.get("tools", [])}
            if "get_operator_parity_status" not in public_names:
                raise AssertionError(f"public discovery must include operator parity status: {public_names}")
            if "start_wb_core_operator_parity_task" in public_names:
                raise AssertionError("public discovery must hide operator parity write tool")
            authed = _mcp(ctx.base_url, "tools/list", {}, token=TOKEN)
            authed_names = {tool.get("name") for tool in authed.get("tools", [])}
            if "start_wb_core_operator_parity_task" not in authed_names:
                raise AssertionError(f"authenticated discovery must include operator parity write tool: {authed_names}")

            status = _tool(ctx.base_url, "get_status", {})
            parity = status.get("operator_parity") or {}
            if parity.get("status") != "ready":
                raise AssertionError(f"get_status must expose ready parity matrix in fixture: {parity}")
            capabilities = parity.get("capabilities") or {}
            required = {
                "operator_worktree_ready",
                "github_ready",
                "ssh_ready",
                "runtime_state_readable",
                "db_readable",
                "browser_ready",
                "browser_session_ready",
                "promo_collector_runnable",
                "xlsx_download_runnable",
                "deploy_gate_ready",
                "secret_broker_ready",
                "redaction_ready",
                "artifact_quarantine_ready",
            }
            missing_ready = [name for name in required if (capabilities.get(name) or {}).get("status") != "ready"]
            if missing_ready:
                raise AssertionError(f"ready fixture has blocked capabilities: {missing_ready} {capabilities}")

            dry = _tool(
                ctx.base_url,
                "start_wb_core_operator_parity_task",
                {"target_id": "wb-core", "task_text": "dry parity smoke", "dry_run": True, "idempotency_key": "parity-dry"},
                token=TOKEN,
            )
            if dry.get("status") != "completed_dry_run" or dry.get("codex_started") is not False:
                raise AssertionError(f"operator parity dry-run must not start Codex: {dry}")
            dry_status = _tool(ctx.base_url, "get_run_status", {"run_id": dry["run_id"]})
            if dry_status.get("run_type") != "operator_parity" or dry_status.get("production_lane_started") is not False:
                raise AssertionError(f"dry parity run must be represented as operator_parity only: {dry_status}")
            dry_artifacts = _tool(ctx.base_url, "list_run_artifacts", {"run_id": dry["run_id"]})
            dry_ids = {item.get("artifact_id") for item in dry_artifacts.get("artifacts", [])}
            if not {"operator_parity_preflight", "operator_parity_runtime_broker_export", "prompt"}.issubset(dry_ids):
                raise AssertionError(f"dry parity artifacts missing preflight/broker export: {dry_artifacts}")

            denied = _tool(
                ctx.base_url,
                "start_wb_core_operator_parity_task",
                {"target_id": "wb-core", "task_text": "real parity without confirmation", "dry_run": False},
                token=TOKEN,
            )
            if denied.get("status") != "blocked" or "confirm_start=true" not in str(denied.get("blocker")):
                raise AssertionError(f"real parity start must require explicit confirmation: {denied}")

            run = _tool(
                ctx.base_url,
                "start_wb_core_operator_parity_task",
                {
                    "target_id": "wb-core",
                    "task_text": "fake parity Codex run",
                    "dry_run": False,
                    "confirm_start": True,
                    "idempotency_key": "parity-real",
                    "max_wait_seconds": 10,
                },
                token=TOKEN,
            )
            run_id = str(run.get("run_id") or "")
            if not run_id:
                raise AssertionError(f"operator parity start must return run_id: {run}")
            final = _wait_run_status(ctx.base_url, run_id, {"completed", "failed", "blocked"})
            if final.get("status") != "completed" or final.get("run_type") != "operator_parity":
                raise AssertionError(f"fake parity Codex run must complete as operator_parity: {final}")
            if final.get("production_lane_started") is not False or final.get("fallback_to_sprint") is not False:
                raise AssertionError(f"operator parity must not start production or fallback: {final}")
            events = final.get("artifact_quarantine_events") or []
            if not any(item.get("status") == "secret_like_content_blocked" for item in events):
                raise AssertionError(f"unsafe parity artifact must be quarantined/redacted: {final}")
            unsafe = _tool(ctx.base_url, "get_run_artifact", {"run_id": run_id, "artifact_id": "operator_parity_unsafe_report"})
            if unsafe.get("status") != "ok" or "sk-testsecret" in str(unsafe.get("content") or ""):
                raise AssertionError(f"unsafe artifact must be readable only after redaction: {unsafe}")
            report = _tool(ctx.base_url, "get_run_report", {"run_id": run_id})
            parity_report = report.get("operator_parity_report") or {}
            if parity_report.get("status") != "completed" or parity_report.get("production_lane_started") is not False:
                raise AssertionError(f"run report must expose parity result without production: {report}")
            active = _tool(ctx.base_url, "list_active_runs", {"target_id": "wb-core"})
            active_ids = {item.get("run_id") for item in active.get("runs", [])}
            if run_id in active_ids:
                raise AssertionError(f"terminal parity run must not remain active: {active}")


class _ServerContext:
    def __init__(self, process: subprocess.Popen[str], base_url: str, state_dir: Path) -> None:
        self.process = process
        self.base_url = base_url
        self.state_dir = state_dir

    def __enter__(self) -> "_ServerContext":
        return self

    def __exit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)


def _running_server(tmp: Path, config_dir: Path, *, unsafe_artifact: bool = False) -> _ServerContext:
    port = _free_port()
    state_dir = tmp / "state"
    process = subprocess.Popen(
        [
            sys.executable,
            str(SERVER),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--state-dir",
            str(state_dir),
            "--target-config-dir",
            str(config_dir),
        ],
        cwd=ROOT,
        env=_server_env(tmp, unsafe_artifact=unsafe_artifact),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    context = _ServerContext(process, f"http://127.0.0.1:{port}", state_dir)
    try:
        _wait_ready(context.base_url)
    except Exception:
        process.terminate()
        raise
    return context


def _server_env(tmp: Path, *, unsafe_artifact: bool) -> dict[str, str]:
    secret_home = tmp / "secrets"
    secret_home.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.pop("OPENAI_API_KEY", None)
    env["DEV_CONTROL_PLANE_MCP_TOKEN"] = TOKEN
    env["DEV_CONTROL_PLANE_SECRET_HOME"] = str(secret_home)
    env["DEV_CONTROL_PLANE_OPERATOR_PARITY_FAKE_READY"] = "1"
    env["DEV_CONTROL_PLANE_OPERATOR_PARITY_FAKE_CODEX"] = "1"
    env["DEV_CONTROL_PLANE_ENABLE_FAKE_CURATOR"] = "1"
    if unsafe_artifact:
        env["DEV_CONTROL_PLANE_OPERATOR_PARITY_FAKE_UNSAFE_ARTIFACT"] = "1"
    return env


def _write_target_config(config_dir: Path, *, worktree: Path, runtime_state: Path) -> None:
    config_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "project_id": "wb-core",
        "display_name": "wb-core",
        "repo_path": str(worktree),
        "source_mode": "local_path",
        "repo_url": str(worktree),
        "branch": "main",
        "source_of_truth_paths": ["README.md"],
        "derived_secondary_paths": [],
        "default_forbidden_paths": ["runtime/**"],
        "default_forbidden_actions": ["direct_target_mutation", "secrets_write"],
        "default_required_smokes": ["git diff --check"],
        "codex_prompt_contract": {},
        "control_plane_notes": ["operator parity smoke fixture"],
        "product_plane_notes": [],
        "target_readonly_by_default": True,
        "execution_policy": {
            "allow_auto_merge": False,
            "allow_direct_target_mutation": False,
            "allow_live_deploy": False,
            "allow_managed_clone_execution": True,
            "default_mode": "fake",
            "require_explicit_real_codex_flag": True,
        },
        "operator_parity": {
            "enabled": True,
            "persistent_worktree_path": str(worktree),
            "runtime_state_path": str(runtime_state),
            "allowed_runtime_read_paths": [
                str(runtime_state / "promo_campaign_archive"),
                str(runtime_state / "promo_xlsx_collector_runs"),
                str(runtime_state / "registry_upload_runtime.sqlite3"),
            ],
            "allowed_runtime_write_paths": [],
            "db_probe_paths": [
                str(runtime_state / "promo_campaign_archive"),
                str(runtime_state / "promo_xlsx_collector_runs"),
                str(runtime_state / "registry_upload_runtime.sqlite3"),
            ],
            "browser_session_paths": [str(runtime_state / "seller_portal_relogin")],
            "collector_runners": {
                "promo_collector": "apps/sheet_vitrina_v1_auto_refresh_tick.py",
                "xlsx_download": "apps/registry_upload_http_entrypoint_hosted_runtime.py",
            },
            "artifact_quarantine_dir": "{state_dir}/artifact_quarantine/operator_parity",
            "required_capabilities": [
                "toolchain_ready",
                "codex_auth_ready",
                "operator_worktree_ready",
                "github_ready",
                "ssh_ready",
                "runtime_state_readable",
                "db_readable",
                "browser_ready",
                "browser_session_ready",
                "promo_collector_runnable",
                "xlsx_download_runnable",
                "deploy_gate_ready",
                "secret_broker_ready",
                "redaction_ready",
                "artifact_quarantine_ready",
            ],
        },
    }
    (config_dir / "wb_core.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _create_worktree(path: Path) -> Path:
    path.mkdir(parents=True)
    (path / "README.md").write_text("# wb-core fixture\n", encoding="utf-8")
    apps = path / "apps"
    apps.mkdir()
    (apps / "sheet_vitrina_v1_auto_refresh_tick.py").write_text("print('collector dry run')\n", encoding="utf-8")
    (apps / "registry_upload_http_entrypoint_hosted_runtime.py").write_text("print('xlsx dry run')\n", encoding="utf-8")
    _git(path, "init", "-b", "main")
    _git(path, "add", ".")
    _git(path, "-c", "user.email=devcontrol@example.invalid", "-c", "user.name=DevControl", "commit", "-m", "seed")
    return path


def _create_runtime_state(path: Path) -> Path:
    for relative in (
        "promo_campaign_archive",
        "promo_xlsx_collector_runs",
        "seller_portal_relogin",
    ):
        directory = path / relative
        directory.mkdir(parents=True, exist_ok=True)
        (directory / ".keep").write_text("fixture\n", encoding="utf-8")
    (path / "registry_upload_runtime.sqlite3").write_text("fixture sqlite metadata\n", encoding="utf-8")
    return path


def _git(cwd: Path, *args: str) -> None:
    completed = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False, timeout=20)
    if completed.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {completed.stderr or completed.stdout}")


def _read_collection(state_dir: Path, name: str) -> dict[str, Any]:
    path = state_dir / "collections" / f"{name}.json"
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return dict(payload) if isinstance(payload, Mapping) else {}


def _tool(base_url: str, name: str, arguments: Mapping[str, Any], *, token: str | None = None) -> dict[str, Any]:
    result = _mcp(base_url, "tools/call", {"name": name, "arguments": dict(arguments)}, token=token)
    structured = result.get("structuredContent")
    if isinstance(structured, dict):
        return structured
    content = result.get("content", [])
    if content and isinstance(content[0], dict):
        return json.loads(content[0].get("text") or "{}")
    raise AssertionError(f"MCP tool result missing structuredContent for {name}: {result}")


def _mcp(base_url: str, method: str, params: Mapping[str, Any], *, token: str | None = None) -> dict[str, Any]:
    body = json.dumps({"jsonrpc": "2.0", "id": f"smoke-{time.time_ns()}", "method": method, "params": params}).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib_request.Request(base_url + "/mcp", data=body, method="POST", headers=headers)
    with urllib_request.urlopen(req, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if "error" in payload:
        raise AssertionError(f"MCP error for {method}: {payload}")
    return payload.get("result") or {}


def _wait_run_status(base_url: str, run_id: str, statuses: set[str]) -> dict[str, Any]:
    deadline = time.time() + 15
    last: dict[str, Any] = {}
    while time.time() < deadline:
        last = _tool(base_url, "get_run_status", {"run_id": run_id})
        if str(last.get("status") or "") in statuses:
            return last
        time.sleep(0.2)
    raise AssertionError(f"run {run_id} did not reach {statuses}: {last}")


def _wait_ready(base_url: str) -> None:
    deadline = time.time() + 10
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib_request.urlopen(base_url + "/api/state", timeout=5) as response:
                if response.status == 200:
                    return
        except Exception as exc:
            last_error = exc
            time.sleep(0.1)
    raise RuntimeError(f"server did not become ready at {base_url}: {last_error}")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


if __name__ == "__main__":
    main()
