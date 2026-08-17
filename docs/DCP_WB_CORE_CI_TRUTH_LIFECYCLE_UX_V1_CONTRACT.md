# DCP `wb-core` CI truth and lifecycle UX v1 contract

contract_status: installed correction proven; canary blocked on fresh readmission

date: 2026-08-17

scope: one exact required-check correction, one shared lifecycle projection,
one notification boundary and one model-free continuation of the existing
`wbc-canary-v1` identity

## 1. Purpose and authority

This contract corrects two facts exposed by the first authorized `wb-core`
canary without changing its product intent or identity:

1. DCP must decide CI eligibility from the configured required check on the
   exact pull-request head, not from unrelated conditional jobs belonging to
   the repository's current Release Train implementation; and
2. DCP must visibly distinguish an open autonomous workflow from a model
   process that is actually consuming one of the three model-action slots.

The governing predecessor is the
[`wb-core` Release Train handoff v1 contract](DCP_WB_CORE_RELEASE_TRAIN_HANDOFF_V1_CONTRACT.md).
It remains authoritative for target/profile/repository identity, labels,
provider gates, FIFO admission, direct-merge ineligibility, `release:ready`,
`release:done`, exact completion proof and WBC Release Train ownership. This
contract narrows no fail-closed gate and grants no new release actor.

Codex execution remains jointly governed by the
[permission-routing](DCP_CODEX_EXECUTOR_PERMISSION_ROUTING_CONTRACT.md) and
[direct-executor routing](DCP_CODEX_DIRECT_EXECUTOR_ROUTING_CONTRACT.md)
contracts. Technical completion is not owner acceptance.

## 2. Exact incident and immutable continuity

The correction is bound to these read-only-proven facts:

| Fact | Exact value |
| --- | --- |
| policy task | `wbc-canary-v1` |
| native card / session | `1` / `wb-core-1` |
| repository / pull request | `orenvlad-ai/wb-core` / `987` |
| source branch | `ao/wb-core-1/root` |
| current pull-request head | `e8cca45f3995b8181fe81ead154f7a933dbacbe8` |
| required check / run | `baseline` / `32048996893` |
| required-check result | exact-head terminal `success` |
| model-action history | one succeeded `initial_worker`, sequence `71` |
| current continuation state | `incident` / `ci_identity_failed` |
| review / admission / merge counts | `0` / `0` / `0` |

The exact-head provider snapshot is OPEN, non-draft, same-repository,
MERGEABLE/CLEAN, with exactly `task:standard` and `scope:repo-only`. Additional
Release Train check rows on that head are `skipped`. The installed policy loop
incorrectly treated any non-passed row as terminal before selecting the
configured `RequiredCheck`, so it persisted `ci_identity_failed` even though
the exact required `baseline` succeeded. Stock notification logic also emitted
`ready_to_merge` before DCP had created a fresh review or FIFO admission.

The incident row/event/packet and stock notification remain immutable audit
evidence. This contract never rewrites them. Any drift in task, card, session,
repository, pull request, branch, head, single-worker count or absence of a
successful exact-head `baseline` makes the recovery ineligible and stops
without adaptation.

## 3. Release-Train-independent CI seam

For a policy target, the trusted CI decision is the target specification's
`RequiredCheck`. For `wb-core` v1 its exact value is `baseline`.

The CI gate MUST:

1. select rows only for the exact current pull-request head;
2. select the exact configured required-check name;
3. require exactly one provider-backed identity for that name and head;
4. require a terminal successful conclusion and a valid provider URL/id;
5. keep missing or pending required CI as a passive model-free wait; and
6. fail closed on a duplicate, malformed, wrong-head-only, cancelled, skipped,
   neutral, timed-out or failed required check.

Additional non-required checks are observational. Their skipped, neutral,
successful or pending conclusions cannot make the named required-check gate
fail merely because they exist. This is not a general permission to ignore
provider policy: a separately typed provider-required blocking failure,
branch-protection conflict, head/base drift, mergeability failure, label drift
or compatibility-marker failure remains independently ineligible.

The implementation MUST NOT name or count the WBC Release Train's workflows,
jobs, matrices or conditional branches. These two model-free fixtures are
therefore behaviorally identical:

- current complex train: one successful exact-head `baseline` plus unrelated
  skipped Release Train jobs; and
- future simplified train: one successful exact-head `baseline` and no other
  check rows.

Removing, renaming or restructuring non-required WBC jobs requires no DCP
source or configuration change. Changing the configured required-check name is
a separate reviewed target-authority change.

## 4. Independent release and provider gates

