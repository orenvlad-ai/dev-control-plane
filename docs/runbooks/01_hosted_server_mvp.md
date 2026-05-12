# Hosted Server MVP Runbook

## Purpose

This runbook describes a safe hosted MVP installation model for `dev-control-plane` as a standalone control-plane service. It is an operator procedure, not an automated deploy script. Do not run SSH, root/sudo, live deploy, public-route or reverse-proxy changes from generic Codex tasks.

## Current Norm

- Active server: `89.191.226.88`.
- SSH alias: `wb-core-eu-root`.
- Public domain: `devcontrol.pro`.
- Public www domain: `www.devcontrol.pro`.
- App path: `/opt/dev-control-plane-runtime/app`.
- State root: `/opt/dev-control-plane-runtime/state`.
- Env file: `/opt/dev-control-plane-runtime/.env`.
- Service: `dev-control-plane.service`.
- Runtime profile: `DEV_CONTROL_PLANE_RUNTIME_PROFILE=hosted`.
- Application bind: `127.0.0.1:8770` only.
- Reverse proxy, HTTPS and auth use a separate nginx site, never `/etc/nginx/sites-enabled/wb-ai`.
- Managed workspaces remain under the state root, normally `/opt/dev-control-plane-runtime/state/workspaces/`.
- Target repos remain external and read-only by default.
- Secrets stay outside the repo and must not be entered into browser UI, committed, logged or included in project packs.

## Directory Layout

```text
/opt/dev-control-plane-runtime/app/
  apps/
  src/dev_control_plane/
  configs/target_projects/
  deploy/examples/

/opt/dev-control-plane-runtime/state/
  collections/
  artifacts/
  runs/
  workspaces/
  logs/
  verifier/

/opt/dev-control-plane-runtime/
  .env
  .codex/
    auth.json
  tools/
    codex/

/etc/nginx/sites-available/dev-control-plane
/etc/nginx/sites-enabled/dev-control-plane
```

The server uses `DEV_CONTROL_PLANE_STATE_DIR` and the unified state layout resolver. Runtime state must not be written into tracked repo paths.

## Installation Outline

These commands are examples for a human operator. They are not executed by this repository and must be adapted to the actual host policy.

1. Create a dedicated system user such as `dev-control-plane`.
2. Clone or update the repo under `/opt/dev-control-plane-runtime/app`.
3. Use the host Python runtime or a reviewed virtual environment.
4. Install runtime dependencies required by the repo.
5. Create `/opt/dev-control-plane-runtime/state` owned by the service user.
6. Create `/opt/dev-control-plane-runtime/.env` from `deploy/examples/systemd/dev-control-plane.environment.example`.
7. Keep OpenAI, Codex and GitHub credentials out of repo files and out of the example environment file. Use `/opt/dev-control-plane-runtime/secrets` or another approved host secret-store policy.
8. Install the systemd unit from `deploy/examples/systemd/dev-control-plane.service` only after human review.
9. Start the service and verify it over localhost before adding any reverse proxy.

## Runtime Environment

Minimal hosted environment:

```text
DEV_CONTROL_PLANE_RUNTIME_PROFILE=hosted
DEV_CONTROL_PLANE_HOST=127.0.0.1
DEV_CONTROL_PLANE_PORT=8770
DEV_CONTROL_PLANE_STATE_DIR=/opt/dev-control-plane-runtime/state
DEV_CONTROL_PLANE_SECRET_HOME=/opt/dev-control-plane-runtime/secrets
DEV_CONTROL_PLANE_CODEX_BIN=/opt/dev-control-plane-runtime/tools/codex/bin/codex
HOME=/opt/dev-control-plane-runtime
CODEX_HOME=/opt/dev-control-plane-runtime/.codex
```

The server rejects non-loopback binds. Do not set `DEV_CONTROL_PLANE_HOST=0.0.0.0`.

## Hosted Codex CLI Install Contract

Codex CLI for hosted `dev-control-plane` is installed as runtime tooling for the dedicated service user, not as a WebCore dependency and not as a repo file.

Approved layout:

- CLI package root: `/opt/dev-control-plane-runtime/tools/codex/`.
- CLI executable: `/opt/dev-control-plane-runtime/tools/codex/bin/codex`.
- Service auth home: `/opt/dev-control-plane-runtime/.codex/`.
- Auth file: `/opt/dev-control-plane-runtime/.codex/auth.json`.
- Runtime Codex config: `/opt/dev-control-plane-runtime/.codex/config.toml`.
- Runtime UI model config: `/opt/dev-control-plane-runtime/config/runtime_config.json`.
- Owner: `dev-control-plane:dev-control-plane`.
- Directory modes: `0755` or stricter for tool files, `0700` for `.codex`.
- Auth file mode: `0600`.
- Config file mode: `0600` or stricter operator policy.
- Service env: `HOME=/opt/dev-control-plane-runtime`, `CODEX_HOME=/opt/dev-control-plane-runtime/.codex`, `DEV_CONTROL_PLANE_CODEX_BIN=/opt/dev-control-plane-runtime/tools/codex/bin/codex`.
- Current hosted defaults: `model = "gpt-5.5"` and `model_reasoning_effort = "xhigh"` when the installed Codex CLI confirms those identifiers.
- Current visible UI-selectable runtime defaults: Curator `gpt-5.5` / `xhigh` and Codex `gpt-5.5` / `xhigh`. These are non-secret selectors only; API keys and login material remain terminal-only.
- Model profiles and presets are deprecated for runtime behavior. A stale `profile` field in runtime config is ignored and must not override explicit OpenAI model/reasoning, Codex model/reasoning or Codex sandbox values.
- Hosted Codex sandbox default may be `danger-full-access` for managed-clone execution when Codex CLI bubblewrap `workspace-write` fails on host loopback namespace setup. This is not a general shell bypass: the service still runs only inside the managed clone and verifier gates must keep original target unchanged, forbidden paths/actions clean, no commit/push/PR/merge/deploy, and secrets scan clean.
- OpenAI deep curator defaults: `DEV_CONTROL_PLANE_OPENAI_TIMEOUT_SECONDS=180`, `DEV_CONTROL_PLANE_OPENAI_RETRY_COUNT=2`, `DEV_CONTROL_PLANE_OPENAI_RETRY_BACKOFF_SECONDS=2`. Retry is bounded and applies only to timeout, transient network, provider timeout and 5xx classes.

