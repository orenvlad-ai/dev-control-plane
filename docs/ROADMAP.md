# Roadmap

The operating constraint remains one active repository change task at a time
using the curator-to-executor flow in `PROJECT_BRIEF.md`. A merged technical
stage is not owner acceptance.

1. **Documentation baseline — merged as PR #96.** The architecture, authority
   boundaries, upstream selection and fixed `DCP_lab` contract were recorded.
   Technical completion is known; owner acceptance was not synthesized.
2. **I2 bounded qualification and laboratory vertical slice — implemented in
   this change.** One separately authorized stage combined the previously
   planned qualification, isolated foundation and first canary. It pins and
   audits Agent Orchestrator revision
   `f17013b53a1752e86c66e87b45aaa4a463fdff62`, preserves Apache provenance and
   deliberately packages no upstream runtime/dependency surface. The DCP-owned
   lab provides one local card, one attempt, one ephemeral Codex worker, exact
   marker evidence, full cleanup and truthful terminal records. **Gate:**
   deterministic tests/audits, local build/start, visible UI smoke, one real
   end-to-end canary, ready PR, required green CI and protected merge. These
   facts prove technical completion only.
3. **Future packaging decision — not approved.** Decide whether a later stage
   needs a source-level upstream fork or signed/notarized macOS `.app`. Any such
   scope must repeat dependency/NOTICE/package audits and preserve the I2
   updater, telemetry, crash and namespace denials.
4. **Future control-contract expansion — not approved.** Retry/recovery,
   reconciliation, reviewer boundary and more general registry behavior require
   a separate threat model and explicit owner authorization. One-change-at-a-
   time remains the governing constraint.
5. **Future private Entire canary — not approved.** It requires explicit owner
   opt-in and must prove that only nullable references cross the privacy
   boundary; no prompt, transcript, credential or private code export is
   allowed. Entire remains absent and non-blocking by default.
6. **Production and target rollout — not approved.** `devcontrol.pro`,
   `wb-core`, real targets, hosted deployment, parallel orchestration, Release
   Train, reviewer loop, arbiter and legacy v1/v2 remain outside scope.
