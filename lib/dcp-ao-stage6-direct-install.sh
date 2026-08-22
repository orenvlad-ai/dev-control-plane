#!/usr/bin/env bash

# One-use Stage 6 direct-model installation. Source preparation is an explicit
# external gate: this installer never clones or repairs managed source. It
# stages an immutable source archive and signed arm64 artifact before stopping
# the canonical app, then installs only those staged bytes.

dcp_ao_stage6_final_configure() {
	DCP_AO_STAGE6_FINAL_MODE=1
	DCP_AO_TWIN_STAGE6_DIRECT_INSTALL_ID="$DCP_AO_TWIN_STAGE6_FINAL_INSTALL_ID"
	DCP_AO_TWIN_STAGE6_AGGREGATE_RECEIPT_SHA256="$DCP_AO_TWIN_STAGE6_DIRECT_RECEIPT_SHA256"
	DCP_AO_TWIN_STAGE6_AGGREGATE_SOURCE_COMMIT="$DCP_AO_TWIN_STAGE6_DIRECT_SOURCE_COMMIT"
	DCP_AO_TWIN_STAGE6_AGGREGATE_SOURCE_TREE="$DCP_AO_TWIN_STAGE6_DIRECT_SOURCE_TREE"
	DCP_AO_STAGE6_PREDECESSOR_SCHEMA=86
	DCP_AO_STAGE6_TARGET_SCHEMA=87
	DCP_AO_STAGE6_MIGRATION_VERSION=0087
	DCP_AO_STAGE6_ADOPTION_INPUT_SCHEMA='dcp.v2.stage6-final-adoption-input/v1'
	DCP_AO_STAGE6_INSTALL_RESULT_SCHEMA='dcp.v2.stage6-final-install/v1'
}

dcp_ao_stage6_direct_backup_root() {
	printf '%s/build/backups/%s-%s\n' "$1" "$DCP_AO_TWIN_STAGE6_DIRECT_INSTALL_ID" "$2"
}

dcp_ao_stage6_direct_find_attempt() {
	local lab_root="$1" manifest
	[[ -d "$lab_root/build/backups" ]] || return 1
	while IFS= read -r manifest; do
		grep -Fxq "install_identity=$DCP_AO_TWIN_STAGE6_DIRECT_INSTALL_ID" "$manifest" && { printf '%s\n' "${manifest%/manifest}"; return 0; }
	done < <(find "$lab_root/build/backups" -mindepth 2 -maxdepth 2 -type f -name manifest -print | LC_ALL=C sort)
	return 1
}

dcp_ao_stage6_direct_verify_predecessor_receipt() {
	local lab_root="$1" receipt
	dcp_ao_verify_replaceable_bundle_at "$(dcp_ao_app_path)" || return 1
	dcp_ao_verify_replaceable_install_receipt "$lab_root" || return 1
	receipt="$(dcp_ao_install_receipt "$lab_root")"
	[[ "$(dcp_ao_sha256 "$receipt")" == "$DCP_AO_TWIN_STAGE6_AGGREGATE_RECEIPT_SHA256" ]] || {
		dcp_ao_fail 'Stage 6 direct install predecessor receipt digest differs'; return 1;
	}
	grep -Fxq "fork_commit=$DCP_AO_TWIN_STAGE6_AGGREGATE_SOURCE_COMMIT" "$receipt" || return 1
	grep -Fxq "fork_tree=$DCP_AO_TWIN_STAGE6_AGGREGATE_SOURCE_TREE" "$receipt" || return 1
}

dcp_ao_stage6_direct_verify_live_fence() {
	local lab_root="$1" require_stopped="${2:-0}"
	[[ "$(dcp_ao_validate_twin_target "$lab_root" 0 1)" == "$lab_root/targets/dcp-wbc-integration-lab" ]] || return 1
	dcp_ao_stage6_direct_verify_predecessor_receipt "$lab_root" || return 1
	dcp_ao_verify_twin_stage6_direct_fence "$lab_root" "${DCP_AO_STAGE6_PREDECESSOR_SCHEMA:-85}" "$require_stopped" || return 1
	dcp_ao_verify_twin_stage6_external_fence
}

dcp_ao_stage6_direct_verify_staged() {
	local backup_root="$1" source_archive worker_archive artifact_archive staged_app manifest source_sha worker_sha artifact_sha
	manifest="$backup_root/manifest"
	source_archive="$backup_root/source.tar"
	worker_archive="$backup_root/worker-output.tar"
	artifact_archive="$backup_root/direct-model-arm64.zip"
	staged_app="$backup_root/staged/DCP Orchestrator.app"
	[[ -f "$manifest" && -f "$source_archive" && -f "$worker_archive" && -f "$artifact_archive" && -d "$staged_app" ]] || {
		dcp_ao_fail 'Stage 6 direct staged package is incomplete'; return 1;
	}
	grep -Fxq 'schema=1' "$manifest" || return 1
	grep -Fxq "install_identity=$DCP_AO_TWIN_STAGE6_DIRECT_INSTALL_ID" "$manifest" || return 1
	grep -Fxq "source_commit=$DCP_AO_FORK_COMMIT" "$manifest" || return 1
	grep -Fxq "source_tree=$DCP_AO_FORK_TREE" "$manifest" || return 1
	grep -Fxq "source_remote=$DCP_AO_FORK_REPOSITORY" "$manifest" || return 1
	source_sha="$(dcp_ao_sha256 "$source_archive")"
	worker_sha="$(dcp_ao_sha256 "$worker_archive")"
	artifact_sha="$(dcp_ao_sha256 "$artifact_archive")"
	grep -Fxq "source_archive_sha256=$source_sha" "$manifest" || { dcp_ao_fail 'staged source archive digest differs'; return 1; }
	grep -Fxq "worker_archive_sha256=$worker_sha" "$manifest" || { dcp_ao_fail 'staged Worker archive digest differs'; return 1; }
	grep -Fxq "artifact_archive_sha256=$artifact_sha" "$manifest" || { dcp_ao_fail 'staged artifact archive digest differs'; return 1; }
	[[ "$(git get-tar-commit-id <"$source_archive")" == "$DCP_AO_FORK_COMMIT" ]] || {
		dcp_ao_fail 'staged source archive commit differs'; return 1;
	}
	[[ "$(git get-tar-commit-id <"$worker_archive")" == "$DCP_AO_TWIN_STAGE6_WORKER_COMMIT" ]] || {
		dcp_ao_fail 'staged Worker archive commit differs'; return 1;
	}
	dcp_ao_verify_bundle_at "$staged_app" || return 1
	grep -Fxq "staged_daemon_sha256=$(dcp_ao_sha256 "$staged_app/Contents/Resources/daemon/dcp-orchestratord")" "$manifest" || return 1
	grep -Fxq "staged_asar_sha256=$(dcp_ao_sha256 "$staged_app/Contents/Resources/app.asar")" "$manifest" || return 1
}

