# WBC integration twin Stage 6 final viability contract

authority_revision: 2026-08-22.1

technical_status: ACTIVE for one aggregate managed-source correction only; live schema 86 remains stopped and unconsumed

owner_acceptance: not requested or synthesized

## 1. Decision and exact finish line

The owner authorizes one final bounded Stage 6 viability pass on the sole
durable Task `dcp-v2-twin-canary-v1`. This contract is the architecture and
managed-source authority for the first two phases of that pass. It closes the
known blocker
`DCP_V2_PUBLICATION_REVISION_PR_BINDING_MISSING` and every same-class
downstream defect discoverable before the single managed-source pull request.

This contract does not itself authorize an install, SQLite mutation, adoption,
start, model/provider effect, target change, merge, deploy, WBC mutation or
production action. After the one source pull request merges, one separately
reviewed dev-control-plane pin/install/live authority must bind the exact merge
and reprove the frozen checkpoint before any live mutation.

The whole owner pass has exactly two terminal outcomes:

1. exact Stage 6 technical `COMPLETE`, followed by one merged evidence-only
   record; or
2. mandatory final `FREEZE/BLOCKED`, followed by one merged evidence-only
   record.

Stage 7 may become eligible after technical completion but must not start in
this pass. Technical completion never synthesizes owner acceptance.

## 2. Frozen entry identity

All source and later live work must preserve these exact facts:

| Fact | Frozen value |
| --- | --- |
| Task | `dcp-v2-twin-canary-v1` |
| Task Revision | `v2-13f81f321f99d1117dc931419e0bea3945ee35a5` |
| Worker Command | `v2-e028f779a18417e990911057f7db7c666f7487ca` |
| DCP-v2 Worker Action | `v2-40f87d048813533daa1108b4316c09139acf0a8f` |
| DCP-v2 runtime | `78535564-a2bc-478c-80b0-207753f2152c` |
| native Worker Action | `74`, terminal `succeeded` |
| Worker commit | `bebbf8f617f1a6fa0b9e91698fe710fe0a2bad2c` |
| Worker tree | `2fda4cae71976fd701bf3a9ccca4031f7afb630d` |
| installed source | `e9eb18a99db71813ac8c4556a614d6a3ce4108aa` |
| installed source tree | `b4db2b329accc9a93691bda7c306cc864b07ee56` |
| install receipt SHA-256 | `fc8f2a2f6264dc1a3e817e42f124bdbd7040a412eade3fcddf97762f59f214d8` |
| live schema | `86`, stopped |
| adoption state | `adoptionConsumed=false`; direct rows `0/0/0` |
| native session | idle, zero active native model Actions |
| provider state | no branch, PR, successor, publication, Admission, Result or effect |

The immutable Worker-output Revision created by adoption must keep
`PRNumber=0`. A second submit, replacement Task, Worker rerun, manual
publication, replay of an ambiguous effect or substitute identity is
forbidden.

## 3. Bounded repository and pull-request budget

The complete owner pass permits exactly:

1. this one reviewed dev-control-plane architecture/authority pull request;
2. one aggregate `dcp-orchestrator` managed-source pull request;
3. one later reviewed dev-control-plane pin/install/live authority pull
   request;
4. one governed install and forward migration;
5. one same-identity adoption;
6. one governed live continuation;
7. one terminal dev-control-plane evidence-only pull request.

The source pull request may receive at most one substantive findings-repair
round, followed by new exact-head checks and a new fresh context-free review.
A second source pull request, second substantive repair round, second install,
second adoption or second live attempt is forbidden and forces final
`FREEZE/BLOCKED`.

The source work must use a new explicit stable standalone development checkout
outside Codex task and temporary roots, with its own `.git`, clean fresh exact
`origin/main` and no relationship to the permanent PR #77 install-input clone
or any historical executor checkout.

## 4. Schema 87 and immutable provider binding

The one aggregate source package must add exactly one forward migration,
`0087`, from stopped schema `86`. The migration must:

