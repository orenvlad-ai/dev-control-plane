# Development Control Plane MVP

## Summary

Development Control Plane is a generic local/internal control-plane for bounded development tasks. It turns operator discussion into task specs, freezes those specs, builds prompts, prepares isolated run artifacts, runs fake executor flows, and verifies handoff artifacts.

## Control-Plane vs Product-Plane

The control-plane is not a product runtime, product UI, public route, deploy lane or hosted operator surface. It must remain independently available from any target product-plane. Future hosted use requires separate host, auth, state, secrets and access policy.

## Current MVP

- TaskSpec, SprintPlan and SprintStep contracts.
- Local CLI for validate, freeze and prompt generation.
- Local-only server bound to `127.0.0.1`.
- Russian chat-first local cockpit with `Чат`, `Подключения` and `Технические детали`.
- Fake and optional OpenAI curator intake.
- Target project adapter/config layer for external repos.
- Target-aware practical cockpit flow with Task Card, next action and compact run/blocker summary.
- Guided safe fake-flow.
- Runner CLI for prepare-run, fake run-step, verify-run and cleanup-run.
- Runner CLI for gated real Codex CLI target runs using managed clone workspaces.
- Deterministic verifier for prompt/handoff blocks, forbidden paths and git diff checks.
- Smoke coverage that does not call OpenAI or real Codex; the Codex gate smoke uses a fake Codex binary.

## Not In Scope

- Production/public route registration.
- Real Codex execution by default.
- Real Codex execution through the local UI.
- OpenAI API use in smoke tests.
- SSH/root/live deploy operations.
- Auto-merge or target product runtime mutation.
- Database migrations or hosted control-plane state.
- Target repo mutation by default.

## Target Project Adapters

Target repositories are external repos described by local adapter metadata under `configs/target_projects/`. A target adapter may provide repo root, source-of-truth docs, derived secondary paths, forbidden paths/actions, smoke commands and prompt-contract notes.

The adapter metadata is not source of truth. Source-of-truth docs, code and policies remain in the target repo. The control-plane reads target source paths to build snapshots and merges target defaults into draft specs. Missing optional paths warn; a target with no usable source-of-truth path blocks.

`wb-core` is one target project profile. It is not this repo's identity and must not be hardcoded into package names, state directories or routes. Target project mutation is future gated execution work; current validation and snapshot flows are read-only.

## Gated Codex CLI Path

MVP-2.0 adds a CLI-only real Codex execution lane. It is disabled in the UI and blocked unless the operator passes `--allow-real-codex`, the task spec is frozen, the target validates, and the target execution policy allows managed-clone execution.

The runner creates `state_dir/target-runs/<run_id>/workspace/<project_id>/` from a local git clone of the target repo HEAD. The original target repo working tree and git metadata are not used as the execution workspace. Outputs are prompt, handoff, log, diff and verifier artifacts. The runner does not auto-commit, push, merge, deploy, SSH, or mutate product-plane routes.

Verifier checks target runs for frozen spec, prompt/handoff presence, mandatory handoff blocks, forbidden path hits, `git diff --check`, Codex exit code, managed workspace ownership, and unchanged original target repo state.

## Practical Cockpit Flow

The local cockpit supports the first real target-aware UX loop:

1. Operator selects a target project.
2. The server validates the target read-only and builds a compact target context summary.
3. Operator writes the task in a normal Russian chat.
4. Discussion plus selected target defaults are passed to OpenAI curator intake.
5. The curator returns a draft TaskSpec only.
6. The UI shows a human-readable Task Card before raw JSON.
7. The recommended next action progresses from draft to freeze to safe fake run.
8. Guided safe fake-flow generates prompt, prepares run artifacts, runs fake executor and verifies.
9. The UI shows compact result/blocker status, with raw JSON, prompt, handoff, logs and paths collapsed under technical details.

The operator UI does not expose a fake/OpenAI selector. Fake curator mode is reserved for smoke/internal fallback through `DEV_CONTROL_PLANE_ENABLE_FAKE_CURATOR=1`. OpenAI curator mode must fail closed when env configuration is absent; smoke coverage verifies missing-key behavior without making a network call.

## Connections Setup

The `Подключения` tab reports OpenAI and Codex CLI readiness without accepting secrets in the browser. OpenAI is configured only through terminal env:

```bash
export OPENAI_API_KEY="..."
export CURATOR_COCKPIT_OPENAI_MODEL="..."
```

Codex CLI subscription auth is terminal-only:

```bash
codex --login
```

The UI may run `codex --version` for install status, but it does not perform login, store API keys, or start real Codex execution.

## Safety Defaults

Execution from raw discussion is forbidden. Prompt/run generation requires a frozen spec. Fake executor is the UI and smoke path. Real Codex CLI execution requires explicit operator-controlled flags and task/target policy. Secrets must not appear in state, prompts, logs, handoffs or summaries.
