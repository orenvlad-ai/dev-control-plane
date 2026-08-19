# WBC integration twin and DCP v2 architecture contract

contract_revision: 2026-08-19.1
contract_status: owner-approved architecture-only; not runtime authority
program_stage: 1 of 9
preferred_future_repository: `orenvlad-ai/dcp-wbc-integration-lab`
external_resources_created_by_this_stage: 0

This contract is the forward architecture authority for a future integration
twin that is deliberately close to the `wb-core` release and deployment
contour while remaining isolated from WBC and production. It also defines the
DCP v2 task-first command model that will drive that twin. This Stage 1 is
documentation and model-free contract validation only. It does not prove that
the twin, DCP v2, Release Train, deployment surface, adapter or any described
runtime exists.

The preferred future repository name is
`orenvlad-ai/dcp-wbc-integration-lab`. This stage does not create that
repository, a deployment destination, an Actions workflow, a branch, a secret,
a DCP task or any other external resource.

Where this contract conflicts with the future-design portions of
[DCP v1 target architecture](TARGET_ARCHITECTURE_V1.md), it supersedes those
portions for the integration-twin and DCP v2 program only. The current
[operating contract](CURRENT_OPERATING_CONTRACT.md), installed predecessor
evidence and target-specific contracts remain authoritative for current state.
This contract grants no present runtime authority and does not repair or
continue the existing WBC canary.

## 1. Purpose and success boundary

The program must prove one coherent path in a non-production environment:

`Task -> immutable exact-head Revision -> durable Command -> bounded model Action -> Admission -> Release/Deployment result`

The twin is not a mocked state machine. Its qualification path uses real Git
refs, pull requests, required GitHub checks, GitHub Actions runs, an actual
merge by the repository-owned Release Train, an immutable artifact built from
the exact merge SHA, and an actual installation and process start in an
isolated lab runtime. The deployed surface must report its exact deployed SHA
and pass health and provenance probes. The payload remains inert and contains
no WBC business behavior or business data.

The program succeeds only when the same reusable Release Train core and DCP v2
state/command protocol have survived independent no-DCP qualification, a
single full DCP canary and the adversarial matrix in this contract. WBC remains
outside the writable contour until a later read-only shadow and a separately
owner-authorized cutover.

The following are invariants, not implementation suggestions:

- DCP SQLite is the sole local task, revision, command, action, admission and
  verified-result authority.
- GitHub is authoritative for repository refs, pull requests, checks, Actions
  runs and merge facts.
- The deployment surface is authoritative for the running service and its
  reported deployed SHA; DCP accepts that fact only through an exact immutable
  Actions proof.
- A terminal, pane, process, runner or daemon instance is a runtime resource,
  never task or workflow authority.
- Every state transition that requires further work atomically persists the
  next durable command in the same SQLite transaction.
- The daemon drains durable commands idempotently on the exact triggering
  event and on startup. It owns no heartbeat, watcher, timer-driven scheduler,
  unbounded poller or blind retry loop.
- A model call exists only as one bounded Action owned by one durable Command.
  Models do not mutate DCP state, admit, merge, deploy or decide whether an
  external proof is true.
- At most three model Actions are globally active. Autonomous CI, Release
  Train and deployment work is represented separately as `workflowActive` and
  consumes no model slot.
- No AI retry exists. One task has one initial worker and one task-level
  bounded repair allowance. Every new exact head requires a fresh review.
- Technical completion never records owner acceptance.

## 2. Predecessor freeze and non-continuation rule

The present WBC canary is immutable predecessor evidence, not migration input
for the twin:

| Fact | Frozen value |
| --- | --- |
| Task / card / native session | `wbc-canary-v1` / `1` / `wb-core-1` |
| Pull request / current canary head | WBC PR #987 / `26044c696651ce5873748ec3f920d40e77c5686c` |
| Exact approved review | `18c54338-df31-4471-a344-4db6648ff4e3` |
| Readmission / admission | generation `1` admitted / admission `32` waiting |
| Database | schema `83`, task revision `23`, SHA-256 `561e6c624aeb5030b3d69dcba1ab2f39222c2b9dd2af16e58c488ad89f518f9b` |
| Model accounting | `73` total / `0` active |
| Runtime | app and daemon stopped |
| Exact blocker | `task_first_startup_admission_continuation_missing` |

