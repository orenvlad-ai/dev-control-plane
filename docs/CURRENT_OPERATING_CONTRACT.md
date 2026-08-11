# Current operating contract

operating_contract_revision: 2026-08-11.6

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
single-flight and restart reconciliation. One separately exact
`dcp-review-lab` profile may create and terminally merge one synthetic PR after
the bounded review and provider gates below. It does not activate general task
execution, arbiter, admission/release, queue, action lease, general recovery
policy, general auto-merge or a real execution target.

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

## Quiet curator closure

Every executor task prompt ends with a mandatory instruction to reach an
applicable terminal state independently and, after COMPLETE or proven BLOCKED,
send exactly one final technical handoff to the originating curator task, then
stop. The handoff states status; work done; work not done or out of scope; PR
and final SHA; checks; review, CI, merge and canonical fast-forward state;
difficulties; risks; and blockers. Each field remains explicit even when its
value is none or not applicable.

Immediately after a successful dispatch the curator ends the turn. Quiet wait
means the absence of active model or tool calls; it is not a wait/poll loop.
Until one of the three permitted wake signals arrives, the curator does not
initiate executor read/list/wait/status queries, GitHub/CI/runtime audits of the
executor's work, follow-up prompts, interim summaries, parallel work,
independent verification of the handoff, heartbeats, automations or monitoring.
The only wake signals are the final handoff, a proven request from the executor
for an action that strictly only a human can perform, or a new explicit owner
instruction.

All technical verification and evidence, relevant checks, semantic/security
self-review and terminal closure before handoff belong to the executor. After
the handoff the curator only restates its result concisely to the owner without
a second technical audit. This closure does not weaken the one-active-change
rule, protected GitHub review, green CI, safe merge, clean canonical
fast-forward or any safety boundary above. Technical completion remains
distinct from manual owner acceptance; only the owner may write
`Задача принята`.

## Exact packaged laboratory contour

The current implemented laboratory stage is I12. Its application source is the
private managed repository `orenvlad-ai/dcp-orchestrator` at exact commit
`e458f545f9e7879c16278ccd13901519a5c5e6bb`, pinned by this repository. That
fork preserves official Agent Orchestrator `v0.12.1`, commit
`1df40e93772c2c48e916870d9c3ddf8f29a69f84`, and the qualified I8 behavior.
Managed source is build/test input only; it is never the canonical runtime and
`npm run dev` must not be used to keep DCP Lab alive.
Preparation fetches the complete ancestry of that exact immutable fork commit
with bounded retry and converts any older shallow checkpoint before provenance
verification; a moving ref or depth-limited substitute is not accepted.

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
managed source, builds, evidence, the remote-free `targets/dcp-lab` and exact
PR-capable `targets/dcp-review-lab` also stay under that root. Electron caches use
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
read-only SQLite/tmux/process-tree checks prove no active worker or reviewer
model action. An `active` worker row is always a stop. A non-active row with a
historical launch id is replaceable only when its exact retained pane exists as
a bare shell or is provably absent; any descendant or ambiguous probe remains a
stop.
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

The only PR-capable entry is the same canonical script with every discriminator
explicit:

`bin/dcp-ao-submit --target dcp-review-lab --profile synthetic-pr --task-id '<lowercase-id>' --prompt '<one line>'`

That profile accepts a 1-16 character lowercase task id, verifies the exact
private repository URL, clean fast-forwarded `main`, canonical base and linked
worktree topology, and rejects duplicate task identity before one native
worker spawn. It installs an exact `accept-edits` worker, one Codex reviewer,
the typed `dcpReviewLabNetwork` marker, stock native
`dcp-review-lab-<n>` worktree/session identity and
`ao/dcp-review-lab-<n>/root` branch plus immutable agent rules. The worker
sandbox enables network only for card 7 onward after that marker and the exact
data/worktree/Git/branch/fetch/push identities validate; cards 1-6, every
ordinary worker and every reviewer remain network-disabled. Unknown or
duplicate flags, another repository/profile/path/remote/branch/config or
ambiguous value fail closed. The remote-free target never receives this
profile or any GitHub mutation authority.

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

### Exact synthetic-PR terminal merge

