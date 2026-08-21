#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
cd "$REPO_ROOT"

contract=docs/DCP_WBC_INTEGRATION_TWIN_DCP_V2_ARCHITECTURE_CONTRACT.md
current=docs/CURRENT_OPERATING_CONTRACT.md

for path in "$contract" "$current" AGENTS.md docs/PROJECT_BRIEF.md docs/ROADMAP.md docs/DECISIONS.md docs/TARGET_ARCHITECTURE_V1.md; do
	[[ -s "$path" ]]
done

grep -Fq 'contract_status: owner-approved architecture-only; not runtime authority' "$contract"
grep -Fq 'program_stage: 1 of 9' "$contract"
grep -Fq 'preferred_future_repository: `orenvlad-ai/dcp-wbc-integration-lab`' "$contract"
grep -Fq 'external_resources_created_by_this_stage: 0' "$contract"
grep -Fq 'Task -> immutable exact-head Revision -> durable Command -> bounded model Action -> Admission -> Release/Deployment result' "$contract"
grep -Fq '`task_first_startup_admission_continuation_missing`' "$contract"
grep -Fq 'schema `83`, task revision `23`' "$contract"
grep -Fq 'app and daemon stopped' "$contract"
grep -Fq 'Every state transition that requires further work atomically persists the' "$contract"
grep -Fq 'next durable command in the same SQLite transaction' "$contract"
grep -Fq 'drains durable commands idempotently on the exact triggering' "$contract"
grep -Fq 'terminal, pane, process, runner or daemon instance is a runtime resource' "$contract"
grep -Fq 'At most three model Actions are globally active' "$contract"
grep -Fq '`workflowActive` and' "$contract"
grep -Fq 'No AI retry exists' "$contract"

for command_kind in \
	'worker.execute/v1' \
	'checks.observe/v1' \
	'review.execute/v1' \
	'repair.execute/v1' \
	'arbiter.execute/v1' \
	'human_gate.open/v1' \
	'admission.enqueue/v1' \
	'readmission.materialize/v1' \
	'release.dispatch/v1' \
	'merge.observe/v1' \
	'deployment.observe/v1' \
	'terminal.verify/v1'; do
	grep -Fq "$command_kind" "$contract"
done

grep -Fq 'task-level repair count `1`' "$contract"
grep -Fq 'finite target-pinned' "$contract"
grep -Fq 'Release Train is ordinary repository-owned GitHub Actions' "$contract"
grep -Fq 'target-spec-pinned Admission issuer/actor' "$contract"
grep -Fq 'PR content, a label, a workflow input' "$contract"
grep -Fq 'configured `baseline` check' "$contract"
grep -Fq 'immutable `readmission_required` proof.' "$contract"
grep -Fq 'maintain a second FIFO, priority queue or durable task state' "$contract"
grep -Fq 'auto-sync, rebase, update-branch, force-push' "$contract"
grep -Fq 'DCP/direct merge route' "$contract"
grep -Fq 'target deploy adapter' "$contract"
grep -Fq 'service-reported deployed SHA' "$contract"
grep -Fq 'Task id, Revision id and Admission id/sequence/digest' "$contract"
grep -Fq 'artifact id, media/type, source SHA and content digest' "$contract"
grep -Fq 'environment and service identifiers' "$contract"
grep -Fq 'merge until verified deployment proof' "$contract"
grep -Fq 'GitHub-hosted ephemeral OCI container' "$contract"
grep -Fq 'planned Stage 2 entry choice, not' "$contract"
grep -Fq 'qualification issuer' "$contract"
grep -Fq 'both issuers are never active together' "$contract"

for heading in \
	'## 5. Atomic transition and command-outbox law' \
	'## 6. Claim, lease, dedupe and crash recovery invariants' \
	'## 8. Reusable mechanical Release Train core' \
	'## 10. Non-simulated deployment proof' \
	'## 13. Qualification matrix' \
	'## 14. Nine execution stages and gates' \
	'## 15. WBC shadow, cutover and rollback fence'; do
	grep -Fq "$heading" "$contract"
done

for matrix_case in \
	'Four Tasks / three slots' \
	'FIFO Admission' \
	'Duplicate GitHub delivery' \
	'Out-of-order GitHub delivery' \
	'Restart at every fence' \
	'Main advance before review' \
	'Main advance after Admission' \
	'Arbiter repair' \
	'Human Gate' \
	'Required CI failure' \
	'Deployment failure' \
	'UI truth'; do
	grep -Fq "| $matrix_case |" "$contract"
done

for stage in \
	'1. Architecture' \
	'2. Twin + Release Train + real deploy' \
	'3. Independent no-DCP qualification' \
	'4. DCP v2 core' \
	'5. Adapter, install and preflight' \
	'6. Single DCP canary to deploy' \
	'7. Full adversarial qualification' \
	'8. WBC read-only shadow' \
	'9. Separately authorized WBC cutover'; do
	grep -Fq "| $stage |" "$contract"
done

grep -Fq 'Stages 1-5 are conservative contour work and MUST create no DCP' "$contract"
grep -Fq 'The first such submit is Stage 6' "$contract"
grep -Fq 'merge/deploy actor is disabled' "$contract"
grep -Fq 'There is never a simultaneous merge window' "$contract"
grep -Fq 'owner acceptance' "$contract"

for authority in "$current" docs/ROADMAP.md docs/TARGET_ARCHITECTURE_V1.md \
	docs/DCP_WBC_INTEGRATION_TWIN_CURRENT_PROGRAM_MANIFEST.md; do
	grep -Fq 'DCP_WBC_INTEGRATION_TWIN_DCP_V2_ARCHITECTURE_CONTRACT.md' "$authority"
done

grep -Fq 'operating_contract_revision: 2026-08-21.5' "$current"
grep -Fq 'task_first_startup_admission_continuation_missing' docs/DECISIONS.md
grep -Fq 'This Stage 1 is' "$contract"
grep -Fq 'one submit' docs/DCP_WBC_INTEGRATION_TWIN_CURRENT_PROGRAM_MANIFEST.md
grep -Fq 'old actor off before new actor on' docs/DCP_WBC_INTEGRATION_TWIN_CURRENT_PROGRAM_MANIFEST.md
grep -Fq 'superseded by the' docs/TARGET_ARCHITECTURE_V1.md

! grep -Eq '(/Users/|/home/|\.codex/worktrees/)' "$contract"
bash -n scripts/i30_wbc_integration_twin_dcp_v2_contract_audit.sh
git diff --check
printf 'PASS I30 WBC integration twin and DCP v2 architecture contract audit\n'
