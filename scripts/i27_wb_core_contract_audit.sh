#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
cd "$REPO_ROOT"

contract=docs/DCP_WB_CORE_RELEASE_TRAIN_HANDOFF_V1_CONTRACT.md
evidence=docs/DCP_WB_CORE_RELEASE_TRAIN_HANDOFF_V1_TERMINAL_EVIDENCE.md
current=docs/CURRENT_OPERATING_CONTRACT.md

for path in "$contract" "$evidence" "$current" AGENTS.md docs/DECISIONS.md docs/PROJECT_BRIEF.md docs/ROADMAP.md docs/UPSTREAM_QUALIFICATION.md; do
	[[ -s "$path" ]]
done

grep -Fq 'contract_status: terminal-complete' "$contract"
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
grep -Fq 'Current technical status is `COMPLETE`' "$contract"
grep -Fq 'current_readiness_status: complete' "$contract"
grep -Fq 'A marker-only check may never' "$contract"
grep -Fq 'same `agentRules` bytes' "$contract"
grep -Fq '`trackerIntake: {}`' "$contract"
grep -Fq 'A non-empty value, unknown extra key' "$contract"

for authority in AGENTS.md "$current" docs/DECISIONS.md docs/PROJECT_BRIEF.md docs/ROADMAP.md docs/UPSTREAM_QUALIFICATION.md; do
	grep -Fq 'DCP_WB_CORE_RELEASE_TRAIN_HANDOFF_V1_CONTRACT.md' "$authority"
done

grep -Fq 'operating_contract_revision: 2026-08-19.1' "$current"
grep -Fq 'ReleaseTrain: for wb-core' "$current"
grep -Fq 'evidence_status: BLOCKED' "$evidence"
grep -Fq 'current_unblock_status: COMPLETE' "$evidence"
grep -Fxq 'current_project_identity_status: COMPLETE' "$evidence"
grep -Fq '4735f74aedf1a1374dd4c8503799dd0761a61f22' "$evidence"
grep -Fq '4e260505a8392a2817542beb720bd3d86cecb9b7' "$evidence"
grep -Fq '32030649900' "$evidence"
grep -Fq 'marker_files=3' "$evidence"
grep -Fq 'wb_core_compatibility=qualified' "$evidence"
grep -Fq 'wb_core_compatibility=blocked' "$evidence"
grep -Fq 'incident_status: blocked-before-reservation' "$evidence"
grep -Fq 'reconciliation_status: config-correct-guard-merge-pending' "$evidence"
grep -Fq 'current_technical_status: COMPLETE' "$evidence"
grep -Fq 'c7dbfab8c0cf336eedc2f7b8d0e1a9714e906103' "$evidence"
grep -Fq '4952702321' "$evidence"
grep -Fq '32046466697' "$evidence"
grep -Fq 'b751c2195bc7aeb9882a2f5b2cd2feda870e5783' "$evidence"
grep -Fq 'post_evidence_target_status: COMPLETE' "$evidence"
grep -Fq 'ea85f26b2eb93efbfad7df9323fb7abc3cc98b57' "$evidence"
grep -Fq '4952775672' "$evidence"
grep -Fq '32047298256' "$evidence"
grep -Fq 'ca303bfebb0b5b8064351783f3d2e5e52177d09f' "$evidence"
grep -Fq '303ae44b6f7965faf02e62ff484631fc7148f585' "$evidence"
grep -Fq 'wb-core baseline changed while' "$evidence"
grep -Fq 'its exact empty defaults' "$evidence"
grep -Fq '0d2088c982dba5003cf9dbb723e756edc0debfed' "$evidence"
grep -Fq 'wbc-canary-v1' "$evidence"
grep -Fq 'c20dc4b34a198116964516e0dc76b98b094e36eb' "$evidence"
grep -Fq 'a95e9a731d483d78d9d4e66c0663c9fb148e244ae5a93c4b0f1a22ea933593ec' "$evidence"
grep -Fq '2e4b0d69593c004a4becb532ed07d59e9be087af884cdfea523fb3e918a84a64' "$evidence"
grep -Fq 'app and daemon running, ready and healthy on port 43231' "$evidence"
grep -Fq '97c4b6c000fa51c571586c39ed1d096adc7fdcdd5838d8c0ad4e15006a96a9d6' "$evidence"
grep -Fq '56f23f070e83564d51798cc236f5f799e02c30fab86041ff3985c680768dd2fa' "$evidence"
grep -Fq '2363c7ed05048c5f01977043f17d4524feceec26feefd6819f69fe3a528ad71f' "$evidence"
grep -Fq 'One exact bounded follow-on WBC task' "$evidence"
! grep -Eq '(/Users/|/home/|\.codex/worktrees/)' "$contract"
! grep -Eq '(/Users/|/home/|\.codex/worktrees/)' "$evidence"

bash -n scripts/i27_wb_core_contract_audit.sh
git diff --check
printf 'PASS I27 wb-core contract audit\n'
