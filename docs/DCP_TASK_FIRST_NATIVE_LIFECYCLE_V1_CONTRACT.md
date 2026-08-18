# DCP task-first native lifecycle v1 contract

contract_status: source complete; Pass 2 pin selected, not installed

date: 2026-08-18

scope: one provider-neutral native lifecycle policy for durable DCP policy tasks

## 1. Purpose and predecessor

This contract replaces duplicated native-shell liveness predicates with one
typed task-first lifecycle policy shared by policy startup reconciliation,
review and recovery eligibility, admission, and terminal release observation.
It is the bounded follow-on authorized by the exact technical blocker in
[`DCP_WB_CORE_REPO_ONLY_READMISSION_NATIVE_LIFECYCLE_BLOCKED_EVIDENCE.md`](DCP_WB_CORE_REPO_ONLY_READMISSION_NATIVE_LIFECYCLE_BLOCKED_EVIDENCE.md).

The durable DCP task/card is authoritative until its target profile's exact
terminal proof. A native shell becoming archived, exited, or terminated is not
itself task completion. A worker, reviewer, repair, or arbiter runtime is
required only while the exact registered model action is launching or running.
CI, provider refresh, review queueing, readmission, FIFO admission, Release
Train wait, Human Gate, incident, and terminal observation are durable
model-free phases and may preserve an exact archived shell.

This contract preserves the exact predecessor identity and every historical
fact:

| Fact | Exact value |
| --- | --- |
| policy task / native card / session | `wbc-canary-v1` / `1` / `wb-core-1` |
| repository / pull request | `orenvlad-ai/wb-core` / `987` |
| branch / current head | `ao/wb-core-1/root` / `26044c696651ce5873748ec3f920d40e77c5686c` |
| task state | revision `22`, `admission_waiting` |
| approved review | `18c54338-df31-4471-a344-4db6648ff4e3` |
| admission / readmission | admission `32` waiting; generation `1` admitted |
| model actions | `73` total, zero active; initial worker sequence `71` once |
| installed database | schema `82`, SHA-256 `9cc8d8805fe61a0b72406fd428640b191516084bfd0910f1165fb897afc7ab31` |

The prior `waiting_identity_drift`, `admission_identity_drift`,
`release_state_drift`, review runs, migrations, incidents, admissions, and
generation history remain immutable evidence. There is no resubmit,
replacement card/session/branch/PR, second initial worker, manual review,
manual label, or direct merge recovery.

## 2. One typed lifecycle authority

Managed source MUST expose one central evaluator and one result value used by
every relevant caller. Names may follow repository conventions, but the value
has these typed inputs:

- durable policy task phase and target profile terminal semantics;
- exact native project/card/session/branch/worktree/display/prompt identity;
- native shell state: `live`, exact `archived_exited_terminated`, or invalid;
- durable registered model-action state: none, queued, launching, running, or
  terminal, including exact role/action/task/session identity; and
- observed runtime process state and exact process/action ownership.

The result provides at least:

- `eligible` plus one stable typed denial reason;
- `runtimeRequirement`: `none` or `exactModelRuntime`;
- whether an exact archived shell is preservable;
- `modelActive`, derived only from a launching/running registered model action;
  and
- `workflowActive`, derived from a nonterminal autonomous task phase and never
  used for global model-slot accounting.

The evaluator is provider-neutral. It contains no `wb-core`, repository ID,
PR number, marker-version, label, Release Train, or profile-specific exception.
Provider adapters continue to establish exact identity and target terminal
proof before constructing the evaluator input. A target-specific terminal
proof never weakens native identity or model/runtime symmetry.

Policy startup, SCM/check observation, review queue/recovery, findings repair,
arbiter recovery, FIFO admission, readmission, Release Train observation, and
terminal release observation MUST consume this same value. A caller may add a
narrower domain gate after it, but may not restate shell liveness or broaden a
denial. Existing caller-specific WBC archived-shell exceptions are deleted
where this shared policy supersedes them.

## 3. Lifecycle state table

`Archived exact` below means one retained native record with every identity
field exact, `is_terminated=1`, `activity_state=exited`, and no live process.
`Exact runtime` means one live exact native shell/process paired one-to-one
with the exact registered launching/running model action.

