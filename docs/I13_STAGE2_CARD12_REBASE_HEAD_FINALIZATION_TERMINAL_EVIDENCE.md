---
evidence_status: technical-blocked
captured_at: 2026-08-13T16:28:45Z
contract_commit: 9465a84ec44f72f6b7c245ebddeac22d722108ae
installed_source_commit: 15b51450b391fdc1ae0f172bbbf95275a6388030
installed_source_tree: f819398a7e78ffa68630b62a3234e6e95283be57
finalization_status: failed
finalization_error_code: provider_identity_drift
worker_calls: 0
arbiter_calls: 0
model_free_actions: 1
reviewer_calls: 0
remote_pr_head: 4de6ff1a0b80223a9b32a05ba68cf0b665296081
required_check: failed
---

# I13 Stage 2 card-12 REBASE_HEAD finalization terminal evidence

## Result

The owner-approved retained-candidate finalization cycle is technically
**BLOCKED** by a strictly human-only GitHub billing/spending condition. The
trusted daemon accepted Git's exact regular `REBASE_HEAD` semantics, adopted
the already existing clean commit without reconstruction or another local Git
write and consumed the one model-free action to push the same PR #9 branch once
with exact old-head force-with-lease. Remote branch and PR #9 now point at
`4de6ff1a0b80223a9b32a05ba68cf0b665296081`.

The post-push validator then failed closed as `provider_identity_drift` because
GitHub correctly advanced the PR-base snapshot from historical provider base
`dbaf01b05e85ffffa4c843a905e2fe5229eaf0da` to exact current main
`b34b31b5443890e69128db2862726950a6bbac0d`. The durable finalization row is
terminal revision 4 at trusted worker/arbiter/action/reviewer counts `0/0/1/0`.
No reviewer ran, admission sequence 4 was not rebound and PR #9 was not merged.

The required `dcp-review-lab` check on the new exact head failed before any
runner step on both its initial attempt and one ordinary rerun. Both GitHub
annotations state that recent account payments failed or the spending limit
must be increased. A second rerun was not attempted. The exact inspect-only
provider-base correction is reviewed, merged, pinned, deterministically
installed and fully preflighted, but its migration 0066 remains unapplied and
the bundle remains stopped. Starting it would immediately make the exact new
head eligible for the cycle's sole reviewer while the mandatory check is known
to be externally blocked; that unsafe partial continuation was not performed.

## Reviewed and merged change chain

