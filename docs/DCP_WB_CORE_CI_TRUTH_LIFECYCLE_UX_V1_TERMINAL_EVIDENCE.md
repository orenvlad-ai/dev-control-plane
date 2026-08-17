# DCP `wb-core` CI truth and lifecycle UX v1 terminal evidence

evidence_status: BLOCKED

installed_correction_status: proven

canary_terminal_status: blocked-on-fresh-readmission

date: 2026-08-18

This is technical evidence, not owner acceptance. It preserves the completed
CI/UX correction and the exact forward progress of the sole authorized canary,
then stops at the first new uncontracted boundary.

## 1. Outcome

The configured-required-check defect is fixed and installed. Exact `baseline`
success on the current PR head became eligible even with unrelated skipped
Release Train jobs. Migration 0079 preserved the original
`ci_identity_failed` audit and queued exactly one fresh reviewer. That reviewer
approved the unchanged head, DCP created one FIFO admission and applied one
`release:ready` handoff without attempting a direct merge.

The canary is nevertheless terminal `BLOCKED` for this program. A preceding
unrelated WBC release advanced `main` after DCP admission. Release Train run
`32057937600` correctly refused to update or merge the stale-base handoff,
removed `release:ready` through `github-actions[bot]`, and published exact
Actions-owned readmission evidence with reason
`base-behind-after-admission`. Installed DCP then failed closed as
`release_state_drift`. Current authority contains no continuation that may
advance this existing DCP branch to current `main` and create the required new
head, fresh `baseline`, fresh DCP review and new FIFO admission. Manual branch
synchronization, a new submit and a replacement identity are forbidden.

## 2. Reviewed delivery chain

The authority PR was ordinary and non-draft:

- dev-control-plane PR #226: head
  `752d4481910b39cee4d0b5610466c94d5b02746f`, exact-head review
  `PRR_kwDOSUqHmc8AAAABJzv8Qg`, baseline run `32052167283`, merge
  `1ca282408bec53a1d696cb58d247e33285209ee9`.

The source implementation was separately reviewed and merged:

- dcp-orchestrator PR #63: reviewed head
  `b11657b24712bbf04b12cbde4f41b1c9d5530280`, review
  `PRR_kwDOTydt6M8AAAABJ0AXKw`, source/package run `32055555244`, merged
  source `93246658c34a7d5cdeb7bb42a7f3496308923608`, tree
  `828c3c6b1b5a5700bde8495a435d40ee3609ec9d`.

The immutable pin/install guard was a third ordinary non-draft change:

- dev-control-plane PR #227: head
  `653e96e3b1d52b1c71d2ef404e5b3adc7a10f5d5`, exact-head review
  `PRR_kwDOSUqHmc8AAAABJ0HNTQ`, baseline run `32056895184`, merge
  `65327c94c48482c7024a6f793012131aea216de3`.

All three reviewed heads had zero unresolved review threads before merge.

## 3. Source and model-free proof

The installed source has one provider-neutral evaluator for the configured
`RequiredCheck`; both the policy loop and terminal admission consume it. Its
fixtures prove identical eligibility for one successful exact-head `baseline`
with either many unrelated skipped jobs or no additional jobs. Missing,
pending, duplicate, malformed, wrong-head, skipped, cancelled and failed
required checks fail closed. Provider identity, required provider policy,
mergeability, exact head, review, admission and release proof remain separate.
No WBC workflow/job/matrix name is part of the DCP decision.

Source verification completed with:

- source/provenance/static governance gates;
- generated SQL/API parity;
- full serial Go tests and build, `go vet`, and race tests for changed policy,
  lifecycle, terminal-merge, session and storage packages;
- 358/358 exact renderer CI tests plus the extended 286-test lifecycle set;
- arm64 package, signature, absence and exact-artifact checks;
- live-copy migration success and exact guard rollback on identity drift; and
- dev-control-plane contract, adapter, immutable-pin and install audits.

The full renderer baseline had 1,538 passes and 25 known environment/baseline
failures: two PR-hydration failures reproduce on exact predecessor main, while
the remainder require optional `cheerio` or stripped updater fixtures. The
exact changed test sets and the packaged 358-test gate are green. Full lint
reports 272 predecessor findings; changed-code lint reports zero new findings.

## 4. Deterministic installation

The governed fence first proved the exact task/session/PR/head/worker identity,
zero active model actions and one exact app/daemon pair. Deterministic build
passed the same source and renderer gates, stopped only that proven pair,
created backup `i12-20260817T185829Z`, installed the exact arm64 bundle and
passed stopped preflight.

Installed identity:

| Fact | Exact value |
| --- | --- |
| source | `93246658c34a7d5cdeb7bb42a7f3496308923608` |
| tree | `828c3c6b1b5a5700bde8495a435d40ee3609ec9d` |
| receipt SHA-256 | `44a6a6906b24d727583f0772ff7f08058791d3b8e83272f827bba76299cbf29d` |
| daemon SHA-256 | `04d9f67ee07ac14dc4ef6c15a3310f2bc3fd07982ddfa78122a65be1839b5efa` |
| app.asar SHA-256 | `571a31794885e1d85156a1ac90104729eb324d2fbf43bb58e0bae81910fd75a4` |
| compatibility | `wb_core_compatibility=qualified` |

The controlled start applied schema migration 0079 once. The exact app/daemon
remain running, ready and healthy on port 43231; the recorded evidence PID is
ephemeral. No second daemon, database, watcher, poller or timer was introduced.

