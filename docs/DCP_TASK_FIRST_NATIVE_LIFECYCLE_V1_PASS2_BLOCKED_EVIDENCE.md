# DCP task-first native lifecycle v1 Pass 2 blocked evidence

evidence_status: `BLOCKED`

date: 2026-08-19

blocker: `task_first_startup_admission_continuation_missing`

owner_acceptance: not requested or synthesized

## 1. Terminal result

The reviewed pin and governed deterministic install succeeded, and migration
0083 applied exactly once. The first controlled startup preserved every model
and identity count but did not advance the existing FIFO admission 32 from
`waiting`. The installed startup path is required to synchronously reconcile
and drain that exact model-free admission. No durable incident or next wake was
created, and PR #987 remained open without `release:ready`.

This is a new installed lifecycle/startup continuation defect before
`release:done`. The owner anti-cycle rule therefore requires technical
`BLOCKED`: the exact app/daemon were stopped at the zero-active-model boundary,
and this pass authored no managed-source correction.

## 2. Reviewed pin gates

Managed-source input remained exact:

- PR #71 head `9055dd67f9e9e421e5ddaa6d0beca144a07abf0f`;
- merge/source `84dbee2a701186628c1ad92950aa14639000fc0b`;
- tree `9374ece6efccf87dcb8a7627c97722a16d063b77`;
- source review `PRR_kwDOTydt6M8AAAABJ-fBzw`;
- source/package workflow `32171208324`.

Pin PR #241 exact head `518198afddf20f2c262c913bbe9641c6b83320f5`
passed review `PRR_kwDOSUqHmc8AAAABJ-x0Bw`, baseline run
`32174574253`, zero unresolved threads and ordinary merge at
`06b2a3051ac570172ba5454711a3649b9d17d6fb`.

Its first stopped `prepare` failed closed before build or install because the
integration guard retained the predecessor WBC helper name and an incorrect
path for the existing future-arbiter caller. Bounded integration-only PR #242
changed those two assertions without changing the lock or managed source.
Exact head `0a6c72762a36faf972750e96c478f746772ac9d0` passed corrected
exact-head review `PRR_kwDOSUqHmc8AAAABJ-0bHQ`, baseline run `32175016560`,
zero threads and ordinary merge at
`377544680a899ceb24144d323f67ddc6bb2276ef`.

After that merge, governed `prepare` verified the exact source/tree, official
ancestry, provenance digests, clean tree, common evaluator, all four callers,
WBC-specific provider/review/admission bindings and migration 0083.

## 3. Deterministic stopped install

Before install the canonical app, daemon, port 43231 and run file were absent;
SQLite had no sidecars, integrity was `ok`, schema was 82 and database SHA-256
was `9cc8d8805fe61a0b72406fd428640b191516084bfd0910f1165fb897afc7ab31`.
The predecessor receipt was
`8b4ba7f8696180fe4dc4ffdff3b096fc314690f893ee704e6c9554dee2934751`.

The governed install passed source/provenance/identity/absence gates, generated
SQL/API reproducibility, the complete Go suite, TypeScript typecheck, 15
frontend files / 358 tests, arm64 packaging and deep signature validation. It
created backup `i12-20260818T191429Z` and installed exact source/tree above.
The final receipt SHA-256 is
`685ae805a61f24f6c7e0628c788e2ad0cfce8d605b65143034296cb212fc757e`;
its daemon SHA-256 is
`4271fefa559e46536ef6e50233cac35f2ffc0939a044e90efa0a476a89d12d7a`
and asar SHA-256 remains
`8d7f0618181b2380de19a4f5c718f74b348743694ff3dccce829548475a045e9`.
Both app and daemon executables are native arm64 and the installed bundle
satisfies its designated requirement.

Stopped preflight passed after the governed read-only WBC initializer advanced
only the clean canonical local target to current main
`e2c8238881be4ffde73fc1ff60d686687306c801`. The live database remained
byte-identical through install.

## 4. Startup and exact blocker

One controlled exact app-owned startup reached ready/healthy on port 43231.
Migration `0083_dcp_task_first_native_lifecycle_recovery_v1.sql` then:

- advanced schema 82 to 83;
- inserted exactly one immutable recovery row
  `wbc-canary-v1-task-first-native-lifecycle` bound to authority
  `5075235780b9c38d95faa9657a70265069d3a5c5`;
- advanced only task revision 22 to 23;
- preserved task/card/session `wbc-canary-v1` / 1 / `wb-core-1`;
- preserved PR #987 head
  `26044c696651ce5873748ec3f920d40e77c5686c`, ReviewRun
  `18c54338-df31-4471-a344-4db6648ff4e3`, generation 1 and admission 32;
- created no task, session, action, ReviewRun, admission, generation or release
  row.

Post-start counts were exactly 27 tasks, 44 sessions, 73 model actions, zero
active model actions, 46 ReviewRuns, 32 admissions and one readmission
generation. The native shell remained exact `exited` / terminated with no
runtime launch ID.

Despite those exact preconditions, startup reconciliation left task state
`admission_waiting`, revision 23 and admission 32 `waiting`, with no lease,
admitted base, error or incident. The release phase and merge SHA remained
empty. Because startup owns the one synchronous FIFO drain and no timer or
unbounded poller may invent a retry, this missing continuation is a new
state-machine/lifecycle defect. A second start was not used to cycle it.

## 5. WBC and release preservation

Fresh provider evidence after the stop showed:

- WBC main `e2c8238881be4ffde73fc1ff60d686687306c801`;
- PR #987 open, non-draft, exact head `26044c696...`, `MERGEABLE` / `BEHIND`;
- labels exactly `scope:repo-only` and `task:standard`;
- required `baseline` run `32129475530` successful;
- no `release:ready`, `release:done`, merge commit or completion proof.

No executor/manual WBC branch, file, label, PR, merge or release mutation
occurred. Scheduled Release Train runs had no eligible handoff and did not
change PR #987. No new submit, card, session, branch, PR, initial worker,
reviewer, repair, arbiter or readmission generation was created.

## 6. Safe terminal boundary

The exact app and daemon were stopped through the governed app-owned quit path.
Final stopped facts are:

- zero exact app processes and zero exact daemon processes;
- port 43231 unoccupied and canonical run file absent;
- SQLite WAL/SHM absent, integrity `ok`, schema 83;
- final database SHA-256
  `561e6c624aeb5030b3d69dcba1ab2f39222c2b9dd2af16e58c488ad89f518f9b`;
- installed source/tree and receipt remain exact and the managed source is
  clean;
- model actions remain 73 total / zero active.

Live terminal-green UI, Actions-owned `release:done`, controlled restart and
terminal dedupe proof were not reached and are not claimed. Live-runtime and
production remain deferred. Platform approval count is zero; no curator-side
collaboration agent/fork/monitor was used.

Technical status is `BLOCKED`, not a Human Gate and not owner acceptance. A
future continuation requires separate owner authority and a new reviewed
managed-source correction; none is included in this pass.
