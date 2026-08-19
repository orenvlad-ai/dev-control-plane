#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
cd "$REPO_ROOT"

contract=docs/DCP_CODEX_DIRECT_EXECUTOR_ROUTING_CONTRACT.md
permission=docs/DCP_CODEX_EXECUTOR_PERMISSION_ROUTING_CONTRACT.md
current=docs/CURRENT_OPERATING_CONTRACT.md

for path in "$contract" "$permission" "$current" AGENTS.md docs/DECISIONS.md; do
	[[ -s "$path" ]]
done

grep -Fq 'direct_executor_routing_contract_revision: 2026-08-16.1' "$contract"
grep -Fq 'permission_routing_contract_revision: 2026-08-16.2' "$permission"
grep -Fq 'DCP_CODEX_EXECUTOR_PERMISSION_ROUTING_CONTRACT.md' "$contract"
grep -Fq 'DCP_CODEX_DIRECT_EXECUTOR_ROUTING_CONTRACT.md' "$permission"
grep -Fq 'terminal `CANARY_QUALIFIED`' "$permission"

grep -Fq '019fa7f5-5f36-7101-8e07-27f8cdfbab08' "$contract"
grep -Fq 'made 16 collaboration' "$contract"
grep -Fq '019fef4e-b486-7a71-a397-aff97a54520c' "$contract"
grep -Fq 'made three hidden executor-like' "$contract"
grep -Fq 'two other checked recent WBC curator tasks made zero' "$contract"

grep -Fq 'separate visible, user-owned Codex task' "$contract"
grep -Fq 'executor thread/task id' "$contract"
grep -Fq 'executor title, pin state, destination repository, worktree, host' "$contract"
grep -Fq '`CANARY_QUALIFIED`' "$contract"
grep -Fq '`CANARY_RESTRICTED`' "$contract"
grep -Fq 'A Codex curator MUST NOT call, request or rely on collaboration `spawn_agent`' "$contract"
grep -Fq 'The first curator-side `spawn_agent` call is a dispatch defect' "$contract"
grep -Fq 'Internal DCP Worker, Reviewer and Arbiter model actions' "$contract"
grep -Fq 'zero curator-side `spawn_agent` calls' "$contract"
grep -Fq 'zero platform approval' "$contract"
grep -Fq 'exactly one terminal technical handoff' "$contract"

for authority in AGENTS.md "$current" docs/DECISIONS.md; do
	grep -Fq 'DCP_CODEX_DIRECT_EXECUTOR_ROUTING_CONTRACT.md' "$authority"
	grep -Fq 'DCP_CODEX_EXECUTOR_PERMISSION_ROUTING_CONTRACT.md' "$authority"
done

grep -Fq 'operating_contract_revision: 2026-08-19.4' "$current"
grep -Fq 'Subagents: curator-side collaboration spawn_agent/subagent calls are forbidden' "$current"
grep -Fq 'Acceptance: zero curator spawn_agent calls' "$current"

! grep -Eq '(/Users/|/home/|\.codex/worktrees/)' "$contract"

bash -n scripts/direct_executor_routing_audit.sh
git diff --check
printf 'PASS direct executor routing audit\n'
