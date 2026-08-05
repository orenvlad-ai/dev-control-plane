"""Independent, typed terminal-contour verification for Orchestrator v2.

Terminal evidence is an executor claim, not release truth.  This module binds a
fresh, independently observed proof to the exact terminal digest and revisions
before :class:`SupervisorEngine` is allowed to persist technical completion.

Only fixed argument-vector, read-only clients are provided here.  No caller
input becomes a shell command and provider output is never surfaced in an
exception, verification record, log, or persisted artifact.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import time
from typing import Any

from .orchestration_contracts import (
    DEV_CONTROL_PLANE_RELEASE_TARGET,
    TaskPassport,
    TerminalEvidence,
)
from .release_train import PullRequestTruth
from .supervisor import ContourVerification, terminal_contract_digest


DEV_CONTROL_PLANE_REPOSITORY = DEV_CONTROL_PLANE_RELEASE_TARGET
DEV_CONTROL_PLANE_TARGET = DEV_CONTROL_PLANE_REPOSITORY
DEV_CONTROL_PLANE_BASE = "main"
DEV_CONTROL_PLANE_REQUIRED_CHECKS = ("v2-suite", "self-closure")
HOSTED_TARGET = "wb-core-eu-root"
HOSTED_DOMAIN = "devcontrol.pro"
WEBCORE_URL = "https://api.selleros.pro"
PUBLIC_URL = "https://devcontrol.pro"

ROOT = Path(__file__).resolve().parents[2]
HOSTED_RUNNER = ROOT / "apps" / "dev_control_plane_hosted_deploy.py"

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_TARGET_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-/]{0,126}$")
_PR_IDENTITY_RE = re.compile(
    r"^github-pr-v1:"
    r"(?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+):"
    r"(?P<number>[1-9][0-9]{0,8}):"
    r"(?P<head>[0-9a-f]{40}):"
    r"(?P<merge>[0-9a-f]{40})$"
)
_DEPLOY_IDENTITY_RE = re.compile(
    r"^hosted-release-v1:"
    r"(?P<target>[A-Za-z0-9][A-Za-z0-9_.-]{0,63}):"
    r"(?P<domain>[A-Za-z0-9.-]{1,253}):"
    r"(?P<release>[0-9a-f]{40})$"
)
_MAX_PROVIDER_OUTPUT = 256_000
_MAX_GITHUB_FILE_OUTPUT = 32_000_000
_GITHUB_PR_FILE_LIMIT = 3_000


class ContourVerifierError(RuntimeError):
    """A controlled, sanitized independent-verification failure."""


@dataclass(frozen=True)
class ImmutablePullRequestIdentity:
    repository: str
    number: int
    head_sha: str
    merge_sha: str

    @classmethod
    def parse(cls, value: str) -> "ImmutablePullRequestIdentity":
        match = _PR_IDENTITY_RE.fullmatch(value) if isinstance(value, str) else None
        if match is None:
            raise ContourVerifierError("immutable PR identity is malformed")
        return cls(
            repository=match.group("repo"),
            number=int(match.group("number")),
            head_sha=match.group("head"),
            merge_sha=match.group("merge"),
        )

    def serialize(self) -> str:
        return f"github-pr-v1:{self.repository}:{self.number}:{self.head_sha}:{self.merge_sha}"


@dataclass(frozen=True)
class ImmutableHostedReleaseIdentity:
    target: str
    domain: str
    release_sha: str

    @classmethod
    def parse(cls, value: str) -> "ImmutableHostedReleaseIdentity":
        match = _DEPLOY_IDENTITY_RE.fullmatch(value) if isinstance(value, str) else None
        if match is None:
            raise ContourVerifierError("immutable hosted release identity is malformed")
        return cls(match.group("target"), match.group("domain"), match.group("release"))

    def serialize(self) -> str:
        return f"hosted-release-v1:{self.target}:{self.domain}:{self.release_sha}"


@dataclass(frozen=True)
class CommandOutcome:
    returncode: int
    stdout: str


CommandRunner = Callable[[tuple[str, ...], float], CommandOutcome]


@dataclass(frozen=True)
class HostedProjectionReadback:
    release_sha: str
    service_role: str
    control_authority: bool
    mutation_routes_enabled: bool
    projection_ingestion_enabled: bool
    tls_verified: bool
    auth_boundary_observed: bool
    webcore_independent: bool


@dataclass(frozen=True)
class IndependentContourProof:
    target: str
    task_id: str
    workstream_id: str
    task_revision: int
    workstream_revision: int
    contour: str
    terminal_digest: str
    source: str
    passed: bool
    checks: tuple[str, ...]
    evidence: tuple[str, ...]
    observed_at: str

    def __post_init__(self) -> None:
        if not _TARGET_RE.fullmatch(self.target):
            raise ContourVerifierError("contour proof target is invalid")
        if self.source not in {
            "github_release_train_readback",
            "diagnostic_verifier",
            "artifact_verifier",
        }:
            raise ContourVerifierError("contour proof source is not allowlisted")
        if self.contour not in {"release:done", "release:production", "diagnostic", "artifact"}:
            raise ContourVerifierError("contour proof kind is invalid")
        if not re.fullmatch(r"[0-9a-f]{64}", self.terminal_digest):
            raise ContourVerifierError("contour proof terminal digest is invalid")
        if self.passed is not True:
            raise ContourVerifierError("independent contour proof did not pass")
        if not self.checks or not self.evidence:
            raise ContourVerifierError("independent contour proof is incomplete")
        for values in (self.checks, self.evidence):
            if any(
                not isinstance(value, str)
                or not value
                or value != value.strip()
                or len(value) > 500
                for value in values
            ):
                raise ContourVerifierError("independent contour proof contains invalid text")
        _require_timestamp(self.observed_at)


ContourAdapter = Callable[[TaskPassport, TerminalEvidence], IndependentContourProof]


class ContourVerifier:
    """Exact ``(contour, target)`` registry used as Supervisor's callback."""

    def __init__(self) -> None:
        self._adapters: dict[tuple[str, str], ContourAdapter] = {}

    def register(self, *, contour: str, target: str, adapter: ContourAdapter) -> None:
        if contour not in {"release:done", "release:production", "diagnostic", "artifact"}:
            raise ContourVerifierError("cannot register an unknown contour")
        if not _TARGET_RE.fullmatch(target):
            raise ContourVerifierError("cannot register an invalid contour target")
        if not callable(adapter):
            raise ContourVerifierError("contour adapter must be callable")
        key = (contour, target)
        if key in self._adapters:
            raise ContourVerifierError("contour adapter is already registered")
        self._adapters[key] = adapter

    def __call__(self, passport: TaskPassport, terminal: TerminalEvidence) -> ContourVerification:
        digest = _validate_terminal_binding(passport, terminal)
        target = _target_from_contract(passport, terminal)
        adapter = self._adapters.get((passport.contour, target))
        if adapter is None:
            raise ContourVerifierError("no explicit verifier is registered for contour and target")
        proof = adapter(passport, terminal)
        if not isinstance(proof, IndependentContourProof):
            raise ContourVerifierError("registered verifier returned an untyped proof")
        expected = (
            target,
            terminal.task_id,
            terminal.workstream_id,
            terminal.task_revision,
            terminal.workstream_revision,
            terminal.closure_kind,
            digest,
        )
        observed = (
            proof.target,
            proof.task_id,
            proof.workstream_id,
            proof.task_revision,
            proof.workstream_revision,
            proof.contour,
            proof.terminal_digest,
        )
        if observed != expected:
            raise ContourVerifierError("registered verifier proof is stale or bound to another terminal")
        expected_source = {
            "release:done": "github_release_train_readback",
            "release:production": "github_release_train_readback",
            "diagnostic": "diagnostic_verifier",
            "artifact": "artifact_verifier",
        }[passport.contour]
        if proof.source != expected_source:
            raise ContourVerifierError("registered verifier returned the wrong proof source")
        verification_digest = _digest_json(
            {
                "target": target,
                "terminal_digest": digest,
                "source": proof.source,
                "checks": proof.checks,
                "evidence": proof.evidence,
                "observed_at": proof.observed_at,
            }
        )
        return ContourVerification(
            verification_id="contour-verification:" + verification_digest[:40],
            task_id=terminal.task_id,
            workstream_id=terminal.workstream_id,
            task_revision=terminal.task_revision,
            workstream_revision=terminal.workstream_revision,
            contour=terminal.closure_kind,
            terminal_digest=digest,
            source=proof.source,
            passed=True,
            checks=proof.checks,
            evidence=proof.evidence,
            verified_at=proof.observed_at,
        )


