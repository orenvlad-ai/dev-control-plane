# Project brief

## Purpose

Keep the governed DCP architecture and one bounded local laboratory entry for
handing synthetic work from a curator to native Agent Orchestrator. This is not
a production control plane.

## Current I12 state

- Public managed source `orenvlad-ai/dcp-orchestrator` at exact commit
  `fbcf4929f9192f7cce9c5097b0bc6a449d28e663` owns application code. It
  preserves official Agent Orchestrator `v0.12.1` commit
  `1df40e93772c2c48e916870d9c3ddf8f29a69f84` and the qualified I8 behavior.
  I11 adds a minimal durable SUBMITTED task/event foundation to the existing Go
  daemon and SQLite, a synthetic/lab board projection, and removal of normal
  manual Orchestrator affordances. I12 adds a bounded event-driven stock
  reviewer for the exact current head of an eligible non-draft PR; the exact
  synthetic review-lab profile additionally permits one trusted terminal merge
  after structured approval and fresh green/CLEAN/MERGEABLE provider facts.
- This repository owns architecture/integration policy, the immutable fork pin,
  provenance, build/install/gateway scripts and adapter—not a second copy of
  application source. Managed source and every generated artifact remain under
  explicit canonical `DCP_AO_LAB_ROOT`.
- The only runtime is native arm64
  `/Users/ovlmacbook/Applications/DCP Orchestrator.app`, bundle id
  `pro.devcontrol.dcp-orchestrator`. Source/dev is build/test only.
- The app is the sole owner of its bundled `dcp-orchestratord` lifecycle.
  Closing its window does not exit; explicit Quit protects active work.
- `bin/dcp-ao-submit` is the sole normal curator door. It serializes exact
  identity/readiness proof and exactly one programmatic worker spawn. The
  ordinary `dcp-lab` target remains remote-free; only explicit target
  `dcp-review-lab`, profile `synthetic-pr` and a bounded task id enable the exact
  disposable GitHub flow. It never starts npm/source, stops, kills, restarts,
  replaces or recovers a daemon.
- Manual orchestrator spawn UI and hints are hidden. Native backend/CLI/API
  mechanisms remain, but only the bounded I12 reviewer is additionally active;
  every other automatic role still needs separate authorization.
- The loopback daemon API supports model-free submit/read/list-events for the
  exact remote-free `dcp-lab` only. Idempotent equal submissions reuse one task
  and event; conflicting/malformed/out-of-scope input fails before mutation.
  Restart preserves task id, SUBMITTED revision and monotonic events without a
  worker, process, timeout or model call.
- I12 reuses the stock review engine, tables, terminal and findings delivery.
  One eligible safely idle worker may create one read-only Codex reviewer for
  an exact head; per-worker locking and existing DB uniqueness prevent
  duplicates. Manual Run Review remains a fallback through the same trigger.
- Reviewer launch/exit is supervised. Early or unsuccessful exit is persisted
  as a visible technical failure. Restart leaves an exact live reviewer alone,
  fails ambiguous state without retry, and reconciles a proven stale run before
  at most one exact-head recovery launch. Approval uses stock Ready-to-Merge;
  findings return through the stock path to the same worker.
- Codex emits only one schema-constrained local JSON verdict. The trusted
  supervisor validates exact worker/reviewer/batch/run/PR/head identity and the
  current open non-draft head, then atomically completes the existing
  `ReviewRun` through the daemon. The model receives no control-plane command,
  daemon/GitHub credentials or network tool; missing, malformed, foreign,
  duplicate, late and stale results record no verdict and create no retry.
- For the exact review-lab profile only, the daemon binds project/session/task,
  base/head/branch/worktree/PR identity, the approved no-findings verdict, one
  successful `dcp-review-lab` check, resolved threads and current
  MERGEABLE/CLEAN state before one expected-head squash merge. The existing
  card becomes Merged and remains so after restart; this synthetic repository
  has no deploy and DCP invents none.
