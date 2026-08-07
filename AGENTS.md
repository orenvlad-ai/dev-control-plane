# Repository rules

This repository contains the authoritative DCP plans and one intentionally
bounded local laboratory runtime: DCP Orchestrator I2. It is not a production
control plane.

- Do not reactivate or copy code from the retired v1/v2 epoch into the active
  tree. Use `archive/legacy-v1-v2-20260807` only as historical evidence.
- The only approved runtime is the fixed one-task `DCP_lab` canary described in
  `docs/PROJECT_BRIEF.md`: loopback UI, one in-process registry authority, one
  attempt, one ephemeral Codex CLI worker, deterministic evidence and cleanup.
- Do not generalize it into a scheduler, queue, retry/recovery system, watcher,
  reviewer loop, model loop, App Server integration, target adapter, hosted API
  or production UI unless a later task explicitly approves that scope.
- Keep runtime state, databases, logs, secrets, auth and TLS material outside
  Git. Never commit credentials or private archive contents.
- Do not discover, import or reuse installed Agent Orchestrator state. Preserve
  the DCP product, bundle, process, service, IPC, environment, state, cache and
  log namespaces and keep updater/telemetry/analytics/crash paths absent.
- Preserve repository history; use ordinary branches and pull requests. Do not
  force-push or rewrite the archived epoch.
- Treat target repositories as external and read-only unless their own current
  governed workflow explicitly authorizes a change.
- Prefer deterministic, model-free validation. Do not synthesize owner
  acceptance.
- DCP is the sole authority for laboratory runtime state. GitHub supplies only
  code/PR/CI/merge facts. Provider/history refs remain optional, default to
  `provider=none`, and never replace DCP state or retain a full transcript.

## Current development workflow

- The project curator is the discussion and dispatch boundary. The curator
  does not change code. After dispatch, the curator waits for a result or a
  question without polling or heartbeat traffic.
- In the curator task, the owner's natural command `запускай` means: create one
  separate, user-owned Codex executor task. Only one change task may be active
  at a time; there is no Release Train, task queue or parallel orchestration.
- The executor works in its own branch and worktree from current `origin/main`,
  runs relevant checks and a semantic self-review, opens a ready, non-draft
  pull request, and uses ordinary GitHub review, CI and merge flow.
- After merge, the executor returns a short technical handoff to the curator.
  Only the owner can accept the result by writing `Задача принята`; technical
  completion must never be presented as that acceptance.
- When Codex Desktop supports it, curator and executor tasks may receive short,
  linked titles and remain pinned. This is best-effort Desktop state, not a
  repository guarantee; only the owner unpins them.

The current scope is documented only in `docs/PROJECT_BRIEF.md`,
`docs/ROADMAP.md` and `docs/DECISIONS.md`.
