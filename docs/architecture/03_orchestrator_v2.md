# Orchestrator Codex v2

Status: authoritative architecture for the v2 runtime. It supersedes the
hosted-execution and hosted-mutation parts of
`02_hosted_control_plane_architecture.md`; the approved host, isolated paths,
Basic Auth boundary and deploy runner remain in force.

## Authority invariant

There is exactly one orchestration writer: the deterministic Supervisor
process on the owner's Mac and its private SQLite registry. They are one
service boundary, not two agents. The hosted `devcontrol.pro` process is a
rebuildable read-only projection and never supplies instructions in an ingest
response. GitHub is the source of PR/check/merge truth and a mechanical Release
Train is the only actuator. A fresh `gpt-5.6-sol`/`ultra` invocation may return
a schema-bound recommendation for a release conflict or incident, but it never
mutates state.

The following equation must hold after cutover:

```text
mutation authority = local Supervisor generation
hosted projection control authority = false
model control authority = false
GitHub hidden control authority = false
```

The legacy hosted cockpit, OAuth writes, MCP write tools, hosted Codex runner,
target production continuation and operator-parity path remain preserved in
Git history and legacy runtime state only. They are not imported by the v2
projection process and cannot be re-enabled by an HTTP request or an old OAuth
grant.

## Runtime topology

### Local Supervisor

The launchd service owns:

- one generation lease and fencing token;
- a SQLite registry in WAL mode with `synchronous=FULL`, foreign keys, schema
  migrations, online backups and mode `0600` under a mode `0700` runtime root;
- optimistic revisions and compare-and-swap transitions;
- event and idempotency identifiers, transactional inbox/outbox, executor
  generations, per-task/per-thread locks, sorted atomic resource locks and one
  global release lane per target;
- the long-lived owned `codex app-server` stdio child used for Supervisor-owned
  executor threads;
- outbound projection delivery and durable attention delivery receipts.

No SQLite transaction remains open while waiting for Codex, GitHub, HTTPS, a
deploy adapter or an arbiter. Each external call follows reserve/call/receipt:
reserve durable work in a short transaction, perform the call, then apply a
receipt only if its generation/revision/token still matches.

Runtime releases are immutable directories selected through atomic `current`
and `previous` symlinks. launchd binds only `127.0.0.1:8766`. Install/update
requires a clean exact `origin/main` SHA. Rollback changes the release symlink;
it never restores a retired legacy writer.

Activation consumes a fresh private nonce and a commit-bound qualification
manifest whose direct evidence files are re-opened safely and digest-checked.
The one allowed real capability canary is a nonterminal, schema-bound
checkpoint below 100%. Its durable call intent is counted before `run_turn`;
`single_attempt_canary` forbids a second model call after any failed or
ambiguous first attempt. Final terminal evidence and curator attention are
created only after activation, restart/offline and rollback proofs complete.
Successful activation writes a separate signed acceptance receipt bound to the
commit, qualification digest, release manifest, Supervisor generation and
nonce digest. Rollback eligibility depends on that receipt; copying or editing
an accepted JSON document cannot manufacture a trusted prior release.

### Hosted projection

The hosted systemd process is a separate entrypoint and imports no legacy
server, MCP, execution or target-production module. It owns only a rebuildable
projection SQLite database and serves:

- `POST /api/v2/ingest`, authenticated by an independent HMAC key;
- `GET /api/v2/health` and sanitized read-only state;
- the Russian responsive dashboard at `/` and `/runs/live`.

All other POST routes, including `/mcp`, OAuth, cancel, mark-stale, task start,
Codex, PR, merge, deploy, rollback and runtime-config writes, return a
controlled method denial before touching state. The service user receives no
Codex, OpenAI, GitHub or target-deploy credentials. Basic Auth continues to
protect the UI; only the exact HMAC ingestion path bypasses Basic Auth at
nginx.

Network or server failure never blocks local work. Projection events remain in
the local durable outbox until acknowledged. The hosted dashboard reports
`last_seen` and stale status instead of inventing progress.

