#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
source "$REPO_ROOT/lib/dcp-ao-common.sh"
source "$REPO_ROOT/lib/dcp-ao-gateway.sh"
source "$REPO_ROOT/lib/dcp-ao-install.sh"
source "$REPO_ROOT/lib/dcp-ao-adapter.sh"

fake_schema=85
fake_action_status=running
fake_direct_rows='0|0|0'
fake_model_counts="$DCP_AO_TWIN_STAGE6_NATIVE_ACTION_SEQUENCE|0|$DCP_AO_TWIN_STAGE6_NATIVE_PREDECESSOR_ACTIONS"
fake_native_state=ci_waiting
fake_counts='1|1|1|1|0|0|0|0'
dcp_ao_verify_twin_stopped_activation() { :; }
dcp_ao_verify_twin_stage6_direct_worker_checkout() { :; }
dcp_ao_install_assert_no_active_model_actions() { :; }
dcp_ao_repo_only_policy_scalar() {
	local query="$2"
	case "$query" in
		'SELECT max(version_id)'*) printf '%s\n' "$fake_schema" ;;
		'PRAGMA foreign_key_check;'*) : ;;
		*'terminal_result_id'*'FROM dcp_v2_task;'*)
			printf '%s\n' "$DCP_AO_TWIN_STAGE6_TASK_ID|$DCP_AO_TWIN_STAGE6_REVISION_ID|worker_queued|1||||$DCP_AO_TWIN_STAGE6_SUBMITTED_AT|$DCP_AO_TWIN_STAGE6_SUBMITTED_AT" ;;
		*'FROM dcp_v2_revision;'*)
			printf '%s\n' "$DCP_AO_TWIN_STAGE6_REVISION_ID|$DCP_AO_TWIN_STAGE6_TASK_ID|1|work_input|main|$DCP_AO_TWIN_STAGE5_BASE_SHA|main|$DCP_AO_TWIN_STAGE5_BASE_SHA|||0|$DCP_AO_TWIN_STAGE6_REVISION_EVIDENCE_DIGEST|$DCP_AO_TWIN_STAGE6_SUBMITTED_AT" ;;
		*'FROM dcp_v2_command;'*)
			printf '%s\n' "$DCP_AO_TWIN_STAGE6_COMMAND_ID|$DCP_AO_TWIN_STAGE6_TASK_ID|$DCP_AO_TWIN_STAGE6_REVISION_ID|worker.execute/v1|leased|dcp-v2-daemon|model:$DCP_AO_TWIN_STAGE6_ACTION_ID|0|||$DCP_AO_TWIN_STAGE6_SUBMITTED_AT|$DCP_AO_TWIN_STAGE6_COMMAND_UPDATED_AT" ;;
		*'FROM dcp_v2_action;'*)
			printf '%s\n' "$DCP_AO_TWIN_STAGE6_ACTION_ID|$DCP_AO_TWIN_STAGE6_COMMAND_ID|$DCP_AO_TWIN_STAGE6_TASK_ID|$DCP_AO_TWIN_STAGE6_REVISION_ID|worker|1|$fake_action_status|1|model:$DCP_AO_TWIN_STAGE6_ACTION_ID|$DCP_AO_TWIN_STAGE6_DIRECT_RUNTIME_ID|||$DCP_AO_TWIN_STAGE6_SUBMITTED_AT|$DCP_AO_TWIN_STAGE6_DIRECT_ACTION_UPDATED_AT" ;;
		*'FROM dcp_v2_result)'*) printf '%s\n' "$fake_counts" ;;
		*"name IN ('dcp_v2_model_runtime'"*) [[ "$fake_schema" == 85 ]] && printf '0\n' || printf '3\n' ;;
		*'FROM dcp_v2_model_runtime)'*) printf '%s\n' "$fake_direct_rows" ;;
		*'version_id=86'*) printf '1\n' ;;
		*'FROM dcp_review_lab_policy_task WHERE'*)
			printf '%s\n' "$DCP_AO_TWIN_STAGE6_TASK_ID|$DCP_AO_TWIN_STAGE6_NATIVE_PAYLOAD_DIGEST|$fake_native_state|4|0|dcp-wbc-integration-lab-1|1|$DCP_AO_TWIN_STAGE6_WORKER_BRANCH|||0|||||" ;;
		*'FROM sessions WHERE'*)
			printf '%s\n' "dcp-wbc-integration-lab-1|idle|0|dcp-wbc-integration-lab-1||$DCP_AO_TWIN_STAGE6_WORKER_BRANCH|$1/data/worktrees/dcp-wbc-integration-lab/dcp-wbc-integration-lab-1" ;;
		*'FROM dcp_model_action WHERE sequence='*)
			printf '%s\n' "$DCP_AO_TWIN_STAGE6_NATIVE_ACTION_SEQUENCE|$DCP_AO_TWIN_STAGE6_NATIVE_ACTION_ID|$DCP_AO_TWIN_STAGE6_TASK_ID|dcp-wbc-integration-lab-1|initial_worker||succeeded|0|$DCP_AO_TWIN_STAGE6_DIRECT_RUNTIME_ID|||" ;;
		*'sum(CASE WHEN sequence <='*) printf '%s\n' "$fake_model_counts" ;;
		*) printf 'unexpected direct fence query: %s\n' "$query" >&2; return 1 ;;
	esac
}

dcp_ao_verify_twin_stage6_direct_fence /synthetic/dcp 85 0
fake_schema=86
dcp_ao_verify_twin_stage6_direct_fence /synthetic/dcp 86 1

assert_rejected() {
	local label="$1" expected="$2"
	if dcp_ao_verify_twin_stage6_direct_fence /synthetic/dcp "$expected" 1 >/dev/null 2>&1; then
		printf 'accepted invalid Stage 6 direct fence: %s\n' "$label" >&2
		exit 1
	fi
}

fake_action_status=launching
assert_rejected stale-action-identity 86
fake_action_status=running
fake_direct_rows='1|0|0'
assert_rejected premature-adoption-runtime 86
fake_direct_rows='0|0|0'
fake_model_counts="$DCP_AO_TWIN_STAGE6_NATIVE_ACTION_SEQUENCE|1|$DCP_AO_TWIN_STAGE6_NATIVE_PREDECESSOR_ACTIONS"
assert_rejected active-model 86
fake_model_counts="$DCP_AO_TWIN_STAGE6_NATIVE_ACTION_SEQUENCE|0|$DCP_AO_TWIN_STAGE6_NATIVE_PREDECESSOR_ACTIONS"
fake_native_state=reserved
assert_rejected native-state-drift 86
fake_native_state=ci_waiting
fake_counts='1|2|1|1|0|0|0|0'
assert_rejected duplicate-revision 86
fake_counts='1|1|1|1|1|0|0|0'
assert_rejected unexpected-downstream-effect 86

printf 'PASS Stage 6 direct-model frozen identity and no-adoption fence\n'
