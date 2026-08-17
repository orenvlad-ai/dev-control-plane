#!/usr/bin/env bash

dcp_ao_validate_prompt() {
	local prompt="$1"
	local size
	if [[ -z "$prompt" ]]; then
		dcp_ao_fail 'prompt must not be empty'
		return 1
	fi
	if [[ "$prompt" == *$'\n'* || "$prompt" == *$'\r'* ]] || \
		printf '%s' "$prompt" | LC_ALL=C grep '[[:cntrl:]]' >/dev/null; then
		dcp_ao_fail 'prompt must be one line without control characters'
		return 1
	fi
	size="$(printf '%s' "$prompt" | LC_ALL=C wc -c | tr -d '[:space:]')"
	if [[ "$size" -gt 512 ]]; then
		dcp_ao_fail 'prompt must be at most 512 UTF-8 bytes'
		return 1
	fi
}

dcp_ao_validate_task_id() {
	local task_id="$1"
	if [[ ! "$task_id" =~ ^[a-z0-9]([a-z0-9-]{0,14}[a-z0-9])?$ ]]; then
		dcp_ao_fail 'task id must be 1-16 lowercase letters, digits, or internal hyphens'
		return 1
	fi
}

dcp_ao_review_agent_rules() {
	printf '%s\n' "DCP synthetic PR profile v4. Work only in this exact public synthetic repository, current native worktree and current AO branch. Do not create subagents, extra branches, worktrees, remotes, network services or additional pull requests. On the initial policy action implement only the direct task, create one commit lineage, push the current branch, open one ready pull request targeting main, and stop. If the trusted daemon supplies the one bounded findings-repair envelope, change only that task on the same branch and pull request, create one new head, push, and stop. Never merge or manually review; only the trusted daemon may perform exact-head review, FIFO admission and terminal merge."
}

dcp_ao_review_config_json() {
	printf '%s\n' "{\"defaultBranch\":\"main\",\"sessionPrefix\":\"dcp-review-lab\",\"worker\":{\"agent\":\"codex\",\"agentConfig\":{\"permissions\":\"accept-edits\",\"dcpReviewLabNetwork\":true}},\"reviewers\":[{\"harness\":\"codex\"}],\"agentRules\":\"$(dcp_ao_review_agent_rules)\"}"
}

dcp_ao_repo_only_agent_rules() {
	printf '%s\n' "DCP repo-only profile v1. Work only in this exact public wb-browser-extension repository, current native worktree and current AO branch. Read and obey the repository AGENTS.md. Do not access or mutate wb-core, dev-control-plane, dcp-orchestrator, production, secrets, other repositories, deployments, servers, telemetry, or live Wildberries APIs. Do not create subagents, extra branches, worktrees, remotes, network services or additional pull requests. On the initial policy action implement only the direct task, run the repository baseline, create one commit lineage, push the current branch, open one ready pull request targeting main, and stop. If the trusted daemon supplies the one bounded findings-repair envelope, change only that task on the same branch and pull request, create one new head, run the repository baseline, push, and stop. Never merge or manually review; only the trusted daemon may perform exact-head review, FIFO admission and terminal merge."
}

dcp_ao_repo_only_config_json() {
	printf '%s\n' "{\"defaultBranch\":\"main\",\"sessionPrefix\":\"wb-browser-extension\",\"worker\":{\"agent\":\"codex\",\"agentConfig\":{\"permissions\":\"accept-edits\",\"dcpReviewLabNetwork\":true}},\"reviewers\":[{\"harness\":\"codex\"}],\"agentRules\":\"$(dcp_ao_repo_only_agent_rules)\"}"
}

dcp_ao_wb_core_agent_rules() {
	printf '%s\n' "DCP wb-core repo-only profile v1. Work only in this exact public wb-core repository, current native worktree and current AO branch. Read and obey the repository AGENTS.md. The task must remain task:standard with exactly scope:repo-only. Do not access live runtime, production, SSH, secrets, runtime data, business data, other repositories, deployments, servers, telemetry, or live Wildberries APIs. Do not create subagents, extra branches, worktrees, remotes, network services or additional pull requests. On the initial policy action implement only the direct task, run baseline, create one commit lineage, push the current branch, open one ready pull request targeting main with exactly task:standard and scope:repo-only and no release label, and stop. If the trusted daemon supplies the one bounded findings-repair envelope, change only that task on the same branch and pull request, create one new head, run baseline, push, and stop. Never add release:ready, merge, release or manually review; only the trusted daemon may perform exact-head review and FIFO admission, and only the WBC GitHub Actions Release Train may merge and add release:done."
}

dcp_ao_wb_core_config_json() {
	printf '%s\n' "{\"defaultBranch\":\"main\",\"sessionPrefix\":\"wb-core\",\"worker\":{\"agent\":\"codex\",\"agentConfig\":{\"permissions\":\"accept-edits\",\"dcpReviewLabNetwork\":true}},\"reviewers\":[{\"harness\":\"codex\"}],\"agentRules\":\"$(dcp_ao_wb_core_agent_rules)\"}"
}

dcp_ao_json_extract() {
	local json="$1" path="$2"
	[[ -x /usr/bin/jq ]] || { dcp_ao_fail 'system JSON parser is absent'; return 1; }
	printf '%s' "$json" | /usr/bin/jq -er --arg path "$path" \
		'getpath($path | split(".") | map(if test("^[0-9]+$") then tonumber else . end))' 2>/dev/null
}

dcp_ao_validate_remote_free_target() {
	local lab_root="$1"
	local target="$lab_root/targets/dcp-lab"
	if [[ ! -d "$target/.git" ]]; then
		dcp_ao_fail 'dcp-lab target is absent; run bin/dcp-ao init-target'
		return 1
	fi
	local resolved
	resolved="$(cd "$target" && pwd -P)"
	if [[ "$resolved" != "$target" ]]; then dcp_ao_fail 'dcp-lab target path did not resolve exactly'; return 1; fi
	if [[ "$(git -C "$target" rev-parse --show-toplevel)" != "$resolved" ]]; then dcp_ao_fail 'dcp-lab repository root mismatch'; return 1; fi
	if [[ -n "$(git -C "$target" remote)" ]]; then dcp_ao_fail 'dcp-lab target must have no remotes'; return 1; fi
	if ! git -C "$target" ls-files --error-unmatch .dcp-lab-target >/dev/null; then dcp_ao_fail 'dcp-lab identity marker is not tracked'; return 1; fi
	if [[ "$(git -C "$target" ls-files)" != '.dcp-lab-target' ]]; then dcp_ao_fail 'dcp-lab baseline may track only its identity marker'; return 1; fi
	if [[ "$(git -C "$target" branch --show-current)" != main ]]; then dcp_ao_fail 'dcp-lab baseline branch must be main'; return 1; fi
	if [[ "$(git -C "$target" rev-list --count HEAD)" -ne 1 ]]; then dcp_ao_fail 'dcp-lab baseline must contain exactly one commit'; return 1; fi
	if [[ "$(dcp_ao_sha256 "$target/.dcp-lab-target")" != '63af912083e6fc32693b315457555805855fe3db87bc6ab730946a061a2219f1' ]]; then dcp_ao_fail 'dcp-lab identity marker content mismatch'; return 1; fi
	local worktree
	while IFS= read -r worktree; do
		[[ "$worktree" == "$target" || "$worktree" == "$lab_root/data/worktrees/"* ]] || {
			dcp_ao_fail "dcp-lab has a foreign linked worktree: $worktree"; return 1;
		}
	done < <(git -C "$target" worktree list --porcelain | sed -n 's/^worktree //p')
	if [[ -n "$(git -C "$target" status --porcelain)" ]]; then dcp_ao_fail 'dcp-lab target must be clean before submission'; return 1; fi
	printf '%s\n' "$resolved"
}

dcp_ao_refresh_review_target() {
	local target="$1" attempt
	for attempt in 1 2 3; do
		if git -C "$target" fetch --quiet --no-tags origin main; then
			return 0
		fi
		if [[ "$attempt" -lt 3 ]]; then sleep "$attempt"; fi
	done
	dcp_ao_fail 'dcp-review-lab origin/main fetch failed after bounded retries'
	return 1
}

