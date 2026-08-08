#!/usr/bin/env bash

# The DCP gateway is the only normal lifecycle entrypoint. It serializes
# submissions, reuses a healthy UI-owned contour, launches the source UI when
# fully stopped, and fails closed rather than guessing about foreign processes.

dcp_ao_gateway_state() {
	printf '%s\n' "$1" | sed -n 's/^[[:space:]]*"state":[[:space:]]*"\([^"]*\)".*/\1/p'
}

dcp_ao_gateway_lock_dir() {
	printf '%s/runtime/gateway/submit.lock\n' "$1"
}

dcp_ao_gateway_acquire_lock() {
	local lab_root="$1" lock_dir owner attempt=0 max_attempts="${DCP_AO_GATEWAY_LOCK_ATTEMPTS:-600}"
	lock_dir="$(dcp_ao_gateway_lock_dir "$lab_root")"
	mkdir -p "$(dirname "$lock_dir")"
	while (( attempt < max_attempts )); do
		if mkdir "$lock_dir" 2>/dev/null; then
			printf '%s\n' "$$" >"$lock_dir/owner.pid"
			return 0
		fi
		owner="$(sed -n '1p' "$lock_dir/owner.pid" 2>/dev/null || true)"
		if [[ "$owner" =~ ^[0-9]+$ ]] && ! kill -0 "$owner" 2>/dev/null; then
			rm -f "$lock_dir/owner.pid"
			rmdir "$lock_dir" 2>/dev/null || true
		else
			sleep 0.1
		fi
		attempt=$((attempt + 1))
	done
	dcp_ao_fail 'canonical gateway is busy or its lock identity is ambiguous'
}

dcp_ao_gateway_release_lock() {
	local lock_dir
	lock_dir="$(dcp_ao_gateway_lock_dir "$1")"
	if [[ "$(sed -n '1p' "$lock_dir/owner.pid" 2>/dev/null || true)" == "$$" ]]; then
		rm -f "$lock_dir/owner.pid"
		rmdir "$lock_dir" 2>/dev/null || true
	fi
}

dcp_ao_gateway_claim_ui_instance() {
	local lab_root="$1" lock_dir owner instance
	if [[ "${DCP_AO_GATEWAY_LAUNCH_AUTH:-}" != "$(dcp_ao_contour_id)" ]]; then
		dcp_ao_fail 'source-run UI lifecycle is private to the canonical submit gateway'
		return 1
	fi
	instance="${DCP_AO_UI_INSTANCE_ID:-}"
	if [[ ! "$instance" =~ ^dcp-ui-[0-9]+-[0-9]+-[0-9]+$ ]]; then
		dcp_ao_fail 'source-run UI launch has no valid gateway instance identity'
		return 1
	fi
	lock_dir="$lab_root/runtime/gateway/ui.lock"
	mkdir -p "$(dirname "$lock_dir")"
	if mkdir "$lock_dir" 2>/dev/null; then
		printf '%s\n' "$$" >"$lock_dir/owner.pid"
		printf '%s\n' "$instance" >"$lock_dir/instance.id"
		return 0
	fi
	owner="$(sed -n '1p' "$lock_dir/owner.pid" 2>/dev/null || true)"
	if [[ "$owner" =~ ^[0-9]+$ ]] && ! kill -0 "$owner" 2>/dev/null; then
		rm -f "$lock_dir/owner.pid" "$lock_dir/instance.id"
		rmdir "$lock_dir" 2>/dev/null || true
		if mkdir "$lock_dir" 2>/dev/null; then
			printf '%s\n' "$$" >"$lock_dir/owner.pid"
			printf '%s\n' "$instance" >"$lock_dir/instance.id"
			return 0
		fi
	fi
	dcp_ao_fail 'canonical source-run UI is already running or its singleton identity is ambiguous'
}

dcp_ao_gateway_status_json() {
	local lab_root="$1" cli="$2"
	dcp_ao_export_runtime_env "$lab_root"
	"$cli" status --json
}

