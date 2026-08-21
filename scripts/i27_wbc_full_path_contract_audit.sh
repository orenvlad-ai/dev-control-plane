#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
cd "$REPO_ROOT"

contract=docs/DCP_WB_CORE_END_TO_END_RELEASE_DEPLOY_V1_CONTRACT.md
current=docs/CURRENT_OPERATING_CONTRACT.md

for path in "$contract" "$current" AGENTS.md docs/DECISIONS.md docs/PROJECT_BRIEF.md docs/ROADMAP.md docs/UPSTREAM_QUALIFICATION.md; do
	[[ -s "$path" ]]
done

grep -Fq 'contract_status: reviewed WBC/source and waiting-recovery pin authority; waiting correction not installed' "$contract"
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
grep -Fq '`release_state_drift` incident with the exact incident admission' "$contract"
grep -Fq 'general incident/arbiter' "$contract"
grep -Fq '`3fdc3976edc6bad591bca4cf4e254b479a905fb3`' "$contract"
grep -Fq 'skipped the archived exact session before' "$contract"
grep -Fq 'general terminated sessions remain excluded' "$contract"
grep -Fq 'legacy v1 marker evidence' "$contract"
grep -Fq 'approved predecessor head' "$contract"
grep -Fq '`admission_identity_drift`' "$contract"
grep -Fq 'reviewed WBC generation' "$contract"
grep -Fq 'next immutable readmission generation' "$contract"
grep -Fq '`waiting_identity_drift`' "$contract"
grep -Fq 'same non-empty admission ID' "$contract"

# The pre-runtime authority may be installed only through the exact reviewed
# source and immutable adapter/source/native-project lock.
source upstream/dcp-orchestrator.lock
[[ "$DCP_AO_FORK_PR_URL" == https://github.com/orenvlad-ai/dcp-orchestrator/pull/76 ]]
[[ "$DCP_AO_FORK_COMMIT" == d084ae3cf0cb3e5e32ebefa197031c24a2b6392d ]]
[[ "$DCP_AO_FORK_TREE" == a6e3c3347bbbddd256e9edbfc541f115813249d2 ]]
[[ "$DCP_AO_WBC_END_TO_END_CONTRACT_COMMIT" == 4f7775f375a612a38e96496f09908ab48e3598c5 ]]
[[ "$DCP_AO_WB_CORE_POLICY_AGENT_RULES_BYTES" == 1241 ]]
[[ "$DCP_AO_WB_CORE_POLICY_AGENT_RULES_SHA256" == e9a32d0fb71401360a763ec911a34dabf6215e85203a8a8a45c1b974044f3c74 ]]
grep -Fq 'dcp_ao_verify_wbc_end_to_end_source "$source_dir"' lib/dcp-ao-common.sh
grep -Fq 'dcp_ao_verify_task_first_lifecycle_source "$source_dir"' lib/dcp-ao-common.sh
grep -Fq 'type preservedWBCReadmissionStore interface' lib/dcp-ao-common.sh
grep -Fq 'GetOpenDCPWBCReadmissionGenerationByTask' lib/dcp-ao-common.sh
grep -Fq 'AcceptsWBCReadmissionMarker' lib/dcp-ao-common.sh
grep -Fq 'mode == triggerPreserved && !futurePolicyReview' lib/dcp-ao-common.sh
grep -Fq 'reviewedWBCReadmissionAdmissionBinding' lib/dcp-ao-common.sh
grep -Fq '0081_dcp_wbc_readmission_admission_recovery_v1.sql' lib/dcp-ao-common.sh
grep -Fq 'boundAdmission := generation.Status == domain.DCPWBCReadmissionAdmitted' lib/dcp-ao-common.sh
grep -Fq '0082_dcp_wbc_readmission_waiting_recovery_v1.sql' lib/dcp-ao-common.sh
grep -Fq 'wb-core.dcp-release-handoff/v2' lib/dcp-ao-adapter.sh
grep -Fq 'wb-core requires --profile repo-only or live-runtime' lib/dcp-ao-adapter.sh

grep -Fq 'DCP_WB_CORE_END_TO_END_RELEASE_DEPLOY_V1_CONTRACT.md' "$current"

blocked_evidence='docs/DCP_WB_CORE_REPO_ONLY_READMISSION_NATIVE_LIFECYCLE_BLOCKED_EVIDENCE.md'
[[ -f "$blocked_evidence" ]]
grep -Fq 'Status: `BLOCKED`' "$blocked_evidence"
grep -Fq 'DCP policy task wbc-canary-v1 native identity drifted' "$blocked_evidence"
grep -Fq '73 model actions' "$blocked_evidence"
grep -Fq 'zero active model actions' "$blocked_evidence"
grep -Fq 'operating_contract_revision: 2026-08-21.4' "$current"
grep -Fq '`repo-only` requires exact admitted-head merge' "$current"
grep -Fq '`live-runtime` additionally requires exact deployed SHA' "$current"
! grep -Eq '(/Users/|/home/|\.codex/worktrees/)' "$contract"

bash -n scripts/i27_wbc_full_path_contract_audit.sh
git diff --check
printf 'PASS I27 WBC full release/deploy path contract audit\n'