- preserve every frozen schema-86 row, primary key, foreign key, trigger,
  index and integrity invariant;
- extend the Revision kind domain with one new kind, `provider_bound`;
- add the Result artifact-source binding required by section 9;
- be transactionally fail-closed, once-only and safe under restart;
- leave schema `87` with `PRAGMA integrity_check=ok` and zero foreign-key
  violations;
- never rewrite an existing Revision, including the Worker-output Revision;
- reject downgrade, skipped predecessor, equal reapply and a partial schema.

Publication success must atomically do all of the following:

1. validate the claimed publication receipt against the exact publication
   Command fence;
2. finish the publication Command and its effect fence;
3. create exactly one immutable `provider_bound` successor Revision;
4. bind that successor to the same repository, base SHA, branch, exact head
   SHA and tree as its Worker or repair output predecessor;
5. bind the real provider PR number, predecessor Revision and publication cause
   Command on that successor;
6. advance the same Task's current-Revision pointer to the successor;
7. enqueue exactly one `checks.observe/v1` Command against the successor.

The transaction is all-or-nothing. It may not alter the predecessor
Revision's `PRNumber=0`, reuse `repair_output` or `readmission_output`, create a
replacement Task or enqueue checks against the predecessor.

Every later repair publication follows the same rule: the immutable
`repair_output` remains provider-free and publication creates one new
`provider_bound` successor with the real PR. A readmission output remains a
distinct immutable `readmission_output`; it is not repurposed as publication
state.

Equal receipt replay and restart are inert. A crossed PR, repository, base,
branch, head, tree, predecessor, cause Command, fence, external id or receipt
digest must fail without mutation. One publication Command can own at most one
successor and one successor can have exactly one publication cause.

## 5. Durable lineage and local worktree recovery

A provider-bound or readmission Revision is not itself produced by a model
Action. The managed service therefore must not assume that the current
Revision's cause Command owns a model Action or worktree receipt.

Any later repair or readmission must resolve its execution worktree by walking
the immutable predecessor-Revision chain back to the exact terminal model
receipt that owns the original standalone worktree. The resolver must:

- require strictly decreasing immutable Revision sequence and an acyclic,
  single-parent chain;
- validate repository, base, branch, head and tree continuity at every edge;
- end at exactly one successful model Action receipt whose stable standalone
  worktree is clean, local and contains the expected Git object;
- reject missing, multiple, crossed, dirty, symlinked, task-root, temporary or
  foreign worktrees;
- keep the local path private and out of public API, evidence and provider
  payloads.

Restart may rediscover this same lineage but may not create a new worktree,
Revision, Command or model Action merely to recover it.

Readmission materialization must be deterministic before any provider fence:
commit content, parent, tree, message, author and committer identity and time
derive only from immutable Command inputs. The expected-old-head push and its
reconciliation must accept one equal remote result and reject a crossed or
multiple result. A crash may leave an unreferenced local Git object, but replay
must calculate the same commit and must not duplicate a provider effect.

## 6. Provider-effect and command laws

Every provider-writing Command, including `publication/v1` and
`admission.enqueue/v1`, requires a durable effect fence before the effect. The
provider request must be deterministic from immutable Command input, and the
same Command must reconcile after a crash by exact readback rather than blind
retry.

Admission enqueue includes the exact context-free approving review publication
when that review is a provider effect. Its fence binds repository, PR,
Revision, head, base, required-check digest, findings digest, review body and
actor boundary. Reconciliation must find or create exactly one matching review
and then atomically create exactly one Admission and next Command. Zero after a
confirmed failed attempt, more than one match, an unexpected actor/body/head or
an ambiguous provider response fails closed without a replay.

No polling establishes correctness. Bounded waits may discover an external
fact; durable readback and exact comparison establish it.

## 7. Exact checks, review, repair and Admission

The downstream machine must enforce all of these bindings:

