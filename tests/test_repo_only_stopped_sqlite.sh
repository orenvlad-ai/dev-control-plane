#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
fixture_root="$(mktemp -d "${TMPDIR:-/tmp}/dcp-repo-only-stopped-sqlite.XXXXXX")"
fixture_root="$(cd "$fixture_root" && pwd -P)"
live_holder_pid=''
cleanup() {
	local status="$?"
	if [[ "$live_holder_pid" =~ ^[1-9][0-9]*$ ]] && kill -0 "$live_holder_pid" 2>/dev/null; then
		kill "$live_holder_pid" 2>/dev/null || true
		wait "$live_holder_pid" 2>/dev/null || true
	fi
	rm -rf "$fixture_root"
	return "$status"
}
trap cleanup EXIT

# shellcheck source=../lib/dcp-ao-common.sh
source "$REPO_ROOT/lib/dcp-ao-common.sh"
# shellcheck source=../lib/dcp-ao-gateway.sh
source "$REPO_ROOT/lib/dcp-ao-gateway.sh"
# shellcheck source=../lib/dcp-ao-adapter.sh
source "$REPO_ROOT/lib/dcp-ao-adapter.sh"

# Linux SQLite can open the copied clean-WAL main file read-only while the
# canonical macOS CLI returns the observed exit 14. Inject that exact primary
# open failure only for fallback cases so every platform exercises the same
# reviewed boundary; live-WAL coverage below disables the injection.
force_readonly_failure=0
sqlite3() {
	if [[ "$force_readonly_failure" == 1 && "${1:-}" == -readonly ]]; then
		return 14
	fi
	command sqlite3 "$@"
}

make_target() {
	local lab_root="$1" target worktree
	target="$lab_root/targets/wb-browser-extension"
	worktree="$lab_root/data/worktrees/wb-browser-extension/wb-browser-extension-1"
	mkdir -p "$target" "$(dirname "$worktree")"
	git -C "$target" init -b main >/dev/null
	git -C "$target" config user.name 'DCP Repo Only Fixture'
	git -C "$target" config user.email 'dcp-repo-only@example.invalid'
	printf 'fixture\n' >"$target/README.md"
	git -C "$target" add README.md
	git -C "$target" commit -m 'Initialize stopped SQLite fixture' >/dev/null
	git -C "$target" worktree add -b ao/wb-browser-extension-1/root "$worktree" main >/dev/null
	printf '%s\n' "$target"
}

make_policy_source() {
	local database="$1" worktree="$2" profile="${3:-repo-only}" duplicate="${4:-0}"
	mkdir -p "$(dirname "$database")"
	sqlite3 "$database" >/dev/null <<SQL
PRAGMA journal_mode=WAL;
CREATE TABLE dcp_review_lab_policy_task (
  session_id TEXT NOT NULL,
  card_number INTEGER NOT NULL,
  worktree_path TEXT NOT NULL,
  source_branch TEXT NOT NULL,
  target TEXT NOT NULL,
  profile TEXT NOT NULL,
  repository TEXT NOT NULL,
  policy_version TEXT NOT NULL
);
INSERT INTO dcp_review_lab_policy_task VALUES (
  'wb-browser-extension-1', 1, '$worktree', 'ao/wb-browser-extension-1/root',
  'wb-browser-extension', '$profile', 'orenvlad-ai/wb-browser-extension',
  'dcp.repo-only.happy-path/v1'
);
SQL
	if [[ "$duplicate" == 1 ]]; then
		sqlite3 "$database" "INSERT INTO dcp_review_lab_policy_task SELECT * FROM dcp_review_lab_policy_task;"
	fi
	sqlite3 "$database" 'PRAGMA wal_checkpoint(TRUNCATE);' >/dev/null
}

install_clean_database() {
	local source="$1" database="$2"
	mkdir -p "$(dirname "$database")"
	cp "$source" "$database"
	[[ ! -e "$database-wal" && ! -e "$database-shm" ]]
}

hash_file() { shasum -a 256 "$1" | awk '{print $1}'; }

make_forwarded_target_with_legacy_worktree() {
	local lab_root="$1" target legacy
	target="$lab_root/targets/wb-browser-extension"
	legacy="$lab_root/data/worktrees/wb-price-extension/wb-price-extension-1"
	mkdir -p "$target" "$lab_root/data/worktrees/wb-price-extension"
	git -C "$target" init -b main >/dev/null
	git -C "$target" config user.name 'DCP Legacy Fixture'
	git -C "$target" config user.email 'dcp-legacy@example.invalid'
	printf 'fixture\n' >"$target/README.md"
	git -C "$target" add README.md
	git -C "$target" commit -m 'Initialize forwarded target fixture' >/dev/null
	git -C "$target" worktree add -b ao/wb-price-extension-1/root "$legacy" main >/dev/null
	printf '%s\n' "$target"
}

