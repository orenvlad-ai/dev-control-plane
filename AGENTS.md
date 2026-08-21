# Repository rules

This public repository owns DCP architecture, operating authority, immutable
qualification evidence and the bounded local integration adapter. Managed
application source lives in `orenvlad-ai/dcp-orchestrator`; target repositories
own their Release Trains. DCP is not a production control plane.

## Start here

For every task, read in this order:

1. [current integration-twin program manifest](docs/DCP_WBC_INTEGRATION_TWIN_CURRENT_PROGRAM_MANIFEST.md);
2. [current operating contract](docs/CURRENT_OPERATING_CONTRACT.md);
3. the task-specific contract and its linked immutable evidence;
4. [project brief](docs/PROJECT_BRIEF.md), [roadmap](docs/ROADMAP.md) and
   [decisions](docs/DECISIONS.md) only when broader context is needed.

The manifest is the single active statement of current integration-twin stage,
identity, blocker and next boundary. Historical contracts and evidence remain
authoritative for facts that occurred, but they do not silently authorize new
work.

## Executor routing

- Qualify every visible executor from its machine-reported effective context.
  The required profile is `approval_policy=never`, unrestricted filesystem,
  network enabled, a ready separate Git worktree and platform approval count
  `0`. Saved settings and prompt assertions are not capability proof.
- Follow the [permission-routing contract](docs/DCP_CODEX_EXECUTOR_PERMISSION_ROUTING_CONTRACT.md)
  and [direct-executor routing contract](docs/DCP_CODEX_DIRECT_EXECUTOR_ROUTING_CONTRACT.md).
- One owner-visible direct executor owns one repository task. Curator-side
  collaboration `spawn_agent` calls, subagents, nested executors, forks and
  parallel DCP tasks are forbidden unless a later owner contract explicitly
  replaces this rule.
- Revalidate the worktree, current `origin/main`, applicable authority and
  platform approval count before mutation and again at terminal handoff.

## Authority and mutation rules

- Owner authorization is exact scope, not a general license. Separate
  architecture, source, pin/install, runtime, submit, provider and production
  gates never collapse into one another.
- A read/diagnostic request authorizes no write. A documentation task authorizes
  no managed-source, runtime, SQLite, target-repository or provider mutation.
- Never infer missing state as success, zero or owner acceptance. Ambiguous or
  contradictory state fails closed with a named technical blocker.
- Do not stop, start, restart, kill, migrate, replay, resubmit, install, merge,
  deploy or rotate credentials unless the active task explicitly authorizes
  that exact operation and identity.
- Preserve co-tenants, production data, credentials and private paths. Public
  documentation must contain no secret value, chat transcript, local worktree
  path or newly exposed sensitive host detail.
- Use synthetic fixtures. Never commit real business data, personal data,
  banking details, production payloads or credentials.

## Git and review

- Fetch fresh `origin/main`; begin from its exact head in a separate clean
  worktree. Never overwrite concurrent or foreign work.
- Use one ordinary `codex/` branch and the exact PR count authorized by the
  task. Stage only reviewed paths; never use broad staging.
- Before merge, require an exact-head context-free semantic/security review,
  the required `baseline` check green for that exact head and zero unresolved
  review threads. If the head changes, the old review and check do not carry.
- Merge normally, fetch the resulting `origin/main`, fast-forward the canonical
  checkout when authorized, and prove clean final readback. Technical
  completion is not owner acceptance.

## Product invariants

- One submit creates one stable Task/card identity. Head or base drift and
  restart create immutable revisions and durable commands, never a replacement
  Task or duplicate initial model call.
- At most three model Actions may be globally active. `workflowActive` and
  truthful `modelActive` are distinct.
- Every exact head needs exact CI and a fresh context-free review. At most one
  task-level findings repair is permitted, followed by a new fresh review.
- Admission is mechanical FIFO authority to decide whether and in what order an
  exact reviewed head may release. DCP and model roles never directly merge or
  deploy and never receive production secrets.
- The repository-owned Release Train validates the exact admitted manifest,
  merges that exact head, builds/deploys through its adapter and publishes
  immutable proof. Repo-only work may end at exact merge/release proof;
  deployable work ends only after verified deployed SHA, health and provenance.
- Human Gate means a genuine owner decision. Technical defects are not Human
  Gates. Owner acceptance is never synthesized.
- Cutover permits one merge/deploy actor: old actor off before new actor on.

## Current Stage 6 fence

Stages 1-5 are technically complete. Stage 6 has exactly one durable identity,
`dcp-v2-twin-canary-v1`; no second submit or replacement identity is permitted.
Aggregate managed-source PR #76, the reviewed pin/install package, one governed
aggregate installation and one start are complete and spent. The native Worker
succeeded, but its terminal fact did not reconcile the DCP-v2 Action/Task:
native is idle with zero active model Actions while DCP-v2 still projects the
Worker Action as running with its slot and runtime.

The exact replaced predecessor source/tree was
`11401ff6eadb80fd87e48229fb8c5458095a63b1` /
`91bf6e25ec1b0e0f971ad36f7b80272aded2482c`; it is historical rollback proof,
not install authority.

Stage 6 is technically blocked under the mandatory hard stop. Do not patch,
restart, retry, reinstall, manually publish the local canary commit or create a
substitute identity. The owner-selected removal of the legacy second-authority
bridge is now source-complete: architecture PR #259 and managed-source PR #77
are merged, and DCP-v2 SQLite plus its daemon directly own model runtime
lifecycle through a stateless typed runner. The governing design remains the
[direct model authority contract](docs/DCP_WBC_INTEGRATION_TWIN_STAGE6_DIRECT_MODEL_AUTHORITY_CONTRACT.md),
and the exact result is the
[direct-model source-complete evidence](docs/DCP_WBC_INTEGRATION_TWIN_STAGE6_DIRECT_MODEL_SOURCE_COMPLETE_EVIDENCE.md).

The direct-model source is not installed. Its merge grants no pin, install,
migration, runtime or provider continuation. The next separate owner boundary
is exact pin/install/migration/stopped preflight. Stage 7 remains not started.
The exact spent-runtime record is the
[Stage 6 aggregate continuation blocked evidence](docs/DCP_WBC_INTEGRATION_TWIN_STAGE6_AGGREGATE_CONTINUATION_BLOCKED_EVIDENCE.md).

Exact checkpoint values, rotation bootstrap and current links are maintained
only in the [current program manifest](docs/DCP_WBC_INTEGRATION_TWIN_CURRENT_PROGRAM_MANIFEST.md).
