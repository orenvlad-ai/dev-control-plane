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
