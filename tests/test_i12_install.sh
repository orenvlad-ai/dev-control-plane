#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
# shellcheck source=../lib/dcp-ao-common.sh
source "$REPO_ROOT/lib/dcp-ao-common.sh"
# shellcheck source=../lib/dcp-ao-gateway.sh
source "$REPO_ROOT/lib/dcp-ao-gateway.sh"
# shellcheck source=../lib/dcp-ao-install.sh
source "$REPO_ROOT/lib/dcp-ao-install.sh"

TEST_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/dcp-ao-i12-install.XXXXXX")"
cleanup() { rm -rf "$TEST_ROOT"; }
trap cleanup EXIT

lab_root="$TEST_ROOT/model-actions"
mkdir -p "$lab_root/data"
database="$lab_root/data/ao.db"
sqlite3 "$database" <<'SQL'
CREATE TABLE sessions (
  id TEXT PRIMARY KEY,
  activity_state TEXT NOT NULL,
  runtime_handle_id TEXT NOT NULL DEFAULT '',
  runtime_launch_id TEXT NOT NULL DEFAULT '',
  is_terminated INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE TABLE review (
  id TEXT PRIMARY KEY,
  reviewer_handle_id TEXT NOT NULL
);
CREATE TABLE review_run (
  id TEXT PRIMARY KEY,
  review_id TEXT NOT NULL,
  status TEXT NOT NULL,
  verdict TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);
INSERT INTO sessions VALUES ('worker-1', 'idle', 'worker-1', '', 0, '2026-08-09T00:00:00Z');
SQL

# A ready contour is replaceable only when every persisted model action is
# proven inactive. A stale running reviewer row is deliberately allowed so the
# new daemon can reconcile it at startup without an installer-side DB write.
DCP_I12_TEST_REVIEW_STATE=stale
DCP_I12_TEST_WORKER_STATE=stale
DCP_I12_TEST_ARBITER_STATE=stale
dcp_ao_install_review_process_state() { printf '%s\n' "$DCP_I12_TEST_REVIEW_STATE"; }
dcp_ao_install_worker_process_state() { printf '%s\n' "$DCP_I12_TEST_WORKER_STATE"; }
dcp_ao_install_arbiter_process_state() { printf '%s\n' "$DCP_I12_TEST_ARBITER_STATE"; }
dcp_ao_install_assert_no_active_model_actions "$lab_root"
sqlite3 "$database" "UPDATE sessions SET activity_state='active', runtime_launch_id='launch-1' WHERE id='worker-1';"
if dcp_ao_install_assert_no_active_model_actions "$lab_root"; then exit 1; fi
sqlite3 "$database" "UPDATE sessions SET activity_state='exited' WHERE id='worker-1';"
DCP_I12_TEST_WORKER_STATE=active
if dcp_ao_install_assert_no_active_model_actions "$lab_root"; then exit 1; fi
DCP_I12_TEST_WORKER_STATE=stale
dcp_ao_install_assert_no_active_model_actions "$lab_root"
sqlite3 "$database" "UPDATE sessions SET runtime_handle_id='' WHERE id='worker-1';"
if dcp_ao_install_assert_no_active_model_actions "$lab_root"; then exit 1; fi
sqlite3 "$database" "UPDATE sessions SET runtime_handle_id='worker-1' WHERE id='worker-1';"
dcp_ao_install_worker_process_state() { return 1; }
if dcp_ao_install_assert_no_active_model_actions "$lab_root"; then exit 1; fi
dcp_ao_install_worker_process_state() { printf '%s\n' "$DCP_I12_TEST_WORKER_STATE"; }
sqlite3 "$database" "UPDATE sessions SET activity_state='idle', runtime_launch_id='' WHERE id='worker-1';"
sqlite3 "$database" "INSERT INTO review VALUES ('review-1','review-worker-1'); INSERT INTO review_run VALUES ('run-1','review-1','running','','2026-08-09T00:00:00Z');"
DCP_I12_TEST_REVIEW_STATE=active
if dcp_ao_install_assert_no_active_model_actions "$lab_root"; then exit 1; fi
DCP_I12_TEST_REVIEW_STATE=stale
dcp_ao_install_assert_no_active_model_actions "$lab_root"
sqlite3 "$database" <<'SQL'
CREATE TABLE dcp_review_lab_arbiter_v1 (
  incident_id TEXT PRIMARY KEY,
  runtime_handle_id TEXT NOT NULL,
  launch_id TEXT NOT NULL,
  status TEXT NOT NULL,
  model_call_count INTEGER NOT NULL,
  created_at TEXT NOT NULL
);
INSERT INTO dcp_review_lab_arbiter_v1 VALUES (
  'dcp-global-release-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
  'dcp-global-release-arbiter-v1',
  'dcp-global-release-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
  'requested', 0, '2026-08-11T00:00:00Z'
);
SQL
dcp_ao_install_assert_no_active_model_actions "$lab_root"
sqlite3 "$database" "UPDATE dcp_review_lab_arbiter_v1 SET status='running', model_call_count=1;"
DCP_I12_TEST_ARBITER_STATE=active
if dcp_ao_install_assert_no_active_model_actions "$lab_root"; then exit 1; fi
DCP_I12_TEST_ARBITER_STATE=stale
dcp_ao_install_assert_no_active_model_actions "$lab_root"
sqlite3 "$database" "UPDATE dcp_review_lab_arbiter_v1 SET runtime_handle_id='foreign-arbiter';"
if dcp_ao_install_assert_no_active_model_actions "$lab_root"; then exit 1; fi
sqlite3 "$database" "UPDATE dcp_review_lab_arbiter_v1 SET runtime_handle_id='dcp-global-release-arbiter-v1';"
dcp_ao_install_arbiter_process_state() { return 1; }
if dcp_ao_install_assert_no_active_model_actions "$lab_root"; then exit 1; fi
dcp_ao_install_arbiter_process_state() { printf '%s\n' "$DCP_I12_TEST_ARBITER_STATE"; }
dcp_ao_install_review_process_state() { return 1; }
if dcp_ao_install_assert_no_active_model_actions "$lab_root"; then exit 1; fi
dcp_ao_install_review_process_state() { printf '%s\n' "$DCP_I12_TEST_REVIEW_STATE"; }
sqlite3 "$database" <<'SQL'
CREATE TABLE dcp_review_lab_arbiter_v1_successor_attempt (
  attempt_id TEXT PRIMARY KEY,
  runtime_handle_id TEXT NOT NULL,
  launch_id TEXT NOT NULL,
  status TEXT NOT NULL,
  model_call_count INTEGER NOT NULL,
  authorized_at TEXT NOT NULL
);
INSERT INTO dcp_review_lab_arbiter_v1_successor_attempt VALUES (
  'dcp-arbiter-successor-3c62ea80b56ef94165519d4f01e4c449c320bff22d16b902dd68d4a1a355ea7d',
  'dcp-global-release-arbiter-v1-successor',
  'dcp-arbiter-successor-3c62ea80b56ef94165519d4f01e4c449c320bff22d16b902dd68d4a1a355ea7d',
  'requested', 0, '2026-08-12T00:00:00Z'
);
SQL
dcp_ao_install_assert_no_active_model_actions "$lab_root"
sqlite3 "$database" "UPDATE dcp_review_lab_arbiter_v1_successor_attempt SET status='running', model_call_count=1;"
DCP_I12_TEST_ARBITER_STATE=active
if dcp_ao_install_assert_no_active_model_actions "$lab_root"; then exit 1; fi
DCP_I12_TEST_ARBITER_STATE=stale
dcp_ao_install_assert_no_active_model_actions "$lab_root"
sqlite3 "$database" "UPDATE dcp_review_lab_arbiter_v1_successor_attempt SET launch_id='dcp-arbiter-successor-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';"
if dcp_ao_install_assert_no_active_model_actions "$lab_root"; then exit 1; fi
sqlite3 "$database" "UPDATE dcp_review_lab_arbiter_v1_successor_attempt SET launch_id=attempt_id;"
dcp_ao_install_arbiter_process_state() { return 1; }
if dcp_ao_install_assert_no_active_model_actions "$lab_root"; then exit 1; fi
dcp_ao_install_arbiter_process_state() { printf '%s\n' "$DCP_I12_TEST_ARBITER_STATE"; }
sqlite3 "$database" <<'SQL'
CREATE TABLE dcp_review_lab_card12_fresh_worker_recovery (
  recovery_id TEXT PRIMARY KEY,
  runtime_handle_id TEXT NOT NULL,
  launch_id TEXT NOT NULL,
  status TEXT NOT NULL,
  worker_model_call_count INTEGER NOT NULL,
  authorized_at TEXT NOT NULL
);
INSERT INTO dcp_review_lab_card12_fresh_worker_recovery VALUES (
  'dcp-card12-fresh-worker-recovery-d2b7142bc9e5844ba165abe24d3222b3e1a94c3577fba5f6f8d97ec3dbad151b',
  'dcp-card12-fresh-worker-recovery', '', 'authorized', 0,
  '2026-08-12T00:00:00Z'
);
SQL
dcp_ao_install_assert_no_active_model_actions "$lab_root"
sqlite3 "$database" "UPDATE dcp_review_lab_card12_fresh_worker_recovery SET status='running', worker_model_call_count=1, launch_id=recovery_id;"
DCP_I12_TEST_WORKER_STATE=active
if dcp_ao_install_assert_no_active_model_actions "$lab_root"; then exit 1; fi
DCP_I12_TEST_WORKER_STATE=stale
dcp_ao_install_assert_no_active_model_actions "$lab_root"
sqlite3 "$database" "UPDATE dcp_review_lab_card12_fresh_worker_recovery SET runtime_handle_id='foreign-worker';"
if dcp_ao_install_assert_no_active_model_actions "$lab_root"; then exit 1; fi
sqlite3 "$database" "UPDATE dcp_review_lab_card12_fresh_worker_recovery SET runtime_handle_id='dcp-card12-fresh-worker-recovery';"
dcp_ao_install_worker_process_state() { return 1; }
if dcp_ao_install_assert_no_active_model_actions "$lab_root"; then exit 1; fi
dcp_ao_install_worker_process_state() { printf '%s\n' "$DCP_I12_TEST_WORKER_STATE"; }

# The process proof itself distinguishes a bare preserved shell and an exact
# missing tmux session from any descendant workload. Server/probe ambiguity is
# not downgraded to stale.
source "$REPO_ROOT/lib/dcp-ao-install.sh"
dcp_ao_install_tmux() { printf '100\n'; }
dcp_ao_install_ps() { printf '100 1 /bin/zsh -i\n200 1 /usr/bin/unrelated\n'; }
[[ "$(dcp_ao_install_review_process_state review-worker-1 run-1)" == stale ]]
[[ "$(dcp_ao_install_worker_process_state worker-1 launch-1)" == stale ]]
[[ "$(dcp_ao_install_arbiter_process_state dcp-global-release-arbiter-v1 dcp-global-release-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa)" == stale ]]
[[ "$(dcp_ao_install_arbiter_process_state dcp-global-release-arbiter-v1-successor dcp-arbiter-successor-3c62ea80b56ef94165519d4f01e4c449c320bff22d16b902dd68d4a1a355ea7d)" == stale ]]
[[ "$(dcp_ao_install_worker_process_state dcp-card12-fresh-worker-recovery dcp-card12-fresh-worker-recovery-d2b7142bc9e5844ba165abe24d3222b3e1a94c3577fba5f6f8d97ec3dbad151b)" == stale ]]
dcp_ao_install_ps() { printf '100 1 /bin/zsh -i\n101 100 codex exec --sandbox read-only\n'; }
[[ "$(dcp_ao_install_review_process_state review-worker-1 run-1)" == active ]]
[[ "$(dcp_ao_install_worker_process_state worker-1 launch-1)" == active ]]
[[ "$(dcp_ao_install_arbiter_process_state dcp-global-release-arbiter-v1 dcp-global-release-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa)" == active ]]
[[ "$(dcp_ao_install_arbiter_process_state dcp-global-release-arbiter-v1-successor dcp-arbiter-successor-3c62ea80b56ef94165519d4f01e4c449c320bff22d16b902dd68d4a1a355ea7d)" == active ]]
[[ "$(dcp_ao_install_worker_process_state dcp-card12-fresh-worker-recovery dcp-card12-fresh-worker-recovery-d2b7142bc9e5844ba165abe24d3222b3e1a94c3577fba5f6f8d97ec3dbad151b)" == active ]]
dcp_ao_install_tmux() { printf "can't find session: review-worker-1\n" >&2; return 1; }
[[ "$(dcp_ao_install_review_process_state review-worker-1 run-1)" == stale ]]
dcp_ao_install_tmux() { printf 'no server running on /tmp/tmux.sock\n' >&2; return 1; }
if dcp_ao_install_review_process_state review-worker-1 run-1; then exit 1; fi
if dcp_ao_install_worker_process_state worker-1 launch-1; then exit 1; fi
if dcp_ao_install_arbiter_process_state dcp-global-release-arbiter-v1 dcp-global-release-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa; then exit 1; fi
if dcp_ao_install_worker_process_state dcp-card12-fresh-worker-recovery dcp-card12-fresh-worker-recovery-d2b7142bc9e5844ba165abe24d3222b3e1a94c3577fba5f6f8d97ec3dbad151b; then exit 1; fi

scenario_root() { local root="$TEST_ROOT/$1"; mkdir -p "$root/state/run"; printf '%s\n' "$root"; }
dcp_ao_gateway_status_json() { cat "$1/test-state.json"; }
dcp_ao_gateway_exact_app_pid() {
	local pids count
	pids="$(sed -n '/^[0-9][0-9]*$/p' "$1/test-app-pid" 2>/dev/null || true)"
	count="$(printf '%s\n' "$pids" | awk 'NF{n++} END{print n+0}')"
	[[ "$count" -eq 1 ]] || { [[ "$count" -eq 0 ]] && return 1; return 2; }
	printf '%s\n' "$pids"
}
dcp_ao_gateway_assert_pair() { printf 'pair\n' >>"$1/test-lifecycle.log"; }
dcp_ao_gateway_port_occupied() { [[ -e "$DCP_I12_TEST_ROOT/test-port-occupied" ]]; }
dcp_ao_install_assert_no_active_model_actions() {
	[[ ! -e "$1/test-active" ]] || { dcp_ao_fail 'test active model action'; return 1; }
	printf 'inactive\n' >>"$1/test-lifecycle.log"
}
dcp_ao_install_request_exact_app_quit() { printf 'quit %s\n' "$1" >>"$DCP_I12_TEST_ROOT/test-lifecycle.log"; }
dcp_ao_install_wait_stopped() { printf 'stopped %s %s\n' "$2" "$3" >>"$1/test-lifecycle.log"; }

# One exact ready app/daemon is stopped through the governed path.
DCP_I12_TEST_ROOT="$(scenario_root own-ready)"
printf '41001\n' >"$DCP_I12_TEST_ROOT/test-app-pid"
printf '{\n  "state": "ready"\n}\n' >"$DCP_I12_TEST_ROOT/test-state.json"
printf '{\n  "pid": 41002\n}\n' >"$DCP_I12_TEST_ROOT/state/run/running.json"
dcp_ao_install_prepare_runtime "$DCP_I12_TEST_ROOT" fake-cli
[[ "$(sed -n '1p' "$DCP_I12_TEST_ROOT/test-lifecycle.log")" == pair ]]
grep -Fxq inactive "$DCP_I12_TEST_ROOT/test-lifecycle.log"
grep -Fxq 'quit 41001' "$DCP_I12_TEST_ROOT/test-lifecycle.log"
grep -Fxq 'stopped 41001 41002' "$DCP_I12_TEST_ROOT/test-lifecycle.log"

# Active work, missing app ownership and ambiguous daemon state all fail before
# a quit request. A truly stopped contour remains a no-op.
DCP_I12_TEST_ROOT="$(scenario_root active)"
printf '41001\n' >"$DCP_I12_TEST_ROOT/test-app-pid"
printf '{\n  "state": "ready"\n}\n' >"$DCP_I12_TEST_ROOT/test-state.json"
printf '{\n  "pid": 41002\n}\n' >"$DCP_I12_TEST_ROOT/state/run/running.json"
touch "$DCP_I12_TEST_ROOT/test-active"
if dcp_ao_install_prepare_runtime "$DCP_I12_TEST_ROOT" fake-cli; then exit 1; fi
! grep -q '^quit ' "$DCP_I12_TEST_ROOT/test-lifecycle.log"

DCP_I12_TEST_ROOT="$(scenario_root foreign)"
printf '{\n  "state": "ready"\n}\n' >"$DCP_I12_TEST_ROOT/test-state.json"
if dcp_ao_install_prepare_runtime "$DCP_I12_TEST_ROOT" fake-cli; then exit 1; fi
[[ ! -e "$DCP_I12_TEST_ROOT/test-lifecycle.log" ]]

DCP_I12_TEST_ROOT="$(scenario_root ambiguous)"
printf '{\n  "state": "stale"\n}\n' >"$DCP_I12_TEST_ROOT/test-state.json"
if dcp_ao_install_prepare_runtime "$DCP_I12_TEST_ROOT" fake-cli; then exit 1; fi
[[ ! -e "$DCP_I12_TEST_ROOT/test-lifecycle.log" ]]

DCP_I12_TEST_ROOT="$(scenario_root stopped)"
printf '{\n  "state": "stopped"\n}\n' >"$DCP_I12_TEST_ROOT/test-state.json"
dcp_ao_install_prepare_runtime "$DCP_I12_TEST_ROOT" fake-cli
[[ ! -e "$DCP_I12_TEST_ROOT/test-lifecycle.log" ]]

DCP_I12_TEST_ROOT="$(scenario_root foreign-port)"
printf '{\n  "state": "stopped"\n}\n' >"$DCP_I12_TEST_ROOT/test-state.json"
touch "$DCP_I12_TEST_ROOT/test-port-occupied"
if dcp_ao_install_prepare_runtime "$DCP_I12_TEST_ROOT" fake-cli; then exit 1; fi

printf 'PASS I12 governed install replacement scenarios\n'