## Hosted Codex Runtime Toolchain

The hosted managed-clone runner requires a small server-side toolchain in the service runtime context. Required tools for hosted runtime are:

- `git`
- `rg` / ripgrep
- `python3`
- `python3 -m venv`
- `pip` or `pip3`
- `jq`
- `bash`, `sh`, `sed`, `awk`, `grep`, `find`, `xargs`, `tar`, `gzip`, `unzip`, `timeout`
- configured Codex binary, normally `/opt/dev-control-plane-runtime/tools/codex/bin/codex`

Hosted WebCore UI/browser parity treats `node`, `npm`, `corepack`, `pnpm`, `yarn` and Playwright/Chromium readiness as baseline readiness. They are surfaced in `codex_runtime_parity`; missing package managers or required browser readiness block hosted Codex before launch for UI/browser-like work instead of becoming hidden runtime failures. `rsync` and `ssh` remain ordinary optional tools for managed-clone execution, while SSH deploy readiness is checked separately for the explicit production lane.

`gh` is optional for ordinary managed-clone execution, but it is required for the explicit `wb-core` production-lane PR/merge/delete-branch stage. Production-lane execution writes `artifacts/production_lane/preflight/production_lane_toolchain.json` and blocks with a controlled missing-tool or GitHub-auth reason before target lock acquisition if `gh` or auth is unavailable.

Provisioning policy:

- Prefer a tool already present in the service `PATH`.
- If the tool is a standard OS package, use the OS package manager for the host. Current approved system package: `ripgrep`.
- For Node/package-manager baseline on hosted runtime, prefer existing service-visible tools only if all of `node`, `npm`, `corepack`, `pnpm` and `yarn` are present. Otherwise the repo-owned provision/deploy runner installs a reviewed Node binary tarball under `/opt/dev-control-plane-runtime/tools/node/`, exposes symlinks through `/opt/dev-control-plane-runtime/tools/bin`, and installs pinned `pnpm`/`yarn` packages under `/opt/dev-control-plane-runtime/tools`.
- For GitHub CLI on hosted runtime, prefer an existing system `gh`; otherwise the repo-owned provision/deploy runner downloads the Ubuntu `gh` package with `apt-get download`, extracts it with `dpkg-deb -x`, and exposes only the binary through `/opt/dev-control-plane-runtime/tools/bin/gh`.
- If system install is not acceptable, use reviewed runtime-local binaries under `/opt/dev-control-plane-runtime/tools/bin`.
- Do not run `curl | bash` or unreviewed install scripts.
- Do not install target project dependencies globally.
- Do not change `/opt/wb-core-runtime/**`, `/opt/wb-ai/.env`, `/etc/nginx/sites-enabled/wb-ai` or WebCore services.

Repo-owned helper:

```bash
python3 apps/dev_control_plane_hosted_toolchain.py print-plan
python3 apps/dev_control_plane_hosted_toolchain.py inventory
python3 apps/dev_control_plane_hosted_toolchain.py validate
python3 apps/dev_control_plane_hosted_toolchain.py provision --dry-run
python3 apps/dev_control_plane_hosted_toolchain.py provision --live
python3 apps/dev_control_plane_hosted_toolchain.py deploy --dry-run
python3 apps/dev_control_plane_hosted_toolchain.py deploy --live
```

The helper is bounded to `dev-control-plane` runtime tools. It does not run Codex tasks, does not deploy WebCore and does not touch WebCore nginx/service/runtime paths. It must not request, store or print GitHub credentials; GitHub authentication remains outside repo-controlled docs/logs/API.

Preflight before real Codex writes `verifier/preflight/toolchain.json`, `verifier/preflight/runtime_parity.json` and `artifacts/environment_parity.json` with sanitized capability and parity matrices. It blocks before Codex if a required hosted tool is missing, if hosted Codex auth is expired/missing, or if a WebCore UI/browser prompt cannot satisfy Node/package-manager/browser readiness. The production-lane preflight uses the same sanitized toolchain status with `gh` required and adds sanitized GitHub auth plus wb-core deploy SSH readiness.

## Hosted GitHub Auth For Production Lane

The explicit `wb-core` production lane needs non-interactive GitHub auth for target branch push, PR creation, PR merge and branch deletion. The approved path is a runtime GitHub token stored outside the repo. Do not paste the token into chat, docs, PR bodies, logs, API requests or run artifacts.

Token requirements:

- Classic PAT: `repo` scope for `orenvlad-ai/wb-core`.
- Fine-grained token: repository access for `orenvlad-ai/wb-core` with Metadata read, Contents read/write and Pull requests read/write. Merge/delete-branch still depends on normal GitHub branch protection and repo permissions.

Terminal-only setup on the hosted server:

```bash
install -d -m 700 -o dev-control-plane -g dev-control-plane /opt/dev-control-plane-runtime/secrets
sudo -u dev-control-plane env \
  DEV_CONTROL_PLANE_SECRET_HOME=/opt/dev-control-plane-runtime/secrets \
  PYTHONPATH=/opt/dev-control-plane-runtime/app/src \
  python3 /opt/dev-control-plane-runtime/app/apps/dev_control_plane_setup.py github-token
```

The command prompts with hidden input and returns only sanitized JSON. It stores the raw token in `/opt/dev-control-plane-runtime/secrets/secrets.json`, which must be mode `0600` and owned by the service user. To remove it:

```bash
sudo -u dev-control-plane env \
  DEV_CONTROL_PLANE_SECRET_HOME=/opt/dev-control-plane-runtime/secrets \
  PYTHONPATH=/opt/dev-control-plane-runtime/app/src \
  python3 /opt/dev-control-plane-runtime/app/apps/dev_control_plane_setup.py delete-github-token
```

Sanitized status check:

```bash
sudo -u dev-control-plane env \
  DEV_CONTROL_PLANE_SECRET_HOME=/opt/dev-control-plane-runtime/secrets \
  PYTHONPATH=/opt/dev-control-plane-runtime/app/src \
  python3 /opt/dev-control-plane-runtime/app/apps/dev_control_plane_setup.py status
```

`GET /api/connections/status` and MCP `get_status` report `github.status`, `configured`, `token_present`, `gh_installed`, repo permission class and blocker text. They must not include the token, username, Authorization headers, cookies, raw env values or raw `gh` output.

## Hosted wb-core Deploy SSH Target

The explicit `wb-core` production lane creates the app backup and runs WebCore deploy commands only after PR merge. The SSH backup/deploy target must still be ready before any target mutation, so production-lane preflight checks it before target lock, target commit, push, PR creation or PR merge. Do not rely on an operator Mac SSH alias. Configure the hosted `dev-control-plane` service user explicitly.

The service user may use either:

- a service-user SSH alias in `/opt/dev-control-plane-runtime/.ssh/config`; or
- an explicit host/user/port in the runtime secret store, with an optional identity file path and known_hosts file path.

No private key material is stored in the repo or in the DevControl secret JSON. If an identity file is used, create it manually for the service user with mode `0600`; diagnostics report only that an identity file is configured, not its path.

Example service-user SSH config:

```sshconfig
Host wb-core-eu-root
  HostName 89.191.226.88
  User root
  Port 22
  IdentityFile /opt/dev-control-plane-runtime/secrets/wb-core-deploy-key
  IdentitiesOnly yes
  StrictHostKeyChecking yes
  UserKnownHostsFile /opt/dev-control-plane-runtime/secrets/known_hosts
```

Create/verify `known_hosts` without disabling host verification:

```bash
install -d -m 700 -o dev-control-plane -g dev-control-plane /opt/dev-control-plane-runtime/.ssh /opt/dev-control-plane-runtime/secrets
ssh-keyscan -H 89.191.226.88 | sudo -u dev-control-plane tee /opt/dev-control-plane-runtime/secrets/known_hosts >/dev/null
chmod 600 /opt/dev-control-plane-runtime/secrets/known_hosts
sudo -u dev-control-plane ssh -F /opt/dev-control-plane-runtime/.ssh/config -o BatchMode=yes wb-core-eu-root true
```

Store the DevControl runtime target metadata outside the repo:

```bash
sudo -u dev-control-plane env \
  DEV_CONTROL_PLANE_SECRET_HOME=/opt/dev-control-plane-runtime/secrets \
  PYTHONPATH=/opt/dev-control-plane-runtime/app/src \
  python3 /opt/dev-control-plane-runtime/app/apps/dev_control_plane_setup.py wb-core-deploy-ssh-target
```

Use alias `wb-core-eu-root` if the service-user SSH config owns the host/user/key policy. If using explicit host/user/port instead, leave the alias only as a display label or blank and provide the host fields at the prompt. To remove the runtime metadata:

```bash
sudo -u dev-control-plane env \
  DEV_CONTROL_PLANE_SECRET_HOME=/opt/dev-control-plane-runtime/secrets \
  PYTHONPATH=/opt/dev-control-plane-runtime/app/src \
  python3 /opt/dev-control-plane-runtime/app/apps/dev_control_plane_setup.py delete-wb-core-deploy-ssh-target
```

Sanitized status check:

```bash
sudo -u dev-control-plane env \
  DEV_CONTROL_PLANE_SECRET_HOME=/opt/dev-control-plane-runtime/secrets \
  PYTHONPATH=/opt/dev-control-plane-runtime/app/src \
  python3 /opt/dev-control-plane-runtime/app/apps/dev_control_plane_setup.py status
```

`GET /api/connections/status` and MCP `get_status` report `ssh_deploy.status`, `configured`, safe alias/host, port, identity policy, strict known_hosts policy, `ssh_installed`, `remote_ready` and blocker text. They must not include private key material, identity file paths, raw SSH stderr/stdout, env values, Authorization headers or cookies.

Approved Codex CLI install source:

- Use the same npm package identity as the local operator CLI, for example `@openai/codex@0.128.0`.
- The hosted provision/deploy runner owns the runtime-local Node/package-manager baseline under `/opt/dev-control-plane-runtime/tools`; do not install target project dependencies globally.
- Do not run `curl | bash`. The runner downloads only the reviewed Node tarball URL and pinned npm packages for the runtime-local baseline, or returns an exact blocker.
- Do not install Codex under `/opt/wb-core-runtime`, do not modify WebCore services, and do not change `/etc/nginx/sites-enabled/wb-ai`.

Approved auth source:

- Copy only Codex-specific auth from the local operator store, normally `~/.codex/auth.json`.
- Do not copy browser, keychain, unrelated project env files or WebCore secrets.
- Do not print auth file contents, tokens, session values or Authorization headers.

Safe verification:

```bash
/opt/dev-control-plane-runtime/tools/codex/bin/codex --version
HOME=/opt/dev-control-plane-runtime CODEX_HOME=/opt/dev-control-plane-runtime/.codex \
  /opt/dev-control-plane-runtime/tools/codex/bin/codex login status
curl -fsS http://127.0.0.1:8770/api/connections/status
```

For hosted/headless login use:

```bash
HOME=/opt/dev-control-plane-runtime CODEX_HOME=/opt/dev-control-plane-runtime/.codex \
  /opt/dev-control-plane-runtime/tools/codex/bin/codex login --device-auth
```

