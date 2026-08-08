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

dcp_ao_preflight_exact_contour() { :; }
dcp_ao_export_runtime_env() { :; }
dcp_ao_gateway_port_occupied() { return 1; }
dcp_ao_gateway_exact_ui_present() { return 1; }
dcp_ao_gateway_assert_pair() { :; }
dcp_ao_gateway_status_json() { cat "$1/test-state.json"; }
dcp_ao_gateway_launch_ui() {
	printf 'launch\n' >>"$1/test-launches.log"
	if [[ -n "${DCP_I7_TEST_LAUNCH_DELAY:-}" ]]; then sleep "$DCP_I7_TEST_LAUNCH_DELAY"; fi
	printf '{\n  "state": "ready"\n}\n' >"$1/test-state.json"
}

scenario_root() {
	local name="$1" root
	root="$TEST_ROOT/$name"
	mkdir -p "$root"
	printf '%s\n' "$root"
}

# Healthy, including an active-worker contour, is reused without a restart.
root="$(scenario_root healthy)"
printf '{\n  "state": "ready"\n}\n' >"$root/test-state.json"
dcp_ao_gateway_ensure "$root" fake-cli
[[ ! -e "$root/test-launches.log" ]]

# A fully stopped contour starts the source UI exactly once.
root="$(scenario_root stopped)"
printf '{\n  "state": "stopped"\n}\n' >"$root/test-state.json"
dcp_ao_gateway_ensure "$root" fake-cli
[[ "$(grep -c '^launch$' "$root/test-launches.log")" -eq 1 ]]

# Two concurrent submissions share the same singleton startup.
root="$(scenario_root concurrent)"
printf '{\n  "state": "stopped"\n}\n' >"$root/test-state.json"
export DCP_I7_TEST_LAUNCH_DELAY=0.2
(dcp_ao_gateway_ensure "$root" fake-cli) & first=$!
(dcp_ao_gateway_ensure "$root" fake-cli) & second=$!
wait "$first" "$second"
unset DCP_I7_TEST_LAUNCH_DELAY
[[ "$(grep -c '^launch$' "$root/test-launches.log")" -eq 1 ]]

# A complete, dead, app-owned run-file is the only stale state recovered.
root="$(scenario_root stale-safe)"
mkdir -p "$root/runtime/run"
printf '{\n  "pid": 999999,\n  "port": 43231,\n  "owner": "app",\n  "browserRuntimeToken": "dead-token"\n}\n' >"$root/runtime/run/running.json"
printf '{\n  "state": "stopped"\n}\n' >"$root/test-state.json"
dcp_ao_gateway_ensure "$root" fake-cli
[[ ! -e "$root/runtime/run/running.json" ]]
[[ "$(grep -c '^launch$' "$root/test-launches.log")" -eq 1 ]]

# Foreign/ambiguous ready state fails closed and never launches a replacement.
root="$(scenario_root foreign)"
printf '{\n  "state": "ready"\n}\n' >"$root/test-state.json"
dcp_ao_gateway_assert_pair() { return 1; }
if dcp_ao_gateway_ensure "$root" fake-cli; then
	printf 'foreign contour was accepted\n' >&2
	exit 1
fi
[[ ! -e "$root/test-launches.log" ]]
dcp_ao_gateway_assert_pair() { :; }

# Unsafe daemon states also fail closed with no lifecycle mutation.
root="$(scenario_root ambiguous)"
printf '{\n  "state": "error"\n}\n' >"$root/test-state.json"
if dcp_ao_gateway_ensure "$root" fake-cli; then
	printf 'ambiguous contour was accepted\n' >&2
	exit 1
fi
[[ ! -e "$root/test-launches.log" ]]

printf 'PASS I7 canonical gateway scenarios\n'
