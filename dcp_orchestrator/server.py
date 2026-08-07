"""DCP-authored loopback-only operator interface."""

from __future__ import annotations

import argparse
import fcntl
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.resources
import json
import os
import secrets
import signal
import threading
import webbrowser

from .canary import CanarySupervisor, SafetyViolation, TERMINAL_STATES
from .config import (
    BUNDLE_ID,
    CANONICAL_PROMPT,
    IPC_NAMESPACE,
    PROCESS_ID,
    PRODUCT_NAME,
    RuntimePaths,
    SERVICE_ID,
    TASK_ID,
)


class Registry:
    """The sole in-process mutation authority for the one-card registry."""

    def __init__(self, paths: RuntimePaths):
        self.paths = paths
        self._lock = threading.Lock()
        self._task: dict | None = None
        self._active = False

    def update(self, task: dict) -> None:
        with self._lock:
            self._task = task
            self._active = task.get("state") not in TERMINAL_STATES

    def snapshot(self) -> dict:
        with self._lock:
            task = json.loads(json.dumps(self._task)) if self._task else None
            return {
                "product": PRODUCT_NAME,
                "bundle_id": BUNDLE_ID,
                "process_id": PROCESS_ID,
                "service_id": SERVICE_ID,
                "ipc_namespace": IPC_NAMESPACE,
                "task_id": TASK_ID,
                "canonical_prompt": CANONICAL_PROMPT,
                "card_count": 1 if task else 0,
                "active": self._active,
                "task": task,
                "runtime_roots": self.paths.public_roots(),
                "owner_acceptance": None,
            }

    def start(self) -> None:
        with self._lock:
            if self._active or self._task is not None:
                raise SafetyViolation("this local server already consumed its one canary")
            self._active = True
            # The POST response must already contain the one stable card; the
            # worker thread may not win this race on every machine.
            self._task = {
                "task_id": TASK_ID,
                "state": "preparing",
                "state_label": "готовится",
                "reason": "accepted",
                "summary": "Лабораторный canary принят; prompt не сохраняется.",
                "card_count": 1,
                "attempt_count": 1,
                "worker_count": 1,
                "retry_count": 0,
                "transitions": [],
                "evidence_refs": [],
                "owner_acceptance": None,
            }
        supervisor = CanarySupervisor(self.paths, on_snapshot=self.update)

        def run() -> None:
            try:
                supervisor.run()
            except Exception as exc:  # a pre-record failure remains visible
                self.update(
                    {
                        "task_id": TASK_ID,
                        "state": "safety_violation",
                        "state_label": "нарушение безопасности",
                        "reason": str(exc),
                        "summary": "Canary не был запущен.",
                        "card_count": 1,
                        "attempt_count": 1,
                        "worker_count": 1,
                        "retry_count": 0,
                        "evidence_refs": [],
                        "owner_acceptance": None,
                    }
                )

        threading.Thread(target=run, name="dcp-orchestrator-canary-worker", daemon=False).start()


def _asset(name: str) -> bytes:
    return importlib.resources.files("dcp_orchestrator.static").joinpath(name).read_bytes()