The full record remains
[Pass 2 BLOCKED evidence](DCP_TASK_FIRST_NATIVE_LIFECYCLE_V1_PASS2_BLOCKED_EVIDENCE.md).
Every earlier incident, failed action, readmission packet, review, admission,
release observation and receipt also remains immutable.

This contract MUST NOT:

- start or restart the current app/daemon;
- drain, repair, re-arm or otherwise continue admission 32;
- update WBC PR #987, its branch, labels, checks, review or Release Train;
- change schema 83 or the live database;
- reinterpret a terminal/process shell as the missing authority; or
- rewrite the blocker as resolved.

DCP v2 is a forward implementation program. Any later migration or adoption of
predecessor data requires a separate contract and may not be inferred from this
architecture.

## 3. Authority model

| Surface | Owns | Explicitly does not own |
| --- | --- | --- |
| Owner | program authorization, material external-destination choice, credentials/secret purpose, WBC cutover and acceptance | technical task transitions or click-by-click command approval |
| DCP SQLite | Task, immutable Revision, durable Command, bounded Action, incident/Human Gate, FIFO Admission, external observation and verified terminal result | GitHub ref/check/merge truth or running-service truth |
| DCP daemon | atomic state/command transactions, command claims, exact reconciliation and typed adapter invocation | an in-memory queue, policy polling, direct target merge or deploy |
| Model Action | one bounded worker, reviewer, repair or arbiter inference against an immutable input envelope | DCP writes, credentials, admission, release, merge, deploy or proof verification |
| GitHub target repository | refs, PR identity/head/base, required checks and merge fact | DCP task state or model activity |
| Release Train core | exact manifest validation, one exact-head merge attempt, immutable readmission/release proof and adapter dispatch | semantic judgement, a second queue, branch synchronization, review or admission |
| Target deploy adapter | exact-merge artifact build/selection, isolated install/start and target-specific probes | release ordering, admission, semantic decisions or DCP terminalization |
| Lab runtime | actual installed bytes, running service and self-reported deployed SHA | task, revision, command, admission or release authority |
| DCP UI/API | a typed projection of durable and verified facts | an independent lifecycle state or manual bypass |

All identifiers crossing an authority boundary are typed and exact. A display
name, terminal title, branch convention or label alone is never identity.

## 4. DCP v2 durable records

### 4.1 Task

A `Task` is the stable owner-approved identity. It binds at least:

- `taskId`, target spec/version, repository numeric identity, base ref and
  execution profile;
- canonical request and scope digests;
- finite policy budgets, including initial worker count `1`, global model-slot
  participation, task-level repair count `1` and a finite target-pinned
  readmission-generation ceiling;
- current immutable revision reference, durable state revision and terminal
  result reference when present; and
- creation and update timestamps.

Equal submit replay returns the same Task. A conflicting payload under the same
task identity fails before mutation. A Task remains authoritative until exact
profile terminal proof or a typed terminal failure/Human Gate.

### 4.2 Immutable exact-head Revision

A `Revision` is append-only and binds one exact repository snapshot:

- Task id, monotonic revision sequence and revision kind;
- repository/base ref, exact base SHA, branch/ref and exact head SHA;
- predecessor revision id and cause command id;
- PR number when it exists;
- immutable input/evidence digest and creation timestamp.

The initial work-input Revision binds the exact starting base and uses that
same SHA as its exact input head. A successful initial worker atomically
creates a successor worker-output Revision with the new exact head. A bounded
repair or mechanical readmission similarly creates a new successor Revision.
No command or action changes a Revision in place. The Task's current-revision
pointer changes in the same transaction that inserts the successor Revision
and its next Command.

A review, check, admission or release fact is valid only for the Revision and
exact head it names. A new head invalidates prior head-specific review,
required-check and admission eligibility without deleting their evidence.

### 4.3 Durable Command

A `Command` is the only durable request for work. It binds:

- command id and provider-neutral command kind/version;
- Task and input Revision ids;
- canonical payload and prerequisite digests;
- deterministic idempotency key;
- `pending`, `leased`, `succeeded`, `failed`, `superseded` or `cancelled`
  state;
- claim owner/epoch/token, side-effect fence and recovery generation;
- result/evidence digest and timestamps; and
- the exact successor transition allowed by its kind.

There is one uniqueness constraint on the idempotency key and one guarded state
transition per durable Task revision. Equal enqueue is inert. The same key with
a conflicting digest is a technical incident.

