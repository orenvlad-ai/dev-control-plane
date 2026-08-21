# WBC integration twin Stage 6 direct-model source-complete evidence

technical_status: COMPLETE at source; NOT INSTALLED

date: 2026-08-21

program_stage: 6 of 9 remains BLOCKED on a separate pin/install/migration/stopped-preflight gate

owner_acceptance: not requested or synthesized

## 1. Exact reviewed authority chain

The owner-selected removal of the DCP-v2 legacy second-authority bridge is
complete in reviewed managed source. It is not installed and grants no live
continuation.

| Package | Exact result |
| --- | --- |
| Architecture/authority | `dev-control-plane` PR #259; base `8dcaaa7829c339b5a0e4250e30dd61a50ec532e6`; head `81525ccfb3adb118b54d69bff39efaecd79c621a`; tree `3d9bc65b6129a3bc9db227b7247e7873efedd6ac`; baseline workflow `32485209932`; exact-head context-free review `4993514607`; zero unresolved threads; normal merge `3aa42b7afda620331d111ba24299e2917821e720`, tree `3d9bc65b6129a3bc9db227b7247e7873efedd6ac` |
| Managed source | `dcp-orchestrator` PR #77; base `d084ae3cf0cb3e5e32ebefa197031c24a2b6392d`; head `21f04ffbe107cb841308d5fb252136531b291d9d`; tree `b4db2b329accc9a93691bda7c306cc864b07ee56`; DCP CI workflow `32495591702`, `source` and `package` green; exact-head context-free review `4994657860`; zero unresolved threads; normal merge `e9eb18a99db71813ac8c4556a614d6a3ce4108aa`, tree `b4db2b329accc9a93691bda7c306cc864b07ee56` |

The source head remained unchanged after its final review and checks. No
findings-repair round was required after publication.

## 2. Direct authority result

The merged source makes DCP SQLite and the DCP daemon the only durable
authority for DCP-v2 Task, Revision, Command, Action, runtime identity, slot,
terminal receipt and deterministic successor Command. A typed provider-neutral
runner is stateless transport only.

The package:

- owns launch, effect and terminal-result fences directly in DCP-v2;
- applies the same direct lifecycle to Worker, Reviewer, findings repair and
  Arbiter Actions, with at most three exact active model slots;
- atomically completes a terminal Action and Command, releases its slot and
  creates the required successor Revision/Command;
- uses strict digest-bound runner inputs, strict bounded reviewer output and
  expected-old-head publication fences;
- projects `workflowActive`, `modelActive` and runtime truth only from DCP-v2
  durable facts plus the matching observed runtime;
- deactivates DCP-v2 policy-task, session and legacy model-action lifecycle
  reads, writes and reservations while preserving ordinary legacy workflows;
- adds forward-only migration 0086 and a hidden stopped, model-free adoption
  entrypoint for a later separately authorized installed-contour phase.

Future direct DCP-v2 tasks create zero legacy DCP policy-task, session or model
Action authority rows. Changes to historical legacy rows cannot alter an
adopted DCP-v2 lifecycle.

## 3. Frozen Worker adoption

The exact one-time adoption path accepts only the existing frozen identity:

- Task `dcp-v2-twin-canary-v1`;
- Revision `v2-13f81f321f99d1117dc931419e0bea3945ee35a5`;
- Command `v2-e028f779a18417e990911057f7db7c666f7487ca`;
- Action `v2-40f87d048813533daa1108b4316c09139acf0a8f`;
- runtime `78535564-a2bc-478c-80b0-207753f2152c`;
- terminal native Worker Action sequence `74`;
- local commit/tree `bebbf8f617f1a6fa0b9e91698fe710fe0a2bad2c` /
  `2fda4cae71976fd701bf3a9ccca4031f7afb630d`.

It validates the complete DCP, native, local Git and absent-provider fence,
then uses one SQLite transaction to finish the existing Action/Command,
release its slot, create the immutable successor Revision and enqueue one
model-free `publication.execute/v1` Command. It performs no submit, model call,
push, PR or other provider effect. Equal replay is inert; missing, crossed or
contradictory identity fails closed. The entrypoint was tested only against a
disposable copy and was not invoked against the installed contour.

## 4. Disposable snapshot and model-free proof

One exact disposable schema-85 snapshot was created through the
repository-approved read-only SQLite path. Its SHA-256 is
`6c0f0f41251bc60a6d01fdd3a00d4eca389c2d37a4f1e64ffece2fbf2c9ffdc9`
and its size is `2048000` bytes. The source database, WAL, SHM, installed
bundle and receipt were byte-identical before and after snapshot creation.
The copy passed schema-version, integrity and foreign-key checks. No private
path or live row is recorded here or committed.

Exact-head local proof passed:

- managed-source provenance, identity, security and absence gates;
- SQLC, OpenAPI and TypeScript generators with a clean tracked diff;
- complete serial backend tests, build and vet;
- uncached race suites for domain, SQLite store and DCP-v2 service;
- exact schema-85 migration and frozen-identity adoption tests;
- direct launch/result/restart/dedupe/asymmetric-runtime, slot, Reviewer,
  repair, Arbiter, publication, Admission, release and Result negative matrix;
- frontend typecheck and 16 exact renderer files, `440/440` tests;
- local arm64 package plus artifact-absence gate;
- committed root/frontend lockfiles unchanged.

GitHub workflow `32495591702` independently passed the exact source and package
jobs for head `21f04ffbe107cb841308d5fb252136531b291d9d`.

## 5. Preserved live and provider boundary

This architecture/source phase performed no installation, migration, app or
daemon stop/start/restart, live SQLite write, second submit, model call, target
push/PR/check/review, Admission, Release Train, merge, artifact, deploy or
Result effect. The installed source/tree remain
`d084ae3cf0cb3e5e32ebefa197031c24a2b6392d` /
`a6e3c3347bbbddd256e9edbfc541f115813249d2`; its receipt remains
`19550a9f02b14f13be8a80214529025fd6d4fe7dc8e5bd12c5eaa1a47dd54b0c`.
The existing stale DCP-v2 projection and local canary commit remain frozen.
WBC PR #987, production, Selectel and the protected Luchiki co-tenant were not
mutated.

## 6. Next exact boundary

Stage 6 remains technically `BLOCKED`, now at an explicit source-to-installed
gate rather than on source design. Any successor needs separate owner authority
for an exact merged-source pin, one governed install/migration and stopped
preflight against the same durable identity. This evidence grants no install,
migration, start, live continuation, provider action, Stage 7, WBC shadow,
production or cutover authority.
