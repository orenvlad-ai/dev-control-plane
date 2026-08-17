#!/usr/bin/env bash

dcp_ao_fail() {
	printf 'DCP AO: %s\n' "$*" >&2
	return 1
}

dcp_ao_repo_root() {
	cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P
}

DCP_AO_REPO_ROOT="$(dcp_ao_repo_root)"
# shellcheck source=../upstream/dcp-orchestrator.lock
source "$DCP_AO_REPO_ROOT/upstream/dcp-orchestrator.lock"

dcp_ao_canonical_lab_root() {
	printf '%s/Library/Application Support/DCP Orchestrator\n' "${HOME:?}"
}

dcp_ao_app_path() {
	printf '%s/Applications/DCP Orchestrator.app\n' "${HOME:?}"
}

dcp_ao_app_executable() {
	printf '%s/Contents/MacOS/dcp-orchestrator\n' "$(dcp_ao_app_path)"
}

dcp_ao_embedded_cli() {
	printf '%s/Contents/Resources/daemon/dcp-orchestratord\n' "$(dcp_ao_app_path)"
}

dcp_ao_run_file() { printf '%s/state/run/running.json\n' "$1"; }
dcp_ao_data_dir() { printf '%s/data\n' "$1"; }
dcp_ao_codex_state_home() { printf '%s/data/codex-state\n' "$1"; }
dcp_ao_install_receipt() { printf '%s/state/install.receipt\n' "$1"; }

