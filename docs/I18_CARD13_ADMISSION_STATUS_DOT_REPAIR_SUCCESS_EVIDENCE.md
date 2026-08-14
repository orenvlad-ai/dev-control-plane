# I18 card-13 admission/status-dot repair success evidence

evidence_status: technical-complete
evidence_date: 2026-08-14

## Reviewed source and integration

- Managed-source PR [#40](https://github.com/orenvlad-ai/dcp-orchestrator/pull/40)
  added the event-driven unchanged-SCM admission catch-up and shared native
  status-dot projection. Exact source
  `70187c13ab0bc8bac07cd2d9ff27e230b866e087`, tree
  `ee81758b33443a66835f785e2cb178b560808c15`, passed exact-head review and
  required source/package run `31781881915`.
- Managed-source PR [#41](https://github.com/orenvlad-ai/dcp-orchestrator/pull/41)
  retained fail-closed startup quarantine while accepting the already proven
  cards-11/12 terminal lifecycle pair. Exact source
  `50136576ce287ed0563b54144523ec14ab34d76c`, tree
  `db4ee06ad176c91402cfc852cc63e1e2252148f3`, passed exact-head review and
  required run `31783935999`.
- Managed-source PR [#42](https://github.com/orenvlad-ai/dcp-orchestrator/pull/42)
  retained provisioned creation-base metadata and added the exact passive
  card-13 startup correction. Reviewed head
  `705697df72f4954140904698273587c31cf65ac1`, review `4935928889` and required
  run `31788673005` passed before ordinary merge at exact source
  `f54b597572d7204096cb16581becee067e1febdc`, tree
  `a56f684853989623fe84c15f2a7958ffa03fd95e`.
- Integration pin/install-guard PRs #170, #171 and #172 merged normally at
  `d83fa53ff5aaa32b64d54c97ed6dc3bae41e7c39`,
  `31179d321dffcbdba12c1a216a9c9af436d4513c` and
  `8cd8e684efbde69f94d95c57ed1546ca546f450f`. Final PR #172 exact head
  `6328d183976b59e48c4646a10950fe0a30bcd98c`, review `4936030836` and baseline
  run `31789635532` passed before merge. The clean canonical checkout was
  fast-forwarded to `8cd8e684efbde69f94d95c57ed1546ca546f450f` before
  installation.

## Root cause and bounded repair

Card 13 exposed two serial fail-closed preconditions. Its admission was created
after the stock observer had already acknowledged materially clean provider
facts; later unchanged fresh snapshots did not re-enter lifecycle, so no
terminal eligibility signal reached the new waiter. PR #40 reuses that existing
SCM event and emits only an idempotent exact-session eligibility signal. The
existing terminal merger, process mutex and SQLite FIFO lease still own every
claim and merge.

The first repaired event then exposed the hidden terminal gate: provisioning
resolved the exact creation base, but stock lifecycle `mergeMetadata` discarded
`diff_base_sha` and `diff_base_ref` before persistence. PR #42 retains both
fields for future tasks and repairs only the unchanged card-13 row when every
card/task/session/worktree/branch/PR/head/base/review/admission/check identity
matches and zero DCP model actions are active. It adds no timer, heartbeat,
watcher, poller, service, merge authority or model call.

## Shared status-dot semantics

One shared native session visual-status mapper drives both central-card and
sidebar dots. A running worker is blue with a gentle pulse and a running
reviewer is yellow with the same active-only pulse. Queued worker/reviewer
states are steady blue/yellow; needs-you, review-pending and admission/merge
waits are steady orange; merged is steady green; failed, incident and exited
are steady red; truly idle is steady gray. CSS animation changes no layout and
`prefers-reduced-motion` removes the pulse while retaining color, state and
accessible text.

Backend tests cover pending-to-waiting followed by one existing-SCM-event
drain/merge, repeated snapshot and new-engine restart dedupe, FIFO preservation,
creation-base retention and the exact passive startup correction including its
active-model fail-closed gate. Renderer tests cover active worker/reviewer,
queued/waiting/merged/incident states, central/sidebar parity and reduced
motion. Source build verification passed `go test -p 1 ./...`, `go build ./...`,
renderer typecheck, generated SQL/API checks, the mandatory 15-file renderer
suite at 349 tests, and the required source/package gates.

## Deterministic installed proof

- Exact source `f54b597572d7204096cb16581becee067e1febdc`, tree
  `a56f684853989623fe84c15f2a7958ffa03fd95e`, was deterministically prepared,
  built, installed and preflighted at `2026-08-14T09:55:20Z`.
- Verified backup: `i12-20260814T095519Z`.
- Install-receipt SHA-256:
  `5f8ce03ca79da650c23c4968eae2e1e9c3deed05dcd57c6d08e108bbe2c6a782`.
- Installed daemon SHA-256:
  `230f14f8b44a5d258367e419dd54d74799fd7e9b754e1b71ff7f73f64694525b`.
- Installed ASAR SHA-256:
  `e9fccb9528ee6babc28bda013a32120d786968081045dd72c04fb14f7dc1abc6`.
- Prestart proved card 13 revision 9/admission waiting, the original two
  succeeded actions, zero active model actions, one exact review and no lease
  or merge. Cards 11/12 were exact quarantined terminal shells.

One controlled canonical start repaired only the empty session creation base to
`5bfd20d3b3f5b7d9d9ccb02500b742a917e6ea01` / `origin/main`. The existing event
path then claimed the same FIFO admission and merged the same reviewed PR once.
No worker, reviewer, arbiter or other model action launched.

## Exact terminal identity and dedupe

- Policy task `chat-probe-b`; session/card `dcp-review-lab-13` / 13; branch
  `ao/dcp-review-lab-13/root`; PR
  [#10](https://github.com/orenvlad-ai/dcp-review-lab/pull/10).
- Original and final reviewed head:
  `e467d1a44668294d59cca15a756c6cef18e4b247`; original provider base:
  `5bfd20d3b3f5b7d9d9ccb02500b742a917e6ea01`; required `dcp-review-lab` check:
  `SUCCESS`.
- ReviewRun `152048c0-6720-4397-9430-df975a453807` remains the sole exact-head
  review, `complete` / structured `approved`, no findings, terminal merge
  `succeeded`.
- Admission `dcp-admission-152048c0-6720-4397-9430-df975a453807`, sequence 5,
  is `succeeded` with the same review/head/base, lease
  `dcp-merge-dcp-admission-152048c0-6720-4397-9430-df975a453807`, refresh count
  0 and no error.
- PR #10 is `MERGED` once at `2026-08-14T09:55:55Z`; exact merge commit and
  remote `main` are
  `1b3f9fb266370326bbb35283fb51fb5226502c42`.
- The durable task is `merged`, revision 10, repair count 0, with the same head,
  review, admission and merge identities. All five admissions are succeeded;
  none is active.
- Model actions remain exactly two: one succeeded initial worker and one
  succeeded reviewer; active actions are zero. Exact review runs remain one.
  Additional worker/reviewer/arbiter/model calls and additional model tokens:
  **zero**.

A controlled stop/start dedupe pass retained task revision 10, the same lease,
review and merge, two total/zero active actions, one review and one remote merge;
quarantine advanced exactly from 13/13 to 14/14. The installed deterministic
DOM fixture then passed 3 focused files / 140 tests against the identical ASAR,
including the current merged state and shared status semantics. The canonical
application and daemon were stopped after proof; port 43231 has no listener.

No new task/card/PR, worker/reviewer/arbiter call, manual merge, historical
cleanup, production deploy, hosted surface or foreign-repository mutation was
performed. This record establishes technical completion only; manual owner
acceptance remains separate.
