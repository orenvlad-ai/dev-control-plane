# I13 Stage 2 exact card-12 fresh worker-session recovery contract

contract_status: owner-approved-pre-runtime
contract_version: dcp-i13-stage2-card12-fresh-worker-recovery-v1
contract_revision: 1
recorded_at: 2026-08-12
dev_control_plane_baseline: f653320a6ad1d1dbed1f0e4ff0ef8a1fb6caca75
managed_source_baseline: 6f1b5f9828853b6c597d6e6b82fda52ced097b61
incident_generation: 1
successor_attempt_generation: 2
fresh_worker_recovery_generation: 1
fresh_worker_recovery_identity_digest: d2b7142bc9e5844ba165abe24d3222b3e1a94c3577fba5f6f8d97ec3dbad151b
worker_model_call_ceiling: 1
worker_token_ceiling: 16384
fresh_reviewer_model_call_ceiling: 1
additional_arbiter_calls: 0

This contract is the reviewed stop required by the owner's 2026-08-12
authorization after the truthful terminal result in
[I13 Stage 2 successor terminal evidence](I13_STAGE2_SUCCESSOR_TERMINAL_EVIDENCE.md).
It permits one fresh, stateless worker runtime and Codex session for the same
existing card 12 recovery owner. It does not revive the consumed native resume
wake, replace any identity, or create a general retry path. This document and
its authoritative references must be green, merged and present in the clean
canonical `dev-control-plane` checkout before managed-source implementation.
The reviewed managed source, immutable pin and deterministic installation and
preflight must then complete before any runtime mutation or model call.

The prior arbiter v1, successor and exact-result validation-recovery contracts
remain authoritative for the frozen incident, accepted decision, scope,
review, admission and merge gates except where this contract explicitly adds
the one fresh worker-session recovery generation. Their rows, artifacts,
digests, counters and failed actions remain immutable.

## 1. Exact frozen predecessor and authority

The only eligible predecessor is this complete exact state:

- incident
  `dcp-global-release-2694dbd8b3d4897063603d7a8607ca516aa2f8e05c5a3c39cf56d8e3f18c3c60`,
  incident generation `1`, identity digest
  `2694dbd8b3d4897063603d7a8607ca516aa2f8e05c5a3c39cf56d8e3f18c3c60`;
- successor attempt
  `dcp-arbiter-successor-3c62ea80b56ef94165519d4f01e4c449c320bff22d16b902dd68d4a1a355ea7d`,
  attempt generation `2`, attempt identity digest
  `3c62ea80b56ef94165519d4f01e4c449c320bff22d16b902dd68d4a1a355ea7d`,
  successor input digest
  `aa44c625c940048d5e0266dac23dd4835a1afcf7648116a056758093b67160e6`
  and accepted decision digest
  `237472879b22a8db65c5a3a0715510dc17aee1de93c45eaab45dde538cefb939`;
- original arbiter input/schema/result artifact SHA-256 values
  `355a00609c8ded920bd87b215cea74d3c50213fa4ed8f0b484ea577f73bdbd7d`,
  `8314793a7dbc3f0fc654c28e5936687138883b6e134460fc7204a025102b805f`
  and `d121d012a0b3042f02886fdc0c2aca806f34be64f9e5a3d15e1edf444ff3ae2d`,
  Codex session `019ff23c-7cbf-7ee1-9567-30c6693f95fe` and `11,583`
  tokens;
- successor input/schema/result artifact SHA-256 values
  `fa30d6ea6620e58c36d5163505b2ae80dcdf70b1ee6e2225e0948fe71bdce627`,
  `8779ee3a04b9d3cf0fa2302ced20407f781f5204cd650fe7326c3f93f23925ca`
  and `9b5ff7847db2533e56bdbbc424114e5bea8e5e3c352ad1d029a99deaba05c172`,
  nested merge-tree evidence digest
  `a19c64060d0f41320b6bf652c47ff5c58810ebec0416d003963bc1b4fcdf524f`,
  Codex session `019ff3a1-7f0e-79e2-baa5-cbaa1cc6fc37` and `12,271`
  tokens;
