# DCP `wb-core` end-to-end release and deploy v1 contract

contract_status: reviewed WBC/source and corrective-pin authority; corrected runtime not installed

date: 2026-08-18

scope: exact public `orenvlad-ai/wb-core`; DCP profiles `repo-only` and
`live-runtime`

## 1. Purpose and predecessor

This contract authorizes one sequential integration and qualification program.
It supersedes only the terminal blocker recorded by the
[`wb-core` CI truth and lifecycle UX v1 evidence](DCP_WB_CORE_CI_TRUTH_LIFECYCLE_UX_V1_TERMINAL_EVIDENCE.md).
It does not weaken the
[`wb-core` Release Train handoff v1 contract](DCP_WB_CORE_RELEASE_TRAIN_HANDOFF_V1_CONTRACT.md),
the configured-required-check rule, the Codex permission/direct-executor
routing contracts, Human Gates or WBC production safety.

The predecessor identity is immutable:

- task/card/session `wbc-canary-v1` / `1` / `wb-core-1`;
- PR #987, branch `ao/wb-core-1/root`, admitted head
  `e8cca45f3995b8181fe81ead154f7a933dbacbe8`;
- initial worker action sequence `71` once, reviewer sequence `72` once,
  approved ReviewRun `1a8c6c60-4bf8-40fd-845e-19a22e878bfc` once and
  admission sequence `31` once; and
- the successful exact-head `baseline`, Actions-owned
  `base-behind-after-admission` event and DCP `release_state_drift` incident.

No submit, replacement task/card/session/branch/PR, second initial worker or
manual release action may replace this identity. The program is not complete
at a documentation, source, pin, install or repo-only merge boundary. Technical
completion requires both this existing canary at exact `release:done` and one
separately named DCP `live-runtime` canary at exact `release:production`.

## 2. Authority and activation order

DCP daemon/SQLite remains the sole local task, action, review, readmission,
admission and observation authority. GitHub remains the sole PR, head, check,
review, label, merge and release-fact authority. The WBC GitHub Actions Release
Train remains the sole physical `wb-core` merge and production deploy actor.
DCP `MergePullRequest` is statically ineligible for this target in every
profile and generation.

Activation is strictly sequential:

1. merge this reviewed pre-runtime authority;
2. merge any required backward-compatible WBC marker/handoff/deploy-proof
   change through the ordinary protected WBC Release Train;
3. merge the managed DCP Orchestrator source change after exact-head semantic/
   security review and all source/package gates;
4. merge a separate immutable dev-control-plane pin/install guard;
5. perform one governed stop, deterministic build/install/preflight and
   controlled start only after exact identity and zero-active-model proof;
6. recover and terminalize the existing repo-only canary;
7. update the local curator bootstrap only after installed authority is proven;
8. submit exactly one new `live-runtime` canary through the canonical DCP
   submit surface and take it to exact production proof; and
9. merge terminal evidence/current-authority updates.

A documentation merge activates no source or runtime. A source merge is only
build input until the separate immutable pin and deterministic install pass.
Every newly proved implementation defect first receives a model-free failing
regression, then an ordinary reviewed correction and repin/install when the
installed artifact changes. Historical failures remain immutable evidence.

The backward-compatible WBC seam is published by PR #990: exact reviewed head
`2e0c259eb76ce0c1e9099731fb027ffb2f0cdc92`, successful `baseline` run
`32104852167`, Release Train run `32105480248`, fresh baseline
`32105512736` and Actions-owned merge/main
`63dad723d40b0a2e22e1944ccd5700cf4c1f28c3` with `release:done`.

Managed-source PR #64 exact head
`141d72420e7d2e749f6bd33b1033535f0c8afa92` passed semantic/security review
`PRR_kwDOTydt6M8AAAABJ57SmQ`, zero review threads and source/package workflow
`32123765975`, then merged normally at source
`6c48702416ec8ddb657ef4d3fe64ceb8e818ed65`, tree
`86c48465f303fa398975052bdf32a9424a3a4e59`. Pin PR #230 merged at
`e9a5df8a1836ddd8e0565b46e05b188065280ad8`; deterministic install receipt
`aa06cc42af7eed66438feaecdf0f33fb6e31111812be7da9968856c1fd14b9de`
proved migration 0080 and dual-profile rules v2. Its first claimed generation
then exposed one implementation-only boundary: the unchanged worker shell had
been archived by stock UI cleanup as exact `exited` / `terminated`, so the
general incident candidate refused to advance the durable readmission lease.

