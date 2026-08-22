#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
cd "$REPO_ROOT"

evidence=docs/DCP_WBC_INTEGRATION_TWIN_STAGE6_AGGREGATE_CONTINUATION_BLOCKED_EVIDENCE.md
contract=docs/DCP_WBC_INTEGRATION_TWIN_STAGE6_AGGREGATE_INSTALL_CONTINUATION_CONTRACT.md
manifest=docs/DCP_WBC_INTEGRATION_TWIN_CURRENT_PROGRAM_MANIFEST.md
current=docs/CURRENT_OPERATING_CONTRACT.md

for path in "$evidence" "$contract" "$manifest" "$current" AGENTS.md README.md \
	docs/PROJECT_BRIEF.md docs/ROADMAP.md docs/DECISIONS.md; do
	[[ -s "$path" ]]
done

grep -Fxq 'evidence_revision: 2026-08-21.1' "$evidence"
grep -Fxq 'technical_status: BLOCKED after the one governed aggregate installation and one same-identity start' "$evidence"
grep -Fxq 'owner_acceptance: not requested or synthesized' "$evidence"

for exact in \
	'`01a02392-c430-7a11-a081-5de18a278f46`' \
	'`DCP · S6 seam · И33`' \
	'`b0c2b6df76adf205229e49c48a1d7277aa7b5059`' \
	'`d084ae3cf0cb3e5e32ebefa197031c24a2b6392d`' \
	'`a6e3c3347bbbddd256e9edbfc541f115813249d2`' \
	'`32477135149`' \
	'`4992765757`' \
	'`747cda40e2a8816c4fdf8940c302e1374bfc2138`' \
	'`085c23a0c1b43654b6885cea75209a70f1a18b68`' \
	'`4a2c2808b5edd1e029bf0992abedcf78c02f7c39`' \
	'`32479309952`' \
	'`4992960012`' \
	'`i12-20260821T120041Z`' \
	'`19550a9f02b14f13be8a80214529025fd6d4fe7dc8e5bd12c5eaa1a47dd54b0c`' \
	'`dcp-v2-twin-canary-v1`' \
	'`v2-13f81f321f99d1117dc931419e0bea3945ee35a5`' \
	'`v2-e028f779a18417e990911057f7db7c666f7487ca`' \
	'`v2-40f87d048813533daa1108b4316c09139acf0a8f`' \
	'`dcp-model-dcp-v2-twin-canary-v1-worker-1`' \
	'`78535564-a2bc-478c-80b0-207753f2152c`' \
	'`bebbf8f617f1a6fa0b9e91698fe710fe0a2bad2c`' \
	'`2fda4cae71976fd701bf3a9ccca4031f7afb630d`' \
	'`375b9b2d0b4c2fce6f2c417850553f79e24a0d92`' \
	'`1272f6a772ba07eca7bdde5f1da7f53110da183b`'; do
	grep -Fq "$exact" "$evidence"
done

for invariant in \
	'exactly once' \
	'No migration, direct SQLite write, blind kill, rollback' \
	'native Action durably succeeded' \
	'DCP-v2 Action as `running`' \
	'false terminal runtime/model projection' \
	'canary remote branch, PR, check, review, Admission manifest' \
	'no Reviewer, repair, arbiter or duplicate provider/model effect' \
	'legacy second-authority bridge must be simplified or removed' \
	'Stage 7, WBC shadow and cutover' \
	'program manifest'; do
	grep -Fq "$invariant" "$evidence"
done

grep -Fxq 'manifest_revision: 2026-08-22.3' "$manifest"
grep -Fxq 'program_status: Stage 6 BLOCKED before adoption; DCP_V2_PUBLICATION_REVISION_PR_BINDING_MISSING; schema 86 stopped and zero provider effect' "$manifest"
grep -Fxq 'operating_contract_revision: 2026-08-22.3' "$current"
grep -Fq 'technical_status: SPENT; one install/start completed; Stage 6 BLOCKED by false terminal runtime/model projection' "$contract"
grep -Eq '^\| 6 \| BLOCKED \|' "$manifest"

for path in AGENTS.md README.md "$current" "$manifest" docs/PROJECT_BRIEF.md docs/ROADMAP.md docs/DECISIONS.md; do
	grep -Fq 'DCP_WBC_INTEGRATION_TWIN_STAGE6_AGGREGATE_CONTINUATION_BLOCKED_EVIDENCE.md' "$path"
done

! grep -Eq '(/Users/|/home/|\.codex/worktrees/|gho_[A-Za-z0-9_]+)' "$evidence" "$manifest" "$current"
! grep -Fq 'owner_acceptance: accepted' "$evidence" "$manifest" "$current"

bash -n scripts/i44_wbc_integration_twin_stage6_aggregate_terminal_audit.sh
git diff --check
printf 'PASS I44 WBC integration twin Stage 6 aggregate terminal audit\n'
