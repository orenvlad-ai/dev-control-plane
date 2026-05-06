# Glossary

This file is derived secondary context. Authoritative definitions remain in the source docs and code.

Development Control Plane: the standalone `dev-control-plane` project for preparing, gating, running and verifying bounded development tasks.

control-plane: orchestration, policy, task specification, execution gating, artifact capture and verification.

product-plane: a target product runtime, product UI, deploy lane, public route or business behavior outside this repo.

target project: an external repo described by adapter metadata under `configs/target_projects/`.

`wb-core`: the first checked-in target project profile. It is target context, not this repo identity.

managed clone / managed workspace: an isolated clone/workspace created under control-plane state for a gated run. It is separate from the original target repo working tree.

TaskSpec: the frozen bounded task contract used to build prompts and run one scoped execution.

SprintStep: a runnable step inside a TaskSpec. If no step id is supplied, the runner/UI may use the first runnable step.

safe fake-flow: deterministic fake execution path for smoke/internal validation. It does not call real Codex and does not mutate targets.

real Codex managed run: operator-confirmed Codex execution inside a managed clone, gated by policy and producing review artifacts.

OpenAI curator: optional AI intake provider used to draft TaskSpecs from operator discussion and target context. It uses terminal/runtime credentials only; fake curator is smoke/internal fallback.

verifier: deterministic checker for frozen spec, prompt/handoff contract, forbidden paths/actions, command status, diff hygiene, managed workspace ownership and original target unchanged state.

handoff: final structured execution report for the curator/operator, including required contract headers.

timeline: ordered run events shown in the cockpit from job lifecycle, Codex logs when available, changed files and verifier checks.

runtime config: non-secret hosted/local settings such as OpenAI/Codex model, reasoning effort and Codex sandbox mode, stored outside the repo when hosted.

target workflow: decision-only PR/preview/approval planning for target managed-clone output.

production lane: explicit target-specific apply/deploy policy. Currently only `wb-core` has this lane, and it is gated by verifier, rollback, secrets, forbidden-path, PR and deploy-runner checks.

derived pack: compact secondary retrieval context under `dev_control_plane_docs_master/**`; refreshed only by derived-sync.

manifest: `99_MANIFEST__DOCSET_VERSION.md`, build metadata for the derived pack only.
