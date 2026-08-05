# Development Control Plane · Orchestrator Codex v2

`dev-control-plane` is a standalone local-first control plane for multiple
Codex tasks. The deterministic Supervisor on the owner's Mac is the only
orchestration authority. `devcontrol.pro` is a sanitized read-only projection,
GitHub Release Train is a mechanical actuator, and fresh Sol Ultra turns are
rare schema-bound advisers.

`wb-core` is an external target, not part of this repository. No SellerOS or
target business code belongs here.

The authoritative design is
[`docs/architecture/03_orchestrator_v2.md`](docs/architecture/03_orchestrator_v2.md).
The approved hosted boundary and target identity remain documented in
[`docs/architecture/02_hosted_control_plane_architecture.md`](docs/architecture/02_hosted_control_plane_architecture.md).

## Authority model

```text
Mac: Supervisor + private SQLite registry       only orchestration writer
Codex App Server: owned local stdio child       executor transport, not truth
GitHub Release Train                            bounded mechanical actuator
Fresh gpt-5.6-sol / ultra                       advice only
devcontrol.pro projection                       rebuildable read-only viewer
```

The hosted process does not import the legacy cockpit/MCP/executor stack. Its
only write route is authenticated Mac-to-server ingestion. Every legacy,
MCP, OAuth, cancel, task-start, Codex, merge, deploy and rollback POST route is
denied before state changes.

Legacy sprint/parallel/ping-pong, operator parity, hosted Codex execution,
Chat-Watcher/Reporter and GitHub heartbeat transport are not v2 fallbacks.
Historical implementation and runtime collections are retained as audit
evidence only.

## Local Supervisor

Runtime state defaults to `~/.dev-control-plane-v2/` and stays outside Git:

```text
current -> releases/<merged-sha>/
previous -> releases/<previous-v2-sha>/
state/supervisor.sqlite3
state/backups/
secrets/projection_hmac.key
logs/
```

The registry uses SQLite WAL, `synchronous=FULL`, foreign keys, schema
migrations, online backups, generation fencing, CAS revisions, event and
idempotency IDs, transactional inbox/outbox, executor generations and sorted
atomic task/thread/resource/release locks. No external wait occurs inside a DB
transaction.

The launchd service binds only `127.0.0.1:8766`. Its HTTP interface is
read-only health/readiness/state; durable task mutations use the local CLI and
strict versioned JSON contracts.

Local development status:

```bash
python3 apps/dev_control_plane_local_install_v2.py status
python3 apps/dev_control_plane_supervisor_v2.py health \
  --state-dir ~/.dev-control-plane-v2/state \
  --request-id '<unique-read-request-id>'
```

The Supervisor `health` command is a private-socket client and therefore
requires the singleton service to be running. Installer `status` is the safe
filesystem-only view when no generation is active.

Filesystem-only installer dry setup (does not activate launchd unless
`--activate` is explicit):

```bash
python3 apps/dev_control_plane_local_install_v2.py install \
  --source . \
  --expected-sha "$(git rev-parse HEAD)"
```

Production install requires a clean checkout whose `HEAD` equals
`origin/main`. Update and rollback use immutable releases and atomic symlinks;
rollback never reactivates a legacy watcher.

## Codex integration

The supported production surface is a Supervisor-owned `codex app-server`
child over stdio JSONL. WebSocket and daemon control sockets are not production
dependencies. The adapter:

- initializes and validates `model/list`;
- requires exact `gpt-5.6-sol` and `ultra` and sends both on every turn;
- creates/resumes only Supervisor-owned threads;
- consumes typed thread/turn/item lifecycle events;
- rejects `model/rerouted`, stale generations and identity mismatches;
- inherits only a fixed path/locale/auth-home environment allowlist, never
  ambient GitHub, provider or SSH-agent credentials from the Supervisor;
- serializes each thread and reconciles stable thread/turn/item IDs after a
  bounded reconnect;
- accepts only schema-bound checkpoint or terminal evidence as orchestration
  input.

Existing Desktop-owned chats are snapshot-readable capability evidence only;
cross-process live event attachment is not claimed. Exact curator delivery is
a separate stateless host-mediated adapter over one durable attention event.
Delivery failure leaves attention pending and visible on the dashboard.

## Task and release contracts

The v2 Task Passport contains objective, expected result, contour,
included/excluded scope, constraints, acceptance, closure, autonomy,
resources/modules/files, dependencies, multi-PR/multi-deploy intent and exact
curator/executor identities.

Progress stages are evidence-backed: 5, 15, 25, 40, 55, 65, 72, 80, 88, 95
and 100. A registered executor begins at 5%. Russian delta/current text may
change without a percentage change. Progress 100 means contour-aware technical
completion; owner acceptance is always separate and never automatic.

