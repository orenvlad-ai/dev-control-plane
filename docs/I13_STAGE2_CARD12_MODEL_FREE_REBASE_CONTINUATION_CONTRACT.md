# I13 Stage 2 exact card-12 model-free rebase continuation contract

contract_status: owner-approved-pre-runtime-model-free
contract_version: dcp-i13-stage2-card12-model-free-rebase-continuation-v1
contract_revision: 1
recorded_at: 2026-08-13
dev_control_plane_baseline: b16f7c5137d41973a930a6f0a9be6f7fdec4e54c
managed_source_baseline: 75a14431a3433f581755f2e0ec096814e3e9ecb1
continuation_generation: 1
continuation_identity_digest: 66eb630c1995f90b37429a2f6c57c57794dda9fc98a29149c88bdb2f01131060
additional_worker_model_calls: 0
additional_arbiter_model_calls: 0
fresh_reviewer_model_call_ceiling: 1

This contract records the owner's 2026-08-13 authorization after the truthful
terminal result in
[card-12 fresh worker recovery terminal evidence](I13_STAGE2_CARD12_FRESH_WORKER_RECOVERY_TERMINAL_EVIDENCE.md).
It permits one trusted, deterministic continuation of only the exact unfinished
rebase left by that consumed worker call. It does not reinterpret the failed
worker as successful, change any immutable predecessor row or artifact, or
authorize another worker or arbiter model call.

This document and its authoritative references must be green, merged and
present in the clean canonical `dev-control-plane` checkout before managed
source work. A separate reviewed managed-source PR, immutable pin PR and exact
deterministic install/preflight must then complete before the daemon may touch
the preserved rebase. The existing daemon, SQLite and exact synthetic PR
remain the only runtime and state authorities.

## 1. Exact immutable predecessor

The only eligible predecessor is the complete state below. Every row, artifact
and counter named here is re-read immediately before the continuation fence.

- Native project/task/card/session are exactly `dcp-review-lab` /
  `i13-arbiter-b` / `dcp-review-lab-12`. The session is idle,
  non-terminated, uses harness `codex`, has display name `DCP:i13-arbiter-b`,
  runtime handle `dcp-review-lab-12`, and has empty native
  `agent_session_id`, `runtime_launch_id`, `diff_base_sha` and
  `diff_base_ref`.
- The canonical worktree is exactly
  `/Users/ovlmacbook/Library/Application Support/DCP Orchestrator/data/worktrees/dcp-review-lab/dcp-review-lab-12`.
  Its Git common directory is exactly
  `/Users/ovlmacbook/Library/Application Support/DCP Orchestrator/targets/dcp-review-lab/.git`
  and its private Git directory is that common directory's exact
  `worktrees/dcp-review-lab-12` child.
- Repository, branch and PR are exactly `orenvlad-ai/dcp-review-lab`,
  `ao/dcp-review-lab-12/root` and
  `https://github.com/orenvlad-ai/dcp-review-lab/pull/9`. The local branch ref
  and remote branch are both exactly
  `d4fcb68051ae113ed497d02151a759800ee85633`; provider facts are OPEN,
  non-draft, unmerged, `CONFLICTING`/`DIRTY`, with that exact one-commit,
  one-file head. Provider `main` is exactly
  `b34b31b5443890e69128db2862726950a6bbac0d`.
- Incident
  `dcp-global-release-2694dbd8b3d4897063603d7a8607ca516aa2f8e05c5a3c39cf56d8e3f18c3c60`,
  accepted successor decision digest
  `237472879b22a8db65c5a3a0715510dc17aee1de93c45eaab45dde538cefb939`
  and terminal successor row `failed/repair_launch_failed` with call/wake
  counts `1/1` remain unchanged.
- Admission sequence `4`, id
  `dcp-admission-ecb500ad-f9f0-443b-9d73-2c8a6350ce34`, remains
  `incident/merge_conflict_or_ambiguity` on the old head, with retained lease
  `dcp-incident-dcp-admission-ecb500ad-f9f0-443b-9d73-2c8a6350ce34`, original
  review run `ecb500ad-f9f0-443b-9d73-2c8a6350ce34`, review
  `6aab2a2f-beb2-40a2-bcdb-c47ebf304a65`, batch
  `ddeeb966-30a0-4870-8f3f-fda32a4ee568`, no merge SHA and zero refresh
  wakes. The old approved/no-findings verdict and its successful named check
  remain bound only to the old head and are never reused.
