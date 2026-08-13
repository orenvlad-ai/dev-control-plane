# I13 Stage 2 card-12 model-free rebase continuation terminal BLOCKED evidence

evidence_status: technical-blocked
recorded_at: 2026-08-13
installed_source: b22d8961fcc367d414510a5daae53eab19bd2578
continuation_generation: 1

This is the immutable technical handoff for the separately governed card-12
model-free rebase continuation. It records a truthful terminal `BLOCKED`. The
reviewed contract, managed source, pin, deterministic install and preflight all
completed. At the first controlled bundle start, however, native terminal
restoration launched ordinary Codex workers for preserved cards 11 and 12
before the exact continuation could cross its model-free action fence. The
continuation failed closed as `identity_drift`, but the two ordinary worker
provider calls had already occurred. Startup also replaced the preserved
card-12 detached-rebase state with a branch-attached unmerged index and conflict
markers. Both effects violate the zero-worker-call and exact-rebase
preconditions and cannot be undone as evidence.

The bundle was stopped. No continuation action, guarded push, fresh reviewer,
admission rebind or merge occurred. PR #9 remains open on its old head. No
second start, reconstruction, manual completion or new source recovery was
attempted because that would require new authority.

## Governed contracts, source, pins and installation

- Contract PR [#151](https://github.com/orenvlad-ai/dev-control-plane/pull/151)
  retained exact head `48006f82a92d2d4c0def78e85b51f291f4d66c3d`,
  passed baseline run `31671737952` and merged normally at
  `e17fa9080434b5642667392fb06db61cf35f19bd`. It authorizes one exact
  model-free continuation action, zero worker calls, zero arbiter calls and at
  most one fresh reviewer only after a trusted new head.
- Managed-source PR
  [#30](https://github.com/orenvlad-ai/dcp-orchestrator/pull/30) retained exact
  head `579d75211b70e02d0f9e0e35be2dbcd5a7427cc1`, passed source/package run
  `31673494083` and merged normally at
  `a7b5476fb886bcbb6bbd91aa89da17966547b3b8`, tree
  `53525c260b4de1ed749aeb4c89f4e085e433c9bd`. Pin PR
  [#152](https://github.com/orenvlad-ai/dev-control-plane/pull/152) retained
  exact head `cc046432dbbcfc060fb8b0874f28a53a31568586`, passed baseline run
  `31674252447` and merged at
  `3ded30725f5ba2f7ad0192319cfb83b844837c94`.
- Exact source `a7b5476fb886bcbb6bbd91aa89da17966547b3b8` passed deterministic
  build/install/preflight without starting runtime. Its receipt at
  `2026-08-13T06:38:17Z` recorded daemon SHA-256
  `c614d5c571a2d954796bebb93b8740632fc1c78f7737edce3ce8f05a1fd2f646`
  and `app.asar` SHA-256
  `a1206d002b16a8d9a3cb4485c4522b4fe685fdb102840d1d96530a4f11a4ff90`.
- The final pre-runtime proof found that GitHub REST/GraphQL and durable PR
  state retain provider base `dbaf01b05e85ffffa4c843a905e2fe5229eaf0da`
  while current main is
  `b34b31b5443890e69128db2862726950a6bbac0d`; the former is the direct
  ancestor of the latter. No migration or runtime action had occurred.
- Provider-base correction contract PR
  [#153](https://github.com/orenvlad-ai/dev-control-plane/pull/153) retained
  exact head `8652217eb1754bb891c4d94f935cc5bb5d7618ed`, passed baseline run
  `31674877912` and merged at
  `9610bf1a8fa41f631ca5ed336d0d9b0313d7d73f`.
- Corrected managed-source PR
  [#31](https://github.com/orenvlad-ai/dcp-orchestrator/pull/31) retained exact
  head `e3e71ca7e0ee46eb03577bb650c2a95d5d06ecd1`, passed source/package run
  `31675550674` and merged normally at
  `b22d8961fcc367d414510a5daae53eab19bd2578`, tree
  `f10fed7982187a3a963b85c93285e641c41c289d`. Correction pin PR
  [#154](https://github.com/orenvlad-ai/dev-control-plane/pull/154) retained
  exact head `33c69aa98a5a02a8d60c169729d5355cd4ea7d8b`, passed baseline run
  `31676081511` and merged at
  `bd70ca1118a8fe2553b60c1be1d85028864fa4fa`.
- Exact corrected source `b22d8961fcc367d414510a5daae53eab19bd2578`
  then passed deterministic prepare, two complete build/install gate passes and
  final preflight. Both passes included provenance/source gates, generated
  parity, full serial Go tests, frontend typecheck, all 348 selected frontend
  tests and native arm64 packaging. The receipt records install time
  `2026-08-13T07:06:47Z`, daemon SHA-256
  `4fa414aaf9c4a184aa5248647c42e6719c9d6dd92380d8f738d9b2f9cd77f93e`
  and unchanged `app.asar` SHA-256
  `a1206d002b16a8d9a3cb4485c4522b4fe685fdb102840d1d96530a4f11a4ff90`.
  The prior bundle backup is `i12-20260813T070646Z`.

## Exact pre-start identity

- Native card/session `dcp-review-lab-12`, task `i13-arbiter-b`, worktree
  `/Users/ovlmacbook/Library/Application Support/DCP Orchestrator/data/worktrees/dcp-review-lab/dcp-review-lab-12`,
  branch `ao/dcp-review-lab-12/root`, repository
  `orenvlad-ai/dcp-review-lab`, ready PR
  [#9](https://github.com/orenvlad-ai/dcp-review-lab/pull/9), incident
  `dcp-global-release-2694dbd8b3d4897063603d7a8607ca516aa2f8e05c5a3c39cf56d8e3f18c3c60`
  and admission sequence 4 all matched the contract.
- The immutable fresh-worker predecessor remained
  `dcp-card12-fresh-worker-recovery-d2b7142bc9e5844ba165abe24d3222b3e1a94c3577fba5f6f8d97ec3dbad151b`,
  terminal `failed/worker_process_failed`, revision 5, worker/reviewer calls
  `1/0`, with no new head, review or merge. Its input/result/log files retained
  exact sizes, mode `0600` and SHA-256 digests
  `131ab471a0509f4851f94e056998b3a620468a69bdd3b19435d2a225da01d393`,
  `e284aeb37d6fdd7ec86ee3ea6ad2272eee7d4856d5a39eb2894c89dd83d0836b`
  and `8909c2cb81e96beb47414576fb6e1c54e9895fcf34e38e2865d87ca821b46a20`.
- Immediately before start there was no DCP app/daemon, recovery supervisor or
  worker Codex descendant. Remote old head was
  `d4fcb68051ae113ed497d02151a759800ee85633`; remote main was exact
  `b34b31b5443890e69128db2862726950a6bbac0d`. PR #9 was OPEN, ready,
  CONFLICTING/DIRTY, with only the old successful named check.
- The worktree was detached at exact current main in the preserved one-commit
  rebase. `REBASE_HEAD` and `ORIG_HEAD` were the old head, the sole unmerged
  path was `AA canary/i13-arbiter-conflict.txt`, and the already written
  two-line resolution digest was
  `2a5da25a78ff8bcd9aff4493f195eaefecbc70c3d4db8902dda468ccf69e5e46`.

## Fail-closed row and unexpected native worker launches

- First start at `2026-08-13T07:08:50Z` ran migrations 0059 and 0060 once.
  They created exactly one continuation row and one provider-base correction
  row with their reviewed immutable identities.
- The continuation became terminal `failed/identity_drift`, revision 1, at
  `2026-08-13 07:08:50.687876 +0000 UTC`. Its trusted counters are worker 0,
  arbiter 0, model-free action 0 and reviewer 0. It has no new head, review run,
  check or merge SHA. Durable counts remained 17 sessions, 11 review runs,
  four admissions, one incident, one successor, one fresh recovery and one
  continuation.
- Concurrent native terminal restoration created tmux terminals for preserved
  cards 11 and 12 and invoked their stored ordinary worker commands. This was
  outside the exact continuation fence. Card 11 opened Codex thread
  `019ff9f3-cad3-73c1-bcee-293efe857349` and reported 33,238 tokens. Card 12
  opened Codex thread `019ff9f3-cbe6-71e2-8636-ea6259a7e7d1` and reported
  33,573 tokens. The retained pane evidence SHA-256 values are respectively
  `57e04e40cc3456171f9d640a942f7d0dfa2cb6d924a6f8c5dfb9c13d07a810a3`
  and `baef38e073b4b8da13cac21a052ec92b2c4107c3eebf7e752b0a136adcba63dc`.
- Both ordinary workers recognized existing provider outcomes and created no
  commit, push or replacement PR. Card 11 remains clean at exact local/remote
  head `2166d10911f06e14a525267975393c0be03727d0`. Card 12 did not stage,
  commit or push. No reviewer or arbiter was launched.
- The startup path nevertheless changed card 12 before the worker inspected it:
  the worktree became attached to the old branch/head, rebase metadata
  disappeared, the sole path became `UU`, and its working bytes reverted to
  conflict markers with digest
  `5850bba009db75bf47ff88aef2d2cecbdba89c68967f51a8cdb60f48e968dc1a`.
  This is not the contract's preserved detached rebase or permitted resolved
  bytes and was not reconstructed.

## Provider, process and model accounting

- The bundle was terminated after the failure was identified. No installed
  app, daemon, supervisor or `/opt/homebrew/bin/codex` child remains. The two
  retained tmux panes contain only idle shells and are preserved as evidence.
- PR #9 remains OPEN and ready at old remote head
  `d4fcb68051ae113ed497d02151a759800ee85633`, base snapshot
  `dbaf01b05e85ffffa4c843a905e2fe5229eaf0da`, CONFLICTING/DIRTY, with no
  merge commit. Remote main remains
  `b34b31b5443890e69128db2862726950a6bbac0d`. The sole card-12 review run is
  still the old complete/approved structured run on the old head; no fresh run
  exists.
- This continuation consumed zero trusted continuation actions, zero fresh
  reviewers and zero new arbiters, but bundle startup caused two actual
  ordinary worker calls. Their exact reported total is 66,811 tokens. The
  prior Stage 2 accounting was seven actual calls with 132,785 exactly recorded
  tokens plus one failed worker call bounded by 16,384 tokens. The truthful new
  aggregate is nine actual calls, 199,596 exactly recorded tokens plus that one
  prior bounded failed call, for a ceiling of 215,980 tokens.

Status is `BLOCKED`. Not done: the retained rebase was not continued, no new
head or fresh check exists, no context-free reviewer ran, admission sequence 4
was not rebound, PR #9 did not merge and no restart/deduplication success proof
is possible. The zero-worker-call contract has been irreversibly exceeded and
the exact local rebase evidence has drifted. Any restart, model-free
reconstruction, second continuation, fresh reviewer or merge now requires new
owner authority and a separately reviewed contract; none is inferred here.
Production, `wb-core`, secrets, Telegram, other repositories and foreign PRs
were not changed.
