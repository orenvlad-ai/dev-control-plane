# Dev Control Plane Passport

## Identity

`dev-control-plane` is a standalone local-first development control-plane project. It is a repo and governance boundary for preparing, gating, running and verifying bounded development tasks against external target repos.

It is not `wb-core`, not a SellerOS/product-plane repo, not a hosted operator surface, and not a deploy lane.

## Current Capabilities

- Russian chat-first local cockpit UI.
- OpenAI curator path with local secret setup and sanitized diagnostics.
- TaskSpec, SprintPlan and SprintStep contracts.
- Target project adapter layer with `wb-core` as the first checked-in profile.
- Safe fake-flow for deterministic local task simulation.
- Operator-confirmed real Codex managed-clone run from the UI and runner CLI.
- Deterministic verifier for handoff blocks, forbidden paths, `git diff --check`, Codex exit status and original target unchanged checks.
- Scrollable run timeline and result summary with artifacts for prompt, handoff, diff and logs.

## Current MVP State

The project is local-only by default and binds the cockpit server to `127.0.0.1`. The current execution model produces review artifacts. Current UI safe flow and managed Codex flow do not commit, push, merge, deploy or mutate the original target repo.

Real Codex execution is gated and runs only inside a managed clone. Smoke coverage uses fakes/stubs and must not make real OpenAI API calls or real Codex executions.

## Known Gaps

- No explicit apply policy from managed clone output back to target repos.
- No hosted auth, hosted state, public route or production deployment model.
- No multi-tenant or remote operator model.
- No automatic PR creation from run artifacts.
- No product-plane/SellerOS integration by design.
