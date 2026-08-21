# Roadmap

The [current program manifest](DCP_WBC_INTEGRATION_TWIN_CURRENT_PROGRAM_MANIFEST.md)
is authoritative for stage and next-task truth. This roadmap shows the forward
sequence only. Git history, [Decisions](DECISIONS.md) and immutable evidence
retain predecessor chronology.

Technical completion never records owner acceptance. One curator-dispatched
repository change may be active at a time.

| Stage | Status | Exit evidence / next boundary |
| --- | --- | --- |
| 1. Architecture | COMPLETE | DCP-v2 Task -> Revision -> Command -> Action -> Admission -> Result architecture merged |
| 2. Persistent cell | COMPLETE | protected lab Release Train, artifact and persistent Selectel smoke proven |
| 3. Independent matrix | COMPLETE | positive, negative, replay, head/main drift and adapter/probe cases proven without DCP |
| 4. Provider-neutral core | COMPLETE | reviewed managed source and dormant schema core merged |
| 5. Install and activation | COMPLETE | adapter, issuer handoff, source pin, schema 84 activation and model-free preflight proven |
| 6. First same-identity canary | BLOCKED | direct DCP-v2 runner source complete, not installed; installed contour remains frozen until a later exact pin/install/migration/stopped-preflight gate |
| 7. Full twin qualification | NOT STARTED | requires Stage 6 continuation and independent real end-to-end qualification |
| 8. WBC read-only shadow | NOT STARTED | requires reviewed Stage 7 terminal evidence and separate owner authority |
| 9. Owner cutover | NOT STARTED | requires shadow evidence and break-before-make old actor off before new actor on |

## Current blocked phase

Aggregate source PR #76 and pin/install-authority PR #257 merged. The one
governed installation and one start were consumed. The native Worker produced
the exact local synthetic commit and succeeded, but DCP-v2 kept its Action
`running` with slot/runtime and its Task `worker_queued`; no remote branch or PR
was created.

The mandatory hard stop is active. Do not patch, restart, retry, reinstall or
manually publish the local target commit. The owner-authorized
[direct model authority phase](DCP_WBC_INTEGRATION_TWIN_STAGE6_DIRECT_MODEL_AUTHORITY_CONTRACT.md)
removed the legacy second-authority bridge in managed source and implemented a
stateless direct runner plus exact no-rerun adoption. The reviewed result is
the [source-complete evidence](DCP_WBC_INTEGRATION_TWIN_STAGE6_DIRECT_MODEL_SOURCE_COMPLETE_EVIDENCE.md).
It is not installed. A later exact pin/install/migration/stopped-preflight task
is required before any live attempt. Stage 7 is not started.

## Immutable stage records

- [Architecture](DCP_WBC_INTEGRATION_TWIN_DCP_V2_ARCHITECTURE_CONTRACT.md)
- [Stage 2 contract](DCP_WBC_INTEGRATION_TWIN_STAGE2_SELECTEL_PERSISTENT_CELL_CONTRACT.md)
  and [evidence](DCP_WBC_INTEGRATION_TWIN_STAGE2_TERMINAL_EVIDENCE.md)
- [Stages 3-4 contract](DCP_WBC_INTEGRATION_TWIN_STAGE3_4_COMBINED_EXECUTION_CONTRACT.md),
  [Stage 3 evidence](DCP_WBC_INTEGRATION_TWIN_STAGE3_TERMINAL_EVIDENCE.md),
  [Stage 4 evidence](DCP_WBC_INTEGRATION_TWIN_STAGE4_SOURCE_COMPLETE_EVIDENCE.md)
- [Stage 5 contract](DCP_WBC_INTEGRATION_TWIN_STAGE5_INSTALL_ACTIVATION_CONTRACT.md)
  and [evidence](DCP_WBC_INTEGRATION_TWIN_STAGE5_TERMINAL_EVIDENCE.md)
- [Stage 6 predecessor correction contract](DCP_WBC_INTEGRATION_TWIN_STAGE6_POST_SUBMIT_NATIVE_SHELL_CORRECTION_CONTRACT.md)
- [Stage 6 aggregate install and continuation contract](DCP_WBC_INTEGRATION_TWIN_STAGE6_AGGREGATE_INSTALL_CONTINUATION_CONTRACT.md)
- [Stage 6 aggregate continuation blocked evidence](DCP_WBC_INTEGRATION_TWIN_STAGE6_AGGREGATE_CONTINUATION_BLOCKED_EVIDENCE.md)
- [Stage 6 direct model authority contract](DCP_WBC_INTEGRATION_TWIN_STAGE6_DIRECT_MODEL_AUTHORITY_CONTRACT.md)
- [Stage 6 direct-model source-complete evidence](DCP_WBC_INTEGRATION_TWIN_STAGE6_DIRECT_MODEL_SOURCE_COMPLETE_EVIDENCE.md)

Historical WBC, DCP Lab and DCP v1 paths are indexed by
[Current operating contract](CURRENT_OPERATING_CONTRACT.md); they are not
active Stage 6 authority.
