# WBC integration twin current program manifest

manifest_revision: 2026-08-21.1

program_status: Stage 6 BLOCKED before model launch

owner_acceptance: not requested or synthesized

This is the concise authoritative entry for the active WBC integration-twin
program. It replaces duplicated current-state narration in bootstrap documents.
Linked contracts and evidence remain immutable authority for their historical
facts; they do not grant a later mutation unless this manifest and a new owner
task explicitly activate it.

## 1. Owner-approved final outcome

The final machine is one bounded chain:

owner and curator define one bounded task -> one submit -> one stable Task/card
-> immutable exact-head Revisions -> durable Commands -> one bounded Worker ->
exact CI -> one fresh context-free Reviewer -> at most one task-level findings
repair and a new fresh review -> mechanical FIFO Admission -> a simple
repository-owned Release Train -> exact merge -> exact artifact -> applicable
persistent deploy -> verified deployed SHA, health and provenance proof.

A `repo-only` task may terminate at exact release/merge proof. A deployable task
terminates only after verified deploy. Admission decides whether and in what
order an exact reviewed head may release. The Release Train only validates the
exact manifest, merges that exact head, builds/deploys through the target
adapter and publishes immutable proof.

DCP and model roles never merge or deploy and never receive production secrets.
One Task survives head drift, base drift and restart without resubmit or
duplicate model calls. At most three globally active model Actions are allowed;
`workflowActive` is separate from truthful `modelActive`. Human Gate is only a
genuine owner decision. Technical defects fail closed with a named state.
Technical completion never synthesizes owner acceptance.

The integration twin must qualify the real GitHub/PR/CI/review/Admission/
Release-Train/merge/artifact/persistent-Selectel-deploy/provenance path plus
restart/dedupe, global parallelism, conflicts and adversarial cases before WBC
read-only shadow and a separately owner-commanded cutover. Cutover has exactly
one merge/deploy actor: old actor off before new actor on.

Non-goals are direct DCP/model merge or deploy, production-secret access,
automatic owner acceptance, a replacement Task after drift, unbounded repair,
polling as correctness, or keeping two release actors live.

## 2. Authority and surface boundaries

| Surface | Current authority |
| --- | --- |
| Architecture and current program | This manifest plus the DCP-v2 architecture contract |
| Historical stage facts | Linked immutable contracts/evidence only |
| `dev-control-plane` | Documentation and model-free audit changes only for the consolidation task |
| Managed source | Frozen; next work requires a separately launched aggregate source phase |
| Installed app/daemon/SQLite | Observe read-only; no stop/start/restart/write/install/migration |
| Integration-twin repository/Release Train/deploy | Observe read-only; no canary effect or manual mutation |
| WBC / PR #987 / production | Frozen and outside Stage 6 continuation |
| Selectel/Luchiki | Protected co-tenant boundary; no mutation and no inferred health |

Capability qualification never broadens owner authority. Source, pin/install,
runtime, submit, provider and production gates remain independent.

## 3. Exact current checkpoint

The 2026-08-21 machine and GitHub readback established:

| Fact | Exact value |
| --- | --- |
| task_id | `dcp-v2-twin-canary-v1` |
| Task state/revision | `worker_queued` / `1` |
| Revision | `v2-13f81f321f99d1117dc931419e0bea3945ee35a5` |
| Command | `v2-e028f779a18417e990911057f7db7c666f7487ca`, `worker.execute/v1`, `leased` |
| Worker Action | `v2-40f87d048813533daa1108b4316c09139acf0a8f`, `launching`, slot `1`, no runtime id |
| v2 rows | Task/Revision/Command/Action `1/1/1/1`; Admission/Incident/ExternalEvent/Result `0/0/0/0` |
| Native identity | card `1`; session `dcp-wbc-integration-lab-1`; task reserved |
| Native model boundary | one canary model Action `queued`; `74` total legacy model Actions, `0` active; no model process/runtime |
| SQLite/runtime | schema `85`, integrity `ok`; existing app/daemon ready at readback |
| Installed source/tree | `11401ff6eadb80fd87e48229fb8c5458095a63b1` / `91bf6e25ec1b0e0f971ad36f7b80272aded2482c` |
| Recovery install | backup `i12-20260821T043432Z`; receipt SHA-256 `098056d800d41f666708b7697d6ccef9f3b5cd2e077a939d89dcf0b1f35767e2` |
| Lab base/main | `375b9b2d0b4c2fce6f2c417850553f79e24a0d92` |
| Lab canary effect | no PR, check, review, Admission manifest, Release Train run, merge, artifact, deploy or result |
| WBC predecessor | PR #987 open at `26044c696651ce5873748ec3f920d40e77c5686c`, `BEHIND`, no release labels |

