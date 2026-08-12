# I13 Stage 2 exact-incident successor arbiter contract

contract_status: owner-approved-pre-runtime
contract_version: dcp-i13-stage2-arbiter-successor-v1
contract_revision: 1
recorded_at: 2026-08-12
dev_control_plane_baseline: ee15bb4710876666866715278b16607247da35df
managed_source_baseline: 182f7a1a95d4e1705de63355e65599b9d79f2c12
incident_generation: 1
successor_attempt_generation: 2
successor_attempt_identity_digest: 3c62ea80b56ef94165519d4f01e4c449c320bff22d16b902dd68d4a1a355ea7d

This is the reviewed stop required by the owner's 2026-08-12 authorization
after the truthful terminal result in
[I13 Stage 2 terminal BLOCKED evidence](I13_STAGE2_BLOCKED_EVIDENCE.md). It
authorizes one successor arbiter attempt for the same persisted incident and
no broader Stage 2 replay. It becomes implementation authority only after this
document and its authoritative references are green, merged and present in
the clean canonical `dev-control-plane` checkout. Until the managed source,
immutable pin and deterministic installation also merge and pass preflight,
it authorizes no runtime mutation or model call.

The original contract remains the authority for the incident, scope, evidence
envelope, allowed verdicts, recovery path and all non-authority not explicitly
overridden here. This contract does not edit, reinterpret or accept the first
rejected result.

## 1. Frozen starting state and authority

The only eligible incident and first model attempt are exact:

- incident
  `dcp-global-release-2694dbd8b3d4897063603d7a8607ca516aa2f8e05c5a3c39cf56d8e3f18c3c60`,
  incident generation `1`, identity digest
  `2694dbd8b3d4897063603d7a8607ca516aa2f8e05c5a3c39cf56d8e3f18c3c60`,
  input digest
  `f618fa8a46715acce0958b592384f0d42c071562e36988163e2b96f2c157fc49`
  and source-packet digest
  `fab52d627d14a21ea7ab2a7fdadb4d6f53478d5cdc496858ca74c37e1dfda057`;
- admission
  `dcp-admission-ecb500ad-f9f0-443b-9d73-2c8a6350ce34`, sequence `4`, retained
  lease
  `dcp-incident-dcp-admission-ecb500ad-f9f0-443b-9d73-2c8a6350ce34`;
- native task/card/session `i13-arbiter-b` / `dcp-review-lab-12`, repository
  `orenvlad-ai/dcp-review-lab`, existing branch
  `ao/dcp-review-lab-12/root`, PR #9 and rejected head
  `d4fcb68051ae113ed497d02151a759800ee85633` against exact current base
  `b34b31b5443890e69128db2862726950a6bbac0d`;
- first actual arbiter inference: `gpt-5.6-sol` / `xhigh`, Codex session
  `019ff23c-7cbf-7ee1-9567-30c6693f95fe`, `11,583` tokens, result artifact
  SHA-256
  `d121d012a0b3042f02886fdc0c2aca806f34be64f9e5a3d15e1edf444ff3ae2d`;
- first result: `assign_recovery`, the exact allowed owner and path,
  `maxWorkerCalls=1`, invalid model-owned `maxFreshReviews=0`, trusted error
  `ARBITER_RESULT_REJECTED`, durable row `failed/submit_failed`, one model call,
  no decision, wake, recovery review or merge.

The first row, result/input/schema artifacts, their byte digests, Codex
session, token count and counters are immutable audit evidence. The successor
must neither update them nor submit the old result through a new acceptance
path. The two earlier strict-config/response-schema pre-inference rejections
and migrations 0053/0054 also remain immutable and are not counted as model
calls.

No other incident, admission, card, task, worker, PR, repository, head or
artifact is eligible. Any drift before launch leaves the incident frozen and
records no successor model call.

## 2. Exact successor attempt identity and storage

Managed source may add one additive migration
`0055_dcp_arbiter_successor_attempt.sql`. It creates one exact subordinate
successor-attempt row in the existing `ao.db`; it does not alter migrations
0050-0054 or create a general attempt, retry, incident, queue or registry
surface. The original `dcp_review_lab_arbiter_v1` row remains byte-for-byte
unchanged by the successor lifecycle.

