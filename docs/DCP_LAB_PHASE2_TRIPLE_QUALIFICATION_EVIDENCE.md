# DCP Lab Phase 2 triple qualification evidence

status: technically complete
date: 2026-08-15
scope: exact public `orenvlad-ai/dcp-review-lab` future-policy path only

## Installed authority

Managed-source PR #45 merged at source
`a96f4ba9410f088401cee8700e092f1f674ad872`, tree
`bedd8adf2508a8f8fdb692354f146d4353535c4d`. Pin/install-guard PR #178
merged at `1c8f9b0c282869b1aedf665d43cebbeaab1847da`, tree
`7afdef1a457735ee5234542f899dc679dc8988f6`. The canonical stopped
prepare/build/install/preflight sequence installed that exact source at
`2026-08-14T21:26:22Z`, created backup `i12-20260814T212622Z`, and produced
install-receipt SHA-256
`865956b3611ea6d39aa2629a247c5c2bb007f4fd38af01bd2c08becdb04a930b`.
The installed daemon SHA-256 is
`79522c20b17630f839181637cec6e535613c4ea8af01bd60b23cbd00048b21de`;
the installed `app.asar` SHA-256 is
`887f08a705f399afddaba204cad073825806fe99de51cb53f837770968274140`.
All build, source, identity, package, type, backend and frontend gates passed.

## Canonical triple

The canonical typed entrypoint submitted the three tasks once and nearly
simultaneously from common exact base
`2ef5c575b16705fb70f75d5dff47ec0f2cae21d2`. It created exactly cards and
native sessions 18-20 and reached exactly three active worker slots, never
more. Each task created a separate branch, worktree, one-line file, ready PR
and successful named `dcp-review-lab` check.

| task | card/session | worker action / launch | PR / exact head | review action / ReviewRun | admission seq | merge |
| --- | --- | --- | --- | --- | --- | --- |
| `night-ui-c` | 18 / `dcp-review-lab-18` | `dcp-model-night-ui-c-worker-1` / `f0b77107-8aa4-4943-8ed5-4066fd1437cd` | #15 / `4936753779bd63385ffaed374ff9bede77f27500` | `dcp-model-night-ui-c-review-1` / `a044d25a-327b-47c7-b722-9684cc0ed26e` | 11 | `32dd6af12ad61ab3a2ce85c1596799c6ad4ba286` |
| `night-ui-a` | 19 / `dcp-review-lab-19` | `dcp-model-night-ui-a-worker-1` / `0d34228e-c102-4f82-99d9-84886c88b833` | #16 / `292178fe855403e2bd4afd341ab12fbabe4397e2` | `dcp-model-night-ui-a-review-1` / `1796b140-a5c7-460f-9166-4c2b07246dfb` | 10 | `4b095a9ebc2219c9e3e8d04e8e644b7dc487e18a` |
| `night-ui-b` | 20 / `dcp-review-lab-20` | `dcp-model-night-ui-b-worker-1` / `0d38b38c-f9cd-470b-b468-946d553a3e75` | #17 / `6211c80a4b9e8b6ab30a38a64c4bca3ec38ef621` | `dcp-model-night-ui-b-review-1` / `be96cdae-fc69-4c94-9290-4bd06f3755b4` | 12 | `b1b58cb92f5a07413bf0077418519727cf93a1fd` |

The durable FIFO merge order was admission 10, 11, 12: PR #16, PR #15, then
PR #17. Every admission used one lease and one trusted daemon merge. Final
`origin/main` is `b1b58cb92f5a07413bf0077418519727cf93a1fd` and contains all three exact
files and values: `night_ui_a=ok`, `night_ui_c=ok`, and `night_ui_b=ok`.

The stock observer initially exposed an incomplete provider snapshot for card
20. PR #44 changed only incomplete facts to passive wait and migration 0068
immutably preserved/re-armed the exact false incident. The first installed
start then exposed a separate startup drain bug caused by correctly archived
terminal shells. PR #45 accepts terminated/exited native shells only for
already-terminal policy tasks. Its exact installed start reused the one queued
review action, claimed slot 1, created exactly one ReviewRun, obtained the
empty-findings `approved` verdict and completed the ordinary admission/merge.
Neither root-cause correction created a replacement task, worker, reviewer,
PR, admission or merge.

## Phase and restart proof

Natural UI observation during the worker runs showed all three cards in blue
Working with blue sidebar dots, with pulse only for active workers and `PR open`
remaining a Working substatus. Natural terminal observation showed merged
cards steady green in both board and sidebar and the interim typed incident
steady red in Needs You. Backend transition facts prove card 20 then moved
through `review_queued` and `review_running` before `admission_waiting` and
`merged`; the shared projection tests cover the yellow In Review and steady
green Ready to Merge mappings, full monotonic sequence, card/sidebar equality,
stale terminal summary suppression and reduced motion. The Mac display became
locked before the live yellow-frame capture, so no claim is made for an
additional screenshot.

After all three terminal merges, a controlled app/daemon restart changed the
runtime identity but preserved exactly: three merged policy tasks, six total
and succeeded model actions (three workers, three reviewers), three complete
approved ReviewRuns, three succeeded admissions, one provider-recovery audit,
zero active actions and the same three merge SHAs. GitHub still reports each
PR merged at its exact head. No duplicate activity appeared.

## Model accounting

All six actions used the installed launcher-selected `gpt-5.6-sol` profile and
reported reasoning effort `none`. Pane terminal accounting is exact:

| task | worker tokens | reviewer tokens | total |
| --- | ---: | ---: | ---: |
| `night-ui-c` | 35,161 | 19,835 | 54,996 |
| `night-ui-a` | 39,537 | 16,822 | 56,359 |
| `night-ui-b` | 16,380 | 26,001 | 42,381 |
| **Phase 2** | **91,078** | **62,658** | **153,736** |

Provider-enrichment repair, migration, build/install/preflight, passive wait
and both controlled restarts used zero DCP model calls and zero model tokens.
There was no findings repair or arbiter action in this phase.

## Result

Phase 2 is green. There are exactly three task/card/session/worker/reviewer/PR/
review/admission/merge contours, no lost change, no foreign mutation, no
duplicate identity and no active model action. The application is stopped.
The separately authorized Phase 3 ordinary future-card arbiter source work may
begin; no arbiter runtime is active at this checkpoint.
