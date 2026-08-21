#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
source "$REPO_ROOT/lib/dcp-ao-common.sh"
source "$REPO_ROOT/lib/dcp-ao-gateway.sh"
source "$REPO_ROOT/lib/dcp-ao-install.sh"
source "$REPO_ROOT/lib/dcp-ao-adapter.sh"

fake_schema=85
fake_native_status=queued
fake_model_counts="$DCP_AO_TWIN_STAGE6_NATIVE_ACTION_SEQUENCE|0|$DCP_AO_TWIN_STAGE6_NATIVE_PREDECESSOR_ACTIONS"

dcp_ao_verify_twin_stopped_activation() { :; }
dcp_ao_install_assert_no_active_model_actions() { :; }
dcp_ao_sha256_stream() {
	local value
	value="$(cat)"
	case "$value" in
		'{"baseSha":"375b9b2d0b4c2fce6f2c417850553f79e24a0d92","prompt":"synthetic"}') printf '%s\n' "$DCP_AO_TWIN_STAGE6_PAYLOAD_DIGEST" ;;
		fake-epoch) printf '%s\n' "$DCP_AO_TWIN_STAGE6_LEASE_EPOCH_SHA256" ;;
		fake-token) printf '%s\n' "$DCP_AO_TWIN_STAGE6_LEASE_TOKEN_SHA256" ;;
		synthetic) printf '%s\n' "$DCP_AO_TWIN_STAGE6_NATIVE_PROMPT_SHA256" ;;
		*) printf '%s' "$value" | shasum -a 256 | awk '{print $1}' ;;
	esac
}
dcp_ao_repo_only_policy_scalar() {
	local query="$2" policy
	policy="$(dcp_ao_twin_policy_digest)"
	case "$query" in
		'SELECT max(version_id)'*) printf '%s\n' "$fake_schema" ;;
		*'FROM dcp_v2_task;'*)
			printf '%s\n' "$DCP_AO_TWIN_STAGE6_TASK_ID|dcp-wbc-integration-lab/v2|orenvlad-ai/dcp-wbc-integration-lab|$DCP_AO_TWIN_REPOSITORY_ID|$DCP_AO_TWIN_OWNER_ID|main|live-runtime|$policy|$DCP_AO_TWIN_STAGE6_REQUEST_DIGEST|$DCP_AO_TWIN_STAGE6_SCOPE_DIGEST|1|1|0|2|0|$DCP_AO_TWIN_STAGE6_REVISION_ID|worker_queued|1||||$DCP_AO_TWIN_STAGE6_SUBMITTED_AT|$DCP_AO_TWIN_STAGE6_SUBMITTED_AT" ;;
		*'FROM dcp_v2_revision;'*)
			printf '%s\n' "$DCP_AO_TWIN_STAGE6_REVISION_ID|$DCP_AO_TWIN_STAGE6_TASK_ID|1|work_input|orenvlad-ai/dcp-wbc-integration-lab|main|$DCP_AO_TWIN_STAGE5_BASE_SHA|main|$DCP_AO_TWIN_STAGE5_BASE_SHA|||0|$DCP_AO_TWIN_STAGE6_REVISION_EVIDENCE_DIGEST|$DCP_AO_TWIN_STAGE6_SUBMITTED_AT" ;;
		*'payload_digest'*'FROM dcp_v2_command;'*)
			printf '%s\n' "$DCP_AO_TWIN_STAGE6_COMMAND_ID|$DCP_AO_TWIN_STAGE6_TASK_ID|$DCP_AO_TWIN_STAGE6_REVISION_ID|worker.execute/v1|$DCP_AO_TWIN_STAGE6_PAYLOAD_DIGEST|$DCP_AO_TWIN_STAGE6_REQUEST_DIGEST|$DCP_AO_TWIN_STAGE6_TASK_ID/worker.execute/v1/1|leased|dcp-v2-daemon|1|1|model:$DCP_AO_TWIN_STAGE6_ACTION_ID|0|||$DCP_AO_TWIN_STAGE6_SUBMITTED_AT|$DCP_AO_TWIN_STAGE6_COMMAND_UPDATED_AT" ;;
		'SELECT payload_json FROM dcp_v2_command;'*)
			printf '{"baseSha":"%s","prompt":"synthetic"}\n' "$DCP_AO_TWIN_STAGE5_BASE_SHA" ;;
		'SELECT lease_epoch FROM dcp_v2_command;'*) printf 'fake-epoch\n' ;;
		'SELECT lease_token FROM dcp_v2_command;'*) printf 'fake-token\n' ;;
		*'FROM dcp_v2_action;'*)
			printf '%s\n' "$DCP_AO_TWIN_STAGE6_ACTION_ID|$DCP_AO_TWIN_STAGE6_COMMAND_ID|$DCP_AO_TWIN_STAGE6_TASK_ID|$DCP_AO_TWIN_STAGE6_REVISION_ID|worker|codex/default|high|20000|1800|$DCP_AO_TWIN_STAGE6_REQUEST_DIGEST|1|launching|1|model:$DCP_AO_TWIN_STAGE6_ACTION_ID||||$DCP_AO_TWIN_STAGE6_SUBMITTED_AT|$DCP_AO_TWIN_STAGE6_ACTION_UPDATED_AT" ;;
		*'FROM dcp_v2_result)'*) printf '1|1|1|1|0|0|0|0\n' ;;
		*"json_object('taskId',task_id"*)
			/usr/bin/jq -cn --arg task "$DCP_AO_TWIN_STAGE6_TASK_ID" --arg payload "$DCP_AO_TWIN_STAGE6_NATIVE_PAYLOAD_DIGEST" --arg worktree "$1/data/worktrees/dcp-wbc-integration-lab/dcp-wbc-integration-lab-1" '{taskId:$task,payloadDigest:$payload,target:"dcp-wbc-integration-lab",profile:"live-runtime",repository:"orenvlad-ai/dcp-wbc-integration-lab",policyVersion:"dcp.wbc-integration-twin/v2",sessionId:"dcp-wbc-integration-lab-1",cardNumber:1,worktreePath:$worktree,sourceBranch:"ao/dcp-wbc-integration-lab-1/root",state:"reserved",revision:1,repairCount:0,prUrl:"",prNumber:0,currentHeadSha:"",previousHeadSha:"",reviewRunId:"",admissionId:"",releasePhase:"",mergeCommitSha:"",errorCode:"",incidentPacket:""}' ;;
		*'SELECT prompt FROM dcp_review_lab_policy_task'*) printf 'synthetic\n' ;;
		*"json_object('id',id,'projectId'"*)
			/usr/bin/jq -cn '{id:"dcp-wbc-integration-lab-1",projectId:"dcp-wbc-integration-lab",num:1,kind:"worker",harness:"codex",activityState:"idle",terminated:0,branch:"",workspacePath:"",runtimeHandleId:"",agentSessionId:"",prompt:"",runtimeLaunchId:""}' ;;
		*"json_object('sequence',sequence"*)
			/usr/bin/jq -cn --argjson sequence "$DCP_AO_TWIN_STAGE6_NATIVE_ACTION_SEQUENCE" --arg id "$DCP_AO_TWIN_STAGE6_NATIVE_ACTION_ID" --arg task "$DCP_AO_TWIN_STAGE6_TASK_ID" --arg status "$fake_native_status" '{sequence:$sequence,id:$id,taskId:$task,sessionId:"dcp-wbc-integration-lab-1",kind:"initial_worker",exactHeadSha:"",status:$status,slot:0,launchId:"",reviewRunId:"",incidentId:"",errorCode:""}' ;;
		*'sum(CASE WHEN sequence <='*) printf '%s\n' "$fake_model_counts" ;;
		*) printf 'unexpected aggregate fence query: %s\n' "$query" >&2; return 1 ;;
	esac
}

dcp_ao_verify_twin_stage6_aggregate_fence /synthetic/dcp 0

assert_rejected() {
	local label="$1"
	if dcp_ao_verify_twin_stage6_aggregate_fence /synthetic/dcp 0 >/dev/null 2>&1; then
		printf 'accepted invalid Stage 6 aggregate fence: %s\n' "$label" >&2
		exit 1
	fi
}

fake_schema=84
assert_rejected schema-drift
fake_schema=85
fake_native_status=running
assert_rejected false-runtime
fake_native_status=queued
fake_model_counts="$DCP_AO_TWIN_STAGE6_NATIVE_ACTION_SEQUENCE|1|$DCP_AO_TWIN_STAGE6_NATIVE_PREDECESSOR_ACTIONS"
assert_rejected active-model

printf 'PASS Stage 6 aggregate identity and runtime fence\n'
