#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
cd "$REPO_ROOT"

contract=docs/DCP_TASK_FIRST_NATIVE_LIFECYCLE_V1_CONTRACT.md
blocked=docs/DCP_WB_CORE_REPO_ONLY_READMISSION_NATIVE_LIFECYCLE_BLOCKED_EVIDENCE.md
current=docs/CURRENT_OPERATING_CONTRACT.md

for path in "$contract" "$blocked" "$current" AGENTS.md docs/DECISIONS.md docs/PROJECT_BRIEF.md docs/ROADMAP.md docs/UPSTREAM_QUALIFICATION.md; do
	[[ -s "$path" ]]
done

grep -Fq 'contract_status: owner-authorized architecture/source pass; source not installed' "$contract"
grep -Fq '`wbc-canary-v1` / `1` / `wb-core-1`' "$contract"
grep -Fq '`26044c696651ce5873748ec3f920d40e77c5686c`' "$contract"
grep -Fq '`18c54338-df31-4471-a344-4db6648ff4e3`' "$contract"
grep -Fq 'admission `32` waiting; generation `1` admitted' "$contract"
grep -Fq 'schema `82`' "$contract"
grep -Fq 'SHA-256 `9cc8d8805fe61a0b72406fd428640b191516084bfd0910f1165fb897afc7ab31`' "$contract"
grep -Fq 'one central evaluator and one result value' "$contract"
grep -Fq 'The evaluator is provider-neutral' "$contract"
grep -Fq '`runtimeRequirement`: `none` or `exactModelRuntime`' "$contract"
grep -Fq 'worker/repair launching or running' "$contract"
grep -Fq 'reviewer/arbiter launching or running' "$contract"
grep -Fq 'admission waiting/claimed/admitted' "$contract"
grep -Fq 'Human Gate' "$contract"
grep -Fq 'any live native/model process without one matching registered' "$contract"
grep -Fq 'any launching/running action without exactly one matching process' "$contract"
grep -Fq 'more than three globally active' "$contract"
grep -Fq 'task phase ×' "$contract"
grep -Fq 'multiple readmission generations' "$contract"
grep -Fq 'zero duplicate task, card, session' "$contract"
grep -Fq 'disposable read-only snapshot' "$contract"
grep -Fq 'one additive immutable future migration after `0082`' "$contract"
grep -Fq 'Tests apply it only to' "$contract"
grep -Fq 'DCP `MergePullRequest`, deploy, SSH' "$contract"
grep -Fq 'MUST NOT change `upstream/dcp-orchestrator.lock`' "$contract"
grep -Fq 'owner-authorized pin/install' "$contract"
grep -Fq 'Status: `BLOCKED`' "$blocked"

for authority in AGENTS.md "$current" docs/DECISIONS.md docs/PROJECT_BRIEF.md docs/ROADMAP.md docs/UPSTREAM_QUALIFICATION.md; do
	grep -Fq 'DCP_TASK_FIRST_NATIVE_LIFECYCLE_V1_CONTRACT.md' "$authority"
done

grep -Fq 'operating_contract_revision: 2026-08-18.11' "$current"
! grep -Eq '(/Users/|/home/|\.codex/worktrees/)' "$contract"
bash -n scripts/i28_task_first_lifecycle_contract_audit.sh
git diff --check
printf 'PASS I28 task-first native lifecycle contract audit\n'
