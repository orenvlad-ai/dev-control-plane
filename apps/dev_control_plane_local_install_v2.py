"""CLI for versioned local Supervisor v2 installation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (SRC, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dev_control_plane.local_install import (  # noqa: E402
    LocalInstallError,
    LocalInstaller,
    LocalInstallLayout,
    result_to_dict,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install/update/rollback local Supervisor v2")
    parser.add_argument("--runtime-root", type=Path)
    parser.add_argument("--launch-agents-dir", type=Path)
    subparsers = parser.add_subparsers(dest="command", required=True)
    install = subparsers.add_parser("install")
    install.add_argument("--source", type=Path, default=ROOT)
    install.add_argument("--expected-sha")
    install.add_argument("--allow-non-main", action="store_true", help="Test/development installs only")
    install.add_argument("--activate", action="store_true")
    install.add_argument("--qualification-manifest", type=Path)
    rollback = subparsers.add_parser("rollback")
    rollback.add_argument("--activate", action="store_true")
    subparsers.add_parser("status")
    args = parser.parse_args(argv)
    layout = LocalInstallLayout.resolve(args.runtime_root, launch_agents_dir=args.launch_agents_dir)
    installer = LocalInstaller(layout)
    try:
        if args.command == "install":
            if args.allow_non_main and args.activate:
                raise LocalInstallError("--allow-non-main cannot be combined with --activate")
            result = result_to_dict(
                installer.install(
                    source_root=args.source,
                    expected_sha=args.expected_sha,
                    require_origin_main=not args.allow_non_main,
                    activate=args.activate,
                    qualification_manifest=args.qualification_manifest,
                )
            )
        elif args.command == "rollback":
            result = result_to_dict(installer.rollback(activate=args.activate))
        else:
            result = installer.status()
    except LocalInstallError as exc:
        result = {"status": "blocked", "reason": str(exc)}
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
