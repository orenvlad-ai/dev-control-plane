# Development Control Plane

Development Control Plane is a local-first development control-plane prototype. It manages bounded task specs, prompt generation, fake execution runs, handoff artifacts and deterministic verification for target repositories.

Current status: local-first, loopback-only hosted-ready standalone project. It is not tied to any single product repo, and target projects are configurable inputs.

## Project Boundary

`dev-control-plane` is its own control-plane repo and project. It is not `wb-core`, not a SellerOS/product-plane runtime, and not a public deployment surface.

`wb-core` is the first external target profile. It remains a separate target repo and is read-only by default. Control-plane runs may read target context and may create managed clones/workspaces, but the original target repo working tree is not used as an execution workspace.

The UI safe flow and managed Codex flow do not commit, push, merge, deploy, open public routes, use SSH/root, or change product-plane routes. Real Codex execution is gated and runs only in a managed clone. Smoke tests use fakes/stubs and must not call the real OpenAI API or the real Codex executor.

Hosted control-plane design is tracked in `docs/architecture/02_hosted_control_plane_architecture.md`. The hosted server MVP runbook is `docs/runbooks/01_hosted_server_mvp.md`. These docs define the remote target, managed clone, target PR, preview/staging and approval workflow boundaries. Production apply/deploy is explicit and target-scoped: only the `wb-core` production lane may create a target PR, merge it and run the approved WebCore deploy runner after verifier, rollback and safety gates pass.

Secrets are stored outside this repo. OpenAI key setup uses the local terminal CLI:

```bash
python3 apps/dev_control_plane_setup.py openai
```

Do not commit `.env`, `secrets.json`, auth files, run ledgers containing sensitive data, or logs containing credentials.

## Run

Start the local server:

```bash
python3 apps/dev_control_plane_server.py --host 127.0.0.1 --port 8765
```

Default behavior is local-only. The server refuses non-`127.0.0.1` binds.

State defaults to `${DEV_CONTROL_PLANE_STATE_DIR}` when the env var is set, otherwise `/tmp/development-control-plane-state`. Runner/server paths are resolved through the unified state layout: `runs/` for per-run metadata and artifacts, `workspaces/` for managed workspaces, `artifacts/` for shared prompt artifacts, `logs/`, `verifier/`, and `collections/` for cockpit state.

Hosted server MVP mode uses the same loopback-only server with `DEV_CONTROL_PLANE_RUNTIME_PROFILE=hosted`, `DEV_CONTROL_PLANE_STATE_DIR=/opt/dev-control-plane-runtime/state` and deployment examples under `deploy/examples/`. The deploy runner is `apps/dev_control_plane_hosted_deploy.py`; live deploy is allowed only for `devcontrol.pro` on `89.191.226.88` after `print-plan`, `validate` and `deploy --dry-run` pass. The runner must not touch WebCore paths/services.

## Run Monitoring

The hosted operator surface includes a monitoring page at `GET /runs/live`. It remains behind the existing `devcontrol.pro` Basic Auth boundary and is not a public no-auth route. The main operator page links to it as `Мониторинг`. The monitor automatically lists active/recent runs and can open `GET /runs/<run_id>/watch` without manual run id entry.

Live monitor viewer APIs are read-only: `GET /api/runs/live`, `GET /api/runs/<run_id>/live`, `GET /api/runs/<run_id>/timeline`, `GET /api/runs/<run_id>/log-tail`, plus SSE streams at `GET /api/runs/stream` and `GET /api/runs/<run_id>/stream`. Timeline and terminal APIs support cursors/offsets so the browser appends new output without recreating the terminal DOM. Completed runs emit their final state and then move to low-frequency refresh. `/api/runs/live` sorts cards by effective recency descending: active items use last activity/update time, terminal items use finish time, then update/start/create fallback. The page exposes no shell input, no command prompt and no arbitrary command path. Clearing the terminal view is local-only and does not delete artifacts. Bounded operator controls are limited to `POST /api/runs/<run_id>/cancel` and `POST /api/runs/<run_id>/mark-stale`, both behind the same Basic Auth boundary; cancel may signal only a recorded run-owned Codex process group and preserves artifacts/workspaces.

