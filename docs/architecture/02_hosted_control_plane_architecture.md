# Hosted Control Plane Architecture

> **v2 authority note (current):**
> [`03_orchestrator_v2.md`](03_orchestrator_v2.md) supersedes every hosted
> execution, queue-selection, follow-up, MCP/OAuth write and target-mutation
> design below. The approved host, DNS, loopback bind, isolated runtime paths,
> Basic Auth boundary and repository-owned deploy runner remain authoritative.
> Since the v2 cutover, the hosted process is a rebuildable read-only
> projection whose only mutation is signed Mac-to-server ingestion. The
> remaining document is retained as architectural/migration history and as the
> source for reusable managed-clone/verifier libraries; it is not permission to
> reactivate hosted control authority.

## Summary

This document fixes the target architecture for a future hosted `dev-control-plane` service. The control-plane remains a standalone project. Product repositories such as `wb-core` are external target projects connected through target adapters; they are not this repo's identity and must not become part of the control-plane runtime.

The intended operator outcome is practical: an approved target task produces verifier artifacts, a GitHub PR, deploy evidence and a curator handoff. The first production-capable target is `wb-core`; other target repos remain read-only/decision-only until they receive their own explicit apply policy.

This is an architecture and governance document. The current implementation covers the local/hosted-ready filesystem state foundation, loopback-only hosted server runtime foundation, dev-control-plane repo self-closure policy, remote managed target source, decision-only target PR/preview/approval gates, an explicit guarded `wb-core` production lane, MCP connection v1 and the simple ordinary execution rule: one ChatGPT MCP task becomes one direct `start_wb_core_auto_task` run. It does not authorize public routes beyond the approved dev-control-plane host, production deploy for non-`wb-core` targets, external WB live actions, uncontrolled database/data mutations, removed legacy orchestration or secrets handling changes.

## Server Layout

The hosted control-plane should be deployed as its own service and host boundary, separate from any target product runtime.

Normative layout:

- Web/UI service: unified dark dashboard shell with `Панель`, `Подключение`, `Мониторинг` and `Технические детали` sections. Legacy chat/curator/task-card APIs may remain backend compatibility paths, but they are not the primary hosted UI.
- API service: task intake, target context read, TaskSpec freeze, job scheduling, run artifact reads, approval transitions and verifier status.
- Worker service: managed-clone preparation, Codex invocation, verifier execution, GitHub PR creation and preview/staging orchestration.
- State store: metadata for tasks, runs, approval gates, artifacts, target adapter snapshots and verifier summaries.
- Secret store integration: server-side only; secrets are never entered into the browser, stored in repo files or returned through API responses.
- Artifact storage: prompts, handoffs, diffs, logs, verifier reports and preview metadata with retention policy.

The hosted service must not share process, filesystem state, deploy lane, public routes or production secrets with a target product-plane service.

Implemented hosted server MVP foundation:

- Runtime profile: `DEV_CONTROL_PLANE_RUNTIME_PROFILE=hosted`.
- Code path convention for the first hosted target: `/opt/dev-control-plane-runtime/app`.
- State root convention for the first hosted target: `/opt/dev-control-plane-runtime/state`, set through `DEV_CONTROL_PLANE_STATE_DIR`.
- Bind policy: application server remains `127.0.0.1:8770` and rejects non-loopback binds.
- Deploy runner: `apps/dev_control_plane_hosted_deploy.py` with `print-plan`, `validate`, `deploy --dry-run`, `deploy --live`, `loopback-probe`, `public-probe`, `webcore-probe`, `rollback-plan`, the v2-only sanitized `quarantine-status` / digest-bound `quarantine-resolve` protocol, and exact-CAS `transaction-status` / `transaction-recover` for stale orphan transactions.
- Immutable package copy is pinned to root-owned `/usr/bin/rsync` locally and
  remotely and uses only package-cwd-relative sources. This is a portability
  and identity invariant: macOS OpenRSYNC does not honour GNU rsync's absolute
  `/./` cut-point convention.
- Service template: `deploy/examples/systemd/dev-control-plane.service`.
- Environment template: `deploy/examples/systemd/dev-control-plane.environment.example`.
- Reverse-proxy template: `deploy/examples/reverse-proxy/nginx.dev-control-plane.conf.example`.
- Runbook: `docs/runbooks/01_hosted_server_mvp.md`.

