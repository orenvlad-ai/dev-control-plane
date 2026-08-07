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
directory, SQLite database, worktrees and Electron `userData`. The only upstream
patch adds an absolute `AO_ELECTRON_USER_DATA_DIR` override while preserving
upstream defaults when absent; its upstream Vitest coverage is part of the
patch.

Every launch sets `AO_TELEMETRY_RENDERER=off`, `AO_TELEMETRY_EVENTS=off`,
`AO_TELEMETRY_METRICS=off` and `AO_TELEMETRY_REMOTE=off`. Native source/dev mode
also sets the supported event-stream kill switch to `*` and keeps
`app.isPackaged=false`, so packaged updater initialization and relocation are
not reached. The application keeps the upstream name and UI; no installed Agent
Orchestrator app or state is an input.

### Curator adapter

`bin/dcp-ao-submit` accepts only:

- target name `dcp-lab`, resolved to the exact lab-owned repository path;
- a non-empty, one-line prompt of at most 512 UTF-8 bytes.

Before submission it proves the target is a clean Git root, contains its tracked
identity marker and has no remotes. It then uses the source-built official AO
CLI and live daemon to register/verify the project, set native project policy
and invoke one worker session with `ao spawn --harness codex`. There is no
second database, registry, daemon, scheduler, loop, retry or reverse-delivery
channel.

### Acceptance canary

The manual I3 canary is exactly one adapter invocation with a fixed safe marker
prompt. Success requires all of these observable facts:

1. Native UI shows the separate `DCP Lab` project and one `DCP I3 Canary`
   Codex worker session.
2. AO creates the session's isolated Git worktree and launches one Codex worker.
3. The worker creates only `dcp-ao-i3-marker.txt` with the requested UTF-8 line,
   without commit, push, PR or remote.
4. AO UI/terminal exposes the worker status and result.
5. AO Electron/daemon processes make no telemetry connection during the canary;
   Codex provider traffic is a separate worker boundary.
6. Minimal screenshots and redacted process/network facts are retained outside
   Git, then the disposable marker/worktree/repository artifacts are cleaned.

Neither an AO terminal status, merge nor technical handoff means owner
acceptance.

## Deliberate non-implementations

I3 does not add DCP roles, orchestrator/reviewer sessions, arbitration, queues,
retry/recovery policy, monitoring, Entire, Symphony runtime, reverse delivery,
App Server integration, hosted/server operation, a signed installer, a fork
repository, real targets, `wb-core`, `devcontrol.pro` or production rollout.
Upstream capabilities beyond the one synthetic session remain upstream
features, not authorization for DCP to exercise them.
