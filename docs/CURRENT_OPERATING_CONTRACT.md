# Current operating contract

operating_contract_revision: 2026-08-08.2

This is the compact operational start for DCP work. It does not replace the
architecture and scope in [Project brief](PROJECT_BRIEF.md),
[Roadmap](ROADMAP.md), or [Decisions](DECISIONS.md). If instructions conflict,
root `AGENTS.md` plus this contract determine how a new curator starts.

## Bootstrap and authority

Codex automatically receives `AGENTS.md` when a task starts in the correct
workspace; the user never has to say “read AGENTS.md”. The curator bootstrap is
one unambiguous chain:

1. local `DCP_curators/AGENTS.md` for curator-only dispatch rules;
2. repository root `AGENTS.md` for repository safety and workflow;
3. this current operating contract;
4. only the relevant authoritative scope documents linked above.

Do not reconstruct the operating state from old chat history. One primary
curator discusses scope and directly creates one executor in a separate Codex
worktree: no nested curator, no intermediate task, and no parallel DCP change.
The curator does not edit. The executor starts from exact current `origin/main`,
runs relevant tests and semantic review, and opens one ready PR. Ordinary
protected review, green CI, and safe merge apply. Technical completion and
owner acceptance are separate; only the owner may write `Задача принята`.
An already-running long-lived task does not hot-reload instructions: before
dispatch or mutation it rechecks exact current `origin/main` and this revision.
Any PR that changes runtime, flow, or boundary must synchronously update this contract
or explicitly prove that current operating state did not change.

## Exact laboratory contour

The active foundation is official Agent Orchestrator `v0.12.1` at commit
`1df40e93772c2c48e916870d9c3ddf8f29a69f84`, managed from the repository pin
and exact patch queue. The only runtime boundary is an explicitly supplied
absolute `DCP_AO_LAB_ROOT`; source, builds, state, logs, worktrees, Electron
`userData`, Codex worker state, evidence, and the remote-free synthetic
`dcp-lab` target stay below it.

The installed `/Applications/Agent Orchestrator.app`, `~/.ao`, real
repositories, `wb-core`, production, and hosted systems are never inputs. Do
not address Agent Orchestrator by application name or use GUI automation. Every
launch or check begins with `bin/dcp-ao preflight`, which must prove the exact
repo-owned launcher, pinned source checkout, source-built CLI/daemon,
`AO_DATA_DIR`, `AO_RUN_FILE`, Electron `userData`, lab-local
`CODEX_SQLITE_HOME`, Codex binary/config policy, and absence of the installed
app path. A failed or ambiguous preflight
stops the operation. If exact source-run UI addressing is unavailable, use the
repo-owned headless daemon plus exact CLI/session/tmux facts and leave only
manual visual comparison to the owner.

The Codex worker uses the existing standard Codex login with no credential copy
or global config change. The AO adapter invokes
`codex exec --ignore-user-config --ephemeral --strict-config`; invocation flags
disable hooks, apps, plugins, and multi-agent tools, so user MCP configuration
and plugin/app capabilities are not loaded. Preflight checks auth availability,
those effective feature states, and the supported exec flags; no hook-trust
bypass is allowed. The existing AO process supervisor supplies the lifecycle
facts for this exact one-shot worker: a successfully started process is active,
a zero exit status closes its launch generation and records idle, and launch
failure, non-zero exit, or signal records exited. No transcript, final-message,
or marker-content heuristic participates in that classification.

## Current stage and dispatch template

The current completed laboratory stage is I6: I5's clean isolated Codex worker
plus machine-outcome lifecycle classification, where a successful one-shot run
settles at Idle and an unsuccessful run remains Exited. Model-free outcome,
state-precedence and presentation coverage plus one cleaned real success canary
close the stage. The nearest allowed next step is separately governed
upstream-refresh maintenance; any control-contract expansion, real target, or
production work still needs explicit owner authorization.

A curator can dispatch without chat history using this checklist:

```text
Task: <one bounded DCP change>
Base: exact current origin/main; separate branch/worktree
Read: root AGENTS.md -> docs/CURRENT_OPERATING_CONTRACT.md -> only relevant authoritative docs
Boundary: exact DCP_AO_LAB_ROOT; never installed AO, ~/.ao, real repos, wb-core, production, or common-name GUI control
Flow: one primary curator -> one direct executor; no nested curator or parallel DCP change
Proof: exact-contour preflight, relevant tests, semantic self-review, one ready PR, green CI, safe merge, clean canonical fast-forward
Stop: fail closed on ambiguous contour, unsafe cleanup, or unsupported auth/isolation; never synthesize owner acceptance
```
