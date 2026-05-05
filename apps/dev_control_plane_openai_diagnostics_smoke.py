"""Smoke-check sanitized OpenAI diagnostics without calling the real API."""

from __future__ import annotations

from email.message import Message
import io
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import time
from tempfile import TemporaryDirectory
from urllib import error as urllib_error, request as urllib_request

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (SRC, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dev_control_plane.ai import (  # noqa: E402
    OPENAI_RESPONSES_URL,
    openai_connection_test,
    openai_connection_test_result_to_dict,
    openai_curator_chat_reply,
)
from dev_control_plane.secrets import SECRET_HOME_ENV, delete_openai_credentials, set_openai_credentials  # noqa: E402

SERVER = ROOT / "apps" / "dev_control_plane_server.py"
PROBE = ROOT / "apps" / "dev_control_plane_openai_probe.py"


def main() -> None:
    with TemporaryDirectory(prefix="dev-control-plane-openai-direct-") as tmp:
        isolated_env = {SECRET_HOME_ENV: str(Path(tmp) / "secrets")}
        _exercise_direct_diagnostics(isolated_env)
        _exercise_probe_missing_key(isolated_env)
    _exercise_server_diagnostics()
    _exercise_server_file_backed_status()
    print("dev-control-plane-openai-diagnostics-smoke passed")


def _exercise_direct_diagnostics(isolated_env: dict[str, str]) -> None:
    missing_key = openai_connection_test(env=isolated_env)
    _assert_result(missing_key, "blocked", "missing_api_key")

    missing_model = openai_connection_test(env={**isolated_env, "OPENAI_API_KEY": "sk-test"})
    _assert_result(missing_model, "blocked", "missing_model")

    cases = (
        (401, "bad key", "auth_error"),
        (403, "no permission", "permission_error"),
        (404, "model does not exist", "model_not_found"),
        (429, "rate limit", "rate_limited"),
        (500, "temporary provider failure", "server_error"),
        (504, "gateway timeout", "provider_timeout"),
        (400, "invalid request", "bad_request"),
        (400, "model_not_found", "model_not_found"),
        (400, "The requested model gpt-5.5 does not exist", "model_not_found"),
        (400, "You do not have access to model gpt-5.5", "permission_error"),
    )
    for status_code, body, expected_type in cases:
        result = openai_connection_test(
            env=_configured_env(isolated_env),
            urlopen=_http_error_urlopen(status_code, body),
        )
        _assert_result(result, "failed", expected_type, http_status=status_code)
        payload = openai_connection_test_result_to_dict(result)
        _assert_sanitized(payload)

    timeout = openai_connection_test(env=_configured_env(isolated_env), urlopen=_timeout_urlopen)
    _assert_result(timeout, "failed", "timeout")

    timeout_then_ok = _timeout_then_ok_urlopen(failures=2)
    timeout_retry_ok = openai_connection_test(env=_configured_env(isolated_env), urlopen=timeout_then_ok)
    if timeout_retry_ok.status != "ok" or timeout_then_ok.calls != 3:
        raise AssertionError(f"timeout retry must be bounded and eventually succeed: {timeout_retry_ok}, calls={timeout_then_ok.calls}")

    server_error_then_ok = _http_error_then_ok_urlopen(500, "temporary provider failure")
    server_retry_ok = openai_connection_test(env=_configured_env(isolated_env), urlopen=server_error_then_ok)
    if server_retry_ok.status != "ok" or server_error_then_ok.calls != 2:
        raise AssertionError(f"5xx retry must be bounded and eventually succeed: {server_retry_ok}, calls={server_error_then_ok.calls}")

    auth_error = _counting_http_error_urlopen(401, "bad key")
    auth_result = openai_connection_test(env=_configured_env(isolated_env), urlopen=auth_error)
    _assert_result(auth_result, "failed", "auth_error", http_status=401)
    if auth_error.calls != 1:
        raise AssertionError(f"auth errors must not be retried: calls={auth_error.calls}")

    certificate = openai_connection_test(env=_configured_env(isolated_env), urlopen=_certificate_error_urlopen)
    _assert_result(certificate, "failed", "certificate_error")

    invalid_json = openai_connection_test(env=_configured_env(isolated_env), urlopen=_response_urlopen("not-json"))
    _assert_result(invalid_json, "failed", "invalid_json")

    invalid_shape = openai_connection_test(env=_configured_env(isolated_env), urlopen=_response_urlopen('{"unexpected": true}'))
    _assert_result(invalid_shape, "failed", "unexpected_response_shape")

    ok = openai_connection_test(env=_configured_env(isolated_env), urlopen=_responses_ok_urlopen)
    if ok.status != "ok" or ok.message != "OpenAI работает" or ok.output_text != "OK":
        raise AssertionError(f"expected ok OpenAI probe: {ok}")

    _, chat_diagnostic = openai_curator_chat_reply(
        [{"role": "operator", "content": "test"}],
        env=_configured_env(isolated_env),
        urlopen=_http_error_urlopen(404, "model does not exist"),
    )
    if not chat_diagnostic or chat_diagnostic.error_type != "model_not_found":
        raise AssertionError(f"chat error must map model_not_found: {chat_diagnostic}")
    if "sk-" in json.dumps(chat_diagnostic.__dict__, ensure_ascii=False):
        raise AssertionError("chat diagnostic leaked key-like content")


def _exercise_probe_missing_key(isolated_env: dict[str, str]) -> None:
    env = os.environ.copy()
    env.pop("OPENAI_API_KEY", None)
    env.pop("CURATOR_COCKPIT_OPENAI_MODEL", None)
    env.pop("CURATOR_COCKPIT_OPENAI_REASONING_EFFORT", None)
    env.pop("DEV_CONTROL_PLANE_OPENAI_TIMEOUT_SECONDS", None)
    env.pop("DEV_CONTROL_PLANE_OPENAI_RETRY_COUNT", None)
    env.pop("DEV_CONTROL_PLANE_OPENAI_RETRY_BACKOFF_SECONDS", None)
    env.update(isolated_env)
    completed = subprocess.run(
        [sys.executable, str(PROBE)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode == 0:
        raise AssertionError(f"probe must fail without key: {completed.stdout}")
    payload = json.loads(completed.stdout)
    if payload.get("error_type") != "missing_api_key" or payload.get("status") != "blocked":
        raise AssertionError(f"probe missing-key output wrong: {payload}")
    _assert_sanitized(payload)


def _exercise_server_diagnostics() -> None:
    with TemporaryDirectory(prefix="dev-control-plane-openai-diagnostics-") as tmp:
        port = _free_port()
        state_dir = Path(tmp) / "state"
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
            env=_server_env_without_openai(Path(tmp) / "empty-secrets"),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            base_url = f"http://127.0.0.1:{port}"
            _wait_ready(base_url)
            html = _get_text(base_url + "/")
            if "Проверить OpenAI" not in html:
                raise AssertionError("UI must include OpenAI test button")

            status = _post_json(base_url + "/api/connections/openai-test", {})
            if status.get("status") != "blocked" or status.get("error_type") != "missing_api_key":
                raise AssertionError(f"server OpenAI test missing-key response wrong: {status}")
            _assert_sanitized(status)

            discussion = _post_json(base_url + "/api/discussions", {"title": "OpenAI diagnostics smoke"})
            discussion = _post_json(
                base_url + f"/api/discussions/{discussion['id']}/messages",
                {"role": "operator", "content": "Проверь диагностику OpenAI."},
            )
            messages = discussion.get("messages", [])
            if "OpenAI-куратор не подключён" not in messages[-1].get("content", ""):
                raise AssertionError(f"chat must show safe OpenAI blocker: {messages}")
            serialized = json.dumps(discussion, ensure_ascii=False)
            if "Traceback" in serialized or "Authorization" in serialized:
                raise AssertionError(f"chat diagnostics leaked unsafe detail: {discussion}")
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def _exercise_server_file_backed_status() -> None:
    with TemporaryDirectory(prefix="dev-control-plane-openai-file-status-") as tmp:
        secret_home = Path(tmp) / "secrets"
        old_secret_home = os.environ.get(SECRET_HOME_ENV)
        os.environ[SECRET_HOME_ENV] = str(secret_home)
        try:
            set_openai_credentials("sk-file-status-smoke", "gpt-file-status")
            port = _free_port()
            state_dir = Path(tmp) / "state"
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
                env=_server_env_with_secret_file(secret_home),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            try:
                base_url = f"http://127.0.0.1:{port}"
                _wait_ready(base_url)
                status = _get_json(base_url + "/api/connections/status")
                openai = status.get("openai", {})
                if openai.get("configured") is not True or openai.get("source") != "file":
                    raise AssertionError(f"server status must read file-backed credentials: {status}")
                if openai.get("reasoning_effort") != "xhigh":
                    raise AssertionError(f"server status must report OpenAI reasoning effort: {status}")
                _assert_sanitized(status)
            finally:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            delete_openai_credentials()
        finally:
            if old_secret_home is None:
                os.environ.pop(SECRET_HOME_ENV, None)
            else:
                os.environ[SECRET_HOME_ENV] = old_secret_home


def _assert_result(result, expected_status: str, expected_error: str, http_status: int | None = None) -> None:
    if result.status != expected_status or result.error_type != expected_error:
        raise AssertionError(f"expected {expected_status}/{expected_error}, got {result}")
    if http_status is not None and result.http_status != http_status:
        raise AssertionError(f"expected HTTP {http_status}, got {result.http_status}")
    payload = openai_connection_test_result_to_dict(result)
    _assert_sanitized(payload)


def _assert_sanitized(payload) -> None:
    serialized = json.dumps(payload, ensure_ascii=False)
    for forbidden in ("sk-test", "sk-file", "Bearer", "Authorization", "Traceback"):
        if forbidden in serialized:
            raise AssertionError(f"diagnostic payload leaked unsafe detail {forbidden}: {payload}")


def _configured_env(isolated_env: dict[str, str]) -> dict[str, str]:
    return {
        **isolated_env,
        "OPENAI_API_KEY": "sk-test",
        "CURATOR_COCKPIT_OPENAI_MODEL": "gpt-test",
        "CURATOR_COCKPIT_OPENAI_REASONING_EFFORT": "xhigh",
        "DEV_CONTROL_PLANE_OPENAI_TIMEOUT_SECONDS": "180",
        "DEV_CONTROL_PLANE_OPENAI_RETRY_COUNT": "2",
        "DEV_CONTROL_PLANE_OPENAI_RETRY_BACKOFF_SECONDS": "0",
    }


def _http_error_urlopen(status_code: int, body: str):
    def _urlopen(_request, timeout=None):
        headers = Message()
        headers["x-request-id"] = "req_smoke"
        raise urllib_error.HTTPError(
            url="https://api.openai.com/v1/responses",
            code=status_code,
            msg="smoke",
            hdrs=headers,
            fp=io.BytesIO(body.encode("utf-8")),
        )

    return _urlopen


def _counting_http_error_urlopen(status_code: int, body: str):
    inner = _http_error_urlopen(status_code, body)

    def _urlopen(request, timeout=None):
        _urlopen.calls += 1
        return inner(request, timeout=timeout)

    _urlopen.calls = 0
    return _urlopen


def _timeout_then_ok_urlopen(*, failures: int):
    def _urlopen(request, timeout=None):
        _urlopen.calls += 1
        if _urlopen.calls <= failures:
            raise urllib_error.URLError(socket.timeout("timed out"))
        return _responses_ok_urlopen(request, timeout=timeout)

    _urlopen.calls = 0
    return _urlopen


def _http_error_then_ok_urlopen(status_code: int, body: str):
    error_urlopen = _http_error_urlopen(status_code, body)

    def _urlopen(request, timeout=None):
        _urlopen.calls += 1
        if _urlopen.calls == 1:
            return error_urlopen(request, timeout=timeout)
        return _responses_ok_urlopen(request, timeout=timeout)

    _urlopen.calls = 0
    return _urlopen


def _timeout_urlopen(_request, timeout=None):
    raise urllib_error.URLError(socket.timeout("timed out"))


def _certificate_error_urlopen(_request, timeout=None):
    raise urllib_error.URLError(ssl.SSLCertVerificationError("CERTIFICATE_VERIFY_FAILED"))


def _response_urlopen(body: str):
    def _urlopen(_request, timeout=None):
        return _FakeResponse(body)

    return _urlopen


def _responses_ok_urlopen(request, timeout=None):
    if timeout != 180.0:
        raise AssertionError(f"OpenAI request timeout must default to hosted deep timeout in smokes: {timeout}")
    if request.full_url != OPENAI_RESPONSES_URL:
        raise AssertionError(f"OpenAI request URL must match Responses API: {request.full_url}")
    if request.get_method() != "POST":
        raise AssertionError(f"OpenAI request method must be POST: {request.get_method()}")
    headers = {key.lower(): value for key, value in request.header_items()}
    if not str(headers.get("authorization") or "").startswith("Bearer "):
        raise AssertionError(f"OpenAI request must include Bearer authorization header: {headers}")
    if headers.get("content-type") != "application/json":
        raise AssertionError(f"OpenAI request must be JSON: {headers}")
    payload = json.loads((request.data or b"{}").decode("utf-8"))
    expected_payload = {"model": "gpt-test", "input": "Ответь только OK", "reasoning": {"effort": "xhigh"}}
    if payload != expected_payload:
        raise AssertionError(f"OpenAI probe payload must include sanitized reasoning config: {payload}")
    return _FakeResponse(
        json.dumps(
            {
                "id": "resp_smoke",
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "OK"}],
                    }
                ],
            },
            ensure_ascii=False,
        )
    )


