#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
cd "$REPO_ROOT"

manifest=docs/DCP_WBC_INTEGRATION_TWIN_CURRENT_PROGRAM_MANIFEST.md
current=docs/CURRENT_OPERATING_CONTRACT.md
brief=docs/PROJECT_BRIEF.md
roadmap=docs/ROADMAP.md
decisions=docs/DECISIONS.md
architecture=docs/DCP_WBC_INTEGRATION_TWIN_DCP_V2_ARCHITECTURE_CONTRACT.md
stage6=docs/DCP_WBC_INTEGRATION_TWIN_STAGE6_POST_SUBMIT_NATIVE_SHELL_CORRECTION_CONTRACT.md

active=(README.md AGENTS.md "$current" "$manifest" "$brief" "$roadmap" "$decisions" "$architecture")
linked=(
	docs/DCP_WBC_INTEGRATION_TWIN_STAGE2_SELECTEL_PERSISTENT_CELL_CONTRACT.md
	docs/DCP_WBC_INTEGRATION_TWIN_STAGE2_TERMINAL_EVIDENCE.md
	docs/DCP_WBC_INTEGRATION_TWIN_STAGE3_4_COMBINED_EXECUTION_CONTRACT.md
	docs/DCP_WBC_INTEGRATION_TWIN_STAGE3_TERMINAL_EVIDENCE.md
	docs/DCP_WBC_INTEGRATION_TWIN_STAGE4_SOURCE_COMPLETE_EVIDENCE.md
	docs/DCP_WBC_INTEGRATION_TWIN_STAGE5_INSTALL_ACTIVATION_CONTRACT.md
	docs/DCP_WBC_INTEGRATION_TWIN_STAGE5_TERMINAL_EVIDENCE.md
	"$stage6"
)

for path in "${active[@]}" "${linked[@]}"; do
	[[ -s "$path" ]]
done

[[ "$(find docs -maxdepth 1 -name 'DCP_WBC_INTEGRATION_TWIN_CURRENT_PROGRAM_MANIFEST.md' -print | wc -l | tr -d ' ')" == 1 ]]
grep -Fxq 'manifest_revision: 2026-08-21.1' "$manifest"
grep -Fxq 'program_status: Stage 6 BLOCKED before model launch' "$manifest"
grep -Fxq 'operating_contract_revision: 2026-08-21.1' "$current"

for needle in \
	'one submit' \
	'one stable Task/card' \
	'immutable exact-head Revisions' \
	'durable Commands' \
	'one bounded Worker' \
	'fresh context-free Reviewer' \
	'at most one task-level findings' \
	'mechanical FIFO Admission' \
	'repository-owned Release Train' \
	'verified deployed SHA, health and provenance proof' \
	'DCP and model roles never merge or deploy' \
	'At most three globally active model Actions' \
	'`workflowActive` is separate from truthful `modelActive`' \
	'Human Gate is only a' \
	'genuine owner decision' \
	'old actor off before new actor on' \
	'owner_acceptance: not requested or synthesized'; do
	grep -Fq "$needle" "$manifest"
done

for exact in \
	'`dcp-v2-twin-canary-v1`' \
	'`v2-13f81f321f99d1117dc931419e0bea3945ee35a5`' \
	'`v2-e028f779a18417e990911057f7db7c666f7487ca`' \
	'`v2-40f87d048813533daa1108b4316c09139acf0a8f`' \
	'`dcp-wbc-integration-lab-1`' \
	'`11401ff6eadb80fd87e48229fb8c5458095a63b1`' \
	'`91bf6e25ec1b0e0f971ad36f7b80272aded2482c`' \
	'`i12-20260821T043432Z`' \
	'`098056d800d41f666708b7697d6ccef9f3b5cd2e077a939d89dcf0b1f35767e2`' \
	'`375b9b2d0b4c2fce6f2c417850553f79e24a0d92`' \
	'`26044c696651ce5873748ec3f920d40e77c5686c`'; do
	grep -Fq "$exact" "$manifest"
done

for stage in 1 2 3 4 5; do
	grep -Eq "^\\| ${stage} \\| COMPLETE \\|" "$manifest"
done
grep -Eq '^\| 6 \| BLOCKED \|' "$manifest"
for stage in 7 8 9; do
	grep -Eq "^\\| ${stage} \\| NOT STARTED \\|" "$manifest"
done

for needle in \
	'DCP live-runtime task' \
	'DCP synthetic task' \
	'reserved command identity drift' \
	'`modelActive=true`' \
	'no runtime id' \
	'Do not authorize another one-defect/one-PR/one-install loop' \
	'exact disposable schema-85 snapshot' \
	'one managed-source' \
	'worktree;' \
	'no PR/install per' \
	'one aggregate source package' \
	'Hard stop:' \
	'Simplify' \
	'or remove the legacy second-authority bridge' \
	'Curator rotation bootstrap/readback'; do
	grep -Fq "$needle" "$manifest"
done

for path in README.md AGENTS.md "$current" "$brief" "$roadmap" "$decisions" "$architecture" "${linked[@]}"; do
	grep -Fq 'DCP_WBC_INTEGRATION_TWIN_CURRENT_PROGRAM_MANIFEST.md' "$path"
done

grep -Fq 'technical_status: SUPERSEDED; recovery installed; Stage 6 BLOCKED before model launch' "$stage6"
grep -Fq 'current_program_role: immutable predecessor authority; source/install scope spent' "$stage6"
grep -Fq 'current_program_projection: Stages 1-5 COMPLETE; Stage 6 BLOCKED before model launch' "$architecture"
grep -Fq 'Stage 1 snapshot, not current live-runtime' "$architecture"
grep -Fq 'consolidate current authority and rotate the Stage 6 curator' "$decisions"
grep -Fq 'source-only aggregate DCP-v2 to legacy-native seam closure' "$roadmap"
grep -Fq 'Stages 1-5 of the WBC integration twin are technically `COMPLETE`' "$brief"
grep -Fq '`BLOCKED before model launch`' "$brief"

if grep -Eqi 'Stage 6 remains evidence-merge gated|Stage 6 remains prohibited|Stages 1-5 (allow|admit) no DCP submit|Stage 3 is the next active gate|technical_status: ACTIVE' \
	README.md AGENTS.md "$current" "$manifest" "$brief" "$roadmap"; then
	echo 'contradictory active stage claim' >&2
	exit 1
fi

for path in README.md AGENTS.md "$current" "$manifest" "$brief" "$roadmap"; do
	! grep -Eq '(/Users/|/home/|\.codex/worktrees/|gho_[A-Za-z0-9_]+)' "$path"
	! grep -Fq 'owner_acceptance: accepted' "$path"
done

bash -n scripts/i42_wbc_integration_twin_current_manifest_audit.sh
git diff --check
printf 'PASS I42 WBC integration twin current program manifest audit\n'