- accepted decision owner `dcp-review-lab-12` and path
  `same_worker_conflict_repair`, with trusted downstream policy `1/1` already
  fixed by the successor contract, current-base SHA
  `b34b31b5443890e69128db2862726950a6bbac0d` and scope/diff/mechanical
  evidence digests
  `1259b9d8569638c986e1dcd56d13f5d8e1e049e5ad2987c94b713bbbc28fd62f`,
  `c81b1e31b06c0045562ac8a2eb13a6cb772483e8c8859b01c3822ad7e630aa62`
  and `1730d612b1f6755c507cd8d6a21871a329e4f5d556361fcef8dbd289d3ab9cc3`;
- successor terminal state exactly `failed/repair_launch_failed`,
  `model_call_count=1`, `recovery_wake_count=1`, empty recovery target SHA and
  empty recovery review-run id;
- native project/task/card/session exactly `dcp-review-lab` /
  `i13-arbiter-b` / `dcp-review-lab-12`, existing worktree
  `/Users/ovlmacbook/Library/Application Support/DCP Orchestrator/data/worktrees/dcp-review-lab/dcp-review-lab-12`,
  branch `ao/dcp-review-lab-12/root`, repository
  `orenvlad-ai/dcp-review-lab`, ready PR #9 at
  `https://github.com/orenvlad-ai/dcp-review-lab/pull/9`, old head
  `d4fcb68051ae113ed497d02151a759800ee85633` and exact current main
  `b34b31b5443890e69128db2862726950a6bbac0d`;
- original task text exactly `DCP synthetic task i13-arbiter-b: Create
  canary/i13-arbiter-conflict.txt with exactly one line: arbiter intent B.
  Commit, push, and open the ready PR required by the profile.`;
- native session activity `idle`, `is_terminated=0`, runtime handle
  `dcp-review-lab-12`, and both native `agent_session_id` and
  `runtime_launch_id` exactly the empty string;
- admission sequence `4`, id
  `dcp-admission-ecb500ad-f9f0-443b-9d73-2c8a6350ce34`, review run
  `ecb500ad-f9f0-443b-9d73-2c8a6350ce34`, review
  `6aab2a2f-beb2-40a2-bcdb-c47ebf304a65`, batch
  `ddeeb966-30a0-4870-8f3f-fda32a4ee568` and retained incident lease
  `dcp-incident-dcp-admission-ecb500ad-f9f0-443b-9d73-2c8a6350ce34`, target
  head `d4fcb68051ae113ed497d02151a759800ee85633` and status/error
  `incident/merge_conflict_or_ambiguity`;
- PR #9 remains OPEN, non-draft, DIRTY/CONFLICTING on the old head with no
  merge commit; its original one approved review and named successful check
  run `31518650351`, job `93869979794` remain immutable and no recovery review
  exists;
- current totals remain six Stage 2 model calls and 132,785 tokens, 11 review
  runs, four admissions, one successor attempt, one accepted successor
  decision, one consumed successor wake and zero successor recovery reviews.

The original arbiter input/schema/result digests, successor
input/schema/result digests, validation-recovery audit row, Codex session ids,
token counts, accepted decision, consumed wake and all prior review/admission
facts remain unchanged. No new arbiter call or decision is required or
authorized. Any changed predecessor fact before the recovery fence is a stop
without a worker model call.

## 2. One additive recovery generation and separate runtime identity

Managed source may add only additive migration
`0057_dcp_review_lab_card12_fresh_worker_recovery.sql`. It creates one exact
subordinate recovery row in the existing `ao.db`. It does not update the
native session's empty `agent_session_id` or `runtime_launch_id`, the successor
row, the incident, admission, old review, old artifacts or migrations
0050-0056. It is not a general worker-attempt, retry, replacement or session
table.

