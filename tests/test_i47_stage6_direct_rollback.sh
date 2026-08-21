#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
source "$REPO_ROOT/lib/dcp-ao-common.sh"
source "$REPO_ROOT/lib/dcp-ao-stage6-direct-install.sh"

dcp_ao_stage6_direct_copy_tree() { cp -R "$1" "$2"; }

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
lab="$tmp/lab"; backup="$tmp/backup"; TEST_APP_PATH="$tmp/DCP Orchestrator.app"
mkdir -p "$lab/data" "$lab/state" "$backup/prior/data" "$backup/prior/state" \
	"$backup/prior/DCP Orchestrator.app" "$TEST_APP_PATH"
printf 'mutated-data\n' >"$lab/data/value"
printf 'mutated-state\n' >"$lab/state/value"
printf 'new-app\n' >"$TEST_APP_PATH/value"
printf 'prior-data\n' >"$backup/prior/data/value"
printf 'prior-state\n' >"$backup/prior/state/value"
printf 'prior-app\n' >"$backup/prior/DCP Orchestrator.app/value"
printf 'install_identity=%s\n' "$DCP_AO_TWIN_STAGE6_DIRECT_INSTALL_ID" >"$backup/manifest"

dcp_ao_app_path() { printf '%s\n' "$TEST_APP_PATH"; }
dcp_ao_stage6_direct_verify_predecessor_receipt() { [[ -f "$1/state/value" ]]; }
dcp_ao_verify_twin_stage6_direct_fence() { [[ "$2" == 85 && "$3" == 1 ]]; }

dcp_ao_stage6_direct_rollback "$lab" "$backup"
[[ "$(cat "$TEST_APP_PATH/value")" == prior-app ]]
[[ "$(cat "$lab/data/value")" == prior-data ]]
[[ "$(cat "$lab/state/value")" == prior-state ]]
[[ "$(cat "$backup/failed-direct-model.app/value")" == new-app ]]
[[ "$(cat "$backup/failed-data/value")" == mutated-data ]]
[[ "$(cat "$backup/failed-state/value")" == mutated-state ]]
grep -Fxq 'rollback=complete' "$backup/manifest"

printf 'PASS Stage 6 direct-model mandatory rollback restoration\n'
