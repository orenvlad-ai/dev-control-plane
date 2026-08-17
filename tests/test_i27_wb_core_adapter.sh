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
[[ "$(dcp_ao_wb_core_compatibility_status "$target")" == qualified ]]
dcp_ao_require_wb_core_compatibility "$target"

grep -Fq 'WBC Release Train is the sole merge and release actor' < <(dcp_ao_wb_core_agent_rules)
grep -Fq '"sessionPrefix":"wb-core"' < <(dcp_ao_wb_core_config_json)
printf 'PASS I27 wb-core adapter compatibility and pre-mutation lock tests\n'
