# DCP task-first native lifecycle v1 source-complete evidence

source_complete_status: `COMPLETE`

installation_status: `NOT AUTHORIZED / NOT PERFORMED`

date: 2026-08-18

## 1. Result and exact authority

The bounded architecture/source pass authorized by
[`DCP_TASK_FIRST_NATIVE_LIFECYCLE_V1_CONTRACT.md`](DCP_TASK_FIRST_NATIVE_LIFECYCLE_V1_CONTRACT.md)
is technically complete. This is source qualification only; it is neither an
installed-runtime qualification nor owner acceptance.

The authority merged first through ordinary dev-control-plane PR #239. Exact
head `d7d306b44bb6ad23595e7fd0fc8e2fc42b884dc6` passed exact-head review
`PRR_kwDOSUqHmc8AAAABJ9mX1A`, baseline workflow `32161917256`, and zero review
threads, then merged normally at
`5075235780b9c38d95faa9657a70265069d3a5c5`, tree
`e3ef51e141aa5f33c0782e8d20db2c2cc27f2f60`.

Implementation began from exact managed-source predecessor
`3fdc3976edc6bad591bca4cf4e254b479a905fb3` only after that authority merge.
The failing-first commit
`5980e51df3e9dc3758cfad61736f6c4d94131768` reproduced the archived-shell
startup rejection before the implementation existed.

## 2. Unified source result

Managed-source PR #71 exact head
`9055dd67f9e9e421e5ddaa6d0beca144a07abf0f` implements one provider-neutral
typed lifecycle evaluator and result value. Policy startup/restart,
review/recovery, SCM observation, FIFO admission/release observation, and
future-arbiter launch/restart consume the shared decision. Superseded
caller-specific archived-shell liveness exceptions are removed; narrower WBC
generation, review, head, and admission bindings remain separate strict
provider gates.

The central policy distinguishes durable workflow activity from registered
model activity. Queued actions own no process or model slot; exact
launching/running actions require their one exact runtime. Passive CI, review
decision, readmission, admission, release wait, Human Gate, incident, and
terminal-observation phases may retain an exact archived exited/terminated
native shell. Unexpected processes, missing processes for active actions,
crossed role/task/session/head/action identity, and more than three global
active model actions remain fail-closed.

The implementation includes an exhaustive phase by native-shell by
model-action by process matrix plus restart fixtures for worker completion, CI
wait, queued/running/completed review, multiple readmission generations,
waiting/claimed/admitted admission, release wait/terminal proof, Human Gate,
incident, global slot accounting, exact review/admission bindings, and
idempotent deduplication. Direct, foreign, and lab behavior remains unchanged
or fail-closed. DCP remains statically unable to merge or deploy `wb-core`; WBC
Actions remains its sole merge/release actor.

## 3. Schema-82 reproduction and inactive migration

A disposable copy of the stopped canonical schema-82 database reproduced the
exact contradiction for `wbc-canary-v1` / card `1` / session `wb-core-1` / PR
#987 / head `26044c696651ce5873748ec3f920d40e77c5686c`. The copy retained task revision
22, admission 32 waiting, readmission generation 1 admitted, 73 total and zero
active model actions, 46 reviews, integrity `ok`, and zero foreign-key errors.

Future migration
`0083_dcp_task_first_native_lifecycle_recovery_v1.sql` is immutable,
exact-preconditioned, transactional, and idempotent. Disposable-copy tests
prove it preserves all incidents and history, creates no task/session/action/
ReviewRun/admission/generation/release fact, advances only the exact task
revision, and re-arms only the already-bound admission continuation. Applying
it twice is a no-op after the first success; every identity or count drift
rolls back. Migration 0083 was not applied to the live database.

The canonical live database remained byte-identical at SHA-256
`9cc8d8805fe61a0b72406fd428640b191516084bfd0910f1165fb897afc7ab31`, with no
WAL or SHM sidecar. The app and daemon remained stopped and port 43231 had no
listener. The retained archived native shell was not modified.

## 4. Exact review, CI, and merge proof

PR #71 exact-head semantic/security review
`PRR_kwDOTydt6M8AAAABJ-fBzw` found no issue and remained anchored to
`9055dd67f9e9e421e5ddaa6d0beca144a07abf0f`. Review threads were empty. DCP CI
workflow `32171208324` passed both required jobs:

- `source` job `95822534551`: source/provenance/identity/absence gates, locked
  dependency setup, generated SQL/API/OpenAPI/TypeScript parity, backend tests
  and build, renderer typecheck, and applicable DCP lifecycle tests;
- `package` job `95822534816`: one ephemeral arm64 source package build and
  inspection, with no installation or installed-artifact mutation.

Independent model-free local proof on the exact head also passed the source
gate, SQL generation, API-spec parity, full serial Go suite, vet, build,
focused race suites for the shared callers/storage, and the disposable
schema-82 migration/restart tests. The connected CI supplied the locked
frontend dependencies and completed the renderer/type/API checks without
installing the resulting package on the governed host.

PR #71 then merged normally at
`84dbee2a701186628c1ad92950aa14639000fc0b`, exact tree
`9374ece6efccf87dcb8a7627c97722a16d063b77`. No managed-source pull request
remained open at source closure.

## 5. Preserved boundary and next gate

This pass did not change `upstream/dcp-orchestrator.lock` or any installed pin;
did not build or install a governed installation artifact; did not start or
stop the already stopped app/daemon; did not write or migrate live SQLite; did
not submit a DCP task or model action; and did not mutate WBC, PR #987, its
branch, labels, files, Release Train state, production, SSH, secrets, or
business data.

Exact source merge `84dbee2a701186628c1ad92950aa14639000fc0b`, tree
`9374ece6efccf87dcb8a7627c97722a16d063b77`, is build input only for a
separately owner-authorized pin/install Pass 2. Migration 0083 and the existing
`wbc-canary-v1` continuation remain inactive until that separate reviewed
gate. Technical `COMPLETE` does not mean owner acceptance.