### 4.4 Bounded model Action

An `Action` exists only for a model-backed Command and binds one role, model,
reasoning level, token/time budget, immutable input digest, launch fence,
runtime identity and result digest. Its attempt number is always `1` for that
semantic action. A provider request crossing the launch fence consumes the
Action even if the process, provider or result later fails. No automatic
second call is created.

The global slot invariant counts only Actions in exact `launching` or
`running` state. A queued Action has no process and consumes no slot. Every
launching/running Action must have exactly one matching live runtime; every
live model runtime must have exactly one matching active Action. Asymmetry,
duplicates or a fourth active Action fail closed.

### 4.5 Admission

An `Admission` is an immutable FIFO claim candidate for one exact Revision and
head. It binds target, Task, Revision, PR, head, base/main snapshot, required
check, fresh review, sequence, state, lease token and manifest digest.

Only deterministic DCP code enqueues and claims Admission. A model cannot
create or select it. One target/base release line has one durable FIFO order.
An older exact Human Gate or terminal failure may be skipped only by an
explicit typed policy; it is never silently deleted. Head or relevant-main
drift prevents release and creates exact readmission evidence.

### 4.6 Release and Deployment result

A `ReleaseResult` or `DeploymentResult` is an immutable observation imported
from a repository-owned Actions proof and verified against the Task, Revision,
Admission and current GitHub facts. A result never overwrites the manifest or
earlier failure/readmission proof. DCP terminal state points to exactly one
verified result digest.

## 5. Atomic transition and command-outbox law

Every durable transition uses one SQLite transaction with this order:

1. Read and compare the exact Task state revision, current Revision and
   prerequisite evidence.
2. Insert the immutable event/result/incident that justifies the transition.
3. Insert a successor Revision when and only when the repository head changed.
4. Update the Task/Admission state with compare-and-set.
5. Insert the one next durable Command, or record an exact terminal/passive
   state that requires no command.
6. Commit all records together.

A transaction that changes state but omits its required next Command is
invalid. A Command without the state/evidence that authorizes it is also
invalid. This is the DCP v2 correction to the predecessor class represented by
`task_first_startup_admission_continuation_missing`.

The daemon owns one command drain function used by both event handling and
startup:

- event delivery calls the drain after the triggering fact commits;
- startup first reconciles leased commands and exact external effects, then
  drains every eligible `pending` command in durable order;
- equal event or startup replay observes the same command idempotency key and
  does not create new work; and
- passive external wait has a durable Command and `workflowActive=true`, but
  owns no model process, heartbeat or polling loop.

Provider reads are bounded one-shot reconciliation steps caused by an event,
startup or an explicitly authorized operator action. They are not periodic
polling. GitHub delivery identity and payload digest are persisted. An equal
duplicate is inert; the same delivery identity with different bytes is an
incident; an out-of-order event is retained but cannot advance state until its
typed predecessor and exact Revision match.

## 6. Claim, lease, dedupe and crash recovery invariants

1. A Command claim is an atomic `pending -> leased` compare-and-set that writes
   a unique owner epoch/token and the exact input digest.
2. Leases do not depend on a heartbeat. Startup may take over only after it
   proves the prior daemon/runtime is absent or adopts the exact still-live
   model Action. Ambiguous liveness stops.
3. Before any external side effect, the executor writes an immutable effect
   fence and external idempotency key. A crash after the fence is reconciled
   from exact external facts before any continuation.
4. Git pushes use expected-old-head protection; merge uses the exact admitted
   head; Actions proofs bind run id, actor, repository and manifest digest.
5. If the external effect already exists exactly, reconciliation records its
   receipt and advances once. If it contradicts the command, reconciliation
   records an incident. It never repeats the effect blindly.
6. A model Action that crossed its provider fence is never launched again.
   Missing or invalid output is terminal for that Action.
7. A command recovery generation reuses the same command and semantic effect;
   it is not a new model attempt, revision, admission or release request.
8. Completion and enqueue of the next Command are atomic. A crash before the
   commit replays reconciliation; a crash after it sees the committed next
   Command.
9. No task can have two active commands that mutate the same Revision or
   external ref. Cross-task model concurrency is limited by the global three
   slots; release ordering is limited by the one Admission FIFO.