The status API may report `installed`, `version`, `authenticated`, sanitized `auth_status`, `codex_runtime_parity`, package-manager versions and browser readiness. It must not return auth file paths, token values, raw auth payloads or provider headers.

The status API may also report sanitized model defaults: OpenAI curator `model` / `reasoning_effort`, Codex CLI `model` / `model_reasoning_effort`, sandbox mode, and runtime config source. If a config file is missing or cannot be parsed, return a controlled status/warning rather than a traceback. Do not infer or invent model ids; confirm them through official docs, API availability checks or Codex CLI-supported configuration before changing hosted defaults.

The dashboard may save non-secret model/runtime settings through `/api/runtime-config`. The file must stay outside the repo, use restricted permissions, and never contain API keys, auth sessions, Authorization headers or provider payloads. The visible `Подключение` UI saves Curator and Codex model/reasoning only; API keys, OAuth grants, GitHub credentials, SSH keys and Codex login remain terminal-only.

OpenAI timeout diagnostics must distinguish local timeout, provider timeout, network error, auth error, unsupported model, rate limit, transient 5xx, invalid JSON and unexpected response shape. Do not retry auth, permission, unsupported model or bad request failures; they need operator/config action rather than backoff.

Rollback:

```bash
systemctl stop dev-control-plane.service
rm -rf /opt/dev-control-plane-runtime/tools/codex
rm -f /opt/dev-control-plane-runtime/.codex/auth.json
systemctl start dev-control-plane.service
```

Rollback must not remove `/opt/dev-control-plane-runtime/state` unless a separate data-retention decision exists. This step does not authorize a real Codex development task.

## Localhost Verification

Before any reverse proxy:

```bash
curl -fsS http://127.0.0.1:8770/api/state
```

Expected properties:

- `runtime_profile` is `hosted`.
- `host` is `127.0.0.1`.
- `bind_policy` is `loopback_only`.
- `state_dir` is `/opt/dev-control-plane-runtime/state`.
- `public_routes_enabled` is `false`.
- `live_deploy_enabled` is `false`.
- `state_layout.workspaces_dir` is inside `/opt/dev-control-plane-runtime/state`.

## MCP Connector Stage 1

Endpoint:

- Public URL: `https://devcontrol.pro/mcp`
- Loopback URL: `http://127.0.0.1:8770/mcp`
- Transport: streamable HTTP over JSON-RPC.
- Auth strategy for ChatGPT Developer Mode: `mixed_noauth_read_oauth_write`.
- Public auth boundary: the main `devcontrol.pro` UI stays behind nginx Basic Auth. `/mcp` is a no-auth exception for read-only MCP discovery/calls so ChatGPT can connect.
- Public no-auth `tools/list`: read tools only. Write tools are hidden and direct unauthenticated write calls return a controlled `denied` result.
- Authenticated read-only target docs: `list_target_docs`, `search_target_docs`, `get_target_doc`, plus compatibility fallback `read_target_docs` with `action=list|search|get`. These are hidden from public no-auth discovery, denied without auth, marked `readOnlyHint=true`, and use the existing OAuth-authenticated MCP session boundary; there is no separate target-docs token in the repo.
- MCP write auth for ChatGPT: OAuth authorization-code + PKCE with `dcp.write` scope. Dynamic client registration is public, token exchange is protocol-required, and `/oauth/authorize` inherits the hosted Basic Auth user gate.
- MCP write auth for protocol/API smokes: separate bearer token stored outside the repo. Do not reuse the Basic Auth password. This is not the ChatGPT Developer Mode UI auth option.

OAuth endpoints:

- Protected resource metadata: `https://devcontrol.pro/.well-known/oauth-protected-resource/mcp`
- Authorization server metadata: `https://devcontrol.pro/.well-known/oauth-authorization-server`
- Dynamic client registration: `https://devcontrol.pro/oauth/register`
- Authorization/consent: `https://devcontrol.pro/oauth/authorize`
- Token exchange: `https://devcontrol.pro/oauth/token`

Public no-auth ChatGPT tools in this stage:

- `get_status`
- `list_targets`
- `get_target_status`
- `get_operator_parity_status`
- `get_production_lock_status`
- `list_active_runs`
- `get_run_status`
- `get_run_report`
- `get_run_timeline`
- `get_run_log_tail`
- `list_run_artifacts`
- `get_run_artifact`
- `get_rollback_plan`
- `search`
- `fetch`

OAuth-authenticated ChatGPT read-only target docs tools:

- `list_target_docs`
- `search_target_docs`
- `get_target_doc`
- `read_target_docs`

Target docs read boundary:

- Allowlist: `README.md`, `AGENTS.md`, `docs/architecture/**`, `docs/modules/**`, `migration/**`.
- Deny: path traversal, `wb_core_docs_master/**`, `99_MANIFEST__DOCSET_VERSION.md`, `runtime/**`, `deploy/**`, `infra/**`, `artifacts/**`, env/secret/auth-like files and oversized reads.
- Responses include branch/commit/ref metadata and sanitized content/snippets only.
- The server uses a cached git snapshot under the control-plane state directory. It does not run Codex, does not checkout/reset the original target repo, does not mutate managed clones and does not deploy.

OAuth-authenticated ChatGPT write tools:

- `start_wb_core_auto_task`
- `start_wb_core_operator_parity_task`
- `start_wb_core_production_lane`
- `start_managed_clone_run`
- `resume_wb_core_production_deploy`
- `request_rollback`

Operator-parity lane for wb-core runtime/archive work:

