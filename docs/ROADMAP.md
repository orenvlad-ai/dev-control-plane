# Roadmap

The current operating constraint is one active change task at a time using the
curator-to-executor PR flow in `PROJECT_BRIEF.md`. The target architecture and
all work after item 1 are future work, not implemented capability.

1. **Documentation baseline — this change.** Record the approved DCP
   architecture, role authority, upstream selection and provenance, fork
   isolation requirements and first `DCP_lab` canary contract. **Gate:** the
   documentation-only PR is reviewed through the ordinary GitHub flow, required
   CI is green, the three authoritative documents agree with `AGENTS.md`, and
   the PR is merged.
2. **Fork and safety qualification plan.** Select a future Agent Orchestrator
   fork point; inventory licenses/notices, update and telemetry/crash paths,
   namespace collisions, data flows and trust boundaries; specify deterministic
   acceptance tests. **Gate:** owner approves the exact implementation scope and
   threat model; no fork build is authorized by this roadmap item alone.
3. **Isolated DCP application foundation.** In a separately approved change,
   create the managed fork with DCP identity and state roots, updater removal,
   telemetry/analytics/crash-reporting disablement and license/provenance
   handling. **Gate:** source and artifact audits, network-denial tests,
   namespace-isolation tests and relevant platform build checks all pass.
4. **Deterministic control contract.** Specify and then implement, in separately
   approved scopes, the task registry, explicit state machine, single-dispatch
   invariant, bounded retries, restart recovery, cleanup receipts, evidence
   schema and independent-review boundary. **Gate:** model-free conformance and
   failure-injection tests pass without synthesizing reviewer or owner approval.
5. **Prepare the isolated `DCP_lab` contour.** Create only the dedicated lab
   Project, local state root and disposable test repository needed by the fixed
   canary; enforce repository/path allowlists and deny `dev-control-plane`,
   `wb-core`, production, hosted systems and real targets. **Gate:** owner
   authorizes the lab run after isolation, kill-path and cleanup dry-run evidence
   is reviewed.
6. **Run the one-task canary.** Execute `dcp-lab-canary-001` exactly as defined
   in `PROJECT_BRIEF.md`. **Gate:** one card, one isolated worker/worktree, exact
   marker evidence, truthful terminal status, complete cleanup and no forbidden
   contact are all proven; otherwise the canary fails and expansion stops.

Production, `devcontrol.pro`, `wb-core`, real target repositories, hosted
deployment, parallel task orchestration and legacy v1/v2 are outside this
roadmap.