10. Terminal proof, failure and Human Gate are idempotent. Later duplicate or
    stale events remain evidence but cannot reopen them.

## 7. Provider-neutral command set

Command names are logical protocol names. GitHub, local Git, future providers
and target deployment adapters implement typed interfaces behind them without
changing their lifecycle meaning.

| Command kind | Deterministic responsibility | Model Action | Successful next fact |
| --- | --- | --- | --- |
| `worker.execute/v1` | Run the sole initial repository worker from the exact work-input Revision | one worker | new exact-head Revision plus `checks.observe/v1` |
| `checks.observe/v1` | Import configured required-check facts for the current exact head | none | `review.execute/v1` only after exact success |
| `review.execute/v1` | Fresh context-free read-only semantic/security review of one exact head | one reviewer | Admission eligibility or one bounded repair decision |
| `repair.execute/v1` | Apply the Task's sole bounded repository repair to exact findings or an arbiter-authorized conflict | one repair worker | new exact-head Revision plus fresh checks/review |
| `arbiter.execute/v1` | Judge one immutable conflict/ambiguity incident and choose the allowed bounded repair or Human Gate | one arbiter | `repair.execute/v1`, `human_gate.open/v1` or typed terminal stop |
| `human_gate.open/v1` | Persist one exact owner question and freeze automated mutation | none | owner answer only through a separately typed future command |
| `admission.enqueue/v1` | Revalidate exact head/check/review and append one FIFO Admission | none | `release.dispatch/v1` when the lease is eligible |
| `readmission.materialize/v1` | From immutable relevant-main or post-Admission drift proof, mechanically create one same-task successor head or exact conflict incident | none unless later arbiter/repair is authorized | new exact-head Revision; never a second initial worker |
| `release.dispatch/v1` | Publish one exact Admission manifest to the target Release Train | none | durable merge/deploy observation wait |
| `merge.observe/v1` | Verify readmission-required or exact merge proof against GitHub | none | readmission command, repo-only terminal verification or deploy wait |
| `deployment.observe/v1` | Verify artifact, install, running SHA and probe proof | none | terminal-proof verification or typed failure |
| `terminal.verify/v1` | Compare the complete immutable result to Task/Revision/Admission/profile | none | one terminal Task result |

The task-level repair allowance is shared by reviewer findings and
arbiter-authorized conflict repair: at most one `repair.execute/v1` may cross
its model fence for a Task. A second findings/conflict repair request is a
typed terminal stop or Human Gate only when the Human Gate criteria genuinely
apply. Mechanical same-task readmission is not a model repair, but its maximum
generation count is finite and pinned in the target spec before submit.

Required-check failure creates no AI retry. A new provider event may prove the
same check run succeeded only when GitHub's immutable run identity supports
that transition; otherwise the task remains failed/blocked according to its
typed policy. Deployment failure similarly records exact proof and does not
automatically rebuild, redeploy or call a model.

## 8. Reusable mechanical Release Train core

The Release Train is ordinary repository-owned GitHub Actions. It is a
mechanical actor, not a reasoning or orchestration service. One run consumes
one immutable Admission manifest containing at least:

- protocol/target-spec version and manifest digest;
- repository full name and numeric identity, base ref and exact current-main
  snapshot;
- Task and Revision ids;
- PR number, head repository/branch and exact admitted head;
- configured required-check name, exact head, run identity and success result;
- exact review identity/digest and no-findings result;
- Admission id, FIFO sequence and admission digest;
- release profile and adapter contract version when applicable;
- target-spec-pinned Admission issuer/actor and triggering event identity; and
- dispatch timestamp.

The manifest is authoritative only when delivered by the exact issuer/actor
pinned in the target spec and the repository-owned integration seam binds that
issuer, manifest digest and Admission. PR content, a label, a workflow input
from an arbitrary writer or a copied manifest is not Admission authority. The
Stage 2 target spec must pin the concrete GitHub event/dispatch mechanism and
actor identity before the first Release Train run.

The core performs only these steps:

1. Recompute the manifest digest and validate its version and complete fields.
2. Require the triggering event and actor to equal the target-spec-pinned
   Admission issuer; reject PR-authored or foreign dispatch input.
3. Prove the workflow is running in the exact repository and base named by the
   manifest.
4. Read the exact PR and require it open, non-draft and on the named base.
5. Require the current PR head to equal the admitted head.
6. Require current base/main to equal the admitted main snapshot.
7. Require the configured `baseline` check to be successful for the exact
   admitted head. Other workflow jobs are observational.
