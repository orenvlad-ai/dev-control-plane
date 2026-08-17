# DCP `wb-core` Release Train handoff v1 terminal evidence

evidence_status: BLOCKED

date: 2026-08-17

scope: installed stopped DCP target, fail-closed compatibility lock and exact WBC follow-on

## 1. Terminal outcome

DCP now contains the owner-reviewed static target `wb-core` / `repo-only` for
exact public `orenvlad-ai/wb-core`, repository ID `1201929580`, owner ID
`237411244`, default branch `main`, labels `task:standard` plus exactly
`scope:repo-only`, and required check `baseline`.

The installed contour is intentionally not eligible for a substantive submit.
Exact WBC main `93ef7ba6afa11871d9bad1636a7c452d39776f0c` does not publish marker
`wb-core.dcp-release-handoff/v1`. Canonical submit therefore fails before app,
daemon, native task, card, session, model action or SQLite mutation. Terminal
status is exactly `BLOCKED` on one separately bounded WBC Release Train
compatibility task. This is not a Human Gate and is not owner acceptance.

No WBC file, branch, label, pull request, task, card, model call, merge or
release was created or changed by this preparation.

## 2. Reviewed delivery chain

Every completed mutation boundary used one ordinary non-draft pull request,
exact-head review and the required workflow. No protection or review bypass
occurred.

