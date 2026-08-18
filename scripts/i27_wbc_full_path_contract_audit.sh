#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
cd "$REPO_ROOT"

contract=docs/DCP_WB_CORE_END_TO_END_RELEASE_DEPLOY_V1_CONTRACT.md
current=docs/CURRENT_OPERATING_CONTRACT.md

for path in "$contract" "$current" AGENTS.md docs/DECISIONS.md docs/PROJECT_BRIEF.md docs/ROADMAP.md docs/UPSTREAM_QUALIFICATION.md; do
	[[ -s "$path" ]]
done

grep -Fq 'contract_status: owner-approved pre-runtime integration authority' "$contract"
grep -Fq '`wbc-canary-v1` / `1` / `wb-core-1`' "$contract"
grep -Fq '`e8cca45f3995b8181fe81ead154f7a933dbacbe8`' "$contract"
grep -Fq 'initial worker action sequence `71` once' "$contract"
grep -Fq 'reviewer sequence `72` once' "$contract"
grep -Fq 'admission sequence `31` once' "$contract"
grep -Fq '`base-behind-after-admission`' "$contract"
grep -Fq 'one mechanical' "$contract"
grep -Fq 'two-parent Git merge' "$contract"
grep -Fq 'normal fast-forward' "$contract"
grep -Fq 'never force/rebase' "$contract"
grep -Fq 'one immutable generation/evidence row' "$contract"
grep -Fq 'No timer, heartbeat, watcher, unbounded poller or AI retry' "$contract"
grep -Fq 'inherits no prior review, check or admission' "$contract"
grep -Fq 'Missing, pending, duplicate, wrong-head, cancelled' "$contract"
grep -Fq 'Global three-model-action' "$contract"
grep -Fq '`wb-core.dcp-release-handoff/v1`' "$contract"
grep -Fq '`repo-only`' "$contract"
grep -Fq '`live-runtime`' "$contract"
grep -Fq '`release:done`' "$contract"
grep -Fq '`release:production`' "$contract"
grep -Fq '`release:halted`' "$contract"
grep -Fq '`wb_core_eu_hosted_runtime_active`' "$contract"
grep -Fq 'DCP `MergePullRequest` is statically ineligible' "$contract"
grep -Fq '`modelActive`' "$contract"
grep -Fq '`workflowActive`' "$contract"
grep -Fq '`Waiting for Release Train`' "$contract"
grep -Fq '`Waiting for deploy`' "$contract"
grep -Fq '`prefers-reduced-motion`' "$contract"
grep -Fq 'Generic stock' "$contract"
grep -Fq 'one new live-runtime task terminal `release:production`' "$contract"
grep -Fq 'zero Codex platform approval prompts' "$contract"

for authority in AGENTS.md "$current" docs/DECISIONS.md docs/PROJECT_BRIEF.md docs/ROADMAP.md docs/UPSTREAM_QUALIFICATION.md; do
	grep -Fq 'DCP_WB_CORE_END_TO_END_RELEASE_DEPLOY_V1_CONTRACT.md' "$authority"
done

grep -Fq 'operating_contract_revision: 2026-08-18.2' "$current"
grep -Fq 'repo-only requires release:done' "$current"
grep -Fq 'live-runtime requires release:production' "$current"
! grep -Eq '(/Users/|/home/|\.codex/worktrees/)' "$contract"

bash -n scripts/i27_wbc_full_path_contract_audit.sh
git diff --check
printf 'PASS I27 WBC full release/deploy path contract audit\n'
