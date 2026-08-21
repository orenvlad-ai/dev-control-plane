# Current operating contract

operating_contract_revision: 2026-08-21.1

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

Technical program state is `Stage 6 BLOCKED before model launch`. Stages 1-5
are technically `COMPLETE`; owner acceptance is not claimed.

The sole durable task is `dcp-v2-twin-canary-v1`. Its immutable v2 identities
are Revision `v2-13f81f321f99d1117dc931419e0bea3945ee35a5`, Command
`v2-e028f779a18417e990911057f7db7c666f7487ca` and Worker Action
`v2-40f87d048813533daa1108b4316c09139acf0a8f`. No second submit or replacement
Task is permitted.

The 2026-08-21 read-only machine checkpoint proved:

- schema `85`; v2 Task/Revision/Command/Action counts `1/1/1/1`, with zero
  Admission, Incident, ExternalEvent or Result;
- native card `1`, session `dcp-wbc-integration-lab-1`, exact task reserved;
- v2 Action `launching`, native model Action `queued`, zero active legacy model
  Actions and no model process or runtime handle;
- installed managed source/tree
  `11401ff6eadb80fd87e48229fb8c5458095a63b1` /
  `91bf6e25ec1b0e0f971ad36f7b80272aded2482c`;
- recovery backup `i12-20260821T043432Z` and machine-computed receipt SHA-256
  `098056d800d41f666708b7697d6ccef9f3b5cd2e077a939d89dcf0b1f35767e2`;
- application and daemon ready on their existing contour; this observation is
  not permission to stop, start or restart them.

Fresh GitHub readback found lab main
`375b9b2d0b4c2fce6f2c417850553f79e24a0d92`, no canary PR and no lab workflow
run after the Stage 5 issuer handoff. WBC PR #987 remains open at
`26044c696651ce5873748ec3f920d40e77c5686c`, `BEHIND`, without release labels.
The protected Luchiki co-tenant was not probed or mutated by this documentation
pass; its last immutable boundary remains the linked Stage 5 evidence.

## Proven blockers and remaining authority

The recovery install completed its exact schema/native-shell correction. It
then exposed two independent defects before any model launch:

1. the DCP-v2 service emits the live-runtime task prompt while the legacy
   session manager validates the synthetic prompt, producing reserved Command
   identity drift;
2. lifecycle projection reports `modelActive=true` for a `launching` Action
   even though no runtime id, runtime process or running native model Action
   exists.

The prior
[Stage 6 native-shell correction contract](DCP_WBC_INTEGRATION_TWIN_STAGE6_POST_SUBMIT_NATIVE_SHELL_CORRECTION_CONTRACT.md)
and recovery pin are spent historical authority. They do not authorize another
managed-source PR, install or live continuation.

The next phase may begin only through a separate owner-launched source task. It
must freeze the live Task and use an exact disposable schema-85 snapshot plus
one managed-source worktree to close the whole DCP-v2 to legacy-native seam in
one branch and one aggregate source package. It must not install per defect.
Any later formal source review/pin/install/live continuation is a separate
authority gate. The hard stop in the current manifest is mandatory.

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
- WBC PR #987, production, Selectel/Luchiki, managed source, installed runtime
  and live SQLite are immutable unless a later task names and authorizes the
  exact surface.

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
- Historical WBC lines:
  [Release Train handoff](DCP_WB_CORE_RELEASE_TRAIN_HANDOFF_V1_CONTRACT.md),
  [CI/lifecycle](DCP_WB_CORE_CI_TRUTH_LIFECYCLE_UX_V1_CONTRACT.md),
  [end-to-end release/deploy](DCP_WB_CORE_END_TO_END_RELEASE_DEPLOY_V1_CONTRACT.md)
  and [task-first lifecycle](DCP_TASK_FIRST_NATIVE_LIFECYCLE_V1_CONTRACT.md).
- Older [DCP v1 target architecture](TARGET_ARCHITECTURE_V1.md) and
  [DCP Lab happy path v1](DCP_LAB_HAPPY_PATH_V1_CONTRACT.md) remain historical
  design/evidence inputs, not current Stage 6 continuation authority.
