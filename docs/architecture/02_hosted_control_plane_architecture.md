# Hosted Control Plane Architecture

## Summary

This document fixes the target architecture for a future hosted `dev-control-plane` service. The control-plane remains a standalone project. Product repositories such as `wb-core` are external target projects connected through target adapters; they are not this repo's identity and must not become part of the control-plane runtime.

The intended operator outcome is practical: an approved target task produces a GitHub PR, a preview or staging URL, verifier artifacts and a curator handoff. The operator can review the result in the morning without allowing automatic target production merge or production deploy.

This is an architecture and governance document. The current implementation covers the local/hosted-ready filesystem state foundation and dev-control-plane repo self-closure policy; it does not authorize live deployment, public routes, real target execution, target repo PR apply/merge, preview deploy or secrets handling changes.

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

Managed workspace output is review material until an explicit apply/PR policy runs.

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

This means the adapter permits managed-clone review work but blocks direct product-plane mutation. Future target adapters must follow the same default unless a separate approved governance task changes the policy.

## Target Repo PR Lifecycle

The future target repo PR lifecycle should be explicit and auditable:

1. Curator drafts a bounded TaskSpec from operator discussion and target context.
2. Operator approves freeze and execution class.
3. Worker creates a managed clone from the target base commit.
4. Codex runs one bounded task inside the managed clone.
5. Verifier checks diff hygiene, forbidden paths/actions, prompt/handoff contract and target-specific checks.
6. Worker creates a target repo branch from the managed clone output only after verifier passes.
7. Worker opens a GitHub PR with summary, changed files, verifier report and preview/staging link when available.
8. Control-plane stores PR URL, branch, commits, verifier report and preview metadata in run state.
9. Curator/operator reviews the PR and preview result.

The control-plane may prepare the target PR and preview in a future apply policy. It must not automatically merge to a target default branch in the current architecture.

## Preview And Staging Lifecycle

Preview/staging is the intended proof surface for target changes. It is separate from production.

Required preview/staging behavior:

- Create preview from the PR branch or an immutable build artifact tied to the PR commit.
- Store preview URL, deploy revision, environment name and verifier status in run metadata.
- Show preview URL in the cockpit result summary and curator handoff.
- Run content-level or route-level verifier checks against preview/staging when target policy defines them.
- Tear down or expire preview environments according to retention policy.

Preview/staging deploy is allowed only after a separate implementation task defines target-specific deploy adapters and safety gates. Production deploy remains manual and out of scope for this stage.

## Curator Approval Flow

Approval gates separate drafting, execution, PR creation and production decisions.

Expected gates:

- Task intake: operator chooses target project and describes the task.
- TaskSpec freeze: curator draft becomes immutable only after policy validation.
- Real Codex run: operator approval is required before a managed-clone Codex run.
- PR creation: allowed only after verifier passes and target policy allows branch/PR creation.
- Preview/staging deploy: allowed only after target preview policy exists and the operator or policy gate approves it.
- Dev-control-plane repo self-merge: allowed only under the clean gates in this document.
- Target production merge/deploy: not automatic; requires separate human approval and a future explicit target apply/deploy policy.

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
- Codex-owned dev-control-plane PRs may be self-merged, including L3, only after clean merge eligibility gates pass and no `NO_AUTO_MERGE` instruction is present.
- Runner/server closure workflow now exposes a decision-only gate backed by `src/dev_control_plane/github_closure.py`.
- Real Codex is gated and managed-clone-only.
- Current local UI/runner output is review material.
- Current runner/server code has a unified filesystem state layout for runs, artifacts, logs, verifier output, cockpit collections and managed workspaces.
- Current flows do not commit, push, merge, deploy or apply changes to original target repos.
- Current smoke coverage uses fake/stub Codex/OpenAI paths and must not call real providers.
- The `wb-core` adapter policy aligns with this boundary and does not need a path change for this architecture task.

## Known Gaps

- A filesystem state layout exists, but a durable hosted database/object-store backend and retention policy are not implemented.
- Multi-worker scheduling and durable job recovery are not implemented.
- GitHub PR creation from managed target workspace output is not implemented.
- The decision gate does not perform the actual GitHub merge through server-side credentials; external `gh` closure remains the explicit mutation step.
- Preview/staging deploy adapters are not implemented.
- Preview verifier contracts are not implemented.
- Production approval and deployment policy is intentionally undefined for automation.
- Secret-store integration for hosted runtime is not implemented.
- Target-specific branch naming, commit author policy and PR labeling policy are not implemented.

## Not In Scope

- Product code changes.
- Changes to `wb-core` or any target repo.
- Changes to `dev_control_plane_docs_master/` or manifest files.
- Live deploy, public routes, SSH/root operations or production runtime changes.
- Real Codex execution against a target.
- Real OpenAI API calls.
- Target repo GitHub PR creation, preview deploy, target auto-merge and production deploy implementation.
- Automatic target merge or production deploy.

## Blockers

Before implementation, the project needs explicit decisions for:

- Hosted state backend and retention policy.
- Workspace cleanup and artifact retention.
- GitHub app/token model for creating branches and PRs without leaking credentials.
- Preview/staging target adapter contract.
- Verifier contract for preview URLs and target-specific smoke scope.
- Human approval UX for PR creation, preview deploy and production handoff.
- Secret-store provider and API redaction policy for hosted mode.