8. Require the manifest's review and Admission evidence to match the
   repository-owned integration seam.
9. If head or main differs, perform no branch/ref mutation and publish one
   immutable `readmission_required` proof.
10. If every fact matches, merge the exact admitted head once through an
   expected-head GitHub merge operation and publish the exact merge proof.
11. For a deploy profile, pass the exact merge/artifact input to the selected
    target deploy adapter and publish its immutable proof. For repo-only,
    publish the repo-only terminal release proof.

The core MUST NOT:

- make a semantic, risk, conflict or repair decision;
- maintain a second FIFO, priority queue or durable task state;
- auto-sync, rebase, update-branch, force-push or merge current main into the
  admitted branch;
- select another task when a manifest is stale;
- accept a different head because its content looks equivalent;
- bypass the configured required check, fresh review or DCP Admission; or
- expose a DCP/direct merge route for the target repository.

GitHub's native runner queue and a repository/base concurrency group are
execution serialization, not a second policy queue. DCP dispatches only the
eligible FIFO Admission manifest. An equal manifest/run replay yields the same
proof; a conflicting proof for one manifest digest fails closed.

On `readmission_required`, DCP imports the immutable proof and atomically
persists `readmission.materialize/v1`. The DCP target adapter, not Release
Train, may create a conflict-free mechanical two-parent successor whose first
parent is the old admitted head and whose second parent is the exact new main.
It uses expected-old-head protection on the same branch/PR. A conflict produces
an incident without mutation. Every resulting head needs a new configured
check, fresh review, FIFO Admission and new manifest. It never creates a second
initial worker.

## 9. Release Train core versus target deploy adapter

The core is reusable only if target-specific deployment behavior is behind a
versioned adapter interface. The interface has three phases:

| Phase | Core input | Adapter obligation | Core verification |
| --- | --- | --- | --- |
| `artifact` | exact repository and merge SHA | produce or select an immutable artifact whose provenance names that SHA | artifact id/digest, source SHA and builder/run identity |
| `install` | artifact digest plus exact environment/service spec | actually install bytes and start the isolated target service | install receipt, environment and service identity |
| `probe` | running service and expected merge SHA | return health and provenance probes, including service-reported deployed SHA | all required probes succeed and deployed SHA equals merge SHA |

The core does not know how WBC builds or deploys. The integration twin adapter
may use an inert HTTP service; a future WBC adapter may call WBC's canonical
artifact/deploy/verify path. Both return the same typed proof envelope. Adding
WBC later changes target spec and adapter implementation, not the core's
Admission, drift, exact-merge or proof-verification logic.

Target adapter failure cannot cause the core to invent success, select another
artifact or retry automatically. The proof records the exact phase and reason.

## 10. Non-simulated deployment proof

For a deploy profile, merge alone is not terminal. After exact merge:

1. Actions builds or selects an immutable artifact from the exact merge SHA.
2. Artifact provenance binds repository, merge SHA, build/run identity and a
   content digest.
3. A distinct adapter phase installs that exact artifact into an isolated lab
   runtime and starts the named service.
4. The running surface returns its deployed SHA through a provenance endpoint
   or equivalent machine-readable interface.
5. Required health and provenance probes execute against the running service.
6. Actions publishes one immutable proof whose digest covers every field.
7. DCP imports the proof, rereads required GitHub facts and terminalizes only
   after exact comparison with its Task, Revision and Admission.

The immutable deployment proof contains at least:

- protocol and target-spec versions;
- Task id, Revision id and Admission id/sequence/digest;
- repository identity, base, PR number and admitted head;
- exact merge SHA and merge actor;
- artifact id, media/type, source SHA and content digest;
- exact deployed SHA;
- environment and service identifiers;
- each required probe name, target, result and evidence digest;
- Actions workflow/run/job identity and actor;
- build, merge, install, start, probe and publish timestamps; and
- canonical proof digest.

The service-reported deployed SHA, artifact source SHA and merge SHA must be
identical. Missing, duplicated, malformed, foreign, stale or crossed fields
fail closed. DCP does not infer deployment from a green workflow, label,
release, artifact upload or merge alone.

