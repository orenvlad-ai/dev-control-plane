# Current operating contract

operating_contract_revision: 2026-08-15.6

This is the compact operational start for DCP work. Architecture and scope
remain authoritative in [Project brief](PROJECT_BRIEF.md),
[Roadmap](ROADMAP.md), and [Decisions](DECISIONS.md). Root `AGENTS.md` plus this
contract define the starting flow when operational instructions conflict.

The owner-approved current future-card rule is
[DCP Lab happy-path v1](DCP_LAB_HAPPY_PATH_V1_CONTRACT.md). It replaces the
qualification-only card/cohort and globally consumed reviewer ceilings for new
tasks: exact policy submissions are durable and idempotent, at most three DCP
model actions are active globally, every exact head has one fresh review, each
task has at most one findings repair cycle, and all policy-eligible tasks share
one durable FIFO merge lease. Historical cards 1-12 and the complete I12/I13
rows/evidence stay immutable. The installed bundle is exact source
`a96f4ba9410f088401cee8700e092f1f674ad872`, tree
`bedd8adf2508a8f8fdb692354f146d4353535c4d`. It preserves its predecessor's
exact passive creation-base repair; together with the stock SCM catch-up event
that repair completed card 13 with zero new model
actions, then controlled restart proved terminal dedupe. PR #10 merged once at
`1b3f9fb266370326bbb35283fb51fb5226502c42`; the application is stopped after
proof.

The active staged development authority is
[DCP Lab phase UI and ordinary-card arbiter v1](DCP_LAB_PHASE_UI_ARBITER_V1_CONTRACT.md).
Its strict order is: shared
forward-only UI projection and install; three-task happy-path qualification;
bounded ordinary-card arbiter source and install; then three sandbox
qualification scenarios. Only exact public `dcp-review-lab` future policy
tasks are eligible. Every phase retains the one daemon/SQLite authority,
three-active-model-action ceiling, passive model-free waits, ordinary review/
CI/FIFO merge gates and immutable historical cards 1-12.