- Read preflight with `get_operator_parity_status` before starting work. The same matrix is also visible in `get_status` and `get_target_status(target_id=wb-core)`.
- Required capabilities are `toolchain_ready`, `codex_auth_ready`, `operator_worktree_ready`, `github_ready`, `ssh_ready`, `runtime_state_readable`, `db_readable`, `browser_ready`, `browser_session_ready`, `promo_collector_runnable`, `xlsx_download_runnable`, `deploy_gate_ready`, `secret_broker_ready`, `redaction_ready` and `artifact_quarantine_ready`.
- `start_wb_core_operator_parity_task` defaults to `dry_run=true`. A real parity Codex start requires OAuth `dcp.write`, `dry_run=false`, `confirm_start=true` and ready preflight.
- The lane runs Codex in the configured persistent operator worktree and writes sanitized `operator_parity_preflight`, `operator_parity_runtime_broker_export`, `operator_parity_report`, log and handoff artifacts.
- Runtime/archive access is read-only by default through allowlisted paths or the sanitized broker export. The current hosted `wb-core` allowlist is `promo_campaign_archive`, `promo_xlsx_collector_runs`, `registry_upload_runtime.sqlite3` and browser/session metadata under `seller_portal_relogin`. Raw cookies, tokens, credentials, `.env`, browser raw profile storage and secret-like artifacts must not be exposed. Secret-like artifact content is redacted and quarantined as `secret_like_content_blocked`.
- This lane does not open PRs, merge, deploy, use sprint/ping-pong, or replace `start_wb_core_auto_task` for ordinary production-capable work.
- If live host preflight blocks on `runtime_state_readable`, the one manual host step is: grant the DevControl service user read access to the configured wb-core runtime state path or configure the sanitized broker allowlist to a readable export.

Frozen sprint/ping-pong boundary:

- `start_sprint`, the sprint orchestrator, curator-to-Codex ping-pong, parent/child task decomposition and the `DEVCONTROL_START_SPRINT_V1` compatibility bridge are frozen for ordinary ChatGPT operator flow.
- Public and authenticated operator discovery must not expose `start_sprint` as a normal write tool.
- Direct non-internal `start_sprint` calls return `start_sprint is frozen for operator flow; use direct wb-core auto Codex task` and create no `mcp-sprint-*` parent or `mcp-managed-*` child.
- `start_managed_clone_run` calls whose `task_text` starts with `DEVCONTROL_START_SPRINT_V1` return the same blocker and must not start a normal managed clone as a fallback.
- Ordinary WebCore work must use `start_wb_core_auto_task`: one direct production-capable run through the existing wb-core production lane, or a precise blocker before Codex starts.

OAuth operational notes:

- The OAuth client is public PKCE; there is no `client_secret` to store or rotate.
- Runtime state stores hashes of authorization codes and access grants, not raw values.
- Do not paste OAuth codes, access grants, Authorization headers, cookies or Basic Auth passwords into docs, PR bodies, handoffs, logs or chat transcripts.
- Static bearer auth remains for loopback/protocol smoke only and must not be used as the ChatGPT UI workaround.

Legacy bearer token setup for protocol/API smoke only:

```bash
sudo -u dev-control-plane env \
  DEV_CONTROL_PLANE_SECRET_HOME=/opt/dev-control-plane-runtime/secrets \
  python3 /opt/dev-control-plane-runtime/app/apps/dev_control_plane_setup.py mcp-token
sudo systemctl restart dev-control-plane.service
```

Generate/rotate token:

```bash
sudo -u dev-control-plane env \
  DEV_CONTROL_PLANE_SECRET_HOME=/opt/dev-control-plane-runtime/secrets \
  python3 /opt/dev-control-plane-runtime/app/apps/dev_control_plane_setup.py generate-mcp-token
sudo systemctl restart dev-control-plane.service
```

The generated token is printed once by the terminal command. Record it only through an approved secret channel. Do not paste it into docs, PR bodies, handoffs, logs or chat transcripts. To disable:

```bash
sudo -u dev-control-plane env \
  DEV_CONTROL_PLANE_SECRET_HOME=/opt/dev-control-plane-runtime/secrets \
  python3 /opt/dev-control-plane-runtime/app/apps/dev_control_plane_setup.py delete-mcp-token
sudo systemctl restart dev-control-plane.service
```

Protocol smoke over loopback:

```bash
curl -fsS http://127.0.0.1:8770/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":"1","method":"initialize","params":{}}'

curl -fsS http://127.0.0.1:8770/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":"2","method":"tools/call","params":{"name":"get_status","arguments":{}}}'

curl -fsS http://127.0.0.1:8770/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":"3","method":"tools/call","params":{"name":"list_targets","arguments":{}}}'

curl -fsS http://127.0.0.1:8770/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":"4","method":"tools/call","params":{"name":"list_active_runs","arguments":{}}}'
```

Authenticated dry-run write smoke is operator-only. Prefer the OAuth connector flow; the first hosted write call must use `dry_run=true`. Legacy bearer direct calls are only for protocol/API smoke with a token from an approved secret channel. Do not paste OAuth grants, bearer values, Authorization headers, or command output into docs, PRs, handoffs or chat transcripts.

Expected result: a `run_id` with `completed_dry_run`, `live_url` / `watch_url`, no `wb-core` PR, no merge, no WebCore deploy, and rollback-plan artifacts under that run directory. Poll with `get_run_status`, read the report with `get_run_report`, inspect terminal/timeline state with `get_run_timeline` / `get_run_log_tail`, and inspect artifacts with `list_run_artifacts` / `get_run_artifact`.

Post-merge recovery for an already merged blocked `wb-core` production-lane run:

Use this only when a production-lane run already passed verifier and merged its target PR, but blocked before backup/deploy/probes. The current known recovery case is `mcp-prod-20260507T162232Z-0d7bb0f7c4`, PR #280, merge commit `f1dd35c427b5cda8907cb99a45343625166af735`.

Dry-run eligibility first; this writes only DevControl resume preflight/report artifacts and must not deploy WebCore:

```bash
sudo -u dev-control-plane env \
  DEV_CONTROL_PLANE_STATE_DIR=/opt/dev-control-plane-runtime/state \
  DEV_CONTROL_PLANE_SECRET_HOME=/opt/dev-control-plane-runtime/secrets \
  python3 /opt/dev-control-plane-runtime/app/apps/dev_control_plane_runner.py \
    target-production-resume-deploy \
    --state-dir /opt/dev-control-plane-runtime/state \
    --run-id mcp-prod-20260507T162232Z-0d7bb0f7c4
```

