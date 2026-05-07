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
7. Keep OpenAI, Codex and GitHub credentials out of repo files and out of the example environment file. Use an approved host secret-store policy when one exists.
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
- Current UI-selectable runtime defaults: OpenAI curator `gpt-5.5` / `xhigh`, Codex `gpt-5.5` / `xhigh`. Lighter confirmed options are exposed only as explicit non-secret runtime config fields.
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

Optional tools are reported as warnings unless the managed target workspace requires them: `node`, `npm`, `corepack`, `pnpm`, `yarn`, `rsync`, `ssh`, `gh`.

Provisioning policy:

- Prefer a tool already present in the service `PATH`.
- If the tool is a standard OS package, use the OS package manager for the host. Current approved package: `ripgrep`.
- If system install is not acceptable, use a reviewed runtime-local binary under `/opt/dev-control-plane-runtime/tools/bin`.
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
```

The helper is bounded to `dev-control-plane` runtime tools. It does not run Codex tasks, does not deploy WebCore and does not touch WebCore nginx/service/runtime paths.

Preflight before real Codex writes `verifier/preflight/toolchain.json` with a sanitized capability matrix and blocks before Codex if a required hosted tool is missing. Missing optional tools stay warnings unless target manifests such as `package.json`, `pnpm-lock.yaml`, `yarn.lock` or `package-lock.json` require them.

Approved install source:

- Use the same npm package identity as the local operator CLI, for example `@openai/codex@0.128.0`.
- The server must already have `node` compatible with the package engine, currently `>=16`.
- If the server does not have `npm`, do not bootstrap a new package manager and do not run `curl | bash`. A bounded operator may create reviewed npm tarballs on the local machine, including the matching Linux optional dependency, transfer only those package artifacts to a temporary server directory, and unpack them into `/opt/dev-control-plane-runtime/tools/codex/`.
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

The status API may report `installed`, `version`, `authenticated` and a sanitized `auth_status`. It must not return auth file paths, token values, raw auth payloads or provider headers.

The status API may also report sanitized model defaults: OpenAI curator `model` / `reasoning_effort`, Codex CLI `model` / `model_reasoning_effort`, sandbox mode, and runtime config source. If a config file is missing or cannot be parsed, return a controlled status/warning rather than a traceback. Do not infer or invent model ids; confirm them through official docs, API availability checks or Codex CLI-supported configuration before changing hosted defaults.

The cockpit may save non-secret model/runtime settings through `/api/runtime-config`. The file must stay outside the repo, use restricted permissions, and never contain API keys, auth sessions, Authorization headers or provider payloads. The saved fields are explicit: OpenAI curator model/reasoning, Codex model/reasoning and Codex sandbox.

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

OAuth-authenticated ChatGPT write tools:

- `start_wb_core_production_lane`
- `start_managed_clone_run`
- `request_rollback`

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
5. Refresh tools. Without OAuth, enable read tools only. After OAuth succeeds, write tools appear with `readOnlyHint=false` and OAuth `dcp.write` metadata.
6. Test in ChatGPT: `Use dev-control-plane MCP get_status.`
7. First write test must be dry-run only: ask ChatGPT to start `start_wb_core_production_lane` with `dry_run=true` and verify it returns a `run_id` without creating a PR or deploying.

Do not start a real `wb-core` production-lane mutation as a connector smoke. If ChatGPT cannot complete OAuth, keep using the read-only connector and inspect the OAuth metadata endpoints first; do not switch write tools to no-auth.

## Hosted Live Monitor

Operator URL:

- Live run list: `https://devcontrol.pro/runs/live`
- Per-run watch page: `https://devcontrol.pro/runs/<run_id>/watch`

Auth boundary:

- The live monitor inherits the main `devcontrol.pro` nginx Basic Auth boundary.
- Do not add `auth_basic off` for `/runs/live`, `/runs/<run_id>/watch` or `/api/runs/*` live-monitor APIs.
- MCP read-only no-auth remains scoped to `/mcp`; live logs are not public no-auth.

Read-only APIs:

- `GET /api/runs/live`
- `GET /api/runs/<run_id>/live`
- `GET /api/runs/<run_id>/timeline`
- `GET /api/runs/<run_id>/log-tail`
- `GET /api/runs/stream`
- `GET /api/runs/<run_id>/stream`

Security behavior:

- The page is a viewer only: no shell input, command prompt, command paste or arbitrary execution control.
- The copy button copies only the currently visible sanitized terminal text. The clear button clears the local browser view only and does not delete artifacts.
- APIs return bounded sanitized data, not raw logs. Sanitization redacts Authorization headers, bearer values, cookies, API key patterns, env secret assignments, sensitive secret paths and risky traceback content.
- ANSI support is allowlisted to SGR color/style sequences. OSC, DCS, APC, PM, clipboard/title/hyperlink controls and arbitrary cursor/control sequences are stripped.
- A pinned/vendored `xterm.js` asset is not present and external CDN loading is prohibited, so the current implementation uses a small local ANSI SGR renderer. Add `xterm.js` only in a separate reviewed dependency/static-asset PR.

Operational check:

```bash
python3 apps/dev_control_plane_live_monitor_smoke.py
```

After hosted deploy, verify without printing credentials:

- `https://devcontrol.pro/runs/live` returns `401` without Basic Auth.
- Authenticated `/runs/live` loads the monitor page.
- Authenticated `/api/runs/live` returns sanitized JSON.
- Starting a fake/local or dry-run MCP run returns `live_url` and `watch_url`; do not run a real `wb-core` production-lane mutation for this check.

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
2. single target production lock acquisition under the control-plane state root;
3. `devcp/<run_id>-<slug>` branch creation;
4. Russian commit and PR metadata;
5. `wb-core` PR creation and merge after expected head SHA check;
6. rollback plan and app backup under `/opt/wb-core-runtime/backups/dev-control-plane`;
7. approved WebCore deploy runner commands:
   - `python3 apps/registry_upload_http_entrypoint_hosted_runtime.py print-plan`;
   - `python3 apps/registry_upload_http_entrypoint_hosted_runtime.py deploy --dry-run`;
   - `python3 apps/registry_upload_http_entrypoint_hosted_runtime.py deploy`;
   - `python3 apps/registry_upload_http_entrypoint_hosted_runtime.py loopback-probe --as-of-date AUTO_YESTERDAY`;
   - `python3 apps/registry_upload_http_entrypoint_hosted_runtime.py public-probe --as-of-date AUTO_YESTERDAY`.

Production lane gates forbid direct push to `main`, overlapping `wb-core` production runs, deploy without merged PR, deploy with failed verifier, deploy with forbidden paths, deploy with failed secrets scan, deploy without rollback plan, external WB live writes, DB/data mutations and derived-pack updates by default. The lock is released after success or failure. A stale lock reports its path and manual cleanup command, and must be removed only after verifying no production lane is running.

## Known Gaps

- The deploy runner exists, but live deploy must stop on DNS/auth/safety blockers.
- No production reverse-proxy/auth policy is implemented.
- No hosted secret-store provider is implemented.
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