dcp_ao_stage6_direct_stage() {
	local lab_root="$1" source_dir identity_before identity_after built stamp backup_root source_archive worker_archive artifact_archive staged_parent staged_app
	local source_sha worker_sha artifact_sha worktree
	if dcp_ao_stage6_direct_find_attempt "$lab_root" >/dev/null; then
		dcp_ao_fail 'Stage 6 direct install identity was already invoked; equal rerun is forbidden'; return 1
	fi
	source_dir="$(dcp_ao_prepare_source "$lab_root")" || return 1
	identity_before="$(dcp_ao_source_filesystem_identity "$source_dir")" || return 1
	stamp="$(date -u +%Y%m%dT%H%M%SZ)"
	backup_root="$(dcp_ao_stage6_direct_backup_root "$lab_root" "$stamp")"
	[[ ! -e "$backup_root" ]] || { dcp_ao_fail 'Stage 6 direct backup path already exists'; return 1; }
	mkdir -p "$backup_root"
	{
		printf 'schema=1\n'
		printf 'install_identity=%s\n' "$DCP_AO_TWIN_STAGE6_DIRECT_INSTALL_ID"
		printf 'status=staging\n'
		printf 'created_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
	} >"$backup_root/manifest"
	chmod 600 "$backup_root/manifest"
	build_app "$lab_root" >&2 || return 1
	built="$(dcp_ao_package_output "$lab_root")"
	dcp_ao_verify_source "$lab_root" || return 1
	identity_after="$(dcp_ao_source_filesystem_identity "$source_dir")" || return 1
	[[ "$identity_before" == "$identity_after" ]] || { dcp_ao_fail 'MANAGED_SOURCE_WORKTREE_DRIFT before staging'; return 1; }
	source_archive="$backup_root/source.tar"
	worker_archive="$backup_root/worker-output.tar"
	artifact_archive="$backup_root/direct-model-arm64.zip"
	staged_parent="$backup_root/staged"
	mkdir -p "$staged_parent"
	git -C "$source_dir" archive --format=tar "$DCP_AO_FORK_COMMIT" >"$source_archive"
	dcp_ao_verify_twin_stage6_direct_worker_checkout "$lab_root" || return 1
	worktree="$lab_root/data/worktrees/dcp-wbc-integration-lab/dcp-wbc-integration-lab-1"
	git -C "$worktree" archive --format=tar "$DCP_AO_TWIN_STAGE6_WORKER_COMMIT" >"$worker_archive"
	dcp_ao_verify_source "$lab_root" || return 1
	[[ "$(dcp_ao_source_filesystem_identity "$source_dir")" == "$identity_before" ]] || {
		dcp_ao_fail 'MANAGED_SOURCE_WORKTREE_DRIFT during source staging'; return 1;
	}
	/usr/bin/ditto -c -k --keepParent "$built" "$artifact_archive"
	/usr/bin/ditto -x -k "$artifact_archive" "$staged_parent"
	staged_app="$staged_parent/DCP Orchestrator.app"
	dcp_ao_verify_bundle_at "$staged_app" || return 1
	source_sha="$(dcp_ao_sha256 "$source_archive")"
	worker_sha="$(dcp_ao_sha256 "$worker_archive")"
	artifact_sha="$(dcp_ao_sha256 "$artifact_archive")"
	{
		printf 'source_commit=%s\n' "$DCP_AO_FORK_COMMIT"
		printf 'source_tree=%s\n' "$DCP_AO_FORK_TREE"
		printf 'source_remote=%s\n' "$DCP_AO_FORK_REPOSITORY"
		printf 'source_path_class=stable-standalone-clone\n'
		printf 'source_filesystem_identity=%s\n' "$identity_before"
		printf 'source_archive_sha256=%s\n' "$source_sha"
		printf 'worker_archive_sha256=%s\n' "$worker_sha"
		printf 'artifact_archive_sha256=%s\n' "$artifact_sha"
		printf 'staged_daemon_sha256=%s\n' "$(dcp_ao_sha256 "$staged_app/Contents/Resources/daemon/dcp-orchestratord")"
		printf 'staged_asar_sha256=%s\n' "$(dcp_ao_sha256 "$staged_app/Contents/Resources/app.asar")"
		printf 'worker_commit=%s\n' "$DCP_AO_TWIN_STAGE6_WORKER_COMMIT"
		printf 'worker_tree=%s\n' "$DCP_AO_TWIN_STAGE6_WORKER_TREE"
		printf 'worker_branch=%s\n' "$DCP_AO_TWIN_STAGE6_WORKER_BRANCH"
		printf 'predecessor_receipt_sha256=%s\n' "$DCP_AO_TWIN_STAGE6_AGGREGATE_RECEIPT_SHA256"
	} >>"$backup_root/manifest"
	mkdir -p "$backup_root/migration-probe"
	printf 'projects:\n  stage6-direct-migration-probe:\n    path: /nonexistent/dcp-stage6-direct-migration-probe\n    name: Stage 6 direct migration probe\n' >"$backup_root/migration-probe/config.yaml"
	dcp_ao_stage6_direct_verify_staged "$backup_root" || return 1
	printf '%s\n' "$backup_root"
}

dcp_ao_stage6_direct_record_backup_file() {
	local manifest="$1" key="$2" path="$3"
	if [[ -f "$path" && ! -L "$path" ]]; then
		printf '%s_state=present\n%s_sha256=%s\n' "$key" "$key" "$(dcp_ao_sha256 "$path")" >>"$manifest"
	elif [[ ! -e "$path" ]]; then
		printf '%s_state=absent\n' "$key" >>"$manifest"
	else
		dcp_ao_fail "Stage 6 direct backup source is unsafe: $key"; return 1
	fi
}

dcp_ao_stage6_direct_copy_tree() {
	/usr/bin/ditto "$1" "$2"
}

dcp_ao_stage6_direct_record_prior_backup() {
	local backup_root="$1" manifest prior
	manifest="$backup_root/manifest"; prior="$backup_root/prior"
	dcp_ao_stage6_direct_record_backup_file "$manifest" prior_database "$prior/data/ao.db" || return 1
	dcp_ao_stage6_direct_record_backup_file "$manifest" prior_database_wal "$prior/data/ao.db-wal" || return 1
	dcp_ao_stage6_direct_record_backup_file "$manifest" prior_database_shm "$prior/data/ao.db-shm" || return 1
	dcp_ao_stage6_direct_record_backup_file "$manifest" prior_receipt "$prior/state/install.receipt" || return 1
	dcp_ao_stage6_direct_record_backup_file "$manifest" prior_allowlist "$prior/state/lab-allowlist.json" || return 1
	dcp_ao_stage6_direct_record_backup_file "$manifest" prior_app_info "$prior/DCP Orchestrator.app/Contents/Info.plist" || return 1
	dcp_ao_stage6_direct_record_backup_file "$manifest" prior_app_daemon "$prior/DCP Orchestrator.app/Contents/Resources/daemon/dcp-orchestratord" || return 1
	dcp_ao_stage6_direct_record_backup_file "$manifest" prior_app_asar "$prior/DCP Orchestrator.app/Contents/Resources/app.asar" || return 1
	grep -Fxq 'prior_database_state=present' "$manifest" || { dcp_ao_fail 'Stage 6 direct database backup is absent'; return 1; }
	grep -Fxq 'prior_receipt_state=present' "$manifest" || { dcp_ao_fail 'Stage 6 direct receipt backup is absent'; return 1; }
	grep -Fxq 'prior_allowlist_state=present' "$manifest" || { dcp_ao_fail 'Stage 6 direct config backup is absent'; return 1; }
	grep -Fxq "prior_receipt_sha256=$DCP_AO_TWIN_STAGE6_AGGREGATE_RECEIPT_SHA256" "$manifest" || return 1
}

dcp_ao_stage6_direct_verify_install_copy() {
	local backup_root="$1" app="$2" manifest
	manifest="$backup_root/manifest"
	dcp_ao_verify_bundle_at "$app" || return 1
	grep -Fxq "staged_daemon_sha256=$(dcp_ao_sha256 "$app/Contents/Resources/daemon/dcp-orchestratord")" "$manifest" || {
		dcp_ao_fail 'Stage 6 direct install copy daemon digest differs'; return 1;
	}
	grep -Fxq "staged_asar_sha256=$(dcp_ao_sha256 "$app/Contents/Resources/app.asar")" "$manifest" || {
		dcp_ao_fail 'Stage 6 direct install copy app digest differs'; return 1;
	}
}

