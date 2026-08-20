#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
source "$REPO_ROOT/lib/dcp-ao-common.sh"
source "$REPO_ROOT/lib/dcp-ao-gateway.sh"
source "$REPO_ROOT/lib/dcp-ao-adapter.sh"

lab_root=/tmp/dcp-stage5-response-test
receipt=11e6cbebb529a20d9553451cb1a705668969c7c38912cd434d83aa24b4794024
policy_digest="$(dcp_ao_twin_policy_digest)"

valid="$(/usr/bin/jq -cn \
	--arg authority "$DCP_AO_TWIN_STAGE5_CONTRACT_COMMIT" \
	--arg source "$DCP_AO_FORK_COMMIT" --arg tree "$DCP_AO_FORK_TREE" \
	--arg receipt "$receipt" --arg policy "$policy_digest" \
	--arg path "$lab_root/targets/dcp-wbc-integration-lab" \
	--argjson repository_id "$DCP_AO_TWIN_REPOSITORY_ID" \
	--argjson owner_id "$DCP_AO_TWIN_OWNER_ID" \
	--argjson workflow_id "$DCP_AO_TWIN_WORKFLOW_ID" '
{
  activation: {
    activationId: "dcp-v2-twin-stage5",
    authorityCommit: $authority,
    sourceCommit: $source,
    sourceTree: $tree,
    installReceiptSha: $receipt,
    targetSpecVersion: "dcp-wbc-integration-lab/v2",
    targetPolicyDigest: $policy,
    repository: "orenvlad-ai/dcp-wbc-integration-lab",
    repositoryId: $repository_id,
    ownerId: $owner_id,
    baseRef: "main",
    requiredCheck: "baseline",
    issuerKind: "dcp/v2",
    issuerActor: "orenvlad-ai",
    issuerEvent: "repository_dispatch",
    issuerEventType: "dcp-admission-v2",
    workflowId: $workflow_id,
    environment: "dcp-wbc-integration-lab-selectel",
    service: "dcp-wbc-integration-lab",
    adapter: "selectel-systemd/v1",
    activatedAt: "2026-08-20T15:51:19Z"
  },
  projectId: "dcp-wbc-integration-lab",
  projectPath: $path,
  created: true,
  projectCreated: true
}')"

assert_rejected() {
	local label="$1" response="$2"
	if dcp_ao_validate_twin_stage5_activation_response "$lab_root" "$receipt" "$response" >/dev/null 2>&1; then
		printf 'accepted invalid Stage 5 response: %s\n' "$label" >&2
		exit 1
	fi
}

dcp_ao_validate_twin_stage5_activation_response "$lab_root" "$receipt" "$valid"

assert_rejected missing "$(printf '%s' "$valid" | /usr/bin/jq -c 'del(.activation.sourceTree)')"

duplicate="${valid/\"sourceCommit\":\"$DCP_AO_FORK_COMMIT\"/\"sourceCommit\":\"$DCP_AO_FORK_COMMIT\",\"sourceCommit\":\"$DCP_AO_FORK_COMMIT\"}"
assert_rejected duplicate "$duplicate"

assert_rejected wrong-type "$(printf '%s' "$valid" | /usr/bin/jq -c '.activation.repositoryId = "1340359100"')"
assert_rejected wrong-value "$(printf '%s' "$valid" | /usr/bin/jq -c '.activation.sourceTree = "0000000000000000000000000000000000000000"')"
assert_rejected uppercase-only "$(printf '%s' "$valid" | /usr/bin/jq -c '.activation.SourceCommit = .activation.sourceCommit | del(.activation.sourceCommit)')"
assert_rejected foreign-extra "$(printf '%s' "$valid" | /usr/bin/jq -c '.activation.foreignRepository = "orenvlad-ai/foreign"')"
assert_rejected foreign-root "$(printf '%s' "$valid" | /usr/bin/jq -c '.foreignIdentity = "present"')"
assert_rejected invalid-time "$(printf '%s' "$valid" | /usr/bin/jq -c '.activation.activatedAt = "not-a-time"')"

printf 'PASS Stage 5 canonical lower-camel activation response parser\n'