| Boundary | Exact head | Exact-head review and workflow | Ordinary merge |
| --- | --- | --- | --- |
| contract PR [#218](https://github.com/orenvlad-ai/dev-control-plane/pull/218) | `b3d5368e6274e4017162a4e83da922a911e90544` | `PRR_kwDOSUqHmc8AAAABJw8NCg`; baseline `32016039417` | `036b1101284f626c931f7edb1750ddd228634832` |
| managed-source PR [#62](https://github.com/orenvlad-ai/dcp-orchestrator/pull/62) | `816320a7a88496f4ebbbea3e295a0a9bcf14015d` | `PRR_kwDOTydt6M8AAAABJxSgIw`; source/package `32019792026` | source `99e8243ac66bfdd7e77538368403d0a3b5964c21`, tree `81b391c80eef98c5723340a1da8e42a3da1bbaec` |
| pin/install-guard PR [#219](https://github.com/orenvlad-ai/dev-control-plane/pull/219) | `7447c4517238b05bc77bb3dea0fb2b0ad61fb483` | `PRR_kwDOSUqHmc8AAAABJxmDHw`; baseline `32023651860` | `4fa942190385026d1e7f8e603940e6f625fc4e21` |

The source/package gate included generated-source verification, backend build,
Go race/vet/tests, frontend typecheck, 356 renderer tests and packaging. The
installed exact-source focused suites for policy submit, repository identity,
SQLite migration, GitHub Release Train action and terminal merger also pass.
The repo-owned I9, I12 and I27 contract/install audits pass.

## 3. Deterministic stopped install

The canonical stopped sequence `prepare -> build -> install -> preflight`
created backup `i12-20260817T111735Z`. The installed receipt is bound to:

- managed source `99e8243ac66bfdd7e77538368403d0a3b5964c21`;
- source tree `81b391c80eef98c5723340a1da8e42a3da1bbaec`;
- receipt SHA-256
  `97c4b6c000fa51c571586c39ed1d096adc7fdcdd5838d8c0ad4e15006a96a9d6`;
- daemon SHA-256
  `b6378d0a01be13332e81f6184e3a1d647361b9fa1a9db37126178f5971cbd089`;
- `app.asar` SHA-256
  `eb1c3a7a927c64ff8f9afdce85617c2e394c027e43be9ff0c2067704fd87559e`.

The installed source checkout is clean. The exact receipt hashes equal the
installed daemon and `app.asar`. Final stopped preflight passes and reports
`wb_core_compatibility=blocked`.

## 4. Migration, history and zero-state proof

One governed model-free start registered the native project and applied
migration 0078 exactly once. The authority row binds target `wb-core`,
repository `orenvlad-ai/wb-core`, profile `repo-only`, repository/owner IDs
`1201929580` / `237411244`, required check `baseline`, release actor
`wbc-github-actions-release-train` and compatibility marker
`wb-core.dcp-release-handoff/v1`.

After graceful stop, SQLite integrity is `ok`, schema is 78 and SHA-256 is
`2363c7ed05048c5f01977043f17d4524feceec26feefd6819f69fe3a528ad71f`.
The preserved contour contains:

- 26 policy tasks: 25 merged and one terminal incident, with zero nonterminal;
- 70 model actions: 67 succeeded, three failed and zero queued/claimed/running;
- 44 ReviewRuns with zero running;
- 30 admissions with zero active;
- 43 native sessions with zero active;
- six native projects, including exactly one clean `wb-core` project;
- zero `wb-core` task/session/action rows.

These historical counts already existed at the PAUSED_SAFE/resume checkpoint.
The I27 registration added only the governed native project and migration
authority; it did not create or replay a historical product or model action.

## 5. Locked canonical-submit proof

The clean read-only WBC checkout has `main` and `origin/main` both at exact
`93ef7ba6afa11871d9bad1636a7c452d39776f0c` and contains zero compatibility
marker matches. One canonical model-free submission probe using a reserved
proof-only task ID exited nonzero with the exact missing-marker error.

Before and after the rejection, SQLite SHA-256 was identically
`56f23f070e83564d51798cc236f5f799e02c30fab86041ff3985c680768dd2fa`.
The proof task does not exist; WBC task/session/action counts remain zero; the
gateway lock is absent; and app, daemon, run-file and port 43231 remain stopped.
This proves the compatibility fence is before native and model mutation.

## 6. Release authority and UI mapping

The installed typed target makes the DCP terminal merger statically ineligible
for `wb-core`. Focused exact-source regressions prove that the DCP path never
calls `MergePullRequest` for this target, fails closed on head or label drift,
and survives restart without duplicate handoff.

Only after exact-head review, successful `baseline` and FIFO admission may DCP
add `release:ready`. The WBC GitHub Actions Release Train is the sole physical
merge/release actor and alone adds terminal `release:done` plus the exact merge
completion proof. DCP only observes those GitHub facts. Admitted, waiting and
release-running cards project to Ready to Merge; Merged requires exact merge
SHA, `release:done` and the completion proof. No second release train, fallback
merge or manual DCP merge exists.

## 7. One exact bounded follow-on WBC task

Change only `orenvlad-ai/wb-core` to publish and enforce repository-owned marker
`wb-core.dcp-release-handoff/v1` for the existing GitHub Actions Release Train:

1. never auto-sync, update or merge a DCP-admitted PR at a head different from
   the exact head bound to its current DCP review and FIFO admission;
2. when base/head drift makes the admitted head behind or otherwise replaces
   it, remove release eligibility and return it to DCP for a fresh successful
   `baseline`, fresh exact-head DCP review and new FIFO admission before
   restoring `release:ready`;
3. keep the WBC Release Train as the only actor that physically merges and
   writes `release:done` with the existing exact completion proof;
4. add model-free tests for no-auto-sync, head-drift readmission, exact-head
   release eligibility and terminal proof, then publish the marker in the
   repository authority consumed by DCP.

The follow-on has no WBC product feature, business/runtime data, production,
SSH, secrets, DCP direct-merge authority or retired watcher/orchestration
scope. Until its ordinary reviewed WBC merge reaches current `main`, canonical
WBC submit remains locked.

## 8. Final stopped boundary

The exact app process, daemon, run-file, port 43231 listener and SQLite WAL/SHM
sidecars are absent. The canonical DCP bundle is stopped and model-free
preflight-ready. Existing targets, aliases, tasks, sessions, actions, reviews,
admissions, incidents and Human Gates were preserved. Production, hosted
systems, secrets, runtime/business data and product execution remained outside
scope.

During final self-review, one unexpected exact installed app/daemon restart was
detected. Process/run-file provenance was exact, model-action and active-session
counts were zero, and the pair was gracefully stopped through the governed
stop fence. It created no WBC or model activity; the clean checkpoint changed
only the physical final SQLite digest recorded above while every governed count
and identity remained stable. The launch cause was not attributed, so future
install operators must retain the same final process/port/run-file/sidecar gate.

## 9. Separately proven unblocking event

current_unblock_status: COMPLETE

current_project_identity_status: COMPLETE

Sections 1 through 8 are preserved predecessor evidence: at that checkpoint the
missing WBC marker correctly made the contour `BLOCKED`. They are not rewritten
as if the compatibility defect or its fail-closed response never existed.

WBC PR [#984](https://github.com/orenvlad-ai/wb-core/pull/984) subsequently
published `wb-core.dcp-release-handoff/v1` in
`docs/architecture/11_github_release_train.md`,
`apps/github_release_train.py` and `apps/github_release_train_spec.py`. Its
exact head `4e260505a8392a2817542beb720bd3d86cecb9b7` passed `baseline`. Release
Train run `32030649900` completed the repo-only selection, preparation and
merge jobs; `app/github-actions` physically merged exact WBC main
`4735f74aedf1a1374dd4c8503799dd0761a61f22`, applied terminal
`release:done`, and wrote completion proof
`<!-- wb-core-release-completion-proof contour=repo-only merge=4735f74aedf1a1374dd4c8503799dd0761a61f22 pr=984 -->`.
Thread-aware readback found zero unresolved review threads. GitHub exposes no
PR review objects for #984, so this evidence does not invent a review ID; the
exact-head baseline, Release Train run, merge actor, label and proof are the
independently verified terminal facts.

The canonical read-only WBC target is clean, with `main` and `origin/main` both
at `4735f74aedf1a1374dd4c8503799dd0761a61f22`. All three required marker files
are present (`marker_files=3`). Installed DCP source, tree and receipt remain:

- `99e8243ac66bfdd7e77538368403d0a3b5964c21`;
- `81b391c80eef98c5723340a1da8e42a3da1bbaec`;
- `97c4b6c000fa51c571586c39ed1d096adc7fdcdd5838d8c0ad4e15006a96a9d6`.

Canonical model-free preflight reports `wb_core_compatibility=qualified`, and
the direct compatibility gate passes. Before and after target readback and
preflight, SQLite SHA-256 is identically
`2363c7ed05048c5f01977043f17d4524feceec26feefd6819f69fe3a528ad71f`;
integrity is `ok`, schema is 78, the immutable handoff authority row exists,
and `wb-core` policy-task/session counts plus queued/active model-action counts
are all zero. No WBC task, card, submission or model call was created.

Unlike the predecessor stopped checkpoint, readback found the exact installed
app and daemon running, ready and healthy on port 43231. PID and uptime are
ephemeral; no launch cause is asserted. This docs/evidence-only pass neither
stopped nor restarted the runtime and changed no installed artifact or SQLite
state.

The compatibility blocker is therefore technically cleared. The contour is
ready for the first separately owner-authorized `wb-core` / `repo-only` canary
under the existing DCP contract. `COMPLETE` here is technical status only, not
authorization to submit that canary and not owner acceptance.

## 10. First-canary project identity drift incident

incident_status: blocked-before-reservation

The first separately authorized submit used task id `wbc-canary-v1`. The
marker-only shell preflight reported `wb_core_compatibility=qualified`, but the
installed daemon rejected the request as `DCP_POLICY_TARGET_INVALID` before
reservation. No immutable task/card/session identity was returned and no retry
was made.

Read-only inspection proved a cross-layer identity split. The existing native
project held the adapter-produced `agentRules` value of 912 UTF-8 bytes,
SHA-256
`a95e9a731d483d78d9d4e66c0663c9fb148e244ae5a93c4b0f1a22ea933593ec`.
Exact installed and pinned managed source
`99e8243ac66bfdd7e77538368403d0a3b5964c21` requires the compile-time
`DCPWBCRepoOnlyPolicyAgentRules` value of 1149 bytes, SHA-256
`2e4b0d69593c004a4becb532ed07d59e9be087af884cdfea523fb3e918a84a64`.
`ReviewRepositoryValidator` compares these values exactly. The shell preflight
checked only the WBC marker and therefore made a false readiness claim.

The canonical target remains clean at exact current WBC main
`c20dc4b34a198116964516e0dc76b98b094e36eb`, equal to `origin/main`; provider
identity remains exact public `orenvlad-ai/wb-core`, repository/owner IDs
`1201929580` / `237411244`, and all three compatibility markers are present.
SQLite is integrity `ok`, schema 78 and still has SHA-256
`2363c7ed05048c5f01977043f17d4524feceec26feefd6819f69fe3a528ad71f`.
`wbc-canary-v1` rows, `wb-core` policy tasks/sessions/actions and active model
actions are all zero. The exact installed app/daemon remain running, ready and
healthy on port 43231; this incident pass did not stop or restart them.

A regression first reproduced the old adapter mismatch as `912 != 1149` and
then passed after binding adapter output to the immutable source-lock byte count
and digest. The corrected model-free preflight now reports
`wb_core_compatibility=blocked` against the still-stale registered project,
with the database digest unchanged before and after. Current technical status
therefore returns to `BLOCKED`, not Human Gate, until the ordinary reviewed
dev-control-plane change merges and the existing native project is reconciled
once through the locked model-free registration path. No managed-source change,
application rebuild, install, WBC write, submit or model call is authorized.

## 11. Reviewed reconciliation and native normalization finding

reconciliation_status: config-correct-guard-merge-pending

Dev-control-plane PR #222 exact head
`7de78a72293782bdaa2c212b049dee151eb7c8bc` passed exact-head semantic/security
review `4952605261`, baseline run `32045273071` and zero unresolved threads,
then merged the source-lock, adapter and registered-project readiness authority
at exact merge `0d2088c982dba5003cf9dbb723e756edc0debfed`. Only after that merge, the locked
model-free `register-wb-core` path ran once against the existing native project.
It did not create a project, task, card, session or model action and did not
stop, restart, rebuild or install the app.

The native CLI persisted the correct 1149-byte policy with SHA-256
`2e4b0d69593c004a4becb532ed07d59e9be087af884cdfea523fb3e918a84a64`.
It also materialized its exact empty defaults: `agentConfig: {}`,
`orchestrator: {agentConfig: {}}`, `trackerIntake: {}` and
`containerReap: {}`. The first guard compared the full stored JSON to the
minimal adapter input and therefore reported a second false `blocked`, even
though the installed daemon ignores those empty defaults and its policy fields
now match exactly. The reconciliation command was not repeated.

A new model-free regression reproduced that native-normalization false negative
before the bounded guard correction. The correction accepts only absence or
those named exact empty forms while retaining exact equality for every policy,
worker, reviewer, path, repository and kind field. Branch-local preflight then
reported `wb_core_compatibility=qualified` against the actual registered
project. Main database, WAL and SHM digests were byte-identical before and
after that read-only preflight:

- main `2363c7ed05048c5f01977043f17d4524feceec26feefd6819f69fe3a528ad71f`;
- WAL `c22d7aa47c772d7a6b00752f3d351320dc7cceda210ba9e1c81cfbbca0ae734e`;
- SHM `7120278615487bd41a5b97ba49f3c3857ef6b34ff7db89aa65aa0f5e05592172`.

SQLite remains integrity `ok`, schema 78; `wbc-canary-v1`, `wb-core`
tasks/sessions/actions and active model actions remain zero. Target main and
`origin/main` remain clean and equal at
`c20dc4b34a198116964516e0dc76b98b094e36eb`. The exact app/daemon remain the
same running healthy PID/port pair. At that checkpoint status remained
technical `BLOCKED` until the normalization guard could pass ordinary
exact-head review/check/merge and a separate terminal evidence merge could
record authoritative final-main readback.

## 12. Terminal project-identity qualification

current_technical_status: COMPLETE

Dev-control-plane PR [#223](https://github.com/orenvlad-ai/dev-control-plane/pull/223)
exact head `c7dbfab8c0cf336eedc2f7b8d0e1a9714e906103` passed exact-head
semantic/security review `4952702321`, baseline run `32046466697` and zero
unresolved threads, then merged normally at
`b751c2195bc7aeb9882a2f5b2cd2feda870e5783`. It accepts only the four exact
empty native-default forms named in section 11. Non-empty values, unknown
extra keys and every policy/worker/reviewer/path/repository/kind mismatch stay
fail-closed. The one reconciliation was not repeated.

Final-main model-free preflight reports
`wb_core_compatibility=qualified` against the actual registered project. Its
`agentRules` are exactly 1149 UTF-8 bytes with SHA-256
`2e4b0d69593c004a4becb532ed07d59e9be087af884cdfea523fb3e918a84a64`;
the only additional native projections are exact empty `agentConfig`, nested
orchestrator `agentConfig`, `trackerIntake` and `containerReap` objects. The
installed managed source/tree/receipt remain exactly:

- `99e8243ac66bfdd7e77538368403d0a3b5964c21`;
- `81b391c80eef98c5723340a1da8e42a3da1bbaec`;
- `97c4b6c000fa51c571586c39ed1d096adc7fdcdd5838d8c0ad4e15006a96a9d6`.

No managed-source change, repin, rebuild, install, stop or restart was needed:
the installed daemon validator already owned the correct policy and only the
dev-control-plane registration/readiness literals were stale. The exact app
and daemon remain running, ready and healthy on port 43231; PID and uptime are
ephemeral and no launch cause is attributed.

The canonical target remains clean with `main == origin/main` at
`c20dc4b34a198116964516e0dc76b98b094e36eb`, exact public provider identity
and three compatibility marker files. Repository ruleset
`wb-core-main-governance` still requires strict `baseline`. SQLite remains
integrity `ok`, schema 78, with the preserved totals of 26 policy tasks, 70
model actions, 44 ReviewRuns, 30 admissions, 43 sessions and six projects.
Main/WAL/SHM SHA-256 remain respectively
`2363c7ed05048c5f01977043f17d4524feceec26feefd6819f69fe3a528ad71f`,
`c22d7aa47c772d7a6b00752f3d351320dc7cceda210ba9e1c81cfbbca0ae734e`
and `7120278615487bd41a5b97ba49f3c3857ef6b34ff7db89aa65aa0f5e05592172`.
`wbc-canary-v1`, all `wb-core` policy task/session/action rows, all
queued/claimed/running actions and all active model actions are zero.

The installed target still has release authority
`wbc-github-actions-release-train`: DCP direct merge remains statically
ineligible, DCP may add only `release:ready` after exact-head review and FIFO
admission, and only the WBC Release Train may merge and add `release:done`.
Technical status is `COMPLETE`, ready only for a new, separately
owner-authorized repo-only canary. The failed task id was not retried. This is
not owner acceptance and authorizes no WBC product or model action. Platform
approval count remained zero throughout the incident correction.
