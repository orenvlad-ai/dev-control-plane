#!/usr/bin/env bash

# Installation may replace one already-running canonical DCP application, but
# only after proving the exact app/daemon pair and proving that no worker,
# reviewer or bounded Stage 2 arbiter model process is active. Unknown process
# state is never treated as idle. The submit gateway lock closes the normal
# submission race while the proof, graceful stop, backup and bundle swap are in
# progress.

dcp_ao_install_sqlite() {
	local database="$1"
	shift
	sqlite3 -readonly -batch -noheader "$database" "$@"
}

dcp_ao_install_tmux() { tmux "$@"; }
dcp_ao_install_ps() { ps "$@"; }

dcp_ao_install_process_state() {
	local handle_id="$1" action_id="$2" action_kind="$3" pane_output pane_pid process_output lowered
	[[ "$handle_id" =~ ^[a-zA-Z0-9_-]+$ && "$action_id" =~ ^[a-zA-Z0-9_-]+$ ]] || {
		dcp_ao_fail "$action_kind has an invalid runtime identity"; return 1;
	}
	if pane_output="$(dcp_ao_install_tmux display-message -p -t "$handle_id:0.0" '#{pane_pid}' 2>&1)"; then
		:
	else
		lowered="$(printf '%s' "$pane_output" | tr '[:upper:]' '[:lower:]')"
		case "$lowered" in
			*"can't find session"*|*"session not found"*) printf 'stale\n'; return 0 ;;
			*) dcp_ao_fail "$action_kind process state is ambiguous for $handle_id"; return 1 ;;
		esac
	fi
	pane_pid="$(printf '%s\n' "$pane_output" | sed -n '1{s/[[:space:]]//g;p;}')"
	[[ "$pane_pid" =~ ^[1-9][0-9]*$ ]] || { dcp_ao_fail "$action_kind pane pid is invalid"; return 1; }
	process_output="$(dcp_ao_install_ps -ww -axo pid=,ppid=,args=)" || {
		dcp_ao_fail "$action_kind process tree could not be inspected"; return 1;
	}
	if printf '%s\n' "$process_output" | awk -v root="$pane_pid" '
		$1 ~ /^[0-9]+$/ && $2 ~ /^[0-9]+$/ { parent[$1]=$2 }
		END {
			desc[root]=1
			for (pass=0; pass<1000; pass++) {
				changed=0
				for (pid in parent) if (!desc[pid] && desc[parent[pid]]) { desc[pid]=1; changed=1 }
				if (!changed) break
			}
			for (pid in desc) if (pid != root && desc[pid]) exit 0
			exit 1
		}'; then
		printf 'active\n'
	else
		printf 'stale\n'
	fi
}

dcp_ao_install_review_process_state() {
	dcp_ao_install_process_state "$1" "$2" reviewer
}

dcp_ao_install_worker_process_state() {
	dcp_ao_install_process_state "$1" "$2" worker
}

dcp_ao_install_arbiter_process_state() {
	dcp_ao_install_process_state "$1" "$2" arbiter
}

