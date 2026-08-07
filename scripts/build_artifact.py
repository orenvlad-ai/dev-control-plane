#!/usr/bin/env python3
"""Build a deterministic, dependency-free DCP laboratory zipapp outside Git."""

from __future__ import annotations

import argparse
from io import BytesIO
from pathlib import Path
import stat
import sys
import zipfile

SOURCE_ROOT = Path(__file__).resolve().parents[1]
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from dcp_orchestrator.config import BUNDLE_ID  # noqa: E402


FIXED_TIME = (2026, 8, 7, 0, 0, 0)


def default_output() -> Path:
    return (
        Path.home()
        / "Library"
        / "Caches"
        / BUNDLE_ID
        / "build"
        / "dcp-orchestrator-lab.pyz"
    )


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def artifact_entries() -> list[tuple[str, bytes]]:
    entries: list[tuple[str, bytes]] = [
        (
            "__main__.py",
            b"from dcp_orchestrator.server import main\n\nif __name__ == '__main__':\n    main()\n",
        )
    ]
    for path in sorted((SOURCE_ROOT / "dcp_orchestrator").rglob("*")):
        if path.is_file() and path.suffix in {".py", ".html", ".js", ".css"}:
            entries.append((path.relative_to(SOURCE_ROOT).as_posix(), path.read_bytes()))
    entries.extend(
        [
            ("NOTICE", (SOURCE_ROOT / "NOTICE").read_bytes()),
            (
                "licenses/agent-orchestrator-APACHE-2.0.txt",
                (SOURCE_ROOT / "third_party" / "agent-orchestrator" / "LICENSE").read_bytes(),
            ),
            (
                "licenses/agent-orchestrator-PROVENANCE.md",
                (SOURCE_ROOT / "third_party" / "agent-orchestrator" / "PROVENANCE.md").read_bytes(),
            ),
        ]
    )
    return entries


def build(output: Path) -> Path:
    output = output.expanduser().resolve()
    if not output.is_absolute() or _inside(output, SOURCE_ROOT):
        raise ValueError("artifact output must be an absolute path outside the source repository")
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    memory = BytesIO()
    with zipfile.ZipFile(memory, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, payload in artifact_entries():
            info = zipfile.ZipInfo(name, FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o644 & 0xFFFF) << 16
            archive.writestr(info, payload)
    output.write_bytes(b"#!/usr/bin/env python3\n" + memory.getvalue())
    output.chmod(output.stat().st_mode | stat.S_IXUSR)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=default_output())
    args = parser.parse_args()
    path = build(args.output)
    print(path)


if __name__ == "__main__":
    main()
