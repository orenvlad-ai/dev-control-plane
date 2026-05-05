# Hosted Control Plane Architecture

## Summary

This document fixes the target architecture for a future hosted `dev-control-plane` service. The control-plane remains a standalone project. Product repositories such as `wb-core` are external target projects connected through target adapters; they are not this repo's identity and must not become part of the control-plane runtime.

The intended operator outcome is practical: an approved target task produces verifier artifacts, a GitHub PR, deploy evidence and a curator handoff. The first production-capable target is `wb-core`; other target repos remain read-only/decision-only until they receive their own explicit apply policy.

This is an architecture and governance document. The current implementation covers the local/hosted-ready filesystem state foundation, loopback-only hosted server runtime foundation, dev-control-plane repo self-closure policy, remote managed target source, decision-only target PR/preview/approval gates, and an explicit `wb-core` production lane. It does not authorize public routes beyond the approved dev-control-plane host, real target execution without managed clone, production deploy for non-`wb-core` targets, external WB live actions, database/data mutations or secrets handling changes.

## Server Layout

The hosted control-plane should be deployed as its own service and host boundary, separate from any target product runtime.

Normative layout:

- Web/UI service: Russian chat-first cockpit, target selector, task card review, run timeline and result summary.
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
- Deploy runner: `apps/dev_control_plane_hosted_deploy.py` with `print-plan`, `validate`, `deploy --dry-run`, `deploy --live`, `loopback-probe`, `public-probe`, `webcore-probe` and `rollback-plan`.
- Service template: `deploy/examples/systemd/dev-control-plane.service`.
- Environment template: `deploy/examples/systemd/dev-control-plane.environment.example`.
- Reverse-proxy template: `deploy/examples/reverse-proxy/nginx.dev-control-plane.conf.example`.
- Runbook: `docs/runbooks/01_hosted_server_mvp.md`.

These files are templates and instructions only. This repo does not apply systemd units, reverse-proxy configuration, SSH/root commands, public routes or live deploy.

## State Directories

Hosted state must be explicit and separate from repo source. The current implementation resolves state through `DEV_CONTROL_PLANE_STATE_DIR` or `/tmp/development-control-plane-state` and must not write runtime state into tracked paths.

Implemented logical layout:

```text
state/
  collections/
    discussions.json
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

## Managed Workspaces

Codex execution must happen only inside a managed clone or managed workspace owned by the control-plane. The original target repo working tree is read-only context.

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

The current general implementation provides decision-only target PR planning in `src/dev_control_plane/target_workflow.py`, runner commands and server endpoints. The plan uses branch names of the form `devcp/<run_id>-<slug>`, Russian commit/PR text, a required PR description, verifier result, changed files, preview URL and rollback/close instructions. The explicit `wb-core` production lane in `src/dev_control_plane/target_production.py` is the exception: it may execute GitHub PR creation/merge and production deploy only after verifier, secrets, forbidden-path, rollback and head-SHA gates pass.

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
- Real Codex is gated and managed-clone-only.
- Current local UI/runner managed-clone output is review material until the explicit `wb-core` production lane consumes a verifier-passed run.
- Current runner/server code has a unified filesystem state layout for runs, artifacts, logs, verifier output, cockpit collections and managed workspaces.
- Current safe/fake/managed-Codex flows do not commit, push, merge, deploy or apply changes to original target repos; only the explicit `wb-core` production lane may mutate the target through PR/merge/deploy gates.
- Current smoke coverage uses fake/stub Codex/OpenAI paths and must not call real providers.
- The `wb-core` adapter policy aligns with this boundary: remote managed clone is enabled, direct original-repo mutation remains disabled, and production deployment is available only after the production-lane gates pass.

## Known Gaps

- A filesystem state layout exists, but a durable hosted database/object-store backend and retention policy are not implemented.
- Hosted server deploy templates exist, but no live deploy automation or public reverse-proxy application is implemented.
- Live deploy automation is repo-owned but must stop when DNS or auth-boundary safety gates are not clean.
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
4. Create `devcp/<run_id>-<slug>` branch in `wb-core`; never push directly to `main`.
5. Commit with Russian message and required run/task summary.
6. Open a PR with Russian title/body containing run id, changed files, verifier, docs status, deploy plan and rollback plan.
7. Merge only when PR head SHA matches expected head.
8. Record pre-merge main commit and merge commit.
9. Create a rollback/app backup and then deploy only from merged `main` through `apps/registry_upload_http_entrypoint_hosted_runtime.py`.
10. Run loopback, public and task-specific post-deploy checks.

The lane blocks deploy if rollback plan is missing, verifier failed, forbidden paths changed, secrets scan failed, the target PR was not merged, the deploy runner is missing, or public verification fails.
