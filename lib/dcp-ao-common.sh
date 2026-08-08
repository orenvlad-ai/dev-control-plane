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

dcp_ao_codex_state_home() {
	local lab_root="$1"
	printf '%s/runtime/codex-state\n' "$lab_root"
}

dcp_ao_codex_binary() {
	local binary
	binary="$(command -v codex || true)"
	if [[ -z "$binary" || "$binary" != /* || ! -x "$binary" ]]; then dcp_ao_fail 'authenticated Codex CLI is absent from the exact launch PATH'; return 1; fi
	case "$binary" in
		/Applications/*) dcp_ao_fail 'refusing Codex executable from /Applications'; return 1 ;;
	esac
	printf '%s\n' "$binary"
}

dcp_ao_preflight_codex_worker() {
	local lab_root="$1"
	local binary login_status help_status feature_status feature
	binary="$(dcp_ao_codex_binary)" || return 1
	login_status="$(env -u CODEX_HOME "$binary" login status 2>&1)" || { dcp_ao_fail 'Codex worker cannot read the existing standard authentication'; return 1; }
	if [[ "$login_status" != *'Logged in'* ]]; then dcp_ao_fail 'Codex worker is not authenticated'; return 1; fi
	help_status="$(env -u CODEX_HOME "$binary" exec --help 2>&1)" || { dcp_ao_fail 'Codex exec worker surface is unavailable'; return 1; }
	for feature in --ignore-user-config --ephemeral --strict-config; do
		if [[ "$help_status" != *"$feature"* ]]; then dcp_ao_fail "Codex exec worker surface is missing $feature"; return 1; fi
	done
	feature_status="$(env -u CODEX_HOME "$binary" \
		--disable apps --disable hooks --disable multi_agent --disable plugins features list 2>&1)" || {
		dcp_ao_fail 'Codex worker isolation flags are not accepted'
		return 1
	}
	for feature in apps hooks multi_agent plugins; do
		if ! printf '%s\n' "$feature_status" | awk -v name="$feature" '$1 == name && $NF == "false" { found=1 } END { exit(found ? 0 : 1) }'; then
			dcp_ao_fail "Codex worker feature is not fail-closed: $feature"
			return 1
		fi
	done
	if [[ -n "${CODEX_HOME:-}" ]]; then dcp_ao_fail 'CODEX_HOME override would make the worker auth/config contour ambiguous'; return 1; fi
}

dcp_ao_print_contour() {
	local lab_root="$1"
	local cli codex_state binary
	cli="$(dcp_ao_cli_path "$lab_root")"
	codex_state="$(dcp_ao_codex_state_home "$lab_root")"
	binary="$(dcp_ao_codex_binary)" || return 1
	printf 'launcher=%s\n' "$DCP_AO_REPO_ROOT/bin/dcp-ao"
	printf 'source=%s\n' "$(dcp_ao_source_dir "$lab_root")"
	printf 'cli=%s\n' "$cli"
	printf 'AO_DATA_DIR=%s\n' "$lab_root/runtime/data"
	printf 'AO_RUN_FILE=%s\n' "$lab_root/runtime/run/running.json"
	printf 'AO_ELECTRON_USER_DATA_DIR=%s\n' "$lab_root/runtime/electron"
	printf 'CODEX_CONFIG_POLICY=exec--ignore-user-config\n'
	printf 'CODEX_SQLITE_HOME=%s\n' "$codex_state"
	printf 'DCP_AO_CONTOUR_ID=%s\n' "$(dcp_ao_contour_id)"
	printf 'codex=%s\n' "$binary"
	printf 'installed_ao_present=false\n'
}

dcp_ao_preflight_exact_contour() {
	local lab_root="$1"
	local cli
	if [[ -e '/Applications/Agent Orchestrator.app' ]]; then
		dcp_ao_fail 'installed Agent Orchestrator is present; refusing ambiguous application contour'
		return 1
	fi
	dcp_ao_verify_source "$lab_root" || return 1
	cli="$(dcp_ao_cli_path "$lab_root")"
	if [[ ! -x "$cli" ]]; then dcp_ao_fail 'AO source binary is absent; run bin/dcp-ao build first'; return 1; fi
	dcp_ao_export_runtime_env "$lab_root" || return 1
	dcp_ao_preflight_codex_worker "$lab_root" || return 1
	dcp_ao_print_contour "$lab_root"
}

dcp_ao_assert_daemon_contour() {
	local lab_root="$1" status="$2"
	local cli pid process_command process_environment run_file run_pid run_port owner browser_token browser_address ui_instance
	cli="$(dcp_ao_cli_path "$lab_root")"
	if [[ "$status" != *"\"runFile\": \"$lab_root/runtime/run/running.json\""* || \
		"$status" != *"\"dataDir\": \"$lab_root/runtime/data\""* ]]; then
		dcp_ao_fail 'live AO daemon does not report the exact lab runtime paths'
		return 1
	fi
	pid="$(printf '%s\n' "$status" | sed -n 's/^[[:space:]]*"pid": \([0-9][0-9]*\),*$/\1/p')"
	if [[ -z "$pid" ]]; then dcp_ao_fail 'live AO daemon did not report a pid'; return 1; fi
	run_file="$lab_root/runtime/run/running.json"
	if [[ ! -f "$run_file" ]]; then dcp_ao_fail 'live AO daemon has no canonical run-file'; return 1; fi
	run_pid="$(sed -n 's/^[[:space:]]*"pid":[[:space:]]*\([0-9][0-9]*\),*$/\1/p' "$run_file")"
	run_port="$(sed -n 's/^[[:space:]]*"port":[[:space:]]*\([0-9][0-9]*\),*$/\1/p' "$run_file")"
	owner="$(sed -n 's/^[[:space:]]*"owner":[[:space:]]*"\([^"]*\)",*$/\1/p' "$run_file")"
	browser_token="$(sed -n 's/^[[:space:]]*"browserRuntimeToken":[[:space:]]*"\([^"]*\)",*$/\1/p' "$run_file")"
	browser_address="$(sed -n 's/^[[:space:]]*"browserRuntimeAddress":[[:space:]]*"\([^"]*\)",*$/\1/p' "$run_file")"
	ui_instance="$(dcp_ao_ui_instance_id "$lab_root")" || return 1
	if [[ "$run_pid" != "$pid" || "$run_port" != "${DCP_AO_PORT:-43231}" || "$owner" != app || \
		-z "$browser_token" || "$browser_address" != "$lab_root/runtime/run/browser.sock" ]]; then
		dcp_ao_fail 'live AO daemon is not owned by the canonical source-run UI'
		return 1
	fi
	process_command="$(ps -p "$pid" -o command=)"
	case "$process_command" in
		"$cli daemon"*) ;;
		*) dcp_ao_fail 'live AO daemon executable is not the exact source-built CLI'; return 1 ;;
	esac
	process_environment="$(ps eww -p "$pid" -o command=)"
	if [[ "$process_environment" != *"DCP_AO_CODEX_ISOLATION=exec-ignore-user-config"* || \
		"$process_environment" != *"DCP_AO_CONTOUR_ID=$(dcp_ao_contour_id)"* || \
		"$process_environment" != *"DCP_AO_UI_INSTANCE_ID=$ui_instance"* || \
		"$process_environment" != *"AO_OWNER=app"* || \
		"$process_environment" != *"AO_BROWSER_RUNTIME_TOKEN=$browser_token"* || \
		"$process_environment" != *"CODEX_SQLITE_HOME=$lab_root/runtime/codex-state"* || \
		"$process_environment" != *"AO_RUN_FILE=$lab_root/runtime/run/running.json"* || \
		"$process_environment" != *"AO_DATA_DIR=$lab_root/runtime/data"* ]]; then
		dcp_ao_fail 'live AO daemon did not inherit the exact lab worker/runtime environment'
		return 1
	fi
}

dcp_ao_contour_id() {
	printf 'dcp-ao-%s-single-entry-v1\n' "$DCP_AO_UPSTREAM_COMMIT"
}

dcp_ao_ui_instance_id() {
	local lab_root="$1" instance_file instance
	instance_file="$lab_root/runtime/gateway/ui.lock/instance.id"
	if [[ ! -f "$instance_file" ]]; then
		dcp_ao_fail 'canonical source-run UI has no singleton instance identity'
		return 1
	fi
	instance="$(sed -n '1p' "$instance_file")"
	if [[ ! "$instance" =~ ^dcp-ui-[0-9]+-[0-9]+-[0-9]+$ ]]; then
		dcp_ao_fail 'canonical source-run UI singleton identity is malformed'
		return 1
	fi
	printf '%s\n' "$instance"
}

dcp_ao_assert_ui_contour() {
	local lab_root="$1" cli owner instance process_command process_environment
	cli="$(dcp_ao_cli_path "$lab_root")"
	owner="$(sed -n '1p' "$lab_root/runtime/gateway/ui.lock/owner.pid" 2>/dev/null || true)"
	instance="$(dcp_ao_ui_instance_id "$lab_root")" || return 1
	if [[ ! "$owner" =~ ^[0-9]+$ ]] || ! kill -0 "$owner" 2>/dev/null; then
		dcp_ao_fail 'canonical source-run UI singleton owner is not live'
		return 1
	fi
	process_command="$(ps -p "$owner" -o command=)"
	if [[ "$process_command" != *"npm"*"run dev"* ]]; then
		dcp_ao_fail 'canonical source-run UI singleton owner is not the source dev process'
		return 1
	fi
	process_environment="$(ps eww -p "$owner" -o command=)"
	if [[ "$process_environment" != *"DCP_AO_CONTOUR_ID=$(dcp_ao_contour_id)"* || \
		"$process_environment" != *"DCP_AO_UI_INSTANCE_ID=$instance"* || \
		"$process_environment" != *"AO_ELECTRON_USER_DATA_DIR=$lab_root/runtime/electron"* || \
		"$process_environment" != *"DCP_AO_EXPECTED_DAEMON_EXECUTABLE=$cli"* ]]; then
		dcp_ao_fail 'canonical source-run UI did not inherit the exact lab identity'
		return 1
	fi
}

dcp_ao_export_runtime_env() {
	local lab_root="$1" cli
	cli="$(dcp_ao_cli_path "$lab_root")"
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
	unset CODEX_HOME
	export CODEX_SQLITE_HOME="$lab_root/runtime/codex-state"
	export DCP_AO_CODEX_ISOLATION='exec-ignore-user-config'
	export DCP_AO_CONTOUR_ID="$(dcp_ao_contour_id)"
	export DCP_AO_REQUIRE_APP_OWNER='1'
	export DCP_AO_FAIL_CLOSED_DAEMON_REPLACEMENT='1'
	export DCP_AO_EXPECTED_DAEMON_EXECUTABLE="$cli"
	export AO_DAEMON_COMMAND="'$cli' daemon"
	export VITE_DCP_HIDE_MANUAL_ORCHESTRATOR_SPAWN='1'
	mkdir -p "$(dirname "$AO_RUN_FILE")" "$AO_DATA_DIR" "$AO_ELECTRON_USER_DATA_DIR" "$CODEX_SQLITE_HOME"
}