- exact checks facts have the current provider-bound Revision's non-zero PR,
  head SHA, base SHA, configured required-check set and passing result;
- a fresh Reviewer Action runs context-free against that exact head and no
  stale review carries after head drift;
- findings may create at most one task-level repair model Action; its new head
  receives new exact checks and a fresh review;
- unresolved review threads are zero before Admission;
- Admission is mechanical FIFO and binds the same Task, current Revision,
  repository, non-zero PR, exact head, base, check digest and review digest;
- manifest construction revalidates every one of those fields from immutable
  state and refuses a stale or crossed Admission;
- a base-drift readmission preserves the same Task, creates one immutable
  readmission Revision and returns through exact checks, fresh review and FIFO
  Admission without a second submit;
- Human Gate represents only a real owner decision; technical contradictions
  become named failed state, never a Human Gate.

The normal no-findings path, the single allowed repair path, conflicts,
readmission, Human Gate and legacy ordinary workflows must all remain distinct
and model-free testable.

## 8. Release Train ownership and exact proof schema

Only the protected integration-lab repository-owned Release Train may merge,
build, publish the artifact and perform the persistent Selectel deployment.
DCP and model roles never merge or deploy, never receive deployment or
production secrets and never use manual SSH or provider-side substitution.

The adapter must decode and validate the complete release proof without
discarding fields before digest verification. The exact proof includes:

- protocol, target specification and qualification case;
- Task, Revision and Admission identity, sequence and Admission digest;
- repository, repository id, base SHA, PR number, head SHA, check and review
  digests;
- merge SHA and merge actor;
- artifact id, media type, source SHA and digest;
- deployed SHA, environment and service;
- the exact single merge, artifact and deploy effect cardinalities;
- health, provenance and anti-co-tenant probes;
- workflow, run id, run attempt, job and dispatch actor;
- ordered immutable timestamps and the proof digest.

Unknown, duplicate, missing, null, type-drifted or crossed fields fail closed.
The proof digest is computed from the complete canonical proof object, never a
truncated decoder projection.

## 9. Artifact, merge, deploy and Result identity

Schema `87`, domain, store, services and projections must persist the artifact
source SHA. Terminal success requires:

`artifact_source_sha == merge_sha == deployed_sha`

as well as the exact artifact digest, canonical repository/environment/service,
health and provenance proof, one immutable release Result and one immutable
deployment Result. Each Result is caused by one exact Command and binds the
same Task, Revision, Admission and release proof. Equal proof replay is inert;
crossed proof, duplicate Result, duplicate effect, SHA mismatch or missing
provenance fails without mutation.

The terminal verifier must read and compare the complete durable chain, not
infer success from a projected state or external workflow conclusion.

## 10. Projection and API truth

The current Revision pointer may advance from Worker/repair output to
`provider_bound` and later to `readmission_output`. API and UI projections must
continue to show one Task/card and must preserve:

- `workflowActive=true` while durable non-model workflow remains;
- `modelActive=true` only for a genuinely active DCP-v2 model Action/runtime;
- globally at most three active model Actions across four Task contention;
- no slot held by publication, checks, review publication, Admission, release,
  deployment or completed model work;
- no private worktree path, provider secret or deployment secret;
- exact failure, conflict and Human Gate state without optimistic fallback.

Generated SQL, API and frontend artifacts must be regenerated from their
authoritative inputs where applicable. Backend, frontend and compatibility
tests must cover the new Revision kind and artifact-source field without
weakening legacy ordinary workflows.

## 11. Required disposable schema-86 proof

Before publishing the one source pull request, one exact disposable copy of the
stopped live schema-86 database and frozen bundle/receipt must prove the entire
remaining Stage 6 chain with typed fake model/provider/Release Train receipts.
The real stopped database, installed bundle and receipt must remain byte- and
row-identical.

The matrix must prove, in one source package:

1. migrate `86 -> 87` once while preserving all frozen rows, integrity and
   foreign keys;
