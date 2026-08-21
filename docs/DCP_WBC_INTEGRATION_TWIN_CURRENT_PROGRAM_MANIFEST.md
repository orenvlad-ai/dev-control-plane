# WBC integration twin current program manifest

manifest_revision: 2026-08-21.4

program_status: Stage 6 BLOCKED; direct DCP-v2 model authority selected for source-only replacement

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
| Architecture and current program | This manifest, the DCP-v2 architecture contract and the Stage 6 direct model authority contract |
| Historical stage facts | Linked immutable contracts/evidence only |
| `dev-control-plane` | One architecture/authority PR and one later terminal source-evidence PR; no runtime authority |
| Managed source | One direct-runner PR from fresh main after the architecture merge; no install authority |
| Installed app/daemon/SQLite | The one aggregate install and one start are spent; no restart, reinstall, direct SQLite write or migration |
| Integration-twin repository/Release Train/deploy | Frozen after the Worker produced only a local commit; no manual provider mutation |
| WBC / PR #987 / production | Frozen and outside Stage 6 continuation |
| Selectel/Luchiki | Only the exact integration-lab Release Train may deploy; no manual SSH/service control and no co-tenant mutation |

Capability qualification never broadens owner authority. Source, pin/install,
runtime, submit, provider and production gates remain independent.

## 3. Exact current checkpoint

The 2026-08-21 machine and GitHub readback established:

| Fact | Exact value |
| --- | --- |
| task_id | `dcp-v2-twin-canary-v1` |
| Task state/revision | `worker_queued` / `1`; stale after native Worker success |
| Revision | `v2-13f81f321f99d1117dc931419e0bea3945ee35a5` |
| Command | `v2-e028f779a18417e990911057f7db7c666f7487ca`, `worker.execute/v1`, still `leased` |
| Worker Action | `v2-40f87d048813533daa1108b4316c09139acf0a8f`, falsely still `running`, slot `1`, runtime `78535564-a2bc-478c-80b0-207753f2152c` after native success |
| v2 rows | Task/Revision/Command/Action `1/1/1/1`; Admission/Incident/ExternalEvent/Result `0/0/0/0` |
| Native identity | card `1`; session `dcp-wbc-integration-lab-1` idle; policy task `ci_waiting`, revision `4` |
| Native model boundary | canary Action `dcp-model-dcp-v2-twin-canary-v1-worker-1` succeeded; `74` total legacy model Actions, `0` active |
| SQLite/runtime | schema `85`; app/daemon ready; native session has no runtime launch id |
| Installed source/tree | `d084ae3cf0cb3e5e32ebefa197031c24a2b6392d` / `a6e3c3347bbbddd256e9edbfc541f115813249d2` |
| Aggregate predecessor | `11401ff6eadb80fd87e48229fb8c5458095a63b1` / `91bf6e25ec1b0e0f971ad36f7b80272aded2482c` |
| Aggregate install | exactly one attempt; backup `i12-20260821T120041Z`; receipt SHA-256 `19550a9f02b14f13be8a80214529025fd6d4fe7dc8e5bd12c5eaa1a47dd54b0c` |
| Aggregate source | PR #76; head `b0c2b6df76adf205229e49c48a1d7277aa7b5059`; merge `d084ae3cf0cb3e5e32ebefa197031c24a2b6392d`; tree `a6e3c3347bbbddd256e9edbfc541f115813249d2` |
| Aggregate source checks/review | workflow `32477135149`, `package` and `source` green; review `4992765757`; zero threads |
| Lab base/main | `375b9b2d0b4c2fce6f2c417850553f79e24a0d92` |
| Lab Worker output | local commit `bebbf8f617f1a6fa0b9e91698fe710fe0a2bad2c`, tree `2fda4cae71976fd701bf3a9ccca4031f7afb630d`; no remote branch or PR |
| Lab canary provider effect | no check, review, Admission manifest, Release Train run, merge, artifact, deploy or Result |
| WBC predecessor | PR #987 open at `26044c696651ce5873748ec3f920d40e77c5686c`, `BEHIND`, no release labels |

The aggregate receipt above is machine-computed. Runtime readiness is a dated
observation, not authority for another start. The Luchiki co-tenant was not
probed during this continuation; its protected boundary is inherited from
immutable Stage 5 evidence, not synthesized as current health.

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
| 6 | BLOCKED | the one install/start is spent; native success did not reconcile DCP-v2 Action/Task runtime truth |
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

## 6. Spent aggregate install/live authority

The bounded aggregate continuation completed its authorized source, pin,
installation and one-start steps:

1. pin/install-authority PR #257 merged with exact review and baseline;
2. preflight proved the predecessor source/tree/receipt, schema-85 identity,
   zero active runtime and zero target provider effect;
3. `install-stage6-aggregate` ran exactly once, created the recoverable backup
   and installed the exact merged aggregate source;
4. stopped preflight proved the new receipt and unchanged sole identity;
5. one governed start adopted the same Command and native Action without
   resubmit or replacement;
6. the native Worker succeeded, but the DCP-v2 Action/Task did not consume that
   terminal fact and remained falsely active.

The mandatory hard stop is now active. Do not patch, restart, retry, reinstall,
publish the local canary branch manually or create a substitute identity. The
legacy second-authority bridge must be simplified or removed under separate
owner architecture/source authority before any further live attempt.

