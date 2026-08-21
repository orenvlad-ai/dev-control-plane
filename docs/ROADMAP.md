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
| 6. First same-identity canary | ACTIVE | aggregate source merged; one governed install and same-identity continuation authorized |
| 7. Full twin qualification | NOT STARTED | requires Stage 6 continuation and independent real end-to-end qualification |
| 8. WBC read-only shadow | NOT STARTED | requires reviewed Stage 7 terminal evidence and separate owner authority |
| 9. Owner cutover | NOT STARTED | requires shadow evidence and break-before-make old actor off before new actor on |

## Active phase

Aggregate source PR #76 completed the model-free seam closure. The active phase
publishes one reviewed dev-control-plane pin/install authority package, performs
exactly one governed aggregate installation, starts once and follows the same
Task to a technical terminal outcome through the target Release Train.

If the one installation exposes another same-class pre-model/native-identity
predicate, stop patching and simplify or remove the legacy second-authority
bridge. Stage 7 is not part of this continuation.

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

Historical WBC, DCP Lab and DCP v1 paths are indexed by
[Current operating contract](CURRENT_OPERATING_CONTRACT.md); they are not
active Stage 6 authority.
