# Dev Control Plane Passport

This file is derived secondary context. Authoritative truth stays in `README.md`, `AGENTS.md`, `docs/architecture/*`, `configs/target_projects/*`, `apps/` and `src/dev_control_plane/`.

## Identity

`dev-control-plane` is a standalone local-first, hosted-ready development control-plane project. It prepares, gates, runs, observes and verifies bounded development tasks against external target repositories.

It is not `wb-core`, not a SellerOS/product-plane runtime, not a target product repo, and not a generic public deployment surface. Target projects are configurable external inputs.

## Current Capabilities

- Unified dark operator dashboard with `Панель`, `Подключение`, `Мониторинг` and `Технические детали`; legacy chat/task-card APIs remain compatibility paths, not the primary UI.
- MCP Stage 1 backend at `POST /mcp` for ChatGPT Developer Mode with `mixed_noauth_read_oauth_write`: public no-auth read tools, OAuth `dcp.write` write tools, and authenticated read-only target docs tools.
- Bounded MCP tools for status, targets, active runs, reports, artifacts, timelines, log tails, rollback plans, read-only search/fetch, direct `wb-core` auto-task intake, explicit managed-clone-only review starts, explicit `wb-core` production-lane starts and post-merge deploy resume.
- `start_wb_core_auto_task` is the ordinary ChatGPT Project route for `wb-core`/WebCore work: DevControl atomically starts one direct production-capable run when exclusive, or returns a precise blocker before Codex starts.
- `start_sprint`, the sprint orchestrator, curator ping-pong, parent/child task decomposition and `DEVCONTROL_START_SPRINT_V1` bridge are frozen for ordinary operator flow. `start_sprint` is hidden from operator discovery; non-internal calls return the frozen blocker and create no parent/child run tree.
- Hosted live monitor at `/runs/live` and `/runs/<run_id>/watch` with sanitized terminal-like output, timeline events, prompt/report/handoff previews, changed files, verifier state, selected promotion state, archival sprint detail when historical runs exist, and bounded cancel/mark-stale controls.
- Codex observability with raw event logs separated from sanitized human terminal transcripts, run-owned process state, wall/idle watchdogs, stale reconciliation and effective status/activity reporting.
- Optional OpenAI curator intake with terminal-only key setup, sanitized diagnostics, bounded timeout/retry behavior and fake curator only for smoke/internal fallback.
- Runtime model/reasoning settings for OpenAI curator and Codex CLI stored as non-secret runtime config outside the repo when hosted.
- TaskSpec and SprintStep contracts, including first-runnable-step fallback. SprintPlan/server-side sprint orchestration remains frozen for operator flow.
- Target project adapter layer with `wb-core` as the first checked-in external target profile and remote managed clone source.
- Unified state layout for collections, prompts, runs, logs, verifier output, artifacts and managed workspaces.
- Safe fake-flow for deterministic local simulation without real OpenAI or real Codex calls.
- Operator-gated real Codex execution through runner/MCP/legacy API paths only inside a managed clone/workspace.
- Hosted Codex runtime parity preflight that records sanitized toolchain/auth/model/sandbox/package-manager/browser readiness and writes `artifacts/environment_parity.json`.
- Prompt consistency gate that blocks contradictory envelopes before Codex starts.
- Deterministic verifier for frozen spec, prompt/handoff presence, exact final handoff blocks, forbidden paths/actions, `git diff --check`, Codex exit status, managed workspace ownership and original target unchanged checks.
- Parallel task ledger for state-only multi-source task intake, guarded execution binding, reconcile/promote actions, selected `Merge & Deploy`, conflict-aware group promotion, refresh-required/frozen sibling state and read-only candidate/target-promotion summaries.
- Promotion safety gate that blocks deploy when the promotion workspace changed-file set does not exactly match verifier `changed_files`, including created/untracked files.
- Decision-only target PR, preview and approve/reject planning for generic targets.
- Codex-owned GitHub closure gate for this repo only.
- Explicit `wb-core` production lane that may create a target PR, merge and run the approved WebCore deploy runner only after verifier, rollback, secrets, forbidden-path, GitHub auth, SSH readiness, PR head SHA and target-lock gates pass.
- OAuth-gated post-merge resume path for already merged blocked `wb-core` production-lane runs; it resumes backup/deploy/probes only and never reruns Codex or changes source.
- Loopback-only hosted server runtime foundation and repo-owned hosted deploy runner for the isolated `devcontrol.pro` service.

## Current State

Default operation is local-only and loopback-only. The server refuses non-`127.0.0.1` binds. Hosted profile uses isolated `/opt/dev-control-plane-runtime/**` state/config/tool paths and must not touch WebCore runtime paths.

Safe fake-flow and normal managed-Codex review flow do not commit, push, merge, deploy, use SSH/root or mutate original target repos. Managed-clone output becomes apply material only through an explicit target policy. Today the only production-capable target policy is the `wb-core` production lane.

Smokes use fake/stub OpenAI and Codex paths. They must not call the real OpenAI API or real Codex executor.

Historical sprint parent/child artifacts may remain visible for audit, but they are read-only archival cards and are not promotion-selectable. The operator should not choose between parent/child runs for deployment.

## Known Gaps

- Durable hosted database/object-store backend and retention policy are not implemented.
- Multi-worker scheduling and durable job recovery are not implemented.
- Real preview/staging deploy adapters and preview verifier contracts are not implemented.
- Generic target PR mutation remains decision-only; real target GitHub mutation is implemented only for the explicit `wb-core` production lane.
- Production approval/deploy policy exists only for `wb-core`.
- Hosted secret-store integration is not implemented; current secret handling is local/runtime-file based and outside the repo.
- Target-specific commit author and PR labeling policy are not implemented.
