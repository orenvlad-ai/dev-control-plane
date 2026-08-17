#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
cd "$REPO_ROOT"

contract=docs/DCP_WB_CORE_RELEASE_TRAIN_HANDOFF_V1_CONTRACT.md
current=docs/CURRENT_OPERATING_CONTRACT.md

for path in "$contract" "$current" AGENTS.md docs/DECISIONS.md docs/PROJECT_BRIEF.md docs/ROADMAP.md; do
	[[ -s "$path" ]]
done

grep -Fq 'contract_status: owner-authorized-pre-runtime' "$contract"
grep -Fq '`orenvlad-ai/wb-core`' "$contract"
grep -Fq '`1201929580` / `237411244`' "$contract"
grep -Fq 'exactly `task:standard`' "$contract"
grep -Fq 'exactly `scope:repo-only`' "$contract"
grep -Fq 'WBC GitHub Actions Release Train only' "$contract"
grep -Fq 'ineligible for repository `orenvlad-ai/wb-core`' "$contract"
grep -Fq 'DCP may add only' "$contract"
grep -Fq '`release:ready`' "$contract"
grep -Fq '`release:done`' "$contract"
grep -Fq '`wb-core.dcp-release-handoff/v1`' "$contract"
grep -Fq 'canonical submit before mutation' "$contract"
grep -Fq '`release_waiting`' "$contract"
grep -Fq 'three independent parallel tasks' "$contract"
grep -Fq 'one named controlled two-task conflict/arbiter cohort' "$contract"
grep -Fq 'preparation program launches no WBC task' "$contract"
grep -Fq 'terminal status is precisely' "$contract"

for authority in AGENTS.md "$current" docs/DECISIONS.md docs/PROJECT_BRIEF.md docs/ROADMAP.md; do
	grep -Fq 'DCP_WB_CORE_RELEASE_TRAIN_HANDOFF_V1_CONTRACT.md' "$authority"
done

grep -Fq 'operating_contract_revision: 2026-08-17.1' "$current"
grep -Fq 'ReleaseTrain: for wb-core' "$current"
! grep -Eq '(/Users/|/home/|\.codex/worktrees/)' "$contract"

bash -n scripts/i27_wb_core_contract_audit.sh
git diff --check
printf 'PASS I27 wb-core contract audit\n'
