#!/usr/bin/env bash
set -euo pipefail

evidence=docs/DCP_WBC_INTEGRATION_TWIN_STAGE4_SOURCE_COMPLETE_EVIDENCE.md
current=docs/CURRENT_OPERATING_CONTRACT.md
contract=docs/DCP_WBC_INTEGRATION_TWIN_STAGE3_4_COMBINED_EXECUTION_CONTRACT.md

for path in "$evidence" "$current" "$contract" AGENTS.md; do
	[[ -s "$path" ]]
done

for needle in \
	'source_complete_status: `COMPLETE`' \
	'installation_status: `NOT AUTHORIZED / NOT PERFORMED`' \
	'adapter_activation_status: `OFF`' \
	'`1401c9f38121b4a65605b23fe6c32e8e38a39d6f`' \
	'`PRR_kwDOTydt6M8AAAABKPsdtQ`' \
	'workflow `32367257928`' \
	'`bcb512239cbc14788f8fe59ece1ba33cbcb18c1f`' \
	'`2a894de8af6e73eabd11bd8d80dc0ed31812930b`' \
	'`0084_dcp_v2_core.sql`' \
	'359/359' \
	'created zero live integration-twin Task, Action and Admission rows' \
	'qualification issuer remains active until' \
	'platform approval count `0`' \
	'owner_acceptance: not requested or synthesized'
do
	grep -Fq "$needle" "$evidence"
done

grep -Fq 'operating_contract_revision: 2026-08-20.9' "$current"
grep -Fq 'DCP_WBC_INTEGRATION_TWIN_STAGE4_SOURCE_COMPLETE_EVIDENCE.md' "$current" AGENTS.md
grep -Fq 'requires a separate owner-authorized lock/pin/install/preflight pass' "$current"
grep -Fq 'qualification issuer remains active until Stage 5' "$current"
grep -Fq 'There are zero live integration-twin' "$current"
grep -Fq 'Task/Action/Admission rows because no submit occurred' "$current"
grep -Fq 'Stage 4 source-complete boundary' "$contract"

! grep -Fq 'owner_acceptance: accepted' "$evidence"
! grep -Eq '(/Users/|/home/|\.codex/worktrees/)' "$evidence"

bash -n scripts/i34_wbc_integration_twin_stage4_source_audit.sh

printf 'PASS I34 WBC integration twin Stage 4 source-complete audit\n'
