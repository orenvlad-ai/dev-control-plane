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
```

The server rejects non-loopback binds. Do not set `DEV_CONTROL_PLANE_HOST=0.0.0.0`.

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

- `devcontrol.pro` resolves only to `89.191.226.88`.
- `www.devcontrol.pro` resolves to `89.191.226.88` or is excluded from the certificate.
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

## Known Gaps

- The deploy runner exists, but live deploy must stop on DNS/auth/safety blockers.
- No production reverse-proxy/auth policy is implemented.
- No hosted secret-store provider is implemented.
- No preview/staging deploy adapter exists.
- No target repo apply policy exists.
- No durable hosted database or object-store backend exists.
- No retention policy for hosted artifacts/workspaces exists.

## Not In Scope

- Changing `wb-core` or any target repo.
- Opening public routes.
- Running SSH/root/sudo or live deploy.
- Running real Codex or real OpenAI.
- Adding preview/staging deploy.
- Adding target repo PR/apply/merge behavior.
- Storing secrets in repo, docs pack, UI, API responses, logs or run artifacts.

## Blockers

Before a real hosted rollout, decide:

- Host owner and access model.
- Secret-store provider and redaction policy.
- Reverse-proxy authentication and HTTPS policy.
- Backup and retention for `/var/lib/dev-control-plane`.
- Monitoring and log retention.
- Manual rollback procedure.
