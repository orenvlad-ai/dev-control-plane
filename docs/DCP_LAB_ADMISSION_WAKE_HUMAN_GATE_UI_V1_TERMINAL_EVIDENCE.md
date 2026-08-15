# DCP Lab admission wake and Human Gate UI v1 terminal evidence

status: technically qualified; owner acceptance is separate
date: 2026-08-15
scope: exact public `orenvlad-ai/dcp-review-lab` policy tasks only

## Result

The bounded correction is technically green. Exact installed source
`5def887cb1c240ca309c4c5ff7bd6298af4784ee`, tree
`885af5298339e8562a22a78f8538cd1c1da4b6e1`, let the existing trusted daemon
skip terminal Human Gate admission 19 and merge the three already-approved
waiters strictly FIFO as sequences 20, 21 and 22. A controlled restart retained
all task, review, admission and merge identities without duplicate activity.
The canonical bundle is stopped after proof.

This is technical evidence, not owner acceptance. Only the owner may state
`Задача принята`.

## Preserved predecessor and first-start failure

Before source or runtime mutation, the running predecessor was re-proved as
source `5691978bf37cb6de2b02243a40f9bac51161db25`, tree
`f35bc7cd5858403ad71b9c2577927624ef12cb39`, receipt SHA-256
`f74bc9f80c8a27dd3f9dc56c6becda61bd96bac737942a6579c85efee1184a51`.
The canonical evidence directory
`i20-admission-wake-human-gate-prechange-20260815T052209Z` preserves a
consistent database, receipt and the unlocked pre-change UI image
`live-ui-prechange-20260815T052629Z.jpeg` (SHA-256
`7af1c8f2dee05ec2fbf25e107c96594ced1d9a0c842da25e9f77acaef627d2a4`).
That image records the incorrect red `Review failed` projection for card 27
and the already-approved cards 28-30.

Managed-source PR #54 added the post-commit wake and shared Human Gate
projection. It merged at source
`e7497c954baeb38ef494b2346046dc4d21e8f5e3`, tree
`52a6037bfde5272d2eea9bfa21909d04201b9a11`; pin/install-guard PR #191 merged
at `d2fcd7445a03f7dabd24bc0a9601b93efcc22c10`. Its deterministic install
produced receipt SHA-256
`dc2fc68b0a66ebaa94862ce4dbc9c792c84009ac514b186803d958a26c13f3c9`.
The first controlled start launched no model action but left sequences 20-22
waiting. Evidence directory
`i20-first-installed-start-sql-claim-block-20260815T0628Z` preserves that
immutable failure.

Copied-live model-free reproduction proved the second root cause exactly:
the Go selector skipped terminal Human Gate sequence 19 and refreshed PR #25
as `MERGEABLE/CLEAN`, but the final atomic claim predicate still rejected the
presence of every `incident` row. The claim returned no owner and performed no
mutation. Restarting was not used as a workaround.

## Reviewed delivery identities

- The original contract merged through control-plane PR #190 at
  `f0f895a9...`.
- Managed-source PR #54 exact head
  `9dadb9cf7715975b547807528f2f61ebc49d50a5` passed exact-head review
  `PRR_kwDOTydt6M8AAAABJqA1dg` and workflow `31868030897`, then merged as
  source `e7497c954baeb38ef494b2346046dc4d21e8f5e3`, tree
  `52a6037bfde5272d2eea9bfa21909d04201b9a11`.
- The exact claim-boundary amendment merged through control-plane PR #192 at
  `b9801a0c69d579e4d5254ecba2954025467faff4` after exact-head review
  `PRR_kwDOSUqHmc8AAAABJqFySQ`.
- Managed-source PR #55 exact head
  `1faad9882dd5bbb3f0486545bb2e26d511aaea16` passed review
  `PRR_kwDOTydt6M8AAAABJqGR4Q` and workflow `31869526221`, then merged as exact
  source `5def887cb1c240ca309c4c5ff7bd6298af4784ee`, tree
  `885af5298339e8562a22a78f8538cd1c1da4b6e1`.
- Pin/install-guard PR #193 exact head
  `ff8cab3881ada1c2f467128bf6e588fb9a73d077` passed review
  `PRR_kwDOSUqHmc8AAAABJqHWuA` and baseline workflow `31869987051`, then merged
  at `c9df0e5c76b1c13eb378d8782fdde177e50a2883`, tree
  `170e8f585114cbe20dfb3e0aa102e004e508aebe`.

The final deterministic build repeated source/provenance/identity gates,
generated sqlc/OpenAPI parity, all Go tests and build, frontend typecheck,
15 required renderer files with 352 tests, packaging and signing. Installation
created backup `i12-20260815T064429Z`; model-free preflight then proved the
exact installed contour. The final receipt is:

```text
installed_at=2026-08-15T06:44:30Z
fork_commit=5def887cb1c240ca309c4c5ff7bd6298af4784ee
fork_tree=885af5298339e8562a22a78f8538cd1c1da4b6e1
daemon_sha256=b4b375cff1d1e861f9586ca927e8d190b2b4a2decc350f7aecef39fda997f7d0
asar_sha256=8bd36d0afcf2f14488dae1f8a49de6f993f5906096a24e099d3bb2faa2b44cb4
receipt_sha256=15b72e71a32863c946a9e6ccf87343bd995d53fe472b2654215ab988696cba9e
```

## Deterministic regression proof

The managed source covers all contract boundaries:

- a newly committed exact admission emits one post-commit eligibility signal;
- concurrent review completion, SCM delivery and replay retain one admission,
  one claim and one merge owner;
