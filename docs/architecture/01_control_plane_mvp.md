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
- Unified dark operator dashboard with `Панель`, `Подключение`, `Мониторинг` and `Технические детали` sections.
- Fake and optional OpenAI curator intake.
- Target project adapter/config layer for external repos.
- Legacy target-aware chat/task-card backend flow retained for API compatibility and smoke coverage, hidden from the primary dashboard UI.
- Guided safe fake-flow.
- Operator-confirmed managed Codex runs in managed clones through CLI/MCP and legacy API paths.
- Hosted live monitor timeline and terminal output for real Codex runs.
- Hosted monitor at `/runs/live`, with sanitized terminal-like output, stage timeline, active/recent runs, changed files, verifier status, selected promotion controls and final report/handoff previews.
- TaskSpec sprint-step normalization for missing/empty `sprint_steps`.
- Runner CLI for prepare-run, fake run-step, verify-run and cleanup-run.
- Runner CLI, MCP and legacy API path for gated real Codex target runs using managed clone workspaces.
- MCP Stage 1 backend at `POST /mcp` using streamable HTTP. Public ChatGPT discovery is mixed no-auth read plus OAuth-gated authenticated tools: unauthenticated discovery exposes bounded status/run/artifact/timeline/log-tail/target/search/fetch tools only, while authenticated OAuth sessions can see bounded write tools and read-only target documentation tools. `start_sprint` is frozen/hidden for ordinary operator discovery.
- Parallel task ledger MVP under `state/collections/parallel_task_ledger.json`: multi-source task intake, target/epoch promotion state, first-finished candidate selection and freeze/refresh-required semantics. The server/API/MCP surface is state-only and does not start workers or production-lane work.
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

MVP-2.0 added a CLI-only real Codex execution lane. Later hosted stages added MCP and legacy API compatibility lanes for the same managed-clone executor. These paths have no arbitrary command input and are blocked unless the task spec/run request is bounded, the target validates, Codex CLI is available, and the target execution policy allows managed-clone execution. The CLI lane still requires `--allow-real-codex`; safe managed-clone TaskSpecs should not duplicate that CLI gate as a human gate.

The runner creates managed workspaces under `state_dir/workspaces/<run_id>/<project_id>/` from either a local target repo source or a hosted `remote_managed_clone` source. Run metadata and artifacts live under `state_dir/runs/<run_id>/` with `artifacts/`, `logs/` and `verifier/` subdirectories. The original target repo working tree and git metadata are not used as the execution workspace. Outputs are prompt, handoff, log, terminal log, timeline, diff and verifier artifacts. The runner/UI path does not auto-commit, push, merge, deploy, SSH, or mutate product-plane routes. The operator confirms the real Codex run itself, but does not need to manually confirm the generated managed-clone path for ordinary safe docs-only tasks.

The UI endpoint returns a background job id immediately and the cockpit polls `GET /api/real-runs/{id}`. Job states are `queued`, `preparing`, `running_codex`, `verifying`, `passed`, `failed`, and `blocked`.

The hosted monitor follows the same run model. `/runs/live` and `/runs/<run_id>/watch` render sanitized state only and are protected by Basic Auth; the main operator page links to the monitor as `Мониторинг`. The API/SSE endpoints under `/api/runs/*` expose sanitized summaries, frozen prompt previews, cursor-based timeline events and offset-based terminal tails; they do not expose raw logs or command input. Bounded `cancel` and `mark-stale` APIs are run-control actions only, not shell execution, and cancel may signal only the recorded run-owned Codex process group while preserving artifacts/workspaces. The browser keeps the selected run pinned, updates run rows by `run_id`, appends terminal output by offset, and stops high-frequency per-run updates after terminal status. ANSI handling allowlists SGR color/style codes, strips unsafe terminal controls such as OSC/DCS/clipboard/title/hyperlink sequences, decodes escaped human multiline text and hides common Codex JSON metadata envelopes by default.