The row is unique for the exact successor attempt and has recovery generation
`1`, identity digest
`d2b7142bc9e5844ba165abe24d3222b3e1a94c3577fba5f6f8d97ec3dbad151b`
and id `dcp-card12-fresh-worker-recovery-` followed by that full digest. The
digest is SHA-256 over this ordered NUL-delimited tuple:

```text
dcp.review-lab.card12-fresh-worker-recovery/v1, recovery generation,
incident id, incident generation, successor attempt id, attempt generation,
attempt identity digest, accepted decision digest, native session id, task id,
project id, repository, canonical worktree path, branch, PR URL, PR number,
old head, exact current main, predecessor status, predecessor error,
old runtime handle id, old agent session id, old runtime launch id,
dcp-i13-stage2-card12-fresh-worker-recovery-v1
```

The two old empty identity values are zero-length tuple members, not omitted
fields. Exact migration eligibility is one `INSERT ... SELECT` over all frozen
predecessor constants. Zero or more than one eligible row fails closed. The
row records independently and auditably:

- recovery id/generation/digest and all predecessor identities;
- status, compare-and-set revision, error and authoritative timestamps;
- model/reasoning, hard token ceiling and worker model-call count `0` or `1`;
- one fresh recovery runtime action id and launch id, plus the fresh Codex
  session id once observed;
- exact sealed input/result/log artifact paths and byte digests;
- old head, current-main SHA, guarded push lease, observed new head and commit;
- fresh review/run/batch ids, check id, admission transition and merge SHA when
  applicable.

The new runtime/action/Codex identities never replace or backfill the native
session columns. Rollback may drop only an empty, unstarted recovery table; it
must refuse after a call fence, launch identity, new head, review or terminal
result exists.

## 3. Exact preconditions before the worker-call fence

Immediately before the one call fence, the trusted daemon must re-read and
prove every Section 1 fact plus all of these current facts:

1. The exact installed source/receipt and running daemon match the separately
   reviewed immutable pin for this contract.
2. There is exactly one recovery row, still `authorized`, with model-call
   count zero, no runtime launch/Codex session/new head/review/merge identity
   and no prior terminal error.
3. No DCP worker, reviewer or arbiter descendant is active. The retained
   `dcp-review-lab-12` pane is either a stable bare shell with no child or is
   provably absent; an ambiguous pane/process probe is a stop.
4. The native session row remains idle, nonterminated and byte-identical in
   all scoped identity fields, including the two empty historical session
   fields. It is not made restorable and its consumed wake is not reset.
5. The canonical linked worktree/private Git dir/common Git dir topology,
   branch, sole origin fetch/push URL and PR identity match exactly. The
   worktree and index are clean at old head
   `d4fcb68051ae113ed497d02151a759800ee85633`; no rebase, merge, sequencer,
   lock or untracked file exists.
6. A fresh fetch proves remote branch head is the same old head and
   `origin/main` is exactly
   `b34b31b5443890e69128db2862726950a6bbac0d`. Fresh provider facts still show
   only PR #9, OPEN, non-draft, same repository/author/base/branch/head and
   DIRTY/CONFLICTING with no merge commit.
7. Model-free history/diff/merge-tree proof shows the only conflict path is
   `canary/i13-arbiter-conflict.txt`, current main contains exactly
   `arbiter intent A\n`, the old candidate contains exactly
   `arbiter intent B\n`, and no other path is in the candidate diff or conflict
   set.
8. The accepted decision, incident/admission global freeze, original review,
   successful old-head check and all counters remain exact; no recovery review,
   new admission claim or terminal merge exists.

The recovery cannot repair a dirty/unknown repository, a moved main/head, an
extra conflict, a foreign process, a changed PR or any partial predecessor. It
persists one terminal failure code and performs no model call in those cases.

## 4. Minimal stateless worker envelope and isolation

The persisted worker input schema is
`dcp.review-lab.card12-fresh-worker-input/v1`, canonical UTF-8 JSON at most
8,192 bytes. It contains only:

1. recovery/incident/successor-decision identity and exact digests;
2. the original task text, its existing approved scope digest and the fixed
   synthetic profile;
3. exact project/card/session/worktree/private/common Git/branch/repository/PR,
   old-head/current-main identities;
4. the exact one-path current-main/candidate bytes and mechanical conflict
   evidence;
5. the only permitted outcome: preserve `arbiter intent A`, add the original
   `arbiter intent B`, and produce exactly
   `arbiter intent A\narbiter intent B\n` on the same branch and PR;
6. one guarded push lease requiring remote branch old head
   `d4fcb68051ae113ed497d02151a759800ee85633`;
7. explicit prohibitions on every other path, task, branch, worktree, PR,
   repository, remote, network destination and control-plane mutation.

The fresh worker receives no old worker transcript or result, reviewer
transcript/verdict, arbiter prompt/result/summary/reasoning, chain-of-thought,
unrelated task/repository, credential, daemon connection, SQLite path, control
command or user Codex configuration. The accepted arbiter decision is reduced
to trusted owner/path/digest constants and is not shown as model reasoning.

The process is one fresh stateless `gpt-5.6-sol` / `xhigh` Codex execution
through `codex exec --ignore-user-config --ephemeral --strict-config`, with
hooks, apps, plugins, MCP, multi-agent and web search disabled. It reuses the
qualified exact synthetic worker workspace-write and network contour only
after all path/Git/branch/remote/profile facts validate. It does not weaken
sandboxing or approvals and receives no arbitrary `--add-dir`. The structured
`features.rollout_budget` configuration is persisted and strictly parsed
model-free before launch with a hard `16,384`-token ceiling. Unsupported budget
enforcement is a stop.

## 5. One worker action and guarded postconditions

The daemon atomically changes the recovery row to `running`, records the hard
budget, fresh action/launch identity and `worker_model_call_count=1` before
process creation. That fence is consumed even if spawn, Codex, network, budget,
Git or result handling later fails. There is no second worker attempt, resume,
fallback, model switch, replacement action or re-arm.

The worker may synchronize only the existing branch from the exact current
main, resolve the one named conflict and produce one new commit/head. Before
allowing its push outcome to advance the recovery, the trusted supervisor must
prove model-free that:

- the new head differs from the old head, has exactly one parent equal to the
  exact current main and is exactly one commit ahead of it;
- its tree differs from current main only at
  `canary/i13-arbiter-conflict.txt`, whose bytes are exactly
  `arbiter intent A\narbiter intent B\n`;
- the worktree/index are clean, there is no merge/rebase/sequencer residue and
  the same branch is checked out;
- exactly one remote mutation occurred through an explicit guarded
  force-with-lease equivalent to
  `refs/heads/ao/dcp-review-lab-12/root:d4fcb68051ae113ed497d02151a759800ee85633`;
- fresh provider facts show the same PR #9 and its exact new head; no new PR,
  branch, card, task, worktree or incident exists.

A zero exit or model claim is not success. Only those trusted Git/provider
facts may persist `worker_succeeded` and the exact new head. Missing,
malformed, late, stale, foreign, dirty, multi-commit or extra-path output is
terminal `BLOCKED`; a remote mutation with unknown outcome is also terminal
and is never retried.

## 6. Exactly one fresh review, admission and terminal merge

Only a trusted `worker_succeeded` transition for the one exact new head may
invoke the existing automatic review trigger. The daemon must atomically fence
the recovery row before launching exactly one fresh, stateless, context-free
reviewer. The reviewer receives only the original approved task/scope, current
authoritative documentation selected by existing deterministic rules, exact
new head/diff and declared checks. It receives no worker transcript, old
review/verdict/findings, arbiter reasoning or recovery history and has the
existing read-only, network-disabled structured-result isolation.

