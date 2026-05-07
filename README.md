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

## MCP Stage 1 Bridge

The hosted server exposes a bounded MCP backend at `POST /mcp` using streamable HTTP. This is the Stage 1 interface bridge for the current ChatGPT Project: ChatGPT remains the UI, while `dev-control-plane` remains the backend/orchestrator.

Implemented MCP tools cover sanitized status, targets, lock state, active runs, run status/report/artifacts, rollback plan, read-only `search`/`fetch`, managed-clone-only starts and explicit `wb-core` production-lane starts. There is no arbitrary shell tool and no tool that accepts a raw command.

ChatGPT Developer Mode uses the public `/mcp` endpoint in `mixed_noauth_read_oauth_write` mode. `initialize`, `tools/list` and read-only tool calls are available without Basic Auth so ChatGPT can connect. Public discovery exposes only read-only tools and marks them with `readOnlyHint=true` plus `noauth` metadata. Write tools are hidden from public no-auth discovery and direct unauthenticated write calls return a controlled `denied` result.

Write tools are ChatGPT-ready only through the OAuth authorization-code + PKCE path with `dcp.write` scope. The server publishes OAuth protected-resource and authorization-server metadata, supports public dynamic client registration, stores only hashed grants in runtime state, and keeps the consent step behind the hosted Basic Auth user gate. The token exchange is protocol-required output only; OAuth grants, bearer values and Authorization headers must not be copied into docs, PR bodies, logs or handoffs.

Legacy MCP bearer-token auth remains only for bounded protocol/API smokes and direct controlled calls. The token is configured outside the repo through terminal setup and must not be treated as the ChatGPT UI auth strategy:

```bash
python3 apps/dev_control_plane_setup.py mcp-token
# or generate once, record it through an approved secret channel, then rotate/delete as needed
python3 apps/dev_control_plane_setup.py generate-mcp-token
python3 apps/dev_control_plane_setup.py delete-mcp-token
```

Current OpenAI docs for ChatGPT Developer Mode document OAuth, No Authentication and Mixed Authentication for app setup. This repo uses Mixed Authentication semantics: no-auth read tools plus OAuth-gated write tools. Do not expose write tools as unauthenticated or use static bearer as the ChatGPT UI workaround.

## GitHub Closure

Codex may perform commit, push, PR creation, merge and branch deletion for its own PRs in `orenvlad-ai/dev-control-plane`, including L3 governance tasks, only after clean gates: current-task or current `codex/*` branch ownership, clean working tree, open PR with expected head SHA, required smokes/checks passed, `git diff --check`, `git diff --cached --check`, verifier passed, no forbidden paths/actions, no protected derived docset changes unless explicitly scoped, clean secrets scan, complete handoff, no blocker and no `NO_AUTO_MERGE`.

The runner and local server expose a decision-only closure gate through `github-closure-decision` and `POST /api/github-closure/decision`. They return `allowed/denied/blockers`, `merge_allowed` and `delete_branch_allowed`; they do not execute GitHub API mutations or store GitHub tokens.

This self-closure policy is repo-local. It does not authorize PR merge/apply in `wb-core` or any target repo, production deploy, preview/staging deploy, public routes, SSH/root, direct target mutation, or bypassing verifier/checks. Target production work needs the separate explicit `wb-core` production lane.

Target repo workflow support has two layers. The general target PR/preview/approval workflow remains decision-only. The explicit `wb-core` production lane is the working apply/deploy mode for production-capable `wb-core` tasks: it consumes verifier-passed managed-clone output and can, only when requested through the production runner, create a `devcp/*` branch, commit with Russian metadata, open a required PR body, merge the PR after head-SHA gates, create a rollback/app backup, run the approved WebCore deploy runner, run post-deploy probes, and publish a report. It uses a single-target production lock so two `wb-core` production-lane runs cannot overlap. It still forbids direct push to `main`, deploy without merged PR, deploy with failed verifier/forbidden paths/secrets, external WB live writes, DB migrations and derived-pack changes by default.

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
python3 apps/dev_control_plane_target_production_smoke.py
python3 apps/dev_control_plane_mcp_smoke.py
python3 apps/dev_control_plane_mcp_oauth_smoke.py
python3 apps/dev_control_plane_mcp_public_discovery_smoke.py
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

## Practical Cockpit Flow

The local cockpit is a Russian chat-first operator UI:

1. Start the server and open the local page.
2. Select a target project, for example `wb-core`.
3. Write the task in `Чат`.
4. Use `Подготовить задачу`; for simple L1/L2 repo-only tasks this drafts and freezes the card when validation passes.
5. Review the human-readable `Карточка задачи`.
6. Use `Запустить Codex безопасно` for an operator-confirmed real Codex run in a managed clone.
7. Watch the scrollable `Ход выполнения` block for managed-clone/Codex/verifier progress.
8. Review `Результат выполнения`: changed files, changed-file count, target unchanged status, verifier status, `git diff --check`, next action, and compact diff/handoff previews.
9. Raw JSON, full prompt, handoff, diff, logs and paths are under `Технические детали`.

