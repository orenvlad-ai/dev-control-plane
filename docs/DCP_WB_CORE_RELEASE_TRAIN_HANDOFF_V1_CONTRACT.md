# DCP `wb-core` Release Train handoff v1 contract

contract_status: terminal-complete

current_readiness_status: blocked-native-normalization-guard-merge

date: 2026-08-17

scope: one exact repo-only DCP target and one fail-closed GitHub Release Train handoff

## 1. Purpose and predecessor

This contract authorizes preparation of the local DCP control plane for the
exact public repository `orenvlad-ai/wb-core`, target `wb-core`, initial profile
`repo-only`. It does not authorize a WBC product task, native card, model call,
product branch, pull request, merge or release.

The installed predecessor is exact managed source
`d152afae2bcbcc3d2b1874adf2e6855bebcf00fb`, tree
`aa7a6f486cf89ec299763ebcde7a5fc35a59214f`, receipt SHA-256
`bc49040398a05c6127b140cd10f3828db178bc410f1b722f887ae7d63b79438b`
and SQLite schema 77. It is stopped and preflight-ready with 23 policy tasks,
60 terminal model actions, 39 ReviewRuns, 27 admissions and zero active model
actions. Every predecessor target, terminal alias, task, session, action,
review, admission, merge, incident and Human Gate remains immutable.

The Codex executor for this program is governed jointly by
[permission routing](DCP_CODEX_EXECUTOR_PERMISSION_ROUTING_CONTRACT.md) and
[direct-executor routing](DCP_CODEX_DIRECT_EXECUTOR_ROUTING_CONTRACT.md). Those
contracts are not duplicated or weakened here.

## 2. Exact target and initial profile

The only new target tuple is:

| Field | Exact value |
| --- | --- |
| target / native project / session prefix | `wb-core` |
| repository | `orenvlad-ai/wb-core` |
| repository ID / owner ID | `1201929580` / `237411244` |
| visibility / default branch / PR base | public / `main` / `main` |
| initial task label | exactly `task:standard` |
| initial scope label | exactly `scope:repo-only` |
| required check | `baseline` on the current exact head |
| DCP policy | `dcp.wb-core.repo-only.release-train/v1` |
| physical merge/release actor | WBC GitHub Actions Release Train only |

`repo-only` grants no live-runtime, production, SSH, secret, runtime-data or
business-data access. The worker may change only task-authorized repository
files, must obey the exact current `wb-core` root `AGENTS.md`, must open one
ready same-repository pull request against `main`, and must not merge or apply
`release:ready`. No prompt or owner instruction may widen machine capability or
this static profile.

This preparation executor has read-only authority over `wb-core` current main,
root `AGENTS.md`, Release Train contract/workflow/code/tests and GitHub metadata.
It must not write a WBC file, branch, label, pull request or workflow.

## 3. Authority boundary

- The DCP daemon and SQLite own local task, model-action, ReviewRun, repair,
  arbiter, admission and incident facts.
- GitHub owns pull-request, head, base, label, check, review, merge and release
  facts.
- The existing WBC GitHub Actions Release Train is the sole physical merge and
  release actor for `wb-core`.
- The DCP terminal merger and direct provider merge path are statically
  ineligible for repository `orenvlad-ai/wb-core` under every profile and
  state. A fallback or manual DCP merge is forbidden.
- After exact-head fresh approval, successful exact-head `baseline`, exact
  provider/task/scope/head/base identity and FIFO admission, DCP may add only
  `release:ready`. It may not remove or rewrite WBC-owned terminal or incident
  labels and may not dispatch the Release Train directly.
- The Release Train owns physical merge and terminal `release:done`. DCP only
  observes exact GitHub terminal facts and records them locally.

The existing global maximum of three active DCP model actions, model-free
durable waits, arbiter priority, one findings repair followed by a fresh review
and one durable serialized admission/release line remain unchanged. A task
waiting for the Release Train consumes no model-action slot, process, timer,
poller, watcher or retry loop.

## 4. Mandatory Release Train compatibility gate

Read-only inspection of exact `wb-core` main
`93ef7ba6afa11871d9bad1636a7c452d39776f0c` found that the current Release Train
may synchronize a behind candidate branch, run a fresh `baseline` on the new
head and immediately merge it. It has no DCP exact-head admission marker or
readmission callback. Therefore the current workflow can replace a DCP-reviewed
head after admission and merge the replacement without a fresh DCP review.

That is incompatible with this contract. It is a repository-owned boundary,
not authority for this executor to change `wb-core`.

