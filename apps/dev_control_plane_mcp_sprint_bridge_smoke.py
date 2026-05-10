"""Smoke-check start_managed_clone_run sprint compatibility bridge is frozen."""

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
TOKEN = "sprint-bridge-smoke-token-0123456789abcdef"
MARKER = "DEVCONTROL_START_SPRINT_V1"


def main() -> None:
    port = _free_port()
    with TemporaryDirectory(prefix="dev-control-plane-sprint-bridge-") as tmp_raw:
        tmp = Path(tmp_raw)
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
            ],
            cwd=ROOT,
            env=_server_env(tmp),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            base_url = f"http://127.0.0.1:{port}"
            _wait_ready(base_url)

            status = _tool(base_url, "get_status", {})
            bridge = ((status.get("mcp") or {}).get("sprint_compatibility_bridge") or {})
            if (
                bridge.get("status") != "frozen"
                or bridge.get("marker") != MARKER
                or "start_sprint is frozen for operator flow" not in str(bridge.get("blocker") or "")
            ):
                raise AssertionError(f"get_status must expose frozen sprint bridge policy: {status}")

            denied_noauth = _tool(base_url, "start_managed_clone_run", _bridge_args("no-auth must deny"))
            if denied_noauth.get("status") != "denied":
                raise AssertionError(f"no-auth bridge call must be denied by write gate: {denied_noauth}")

            normal = _tool(
                base_url,
                "start_managed_clone_run",
                {"target_id": "wb-core", "task_text": "normal managed clone bridge smoke", "no_pr_no_deploy": True},
                token=TOKEN,
            )
            normal_run_id = str(normal.get("run_id") or "")
            if normal.get("status") != "queued" or not normal_run_id.startswith("mcp-managed-"):
                raise AssertionError(f"normal managed clone call must stay unchanged: {normal}")
            normal_final = _wait_run_status(base_url, normal_run_id, {"passed", "failed", "blocked"})
            if normal_final.get("status") != "passed" or normal_final.get("run_type") != "managed":
                raise AssertionError(f"normal managed clone run must pass in fake mode: {normal_final}")

            before_invalid_count = _mcp_run_count(state_dir)
            bridged = _tool(base_url, "start_managed_clone_run", _bridge_args("bridge must stay frozen"), token=TOKEN)
            if (
                bridged.get("status") != "blocked"
                or bridged.get("run_id")
                or bridged.get("compatibility_bridge") != "start_managed_clone_run"
                or "start_sprint is frozen for operator flow" not in str(bridged.get("blocker") or "")
            ):
                raise AssertionError(f"bridge must fail closed without sprint parent run: {bridged}")
            if _mcp_run_count(state_dir) != before_invalid_count:
                raise AssertionError("frozen sprint bridge must not create a managed or sprint run")

            invalid = _tool(
                base_url,
                "start_managed_clone_run",
                {"target_id": "wb-core", "task_text": f"{MARKER}\nnot-json", "no_pr_no_deploy": True},
                token=TOKEN,
            )
            if invalid.get("status") != "blocked" or invalid.get("run_id"):
                raise AssertionError(f"invalid bridge payload must fail closed without run_id: {invalid}")
            if _mcp_run_count(state_dir) != before_invalid_count:
                raise AssertionError("invalid bridge payload must not create a managed or sprint run")

            no_pr = _tool(base_url, "start_managed_clone_run", {**_bridge_args("no pr false"), "no_pr_no_deploy": False}, token=TOKEN)
            if no_pr.get("status") != "blocked" or no_pr.get("run_id"):
                raise AssertionError(f"bridge with no_pr_no_deploy=false must be denied without run: {no_pr}")
            if _mcp_run_count(state_dir) != before_invalid_count:
                raise AssertionError("denied no_pr_no_deploy=false bridge must not create a run")

            production_mode = _tool(
                base_url,
                "start_managed_clone_run",
                _bridge_args("production mode denied", execution_mode="production_lane"),
                token=TOKEN,
            )
            if production_mode.get("status") != "blocked" or production_mode.get("run_id"):
                raise AssertionError(f"bridge must deny unsupported execution_mode without run: {production_mode}")
            if _mcp_run_count(state_dir) != before_invalid_count:
                raise AssertionError("unsupported bridge execution_mode must not create a run")

            state_text = "\n".join(path.read_text(encoding="utf-8", errors="replace") for path in state_dir.rglob("*") if path.is_file())
            if TOKEN in state_text or "Authorization: Bearer" in state_text:
                raise AssertionError("sprint bridge smoke token leaked into state/artifacts")
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

    print("dev-control-plane-mcp-sprint-bridge-smoke passed")


def _bridge_args(sprint_text: str, *, execution_mode: str = "managed_clone_only") -> dict[str, Any]:
    payload = {
        "sprint_text": sprint_text,
        "max_steps": 2,
        "max_retries_per_step": 1,
        "execution_mode": execution_mode,
    }
    return {"target_id": "wb-core", "task_text": f"{MARKER}\n{json.dumps(payload, ensure_ascii=False)}", "no_pr_no_deploy": True}


def _mcp(base_url: str, method: str, params: Mapping[str, Any], *, token: str | None = None) -> dict[str, Any]:
    body = json.dumps({"jsonrpc": "2.0", "id": f"smoke-{time.time_ns()}", "method": method, "params": params}).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib_request.Request(base_url + "/mcp", data=body, method="POST", headers=headers)
    with urllib_request.urlopen(req, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if "error" in payload:
        raise AssertionError(f"MCP error for {method}: {payload}")
    return payload.get("result") or {}


def _tool(base_url: str, name: str, arguments: Mapping[str, Any], *, token: str | None = None) -> dict[str, Any]:
    result = _mcp(base_url, "tools/call", {"name": name, "arguments": dict(arguments)}, token=token)
    structured = result.get("structuredContent")
    if isinstance(structured, dict):
        return structured
    content = result.get("content", [])
    if content and isinstance(content[0], dict):
        return json.loads(content[0].get("text") or "{}")
    return {}


def _wait_run_status(base_url: str, run_id: str, terminal: set[str]) -> dict[str, Any]:
    deadline = time.time() + 15
    last: dict[str, Any] = {}
    while time.time() < deadline:
        last = _tool(base_url, "get_run_status", {"run_id": run_id})
        if str(last.get("status") or "") in terminal:
            return last
        time.sleep(0.1)
    raise AssertionError(f"run did not reach terminal status: {last}")


def _mcp_run_count(state_dir: Path) -> int:
    path = state_dir / "collections" / "mcp_runs.json"
    if not path.exists():
        return 0
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise AssertionError(f"mcp_runs collection must be object: {payload}")
    return len(payload)


def _get_json(url: str) -> dict[str, Any]:
    with urllib_request.urlopen(url, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


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


def _server_env(tmp: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("OPENAI_API_KEY", None)
    env["DEV_CONTROL_PLANE_SECRET_HOME"] = str(tmp / "secrets")
    env["DEV_CONTROL_PLANE_MCP_TOKEN"] = TOKEN
    env["DEV_CONTROL_PLANE_MCP_FAKE_RUNS"] = "1"
    env["DEV_CONTROL_PLANE_ENABLE_FAKE_CURATOR"] = "1"
    return env


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


if __name__ == "__main__":
    main()
