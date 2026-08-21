#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
source "$REPO_ROOT/lib/dcp-ao-common.sh"
source "$REPO_ROOT/lib/dcp-ao-gateway.sh"
source "$REPO_ROOT/lib/dcp-ao-install.sh"
source "$REPO_ROOT/lib/dcp-ao-adapter.sh"

receipt=44e6cbebb529a20d9553451cb1a705668969c7c38912cd434d83aa24b4794024
valid="$(dcp_ao_twin_stage6_aggregate_response "$receipt")"

assert_rejected() {
	local label="$1" response="$2"
	if dcp_ao_validate_twin_stage6_aggregate_response "$receipt" "$response" >/dev/null 2>&1; then
		printf 'accepted invalid Stage 6 aggregate response: %s\n' "$label" >&2
		exit 1
	fi
}

dcp_ao_validate_twin_stage6_aggregate_response "$receipt" "$valid"
assert_rejected missing "$(printf '%s' "$valid" | /usr/bin/jq -c 'del(.commandId)')"
duplicate="${valid/\"taskId\":\"$DCP_AO_TWIN_STAGE6_TASK_ID\"/\"taskId\":\"$DCP_AO_TWIN_STAGE6_TASK_ID\",\"taskId\":\"$DCP_AO_TWIN_STAGE6_TASK_ID\"}"
assert_rejected duplicate "$duplicate"
assert_rejected wrong-type "$(printf '%s' "$valid" | /usr/bin/jq -c '.nativeCardNumber = "1"')"
assert_rejected wrong-value "$(printf '%s' "$valid" | /usr/bin/jq -c '.nativeActionId = "foreign"')"
assert_rejected uppercase-only "$(printf '%s' "$valid" | /usr/bin/jq -c '.TaskId = .taskId | del(.taskId)')"
assert_rejected foreign-extra "$(printf '%s' "$valid" | /usr/bin/jq -c '.foreignIdentity = "present"')"
assert_rejected predecessor-drift "$(printf '%s' "$valid" | /usr/bin/jq -c '.predecessorReceiptSha = "0000000000000000000000000000000000000000000000000000000000000000"')"
assert_rejected source-drift "$(printf '%s' "$valid" | /usr/bin/jq -c '.installedSourceTree = "0000000000000000000000000000000000000000"')"

printf 'PASS Stage 6 aggregate canonical lower-camel response parser\n'