The new DCP target MUST remain fail-closed before task, native identity,
worktree, action or model mutation until exact fetched `wb-core` main contains
the repository-owned compatibility marker
`wb-core.dcp-release-handoff/v1` and the marker is bound by WBC code and tests
to all of these invariants:

1. a DCP-admitted exact head is never automatically synchronized or replaced;
2. a behind or drifting candidate loses merge eligibility and is returned to
   DCP readmission before any branch update or merge;
3. a replacement head requires a fresh successful `baseline`, fresh DCP review
   and new FIFO admission before `release:ready` can become merge-eligible;
4. only the WBC Release Train can physically merge and add `release:done`;
5. the terminal completion proof binds pull request number, exact merge SHA and
   contour `repo-only`.

An absent, ambiguous, mutable-only, wrong-ref or conflicting marker rejects
canonical submit before mutation. The installer may register and model-free
preflight the target while locked, but it must report the compatibility gate as
`blocked` rather than claiming substantive readiness.

WBC PR #984 subsequently satisfied this gate on exact current WBC main
`4735f74aedf1a1374dd4c8503799dd0761a61f22`. The marker is present in the WBC
Release Train authority, implementation and specification; those files bind
no-auto-sync, behind/head-drift ineligibility, fresh successful `baseline`,
fresh DCP review and FIFO readmission before a new `release:ready`. This changes
only the gate result from `blocked` to `qualified`; it does not widen DCP merge,
release, runtime or product authority.

### 4.1 Exact native-project identity lock

Marker compatibility is necessary but not sufficient for readiness. The
adapter-produced `wb-core` project config, the registered native project and
the compile-time policy in the exact installed/pinned managed source MUST have
the same `agentRules` bytes. The source-lock expectation is exactly 1149 UTF-8
bytes with SHA-256
`2e4b0d69593c004a4becb532ed07d59e9be087af884cdfea523fb3e918a84a64`.

Model-free readiness MUST never report `qualified` if any of the following
differs: the source-lock expectation, adapter-produced config, the single
registered `wb-core` native project config, target path, repository URL or
project kind. A readable adapter/project mismatch reports
`wb_core_compatibility=blocked`; ambiguous source-lock or database proof fails
preflight hard. Canonical submit MUST reject before reservation, native task,
session, action or model mutation in either case. A marker-only check may never
report `qualified`.

The sole permitted reconciliation is model-free `project set-config` through
the existing locked `register-wb-core` adapter after the ordinary reviewed
dev-control-plane correction has merged. It may update only the existing
native project's config and must preserve every task/session/action/history
row. It does not authorize a submit or model call.

The native CLI may persist exactly these additional empty default projections
when applying that minimal adapter config: top-level `agentConfig: {}`,
`orchestrator: {agentConfig: {}}`, `trackerIntake: {}` and
`containerReap: {}`. Readiness may normalize only their absence versus those
exact empty forms. A non-empty value, unknown extra key, changed worker,
reviewer, path, repository, project kind or policy rule remains blocked. These
storage defaults are not policy authority and are not compared by the installed
`ReviewRepositoryValidator`.

Managed-source change, source repin, application rebuild, install, stop or
restart are not required for this incident because exact installed source
`99e8243ac66bfdd7e77538368403d0a3b5964c21` already contains the correct
compile-time 1149-byte policy and rejects the stale registration. The defect
is confined to the dev-control-plane adapter/readiness comparison. Any contrary
source or artifact evidence fails closed into the full source -> pin -> install
sequence instead of using this bounded reconciliation.

## 5. DCP state and GitHub mapping

For this target only, successful FIFO admission changes local state to
`release_waiting` and atomically owns the one durable release line. The board
keeps its stock four columns and one card per task:

| DCP / GitHub fact | Board projection | Allowed next actor |
| --- | --- | --- |
| worker or bounded repair active | Working | DCP model action |
| fresh review queued/running | In Review / Arbiter | DCP Reviewer |
| compatible typed conflict | In Review / Arbiter | DCP Arbiter |
| FIFO admitted, `release:ready`, waiting or `release:running` | Ready to Merge | WBC Release Train |
| exact merge SHA, `release:done`, exact completion proof | Merged | none |
| head/base/label/check/proof drift | Needs You / incident | no automatic actor |

`release_waiting` is a zero-action wait. Restart reconciles the same admission,
pull request and exact admitted head. `release:ready` is added idempotently only
after re-reading every exact gate. If the pull-request head changes before
terminal completion, DCP fails closed and never treats the replacement as
reviewed or admitted. A merge without exact `release:done` and the completion
proof remains nonterminal; `release:done` without an exact merge SHA/proof is an
incident. Only the conjunction of exact merge SHA, terminal label and proof may
complete the local task.

The completion proof format currently owned by WBC is:

```text
<!-- wb-core-release-completion-proof contour=repo-only merge=<40-hex-sha> pr=<positive-number> -->
```

## 6. Qualification route, overlap and conflict

No permanent one-task WBC limit is introduced. After the compatibility gate
exists and this installed contour is separately proven, future owner dispatch
may qualify the policy in this order:

1. one safe repo-only canary;
2. three independent parallel tasks under the global three-action ceiling;
3. one named controlled two-task conflict/arbiter cohort;
4. a more complex named conflict only if evidence shows it is necessary.

Unexpected overlap is held fail-closed. Intentional overlap is eligible only
inside the exact named qualification cohort. The retired WBC watcher,
orchestration, passport and lane protocols are evidence only and gain no
authority.

## 7. Required source and model-free proof

The managed source may add only typed/static target policy, fail-closed
provider/profile/label/check/compatibility validation, Release Train handoff
and observation, the `release_waiting` projection and model-free tests. It must
not change DCP Worker/Reviewer/Arbiter model semantics outside the new target,
production behavior or any existing target.

Tests must prove:

- exact numeric/full-name/public/main/label/profile/check identity;
- absent or invalid compatibility marker rejects submit before durable or model
  mutation;
- `wb-core` can never reach `MergePullRequest` or another direct merge action;
- `release:ready` is the only DCP GitHub mutation and is exact-head guarded and
  idempotent;
- ready/running Release Train waits consume zero model actions;
- head drift, crossed labels/base/repository and false terminal proof fail
  closed;
- exact merge SHA plus `release:done` plus exact proof completes once;
- one serialized admission/release owner survives restart without duplicates;
- existing synthetic and browser-extension targets remain byte/behavior stable;
- UI/generated SQL/OpenAPI, Go race/build/vet, renderer and package gates pass.

No second service, database, registry, release train, watcher, poller, timer,
credential, retry policy, provider target launcher or manual merge path is
authorized.

## 8. Sequential delivery and terminal meaning

Delivery remains sequential:

1. merge this exact-head reviewed contract with green `baseline`;
2. merge one ordinary managed-source PR after exact-head semantic/security
   review and successful source/package checks;
3. merge one separate reviewed immutable pin/install-guard PR;
4. prove the canonical app stopped, then run deterministic
   `prepare -> build -> install -> preflight` with verified backup and receipt;
5. merge reviewed terminal evidence and leave canonical main clean and
   fast-forwarded.

Stages 1 through 4 are complete. Contract PR #218 merged at exact authority
`036b1101284f626c931f7edb1750ddd228634832`. Managed-source PR #62 exact head
`816320a7a88496f4ebbbea3e295a0a9bcf14015d` passed semantic/security review
`PRR_kwDOTydt6M8AAAABJxSgIw` and source/package workflow `32019792026`, then
merged at source `99e8243ac66bfdd7e77538368403d0a3b5964c21`, tree
`81b391c80eef98c5723340a1da8e42a3da1bbaec`. Pin/install-guard PR #219 exact
head `7447c4517238b05bc77bb3dea0fb2b0ad61fb483` passed review
`PRR_kwDOSUqHmc8AAAABJxmDHw` and baseline workflow `32023651860`, then merged
at `4fa942190385026d1e7f8e603940e6f625fc4e21`. Deterministic stopped install
created backup `i12-20260817T111735Z` and receipt SHA-256
`97c4b6c000fa51c571586c39ed1d096adc7fdcdd5838d8c0ad4e15006a96a9d6` for the
exact managed source and tree. Terminal proof is recorded in
[DCP_WB_CORE_RELEASE_TRAIN_HANDOFF_V1_TERMINAL_EVIDENCE.md](DCP_WB_CORE_RELEASE_TRAIN_HANDOFF_V1_TERMINAL_EVIDENCE.md)
and becomes authority only through its ordinary reviewed merge.

The preparation program launches no WBC task, session, worker, reviewer,
arbiter, repair, pull request, admission, merge or model call. Installed proof
requires SQLite integrity `ok`, preserved history, zero active model actions,
zero `wb-core` task/session/action rows, direct merger ineligibility and the app
stopped.

The predecessor evidence remains precisely `BLOCKED` for the interval in which
WBC main lacked the compatibility marker. The separately merged WBC change
cleared that marker blocker, but the first authorized canary exposed the
independent native-project rules drift described in section 4.1. The reviewed
adapter merge and one model-free existing-project reconciliation then wrote the
correct 1149-byte rules, but exposed the exact native empty-default projection
above. Current technical status remains `BLOCKED` pending reviewed merge of
that bounded normalization guard and terminal evidence. This is neither a
submit authorization nor owner acceptance.