make_legacy_policy_source() {
	local database="$1" worktree="$2" state="${3:-merged}" merge_sha="${4:-62853496837f64522bb08ba56169f60f3b0f9a2c}"
	mkdir -p "$(dirname "$database")"
	sqlite3 "$database" >/dev/null <<SQL
PRAGMA journal_mode=WAL;
CREATE TABLE dcp_review_lab_policy_task (
  task_id TEXT, payload_digest TEXT, target TEXT, profile TEXT,
  repository TEXT, policy_version TEXT, session_id TEXT, card_number INTEGER,
  worktree_path TEXT, source_branch TEXT, state TEXT, revision INTEGER,
  repair_count INTEGER, pr_url TEXT, pr_number INTEGER, current_head_sha TEXT,
  previous_head_sha TEXT, review_run_id TEXT, admission_id TEXT,
  merge_commit_sha TEXT, error_code TEXT, incident_packet TEXT
);
INSERT INTO dcp_review_lab_policy_task VALUES (
  'price-arch-v1', 'efe6a81cfff28be89cc327bdc9e2380ca585fcc6b03064c0290b6aaf4c7b59fe',
  'wb-price-extension', 'repo-only', 'orenvlad-ai/wb-price-extension',
  'dcp.repo-only.happy-path/v1', 'wb-price-extension-1', 1,
  '$worktree', 'ao/wb-price-extension-1/root', '$state', 7, 0,
  'https://github.com/orenvlad-ai/wb-price-extension/pull/1', 1,
  'afc748eba5ff05c0dc24d3002c690ec9f44984fb', '',
  'b0acfb9e-600c-4816-bb2f-02a67817ea05',
  'dcp-admission-b0acfb9e-600c-4816-bb2f-02a67817ea05',
  '$merge_sha', '', ''
);
SQL
	sqlite3 "$database" 'PRAGMA wal_checkpoint(TRUNCATE);' >/dev/null
}

legacy_root="$fixture_root/legacy"
legacy_target="$(make_forwarded_target_with_legacy_worktree "$legacy_root")"
legacy_worktree="$legacy_root/data/worktrees/wb-price-extension/wb-price-extension-1"
legacy_source="$fixture_root/legacy-source.db"
legacy_database="$legacy_root/data/ao.db"
make_legacy_policy_source "$legacy_source" "$legacy_worktree"
install_clean_database "$legacy_source" "$legacy_database"
force_readonly_failure=1
dcp_ao_gateway_exact_app_pid() { return 1; }
dcp_ao_gateway_port_occupied() { return 1; }
legacy_before_hash="$(hash_file "$legacy_database")"
dcp_ao_validate_repo_only_worktrees "$legacy_root" "$legacy_target"
[[ "$(hash_file "$legacy_database")" == "$legacy_before_hash" ]]

nonterminal_root="$fixture_root/legacy-nonterminal"
nonterminal_target="$(make_forwarded_target_with_legacy_worktree "$nonterminal_root")"
nonterminal_worktree="$nonterminal_root/data/worktrees/wb-price-extension/wb-price-extension-1"
nonterminal_source="$fixture_root/legacy-nonterminal-source.db"
make_legacy_policy_source "$nonterminal_source" "$nonterminal_worktree" ci_waiting ''
install_clean_database "$nonterminal_source" "$nonterminal_root/data/ao.db"
if dcp_ao_validate_repo_only_worktrees "$nonterminal_root" "$nonterminal_target" >/dev/null; then
	printf 'nonterminal legacy repo-only worktree was accepted\n' >&2
	exit 1
fi

clean_root="$fixture_root/clean"
clean_target="$(make_target "$clean_root")"
clean_worktree="$clean_root/data/worktrees/wb-browser-extension/wb-browser-extension-1"
clean_source="$fixture_root/clean-source.db"
clean_database="$clean_root/data/ao.db"
make_policy_source "$clean_source" "$clean_worktree"
install_clean_database "$clean_source" "$clean_database"

force_readonly_failure=1
if sqlite3 -readonly -batch -noheader "$clean_database" \
	"SELECT count(*) FROM dcp_review_lab_policy_task;" >/dev/null 2>&1; then
	printf 'clean stopped WAL fixture did not reproduce sqlite3 -readonly failure\n' >&2
	exit 1
fi

dcp_ao_gateway_exact_app_pid() { return 1; }
dcp_ao_gateway_port_occupied() { return 1; }
before_hash="$(hash_file "$clean_database")"
dcp_ao_validate_repo_only_worktrees "$clean_root" "$clean_target"
after_hash="$(hash_file "$clean_database")"
[[ "$before_hash" == "$after_hash" ]]
[[ ! -e "$clean_database-wal" && ! -e "$clean_database-shm" ]]