- The predecessor fresh-worker row is exactly
  `dcp-card12-fresh-worker-recovery-d2b7142bc9e5844ba165abe24d3222b3e1a94c3577fba5f6f8d97ec3dbad151b`,
  recovery generation `1`, revision `5`, terminal
  `failed/worker_process_failed`, worker/reviewer calls `1/0`, input digest
  `1b79923f68e0a53414579f059a1984fbcdae7aea4593d86c7fa4ae62027114bd`,
  launch id equal to that recovery id, and empty admitted worker session,
  token, result/log digest, new head/commit, recovery review/check and merge
  fields. Its timestamps and every other column stay immutable.
- Original arbiter input/schema/result SHA-256 values remain
  `355a00609c8ded920bd87b215cea74d3c50213fa4ed8f0b484ea577f73bdbd7d`,
  `8314793a7dbc3f0fc654c28e5936687138883b6e134460fc7204a025102b805f`
  and `d121d012a0b3042f02886fdc0c2aca806f34be64f9e5a3d15e1edf444ff3ae2d`.
  Successor input/schema/result SHA-256 values remain
  `fa30d6ea6620e58c36d5163505b2ae80dcdf70b1ee6e2225e0948fe71bdce627`,
  `8779ee3a04b9d3cf0fa2302ced20407f781f5204cd650fe7326c3f93f23925ca`
  and `9b5ff7847db2533e56bdbbc424114e5bea8e5e3c352ad1d029a99deaba05c172`.
- Fresh-worker input/result/event-log files are regular mode-0600 files of
  exactly 3,143 / 541 / 3,802 bytes and SHA-256
  `131ab471a0509f4851f94e056998b3a620468a69bdd3b19435d2a225da01d393`,
  `e284aeb37d6fdd7ec86ee3ea6ad2272eee7d4856d5a39eb2894c89dd83d0836b`
  and `8909c2cb81e96beb47414576fb6e1c54e9895fcf34e38e2865d87ca821b46a20`.
  They are read-only evidence to this continuation and are never edited or
  replayed as a model result.
- Durable counts start at 17 native sessions, 11 review runs, four admissions,
  one original incident row, one successor row, one fresh-worker row and one
  preflight-recovery audit row. Stage 2 has seven actual model calls, with
  132,785 exactly recorded predecessor tokens plus the one exhausted worker
  call bounded above by 16,384 tokens. This continuation adds no model use
  until its possible one fresh reviewer.

Any mismatch is terminal before Git mutation. A moved current main, remote
head, PR, predecessor row, artifact or counter is not guessed around. A later
benign change requires a separate reviewed exact-equivalence contract and
source change.

## 2. Exact preserved rebase evidence

The continuation applies only to this byte-exact Git state:

1. `HEAD` is detached at exact current main
   `b34b31b5443890e69128db2862726950a6bbac0d`; `HEAD` file SHA-256 is
   `1ae2db070d57e5e89b631b34a443f8c929f86a13c9014c7f8300c184310049cd`.
   `ORIG_HEAD`, `REBASE_HEAD`, `rebase-merge/orig-head` and
   `rebase-merge/stopped-sha` all name old head
   `d4fcb68051ae113ed497d02151a759800ee85633` and their 41-byte file SHA-256
   is `657c15026f6e8f51e96e6ff6c2ae94a5d6f4031ec95f07030b52f6226cc4d810`.
2. `rebase-merge/onto` names exact current main;
   `rebase-merge/head-name` contains exactly `detached HEAD\n`;
   `msgnum=end=1`; `git-rebase-todo` is empty; `done` contains exactly the
   single old-head pick; and the stopped commit subject is exactly
   `chore: add i13 arbiter intent B canary`.