## 7. Exact technical blocker and next boundary

The native Worker Action succeeded and released its slot at
`2026-08-21T12:02:34Z`; its session became idle with no runtime launch id. A
fresh read still showed DCP-v2 Action
`v2-40f87d048813533daa1108b4316c09139acf0a8f` as `running`, slot `1`, with
runtime `78535564-a2bc-478c-80b0-207753f2152c`, while its Task remained
`worker_queued`. This is the false terminal runtime/model projection prohibited
by the aggregate contract.

The Worker created one exact local synthetic commit, but no remote branch, PR,
CI, review, Admission, Release Train, merge, artifact, deploy or Result effect
occurred. The complete observed record is the
[Stage 6 aggregate continuation blocked evidence](DCP_WBC_INTEGRATION_TWIN_STAGE6_AGGREGATE_CONTINUATION_BLOCKED_EVIDENCE.md).

The owner has now selected removal, not another predicate patch or
synchronization loop. Under the
[Stage 6 direct model authority contract](DCP_WBC_INTEGRATION_TWIN_STAGE6_DIRECT_MODEL_AUTHORITY_CONTRACT.md),
DCP SQLite and the daemon become the sole lifecycle authority and invoke a
stateless typed runner for Worker, Reviewer, repair and Arbiter. The source
package must also adopt the exact frozen Worker result once without another
model call or provider effect.

This is architecture/source-only authority. The installed schema-85 contour,
running app/daemon, current Task contradiction and local canary commit remain
frozen. After reviewed source completion, the next separate owner boundary is
an exact source pin, one governed install/migration and stopped preflight; live
continuation is not implied. Stage 7, WBC shadow and cutover remain separately
fenced. Technical evidence does not synthesize owner acceptance.

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
   counts still match; read back both the terminal native Action and stale
   DCP-v2 projection; verify no second submit, Admission, Result or provider
   effect appeared.
4. Read back installed source/tree/receipt, current dev-control-plane/lab/WBC
   GitHub state and exact open PR/check/review facts. Do not infer remote host
   health from old evidence.
5. Classify every intended action by surface: docs, managed source, installed
   contour, live SQLite, lab provider, WBC or production. Stop unless the new
   owner task explicitly authorizes that exact surface.
6. Treat the aggregate installer and start authority as spent. Do not retry,
   reinstall, publish the local target branch or patch another predicate.
7. Terminal handoff states technical `COMPLETE` or proven `BLOCKED`, lists exact
   identities and validation, names remaining risk and explicitly says owner
   acceptance was not synthesized.

## 9. Authoritative links

- [DCP-v2 architecture](DCP_WBC_INTEGRATION_TWIN_DCP_V2_ARCHITECTURE_CONTRACT.md)
- Stage 6 active source authority:
  [direct DCP-v2 model authority contract](DCP_WBC_INTEGRATION_TWIN_STAGE6_DIRECT_MODEL_AUTHORITY_CONTRACT.md)
- Stage 2: [contract](DCP_WBC_INTEGRATION_TWIN_STAGE2_SELECTEL_PERSISTENT_CELL_CONTRACT.md),
  [evidence](DCP_WBC_INTEGRATION_TWIN_STAGE2_TERMINAL_EVIDENCE.md)
- Stages 3-4: [contract](DCP_WBC_INTEGRATION_TWIN_STAGE3_4_COMBINED_EXECUTION_CONTRACT.md),
  [Stage 3 evidence](DCP_WBC_INTEGRATION_TWIN_STAGE3_TERMINAL_EVIDENCE.md),
  [Stage 4 evidence](DCP_WBC_INTEGRATION_TWIN_STAGE4_SOURCE_COMPLETE_EVIDENCE.md)
- Stage 5: [contract](DCP_WBC_INTEGRATION_TWIN_STAGE5_INSTALL_ACTIVATION_CONTRACT.md),
  [evidence](DCP_WBC_INTEGRATION_TWIN_STAGE5_TERMINAL_EVIDENCE.md)
- Stage 6 predecessor authority:
  [post-submit native-shell correction contract](DCP_WBC_INTEGRATION_TWIN_STAGE6_POST_SUBMIT_NATIVE_SHELL_CORRECTION_CONTRACT.md)
- Stage 6 spent authority:
  [aggregate install and same-identity continuation contract](DCP_WBC_INTEGRATION_TWIN_STAGE6_AGGREGATE_INSTALL_CONTINUATION_CONTRACT.md)
- Stage 6 terminal evidence:
  [aggregate continuation blocked evidence](DCP_WBC_INTEGRATION_TWIN_STAGE6_AGGREGATE_CONTINUATION_BLOCKED_EVIDENCE.md)
- Historical WBC predecessor:
  [task-first blocked evidence](DCP_TASK_FIRST_NATIVE_LIFECYCLE_V1_PASS2_BLOCKED_EVIDENCE.md),
  [PR #987 lifecycle evidence](DCP_WB_CORE_CI_TRUTH_LIFECYCLE_UX_V1_TERMINAL_EVIDENCE.md)
- Operational routing:
  [permission routing](DCP_CODEX_EXECUTOR_PERMISSION_ROUTING_CONTRACT.md),
  [direct executor routing](DCP_CODEX_DIRECT_EXECUTOR_ROUTING_CONTRACT.md)
