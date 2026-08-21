#!/usr/bin/env bash

# One-use Stage 6 direct-model installation. Source preparation is an explicit
# external gate: this installer never clones or repairs managed source. It
# stages an immutable source archive and signed arm64 artifact before stopping
# the canonical app, then installs only those staged bytes.

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
	dcp_ao_verify_twin_stage6_direct_fence "$lab_root" 85 "$require_stopped" || return 1
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
		'{schemaVersion:"dcp.v2.stage6-direct-adoption-input/v1",sourceCommit:$source,sourceTree:$sourceTree,installReceiptSha:$receipt,
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
	dcp_ao_verify_twin_stage6_direct_fence "$lab_root" 85 1
}

dcp_ao_stage6_direct_install_locked() {
	local lab_root="$1" backup_root="$2" app prior staged install_staging receipt_sha
	app="$(dcp_ao_app_path)"; prior="$backup_root/prior"; staged="$backup_root/staged/DCP Orchestrator.app"
	install_staging="$(dirname "$app")/.DCP-Orchestrator-stage6-direct-$$.app"
	dcp_ao_stage6_direct_verify_staged "$backup_root" || return 1
	dcp_ao_stage6_direct_verify_live_fence "$lab_root" 0 || return 1
	dcp_ao_install_prepare_runtime "$lab_root" "$(dcp_ao_embedded_cli)" || return 1
	dcp_ao_verify_twin_stage6_direct_fence "$lab_root" 85 1 || return 1
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
		! dcp_ao_verify_twin_stage6_direct_fence "$lab_root" 86 1 ||
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
		printf 'migration_0086_applications=1\n'
		printf 'rollback=not-invoked\n'
		printf 'install_receipt_sha256=%s\n' "$receipt_sha"
	} >>"$backup_root/manifest"
	printf 'backup %s\nreceipt %s\ninstalled %s\n' "$backup_root" "$receipt_sha" "$app"
}

install_stage6_direct_model_app() {
	local lab_root="$1" backup_root result
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
	dcp_ao_verify_twin_stage6_direct_fence "$lab_root" 86 1
	dcp_ao_verify_twin_stage6_external_fence
	grep -Fxq 'status=installed-stopped' "$backup_root/manifest"
	grep -Fxq 'install_invocations=1' "$backup_root/manifest"
	grep -Fxq 'migration_0086_applications=1' "$backup_root/manifest"
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
		'.schemaVersion == "dcp.v2.stage6-direct-adoption-input/v1" and .installReceiptSha == $receipt and
		.taskId == $task and .nativeSequence == 74 and .remoteBranchAbsent == true and .openPrCount == 0 and .consumed == false' \
		"$backup_root/adoption-input.json" >/dev/null
	/usr/bin/jq -cn --arg source "$DCP_AO_FORK_COMMIT" --arg tree "$DCP_AO_FORK_TREE" --arg receipt "$receipt_sha" \
		--arg task "$DCP_AO_TWIN_STAGE6_TASK_ID" --arg action "$DCP_AO_TWIN_STAGE6_ACTION_ID" \
		'{schemaVersion:"dcp.v2.stage6-direct-install/v1",sourceCommit:$source,sourceTree:$tree,installReceiptSha:$receipt,taskId:$task,actionId:$action,databaseSchema:86,appStopped:true,adoptionConsumed:false}'
}
