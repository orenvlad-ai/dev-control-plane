"""Target project adapter/config support for external repos."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
from typing import Any, Literal, Mapping, Sequence

from dev_control_plane.contracts import (
    ControlPlaneValidationError,
    TaskSpec,
    task_spec_from_mapping,
    task_spec_to_dict,
    validate_task_spec,
)

TargetProjectStatus = Literal["valid", "warning", "blocked"]

TEXT_SUFFIXES = {".md", ".txt", ".rst", ".json", ".toml", ".yaml", ".yml"}
DEFAULT_MAX_BYTES_PER_FILE = 12000
SOURCE_MODES = {"local_path", "remote_managed_clone"}


@dataclass(frozen=True)
class TargetProjectConfig:
    project_id: str
    display_name: str
    repo_path: str
    source_of_truth_paths: Sequence[str]
    derived_secondary_paths: Sequence[str]
    default_forbidden_paths: Sequence[str]
    default_forbidden_actions: Sequence[str]
    default_required_smokes: Sequence[str]
    codex_prompt_contract: Mapping[str, Any]
    control_plane_notes: Sequence[str]
    product_plane_notes: Sequence[str]
    target_readonly_by_default: bool
    execution_policy: Mapping[str, Any]
    operator_parity: Mapping[str, Any]
    source_mode: str = "local_path"
    repo_url: str | None = None
    branch: str = "main"

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_of_truth_paths", _to_tuple(self.source_of_truth_paths))
        object.__setattr__(self, "derived_secondary_paths", _to_tuple(self.derived_secondary_paths))
        object.__setattr__(self, "default_forbidden_paths", _to_tuple(self.default_forbidden_paths))
        object.__setattr__(self, "default_forbidden_actions", _to_tuple(self.default_forbidden_actions))
        object.__setattr__(self, "default_required_smokes", _to_tuple(self.default_required_smokes))
        object.__setattr__(self, "codex_prompt_contract", dict(self.codex_prompt_contract))
        object.__setattr__(self, "control_plane_notes", _to_tuple(self.control_plane_notes))
        object.__setattr__(self, "product_plane_notes", _to_tuple(self.product_plane_notes))
        object.__setattr__(self, "execution_policy", dict(self.execution_policy))
        object.__setattr__(self, "operator_parity", dict(self.operator_parity))


@dataclass(frozen=True)
class TargetProjectValidationResult:
    status: TargetProjectStatus
    project_id: str
    repo_path: str
    source_mode: str
    repo_url: str | None
    branch: str
    repo_exists: bool
    is_git_repo: bool
    remote_source_available: bool
    managed_clone_ready: bool
    current_branch: str | None
    head_commit: str | None
    dirty_state_summary: str | None
    source_of_truth_found: Sequence[str]
    missing_source_paths: Sequence[str]
    warnings: Sequence[str]
    blockers: Sequence[str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_of_truth_found", _to_tuple(self.source_of_truth_found))
        object.__setattr__(self, "missing_source_paths", _to_tuple(self.missing_source_paths))
        object.__setattr__(self, "warnings", _to_tuple(self.warnings))
        object.__setattr__(self, "blockers", _to_tuple(self.blockers))


@dataclass(frozen=True)
class TargetContextSnapshot:
    project_id: str
    repo_path: str
    source_mode: str
    repo_url: str | None
    branch: str
    head_commit: str | None
    current_branch: str | None
    source_files: Sequence[Mapping[str, Any]]
    source_summary: str
    forbidden_paths: Sequence[str]
    forbidden_actions: Sequence[str]
    required_smokes: Sequence[str]
    created_at: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_files", tuple(dict(item) for item in self.source_files))
        object.__setattr__(self, "forbidden_paths", _to_tuple(self.forbidden_paths))
        object.__setattr__(self, "forbidden_actions", _to_tuple(self.forbidden_actions))
        object.__setattr__(self, "required_smokes", _to_tuple(self.required_smokes))


@dataclass(frozen=True)
class TargetContextSummary:
    project_id: str
    display_name: str
    repo_path: str
    source_mode: str
    repo_url: str | None
    branch: str
    remote_source_available: bool
    managed_clone_ready: bool
    validation_status: TargetProjectStatus
    current_branch: str | None
    head_commit: str | None
    source_of_truth_paths_found: Sequence[str]
    missing_source_paths: Sequence[str]
    derived_secondary_paths: Sequence[str]
    default_forbidden_paths: Sequence[str]
    default_forbidden_actions: Sequence[str]
    default_required_smokes: Sequence[str]
    workflow_notes: Sequence[str]
    warnings: Sequence[str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_of_truth_paths_found", _to_tuple(self.source_of_truth_paths_found))
        object.__setattr__(self, "missing_source_paths", _to_tuple(self.missing_source_paths))
        object.__setattr__(self, "derived_secondary_paths", _to_tuple(self.derived_secondary_paths))
        object.__setattr__(self, "default_forbidden_paths", _to_tuple(self.default_forbidden_paths))
        object.__setattr__(self, "default_forbidden_actions", _to_tuple(self.default_forbidden_actions))
        object.__setattr__(self, "default_required_smokes", _to_tuple(self.default_required_smokes))
        object.__setattr__(self, "workflow_notes", _to_tuple(self.workflow_notes))
        object.__setattr__(self, "warnings", _to_tuple(self.warnings))


def load_target_project_config(path: Path) -> TargetProjectConfig:
    payload = _read_json(path)
    return TargetProjectConfig(
        project_id=_required_str(payload, "project_id"),
        display_name=_required_str(payload, "display_name"),
        repo_path=_required_str(payload, "repo_path"),
        source_mode=_optional_str(payload, "source_mode") or "local_path",
        repo_url=_optional_str(payload, "repo_url"),
        branch=_optional_str(payload, "branch") or "main",
        source_of_truth_paths=_sequence(payload, "source_of_truth_paths"),
        derived_secondary_paths=_sequence(payload, "derived_secondary_paths", default=()),
        default_forbidden_paths=_sequence(payload, "default_forbidden_paths"),
        default_forbidden_actions=_sequence(payload, "default_forbidden_actions"),
        default_required_smokes=_sequence(payload, "default_required_smokes", default=()),
        codex_prompt_contract=_mapping(payload, "codex_prompt_contract", default={}),
        control_plane_notes=_sequence(payload, "control_plane_notes", default=()),
        product_plane_notes=_sequence(payload, "product_plane_notes", default=()),
        target_readonly_by_default=bool(payload.get("target_readonly_by_default", True)),
        execution_policy=_mapping(payload, "execution_policy", default=_default_execution_policy()),
        operator_parity=_mapping(payload, "operator_parity", default={}),
    )


def load_target_project_configs(config_dir: Path) -> tuple[TargetProjectConfig, ...]:
    if not config_dir.exists():
        return ()
    configs = [load_target_project_config(path) for path in sorted(config_dir.glob("*.json"))]
    return tuple(configs)


def validate_target_project(config: TargetProjectConfig) -> TargetProjectValidationResult:
    source_mode = _normalize_source_mode(config.source_mode)
    repo = Path(config.repo_path).expanduser().resolve()
    repo_exists = repo.is_dir()
    warnings: list[str] = []
    blockers: list[str] = []
    is_git_repo = False
    remote_source_available = False
    managed_clone_ready = False
    current_branch: str | None = None
    head_commit: str | None = None
    dirty_state_summary: str | None = None

    if not config.target_readonly_by_default:
        warnings.append("target_readonly_by_default is false; MVP expects read-only target configs")
    if source_mode == "remote_managed_clone":
        if not config.repo_url:
            blockers.append("repo_url is required for remote_managed_clone source mode")
        else:
            remote = _git_ls_remote_head(config.repo_url, config.branch)
            if remote.returncode == 0 and remote.stdout.strip():
                remote_source_available = True
                managed_clone_ready = True
                is_git_repo = True
                current_branch = config.branch
                head_commit = remote.stdout.strip().split()[0]
            else:
                blockers.append(
                    "remote source unavailable: "
                    + (_command_output(remote) or f"{config.repo_url} branch {config.branch}")
                )
        if not repo_exists:
            warnings.append(f"local repo_path missing but not required in remote_managed_clone mode: {repo}")
        else:
            warnings.append("local repo_path exists but hosted execution will use remote managed clone source")

    if source_mode == "local_path" and not repo_exists:
        blockers.append(f"repo_path does not exist: {repo}")
    if repo_exists:
        top_level = _git(repo, "rev-parse", "--show-toplevel")
        if top_level.returncode == 0:
            is_git_repo = True
            actual_top = Path(top_level.stdout.strip()).resolve()
            if source_mode == "local_path" and actual_top != repo:
                blockers.append(f"repo_path must be git toplevel: expected {actual_top}, got {repo}")
            if source_mode == "local_path":
                current_branch = _git_text(repo, "branch", "--show-current") or None
                head_commit = _git_text(repo, "rev-parse", "HEAD") or None
                managed_clone_ready = True
            dirty_state_summary = _git_text(repo, "status", "--short") or None
            if dirty_state_summary:
                warnings.append("target repo has dirty state; validation remains read-only")
        else:
            if source_mode == "local_path":
                blockers.append(f"repo_path is not a git repo: {repo}")
            else:
                warnings.append(f"local repo_path is not a git repo and is ignored in remote_managed_clone mode: {repo}")

    found: list[str] = []
    missing: list[str] = []
    if repo_exists:
        for rel_path in config.source_of_truth_paths:
            candidate = _safe_target_path(repo, rel_path)
            if candidate.exists():
                found.append(_normalize_repo_path(rel_path))
            else:
                missing.append(_normalize_repo_path(rel_path))
        if missing:
            warnings.append(f"missing configured source paths: {', '.join(missing)}")
        if not found:
            blockers.append("no configured source_of_truth_paths were found")
    else:
        if source_mode == "remote_managed_clone" and remote_source_available:
            warnings.append("source_of_truth_paths will be verified inside the remote managed clone workspace")
        else:
            missing = [_normalize_repo_path(path) for path in config.source_of_truth_paths]

    status: TargetProjectStatus
    if blockers:
        status = "blocked"
    elif warnings:
        status = "warning"
    else:
        status = "valid"
    return TargetProjectValidationResult(
        status=status,
        project_id=config.project_id,
        repo_path=str(repo),
        source_mode=source_mode,
        repo_url=config.repo_url,
        branch=config.branch,
        repo_exists=repo_exists,
        is_git_repo=is_git_repo,
        remote_source_available=remote_source_available,
        managed_clone_ready=managed_clone_ready,
        current_branch=current_branch,
        head_commit=head_commit,
        dirty_state_summary=dirty_state_summary,
        source_of_truth_found=tuple(found),
        missing_source_paths=tuple(missing),
        warnings=tuple(warnings),
        blockers=tuple(blockers),
    )


def build_target_context_snapshot(
    config: TargetProjectConfig,
    *,
    max_bytes_per_file: int = DEFAULT_MAX_BYTES_PER_FILE,
) -> TargetContextSnapshot:
    validation = validate_target_project(config)
    if validation.status == "blocked":
        raise ControlPlaneValidationError(
            f"target project validation blocked: {'; '.join(validation.blockers)}"
        )
    repo = Path(validation.repo_path)
    files = _collect_source_files(repo, config.source_of_truth_paths)
    if not files:
        raise ControlPlaneValidationError("target context snapshot has no source files")
    source_files = [_read_source_file(repo, path, max_bytes_per_file=max_bytes_per_file) for path in files]
    summary = (
        f"{config.display_name}: read {len(source_files)} source file(s) from "
        f"{', '.join(validation.source_of_truth_found)}"
    )
    return TargetContextSnapshot(
        project_id=config.project_id,
        repo_path=str(repo),
        source_mode=validation.source_mode,
        repo_url=validation.repo_url,
        branch=validation.branch,
        head_commit=validation.head_commit,
        current_branch=validation.current_branch,
        source_files=tuple(source_files),
        source_summary=summary,
        forbidden_paths=config.default_forbidden_paths,
        forbidden_actions=config.default_forbidden_actions,
        required_smokes=config.default_required_smokes,
        created_at=_now_utc(),
    )


def build_target_context_summary(config: TargetProjectConfig) -> TargetContextSummary:
    validation = validate_target_project(config)
    workflow_notes = (*config.control_plane_notes, *config.product_plane_notes)
    return TargetContextSummary(
        project_id=config.project_id,
        display_name=config.display_name,
        repo_path=str(Path(config.repo_path).expanduser().resolve()),
        source_mode=validation.source_mode,
        repo_url=validation.repo_url,
        branch=validation.branch,
        remote_source_available=validation.remote_source_available,
        managed_clone_ready=validation.managed_clone_ready,
        validation_status=validation.status,
        current_branch=validation.current_branch,
        head_commit=validation.head_commit,
        source_of_truth_paths_found=validation.source_of_truth_found,
        missing_source_paths=validation.missing_source_paths,
        derived_secondary_paths=config.derived_secondary_paths,
        default_forbidden_paths=config.default_forbidden_paths,
        default_forbidden_actions=config.default_forbidden_actions,
        default_required_smokes=config.default_required_smokes,
        workflow_notes=workflow_notes,
        warnings=(*validation.warnings, *validation.blockers),
    )


def merge_target_defaults_into_task_spec(task_spec: TaskSpec, target_config: TargetProjectConfig) -> TaskSpec:
    from dataclasses import replace

    merged = replace(
        task_spec,
        required_smokes=_merge_unique((*task_spec.required_smokes, *target_config.default_required_smokes)),
        forbidden_paths=_merge_unique((*task_spec.forbidden_paths, *target_config.default_forbidden_paths)),
        forbidden_actions=_merge_unique((*task_spec.forbidden_actions, *target_config.default_forbidden_actions)),
    )
    validate_task_spec(merged, require_frozen=task_spec.status == "frozen")
    return merged


def merge_target_defaults_into_task_spec_payload(
    payload: Mapping[str, Any],
    target_config: TargetProjectConfig,
) -> dict[str, Any]:
    task_spec = task_spec_from_mapping(payload)
    merged_spec = merge_target_defaults_into_task_spec(task_spec, target_config)
    merged = _json_ready(dict(payload))
    merged.update(task_spec_to_dict(merged_spec))
    merged["target_project_id"] = target_config.project_id
    merged["target_project"] = target_project_defaults(target_config)
    if isinstance(payload.get("sprint_steps"), Sequence) and not isinstance(payload.get("sprint_steps"), (str, bytes)):
        merged["sprint_steps"] = [
            _merge_step_required_smokes(step, target_config.default_required_smokes)
            for step in payload["sprint_steps"]  # type: ignore[index]
        ]
    elif isinstance(payload.get("steps"), Sequence) and not isinstance(payload.get("steps"), (str, bytes)):
        merged["steps"] = [
            _merge_step_required_smokes(step, target_config.default_required_smokes)
            for step in payload["steps"]  # type: ignore[index]
        ]
    return merged


def target_project_defaults(config: TargetProjectConfig) -> dict[str, Any]:
    return {
        "project_id": config.project_id,
        "display_name": config.display_name,
        "repo_path": config.repo_path,
        "source_mode": _normalize_source_mode(config.source_mode),
        "repo_url": config.repo_url,
        "branch": config.branch,
        "source_of_truth_paths": list(config.source_of_truth_paths),
        "derived_secondary_paths": list(config.derived_secondary_paths),
        "default_forbidden_paths": list(config.default_forbidden_paths),
        "default_forbidden_actions": list(config.default_forbidden_actions),
        "default_required_smokes": list(config.default_required_smokes),
        "codex_prompt_contract": _json_ready(dict(config.codex_prompt_contract)),
        "control_plane_notes": list(config.control_plane_notes),
        "product_plane_notes": list(config.product_plane_notes),
        "target_readonly_by_default": config.target_readonly_by_default,
        "execution_policy": _json_ready(dict(config.execution_policy)),
    }


def target_project_config_to_dict(config: TargetProjectConfig) -> dict[str, Any]:
    return _json_ready(asdict(config))


def target_project_validation_result_to_dict(result: TargetProjectValidationResult) -> dict[str, Any]:
    return _json_ready(asdict(result))


def target_context_snapshot_to_dict(snapshot: TargetContextSnapshot) -> dict[str, Any]:
    return _json_ready(asdict(snapshot))


def target_context_summary_to_dict(summary: TargetContextSummary) -> dict[str, Any]:
    return _json_ready(asdict(summary))


def _collect_source_files(repo: Path, source_paths: Sequence[str]) -> tuple[Path, ...]:
    files: list[Path] = []
    for rel_path in source_paths:
        candidate = _safe_target_path(repo, rel_path)
        if candidate.is_file():
            files.append(candidate)
        elif candidate.is_dir():
            for path in sorted(candidate.rglob("*")):
                if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES:
                    files.append(path)
    unique = sorted({path.resolve() for path in files})
    return tuple(unique)


def _read_source_file(repo: Path, path: Path, *, max_bytes_per_file: int) -> dict[str, Any]:
    raw = path.read_bytes()
    truncated = len(raw) > max_bytes_per_file
    snippet = raw[:max_bytes_per_file].decode("utf-8", errors="replace")
    rel = path.resolve().relative_to(repo.resolve()).as_posix()
    return {
        "path": rel,
        "bytes_total": len(raw),
        "bytes_read": min(len(raw), max_bytes_per_file),
        "truncated": truncated,
        "content": snippet,
    }


def _merge_step_required_smokes(step: Any, required_smokes: Sequence[str]) -> Any:
    if not isinstance(step, Mapping):
        return step
    merged = _json_ready(dict(step))
    current = merged.get("required_smokes", [])
    if not isinstance(current, Sequence) or isinstance(current, (str, bytes)):
        current = []
    merged["required_smokes"] = list(_merge_unique((*current, *required_smokes)))
    return merged


def _safe_target_path(repo: Path, rel_path: str) -> Path:
    normalized = _normalize_repo_path(rel_path)
    candidate = (repo / normalized).resolve()
    try:
        candidate.relative_to(repo.resolve())
    except ValueError as exc:
        raise ControlPlaneValidationError(f"target path escapes repo: {rel_path}") from exc
    return candidate


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = _safe_git_env()
    return subprocess.run(("git", *args), cwd=cwd, capture_output=True, text=True, check=False, env=env)


def _git_text(cwd: Path, *args: str) -> str:
    result = _git(cwd, *args)
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _read_json(path: Path) -> Mapping[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ControlPlaneValidationError("target config JSON root must be an object")
    return payload


def _required_str(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ControlPlaneValidationError(f"{key} is required")
    return value.strip()


def _sequence(payload: Mapping[str, Any], key: str, default: Sequence[str] | None = None) -> tuple[str, ...]:
    value = payload.get(key, default)
    if value is None:
        raise ControlPlaneValidationError(f"{key} is required")
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ControlPlaneValidationError(f"{key} must be a list")
    return tuple(str(item) for item in value)


def _mapping(payload: Mapping[str, Any], key: str, default: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
    value = payload.get(key, default)
    if value is None:
        raise ControlPlaneValidationError(f"{key} is required")
    if not isinstance(value, Mapping):
        raise ControlPlaneValidationError(f"{key} must be an object")
    return value


def _optional_str(payload: Mapping[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ControlPlaneValidationError(f"{key} must be a string")
    text = value.strip()
    return text or None


def _default_execution_policy() -> dict[str, Any]:
    return {
        "default_mode": "fake",
        "allow_managed_clone_execution": False,
        "allow_direct_target_mutation": False,
        "allow_live_deploy": False,
        "allow_auto_merge": False,
        "require_explicit_real_codex_flag": True,
    }


def _to_tuple(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(str(value) for value in values)


def _merge_unique(values: Sequence[str]) -> tuple[str, ...]:
    merged: list[str] = []
    for value in values:
        item = str(value)
        if item not in merged:
            merged.append(item)
    return tuple(merged)


def _normalize_repo_path(path: Any) -> str:
    return str(path).strip().replace("\\", "/").lstrip("./")


def _normalize_source_mode(source_mode: str) -> str:
    mode = str(source_mode or "local_path").strip() or "local_path"
    if mode not in SOURCE_MODES:
        raise ControlPlaneValidationError(f"source_mode must be one of {sorted(SOURCE_MODES)}")
    return mode


def _git_ls_remote_head(repo_url: str, branch: str) -> subprocess.CompletedProcess[str]:
    env = _safe_git_env()
    command = ("git", "ls-remote", "--heads", repo_url, branch)
    try:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr_raw = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return subprocess.CompletedProcess(command, 124, stdout, stderr_raw or "git ls-remote timed out")


def _safe_git_env() -> dict[str, str]:
    env: dict[str, str] = {"GIT_TERMINAL_PROMPT": "0"}
    for key in ("PATH", "HOME", "LANG", "LC_ALL"):
        value = os.environ.get(key)
        if value:
            env[key] = value
    return env


def _command_output(result: subprocess.CompletedProcess[str]) -> str:
    return "\n".join(part for part in (result.stdout.strip(), result.stderr.strip()) if part)


def _now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _json_ready(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    return value
