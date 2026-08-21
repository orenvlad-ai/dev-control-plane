# WBC integration twin Stage 3 to Stage 4 combined execution contract

contract_revision: 2026-08-20.1

contract_status: owner-approved combined program; Stage 3 active only after Stage 2 evidence merge; Stage 4 source activation conditional on independently green Stage 3

program_stages: 3 and 4 of 9

current_program_role: historical-complete Stages 3-4 authority; no current mutation authority

See the [current program manifest](DCP_WBC_INTEGRATION_TWIN_CURRENT_PROGRAM_MANIFEST.md).
Conditional activation language below records the original gate and is spent.

## 1. Authority boundary

This contract records the owner's explicit decision to run two sequential
technical stages in one visible executor pass. It does not collapse their
gates. Stage 3 must independently qualify the real lab Release Train and
persistent deploy adapter without DCP. Stage 4 managed-source work may begin
only after an ordinary reviewed/green dev-control-plane PR records Stage 3
terminal green and explicitly activates the source boundary.

Intermediate Stage 3 success is not terminal completion for the executor. A
Stage 3 failure, protected-surface drift or exhausted bounded correction stops
the combined pass `BLOCKED` before managed-source mutation.

This contract grants no Stage 5 source lock, pin, build, install, preflight,
issuer switch, DCP adapter activation or schema migration against live data. It
grants no Stage 6 submit/canary, WBC write/cutover, production mutation or owner
acceptance.

## 2. Frozen inputs

Stage 2 terminal truth is the exact record in
`DCP_WBC_INTEGRATION_TWIN_STAGE2_TERMINAL_EVIDENCE.md`. Lab work starts from
current protected `orenvlad-ai/dcp-wbc-integration-lab` main and its exact
numeric repository/ruleset/environment identities. The qualification issuer
remains the sole active issuer. DCP issuer stays absent/off.

The installed DCP predecessor remains frozen exactly as recorded in
`DCP_TASK_FIRST_NATIVE_LIFECYCLE_V1_PASS2_BLOCKED_EVIDENCE.md`: schema 83,
PR #987, admission 32 and blocker
`task_first_startup_admission_continuation_missing`. The pass may not open live
SQLite writable, start the app/daemon, continue that admission or mutate WBC.

## 3. Stage 3 independent qualification

Stage 3 uses only the lab repository, its qualification-only issuer, real
GitHub/Actions and exact persistent Selectel cell. It is entirely model-free
and uses no DCP state, label, task or model fact.

The Release Train harness MUST record these seven fixed cases:

1. A valid exact manifest produces one exact admitted-head merge, one immutable
   artifact, one real persistent install/start, successful health/provenance
   and one complete proof.
2. PR/head drift performs no ref mutation, merge or deploy and produces exactly
   one immutable `readmission_required` proof.
3. Main drift performs no update/rebase/merge or deploy and produces exactly
   one immutable `readmission_required` proof.
4. Wrong repository, base, PR or required-check identity fails before merge and
   deploy.
5. Equal duplicate manifest/event returns the same fact/proof with zero second
   merge or deployment.
6. Artifact/source/deployed-SHA mismatch produces no success proof and one
   exact deployment failure.
7. Adapter or probe failure produces no automatic retry/redeploy and no false
   terminal success.

Real inert PRs, checks, reviews, manifests, runs and persistent deployment are
used where the behavior requires them. Negative fixtures are bounded to the
lab and cannot address another repository, WBC, Luchiki or another host path.
The mechanical train has no auto-sync, rebase, update-branch, force-push, head
substitution, semantic choice, second queue or blind retry.

Failure cases MUST preserve or restore the last known-good lab release through
the adapter's bounded current/previous rollback. They may not change Luchiki,
shared host services, firewall/network, billing, retained legacy roots or a
second credential. Every persistent proof names exact case, manifest, run,
artifact, deployed SHA and effect count.

One bounded correction is permitted for each newly proven implementation
defect that remains inside this exact protocol. The original failing run and
proof remain immutable. A need for another issuer, destination, paid resource,
model, DCP fact, automatic retry, shared-host privilege or protocol expansion
is terminal `BLOCKED`.

Every substantive lab change uses an ordinary ready PR, exact-head `baseline`,
fresh context-free semantic/security review with no findings, zero unresolved
threads and exact expected-head merge through the repository-owned Release
Train. The consumed historical bootstrap exception cannot recur.

## 4. Stage 3 terminal and Stage 4 activation gate