dcp_ao_install_assert_no_active_model_actions() {
	local lab_root="$1" database workers reviews arbiter_table arbiters successor_table successors recovery_table recoveries handle_id action_id activity_state state
	database="$(dcp_ao_data_dir "$lab_root")/ao.db"
	dcp_ao_require_tool sqlite3 || return 1
	[[ -f "$database" ]] || { dcp_ao_fail 'canonical SQLite is absent while the DCP runtime is ready'; return 1; }
	workers="$(dcp_ao_install_sqlite "$database" \
		"SELECT runtime_handle_id || '|' || runtime_launch_id || '|' || activity_state FROM sessions WHERE is_terminated = 0 AND (activity_state = 'active' OR coalesce(runtime_launch_id, '') <> '') ORDER BY created_at, id;")" || {
		dcp_ao_fail 'active worker state could not be read'; return 1;
	}
	while IFS='|' read -r handle_id action_id activity_state; do
		[[ -n "$handle_id" || -n "$action_id" || -n "$activity_state" ]] || continue
		[[ "$activity_state" != active ]] || { dcp_ao_fail 'refusing install while a worker model action is active'; return 1; }
		[[ -n "$handle_id" && -n "$action_id" ]] || { dcp_ao_fail 'stale worker launch has incomplete runtime identity'; return 1; }
		state="$(dcp_ao_install_worker_process_state "$handle_id" "$action_id")" || return 1
		[[ "$state" == stale ]] || { dcp_ao_fail "refusing install while worker launch $action_id is active"; return 1; }
	done <<<"$workers"
	reviews="$(dcp_ao_install_sqlite "$database" \
		"SELECT r.reviewer_handle_id || char(9) || rr.id FROM review_run rr JOIN review r ON r.id = rr.review_id WHERE rr.status = 'running' AND rr.verdict = '' ORDER BY rr.created_at, rr.id;")" || {
		dcp_ao_fail 'running reviewer state could not be read'; return 1;
	}
	while IFS=$'\t' read -r handle_id action_id; do
		[[ -n "$handle_id" && -n "$action_id" ]] || continue
		state="$(dcp_ao_install_review_process_state "$handle_id" "$action_id")" || return 1
		[[ "$state" == stale ]] || { dcp_ao_fail "refusing install while reviewer run $action_id is active"; return 1; }
	done <<<"$reviews"
	arbiter_table="$(dcp_ao_install_sqlite "$database" \
		"SELECT count(*) FROM sqlite_master WHERE type = 'table' AND name = 'dcp_review_lab_arbiter_v1';")" || {
		dcp_ao_fail 'arbiter action schema state could not be read'; return 1;
	}
	[[ "$arbiter_table" == 0 || "$arbiter_table" == 1 ]] || { dcp_ao_fail 'arbiter action schema state is ambiguous'; return 1; }
	if [[ "$arbiter_table" == 1 ]]; then
		arbiters="$(dcp_ao_install_sqlite "$database" \
			"SELECT runtime_handle_id || char(9) || launch_id FROM dcp_review_lab_arbiter_v1 WHERE status = 'running' AND model_call_count = 1 ORDER BY created_at, incident_id;")" || {
			dcp_ao_fail 'running arbiter state could not be read'; return 1;
		}
		while IFS=$'\t' read -r handle_id action_id; do
			[[ -n "$handle_id" && -n "$action_id" ]] || continue
			[[ "$handle_id" == dcp-global-release-arbiter-v1 && "$action_id" =~ ^dcp-global-release-[0-9a-f]{64}$ ]] || {
				dcp_ao_fail 'running arbiter has invalid exact identity'; return 1;
			}
			state="$(dcp_ao_install_arbiter_process_state "$handle_id" "$action_id")" || return 1
			[[ "$state" == stale ]] || { dcp_ao_fail "refusing install while arbiter call $action_id is active"; return 1; }
		done <<<"$arbiters"
	fi
	successor_table="$(dcp_ao_install_sqlite "$database" \
		"SELECT count(*) FROM sqlite_master WHERE type = 'table' AND name = 'dcp_review_lab_arbiter_v1_successor_attempt';")" || {
		dcp_ao_fail 'arbiter successor schema state could not be read'; return 1;
	}
	[[ "$successor_table" == 0 || "$successor_table" == 1 ]] || { dcp_ao_fail 'arbiter successor schema state is ambiguous'; return 1; }
	if [[ "$successor_table" == 1 ]]; then
		successors="$(dcp_ao_install_sqlite "$database" \
			"SELECT runtime_handle_id || char(9) || launch_id FROM dcp_review_lab_arbiter_v1_successor_attempt WHERE status = 'running' AND model_call_count = 1 ORDER BY authorized_at, attempt_id;")" || {
			dcp_ao_fail 'running arbiter successor state could not be read'; return 1;
		}
		while IFS=$'\t' read -r handle_id action_id; do
			[[ -n "$handle_id" && -n "$action_id" ]] || continue
			[[ "$handle_id" == dcp-global-release-arbiter-v1-successor && "$action_id" == dcp-arbiter-successor-3c62ea80b56ef94165519d4f01e4c449c320bff22d16b902dd68d4a1a355ea7d ]] || {
				dcp_ao_fail 'running arbiter successor has invalid exact identity'; return 1;
			}
			state="$(dcp_ao_install_arbiter_process_state "$handle_id" "$action_id")" || return 1
			[[ "$state" == stale ]] || { dcp_ao_fail "refusing install while arbiter successor call $action_id is active"; return 1; }
		done <<<"$successors"
	fi
	recovery_table="$(dcp_ao_install_sqlite "$database" \
		"SELECT count(*) FROM sqlite_master WHERE type = 'table' AND name = 'dcp_review_lab_card12_fresh_worker_recovery';")" || {
		dcp_ao_fail 'card-12 fresh-worker recovery schema state could not be read'; return 1;
	}
	[[ "$recovery_table" == 0 || "$recovery_table" == 1 ]] || { dcp_ao_fail 'card-12 fresh-worker recovery schema state is ambiguous'; return 1; }
	if [[ "$recovery_table" == 1 ]]; then
		recoveries="$(dcp_ao_install_sqlite "$database" \
			"SELECT runtime_handle_id || char(9) || launch_id FROM dcp_review_lab_card12_fresh_worker_recovery WHERE status = 'running' AND worker_model_call_count = 1 ORDER BY authorized_at, recovery_id;")" || {
			dcp_ao_fail 'running card-12 fresh-worker recovery state could not be read'; return 1;
		}
		while IFS=$'\t' read -r handle_id action_id; do
			[[ -n "$handle_id" && -n "$action_id" ]] || continue
			[[ "$handle_id" == dcp-card12-fresh-worker-recovery && "$action_id" == dcp-card12-fresh-worker-recovery-d2b7142bc9e5844ba165abe24d3222b3e1a94c3577fba5f6f8d97ec3dbad151b ]] || {
				dcp_ao_fail 'running card-12 fresh-worker recovery has invalid exact identity'; return 1;
			}
			state="$(dcp_ao_install_worker_process_state "$handle_id" "$action_id")" || return 1
			[[ "$state" == stale ]] || { dcp_ao_fail "refusing install while card-12 fresh-worker recovery $action_id is active"; return 1; }
		done <<<"$recoveries"
	fi
}