dcp_ao_stage6_direct_write_receipt() {
	local lab_root="$1" backup_root="$2" receipt staging app
	app="$(dcp_ao_app_path)"; receipt="$(dcp_ao_install_receipt "$lab_root")"; staging="$receipt.stage6-direct-$$"
	{
		printf 'schema=1\n'
		printf 'bundle_path=%s\n' "$app"
		printf 'bundle_id=pro.devcontrol.dcp-orchestrator\n'
		printf 'fork_commit=%s\n' "$DCP_AO_FORK_COMMIT"
		printf 'fork_tree=%s\n' "$DCP_AO_FORK_TREE"
		printf 'upstream_commit=%s\n' "$DCP_AO_UPSTREAM_COMMIT"
		printf 'i8_parity_diff_sha256=%s\n' "$DCP_AO_I8_PARITY_DIFF_SHA256"
		printf 'daemon_sha256=%s\n' "$(dcp_ao_sha256 "$(dcp_ao_embedded_cli)")"
		printf 'asar_sha256=%s\n' "$(dcp_ao_sha256 "$app/Contents/Resources/app.asar")"
		printf 'install_identity=%s\n' "$DCP_AO_TWIN_STAGE6_DIRECT_INSTALL_ID"
		grep -E '^(source_archive_sha256|worker_archive_sha256|artifact_archive_sha256)=' "$backup_root/manifest"
		printf 'predecessor_receipt_sha256=%s\n' "$DCP_AO_TWIN_STAGE6_AGGREGATE_RECEIPT_SHA256"
		printf 'installed_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
	} >"$staging"
	chmod 600 "$staging"
	mv "$staging" "$receipt"
	dcp_ao_verify_installed_bundle "$lab_root"
}

dcp_ao_stage6_direct_migrate() {
	local lab_root="$1" backup_root="$2" output duplicate_paths
	dcp_ao_export_runtime_env "$lab_root"
	output="$("$(dcp_ao_embedded_cli)" import --dry-run --yes --from "$backup_root/migration-probe" --json)" || return 1
	duplicate_paths="$(printf '%s' "$output" | /usr/bin/jq --stream -s -r '[.[] | select(length == 2) | .[0] | map(tostring) | join(".")] | group_by(.) | map(select(length != 1) | .[0]) | join(",")')" || return 1
	[[ -z "$duplicate_paths" ]] || { dcp_ao_fail 'Stage 6 direct migration response contains duplicate fields'; return 1; }
	printf '%s' "$output" | /usr/bin/jq -e '
		type == "object" and (keys == ["dryRun","projectsImported","projectsSkipped"] or
		keys == ["dryRun","notes","projectsImported","projectsSkipped"]) and
		.dryRun == true and .projectsImported == 1 and .projectsSkipped == 0 and
		((has("notes") | not) or (.notes | type == "array"))
	' >/dev/null || { dcp_ao_fail 'Stage 6 direct migration dry-run response differs'; return 1; }
	printf '%s\n' "$output" >"$backup_root/migration-response.json"
	chmod 600 "$backup_root/migration-response.json"
}

dcp_ao_stage6_direct_write_adoption_input() {
	local lab_root="$1" backup_root="$2" receipt_sha worktree worktree_json output_json worktree_digest output_digest input input_sha
	receipt_sha="$(dcp_ao_sha256 "$(dcp_ao_install_receipt "$lab_root")")"
	worktree="$lab_root/data/worktrees/dcp-wbc-integration-lab/dcp-wbc-integration-lab-1"
	worktree_json="$(/usr/bin/jq -cS -n --arg branch "$DCP_AO_TWIN_STAGE6_WORKER_BRANCH" --arg worktree "$worktree" '{branch:$branch,worktree:$worktree}')"
	output_json="$(/usr/bin/jq -cS -n --arg commit "$DCP_AO_TWIN_STAGE6_WORKER_COMMIT" --arg tree "$DCP_AO_TWIN_STAGE6_WORKER_TREE" \
		'{commit:$commit,content:"Stage 6 DCP v2 canary.",path:"docs/STAGE6_CANARY.md",tree:$tree}')"
	worktree_digest="$(printf '%s' "$worktree_json" | dcp_ao_sha256_stream)"
	output_digest="$(printf '%s' "$output_json" | dcp_ao_sha256_stream)"
	input="$(/usr/bin/jq -cS -n --arg source "$DCP_AO_FORK_COMMIT" --arg sourceTree "$DCP_AO_FORK_TREE" \
		--arg receipt "$receipt_sha" --arg task "$DCP_AO_TWIN_STAGE6_TASK_ID" --arg revision "$DCP_AO_TWIN_STAGE6_REVISION_ID" \
		--arg command "$DCP_AO_TWIN_STAGE6_COMMAND_ID" --arg action "$DCP_AO_TWIN_STAGE6_ACTION_ID" \
		--arg runtime "$DCP_AO_TWIN_STAGE6_DIRECT_RUNTIME_ID" --arg nativeAction "$DCP_AO_TWIN_STAGE6_NATIVE_ACTION_ID" \
		--arg commit "$DCP_AO_TWIN_STAGE6_WORKER_COMMIT" --arg tree "$DCP_AO_TWIN_STAGE6_WORKER_TREE" \
		--arg branch "$DCP_AO_TWIN_STAGE6_WORKER_BRANCH" --arg worktree "$worktree" --arg worktreeDigest "$worktree_digest" \
		--arg outputDigest "$output_digest" \
		--arg inputSchema "${DCP_AO_STAGE6_ADOPTION_INPUT_SCHEMA:-dcp.v2.stage6-direct-adoption-input/v1}" \
		'{schemaVersion:$inputSchema,sourceCommit:$source,sourceTree:$sourceTree,installReceiptSha:$receipt,
		taskId:$task,revisionId:$revision,commandId:$command,actionId:$action,runtimeId:$runtime,nativeActionId:$nativeAction,
		nativeSequence:74,commitSha:$commit,treeSha:$tree,branch:$branch,worktree:$worktree,worktreeDigest:$worktreeDigest,
		outputDigest:$outputDigest,remoteBranchAbsent:true,openPrCount:0,consumed:false}')"
	printf '%s\n' "$input" >"$backup_root/adoption-input.json"
	chmod 600 "$backup_root/adoption-input.json"
	input_sha="$(dcp_ao_sha256 "$backup_root/adoption-input.json")"
	printf 'adoption_input_sha256=%s\n' "$input_sha" >>"$backup_root/manifest"
}

dcp_ao_stage6_direct_rollback() {
	local lab_root="$1" backup_root="$2" app failed_app failed_data failed_state
	app="$(dcp_ao_app_path)"; failed_app="$backup_root/failed-direct-model.app"; failed_data="$backup_root/failed-data"; failed_state="$backup_root/failed-state"
	[[ ! -e "$failed_app" && ! -e "$failed_data" && ! -e "$failed_state" ]] || return 1
	[[ ! -e "$app" ]] || mv "$app" "$failed_app"
	mv "$backup_root/prior/DCP Orchestrator.app" "$app"
	[[ ! -e "$lab_root/data" ]] || mv "$lab_root/data" "$failed_data"
	dcp_ao_stage6_direct_copy_tree "$backup_root/prior/data" "$lab_root/data"
	[[ ! -e "$lab_root/state" ]] || mv "$lab_root/state" "$failed_state"
	dcp_ao_stage6_direct_copy_tree "$backup_root/prior/state" "$lab_root/state"
	printf 'rollback=complete\n' >>"$backup_root/manifest"
	dcp_ao_stage6_direct_verify_predecessor_receipt "$lab_root" || return 1
	dcp_ao_verify_twin_stage6_direct_fence "$lab_root" "${DCP_AO_STAGE6_PREDECESSOR_SCHEMA:-85}" 1
}