def _acquire_server_lease(paths: RuntimePaths):
    """Prevent two DCP servers from sharing the same state/IPC namespace."""
    lease_path = paths.state / "server.lock"
    handle = lease_path.open("a+", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        handle.close()
        raise RuntimeError("another DCP Orchestrator server owns this runtime namespace") from exc
    handle.seek(0)
    handle.truncate()
    handle.write(str(os.getpid()) + "\n")
    handle.flush()
    os.fsync(handle.fileno())
    lease_path.chmod(0o600)
    return handle, lease_path


def make_handler(registry: Registry, token: str):
    class Handler(BaseHTTPRequestHandler):
        server_version = "DCP-Orchestrator-Lab/0.1"

        def log_message(self, _format: str, *_args) -> None:
            return

        def _security_headers(self) -> None:
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "connect-src 'self'; img-src 'self' data:; object-src 'none'; "
                "base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
            )

        def _send(self, status: HTTPStatus, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self._security_headers()
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: HTTPStatus, payload: dict) -> None:
            self._send(
                status,
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
                "application/json; charset=utf-8",
            )

        def _authorized(self) -> bool:
            return secrets.compare_digest(self.headers.get("X-DCP-Token", ""), token)

        def _valid_host(self) -> bool:
            expected = f"127.0.0.1:{self.server.server_address[1]}"
            return secrets.compare_digest(self.headers.get("Host", ""), expected)

        def _valid_origin(self) -> bool:
            origin = self.headers.get("Origin")
            expected = f"http://127.0.0.1:{self.server.server_address[1]}"
            return origin is None or secrets.compare_digest(origin, expected)

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
            if not self._valid_host():
                self._json(HTTPStatus.FORBIDDEN, {"error": "invalid_loopback_host"})
                return
            if self.path == "/":
                page = _asset("index.html").replace(b"__DCP_TOKEN__", token.encode("ascii"))
                self._send(HTTPStatus.OK, page, "text/html; charset=utf-8")
            elif self.path == "/app.js":
                self._send(HTTPStatus.OK, _asset("app.js"), "text/javascript; charset=utf-8")
            elif self.path == "/styles.css":
                self._send(HTTPStatus.OK, _asset("styles.css"), "text/css; charset=utf-8")
            elif self.path == "/api/state" and self._authorized():
                self._json(HTTPStatus.OK, registry.snapshot())
            else:
                self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

        def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
            if not self._valid_host() or not self._valid_origin():
                self._json(HTTPStatus.FORBIDDEN, {"error": "invalid_loopback_origin"})
                return
            if self.path != "/api/canary":
                self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                return
            if not self._authorized():
                self._json(HTTPStatus.FORBIDDEN, {"error": "invalid_process_token"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = 0
            if length < 2 or length > 512:
                self._json(HTTPStatus.BAD_REQUEST, {"error": "invalid_request_size"})
                return
            try:
                payload = json.loads(self.rfile.read(length))
            except (json.JSONDecodeError, UnicodeDecodeError):
                self._json(HTTPStatus.BAD_REQUEST, {"error": "invalid_json"})
                return
            prompt = payload.get("prompt") if isinstance(payload, dict) else None
            if prompt != CANONICAL_PROMPT:
                self._json(
                    HTTPStatus.BAD_REQUEST,
                    {"error": "prompt_must_match_fixed_synthetic_canary"},
                )
                return
            try:
                registry.start()
            except SafetyViolation as exc:
                self._json(HTTPStatus.CONFLICT, {"error": str(exc)})
                return
            self._json(HTTPStatus.ACCEPTED, registry.snapshot())

    return Handler


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="DCP Orchestrator isolated laboratory UI")
    parser.add_argument("--port", type=int, default=0, help="loopback port; 0 chooses a free port")
    parser.add_argument("--no-open", action="store_true", help="do not open the browser")
    args = parser.parse_args(argv)
    if args.port < 0 or args.port > 65535:
        parser.error("port must be between 0 and 65535")

    paths = RuntimePaths.from_environment()
    paths.create()
    lease_handle, lease_path = _acquire_server_lease(paths)
    state_file = paths.state / "server.json"
    server = None
    try:
        token = secrets.token_urlsafe(32)
        registry = Registry(paths)
        server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(registry, token))
        port = server.server_address[1]
        state_payload = {
            "schema_version": 1,
            "product": PRODUCT_NAME,
            "bundle_id": BUNDLE_ID,
            "process_id": PROCESS_ID,
            "service_id": SERVICE_ID,
            "ipc_namespace": IPC_NAMESPACE,
            "pid": os.getpid(),
            "endpoint": f"http://127.0.0.1:{port}",
            "token_persisted": False,
        }
        state_file.write_text(json.dumps(state_payload, indent=2) + "\n", encoding="utf-8")
        state_file.chmod(0o600)
        url = f"http://127.0.0.1:{port}/"
        print(f"{PRODUCT_NAME}: {url}", flush=True)
        print("Stop with Ctrl-C. Runtime data stays in the DCP namespace outside Git.", flush=True)
        if not args.no_open:
            webbrowser.open(url, new=1)

        def stop(_signum, _frame) -> None:
            threading.Thread(target=server.shutdown, daemon=True).start()

        signal.signal(signal.SIGINT, stop)
        signal.signal(signal.SIGTERM, stop)
        server.serve_forever(poll_interval=0.2)
    finally:
        if server is not None:
            server.server_close()
        try:
            state_file.unlink()
        except FileNotFoundError:
            pass
        fcntl.flock(lease_handle.fileno(), fcntl.LOCK_UN)
        lease_handle.close()
        try:
            lease_path.unlink()
        except FileNotFoundError:
            pass


if __name__ == "__main__":
    main()
