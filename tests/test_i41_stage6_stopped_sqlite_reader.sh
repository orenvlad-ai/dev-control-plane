#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
source "$REPO_ROOT/lib/dcp-ao-common.sh"
source "$REPO_ROOT/lib/dcp-ao-gateway.sh"
source "$REPO_ROOT/lib/dcp-ao-install.sh"

fixture_root="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "$fixture_root"' EXIT
mkdir -p "$fixture_root/data" "$fixture_root/state/run"
database="$fixture_root/data/ao.db"

sqlite3 "$database" >/dev/null <<'SQL'
CREATE TABLE sessions (
  id TEXT PRIMARY KEY,
  is_terminated INTEGER NOT NULL,
  activity_state TEXT NOT NULL,
  runtime_launch_id TEXT,
  runtime_handle_id TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE review (
  id TEXT PRIMARY KEY,
  reviewer_handle_id TEXT
);
CREATE TABLE review_run (
  id TEXT PRIMARY KEY,
  review_id TEXT NOT NULL,
  status TEXT NOT NULL,
  verdict TEXT NOT NULL,
  created_at TEXT NOT NULL
);
PRAGMA journal_mode=WAL;
SQL

# Force the exact branch exercised by a clean WAL shutdown: the ordinary
# read-only opener failed, so only a proven stopped contour may use immutable.
dcp_ao_install_sqlite_readonly() { return 1; }
dcp_ao_gateway_exact_app_pid() { return 1; }
dcp_ao_gateway_port_occupied() { return 1; }

dcp_ao_install_assert_no_active_model_actions "$fixture_root"

dcp_ao_gateway_exact_app_pid() { printf '123\n'; return 0; }
if dcp_ao_install_assert_no_active_model_actions "$fixture_root" >/dev/null 2>&1; then
	printf 'immutable reader accepted a running app identity\n' >&2
	exit 1
fi
dcp_ao_gateway_exact_app_pid() { return 1; }

printf '{}\n' >"$fixture_root/state/run/running.json"
if dcp_ao_install_assert_no_active_model_actions "$fixture_root" >/dev/null 2>&1; then
	printf 'immutable reader accepted a stopped contour with a run-file\n' >&2
	exit 1
fi
rm "$fixture_root/state/run/running.json"

dcp_ao_gateway_port_occupied() { return 0; }
if dcp_ao_install_assert_no_active_model_actions "$fixture_root" >/dev/null 2>&1; then
	printf 'immutable reader accepted an occupied canonical port\n' >&2
	exit 1
fi
dcp_ao_gateway_port_occupied() { return 1; }

printf 'foreign-sidecar\n' >"$database-wal"
if dcp_ao_install_assert_no_active_model_actions "$fixture_root" >/dev/null 2>&1; then
	printf 'immutable reader accepted a SQLite sidecar\n' >&2
	exit 1
fi
rm "$database-wal"

sqlite3 "$database" \
	"INSERT INTO sessions(id,is_terminated,activity_state,runtime_launch_id,runtime_handle_id,created_at) VALUES('active-worker',0,'active','','','2026-08-21T00:00:00Z');"
if dcp_ao_install_assert_no_active_model_actions "$fixture_root" >/dev/null 2>&1; then
	printf 'stopped reader accepted an active model action\n' >&2
	exit 1
fi

printf 'PASS Stage 6 stopped immutable SQLite reader\n'