The successor row is unique for the incident and has:

- incident generation `1` and attempt generation exactly `2`;
- attempt identity digest
  `3c62ea80b56ef94165519d4f01e4c449c320bff22d16b902dd68d4a1a355ea7d`;
- attempt id `dcp-arbiter-successor-` followed by that full digest;
- model `gpt-5.6-sol`, reasoning `xhigh`, token budget `16384` and model-call
  count constrained to `0` or `1`;
- deterministic policy maxima `policy_max_worker_calls=1` and
  `policy_max_fresh_reviews=1`, fixed before launch;
- a distinct runtime handle, launch id, sealed artifact directory, input,
  schema and result paths that cannot overwrite or alias the original attempt.

The attempt digest is SHA-256 over this ordered NUL-delimited tuple:

```text
successor-attempt schema, incident id, incident generation, attempt generation,
incident identity digest, incident input digest, admission id, session id,
PR URL, rejected head, current base, first Codex session,
first result-artifact digest, first token count, successor contract version
```

Migration eligibility is a single exact `INSERT ... SELECT` over the frozen
failed row and the known immutable constants above. Zero or more than one
eligible row is a stop. Rollback drops only the new empty/unstarted successor
table; after the successor call fence or any accepted decision it must fail
closed rather than erase audit history.

Exactly two actual arbiter inference attempts may exist for this incident:
the immutable rejected attempt and this successor. At most one decision may be
accepted across them, and only the successor row can hold it.

## 3. Minimal successor input

The persisted successor input schema is
`dcp.review-lab.global-release-arbiter-successor-input/v1`, canonical UTF-8
JSON at most 16,384 bytes. It contains the same bounded authoritative incident
facts and evidence digests already permitted by the v1 frozen input, plus only
the successor attempt id/generation/identity digest and the deterministic
allowed verdict/owner/path/safe-stop values. Immediately before the call fence,
the daemon independently recomputes the original incident/input/source and all
scope/history/diff/check/review/queue/mechanical digests, current provider
facts and the successor input digest.

The model input excludes the first result artifact, its summary or reasoning,
all executor/reviewer transcripts, unrelated tasks/repositories, credentials,
environment secrets, daemon connection, GitHub token, mutation tools, worker
worktree and user Codex configuration. The first result/session/token facts are
trusted launch-eligibility evidence only and are not model context.

The successor is stateless and ephemeral. It uses the same strict
`codex exec --ignore-user-config --ephemeral --strict-config`, read-only,
network-disabled, tool-disabled isolation as the original arbiter. It can only
select the exact recovery owner/path or one existing safe-stop code.

## 4. One successor call and hard budget

The owner authorizes exactly one successor model call:

- model `gpt-5.6-sol`;
- reasoning `xhigh`;
- hard weighted rollout budget `16,384` tokens, persisted before process
  creation and enforced with the already qualified structured
  `features.rollout_budget` configuration;
- maximum successor calls `1`; no retry, replacement, resume, fallback, model
  switch, downgrade, third attempt or new incident generation.

The successor row enters `running` and `model_call_count=1` in one
compare-and-set before launch. Launch, network, provider, budget, missing
result, malformed result, submit or unknown failures are terminal. No prior
pre-inference exception is reusable and no new re-arm exists. Restart may
leave an exact live descendant alone or consume one exact completed artifact
model-free, but never creates another call.

The Stage 2 cumulative live ceilings become:

| Action | Cumulative ceiling |
| --- | ---: |
| Initial workers | 2 |
| Initial exact-head reviewers | 2 |
| Arbiter inference attempts | 2 |
| Selected same-worker conflict repair | 1 |
| Fresh reviewer for the repaired head | 1 |
| Total model calls | 8 |
| Successor arbiter tokens | 16,384 hard maximum |

Five model calls and 120,514 tokens are already consumed. Only the successor
arbiter and, after an accepted recovery decision, one same-worker wake and one
fresh reviewer remain available. A `safe_stop` or any successor failure ends
truthfully without borrowing either downstream call.

## 5. Model decision and deterministic policy