The MCP endpoint follows the same long-running rule. Accepted start tools return a `run_id` quickly plus `live_url` / `watch_url`; `list_active_runs`, `get_run_status`, `get_run_report`, `get_run_timeline`, `get_run_log_tail`, `list_run_artifacts` and `get_run_artifact` own follow-up inspection. MCP write tools do not accept shell commands. `start_wb_core_auto_task` is the ordinary ChatGPT Project path for `wb-core`/WebCore work: it either starts one direct production-capable run that continues through the existing `wb-core` production lane, or returns a precise blocker before Codex starts. It must not fall back to sprint, `start_managed_clone_run`, the `DEVCONTROL_START_SPRINT_V1` bridge or managed-clone-only execution. `start_managed_clone_run` is no-PR/no-deploy and is not a WebCore merge/deploy fallback. `start_wb_core_production_lane` is explicit and uses the existing `wb-core` production-lane gates; dry-run mode records prompt/report/rollback artifacts without Codex, PR, merge or deploy. `start_sprint`, the sprint orchestrator, curator ping-pong and parent/child run tree are frozen for ordinary operator flow; direct non-internal calls return `start_sprint is frozen for operator flow; use direct wb-core auto Codex task`. `resume_wb_core_production_deploy` is a separate OAuth-gated recovery path for already merged blocked production-lane runs; it resumes only backup/deploy/probes after eligibility checks and never reruns Codex, branches, commits, pushes, opens a new PR or merges again. Authenticated target docs tools are read-only and never run Codex; they read allowlisted docs from a cached git snapshot and reject traversal, forbidden paths and oversized reads.

## Parallel Task Ledger MVP

The parallel task ledger is the first server-side model for future multi-source task orchestration. It is file-backed JSON state, not a durable DB/object-store, and lives under the normal state layout as `collections/parallel_task_ledger.json`.

The ledger is target-scoped, not chat-scoped:
- a `TaskRecord` has `target_id`, `promotion_epoch`, `source`, optional `chat_id`, optional `batch_id`, optional `release_group`, optional `idempotency_key`, task text and lifecycle status;
- a `ParallelRun` binds a task to a managed-clone run or future production-lane run id without launching either one;
- a `PromotionCandidate` is created when a managed run verifier passes;
- a `TargetPromotionState` tracks first-candidate selection, production-lane state, completion and frozen sibling ids for one `target_id + promotion_epoch`.

Batch/release groups are metadata only. They do not own execution or promotion; the governing scope is `target_id + promotion_epoch`. Idempotency is enforced within that scope.

MVP statuses are: `submitted`, `managed_run_running`, `verifier_passed`, `promotion_queued`, `auto_promoting_first`, `production_lane_running`, `production_complete`, `frozen_base_stale`, `refresh_required`, `blocked` and `failed`.

The first-finished rule is deliberately conservative and now applies only to legacy/admin parallel promotion state. The ledger can select the earliest verifier-passed candidate, but marking it `auto_promoting_first` requires an explicit policy flag. Without that flag the candidate is queued and promotion does not start. Ordinary `wb-core` work does not depend on this ledger: `start_wb_core_auto_task` uses the verified managed clone/worktree as the production source of truth, and `diff.patch` is audit evidence rather than a transport layer.

This MVP explicitly freezes ping-pong/server-side curator use for parallel-flow. The ledger records `parallel_ping_pong_enabled=false` and does not call `start_sprint`.

The server/API/MCP entrypoint is operator-visible and guarded:
- `POST /api/parallel-tasks` submits a ledger task;
- the main operator dashboard renders task/candidate/promotion summaries, frozen/refresh-required state and fake/dry action controls;
- `POST /api/parallel-tasks/{id}/start-execution` explicitly binds a fake managed-run id by default and moves the task to `managed_run_running`;
- `execution_mode=real_managed_clone` is an opt-in bridge into the existing managed-clone runner, disabled unless the runtime enables it and the caller confirms it; it never calls sprint/ping-pong, PR, merge, deploy or production lane;
- `POST /api/parallel-tasks/{id}/reconcile` explicitly consumes a managed-run status/report or sanitized existing run/job artifacts and updates `verifier_passed`, `blocked` or `failed`;
- `POST /api/parallel-tasks/{id}/promote`, `POST /api/parallel-targets/{id}/promote-next` and `POST /api/parallel-selection/promote` evaluate promotion state and can fake-complete or plan the state machine for tests only;
- `GET /api/parallel-tasks`, `GET /api/parallel-tasks/{id}`, `GET /api/parallel-targets/{id}/promotion-candidates` and `GET /api/parallel-targets/{id}/promotion-state` read sanitized summaries;
- MCP read tools `list_parallel_tasks`, `get_parallel_task`, `list_parallel_candidates` and `get_target_promotion_state` expose sanitized summaries;
- MCP write tools `submit_parallel_task`, `start_parallel_task_execution`, `reconcile_parallel_task`, `promote_parallel_task`, `promote_next_parallel_candidate` and `promote_parallel_selection` require OAuth `dcp.write`.

