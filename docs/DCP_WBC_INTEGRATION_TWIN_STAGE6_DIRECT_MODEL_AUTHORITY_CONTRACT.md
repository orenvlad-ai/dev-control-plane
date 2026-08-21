# Stage 6 direct DCP-v2 model authority contract

contract_revision: 2026-08-21.1

technical_status: owner-approved architecture and managed-source authority; not install, migration, runtime or provider authority

owner_acceptance: not requested or synthesized

This contract records the owner's decision to remove the DCP-v2 dependency on
the legacy native lifecycle. It authorizes one reviewed architecture package
and, only after that package merges, one reviewed managed-source package. It
does not authorize installation, migration of the installed database, app or
daemon control, runtime continuation, provider publication, Stage 7, WBC,
production or cutover.

The active entry remains the
[current program manifest](DCP_WBC_INTEGRATION_TWIN_CURRENT_PROGRAM_MANIFEST.md).
The prior aggregate install/start authority is spent, and the
[blocked evidence](DCP_WBC_INTEGRATION_TWIN_STAGE6_AGGREGATE_CONTINUATION_BLOCKED_EVIDENCE.md)
remains immutable.

## 1. Frozen checkpoint

Source work must preserve the installed schema-85 contour without mutation:

| Fact | Frozen identity |
| --- | --- |
| Task | `dcp-v2-twin-canary-v1`, stale `worker_queued`, revision `1` |
| Revision | `v2-13f81f321f99d1117dc931419e0bea3945ee35a5` |
| Command | `v2-e028f779a18417e990911057f7db7c666f7487ca`, `worker.execute/v1`, `leased` |
| DCP-v2 Action | `v2-40f87d048813533daa1108b4316c09139acf0a8f`, falsely `running`, slot `1` |
| Runtime/launch | `78535564-a2bc-478c-80b0-207753f2152c` |
| Native terminal evidence | Action sequence `74` succeeded; session idle; zero active native model Actions |
| Existing Worker output | local commit `bebbf8f617f1a6fa0b9e91698fe710fe0a2bad2c`, tree `2fda4cae71976fd701bf3a9ccca4031f7afb630d` |
| Installed source/tree | `d084ae3cf0cb3e5e32ebefa197031c24a2b6392d` / `a6e3c3347bbbddd256e9edbfc541f115813249d2` |
| Install receipt | SHA-256 `19550a9f02b14f13be8a80214529025fd6d4fe7dc8e5bd12c5eaa1a47dd54b0c` |
| Counts | v2 Task/Revision/Command/Action `1/1/1/1`; downstream `0/0/0/0` |

The local Worker commit has no remote branch, PR, CI, review, Admission,
Release Train, merge, artifact, deployment or Result effect. It must not be
pushed or regenerated in this phase. WBC PR #987, production and the protected
Selectel/Luchiki contour remain frozen.

## 2. Sole-authority decision

For every DCP-v2 Task, including Worker, Reviewer, findings-repair and Arbiter:

1. DCP SQLite is the only durable authority for Task, immutable Revision,
   Command, Action, runtime identity, slot, launch/effect fence, terminal model
   receipt and the next Command.
2. The DCP daemon owns all lifecycle decisions and every atomic transition.
3. A typed provider-neutral runner is stateless transport. It may prepare an
   isolated worktree, launch one bounded model process, report exact liveness
   and return one typed terminal receipt. It owns no Task, Action, queue,
   retry, session, card or policy state.
4. DCP-v2 must not create, update or consult
   `dcp_review_lab_policy_task`, `sessions` or `dcp_model_action` for current
   lifecycle authority. Historical rows remain readable only by the explicit
   one-time adoption validator described below.
5. Ordinary non-DCP and legacy workflows remain supported and retain their
   existing tables and behavior. No historical row is deleted or rewritten.
6. The bridge is removed, not replaced by dual-write, synchronization,
   shadow-state, heartbeat, poller or retry logic.

GitHub and deployment authorities remain unchanged: GitHub owns repository
facts, and the repository-owned Release Train alone merges and deploys an
exact admitted head.

## 3. Direct typed runner boundary

The managed source must expose one provider-neutral runner interface whose
typed inputs bind at least:

- Task, Revision, Command and Action ids;
- role (`worker`, `reviewer`, `repair` or `arbiter`), attempt `1`, model,
  reasoning and hard budget;
- immutable input and prompt digests, repository identity, exact base/head,
  branch, worktree and allowed paths;
- launch fence, effect fence and expected-old-head; and
- a runtime id allocated and durably reserved by DCP before launch.

The runner returns only typed receipts:

- launch receipt: exact Action, launch fence, runtime id and provider request
  identity/digest;
- liveness observation: exact runtime id and process state, without durable
  policy meaning; and
- terminal receipt: exact Action/runtime/fence, terminal status, output/result
  digest and role-specific repository facts such as commit, tree, branch and
  worktree identity.

The runner receives no SQLite handle and cannot enqueue work, reserve a slot,
advance a Task, create a provider effect or decide whether a result is trusted.
An equal receipt is inert. Crossed identity, mismatched digest or more than one
runtime for an Action is a technical incident with no new effect.

## 4. Atomic direct lifecycle

One SQLite transaction claims an eligible model Command, allocates one of the
three global slots, creates its Action when needed, and persists the launch
and effect fences plus DCP-owned runtime identity before transport launch. A
crash before the fence permits no provider call. A crash after the fence may
only adopt the exact matching live runtime or terminal receipt; it never
launches another call.

Trusted terminal ingestion uses one transaction to:

1. compare Task state revision, current Revision, Command lease, Action,
   runtime and fence;
