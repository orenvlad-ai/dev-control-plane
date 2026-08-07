# Decisions

## 2026-08-07 — retire the legacy epoch

- v1/v2 is frozen at `archive/legacy-v1-v2-20260807`; history is preserved
  without rewrite.
- Legacy modules, imports, routes, workflows and deployment code are absent
  from the active tree.
- The old hosted projection is retired. Its runtime and TLS evidence remain
  recoverable, while `devcontrol.pro` stays reserved.

## 2026-08-07 — leave a planning surface

- This repository contains documentation and model-free CI only.
- No Agent Orchestrator or other control-plane implementation is selected or
  imported by this reset.
- Architecture and implementation require a new owner-approved task.
- Technical completion and owner acceptance remain separate states.

## 2026-08-07 — use one simple repository-change flow

- The curator owns discussion and dispatch, does not edit code, and waits
  without polling after dispatch.
- The owner's natural command `запускай` dispatches one separate, user-owned
  Codex executor task. Only one change task may be active at a time; no Release
  Train, task queue or parallel orchestration is introduced.
- The executor uses a separate branch/worktree, relevant checks, semantic
  self-review and an ordinary ready, non-draft PR with review, green CI and
  safe merge. It then returns a concise technical handoff to the curator.
- Supported Codex Desktop title and pin controls are best-effort task metadata,
  not repository automation. The owner manually unpins tasks.
- Only the owner's exact phrase `Задача принята` records acceptance. A merge or
  technical handoff does not, and agents must not synthesize that decision.

## 2026-08-07 — reserve an isolated future orchestrator lab

- `dev-control-plane` remains the single source of truth.
- `Лаборатория оркестратора` may later be created manually as a separate
  ChatGPT/Codex Project and isolated runtime/state space for synthetic tests.
- The lab is neither the repository's development workflow nor a connection to
  `wb-core`, target repositories or production.
- No lab Project, runtime, integration or deployment is created by this
  decision; each experiment needs separate approval.