From merge until verified deployment proof, the Task remains nonterminal with
`modelActive=false` and `workflowActive=true`. A terminal deployment failure
is shown as failure only after its exact proof is persisted; no automatic
redeploy follows. Duplicate success/failure delivery is idempotent, while
contradictory results for the same proof identity create an incident.

## 11. Stage 2 deployment-surface recommendation and entry decision

The safest preferred Stage 2 surface is an ephemeral, single-tenant OCI
container on a GitHub-hosted Actions runner:

- build an immutable OCI image or image archive from the exact merge SHA;
- persist its digest as a workflow artifact;
- in a separate deploy job, download that exact artifact, load and run it as a
  real container, then execute health and deployed-SHA probes;
- give it no production route, WBC secret, business data or persistent volume;
  and
- destroy it with the runner after proof publication.

This is a real install/start/probe path while minimizing long-lived
credentials and destination drift. Its limitation is deliberate: the service
is not reachable after the Actions job and therefore proves release mechanics,
not persistent operations.

| Option | Strength | Cost/risk | Recommendation |
| --- | --- | --- | --- |
| GitHub-hosted ephemeral OCI container | no new long-lived host or deploy credential; exact artifact can be installed and probed | short-lived service; weaker persistent-operations fidelity | preferred default for the integration twin |
| Dedicated self-hosted lab VM/runner | persistent service and closer operational fidelity | host hardening, runner trust, lifecycle and credentials become owner obligations | use only if persistent post-run proof is a Stage 2 requirement |
| Managed cloud preview environment | realistic remote deployment and public/controlled endpoint | new vendor destination, billing, secret and egress decisions | defer unless the owner explicitly selects it |

Before Stage 2 creates any repository or destination, the owner must record one
entry decision: accept the ephemeral OCI surface, or select a named isolated
persistent environment with its credential purpose, retention, network and
rollback boundary. The decision also pins environment/service identifiers,
artifact retention and whether post-job reachability is required. No
credential is requested in Stage 1. This is a planned Stage 2 entry choice, not
an architecture blocker.

## 12. Activity and UI truth

`modelActive` is true only when at least one exact bounded Action is launching
or running and has the matching runtime. `workflowActive` is true when the Task
is nonterminal and owns a pending/leased deterministic Command, external CI,
Release Train, readmission, merge or deployment wait/run. Both may be false for
Human Gate, terminal success or terminal failure. `workflowActive` never
consumes a model slot.

The UI/API derives all surfaces from the same typed projection:

- queued/running worker, reviewer, repair and arbiter roles are distinct;
- only a running model Action pulses;
- CI, Admission, readmission, Release Train and deployment waits remain
  visibly workflow-active without implying a model process;
- Human Gate is a steady owner-decision state with the exact question;
- technical failure is distinct from Human Gate;
- `Merged` is not `Deployed`;
- a deploy-profile Task remains active after merge until verified deployment;
- terminal success shows the exact merge, artifact, deployed SHA, environment,
  service and proof digest; and
- stale stock PR text, terminal shell state or late events cannot override the
  durable current Revision/result.

Board, sidebar, detail view, notification text and accessibility output use
this one projection. No manual UI button can create an untyped command or skip
an invariant.

## 13. Qualification matrix

Every case uses real SQLite transactions and, where repository/release/deploy
behavior is under test, real GitHub/Actions and the selected real isolated lab
runtime. Fixtures may create inert source changes and controlled failures, but
may not replace the behavior under qualification with a simulation.

### 13.1 Independent twin qualification without DCP

Before DCP v2 implementation, the future twin repository, Release Train core
and deploy adapter are qualified independently with a fixed model-free
repository harness:

| Case | Required proof |
| --- | --- |
| Valid exact manifest | one exact admitted-head merge, immutable artifact, real install/start, successful health/provenance probes and complete proof |
| Head drift | no merge/ref mutation; one immutable `readmission_required` proof |
| Main drift | no branch update or merge; one immutable `readmission_required` proof |
| Wrong repository/base/PR/check | fail before merge and deploy |
| Duplicate manifest/event | same terminal proof, no second merge/deploy |
| Artifact/deployed-SHA mismatch | no success proof; exact deployment failure |
| Adapter/probe failure | no automatic retry and no false terminal deploy |