Executor terminal strings cannot produce 100% by themselves. An exact
`(contour, target)` verifier independently re-reads immutable release truth and
binds its typed receipt to the terminal digest and current revisions. The
control-plane self-release requires merged `main`, exact PR head/merge,
`v2-suite=SUCCESS`, Passport-scoped diff, and—when production is claimed—the
approved hosted runner's read-only release/TLS/Auth/WebCore probes. Diagnostic
and artifact targets require their own explicitly registered callbacks.

The deterministic release order is active-lane continuity, owner
priority/dependencies, critical-path/unblock value, risk/resource isolation,
aging/fairness, then creation time. Overlap, shared schema/migration/contract,
dependencies, lane competition, conflicts, Passport-vs-diff mismatch,
unknown classification or multiple safe orders freeze one immutable
`RELEASE_PLAN` case. A fresh Sol Ultra response must bind exact task revisions,
PR head SHAs and resources before the Supervisor can apply it mechanically.

Incident handling is fixed: one bounded current retry, one successor from a
verified checkpoint, one incident with one fresh arbiter, one application plus
independent verification, then park on the same failure. HumanGate is a closed
allowlist and requests one truly human-exclusive action only after independent
safe work is complete.

The only ordinary release intake command is
`register_release_candidate`. It accepts only the current task/workstream, one
expected PR head SHA and an idempotent message ID. The Supervisor derives every
scheduler field from the current Passport and a fresh, complete GitHub PR
readback; callers cannot submit priority, resources, diff, checks, lane state or
admission truth. A merged PR is recorded as proof-only and is never actuated as
if it were still open.

After bootstrap, ordinary `self_merge` does not authorize a change to the
installed Supervisor/governance/deploy/install authority surface. Such an open
PR produces one `security_permission_change` HumanGate and needs a separate
exact-head two-phase authorization. A protected PR that GitHub already proves
merged remains proof-only and cannot enqueue merge or deploy work.

For external `wb-core` work, the registered adapter uses that repository's
current GitHub-native Release Train protocol. It posts the exact admission
command, observes the trusted `main` queue/status implementation, waits without
consuming a causal retry budget, and accepts terminal production proof only
from immutable target readback. It never merges or deploys `wb-core` directly.
After the whole Task Passport closure barrier is proven, a distinct idempotent
target-lane release command closes the target logical lane; the first PR is not
treated as task completion for multi-PR or multi-deploy work.

## Hosted read-only projection

Run locally with an external mode-`0600` HMAC key:

```bash
python3 apps/dev_control_plane_projection_v2.py \
  --host 127.0.0.1 \
  --port 8770 \
  --database /tmp/dev-control-plane-projection/projection.sqlite3 \
  --hmac-key-file /path/outside/repo/projection_hmac.key
```

Routes:

- `POST /api/v2/ingest` — the only mutation, signed and replay-protected;
- `GET /api/v2/health` — sanitized role/readiness/last-seen state;
- `GET /api/v2/state` — sanitized projection detail;
- `GET /` and `GET /runs/live` — concise responsive Russian dashboard.

The main UI shows task/workstream, progress, evidence delta/current, release
lane, incidents, pending attention, acceptance and `last_seen`/stale state. It
does not show raw JSON, raw logs, commands or secrets. Accepted tasks disappear
from active cards but remain in sanitized audit storage.

If the network or server is unavailable, local execution continues and the
durable outbox retries with backoff. Ingest ACKs contain receipt identity only
and never control instructions.

## Hosted rollout

Live deployment is allowed only through the repository-owned runner and the
exact approved target `wb-core-eu-root` / `89.191.226.88`, service
`dev-control-plane.service`, bind `127.0.0.1:8770`, isolated
`/opt/dev-control-plane-runtime/**`:

```bash
python3 apps/dev_control_plane_hosted_deploy.py print-plan
python3 apps/dev_control_plane_hosted_deploy.py validate
python3 apps/dev_control_plane_hosted_deploy.py deploy --dry-run
python3 apps/dev_control_plane_hosted_deploy.py deploy --live
python3 apps/dev_control_plane_hosted_deploy.py loopback-probe
python3 apps/dev_control_plane_hosted_deploy.py public-probe
python3 apps/dev_control_plane_hosted_deploy.py webcore-probe
python3 apps/dev_control_plane_hosted_deploy.py transaction-status \
  --release-sha "$ORPHANED_SHA"
python3 apps/dev_control_plane_hosted_deploy.py transaction-recover --dry-run \
  --release-sha "$ORPHANED_SHA" --attempt-id "$ATTEMPT_ID" \
  --snapshot-sha256 "$SNAPSHOT_SHA256" --expected-stage "$STAGE"
```