Phase 1 managed-source [PR #43](https://github.com/orenvlad-ai/dcp-orchestrator/pull/43)
passed exact-head review and final `source`/`package`, then merged at exact
source `01d8905d98ddc7e1ace42c1e6440a4cb6a652e22`, tree
`3b4a01d924ea582bdc555f9b744ce502ed87ef0b`. Pin/install-guard PR #175 merged
at `619431abca3d8a3d7fa75bc949f82b6750f18876`, tree
`d0a6e3b306c4d1521eae763a6393ebcb0a14b93b`. Deterministic stopped install at
`2026-08-14T20:19:32Z` produced receipt SHA-256
`a3f73b2a5c24abe95dc7891ad5768ce33ceb28b6ae79292bc0313546b1edc10f`
and backup `i12-20260814T201931Z`; model-free preflight passed, the application
is stopped and all ten historical policy model actions remain terminal with
zero active. Phase 2 submissions are now eligible only through the canonical
typed entrypoint. Exact proof is in
[Phase 1 install evidence](DCP_LAB_PHASE_UI_V1_INSTALL_EVIDENCE.md).

Phase 2 submitted three exact future tasks once. Cards 18 and 19 each used one
worker and one fresh reviewer and merged through the trusted daemon. Card 20
used one worker and opened exact PR #17 with a successful named check, but a
stock structural PR row arrived before provider enrichment and the old policy
gate recorded a false `provider_identity_drift` incident. No reviewer or retry
ran for that card. Managed-source
[PR #44](https://github.com/orenvlad-ai/dcp-orchestrator/pull/44) fixes only that
ordering boundary and immutably audits/re-arms the exact card-20 incident by
migration 0068. It passed exact-head review plus `source` and `package` and
merged at `7147171e9e2e7fcfcb14cbd1dc25e215d7c86312`, tree
`3be7ed1acd064faca53702fc7ddcead9a796a10b`. It was deterministically installed
at `2026-08-14T21:04:16Z` with backup `i12-20260814T210415Z` and receipt
`0c8bffd3f019c2c2844b0f5ba60dd3c953dec6285f1dccb343d276338543c2b9`.
The first controlled start applied migration 0068 once, preserved the original
incident audit and queued exactly one card-20 reviewer, but launched no ReviewRun
or model: startup reconciliation stopped on stock-archived merged card 13 before
the shared drain. Managed-source
[PR #45](https://github.com/orenvlad-ai/dcp-orchestrator/pull/45) permits an
exact terminated/exited shell only for an already-terminal policy task and
retains full native metadata checks. It passed exact-head review and both checks,
then merged at `a96f4ba9410f088401cee8700e092f1f674ad872`, tree
`bedd8adf2508a8f8fdb692354f146d4353535c4d`. Pin/install-guard PR #178 merged
at `1c8f9b0c282869b1aedf665d43cebbeaab1847da`, tree
`7afdef1a457735ee5234542f899dc679dc8988f6`. Deterministic stopped install at
`2026-08-14T21:26:22Z` produced receipt SHA-256
`865956b3611ea6d39aa2629a247c5c2bb007f4fd38af01bd2c08becdb04a930b`.
The exact start drained the existing card-20 reviewer once; it approved head
`6211c80...` and the trusted daemon merged PR #17 at `b1b58cb...`. Cards
18-20 now retain exactly three workers, three reviewers, three approved
ReviewRuns, three FIFO admissions and three merges. Controlled restart
preserved all identities and zero active actions. The bundle is stopped and
Phase 3 source work is eligible. Exact proof is in
[Phase 2 triple evidence](DCP_LAB_PHASE2_TRIPLE_QUALIFICATION_EVIDENCE.md).

Phase 3 managed-source
[PR #46](https://github.com/orenvlad-ai/dcp-orchestrator/pull/46) binds only
ordinary future-card typed incidents to the existing daemon/SQLite authority
and global three-slot model-action queue. One immutable generation receives a
fresh context-free `gpt-5.6-sol` / `xhigh` call under the hard 16,384-token
ceiling, then may persist deterministic order/hold, one bounded same-card
successor repair or a fail-closed HumanGate question. Repair still requires a
fresh exact-head reviewer and the unchanged FIFO admission/merge gates.
Exact head `4b77a69c11c68930dbeadc5933c7ba1e2145dd68` passed semantic/security
review and workflow `31846494241` (`source` and `package` successful), then
merged at source `3bc21e11060d07b7f5339365b8df58f82b9c5439`, tree
`0af68800b32c4ec195722b72cd8cd39f8aafbac3`. It was deterministically installed
at `2026-08-14T22:41:11Z` with backup `i12-20260814T224111Z` and receipt SHA-256
`82f30938095551643c8aecf0c5953121348e91f97078867e99d599973f78adfe`.
Migration 0069 applied once and the first two-task Scenario-A contour produced
PRs #18/#19, two workers, two fresh reviewers, one trusted merge and one exact
`merge_conflict_or_ambiguity` incident. No arbiter row or call opened. A
model-free live-SQLite-copy reproduction proved the root cause: the future
arbiter reused the ordinary candidate helper restricted to `admission_waiting`
after the task/admission had atomically entered `incident`. Managed-source
[PR #47](https://github.com/orenvlad-ai/dcp-orchestrator/pull/47) keeps ordinary
admission restricted, gives derivation and pre-launch revalidation an exact
incident-only helper and adds the negative/positive regression. It passed
workflow `31848548624` and semantic/security review, then merged at source
`3f31b66cbf93cc3067ca64cc1908b077727dad0a`, tree
`42ec79b53cc400e9fa8a60b126b2febb61515d4f`. It was deterministically installed
at `2026-08-14T23:11:46Z` with backup `i12-20260814T231146Z` and receipt SHA-256
`2b484047b688ffd2ce585d1e3c0491c688c048a0f0fc85aaa93e8bd1d6f761bd`.
Generation 1 opened exactly for `arb-a-second`, consumed one logical call fence
and was rejected by the provider with HTTP 400 because `uniqueItems` is not
permitted in response schema. No inference, result or model tokens occurred;
the incident/action are immutable `failed/launch_failed`. Managed-source
[PR #48](https://github.com/orenvlad-ai/dcp-orchestrator/pull/48) replaces
unsupported `$schema`/`const`/`uniqueItems` with enum-backed exact identities,
adds a model-free compatibility fence and migration 0070 for one exact additive
generation 2 while preserving generation 1. Exact head `a2d49d99...` passed
workflow `31850383431` and semantic/security review, then merged at source
`ae2be4995068c2aa532860b7ad1a798ea13752d2`, tree
`205293679414045bdf1880e0cc435c87ac456e42`. It was deterministically installed
at `2026-08-14T23:39:55Z` with backup `i12-20260814T233954Z` and receipt SHA-256
`9d2432ce108addd48fd5d30f5061bd644676cc2db7a9df0b150c12ae08f3a267`.
Generation 2 produced the byte-exact 1,158-byte `successor_repair` result
`b8d34711413d429d2ae75eccd078c58a6ece778a4b0ad7d606361ce30a51d36d`
in Codex session `01a002a6-56e1-7781-917b-ff5640953091` after 10,569 tokens.
The daemon had already persisted `failed/launch_failed`: the launcher compared
the durable incident handle with tmux's deterministic shortened physical
handle `dcp-future-arbiter-9e94bbd542baf-631f35f9`, even though process creation
had succeeded. Managed-source
[PR #49](https://github.com/orenvlad-ai/dcp-orchestrator/pull/49) adds an opaque
runtime-handle resolver and migration 0071, which preserves the failure/action
and exact artifact/session/token facts before one model-free validation of only
that unchanged result. It creates no generation or arbiter call and queues only
the existing bounded repair. Exact head `ffdec2bd...` passed workflow
`31852087643` and semantic/security review, then merged at source
`76b272697091bfb684b079bbea9888c882545a46`, tree
`baaa4de1d20d4d30fbf5e4a6872e8999c4c60b1d`. It is build/test input until this
separate pin merge, deterministic stopped install and model-free preflight.

The completed live identity is policy task `chat-probe-b`, native session/card
`dcp-review-lab-13` / 13, state `merged` revision 10 and repair count 0. Its
unchanged head `e467d1a...`, successful named check and sole approved ReviewRun
`152048c0-6720-4397-9430-df975a453807` feed the same admission sequence 5,
which succeeded with one lease and merge `1b3f9fb...`. Exactly one initial
worker and one reviewer remain succeeded; no model action is active and the
repair added zero model calls.

I9 records the separately approved future
[DCP v1 target architecture](TARGET_ARCHITECTURE_V1.md). That document is
design-only outside the exact happy-path v1 slice and is not otherwise part of
the current operating flow. The I11 foundation, bounded I12 reviewer and I13
slices below are qualification history for cards 1-12; their task-count and
model-call ceilings do not constrain a future task governed by the new policy.
I11 activates
only durable model-free submission, read, events, restart recovery and display
of a synthetic SUBMITTED task. I12 activates one stock, exact-head, read-only
reviewer after an eligible worker becomes safely idle, with model-free
single-flight and restart reconciliation. One separately exact
`dcp-review-lab` profile may create and terminally merge one synthetic PR after
the bounded review and provider gates below. I13 adds only the exact Stage 1
admission line and Stage 2 history below. Happy-path v1 activates only its exact
synthetic task/action/review/admission path in the currently installed bundle.
The new staged contract may activate only its bounded event-driven future-card
incident arbiter after the separate Phase 3 source/pin/install gates; it does
not activate production admission/release, general recovery, a general model
loop, another target or a real execution surface.

## Historical owner-approved I13 staged block

On 2026-08-11 the owner separately approved two sequential autonomous stages.
Stage 1 is technically complete. Its green terminal handoff, independent
curator verification and the fresh Stage 2 executor satisfy the recorded
entry condition; none of that widens the exact Stage 2 contract below.

Stage 1 is one minimal mechanical Admission Controller inside the existing DCP
daemon and SQLite for exactly two new synthetic `dcp-review-lab` native
task/card identities. The two existing stock-compatible worker and automatic
review contours may run independently. After both exact heads are approved and
provider-qualified, only one durable admission owner may hold terminal merge
authority. The other task persists a passive FIFO wait with no process, timer,
heartbeat, watcher, model polling or token use. A terminal result is the event
that causes one model-free reconciliation of the next waiter.

Reconciliation has three allowed outcomes. A compatible fresh candidate may
claim and merge. Deterministic relevant-main staleness may create one bounded
wake/resume for the same original worker and, after a new exact-head handoff,
one fresh automatic review. Proven conflict or ambiguity may persist one
structured arbiter-needed incident packet, but Stage 1 cannot create or call an
arbiter. Exact task/card/session/worktree/repository/PR/head/check/review and
admission-generation identity, FIFO order, ownership and action outcome must
survive controlled restart. Duplicate review, wake, claim or merge, stale
ownership and manual orchestration fail closed.

The Stage 1 live allowance is exactly two new initial worker calls and at most
one automatic reviewer per initial exact head. One additional same-worker wake
and one fresh exact-head reviewer are permitted only if the second task's
post-first-merge reconciliation proves the ordinary-refresh condition. There
is no replacement card, generic retry, manual Run Review or model call beyond
those bounds.
The happy-path canary should use compatible changes and complete with only the
two initial workers and two reviewers.

Stage 1 has now completed its governed managed-fork PRs, green CI, immutable
pin updates, deterministic build/install gates and bounded live qualification.
The implementation adds only additive migrations in the existing SQLite plus
the bounded admission records/events/actions above. It adds no
second registry/database/daemon, queue service, scheduler, watcher, heartbeat,
general recovery loop, UI column, Release Train, label authority, production
target, `wb-core`, hosted surface, Telegram, Human Gate or owner-acceptance
synthesis.

Stage 2 is limited in advance to one event-driven arbiter v1 for a proven
Stage 1 structured ambiguity. Its reviewed pre-runtime contract is
[I13 Stage 2 global release arbiter v1](I13_STAGE2_ARBITER_V1_CONTRACT.md).
That contract fixes one exact incident generation, the Sol/xhigh one-call and
16,384-token arbiter budget, decision/mutation authority, cards 11/12 and the
seven-call total synthetic qualification ceiling. It must be green, merged and
present in the clean canonical checkout before managed-source implementation,
runtime mutation or a model call. Contract PR #133 and managed-source PR #23
are green and merged. Contract correction PR #137 and managed-source correction
PR #24 additionally pin the qualified strict rollout-budget configuration and
one audited same-generation recovery from the observed local strict-config
rejection. The corrected source was pinned by PR #138 and deterministically
installed. Its provider then rejected root response-schema `oneOf` with
`invalid_json_schema` before inference, result output or token use. Revision 19
freezes one final, separately audited same-incident re-arm after a
non-compositional schema correction; it does not authorize a second
inference/model call or a general loop. Managed-source PR #25 is green and
merged, and this revision pins its exact immutable merge/tree; installation and
resumed live qualification are not yet claimed.

The first Stage 2 live identities are immutably cards 11/12 with approved
exact-head reviews and green checks. The earlier four-byte integration-literal
drift was corrected without repeating either worker or reviewer. Admission
then merged card 11 once at
`b34b31b5443890e69128db2862726950a6bbac0d` and retained card 12 under the
global freeze with exact incident
`dcp-global-release-2694dbd8b3d4897063603d7a8607ca516aa2f8e05c5a3c39cf56d8e3f18c3c60`.
The first package fenced one launch, but Codex strict parsing rejected its
top-level `rollout_budget.*` shape before a Codex session or provider request;
the durable action row is `failed/child_failed`, and the live model-call total
therefore remained the four initial worker/reviewer calls. Correction PRs
#137/#24 preserve that rejection in one migration-0053 audit row and re-armed
only this same incident/generation. Exact installed source
`2fbd9bf4789a5b388fb12c58d9347968ed06e6de` then passed strict config and
opened Codex session `019ff21d-4cde-72d1-b70d-49efd3cd1c17`, but the provider
rejected unsupported root `oneOf` with `invalid_json_schema` before inference,
result output or tokens. At that checkpoint the incident remained failed/frozen
with zero recovery wakes and one durable incident row; revision 19 then
authorized the final separately audited schema correction.

## Stage 2 terminal result

The fresh Stage 2 executor reached a proven terminal `BLOCKED`, recorded in
[I13 Stage 2 terminal BLOCKED evidence](I13_STAGE2_BLOCKED_EVIDENCE.md). The
single Sol/xhigh inference returned `assign_recovery` but
`maxFreshReviews=0`; trusted validation rejected it because the only permitted
path requires one fresh review. The durable incident remains frozen with one
call, no decision, no wake and no recovery review. No continuation is
authorized by the original contract.

## Owner-approved exact-incident successor correction

On 2026-08-12 the owner authorized the separately reviewed
[exact-incident successor arbiter contract](I13_STAGE2_ARBITER_SUCCESSOR_CONTRACT.md).
It does not revise or accept the rejected artifact. It preserves the original
failed row, result/input/schema artifacts, session, token count and counters,
then permits one distinct attempt-generation-2 `gpt-5.6-sol`/`xhigh` call for
the same incident under a hard 16,384-token budget. The new contract must merge
into the clean canonical checkout before source work; managed source, immutable
pin and deterministic install/preflight must then merge and complete before the
call.

The successor model does not own `maxWorkerCalls` or `maxFreshReviews`. Those
fields are absent from its decision schema; the trusted daemon fixes the only
positive policy to one same-worker wake plus one fresh exact-head review. The
successor may choose only the existing card-12 recovery owner/path or a bounded
safe stop. At most one successor decision, worker wake, reviewer and PR #9
terminal merge may occur. Duplicate, late, stale, foreign and malformed results
are inert, restart cannot relaunch, and every wait remains model-free without a
timer, watcher, heartbeat or poll. There is no replacement card/incident/PR,
third arbiter call or general retry policy.

The one successor call then produced an exact schema-valid recovery artifact,
but the trusted validator omitted its nested, frozen-envelope
`mergeTreeEvidenceDigest` from the evidence allowlist and failed closed. The
owner-authorized
[exact-result validation recovery](I13_STAGE2_SUCCESSOR_VALIDATION_RECOVERY_CONTRACT.md)
permits one reviewed model-free correction and one atomic validation of that
unchanged exact result. It permits zero additional model calls, records the
failed successor state in a separate audit row and stops at `decided`/zero-wake
until a controlled restart. Every non-exact or later replay remains inert.

The exact recovery source was subsequently merged, deterministically installed
and exercised. Its one model-free replay accepted the unchanged successor
result once and stopped at `decided`/zero-wake. The required controlled restart
then consumed the sole card-12 wake, but the stock native resume failed before
Codex launch because the preserved worker has no restorable `agent_session_id`.
The successor attempt is terminal `failed/repair_launch_failed`, with one
accepted decision, one consumed wake, no recovery review and no merge. A second
controlled restart was inert. This terminal `BLOCKED` is recorded in
[I13 Stage 2 successor terminal evidence](I13_STAGE2_SUCCESSOR_TERMINAL_EVIDENCE.md);
no continuation is authorized by the successor contracts.

## Owner-approved exact card-12 fresh worker-session recovery

On 2026-08-12 the owner separately authorized the governed
[card-12 fresh worker-session recovery](I13_STAGE2_CARD12_FRESH_WORKER_RECOVERY_CONTRACT.md)
after the immutable `failed/repair_launch_failed` predecessor above. It does
not reset the consumed native wake or change the accepted successor decision.
Its own reviewed contract must merge into the clean canonical checkout before
managed-source work; separate reviewed source and immutable pin merges plus
deterministic install/preflight must complete before runtime or a model call.

Only existing card/session `dcp-review-lab-12`, task `i13-arbiter-b`, its
current worktree/branch, PR #9, old head
`d4fcb68051ae113ed497d02151a759800ee85633` and the same incident are eligible.
Recovery generation 1 may create exactly one separately audited fresh
stateless worker runtime/Codex session under a hard 16,384-token ceiling. The
old empty native `agent_session_id`/`runtime_launch_id`, failed row, one
accepted decision and one consumed wake remain unchanged. The worker receives
only the bounded original task/scope and exact conflict-repair envelope, may
produce one guarded same-branch head, and has no second attempt.

One trusted new head may launch at most one fresh context-free reviewer. Only
approved/no-findings output, the exact named successful check and current
OPEN/non-draft/MERGEABLE/CLEAN provider facts may rebind admission sequence 4
and let the existing daemon terminally merge the same PR #9 once. Duplicate,
late, stale, foreign, malformed, restart or exhausted-budget cases fail closed
without another worker/reviewer. No new card/task/native session/worktree/
branch/PR/incident/arbiter call or decision, transcript replay, general retry
or expanded repository is authorized.

Exact source `75a14431a3433f581755f2e0ec096814e3e9ecb1` was subsequently
deterministically installed and preflighted. Its audited migration re-armed the
same zero-call generation-1 row once, and the one fresh stateless worker call
started with exact Codex thread `019ff5f3-c655-7ea2-9213-6e137f148285`.
The worker reached the proven add/add conflict and wrote only the permitted
local two-line resolution, but exhausted the hard 16,384-token rollout budget
before commit or guarded push. The row is terminal
`failed/worker_process_failed`, worker/reviewer calls are `1/0`, the remote head
is unchanged and no review, admission rebind or merge occurred. A controlled
post-terminal restart was inert. This terminal `BLOCKED` is recorded in
[card-12 fresh worker recovery terminal evidence](I13_STAGE2_CARD12_FRESH_WORKER_RECOVERY_TERMINAL_EVIDENCE.md);
no second worker/reviewer attempt or manual completion is authorized.

## Owner-approved exact card-12 model-free rebase continuation

On 2026-08-13 the owner separately authorized the governed
[card-12 model-free rebase continuation](I13_STAGE2_CARD12_MODEL_FREE_REBASE_CONTINUATION_CONTRACT.md)
after the immutable `failed/worker_process_failed` predecessor above. The new
reviewed contract must merge into the clean canonical checkout before managed
source work. Separate managed-source and pin PRs plus deterministic exact
install/preflight must complete before the daemon mutates the retained rebase.

Only the same card/session/task/worktree/branch/PR #9/incident and exact old
head/current main are eligible. One daemon-owned model-free action may stage
only the already written permitted two-line conflict resolution, continue the
existing single-commit detached rebase non-interactively, restore only the
existing local branch ref and push that same branch exactly once with the old
head as force-with-lease. Preconditions bind the terminal predecessor row and
artifacts, complete rebase metadata, sole AA index path, resolved bytes, fresh
remote/provider facts and absence of active mutators. Any mismatch fails before
Git mutation; an uncertain one-shot outcome cannot be retried.

This continuation authorizes zero worker model calls and zero arbiter model
calls or decisions. Only one trusted exact new head may receive at most one
fresh context-free reviewer. Approved/no-findings output, one successful named
check and current OPEN/non-draft/MERGEABLE/CLEAN facts remain prerequisites for
rebind of admission sequence 4 and the existing daemon's one terminal merge of
the same PR #9. All predecessor rows and their `1/0` fresh-worker/reviewer
counts remain immutable. No replacement card/task/native session/worktree/
branch/PR/incident, second continuation/reviewer, manual Run Review, manual
completion or general Git/retry mechanism is authorized.

The contract merged as dev-control-plane PR #151 at
`e17fa9080434b5642667392fb06db61cf35f19bd`. Managed-source PR
[#30](https://github.com/orenvlad-ai/dcp-orchestrator/pull/30) then passed its
`source` and `package` checks and merged normally at exact commit
`a7b5476fb886bcbb6bbd91aa89da17966547b3b8`, tree
`53525c260b4de1ed749aeb4c89f4e085e433c9bd`. Migration 0059 adds only the
subordinate exact continuation row and its one-action/one-reviewer fences.
This pin revision claims no installation, runtime action, new head, reviewer or
merge; deterministic install/preflight remains mandatory.

## Owner-authorized exact provider-base correction

The pinned source was deterministically built, installed and preflighted at
`2026-08-13T06:38:17Z` without starting the daemon. The exact receipt names
`a7b5476fb886bcbb6bbd91aa89da17966547b3b8`, tree
`53525c260b4de1ed749aeb4c89f4e085e433c9bd`. A final read-only provider proof
then established that current `refs/heads/main` remains exact `b34b31b...`, but
GitHub REST/GraphQL and durable PR state all retain the exact PR-base snapshot
`dbaf01b05e85ffffa4c843a905e2fe5229eaf0da`. That snapshot is an ancestor of
current main. Managed PR #30 incorrectly required the two distinct facts to be
equal and would fail before action.

The governed
[provider-base correction contract](I13_STAGE2_CARD12_MODEL_FREE_PROVIDER_BASE_CORRECTION_CONTRACT.md)
authorizes only one additive exact correction row and separate exact checks for
provider base, current main and their ancestry. It adds no authority or model
call and preserves the original one-action/one-reviewer ceilings. Runtime
remains stopped; migration 0059 has not run and no continuation/reviewer fence
has been consumed. The correction contract, managed source, pin and repeat
install/preflight must complete before startup.

The correction contract merged as dev-control-plane PR #153 at
`9610bf1a8fa41f631ca5ed336d0d9b0313d7d73f`. Managed-source PR
[#31](https://github.com/orenvlad-ai/dcp-orchestrator/pull/31) then passed its
`source` and `package` checks and merged normally at exact commit
`b22d8961fcc367d414510a5daae53eab19bd2578`, tree
`f10fed7982187a3a963b85c93285e641c41c289d`. Migration 0060 adds the one
immutable correction row and the validator separates exact provider base,
current main and ancestry. This pin revision claims no repeat installation or
runtime action.

## Card-12 model-free continuation terminal result

Exact corrected source `b22d8961fcc367d414510a5daae53eab19bd2578` was
subsequently built, installed and preflighted. At the first controlled bundle
start, native terminal restoration launched ordinary Codex workers for
preserved cards 11 and 12 before the exact model-free action fence. They
reported 33,238 and 33,573 tokens. The exact continuation row failed closed as
`failed/identity_drift` with worker/arbiter/action/reviewer counters
`0/0/0/0`, but the two actual worker provider calls already violated the
zero-worker-call contract. Startup also replaced the preserved detached rebase
with a branch-attached `UU` conflict-marker state.

The bundle is stopped. PR #9 remains OPEN on old head
`d4fcb68051ae113ed497d02151a759800ee85633`; no new head, fresh review,
admission rebind or merge exists. This terminal `BLOCKED` is recorded in
[card-12 model-free continuation terminal evidence](I13_STAGE2_CARD12_MODEL_FREE_REBASE_CONTINUATION_TERMINAL_EVIDENCE.md).
No restart, reconstruction, reviewer, merge or further continuation is
authorized without a new separately reviewed contract.

## Owner-approved card-12 cold-start quarantined recovery

The owner separately authorized the governed
[cold-start quarantined recovery](I13_STAGE2_CARD12_COLD_START_QUARANTINED_RECOVERY_CONTRACT.md)
after the immutable blocker above. It explicitly supersedes, rather than
reuses, the violated zero-worker-call continuation authority. The two native
restoration calls and 66,811 reported tokens remain immutable failure
accounting.

The new cycle first requires a durable model-free startup quarantine to be
established and read before any session reconcile, tmux/native restoration or
stored worker-command launch. Exact governed cards 11/12 cannot be restored as
ordinary workers; unknown/missing database state fails daemon startup before
runtime creation, while unrelated eligible sessions retain stock behavior.
The quarantine, exact crash/restart tests and one subordinate recovery row
must merge in a separate managed-source PR. A separate pin/install-guard PR
and deterministic build/install/preflight must complete before runtime starts.

Only then may one daemon-owned model-free action create an immutable backup,
verify the exact branch-attached card-12 `UU` marker state, reconstruct the
known one-commit rebase onto current main, apply only the authorized two-line
bytes and push the same PR #9 branch once with exact old-head force-with-lease.
This cycle permits zero worker calls, zero arbiter calls and at most one fresh
context-free reviewer on the one new head. Fresh approved/no-findings output,
the new named successful check and current CLEAN/MERGEABLE facts remain
mandatory for admission sequence 4 rebind and one normal terminal merge.
Every mismatch or worker launch is terminal `BLOCKED`.

The cold-start recovery contract merged as dev-control-plane PR #156 at
`623c3896a50d410e5b305ed08cf29abdc40b5b23`. Managed-source PR
[#32](https://github.com/orenvlad-ai/dcp-orchestrator/pull/32) then passed its
`source` and `package` checks, received a semantic/security review with no
findings, and merged normally at exact commit
`032e16aa3025858eeddecc1a25e87d4ec8ea4f18`, tree
`cc519e93923e02d59463bbe14dd77192a237ce95`. Migration 0061 adds only schema;
the daemon atomically bootstraps and validates the exact quarantine before
constructing runtime/session restoration, then exposes one exact backed-up
model-free recovery. This pin revision adds an installer-side active-recovery
guard and claims no installation, runtime start, action, reviewer or merge.

That source was then deterministically installed. Its first controlled start
proved the quarantine ordering before restoration: cards 11/12 stayed as bare
shells with zero descendants and no governed worker call. The recovery failed
closed before backup/action as `failed/preflight_or_backup_failed`, revision 1,
with worker/arbiter/action/reviewer counters `0/0/0/0`, because its trusted
`/opt/homebrew/bin/gh` constant was a symlink while the verifier accepts only a
physical regular file. The exact Git/PR/runtime state remained unchanged.
Managed-source [PR #33](https://github.com/orenvlad-ai/dcp-orchestrator/pull/33)
preserves that failure in one immutable migration-0062 audit, re-arms only the
same row at revision 2, and substitutes the pre-proven physical binary at the
same digest. It passed `source` and `package`, received an exact-head
semantic/security review with no findings, and merged normally at
`798e9bfb8f75846d846f2ec2d4dfc9ec0076573b`, tree
`e5668c51fbc3c7aae872cafbe4759fc405fa0677`. This correction adds no identity,
model call, action, reviewer or retry authority. It is not runtime until this
separate pin merges and repeat deterministic install/preflight succeeds.

After that pin merged, source PR #33 was deterministically installed and its
controlled start again proved the quarantine: cards 11/12 stayed bare and no
governed worker launched. Recovery again failed before backup/action as
`failed/preflight_or_backup_failed`, now revision 3 with `0/0/0/0` counters.
The newly proven exact cause was Git's regular `AUTO_MERGE` tree ref already
created with the preserved stock conflict. It is neither a running process nor
an additional worktree path, and its exact tree/file/blob identities reproduce
the same marker bytes. Managed-source
[PR #34](https://github.com/orenvlad-ai/dcp-orchestrator/pull/34) preserves that
second failure in immutable migration 0063, re-arms only the same row at
revision 4, requires all exact `AUTO_MERGE` identities and includes the ref in
the sealed backup. A copied exact Git proof showed that the existing governed
`reset --hard` removes it and yields the required clean old-head basis. PR #34
passed source/package CI, received exact-head semantic/security review with no
findings and merged normally at
`04a967c26499a482fbff9a204bab046d79d2a2e2`, tree
`fedee6276e8ce4a492d3c298aaf4bf843179c8bc`. It adds no authority. It is not
runtime until this separate pin merges and final repeat deterministic
install/preflight succeeds.

That final source was deterministically installed and preflighted. The terminal
start again fenced cards 11/12 before restoration with zero governed worker or
arbiter calls. It sealed exact backup digest
`82d0e5834375c380069e7d48a7fdb2066371670d92733ce59545718469a4f3dd`
and consumed the sole model-free action. The action produced clean local commit
`4de6ff1a0b80223a9b32a05ba68cf0b665296081` with the exact bytes and parent,
but Git retained `REBASE_HEAD`; the trusted postcondition rejected it before
push. The row is terminal `failed/model_free_action_failed`, revision 7, at
worker/arbiter/action/reviewer counts `0/0/1/0`. Remote PR #9 remains at old
head `d4fcb68051ae113ed497d02151a759800ee85633`; no fresh review/check,
admission rebind or merge exists. A controlled restart advanced quarantine
verification to 4/4 while preserving all terminal counts and producing no
duplicate. Exact proof is in
[cold-start recovery terminal evidence](I13_STAGE2_CARD12_COLD_START_QUARANTINED_RECOVERY_TERMINAL_EVIDENCE.md).
The bundle is stopped and no further recovery action is authorized.

The owner has now separately authorized the reviewed
[exact REBASE_HEAD finalization](I13_STAGE2_CARD12_REBASE_HEAD_FINALIZATION_CONTRACT.md).
It supersedes only the consumed cold-start authority while preserving that
failed revision-7 row, its sealed backup, action fence, counters and every
earlier artifact. One new subordinate finalization row may recognize Git's
regular `REBASE_HEAD` as inert only when the entire retained-candidate,
pseudoref, quarantine, process, SQLite, Git and provider identity conjunction
is byte-exact. The trusted daemon may then adopt existing clean commit
`4de6ff1a0b80223a9b32a05ba68cf0b665296081` without reconstruction or any
local Git write and issue one old-head force-with-lease push of the same PR #9
branch. Zero worker/arbiter calls and zero rebase/reconstruction are allowed;
at most one fresh context-free reviewer may run on that exact new head before
the existing admission rebind and normal merge gates. Contract, managed-source
and pin/install-guard PRs must merge separately and deterministic stopped
preflight must pass before the single live attempt.

Managed-source [PR #35](https://github.com/orenvlad-ai/dcp-orchestrator/pull/35)
implements only that exact finalization. Migration 0064 creates the additive
successor without changing the failed predecessor; the daemon proves the full
candidate, inert-pseudoref, backup, quarantine, process, SQLite and provider
conjunction before one action fence and exact force-with-lease push. The stock
reviewer and existing admission/merge engines retain their exact-head gates.
PR #35 passed source/package CI, received an exact-head semantic/security
review with no findings and merged normally at
`6f53f74f456b869c98bb82d928f671b54672808a`, tree
`0fab2ee443d8bf20a0efcc524851e8c9589e6dd9`. This separate pin adds an
installer refusal while the finalization is active and claims no installation,
runtime action, push, review, admission rebind or merge.

That source was deterministically installed and preflighted. Its first start
held the startup quarantine at 5/5 with both governed cards still bare, then
failed before the action fence as `failed/identity_drift`, revision 1, with
worker/arbiter/action/reviewer counters `0/0/0/0`. The exact cause was not live
identity drift: finalizer predecessor validation reused the old tool-path and
`AUTO_MERGE` audit queries whose predicates intentionally require the earlier
authorized rev2/rev4 recovery states. Both therefore returned zero for the
required terminal rev7 predecessor although both immutable audit rows remained
present exactly once. Candidate, pseudorefs, remote PR, sealed backup,
admission and incident remained unchanged; no push or review occurred.

The contract's bounded direct-path authority is implemented by managed-source
[PR #36](https://github.com/orenvlad-ai/dcp-orchestrator/pull/36). Migration
0065 preserves that exact zero-action failure in immutable correction audit
`52490d8c01eccc8f02984ec4d863895c0215950590cfc5309d00a1525eb8f11b`,
re-arms only the same finalization row at revision 2, and validates the audit,
both original audit identities, terminal predecessor and quarantine 6/6+
without changing either historical query. PR #36 passed source/package CI,
received exact-head semantic/security review with no findings and merged
normally at `e15a6d22f83876b240fa61889b6821bd49904f28`, tree
`48d1266abc44de79bda0ca2865558d259325fc0d`. Its repeat deterministic install
and preflight passed without a runtime start. The final stopped prestart source
audit found that executor preflight still required obsolete revision 0 even
though migration 0065 and the engine admit only re-armed revision 2. Managed-
source [PR #37](https://github.com/orenvlad-ai/dcp-orchestrator/pull/37)
uses one exact revision-2 constant at both gates, explicitly rejects revision 0
and changes no other precondition or authority. It passed source/package CI and
exact-head semantic/security review, then merged normally at
`1f1e8cedf44d30773568f8801710f1371b14a47b`, tree
`4523bfacf690c15f75c155ccfc2f14831db7b2f2`. Its deterministic install and full
prestart proof passed. The sole live action then performed exactly one guarded
push of candidate `4de6ff1a0b80223a9b32a05ba68cf0b665296081`
and failed closed at `failed/provider_identity_drift`, revision 4, counters
`0/0/1/0`: post-push GitHub base changed from historical provider snapshot
`dbaf01b05e85ffffa4c843a905e2fe5229eaf0da` to exact current main
`b34b31b5443890e69128db2862726950a6bbac0d`. No reviewer ran. The new required
check failed before any runner step on both its initial attempt and one ordinary
rerun because GitHub reported failed account payments or an insufficient
spending limit for the private repository.

Managed-source [PR #38](https://github.com/orenvlad-ai/dcp-orchestrator/pull/38)
preserves the one action/push and first post-push provider/check facts in
migration 0066. It re-arms only inspect-only revision 5 at `0/0/1/0`; the engine
cannot re-enter the push path, and historical pre-push base remains distinct
from current-main post-push base. PR #38 passed source/package CI and exact-head
semantic/security review, then merged normally at
`15b51450b391fdc1ae0f172bbbf95275a6388030`, tree
`f819398a7e78ffa68630b62a3234e6e95283be57`. That exact source was
deterministically installed at `2026-08-13T16:25:14Z`; full source/package,
Go, typecheck, 15/348 renderer tests and installed-artifact preflight passed.
The final receipt SHA-256 is
`b362851fb43d772a7cbd1d1a85ebeaa6980f78a5e1b96d87f6ae74bb2b5eb0dc`.
Runtime remained stopped, goose remains 65 and migration 0066 is unapplied.
The cycle is technically `BLOCKED` until a human fixes GitHub billing/spending
and the unchanged exact-head required check succeeds. Starting now would
consume the sole reviewer against a known-failed prerequisite. Exact terminal
proof is in
[REBASE_HEAD finalization terminal evidence](I13_STAGE2_CARD12_REBASE_HEAD_FINALIZATION_TERMINAL_EVIDENCE.md).

The owner then explicitly directed continuation after the human-only blocker
was removed without task/code/head drift. The bounded synthetic repository was
made public only after a full reachable-history review found no secrets; the
same Actions run then completed real checkout/test steps successfully on exact
head `4de6ff1a...`. One installed inspect-only start applied migration 0066,
used no second action or push, launched one fresh context-free reviewer and
persisted approved/empty-findings ReviewRun `efa36083-3efd-497f-90b7-db7e7fbf04d2`.
Admission sequence 4 rebound to that run/current main and PR #9 squash-merged
once at `5bfd20d3b3f5b7d9d9ccb02500b742a917e6ea01`. The finalizer is
`succeeded` revision 9 at `0/0/1/1`. Controlled restart advanced quarantine to
8/8 with no duplicate model/action/review/admission/merge activity, and the
bundle is stopped. Exact proof is in
[REBASE_HEAD finalization success evidence](I13_STAGE2_CARD12_REBASE_HEAD_FINALIZATION_SUCCESS_EVIDENCE.md).

## Bootstrap and authority

Codex automatically receives root `AGENTS.md` in the repository. A new curator
reads local `DCP_curators/AGENTS.md`, root `AGENTS.md`, this contract, then only
the relevant authoritative scope documents. Do not reconstruct current state
from chat history.

One primary curator discusses and dispatches one direct executor in a separate
worktree. There is no nested curator or parallel DCP change. The executor starts
from exact current `origin/main`, runs relevant tests and semantic/security
self-review, and opens one ready PR. Ordinary protected GitHub review, green CI,
safe merge, and a clean canonical fast-forward apply. Technical completion is
not owner acceptance; only the owner may write `Задача принята`.

For the existing I8 worker flow, the curator has one normal mechanical entry
only: `bin/dcp-ao-submit`. The I11 submit API is an internal/lab model-free
proof surface, not a second curator dispatch route or manual UI flow. I12 needs
no second chat impulse: the daemon reacts to persisted lifecycle/SCM facts and
the manual stock Run Review remains only a fallback through the same trigger.
Direct app launch, daemon, stop, restart, build, install, or source/dev commands
are executor operations, not curator dispatch steps.

## Quiet curator closure

Every executor task prompt ends with a mandatory instruction to reach an
applicable terminal state independently and, after COMPLETE or proven BLOCKED,
send exactly one final technical handoff to the originating curator task, then
stop. The handoff states status; work done; work not done or out of scope; PR
and final SHA; checks; review, CI, merge and canonical fast-forward state;
difficulties; risks; and blockers. Each field remains explicit even when its
value is none or not applicable.

Immediately after a successful dispatch the curator ends the turn. Quiet wait
means the absence of active model or tool calls; it is not a wait/poll loop.
Until one of the three permitted wake signals arrives, the curator does not
initiate executor read/list/wait/status queries, GitHub/CI/runtime audits of the
executor's work, follow-up prompts, interim summaries, parallel work,
independent verification of the handoff, heartbeats, automations or monitoring.
The only wake signals are the final handoff, a proven request from the executor
for an action that strictly only a human can perform, or a new explicit owner
instruction.

All technical verification and evidence, relevant checks, semantic/security
self-review and terminal closure before handoff belong to the executor. After
the handoff the curator only restates its result concisely to the owner without
a second technical audit. This closure does not weaken the one-active-change
rule, protected GitHub review, green CI, safe merge, clean canonical
fast-forward or any safety boundary above. Technical completion remains
distinct from manual owner acceptance; only the owner may write
`Задача принята`.

## Installed happy-path baseline

The exact installed source is `a96f4ba9410f088401cee8700e092f1f674ad872`,
tree `bedd8adf2508a8f8fdb692354f146d4353535c4d`. It retains the
historical result: the card-12 finalizer succeeded, PR #9 merged once and the earlier
controlled restart preserved terminal rows/counts. Card 13 also succeeded on
its original identity: PR #10 merged once at `1b3f9fb...`, task revision 10 is
merged, admission sequence 5 and its sole review are succeeded, and no model
action is active.
All earlier BLOCKED recovery attempts, the sealed backup, restoration-token
accounting and cards-11/12 quarantine remain immutable evidence as recorded
above. The first I18 deterministic install completed with receipt
`70187c13ab0bc8bac07cd2d9ff27e230b866e087` / tree
`ee81758b33443a66835f785e2cb178b560808c15`, then its first controlled start
failed closed before daemon wiring: cards 11/12 had naturally reached exact
stock terminal `exited/terminated`, while their startup fence admitted only
the earlier `idle/non-terminated` pair. Card 13 and all model/action/admission
counts remained unchanged. The repeat deterministic install completed at
`2026-08-14T09:00:51Z` with receipt SHA-256
`0b8744901c8ddf9223ee8bab4add0f645e59bc244888d5d1846b4033d343ee2c`
and backup `i12-20260814T090051Z`. Its controlled start preserved zero active
model actions and delivered the stock eligibility signal, but the terminal
merge lineage gate found empty `diff_base_sha`/`diff_base_ref` before any claim.
That verified predecessor was replaced only through the recorded backup/install
sequence below. Application source is the public managed repository
`orenvlad-ai/dcp-orchestrator` at exact pinned commit
`3bc21e11060d07b7f5339365b8df58f82b9c5439`, tree
`0af68800b32c4ec195722b72cd8cd39f8aafbac3`. That
fork preserves official Agent Orchestrator `v0.12.1`, commit
`1df40e93772c2c48e916870d9c3ddf8f29a69f84`, and the qualified I8 behavior.
Managed source is build/test input only; it is never the canonical runtime and
`npm run dev` must not be used to keep DCP Lab alive.
The final deterministic install completed at `2026-08-14T09:55:20Z` with
verified backup `i12-20260814T095519Z` and receipt SHA-256
`5f8ce03ca79da650c23c4968eae2e1e9c3deed05dcd57c6d08e108bbe2c6a782`.
One controlled start repaired only the exact empty card-13 creation base and
completed its existing admission/merge path. A controlled restart retained the
same task/review/lease/merge and zero duplicate model or merge activity;
quarantine reached 14/14. The canonical application is stopped. Exact proof is
in [I18 success evidence](I18_CARD13_ADMISSION_STATUS_DOT_REPAIR_SUCCESS_EVIDENCE.md).
The later Phase 1 presentation-only source was deterministically installed at
`2026-08-14T20:19:32Z` with backup `i12-20260814T201931Z` and receipt SHA-256
`a3f73b2a5c24abe95dc7891ad5768ce33ceb28b6ae79292bc0313546b1edc10f`.
Stopped preflight preserved all five merged future-card identities, ten total
and zero active model actions, and no nonterminal policy task. Exact proof is
[recorded here](DCP_LAB_PHASE_UI_V1_INSTALL_EVIDENCE.md).
Preparation fetches the complete ancestry of that exact immutable fork commit
with bounded retry and converts any older shallow checkpoint before provenance
verification; a moving ref or depth-limited substitute is not accepted.

The sole runtime is the native arm64 application at the exact path:

`/Users/ovlmacbook/Applications/DCP Orchestrator.app`

Its bundle id is `pro.devcontrol.dcp-orchestrator`, main executable is
`dcp-orchestrator`, embedded daemon/CLI is `dcp-orchestratord`, health service is
`dcp-orchestrator-daemon`, and the fixed loopback port is `43231`. The app owns
the daemon lifecycle through the native supervisor link. It stores durable
state below the explicitly supplied canonical `DCP_AO_LAB_ROOT`:

`/Users/ovlmacbook/Library/Application Support/DCP Orchestrator`

`state/` contains the run-file, gateway/install facts and app settings; `data/`
contains SQLite, worktrees, Electron user data and lab-local Codex state;
managed source, builds, evidence, the remote-free `targets/dcp-lab` and exact
PR-capable `targets/dcp-review-lab` also stay under that root. Electron caches use
`~/Library/Caches/pro.devcontrol.dcp-orchestrator`; logs use
`~/Library/Logs/DCP Orchestrator`. The installed
`/Applications/Agent Orchestrator.app`, `~/.ao`, real repositories other than
the explicitly authorized disposable review-lab canary, other remotes,
`wb-core`, production and hosted systems are never inspected or used.

Executor-only installation is deterministic:

```text
export DCP_AO_LAB_ROOT="$HOME/Library/Application Support/DCP Orchestrator"
bin/dcp-ao prepare
bin/dcp-ao build
bin/dcp-ao install
bin/dcp-ao preflight
```

`build` verifies the fork pin/provenance, DCP operational source gate,
generated API parity and model-free Go/Vitest/type gates, then packages an
arm64 `.app`. `install` ad-hoc signs and places the exact
verified bundle at the canonical path, retaining any prior verified DCP bundle
as a lab-root backup together with applicable state/data. A running canonical
old app is replaced only after its exact app/daemon identity is proven and
read-only SQLite/tmux/process-tree checks prove no active worker, reviewer,
future policy slot owner or bounded Stage 2 arbiter model action. A claimed or
running `dcp_model_action` and an `active` worker row are always a stop.
A non-active row with a
historical launch id is replaceable only when its exact retained pane exists as
a bare shell or is provably absent; any descendant or ambiguous probe remains a
stop.
The submit lock closes the normal submission race; a foreign, duplicate,
unhealthy or ambiguous process and any active action fail closed. A persisted
running review with a missing pane or bare stable shell is preserved for the
new daemon's model-free startup reconciliation. Only a proven descendant of
that exact reviewer pane counts as active; unrelated system processes do not.
Installation leaves the new
bundle stopped so all post-install gates run before an authorized live launch.
`preflight` verifies the exact fork
source, Info.plist identity, arm64 main and daemon executables, signature,
license/notice/provenance, absence of updater feed and packaged
telemetry/updater/crash modules, exact fork-bound install receipt and Codex
isolation. It never probes the upstream installed app or its data.

## Gateway and lifecycle

`bin/dcp-ao-submit --target dcp-lab --prompt '<one line>'` holds a lab-local
singleton from contour proof through the one native `ao spawn`. The prompt is
non-empty, one line and at most 512 UTF-8 bytes; the target is the exact
remote-free disposable repository.

The only PR-capable entry is the same canonical script with every discriminator
explicit:

`bin/dcp-ao-submit --target dcp-review-lab --profile synthetic-pr --task-id '<lowercase-id>' --prompt '<one line>'`

That profile accepts a 1-16 character lowercase task id and verifies the exact
public repository URL, clean fast-forwarded `main`, canonical base and linked
worktree topology. The happy-path bundle durably resolves equal/conflicting
task replay before a model action and binds one stock native
`dcp-review-lab-<n>` worktree/session plus
`ao/dcp-review-lab-<n>/root` branch. It installs an exact `accept-edits`
worker, one Codex reviewer and the typed `dcpReviewLabNetwork` marker. Worker
network is eligible for a new policy task only after the task row and exact
data/worktree/Git/branch/fetch/push identities validate; card number is not an
authority or ceiling. Cards 1-12 keep their historical classification, every
reviewer and any arbiter remain outside this worker-network contour. Unknown
or duplicate flags, another repository/profile/path/remote/branch/config or
ambiguous value fail closed. The remote-free target never receives this
profile or any GitHub mutation authority. The currently installed
qualification bundle still rejects cards 13+ until replaced by the exact new
pin.

When the exact app is off, the gateway requires stopped status, no run-file and
an unused fixed port, opens the absolute bundle path, then waits up to 60 seconds
for one exact app PID and its ready daemon. When the app is already running, it
is reused without restart or kill. The gateway matches the run-file's daemon
PID/port/owner, contour id, app PID, per-launch app instance id, bundle id,
bundle path, browser token/socket, embedded daemon command and service name.
The daemon itself produces `dcp-orchestrator-daemon` in both its authenticated
status response and run-file; the gateway requires the two independent facts
to match rather than supplying or inferring the service identity.
Two simultaneous submissions serialize into one app/daemon and two separate
worker sessions with no duplicate spawn.

Any stale run-file, foreign/duplicate app, foreign daemon, occupied port,
identity mismatch, unhealthy state or ambiguous state fails closed without
delete, kill, stop, restart or replacement. The gateway never owns the app or
daemon. Closing the last window on macOS leaves the app, daemon and work alive;
the Dock/tray can reopen the window. Explicit Quit is separate and warns or
refuses silent exit while an active worker exists or its state cannot be proven.

The renderer hides manual `Spawn Orchestrator` controls and related hints.
Backend/CLI/API/programmatic orchestrator mechanisms remain available, but only
the happy-path v1 worker/reviewer roles are active for future policy tasks after
installation. Arbiter and all other automatic roles remain inactive.

## I11 durable model-free task foundation

The existing daemon and its existing `ao.db` accept, store, read and list
synthetic DCP tasks through typed loopback-only API endpoints. The only allowed
repository identity is the exact clean, single-commit, remote-free
`targets/dcp-lab`. Each task has a durable task id, idempotency key, immutable
canonical approved task/scope representation and digest, exact repository
identity, state SUBMITTED, revision and timestamps. A per-task append-only
event stream stores monotonic sequence, event id/type/source,
correlation/causation/idempotency, from/to state and versioned payload/evidence
digests. Task state and event append share one transaction, and stale revisions
are rejected.

The same idempotency key plus the same canonical payload returns the same task
id without a duplicate event. The same key with a different payload, malformed
input or an out-of-scope target fails before mutation. The existing board shows
one stable synthetic/lab card in Working with exact substate SUBMITTED. There
is no creation button, webhook, external service, polling loop or second
display-state authority.

On daemon/app restart, schema validation preserves prior I8 sessions and the
same task, revision and events. A waiting SUBMITTED task receives no timeout,
model, process, wake, checkpoint or action lease. No full transcript,
chain-of-thought, secret, credential or user Codex configuration is stored.

## Historical I12 bounded automatic reviewer foundation

I12 reuses Agent Orchestrator's existing `Review`, `ReviewRun`, review engine,
one worker session/card, stable `review-<session>` terminal and existing
findings delivery. It adds no reviewer service, watcher, scheduler, heartbeat,
queue, second registry/database or new card. The Codex reviewer uses standard
authentication through `codex exec` with `approval_policy="never"` and
`--sandbox read-only`; web search is disabled, the unsupported exec-level
`--ask-for-approval` is not emitted, and dangerous bypass flags are rejected.
The model has no reviewer network tool, GitHub token, DCP daemon variables or
control-plane command channel. It returns only one Codex-native
`--output-schema`/`--output-last-message` JSON result containing exact
worker/reviewer/batch/run/PR/head identity, `approved` or
`changes_requested`, a bounded summary and bounded findings.

The shared trigger is serialized per worker and by the existing unique
review-run constraint. Its normal automatic path is eligible only for the exact
current head of an open non-draft PR after a non-terminated worker has safely
reached Idle with no active launch and no prior run for that exact PR/SHA. SCM
observation and successful supervised worker exit are events into that trigger;
there is no new polling loop. A completed/failed/cancelled run for the same
head is never automatically duplicated, while a new head may receive one new
review. Manual Run Review remains a fallback through the same engine.

One narrower continuation exists only for the preserved terminated worker whose
latest durable review failure proves the known reviewer working-directory
mismatch. The stock SCM observer keeps only that proven session visible long
enough to observe one replacement head; every other terminated session remains
excluded. On that exact head, the stock workspace adapter restores the saved
single-repository path and branch model-free; the engine then requires a clean
worktree at exactly that head before launching the same stable reviewer
terminal. Any resulting run or second matching failure consumes the
continuation, so it cannot become a retry loop or resurrect the worker.

The reviewer is itself one-shot supervised. Start failure, early CLI exit,
non-zero exit, signal, or zero exit without a submitted verdict durably fails
the still-running exact run and projects an actionable Needs You state rather
than perpetual Reviewing. On restart, an exact still-live supervisor is left
alone; ambiguous liveness is failed without retry; a proven stale run is failed
and receives at most one exact-head recovery launch without a model call during
reconciliation. Approval uses the stock Ready-to-Merge/SCM projection;
findings use stock delivery to the same worker identity and worktree.

After a successful model exit, the trusted one-shot supervisor reads exactly
one result artifact, independently validates its schema and every trusted
identity, and submits it through the existing session-scoped daemon endpoint.
One guarded SQLite statement completes the still-running `ReviewRun` only when
the stable reviewer terminal, batch, run, PR URL and exact target SHA match and
the same open non-draft PR row still owns that current head. Missing,
ambiguous, malformed, foreign, duplicate, late, closed/draft or stale-head
results fail closed without a verdict, retry or synthetic fallback. The
existing lifecycle path alone projects approval or delivers findings, so
SQLite remains the sole state authority and restart cannot launch a second
reviewer after a terminal verdict.

The private pane-local exact-binary `ao` alias remains only for compatibility
with other stock reviewer adapters. The Codex structured-result success path
does not prepend it to PATH and never depends on a command chosen by the model.
No global PATH entry, installed/retired AO discovery, `~/.ao`, reviewer network
permission, credential, migration, service, schema/database authority or
second persistence path is added.

### Exact synthetic-PR terminal merge

Only an Idle native worker whose project is exactly `dcp-review-lab`, whose
session/task prompt and `DCP:<task-id>` display name agree, and whose workspace,
private/common Git directories, `ao/dcp-review-lab-<n>/root` branch and single
ready PR all match may enter the terminal gate. A session base is accepted only
when both stock fields are absent or when both contain the exact `origin/main`
identity; in either case the valid PR base SHA must equal clean canonical
`main` and `origin/main`. The one structured Codex
review must be approved with no findings for that exact PR/head. Fresh GitHub
facts must show OPEN, non-draft, the same author/base/head and exact head
repository, exactly one successful check named `dcp-review-lab`, no unresolved
review thread, MERGEABLE and CLEAN.
The stock provider review decision must be the known non-blocking `none` or
`approved`; empty, unknown, review-required and changes-requested decisions,
and missing, skipped, neutral or ambiguous values elsewhere, fail closed.

The trusted daemon then claims that same `ReviewRun` once and requests a squash
merge with the expected head SHA. Success stores the provider merge SHA and
projects the existing card to terminal `Merged`; the synthetic repository has
no deploy, so no deploy fact is invented. A provider error or unknown mutation
outcome is terminal and is not automatically retried. Startup may only reconcile
an already-running claim from fresh proof that the exact PR was merged; it never
creates a second merge, reviewer, card, service or state authority. PRs #1/#2/#3
and all preceding cards/runs remain immutable.

Managed-fork PR [#8](https://github.com/orenvlad-ai/dcp-orchestrator/pull/8)
closes the final worker-side installed-CLI argv blocker at exact merge commit
`5ab85f0010bd120728b8514c84f1fe41fac0ba70`, tree
`6c0b7fadb5a4525a822b371b10fc2069fc9afa4c`. The I4 native card remains
immutable evidence of a pre-model parser failure; it is not reused or hidden.

Managed-fork PR [#9](https://github.com/orenvlad-ai/dcp-orchestrator/pull/9)
closes the next worker-side sandbox blocker at exact merge commit
`be3239808c88dff1a0f2a7801fedfb73c61ed789`, tree
`7fdd7db08e8c37f1fe783538cfea3cba2c55441a`. The non-bypass builder derives
only the concrete linked worktree's private gitdir and common `.git`, verifies
their pointer/backlink/commondir topology against local Git, and passes those
two roots through supported `--add-dir`. Missing, ordinary or inconsistent
layouts fail before Codex starts. The reviewer strips all worker
`--add-dir` pairs before enforcing read-only mode.

The failed I2 run `b65be186-7326-4272-85aa-acfcd39bc938`, the failed I3 run
whose id begins `0aaf2da9`, and `orenvlad-ai/dcp-review-lab#1`, `#2` and `#3` are
immutable audit evidence: they are not changed, reused, retried or merged. The
I5 checkpoint card `dcp-review-lab-4` is also immutable: its one worker call
reached Codex session `019fece4-e13f-79b1-b3af-c0e6392ebdb5` and consumed
16,222 tokens, but the built-in workspace sandbox denied Git's external
worktree metadata, so it produced only an untracked marker and no commit, push,
PR or reviewer call.

The first terminal-merge qualification attempt is preserved as
`dcp-review-lab-6`: Codex session
`019fefec-83f2-7090-a4e6-fcda57f262f9` consumed 29,309 tokens, created one
local commit `c92bbef`, then stopped after two bounded push attempts both proved
that the workspace-write sandbox could not resolve `github.com`. It created no
remote branch, PR or reviewer run and is never resumed or reused. Managed-fork
PR [#14](https://github.com/orenvlad-ai/dcp-orchestrator/pull/14) adds only the
typed/exact worker network contour above at merge
`0ef626fad32af4397b345e596a0f98e1965a0077`, tree
`8d3c05febe32c15072d23f87b02c82e29e2b51be`; reviewer argv explicitly rejects
that worker flag. The first canonical submit after that install failed closed
before native spawn or model launch because the strict CLI config mirror did
not yet accept the typed marker. Managed-fork PR
[#15](https://github.com/orenvlad-ai/dcp-orchestrator/pull/15) preserves that
existing field through exact `--config-json`; that bounded merge is
`e458f545f9e7879c16278ccd13901519a5c5e6bb`, tree
`c618f25ab14c5e55402232c411332cb667e803f6`. No card 7 was created and the
remaining worker allowance stays at two calls.

Card `dcp-review-lab-7` then used worker Codex session
`019ff01e-9d97-7cf3-b241-4d6820fe26e1` to create commit
`f10c825fced998c01a3e83ef4073451c3bd2e4a3` and ready PR #4. The sole automatic
reviewer session `019ff01f-9805-7c22-9bd4-54d53e99be5d` returned approved with
no findings for exact run `28025930-ecc0-481e-a13b-9fb5a5a14a94`; the required
check is successful and provider facts are OPEN/MERGEABLE/CLEAN. The terminal
engine still compared the retired synthetic prefix and pre-marker worker
config, so it correctly made no provider mutation. Managed-fork PR
[#16](https://github.com/orenvlad-ai/dcp-orchestrator/pull/16) binds eligibility
to native card 7+ and marker=true at merge
`f23ee9a9cbc8be57710b4dd6c95a23bf0fb52b24`, tree
`67a084e9e546a725b0b19b3074ba205f6c03fa82`. The stock native spawn leaves both
session diff-base fields absent, so managed-fork PR
[#17](https://github.com/orenvlad-ai/dcp-orchestrator/pull/17) accepts only that
paired absence and instead binds the valid stored/fresh PR base to clean local
`main` and `origin/main`. The stock GitHub adapter normalizes an absent provider
review to domain `none`; managed-fork PR
[#18](https://github.com/orenvlad-ai/dcp-orchestrator/pull/18) accepts that
known non-blocking value while rejecting empty/unknown/blocking decisions. The
stock GraphQL batch omitted the head-repository field, so managed-fork PR
[#19](https://github.com/orenvlad-ai/dcp-orchestrator/pull/19) requests and
preserves `headRepository.nameWithOwner`; null or missing identity stays empty
and fails closed. Managed-fork PR
[#20](https://github.com/orenvlad-ai/dcp-orchestrator/pull/20) adds the exact
I13 Stage 1 durable admission/refresh/incident slice. Model-free preflight then
found pre-stage card 8 and PR #5 already completed, so managed-fork PR
[#21](https://github.com/orenvlad-ai/dcp-orchestrator/pull/21) binds the fresh
cohort to cards 9/10 and fixes the browser broker cancellation race exposed by
CI. Canary then exposed a false `canonical_main_diverged` packet after the first
merge advanced exact `origin/main`; managed-fork PR
[#22](https://github.com/orenvlad-ai/dcp-orchestrator/pull/22) retains the packet
as audit evidence, proves exact fast-forward ancestry and a clean merge tree,
and permits one startup-only model-free recovery. Managed-fork PR
[#23](https://github.com/orenvlad-ai/dcp-orchestrator/pull/23) adds only the
reviewed exact Stage 2 incident/input/action, one-shot arbiter and bounded
same-worker repair contour. Managed-fork
[#24](https://github.com/orenvlad-ai/dcp-orchestrator/pull/24) corrects the
strict structured rollout-budget shape and adds the one-row audited prelaunch
recovery. The current immutable source merge is
`2fbd9bf4789a5b388fb12c58d9347968ed06e6de`, tree
`ada1ccead3e9920bf1e658ac3c136bc61acea6ab`.

For the exact historical card-7 qualification, the automatic reviewer
allowance is consumed. One unused emergency worker-call ceiling remains from
the original three, but it is not used for that contour:
the complete approved run closed through model-free startup reconciliation
after exact install. There was no new card, reviewer, manual Run Review or
second chat impulse. Neither ceiling applies to a new happy-path v1 task. The
daemon claimed the existing run once and squash-merged
PR #4 at provider merge SHA
`202ca32a0e8d563c6c478d094073246383720e5d` on
`2026-08-11T10:52:05Z`. Card 7 projected `Merged` before restart and the same
run/card/SHA projected `Merged` after a controlled app/daemon restart.

The installed receipt binds fork `b23b519cd532555c203863586032d157fc1c8c13`,
daemon SHA-256 `c9d59d2c2a8453d278ebc45a5a4872e8f96d35fd9ad29cad6cd109a0043cc6a1`
and asar SHA-256 `a1206d002b16a8d9a3cb4485c4522b4fe685fdb102840d1d96530a4f11a4ff90`
at `2026-08-11T14:26:15Z`; the preceding bundle backup is
`i12-20260811T142614Z`. The Stage 1 cohort is the two distinct native cards
`dcp-review-lab-9` (`DCP:i13-admit-a`) and `dcp-review-lab-10`
(`DCP:i13-admit-b`). Admission sequence 1 belongs to card 10 / PR #6 / head
`3afd3d4cbcc2fe4a6bf2fde3e747213e5c874d53`; sequence 2 belongs to card 9 /
PR #7 / head `649c60cbe6c8542f0a3d20b05b11ae5c54a79263`. Both reviews are approved
with no findings and both named `dcp-review-lab` checks are successful.

Sequence 1 merged once at `5e65c167d8d9d36d70c89fc8e9b5b07497905645`
on `2026-08-11T13:57:55Z`. Sequence 2 waited durably without a model process,
retained its original 941-byte structured false `canonical_main_diverged`
packet, then startup reconciliation proved exact provider-base fast-forward
ancestry and a clean merge tree and merged once at
`dbaf01b05e85ffffa4c843a905e2fe5229eaf0da` on
`2026-08-11T14:28:38Z`. `refresh_wake_count` remained zero for both rows.
Two controlled starts preserved order, leases, PR/head/base/review/run/merge
identity, two succeeded rows, seven total reviews, nine total runs and ten
cards with no card 11. No duplicate review, run, wake, claim or merge appeared.
The exact two canary sessions were then terminated through the native session
lifecycle and their worktrees reclaimed while their cards still truthfully
project `Merged`; historical audit rows and reviewer panes remain. The target
checkout is clean at exact `origin/main` `dbaf01b05e85ffffa4c843a905e2fe5229eaf0da`.
PRs #1/#2/#3 remain unchanged.

## Worker and release gates

The Codex worker uses standard authentication but runs through
`codex exec --ignore-user-config --ephemeral --strict-config`, with hooks, apps,
plugins and multi-agent disabled. It does not load user MCP/plugin/app/hook
configuration; `CODEX_SQLITE_HOME` is DCP-local. AO's existing supervisor maps
running to Working, exit zero to Idle, and every failed launch/non-zero/signal
to Exited. The packaged one-shot wrapper alone receives exact `AO_DATA_DIR` and
`AO_RUN_FILE` values for its start/exit hooks. Those variables are stripped
from the retained tmux shell and from the Codex child, so lifecycle reporting
does not weaken worker isolation.

For the non-bypass `accept-edits`/`auto` modes, the worker uses Codex's supported
`approval_policy="on-request"` config override with explicit
`--sandbox workspace-write`; it never emits the unsupported exec-level
`--ask-for-approval`. For a linked worktree it adds only its verified private
gitdir and common `.git` as writable roots; no caller may supply an arbitrary
path, and ordinary/mismatched layouts fail closed. Unknown permission modes
fail closed before launch. The model-free installed-CLI preflight runs only
`--help` and `features list` while exercising the same isolation, config,
sandbox and repeated `--add-dir` parser surface, so it cannot make a model
request. Fork tests separately reproduce the baseline Git denial and successful
`git add` with only the derived roots inside an isolated linked worktree.
Only the typed synthetic-PR profile may additionally set
`sandbox_workspace_write.network_access=true`, and only after an exact future
policy task row (or immutable historical allowlisted card), canonical
data/worktree/private/common Git paths, branch and sole fetch/push origin all
match `orenvlad-ai/dcp-review-lab`. The reviewer rejects this flag before
enforcing read-only mode. No ordinary worker, remote-free target or reviewer
receives network from this exception.

The package has no updater initialization, feed metadata, maker or publisher;
updater UI/IPC is inert and updater dependencies are pruned. Renderer and daemon
telemetry cannot be enabled by environment, no telemetry control routes are
mounted, and no analytics key/host/install identity, local telemetry reservoir,
crash upload or crash reporter is initialized or packaged. Source/dev remains
only a model-free build/test instrument.

Historical I12 added no general task execution, arbiter, admission, Release
Train, general auto-merge, repair loop, monitoring service, real execution
target, `wb-core`, production, hosted API, Telegram, notarization or
distribution installer. Happy-path v1 separately activates only its exact
synthetic task, one bounded findings repair and durable admission line.
Historical I8 live qualification used only short
remote-free marker tasks and no automatic retry. The owner raised its
cumulative ceiling to five model calls: one preserved diagnostic stop-gate plus
one successful cold, one successful warm and two successful concurrent calls.
The four qualified sessions (`dcp-lab-2` through `dcp-lab-5`) are distinct and
Idle under one persistent app and daemon; minimal redacted evidence remains
outside Git. I11 itself used zero model calls. After the preserved I5 checkpoint
call, card 6 and card 7 consumed two of the separate three-worker allowance;
one unused emergency worker-call ceiling remains. The historical automatic
reviewer allowance is consumed for that exact run; neither ceiling applies to
a new happy-path v1 task, which is governed by the durable three-slot and
per-task/per-head limits instead.

`dev-control-plane` remains architecture, integration and exact-pin authority,
while the public managed fork owns application code. The retired patch queue
is historical Git evidence only. I9 remains inactive outside the explicitly
approved happy-path v1 synthetic task/review/admission slice.

## Dispatch template

```text
Task: <one bounded DCP change>
Base: exact current origin/main; separate branch/worktree
Read: root AGENTS.md -> docs/CURRENT_OPERATING_CONTRACT.md -> relevant authoritative docs
Boundary: canonical DCP_AO_LAB_ROOT and exact DCP Orchestrator.app; never installed AO, ~/.ao, repositories/remotes outside the explicitly authorized disposable canary, wb-core or production
Flow: one curator -> one direct executor; no nested curator or parallel DCP change
Entry: bin/dcp-ao-submit is the only worker entry; dcp-lab stays remote-free and only exact dcp-review-lab plus explicit synthetic-pr/task-id is PR-capable; equal future-task replay is idempotent and automatic review/terminal merge need no second chat impulse
Proof: separate contract/source/pin PRs, exact-head semantic/security review, green CI, model-free four-task/three-slot/per-head-review/FIFO/restart/dedupe fixtures, deterministic backed-up install/preflight, zero executor canary model calls and clean canonical fast-forward
Stop: fail closed on ambiguous identity/auth/isolation or unsafe cleanup; never synthesize owner acceptance
Quiet: after successful dispatch end the curator turn; quiet wait has no active model/tool calls or wait/poll loop; wake only on final handoff, proven strict human-only request, or new explicit owner instruction
Close: executor independently reaches COMPLETE or proven BLOCKED, owns all verification/evidence/semantic-security self-review/closure, then sends exactly one final handoff to the originating curator task and stops
Handoff: status; done; not done/out of scope; PR and final SHA; checks; review/CI/merge/canonical fast-forward state; difficulties; risks; blockers; curator only summarizes it without a second technical audit
```
