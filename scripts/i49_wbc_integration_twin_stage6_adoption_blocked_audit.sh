#!/usr/bin/env bash
set -euo pipefail

evidence=docs/DCP_WBC_INTEGRATION_TWIN_STAGE6_SAME_IDENTITY_ADOPTION_BLOCKED_EVIDENCE.md
manifest=docs/DCP_WBC_INTEGRATION_TWIN_CURRENT_PROGRAM_MANIFEST.md
current=docs/CURRENT_OPERATING_CONTRACT.md
stable=docs/DCP_WBC_INTEGRATION_TWIN_STAGE6_DIRECT_MODEL_STABLE_INSTALL_COMPLETE_EVIDENCE.md
status='program_status: Stage 6 FINAL FREEZE/BLOCKED; schema 87 stopped after one adoption transaction applied but gateway receipt validation failed; zero provider effect'

for path in "$evidence" "$manifest" "$current" "$stable" AGENTS.md README.md \
	docs/PROJECT_BRIEF.md docs/ROADMAP.md docs/DECISIONS.md; do
	[[ -s "$path" ]]
done

grep -Fxq 'evidence_revision: 2026-08-22.1' "$evidence"
grep -Fxq 'technical_status: BLOCKED before live adoption and governed continuation by DCP_V2_PUBLICATION_REVISION_PR_BINDING_MISSING' "$evidence"
grep -Fxq 'owner_acceptance: not requested or synthesized' "$evidence"
grep -Fxq 'manifest_revision: 2026-08-23.1' "$manifest"
grep -Fxq "$status" "$manifest"
grep -Fxq 'operating_contract_revision: 2026-08-23.1' "$current"

for exact in \
	'`01a0282b-bc36-76c0-af83-4a8e4ec5a71e`' \
	'`DCP · S6 adoption · И34`' \
	'`dcp-v2-twin-canary-v1`' \
	'`v2-13f81f321f99d1117dc931419e0bea3945ee35a5`' \
	'`v2-e028f779a18417e990911057f7db7c666f7487ca`' \
	'`v2-40f87d048813533daa1108b4316c09139acf0a8f`' \
	'`78535564-a2bc-478c-80b0-207753f2152c`' \
	'`bebbf8f617f1a6fa0b9e91698fe710fe0a2bad2c`' \
	'`2fda4cae71976fd701bf3a9ccca4031f7afb630d`' \
	'`e9eb18a99db71813ac8c4556a614d6a3ce4108aa`' \
	'`b4db2b329accc9a93691bda7c306cc864b07ee56`' \
	'`fc8f2a2f6264dc1a3e817e42f124bdbd7040a412eade3fcddf97762f59f214d8`' \
	'`1e3fdd63457d2c1bfdb1a64c647c56b5d75c5d7260de91b033a93e22a82f7f09`' \
	'`v2-0e1aadfb444bc4d9f4c90c8bf936a0ebec125300`' \
	'`v2-06b20be020812369bf4286fd335aa8f5281d15e2`' \
	'`v2-eb68fd8ab844afa1e0639deebc6aca641704a88a`'; do
	grep -Fq "$exact" "$evidence"
done

for invariant in \
	'DCP_V2_PUBLICATION_REVISION_PR_BINDING_MISSING' \
	'`completeWorkerReceipt`' \
	'`publicationOutcome`' \
	'`completeChecks`' \
	'`PRNumber=0`' \
	'`integrity_check=ok`' \
	'foreign-key violations `0`' \
	'Admission/Incident/ExternalEvent/Result `0/0/0/0`' \
	'model-runtime/terminal-receipt/adoption `0/0/0`' \
	'`adoptionConsumed=false`' \
	'No adoption authority package' \
	'no live adoption' \
	'zero provider effect'; do
	grep -Fq "$invariant" "$evidence"
done

for path in AGENTS.md README.md "$current" "$manifest" docs/PROJECT_BRIEF.md \
	docs/ROADMAP.md docs/DECISIONS.md; do
	grep -Fq 'DCP_WBC_INTEGRATION_TWIN_STAGE6_SAME_IDENTITY_ADOPTION_BLOCKED_EVIDENCE.md' "$path"
done

grep -Eq '^\| 6 \| FINAL FREEZE/BLOCKED \|' "$manifest"
for stage in 7 8 9; do
	grep -Eq "^\| ${stage} \| NOT STARTED \|" "$manifest"
done

if grep -Eqi 'adoptionConsumed=true|Stage 7 (is|becomes) (active|authorized)|owner_acceptance: accepted|runtime_authority: active' \
	"$evidence" "$manifest" "$current" AGENTS.md README.md docs/PROJECT_BRIEF.md docs/ROADMAP.md; then
	echo 'blocked evidence authority broadening detected' >&2
	exit 1
fi

! grep -Eq '(/Users/|/home/|\.codex/worktrees/|gho_[A-Za-z0-9_]+)' \
	"$evidence" "$manifest" "$current" AGENTS.md README.md docs/PROJECT_BRIEF.md docs/ROADMAP.md

bash -n scripts/i49_wbc_integration_twin_stage6_adoption_blocked_audit.sh
git diff --check
printf 'PASS I49 Stage 6 same-identity adoption blocked evidence\n'