class AllowlistedGitHubReadback:
    """Read only the exact dev-control-plane PR and ``main`` identity via ``gh``."""

    _PR_FIELDS = (
        "number,state,isDraft,headRefName,headRefOid,baseRefName,mergeable,"
        "mergeStateStatus,statusCheckRollup,changedFiles,url,mergeCommit"
    )

    def __init__(
        self,
        *,
        repository: str = DEV_CONTROL_PLANE_REPOSITORY,
        gh_binary: str = "gh",
        command_runner: CommandRunner | None = None,
        timeout_seconds: float = 45.0,
    ) -> None:
        if repository != DEV_CONTROL_PLANE_REPOSITORY:
            raise ContourVerifierError("GitHub readback repository is not approved")
        if Path(gh_binary).name != "gh":
            raise ContourVerifierError("GitHub readback binary is not allowlisted")
        if timeout_seconds <= 0 or timeout_seconds > 120:
            raise ContourVerifierError("GitHub readback timeout is invalid")
        self.repository = repository
        self.gh_binary = gh_binary
        self.command_runner = command_runner or _subprocess_runner
        self.timeout_seconds = float(timeout_seconds)

    def read_pr(self, number: int) -> PullRequestTruth:
        if isinstance(number, bool) or not isinstance(number, int) or number < 1 or number > 999_999_999:
            raise ContourVerifierError("GitHub PR number is invalid")
        payload = self._run_json(
            (
                self.gh_binary,
                "pr",
                "view",
                str(number),
                "--repo",
                self.repository,
                "--json",
                self._PR_FIELDS,
            )
        )
        changed_files = _changed_file_count(payload)
        pages = self._run_json_value(
            (
                self.gh_binary,
                "api",
                "--paginate",
                "--slurp",
                f"/repos/{self.repository}/pulls/{number}/files?per_page=100",
            ),
            label="GitHub paginated PR file readback",
            max_output_bytes=_MAX_GITHUB_FILE_OUTPUT,
        )
        return _pull_request_truth(
            payload,
            files=_complete_file_readback(pages, changed_files),
        )

    def read_main_head(self) -> str:
        payload = self._run_json(
            (
                self.gh_binary,
                "api",
                f"repos/{self.repository}/git/ref/heads/{DEV_CONTROL_PLANE_BASE}",
            )
        )
        ref_object = payload.get("object")
        sha = ref_object.get("sha") if isinstance(ref_object, Mapping) else None
        if not isinstance(sha, str) or not _SHA_RE.fullmatch(sha):
            raise ContourVerifierError("GitHub main readback has no immutable SHA")
        return sha

    def require_ancestor(self, ancestor_sha: str, descendant_sha: str) -> None:
        if (
            not _SHA_RE.fullmatch(ancestor_sha)
            or not _SHA_RE.fullmatch(descendant_sha)
            or ancestor_sha == descendant_sha
        ):
            raise ContourVerifierError("GitHub compare identity is invalid")
        payload = self._run_json(
            (
                self.gh_binary,
                "api",
                f"/repos/{self.repository}/compare/{ancestor_sha}...{descendant_sha}",
                "--jq",
                "{status: .status, ahead_by: .ahead_by, merge_base_commit: {sha: .merge_base_commit.sha}}",
            )
        )
        merge_base = payload.get("merge_base_commit")
        merge_base_sha = merge_base.get("sha") if isinstance(merge_base, Mapping) else None
        ahead_by = payload.get("ahead_by")
        if (
            payload.get("status") != "ahead"
            or merge_base_sha != ancestor_sha
            or isinstance(ahead_by, bool)
            or not isinstance(ahead_by, int)
            or ahead_by < 1
        ):
            raise ContourVerifierError("GitHub compare did not prove ordered merge ancestry")

    def _run_json(self, argv: tuple[str, ...]) -> Mapping[str, Any]:
        payload = self._run_json_value(argv, label="GitHub readback")
        if not isinstance(payload, Mapping):
            raise ContourVerifierError("GitHub readback output is not an object")
        return payload

    def _run_json_value(
        self,
        argv: tuple[str, ...],
        *,
        label: str,
        max_output_bytes: int = _MAX_PROVIDER_OUTPUT,
    ) -> Any:
        outcome = self.command_runner(argv, self.timeout_seconds)
        if outcome.returncode != 0:
            raise ContourVerifierError("GitHub readback command failed")
        return _bounded_json_value(outcome.stdout, label, max_output_bytes=max_output_bytes)


