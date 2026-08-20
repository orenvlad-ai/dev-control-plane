# WBC integration twin DCP v2 Stage 4 source-complete evidence

source_complete_status: `COMPLETE`

installation_status: `NOT AUTHORIZED / NOT PERFORMED`

adapter_activation_status: `OFF`

date: 2026-08-20

program_stage: 4 of 9

owner_acceptance: not requested or synthesized

## 1. Terminal result and authority chain

Stages 1-4 of the WBC integration-twin program are technically `COMPLETE`.
Stage 4 is source completion only: the provider-neutral DCP v2 core is merged
in the official managed source, but is dormant, uninstalled and unbound to any
live target adapter.

The exact reviewed authority chain is:

| Stage | Evidence gate | Exact result |
| --- | --- | --- |
| 1 | Architecture PR #244 | head `ba2798a4c302cac0ef79df4c31242c902dadc1f5`, review `PRR_kwDOSUqHmc8AAAABKDIDSQ`, baseline `32226390667`, merge/tree `a6e1ab242cd1fc28d161d905b313e30180fe952d` / `bfe1949d8949cab37231bf044a0aaad10eced6ab` |
| 2 authority | Persistent-cell PR #245 | head `a0a0945619bc7a3d8c207d1f5c229247d12a2052`, review `PRR_kwDOSUqHmc8AAAABKM7n3g`, baseline `32338651891`, merge/tree `86dfdb0f66889494219da7fc60351c5cee38660d` / `3284c87fbb456f75dbc99c64c558470e28963695` |
| 2 closure / 3-4 program | DCP PR #246 | head `97c03e45eb8f36953ae599420bac7bb2e4bbca0e`, review `PRR_kwDOSUqHmc8AAAABKOkuQQ`, baseline `32355628568`, merge/tree `4e6d50af5bee5c425d68de7cb41d0e869f2170e2` / `a4e36e57dd0ceb85f0218b1fadabc56e6059d461` |
| 3 closure / 4 activation | DCP PR #247 | head `c6af73b454a2f917752a81b9afb8b3c54c7ed6dc`, review `PRR_kwDOSUqHmc8AAAABKO7iDQ`, baseline `32359518541`, merge/tree `8be08577673722edc9ae036dedea46c88ceac129` / `2587b98c411e1df2d8ccf4c3015f32ea59c716ef` |

Stage 4 began only after PR #247 was present on `dev-control-plane` main. The
authoritative design remains
`DCP_WBC_INTEGRATION_TWIN_DCP_V2_ARCHITECTURE_CONTRACT.md`; the exact execution
boundary is `DCP_WBC_INTEGRATION_TWIN_STAGE3_4_COMBINED_EXECUTION_CONTRACT.md`.

## 2. Exact managed-source result

The managed repository is exact public `orenvlad-ai/dcp-orchestrator`,
repository/owner IDs `1327984104` / `237411244`, default branch `main`.
Implementation started from official-ancestry main
`84dbee2a701186628c1ad92950aa14639000fc0b`.

Managed-source PR #72 exact head
`1401c9f38121b4a65605b23fe6c32e8e38a39d6f`, tree
`2a894de8af6e73eabd11bd8d80dc0ed31812930b`, added the dormant core. Exact-head
context-free semantic/security review
`PRR_kwDOTydt6M8AAAABKPsdtQ` (`4982513077`) found no issue. Review threads were
empty.

DCP CI workflow `32367257928` passed both connected jobs:

- package job `96419384315` completed green in the ephemeral CI environment;
- source job `96419384655` passed source/provenance/identity/absence gates,
  locked dependencies, generated SQL/OpenAPI/TypeScript parity, serial backend
  tests/build, renderer typecheck and all applicable renderer tests.

PR #72 merged through the ordinary protected PR path at
`bcb512239cbc14788f8fe59ece1ba33cbcb18c1f`, exact tree
`2a894de8af6e73eabd11bd8d80dc0ed31812930b`. The source head is its second
parent and is an ancestor of final main. No managed-source PR remained open at
source closure. The CI package was not installed into the governed DCP
installation and is not an installation receipt.

## 3. Provider-neutral core and transaction law

The merged source adds the Stage 4 protocol without a live adapter:

- durable Task -> immutable exact-head Revision -> durable typed Command ->
  bounded model Action -> FIFO Admission -> immutable verified
  Release/Deployment Result;
- one atomic SQLite transaction for every authoritative task transition,
  completed command and required successor Revision, Command, Action,
  Admission, Incident or Result;
- exact CAS binding to task state revision, current Revision, leased Command,
  optional provider delivery, exact model Action result and effect fence;
- one initial worker, one task-level repair allowance, one reviewer Action per
  exact Revision, finite readmission generations and at most three globally
  active model Actions through physical slot uniqueness;
- global FIFO command and per-line FIFO admission identities, durable
  lease-owner/epoch/token/fence records, exact replay dedupe and fail-closed
  conflicting delivery handling;
- one finite startup/event drain only. There is no heartbeat, watcher, timer,
  scheduler, unbounded polling, blind external retry or AI retry loop;
- typed provider-neutral repository, Release Train and deployment observation
  interfaces. The core exposes no direct merge/install/redeploy/restart method;
  no lab or WBC target is activated or special-cased.

