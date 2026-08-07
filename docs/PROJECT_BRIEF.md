# Project brief

## Purpose

Keep a clean repository where the owner can later design a development control
plane from first principles, while using a small, explicit workflow for changes
to this repository.

## Current state

- No active runtime, routes, build, deployment or product integration exists in
  the repository.
- The previous v1/v2 source lineage is recoverable from
  `archive/legacy-v1-v2-20260807`.
- Sensitive local and hosted runtime evidence is retained only in private
  checksum archives.
- `devcontrol.pro` remains reserved; no replacement UI is deployed.

## Current development flow

1. The user discusses a change in the `dev-control-plane` curator task. The
   curator is the discussion and dispatch boundary and does not edit code.
2. The natural command `запускай` tells the curator to create one separate,
   user-owned Codex executor task. At most one change task may be active; this
   flow has no Release Train, task queue or parallel orchestration.
3. The executor starts from current `origin/main` in its own branch and
   worktree, changes only the approved scope, runs relevant checks and performs
   a semantic self-review.
4. The executor opens a ready, non-draft pull request. After the PR has been
   checked and CI is green, it is merged by an ordinary safe GitHub flow and
   the feature branch is removed.
5. The executor sends the curator a short technical handoff containing the PR,
   merge commit, material changes, checks and deliberate non-implementations.
   After dispatch, the curator does not poll or send heartbeats; it waits for
   that result or a blocking question.
6. Technical completion does not imply owner acceptance. The owner reviews the
   result and alone records acceptance with the exact phrase `Задача принята`.
   Neither curator nor executor may synthesize it.
7. Where Codex Desktop exposes supported thread controls, curator and executor
   receive short linked titles and stay pinned. This is best-effort Desktop
   state rather than a repository capability; final unpinning is manual and
   belongs to the owner.

## Future test contour: `Лаборатория оркестратора`

The repository remains the single source of truth. A future orchestrator lab
may be a separate ChatGPT/Codex Project with its own isolated runtime and state
space for synthetic tests only. It is not the working method for developing
`dev-control-plane`, is not connected to `wb-core`, and has no authority over a
target repository or production system.

The owner can prepare the Project manually when a later test task approves it:

1. Create a new ChatGPT/Codex Project named `Лаборатория оркестратора`.
2. In its instructions, name this repository and these authoritative documents
   as the only source of truth; limit the Project to synthetic tests; forbid
   `wb-core`, production and target-repository changes; and require explicit
   owner acceptance.
3. For any separately approved runtime experiment, choose a dedicated local
   state directory outside this Git worktree and keep runtime state, logs,
   credentials and test artifacts there.
4. Do not start a runtime or connect an external system until a separate task
   approves the specific experiment and its cleanup.

This task creates neither that UI Project nor any laboratory runtime or state.

## Boundary

The active tree remains documentation plus model-free CI. Future requirements,
architecture, runtime, integrations, security boundaries and rollout must be
approved in a separate task before code is added. Legacy v1/v2 is evidence
only and must not be reactivated or copied.
