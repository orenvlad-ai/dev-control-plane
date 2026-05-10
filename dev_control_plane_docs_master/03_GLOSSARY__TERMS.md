# Glossary

This file is derived secondary context. Authoritative definitions remain in the source docs and code.

Development Control Plane: the standalone `dev-control-plane` project for preparing, gating, running, observing and verifying bounded development tasks.

control-plane: orchestration, policy, task specification, execution gating, artifact capture, live observation and verification.

product-plane: a target product runtime, product UI, deploy lane, public route or business behavior outside this repo.

target project: an external repo described by adapter metadata under `configs/target_projects/`.

`wb-core`: the first checked-in target project profile. It is target context, not this repo identity.

managed clone / managed workspace: an isolated clone/workspace created under control-plane state for a gated run. It is separate from the original target repo working tree.

TaskSpec: the frozen bounded task contract used to build prompts and run one scoped execution.

SprintStep: a runnable step inside a TaskSpec. If no step id is supplied, the runner/UI may use the first runnable step. This step contract is separate from the frozen sprint orchestrator.

safe fake-flow: deterministic fake execution path for smoke/internal validation. It does not call real Codex and does not mutate targets.

real Codex managed run: operator- or MCP-gated Codex execution inside a managed clone, producing review artifacts.

OpenAI curator: optional AI intake provider used to draft TaskSpecs from operator discussion and target context. It uses terminal/runtime credentials only; fake curator is smoke/internal fallback.

MCP Stage 1 bridge: bounded `POST /mcp` backend for ChatGPT Developer Mode with public no-auth read tools and OAuth-gated authenticated tools.

OAuth `dcp.write`: write-tool authorization scope for MCP start/resume/promotion tools and authenticated target-docs discovery.

target docs tools: authenticated read-only MCP tools that expose allowlisted target docs from cached snapshots without mutating the target repo.

`start_wb_core_auto_task`: canonical ChatGPT Project write route for ordinary `wb-core`/WebCore work; it starts one direct production-capable run when exclusive, or returns a precise blocker before Codex starts.

`start_sprint`: frozen/internal compatibility surface. It is hidden from ordinary operator discovery; non-internal calls return the frozen blocker and create no parent/child run tree.

`DEVCONTROL_START_SPRINT_V1`: frozen compatibility marker formerly carried through `start_managed_clone_run`; ordinary operator use returns the same frozen blocker and must not route to sprint or managed-clone-only fallback.

live monitor: read-only `/runs/live` and `/runs/<run_id>/watch` UI for sanitized run state, terminal-like output, timeline, artifacts and bounded cancel/mark-stale controls.

effective status/activity: non-mutating live-run reconciliation fields that distinguish raw run status from observed Codex process/log/verifier state.

runtime parity: sanitized preflight status for required hosted tools, Codex auth, model/reasoning, sandbox, package-manager baseline and browser readiness.

verifier: deterministic checker for frozen spec, prompt/handoff contract, forbidden paths/actions, command status, diff hygiene, managed workspace ownership and original target unchanged state.

handoff: final structured execution report for the curator/operator, including required contract headers.

timeline: ordered run events shown in the cockpit and live monitor from job lifecycle, Codex logs when available, changed files and verifier checks.

runtime config: non-secret hosted/local settings such as OpenAI/Codex model, reasoning effort and Codex sandbox mode, stored outside the repo when hosted.

target workflow: decision-only PR/preview/approval planning for target managed-clone output.

production lane: explicit target-specific apply/deploy policy. Currently only `wb-core` has this lane, and it is gated by verifier, rollback, secrets, forbidden-path, GitHub auth, SSH readiness, PR and deploy-runner checks.

parallel task ledger: state collection for multi-source per-target task intake, fake/guarded execution binding, reconcile and promotion decisions. It records ping-pong as frozen and never calls `start_sprint`.

selected promotion: the shared UI/MCP `Merge & Deploy` path for selecting verifier-passed candidates or managed runs, planning single/group promotion, deferring same-group conflicts and invoking the existing `wb-core` production lane only under explicit real-production gates.

promotion diff gate: deploy safety check that requires the promotion workspace changed-file set to match verifier `changed_files`, including created/untracked files.

archival sprint run: historical sprint parent/child run data that may be displayed read-only but cannot be selected for promotion.

post-merge resume: recovery path for already merged blocked `wb-core` production-lane runs; it resumes backup/deploy/probes only.

GitHub closure: Codex-owned commit/push/PR/merge/delete-branch policy for this repo only after clean gates.

derived pack: compact secondary retrieval context under `dev_control_plane_docs_master/**`; refreshed only by derived-sync.

manifest: `99_MANIFEST__DOCSET_VERSION.md`, build metadata for the derived pack only.
