#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
# shellcheck source=../lib/dcp-ao-common.sh
source "$REPO_ROOT/lib/dcp-ao-common.sh"
# shellcheck source=../lib/dcp-ao-gateway.sh
source "$REPO_ROOT/lib/dcp-ao-gateway.sh"

TEST_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/dcp-ao-i7-gateway.XXXXXX")"
cleanup() { rm -rf "$TEST_ROOT"; }
trap cleanup EXIT

export DCP_AO_GATEWAY_LOCK_ATTEMPTS=100
dcp_ao_preflight_exact_contour() { :; }
dcp_ao_export_runtime_env() { :; }
dcp_ao_gateway_port_occupied() { return 1; }
dcp_ao_gateway_exact_ui_present() { [[ -f "$1/test-ui-present" ]]; }
dcp_ao_gateway_assert_pair() { :; }
dcp_ao_gateway_status_json() {
	local root="$1" failures
	if [[ -f "$root/test-status-failures" ]]; then
		failures="$(sed -n '1p' "$root/test-status-failures")"
		if (( failures > 0 )); then
			printf '%s\n' "$((failures - 1))" >"$root/test-status-failures"
			return 127
		fi
	fi
	if grep -Fq '"state": "stale"' "$root/test-state.json" && [[ ! -e "$root/runtime/run/running.json" ]]; then
		printf '{\n  "state": "stopped"\n}\n'
	else
		cat "$root/test-state.json"
	fi
}
dcp_ao_gateway_launch_ui() {
	printf 'launch\n' >>"$1/test-lifecycle.log"
	printf 'present\n' >"$1/test-ui-present"
	if [[ -n "${DCP_I7_TEST_TRANSIENT_STATUS_FAILURES:-}" ]]; then
		printf '%s\n' "$DCP_I7_TEST_TRANSIENT_STATUS_FAILURES" >"$1/test-status-failures"
	fi
	if [[ -n "${DCP_I7_TEST_LAUNCH_DELAY:-}" ]]; then sleep "$DCP_I7_TEST_LAUNCH_DELAY"; fi
	printf '{\n  "state": "ready"\n}\n' >"$1/test-state.json"
}

scenario_root() {
	local name="$1" root
	root="$TEST_ROOT/$name"
	mkdir -p "$root"
	printf '%s\n' "$root"
}

dcp_ao_ui_owner_command_matches "/bin/bash $REPO_ROOT/bin/dcp-ao __gateway-launch"
if dcp_ao_ui_owner_command_matches 'npm run dev'; then
	printf 'mutable npm process was accepted as the UI singleton owner\n' >&2
	exit 1
fi

# Healthy includes an active worker and is reused without any lifecycle action.
root="$(scenario_root active-worker)"
printf '{\n  "state": "ready",\n  "activeWorkers": 1\n}\n' >"$root/test-state.json"
dcp_ao_gateway_ensure "$root" fake-cli
[[ ! -e "$root/test-lifecycle.log" ]]

# A fully stopped contour starts the canonical source UI exactly once.
root="$(scenario_root stopped)"
printf '{\n  "state": "stopped"\n}\n' >"$root/test-state.json"
dcp_ao_gateway_ensure "$root" fake-cli
[[ "$(grep -c '^launch$' "$root/test-lifecycle.log")" -eq 1 ]]

# Upstream predev may briefly replace the daemon binary while the exact UI
# singleton remains live; readiness waits through that bounded build gap.
root="$(scenario_root cold-build-gap)"
printf '{\n  "state": "stopped"\n}\n' >"$root/test-state.json"
export DCP_I7_TEST_TRANSIENT_STATUS_FAILURES=1
dcp_ao_gateway_ensure "$root" fake-cli
unset DCP_I7_TEST_TRANSIENT_STATUS_FAILURES
[[ "$(grep -c '^launch$' "$root/test-lifecycle.log")" -eq 1 ]]
[[ "$(sed -n '1p' "$root/test-status-failures")" -eq 0 ]]

# Concurrent entries share one startup under the lifecycle singleton.
root="$(scenario_root concurrent-start)"
printf '{\n  "state": "stopped"\n}\n' >"$root/test-state.json"
export DCP_I7_TEST_LAUNCH_DELAY=0.2
(dcp_ao_gateway_ensure "$root" fake-cli) & first=$!
(dcp_ao_gateway_ensure "$root" fake-cli) & second=$!
wait "$first" "$second"
unset DCP_I7_TEST_LAUNCH_DELAY
[[ "$(grep -c '^launch$' "$root/test-lifecycle.log")" -eq 1 ]]