dcp_ao_gateway_port_occupied() {
	local port="${DCP_AO_PORT:-43231}"
	if command -v nc >/dev/null 2>&1; then
		nc -z -w 1 127.0.0.1 "$port" >/dev/null 2>&1
		return
	fi
	curl --silent --show-error --max-time 1 "http://127.0.0.1:$port/healthz" >/dev/null 2>&1
}

dcp_ao_gateway_exact_ui_present() {
	dcp_ao_assert_ui_contour "$1" >/dev/null 2>&1
}

dcp_ao_gateway_assert_pair() {
	local lab_root="$1" status="$2"
	dcp_ao_assert_daemon_contour "$lab_root" "$status" || return 1
	dcp_ao_assert_ui_contour "$lab_root"
}

dcp_ao_gateway_reconcile_stale_once() {
	local lab_root="$1" run_file pid owner port token address started_at
	run_file="$lab_root/runtime/run/running.json"
	[[ -e "$run_file" ]] || return 0
	[[ -f "$run_file" ]] || { dcp_ao_fail 'canonical run-file path is not a regular file'; return 1; }
	pid="$(sed -n 's/^[[:space:]]*"pid":[[:space:]]*\([0-9][0-9]*\),*$/\1/p' "$run_file")"
	port="$(sed -n 's/^[[:space:]]*"port":[[:space:]]*\([0-9][0-9]*\),*$/\1/p' "$run_file")"
	owner="$(sed -n 's/^[[:space:]]*"owner":[[:space:]]*"\([^"]*\)",*$/\1/p' "$run_file")"
	token="$(sed -n 's/^[[:space:]]*"browserRuntimeToken":[[:space:]]*"\([^"]*\)",*$/\1/p' "$run_file")"
	address="$(sed -n 's/^[[:space:]]*"browserRuntimeAddress":[[:space:]]*"\([^"]*\)",*$/\1/p' "$run_file")"
	started_at="$(sed -n 's/^[[:space:]]*"startedAt":[[:space:]]*"\([^"]*\)",*$/\1/p' "$run_file")"
	if [[ ! "$pid" =~ ^[0-9]+$ || "$port" != "${DCP_AO_PORT:-43231}" || "$owner" != app || -z "$token" || \
		"$address" != "$lab_root/runtime/run/browser.sock" || -z "$started_at" ]]; then
		dcp_ao_fail 'stale run-file identity is incomplete or foreign; refusing recovery'
		return 1
	fi
	if kill -0 "$pid" 2>/dev/null || dcp_ao_gateway_port_occupied; then
		dcp_ao_fail 'run-file still names a live or port-owning process; refusing recovery'
		return 1
	fi
	rm -f "$run_file"
}

dcp_ao_gateway_launch_ui() {
	local lab_root="$1" gateway_dir log_file instance
	gateway_dir="$lab_root/runtime/gateway"
	log_file="$gateway_dir/source-ui.log"
	mkdir -p "$gateway_dir"
	instance="dcp-ui-$$-$(date +%s)-${RANDOM:-0}"
	nohup env DCP_AO_LAB_ROOT="$lab_root" DCP_AO_GATEWAY_LAUNCH_AUTH="$(dcp_ao_contour_id)" \
		DCP_AO_UI_INSTANCE_ID="$instance" "$DCP_AO_REPO_ROOT/bin/dcp-ao" __gateway-launch >>"$log_file" 2>&1 </dev/null &
	printf '%s\n' "$!" >"$gateway_dir/ui-launch.pid"
}

dcp_ao_gateway_wait_ready() {
	local lab_root="$1" cli="$2" status state attempt=0
	while (( attempt < 120 )); do
		if ! status="$(dcp_ao_gateway_status_json "$lab_root" "$cli" 2>/dev/null)"; then
			if ! dcp_ao_gateway_exact_ui_present "$lab_root"; then
				dcp_ao_fail 'canonical source-run UI disappeared before daemon status became available'
				return 1
			fi
			sleep 0.5
			attempt=$((attempt + 1))
			continue
		fi
		state="$(dcp_ao_gateway_state "$status")"
		if [[ "$state" == ready ]]; then
			dcp_ao_gateway_assert_pair "$lab_root" "$status" || return 1
			return 0
		fi
		if [[ "$state" != stopped && "$state" != starting ]]; then
			dcp_ao_fail "canonical UI launch entered unsafe daemon state: ${state:-unknown}"
			return 1
		fi
		sleep 0.5
		attempt=$((attempt + 1))
	done
	dcp_ao_fail 'canonical source-run UI did not become ready within 60 seconds'
}

dcp_ao_gateway_ensure_locked() {
	local lab_root="$1" cli="$2" status state recovered_status
	status="$(dcp_ao_gateway_status_json "$lab_root" "$cli")" || return 1
	state="$(dcp_ao_gateway_state "$status")"
	case "$state" in
		ready)
			dcp_ao_gateway_assert_pair "$lab_root" "$status"
			return
			;;
		stopped)
			if [[ -e "$lab_root/runtime/run/running.json" ]]; then
				dcp_ao_fail 'stopped status conflicts with an existing run-file; refusing recovery'
				return 1
			fi
			if dcp_ao_gateway_exact_ui_present "$lab_root"; then
				dcp_ao_gateway_wait_ready "$lab_root" "$cli"
				return
			fi
			if dcp_ao_gateway_port_occupied; then
				dcp_ao_fail 'canonical port is occupied without a proven DCP UI/daemon identity'
				return 1
			fi
			dcp_ao_gateway_launch_ui "$lab_root" || return 1
			dcp_ao_gateway_wait_ready "$lab_root" "$cli"
			return
			;;
		stale)
			if dcp_ao_gateway_exact_ui_present "$lab_root"; then
				dcp_ao_fail 'stale daemon state still has a live canonical UI; refusing recovery'
				return 1
			fi
			dcp_ao_gateway_reconcile_stale_once "$lab_root" || return 1
			recovered_status="$(dcp_ao_gateway_status_json "$lab_root" "$cli")" || return 1
			if [[ "$(dcp_ao_gateway_state "$recovered_status")" != stopped ]]; then
				dcp_ao_fail 'bounded stale recovery did not produce a fully stopped contour'
				return 1
			fi
			if dcp_ao_gateway_port_occupied; then
				dcp_ao_fail 'canonical port is occupied after bounded stale recovery'
				return 1
			fi
			dcp_ao_gateway_launch_ui "$lab_root" || return 1
			dcp_ao_gateway_wait_ready "$lab_root" "$cli"
			return
			;;
		*)
			dcp_ao_fail "daemon state is ambiguous or unsafe: ${state:-unknown}; no process was stopped or started"
			return 1
			;;
	esac
}

dcp_ao_gateway_ensure() {
	local lab_root="$1" cli="$2" result
	dcp_ao_gateway_acquire_lock "$lab_root" || return 1
	if dcp_ao_preflight_exact_contour "$lab_root" >/dev/null && \
		dcp_ao_gateway_ensure_locked "$lab_root" "$cli"; then
		result=0
	else
		result=$?
	fi
	dcp_ao_gateway_release_lock "$lab_root"
	return "$result"
}

# Hold the same singleton through lifecycle proof and the complete submission.
# The callback is invoked only after exact-contour preflight and always releases
# the lock before this function returns.
dcp_ao_gateway_with_lock() {
	local lab_root="$1" cli="$2" callback="$3" result
	shift 3
	dcp_ao_gateway_acquire_lock "$lab_root" || return 1
	if dcp_ao_preflight_exact_contour "$lab_root" >/dev/null && \
		"$callback" "$lab_root" "$cli" "$@"; then
		result=0
	else
		result=$?
	fi
	dcp_ao_gateway_release_lock "$lab_root"
	return "$result"
}
