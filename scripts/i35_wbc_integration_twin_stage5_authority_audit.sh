#!/usr/bin/env bash
set -euo pipefail

contract=docs/DCP_WBC_INTEGRATION_TWIN_STAGE5_INSTALL_ACTIVATION_CONTRACT.md
current=docs/CURRENT_OPERATING_CONTRACT.md

for path in "$contract" "$current" AGENTS.md docs/DECISIONS.md docs/ROADMAP.md docs/PROJECT_BRIEF.md; do
	[[ -s "$path" ]]
done

for needle in \
	'program_stage: 5 of 9' \
	'stage6_task_id: `dcp-v2-twin-canary-v1`' \
	'`bcb512239cbc14788f8fe59ece1ba33cbcb18c1f`' \
	'`2a894de8af6e73eabd11bd8d80dc0ed31812930b`' \
	'`1340359100` / `237411244`' \
	'`21077248`' \
	'`20234191757`' \
	'`96be74db-785f-4653-85a8-a4e7c1d3ccdf`' \
	'`repository_dispatch` / event type `dcp-admission-v2`' \
	'No point may accept both issuer kinds' \
	'`0084_dcp_v2_core.sql` once' \
	'zero twin Task, Revision, Command, Action, Admission, Incident and Result' \
	'PR #987 is unchanged' \
	'Stage 7 work' \
	'owner_acceptance: not requested or synthesized'
do
	grep -Fq "$needle" "$contract"
done

grep -Fq 'operating_contract_revision: 2026-08-21.4' "$current"
grep -Fq 'DCP_WBC_INTEGRATION_TWIN_STAGE5_INSTALL_ACTIVATION_CONTRACT.md' "$current" AGENTS.md docs/ROADMAP.md docs/PROJECT_BRIEF.md
grep -Fq 'authorize Stage 5 adapter, issuer handoff and stopped installation' docs/DECISIONS.md

! grep -Fq 'owner_acceptance: accepted' "$contract"
! grep -Eq '(/Users/|/home/|\.codex/worktrees/)' "$contract"

bash -n scripts/i35_wbc_integration_twin_stage5_authority_audit.sh

printf 'PASS I35 WBC integration twin Stage 5 authority audit\n'