dcp_ao_stage6_direct_install_locked() {
	local lab_root="$1" backup_root="$2" app prior staged install_staging receipt_sha
	app="$(dcp_ao_app_path)"; prior="$backup_root/prior"; staged="$backup_root/staged/DCP Orchestrator.app"
	install_staging="$(dirname "$app")/.DCP-Orchestrator-stage6-direct-$$.app"
	dcp_ao_stage6_direct_verify_staged "$backup_root" || return 1
	dcp_ao_stage6_direct_verify_live_fence "$lab_root" 0 || return 1
	dcp_ao_install_prepare_runtime "$lab_root" "$(dcp_ao_embedded_cli)" || return 1
	dcp_ao_verify_twin_stage6_direct_fence "$lab_root" "${DCP_AO_STAGE6_PREDECESSOR_SCHEMA:-85}" 1 || return 1
	mkdir -p "$prior"
	/usr/bin/ditto "$lab_root/state" "$prior/state"
	/usr/bin/ditto "$lab_root/data" "$prior/data"
	diff -qr "$lab_root/state" "$prior/state" >/dev/null
	diff -qr "$lab_root/data" "$prior/data" >/dev/null
	[[ "$(dcp_ao_sha256 "$prior/state/install.receipt")" == "$DCP_AO_TWIN_STAGE6_AGGREGATE_RECEIPT_SHA256" ]] || return 1
	dcp_ao_stage6_direct_record_prior_backup "$backup_root" || return 1
	# The source checkout is no longer needed after staging. Re-verify only the
	# immutable source/Worker archives and install bytes immediately before swap.
	dcp_ao_stage6_direct_verify_staged "$backup_root" || return 1
	[[ ! -e "$install_staging" ]] || { dcp_ao_fail 'Stage 6 direct install staging target already exists'; return 1; }
	/usr/bin/ditto "$staged" "$install_staging"
	dcp_ao_stage6_direct_verify_install_copy "$backup_root" "$install_staging" || return 1
	mv "$app" "$prior/DCP Orchestrator.app"
	if ! mv "$install_staging" "$app" || ! dcp_ao_verify_bundle_at "$app" ||
		! dcp_ao_stage6_direct_write_receipt "$lab_root" "$backup_root" ||
		! dcp_ao_stage6_direct_migrate "$lab_root" "$backup_root" ||
		! dcp_ao_verify_twin_stage6_direct_fence "$lab_root" "${DCP_AO_STAGE6_TARGET_SCHEMA:-86}" 1 ||
		! dcp_ao_verify_twin_stage6_external_fence ||
		! dcp_ao_stage6_direct_write_adoption_input "$lab_root" "$backup_root"; then
		dcp_ao_stage6_direct_rollback "$lab_root" "$backup_root" || dcp_ao_fail 'mandatory Stage 6 direct rollback verification failed'
		dcp_ao_fail 'Stage 6 direct install failed and rollback was attempted; reinstall is forbidden'
		return 1
	fi
	receipt_sha="$(dcp_ao_sha256 "$(dcp_ao_install_receipt "$lab_root")")"
	{
		printf 'status=installed-stopped\n'
		printf 'install_invocations=1\n'
		printf 'migration_%s_applications=1\n' "${DCP_AO_STAGE6_MIGRATION_VERSION:-0086}"
		printf 'rollback=not-invoked\n'
		printf 'install_receipt_sha256=%s\n' "$receipt_sha"
	} >>"$backup_root/manifest"
	printf 'backup %s\nreceipt %s\ninstalled %s\n' "$backup_root" "$receipt_sha" "$app"
}

install_stage6_direct_model_app() {
	local lab_root="$1" backup_root result
	if [[ "${DCP_AO_STAGE6_FINAL_MODE:-0}" != 1 && "$DCP_AO_FORK_COMMIT" != "$DCP_AO_TWIN_STAGE6_DIRECT_SOURCE_COMMIT" ]]; then
		dcp_ao_fail 'historical Stage 6 direct-model install is disabled for the final source lock'; return 1
	fi
	for name in DCP_AO_TEST_ALLOW_NONCANONICAL_STABLE_SOURCE DCP_AO_TEST_STABLE_SOURCE_DIR DCP_AO_TEST_SKIP_SOURCE_CONTENT_GUARDS DCP_AO_TEST_ALLOW_NONCANONICAL_LAB_ROOT; do
		[[ -z "${!name:-}" ]] || { dcp_ao_fail "test-only environment is forbidden for governed install: $name"; return 1; }
	done
	dcp_ao_stage6_direct_verify_live_fence "$lab_root" 0 || return 1
	dcp_ao_verify_source "$lab_root" || return 1
	backup_root="$(dcp_ao_stage6_direct_stage "$lab_root")" || return 1
	dcp_ao_gateway_acquire_lock "$lab_root" || return 1
	if dcp_ao_stage6_direct_install_locked "$lab_root" "$backup_root"; then result=0; else result=$?; fi
	dcp_ao_gateway_release_lock "$lab_root"
	return "$result"
}

preflight_stage6_direct_model() {
	local lab_root="$1" backup_root receipt_sha adoption_sha
	backup_root="$(dcp_ao_stage6_direct_find_attempt "$lab_root")" || { dcp_ao_fail 'Stage 6 direct install evidence is absent'; return 1; }
	dcp_ao_stage6_direct_verify_staged "$backup_root"
	dcp_ao_verify_installed_bundle "$lab_root"
	dcp_ao_verify_twin_stage6_direct_fence "$lab_root" "${DCP_AO_STAGE6_TARGET_SCHEMA:-86}" 1
	dcp_ao_verify_twin_stage6_external_fence
	grep -Fxq 'status=installed-stopped' "$backup_root/manifest"
	grep -Fxq 'install_invocations=1' "$backup_root/manifest"
	grep -Fxq "migration_${DCP_AO_STAGE6_MIGRATION_VERSION:-0086}_applications=1" "$backup_root/manifest"
	grep -Fxq 'rollback=not-invoked' "$backup_root/manifest"
	grep -Fxq 'prior_database_state=present' "$backup_root/manifest"
	grep -Eq '^prior_database_wal_state=(present|absent)$' "$backup_root/manifest"
	grep -Eq '^prior_database_shm_state=(present|absent)$' "$backup_root/manifest"
	grep -Fxq 'prior_receipt_state=present' "$backup_root/manifest"
	grep -Fxq 'prior_allowlist_state=present' "$backup_root/manifest"
	receipt_sha="$(dcp_ao_sha256 "$(dcp_ao_install_receipt "$lab_root")")"
	grep -Fxq "install_receipt_sha256=$receipt_sha" "$backup_root/manifest"
	[[ -f "$backup_root/adoption-input.json" ]] || { dcp_ao_fail 'future adoption input evidence is absent'; return 1; }
	adoption_sha="$(dcp_ao_sha256 "$backup_root/adoption-input.json")"
	grep -Fxq "adoption_input_sha256=$adoption_sha" "$backup_root/manifest"
	/usr/bin/jq -e --arg receipt "$receipt_sha" --arg task "$DCP_AO_TWIN_STAGE6_TASK_ID" \
		--arg inputSchema "${DCP_AO_STAGE6_ADOPTION_INPUT_SCHEMA:-dcp.v2.stage6-direct-adoption-input/v1}" \
		'.schemaVersion == $inputSchema and .installReceiptSha == $receipt and
		.taskId == $task and .nativeSequence == 74 and .remoteBranchAbsent == true and .openPrCount == 0 and .consumed == false' \
		"$backup_root/adoption-input.json" >/dev/null
	/usr/bin/jq -cn --arg source "$DCP_AO_FORK_COMMIT" --arg tree "$DCP_AO_FORK_TREE" --arg receipt "$receipt_sha" \
		--arg task "$DCP_AO_TWIN_STAGE6_TASK_ID" --arg action "$DCP_AO_TWIN_STAGE6_ACTION_ID" \
		--arg resultSchema "${DCP_AO_STAGE6_INSTALL_RESULT_SCHEMA:-dcp.v2.stage6-direct-install/v1}" \
		--argjson databaseSchema "${DCP_AO_STAGE6_TARGET_SCHEMA:-86}" \
		'{schemaVersion:$resultSchema,sourceCommit:$source,sourceTree:$tree,installReceiptSha:$receipt,taskId:$task,actionId:$action,databaseSchema:$databaseSchema,appStopped:true,adoptionConsumed:false}'
}

