"""Smoke-check MCP start_sprint is frozen for ordinary operator flow."""

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
TOKEN = "sprint-smoke-token-0123456789abcdef0123456789abcdef"


def main() -> None:
    port = _free_port()
    with TemporaryDirectory(prefix="dev-control-plane-sprint-") as tmp_raw:
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

            public_tools = _mcp(base_url, "tools/list", {})
            public_names = {tool.get("name") for tool in public_tools.get("tools", [])}
            if "start_sprint" in public_names:
                raise AssertionError("public no-auth tools/list must hide start_sprint")
            denied = _tool(base_url, "start_sprint", {"target_id": "wb-core", "sprint_text": "must not start"})
            if denied.get("status") != "denied":
                raise AssertionError(f"no-auth start_sprint must be denied: {denied}")

            auth_tools = _mcp(base_url, "tools/list", {}, token=TOKEN)
            auth_names = {tool.get("name") for tool in auth_tools.get("tools", [])}
            if "start_sprint" in auth_names:
                raise AssertionError("authenticated operator tools/list must hide frozen start_sprint")

            started = _tool(
                base_url,
                "start_sprint",
                {
                    "target_id": "wb-core",
                    "sprint_text": "Проверь README.md и создай fake sprint report artifact in managed clone only.",
                    "max_steps": 2,
                    "max_retries_per_step": 1,
                    "execution_mode": "managed_clone_only",
                },
                token=TOKEN,
            )
            if (
                started.get("status") != "blocked"
                or "start_sprint is frozen for operator flow" not in str(started.get("blocker") or "")
                or started.get("run_id")
            ):
                raise AssertionError(f"start_sprint must fail closed without parent/child run: {started}")

            live = _get_json(base_url + "/api/runs/live")
            if any(str(run.get("run_id") or "").startswith("mcp-sprint-") for run in live.get("runs", [])):
                raise AssertionError(f"frozen start_sprint must not create live sprint runs: {live}")

            state_text = "\n".join(path.read_text(encoding="utf-8", errors="replace") for path in state_dir.rglob("*") if path.is_file())
            if TOKEN in state_text or "Authorization: Bearer" in state_text:
                raise AssertionError("sprint smoke token leaked into state/artifacts")
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

    print("dev-control-plane-mcp-start-sprint-smoke passed")


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