Managed-source PR #65 exact head
`45ef29fb27f74d464f324613d6ad57a54fa73d31` passed semantic/security review
`PRR_kwDOTydt6M8AAAABJ6SM5g`, zero threads and source/package workflow
`32127715980`, then merged normally at source
`13e8ce2968c516ce8f9b64b4e096010d9161445b`, tree
`2462a0ee67a033d6208a8b3d0972bb8426038b85`. It permits only the exact
`wb-core` `release_state_drift` incident with the exact incident admission
binding and paired archived shell to resume; the general incident/arbiter
candidate and every identity/provider/review gate remain unchanged. The lock
selects this correction, but the installed running bundle remains source
`6c487024...`, tree `86c48465...`, receipt `aa06cc42...` until the separate
corrective pin merge and governed deterministic replacement succeed.

## 3. Stable versioned WBC seam

DCP depends only on a small typed provider interface, never on Release Train
workflow names, job names, matrices or internal queue topology:

- exact repository/provider/base/PR/head/branch and configured
  `RequiredCheck` facts;
- an immutable Actions-owned versioned readmission event;
- an exact DCP admission handoff bound to `release:ready`; and
- a target-profile terminal proof (`release:done` for `repo-only`,
  `release:production` for `live-runtime`).

The existing `wb-core.dcp-release-handoff/v1` repo-only behavior remains valid.
A backward-compatible successor version may add fields and `live-runtime`, but
must not alter ordinary non-DCP STANDARD or LOOP behavior. Removing or renaming
non-required Release Train jobs must require no DCP source change.

Every trusted event/proof is an immutable GitHub comment or equivalent
repository fact created by `github-actions[bot]`, with stable marker/version,
creation time equal to update time, exact cardinality and no later contradictory
event. Edited, deleted, duplicated, malformed, foreign, stale or crossed
evidence is inert and fails closed.

## 4. Generic event-driven fresh readmission

### 4.1 Generation identity

One readmission generation binds at least:

- repository and provider repository/owner identity;
- base ref, exact current provider main and observed provider timestamp;
- DCP task/session/card, task class, scope/profile, native branch and PR;
- prior admitted head, exact required-check name/result/evidence and exact
  DCP admission/ready event;
- readmission reason, marker version, Actions actor, event id and timestamps;
  and
- an integrity digest over the canonical envelope.

For legacy v1 repo-only evidence, the immutable Actions marker, exact GitHub
timeline/check facts and immutable DCP task/admission row form one compatibility
envelope; every field above must still resolve uniquely and agree. This is a
version adapter, not a task-number migration. Future successor events carry or
cryptographically bind the complete envelope directly.

The database stores one immutable generation/evidence row and one durable
lease per exact event. Equal startup, provider, webhook or event replay returns
the same row. A different valid later event creates exactly one later
generation. Conflicting identity, two live leases or crossed events fail
closed. No timer, heartbeat, watcher, unbounded poller or AI retry is added.

### 4.2 Model-free branch advance

After exact provider refresh and lease claim, the daemon may advance only the
same existing source branch and PR. The permitted strategy is one mechanical
two-parent Git merge whose first parent is the event's admitted head and whose
second parent is the event's exact current main:

- source branch remote head must still equal the admitted head;
- current main must be the exact provider main and a descendant of the
  generation's admitted base;
- the task worktree and canonical target must be clean and exact;
- Git's merge-tree calculation must be conflict-free;
- the generated commit tree and two parents are independently postvalidated;
- push is a normal fast-forward of the existing branch, never force/rebase;
- post-push PR head must equal the generated head; and
- no file content or product intent is authored by this operation beyond the
  mechanically computed merge tree.

Any content conflict, ambiguous ancestry, foreign commit, head/base drift,
dirty path, provider mismatch, push race or postvalidation mismatch produces
no branch mutation. A genuine conflict follows the existing bounded typed
conflict/arbiter/Human-Gate authority; it is never guessed.

### 4.3 Fresh gates and dedupe

The generated head inherits no prior review, check or admission. It must
receive one exact successful configured `baseline`, exactly one fresh
context-free reviewer for that head, a new FIFO admission and a new exact
`release:ready` event. Missing, pending, duplicate, wrong-head, cancelled,
failed or malformed required-check evidence cannot pass. Head/base drift at
review, admission or release creates no stale approval.

Each generated head has at most one reviewer action. Global three-model-action
accounting remains unchanged; the branch advance and all provider waits consume
zero model slots. Restart at any fence resumes or deduplicates the same lease,
generation, push, reviewer, admission and release event. Competing tasks retain
the single serialized FIFO admission/release line. No duplicate initial worker,
task, card, session, PR, branch or release event is possible.

