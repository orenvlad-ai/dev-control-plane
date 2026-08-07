#!/usr/bin/env bash

dcp_ao_fail() {
	printf 'DCP AO: %s\n' "$*" >&2
	return 1
}

dcp_ao_repo_root() {
	cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P
}

DCP_AO_REPO_ROOT="$(dcp_ao_repo_root)"
# shellcheck source=../upstream/agent-orchestrator.lock
source "$DCP_AO_REPO_ROOT/upstream/agent-orchestrator.lock"

dcp_ao_require_lab_root() {
	local requested="${DCP_AO_LAB_ROOT:-}"
	local dcp_user_home="${HOME:?}"
	if [[ -z "$requested" ]]; then dcp_ao_fail 'set DCP_AO_LAB_ROOT to an absolute directory outside Git'; return 1; fi
	if [[ "$requested" != /* ]]; then dcp_ao_fail 'DCP_AO_LAB_ROOT must be absolute'; return 1; fi
	case "$requested/" in
		"$DCP_AO_REPO_ROOT/"*) dcp_ao_fail 'DCP_AO_LAB_ROOT must be outside the DCP checkout'; return 1 ;;
		"$dcp_user_home/.ao/"*) dcp_ao_fail 'DCP_AO_LAB_ROOT must not use installed Agent Orchestrator state'; return 1 ;;
		"/Applications/"*) dcp_ao_fail 'DCP_AO_LAB_ROOT must not use /Applications'; return 1 ;;
	esac
	if [[ "$requested" == / || "$requested" == "$dcp_user_home" ]]; then
		dcp_ao_fail 'DCP_AO_LAB_ROOT must be a dedicated directory, not a broad root'
		return 1
	fi
	mkdir -p "$requested"
	local resolved
	resolved="$(cd "$requested" && pwd -P)"
	case "$resolved/" in
		"$DCP_AO_REPO_ROOT/"*) dcp_ao_fail 'DCP_AO_LAB_ROOT must be outside the DCP checkout'; return 1 ;;
		"$dcp_user_home/.ao/"*) dcp_ao_fail 'DCP_AO_LAB_ROOT must not resolve into installed Agent Orchestrator state'; return 1 ;;
		"/Applications/"*) dcp_ao_fail 'DCP_AO_LAB_ROOT must not resolve into /Applications'; return 1 ;;
	esac
	if [[ "$resolved" == / || "$resolved" == "$dcp_user_home" ]]; then
		dcp_ao_fail 'DCP_AO_LAB_ROOT resolved to a broad root'
		return 1
	fi
	printf '%s\n' "$resolved"
}

dcp_ao_source_dir() {
	local lab_root="$1"
	printf '%s/source/agent-orchestrator-%s-%s\n' \
		"$lab_root" "${DCP_AO_UPSTREAM_TAG#v}" "${DCP_AO_UPSTREAM_COMMIT:0:12}"
}

dcp_ao_patch_path() {
	printf '%s/%s\n' "$DCP_AO_REPO_ROOT" "$DCP_AO_PATCH_FILE"
}

dcp_ao_sha256() {
	shasum -a 256 "$1" | awk '{print $1}'
}

dcp_ao_use_supported_node() {
	if [[ -x /opt/homebrew/opt/node@20/bin/node ]]; then
		export PATH="/opt/homebrew/opt/node@20/bin:$PATH"
	fi
}

dcp_ao_require_tool() {
	if ! command -v "$1" >/dev/null 2>&1; then dcp_ao_fail "required tool not found: $1"; return 1; fi
}

dcp_ao_verify_source() {
	local lab_root="$1"
	local source_dir patch_path actual tmp_diff
	source_dir="$(dcp_ao_source_dir "$lab_root")"
	patch_path="$(dcp_ao_patch_path)"
	if [[ ! -d "$source_dir/.git" ]]; then dcp_ao_fail "managed source is absent; run bin/dcp-ao prepare"; return 1; fi

	actual="$(git -C "$source_dir" remote get-url origin)"
	if [[ "$actual" != "$DCP_AO_UPSTREAM_REPOSITORY" ]]; then dcp_ao_fail "unexpected upstream remote: $actual"; return 1; fi
	actual="$(git -C "$source_dir" rev-parse HEAD)"
	if [[ "$actual" != "$DCP_AO_UPSTREAM_COMMIT" ]]; then dcp_ao_fail "unexpected upstream commit: $actual"; return 1; fi
	actual="$(git -C "$source_dir" rev-parse 'HEAD^{tree}')"
	if [[ "$actual" != "$DCP_AO_UPSTREAM_TREE" ]]; then dcp_ao_fail "unexpected upstream tree: $actual"; return 1; fi
	actual="$(dcp_ao_sha256 "$source_dir/LICENSE")"
	if [[ "$actual" != "$DCP_AO_UPSTREAM_LICENSE_SHA256" ]]; then dcp_ao_fail "unexpected upstream LICENSE digest: $actual"; return 1; fi
	actual="$(dcp_ao_sha256 "$patch_path")"
	if [[ "$actual" != "$DCP_AO_PATCH_SHA256" ]]; then dcp_ao_fail "unexpected DCP patch digest: $actual"; return 1; fi
	if git -C "$source_dir" ls-tree -r --name-only HEAD | awk 'BEGIN{IGNORECASE=1} /(^|\/)NOTICE([^\/]*$)/ {found=1} END{exit found?0:1}'; then
		dcp_ao_fail 'upstream NOTICE result changed; re-audit before continuing'
		return 1
	fi
	if [[ -n "$(git -C "$source_dir" ls-files --others --exclude-standard)" ]]; then dcp_ao_fail 'managed source has unexpected untracked files'; return 1; fi
	if ! git -C "$source_dir" diff --check; then dcp_ao_fail 'managed source patch has whitespace errors'; return 1; fi
	tmp_diff="$(mktemp "${TMPDIR:-/tmp}/dcp-ao-diff.XXXXXX")"
	git -C "$source_dir" diff --binary --full-index --no-ext-diff >"$tmp_diff"
	if ! cmp -s "$tmp_diff" "$patch_path"; then
		rm -f "$tmp_diff"
		dcp_ao_fail 'managed source diff is not the exact DCP patch queue'
		return 1
	fi
	rm -f "$tmp_diff"
}

dcp_ao_prepare_source() {
	local lab_root="$1"
	local source_dir patch_path
	source_dir="$(dcp_ao_source_dir "$lab_root")"
	patch_path="$(dcp_ao_patch_path)"
	dcp_ao_require_tool git
	dcp_ao_require_tool shasum
	dcp_ao_require_tool cmp

	if [[ ! -e "$source_dir" ]]; then
		mkdir -p "$(dirname "$source_dir")"
		git init "$source_dir" >/dev/null
		git -C "$source_dir" remote add origin "$DCP_AO_UPSTREAM_REPOSITORY"
		git -C "$source_dir" fetch --depth=1 origin "refs/tags/$DCP_AO_UPSTREAM_TAG"
		git -C "$source_dir" checkout --detach "$DCP_AO_UPSTREAM_COMMIT" >/dev/null
	fi
	if [[ ! -d "$source_dir/.git" ]]; then dcp_ao_fail "refusing unexpected source path: $source_dir"; return 1; fi
	if [[ "$(git -C "$source_dir" rev-parse HEAD)" != "$DCP_AO_UPSTREAM_COMMIT" ]]; then dcp_ao_fail 'managed source exists at the wrong commit'; return 1; fi
	if [[ "$(git -C "$source_dir" rev-parse 'HEAD^{tree}')" != "$DCP_AO_UPSTREAM_TREE" ]]; then dcp_ao_fail 'managed source tree does not match the lock'; return 1; fi
	if [[ "$(git -C "$source_dir" remote get-url origin)" != "$DCP_AO_UPSTREAM_REPOSITORY" ]]; then dcp_ao_fail 'managed source remote does not match the lock'; return 1; fi
	if [[ -n "$(git -C "$source_dir" ls-files --others --exclude-standard)" ]]; then dcp_ao_fail 'managed source has unexpected untracked files'; return 1; fi

	if git -C "$source_dir" apply --reverse --check "$patch_path" >/dev/null 2>&1; then
		:
	elif git -C "$source_dir" diff --quiet && git -C "$source_dir" apply --check "$patch_path"; then
		git -C "$source_dir" apply "$patch_path"
	else
		dcp_ao_fail 'managed source is neither clean upstream nor the exact DCP patch state'
		return 1
	fi
	dcp_ao_verify_source "$lab_root" || return 1
	printf '%s\n' "$source_dir"
}

dcp_ao_cli_path() {
	local lab_root="$1"
	printf '%s/frontend/daemon/ao\n' "$(dcp_ao_source_dir "$lab_root")"
}

dcp_ao_export_runtime_env() {
	local lab_root="$1"
	export AO_RUN_FILE="$lab_root/runtime/run/running.json"
	export AO_DATA_DIR="$lab_root/runtime/data"
	export AO_PORT="${DCP_AO_PORT:-43231}"
	export AO_AGENT='codex'
	export AO_ELECTRON_USER_DATA_DIR="$lab_root/runtime/electron"
	export AO_TELEMETRY_RENDERER='off'
	export AO_TELEMETRY_EVENTS='off'
	export AO_TELEMETRY_METRICS='off'
	export AO_TELEMETRY_REMOTE='off'
	export AO_TELEMETRY_DISABLED_EVENTS='*'
	export VITE_AO_POSTHOG_KEY=''
	mkdir -p "$(dirname "$AO_RUN_FILE")" "$AO_DATA_DIR" "$AO_ELECTRON_USER_DATA_DIR"
}