unsafe_root="$fixture_root/unsafe"
unsafe_target="$(make_target "$unsafe_root")"
unsafe_worktree="$unsafe_root/data/worktrees/wb-browser-extension/wb-browser-extension-1"
unsafe_source="$fixture_root/unsafe-source.db"
unsafe_database="$unsafe_root/data/ao.db"
make_policy_source "$unsafe_source" "$unsafe_worktree"
install_clean_database "$unsafe_source" "$unsafe_database"
dcp_ao_gateway_exact_app_pid() { printf '12345\n'; }
if dcp_ao_validate_repo_only_worktrees "$unsafe_root" "$unsafe_target" >/dev/null; then
	printf 'immutable fallback accepted a running exact app\n' >&2
	exit 1
fi
dcp_ao_gateway_exact_app_pid() { return 1; }
dcp_ao_gateway_port_occupied() { return 0; }
if dcp_ao_validate_repo_only_worktrees "$unsafe_root" "$unsafe_target" >/dev/null; then
	printf 'immutable fallback accepted an occupied canonical port\n' >&2
	exit 1
fi
dcp_ao_gateway_port_occupied() { return 1; }
mkdir "$unsafe_database-wal"
if dcp_ao_validate_repo_only_worktrees "$unsafe_root" "$unsafe_target" >/dev/null; then
	printf 'immutable fallback accepted an existing WAL sidecar\n' >&2
	exit 1
fi

mismatch_root="$fixture_root/mismatch"
mismatch_target="$(make_target "$mismatch_root")"
mismatch_worktree="$mismatch_root/data/worktrees/wb-browser-extension/wb-browser-extension-1"
mismatch_source="$fixture_root/mismatch-source.db"
make_policy_source "$mismatch_source" "$mismatch_worktree" synthetic-pr
install_clean_database "$mismatch_source" "$mismatch_root/data/ao.db"
if dcp_ao_validate_repo_only_worktrees "$mismatch_root" "$mismatch_target" >/dev/null; then
	printf 'immutable fallback accepted a mismatched policy row\n' >&2
	exit 1
fi

duplicate_root="$fixture_root/duplicate"
duplicate_target="$(make_target "$duplicate_root")"
duplicate_worktree="$duplicate_root/data/worktrees/wb-browser-extension/wb-browser-extension-1"
duplicate_source="$fixture_root/duplicate-source.db"
make_policy_source "$duplicate_source" "$duplicate_worktree" repo-only 1
install_clean_database "$duplicate_source" "$duplicate_root/data/ao.db"
if dcp_ao_validate_repo_only_worktrees "$duplicate_root" "$duplicate_target" >/dev/null; then
	printf 'immutable fallback accepted duplicate policy authority\n' >&2
	exit 1
fi

live_root="$fixture_root/live"
live_target="$(make_target "$live_root")"
live_worktree="$live_root/data/worktrees/wb-browser-extension/wb-browser-extension-1"
live_database="$live_root/data/ao.db"
make_policy_source "$live_database" "$live_worktree"
force_readonly_failure=0
command sqlite3 "$live_database" >/dev/null <<'SQL' &
PRAGMA journal_mode=WAL;
UPDATE dcp_review_lab_policy_task
SET profile='synthetic-pr'
WHERE session_id='wb-browser-extension-1';
.shell sleep 3
SQL
live_holder_pid="$!"
live_ready=0
for _ in {1..30}; do
	if [[ -e "$live_database-wal" && -e "$live_database-shm" ]] && \
		[[ "$(command sqlite3 -readonly -batch -noheader "$live_database" \
			"SELECT profile FROM dcp_review_lab_policy_task WHERE session_id='wb-browser-extension-1';")" == synthetic-pr ]]; then
		live_ready=1
		break
	fi
	sleep 0.1
done
[[ "$live_ready" == 1 ]]
dcp_ao_gateway_exact_app_pid() { return 2; }
dcp_ao_gateway_port_occupied() { return 0; }
if dcp_ao_validate_repo_only_worktrees "$live_root" "$live_target" >/dev/null; then
	printf 'primary read-only path ignored current live WAL contents\n' >&2
	exit 1
fi
wait "$live_holder_pid"
live_holder_pid=''

corrupt_root="$fixture_root/corrupt"
corrupt_target="$(make_target "$corrupt_root")"
mkdir -p "$corrupt_root/data"
printf 'not sqlite\n' >"$corrupt_root/data/ao.db"
dcp_ao_gateway_exact_app_pid() { return 1; }
dcp_ao_gateway_port_occupied() { return 1; }
if dcp_ao_validate_repo_only_worktrees "$corrupt_root" "$corrupt_target" >/dev/null; then
	printf 'immutable fallback accepted a malformed database\n' >&2
	exit 1
fi

printf 'PASS repo-only stopped SQLite read compatibility\n'