Passing the required check means only that fresh DCP review may become
eligible. It does not mean ready to merge, admission, release or completion.
The existing gates remain ordered and independent:

```text
exact provider/task/profile/labels/head/base/marker
  -> exact configured required check
  -> fresh context-free DCP review of that exact head
  -> optional one findings repair and fresh review
  -> FIFO admission
  -> exact-head release:ready
  -> WBC Release Train merge + release:done + exact completion proof
```

DCP `MergePullRequest` and every direct provider merge remain statically
ineligible for `wb-core`. `release:ready` remains exact-head guarded and
idempotent. Head drift invalidates review/admission and follows the repository
marker's fresh-readmission rule. DCP completion still requires the exact merge
SHA, `release:done` and the exact WBC completion proof.

## 5. Typed lifecycle activity

The renderer/session read model MUST expose two independent typed facts (these
names are normative concepts; implementation names may differ):

- `modelActive`: a durable DCP model action is actually `claimed` or `running`
  for this task and therefore occupies a global model slot; and
- `workflowActive`: the policy lifecycle is autonomous and nonterminal, with
  no Human Gate or actionable terminal technical incident.

`workflowActive` is presentation state only. It creates no action, slot,
process, timer, poller, watcher, heartbeat, retry or token use. The global
three-active-model-action ceiling continues to use only durable action state.

One shared typed projection drives board card, sidebar dot, details/header and
accessibility text:

| Durable phase | workflowActive | modelActive | Truthful primary substatus |
| --- | --- | --- | --- |
| worker/repair queued | true | false | `Worker queued` / `Repair queued` |
| worker/repair running | true | true | `Worker running` / `Repair running` |
| CI/provider refresh wait | true | false | `Waiting for CI/GitHub update` |
| reviewer queued | true | false | `Reviewer queued` |
| reviewer running | true | true | `Review running` |
| automatic arbiter queued | true | false | `Arbiter queued` |
| automatic arbiter running | true | true | `Arbiter running` |
| FIFO admission wait | true | false | `Waiting for admission` |
| `wb-core` release wait/run | true | false | `Waiting for Release Train` / `Release Train running` |
| deploy wait/run where a target defines deploy | true | false | `Waiting for deploy` / `Deploy running` |
| exact Human Gate | false | false | `Needs your decision` |
| actionable technical incident/failure | false | false | `Needs attention` / exact error |
| merged/released/deployed terminal | false | false | exact terminal label |

The gentle activity indicator represents `workflowActive`; any distinct model
indicator represents `modelActive`. Copy and accessibility text must never say
that a passive wait consumes a model slot. Exact Human Gate and technical
failure are steady and non-animated. Terminal success is steady green. A
repo-only target invents no deploy state. `prefers-reduced-motion` disables
motion without removing phase, color, substatus or accessible activity text.

This section supersedes only the presentation rule in
`DCP_LAB_PHASE_UI_ARBITER_V1_CONTRACT.md` that motion occurs exclusively while
a model process is running. It does not change that contract's durable phases,
board zones, one-card identity, model accounting or action authority.

## 6. Notification truth

Generic stock `ready_to_merge` notification creation MUST be suppressed for a
DCP policy session until the policy has completed a fresh exact-head review and
FIFO admission. A passing SCM aggregate alone is never sufficient.

After admission, notification text is target-policy truth:

- `wb-core`: `Ready for Release Train` or `Waiting for Release Train`; never a
  claim that DCP will merge;
- a target whose DCP policy owns direct terminal merge: the existing truthful
  ready-to-merge wording; and
- terminal release/deploy: only after the target-specific terminal proof.

An older stock SCM summary may not override a newer typed policy phase in the
card, sidebar, details or notification. Notification suppression creates no
second policy store; it consults the same typed projection and durable SQLite
facts.

## 7. Model-free regressions

Source acceptance requires tests that first reproduce this incident and then
prove the correction:

- exact successful `baseline` plus unrelated skipped jobs becomes review-
  eligible;
- exact successful `baseline` as the only check is identically eligible;
- missing, pending, duplicate, malformed, wrong-head, skipped, cancelled or
  failed required `baseline` cannot pass;
- a separately provider-required blocking failure is not bypassed;
- `wb-core` never calls `MergePullRequest`;
- `release:ready` remains idempotent and exact-head guarded;
- restart cannot duplicate worker, reviewer, admission or release handoff;
- the full forward UI path covers every active and passive phase;
- `modelActive` and `workflowActive` remain distinct;
- Human Gate/error/terminal/stale-SCM/reduced-motion cases are steady and
  truthful; and
- board, sidebar, details/header and accessibility projections agree exactly.

