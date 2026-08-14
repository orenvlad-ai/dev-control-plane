#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
cd "$REPO_ROOT"

target=docs/TARGET_ARCHITECTURE_V1.md
[[ -s "$target" ]]

grep -Fq 'contract_status: target-design-only' "$target"
grep -Fq 'The current operating contour is the packaged I12/I13' "$target"
grep -Fq 'daemon and its existing SQLite are the only local' "$target"
grep -Fq 'GitHub is authoritative for repository refs, pull requests, checks, merge' "$target"
grep -Fq 'Three consecutive complete reviewer cycles are allowed' "$target"
grep -Fq 'READY_FOR_ADMISSION' "$target"
grep -Fq 'WAITING_GLOBAL_RELEASE' "$target"
grep -Fq 'release:ready' "$target"
grep -Fq 'Sol, `xhigh`' "$target"
grep -Fq 'HumanGate is allowed only' "$target"
grep -Fq 'Desktop release loop' "$target"
grep -Fq 'DCP v1 architecture, authority/transition/event contracts' "$target"
grep -Fq 'Telegram' "$target"
grep -Fq 'Symphony is provenance, not a dependency' "$target"
grep -Fq 'HistoryProvider' "$target"
grep -Fq 'provider=none' "$target"
grep -Fq 'I9 does not install, invoke, contact or test Entire' "$target"

for heading in \
	'## 2. Authority boundaries' \
	'## 5. Task, review and release states' \
	'## 6. Nominal sequence' \
	'## 9. Durable events and checkpoints' \
	'## 13. Failure matrix' \
	'## 14. Optional history/provenance seam' \
	'## 15. Fork and source-of-truth boundary' \
	'## 16. Paper test plan'; do
	grep -Fq "$heading" "$target"
done

[[ "$(grep -c '^```mermaid$' "$target")" -eq 2 ]]
[[ "$(grep -c '^| .* |' "$target")" -ge 75 ]]

for paper_case in \
	'Normal success' \
	'Reviewer reject' \
	'Three-cycle escalation' \
	'Two conflicting PRs' \
	'Head change' \
	'Release halt' \
	'Lost executor' \
	'DCP restart' \
	'HumanGate' \
	'Concurrent tasks' \
	'Desktop rollback' \
	'History provider absent' \
	'History provider failure'; do
	grep -Fq "| $paper_case |" "$target"
done

grep -Fq '[DCP v1 target architecture](TARGET_ARCHITECTURE_V1.md)' docs/CURRENT_OPERATING_CONTRACT.md
grep -Fq 'The exact installed source is `f54b597572d7204096cb16581becee067e1febdc`' docs/CURRENT_OPERATING_CONTRACT.md
grep -Fq 'design-only outside the exact happy-path v1 slice' docs/CURRENT_OPERATING_CONTRACT.md
grep -Fq 'I9 DCP v1 target architecture contract' docs/ROADMAP.md
grep -Fq 'Remaining target-contract implementation — not approved beyond the' docs/ROADMAP.md
grep -Fq 'record the DCP v1 target contract without activating it in I9' docs/DECISIONS.md
grep -Fq 'I9 target design outside the active lab slice' docs/PROJECT_BRIEF.md

happy_path=docs/DCP_LAB_HAPPY_PATH_V1_CONTRACT.md
[[ -s "$happy_path" ]]
grep -Fq 'contract_revision: 2026-08-14.3' "$happy_path"
grep -Fq 'status: owner-approved implementation contract' "$happy_path"
grep -Fq 'public synthetic repository' "$happy_path"
grep -Fq 'An equal replay of the same canonical' "$happy_path"
grep -Fq 'At most three DCP model actions may be active globally' "$happy_path"
grep -Fq 'one context-free review for the resulting new exact head' "$happy_path"
grep -Fq 'The existing `dcp_review_lab_admission` sequence is generalized' "$happy_path"
grep -Fq 'cards 11/12' "$happy_path"
grep -Fq 'Preserve existing `chat-probe-b`/card-13/PR-10/head/review/admission' "$happy_path"
for policy_file in AGENTS.md docs/CURRENT_OPERATING_CONTRACT.md docs/PROJECT_BRIEF.md docs/ROADMAP.md docs/DECISIONS.md; do
	grep -Fq 'DCP_LAB_HAPPY_PATH_V1_CONTRACT.md' "$policy_file"
done
grep -Fq 'card number is' AGENTS.md docs/CURRENT_OPERATING_CONTRACT.md
grep -Fq 'not an authority or ceiling' AGENTS.md docs/CURRENT_OPERATING_CONTRACT.md
grep -Fq 'The first I18 deterministic install completed with receipt' docs/CURRENT_OPERATING_CONTRACT.md
grep -Fq 'Policy-driven [DCP Lab happy path v1]' docs/ROADMAP.md
grep -Fq 'authorize policy-driven DCP Lab happy-path v1' docs/DECISIONS.md