The dry-run must report `resume_dry_run_ready` or an exact blocker. Required gates are: `wb-core` production-lane run, verifier passed, PR URL/number present, merge commit present and on `origin/main`, rollback plan present and matching the merge commit, changed files outside forbidden paths, GitHub auth ready, SSH deploy readiness ready, and target production lock free. Codex CLI is not required for this recovery preflight because this path never reruns Codex.

Execute backup/deploy/probes only after explicit operator approval:

```bash
sudo -u dev-control-plane env \
  DEV_CONTROL_PLANE_STATE_DIR=/opt/dev-control-plane-runtime/state \
  DEV_CONTROL_PLANE_SECRET_HOME=/opt/dev-control-plane-runtime/secrets \
  python3 /opt/dev-control-plane-runtime/app/apps/dev_control_plane_runner.py \
    target-production-resume-deploy \
    --state-dir /opt/dev-control-plane-runtime/state \
    --run-id mcp-prod-20260507T162232Z-0d7bb0f7c4 \
    --execute \
    --confirm-resume-deploy
```

ChatGPT can use the OAuth-gated MCP tool `resume_wb_core_production_deploy` with `dry_run=true` for eligibility. `dry_run=false` requires `confirm_resume_deploy=true` and `dcp.write`; no-auth discovery hides the tool and unauthenticated direct calls are denied. The recovery path never reruns Codex, changes the diff, creates a branch, commits, pushes, opens a new PR or merges again. It uses the recorded merge commit and writes `resume_preflight`, `backup_result`, `deploy_result`, `probe_result`, `resume_deploy_result` and `resume_deploy_report` artifacts.

Parallel run tracking:

- `start_managed_clone_run` creates managed-clone-only runs and returns quickly.
- Multiple managed-clone runs can exist at once; each has its own `run_id` and workspace.
- `list_active_runs` shows active MCP runs.
- `get_run_status` and `get_run_report` always take `run_id`.
- `wb-core` production merge/deploy is serialized by the target production lock. If the lock is active, a production-lane start returns `waiting_for_target_lock` with the active run id rather than a generic error.

Manual ChatGPT setup:

1. Open ChatGPT settings.
2. Go to Settings -> Connectors/Apps -> Advanced settings -> Developer mode.
3. Create/Add a remote MCP server/app with URL `https://devcontrol.pro/mcp`.
4. Use the connector auth flow offered by Developer Mode. No-auth read discovery should work immediately; OAuth write authorization uses the hosted consent URL and requires the current Basic Auth credentials for `devcontrol.pro`.
5. Refresh tools. Without OAuth, enable public read tools only. After OAuth succeeds, authenticated target docs tools appear with `readOnlyHint=true`, and write tools appear with `readOnlyHint=false` plus OAuth `dcp.write` metadata. If the three granular docs tools are not visible after refresh, use the `read_target_docs` fallback.
6. Test in ChatGPT: `Use dev-control-plane MCP get_status.`
7. Test target docs after OAuth: `Use dev-control-plane MCP search_target_docs for target wb-core with query architecture.` Fallback prompt: `Use dev-control-plane MCP read_target_docs with action search, target wb-core, query architecture.`
8. First write test must be dry-run only: ask ChatGPT to start `start_wb_core_production_lane` with `dry_run=true` and verify it returns a `run_id` without creating a PR or deploying.

Do not start a real `wb-core` production-lane mutation as a connector smoke. If ChatGPT cannot complete OAuth, keep using the read-only connector and inspect the OAuth metadata endpoints first; do not switch write tools to no-auth.

## Hosted Live Monitor

Operator URL:

- Live run list: `https://devcontrol.pro/runs/live`
- Per-run watch page: `https://devcontrol.pro/runs/<run_id>/watch`
- Main page entry point: `Живые запуски` link in the dark dashboard sidebar on `https://devcontrol.pro/`.

Auth boundary:

- The live monitor inherits the main `devcontrol.pro` nginx Basic Auth boundary.
- Do not add `auth_basic off` for `/runs/live`, `/runs/<run_id>/watch` or `/api/runs/*` live-monitor APIs.
- MCP read-only no-auth remains scoped to `/mcp`; live logs are not public no-auth.

Read-only APIs:

- `GET /api/runs/live`
- `GET /api/runs/<run_id>/live` includes sanitized run detail, frozen prompt preview, Codex process status and stale assessment
- `GET /api/runs/<run_id>/timeline`
- `GET /api/runs/<run_id>/log-tail`
- `GET /api/runs/stream`
- `GET /api/runs/<run_id>/stream`

Bounded run-control APIs:

- `POST /api/runs/<run_id>/cancel`
- `POST /api/runs/<run_id>/mark-stale`

These endpoints inherit the main Basic Auth boundary. They do not accept shell commands, do not mutate target repos, and preserve artifacts/workspaces. Cancel may signal only the Codex process group recorded in the run-owned process state; if there is no owned live process, use mark-stale instead.

Security behavior:

