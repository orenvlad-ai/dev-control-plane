# Repository rules

This repository is the authoritative DCP plan plus one bounded local
laboratory integration: DCP I3 on the official Agent Orchestrator source. It is
not a production control plane.

- The active foundation is the native Agent Orchestrator application at the
  exact release pinned in `upstream/agent-orchestrator.lock`. Keep its Electron
  UI, Go daemon, projects, sessions, worktrees and Codex adapter intact.
- The retired I2 Python/loopback slice is historical Git evidence only. Do not
  restore its launcher, registry, UI, supervisor or canary as an active path.
- Do not reactivate or copy the retired v1/v2 epoch. Use
  `archive/legacy-v1-v2-20260807` only as historical evidence.
- Keep the upstream source checkout, dependencies, builds, state, databases,
  logs, credentials, screenshots and canary repositories outside Git beneath
  an explicitly supplied `DCP_AO_LAB_ROOT`.
- Never run, inspect, migrate or import `/Applications/Agent Orchestrator.app`
  or its existing data. In particular, do not use upstream `ao start`; DCP uses
  the pinned source launcher and the source-built daemon/CLI only.
- Preserve the managed-source boundary: Git contains the pin, provenance,
  exact patch queue, launcher and adapter, but not a second copy of the
  upstream product. Updating upstream means a new reviewed pin and patch
  rebase, never a floating branch.
- The only DCP adapter target is the disposable remote-free `dcp-lab` repository
  created beneath the lab root. Real repositories remain out of scope.
- Do not add a DCP registry, database, daemon, scheduler, queue, retry/recovery
  policy, watcher, reviewer, arbiter, model loop, hosted API or production UI.
  Agent Orchestrator remains the sole lab runtime authority.
- Disable renderer and daemon telemetry with the supported AO environment
  switches for every DCP launch. Source/dev mode keeps the packaged updater
  inactive. Do not broaden this into an updater/telemetry refactor.
- Never synthesize owner acceptance. Only the owner may write
  `Задача принята`.

## Current development workflow

- The curator discusses and dispatches but does not change code. Only one DCP
  change task may be active.
- The executor works from current `origin/main` in a separate branch/worktree,
  runs relevant checks and a semantic self-review, and opens one ready PR.
- Use ordinary protected GitHub review, CI and merge. Never force-push or
  rewrite the archived epoch.
- After merge, fast-forward the clean canonical checkout and return a concise
  technical handoff. Technical completion is not owner acceptance.

Current scope is authoritative only in `docs/PROJECT_BRIEF.md`,
`docs/ROADMAP.md` and `docs/DECISIONS.md`.
