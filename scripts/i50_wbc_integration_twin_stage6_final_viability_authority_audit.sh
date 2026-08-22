#!/usr/bin/env bash
set -euo pipefail

contract=docs/DCP_WBC_INTEGRATION_TWIN_STAGE6_FINAL_VIABILITY_CONTRACT.md
manifest=docs/DCP_WBC_INTEGRATION_TWIN_CURRENT_PROGRAM_MANIFEST.md
current=docs/CURRENT_OPERATING_CONTRACT.md
blocked=docs/DCP_WBC_INTEGRATION_TWIN_STAGE6_SAME_IDENTITY_ADOPTION_BLOCKED_EVIDENCE.md
status='program_status: Stage 6 BLOCKED before adoption on DCP_V2_PUBLICATION_REVISION_PR_BINDING_MISSING; one final viability source correction authorized; schema 86 stopped and zero provider effect'

for path in "$contract" "$manifest" "$current" "$blocked" AGENTS.md README.md \
	docs/PROJECT_BRIEF.md docs/ROADMAP.md docs/DECISIONS.md; do
	[[ -s "$path" ]]
done

grep -Fxq 'authority_revision: 2026-08-22.1' "$contract"
grep -Fxq 'technical_status: ACTIVE for one aggregate managed-source correction only; live schema 86 remains stopped and unconsumed' "$contract"
grep -Fxq 'owner_acceptance: not requested or synthesized' "$contract"
grep -Fxq 'manifest_revision: 2026-08-22.4' "$manifest"
grep -Fxq "$status" "$manifest"
grep -Fxq 'operating_contract_revision: 2026-08-22.4' "$current"

for exact in \
	'`dcp-v2-twin-canary-v1`' \
	'`v2-13f81f321f99d1117dc931419e0bea3945ee35a5`' \
	'`v2-e028f779a18417e990911057f7db7c666f7487ca`' \
	'`v2-40f87d048813533daa1108b4316c09139acf0a8f`' \
	'`78535564-a2bc-478c-80b0-207753f2152c`' \
	'`bebbf8f617f1a6fa0b9e91698fe710fe0a2bad2c`' \
	'`2fda4cae71976fd701bf3a9ccca4031f7afb630d`' \
	'`e9eb18a99db71813ac8c4556a614d6a3ce4108aa`' \
	'`b4db2b329accc9a93691bda7c306cc864b07ee56`' \
	'`fc8f2a2f6264dc1a3e817e42f124bdbd7040a412eade3fcddf97762f59f214d8`'; do
	grep -Fq "$exact" "$contract"
done

for invariant in \
	'DCP_V2_PUBLICATION_REVISION_PR_BINDING_MISSING' \
	'`0087`' \
	'`provider_bound`' \
	'`PRNumber=0`' \
	'Publication success' \
	'advance the same Task' \
	'`checks.observe/v1`' \
	'immutable predecessor-Revision chain' \
	'`admission.enqueue/v1`' \
	'`artifact_source_sha == merge_sha == deployed_sha`' \
	'four Tasks contending for three slots' \
	'at most one substantive findings-repair' \
	'A second source pull request' \
	'final `FREEZE/BLOCKED`' \
	'Stage 7 may become eligible' \
	'owner acceptance'; do
	grep -Fq "$invariant" "$contract"
done

for path in AGENTS.md README.md "$current" "$manifest" docs/PROJECT_BRIEF.md \
	docs/ROADMAP.md docs/DECISIONS.md; do
	grep -Fq 'DCP_WBC_INTEGRATION_TWIN_STAGE6_FINAL_VIABILITY_CONTRACT.md' "$path"
done

grep -Fq 'DCP_V2_PUBLICATION_REVISION_PR_BINDING_MISSING' "$blocked"
grep -Fq 'adoptionConsumed=false' "$blocked"
grep -Eq '^\| 6 \| BLOCKED \|' "$manifest"
for stage in 7 8 9; do
	grep -Eq "^\| ${stage} \| NOT STARTED \|" "$manifest"
done

if grep -Eqi 'adoptionConsumed=true|Stage 7 (is|becomes) (active|authorized)|owner_acceptance: accepted|runtime_authority: active' \
	"$contract" "$manifest" "$current" AGENTS.md README.md docs/PROJECT_BRIEF.md docs/ROADMAP.md; then
	echo 'final viability authority broadening detected' >&2
	exit 1
fi

! grep -Eq '(/Users/|/home/|\.codex/worktrees/|gho_[A-Za-z0-9_]+)' \
	"$contract" "$manifest" "$current" AGENTS.md README.md docs/PROJECT_BRIEF.md docs/ROADMAP.md

bash -n scripts/i50_wbc_integration_twin_stage6_final_viability_authority_audit.sh
git diff --check
printf 'PASS I50 Stage 6 final viability architecture/source authority\n'