dcp_ao_install_request_exact_app_quit() {
	local app_pid="$1"
	[[ "$app_pid" =~ ^[1-9][0-9]*$ ]] || { dcp_ao_fail 'exact app pid is invalid'; return 1; }
	kill -TERM "$app_pid"
}

dcp_ao_install_wait_stopped() {
	local lab_root="$1" prior_app_pid="$2" prior_daemon_pid="$3" attempt=0 current result
	while (( attempt < 120 )); do
		if ! kill -0 "$prior_app_pid" 2>/dev/null && ! kill -0 "$prior_daemon_pid" 2>/dev/null && \
			[[ ! -e "$(dcp_ao_run_file "$lab_root")" ]] && ! dcp_ao_gateway_port_occupied; then
			result=0; current="$(dcp_ao_gateway_exact_app_pid "$lab_root" 2>/dev/null)" || result=$?
			[[ "$result" -ne 2 ]] || { dcp_ao_fail 'duplicate exact DCP app appeared during install'; return 1; }
			[[ -z "$current" ]] || { dcp_ao_fail 'a new exact DCP app appeared during install'; return 1; }
			return 0
		fi
		sleep 0.5
		attempt=$((attempt + 1))
	done
	dcp_ao_fail 'exact DCP app/daemon did not stop cleanly within 60 seconds'
}

dcp_ao_install_prepare_runtime() {
	local lab_root="$1" cli="$2" status state app_pid_result=0 app_pid run_file daemon_pid
	status="$(dcp_ao_gateway_status_json "$lab_root" "$cli")" || {
		dcp_ao_fail 'installed daemon status is unavailable or ambiguous'; return 1;
	}
	state="$(dcp_ao_gateway_state "$status")"
	app_pid="$(dcp_ao_gateway_exact_app_pid "$lab_root")" || app_pid_result=$?
	[[ "$app_pid_result" -ne 2 ]] || return 1
	case "$state" in
		stopped)
			[[ -z "$app_pid" ]] || { dcp_ao_fail 'stopped status conflicts with an exact DCP app process'; return 1; }
			[[ ! -e "$(dcp_ao_run_file "$lab_root")" ]] || { dcp_ao_fail 'stopped status conflicts with a run-file'; return 1; }
			if dcp_ao_gateway_port_occupied; then dcp_ao_fail 'canonical port is occupied without proven DCP ownership'; return 1; fi
			return 0
			;;
		ready)
			[[ -n "$app_pid" ]] || { dcp_ao_fail 'ready daemon has no exact DCP app owner'; return 1; }
			dcp_ao_gateway_assert_pair "$lab_root" "$status" || return 1
			dcp_ao_install_assert_no_active_model_actions "$lab_root" || return 1
			run_file="$(dcp_ao_run_file "$lab_root")"
			daemon_pid="$(sed -n 's/^[[:space:]]*"pid":[[:space:]]*\([0-9][0-9]*\),*$/\1/p' "$run_file")"
			[[ "$daemon_pid" =~ ^[1-9][0-9]*$ ]] || { dcp_ao_fail 'ready daemon pid is invalid'; return 1; }
			dcp_ao_install_request_exact_app_quit "$app_pid" || return 1
			dcp_ao_install_wait_stopped "$lab_root" "$app_pid" "$daemon_pid"
			;;
		*)
			dcp_ao_fail "daemon state is ambiguous or unsafe for install: ${state:-unknown}"
			return 1
			;;
	esac
}