The example unit, environment and reverse-proxy files are templates. The only
live application exception is the repository-owned runner against the exact
host/service/paths authorized by `AGENTS.md` and the v2 architecture; generic
hosted code and every other target remain forbidden from applying systemd,
reverse-proxy, SSH/root or public-route changes.

## State Directories

Hosted state must be explicit and separate from repo source. The current implementation resolves state through `DEV_CONTROL_PLANE_STATE_DIR` or `/tmp/development-control-plane-state` and must not write runtime state into tracked paths.

Implemented logical layout:

```text
state/
  collections/
    discussions.json
    parallel_task_ledger.json  # legacy read-only migration state, not an execution surface
    task_specs.json
    prompts.json
    runs.json
    real_runs.json
  artifacts/
    prompts/
  runs/
    <run_id>/
      run.json
      managed_workspace.json
      artifacts/
        prompt.md
        handoff.md
        diff.patch
      logs/
        executor.log
        codex.log
      verifier/
        verifier.json
        checks/
          git_diff_check.txt
  workspaces/
    <run_id>/<target_id>/
  logs/
  verifier/
```

Current `.gitignore` already treats `state/`, `runs/` and `workspaces/` as local/runtime-only paths. Hosted state follows the same rule: it is operational data, not source code and not project-pack content.

The resolver rejects unsafe `run_id`, `target_id`, workspace and collection path components. Run artifacts, logs and verifier outputs are owned by `state/runs/<run_id>/`; managed workspaces are owned by `state/workspaces/<run_id>/<target_id>/`. Existing root-level cockpit collection files are read as a legacy fallback, but new writes go through `state/collections/`.

Legacy orchestration collections such as `parallel_task_ledger.json` may exist only as read-only migration/audit state. They are not ordinary runtime inputs, not MCP tool surfaces and not production-selection queues. New ChatGPT MCP work must enter through `start_wb_core_auto_task`; removed sprint/parallel/ping-pong/managed-clone-only launch paths must return a controlled removed-flow blocker if reached through compatibility APIs.

## Managed Workspaces

Codex execution must happen only inside a managed clone or managed workspace owned by the control-plane. The original target repo working tree is read-only context. The former operator-parity runtime lane is removed and must not become a fallback for ordinary work without a future explicit policy.

Required managed-workspace behavior:

- Clone or checkout the selected target revision into `state/workspaces/<run_id>/<target_id>/`.
- Record the target repo URL, target branch, base commit and workspace path in run metadata.
- Run Codex only against the managed workspace.
- Run verifier checks inside the managed workspace.
- Produce diff, handoff, logs and verifier report as control-plane artifacts.
- Never write, reset, checkout, commit, push, merge or deploy from the original target repo path.

Managed workspace output is review material until an explicit apply/PR policy runs. The first implemented apply policy is the `wb-core` production lane; it still never uses the original target repo path as its execution workspace.

## Dev-Control-Plane Repo Closure

`dev-control-plane` has a narrow self-closure policy for Codex-owned work in this repository. Codex may complete commit, push, PR creation, merge and branch deletion for its own PR in `orenvlad-ai/dev-control-plane`, including L3 tasks, only when all merge eligibility gates are clean:

- The PR was created for the current task or belongs to the current Codex-owned `codex/*` branch.
- Repo is exactly `orenvlad-ai/dev-control-plane`.
- `git status --short --branch` is clean before merge.
- The PR is open and the PR head SHA matches the expected local head SHA.
- Every required task smoke/check has passed.
- `git diff --check` and `git diff --cached --check` are clean.
- Verifier status is `passed`.
- Forbidden paths/actions are absent.
- `dev_control_plane_docs_master/**` and `99_MANIFEST__DOCSET_VERSION.md` are unchanged unless the task is explicitly a derived-sync task.
- Secrets scan is clean for tokens, private keys, Authorization header values, `.env` and Codex auth material.
- Final handoff includes status, work summary, changed files, checks, untouched scope, blocker, repo state, commit/push/PR/merge status and `=== СЖАТАЯ ПРОВЕРКА ===`.
- Blocker is absent.
- The task does not contain an explicit `NO_AUTO_MERGE` instruction.

