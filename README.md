# Development Control Plane

This public repository owns DCP architecture, operating authority, immutable
qualification evidence and one bounded local integration adapter. Managed
application source lives in
[`orenvlad-ai/dcp-orchestrator`](https://github.com/orenvlad-ai/dcp-orchestrator);
target repositories own their Release Trains. DCP is not a production control
plane.

## Current program

Start with the
[WBC integration twin current program manifest](docs/DCP_WBC_INTEGRATION_TWIN_CURRENT_PROGRAM_MANIFEST.md).
It is the single active statement of the final outcome, exact current
checkpoint, program stages, blockers, anti-cycle tactic and curator-rotation
readback.

Stages 1-5 are technically complete. Stage 6 preserves the sole durable Task
`dcp-v2-twin-canary-v1`; no second submit or replacement identity is permitted.
The complete aggregate seam package, one governed installation and one start
are spent. The native Worker succeeded, but DCP-v2 remained falsely active, so
Stage 6 is technically blocked under the mandatory hard stop. The
owner-selected replacement is now source-complete: DCP-v2 is the sole
model-runtime authority behind a stateless typed runner, with one exact
no-rerun adoption of the frozen Worker output. The exact source is now
installed once at schema `86` and stopped, with digest-bound recovery evidence.
The install authority is spent. A later owner-authorized adoption/live attempt
stopped before live adoption on
`DCP_V2_PUBLICATION_REVISION_PR_BINDING_MISSING`: publication cannot bind its
real PR number to the immutable successor Revision before exact check
observation. Schema `86` remains stopped and unconsumed with zero provider
effect.
The final bounded viability source correction is now reviewed, green and
merged under the
[final viability contract](docs/DCP_WBC_INTEGRATION_TWIN_STAGE6_FINAL_VIABILITY_CONTRACT.md).
It covers schema `87`, immutable provider-bound publication and the complete
downstream seam. One separately reviewed
[final pin/install/live authority](docs/DCP_WBC_INTEGRATION_TWIN_STAGE6_FINAL_PIN_INSTALL_LIVE_CONTRACT.md)
is the sole next gate; it grants no live mutation before its merge.
Stage 7, WBC shadow, production and cutover remain fenced.

Technical completion is not owner acceptance.

## Delivery model

One bounded curator decision becomes one submit and one stable Task/card.
Immutable exact-head Revisions and durable Commands drive bounded model Actions,
exact CI, a fresh context-free review, at most one task-level findings repair,
mechanical FIFO Admission and a repository-owned Release Train. The Release
Train alone merges the exact admitted head, builds the exact artifact, performs
an applicable persistent deploy and publishes immutable proof.

DCP and model roles never merge or deploy, never receive production secrets
and never synthesize owner acceptance. At most three model Actions may be
globally active; workflow activity and truthful model activity are separate.
Human Gate is reserved for a genuine owner decision. Technical defects fail
closed.

## Repository map

- [Repository rules](AGENTS.md)
- [Current operating contract](docs/CURRENT_OPERATING_CONTRACT.md)
- [Current program manifest](docs/DCP_WBC_INTEGRATION_TWIN_CURRENT_PROGRAM_MANIFEST.md)
- [DCP-v2 architecture](docs/DCP_WBC_INTEGRATION_TWIN_DCP_V2_ARCHITECTURE_CONTRACT.md)
- [Stage 6 final viability contract](docs/DCP_WBC_INTEGRATION_TWIN_STAGE6_FINAL_VIABILITY_CONTRACT.md)
- [Stage 6 final pin/install/live contract](docs/DCP_WBC_INTEGRATION_TWIN_STAGE6_FINAL_PIN_INSTALL_LIVE_CONTRACT.md)
- [Stage 6 direct DCP-v2 model authority](docs/DCP_WBC_INTEGRATION_TWIN_STAGE6_DIRECT_MODEL_AUTHORITY_CONTRACT.md)
- [Stage 6 direct-model source-complete evidence](docs/DCP_WBC_INTEGRATION_TWIN_STAGE6_DIRECT_MODEL_SOURCE_COMPLETE_EVIDENCE.md)
- [Stage 6 direct-model stable-source pin/install authority](docs/DCP_WBC_INTEGRATION_TWIN_STAGE6_DIRECT_MODEL_STABLE_INSTALL_CONTRACT.md)
- [Stage 6 direct-model stable install complete evidence](docs/DCP_WBC_INTEGRATION_TWIN_STAGE6_DIRECT_MODEL_STABLE_INSTALL_COMPLETE_EVIDENCE.md)
- [Stage 6 same-identity adoption blocked evidence](docs/DCP_WBC_INTEGRATION_TWIN_STAGE6_SAME_IDENTITY_ADOPTION_BLOCKED_EVIDENCE.md)
- [Stage 6 aggregate install and continuation contract](docs/DCP_WBC_INTEGRATION_TWIN_STAGE6_AGGREGATE_INSTALL_CONTINUATION_CONTRACT.md)
- [Stage 6 aggregate continuation blocked evidence](docs/DCP_WBC_INTEGRATION_TWIN_STAGE6_AGGREGATE_CONTINUATION_BLOCKED_EVIDENCE.md)
- [Project brief](docs/PROJECT_BRIEF.md)
- [Roadmap](docs/ROADMAP.md)
- [Decisions](docs/DECISIONS.md)
- [Historical DCP v1 architecture](docs/TARGET_ARCHITECTURE_V1.md)
- [Upstream qualification](docs/UPSTREAM_QUALIFICATION.md)

Linked stage contracts and evidence retain immutable chronology. Historical
“active” or “next” language is not current authority after a later reviewed and
merged stage record supersedes it.

## Model-free audit

The GitHub `Baseline` workflow runs the repository's shell and fixture audits,
including the current-manifest topology/status audit. The local entry for the
full deterministic contour is:

```sh
./scripts/i12_audit.sh
```

The current manifest-specific entry is:

```sh
./scripts/i42_wbc_integration_twin_current_manifest_audit.sh
```

The terminal Stage 6 evidence audit is:

```sh
./scripts/i44_wbc_integration_twin_stage6_aggregate_terminal_audit.sh
```

The direct-model source-complete audit is:

```sh
./scripts/i46_wbc_integration_twin_direct_model_source_audit.sh
```

The stable-source pin/install authority audit is:

```sh
./scripts/i47_wbc_integration_twin_stage6_direct_install_audit.sh
```

The stopped-install terminal evidence audit is:

```sh
./scripts/i48_wbc_integration_twin_stage6_direct_install_terminal_audit.sh
```

The same-identity adoption blocked evidence audit is:

```sh
./scripts/i49_wbc_integration_twin_stage6_adoption_blocked_audit.sh
```

The final viability authority audit is:

```sh
./scripts/i50_wbc_integration_twin_stage6_final_viability_authority_audit.sh
```

The final pin/install/live authority audit is:

```sh
./scripts/i51_wbc_integration_twin_stage6_final_pin_live_audit.sh
```

These audits validate documentation and repository fixtures only. Running them
does not authorize a managed-source change, runtime control, live SQLite write,
submit, provider action, merge, deploy or production access.