install_stage6_final_app() {
	dcp_ao_stage6_final_configure
	install_stage6_direct_model_app "$1"
}

preflight_stage6_final() {
	dcp_ao_stage6_final_configure
	preflight_stage6_direct_model "$1"
}

dcp_ao_stage6_final_assert_governed_env() {
	local name
	for name in DCP_AO_TEST_ALLOW_NONCANONICAL_STABLE_SOURCE DCP_AO_TEST_STABLE_SOURCE_DIR DCP_AO_TEST_SKIP_SOURCE_CONTENT_GUARDS DCP_AO_TEST_ALLOW_NONCANONICAL_LAB_ROOT; do
		[[ -z "${!name:-}" ]] || { dcp_ao_fail "test-only environment is forbidden for governed final continuation: $name"; return 1; }
	done
}

dcp_ao_stage6_final_attempt_root() {
	dcp_ao_stage6_final_configure
	dcp_ao_stage6_direct_find_attempt "$1"
}

dcp_ao_stage6_final_validate_adoption_response() {
	local response="$1" receipt_sha="$2" duplicate_paths
	duplicate_paths="$(/usr/bin/jq --stream -s -r '[.[] | select(length == 2) | .[0] | map(tostring) | join(".")] | group_by(.) | map(select(length != 1) | .[0]) | join(",")' "$response")" || return 1
	[[ -z "$duplicate_paths" ]] || { dcp_ao_fail 'Stage 6 final adoption response contains duplicate fields'; return 1; }
	/usr/bin/jq -e \
		--arg source "$DCP_AO_FORK_COMMIT" --arg tree "$DCP_AO_FORK_TREE" --arg receipt "$receipt_sha" \
		--arg task "$DCP_AO_TWIN_STAGE6_TASK_ID" --arg revision "$DCP_AO_TWIN_STAGE6_REVISION_ID" \
		--arg command "$DCP_AO_TWIN_STAGE6_COMMAND_ID" --arg action "$DCP_AO_TWIN_STAGE6_ACTION_ID" \
		--arg runtime "$DCP_AO_TWIN_STAGE6_DIRECT_RUNTIME_ID" --arg native "$DCP_AO_TWIN_STAGE6_NATIVE_ACTION_ID" \
		--arg commit "$DCP_AO_TWIN_STAGE6_WORKER_COMMIT" --arg workerTree "$DCP_AO_TWIN_STAGE6_WORKER_TREE" \
		--arg branch "$DCP_AO_TWIN_STAGE6_WORKER_BRANCH" '
		type == "object" and keys == ["adoption","applied","installReceiptSha","installedSourceCommit","installedSourceTree","schemaVersion"] and
		.schemaVersion == "dcp.v2.stage6-direct-adoption/v1" and .installedSourceCommit == $source and
		.installedSourceTree == $tree and .installReceiptSha == $receipt and .applied == true and
		.adoption.taskId == $task and .adoption.revisionId == $revision and .adoption.commandId == $command and
		.adoption.actionId == $action and .adoption.runtimeId == $runtime and .adoption.nativeActionId == $native and
		.adoption.nativeSequence == 74 and .adoption.commitSha == $commit and .adoption.treeSha == $workerTree and
		.adoption.branch == $branch and (.adoption.receiptId | type == "string" and length > 0) and
		(.adoption.legacyEvidenceDigest | test("^[0-9a-f]{64}$")) and (.adoption.worktreeDigest | test("^[0-9a-f]{64}$")) and
		(.adoption.outputDigest | test("^[0-9a-f]{64}$")) and (.adoption.consumedAt | type == "string")
	' "$response" >/dev/null || { dcp_ao_fail 'Stage 6 final adoption response identity differs'; return 1; }
}

adopt_stage6_final() {
	local lab_root="$1" backup_root manifest receipt_sha pending response_sha result=0
	dcp_ao_stage6_final_configure
	dcp_ao_stage6_final_assert_governed_env || return 1
	backup_root="$(dcp_ao_stage6_final_attempt_root "$lab_root")" || { dcp_ao_fail 'Stage 6 final install evidence is absent'; return 1; }
	manifest="$backup_root/manifest"; pending="$backup_root/adoption-response.pending.json"
	! grep -Eq '^adoption_attempt=' "$manifest" || { dcp_ao_fail 'Stage 6 final adoption was already attempted; replay is forbidden'; return 1; }
	[[ ! -e "$pending" && ! -e "$backup_root/adoption-response.json" ]] || { dcp_ao_fail 'Stage 6 final adoption output already exists'; return 1; }
	preflight_stage6_final "$lab_root" >/dev/null || return 1
	dcp_ao_gateway_acquire_lock "$lab_root" || return 1
	if preflight_stage6_final "$lab_root" >/dev/null; then
		printf 'adoption_attempt=1\nadoption_started_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >>"$manifest"
		dcp_ao_export_runtime_env "$lab_root"
		receipt_sha="$(dcp_ao_sha256 "$(dcp_ao_install_receipt "$lab_root")")"
		if "$(dcp_ao_embedded_cli)" dcp stage6-direct-adopt \
			--source-commit "$DCP_AO_FORK_COMMIT" --source-tree "$DCP_AO_FORK_TREE" \
			--install-receipt-sha "$receipt_sha" --json >"$pending" &&
			dcp_ao_stage6_final_validate_adoption_response "$pending" "$receipt_sha" &&
			dcp_ao_verify_twin_stage6_adopted_fence "$lab_root" 1 &&
			dcp_ao_verify_twin_stage6_external_fence; then
			mv "$pending" "$backup_root/adoption-response.json"
			response_sha="$(dcp_ao_sha256 "$backup_root/adoption-response.json")"
			printf 'adoption_status=adopted-stopped\nadoption_response_sha256=%s\nadoption_completed_at=%s\n' \
				"$response_sha" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >>"$manifest"
		else
			result=$?
			printf 'adoption_status=failed-or-ambiguous\n' >>"$manifest"
		fi
	else
		result=$?
	fi
	dcp_ao_gateway_release_lock "$lab_root"
	return "$result"
}

