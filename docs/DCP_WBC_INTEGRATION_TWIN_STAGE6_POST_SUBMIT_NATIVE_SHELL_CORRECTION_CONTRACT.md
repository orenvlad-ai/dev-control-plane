# DCP v2 integration twin Stage 6 post-submit native-shell correction contract

contract_revision: 2026-08-20.1
technical_status: ACTIVE
owner_acceptance: not requested or claimed

## 1. Scope and preserved incident

The owner-authorized Stage 6 submit crossed its durable boundary exactly once
for task `dcp-v2-twin-canary-v1` at
`2026-08-20 17:16:00.000286 +0000 UTC`. The canonical database contains only:

- Task `dcp-v2-twin-canary-v1`, state `worker_queued`, revision `1`;
- immutable Revision
  `v2-13f81f321f99d1117dc931419e0bea3945ee35a5`, sequence `1`, bound to lab
  main `375b9b2d0b4c2fce6f2c417850553f79e24a0d92`;
- leased Command `v2-e028f779a18417e990911057f7db7c666f7487ca`,
  `worker.execute/v1`, with effect fence
  `model:v2-40f87d048813533daa1108b4316c09139acf0a8f`; and
- the sole initial Worker Action
  `v2-40f87d048813533daa1108b4316c09139acf0a8f`, status `launching`, slot `1`,
  with no runtime id.

There is no native policy task, native twin session, predecessor model Action,
PR, check, review, Admission, release dispatch, merge, artifact, deployment,
Result, incident or external event for this Task. No model process crossed the
runtime boundary. The HTTP `500` is preserved evidence; it never authorizes a
second or replacement submit.

## 2. Exact defect adjudication

The submitted id is 21 bytes. The schema-84 predecessor table
`dcp_review_lab_policy_task` still admits task ids only between 1 and 16 bytes
and its target tuple check does not include the already compiled and activated
integration twin. Disposable-copy probes independently reproduce both exact
CHECK failures. The DCP v2 Task table, public submit validator and target
registry already admit only this fixed canary id and the exact twin tuple.

This is one non-compositional compatibility defect: migration 0084 activated
the v2 authority and adapter without extending the legacy table used solely as
the bounded native model runtime resource. It is not a model, provider,
credential, destination, issuer or architecture choice.

## 3. Single aggregate managed-source correction

One ordinary reviewed managed-source PR may correct only this defect from the
exact official-ancestry source merge/tree
`c1fc43d74cd517b7d73540f340058fa17b56ef15` /
`ff51ca2b1f6f9fa502b999f50a366a8e35035421`:

1. A forward migration `0085` may rebuild only
   `dcp_review_lab_policy_task`, preserving every predecessor row and child
   identity byte-for-byte. Existing task ids remain limited to 1..16 bytes.
   The sole longer exception is exact `dcp-v2-twin-canary-v1`, and it is valid
   only with target/profile/repository/policy tuple
   `dcp-wbc-integration-lab` / `live-runtime` /
   `orenvlad-ai/dcp-wbc-integration-lab` /
   `dcp.wbc-integration-twin/v2`. All historical target alternatives and
   immutable-transition guards remain unchanged.
2. Startup recovery may act only when the exact Task, Revision, leased Command
   and fenced launching Action above are present, their payload/base identities
   bind, no native twin identity exists and no model runtime crossed the
   boundary. It may reserve exactly one native card/session and predecessor
   runtime Action for that same Task, then launch the already fenced v2 Worker
   once. It creates no second v2 Task, Revision, Command or Action and consumes
   no repair allowance.
3. Any partial native identity, mismatched payload, different command/action
   state, runtime id, process, incident or external effect fails closed. General
   startup, dedupe, three-slot, repair and predecessor behavior cannot be
   weakened.

The correction must include failing-first regression coverage, migration
rollback and exact-copy preservation tests, exact tuple/long-id negative tests,
same-identity startup recovery, duplicate-startup inertia, and absence of a
second model launch.

## 4. Exact repin and recovery installation

After the managed-source PR passes exact-head semantic/security review,
connected source/package CI and normal merge, one separate reviewed/green DCP
pin/install-guard PR may select only that merge/tree. The immutable Stage 5
activation row remains bound to its original source/tree/receipt and is never
rewritten as a new activation.

The guard must provide one explicit stopped Stage 6 recovery-install path. It
must prove the exact incident identities and absence of an actual model process
before the governed stop; install the reviewed bundle once; apply migration
0085 while stopped; bind the new source/tree/install receipt in the external
DCP lock and receipt; and prove the same Task/Revision/Command/Action counts,
zero native twin identities and no listener before controlled continuation.
It must not reuse the Stage 5 zero-state assertion or report the correction as
a second Stage 5 activation.

If the source correction, pin, stopped migration or single recovery install
fails; if a new defect class appears; or if architecture, credential,
destination or protected-surface scope must change, Stage 6 stops technical
`BLOCKED`. There is no second source correction cycle or install retry.

## 5. Continuation and boundaries

After exact install proof, one controlled start may continue only the preserved
Task and its sole initial Worker. The original Stage 6 review, FIFO Admission,
DCP manifest, repository-owned Release Train, merge, artifact, persistent
Selectel deployment, verified Result and restart/dedupe gates remain unchanged.

No direct/manual lab merge or deploy, qualification issuer, WBC/PR987 mutation,
production, Luchiki/shared-host change, secret disclosure, cleanup, owner
acceptance or Stage 7 work is authorized. Stage 7 remains fenced until the
required independent curator verification of a merged Stage 6 terminal record.