If any gate fails, Codex must leave the PR open and report the exact blocker. This policy is implemented as a merge eligibility helper in `src/dev_control_plane/github_closure.py`, a runner decision command and a local server decision endpoint. The workflow gate returns `allowed/denied/blockers`, `merge_allowed` and `delete_branch_allowed`; it does not accept GitHub credentials or execute hidden GitHub API mutation from the cockpit. The actual GitHub merge/delete branch operation remains an explicit external `gh` workflow step after the gate is allowed.

## Target Repo Boundary

Target adapters describe external repositories. They are metadata inputs, not source of truth.

The `wb-core` adapter currently matches this architecture:

- `target_readonly_by_default` is `true`.
- `allow_managed_clone_execution` is `true`.
- `allow_direct_target_mutation` is `false`.
- `allow_auto_merge` is `false`.
- `allow_live_deploy` is `false`.
- forbidden actions include live deploy, SSH/root, public route changes, secrets writes, auto-merge and direct target mutation.

The `wb-core` adapter now supports hosted remote managed clone source:

- `source_mode`: `remote_managed_clone`.
- `repo_url`: `https://github.com/orenvlad-ai/wb-core.git`.
- `branch`: `main`.
- `repo_path`: kept as `/Users/ovlmacbook/Projects/wb-core` for local mode/context only.

Hosted mode must not require the Mac local path. A missing local `repo_path` is a warning when the remote source is reachable and managed clone is ready. Remote source validation uses non-interactive git access and must return an exact blocker if the remote source or branch is unavailable.

This means the adapter permits managed-clone review work but blocks direct product-plane mutation. Future target adapters must follow the same default unless a separate approved governance task changes the policy.

## Target Repo PR Lifecycle

The target repo PR lifecycle is explicit and auditable:

1. Curator drafts a bounded TaskSpec from operator discussion and target context.
2. Operator approves freeze and execution class.
3. Worker creates a managed clone from the target base commit.
4. Codex runs one bounded task inside the managed clone.
5. Verifier checks diff hygiene, forbidden paths/actions, prompt/handoff contract and target-specific checks.
6. Worker creates or plans a target repo branch from the managed clone output only after verifier passes.
7. Worker opens or plans a GitHub PR with summary, changed files, verifier report and preview/staging link when available.
8. Control-plane stores PR URL, branch, commits, verifier report and preview metadata in run state.
9. Curator/operator reviews the PR and preview result.

The current general implementation provides decision-only target PR planning in `src/dev_control_plane/target_workflow.py`, runner commands and server endpoints. The plan uses branch names of the form `devcp/<run_id>-<slug>`, Russian commit/PR text, a required PR description, verifier result, changed files, preview URL and rollback/close instructions. The explicit `wb-core` production lane in `src/dev_control_plane/target_production.py` is the exception: it may execute GitHub PR creation/merge and production deploy only after verifier, secrets, forbidden-path, rollback, GitHub CLI availability, hosted GitHub auth readiness, hosted wb-core deploy SSH readiness and head-SHA gates pass. Removed sprint/ping-pong/parent-child orchestration is not a target apply path: ordinary ChatGPT Project WebCore work must not create `mcp-sprint-*` parents, child managed-run cards or curator ping-pong steps.

## Preview And Staging Lifecycle

Preview/staging is the intended proof surface for target changes. It is separate from production.

Required preview/staging behavior:

- Create preview from the PR branch or an immutable build artifact tied to the PR commit.
- Store preview URL, deploy revision, environment name and verifier status in run metadata.
- Show preview URL in the cockpit result summary and curator handoff.
- Run content-level or route-level verifier checks against preview/staging when target policy defines them.
- Tear down or expire preview environments according to retention policy.

The current implementation provides a decision-only preview dry-run contract. The preferred URL shape is `https://devcontrol.pro/previews/wb-core/<run_id>/`, protected by the same auth boundary. Preview state belongs under `state/previews/<run_id>`. The dry-run contract explicitly avoids `/opt/wb-core-runtime/**`, `api.selleros.pro` and `/etc/nginx/sites-enabled/wb-ai`.

