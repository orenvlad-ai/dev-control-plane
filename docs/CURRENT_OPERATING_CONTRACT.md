# Current operating contract

operating_contract_revision: 2026-08-09.11

This is the compact operational start for DCP work. Architecture and scope
remain authoritative in [Project brief](PROJECT_BRIEF.md),
[Roadmap](ROADMAP.md), and [Decisions](DECISIONS.md). Root `AGENTS.md` plus this
contract define the starting flow when operational instructions conflict.

I9 records the separately approved future
[DCP v1 target architecture](TARGET_ARCHITECTURE_V1.md). That document is
design-only and is not part of the current operating flow except for the
explicitly implemented I11 foundation below. I11 activates only durable
model-free submission, read, events, restart recovery and display of a
synthetic SUBMITTED task. It does not activate execution, reviewer, arbiter,
admission/release, queue, lease, recovery policy, model call or real target.

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

For the existing I8 worker flow, the curator has one normal mechanical entry
only: `bin/dcp-ao-submit`. The I11 submit API is an internal/lab model-free
proof surface, not a second curator dispatch route or manual UI flow. Direct app
launch, daemon, stop, restart, build, install, or source/dev commands are not
curator dispatch steps.

## Exact packaged laboratory contour

The current implemented laboratory stage is I11. Its application source is the
private managed repository `orenvlad-ai/dcp-orchestrator` at exact commit
`417a844e7b85b6b14ae9a1855009d8bf139ee43d`, pinned by this repository. That
fork preserves official Agent Orchestrator `v0.12.1`, commit
`1df40e93772c2c48e916870d9c3ddf8f29a69f84`, and the qualified I8 behavior.
Managed source is build/test input only; it is never the canonical runtime and
`npm run dev` must not be used to keep DCP Lab alive.

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

`build` verifies the fork pin/provenance, DCP operational source gate,
generated API parity and model-free Go/Vitest/type gates, then packages an
arm64 `.app`. `install` ad-hoc signs and places the exact
verified bundle at the canonical path, retaining any prior verified DCP bundle
as a lab-root backup together with applicable state/data. `preflight` verifies the exact fork
source, Info.plist identity, arm64 main and daemon executables, signature,
license/notice/provenance, absence of updater feed and packaged
telemetry/updater/crash modules, exact fork-bound install receipt and Codex
isolation. It never probes the upstream installed app or its data.

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

## I11 durable model-free task foundation

The existing daemon and its existing `ao.db` accept, store, read and list
synthetic DCP tasks through typed loopback-only API endpoints. The only allowed
repository identity is the exact clean, single-commit, remote-free
`targets/dcp-lab`. Each task has a durable task id, idempotency key, immutable
canonical approved task/scope representation and digest, exact repository
identity, state SUBMITTED, revision and timestamps. A per-task append-only
event stream stores monotonic sequence, event id/type/source,
correlation/causation/idempotency, from/to state and versioned payload/evidence
digests. Task state and event append share one transaction, and stale revisions
are rejected.

The same idempotency key plus the same canonical payload returns the same task
id without a duplicate event. The same key with a different payload, malformed
input or an out-of-scope target fails before mutation. The existing board shows
one stable synthetic/lab card in Working with exact substate SUBMITTED. There
is no creation button, webhook, external service, polling loop or second
display-state authority.

On daemon/app restart, schema validation preserves prior I8 sessions and the
same task, revision and events. A waiting SUBMITTED task receives no timeout,
model, process, wake, checkpoint or action lease. No full transcript,
chain-of-thought, secret, credential or user Codex configuration is stored.

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

I11 adds no task execution, reviewer, arbiter, queue, retry/recovery policy,
monitoring, real target, `wb-core`, production, hosted API, notarization or
distribution installer. Historical I8 live qualification used only short
remote-free marker tasks and no automatic retry. The owner raised its
cumulative ceiling to five model calls: one preserved diagnostic stop-gate plus
one successful cold, one successful warm and two successful concurrent calls.
The four qualified sessions (`dcp-lab-2` through `dcp-lab-5`) are distinct and
Idle under one persistent app and daemon; minimal redacted evidence remains
outside Git. I11 itself uses zero model calls.

`dev-control-plane` remains architecture, integration and exact-pin authority,
while the private managed fork owns application code. The retired patch queue
is historical Git evidence only. I11 adds only the foundation explicitly
described above; I9 remains inactive target design for every future role,
transition, admission, release and recovery mechanism.

## Dispatch template

```text
Task: <one bounded DCP change>
Base: exact current origin/main; separate branch/worktree
Read: root AGENTS.md -> docs/CURRENT_OPERATING_CONTRACT.md -> relevant authoritative docs
Boundary: canonical DCP_AO_LAB_ROOT and exact DCP Orchestrator.app; never installed AO, ~/.ao, real repos, remotes, wb-core or production
Flow: one curator -> one direct executor; no nested curator or parallel DCP change
Entry: existing I8 worker entry remains only bin/dcp-ao-submit; I11 internal submit is model-free proof only
Proof: model-free gates with zero I11 model calls, semantic/security review, one ready PR, green CI, safe merge, clean canonical fast-forward
Stop: fail closed on ambiguous identity/auth/isolation or unsafe cleanup; never synthesize owner acceptance
```
