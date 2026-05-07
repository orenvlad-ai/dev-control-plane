# Development Control Plane MVP

## Summary

Development Control Plane is a generic local/internal control-plane for bounded development tasks. It turns operator discussion into task specs, freezes those specs, builds prompts, prepares isolated run artifacts, runs fake executor flows, and verifies handoff artifacts.

This repo is the standalone project identity for the control-plane. Target repositories such as `wb-core` are external inputs, not the identity of this repo.

## Control-Plane vs Product-Plane

The control-plane is not a product runtime, product UI, public route, deploy lane or hosted operator surface. It must remain independently available from any target product-plane. Future hosted use requires separate host, auth, state, secrets and access policy.

No SellerOS or target product-plane coupling is part of the control-plane MVP. Adapters may describe target repos, but target product routes, deploy lanes and business runtime behavior remain outside this repo.

## Current MVP

- TaskSpec, SprintPlan and SprintStep contracts.
- Local CLI for validate, freeze and prompt generation.
- Loopback-only server bound to `127.0.0.1`, with hosted runtime profile setup documented separately.
- Russian chat-first local cockpit with optimistic message rendering, loading states, `Чат`, `Подключения` and collapsed `Технические детали`.
- Fake and optional OpenAI curator intake.
- Target project adapter/config layer for external repos.
- Target-aware practical cockpit flow with Task Card, two primary operator actions and compact run/blocker summary.
- Guided safe fake-flow.
- Operator-confirmed local UI real Codex run in a managed clone.
- Compact scrollable `Ход выполнения` timeline for real Codex runs.
- Hosted read-only live monitor at `/runs/live`, with sanitized terminal-like output, stage timeline, active/recent runs, changed files, verifier status and final report/handoff previews.
- TaskSpec sprint-step normalization for missing/empty `sprint_steps`.
- Runner CLI for prepare-run, fake run-step, verify-run and cleanup-run.
- Runner CLI and local UI path for gated real Codex target runs using managed clone workspaces.
- MCP Stage 1 backend at `POST /mcp` using streamable HTTP. Public ChatGPT discovery is mixed no-auth read plus OAuth-gated write: unauthenticated discovery exposes bounded status/run/artifact/timeline/log-tail/target/search/fetch tools only, while authenticated OAuth sessions can see bounded write tools.
- Deterministic verifier for prompt/handoff contract blocks, forbidden paths and git diff checks.
- Local OpenAI secret setup CLI and restricted file-backed credential store.
- Sanitized OpenAI diagnostics and a manual OpenAI probe CLI.
- Smoke coverage that does not call OpenAI or real Codex; the Codex gate/UI/timeline smokes use a fake Codex binary.

## Not In Scope

- Production/public route registration.
- Real Codex execution by default.
- OpenAI API use in smoke tests.
- SSH/root/live deploy operations.
- Target repo auto-merge or target product runtime mutation.
- Unauthenticated MCP write tools, including hidden write tools accidentally appearing in public `tools/list`.
- Static bearer as ChatGPT UI write auth; OAuth authorization-code + PKCE is the supported ChatGPT write-tool gate, while bearer auth remains protocol-smoke/direct-control fallback only.
- Database migrations or hosted control-plane state.
- Target repo mutation by default.
- Direct mutation of the original target repo by safe fake-flow or managed Codex UI flow.
- Real OpenAI or real Codex calls in smoke tests.

## Target Project Adapters

Target repositories are external repos described by local adapter metadata under `configs/target_projects/`. A target adapter may provide repo root, source-of-truth docs, derived secondary paths, forbidden paths/actions, smoke commands and prompt-contract notes.

The adapter metadata is not source of truth. Source-of-truth docs, code and policies remain in the target repo. The control-plane reads target source paths to build snapshots and merges target defaults into draft specs. Missing optional paths warn; a target with no usable source-of-truth path blocks.

Source-of-truth paths are context, not automatic forbidden paths. A target may list `README.md`, `docs/architecture/`, `docs/modules/` or `migration/` as canonical context without forbidding safe bounded edits there. Forbidden paths come from explicit task scope or target policy defaults.

`wb-core` is one target project profile. It is not this repo's identity and must not be hardcoded into package names, state directories or routes. Target project mutation is future gated execution work; current validation and snapshot flows are read-only.

