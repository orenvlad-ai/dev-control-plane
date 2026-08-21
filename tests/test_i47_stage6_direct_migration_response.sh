#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
source "$REPO_ROOT/lib/dcp-ao-common.sh"
source "$REPO_ROOT/lib/dcp-ao-stage6-direct-install.sh"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
fake_cli="$tmp/fake-cli"
cat >"$fake_cli" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$DCP_FAKE_MIGRATION_RESPONSE"
EOF
chmod +x "$fake_cli"
dcp_ao_embedded_cli() { printf '%s\n' "$fake_cli"; }
dcp_ao_export_runtime_env() { :; }
mkdir -p "$tmp/backup/migration-probe"

valid='{"dryRun":true,"projectsImported":1,"projectsSkipped":0}'
export DCP_FAKE_MIGRATION_RESPONSE="$valid"
dcp_ao_stage6_direct_migrate /synthetic/lab "$tmp/backup"

assert_rejected() {
	local label="$1" value="$2"
	export DCP_FAKE_MIGRATION_RESPONSE="$value"
	if dcp_ao_stage6_direct_migrate /synthetic/lab "$tmp/backup" >/dev/null 2>&1; then
		printf 'accepted invalid Stage 6 direct migration response: %s\n' "$label" >&2
		exit 1
	fi
}

assert_rejected wrong-type '{"dryRun":"true","projectsImported":1,"projectsSkipped":0}'
assert_rejected unexpected-write '{"dryRun":false,"projectsImported":1,"projectsSkipped":0}'
assert_rejected skipped '{"dryRun":true,"projectsImported":0,"projectsSkipped":1}'
assert_rejected duplicate '{"dryRun":true,"dryRun":true,"projectsImported":1,"projectsSkipped":0}'
assert_rejected wrong-casing '{"DryRun":true,"projectsImported":1,"projectsSkipped":0}'
assert_rejected foreign-extra '{"dryRun":true,"projectsImported":1,"projectsSkipped":0,"written":1}'

printf 'PASS Stage 6 packaged migration strict dry-run response parser\n'