The native terminal/process shell remains a runtime resource rather than Task
authority. A queued Action owns no physical model slot. A launching/running
Action requires its exact durable launch fence and runtime identity; ambiguous
crossed effects and active-runtime adoption without exact proof stop safely.

## 4. Forward schema and model-free proof

Migration `0084_dcp_v2_core.sql` is additive and forward-only. It adds empty
authority/task/revision/command/action/admission/event/incident/result tables,
immutable identity triggers and guarded one-way transitions. Its authority row
is fixed to dev-control-plane merge
`8be08577673722edc9ae036dedea46c88ceac129`, Stage `4`,
`adapter_activated=0` and `installed=0`.

Migration proof ran only on new disposable databases and an exact disposable
schema-83 copy. It proved additive preservation, foreign-key integrity,
rollback and idempotent empty initialization. The live schema-83 SQLite was not
opened by Stage 4, writable or otherwise; migration 0084 was not applied and
the frozen predecessor task/history/PR #987 state was not changed.

Independent model-free validation on exact head `1401c9f...` passed:

- source/provenance/identity/security absence gate;
- generated sqlc and OpenAPI/TypeScript parity with an identical before/after
  diff digest;
- full serial Go test suite, full Go build and vet;
- race suites for domain law, command engine and SQLite store; the store race
  package completed in `272.237s`;
- 23 focused new core tests: three domain projection/state tests, two migration
  tests, twelve transactional store tests and six startup/event engine tests;
- frontend typecheck and `359/359` applicable renderer/accessibility tests.

The focused proof covers transaction rollback, command and external-delivery
dedupe, command/action/admission lease and effect fences, startup before and
after core fences, three global slots, FIFO, duplicate and out-of-order events,
one repair, two finite readmission generations without a second worker, typed
arbiter/Human Gate, exact release/deployment/terminal bindings and no lost or
duplicate Command, Action, Admission or Result.

## 5. One truthful lifecycle projection

The optional DCP v2 projection is generated from the same durable Task,
Command, Action, Admission and Result facts used by the engine. The API and
frontend types keep it absent for every incumbent session until a later
activation stage.

When present in the future, the same projection drives card, sidebar, details
and accessibility text. `modelActive` is true only for launching/running model
Actions; `workflowActive` separately covers queued model work and autonomous
CI/admission/release/deployment work. Only `modelActive` pulses. Human Gate and
error truth are steady; `Merged` and `Deployed` remain distinct terminal
states. No predecessor UI flow is replaced by the dormant projection.

## 6. Preserved Stage 2/3 destination truth

Stage 4 did not mutate the lab repository or Selectel host. The final Stage 3
record remains authoritative:

- lab repository/owner IDs `1340359100` / `237411244`, ruleset `21077248`,
  environment `20234191757`;
- lab main/deployed SHA `157ae90edb0891506639b845deac141f75189ec7`,
  loopback `127.0.0.1:18321`, persistent service
  `dcp-wbc-integration-lab`, two-release retention and zero incoming release;
- ten matrix manifests/runs, two success-shaped runs, eight expected
  fail-closed runs, exactly one matrix merge/deploy/proof and zero replay or
  negative merge/deploy effect;
- qualification-only issuer still active and DCP issuer still off;
- protected Luchiki HTTPS/nginx/timer invariants and its truthful pre-existing
  counter evidence unchanged;
- legacy retirement/rollback remnants remain literal and no paid Selectel
  resource, inventory, billing, shared OS, network or firewall change occurred.

Exact Stage 2 and Stage 3 identities, artifacts, proof digests and negative
case results remain in their terminal-evidence documents and are not recreated
or normalized here.

## 7. Stop boundary, counts and risks

Stage 4 created zero live integration-twin Task, Action and Admission rows and
performed no submit. Because migration 0084 was not installed, this is a
source-only zero-state statement, not a fabricated live-table readback.

This pass did not change a DCP source lock or installed pin; did not build or
install a governed artifact; did not start, stop or connect to the DCP
app/daemon; did not open or migrate live SQLite; did not mutate WBC, PR #987,
Release Train, production, business data or secrets; and did not change the
lab/Selectel/Luchiki surfaces after Stage 3 qualification.

The bounded difficulties remain preserved rather than erased: Stage 2 retains
the truthful pre-cleanup Luchiki counter failure; Stage 3 retains the original
artifact-layout failure and its sole bounded correction. Stage 4 required no
source correction after review and has no technical blocker at the source
boundary.

The remaining risk is deliberately a gate: dormant source is not an installed
or qualified runtime. Stage 5 requires a separate owner-authorized exact
lock/pin/install/preflight pass. The qualification issuer remains active until
Stage 5 explicitly proves it off and proves the exact DCP issuer on. Stage 6
submit/canary, WBC cutover and every production action remain separately
prohibited. Technical `COMPLETE` does not mean owner acceptance.

Effective routing for this pass was `approval_policy=never`, unrestricted
filesystem, network enabled and a separate Git worktree. Codex app was
`26.707.41301` build `5103`, CLI `0.145.0`, Git `2.50.1`, GitHub CLI `2.87.2`,
platform approval count `0`, and collaboration subagent/fork/monitor/nested-
executor count `0`.
