#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
cd "$REPO_ROOT"

contract=docs/DCP_WB_CORE_CI_TRUTH_LIFECYCLE_UX_V1_CONTRACT.md
current=docs/CURRENT_OPERATING_CONTRACT.md

for path in "$contract" "$current" AGENTS.md docs/DECISIONS.md docs/PROJECT_BRIEF.md docs/ROADMAP.md docs/UPSTREAM_QUALIFICATION.md; do
	[[ -s "$path" ]]
done

grep -Fq 'contract_status: owner-authorized; source merged; immutable pin/install pending' "$contract"
grep -Fq '`wbc-canary-v1`' "$contract"
grep -Fq '`wb-core-1`' "$contract"
grep -Fq '`e8cca45f3995b8181fe81ead154f7a933dbacbe8`' "$contract"
grep -Fq '`32048996893`' "$contract"
grep -Fq 'sequence `71`' "$contract"
grep -Fq 'configured required-check name' "$contract"
grep -Fq 'Additional non-required checks are observational' "$contract"
grep -Fq 'current complex train' "$contract"
grep -Fq 'future simplified train' "$contract"
grep -Fq 'DCP `MergePullRequest`' "$contract"
grep -Fq '`release:ready` remains exact-head guarded and' "$contract"
grep -Fq '`modelActive`' "$contract"
grep -Fq '`workflowActive`' "$contract"
grep -Fq '`Waiting for CI/GitHub update`' "$contract"
grep -Fq '`Waiting for Release Train`' "$contract"
grep -Fq '`prefers-reduced-motion`' "$contract"
grep -Fq 'Generic stock `ready_to_merge` notification creation MUST be suppressed' "$contract"
grep -Fq 'queue exactly one fresh' "$contract"
grep -Fq 'No second initial worker' "$contract"
grep -Fq 'ordinary reviewed managed-source PR' "$contract"
grep -Fq 'one-card identity' "$contract"
grep -Fq '93246658c34a7d5cdeb7bb42a7f3496308923608' "$contract"
grep -Fq '828c3c6b1b5a5700bde8495a435d40ee3609ec9d' "$contract"

for authority in AGENTS.md "$current" docs/DECISIONS.md docs/PROJECT_BRIEF.md docs/ROADMAP.md docs/UPSTREAM_QUALIFICATION.md; do
	grep -Fq 'DCP_WB_CORE_CI_TRUTH_LIFECYCLE_UX_V1_CONTRACT.md' "$authority"
done

grep -Fq 'operating_contract_revision: 2026-08-17.9' "$current"
! grep -Eq '(/Users/|/home/|\.codex/worktrees/)' "$contract"

bash -n scripts/i27_wbc_ci_lifecycle_contract_audit.sh
git diff --check
printf 'PASS I27 WBC CI truth and lifecycle UX contract audit\n'