2. persist the immutable terminal receipt/result;
3. finish the Action and Command and release the exact slot;
4. create an immutable successor Revision when repository output changed;
5. move the same Task pointer/state; and
6. enqueue exactly one deterministic next Command, or terminalize/passivate.

No intermediate committed state may contain a terminal Action with a leased
Command, an occupied terminal slot, a changed head without its successor
Revision, or a Task transition without its required next Command.

Repository publication is separated from model execution. A model-free
`publication.execute/v1` Command may publish an already-produced exact commit
only with an effect fence, expected-old-head, exact repository/branch/commit/
tree and idempotent remote reconciliation. It cannot invoke a model. This
phase defines and tests that command but does not execute it against GitHub.

Reviewer, repair and Arbiter Actions use the same runner and terminal law.
The one task-level repair ceiling is shared by review findings and
arbiter-authorized repair. No automatic second call exists.

## 5. Exact one-time current-Worker adoption

The source package must implement one explicit, idempotent adoption input for
the frozen Worker. It is not a submit, launch, provider event or general
legacy reconciliation path.

The validator accepts only the complete conjunction in section 1 plus:

- exact native Action id/kind/sequence/status/launch id and terminal time;
- exact native session/card/policy identity in its historical terminal state;
- exact local repository, worktree, branch, base ancestry, clean status,
  commit, tree and bounded output bytes;
- absence of the remote branch, PR and downstream/provider effects; and
- an immutable digest covering all accepted legacy evidence.

On a disposable migrated snapshot, one transaction consumes that receipt,
finishes the existing DCP Action and Command, releases slot `1`, creates the
successor Worker-output Revision and enqueues the deterministic model-free
`publication.execute/v1` Command for the same local commit. It creates no Task,
initial Worker, native card/session/model Action, model call, push or PR.

Equal replay returns the same adopted result. Missing, crossed, stale or
contradictory identity fails without mutation. After consumption, later
changes to legacy tables cannot affect DCP-v2 state. The immutable adoption
receipt remains evidence only.

## 6. Additive schema and source boundary

The managed package may add one forward-only migration after schema 85. It may
add DCP-owned runtime/terminal-receipt and exact Stage 6 adoption records,
constraints and indexes. It must not alter or delete legacy tables or rewrite
the frozen rows. Migration tests run only against synthetic fixtures and an
exact disposable read-only-derived schema-85 snapshot.

Merging source does not migrate the installed database. No install, live
migration, stop, start or preflight authority exists here. A later owner task
must pin the merged source and define exact backup, migration, stopped
preflight, adoption-input construction and rollback gates.

## 7. Legacy-dependency removal gates

Managed-source completion requires all of the following:

- DCP-v2 construction no longer requires the legacy policy provisioner;
- DCP-v2 startup has no native-shell recovery or reconciliation branch;
- DCP-v2 service and projection perform zero ongoing reads/writes of legacy
  policy-task/session/model-action lifecycle rows;
- DCP-v2 Worker, Reviewer, repair and Arbiter all use the direct runner;
- future direct tasks create zero legacy DCP policy/session/model-action rows;
- the exact adoption path is the sole code path allowed to read the frozen
  legacy evidence, and it becomes inert after consumption; and
- legacy/non-DCP tests prove their ordinary workflows remain intact.

Compatibility adapters that still call `PrepareLegacyReview`,
`StartLegacyAction`, `CompleteLegacyWorker`, `CompleteLegacyReview` or an
equivalent DCP-v2/native lifecycle callback fail this gate.

## 8. Projection truth

UI/API fields derive from the DCP-v2 Task/Command/Action/runtime/result
projection. `modelActive=true` requires both an exact DCP Action in
`launching` or `running` and one matching live runner runtime. An active Action
without its runtime, or a live runtime for an inactive Action, fails closed
and never displays a healthy active model.

`workflowActive=true` may represent queued model work, CI, publication,
review, Admission, Release Train or deployment observation with no model slot.
Queued, launching, running, terminal and CI-wait projections must be tested
from the same durable source used by board, sidebar and task detail.

## 9. Model-free and negative acceptance matrix

The source package must prove with synthetic data and the disposable snapshot:

- the frozen native success reproduces the old stale Action/Command/Task and
  the direct adoption fixes it atomically without a second model call;
- restart before/after claim, launch fence, runtime receipt and terminal
  receipt produces no duplicate effect;
- equal terminal/adoption replay is inert; contradictory runtime/result/
  commit/tree facts fail without effect;
- missing runtime for an active Action and a runtime for an inactive Action
  fail closed;
- exactly three active Actions hold slots and a fourth waits durably;
- terminal success releases the slot and advances the same Task atomically;
- Worker, Reviewer, repair and Arbiter share the direct boundary and enforce
  the single repair allowance;
- legacy-row mutation after adoption cannot alter DCP-v2 state;
- new direct tasks create no legacy lifecycle-authority rows;
- queued/launching/running/terminal/CI-wait UI projections are truthful; and
- store, restart, dedupe, race, source, package and generator suites pass with
  a clean tracked tree.

## 10. Phase acceptance and next gate

Architecture acceptance requires one ready `dev-control-plane` PR with green
exact-head `baseline`, one fresh context-free semantic/security review, zero
threads and normal merge. Only then may the one managed-source package begin
from fresh `dcp-orchestrator` main.

Source acceptance requires one ready managed-source PR, full exact-head source
and package checks, one fresh context-free semantic/security review, zero
threads and normal merge. A terminal evidence-only DCP PR may then record the
exact source result and snapshot digest.

Completion of these source phases leaves Stage 6 blocked and the installed
contour unchanged. The next separate boundary is exact source pin, one
governed install/migration and stopped preflight for the same frozen identity.
It does not imply live continuation, Stage 7, WBC shadow, production or owner
acceptance.