dcp_ao_validate_review_provider_identity() {
	local provider
	dcp_ao_require_tool gh || return 1
	provider="$(gh api repos/orenvlad-ai/dcp-review-lab \
		--jq '[.full_name, (.private|tostring), .default_branch, (.id|tostring), (.owner.id|tostring)] | join("|")')" || {
		dcp_ao_fail 'dcp-review-lab provider identity is unavailable'; return 1;
	}
	[[ "$provider" == 'orenvlad-ai/dcp-review-lab|false|main|1329007118|237411244' ]] || {
		dcp_ao_fail 'dcp-review-lab provider identity is not exact and public'; return 1;
	}
}

dcp_ao_refresh_repo_only_target() {
	local target="$1" attempt
	for attempt in 1 2 3; do
		if git -C "$target" fetch --quiet --no-tags origin main; then
			return 0
		fi
		if [[ "$attempt" -lt 3 ]]; then sleep "$attempt"; fi
	done
	dcp_ao_fail 'wb-browser-extension origin/main fetch failed after bounded retries'
	return 1
}

dcp_ao_validate_repo_only_provider_identity() {
	local provider
	dcp_ao_require_tool gh || return 1
	provider="$(gh api repos/orenvlad-ai/wb-browser-extension \
		--jq '[.full_name, (.private|tostring), .default_branch, (.id|tostring), (.owner.id|tostring)] | join("|")')" || {
		dcp_ao_fail 'wb-browser-extension provider identity is unavailable'; return 1;
	}
	[[ "$provider" == 'orenvlad-ai/wb-browser-extension|false|main|1335072844|237411244' ]] || {
		dcp_ao_fail 'wb-browser-extension provider identity is not exact and public'; return 1;
	}
}

dcp_ao_refresh_wb_core_target() {
	local target="$1" attempt
	for attempt in 1 2 3; do
		if git -C "$target" fetch --quiet --no-tags origin main; then
			return 0
		fi
		if [[ "$attempt" -lt 3 ]]; then sleep "$attempt"; fi
	done
	dcp_ao_fail 'wb-core origin/main fetch failed after bounded retries'
	return 1
}

dcp_ao_validate_wb_core_provider_identity() {
	local provider
	dcp_ao_require_tool gh || return 1
	provider="$(gh api repos/orenvlad-ai/wb-core \
		--jq '[.full_name, (.private|tostring), .default_branch, (.id|tostring), (.owner.id|tostring)] | join("|")')" || {
		dcp_ao_fail 'wb-core provider identity is unavailable'; return 1;
	}
	[[ "$provider" == 'orenvlad-ai/wb-core|false|main|1201929580|237411244' ]] || {
		dcp_ao_fail 'wb-core provider identity is not exact and public'; return 1;
	}
}

dcp_ao_wb_core_compatibility_status() {
	local target="$1" marker='wb-core.dcp-release-handoff/v1' path lab_root project_status
	dcp_ao_wb_core_rules_match_source_lock || return 1
	for path in \
		docs/architecture/11_github_release_train.md \
		apps/github_release_train.py \
		apps/github_release_train_spec.py; do
		git -C "$target" grep -Fq "$marker" HEAD -- "$path" || { printf 'blocked\n'; return 0; }
	done
	lab_root="${target%/targets/wb-core}"
	[[ "$lab_root/targets/wb-core" == "$target" ]] || {
		dcp_ao_fail 'wb-core compatibility target path is outside the exact contour'; return 1;
	}
	project_status="$(dcp_ao_wb_core_project_identity_status "$lab_root")" || return 1
	printf '%s\n' "$project_status"
}

dcp_ao_wb_core_rules_match_source_lock() {
	local rules bytes digest
	rules="$(dcp_ao_wb_core_agent_rules)"
	bytes="$(printf '%s' "$rules" | LC_ALL=C wc -c | tr -d '[:space:]')"
	digest="$(printf '%s' "$rules" | dcp_ao_sha256_stream)"
	[[ "$bytes" == "$DCP_AO_WB_CORE_POLICY_AGENT_RULES_BYTES" && \
		"$digest" == "$DCP_AO_WB_CORE_POLICY_AGENT_RULES_SHA256" ]] || {
		dcp_ao_fail 'wb-core adapter policy rules drifted from the pinned managed-source expectation'; return 1;
	}
}

dcp_ao_wb_core_project_identity_status() {
	local lab_root="$1" table_count project_json expected_config rules
	table_count="$(dcp_ao_repo_only_policy_scalar "$lab_root" \
		"SELECT count(*) FROM sqlite_master WHERE type='table' AND name='projects';")" || return 1
	[[ "$table_count" == 1 ]] || { printf 'blocked\n'; return 0; }
	project_json="$(dcp_ao_repo_only_policy_scalar "$lab_root" \
		"SELECT json_object('id', id, 'path', path, 'repo', repo_origin_url, 'kind', kind, 'config', json(config)) FROM projects WHERE id='wb-core';")" || return 1
	[[ -n "$project_json" ]] || { printf 'blocked\n'; return 0; }
	expected_config="$(dcp_ao_wb_core_config_json)"
	rules="$(dcp_ao_wb_core_agent_rules)"
	if printf '%s' "$project_json" | /usr/bin/jq -e \
		--arg path "$lab_root/targets/wb-core" \
		--arg rules "$rules" \
		--argjson config "$expected_config" \
		'.id == "wb-core" and .path == $path and .repo == "https://github.com/orenvlad-ai/wb-core.git" and .kind == "single_repo" and .config == $config and .config.agentRules == $rules' \
		>/dev/null 2>&1; then
		printf 'qualified\n'
	else
		printf 'blocked\n'
	fi
}

dcp_ao_require_wb_core_compatibility() {
	local target="$1" status
	status="$(dcp_ao_wb_core_compatibility_status "$target")" || return 1
	[[ "$status" == qualified ]] || {
		dcp_ao_fail 'wb-core compatibility gate is blocked: repository-owned marker wb-core.dcp-release-handoff/v1 is absent or incomplete';
		return 1;
	}
}

dcp_ao_validate_future_review_worktree() {
	local lab_root="$1" path="$2" branch="$3" session_id="$4" number database table_count row_count
	[[ "$session_id" =~ ^dcp-review-lab-([1-9][0-9]*)$ ]] || return 1
	number="${BASH_REMATCH[1]}"
	[[ "$number" -gt 12 && "$path" == "$lab_root/data/worktrees/dcp-review-lab/$session_id" && \
		"$branch" == "refs/heads/ao/$session_id/root" ]] || return 1
	database="$lab_root/data/ao.db"
	[[ -f "$database" ]] || { dcp_ao_fail 'future dcp-review-lab worktree has no durable policy authority'; return 1; }
	table_count="$(sqlite3 -readonly -batch -noheader "$database" \
		"SELECT count(*) FROM sqlite_master WHERE type='table' AND name='dcp_review_lab_policy_task';")" || return 1
	[[ "$table_count" == 1 ]] || { dcp_ao_fail 'future dcp-review-lab policy schema is unavailable'; return 1; }
	row_count="$(sqlite3 -readonly -batch -noheader "$database" \
		"SELECT count(*) FROM dcp_review_lab_policy_task WHERE session_id='$session_id' AND card_number=$number AND worktree_path='$path' AND source_branch='ao/$session_id/root' AND target='dcp-review-lab' AND profile='synthetic-pr' AND repository='orenvlad-ai/dcp-review-lab' AND policy_version='dcp.review-lab.happy-path/v1';")" || return 1
	[[ "$row_count" == 1 ]] || { dcp_ao_fail 'future dcp-review-lab worktree lacks one exact durable policy row'; return 1; }
}

