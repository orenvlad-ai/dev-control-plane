#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
cd "$REPO_ROOT"

evidence=docs/DCP_WBC_INTEGRATION_TWIN_STAGE2_TERMINAL_EVIDENCE.md
contract=docs/DCP_WBC_INTEGRATION_TWIN_STAGE3_4_COMBINED_EXECUTION_CONTRACT.md
current=docs/CURRENT_OPERATING_CONTRACT.md

for path in "$evidence" "$contract" "$current" AGENTS.md docs/PROJECT_BRIEF.md docs/ROADMAP.md docs/DECISIONS.md; do
	[[ -s "$path" ]]
done

for needle in \
	'evidence_status: `COMPLETE`' \
	'program_stage: 2 of 9' \
	'owner_acceptance: not requested or synthesized' \
	'1340359100' \
	'21077248' \
	'20234191757' \
	'5030236a22168c2bdc525b62985bda2c11888f76' \
	'ec23bcbd8a5282a4566307d1a308061094ef839c' \
	'32341023840' \
	'32341176639' \
	'9396402262' \
	'af73cd04167a94ccb96b9ad257c023d51a7830d6993eae2a62cc254fb6985a58' \
	'c5c18e63304ab9f4ba3fd244ab780e91fd7d7b49540a24b296dbc9d2ea0f0fe7' \
	'b96b837e5a1d3ba9575767097e9c8a49e8d54a228bf67f77715f0d5e3270954c' \
	'96be74db-785f-4653-85a8-a4e7c1d3ccdf' \
	'33,406,214,144 free root bytes' \
	'platform approval count `0`' \
	'zero collaboration subagents'; do
	grep -Fq "$needle" "$evidence"
done

grep -Fq 'Repository Actions secrets are empty' "$evidence"
grep -Fq '`DCP_WBC_LAB_KNOWN_HOSTS` and `DCP_WBC_LAB_SSH_KEY`' "$evidence"
grep -Fq '`dcp_issuer` is `off`' "$evidence"
grep -Fq 'pre-cleanup counter exit-code failure remains preserved' "$evidence"
grep -Fq 'ordinary timer' "$evidence"
grep -Fq 'promo_xlsx_collector_runs` is absent' "$evidence"
grep -Fq 'retained container, exited' "$evidence"
grep -Fq 'retained local volume' "$evidence"
grep -Fq 'No DCP submit, twin row, model call' "$evidence"

for needle in \
	'contract_status: owner-approved combined program' \
	'program_stages: 3 and 4 of 9' \
	'managed-source work may begin' \
	'valid exact manifest' \
	'PR/head drift' \
	'Main drift' \
	'Wrong repository, base, PR or required-check identity' \
	'Equal duplicate manifest/event' \
	'Artifact/source/deployed-SHA mismatch' \
	'Adapter or probe failure' \
	'no auto-sync, rebase, update-branch, force-push' \
	'one bounded correction' \
	'Task -> immutable exact-head Revision -> durable typed Command' \
	'at most three globally active model Actions' \
	'WBC or current-canary special case' \
	'disposable exact schema-83 copies' \
	'zero lost or duplicate Command, Action, Admission or Result' \
	'Stage 5 requires a separate owner-authorized lock/pin/install pass' \
	'qualification issuer remains active'; do
	grep -Fiq "$needle" "$contract"
done

for authority in AGENTS.md "$current" docs/PROJECT_BRIEF.md docs/ROADMAP.md docs/DECISIONS.md; do
	grep -Fq 'DCP_WBC_INTEGRATION_TWIN_STAGE2_TERMINAL_EVIDENCE.md' "$authority"
	grep -Fq 'DCP_WBC_INTEGRATION_TWIN_STAGE3_4_COMBINED_EXECUTION_CONTRACT.md' "$authority"
done

grep -Fq 'operating_contract_revision: 2026-08-20.6' "$current"
! grep -Fq 'owner_acceptance: accepted' "$evidence"
! grep -Eq '(/Users/|/home/|\.codex/worktrees/)' "$contract"
bash -n scripts/i32_wbc_integration_twin_stage2_stage4_audit.sh
git diff --check
printf 'PASS I32 Stage 2 closure and Stage 3-4 combined authority audit\n'