The harness supplies an exact Admission manifest through one qualification-only
issuer/actor pinned by the lab target spec; it does not run DCP, read a DCP
database or depend on DCP labels/state. Stage 3 is terminal only when the twin
can prove its release/deploy boundary independently. That qualification issuer
must be disabled and proven unable to dispatch before Stage 5 may pin the DCP
issuer for a future canary; both issuers are never active together.

### 13.2 Single DCP canary

The first DCP submit occurs only in Stage 6. One inert Task must traverse the
complete DCP v2 chain and finish at verified deployment with one Task, bounded
Revisions, one initial worker, fresh exact-head review(s), one Admission per
released Revision, one exact merge and one exact deploy proof. No concurrent
or adversarial tasks are admitted before that terminal result and restart
readback.

### 13.3 Full adversarial qualification

| Case | Required result |
| --- | --- |
| Four Tasks / three slots | exactly three model Actions active at maximum; fourth waits durably with no process/token; later drains once |
| FIFO Admission | release manifests and merges follow durable Admission order despite worker/review completion order |
| Duplicate GitHub delivery | equal delivery is inert across restart; conflicting duplicate is an incident |
| Out-of-order GitHub delivery | fact is retained but cannot cross missing predecessor or wrong Revision |
| Restart at every fence | restart before/after command claim, model fence/result, head creation, check, review, Admission, release dispatch, readmission proof, merge, artifact install and deployment proof creates no duplicate or lost next command |
| Main advance before review | old-head/base evidence is invalidated; same Task reaches a new exact Revision and fresh review under finite policy |
| Main advance after Admission | Release Train performs no sync/merge; immutable readmission proof creates same-task mechanical readmission, fresh check/review/Admission and no second initial worker |
| Readmission replay | equal generation/head is idempotent; crossed generation or exhausted finite ceiling stops |
| Mechanical readmission conflict | no branch mutation; one exact incident and at most one arbiter Action |
| Arbiter repair | one allowed conflict repair creates one new Revision, fresh check/review and re-enters the original task flow; task-level repair budget remains one |
| Human Gate | exact owner question is durable, no automatic mutation proceeds and UI is steady decision state |
| Required CI failure | no review/admission/release, no AI retry and truthful failure/wait semantics |
| Deployment failure | merge remains immutable, no false deployed result, no automatic redeploy; duplicate observation is inert |
| UI truth | `modelActive`/`workflowActive`, role, Revision, Admission, merge and deployment proof match SQLite/GitHub/runtime at every state |

The final adversarial record includes exact row/action/revision/admission counts,
maximum concurrency, GitHub PR/head/check/run/merge identities, artifact and
deploy proofs, restart snapshots and zero duplicate effects.

## 14. Nine execution stages and gates

Stages are sequential. Failure of an entry or terminal gate stops before the
next stage. Stages 1-5 are conservative contour work and MUST create no DCP
submit for the twin. The first such submit is Stage 6.

| Stage | Entry gate | Permitted scope | Terminal/stop gate |
| --- | --- | --- | --- |
| 1. Architecture | owner-authorized docs task and preserved predecessor evidence | this contract, minimal authority indexes and model-free doc audit | ordinary reviewed/green merged docs PR; no runtime or external resource; technical `COMPLETE` is not acceptance |
| 2. Twin + Release Train + real deploy | Stage 1 merged; separate owner authorization; recorded deploy-surface entry decision | create exact lab repository, protections, mechanical core, inert target adapter and real isolated deploy | exact reviewed repo state; one documented target spec; no DCP integration; stop on destination/credential ambiguity |
| 3. Independent no-DCP qualification | Stage 2 exact repo/core/adapter ready | run the fixed model-free manifest matrix without DCP | every §13.1 case proven; no DCP database/task/model use |
| 4. DCP v2 core | Stage 3 green; separate reviewed implementation authority | SQLite Task/Revision/Command/Action/Admission/result protocol, atomic outbox, drain, leases, projections and model-free tests | source reviewed/green with exhaustive transaction/restart proofs; no install, adapter activation or twin submit |
| 5. Adapter, install and preflight | Stage 4 exact source selected by separate pin/install authority | twin provider adapter, deterministic build/install and stopped model-free preflight | exact installed receipt, schema/protocol proof, qualification issuer off, exact DCP issuer pinned, zero twin Task/Action/Admission and stopped/preflight-ready runtime |
| 6. Single DCP canary to deploy | Stage 5 green; owner authorizes one bounded canary; twin and deploy surface unchanged | exactly one inert Task through real PR/CI/review/Admission/RT/merge/artifact/install/probes | one verified deployment proof and restart dedupe; otherwise exact `BLOCKED`/failure; no second submit |
| 7. Full adversarial qualification | Stage 6 terminal success and independent curator check | bounded §13.3 cohort and fault/event/restart injections | complete matrix, exact counts and UI truth; no unresolved incident except intentional Human Gate evidence |
| 8. WBC read-only shadow | Stage 7 green; separate owner authorization; current WBC contract reread | observe WBC PR/check/release/deploy facts and compare projected decisions | zero WBC writes/blocks, bounded report of matches/differences, no actor change |
| 9. Separately authorized WBC cutover | Stage 8 accepted as technical input plus explicit owner command and cutover manifest | one fenced actor handoff and one WBC canary | one actor only, canary exact proof, rollback fence intact; owner acceptance remains separate |