Monitoring cards use an operator lifecycle mapping instead of raw status colors. Managed-clone `passed` / verifier-passed output is amber `Готово к выкладке`, not green production success; green is reserved for `production_complete` / deployed / public-verified outcomes. Cards show short human task titles first, with long `run_id`/`task_id` kept as secondary detail, plus compact start/finish/duration text, changed-file hints and promotion eligibility. Ordinary wb-core `Merge & Deploy` is single-run only for `ready_for_single_merge_deploy` runs through `merge_deploy_ready_run`; the UI may expose checkboxes, but once one item is selected other eligible items are disabled and backend requests with more than one id fail closed. Legacy selected-promotion groups may remain inspectable or cancellable for audit/hygiene, but they are not part of ordinary wb-core intake or deploy routing.

Each run may write sanitized monitor artifacts under its run directory: `logs/timeline.jsonl` for stage events, raw machine-readable Codex event logs, `logs/terminal.log` for terminal-like output, and a frozen prompt artifact that the `Промпт` panel displays before/during/after execution. The human terminal transcript expands common Codex events such as item start/completion and command execution into readable lines with timestamps, command text, status, exit code, duration and bounded output excerpts, while raw events remain available as machine artifacts. The sanitizer redacts credential markers and secret paths, strips unsafe terminal controls such as OSC/DCS/clipboard/title/hyperlink sequences, preserves only safe ANSI SGR color/style sequences, decodes escaped multiline human text, and hides common Codex JSONL metadata envelopes from the default terminal view. A vendored `xterm.js` asset is not present in this repo and external CDN loading is prohibited, so the current UI uses a small local ANSI SGR renderer instead of adding an unpinned browser terminal dependency.

Hosted Codex observability records run-owned process state under the run logs directory, including `started_at`, activity timestamps, process ids/session ids, elapsed time and stale assessment. Watchdog limits cover maximum wall time and no-output/no-event idle time; timeout handling kills only the run-owned Codex process group, marks the run with a controlled stale/blocker status, and preserves partial artifacts/workspaces. On service restart, `running_codex` runs are reconciled as live, `stale_timeout` or `stale_lost_process`. Live/MCP status also reports `effective_status`, `effective_activity`, `is_inconsistent`, and `control_plane_observer_status` so a DevControl observer failure cannot hide a still-active Codex process or a handoff that exists before verifier ran. `get_status` reports sanitized Codex observability readiness, watchdog limits and the effective IO mode; `codex_io_mode=event` remains the safe default, with PTY capture only as an explicit runtime config experiment.

Before Codex starts, the runner applies a prompt consistency gate to structured route fields, not incidental raw prompt wording. Production decisions come from fields such as `execution_mode`, `production_allowed` and `merge_deploy_policy`; prose that describes deploy limitations does not block a valid production-capable route. Structured contradictions such as `production_allowed=false` with production-lane execution still return a controlled blocker before Codex starts.

## MCP Stage 1 Bridge

The hosted server exposes a bounded MCP backend at `POST /mcp` using streamable HTTP. This is the Stage 1 interface bridge for the current ChatGPT Project: ChatGPT remains the UI, while `dev-control-plane` remains the backend/orchestrator.

Implemented MCP tools cover sanitized status, targets, lock state, active runs, run status/report/artifacts, run timeline/log tail, rollback plan, read-only `search`/`fetch`, OAuth-gated read-only target documentation tools, the normal direct `wb-core` auto-task route, explicit `wb-core` operator-parity tasks, explicit managed-clone-only starts for non-production review work, explicit `wb-core` production-lane starts, and OAuth-gated post-merge deploy resume for already merged blocked `wb-core` production-lane runs. Start/resume responses include `live_url` and `watch_url` for the hosted live monitor. There is no arbitrary shell tool and no tool that accepts a raw command.

ChatGPT Developer Mode uses the public `/mcp` endpoint in `mixed_noauth_read_oauth_write` mode. `initialize`, `tools/list` and read-only tool calls are available without Basic Auth so ChatGPT can connect. Public discovery exposes only read-only tools and marks them with `readOnlyHint=true` plus `noauth` metadata. Write tools are hidden from public no-auth discovery and direct unauthenticated write calls return a controlled `denied` result.

Target documentation reads use the same authenticated MCP session boundary as write exposure, but remain read-only and are annotated with `readOnlyHint=true`. Public no-auth discovery hides `list_target_docs`, `search_target_docs`, `get_target_doc` and the compatibility fallback `read_target_docs`; direct unauthenticated calls are denied. These tools read only allowlisted target docs (`README.md`, `AGENTS.md`, `docs/architecture/**`, `docs/modules/**`, `migration/**`) from a cached git snapshot under control-plane state; they reject traversal, forbidden paths, secret/env files and oversized reads.

