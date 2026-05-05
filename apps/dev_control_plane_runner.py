"""Local repo-only runner CLI for development control-plane MVP execution artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Callable, Mapping

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (SRC, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dev_control_plane.contracts import ControlPlaneValidationError  # noqa: E402
from dev_control_plane.execution import (  # noqa: E402
    ControlPlaneExecutionError,
    cleanup_target_run,
    cleanup_run_worktree,
    prepare_target_run,
    prepare_run,
    real_codex_run_result_to_dict,
    run_result_to_dict,
    run_codex_cli,
    run_step,
    verifier_result_to_dict,
    verify_target_run,
    verify_run,
)
from dev_control_plane.github_closure import (  # noqa: E402
    evaluate_dev_control_plane_closure_decision,
    github_closure_decision_to_dict,
)
from dev_control_plane.state_layout import DEFAULT_STATE_DIR, STATE_DIR_ENV, resolve_state_root  # noqa: E402
from dev_control_plane.target_projects import load_target_project_config  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.handler(args)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Repo-only development control-plane MVP runner.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare_parser = subparsers.add_parser("prepare-run")
    _add_run_inputs(prepare_parser)
    prepare_parser.set_defaults(handler=_handle_prepare_run)

    run_parser = subparsers.add_parser("run-step")
    _add_run_inputs(run_parser)
    run_parser.add_argument("--executor-mode", choices=("fake", "command"), default="fake")
    run_parser.add_argument("--allow-real-executor", action="store_true")
    run_parser.add_argument("--executor-command")
    run_parser.add_argument("--cleanup", action="store_true")
    run_parser.set_defaults(handler=_handle_run_step)

    verify_parser = subparsers.add_parser("verify-run")
    verify_parser.add_argument("--run-dir", required=True, type=Path)
    verify_parser.set_defaults(handler=_handle_verify_run)

    cleanup_parser = subparsers.add_parser("cleanup-run")
    cleanup_parser.add_argument("--run-dir", required=True, type=Path)
    cleanup_parser.set_defaults(handler=_handle_cleanup_run)

    prepare_target_parser = subparsers.add_parser("prepare-target-run")
    _add_target_run_inputs(prepare_target_parser)
    prepare_target_parser.set_defaults(handler=_handle_prepare_target_run)

    codex_parser = subparsers.add_parser("run-codex-cli")
    _add_target_run_inputs(codex_parser)
    codex_parser.add_argument("--allow-real-codex", action="store_true")
    codex_parser.add_argument("--codex-bin")
    codex_parser.add_argument("--codex-extra-arg", action="append", default=[])
    codex_parser.set_defaults(handler=_handle_run_codex_cli)

    verify_target_parser = subparsers.add_parser("verify-target-run")
    verify_target_parser.add_argument("--run-dir", required=True, type=Path)
    verify_target_parser.set_defaults(handler=_handle_verify_target_run)

    cleanup_target_parser = subparsers.add_parser("cleanup-target-run")
    cleanup_target_parser.add_argument("--run-dir", required=True, type=Path)
    cleanup_target_parser.set_defaults(handler=_handle_cleanup_target_run)

    github_closure_parser = subparsers.add_parser("github-closure-decision")
    github_closure_parser.add_argument("--input", required=True, type=Path)
    github_closure_parser.add_argument(
        "--auto-merge",
        action="store_true",
        help="Evaluate merge/delete-branch eligibility; does not call GitHub APIs.",
    )
    github_closure_parser.set_defaults(handler=_handle_github_closure_decision)

    return parser


def _add_run_inputs(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--task-spec", required=True, type=Path)
    parser.add_argument("--step-id")
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument(
        "--state-dir",
        type=Path,
        help=f"Control-plane state root. Defaults to ${STATE_DIR_ENV} or {DEFAULT_STATE_DIR}.",
    )
    parser.add_argument("--base-ref")
    parser.add_argument("--branch-name")


def _add_target_run_inputs(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--target-config", required=True, type=Path)
    parser.add_argument("--task-spec", required=True, type=Path)
    parser.add_argument("--step-id")
    parser.add_argument(
        "--state-dir",
        type=Path,
        help=f"Control-plane state root. Defaults to ${STATE_DIR_ENV} or {DEFAULT_STATE_DIR}.",
    )
    parser.add_argument("--base-ref")


def _handle_prepare_run(args: argparse.Namespace) -> int:
    return _run_json_command(lambda: _prepare_run_summary(args))


def _handle_run_step(args: argparse.Namespace) -> int:
    return _run_json_command(lambda: _run_step_summary(args))


def _handle_verify_run(args: argparse.Namespace) -> int:
    return _run_json_command(lambda: _verify_run_summary(args.run_dir))


def _handle_cleanup_run(args: argparse.Namespace) -> int:
    return _run_json_command(lambda: (cleanup_run_worktree(args.run_dir), 0))


def _handle_prepare_target_run(args: argparse.Namespace) -> int:
    return _run_json_command(lambda: _prepare_target_run_summary(args))


def _handle_run_codex_cli(args: argparse.Namespace) -> int:
    return _run_json_command(lambda: _run_codex_cli_summary(args))


def _handle_verify_target_run(args: argparse.Namespace) -> int:
    return _run_json_command(lambda: _verify_target_run_summary(args.run_dir))


def _handle_cleanup_target_run(args: argparse.Namespace) -> int:
    return _run_json_command(lambda: (cleanup_target_run(args.run_dir), 0))


def _handle_github_closure_decision(args: argparse.Namespace) -> int:
    return _run_json_command(lambda: _github_closure_decision_summary(args))


def _prepare_run_summary(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    payload = _read_json(args.task_spec)
    result = prepare_run(
        payload,
        step_id=args.step_id,
        repo_root=args.repo_root,
        state_dir=_state_dir_arg(args.state_dir),
        base_ref=args.base_ref,
        branch_name=args.branch_name,
    )
    summary = _summary_from_run_result(result)
    _add_step_selection_warning(summary, args.step_id)
    summary["verifier_status"] = None
    return summary, 0


def _run_step_summary(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    payload = _read_json(args.task_spec)
    result = run_step(
        payload,
        step_id=args.step_id,
        repo_root=args.repo_root,
        state_dir=_state_dir_arg(args.state_dir),
        base_ref=args.base_ref,
        branch_name=args.branch_name,
        executor_mode=args.executor_mode,
        allow_real_executor=args.allow_real_executor,
        executor_command=args.executor_command,
    )
    summary = _summary_from_run_result(result)
    _add_step_selection_warning(summary, args.step_id)
    summary["verifier_status"] = "passed" if result.status == "verifier_passed" else result.status
    if args.cleanup:
        summary["cleanup"] = cleanup_run_worktree(Path(result.run_dir))
    return summary, 0 if result.status == "verifier_passed" else 1


def _prepare_target_run_summary(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    payload = _read_json(args.task_spec)
    target_config = load_target_project_config(args.target_config)
    result = prepare_target_run(
        payload,
        target_config=target_config,
        step_id=args.step_id,
        state_dir=_state_dir_arg(args.state_dir),
        base_ref=args.base_ref,
        target_config_path=args.target_config,
    )
    summary = _summary_from_real_codex_result(result)
    _add_step_selection_warning(summary, args.step_id)
    summary["verifier_status"] = None
    return summary, 0


def _run_codex_cli_summary(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    payload = _read_json(args.task_spec)
    target_config = load_target_project_config(args.target_config)
    result = run_codex_cli(
        payload,
        target_config=target_config,
        step_id=args.step_id,
        state_dir=_state_dir_arg(args.state_dir),
        allow_real_codex=args.allow_real_codex,
        codex_bin=args.codex_bin,
        codex_args=tuple(args.codex_extra_arg or ()),
        base_ref=args.base_ref,
        target_config_path=args.target_config,
    )
    summary = _summary_from_real_codex_result(result)
    _add_step_selection_warning(summary, args.step_id)
    summary["verifier_status"] = result.verifier_status
    return summary, 0 if result.status == "verifier_passed" else 1


def _verify_run_summary(run_dir: Path) -> tuple[dict[str, Any], int]:
    verifier = verify_run(run_dir)
    summary = {
        "status": "verified" if verifier.status == "passed" else "verification_failed",
        "run_dir": str(run_dir),
        "verifier_status": verifier.status,
        "changed_files": list(verifier.changed_files),
        "forbidden_path_hits": list(verifier.forbidden_path_hits),
        "mandatory_handoff_blocks_present": verifier.mandatory_handoff_blocks_present,
        "check_results": [check for check in verifier_result_to_dict(verifier)["check_results"]],
        "blocker_reason": verifier.blocker_reason,
    }
    return summary, 0 if verifier.status == "passed" else 1


def _verify_target_run_summary(run_dir: Path) -> tuple[dict[str, Any], int]:
    verifier = verify_target_run(run_dir)
    summary = {
        "status": "verified" if verifier.status == "passed" else "verification_failed",
        "run_dir": str(run_dir),
        "verifier_status": verifier.status,
        "changed_files": list(verifier.changed_files),
        "forbidden_path_hits": list(verifier.forbidden_path_hits),
        "mandatory_handoff_blocks_present": verifier.mandatory_handoff_blocks_present,
        "check_results": [check for check in verifier_result_to_dict(verifier)["check_results"]],
        "blocker_reason": verifier.blocker_reason,
    }
    return summary, 0 if verifier.status == "passed" else 1


def _github_closure_decision_summary(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    payload = _read_json(args.input)
    decision = evaluate_dev_control_plane_closure_decision(payload, requested_auto_merge=args.auto_merge)
    summary = github_closure_decision_to_dict(decision)
    summary["requested_auto_merge"] = bool(args.auto_merge)
    return summary, 0 if decision.allowed else 1


def _summary_from_run_result(result) -> dict[str, Any]:
    payload = run_result_to_dict(result)
    return {
        "status": result.status,
        "run_id": result.id,
        "task_spec_id": result.task_spec_id,
        "step_id": result.step_id,
        "branch_name": result.branch_name,
        "run_dir": result.run_dir,
        "worktree_path": result.worktree_path,
        "prompt_path": result.prompt_path,
        "handoff_path": result.handoff_path,
        "log_path": result.log_path,
        "changed_files": payload["changed_files"],
        "check_results": payload["check_results"],
        "blocker_reason": result.blocker_reason,
        "next_manual_step": result.next_manual_step,
    }


def _summary_from_real_codex_result(result) -> dict[str, Any]:
    payload = real_codex_run_result_to_dict(result)
    return {
        "status": result.status,
        "run_id": result.id,
        "target_project_id": result.target_project_id,
        "task_spec_id": result.task_spec_id,
        "step_id": result.step_id,
        "run_dir": result.run_dir,
        "workspace_path": result.workspace_path,
        "prompt_path": result.prompt_path,
        "handoff_path": result.handoff_path,
        "log_path": result.log_path,
        "diff_path": result.diff_path,
        "changed_files": payload["changed_files"],
        "check_results": payload["check_results"],
        "verifier_status": result.verifier_status,
        "blocker_reason": result.blocker_reason,
        "next_manual_step": result.next_manual_step,
        "codex_exit_code": result.codex_exit_code,
    }


def _run_json_command(callback: Callable[[], tuple[dict[str, Any], int]]) -> int:
    try:
        summary, exit_code = callback()
    except (ControlPlaneValidationError, ControlPlaneExecutionError) as exc:
        summary = {
            "status": "blocked",
            "run_id": None,
            "validation_ok": False,
            "errors": [str(exc)],
            "blocker_reason": str(exc),
        }
        exit_code = 1
    except Exception as exc:
        summary = {
            "status": "error",
            "run_id": None,
            "validation_ok": False,
            "errors": [str(exc)],
            "blocker_reason": str(exc),
        }
        exit_code = 1
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return exit_code


def _add_step_selection_warning(summary: dict[str, Any], requested_step_id: str | None) -> None:
    if requested_step_id and requested_step_id != summary.get("step_id"):
        summary.setdefault("warnings", []).append(
            f"requested step_id {requested_step_id} not found; used first runnable step {summary.get('step_id')}"
        )


def _read_json(path: Path) -> Mapping[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ControlPlaneExecutionError("JSON root must be an object")
    return payload


def _state_dir_arg(path: Path | None) -> Path:
    return resolve_state_root(path)


if __name__ == "__main__":
    raise SystemExit(main())