dcp_ao_require_lab_root() {
	local requested="${DCP_AO_LAB_ROOT:-}" canonical dcp_user_home="${HOME:?}" resolved
	canonical="$(dcp_ao_canonical_lab_root)"
	if [[ -z "$requested" ]]; then dcp_ao_fail "set DCP_AO_LAB_ROOT to $canonical"; return 1; fi
	if [[ "$requested" != /* ]]; then dcp_ao_fail 'DCP_AO_LAB_ROOT must be absolute'; return 1; fi
	case "$requested/" in
		"$DCP_AO_REPO_ROOT/"*|"$dcp_user_home/.ao/"*|"/Applications/"*)
			dcp_ao_fail 'DCP_AO_LAB_ROOT crosses a forbidden source/state boundary'; return 1 ;;
	esac
	if [[ "$requested" == / || "$requested" == "$dcp_user_home" ]]; then
		dcp_ao_fail 'DCP_AO_LAB_ROOT must be a dedicated directory'; return 1
	fi
	if [[ "${DCP_AO_TEST_ALLOW_NONCANONICAL_LAB_ROOT:-0}" != 1 && "$requested" != "$canonical" ]]; then
		dcp_ao_fail "packaged DCP Lab root must be exactly $canonical"; return 1
	fi
	mkdir -p "$requested"
	resolved="$(cd "$requested" && pwd -P)"
	if [[ "${DCP_AO_TEST_ALLOW_NONCANONICAL_LAB_ROOT:-0}" != 1 && "$resolved" != "$canonical" ]]; then
		dcp_ao_fail 'DCP_AO_LAB_ROOT resolves outside the canonical DCP namespace'; return 1
	fi
	printf '%s\n' "$resolved"
}

dcp_ao_source_dir() {
	printf '%s/source/dcp-orchestrator-%s\n' "$1" "${DCP_AO_FORK_COMMIT:0:12}"
}

dcp_ao_sha256() { shasum -a 256 "$1" | awk '{print $1}'; }
dcp_ao_sha256_stream() { shasum -a 256 | awk '{print $1}'; }

dcp_ao_verify_wb_core_policy_source() {
	local source_dir="$1" policy_file prefix line rules bytes digest
	policy_file="$source_dir/backend/internal/domain/dcp_lab_policy.go"
	prefix='const DCPWBCRepoOnlyPolicyAgentRules = "'
	[[ -f "$policy_file" && "$(grep -Fc "$prefix" "$policy_file")" == 1 ]] || {
		dcp_ao_fail 'managed source wb-core policy rules declaration is absent or ambiguous'; return 1;
	}
	line="$(grep -F "$prefix" "$policy_file")"
	case "$line" in "$prefix"*\") ;; *) dcp_ao_fail 'managed source wb-core policy rules declaration is malformed'; return 1 ;; esac
	rules="${line#"$prefix"}"
	rules="${rules%\"}"
	[[ "$rules" != *\\* ]] || {
		dcp_ao_fail 'managed source wb-core policy rules require unsupported Go string unescaping'; return 1;
	}
	bytes="$(printf '%s' "$rules" | LC_ALL=C wc -c | tr -d '[:space:]')"
	digest="$(printf '%s' "$rules" | dcp_ao_sha256_stream)"
	[[ "$bytes" == "$DCP_AO_WB_CORE_POLICY_AGENT_RULES_BYTES" && \
		"$digest" == "$DCP_AO_WB_CORE_POLICY_AGENT_RULES_SHA256" ]] || {
		dcp_ao_fail 'managed source wb-core policy rules drifted from the immutable source lock'; return 1;
	}
}

dcp_ao_verify_wbc_ci_lifecycle_source() {
	local source_dir="$1" migration
	migration="$source_dir/backend/internal/storage/sqlite/migrations/0079_dcp_wbc_ci_truth_recovery_v1.sql"
	for path in \
		backend/internal/domain/dcp_lab_policy.go \
		backend/internal/service/dcptask/policy.go \
		backend/internal/dcpterminalmerge/merge.go \
		backend/internal/domain/session.go \
		backend/internal/lifecycle/reactions.go \
		frontend/src/renderer/lib/session-presentation.ts \
		"${migration#"$source_dir/"}"; do
		[[ -s "$source_dir/$path" ]] || {
			dcp_ao_fail "managed source WBC CI/lifecycle authority is absent: $path"; return 1;
		}
	done
	grep -Fq 'func EvaluateDCPRequiredCheck' "$source_dir/backend/internal/domain/dcp_lab_policy.go" || return 1
	grep -Fq 'domain.EvaluateDCPRequiredCheck' "$source_dir/backend/internal/service/dcptask/policy.go" || return 1
	grep -Fq 'domain.EvaluateDCPRequiredCheck' "$source_dir/backend/internal/dcpterminalmerge/merge.go" || return 1
	grep -Fq 'candidate.spec.UsesWBCReleaseTrain()' "$source_dir/backend/internal/dcpterminalmerge/merge.go" || return 1
	grep -Fq 'DCPPolicyModelActive' "$source_dir/backend/internal/domain/session.go" || return 1
	grep -Fq 'DCPPolicyWorkflowActive' "$source_dir/backend/internal/domain/session.go" || return 1
	grep -Fq 'ReadyDestination = "wbc_release_train"' "$source_dir/backend/internal/lifecycle/reactions.go" || return 1
	grep -Fq 'workflowActive' "$source_dir/frontend/src/renderer/lib/session-presentation.ts" || return 1
	grep -Fq "contract_commit = '$DCP_AO_WBC_CI_TRUTH_CONTRACT_COMMIT'" "$migration" || return 1
	grep -Fq "task_id = 'wbc-canary-v1'" "$migration" || return 1
	grep -Fq 'worker.sequence = 71' "$migration" || return 1
	grep -Fq "reviewer_action_id = 'dcp-model-wbc-canary-v1-review-1'" "$migration" || return 1
}

dcp_ao_use_supported_node() {
	if [[ -x /opt/homebrew/opt/node@20/bin/node ]]; then export PATH="/opt/homebrew/opt/node@20/bin:$PATH"; fi
}

dcp_ao_require_tool() {
	command -v "$1" >/dev/null 2>&1 || dcp_ao_fail "required tool not found: $1"
}

dcp_ao_verify_source() {
	local lab_root="$1" source_dir actual parity_digest
	source_dir="$(dcp_ao_source_dir "$lab_root")"
	[[ -d "$source_dir/.git" ]] || { dcp_ao_fail 'managed source is absent; run bin/dcp-ao prepare'; return 1; }
	actual="$(git -C "$source_dir" remote get-url origin)"
	[[ "$actual" == "$DCP_AO_FORK_REPOSITORY" ]] || { dcp_ao_fail "unexpected managed fork remote: $actual"; return 1; }
	actual="$(git -C "$source_dir" remote get-url upstream)"
	[[ "$actual" == "$DCP_AO_UPSTREAM_REPOSITORY" ]] || { dcp_ao_fail "unexpected read-only upstream remote: $actual"; return 1; }
	actual="$(git -C "$source_dir" remote get-url --push upstream)"
	[[ "$actual" == DISABLED ]] || { dcp_ao_fail 'upstream remote is not push-disabled'; return 1; }
	actual="$(git -C "$source_dir" rev-parse HEAD)"
	[[ "$actual" == "$DCP_AO_FORK_COMMIT" ]] || { dcp_ao_fail "unexpected managed fork commit: $actual"; return 1; }
	actual="$(git -C "$source_dir" rev-parse 'HEAD^{tree}')"
	[[ "$actual" == "$DCP_AO_FORK_TREE" ]] || { dcp_ao_fail "unexpected managed fork tree: $actual"; return 1; }
	[[ "$(git -C "$source_dir" rev-parse "$DCP_AO_UPSTREAM_COMMIT^{tree}")" == "$DCP_AO_UPSTREAM_TREE" ]] || { dcp_ao_fail 'upstream provenance tree mismatch'; return 1; }
	git -C "$source_dir" merge-base --is-ancestor "$DCP_AO_UPSTREAM_COMMIT" "$DCP_AO_I8_PARITY_COMMIT" || { dcp_ao_fail 'I8 parity anchor does not descend from upstream'; return 1; }
	git -C "$source_dir" merge-base --is-ancestor "$DCP_AO_I8_PARITY_COMMIT" "$DCP_AO_FORK_COMMIT" || { dcp_ao_fail 'fork commit does not descend from I8 parity'; return 1; }
	parity_digest="$(git -C "$source_dir" diff "$DCP_AO_UPSTREAM_COMMIT" "$DCP_AO_I8_PARITY_COMMIT" --binary --full-index --no-ext-diff | dcp_ao_sha256_stream)"
	[[ "$parity_digest" == "$DCP_AO_I8_PARITY_DIFF_SHA256" ]] || { dcp_ao_fail 'I8 parity diff digest mismatch'; return 1; }
	actual="$(dcp_ao_sha256 "$source_dir/LICENSE")"
	[[ "$actual" == "$DCP_AO_FORK_LICENSE_SHA256" ]] || { dcp_ao_fail 'fork LICENSE digest mismatch'; return 1; }
	actual="$(dcp_ao_sha256 "$source_dir/NOTICE")"
	[[ "$actual" == "$DCP_AO_FORK_NOTICE_SHA256" ]] || { dcp_ao_fail 'fork NOTICE digest mismatch'; return 1; }
	actual="$(dcp_ao_sha256 "$source_dir/DCP_PROVENANCE.md")"
	[[ "$actual" == "$DCP_AO_FORK_PROVENANCE_SHA256" ]] || { dcp_ao_fail 'fork provenance digest mismatch'; return 1; }
	dcp_ao_verify_wb_core_policy_source "$source_dir" || return 1
	dcp_ao_verify_wbc_ci_lifecycle_source "$source_dir" || return 1
	if git -C "$source_dir" ls-tree -r --name-only "$DCP_AO_UPSTREAM_COMMIT" | awk 'BEGIN{IGNORECASE=1} /(^|\/)NOTICE([^\/]*$)/ {found=1} END{exit found?0:1}'; then
		dcp_ao_fail 'upstream NOTICE result changed; re-audit required'; return 1
	fi
	[[ -z "$(git -C "$source_dir" ls-files --others --exclude-standard)" ]] || { dcp_ao_fail 'managed source has unexpected untracked files'; return 1; }
	git -C "$source_dir" diff --quiet || { dcp_ao_fail 'managed fork source has unstaged changes'; return 1; }
	git -C "$source_dir" diff --cached --quiet || { dcp_ao_fail 'managed fork source has staged changes'; return 1; }
	git -C "$source_dir" diff --check || { dcp_ao_fail 'managed fork source has whitespace errors'; return 1; }
}

dcp_ao_prepare_source() {
	local lab_root="$1" source_dir attempt fetch_mode
	source_dir="$(dcp_ao_source_dir "$lab_root")"
	for tool in git shasum; do dcp_ao_require_tool "$tool" || return 1; done
	if [[ ! -e "$source_dir" ]]; then
		mkdir -p "$(dirname "$source_dir")"
		git init "$source_dir" >/dev/null
		git -C "$source_dir" remote add origin "$DCP_AO_FORK_REPOSITORY"
		git -C "$source_dir" remote add upstream "$DCP_AO_UPSTREAM_REPOSITORY"
		git -C "$source_dir" remote set-url --add --push upstream DISABLED
		for attempt in 1 2 3; do
			if git -C "$source_dir" fetch --no-tags origin "$DCP_AO_FORK_COMMIT"; then break; fi
			[[ "$attempt" -lt 3 ]] || { dcp_ao_fail 'managed fork fetch failed after three attempts'; return 1; }
			sleep "$attempt"
		done
		git -C "$source_dir" checkout --detach "$DCP_AO_FORK_COMMIT" >/dev/null
	fi
	[[ -d "$source_dir/.git" ]] || { dcp_ao_fail "refusing unexpected source path: $source_dir"; return 1; }
	if [[ "$(git -C "$source_dir" rev-parse --is-shallow-repository)" == true ]]; then
		fetch_mode=--unshallow
		for attempt in 1 2 3; do
			if git -C "$source_dir" fetch --no-tags "$fetch_mode" origin "$DCP_AO_FORK_COMMIT"; then break; fi
			[[ "$attempt" -lt 3 ]] || { dcp_ao_fail 'managed fork history fetch failed after three attempts'; return 1; }
			sleep "$attempt"
		done
	fi
	[[ "$(git -C "$source_dir" rev-parse HEAD)" == "$DCP_AO_FORK_COMMIT" ]] || { dcp_ao_fail 'managed source is at the wrong fork commit'; return 1; }
	[[ "$(git -C "$source_dir" rev-parse 'HEAD^{tree}')" == "$DCP_AO_FORK_TREE" ]] || { dcp_ao_fail 'managed source tree differs from fork lock'; return 1; }
	dcp_ao_verify_source "$lab_root" || return 1
	printf '%s\n' "$source_dir"
}

dcp_ao_package_output() {
	printf '%s/frontend/out/DCP Orchestrator-darwin-arm64/DCP Orchestrator.app\n' "$(dcp_ao_source_dir "$1")"
}

dcp_ao_contour_id() { printf 'dcp-ao-%s-packaged-v1\n' "$DCP_AO_UPSTREAM_COMMIT"; }

dcp_ao_verify_bundle_contents_at() {
	local app="$1" require_fork_metadata="$2" plist executable daemon arch bundle_id bundle_name
	plist="$app/Contents/Info.plist"; executable="$app/Contents/MacOS/dcp-orchestrator"; daemon="$app/Contents/Resources/daemon/dcp-orchestratord"
	[[ -d "$app" && -f "$plist" && -x "$executable" && -x "$daemon" ]] || { dcp_ao_fail "incomplete DCP app bundle: $app"; return 1; }
	bundle_id="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$plist")"
	bundle_name="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleName' "$plist")"
	[[ "$bundle_id" == pro.devcontrol.dcp-orchestrator && "$bundle_name" == 'DCP Orchestrator' ]] || { dcp_ao_fail 'app bundle identity mismatch'; return 1; }
	[[ "$(/usr/libexec/PlistBuddy -c 'Print :CFBundleExecutable' "$plist")" == dcp-orchestrator ]] || { dcp_ao_fail 'app executable namespace mismatch'; return 1; }
	[[ "$(/usr/libexec/PlistBuddy -c 'Print :DCPUpstreamCommit' "$plist")" == "$DCP_AO_UPSTREAM_COMMIT" ]] || { dcp_ao_fail 'bundle upstream identity mismatch'; return 1; }
	[[ "$(/usr/libexec/PlistBuddy -c 'Print :DCPContour' "$plist")" == dcp-i8-packaged-app-v1 ]] || { dcp_ao_fail 'bundle contour identity mismatch'; return 1; }
	arch="$(lipo -archs "$executable")"; [[ "$arch" == arm64 ]] || { dcp_ao_fail "main executable is not exact arm64: $arch"; return 1; }
	arch="$(lipo -archs "$daemon")"; [[ "$arch" == arm64 ]] || { dcp_ao_fail "daemon is not exact arm64: $arch"; return 1; }
	[[ -f "$app/Contents/Resources/LICENSE" ]] || { dcp_ao_fail 'fork license is absent from bundle'; return 1; }
	[[ "$(dcp_ao_sha256 "$app/Contents/Resources/LICENSE")" == "$DCP_AO_FORK_LICENSE_SHA256" ]] || { dcp_ao_fail 'bundled LICENSE mismatch'; return 1; }
	if [[ "$require_fork_metadata" == 1 ]]; then
		[[ -f "$app/Contents/Resources/NOTICE" ]] || { dcp_ao_fail 'fork NOTICE is absent from bundle'; return 1; }
		[[ -f "$app/Contents/Resources/DCP_PROVENANCE.md" ]] || { dcp_ao_fail 'fork provenance is absent from bundle'; return 1; }
		[[ "$(dcp_ao_sha256 "$app/Contents/Resources/NOTICE")" == "$DCP_AO_FORK_NOTICE_SHA256" ]] || { dcp_ao_fail 'bundled NOTICE mismatch'; return 1; }
		[[ "$(dcp_ao_sha256 "$app/Contents/Resources/DCP_PROVENANCE.md")" == "$DCP_AO_FORK_PROVENANCE_SHA256" ]] || { dcp_ao_fail 'bundled provenance mismatch'; return 1; }
	fi
	[[ ! -e "$app/Contents/Resources/app-update.yml" ]] || { dcp_ao_fail 'forbidden updater feed is packaged'; return 1; }
	if find "$app" \( -iname '*electron-updater*' -o -iname '*posthog*' -o -iname '*sentry*' \) -print -quit | grep -q .; then dcp_ao_fail 'forbidden updater/telemetry/crash package is bundled'; return 1; fi
	if strings "$app/Contents/Resources/app.asar" | grep -Eiq 'us(-assets)?\.i\.posthog\.com|eu\.i\.posthog\.com|phc_[[:alnum:]]+|electron-updater|app-update\.yml|sentry\.io|crashReporter[[:space:]]*\.[[:space:]]*(start|submit)'; then
		dcp_ao_fail 'forbidden update/analytics/crash endpoint or key is present in app.asar'; return 1
	fi
	if strings "$daemon" | grep -Eiq 'us\.i\.posthog\.com|eu\.i\.posthog\.com|phc_[[:alnum:]]+|sentry\.io'; then
		dcp_ao_fail 'forbidden analytics endpoint or key is present in daemon'; return 1
	fi
	codesign --verify --deep --strict "$app" >/dev/null 2>&1 || { dcp_ao_fail 'bundle signature verification failed'; return 1; }
}

dcp_ao_verify_bundle_at() { dcp_ao_verify_bundle_contents_at "$1" 1; }

# A replacement may back up a previously qualified DCP bundle. Older I8
# bundles predate the fork NOTICE/provenance resources but retain the same
# runtime identity and absence gates. They are accepted only as replaceable
# prior bundles, never as the newly installed artifact.
dcp_ao_verify_replaceable_bundle_at() { dcp_ao_verify_bundle_contents_at "$1" 0; }

dcp_ao_verify_install_receipt() {
	local lab_root="$1" receipt app daemon asar
	receipt="$(dcp_ao_install_receipt "$lab_root")"; app="$(dcp_ao_app_path)"; daemon="$(dcp_ao_embedded_cli)"; asar="$app/Contents/Resources/app.asar"
	[[ -f "$receipt" && -f "$asar" ]] || { dcp_ao_fail 'canonical install receipt is absent'; return 1; }
	grep -Fxq "bundle_path=$app" "$receipt" || { dcp_ao_fail 'receipt bundle path mismatch'; return 1; }
	grep -Fxq 'bundle_id=pro.devcontrol.dcp-orchestrator' "$receipt" || { dcp_ao_fail 'receipt bundle id mismatch'; return 1; }
	grep -Fxq "fork_commit=$DCP_AO_FORK_COMMIT" "$receipt" || { dcp_ao_fail 'receipt fork mismatch'; return 1; }
	grep -Fxq "fork_tree=$DCP_AO_FORK_TREE" "$receipt" || { dcp_ao_fail 'receipt fork tree mismatch'; return 1; }
	grep -Fxq "upstream_commit=$DCP_AO_UPSTREAM_COMMIT" "$receipt" || { dcp_ao_fail 'receipt upstream mismatch'; return 1; }
	grep -Fxq "i8_parity_diff_sha256=$DCP_AO_I8_PARITY_DIFF_SHA256" "$receipt" || { dcp_ao_fail 'receipt I8 parity mismatch'; return 1; }
	grep -Fxq "daemon_sha256=$(dcp_ao_sha256 "$daemon")" "$receipt" || { dcp_ao_fail 'receipt daemon digest mismatch'; return 1; }
	grep -Fxq "asar_sha256=$(dcp_ao_sha256 "$asar")" "$receipt" || { dcp_ao_fail 'receipt app digest mismatch'; return 1; }
}

dcp_ao_verify_replaceable_install_receipt() {
	local lab_root="$1" receipt app daemon asar
	receipt="$(dcp_ao_install_receipt "$lab_root")"; app="$(dcp_ao_app_path)"; daemon="$(dcp_ao_embedded_cli)"; asar="$app/Contents/Resources/app.asar"
	[[ -f "$receipt" && -f "$asar" ]] || { dcp_ao_fail 'prior install receipt is absent'; return 1; }
	if grep -Fxq "fork_commit=$DCP_AO_FORK_COMMIT" "$receipt"; then
		dcp_ao_verify_install_receipt "$lab_root"
		return
	fi
	grep -Fxq "bundle_path=$app" "$receipt" || { dcp_ao_fail 'prior receipt bundle path mismatch'; return 1; }
	grep -Fxq 'bundle_id=pro.devcontrol.dcp-orchestrator' "$receipt" || { dcp_ao_fail 'prior receipt bundle id mismatch'; return 1; }
	grep -Fxq "upstream_commit=$DCP_AO_UPSTREAM_COMMIT" "$receipt" || { dcp_ao_fail 'prior receipt upstream mismatch'; return 1; }
	if grep -Fxq "fork_commit=$DCP_AO_PRIOR_FORK_COMMIT" "$receipt"; then
		grep -Fxq "fork_tree=$DCP_AO_PRIOR_FORK_TREE" "$receipt" || { dcp_ao_fail 'prior receipt fork tree mismatch'; return 1; }
		grep -Fxq "i8_parity_diff_sha256=$DCP_AO_I8_PARITY_DIFF_SHA256" "$receipt" || { dcp_ao_fail 'prior receipt I8 parity mismatch'; return 1; }
	elif grep -Eq '^fork_(commit|tree)=' "$receipt"; then
		dcp_ao_fail 'prior receipt names an unapproved managed fork'; return 1
	else
		grep -Fxq "patch_sha256=$DCP_AO_I8_PARITY_DIFF_SHA256" "$receipt" || { dcp_ao_fail 'prior receipt I8 parity mismatch'; return 1; }
	fi
	grep -Fxq "daemon_sha256=$(dcp_ao_sha256 "$daemon")" "$receipt" || { dcp_ao_fail 'prior receipt daemon digest mismatch'; return 1; }
	grep -Fxq "asar_sha256=$(dcp_ao_sha256 "$asar")" "$receipt" || { dcp_ao_fail 'prior receipt app digest mismatch'; return 1; }
}

dcp_ao_verify_installed_bundle() {
	local app; app="$(dcp_ao_app_path)"
	dcp_ao_verify_bundle_at "$app" || return 1
	dcp_ao_verify_install_receipt "$1"
}

dcp_ao_codex_binary() {
	local binary; binary="$(command -v codex || true)"
	[[ -n "$binary" && "$binary" == /* && -x "$binary" ]] || { dcp_ao_fail 'authenticated Codex CLI is absent'; return 1; }
	case "$binary" in /Applications/*) dcp_ao_fail 'refusing Codex executable from /Applications'; return 1;; esac
	printf '%s\n' "$binary"
}

dcp_ao_preflight_codex_worker() {
	local lab_root="$1" binary login_status help_status feature_status feature
	local -a exec_probe feature_probe
	binary="$(dcp_ao_codex_binary)" || return 1
	login_status="$(env -u CODEX_HOME "$binary" login status 2>&1)" || { dcp_ao_fail 'Codex worker cannot read standard authentication'; return 1; }
	[[ "$login_status" == *'Logged in'* ]] || { dcp_ao_fail 'Codex worker is not authenticated'; return 1; }
	exec_probe=(
		exec --ignore-user-config --ephemeral --strict-config
		--disable hooks --disable apps --disable plugins --disable multi_agent
		-c check_for_update_on_startup=false
		-c notice.hide_rate_limit_model_nudge=true
		-c 'approval_policy="on-request"'
		--sandbox workspace-write
		--add-dir "$lab_root/evidence/codex-preflight/gitdir"
		--add-dir "$lab_root/evidence/codex-preflight/common"
		--help
	)
	help_status="$(env -u CODEX_HOME "$binary" "${exec_probe[@]}" 2>&1)" || { dcp_ao_fail 'Codex worker parser rejected the model-free launch preflight'; return 1; }
	for feature in --ignore-user-config --ephemeral --strict-config; do [[ "$help_status" == *"$feature"* ]] || { dcp_ao_fail "Codex exec is missing $feature"; return 1; }; done
	feature_probe=(
		--disable hooks --disable apps --disable plugins --disable multi_agent
		-c check_for_update_on_startup=false
		-c notice.hide_rate_limit_model_nudge=true
		-c 'approval_policy="on-request"'
		-c 'approvals_reviewer="auto_review"'
		--sandbox workspace-write
		features list
	)
	feature_status="$(env -u CODEX_HOME "$binary" "${feature_probe[@]}" 2>&1)" || { dcp_ao_fail 'Codex worker config/sandbox capability preflight failed'; return 1; }
	[[ "$feature_status" != *'unknown configuration field'* ]] || { dcp_ao_fail 'Codex worker config/sandbox capability is unknown'; return 1; }
	for feature in apps hooks multi_agent plugins; do
		printf '%s\n' "$feature_status" | awk -v name="$feature" '$1 == name && $NF == "false" { found=1 } END { exit(found ? 0 : 1) }' || { dcp_ao_fail "Codex feature is not fail-closed: $feature"; return 1; }
	done
	[[ -z "${CODEX_HOME:-}" ]] || { dcp_ao_fail 'CODEX_HOME override makes worker identity ambiguous'; return 1; }
}

dcp_ao_export_runtime_env() {
	local lab_root="$1"
	export AO_RUN_FILE="$(dcp_ao_run_file "$lab_root")"
	export AO_DATA_DIR="$(dcp_ao_data_dir "$lab_root")"
	export AO_PORT="${DCP_AO_PORT:-43231}"
	export AO_AGENT=codex
	export AO_TELEMETRY_RENDERER=off AO_TELEMETRY_EVENTS=off AO_TELEMETRY_METRICS=off AO_TELEMETRY_REMOTE=off AO_TELEMETRY_DISABLED_EVENTS='*'
	unset CODEX_HOME
	export CODEX_SQLITE_HOME="$(dcp_ao_codex_state_home "$lab_root")"
	export DCP_AO_CODEX_ISOLATION=exec-ignore-user-config DCP_AO_CONTOUR_ID="$(dcp_ao_contour_id)"
	export DCP_AO_REQUIRE_APP_OWNER=1 DCP_AO_FAIL_CLOSED_DAEMON_REPLACEMENT=1
	export DCP_AO_EXPECTED_DAEMON_EXECUTABLE="$(dcp_ao_embedded_cli)"
	export VITE_DCP_HIDE_MANUAL_ORCHESTRATOR_SPAWN=1
	mkdir -p "$(dirname "$AO_RUN_FILE")" "$AO_DATA_DIR" "$CODEX_SQLITE_HOME"
}

dcp_ao_preflight_exact_contour() {
	local lab_root="$1" wb_core_status
	dcp_ao_verify_source "$lab_root" || return 1
	dcp_ao_verify_installed_bundle "$lab_root" || return 1
	dcp_ao_preflight_codex_worker "$lab_root" || return 1
	[[ "$(dcp_ao_validate_repo_only_target "$lab_root" 0)" == "$lab_root/targets/wb-browser-extension" ]] || return 1
	[[ "$(dcp_ao_validate_wb_core_target "$lab_root" 0)" == "$lab_root/targets/wb-core" ]] || return 1
	wb_core_status="$(dcp_ao_wb_core_compatibility_status "$lab_root/targets/wb-core")" || return 1
	[[ "$wb_core_status" == blocked || "$wb_core_status" == qualified ]] || {
		dcp_ao_fail 'wb-core compatibility status is ambiguous'; return 1;
	}
}

dcp_ao_print_contour() {
	local lab_root="$1"
	printf 'app=%s\n' "$(dcp_ao_app_path)"
	printf 'app_executable=%s\n' "$(dcp_ao_app_executable)"
	printf 'daemon=%s\n' "$(dcp_ao_embedded_cli)"
	printf 'source=%s\n' "$(dcp_ao_source_dir "$lab_root")"
	printf 'AO_DATA_DIR=%s\n' "$(dcp_ao_data_dir "$lab_root")"
	printf 'AO_RUN_FILE=%s\n' "$(dcp_ao_run_file "$lab_root")"
	printf 'CODEX_SQLITE_HOME=%s\n' "$(dcp_ao_codex_state_home "$lab_root")"
	printf 'DCP_AO_CONTOUR_ID=%s\n' "$(dcp_ao_contour_id)"
	printf 'target=%s\n' "$lab_root/targets/dcp-lab"
	printf 'repo_only_target=%s\n' "$lab_root/targets/wb-browser-extension"
	printf 'wb_core_target=%s\n' "$lab_root/targets/wb-core"
	printf 'wb_core_compatibility=%s\n' "$(dcp_ao_wb_core_compatibility_status "$lab_root/targets/wb-core")"
}
