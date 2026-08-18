# I3 upstream qualification

This is the implementation-time record for **DCP · Штатный AO · И3**. Evidence
was gathered from fresh source checkouts and isolated runtime roots outside the
DCP repository on 2026-08-07.

The current governed managed-source descendant is PR #57 merge
`f94b0603916c410419654ca4752ffa9084116ff8`, tree
`11a9856ea2504ef923221a97064a59a762a99ed8`. It preserves the exact official
`v0.12.1` ancestry recorded below and remains build/test input until its
separate immutable pin and deterministic stopped installation qualify it.

## Stable release and primary-source provenance

The official GitHub release API identified
[`v0.12.1`](https://github.com/Untrivial-ai/agent-orchestrator/releases/tag/v0.12.1)
as the latest non-draft, non-prerelease stable release, published
`2026-08-05T18:28:27Z`. Its release body states that it was built from
`Untrivial-ai/agent-orchestrator@1df40e93772c2c48e916870d9c3ddf8f29a69f84`.

- Official remote:
  `https://github.com/Untrivial-ai/agent-orchestrator.git`.
- Tag: `v0.12.1`, a direct commit ref.
- Commit: `1df40e93772c2c48e916870d9c3ddf8f29a69f84`.
- Git tree: `36bf30cc4960c10f0d94fc63a8ff0a4dd22bb8a8`.
- Commit time: `2026-08-05T17:04:16Z`.
- GitHub commit verification: `verified=true`, `reason=valid`, verified at
  `2026-08-05T17:19:52Z`.
- Apple-silicon release asset digest reported by GitHub:
  `sha256:f9cf073e5dece2b647875473d0f44628cd7d4451c08ea61dbe4dc4e83b9607cb`.

Pinned primary material:

- [README](https://github.com/Untrivial-ai/agent-orchestrator/blob/1df40e93772c2c48e916870d9c3ddf8f29a69f84/README.md)
- [development guide](https://github.com/Untrivial-ai/agent-orchestrator/blob/1df40e93772c2c48e916870d9c3ddf8f29a69f84/docs/development.md)
- [CLI/daemon boundary](https://github.com/Untrivial-ai/agent-orchestrator/blob/1df40e93772c2c48e916870d9c3ddf8f29a69f84/docs/cli/README.md)
- [architecture](https://github.com/Untrivial-ai/agent-orchestrator/blob/1df40e93772c2c48e916870d9c3ddf8f29a69f84/docs/architecture.md)
- [telemetry](https://github.com/Untrivial-ai/agent-orchestrator/blob/1df40e93772c2c48e916870d9c3ddf8f29a69f84/docs/telemetry.md)
- [Apache-2.0 LICENSE](https://github.com/Untrivial-ai/agent-orchestrator/blob/1df40e93772c2c48e916870d9c3ddf8f29a69f84/LICENSE)

## License, NOTICE and dependency observations

The tracked root `LICENSE` is Apache License 2.0, Copyright 2026 Untrivial, with
SHA-256
`1a2219722b7ef58364065e9073a2cb2831891eb147a785742a31431c9cddad1d`.
A case-insensitive scan of every tracked path at the tag found no `NOTICE` file.
The license is preserved byte-for-byte in
`third_party/agent-orchestrator/LICENSE` and the DCP modification boundary is
recorded in repository `NOTICE` and provenance.

`frontend/package.json` still declares `license: MIT`, inconsistent with the
root Apache-2.0 file. DCP does not publish or redistribute an I3 binary; it
fetches official source for a local lab build. Any future distribution must
resolve that metadata ambiguity and generate a complete dependency/NOTICE
inventory rather than treating the root file as the whole answer.

Locked installation reported known npm audit findings during qualification:
three vulnerabilities in the root tool package, 35 in the Electron frontend
(including 29 high and one critical), and ten in the landing package. I3 does
not widen scope into dependency remediation; it records these as upstream
local-build risk and never presents the source build as a hardened release.

## Build and runtime prerequisites

The pinned development guide requires Go 1.25.7+, Node.js 20.19+, npm 10+, Git,
an agent CLI and, on macOS, `tmux`. The qualification Mac was Apple silicon,
macOS 26.4.1, with:

- Go 1.26.5;
- Node.js 20.20.2 and npm 10.8.2 for upstream CI parity;
- Git 2.50.1 and tmux 3.7b;
- authenticated Codex CLI 0.145.0.

The frontend dependency graph emits engine warnings because current
`@electron/rebuild` metadata asks for Node 22.12+, while upstream docs and CI
still select Node 20. The documented/CI Node 20 path nevertheless completed
installation, typecheck and native packaging.

## Clean upstream build and source-run result

Before any DCP source change, a detached checkout of the exact release passed:

- root, frontend and landing `npm ci` using their committed lock files;
- `cd backend && go build ./...`;
- serial `cd backend && go test -p 1 ./...`;
- `cd frontend && npm run typecheck`;
- `cd frontend && npm run package`, producing the native Darwin arm64 Electron
  app bundle.

The full frontend Vitest run passed 1,591 of 1,592 tests and timed out once in a
reviewer-selection UI test; the exact failed test passed immediately when rerun
alone. The DCP isolation patch's focused test and typecheck passed. This is
recorded as a flaky upstream test risk, not hidden as a clean full-suite pass.

A source-built Go daemon then ran on `127.0.0.1` with explicit external
`AO_RUN_FILE` and `AO_DATA_DIR`. Native CLI calls reported ready health,
successful migrations, Git/tmux readiness and installed+authorized Codex. A
remote-free synthetic repository was registered through `ao project add` and
returned through `ao project ls`.

The supported task boundary is the documented thin CLI over the daemon:

```text
ao project add  -> POST /api/v1/projects
ao spawn        -> POST /api/v1/sessions
```

`ao spawn --project dcp-lab --kind worker --harness codex --prompt ...` creates
an isolated worktree and passes the prompt through the upstream Codex adapter.
No direct SQLite or runtime access is needed. Upstream `ao start` is not used:
at this release it is a desktop bootstrapper for the installed application,
not the contributor source-daemon command.

## Telemetry, updater and minimum patch

Upstream provides supported telemetry controls. DCP sets the renderer,
local-event, local-metric and remote-export switches to `off` and applies the
documented `AO_TELEMETRY_DISABLED_EVENTS=*` kill switch. Renderer bootstrap
returns null when `AO_TELEMETRY_RENDERER=off`, so the PostHog client is never
initialized; daemon remote export is also off.

The native lab runs `electron-forge start`, making `app.isPackaged=false`.
Upstream `initAutoUpdates()` returns before updater initialization in this mode,
and macOS package relocation is also skipped. Therefore I3 needs no updater or
telemetry code patch.

`AO_DATA_DIR` and `AO_RUN_FILE` do not control Electron's Chromium profile,
caches, local storage and crash-dump root; upstream hard-codes those below
`~/.ao`. The sole patch adds an absolute `AO_ELECTRON_USER_DATA_DIR` override,
preserves upstream defaults when absent and adds three focused tests. Its exact
SHA-256 is
`54e67a4d3bc338cd40215142bbecc7cd45c3ebddd4b54224ed982b63c5b8bc14`.

## Patched native launch and acceptance result

The managed patched checkout repeated the backend build, full serial Go suite,
14 focused app-state tests, TypeScript typecheck and Darwin arm64 native
package successfully. The source launcher then opened the upstream Electron UI
with the isolated userData root and a ready Go daemon on `127.0.0.1:43231`.
Native doctor checks passed Git, tmux, Codex resolution, Codex authorization and
AO's Codex launch flags.

The acceptance canary used exactly one real adapter invocation. Native AO
registered `DCP Lab`, created one `DCP I3 Canary` worker session and branch
`ao/dcp-lab-1/root`, created one tmux-backed worktree and launched the native
Codex harness. The worker created only `dcp-ao-i3-marker.txt`: 17 bytes,
hex `44435020414f2049332063616e6172790a`, SHA-256
`537726ede29e632ae1c660074bb5c100a1c0e3a3320e05a7e69b508f5d97e9a1`.
Target HEAD did not change, and neither target nor worktree had a remote;
there was no commit, push or pull request. The native UI exposed the project,
session, Codex terminal, mutation check and final result.

During a two-minute window spanning submission and completion, 59 snapshots of
the source Electron main/helpers and AO daemon found only `127.0.0.1`/`::1`
sockets between UI, Vite and daemon; non-loopback AO socket observations were
zero. Codex provider/MCP traffic was outside this AO telemetry measurement.
After evidence capture, native AO terminated the session, reclaimed its
worktree and removed the project. The exact clean remote-free target was moved
to macOS Trash; no active canary project, session, worktree or target remains.
Minimal screenshot, network and canary summaries remain outside Git under
`$DCP_AO_LAB_ROOT/evidence`.

## Managed-source and update strategy

DCP uses a verified external checkout rather than a new fork repository,
vendor copy or subtree. Git stores only:

- the release/commit/tree/license/NOTICE lock;
- the exact narrow patch queue;
- source launcher, adapter and deterministic tests;
- Apache license and provenance.

`bin/dcp-ao prepare` fetches the exact tag into `DCP_AO_LAB_ROOT`, checks the
official remote, commit, tree and license, proves the NOTICE result, applies the
patch and refuses any other diff or untracked source file. Future maintenance
selects a new stable release, updates the lock, rebases the patch from a clean
tree and repeats the entire build/run/UI/canary/network gate. No floating branch,
release feed or installed AO state can silently change the active foundation.

## I8 packaged-application qualification (2026-08-08)

I8 retains official Agent Orchestrator `v0.12.1` at commit
`1df40e93772c2c48e916870d9c3ddf8f29a69f84` through the managed-source
boundary. The exact repository-owned patch queue has SHA-256
`047c9f74902ede19b6e3a3ba753fc7b2702a322a9be709fb0e975cc5628314d2`.
It packages a native arm64, locally ad-hoc-signed application at
`/Users/ovlmacbook/Applications/DCP Orchestrator.app`, bundle id
`pro.devcontrol.dcp-orchestrator`, without creating a vendor copy or Git fork.

Model-free qualification passed the full serial Go suite, renderer typecheck,
74 selected renderer tests, repository audit, shell/diff checks and native
package/install/preflight. Artifact checks proved the exact application,
executable, daemon, service, fixed port, Info.plist, signature, receipt,
embedded-daemon digest and ASAR digest identities. The daemon produces
`dcp-orchestrator-daemon` in authenticated status and the run-file. The gateway
requires both facts, and tests cover missing, mismatched, stale, foreign,
duplicate and occupied-port identities.

The packaged one-shot supervisor receives exact daemon connection paths only
for its start/exit hooks. Targeted and full tests prove that the retained tmux
shell and Codex child do not inherit `AO_DATA_DIR` or `AO_RUN_FILE`; the worker
still runs with strict, ephemeral, ignore-user-config isolation and successful
exit is recorded as Idle.

Release-gate source and bundle scans proved no updater initialization, feed,
maker, publisher, packaged updater module, PostHog/Sentry client or host,
telemetry key/install identity/reservoir, or crash reporter initialization.
Runtime socket inspection found no external network connection in the exact
app, daemon or helper processes; loopback IPC remained expected. The selected
upstream dependency tree still reports recorded npm audit findings and Node 20
engine warnings, but those do not change this bounded local qualification and
remain an upstream maintenance risk rather than an I8 remediation claim.

The owner raised the cumulative live allowance from four to five model calls.
Exactly five were consumed with no automatic retry: one preserved diagnostic
stop-gate, then a successful cold call (`dcp-lab-2`), warm call (`dcp-lab-3`)
and two concurrent calls (`dcp-lab-4`, `dcp-lab-5`). The four qualified
sessions created separate exact marker files, reached Idle without duplicates
and remained visible in one persistent application backed by one daemon.
Minimal redacted summaries are retained outside Git below the canonical I8
evidence root; earlier I7 artifacts were neither changed nor removed.

A dedicated DCP Git fork is not created by I8. It is the next separately
owner-approved architectural stage after I8 acceptance; until then the exact
pin plus reviewed repository-owned patch queue remains the source authority.

## I10 managed-fork qualification (2026-08-08)

I10 replaces only that source boundary. The application source now belongs to
the private standalone repository
[`orenvlad-ai/dcp-orchestrator`](https://github.com/orenvlad-ai/dcp-orchestrator).
GitHub did not permit a private repository in the public upstream fork network
under the available account plan, so the approved fallback preserves the full
upstream Git ancestry in a private standalone repository. `origin` is DCP;
`upstream` is the official repository with push disabled.

Fork PR [#1](https://github.com/orenvlad-ai/dcp-orchestrator/pull/1) merged as
`e770c2745dbf3b839af7dc7a6789aea192208a06`, tree
`a85d5c1abac34371399065fdd521752ae687491f`. Its ancestry includes exact
upstream `v0.12.1` commit `1df40e93772c2c48e916870d9c3ddf8f29a69f84`
and the seven reviewable I8 commits. The last behavior-parity commit is
`23fe9bba77873075f32b813fb0a3c936598882fb`; its binary full-index diff from
the upstream commit has SHA-256
`047c9f74902ede19b6e3a3ba753fc7b2702a322a9be709fb0e975cc5628314d2`, exactly
matching the formerly active I8 patch.

The fork preserves the Apache-2.0 `LICENSE` byte-for-byte (SHA-256
`1a2219722b7ef58364065e9073a2cb2831891eb147a785742a31431c9cddad1d`), records
that upstream has no `NOTICE`, and adds DCP `NOTICE` and `DCP_PROVENANCE.md`
files whose SHA-256 values are respectively
`591f69f0abf358b44891fda2fbdf6cbf9e30bd0ef71bfc146fe92edfd1fb1637` and
`1063dee130fffa68a9b4ec6d5b94ad6ae951d1abadd8de3d6b24bcc04c917fdf`.
The packaged application includes all three files.

The fork's pull-request and default-branch CI passed backend tests/build,
renderer typecheck and the 74 I8-selected tests, native arm64 packaging,
identity/namespace and artifact gates, and absence checks for updater,
telemetry and crash reporting. The workflow is read-only and defines no
release, publisher, updater, schedule, manual dispatch or artifact upload.
Before the fork merge, the exact source was also built and packaged in a fresh
external build/state contour. The canonical application and its state were not
touched during this proof, and no model canary was run.

`upstream/dcp-orchestrator.lock` is now the sole active source pin in
`dev-control-plane`. It binds the exact fork revision, tree, parity anchor,
license/NOTICE/provenance digests and upstream ancestry. The former patch and
copied license/provenance files are removed from the active tree and remain
available only as historical Git evidence. A canonical replacement must first
pass all model-free gates from exact merged `dev-control-plane` main, verify the
old installed identity, stop the exact app cleanly, and create a checked backup
of its bundle plus applicable DCP state/data. I8 behavior remains unchanged and
the I9 target design remains inactive.

## I11 durable task-foundation qualification (2026-08-09)

Fork PR [#2](https://github.com/orenvlad-ai/dcp-orchestrator/pull/2) merged as
`417a844e7b85b6b14ae9a1855009d8bf139ee43d`, tree
`15a77f0804c99c8b603b96aaf7797dad8e77b4df`. Its pull-request CI passed in
[run 31303457144](https://github.com/orenvlad-ai/dcp-orchestrator/actions/runs/31303457144),
and exact merged-main CI passed in
[run 31303746653](https://github.com/orenvlad-ai/dcp-orchestrator/actions/runs/31303746653).
The Apache-2.0 license, DCP NOTICE/provenance digests, exact I8 parity anchor and
official upstream ancestry remain unchanged.

Part A source gates independently proved that a new fork executor receives the
DCP-specific `AGENTS.md`/`CLAUDE.md`, the exact pinned operating and target
contract reference, private managed-fork/additive-migration/generation/check
rules, and explicit prohibitions on `~/.ao`, installed upstream AO, update,
publisher, telemetry, crash, real-target and hidden future-role paths. The gate
rejects restoration of the conflicting upstream operational contract.

Backend tests cover migration 0048 on fresh and existing-I8 databases,
idempotent equal replay, conflicting replay, invalid target, task/event atomic
rollback, monotonic event sequence and stale revision rejection. The full Go
test suite and build passed. SQL/OpenAPI/TypeScript regeneration reproduced a
clean tree. Renderer typecheck plus 14 applicable DCP suites passed 282 tests,
including one stable synthetic SUBMITTED card, no duplicate and no normal
manual Orchestrator affordance; programmatic backend capability remains tested.
Native arm64 source/package identity, namespace, license, updater, telemetry
and crash gates also passed. A separate exact-merged-fork integration build
through `bin/dcp-ao build` used an isolated temporary lab root and passed the
same gates. Its packaged main executable, daemon and ASAR SHA-256 values were
respectively
`3d03c4567db8f86a5cb72ad76588a61ea317b1132410fe291964c7b69fb531ec`,
`915a618419e943b7f4aeb02067a598a907dd8ffd612696de093937ccc74b3669` and
`6e5cc27c093c11d8e3844e7784ce13071ca7478d43d71f79cc2d4dc5fbe26d10`.

The isolated runtime proof used disposable state and a clean, single-commit,
remote-free target. Initial submit returned 201 for task
`dcp_task_5eb860cf-98af-4ec8-be03-044773ddf859`; equal replay returned 200 with
the same id and exactly one event. Restart retained SUBMITTED revision 1 and
event sequence 1, with no sessions, worktrees or task process. The real Codex
binary was shadowed by `/usr/bin/false`; the proof records ZERO model calls and
no DCP worker submission.

For rollback compatibility, the exact prior I10 daemon at
`e770c2745dbf3b839af7dc7a6789aea192208a06` reopened the same database after
migration 0048; the task/event survived and the I11 daemon reread them. The
migration is additive and prior code ignores the new tables. Canonical install
still requires exact merged pins, all green gates, a stopped contour or one
proven canonical inactive app/daemon pair, and a verified backup of the
existing bundle, receipt, state and data. No owner
acceptance is inferred from this technical qualification.

## I12 managed-fork reviewer qualification (2026-08-10)

I12 retains the same official `v0.12.1` ancestry, Apache-2.0 LICENSE,
DCP NOTICE/provenance and exact I8 parity anchor. Application changes were
reviewed in managed-fork PRs
[`orenvlad-ai/dcp-orchestrator#3`](https://github.com/orenvlad-ai/dcp-orchestrator/pull/3)
and
[`orenvlad-ai/dcp-orchestrator#4`](https://github.com/orenvlad-ai/dcp-orchestrator/pull/4),
with the exact event-delivery closure in
[`orenvlad-ai/dcp-orchestrator#5`](https://github.com/orenvlad-ai/dcp-orchestrator/pull/5).
The packaged verdict-channel closure is
[`orenvlad-ai/dcp-orchestrator#6`](https://github.com/orenvlad-ai/dcp-orchestrator/pull/6).
The deterministic structured-result closure is
[`orenvlad-ai/dcp-orchestrator#7`](https://github.com/orenvlad-ai/dcp-orchestrator/pull/7).
The installed-Codex worker argv compatibility closure is
[`orenvlad-ai/dcp-orchestrator#8`](https://github.com/orenvlad-ai/dcp-orchestrator/pull/8).
The linked-worktree metadata sandbox closure is
[`orenvlad-ai/dcp-orchestrator#9`](https://github.com/orenvlad-ai/dcp-orchestrator/pull/9).
The exact synthetic-PR terminal merge is
[`orenvlad-ai/dcp-orchestrator#10`](https://github.com/orenvlad-ai/dcp-orchestrator/pull/10),
with typed reviewer config preservation in
[`#11`](https://github.com/orenvlad-ai/dcp-orchestrator/pull/11) and the native
card-name compatibility closure in
[`#12`](https://github.com/orenvlad-ai/dcp-orchestrator/pull/12), followed by
the exact single-PR prompt closure in
[`#13`](https://github.com/orenvlad-ai/dcp-orchestrator/pull/13) and the exact
typed worker-network closure in
[`#14`](https://github.com/orenvlad-ai/dcp-orchestrator/pull/14), followed by
strict CLI config preservation in
[`#15`](https://github.com/orenvlad-ai/dcp-orchestrator/pull/15), and exact
native terminal-profile alignment in
[`#16`](https://github.com/orenvlad-ai/dcp-orchestrator/pull/16), and exact
stock-native base derivation in
[`#17`](https://github.com/orenvlad-ai/dcp-orchestrator/pull/17), and exact
known absent-review handling in
[`#18`](https://github.com/orenvlad-ai/dcp-orchestrator/pull/18), and exact
GraphQL head-repository preservation in
[`#19`](https://github.com/orenvlad-ai/dcp-orchestrator/pull/19).
The bounded two-task I13 Stage 1 admission implementation is
[`#20`](https://github.com/orenvlad-ai/dcp-orchestrator/pull/20). Model-free
preflight found card 8 and PR #5 were already immutable pre-stage evidence, so
[`#21`](https://github.com/orenvlad-ai/dcp-orchestrator/pull/21) binds the fresh
cohort to cards 9/10 and closes the browser broker cancellation race exposed by
CI. Canary then exposed a false `canonical_main_diverged` packet after the first
merge advanced exact `origin/main`; [#22](https://github.com/orenvlad-ai/dcp-orchestrator/pull/22)
retains that audit packet and adds exact fast-forward/merge-tree proof plus one
startup-only model-free recovery. The separately reviewed Stage 2 source is
managed-fork [#23](https://github.com/orenvlad-ai/dcp-orchestrator/pull/23),
which adds only the exact v1 incident, one-shot arbiter and bounded same-worker
repair path. Managed-fork [#24](https://github.com/orenvlad-ai/dcp-orchestrator/pull/24)
corrects the strict structured rollout-budget configuration and preserves the
proven pre-provider rejection in one bounded audit row before re-arming only
the same incident/generation. Managed-fork
[#25](https://github.com/orenvlad-ai/dcp-orchestrator/pull/25) replaces the
provider-rejected root response-schema composition with an all-required
enum-only envelope, retains trusted cross-field validation and adds only the
exact migration-0054 no-inference/no-result/no-token audit/re-arm. The current
immutable source merge commit is
`182f7a1a95d4e1705de63355e65599b9d79f2c12`, tree
`3f4c9c7a6efc9a7164852eeaafde4423ef9cec6f`. Its deterministic correction
install and resumed live qualification are deliberately not claimed by this
pin revision.

The subsequent deterministic install and one-call qualification reached the
truthful terminal state documented in
[I13 Stage 2 terminal BLOCKED evidence](I13_STAGE2_BLOCKED_EVIDENCE.md): the
single inference returned a semantically invalid zero-fresh-review recovery
path, trusted validation rejected it, and no wake, new review or second merge
occurred.

The owner-approved exact-incident correction is implemented by managed-fork
[#26](https://github.com/orenvlad-ai/dcp-orchestrator/pull/26). It passed the
source and package checks and merged normally at
`baac2921a6901e836cbbf3759c3c42f5259ea37c`, tree
`a1ecbb79bd14a48ee270e6ce320633f2227cfe46`. Migration 0055 preserves the
rejected row and artifacts while adding one exact generation-2 call fence; the
successor decision omits model-owned worker/reviewer limits and the trusted
daemon enforces the fixed `1/1` policy. This pin revision does not claim
installation, successor inference or live recovery.

The separately reviewed model-free validation correction is implemented by
managed-fork [#27](https://github.com/orenvlad-ai/dcp-orchestrator/pull/27).
Both source/package checks passed and it merged normally at
`6f1b5f9828853b6c597d6e6b82fda52ced097b61`, tree
`7cb55d85073af960944a645e2fbe13503e98bf4f`. Migration 0056 adds only the
exact observed-result audit fence and the trusted parser admits only the
already frozen nested merge-tree digest. No new model-call path exists. Pin PR
#145 subsequently passed its exact authorized baseline rerun, merged normally
at `0df41738a68d89aa1a9239d577d69cd5aff23d5b`, and the source passed
deterministic prepare/build/install/preflight. Model-free startup accepted the
unchanged successor result once. The decision-boundary restart consumed the
only card-12 wake, but stock native resume failed before Codex launch because
the preserved session lacks a restorable `agent_session_id`. The successor row
is terminal `failed/repair_launch_failed`; the post-terminal restart created no
duplicate call, wake, review or merge. Exact live evidence is in
[I13 Stage 2 successor terminal evidence](I13_STAGE2_SUCCESSOR_TERMINAL_EVIDENCE.md).

The separately reviewed exact card-12 fresh worker recovery is implemented by
managed-fork [#28](https://github.com/orenvlad-ai/dcp-orchestrator/pull/28).
Required source/package checks passed and it merged normally at
`fbcf4929f9192f7cce9c5097b0bc6a449d28e663`, tree
`2ce917e525690d0cd05e060b552dc8bd072b8a15`. Migration 0057 binds one
subordinate generation-1 row to every immutable predecessor identity/digest
and separate fresh runtime identity. The trusted path permits one hard-budget
stateless worker, one guarded same-branch head and at most one new
context-free review before the existing admission and terminal-merge gates.
This pin revision claims no installation or live action.

Exact `fbcf4929f9192f7cce9c5097b0bc6a449d28e663` then passed deterministic
prepare/build/install/preflight. Its first controlled start stopped before the
worker call fence at `preflight_failed/identity_drift`, with worker/reviewer
counts 0/0 and no fresh runtime/session/artifact/head. Exact Git proof showed
the frozen conflict path has `arbiter intent A` on current main and `arbiter
intent B` on the old candidate, so its name-status is modified (`M`) rather
than added (`A`). Managed-fork
[#29](https://github.com/orenvlad-ai/dcp-orchestrator/pull/29) retains that
failure in migration 0058 and corrects only the exact assertion. Required
source/package checks passed; it merged normally at
`75a14431a3433f581755f2e0ec096814e3e9ecb1`, tree
`a993819f30776ca595d5687f098ec00b98d67ba2`. This pin revision claims no
installation or resumed live action.

The separately reviewed exact model-free continuation is implemented by
managed-fork [#30](https://github.com/orenvlad-ai/dcp-orchestrator/pull/30).
Its `source` check passed in 4m40s and its `package` check passed in 1m13s; the
ready PR merged normally at `a7b5476fb886bcbb6bbd91aa89da17966547b3b8`,
tree `53525c260b4de1ed749aeb4c89f4e085e433c9bd`. Migration 0059 binds one exact
subordinate row to the immutable failed predecessor and permits only one
model-free Git action and one fresh exact-head reviewer fence. The source
qualification also passed full serial backend tests/build, generated sqlc/API
parity, renderer type/tests, the managed source gate and a copied-SQLite
migration/CAS proof. This pin revision claims no installation or live action.

The separately reviewed exact provider-base correction is implemented by
managed-fork [#31](https://github.com/orenvlad-ai/dcp-orchestrator/pull/31).
Its `source` check passed in 4m53s and its `package` check passed in 1m49s; the
ready PR merged normally at `b22d8961fcc367d414510a5daae53eab19bd2578`,
tree `f10fed7982187a3a963b85c93285e641c41c289d`. Local qualification also passed
the full serial backend suite/build, source gate, generated parity, packaged
renderer 15/348 gates, exact live retained-rebase preflight and copied-live
SQLite migration/immutability proof. This pin revision claims no repeat
installation or runtime action.

The separately reviewed cold-start quarantine and recovery is implemented by
managed-fork [#32](https://github.com/orenvlad-ai/dcp-orchestrator/pull/32).
Its `source` check passed in 4m32s and its `package` check passed in 1m53s; the
ready PR received a semantic/security review with no findings and merged
normally at `032e16aa3025858eeddecc1a25e87d4ec8ea4f18`, tree
`cc519e93923e02d59463bbe14dd77192a237ce95`. Local qualification passed the
full serial backend suite/build, source gate, generated parity, renderer
typecheck, package inspection, focused cold-start/crash/restart restore tests,
and a copied-live SQLite bootstrap/restart proof. The latter produced one
unchanged recovery row, two unchanged quarantine identities, zero calls, and
verification counts 1 then 2. This pin revision claims no installation or live
action.

That exact source was deterministically built, installed and preflighted. Its
first controlled start proved the quarantine before native restoration: cards
11/12 remained bare shells with zero descendants and no governed worker call.
The recovery failed before backup/action as
`failed/preflight_or_backup_failed`, revision 1, at trusted counters
`0/0/0/0`, because `/opt/homebrew/bin/gh` is a symlink and the verifier
correctly requires a physical regular file. Managed-fork
[#33](https://github.com/orenvlad-ai/dcp-orchestrator/pull/33) preserves that
exact zero-call failure in migration 0062, re-arms only the same row at revision
2, and substitutes the independently proven physical binary path without
changing its expected digest. Local qualification passed the source gate,
generated parity, full serial backend suite/build, renderer typecheck and a
copied-live SQLite migration/immutability proof. Its `source` check passed in
4m48s and `package` passed in 1m23s; an exact-head semantic/security review had
no findings. The ready PR merged normally at
`798e9bfb8f75846d846f2ec2d4dfc9ec0076573b`, tree
`e5668c51fbc3c7aae872cafbe4759fc405fa0677`. This pin revision claims no repeat
installation or live action.

Source PR #33 was then deterministically installed. Its controlled start again
proved the fence before restoration with bare cards 11/12 and no governed
worker, but recovery failed before backup/action at revision 3 with counters
`0/0/0/0`. The exact preserved Git `AUTO_MERGE` tree ref was the sole new
model-free precondition. Managed-fork
[#34](https://github.com/orenvlad-ai/dcp-orchestrator/pull/34) records that exact
failure in migration 0063, re-arms only the same row at revision 4, validates
the exact tree/file/blob/marker identities and seals the ref into the backup.
Copied-live SQLite migration and copied exact Git reset proofs passed, as did
the source gate, generated parity, full serial backend suite/build and renderer
typecheck. Its `source` check passed in 4m53s and `package` in 1m38s; exact-head
semantic/security review found no issues. The ready PR merged normally at
`04a967c26499a482fbff9a204bab046d79d2a2e2`, tree
`fedee6276e8ce4a492d3c298aaf4bf843179c8bc`. This pin revision claims no final
repeat installation or live action.

That exact source was then deterministically built, installed and preflighted.
The terminal start established the quarantine before restoration, left cards
11/12 as bare shells and launched zero new worker or arbiter calls. The sole
model-free action sealed backup digest
`82d0e5834375c380069e7d48a7fdb2066371670d92733ce59545718469a4f3dd` and
produced the exact clean local rebase head
`4de6ff1a0b80223a9b32a05ba68cf0b665296081`. Git retained `REBASE_HEAD`; the
trusted postcondition rejected it before push. The durable result is terminal
`failed/model_free_action_failed`, revision 7, at `0/0/1/0`. A controlled
restart advanced quarantine verification to 4/4 with no duplicate. Remote PR
#9 remains unchanged; no fresh review, admission rebind or merge exists. Exact
qualification proof is in
[cold-start recovery terminal evidence](I13_STAGE2_CARD12_COLD_START_QUARANTINED_RECOVERY_TERMINAL_EVIDENCE.md).

Live I13 Stage 1 qualification then used exactly two fresh native identities:
card 9 `DCP:i13-admit-a` and card 10 `DCP:i13-admit-b`. The workers used 20,437
and 20,055 tokens; their one automatic reviewer each used 25,539 and 9,976
tokens. The four-call total was 76,007 tokens, with no refresh wake or repeated
review. Review completion durably ordered card 10 first and card 9 second.
PR #6 exact head `3afd3d4cbcc2fe4a6bf2fde3e747213e5c874d53` merged once at
`5e65c167d8d9d36d70c89fc8e9b5b07497905645`; PR #7 exact head
`649c60cbe6c8542f0a3d20b05b11ae5c54a79263` merged once afterward at
`dbaf01b05e85ffffa4c843a905e2fe5229eaf0da`. Both exact heads had one
approved no-findings structured run and one successful named check.

The second row stayed durable and model-free while the correction was built
and installed. Its original 941-byte false `canonical_main_diverged` packet is
retained in `recovered_incident_packet`; exact fast-forward ancestry and a clean
merge tree recovered it on startup without changing task/session/PR/head/review
identity. Two controlled starts retained two succeeded rows, FIFO sequence,
lease and merge SHA, while counts stayed seven reviews, nine runs and ten cards
with no card 11. Both canary sessions then terminated through the stock native
lifecycle, which reclaimed only their worktrees while their retained cards
still project `Merged`. The target checkout is clean and fast-forwarded to
exact `origin/main` `dbaf01b05e85ffffa4c843a905e2fe5229eaf0da`; the installed
receipt is exact fork `b23b519cd532555c203863586032d157fc1c8c13`, daemon SHA-256
`c9d59d2c2a8453d278ebc45a5a4872e8f96d35fd9ad29cad6cd109a0043cc6a1`
and asar SHA-256 `a1206d002b16a8d9a3cb4485c4522b4fe685fdb102840d1d96530a4f11a4ff90`
at `2026-08-11T14:26:15Z`. No arbiter was implemented or invoked.

The source proof is model-free: full serial backend tests/build, generated
SQL/OpenAPI/TypeScript parity, frontend typecheck, focused renderer tests,
source boundary checks and native arm64 packaging pass. The reviewer path
reuses stock review storage/engine/runtime/delivery, removes the unsupported
Codex exec approval argument, enforces read-only execution, and adds supervised
exit plus event-driven single-flight/restart reconciliation. The bounded
follow-up restores only the proven missing preserved worktree and verifies its
saved identity, clean state and exact PR head before the same reviewer terminal
launches. The stock SCM observer includes a terminated session only while the
single durable missing-worktree proof remains unused; a second matching failure
or any resulting run consumes that visibility. No new service, database,
scheduler, watcher, heartbeat or migration is introduced. Live evidence uses a
private reviewer-pane `ao` alias atomically and identity-bound to the same exact
embedded supervisor executable only for compatibility. Codex does not receive
that alias or choose a callback command: native schema/last-message output
supplies one bounded result to the trusted supervisor, which independently
binds every identity and current exact PR head before one guarded existing
`ReviewRun` update. No reviewer network, daemon/GitHub credentials, global PATH,
retired AO discovery or another persistence authority is present.
The worker-side proof separately runs the generated `accept-edits` command
through the real Codex parser with `--help` and validates its config/features
surface with `features list`; neither path can make a model request. The worker
uses `approval_policy="on-request"` plus explicit `workspace-write`, emits no
exec-level `--ask-for-approval`, and rejects unknown permission modes. PR #9
adds only the concrete linked worktree's verified gitdir and common `.git` as
writable roots. Its real installed-sandbox test reproduces the baseline
`git add` denial, proves success with both roots, rejects invalid topology and
proves the reviewer retains no write roots; every probe is model-free.

The failed I2/I3 runs and PRs #1/#2/#3 are preserved as immutable evidence and
are not changed, reused, retried or merged. The preserved `dcp-review-lab-4` worker
call reached native session `019fece4-e13f-79b1-b3af-c0e6392ebdb5`, consumed
16,222 tokens and stopped with only an untracked marker because Git metadata
was outside its sandbox; it has no commit, PR or reviewer run. After the exact
current-pin install, card 6 and card 7 consumed two of the original three-worker
allowance. Card 7 created the fresh minimal unmerged PR and the exactly one
automatic reviewer approved its exact head, so the reviewer allowance is
consumed. One unused emergency worker call remains, but no new card or model
call is permitted for this approved run. Only the trusted daemon may terminally
merge the fresh exact head
after structured approval, the successful named `dcp-review-lab` check, no
unresolved thread and fresh CLEAN/MERGEABLE provider facts. Restart must
preserve the terminal Merged projection without a second reviewer or merge;
the synthetic repository has no deploy and no deploy fact is invented.

## Canonical synthetic-PR terminal qualification (2026-08-11)

The terminal addition remains on the exact official `v0.12.1` ancestry and I8
parity anchor. It adds one migration only on the existing `ReviewRun` table,
one guarded claim/complete/fail transaction in the existing SQLite authority,
and one event-driven provider mutation through the stock SCM adapter. It adds
no service, database, task-card type, watcher, scheduler, queue, general retry,
arbiter, Release Train or production authority.

Model-free source proof covers exact worker/project/profile/task/prompt,
base/head/branch/worktree/Git-dir/PR identity; approved structured verdict with
no findings; required successful named check; resolved threads; provider
OPEN/MERGEABLE/CLEAN state; concurrent single-winner claim; provider error and
uncertain restart behavior; succeeded restart reconciliation; and terminal
Merged projection. The sole submit adapter separately proves that `dcp-lab`
rejects any mutation profile while `dcp-review-lab` requires the exact profile,
task id, remote, clean base, topology and typed worker/reviewer config before a
single native spawn.

The first fresh terminal attempt is immutable card `dcp-review-lab-6`, Codex
session `019fefec-83f2-7090-a4e6-fcda57f262f9`: it consumed 29,309 tokens,
created one local commit `c92bbef`, and stopped after two bounded push attempts
both proved DNS denial inside the workspace-write sandbox. No remote branch,
PR or reviewer run exists. PR #14 model-free tests prove that only typed card
7+ with the canonical data/worktree/private/common Git paths, exact branch and
sole exact fetch/push origin receives worker network; cards 1-6 and the
structured reviewer do not. The failed card is never resumed or reused, and
card 7 later completed the successful worker path after the distinct fixes.

The first canonical submit after installing PR #14 failed closed before any
native card or model launch because the strict CLI config mirror rejected the
new typed marker. PR #15 adds that already-governed field to the mirror and
proves its exact JSON preservation while retaining unknown-field rejection.
The pre-spawn stop created no card 7 and consumed no worker call.

The eventual card `dcp-review-lab-7` created commit
`f10c825fced998c01a3e83ef4073451c3bd2e4a3` and ready PR #4. Worker session
`019ff01e-9d97-7cf3-b241-4d6820fe26e1` used 36,386 tokens; sole reviewer
session `019ff01f-9805-7c22-9bd4-54d53e99be5d` used 10,258 and persisted
approved/no-findings run `28025930-ecc0-481e-a13b-9fb5a5a14a94`. PR #16 aligns
terminal eligibility with native card 7+ and marker=true. Stock native spawn
leaves both session diff-base fields absent; PR #17 accepts only that pair and
binds the stored/fresh PR base to clean canonical `main` and `origin/main`, so
startup can reconcile the existing run without another model call. PR #18 then
accepts the adapter's exact domain `none` for the absent GitHub review while
empty, unknown and blocking provider decisions remain fail-closed. PR #19 adds
the missing `headRepository.nameWithOwner` to the stock GraphQL observation so
the exact-repository gate remains strict rather than accepting an unknown fact.

The final pinned install at fork merge
`1cca0af6043e3930b184e79d1f871b88ca402e01` reconciled the already-approved run
without another model call. The trusted daemon claimed run
`28025930-ecc0-481e-a13b-9fb5a5a14a94` once and squash-merged PR #4 at
`202ca32a0e8d563c6c478d094073246383720e5d`. Card `dcp-review-lab-7` projected
`Merged` before restart and the same card/run/SHA projected `Merged` after a
controlled app/daemon restart. Counts remained one review, one run and seven
cards, with no card 8 or active exact model descendant.

PRs #1/#2/#3 remain open on heads `abfcaa90208dedf84d66047d5c0ae7bd11152b1c`,
`7a140dcf62ccb086691263ce82328b5f299ff078` and
`33815247a6fab6b68c47c60a890c4f968c1dd459`. The synthetic repository has zero
deployments and only the `DCP Review Lab` PR check workflow; terminal `Merged`
is recorded without fabricating deploy evidence.

## Exact retained-candidate finalization source pin

The reviewed finalization contract merged in dev-control-plane PR #161 at
`9465a84ec44f72f6b7c245ebddeac22d722108ae`. Managed-fork
[PR #35](https://github.com/orenvlad-ai/dcp-orchestrator/pull/35) adds only
migration 0064 and the exact daemon-local finalizer for retained commit
`4de6ff1a0b80223a9b32a05ba68cf0b665296081`. It preserves the terminal
revision-7 predecessor and sealed backup, makes no local Git write, requires
the exact regular `REBASE_HEAD`/`ORIG_HEAD` conjunction, and fences one guarded
old-head force-with-lease push plus at most one stock exact-head reviewer.

PR #35 received exact-head semantic/security review with no findings. Its
`source` and `package` checks passed before ordinary merge at exact commit
`6f53f74f456b869c98bb82d928f671b54672808a`, tree
`0fab2ee443d8bf20a0efcc524851e8c9589e6dd9`, on 2026-08-13. The integration
pin retains official Agent Orchestrator `v0.12.1` ancestry and adds an
installer refusal for an active finalization. This pin stage claims ZERO model
calls and no install, runtime action, push, review, admission rebind or merge.

## Exact finalization audit-query correction pin

Exact source `6f53f74f456b869c98bb82d928f671b54672808a` was subsequently installed
and preflighted. Its first controlled start preserved quarantine 5/5 and bare
cards 11/12, but finalization failed before the action fence as
`failed/identity_drift`, revision 1, counters `0/0/0/0`. Both historical cold-
start audit rows remained present once. The defect was their old query
predicates: each requires its earlier authorized recovery revision and is not a
valid terminal-rev7 existence proof.

Managed-fork [PR #36](https://github.com/orenvlad-ai/dcp-orchestrator/pull/36)
adds only immutable migration-0065 correction audit
`52490d8c01eccc8f02984ec4d863895c0215950590cfc5309d00a1525eb8f11b`
and the dedicated exact validator. Copied-live SQLite up/query/down proof,
serial Go test/build, sqlc/API parity, frontend typecheck and the source gate
passed locally. Package and source CI passed, and exact-head semantic/security
review found no issues before ordinary merge at
`e15a6d22f83876b240fa61889b6821bd49904f28`, tree
`48d1266abc44de79bda0ca2865558d259325fc0d`. A final stopped prestart source
audit then found the remaining obsolete revision-0 executor gate before any
action. Managed-fork PR #37 binds that gate and engine validation to the exact
audited revision 2 and merged at `1f1e8cedf44d30773568f8801710f1371b14a47b`,
tree `4523bfacf690c15f75c155ccfc2f14831db7b2f2`. The existing installer guard
then protected the sole successful push. Its post-push base-snapshot validation
failed closed at revision 4 with action/reviewer counts `1/0`, and the private-
repository check was rejected twice before runner work by a GitHub billing/
spending-limit annotation. Managed-fork PR #38 preserves those exact facts and
adds only inspect-only post-push adoption at current-main base. It merged at
`15b51450b391fdc1ae0f172bbbf95275a6388030`, tree
`f819398a7e78ffa68630b62a3234e6e95283be57`. The existing installer guard
rejects every active state of the same finalization row. That source was
deterministically installed/preflighted while stopped; receipt SHA-256 is
`b362851fb43d772a7cbd1d1a85ebeaa6980f78a5e1b96d87f6ae74bb2b5eb0dc`.
Goose remains 65 and migration 0066 is unapplied. The resulting qualification
is technically `BLOCKED` on the human-only GitHub billing/spending condition;
the sole reviewer, admission rebind, merge and corrected-runtime restart were
not consumed. Exact proof is in
[REBASE_HEAD finalization terminal evidence](I13_STAGE2_CARD12_REBASE_HEAD_FINALIZATION_TERMINAL_EVIDENCE.md).

After explicit owner continuation, the unchanged exact-head check passed as
job `94521518361`. The installed source applied migration 0066 and only its
inspect-completed path: no second action/push occurred. Fresh ReviewRun
`efa36083-3efd-497f-90b7-db7e7fbf04d2` returned approved with empty findings,
admission sequence 4 rebound and PR #9 squash-merged once at
`5bfd20d3b3f5b7d9d9ccb02500b742a917e6ea01`. Finalization is `succeeded`
revision 9 at `0/0/1/1`. Controlled restart preserved one correction/review/
admission/merge and advanced quarantine to 8/8 with zero duplicate model or
mutation activity. The bundle is stopped. Exact proof is in
[REBASE_HEAD finalization success evidence](I13_STAGE2_CARD12_REBASE_HEAD_FINALIZATION_SUCCESS_EVIDENCE.md).

## Policy-driven happy-path v1 source pin

Managed-source [PR #39](https://github.com/orenvlad-ai/dcp-orchestrator/pull/39)
preserves the same official `v0.12.1` and I8 ancestry while adding only the
reviewed future-task policy. Required `source`/`package` CI and exact-head
semantic/security review passed before ordinary merge at
`5c9ce30bfdd61bc8cc49106c9eb3d62fbf867abd`, tree
`45660cc8293d78dded4235f9406586fd8771077d`. Model-free fixtures cover four
future tasks, the global three-slot cap and passive fourth waiter, equal and
conflicting replay, one review per exact head, bounded findings repair/new
head, duplicate SCM delivery, FIFO admission, main advancement, restart and
terminal dedupe.

Live card 13 then proved a narrower ordering gap: its CLEAN/MERGEABLE stock SCM
facts were acknowledged before admission sequence 5 existed, the immediate
terminal read remained passive on transient unknown facts, and later identical
snapshots skipped lifecycle notification. Managed-source
[PR #40](https://github.com/orenvlad-ai/dcp-orchestrator/pull/40) passed formal
exact-head semantic/security review plus required `source` and `package`, then
merged normally at exact commit
`70187c13ab0bc8bac07cd2d9ff27e230b866e087`, tree
`ee81758b33443a66835f785e2cb178b560808c15`. It adds only a stock-SCM-event
catch-up signal fenced to the exact durable waiting admission and one shared
native card/sidebar status mapper. Focused regression covers pending-to-wait,
later CLEAN-to-one-merge, new-engine restart dedupe, FIFO preservation, active
worker/reviewer pulse, steady queues/waits/terminal colors, parity and reduced
motion. This repair pin stage used ZERO model calls and claims no install or
live mutation; installed `5c9ce30...` remained the sole verified replacement
predecessor until deterministic stopped install/preflight.

That install completed at exact source `70187c13ab0bc8bac07cd2d9ff27e230b866e087`
and tree `ee81758b33443a66835f785e2cb178b560808c15`, but its first controlled
start failed closed before daemon wiring. Exact cards 11/12 had already reached
the stock terminal pair `exited/terminated` after their succeeded admissions;
their durable quarantine query admitted only the older `idle/non-terminated`
pair. Card 13 remained revision 9/waiting and no action/claim/model call ran.
Managed-source [PR #41](https://github.com/orenvlad-ai/dcp-orchestrator/pull/41)
adds only the exact terminal pair while rejecting mixed/active state and
retaining every session/admission/recovery identity gate. DCP CI run
`31783935999` passed source/package and ordinary merge produced exact source
`50136576ce287ed0563b54144523ec14ab34d76c`, tree
`db4ee06ad176c91402cfc852cc63e1e2252148f3`. Installed `70187c13...` is the sole
replacement predecessor until repeat stopped install/preflight succeeds.

The repeat stopped install then completed at exact source `50136576...`, tree
`db4ee06a...`, with receipt SHA-256
`0b8744901c8ddf9223ee8bab4add0f645e59bc244888d5d1846b4033d343ee2c`.
One controlled start passed quarantine and proved the stock SCM observer emitted
the new exact-head eligibility signal, but the terminal merger failed before
claim with `policy task creation base is unavailable`. Read-only reproduction
proved the provisioner had resolved the base while stock lifecycle
`mergeMetadata` discarded both fields before persistence. Managed-source
[PR #42](https://github.com/orenvlad-ai/dcp-orchestrator/pull/42) retains those
fields for future tasks and adds one exact, zero-active-model startup repair for
the unchanged card-13 identity. Exact-head review `4935928889` and DCP CI run
`31788673005` passed; ordinary merge produced source
`f54b597572d7204096cb16581becee067e1febdc`, tree
`a56f684853989623fe84c15f2a7958ffa03fd95e`.

That exact source was deterministically installed at
`2026-08-14T09:55:20Z`; receipt SHA-256 is
`5f8ce03ca79da650c23c4968eae2e1e9c3deed05dcd57c6d08e108bbe2c6a782` and the
verified backup is `i12-20260814T095519Z`. One controlled start repaired only
the exact passive card-13 creation base, then the stock observer/terminal merger
completed admission sequence 5 and merged unchanged PR #10 once at
`1b3f9fb266370326bbb35283fb51fb5226502c42`. Task revision 10, the sole ReviewRun
and admission/lease/merge identity persisted across controlled restart. The two
historical policy actions remain succeeded, active actions are zero and the
repair added zero model calls/tokens. Quarantine reached 14/14 and the canonical
bundle is stopped. Exact proof is in
[I18 success evidence](I18_CARD13_ADMISSION_STATUS_DOT_REPAIR_SUCCESS_EVIDENCE.md).

## Admission wake and Human Gate UI v1 terminal qualification

Managed-source PR #54 added the bounded post-commit admission signal and shared
terminal Human Gate projection, then its first installed start exposed the
remaining all-incident SQLite claim blocker without model or queue mutation.
PR #55 narrowed only that claim predicate to ignore an exact latest terminal
Human Gate. Exact source `5def887cb1c240ca309c4c5ff7bd6298af4784ee`, tree
`885af5298339e8562a22a78f8538cd1c1da4b6e1`, passed workflow `31869526221`
and exact-head review, was pinned through control-plane PR #193, and was
deterministically installed with receipt SHA-256
`15b72e71a32863c946a9e6ccf87343bd995d53fe472b2654215ab988696cba9e`.

One corrected controlled start skipped terminal Human Gate admission 19 and
the trusted daemon merged existing sequences 20-22 strictly FIFO as PR #25 at
`eaf457d70f4cb94cc81a3a4cbd3a5bdfd821cf04`, PR #26 at
`a433d0b8f06293b39c07db1ce677ae4f049fede5`, and PR #27 at
`80e98e06d1f4717589dbefde974c37da46780d28`. Remote main contains all three
expected qualification files. Controlled restart preserved those identities,
47 model actions, 33 reviews, 22 admissions and zero active or duplicate model
activity. Card 27/PR #24 remains unchanged at terminal Human Gate. The bundle
is stopped; exact proof is in
[admission-wake/Human-Gate terminal evidence](DCP_LAB_ADMISSION_WAKE_HUMAN_GATE_UI_V1_TERMINAL_EVIDENCE.md).

## First exact real repo-only target v1 installation

Managed-source PR #57 exact merge
`f94b0603916c410419654ca4752ffa9084116ff8`, tree
`11a9856ea2504ef923221a97064a59a762a99ed8`, adds only the statically
allowlisted public `wb-price-extension` / `repo-only` policy tuple and I21
empty-subsection renderer correction. It passed required source/package
workflow `31886665288` and exact-head review. Pin PR #199 and the proven
read-only provider-query compatibility PR #200 merged normally.

Repeated stopped deterministic install/preflight passed with receipt SHA-256
`06ebdbf6c418ed3805ff85737a638cf9e78cf5f70a1b035211016c0b117d26fc`.
SQLite remained byte-identical, integrity `ok`, with 58 terminal and zero
active model actions; the new target has zero tasks or sessions. Existing
synthetic history and Human Gate PR #24 are unchanged, no live model call or
target task ran, and the bundle is stopped. Exact proof is in
[real target v1 install evidence](DCP_REAL_TARGET_V1_INSTALL_EVIDENCE.md).

## Runtime provider identity terminal qualification

Managed-source PR #58 replaces only the daemon runtime's unsupported
`gh repo view --json databaseId` projection with typed read-only REST metadata.
Exact head `636aa9311a180bba41f142533251c3c72fc73bb9` passed semantic/security review
`PRR_kwDOTydt6M8AAAABJrDKDA` and required source/package workflow
`31891814079`, then merged normally at exact source
`9162d4c0eca9efd2a3d9fe1ad09d640c40738c47`, tree
`ec8e4c6d613e5e503a2582955b40bb8f104f76ce`.

The correction preserves exact public full-name, `main`, numeric repository-id
`1335072844` and owner-id `237411244` equality; missing, null, malformed,
wrong-type or command-error results fail closed. It adds no target, migration,
service, storage, retry, credential or model authority. Pin/install PR #203
merged at `74e49338e76efce8fdaeeae80ce34b9352f9d631`; stopped deterministic
install/preflight and the receipt-bound exact production-function live-provider
harness passed with receipt SHA-256
`5cb06d6edaeb70080999f531da76109936732a57bee8262d9c0cf0af1b7ce295`.
SQLite stayed byte-identical, target activity remains zero, PR #24 is unchanged
and DCP is stopped. Exact proof is in
[runtime provider identity terminal evidence](DCP_REAL_TARGET_PROVIDER_IDENTITY_V1_TERMINAL_EVIDENCE.md).

## Exact first-submit recovery source pin

Managed-source PR #59 preserves immutable fields in hidden submit JSON, routes
the exact repo-only reviewer through the existing global policy action gate,
uses typed REST metadata in the terminal merger, and adds exact forward-only
migration 0076. Exact head
`fe75d421a161820e02a4a1bd22f2c1434cf5d887` passed semantic/security review
`PRR_kwDOTydt6M8AAAABJrRQwQ` and required source/package workflow
`31897733520`, then merged normally at exact source
`2430e6268281a750f843057acf3084193efacdc5`, tree
`3c349323207913574d22a7905441cb9628d7faf0`.

The migration is bound to existing `price-arch-v1`, action sequence 59, PR #1,
exact head/check and approved ReviewRun. It may append only reviewer accounting
sequence 60 for the already-consumed 20,512-token call and move the same task to
passive `admission_waiting`; it launches no submit, model, push, admission,
lease or merge. This source remains build/test input until the separate
pin/install guard and deterministic stopped install/preflight complete.

## Exact stopped-WAL preflight compatibility

Control-plane pin/install-guard PR #206 merged at
`b8906e69e23c67b784257fead296729e7e73a45d`. Its first deterministic stopped
install created backup `i12-20260815T173130Z` and installed exact source
`2430e626...` / tree `3c349323...` with receipt SHA-256
`420fc3bc9c83efcbd3b5a8288f4754e57b263847eb8a9b2d7d1937d428289c50`.
Stopped preflight failed before migration because the adapter's read-only SQLite
CLI open cannot recreate absent WAL/SHM sidecars after clean shutdown. The
reviewed compatibility contract permits only an immutable SELECT fallback
after exact stopped/process/port/sidecar proof; it changes no managed source or
runtime authority.

## Exact repo-only startup quarantine boundary

The stopped-SQLite compatibility merged, and final stopped install/preflight
passed with backup `i12-20260815T175234Z` and receipt `6f8c8d846a263eab8409f9370af0ddf36d409574dd43ae769690cfcf14077698`.
The first controlled start applied migration 0076 once and recovered exact
revision 5/actions 59-60, then failed before runtime construction because the
startup quarantine classifier remained synthetic-only. The reviewed correction
may add only the exact already-authorized repo-only tuple to the same fail-
closed restore fence; it adds no migration or model/admission/merge authority.
Managed-source PR #60 exact head
`fea7ef95ecf0844ac9059c78ccd1e65778d74928` passed review
`PRR_kwDOTydt6M8AAAABJrXpVQ` and required workflow `31900560949`, then merged
normally at source `f857fc652a529955a3bca4205c09961a1a80b811`, tree
`ce8d2a4af467faf7c816152d04ac8a423eeb1b3b`. It remains build/test input until
the separate pin/install guard and stopped deterministic install/preflight.
Final pin/install-guard PR #210 merged at
`7c8db9ee8ae4888b4fc5d0f424475a194b6be949`; deterministic stopped install
created backup `i12-20260815T182802Z` and receipt `2c38e353...`. The existing
admission controller and terminal merger then merged original PR #1 at
`62853496837f64522bb08ba56169f60f3b0f9a2c`. Controlled restart preserved the
sole worker/reviewer, actions 59-60, one ReviewRun/admission and zero active or
duplicate model activity. The exact bundle is stopped and preflight-ready; see
`DCP_REAL_TARGET_SUBMIT_RECOVERY_V1_TERMINAL_EVIDENCE.md`.

## Repo-only target forward source pin

The GitHub repository now has canonical full name
`orenvlad-ai/wb-browser-extension` with unchanged repository id `1335072844`,
owner id `237411244`, public `main`, `baseline` and branch protection. The old
URL redirects but is not a second provider repository. Managed-source PR #61
exact head `05530e0a45ac630dd87dc9e5a6c4712d3305b3d7` passed semantic/security
review `PRR_kwDOTydt6M8AAAABJskmTw` and source/package workflow `31934075873`,
then merged normally at source `d152afae2bcbcc3d2b1874adf2e6855bebcf00fb`,
tree `aa7a6f486cf89ec299763ebcde7a5fc35a59214f`. Migration 0077 adds only the
current tuple and immutable forward mapping while leaving the exact completed
legacy row unchanged. It remains build/test input until the separate pin and
stopped deterministic install/preflight complete.

## `wb-core` Release Train handoff source pin

The governing authority is
`DCP_WB_CORE_RELEASE_TRAIN_HANDOFF_V1_CONTRACT.md`.

Managed-source PR #62 exact head
`816320a7a88496f4ebbbea3e295a0a9bcf14015d` passed semantic/security review
`PRR_kwDOTydt6M8AAAABJxSgIw` and source/package workflow `32019792026`, then
merged normally at source `99e8243ac66bfdd7e77538368403d0a3b5964c21`, tree
`81b391c80eef98c5723340a1da8e42a3da1bbaec`. The change is bounded to the exact
typed `wb-core` policy, compatibility lock, Release Train handoff/observation,
projection, migration and model-free tests. Pin/install-guard PR #219 merged at
`4fa942190385026d1e7f8e603940e6f625fc4e21`; stopped deterministic install
produced exact receipt
`97c4b6c000fa51c571586c39ed1d096adc7fdcdd5838d8c0ad4e15006a96a9d6`.
Schema 78, exact native project registration, zero WBC task/session/action rows
and the byte-preserving compatibility rejection passed. The source is now the
installed runtime authority. WBC PR #984 subsequently published the
repository-owned marker at exact main
`4735f74aedf1a1374dd4c8503799dd0761a61f22`; installed model-free preflight and
the direct gate now report `qualified`. Source, tree, receipt and database
digest remain unchanged, with zero WBC tasks/sessions and zero queued/active
model actions. Current app/daemon readback is running, ready and healthy; this
evidence pass does not attribute or change that state. No WBC submit, task or
model call was authorized or performed, and the first repo-only canary still
requires separate owner authorization.

That first authorized canary submit later failed before reservation because
the dev-control-plane adapter had registered a 912-byte `agentRules` value
while this exact installed source requires 1149 bytes. Managed source and the
artifact remain correct and unchanged. The integration now locks the source
expectation by byte count and SHA-256 and checks adapter output plus the actual
native project before reporting readiness. PR #222 and the one reviewed
model-free project-config reconciliation corrected the stale registration.
There is no managed-source change, source pin, rebuild, install, WBC mutation,
retry or model call.

After PR #222 merged, the one model-free reconciliation persisted the correct
source policy plus native empty default projections. A focused regression
proved the first readiness comparison was stricter than the daemon only at
those empty storage fields. The bounded follow-up accepts absence or the exact
empty native forms while preserving every policy and identity comparison.
No second reconciliation, source/artifact/runtime change, submit or model call
is authorized. PR #223 merged the exact native-default guard at
`b751c2195bc7aeb9882a2f5b2cd2feda870e5783`; final-main readiness is
`qualified` and technical status is `COMPLETE`, ready only for a separately
owner-authorized repo-only canary.

Evidence PR #224 merged that record at
`ca303bfebb0b5b8064351783f3d2e5e52177d09f`. A subsequent fresh WBC fetch
detected one new descendant main commit and correctly blocked stale-baseline
preflight. The existing governed read-only-target initializer fast-forwarded
only the canonical target to
`303ae44b6f7965faf02e62ff484631fc7148f585`; final preflight is `qualified`
with installed source/artifact, project config, SQLite digests and zero-state
unchanged.

The current managed-source authority is
`DCP_WB_CORE_CI_TRUTH_LIFECYCLE_UX_V1_CONTRACT.md`. PR #63 exact head
`b11657b24712bbf04b12cbde4f41b1c9d5530280` passed review
`PRR_kwDOTydt6M8AAAABJ0AXKw` and workflow `32055555244`, then merged at exact
source `93246658c34a7d5cdeb7bb42a7f3496308923608`, tree
`828c3c6b1b5a5700bde8495a435d40ee3609ec9d`. The source selects only the
target spec's exact `RequiredCheck` on the current head, proves complex and
simplified Release Train fixtures behave identically, exposes distinct model/
workflow activity facts, makes all policy UI surfaces and notifications
consume one projection, and adds one exact model-free recovery for the
existing canary incident. Pin PR #227 and deterministic install bound that
source at receipt `44a6a690...`; migration 0079 recovered only the same task
into one approved reviewer and admission. Release Train run `32057937600`
correctly emitted fresh-readmission evidence after concurrent WBC main advance.
Installed DCP stopped fail-closed at `release_state_drift`; a separate governed
DCP continuation is required before the unchanged canary may create a new head,
fresh baseline/review/admission and a new handoff. Exact terminal proof is in
`DCP_WB_CORE_CI_TRUTH_LIFECYCLE_UX_V1_TERMINAL_EVIDENCE.md`.

The completed managed-source qualification authority is the task-first native
lifecycle architecture/source pass in
`DCP_TASK_FIRST_NATIVE_LIFECYCLE_V1_CONTRACT.md`, layered on
`DCP_WB_CORE_END_TO_END_RELEASE_DEPLOY_V1_CONTRACT.md`. Source qualification
proved strict parsing/deduplication of immutable
versioned WBC readmission events; one durable conflict-free mechanical merge
generation on the same branch/PR; fresh required-check/reviewer/FIFO admission
per generated head; static direct-merge ineligibility; exact repo-only and
live-runtime terminal proof validation; dual-profile adapter/source/native
project parity; continuous model-versus-workflow UI truth; notification dedupe;
and restart at every fence. It additionally proved task-first terminality,
provider-neutral archived-shell eligibility, exact model-action/runtime
symmetry, exhaustive phase by shell by action restart coverage, and immutable
schema-82 migration-0083 recovery on disposable copies. Authority PR #239
merged at `5075235780...`; managed-source PR #71 exact head `9055dd67f9...`
passed review `PRR_kwDOTydt6M8AAAABJ-fBzw`, workflow `32171208324`, and zero
threads before ordinary merge at source `84dbee2a701...`, tree
`9374ece6ef...`. The live database stayed byte-identical, migration 0083 is
inactive, and source is ready only for a separately owner-authorized reviewed
pin/install Pass 2. Exact source-complete proof is in
`DCP_TASK_FIRST_NATIVE_LIFECYCLE_V1_SOURCE_COMPLETE_EVIDENCE.md`.
WBC PR #990 published the exact v2 seam at
Actions-owned main `63dad723d40b0a2e22e1944ccd5700cf4c1f28c3`.
Managed-source PR #64 passed exact-head review
`PRR_kwDOTydt6M8AAAABJ57SmQ`, workflow `32123765975` and zero threads, then
merged and was installed at source
`6c48702416ec8ddb657ef4d3fe64ceb8e818ed65`, tree
`86c48465f303fa398975052bdf32a9424a3a4e59`, receipt `aa06cc42...`.
The claimed generation exposed only the exact archived-shell candidate defect.
Corrective managed-source PR #65 exact head
`45ef29fb27f74d464f324613d6ad57a54fa73d31` passed review
`PRR_kwDOTydt6M8AAAABJ6SM5g`, workflow `32127715980` and zero threads, then
merged at source `13e8ce2968c516ce8f9b64b4e096010d9161445b`, tree
`2462a0ee67a033d6208a8b3d0972bb8426038b85`. Pin PR #231 and receipt
`a7691706...` installed it; the one generation pushed PR #987 head
`26044c696...` and exact-head baseline run `32129475530` succeeded. The stock
SCM observer skipped the archived exact session before persisting the new-head
required check. Corrective managed-source PR #66 exact head
`2ce5cf3653ad3af8e82740e748c71f65db1a3f1c` passed review
`PRR_kwDOTydt6M8AAAABJ6ujgw`, workflow `32132561114` and zero threads, then
merged at source `8df57dafff8e5a57cf27ff65e67cd695bf6a5ba4`, tree
`92cb1995aa014a9dafc35c10fc3468f9725d1fa4`. Pin PR #232 and receipt
`50179098...` installed it with 72 actions and zero active. The existing
generation's legacy v1 marker evidence then exposed the strict-v2 observer
mismatch. Corrective PR #67 exact head
`a6830158b60aa27bc745371805b7d35f81cabd20` passed review
`PRR_kwDOTydt6M8AAAABJ7HIAw`, workflow `32136552907` and zero threads, then
merged at source `22d8a6a47401144b3fe48de064321e4b1d7fa0e3`, tree
`38ad8eabeecce8131261e97a344f55ecb11725d2`. Pin PR #233 and receipt
`e3bda8d3...` installed it; exact baseline persistence and restart preserved
72/0 but the approved predecessor head triggered the generic preserved-review
rejection. Corrective PR #68 exact head
`0b3393277c519b1bd9884674d88112e1394bbc5d` passed corrected review
`PRR_kwDOTydt6M8AAAABJ7h_TA`, workflow `32140877774` and zero threads, then
merged at source `df8509a03562cf4f1b16ffe733bb874c4a768459`, tree
`946f3c683339ff346ed718acfcd399b858082181`. Pin PR #234 and receipt
`22c6d8d7...` installed it; exact reviewer sequence 73 approved head
`26044c696...` before admission recorded `admission_identity_drift` for the
same reviewed generation. Corrective PR #69 exact head
`4295395134d960de21f792015795d7155534d1a7` passed review
`PRR_kwDOTydt6M8AAAABJ8A6TQ`, workflow `32145665410` and zero threads, then
merged at source `2accc566f19a2ab0d1f99e70ba9e4cfa01fd0925`, tree
`ef2b5378f3e3427229a8ee3627192a0bb1c0c9e8`. Pin PR #235 and receipt
`f4969ffd...` installed it; the exact enqueue bound admission 32 and advanced
generation 1 to `admitted` before the waiting selector recorded
`waiting_identity_drift`. Corrective PR #70 exact head
`9cd8f0e33c07ec33c6789481c1574368f9d940a0` passed review
`PRR_kwDOTydt6M8AAAABJ8sMcQ`, workflow `32152293511` and zero threads, then
merged at source `3fdc3976edc6bad591bca4cf4e254b479a905fb3`, tree
`5c945ae8c4ce0101463d1ddbdff54bd75d619de0`. The lock selects only its exact
same-admission binding across the reviewed-to-admitted transition and the
zero-new-row migration-0082 recovery; general terminated sessions remain
excluded. Corrective pin PR #237 installed exact receipt `8b4ba7f8...`; startup
then proved a contradictory native-shell lifecycle predicate between policy
reconciliation and terminal admission. The app is stopped and continuation is
technical `BLOCKED` pending a shared typed lifecycle redesign/test.
