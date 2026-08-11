# I13 Stage 2 terminal BLOCKED evidence

evidence_status: technical-blocked
recorded_at: 2026-08-11
installed_source: 182f7a1a95d4e1705de63355e65599b9d79f2c12
incident_generation: 1

This is the immutable technical handoff evidence for the one owner-approved
I13 Stage 2 global release arbiter v1 qualification. It records a truthful
`BLOCKED`, not owner acceptance and not a successful safe stop. The sole actual
arbiter inference returned a schema-valid but semantically invalid recovery
decision; the trusted daemon rejected it fail-closed, and the reviewed one-call
budget forbids another arbiter.

## Governed source and installation

- Contract PRs
  [#133](https://github.com/orenvlad-ai/dev-control-plane/pull/133),
  [#137](https://github.com/orenvlad-ai/dev-control-plane/pull/137) and
  [#139](https://github.com/orenvlad-ai/dev-control-plane/pull/139) merged at
  `0b12727a99ddc448b5d19c252615b7bf13bd7113`,
  `4d3e0736635579db053516813e2d5944f903f777` and
  `3f3a3bb2c2e951cbf7a34da75d3cc3f09d906001`.
- Managed-source PRs
  [#23](https://github.com/orenvlad-ai/dcp-orchestrator/pull/23),
  [#24](https://github.com/orenvlad-ai/dcp-orchestrator/pull/24) and
  [#25](https://github.com/orenvlad-ai/dcp-orchestrator/pull/25) merged at
  `d5f9fd4b3459596fcb2d79efc0023bad4f7f0aa0`,
  `2fbd9bf4789a5b388fb12c58d9347968ed06e6de` and
  `182f7a1a95d4e1705de63355e65599b9d79f2c12`; the installed final tree is
  `3f4c9c7a6efc9a7164852eeaafde4423ef9cec6f`.
- Integration/pin PRs
  [#134](https://github.com/orenvlad-ai/dev-control-plane/pull/134),
  [#138](https://github.com/orenvlad-ai/dev-control-plane/pull/138) and
  [#140](https://github.com/orenvlad-ai/dev-control-plane/pull/140) merged at
  `58afac3d9859c9c84ac54a5d6b4622c391c5ebac`,
  `ce1b6afd289dc5ded44bc0c93bf3d59939d5fba7` and
  `fbdadf1c833771e2bd610fc921b8998e40b84f02`. Bounded model-free integration
  corrections #135/#136 merged at `fdebf67f97dc8ecb3162ae34be1df89f2ed07499`
  and `b66c8220aa11b6379261a39cf3412250f03223f2` without another card or model
  call.
- The deterministic final installation receipt records fork
  `182f7a1a95d4e1705de63355e65599b9d79f2c12`, tree
  `3f4c9c7a6efc9a7164852eeaafde4423ef9cec6f`, daemon SHA-256
  `f4bfe03776a1c2c227ca58c48a517c2fb9dde5d4cf1de60996c5e3a4cce2798d`,
  `app.asar` SHA-256
  `a1206d002b16a8d9a3cb4485c4522b4fe685fdb102840d1d96530a4f11a4ff90`
  and install time `2026-08-11T19:10:52Z`.

All contract, source, package and pin checks were green before each ordinary
protected merge. The final install reran the complete Go, Vitest, typecheck,
source/provenance and deterministic package gates.

## Exact canary and frozen incident

- Card 11 / task `i13-arbiter-a` / session `dcp-review-lab-11` used worker
  Codex session `019ff1e7-5654-7a22-9801-f3b3bd28353d`, produced head
  `2166d10911f06e14a525267975393c0be03727d0` on PR #8, and consumed 30,834
  tokens. Review run `841c6c1e-3dcd-4ffb-875e-c42dfa358919`, review
  `87a74347-d467-4f7d-be7b-316fba7b9fd1`, batch
  `af2eb45f-c842-48b0-a96e-39f883d6d14a`, reviewer Codex session
  `019ff1e8-3639-7863-bae7-9283139d9227` and 17,924 tokens approved that exact
  head. Its named check passed and admission sequence 3 merged once at
  `b34b31b5443890e69128db2862726950a6bbac0d`.
- Card 12 / task `i13-arbiter-b` / session `dcp-review-lab-12` used worker
  Codex session `019ff1e7-7686-7d60-94b2-34bd178bf5e6`, produced head
  `d4fcb68051ae113ed497d02151a759800ee85633` on PR #9, and consumed 45,151
  tokens. Review run `ecb500ad-f9f0-443b-9d73-2c8a6350ce34`, review
  `6aab2a2f-beb2-40a2-bcdb-c47ebf304a65`, batch
  `ddeeb966-30a0-4870-8f3f-fda32a4ee568`, reviewer Codex session
  `019ff1e8-341b-7031-9665-ed18598912c1` and 15,022 tokens approved that exact
  head. Its named check passed. After PR #8 advanced main, PR #9 became the
  intended real add/add conflict and remains OPEN/DIRTY.
- Admission sequence 4 retained lease
  `dcp-incident-dcp-admission-ecb500ad-f9f0-443b-9d73-2c8a6350ce34` with
  `merge_conflict_or_ambiguity`; it never merged or refreshed.
- The one durable arbiter incident is
  `dcp-global-release-2694dbd8b3d4897063603d7a8607ca516aa2f8e05c5a3c39cf56d8e3f18c3c60`.
  Its identity digest is the same suffix, input digest is
  `f618fa8a46715acce0958b592384f0d42c071562e36988163e2b96f2c157fc49`,
  source-packet digest is
  `fab52d627d14a21ea7ab2a7fdadb4d6f53478d5cdc496858ca74c37e1dfda057`,
  and scope/history/diff/check/review/queue/mechanical digests are respectively
  `1259b9d8569638c986e1dcd56d13f5d8e1e049e5ad2987c94b713bbbc28fd62f`,
  `6a17ad96f4e3bd32d3058ef5ef07a6af426d2ab2c349ee6fd42d10d1549c9211`,
  `c81b1e31b06c0045562ac8a2eb13a6cb772483e8c8859b01c3822ad7e630aa62`,
  `ddcd2dd72c13702056589926d99a08cd895f10af54f5c4e5e5dbe6bd9e2121f2`,
  `6fd1519899b0cf66db09de087c8b8666307376988a96ba14908c0345b688157a`,
  `af840dbaa49ec99f7ccf6c6de95c1b762a7d6f5f26910e7ae70406eaedc9c813`
  and `1730d612b1f6755c507cd8d6a21871a329e4f5d556361fcef8dbd289d3ab9cc3`.

## Arbiter result and blocker

- Migration 0053 preserves the first strict local config rejection before a
  Codex session/provider request. Migration 0054 preserves corrected-source
  Codex session `019ff21d-4cde-72d1-b70d-49efd3cd1c17` and provider code
  `invalid_json_schema`, with result-artifact-present `0` and token-record-present
  `0`. Neither rejected attempt performed model inference or consumed tokens.
- The only actual arbiter inference used `gpt-5.6-sol`, reasoning `xhigh`, the
  persisted 16,384-token ceiling and Codex session
  `019ff23c-7cbf-7ee1-9567-30c6693f95fe`. It consumed 11,583 tokens.
- Result artifact SHA-256 is
  `d121d012a0b3042f02886fdc0c2aca806f34be64f9e5a3d15e1edf444ff3ae2d`;
  its frozen schema and input artifact SHA-256 values are
  `8314793a7dbc3f0fc654c28e5936687138883b6e134460fc7204a025102b805f`
  and `355a00609c8ded920bd87b215cea74d3c50213fa4ed8f0b484ea577f73bdbd7d`.
- The artifact chose `assign_recovery`, owner `dcp-review-lab-12`, path
  `same_worker_conflict_repair`, `maxWorkerCalls=1` and
  `maxFreshReviews=0`. The contract requires `1`; therefore trusted cross-field
  validation rejected the artifact with `ARBITER_RESULT_REJECTED`, and the
  durable terminal row is `failed/submit_failed`, `model_call_count=1`, empty
  decision digest, empty recovery owner/path and `recovery_wake_count=0`.
- This is the blocker: the one reviewed arbiter inference is consumed, but no
  valid decision exists. Repairing or synthesizing the result, accepting a
  zero-review path, or issuing another arbiter would violate the exact contract.

The Stage 2 canary therefore used five actual model inferences and 120,514
tokens: two workers (75,985), two initial reviewers (32,946) and one arbiter
(11,583). It used no recovery worker, fresh reviewer or waiting-task token.

## Restart, duplicates and cleanup

- Controlled deterministic replacement/start after incident persistence and
  before the actual arbiter preserved the same incident, FIFO priority and one
  action row. Migration 0054 re-armed that exact generation at
  `2026-08-11 19:11:12 UTC`; the sole call fence entered running at
  `2026-08-11 19:11:16.694424 UTC`.
- The rejected result became terminal at
  `2026-08-11 19:11:47.681233 UTC`. A controlled exact app/daemon restart then
  started the replacement daemon at `2026-08-11T19:12:52.924929Z`; the arbiter
  row remained unchanged and no process relaunched.
- Post-restart counts are one arbiter row, one fenced call, zero decisions,
  zero recovery wakes, zero recovery reviews, two admission rows, one historical
  successful merge, zero admission refresh wakes, and exactly one initial
  review run per card. No worker, reviewer or arbiter descendant remains.
- No canary screenshots, preview assets or other visual artifacts were created,
  so no visual deletion was applicable. Native cards 11/12, retained terminals,
  PRs, worktrees, incident packets and SQLite rows remain immutable audit
  evidence as required.

## Terminal state

Status is `BLOCKED`. Not done: there is no accepted arbiter decision, selected
recovery, repaired exact head, fresh review, second admission success or PR #9
terminal merge. Production, `wb-core`, real repositories, labels, HumanGate,
owner acceptance and every out-of-scope integration were untouched. Residual
risk is the intentionally frozen OPEN/DIRTY synthetic PR #9 and its durable
incident; any continuation needs new owner authority and a new reviewed model
budget/contract decision. Technical completion and owner acceptance are not
claimed.
