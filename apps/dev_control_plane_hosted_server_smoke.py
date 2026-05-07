"""Smoke-check hosted server runtime foundation without live deployment."""

from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from tempfile import TemporaryDirectory
from urllib import request as urllib_request

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "apps" / "dev_control_plane_server.py"


def main() -> None:
    with TemporaryDirectory(prefix="dev-control-plane-hosted-server-") as tmp_raw:
        tmp = Path(tmp_raw)
        state_dir = tmp / "hosted-state"
        port = _free_port()

        process = subprocess.Popen(
            [sys.executable, str(SERVER)],
            cwd=ROOT,
            env=_hosted_env(state_dir, port),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            base_url = f"http://127.0.0.1:{port}"
            _wait_ready(base_url)
            state = _get_json(base_url + "/api/state")
            _assert_hosted_state(state, state_dir, port)
            connections = _get_json(base_url + "/api/connections/status")
            github = connections.get("github", {})
            if github.get("status") != "missing" or "GitHub runtime token is missing" not in str(github.get("blocker")):
                raise AssertionError(f"hosted get_status must expose sanitized missing GitHub auth readiness: {github}")
            serialized = json.dumps(github, ensure_ascii=False)
            for forbidden in ("github_pat_", "ghp_", "Authorization", "Bearer "):
                if forbidden in serialized:
                    raise AssertionError(f"GitHub auth status leaked secret material: {github}")
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

        _assert_non_loopback_bind_blocked(tmp)

    print("dev-control-plane-hosted-server-smoke passed")


def _hosted_env(state_dir: Path, port: int) -> dict[str, str]:
    env = os.environ.copy()
    for key in ("DEV_CONTROL_PLANE_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN"):
        env.pop(key, None)
    env["DEV_CONTROL_PLANE_RUNTIME_PROFILE"] = "hosted"
    env["DEV_CONTROL_PLANE_HOST"] = "127.0.0.1"
    env["DEV_CONTROL_PLANE_PORT"] = str(port)
    env["DEV_CONTROL_PLANE_STATE_DIR"] = str(state_dir)
    env["DEV_CONTROL_PLANE_SECRET_HOME"] = str(state_dir.parent / "empty-secrets")
    env["DEV_CONTROL_PLANE_ENABLE_FAKE_CURATOR"] = "1"
    return env


def _assert_hosted_state(state: dict, state_dir: Path, port: int) -> None:
    if state.get("runtime_profile") != "hosted":
        raise AssertionError(f"server must report hosted runtime profile: {state}")
    if state.get("host") != "127.0.0.1" or state.get("port") != port:
        raise AssertionError(f"hosted server must remain loopback-only on requested port: {state}")
    if state.get("bind_policy") != "loopback_only" or state.get("local_only") is not True:
        raise AssertionError(f"hosted foundation must preserve loopback/local-only policy: {state}")
    if state.get("public_routes_enabled") is not False or state.get("live_deploy_enabled") is not False:
        raise AssertionError(f"hosted foundation must not enable live/public routes: {state}")
    if Path(str(state.get("state_dir"))).resolve() != state_dir.resolve():
        raise AssertionError(f"hosted server must use DEV_CONTROL_PLANE_STATE_DIR: {state}")
    layout = state.get("state_layout") or {}
    for key in ("runs_dir", "workspaces_dir", "artifacts_dir", "logs_dir", "verifier_dir", "collections_dir"):
        path = Path(str(layout.get(key))).resolve()
        if not path.exists():
            raise AssertionError(f"state layout directory must exist for {key}: {path}")
        if not _is_relative_to(path, state_dir.resolve()):
            raise AssertionError(f"state layout directory must stay inside hosted state root: {path}")
    allowed_live_monitor_routes = {
        "GET /runs/live",
        "GET /runs/{run_id}/watch",
        "GET /api/runs/live",
        "GET /api/runs/stream",
        "GET /api/runs/{id}/live",
        "GET /api/runs/{id}/timeline",
        "GET /api/runs/{id}/log-tail",
        "GET /api/runs/{id}/stream",
    }
    for route in state.get("exposed_routes", []):
        if "deploy" in route.lower() or ("live" in route.lower() and route not in allowed_live_monitor_routes):
            raise AssertionError(f"hosted foundation must not expose live/deploy route: {route}")


def _assert_non_loopback_bind_blocked(tmp: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(SERVER),
            "--host",
            "0.0.0.0",
            "--port",
            "0",
            "--state-dir",
            str(tmp / "blocked-state"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode == 0:
        raise AssertionError("server must reject non-loopback bind before serving")
    payload = json.loads(completed.stderr)
    if payload.get("status") != "blocked" or payload.get("bind_policy") != "loopback_only":
        raise AssertionError(f"non-loopback bind must fail with controlled blocker: {payload}")


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


def _get_json(url: str) -> dict:
    with urllib_request.urlopen(url, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


if __name__ == "__main__":
    main()