preflight_stage6_final_adopted() {
	local lab_root="$1" backup_root manifest response_sha
	dcp_ao_stage6_final_configure
	backup_root="$(dcp_ao_stage6_final_attempt_root "$lab_root")" || return 1
	manifest="$backup_root/manifest"
	dcp_ao_verify_installed_bundle "$lab_root"
	dcp_ao_verify_twin_stage6_adopted_fence "$lab_root" 1
	dcp_ao_verify_twin_stage6_external_fence
	grep -Fxq 'adoption_attempt=1' "$manifest"
	grep -Fxq 'adoption_status=adopted-stopped' "$manifest"
	[[ -f "$backup_root/adoption-response.json" ]] || return 1
	response_sha="$(dcp_ao_sha256 "$backup_root/adoption-response.json")"
	grep -Fxq "adoption_response_sha256=$response_sha" "$manifest"
	/usr/bin/jq -cn --arg task "$DCP_AO_TWIN_STAGE6_TASK_ID" --arg source "$DCP_AO_FORK_COMMIT" \
		'{schemaVersion:"dcp.v2.stage6-final-adopted/v1",taskId:$task,installedSourceCommit:$source,databaseSchema:87,appStopped:true,adoptionConsumed:true,providerEffect:false}'
}

dcp_ao_verify_twin_stage6_published_fence() {
	local lab_root="$1" task current revision commands counts active_rows pr_number
	dcp_ao_verify_twin_stopped_activation "$lab_root" 0 0 || return 1
	[[ "$(dcp_ao_repo_only_policy_scalar "$lab_root" 'SELECT max(version_id) FROM goose_db_version WHERE is_applied=1;')" == 87 ]] || return 1
	task="$(dcp_ao_repo_only_policy_scalar "$lab_root" "SELECT task_id || '|' || state || '|' || state_revision || '|' || current_revision_id || '|' || error_code FROM dcp_v2_task;")" || return 1
	[[ "$task" =~ ^${DCP_AO_TWIN_STAGE6_TASK_ID}\|checks_waiting\|3\|v2-[0-9a-f]{40}\|$ ]] || { dcp_ao_fail 'Stage 6 published Task fence differs'; return 1; }
	current="${task%|}"; current="${current##*|}"
	revision="$(dcp_ao_repo_only_policy_scalar "$lab_root" \
		"SELECT kind || '|' || head_ref || '|' || head_sha || '|' || tree_sha || '|' || predecessor_revision_id || '|' || cause_command_id || '|' || pr_number FROM dcp_v2_revision WHERE revision_id=(SELECT current_revision_id FROM dcp_v2_task);")" || return 1
	[[ "$revision" =~ ^provider_bound\|${DCP_AO_TWIN_STAGE6_WORKER_BRANCH}\|${DCP_AO_TWIN_STAGE6_WORKER_COMMIT}\|${DCP_AO_TWIN_STAGE6_WORKER_TREE}\|v2-[0-9a-f]{40}\|v2-[0-9a-f]{40}\|[1-9][0-9]*$ ]] || {
		dcp_ao_fail 'Stage 6 provider-bound Revision fence differs'; return 1;
	}
	pr_number="${revision##*|}"
	commands="$(dcp_ao_repo_only_policy_scalar "$lab_root" "SELECT sum(kind='publication.execute/v1' AND status='succeeded') || '|' || sum(kind='checks.observe/v1' AND status IN ('pending','leased')) || '|' || sum(status IN ('pending','leased')) FROM dcp_v2_command;")" || return 1
	[[ "$commands" == '1|1|1' ]] || { dcp_ao_fail 'Stage 6 published Command fence differs'; return 1; }
	counts="$(dcp_ao_repo_only_policy_scalar "$lab_root" 'SELECT (SELECT count(*) FROM dcp_v2_task) || "|" || (SELECT count(*) FROM dcp_v2_revision) || "|" || (SELECT count(*) FROM dcp_v2_command) || "|" || (SELECT count(*) FROM dcp_v2_action) || "|" || (SELECT count(*) FROM dcp_v2_admission) || "|" || (SELECT count(*) FROM dcp_v2_result);')" || return 1
	[[ "$counts" == '1|3|3|1|0|0' ]] || { dcp_ao_fail 'Stage 6 published lifecycle cardinality differs'; return 1; }
	active_rows="$(dcp_ao_repo_only_policy_scalar "$lab_root" "SELECT (SELECT count(*) FROM dcp_v2_model_runtime WHERE state IN ('reserved','running')) || '|' || (SELECT count(*) FROM dcp_v2_action WHERE status IN ('launching','running'));")" || return 1
	[[ "$active_rows" == '0|0' ]] || { dcp_ao_fail 'Stage 6 publication unexpectedly activated a model'; return 1; }
	printf '%s\n' "$pr_number"
}

dcp_ao_verify_twin_stage6_publication_effect() {
	local expected_pr="$1" refs pulls
	refs="$(dcp_ao_stage6_gh_api 'repos/orenvlad-ai/dcp-wbc-integration-lab/git/matching-refs/heads/ao/dcp-wbc-integration-lab-1/root')" || return 1
	printf '%s' "$refs" | /usr/bin/jq -e --arg sha "$DCP_AO_TWIN_STAGE6_WORKER_COMMIT" 'type == "array" and length == 1 and .[0].object.sha == $sha' >/dev/null || {
		dcp_ao_fail 'Stage 6 publication branch effect is absent or ambiguous'; return 1;
	}
	pulls="$(dcp_ao_stage6_gh_api 'repos/orenvlad-ai/dcp-wbc-integration-lab/pulls?state=all&head=orenvlad-ai:ao/dcp-wbc-integration-lab-1/root&per_page=100')" || return 1
	printf '%s' "$pulls" | /usr/bin/jq -e --argjson pr "$expected_pr" --arg head "$DCP_AO_TWIN_STAGE6_WORKER_COMMIT" \
		'type == "array" and length == 1 and .[0].number == $pr and .[0].state == "open" and .[0].draft == false and .[0].base.ref == "main" and .[0].head.sha == $head' >/dev/null || {
		dcp_ao_fail 'Stage 6 publication PR effect is absent or ambiguous'; return 1;
	}
}

continue_stage6_final() {
	local lab_root="$1" backup_root manifest pr_number status result=0
	dcp_ao_stage6_final_configure
	dcp_ao_stage6_final_assert_governed_env || return 1
	backup_root="$(dcp_ao_stage6_final_attempt_root "$lab_root")" || return 1
	manifest="$backup_root/manifest"
	! grep -Eq '^continuation_attempt=' "$manifest" || { dcp_ao_fail 'Stage 6 final live continuation was already attempted; restart is forbidden'; return 1; }
	preflight_stage6_final_adopted "$lab_root" >/dev/null || return 1
	dcp_ao_gateway_acquire_lock "$lab_root" || return 1
	if preflight_stage6_final_adopted "$lab_root" >/dev/null; then
		printf 'continuation_attempt=1\ncontinuation_started_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >>"$manifest"
		if dcp_ao_gateway_ensure_locked "$lab_root" "$(dcp_ao_embedded_cli)" &&
			pr_number="$(dcp_ao_verify_twin_stage6_published_fence "$lab_root")" &&
			dcp_ao_verify_twin_stage6_publication_effect "$pr_number"; then
			status="$(dcp_ao_gateway_status_json "$lab_root" "$(dcp_ao_embedded_cli)")"
			printf '%s\n' "$status" >"$backup_root/continuation-start-status.json"
			printf 'continuation_status=running-exact\ncontinuation_pr_number=%s\ncontinuation_start_status_sha256=%s\n' \
				"$pr_number" "$(dcp_ao_sha256 "$backup_root/continuation-start-status.json")" >>"$manifest"
		else
			result=$?
			printf 'continuation_status=failed-or-ambiguous\n' >>"$manifest"
		fi
	else
		result=$?
	fi
	dcp_ao_gateway_release_lock "$lab_root"
	return "$result"
}

