---
evidence_status: technical-complete
evidence_date: 2026-08-15
owner_acceptance: separate
live_dcp_tasks_created: 0
additional_model_actions: 0
production_changes: 0
---

# DCP real-target runtime provider identity v1 terminal evidence

## Result

The installed daemon runtime provider compatibility defect is corrected and
proved model-free for exact public `orenvlad-ai/wb-price-extension`. The
receipt-bound production function now uses typed `gh api --method GET
repos/orenvlad-ai/wb-price-extension` metadata and preserves exact public,
`main`, repository ID `1335072844` and owner ID `237411244` equality.
Missing, null, malformed, wrong-type, wrong-identity and command-error results
fail closed.

No live product submit ran. No DCP task, card, session, worktree, branch, pull
request or model action was created for `wb-price-extension`. Technical
completion is recorded here; owner acceptance and the curator's first live
task decision remain separate.

## Governed chain

| Gate | Exact result |
| --- | --- |
| Contract | dev-control-plane PR #202, reviewed head `873988e13c412d398667b1006cb18b34151593fd`, review `PRR_kwDOSUqHmc8AAAABJrCOoA`, workflow `31891353644`, merge `9db6ea4856cb834f45aa5f59417a5955a01bc623` |
| Managed source | dcp-orchestrator PR #58, reviewed head `636aa9311a180bba41f142533251c3c72fc73bb9`, review `PRR_kwDOTydt6M8AAAABJrDKDA`, source/package workflow `31891814079`, merge `9162d4c0eca9efd2a3d9fe1ad09d640c40738c47`, tree `ec8e4c6d613e5e503a2582955b40bb8f104f76ce` |
| Pin/install guard | dev-control-plane PR #203, reviewed head `4d7ac25fce9a61fce3b933f066a363c8bcef571b`, review `PRR_kwDOSUqHmc8AAAABJrKcWQ`, baseline workflow `31894800573`, merge `74e49338e76efce8fdaeeae80ce34b9352f9d631`, tree `8f1565004edfa236d6449029298cbad4dac97b06` |

All pull requests were ready, exact-head reviewed, green and normally merged.
There was no bypass and no replacement source branch or PR.

## Source and installed artifact

Deterministic canonical `prepare -> build -> install -> preflight` ran from a
clean dev-control-plane `main` at pin merge `74e49338...`. It prepared clean
managed source
`/Users/ovlmacbook/Library/Application Support/DCP Orchestrator/source/dcp-orchestrator-9162d4c0eca9`
at exact source `9162d4c0eca9efd2a3d9fe1ad09d640c40738c47` and tree
`ec8e4c6d613e5e503a2582955b40bb8f104f76ce`.

The stopped install preserved backup `i12-20260815T161620Z` and installed at
`2026-08-15T16:16:21Z`. Exact artifact identity is:

- receipt SHA-256
  `5cb06d6edaeb70080999f531da76109936732a57bee8262d9c0cf0af1b7ce295`;
- daemon SHA-256
  `4551866748919c808b1496f13a14de8b0ec23c05d883fbd8f9b484932a4fc43b`;
- asar SHA-256
  `9e4388d9f23364c6cd626c2b16e2b5f3de469986c3ff743120d5886ba4fa8404`.

The receipt values equal independently hashed installed files. Deep strict
code-signature verification passed. Model-free preflight printed the exact
packaged app, daemon, source, isolated data/run/Codex paths and repo-only target
path. The asar is byte-identical to the predecessor because this bounded fix
changes only daemon source.

## Runtime provider proof

The receipt-bound exact prepared source ran the focused production-function
harness with `DCP_PROVIDER_IDENTITY_LIVE_TEST=1`. It invoked the corrected live
read-only REST path and passed `TestReadPublicReviewRepositoryLiveExactProvider`
against the exact target. The same focused run proved:

- only `gh api --method GET repos/orenvlad-ai/wb-price-extension` is accepted;
- private, wrong repository, wrong default branch, wrong repository ID, wrong
  owner ID and provider error are rejected;
- malformed JSON, missing repository, null repository ID, null owner, missing
  owner ID, wrong numeric type and command failure are rejected.

This harness calls the production Go function directly and contains no daemon
start, submit, SQLite, session, worktree, branch, PR or model-action path. The
live provider result was exactly
`orenvlad-ai/wb-price-extension|false|main|1335072844|237411244`.

Source gates, generated SQL/OpenAPI parity, full serial Go tests, Go build/vet,
frontend typecheck, packaging/signing and 15 governed renderer files with
356 tests passed. Required source/package and baseline workflows are green.
Existing upstream npm engine, deprecation and audit warnings remain visible;
this correction adds no dependency.

## Repository and durable-state proof

After a fresh fetch, the target is a clean sole `main` at
`9522cfb633f9b3f5a87298f4f1dcce902bb7ebfd`, equal to `origin/main`, tree
`b43f500f195c7c1f64874b5a9c5bcda5e38401c3`. Fetch and push origin are both
exact `https://github.com/orenvlad-ai/wb-price-extension.git`; the repository
is public, default branch `main`, repository ID `1335072844`, owner ID
`237411244`, with zero open pull requests.

SQLite stayed byte-identical before and after install at SHA-256
`da78e509b5353563e367f4ecab63e34b4606fd23116f6b82198cab96aa33e24d`,
integrity `ok`. Counts remained 39 sessions (zero active), 38 review runs
(zero running), 58 model actions (zero claimed/running), 22 policy tasks and
six future-card arbiter rows. `wb-price-extension` task and session counts are
both zero.

Historical `dcp-review-lab` PR #24 is unchanged: open, non-draft, head
`58adc8c6abe1d2fee90cd1bfa9addd149cede1a8`, provider state
`DIRTY`/conflicting. Card 27 remains revision 10 in terminal `human_gate` with
one arbiter call and the exact owner question: “Should
qualification/arbiter-c.txt on main remain mode=left or be replaced with
mode=right?”

The app and daemon are stopped. The runfile and browser socket are absent,
TCP 43231 has zero listeners, and exact app/daemon process count is zero. All
28 retained historical DCP review/arbiter tmux panes remain bare `zsh` shells
with zero descendants; none was altered or counted as active model work.

## Boundary and handoff

The correction adds no service, database, registry, queue, poller, retry,
credential, target, model or merge authority. It does not touch `wb-core`,
production, Telegram, secrets or foreign repositories. No live product submit
was run. The installed bundle is stopped and preflight-ready for the main
curator's separate decision.
