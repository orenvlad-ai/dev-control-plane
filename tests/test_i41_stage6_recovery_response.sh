#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
source "$REPO_ROOT/lib/dcp-ao-common.sh"
source "$REPO_ROOT/lib/dcp-ao-gateway.sh"
source "$REPO_ROOT/lib/dcp-ao-install.sh"
source "$REPO_ROOT/lib/dcp-ao-adapter.sh"

receipt=44e6cbebb529a20d9553451cb1a705668969c7c38912cd434d83aa24b4794024
valid="$(/usr/bin/jq -cn \
	--arg source "$DCP_AO_FORK_COMMIT" --arg tree "$DCP_AO_FORK_TREE" \
	--arg receipt "$receipt" \
	--arg stage5_source "$DCP_AO_TWIN_STAGE5_SOURCE_COMMIT" \
	--arg stage5_tree "$DCP_AO_TWIN_STAGE5_SOURCE_TREE" \
	--arg stage5_receipt "$DCP_AO_TWIN_STAGE5_RECEIPT_SHA256" \
	--arg task "$DCP_AO_TWIN_STAGE6_TASK_ID" \
	--arg revision "$DCP_AO_TWIN_STAGE6_REVISION_ID" \
	--arg command "$DCP_AO_TWIN_STAGE6_COMMAND_ID" \
	--arg action "$DCP_AO_TWIN_STAGE6_ACTION_ID" \
	--arg base "$DCP_AO_TWIN_STAGE5_BASE_SHA" '
{
  schemaVersion: "dcp.v2.stage6-native-shell-recovery/v1",
  installedSourceCommit: $source,
  installedSourceTree: $tree,
  installReceiptSha: $receipt,
  stage5ActivationId: "dcp-v2-twin-stage5",
  stage5SourceCommit: $stage5_source,
  stage5SourceTree: $stage5_tree,
  stage5ReceiptSha: $stage5_receipt,
  taskId: $task,
  revisionId: $revision,
  commandId: $command,
  actionId: $action,
  baseSha: $base,
  ready: true
}')"

assert_rejected() {
	local label="$1" response="$2"
	if dcp_ao_validate_twin_stage6_recovery_response "$receipt" "$response" >/dev/null 2>&1; then
		printf 'accepted invalid Stage 6 recovery response: %s\n' "$label" >&2
		exit 1
	fi
}

dcp_ao_validate_twin_stage6_recovery_response "$receipt" "$valid"
assert_rejected missing "$(printf '%s' "$valid" | /usr/bin/jq -c 'del(.commandId)')"
duplicate="${valid/\"taskId\":\"$DCP_AO_TWIN_STAGE6_TASK_ID\"/\"taskId\":\"$DCP_AO_TWIN_STAGE6_TASK_ID\",\"taskId\":\"$DCP_AO_TWIN_STAGE6_TASK_ID\"}"
assert_rejected duplicate "$duplicate"
assert_rejected wrong-type "$(printf '%s' "$valid" | /usr/bin/jq -c '.ready = "true"')"
assert_rejected wrong-value "$(printf '%s' "$valid" | /usr/bin/jq -c '.actionId = "v2-foreign"')"
assert_rejected uppercase-only "$(printf '%s' "$valid" | /usr/bin/jq -c '.TaskId = .taskId | del(.taskId)')"
assert_rejected foreign-extra "$(printf '%s' "$valid" | /usr/bin/jq -c '.foreignIdentity = "present"')"
assert_rejected stage5-drift "$(printf '%s' "$valid" | /usr/bin/jq -c '.stage5ReceiptSha = "0000000000000000000000000000000000000000000000000000000000000000"')"

printf 'PASS Stage 6 canonical lower-camel recovery response parser\n'
