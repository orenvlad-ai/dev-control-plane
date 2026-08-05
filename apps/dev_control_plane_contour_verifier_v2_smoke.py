"""Fake-only smoke for independent, typed v2 terminal-contour verification."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (SRC, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dev_control_plane.contour_verifier import (  # noqa: E402
    AllowlistedGitHubReadback,
    CommandOutcome,
    ContourVerifier,
    ContourVerifierError,
    DEV_CONTROL_PLANE_REPOSITORY,
    HOSTED_RUNNER,
    HostedDeployRunnerReadback,
    ImmutableHostedReleaseIdentity,
    ImmutablePullRequestIdentity,
    IndependentContourProof,
    build_dev_control_plane_contour_verifier,
)
from dev_control_plane.orchestration_contracts import (  # noqa: E402
    AutonomyEnvelope,
    CuratorIdentity,
    DEV_CONTROL_PLANE_RELEASE_TARGET,
    ExecutorIdentity,
    OrchestrationValidationError,
    ReleaseClosureManifest,
    TaskPassport,
    TerminalEvidence,
    Workstream,
)
from dev_control_plane.supervisor import SupervisorEngine, SupervisorError, terminal_contract_digest  # noqa: E402
from dev_control_plane.supervisor_registry import SupervisorRegistry  # noqa: E402


NOW = "2026-08-05T08:00:00Z"
CLOCK = 1_754_384_400.0
HEAD = "a" * 40
HEAD_TWO = "b" * 40
MERGE = "c" * 40
MERGE_TWO = "d" * 40
FILES = ("src/dev_control_plane/contour_verifier.py", "docs/architecture/03_orchestrator_v2.md")


class FakeReadbackProvider:
    def __init__(self) -> None:
        self.pr_files: dict[int, tuple[str, ...]] = {
            41: (FILES[0],),
            42: (FILES[1],),
        }
        self.prs: dict[int, dict[str, Any]] = {
            41: _pr_payload(41, HEAD, MERGE, self.pr_files[41]),
            42: _pr_payload(42, HEAD_TWO, MERGE_TWO, self.pr_files[42]),
        }
        self.pr_file_pages: dict[int, object] = {
            number: _file_pages(files) for number, files in self.pr_files.items()
        }
        self.main_sha = MERGE
        self.release_sha = MERGE
        self.compare_results: dict[tuple[str, str], dict[str, Any]] = {
            (MERGE, MERGE_TWO): {
                "status": "ahead",
                "ahead_by": 1,
                "merge_base_commit": {"sha": MERGE},
            }
        }
        self.public_auth = True
        self.webcore_ok = True
        self.calls: list[tuple[str, ...]] = []

    def run(self, argv: tuple[str, ...], _timeout: float) -> CommandOutcome:
        self.calls.append(argv)
        if argv[:3] == ("gh", "pr", "view"):
            return CommandOutcome(0, json.dumps(self.prs[int(argv[3])], sort_keys=True))
        if argv[:4] == ("gh", "api", "--paginate", "--slurp"):
            endpoint = argv[4]
            try:
                number = int(endpoint.split("/pulls/", 1)[1].split("/", 1)[0])
            except (IndexError, ValueError) as exc:
                raise AssertionError(f"unexpected PR files endpoint: {endpoint}") from exc
            return CommandOutcome(0, json.dumps(self.pr_file_pages[number], sort_keys=True))
        if argv[:2] == ("gh", "api") and "/compare/" in argv[2]:
            comparison = argv[2].split("/compare/", 1)[1]
            ancestor, descendant = comparison.split("...", 1)
            return CommandOutcome(
                0,
                json.dumps(self.compare_results[(ancestor, descendant)], sort_keys=True),
            )
        if argv[:2] == ("gh", "api"):
            return CommandOutcome(0, json.dumps({"object": {"sha": self.main_sha}}, sort_keys=True))
        if argv[:3] == (sys.executable, str(HOSTED_RUNNER.resolve()), "loopback-probe"):
            return CommandOutcome(0, json.dumps(_loopback_payload(self.release_sha), sort_keys=True))
        if argv[2:] == ("public-probe", "--url", "https://devcontrol.pro"):
            return CommandOutcome(0, json.dumps(_public_payload(self.public_auth), sort_keys=True))
        if argv[2:] == ("webcore-probe", "--url", "https://api.selleros.pro"):
            return CommandOutcome(0, json.dumps(_webcore_payload(self.webcore_ok), sort_keys=True))
        raise AssertionError(f"unexpected fake command: {argv}")


def main() -> None:
    assert DEV_CONTROL_PLANE_REPOSITORY == DEV_CONTROL_PLANE_RELEASE_TARGET
    _complete_file_readback_smoke()
    passport = _passport()
    terminal = _terminal(passport)

    provider = FakeReadbackProvider()
    verifier = _verifier(provider)
    verification = verifier(passport, terminal)
    assert verification.passed is True
    assert verification.source == "github_release_train_readback"
    assert verification.terminal_digest == terminal_contract_digest(terminal)
    assert "origin_main_final_merge_matched" in verification.checks
    assert "hosted_projection_read_only" in verification.checks
    assert provider.calls == _expected_commands(41, production=True)

    # The same verifier is the actual Supervisor callback: executor strings alone
    # cannot create a technical terminal event.
    integrated_provider = FakeReadbackProvider()
    with TemporaryDirectory(prefix="dev-control-plane-contour-verifier-") as raw:
        registry = SupervisorRegistry(Path(raw) / "supervisor.sqlite3")
        fence = registry.acquire_generation("contour-verifier-smoke-generation")
        engine = SupervisorEngine(
            registry,
            fence,
            supervisor_id="contour-verifier-smoke-supervisor",
            contour_verifier=_verifier(integrated_provider),
        )
        engine.register(passport, _workstream(passport), message_id="register-contour-smoke")
        forged_terminal = replace(
            terminal,
            terminal_id="terminal-forged-context",
            event_id="event-forged-context",
            pr_identities=(_pr_identity(41, "f" * 40, MERGE),),
            checks=("caller-context:passed",),
            evidence=(f"origin/main:{MERGE}", "probe:healthy", "caller-context:verified"),
        )
        try:
            engine.import_terminal(forged_terminal, message_id="terminal-forged-context")
        except (ContourVerifierError, SupervisorError):
            pass
        else:
            raise AssertionError("caller-supplied terminal context created a passed receipt")
        assert registry.get_event(forged_terminal.event_id) is None
        result = engine.import_terminal(terminal, message_id="terminal-contour-smoke")
        assert result["progress"] == 100 and result["verification_id"].startswith("contour-verification:")
        stored = registry.get_event(terminal.event_id)
        assert stored is not None
        assert stored["payload"]["independent_verification"]["terminal_digest"] == terminal_contract_digest(terminal)
        registry.release_generation(engine.fence)

    # The default clients use fixed argv with no shell and no mutating runner command.
    default_provider = FakeReadbackProvider()

    def fake_subprocess(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert kwargs.get("shell") in {None, False}
        assert kwargs["stdin"] is subprocess.DEVNULL
        assert kwargs["check"] is False
        outcome = default_provider.run(tuple(argv), float(kwargs["timeout"]))
        return subprocess.CompletedProcess(argv, outcome.returncode, outcome.stdout, "provider-secret-stderr")

    with patch("dev_control_plane.contour_verifier.subprocess.run", side_effect=fake_subprocess):
        default_verifier = build_dev_control_plane_contour_verifier(clock=lambda: CLOCK)
        assert default_verifier(passport, terminal).passed is True
    assert all("--live" not in call and "deploy" not in call[2:] and "rollback" not in call for call in default_provider.calls)

    # release:done proves GitHub/main only and cannot smuggle a production claim.
    done_passport = replace(
        passport,
        contour="release:done",
        autonomy=AutonomyEnvelope(
            allowed_actions=("github_readback", "self_merge", "target_lane_release"),
            prohibited_actions=("self_hosted_deploy", "wb_github_command"),
        ),
        release_manifest=ReleaseClosureManifest(
            logical_lane_id="dev-control-plane",
            pr_identities=(_pr_identity(41, HEAD, MERGE),),
            deploy_identities=(),
            finalized_at=NOW,
        ),
    )
    done_terminal = replace(
        terminal,
        terminal_id="terminal-release-done",
        event_id="event-release-done",
        closure_kind="release:done",
        deploy_identities=(),
    )
    done_provider = FakeReadbackProvider()
    assert _verifier(done_provider)(done_passport, done_terminal).passed is True
    assert done_provider.calls == _expected_commands(41, production=False)

    # A declared multi-PR lane validates every immutable PR and binds main to the last merge.
    multi_manifest = ReleaseClosureManifest(
        logical_lane_id="dev-control-plane",
        pr_identities=(
            _pr_identity(41, HEAD, MERGE),
            _pr_identity(42, HEAD_TWO, MERGE_TWO),
        ),
        deploy_identities=(_deploy_identity(MERGE_TWO),),
        finalized_at=NOW,
    )
    multi_passport = replace(
        passport,
        multi_pr_intent=True,
        release_manifest=multi_manifest,
    )
    multi_terminal = replace(
        terminal,
        terminal_id="terminal-multi-pr",
        event_id="event-multi-pr",
        pr_identities=(
            _pr_identity(41, HEAD, MERGE),
            _pr_identity(42, HEAD_TWO, MERGE_TWO),
        ),
        deploy_identities=(_deploy_identity(MERGE_TWO),),
        evidence=(f"origin/main:{MERGE_TWO}", "probe:healthy"),
    )
    multi_provider = FakeReadbackProvider()
    multi_provider.main_sha = MERGE_TWO
    multi_provider.release_sha = MERGE_TWO
    multi_proof = _verifier(multi_provider)(multi_passport, multi_terminal)
    assert multi_proof.passed is True
    assert "github_merge_ancestry_verified" in multi_proof.checks
    assert (
        "gh",
        "api",
        f"/repos/{DEV_CONTROL_PLANE_REPOSITORY}/compare/{MERGE}...{MERGE_TWO}",
        "--jq",
        "{status: .status, ahead_by: .ahead_by, merge_base_commit: {sha: .merge_base_commit.sha}}",
    ) in multi_provider.calls

    missing_manifest = replace(passport, multi_pr_intent=True, release_manifest=None)
    _reject(_verifier(FakeReadbackProvider()), missing_manifest, multi_terminal)

    reordered_manifest = replace(
        multi_manifest,
        pr_identities=tuple(reversed(multi_manifest.pr_identities)),
    )
    _reject(
        _verifier(FakeReadbackProvider()),
        replace(multi_passport, release_manifest=reordered_manifest),
        multi_terminal,
    )

    incomplete_terminal = replace(
        multi_terminal,
        terminal_id="terminal-multi-pr-incomplete-manifest",
        event_id="event-multi-pr-incomplete-manifest",
        pr_identities=(
            *multi_terminal.pr_identities,
            _pr_identity(43, "e" * 40, "f" * 40),
        ),
    )
    _reject(_verifier(FakeReadbackProvider()), multi_passport, incomplete_terminal)

    wrong_lane_manifest = replace(multi_manifest, logical_lane_id="other-release-lane")
    try:
        replace(multi_passport, release_manifest=wrong_lane_manifest)
    except OrchestrationValidationError:
        pass
    else:
        raise AssertionError("manifest lane mismatch crossed the Passport constructor")

    nonancestor_provider = FakeReadbackProvider()
    nonancestor_provider.main_sha = MERGE_TWO
    nonancestor_provider.release_sha = MERGE_TWO
    nonancestor_provider.compare_results[(MERGE, MERGE_TWO)] = {
        "status": "diverged",
        "ahead_by": 1,
        "merge_base_commit": {"sha": "0" * 40},
    }
    _reject(_verifier(nonancestor_provider), multi_passport, multi_terminal)

    # Forgery and immutable readback mismatches all fail closed.
    _reject(verifier, passport, replace(terminal, pr_identities=(terminal.pr_identities[0] + ";touch",)))
    _reject(verifier, passport, replace(terminal, task_revision=2))
    _reject(verifier, passport, replace(terminal, pr_identities=(_pr_identity(41, "f" * 40, MERGE),)))
    _reject(verifier, passport, replace(terminal, deploy_identities=(_deploy_identity("f" * 40),)))

    check_provider = FakeReadbackProvider()
    check_provider.prs[41]["statusCheckRollup"] = [
        {"name": "v2-suite", "conclusion": "FAILURE"},
        {"name": "self-closure", "conclusion": "SUCCESS"},
    ]
    _reject(_verifier(check_provider), passport, terminal)

    missing_self_closure = FakeReadbackProvider()
    missing_self_closure.prs[41]["statusCheckRollup"] = [
        {"name": "v2-suite", "conclusion": "SUCCESS"}
    ]
    _reject(_verifier(missing_self_closure), passport, terminal)

    failed_self_closure = FakeReadbackProvider()
    failed_self_closure.prs[41]["statusCheckRollup"] = [
        {"name": "v2-suite", "conclusion": "SUCCESS"},
        {"name": "self-closure", "conclusion": "FAILURE"},
    ]
    _reject(_verifier(failed_self_closure), passport, terminal)

    scope_provider = FakeReadbackProvider()
    scope_provider.pr_file_pages[41] = [[{"filename": "outside/passport.py"}]]
    _reject(_verifier(scope_provider), passport, terminal)

    base_provider = FakeReadbackProvider()
    base_provider.prs[41]["baseRefName"] = "release"
    _reject(_verifier(base_provider), passport, terminal)

    main_provider = FakeReadbackProvider()
    main_provider.main_sha = "f" * 40
    _reject(_verifier(main_provider), passport, terminal)

    probe_provider = FakeReadbackProvider()
    probe_provider.release_sha = "f" * 40
    _reject(_verifier(probe_provider), passport, terminal)

    tls_provider = FakeReadbackProvider()
    tls_provider.public_auth = False
    _reject(_verifier(tls_provider), passport, terminal)

    webcore_provider = FakeReadbackProvider()
    webcore_provider.webcore_ok = False
    _reject(_verifier(webcore_provider), passport, terminal)

    # Provider bodies and stderr never leak from controlled failure messages.
    failing_github = AllowlistedGitHubReadback(
        command_runner=lambda _argv, _timeout: CommandOutcome(9, "Authorization: should-not-leak")
    )
    try:
        failing_github.read_pr(41)
    except ContourVerifierError as exc:
        assert "Authorization" not in str(exc) and "should-not-leak" not in str(exc)
    else:
        raise AssertionError("failed provider command was accepted")

    # Diagnostic and artifact contours have no default. Each exact target needs a typed callback.
    diagnostic_passport, diagnostic_terminal = _non_release_contracts("diagnostic", "diagnostic-fixture")
    empty_registry = ContourVerifier()
    _reject(empty_registry, diagnostic_passport, diagnostic_terminal)
    diagnostic_registry = ContourVerifier()
    diagnostic_registry.register(
        contour="diagnostic",
        target="diagnostic-fixture",
        adapter=lambda p, t: _registered_proof(p, t, "diagnostic-fixture", "diagnostic_verifier"),
    )
    assert diagnostic_registry(diagnostic_passport, diagnostic_terminal).passed is True

    stale_registry = ContourVerifier()
    stale_registry.register(
        contour="diagnostic",
        target="diagnostic-fixture",
        adapter=lambda p, t: replace(
            _registered_proof(p, t, "diagnostic-fixture", "diagnostic_verifier"),
            terminal_digest="0" * 64,
        ),
    )
    _reject(stale_registry, diagnostic_passport, diagnostic_terminal)

    artifact_passport, artifact_terminal = _non_release_contracts("artifact", "artifact-fixture")
    artifact_registry = ContourVerifier()
    artifact_registry.register(
        contour="artifact",
        target="artifact-fixture",
        adapter=lambda p, t: _registered_proof(p, t, "artifact-fixture", "artifact_verifier"),
    )
    assert artifact_registry(artifact_passport, artifact_terminal).source == "artifact_verifier"

    # Production CLI no longer accepts a caller-supplied verification file.
    runtime_source = (ROOT / "apps" / "dev_control_plane_supervisor_v2.py").read_text(encoding="utf-8")
    assert "--verification" not in runtime_source
    assert "contour_verification_from_mapping" not in runtime_source
    assert "contour_verifier = build_dev_control_plane_contour_verifier()" in runtime_source
    assert "contour_verifier=contour_verifier," in runtime_source

    payload = {
        "status": "passed",
        "checks": 31,
        "real_network_calls": 0,
        "mutating_commands": 0,
        "terminal_digest": verification.terminal_digest,
        "release_identity": MERGE,
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _verifier(provider: FakeReadbackProvider) -> ContourVerifier:
    return build_dev_control_plane_contour_verifier(
        github=AllowlistedGitHubReadback(command_runner=provider.run),
        hosted=HostedDeployRunnerReadback(command_runner=provider.run),
        clock=lambda: CLOCK,
    )


def _passport() -> TaskPassport:
    return TaskPassport(
        task_id="task-contour-release",
        revision=1,
        title="Независимая проверка production-контура",
        objective="Доказать релиз без доверия к terminal-строкам исполнителя.",
        expected_result="GitHub, origin/main и hosted projection независимо совпадают.",
        contour="release:production",
        included_scope=("standalone control plane",),
        excluded_scope=("target product business code",),
        constraints=("read-only verification",),
        acceptance=("v2-suite SUCCESS", "hosted projection healthy"),
        closure=("owner acceptance remains explicit",),
        autonomy=AutonomyEnvelope(
            allowed_actions=(
                "github_readback",
                "hosted_readback",
                "self_merge",
                "self_hosted_deploy",
                "target_lane_release",
            ),
            prohibited_actions=("wb_github_command",),
        ),
        workstream_ids=("workstream-contour-release",),
        release_manifest=ReleaseClosureManifest(
            logical_lane_id="dev-control-plane",
            pr_identities=(_pr_identity(41, HEAD, MERGE),),
            deploy_identities=(_deploy_identity(MERGE),),
            finalized_at=NOW,
        ),
        resources=(
            f"target:{DEV_CONTROL_PLANE_REPOSITORY}",
            "release-lane:dev-control-plane",
            "repo:dev-control-plane",
        ),
        modules=("module:orchestrator-v2",),
        files=FILES,
        dependencies=(),
        multi_pr_intent=False,
        multi_deploy_intent=False,
        curator=CuratorIdentity("curator-thread-contour", "desktop-host-contour"),
        executor=ExecutorIdentity(
            "executor-thread-contour",
            "desktop-host-contour",
            "gpt-5.6-sol",
            "ultra",
        ),
        created_at=NOW,
    )


def _terminal(passport: TaskPassport) -> TerminalEvidence:
    assert passport.executor is not None
    return TerminalEvidence(
        terminal_id="terminal-contour-production",
        event_id="event-contour-production",
        task_id=passport.task_id,
        task_revision=passport.revision,
        workstream_id="workstream-contour-release",
        workstream_revision=1,
        executor_generation=1,
        executor=passport.executor,
        closure_kind=passport.contour,
        summary_ru="Исполнитель заявил production closure; verifier проверит его независимо.",
        evidence=(f"origin/main:{MERGE}", "probe:healthy"),
        checks=("executor-suite:passed",),
        pr_identities=(_pr_identity(41, HEAD, MERGE),),
        deploy_identities=(_deploy_identity(MERGE),),
        owner_acceptance_required=True,
        created_at=NOW,
    )


def _workstream(passport: TaskPassport) -> Workstream:
    return Workstream(
        workstream_id="workstream-contour-release",
        task_id=passport.task_id,
        revision=1,
        generation=1,
        root_workstream_id="workstream-contour-release",
        corrective_of_generation=None,
        title=passport.title,
        objective=passport.objective,
        state="started",
        executor=passport.executor,
        resources=passport.resources,
        dependencies=(),
        created_at=NOW,
    )


def _non_release_contracts(contour: str, target: str) -> tuple[TaskPassport, TerminalEvidence]:
    passport = replace(
        _passport(),
        task_id=f"task-{contour}",
        contour=contour,
        autonomy=AutonomyEnvelope(
            allowed_actions=("github_readback",),
            prohibited_actions=("target_release_command",),
        ),
        release_manifest=None,
        resources=(f"verification-target:{target}", "module:contour-fixture"),
        files=(),
    )
    assert passport.executor is not None
    terminal = replace(
        _terminal(passport),
        terminal_id=f"terminal-{contour}",
        event_id=f"event-{contour}",
        task_id=passport.task_id,
        closure_kind=contour,
        evidence=(f"{contour}:immutable-fixture",),
        pr_identities=(),
        deploy_identities=(),
    )
    return passport, terminal


def _registered_proof(
    passport: TaskPassport,
    terminal: TerminalEvidence,
    target: str,
    source: str,
) -> IndependentContourProof:
    return IndependentContourProof(
        target=target,
        task_id=terminal.task_id,
        workstream_id=terminal.workstream_id,
        task_revision=terminal.task_revision,
        workstream_revision=terminal.workstream_revision,
        contour=terminal.closure_kind,
        terminal_digest=terminal_contract_digest(terminal),
        source=source,
        passed=True,
        checks=(f"{passport.contour}_callback_passed",),
        evidence=(f"{passport.contour}:immutable-callback-proof",),
        observed_at=NOW,
    )


def _pr_payload(number: int, head: str, merge: str, files: tuple[str, ...]) -> dict[str, Any]:
    return {
        "number": number,
        "state": "MERGED",
        "isDraft": False,
        "headRefName": f"codex/contour-{number}",
        "headRefOid": head,
        "baseRefName": "main",
        "mergeable": "UNKNOWN",
        "mergeStateStatus": "CLEAN",
        "statusCheckRollup": [
            {"name": "v2-suite", "conclusion": "SUCCESS"},
            {"name": "self-closure", "conclusion": "SUCCESS"},
        ],
        "changedFiles": len(files),
        "url": f"https://github.com/{DEV_CONTROL_PLANE_REPOSITORY}/pull/{number}",
        "mergeCommit": {"oid": merge},
    }


def _file_pages(files: tuple[str, ...]) -> list[list[dict[str, str]]]:
    return [
        [{"filename": path} for path in files[offset : offset + 100]]
        for offset in range(0, len(files), 100)
    ] or [[]]


def _loopback_payload(release: str) -> dict[str, Any]:
    return {
        "status": "passed",
        "probe": "loopback",
        "health": {
            "service_role": "hosted_projection_v2",
            "control_authority": False,
            "mutation_routes_enabled": False,
            "projection_ingestion_enabled": True,
            "release_sha": release,
        },
    }


def _public_payload(passed: bool) -> dict[str, Any]:
    return {
        "status": "passed" if passed else "failed",
        "probe": "public",
        "url": "https://devcontrol.pro",
        "http_status": 401 if passed else 0,
        "transport": "ok" if passed else "tls_failed",
        "auth_boundary_observed": passed,
    }


def _webcore_payload(passed: bool) -> dict[str, Any]:
    return {
        "status": "passed" if passed else "failed",
        "probe": "webcore",
        "url": "https://api.selleros.pro",
        "http_status": 200 if passed else 0,
        "transport": "ok" if passed else "failed",
    }


def _pr_identity(number: int, head: str, merge: str) -> str:
    return ImmutablePullRequestIdentity(DEV_CONTROL_PLANE_REPOSITORY, number, head, merge).serialize()


def _deploy_identity(release: str) -> str:
    return ImmutableHostedReleaseIdentity("wb-core-eu-root", "devcontrol.pro", release).serialize()


def _expected_commands(number: int, *, production: bool) -> list[tuple[str, ...]]:
    result = [
        (
            "gh",
            "pr",
            "view",
            str(number),
            "--repo",
            DEV_CONTROL_PLANE_REPOSITORY,
            "--json",
            AllowlistedGitHubReadback._PR_FIELDS,
        ),
        (
            "gh",
            "api",
            "--paginate",
            "--slurp",
            f"/repos/{DEV_CONTROL_PLANE_REPOSITORY}/pulls/{number}/files?per_page=100",
        ),
        ("gh", "api", f"repos/{DEV_CONTROL_PLANE_REPOSITORY}/git/ref/heads/main"),
    ]
    if production:
        result.extend(
            (
                (sys.executable, str(HOSTED_RUNNER.resolve()), "loopback-probe"),
                (sys.executable, str(HOSTED_RUNNER.resolve()), "public-probe", "--url", "https://devcontrol.pro"),
                (sys.executable, str(HOSTED_RUNNER.resolve()), "webcore-probe", "--url", "https://api.selleros.pro"),
            )
        )
    return result


def _reject(verifier: Any, passport: TaskPassport, terminal: TerminalEvidence) -> None:
    try:
        verifier(passport, terminal)
    except ContourVerifierError:
        return
    raise AssertionError("forged, stale, or mismatched contour proof was accepted")


def _complete_file_readback_smoke() -> None:
    files = tuple(f"src/generated/contour-{index:03d}.py" for index in range(101))
    provider = FakeReadbackProvider()
    provider.prs[41] = _pr_payload(41, HEAD, MERGE, files)
    provider.pr_file_pages[41] = _file_pages(files)
    truth = AllowlistedGitHubReadback(command_runner=provider.run).read_pr(41)
    assert truth.files == files
    assert provider.calls == _expected_commands(41, production=False)[:2]

    truncated = FakeReadbackProvider()
    truncated.prs[41] = _pr_payload(41, HEAD, MERGE, files)
    truncated.pr_file_pages[41] = _file_pages(files[:100])
    _reject_read_pr(truncated)

    duplicate = FakeReadbackProvider()
    duplicate_files = ("src/duplicate.py", "src/other.py")
    duplicate.prs[41] = _pr_payload(41, HEAD, MERGE, duplicate_files)
    duplicate.pr_file_pages[41] = [[
        {"filename": "src/duplicate.py"},
        {"filename": "src/duplicate.py"},
    ]]
    _reject_read_pr(duplicate)

    over_limit = FakeReadbackProvider()
    over_limit.prs[41]["changedFiles"] = 3_001
    _reject_read_pr(over_limit)
    assert len(over_limit.calls) == 1

    malformed = FakeReadbackProvider()
    malformed.pr_file_pages[41] = [{"filename": FILES[0]}]
    _reject_read_pr(malformed)


def _reject_read_pr(provider: FakeReadbackProvider) -> None:
    try:
        AllowlistedGitHubReadback(command_runner=provider.run).read_pr(41)
    except ContourVerifierError:
        return
    raise AssertionError("incomplete or malformed contour PR file readback was accepted")


if __name__ == "__main__":
    main()
