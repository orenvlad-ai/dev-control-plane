# Project brief

## Purpose

DCP coordinates one durable software-delivery Task from bounded curator intent
through immutable revisions, commands, model work, exact CI/review, mechanical
admission and a repository-owned Release Train. It preserves identity and
truthful state across drift and restart. It is not a production control plane.

The single current entry is the
[WBC integration twin current program manifest](DCP_WBC_INTEGRATION_TWIN_CURRENT_PROGRAM_MANIFEST.md).
Use linked contracts and evidence for historical facts, not duplicated current
state.

## Target outcome

One submit creates one stable Task/card. Each exact head is an immutable
Revision driven by durable Commands. One bounded Worker produces repository
work; exact CI and a fresh context-free Reviewer decide it; at most one
task-level findings repair creates a new head and new review. Mechanical FIFO
Admission decides release eligibility and order. The target repository's simple
Release Train merges the exact admitted head, builds the exact artifact,
performs an applicable persistent deploy and publishes immutable merge,
deployed-SHA, health and provenance proof.

A repo-only Task may finish at exact release/merge proof. A deployable Task
finishes only after verified deploy. DCP and model roles never merge or deploy,
never receive production secrets and never synthesize owner acceptance.

## Governing invariants

- One Task survives head/base drift and restart without resubmit or duplicate
  model calls.
- At most three model Actions are globally active; `workflowActive` and
  truthful `modelActive` are separate.
- Human Gate is reserved for a genuine owner decision. Technical defects fail
  closed with a named state.
- Admission orders exact reviewed heads; Release Train is the only merge/deploy
  actor.
- Cutover is break-before-make: old actor off before new actor on.
- Capability qualification, owner authorization, source review, install,
  runtime, provider and production authority are separate gates.

## Current program

Stages 1-5 of the WBC integration twin are technically `COMPLETE`. Stage 6 is
`BLOCKED` on the sole durable identity `dcp-v2-twin-canary-v1`; a second submit
or replacement Task is forbidden. Aggregate source PR #76, pin/install PR #257,
the one governed installation and one start are complete and spent. The native
Worker succeeded, but its terminal fact left the DCP-v2 Worker Action falsely
`running` and the Task `worker_queued`.

The mandatory hard stop prohibits patch, restart, retry, reinstall, manual
target publication or substitute identity. Complete removal of the legacy
second-authority bridge is now source-complete: DCP-v2 owns model lifecycle
directly through a stateless typed runner and can adopt the existing Worker
output once without a rerun. The exact source is installed once at schema `86`
and stopped; authority PR #261, the stable-source guard, digest-bound staged
package, governed install, migration and stopped preflight are complete. The
[stable install complete evidence](DCP_WBC_INTEGRATION_TWIN_STAGE6_DIRECT_MODEL_STABLE_INSTALL_COMPLETE_EVIDENCE.md)
records the exact result. A later owner-authorized adoption/live attempt stopped
before adoption on
`DCP_V2_PUBLICATION_REVISION_PR_BINDING_MISSING`; the exact
[safe-stop evidence](DCP_WBC_INTEGRATION_TWIN_STAGE6_SAME_IDENTITY_ADOPTION_BLOCKED_EVIDENCE.md)
proves schema `86` stopped, `adoptionConsumed=false` and zero provider effect.
The owner-authorized aggregate source correction under the
[final viability contract](DCP_WBC_INTEGRATION_TWIN_STAGE6_FINAL_VIABILITY_CONTRACT.md),
including migration `0087`, immutable provider-bound publication and the full
downstream seam, is reviewed, green and merged. The live contour remains
frozen pending the one reviewed
[final pin/install/live authority](DCP_WBC_INTEGRATION_TWIN_STAGE6_FINAL_PIN_INSTALL_LIVE_CONTRACT.md).
See the
[terminal evidence](DCP_WBC_INTEGRATION_TWIN_STAGE6_AGGREGATE_CONTINUATION_BLOCKED_EVIDENCE.md).
The governing source boundary and exact result are the
[direct model authority contract](DCP_WBC_INTEGRATION_TWIN_STAGE6_DIRECT_MODEL_AUTHORITY_CONTRACT.md)
and [source-complete evidence](DCP_WBC_INTEGRATION_TWIN_STAGE6_DIRECT_MODEL_SOURCE_COMPLETE_EVIDENCE.md).

Stage 7 must independently qualify the complete real twin path, including
restart/dedupe, parallelism, conflicts and adversarial cases. Stage 8 WBC
read-only shadow and Stage 9 owner-commanded cutover remain separately fenced.

## Repository boundaries

| Repository/surface | Responsibility |
| --- | --- |
| `dev-control-plane` | architecture, authority, immutable evidence, local adapter and model-free audits |
| `dcp-orchestrator` | managed application source under an exact reviewed pin |
| `dcp-wbc-integration-lab` | protected real Release Train and persistent deploy qualification |
| target repository | its CI, merge/deploy actor and immutable release proof |
| installed contour / SQLite | runtime state; never mutated by documentation or source-only authority |

Historical programs remain discoverable through
[Decisions](DECISIONS.md), [Roadmap](ROADMAP.md),
[DCP v1 target architecture](TARGET_ARCHITECTURE_V1.md) and their linked
immutable evidence. They do not supersede the current manifest.