Real WebCore preview deploy remains blocked until a target-specific preview runtime command, isolated loopback port policy, route mapping and verifier contract are defined. `wb-core` production deploy is available only through the explicit production lane and the approved WebCore deploy runner.

## Curator Approval Flow

Approval gates separate drafting, execution, PR creation and production decisions.

Expected gates:

- Task intake: operator chooses target project and describes the task.
- TaskSpec freeze: curator draft becomes immutable only after policy validation.
- Real Codex run: operator approval is required before a managed-clone Codex run.
- PR creation: plan is allowed only from managed workspace output after verifier, forbidden-path and secrets gates pass; real GitHub mutation is allowed only inside an explicit production lane such as `wb-core`.
- Preview/staging deploy: dry-run contract exists; real preview deploy is allowed only after target preview policy exists and the operator or policy gate approves it.
- Approve/reject: decision helper can approve target merge only when preview/verifier/forbidden-path/secrets/blocker gates pass and a target merge policy is explicitly enabled. Reject never changes production.
- Dev-control-plane repo self-merge: allowed only under the clean gates in this document.
- Target production merge/deploy: not automatic for generic targets; `wb-core` has an explicit target apply/deploy policy with rollback and deploy-runner gates.

The UI must explain gate state without exposing raw secrets or arbitrary shell controls.

## Prohibitions

The hosted control-plane must not:

- Mutate the original target repo working tree directly.
- Run Codex outside a managed clone/workspace.
- Auto-merge target PRs into production branches.
- Auto-deploy production.
- Add public routes or hosted deploy wiring without a dedicated implementation/governance task.
- Execute SSH/root/live deploy actions from generic task prompts.
- Expose arbitrary shell command fields in the UI.
- Store secrets in repo files, project packs, prompts, handoffs, logs or browser state.
- Return API keys, Authorization headers, Codex auth, provider credentials or raw secret-bearing tracebacks through APIs.
- Treat `wb-core` or any other target as this repo's identity.

## Current Norm

- `dev-control-plane` is standalone control-plane source.
- Target projects are external adapters and read-only by default.
- `wb-core` uses remote managed clone source on hosted runtime; missing local Mac path is not a hosted blocker when the remote source is reachable.
- Runner/server expose decision-only target PR, preview and approve/reject workflow gates, plus an explicit `wb-core` production-lane plan endpoint.
- Codex-owned dev-control-plane PRs may be self-merged, including L3, only after clean merge eligibility gates pass and no `NO_AUTO_MERGE` instruction is present.
- Runner/server closure workflow now exposes a decision-only gate backed by `src/dev_control_plane/github_closure.py`.
- Hosted server runtime foundation exists for a loopback-only service profile with systemd/reverse-proxy examples and a hosted smoke.
- A repo-owned deploy runner exists for the isolated `devcontrol.pro` service and blocks live deploy unless DNS, target host, path, service, port and auth-boundary gates are clean.
- Real Codex is gated and managed-clone-based.
- Current runner/MCP/legacy API managed-clone output is review material until the explicit `wb-core` production lane consumes a verifier-passed run.
- Current runner/server code has a unified filesystem state layout for runs, artifacts, logs, verifier output, cockpit collections and managed workspaces.
- Legacy parallel orchestration is removed from API/MCP operator runtime. Historical ledger records are read-only migration/audit state and cannot submit, start, reconcile, promote or deploy work.
- Current safe/fake/managed-Codex flows do not commit, push, merge, deploy or apply changes to original target repos; only the explicit `wb-core` production lane may mutate the target through PR/merge/deploy gates.
- Current smoke coverage uses fake/stub Codex/OpenAI paths and must not call real providers.
- The `wb-core` adapter policy aligns with this boundary: remote managed clone is enabled, direct original-repo mutation remains disabled, and production deployment is available only after the production-lane gates pass.

## Known Gaps

