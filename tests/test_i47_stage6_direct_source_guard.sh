#!/usr/bin/env bash
set -euo pipefail
trap 'printf "I47 source-guard fixture failed at line %s\n" "$LINENO" >&2' ERR

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
source "$REPO_ROOT/lib/dcp-ao-common.sh"
source "$REPO_ROOT/lib/dcp-ao-stage6-direct-install.sh"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
tmp="$(cd "$tmp" && pwd -P)"
source_fixture="$tmp/source"
git init --quiet -b main "$source_fixture"
git -C "$source_fixture" config user.name 'DCP fixture'
git -C "$source_fixture" config user.email 'dcp-fixture@example.invalid'
printf 'stable fixture\n' >"$source_fixture/fixture"
git -C "$source_fixture" add fixture
git -C "$source_fixture" commit --quiet -m 'fixture: stable source'
git -C "$source_fixture" remote add origin "$DCP_AO_FORK_REPOSITORY"
DCP_AO_FORK_COMMIT="$(git -C "$source_fixture" rev-parse HEAD)"
DCP_AO_FORK_TREE="$(git -C "$source_fixture" rev-parse 'HEAD^{tree}')"
DCP_AO_TWIN_STAGE6_WORKER_COMMIT="$DCP_AO_FORK_COMMIT"
git -C "$source_fixture" checkout --quiet --detach "$DCP_AO_FORK_COMMIT"
export DCP_AO_TEST_ALLOW_NONCANONICAL_STABLE_SOURCE=1
export DCP_AO_TEST_STABLE_SOURCE_DIR="$source_fixture"
export DCP_AO_TEST_SKIP_SOURCE_CONTENT_GUARDS=1
dcp_ao_verify_source /synthetic/lab

assert_rejected() {
	local label="$1"
	if dcp_ao_verify_source /synthetic/lab >/dev/null 2>&1; then
		printf 'accepted invalid stable source: %s\n' "$label" >&2
		exit 1
	fi
}

git -C "$source_fixture" remote set-url origin https://github.com/example/foreign.git
assert_rejected wrong-remote
git -C "$source_fixture" remote set-url origin "$DCP_AO_FORK_REPOSITORY"
printf 'dirty\n' >"$source_fixture/foreign-untracked"
assert_rejected dirty-tree
rm "$source_fixture/foreign-untracked"
git -C "$source_fixture" switch --quiet -c foreign-head
printf 'foreign\n' >>"$source_fixture/fixture"
git -C "$source_fixture" commit --quiet -am 'fixture: foreign source'
assert_rejected wrong-commit-tree
git -C "$source_fixture" checkout --quiet --detach "$DCP_AO_FORK_COMMIT"

alias_fixture="$tmp/source-link"
ln -s "$source_fixture" "$alias_fixture"
export DCP_AO_TEST_STABLE_SOURCE_DIR="$alias_fixture"
assert_rejected symlink
export DCP_AO_TEST_STABLE_SOURCE_DIR="$source_fixture"

mv "$source_fixture" "$tmp/disappeared"
assert_rejected disappearance-before-staging
mv "$tmp/disappeared" "$source_fixture"
dcp_ao_verify_source /synthetic/lab

lab="$tmp/lab"
mkdir -p "$lab/build/backups/prior-attempt"
printf 'install_identity=%s\n' "$DCP_AO_TWIN_STAGE6_DIRECT_INSTALL_ID" >"$lab/build/backups/prior-attempt/manifest"
[[ "$(dcp_ao_stage6_direct_find_attempt "$lab")" == "$lab/build/backups/prior-attempt" ]]