## 5. Exact target profiles

Both profiles bind exact public `orenvlad-ai/wb-core`, repository ID
`1201929580`, owner ID `237411244`, base `main`, task label `task:standard` and
required check `baseline`.

### `repo-only`

- exactly label `scope:repo-only`;
- DCP may add only exact-head `release:ready` after fresh review/FIFO admission;
- WBC Actions exclusively merges and adds `release:done`; and
- DCP terminal success requires exact merge SHA plus the versioned Actions-owned
  repo-only completion proof. A deploy state is never invented.

### `live-runtime`

- exactly label `scope:live-runtime`;
- worker, repair, reviewer and arbiter remain repository-only model roles with
  no production, SSH, secret, runtime-data, business-data or WB API authority;
- DCP may add only exact-head `release:ready` after fresh review/FIFO admission;
- WBC Actions exclusively merges the reviewed head and invokes the existing
  canonical exact-SHA deploy-and-verify path; and
- DCP terminal success requires exact merge SHA, `release:production`, exact
  deployed SHA equal to that merge, Actions-owned deploy/verify proof, exact
  canonical target and service identity, and the required loopback/public probe
  identities and successful results.

Merge alone, `release:done`, stale deployed SHA, missing/ambiguous proof,
inactive service, missing mandatory probe or `release:halted` is nonterminal or
fail-closed. DCP gains no production credential and may not SSH, deploy,
restart the production service, mutate business data or add a second train.
The WBC workflow must preserve production Environment, secret, clean checkout,
exact-SHA, target, service and probe gates.

Preflight, adapter registration, managed-source target specification and the
actual native project must agree for both profiles before task mutation. The
shared project rules may describe both release profiles, but every model role
receives the same repository-only filesystem/network/secret boundary. Equal
submit is idempotent; conflicting replay remains blocked.

## 6. Continuous lifecycle and notifications

`modelActive` continues to mean an actually claimed/running worker, repair,
reviewer or arbiter and is the only model-slot input. `workflowActive` means the
autonomous policy chain is open and remains true through queued/running model
work, CI/provider refresh, readmission, review, arbiter, FIFO admission,
Release Train, merge observation and target-applicable deploy/verify waits.
Passive waits own zero model slots, processes, timers and tokens.

One typed projection is used by board card, sidebar dot, details/header,
accessibility text and notifications. It provides truthful phase copy including
`Waiting for CI/GitHub update`, `Reviewer queued`, `Waiting for Release Train`,
`Release Train running`, `Waiting for deploy` and `Deploy running`. The same
gentle activity indicator denotes an open automated lifecycle, never model-slot
consumption. `prefers-reduced-motion` disables motion without losing state text.

Exact Human Gate/Needs You and actionable technical failure are steady and
clear. Repo-only is terminal steady green only after `release:done` proof.
Live-runtime is terminal steady green only after `release:production` proof;
merge before deploy remains active/nonterminal. Generic stock
`ready_to_merge`, merge-success or CI-success notifications are suppressed for
DCP policy sessions until policy truth permits them. Admission wording is
`Ready for / waiting for Release Train`; live merge wording is deploy pending/
running; terminal wording is emitted only from the applicable proof.

Fixtures must cover the full forward paths, every passive wait, actual model
activity, Human Gate, technical error, stale SCM summaries, reduced motion,
all-surface equality and notification dedupe with zero live model calls.

## 7. WBC compatibility and production proof

The WBC compatibility change is limited to Release Train authority, workflow,
implementation, specification/tests and directly necessary provenance/docs.
It must:

- preserve v1 repo-only and ordinary non-DCP behavior;
- recognize only exact DCP branch/task/scope/handoff identity;
- prohibit WBC auto-sync after admitted-head drift for both DCP profiles;
- emit the versioned Actions-owned readmission envelope instead;
- use the existing exact configured baseline and current-head gates;
- for DCP live-runtime, capture and validate the existing canonical
  deploy-and-verify result or an equivalent read-only exact-SHA reconciliation
  result before writing a versioned completion proof and
  `release:production`; and
- expose stable proof fields rather than workflow/job names.

The production proof binds PR, DCP session/task/profile, reviewed/admitted head,
merge SHA, deployed SHA, target id `wb_core_eu_hosted_runtime_active`, canonical
service identity, deployment-complete evidence, required probe identities,
sanitized results, Actions actor/run and immutable timestamps/digest. It never
contains secrets, cookies, SSH material or business data.

## 8. Qualification executions

### Existing repo-only canary

