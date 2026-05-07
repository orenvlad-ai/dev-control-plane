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
    DEFAULT_OPENAI_REASONING_EFFORT,
    SecretStoreError,
    delete_mcp_token,
    delete_openai_credentials,
    generate_mcp_token,
    get_mcp_auth_status,
    get_openai_status,
    set_mcp_token,
    set_openai_credentials,
)

DEFAULT_OPENAI_MODEL = "gpt-5.5"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Development Control Plane local setup.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("openai").set_defaults(handler=_handle_openai)
    subparsers.add_parser("mcp-token").set_defaults(handler=_handle_mcp_token)
    subparsers.add_parser("generate-mcp-token").set_defaults(handler=_handle_generate_mcp_token)
    subparsers.add_parser("status").set_defaults(handler=_handle_status)
    subparsers.add_parser("delete-openai").set_defaults(handler=_handle_delete_openai)
    subparsers.add_parser("delete-mcp-token").set_defaults(handler=_handle_delete_mcp_token)
    args = parser.parse_args(argv)
    return args.handler(args)


def _handle_openai(_args: argparse.Namespace) -> int:
    try:
        api_key = getpass.getpass("OpenAI API key: ").strip()
        model = input(f"Model [{DEFAULT_OPENAI_MODEL}]: ").strip() or DEFAULT_OPENAI_MODEL
        reasoning_effort = (
            input(f"Reasoning effort [{DEFAULT_OPENAI_REASONING_EFFORT}]: ").strip()
            or DEFAULT_OPENAI_REASONING_EFFORT
        )
        summary = set_openai_credentials(api_key, model, reasoning_effort)
    except (SecretStoreError, EOFError, KeyboardInterrupt) as exc:
        summary = {"status": "error", "error": str(exc)}
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        return 1
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


def _handle_status(_args: argparse.Namespace) -> int:
    print(json.dumps({"openai": get_openai_status(), "mcp": get_mcp_auth_status()}, ensure_ascii=False, sort_keys=True))
    return 0


def _handle_delete_openai(_args: argparse.Namespace) -> int:
    print(json.dumps(delete_openai_credentials(), ensure_ascii=False, sort_keys=True))
    return 0


def _handle_mcp_token(_args: argparse.Namespace) -> int:
    try:
        token = getpass.getpass("MCP bearer token: ").strip()
        summary = set_mcp_token(token)
    except (SecretStoreError, EOFError, KeyboardInterrupt) as exc:
        summary = {"status": "error", "error": str(exc)}
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        return 1
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


def _handle_generate_mcp_token(_args: argparse.Namespace) -> int:
    try:
        summary = generate_mcp_token()
    except SecretStoreError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False, sort_keys=True))
        return 1
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


def _handle_delete_mcp_token(_args: argparse.Namespace) -> int:
    print(json.dumps(delete_mcp_token(), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