class HostedDeployRunnerReadback:
    """Use only the hosted runner's three fixed, read-only probe commands."""

    def __init__(
        self,
        *,
        runner_path: Path = HOSTED_RUNNER,
        command_runner: CommandRunner | None = None,
        timeout_seconds: float = 60.0,
    ) -> None:
        resolved = runner_path.resolve()
        if resolved != HOSTED_RUNNER.resolve():
            raise ContourVerifierError("hosted readback runner path is not approved")
        if timeout_seconds <= 0 or timeout_seconds > 180:
            raise ContourVerifierError("hosted readback timeout is invalid")
        self.runner_path = resolved
        self.command_runner = command_runner or _subprocess_runner
        self.timeout_seconds = float(timeout_seconds)

    def readback(self, expected_release: str) -> HostedProjectionReadback:
        if not _SHA_RE.fullmatch(expected_release):
            raise ContourVerifierError("expected hosted release identity is invalid")
        loopback = self._run("loopback-probe")
        public = self._run("public-probe", "--url", PUBLIC_URL)
        webcore = self._run("webcore-probe", "--url", WEBCORE_URL)

        health = loopback.get("health")
        if (
            loopback.get("status") != "passed"
            or loopback.get("probe") != "loopback"
            or not isinstance(health, Mapping)
            or health.get("release_sha") != expected_release
            or health.get("service_role") != "hosted_projection_v2"
            or health.get("control_authority") is not False
            or health.get("mutation_routes_enabled") is not False
            or health.get("projection_ingestion_enabled") is not True
        ):
            raise ContourVerifierError("hosted loopback release readback did not match")
        if (
            public.get("status") != "passed"
            or public.get("probe") != "public"
            or public.get("url") != PUBLIC_URL
            or public.get("transport") != "ok"
            or public.get("http_status") not in {401, 403}
            or public.get("auth_boundary_observed") is not True
        ):
            raise ContourVerifierError("hosted TLS or Basic Auth readback did not pass")
        if (
            webcore.get("status") != "passed"
            or webcore.get("probe") != "webcore"
            or webcore.get("url") != WEBCORE_URL
            or webcore.get("transport") != "ok"
            or webcore.get("http_status") not in {200, 301, 302, 401, 403, 404}
        ):
            raise ContourVerifierError("WebCore independence readback did not pass")
        return HostedProjectionReadback(
            release_sha=expected_release,
            service_role="hosted_projection_v2",
            control_authority=False,
            mutation_routes_enabled=False,
            projection_ingestion_enabled=True,
            tls_verified=True,
            auth_boundary_observed=True,
            webcore_independent=True,
        )

    def _run(self, *arguments: str) -> Mapping[str, Any]:
        argv = (sys.executable, str(self.runner_path), *arguments)
        outcome = self.command_runner(argv, self.timeout_seconds)
        if outcome.returncode != 0:
            raise ContourVerifierError("hosted read-only probe command failed")
        return _bounded_json_object(outcome.stdout, "hosted readback")