Submitting a parallel task does not start Codex, managed clone, sprint/ping-pong, PR, merge, deploy or production-lane work. Starting execution is a separate explicit action. Reconciliation stores bounded changed-file and verifier summary metadata. Read summaries omit full task text and expose only operator-visible metadata such as task id, target id, source metadata, batch/release group, promotion epoch, run bindings, blockers and timestamps.

Promotion remains serial and policy-gated per target. Legacy parallel promotion can still fake-complete or reconcile state for admin smokes and cleanup, but ordinary operator flow does not use group selected promotion. Ordinary manual `Merge & Deploy` is single-run only: `merge_deploy_ready_run` accepts exactly one `ready_for_single_merge_deploy` run, re-verifies the same managed clone/worktree, then invokes the existing wb-core PR/merge/deploy/probe lane without applying a diff artifact in a separate promotion workspace. Backend requests with more than one selected id fail closed and create no group promotion state. Managed-clone `passed` means amber `Готово к выкладке`; green `В проде` is reserved for production-complete/deployed/public-verified state. Local/test profiles remain fail-closed or stubbed.

Before starting Codex, the hosted runner performs managed-workspace preflight with workspace existence/write checks, `pwd`, `git status --short --branch`, `rg --version`, `python3 --version`, `jq --version`, the configured `codex --version`, and a sanitized Codex auth check. It writes both `verifier/preflight/toolchain.json` and `artifacts/environment_parity.json`, including Codex/model/reasoning, `node`/`npm`/`corepack`/`pnpm`/`yarn`, Python/pip, git/gh, browser readiness, sanitized PATH, target id and base commit. A failed preflight returns a controlled blocker and does not start Codex. Before Codex starts, a prompt consistency gate validates structured route fields such as `execution_mode`, `production_allowed` and `merge_deploy_policy`; incidental prompt prose about deploy limitations is diagnostic text only and must not block a valid production-capable route. Hosted WebCore UI/browser tasks require the runtime-local package-manager baseline and Playwright/Chromium readiness; expired or missing Codex auth blocks with the terminal-only `codex login --device-auth` command. `gh` is required only when a verifier-passed run enters the explicit `wb-core` production lane; that lane writes a separate sanitized production-lane toolchain/auth preflight and blocks before target lock acquisition if GitHub CLI, runtime token, repo write permission, HTTPS git auth readiness or wb-core deploy SSH readiness is unavailable. The SSH gate is explicit to the hosted service user and uses strict host-key checking; it must not rely on an operator Mac SSH alias. The Codex command receives explicit runtime model/reasoning and sandbox settings from non-secret runtime config. In hosted mode, `danger-full-access` is allowed only as a Codex CLI compatibility mode for the isolated managed clone when Linux bubblewrap cannot create loopback networking; original target mutation, target commit/push/PR/merge/deploy and product runtime changes remain forbidden by DCP policy and verifier gates.

Codex observability stores two log layers: raw machine-readable events and a sanitized human terminal transcript. The transcript expands item lifecycle and command execution events into readable terminal-like lines with timestamps, command text, status, exit codes, duration and bounded output excerpts, while preserving the raw event log for diagnostics. Run-owned process supervision records `started_at`, `last_output_at`, `last_event_at`, elapsed time and process/session ids, applies wall and idle watchdog limits, and reconciles stale `running_codex` runs after service restart. Status readers compute a non-mutating reconciliation layer: raw run status stays visible, while `effective_status`/`effective_activity` shows cases like `control_error_codex_running`, `needs_verifier_after_control_error`, stale/operator-stopped, and handoff-present/verifier-missing. `codex_io_mode=event` is the default; PTY capture is only an explicit runtime experiment and diagnostics report why it is not active by default.

The real Codex prompt contract requires the final answer to start with exact first line `=== ДЛЯ КУРАТОРА ===` and to include `=== СЖАТАЯ ПРОВЕРКА ===`. Missing or misplaced handoff blocks are verifier failures with operator-readable reasons.

For this `dev-control-plane` repo only, the prompt contract now permits Codex-owned commit/push/PR/merge/delete-branch closure, including L3, after clean merge eligibility gates. The permission does not apply to `wb-core` or any target repo, production deploy, preview/staging deploy, direct target mutation, public routes or SSH/root actions.

CLI runner step selection follows the same runnable-step contract as the cockpit: no step id means first runnable step, and a missing requested step id falls back to the first runnable step with a warning instead of blocking before execution.

