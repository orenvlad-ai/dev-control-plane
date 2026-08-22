#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
source "$REPO_ROOT/lib/dcp-ao-common.sh"
source "$REPO_ROOT/lib/dcp-ao-gateway.sh"
source "$REPO_ROOT/lib/dcp-ao-install.sh"
source "$REPO_ROOT/lib/dcp-ao-adapter.sh"
source "$REPO_ROOT/lib/dcp-ao-stage6-direct-install.sh"

dcp_ao_stage6_final_configure
[[ "$DCP_AO_TWIN_STAGE6_DIRECT_INSTALL_ID" == "$DCP_AO_TWIN_STAGE6_FINAL_INSTALL_ID" ]]
[[ "$DCP_AO_STAGE6_PREDECESSOR_SCHEMA" == 86 ]]
[[ "$DCP_AO_STAGE6_TARGET_SCHEMA" == 87 ]]
[[ "$DCP_AO_TWIN_STAGE6_AGGREGATE_RECEIPT_SHA256" == "$DCP_AO_TWIN_STAGE6_DIRECT_RECEIPT_SHA256" ]]

next_revision="v2-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
fake_direct_rows='1|1|1'
fake_active_rows='0|0'
fake_task_state=checks_waiting
fake_task_revision=2
fake_model_counts="$DCP_AO_TWIN_STAGE6_NATIVE_ACTION_SEQUENCE|0"
dcp_ao_verify_twin_stopped_activation() { :; }
dcp_ao_verify_twin_stage6_direct_worker_checkout() { :; }
dcp_ao_install_assert_no_active_model_actions() { :; }
dcp_ao_repo_only_policy_scalar() {
	local query="$2"
	case "$query" in
		'SELECT max(version_id)'*) printf '87\n' ;;
		'PRAGMA foreign_key_check;'*) : ;;
		*'version_id=87'*) printf '1\n' ;;
		*"SELECT task_id || '|' || state"*)
			printf '%s\n' "$DCP_AO_TWIN_STAGE6_TASK_ID|$fake_task_state|$fake_task_revision|$next_revision||" ;;
		*'FROM dcp_v2_revision WHERE sequence=2'*)
			printf '%s\n' "$DCP_AO_TWIN_STAGE6_TASK_ID|2|worker_output|$DCP_AO_TWIN_STAGE5_BASE_SHA|$DCP_AO_TWIN_STAGE6_WORKER_BRANCH|$DCP_AO_TWIN_STAGE6_WORKER_COMMIT|$DCP_AO_TWIN_STAGE6_WORKER_TREE|$DCP_AO_TWIN_STAGE6_REVISION_ID|$DCP_AO_TWIN_STAGE6_COMMAND_ID|0" ;;
		*'group_concat(sequence'*)
			printf '%s\n' "1|worker.execute/v1|succeeded|$DCP_AO_TWIN_STAGE6_REVISION_ID|model:$DCP_AO_TWIN_STAGE6_ACTION_ID;2|publication.execute/v1|pending|$next_revision|" ;;
		*"SELECT action_id || '|' || status"*)
			printf '%s\n' "$DCP_AO_TWIN_STAGE6_ACTION_ID|succeeded|0|$DCP_AO_TWIN_STAGE6_DIRECT_RUNTIME_ID|64|" ;;
		*'FROM dcp_v2_result)'*) printf '1|2|2|1|0|0|0|0\n' ;;
		*'FROM dcp_v2_model_terminal_receipt)'*) printf '%s\n' "$fake_direct_rows" ;;
		*"state IN ('reserved','running')"*) printf '%s\n' "$fake_active_rows" ;;
		*'FROM dcp_v2_stage6_worker_adoption_v1;'*)
			printf '%s\n' "dcp-v2-stage6-worker-adoption-v1|$DCP_AO_TWIN_STAGE6_TASK_ID|$DCP_AO_TWIN_STAGE6_REVISION_ID|$DCP_AO_TWIN_STAGE6_COMMAND_ID|$DCP_AO_TWIN_STAGE6_ACTION_ID|$DCP_AO_TWIN_STAGE6_DIRECT_RUNTIME_ID|$DCP_AO_TWIN_STAGE6_NATIVE_ACTION_ID|$DCP_AO_TWIN_STAGE6_NATIVE_ACTION_SEQUENCE|$DCP_AO_TWIN_STAGE6_WORKER_COMMIT|$DCP_AO_TWIN_STAGE6_WORKER_TREE|$DCP_AO_TWIN_STAGE6_WORKER_BRANCH" ;;
		*'FROM dcp_model_action;'*) printf '%s\n' "$fake_model_counts" ;;
		*) printf 'unexpected final adopted query: %s\n' "$query" >&2; return 1 ;;
	esac
}

