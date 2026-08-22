#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
cd "$REPO_ROOT"

evidence=docs/DCP_WBC_INTEGRATION_TWIN_STAGE6_DIRECT_MODEL_SOURCE_COMPLETE_EVIDENCE.md
contract=docs/DCP_WBC_INTEGRATION_TWIN_STAGE6_DIRECT_MODEL_AUTHORITY_CONTRACT.md
manifest=docs/DCP_WBC_INTEGRATION_TWIN_CURRENT_PROGRAM_MANIFEST.md
current=docs/CURRENT_OPERATING_CONTRACT.md

for path in "$evidence" "$contract" "$manifest" "$current" AGENTS.md README.md \
	docs/PROJECT_BRIEF.md docs/ROADMAP.md docs/DECISIONS.md; do
	[[ -s "$path" ]]
done

grep -Fxq 'technical_status: COMPLETE at source; NOT INSTALLED' "$evidence"
grep -Fxq 'owner_acceptance: not requested or synthesized' "$evidence"
grep -Fxq 'manifest_revision: 2026-08-22.5' "$manifest"
grep -Fxq 'program_status: Stage 6 final source merged; one reviewed pin/install/live authority proposed; schema 86 stopped, adoption unconsumed and zero provider effect' "$manifest"
grep -Fxq 'operating_contract_revision: 2026-08-22.5' "$current"

for exact in \
	'`81525ccfb3adb118b54d69bff39efaecd79c621a`' \
	'`4993514607`' \
	'`3aa42b7afda620331d111ba24299e2917821e720`' \
	'`21f04ffbe107cb841308d5fb252136531b291d9d`' \
	'`b4db2b329accc9a93691bda7c306cc864b07ee56`' \
	'`32495591702`' \
	'`4994657860`' \
	'`e9eb18a99db71813ac8c4556a614d6a3ce4108aa`' \
	'`6c0f0f41251bc60a6d01fdd3a00d4eca389c2d37a4f1e64ffece2fbf2c9ffdc9`' \
	'`dcp-v2-twin-canary-v1`' \
	'`v2-13f81f321f99d1117dc931419e0bea3945ee35a5`' \
	'`v2-e028f779a18417e990911057f7db7c666f7487ca`' \
	'`v2-40f87d048813533daa1108b4316c09139acf0a8f`' \
	'`bebbf8f617f1a6fa0b9e91698fe710fe0a2bad2c`' \
	'`2fda4cae71976fd701bf3a9ccca4031f7afb630d`'; do
	grep -Fq "$exact" "$evidence"
done

for invariant in \
	'only durable' \
	'stateless transport only' \
	'Equal replay is inert' \
	'Future direct DCP-v2 tasks create zero legacy' \
	'440/440' \
	'not installed' \
	'exact merged-source pin' \
	'grants no install'; do
	grep -Fiq "$invariant" "$evidence" "$manifest" "$current"
done

grep -Eq '^\| 6 \| ACTIVE \|' "$manifest"
for stage in 7 8 9; do
	grep -Eq "^\\| ${stage} \\| NOT STARTED \\|" "$manifest"
done

for path in AGENTS.md README.md "$current" "$manifest" docs/PROJECT_BRIEF.md \
	docs/ROADMAP.md docs/DECISIONS.md; do
	grep -Fq 'DCP_WBC_INTEGRATION_TWIN_STAGE6_DIRECT_MODEL_SOURCE_COMPLETE_EVIDENCE.md' "$path"
done

if grep -Eqi 'Stage 7 (is|becomes) (active|authorized)|^install_authority: active$|^runtime_authority: active$' \
	"$evidence" "$manifest" "$current" AGENTS.md README.md docs/PROJECT_BRIEF.md docs/ROADMAP.md; then
	echo 'source-evidence authority broadening detected' >&2
	exit 1
fi

! grep -Eq '(/Users/|/home/|\.codex/worktrees/|gho_[A-Za-z0-9_]+)' \
	"$evidence" "$manifest" "$current" AGENTS.md README.md docs/PROJECT_BRIEF.md docs/ROADMAP.md
! grep -Fq 'owner_acceptance: accepted' "$evidence" "$manifest" "$current"

bash -n scripts/i46_wbc_integration_twin_direct_model_source_audit.sh
git diff --check
printf 'PASS I46 WBC integration twin direct-model source-complete audit\n'