3. The complete permitted metadata set is exactly `AUTO_MERGE`, `MERGE_MSG`,
   `REBASE_HEAD` plus these 15 `rebase-merge` files: `author-script`, `done`,
   `drop_redundant_commits`, `end`, `git-rebase-todo`,
   `git-rebase-todo.backup`, `head-name`, `interactive`, `message`, `msgnum`,
   `no-reschedule-failed-exec`, `onto`, `orig-head`, `patch` and
   `stopped-sha`. SHA-256 over the ordered NUL-delimited
   `relative path, byte size, file SHA-256` tuples is exactly
   `db9933afbc18ffbd031818990e2b350845c766a5f0ae8ed37fae8f4e8a66f371`.
   No other merge, cherry-pick, revert, bisect, sequencer or lock residue is
   present.
4. Exactly one unmerged path exists and its status is `AA`:
   `canary/i13-arbiter-conflict.txt`. Index stage 2 is blob
   `ed237ce2dd2684371797e22634480ffb28dc9e77` with bytes
   `arbiter intent A\n`; index stage 3 is blob
   `a4c945ba7328504f2efea44f076a1407c6aa7b47` with bytes
   `arbiter intent B\n`. No stage 1 entry exists.
5. The working file is a regular mode-0644 34-byte file containing exactly
   `arbiter intent A\narbiter intent B\n`, SHA-256
   `2a5da25a78ff8bcd9aff4493f195eaefecbc70c3d4db8902dda468ccf69e5e46`.
   There is no other modified, staged or untracked path. The complete
   NUL-terminated porcelain-v1 status SHA-256 is
   `0c7f653e181d09cdbbc96d3bcff1ca63851fcaf3a3db0236a0896d88f0f6be84`.
6. The old commit has exactly one parent
   `dbaf01b05e85ffffa4c843a905e2fe5229eaf0da`, which is also the exact merge
   base with current main. The old candidate differs from current main only at
   the named path; its binary full-index diff SHA-256 is
   `9a752434961d4ef2dc8c6478582ab497ee4c19436b28ee0112c0fb5600b81a18`.

The failed worker's local resolution is immutable evidence until the new
daemon-owned continuation fence is consumed. No shell, curator or model may
stage, continue, abort, reset, clean, switch, commit or push it outside the
reviewed managed-source path.

## 3. One additive continuation row

Managed source may add only additive migration
`0059_dcp_review_lab_card12_model_free_rebase_continuation.sql`. It creates one
subordinate row in the existing `ao.db`; it does not edit migrations 0048-0058
or update any predecessor row. The row is not a generic Git action, retry,
worker attempt, repair, reviewer or admission table.

The row id is `dcp-card12-model-free-rebase-continuation-` followed by identity
digest
`66eb630c1995f90b37429a2f6c57c57794dda9fc98a29149c88bdb2f01131060`.
That digest is SHA-256 over this ordered NUL-delimited tuple:

```text
dcp.review-lab.card12-model-free-rebase-continuation/v1,
continuation generation 1, predecessor fresh-worker recovery id, incident id,
admission id, native session id, task id, project id, repository,
canonical worktree path, source branch, PR URL, PR number, remote old head,
current main, predecessor status, predecessor error, predecessor revision,
predecessor input digest, input/result/log artifact SHA-256 values,
rebase metadata aggregate SHA-256, permitted resolved-bytes SHA-256,
dcp-i13-stage2-card12-model-free-rebase-continuation-v1
```

One exact `INSERT ... SELECT` over all predecessor constants creates the row.
Zero or multiple eligible predecessors fail closed. The row separately records:

- exact continuation identity, generation, contract commit and every frozen
  predecessor/Git/artifact digest;
- status, revision, one model-free action fence constrained to `0` or `1`,
  timestamps and a bounded error code;
- old head/current main, observed new commit/head, local branch-ref transition,
  exact guarded-push ref/lease and provider-observed new head;
- fresh review/run/batch/check identities, reviewer call count constrained to
  `0` or `1`, admission rebind and terminal merge SHA.

