# I13 Stage 2 card-12 exact REBASE_HEAD finalization contract

contract_status: owner-approved-pre-runtime-model-free
contract_version: dcp-i13-stage2-card12-rebase-head-finalization-v1
contract_revision: 1
recorded_at: 2026-08-13
dev_control_plane_baseline: 3985d88633ec4b801612c2c5af28d75f893e7e82
managed_source_baseline: 04a967c26499a482fbff9a204bab046d79d2a2e2
managed_source_tree: fedee6276e8ce4a492d3c298aaf4bf843179c8bc
finalization_generation: 1
finalization_identity_digest: a073fb250a5343cffa210614247c76a080bb9e7db6a6cd8d052909611a75e50b
additional_worker_model_calls: 0
additional_arbiter_model_calls: 0
fresh_reviewer_model_call_ceiling: 1

This contract records the owner's separate 2026-08-13 authorization after the
truthful terminal result in
[card-12 cold-start recovery terminal evidence](I13_STAGE2_CARD12_COLD_START_QUARANTINED_RECOVERY_TERMINAL_EVIDENCE.md).
The cold-start recovery row, its action fence and its artifacts are consumed and
immutable. This contract does not re-arm that row. It permits one new,
subordinate, daemon-owned finalization generation only for the already existing
clean local commit whose reconstruction succeeded before the predecessor
misclassified Git's regular `REBASE_HEAD` pseudoref as active operation residue.

This document must pass ordinary review, merge and be present in the clean
canonical `dev-control-plane` checkout before managed-source implementation.
One separate reviewed managed-source PR, one separate immutable pin/install-
guard PR and deterministic exact build/install/preflight must complete before
runtime starts. The existing daemon and SQLite remain the only runtime and
state authorities.

## 1. Immutable predecessor and actual model accounting

All earlier rows, artifacts, calls and counters remain immutable. In
particular:

- Cold-start recovery
  `dcp-card12-cold-start-recovery-087176dbe56428dc97a99823a94daa4687c41b15c14a08de21db2c6c602f0f2f`
  remains terminal `failed/model_free_action_failed`, revision `7`, with
  worker/arbiter/model-free-action/reviewer counts `0/0/1/0`.
- Its `local_ref_before` remains the old head, while `local_ref_after`,
  `new_head`, `new_commit`, `provider_new_head`, all recovery-review fields and
  `merge_commit_sha` remain empty. No successor may backfill them.
- Its immutable backup path remains
  `/Users/ovlmacbook/Library/Application Support/DCP Orchestrator/evidence/dcp-card12-cold-start-recovery/dcp-card12-cold-start-recovery-087176dbe56428dc97a99823a94daa4687c41b15c14a08de21db2c6c602f0f2f`
  with manifest/row digest
  `82d0e5834375c380069e7d48a7fdb2066371670d92733ce59545718469a4f3dd`.
- The two earlier zero-call direct-path audits, the terminal continuation, the
  failed fresh-worker row, the accepted arbiter successor decision and consumed
  wake remain unchanged.
- Admission sequence `3` remains succeeded at merge SHA
  `b34b31b5443890e69128db2862726950a6bbac0d`. Admission sequence `4`, id
  `dcp-admission-ecb500ad-f9f0-443b-9d73-2c8a6350ce34`, remains
  `incident/merge_conflict_or_ambiguity` on the old head with its retained
  incident lease and no merge SHA until the new exact review is admitted.
- The unauthorized card-11/card-12 native restoration calls remain immutable:
  threads `019ff9f3-cad3-73c1-bcee-293efe857349` and
  `019ff9f3-cbe6-71e2-8636-ea6259a7e7d1`, with `33,238` and `33,573`
  reported tokens, respectively. Their exact total is `66,811` tokens.

The truthful starting Stage 2 aggregate remains nine actual calls with
`199,596` exactly reported tokens plus the earlier failed fresh-worker call
bounded by `16,384` tokens, for a ceiling of `215,980`. This finalization adds
no worker or arbiter call. Its only possible model use is one fresh
context-free reviewer after the exact retained candidate is pushed and
provider-confirmed.

## 2. Exact retained candidate and repository identity

The only eligible identities are:

- project `dcp-review-lab`, card/session `dcp-review-lab-12`, task
  `i13-arbiter-b`;
