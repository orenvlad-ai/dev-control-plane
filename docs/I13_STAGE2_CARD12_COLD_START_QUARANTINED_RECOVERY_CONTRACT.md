# I13 Stage 2 card-12 cold-start quarantined recovery contract

contract_status: owner-approved-pre-runtime-model-free
contract_version: dcp-i13-stage2-card12-cold-start-quarantined-recovery-v1
contract_revision: 1
recorded_at: 2026-08-13
dev_control_plane_baseline: cc8e71c236ecd7869c35dae7435beee8e07f90b8e
managed_source_baseline: b22d8961fcc367d414510a5daae53eab19bd2578
startup_fence_generation: 1
recovery_generation: 1
recovery_identity_digest: 087176dbe56428dc97a99823a94daa4687c41b15c14a08de21db2c6c602f0f2f
additional_worker_model_calls: 0
additional_arbiter_model_calls: 0
fresh_reviewer_model_call_ceiling: 1

This contract records the owner's separate 2026-08-13 authorization after the
truthful terminal result in
[card-12 model-free continuation terminal evidence](I13_STAGE2_CARD12_MODEL_FREE_REBASE_CONTINUATION_TERMINAL_EVIDENCE.md).
It supersedes, rather than reuses, the earlier zero-worker-call continuation
authority. That authority is consumed and immutable because cold startup
launched two ordinary workers outside its trusted counters. This new cycle
preserves those calls and their 66,811 reported tokens as failure evidence,
then permits one startup-order correction and one new daemon-owned, model-free
recovery generation for only the exact post-drift card-12 state.

This document must pass ordinary review, merge and be present in the clean
canonical `dev-control-plane` checkout before managed-source implementation.
One separate reviewed managed-source PR, one separate immutable pin/install-
guard PR and deterministic exact build/install/preflight must all complete
before runtime starts. The existing daemon and SQLite remain the only runtime
and state authorities.

## 1. Immutable failed predecessor and actual model accounting

All earlier rows, artifacts and counters remain immutable. In particular:

- Continuation
  `dcp-card12-model-free-rebase-continuation-66eb630c1995f90b37429a2f6c57c57794dda9fc98a29149c88bdb2f01131060`
  remains terminal `failed/identity_drift`, revision `1`, with trusted
  worker/arbiter/model-free-action/reviewer counts `0/0/0/0`, no new head,
  review, admission rebind or merge.
- The predecessor fresh-worker row remains terminal
  `failed/worker_process_failed`, revision `5`, with worker/reviewer counts
  `1/0`, its exact artifacts and no downstream result.
- Card 11 admission sequence `3`, id
  `dcp-admission-841c6c1e-3dcd-4ffb-875e-c42dfa358919`, remains `succeeded`
  with merge SHA `b34b31b5443890e69128db2862726950a6bbac0d`.
- Card 12 admission sequence `4`, id
  `dcp-admission-ecb500ad-f9f0-443b-9d73-2c8a6350ce34`, remains
  `incident/merge_conflict_or_ambiguity`, with the same lease, old head,
  review/run/batch identity and no merge SHA.
- The exact incident, generation-2 successor decision, consumed wake, failed
  fresh-worker action, old approved review and old named check remain
  unchanged. No old verdict or check may be rebound to a new head.
- The unauthorized native restoration calls remain immutable evidence. Card
  11 used thread `019ff9f3-cad3-73c1-bcee-293efe857349` and reported `33,238`
  tokens. Card 12 used thread `019ff9f3-cbe6-71e2-8636-ea6259a7e7d1`
  and reported `33,573` tokens. The exact error total is `66,811` tokens.

The truthful starting Stage 2 aggregate is nine actual calls with `199,596`
exactly reported tokens plus the earlier failed fresh-worker call bounded by
`16,384` tokens, for a ceiling of `215,980`. This contract adds no worker or
arbiter call. Its only possible model use is one fresh context-free reviewer
after a trusted new head exists.

## 2. Exact current identities and post-drift Git state

The only eligible native identities are:

- project `dcp-review-lab`;
- card/session `dcp-review-lab-11`, task `i13-arbiter-a`, already merged;
- card/session `dcp-review-lab-12`, task `i13-arbiter-b`;
- repository `orenvlad-ai/dcp-review-lab`;
- worktree
  `/Users/ovlmacbook/Library/Application Support/DCP Orchestrator/data/worktrees/dcp-review-lab/dcp-review-lab-12`;