The successor output schema is
`dcp.review-lab.global-release-arbiter-successor-decision/v1`. Every incident,
attempt, input, admission, task/card/session, repository, PR, rejected-head and
current-base identity is a JSON-Schema constant. The model-owned fields are
only:

- `verdict`: `assign_recovery` or `safe_stop`;
- `recoveryOwnerSessionId`: the exact card-12 session or the empty sentinel;
- `recoveryPath`: `same_worker_conflict_repair` or the empty sentinel;
- `safeStopCode`: the empty sentinel or one existing bounded safe-stop code;
- one bounded summary and one to eight already-present evidence digests.

`maxWorkerCalls` and `maxFreshReviews` are removed from both the model schema
and model artifact. They are trusted policy, not a semantic choice. After
exact schema and cross-field validation, the daemon deterministically maps an
accepted `assign_recovery` to the pre-persisted policy `1/1`, or a valid
`safe_stop` to `0/0`. It validates those policy values again in the decision
transaction and before each downstream action. The model cannot reduce,
increase or otherwise control either limit.

An accepted decision is bound to the exact incident id/generation/identity and
input digest plus the exact successor attempt id/generation/identity and
successor input digest. Missing, malformed, foreign, duplicate, late, stale or
old-v1 output is inert. The daemon accepts at most one successor decision
digest and consumes at most one selected path.

The original arbiter non-authority remains unchanged. The successor cannot
edit code, widen scope, change admission priority, call GitHub, apply a label,
merge, create HumanGate, accept risk or record owner acceptance.

## 6. Recovery and terminal result

For `assign_recovery`, the daemon first persists the accepted successor
decision without waking a worker. The controlled qualification restart at
this durable `decided` boundary must preserve both attempts, exactly one
accepted decision and zero wakes; startup reconciliation may then consume the
single policy-bound wake.

Only the original `dcp-review-lab-12` worker may wake, in its existing
worktree/branch/PR. It may create one direct repaired head based on exact
current `origin/main`, limited to the original two-line canary intent. It may
push only the same branch with the existing force-with-lease fence. No new
task, card, worktree, branch, PR, incident or scope is permitted.

Exactly one fresh, stateless, context-free reviewer may inspect the new exact
head. Only its approved/no-findings structured verdict, the exact successful
named check and fresh provider facts may transactionally rebind admission
sequence 4 and proceed through the existing trusted terminal merge of PR #9.
The daemon, not the model, applies the `1/1` policy and one selected recovery
action.

A safe stop, worker/reviewer/check failure, malformed handoff, unexpected head,
second ambiguity or merge uncertainty is a truthful terminal `BLOCKED`. It
cannot launch another model or simulate success.

## 7. Restart, duplicate and evidence proof

Qualification must perform a controlled restart at the accepted-decision
boundary before the recovery wake, and another after the terminal outcome.
Evidence must prove:

- the original failed row, pre-inference audit rows and original
  input/schema/result artifacts and digests are unchanged;
- exactly two arbiter inference attempts total, one successor call fence and
  at most one accepted successor decision;
- the same incident/admission/card/task/session/worktree/branch/PR identity and
  an exact attempt-generation-2 decision/input binding;
- zero duplicate arbiter calls/results, worker wakes, review runs, admission
  claims or terminal merges before and after both restarts;
- at most one recovery wake, one new exact head, one fresh reviewer and one
  PR #9 merge, or truthful zeroes after safe stop/failure;
- durable waiting and both restart intervals use no heartbeat, timer, polling
  process, model-status call or token.

Managed-source implementation, immutable pin/integration and terminal evidence
use separate ready PRs, ordinary protected review, green CI and safe merge. The
clean canonical checkout is fast-forwarded after each merge. Only the exact
merged fork pin may be built and deterministically installed before the one
successor call.

## 8. Explicit non-authority

This correction adds no production target, `wb-core`, real repository,
replacement card/PR/incident, second daemon/database/registry, task or queue
service, watcher, heartbeat, timer, polling/model loop, general retry/recovery,
Release Train, deploy, hosted surface, Telegram, labels, HumanGate, updater,
telemetry or owner-acceptance synthesis. It never reads or operates installed
Agent Orchestrator or `~/.ao`. Technical completion is not owner acceptance;
only the owner may write `Задача принята`.