- The page is a viewer only: no shell input, command prompt, command paste or arbitrary execution control.
- The selected run is pinned in the browser; automatic selection should only happen when there is no selected run or the selected run disappears.
- Terminal output uses the `offset` field from `/api/runs/<run_id>/log-tail` for append-only rendering. Timeline reads may use the `cursor`/`after` field from `/api/runs/<run_id>/timeline`.
- The `Промпт` panel displays the frozen prompt artifact before, during and after execution with sanitized copy support.
- Active stage cards show `выполняется` / `Codex работает`, elapsed time and last activity from recorded Codex process state.
- Run detail includes raw `status` plus effective reconciliation fields. If raw status is failed but Codex is still active, the UI shows `control_error_codex_running` with a running indicator. If handoff exists but verifier is missing after a DevControl error, the UI shows `needs_verifier_after_control_error` and keeps the handoff visible.
- Stale/operator-marked runs should show an amber stale/operator badge, distinct from red failed and green completed states.
- Completed/passed/failed runs should show their final state and then switch to quiet/low-frequency refresh.
- The copy button copies only the currently visible sanitized terminal text. The clear button clears the local browser view only and does not delete artifacts.
- APIs return bounded sanitized data, not raw logs. Sanitization redacts Authorization headers, bearer values, cookies, API key patterns, env secret assignments, sensitive secret paths and risky traceback content.
- ANSI support is allowlisted to SGR color/style sequences. OSC, DCS, APC, PM, clipboard/title/hyperlink controls and arbitrary cursor/control sequences are stripped.
- Raw Codex event logs remain machine artifacts. The default terminal transcript expands item start/completion and command execution events into readable text with timestamps, command text, status, exit code, duration and bounded output excerpts.
- Common Codex JSONL metadata envelopes are hidden from the default terminal view. Assistant/handoff text is rendered as text, and escaped newlines are decoded before display.
- A pinned/vendored `xterm.js` asset is not present and external CDN loading is prohibited, so the current implementation uses a small local ANSI SGR renderer. Add `xterm.js` only in a separate reviewed dependency/static-asset PR.
- Watchdog state is configured outside the repo. `codex_io_mode=event` is the default; `pty` is diagnostic/experimental and should not be enabled until a separate host validation proves it safe.
- Prompt consistency gates block contradictory envelopes before Codex starts, for example production-lane plus repo-only/no-live/no-deploy, UI work plus no UI, or Codex execution plus no Codex worker run.

Operational check:

```bash
python3 apps/dev_control_plane_live_monitor_smoke.py
```

After hosted deploy, verify without printing credentials:

- `https://devcontrol.pro/runs/live` returns `401` without Basic Auth.
- Authenticated `/runs/live` loads the monitor page.
- Authenticated `/` contains a `Живые запуски` link to `/runs/live`.
- Authenticated `/api/runs/live` returns sanitized JSON.
- Authenticated `/api/runs/<run_id>/live` for a known run returns sanitized prompt/process/stale fields.
- `get_status` reports `codex_observability` readiness and the effective IO mode.
- Starting a fake/local or dry-run MCP run returns `live_url` and `watch_url`; do not run a real `wb-core` production-lane mutation for this check.

Stuck run recovery:

For a stuck run such as `mcp-prod-20260507T203745Z-a50c2e4bb2`, first open `/runs/<run_id>/watch` and inspect `Промпт`, `Лог Codex`, last activity and stale assessment. If the process state shows an owned active Codex process and the operator wants to stop it, use `Остановить` or `POST /api/runs/<run_id>/cancel`. If the service has no owned live process, use `Пометить stale/blocked` or `POST /api/runs/<run_id>/mark-stale`. Do not start rollback, deploy or a new production-lane run as part of this diagnostic step.

Frozen sprint check:

- In ChatGPT Developer Mode, after OAuth consent, verify authenticated `tools/list` does not expose `start_sprint`.
- A direct `start_sprint` call with `target_id=wb-core` must return `blocked` with `start_sprint is frozen for operator flow; use direct wb-core auto Codex task` and no `run_id`.
- A `start_managed_clone_run` call with `task_text` starting `DEVCONTROL_START_SPRINT_V1` must return the same blocker and create no managed or sprint run.
- Use `start_wb_core_auto_task` for ordinary WebCore tasks; if direct production-capable intake cannot proceed, report its blocker rather than falling back.

## Repo-Owned Deploy Runner

Use the deploy runner for planning and validation:

```bash
python3 apps/dev_control_plane_hosted_deploy.py print-plan
python3 apps/dev_control_plane_hosted_deploy.py validate
python3 apps/dev_control_plane_hosted_deploy.py deploy --dry-run
```

Live deploy is allowed only after these gates pass:

- Cloudflare/Google DNS-over-HTTPS resolves `devcontrol.pro` and `www.devcontrol.pro` to `89.191.226.88`.
- The target server resolves both names to `89.191.226.88` through `getent ahostsv4` and `dig` when `dig` is available.
- Local Codex machine DNS may be stale; stale local `system` or default `dig` results are warnings only when public DoH and target-server DNS are clean.
- SSH target is `wb-core-eu-root`.
- App/state/env paths are under `/opt/dev-control-plane-runtime/**`, not WebCore paths.
- Service is `dev-control-plane.service`, not WebCore services.
- Loopback is `127.0.0.1:8770`, not `8765` or `8000`.
- nginx site is `/etc/nginx/sites-enabled/dev-control-plane`, not `/etc/nginx/sites-enabled/wb-ai`.
- nginx basic auth is configured before cockpit traffic is exposed.

After a successful merge to `main`, a human-approved live step may run:

```bash
python3 apps/dev_control_plane_hosted_deploy.py deploy --live
python3 apps/dev_control_plane_hosted_deploy.py loopback-probe
python3 apps/dev_control_plane_hosted_deploy.py public-probe
python3 apps/dev_control_plane_hosted_deploy.py webcore-probe
```

If any safety gate fails, do not run `deploy --live`.

## Reverse Proxy Boundary

`deploy/examples/reverse-proxy/nginx.dev-control-plane.conf.example` is a template only. It must not be copied into a live reverse proxy by Codex. Public access requires a separate approved task that defines HTTPS, auth, allowed routes, logging and rollback.

The application service should continue to listen on `127.0.0.1`. External access belongs to the reverse proxy and must include an approved authentication layer before use.

## Smoke

Run the hosted foundation smoke locally:

```bash
python3 apps/dev_control_plane_hosted_server_smoke.py
```

The smoke uses a temp state root, starts the server only on `127.0.0.1`, checks hosted state layout creation and verifies that a non-loopback bind is blocked. It does not call real OpenAI, does not run real Codex, does not use SSH/root/sudo and does not deploy.