dcp_ao_validate_review_worktree() {
	local lab_root="$1" target="$2" path="$3" head="$4" branch="$5"
	local expected_root="$lab_root/data/worktrees/dcp-review-lab" session_id
	[[ "$head" =~ ^[0-9a-f]{40}$ ]] || { dcp_ao_fail "dcp-review-lab worktree has invalid HEAD: $path"; return 1; }
	if [[ "$path" == "$target" ]]; then
		[[ "$branch" == refs/heads/main ]] || { dcp_ao_fail 'dcp-review-lab baseline worktree is not on main'; return 1; }
		return 0
	fi
	case "$path|$branch" in
		"$expected_root/dcp-review-lab-1|refs/heads/ao/dcp-review-canary/root"|\
		"$expected_root/dcp-review-lab-2|refs/heads/ao/dcp-verdict-canary/root"|\
		"$expected_root/dcp-review-lab-3|refs/heads/ao/dcp-i4-verdict/root"|\
		"$expected_root/dcp-review-lab-4|refs/heads/ao/dcp-review-lab-4/root"|\
		"$expected_root/dcp-review-lab-5|refs/heads/ao/dcp-review-lab-5/root") ;;
		*)
			case "$path" in
				"$expected_root"/dcp-review-lab-*)
					session_id="${path##*/}"
					if [[ "$session_id" =~ ^dcp-review-lab-([6-9]|1[0-2])$ ]]; then
						[[ "$branch" == "refs/heads/ao/$session_id/root" ]] || {
							dcp_ao_fail "dcp-review-lab linked worktree identity mismatch: $path"; return 1;
						}
					else
						dcp_ao_validate_future_review_worktree "$lab_root" "$path" "$branch" "$session_id" || {
							dcp_ao_fail "dcp-review-lab linked worktree identity mismatch: $path"; return 1;
						}
					fi
					;;
				*) dcp_ao_fail "dcp-review-lab has a foreign linked worktree: $path"; return 1 ;;
			esac
			;;
	esac
	[[ -e "$path/.git" && "$(cd "$path" && pwd -P)" == "$path" ]] || { dcp_ao_fail "dcp-review-lab linked worktree path is unsafe: $path"; return 1; }
	[[ "$(git -C "$path" rev-parse --show-toplevel)" == "$path" ]] || { dcp_ao_fail "dcp-review-lab linked worktree root mismatch: $path"; return 1; }
	[[ "$(git -C "$path" rev-parse --path-format=absolute --git-common-dir)" == "$target/.git" ]] || { dcp_ao_fail "dcp-review-lab linked common git dir mismatch: $path"; return 1; }
	[[ "$(git -C "$path" rev-parse --absolute-git-dir)" == "$target/.git/worktrees/${path##*/}" ]] || { dcp_ao_fail "dcp-review-lab linked private git dir mismatch: $path"; return 1; }
}

dcp_ao_validate_review_worktrees() {
	local lab_root="$1" target="$2" path='' head='' branch='' base_count=0 line
	while IFS= read -r line || [[ -n "$line" ]]; do
		case "$line" in
			worktree\ *)
				[[ -z "$path" ]] || { dcp_ao_fail 'malformed dcp-review-lab worktree list'; return 1; }
				path="${line#worktree }"
				;;
			HEAD\ *) head="${line#HEAD }" ;;
			branch\ *) branch="${line#branch }" ;;
			'')
				[[ -n "$path" && -n "$head" && -n "$branch" ]] || { dcp_ao_fail 'incomplete dcp-review-lab worktree identity'; return 1; }
				dcp_ao_validate_review_worktree "$lab_root" "$target" "$path" "$head" "$branch" || return 1
				if [[ "$path" == "$target" ]]; then base_count=$((base_count + 1)); fi
				path=''; head=''; branch=''
				;;
			*) dcp_ao_fail "unexpected dcp-review-lab worktree metadata: $line"; return 1 ;;
		esac
	done < <(git -C "$target" worktree list --porcelain)
	[[ -z "$path" && "$base_count" -eq 1 ]] || { dcp_ao_fail 'dcp-review-lab baseline worktree identity is ambiguous'; return 1; }
}

dcp_ao_validate_review_target() {
	local lab_root="$1" refresh="${2:-0}" resolved head remote_head
	local target="$lab_root/targets/dcp-review-lab"
	[[ -d "$target/.git" ]] || { dcp_ao_fail 'exact dcp-review-lab target is absent'; return 1; }
	resolved="$(cd "$target" && pwd -P)"
	[[ "$resolved" == "$target" && "$(git -C "$target" rev-parse --show-toplevel)" == "$target" ]] || { dcp_ao_fail 'dcp-review-lab repository path mismatch'; return 1; }
	dcp_ao_validate_review_provider_identity || return 1
	[[ "$(git -C "$target" remote)" == origin ]] || { dcp_ao_fail 'dcp-review-lab must have exactly one origin remote'; return 1; }
	[[ "$(git -C "$target" remote get-url origin)" == 'https://github.com/orenvlad-ai/dcp-review-lab.git' ]] || { dcp_ao_fail 'dcp-review-lab fetch URL mismatch'; return 1; }
	[[ "$(git -C "$target" remote get-url --push origin)" == 'https://github.com/orenvlad-ai/dcp-review-lab.git' ]] || { dcp_ao_fail 'dcp-review-lab push URL mismatch'; return 1; }
	[[ "$(git -C "$target" branch --show-current)" == main ]] || { dcp_ao_fail 'dcp-review-lab baseline branch must be main'; return 1; }
	[[ -z "$(git -C "$target" status --porcelain)" ]] || { dcp_ao_fail 'dcp-review-lab baseline must be clean'; return 1; }
	if [[ "$refresh" == 1 ]]; then dcp_ao_refresh_review_target "$target" || return 1; fi
	remote_head="$(git -C "$target" rev-parse --verify refs/remotes/origin/main 2>/dev/null)" || { dcp_ao_fail 'dcp-review-lab origin/main is absent'; return 1; }
	head="$(git -C "$target" rev-parse HEAD)"
	if [[ "$head" != "$remote_head" ]]; then
		[[ "$refresh" == 1 ]] || { dcp_ao_fail 'dcp-review-lab baseline changed while submission was locked'; return 1; }
		git -C "$target" merge-base --is-ancestor "$head" "$remote_head" || { dcp_ao_fail 'dcp-review-lab main diverged from origin/main'; return 1; }
		git -C "$target" merge --ff-only "$remote_head" >/dev/null || { dcp_ao_fail 'dcp-review-lab main could not fast-forward'; return 1; }
		head="$(git -C "$target" rev-parse HEAD)"
	fi
	[[ "$head" == "$remote_head" && -z "$(git -C "$target" status --porcelain)" ]] || { dcp_ao_fail 'dcp-review-lab clean base identity changed'; return 1; }
	dcp_ao_validate_review_worktrees "$lab_root" "$target" || return 1
	printf '%s\n' "$resolved"
}

dcp_ao_repo_only_policy_scalar() {
	local lab_root="$1" query="$2" database result app_pid app_pid_result=0
	database="$lab_root/data/ao.db"
	if result="$(sqlite3 -readonly -batch -noheader "$database" "$query" 2>/dev/null)"; then
		printf '%s\n' "$result"
		return 0
	fi
	[[ -f "$database" && ! -L "$database" && \
		"$(cd "$(dirname "$database")" && pwd -P)/${database##*/}" == "$database" ]] || {
		dcp_ao_fail 'repo-only policy database path is unsafe'; return 1;
	}
	app_pid="$(dcp_ao_gateway_exact_app_pid "$lab_root" 2>/dev/null)" || app_pid_result=$?
	[[ "$app_pid_result" -eq 1 && -z "$app_pid" ]] || {
		dcp_ao_fail 'repo-only immutable policy read requires the exact app to be stopped'; return 1;
	}
	if dcp_ao_gateway_port_occupied; then
		dcp_ao_fail 'repo-only immutable policy read requires an unoccupied canonical port'; return 1
	fi
	[[ ! -e "$database-wal" && ! -e "$database-shm" ]] || {
		dcp_ao_fail 'repo-only immutable policy read requires absent SQLite sidecars'; return 1;
	}
	case "$database" in
		*'?'*|*'#'*) dcp_ao_fail 'repo-only policy database path is not URI-safe'; return 1 ;;
	esac
	result="$(sqlite3 -batch -noheader "file:$database?mode=ro&immutable=1" "$query" 2>/dev/null)" || {
		dcp_ao_fail 'repo-only immutable policy read failed'; return 1;
	}
	printf '%s\n' "$result"
}