dcp_ao_stage6_final_terminal_snapshot() {
	local lab_root="$1" task revision result result_bindings counts commands actions admissions direct_rows
	task="$(dcp_ao_repo_only_policy_scalar "$lab_root" "SELECT task_id || '|' || state || '|' || current_revision_id || '|' || terminal_result_id || '|' || repair_used || '|' || readmission_count || '|' || error_code FROM dcp_v2_task;")" || return 1
	revision="$(dcp_ao_repo_only_policy_scalar "$lab_root" "SELECT revision_id || '|' || kind || '|' || pr_number || '|' || head_sha || '|' || tree_sha FROM dcp_v2_revision WHERE revision_id=(SELECT current_revision_id FROM dcp_v2_task);")" || return 1
	result="$(dcp_ao_repo_only_policy_scalar "$lab_root" "SELECT result_id || '|' || task_id || '|' || revision_id || '|' || admission_id || '|' || command_id || '|' || kind || '|' || provider || '|' || proof_id || '|' || run_id || '|' || actor || '|' || manifest_digest || '|' || proof_digest || '|' || merge_sha || '|' || artifact_source_sha || '|' || artifact_digest || '|' || deployed_sha || '|' || environment || '|' || service || '|' || probe_digest || '|' || verified || '|' || error_code FROM dcp_v2_result WHERE kind='deployment';")" || return 1
	result_bindings="$(dcp_ao_repo_only_policy_scalar "$lab_root" "SELECT count(*) || '|' || sum(kind='release') || '|' || sum(kind='deployment') || '|' || count(DISTINCT merge_sha) || '|' || count(DISTINCT artifact_source_sha) || '|' || count(DISTINCT artifact_digest) || '|' || count(DISTINCT manifest_digest) || '|' || count(DISTINCT proof_digest) FROM dcp_v2_result;")" || return 1
	counts="$(dcp_ao_repo_only_policy_scalar "$lab_root" 'SELECT (SELECT count(*) FROM dcp_v2_task) || "|" || (SELECT count(*) FROM dcp_v2_revision) || "|" || (SELECT count(*) FROM dcp_v2_command) || "|" || (SELECT count(*) FROM dcp_v2_action) || "|" || (SELECT count(*) FROM dcp_v2_admission) || "|" || (SELECT count(*) FROM dcp_v2_incident) || "|" || (SELECT count(*) FROM dcp_v2_external_event) || "|" || (SELECT count(*) FROM dcp_v2_result);')" || return 1
	commands="$(dcp_ao_repo_only_policy_scalar "$lab_root" "SELECT count(*) || '|' || sum(status IN ('pending','leased')) || '|' || sum(kind='terminal.verify/v1' AND status='succeeded') FROM dcp_v2_command;")" || return 1
	actions="$(dcp_ao_repo_only_policy_scalar "$lab_root" "SELECT count(*) || '|' || sum(status IN ('queued','launching','running')) || '|' || sum(status='succeeded') || '|' || sum(status='failed') FROM dcp_v2_action;")" || return 1
	admissions="$(dcp_ao_repo_only_policy_scalar "$lab_root" "SELECT count(*) || '|' || sum(status='succeeded') || '|' || sum(status='readmission_required') || '|' || count(DISTINCT manifest_digest) FROM dcp_v2_admission;")" || return 1
	direct_rows="$(dcp_ao_repo_only_policy_scalar "$lab_root" "SELECT (SELECT count(*) FROM dcp_v2_model_runtime) || '|' || (SELECT count(*) FROM dcp_v2_model_runtime WHERE state IN ('reserved','running')) || '|' || (SELECT count(*) FROM dcp_v2_model_terminal_receipt) || '|' || (SELECT count(*) FROM dcp_v2_stage6_worker_adoption_v1);")" || return 1
	/usr/bin/jq -cS -n --arg task "$task" --arg revision "$revision" --arg result "$result" --arg resultBindings "$result_bindings" --arg counts "$counts" \
		--arg commands "$commands" --arg actions "$actions" --arg admissions "$admissions" --arg directRows "$direct_rows" \
		'{actions:$actions,admissions:$admissions,commands:$commands,counts:$counts,directRows:$directRows,result:$result,resultBindings:$resultBindings,revision:$revision,task:$task}'
}