The current `wb-core` adapter points at `/Users/ovlmacbook/Projects/wb-core`. The current ChatGPT Project for `wb-core` remains canonical for `wb-core` product work. Control-plane tasks must not mutate `wb-core` except through managed clones and a future explicit apply policy.

## Gated Codex CLI Path

MVP-2.0 added a CLI-only real Codex execution lane. MVP-2.1 adds an operator-confirmed local UI lane for the same managed-clone executor. The UI lane is local-only, has no arbitrary command input, and is blocked unless the task spec is frozen, the target validates, Codex CLI is available, and the target execution policy allows managed-clone execution. The CLI lane still requires `--allow-real-codex`; safe managed-clone TaskSpecs should not duplicate that CLI gate as a human gate.

The runner creates managed workspaces under `state_dir/workspaces/<run_id>/<project_id>/` from either a local target repo source or a hosted `remote_managed_clone` source. Run metadata and artifacts live under `state_dir/runs/<run_id>/` with `artifacts/`, `logs/` and `verifier/` subdirectories. The original target repo working tree and git metadata are not used as the execution workspace. Outputs are prompt, handoff, log, terminal log, timeline, diff and verifier artifacts. The runner/UI path does not auto-commit, push, merge, deploy, SSH, or mutate product-plane routes. The operator confirms the real Codex run itself, but does not need to manually confirm the generated managed-clone path for ordinary safe docs-only tasks.

The UI endpoint returns a background job id immediately and the cockpit polls `GET /api/real-runs/{id}`. Job states are `queued`, `preparing`, `running_codex`, `verifying`, `passed`, `failed`, and `blocked`.

The hosted live monitor follows the same run model. `/runs/live` and `/runs/<run_id>/watch` render sanitized state only and are protected by Basic Auth; the main operator page links to the monitor as `Живые запуски`. The API/SSE endpoints under `/api/runs/*` expose sanitized summaries, cursor-based timeline events and offset-based terminal tails only; they do not expose raw logs or command input. The browser keeps the selected run pinned, updates run rows by `run_id`, appends terminal output by offset, and stops high-frequency per-run updates after terminal status. ANSI handling allowlists SGR color/style codes, strips unsafe terminal controls such as OSC/DCS/clipboard/title/hyperlink sequences, decodes escaped human multiline text and hides common Codex JSON metadata envelopes by default.

The MCP endpoint follows the same long-running rule. Start tools return a `run_id` quickly plus `live_url` / `watch_url`; `list_active_runs`, `get_run_status`, `get_run_report`, `get_run_timeline`, `get_run_log_tail`, `list_run_artifacts` and `get_run_artifact` own follow-up inspection. MCP write tools do not accept shell commands. `start_managed_clone_run` is no-PR/no-deploy. `start_wb_core_production_lane` is explicit and uses the existing `wb-core` production-lane gates; dry-run mode records prompt/report/rollback artifacts without Codex, PR, merge or deploy.

Before starting Codex, the hosted runner performs managed-workspace preflight with workspace existence/write checks, `pwd`, `git status --short --branch`, `rg --version`, `python3 --version`, `jq --version` and the configured `codex --version`. It also writes a sanitized `verifier/preflight/toolchain.json` capability matrix with required tools, optional tools, detected paths, versions, source (`system` or `runtime-local`), warnings and blockers. A failed preflight returns a controlled blocker and does not start Codex. Optional tools such as `node`, `npm`, `corepack`, `pnpm`, `yarn`, `ssh` or `rsync` are warnings unless the inspected managed workspace manifests require them. `gh` is required only when a verifier-passed run enters the explicit `wb-core` production lane; that lane writes a separate sanitized production-lane toolchain preflight and blocks before target lock acquisition if GitHub CLI is unavailable. The Codex command receives explicit runtime model/reasoning and sandbox settings from non-secret runtime config. In hosted mode, `danger-full-access` is allowed only as a Codex CLI compatibility mode for the isolated managed clone when Linux bubblewrap cannot create loopback networking; original target mutation, target commit/push/PR/merge/deploy and product runtime changes remain forbidden by DCP policy and verifier gates.

