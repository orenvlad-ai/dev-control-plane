# Project brief

## Purpose

Keep the governed DCP architecture and one bounded local laboratory entrypoint
for handing a synthetic task from a normal curator task to native Agent
Orchestrator. This repository is not a production control plane.

## Current state

- Active foundation: official Agent Orchestrator stable release `v0.12.1`,
  commit `1df40e93772c2c48e916870d9c3ddf8f29a69f84`, managed outside Git from the
  exact repository pin and patch queue committed here.
- Preserved upstream runtime: Electron UI, Go loopback daemon, SQLite authority,
  projects, sessions, task prompts, tmux runtime, isolated Git worktrees and the
  native Codex adapter.
- Repo-owned surface: source verifier/launcher plus a single synchronous adapter
  that validates `dcp-lab` and invokes supported `ao project`/`ao spawn`
  commands. It owns no task state.
- Current I5 worker boundary: exact-contour preflight rejects the installed AO
  path, and the patched Codex adapter uses the supported ephemeral exec surface
  without user config, MCP, apps, plugins or hooks while retaining standard
  authentication.
- Current I6 lifecycle boundary: the existing AO process supervisor records
  one-shot Codex `Start` as active, a zero exit status as idle, and every
  unsuccessful machine outcome as exited. Closing the successful launch
  generation prevents stale workload-death reconciliation from reversing idle.
- Current I7 entry boundary: `bin/dcp-ao-submit` owns one singleton across exact
  UI/daemon proof and native submission. It reuses healthy UI-owned runtime,
  starts the source UI only from fully stopped or one known-safe stale state,
  and fails closed without process replacement for every foreign or ambiguous
  contour. Manual orchestrator-spawn affordances are hidden only in DCP Lab UI;
  upstream orchestration APIs remain available.
- Current curator start: root `AGENTS.md` routes directly to the compact,
  versioned `CURRENT_OPERATING_CONTRACT.md`; architecture remains here, in the
  roadmap and in decisions.
- I2's Python/loopback UI was owner-accepted as an experiment and is retired.
  Its launcher and runtime are absent from the active tree; Git history remains
  the evidence.
- v1/v2 remains frozen at `archive/legacy-v1-v2-20260807` and is not an active
  base.

## Development flow

1. The owner discusses a change with the curator; the curator does not edit.
2. `запускай` dispatches one separate executor task. Parallel DCP change tasks,
   queues and Release Train remain absent.
3. The executor starts from current `origin/main` in a separate branch/worktree,
   changes only the approved scope, verifies it and performs semantic review.
4. One ready PR uses ordinary protected review, green required CI and merge.
5. The executor fast-forwards the clean canonical checkout after merge and
   returns a technical handoff. Only the owner may record `Задача принята`.

## Implemented I3 laboratory boundary

### Managed upstream source

`upstream/agent-orchestrator.lock` pins repository, release, tag, commit, tree,
publication time, LICENSE digest, NOTICE result and patch digest. `bin/dcp-ao
prepare` creates a detached upstream checkout below the explicitly supplied
`DCP_AO_LAB_ROOT`, verifies every pinned fact, applies the exact patch and
refuses any other source diff or untracked file.

No upstream runtime source is copied into this repository. A future upstream
update is a deliberate lock change plus clean patch rebase, full qualification,
native build/run and canary. There is no floating branch and no second GitHub
repository.

### Isolation and network policy

The launcher sets explicit lab-local locations for AO's `running.json`, data
directory, SQLite database, worktrees and Electron `userData`. The exact
upstream patch queue adds an absolute `AO_ELECTRON_USER_DATA_DIR` override while
preserving upstream defaults when absent, and narrows the Codex worker launch.
Upstream Go/Vitest coverage for both patched boundaries is part of the queue.

Every launch sets `AO_TELEMETRY_RENDERER=off`, `AO_TELEMETRY_EVENTS=off`,
`AO_TELEMETRY_METRICS=off` and `AO_TELEMETRY_REMOTE=off`. Native source/dev mode
also sets the supported event-stream kill switch to `*` and keeps
`app.isPackaged=false`, so packaged updater initialization and relocation are
not reached. The application keeps the upstream name and UI; no installed Agent
Orchestrator app or state is an input.

### Curator gateway and adapter

`bin/dcp-ao-submit` accepts only:

- target name `dcp-lab`, resolved to the exact lab-owned repository path;
- a non-empty, one-line prompt of at most 512 UTF-8 bytes.

Before submission it proves the target is a clean Git root, contains its tracked
identity marker and has no remotes. One gateway singleton then covers contour
startup/proof, project registration/configuration and `ao spawn --harness
codex`. Healthy source-run UI plus app-owned daemon is submit-only and is never
restarted, even with active workers. Fully stopped starts exactly one canonical
source UI and waits for a shared dynamic instance identity, exact executable,
run-file, runtime environment and ready state. The sole recovery deletes one
complete dead app-owned stale run-file with exact port/socket identity. All
other state fails closed without kill, stop, restart or replacement.

The source-built official AO CLI and live daemon then register/verify the
project, set native project policy and invoke one worker session. Direct
launch/daemon/stop/restart is absent from curator and normal lab flow. There is
no second database, registry, daemon, scheduler, loop, retry or reverse-delivery
channel.

The worker command is
`codex exec --ignore-user-config --ephemeral --strict-config` with hooks, apps,
plugins and multi-agent features disabled. Its SQLite state is lab-local;
authentication remains the existing standard Codex login and is never copied.
The same AO supervisor that already fences each process generation maps its
exact process outcome: running to active, zero exit to idle, and launch failure,
non-zero exit or signal to exited. Successful idle cannot mask a sticky
waiting-input/blocked state, and existing PR/review/merge display precedence is
unchanged.

### Acceptance canary

The post-merge I7 canary is exactly one gateway invocation with a fixed safe
marker prompt and no pre-existing duplicate I7 session. Success requires all
of these observable facts:

1. Exact CLI/session facts show the separate `DCP Lab` project and one
   `DCP I7 Task` Codex worker session in the canonical source-run UI.
2. AO creates the session's isolated Git worktree and launches one Codex worker.
3. The worker creates only `dcp-ao-i7-marker.txt` with the requested UTF-8 line,
   without commit, push, PR or remote.
4. AO CLI/daemon facts expose a Working to Idle transition, while model-free
   process tests separately prove non-zero/signal/launch failure remain Exited.
5. The AO daemon runs with every supported telemetry switch off; Codex provider
   traffic remains a separate worker boundary.
6. The UI has no manual `Spawn Orchestrator` action or related hint, while
   model-free tests prove the existing orchestration function/API remains.
7. Worker terminal and new daemon output contain no Figma/MCP/OAuth startup or
   hook-trust warning. Minimal redacted facts are retained outside Git, then the
   disposable marker/worktree/repository artifacts are cleaned.

Neither an AO terminal status, merge nor technical handoff means owner
acceptance.

## Deliberate non-implementations

I7 does not add DCP roles, orchestrator/reviewer sessions, arbitration, queues,
retry/recovery policy, monitoring, Entire, Symphony runtime, reverse delivery,
App Server integration, hosted/server operation, a signed installer, a fork
repository, real targets, `wb-core`, `devcontrol.pro` or production rollout.
Upstream capabilities beyond the one synthetic session remain upstream
features, not authorization for DCP to exercise them.