After installed source is proven, consume the exact valid predecessor
readmission envelope under the generic mechanism. Preserve the original
incident/evidence, create only the required generation merge head, one fresh
baseline/reviewer/admission/handoff and let WBC Actions produce the exact
merge, `release:done` and terminal proof. Later main advances use later valid
generations on the same identity. No resubmit, repair-by-hand, arbiter for a
deterministic merge, manual label or manual merge is allowed.

### One new live-runtime canary

Only after repo-only terminal proof and installed dual-profile preflight, submit
one new unique task id through the canonical `dcp-ao-submit` surface. Its
product slice is the smallest reversible, secret-free, no-business-effect
runtime provenance qualification on an existing read-only health/status/
provenance surface. It adds no public route breadth, auth/security change,
dependency, systemd/nginx change, business logic, schedule, stored/runtime/
business data or WB call. If current code cannot support such a slice without a
material choice, the exact Human Gate is required.

The task follows one initial worker, configured baseline, fresh context-free
review, at most the existing single findings repair plus fresh review, FIFO
admission, `release:ready`, WBC Actions exact merge/deploy/verify,
`release:production` and DCP terminal observation. Concurrent main advancement
uses the same generic readmission generations, never resubmit/replacement.

After terminal proof, one controlled DCP restart must prove no duplicate
worker, reviewer, readmission generation, admission, release or deploy
observation and zero active model actions.

## 9. Curator bootstrap boundary

The local `DCP_WBC_curators` bootstrap is a consumer, never architecture
authority. It may be updated only after the corresponding repository source,
pin, install and dual-profile preflight are proven. It must dynamically re-read
current repository authorities and permit:

- `repo-only` for code/docs/tests with terminal `release:done` and no deploy;
- `live-runtime` only after explicit owner deploy authorization, with terminal
  `release:production`; and
- one canonical submit, one unique 1-16 character task id and one non-empty
  prompt of at most 512 UTF-8 bytes.

It may not authorize `production-mutation`, direct execution, SSH, secrets,
business data, curator polling, a second submit or direct WBC release action.

## 10. Required regressions and review

Model-free tests must reproduce the current behind-main incident before the
fix and cover:

- one and multiple sequential main advances, competing tasks and restart at
  every generation/lease/push/review/admission/release fence;
- legacy v1 compatibility plus complete successor marker validation;
- stale, duplicate, edited, deleted, foreign, malformed and crossed evidence;
- clean merge generation, conflict, ancestry/head/push races and postvalidation;
- missing/pending/duplicate/wrong-head/cancelled/failed required baseline;
- reviewer/action ceiling and zero duplicate/model-call leakage;
- direct `wb-core` merge ineligibility and exact-head `release:ready` dedupe;
- repo-only `release:done` and live-runtime exact production-proof validation;
- missing/stale/wrong target/service/SHA/probe proof and `release:halted`;
- lifecycle/UI/notification truth and restart dedupe; and
- adapter/source/native-project parity for both profiles.

Run repository-owned audits, serial/race Go tests, vet/build, generated SQL/
OpenAPI/TypeScript parity, frontend typecheck/renderer tests and package/artifact
gates as applicable. Every PR is ordinary, non-draft, exact-head reviewed,
green, thread-clean and normally merged. No force-push or history rewrite is
permitted.

## 11. Exclusions and terminal acceptance

Out of scope are `scope:production-mutation`, business-data mutation/backfill,
WB writes, manual/ad-hoc SSH or deploy, secret rotation, auth/security changes,
new destinations, WBC product work outside the single canary, unrelated PRs,
legacy cleanup, a second daemon/database/service/train/deployer/watcher/poller/
timer, installed/retired AO, updater/telemetry and owner-acceptance synthesis.

Technical `COMPLETE` requires together:

- PR #987 terminal `release:done` in DCP with one initial worker total;
- installed generic readmission and restart/dedupe proof on the real incident;
- installed exact dual-profile target plus the updated bootstrap consumer;
- exactly one new live-runtime task terminal `release:production` from exact
  Actions merge/deployed SHA, target/service and required probe proof;
- truthful installed UI/notifications through all observed phases;
- clean final DCP/source/WBC main readbacks, SQLite integrity and zero active or
  duplicate actions; and
- zero Codex platform approval prompts and one final technical handoff from the
  same visible direct-executor task.

A final `BLOCKED` is permitted only for an evidenced strictly human credential/
production Environment action, unsafe material product/risk decision, new
external destination, irreversible condition or exhausted repo-owned safe
remediation. Temporary CI/provider/queue delay is a durable wait, not a new
task or technical closure. Technical completion is never owner acceptance.
