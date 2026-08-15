---
evidence_status: technical-complete
evidence_date: 2026-08-15
owner_acceptance: separate
live_dcp_tasks_created: 0
additional_model_actions: 0
production_changes: 0
---

# DCP real target v1 install evidence

## Result

The first exact real repository target is installed and model-free
preflight-ready. The public repository is
`orenvlad-ai/wb-price-extension`; its only DCP tuple is target
`wb-price-extension`, profile `repo-only`, repository
`orenvlad-ai/wb-price-extension`, default branch `main`, required check
`baseline` and policy `dcp.repo-only.happy-path/v1`.

No DCP task/card/session/worktree/branch/PR or model action was created for the
new target. The product extension, WB API adapter, credential storage, product
UI, deployment, Release Train and production mutation remain outside this
preparation. Owner acceptance is separate.

## Governed chain

| Gate | Exact result |
| --- | --- |
| Contract | dev-control-plane PR #198, reviewed head `4933a1bd5ebd0bd0ba72e862a6033ea6209665ab`, review `PRR_kwDOSUqHmc8AAAABJq1kXA`, workflow `31885413130`, merge `4f251b7f6877d974ee80169391e89a79d1367658`, tree `90da1fa402a49a633e6685f0d4ef28cf31de3a31` |
| Managed source | dcp-orchestrator PR #57, reviewed head `8af4196d8c3a7bb0c2fca58a3a818e5d7cdbac06`, review `PRR_kwDOTydt6M8AAAABJq4I-g`, source/package workflow `31886665288`, merge `f94b0603916c410419654ca4752ffa9084116ff8`, tree `11a9856ea2504ef923221a97064a59a762a99ed8` |
| Pin/install guard | dev-control-plane PR #199, reviewed head `cfdf23ed32bbf47b23aa8c6ad88842c57f588bba`, review `PRR_kwDOSUqHmc8AAAABJq5raQ`, workflow `31887486996`, merge `2fe7d4bf2ef719d9525ac3c046e45f234e83aef3`, tree `8d3b6883491c9c930ff3c5352f520e91098a68e1` |
| Provider compatibility | dev-control-plane PR #200, reviewed head `a72ba92ef84c2c7107f69e2cfb43b30ae24dc0c1`, review `PRR_kwDOSUqHmc8AAAABJq6vtQ`, workflow `31887976497`, merge `98aef56947c58461562122f1663a7d0849c43f5a`, tree `6f41cb6af5b597d12960eeb47bbe3d32413289d0` |

All four pull requests were ready, green and merged normally. There was no
manual bypass. Source PR #57 retains official Agent Orchestrator ancestry and
adds only the reviewed static registry tuple, repo-only projection/isolation,
migration 0075 and I21 renderer correction.

## New repository evidence

The public repository was created separately at
`https://github.com/orenvlad-ai/wb-price-extension`. Its sole bootstrap commit
is `9522cfb633f9b3f5a87298f4f1dcce902bb7ebfd`, tree
`b43f500f195c7c1f64874b5a9c5bcda5e38401c3`. It is one clean `main`
worktree with one commit and zero open pull requests.

Bootstrap contains only `README.md`, repo-only `AGENTS.md`, high-level project
and architecture documents, `.gitignore`, the model-free verifier and its
GitHub Actions workflow. It has no product code, secret, environment, GitHub
secret, WB endpoint/data, deployment or telemetry. Repository ID `1335072844`
and owner ID `237411244` are frozen in the fail-closed provider identity check.

Workflow `31885027761` ran the exact stable job/check name `baseline` on the
bootstrap head and succeeded. The verifier checks required files, shell syntax,
diff/whitespace, a bounded credential-pattern scan and workflow identity; it
does not contact WB or require secrets. Branch protection is strict, requires
`baseline`, applies to administrators, and the repository is squash-only for
future feature changes.

## Runtime and install evidence

Before install the canonical stopped receipt was
`653417573689a62cd0fb570c0bbc9e432a38e0b57af1347a93f606dd94228760`
for source `bd8d6733...` / tree `4981847f...`. After the governed pin, the first
stopped install created backup `i12-20260815T133921Z` and receipt
`9d0279dfd338daa7649ea0012fecf6302f2d354a8a783e34348b9c5c232752cc`.
Its first preflight failed closed before daemon/state/model activity because the
local `gh repo view --json` projection did not expose `databaseId`.

PR #200 changed only that read-only lookup to stable REST fields with the same
exact numeric equality. After its merge, the repeated stopped deterministic
build/install created backup `i12-20260815T134528Z`. Final install receipt
SHA-256 is
`06ebdbf6c418ed3805ff85737a638cf9e78cf5f70a1b035211016c0b117d26fc`
for exact source `f94b0603916c410419654ca4752ffa9084116ff8`, tree
`11a9856ea2504ef923221a97064a59a762a99ed8`, daemon SHA-256
`14ea1f6feb41426395de7b6dd4fda03eeaa13b507eba50278a71c4582611c587`
and asar SHA-256
`9e4388d9f23364c6cd626c2b16e2b5f3de469986c3ff743120d5886ba4fa8404`.
Deep strict code-signature verification passed.

