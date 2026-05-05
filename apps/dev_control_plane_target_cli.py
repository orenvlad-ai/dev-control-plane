"""Target project adapter CLI for Development Control Plane."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (SRC, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dev_control_plane.target_projects import (  # noqa: E402
    build_target_context_snapshot,
    load_target_project_config,
    load_target_project_configs,
    target_context_snapshot_to_dict,
    target_project_config_to_dict,
    target_project_validation_result_to_dict,
    validate_target_project,
)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.handler(args)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Development Control Plane target project tooling.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list-targets")
    list_parser.add_argument("--config-dir", required=True, type=Path)
    list_parser.set_defaults(handler=_handle_list_targets)

    validate_parser = subparsers.add_parser("validate-target")
    validate_parser.add_argument("--config", required=True, type=Path)
    validate_parser.set_defaults(handler=_handle_validate_target)

    snapshot_parser = subparsers.add_parser("snapshot-target")
    snapshot_parser.add_argument("--config", required=True, type=Path)
    snapshot_parser.add_argument("--output", required=True, type=Path)
    snapshot_parser.add_argument("--max-bytes-per-file", default=12000, type=int)
    snapshot_parser.set_defaults(handler=_handle_snapshot_target)

    return parser


def _handle_list_targets(args: argparse.Namespace) -> int:
    return _run_json_command(lambda: _list_targets(args.config_dir))


def _handle_validate_target(args: argparse.Namespace) -> int:
    return _run_json_command(lambda: _validate_target(args.config))


def _handle_snapshot_target(args: argparse.Namespace) -> int:
    return _run_json_command(lambda: _snapshot_target(args.config, args.output, args.max_bytes_per_file))


def _list_targets(config_dir: Path) -> tuple[dict[str, Any], int]:
    configs = load_target_project_configs(config_dir)
    targets = []
    for config in configs:
        targets.append(
            {
                "project_id": config.project_id,
                "display_name": config.display_name,
                "repo_path": config.repo_path,
                "source_mode": config.source_mode,
                "repo_url": config.repo_url,
                "branch": config.branch,
                "target_readonly_by_default": config.target_readonly_by_default,
            }
        )
    return {"status": "ok", "targets": targets}, 0


def _validate_target(config_path: Path) -> tuple[dict[str, Any], int]:
    config = load_target_project_config(config_path)
    result = validate_target_project(config)
    payload = target_project_validation_result_to_dict(result)
    return payload, 1 if result.status == "blocked" else 0


def _snapshot_target(config_path: Path, output_path: Path, max_bytes_per_file: int) -> tuple[dict[str, Any], int]:
    config = load_target_project_config(config_path)
    snapshot = build_target_context_snapshot(config, max_bytes_per_file=max_bytes_per_file)
    payload = target_context_snapshot_to_dict(snapshot)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary = {
        "status": "snapshot_created",
        "output_path": str(output_path),
        "project_id": snapshot.project_id,
        "head_commit": snapshot.head_commit,
        "source_file_count": len(snapshot.source_files),
        "warning_count": len(validate_target_project(config).warnings),
        "target": target_project_config_to_dict(config),
    }
    return summary, 0


def _run_json_command(callback: Callable[[], tuple[dict[str, Any], int]]) -> int:
    try:
        summary, exit_code = callback()
    except Exception as exc:
        summary = {
            "status": "error",
            "errors": [str(exc)],
            "blockers": [str(exc)],
        }
        exit_code = 1
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
