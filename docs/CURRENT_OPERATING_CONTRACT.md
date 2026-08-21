# Current operating contract

operating_contract_revision: 2026-08-21.3

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

Technical program state is `Stage 6 BLOCKED after aggregate install and
same-identity start`. Stages 1-5 are technically `COMPLETE`; owner acceptance
is not claimed.

The sole durable task is `dcp-v2-twin-canary-v1`. Its immutable v2 identities
are Revision `v2-13f81f321f99d1117dc931419e0bea3945ee35a5`, Command
`v2-e028f779a18417e990911057f7db7c666f7487ca` and Worker Action
`v2-40f87d048813533daa1108b4316c09139acf0a8f`. No second submit or replacement
Task is permitted.

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
  co-tenant mutation is permitted. Managed source is frozen at PR #76.
- The one aggregate install and one governed start are spent. The local canary
  commit may not be manually pushed or converted into a provider effect.

## Historical authority index

- [DCP-v2 architecture](DCP_WBC_INTEGRATION_TWIN_DCP_V2_ARCHITECTURE_CONTRACT.md)
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