| Durable task phase | Required action fact | Runtime | Archived exact shell | Result |
| --- | --- | --- | --- | --- |
| worker/repair queued | exact matching queued action | none | allowed | eligible, workflow active, model inactive |
| worker/repair launching or running | exact matching launching/running action | exact runtime required | forbidden | eligible only with exact process/action symmetry |
| CI/provider/check wait | no launching/running action | none | allowed | eligible passive continuation |
| reviewer/arbiter queued | exact matching queued action | none | allowed | eligible, workflow active, model inactive |
| reviewer/arbiter launching or running | exact matching launching/running action | exact runtime required | forbidden | eligible only with exact process/action symmetry |
| review/repair decision completed | no launching/running action | none | allowed | eligible model-free transition |
| readmission evidence/lease/head/check wait | no launching/running action | none | allowed | eligible model-free generation continuation |
| admission waiting/claimed/admitted | no launching/running action | none | allowed | eligible only with exact review/generation/admission bindings |
| release handoff/wait/terminal observation | no launching/running action | none | allowed | eligible until exact profile terminal proof |
| Human Gate | no launching/running action | none | allowed | stable non-automatic task, not terminal |
| actionable incident | no launching/running action | none | allowed | stable fail-closed task, not terminal |
| exact profile terminal proof | no launching/running action | none | allowed | terminal task; no further automatic actor |

Queued and terminal historical actions own no process and no global active
slot. Durable action states equivalent to claimed/launching/running own one
slot and require exact runtime symmetry. Multiple readmission generations do
not alter these rules: only the exact currently bound review/action/admission
facts may advance the durable task.

## 4. Fail-closed identity and security invariants

Before any eligibility result, the caller and central evaluator together MUST
prove exact project, repository ID/full name/owner/provider, policy task, card,
session, branch, worktree, prompt, display name, target profile, PR, current
head, review, generation, admission, and applicable terminal-proof identity.
Missing, empty, duplicate, crossed, stale, foreign, or conflicting identity is
ineligible.

The following are always fail-closed:

1. any live native/model process without one matching registered
   launching/running model action;
2. any launching/running action without exactly one matching process;
3. a process paired to another task/session/role/action, more than one process,
   or a queued/terminal action with a live process;
4. an archived shell during a phase whose action is launching/running;
5. a nonterminal task without its exact durable native identity record;
6. a role/phase mismatch, including a reviewer process in a worker phase;
7. more than three globally active launching/running DCP model actions; or
8. any attempt to infer task terminality from shell exit/termination instead
   of the exact target-profile proof.

The global three-slot selector continues to count durable active model actions,
not `workflowActive`, queued work, provider waits, or archived shells. Startup
and restart re-evaluate the same facts idempotently and may neither synthesize
an action/process nor reuse an action registered to another exact head.

Direct and lab flows remain fail-closed or behaviorally unchanged as
applicable. DCP `MergePullRequest`, deploy, SSH, production credentials, and
business-data authority remain statically ineligible for `wb-core`. WBC GitHub
Actions remains the sole physical merge/release actor; DCP may only perform
the already-authorized exact-head `release:ready` handoff after review and
FIFO admission.

## 5. Restart and model-free acceptance matrix

Source acceptance requires an exhaustive table-driven matrix for task phase ×
native shell state × model-action state × process state. It MUST include no
action, queued, launching, running, succeeded, failed, and crossed-role action
facts against live, exact archived, absent, duplicate, and foreign native
states. Every denial has a stable typed reason.

Restart fixtures cover at least:

- worker completion and CI/provider wait;
- review queued, launching/running, approved, findings, and repaired review;
- one and multiple readmission generations at evidence, lease, head push,
  check, review, and generation-binding fences;
- admission waiting, claimed, enqueue transition, admitted, release handoff,
  Release Train wait, and profile terminal proof;
- Human Gate and actionable incident;
- exact review/admission/head bindings and crossed/stale variants;
- global three-slot accounting with queued versus launching/running actions;
- idempotent repeated startup/restart and concurrent selector attempts; and
- zero duplicate task, card, session, branch, PR, worker, reviewer, repair,
  arbiter, ReviewRun, admission, generation, release, or terminal observation.

Tests MUST prove provider neutrality with at least the existing synthetic,
browser-extension, and WBC policy families. They also prove that direct/lab
paths are unchanged unless they previously depended on a duplicated predicate
now exactly represented by the common value.

## 6. Exact schema-82 regression and future migration

