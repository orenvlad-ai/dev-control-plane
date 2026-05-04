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

## Target Project Adapters

Target repositories are future configurable inputs. A target adapter may provide repo root, source-of-truth docs, forbidden paths, smoke commands and policy defaults. No target repository is the identity of this project. A repository such as `wb-core` can be one future target adapter, not a hardcoded package name, route, state directory or UI identity.

## Safety Defaults

Execution from raw discussion is forbidden. Prompt/run generation requires a frozen spec. Fake executor is the smoke path. Command executor requires explicit operator-controlled flags and task policy. Secrets must not appear in state, prompts, logs, handoffs or summaries.