- A filesystem state layout exists, but a durable hosted database/object-store backend and retention policy are not implemented.
- Hosted server deploy templates and repo-owned live deploy automation exist, but live deploy must stop when DNS, SSH, service, port or auth-boundary safety gates are not clean.
- Multi-worker scheduling and durable job recovery are not implemented.
- Real GitHub PR mutation from managed target workspace output is implemented only for the explicit `wb-core` production lane.
- Server-side GitHub credentials are not owned by the cockpit; `target-production-run --execute` remains the explicit mutation step.
- Real preview/staging deploy adapters are not implemented; only dry-run preview contract exists.
- Preview verifier contracts are not implemented.
- Production approval and deployment policy is implemented only for `wb-core` and only through verifier/rollback/deploy-runner gates.
- Secret-store integration for hosted runtime is not implemented.
- Target-specific commit author and PR labeling policy are not implemented.

## Not In Scope

- Product code changes outside managed-clone target lanes.
- Changes to `wb-core` or any target repo outside the explicit `wb-core` production lane.
- Changes to `dev_control_plane_docs_master/` or manifest files.
- Live deploy, public routes, SSH/root operations or production runtime changes outside the explicit `wb-core` production lane.
- Real Codex execution against a target outside a managed clone.
- Real OpenAI API calls.
- Real target repo GitHub PR creation, target merge and production deploy for targets other than `wb-core`.
- Automatic target merge or production deploy without verifier, secrets, rollback and deploy-runner gates.

## Blockers

Before implementation, the project needs explicit decisions for:

- Hosted state backend and retention policy.
- Workspace cleanup and artifact retention.
- GitHub app/token model for creating branches and PRs without leaking credentials.
- Target-specific preview runtime command, isolated port model and route mapping.
- Verifier contract for preview URLs and target-specific smoke scope.
- Human approval UX for PR creation, preview deploy and production handoff.
- Secret-store provider and API redaction policy for hosted mode.

## Explicit wb-core Production Lane

The `wb-core` production lane is the first target mutation policy. It is not a general target-repo permission. It is allowed only for `target_id=wb-core`, `repo_url=https://github.com/orenvlad-ai/wb-core.git`, `branch=main`, and managed workspaces under control-plane state.

Flow:

1. Load target rules from the managed clone: `README.md`, `AGENTS.md` when present, `docs/architecture/**`, `docs/modules/**`, `migration/**`, target adapter config and current code state.
2. Run Codex only in a managed clone.
3. Require verifier passed, clean forbidden paths/actions, clean secrets scan and bounded changed files.
4. Run production-lane preflight for hosted tools, GitHub CLI/auth and wb-core deploy SSH readiness. This blocks before target lock, commit, push, PR creation or merge if the hosted service user cannot reach the configured SSH target with strict host-key checking.
5. Create `devcp/<run_id>-<slug>` branch in `wb-core`; never push directly to `main`.
6. Commit with Russian message and required run/task summary.
7. Open a PR with Russian title/body containing run id, changed files, verifier, docs status, deploy plan and rollback plan.
8. Merge only when PR head SHA matches expected head.
9. Record pre-merge main commit and merge commit.
10. Create a rollback/app backup and then deploy only from merged `main` through `apps/registry_upload_http_entrypoint_hosted_runtime.py`.
11. Run loopback, public and task-specific post-deploy checks.

The lane is explicit: production-capable `wb-core` tasks must carry `execution_mode=production_lane` or `apply_mode=target_pr_merge_deploy`, and the server UI labels it as the production path. If this mode is impossible, the runner returns an exact blocker rather than falling back to managed-clone-only review.

The lane also owns a single `wb-core` target production lock under the configured state root. A second production-lane run is blocked while the lock is active. Stale locks report age, path and a manual cleanup command; cleanup is allowed only after verifying no deploy/rollback is running. The lock is released on success or failure.

The lane blocks before mutation if rollback plan is missing, verifier failed, forbidden paths changed, secrets scan failed, required hosted tools are missing, GitHub auth/readiness is missing, or the wb-core deploy SSH target is missing/unreachable. After mutation starts, it still blocks deploy if the target PR was not merged, the deploy runner is missing, the target lock cannot be acquired, or public verification fails.

## MCP Stage 1 Interface Bridge

Stage 1 adds a remote MCP backend to the hosted control-plane. ChatGPT.com remains the user-facing UI; the control-plane is the backend/orchestrator that exposes bounded tools over `POST /mcp` with streamable HTTP. The implementation uses Mixed Authentication semantics: public no-auth discovery/read tools plus OAuth-gated write and target-docs tools. Developer Mode respects `readOnlyHint`; DevControl does not expose generic `search`/`fetch` tools as part of the stable operator surface.

