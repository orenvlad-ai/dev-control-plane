# Project brief

## Purpose

Keep a clean planning repository for the DCP control plane while recording the
first approved target architecture and a small, explicit workflow for changes
to this repository.

## Current state

- This repository has no active control-plane runtime, routes, build,
  deployment or product integration. It contains documentation and model-free
  CI only.
- No DCP Orchestrator application, supervisor, managed fork, reviewer contour
  or canary exists yet.
- The previous v1/v2 source lineage is recoverable from
  `archive/legacy-v1-v2-20260807` as historical evidence only. Nothing from it
  is an active architectural base.
- Sensitive local and hosted runtime evidence is retained only in private
  checksum archives. Runtime state, logs, credentials and test artifacts do not
  belong in Git.
- `devcontrol.pro` remains reserved; no replacement UI is deployed.

## Current development flow

The following governs repository changes now; it does not imply that the target
DCP Orchestrator already exists.

1. The owner discusses a change in the `dev-control-plane` curator task. The
   curator is the discussion and dispatch boundary and does not edit files.
2. The natural command `запускай` tells the curator to create one separate,
   user-owned Codex executor task. At most one change task may be active; this
   flow has no Release Train, task queue or parallel orchestration.
3. The executor starts from current `origin/main` in its own branch and
   worktree, changes only the approved scope, runs relevant checks and performs
   a semantic self-review.
4. The executor opens a ready, non-draft pull request. After the PR has been
   checked and required CI are green, it is merged through the ordinary
   protected GitHub flow and the feature branch is removed when safe.
5. The executor sends the curator a short technical handoff containing the PR,
   merge commit, material changes, checks and deliberate non-implementations.
   After dispatch, the curator does not poll or send heartbeats; it waits for
   that result or a blocking question.
6. Technical completion does not imply owner acceptance. The owner reviews the
   result and alone records acceptance with the exact phrase `Задача принята`.
   No system or other role may synthesize it.
7. Where Codex Desktop exposes supported task controls, curator and executor
   receive short linked titles and stay pinned. This is best-effort Desktop
   state rather than a repository capability; final unpinning is manual and
   belongs to the owner.

## Approved target architecture

This is a design target, not a description of deployed components:

> owner → curator → DCP Orchestrator → Codex executor in an isolated worktree
> → independent reviewer → GitHub/CI/merge → manual owner acceptance

