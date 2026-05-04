"""Manual sanitized OpenAI connection probe for Development Control Plane."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (SRC, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dev_control_plane.ai import openai_connection_test, openai_connection_test_result_to_dict  # noqa: E402


def main() -> int:
    result = openai_connection_test(urlopen=_stub_urlopen) if _stub_enabled() else openai_connection_test()
    print(json.dumps(openai_connection_test_result_to_dict(result), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == "ok" else 1


def _stub_enabled() -> bool:
    return str(os.environ.get("DEV_CONTROL_PLANE_OPENAI_PROBE_STUB") or "").strip() == "1"


def _stub_urlopen(_request, timeout=None):
    return _StubResponse('{"output_text": "OK"}')


class _StubResponse:
    def __init__(self, body: str) -> None:
        self._body = body.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb):
        return False

    def read(self) -> bytes:
        return self._body


if __name__ == "__main__":
    raise SystemExit(main())