The receipt above is the machine-computed value; an earlier dispatch
transcription differed and is not authority. Runtime readiness is a dated
observation, not a standing claim or permission to control the process. The
Luchiki co-tenant was not probed during this documentation pass; its protected
frozen boundary is inherited from immutable Stage 5 evidence, not synthesized
as current health.

Exactly one durable Stage 6 Task exists. A second submit, equal replay intended
as recovery, replacement identity, second initial Worker or manual provider
effect is prohibited.

## 4. Program stage projection

| Stage | Status | Meaning |
| --- | --- | --- |
| 1 | COMPLETE | DCP-v2 architecture recorded; historical immutable gate |
| 2 | COMPLETE | persistent integration cell and real deploy smoke proven |
| 3 | COMPLETE | model-free positive, negative, replay and drift matrix proven |
| 4 | COMPLETE | provider-neutral core source merged |
| 5 | COMPLETE | adapter, issuer handoff, activation, install and stopped preflight proven |
| 6 | BLOCKED | sole Task preserved; recovery installed; blocked before model launch |
| 7 | NOT STARTED | independent full twin qualification remains fenced |
| 8 | NOT STARTED | WBC read-only shadow requires separate authority after Stage 7 |
| 9 | NOT STARTED | owner-commanded cutover requires old actor off before new actor on |

`COMPLETE` is technical evidence, never owner acceptance.

## 5. Latest proven blockers

The single recovery install completed the schema-85/native-shell compatibility
change, then the same durable Command stopped before model launch on two
independent defects:

1. Prompt identity: the DCP-v2 policy service builds `DCP live-runtime task …`
   while the legacy session-manager reservation validator expects
   `DCP synthetic task …`; the exact reserved spawn envelope therefore fails
   as `reserved command identity drift`.
2. UI truth: the DCP-v2 projection treats a `launching` Action as
   `modelActive=true` even when the runtime id is empty, no model process exists
   and the native model Action is only `queued`. `workflowActive` is truthful;
   `modelActive` is not.

These defects and the tactic below become current repository authority only
when the consolidation PR containing this manifest passes exact-head review,
green baseline, zero unresolved threads and normal merge. They do not
themselves authorize implementation or live continuation.

## 6. Aggregate anti-cycle tactic

Do not authorize another one-defect/one-PR/one-install loop.

After curator rotation, the next separately launched implementation phase must:

1. freeze the live Task and installed contour;
2. copy an exact disposable schema-85 snapshot and use one managed-source
   worktree;
3. reproduce and close successive local defects across the complete DCP-v2 to
   legacy-native runtime seam in the same working branch, with no PR/install per
   defect;
4. exercise model-free/fake boundaries from the reserved Command through spawn
   envelope, trusted result ingestion, exact CI, fresh review, Admission,
   Release Train/deploy Result projection, restart/dedupe and UI truth;
5. publish one aggregate source package with explicit negative tests and no live
   runtime or provider mutation.

A later, separately authorized phase may perform formal source review, lock,
pin/install and same-identity live continuation. No gate is implicit.

Hard stop: if that aggregate package is installed once and another same-class
pre-model/native-identity predicate appears, stop patching predicates. Simplify
or remove the legacy second-authority bridge before any further live attempt.

## 7. Next separately launched task and success boundary

The next task is source-only aggregate seam closure. It succeeds only when one
working branch and disposable schema-85 fixtures prove, without a real model or
provider write:

