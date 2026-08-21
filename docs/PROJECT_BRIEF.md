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
`BLOCKED before model launch` on the sole durable identity
`dcp-v2-twin-canary-v1`; a second submit or replacement Task is forbidden.
The recovery install succeeded, then exposed a live-runtime/synthetic prompt
identity mismatch and a false `modelActive` projection without a real runtime.

The next separately launched source-only phase must use a disposable exact
schema-85 snapshot and one managed-source worktree to close the entire DCP-v2
to legacy-native seam as one aggregate package. It may not install per defect.
If one later aggregate installation still exposes a same-class pre-model/native
identity predicate, stop patching and simplify or remove the legacy
second-authority bridge.

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
