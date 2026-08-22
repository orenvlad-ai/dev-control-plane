# Current operating contract

operating_contract_revision: 2026-08-23.1

## Operational entry

The [current integration-twin program manifest](DCP_WBC_INTEGRATION_TWIN_CURRENT_PROGRAM_MANIFEST.md)
is the single active source for the final goal, present stage, immutable
identity, proven blockers, anti-cycle tactic and curator rotation. Root
[`AGENTS.md`](../AGENTS.md) supplies mandatory repository, routing, safety,
review and completion rules.

When sources differ, use this order:

1. machine-reported effective context and current read-only state;
2. explicit owner authority for the current task;
3. this operating contract and root `AGENTS.md`;
4. the current program manifest;
5. the applicable stage contract;
6. linked immutable evidence and Git history.

Historical documents remain authoritative evidence of what happened. Their
old “active”, “next” or “prohibited until” language is not present authority
after a later reviewed and merged stage record supersedes it.

## Executor qualification

The [permission-routing contract](DCP_CODEX_EXECUTOR_PERMISSION_ROUTING_CONTRACT.md)
requires fresh machine proof of `approval_policy=never`, unrestricted
filesystem, network enabled, a ready separate Git worktree and platform
approval count `0`. The
[direct-executor routing contract](DCP_CODEX_DIRECT_EXECUTOR_ROUTING_CONTRACT.md)
requires one separate visible user-owned executor and zero curator-side
collaboration subagents, forks, nested executors or parallel DCP tasks.

Qualification grants capability, not task authority. A task may use only the
repositories, state and mutation surfaces explicitly placed in scope.

## Current integration-twin checkpoint

Technical program state is `Stage 6 FINAL FREEZE/BLOCKED; schema 87 stopped
after one adoption transaction applied but its reviewed gateway response
validation failed; zero provider effect`. Stages 1-5 are technically
`COMPLETE`; Stage 7 is not started and owner acceptance is not claimed.

The sole durable task is `dcp-v2-twin-canary-v1`. Its original immutable Worker
identities remain Revision `v2-13f81f321f99d1117dc931419e0bea3945ee35a5`,
Command `v2-e028f779a18417e990911057f7db7c666f7487ca` and Action
`v2-40f87d048813533daa1108b4316c09139acf0a8f`. The consumed adoption created
current Worker-output Revision `v2-0e1aadfb444bc4d9f4c90c8bf936a0ebec125300`
and pending publication Command `v2-06b20be020812369bf4286fd335aa8f5281d15e2`.
No second submit or replacement Task is permitted.

The terminal 2026-08-21 read-only machine checkpoint proved:

- schema `85`; v2 Task/Revision/Command/Action counts `1/1/1/1`, with zero
  Admission, Incident, ExternalEvent or Result;
- native card `1`, session `dcp-wbc-integration-lab-1`, policy task
  `ci_waiting` revision `4`, idle session and no runtime launch id;
- native initial Worker Action sequence `74` succeeded and released slot `1`,
  leaving zero active legacy model Actions;
- the v2 Action remained falsely `running`, slot `1`, runtime
  `78535564-a2bc-478c-80b0-207753f2152c`, and the Task remained
  `worker_queued` after that native terminal fact;
- installed managed source/tree
  `d084ae3cf0cb3e5e32ebefa197031c24a2b6392d` /
  `a6e3c3347bbbddd256e9edbfc541f115813249d2`;
- exact replaced predecessor source/tree
  `11401ff6eadb80fd87e48229fb8c5458095a63b1` /
  `91bf6e25ec1b0e0f971ad36f7b80272aded2482c`;
- exactly one aggregate install created backup `i12-20260821T120041Z` and
  machine-computed receipt SHA-256
  `19550a9f02b14f13be8a80214529025fd6d4fe7dc8e5bd12c5eaa1a47dd54b0c`;
- the Worker produced local commit
  `bebbf8f617f1a6fa0b9e91698fe710fe0a2bad2c`, but no remote branch, PR or
  downstream provider effect.

Managed-source PR #76 is now merged at aggregate source commit
`d084ae3cf0cb3e5e32ebefa197031c24a2b6392d`, tree
`a6e3c3347bbbddd256e9edbfc541f115813249d2`. Its exact package head was
`b0c2b6df76adf205229e49c48a1d7277aa7b5059`; workflow `32477135149` passed
`package` and `source`, review `4992765757` was bound to that head and review
threads were zero.

Fresh GitHub readback found lab main
`375b9b2d0b4c2fce6f2c417850553f79e24a0d92`, no canary PR and no lab workflow
run after the Stage 5 issuer handoff. WBC PR #987 remains open at
`26044c696651ce5873748ec3f920d40e77c5686c`, `BEHIND`, without release labels.
The protected Luchiki co-tenant was not probed or mutated by this documentation
pass; its last immutable boundary remains the linked Stage 5 evidence.

