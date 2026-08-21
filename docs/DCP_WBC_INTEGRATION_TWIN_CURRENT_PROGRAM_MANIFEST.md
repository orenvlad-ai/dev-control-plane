# WBC integration twin current program manifest

manifest_revision: 2026-08-21.2

program_status: Stage 6 aggregate install and same-identity continuation authorized

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
| `dev-control-plane` | One reviewed pin/install-authority package, then at most one terminal evidence package |
| Managed source | Aggregate PR #76 merged and frozen |
| Installed app/daemon/SQLite | Exactly one governed aggregate install, one start and same-identity continuation; no direct SQLite write or migration |
| Integration-twin repository/Release Train/deploy | The same Task may act only through its bounded Worker and repository-owned Release Train; no manual mutation |
| WBC / PR #987 / production | Frozen and outside Stage 6 continuation |
| Selectel/Luchiki | Only the exact integration-lab Release Train may deploy; no manual SSH/service control and no co-tenant mutation |

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
| Aggregate source | PR #76; head `b0c2b6df76adf205229e49c48a1d7277aa7b5059`; merge `d084ae3cf0cb3e5e32ebefa197031c24a2b6392d`; tree `a6e3c3347bbbddd256e9edbfc541f115813249d2` |
| Aggregate source checks/review | workflow `32477135149`, `package` and `source` green; review `4992765757`; zero threads |
| Lab base/main | `375b9b2d0b4c2fce6f2c417850553f79e24a0d92` |
| Lab canary effect | no PR, check, review, Admission manifest, Release Train run, merge, artifact, deploy or result |
| WBC predecessor | PR #987 open at `26044c696651ce5873748ec3f920d40e77c5686c`, `BEHIND`, no release labels |

The receipt above is the machine-computed value; an earlier dispatch
transcription differed and is not authority. Runtime readiness is a dated
observation and must be freshly proven before the explicitly authorized
governed install/start. The Luchiki co-tenant was not probed during this
documentation pass; its protected boundary is inherited from immutable Stage
5 evidence, not synthesized as current health.

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
| 6 | ACTIVE | aggregate source merged; one governed install and same-identity live continuation authorized |
| 7 | NOT STARTED | independent full twin qualification remains fenced |
| 8 | NOT STARTED | WBC read-only shadow requires separate authority after Stage 7 |
| 9 | NOT STARTED | owner-commanded cutover requires old actor off before new actor on |

`COMPLETE` is technical evidence, never owner acceptance.

## 5. Aggregate source closure

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

Managed-source PR #76 reproduced both defects failing-first and closed them as
part of the complete local DCP-v2 to legacy-native seam. The exact package also
covered same-identity native adoption, effect fences, immutable successor
Revisions, result contradiction/dedupe, fresh review, FIFO Admission,
Release-Train proof ingestion, restart, drift, conflict and exhausted-policy
failures with fake/model-free boundaries and zero duplicate effects. Its head,
tree, review, checks and merge are recorded in the checkpoint above and in the
[aggregate continuation contract](DCP_WBC_INTEGRATION_TWIN_STAGE6_AGGREGATE_INSTALL_CONTINUATION_CONTRACT.md).

## 6. Active aggregate install/live authority

Do not return to a one-defect/one-PR/one-install loop. The only active mutation
path is the bounded aggregate continuation contract:

1. merge one reviewed dev-control-plane pin/install-authority package;
2. revalidate the exact predecessor source/tree/receipt, schema-85 identity,
   zero active runtime and zero target provider effect before stop and again
   under the gateway lock;
3. build the exact merged aggregate source and install it exactly once through
   `install-stage6-aggregate`, with recoverable backup and automatic rollback;
4. prove the exact stopped post-install receipt and unchanged sole identity;
5. start once and continue the same Task without submit or replacement through
   its bounded model/CI/review/Admission/Release-Train path;
6. publish at most one terminal evidence-only repository update.

Hard stop: if that aggregate package is installed once and another same-class
pre-model/native-identity predicate appears, stop patching predicates. Simplify
or remove the legacy second-authority bridge before any further live attempt.

## 7. Current success boundary

The source-only aggregate seam closure is complete. Stage 6 continuation now
succeeds only when the one governed installation preserves the same identity
and that Task reaches an unambiguous technical terminal outcome proving:

- exact same-identity adoption from leased Command through one spawn envelope
  with no second submit or duplicate initial model call;
- truthful runtime/model/workflow projection at queued, launching, running and
  terminal states;
- trusted result ingestion and new immutable Revision behavior;
- exact-head CI, fresh review, at most one task-level repair, FIFO Admission and
  Release Train/deploy Result projection;
- trusted immutable release/deploy Result and verified deployed SHA, health and
  provenance when the deployable lab path is reached;
- no duplicate model/provider/merge/deploy effect.

Stage 7, WBC shadow and cutover remain separately fenced. Technical completion
does not synthesize owner acceptance.

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
6. For the active continuation, use only the reviewed aggregate installer,
   exactly one installation attempt and one governed start. Preserve the hard
   stop above.
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
- Stage 6 active authority:
  [aggregate install and same-identity continuation contract](DCP_WBC_INTEGRATION_TWIN_STAGE6_AGGREGATE_INSTALL_CONTINUATION_CONTRACT.md)
- Historical WBC predecessor:
  [task-first blocked evidence](DCP_TASK_FIRST_NATIVE_LIFECYCLE_V1_PASS2_BLOCKED_EVIDENCE.md),
  [PR #987 lifecycle evidence](DCP_WB_CORE_CI_TRUTH_LIFECYCLE_UX_V1_TERMINAL_EVIDENCE.md)
- Operational routing:
  [permission routing](DCP_CODEX_EXECUTOR_PERMISSION_ROUTING_CONTRACT.md),
  [direct executor routing](DCP_CODEX_DIRECT_EXECUTOR_ROUTING_CONTRACT.md)