| Stage | Pull request | Result |
| --- | --- | --- |
| Governing finalization contract | dev-control-plane [#161](https://github.com/orenvlad-ai/dev-control-plane/pull/161) | exact-head no-findings review and baseline green; merged at `9465a84ec44f72f6b7c245ebddeac22d722108ae` |
| Initial finalizer source | dcp-orchestrator [#35](https://github.com/orenvlad-ai/dcp-orchestrator/pull/35) | source/package green and exact-head no-findings semantic/security review; merged at `6f53f74f456b869c98bb82d928f671b54672808a`, tree `0fab2ee443d8bf20a0efcc524851e8c9589e6dd9` |
| Initial source pin/install guard | dev-control-plane [#162](https://github.com/orenvlad-ai/dev-control-plane/pull/162) | baseline green and exact-head no-findings review; merged at `277b1dbc57f20125b181c09dbaa787d4858b7918` |
| Audit-query direct-path correction | dcp-orchestrator [#36](https://github.com/orenvlad-ai/dcp-orchestrator/pull/36) | source/package green and exact-head no-findings review; merged at `e15a6d22f83876b240fa61889b6821bd49904f28`, tree `48d1266abc44de79bda0ca2865558d259325fc0d` |
| Audit-query correction pin | dev-control-plane [#163](https://github.com/orenvlad-ai/dev-control-plane/pull/163) | baseline green and exact-head no-findings review; merged at `51473eb5a651ac041c86901599da409126e8d7d6` |
| Revision-gate direct-path correction | dcp-orchestrator [#37](https://github.com/orenvlad-ai/dcp-orchestrator/pull/37) | source/package green and exact-head no-findings review; merged at `1f1e8cedf44d30773568f8801710f1371b14a47b`, tree `4523bfacf690c15f75c155ccfc2f14831db7b2f2` |
| Revision-gate correction pin | dev-control-plane [#164](https://github.com/orenvlad-ai/dev-control-plane/pull/164) | exact-head baseline green after its static pin audit was corrected, plus exact-head no-findings review; merged at `3e0f1e90116a5cc801dfa05758b4f17bb246fd22` |
| Post-push provider-base correction | dcp-orchestrator [#38](https://github.com/orenvlad-ai/dcp-orchestrator/pull/38) | source/package green and exact-head no-findings review; merged at `15b51450b391fdc1ae0f172bbbf95275a6388030`, tree `f819398a7e78ffa68630b62a3234e6e95283be57` |
| Provider-base correction pin | dev-control-plane [#165](https://github.com/orenvlad-ai/dev-control-plane/pull/165) | baseline green and exact-head no-findings review; merged at `ca7c28b62f787ec283af4eee6fe66801197004d1` |

Every source and pin stage merged through the ordinary protected GitHub flow.
The final canonical dev-control-plane checkout was clean and fast-forwarded to
`ca7c28b62f787ec283af4eee6fe66801197004d1` before this evidence branch. The
three direct-path source/pin pairs were each taken only after a newly proven
exact defect; none adds a worker, arbiter, second push, second reviewer,
replacement identity or general retry path.

## Deterministic installations and final receipt

Every build/install ran the source/provenance gates, generated parity checks,
full serial Go tests and Go build, renderer typecheck, 15 test files / 348
renderer tests, native arm64 packaging, ad-hoc signing and installed-artifact
preflight. The exact receipt succession was:

| Installed source | Integration backup | Previous receipt SHA-256 |
| --- | --- | --- |
| `6f53f74f456b869c98bb82d928f671b54672808a` | `i12-20260813T150956Z` | `bbe700c6628c5bd35cb9b4c11e2110fcd65ccc1f4c8a11e9e7847bb63e5223a5` |
| `e15a6d22f83876b240fa61889b6821bd49904f28` | `i12-20260813T153929Z` | `ef8926f4e2f5540a07f7415a2e5960dbdb00ebc075cb520b97836fdc7911ee7d` |
| `1f1e8cedf44d30773568f8801710f1371b14a47b` | `i12-20260813T160130Z` | `59b72fcbcbcf4f6c45030df4d8078992304886d93a8f01aca64b2c0c06f6b72d` |
| `15b51450b391fdc1ae0f172bbbf95275a6388030` | `i12-20260813T162514Z` | `ea65c53c997ea78dd3d8ab9e2582658426c3f3bdc2c6a211f008c9e1873dea69` |

The final installed receipt was written at `2026-08-13T16:25:14Z` and has
SHA-256 `b362851fb43d772a7cbd1d1a85ebeaa6980f78a5e1b96d87f6ae74bb2b5eb0dc`.
It binds source/tree `15b51450...` / `f819398...`, daemon SHA-256
`a53c4f2ad38ff2303ee5437c3fa83af80931add00443804ef58a7d6f192b62d2`
and ASAR SHA-256
`a1206d002b16a8d9a3cb4485c4522b4fe685fdb102840d1d96530a4f11a4ff90`.
The final package and preflight passed while runtime remained stopped.

## Exact retained candidate and pseudoref proof

The same card/session `dcp-review-lab-12`, task `i13-arbiter-b`, admission
sequence 4, incident, worktree, branch `ao/dcp-review-lab-12/root` and PR #9
were preserved throughout. Before the one action, remote head was
`d4fcb68051ae113ed497d02151a759800ee85633`, current main was
`b34b31b5443890e69128db2862726950a6bbac0d`, and provider base `dbaf01b...`
had the proven required ancestry.

The trusted preconditions proved clean local commit
`4de6ff1a0b80223a9b32a05ba68cf0b665296081`, parent `b34b31b...`, exact
original subject/author/date, and sole diff `M canary/i13-arbiter-conflict.txt`.
The file digest is
`2a5da25a78ff8bcd9aff4493f195eaefecbc70c3d4db8902dda468ccf69e5e46`;
the clean status digest is
`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.

Both regular `REBASE_HEAD` and `ORIG_HEAD` contain exactly old head plus LF and
have SHA-256
`657c15026f6e8f51e96e6ff6c2ae94a5d6f4031ec95f07030b52f6226cc4d810`.
There is no `rebase-apply`, `rebase-merge`, sequencer, `MERGE_HEAD`,
`CHERRY_PICK_HEAD`, `REVERT_HEAD` or bisect state. The sealed backup manifest
and durable row still match
`82d0e5834375c380069e7d48a7fdb2066371670d92733ce59545718469a4f3dd`.

After the daemon-owned guarded push, both the remote branch and PR #9 head are
exact candidate `4de6ff1a...`; remote main and PR base are exact current main
`b34b31b...`. The local branch is clean and matches the remote. No manual push,
reset, rebase, amend or reconstruction occurred.

## Quarantine, SQLite and process proof

The one live finalization start held pre-restoration quarantine at 6/6. Cards
11/12 remained bare `zsh` panes with zero descendants; no governed worker or
arbiter process launched. The bundle was stopped cleanly after the post-push
failure. At final capture the run file and DCP listener were absent, and both
governed panes still had zero descendants.

The stopped live database has goose version 65, so migration 0066 and its
provider-base recovery table are absent. The original finalization row remains
`failed/provider_identity_drift`, revision 4, at `0/0/1/0`, with empty
`provider_new_head`, review/check/merge identities. Migration 0065's immutable
audit exists once. The cold-start predecessor remains
`failed/model_free_action_failed`, revision 7, at `0/0/1/0`; its trusted new
head/local-ref-after fields remain empty. Quarantine rows are still 6/6.
Admission sequence 4 remains the old `incident` row targeting `d4fcb680...`,
with no rebind or merge. The stopped SQLite SHA-256 is
`6e6d4a491ebf82ead3d0d47782c765897100828fa96a850c6f12017e383a6236`
and its WAL is empty.

## Required check, reviewer, admission and merge

Push of candidate `4de6ff1a...` created required workflow run
[31718637023](https://github.com/orenvlad-ai/dcp-review-lab/actions/runs/31718637023).
Attempt 1 job `94509683728` and the sole ordinary rerun's attempt 2 job
`94510289136` both completed `failure` with zero steps. Their exact annotation
is: “The job was not started because recent account payments have failed or
your spending limit needs to be increased. Please check the 'Billing & plans'
section in your settings”.

PR #9 is OPEN, MERGEABLE/UNSTABLE on exact candidate/current-main head/base.
There are zero GitHub reviews and zero `ReviewRun` rows for candidate
`4de6ff1a...`. The SQLite check captured the first failed job. The old
structured review/check was not reused; admission sequence 4 remains the old
incident and its merge SHA is empty.

The inspect-only correction would first apply migration 0066, re-arm only the
same row at revision 5 with action count already one and then inspect the
already pushed candidate. It cannot re-enter the action/push path. It was not
started because the external required check is known failed and a start would
consume the sole authorized reviewer before the human-only prerequisite can
be repaired. Consequently no controlled corrected-runtime restart proof was
performed; the stopped pre-migration snapshot is the safe terminal state.

## Model and token accounting

| Activity | Calls | Tokens |
| --- | ---: | ---: |
| New finalization workers | 0 | 0 |
| New finalization arbiters | 0 | 0 |
| New exact-head reviewers | 0 | 0 |
| Model-free finalization action/push | 1 | 0 |
| Preserved unauthorized card-11 restoration | 1 historical | 33,238 historical |
| Preserved unauthorized card-12 restoration | 1 historical | 33,573 historical |
| **Preserved unauthorized total** | **2 historical** | **66,811 historical** |

This cycle added no model call and no model tokens. All earlier arbiter,
successor and fresh-worker artifacts/counters remain immutable and were not
reused.

## Work not done, blocker and residual risk

- A human must resolve GitHub account payments or the private-repository
  Actions spending limit, then establish a successful `dcp-review-lab` check
  on the unchanged exact head. The executor cannot change that account state.
- The installed inspect-only continuation was not started; migration 0066,
  reviewer, admission rebind, merge and controlled post-terminal restart were
  therefore not consumed. Resuming them requires an explicit owner instruction
  after the same-head check is green and a fresh stopped-state proof still
  matches.
- No second check rerun, reviewer, worker, arbiter, action, push, manual bypass,
  merge, replacement identity or foreign change was attempted.
- No production repository, wb-core, secret, Telegram, foreign PR, replacement
  card/task/session/worktree/branch/PR/incident or arbiter decision was touched.
- Technical status is `BLOCKED`, not owner acceptance. Only the owner may
  record acceptance.
