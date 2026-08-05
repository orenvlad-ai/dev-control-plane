"""Deterministic smoke coverage for the v2 mechanical Release Train."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (SRC, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dev_control_plane.release_train import (  # noqa: E402
    GitHubClient,
    MechanicalReleaseTrain,
    PullRequestTruth,
    ReleaseCandidate,
    ReleaseTrainError,
)


SHA = "a" * 40
MERGE_SHA = "b" * 40


class FakeGitHub:
    def __init__(self, truth: PullRequestTruth) -> None:
        self.truth = truth
        self.merges = 0

    def read_pr(self, *, repo: str, pr_number: int) -> PullRequestTruth:
        assert repo == "orenvlad-ai/dev-control-plane"
        assert pr_number == 42
        return self.truth

    def merge_pr(self, *, repo: str, pr_number: int, expected_head_sha: str) -> None:
        assert expected_head_sha == SHA
        self.merges += 1
        self.truth = replace(self.truth, state="MERGED", merge_commit_sha=MERGE_SHA)


class FixtureGitHubClient(GitHubClient):
    def __init__(self, metadata: dict[str, object], pages: object) -> None:
        super().__init__()
        self.metadata = metadata
        self.pages = pages
        self.calls: list[tuple[str, ...]] = []

    def _run(self, arguments: Sequence[str]) -> str:
        call = tuple(arguments)
        self.calls.append(call)
        if call[:2] == ("pr", "view"):
            return json.dumps(self.metadata, sort_keys=True)
        if call[:3] == ("api", "--paginate", "--slurp"):
            return json.dumps(self.pages, sort_keys=True)
        raise AssertionError(f"unexpected GitHub fixture command: {call}")


def main() -> None:
    _complete_file_readback_smoke()
    candidate = ReleaseCandidate(
        lane_id="lane-1",
        task_id="task-1",
        workstream_id="ws-1",
        revision=3,
        repo="orenvlad-ai/dev-control-plane",
        pr_number=42,
        expected_head_sha=SHA,
        base_ref="main",
        required_checks=("v2-suite",),
        declared_files=("src/dev_control_plane/example.py",),
        resources=("repo:dev-control-plane",),
    )
    truth = PullRequestTruth(
        number=42,
        state="OPEN",
        is_draft=False,
        head_ref="codex/orchestrator-v2",
        head_sha=SHA,
        base_ref="main",
        mergeable="MERGEABLE",
        merge_state="CLEAN",
        url="https://github.com/orenvlad-ai/dev-control-plane/pull/42",
        files=("src/dev_control_plane/example.py",),
        checks={"v2-suite": "SUCCESS"},
    )
    github = FakeGitHub(truth)
    deployed: list[str] = []
    guard_calls: list[str] = []

    def fence_guard(boundary: str, item: ReleaseCandidate) -> None:
        assert item == candidate
        guard_calls.append(boundary)

    def deploy(item: ReleaseCandidate, merge_sha: str) -> str:
        assert item == candidate and merge_sha == MERGE_SHA
        deployed.append(merge_sha)
        return f"dev-control-plane@{merge_sha}"

    def verify(item: ReleaseCandidate, identity: str) -> dict[str, str]:
        assert item == candidate and identity.endswith(MERGE_SHA)
        return {"status": "passed", "identity": identity}

    def deploy_readback(item: ReleaseCandidate, merge_sha: str) -> str | None:
        assert item == candidate and merge_sha == MERGE_SHA
        return f"dev-control-plane@{merge_sha}" if merge_sha in deployed else None

    train = MechanicalReleaseTrain(
        github,
        fence_guard=fence_guard,
        deploy_adapters={"hosted": deploy},
        deploy_readback_adapters={"hosted": deploy_readback},
        verify_adapters={"hosted": verify},
    )
    result = train.execute(candidate, target_adapter="hosted")
    assert result.status == "passed"
    assert "before_github_merge" in guard_calls
    assert "before_deploy" in guard_calls
    assert guard_calls[-1] == "after_verify"
    assert github.merges == 1 and deployed == [MERGE_SHA]
    assert result.executed_steps == (
        "github_readback",
        "github_merge",
        "github_merge_readback",
        "deploy_readback",
        "deploy",
        "verify",
    )

    # A repeated receipt is idempotent: GitHub is read back as merged and not merged twice.
    repeated = train.execute(candidate, target_adapter="hosted")
    assert repeated.status == "passed" and github.merges == 1 and deployed == [MERGE_SHA]
    assert repeated.executed_steps == (
        "github_readback",
        "github_merge_readback",
        "deploy_readback",
        "verify",
    )

    github.truth = replace(github.truth, state="OPEN", merge_commit_sha=None, head_sha="c" * 40)
    stale = train.execute(candidate, target_adapter="hosted")
    assert stale.status == "blocked" and "PR head SHA changed" in stale.blockers
    assert github.merges == 1

    github.truth = replace(
        truth,
        checks={"v2-suite": "FAILURE"},
        files=("src/dev_control_plane/unclassified.py",),
    )
    mismatch = train.admit(candidate)
    assert not mismatch.allowed
    assert "required check not green: v2-suite" in mismatch.blockers
    assert "Passport-vs-diff mismatch" in mismatch.blockers

    github.truth = replace(truth, checks={"v2-suite": "SKIPPED"})
    assert not train.admit(candidate).allowed

    # A generation that becomes stale at an external boundary cannot perform
    # the corresponding mutation, even though admission was previously green.
    fenced_github = FakeGitHub(truth)
    fenced_deploys: list[str] = []

    def stale_before_merge(boundary: str, _item: ReleaseCandidate) -> None:
        if boundary == "before_github_merge":
            raise ReleaseTrainError("stale Supervisor generation")

    fenced_train = MechanicalReleaseTrain(
        fenced_github,
        fence_guard=stale_before_merge,
        deploy_adapters={"hosted": lambda _item, sha: fenced_deploys.append(sha) or sha},
        deploy_readback_adapters={"hosted": lambda _item, _sha: None},
        verify_adapters={"hosted": lambda _item, identity: {"status": "passed", "identity": identity}},
    )
    try:
        fenced_train.execute(candidate, target_adapter="hosted")
    except ReleaseTrainError as exc:
        assert "stale" in str(exc)
    else:
        raise AssertionError("stale generation crossed the GitHub merge boundary")
    assert fenced_github.merges == 0 and not fenced_deploys
    print("release train v2 smoke: ok")


def _complete_file_readback_smoke() -> None:
    files = tuple(f"src/generated/file-{index:03d}.py" for index in range(101))
    client = FixtureGitHubClient(
        _provider_metadata(changed_files=len(files)),
        [
            [{"filename": path} for path in files[:100]],
            [{"filename": path} for path in files[100:]],
        ],
    )
    truth = client.read_pr(repo="orenvlad-ai/dev-control-plane", pr_number=42)
    assert truth.files == files
    assert client.calls == [
        (
            "pr",
            "view",
            "42",
            "--repo",
            "orenvlad-ai/dev-control-plane",
            "--json",
            GitHubClient._PR_FIELDS,
        ),
        (
            "api",
            "--paginate",
            "--slurp",
            "/repos/orenvlad-ai/dev-control-plane/pulls/42/files?per_page=100",
        ),
    ]

    truncated = FixtureGitHubClient(
        _provider_metadata(changed_files=101),
        [[{"filename": path} for path in files[:100]]],
    )
    _raises_release_train(truncated.read_pr, repo="orenvlad-ai/dev-control-plane", pr_number=42)

    duplicate = FixtureGitHubClient(
        _provider_metadata(changed_files=2),
        [[{"filename": "src/duplicate.py"}, {"filename": "src/duplicate.py"}]],
    )
    _raises_release_train(duplicate.read_pr, repo="orenvlad-ai/dev-control-plane", pr_number=42)

    over_limit = FixtureGitHubClient(_provider_metadata(changed_files=3_001), [])
    _raises_release_train(over_limit.read_pr, repo="orenvlad-ai/dev-control-plane", pr_number=42)
    assert len(over_limit.calls) == 1

    malformed_pages = FixtureGitHubClient(
        _provider_metadata(changed_files=1),
        [{"filename": "src/not-a-slurped-page.py"}],
    )
    _raises_release_train(malformed_pages.read_pr, repo="orenvlad-ai/dev-control-plane", pr_number=42)


def _provider_metadata(*, changed_files: int) -> dict[str, object]:
    return {
        "number": 42,
        "state": "OPEN",
        "isDraft": False,
        "headRefName": "codex/orchestrator-v2",
        "headRefOid": SHA,
        "baseRefName": "main",
        "mergeable": "MERGEABLE",
        "mergeStateStatus": "CLEAN",
        "statusCheckRollup": [{"name": "v2-suite", "conclusion": "SUCCESS"}],
        "changedFiles": changed_files,
        "url": "https://github.com/orenvlad-ai/dev-control-plane/pull/42",
        "mergeCommit": None,
    }


def _raises_release_train(function: object, **kwargs: object) -> None:
    try:
        function(**kwargs)  # type: ignore[operator]
    except ReleaseTrainError:
        return
    raise AssertionError("incomplete or malformed GitHub PR file readback was accepted")


if __name__ == "__main__":
    main()
