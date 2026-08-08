#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
# shellcheck source=../lib/dcp-ao-common.sh
source "$REPO_ROOT/lib/dcp-ao-common.sh"
# shellcheck source=../lib/dcp-ao-gateway.sh
source "$REPO_ROOT/lib/dcp-ao-gateway.sh"

TEST_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/dcp-ao-i8-gateway.XXXXXX")"
cleanup() { rm -rf "$TEST_ROOT"; }
trap cleanup EXIT

export DCP_AO_GATEWAY_LOCK_ATTEMPTS=100
dcp_ao_preflight_exact_contour() { :; }
dcp_ao_export_runtime_env() { :; }
dcp_ao_gateway_port_occupied() { return 1; }
dcp_ao_gateway_assert_pair() { :; }
dcp_ao_gateway_exact_app_pid() {
	local pids count
	pids="$(sed -n '/^[0-9][0-9]*$/p' "$1/test-app-pids" 2>/dev/null || true)"
	count="$(printf '%s\n' "$pids" | awk 'NF{n++} END{print n+0}')"
	[[ "$count" -eq 1 ]] || { [[ "$count" -eq 0 ]] && return 1; return 2; }
	printf '%s\n' "$pids"
}
dcp_ao_gateway_status_json() { cat "$1/test-state.json"; }
dcp_ao_gateway_launch_app() {
	printf 'launch\n' >>"$1/test-lifecycle.log"
	if [[ -n "${DCP_I8_TEST_LAUNCH_DELAY:-}" ]]; then sleep "$DCP_I8_TEST_LAUNCH_DELAY"; fi
	printf '41001\n' >"$1/test-app-pids"
	printf '{\n  "state": "ready"\n}\n' >"$1/test-state.json"
}

scenario_root() { local root="$TEST_ROOT/$1"; mkdir -p "$root/state/run"; printf '%s\n' "$root"; }

# CLI status and the run-file must independently carry the exact service
# namespace before the gateway accepts an app/daemon pair.
root="$(scenario_root service-namespace)"
printf '{\n  "service": "dcp-orchestrator-daemon"\n}\n' >"$root/test-status.json"
printf '{\n  "service": "dcp-orchestrator-daemon"\n}\n' >"$root/state/run/running.json"
dcp_ao_gateway_assert_service_namespace "$(cat "$root/test-status.json")" "$root/state/run/running.json"
if dcp_ao_gateway_assert_service_namespace '{}' "$root/state/run/running.json"; then exit 1; fi
printf '{}\n' >"$root/state/run/running.json"
if dcp_ao_gateway_assert_service_namespace "$(cat "$root/test-status.json")" "$root/state/run/running.json"; then exit 1; fi
printf '{\n  "service": "foreign-daemon"\n}\n' >"$root/state/run/running.json"
if dcp_ao_gateway_assert_service_namespace "$(cat "$root/test-status.json")" "$root/state/run/running.json"; then exit 1; fi

# Warm submit reuses one already-ready app and daemon without lifecycle action.
root="$(scenario_root warm)"
printf '41001\n' >"$root/test-app-pids"
printf '{\n  "state": "ready"\n}\n' >"$root/test-state.json"
dcp_ao_gateway_ensure "$root" fake-cli
[[ ! -e "$root/test-lifecycle.log" ]]

# Cold submit opens the exact app once from a fully stopped contour.
root="$(scenario_root cold)"
printf '{\n  "state": "stopped"\n}\n' >"$root/test-state.json"
dcp_ao_gateway_ensure "$root" fake-cli
[[ "$(grep -c '^launch$' "$root/test-lifecycle.log")" -eq 1 ]]

# Two simultaneous cold entries serialize into one launch.
root="$(scenario_root concurrent-start)"
printf '{\n  "state": "stopped"\n}\n' >"$root/test-state.json"
export DCP_I8_TEST_LAUNCH_DELAY=0.2
(dcp_ao_gateway_ensure "$root" fake-cli) & first=$!
(dcp_ao_gateway_ensure "$root" fake-cli) & second=$!
wait "$first" "$second"
unset DCP_I8_TEST_LAUNCH_DELAY
[[ "$(grep -c '^launch$' "$root/test-lifecycle.log")" -eq 1 ]]

# The singleton covers the complete submission callback.
serialized_callback() {
	local root="$3"
	if ! mkdir "$root/critical" 2>/dev/null; then printf 'overlap\n' >>"$root/callback.log"; return 1; fi
	sleep 0.1; printf 'callback\n' >>"$root/callback.log"; rmdir "$root/critical"
}
root="$(scenario_root concurrent-submit)"
(dcp_ao_gateway_with_lock "$root" fake-cli serialized_callback "$root") & first=$!
(dcp_ao_gateway_with_lock "$root" fake-cli serialized_callback "$root") & second=$!
wait "$first" "$second"
[[ "$(grep -c '^callback$' "$root/callback.log")" -eq 2 ]]
[[ "$(grep -c '^overlap$' "$root/callback.log" || true)" -eq 0 ]]

# A failed preflight invokes no callback and releases the lock.
root="$(scenario_root preflight-failure)"
dcp_ao_preflight_exact_contour() { return 23; }
if dcp_ao_gateway_with_lock "$root" fake-cli serialized_callback "$root"; then exit 1; fi
[[ ! -e "$root/callback.log" && ! -e "$(dcp_ao_gateway_lock_dir "$root")" ]]
dcp_ao_preflight_exact_contour() { :; }

# Stopped plus any run-file fails closed and preserves it.
root="$(scenario_root stopped-runfile)"
printf '{}\n' >"$root/state/run/running.json"
printf '{\n  "state": "stopped"\n}\n' >"$root/test-state.json"
if dcp_ao_gateway_ensure "$root" fake-cli; then exit 1; fi
[[ -f "$root/state/run/running.json" && ! -e "$root/test-lifecycle.log" ]]

# A stale, unhealthy, or otherwise ambiguous daemon is never recovered.
root="$(scenario_root stale)"
printf '{"identity":"preserve"}\n' >"$root/state/run/running.json"
printf '{\n  "state": "stale"\n}\n' >"$root/test-state.json"
if dcp_ao_gateway_ensure "$root" fake-cli; then exit 1; fi
grep -Fq preserve "$root/state/run/running.json"
[[ ! -e "$root/test-lifecycle.log" ]]

# Ready without the exact app, or with duplicate exact app processes, fails.
root="$(scenario_root ready-without-app)"
printf '{\n  "state": "ready"\n}\n' >"$root/test-state.json"
if dcp_ao_gateway_ensure "$root" fake-cli; then exit 1; fi
root="$(scenario_root duplicate-app)"
printf '41001\n41002\n' >"$root/test-app-pids"
printf '{\n  "state": "ready"\n}\n' >"$root/test-state.json"
if dcp_ao_gateway_ensure "$root" fake-cli; then exit 1; fi

# Foreign port occupation blocks a cold launch.
root="$(scenario_root foreign-port)"
printf '{\n  "state": "stopped"\n}\n' >"$root/test-state.json"
dcp_ao_gateway_port_occupied() { return 0; }
if dcp_ao_gateway_ensure "$root" fake-cli; then exit 1; fi
[[ ! -e "$root/test-lifecycle.log" ]]

printf 'PASS I8 packaged-app gateway and singleton scenarios\n'