Write tools are ChatGPT-ready only through the OAuth authorization-code + PKCE path with `dcp.write` scope. The server publishes OAuth protected-resource and authorization-server metadata, supports public dynamic client registration, stores only hashed grants in durable runtime state collections, and keeps the consent step behind the hosted Basic Auth user gate. Status payloads expose sanitized readiness and reconnect diagnostics such as token expired, missing scope, grant/client not found and resource metadata mismatch, without returning tokens, Authorization headers, cookies or provider bodies. The token exchange is protocol-required output only; OAuth grants, bearer values and Authorization headers must not be copied into docs, PR bodies, logs or handoffs. ChatGPT connector/link-cache `404 Link not found` or reauth churn can be diagnosed from DevControl status, but the connector cache itself is external to DevControl.

`start_wb_core_auto_task` is the canonical write tool for ordinary ChatGPT Project wb-core/WebCore tasks. ChatGPT supplies only the bounded task text; DevControl decides the route from structured server state. If no production-capable wb-core work or production lock is active, the task is routed as `wb_core_exclusive_auto_production`: one clean managed clone/Codex run -> verifier/checks on that same clone -> existing guarded wb-core PR/merge/deploy/probe lane -> `production_complete`. The verified managed clone/worktree is the ordinary production source of truth; `diff.patch` remains audit evidence and is not re-applied as transport. If a production-capable run, active auto-production intent or production lock is active, ordinary intake returns `wb_core_direct_auto_blocked` before creating a run, task spec, workspace or Codex process. `wb_core_prepare_only` is legacy/explicit-review state only and is not an ordinary fallback. Uncertain state also blocks fail-closed. It must not substitute `start_sprint`, `start_managed_clone_run`, the sprint bridge or a managed-clone-only fallback for ordinary WebCore work.

`start_wb_core_operator_parity_task` is the explicit operator-parity lane for wb-core tasks that need real host context: runtime/archive/DB/browser/session/collector data, deploy-path diagnostics, or other evidence that a sterile managed clone cannot see. It uses route `wb_core_operator_parity_task` and starts only after `get_operator_parity_status` reports the required capability matrix ready: persistent operator worktree, Codex auth/toolchain, GitHub/SSH readiness, runtime state and DB/source snapshot readability, browser/session readiness, collector/download runners, deploy-gate readiness, secret broker, redaction and artifact quarantine. If any required capability is missing, DevControl returns a blocker before Codex starts. The lane writes sanitized preflight, runtime broker export, logs and handoff artifacts; secret-like artifacts are redacted and quarantined. It does not open PRs, merge, deploy, use sprint/ping-pong, or act as an ordinary auto-task fallback.

`start_sprint`, the sprint orchestrator, curator-to-Codex ping-pong, parent/child task decomposition and the `DEVCONTROL_START_SPRINT_V1` compatibility bridge are frozen for ordinary ChatGPT Project operator flow. `start_sprint` is hidden from operator MCP discovery; if called directly in a non-internal runtime it returns `start_sprint is frozen for operator flow; use direct wb-core auto Codex task` and creates no parent or child run. The bridge marker on `start_managed_clone_run` is also frozen and returns the same blocker instead of routing to sprint or managed-clone fallback. Historical sprint artifacts may remain readable as archival run data only.

## Parallel Task Ledger MVP

The first parallel orchestration layer is a machine-readable ledger at `state/collections/parallel_task_ledger.json`. The ledger accepts tasks from any source/chat into a shared `target_id + promotion_epoch` scope, with optional `batch_id`, optional `release_group` and an `idempotency_key` for duplicate-safe intake.

MVP task statuses are `submitted`, `managed_run_running`, `verifier_passed`, `promotion_queued`, `auto_promoting_first`, `production_lane_running`, `production_complete`, `frozen_base_stale`, `refresh_required`, `ready_for_separate_deploy`, `partially_deployed`, `blocked` and `failed`. Helper transitions can submit a task, bind a managed run id, mark verifier passed, select the first verifier-passed candidate, queue or explicitly mark the first candidate as `auto_promoting_first`, bind production-lane state, and freeze same-target/same-epoch siblings after `production_complete`.

