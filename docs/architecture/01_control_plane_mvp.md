# Development Control Plane MVP

## Summary

Development Control Plane is a generic local/internal control-plane for bounded development tasks. It turns operator discussion into task specs, freezes those specs, builds prompts, prepares isolated run artifacts, runs fake executor flows, and verifies handoff artifacts.

## Control-Plane vs Product-Plane

The control-plane is not a product runtime, product UI, public route, deploy lane or hosted operator surface. It must remain independently available from any target product-plane. Future hosted use requires separate host, auth, state, secrets and access policy.

## Current MVP

- TaskSpec, SprintPlan and SprintStep contracts.
- Local CLI for validate, freeze and prompt generation.
- Local-only server bound to `127.0.0.1`.
- Russian chat-first local cockpit with optimistic message rendering, loading states, `Чат`, `Подключения` and collapsed `Технические детали`.
- Fake and optional OpenAI curator intake.
- Target project adapter/config layer for external repos.
- Target-aware practical cockpit flow with Task Card, two primary operator actions and compact run/blocker summary.
- Guided safe fake-flow.
- Operator-confirmed local UI real Codex run in a managed clone.
- Compact scrollable `Ход выполнения` timeline for real Codex runs.
- TaskSpec sprint-step normalization for missing/empty `sprint_steps`.
- Runner CLI for prepare-run, fake run-step, verify-run and cleanup-run.
- Runner CLI and local UI path for gated real Codex target runs using managed clone workspaces.
- Deterministic verifier for prompt/handoff contract blocks, forbidden paths and git diff checks.
- Local OpenAI secret setup CLI and restricted file-backed credential store.
- Sanitized OpenAI diagnostics and a manual OpenAI probe CLI.
- Smoke coverage that does not call OpenAI or real Codex; the Codex gate/UI/timeline smokes use a fake Codex binary.

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

Source-of-truth paths are context, not automatic forbidden paths. A target may list `README.md`, `docs/architecture/`, `docs/modules/` or `migration/` as canonical context without forbidding safe bounded edits there. Forbidden paths come from explicit task scope or target policy defaults.

`wb-core` is one target project profile. It is not this repo's identity and must not be hardcoded into package names, state directories or routes. Target project mutation is future gated execution work; current validation and snapshot flows are read-only.

## Gated Codex CLI Path

MVP-2.0 added a CLI-only real Codex execution lane. MVP-2.1 adds an operator-confirmed local UI lane for the same managed-clone executor. The UI lane is local-only, has no arbitrary command input, and is blocked unless the task spec is frozen, the target validates, Codex CLI is available, and the target execution policy allows managed-clone execution. The CLI lane still requires `--allow-real-codex`; safe managed-clone TaskSpecs should not duplicate that CLI gate as a human gate.

The runner creates `state_dir/target-runs/<run_id>/workspace/<project_id>/` from a local git clone of the target repo HEAD. The original target repo working tree and git metadata are not used as the execution workspace. Outputs are prompt, handoff, log, diff and verifier artifacts. The runner/UI path does not auto-commit, push, merge, deploy, SSH, or mutate product-plane routes. The operator confirms the real Codex run itself, but does not need to manually confirm the generated managed-clone path for ordinary safe docs-only tasks.

The UI endpoint returns a background job id immediately and the cockpit polls `GET /api/real-runs/{id}`. Job states are `queued`, `preparing`, `running_codex`, `verifying`, `passed`, `failed`, and `blocked`.

The real Codex prompt contract requires the final answer to start with exact first line `=== ДЛЯ КУРАТОРА ===` and to include `=== СЖАТАЯ ПРОВЕРКА ===`. Missing or misplaced handoff blocks are verifier failures with operator-readable reasons.

CLI runner step selection follows the same runnable-step contract as the cockpit: no step id means first runnable step, and a missing requested step id falls back to the first runnable step with a warning instead of blocking before execution.

Verifier checks target runs for frozen spec, prompt/handoff presence, mandatory handoff blocks, forbidden path hits, `git diff --check`, Codex exit code, managed workspace ownership, and unchanged original target repo state.

## Practical Cockpit Flow

The local cockpit supports the first real target-aware UX loop:

1. Operator selects a target project.
2. The server validates the target read-only and builds a compact target context summary.
3. Operator writes the task in a normal Russian chat.
4. The operator message appears immediately, the UI shows a pending/typing state, then discussion plus selected target defaults are passed to OpenAI curator intake.
5. The curator returns a draft TaskSpec only.
6. The UI shows a human-readable Task Card before raw JSON.
7. The primary `Подготовить задачу` action drafts the card and may freeze simple validated L1/L2 repo-only tasks; risky L3/gated tasks require operator confirmation before freeze.
8. The operator may explicitly confirm `Запустить Codex безопасно`; this starts real Codex only in a managed clone and returns progress through a background job.
9. The UI shows a fixed-height scrollable `Ход выполнения` block from job lifecycle, Codex JSONL log events, changed files and verifier checks.
10. The UI shows `Результат выполнения` with changed files, changed-file count, target unchanged status, verifier status, `git diff --check`, next action, and compact diff/handoff previews.
11. `Тестовый прогон без Codex` remains available under additional actions; raw JSON, prompt, handoff, diff, logs and paths are collapsed under technical details.

The operator UI does not expose a fake/OpenAI selector. Fake curator mode is reserved for smoke/internal fallback through `DEV_CONTROL_PLANE_ENABLE_FAKE_CURATOR=1`. OpenAI curator mode must fail closed when env configuration is absent; smoke coverage verifies missing-key behavior without making a network call.

## Connections Setup

The `Подключения` tab reports OpenAI and Codex CLI readiness without accepting secrets in the browser. OpenAI is configured through terminal-only setup:

```bash
python3 apps/dev_control_plane_setup.py openai
```

The setup command reads the key with hidden input and writes `~/.dev-control-plane/secrets.json` outside this repo with restricted permissions where practical. The status command reports only sanitized metadata:

```bash
python3 apps/dev_control_plane_setup.py status
```

Environment variables remain supported and override the local secret file:

```bash
export OPENAI_API_KEY="..."
export CURATOR_COCKPIT_OPENAI_MODEL="..."
```

Codex CLI subscription auth is terminal-only:

```bash
codex --login
```

The UI may run `codex --version` for install status, but it does not perform login, accept API keys, or start real Codex execution.

## OpenAI Diagnostics

OpenAI errors are mapped into safe operator-facing types: `missing_api_key`, `missing_model`, `auth_error`, `permission_error`, `model_not_found`, `rate_limited`, `timeout`, `network_error`, `certificate_error`, `bad_request`, `invalid_json`, `unexpected_response_shape` and `unknown_error`.

The connection test endpoint and manual probe read env credentials first and then the local secret file. They may return error type, HTTP status, request id, provider, model, short message and suggested next step. They must not return API keys, Authorization headers, raw tracebacks or full response bodies. Smoke coverage uses stubbed OpenAI responses and does not call the real OpenAI API.

## Safety Defaults

Execution from raw discussion is forbidden. Prompt/run generation requires a frozen spec. Fake executor is the UI and smoke path. Real Codex CLI execution requires explicit operator-controlled flags and task/target policy. Secrets must not appear in repo files, UI fields, API responses, state, prompts, logs, handoffs or summaries.