dcp_ao_validate_future_repo_only_worktree() {
	local lab_root="$1" path="$2" branch="$3" session_id="$4" number database table_count row_count
	[[ "$session_id" =~ ^wb-browser-extension-([1-9][0-9]*)$ ]] || return 1
	number="${BASH_REMATCH[1]}"
	[[ "$path" == "$lab_root/data/worktrees/wb-browser-extension/$session_id" && \
		"$branch" == "refs/heads/ao/$session_id/root" ]] || return 1
	database="$lab_root/data/ao.db"
	[[ -f "$database" ]] || { dcp_ao_fail 'wb-browser-extension worktree has no durable policy authority'; return 1; }
	table_count="$(dcp_ao_repo_only_policy_scalar "$lab_root" \
		"SELECT count(*) FROM sqlite_master WHERE type='table' AND name='dcp_review_lab_policy_task';")" || return 1
	[[ "$table_count" == 1 ]] || { dcp_ao_fail 'repo-only policy schema is unavailable'; return 1; }
	row_count="$(dcp_ao_repo_only_policy_scalar "$lab_root" \
		"SELECT count(*) FROM dcp_review_lab_policy_task WHERE session_id='$session_id' AND card_number=$number AND worktree_path='$path' AND source_branch='ao/$session_id/root' AND target='wb-browser-extension' AND profile='repo-only' AND repository='orenvlad-ai/wb-browser-extension' AND policy_version='dcp.repo-only.happy-path/v1';")" || return 1
	[[ "$row_count" == 1 ]] || { dcp_ao_fail 'wb-browser-extension worktree lacks one exact durable policy row'; return 1; }
}

dcp_ao_validate_legacy_repo_only_worktree() {
	local lab_root="$1" path="$2" branch="$3" row_count
	[[ "$path" == "$lab_root/data/worktrees/wb-price-extension/wb-price-extension-1" && \
		"$branch" == refs/heads/ao/wb-price-extension-1/root ]] || return 1
	row_count="$(dcp_ao_repo_only_policy_scalar "$lab_root" \
		"SELECT count(*) FROM dcp_review_lab_policy_task WHERE task_id='price-arch-v1' AND payload_digest='efe6a81cfff28be89cc327bdc9e2380ca585fcc6b03064c0290b6aaf4c7b59fe' AND target='wb-price-extension' AND profile='repo-only' AND repository='orenvlad-ai/wb-price-extension' AND policy_version='dcp.repo-only.happy-path/v1' AND session_id='wb-price-extension-1' AND card_number=1 AND worktree_path='$path' AND source_branch='ao/wb-price-extension-1/root' AND state='merged' AND revision=7 AND repair_count=0 AND pr_url='https://github.com/orenvlad-ai/wb-price-extension/pull/1' AND pr_number=1 AND current_head_sha='afc748eba5ff05c0dc24d3002c690ec9f44984fb' AND previous_head_sha='' AND review_run_id='b0acfb9e-600c-4816-bb2f-02a67817ea05' AND admission_id='dcp-admission-b0acfb9e-600c-4816-bb2f-02a67817ea05' AND merge_commit_sha='62853496837f64522bb08ba56169f60f3b0f9a2c' AND error_code='' AND incident_packet='';")" || return 1
	[[ "$row_count" == 1 ]] || { dcp_ao_fail 'legacy wb-price-extension worktree lacks the exact terminal policy row'; return 1; }
}

dcp_ao_validate_repo_only_worktree() {
	local lab_root="$1" target="$2" path="$3" head="$4" branch="$5" session_id
	local expected_root="$lab_root/data/worktrees/wb-browser-extension"
	[[ "$head" =~ ^[0-9a-f]{40}$ ]] || { dcp_ao_fail "wb-browser-extension worktree has invalid HEAD: $path"; return 1; }
	if [[ "$path" == "$target" ]]; then
		[[ "$branch" == refs/heads/main ]] || { dcp_ao_fail 'wb-browser-extension baseline worktree is not on main'; return 1; }
		return 0
	fi
	case "$path|$branch" in
		"$lab_root/data/worktrees/wb-price-extension/wb-price-extension-1|refs/heads/ao/wb-price-extension-1/root")
			dcp_ao_validate_legacy_repo_only_worktree "$lab_root" "$path" "$branch" || {
				dcp_ao_fail "legacy wb-price-extension linked worktree identity mismatch: $path"; return 1;
			}
			;;
		"$expected_root"/wb-browser-extension-*\|*)
			session_id="${path##*/}"
			dcp_ao_validate_future_repo_only_worktree "$lab_root" "$path" "$branch" "$session_id" || {
				dcp_ao_fail "wb-browser-extension linked worktree identity mismatch: $path"; return 1;
			}
			;;
		*) dcp_ao_fail "wb-browser-extension has a foreign linked worktree: $path"; return 1 ;;
	esac
	[[ -e "$path/.git" && "$(cd "$path" && pwd -P)" == "$path" ]] || { dcp_ao_fail "wb-browser-extension linked worktree path is unsafe: $path"; return 1; }
	[[ "$(git -C "$path" rev-parse --show-toplevel)" == "$path" ]] || { dcp_ao_fail "wb-browser-extension linked worktree root mismatch: $path"; return 1; }
	[[ "$(git -C "$path" rev-parse --path-format=absolute --git-common-dir)" == "$target/.git" ]] || { dcp_ao_fail "wb-browser-extension linked common git dir mismatch: $path"; return 1; }
	[[ "$(git -C "$path" rev-parse --absolute-git-dir)" == "$target/.git/worktrees/${path##*/}" ]] || { dcp_ao_fail "wb-browser-extension linked private git dir mismatch: $path"; return 1; }
}

dcp_ao_validate_repo_only_worktrees() {
	local lab_root="$1" target="$2" path='' head='' branch='' base_count=0 line
	while IFS= read -r line || [[ -n "$line" ]]; do
		case "$line" in
			worktree\ *)
				[[ -z "$path" ]] || { dcp_ao_fail 'malformed wb-browser-extension worktree list'; return 1; }
				path="${line#worktree }"
				;;
			HEAD\ *) head="${line#HEAD }" ;;
			branch\ *) branch="${line#branch }" ;;
			'')
				[[ -n "$path" && -n "$head" && -n "$branch" ]] || { dcp_ao_fail 'incomplete wb-browser-extension worktree identity'; return 1; }
				dcp_ao_validate_repo_only_worktree "$lab_root" "$target" "$path" "$head" "$branch" || return 1
				if [[ "$path" == "$target" ]]; then base_count=$((base_count + 1)); fi
				path=''; head=''; branch=''
				;;
			*) dcp_ao_fail "unexpected wb-browser-extension worktree metadata: $line"; return 1 ;;
		esac
	done < <(git -C "$target" worktree list --porcelain)
	[[ -z "$path" && "$base_count" -eq 1 ]] || { dcp_ao_fail 'wb-browser-extension baseline worktree identity is ambiguous'; return 1; }
}