The 2026-08-22 stopped readback supersedes only the installed-contour fields:

- authority PR #261 merged as
  `74b421ccf2eefcbd80e3716935056874f38509f5`, tree
  `d7609aa9cbfc5575279ea36c48e8b5de3b710dc4`;
- exactly one stable-source direct install and migration `0086` completed;
  rollback count is zero and the app/daemon remain stopped;
- installed source/tree are now
  `e9eb18a99db71813ac8c4556a614d6a3ce4108aa` /
  `b4db2b329accc9a93691bda7c306cc864b07ee56`, with receipt SHA-256
  `fc8f2a2f6264dc1a3e817e42f124bdbd7040a412eade3fcddf97762f59f214d8`;
- schema is exactly `86`, integrity is `ok`, foreign-key violations are zero,
  the same v2 rows remain `1/1/1/1`, downstream rows remain `0/0/0/0`, and
  direct runtime/terminal/adoption rows are `0/0/0`;
- the exact native Action, idle session and local Worker commit are unchanged;
  no start, adoption, publication or external provider effect occurred.

The complete machine record is the
[stable install complete evidence](DCP_WBC_INTEGRATION_TWIN_STAGE6_DIRECT_MODEL_STABLE_INSTALL_COMPLETE_EVIDENCE.md).

## Proven blocker and exhausted authority

The recovery install historically exposed two independent defects before model
launch:

1. the DCP-v2 service emits the live-runtime task prompt while the legacy
   session manager validates the synthetic prompt, producing reserved Command
   identity drift;
2. lifecycle projection reports `modelActive=true` for a `launching` Action
   even though no runtime id, runtime process or running native model Action
   exists.

Aggregate source PR #76 closed those defects locally. Pin/install-authority PR
#257 merged, the aggregate installer ran exactly once, stopped preflight
preserved the same identity and the governed start adopted the existing Worker.
The native Worker then succeeded, but its terminal fact did not reconcile the
DCP-v2 Action or Task. The DCP-v2 Action stayed `running` with its runtime and
slot while the native Action was `succeeded`, slot `0`, and its session idle.
That false terminal runtime/model projection is the exact technical blocker.

The
[Stage 6 aggregate continuation contract](DCP_WBC_INTEGRATION_TWIN_STAGE6_AGGREGATE_INSTALL_CONTINUATION_CONTRACT.md)
is spent. Its mandatory hard stop prohibits a corrective patch, restart, retry,
reinstall, substitute identity or manual target publication. The complete
observed record is the
[Stage 6 aggregate continuation blocked evidence](DCP_WBC_INTEGRATION_TWIN_STAGE6_AGGREGATE_CONTINUATION_BLOCKED_EVIDENCE.md).
Any successor requires separate owner architecture/source authority and must
simplify or remove the legacy second-authority bridge before another live
attempt.

## Completed architecture/source package

The owner has selected complete removal of the DCP-v2 legacy second-authority
bridge. The
[direct model authority contract](DCP_WBC_INTEGRATION_TWIN_STAGE6_DIRECT_MODEL_AUTHORITY_CONTRACT.md)
makes DCP SQLite and the DCP daemon the sole Task/Revision/Command/Action and
model-runtime lifecycle authority. A typed runner is stateless transport only;
DCP-v2 may not maintain, dual-write or reconcile current lifecycle through
legacy policy-task, session or model-action state.

Architecture PR #259 and managed-source PR #77 are reviewed, green and merged.
The [direct-model source-complete evidence](DCP_WBC_INTEGRATION_TWIN_STAGE6_DIRECT_MODEL_SOURCE_COMPLETE_EVIDENCE.md)
records their exact heads, trees, reviews, checks and merges, the disposable
schema-85 proof and the complete model-free matrix. The merged source contains
an exact idempotent no-model adoption of the frozen Worker terminal receipt and
local commit into the same durable Task, followed by a model-free publication
Command that was not executed in this phase.

The direct model authority source is complete and installed at schema `86`.
The Task contradiction and local canary commit remain frozen and unconsumed in
the stopped contour.

## Completed stable-source pin/install boundary

The owner separately authorized the
[stable-source pin/install contract](DCP_WBC_INTEGRATION_TWIN_STAGE6_DIRECT_MODEL_STABLE_INSTALL_CONTRACT.md).
It binds PR #77 merge `e9eb18a99db71813ac8c4556a614d6a3ce4108aa`, tree
`b4db2b329accc9a93691bda7c306cc864b07ee56`, to one permanent standalone
managed-source clone, one staged source/artifact package, one governed install,
forward-only migration `0086`, and a stopped preflight.

