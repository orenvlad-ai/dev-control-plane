# DCP Lab happy-path v1 contract

contract_revision: 2026-08-14.3
status: owner-approved implementation contract; runtime-gated until the
separate managed-source and pin/install sequence completes

## Purpose and precedence

This contract replaces qualification-only card/cohort ceilings with one
policy-driven happy path for future synthetic DCP Lab tasks. It is the current
rule for every new task submitted through the canonical command with exact
target `dcp-review-lab`, profile `synthetic-pr` and a unique task id.

The completed cards 1-12, their sessions, worktrees, branches, pull requests,
review runs, admission rows, incidents, recovery/finalization rows, counters,
token accounting and evidence remain immutable. The cards-11/12 startup
quarantine remains authoritative for those two historical sessions only. It
must not reject, classify, restore or otherwise govern a future session.

Until an exact managed-source commit is reviewed, pinned, deterministically
installed and passes the stopped preflight below, the installed qualification
bundle remains the runtime authority and must fail closed on a future card.

## Exact scope

- The sole PR-capable target is the public synthetic repository
  `orenvlad-ai/dcp-review-lab`, selected only by target `dcp-review-lab` and
  profile `synthetic-pr`. The canonical repository path, common/private Git
  directories, sole `origin` fetch/push URLs, `main`, native worktree and
  `ao/dcp-review-lab-<n>/root` branch must all agree.
- The remote-free target `dcp-lab` remains remote-free and receives no worker
  network, PR, review, admission or merge authority. Every other repository,
  target, profile, path, remote or branch is out of scope.
- The existing DCP daemon and existing `ao.db` are the sole runtime and state
  authority. This change adds no daemon, database, registry, task-card service,
  scheduler, watcher, timer, heartbeat, poll loop, hosted surface or UI column.
- The stock native project, session/card, worktree, review engine, findings
  delivery and board columns remain the presentation and lifecycle surface.
  The synthetic repository has no deploy; its successful terminal state is
  `Merged`.
- No arbiter, HumanGate, manual merge/review bypass, Release Train, production
  repository, `wb-core`, Telegram, Entire/Symphony runtime, secret or new
  external service is activated.

## Durable submission and native identity

The canonical `bin/dcp-ao-submit` is the only normal entry. The submit lock
serializes validation, idempotency resolution and native identity creation.
The daemon persists one additive future-task row in `ao.db` before a model may
start. The row binds at least:

- task id, canonical payload and payload digest;
- exact target/profile/repository and policy version;
- one native session/card number and id, worktree and branch;
- lifecycle state, revision and timestamps.

Task id is unique for the future policy. An equal replay of the same canonical
payload returns the same durable task and native identity without another
card, worktree, branch, event or model action. A replay with any payload,
target, profile or repository difference is rejected before mutation. Crash
recovery may complete only the already reserved identity; it cannot allocate a
replacement. A session with matching display text but no exact policy row, or
a policy row whose session/worktree/branch identity drifts, fails closed.

Historical task ids and cards are evidence, not reusable policy rows. New card
numbers are allocated by the stock native session mechanism and are not
allowlisted or capped by a particular integer.

## Global model-action policy

At most three DCP model actions may be active globally. A model action is a
Codex worker, reviewer or any future role launched by the DCP daemon or its
canonical submit path. The policy uses additive durable action/lease rows in
the existing `ao.db` with these invariants:

- only slots 1, 2 and 3 exist, and each may have at most one active owner;
- one task has at most one active worker action;
- one exact PR head has at most one active reviewer action;
- queued actions own no process, timer, heartbeat, watcher, poller or token;
- an action release or another persisted lifecycle/SCM event causes one
  model-free FIFO drain; startup performs one model-free reconciliation;
- exact live ownership is preserved across restart; stale or ambiguous
  ownership is failed closed and is never silently duplicated.

The ceiling limits simultaneous actions, not the number of durable tasks over
time. Four or more tasks may be accepted and wait durably. CI wait, review
eligibility wait and admission wait never hold a model slot.

## Worker, PR and bounded repair