dcp_ao_validate_repo_only_target() {
	local lab_root="$1" refresh="${2:-0}" resolved head remote_head tracked
	local target="$lab_root/targets/wb-browser-extension"
	[[ -d "$target/.git" ]] || { dcp_ao_fail 'exact wb-browser-extension target is absent'; return 1; }
	resolved="$(cd "$target" && pwd -P)"
	[[ "$resolved" == "$target" && "$(git -C "$target" rev-parse --show-toplevel)" == "$target" ]] || { dcp_ao_fail 'wb-browser-extension repository path mismatch'; return 1; }
	dcp_ao_validate_repo_only_provider_identity || return 1
	[[ "$(git -C "$target" remote)" == origin ]] || { dcp_ao_fail 'wb-browser-extension must have exactly one origin remote'; return 1; }
	[[ "$(git -C "$target" remote get-url origin)" == 'https://github.com/orenvlad-ai/wb-browser-extension.git' ]] || { dcp_ao_fail 'wb-browser-extension fetch URL mismatch'; return 1; }
	[[ "$(git -C "$target" remote get-url --push origin)" == 'https://github.com/orenvlad-ai/wb-browser-extension.git' ]] || { dcp_ao_fail 'wb-browser-extension push URL mismatch'; return 1; }
	[[ "$(git -C "$target" branch --show-current)" == main ]] || { dcp_ao_fail 'wb-browser-extension baseline branch must be main'; return 1; }
	[[ -z "$(git -C "$target" status --porcelain)" ]] || { dcp_ao_fail 'wb-browser-extension baseline must be clean'; return 1; }
	for tracked in AGENTS.md README.md docs/PROJECT_BRIEF.md docs/ARCHITECTURE.md .github/workflows/baseline.yml scripts/baseline.sh; do
		git -C "$target" ls-files --error-unmatch "$tracked" >/dev/null 2>&1 || { dcp_ao_fail "wb-browser-extension required baseline file is absent: $tracked"; return 1; }
	done
	[[ -x "$target/scripts/baseline.sh" ]] || { dcp_ao_fail 'wb-browser-extension baseline verifier is not executable'; return 1; }
	if [[ "$refresh" == 1 ]]; then dcp_ao_refresh_repo_only_target "$target" || return 1; fi
	remote_head="$(git -C "$target" rev-parse --verify refs/remotes/origin/main 2>/dev/null)" || { dcp_ao_fail 'wb-browser-extension origin/main is absent'; return 1; }
	head="$(git -C "$target" rev-parse HEAD)"
	if [[ "$head" != "$remote_head" ]]; then
		[[ "$refresh" == 1 ]] || { dcp_ao_fail 'wb-browser-extension baseline changed while submission was locked'; return 1; }
		git -C "$target" merge-base --is-ancestor "$head" "$remote_head" || { dcp_ao_fail 'wb-browser-extension main diverged from origin/main'; return 1; }
		git -C "$target" merge --ff-only "$remote_head" >/dev/null || { dcp_ao_fail 'wb-browser-extension main could not fast-forward'; return 1; }
		head="$(git -C "$target" rev-parse HEAD)"
	fi
	[[ "$head" == "$remote_head" && -z "$(git -C "$target" status --porcelain)" ]] || { dcp_ao_fail 'wb-browser-extension clean base identity changed'; return 1; }
	dcp_ao_validate_repo_only_worktrees "$lab_root" "$target" || return 1
	(cd "$target" && ./scripts/baseline.sh) >/dev/null || { dcp_ao_fail 'wb-browser-extension model-free baseline failed'; return 1; }
	printf '%s\n' "$resolved"
}

dcp_ao_validate_future_wb_core_worktree() {
	local lab_root="$1" path="$2" branch="$3" session_id="$4" number table_count row_count
	[[ "$session_id" =~ ^wb-core-([1-9][0-9]*)$ ]] || return 1
	number="${BASH_REMATCH[1]}"
	[[ "$path" == "$lab_root/data/worktrees/wb-core/$session_id" && \
		"$branch" == "refs/heads/ao/$session_id/root" ]] || return 1
	table_count="$(dcp_ao_repo_only_policy_scalar "$lab_root" \
		"SELECT count(*) FROM sqlite_master WHERE type='table' AND name='dcp_review_lab_policy_task';")" || return 1
	[[ "$table_count" == 1 ]] || { dcp_ao_fail 'wb-core policy schema is unavailable'; return 1; }
	row_count="$(dcp_ao_repo_only_policy_scalar "$lab_root" \
		"SELECT count(*) FROM dcp_review_lab_policy_task WHERE session_id='$session_id' AND card_number=$number AND worktree_path='$path' AND source_branch='ao/$session_id/root' AND target='wb-core' AND profile='repo-only' AND repository='orenvlad-ai/wb-core' AND policy_version='dcp.wb-core.repo-only.release-train/v1';")" || return 1
	[[ "$row_count" == 1 ]] || { dcp_ao_fail 'wb-core worktree lacks one exact durable policy row'; return 1; }
}

dcp_ao_validate_wb_core_worktree() {
	local lab_root="$1" target="$2" path="$3" head="$4" branch="$5" session_id
	[[ "$head" =~ ^[0-9a-f]{40}$ ]] || { dcp_ao_fail "wb-core worktree has invalid HEAD: $path"; return 1; }
	if [[ "$path" == "$target" ]]; then
		[[ "$branch" == refs/heads/main ]] || { dcp_ao_fail 'wb-core baseline worktree is not on main'; return 1; }
		return 0
	fi
	session_id="${path##*/}"
	dcp_ao_validate_future_wb_core_worktree "$lab_root" "$path" "$branch" "$session_id" || {
		dcp_ao_fail "wb-core linked worktree identity mismatch: $path"; return 1;
	}
	[[ -e "$path/.git" && "$(cd "$path" && pwd -P)" == "$path" ]] || { dcp_ao_fail "wb-core linked worktree path is unsafe: $path"; return 1; }
	[[ "$(git -C "$path" rev-parse --show-toplevel)" == "$path" ]] || { dcp_ao_fail "wb-core linked worktree root mismatch: $path"; return 1; }
	[[ "$(git -C "$path" rev-parse --path-format=absolute --git-common-dir)" == "$target/.git" ]] || { dcp_ao_fail "wb-core linked common git dir mismatch: $path"; return 1; }
	[[ "$(git -C "$path" rev-parse --absolute-git-dir)" == "$target/.git/worktrees/${path##*/}" ]] || { dcp_ao_fail "wb-core linked private git dir mismatch: $path"; return 1; }
}

dcp_ao_validate_wb_core_worktrees() {
	local lab_root="$1" target="$2" path='' head='' branch='' base_count=0 line
	while IFS= read -r line || [[ -n "$line" ]]; do
		case "$line" in
			worktree\ *)
				[[ -z "$path" ]] || { dcp_ao_fail 'malformed wb-core worktree list'; return 1; }
				path="${line#worktree }"
				;;
			HEAD\ *) head="${line#HEAD }" ;;
			branch\ *) branch="${line#branch }" ;;
			'')
				[[ -n "$path" && -n "$head" && -n "$branch" ]] || { dcp_ao_fail 'incomplete wb-core worktree identity'; return 1; }
				dcp_ao_validate_wb_core_worktree "$lab_root" "$target" "$path" "$head" "$branch" || return 1
				if [[ "$path" == "$target" ]]; then base_count=$((base_count + 1)); fi
				path=''; head=''; branch=''
				;;
			*) dcp_ao_fail "unexpected wb-core worktree metadata: $line"; return 1 ;;
		esac
	done < <(git -C "$target" worktree list --porcelain)
	[[ -z "$path" && "$base_count" -eq 1 ]] || { dcp_ao_fail 'wb-core baseline worktree identity is ambiguous'; return 1; }
}

