#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
cd "$REPO_ROOT"

evidence=docs/DCP_WBC_INTEGRATION_TWIN_STAGE3_TERMINAL_EVIDENCE.md
contract=docs/DCP_WBC_INTEGRATION_TWIN_STAGE3_4_COMBINED_EXECUTION_CONTRACT.md
current=docs/CURRENT_OPERATING_CONTRACT.md

for path in "$evidence" "$contract" "$current" AGENTS.md docs/PROJECT_BRIEF.md docs/ROADMAP.md docs/DECISIONS.md; do
	[[ -s "$path" ]]
done

for needle in \
	'evidence_status: `COMPLETE`' \
	'program_stage: 3 of 9' \
	'owner_acceptance: not requested or synthesized' \
	'1340359100' \
	'21077248' \
	'20234191757' \
	'157ae90edb0891506639b845deac141f75189ec7' \
	'322dc03813a18cf91c9bf015e4c88a0c608472c3' \
	'32358500799' \
	'9402608863' \
	'f1f04ecfef562d27b61cf5e7e65695def99ac5689f9edf628532b18f81cd77c4' \
	'55569381f6579efe98ba75f553822a85597d7dd6c5379c07f58ce223f5fa88f7' \
	'32b00f27f41e5d84164f96e824dcdb336c330210f2baac364143b2d3ecad9200' \
	'32358094724' \
	'32358633669' \
	'32358707237' \
	'32358348110' \
	'32358400185' \
	'96be74db-785f-4653-85a8-a4e7c1d3ccdf' \
	'33,398,226,944 bytes' \
	'platform approval count `0`' \
	'collaboration subagent' \
	'count `0`'; do
	grep -Fq "$needle" "$evidence"
done

for needle in \
	'Valid exact manifest' \
	'PR/head drift' \
	'Main drift' \
	'Wrong repository/base/PR/check identity' \
	'Equal duplicate manifest/event' \
	'Artifact/source/deployed-SHA mismatch' \
	'Adapter/probe failure' \
	'negative case produced zero ref update' \
	'qualification issuer remains solely active' \
	'No DCP app, daemon, SQLite, Task, Revision, Command, Action' \
	'lock/pin/install/preflight and Stage 6 submit remain prohibited'; do
	grep -Fiq "$needle" "$evidence"
done

for authority in AGENTS.md "$current" docs/PROJECT_BRIEF.md docs/ROADMAP.md docs/DECISIONS.md "$contract"; do
	grep -Fq 'DCP_WBC_INTEGRATION_TWIN_STAGE3_TERMINAL_EVIDENCE.md' "$authority"
done

grep -Fq 'operating_contract_revision: 2026-08-20.3' "$current"
grep -Fq 'managed-source implementation boundary' "$contract"
grep -Fq 'stage or adapter authority is activated' "$contract"
! grep -Fq 'owner_acceptance: accepted' "$evidence"
! grep -Eq '(/Users/|/home/|\.codex/worktrees/)' "$evidence" "$contract"
bash -n scripts/i33_wbc_integration_twin_stage3_audit.sh
git diff --check
printf 'PASS I33 WBC integration twin Stage 3 terminal and Stage 4 activation audit\n'
