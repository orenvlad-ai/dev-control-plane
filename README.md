# Development Control Plane

The active DCP laboratory foundation is the native
[Agent Orchestrator](https://github.com/Untrivial-ai/agent-orchestrator)
application: its Electron UI, Go daemon, project/session registry, isolated Git
worktrees and native Codex adapter. DCP keeps only a pinned source-management
boundary, an exact-contour gateway, and a small curator-facing adapter.

This is local laboratory infrastructure, not production. It does not connect
to real target repositories, `wb-core`, `devcontrol.pro` or hosted DCP systems,
and it adds no DCP queue, scheduler, reviewer, retry loop or second registry.

## Prerequisites

- macOS on Apple silicon;
- Go 1.25.7 or newer;
- Node.js 20.19 or newer with npm 10 or newer;
- Git and `tmux`;
- an installed and authenticated Codex CLI with the worker-isolation flags
  checked by `bin/dcp-ao preflight`.

Set one absolute lab root outside Git. All upstream source, dependencies,
Electron data, daemon state, worktrees, logs and evidence remain below it:

```sh
export DCP_AO_LAB_ROOT="$HOME/Library/Application Support/DCP AO I3 Lab"
```

## Prepare and build the pinned source

```sh
./bin/dcp-ao prepare
./bin/dcp-ao build
./bin/dcp-ao preflight
```

`prepare` fetches only official release `v0.12.1`, verifies commit/tree/LICENSE
and applies the exact reviewed patch queue. Normal UI/daemon lifecycle is not a
separate operator step: the submit gateway reuses a healthy canonical source
UI or starts it only from a fully stopped/known-safe stale contour. It preserves
the Agent Orchestrator product/UI and supervises the upstream Go daemon. The
gateway explicitly disables AO telemetry and gives Electron, daemon and SQLite
separate lab paths. Source/dev mode does not start the packaged auto-updater.

Do not use `ao start`: upstream `v0.12.1` implements it as an installed desktop
bootstrapper. DCP uses only `bin/dcp-ao` and the source-built CLI.
`preflight` fails if the installed `/Applications/Agent Orchestrator.app` path
exists or any source/runtime/worker path is ambiguous. Do not launch a separate
headless daemon: DCP requires one source UI/app-owned daemon identity.

Useful commands:

```sh
./bin/dcp-ao status
./bin/dcp-ao doctor
./bin/dcp-ao paths
```

## Submit one synthetic task from a curator task

Create the disposable allowlisted repository once, then submit one short prompt
through the only normal DCP Gateway entry:

```sh
./bin/dcp-ao init-target
./bin/dcp-ao-submit \
  --target dcp-lab \
  --prompt 'Создай только dcp-ao-i7-marker.txt с UTF-8 строкой DCP AO I7 canary и завершающим LF; не изменяй другие файлы, не делай commit, push или PR.'
```

The gateway holds one singleton through exact UI/daemon proof and the complete
submit. It never restarts a healthy contour or active worker, performs at most
one known-safe stale run-file recovery, and fails closed without kill for every
foreign or ambiguous state. The adapter validates a clean remote-free
repository beneath the lab root, registers it as a native AO project when
needed, applies native AO project configuration, and invokes exactly one
`ao spawn` with the Codex harness. It has no database, registry, background
process or status model of its own.
The patched adapter uses
`codex exec --ignore-user-config --ephemeral --strict-config`; hooks, apps,
plugins and multi-agent tools are disabled per invocation, so user MCP
configuration is not loaded while the existing standard Codex login remains
available. Codex SQLite worker state is rooted below the lab and no credential
is copied. AO's existing process supervisor reports the running one-shot worker
as Working, exit zero as ordinary Idle, and any unsuccessful machine outcome as
red Exited.

Only manual orchestrator-spawn affordances and related hints are hidden in the
DCP Lab UI. Existing orchestrators, automatic/programmatic orchestration,
backend/CLI/API endpoints and additional worker agents remain upstream
capabilities; I7 adds no reviewer or arbiter.

## Validate the repository-owned boundary

```sh
./scripts/i3_audit.sh
```

The audit is model-free and network-free. It checks provenance and patch
digests, retired I2 absence, shell syntax, adapter validation and the one-spawn
integration fixture. Real native UI and Codex canaries are explicit local
operator evidence and are never run by CI.

The I2 loopback slice was accepted by the owner but is now a retired experiment;
its active code is absent and remains recoverable through ordinary Git history.
Only the owner's exact phrase `Задача принята` records acceptance of a
laboratory stage.

Authoritative scope:

- [Project brief](docs/PROJECT_BRIEF.md)
- [Roadmap](docs/ROADMAP.md)
- [Decisions](docs/DECISIONS.md)
- [Current operating contract](docs/CURRENT_OPERATING_CONTRACT.md)
- [Upstream qualification](docs/UPSTREAM_QUALIFICATION.md)

The v1/v2 epoch remains historical evidence only at
[`archive/legacy-v1-v2-20260807`](https://github.com/orenvlad-ai/dev-control-plane/releases/tag/archive/legacy-v1-v2-20260807).
