# Dev Control Plane Passport

This file is derived secondary context. Authoritative truth stays in `README.md`, `AGENTS.md`, `docs/architecture/*`, `configs/target_projects/*`, `apps/` and `src/dev_control_plane/`.

## Identity

`dev-control-plane` is a standalone local-first, hosted-ready development control-plane project. It prepares, gates, runs and verifies bounded development tasks against external target repositories.

It is not `wb-core`, not a SellerOS/product-plane runtime, not a target product repo, and not a generic deployment surface. Target projects are configurable external inputs.

## Current Capabilities

- Russian chat-first operator cockpit with target selector, task card review, run timeline, result summary and collapsed technical details.
- OpenAI curator path with terminal-only secret setup, sanitized diagnostics, bounded timeout/retry settings and fake curator only for smoke/internal fallback.
- Runtime model settings for OpenAI curator and Codex CLI stored as non-secret runtime config outside the repo.
- TaskSpec, SprintPlan and SprintStep contracts, including first-runnable-step fallback.
- Target project adapter layer with `wb-core` as the first checked-in profile.
- Unified state layout for collections, prompts, runs, logs, verifier output and managed workspaces.
- Safe fake-flow for deterministic local task simulation.
- Operator-confirmed real Codex execution from UI and runner CLI only inside a managed clone.
- Hosted Codex toolchain preflight with sanitized tool/version diagnostics.
- Deterministic verifier for frozen spec, prompt/handoff presence, exact final handoff blocks, forbidden paths/actions, `git diff --check`, Codex exit status, managed workspace ownership and original target unchanged checks.
- Scrollable `Ход выполнения` timeline and `Результат выполнения` summary with changed files, diff and handoff previews.
- Decision-only target PR, preview and approve/reject planning for generic targets.
- Codex-owned GitHub closure gate for this repo only.
- Explicit `wb-core` production lane that may create a target PR, merge and run the approved WebCore deploy runner only after verifier, rollback, secrets, forbidden-path and target-lock gates pass.
- Loopback-only hosted server runtime foundation and repo-owned hosted deploy runner for the isolated `devcontrol.pro` service.

## Current State

Default operation is local-only and loopback-only. The server refuses non-`127.0.0.1` binds. Hosted profile uses isolated `/opt/dev-control-plane-runtime/**` state/config/tool paths and must not touch WebCore runtime paths.

Safe fake-flow and normal managed-Codex review flow do not commit, push, merge, deploy, use SSH/root or mutate original target repos. Managed-clone output becomes apply material only through an explicit target policy. Today the only production-capable target policy is the `wb-core` production lane.

Smokes use fake/stub OpenAI and Codex paths. They must not call the real OpenAI API or real Codex executor.

## Known Gaps

- Durable hosted database/object-store backend and retention policy are not implemented.
- Multi-worker scheduling and durable job recovery are not implemented.
- Real preview/staging deploy adapters and preview verifier contracts are not implemented.
- Generic target PR mutation remains decision-only; real target GitHub mutation is implemented only for the explicit `wb-core` production lane.
- Production approval/deploy policy exists only for `wb-core`.
- Hosted secret-store integration is not implemented; current secret handling is local/runtime-file based and outside the repo.
- Target-specific commit author and PR labeling policy are not implemented.