Rollback may drop only an empty, unstarted row/table. It refuses after the
model-free action fence, a Git ref/worktree mutation, reviewer fence,
admission rebind or terminal result. The predecessor fresh-worker row and its
`1/0` call counts remain byte-for-byte unchanged for all outcomes.

## 4. Preconditions and mutator quiescence

Immediately before the one model-free action fence, the trusted daemon must
prove all Sections 1-3 facts plus:

1. The installed bundle/receipt and running daemon match the separately merged
   immutable managed-source pin implementing this contract.
2. Exactly one continuation row is `authorized`, revision zero, action count
   zero, reviewer count zero, and has no new-head, review, admission or merge
   identity.
3. The canonical DCP app/daemon contour is unique. No worker, reviewer,
   arbiter, successor or fresh-worker supervised descendant is active. Every
   exact retained pane is provably absent or a stable bare shell; any foreign
   or ambiguous process/pane is a stop.
4. Fresh authenticated read-only Git transport, using only exact existing
   `/opt/homebrew/bin/gh` 2.87.2 with binary SHA-256
   `f392d9ad8d2260c671566936b127f5436772ce16e25b091cf1fa7b301987f27e`
   as `git credential` helper, proves only the two scoped refs and their exact
   old-head/current-main values. No token value is logged, stored or passed to
   a model.
5. Fresh provider facts independently prove the exact same OPEN/non-draft,
   unmerged PR, repository/author/base/head branch and old head, with no extra
   PR or changed identity. The old check/review stay old-head evidence only.
6. Worktree/common/private Git paths, origin fetch/push URLs, local branch ref,
   detached HEAD, complete rebase metadata, index stages, working bytes,
   status digest and absence of locks/foreign residue still match exactly.

The daemon atomically moves only that row from `authorized` to `running`,
increments `model_free_action_count` to one and persists the start time before
the first Git write. The fence is consumed even if staging, rebase continuation,
local-ref update, push, provider confirmation or later handling fails. There is
no second model-free continuation, command retry or manual fallback.

## 5. Exact deterministic continuation and guarded push

After the fence, the daemon executes only this bounded state transition:

1. Stage only `canary/i13-arbiter-conflict.txt` through a pathspec-literal exact
   Git operation. Re-read the index and require one stage-0 entry whose blob
   bytes and SHA-256 equal the permitted 34-byte file, with no other staged,
   modified, unmerged or untracked path.
2. Run one non-interactive `git -c core.hooksPath=/dev/null -c
   commit.gpgSign=false rebase --continue` with `GIT_EDITOR=:` and no hook,
   signing, credential or user-command interpolation. The rebase must consume
   exactly the existing single stopped commit and remove only the permitted
   rebase metadata.
3. Require a new detached head different from the old head, exactly one commit
   ahead of current main, with one parent equal to current main. Its tree may
   differ from current main only at the exact canary path with the exact
   two-line bytes. The worktree and index must be clean and all rebase/merge/
   sequencer/lock residue absent. Commit subject and original author identity/
   timestamp must remain those of the stopped intended commit.
4. Atomically move only local ref
   `refs/heads/ao/dcp-review-lab-12/root` from the exact old head to the exact
   new head, then attach the same worktree to that already-existing branch.
   A non-old local ref or a foreign worktree owner is a terminal stop.
5. Re-prove remote old head/current main through the exact credential helper,
   then perform exactly one push equivalent to:

   ```text
   git -c credential.helper=!/opt/homebrew/bin/gh auth git-credential \
     push --force-with-lease=refs/heads/ao/dcp-review-lab-12/root:d4fcb68051ae113ed497d02151a759800ee85633 \
     origin HEAD:refs/heads/ao/dcp-review-lab-12/root
   ```

   No other refspec, push, branch, PR, repository or remote mutation is
   permitted. A rejected or unknown push outcome is terminal and is never
   retried.
6. Fresh Git/provider facts must prove the same branch/PR now owns exactly the
   new head, current main is unchanged, the PR remains OPEN/non-draft and the
   candidate is the single exact intended commit/diff. Only then may the row
   persist `worker_succeeded` as a compatibility state meaning “trusted
   candidate available”; it records zero worker model calls and does not edit
   the predecessor failed-worker row.

