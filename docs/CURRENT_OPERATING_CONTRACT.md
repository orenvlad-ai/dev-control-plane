# Current operating contract

operating_contract_revision: 2026-08-12.8

This is the compact operational start for DCP work. Architecture and scope
remain authoritative in [Project brief](PROJECT_BRIEF.md),
[Roadmap](ROADMAP.md), and [Decisions](DECISIONS.md). Root `AGENTS.md` plus this
contract define the starting flow when operational instructions conflict.

I9 records the separately approved future
[DCP v1 target architecture](TARGET_ARCHITECTURE_V1.md). That document is
design-only and is not part of the current operating flow except for the
explicit I11 foundation, bounded I12 reviewer and separately authorized I13
slices below. I11 activates
only durable model-free submission, read, events, restart recovery and display
of a synthetic SUBMITTED task. I12 activates one stock, exact-head, read-only
reviewer after an eligible worker becomes safely idle, with model-free
single-flight and restart reconciliation. One separately exact
`dcp-review-lab` profile may create and terminally merge one synthetic PR after
the bounded review and provider gates below. I13 adds only the exact Stage 1
admission line and current Stage 2 source-integration state below; none of these
activate general task execution, arbitration, admission/release, queue, action
lease, general recovery policy, general auto-merge or a real execution target.

## Owner-approved I13 staged block

On 2026-08-11 the owner separately approved two sequential autonomous stages.
Stage 1 is technically complete. Its green terminal handoff, independent
curator verification and the fresh Stage 2 executor satisfy the recorded
entry condition; none of that widens the exact Stage 2 contract below.

Stage 1 is one minimal mechanical Admission Controller inside the existing DCP
daemon and SQLite for exactly two new synthetic `dcp-review-lab` native
task/card identities. The two existing stock-compatible worker and automatic
review contours may run independently. After both exact heads are approved and
provider-qualified, only one durable admission owner may hold terminal merge
authority. The other task persists a passive FIFO wait with no process, timer,
heartbeat, watcher, model polling or token use. A terminal result is the event
that causes one model-free reconciliation of the next waiter.

Reconciliation has three allowed outcomes. A compatible fresh candidate may
claim and merge. Deterministic relevant-main staleness may create one bounded
wake/resume for the same original worker and, after a new exact-head handoff,
one fresh automatic review. Proven conflict or ambiguity may persist one
structured arbiter-needed incident packet, but Stage 1 cannot create or call an
arbiter. Exact task/card/session/worktree/repository/PR/head/check/review and
admission-generation identity, FIFO order, ownership and action outcome must
survive controlled restart. Duplicate review, wake, claim or merge, stale
ownership and manual orchestration fail closed.

The Stage 1 live allowance is exactly two new initial worker calls and at most
one automatic reviewer per initial exact head. One additional same-worker wake
and one fresh exact-head reviewer are permitted only if the second task's
post-first-merge reconciliation proves the ordinary-refresh condition. There
is no replacement card, generic retry, manual Run Review or model call beyond
those bounds.
The happy-path canary should use compatible changes and complete with only the
two initial workers and two reviewers.

Stage 1 has now completed its governed managed-fork PRs, green CI, immutable
pin updates, deterministic build/install gates and bounded live qualification.
The implementation adds only additive migrations in the existing SQLite plus
the bounded admission records/events/actions above. It adds no
second registry/database/daemon, queue service, scheduler, watcher, heartbeat,
general recovery loop, UI column, Release Train, label authority, production
target, `wb-core`, hosted surface, Telegram, Human Gate or owner-acceptance
synthesis.

