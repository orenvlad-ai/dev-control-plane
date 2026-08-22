#!/usr/bin/env bash
set -euo pipefail

contract=docs/DCP_WBC_INTEGRATION_TWIN_STAGE6_POST_SUBMIT_NATIVE_SHELL_CORRECTION_CONTRACT.md
current=docs/CURRENT_OPERATING_CONTRACT.md

for required in "$contract" "$current" AGENTS.md docs/PROJECT_BRIEF.md docs/ROADMAP.md docs/DECISIONS.md; do
	[[ -s "$required" ]]
done

for exact in \
	'contract_revision: 2026-08-20.1' \
	'`dcp-v2-twin-canary-v1`' \
	'`v2-13f81f321f99d1117dc931419e0bea3945ee35a5`' \
	'`v2-e028f779a18417e990911057f7db7c666f7487ca`' \
	'`v2-40f87d048813533daa1108b4316c09139acf0a8f`' \
	'`375b9b2d0b4c2fce6f2c417850553f79e24a0d92`' \
	'`c1fc43d74cd517b7d73540f340058fa17b56ef15`' \
	'`ff51ca2b1f6f9fa502b999f50a366a8e35035421`' \
	'forward migration `0085`' \
	'second or replacement submit' \
	'Stage 7 remains fenced'; do
	grep -Fq "$exact" "$contract"
done

grep -Fq 'operating_contract_revision: 2026-08-22.5' "$current"
grep -Fq 'DCP_WBC_INTEGRATION_TWIN_STAGE6_POST_SUBMIT_NATIVE_SHELL_CORRECTION_CONTRACT.md' "$current" AGENTS.md docs/PROJECT_BRIEF.md docs/ROADMAP.md
grep -Fq 'owner_acceptance: not requested or claimed' "$contract"
! grep -Fq 'owner_acceptance: accepted' "$contract"
! grep -Eq '(/Users/|/home/|\.codex/worktrees/)' "$contract"

bash -n scripts/i40_wbc_integration_twin_stage6_correction_audit.sh
git diff --check
printf 'PASS I40 WBC integration twin Stage 6 correction authority audit\n'