stage2=docs/I13_STAGE2_ARBITER_V1_CONTRACT.md
[[ -s "$stage2" ]]
grep -Fq 'contract_status: owner-approved-pre-runtime' "$stage2"
grep -Fq 'dcp.review-lab.global-release-incident/v1' "$stage2"
grep -Fq 'dcp.review-lab.global-release-arbiter-input/v1' "$stage2"
grep -Fq 'dcp.review-lab.global-release-arbiter-decision/v1' "$stage2"
grep -Fq 'gpt-5.6-sol' "$stage2"
grep -Fq '16,384 tokens' "$stage2"
grep -Fq 'same_worker_conflict_repair' "$stage2"
grep -Fq 'Total model calls | 7' "$stage2"
grep -Fq 'The expected resolvable canary result is not `safe_stop`' "$stage2"
grep -Fq '[I13 Stage 2 global release arbiter v1](I13_STAGE2_ARBITER_V1_CONTRACT.md)' docs/CURRENT_OPERATING_CONTRACT.md
grep -Fq '[I13 Stage 2 terminal BLOCKED evidence](I13_STAGE2_BLOCKED_EVIDENCE.md)' docs/CURRENT_OPERATING_CONTRACT.md
grep -Fq 'evidence_status: technical-blocked' docs/I13_STAGE2_BLOCKED_EVIDENCE.md

successor=docs/I13_STAGE2_ARBITER_SUCCESSOR_CONTRACT.md
[[ -s "$successor" ]]
grep -Fq 'contract_status: owner-approved-pre-runtime' "$successor"
grep -Fq 'successor_attempt_generation: 2' "$successor"
grep -Fq 'policy_max_fresh_reviews=1' "$successor"
grep -Fq 'dcp.review-lab.global-release-arbiter-successor-decision/v1' "$successor"
grep -Fq 'Total model calls | 8' "$successor"
grep -Fq 'I13_STAGE2_ARBITER_SUCCESSOR_CONTRACT.md' docs/CURRENT_OPERATING_CONTRACT.md
grep -Fq 'e15a6d22f83876b240fa61889b6821bd49904f28' docs/CURRENT_OPERATING_CONTRACT.md docs/PROJECT_BRIEF.md docs/DECISIONS.md docs/UPSTREAM_QUALIFICATION.md

validation_recovery=docs/I13_STAGE2_SUCCESSOR_VALIDATION_RECOVERY_CONTRACT.md
[[ -s "$validation_recovery" ]]
grep -Fq 'contract_status: owner-approved-pre-runtime-model-free' "$validation_recovery"
grep -Fq 'additional_model_calls: 0' "$validation_recovery"
grep -Fq '9b5ff7847db2533e56bdbbc424114e5bea8e5e3c352ad1d029a99deaba05c172' "$validation_recovery"
grep -Fq 'a19c64060d0f41320b6bf652c47ff5c58810ebec0416d003963bc1b4fcdf524f' "$validation_recovery"
grep -Fq 'I13_STAGE2_SUCCESSOR_VALIDATION_RECOVERY_CONTRACT.md' docs/CURRENT_OPERATING_CONTRACT.md

successor_terminal=docs/I13_STAGE2_SUCCESSOR_TERMINAL_EVIDENCE.md
[[ -s "$successor_terminal" ]]
grep -Fq 'evidence_status: technical-blocked' "$successor_terminal"
grep -Fq 'successor_attempt_generation: 2' "$successor_terminal"
grep -Fq 'failed/repair_launch_failed' "$successor_terminal"
grep -Fq '237472879b22a8db65c5a3a0715510dc17aee1de93c45eaab45dde538cefb939' "$successor_terminal"
grep -Fq 'I13_STAGE2_SUCCESSOR_TERMINAL_EVIDENCE.md' docs/CURRENT_OPERATING_CONTRACT.md docs/PROJECT_BRIEF.md docs/DECISIONS.md docs/UPSTREAM_QUALIFICATION.md

fresh_worker_recovery=docs/I13_STAGE2_CARD12_FRESH_WORKER_RECOVERY_CONTRACT.md
[[ -s "$fresh_worker_recovery" ]]
grep -Fq 'contract_status: owner-approved-pre-runtime' "$fresh_worker_recovery"
grep -Fq 'fresh_worker_recovery_generation: 1' "$fresh_worker_recovery"
grep -Fq 'd2b7142bc9e5844ba165abe24d3222b3e1a94c3577fba5f6f8d97ec3dbad151b' "$fresh_worker_recovery"
grep -Fq 'worker_token_ceiling: 16384' "$fresh_worker_recovery"
grep -Fq 'fresh_reviewer_model_call_ceiling: 1' "$fresh_worker_recovery"
grep -Fq 'additional_arbiter_calls: 0' "$fresh_worker_recovery"
grep -Fq 'I13_STAGE2_CARD12_FRESH_WORKER_RECOVERY_CONTRACT.md' AGENTS.md docs/CURRENT_OPERATING_CONTRACT.md docs/PROJECT_BRIEF.md docs/DECISIONS.md

