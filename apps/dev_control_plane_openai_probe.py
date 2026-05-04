"""Manual sanitized OpenAI connection probe for Development Control Plane."""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (SRC, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dev_control_plane.ai import openai_connection_test, openai_connection_test_result_to_dict  # noqa: E402


def main() -> int:
    result = openai_connection_test()
    print(json.dumps(openai_connection_test_result_to_dict(result), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
