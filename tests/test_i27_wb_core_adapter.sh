#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
test_root="$(mktemp -d "${TMPDIR:-/tmp}/dcp-ao-i27-test.XXXXXX")"
export DCP_AO_LAB_ROOT="$(cd "$test_root" && pwd -P)"
export DCP_AO_TEST_ALLOW_NONCANONICAL_LAB_ROOT=1
cleanup() {
	local status="$?"
	rm -rf "$DCP_AO_LAB_ROOT"
	return "$status"
}
trap cleanup EXIT

# shellcheck source=../lib/dcp-ao-common.sh
source "$REPO_ROOT/lib/dcp-ao-common.sh"
# shellcheck source=../lib/dcp-ao-gateway.sh
source "$REPO_ROOT/lib/dcp-ao-gateway.sh"
# shellcheck source=../lib/dcp-ao-adapter.sh
source "$REPO_ROOT/lib/dcp-ao-adapter.sh"

target="$DCP_AO_LAB_ROOT/targets/wb-core"
mkdir -p "$target/.github/workflows" "$target/docs/architecture" "$target/apps"
git -C "$target" init -b main >/dev/null
git -C "$target" config user.name 'DCP I27 Test'
git -C "$target" config user.email 'dcp-i27@example.invalid'
git -C "$target" remote add origin https://github.com/orenvlad-ai/wb-core.git
printf 'test authority\n' >"$target/AGENTS.md"
printf 'name: Baseline CI\n' >"$target/.github/workflows/baseline-ci.yml"
printf 'release train contract\n' >"$target/docs/architecture/11_github_release_train.md"
printf '# release train\n' >"$target/apps/github_release_train.py"
printf '# release train spec\n' >"$target/apps/github_release_train_spec.py"
printf '# release train smoke\n' >"$target/apps/github_release_train_smoke.py"
git -C "$target" add .
git -C "$target" commit -m 'Initialize exact wb-core fixture' >/dev/null
git -C "$target" update-ref refs/remotes/origin/main HEAD
mkdir -p "$DCP_AO_LAB_ROOT/data"
sqlite3 "$DCP_AO_LAB_ROOT/data/ao.db" <<'SQL'
CREATE TABLE projects (
	id TEXT PRIMARY KEY,
	path TEXT NOT NULL,
	repo_origin_url TEXT NOT NULL DEFAULT '',
	display_name TEXT NOT NULL DEFAULT '',
	registered_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
	archived_at TIMESTAMP,
	config TEXT,
	kind TEXT NOT NULL DEFAULT 'single_repo'
);
SQL

gh() {
	[[ "$1" == api && "$2" == repos/orenvlad-ai/wb-core ]] || return 1
	if [[ "${DCP_AO_TEST_WB_CORE_DRIFT:-0}" == 1 ]]; then
		printf '%s\n' 'orenvlad-ai/wb-core|true|main|1201929580|237411244'
	else
		printf '%s\n' 'orenvlad-ai/wb-core|false|main|1201929580|237411244'
	fi
}
dcp_ao_refresh_wb_core_target() { :; }

[[ "$(dcp_ao_validate_wb_core_target "$DCP_AO_LAB_ROOT" 1)" == "$target" ]]
[[ -z "$(git -C "$target" status --porcelain)" ]]
[[ "$(dcp_ao_wb_core_compatibility_status "$target")" == blocked ]]
if DCP_AO_TEST_WB_CORE_DRIFT=1 dcp_ao_validate_wb_core_target "$DCP_AO_LAB_ROOT" 0 >/dev/null; then
	printf 'wb-core provider drift was accepted\n' >&2
	exit 1
fi

mutation_log="$DCP_AO_LAB_ROOT/mutation.log"
dcp_ao_resolve_cli() { printf '%s\n' fake-cli; }
dcp_ao_gateway_with_lock() {
	local lab_root="$1" cli="$2" callback="$3"
	shift 3
	"$callback" "$lab_root" "$cli" "$@"
}
dcp_ao_gateway_ensure_locked() { printf 'daemon-start\n' >>"$mutation_log"; }
if dcp_ao_submit --target wb-core --profile repo-only --task-id canary --prompt 'No mutation'; then
	printf 'locked wb-core submit was accepted\n' >&2
	exit 1
fi
[[ ! -e "$mutation_log" ]]

for path in \
	docs/architecture/11_github_release_train.md \
	apps/github_release_train.py \
	apps/github_release_train_spec.py; do
	printf '%s\n' 'wb-core.dcp-release-handoff/v1' >>"$target/$path"