## 5. Exact canary continuity

Identity was preserved throughout:

| Fact | Exact value |
| --- | --- |
| task / card / session | `wbc-canary-v1` / `1` / `wb-core-1` |
| PR / branch | `987` / `ao/wb-core-1/root` |
| unchanged head | `e8cca45f3995b8181fe81ead154f7a933dbacbe8` |
| initial worker | sequence 71, succeeded once, 67,932 tokens |
| recovery | `wbc-canary-v1-ci-truth-recovery`, `applied` once |
| fresh reviewer | sequence 72, succeeded once, 16,594 tokens |
| ReviewRun | `1a8c6c60-4bf8-40fd-845e-19a22e878bfc`, `approved` |
| admission | sequence 31, one row |
| repair / arbiter | 0 / 0 |
| total canary model calls / tokens | 2 / 84,526 |

The original worker, task, PR, branch and commit were not recreated. Migration
0079 alone moved the false incident into reviewer eligibility. DCP then applied
`release:ready` once at `2026-08-17T19:00:23Z`. No DCP provider merge call was
eligible or attempted.

## 6. Exact blocker

The admission bound reviewed base
`45efaf76065f4364d815cb44fc15396fdf6d1f7d`. Before the canary reached the
serialized Release Train owner, an unrelated earlier release advanced provider
`main` to `fb24ce60897cbf4df27fbc460c86f1cf66d808ca`. PR #987 remained OPEN on
the unchanged head and became `BEHIND`.

Release Train run `32057937600` completed successfully as a readmission event,
not a release. Its `Prepare queued PR` job emitted:

```text
{"head_sha":"e8cca45f3995b8181fe81ead154f7a933dbacbe8","pr_number":987,"reason":"base-behind-after-admission","status":"dcp-readmission-required"}
```

At `2026-08-17T19:05:42Z`, `github-actions[bot]` removed `release:ready` and
published exactly one marker comment:

```text
<!-- wb-core-dcp-release-readmission-required base=main head=e8cca45f3995b8181fe81ead154f7a933dbacbe8 pr=987 reason=base-behind-after-admission version=wb-core.dcp-release-handoff/v1 -->
```

DCP recorded task revision 12 and admission sequence 31 as immutable
`incident/release_state_drift`; the ReviewRun terminal-merge projection is
`failed/release_state_drift`. PR #987 has only `task:standard` and
`scope:repo-only`, no merge SHA, no `release:done` and no completion proof.

This is not a Human Gate and not a Release Train defect. The repository marker
performed its required no-auto-sync/fresh-readmission behavior. It exposed a
missing DCP continuation authority after an Actions-owned readmission event.

## 7. SQLite, runtime and notification state

At the terminal readback (`2026-08-17T19:09:04Z`):

- SQLite integrity is `ok`, schema is 79;
- totals are 27 policy tasks, 44 sessions, 72 model actions, 45 ReviewRuns and
  31 admissions;
- active model actions and active worker sessions are both 0;
- canary counts are one task, one session, two succeeded actions, one approved
  ReviewRun and one incident admission;
- database main/WAL/SHM SHA-256 values are respectively
  `60ec8f3ad5fbf42b2994814806c60dbc50d2c75e0ea1a666adf35e20fd002174`,
  `e751238caef72176d0b39c2b12b77207664428bd69258ada78380feb1071eb7a`
  and `729922f2300bd5fee80471b9a1ff44717a5fe2f1a7a5bf67d05aa8b1b0664bd0`;
- the canonical local target remains clean at its admitted base, and the
  existing canary worktree is clean at the unchanged PR head; no manual target
  refresh or branch update was performed; and
- the predecessor premature stock notification remains immutable audit, is
  `read`, and was resolved at `2026-08-17T19:02:52Z`; no new generic
  `ready_to_merge` notification was created.

The installed read model returned the current policy state as `incident`, so
the shared card/sidebar/details/accessibility projection is steady and
non-animated. Model-free component tests prove workflow motion during queued,
CI, review, admission and Release Train waits while `modelActive` remains false
for passive waits; reduced motion retains the phase and accessible status.

## 8. Safe continuation boundary

One separately owner-authorized DCP follow-on is required: define and implement
a typed fresh-readmission continuation for an exact Actions-owned
`wb-core.dcp-release-handoff/v1` readmission event. It must preserve the existing
task/session/PR/worker/review/admission/incident history, advance only the same
branch from the newly proven provider `main` under an exact lease, create a new
head without product edits, require a fresh successful `baseline`, queue one
fresh context-free review, create a new FIFO admission and apply a new exact
`release:ready`. It must fail closed on conflict, head/event/actor drift or any
non-exact provider fact and must add no second initial worker, submit, card,
session, PR, Release Train or direct merge authority.

No WBC file/workflow change is required to fix this blocker. The configured-
required-check seam remains independent of both the current complex Release
Train topology and any future simplification of its non-required jobs.

## 9. Exclusions preserved

This pass made no manual WBC repository/branch/PR/label/merge change, no new
submit, no second initial worker, no repair or arbiter call, no production or
deploy action, no SSH/secret/runtime/business-data access, no legacy cleanup,
no model-ceiling change and no owner-answer synthesis. Platform approval count
remained 0. The sole visible direct executor task was
`01a00a71-8fad-7c43-b024-be3d9f81ee5e`; no collaboration subagent was used.