dcp_ao_verify_twin_stage6_adopted_fence /synthetic/final 1

assert_adopted_rejected() {
	local label="$1"
	if dcp_ao_verify_twin_stage6_adopted_fence /synthetic/final 1 >/dev/null 2>&1; then
		printf 'accepted invalid final adopted fence: %s\n' "$label" >&2
		exit 1
	fi
}

fake_direct_rows='2|1|1'
assert_adopted_rejected duplicate-runtime
fake_direct_rows='1|1|1'
fake_active_rows='1|0'
assert_adopted_rejected active-runtime
fake_active_rows='0|0'
fake_task_state=worker_queued
assert_adopted_rejected stale-task
fake_task_state=checks_waiting
fake_task_revision=3
assert_adopted_rejected duplicate-transition
fake_task_revision=2
fake_model_counts="$DCP_AO_TWIN_STAGE6_NATIVE_ACTION_SEQUENCE|1"
assert_adopted_rejected native-model-active
fake_model_counts="$DCP_AO_TWIN_STAGE6_NATIVE_ACTION_SEQUENCE|0"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
valid="$tmp/valid.json"
/usr/bin/jq -cn \
	--arg source "$DCP_AO_FORK_COMMIT" --arg tree "$DCP_AO_FORK_TREE" \
	--arg receipt "$(printf r%.0s {1..64})" --arg task "$DCP_AO_TWIN_STAGE6_TASK_ID" \
	--arg revision "$DCP_AO_TWIN_STAGE6_REVISION_ID" --arg command "$DCP_AO_TWIN_STAGE6_COMMAND_ID" \
	--arg action "$DCP_AO_TWIN_STAGE6_ACTION_ID" --arg runtime "$DCP_AO_TWIN_STAGE6_DIRECT_RUNTIME_ID" \
	--arg native "$DCP_AO_TWIN_STAGE6_NATIVE_ACTION_ID" --arg commit "$DCP_AO_TWIN_STAGE6_WORKER_COMMIT" \
	--arg workerTree "$DCP_AO_TWIN_STAGE6_WORKER_TREE" --arg branch "$DCP_AO_TWIN_STAGE6_WORKER_BRANCH" \
	'{schemaVersion:"dcp.v2.stage6-direct-adoption/v1",installedSourceCommit:$source,installedSourceTree:$tree,installReceiptSha:$receipt,applied:true,
	adoption:{adoptionId:"dcp-v2-stage6-worker-adoption-v1",taskId:$task,revisionId:$revision,commandId:$command,actionId:$action,
	runtimeId:$runtime,nativeActionId:$native,nativeSequence:74,legacyEvidenceDigest:("a"*64),commitSha:$commit,treeSha:$workerTree,
	branch:$branch,worktreeDigest:("b"*64),outputDigest:("c"*64),receiptId:"receipt",consumedAt:"2026-08-22T00:00:00Z"}}' >"$valid"
receipt="$(/usr/bin/jq -r .installReceiptSha "$valid")"
dcp_ao_stage6_final_validate_adoption_response "$valid" "$receipt"
/usr/bin/jq '.applied=false' "$valid" >"$tmp/replay.json"
if dcp_ao_stage6_final_validate_adoption_response "$tmp/replay.json" "$receipt" >/dev/null 2>&1; then
	echo 'accepted equal adoption replay as the one live application' >&2
	exit 1
fi
/usr/bin/jq '.adoption.commitSha=("d"*40)' "$valid" >"$tmp/crossed.json"
if dcp_ao_stage6_final_validate_adoption_response "$tmp/crossed.json" "$receipt" >/dev/null 2>&1; then
	echo 'accepted crossed Worker output in adoption response' >&2
	exit 1
fi

