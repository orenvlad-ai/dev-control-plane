# I13 Stage 2 card-12 model-free provider-base correction contract

contract_status: owner-authorized-direct-path-correction-pre-runtime

correction_generation: 1

correction_identity_digest: `25663a5a551fce7ec0d6d9055588b4c4d1d1294fd926e2c7c2347cacd799ab59`

## Purpose

This contract corrects one non-compositional pre-action validation defect in
the already reviewed
[card-12 model-free rebase continuation](I13_STAGE2_CARD12_MODEL_FREE_REBASE_CONTINUATION_CONTRACT.md).
It adds no task, card, session, worktree, branch, PR, incident, admission,
worker call, arbiter call, reviewer call, Git action or retry. The correction
must merge and be implemented, pinned, deterministically installed and
preflighted before the stopped DCP daemon may start.

## Proven stopped evidence

The installed receipt is exact managed source
`a7b5476fb886bcbb6bbd91aa89da17966547b3b8`, tree
`53525c260b4de1ed749aeb4c89f4e085e433c9bd`, installed at
`2026-08-13T06:38:17Z`. Deterministic build/install/preflight passed, but the
new daemon has never started: canonical status is `stopped`, migration 0059 has
not run, its continuation table is absent and no continuation action or
reviewer fence has been consumed. The immutable fresh-worker predecessor
remains `failed/worker_process_failed`, revision 5, with worker/reviewer counts
`1/0` and no new head or review.

Read-only GitHub and local Git proof established all of these simultaneous
facts:

- `refs/heads/main` is exactly
  `b34b31b5443890e69128db2862726950a6bbac0d` through both `git ls-remote` and
  the GitHub GraphQL repository ref.
- PR #9 remains OPEN, non-draft and conflicting on old head
  `d4fcb68051ae113ed497d02151a759800ee85633`.
- GitHub REST `base.sha`, GraphQL `baseRefOid` and the durable `pr.base_sha`
  observation are all exactly
  `dbaf01b05e85ffffa4c843a905e2fe5229eaf0da`.
- `dbaf01b05e85ffffa4c843a905e2fe5229eaf0da` is an ancestor of current main
  `b34b31b5443890e69128db2862726950a6bbac0d`; the sole ancestry-path commit is
  that exact current-main commit, which introduced the proven `arbiter intent
  A` canary.
- The preserved rebase is still detached at current main with exact original
  head/onto/message metadata, one AA path and resolved digest
  `2a5da25a78ff8bcd9aff4493f195eaefecbc70c3d4db8902dda468ccf69e5e46`.

The defect is therefore mechanical: managed-source PR #30 compared the PR's
historical provider base snapshot with the current target-branch ref as if they
were the same fact. The installed source would fail closed before its Git
action. It has not been allowed to do so.

## Exact correction

The correction must persist one additive immutable row bound to:

- continuation
  `dcp-card12-model-free-rebase-continuation-66eb630c1995f90b37429a2f6c57c57794dda9fc98a29149c88bdb2f01131060`;
- correction digest
  `25663a5a551fce7ec0d6d9055588b4c4d1d1294fd926e2c7c2347cacd799ab59`;
- this contract's exact merge commit;
- provider PR base
  `dbaf01b05e85ffffa4c843a905e2fe5229eaf0da`;
- canonical current main
  `b34b31b5443890e69128db2862726950a6bbac0d`;
- original contract commit `e17fa9080434b5642667392fb06db61cf35f19bd`;
- reviewed source commit `a7b5476fb886bcbb6bbd91aa89da17966547b3b8`.

The trusted pre-action validator must require the stored and freshly fetched
PR base to equal the exact provider-base SHA above. Independently, the existing
model-free executor must continue to require remote `refs/heads/main`, local
detached `HEAD`, rebase `onto`, the intended new commit's sole parent and the
post-push remote main to equal exact current main. It must additionally prove
provider base is an ancestor of current main from the already fetched exact
repository. Neither SHA may be inferred, refreshed to a moving value or used
as a substitute for the other.

After the new head, ordinary terminal admission continues to refresh current
main and prove merge compatibility before claiming the merge. The provider PR
base remains the review-base fact; the admitted base remains the separately
proven current canonical main.

## Unchanged authority and ceilings

- Additional worker model calls: `0`.
- Additional arbiter model calls or decisions: `0`.
- Model-free continuation actions: still exactly `1` total.
- Fresh context-free reviewer calls: still at most `1` total on the single new
  exact head.
- No replacement identity, manual rebase/push/review/merge, second action,
  second reviewer or general provider-base compatibility policy is authorized.
- Every row/identity/digest/ref/ancestry mismatch fails before Git mutation.

## Required delivery order and terminal states

1. Merge this contract through one ordinary ready dev-control-plane PR.
2. Merge one minimal managed-source PR with migration, validator and exact
   tests; `source` and `package` checks must pass.
3. Merge one pin/install-guard PR, fast-forward the clean canonical checkout,
   then repeat deterministic prepare/build/install/preflight.
4. Only then start the existing daemon for the original governed continuation.

`COMPLETE` still requires the one new head, one approved/no-findings review,
successful named check, exact admission rebind, one ordinary terminal merge
of PR #9 and controlled restart/deduplication proof. Any need for new authority
or any precondition mismatch is terminal `BLOCKED`.