### GitHub Release Train

The scheduler chooses a logical candidate; the Release Train does not. The
only ordinary intake is an exact task/workstream plus expected PR head SHA.
The Supervisor derives target, resources, dependencies, priority, logical lane
and declared files from the current Passport, then re-reads the complete PR
diff, checks, conflicts and merge state from GitHub. A caller cannot inject
scheduler policy or admission truth. A merged PR is proof-only and cannot be
actuated as an open candidate.

The actuator compare-and-swap merges the expected head, reads back the merge
commit, then invokes only a registered target deploy/verify adapter. It exposes
no raw command input. Repeated receipts are idempotent. Nonterminal target
observations are durable and re-polled without consuming the causal incident
budget; a changed PR head is superseded and must pass fresh intake.

`wb-core` remains an external target. Its business code never enters this
repository. The v2 adapter uses the target repository's current GitHub-native
admission, trusted-main queue readback and target production proof. It never
merges, deploys or edits `wb-core` directly. When the whole Task Passport
closure barrier is independently proven, a separate idempotent target-lane
release receipt closes the logical target lane as `completed`; a serious parked
closure uses `parked`. Any future target protocol change requires its own
governed PR and current target release lane.

## Contracts and task model

All v2 boundaries reject unknown schema versions and invalid enum values. A
Task Passport includes objective, expected result, contour, included/excluded
scope, constraints, acceptance, closure, autonomy, resources/modules/files,
dependencies, multi-PR/multi-deploy intent and exact curator/executor
identities.

Independent objectives have independent acceptance envelopes. Parallel parts
of one objective are workstreams of one task. A corrective or successor
generation retains the root workstream identity. The first merge/deploy is not
terminal when the passport declares a multi-PR or multi-deploy contour; the
logical target lane remains held until contour-aware proof is complete.

Executor identity is fail-closed:

```text
model = gpt-5.6-sol
reasoning = ultra
thread = exact Supervisor-owned Codex thread
host = recorded local host identity
```

The Supervisor stores both requested identity and observed protocol evidence.
An unsupported effort, a `model/rerouted` event, a stale executor generation or
an identity mismatch invalidates the registration/turn rather than silently
downgrading it. This requirement does not modify personal or unrelated chats.

## Codex transport

Production integration is an owned `codex app-server` child over local stdio
JSONL. WebSocket and the daemon control socket are not production dependencies.
At startup the adapter initializes the protocol, validates `model/list`, and
explicitly sends the required model and effort on each turn. Checkpoints and
terminal evidence are validated against output schemas; prose is never
orchestration truth.

The App Server child receives only a fixed path/locale/auth-home environment
allowlist plus non-interactive safety defaults. Ambient GitHub, OpenAI provider,
SSH-agent and other Supervisor credentials are not inherited by the executor;
release credentials remain confined to the independently fenced Release Train.

Each thread is serialized. Notifications are deduplicated by stable
thread/turn/item identities. After a disconnect the adapter reconnects with
bounded exponential backoff and jitter, then reconciles with stable
`thread/read(includeTurns=true)`. App Server exposes no documented global replay
cursor, so the design does not claim one. Existing Desktop-owned threads are
snapshot-readable only; cross-process live lifecycle attachment is not a
supported capability.

The exact curator chat is a host capability, not an App Server method. Terminal
and HumanGate messages first become non-coalescible durable attention events.
A stateless delivery-only adapter may claim exactly one event and ask the host
bridge to deliver it. It does not monitor, schedule or decide. Delivery failure
returns the event to pending and leaves `pending attention` visible remotely.
The exact curator thread locator remains in the local Passport/attention outbox;
it is not included in the hosted projection, hosted SQLite copy or state API.

## Deterministic scheduling

The mechanical fast path is:

1. continue a healthy active logical multi-PR lane;
2. release the only eligible green, conflict-free candidate;
3. when candidates are proven disjoint, choose by the hard order below.

Hard order before an arbiter:

1. active logical-lane continuity;
2. explicit owner priority and dependencies;
3. critical-path/unblock value;
4. risk and resource isolation;
5. aging/fairness;
6. `created_at` as the final tie-break only.

Task Passport declarations are compared with the actual PR diff. Two or more
ready candidates require an immutable `RELEASE_PLAN` case when they overlap in
files/modules/resources, touch the same DB/schema/migration/shared contract,
have an explicit dependency or lane competition, conflict in GitHub, disagree
with their Passport, contain an unknown path/resource, or admit multiple safe
orders. A fresh Sol Ultra response is a small schema-bound sequence/DAG bound
to task revisions, PR head SHAs and resources. A stale answer is discarded.
One accepted plan is stored and executed mechanically; it is not recomputed
every polling interval.

## Incidents, retry and HumanGate

For one causal fingerprint:

1. first occurrence: refresh truth and perform one bounded retry in the current
   executor;
2. second: create exactly one successor from a verified checkpoint; mark the
   predecessor stale only after successor proof;
3. third: create one incident and one fresh Sol Ultra `INCIDENT` decision;
4. apply the decision once and verify independently;
5. if the same fingerprint remains, do not create a fourth blind retry or
   another arbiter; park only the affected workstream and create one serious
   stall attention event.

A new budget requires a real Passport, strategy or causal-evidence revision.
The closed HumanGate allowlist is missing credential, interactive login/2FA,
captcha, security/permission change, new external destination, proven
irreversible risk, material scope/risk/acceptance change, or platform hard
stop. A gate is valid only when the next action is genuinely human-exclusive,
outside the autonomy envelope, independent safe work is complete and
repo-owned remediation is exhausted. Git/GitHub/CI/test/merge/deploy/retry,
queue wait, context size, weak confidence and reversible engineering choices
are not HumanGates.

## Progress, closure and acceptance

Progress is evidence-backed and monotonic except after explicit objective
invalidation. A registered executor starts at 5%. Canonical stages are 5, 15,
25, 40, 55, 65, 72, 80, 88, 95 and 100. Each checkpoint may update the Russian
delta/current text without changing the percentage. Time remaining is a
bounded estimate backed by unfinished stages, never elapsed-time fiction.

The main dashboard renders, without raw JSON:

```text
Статус: <В работе / Ожидание выпуска / Восстановление / Блокер / Завершена — требуется приёмка>
Задача: <человеческое название>
Прогресс: ≈N% · Осталось: ≈реалистичный диапазон
С прошлого отчёта: <доказанная дельта>
Сейчас: <одно действие>
Блокер: <только strict blocker>
```

It also shows task/workstream identity, PR/release lane, incidents, pending
attention, owner acceptance and `last_seen`. Sanitized audit detail is a
separate view. Accepted tasks disappear from active cards but remain in audit
history.

Progress 100 means contour-aware technical completion only. The Supervisor
must independently prove the declared closure using GitHub/Release Train and
create durable attention. The curator handoff is short Russian text with
status, one or two completed items, checks and real limitations, ending with a
request to reply exactly `Задача принята`. Acceptance is never automated.

Terminal strings supplied by an executor are claims, not closure proof. The
Supervisor dispatches them through an exact `(contour, target)` verifier
registry. `diagnostic` and `artifact` have no implicit verifier: a deterministic
callback must be registered for that exact target and return a typed proof
bound to the task/workstream revisions and SHA-256 terminal digest. Those
Passports declare exactly one `target:<target-id>` resource so registry routing
cannot depend on prose.

The control plane self-release adapter accepts only these immutable identities:

```text
github-pr-v1:orenvlad-ai/dev-control-plane:<PR>:<head-SHA>:<merge-SHA>
hosted-release-v1:wb-core-eu-root:devcontrol.pro:<deployed-merge-SHA>
```