- exact latest Human Gate releases the next minimum FIFO waiter, while pending,
  running, failed, stale, foreign and mismatched incidents still block;
- two concurrent real-SQLite claims after release yield exactly one owner;
- sequences 20-22 and three non-overlapping PRs sharing an old base advance
  through fresh canonical/provider facts without lost changes;
- unknown, stale, foreign and ambiguous identities fail closed;
- Human Gate overrides stock `Review failed`, uses shared board/sidebar
  Needs You / Needs your decision state and a steady orange non-pulsing dot,
  including reduced motion; genuine failures remain red.

In addition to the required package suite, the exact installed source's focused
Human Gate DOM/state run passed 155/155 tests across shared presentation,
board, sidebar and workspace-query fixtures. The packaged `app.asar` has the
receipt-bound SHA above and contains `status.human_gate = Needs your decision`.

## Live FIFO qualification

Immediately before the corrected start, SQLite still held 47 model actions,
33 ReviewRuns, 22 admissions and zero active model actions. Sequence 19 was
the unchanged terminal incident and sequences 20-22 were waiting. One start of
the exact installed bundle produced this trusted order:

| seq | task/card | PR/head | admitted base | terminal merge |
| ---: | --- | --- | --- | --- |
| 20 | `manual-triple-a` / 28 | #25 / `f61ead3aeb9900a1142e237b1ed75b6be787e5c2` | `e7056f5f0328e041f9f81aa420ab22f713acecdf` | `eaf457d70f4cb94cc81a3a4cbd3a5bdfd821cf04` |
| 21 | `manual-triple-b` / 29 | #26 / `33969ae8d066cc6eccb17858d2204ef897c74664` | `eaf457d70f4cb94cc81a3a4cbd3a5bdfd821cf04` | `a433d0b8f06293b39c07db1ce677ae4f049fede5` |
| 22 | `manual-triple-c` / 30 | #27 / `c914f1a8d3f85b6ccc6e8bf9b6578641956ff2dc` | `a433d0b8f06293b39c07db1ce677ae4f049fede5` | `80e98e06d1f4717589dbefde974c37da46780d28` |

GitHub records the corresponding merge times as 06:45:44Z, 06:45:52Z and
06:45:59Z. Remote `main` is the final merge
`80e98e06d1f4717589dbefde974c37da46780d28` and contains exact bytes:

```text
qualification/manual-triple-20260815-a.txt = manual-triple-a=ok
qualification/manual-triple-20260815-b.txt = manual-triple-b=ok
qualification/manual-triple-20260815-c.txt = manual-triple-c=ok
```

Tasks 28-30 are `merged` revision 10 with repair count zero. Their existing
worker and reviewer actions remain exactly one succeeded row each. No
replacement card/task/branch/PR, repair, review, arbiter or manual merge was
created.

## Human Gate and installed UI proof

Admission 19 remains `incident/merge_conflict_or_ambiguity` with no lease or
merge. Card 27 task `arb-c-right` remains `incident` revision 10, repair count
zero, PR #24 exact head
`58adc8c6abe1d2fee90cd1bfa9addd149cede1a8`. GitHub still reports PR #24 open,
ready, required check successful and `DIRTY`; no owner answer or mutation was
made.

After both live starts, the installed daemon API exposed the exact typed state:

```text
status=review_failed
dcpPolicyState=incident
dcpArbiterStatus=human_gate
dcpArbiterGeneration=1
dcpArbiterIncidentKind=merge_conflict_or_ambiguity
dcpArbiterCohort=[arb-c-left, arb-c-right]
dcpHumanGateQuestion=Should qualification/arbiter-c.txt on main remain mode=left or be replaced with mode=right?
```

The raw stock failure is intentionally preserved, while the shared exact
Human Gate projection has precedence and yields board/sidebar Needs You,
primary label `Needs your decision`, steady orange and the durable details.
The Mac was locked during post-install visual capture, so no post-install live
screenshot is claimed. The receipt-bound packaged artifact, installed API and
155 passing DOM/state tests provide the contract-authorized UI fallback; they
do not substitute for, and were not used instead of, the completed functional
live queue qualification.

## Restart, dedupe and final state

The post-merge controlled restart preserved admission statuses, merge SHAs and
timestamps exactly. Counts remained 47 model actions, 33 ReviewRuns and 22
admissions, with zero active model actions. The five future arbiter rows still
sum to five historical calls; card 27 generation 1 remains the same single
Human Gate call. Thus this correction added zero model calls and zero tokens.
All worker/reviewer panes for cards 27-30 were bare `zsh` with no model child.

The final stopped database and receipt are preserved beneath
`i20-admission-wake-human-gate-terminal-20260815T0648Z`; their SHA-256 values
are respectively
`15cbe955fc33de616b552228ca70b9a9876e2ff6c0671dfbf48c4f134bedbb0f`
and
`15b72e71a32863c946a9e6ccf87343bd995d53fe472b2654215ab988696cba9e`.
After proof the exact canonical application was stopped cleanly: its run file
is absent, port `127.0.0.1:43231` is not listening and active model actions are
zero.

## Residual boundary

No technical blocker remains for this bounded correction. The Mac lock
prevented a new live screenshot, which is recorded without overclaiming and is
covered by the contract-authorized installed artifact/API/DOM proof. The
separate Phase-4 card-26 ephemeral token-accounting acceptance remains the
previously recorded terminal `BLOCKED`; this correction does not recreate or
alter that evidence. Owner acceptance remains outstanding.
