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
- Current UI-selectable runtime defaults: OpenAI curator `gpt-5.5` / `xhigh`, Codex `gpt-5.5` / `xhigh`. Lighter confirmed options are exposed only as non-secret runtime config.
- Hosted Codex sandbox default may be `danger-full-access` for managed-clone execution when Codex CLI bubblewrap `workspace-write` fails on host loopback namespace setup. This is not a general shell bypass: the service still runs only inside the managed clone and verifier gates must keep original target unchanged, forbidden paths/actions clean, no commit/push/PR/merge/deploy, and secrets scan clean.
- OpenAI deep curator defaults: `DEV_CONTROL_PLANE_OPENAI_TIMEOUT_SECONDS=180`, `DEV_CONTROL_PLANE_OPENAI_RETRY_COUNT=2`, `DEV_CONTROL_PLANE_OPENAI_RETRY_BACKOFF_SECONDS=2`. Retry is bounded and applies only to timeout, transient network, provider timeout and 5xx classes.

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

The cockpit may save non-secret model/runtime settings through `/api/runtime-config`. The file must stay outside the repo, use restricted permissions, and never contain API keys, auth sessions, Authorization headers or provider payloads.

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
```

Server endpoints expose the same decision-only contracts:

- `POST /api/target-workflow/pr-plan`
- `POST /api/target-workflow/preview-plan`
- `POST /api/target-workflow/approval-decision`

These commands and endpoints do not push target branches, open GitHub PRs, merge target PRs, deploy WebCore preview or production, or mutate `/opt/wb-core-runtime/**`.

## Known Gaps

- The deploy runner exists, but live deploy must stop on DNS/auth/safety blockers.
- No production reverse-proxy/auth policy is implemented.
- No hosted secret-store provider is implemented.
- No real preview/staging deploy adapter exists; only a dry-run contract exists.
- No real target repo apply/merge policy exists; only PR/approval decision objects exist.
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