For `release:done` it independently reads every named PR through the fixed
read-only `gh` adapter, requires merged/base `main`, exact head and merge,
both `v2-suite=SUCCESS` and `self-closure=SUCCESS`, and verifies that every
changed file is declared by the Passport. The final merge must equal the
current GitHub `main` head. The installed prior release also classifies the
actual diff independently of candidate-controlled workflows: controller,
governance, deploy, install, migration and projection-authority paths require a
typed `security_permission_change` HumanGate and cannot be self-merged from
green check names alone. Ordinary `self_merge` is intentionally not an
authorization for that installed authority surface, and the current Task
Passport vocabulary has no escape hatch that can silently widen it. A future
protected update therefore uses a new exact-head governed two-phase permission
change. An exact PR already proved `MERGED` is read-only closure evidence only:
it is never admission-ready and cannot enqueue a release action. For
`release:production` it additionally invokes only the hosted deploy runner's
fixed `loopback-probe`, `public-probe`, and `webcore-probe` commands. Their
readback must bind the active immutable release to that merge and prove the
projection-only role, valid HTTPS transport, Basic Auth boundary, and WebCore
independence. No caller-supplied `ContourVerification` file is accepted.

## Migration and rollback

Legacy state is never destructively converted. Before cutover:

- archive the live legacy local observer database through SQLite online backup,
  verify integrity and SHA-256, and retain its source/plist;
- on a Mac where the exact legacy DB, plist and launchd label never existed,
  seal a distinct private `legacy-absence/v2` receipt; never fabricate an empty
  archive or retirement record;
- record only sanitized table counts and shadow aggregates, never legacy raw
  events or provider payloads;
- preserve hosted JSON collections and audit history in their existing paths,
  mark them archived in rollout evidence, and never import them as writable v2
  truth;
- compare local v2/GitHub facts with the available legacy observer in shadow
  mode; do not start G6, Luna Watcher, Reporter, heartbeat or a global chat
  watcher.

Cutover order is tests/fakes, read-only shadow, hosted projection deploy,
non-activated local install, one checkpoint-only Codex capability pilot,
archive/retire the exact legacy launch agent (or prove exact clean-Mac
absence), then atomically activate one Supervisor generation. Closure includes
restart recovery, offline outbox/replay, hosted staleness, TLS/public
protection and version rollback proof. Only after those proofs may a private
schema-bound terminal command create the one final attention; it makes no
second model call and release contours wait for target-lane closure readback.

Hosted rollback switches to the previous immutable projection release without
restoring hosted mutation authority. Local rollback switches to the previous v2
release without reactivating the retired legacy observer. Runtime databases and
backups are retained in both cases.

A failed hosted activation may restore only an independently verified previous
v2 projection. With legacy or no previous v2 release it must prove the service
inactive and disabled, the exact nginx site and app pointer absent, port 8770
free, then retain an immutable quarantine receipt and pre-mutation snapshot.
Validation rejects an unresolved receipt. Bootstrap remediation is a separate
repo-governed runner transition: sanitized status readback plus a digest-bound
disposition naming an exact, distinct `origin/main` replacement SHA. It changes
no authority state and retains all evidence; when legacy layout still occupies
the app path it may atomically archive and idempotently normalize that inert
tree. A failed release may truthfully be absent when failure happened before
release finalization. Before activation begins, a newer descendant
`origin/main` may replace the declared tip only by appending a prior-tip and
prior-anchor bound supersession receipt. The old quarantine becomes historical
only after the effective descendant completes the full hosted proof and a
paired remediation receipt binds its deployed SHA and terminal chain anchor.

An orphan activation transaction remains fenced to its exact attempt. The
runner exposes sanitized `transaction-status`; `transaction-recover` requires
the exact release, attempt, snapshot digest and recorded stage, repeats all
source/target evidence, refuses a stage younger than 900 seconds and performs
only restore-or-quarantine recovery. It cannot continue activation.

Historical three-line `DEPLOYED` receipts that predate the systemd-unit digest
remain audit evidence only. They cannot authorize start, restore, rollback or
quarantine remediation; every authority-capable v2 deployment writes and
verifies the four-line receipt bound to the exact unit SHA-256.
