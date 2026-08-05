"""Mechanical GitHub release actuator for Supervisor-owned release lanes.

The module deliberately contains no scheduler or model policy.  It consumes an
already admitted, immutable release candidate, re-reads GitHub truth, and may
perform one compare-and-swap merge.  Deploy and verification remain explicit
registered callbacks owned by a target adapter; no web request can provide a
command line.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import json
from pathlib import Path
import re
import subprocess
from typing import Any


_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SAFE_CHECK_CONCLUSIONS = {"SUCCESS"}
_GITHUB_PR_FILE_LIMIT = 3_000
_MAX_GITHUB_FILE_OUTPUT_BYTES = 32_000_000


class ReleaseTrainError(RuntimeError):
    """Raised when immutable admission truth is stale or unsafe."""


@dataclass(frozen=True)
class ReleaseCandidate:
    lane_id: str
    task_id: str
    workstream_id: str
    revision: int
    repo: str
    pr_number: int
    expected_head_sha: str
    base_ref: str
    required_checks: tuple[str, ...]
    declared_files: tuple[str, ...]
    resources: tuple[str, ...]
    multi_pr: bool = False

    def __post_init__(self) -> None:
        if not self.lane_id or not self.task_id or not self.workstream_id:
            raise ValueError("lane/task/workstream identity is required")
        if self.revision < 1:
            raise ValueError("candidate revision must be positive")
        if not _REPO_RE.fullmatch(self.repo):
            raise ValueError("repo must be owner/name")
        if self.pr_number < 1:
            raise ValueError("pr_number must be positive")
        if not _SHA_RE.fullmatch(self.expected_head_sha):
            raise ValueError("expected_head_sha must be a full lowercase SHA")
        if not self.base_ref or self.base_ref.startswith("-"):
            raise ValueError("base_ref is invalid")
        object.__setattr__(self, "required_checks", _stable_tuple(self.required_checks))
        object.__setattr__(self, "declared_files", _stable_tuple(self.declared_files))
        object.__setattr__(self, "resources", _stable_tuple(self.resources))
        if not self.required_checks:
            raise ValueError("at least one required check is mandatory")
        if not self.declared_files:
            raise ValueError("Passport-declared files are mandatory")
        if not self.resources:
            raise ValueError("classified release resources are mandatory")


@dataclass(frozen=True)
class PullRequestTruth:
    number: int
    state: str
    is_draft: bool
    head_ref: str
    head_sha: str
    base_ref: str
    mergeable: str
    merge_state: str
    url: str
    files: tuple[str, ...]
    checks: Mapping[str, str]
    merge_commit_sha: str | None = None


@dataclass(frozen=True)
class ReleaseAdmission:
    allowed: bool
    blockers: tuple[str, ...]
    truth: PullRequestTruth


@dataclass(frozen=True)
class ReleaseResult:
    status: str
    candidate: ReleaseCandidate
    pr_url: str
    merge_commit_sha: str | None
    deployed_identity: str | None
    verification: Mapping[str, Any] | None
    executed_steps: tuple[str, ...]
    blockers: tuple[str, ...] = ()


class GitHubClient:
    """Small allowlisted `gh` adapter; inputs never become a shell command."""

    _PR_FIELDS = (
        "number,state,isDraft,headRefName,headRefOid,baseRefName,mergeable,"
        "mergeStateStatus,statusCheckRollup,changedFiles,url,mergeCommit"
    )

    def __init__(self, *, gh_binary: str = "gh", timeout_seconds: float = 45.0) -> None:
        self._gh_binary = gh_binary
        self._timeout_seconds = timeout_seconds

    def read_pr(self, *, repo: str, pr_number: int) -> PullRequestTruth:
        _validate_repo_and_pr(repo, pr_number)
        payload = self._run_json(
            ("pr", "view", str(pr_number), "--repo", repo, "--json", self._PR_FIELDS)
        )
        changed_files = _changed_file_count(payload)
        pages = self._run_json_value(
            (
                "api",
                "--paginate",
                "--slurp",
                f"/repos/{repo}/pulls/{pr_number}/files?per_page=100",
            ),
            max_output_bytes=_MAX_GITHUB_FILE_OUTPUT_BYTES,
        )
        files = _complete_file_readback(pages, changed_files)
        return _truth_from_payload(payload, files=files)

    def merge_pr(self, *, repo: str, pr_number: int, expected_head_sha: str) -> None:
        _validate_repo_and_pr(repo, pr_number)
        if not _SHA_RE.fullmatch(expected_head_sha):
            raise ReleaseTrainError("invalid expected head SHA")
        self._run(
            (
                "pr",
                "merge",
                str(pr_number),
                "--repo",
                repo,
                "--squash",
                "--delete-branch",
                "--match-head-commit",
                expected_head_sha,
            )
        )

    def _run_json(self, arguments: Sequence[str]) -> Mapping[str, Any]:
        payload = self._run_json_value(arguments)
        if not isinstance(payload, Mapping):
            raise ReleaseTrainError("GitHub returned a non-object payload")
        return payload

    def _run_json_value(
        self,
        arguments: Sequence[str],
        *,
        max_output_bytes: int = 1_000_000,
    ) -> Any:
        output = self._run(arguments)
        try:
            output_size = len(output.encode("utf-8"))
        except UnicodeError as exc:
            raise ReleaseTrainError("GitHub returned invalid text") from exc
        if output_size > max_output_bytes:
            raise ReleaseTrainError("GitHub returned an oversized payload")
        try:
            payload = json.loads(output)
        except (json.JSONDecodeError, UnicodeError) as exc:
            raise ReleaseTrainError("GitHub returned invalid JSON") from exc
        return payload

    def _run(self, arguments: Sequence[str]) -> str:
        try:
            completed = subprocess.run(
                [self._gh_binary, *arguments],
                check=False,
                capture_output=True,
                text=True,
                timeout=self._timeout_seconds,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ReleaseTrainError("GitHub command unavailable or timed out") from exc
        if completed.returncode != 0:
            # Provider output can contain sensitive headers or bodies; do not surface it.
            raise ReleaseTrainError(f"GitHub command failed with exit {completed.returncode}")
        return completed.stdout


class MechanicalReleaseTrain:
    """Execute a single immutable release lane after deterministic admission."""

    def __init__(
        self,
        github: GitHubClient,
        *,
        fence_guard: Callable[[str, ReleaseCandidate], None],
        deploy_adapters: Mapping[str, Callable[[ReleaseCandidate, str], str]] | None = None,
        deploy_readback_adapters: Mapping[
            str, Callable[[ReleaseCandidate, str], str | None]
        ] | None = None,
        verify_adapters: Mapping[str, Callable[[ReleaseCandidate, str], Mapping[str, Any]]] | None = None,
    ) -> None:
        if not callable(fence_guard):
            raise ValueError("a live Supervisor fence guard is required")
        self._github = github
        self._fence_guard = fence_guard
        self._deploy_adapters = dict(deploy_adapters or {})
        self._deploy_readback_adapters = dict(deploy_readback_adapters or {})
        self._verify_adapters = dict(verify_adapters or {})

    def admit(self, candidate: ReleaseCandidate) -> ReleaseAdmission:
        truth = self._github.read_pr(repo=candidate.repo, pr_number=candidate.pr_number)
        blockers: list[str] = []
        if truth.state not in {"OPEN", "MERGED"}:
            blockers.append(f"PR state is {truth.state}, expected OPEN or MERGED")
        if truth.is_draft:
            blockers.append("PR is draft")
        if truth.head_sha != candidate.expected_head_sha:
            blockers.append("PR head SHA changed")
        if truth.base_ref != candidate.base_ref:
            blockers.append("PR base branch changed")
        if truth.state == "OPEN":
            if truth.mergeable != "MERGEABLE":
                blockers.append(f"PR is not mergeable: {truth.mergeable}")
            if truth.merge_state not in {"CLEAN", "HAS_HOOKS", "UNSTABLE"}:
                blockers.append(f"PR merge state is not admitted: {truth.merge_state}")
        elif not truth.merge_commit_sha:
            blockers.append("merged PR has no immutable merge commit")
        for check_name in candidate.required_checks:
            conclusion = truth.checks.get(check_name)
            if conclusion not in _SAFE_CHECK_CONCLUSIONS:
                blockers.append(f"required check not green: {check_name}")
        actual_files = set(truth.files)
        declared_files = set(candidate.declared_files)
        if not actual_files:
            blockers.append("PR diff has no files")
        if declared_files and not actual_files.issubset(declared_files):
            blockers.append("Passport-vs-diff mismatch")
        if any(_unsafe_repo_path(path) for path in actual_files):
            blockers.append("PR contains unsafe or unclassified path")
        return ReleaseAdmission(not blockers, tuple(blockers), truth)

    def execute(self, candidate: ReleaseCandidate, *, target_adapter: str) -> ReleaseResult:
        self._fence_guard("before_github_readback", candidate)
        admission = self.admit(candidate)
        if not admission.allowed:
            return ReleaseResult(
                status="blocked",
                candidate=candidate,
                pr_url=admission.truth.url,
                merge_commit_sha=admission.truth.merge_commit_sha,
                deployed_identity=None,
                verification=None,
                executed_steps=("github_readback",),
                blockers=admission.blockers,
            )

        steps = ["github_readback"]
        truth = admission.truth
        if truth.state != "MERGED":
            self._fence_guard("before_github_merge", candidate)
            self._github.merge_pr(
                repo=candidate.repo,
                pr_number=candidate.pr_number,
                expected_head_sha=candidate.expected_head_sha,
            )
            steps.append("github_merge")
            self._fence_guard("after_github_merge", candidate)
            readback = self.admit(candidate)
            if not readback.allowed:
                raise ReleaseTrainError("merge readback failed immutable admission")
            truth = readback.truth
        if truth.state != "MERGED" or not truth.merge_commit_sha:
            raise ReleaseTrainError("merge readback did not prove MERGED state")
        steps.append("github_merge_readback")

        deploy = self._deploy_adapters.get(target_adapter)
        deploy_readback = self._deploy_readback_adapters.get(target_adapter)
        verify = self._verify_adapters.get(target_adapter)
        if deploy is None or deploy_readback is None or verify is None:
            raise ReleaseTrainError("registered deploy, deploy-readback and verify adapters are required")
        self._fence_guard("before_deploy_readback", candidate)
        deployed_identity = deploy_readback(candidate, truth.merge_commit_sha)
        steps.append("deploy_readback")
        if deployed_identity is None:
            self._fence_guard("before_deploy", candidate)
            deployed_identity = deploy(candidate, truth.merge_commit_sha)
            if not deployed_identity:
                raise ReleaseTrainError("deploy adapter returned no immutable identity")
            steps.append("deploy")
            self._fence_guard("after_deploy", candidate)
        self._fence_guard("before_verify", candidate)
        verification = verify(candidate, deployed_identity)
        if not isinstance(verification, Mapping) or verification.get("status") != "passed":
            raise ReleaseTrainError("independent production verification did not pass")
        self._fence_guard("after_verify", candidate)
        steps.append("verify")
        return ReleaseResult(
            status="passed",
            candidate=candidate,
            pr_url=truth.url,
            merge_commit_sha=truth.merge_commit_sha,
            deployed_identity=deployed_identity,
            verification=dict(verification),
            executed_steps=tuple(steps),
        )


def _truth_from_payload(payload: Mapping[str, Any], *, files: Sequence[str]) -> PullRequestTruth:
    checks: dict[str, str] = {}
    rollup = payload.get("statusCheckRollup")
    if isinstance(rollup, Sequence) and not isinstance(rollup, (str, bytes)):
        for item in rollup:
            if not isinstance(item, Mapping):
                continue
            name = str(item.get("name") or item.get("context") or "").strip()
            conclusion = str(item.get("conclusion") or item.get("state") or "").upper()
            if name:
                checks[name] = conclusion
    merge_commit = payload.get("mergeCommit")
    merge_sha = str(merge_commit.get("oid") or "") if isinstance(merge_commit, Mapping) else ""
    return PullRequestTruth(
        number=int(payload.get("number") or 0),
        state=str(payload.get("state") or "UNKNOWN").upper(),
        is_draft=bool(payload.get("isDraft")),
        head_ref=str(payload.get("headRefName") or ""),
        head_sha=str(payload.get("headRefOid") or ""),
        base_ref=str(payload.get("baseRefName") or ""),
        mergeable=str(payload.get("mergeable") or "UNKNOWN").upper(),
        merge_state=str(payload.get("mergeStateStatus") or "UNKNOWN").upper(),
        url=str(payload.get("url") or ""),
        files=tuple(sorted(files)),
        checks=checks,
        merge_commit_sha=merge_sha if _SHA_RE.fullmatch(merge_sha) else None,
    )


def _changed_file_count(payload: Mapping[str, Any]) -> int:
    changed_files = payload.get("changedFiles")
    if isinstance(changed_files, bool) or not isinstance(changed_files, int) or changed_files < 0:
        raise ReleaseTrainError("GitHub changedFiles readback is malformed")
    if changed_files > _GITHUB_PR_FILE_LIMIT:
        raise ReleaseTrainError("GitHub PR file count exceeds the complete readback limit")
    return changed_files


def _complete_file_readback(payload: Any, expected_count: int) -> tuple[str, ...]:
    if not isinstance(payload, Sequence) or isinstance(payload, (str, bytes, bytearray)):
        raise ReleaseTrainError("GitHub paginated PR file readback is malformed")
    files: list[str] = []
    observed: set[str] = set()
    for page in payload:
        if not isinstance(page, Sequence) or isinstance(page, (str, bytes, bytearray)):
            raise ReleaseTrainError("GitHub paginated PR file readback is malformed")
        for item in page:
            if not isinstance(item, Mapping):
                raise ReleaseTrainError("GitHub paginated PR file readback is malformed")
            filename = item.get("filename")
            if not isinstance(filename, str) or not filename or "\x00" in filename:
                raise ReleaseTrainError("GitHub PR filename readback is malformed")
            if filename in observed:
                raise ReleaseTrainError("GitHub PR file readback contains a duplicate filename")
            observed.add(filename)
            files.append(filename)
            if len(files) > _GITHUB_PR_FILE_LIMIT:
                raise ReleaseTrainError("GitHub PR file readback exceeds the provider limit")
    if len(files) != expected_count:
        raise ReleaseTrainError("GitHub PR file readback is incomplete or count-mismatched")
    return tuple(files)


def _validate_repo_and_pr(repo: str, pr_number: int) -> None:
    if not _REPO_RE.fullmatch(repo) or pr_number < 1:
        raise ReleaseTrainError("invalid GitHub repository or PR number")


def _stable_tuple(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))


def _unsafe_repo_path(path: str) -> bool:
    candidate = Path(path)
    return candidate.is_absolute() or ".." in candidate.parts or path.startswith(".git/")
