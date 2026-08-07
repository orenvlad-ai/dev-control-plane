# Project brief

## Purpose

Keep a governed DCP control-plane repository with the approved target
architecture, a small explicit change workflow and one bounded local
laboratory vertical slice.

## Current state

- This repository contains DCP Orchestrator I2: a dependency-free local
  loopback UI, a one-card in-process registry authority, one-attempt canary
  supervisor, isolated Codex CLI worker, deterministic evidence and cleanup.
- The slice is laboratory-only. There is no production deployment, hosted API,
  target adapter, queue, retry/recovery system, parallel orchestration,
  reviewer contour, arbiter or owner-acceptance automation.
- Agent Orchestrator revision `f17013b53a1752e86c66e87b45aaa4a463fdff62`
  is qualified and retained as architectural provenance. Its runtime source,
  binary and dependencies are not vendored or packaged in I2.
- The previous v1/v2 source lineage is recoverable from
  `archive/legacy-v1-v2-20260807` as historical evidence only. Nothing from it
  is an active architectural base.
- Sensitive local and hosted runtime evidence is retained only in private
  checksum archives. Runtime state, logs, credentials and test artifacts do not
  belong in Git.
- `devcontrol.pro` remains reserved; no replacement UI is deployed.

## Current development flow

The following governs repository changes now; the bounded I2 lab does not imply
that later target components already exist or are approved.

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

This remains a design target beyond the implemented one-worker laboratory
segment; it is not a description of deployed production components:

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

## Implemented first canary: `DCP_lab`

`DCP_lab` names the isolated local lab contour implemented by I2. The
repo-owned launcher creates its DCP-namespaced state roots and clean disposable
repository lazily on first operator run. Generated runtime data never enters
Git.

The canary validates only registry/UI → isolated dispatch → worker → evidence →
cleanup. It deliberately does not claim to validate the later independent
reviewer or GitHub/CI/merge portions of the target chain.

### Fixed test payload

- A dedicated disposable local Git repository is created for `DCP_lab` by the
  approved I2 runtime. Its canonical repository path, Git common directory and
  baseline commit are allowlisted before dispatch; it has no remotes. It is not
  `dev-control-plane`, `wb-core`, a production repository or any real target
  repository.
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

### Local operating path

On macOS, with Python 3.11+, Git and an authenticated `codex` CLI, the owner
opens the interface from a checkout with:

```sh
./bin/dcp-orchestrator
```

The server binds only to `127.0.0.1` on an ephemeral port, requires an
unpersisted per-process token for API calls and sends a same-origin-only CSP.
It accepts only the fixed synthetic prompt `Запусти изолированный DCP canary`.
The prompt is neither persisted nor forwarded as free-form worker authority.
Retained terminal/evidence records have no automatic upload or expiry; the I2
lab policy is local, indefinite retention until the owner deliberately removes
the DCP lab data root. The application has no deletion control.

The worker command is one `codex exec` child using an ephemeral session,
ignored user configuration, workspace-write sandbox, sanitized environment and
the disposable worktree as its only working directory. DCP retains no full
transcript. Provider communication by that existing CLI is the only external
provider trust boundary; the DCP application itself has no non-loopback
endpoint.

The DCP product identity is **DCP Orchestrator**, bundle ID
`pro.devcontrol.dcp-orchestrator`, process/IPC namespace `dcp-orchestrator` and
service identity `pro.devcontrol.dcp-orchestrator.lab`. The source launcher is
the supported I2 delivery; no signed/notarized macOS `.app` or production
installer is claimed.

### Provenance/history seam

DCP remains the sole source of runtime task, attempt, transition and evidence
state. GitHub remains the source of code, PR, CI and merge facts. Terminal
records include only nullable, provider-neutral `provider`, `session`,
`checkpoint`, `commit`, `digest` and `url` refs. The default is
`provider=none`; provider absence or failure cannot block a task. No full
transcript belongs in DCP history refs.

Entire is not installed, called or added as a runtime dependency in I2. A
future Entire canary must be private, explicitly owner-opted-in and separately
approved. It may write only bounded references and must prove that prompts,
transcripts, credentials and private code are not exported through the seam.

## Boundary

The active tree is documentation, model-free CI and the bounded I2 local lab
described above. Expansion into a full upstream source fork, signed desktop
bundle, retry/recovery supervisor, independent reviewer, target integration,
hosted API, production or rollout requires later explicit approval. Legacy
v1/v2 remains evidence only and must not be reactivated or copied.
