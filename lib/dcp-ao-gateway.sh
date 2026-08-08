#!/usr/bin/env bash

# The gateway never owns the application or daemon. It serializes submissions,
# proves the exact installed bundle/process pair, opens that absolute bundle
# only from a completely stopped state, and otherwise fails closed.

dcp_ao_gateway_state() {
	printf '%s\n' "$1" | sed -n 's/^[[:space:]]*"state":[[:space:]]*"\([^"]*\)".*/\1/p'
}

dcp_ao_gateway_assert_service_namespace() {
	local status="$1" run_file="$2" status_service run_service expected='dcp-orchestrator-daemon'
	status_service="$(printf '%s\n' "$status" | sed -n 's/^[[:space:]]*"service":[[:space:]]*"\([^"]*\)".*/\1/p')"
	run_service="$(sed -n 's/^[[:space:]]*"service":[[:space:]]*"\([^"]*\)".*/\1/p' "$run_file")"
	[[ "$status_service" == "$expected" && "$run_service" == "$expected" ]] || {
		dcp_ao_fail 'daemon service namespace mismatch'; return 1;
	}
}

dcp_ao_gateway_lock_dir() { printf '%s/state/gateway/submit.lock\n' "$1"; }

dcp_ao_gateway_acquire_lock() {
	local lab_root="$1" lock_dir owner attempt=0 max_attempts="${DCP_AO_GATEWAY_LOCK_ATTEMPTS:-600}"
	lock_dir="$(dcp_ao_gateway_lock_dir "$lab_root")"; mkdir -p "$(dirname "$lock_dir")"
	while (( attempt < max_attempts )); do
		if mkdir "$lock_dir" 2>/dev/null; then printf '%s\n' "$$" >"$lock_dir/owner.pid"; return 0; fi
		owner="$(sed -n '1p' "$lock_dir/owner.pid" 2>/dev/null || true)"
		if [[ "$owner" =~ ^[0-9]+$ ]] && ! kill -0 "$owner" 2>/dev/null; then
			rm -f "$lock_dir/owner.pid"; rmdir "$lock_dir" 2>/dev/null || true
		else sleep 0.1
		fi
		attempt=$((attempt + 1))
	done
	dcp_ao_fail 'canonical submit gateway is busy or its lock is ambiguous'
}

dcp_ao_gateway_release_lock() {
	local lock_dir; lock_dir="$(dcp_ao_gateway_lock_dir "$1")"
	if [[ "$(sed -n '1p' "$lock_dir/owner.pid" 2>/dev/null || true)" == "$$" ]]; then
		rm -f "$lock_dir/owner.pid"; rmdir "$lock_dir" 2>/dev/null || true
	fi
}

dcp_ao_gateway_status_json() {
	dcp_ao_export_runtime_env "$1"
	"$2" status --json
}

dcp_ao_gateway_port_occupied() {
	local port="${DCP_AO_PORT:-43231}"
	if command -v nc >/dev/null 2>&1; then nc -z -w 1 127.0.0.1 "$port" >/dev/null 2>&1; return; fi
	curl --silent --show-error --max-time 1 "http://127.0.0.1:$port/healthz" >/dev/null 2>&1
}

dcp_ao_gateway_app_pids() {
	local executable; executable="$(dcp_ao_app_executable)"
	ps -axo pid=,command= | awk -v exact="$executable" '$0 ~ /^[[:space:]]*[0-9]+[[:space:]]+/ { pid=$1; sub(/^[[:space:]]*[0-9]+[[:space:]]+/, "", $0); if ($0 == exact) print pid }'
}

dcp_ao_gateway_exact_app_pid() {
	local pids count
	pids="$(dcp_ao_gateway_app_pids)"; count="$(printf '%s\n' "$pids" | awk 'NF{n++} END{print n+0}')"
	[[ "$count" -eq 1 ]] || { [[ "$count" -eq 0 ]] && return 1; dcp_ao_fail 'more than one exact DCP app process is running'; return 2; }
	printf '%s\n' "$pids"
}

dcp_ao_gateway_assert_pair() {
	local lab_root="$1" status="$2" run_file app_pid status_pid run_pid run_port owner contour run_app_pid instance bundle_id bundle_path token address process_command daemon
	run_file="$(dcp_ao_run_file "$lab_root")"; daemon="$(dcp_ao_embedded_cli)"
	app_pid="$(dcp_ao_gateway_exact_app_pid "$lab_root")" || { dcp_ao_fail 'ready daemon has no single exact DCP app owner'; return 1; }
	[[ -f "$run_file" ]] || { dcp_ao_fail 'ready daemon has no canonical run-file'; return 1; }
	status_pid="$(printf '%s\n' "$status" | sed -n 's/^[[:space:]]*"pid": \([0-9][0-9]*\),*$/\1/p')"
	run_pid="$(sed -n 's/^[[:space:]]*"pid":[[:space:]]*\([0-9][0-9]*\),*$/\1/p' "$run_file")"
	run_port="$(sed -n 's/^[[:space:]]*"port":[[:space:]]*\([0-9][0-9]*\),*$/\1/p' "$run_file")"
	owner="$(sed -n 's/^[[:space:]]*"owner":[[:space:]]*"\([^"]*\)",*$/\1/p' "$run_file")"
	contour="$(sed -n 's/^[[:space:]]*"dcpContourId":[[:space:]]*"\([^"]*\)",*$/\1/p' "$run_file")"
	run_app_pid="$(sed -n 's/^[[:space:]]*"dcpAppPid":[[:space:]]*\([0-9][0-9]*\),*$/\1/p' "$run_file")"
	instance="$(sed -n 's/^[[:space:]]*"dcpAppInstanceId":[[:space:]]*"\([^"]*\)",*$/\1/p' "$run_file")"
	bundle_id="$(sed -n 's/^[[:space:]]*"dcpAppBundleId":[[:space:]]*"\([^"]*\)",*$/\1/p' "$run_file")"
	bundle_path="$(sed -n 's/^[[:space:]]*"dcpAppBundlePath":[[:space:]]*"\([^"]*\)",*$/\1/p' "$run_file")"
	token="$(sed -n 's/^[[:space:]]*"browserRuntimeToken":[[:space:]]*"\([^"]*\)",*$/\1/p' "$run_file")"
	address="$(sed -n 's/^[[:space:]]*"browserRuntimeAddress":[[:space:]]*"\([^"]*\)",*$/\1/p' "$run_file")"
	if [[ ! "$run_pid" =~ ^[0-9]+$ || "$status_pid" != "$run_pid" || "$run_port" != "${DCP_AO_PORT:-43231}" || "$owner" != app || \
		"$contour" != "$(dcp_ao_contour_id)" || "$run_app_pid" != "$app_pid" || ! "$instance" =~ ^dcp-app-[0-9]+-[0-9a-f-]+$ || \
		"$bundle_id" != pro.devcontrol.dcp-orchestrator || "$bundle_path" != "$(dcp_ao_app_path)" || -z "$token" || "$address" != "$lab_root/state/run/browser.sock" ]]; then
		dcp_ao_fail 'daemon run-file does not prove the exact DCP app identity'; return 1
	fi
	process_command="$(ps -p "$run_pid" -o command=)"
	case "$process_command" in "$daemon daemon"*) ;; *) dcp_ao_fail 'daemon executable is not the bundled DCP daemon'; return 1;; esac
	dcp_ao_gateway_assert_service_namespace "$status" "$run_file" || return 1
}

dcp_ao_gateway_launch_app() {
	local app; app="$(dcp_ao_app_path)"
	/usr/bin/open "$app"
}

dcp_ao_gateway_wait_ready() {
	local lab_root="$1" cli="$2" status state app_pid attempt=0
	while (( attempt < 120 )); do
		app_pid="$(dcp_ao_gateway_exact_app_pid "$lab_root" 2>/dev/null || true)"
		[[ -n "$app_pid" ]] || { sleep 0.5; attempt=$((attempt + 1)); continue; }
		status="$(dcp_ao_gateway_status_json "$lab_root" "$cli" 2>/dev/null || true)"
		state="$(dcp_ao_gateway_state "$status")"
		if [[ "$state" == ready ]]; then dcp_ao_gateway_assert_pair "$lab_root" "$status"; return; fi
		[[ -z "$state" || "$state" == stopped || "$state" == starting ]] || { dcp_ao_fail "app startup entered unsafe daemon state: ${state:-unknown}"; return 1; }
		sleep 0.5; attempt=$((attempt + 1))
	done
	dcp_ao_fail 'exact DCP app and daemon did not become ready within 60 seconds'
}

dcp_ao_gateway_ensure_locked() {
	local lab_root="$1" cli="$2" status state app_pid_result app_pid
	status="$(dcp_ao_gateway_status_json "$lab_root" "$cli")" || return 1
	state="$(dcp_ao_gateway_state "$status")"
	app_pid_result=0; app_pid="$(dcp_ao_gateway_exact_app_pid "$lab_root")" || app_pid_result=$?
	[[ "$app_pid_result" -ne 2 ]] || return 1
	case "$state" in
		ready)
			[[ -n "$app_pid" ]] || { dcp_ao_fail 'ready daemon is foreign because exact app is absent'; return 1; }
			dcp_ao_gateway_assert_pair "$lab_root" "$status"
			;;
		stopped)
			if [[ -e "$(dcp_ao_run_file "$lab_root")" ]]; then dcp_ao_fail 'stopped state conflicts with a run-file; refusing mutation'; return 1; fi
			if [[ -n "$app_pid" ]]; then dcp_ao_gateway_wait_ready "$lab_root" "$cli"; return; fi
			if dcp_ao_gateway_port_occupied; then dcp_ao_fail 'canonical port is occupied without proven DCP ownership'; return 1; fi
			dcp_ao_gateway_launch_app "$lab_root" || return 1
			dcp_ao_gateway_wait_ready "$lab_root" "$cli"
			;;
		*)
			dcp_ao_fail "daemon state is ambiguous or unsafe: ${state:-unknown}; gateway changed nothing"
			return 1
			;;
	esac
}

dcp_ao_gateway_with_lock() {
	local lab_root="$1" cli="$2" callback="$3" result
	shift 3
	dcp_ao_gateway_acquire_lock "$lab_root" || return 1
	if dcp_ao_preflight_exact_contour "$lab_root" >/dev/null && "$callback" "$lab_root" "$cli" "$@"; then result=0; else result=$?; fi
	dcp_ao_gateway_release_lock "$lab_root"
	return "$result"
}

dcp_ao_gateway_ensure() {
	local lab_root="$1" cli="$2"
	dcp_ao_gateway_with_lock "$lab_root" "$cli" dcp_ao_gateway_ensure_locked
}
