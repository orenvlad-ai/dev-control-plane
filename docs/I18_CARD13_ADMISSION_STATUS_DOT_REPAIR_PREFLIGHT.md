# I18 card-13 admission/status-dot repair preflight

evidence_status: creation-base-correction-pre-install-pin
evidence_date: 2026-08-14

## Immutable source result

- Managed repository: `orenvlad-ai/dcp-orchestrator`.
- Ready PR: [#40](https://github.com/orenvlad-ai/dcp-orchestrator/pull/40).
- Reviewed exact head: `02247cb8d6c91fe9be655417ecda1b4aaf04d6f2`.
- Formal semantic/security review id: `4935176627`.
- Required GitHub Actions run `31781881915`: `source=success`,
  `package=success`.
- Ordinary merge commit: `70187c13ab0bc8bac07cd2d9ff27e230b866e087`.
- Exact source tree: `ee81758b33443a66835f785e2cb178b560808c15`.
- Sole allowed installed predecessor: source
  `5c9ce30bfdd61bc8cc49106c9eb3d62fbf867abd`, tree
  `45660cc8293d78dded4235f9406586fd8771077d`.

## First install and terminal-quarantine correction

- Exact source `70187c13ab0bc8bac07cd2d9ff27e230b866e087` was
  deterministically installed at `2026-08-14T08:19:34Z`; receipt SHA-256
  `1504d133445f4aa66e3c369356d6f52d9a49736f953cde3808229e77588b53b1`
  and verified backup `i12-20260814T081933Z` are exact.
- Its first controlled start failed before daemon wiring with `exact governed
  startup quarantine is unavailable`. The app was stopped without a run-file
  or listener. Card 13 stayed revision 9/waiting, admission sequence 5 stayed
  unclaimed and both existing model actions stayed succeeded once.
- The durable pre-install database and change log prove cards 11/12 had already
  reached exact stock terminal `exited/terminated` at
  `2026-08-14T07:18:16Z`; their quarantine rows, succeeded admissions and all
  recovery/finalization identities remained exact. The startup query admitted
  only their older `idle/non-terminated` lifecycle pair.
- Corrective managed-source [PR #41](https://github.com/orenvlad-ai/dcp-orchestrator/pull/41)
  exact head `24a816d29860b2892dcf64d847a3082e4e94c352`, formal review
  `4935346602` and DCP CI run `31783935999` are green. It accepts only the two
  exact idle/terminal pairs and retains fail-closed mixed/active/foreign gates.
  Ordinary merge is `50136576ce287ed0563b54144523ec14ab34d76c`, tree
  `db4ee06ad176c91402cfc852cc63e1e2252148f3`.
- The immutable pin now accepts installed `70187c13...` / `ee81758...` as its
  sole predecessor. The correction authorizes no migration, historical runtime
  restoration, model call, retry, admission claim, reviewer or merge.

## Proven live checkpoint before mutation

- Policy task `chat-probe-b`; native session/card `dcp-review-lab-13` / 13;
  state `admission_waiting`, revision 9, repair count 0.
- Branch `ao/dcp-review-lab-13/root`; PR #10; exact head
  `e467d1a44668294d59cca15a756c6cef18e4b247`; base/main
  `5bfd20d3b3f5b7d9d9ccb02500b742a917e6ea01`.
- Provider PR is OPEN, ready, CLEAN/MERGEABLE; named `dcp-review-lab` check is
  successful.
- Initial worker action succeeded once. ReviewRun
  `152048c0-6720-4397-9430-df975a453807` succeeded once on the exact head with
  structured `approved` and no findings.
- Admission `dcp-admission-152048c0-6720-4397-9430-df975a453807`, sequence 5,
  is waiting with no lease, merge SHA or error. All earlier admissions are
  terminal succeeded, so the global FIFO head is free.
- No model action is active; retained worker/reviewer terminals are bare
  shells. The daemon is healthy. No replacement task/card/PR is authorized.

## Root cause and bounded repair

The stock SCM observer persisted and acknowledged the material exact-head
CLEAN/MERGEABLE facts before sequence 5 existed. The review completion then
created the admission, but its immediate trusted terminal fetch saw transient
unknown mergeability and correctly left it waiting. Later stock observer
snapshots were fresh but semantically identical to the already stored facts, so
the observer skipped the lifecycle entrypoint and no terminal eligibility
signal reached the new waiter.

PR #40 adds only an optional catch-up call on that existing unchanged SCM event.
Lifecycle verifies the exact durable policy/admission/head plus materially
OPEN/passing/CLEAN/MERGEABLE snapshot and emits an idempotent eligibility
signal. `terminalMerger.Try`, its process mutex and the SQLite FIFO lease remain
the sole claim/merge authority and revalidate every provider/Git/review/check/
head gate. There is no new timer, heartbeat, watcher, poller, database, model
call, network contour or manual bypass.

The same native session read model additionally exposes the durable policy
state and a boolean true only for a running model action. One shared mapper
drives the central-card and sidebar dots, with gentle active-only worker/review
pulse and steady queued/waiting/terminal colors. Reduced motion disables pulse
without removing the steady state.

## Verification before pin

- Source/provenance/absence gates: PASS.
- Generated SQL/API artifacts: current.
- Backend `go test -p 1 ./...`: PASS; `go build ./...`: PASS.
- Renderer typecheck: PASS.
- Existing applicable 15-file renderer suite plus two focused files: 17 files,
  415 tests, all PASS.
- Focused tests prove pending-to-waiting then later CLEAN-to-one merge, a new
  engine/startup replay without duplicate claim/merge, existing FIFO storage
  ordering, exact waiting identity fencing, central/sidebar parity, active
  worker/reviewer and passive/terminal colors, and reduced motion.

This document claims no installation, runtime mutation, admission claim, merge
or new model/token use. After this pin passes green baseline and merges, the
executor may run only the deterministic stopped prepare/build/install/preflight
and one controlled model-free card-13 completion plus restart-dedupe proof.

## Repeat install and proven creation-base blocker

- Exact source `50136576ce287ed0563b54144523ec14ab34d76c`, tree
  `db4ee06ad176c91402cfc852cc63e1e2252148f3`, was deterministically installed
  at `2026-08-14T09:00:51Z`. Receipt SHA-256 is
  `0b8744901c8ddf9223ee8bab4add0f645e59bc244888d5d1846b4033d343ee2c`;
  verified backup `i12-20260814T090051Z` is retained.
- The controlled start passed the exact cards-11/12 quarantine, launched zero
  model actions and received current OPEN/passing/CLEAN/MERGEABLE PR facts. A
  read-only provider/observer probe proved the stock SCM event emitted terminal
  eligibility for the unchanged exact head. Direct read-only terminal-engine
  reproduction then failed before claim with `policy task creation base is
  unavailable`.
- The exact card-13 session row had empty `diff_base_sha` and `diff_base_ref`.
  Source review proved provisioning resolved those fields, but stock lifecycle
  `mergeMetadata` omitted them before its durable session update.
- Managed-source [PR #42](https://github.com/orenvlad-ai/dcp-orchestrator/pull/42)
  retains both fields for every future provision and performs one exact startup
  repair only when the unchanged card/session/task/worktree/branch/PR/head/base/
  review/admission/check identities and zero active model actions all match.
  Every mismatch is a no-op; ordinary Git/provider/review/FIFO merge gates are
  unchanged. Exact head `705697df72f4954140904698273587c31cf65ac1`, review
  `4935928889` and CI run `31788673005` passed. Ordinary merge is
  `f54b597572d7204096cb16581becee067e1febdc`, tree
  `a56f684853989623fe84c15f2a7958ffa03fd95e`.

This correction pin claims no install, runtime start, model call, admission
claim or merge. Installed source `50136576...` / `db4ee06a...` is the sole
allowed predecessor for the next deterministic stopped replacement.