The real Codex prompt contract requires the final answer to start with exact first line `=== ДЛЯ КУРАТОРА ===` and to include `=== СЖАТАЯ ПРОВЕРКА ===`. Missing or misplaced handoff blocks are verifier failures with operator-readable reasons.

For this `dev-control-plane` repo only, the prompt contract now permits Codex-owned commit/push/PR/merge/delete-branch closure, including L3, after clean merge eligibility gates. The permission does not apply to `wb-core` or any target repo, production deploy, preview/staging deploy, direct target mutation, public routes or SSH/root actions.

CLI runner step selection follows the same runnable-step contract as the cockpit: no step id means first runnable step, and a missing requested step id falls back to the first runnable step with a warning instead of blocking before execution.

Verifier checks target runs for frozen spec, prompt/handoff presence, mandatory handoff blocks, forbidden path hits, `git diff --check`, Codex exit code, managed workspace ownership, and unchanged original target repo state.

For `wb-core` visible UI label, interface text, tab label and template text tasks, TaskSpec scope may expand only to bounded UI template paths. The current allowed expansion is `packages/adapters/templates/*.html`, with exact file additions such as `packages/adapters/templates/sheet_vitrina_v1_web_vitrina.html` when the operator explicitly names the visible `Витрина` label. This does not open broad package paths and does not relax forbidden paths such as `runtime/**`, `deploy/**`, `infra/**`, `artifacts/registry_upload_http_entrypoint/**`, `wb_core_docs_master/**` or `99_MANIFEST__DOCSET_VERSION.md`.

The GitHub closure eligibility helper checks repo identity, PR ownership, PR head SHA, clean working tree, required checks, diff checks, verifier status, forbidden paths/actions, protected derived docset paths, secrets scan state, handoff completeness, blocker absence and `NO_AUTO_MERGE`. Runner CLI and local server expose this as a decision-only gate; they do not execute hidden GitHub API mutation or store GitHub credentials.

Target PR, preview and approve/reject support is also decision-only in this MVP. It can produce plans for `wb-core` managed-clone output, preview URL shape and approval gates, but it does not push target branches, merge target PRs or deploy WebCore.

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

The hosted card draft path starts a short `/api/discussions/{id}/draft-task-spec-jobs` request and polls `/api/draft-task-spec-jobs/{id}` so nginx proxy timeouts do not break long deep-curator requests. Card draft responses include sanitized performance diagnostics: total duration, target validation duration, context build duration, curator duration, card validation duration, selected model/reasoning and token estimate. They must not include prompts with secrets, Authorization headers or raw provider bodies.

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
export CURATOR_COCKPIT_OPENAI_REASONING_EFFORT="xhigh"
export DEV_CONTROL_PLANE_OPENAI_TIMEOUT_SECONDS="180"
export DEV_CONTROL_PLANE_OPENAI_RETRY_COUNT="2"
export DEV_CONTROL_PLANE_OPENAI_RETRY_BACKOFF_SECONDS="2"
```

Codex CLI subscription auth is terminal-only:

```bash
codex --login
```

The UI may run `codex --version` for install status, but it does not perform login, accept API keys, or start real Codex execution.

## OpenAI Diagnostics

OpenAI errors are mapped into safe operator-facing types: `missing_api_key`, `missing_model`, `auth_error`, `permission_error`, `model_not_found`, `rate_limited`, `timeout`, `provider_timeout`, `network_error`, `server_error`, `certificate_error`, `bad_request`, `invalid_json`, `unexpected_response_shape` and `unknown_error`. Deep hosted requests use a 180 second default timeout and bounded retry/backoff only for timeout, transient network, provider timeout and 5xx/server errors.

The connection test endpoint and manual probe read env credentials first and then the local secret file. They may return error type, HTTP status, request id, provider, model, short message and suggested next step. They must not return API keys, Authorization headers, raw tracebacks or full response bodies. Smoke coverage uses stubbed OpenAI responses and does not call the real OpenAI API.

## Safety Defaults

Execution from raw discussion is forbidden. Prompt/run generation requires a frozen spec. Fake executor is the UI and smoke path. Real Codex CLI execution requires explicit operator-controlled flags and task/target policy. Secrets must not appear in repo files, UI fields, API responses, state, prompts, logs, handoffs or summaries.
