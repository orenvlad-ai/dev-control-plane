# I18 card-13 admission/status-dot repair preflight

evidence_status: pre-install-pin
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