The prior `MANAGED_SOURCE_WORKTREE_DRIFT` attempt stopped before any authority
PR, backup, app stop, install, migration or rollback and had no live/provider
effect. Its task-owned source path is not recovered or reused. The new guard
rejects task worktrees, temporary roots, symlinks, linked Git metadata, dirty or
foreign repositories, commit/tree drift, filesystem-identity drift, staged
digest mismatch and equal rerun. The installer never clones source and consumes
only digest-bound staged bytes after app stop.

Authority PR #261, one stable-source backup/install, migration `0086` and the
stopped preflight are complete. The exact result is recorded in the
[stable install complete evidence](DCP_WBC_INTEGRATION_TWIN_STAGE6_DIRECT_MODEL_STABLE_INSTALL_COMPLETE_EVIDENCE.md).
That authority is now spent. It grants no restart, adoption, successor
Revision, publication, model/provider call, target change, Stage 7, WBC,
Selectel or production mutation. Stage 6 remains `BLOCKED`; Stage 7 and later
surfaces remain fenced.

## Same-identity adoption safe stop

The owner later authorized one separately reviewed same-identity adoption and
live-continuation phase. Before its authority package or any live mutation,
exact installed-source inspection found
`DCP_V2_PUBLICATION_REVISION_PR_BINDING_MISSING`: the Worker receipt creates an
immutable successor Revision with `PRNumber=0`; publication does not bind its
real PR number back to that Revision; and the first check event requires the
observed non-zero PR to equal the unchanged Revision value. A disposable-copy,
model-free adoption proved the exact successor/publication boundary without
touching live SQLite or a provider.

This is a managed-source defect. The command's automatic safe stop therefore
ended before an adoption authority PR, live adoption, start, model call or
provider effect. The stopped schema-86 contour remains unconsumed with direct
runtime/terminal/adoption rows `0/0/0` and `adoptionConsumed=false`. The exact
record is the
[same-identity adoption blocked evidence](DCP_WBC_INTEGRATION_TWIN_STAGE6_SAME_IDENTITY_ADOPTION_BLOCKED_EVIDENCE.md).
The owner authorized exactly one aggregate managed-source correction
under the
[Stage 6 final viability contract](DCP_WBC_INTEGRATION_TWIN_STAGE6_FINAL_VIABILITY_CONTRACT.md).
Architecture PR #264 and managed-source PR #78 are now reviewed, green and
merged. The merged source is `d10a9791392e19510590c3fb4a3d231fe980ecf6`,
tree `acd93511dd1c77dd2508734bf0b8d331594115cf`; merged-main CI
`32591004094` passed both source and package jobs. It covers forward migration
`0087`, immutable provider-bound publication and the complete downstream seam.

The
[final pin/install/live contract](DCP_WBC_INTEGRATION_TWIN_STAGE6_FINAL_PIN_INSTALL_LIVE_CONTRACT.md)
was reviewed and merged through authority PR #265 as
`a53687edf44bd72d10495993993f292a6e21720d`. Its single install and migration
`0087` completed with receipt
`9183c6207908de6f638360b86b8f6e1393d7fc8f0d169e10ac8e0b9dd97421ca`.
The stopped schema-87 preflight was exact.

The single adoption command then committed its same-identity transaction but
serialized the nested adoption object with PascalCase Go field names. The
reviewed gateway required lower-camel JSON, returned
`Stage 6 final adoption response identity differs` and recorded the attempt as
`failed-or-ambiguous`. Durable state is Task/Revision/Command/Action
`1/2/2/1`, direct runtime/terminal/adoption rows `1/1/1`, zero active model
state, app/daemon stopped and zero provider effect. The attempt may not be
replayed and the app may not be started. The exact record is the
[final freeze blocked evidence](DCP_WBC_INTEGRATION_TWIN_STAGE6_FINAL_FREEZE_BLOCKED_EVIDENCE.md).

Stage 6 is `FINAL FREEZE/BLOCKED`. All source/install/adoption/start authority
in the final pass is spent or unusable. Do not patch, reinstall, replay,
continue, publish the canary or begin Stage 7.

## Target and completion boundaries

- Admission decides whether and in what FIFO order an exact reviewed head may
  release. The target repository's Release Train is the sole merge/deploy
  actor.
- DCP and model roles never merge or deploy, never receive production secrets
  and never infer target success.
- `repo-only` requires exact admitted-head merge and immutable release proof.
  `live-runtime` additionally requires exact deployed SHA, canonical target,
  health and provenance proof.
- At most three model Actions are globally active. `workflowActive` remains
  distinct from truthful `modelActive`.
- Human Gate is only a genuine owner decision. Technical defects fail closed.
  Technical completion never synthesizes owner acceptance.