Only an Idle native worker whose project is exactly `dcp-review-lab`, whose
session/task prompt and `DCP:<task-id>` display name agree, and whose workspace,
private/common Git directories, `ao/dcp-review-lab-<n>/root` branch, base SHA and
single ready PR all match may enter the terminal gate. The one structured Codex
review must be approved with no findings for that exact PR/head. Fresh GitHub
facts must show OPEN, non-draft, the same author/base/head, exactly one successful
check named `dcp-review-lab`, no unresolved review thread, MERGEABLE and CLEAN.
Unknown, missing, skipped, neutral or ambiguous values fail closed.

The trusted daemon then claims that same `ReviewRun` once and requests a squash
merge with the expected head SHA. Success stores the provider merge SHA and
projects the existing card to terminal `Merged`; the synthetic repository has
no deploy, so no deploy fact is invented. A provider error or unknown mutation
outcome is terminal and is not automatically retried. Startup may only reconcile
an already-running claim from fresh proof that the exact PR was merged; it never
creates a second merge, reviewer, card, service or state authority. PRs #1/#2/#3
and all preceding cards/runs remain immutable.

Managed-fork PR [#8](https://github.com/orenvlad-ai/dcp-orchestrator/pull/8)
closes the final worker-side installed-CLI argv blocker at exact merge commit
`5ab85f0010bd120728b8514c84f1fe41fac0ba70`, tree
`6c0b7fadb5a4525a822b371b10fc2069fc9afa4c`. The I4 native card remains
immutable evidence of a pre-model parser failure; it is not reused or hidden.

Managed-fork PR [#9](https://github.com/orenvlad-ai/dcp-orchestrator/pull/9)
closes the next worker-side sandbox blocker at exact merge commit
`be3239808c88dff1a0f2a7801fedfb73c61ed789`, tree
`7fdd7db08e8c37f1fe783538cfea3cba2c55441a`. The non-bypass builder derives
only the concrete linked worktree's private gitdir and common `.git`, verifies
their pointer/backlink/commondir topology against local Git, and passes those
two roots through supported `--add-dir`. Missing, ordinary or inconsistent
layouts fail before Codex starts. The reviewer strips all worker
`--add-dir` pairs before enforcing read-only mode.

The failed I2 run `b65be186-7326-4272-85aa-acfcd39bc938`, the failed I3 run
whose id begins `0aaf2da9`, and `orenvlad-ai/dcp-review-lab#1`, `#2` and `#3` are
immutable audit evidence: they are not changed, reused, retried or merged. The
I5 checkpoint card `dcp-review-lab-4` is also immutable: its one worker call
reached Codex session `019fece4-e13f-79b1-b3af-c0e6392ebdb5` and consumed
16,222 tokens, but the built-in workspace sandbox denied Git's external
worktree metadata, so it produced only an untracked marker and no commit, push,
PR or reviewer call.

The first terminal-merge qualification attempt is preserved as
`dcp-review-lab-6`: Codex session
`019fefec-83f2-7090-a4e6-fcda57f262f9` consumed 29,309 tokens, created one
local commit `c92bbef`, then stopped after two bounded push attempts both proved
that the workspace-write sandbox could not resolve `github.com`. It created no
remote branch, PR or reviewer run and is never resumed or reused. Managed-fork
PR [#14](https://github.com/orenvlad-ai/dcp-orchestrator/pull/14) adds only the
typed/exact worker network contour above at merge
`0ef626fad32af4397b345e596a0f98e1965a0077`, tree
`8d3c05febe32c15072d23f87b02c82e29e2b51be`; reviewer argv explicitly rejects
that worker flag. The first canonical submit after that install failed closed
before native spawn or model launch because the strict CLI config mirror did
not yet accept the typed marker. Managed-fork PR
[#15](https://github.com/orenvlad-ai/dcp-orchestrator/pull/15) preserves that
existing field through exact `--config-json`; the current merge is
`e458f545f9e7879c16278ccd13901519a5c5e6bb`, tree
`c618f25ab14c5e55402232c411332cb667e803f6`. No card 7 was created and the
remaining worker allowance stays at two calls.

After every model-free source, API, type, package, install and identity gate,
the original three-call allowance has one consumed by immutable card 6; the
remaining qualification may use at most two fresh worker model calls, each on
a new native card and only after a distinct proven fix. An unchanged
failure is never retried; the same root cause repeating twice stops the flow.
Only the successful worker may create the single fresh unmerged minimal PR, and
only then may exactly one automatic reviewer model call run. There is no manual
Run Review or second chat impulse. After the required exact-head GitHub gate,
only the daemon performs the one terminal canary merge. The approved verdict
must progress from Ready to Merge to Merged; app/daemon restart must restore
Merged without another reviewer or merge. Old sessions, cards, runs and
canaries remain immutable evidence.

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

For the non-bypass `accept-edits`/`auto` modes, the worker uses Codex's supported
`approval_policy="on-request"` config override with explicit
`--sandbox workspace-write`; it never emits the unsupported exec-level
`--ask-for-approval`. For a linked worktree it adds only its verified private
gitdir and common `.git` as writable roots; no caller may supply an arbitrary
path, and ordinary/mismatched layouts fail closed. Unknown permission modes
fail closed before launch. The model-free installed-CLI preflight runs only
`--help` and `features list` while exercising the same isolation, config,
sandbox and repeated `--add-dir` parser surface, so it cannot make a model
request. Fork tests separately reproduce the baseline Git denial and successful
`git add` with only the derived roots inside an isolated linked worktree.
Only the typed synthetic-PR profile may additionally set
`sandbox_workspace_write.network_access=true`, and only after the exact native
card (7 or later), canonical data/worktree/private/common Git paths, branch and
sole fetch/push origin all match `orenvlad-ai/dcp-review-lab`. The reviewer
rejects this flag before enforcing read-only mode. No ordinary worker, earlier
card, remote-free target or reviewer receives network from this exception.

The package has no updater initialization, feed metadata, maker or publisher;
updater UI/IPC is inert and updater dependencies are pruned. Renderer and daemon
telemetry cannot be enabled by environment, no telemetry control routes are
mounted, and no analytics key/host/install identity, local telemetry reservoir,
crash upload or crash reporter is initialized or packaged. Source/dev remains
only a model-free build/test instrument.

I12 adds no general task execution, arbiter, admission, Release Train, general
auto-merge, repair loop, monitoring service, real execution target, `wb-core`,
production, hosted API, Telegram, notarization or distribution installer.
Historical I8 live qualification used only short
remote-free marker tasks and no automatic retry. The owner raised its
cumulative ceiling to five model calls: one preserved diagnostic stop-gate plus
one successful cold, one successful warm and two successful concurrent calls.
The four qualified sessions (`dcp-lab-2` through `dcp-lab-5`) are distinct and
Idle under one persistent app and daemon; minimal redacted evidence remains
outside Git. I11 itself used zero model calls. After the preserved I5 checkpoint
call, the final I12 qualification has the separate bounded ceiling above: at
most two remaining fresh worker calls after distinct model-free fixes and
exactly one automatic reviewer call only after a successful worker commit/PR.

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
Entry: bin/dcp-ao-submit is the only worker entry; dcp-lab stays remote-free and only exact dcp-review-lab plus explicit synthetic-pr/task-id is PR-capable; I11 internal submit is model-free proof only; automatic review/terminal merge need no second chat impulse
Proof: model-free gates, at most two remaining fresh worker calls after distinct proven fixes and exactly one automatic-reviewer call only after a successful canary commit/PR, exact-head green/CLEAN/MERGEABLE terminal merge, restart persistence, semantic/security review, one ready implementation PR per repository, green CI, safe merge, clean canonical fast-forward
Stop: fail closed on ambiguous identity/auth/isolation or unsafe cleanup; never synthesize owner acceptance
Quiet: after successful dispatch end the curator turn; quiet wait has no active model/tool calls or wait/poll loop; wake only on final handoff, proven strict human-only request, or new explicit owner instruction
Close: executor independently reaches COMPLETE or proven BLOCKED, owns all verification/evidence/semantic-security self-review/closure, then sends exactly one final handoff to the originating curator task and stops
Handoff: status; done; not done/out of scope; PR and final SHA; checks; review/CI/merge/canonical fast-forward state; difficulties; risks; blockers; curator only summarizes it without a second technical audit
```