Verifier checks target runs for frozen spec, prompt/handoff presence, mandatory handoff blocks, forbidden path hits, `git diff --check`, Codex exit code, managed workspace ownership, and unchanged original target repo state.

For `wb-core` visible UI label, interface text, tab label and template text tasks, TaskSpec scope may expand only to bounded UI template paths. The current allowed expansion is `packages/adapters/templates/*.html`, with exact file additions such as `packages/adapters/templates/sheet_vitrina_v1_web_vitrina.html` when the operator explicitly names the visible `Витрина` label. This does not open broad package paths and does not relax forbidden paths such as `runtime/**`, `deploy/**`, `infra/**`, `artifacts/registry_upload_http_entrypoint/**`, `wb_core_docs_master/**` or `99_MANIFEST__DOCSET_VERSION.md`.

The GitHub closure eligibility helper checks repo identity, PR ownership, PR head SHA, clean working tree, required checks, diff checks, verifier status, forbidden paths/actions, protected derived docset paths, secrets scan state, handoff completeness, blocker absence and `NO_AUTO_MERGE`. Runner CLI and local server expose this as a decision-only gate; they do not execute hidden GitHub API mutation or store GitHub credentials.

Target PR, preview and approve/reject support is also decision-only in this MVP. It can produce plans for `wb-core` managed-clone output, preview URL shape and approval gates, but it does not push target branches, merge target PRs or deploy WebCore.

## Operator Dashboard Flow

The primary operator surface is a hosted-ready dark dashboard, not a chat UI:

1. `Панель` shows compact cards for service readiness, MCP auth/tools, GitHub auth, SSH deploy readiness, active runs and the `wb-core` production lock.
2. `Подключение` edits only non-secret Curator and Codex model/reasoning defaults. Secret setup, Codex login and OpenAI checks remain terminal-only.
3. `Мониторинг` links to `/runs/live`, which uses the same visual shell and continues to render sanitized terminal output, timelines, changed files, handoff/report details, selected `Merge & Deploy` controls and read-only archival sprint detail for historical sprint runs. Historical sprint parent/child cards are not promotion-selectable.
4. `Технические детали` keeps secondary compact diagnostics and sanitized JSON for debugging.

The legacy chat/curator/task-card API path remains available for compatibility and smokes. It is not visible in the primary UI/navigation. Fake curator mode is reserved for smoke/internal fallback through `DEV_CONTROL_PLANE_ENABLE_FAKE_CURATOR=1`. OpenAI curator mode must fail closed when env configuration is absent; smoke coverage verifies missing-key behavior without making a network call.

The hosted card draft path starts a short `/api/discussions/{id}/draft-task-spec-jobs` request and polls `/api/draft-task-spec-jobs/{id}` so nginx proxy timeouts do not break long deep-curator requests. Card draft responses include sanitized performance diagnostics: total duration, target validation duration, context build duration, curator duration, card validation duration, selected model/reasoning and token estimate. They must not include prompts with secrets, Authorization headers or raw provider bodies.

## Connections Setup

The `Подключение` tab reports Codex readiness and edits only non-secret Curator and Codex model/reasoning defaults without accepting secrets in the browser. OpenAI keys are configured and checked through terminal-only setup:

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
codex login
codex login --device-auth
```

The UI may run `codex --version` for install status, but it does not perform login, accept API keys, or start real Codex execution.

## OpenAI Diagnostics

OpenAI errors are mapped into safe operator-facing types: `missing_api_key`, `missing_model`, `auth_error`, `permission_error`, `model_not_found`, `rate_limited`, `timeout`, `provider_timeout`, `network_error`, `server_error`, `certificate_error`, `bad_request`, `invalid_json`, `unexpected_response_shape` and `unknown_error`. Deep hosted requests use a 180 second default timeout and bounded retry/backoff only for timeout, transient network, provider timeout and 5xx/server errors.

The connection test endpoint and manual probe read env credentials first and then the local secret file. They may return error type, HTTP status, request id, provider, model, short message and suggested next step. They must not return API keys, Authorization headers, raw tracebacks or full response bodies. Smoke coverage uses stubbed OpenAI responses and does not call the real OpenAI API.

## Safety Defaults

Execution from raw discussion is forbidden. Prompt/run generation requires a frozen spec. Fake executor is the UI and smoke path. Real Codex CLI execution requires explicit operator-controlled flags and task/target policy. Secrets must not appear in repo files, UI fields, API responses, state, prompts, logs, handoffs or summaries.