dcp_ao_validate_wb_core_target() {
	local lab_root="$1" refresh="${2:-0}" resolved head remote_head tracked
	local target="$lab_root/targets/wb-core"
	[[ -d "$target/.git" ]] || { dcp_ao_fail 'exact wb-core target is absent; run bin/dcp-ao init-wb-core'; return 1; }
	resolved="$(cd "$target" && pwd -P)"
	[[ "$resolved" == "$target" && "$(git -C "$target" rev-parse --show-toplevel)" == "$target" ]] || { dcp_ao_fail 'wb-core repository path mismatch'; return 1; }
	dcp_ao_validate_wb_core_provider_identity || return 1
	[[ "$(git -C "$target" remote)" == origin ]] || { dcp_ao_fail 'wb-core must have exactly one origin remote'; return 1; }
	[[ "$(git -C "$target" remote get-url origin)" == 'https://github.com/orenvlad-ai/wb-core.git' ]] || { dcp_ao_fail 'wb-core fetch URL mismatch'; return 1; }
	[[ "$(git -C "$target" remote get-url --push origin)" == 'https://github.com/orenvlad-ai/wb-core.git' ]] || { dcp_ao_fail 'wb-core push URL mismatch'; return 1; }
	[[ "$(git -C "$target" branch --show-current)" == main ]] || { dcp_ao_fail 'wb-core baseline worktree is not on main'; return 1; }
	[[ -z "$(git -C "$target" status --porcelain)" ]] || { dcp_ao_fail 'wb-core baseline must be clean'; return 1; }
	for tracked in AGENTS.md .github/workflows/baseline-ci.yml docs/architecture/11_github_release_train.md apps/github_release_train.py apps/github_release_train_spec.py apps/github_release_train_smoke.py; do
		git -C "$target" ls-files --error-unmatch "$tracked" >/dev/null 2>&1 || { dcp_ao_fail "wb-core required Release Train file is absent: $tracked"; return 1; }
	done
	if [[ "$refresh" == 1 ]]; then dcp_ao_refresh_wb_core_target "$target" || return 1; fi
	remote_head="$(git -C "$target" rev-parse --verify refs/remotes/origin/main 2>/dev/null)" || { dcp_ao_fail 'wb-core origin/main is absent'; return 1; }
	head="$(git -C "$target" rev-parse HEAD)"
	if [[ "$head" != "$remote_head" ]]; then
		[[ "$refresh" == 1 ]] || { dcp_ao_fail 'wb-core baseline changed while submission was locked'; return 1; }
		git -C "$target" merge-base --is-ancestor "$head" "$remote_head" || { dcp_ao_fail 'wb-core main diverged from origin/main'; return 1; }
		git -C "$target" merge --ff-only "$remote_head" >/dev/null || { dcp_ao_fail 'wb-core main could not fast-forward'; return 1; }
		head="$(git -C "$target" rev-parse HEAD)"
	fi
	[[ "$head" == "$remote_head" && -z "$(git -C "$target" status --porcelain)" ]] || { dcp_ao_fail 'wb-core clean base identity changed'; return 1; }
	dcp_ao_validate_wb_core_worktrees "$lab_root" "$target" || return 1
	python3 -c 'import ast, pathlib, sys; [ast.parse(pathlib.Path(path).read_text(encoding="utf-8"), filename=path) for path in sys.argv[1:]]' \
		"$target/apps/github_release_train.py" \
		"$target/apps/github_release_train_spec.py" \
		"$target/apps/github_release_train_smoke.py" || { dcp_ao_fail 'wb-core Release Train syntax check failed'; return 1; }
	printf '%s\n' "$resolved"
}

dcp_ao_init_wb_core_target() {
	local lab_root="$1" target="$lab_root/targets/wb-core"
	if [[ ! -e "$target" ]]; then
		mkdir -p "$(dirname "$target")"
		git clone --origin origin --branch main --single-branch https://github.com/orenvlad-ai/wb-core.git "$target" >/dev/null || {
			dcp_ao_fail 'wb-core read-only baseline clone failed'; return 1;
		}
	fi
	[[ "$(dcp_ao_validate_wb_core_target "$lab_root" 1)" == "$target" ]] || return 1
	printf 'wb_core_target=%s\nwb_core_compatibility=%s\n' "$target" "$(dcp_ao_wb_core_compatibility_status "$target")"
}

dcp_ao_resolve_cli() {
	local lab_root="$1"
	dcp_ao_preflight_exact_contour "$lab_root"
	local cli
	cli="$(dcp_ao_embedded_cli)"
	if [[ ! -x "$cli" ]]; then dcp_ao_fail 'packaged DCP daemon/CLI is absent'; return 1; fi
	printf '%s\n' "$cli"
}

dcp_ao_submit_locked() {
	local lab_root="$1" cli="$2" target_name="$3" profile="$4" task_id="$5" target="$6" prompt="$7"
	local status projects details spawn_output session_id
	# Fetch and fast-forward an exact PR-capable baseline only while the
	# canonical submit lock is held. Concurrent typed submits otherwise race
	# between the pre-lock refresh and this identity check.
	case "$target_name" in
		dcp-review-lab) [[ "$(dcp_ao_validate_review_target "$lab_root" 1)" == "$target" ]] || return 1 ;;
		wb-browser-extension) [[ "$(dcp_ao_validate_repo_only_target "$lab_root" 1)" == "$target" ]] || return 1 ;;
		wb-core)
			[[ "$(dcp_ao_validate_wb_core_target "$lab_root" 1)" == "$target" ]] || return 1
			dcp_ao_require_wb_core_compatibility "$target" || return 1
			;;
		dcp-lab) [[ "$(dcp_ao_validate_remote_free_target "$lab_root")" == "$target" ]] || return 1 ;;
		*) dcp_ao_fail 'submission target escaped the exact allowlist'; return 1 ;;
	esac
	dcp_ao_gateway_ensure_locked "$lab_root" "$cli" || return 1
	dcp_ao_export_runtime_env "$lab_root"
	dcp_ao_preflight_codex_worker "$lab_root" || return 1
	status="$("$cli" status --json)"
	if ! printf '%s' "$status" | grep -Fq '"state": "ready"'; then dcp_ao_fail 'isolated AO daemon is not ready'; return 1; fi
	dcp_ao_gateway_assert_pair "$lab_root" "$status" || return 1

	if [[ "$target_name" == dcp-review-lab ]]; then
		dcp_ao_prepare_review_project "$cli" "$target" || return 1
		spawn_output="$("$cli" dcp submit --target dcp-review-lab --profile synthetic-pr \
			--repository orenvlad-ai/dcp-review-lab --task-id "$task_id" --prompt "$prompt" --json)" || return 1
		dcp_ao_validate_policy_submit_response "$lab_root" "$task_id" dcp-review-lab synthetic-pr "$spawn_output" || return 1
	elif [[ "$target_name" == wb-browser-extension ]]; then
		dcp_ao_prepare_repo_only_project "$cli" "$target" || return 1
		spawn_output="$("$cli" dcp submit --target wb-browser-extension --profile repo-only \
			--repository orenvlad-ai/wb-browser-extension --task-id "$task_id" --prompt "$prompt" --json)" || return 1
		dcp_ao_validate_policy_submit_response "$lab_root" "$task_id" wb-browser-extension repo-only "$spawn_output" || return 1
	elif [[ "$target_name" == wb-core ]]; then
		dcp_ao_prepare_wb_core_project "$cli" "$target" || return 1
		spawn_output="$("$cli" dcp submit --target wb-core --profile repo-only \
			--repository orenvlad-ai/wb-core --task-id "$task_id" --prompt "$prompt" --json)" || return 1
		dcp_ao_validate_policy_submit_response "$lab_root" "$task_id" wb-core repo-only "$spawn_output" || return 1
	else
		projects="$("$cli" project ls --json)"
		if ! printf '%s' "$projects" | grep -Fq '"id": "dcp-lab"'; then
			"$cli" project add --id dcp-lab --name 'DCP Lab' --path "$target" --worker-agent codex
		else
			details="$("$cli" project get dcp-lab --json)"
			if ! printf '%s' "$details" | grep -Fq "\"path\": \"$target\""; then dcp_ao_fail 'AO dcp-lab project points at another path'; return 1; fi
		fi
		"$cli" project set-config dcp-lab --config-json \
			'{"defaultBranch":"main","sessionPrefix":"dcp-i8","worker":{"agent":"codex","agentConfig":{"permissions":"bypass-permissions"}},"agentRules":"Synthetic remote-free DCP lab only. Do not create subagents, commits, branches beyond the DCP workspace branch, remotes, pushes, pull requests, or network services. Make only the exact file mutation requested by the direct task prompt and then report the result."}'
		spawn_output="$("$cli" spawn --project dcp-lab --kind worker --name 'DCP I8 Task' --harness codex --prompt "$prompt")"
	fi
	if [[ "$target_name" == dcp-review-lab || "$target_name" == wb-browser-extension || "$target_name" == wb-core ]]; then
		return 0
	fi
	printf '%s\n' "$spawn_output"
	session_id="$(printf '%s\n' "$spawn_output" | sed -n 's/^spawned session \([^ ]*\).*/\1/p')"
	if [[ -z "$session_id" ]]; then dcp_ao_fail 'AO did not return a session id'; return 1; fi
	printf 'session_id=%s\n' "$session_id"
}