No stage inherits mutation authority merely because the previous stage is
complete. Each repository, runtime, credential, model and production boundary
requires its own explicit entry authority and fresh routing/preflight.

## 15. WBC shadow, cutover and rollback fence

Stage 8 shadow is read-only and non-interfering:

- it may read exact WBC repository, PR, check, Actions, release and deployment
  proofs authorized for comparison;
- it writes no branch, label, check, comment, status, environment, artifact or
  DCP/WBC control fact;
- it does not block or delay the existing WBC actor; and
- disagreement is a report, never an automatic correction.

Stage 9 requires a separate owner command naming the exact WBC target, actor,
canary and rollback boundary. Before cutover, machine proof must show zero
active WBC merge and deploy runs under both old and proposed actors. The old
merge/deploy actor is disabled and its disabled state is verified before the
new actor is enabled. There is never a simultaneous merge window.

After enablement, exactly one bounded WBC canary may run. Success requires the
same exact-head Admission/merge/deployment proof rules. On any ambiguity or
failure, the rollback fence first disables the new actor, proves zero active
new merge/deploy work, and only then may a separately authorized rollback
restore the old actor. No actor handoff guesses whether an in-flight run is
safe. Shadow and cutover grant models no WBC, SSH, secret, production or
business-data authority.

## 16. Security and forbidden surfaces

All model envelopes are repository-only, immutable and least-privilege. They
contain no GitHub write credential, deploy credential, production secret,
business data, prior transcript or control-plane mutation tool. Reviewer and
arbiter are context-free. Release/deploy credentials, if a later stage needs
them, stay in repository/environment-owned Actions boundaries and are never
returned in proof.

This Stage 1 forbids:

- managed `dcp-orchestrator` source/code, source lock/pin, build or install;
- app/daemon start, stop, restart or loopback use;
- SQLite read/write/migration or current-runtime inspection beyond preserved
  documentation;
- creation of the lab repository, branch protection, Actions workflows,
  artifacts, environments, runners or deployment destination;
- DCP submit/card/Command/Action/model call;
- WBC file, PR, branch, label, check, Release Train, deployment, production,
  SSH, secret or business-data mutation;
- cleanup of predecessor worktrees, tasks, incidents or evidence; and
- owner-acceptance synthesis.

An implementation finding that weakens atomic command persistence, exact-head
identity, bounded model work, Release Train non-intelligence, real deployment
proof, actor exclusivity or predecessor immutability is an architecture defect
and stops the applicable later stage. A material external-destination choice
stops at that stage's owner entry decision; it is not silently inferred.

## 17. Stage 1 acceptance

This architecture stage is technically `COMPLETE` only when:

- this contract and the minimal root/current/brief/roadmap/decision indexes are
  internally consistent;
- model-free assertions cover the task/revision/command chain, atomic
  transition-plus-command law, command set, three-slot/activity split,
  Release Train restrictions, real deploy proof, nine stages, predecessor
  blocker and WBC cutover fence;
- repository links, diff hygiene and forbidden-surface checks pass;
- one ordinary ready PR receives exact-head semantic/security review with no
  findings, green `baseline` and zero unresolved threads;
- the PR merges normally and the clean canonical checkout fast-forwards to
  final `origin/main`; and
- terminal reporting records the exact PR/head/review/check/merge/final-main,
  remaining Stage 2 choice and `platform_approval_count=0`.

Completion creates no runtime authority, external destination, DCP submit,
WBC continuation, WBC cutover or owner acceptance.