MCP connection v1 is the stable connector contract for ChatGPT:

- `public_url`: `https://devcontrol.pro`
- `mcp_endpoint`: `https://devcontrol.pro/mcp`
- `oauth_issuer`: `https://devcontrol.pro`
- `oauth_resource`: `https://devcontrol.pro/mcp`
- `resource_metadata`: `https://devcontrol.pro/.well-known/oauth-protected-resource/mcp`
- `transport`: `streamable_http`
- `auth`: `oauth2_authorization_code_pkce`
- `scope`: `dcp.write`

`get_status` exposes `mcp.connection_contract_version=mcp_connection_v1`, the visible `mcp.discovery_hash`, sanitized OAuth counters (`active_grants_count`, `expired_grants_count`, `pending_codes_count`, `registered_clients_count`) and reconnect diagnostics. Discovery is deterministic: stable tool names, sorted tool order, code-defined JSON schemas, no runtime run/state/OAuth fields and a SHA-256 canonical discovery hash. Changing the public URL, endpoint path, OAuth issuer/resource, resource metadata URL, auth mode, scope, tool names, schemas or ordering requires forced ChatGPT reconnect. ChatGPT connector cache/link failures remain external; DevControl reports only server-side metadata, discovery hash, OAuth state counts and reason codes.

MCP tool surface:

- Public read/status: `get_status`, `list_targets`, `get_target_status`, `list_active_runs`, `get_run_status`, `get_run_report`, `get_run_timeline`, `get_run_log_tail`, `list_run_artifacts`, `get_run_artifact`.
- Authenticated read-only: `list_target_docs`, `search_target_docs`, `get_target_doc`, and compatibility fallback `read_target_docs` with `action=list|search|get`. These are hidden from public no-auth `tools/list`, require an authenticated MCP session, keep `readOnlyHint=true`, and expose only sanitized snippets/content from allowlisted target docs paths.
- OAuth-gated write/safety: `start_wb_core_auto_task` and `request_rollback`. These are hidden from public no-auth `tools/list`; direct unauthenticated calls return a controlled denial. No sprint, ping-pong, parent/child, parallel, selected-promotion, managed-clone-only fallback, explicit production-lane, resume-deploy or operator-parity MCP tools are exported.

The MCP layer is an adapter over existing control-plane code. It must not duplicate production-lane deploy logic. `start_wb_core_auto_task` is the normal and only ordinary ChatGPT Project route for `wb-core`/WebCore work. When no production-capable run or production lock is active, `wb_core_exclusive_auto_production` runs one clean managed clone through Codex, verifier and the existing guarded wb-core PR/merge/deploy/probe lane. That verified managed clone is the ordinary production source of truth; `diff.patch` is audit evidence and is not re-applied in a separate promotion workspace. When another production-capable run, auto-production intent or lock is active, the server returns `wb_core_direct_auto_blocked` before creating a run, task spec, workspace or Codex process. If the direct route is unavailable, the only valid response is `direct wb-core auto Codex tool unavailable; sprint/ping-pong flow is removed`.

All MCP runs have a unique `run_id`, a state directory under `state/runs/<run_id>/`, and managed workspace ownership under `state/workspaces/<run_id>/<target_id>/` when Codex is actually run. Tool calls read status and artifacts by `run_id`, so ChatGPT can track the single direct run without prompt copying.

Target docs access is an authenticated read-only target boundary. The MCP layer reads `README.md`, `AGENTS.md`, `docs/architecture/**`, `docs/modules/**` and `migration/**` from a cached git snapshot under control-plane state and returns the branch/commit with every response. It does not checkout/reset the original target repo, does not mutate managed clones, does not expose `wb_core_docs_master/**` by default, and denies runtime/deploy/infra/artifact/env/secret paths, path traversal and oversized reads.

Concurrency model:

- Ordinary `wb-core` write intake is exclusive: a second production-capable run is blocked before creating a run, workspace or Codex process.
- The original target repo is not an execution workspace.
- Managed-clone Codex execution requires sanitized hosted runtime parity before Codex starts: Codex auth, required CLI tools, runtime-local `node`/`npm`/`corepack`/`pnpm`/`yarn` for WebCore UI/browser work, browser-smoke readiness when prompted, and a per-run `environment_parity.json` artifact. `wb-core` production execution additionally requires GitHub CLI `gh`, runtime GitHub token, repo write permission, HTTPS git auth and wb-core deploy SSH readiness before the target production lock is acquired.
- `wb-core` production merge/deploy is serialized by the single target production lock.
- MVP lock wait semantics are controlled: if the lock is active at production-lane start or before production execution, the run enters `waiting_for_target_lock` with the active run id. A durable queue is future scope.
- The production lane records the managed-clone base ref and blocks deploy if `origin/main` changed before merge/deploy; the operator must rerun/reverify on current main.

Security model:

- The main hosted UI remains behind the reverse-proxy Basic Auth boundary.
- `/mcp` is a public no-auth exception for ChatGPT-compatible read-only discovery/calls. Public no-auth `tools/list` exposes only read tools, each annotated with `readOnlyHint=true` and `noauth` metadata. Direct no-auth write calls return a controlled denial with OAuth metadata.
- Authenticated target docs tools are not public no-auth read tools. Public discovery hides them, direct no-auth calls return a controlled denial, and authenticated discovery marks them read-only with OAuth-session metadata.
- OAuth protected-resource and authorization-server metadata are public under `/.well-known/...`; dynamic client registration and token exchange are public protocol endpoints; `/oauth/authorize` inherits the reverse-proxy Basic Auth user gate. OAuth clients/codes/access grants/refresh grants are durable runtime state collections, grants are stored as hashes, and status exposes sanitized reconnect diagnostics for unauthenticated calls, expired tokens, missing scope, missing client/grant, resource metadata mismatch, refresh-token expiry/revocation/reuse and missing `offline_access`. Authorization codes are single-use and expired/used codes are cleaned during normal OAuth/status activity. Access tokens remain short-lived. When `offline_access` is requested, the authorization-code exchange issues a hash-stored refresh token; refresh-token exchange rotates the refresh token, revokes the old token and revokes the full family if an old token is reused. Expired grants and stale registered clients are cleaned after retention. Tokens, Authorization headers, cookies, raw provider bodies and secret material are never logged or returned outside protocol-required responses. ChatGPT connector/link-cache failures such as transient `404 Link not found` remain external, but DevControl reports the server-side OAuth/resource/grant state needed to diagnose them.
- MCP write tools additionally support the existing separate bearer token stored outside the repo through `apps/dev_control_plane_setup.py mcp-token` or `generate-mcp-token` for bounded protocol/API smoke and direct controlled calls. Static bearer is not the ChatGPT UI auth strategy.
- Read tools are sanitized and must not return secrets, raw provider bodies, Authorization headers, cookies, Codex auth/session material, `.env` files or secret artifacts.
- Every MCP tool call appends a sanitized audit entry under the state logs directory with timestamp, tool, caller/source, run id, result status and blocker. It does not log token values or raw task prompts.
- There is no arbitrary shell/command tool.

## Hosted Live Monitor

The hosted service exposes a permanent run monitor at `GET /runs/live` and per-run pages at `GET /runs/<run_id>/watch`. The main operator page links to it as `Мониторинг`. These routes are part of the main operator UI and must remain behind the existing reverse-proxy Basic Auth boundary; they are not MCP no-auth exceptions.

The live monitor consumes the same run state as MCP and the hosted UI:

- `GET /api/runs/live` lists active/recent runs in deterministic effective-recency order. Active runs use last activity/update time; terminal runs such as `post_deploy_passed`, `production_complete`, `partially_deployed`, failed, cancelled and stale use finish time first, then update/start/create fallback. This keeps a just-finished run at the top instead of dropping it below older cards.
- `GET /api/runs/<run_id>/live` returns sanitized detail, frozen prompt preview, changed files, verifier state, PR/merge/deploy/probe fields when present, blockers, Codex process/stale assessment and final report/handoff preview.
- `GET /api/runs/<run_id>/timeline` returns sanitized `logs/timeline.jsonl` events and supports a cursor for incremental reads.
- `GET /api/runs/<run_id>/log-tail` returns a bounded sanitized tail from `logs/terminal.log` and supports a byte offset for append-only terminal rendering.
- `GET /api/runs/stream` and `GET /api/runs/<run_id>/stream` provide read-only SSE updates, with polling fallback in the page.