dcp_ao_verify_twin_stage6_terminal_fence() {
	local lab_root="$1" snapshot task revision result result_bindings counts commands actions admissions direct_rows merge_sha artifact_source_sha deployed_sha
	local current_main pr_number pr wbc status action_count action_succeeded admission_count admission_succeeded admission_readmission admission_digests
	local task_count revision_count command_count action_rows admission_rows incident_rows event_rows result_rows
	dcp_ao_verify_installed_bundle "$lab_root" || return 1
	status="$(dcp_ao_gateway_status_json "$lab_root" "$(dcp_ao_embedded_cli)")" || return 1
	[[ "$(dcp_ao_gateway_state "$status")" == ready ]] || { dcp_ao_fail 'Stage 6 terminal fence requires the exact daemon ready'; return 1; }
	dcp_ao_gateway_assert_pair "$lab_root" "$status" || return 1
	dcp_ao_verify_twin_stopped_activation "$lab_root" 0 0 || return 1
	[[ "$(dcp_ao_repo_only_policy_scalar "$lab_root" 'SELECT max(version_id) FROM goose_db_version WHERE is_applied=1;')" == 87 ]] || return 1
	[[ "$(dcp_ao_repo_only_policy_scalar "$lab_root" 'PRAGMA integrity_check;')" == ok ]] || return 1
	[[ -z "$(dcp_ao_repo_only_policy_scalar "$lab_root" 'PRAGMA foreign_key_check;')" ]] || return 1
	snapshot="$(dcp_ao_stage6_final_terminal_snapshot "$lab_root")" || return 1
	task="$(printf '%s' "$snapshot" | /usr/bin/jq -r .task)"
	revision="$(printf '%s' "$snapshot" | /usr/bin/jq -r .revision)"
	result="$(printf '%s' "$snapshot" | /usr/bin/jq -r .result)"
	result_bindings="$(printf '%s' "$snapshot" | /usr/bin/jq -r .resultBindings)"
	counts="$(printf '%s' "$snapshot" | /usr/bin/jq -r .counts)"
	commands="$(printf '%s' "$snapshot" | /usr/bin/jq -r .commands)"
	actions="$(printf '%s' "$snapshot" | /usr/bin/jq -r .actions)"
	admissions="$(printf '%s' "$snapshot" | /usr/bin/jq -r .admissions)"
	direct_rows="$(printf '%s' "$snapshot" | /usr/bin/jq -r .directRows)"
	[[ "$task" =~ ^${DCP_AO_TWIN_STAGE6_TASK_ID}\|deployed\|v2-[0-9a-f]{40}\|v2-[0-9a-f]{40}\|[01]\|[0-2]\|$ ]] || { dcp_ao_fail 'Stage 6 terminal Task fence differs'; return 1; }
	[[ "$revision" =~ ^v2-[0-9a-f]{40}\|(provider_bound|readmission_output)\|[1-9][0-9]*\|[0-9a-f]{40}\|[0-9a-f]{40}$ ]] || { dcp_ao_fail 'Stage 6 terminal Revision fence differs'; return 1; }
	pr_number="$(printf '%s' "$revision" | awk -F'|' '{print $3}')"
	[[ "$result" =~ ^v2-[0-9a-f]{40}\|${DCP_AO_TWIN_STAGE6_TASK_ID}\|v2-[0-9a-f]{40}\|v2-[0-9a-f]{40}\|v2-[0-9a-f]{40}\|deployment\|github\|[^|]+\|[^|]+\|[^|]+\|[0-9a-f]{64}\|[0-9a-f]{64}\|[0-9a-f]{40}\|[0-9a-f]{40}\|[0-9a-f]{64}\|[0-9a-f]{40}\|dcp-wbc-integration-lab-selectel\|dcp-wbc-integration-lab\|[0-9a-f]{64}\|1\|$ ]] || {
		dcp_ao_fail 'Stage 6 terminal Result proof differs'; return 1;
	}
	merge_sha="$(printf '%s' "$result" | awk -F'|' '{print $13}')"
	artifact_source_sha="$(printf '%s' "$result" | awk -F'|' '{print $14}')"
	deployed_sha="$(printf '%s' "$result" | awk -F'|' '{print $16}')"
	[[ "$merge_sha" == "$artifact_source_sha" && "$merge_sha" == "$deployed_sha" ]] || { dcp_ao_fail 'Stage 6 terminal merge/artifact/deploy SHA binding differs'; return 1; }
	[[ "$result_bindings" == '2|1|1|1|1|1|1|2' ]] || { dcp_ao_fail 'Stage 6 terminal release/deployment Result binding differs'; return 1; }
	IFS='|' read -r task_count revision_count command_count action_rows admission_rows incident_rows event_rows result_rows <<<"$counts"
	[[ "$task_count" == 1 && "$revision_count" -ge 3 && "$command_count" -ge 3 && "$action_rows" -ge 2 &&
		"$admission_rows" -ge 1 && "$admission_rows" -le 3 && "$incident_rows" == 0 && "$event_rows" -ge 2 && "$result_rows" == 2 ]] || {
		dcp_ao_fail 'Stage 6 terminal lifecycle table cardinality differs'; return 1;
	}
	[[ "$commands" =~ ^[1-9][0-9]*\|0\|1$ ]] || { dcp_ao_fail 'Stage 6 terminal Command cardinality differs'; return 1; }
	[[ "$actions" =~ ^[1-9][0-9]*\|0\|[1-9][0-9]*\|0$ ]] || { dcp_ao_fail 'Stage 6 terminal Action cardinality differs'; return 1; }
	action_count="${actions%%|*}"; action_succeeded="$(printf '%s' "$actions" | awk -F'|' '{print $3}')"
	[[ "$action_count" == "$action_succeeded" ]] || { dcp_ao_fail 'Stage 6 terminal Actions are not all succeeded'; return 1; }
	[[ "$admissions" =~ ^[1-3]\|1\|[0-2]\|[1-3]$ ]] || { dcp_ao_fail 'Stage 6 terminal Admission cardinality differs'; return 1; }
	admission_count="${admissions%%|*}"; admission_succeeded="$(printf '%s' "$admissions" | awk -F'|' '{print $2}')"; admission_readmission="$(printf '%s' "$admissions" | awk -F'|' '{print $3}')"; admission_digests="${admissions##*|}"
	[[ "$admission_succeeded" == 1 && "$admission_count" -eq $((admission_readmission + 1)) && "$admission_count" == "$admission_digests" ]] || { dcp_ao_fail 'Stage 6 terminal Admissions are duplicated or not terminal'; return 1; }
	[[ "$direct_rows" =~ ^[1-9][0-9]*\|0\|[1-9][0-9]*\|1$ ]] || { dcp_ao_fail 'Stage 6 terminal direct-model rows differ'; return 1; }
	dcp_ao_install_assert_no_active_model_actions "$lab_root" || return 1
	current_main="$(dcp_ao_stage6_gh_api 'repos/orenvlad-ai/dcp-wbc-integration-lab/git/ref/heads/main')" || return 1
	printf '%s' "$current_main" | /usr/bin/jq -e --arg sha "$merge_sha" '.object.sha == $sha' >/dev/null || { dcp_ao_fail 'Stage 6 terminal lab main differs from Result merge'; return 1; }
	pr="$(dcp_ao_stage6_gh_api "repos/orenvlad-ai/dcp-wbc-integration-lab/pulls/$pr_number")" || return 1
	printf '%s' "$pr" | /usr/bin/jq -e --argjson number "$pr_number" --arg merge "$merge_sha" \
		'.number == $number and .state == "closed" and .merged == true and .merge_commit_sha == $merge and .base.ref == "main"' >/dev/null || {
		dcp_ao_fail 'Stage 6 terminal PR merge readback differs'; return 1;
	}
	wbc="$(dcp_ao_stage6_gh_api 'repos/orenvlad-ai/wb-core/pulls/987')" || return 1
	printf '%s' "$wbc" | /usr/bin/jq -e --arg head "$DCP_AO_TWIN_STAGE6_WBC_PR_HEAD" '
		.number == 987 and .state == "open" and .merged == false and .base.ref == "main" and .head.sha == $head
	' >/dev/null || { dcp_ao_fail 'Stage 6 terminal frozen WBC PR 987 boundary drifted'; return 1; }
	printf '%s\n' "$snapshot"
}

restart_stage6_final_dedupe() {
	local lab_root="$1" backup_root manifest before after result=0
	dcp_ao_stage6_final_configure
	dcp_ao_stage6_final_assert_governed_env || return 1
	backup_root="$(dcp_ao_stage6_final_attempt_root "$lab_root")" || return 1
	manifest="$backup_root/manifest"
	grep -Fxq 'continuation_attempt=1' "$manifest" || return 1
	grep -Fxq 'continuation_status=running-exact' "$manifest" || return 1
	! grep -Eq '^terminal_restart_attempt=' "$manifest" || { dcp_ao_fail 'Stage 6 terminal restart/dedupe was already attempted'; return 1; }
	before="$(dcp_ao_verify_twin_stage6_terminal_fence "$lab_root")" || return 1
	dcp_ao_gateway_acquire_lock "$lab_root" || return 1
	if before="$(dcp_ao_verify_twin_stage6_terminal_fence "$lab_root")"; then
		printf 'terminal_restart_attempt=1\nterminal_restart_started_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >>"$manifest"
		printf '%s\n' "$before" >"$backup_root/terminal-before-restart.json"
		if dcp_ao_install_prepare_runtime "$lab_root" "$(dcp_ao_embedded_cli)" &&
			dcp_ao_gateway_ensure_locked "$lab_root" "$(dcp_ao_embedded_cli)" &&
			after="$(dcp_ao_verify_twin_stage6_terminal_fence "$lab_root")" && [[ "$before" == "$after" ]]; then
			printf '%s\n' "$after" >"$backup_root/terminal-after-restart.json"
			printf 'terminal_restart_status=dedupe-proven\nterminal_snapshot_sha256=%s\nterminal_restart_completed_at=%s\n' \
				"$(dcp_ao_sha256 "$backup_root/terminal-after-restart.json")" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >>"$manifest"
		else
			result=$?
			printf 'terminal_restart_status=failed-or-ambiguous\n' >>"$manifest"
		fi
	else
		result=$?
	fi
	dcp_ao_gateway_release_lock "$lab_root"
	return "$result"
}