Before source merge, a disposable read-only snapshot of the stopped canonical
schema-82 database MUST reproduce the current contradiction: startup rejects
`wbc-canary-v1` because `wb-core-1` is exact archived/exited/terminated while
the same exact task/review/generation/admission is eligible for model-free
admission continuation. The live database is never opened writable, migrated,
or replaced in this pass.

The corrected common evaluator MUST accept only that snapshot's exact
non-model continuation and MUST continue to reject identity drift, active
action/process asymmetry, foreign profiles, crossed reviews/admissions, and
later-generation mismatches.

Managed source prepares one additive immutable future migration after `0082`.
It is idempotent and exact-preconditioned on the preserved task/card/session/
PR/head/review/generation/admission identities above. It preserves every
incident and history row, creates no new task/session/action/ReviewRun/
admission/generation/release/provider fact, and only re-arms the already bound
admission continuation required after the shared evaluator is installed. Zero
or multiple matching rows, any changed count/value, or any pre-existing
conflicting migration fact aborts transactionally. Tests apply it only to
disposable schema-82 copies, twice, and prove the second application is a
no-op with byte-equivalent logical state.

## 7. Source gates and review

Implementation begins only after this authority merges. It uses one separate
managed-source worktree/branch and one ordinary non-draft pull request. A
model-free regression fails before the correction. The exact source head then
requires semantic/security review, zero unresolved findings, source/package
CI, generated SQL/API/OpenAPI/TypeScript parity, full relevant serial Go tests,
race, vet, build, renderer/type/UI lifecycle tests, repository audits,
provenance and forbidden-surface absence checks required by managed-source
`AGENTS.md`.

Semantic review MUST verify that there is one evaluator/value type, every
relevant caller consumes it, superseded target-specific archived-shell helpers
are gone, target identity stays strict, no model ceiling changes, WBC direct
merge/deploy remains impossible, and migration/restart tests prove dedupe.

## 8. Sequential delivery and no-install boundary

This owner-authorized pass is strictly:

1. merge this ordinary reviewed authority PR after exact-head review and green
   dev-control-plane `baseline`;
2. merge one ordinary reviewed managed-source implementation PR after all
   source gates; and
3. if needed, merge one narrow source-complete dev-control-plane evidence/
   authority update recording exact source head/tree/review/workflow truth.

This pass MUST NOT change `upstream/dcp-orchestrator.lock` or any installed pin,
build an installation artifact, install/package/replace the app, start or stop
the app/daemon, touch port/run-file state, write or migrate live SQLite, submit
a DCP task/model action, mutate PR #987/WBC branch/labels/files, hand off to
Release Train, perform live-runtime/production/SSH/secret/business-data work,
or edit curator bootstrap. Installed DCP remains stopped and its database is
byte-preserved. WBC is read-only evidence only.

Source merge is build input for a separately owner-authorized pin/install
Pass 2; it is not installed/runtime authority. Technical completion of this
pass is not owner acceptance.

## 9. Source-complete record

Authority PR #239 merged first at
`5075235780b9c38d95faa9657a70265069d3a5c5`. Managed-source PR #71 exact head
`9055dd67f9e9e421e5ddaa6d0beca144a07abf0f` then passed exact-head review,
source/package workflow `32171208324`, and zero review threads before ordinary
merge at source `84dbee2a701186628c1ad92950aa14639000fc0b`, tree
`9374ece6efccf87dcb8a7627c97722a16d063b77`.

The complete model-free source, disposable schema-82 recovery proof, live
database preservation, and no-install boundary are recorded in
[`DCP_TASK_FIRST_NATIVE_LIFECYCLE_V1_SOURCE_COMPLETE_EVIDENCE.md`](DCP_TASK_FIRST_NATIVE_LIFECYCLE_V1_SOURCE_COMPLETE_EVIDENCE.md).
Migration 0083 remains inactive. The source merge is ready only for a
separately owner-authorized reviewed pin/install Pass 2.

## 10. Pass 2 pin selection

The owner authorized the bounded activation pass. The immutable lock selects
only managed-source PR #71 merge
`84dbee2a701186628c1ad92950aa14639000fc0b`, tree
`9374ece6efccf87dcb8a7627c97722a16d063b77`, with predecessor source
`3fdc3976edc6bad591bca4cf4e254b479a905fb3`, tree
`5c945ae8c4ce0101463d1ddbdff54bd75d619de0`. Installation remains prohibited
until this exact pin/install guard passes exact-head semantic/security review,
green baseline, zero unresolved threads and ordinary merge. This selection
adds no managed-source implementation or repair authority.