- branch `ao/dcp-review-lab-12/root` and ready PR
  `https://github.com/orenvlad-ai/dcp-review-lab/pull/9`;
- incident
  `dcp-global-release-2694dbd8b3d4897063603d7a8607ca516aa2f8e05c5a3c39cf56d8e3f18c3c60`;
- remote/local old head
  `d4fcb68051ae113ed497d02151a759800ee85633`;
- exact current main `b34b31b5443890e69128db2862726950a6bbac0d`;
- provider PR-base snapshot
  `dbaf01b05e85ffffa4c843a905e2fe5229eaf0da`, proven an ancestor of current
  main.

The app and daemon are stopped. Both retained native panes are stable bare
shells with no Codex or supervisor child. The card-12 worktree is attached to
the existing branch at the old head, has no rebase metadata, and has exactly
one unmerged path `UU canary/i13-arbiter-conflict.txt`. Its complete
NUL-terminated porcelain-v1 status SHA-256 is
`fd7d8ff8f4918e9960e5e46e01c70a877d4218b3fa1e884ecc1723935b1c9886`.

The unmerged index has exact stage blobs:

- stage 1 `ed237ce2dd2684371797e22634480ffb28dc9e77`;
- stage 2 `a4c945ba7328504f2efea44f076a1407c6aa7b47`;
- stage 3 `80a658c4cfc3ffda5786da316bc0bd10ffb1834f`.

The 104-byte conflict-marker file SHA-256 is
`5850bba009db75bf47ff88aef2d2cecbdba89c68967f51a8cdb60f48e968dc1a`.
There is no other modified, staged, unmerged or untracked path and no rebase,
merge, cherry-pick, revert, bisect, sequencer or lock residue. The only
authorized resolved bytes remain exactly
`arbiter intent A\narbiter intent B\n`, SHA-256
`2a5da25a78ff8bcd9aff4493f195eaefecbc70c3d4db8902dda468ccf69e5e46`.

Every local, SQLite, process, provider, ref, ancestry, index, byte or digest
mismatch fails closed. A changed but apparently equivalent state is not
guessed around.

## 3. Pre-restoration cold-start quarantine

The managed source must correct startup order before enabling recovery. The
daemon must establish and read one durable startup-restoration fence
transaction immediately after opening/migrating its existing SQLite and before
constructing or invoking any path that can create, restore or relaunch a tmux
pane, native terminal, supervisor or stored worker command.

The transaction classifies both exact governed sessions model-free:

1. Card 11 is terminal admission evidence and must not be restored as an
   ordinary worker.
2. Card 12 is owned by the exact terminal predecessor plus this governed
   recovery generation and must not be restored as an ordinary worker.

The classification is persisted with exact session/admission/incident/
continuation/recovery identities, a generation, contract commit, state digest,
created time and last verified time. A restart reads the same rows and
revalidates their immutable source facts. It does not depend on launch timing,
process killing, a heartbeat, watcher, model judgement or a later reconcile.

The returned in-memory fence is sealed before session-manager startup
reconciliation. Both its live-capture and restore passes must skip cards 11/12
without touching their workspace, Git state, markers, panes or stored worker
commands. Unrelated sessions retain stock restoration behavior. If either
governed card exists but its classification is absent, ambiguous or stale, or
if the database/precondition read or transaction fails, daemon startup fails
before session restoration and before serving. It must never fall back to the
old best-effort path for these cards.

A crash after durable fence establishment but before recovery leaves the
fence effective on the next start. Tests must prove zero card-11/card-12
runtime creates and zero stored worker-command launches on first start, at
that crash boundary and on restart. They must also prove no tmux or Codex child
can be created before fence establishment, while an unrelated eligible saved
session still follows stock restoration.

## 4. Additive exact recovery generation

Managed source may add one additive migration after 0060. It may create only:

- the durable exact startup-quarantine rows described above; and
- one subordinate card-12 post-drift model-free recovery row.

No merged migration or predecessor row may be edited. The recovery row id is
`dcp-card12-cold-start-quarantined-recovery-` followed by identity digest
`087176dbe56428dc97a99823a94daa4687c41b15c14a08de21db2c6c602f0f2f`.
The digest is SHA-256 over the ordered NUL-delimited tuple:

```text
dcp.review-lab.card12-cold-start-quarantined-recovery/v1,
recovery generation 1,
failed continuation id/status/error/revision/action/reviewer counts,
card-11 admission id/status/merge SHA,
card-12 admission id/status/error,
card-11 session id,
card-12 session id/task/project/repository/worktree/branch/PR,
old head/current main/provider base,
post-drift status digest,
conflict-marker digest,
index stage-1/stage-2/stage-3 blob ids,
authorized resolved-bytes digest,
two unauthorized worker thread ids and token counts,
dcp-i13-stage2-card12-cold-start-quarantined-recovery-v1
```

One exact `INSERT ... SELECT` over all frozen predecessor facts creates the
row. Zero or multiple matches fail closed. The row separately records status,
revision, startup-fence generation, backup path/digest, one model-free action
count constrained to `0` or `1`, reviewer count constrained to `0` or `1`,
old/main/provider refs, new commit/head, exact guarded push, fresh review/check,
admission rebind, terminal merge and bounded error. Rollback may remove only
empty unstarted rows; it refuses after fence, backup, action, review, rebind or
terminal result.

## 5. Physical preflight and immutable backup

After the startup fence is active and before consuming the recovery action,
the trusted daemon must prove all Sections 1-4 facts plus:

1. installed receipt, running daemon and separately merged immutable pin all
   identify this exact implementation;
2. one authorized recovery row has revision zero, action/reviewer counts zero
   and empty downstream identities;
3. there is no active worker, reviewer, arbiter, recovery supervisor, Codex
   descendant or other mutator; both governed panes are absent or stable bare
   shells;
4. canonical worktree/private Git/common Git topology, branch ownership,
   origin fetch/push URLs and provider identity are exact;
5. fresh authenticated read-only transport proves only the scoped remote old
   head and current main, while fresh provider facts prove the same OPEN,
   non-draft, unmerged PR and historical provider base;
6. exact attached HEAD, local branch ref, sole `UU` path, index stages,
   conflict-marker bytes/status digest and absence of every extra path or Git
   operation residue still match.

Before the first repository write, the daemon creates one private immutable
backup below the canonical DCP lab evidence root. It contains a canonical
manifest plus byte-exact copies of the scoped worktree file and private Git
state required to audit the attached HEAD, branch ref, index and operation
residue. Files are regular, non-symlink, owner-only and created through a
temporary directory followed by atomic rename. The manifest records each
relative path, mode, size and SHA-256; the ordered aggregate backup digest and
absolute backup path are persisted in the recovery row. Existing backup names
or mismatched files are a stop. The backup is never restored automatically or
modified after publication.

Only after re-reading the immutable backup and all preconditions may one
compare-and-set move the recovery row from `authorized` to `running`, set
`model_free_action_count=1` and persist the action start. This fence is
consumed even if a later Git command, push or provider confirmation fails.

## 6. Deterministic reconstruction, continuation and guarded push

The one trusted daemon-owned action may perform only this exact transition:

1. Restore a clean local old-head basis for the already attached existing
   branch, using the exact old head after the backup and fence. No other ref,
   worktree or path may change.
2. Rebase only the one old-head commit whose sole parent is provider base and
   whose subject is `chore: add i13 arbiter intent B canary` onto exact current
   main. Hooks and signing are disabled and the operation is non-interactive.
3. Require the reconstructed rebase to stop only on the exact canary path with
   the expected current-main and candidate bytes and no other status path.
4. Write only the authorized two-line bytes, stage only that literal path and
   continue the one commit non-interactively. Require rebase metadata to be
   consumed and the same existing branch to own the result.
5. Prove the new head differs from the old head, is exactly one commit above
   current main with current main as its sole parent, preserves the intended
   subject/author, and differs only at the exact canary path with the exact
   two-line bytes. Worktree/index must be clean and every operation/lock
   residue absent.
6. Re-prove remote old head/current main/provider identity, then issue exactly
   one push of the same branch with force-with-lease fixed to
   `d4fcb68051ae113ed497d02151a759800ee85633`. No other refspec, branch,
   repository or remote mutation is permitted.
