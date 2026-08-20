#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
source "$REPO_ROOT/lib/dcp-ao-common.sh"
source "$REPO_ROOT/lib/dcp-ao-gateway.sh"
source "$REPO_ROOT/lib/dcp-ao-adapter.sh"

dcp_ao_twin_rules_match_source_lock
[[ "$(dcp_ao_twin_policy_digest)" == 1328a21cfd27cd50abcf6bcfac8775c1436e8bc0809a2c92fa8adedfc2326027 ]]
dcp_ao_validate_twin_task_id dcp-v2-twin-canary-v1
if dcp_ao_validate_twin_task_id foreign; then exit 1; fi

dcp_ao_require_tool() { :; }
gh() {
	case "$*" in
		'api repos/orenvlad-ai/dcp-wbc-integration-lab --jq '[* )
			printf 'orenvlad-ai/dcp-wbc-integration-lab|false|main|1340359100|237411244\n' ;;
		'api repos/orenvlad-ai/dcp-wbc-integration-lab/actions/workflows/338377713 --jq '[* )
			printf '338377713|Release Train|.github/workflows/release-train.yml|active\n' ;;
		*) return 1 ;;
	esac
}
dcp_ao_validate_twin_provider_identity

response='{"task":{"TaskID":"dcp-v2-twin-canary-v1","TargetSpecVersion":"dcp-wbc-integration-lab/v2","Repository":"orenvlad-ai/dcp-wbc-integration-lab","RepositoryID":1340359100,"OwnerID":237411244,"BaseRef":"main","Profile":"live-runtime","InitialWorkerBudget":1,"RepairBudget":1,"MaxReadmissions":2,"CurrentRevisionID":"revision-1","State":"worker_running","StateRevision":2},"native":{"taskId":"dcp-v2-twin-canary-v1","target":"dcp-wbc-integration-lab","profile":"live-runtime","repository":"orenvlad-ai/dcp-wbc-integration-lab","sessionId":"dcp-wbc-integration-lab-1","cardNumber":1,"worktreePath":"/tmp/lab/data/worktrees/dcp-wbc-integration-lab/dcp-wbc-integration-lab-1","sourceBranch":"ao/dcp-wbc-integration-lab-1/root"},"projection":{"phase":"worker_running","modelActive":true,"workflowActive":true},"duplicate":false}'
dcp_ao_validate_v2_twin_submit_response /tmp/lab dcp-v2-twin-canary-v1 "$response" >/dev/null
if dcp_ao_validate_v2_twin_submit_response /tmp/lab foreign "$response" >/dev/null 2>&1; then exit 1; fi

printf 'PASS Stage 5 twin adapter exact identity fixtures\n'
