# Current operating contract

operating_contract_revision: 2026-08-08.8

This is the compact operational start for DCP work. Architecture and scope
remain authoritative in [Project brief](PROJECT_BRIEF.md),
[Roadmap](ROADMAP.md), and [Decisions](DECISIONS.md). Root `AGENTS.md` plus this
contract define the starting flow when operational instructions conflict.

## Bootstrap and authority

Codex automatically receives root `AGENTS.md` in the repository. A new curator
reads local `DCP_curators/AGENTS.md`, root `AGENTS.md`, this contract, then only
the relevant authoritative scope documents. Do not reconstruct current state
from chat history.

One primary curator discusses and dispatches one direct executor in a separate
worktree. There is no nested curator or parallel DCP change. The executor starts
from exact current `origin/main`, runs relevant tests and semantic/security
self-review, and opens one ready PR. Ordinary protected GitHub review, green CI,
safe merge, and a clean canonical fast-forward apply. Technical completion is
not owner acceptance; only the owner may write `Задача принята`.

For DCP Lab, the curator has one normal mechanical entry only:
`bin/dcp-ao-submit`. Direct app launch, daemon, stop, restart, build, install, or
source/dev commands are not curator dispatch steps.

## Exact packaged laboratory contour

The current implemented laboratory stage is I8. Its foundation is official
Agent Orchestrator `v0.12.1`, commit
`1df40e93772c2c48e916870d9c3ddf8f29a69f84`, managed from the repository pin
and exact patch queue. Managed source is build/test input only; it is never the
canonical runtime and `npm run dev` must not be used to keep DCP Lab alive.

The sole runtime is the native arm64 application at the exact path:

`/Users/ovlmacbook/Applications/DCP Orchestrator.app`

Its bundle id is `pro.devcontrol.dcp-orchestrator`, main executable is
`dcp-orchestrator`, embedded daemon/CLI is `dcp-orchestratord`, health service is
`dcp-orchestrator-daemon`, and the fixed loopback port is `43231`. The app owns
the daemon lifecycle through the native supervisor link. It stores durable
state below the explicitly supplied canonical `DCP_AO_LAB_ROOT`:

`/Users/ovlmacbook/Library/Application Support/DCP Orchestrator`

`state/` contains the run-file, gateway/install facts and app settings; `data/`
contains SQLite, worktrees, Electron user data and lab-local Codex state;
managed source, builds, evidence and the remote-free `targets/dcp-lab` also stay
under that root. Electron caches use
`~/Library/Caches/pro.devcontrol.dcp-orchestrator`; logs use
`~/Library/Logs/DCP Orchestrator`. The installed
`/Applications/Agent Orchestrator.app`, `~/.ao`, real repositories, remotes,
`wb-core`, production and hosted systems are never inspected or used.

Executor-only installation is deterministic:

```text
export DCP_AO_LAB_ROOT="$HOME/Library/Application Support/DCP Orchestrator"
bin/dcp-ao prepare
bin/dcp-ao build
bin/dcp-ao install
bin/dcp-ao preflight
```

`build` verifies the pin/patch and model-free Go/Vitest/type gates, then packages
an arm64 `.app`. `install` ad-hoc signs and places the exact verified bundle at
the canonical path, retaining any prior verified DCP bundle as a lab-root
backup. `preflight` verifies the source patch, Info.plist identity, arm64 main
and daemon executables, signature, license/notice, absence of updater feed and
packaged telemetry/updater modules, exact install receipt and Codex isolation.
It never probes the upstream installed app or its data.

## Gateway and lifecycle

`bin/dcp-ao-submit --target dcp-lab --prompt '<one line>'` holds a lab-local
singleton from contour proof through the one native `ao spawn`. The prompt is
non-empty, one line and at most 512 UTF-8 bytes; the target is the exact
remote-free disposable repository.

When the exact app is off, the gateway requires stopped status, no run-file and
an unused fixed port, opens the absolute bundle path, then waits up to 60 seconds
for one exact app PID and its ready daemon. When the app is already running, it
is reused without restart or kill. The gateway matches the run-file's daemon
PID/port/owner, contour id, app PID, per-launch app instance id, bundle id,
bundle path, browser token/socket, embedded daemon command and service name.
The daemon itself produces `dcp-orchestrator-daemon` in both its authenticated
status response and run-file; the gateway requires the two independent facts
to match rather than supplying or inferring the service identity.
Two simultaneous submissions serialize into one app/daemon and two separate
worker sessions with no duplicate spawn.

Any stale run-file, foreign/duplicate app, foreign daemon, occupied port,
identity mismatch, unhealthy state or ambiguous state fails closed without
delete, kill, stop, restart or replacement. The gateway never owns the app or
daemon. Closing the last window on macOS leaves the app, daemon and work alive;
the Dock/tray can reopen the window. Explicit Quit is separate and warns or
refuses silent exit while an active worker exists or its state cannot be proven.

The renderer hides manual `Spawn Orchestrator` controls and related hints.
Backend/CLI/API/programmatic orchestrator and additional-agent mechanisms remain
available for a future separately authorized reviewer/arbiter stage.

## Worker and release gates

The Codex worker uses standard authentication but runs through
`codex exec --ignore-user-config --ephemeral --strict-config`, with hooks, apps,
plugins and multi-agent disabled. It does not load user MCP/plugin/app/hook
configuration; `CODEX_SQLITE_HOME` is DCP-local. AO's existing supervisor maps
running to Working, exit zero to Idle, and every failed launch/non-zero/signal
to Exited. The packaged one-shot wrapper alone receives exact `AO_DATA_DIR` and
`AO_RUN_FILE` values for its start/exit hooks. Those variables are stripped
from the retained tmux shell and from the Codex child, so lifecycle reporting
does not weaken worker isolation.

The package has no updater initialization, feed metadata, maker or publisher;
updater UI/IPC is inert and updater dependencies are pruned. Renderer and daemon
telemetry cannot be enabled by environment, no telemetry control routes are
mounted, and no analytics key/host/install identity, local telemetry reservoir,
crash upload or crash reporter is initialized or packaged. Source/dev remains
only a model-free build/test instrument.

I8 adds no reviewer, arbiter, queue, retry/recovery policy, monitoring, real
target, `wb-core`, production, hosted API, notarization or distribution
installer. Its completed live qualification used only short remote-free marker
tasks and no automatic retry. The owner raised the cumulative ceiling to five
model calls: one preserved diagnostic stop-gate plus one successful cold, one
successful warm and two successful concurrent calls. The four qualified
sessions (`dcp-lab-2` through `dcp-lab-5`) are distinct and Idle under one
persistent app and daemon; minimal redacted evidence remains outside Git.

A dedicated DCP Git fork is not part of I8. It is the next separately
owner-approved architectural stage after I8 acceptance; until then the exact
release pin and repository-owned patch queue remain authoritative.

## Dispatch template

```text
Task: <one bounded DCP change>
Base: exact current origin/main; separate branch/worktree
Read: root AGENTS.md -> docs/CURRENT_OPERATING_CONTRACT.md -> relevant authoritative docs
Boundary: canonical DCP_AO_LAB_ROOT and exact DCP Orchestrator.app; never installed AO, ~/.ao, real repos, remotes, wb-core or production
Flow: one curator -> one direct executor; no nested curator or parallel DCP change
Entry: curator uses only bin/dcp-ao-submit
Proof: model-free gates, semantic/security review, one ready PR, green CI, safe merge, clean canonical fast-forward
Stop: fail closed on ambiguous identity/auth/isolation or unsafe cleanup; never synthesize owner acceptance
```