## Target Workflow Dry-Runs

Hosted `wb-core` readiness uses `remote_managed_clone` from `https://github.com/orenvlad-ai/wb-core.git` on `main`. The local Mac `repo_path` remains in the adapter for local context, but it is not a hosted blocker when the remote source is reachable.

Decision-only checks:

```bash
python3 apps/dev_control_plane_target_remote_source_smoke.py
python3 apps/dev_control_plane_target_workflow_smoke.py
```

Runner dry-run commands:

```bash
python3 apps/dev_control_plane_runner.py target-pr-plan --input /path/to/payload.json
python3 apps/dev_control_plane_runner.py preview-plan --input /path/to/payload.json
python3 apps/dev_control_plane_runner.py target-approval-decision --input /path/to/payload.json
python3 apps/dev_control_plane_runner.py target-production-plan --input /path/to/payload.json
python3 apps/dev_control_plane_runner.py target-production-run --input /path/to/payload.json
```

Server endpoints expose the same decision-only contracts:

- `POST /api/target-workflow/pr-plan`
- `POST /api/target-workflow/preview-plan`
- `POST /api/target-workflow/approval-decision`
- `POST /api/target-production/plan`

The general target workflow commands and endpoints do not push target branches, open GitHub PRs, merge target PRs, deploy WebCore preview or production, or mutate `/opt/wb-core-runtime/**`.

The explicit `wb-core` production lane is different and intentionally mutating only when `target-production-run --execute` is used. It is the production-capable apply/deploy mode for `wb-core` code tasks. The payload must be explicit (`execution_mode=production_lane` or `apply_mode=target_pr_merge_deploy`, with production lane enabled); otherwise the runner returns a controlled blocker instead of silently falling back to managed-clone-only review. It consumes verifier-passed managed-clone output and then performs:

1. target rules inventory from `README.md`, `AGENTS.md` if present, `docs/architecture/**`, `docs/modules/**`, `migration/**`, adapter config and code state;
2. production-lane toolchain/auth preflight requiring GitHub CLI `gh`, runtime GitHub token, repo write permission, HTTPS git auth readiness and wb-core deploy SSH readiness;
3. single target production lock acquisition under the control-plane state root;
4. `devcp/<run_id>-<slug>` branch creation;
5. Russian commit and PR metadata;
6. `wb-core` PR creation and merge after expected head SHA check;
7. rollback plan and app backup under `/opt/wb-core-runtime/backups/dev-control-plane`;
8. approved WebCore deploy runner commands:
   - `python3 apps/registry_upload_http_entrypoint_hosted_runtime.py print-plan`;
   - `python3 apps/registry_upload_http_entrypoint_hosted_runtime.py deploy --dry-run`;
   - `python3 apps/registry_upload_http_entrypoint_hosted_runtime.py deploy`;
   - `python3 apps/registry_upload_http_entrypoint_hosted_runtime.py loopback-probe --as-of-date AUTO_YESTERDAY`;
   - `python3 apps/registry_upload_http_entrypoint_hosted_runtime.py public-probe --as-of-date AUTO_YESTERDAY`.

Production lane gates forbid direct push to `main`, overlapping `wb-core` production runs, deploy without merged PR, deploy with failed verifier, deploy with forbidden paths, deploy with failed secrets scan, deploy without rollback plan, external WB live writes, DB/data mutations and derived-pack updates by default. The lock is released after success or failure. A stale lock reports its path and manual cleanup command, and must be removed only after verifying no production lane is running.

## Recovery For Already Merged But SSH-Blocked Runs

If an older production-lane run already merged a `wb-core` PR but blocked at SSH backup/deploy, do not rerun the original task or merge another PR. First configure and verify the hosted SSH deploy target above. Then recover manually under a separate explicit deploy approval, using the already recorded production-lane report:

1. Confirm the blocked run id, PR URL, merge commit and pre-merge main commit in `production_lane_result.json` / MCP `get_run_report`.
2. Confirm the merged commit is still the intended `origin/main` head or identify any later commits that must be reviewed before deploy.
3. Run the approved WebCore deploy runner against the already merged commit only after explicit approval.
4. Create/record the app backup and post-deploy probe evidence in the run handoff.
5. If deploy is no longer safe because `main` moved or verification context is stale, return a blocker and request a fresh production-lane run on current `main`.

For run `mcp-prod-20260507T162232Z-0d7bb0f7c4`, the known merged PR is `orenvlad-ai/wb-core#280` with merge commit `f1dd35c427b5cda8907cb99a45343625166af735`. This PR does not auto-deploy or roll back that commit; it only ensures future runs fail before merge when SSH readiness is missing.

## Known Gaps

- The deploy runner exists, but live deploy must stop on DNS/auth/safety blockers.
- No production reverse-proxy/auth policy is implemented.
- No managed external secret-store provider is implemented; current hosted credentials use the restricted runtime file secret store outside the repo.
- No real preview/staging deploy adapter exists; only a dry-run contract exists.
- Full provider/VPS snapshot integration is not configured; rollback uses git revert plus app backup and WebCore redeploy.
- No durable hosted database or object-store backend exists.
- No retention policy for hosted artifacts/workspaces exists.

## Not In Scope

- Changing `wb-core` or any target repo.
- Opening public routes.
- Running SSH/root/sudo or live deploy.
- Running real Codex or real OpenAI.
- Running real preview/staging deploy.
- Running real target repo PR/apply/merge behavior.
- Storing secrets in repo, docs pack, UI, API responses, logs or run artifacts.

## Blockers

Before a real hosted rollout, decide:

- Host owner and access model.
- Secret-store provider and redaction policy.
- Reverse-proxy authentication and HTTPS policy.
- Backup and retention for `/var/lib/dev-control-plane`.
- Monitoring and log retention.
- Manual rollback procedure.
