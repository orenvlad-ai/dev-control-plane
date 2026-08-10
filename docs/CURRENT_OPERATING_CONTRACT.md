# Current operating contract

operating_contract_revision: 2026-08-10.14

This is the compact operational start for DCP work. Architecture and scope
remain authoritative in [Project brief](PROJECT_BRIEF.md),
[Roadmap](ROADMAP.md), and [Decisions](DECISIONS.md). Root `AGENTS.md` plus this
contract define the starting flow when operational instructions conflict.

I9 records the separately approved future
[DCP v1 target architecture](TARGET_ARCHITECTURE_V1.md). That document is
design-only and is not part of the current operating flow except for the
explicit I11 foundation and bounded I12 reviewer slice below. I11 activates
only durable model-free submission, read, events, restart recovery and display
of a synthetic SUBMITTED task. I12 activates one stock, exact-head, read-only
reviewer after an eligible worker becomes safely idle, with model-free
single-flight and restart reconciliation. It does not activate task execution,
arbiter, admission/release, queue, action lease, general recovery policy,
auto-merge or a real execution target.

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
proof surface, not a second curator dispatch route or manual UI flow. I12 needs
no second chat impulse: the daemon reacts to persisted lifecycle/SCM facts and
the manual stock Run Review remains only a fallback through the same trigger.
Direct app launch, daemon, stop, restart, build, install, or source/dev commands
are executor operations, not curator dispatch steps.

## Exact packaged laboratory contour

The current implemented laboratory stage is I12. Its application source is the
private managed repository `orenvlad-ai/dcp-orchestrator` at exact commit
`f4970bd46f55ac75069c569e96b89597cd646b6c`, pinned by this repository. That
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
`/Applications/Agent Orchestrator.app`, `~/.ao`, real repositories other than
the explicitly authorized disposable review-lab canary, other remotes,
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
as a lab-root backup together with applicable state/data. A running canonical
old app is replaced only after its exact app/daemon identity is proven and
read-only SQLite/tmux checks prove no active worker or reviewer model action.
The submit lock closes the normal submission race; a foreign, duplicate,
unhealthy or ambiguous process and any active action fail closed. A persisted
running review with a missing pane or bare stable shell is preserved for the
new daemon's model-free startup reconciliation. Only a proven descendant of
that exact reviewer pane counts as active; unrelated system processes do not.
Installation leaves the new
bundle stopped so all post-install gates run before an authorized live launch.
`preflight` verifies the exact fork
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
available, but I12 authorizes only the bounded reviewer path below; arbiter and
additional automatic agent roles remain inactive.

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

## I12 bounded automatic reviewer

I12 reuses Agent Orchestrator's existing `Review`, `ReviewRun`, review engine,
one worker session/card, stable `review-<session>` terminal and existing
findings delivery. It adds no reviewer service, watcher, scheduler, heartbeat,
queue, second registry/database or new card. The Codex reviewer uses standard
authentication through `codex exec` with `approval_policy="never"` and
`--sandbox read-only`; web search is disabled, the unsupported exec-level
`--ask-for-approval` is not emitted, and dangerous bypass flags are rejected.
The model has no reviewer network tool, GitHub token, DCP daemon variables or
control-plane command channel. It returns only one Codex-native
`--output-schema`/`--output-last-message` JSON result containing exact
worker/reviewer/batch/run/PR/head identity, `approved` or
`changes_requested`, a bounded summary and bounded findings.

The shared trigger is serialized per worker and by the existing unique
review-run constraint. Its normal automatic path is eligible only for the exact
current head of an open non-draft PR after a non-terminated worker has safely
reached Idle with no active launch and no prior run for that exact PR/SHA. SCM
observation and successful supervised worker exit are events into that trigger;
there is no new polling loop. A completed/failed/cancelled run for the same
head is never automatically duplicated, while a new head may receive one new
review. Manual Run Review remains a fallback through the same engine.

One narrower continuation exists only for the preserved terminated worker whose
latest durable review failure proves the known reviewer working-directory
mismatch. The stock SCM observer keeps only that proven session visible long
enough to observe one replacement head; every other terminated session remains
excluded. On that exact head, the stock workspace adapter restores the saved
single-repository path and branch model-free; the engine then requires a clean
worktree at exactly that head before launching the same stable reviewer
terminal. Any resulting run or second matching failure consumes the
continuation, so it cannot become a retry loop or resurrect the worker.