7. Fresh Git/provider facts must prove PR #9 now owns exactly the new head,
   current main is unchanged and the one-commit/one-path candidate matches.

No manual Git completion, shell bypass, second action or push retry exists. A
rejected or unknown push is terminal. If the remote mutation is later proved
to have succeeded, startup may only persist that exact already-observed head
model-free; it cannot repeat a repository write.

## 7. One fresh review, admission and merge

Only the persisted exact new head may consume the recovery row's one reviewer
fence and enter the existing stock automatic review engine. The reviewer is
fresh, stateless, context-free, read-only, network-disabled and schema-bound.
It receives the original approved task/scope, deterministically selected
authoritative documentation and the exact new head/diff/checks. It receives no
worker transcript, old review, arbiter reasoning, recovery artifacts, daemon
credential or control channel.

A launch/result/process failure, malformed/late/stale/foreign identity,
findings, non-approval or changed head is terminal with no second reviewer.
Progress requires all of:

- one structured `approved` verdict with empty findings for the exact new head;
- one fresh successful check named `dcp-review-lab` for that head;
- no unresolved review thread;
- fresh exact OPEN, non-draft, same-repository/head/base identity and
  `MERGEABLE`/`CLEAN` provider facts.

The trusted daemon may then atomically rebind only admission sequence 4 from
the old run/head to the new run/head while retaining the same task, session,
incident and FIFO identity. The existing admission engine must revalidate all
facts and may issue one expected-head squash merge of only PR #9. Neither the
recovery action nor reviewer can merge. Provider ambiguity remains one-shot
and fail-closed.

## 8. Restart, tests and terminal evidence

Managed-source tests must cover at least:

- exact migration and rollback refusal after each fence;
- startup ordering, including a recorded call-order assertion that durable
  fence establishment precedes any session reconcile/runtime create;
- card-11/card-12 zero worker launch on first cold start, crash after fence and
  restart, plus stock restoration for an unrelated eligible session;
- unknown/missing/ambiguous rows and database read failures stopping before a
  runtime create;
- exact post-drift Git/index/marker acceptance and every identity/digest/extra-
  path/mutator rejection;
- atomic backup creation, digest verification, pre-existing-path rejection and
  no repository mutation before backup/action fences;
- exact one-commit reconstruction, permitted bytes, single force-with-lease
  push and rejection/unknown-outcome behavior;
- one fresh reviewer, old-head verdict/check rejection, admission rebind,
  terminal merge and restart deduplication;
- crash boundaries before/after backup, action fence, local commit, push,
  reviewer fence, rebind and merge.

After a terminal success or failure, one controlled stop/start must preserve
the startup quarantine, recovery row, predecessor rows, backup, all identities
and counts without another worker, arbiter, action, reviewer, push, admission
claim or merge. Terminal evidence uses a separate reviewed PR and includes all
contract/source/pin/evidence PRs and merge SHAs, CI, installed receipt, exact
before/after state, backup digest, startup-fence proof, the immutable 66,811-
token error, any fresh reviewer token count, admission/merge facts and restart
deduplication.

`COMPLETE` requires PR #9 merged from the one freshly reviewed exact head.
Any mismatch, worker launch, exhausted one-shot fence or unknown mutation is
truthful `BLOCKED`.

## 9. Exact ceilings and non-authority

| Action | New ceiling |
| --- | ---: |
| Startup-order corrections | 1 |
| Card-12 model-free recovery actions | 1 |
| Worker model calls | 0 |
| Arbiter model calls or decisions | 0 |
| Fresh exact-head reviewer calls | 1 |
| New cards/tasks/native sessions/worktrees/branches/PRs/incidents | 0 |
| Guarded pushes of the existing PR #9 branch | 1 |
| PR #9 terminal merges | 1 |

This contract creates no replacement identity, worker/arbiter retry,
transcript replay, second daemon/database/registry, queue, scheduler, watcher,
heartbeat, timer, polling/model loop, general Git repair API, manual Run
Review, manual merge, Release Train, deploy, production target, `wb-core`,
other repository, secret export, Telegram, hosted/mobile surface, HumanGate or
owner-acceptance synthesis. It never reads or operates installed Agent
Orchestrator or `~/.ao`. Technical completion is not owner acceptance; only
the owner may write `Задача принята`.