The terminal and prompt panels are viewers only. They expose no input, prompt editing, command paste or shell execution path. The browser keeps `selectedRunId` pinned unless the run disappears, updates rows by stable `run_id`, appends terminal chunks by offset, preserves scroll position, and closes/quietens per-run live updates when a run reaches terminal status. Running stage cards show a spinner/pulse, elapsed time and last activity independently from terminal output. It preserves allowed ANSI SGR color/style sequences and approximates carriage-return spinner updates, while stripping OSC, DCS, APC, PM, clipboard/title/hyperlink controls and arbitrary cursor/control sequences. Because this repo does not vendor a pinned `xterm.js` asset and CDN loading is prohibited, Stage 1 uses a small local ANSI SGR renderer rather than adding an unreviewed browser terminal dependency.

Monitoring cards use operator lifecycle semantics rather than raw run color. Direct verifier-passed production-capable work is amber `Готово к выкладке`; green `В проде` is reserved for production-complete / deployed / public-verified state. Historical sprint/parallel records are read-only generic artifacts only and are never selectable for promotion. Cards show short human task titles, compact timing, changed-file hints, blockers and production linkage, with long ids visible only as secondary detail. The UI must not expose selected-promotion groups, sprint parent/child controls, parallel queues or managed-clone fallback controls. True verifier/deploy/security/GitHub/SSH blockers remain red. Local/test profiles stay fail-closed or stubbed.

The monitor must never serve raw logs. Run writers append sanitized timeline and terminal artifacts (`logs/timeline.jsonl`, `logs/terminal.log`), keep raw Codex event logs as machine artifacts, and API readers sanitize again before returning data. Secret markers, Authorization headers, bearer values, cookies, API key patterns, env secret assignments, Codex/OpenAI auth material, sensitive secret paths and risky traceback content are redacted. Common Codex JSONL metadata envelopes such as token usage and turn completion are hidden from the default terminal view; assistant/handoff text is rendered as readable text with escaped newlines decoded. Item lifecycle and command execution events are expanded into human-readable transcript lines with timestamps, ids, command text, status, exit code, duration and bounded output excerpts.

Bounded run-control APIs are available only behind the same Basic Auth boundary: `POST /api/runs/<run_id>/cancel` and `POST /api/runs/<run_id>/mark-stale`. They do not accept shell commands and do not mutate targets. Cancel checks recorded process ownership before signaling the run-owned Codex process group and preserves artifacts/workspaces. Mark-stale records a controlled blocked/stale state for lost processes. On service restart, `running_codex` runs are reconciled as live, `stale_timeout` or `stale_lost_process` based on recorded process/activity state. Status readers keep raw status and observer diagnostics separate from effective activity: if DevControl fails but Codex is still alive or logs move after the failure, the effective state is `control_error_codex_running`; if a handoff exists but verifier is missing after a control error, the effective state is `needs_verifier_after_control_error`. The hosted status payload reports sanitized watchdog readiness, limits and IO mode; `event` capture is the safe default, while PTY capture is optional runtime config and disabled unless explicitly validated.

ChatGPT auth strategy: current ChatGPT Developer Mode app setup docs document OAuth, No Authentication and Mixed Authentication, not a static bearer-token field for ChatGPT UI setup. Stage 1 therefore chooses `mixed_noauth_read_oauth_write`: no-auth read tools remain connectable, write tools stay hidden/denied without auth, and authenticated discovery exposes write tools only after OAuth `dcp.write`. Write tools must not be exposed as unauthenticated to bypass connector setup issues.

The former sprint loop, `DEVCONTROL_START_SPRINT_V1` bridge, curator ping-pong, parent/child decomposition, parallel task intake/execution/reconcile/promotion and managed-clone-only operator fallback are removed from the runtime/operator architecture. Future orchestration must be introduced as a new explicit policy and must not reuse hidden legacy MCP tools.
