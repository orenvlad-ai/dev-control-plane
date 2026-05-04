# Development Control Plane MVP

## Summary

Development Control Plane is a generic local/internal control-plane for bounded development tasks. It turns operator discussion into task specs, freezes those specs, builds prompts, prepares isolated run artifacts, runs fake executor flows, and verifies handoff artifacts.

## Control-Plane vs Product-Plane

The control-plane is not a product runtime, product UI, public route, deploy lane or hosted operator surface. It must remain independently available from any target product-plane. Future hosted use requires separate host, auth, state, secrets and access policy.

## Current MVP

- TaskSpec, SprintPlan and SprintStep contracts.
- Local CLI for validate, freeze and prompt generation.
- Local-only server bound to `127.0.0.1`.
- Discuss, Task Spec, Sprint Plan, Human Gates and Run UI.
- Fake and optional OpenAI curator intake.
- Target project adapter/config layer for external repos.
- Target-aware practical cockpit flow with Task Card, next action and compact run/blocker summary.
- Guided safe fake-flow.
- Runner CLI for prepare-run, fake run-step, verify-run and cleanup-run.
- Deterministic verifier for prompt/handoff blocks, forbidden paths and git diff checks.
- Smoke coverage that does not call OpenAI or real Codex.

## Not In Scope

- Production/public route registration.
- Real Codex execution by default.
- OpenAI API use in smoke tests.
- SSH/root/live deploy operations.
- Auto-merge or target product runtime mutation.
- Database migrations or hosted control-plane state.
- Target repo mutation by default.

## Target Project Adapters

Target repositories are external repos described by local adapter metadata under `configs/target_projects/`. A target adapter may provide repo root, source-of-truth docs, derived secondary paths, forbidden paths/actions, smoke commands and prompt-contract notes.

The adapter metadata is not source of truth. Source-of-truth docs, code and policies remain in the target repo. The control-plane reads target source paths to build snapshots and merges target defaults into draft specs. Missing optional paths warn; a target with no usable source-of-truth path blocks.

`wb-core` is one target project profile. It is not this repo's identity and must not be hardcoded into package names, state directories or routes. Target project mutation is future gated execution work; current validation and snapshot flows are read-only.

## Practical Cockpit Flow

The local cockpit supports the first real target-aware UX loop:

1. Operator selects a target project.
2. The server validates the target read-only and builds a compact target context summary.
3. Discussion plus selected target defaults are passed to the curator intake.
4. The curator returns a draft TaskSpec only.
5. The UI shows a human-readable Task Card before raw JSON.
6. The recommended next action progresses from draft to freeze to safe fake run.
7. Guided safe fake-flow generates prompt, prepares run artifacts, runs fake executor and verifies.
8. The UI shows compact result/blocker status, with raw prompt/handoff in details.

OpenAI curator mode is optional and must fail closed when env configuration is absent. Smoke coverage uses the fake curator only for successful draft flow and verifies OpenAI missing-key behavior without making a network call.

## Safety Defaults

Execution from raw discussion is forbidden. Prompt/run generation requires a frozen spec. Fake executor is the smoke path. Command executor requires explicit operator-controlled flags and task policy. Secrets must not appear in state, prompts, logs, handoffs or summaries.