The recovery permits at most one new reviewer model call and one new
`ReviewRun` for the new head. A launch failure, malformed/late/stale/foreign
result, findings, non-approval, reviewer failure or changed head is terminal
without a second reviewer or worker. The old review remains bound only to the
old head.

Only an approved/no-findings verdict bound to the exact new head, exactly one
successful check named `dcp-review-lab`, no unresolved review threads and fresh
provider OPEN/non-draft/same-identity/MERGEABLE/CLEAN facts may
transactionally rebind the original admission sequence 4 and incident to the
new review/head. The existing trusted admission engine must then revalidate
all current facts and may perform exactly one expected-head terminal squash
merge of the same PR #9. The worker and reviewer cannot merge. Provider error
or unknown merge outcome follows the existing fail-closed terminal
reconciliation and never creates a second mutation.

## 7. Restart, duplicate and failure behavior

The deterministic install leaves the application stopped after preflight.
One controlled start crosses the recovery boundary. Restart and replay obey
these rules:

- before the call fence, only the exact unused authorized row may fence and
  launch once; any non-exact row is terminal without a call;
- after the call fence, an exact live supervised descendant is left alone;
  absent, foreign or ambiguous liveness cannot relaunch and ends terminally;
- an exact completed worker with trusted new-head facts may continue
  model-free to the one reviewer fence, but cannot create another worker;
- after the reviewer fence, an exact live reviewer is left alone and an exact
  completed artifact may be consumed once through the existing trusted path;
  no second review is launched for that head;
- old-head, duplicate, late, stale, foreign or malformed worker/reviewer
  artifacts and all replay after a terminal row are inert;
- any unexpected new head, branch, PR, process, row, call, check, review,
  admission claim or merge causes a terminal failure under the global freeze;
  it is not repaired automatically.

After terminal success or failure, a second controlled stop/start must prove
the same recovery row, identities, call counts and terminal result with no
duplicate session, wake, worker, review, admission or merge. A failed worker,
reviewer, check or precondition is a truthful technical `BLOCKED`. No status
uses a timer, watcher, heartbeat, polling/model loop or borrowed model budget.

## 8. Qualification evidence and ceilings

The bounded live additions are:

| Action | New ceiling |
| --- | ---: |
| Fresh card-12 worker runtime/Codex session | 1 |
| Fresh worker model calls | 1 |
| Fresh worker tokens | 16,384 hard maximum |
| Fresh exact-head reviewer model calls | 1 |
| Arbiter calls or decisions | 0 |
| New cards/tasks/worktrees/branches/PRs/incidents | 0 |
| PR #9 terminal merges | 1 |

Terminal evidence must retain byte/digest/counter proof for every old attempt
and record the old empty native-session ids separately from the new recovery
action/launch/Codex session ids. It must report exact worker/reviewer calls and
tokens, old/new head, review/run/check/admission/merge facts, both controlled
starts and zero duplicates. COMPLETE requires the same PR #9 to merge from the
one freshly reviewed exact head. An exhausted budget or failed exact
precondition is BLOCKED and cannot be described as success.

Contract, managed-source implementation, immutable pin/integration and
terminal evidence use separate ready PRs, ordinary protected review, strict
green required checks, resolved conversations and normal merge. The two public
GitHub repositories use standard hosted Actions. No force-push is used for
these governed repositories; the only force-with-lease mutation is the exact
authorized synthetic PR #9 branch action above. The clean canonical
`dev-control-plane` checkout is fast-forwarded after each merge.

## 9. Explicit non-authority

This recovery creates no new card, task, native session, worktree, branch, PR,
incident, arbiter attempt/call/decision, second daemon/database/registry, task
or queue service, watcher, heartbeat, timer, poll, general retry/recovery,
transcript replay, Release Train, deploy, production target, `wb-core`, real
repository, hosted/mobile surface, Telegram, label authority, HumanGate,
updater, telemetry or owner-acceptance synthesis. It never reads or operates
installed Agent Orchestrator or `~/.ao`. Technical completion is not owner
acceptance; only the owner may write `Задача принята`.