backup="$tmp/backup"
mkdir -p "$backup/staged/DCP Orchestrator.app/Contents/Resources/daemon"
printf 'daemon\n' >"$backup/staged/DCP Orchestrator.app/Contents/Resources/daemon/dcp-orchestratord"
printf 'asar\n' >"$backup/staged/DCP Orchestrator.app/Contents/Resources/app.asar"
git -C "$source_fixture" archive --format=tar "$DCP_AO_FORK_COMMIT" >"$backup/source.tar"
git -C "$source_fixture" archive --format=tar "$DCP_AO_FORK_COMMIT" >"$backup/worker-output.tar"
printf 'artifact\n' >"$backup/direct-model-arm64.zip"
dcp_ao_verify_bundle_at() { :; }
{
	printf 'schema=1\ninstall_identity=%s\nsource_commit=%s\nsource_tree=%s\nsource_remote=%s\n' \
		"$DCP_AO_TWIN_STAGE6_DIRECT_INSTALL_ID" "$DCP_AO_FORK_COMMIT" "$DCP_AO_FORK_TREE" "$DCP_AO_FORK_REPOSITORY"
	printf 'source_archive_sha256=%s\n' "$(dcp_ao_sha256 "$backup/source.tar")"
	printf 'worker_archive_sha256=%s\n' "$(dcp_ao_sha256 "$backup/worker-output.tar")"
	printf 'artifact_archive_sha256=%s\n' "$(dcp_ao_sha256 "$backup/direct-model-arm64.zip")"
	printf 'staged_daemon_sha256=%s\n' "$(dcp_ao_sha256 "$backup/staged/DCP Orchestrator.app/Contents/Resources/daemon/dcp-orchestratord")"
	printf 'staged_asar_sha256=%s\n' "$(dcp_ao_sha256 "$backup/staged/DCP Orchestrator.app/Contents/Resources/app.asar")"
} >"$backup/manifest"
dcp_ao_stage6_direct_verify_staged "$backup"
dcp_ao_stage6_direct_verify_install_copy "$backup" "$backup/staged/DCP Orchestrator.app"
printf 'tamper-copy\n' >>"$backup/staged/DCP Orchestrator.app/Contents/Resources/daemon/dcp-orchestratord"
if dcp_ao_stage6_direct_verify_install_copy "$backup" "$backup/staged/DCP Orchestrator.app" >/dev/null 2>&1; then
	printf 'accepted copied daemon digest mismatch\n' >&2
	exit 1
fi
printf 'daemon\n' >"$backup/staged/DCP Orchestrator.app/Contents/Resources/daemon/dcp-orchestratord"
printf 'tamper\n' >>"$backup/direct-model-arm64.zip"
if dcp_ao_stage6_direct_verify_staged "$backup" >/dev/null 2>&1; then
	printf 'accepted staged artifact digest mismatch\n' >&2
	exit 1
fi

prior_backup="$tmp/prior-backup"
mkdir -p "$prior_backup/prior/data" "$prior_backup/prior/state" \
	"$prior_backup/prior/DCP Orchestrator.app/Contents/Resources/daemon"
printf 'database\n' >"$prior_backup/prior/data/ao.db"
printf 'shm\n' >"$prior_backup/prior/data/ao.db-shm"
printf 'receipt\n' >"$prior_backup/prior/state/install.receipt"
printf 'allowlist\n' >"$prior_backup/prior/state/lab-allowlist.json"
printf 'plist\n' >"$prior_backup/prior/DCP Orchestrator.app/Contents/Info.plist"
printf 'daemon\n' >"$prior_backup/prior/DCP Orchestrator.app/Contents/Resources/daemon/dcp-orchestratord"
printf 'asar\n' >"$prior_backup/prior/DCP Orchestrator.app/Contents/Resources/app.asar"
: >"$prior_backup/manifest"
DCP_AO_TWIN_STAGE6_AGGREGATE_RECEIPT_SHA256="$(dcp_ao_sha256 "$prior_backup/prior/state/install.receipt")"
dcp_ao_stage6_direct_record_prior_backup "$prior_backup"
grep -Fxq 'prior_database_state=present' "$prior_backup/manifest"
grep -Fxq 'prior_database_wal_state=absent' "$prior_backup/manifest"
grep -Fxq 'prior_database_shm_state=present' "$prior_backup/manifest"
grep -Fxq 'prior_allowlist_state=present' "$prior_backup/manifest"

unset DCP_AO_TEST_ALLOW_NONCANONICAL_STABLE_SOURCE DCP_AO_TEST_STABLE_SOURCE_DIR DCP_AO_TEST_SKIP_SOURCE_CONTENT_GUARDS
HOME="$tmp/home"; export HOME
mkdir -p "$HOME/.codex/worktrees/task/dcp-orchestrator/.git"
if dcp_ao_verify_source /synthetic/lab >/dev/null 2>&1; then
	printf 'accepted ephemeral source path\n' >&2
	exit 1
fi

printf 'PASS Stage 6 stable standalone source and staged digest guards\n'
