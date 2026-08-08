# Development Control Plane

DCP I8 is a bounded local laboratory built from pinned Agent Orchestrator
`v0.12.1`. It preserves the native Electron UI, Go daemon, project/session
model, isolated worktrees and Codex adapter, but packages them under a canonical
DCP identity. This is not a production control plane and it has no real target,
reviewer, arbiter, queue, retry loop, hosted service or second registry.

I9 separately records the future [DCP v1 target architecture](docs/TARGET_ARCHITECTURE_V1.md).
It is design-only and activates none of those mechanisms. This README and the
current operating contract continue to describe I8 until a later approved
implementation changes them.

## Canonical local application

Requirements are macOS on Apple silicon, Go 1.25.7+, Node 20.19+/npm 10+, Git,
`tmux`, and an authenticated Codex CLI supporting the isolation flags verified
by preflight.

Use the exact lab root:

```sh
export DCP_AO_LAB_ROOT="$HOME/Library/Application Support/DCP Orchestrator"
```

An executor prepares, qualifies and installs with:

```sh
./bin/dcp-ao prepare
./bin/dcp-ao build
./bin/dcp-ao install
./bin/dcp-ao preflight
```

The result is the user-owned native arm64 app at
`~/Applications/DCP Orchestrator.app`, bundle id
`pro.devcontrol.dcp-orchestrator`. The app owns its embedded
`dcp-orchestratord`; managed source/dev is only a build/test input. Do not use
`ao start`, `npm run dev`, common-name app lookup or GUI automation. Never
inspect or import `/Applications/Agent Orchestrator.app` or `~/.ao`.

Durable state/data, managed source, builds, evidence and the remote-free target
stay below the lab root. Cache uses
`~/Library/Caches/pro.devcontrol.dcp-orchestrator`; logs use
`~/Library/Logs/DCP Orchestrator`.

Useful executor diagnostics:

```sh
./bin/dcp-ao status
./bin/dcp-ao doctor
./bin/dcp-ao paths
```

Closing the macOS window leaves the app, daemon and work alive. Explicit Quit
is separate and warns before losing supervision of active or unproven work.

## Submit one synthetic task

Create the disposable target once, then use the only normal curator entry:

```sh
./bin/dcp-ao init-target
./bin/dcp-ao-submit \
  --target dcp-lab \
  --prompt 'Создай только dcp-ao-i8-marker.txt со строкой DCP AO I8 canary и LF; больше ничего не меняй, не делай commit, push или PR.'
```

The gateway holds one singleton through exact app/daemon proof and one native
spawn. It reuses a ready exact app or opens its absolute bundle path from a
completely stopped contour. It never owns, kills, stops, restarts, replaces or
recovers the runtime. Stale, foreign, duplicate, unhealthy or ambiguous facts
fail closed and remain intact. Simultaneous submits serialize into distinct
sessions under one app and daemon.

The worker runs through
`codex exec --ignore-user-config --ephemeral --strict-config` with hooks, apps,
plugins and multi-agent disabled. Standard authentication is retained without
credential copying; Codex SQLite state is lab-local. AO's existing supervisor
reports Working while live, Idle on zero exit and Exited on failure. Only the
one-shot supervisor wrapper receives the exact daemon connection for its hooks;
the retained shell and Codex child do not inherit it.

Manual orchestrator-spawn controls and hints are hidden in the DCP UI. Native
backend/CLI/API/programmatic orchestrator and additional-agent mechanisms are
preserved for a future separately authorized stage.

## Model-free audit

```sh
./scripts/i8_audit.sh
```

CI checks pin/patch provenance, packaged identity and release-gate source facts,
shell syntax, target validation, single-spawn behavior and cold/warm/concurrent
gateway semantics. Native package and live Codex qualification remain explicit
local executor evidence.

Authoritative scope:

- [Project brief](docs/PROJECT_BRIEF.md)
- [Roadmap](docs/ROADMAP.md)
- [Decisions](docs/DECISIONS.md)
- [Current operating contract](docs/CURRENT_OPERATING_CONTRACT.md)
- [DCP v1 target architecture](docs/TARGET_ARCHITECTURE_V1.md)
- [Upstream qualification](docs/UPSTREAM_QUALIFICATION.md)

The retired I2 experiment and v1/v2 epoch remain Git history. Technical
completion is not owner acceptance; only the owner may write the acceptance
phrase reserved in root `AGENTS.md`.
