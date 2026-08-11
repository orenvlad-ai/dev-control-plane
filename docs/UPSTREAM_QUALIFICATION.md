# I3 upstream qualification

This is the implementation-time record for **DCP · Штатный AO · И3**. Evidence
was gathered from fresh source checkouts and isolated runtime roots outside the
DCP repository on 2026-08-07.

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
startup-only model-free recovery. The current immutable source merge commit is
`b23b519cd532555c203863586032d157fc1c8c13`, tree
`a7ad1f64ee089beaeb2fc4b1f43f8778526997a6`.

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