The first-finished promotion path is fail-closed: a candidate may become `auto_promoting_first` only when the caller passes explicit auto-promote policy. After one candidate reaches `production_complete`, other tasks in the same target/epoch become `frozen_base_stale` or `refresh_required`; frozen candidates cannot be promoted without a future refresh/rebase flow. The parallel-flow layer explicitly freezes ping-pong/server-side curator use with `parallel_ping_pong_enabled=false`; it does not call `start_sprint` or the sprint bridge.

The runtime surface starts state-only and is visible in the operator dashboard. Local/server API routes are `POST /api/parallel-tasks`, `GET /api/parallel-tasks`, `GET /api/parallel-tasks/{id}`, `GET /api/parallel-targets/{id}/promotion-candidates`, `GET /api/parallel-targets/{id}/promotion-state`, plus explicit execution/reconcile/promotion actions. MCP exposes sanitized read tools `list_parallel_tasks`, `get_parallel_task`, `list_parallel_candidates`, `get_target_promotion_state` and OAuth-gated write tools for submit/start/reconcile/promote. Submitting a parallel task records ledger state only; it does not start Codex, ping-pong, PR, merge, deploy or production-lane work.

The execution coordinator foundation remains available for legacy/admin state management, but it is no longer part of ordinary `wb-core` task routing. `start_parallel_task_execution` defaults to fake/state-only binding and never calls `start_sprint`, PR, merge, deploy or production-lane work. `reconcile_parallel_task` can still mark ledger tasks `verifier_passed`, `blocked` or `failed`, and cleanup tools can archive old selected-promotion state. Ordinary manual `Merge & Deploy` is single-run only through `merge_deploy_ready_run`, which accepts exactly one verifier-passed `ready_for_single_merge_deploy` run, re-verifies the same managed clone, then uses the guarded wb-core PR/merge/deploy/probe lane. Group selected Merge & Deploy is disabled for the ordinary operator flow; backend requests with more than one selected id fail closed and create no promotion group.

Legacy MCP bearer-token auth remains only for bounded protocol/API smokes and direct controlled calls. The token is configured outside the repo through terminal setup and must not be treated as the ChatGPT UI auth strategy:

```bash
python3 apps/dev_control_plane_setup.py mcp-token
# or generate once, record it through an approved secret channel, then rotate/delete as needed
python3 apps/dev_control_plane_setup.py generate-mcp-token
python3 apps/dev_control_plane_setup.py delete-mcp-token
```

Current OpenAI docs for ChatGPT Developer Mode document OAuth, No Authentication and Mixed Authentication for app setup. This repo uses Mixed Authentication semantics: no-auth public read tools plus OAuth-gated authenticated tools. Do not expose write tools or target-docs tools as unauthenticated or use static bearer as the ChatGPT UI workaround.

## GitHub Closure

Codex may perform commit, push, PR creation, merge and branch deletion for its own PRs in `orenvlad-ai/dev-control-plane`, including L3 governance tasks, only after clean gates: current-task or current `codex/*` branch ownership, clean working tree, open PR with expected head SHA, required smokes/checks passed, `git diff --check`, `git diff --cached --check`, verifier passed, no forbidden paths/actions, no protected derived docset changes unless explicitly scoped, clean secrets scan, complete handoff, no blocker and no `NO_AUTO_MERGE`.

The runner and local server expose a decision-only closure gate through `github-closure-decision` and `POST /api/github-closure/decision`. They return `allowed/denied/blockers`, `merge_allowed` and `delete_branch_allowed`; they do not execute GitHub API mutations or store GitHub tokens.

This self-closure policy is repo-local. It does not authorize PR merge/apply in `wb-core` or any target repo, production deploy, preview/staging deploy, public routes, SSH/root, direct target mutation, or bypassing verifier/checks. Target production work needs the separate explicit `wb-core` production lane.