- WBC PR #987 and production remain immutable. Selectel may be touched only by
  the exact integration-lab Release Train; no manual SSH/service action or
  co-tenant mutation is permitted. The managed-source PR budget is spent.
- The aggregate install/start, direct-model stopped install and final
  schema-87 install/adoption are spent. The consumed failed/ambiguous adoption
  may not be replayed; the local canary commit may not be manually pushed or
  converted into a provider effect.

## Historical authority index

- [DCP-v2 architecture](DCP_WBC_INTEGRATION_TWIN_DCP_V2_ARCHITECTURE_CONTRACT.md)
- [Stage 6 final viability contract](DCP_WBC_INTEGRATION_TWIN_STAGE6_FINAL_VIABILITY_CONTRACT.md)
- [Stage 6 final pin/install/live contract](DCP_WBC_INTEGRATION_TWIN_STAGE6_FINAL_PIN_INSTALL_LIVE_CONTRACT.md)
- [Stage 6 final freeze blocked evidence](DCP_WBC_INTEGRATION_TWIN_STAGE6_FINAL_FREEZE_BLOCKED_EVIDENCE.md)
- [Stage 6 direct model authority](DCP_WBC_INTEGRATION_TWIN_STAGE6_DIRECT_MODEL_AUTHORITY_CONTRACT.md)
  and [source-complete evidence](DCP_WBC_INTEGRATION_TWIN_STAGE6_DIRECT_MODEL_SOURCE_COMPLETE_EVIDENCE.md)
- [Stage 6 direct-model stable-source pin/install authority](DCP_WBC_INTEGRATION_TWIN_STAGE6_DIRECT_MODEL_STABLE_INSTALL_CONTRACT.md)
  and [stopped install evidence](DCP_WBC_INTEGRATION_TWIN_STAGE6_DIRECT_MODEL_STABLE_INSTALL_COMPLETE_EVIDENCE.md)
- [Stage 6 same-identity adoption blocked evidence](DCP_WBC_INTEGRATION_TWIN_STAGE6_SAME_IDENTITY_ADOPTION_BLOCKED_EVIDENCE.md)
- [Stage 2 persistent-cell contract](DCP_WBC_INTEGRATION_TWIN_STAGE2_SELECTEL_PERSISTENT_CELL_CONTRACT.md)
  and [terminal evidence](DCP_WBC_INTEGRATION_TWIN_STAGE2_TERMINAL_EVIDENCE.md)
- [Stages 3-4 execution contract](DCP_WBC_INTEGRATION_TWIN_STAGE3_4_COMBINED_EXECUTION_CONTRACT.md),
  [Stage 3 evidence](DCP_WBC_INTEGRATION_TWIN_STAGE3_TERMINAL_EVIDENCE.md) and
  [Stage 4 evidence](DCP_WBC_INTEGRATION_TWIN_STAGE4_SOURCE_COMPLETE_EVIDENCE.md)
- [Stage 5 contract](DCP_WBC_INTEGRATION_TWIN_STAGE5_INSTALL_ACTIVATION_CONTRACT.md)
  and [terminal evidence](DCP_WBC_INTEGRATION_TWIN_STAGE5_TERMINAL_EVIDENCE.md)
- [Stage 6 native-shell correction contract](DCP_WBC_INTEGRATION_TWIN_STAGE6_POST_SUBMIT_NATIVE_SHELL_CORRECTION_CONTRACT.md)
- [Stage 6 aggregate install and continuation contract](DCP_WBC_INTEGRATION_TWIN_STAGE6_AGGREGATE_INSTALL_CONTINUATION_CONTRACT.md)
- [Stage 6 aggregate continuation blocked evidence](DCP_WBC_INTEGRATION_TWIN_STAGE6_AGGREGATE_CONTINUATION_BLOCKED_EVIDENCE.md)
- Historical WBC lines:
  [Release Train handoff](DCP_WB_CORE_RELEASE_TRAIN_HANDOFF_V1_CONTRACT.md),
  [CI/lifecycle](DCP_WB_CORE_CI_TRUTH_LIFECYCLE_UX_V1_CONTRACT.md),
  [end-to-end release/deploy](DCP_WB_CORE_END_TO_END_RELEASE_DEPLOY_V1_CONTRACT.md)
  and [task-first lifecycle](DCP_TASK_FIRST_NATIVE_LIFECYCLE_V1_CONTRACT.md).
- Older [DCP v1 target architecture](TARGET_ARCHITECTURE_V1.md) and
  [DCP Lab happy path v1](DCP_LAB_HAPPY_PATH_V1_CONTRACT.md) remain historical
  design/evidence inputs, not current Stage 6 continuation authority.