The initial worker receives only its immutable task and exact synthetic target
policy. It may create one commit lineage on its one native branch, push that
branch and open at most one ready pull request targeting `main`. A second pull
request, foreign branch/head, draft, different author/base/head repository or
missing provider identity fails closed.

Provisioning must persist the exact task creation-base SHA and ref in the same
native session metadata before a worker launch. Terminal admission revalidates
that the reviewed head descends from this durable base and that its commit count
fits the one-initial-plus-one-repair ceiling. Missing creation-base metadata is
never inferred at merge time. A bounded startup correction may fill it only for
the separately recorded exact card-13 live identity and zero active model
actions; every mismatch is an inert no-op.

For each task the automatic model budget is bounded to:

1. one initial worker action;
2. one context-free review for the resulting exact head;
3. only when that review returns structured findings, one repair worker action
   on the same task/session/worktree/branch/PR;
4. one context-free review for the resulting new exact head.

The repair envelope contains the immutable task/scope, exact prior and current
head, review run and bounded structured findings. It creates no replacement
identity. The worker must produce a different exact head on the same PR; an
unchanged, stale, foreign or ambiguous result fails closed. A second
changes-requested verdict is terminal and creates no third worker/reviewer
cycle. Machine failure, budget exhaustion or unknown provider mutation is
terminal and is not automatically retried.

## Exact-head review and CI

Every exact PR head requires its own fresh context-free structured reviewer.
The existing `Review`/`ReviewRun`, stable reviewer terminal and trusted result
supervisor remain authoritative. A durable uniqueness constraint and action
lease make launch single-flight and restart-idempotent. A verdict for another
head, task, session, PR, batch or run is inert. A verdict is never copied to a
new head.

The reviewer remains read-only, network-disabled and credential-free. It
receives no daemon or GitHub authority. The trusted supervisor validates the
exact current open non-draft PR/head before one guarded persistence action.
Approved with empty findings may continue; structured findings return only to
the same task's bounded repair path.

Before admission, fresh provider facts must show exactly one successful named
check `dcp-review-lab` for the current head, OPEN, non-draft, expected
repository/author/base/branch/head, no unresolved review thread and a known
non-blocking provider review decision. Missing, stale, skipped, neutral,
cancelled, duplicate or ambiguous check/provider facts fail closed.

## Durable FIFO admission and terminal merge

The existing `dcp_review_lab_admission` sequence is generalized for all
policy-eligible future tasks without modifying historical rows. Each approved,
empty-findings exact head may enqueue once. One durable global merge lease may
be active; all later rows wait by sequence without a process, timer, heartbeat,
poller or model slot.

Immediately before merge the trusted daemon revalidates the full task/session/
worktree/branch/PR/head identity, current `main`, approved exact-head review,
fresh named check, resolved threads and current MERGEABLE/CLEAN provider facts.
Only the daemon may request the ordinary expected-head squash merge. It stores
the provider merge SHA once and projects the same native card to `Merged`.

When a preceding merge advances `main`, the next persisted waiter is
reconciled model-free. If its exact head remains cleanly mergeable and all
fresh facts pass, it may claim the lease. A conflict, non-fast-forward identity
ambiguity or uncertain provider outcome persists a structured incident and
stops that task fail-closed. It does not launch an arbiter, create a HumanGate,
reuse an old review, rebuild a card or permit manual bypass. A terminal result
or lease release causes one event-driven drain of the next FIFO waiter.

The stock SCM observer is also an eligibility event for an already persisted
waiting admission. When a freshly fetched exact-head snapshot is materially
OPEN, passing, MERGEABLE and CLEAN but its semantic hashes already match the
durable SCM rows, lifecycle must still emit one idempotent model-free terminal-
merge eligibility signal for that exact session. This closes only the ordering
gap in which the provider snapshot was acknowledged before the admission row
existed. Unknown, pending, stale, foreign, conflicting or non-waiting facts
remain passive or fail closed under the existing terminal rules. The signal
does not claim or merge: the existing process mutex and durable SQLite FIFO
lease remain the sole owner, so duplicate/out-of-order snapshots and restart
cannot duplicate a claim or merge.

