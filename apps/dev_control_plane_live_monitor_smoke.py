"""Smoke-check hosted-style read-only live monitor APIs and page."""

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
SRC = ROOT / "src"
for path in (SRC, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dev_control_plane.live_monitor import append_terminal_output  # noqa: E402

SERVER = ROOT / "apps" / "dev_control_plane_server.py"
TOKEN = "live-monitor-smoke-token-0123456789abcdef"


def main() -> None:
    port = _free_port()
    with TemporaryDirectory(prefix="dev-control-plane-live-monitor-") as tmp_raw:
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

            home = _get_text(base_url + "/")
            if 'href="/runs/live"' not in home or "Живые запуски" not in home:
                raise AssertionError("operator homepage must expose a neutral link to /runs/live")

            page = _get_text(base_url + "/runs/live")
            for token in (
                "DevControl Live Runs",
                "terminal",
                "pause autoscroll",
                "copy visible sanitized log",
                "clear local view",
                "userSelectedRun",
                "terminalStates",
                "runTerminalFinalized",
                "chooseSelectedRun",
                "appendTerminalDelta",
            ):
                if token not in page:
                    raise AssertionError(f"live page missing expected terminal UI token: {token}")
            forbidden_page_tokens = ("<input", "<textarea", "contenteditable", "executor_command", "shell")
            lowered = page.lower()
            for token in forbidden_page_tokens:
                if token in lowered:
                    raise AssertionError(f"live page must not expose command input token: {token}")

            empty = _get_json(base_url + "/api/runs/live")
            if empty.get("status") != "ok" or empty.get("active_count") != 0:
                raise AssertionError(f"empty live run list must be controlled: {empty}")

            started = _tool(
                base_url,
                "start_managed_clone_run",
                {"target_id": "wb-core", "task_text": "live monitor fake managed run"},
                token=TOKEN,
            )
            run_id = started.get("run_id")
            if not run_id or not started.get("live_url") or not started.get("watch_url"):
                raise AssertionError(f"start tool must return live/watch URLs: {started}")
            final = _wait_run_status(base_url, run_id, {"passed", "failed", "blocked"})
            if final.get("status") != "passed":
                raise AssertionError(f"fake managed-clone run must pass for live monitor smoke: {final}")

            run_dir = state_dir / "runs" / run_id
            raw_secret = "Authorization: " + "Bearer live-monitor-sensitive-token-0123456789"
            append_terminal_output(
                run_dir,
                "\x1b[1;32mgreen live line\x1b[0m\n"
                "spinner: one\rspinner: done\n"
                "\x1b]52;c;clipboard\x07"
                "\x1bP1;2;danger\x1b\\"
                f"{raw_secret}\n",
            )

            live = _get_json(base_url + "/api/runs/live")
            matching = [run for run in live.get("runs", []) if run.get("run_id") == run_id]
            if not matching:
                raise AssertionError(f"live run list must include new MCP run: {live}")
            if matching[0].get("watch_url") != started.get("watch_url"):
                raise AssertionError(f"live list must preserve watch_url: {matching[0]}")

            timeline = _get_json(base_url + f"/api/runs/{run_id}/timeline")
            titles = " ".join(str(event.get("title") or "") for event in timeline.get("events", []))
            if "Queued" not in titles and "Managed clone" not in titles:
                raise AssertionError(f"timeline must include run stage events: {timeline}")

            tail = _get_json(base_url + f"/api/runs/{run_id}/log-tail")
            ansi = tail.get("ansi_text") or ""
            plain = tail.get("plain_text") or ""
            if "\x1b[1;32m" not in ansi:
                raise AssertionError(f"safe ANSI SGR color/style must survive: {tail}")
            for forbidden in ("\x1b]52", "\x1bP", "clipboard", "live-monitor-sensitive-token", "Authorization: Bearer"):
                if forbidden in ansi or forbidden in plain:
                    raise AssertionError(f"unsafe control/secret leaked into live log tail: {forbidden} {tail}")
            if "[redacted]" not in ansi or "spinner: done" not in plain:
                raise AssertionError(f"redaction and carriage-return handling must be visible: {tail}")

            start_offset = int(tail.get("next_offset") or 0)
            append_terminal_output(run_dir, "offset-only line\n")
            delta = _get_json(base_url + f"/api/runs/{run_id}/log-tail?offset={start_offset}")
            if "offset-only line" not in delta.get("plain_text", "") or "green live line" in delta.get("plain_text", ""):
                raise AssertionError(f"offset log-tail must append only new terminal content: {delta}")
            repeat = _get_json(base_url + f"/api/runs/{run_id}/log-tail?offset={delta.get('next_offset')}")
            if "offset-only line" in repeat.get("plain_text", ""):
                raise AssertionError(f"terminal offset must not duplicate prior lines: {repeat}")

            json_offset = int(delta.get("next_offset") or 0)
            append_terminal_output(
                run_dir,
                '{"type":"turn.completed","usage":{"input_tokens":123}}\n'
                '{"type":"assistant_message","message":"hello escaped\\\\nworld"}\n',
            )
            json_tail = _get_json(base_url + f"/api/runs/{run_id}/log-tail?offset={json_offset}")
            json_text = json_tail.get("plain_text", "")
            if "hello escaped\nworld" not in json_text:
                raise AssertionError(f"escaped newline content must render as multiline text: {json_tail}")
            for raw_marker in ("turn.completed", "{\"type\"", "input_tokens"):
                if raw_marker in json_text or raw_marker in json_tail.get("ansi_text", ""):
                    raise AssertionError(f"raw JSON envelope must stay hidden from terminal view: {raw_marker} {json_tail}")

            repeated_live = [_get_json(base_url + "/api/runs/live") for _ in range(3)]
            repeated_ids = [payload.get("runs", [{}])[0].get("run_id") for payload in repeated_live if payload.get("runs")]
            if len(set(repeated_ids)) != 1 or repeated_ids[0] != run_id:
                raise AssertionError(f"selected/default run order must be stable across refreshes: {repeated_ids}")

            detail = _get_json(base_url + f"/api/runs/{run_id}/live")
            if "README.md" not in detail.get("changed_files", []) or "fake MCP managed-clone run completed" not in str(detail.get("handoff") or ""):
                raise AssertionError(f"completed live detail must include changed files and handoff: {detail}")

            sse_line = _read_sse_line(base_url + f"/api/runs/{run_id}/stream")
            if "event: run" not in sse_line:
                raise AssertionError(f"SSE stream must emit run events: {sse_line}")

            watch = _get_text(base_url + f"/runs/{run_id}/watch")
            if run_id not in watch:
                raise AssertionError("watch page must embed selected run id")

            state_text = "\n".join(path.read_text(encoding="utf-8", errors="replace") for path in state_dir.rglob("*") if path.is_file())
            if "live-monitor-sensitive-token" in state_text or "Authorization: Bearer" in state_text:
                raise AssertionError("live monitor sanitizer must not persist raw secret marker")
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

    print("dev-control-plane-live-monitor-smoke passed")


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
    deadline = time.time() + 10
    last: dict[str, Any] = {}
    while time.time() < deadline:
        last = _tool(base_url, "get_run_status", {"run_id": run_id})
        if str(last.get("status") or "") in terminal:
            return last
        time.sleep(0.1)
    raise AssertionError(f"run did not reach terminal status: {last}")


def _get_json(url: str) -> dict[str, Any]:
    return json.loads(_get_text(url))


def _get_text(url: str) -> str:
    with urllib_request.urlopen(url, timeout=10) as response:
        return response.read().decode("utf-8")


def _read_sse_line(url: str) -> str:
    req = urllib_request.Request(url, method="GET", headers={"Accept": "text/event-stream"})
    with urllib_request.urlopen(req, timeout=10) as response:
        lines = []
        deadline = time.time() + 3
        while time.time() < deadline:
            line = response.readline().decode("utf-8")
            if not line:
                break
            lines.append(line)
            if line == "\n":
                break
        return "".join(lines)


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