class _FakeResponse:
    def __init__(self, body: str) -> None:
        self._body = body.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb):
        return False

    def read(self) -> bytes:
        return self._body


def _server_env_without_openai(secret_home: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("OPENAI_API_KEY", None)
    env.pop("CURATOR_COCKPIT_OPENAI_MODEL", None)
    env.pop("CURATOR_COCKPIT_OPENAI_REASONING_EFFORT", None)
    env.pop("DEV_CONTROL_PLANE_OPENAI_TIMEOUT_SECONDS", None)
    env.pop("DEV_CONTROL_PLANE_OPENAI_RETRY_COUNT", None)
    env.pop("DEV_CONTROL_PLANE_OPENAI_RETRY_BACKOFF_SECONDS", None)
    env[SECRET_HOME_ENV] = str(secret_home)
    return env


def _server_env_with_secret_file(secret_home: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("OPENAI_API_KEY", None)
    env.pop("CURATOR_COCKPIT_OPENAI_MODEL", None)
    env.pop("CURATOR_COCKPIT_OPENAI_REASONING_EFFORT", None)
    env.pop("DEV_CONTROL_PLANE_OPENAI_TIMEOUT_SECONDS", None)
    env.pop("DEV_CONTROL_PLANE_OPENAI_RETRY_COUNT", None)
    env.pop("DEV_CONTROL_PLANE_OPENAI_RETRY_BACKOFF_SECONDS", None)
    env[SECRET_HOME_ENV] = str(secret_home)
    return env


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
    return json.loads(_get_text(url))


def _get_text(url: str) -> str:
    with urllib_request.urlopen(url, timeout=10) as response:
        return response.read().decode("utf-8")


def _post_json(url: str, payload: dict) -> dict:
    body = json.dumps(payload).encode("utf-8")
    request = urllib_request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib_request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


if __name__ == "__main__":
    main()
