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
| 6. First same-identity canary | FINAL FREEZE/BLOCKED | one schema-87 install and adoption transaction occurred; gateway receipt validation failed, so replay/start/provider continuation are forbidden |
| 7. Full twin qualification | NOT STARTED / INELIGIBLE | final Stage 6 freeze blocks entry; requires a new owner program outside this pass |
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
It is installed once at schema `86` and stopped. The spent
[stable-source pin/install contract](DCP_WBC_INTEGRATION_TWIN_STAGE6_DIRECT_MODEL_STABLE_INSTALL_CONTRACT.md)
and [stable install complete evidence](DCP_WBC_INTEGRATION_TWIN_STAGE6_DIRECT_MODEL_STABLE_INSTALL_COMPLETE_EVIDENCE.md)
record the digest-bound backup, install, migration and stopped preflight. They
grant no restart, adoption or live attempt. A later owner-authorized attempt
stopped before live adoption because publication cannot bind the real PR number
to the immutable successor Revision before exact check observation. The
[same-identity adoption blocked evidence](DCP_WBC_INTEGRATION_TWIN_STAGE6_SAME_IDENTITY_ADOPTION_BLOCKED_EVIDENCE.md)
records the named defect, unconsumed schema-86 state and zero provider effect.
The [final viability contract](DCP_WBC_INTEGRATION_TWIN_STAGE6_FINAL_VIABILITY_CONTRACT.md)
authorized exactly one aggregate source correction and its complete model-free
matrix; that source and the one-use
[final pin/install/live contract](DCP_WBC_INTEGRATION_TWIN_STAGE6_FINAL_PIN_INSTALL_LIVE_CONTRACT.md)
were reviewed and merged. The final install reached schema `87`, but the sole
adoption response failed the reviewed lower-camel identity validator after its
transaction applied. The exact stopped, zero-provider state is recorded in the
[final freeze evidence](DCP_WBC_INTEGRATION_TWIN_STAGE6_FINAL_FREEZE_BLOCKED_EVIDENCE.md).
No replay, continuation or Stage 7 entry is authorized.

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
- [Stage 6 direct-model stable-source pin/install authority](DCP_WBC_INTEGRATION_TWIN_STAGE6_DIRECT_MODEL_STABLE_INSTALL_CONTRACT.md)
- [Stage 6 direct-model stable install complete evidence](DCP_WBC_INTEGRATION_TWIN_STAGE6_DIRECT_MODEL_STABLE_INSTALL_COMPLETE_EVIDENCE.md)
- [Stage 6 same-identity adoption blocked evidence](DCP_WBC_INTEGRATION_TWIN_STAGE6_SAME_IDENTITY_ADOPTION_BLOCKED_EVIDENCE.md)
- [Stage 6 final viability contract](DCP_WBC_INTEGRATION_TWIN_STAGE6_FINAL_VIABILITY_CONTRACT.md)
- [Stage 6 final pin/install/live contract](DCP_WBC_INTEGRATION_TWIN_STAGE6_FINAL_PIN_INSTALL_LIVE_CONTRACT.md)

Historical WBC, DCP Lab and DCP v1 paths are indexed by
[Current operating contract](CURRENT_OPERATING_CONTRACT.md); they are not
active Stage 6 authority.