- repository `orenvlad-ai/dcp-review-lab`;
- worktree
  `/Users/ovlmacbook/Library/Application Support/DCP Orchestrator/data/worktrees/dcp-review-lab/dcp-review-lab-12`;
- branch `ao/dcp-review-lab-12/root`, push ref
  `refs/heads/ao/dcp-review-lab-12/root` and ready PR
  `https://github.com/orenvlad-ai/dcp-review-lab/pull/9`;
- incident
  `dcp-global-release-2694dbd8b3d4897063603d7a8607ca516aa2f8e05c5a3c39cf56d8e3f18c3c60`;
- remote PR head and exact force-with-lease value
  `d4fcb68051ae113ed497d02151a759800ee85633`;
- exact current main `b34b31b5443890e69128db2862726950a6bbac0d`;
- provider PR-base snapshot
  `dbaf01b05e85ffffa4c843a905e2fe5229eaf0da`, proven an ancestor of current
  main; and
- retained local candidate
  `4de6ff1a0b80223a9b32a05ba68cf0b665296081`.

The same existing branch and attached worktree point at the retained candidate.
Its sole parent is exact current main. It is exactly one commit ahead, has
subject `chore: add i13 arbiter intent B canary`, author
`Влад Сагитов <ovlmacbook@oVl-MacBook-Pro.local>` and author date
`2026-08-11T22:38:48+05:00`. Its tree differs from current main only by
`M canary/i13-arbiter-conflict.txt`; the file is exactly
`arbiter intent A\narbiter intent B\n`, SHA-256
`2a5da25a78ff8bcd9aff4493f195eaefecbc70c3d4db8902dda468ccf69e5e46`,
and Git blob `80a658c4cfc3ffda5786da316bc0bd10ffb1834f`. The binary full-index
current-main-to-candidate diff SHA-256 is
`b415f3cc21e091afc82e8fbf5fa1a6f0e64ec42465ea8702efe4c681f47295f7`.

