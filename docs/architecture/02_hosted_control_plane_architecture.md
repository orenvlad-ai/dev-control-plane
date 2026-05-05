# Hosted Control Plane Architecture

## Summary

This document fixes the target architecture for a future hosted `dev-control-plane` service. The control-plane remains a standalone project. Product repositories such as `wb-core` are external target projects connected through target adapters; they are not this repo's identity and must not become part of the control-plane runtime.

The intended operator outcome is practical: an approved task produces a GitHub PR, a preview or staging URL, verifier artifacts and a curator handoff. The operator can review the result in the morning without allowing automatic production merge or production deploy.

This is an architecture and governance document only. It does not authorize code changes, live deployment, public routes, real target execution or secrets handling changes in this step.

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

Hosted state must be explicit and separate from repo source. A future implementation should make these directories configurable and should not write runtime state into tracked paths.

Recommended logical layout:

```text
state/
  targets/
    <target_id>/snapshots/
  runs/
    <run_id>/
      task_spec.json
      prompt.md
      handoff.md
      diff.patch
      verifier_report.json
      timeline.jsonl
      preview.json
  workspaces/
    <run_id>/<target_id>/
  logs/
    <run_id>/
```

Current `.gitignore` already treats `state/`, `runs/` and `workspaces/` as local/runtime-only paths. Hosted state must follow the same rule: it is operational data, not source code and not project-pack content.

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

## PR Lifecycle

The future PR lifecycle should be explicit and auditable:

1. Curator drafts a bounded TaskSpec from operator discussion and target context.
2. Operator approves freeze and execution class.
3. Worker creates a managed clone from the target base commit.
4. Codex runs one bounded task inside the managed clone.
5. Verifier checks diff hygiene, forbidden paths/actions, prompt/handoff contract and target-specific checks.
6. Worker creates a target repo branch from the managed clone output only after verifier passes.
7. Worker opens a GitHub PR with summary, changed files, verifier report and preview/staging link when available.
8. Control-plane stores PR URL, branch, commits, verifier report and preview metadata in run state.
9. Curator/operator reviews the PR and preview result.

The control-plane may prepare the PR and preview. It must not automatically merge to the target default branch in the current architecture.

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
- Production merge/deploy: not automatic; requires separate human approval outside the current automated workflow.

The UI must explain gate state without exposing raw secrets or arbitrary shell controls.

## Prohibitions

The hosted control-plane must not:

- Mutate the original target repo working tree directly.
- Run Codex outside a managed clone/workspace.
- Auto-merge PRs into production branches.
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
- Real Codex is gated and managed-clone-only.
- Current local UI/runner output is review material.
- Current flows do not commit, push, merge, deploy or apply changes to original target repos.
- Current smoke coverage uses fake/stub Codex/OpenAI paths and must not call real providers.
- The `wb-core` adapter policy aligns with this boundary and does not need a path change for this architecture task.

## Known Gaps

- Hosted server state layout is not implemented.
- Multi-worker scheduling and durable job recovery are not implemented.
- GitHub PR creation from managed workspace output is not implemented.
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
- Runner/server/UI implementation changes.
- Automatic merge or production deploy.

## Blockers

Before implementation, the project needs explicit decisions for:

- Hosted state backend and retention policy.
- Workspace cleanup and artifact retention.
- GitHub app/token model for creating branches and PRs without leaking credentials.
- Preview/staging target adapter contract.
- Verifier contract for preview URLs and target-specific smoke scope.
- Human approval UX for PR creation, preview deploy and production handoff.
- Secret-store provider and API redaction policy for hosted mode.