The inverse ordering gap has the same single-authority rule. If the exact
approved policy admission commits after the last materially clean SCM snapshot,
the newly created durable identity emits one post-commit in-process eligibility
signal to the existing terminal merger. The signal occurs only after the
transaction has returned the exact committed identity, owns no provider/SCM or
merge side effect, and is emitted only for first creation. Existing admission
replay, stale/foreign/ambiguous identity or transaction failure emits no
signal. Concurrent lifecycle, SCM and startup delivery remains harmless
because `terminalMerger.Try`, its process mutex and the SQLite FIFO lease still
own every claim and guarded merge.

## Restart, quarantine and UI truth

Controlled restart preserves task id/payload, native identity, action queue
order, active leases, exact-head review uniqueness, bounded repair count,
admission sequence/lease and terminal merge SHA. Startup reconciliation is
model-free and may only adopt exact live/terminal provider facts or advance a
durable queue after a proven terminal predecessor. It cannot repeat a worker,
reviewer, admission claim or merge.

The historical pre-restoration quarantine and recovery tables remain byte- and
row-immutable. Their startup fence continues to suppress native restoration of
cards 11/12, but future policy cards are classified exclusively by their exact
new task/action rows. Missing or ambiguous classification fails closed; the
historical quarantine is never interpreted as a global future-task ban. The
same exact historical rows may be either pre-terminal `idle/non-terminated` or
stock-terminal `exited/terminated`; mixed/active pairs fail closed and neither
accepted pair restores a historical runtime.

The stock board truthfully projects queued/waiting work, active worker/reviewer,
findings/repair, Ready to Merge, failure/incident and terminal `Merged` through
existing card fields and columns. The central card and left sidebar consume one
shared visual-status projection from the same native session read model. The
2026-08-15 staged
[phase UI contract](DCP_LAB_PHASE_UI_ARBITER_V1_CONTRACT.md#phase-1-one-typed-forward-only-ui-projection)
supersedes only the earlier visual mapping after its separately reviewed source
and install gates: policy PR/CI preparation remains blue Working, only review
queue/run is yellow In Review, admission wait is steady green Ready to Merge,
merged is steady green, and typed incident/failure remains steady Needs You
with red failure/incident emphasis. An exact `incident` whose latest durable
arbiter status/verdict is `human_gate` is the typed exception: it remains in
Needs You with the primary label `Needs your decision` and a steady orange dot,
and exposes its exact incident kind, generation, cohort and owner question.
An older failed action or stock `review_failed` summary cannot override it;
real failures without that exact Human Gate remain red. Pulse represents only
a durably active worker/repair or reviewer, causes no layout shift and is disabled by
`prefers-reduced-motion` without removing steady color or accessible text. No
parallel card state or independent sidebar mapping is introduced.

## Required implementation and proof sequence

1. Merge this reviewed contract in `dev-control-plane` with green `baseline`.
2. From current managed `origin/main`, implement the bounded policy in one or
   more reviewed ready PRs in `orenvlad-ai/dcp-orchestrator`. Require exact-head
   semantic/security self-review plus green `source` and `package`, then merge
   normally.
3. Merge a separate `dev-control-plane` pin/install-guard PR with the exact
   source commit/tree and green `baseline`.
4. With the installed bundle stopped and no active model action, run the
   deterministic prepare/build/install/preflight sequence. Preserve the
   verified prior bundle and state/data backup and bind the new exact receipt.
5. Run model-free fixtures covering at least four future tasks, the three-slot
   cap and passive fourth waiter, one review per exact head, bounded findings
   repair plus head change, duplicate equal/conflicting submit, duplicate SCM
   event, FIFO admission, main advancement, restart recovery and terminal
   dedupe. Include fail-closed foreign repository/profile/head/revision cases.
6. Preserve existing `chat-probe-b`/card-13/PR-10/head/review/admission
   identities and do not submit another task or launch a worker/reviewer. After
   the reviewed repair pin and deterministic stopped install, one controlled
   start may finish only that durable waiting admission model-free. Prove one
   merge, terminal persistence and restart dedupe, then leave the application
   stopped with zero new model calls and zero new model tokens.

Technical completion is not owner acceptance. Only the owner may write
`Задача принята`.