The live runner requires exact clean merged `origin/main`, installs an
immutable release, preserves previous v2 rollback, does not provision hosted
Codex/GitHub/SSH execution credentials, keeps Basic Auth over the UI, repairs
and proves ACME/TLS freshness, verifies every mutation route stays closed, and
proves WebCore remains independent. Its rsync transport is pinned to
root-owned `/usr/bin/rsync` on both ends and uses only package-cwd-relative
sources so the immutable layout is identical under macOS OpenRSYNC and GNU
rsync. Runtime state is retained across release
and rollback.

An unresolved fail-closed rollout is inspected and dispositioned only by the
same runner after the corrective code is merged. The failed SHA, snapshot
digest and distinct replacement `origin/main` SHA are mandatory CAS inputs:

```bash
python3 apps/dev_control_plane_hosted_deploy.py quarantine-status \
  --release-sha "$FAILED_SHA"
python3 apps/dev_control_plane_hosted_deploy.py quarantine-resolve --dry-run \
  --release-sha "$FAILED_SHA" --snapshot-sha256 "$SNAPSHOT_SHA256" \
  --replacement-sha "$MERGED_SHA"
python3 apps/dev_control_plane_hosted_deploy.py quarantine-resolve --live \
  --release-sha "$FAILED_SHA" --snapshot-sha256 "$SNAPSHOT_SHA256" \
  --replacement-sha "$MERGED_SHA"
```

This transition seals immutable audit evidence while authority remains
disabled. It may atomically move an inert legacy app directory into its
root-owned, non-writable archive and finish that normalization idempotently; it
never deletes the quarantine/snapshot, relinks the app, starts a service or
restores legacy. A failed release may be recorded as absent when failure
preceded release finalization. If `origin/main` advances before any activation
artifact exists, one append-only CAS supersession may bind the next descendant
tip; each further advance extends the same immutable chain. The normal
print-plan/validate/dry-run/live/probe sequence is still required for its
effective tip, and final remediation binds both the deployed SHA and terminal
chain anchor.

An orphan activation is inspectable with `transaction-status`. Recovery uses
`transaction-recover --dry-run` and then `--live`, requires an unchanged exact
release/attempt/snapshot/stage readback and a stage at least 900 seconds old,
and can only restore or quarantine safely; it cannot activate a release.

## Migration

Legacy state is never deleted or treated as v2 truth. The migration tool makes
an online SQLite backup with integrity/SHA-256 evidence and exposes only
sanitized shadow aggregates:

```bash
python3 apps/dev_control_plane_migration_v2.py archive \
  --destination ~/.dev-control-plane-v2/backups/legacy-monitor
python3 apps/dev_control_plane_migration_v2.py shadow
```

Retirement of the exact legacy launch agent requires the verified archive
manifest. It unloads the agent but retains its plist, source DB and backup. G6,
Luna Watcher, Reporter or a global chat watcher must not be started.

## Tests

The authoritative suite is fake-first and performs no real OpenAI/Codex call:

```bash
python3 apps/dev_control_plane_v2_suite.py
```

Core individual checks include:

```bash
python3 apps/dev_control_plane_v2_registry_smoke.py
python3 apps/dev_control_plane_codex_app_server_v2_smoke.py
python3 apps/dev_control_plane_arbiter_v2_smoke.py
python3 apps/dev_control_plane_projection_v2_smoke.py
python3 apps/dev_control_plane_supervisor_v2_smoke.py
python3 apps/dev_control_plane_supervisor_runtime_v2_smoke.py
python3 apps/dev_control_plane_contour_verifier_v2_smoke.py
python3 apps/dev_control_plane_release_train_v2_smoke.py
python3 apps/dev_control_plane_wb_core_release_adapter_v2_smoke.py
python3 apps/dev_control_plane_local_install_v2_smoke.py
python3 apps/dev_control_plane_migration_v2_smoke.py
python3 apps/dev_control_plane_hosted_deploy_smoke.py
python3 apps/dev_control_plane_hosted_quarantine_v2_smoke.py
python3 apps/dev_control_plane_hosted_state_machine_v2_smoke.py
```

CI also compiles all Python, checks projection import isolation, scans for
forbidden paths/secrets, runs `git diff --check` and executes retained safety
smokes for state layout, legacy-entrypoint denial, GitHub closure and target
isolation. One bounded real App Server canary may run only after this suite is
green.

## Repository boundary and secrets

Target configs under `configs/target_projects/` are adapter metadata, not
target source of truth. The original target checkout is read-only by default;
`wb-core` changes, if ever required, need a separate governed target PR and its
current Release Train.

Never commit `.env`, HMAC values, API keys, Codex/OpenAI/GitHub/SSH auth,
cookies, private keys, raw provider payloads or sensitive runtime/log state.
The derived `dev_control_plane_docs_master/` pack is secondary and is not
updated unless a task explicitly requests a derived sync.
