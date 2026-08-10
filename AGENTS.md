# Repository rules

This repository is the authoritative DCP plan plus one bounded local
laboratory integration: the I12 automatic reviewer contour on the I11 durable
model-free task foundation and qualified I8 worker contour. Managed DCP
Orchestrator source retains the exact official Agent Orchestrator ancestry. It
is not a production control plane.

- The active source foundation is the private managed DCP Orchestrator
  repository at the exact commit pinned in `upstream/dcp-orchestrator.lock`.
  It preserves Agent Orchestrator `v0.12.1` history and the qualified I8
  behavior. I11 adds the approved durable SUBMITTED task/event foundation and
  removes normal manual Orchestrator affordances. I12 activates only the stock
  review engine's bounded automatic, exact-head, read-only reviewer path; keep
  the Electron UI, Go daemon, projects, sessions, worktrees and Codex adapters
  intact.
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
- The normal DCP adapter target is the disposable remote-free `dcp-lab`
  repository created beneath the lab root. The final I12 qualification may use
  only the disposable `orenvlad-ai/dcp-review-lab` repository for one fresh
  unmerged canary PR; its existing PRs #1/#2 and cards/runs are immutable audit
  evidence and must not be changed or reused. Every other real repository
  remains out of scope.
- The existing DCP daemon and its existing SQLite are the sole lab runtime and
  state authority. Do not add a second registry, database, daemon, scheduler,
  queue, watcher, reviewer service, arbiter, general retry/recovery policy,
  hosted API or production UI. I12 permits one event-driven stock reviewer
  launch for an eligible exact PR head plus one model-free stale-run recovery;
  it does not execute I11 SUBMITTED tasks or add a general model loop.
- The Codex reviewer model returns only one schema-constrained verdict artifact
  and receives no daemon/GitHub credentials, reviewer network tool or
  control-plane command. The trusted one-shot supervisor validates exact
  worker/reviewer/batch/run/PR/head identity and current terminal ownership,
  then persists once through the existing daemon and guarded `ReviewRun`
  transaction. Missing, ambiguous, malformed, foreign, duplicate, late or
  stale results fail closed without a verdict or retry; the compatibility
  `ao` alias is not the Codex success path.
- Final live qualification has a total budget of exactly one minimal worker
  model call for one new native card and exactly one automatic reviewer model
  call. There is no retry, second call, manual Run Review, second chat impulse
  or canary merge.
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