dcp_ao_validate_policy_submit_response() {
	local lab_root="$1" task_id="$2" target_name="$3" profile="$4" response="$5"
	local session_id card_number worktree branch state revision duplicate minimum=1 repository
	case "$target_name|$profile" in
		dcp-review-lab\|synthetic-pr) repository=orenvlad-ai/dcp-review-lab ;;
		wb-browser-extension\|repo-only) repository=orenvlad-ai/wb-browser-extension ;;
		wb-core\|repo-only) repository=orenvlad-ai/wb-core ;;
		*) dcp_ao_fail 'policy submit response validator received a foreign tuple'; return 1 ;;
	esac
	printf '%s' "$response" | /usr/bin/jq -e '.task | type == "object"' >/dev/null 2>&1 || {
		dcp_ao_fail 'policy submit response was malformed'; return 1;
	}
	session_id="$(dcp_ao_json_extract "$response" task.sessionId)" || return 1
	card_number="$(dcp_ao_json_extract "$response" task.cardNumber)" || return 1
	worktree="$(dcp_ao_json_extract "$response" task.worktreePath)" || return 1
	branch="$(dcp_ao_json_extract "$response" task.sourceBranch)" || return 1
	state="$(dcp_ao_json_extract "$response" task.state)" || return 1
	revision="$(dcp_ao_json_extract "$response" task.revision)" || return 1
	duplicate="$(printf '%s' "$response" | /usr/bin/jq -er '.duplicate | if type == "boolean" then tostring else error("not boolean") end')" || return 1
	[[ "$(dcp_ao_json_extract "$response" task.taskId)" == "$task_id" && \
		"$(dcp_ao_json_extract "$response" task.target)" == "$target_name" && \
		"$(dcp_ao_json_extract "$response" task.profile)" == "$profile" && \
		"$(dcp_ao_json_extract "$response" task.repository)" == "$repository" ]] || {
		dcp_ao_fail 'policy submit immutable payload identity drifted'; return 1;
	}
	[[ "$target_name" != dcp-review-lab ]] || minimum=13
	[[ "$session_id" =~ ^${target_name}-([1-9][0-9]*)$ && "${BASH_REMATCH[1]}" == "$card_number" && "$card_number" -ge "$minimum" ]] || {
		dcp_ao_fail 'policy submit native card identity drifted'; return 1;
	}
	[[ "$worktree" == "$lab_root/data/worktrees/$target_name/$session_id" && \
		"$branch" == "ao/$session_id/root" && "$revision" =~ ^[1-9][0-9]*$ && \
		"$duplicate" =~ ^(true|false)$ && \
		"$state" =~ ^(reserved|worker_queued|worker_running|ci_waiting|review_queued|review_running|repair_queued|repair_running|admission_waiting|release_waiting|merged|failed|incident)$ ]] || {
		dcp_ao_fail 'policy submit mutable state identity drifted'; return 1;
	}
	printf 'profile=%s\ntask_id=%s\nsession_id=%s\ncard_number=%s\nworktree=%s\nbranch=%s\nstate=%s\nrevision=%s\nduplicate=%s\n' \
		"$profile" "$task_id" "$session_id" "$card_number" "$worktree" "$branch" "$state" "$revision" "$duplicate"
}

dcp_ao_prepare_review_project() {
	local cli="$1" target="$2" projects details index=0 project_id found=0 rules
	projects="$("$cli" project ls --json)" || return 1
	printf '%s' "$projects" | /usr/bin/jq -e '.projects | type == "array"' >/dev/null 2>&1 || { dcp_ao_fail 'AO project list was malformed'; return 1; }
	while project_id="$(dcp_ao_json_extract "$projects" "projects.$index.id")"; do
		if [[ "$project_id" == dcp-review-lab ]]; then found=$((found + 1)); fi
		index=$((index + 1))
	done
	[[ "$found" -le 1 ]] || { dcp_ao_fail 'AO has duplicate dcp-review-lab projects'; return 1; }
	if [[ "$found" -eq 0 ]]; then
		"$cli" project add --id dcp-review-lab --name 'DCP Review Lab' --path "$target" --worker-agent codex || return 1
	fi
	"$cli" project set-config dcp-review-lab --config-json "$(dcp_ao_review_config_json)" || return 1
	details="$("$cli" project get dcp-review-lab --json)" || return 1
	rules="$(dcp_ao_review_agent_rules)"
	[[ "$(dcp_ao_json_extract "$details" status)" == ok && \
		"$(dcp_ao_json_extract "$details" project.id)" == dcp-review-lab && \
		"$(dcp_ao_json_extract "$details" project.path)" == "$target" && \
		"$(dcp_ao_json_extract "$details" project.kind)" == single_repo && \
		"$(dcp_ao_json_extract "$details" project.repo)" == 'https://github.com/orenvlad-ai/dcp-review-lab.git' && \
		"$(dcp_ao_json_extract "$details" project.defaultBranch)" == main && \
		"$(dcp_ao_json_extract "$details" project.config.defaultBranch)" == main && \
		"$(dcp_ao_json_extract "$details" project.config.sessionPrefix)" == dcp-review-lab && \
		"$(dcp_ao_json_extract "$details" project.config.worker.agent)" == codex && \
		"$(dcp_ao_json_extract "$details" project.config.worker.agentConfig.permissions)" == accept-edits && \
		"$(dcp_ao_json_extract "$details" project.config.worker.agentConfig.dcpReviewLabNetwork)" == true && \
		"$(dcp_ao_json_extract "$details" project.config.reviewers.0.harness)" == codex && \
		"$(dcp_ao_json_extract "$details" project.config.agentRules)" == "$rules" ]] || { dcp_ao_fail 'AO dcp-review-lab project/profile identity mismatch'; return 1; }
	if dcp_ao_json_extract "$details" project.config.reviewers.1.harness >/dev/null; then
		dcp_ao_fail 'AO dcp-review-lab has an extra reviewer'
		return 1
	fi
}

dcp_ao_prepare_repo_only_project() {
	local cli="$1" target="$2" projects details index=0 project_id found=0 rules
	projects="$("$cli" project ls --json)" || return 1
	printf '%s' "$projects" | /usr/bin/jq -e '.projects | type == "array"' >/dev/null 2>&1 || { dcp_ao_fail 'AO project list was malformed'; return 1; }
	while project_id="$(dcp_ao_json_extract "$projects" "projects.$index.id")"; do
		if [[ "$project_id" == wb-browser-extension ]]; then found=$((found + 1)); fi
		index=$((index + 1))
	done
	[[ "$found" -le 1 ]] || { dcp_ao_fail 'AO has duplicate wb-browser-extension projects'; return 1; }
	if [[ "$found" -eq 0 ]]; then
		"$cli" project add --id wb-browser-extension --name 'WB Browser Extension' --path "$target" --worker-agent codex || return 1
	fi
	"$cli" project set-config wb-browser-extension --config-json "$(dcp_ao_repo_only_config_json)" || return 1
	details="$("$cli" project get wb-browser-extension --json)" || return 1
	rules="$(dcp_ao_repo_only_agent_rules)"
	[[ "$(dcp_ao_json_extract "$details" status)" == ok && \
		"$(dcp_ao_json_extract "$details" project.id)" == wb-browser-extension && \
		"$(dcp_ao_json_extract "$details" project.path)" == "$target" && \
		"$(dcp_ao_json_extract "$details" project.kind)" == single_repo && \
		"$(dcp_ao_json_extract "$details" project.repo)" == 'https://github.com/orenvlad-ai/wb-browser-extension.git' && \
		"$(dcp_ao_json_extract "$details" project.defaultBranch)" == main && \
		"$(dcp_ao_json_extract "$details" project.config.defaultBranch)" == main && \
		"$(dcp_ao_json_extract "$details" project.config.sessionPrefix)" == wb-browser-extension && \
		"$(dcp_ao_json_extract "$details" project.config.worker.agent)" == codex && \
		"$(dcp_ao_json_extract "$details" project.config.worker.agentConfig.permissions)" == accept-edits && \
		"$(dcp_ao_json_extract "$details" project.config.worker.agentConfig.dcpReviewLabNetwork)" == true && \
		"$(dcp_ao_json_extract "$details" project.config.reviewers.0.harness)" == codex && \
		"$(dcp_ao_json_extract "$details" project.config.agentRules)" == "$rules" ]] || { dcp_ao_fail 'AO wb-browser-extension project/profile identity mismatch'; return 1; }
	if dcp_ao_json_extract "$details" project.config.reviewers.1.harness >/dev/null; then
		dcp_ao_fail 'AO wb-browser-extension has an extra reviewer'
		return 1
	fi
}