Stage 2 is limited in advance to one event-driven arbiter v1 for a proven
Stage 1 structured ambiguity. Its reviewed pre-runtime contract is
[I13 Stage 2 global release arbiter v1](I13_STAGE2_ARBITER_V1_CONTRACT.md).
That contract fixes one exact incident generation, the Sol/xhigh one-call and
16,384-token arbiter budget, decision/mutation authority, cards 11/12 and the
seven-call total synthetic qualification ceiling. It must be green, merged and
present in the clean canonical checkout before managed-source implementation,
runtime mutation or a model call. Contract PR #133 and managed-source PR #23
are green and merged. Contract correction PR #137 and managed-source correction
PR #24 additionally pin the qualified strict rollout-budget configuration and
one audited same-generation recovery from the observed local strict-config
rejection. The corrected source was pinned by PR #138 and deterministically
installed. Its provider then rejected root response-schema `oneOf` with
`invalid_json_schema` before inference, result output or token use. Revision 19
freezes one final, separately audited same-incident re-arm after a
non-compositional schema correction; it does not authorize a second
inference/model call or a general loop. Managed-source PR #25 is green and
merged, and this revision pins its exact immutable merge/tree; installation and
resumed live qualification are not yet claimed.

The first Stage 2 live identities are immutably cards 11/12 with approved
exact-head reviews and green checks. The earlier four-byte integration-literal
drift was corrected without repeating either worker or reviewer. Admission
then merged card 11 once at
`b34b31b5443890e69128db2862726950a6bbac0d` and retained card 12 under the
global freeze with exact incident
`dcp-global-release-2694dbd8b3d4897063603d7a8607ca516aa2f8e05c5a3c39cf56d8e3f18c3c60`.
The first package fenced one launch, but Codex strict parsing rejected its
top-level `rollout_budget.*` shape before a Codex session or provider request;
the durable action row is `failed/child_failed`, and the live model-call total
therefore remained the four initial worker/reviewer calls. Correction PRs
#137/#24 preserve that rejection in one migration-0053 audit row and re-armed
only this same incident/generation. Exact installed source
`2fbd9bf4789a5b388fb12c58d9347968ed06e6de` then passed strict config and
opened Codex session `019ff21d-4cde-72d1-b70d-49efd3cd1c17`, but the provider
rejected unsupported root `oneOf` with `invalid_json_schema` before inference,
result output or tokens. At that checkpoint the incident remained failed/frozen
with zero recovery wakes and one durable incident row; revision 19 then
authorized the final separately audited schema correction.

## Stage 2 terminal result

The fresh Stage 2 executor reached a proven terminal `BLOCKED`, recorded in
[I13 Stage 2 terminal BLOCKED evidence](I13_STAGE2_BLOCKED_EVIDENCE.md). The
single Sol/xhigh inference returned `assign_recovery` but
`maxFreshReviews=0`; trusted validation rejected it because the only permitted
path requires one fresh review. The durable incident remains frozen with one
call, no decision, no wake and no recovery review. No continuation is
authorized by the original contract.

## Owner-approved exact-incident successor correction

On 2026-08-12 the owner authorized the separately reviewed
[exact-incident successor arbiter contract](I13_STAGE2_ARBITER_SUCCESSOR_CONTRACT.md).
It does not revise or accept the rejected artifact. It preserves the original
failed row, result/input/schema artifacts, session, token count and counters,
then permits one distinct attempt-generation-2 `gpt-5.6-sol`/`xhigh` call for
the same incident under a hard 16,384-token budget. The new contract must merge
into the clean canonical checkout before source work; managed source, immutable
pin and deterministic install/preflight must then merge and complete before the
call.

The successor model does not own `maxWorkerCalls` or `maxFreshReviews`. Those
fields are absent from its decision schema; the trusted daemon fixes the only
positive policy to one same-worker wake plus one fresh exact-head review. The
successor may choose only the existing card-12 recovery owner/path or a bounded
safe stop. At most one successor decision, worker wake, reviewer and PR #9
terminal merge may occur. Duplicate, late, stale, foreign and malformed results
are inert, restart cannot relaunch, and every wait remains model-free without a
timer, watcher, heartbeat or poll. There is no replacement card/incident/PR,
third arbiter call or general retry policy.

The one successor call then produced an exact schema-valid recovery artifact,
but the trusted validator omitted its nested, frozen-envelope
`mergeTreeEvidenceDigest` from the evidence allowlist and failed closed. The
owner-authorized
[exact-result validation recovery](I13_STAGE2_SUCCESSOR_VALIDATION_RECOVERY_CONTRACT.md)
permits one reviewed model-free correction and one atomic validation of that
unchanged exact result. It permits zero additional model calls, records the
failed successor state in a separate audit row and stops at `decided`/zero-wake
until a controlled restart. Every non-exact or later replay remains inert.

