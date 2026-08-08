# Repository rules

This repository is the authoritative DCP plan plus one bounded local
laboratory integration: DCP I8 on managed DCP Orchestrator source that retains
the exact official Agent Orchestrator ancestry. It is not a production control
plane.

- The active source foundation is the private managed DCP Orchestrator
  repository at the exact commit pinned in `upstream/dcp-orchestrator.lock`.
  It preserves Agent Orchestrator `v0.12.1` history and the exact I8 behavior.
  Keep its Electron UI, Go daemon, projects, sessions, worktrees and Codex
  adapter intact.
- The retired I2 Python/loopback slice is historical Git evidence only. Do not
  restore its launcher, registry, UI, supervisor or canary as an active path.
- Do not reactivate or copy the retired v1/v2 epoch. Use
  `archive/legacy-v1-v2-20260807` only as historical evidence.
- Keep the managed fork checkout, dependencies, builds, state, databases,
  screenshots and canary repositories outside Git beneath the canonical,
  explicitly supplied `DCP_AO_LAB_ROOT` at
  `~/Library/Application Support/DCP Orchestrator`. Electron caches use
  `~/Library/Caches/pro.devcontrol.dcp-orchestrator` and logs use
  `~/Library/Logs/DCP Orchestrator`. Existing standard Codex
  authentication is the only external credential input; never copy or expose
  it, and never load the user's Codex configuration into a lab worker.
- Never run, inspect, migrate or import `/Applications/Agent Orchestrator.app`,
  `~/.ao`, or their data. Do not use upstream `ao start`. The only DCP Lab
  runtime is the locally installed exact bundle at
  `~/Applications/DCP Orchestrator.app`; pinned managed source is build/test
  input only and never the canonical runtime.
- Preserve the managed-source boundary: this repository contains the exact
  approved fork pin, provenance, launcher and adapter, but not a second copy of
  application code. The private `orenvlad-ai/dcp-orchestrator` repository owns
  application source; official upstream is a read-only reference there.
  Updating either source boundary requires a new reviewed immutable pin, never
  a floating branch.
- The only DCP adapter target is the disposable remote-free `dcp-lab` repository
  created beneath the lab root. Real repositories remain out of scope.
- Do not add a DCP registry, database, daemon, scheduler, queue, retry/recovery
  policy, watcher, reviewer, arbiter, model loop, hosted API or production UI.
  Agent Orchestrator remains the sole lab runtime authority.
- The DCP package has no updater initialization, feed, maker or publisher and
  packages no updater module. Renderer/daemon telemetry is hard-disabled in
  the patch as well as by environment; no telemetry key, host, installation
  identity, local reservoir or crash reporter is initialized by the package.
- The one-shot supervisor receives the exact DCP daemon connection only in its
  start/exit hook wrapper. The retained tmux shell and the Codex worker never
  inherit `AO_DATA_DIR` or `AO_RUN_FILE`; a successful supervised exit is
  recorded as Idle without weakening strict/ephemeral/ignore-user-config
  isolation.
- Never synthesize owner acceptance. Only the owner may write
  `Задача принята`.

## Current development workflow

Operational startup is authoritative in
`docs/CURRENT_OPERATING_CONTRACT.md`. A new curator reads this file, then that
contract, then only the relevant scope documents linked by the contract.

- The curator discusses and dispatches but does not change code. Only one DCP
  change task may be active.
- The executor works from current `origin/main` in a separate branch/worktree,
  runs relevant checks and a semantic self-review, and opens one ready PR.
- Use ordinary protected GitHub review, CI and merge. Never force-push or
  rewrite the archived epoch.
- After merge, fast-forward the clean canonical checkout and return a concise
  technical handoff. Technical completion is not owner acceptance.

Architecture and scope remain authoritative only in `docs/PROJECT_BRIEF.md`,
`docs/ROADMAP.md` and `docs/DECISIONS.md`. If operational instructions conflict,
this file plus `docs/CURRENT_OPERATING_CONTRACT.md` define the starting flow.