dcp_ao_prepare_wb_core_project() {
	local cli="$1" target="$2" projects details index=0 project_id found=0 rules
	projects="$("$cli" project ls --json)" || return 1
	printf '%s' "$projects" | /usr/bin/jq -e '.projects | type == "array"' >/dev/null 2>&1 || { dcp_ao_fail 'AO project list was malformed'; return 1; }
	while project_id="$(dcp_ao_json_extract "$projects" "projects.$index.id")"; do
		if [[ "$project_id" == wb-core ]]; then found=$((found + 1)); fi
		index=$((index + 1))
	done
	[[ "$found" -le 1 ]] || { dcp_ao_fail 'AO has duplicate wb-core projects'; return 1; }
	if [[ "$found" -eq 0 ]]; then
		"$cli" project add --id wb-core --name 'WB Core' --path "$target" --worker-agent codex || return 1
	fi
	"$cli" project set-config wb-core --config-json "$(dcp_ao_wb_core_config_json)" || return 1
	details="$("$cli" project get wb-core --json)" || return 1
	rules="$(dcp_ao_wb_core_agent_rules)"
	[[ "$(dcp_ao_json_extract "$details" status)" == ok && \
		"$(dcp_ao_json_extract "$details" project.id)" == wb-core && \
		"$(dcp_ao_json_extract "$details" project.path)" == "$target" && \
		"$(dcp_ao_json_extract "$details" project.kind)" == single_repo && \
		"$(dcp_ao_json_extract "$details" project.repo)" == 'https://github.com/orenvlad-ai/wb-core.git' && \
		"$(dcp_ao_json_extract "$details" project.defaultBranch)" == main && \
		"$(dcp_ao_json_extract "$details" project.config.defaultBranch)" == main && \
		"$(dcp_ao_json_extract "$details" project.config.sessionPrefix)" == wb-core && \
		"$(dcp_ao_json_extract "$details" project.config.worker.agent)" == codex && \
		"$(dcp_ao_json_extract "$details" project.config.worker.agentConfig.permissions)" == accept-edits && \
		"$(dcp_ao_json_extract "$details" project.config.worker.agentConfig.dcpReviewLabNetwork)" == true && \
		"$(dcp_ao_json_extract "$details" project.config.reviewers.0.harness)" == codex && \
		"$(dcp_ao_json_extract "$details" project.config.agentRules)" == "$rules" ]] || { dcp_ao_fail 'AO wb-core project/profile identity mismatch'; return 1; }
	if dcp_ao_json_extract "$details" project.config.reviewers.1.harness >/dev/null; then
		dcp_ao_fail 'AO wb-core has an extra reviewer'
		return 1
	fi
}

dcp_ao_register_wb_core_locked() {
	local lab_root="$1" cli="$2" target="$lab_root/targets/wb-core" status
	[[ "$(dcp_ao_validate_wb_core_target "$lab_root" 1)" == "$target" ]] || return 1
	dcp_ao_gateway_ensure_locked "$lab_root" "$cli" || return 1
	dcp_ao_export_runtime_env "$lab_root"
	dcp_ao_preflight_codex_worker "$lab_root" || return 1
	status="$("$cli" status --json)" || return 1
	printf '%s' "$status" | grep -Fq '"state": "ready"' || { dcp_ao_fail 'isolated AO daemon is not ready'; return 1; }
	dcp_ao_gateway_assert_pair "$lab_root" "$status" || return 1
	dcp_ao_prepare_wb_core_project "$cli" "$target" || return 1
	printf 'wb_core_project=registered\nwb_core_compatibility=%s\n' "$(dcp_ao_wb_core_compatibility_status "$target")"
}

dcp_ao_register_wb_core() {
	local lab_root="$1" cli
	cli="$(dcp_ao_resolve_cli "$lab_root")" || return 1
	dcp_ao_gateway_with_lock "$lab_root" "$cli" dcp_ao_register_wb_core_locked
}

dcp_ao_submit() {
	local target_name='' profile='' task_id='' prompt=''
	local target_seen=0 profile_seen=0 task_seen=0 prompt_seen=0
	if [[ "${1:-}" == '-h' || "${1:-}" == '--help' ]]; then
		cat <<'EOF'
Usage: bin/dcp-ao-submit --target dcp-lab --prompt 'one short prompt'
       bin/dcp-ao-submit --target dcp-review-lab --profile synthetic-pr --task-id task-id --prompt 'one short prompt'
       bin/dcp-ao-submit --target wb-browser-extension --profile repo-only --task-id task-id --prompt 'one short prompt'
       bin/dcp-ao-submit --target wb-core --profile repo-only --task-id task-id --prompt 'one short prompt'

The default lab target is disposable and remote-free. The synthetic-pr profile
and repo-only profile are separately fixed to their exact public repositories
and a 1-16 character task id. Prompts must be one line and no more than 512
UTF-8 bytes.
EOF
		return 0
	fi
	while [[ "$#" -gt 0 ]]; do
		case "$1" in
			--target)
				if [[ "$#" -lt 2 ]]; then dcp_ao_fail '--target requires a value'; return 1; fi
				[[ "$target_seen" -eq 0 ]] || { dcp_ao_fail 'duplicate --target'; return 1; }
				target_seen=1
				target_name="$2"
				shift 2
				;;
			--profile)
				if [[ "$#" -lt 2 ]]; then dcp_ao_fail '--profile requires a value'; return 1; fi
				[[ "$profile_seen" -eq 0 ]] || { dcp_ao_fail 'duplicate --profile'; return 1; }
				profile_seen=1
				profile="$2"
				shift 2
				;;
			--task-id)
				if [[ "$#" -lt 2 ]]; then dcp_ao_fail '--task-id requires a value'; return 1; fi
				[[ "$task_seen" -eq 0 ]] || { dcp_ao_fail 'duplicate --task-id'; return 1; }
				task_seen=1
				task_id="$2"
				shift 2
				;;
			--prompt)
				if [[ "$#" -lt 2 ]]; then dcp_ao_fail '--prompt requires a value'; return 1; fi
				[[ "$prompt_seen" -eq 0 ]] || { dcp_ao_fail 'duplicate --prompt'; return 1; }
				prompt_seen=1
				prompt="$2"
				shift 2
				;;
			*) dcp_ao_fail "unknown argument: $1" ; return 1 ;;
		esac
	done
	dcp_ao_validate_prompt "$prompt" || return 1
	local lab_root target cli
	lab_root="$(dcp_ao_require_lab_root)" || return 1
	case "$target_name" in
		dcp-lab)
			[[ -z "$profile" && -z "$task_id" ]] || { dcp_ao_fail 'dcp-lab does not accept a profile or task id'; return 1; }
			target="$(dcp_ao_validate_remote_free_target "$lab_root")" || return 1
			;;
		dcp-review-lab)
			[[ "$profile" == synthetic-pr ]] || { dcp_ao_fail 'dcp-review-lab requires --profile synthetic-pr'; return 1; }
			dcp_ao_validate_task_id "$task_id" || return 1
			target="$lab_root/targets/dcp-review-lab"
			;;
		wb-browser-extension)
			[[ "$profile" == repo-only ]] || { dcp_ao_fail 'wb-browser-extension requires --profile repo-only'; return 1; }
			dcp_ao_validate_task_id "$task_id" || return 1
			target="$lab_root/targets/wb-browser-extension"
			;;
		wb-core)
			[[ "$profile" == repo-only ]] || { dcp_ao_fail 'wb-core requires --profile repo-only'; return 1; }
			dcp_ao_validate_task_id "$task_id" || return 1
			target="$lab_root/targets/wb-core"
			;;
		*) dcp_ao_fail 'only --target dcp-lab, exact dcp-review-lab, exact wb-browser-extension, or exact wb-core is allowed'; return 1 ;;
	esac
	cli="$(dcp_ao_resolve_cli "$lab_root")" || return 1
	dcp_ao_gateway_with_lock "$lab_root" "$cli" dcp_ao_submit_locked "$target_name" "$profile" "$task_id" "$target" "$prompt"
}
