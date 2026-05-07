"""Smoke-check ChatGPT-compatible public MCP read-only discovery."""

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


def main() -> None:
    port = _free_port()
    with TemporaryDirectory(prefix="dev-control-plane-mcp-public-") as tmp_raw:
        tmp = Path(tmp_raw)
        process = subprocess.Popen(
            [
                sys.executable,
                str(SERVER),
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--state-dir",
                str(tmp / "state"),
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

            status_doc = _get_json(base_url + "/mcp")
            if status_doc.get("chatgpt_auth_strategy") != "mixed_noauth_read_oauth_write":
                raise AssertionError(f"MCP status must advertise read-only ChatGPT strategy: {status_doc}")
            if status_doc.get("write_tools") or status_doc.get("write_tools_hidden") is not True:
                raise AssertionError(f"public MCP status must hide write tool names: {status_doc}")
            if status_doc.get("chatgpt_write_tools_ready") is not True:
                raise AssertionError(f"public MCP status must report OAuth write readiness without exposing tools: {status_doc}")

            initialize = _mcp(base_url, "initialize", {})
            if initialize.get("protocolVersion") != "2025-06-18":
                raise AssertionError(f"initialize must succeed without auth: {initialize}")

            tools = _mcp(base_url, "tools/list", {})
            names = {str(tool.get("name") or "") for tool in tools.get("tools", [])}
            read_tools = {
                "fetch",
                "get_production_lock_status",
                "get_rollback_plan",
                "get_run_artifact",
                "get_run_report",
                "get_run_status",
                "get_status",
                "get_target_status",
                "list_active_runs",
                "list_run_artifacts",
                "list_targets",
                "search",
            }
            write_tools = {"request_rollback", "start_managed_clone_run", "start_wb_core_production_lane"}
            if names != read_tools:
                raise AssertionError(f"public tools/list must expose exactly read-only tools: {names}")
            if names & write_tools:
                raise AssertionError(f"public discovery must not expose write tools: {names & write_tools}")
            for tool in tools.get("tools", []):
                annotations = tool.get("annotations") or {}
                if annotations.get("readOnlyHint") is not True:
                    raise AssertionError(f"public tool must carry readOnlyHint=true: {tool}")
                schemes = tool.get("securitySchemes") or (tool.get("_meta") or {}).get("securitySchemes") or []
                if {"type": "noauth"} not in schemes:
                    raise AssertionError(f"public read tool must advertise noauth scheme: {tool}")

            get_status = _tool(base_url, "get_status", {})
            if get_status.get("status") != "ok":
                raise AssertionError(f"public get_status must work: {get_status}")
            active = _tool(base_url, "list_active_runs", {})
            if active.get("status") != "ok":
                raise AssertionError(f"public list_active_runs must work: {active}")
            denied = _tool(base_url, "start_wb_core_production_lane", {"task_text": "must not start", "dry_run": True})
            if denied.get("status") != "denied" or denied.get("chatgpt_write_tools_ready") is not True:
                raise AssertionError(f"direct public write call must fail closed: {denied}")
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

    print("dev-control-plane-mcp-public-discovery-smoke passed")


def _mcp(base_url: str, method: str, params: Mapping[str, Any]) -> dict[str, Any]:
    body = json.dumps({"jsonrpc": "2.0", "id": f"smoke-{time.time_ns()}", "method": method, "params": params}).encode("utf-8")
    req = urllib_request.Request(base_url + "/mcp", data=body, method="POST", headers={"Content-Type": "application/json"})
    with urllib_request.urlopen(req, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if "error" in payload:
        raise AssertionError(f"MCP error for {method}: {payload}")
    return payload.get("result") or {}


def _tool(base_url: str, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
    result = _mcp(base_url, "tools/call", {"name": name, "arguments": dict(arguments)})
    structured = result.get("structuredContent")
    if isinstance(structured, dict):
        return structured
    content = result.get("content", [])
    if content and isinstance(content[0], dict):
        return json.loads(content[0].get("text") or "{}")
    return {}


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


def _server_env(tmp: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("OPENAI_API_KEY", None)
    env.pop("DEV_CONTROL_PLANE_MCP_TOKEN", None)
    env["DEV_CONTROL_PLANE_SECRET_HOME"] = str(tmp / "secrets")
    env["DEV_CONTROL_PLANE_ENABLE_FAKE_CURATOR"] = "1"
    return env


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


if __name__ == "__main__":
    main()
