# Glossary

Development Control Plane: the standalone local-first project in this repo for preparing, gating, running and verifying bounded development tasks.

control-plane: orchestration, policy, task specification, execution gating, artifact capture and verification.

product-plane: the target product runtime, product UI, deploy lanes, public routes and business behavior outside this repo.

target project: an external repo described by adapter metadata under `configs/target_projects/`.

managed clone: an isolated clone/workspace created by the control-plane for a gated run. It is separate from the original target repo working tree.

TaskSpec: the frozen bounded task contract used to build prompts and run one scoped execution.

safe fake-flow: deterministic fake execution path for smoke/internal validation. It does not call real Codex and does not mutate targets.

real Codex managed run: operator-confirmed Codex execution inside a managed clone, gated by policy and producing review artifacts.

verifier: deterministic checker for prompt/handoff contract, forbidden paths/actions, command status, diff hygiene and original target unchanged state.

handoff: final structured execution report for the curator/operator, including required contract headers.

timeline: ordered run events shown in the cockpit from job lifecycle, Codex logs when available, changed files and verifier checks.
