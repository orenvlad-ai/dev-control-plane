"""Loopback-only hosted projection v2 entrypoint."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (SRC, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dev_control_plane.projection_server import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