A zero process exit is not sufficient. Every exact local, remote and provider
postcondition is required. If the remote mutation succeeds but a later fact is
ambiguous, the row fails terminally and startup may only reconcile the exact
already-observed remote head model-free; it may not push again.

## 6. One fresh reviewer, admission and merge

Only the exact persisted new head from Section 5 may enter the existing stock
automatic review trigger. One compare-and-set on the continuation row fences
exactly one new `ReviewRun` and increments its reviewer call count to one. The
predecessor row remains `1/0` and the old run remains bound to the old head.

The reviewer is the existing fresh, stateless, context-free Codex reviewer. It
receives only the original approved task/scope, authoritative documentation
selected by existing deterministic rules, exact new head/diff and declared
checks. It receives no worker transcript, old verdict, arbiter reasoning,
recovery artifacts, daemon credential or network tool. Existing read-only,
network-disabled, schema-bound trusted-result handling applies.

Any launch/result/process failure, malformed or stale identity, findings,
non-approval, changed head or second review attempt is terminal without another
worker, reviewer or arbiter. Only all of these allow progress:

- exactly one new structured `approved` verdict with empty findings for the
  exact new head;
- exactly one successful check named `dcp-review-lab` for that same head;
- no unresolved review thread;
- fresh exact repository/PR/head/base facts showing OPEN, non-draft,
  MERGEABLE and CLEAN.

The trusted daemon may then atomically rebind only admission sequence 4 from
the old run/head to this new run/head while retaining the same task, session,
incident and FIFO identity. The existing admission engine revalidates every
fact and may make exactly one expected-head squash merge of only PR #9. Neither
the model-free continuation nor reviewer can merge. Provider error or unknown
merge outcome follows existing one-shot terminal reconciliation and never
causes a second merge request.

## 7. Restart, deduplication and terminal evidence

Startup reconciliation obeys these bounds:

- before the action fence, only the exact authorized row may fence once;
- while `running`, an exact in-progress daemon-owned Git operation is never
  duplicated; absent or ambiguous ownership fails without another action;
- after a proven new remote head, reconciliation may persist that exact result
  once but cannot stage, continue, move a ref or push again;
- after the reviewer fence, an exact live reviewer is left alone and one exact
  completed artifact may be consumed through the stock trusted path; no second
  review is launched;
- duplicate, late, old-head, foreign or malformed Git/provider/reviewer facts
  are inert after the applicable fence;
- after terminal success or failure, a controlled stop/start must preserve all
  predecessor rows, the one continuation row, identities, action/reviewer
  counts and terminal result without another model-free action, model call,
  wake, review, admission claim, push or merge.

Terminal evidence must include contract/source/pin PRs and SHAs, required CI,
installed receipt and artifact digests, exact before/after Git/provider/SQLite
identities, the one push lease, new review/run/check/admission/merge facts,
model-call and token accounting and controlled-restart deduplication proof.
`COMPLETE` requires PR #9 merged from the one freshly reviewed exact head.
Every mismatch or exhausted one-shot action is truthful `BLOCKED`.

## 8. Exact ceilings and explicit non-authority

| Action | New ceiling |
| --- | ---: |
| Model-free rebase continuation actions | 1 |
| Worker model calls | 0 |
| Arbiter model calls or decisions | 0 |
| Fresh exact-head reviewer calls | 1 |
| New cards/tasks/native sessions/worktrees/branches/PRs/incidents | 0 |
| Guarded pushes of the existing PR #9 branch | 1 |
| PR #9 terminal merges | 1 |

This contract creates no worker/arbiter retry, transcript replay, replacement
identity, second daemon/database/registry, queue/scheduler/watcher/heartbeat/
timer/poll, general Git repair API, manual Run Review, manual merge, Release
Train, deploy, production target, `wb-core`, other repository, secret export,
Telegram, hosted/mobile surface, HumanGate or owner-acceptance synthesis. It
never reads or operates installed Agent Orchestrator or `~/.ao`. Technical
completion is not owner acceptance; only the owner may write `Задача принята`.
