# I13 Stage 2 card-12 fresh worker recovery terminal BLOCKED evidence

evidence_status: technical-blocked
recorded_at: 2026-08-12
installed_source: 75a14431a3433f581755f2e0ec096814e3e9ecb1
recovery_generation: 1

This is the immutable technical handoff evidence for the separately governed
card-12 fresh worker-session recovery. It records a truthful terminal
`BLOCKED`, not owner acceptance. The sole authorized stateless worker call
started against the exact existing card, worktree, branch and PR, reached the
one proven add/add conflict and exhausted its hard 16,384-token rollout budget
after writing the permitted resolution locally but before a commit or guarded
push. The trusted supervisor failed closed. No new head, fresh reviewer,
admission rebind or merge exists, and no second worker attempt is authorized.

The earlier [Stage 2 successor terminal BLOCKED evidence](I13_STAGE2_SUCCESSOR_TERMINAL_EVIDENCE.md)
and all predecessor rows and artifacts remain unchanged. This record does not
reset the consumed native wake or alter the accepted successor decision.

## Governed contract, source, pins and installation

- Contract PR [#147](https://github.com/orenvlad-ai/dev-control-plane/pull/147)
  retained exact head `201ae3ad68078fb3289bf3bed16700ef175ef575` and
  merged normally at `2a174899ae72bf1db548c3b2f172d963488191f1`.
  Its [fresh worker-session recovery contract](I13_STAGE2_CARD12_FRESH_WORKER_RECOVERY_CONTRACT.md)
  fixes recovery identity digest
  `d2b7142bc9e5844ba165abe24d3222b3e1a94c3577fba5f6f8d97ec3dbad151b`,
  one worker call under a hard 16,384-token ceiling, at most one fresh
  reviewer, and zero new arbiter calls.
- Managed-source PR
  [#28](https://github.com/orenvlad-ai/dcp-orchestrator/pull/28) passed required
  source/package CI run `31591783582` and merged normally at
  `fbcf4929f9192f7cce9c5097b0bc6a449d28e663`, tree
  `2ce917e525690d0cd05e060b552dc8bd072b8a15`. Pin PR
  [#148](https://github.com/orenvlad-ai/dev-control-plane/pull/148) retained
  exact head `237d418ebe8939f6f93f8d179ddf7d8a2d8aef3b`, passed baseline run
  `31594416423` and merged at
  `50ade9d7f202dc432fb652c2b770e0638e768e93`.
- Exact source `fbcf4929f9192f7cce9c5097b0bc6a449d28e663` was
  deterministically prepared, built, installed and preflighted. Its first
  controlled start created the one generation-1 recovery row but failed closed
  before the call fence at `preflight_failed/identity_drift`: worker/reviewer
  calls remained `0/0`, and no launch, Codex session, token, input, result,
  head, review or merge was recorded. Model-free inspection proved that the
  exact conflict path is `M`, not `A`, from current main.
- Managed-source correction PR
  [#29](https://github.com/orenvlad-ai/dcp-orchestrator/pull/29) passed required
  source/package CI run `31595652979` and merged normally at
  `75a14431a3433f581755f2e0ec096814e3e9ecb1`, tree
  `a993819f30776ca595d5687f098ec00b98d67ba2`. Migration 0058 preserves the
  zero-call failure in one separate audit row and re-arms only that still-unused
  exact recovery row; the code change corrects only the exact path-status
  assertion.
- Correction pin PR
  [#149](https://github.com/orenvlad-ai/dev-control-plane/pull/149) retained
  exact head `74a12daaaece1a9e136f538ab60de27c010ecbf5`, passed baseline run
  `31596234569` and merged normally at
  `60acb70fd1d4ca603286f6930e899116317395d0`. The clean canonical checkout
  fast-forwarded to that merge before installation.
- Deterministic `prepare`, `build`, `install` and `preflight` then succeeded for
  exact source `75a14431a3433f581755f2e0ec096814e3e9ecb1`. Both build passes ran
  the source/provenance and generated-parity gates, complete serial Go tests,
  frontend typecheck and all 348 frontend tests before native arm64 packaging.
  The prior bundle backup is `i12-20260812T122948Z`.
- The install receipt records tree
  `a993819f30776ca595d5687f098ec00b98d67ba2`, install time
  `2026-08-12T12:29:49Z`, daemon SHA-256
  `68acea7d790ec813c85a9acadde2b8870c85c31c0669d4b36d847b021db3afe5`
  and `app.asar` SHA-256
  `a1206d002b16a8d9a3cb4485c4522b4fe685fdb102840d1d96530a4f11a4ff90`.

No recovery runtime or model action occurred before the contract, source and
pin merges plus exact deterministic installation and preflight.

## Exact preserved identity and predecessor

- The recovery retained native card/session `dcp-review-lab-12`, task
  `i13-arbiter-b`, project `dcp-review-lab`, worktree
  `/Users/ovlmacbook/Library/Application Support/DCP Orchestrator/data/worktrees/dcp-review-lab/dcp-review-lab-12`,
  branch `ao/dcp-review-lab-12/root`, repository
  `orenvlad-ai/dcp-review-lab`, and ready PR
  [#9](https://github.com/orenvlad-ai/dcp-review-lab/pull/9).
- The same incident remains
  `dcp-global-release-2694dbd8b3d4897063603d7a8607ca516aa2f8e05c5a3c39cf56d8e3f18c3c60`.
  The same generation-2 successor remains
  `dcp-arbiter-successor-3c62ea80b56ef94165519d4f01e4c449c320bff22d16b902dd68d4a1a355ea7d`,
  with accepted decision digest
  `237472879b22a8db65c5a3a0715510dc17aee1de93c45eaab45dde538cefb939`,
  owner `dcp-review-lab-12` and path `same_worker_conflict_repair`.
- The predecessor row remains terminal `failed/repair_launch_failed`, with
  `model_call_count=1`, `recovery_wake_count=1`, no recovery review and no
  recovery target head. Native card 12 remains idle and non-terminated with
  both `agent_session_id` and `runtime_launch_id` empty.
- Admission sequence 4 remains
  `dcp-admission-ecb500ad-f9f0-443b-9d73-2c8a6350ce34`, status `incident`,
  lease `dcp-incident-dcp-admission-ecb500ad-f9f0-443b-9d73-2c8a6350ce34`,
  error `merge_conflict_or_ambiguity`, target head
  `d4fcb68051ae113ed497d02151a759800ee85633`, zero refresh wakes and no merge
  SHA. Its original review run remains the sole card-12 run and is
  complete/approved on that old head through `structured_dcp_v1`.
- Post-terminal SHA-256 verification preserved the original arbiter
  input/schema/result at
  `355a00609c8ded920bd87b215cea74d3c50213fa4ed8f0b484ea577f73bdbd7d`,
  `8314793a7dbc3f0fc654c28e5936687138883b6e134460fc7204a025102b805f`
  and `d121d012a0b3042f02886fdc0c2aca806f34be64f9e5a3d15e1edf444ff3ae2d`.
  The successor input/schema/result also remain
  `fa30d6ea6620e58c36d5163505b2ae80dcdf70b1ee6e2225e0948fe71bdce627`,
  `8779ee3a04b9d3cf0fa2302ced20407f781f5204cd650fe7326c3f93f23925ca`
  and `9b5ff7847db2533e56bdbbc424114e5bea8e5e3c352ad1d029a99deaba05c172`.
  No arbiter row, call, decision, wake or artifact changed.

## One fresh worker call and fail-closed result

- Migration 0058 wrote exactly one
  `dcp_card12_fresh_worker_preflight_recovery` audit row for the immutable
  `preflight_failed/identity_drift` predecessor, its `0/0` counters and empty
  launch/session/token/artifact/head/review/merge fields. It then re-armed only
  recovery generation 1 at `2026-08-12 12:30:07`.
- The exact recovery row is
  `dcp-card12-fresh-worker-recovery-d2b7142bc9e5844ba165abe24d3222b3e1a94c3577fba5f6f8d97ec3dbad151b`.
  It crossed the worker fence once with that same value as the separate
  runtime action and launch identity. The bounded semantic input digest is
  `1b79923f68e0a53414579f059a1984fbcdae7aea4593d86c7fa4ae62027114bd`;
  the immutable 3,143-byte input file SHA-256 is
  `131ab471a0509f4851f94e056998b3a620468a69bdd3b19435d2a225da01d393`.
- The one `gpt-5.6-sol`/`xhigh` stateless call created fresh Codex thread
  `019ff5f3-c655-7ea2-9213-6e137f148285`. It received only the structured
  original task, exact identity/current-main/old-head/conflict bytes, one
  permitted path and exact guarded lease; no prior worker transcript or
  arbiter reasoning was supplied.
- The worker proved exact branch and old head, current-main bytes `arbiter
  intent A` and candidate bytes `arbiter intent B`. It began the exact rebase
  onto `b34b31b5443890e69128db2862726950a6bbac0d`, reached the expected add/add
  conflict and wrote the permitted two-line resolution locally. Before it
  could stage, continue, commit or execute the one guarded push, Codex emitted
  `shared rollout token budget exhausted` and `turn.failed`.
- The immutable 541-byte supervisor result records `started=true`,
  `exitCode=1`, the fresh Codex thread, and `tokenCount=0` because the failed
  turn emitted no terminal usage record. Its SHA-256 is
  `e284aeb37d6fdd7ec86ee3ea6ad2272eee7d4856d5a39eb2894c89dd83d0836b`.
  The 15-line, non-overflow event log SHA-256 is
  `8909c2cb81e96beb47414576fb6e1c54e9895fcf34e38e2865d87ca821b46a20`.
  The explicit exhaustion event proves the hard 16,384-token ceiling stopped
  the call; `tokenCount=0` must not be misread as zero inference usage.
- The trusted row became terminal `failed/worker_process_failed`, revision 5,
  at `2026-08-12 12:32:25.015963 +0000 UTC`. It retains
  `worker_model_call_count=1`, `reviewer_model_call_count=0`, the one launch
  identity and input digest, with no new commit/head, recovery review/check or
  merge SHA. The separate immutable result/log files retain the failed fresh
  Codex identity even though no successful worker result was admitted into the
  row.

## Git, provider and restart proof

- The local worktree truthfully remains stopped at detached current-main HEAD
  `b34b31b5443890e69128db2862726950a6bbac0d` in the unfinished one-commit
  rebase. Its sole unmerged index path is
  `canary/i13-arbiter-conflict.txt` (`AA`); the working file has exactly the
  permitted two lines. This incomplete local state is retained as failure
  evidence and was not committed, pushed or manually completed.
- Fresh provider facts after failure keep PR #9 ready and `OPEN`, head branch
  `ao/dcp-review-lab-12/root`, exact remote head
  `d4fcb68051ae113ed497d02151a759800ee85633`, `CONFLICTING` and `DIRTY`, with
  no merge commit. The old named `dcp-review-lab` check remains successful on
  the old head; it is not a recovery check and cannot admit a new head.
- Before the terminal restart, counts were one fresh recovery row, one
  preflight-recovery audit row, 17 native sessions, 11 review runs, four
  admissions, one incident arbiter row and one successor row. The fresh row
  held worker/reviewer calls `1/0`; the successor held model/wake counts `1/1`.
- A controlled exact app/daemon stop and restart completed after the worker
  process exited. The post-restart daemon started at
  `2026-08-12T12:33:47.865318Z`. The terminal recovery status, revision,
  timestamps, call counts and empty downstream fields remained identical.
  All row counts above remained unchanged. No recovery supervisor or Codex
  process reappeared; the retained recovery tmux pane contains only a bare
  `zsh` with no model child.
- Thus the recovery has exactly one worker call, zero fresh reviewer calls,
  zero new arbiter calls, zero new native sessions, zero new review/admission
  rows, zero pushes, zero new remote heads and zero merges. Restart caused no
  duplicate session, wake, review, admission or merge activity.

## Model accounting and terminal state

The immutable predecessor aggregate remains six Stage 2 model calls and
132,785 exact recorded tokens. This recovery added exactly one worker model
call and no reviewer or arbiter call. The failed Codex turn did not return a
usage total, so the trusted supervisor artifact records `tokenCount=0` while
the event log proves the configured hard 16,384-token rollout budget was
exhausted. The truthful aggregate is therefore seven actual Stage 2 calls,
132,785 previously recorded tokens plus one failed call bounded above by
16,384 additional tokens; the whole Stage 2 contour cannot exceed 149,169
tokens. No exact smaller total is claimed without provider usage evidence.

Status is `BLOCKED`. Not done: there is no repaired commit or exact new head,
no fresh context-free review/check, no admission rebind, and PR #9 did not
merge. The sole worker budget is consumed, and its local uncommitted resolution
cannot be admitted or pushed without a forbidden second worker/manual bypass.
Continuing requires new owner authority and a separately reviewed contract;
none is inferred here. Production, `wb-core`, other repositories, secrets,
labels, Telegram, hosted UI, owner acceptance and production Release Train were
untouched. Technical completion and owner acceptance are not claimed.