The exact recovery source was subsequently merged, deterministically installed
and exercised. Its one model-free replay accepted the unchanged successor
result once and stopped at `decided`/zero-wake. The required controlled restart
then consumed the sole card-12 wake, but the stock native resume failed before
Codex launch because the preserved worker has no restorable `agent_session_id`.
The successor attempt is terminal `failed/repair_launch_failed`, with one
accepted decision, one consumed wake, no recovery review and no merge. A second
controlled restart was inert. This terminal `BLOCKED` is recorded in
[I13 Stage 2 successor terminal evidence](I13_STAGE2_SUCCESSOR_TERMINAL_EVIDENCE.md);
no continuation is authorized by the successor contracts.

## Owner-approved exact card-12 fresh worker-session recovery

On 2026-08-12 the owner separately authorized the governed
[card-12 fresh worker-session recovery](I13_STAGE2_CARD12_FRESH_WORKER_RECOVERY_CONTRACT.md)
after the immutable `failed/repair_launch_failed` predecessor above. It does
not reset the consumed native wake or change the accepted successor decision.
Its own reviewed contract must merge into the clean canonical checkout before
managed-source work; separate reviewed source and immutable pin merges plus
deterministic install/preflight must complete before runtime or a model call.

Only existing card/session `dcp-review-lab-12`, task `i13-arbiter-b`, its
current worktree/branch, PR #9, old head
`d4fcb68051ae113ed497d02151a759800ee85633` and the same incident are eligible.
Recovery generation 1 may create exactly one separately audited fresh
stateless worker runtime/Codex session under a hard 16,384-token ceiling. The
old empty native `agent_session_id`/`runtime_launch_id`, failed row, one
accepted decision and one consumed wake remain unchanged. The worker receives
only the bounded original task/scope and exact conflict-repair envelope, may
produce one guarded same-branch head, and has no second attempt.

One trusted new head may launch at most one fresh context-free reviewer. Only
approved/no-findings output, the exact named successful check and current
OPEN/non-draft/MERGEABLE/CLEAN provider facts may rebind admission sequence 4
and let the existing daemon terminally merge the same PR #9 once. Duplicate,
late, stale, foreign, malformed, restart or exhausted-budget cases fail closed
without another worker/reviewer. No new card/task/native session/worktree/
branch/PR/incident/arbiter call or decision, transcript replay, general retry
or expanded repository is authorized.

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