model_free_rebase=docs/I13_STAGE2_CARD12_MODEL_FREE_REBASE_CONTINUATION_CONTRACT.md
[[ -s "$model_free_rebase" ]]
grep -Fq 'contract_status: owner-approved-pre-runtime-model-free' "$model_free_rebase"
grep -Fq 'continuation_generation: 1' "$model_free_rebase"
grep -Fq '66eb630c1995f90b37429a2f6c57c57794dda9fc98a29149c88bdb2f01131060' "$model_free_rebase"
grep -Fq 'additional_worker_model_calls: 0' "$model_free_rebase"
grep -Fq 'additional_arbiter_model_calls: 0' "$model_free_rebase"
grep -Fq 'fresh_reviewer_model_call_ceiling: 1' "$model_free_rebase"
grep -Fq 'db9933afbc18ffbd031818990e2b350845c766a5f0ae8ed37fae8f4e8a66f371' "$model_free_rebase"
grep -Fq 'I13_STAGE2_CARD12_MODEL_FREE_REBASE_CONTINUATION_CONTRACT.md' AGENTS.md docs/CURRENT_OPERATING_CONTRACT.md docs/PROJECT_BRIEF.md docs/DECISIONS.md

provider_base_correction=docs/I13_STAGE2_CARD12_MODEL_FREE_PROVIDER_BASE_CORRECTION_CONTRACT.md
[[ -s "$provider_base_correction" ]]
grep -Fq 'contract_status: owner-authorized-direct-path-correction-pre-runtime' "$provider_base_correction"
grep -Fq '25663a5a551fce7ec0d6d9055588b4c4d1d1294fd926e2c7c2347cacd799ab59' "$provider_base_correction"
grep -Fq 'dbaf01b05e85ffffa4c843a905e2fe5229eaf0da' "$provider_base_correction"
grep -Fq 'b34b31b5443890e69128db2862726950a6bbac0d' "$provider_base_correction"
grep -Fq 'I13_STAGE2_CARD12_MODEL_FREE_PROVIDER_BASE_CORRECTION_CONTRACT.md' AGENTS.md docs/CURRENT_OPERATING_CONTRACT.md docs/PROJECT_BRIEF.md docs/DECISIONS.md

cold_start_recovery=docs/I13_STAGE2_CARD12_COLD_START_QUARANTINED_RECOVERY_CONTRACT.md
[[ -s "$cold_start_recovery" ]]
grep -Fq 'contract_status: owner-approved-pre-runtime-model-free' "$cold_start_recovery"
grep -Fq '087176dbe56428dc97a99823a94daa4687c41b15c14a08de21db2c6c602f0f2f' "$cold_start_recovery"
grep -Fq 'additional_worker_model_calls: 0' "$cold_start_recovery"
grep -Fq 'additional_arbiter_model_calls: 0' "$cold_start_recovery"
grep -Fq 'fresh_reviewer_model_call_ceiling: 1' "$cold_start_recovery"
grep -Fq '66,811' "$cold_start_recovery"
grep -Fq '5850bba009db75bf47ff88aef2d2cecbdba89c68967f51a8cdb60f48e968dc1a' "$cold_start_recovery"
grep -Fq 'I13_STAGE2_CARD12_COLD_START_QUARANTINED_RECOVERY_CONTRACT.md' AGENTS.md docs/CURRENT_OPERATING_CONTRACT.md docs/PROJECT_BRIEF.md docs/DECISIONS.md

rebase_head_finalization=docs/I13_STAGE2_CARD12_REBASE_HEAD_FINALIZATION_CONTRACT.md
[[ -s "$rebase_head_finalization" ]]
grep -Fq 'contract_status: owner-approved-pre-runtime-model-free' "$rebase_head_finalization"
grep -Fq 'a073fb250a5343cffa210614247c76a080bb9e7db6a6cd8d052909611a75e50b' "$rebase_head_finalization"
grep -Fq 'additional_worker_model_calls: 0' "$rebase_head_finalization"
grep -Fq 'additional_arbiter_model_calls: 0' "$rebase_head_finalization"
grep -Fq 'fresh_reviewer_model_call_ceiling: 1' "$rebase_head_finalization"
grep -Fq 'REBASE_HEAD' "$rebase_head_finalization"
grep -Fq 'I13_STAGE2_CARD12_REBASE_HEAD_FINALIZATION_CONTRACT.md' AGENTS.md docs/CURRENT_OPERATING_CONTRACT.md docs/PROJECT_BRIEF.md docs/DECISIONS.md

git diff --check
printf 'PASS I9 target-contract documentation audit\n'
