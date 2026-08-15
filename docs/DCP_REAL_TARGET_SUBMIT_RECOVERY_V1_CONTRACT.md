# DCP real-target submit recovery v1 contract

contract_status: owner-approved-pre-runtime

date: 2026-08-15

scope: one exact existing `price-arch-v1` identity and its already-consumed
worker/reviewer contour

## 1. Exact predecessor and preserved live identity

The installed predecessor is managed source
`9162d4c0eca9efd2a3d9fe1ad09d640c40738c47`, tree
`ec8e4c6d613e5e503a2582955b40bb8f104f76ce`, with receipt SHA-256
`5cb06d6edaeb70080999f531da76109936732a57bee8262d9c0cf0af1b7ce295`.
The only target is public `orenvlad-ai/wb-price-extension`, target
`wb-price-extension`, profile `repo-only`, default branch `main`, repository id
`1335072844`, owner id `237411244` and required check `baseline`.

Exactly one canonical submit was made for task `price-arch-v1`. It created and
must preserve these identities:

- native card/session `wb-price-extension-1`, card 1;
- worktree
  `data/worktrees/wb-price-extension/wb-price-extension-1` and branch
  `ao/wb-price-extension-1/root`;
- initial-worker action sequence 59,
  `dcp-model-price-arch-v1-worker-1`, launch
  `b815e3d2-0dc2-48fe-b9bd-c2bb0b426bcd`;
- policy payload digest
  `efe6a81cfff28be89cc327bdc9e2380ca585fcc6b03064c0290b6aaf4c7b59fe`.

The adapter returned post-submit error
`policy submit immutable payload identity drifted`; no second submit is permitted.
Read-only proof before correction found SQLite integrity `ok`, one
target policy task/session/action and no duplicate identity. The initial worker
did run once, succeeded, consumed 27,373 tokens, created exact commit/head
`afc748eba5ff05c0dc24d3002c690ec9f44984fb`, and opened ready PR #1 from the
same branch to exact main `9522cfb633f9b3f5a87298f4f1dcce902bb7ebfd`.
The worktree is clean, the provider reports the same head, and required
`baseline` workflow `31896051686`, job `95039422914`, succeeded.

One context-free reviewer also already ran once for that exact session, PR and
head. ReviewRun `b0acfb9e-600c-4816-bb2f-02a67817ea05`, review
`f754d155-faad-4a6b-8a03-53a3b93b11b8`, batch
`6b097406-b9bc-42e5-90fb-2b82180e9458` completed approved with empty findings
and consumed 20,512 tokens. It must not run again. There is no admission or
merge. The policy task is passively `ci_waiting`, revision 4; the native
session is retained idle/exited with bare shell panes and no model descendant.

## 2. Proven root causes

The complete first failure is a response-projection defect, not payload drift.
The server durably accepted the exact 510-byte prompt and canonical payload.
The native session prompt is only the same prompt with the deterministic
`DCP repo-only task price-arch-v1: ` prefix. The hidden `dcp submit` CLI decodes
the server response through a reduced task struct that omits `target`,
`profile` and `repository`; JSON output therefore drops them. The adapter's
unchanged equality validator compares the absent fields with the submitted
tuple and correctly fails closed after creation.

Two downstream defects became visible before recovery:

1. reviewer policy classification is keyed to project
   `dcp-review-lab` before consulting the durable policy gate. The exact
   `repo-only` reviewer therefore completed through the stock path without a
   corresponding global `dcp_model_action` row;
2. the terminal merger's independent provider validator still requests
   unsupported `gh repo view --json databaseId`, although the task/runtime
   provider path already uses typed REST metadata.

These are bounded seams of the already-authorized target, review and merger
architecture. They do not authorize a replacement identity, a second model
call or weakened validation.

## 3. Authorized source correction

One managed-source change may do only the following:

1. preserve exact immutable `target`, `profile` and `repository` fields in the
   hidden CLI submit response and keep the adapter's byte-for-byte equality
   checks unchanged;
2. classify a review as policy-governed when the existing durable policy gate
   proves the exact session, for both allowlisted policy targets, while keeping
   foreign/ordinary/manual reviews outside this path;
3. replace only the terminal merger's unsupported repository projection with
   typed read-only REST metadata and retain exact public full-name, `main`,
   numeric repository-id and owner-id equality checks;
