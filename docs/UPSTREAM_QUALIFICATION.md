# I2 upstream and safety qualification

This is the bounded implementation-time qualification record for **DCP ·
Интерфейс · И2**. It describes evidence gathered from a disposable clone
outside the DCP repository. It does not make upstream runtime code reachable or
packaged.

## Pinned provenance

- Official remote: `https://github.com/Untrivial-ai/agent-orchestrator.git`.
- Required and selected revision:
  `f17013b53a1752e86c66e87b45aaa4a463fdff62`; no replacement revision was
  needed.
- Git tree: `6402905847ad8f31531b70d0d90f47324c0469b6`; parent:
  `53ccd9340ca981191c92c4033bbe3d7d625124be`; subject:
  `fix(frontend): remove extra terminal edge spacing (#3609)`.
- A fresh clone resolved the exact commit/tree. GitHub's commit API reported
  `verified=true`, `reason=valid`, verified at `2026-08-07T07:17:54Z`.
- The checkout contains 2,072 tracked paths and 75,794,987 tracked bytes
  (approximately 240 MB with Git metadata and checkout).

## License, notices and dependencies

The root upstream `LICENSE` is Apache-2.0, Copyright 2026 Untrivial. Its
SHA-256 is
`1a2219722b7ef58364065e9073a2cb2831891eb147a785742a31431c9cddad1d`.
There is no tracked `NOTICE` path at the pinned revision. DCP preserves the
license byte-for-byte, supplies its own attribution notice and states the
modification/package boundary in
`third_party/agent-orchestrator/PROVENANCE.md`.

The upstream `frontend/package.json` declares `license: MIT`, which does not
match the root Apache-2.0 license file. I2 does not redistribute that frontend
or any other upstream source/dependency, so the conflicting manifest metadata
does not enter the laboratory package. Any later source-level fork or
distribution must resolve this ambiguity with upstream and repeat the license
and dependency-notice review; root-license observation alone is not sufficient
for that future decision.

The upstream dependency/package surface is too broad for the approved canary:

| Manifest | Locked package entries | Entries classed production by npm lock |
| --- | ---: | ---: |
| root `package-lock.json` | 34 | 0 |
| `frontend/package-lock.json` | 1,223 | 316 |
| `frontend/acp-runtime/package-lock.json` | 112 | 111 |
| landing site lock | 575 | 491 |
| documentation site lock | 437 | 393 |
| mobile lock | 829 | 761 |
| scripts lock | 186 | 185 |

The backend manifest also contains 36 lines across its direct `require` block,
including PTY, WebSocket, HTTP routing, SQLite, Git/worktree and agent-protocol
libraries. DCP I2 incorporates none of those packages. Its packaged Python
runtime dependency list is empty; `python3`, `git` and the owner's existing
`codex` CLI are explicit host executables rather than bundled dependencies.

## Reachable upstream surfaces found

The qualification did not assume that a default-off preference was removal.
It found concrete reachable/package wiring that must not enter DCP I2:

- Electron Forge sets product `Agent Orchestrator`, executable
  `agent-orchestrator` and bundle ID `dev.agent-orchestrator.desktop`; it ships
  a daemon, ACP runtime and generated `app-update.yml` as extra resources.
- `electron-updater` is a frontend production dependency. `main.ts` calls
  `startAutoUpdates`; updater code configures channels, periodic checks,
  download and quit/install, with GitHub release feeds and an
  `agent-orchestrator-updater` cache identity.
- The renderer depends on `posthog-js`. A baked PostHog project key and
  `https://us.i.posthog.com` host are passed by the Electron supervisor to the
  daemon for packaged runs. The daemon supports local SQLite telemetry and a
  PostHog exporter.
- The separate landing subtree depends on PostHog and Sentry packages and
  contains server/edge Sentry initialization. Upstream docs do not prove the
  absence of other crash paths, so DCP treats all inherited crash-reporting
  code and dependencies as denied.
- Upstream runtime state is deliberately reparented to `~/.ao`, including
  Electron `userData`/crash-dump derivations, data, run files, logs and import
  scanning. Its IPC includes loopback HTTP plus `supervise.sock` or
  `ao-supervise*` named pipes. It can discover/import projects and state.
- The reviewed tree also contains broad agent/reviewer/SCM/tracker/browser,
  GitHub release/API, mobile/proxy, remote access, website and notification
  paths. These are not needed for the fixed canary.

Representative external trust destinations in the upstream tree include
GitHub API/releases, PostHog hosts, Sentry, agent-provider endpoints, Slack,
Discord, Linear and website/CDN services. This inventory is not treated as a
complete network allowlist; its consequence is that no upstream runtime or
dependency enters the I2 package.

## DCP data flows and trust boundaries

The implemented flow is deliberately smaller:

1. A browser on this Mac loads static assets from a process-token-protected
   `127.0.0.1` server. CSP permits only the same origin. The fixed synthetic
   prompt is accepted only on an exact match, is not stored and is not passed
   through as free-form worker authority.
2. The sole DCP registry mutation authority records one card/task/attempt and
   starts one foreground child process. There is no queue, retry, reviewer,
   scheduler, watcher or remote DCP endpoint.
3. A disposable DCP-owned Git repository with no remotes is created beneath
   the DCP data root. Its canonical path, Git common directory and baseline
   commit are persisted as the allowlist before dispatch.
4. One `codex exec` process runs with an exact marker instruction, ephemeral
   session mode, ignored user configuration, workspace-write sandbox and a
   sanitized environment. It receives only the disposable worktree as `cwd`.
   Codex provider communication is the only external provider boundary; model
   tool network is denied by policy and instruction. DCP stores neither prompt
   nor transcript, only the executor identity, exit fact and output digest.
5. DCP verifies path/common-dir containment, exact marker bytes, byte count,
   SHA-256 and the complete scoped Git mutation set. It then removes the
   worktree, canary branch, lock and attempt state and verifies that the marker
   disappeared before publishing a successful terminal state.
6. Immutable redacted terminal/evidence JSON is retained in the DCP data
   namespace until deliberate owner removal; there is no automatic upload,
   expiry or deletion control. No GitHub, target repository, hosted or
   production fact is synthesized by this laboratory record.

The DCP server never reads, discovers, migrates or imports installed Agent
Orchestrator state. All allowlisting is positive: only the DCP-created
repository and pinned baseline are accepted. `dev-control-plane`, `wb-core`,
production, hosted systems and real target repositories are not allowlisted and
are recorded as negative evidence.

## Qualification decision and deterministic gates

Importing the 75 MB upstream tree and its broad desktop/backend dependency
surface would expand I2 beyond the approved canary and make updater,
telemetry/crash, network and namespace denials harder to prove. There is no
blocker to the requested outcome because the upstream revision is used as
pinned application-foundation provenance while the reachable I2 laboratory
slice is newly DCP-authored and dependency-free.

`scripts/safety_audit.py` deterministically enforces:

- pinned license digest and provenance/NOTICE results;
- an empty runtime dependency list and stdlib-only imports;
- absence of upstream updater clients/config, telemetry keys/hosts,
  crash-reporting endpoints and upstream namespace identities from source and
  executable artifact entries;
- only an explicit loopback application endpoint in runtime source;
- deterministic artifact bytes and an exact, minimal packaged surface with
  license/provenance/NOTICE included;
- runtime/network-denial and namespace/containment behavior covered by unit and
  integration tests.

Generated artifacts and all runtime evidence remain outside Git.