Target repo workflow support has two layers. The general target PR/preview/approval workflow remains decision-only. The explicit `wb-core` production lane is the working apply/deploy mode for production-capable `wb-core` tasks: it consumes verifier-passed managed-clone output and can, only when requested through the production runner, create a `devcp/*` branch, commit with Russian metadata, open a required PR body, merge the PR after head-SHA gates, create a rollback/app backup, run the approved WebCore deploy runner, run post-deploy probes, and publish a report. It checks GitHub CLI availability, sanitized hosted GitHub auth readiness and sanitized wb-core deploy SSH readiness before acquiring the target production lock, then uses a single-target production lock so two `wb-core` production-lane runs cannot overlap. It still forbids direct push to `main`, deploy without merged PR, deploy with failed verifier/forbidden paths/secrets, external WB live writes, DB migrations and derived-pack changes by default.

## Smokes

```bash
python3 apps/dev_control_plane_smoke.py
python3 apps/dev_control_plane_cli_smoke.py
python3 apps/dev_control_plane_server_smoke.py
python3 apps/dev_control_plane_runner_smoke.py
python3 apps/dev_control_plane_state_layout_smoke.py
python3 apps/dev_control_plane_hosted_server_smoke.py
python3 apps/dev_control_plane_hosted_deploy_smoke.py
python3 apps/dev_control_plane_github_closure_smoke.py
python3 apps/dev_control_plane_github_closure_workflow_smoke.py
python3 apps/dev_control_plane_github_auth_smoke.py
python3 apps/dev_control_plane_ssh_deploy_smoke.py
python3 apps/dev_control_plane_target_production_smoke.py
python3 apps/dev_control_plane_mcp_smoke.py
python3 apps/dev_control_plane_mcp_oauth_smoke.py
python3 apps/dev_control_plane_mcp_public_discovery_smoke.py
python3 apps/dev_control_plane_wb_core_auto_task_smoke.py
python3 apps/dev_control_plane_mcp_sprint_bridge_smoke.py
python3 apps/dev_control_plane_mcp_start_sprint_smoke.py
python3 apps/dev_control_plane_sprint_orchestrator_smoke.py
python3 apps/dev_control_plane_live_monitor_smoke.py
python3 apps/dev_control_plane_ai_smoke.py
python3 apps/dev_control_plane_target_smoke.py
python3 apps/dev_control_plane_target_remote_source_smoke.py
python3 apps/dev_control_plane_target_workflow_smoke.py
python3 apps/dev_control_plane_practical_cockpit_smoke.py
python3 apps/dev_control_plane_real_codex_gate_smoke.py
python3 apps/dev_control_plane_real_codex_ui_smoke.py
python3 apps/dev_control_plane_run_timeline_smoke.py
python3 apps/dev_control_plane_openai_diagnostics_smoke.py
python3 apps/dev_control_plane_secrets_smoke.py
python3 apps/dev_control_plane_task_flow_smoke.py
python3 apps/dev_control_plane_parallel_ledger_smoke.py
python3 apps/dev_control_plane_parallel_api_mcp_smoke.py
python3 apps/dev_control_plane_parallel_coordinator_smoke.py
python3 apps/dev_control_plane_parallel_dashboard_smoke.py
```

## Target Projects

Target projects are external repositories described by local adapter metadata under `configs/target_projects/`. The first checked-in adapter is `wb-core`; it keeps the local Mac path for local mode and also defines remote managed-clone source `https://github.com/orenvlad-ai/wb-core.git` on `main`. Hosted mode does not require `/Users/ovlmacbook/Projects/wb-core`.

Adapter config is not source of truth. Source-of-truth docs, code and policies stay in the target repo. The control-plane only reads configured source paths and merges target defaults such as forbidden paths/actions and required smokes into draft task specs.

Source-of-truth paths are context, not automatic forbidden paths. For example, `README.md`, `docs/architecture/`, `docs/modules/`, and `migration/` should not be forbidden just because they are canonical source paths.

Inspect targets locally:

```bash
python3 apps/dev_control_plane_target_cli.py list-targets --config-dir configs/target_projects
python3 apps/dev_control_plane_target_cli.py validate-target --config configs/target_projects/wb_core.json
python3 apps/dev_control_plane_target_cli.py snapshot-target --config configs/target_projects/wb_core.json --output /tmp/wb-core-context-snapshot.json
```

Target validation/snapshot flows are read-only. Managed-clone execution itself still does not commit, push, merge or deploy target code. Production mutation is available only through the explicit `wb-core` production lane after a verifier-passed run and rollback plan.

## Operator Dashboard Flow

The primary operator page is a unified dark dashboard shell:

1. `Панель` shows compact status cards for the DevControl service, MCP auth/tools, GitHub auth, SSH deploy readiness, active runs and the `wb-core` production lock.
2. `Подключение` exposes only non-secret Curator and Codex settings: model, reasoning depth and save.
3. `Мониторинг` opens `/runs/live` inside the same visual shell and includes sanitized run/task cards, prompt/log/artifact panels, single-run `Merge & Deploy`, legacy/admin group state where still needed for audit, and read-only archival sprint detail when historical sprint runs exist. Historical sprint parent/child cards are not promotion-selectable.
4. `Технические детали` keeps compact advanced diagnostics and sanitized JSON secondary to the dashboard cards.

Legacy chat/curator/task-card backend APIs remain present for compatibility and smoke coverage, but the visible primary UI no longer exposes the old chat block. ChatGPT MCP ordinary `wb-core` intake is `start_wb_core_auto_task` only: an idle target receives one direct production-capable run, while a busy target receives a fail-closed blocker before any second run/workspace/Codex process is created. Managed-clone-only and prepare-only tools are not a fallback for WebCore tasks that expect merge/deploy.

Runnable specs are normalized with at least one sprint step. If no step id is supplied, safe fake-flow uses the first runnable step instead of assuming `step-001`.

The legacy chat flow remains a backend/API compatibility path rather than the primary operator screen.

## Optional OpenAI Intake

The AI curator intake supports a fake provider for smokes and an optional OpenAI provider for local use.

Recommended one-time local setup:

```bash
python3 apps/dev_control_plane_setup.py openai
```

The setup command asks for the API key with hidden terminal input and stores it outside this repo at `~/.dev-control-plane/secrets.json`. The secret directory is created with restricted permissions where the OS supports it, and the secret file is written with mode `0600`.

Check local setup:

```bash
python3 apps/dev_control_plane_setup.py status
```

Environment variables still have priority over the local secret file:

```bash
export OPENAI_API_KEY=...
export CURATOR_COCKPIT_OPENAI_MODEL=...
export CURATOR_COCKPIT_OPENAI_REASONING_EFFORT=xhigh
export DEV_CONTROL_PLANE_OPENAI_TIMEOUT_SECONDS=180
export DEV_CONTROL_PLANE_OPENAI_RETRY_COUNT=2
export DEV_CONTROL_PLANE_OPENAI_RETRY_BACKOFF_SECONDS=2
```

Delete stored OpenAI credentials:

```bash
python3 apps/dev_control_plane_setup.py delete-openai
```

Do not enter API keys in the UI. Do not commit `.env` files, API keys, auth files, local secret stores, logs containing secrets, or run ledgers with sensitive content. The cockpit, status API and probe never return the API key.

Use the terminal probe below for OpenAI checks. The primary `Подключение` UI exposes only non-secret curator model/reasoning selectors, not OpenAI keys or an OpenAI test button.

The OpenAI client uses the Responses API with sanitized model config: `{"model": "...", "input": "...", "reasoning": {"effort": "xhigh"}}` when reasoning effort is configured. Deep hosted curator requests default to `DEV_CONTROL_PLANE_OPENAI_TIMEOUT_SECONDS=180`, `DEV_CONTROL_PLANE_OPENAI_RETRY_COUNT=2`, and `DEV_CONTROL_PLANE_OPENAI_RETRY_BACKOFF_SECONDS=2`. Retries are bounded and apply only to timeout, transient network and 5xx/provider-timeout classes, not auth/model/bad-request failures. If the local Python install cannot find a CA bundle, set `DEV_CONTROL_PLANE_OPENAI_CA_BUNDLE=/path/to/cert.pem`.

Hosted runtime model settings are non-secret config and are stored outside the repo, normally under `/opt/dev-control-plane-runtime/config/runtime_config.json` when `DEV_CONTROL_PLANE_STATE_DIR=/opt/dev-control-plane-runtime/state`. The visible `Подключение` tab can switch Curator and Codex model/reasoning defaults. It must not accept API keys, OAuth grants, GitHub tokens, SSH keys or Codex login material. Model profiles/presets are deprecated and ignored so they cannot override explicit saved settings. Defaults remain `gpt-5.5` + `xhigh`.

Manual terminal probe:

```bash
python3 apps/dev_control_plane_openai_probe.py
```

The probe reads env vars first, then the local secret file, prints sanitized JSON and exits `0` only when OpenAI responds successfully. Smoke tests cover diagnostics with stubs and do not call the real OpenAI API.

