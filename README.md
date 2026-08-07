# Development Control Plane

This repository is a minimal planning surface for a future development control
plane. It currently contains no runtime, scheduler, supervisor, hosted service,
API, UI, target adapter or Agent Orchestrator implementation.

Repository changes use one simple flow: discuss with the project curator,
say `запускай` to dispatch one separate user-owned Codex executor task, work in
an isolated branch/worktree, validate and self-review, then open, check and
merge a normal pull request after green CI. The executor gives the curator a
short technical handoff; only the owner closes the human acceptance step with
`Задача принята`. The curator dispatches but does not edit or poll. There is no
Release Train, queue or parallel change orchestration.

The retired v1/v2 epoch is preserved at the annotated tag
[`archive/legacy-v1-v2-20260807`](https://github.com/orenvlad-ai/dev-control-plane/releases/tag/archive/legacy-v1-v2-20260807).
Its sensitive runtime state is retained separately in owner-private,
checksum-verified archives and is not stored in Git.

Start with:

- [`docs/PROJECT_BRIEF.md`](docs/PROJECT_BRIEF.md)
- [`docs/ROADMAP.md`](docs/ROADMAP.md)
- [`docs/DECISIONS.md`](docs/DECISIONS.md)

Any architecture or implementation begins as a separate, explicitly approved
task. Technical readiness never substitutes for owner acceptance.