The index and worktree are clean. The complete NUL-terminated porcelain-v1
status is empty and therefore has SHA-256
`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.
The local branch's configured remote may report ordinary ahead/behind counts;
only the exact local and remote commit identities above are authoritative.

## 3. Exact inert pseudoref semantics

The only accepted post-rebase pseudorefs are regular, non-symlink mode-0644
files in the exact card-12 private Git directory:

- `REBASE_HEAD`, 41 bytes, containing exactly the old head plus one newline;
- `ORIG_HEAD`, 41 bytes, containing exactly the old head plus one newline.

Each file has SHA-256
`657c15026f6e8f51e96e6ff6c2ae94a5d6f4031ec95f07030b52f6226cc4d810`.
No `rebase-apply`, `rebase-merge`, `MERGE_HEAD`, `AUTO_MERGE`,
`CHERRY_PICK_HEAD`, `REVERT_HEAD`, `BISECT_LOG`, `sequencer`, index/ref lock or
other active operation state exists. There is no active Git, worker, reviewer,
arbiter or recovery mutator.

In exactly this complete retained-candidate state, regular `REBASE_HEAD` is
historical commit evidence rather than proof of an active rebase. The managed
implementation may recognize that one conjunction only. It must not remove,
rewrite or synthesize either pseudoref, and it must not weaken the general
operation-residue guards used by the predecessor reconstruction, any ordinary
worker, reviewer, worktree or repository. A missing, changed, additional,
non-regular or differently located pseudoref remains a terminal mismatch.

## 4. One additive finalization row

Managed source may add only additive migration
`0064_dcp_card12_rebase_head_finalization.sql`. It creates one subordinate
finalization row in the existing `ao.db`; it neither edits an earlier migration
nor updates the failed cold-start recovery row or any predecessor.

The row id is `dcp-card12-rebase-head-finalization-` followed by identity digest
`a073fb250a5343cffa210614247c76a080bb9e7db6a6cd8d052909611a75e50b`.
That digest is SHA-256 over the ordered NUL-delimited tuple:

```text
dcp.review-lab.card12-rebase-head-finalization/v1,
finalization generation 1,
predecessor recovery id/status/error/revision/worker/arbiter/action/reviewer counts,
predecessor backup path and digest,
incident and admission ids,
card/session/task/project/repository/worktree/branch/PR identities,
old head, retained candidate, current main and provider base,
conflict path, resolved-file digest and current-main-to-candidate diff digest,
REBASE_HEAD name/digest, ORIG_HEAD name/digest,
card-11/card-12 quarantine verification counts,
the two unauthorized worker token counts,
dcp-i13-stage2-card12-rebase-head-finalization-v1
```

One exact `INSERT ... SELECT` over the terminal predecessor and quarantine
facts creates the row. The migration-side stopped baseline requires exactly
two quarantine rows at verification counts `4/4`; zero or multiple matches
fail closed. Ordinary databases without this exact governed contour remain
compatible and create no finalization row.

The new row separately records status/revision, one model-free finalization
action constrained to `0` or `1`, one reviewer count constrained to `0` or
`1`, predecessor/backup/pseudoref/candidate digests, the old-head push lease,
provider-confirmed head, fresh review/check identities, admission rebind and
terminal merge SHA. Rollback may remove only an empty unstarted row and refuses
after action, push, review, rebind or terminal result.

## 5. Quarantine, install and pre-action proof

The existing pre-restoration quarantine remains mandatory and unchanged. On
the first new bundle start it must validate/touch both exact rows before runtime
construction, advancing their verification counts from `4/4` to `5/5` while
keeping cards 11/12 as bare shells with zero descendants. A controlled
post-terminal restart must advance the same rows once more without creating a
worker. Missing, ambiguous or unreadable quarantine state aborts startup before
session restoration.

Before the finalization action fence, the trusted daemon must also prove:

1. installed receipt, running daemon and separately merged immutable pin all
   identify the exact reviewed implementation;
2. the predecessor row, both direct-path audits, sealed backup and every
   immutable identity in Sections 1-4 are exact;
3. the sole finalization row is `authorized`, revision zero, with action and
   reviewer counts zero and empty downstream fields;
4. the canonical worktree/private/common Git topology, branch ownership,
   origin fetch/push URLs and single PR identity are exact;
5. the complete retained-candidate topology, bytes, status, pseudoref files and
   absence of any additional operation residue match Sections 2-3;
6. both governed panes are absent or stable bare shells and there is no worker,
   reviewer, arbiter, recovery supervisor, Codex descendant or foreign mutator;
7. fresh authenticated read-only Git transport proves remote branch still at
   the old head and remote current main unchanged; and
8. fresh provider facts prove the same OPEN, non-draft, unmerged PR, historical
   provider base, repository/author/branch and old head.

Every SQLite, backup, process, path, local/ref, provider, ancestry, byte, mode,
digest or count mismatch fails before a repository write. A changed but
apparently equivalent candidate is not guessed around.

## 6. One model-free adoption and guarded push

After all preconditions pass, one compare-and-set moves only the finalization
row from `authorized` to `running`, sets
`model_free_finalization_action_count=1` and persists action start before the
push. The fence is consumed even if transport, provider confirmation or later
handling fails.

The action performs no reconstruction, rebase, stage, commit, amend, checkout,
reset, clean, branch move, pseudoref delete or other local Git write. It
revalidates the retained candidate and the exact remote old-head/current-main
facts, then issues exactly one push equivalent to:

```text
git -c credential.helper=!/opt/homebrew/Cellar/gh/2.87.2/bin/gh auth git-credential \
  push --force-with-lease=refs/heads/ao/dcp-review-lab-12/root:d4fcb68051ae113ed497d02151a759800ee85633 \
  origin HEAD:refs/heads/ao/dcp-review-lab-12/root