Notification tests MUST prove suppression before review/admission, truthful
Release Train wording after admission and no false ready notification from
aggregate passing SCM state. All fixtures are model-free and make no WBC
mutation.

Run generated parity, Go test/race/build/vet, renderer/type/package gates and
the installed-artifact suite required by the managed-source repository.

## 8. Exact forward recovery

Only after the reviewed authority, managed-source and immutable pin merges and
deterministic stopped install/preflight may one additive migration authorize a
model-free recovery of this exact incident.

The migration and reconciler MUST:

1. preserve the original `ci_identity_failed` incident/event/evidence;
2. bind every identity and count in section 2 plus current provider facts;
3. re-evaluate only the exact configured successful required check;
4. create no task, card, session, worktree, branch, pull request, initial
   worker, repair, arbiter, admission or release label; and
5. clear only the false current incident state and queue exactly one fresh
   context-free reviewer for head `e8cca45f3995b8181fe81ead154f7a933dbacbe8`.

The ordinary installed policy then owns all further progress. Findings may use
only the already-authorized one bounded repair and a fresh review. Empty
findings proceed through FIFO admission, exact `release:ready`, WBC Release
Train merge/`release:done` and DCP terminal observation. A new uncontracted
drift fails closed. No second initial worker, manual review, manual label,
manual merge, branch synchronization or replacement identity is authorized.

## 9. Sequential delivery and terminal meaning

Delivery is strictly sequential:

1. ordinary reviewed dev-control-plane authority PR with green `baseline`;
2. ordinary reviewed managed-source PR with exact-head semantic/security
   review and full source/package gates;
3. separate reviewed dev-control-plane immutable pin/install-guard PR;
4. governed zero-active-action stop, deterministic prepare/build/install/
   preflight with backup and receipt, controlled start and exact recovery;
5. ordinary reviewed terminal-evidence/current-authority PR.

A documentation merge is not source or runtime authority. Managed source is
not installed authority before the separate pin and deterministic install.
The existing app/daemon and SQLite remain untouched until step 4. WBC files,
workflows, branches, pull requests and labels are changed only by the already
authorized worker/daemon/Release Train path; no manual WBC mutation is allowed.

`COMPLETE` requires the same canary to reach exact terminal WBC Release Train
proof, installed UI/notification proof, SQLite integrity, zero active actions,
one initial worker, no duplicate identity/action/review/admission/release and a
clean final-main readback. Any new uncontracted blocker ends `BLOCKED` at a
safe boundary. Neither result is owner acceptance.

Managed-source PR #63 exact head
`b11657b24712bbf04b12cbde4f41b1c9d5530280` passed exact-head
semantic/security review `PRR_kwDOTydt6M8AAAABJ0AXKw` and source/package
workflow `32055555244`, then merged normally at exact source
`93246658c34a7d5cdeb7bb42a7f3496308923608`, tree
`828c3c6b1b5a5700bde8495a435d40ee3609ec9d`. It remained build/install input
only until the separate immutable pin merged and the governed deterministic
install fence proved the artifact, migration and preserved live identity.

Pin/install-guard PR #227 exact head
`653e96e3b1d52b1c71d2ef404e5b3adc7a10f5d5` passed review
`PRR_kwDOSUqHmc8AAAABJ0HNTQ` and baseline run `32056895184`, then merged at
`65327c94c48482c7024a6f793012131aea216de3`. Deterministic install proved exact
source `93246658c34a7d5cdeb7bb42a7f3496308923608`, tree
`828c3c6b1b5a5700bde8495a435d40ee3609ec9d` and receipt
`44a6a6906b24d727583f0772ff7f08058791d3b8e83272f827bba76299cbf29d`.
Migration 0079 recovered only the same canary into one fresh approved review
and one FIFO admission. A concurrent WBC main advance then caused Release Train
run `32057937600` to publish its required exact readmission event; installed
DCP stopped as `release_state_drift` because no fresh-readmission continuation
is authorized or implemented. Current terminal status is `BLOCKED`, not a
Human Gate. Exact proof is in
[terminal evidence](DCP_WB_CORE_CI_TRUTH_LIFECYCLE_UX_V1_TERMINAL_EVIDENCE.md).

## 10. Explicit exclusions

This contract adds no WBC Release Train implementation change, workflow/job
name dependency, product task, second canary, direct WBC merge, manual review,
manual label, production/deploy authority, SSH, secret/runtime/business-data
access, second daemon/database/service, watcher/poller/timer, updater,
telemetry, legacy cleanup, model ceiling change or owner-answer synthesis.
