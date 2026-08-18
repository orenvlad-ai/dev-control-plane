# DCP wb-core repo-only readmission native-lifecycle blocked evidence

Status: `BLOCKED` (technical, not a Human Gate and not owner acceptance)

Date: 2026-08-18

## Scope and stop rule

This evidence closes only the bounded repo-only continuation of exact task/card/
session `wbc-canary-v1` / `1` / `wb-core-1` and PR #987. The owner separately
deferred every new `live-runtime` submit, production deploy/verify,
`release:production` and curator-bootstrap activation.

After one governed install and live continuation, the owner prohibited another
one-off managed-source predicate repair. A newly proven DCP state-machine defect
therefore ends this stage at a stopped, model-free safe boundary and requires a
separate full lifecycle redesign/test authority.

## Reviewed delivery and corrected immutable pin

- Managed-source PR #70 exact head
  `9cd8f0e33c07ec33c6789481c1574368f9d940a0` passed review
  `PRR_kwDOTydt6M8AAAABJ8sMcQ`, zero unresolved threads and workflow
  `32152293511`, then merged at source
  `3fdc3976edc6bad591bca4cf4e254b479a905fb3`.
- Pin PR #236 exact head `fcae00f7a7ae40b1f271b30e18d14746cb721ee0`
  passed corrected exact-head review and baseline `32153689496`, then merged at
  `d38f5382cd4cbb77a76592652dacf4017c5f12ba`. Governed prepare rejected its
  stale pre-merge tree `da8bf791...` before build, app stop or runtime mutation.
- Corrective pin PR #237 exact head
  `3b9df61900921961d96acd4496c8ba1875daece2` passed review
  `PRR_kwDOSUqHmc8AAAABJ8_20Q`, zero unresolved threads and baseline
  `32155526405`, then merged at
  `2935b79367a0bb6cece94bc8d422bda97f76088b`. It binds source `3fdc3976...`
  to its exact GitHub merge tree
  `5c945ae8c4ce0101463d1ddbdff54bd75d619de0`.

Two transient Git fetch receive failures occurred before checkout or build.
The already-reviewed PR head history and the official Git Data API's verified
payload/signature reproduced the exact signed merge object `3fdc3976...`; the
ordinary source verifier then proved commit, tree, ancestry and provenance.

## Installed and stopped proof

The governed install created backup `i12-20260818T154305Z` and installed:

- source `3fdc3976edc6bad591bca4cf4e254b479a905fb3`;
- tree `5c945ae8c4ce0101463d1ddbdff54bd75d619de0`;
- receipt SHA-256
  `8b4ba7f8696180fe4dc4ffdff3b096fc314690f893ee704e6c9554dee2934751`;
- daemon SHA-256
  `f01f72abeffe6fc5d7a21bff9af557ca5b8fd919f9f0eb71d38ea51e54eb8f60`;
- app-asar SHA-256
  `8d7f0618181b2380de19a4f5c718f74b348743694ff3dccce829548475a045e9`.

The read-only canonical WBC target was advanced only by the governed
`init-wb-core` fast-forward and is clean at
`HEAD == origin/main == 021b8c919949632cb67bc090189dbfa4e5e38417`.
Post-install preflight reported `wb_core_compatibility=qualified`.

One controlled start applied migration 0082. A second controlled start exposed
the exact startup error below and was stopped through the exact app-owner TERM
path. Final state has no canonical app/daemon process, no port 43231 listener
and no run file. SQLite SHA-256 is
`9cc8d8805fe61a0b72406fd428640b191516084bfd0910f1165fb897afc7ab31`,
integrity is `ok`, schema is 82, and history contains 73 model actions, 46
ReviewRuns and 32 admissions with zero active model actions.

## Preserved canary identity

- task/card/session/PR remain `wbc-canary-v1` / `1` / `wb-core-1` / #987;
- source branch remains `ao/wb-core-1/root`;
- exact PR head remains `26044c696651ce5873748ec3f920d40e77c5686c`;
- exact-head `baseline` run `32129475530` is successful;
- PR #987 is open, mergeable and `BEHIND`, with only `task:standard` and
  `scope:repo-only`; no `release:ready` or `release:done` exists;
- action sequence 71 is the sole succeeded initial worker; sequences 72 and 73
  are the two historical succeeded reviewers for their distinct exact heads;
- task revision 22 is `admission_waiting`, bound to ReviewRun
  `18c54338-df31-4471-a344-4db6648ff4e3` and admission sequence 32;
- admission 32 is exactly `waiting`, with no lease/error/refresh wake;
- generation 1 remains exactly `admitted` and bound to the same head, ReviewRun
  and admission; migration-0082 evidence preserves prior revision 21 and
  `waiting_identity_drift`;
- no new task, card, session, branch, PR, worker, reviewer, admission,
  generation, release label, WBC repository write or model call was created by
  this install/continuation.

## Exact blocker and root cause

The second controlled start logged, before any new action:

```text
reconcile DCP policy tasks on boot failed closed: DCP policy task wbc-canary-v1 native identity drifted
```

The durable native session is exactly project/session/card `wb-core` /
`wb-core-1` / `1`, branch/worktree/display name are exact, and its stock archive
state is `is_terminated=1`, `activity_state=exited`. The policy task is the
nonterminal `admission_waiting` revision 22.

`service/dcptask.exactPolicyNativeIdentity` rejects every terminated session
owned by a nonterminal policy task. Separately, `dcpterminalmerge` intentionally
accepts the same exact terminated/exited WBC shell after completed review and
during admission/readmission/release continuation. Migration 0082 re-armed the
admission correctly, but startup policy reconciliation fails earlier on this
contradictory cross-service lifecycle predicate. Admission remains waiting and
cannot reach the Actions-owned `release:done` terminal proof.

This is a DCP lifecycle design defect, not a GitHub, permission, Human Gate,
WBC Release Train or product-code blocker. Platform approval count remained 0.

## Required follow-on redesign/test

A separately owner-authorized DCP change must begin with the exact stopped
schema-82 live-copy regression above and replace duplicated shell predicates
with one typed native-session lifecycle policy shared by policy startup,
review recovery and terminal admission/release code. It must at minimum:

1. distinguish model/process activity from a preserved terminated native shell
   and from autonomous workflow activity;
2. define exact allowed session state for every policy phase, including review,
   readmission review, admission, Release Train wait and terminal observation;
3. keep a terminated/exited shell eligible only when project/card/session/
   branch/worktree/prompt/display identity is exact, no worker launch is active,
   and the phase needs no unaccounted model process;
4. fail closed for terminated sessions that would require an unproven worker,
   repair, reviewer or arbiter continuation;
5. test restarts at every fence, multiple readmission generations, admission
   claim/handoff/terminal observation, global three-slot accounting and zero
   duplicate task/card/session/PR/worker/reviewer/admission/release facts;
6. preserve DCP direct-merge ineligibility and WBC Actions as the only physical
   merge/release actor.

Only after reviewed authority, source, immutable repin and governed reinstall
may the same existing identity continue. No resubmit or replacement PR is an
acceptable recovery.