The reviewer is itself one-shot supervised. Start failure, early CLI exit,
non-zero exit, signal, or zero exit without a submitted verdict durably fails
the still-running exact run and projects an actionable Needs You state rather
than perpetual Reviewing. On restart, an exact still-live supervisor is left
alone; ambiguous liveness is failed without retry; a proven stale run is failed
and receives at most one exact-head recovery launch without a model call during
reconciliation. Approval uses the stock Ready-to-Merge/SCM projection;
findings use stock delivery to the same worker identity and worktree.

After a successful model exit, the trusted one-shot supervisor reads exactly
one result artifact, independently validates its schema and every trusted
identity, and submits it through the existing session-scoped daemon endpoint.
One guarded SQLite statement completes the still-running `ReviewRun` only when
the stable reviewer terminal, batch, run, PR URL and exact target SHA match and
the same open non-draft PR row still owns that current head. Missing,
ambiguous, malformed, foreign, duplicate, late, closed/draft or stale-head
results fail closed without a verdict, retry or synthetic fallback. The
existing lifecycle path alone projects approval or delivers findings, so
SQLite remains the sole state authority and restart cannot launch a second
reviewer after a terminal verdict.

The private pane-local exact-binary `ao` alias remains only for compatibility
with other stock reviewer adapters. The Codex structured-result success path
does not prepend it to PATH and never depends on a command chosen by the model.
No global PATH entry, installed/retired AO discovery, `~/.ao`, reviewer network
permission, credential, migration, service, schema/database authority or
second persistence path is added.

The failed I2 run `b65be186-7326-4272-85aa-acfcd39bc938`, the failed I3 run
whose id begins `0aaf2da9`, and `orenvlad-ai/dcp-review-lab#1` and `#2` are
immutable audit evidence: they are not changed, reused, retried or merged. The
only remaining live I12 qualification is one new minimal change on one new
native card and fresh unmerged PR in the same disposable review-lab repository.
After every model-free source, API, type, package, install and identity gate,
the entire live budget is exactly one minimal worker model call for that card
and exactly one automatically launched internal reviewer model call. There is
no retry, second worker/reviewer call, manual Run Review, second chat impulse or
merge of any test PR. A saved approved verdict must project the new card to
Ready to Merge; app/daemon restart must restore that state without launching
another reviewer. Old sessions and all canaries remain immutable evidence.

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

I12 adds no task execution, arbiter, admission, Release Train, auto-merge,
general repair loop, monitoring service, real execution target, `wb-core`,
production, hosted API, Telegram, notarization or distribution installer.
Historical I8 live qualification used only short
remote-free marker tasks and no automatic retry. The owner raised its
cumulative ceiling to five model calls: one preserved diagnostic stop-gate plus
one successful cold, one successful warm and two successful concurrent calls.
The four qualified sessions (`dcp-lab-2` through `dcp-lab-5`) are distinct and
Idle under one persistent app and daemon; minimal redacted evidence remains
outside Git. I11 itself used zero model calls; this final I12 canary has a
separately authorized ceiling of exactly one worker call and one automatic
reviewer call after model-free qualification.

`dev-control-plane` remains architecture, integration and exact-pin authority,
while the private managed fork owns application code. The retired patch queue
is historical Git evidence only. I11 and I12 add only the slices explicitly
described above; I9 remains inactive target design for task execution,
multi-cycle review, arbitration, admission, release and general recovery.

## Dispatch template

```text
Task: <one bounded DCP change>
Base: exact current origin/main; separate branch/worktree
Read: root AGENTS.md -> docs/CURRENT_OPERATING_CONTRACT.md -> relevant authoritative docs
Boundary: canonical DCP_AO_LAB_ROOT and exact DCP Orchestrator.app; never installed AO, ~/.ao, repositories/remotes outside the explicitly authorized disposable canary, wb-core or production
Flow: one curator -> one direct executor; no nested curator or parallel DCP change
Entry: existing I8 worker entry remains only bin/dcp-ao-submit; I11 internal submit is model-free proof only; I12 auto-review needs no second chat impulse
Proof: model-free gates, exactly one worker plus one automatic-reviewer call for the authorized fresh I12 canary, semantic/security review, one ready PR per repository, green CI, safe merge, clean canonical fast-forward
Stop: fail closed on ambiguous identity/auth/isolation or unsafe cleanup; never synthesize owner acceptance
```