The final installed model-free preflight passed and printed the exact packaged
app, daemon, managed source, isolated data/run/Codex paths and the canonical
repo-only target path. It validated public numeric provider identity, exact
HTTPS fetch/push origin, clean `main == origin/main`, canonical worktree
topology, required tracked baseline files and the model-free target baseline.
Foreign target, missing profile and mismatched profile CLI cases fail closed.
The public CLI advertises exactly:

```text
bin/dcp-ao-submit --target wb-price-extension --profile repo-only --task-id task-id --prompt 'one short prompt'
```

The packaged daemon contains the exact target identity. Receipt-bound asar
inspection found the I21 `SessionsBoard` asset SHA-256
`8586708a40b0c3e791d3a584167d15b8c0c037f99dc2576a254f917200021a8b`
with independent non-empty Arbiter/Review predicates and conditional section
rendering. The physical paired-count header and all previously qualified status
projections remain unchanged.

## Verification and unchanged durable state

- Generated SQL and OpenAPI parity, full serial Go tests, Go build/vet,
  frontend typecheck, source/provenance/identity gates, packaging and signing
  passed.
- Governed renderer coverage passed 15 files and 356 tests, including I21
  `0/0`, `n/0`, `0/n` and `n/n` section cases, sidebar parity, accessibility,
  Human Gate/failure colors and reduced-motion behavior.
- The full upstream non-governed `npm test` command still reports 25 existing
  failures among 1,560 tests in removed Updates UI, stale PR-hydration mocks and
  an uninstalled landing-page dependency. These are outside the governed
  renderer/package gate and were not hidden or changed by I22.
- Dependency installation reports existing upstream audit warnings. I22 adds no
  dependency or product package; required source/package workflows are green.
- Live-copy migration 0075 and exact target/registry/CLI/security/restart tests
  passed. The canonical database was deliberately not migrated by starting the
  daemon during preparation; the first authorized future submit will apply the
  immutable migration before its exact native submit.
- SQLite stayed byte-identical across both installs at SHA-256
  `fed4a8c0bc5325681ce5a4d436e4fab630265ddcc891b41a7c107fc5a15f0297`,
  integrity `ok`: 39 exited sessions, 38 review runs, 58 terminal model actions
  (zero active), 22 policy tasks, 26 admissions and six future-card arbiter
  rows. New-target task/session counts are both zero.
- Existing `dcp-review-lab` history is unchanged. Historical Human Gate PR #24
  remains open on head `58adc8c6abe1d2fee90cd1bfa9addd149cede1a8`, provider state
  `DIRTY`; no row, branch, PR or question was changed.
- The final app/daemon is stopped. Canonical runfile, browser socket, TCP 43231
  listener and model children are absent. Six historical terminal arbiter tmux
  panes remain idle and were preserved as existing state; no old app, backup or
  state was deleted.

## Curator handoff — do not run during preparation

The following commands are prepared but were not executed.

### 1. One light documentation/design task

```sh
bin/dcp-ao-submit --target wb-price-extension --profile repo-only --task-id arch-flow-v1 --prompt 'Refine docs/ARCHITECTURE.md with an explicit user-confirmed price-change flow, extension permission boundary, and no-live-WB acceptance notes. Change no product code or other files, run baseline, then follow the repo PR flow.'
```

### 2. Three independent parallel scaffold tasks

```sh
bin/dcp-ao-submit --target wb-price-extension --profile repo-only --task-id mv3-manifest-v1 --prompt 'Add a minimal Manifest V3 scaffold and focused baseline checks only. Use no WB endpoint, credential, telemetry, server, deployment, background network request, or product UI beyond the manifest boundary.'
bin/dcp-ao-submit --target wb-price-extension --profile repo-only --task-id price-domain-v1 --prompt 'Add a pure price-change domain model with local validation and unit tests only. Use no browser API, storage, credential, WB network call, UI, server, deployment, or telemetry.'
bin/dcp-ao-submit --target wb-price-extension --profile repo-only --task-id options-ui-v1 --prompt 'Add a static local options-page scaffold and accessibility checks only. Do not add credentials, persistence, WB calls, background logic, server code, deployment, telemetry, or modify domain modules.'
```

### 3. One technically resolvable conflict scenario

Submit both tasks close together so both start from the same clean main. Their
intents are explicitly compatible: the final canonical order is
Draft, Validate, Confirm, Queue, Apply, so the existing arbiter can choose one
bounded successor repair without asking for product intent.

```sh
bin/dcp-ao-submit --target wb-price-extension --profile repo-only --task-id conflict-flow-a --prompt 'Create docs/FIRST_CHANGE_FLOW.md with a First change flow heading and ordered steps Draft, Validate, Confirm. Preserve compatible existing steps and their order, change no other file, and run baseline.'
bin/dcp-ao-submit --target wb-price-extension --profile repo-only --task-id conflict-flow-b --prompt 'Create docs/FIRST_CHANGE_FLOW.md with complementary steps Draft, Confirm, Queue, Apply. Preserve compatible steps; if Validate exists, the required combined order is Draft, Validate, Confirm, Queue, Apply. Change no other file and run baseline.'
```

The next curator owns the decision to make the first live submit. A terminal
merge means repository `MERGED` only; it is not deploy, release, production
apply or owner acceptance.
