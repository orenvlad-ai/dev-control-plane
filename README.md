# Development Control Plane

This repository now contains the bounded **DCP Orchestrator** I2 laboratory
slice plus the authoritative plans for later DCP work. It is a local lab, not
production and not a complete orchestrator.

The lab provides one real flow on this Mac:

> fixed synthetic prompt → one `dcp-lab-canary-001` card → one isolated Codex
> worker → exact marker evidence → verified cleanup → truthful terminal result

It does not connect to `wb-core`, production, `devcontrol.pro`, hosted DCP
services, real target repositories or installed Agent Orchestrator state. It
has no queue, parallel dispatch, retries, reviewer loop, arbiter or owner
acceptance automation.

## Open the local interface

Prerequisites are macOS, Python 3.11 or newer, Git, and an existing authenticated
`codex` CLI. From a fresh checkout after merge:

```sh
./bin/dcp-orchestrator
```

The command starts a token-protected loopback server, opens the browser and
prints its local URL. The canary prompt is prefilled with the only accepted
synthetic value. Press **Запустить один canary** once and wait for the one card
to reach a terminal state. Stop the local server with `Ctrl-C`.

Successful terminal state is `succeeded` only after exact marker verification
and cleanup. Other truthful terminal states are `failed`, `cleanup_failed` and
`safety_violation`, each with a machine-readable reason. None means
`Задача принята`.

Runtime state and retained redacted evidence live outside Git:

- `~/Library/Application Support/DCP Orchestrator/state/`
- `~/Library/Application Support/DCP Orchestrator/data/`
- `~/Library/Caches/pro.devcontrol.dcp-orchestrator/`
- `~/Library/Logs/DCP Orchestrator/`

The clean disposable baseline repository is retained under the DCP data root;
attempt worktrees, branches, marker, lock and transient state must disappear
before success. The app never searches for or migrates `~/.ao`.

## Build and validate

The source launcher is the supported owner path. A deterministic dependency-free
zipapp can also be built outside Git:

```sh
python3 scripts/build_artifact.py
```

By default it is written to
`~/Library/Caches/pro.devcontrol.dcp-orchestrator/build/`. Validate the complete
model-free surface with:

```sh
python3 -m unittest discover -s tests -v
python3 scripts/safety_audit.py
```

The audit covers source, dependencies, deterministic artifact contents,
license/provenance, forbidden updater/telemetry/crash surfaces, external
endpoints and upstream namespaces. CI runs the same checks without a model or
network canary. A real canary is an explicit local operator action.

## Governance and provenance

The upstream qualification is recorded in
[`docs/UPSTREAM_QUALIFICATION.md`](docs/UPSTREAM_QUALIFICATION.md). Agent
Orchestrator revision `f17013b53a1752e86c66e87b45aaa4a463fdff62` is pinned as
architectural provenance; its broad Electron/Go runtime and dependencies are
not vendored or packaged. Apache-2.0 license and attribution are preserved in
`third_party/agent-orchestrator/` and `NOTICE`.

Repository changes retain the one-curator/one-executor flow: a ready PR, green
required CI and ordinary protected merge, followed by a technical handoff.
Only the owner records acceptance with the exact phrase `Задача принята`.

Authoritative scope:

- [`docs/PROJECT_BRIEF.md`](docs/PROJECT_BRIEF.md)
- [`docs/ROADMAP.md`](docs/ROADMAP.md)
- [`docs/DECISIONS.md`](docs/DECISIONS.md)

The retired v1/v2 epoch remains historical evidence only at
[`archive/legacy-v1-v2-20260807`](https://github.com/orenvlad-ai/dev-control-plane/releases/tag/archive/legacy-v1-v2-20260807).