2. adopt the exact frozen terminal Worker receipt once without model/provider
   effect, creating one Worker-output Revision and one publication Command;
3. publish once into one provider-bound Revision with the real PR and one
   checks Command in a single transaction;
4. make equal replay/restart inert and reject every crossed PR, head, commit,
   tree, Revision, fence and result without mutation;
5. traverse checks, fresh Reviewer, optional single repair, new exact head,
   fresh review, FIFO Admission, Release Train proof ingestion, exact merge,
   artifact, deploy Results and truthful terminal projection;
6. restart before and after every claim, effect, receipt and transition without
   duplicate Command, Revision, model Action, publication, review, Admission,
   merge, artifact, deploy or Result;
7. prove four Tasks contending for three slots, truthful `modelActive` and
   `workflowActive`, conflicts, readmission, Human Gate and legacy workflows;
8. pass generators, provenance/security/absence gates, serial tests, build,
   vet, focused race suites, frontend typecheck/tests and package checks.

The test matrix must include the actual integration-lab proof shape, not a
reduced fixture.

## 12. Source pull-request gates

The aggregate managed-source pull request may publish only after the complete
local matrix passes and every locally found same-class defect is included. It
must be ready for review, not draft, and must have:

- exact-head source and package CI green;
- one fresh context-free semantic/security review bound to that head;
- zero unresolved review threads;
- normal merge.

If the head changes after findings repair, all exact-head checks and the fresh
review must be repeated. A material review finding that changes the final
machine invariants or requires a different architecture forces final
`FREEZE/BLOCKED` rather than an improvised source change.

Source merge alone grants no install or live authority.

## 13. Later pin/install/live boundary

After the source merge, the one later authority pull request must bind its
exact merge commit/tree to the installed predecessor, schema `86`, receipt,
frozen Task chain, native Action and Worker output. It must require a new
permanent standalone clean detached install-source clone and extend the
stable-source guard with exact Git/filesystem identity, staged digest-bound
source/Worker/signed-artifact bytes, one-use install identity and equal-rerun
rejection.

Only that merged authority may permit one backup, one install/migration `0087`,
automatic rollback on post-stop failure, stopped schema-87 preflight, one new
unconsumed digest-bound adoption input, one adoption, one governed start, the
exact lab provider path and one bounded post-terminal restart/dedupe readback.
It must continue to forbid resubmit, Worker rerun, manual publication,
manual merge/deploy/SSH, a second attempt, WBC and production.

## 14. Mandatory final freeze

After the single source pull request merges, any of the following immediately
ends the pass as final `FREEZE/BLOCKED`:

- another fundamental Task/Revision/Command lifecycle defect;
- need for a second managed-source pull request or second installation;
- state not covered by the complete disposable matrix;
- duplicate Task, model Action, publication, review, Admission, merge, artifact,
  deploy or Result;
- ambiguous provider effect;
- migration, install, adoption or live continuation that cannot complete under
  the one-use contract.

There is no “one more small fix” after that gate. Failure of the one governed
install requires automatic rollback and terminal evidence; it is never retried.
Failed or ambiguous adoption and live continuation are never replayed.

## 15. Global absence and security gates

Every phase must prove absence of:

- a second Task submit or replacement identity;
- a Worker rerun or initial-model duplicate;
- legacy lifecycle dual-write or a restored second-authority bridge;
- in-place Revision mutation;
- provider or deployment secrets in DCP/model input, logs, API or evidence;
- DCP/model merge or deploy authority;
- manual canary branch/PR, manual lab merge/deploy or SSH;
- mutation of WBC PR #987, the WBC repository, production, cutover or the
  protected co-tenant;
- Stage 7 work or synthesized owner acceptance.

This contract supersedes the old “no managed-source correction” fence only for
the single aggregate source package described here. All historical spent
install/start authority remains spent, and the stopped live contour remains
immutable until the later pin/install/live authority is reviewed and merged.