```

No other refspec, branch, remote, repository mutation or push retry is allowed.
A rejected or unknown push outcome is terminal. If the exact push succeeds but
a later observation is interrupted, startup may only prove remote/provider head
`4de6ff1a...` and persist that already-completed result model-free; it cannot
push again. Only fresh Git and provider facts proving PR #9 now owns exactly the
retained candidate, with current main unchanged and the exact one-commit/
one-path content, may move the row to `candidate_ready`.

## 7. One fresh review, admission and merge

Only the persisted retained candidate may consume the finalization row's one
reviewer fence and enter the existing stock automatic review engine. The
reviewer is fresh, stateless, context-free, read-only, network-disabled and
schema-bound. It receives only the original approved task/scope,
deterministically selected authoritative documentation and the exact new
head/diff/checks. It receives no worker transcript, old review, arbiter
reasoning, recovery artifacts, daemon credential or control channel.

The old approved review and old successful check remain bound only to old head
`d4fcb...` and cannot be reused. A launch/result/process failure, malformed,
late, stale or foreign identity, findings, non-approval or changed head is
terminal with no second reviewer. Progress requires all of:

- one new structured `approved` verdict with empty findings for exact head
  `4de6ff1a...`;
- exactly one fresh successful check named `dcp-review-lab` for that head;
- no unresolved review thread; and
- fresh exact OPEN, non-draft, same-repository/head/base facts with provider
  `MERGEABLE` and `CLEAN`.

The trusted daemon may then atomically rebind only admission sequence 4 from
the old run/head to the new run/head while retaining the same task, session,
incident and FIFO identity. The existing admission engine revalidates all
current facts and may issue one expected-head squash merge of only PR #9.
Neither the finalizer nor reviewer may merge. Provider ambiguity remains
one-shot and fail-closed.

## 8. Tests, crash boundaries and restart proof

Managed-source tests must cover at least:

- exact migration eligibility, immutable predecessor proof and rollback refusal
  after each fence;
- quarantine establishment before any runtime construction, zero card-11/
  card-12 worker launch on first start and restart, and stock behavior for an
  unrelated eligible session;
- exact retained candidate, clean index/worktree, parent/subject/author/date,
  one-path bytes and remote/provider acceptance;
- exact regular `REBASE_HEAD`/`ORIG_HEAD` acceptance only in the complete
  allowed conjunction and rejection of every changed mode/byte/path, active
  rebase directory, sequencer, merge/cherry-pick/bisect state, lock, extra path
  or mutator;
- preservation of the general predecessor residue guard;
- zero reconstruction/local-Git writes, one finalization fence, exactly one
  old-head force-with-lease push and fail-closed rejected/unknown outcomes;
- crash boundaries before/after action fence, remote push, provider
  confirmation, reviewer fence, admission rebind and merge;
- one fresh reviewer, old-head verdict/check rejection, admission rebind,
  terminal merge and restart deduplication.

After terminal success or failure, one controlled stop/start must preserve the
quarantine, predecessor/finalization rows, sealed backup, all identities and
counts without another worker, arbiter, finalization action, push, reviewer,
admission claim or merge. Terminal evidence uses a separate reviewed PR and
includes all contract/source/pin/evidence PRs and merge SHAs, CI, installed
receipt, exact before/after state, pseudoref proof, quarantine proof, guarded
push, fresh review/check/admission/merge facts, full model/token accounting and
restart deduplication.

`COMPLETE` requires PR #9 merged from exact retained head `4de6ff1a...` after
the one fresh review. Any mismatch, worker/arbiter launch, exhausted one-shot
fence, second reviewer or unknown mutation is truthful `BLOCKED`.

## 9. Required delivery order and exact ceilings

The delivery order is strict:

1. merge this contract through one ordinary ready `dev-control-plane` PR;
2. merge one minimal managed-source PR with additive migration, trusted
   finalizer and exact tests after exact-head semantic/security review and green
   `source`/`package` checks;
3. merge one separate pin/install-guard PR with green baseline, then
   fast-forward the clean canonical checkout;
4. run deterministic `prepare`, `build`, `install` and stopped `preflight`;
5. complete one final read-only prestart proof, then make one live attempt; and
6. record the terminal result and restart proof in a separate reviewed evidence
   PR.

| Action | New ceiling |
| --- | ---: |
| Card-12 retained-candidate finalization actions | 1 |
| Local rebase/reconstruction/stage/commit/ref/pseudoref actions | 0 |
| Worker model calls | 0 |
| Arbiter model calls or decisions | 0 |
| Fresh exact-head reviewer calls | 1 |
| New cards/tasks/native sessions/worktrees/branches/PRs/incidents | 0 |
| Guarded pushes of the existing PR #9 branch | 1 |
| PR #9 terminal merges | 1 |

This contract creates no replacement identity, worker/arbiter retry,
transcript replay, second daemon/database/registry, queue, scheduler, watcher,
heartbeat, timer, polling/model loop, general Git repair API, manual Run Review,
manual push/rebase/merge, Release Train, deploy, production target, `wb-core`,
other repository, secret export, Telegram, hosted/mobile surface, HumanGate or
owner-acceptance synthesis. It never reads or operates installed Agent
Orchestrator or `~/.ao`. Technical completion is not owner acceptance; only
the owner may write `Задача принята`.
