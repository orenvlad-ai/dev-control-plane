#!/usr/bin/env bash
set -euo pipefail

evidence=docs/DCP_WBC_INTEGRATION_TWIN_STAGE6_DIRECT_MODEL_STABLE_INSTALL_COMPLETE_EVIDENCE.md
contract=docs/DCP_WBC_INTEGRATION_TWIN_STAGE6_DIRECT_MODEL_STABLE_INSTALL_CONTRACT.md
manifest=docs/DCP_WBC_INTEGRATION_TWIN_CURRENT_PROGRAM_MANIFEST.md
current=docs/CURRENT_OPERATING_CONTRACT.md

for path in "$evidence" "$contract" "$manifest" "$current" AGENTS.md README.md \
	docs/PROJECT_BRIEF.md docs/ROADMAP.md docs/DECISIONS.md; do
	[[ -s "$path" ]]
done

grep -Fxq 'evidence_revision: 2026-08-22.2' "$evidence"
grep -Fxq 'technical_status: COMPLETE for exact pin, one governed migration/install and stopped preflight; Stage 6 adoption/live continuation remains BLOCKED' "$evidence"
grep -Fxq 'owner_acceptance: not requested or synthesized' "$evidence"
grep -Fxq 'manifest_revision: 2026-08-22.4' "$manifest"
grep -Fxq 'program_status: Stage 6 BLOCKED before adoption on DCP_V2_PUBLICATION_REVISION_PR_BINDING_MISSING; one final viability source correction authorized; schema 86 stopped and zero provider effect' "$manifest"
grep -Fxq 'operating_contract_revision: 2026-08-22.4' "$current"

for exact in \
	'`37fb9420fdd3d8fb25606012941c1c1b3c4678a4`' \
	'`d7609aa9cbfc5575279ea36c48e8b5de3b710dc4`' \
	'`32519332471`' \
	'`4996761109`' \
	'`74b421ccf2eefcbd80e3716935056874f38509f5`' \
	'`7e4d4f65e7ba05080f476641dce15fd49338f4fcbcedec3ce5c06168a9b3d75d`' \
	'`70604506cfd1daa6fcb9d5910c800be65af857129c0fbf8f12f5f9d4b2959cb9`' \
	'`daa766bdc41da8455a6804cd3fcc5d0d5b3e5454da00dd8cdb4dc7060802cce4`' \
	'`1e3fdd63457d2c1bfdb1a64c647c56b5d75c5d7260de91b033a93e22a82f7f09`' \
	'`fc8f2a2f6264dc1a3e817e42f124bdbd7040a412eade3fcddf97762f59f214d8`' \
	'`e9eb18a99db71813ac8c4556a614d6a3ce4108aa`' \
	'`b4db2b329accc9a93691bda7c306cc864b07ee56`' \
	'`dcp-v2-twin-canary-v1`' \
	'`v2-13f81f321f99d1117dc931419e0bea3945ee35a5`' \
	'`v2-e028f779a18417e990911057f7db7c666f7487ca`' \
	'`v2-40f87d048813533daa1108b4316c09139acf0a8f`'; do
	grep -Fq "$exact" "$evidence"
done

for invariant in \
	'Counts are backup `1`, install invocation `1`, migration `1`, rollback `0`' \
	'`integrity_check=ok`' \
	'Admission/Incident/ExternalEvent/Result `0/0/0/0`' \
	'direct model-runtime/terminal-receipt/one-time-adoption rows `0/0/0`' \
	'`appStopped=true`' \
	'`adoptionConsumed=false`' \
	'No reinstall or retry was' \
	'No target,' \
	'owner authority'; do
	grep -Fq "$invariant" "$evidence"
done

for path in AGENTS.md README.md "$current" "$manifest" docs/PROJECT_BRIEF.md \
	docs/ROADMAP.md docs/DECISIONS.md; do
	grep -Fq 'DCP_WBC_INTEGRATION_TWIN_STAGE6_DIRECT_MODEL_STABLE_INSTALL_COMPLETE_EVIDENCE.md' "$path"
done

grep -Eq '^\| 6 \| BLOCKED \|' "$manifest"
for stage in 7 8 9; do
	grep -Eq "^\| ${stage} \| NOT STARTED \|" "$manifest"
done

if grep -Eqi 'Stage 7 (is|becomes) (active|authorized)|adoption_authority: active|runtime_authority: active|owner_acceptance: accepted' \
	"$evidence" "$manifest" "$current" AGENTS.md README.md docs/PROJECT_BRIEF.md docs/ROADMAP.md; then
	echo 'terminal evidence authority broadening detected' >&2
	exit 1
fi

! grep -Eq '(/Users/|/home/|\.codex/worktrees/|gho_[A-Za-z0-9_]+)' \
	"$evidence" "$manifest" "$current" AGENTS.md README.md docs/PROJECT_BRIEF.md docs/ROADMAP.md

bash -n scripts/i48_wbc_integration_twin_stage6_direct_install_terminal_audit.sh
git diff --check
printf 'PASS I48 Stage 6 direct-model stable install terminal evidence\n'