Stage 3 is technically green only when one reviewed/green dev-control-plane
terminal-evidence PR binds:

- every case's exact manifest/evidence/proof digest and expected result;
- all PR, head, check, review, workflow, job, merge and artifact identities;
- merge/deploy/ref effect counts, duplicate counts and last-known-good final
  deployment;
- current repository/ruleset/environment/issuer and exact host/service proof;
- protected Luchiki and retained legacy invariants; and
- zero DCP runtime/database/task/model use and zero platform approvals.

That PR is the only permitted Stage 4 implementation activation. Its final
merged text must say that all seven cases are independently green and that the
exact managed-source pass below is now active. A partial, failing or unmerged
record cannot activate Stage 4.

## 5. Stage 4 provider-neutral DCP v2 core

After activation, managed-source work begins from exact current official-
ancestry `orenvlad-ai/dcp-orchestrator` main. It implements the protocol already
defined by the Stage 1 architecture, without activating the lab or WBC target:

`Task -> immutable exact-head Revision -> durable typed Command -> bounded model Action -> FIFO Admission -> verified Release/Deployment result`

Required source behavior is:

- every authoritative transition and its required next Command commit in one
  SQLite transaction;
- one idempotent command drain shared by exact event and startup entry;
- durable command idempotency, leases, side-effect fences, dedupe and crash
  reconciliation without heartbeat, watcher, timer scheduler, unbounded poller
  or blind retry;
- a terminal/process shell is only a runtime resource;
- exactly one initial worker, one shared task-level repair allowance, fresh
  review per exact head and at most three globally active model Actions;
- exact Revision/head/check/review/admission/result binding;
- finite mechanical readmission and typed incident, Human Gate and arbiter
  boundaries;
- separate `modelActive` and `workflowActive` derived through one projection
  for board/card, sidebar, detail, notification and accessibility surfaces;
- steady Human Gate and terminal error truth, active autonomous nonterminal
  workflow truth, and `Merged` distinct from `Deployed`; and
- provider-neutral repository, release and deployment interfaces with no live
  lab, WBC or current-canary special case.

Forward-only migration/source definitions may extend schema after 83, but live
SQLite is never opened writable or migrated in Stage 4. Migration tests use
disposable exact schema-83 copies and prove all predecessor rows byte-stable.

## 6. Required model-free Stage 4 proof

The source suite covers at least:

- rollback of every state-plus-next-command transaction;
- equal/conflicting command idempotency, claim lease and recovery generation;
- restart before and after command claim, model fence/result, Revision update,
  check, review, Admission, release dispatch, readmission, merge, artifact,
  deploy proof and terminal verification;
- multiple revisions and readmission generations without stale-head reuse;
- four tasks against the global three-slot ceiling;
- FIFO Admission independent of worker/reviewer completion order;
- duplicate and out-of-order provider events;
- one shared repair ceiling, no AI retry and finite arbiter/Human Gate paths;
- exact `modelActive`/`workflowActive` and all UI/accessibility projections; and
- zero lost or duplicate Command, Action, Admission or Result across every
  restart fence.

The exact source head must pass official ancestry/provenance, generated parity,
full serial tests, build/vet, relevant race suites, renderer/type/accessibility
tests, security/absence gates and connected source/package CI. It then receives
one exact-head context-free semantic/security review with no findings and zero
threads before ordinary merge.

## 7. Stage 4 source-complete boundary

After managed-source merge, a separate reviewed/green dev-control-plane
source-complete evidence PR binds the exact source head, merge, tree, review,
workflow and all model-free proof. Final authority states:

- Stages 1-4 are technically `COMPLETE`;
- Stage 5 requires a separate owner-authorized lock/pin/install pass;
- the qualification issuer remains active until Stage 5 explicitly proves it
  off and proves the DCP issuer exact;
- live DCP contains zero integration-twin Task/Action/Admission rows because no
  submit occurred; and
- no install, runtime start, WBC mutation, production action or owner
  acceptance is claimed.

Stage 4 completion is source only. A source merge is never an installed or
activated control plane.

## 8. Stage 3 activation record

Independent Stage 3 is technically `COMPLETE` in
`DCP_WBC_INTEGRATION_TWIN_STAGE3_TERMINAL_EVIDENCE.md`. When that exact
reviewed/green evidence is present on dev-control-plane `main`, the Stage 4
managed-source implementation boundary in sections 5-7 is `ACTIVE`. No other
stage or adapter authority is activated.