- I5 isolation remains: Codex uses standard authentication with
  `exec --ignore-user-config --ephemeral --strict-config`, and apps, hooks,
  plugins and multi-agent disabled. I6 process-outcome classification remains:
  Working while live, Idle on zero exit, Exited on machine failure. Exact
  daemon connection variables reach only the one-shot supervisor wrapper and
  are filtered from both the retained shell and the Codex child.
- The package cannot initialize an updater or telemetry and includes no update
  feed, maker/publisher, updater module, analytics client/key/host/identity,
  telemetry reservoir or crash reporter.

## Managed source, artifact and namespaces

`upstream/dcp-orchestrator.lock` pins the private fork repository, merged commit
and tree, LICENSE/NOTICE/provenance digests, exact I8 parity anchor/digest and
the preserved upstream release provenance. `bin/dcp-ao prepare` creates a clean
detached fork checkout below `DCP_AO_LAB_ROOT`, configures official upstream as
a push-disabled reference, and refuses another commit, diff or untracked file.
The retired patch queue is historical Git evidence only. A source refresh needs
new reviewed immutable fork and upstream pins plus license/dependency audit.

The canonical lab root is
`~/Library/Application Support/DCP Orchestrator`. Durable `state/` and `data/`,
managed source/build/evidence, the remote-free `targets/dcp-lab` and the exact
PR-capable `targets/dcp-review-lab` are isolated there. Cache is
`~/Library/Caches/pro.devcontrol.dcp-orchestrator`; logs are
`~/Library/Logs/DCP Orchestrator`. The app executable, daemon executable,
health service, run-file/socket, fixed port and per-launch instance identity are
all DCP-specific. No installed Agent Orchestrator application or `~/.ao` data is
ever discovered, inspected, migrated or imported.

`bin/dcp-ao build` runs the fork operational source gate, regenerates and
verifies API artifacts, then runs model-free backend tests/build, renderer
type/tests and native packaging. `bin/dcp-ao install` ad-hoc signs the verified artifact and
installs it only at the canonical user-owned path. The receipt binds bundle
path/id, exact fork commit/tree, preserved upstream commit, I8 parity digest,
embedded daemon digest and ASAR digest. I12 may stop one proven canonical old
app/daemon only after read-only SQLite/tmux checks prove there is no active
worker or reviewer model action. Foreign, ambiguous and active states fail
closed; a proven stale running reviewer is preserved for new-daemon
reconciliation. Replacement preserves a verified prior bundle plus applicable
state/data and leaves the new bundle stopped for post-install gates.
Notarization and a distribution installer are deliberately absent.

## Gateway and adapter

The adapter accepts target `dcp-lab` with no profile and a one-line prompt of at
most 512 UTF-8 bytes. It proves the repository root, marker, baseline, no
remotes and that every linked worktree is under DCP data. Its only second mode
requires exact `dcp-review-lab`, explicit `synthetic-pr`, a unique 1-16
character lowercase task id and the same bounded prompt. That path proves exact
repo/fetch/push URLs, clean fast-forwarded main, allowed historical/new linked
worktrees, private/common Git dirs and one typed Codex worker/reviewer config;
all unknown or ambiguous values fail closed.

Under one submission lock, the gateway either reuses one proven ready exact app
or opens its absolute bundle path from a completely stopped state. Readiness
binds app PID/instance/bundle to daemon PID/executable/service/port/run-file and
browser socket. Stale, foreign, duplicate, unhealthy, port-conflicting or
incomplete facts fail closed and are preserved as evidence. Concurrent submits
therefore produce one app, one daemon and distinct native sessions without
duplicate spawn.

The daemon produces its exact `dcp-orchestrator-daemon` service namespace in
both authenticated status and the run-file. The gateway requires both facts to
agree; it neither infers nor supplies a missing identity.