## Codex CLI Setup

Codex CLI auth is terminal-only:

```bash
codex login
codex login --device-auth
```

Use `codex login --device-auth` for hosted/headless service-user setup. The cockpit shows whether `codex` is installed/authenticated and never performs Codex login or asks for Codex credentials.

Hosted Codex CLI setup is governed by `docs/runbooks/01_hosted_server_mvp.md`: install the reviewed npm package layout under `/opt/dev-control-plane-runtime/tools/codex`, keep `auth.json` outside the repo under `/opt/dev-control-plane-runtime/.codex`, keep model defaults in `/opt/dev-control-plane-runtime/.codex/config.toml`, and verify only `codex --version` / `codex login status`. Do not run a real Codex task as part of install/auth setup.

Hosted Codex runs pass the selected model/reasoning and an explicit sandbox mode to `codex exec`. When the hosted Linux bubblewrap `workspace-write` sandbox cannot create its loopback namespace, the runtime may use `danger-full-access` only inside the managed clone; DCP gates still enforce managed workspace ownership, forbidden paths/actions, hosted toolchain preflight, original-target unchanged checks, and no target commit/push/PR/deploy. The preflight writes sanitized toolchain diagnostics plus `artifacts/environment_parity.json`, checks Codex authentication before launch, and treats hosted `node`, `npm`, `corepack`, `pnpm`, `yarn` and browser-smoke readiness as the WebCore UI baseline. The explicit `wb-core` production lane runs a second sanitized toolchain/auth preflight before target lock/commit/push/PR/merge/deploy and requires `gh`, a runtime GitHub token outside the repo, write access to `orenvlad-ai/wb-core`, HTTPS git auth readiness for push, and a configured service-user SSH deploy target that passes `ssh -o BatchMode=yes` with strict host-key checking.

Operator-parity runs are a separate hosted lane, not a production apply path. They use the configured persistent wb-core operator worktree under state/runtime policy and expose a sanitized capability matrix through `get_status`, `get_target_status` and `get_operator_parity_status`. Runtime/archive access is read-only by default through allowlisted paths or a sanitized broker export. Any production follow-up from a parity investigation must enter the normal guarded wb-core PR/merge/deploy lane.

## Execution Boundary

The fake executor is the default safe check. Real Codex execution is available through the runner CLI and MCP managed-clone tools; legacy compatibility API paths remain gated and use a managed clone under the selected state directory. They do not mutate the original target repo path. Target commit, push, merge and production deploy may happen only as a separate explicit `wb-core` production-lane step after verifier passed, target lock acquisition and all PR/deploy gates.

The managed-Codex path has no arbitrary shell command field and no Codex command template input. It starts only the built-in managed-clone Codex executor, returns a job/run id immediately, exposes job status (`queued`, `preparing`, `running_codex`, `verifying`, `passed`, `failed`, `blocked`), and stores prompt, handoff, diff, log and verifier artifacts for review.

The live monitor shows terminal-like output and timeline events from job lifecycle, Codex JSONL log events when available, changed files, and verifier checks. Raw Codex logs stay behind sanitized artifact APIs and `Технические детали`.

Codex final handoff must start with the exact first line `=== ДЛЯ КУРАТОРА ===` and must include `=== СЖАТАЯ ПРОВЕРКА ===`. If the report is missing a required block, the verifier returns an explicit handoff contract error naming the missing header.

Safe managed-clone tasks do not require a human gate to confirm the generated workspace path. Real Codex authorization is enforced by the runner CLI flag, not by adding a repeated human gate to every TaskSpec.

The runner CLI also selects the first runnable sprint step when no `--step-id` is supplied, and falls back to that first step with a warning when a supplied step id is absent.

Operator-controlled example:

```bash
python3 apps/dev_control_plane_runner.py run-codex-cli \
  --target-config configs/target_projects/wb_core.json \
  --task-spec /path/to/frozen_task_spec.json \
  --step-id step-001 \
  --state-dir /tmp/dev-control-plane-runs \
  --allow-real-codex
```

The smoke suite uses a fake Codex binary, not the real Codex CLI. Command output is captured as local artifacts: prompt, handoff, diff and logs.

No production route, deploy lane, public host, SSH/root action, target repo auto-merge, or product-plane integration is part of this prototype.
