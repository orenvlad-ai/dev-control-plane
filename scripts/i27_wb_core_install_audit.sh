#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
cd "$REPO_ROOT"
# shellcheck source=../upstream/dcp-orchestrator.lock
source upstream/dcp-orchestrator.lock

contract=docs/DCP_WB_CORE_RELEASE_TRAIN_HANDOFF_V1_CONTRACT.md
evidence=docs/DCP_WB_CORE_RELEASE_TRAIN_HANDOFF_V1_TERMINAL_EVIDENCE.md
current=docs/CURRENT_OPERATING_CONTRACT.md
adapter=lib/dcp-ao-adapter.sh

for path in \
	"$contract" "$evidence" "$current" upstream/dcp-orchestrator.lock \
	bin/dcp-ao bin/dcp-ao-submit lib/dcp-ao-common.sh "$adapter" \
	tests/test_i27_wb_core_adapter.sh; do
	[[ -s "$path" ]]
done

[[ "$DCP_AO_FORK_PR_URL" == https://github.com/orenvlad-ai/dcp-orchestrator/pull/77 ]]
[[ "$DCP_AO_FORK_COMMIT" == e9eb18a99db71813ac8c4556a614d6a3ce4108aa ]]
[[ "$DCP_AO_FORK_TREE" == b4db2b329accc9a93691bda7c306cc864b07ee56 ]]
[[ "$DCP_AO_PRIOR_FORK_COMMIT" == d084ae3cf0cb3e5e32ebefa197031c24a2b6392d ]]
[[ "$DCP_AO_PRIOR_FORK_TREE" == a6e3c3347bbbddd256e9edbfc541f115813249d2 ]]
[[ "$DCP_AO_WBC_CI_TRUTH_CONTRACT_COMMIT" == 1ca282408bec53a1d696cb58d247e33285209ee9 ]]
[[ "$DCP_AO_WBC_END_TO_END_CONTRACT_COMMIT" == 4f7775f375a612a38e96496f09908ab48e3598c5 ]]
[[ "$DCP_AO_WB_CORE_POLICY_AGENT_RULES_BYTES" == 1241 ]]
[[ "$DCP_AO_WB_CORE_POLICY_AGENT_RULES_SHA256" == e9a32d0fb71401360a763ec911a34dabf6215e85203a8a8a45c1b974044f3c74 ]]

grep -Fq 'orenvlad-ai/wb-core|false|main|1201929580|237411244' "$adapter"
grep -Fq 'dcp.wb-core.repo-only.release-train/v1' "$adapter"
grep -Fq 'dcp.wb-core.live-runtime.release-train/v1' "$adapter"
grep -Fq 'wb-core.dcp-release-handoff/v2' "$adapter"
grep -Fq 'dcp_ao_require_wb_core_compatibility "$target"' "$adapter"
grep -Fq 'dcp_ao_prepare_wb_core_project' "$adapter"
grep -Fq 'dcp_ao_wb_core_rules_match_source_lock' "$adapter"
grep -Fq 'dcp_ao_wb_core_project_identity_status' "$adapter"
grep -Fq 'dcp_ao_verify_wbc_ci_lifecycle_source "$source_dir"' lib/dcp-ao-common.sh
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
grep -Fq '"$cli" dcp submit --target wb-core --profile "$profile"' "$adapter"
grep -Fq -- '--repository orenvlad-ai/wb-core' "$adapter"
grep -Fq 'release_waiting' "$adapter"
grep -Fq 'Only WBC GitHub Actions may merge, add release:done for repo-only, or deploy and add release:production for live-runtime.' "$adapter"
grep -Fq 'python3 -c' "$adapter"
! grep -Fq 'python3 -m py_compile "$target/apps/github_release_train.py"' "$adapter"

grep -Fq 'dcp_ao_validate_wb_core_target "$lab_root" 0' lib/dcp-ao-common.sh
grep -Fq 'dcp_ao_verify_wb_core_policy_source "$source_dir"' lib/dcp-ao-common.sh
grep -Fq 'wb_core_compatibility=%s' lib/dcp-ao-common.sh
grep -Fq 'init-wb-core' bin/dcp-ao
grep -Fq 'register-wb-core' bin/dcp-ao
grep -Fq 'Stage 6 BLOCKED before adoption' "$current"
grep -Fq '11401ff6eadb80fd87e48229fb8c5458095a63b1' "$current"
grep -Fq 'DCP_WB_CORE_RELEASE_TRAIN_HANDOFF_V1_CONTRACT.md' "$current"
grep -Fq 'i12-20260817T111735Z' "$evidence"
grep -Fq 'schema is 78' "$evidence"
grep -Fq 'zero `wb-core` task/session/action rows' "$evidence"
grep -Fq 'current_unblock_status: COMPLETE' "$evidence"
grep -Fxq 'current_project_identity_status: COMPLETE' "$evidence"
grep -Fq 'current_technical_status: COMPLETE' "$evidence"
grep -Fq 'wbc-canary-v1' "$evidence"
grep -Fq 'a95e9a731d483d78d9d4e66c0663c9fb148e244ae5a93c4b0f1a22ea933593ec' "$evidence"
grep -Fq '2e4b0d69593c004a4becb532ed07d59e9be087af884cdfea523fb3e918a84a64' "$evidence"

bash -n scripts/i27_wb_core_install_audit.sh tests/test_i27_wb_core_adapter.sh \
	bin/dcp-ao bin/dcp-ao-submit lib/dcp-ao-common.sh "$adapter"
tests/test_i27_wb_core_adapter.sh
git diff --check
printf 'PASS I27 wb-core immutable pin/install audit\n'
