---
evidence_status: technical-blocked
captured_at: 2026-08-13T12:30:08Z
contract_commit: 623c3896a50d410e5b305ed08cf29abdc40b5b23
installed_source_commit: 04a967c26499a482fbff9a204bab046d79d2a2e2
installed_source_tree: fedee6276e8ce4a492d3c298aaf4bf843179c8bc
recovery_status: failed
recovery_error_code: model_free_action_failed
worker_calls: 0
arbiter_calls: 0
model_free_actions: 1
reviewer_calls: 0
remote_pr_head: d4fcb68051ae113ed497d02151a759800ee85633
local_unpushed_head: 4de6ff1a0b80223a9b32a05ba68cf0b665296081
---

# I13 Stage 2 card-12 cold-start quarantined recovery terminal evidence

## Result

The owner-approved cold-start recovery cycle is technically **BLOCKED**. The
pre-restoration quarantine fixed the architectural startup-order defect: every
guarded start classified exact cards 11/12 before runtime construction, neither
card launched a worker, and both preserved tmux panes remained bare `zsh`
shells with zero descendants. The one governed model-free action created and
sealed the required backup and deterministically completed the local one-commit
rebase. It then failed closed before its guarded push because Git retained the
regular `REBASE_HEAD` pseudoref after `rebase --continue`, while the trusted
candidate postcondition rejects that ref.

The durable recovery row is terminal `failed/model_free_action_failed`, revision
7, with trusted worker/arbiter/action/reviewer counts `0/0/1/0`. The exact same
branch now points locally at unpushed clean commit
`4de6ff1a0b80223a9b32a05ba68cf0b665296081`; remote branch and PR #9 remain at
`d4fcb68051ae113ed497d02151a759800ee85633`. No fresh review, check, admission
rebind or merge occurred. A controlled post-terminal restart preserved all
counts and identities and produced no duplicate activity. The bundle is
stopped. No further reconstruction, push, reviewer, merge or retry is
authorized by this cycle.

## Reviewed and merged change chain

