"""Local setup CLI for Development Control Plane credentials."""

from __future__ import annotations

import argparse
import getpass
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (SRC, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dev_control_plane.secrets import (  # noqa: E402
    SecretStoreError,
    delete_openai_credentials,
    get_openai_status,
    set_openai_credentials,
)

DEFAULT_OPENAI_MODEL = "gpt-5.5"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Development Control Plane local setup.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("openai").set_defaults(handler=_handle_openai)
    subparsers.add_parser("status").set_defaults(handler=_handle_status)
    subparsers.add_parser("delete-openai").set_defaults(handler=_handle_delete_openai)
    args = parser.parse_args(argv)
    return args.handler(args)


def _handle_openai(_args: argparse.Namespace) -> int:
    try:
        api_key = getpass.getpass("OpenAI API key: ").strip()
        model = input(f"Model [{DEFAULT_OPENAI_MODEL}]: ").strip() or DEFAULT_OPENAI_MODEL
        summary = set_openai_credentials(api_key, model)
    except (SecretStoreError, EOFError, KeyboardInterrupt) as exc:
        summary = {"status": "error", "error": str(exc)}
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        return 1
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


def _handle_status(_args: argparse.Namespace) -> int:
    print(json.dumps({"openai": get_openai_status()}, ensure_ascii=False, sort_keys=True))
    return 0


def _handle_delete_openai(_args: argparse.Namespace) -> int:
    print(json.dumps(delete_openai_credentials(), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
