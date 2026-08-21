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
The complete aggregate seam package is merged, and one governed aggregate
install plus same-identity continuation is active under its bounded contract.
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
- [Stage 6 aggregate install and continuation contract](docs/DCP_WBC_INTEGRATION_TWIN_STAGE6_AGGREGATE_INSTALL_CONTINUATION_CONTRACT.md)
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

The active aggregate install-authority audit is:

```sh
./scripts/i43_wbc_integration_twin_stage6_aggregate_install_audit.sh
```

These audits validate documentation and repository fixtures only. Running them
does not authorize a managed-source change, runtime control, live SQLite write,
submit, provider action, merge, deploy or production access.
