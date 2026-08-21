#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
source "$REPO_ROOT/lib/dcp-ao-common.sh"
source "$REPO_ROOT/lib/dcp-ao-gateway.sh"
source "$REPO_ROOT/lib/dcp-ao-install.sh"
source "$REPO_ROOT/lib/dcp-ao-adapter.sh"

fixture_main_sha="$DCP_AO_TWIN_STAGE5_BASE_SHA"
fixture_open_prs='[]'
fixture_native_refs='[]'
fixture_runs='{"workflow_runs":[]}'
fixture_wbc_head="$DCP_AO_TWIN_STAGE6_WBC_PR_HEAD"

dcp_ao_stage6_gh_api() {
	case "$1" in
		repos/orenvlad-ai/dcp-wbc-integration-lab/git/ref/heads/main)
			printf '{"object":{"sha":"%s"}}\n' "$fixture_main_sha" ;;
		'repos/orenvlad-ai/dcp-wbc-integration-lab/pulls?state=open&per_page=100') printf '%s\n' "$fixture_open_prs" ;;
		'repos/orenvlad-ai/dcp-wbc-integration-lab/git/matching-refs/heads/ao/dcp-wbc-integration-lab-1/root') printf '%s\n' "$fixture_native_refs" ;;
		'repos/orenvlad-ai/dcp-wbc-integration-lab/actions/runs?per_page=100') printf '%s\n' "$fixture_runs" ;;
		repos/orenvlad-ai/wb-core/pulls/987)
			printf '{"number":987,"state":"open","draft":false,"merged":false,"base":{"ref":"main"},"head":{"sha":"%s","repo":{"full_name":"orenvlad-ai/wb-core"}}}\n' "$fixture_wbc_head" ;;
		*) return 1 ;;
	esac
}

dcp_ao_require_tool() { :; }
dcp_ao_verify_twin_stage6_external_fence

assert_rejected() {
	local label="$1"
	if dcp_ao_verify_twin_stage6_external_fence >/dev/null 2>&1; then
		printf 'accepted invalid Stage 6 external fence: %s\n' "$label" >&2
		exit 1
	fi
}

fixture_main_sha=0000000000000000000000000000000000000000
assert_rejected main-drift
fixture_main_sha="$DCP_AO_TWIN_STAGE5_BASE_SHA"
fixture_open_prs='[{"number":1}]'
assert_rejected duplicate-pr
fixture_open_prs='[]'
fixture_native_refs='[{"ref":"refs/heads/ao/dcp-wbc-integration-lab-1/root"}]'
assert_rejected native-branch
fixture_native_refs='[]'
fixture_runs='{"workflow_runs":[{"created_at":"2026-08-21T00:00:00Z","event":"repository_dispatch","head_branch":"main"}]}'
assert_rejected provider-effect
fixture_runs='{"workflow_runs":[]}'
fixture_wbc_head=0000000000000000000000000000000000000000
assert_rejected wbc-drift

printf 'PASS Stage 6 aggregate external zero-effect fence\n'