# The singleton also covers the complete submit callback, not only startup.
serialized_callback() {
	local root="$3"
	if ! mkdir "$root/critical" 2>/dev/null; then
		printf 'overlap\n' >>"$root/callback.log"
		return 1
	fi
	sleep 0.1
	printf 'callback\n' >>"$root/callback.log"
	rmdir "$root/critical"
}
root="$(scenario_root concurrent-submit)"
(dcp_ao_gateway_with_lock "$root" fake-cli serialized_callback "$root") & first=$!
(dcp_ao_gateway_with_lock "$root" fake-cli serialized_callback "$root") & second=$!
wait "$first" "$second"
[[ "$(grep -c '^callback$' "$root/callback.log")" -eq 2 ]]
[[ "$(grep -c '^overlap$' "$root/callback.log" || true)" -eq 0 ]]

# A failed preflight never invokes submit and still releases the singleton.
root="$(scenario_root preflight-failure)"
dcp_ao_preflight_exact_contour() { return 23; }
if dcp_ao_gateway_with_lock "$root" fake-cli serialized_callback "$root"; then
	printf 'failed preflight reached submit callback\n' >&2
	exit 1
fi
[[ ! -e "$root/callback.log" ]]
[[ ! -e "$(dcp_ao_gateway_lock_dir "$root")" ]]
dcp_ao_preflight_exact_contour() { :; }

# A complete dead app-owned run-file is recovered once from the real AO "stale" state.
root="$(scenario_root stale-safe)"
mkdir -p "$root/runtime/run" "$root/runtime/gateway/ui.lock"
printf 'dcp-ui-1-2-3\n' >"$root/runtime/gateway/ui.lock/instance.id"
printf '{\n  "pid": 2147483647,\n  "port": 43231,\n  "startedAt": "2026-08-08T00:00:00Z",\n  "owner": "app",\n  "browserRuntimeToken": "dead-token",\n  "browserRuntimeAddress": "%s/runtime/run/browser.sock",\n  "dcpContourId": "%s",\n  "dcpUiInstanceId": "dcp-ui-1-2-3"\n}\n' "$root" "$(dcp_ao_contour_id)" >"$root/runtime/run/running.json"
printf '{\n  "state": "stale"\n}\n' >"$root/test-state.json"
dcp_ao_gateway_ensure "$root" fake-cli
[[ ! -e "$root/runtime/run/running.json" ]]
[[ "$(grep -c '^launch$' "$root/test-lifecycle.log")" -eq 1 ]]

# A ready foreign contour fails closed and does not launch a replacement.
root="$(scenario_root foreign-ready)"
printf '{\n  "state": "ready"\n}\n' >"$root/test-state.json"
dcp_ao_gateway_assert_pair() { return 1; }
if dcp_ao_gateway_ensure "$root" fake-cli; then
	printf 'foreign contour was accepted\n' >&2
	exit 1
fi
[[ ! -e "$root/test-lifecycle.log" ]]
dcp_ao_gateway_assert_pair() { :; }

# An incomplete/foreign stale identity is never deleted or replaced.
root="$(scenario_root foreign-stale)"
mkdir -p "$root/runtime/run"
printf '{\n  "pid": 2147483647,\n  "port": 43231,\n  "startedAt": "2026-08-08T00:00:00Z",\n  "owner": "persistent",\n  "browserRuntimeToken": "foreign",\n  "browserRuntimeAddress": "/tmp/foreign.sock"\n}\n' >"$root/runtime/run/running.json"
printf '{\n  "state": "stale"\n}\n' >"$root/test-state.json"
if dcp_ao_gateway_ensure "$root" fake-cli; then
	printf 'foreign stale contour was recovered\n' >&2
	exit 1
fi
[[ -f "$root/runtime/run/running.json" ]]
[[ ! -e "$root/test-lifecycle.log" ]]

# All other daemon states fail closed with no lifecycle mutation.
root="$(scenario_root ambiguous)"
printf '{\n  "state": "unhealthy"\n}\n' >"$root/test-state.json"
if dcp_ao_gateway_ensure "$root" fake-cli; then
	printf 'ambiguous contour was accepted\n' >&2
	exit 1
fi
[[ ! -e "$root/test-lifecycle.log" ]]

printf 'PASS I7 canonical gateway and singleton scenarios\n'