The current approved source stage is the exact I13 Stage 2 card-12 fresh worker
recovery. The installed runtime is exact source
`fbcf4929f9192f7cce9c5097b0bc6a449d28e663`. Its first controlled start
failed closed before the call fence at `preflight_failed/identity_drift`, with
0/0 worker/reviewer calls, because the Git preflight required the exact
conflict path to be added rather than modified from current main. Managed-source
[PR #29](https://github.com/orenvlad-ai/dcp-orchestrator/pull/29) passed
source/package CI and merged normally. Migration 0058 preserves that zero-call
failure in a separate audit and re-arms only the same unused generation-1 row;
the code correction changes only the exact `M` path-status assertion. This pin
claims no replacement/install, recovery model call, new head, review or merge.
Application source is the public managed repository
`orenvlad-ai/dcp-orchestrator` at exact commit
`75a14431a3433f581755f2e0ec096814e3e9ecb1`, tree
`a993819f30776ca595d5687f098ec00b98d67ba2`, pinned by this repository. That
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
read-only SQLite/tmux/process-tree checks prove no active worker, reviewer or
bounded Stage 2 arbiter model action. An `active` worker row is always a stop.
A non-active row with a
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
sandbox enables network only for exact cards 7, 9, 10, 11 and 12 after that
marker and the exact data/worktree/Git/branch/fetch/push identities validate;
the installed Stage 1 bundle still recognizes only 7, 9 and 10 until replaced.
Cards 1-6, pre-stage card 8, cards 13+, every ordinary worker, every reviewer
and the arbiter remain outside this worker-network contour. Unknown or
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
private/common Git directories, `ao/dcp-review-lab-<n>/root` branch and single
ready PR all match may enter the terminal gate. A session base is accepted only
when both stock fields are absent or when both contain the exact `origin/main`
identity; in either case the valid PR base SHA must equal clean canonical
`main` and `origin/main`. The one structured Codex
review must be approved with no findings for that exact PR/head. Fresh GitHub
facts must show OPEN, non-draft, the same author/base/head and exact head
repository, exactly one successful check named `dcp-review-lab`, no unresolved
review thread, MERGEABLE and CLEAN.
The stock provider review decision must be the known non-blocking `none` or
`approved`; empty, unknown, review-required and changes-requested decisions,
and missing, skipped, neutral or ambiguous values elsewhere, fail closed.

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
existing field through exact `--config-json`; that bounded merge is
`e458f545f9e7879c16278ccd13901519a5c5e6bb`, tree
`c618f25ab14c5e55402232c411332cb667e803f6`. No card 7 was created and the
remaining worker allowance stays at two calls.

Card `dcp-review-lab-7` then used worker Codex session
`019ff01e-9d97-7cf3-b241-4d6820fe26e1` to create commit
`f10c825fced998c01a3e83ef4073451c3bd2e4a3` and ready PR #4. The sole automatic
reviewer session `019ff01f-9805-7c22-9bd4-54d53e99be5d` returned approved with
no findings for exact run `28025930-ecc0-481e-a13b-9fb5a5a14a94`; the required
check is successful and provider facts are OPEN/MERGEABLE/CLEAN. The terminal
engine still compared the retired synthetic prefix and pre-marker worker
config, so it correctly made no provider mutation. Managed-fork PR
[#16](https://github.com/orenvlad-ai/dcp-orchestrator/pull/16) binds eligibility
to native card 7+ and marker=true at merge
`f23ee9a9cbc8be57710b4dd6c95a23bf0fb52b24`, tree
`67a084e9e546a725b0b19b3074ba205f6c03fa82`. The stock native spawn leaves both
session diff-base fields absent, so managed-fork PR
[#17](https://github.com/orenvlad-ai/dcp-orchestrator/pull/17) accepts only that
paired absence and instead binds the valid stored/fresh PR base to clean local
`main` and `origin/main`. The stock GitHub adapter normalizes an absent provider
review to domain `none`; managed-fork PR
[#18](https://github.com/orenvlad-ai/dcp-orchestrator/pull/18) accepts that
known non-blocking value while rejecting empty/unknown/blocking decisions. The
stock GraphQL batch omitted the head-repository field, so managed-fork PR
[#19](https://github.com/orenvlad-ai/dcp-orchestrator/pull/19) requests and
preserves `headRepository.nameWithOwner`; null or missing identity stays empty
and fails closed. Managed-fork PR
[#20](https://github.com/orenvlad-ai/dcp-orchestrator/pull/20) adds the exact
I13 Stage 1 durable admission/refresh/incident slice. Model-free preflight then
found pre-stage card 8 and PR #5 already completed, so managed-fork PR
[#21](https://github.com/orenvlad-ai/dcp-orchestrator/pull/21) binds the fresh
cohort to cards 9/10 and fixes the browser broker cancellation race exposed by
CI. Canary then exposed a false `canonical_main_diverged` packet after the first
merge advanced exact `origin/main`; managed-fork PR
[#22](https://github.com/orenvlad-ai/dcp-orchestrator/pull/22) retains the packet
as audit evidence, proves exact fast-forward ancestry and a clean merge tree,
and permits one startup-only model-free recovery. Managed-fork PR
[#23](https://github.com/orenvlad-ai/dcp-orchestrator/pull/23) adds only the
reviewed exact Stage 2 incident/input/action, one-shot arbiter and bounded
same-worker repair contour. Managed-fork
[#24](https://github.com/orenvlad-ai/dcp-orchestrator/pull/24) corrects the
strict structured rollout-budget shape and adds the one-row audited prelaunch
recovery. The current immutable source merge is
`2fbd9bf4789a5b388fb12c58d9347968ed06e6de`, tree
`ada1ccead3e9920bf1e658ac3c136bc61acea6ab`.

The automatic reviewer allowance is consumed. One unused emergency worker-call
ceiling remains from the original three, but it is not used for this contour:
the complete approved run closed through model-free startup reconciliation
after exact install. There was no new card, reviewer, manual Run Review or
second chat impulse. The daemon claimed the existing run once and squash-merged
PR #4 at provider merge SHA
`202ca32a0e8d563c6c478d094073246383720e5d` on
`2026-08-11T10:52:05Z`. Card 7 projected `Merged` before restart and the same
run/card/SHA projected `Merged` after a controlled app/daemon restart.

The installed receipt binds fork `b23b519cd532555c203863586032d157fc1c8c13`,
daemon SHA-256 `c9d59d2c2a8453d278ebc45a5a4872e8f96d35fd9ad29cad6cd109a0043cc6a1`
and asar SHA-256 `a1206d002b16a8d9a3cb4485c4522b4fe685fdb102840d1d96530a4f11a4ff90`
at `2026-08-11T14:26:15Z`; the preceding bundle backup is
`i12-20260811T142614Z`. The Stage 1 cohort is the two distinct native cards
`dcp-review-lab-9` (`DCP:i13-admit-a`) and `dcp-review-lab-10`
(`DCP:i13-admit-b`). Admission sequence 1 belongs to card 10 / PR #6 / head
`3afd3d4cbcc2fe4a6bf2fde3e747213e5c874d53`; sequence 2 belongs to card 9 /
PR #7 / head `649c60cbe6c8542f0a3d20b05b11ae5c54a79263`. Both reviews are approved
with no findings and both named `dcp-review-lab` checks are successful.

Sequence 1 merged once at `5e65c167d8d9d36d70c89fc8e9b5b07497905645`
on `2026-08-11T13:57:55Z`. Sequence 2 waited durably without a model process,
retained its original 941-byte structured false `canonical_main_diverged`
packet, then startup reconciliation proved exact provider-base fast-forward
ancestry and a clean merge tree and merged once at
`dbaf01b05e85ffffa4c843a905e2fe5229eaf0da` on
`2026-08-11T14:28:38Z`. `refresh_wake_count` remained zero for both rows.
Two controlled starts preserved order, leases, PR/head/base/review/run/merge
identity, two succeeded rows, seven total reviews, nine total runs and ten
cards with no card 11. No duplicate review, run, wake, claim or merge appeared.
The exact two canary sessions were then terminated through the native session
lifecycle and their worktrees reclaimed while their cards still truthfully
project `Merged`; historical audit rows and reviewer panes remain. The target
checkout is clean at exact `origin/main` `dbaf01b05e85ffffa4c843a905e2fe5229eaf0da`.
PRs #1/#2/#3 remain unchanged.

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
call, card 6 and card 7 consumed two of the separate three-worker allowance;
one unused emergency worker-call ceiling remains. The automatic reviewer
allowance is consumed and no further model call is permitted for the approved
run.

`dev-control-plane` remains architecture, integration and exact-pin authority,
while the public managed fork owns application code. The retired patch queue
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
Proof: model-free gates, card 7 exact-head green/CLEAN/MERGEABLE with the sole approved reviewer already persisted, no further model call, terminal merge and restart persistence, semantic/security review, one ready implementation PR per repository, green CI, safe merge, clean canonical fast-forward
Stop: fail closed on ambiguous identity/auth/isolation or unsafe cleanup; never synthesize owner acceptance
Quiet: after successful dispatch end the curator turn; quiet wait has no active model/tool calls or wait/poll loop; wake only on final handoff, proven strict human-only request, or new explicit owner instruction
Close: executor independently reaches COMPLETE or proven BLOCKED, owns all verification/evidence/semantic-security self-review/closure, then sends exactly one final handoff to the originating curator task and stops
Handoff: status; done; not done/out of scope; PR and final SHA; checks; review/CI/merge/canonical fast-forward state; difficulties; risks; blockers; curator only summarizes it without a second technical audit
```