done
git -C "$target" add .
git -C "$target" commit -m 'Add exact compatibility marker fixture' >/dev/null
git -C "$target" update-ref refs/remotes/origin/main HEAD
[[ "$(dcp_ao_wb_core_compatibility_status "$target")" == blocked ]]
stale_config='{"defaultBranch":"main","sessionPrefix":"wb-core","worker":{"agent":"codex","agentConfig":{"permissions":"accept-edits","dcpReviewLabNetwork":true}},"reviewers":[{"harness":"codex"}],"agentRules":"stale adapter rules"}'
sqlite3 "$DCP_AO_LAB_ROOT/data/ao.db" \
	"INSERT INTO projects (id, path, repo_origin_url, config, kind) VALUES ('wb-core', '$target', 'https://github.com/orenvlad-ai/wb-core.git', '$stale_config', 'single_repo');"
[[ "$(dcp_ao_wb_core_compatibility_status "$target")" == blocked ]]
expected_config="$(dcp_ao_wb_core_config_json)"
sqlite3 "$DCP_AO_LAB_ROOT/data/ao.db" \
	"UPDATE projects SET config = '$(printf '%s' "$expected_config" | sed "s/'/''/g")' WHERE id = 'wb-core';"
[[ "$(dcp_ao_wb_core_compatibility_status "$target")" == qualified ]]
native_config="$(printf '%s' "$expected_config" | /usr/bin/jq -c \
	'. + {agentConfig:{}, orchestrator:{agentConfig:{}}, trackerIntake:{}, containerReap:{}}')"
sqlite3 "$DCP_AO_LAB_ROOT/data/ao.db" \
	"UPDATE projects SET config = '$(printf '%s' "$native_config" | sed "s/'/''/g")' WHERE id = 'wb-core';"
[[ "$(dcp_ao_wb_core_compatibility_status "$target")" == qualified ]] || {
	printf 'native empty-default config normalization was rejected\n' >&2
	exit 1
}
for drift_config in \
	"$(printf '%s' "$native_config" | /usr/bin/jq -c '.agentConfig = {unexpected:true}')" \
	"$(printf '%s' "$native_config" | /usr/bin/jq -c '.unknownDefault = {}')"; do
	sqlite3 "$DCP_AO_LAB_ROOT/data/ao.db" \
		"UPDATE projects SET config = '$(printf '%s' "$drift_config" | sed "s/'/''/g")' WHERE id = 'wb-core';"
	[[ "$(dcp_ao_wb_core_compatibility_status "$target")" == blocked ]] || {
		printf 'non-empty or unknown native config drift was accepted\n' >&2
		exit 1
	}
done
sqlite3 "$DCP_AO_LAB_ROOT/data/ao.db" \
	"UPDATE projects SET config = '$(printf '%s' "$native_config" | sed "s/'/''/g")' WHERE id = 'wb-core';"
dcp_ao_require_wb_core_compatibility "$target"

grep -Fq 'only the WBC GitHub Actions Release Train may merge and add release:done' < <(dcp_ao_wb_core_agent_rules)
grep -Fq '"sessionPrefix":"wb-core"' < <(dcp_ao_wb_core_config_json)
rules="$(dcp_ao_wb_core_agent_rules)"
rules_bytes="$(printf '%s' "$rules" | LC_ALL=C wc -c | tr -d '[:space:]')"
rules_sha256="$(printf '%s' "$rules" | dcp_ao_sha256_stream)"
[[ "$rules_bytes" == "$DCP_AO_WB_CORE_POLICY_AGENT_RULES_BYTES" ]] || {
	printf 'wb-core adapter rules bytes drifted from pinned managed source: got=%s want=%s\n' \
		"$rules_bytes" "$DCP_AO_WB_CORE_POLICY_AGENT_RULES_BYTES" >&2
	exit 1
}
[[ "$rules_sha256" == "$DCP_AO_WB_CORE_POLICY_AGENT_RULES_SHA256" ]] || {
	printf 'wb-core adapter rules digest drifted from pinned managed source: got=%s want=%s\n' \
		"$rules_sha256" "$DCP_AO_WB_CORE_POLICY_AGENT_RULES_SHA256" >&2
	exit 1
}
[[ "$(printf '%s' "$(dcp_ao_wb_core_config_json)" | /usr/bin/jq -er '.agentRules')" == "$rules" ]]
source_fixture="$DCP_AO_LAB_ROOT/source-fixture"
mkdir -p "$source_fixture/backend/internal/domain"
printf 'package domain\n\nconst DCPWBCRepoOnlyPolicyAgentRules = "%s"\n' "$rules" \
	>"$source_fixture/backend/internal/domain/dcp_lab_policy.go"
dcp_ao_verify_wb_core_policy_source "$source_fixture"
printf 'package domain\n\nconst DCPWBCRepoOnlyPolicyAgentRules = "%s drift"\n' "$rules" \
	>"$source_fixture/backend/internal/domain/dcp_lab_policy.go"
if dcp_ao_verify_wb_core_policy_source "$source_fixture" >/dev/null 2>&1; then
	printf 'managed-source policy drift was accepted\n' >&2
	exit 1
fi
printf 'PASS I27 wb-core adapter compatibility and pre-mutation lock tests\n'
