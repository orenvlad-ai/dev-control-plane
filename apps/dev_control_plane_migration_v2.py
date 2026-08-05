"""CLI for non-destructive Orchestrator v2 legacy migration."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (SRC, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dev_control_plane.migration import (  # noqa: E402
    MigrationError,
    archive_legacy_monitor,
    prove_legacy_absence,
    retire_legacy_monitor,
    shadow_snapshot,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Archive/compare/retire legacy local observer")
    subparsers = parser.add_subparsers(dest="command", required=True)
    archive = subparsers.add_parser("archive")
    archive.add_argument("--destination", type=Path, required=True)
    absence = subparsers.add_parser("absence")
    absence.add_argument("--destination", type=Path, required=True)
    shadow = subparsers.add_parser("shadow")
    shadow.add_argument("--source-db", type=Path)
    retire = subparsers.add_parser("retire")
    retire.add_argument("--archive-manifest", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "archive":
            payload = asdict(archive_legacy_monitor(destination=args.destination))
        elif args.command == "absence":
            payload = asdict(prove_legacy_absence(destination=args.destination))
        elif args.command == "shadow":
            payload = shadow_snapshot(args.source_db) if args.source_db else shadow_snapshot()
        else:
            payload = retire_legacy_monitor(archive_manifest=args.archive_manifest)
    except MigrationError as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}, ensure_ascii=False, sort_keys=True))
        return 1
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