The adapter registers/verifies the selected exact native project, installs its
strict target-specific policy and calls one `spawn --kind worker --harness
codex`. It owns
no registry, database, scheduler, queue, watcher, retry, model loop or reverse
delivery.

## I8 qualification

Model-free gates cover the exact fork/source boundary and I8 parity, worker
isolation/outcomes, gateway cold/warm/concurrent behavior, fail-closed
identities, application Info.plist/signature/architecture, embedded daemon, license/notice and
telemetry/updater/crash artifact absence. The completed bounded live
qualification used the owner-raised cumulative allowance of five short
marker-only model calls with no automatic retry: one preserved diagnostic
stop-gate followed by these four qualified calls:

1. cold submit while the exact app is off;
2. warm submit while the same app and daemon remain alive;
3. two simultaneous minimal submits.

The cold `dcp-lab-2`, warm `dcp-lab-3` and concurrent `dcp-lab-4`/`dcp-lab-5`
sessions each created its exact isolated marker and reached Idle with no
duplicates. One exact app and daemon remained alive, the UI showed the tasks,
the child connection variables were absent and updater/telemetry/external
network gates were clean. Minimal redacted evidence stays outside Git. Earlier
I7 evidence is immutable diagnostic input and is not deleted or changed.

## I11 qualification

I11 adds migration 0048 to the existing `ao.db`; it does not create a second
database, service, registry, scheduler or polling loop. Store/service/API tests
cover fresh and existing-I8 databases, atomic submit/event writes, equal and
conflicting idempotency, target validation, monotonic events, stale revision
rejection and restart persistence. Generated SQL/OpenAPI/TypeScript artifacts
reproduce cleanly. UI tests cover one stable synthetic SUBMITTED card and the
absence of manual Orchestrator buttons/commands while programmatic backend
capability remains available.

An isolated packaged arm64 proof blocked the real Codex executable and used
only loopback task APIs. It proved one 201 submit, one equal 200 replay with the
same task id and exactly one event, restart persistence, no process/model call,
and compatibility with existing sessions. The exact prior I10 daemon reopened
the migration-48 database and the I11 daemon then reread the same task, proving
the additive schema does not require an unsafe down migration. I11 consumed
zero model calls.

## I12 qualification

