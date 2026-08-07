# Roadmap

The current operating constraint is one active change task at a time using the
simple curator-to-executor PR flow in `PROJECT_BRIEF.md`. A Release Train, task
queue and parallel orchestration are not part of that flow.

The following items are backlog only and are not designed or implemented:

1. Write a separately approved product and threat-model brief.
2. Evaluate upstream foundations, including provenance, licensing and support
   boundaries, before selecting any runtime.
3. Define one authority model, explicit human acceptance and target-repository
   safety boundaries.
4. Design a first synthetic experiment for the isolated `Лаборатория
   оркестратора` contour, including state isolation and cleanup, before creating
   or starting any lab runtime.
5. Specify deterministic tests, recovery and operational evidence before a
   pilot.
6. Treat any GitHub integration, hosted UI or `devcontrol.pro` rollout as a
   later governed deployment task with rollback proof.