The operator screen does not expose a fake/OpenAI selector. OpenAI curator mode is the normal UI path and fails closed when env configuration is missing. Fake curator remains available only for smoke/internal fallback with `DEV_CONTROL_PLANE_ENABLE_FAKE_CURATOR=1`. `Тестовый прогон без Codex` is an advanced optional action that uses only the fake executor and is usually not required before a standard managed-clone run. `Запустить Codex безопасно` starts real Codex only after operator confirmation and only in a managed clone; it does not mutate the original target repo and does not commit, push, merge or deploy. The separate production lane starts only after that managed-clone run has passed verifier gates.

Runnable specs are normalized with at least one sprint step. If no step id is supplied, safe fake-flow uses the first runnable step instead of assuming `step-001`.

Chat messages are optimistic: the operator message appears immediately, the UI shows `Куратор думает...`, and duplicate sends are disabled while the request is pending. Main actions show loading states such as `Готовлю задачу...`, `Формирую карточку...`, `Фиксирую задачу...`, `Проверяю сценарий...`, `Запускаю Codex...`, and `Проверяю OpenAI...`.

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

Use the `Подключения` tab and its `Проверить OpenAI` button to run a minimal local connection test. The result is sanitized: it may include `error_type`, HTTP status, request id, model, short message and a suggested next step, but never the API key or Authorization header.

The OpenAI client uses the Responses API with sanitized model config: `{"model": "...", "input": "...", "reasoning": {"effort": "xhigh"}}` when reasoning effort is configured. Deep hosted curator requests default to `DEV_CONTROL_PLANE_OPENAI_TIMEOUT_SECONDS=180`, `DEV_CONTROL_PLANE_OPENAI_RETRY_COUNT=2`, and `DEV_CONTROL_PLANE_OPENAI_RETRY_BACKOFF_SECONDS=2`. Retries are bounded and apply only to timeout, transient network and 5xx/provider-timeout classes, not auth/model/bad-request failures. If the local Python install cannot find a CA bundle, set `DEV_CONTROL_PLANE_OPENAI_CA_BUNDLE=/path/to/cert.pem`.

Hosted runtime model settings are non-secret config and are stored outside the repo, normally under `/opt/dev-control-plane-runtime/config/runtime_config.json` when `DEV_CONTROL_PLANE_STATE_DIR=/opt/dev-control-plane-runtime/state`. The `Подключения` tab can switch only explicit values: OpenAI curator model/reasoning, Codex model/reasoning and Codex sandbox. Model profiles/presets are deprecated and ignored so they cannot override explicit saved settings. Defaults remain `gpt-5.5` + `xhigh`.

Manual terminal probe:

```bash
python3 apps/dev_control_plane_openai_probe.py
```

The probe reads env vars first, then the local secret file, prints sanitized JSON and exits `0` only when OpenAI responds successfully. Smoke tests cover diagnostics with stubs and do not call the real OpenAI API.

## Codex CLI Setup

Codex CLI auth is terminal-only:

```bash
codex --login
```

Choose `Sign in with ChatGPT`. The cockpit shows whether `codex` is installed and reports that auth is checked at the first Codex run. The UI does not perform Codex login and never asks for Codex credentials.

Hosted Codex CLI setup is governed by `docs/runbooks/01_hosted_server_mvp.md`: install the reviewed npm package layout under `/opt/dev-control-plane-runtime/tools/codex`, keep `auth.json` outside the repo under `/opt/dev-control-plane-runtime/.codex`, keep model defaults in `/opt/dev-control-plane-runtime/.codex/config.toml`, and verify only `codex --version` / `codex login status`. Do not run a real Codex task as part of install/auth setup.

Hosted Codex runs pass the selected model/reasoning and an explicit sandbox mode to `codex exec`. When the hosted Linux bubblewrap `workspace-write` sandbox cannot create its loopback namespace, the runtime may use `danger-full-access` only inside the managed clone; DCP gates still enforce managed workspace ownership, forbidden paths/actions, hosted toolchain preflight, original-target unchanged checks, and no target commit/push/PR/deploy. The preflight writes sanitized toolchain diagnostics and checks required runtime tools such as `git`, `rg`, `python3`, `jq` and the configured Codex binary before Codex starts.

## Execution Boundary

The fake executor is the default safe check. Real Codex execution is available through the runner CLI and through the local UI's `Запустить Codex безопасно` button, but both paths are gated and use a managed clone under the selected state directory. They do not mutate the original target repo path. Target commit, push, merge and production deploy may happen only as a separate explicit `wb-core` production-lane step after verifier passed, target lock acquisition and all PR/deploy gates.

The UI real-Codex path has no arbitrary shell command field and no Codex command template input. It starts only the built-in managed-clone Codex executor, returns a job id immediately, polls job status (`queued`, `preparing`, `running_codex`, `verifying`, `passed`, `failed`, `blocked`), and stores prompt, handoff, diff, log and verifier artifacts for review.

The cockpit shows a compact scrollable `Ход выполнения` timeline built from job lifecycle, Codex JSONL log events when available, changed files, and verifier checks. Raw Codex logs stay under `Технические детали`.

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
