#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
cd "$REPO_ROOT"

contract=docs/DCP_TASK_FIRST_NATIVE_LIFECYCLE_V1_CONTRACT.md
blocked=docs/DCP_WB_CORE_REPO_ONLY_READMISSION_NATIVE_LIFECYCLE_BLOCKED_EVIDENCE.md
evidence=docs/DCP_TASK_FIRST_NATIVE_LIFECYCLE_V1_SOURCE_COMPLETE_EVIDENCE.md
pass2=docs/DCP_TASK_FIRST_NATIVE_LIFECYCLE_V1_PASS2_BLOCKED_EVIDENCE.md
current=docs/CURRENT_OPERATING_CONTRACT.md

for path in "$contract" "$blocked" "$evidence" "$pass2" "$current" AGENTS.md docs/DECISIONS.md docs/PROJECT_BRIEF.md docs/ROADMAP.md docs/UPSTREAM_QUALIFICATION.md; do
	[[ -s "$path" ]]
done

grep -Fq 'contract_status: Pass 2 installed; startup continuation BLOCKED, runtime stopped' "$contract"
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
grep -Fq 'source_complete_status: `COMPLETE`' "$evidence"
grep -Fq 'installation_status: `NOT AUTHORIZED / NOT PERFORMED`' "$evidence"
grep -Fq '`84dbee2a701186628c1ad92950aa14639000fc0b`' "$evidence"
grep -Fq '`9374ece6efccf87dcb8a7627c97722a16d063b77`' "$evidence"
grep -Fq '`9055dd67f9e9e421e5ddaa6d0beca144a07abf0f`' "$evidence"
grep -Fq '`PRR_kwDOTydt6M8AAAABJ-fBzw`' "$evidence"
grep -Fq 'workflow `32171208324`' "$evidence"
grep -Fq '`0083_dcp_task_first_native_lifecycle_recovery_v1.sql`' "$evidence"
grep -Fq '`9cc8d8805fe61a0b72406fd428640b191516084bfd0910f1165fb897afc7ab31`' "$evidence"
grep -Fq 'Migration 0083 was not applied to the live database' "$evidence"
grep -Fq 'did not change `upstream/dcp-orchestrator.lock`' "$evidence"
grep -Fq 'evidence_status: `BLOCKED`' "$pass2"
grep -Fq 'task_first_startup_admission_continuation_missing' "$pass2"
grep -Fq '`685ae805a61f24f6c7e0628c788e2ad0cfce8d605b65143034296cb212fc757e`' "$pass2"
grep -Fq '`561e6c624aeb5030b3d69dcba1ab2f39222c2b9dd2af16e58c488ad89f518f9b`' "$pass2"
grep -Fq 'schema 82 to 83' "$pass2"
grep -Fq '73 total / zero active' "$pass2"
grep -Fq 'No executor/manual WBC' "$pass2"

for authority in AGENTS.md "$current" docs/DECISIONS.md docs/PROJECT_BRIEF.md docs/ROADMAP.md docs/UPSTREAM_QUALIFICATION.md; do
	grep -Fq 'DCP_TASK_FIRST_NATIVE_LIFECYCLE_V1_CONTRACT.md' "$authority"
	grep -Fq 'DCP_TASK_FIRST_NATIVE_LIFECYCLE_V1_SOURCE_COMPLETE_EVIDENCE.md' "$authority"
	grep -Fq 'DCP_TASK_FIRST_NATIVE_LIFECYCLE_V1_PASS2_BLOCKED_EVIDENCE.md' "$authority"
done

source upstream/dcp-orchestrator.lock
[[ "$DCP_AO_FORK_PR_URL" == https://github.com/orenvlad-ai/dcp-orchestrator/pull/74 ]]
[[ "$DCP_AO_FORK_COMMIT" == c1fc43d74cd517b7d73540f340058fa17b56ef15 ]]
[[ "$DCP_AO_FORK_TREE" == ff51ca2b1f6f9fa502b999f50a366a8e35035421 ]]
[[ "$DCP_AO_PRIOR_FORK_COMMIT" == 84dbee2a701186628c1ad92950aa14639000fc0b ]]
[[ "$DCP_AO_PRIOR_FORK_TREE" == 9374ece6efccf87dcb8a7627c97722a16d063b77 ]]
[[ "$DCP_AO_TASK_FIRST_LIFECYCLE_CONTRACT_COMMIT" == 5075235780b9c38d95faa9657a70265069d3a5c5 ]]
grep -Fq 'dcp_ao_verify_task_first_lifecycle_source "$source_dir"' lib/dcp-ao-common.sh
grep -Fq '0083_dcp_task_first_native_lifecycle_recovery_v1.sql' lib/dcp-ao-common.sh
grep -Fq 'operating_contract_revision: 2026-08-20.9' "$current"
! grep -Eq '(/Users/|/home/|\.codex/worktrees/)' "$contract"
! grep -Eq '(/Users/|/home/|\.codex/worktrees/)' "$evidence"
! grep -Eq '(/Users/|/home/|\.codex/worktrees/)' "$pass2"
bash -n scripts/i28_task_first_lifecycle_contract_audit.sh
git diff --check
printf 'PASS I28 task-first native lifecycle contract audit\n'