- exact same-identity adoption from leased Command through one spawn envelope;
- truthful runtime/model/workflow projection at queued, launching, running and
  terminal states;
- trusted result ingestion and new immutable Revision behavior;
- exact-head CI, fresh review, at most one task-level repair, FIFO Admission and
  Release Train/deploy Result projection;
- restart, duplicate event, duplicate result, head/base drift, conflict and
  stale-fence failures without duplicate model/provider effect;
- one reviewable aggregate source package and no installed-contour change.

It does not succeed by fixing only the prompt or only the UI projection. It
does not authorize pin/install or live continuation.

## 8. Curator rotation bootstrap/readback

A new curator starts here and records one compact checkpoint:

1. Qualify one visible direct executor: task id/title, host, separate clean
   worktree, `approval_policy=never`, unrestricted filesystem, network enabled,
   tool versions and platform approval count `0`. Use no subagent or nested
   executor.
2. Fetch current `origin/main`; read root `AGENTS.md`, current operating
   contract, this manifest, DCP-v2 architecture and only the contract/evidence
   linked to the active stage.
3. Prove read-only that the sole Task/Revision/Command/Action ids and schema-85
   counts still match; verify no second submit, runtime process, Admission,
   Result or canary provider effect appeared.
4. Read back installed source/tree/receipt, current dev-control-plane/lab/WBC
   GitHub state and exact open PR/check/review facts. Do not infer remote host
   health from old evidence.
5. Classify every intended action by surface: docs, managed source, installed
   contour, live SQLite, lab provider, WBC or production. Stop unless the new
   owner task explicitly authorizes that exact surface.
6. For the aggregate source phase, freeze the live identity and work only from
   a disposable exact snapshot. Preserve the hard stop above.
7. Terminal handoff states technical `COMPLETE` or proven `BLOCKED`, lists exact
   identities and validation, names remaining risk and explicitly says owner
   acceptance was not synthesized.

## 9. Authoritative links

- [DCP-v2 architecture](DCP_WBC_INTEGRATION_TWIN_DCP_V2_ARCHITECTURE_CONTRACT.md)
- Stage 2: [contract](DCP_WBC_INTEGRATION_TWIN_STAGE2_SELECTEL_PERSISTENT_CELL_CONTRACT.md),
  [evidence](DCP_WBC_INTEGRATION_TWIN_STAGE2_TERMINAL_EVIDENCE.md)
- Stages 3-4: [contract](DCP_WBC_INTEGRATION_TWIN_STAGE3_4_COMBINED_EXECUTION_CONTRACT.md),
  [Stage 3 evidence](DCP_WBC_INTEGRATION_TWIN_STAGE3_TERMINAL_EVIDENCE.md),
  [Stage 4 evidence](DCP_WBC_INTEGRATION_TWIN_STAGE4_SOURCE_COMPLETE_EVIDENCE.md)
- Stage 5: [contract](DCP_WBC_INTEGRATION_TWIN_STAGE5_INSTALL_ACTIVATION_CONTRACT.md),
  [evidence](DCP_WBC_INTEGRATION_TWIN_STAGE5_TERMINAL_EVIDENCE.md)
- Stage 6 predecessor authority:
  [post-submit native-shell correction contract](DCP_WBC_INTEGRATION_TWIN_STAGE6_POST_SUBMIT_NATIVE_SHELL_CORRECTION_CONTRACT.md)
- Historical WBC predecessor:
  [task-first blocked evidence](DCP_TASK_FIRST_NATIVE_LIFECYCLE_V1_PASS2_BLOCKED_EVIDENCE.md),
  [PR #987 lifecycle evidence](DCP_WB_CORE_CI_TRUTH_LIFECYCLE_UX_V1_TERMINAL_EVIDENCE.md)
- Operational routing:
  [permission routing](DCP_CODEX_EXECUTOR_PERMISSION_ROUTING_CONTRACT.md),
  [direct executor routing](DCP_CODEX_DIRECT_EXECUTOR_ROUTING_CONTRACT.md)