publication_probe_file="$tmp/publication-probe"
dcp_ao_verify_twin_stage6_published_fence() {
	if [[ ! -f "$publication_probe_file" ]]; then
		: >"$publication_probe_file"
		return 1
	fi
	printf '17\n'
}
dcp_ao_verify_twin_stage6_publication_effect() { [[ "$1" == 17 ]]; }
sleep() { :; }
[[ "$(dcp_ao_stage6_final_wait_published /synthetic/final)" == 17 ]]
dcp_ao_verify_twin_stage6_published_fence() { return 1; }
if dcp_ao_stage6_final_wait_published /synthetic/final >/dev/null 2>&1; then
	echo 'accepted publication observation timeout as success' >&2
	exit 1
fi

terminal_revision="v2-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
terminal_result="v2-cccccccccccccccccccccccccccccccccccccccc"
terminal_admission="v2-dddddddddddddddddddddddddddddddddddddddd"
terminal_command="v2-eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
terminal_merge="$(printf f%.0s {1..40})"
terminal_result_bindings='2|1|1|1|1|1|1|2'
dcp_ao_verify_installed_bundle() { :; }
dcp_ao_gateway_status_json() { printf '{\n  "state": "ready"\n}\n'; }
dcp_ao_gateway_assert_pair() { :; }
dcp_ao_verify_twin_stopped_activation() { :; }
dcp_ao_stage6_gh_api() {
	case "$1" in
		*/git/ref/heads/main) printf '{"object":{"sha":"%s"}}\n' "$terminal_merge" ;;
		*/pulls/17) printf '{"number":17,"state":"closed","merged":true,"merge_commit_sha":"%s","base":{"ref":"main"}}\n' "$terminal_merge" ;;
		*wb-core/pulls/987) printf '{"number":987,"state":"open","merged":false,"base":{"ref":"main"},"head":{"sha":"%s"}}\n' "$DCP_AO_TWIN_STAGE6_WBC_PR_HEAD" ;;
		*) return 1 ;;
	esac
}
dcp_ao_repo_only_policy_scalar() {
	local query="$2"
	case "$query" in
		'SELECT max(version_id)'*) printf '87\n' ;;
		'PRAGMA integrity_check;'*) printf 'ok\n' ;;
		'PRAGMA foreign_key_check;'*) : ;;
		*"SELECT task_id || '|' || state"*) printf '%s\n' "$DCP_AO_TWIN_STAGE6_TASK_ID|deployed|$terminal_revision|$terminal_result|0|0|" ;;
		*"SELECT revision_id || '|' || kind"*) printf '%s\n' "$terminal_revision|provider_bound|17|$DCP_AO_TWIN_STAGE6_WORKER_COMMIT|$DCP_AO_TWIN_STAGE6_WORKER_TREE" ;;
		*"FROM dcp_v2_result WHERE kind='deployment'"*)
			printf '%s\n' "$terminal_result|$DCP_AO_TWIN_STAGE6_TASK_ID|$terminal_revision|$terminal_admission|$terminal_command|deployment|github|proof|91|github-actions|$(printf a%.0s {1..64})|$(printf b%.0s {1..64})|$terminal_merge|$terminal_merge|$(printf c%.0s {1..64})|$terminal_merge|dcp-wbc-integration-lab-selectel|dcp-wbc-integration-lab|$(printf d%.0s {1..64})|1|" ;;
		*'count(DISTINCT artifact_source_sha)'*) printf '%s\n' "$terminal_result_bindings" ;;
		*'FROM dcp_v2_result);'*) printf '1|3|10|2|1|0|2|2\n' ;;
		*"sum(kind='terminal.verify/v1'"*) printf '10|0|1\n' ;;
		*"sum(status IN ('queued','launching','running'))"*) printf '2|0|2|0\n' ;;
		*"sum(status='readmission_required')"*) printf '1|1|0|1\n' ;;
		*"FROM dcp_v2_model_runtime WHERE state IN ('reserved','running')"*) printf '2|0|2|1\n' ;;
		*) printf 'unexpected final terminal query: %s\n' "$query" >&2; return 1 ;;
	esac
}

dcp_ao_verify_twin_stage6_terminal_fence /synthetic/final >/dev/null
terminal_result_bindings='3|1|2|1|1|1|1|3'
if dcp_ao_verify_twin_stage6_terminal_fence /synthetic/final >/dev/null 2>&1; then
	echo 'accepted duplicate terminal deployment Result' >&2
	exit 1
fi

printf 'PASS Stage 6 final schema-87 adoption and one-use response fences\n'