4. add one immutable exact-state, model-free forward migration for the identity
   in section 1.

Prompt canonicalization, the 512-byte UTF-8 ceiling, payload digesting, equal
replay identity, conflicting replay rejection, server-side immutable fields,
local Git/worktree checks, three-slot global action limit, exact-head review,
named check, provider mergeability, FIFO admission lease and guarded terminal
merge remain unchanged. Missing, null, malformed, foreign, stale or conflicting
facts fail closed.

## 4. One-way recovery

The migration must first prove every immutable predecessor fact: exact task,
target/profile/repository/policy/payload digest, session/card/worktree/branch,
worker sequence/id/launch/status, PR number/url/base/head, successful current
head check, exact completed approved ReviewRun/review/batch with empty findings,
revision 4, zero admission, zero target duplicate and zero claimed/running model
action row. The executor separately proves no process descendant before install.
Any mismatch makes the migration a no-op or fail closed.

On that conjunction only, it may:

- append exactly one succeeded reviewer action accounting row at next global
  sequence 60, identity `dcp-model-price-arch-v1-review-1`, bound to the exact
  existing ReviewRun/head and the truthful 20,512-token completed call;
- bind the existing task to PR #1 and the exact approved ReviewRun/head;
- advance the same task exactly once to `admission_waiting`, revision 5, so the
  existing admission reconciliation must perform every later gate;
- append one immutable audit record containing the predecessor and recovered
  identities.

It may not invoke submit, launch worker/reviewer/arbiter, create a replacement
task/card/session/branch/PR, rewrite the worker or ReviewRun, invent token
usage, insert an admission directly, claim a merge lease or merge. The existing
terminal merger alone must revalidate current provider/check/review facts,
create the durable FIFO admission, claim its lease and perform the ordinary
merge. Findings may use only the pre-existing one-repair contour; the already
approved empty-findings result requires none. A genuine typed Human Gate stops
with its exact owner question.

## 5. Regression and security gates

Model-free source coverage must reproduce the exact 510-byte payload and prove
that CLI JSON preserves all immutable response fields, equal replay remains
idempotent and a 513-byte prompt still fails. Reviewer tests must prove the
exact repo-only policy session uses the global policy action gate while a
foreign ordinary session does not. Terminal-merger tests must accept only the
exact REST identity and reject private, renamed, wrong-branch, wrong repository
id, wrong owner id, missing/null/wrong-type fields, malformed JSON and command
failure.

An exact migration fixture must prove one recovery from the section 1 state,
zero recovery on every identity mismatch, idempotence on replay, action count
`1 worker + 1 reviewer`, unchanged model-call artifacts, one task/card/session,
and no admission/merge side effect inside the migration. Generated SQL/OpenAPI
parity, serial Go tests/build/vet, source/package/artifact gates, I9/I12 audits
and clean-tree checks remain required.

The change adds no daemon, database, service, registry, queue, timer, poller,
watcher, heartbeat, retry policy, credential, target, model authority, manual
review/merge affordance or deployment path. `wb-core`, production, servers,
secrets, Telegram, foreign repositories and historical PR #24 are out of scope.

## 6. Sequential delivery and terminal proof

Delivery is strictly ordered:

1. merge this reviewed contract with green baseline;
2. merge one ordinary managed-source PR after fresh exact-head
   semantic/security review and successful source/package CI;
3. merge one separate reviewed immutable pin/install-guard PR;
4. prove no active/unknown model action or descendant, gracefully stop the
   exact canonical app, then run deterministic
   `prepare -> build -> install -> preflight` with backup and receipt;
5. prove the installed exact-state recovery model-free, then start only the
   canonical daemon so its existing reconciliation can continue the same task;
6. after terminal outcome, perform one controlled restart and prove stable
   identities, zero duplicate activity and no active process descendant;
7. stop DCP preflight-ready and merge one reviewed terminal evidence PR from a
   clean fast-forwarded control-plane `main`.

Technical completion requires the original `price-arch-v1` / card 1 to be
terminal `MERGED`, with exact worker/reviewer/token accounting, one approved
review, one admission and one ordinary provider merge. Otherwise evidence must
record one exact `BLOCKED` or Human Gate state without replacement activity.
