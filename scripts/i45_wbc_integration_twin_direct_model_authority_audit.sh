#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
cd "$REPO_ROOT"

contract=docs/DCP_WBC_INTEGRATION_TWIN_STAGE6_DIRECT_MODEL_AUTHORITY_CONTRACT.md
manifest=docs/DCP_WBC_INTEGRATION_TWIN_CURRENT_PROGRAM_MANIFEST.md
current=docs/CURRENT_OPERATING_CONTRACT.md
blocked=docs/DCP_WBC_INTEGRATION_TWIN_STAGE6_AGGREGATE_CONTINUATION_BLOCKED_EVIDENCE.md
architecture=docs/DCP_WBC_INTEGRATION_TWIN_DCP_V2_ARCHITECTURE_CONTRACT.md

for path in "$contract" "$manifest" "$current" "$blocked" "$architecture" \
	AGENTS.md README.md docs/PROJECT_BRIEF.md docs/ROADMAP.md docs/DECISIONS.md; do
	[[ -s "$path" ]]
done

grep -Fxq 'contract_revision: 2026-08-21.1' "$contract"
grep -Fxq 'technical_status: owner-approved architecture and managed-source authority; not install, migration, runtime or provider authority' "$contract"
grep -Fxq 'owner_acceptance: not requested or synthesized' "$contract"
grep -Fxq 'manifest_revision: 2026-08-22.2' "$manifest"
grep -Fxq 'program_status: Stage 6 BLOCKED; direct-model source installed at schema 86 and stopped, adoption/live continuation not authorized' "$manifest"
grep -Fxq 'operating_contract_revision: 2026-08-22.2' "$current"

for exact in \
	'`dcp-v2-twin-canary-v1`' \
	'`v2-13f81f321f99d1117dc931419e0bea3945ee35a5`' \
	'`v2-e028f779a18417e990911057f7db7c666f7487ca`' \
	'`v2-40f87d048813533daa1108b4316c09139acf0a8f`' \
	'`78535564-a2bc-478c-80b0-207753f2152c`' \
	'`bebbf8f617f1a6fa0b9e91698fe710fe0a2bad2c`' \
	'`2fda4cae71976fd701bf3a9ccca4031f7afb630d`' \
	'`d084ae3cf0cb3e5e32ebefa197031c24a2b6392d`' \
	'`a6e3c3347bbbddd256e9edbfc541f115813249d2`' \
	'`19550a9f02b14f13be8a80214529025fd6d4fe7dc8e5bd12c5eaa1a47dd54b0c`'; do
	grep -Fq "$exact" "$contract"
done

for invariant in \
	'DCP SQLite is the only durable authority' \
	'typed provider-neutral runner is stateless transport' \
	'`dcp_review_lab_policy_task`, `sessions` or `dcp_model_action`' \
	'not replaced by dual-write' \
	'one SQLite transaction' \
	'`publication.execute/v1`' \
	'exact one-time current-Worker adoption' \
	'Equal replay returns the same adopted result' \
	'future direct tasks create zero legacy' \
	'`modelActive=true` requires both an exact DCP Action' \
	'exactly three active Actions hold slots and a fourth waits durably' \
	'Merging source does not migrate the installed database' \
	'next separate boundary is exact source pin'; do
	grep -Fiq "$invariant" "$contract"
done

for path in AGENTS.md README.md "$current" "$manifest" docs/PROJECT_BRIEF.md \
	docs/ROADMAP.md docs/DECISIONS.md "$architecture"; do
	grep -Fq 'DCP_WBC_INTEGRATION_TWIN_STAGE6_DIRECT_MODEL_AUTHORITY_CONTRACT.md' "$path"
done

grep -Fq 'technical_status: BLOCKED after the one governed aggregate installation and one same-identity start' "$blocked"
grep -Eq '^\| 6 \| BLOCKED \|' "$manifest"
for stage in 7 8 9; do
	grep -Eq "^\\| ${stage} \\| NOT STARTED \\|" "$manifest"
done

if grep -Eqi 'dual-write is authorized|Stage 7 (is|becomes) (active|authorized)|^install_authority: active$|^runtime_authority: active$' \
	"$contract" "$manifest" "$current" AGENTS.md README.md docs/PROJECT_BRIEF.md docs/ROADMAP.md; then
	echo 'authority broadening detected' >&2
	exit 1
fi

! grep -Eq '(/Users/|/home/|\.codex/worktrees/|gho_[A-Za-z0-9_]+)' \
	"$contract" "$manifest" "$current" AGENTS.md README.md docs/PROJECT_BRIEF.md docs/ROADMAP.md
! grep -Fq 'owner_acceptance: accepted' "$contract" "$manifest" "$current"

bash -n scripts/i45_wbc_integration_twin_direct_model_authority_audit.sh
git diff --check
printf 'PASS I45 WBC integration twin direct DCP-v2 model authority audit\n'