The future **DCP Orchestrator** is based on a DCP-managed fork of
[Agent Orchestrator](https://github.com/Untrivial-ai/agent-orchestrator). It is
the authoritative task registry and operator monitoring surface for DCP runtime
state. A mechanical supervisor behind that surface applies deterministic state
transitions, retries, recovery, cleanup and invariant checks. The application
and supervisor do not replace model judgement, repository review, GitHub
protection or the owner's acceptance authority.

The target adopts selected state-management principles from
[OpenAI Symphony](https://github.com/openai/symphony), not its implementation:
one mutation authority, explicit attempt outcomes, idempotent dispatch checks,
reconciliation, bounded failure retries, restart recovery from authoritative
facts, isolated workspace containment and explicit cleanup. DCP does not import
Symphony code and does not run a separate Symphony service.

### Role and authority boundaries

- **Owner:** defines intent; authorizes material scope, implementation and
  deployment steps; resolves policy choices; and is the only actor that may
  record acceptance with `Задача принята`.
- **Curator:** discusses and sharpens the design, checks the dispatch boundary
  and dispatches the one approved change task. It does not modify files or
  supervise the executor with polling traffic.
- **DCP Orchestrator:** holds the canonical runtime record for tasks, attempts,
  evidence references and operator-visible states. It presents facts and
  authorized controls; it does not infer approval or acceptance.
- **Mechanical supervisor:** performs only specified, deterministic transitions,
  bounded retries, reconciliation, recovery, cleanup and invariant checks. An
  outcome needing semantic judgement is routed to a person or model-bearing
  role instead of being guessed.
- **Codex executor:** works in one isolated worktree and branch, with an explicit
  repository identity and scope allowlist. It produces a diff and evidence but
  cannot approve its own result or record owner acceptance.
- **Independent reviewer:** is separate from the executor and evaluates the
  diff, evidence, tests and risks. Its verdict is input to the GitHub flow, not
  owner acceptance.
- **GitHub/CI/merge:** supplies repository review, required checks, protection
  and merge facts. A merge is technical completion only.
- **Arbiter:** is invoked only for a genuinely ambiguous incident that the
  deterministic policy and ordinary review cannot resolve. It is not a
  permanent happy-path participant and cannot stand in for the owner.

The current one-change-at-a-time constraint remains in force until a later
owner-approved design explicitly changes it. The selected upstream's support
for parallel sessions is not permission to enable parallel DCP change tasks.

## First future canary: `DCP_lab`

`DCP_lab` names a future, isolated lab contour. This document defines its first
canary contract; it does not create the Project, application, runtime, state
root or test repository and does not run the canary.

The canary validates only registry/UI → isolated dispatch → worker → evidence →
cleanup. It deliberately does not claim to validate the later independent
reviewer or GitHub/CI/merge portions of the target chain.

### Fixed test payload

- A dedicated disposable local Git repository is created for `DCP_lab` by a
  separately approved future task. Its repository identity and baseline commit
  are allowlisted before dispatch. It is not `dev-control-plane`, `wb-core`, a
  production repository or any real target repository.
- DCP registers exactly one synthetic task, `dcp-lab-canary-001`, and the DCP
  application displays exactly one card for it.
- One Codex worker receives a separate worktree under the dedicated lab root.
  Its only file mutation is to create
  `canary/dcp-orchestrator-canary.txt` with the exact UTF-8 bytes
  `DCP isolated canary\n`. The marker remains uncommitted and is never pushed or
  merged.
- The supervisor records ordered state transitions and does not display
  `succeeded` until marker verification and cleanup have both passed. Other
  terminal outcomes include at least `failed`, `cleanup_failed` and
  `safety_violation`, each with a machine-readable reason.

### Observable success and evidence

All of the following are required for success:

1. A machine-readable registry snapshot and a UI capture show one task ID, one
   card, one attempt and one worker; no duplicate dispatch or retry exists.
2. The attempt record contains ordered transition sequence numbers, timestamps,
   terminal reason, retry count, executor identity and the allowlisted repository
   and baseline commit.
3. Before execution, path evidence proves that the worker `cwd` is the dedicated
   worktree, that its resolved path is inside the lab root and that its Git
   common directory belongs to the disposable test repository.
4. Marker evidence records the relative path, exact byte length, SHA-256 and a
   scoped status/diff proving there were no other mutations.
5. Cleanup evidence proves that the worker process/session has exited; transient
   locks, timers and attempt state are gone; the worktree and canary branch are
   removed; and the uncommitted marker disappeared with the worktree. The clean
   baseline test repository may be retained for later lab runs.
6. The immutable terminal task/event record and redacted evidence manifest are
   retained under the dedicated DCP lab data namespace according to an approved
   lab retention policy. They contain no credentials, prompts or private logs.
7. Negative path and repository-identity checks prove that the canary did not
   read from or write to `dev-control-plane`, `wb-core`, production, hosted
   systems or real target repositories.

The canary fails if any item is absent, if the card count differs from one, if
the marker bytes or mutation set differ, if a terminal status precedes cleanup,
if residue remains, or if a forbidden path/repository/system is contacted. A
safety-boundary violation stops the attempt and is not automatically retried.
Neither `succeeded` nor any other canary status means `Задача принята`.

## Boundary

The active tree remains documentation plus model-free CI. The managed fork,
application, supervisor, registry, state machine, reviewer integration,
`DCP_lab`, canary, hosted API, production integration and rollout all require
later gated tasks. Legacy v1/v2 remains evidence only and must not be
reactivated or copied.