class DevControlPlaneReleaseAdapter:
    """Independent release proof for the control plane's own governed lane."""

    def __init__(
        self,
        github: AllowlistedGitHubReadback,
        hosted: HostedDeployRunnerReadback,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.github = github
        self.hosted = hosted
        self.clock = clock

    def __call__(self, passport: TaskPassport, terminal: TerminalEvidence) -> IndependentContourProof:
        digest = _validate_terminal_binding(passport, terminal)
        _validate_release_manifest(passport, terminal)
        identities = tuple(ImmutablePullRequestIdentity.parse(item) for item in terminal.pr_identities)
        if not identities:
            raise ContourVerifierError("release contour has no immutable PR identity")
        if not passport.multi_pr_intent and len(identities) != 1:
            raise ContourVerifierError("single-PR Passport cannot close with multiple PR identities")
        if any(identity.repository != DEV_CONTROL_PLANE_REPOSITORY for identity in identities):
            raise ContourVerifierError("release identity names an unapproved repository")
        if len({identity.number for identity in identities}) != len(identities):
            raise ContourVerifierError("release identity contains a duplicate PR")
        if not passport.files:
            raise ContourVerifierError("release Passport has no exact declared files")

        checked_prs: list[ImmutablePullRequestIdentity] = []
        for identity in identities:
            truth = self.github.read_pr(identity.number)
            _verify_pull_request_truth(identity, truth, passport.files)
            checked_prs.append(identity)
        ancestry_evidence: list[str] = []
        for ancestor, descendant in zip(checked_prs, checked_prs[1:]):
            self.github.require_ancestor(ancestor.merge_sha, descendant.merge_sha)
            ancestry_evidence.append(f"github:ancestor:{ancestor.merge_sha}:{descendant.merge_sha}")
        main_sha = self.github.read_main_head()
        if main_sha != checked_prs[-1].merge_sha:
            raise ContourVerifierError("origin/main does not match the final immutable merge identity")

        checks = [
            "github_prs_merged",
            "v2_suite_success",
            "passport_diff_scope_matched",
            "origin_main_final_merge_matched",
        ]
        if len(checked_prs) > 1:
            checks.extend(("release_manifest_chain_matched", "github_merge_ancestry_verified"))
        evidence = [
            *(f"github:pr:{identity.number}:head:{identity.head_sha}:merge:{identity.merge_sha}" for identity in checked_prs),
            *ancestry_evidence,
            f"origin/main:{main_sha}",
        ]
        if passport.contour == "release:production":
            if len(terminal.deploy_identities) != 1:
                raise ContourVerifierError("production contour requires one exact hosted release identity")
            deployed = ImmutableHostedReleaseIdentity.parse(terminal.deploy_identities[0])
            if deployed.target != HOSTED_TARGET or deployed.domain != HOSTED_DOMAIN:
                raise ContourVerifierError("production identity names an unapproved hosted target")
            if deployed.release_sha != main_sha:
                raise ContourVerifierError("hosted identity does not match the final origin/main merge")
            hosted = self.hosted.readback(deployed.release_sha)
            if hosted.release_sha != main_sha:
                raise ContourVerifierError("hosted readback is stale")
            checks.extend(
                (
                    "hosted_release_identity_matched",
                    "hosted_projection_read_only",
                    "tls_and_basic_auth_verified",
                    "webcore_independence_verified",
                )
            )
            evidence.append(f"hosted:{HOSTED_TARGET}:{HOSTED_DOMAIN}:release:{hosted.release_sha}")
        elif terminal.deploy_identities:
            raise ContourVerifierError("release:done must not claim an unverified production deploy")

        return IndependentContourProof(
            target=DEV_CONTROL_PLANE_TARGET,
            task_id=terminal.task_id,
            workstream_id=terminal.workstream_id,
            task_revision=terminal.task_revision,
            workstream_revision=terminal.workstream_revision,
            contour=terminal.closure_kind,
            terminal_digest=digest,
            source="github_release_train_readback",
            passed=True,
            checks=tuple(checks),
            evidence=tuple(evidence),
            observed_at=_iso(self.clock()),
        )


def build_dev_control_plane_contour_verifier(
    *,
    github: AllowlistedGitHubReadback | None = None,
    hosted: HostedDeployRunnerReadback | None = None,
    clock: Callable[[], float] = time.time,
) -> ContourVerifier:
    """Build the production verifier with only the explicit self-release adapters."""

    release = DevControlPlaneReleaseAdapter(
        github or AllowlistedGitHubReadback(),
        hosted or HostedDeployRunnerReadback(),
        clock=clock,
    )
    verifier = ContourVerifier()
    verifier.register(contour="release:done", target=DEV_CONTROL_PLANE_TARGET, adapter=release)
    verifier.register(contour="release:production", target=DEV_CONTROL_PLANE_TARGET, adapter=release)
    return verifier


def _validate_terminal_binding(passport: TaskPassport, terminal: TerminalEvidence) -> str:
    if (
        terminal.task_id != passport.task_id
        or terminal.task_revision != passport.revision
        or terminal.closure_kind != passport.contour
    ):
        raise ContourVerifierError("terminal claim is stale or bound to another Passport")
    if terminal.owner_acceptance_required is not True:
        raise ContourVerifierError("terminal claim omitted explicit owner acceptance")
    return terminal_contract_digest(terminal)


def _validate_release_manifest(passport: TaskPassport, terminal: TerminalEvidence) -> None:
    manifest = passport.release_manifest
    if passport.multi_pr_intent and manifest is None:
        raise ContourVerifierError("multi-PR terminal closure requires a typed release manifest")
    if manifest is None:
        return
    if tuple(manifest.pr_identities) != tuple(terminal.pr_identities):
        raise ContourVerifierError("release manifest PR chain does not exactly match terminal order")
    if tuple(manifest.deploy_identities) != tuple(terminal.deploy_identities):
        raise ContourVerifierError("release manifest deploy chain does not exactly match terminal order")
    logical_lanes = tuple(
        item.removeprefix("release-lane:")
        for item in passport.resources
        if item.startswith("release-lane:")
    )
    if len(logical_lanes) != 1 or logical_lanes[0] != manifest.logical_lane_id:
        raise ContourVerifierError("release manifest logical lane does not match the Passport")


def _target_from_contract(passport: TaskPassport, terminal: TerminalEvidence) -> str:
    declared = tuple(item.removeprefix("target:") for item in passport.resources if item.startswith("target:"))
    if len(declared) > 1 or any(not _TARGET_RE.fullmatch(item) for item in declared):
        raise ContourVerifierError("Passport target resource is ambiguous or invalid")
    if passport.contour.startswith("release:"):
        identities = tuple(ImmutablePullRequestIdentity.parse(item) for item in terminal.pr_identities)
        repositories = {identity.repository for identity in identities}
        if len(repositories) != 1:
            raise ContourVerifierError("release contour does not identify exactly one target repository")
        target = next(iter(repositories))
        if declared and declared[0] != target:
            raise ContourVerifierError("Passport target resource contradicts the PR identity")
        return target
    verification_targets = tuple(
        item.removeprefix("verification-target:")
        for item in passport.resources
        if item.startswith("verification-target:")
    )
    if len(verification_targets) != 1 or not _TARGET_RE.fullmatch(verification_targets[0]):
        raise ContourVerifierError(
            "diagnostic/artifact Passport requires one verification-target resource"
        )
    return verification_targets[0]


def _verify_pull_request_truth(
    identity: ImmutablePullRequestIdentity,
    truth: PullRequestTruth,
    declared_files: Sequence[str],
) -> None:
    if truth.number != identity.number:
        raise ContourVerifierError("GitHub returned another PR")
    if truth.state != "MERGED" or truth.is_draft:
        raise ContourVerifierError("PR is not an immutable merged release")
    if truth.base_ref != DEV_CONTROL_PLANE_BASE:
        raise ContourVerifierError("PR base is not main")
    if truth.head_sha != identity.head_sha or truth.merge_commit_sha != identity.merge_sha:
        raise ContourVerifierError("PR head or merge identity changed")
    failed_checks = tuple(
        name
        for name in DEV_CONTROL_PLANE_REQUIRED_CHECKS
        if truth.checks.get(name) != "SUCCESS"
    )
    if failed_checks:
        raise ContourVerifierError("required self-release checks are not SUCCESS")
    actual = set(truth.files)
    declared = set(declared_files)
    if not actual:
        raise ContourVerifierError("merged PR diff is empty")
    if any(_unsafe_repo_path(path) for path in actual):
        raise ContourVerifierError("merged PR diff contains an unsafe path")
    if not actual.issubset(declared):
        raise ContourVerifierError("merged PR diff exceeds Passport file scope")


def _pull_request_truth(payload: Mapping[str, Any], *, files: Sequence[str]) -> PullRequestTruth:
    try:
        number = int(payload.get("number"))
    except (TypeError, ValueError) as exc:
        raise ContourVerifierError("GitHub PR readback is malformed") from exc
    rollup = payload.get("statusCheckRollup")
    if not isinstance(rollup, Sequence) or isinstance(rollup, (str, bytes, bytearray)):
        raise ContourVerifierError("GitHub check readback is malformed")
    checks: dict[str, str] = {}
    for item in rollup:
        if not isinstance(item, Mapping):
            raise ContourVerifierError("GitHub check readback is malformed")
        name = item.get("name") or item.get("context")
        conclusion = item.get("conclusion") or item.get("state")
        if isinstance(name, str) and isinstance(conclusion, str) and name:
            checks[name] = conclusion.upper()
    merge = payload.get("mergeCommit")
    merge_sha = merge.get("oid") if isinstance(merge, Mapping) else None
    head_sha = payload.get("headRefOid")
    if not isinstance(head_sha, str) or not _SHA_RE.fullmatch(head_sha):
        raise ContourVerifierError("GitHub PR head readback is malformed")
    if not isinstance(merge_sha, str) or not _SHA_RE.fullmatch(merge_sha):
        merge_sha = None
    return PullRequestTruth(
        number=number,
        state=str(payload.get("state") or "UNKNOWN").upper(),
        is_draft=payload.get("isDraft") is True,
        head_ref=str(payload.get("headRefName") or ""),
        head_sha=head_sha,
        base_ref=str(payload.get("baseRefName") or ""),
        mergeable=str(payload.get("mergeable") or "UNKNOWN").upper(),
        merge_state=str(payload.get("mergeStateStatus") or "UNKNOWN").upper(),
        url="",
        files=tuple(sorted(files)),
        checks=checks,
        merge_commit_sha=merge_sha,
    )


def _changed_file_count(payload: Mapping[str, Any]) -> int:
    changed_files = payload.get("changedFiles")
    if isinstance(changed_files, bool) or not isinstance(changed_files, int) or changed_files < 0:
        raise ContourVerifierError("GitHub changedFiles readback is malformed")
    if changed_files > _GITHUB_PR_FILE_LIMIT:
        raise ContourVerifierError("GitHub PR file count exceeds the complete readback limit")
    return changed_files


def _complete_file_readback(payload: Any, expected_count: int) -> tuple[str, ...]:
    if not isinstance(payload, Sequence) or isinstance(payload, (str, bytes, bytearray)):
        raise ContourVerifierError("GitHub paginated PR file readback is malformed")
    files: list[str] = []
    observed: set[str] = set()
    for page in payload:
        if not isinstance(page, Sequence) or isinstance(page, (str, bytes, bytearray)):
            raise ContourVerifierError("GitHub paginated PR file readback is malformed")
        for item in page:
            if not isinstance(item, Mapping):
                raise ContourVerifierError("GitHub paginated PR file readback is malformed")
            filename = item.get("filename")
            if not isinstance(filename, str) or not filename or "\x00" in filename:
                raise ContourVerifierError("GitHub PR filename readback is malformed")
            if filename in observed:
                raise ContourVerifierError("GitHub PR file readback contains a duplicate filename")
            observed.add(filename)
            files.append(filename)
            if len(files) > _GITHUB_PR_FILE_LIMIT:
                raise ContourVerifierError("GitHub PR file readback exceeds the provider limit")
    if len(files) != expected_count:
        raise ContourVerifierError("GitHub PR file readback is incomplete or count-mismatched")
    return tuple(files)


def _unsafe_repo_path(value: str) -> bool:
    if not isinstance(value, str) or not value or "\\" in value or value.startswith("/") or "\x00" in value:
        return True
    path = PurePosixPath(value)
    return not path.parts or any(part in {"", ".", ".."} for part in path.parts) or value.startswith(".git/")


def _bounded_json_object(raw: str, label: str) -> Mapping[str, Any]:
    payload = _bounded_json_value(raw, label, max_output_bytes=_MAX_PROVIDER_OUTPUT)
    if not isinstance(payload, Mapping):
        raise ContourVerifierError(f"{label} output is not an object")
    return payload


def _bounded_json_value(raw: str, label: str, *, max_output_bytes: int) -> Any:
    if not isinstance(raw, str):
        raise ContourVerifierError(f"{label} output is oversized")
    try:
        output_size = len(raw.encode("utf-8"))
    except UnicodeError as exc:
        raise ContourVerifierError(f"{label} output is invalid text") from exc
    if output_size > max_output_bytes:
        raise ContourVerifierError(f"{label} output is oversized")
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise ContourVerifierError(f"{label} output is invalid JSON") from exc
    return payload


def _subprocess_runner(argv: tuple[str, ...], timeout_seconds: float) -> CommandOutcome:
    try:
        completed = subprocess.run(
            list(argv),
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ContourVerifierError("independent readback command is unavailable") from exc
    stdout = completed.stdout
    if len(stdout.encode("utf-8")) > _MAX_PROVIDER_OUTPUT:
        raise ContourVerifierError("independent readback command output is oversized")
    return CommandOutcome(completed.returncode, stdout)


def _require_timestamp(value: str) -> None:
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except (TypeError, ValueError) as exc:
        raise ContourVerifierError("contour proof timestamp is invalid") from exc
    if parsed.tzinfo is None:
        raise ContourVerifierError("contour proof timestamp has no timezone")


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _digest_json(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