| Stage | Pull request | Result |
| --- | --- | --- |
| Governing contract | dev-control-plane [#156](https://github.com/orenvlad-ai/dev-control-plane/pull/156) | merged normally at `623c3896a50d410e5b305ed08cf29abdc40b5b23` |
| Startup quarantine and recovery source | dcp-orchestrator [#32](https://github.com/orenvlad-ai/dcp-orchestrator/pull/32) | source/package green; no-findings semantic/security review; merged at `032e16aa3025858eeddecc1a25e87d4ec8ea4f18`, tree `cc519e93923e02d59463bbe14dd77192a237ce95` |
| Initial source pin/install guard | dev-control-plane [#157](https://github.com/orenvlad-ai/dev-control-plane/pull/157) | baseline green; no-findings review; merged at `277d479bbf5664d4a7140566a1ad5af4234ab44e` |
| Physical `gh` direct-path correction | dcp-orchestrator [#33](https://github.com/orenvlad-ai/dcp-orchestrator/pull/33) | source/package green; no-findings review; merged at `798e9bfb8f75846d846f2ec2d4dfc9ec0076573b`, tree `e5668c51fbc3c7aae872cafbe4759fc405fa0677` |
| Physical `gh` pin | dev-control-plane [#158](https://github.com/orenvlad-ai/dev-control-plane/pull/158) | baseline green; no-findings review; merged at `74c3e486a9154ed2e1ed44c5f752a90894a65a18` |
| Exact `AUTO_MERGE` direct-path correction | dcp-orchestrator [#34](https://github.com/orenvlad-ai/dcp-orchestrator/pull/34) | source/package green; no-findings review; merged at `04a967c26499a482fbff9a204bab046d79d2a2e2`, tree `fedee6276e8ce4a492d3c298aaf4bf843179c8bc` |
| Exact `AUTO_MERGE` pin | dev-control-plane [#159](https://github.com/orenvlad-ai/dev-control-plane/pull/159) | baseline green; no-findings review; merged at `9798eadf7bf966fd7b395279f2c779fdeb4706ae` |

Every PR was ready, exact-head reviewed, passed its repository's required CI
and merged through ordinary GitHub merge. The canonical dev-control-plane
checkout was fast-forwarded and clean after each pin merge. The two direct-path
source/pin pairs were the only bounded model-free corrections taken after newly
proven defects; neither expanded identities or budgets.

## Deterministic install receipts and integration backups

All build/install runs used the exact native arm64 package contour under the
canonical `DCP_AO_LAB_ROOT`; each ran source/provenance gates, generated parity,
the full serial Go test suite and Go build, renderer typecheck, 15 test files /
348 renderer tests, packaging, ad-hoc signing and installed-artifact preflight.

| Installed source | Integration backup | Backup manifest SHA-256 | New receipt SHA-256 |
| --- | --- | --- | --- |
| `032e16aa3025858eeddecc1a25e87d4ec8ea4f18` | `i12-20260813T112655Z` | `23598eff682331cec45b4d0f8952cd5a5c4907cc1afdeac924066dd3a0b9a5db` | `0fa241f88e4fe6aae860f8562bedf9f5a879f983ec9ef2308fb656e164455667` |
| `798e9bfb8f75846d846f2ec2d4dfc9ec0076573b` | `i12-20260813T115724Z` | `7784c1c6359ac0087facb4d78d82a4167ce593d17a020498cb2b206a5382cb70` | `75361d3998ca94f74ca9224a143193142e289164acfba637b9c22e92368cab71` |
| `04a967c26499a482fbff9a204bab046d79d2a2e2` | `i12-20260813T122812Z` | `f237643a14e0476b984d9046fdd219f341225200641907f2482dad87c4e6d166` | `bbe700c6628c5bd35cb9b4c11e2110fcd65ccc1f4c8a11e9e7847bb63e5223a5` |

The terminal installed receipt names source/tree
`04a967c26499a482fbff9a204bab046d79d2a2e2` /
`fedee6276e8ce4a492d3c298aaf4bf843179c8bc`, daemon SHA-256
`fcc05ee862f91d7e709261d8024b7004a97d40ca7b0efd81e325531ad8ca7d53`,
ASAR SHA-256
`a1206d002b16a8d9a3cb4485c4522b4fe685fdb102840d1d96530a4f11a4ff90`
and install time `2026-08-13T12:28:12Z`. Preflight passed before every start.

## Exact starting identity

All starts proved the same card/session `dcp-review-lab-12`, task
`i13-arbiter-b`, worktree
`/Users/ovlmacbook/Library/Application Support/DCP Orchestrator/data/worktrees/dcp-review-lab/dcp-review-lab-12`,
branch `ao/dcp-review-lab-12/root`, PR #9, incident and admission sequence 4.
Before the action:

- remote head and local branch head were
  `d4fcb68051ae113ed497d02151a759800ee85633`;
- current remote main was `b34b31b5443890e69128db2862726950a6bbac0d`;
- provider PR-base snapshot was
  `dbaf01b05e85ffffa4c843a905e2fe5229eaf0da`, proven an ancestor of current
  main and the exact merge base;
- the sole worktree entry was `UU canary/i13-arbiter-conflict.txt`, status
  digest `fd7d8ff8f4918e9960e5e46e01c70a877d4218b3fa1e884ecc1723935b1c9886`;
- conflict-marker bytes digest was
  `5850bba009db75bf47ff88aef2d2cecbdba89c68967f51a8cdb60f48e968dc1a`;
- index stage blobs were `ed237ce2dd2684371797e22634480ffb28dc9e77`,
  `a4c945ba7328504f2efea44f076a1407c6aa7b47` and
  `80a658c4cfc3ffda5786da316bc0bd10ffb1834f`;
- intended resolved bytes digest was
  `2a5da25a78ff8bcd9aff4493f195eaefecbc70c3d4db8902dda468ccf69e5e46`;
- no app, daemon, model child or other exact recovery/reviewer runtime existed.

## Startup fence proof and bounded direct-path failures

The first PR-32 start atomically created two quarantine rows before runtime
construction. Card 11 was `governed_terminal`, card 12 was
`governed_recovery`; each had verification count 1. The panes remained
`dcp-review-lab-11|57556|zsh|0` and
`dcp-review-lab-12|57589|zsh|0`, with zero descendants. Recovery failed before
backup/action at revision 1 because trusted path `/opt/homebrew/bin/gh` was a
Homebrew symlink. The physical regular file
`/opt/homebrew/Cellar/gh/2.87.2/bin/gh` had the same expected SHA-256
`f392d9ad8d2260c671566936b127f5436772ce16e25b091cf1fa7b301987f27e`.
Migration 0062 preserved that failure and re-armed only the same row at revision
2.

The PR-33 start again fenced both cards before restoration; verification counts
became 2/2 and no worker launched. It failed before backup/action at revision 3
because the exact preserved Git `AUTO_MERGE` ref was classified as residue.
Read-only proof established its tree
`3eba7b0dec18c759875b2b33a8d7d2379caaa6a1`, regular ref-file digest
`dac6e5a895aed94e8cd5a0f1a39b1c23f0201393e621c635ed228070710c13ed`
and conflict blob `1af18aad20e3aab90ea7f1c617d330abc3b08de9`; the blob reproduced the exact
marker bytes. Migration 0063 preserved that second failure and re-armed only
the same row at revision 4.

Copied-live SQLite migration proofs for both corrections preserved one recovery
identity and zero counters. A copied exact Git-state proof confirmed ordinary
`reset --hard d4fcb68051ae113ed497d02151a759800ee85633` removed `AUTO_MERGE` and
yielded a clean old-head basis. Neither correction started runtime before its
source and pin PRs merged and deterministic install/preflight passed.

## Sealed backup and action result

The final PR-34 start increased quarantine verification counts to 3/3 and again
created no governed worker. It atomically persisted the immutable backup at

`/Users/ovlmacbook/Library/Application Support/DCP Orchestrator/evidence/dcp-card12-cold-start-recovery/dcp-card12-cold-start-recovery-087176dbe56428dc97a99823a94daa4687c41b15c14a08de21db2c6c602f0f2f`

with manifest/row digest
`82d0e5834375c380069e7d48a7fdb2066371670d92733ce59545718469a4f3dd`.
The sealed inventory contains exactly the original conflict bytes, Git HEAD,
index, branch ref, `AUTO_MERGE`, zero-delimited status, unmerged stages and
worktree listing. Relevant member digests are:

| Member | SHA-256 |
| --- | --- |
| `git/AUTO_MERGE` | `dac6e5a895aed94e8cd5a0f1a39b1c23f0201393e621c635ed228070710c13ed` |
| `worktree/conflict.txt` | `5850bba009db75bf47ff88aef2d2cecbdba89c68967f51a8cdb60f48e968dc1a` |
| `git/HEAD` | `385ac8a67d927074b61ad352e876bdeb29f7051b28773bc3d7d7f5c485b6518a` |
| `git/index` | `a516eaeff1359d956a60300ba4a4d3b44004b3a614e7b510d5c13f66ff354826` |
| `git/branch-ref` | `657c15026f6e8f51e96e6ff6c2ae94a5d6f4031ec95f07030b52f6226cc4d810` |
| `audit/status.z` | `fd7d8ff8f4918e9960e5e46e01c70a877d4218b3fa1e884ecc1723935b1c9886` |

The one action fence changed the row to `running`, revision 6, action count 1.
The daemon restored a clean old-head basis, rebased the one intended commit on
exact current main, applied only the authorized bytes and continued
non-interactively. It produced clean local commit
`4de6ff1a0b80223a9b32a05ba68cf0b665296081` with parent
`b34b31b5443890e69128db2862726950a6bbac0d`, original subject, author and author
date, and the sole diff `M canary/i13-arbiter-conflict.txt`. Its file digest is
the intended `2a5da25a...` and the worktree status is empty.

Git retained regular pseudoref `REBASE_HEAD` containing old head `d4fcb...`;
its file digest is
`657c15026f6e8f51e96e6ff6c2ae94a5d6f4031ec95f07030b52f6226cc4d810`.
The trusted postcondition rejected it before the guarded force-with-lease push.
The row therefore became terminal `failed/model_free_action_failed`, revision
7, leaving durable `local_ref_after`, `new_head`, review and merge fields empty.
The local branch points at `4de6ff1a...`, but remote branch and PR #9 remain at
`d4fcb...`; this evidence does not authorize pushing that local commit.

## Model, review, admission and merge accounting

The two previously unauthorized native restoration calls remain immutable:

| Card | Codex thread | Reported tokens |
| --- | --- | ---: |
| 11 | `019ff9f3-cad3-73c1-bcee-293efe857349` | 33,238 |
| 12 | `019ff9f3-cbe6-71e2-8636-ea6259a7e7d1` | 33,573 |
| **Unauthorized total** | | **66,811** |

This recovery cycle added **zero worker calls, zero arbiter calls and zero
reviewer calls/tokens**. Only the one model-free action ran. Because no push
occurred, no fresh exact-head reviewer was eligible. The recovery review IDs
and check ID remain empty; there are zero ReviewRun or admission rows for local
head `4de6ff1a...`.

Admission sequence 4 remains the old immutable `incident` row at target
`d4fcb...`, old review run `ecb500ad-f9f0-443b-9d73-2c8a6350ce34`, admitted
base `dbaf...`, empty merge SHA and error `merge_conflict_or_ambiguity`. The old
review/check were not reused. PR #9 remains OPEN, CONFLICTING/DIRTY at `d4fcb...`
with only its historical successful check; there is no admission rebind and no
merge.

## Restart dedupe and terminal state

After the terminal failure, the exact app and daemon were stopped cleanly and
started once. The quarantine rows advanced from 3/3 to 4/4 before restoration;
cards 11/12 again stayed bare `zsh` shells with zero descendants. The recovery
remained `failed/model_free_action_failed`, revision 7, at `0/0/1/0`; the one
tool-path audit and one `AUTO_MERGE` audit remained unique; backup/action/review
and remote counts did not change. No worker, arbiter, reviewer, second action,
admission rebind, push or merge occurred. The app and daemon were then stopped;
the run file and canonical port are absent. The stopped terminal SQLite digest
is `d59b04b197c5e3e99c89b84b650aab560548d4fc5e2e0bca929153d43902d807`;
the installed receipt remains
`bbe700c6628c5bd35cb9b4c11e2110fcd65ccc1f4c8a11e9e7847bb63e5223a5`.

## Work not done, risks and authority boundary

- PR #9 was not updated or merged. No fresh review/check/admission rebind exists.
- The governed local commit `4de6ff1a...` is retained only as terminal evidence;
  it is not remote and must not be pushed manually.
- The trusted postcondition's treatment of post-rebase `REBASE_HEAD` is the
  remaining exact blocker. Correcting it would require new owner authority and
  a separately reviewed contract/source/pin/install cycle; this evidence grants
  none.
- No production repository, wb-core, secret, Telegram, foreign PR, replacement
  card/task/session/worktree/branch/PR/incident or arbiter decision was changed.
- Technical completion is not owner acceptance. Only the owner may record
  acceptance.
