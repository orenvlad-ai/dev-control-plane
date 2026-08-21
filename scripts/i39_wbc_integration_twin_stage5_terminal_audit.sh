#!/usr/bin/env bash
set -euo pipefail

evidence=docs/DCP_WBC_INTEGRATION_TWIN_STAGE5_TERMINAL_EVIDENCE.md
current=docs/CURRENT_OPERATING_CONTRACT.md

for required in "$evidence" "$current" AGENTS.md docs/PROJECT_BRIEF.md docs/ROADMAP.md docs/DECISIONS.md; do
	[[ -s "$required" ]]
done

for exact in \
	'evidence_status: COMPLETE' \
	'`837a125ed3bb482351bef2a7d8bfdf875cc2fdeb`' \
	'`38f40576dbf246bde6e42ef877c5473bb61fa125`' \
	'`c1fc43d74cd517b7d73540f340058fa17b56ef15`' \
	'`ff51ca2b1f6f9fa502b999f50a366a8e35035421`' \
	'`54dd88beef2e9c93ee86435df2645d6707acf2dc3e2c0c0b4dad6de9b40cc9c0`' \
	'`da0918196d4c63f571d63feaf00f71c84e27d91498240779590a0ee67700eb86`' \
	'`i12-20260820T155118Z`' \
	'`i12-20260820T163147Z`' \
	'`96be74db-785f-4653-85a8-a4e7c1d3ccdf`' \
	'`dcp-v2-twin-canary-v1`'; do
	grep -Fq "$exact" "$evidence"
done

grep -Fq 'operating_contract_revision: 2026-08-21.4' "$current"
grep -Fq 'contract_revision: 2026-08-20.4' docs/DCP_WBC_INTEGRATION_TWIN_STAGE5_INSTALL_ACTIVATION_CONTRACT.md
grep -Eq '^\| 5 \| COMPLETE \|' docs/DCP_WBC_INTEGRATION_TWIN_CURRENT_PROGRAM_MANIFEST.md
grep -Eq '^\| 7 \| NOT STARTED \|' docs/DCP_WBC_INTEGRATION_TWIN_CURRENT_PROGRAM_MANIFEST.md
grep -Fq 'owner_acceptance: not requested or claimed' "$evidence"
! grep -Fq 'owner_acceptance: accepted' "$evidence"
! grep -Eq '(/Users/|/home/|\.codex/worktrees/)' "$evidence"

bash -n scripts/i39_wbc_integration_twin_stage5_terminal_audit.sh
printf 'PASS I39 WBC integration twin Stage 5 terminal evidence audit\n'