Fork PR [#3](https://github.com/orenvlad-ai/dcp-orchestrator/pull/3) established
the I12 reviewer contour. Follow-up PR
[#4](https://github.com/orenvlad-ai/dcp-orchestrator/pull/4) added bounded
preserved-worktree recovery, and PR
[#5](https://github.com/orenvlad-ai/dcp-orchestrator/pull/5) closes its stock
SCM event-delivery gap. PR
[#6](https://github.com/orenvlad-ai/dcp-orchestrator/pull/6) restored the
packaged stock verdict callback. PR
[#7](https://github.com/orenvlad-ai/dcp-orchestrator/pull/7) removes model
command choice from that success path. PR
[#8](https://github.com/orenvlad-ai/dcp-orchestrator/pull/8) closes the worker's
installed-Codex argv blocker at immutable commit
`5ab85f0010bd120728b8514c84f1fe41fac0ba70`, tree
`6c0b7fadb5a4525a822b371b10fc2069fc9afa4c`. It replaces only the unsupported
exec-level approval argument with the supported config override and explicit
workspace-write sandbox, while unknown permission modes fail closed. The
follow-up [#9](https://github.com/orenvlad-ai/dcp-orchestrator/pull/9), merge
`be3239808c88dff1a0f2a7801fedfb73c61ed789`, tree
`7fdd7db08e8c37f1fe783538cfea3cba2c55441a`, derives and verifies only the
concrete linked worktree gitdir/common `.git` roots needed by Git, grants them
through repeated `--add-dir`, and removes those roots from the read-only
reviewer command. Invalid layouts fail before launch. The
structured reviewer uses Codex-native output plus one trusted
identity/current-head-bound existing `ReviewRun` update; the private
exact-binary alias remains compatibility-only. No network access, credentials,
global PATH state, migration or persistence authority is added.

Managed-fork PR [#10](https://github.com/orenvlad-ai/dcp-orchestrator/pull/10)
adds the exact review-lab terminal claim/merge transaction and fail-closed
identity/provider gates. PR
[#11](https://github.com/orenvlad-ai/dcp-orchestrator/pull/11) makes the stock
CLI preserve the explicit typed Codex reviewer instead of silently discarding
it. PR [#12](https://github.com/orenvlad-ai/dcp-orchestrator/pull/12) fits the
exact `DCP:<task-id>` identity inside the native card-name limit, and PR
[#13](https://github.com/orenvlad-ai/dcp-orchestrator/pull/13) removes the
contradictory prohibition on the one required ready PR while continuing to
forbid extras. PR [#14](https://github.com/orenvlad-ai/dcp-orchestrator/pull/14)
adds the exact typed worker-network profile while keeping cards 1-6 and every
reviewer network-disabled. PR
[#15](https://github.com/orenvlad-ai/dcp-orchestrator/pull/15) preserves that
typed marker through the strict CLI config mirror after one canonical submit
failed closed before spawn or model launch. PR
[#16](https://github.com/orenvlad-ai/dcp-orchestrator/pull/16) aligns terminal
eligibility with the actual native card 7+ prefix and typed marker. PR
[#17](https://github.com/orenvlad-ai/dcp-orchestrator/pull/17) handles the exact
stock-native paired absence of session diff-base fields while binding the valid
PR base to clean canonical `main` and `origin/main`. PR
[#18](https://github.com/orenvlad-ai/dcp-orchestrator/pull/18) accepts the stock
provider's known absent-review value `none` while rejecting unknown and blocking
decisions. PR [#19](https://github.com/orenvlad-ai/dcp-orchestrator/pull/19)
requests and preserves exact GraphQL head-repository identity instead of
weakening the terminal gate for a missing fact. PR
[#20](https://github.com/orenvlad-ai/dcp-orchestrator/pull/20) adds the bounded
I13 Stage 1 admission slice. After model-free discovery that pre-stage card 8
and PR #5 were already immutable completed evidence,
[#21](https://github.com/orenvlad-ai/dcp-orchestrator/pull/21) binds the fresh
cohort to cards 9/10 and closes a browser broker cancellation race exposed by
CI. Canary then exposed a false `canonical_main_diverged` incident after the
first merge advanced `origin/main`; [#22](https://github.com/orenvlad-ai/dcp-orchestrator/pull/22)
adds exact fast-forward/merge-tree proof and one startup-only, audit-preserving
model-free recovery. [#23](https://github.com/orenvlad-ai/dcp-orchestrator/pull/23)
implements only the separately reviewed Stage 2 v1 incident, one-shot arbiter
and same-worker repair contour. [#24](https://github.com/orenvlad-ai/dcp-orchestrator/pull/24)
corrects the strict structured rollout-budget configuration and preserves the
first pre-provider rejection in one migration-0053 audit row before re-arming
only the same incident/generation. The current immutable source merge is
`2fbd9bf4789a5b388fb12c58d9347968ed06e6de`, tree
`ada1ccead3e9920bf1e658ac3c136bc61acea6ab`.

Model-free tests cover reviewer
CLI compatibility/read-only policy, eligibility, exact-SHA idempotency and
single-flight, single-use terminated-session observation, exact path/branch
restoration, clean exact-head verification, exact executable identity,
PATH/retired-AO isolation, structured schema and identity validation, atomic
single-winner verdict persistence, duplicate/late/foreign/malformed rejection,
process exit, startup reconciliation, truthful UI projection and unchanged
worker identity/findings delivery. The full serial Go suite,
generated SQL/OpenAPI/TypeScript parity, frontend typecheck, focused renderer
tests, source gates, native package gates and fork CI pass.

The failed I2/I3 runs and `orenvlad-ai/dcp-review-lab#1`, `#2` and `#3` remain
immutable negative audit evidence and are never changed, reused, retried or
merged. `dcp-review-lab-4` separately preserves the 16,222-token worker call
that reached model session `019fece4-e13f-79b1-b3af-c0e6392ebdb5` but left
only an untracked marker when Git metadata remained outside the sandbox; it has
no commit, PR or reviewer run. Card 6 consumed the first call from the original
three-worker allowance. Card 7 consumed the second and created exact head
`f10c825fced998c01a3e83ef4073451c3bd2e4a3` plus ready PR #4; the sole automatic
reviewer approved that head with no findings and the named check is green with
current CLEAN/MERGEABLE facts. The automatic reviewer allowance is consumed.
One unused emergency worker-call ceiling remains, but no new card or model call
is used for this approved run. Model-free terminal reconciliation merged PR #4
once at `202ca32a0e8d563c6c478d094073246383720e5d`; the same existing card/run
projects `Merged` before and after controlled restart with one review, one run,
seven cards and no card 8. Minimal exact-SHA evidence remains below the lab
root rather than in Git.

The first fresh terminal attempt is preserved as `dcp-review-lab-6`: native
Codex session `019fefec-83f2-7090-a4e6-fcda57f262f9` used 29,309 tokens and
created local commit `c92bbef`, but two bounded push attempts both failed
because the worker sandbox could not resolve GitHub. It created no remote
branch, PR or reviewer run. The card is not resumed or reused; after the
distinct model-free PR #14 fix, card 7 completed the successful worker path.

Card `dcp-review-lab-7` used worker session
`019ff01e-9d97-7cf3-b241-4d6820fe26e1` and 36,386 tokens. The only reviewer,
session `019ff01f-9805-7c22-9bd4-54d53e99be5d`, used 10,258 tokens and stored
approved/no-findings run `28025930-ecc0-481e-a13b-9fb5a5a14a94`. PR #16 fixes
the model-free terminal profile mismatch, PR #17 fixes the stock-native missing
base metadata case and PR #18 fixes the adapter's known `none` review decision
without repeating either model call. PR #19 supplies the exact missing
head-repository provider fact; null/unknown remains fail-closed.

The exact installed receipt is fork `b23b519cd532555c203863586032d157fc1c8c13`,
daemon SHA-256 `c9d59d2c2a8453d278ebc45a5a4872e8f96d35fd9ad29cad6cd109a0043cc6a1`
and asar SHA-256 `a1206d002b16a8d9a3cb4485c4522b4fe685fdb102840d1d96530a4f11a4ff90`,
installed at `2026-08-11T14:26:15Z`. The bounded I13 Stage 1 qualification used
cards 9/10, two workers and two reviewers only. Durable admission order was
card 10 / PR #6 / head `3afd3d4cbcc2fe4a6bf2fde3e747213e5c874d53`, then
card 9 / PR #7 / head `649c60cbe6c8542f0a3d20b05b11ae5c54a79263`.
They merged strictly once and sequentially at
`5e65c167d8d9d36d70c89fc8e9b5b07497905645` and
`dbaf01b05e85ffffa4c843a905e2fe5229eaf0da`. The second row's false
`canonical_main_diverged` packet remains retained evidence; exact ancestry and
clean merge-tree proof recovered it without a worker/reviewer wake. Two
controlled restarts preserved all admission identities and counts. PRs
#1/#2/#3 remain open and unchanged; the synthetic repository reports zero
deployments, so no deploy fact is invented after terminal `Merged`.

## Development and delivery

One curator dispatches one direct executor from current `origin/main`. The
executor qualifies before opening one ready PR, uses ordinary CI/review/merge,
fast-forwards the clean canonical checkout, rebuilds/installs from exact merged
main and runs a model-free post-install identity/readiness smoke. Technical
completion never means owner acceptance.

## Owner-approved I13 staged implementation

The owner approved one autonomous two-stage block on 2026-08-11. Stage 1 is now
technically complete and extends only the synthetic `dcp-review-lab` contour
to two new native task/card identities with independent worker and automatic
review paths plus one mechanical serialized admission/terminal-merge line in
the existing daemon and SQLite. The second task must wait durably without a
process, heartbeat, timeout, model poll or token use. Completion of the first
triggers one model-free reconciliation: a fresh compatible candidate proceeds,
ordinary deterministic staleness gets at most one same-worker refresh wake and
fresh exact-head review, and proven ambiguity stores one structured
arbiter-needed packet without launching an arbiter.

The implementation must preserve exact task/card/session/worktree/repository/
PR/head/check/review/admission-generation identity, single ownership, FIFO
order, duplicate rejection and restart recovery. It may add an additive schema
slice to the existing SQLite but no second database, queue service, watcher,
scheduler, heartbeat, general retry loop, UI column, Release Train or real
target. Its live happy-path qualification is bounded to two initial workers and
two reviewers; one additional same-worker wake and fresh reviewer are allowed
only for a deterministically required ordinary refresh.

Stage 2 entry is satisfied by the green Stage 1, independent curator check and
fresh executor. Its bounded event-driven arbiter v1 source for one proven
structured incident has passed the managed-fork flow. The first Stage 2 source
is installed and the exact cards 11/12 incident is frozen; the corrected source
remains build/test input until this immutable correction pin is reviewed,
merged and deterministically installed.

The fresh Stage 2 executor has now frozen the separate reviewed pre-runtime
[arbiter v1 contract](I13_STAGE2_ARBITER_V1_CONTRACT.md). It permits only a
fresh cards 11/12 real-conflict incident, one `gpt-5.6-sol`/`xhigh` arbiter call
under a hard 16,384-token budget and one same-worker repair path or safe stop.
Its complete live ceiling is seven model calls. Cards 11/12 consumed only their
four initial worker/reviewer calls; card 11 merged and card 12 opened the one
exact conflict incident. The first arbiter child stopped during strict local
config parsing before a model/provider request. Correction PRs #137/#24 kept
the same one-call/seven-call ceiling and consumed their one-row audited re-arm.
The corrected launcher passed strict config, but the provider rejected
unsupported root response-schema `oneOf` before model inference or token use.
Contract revision 19 permits one final separately audited same-identity re-arm
only after replacing that composition with required constant/enum fields and
trusted cross-field validation. The live ceiling is unchanged.

The final exact installation ran that one inference. Its artifact selected the
right worker/path but set `maxFreshReviews=0`, so trusted validation rejected it
and no recovery occurred. The exact terminal state and token/restart/duplicate
proof are recorded in
[I13 Stage 2 terminal BLOCKED evidence](I13_STAGE2_BLOCKED_EVIDENCE.md). Stage 2
reached a truthful technical `BLOCKED`; its original one-call budget is
consumed and that evidence stays immutable. On 2026-08-12 the owner authorized
one separately reviewed
[exact-incident successor attempt](I13_STAGE2_ARBITER_SUCCESSOR_CONTRACT.md).
Only that attempt-generation-2 call may continue the same card 12 / PR #9
incident, under a hard 16,384-token budget. The model no longer owns worker or
review ceilings; trusted policy fixes the sole positive path at one same-worker
wake and one fresh review. There is no replacement identity, third arbiter or
general retry loop. Managed-source PR #26 implements only that successor
contract at merge `baac2921a6901e836cbbf3759c3c42f5259ea37c`, tree
`a1ecbb79bd14a48ee270e6ce320633f2227cfe46`; this integration pin does not yet
claim deterministic installation, a successor call or a live result.

The installed successor subsequently used its sole call and returned the exact
approved owner/path, but the trusted evidence allowlist omitted one nested
digest already present in its frozen envelope. The bounded
[exact-result validation recovery](I13_STAGE2_SUCCESSOR_VALIDATION_RECOVERY_CONTRACT.md)
authorizes only a reviewed model-free validation of that unchanged artifact,
with a separate failure audit and zero new model calls. It adds no generic
late-result path and cannot wake a worker before the required decision-boundary
restart. Managed-source PR #27 implements only that recovery at merge
`6f1b5f9828853b6c597d6e6b82fda52ced097b61`, tree
`7cb55d85073af960944a645e2fbe13503e98bf4f`. Exact pin PR #145 then passed its
authorized baseline rerun, merged normally and was deterministically installed.
One model-free replay accepted the unchanged generation-2 result and persisted
one exact decision. At the required restart, the sole card-12 wake failed
before Codex launch because the preserved worker has no restorable
`agent_session_id`; the successor is terminal `failed/repair_launch_failed`
with no new head, reviewer or merge. The second controlled restart was inert.
The complete identity, artifact, counter and token proof is recorded in
[I13 Stage 2 successor terminal evidence](I13_STAGE2_SUCCESSOR_TERMINAL_EVIDENCE.md).
No further wake, model call or replacement identity is authorized.

The owner then separately authorized one governed
[exact card-12 fresh worker-session recovery](I13_STAGE2_CARD12_FRESH_WORKER_RECOVERY_CONTRACT.md).
It preserves the terminal predecessor, accepted decision, consumed wake and
empty native session ids, but permits one separately audited stateless worker
runtime/Codex session for the same card/task/worktree/branch/PR #9 under a hard
16,384-token ceiling. Only its one guarded new head may receive at most one
fresh context-free reviewer and re-enter the existing exact admission/merge
gates. The contract must merge before source work, and source/pin/install/
preflight must complete before live use. There is no new card, task, native
session, worktree, branch, PR, incident, arbiter call/decision, transcript
replay, second worker/reviewer attempt or general retry mechanism.
Managed-source PR #28 implements only that exact recovery at merge
`fbcf4929f9192f7cce9c5097b0bc6a449d28e663`, tree
`2ce917e525690d0cd05e060b552dc8bd072b8a15`. This immutable integration pin
also fences an active exact fresh-worker process during replacement, but does
not claim installation, a recovery worker/reviewer call, a new head or merge.

## I9 target design, not current runtime

I9 records the agreed future [DCP v1 target architecture](TARGET_ARCHITECTURE_V1.md).
It selects the existing DCP daemon and SQLite as the sole future local authority,
GitHub as PR/CI/merge/deploy authority, a model-free Admission Controller inside
the daemon, one GitHub Actions Release Train, event-driven Sol `xhigh`
executor/reviewer/arbiter roles, durable model-free waits, bounded review and
release-incident recovery and a compact DCP UI. I10 separately implemented only
the governed fork boundary. I11 implements durable task identity, SUBMITTED
state/event persistence and display; I12 implements the bounded stock reviewer
and the exact synthetic-PR terminal exception described above. I9 preserves
Symphony only as pinned design provenance, not a
runtime dependency, and reserves a default-off provider-neutral history seam
whose future outputs are compact immutable refs/digests rather than task state,
code or transcripts.

The unimplemented portions remain a documentation contract only. I12 does not
activate task execution, repeated repair cycles, arbiter, admission/release,
action leases or general incident recovery. The qualified I8 curator-to-worker
flow and I11 model-free task surface remain available and unchanged.

## Deliberate non-implementations

The current I12 runtime adds no general task execution, arbiter, DCP multi-role
loop, queue, general retry/recovery policy, monitoring service, real execution
target, `wb-core`, hosted service, production UI, reverse chat delivery,
Telegram, updater, notarization or distribution installer. Upstream
capabilities outside the synthetic session, I11 task foundation and exact I12
reviewer slice remain capabilities, not authorization to exercise them.
