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

dcp_ao_validate_twin_task_id() {
	[[ "$1" == dcp-v2-twin-canary-v1 ]] || { dcp_ao_fail 'integration-twin accepts only exact task id dcp-v2-twin-canary-v1'; return 1; }
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
	printf '%s\n' "DCP wb-core Release Train profiles v2. Work only in this exact public wb-core repository, current native worktree and current AO branch. Read and obey repository AGENTS.md. The immutable DCP task profile is either repo-only or live-runtime; keep task:standard and exactly the matching scope label. Model actions are repository-only for both profiles: never access production, SSH, secrets, runtime or business data, servers, telemetry, deployments, or live Wildberries APIs. Do not create subagents, extra branches, worktrees, remotes, services, or pull requests. On the initial action implement only the direct task, run baseline, create one commit lineage, push the current branch, open one ready PR targeting main with the exact task/scope labels and no release label, then stop. On the one bounded findings repair, change only that task on the same branch and PR, create one new head, run baseline, push, then stop. Never synchronize an admitted head, add release labels, merge, deploy, release, or manually review. Only the trusted DCP daemon may perform exact-head review and FIFO admission and add release:ready. Only WBC GitHub Actions may merge, add release:done for repo-only, or deploy and add release:production for live-runtime."
}

dcp_ao_wb_core_config_json() {
	printf '%s\n' "{\"defaultBranch\":\"main\",\"sessionPrefix\":\"wb-core\",\"worker\":{\"agent\":\"codex\",\"agentConfig\":{\"permissions\":\"accept-edits\",\"dcpReviewLabNetwork\":true}},\"reviewers\":[{\"harness\":\"codex\"}],\"agentRules\":\"$(dcp_ao_wb_core_agent_rules)\"}"
}

dcp_ao_twin_agent_rules() {
	printf '%s\n' "DCP v2 integration-twin task. Work only in exact public orenvlad-ai/dcp-wbc-integration-lab, the current native worktree and the current AO branch. Read and obey repository AGENTS.md. Make only the tiny inert task requested by the prompt. Do not access SSH, Selectel, secrets, runtime, deployment, business data, wb-core, production, or Wildberries APIs. Do not create subagents, extra branches, worktrees, remotes, services, repositories, or pull requests. Run the repository baseline, create one commit lineage, push the current branch, open exactly one ready PR targeting main, then stop. A bounded findings repair may change only the same task on the same branch and PR, run baseline, push the fresh head, then stop. Never merge, deploy, dispatch Release Train, synchronize or rebase an admitted head, or manually review. Only the DCP v2 daemon may review and admit; only the repository Release Train may merge, build, install, start and prove deployment."
}

dcp_ao_twin_config_json() {
	printf '%s\n' "{\"defaultBranch\":\"main\",\"sessionPrefix\":\"dcp-wbc-integration-lab\",\"worker\":{\"agent\":\"codex\",\"agentConfig\":{\"permissions\":\"accept-edits\",\"dcpReviewLabNetwork\":true}},\"reviewers\":[{\"harness\":\"codex\"}],\"agentRules\":\"$(dcp_ao_twin_agent_rules)\"}"
}

dcp_ao_twin_rules_match_source_lock() {
	local rules bytes digest
	rules="$(dcp_ao_twin_agent_rules)"
	bytes="$(printf '%s' "$rules" | LC_ALL=C wc -c | tr -d '[:space:]')"
	digest="$(printf '%s' "$rules" | dcp_ao_sha256_stream)"
	[[ "$bytes" == "$DCP_AO_TWIN_POLICY_AGENT_RULES_BYTES" && "$digest" == "$DCP_AO_TWIN_POLICY_AGENT_RULES_SHA256" ]] || {
		dcp_ao_fail 'integration-twin adapter rules drifted from the pinned managed-source expectation'; return 1;
	}
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

dcp_ao_validate_twin_provider_identity() {
	local provider workflow
	dcp_ao_require_tool gh || return 1
	provider="$(gh api repos/orenvlad-ai/dcp-wbc-integration-lab \
		--jq '[.full_name, (.private|tostring), .default_branch, (.id|tostring), (.owner.id|tostring)] | join("|")')" || {
		dcp_ao_fail 'integration-twin provider identity is unavailable'; return 1;
	}
	[[ "$provider" == "orenvlad-ai/dcp-wbc-integration-lab|false|main|$DCP_AO_TWIN_REPOSITORY_ID|$DCP_AO_TWIN_OWNER_ID" ]] || {
		dcp_ao_fail 'integration-twin provider identity is not exact and public'; return 1;
	}
	workflow="$(gh api "repos/orenvlad-ai/dcp-wbc-integration-lab/actions/workflows/$DCP_AO_TWIN_WORKFLOW_ID" \
		--jq '[.id, .name, .path, .state] | map(tostring) | join("|")')" || {
		dcp_ao_fail 'integration-twin DCP issuer workflow identity is unavailable'; return 1;
	}
	[[ "$workflow" == "$DCP_AO_TWIN_WORKFLOW_ID|Release Train|.github/workflows/release-train.yml|active" ]] || {
		dcp_ao_fail 'integration-twin DCP issuer workflow is not exact and active'; return 1;
	}
}

dcp_ao_refresh_twin_target() {
	local target="$1" attempt
	for attempt in 1 2 3; do
		if git -C "$target" fetch --quiet --no-tags origin main; then return 0; fi
		if [[ "$attempt" -lt 3 ]]; then sleep "$attempt"; fi
	done
	dcp_ao_fail 'integration-twin origin/main fetch failed after bounded retries'
	return 1
}

dcp_ao_wb_core_compatibility_status() {
	local target="$1" marker='wb-core.dcp-release-handoff/v2' path lab_root project_status
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
		'.id == "wb-core" and .path == $path and .repo == "https://github.com/orenvlad-ai/wb-core.git" and .kind == "single_repo" and
		 (.config | del(.agentConfig, .orchestrator, .trackerIntake, .containerReap)) == $config and
		 ((.config | has("agentConfig") | not) or .config.agentConfig == {}) and
		 ((.config | has("orchestrator") | not) or .config.orchestrator == {agentConfig:{}}) and
		 ((.config | has("trackerIntake") | not) or .config.trackerIntake == {}) and
		 ((.config | has("containerReap") | not) or .config.containerReap == {}) and
		 .config.agentRules == $rules' \
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
		dcp_ao_fail 'wb-core compatibility gate is blocked: repository-owned marker wb-core.dcp-release-handoff/v2 is absent or incomplete';
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
		"SELECT count(*) FROM dcp_review_lab_policy_task WHERE session_id='$session_id' AND card_number=$number AND worktree_path='$path' AND source_branch='ao/$session_id/root' AND target='wb-core' AND repository='orenvlad-ai/wb-core' AND ((profile='repo-only' AND policy_version='dcp.wb-core.repo-only.release-train/v1') OR (profile='live-runtime' AND policy_version='dcp.wb-core.live-runtime.release-train/v1'));")" || return 1
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

dcp_ao_validate_twin_target() {
	local lab_root="$1" refresh="${2:-0}" require_stage5_base="${3:-0}" target resolved head remote_head path branch
	target="$lab_root/targets/dcp-wbc-integration-lab"
	[[ -d "$target/.git" ]] || { dcp_ao_fail 'exact integration-twin target is absent; run bin/dcp-ao init-twin'; return 1; }
	resolved="$(cd "$target" && pwd -P)"
	[[ "$resolved" == "$target" && "$(git -C "$target" rev-parse --show-toplevel)" == "$target" ]] || {
		dcp_ao_fail 'integration-twin repository path mismatch'; return 1;
	}
	dcp_ao_validate_twin_provider_identity || return 1
	[[ "$(git -C "$target" remote)" == origin ]] || { dcp_ao_fail 'integration-twin must have exactly one origin remote'; return 1; }
	[[ "$(git -C "$target" remote get-url origin)" == 'https://github.com/orenvlad-ai/dcp-wbc-integration-lab.git' ]] || { dcp_ao_fail 'integration-twin fetch URL mismatch'; return 1; }
	[[ "$(git -C "$target" remote get-url --push origin)" == 'https://github.com/orenvlad-ai/dcp-wbc-integration-lab.git' ]] || { dcp_ao_fail 'integration-twin push URL mismatch'; return 1; }
	[[ "$(git -C "$target" branch --show-current)" == main && -z "$(git -C "$target" status --porcelain)" ]] || {
		dcp_ao_fail 'integration-twin baseline must be clean on main'; return 1;
	}
	if [[ "$refresh" == 1 ]]; then dcp_ao_refresh_twin_target "$target" || return 1; fi
	remote_head="$(git -C "$target" rev-parse --verify refs/remotes/origin/main 2>/dev/null)" || { dcp_ao_fail 'integration-twin origin/main is absent'; return 1; }
	head="$(git -C "$target" rev-parse HEAD)"
	if [[ "$head" != "$remote_head" ]]; then
		[[ "$refresh" == 1 ]] || { dcp_ao_fail 'integration-twin baseline changed while the gateway was locked'; return 1; }
		git -C "$target" merge-base --is-ancestor "$head" "$remote_head" || { dcp_ao_fail 'integration-twin main diverged from origin/main'; return 1; }
		git -C "$target" merge --ff-only "$remote_head" >/dev/null || { dcp_ao_fail 'integration-twin main could not fast-forward'; return 1; }
		head="$(git -C "$target" rev-parse HEAD)"
	fi
	[[ "$head" == "$remote_head" && -z "$(git -C "$target" status --porcelain)" ]] || { dcp_ao_fail 'integration-twin clean base identity changed'; return 1; }
	if [[ "$require_stage5_base" == 1 && "$head" != "$DCP_AO_TWIN_STAGE5_BASE_SHA" ]]; then
		dcp_ao_fail 'integration-twin Stage 5 baseline differs from the issuer-handoff merge'; return 1
	fi
	for path in AGENTS.md .github/workflows/baseline.yml .github/workflows/release-train.yml scripts/release_train.py target-spec.json; do
		git -C "$target" ls-files --error-unmatch "$path" >/dev/null 2>&1 || { dcp_ao_fail "integration-twin required release file is absent: $path"; return 1; }
	done
	git -C "$target" grep -Fq 'dcp-admission-v2' HEAD -- .github/workflows/release-train.yml scripts/release_train.py || { dcp_ao_fail 'integration-twin DCP issuer seam is absent'; return 1; }
	[[ ! -e "$target/scripts/qualification_issuer.py" ]] || { dcp_ao_fail 'qualification-only issuer remains installed'; return 1; }
	while IFS='|' read -r path branch; do
		[[ -n "$path" ]] || continue
		if [[ "$path" == "$target" ]]; then
			[[ "$branch" == refs/heads/main ]] || { dcp_ao_fail 'integration-twin baseline worktree branch drifted'; return 1; }
		else
			[[ "$path" == "$lab_root/data/worktrees/dcp-wbc-integration-lab/dcp-wbc-integration-lab-"* && "$branch" == refs/heads/ao/dcp-wbc-integration-lab-*/root ]] || {
				dcp_ao_fail "integration-twin has a foreign linked worktree: $path"; return 1;
			}
		fi
	done < <(git -C "$target" worktree list --porcelain | awk '/^worktree / {p=substr($0,10)} /^branch / {print p "|" substr($0,8)}')
	printf '%s\n' "$resolved"
}

dcp_ao_init_twin_target() {
	local lab_root="$1" target="$lab_root/targets/dcp-wbc-integration-lab"
	if [[ ! -e "$target" ]]; then
		mkdir -p "$(dirname "$target")"
		git clone --origin origin --branch main --single-branch https://github.com/orenvlad-ai/dcp-wbc-integration-lab.git "$target" >/dev/null || {
			dcp_ao_fail 'integration-twin baseline clone failed'; return 1;
		}
	fi
	[[ "$(dcp_ao_validate_twin_target "$lab_root" 1 1)" == "$target" ]] || return 1
	printf 'twin_target=%s\ntwin_base=%s\nissuer=dcp/v2\n' "$target" "$(git -C "$target" rev-parse HEAD)"
}

dcp_ao_twin_policy_digest() {
	local rules
	rules="$(dcp_ao_twin_agent_rules)"
	/usr/bin/jq -cjn --arg rules "$rules" '{agentRules:$rules,targetSpec:"dcp-wbc-integration-lab/v2"}' | dcp_ao_sha256_stream
}

dcp_ao_validate_twin_stage5_activation_response() {
	local lab_root="$1" receipt_sha="$2" response="$3" policy_digest duplicate_paths
	[[ "$receipt_sha" =~ ^[0-9a-f]{64}$ ]] || {
		dcp_ao_fail 'Stage 5 activation response receipt identity is malformed'; return 1;
	}
	policy_digest="$(dcp_ao_twin_policy_digest)" || return 1
	duplicate_paths="$(printf '%s' "$response" | /usr/bin/jq --stream -s -r '
		[.[] | select(length == 2) | .[0] | map(tostring) | join(".")]
		| group_by(.) | map(select(length != 1) | .[0]) | join(",")
	')" || {
		dcp_ao_fail 'Stage 5 activation response is not valid JSON'; return 1;
	}
	[[ -z "$duplicate_paths" ]] || {
		dcp_ao_fail 'Stage 5 activation response contains duplicate fields'; return 1;
	}
	printf '%s' "$response" | /usr/bin/jq -e \
		--arg authority "$DCP_AO_TWIN_STAGE5_CONTRACT_COMMIT" \
		--arg source "$DCP_AO_TWIN_STAGE5_SOURCE_COMMIT" --arg tree "$DCP_AO_TWIN_STAGE5_SOURCE_TREE" \
		--arg receipt "$receipt_sha" --arg policy "$policy_digest" \
		--arg path "$lab_root/targets/dcp-wbc-integration-lab" \
		--argjson repository_id "$DCP_AO_TWIN_REPOSITORY_ID" \
		--argjson owner_id "$DCP_AO_TWIN_OWNER_ID" \
		--argjson workflow_id "$DCP_AO_TWIN_WORKFLOW_ID" '
		type == "object" and
		(keys == ["activation", "created", "projectCreated", "projectId", "projectPath"]) and
		(.activation | type == "object" and keys == [
			"activatedAt", "activationId", "adapter", "authorityCommit", "baseRef",
			"environment", "installReceiptSha", "issuerActor", "issuerEvent",
			"issuerEventType", "issuerKind", "ownerId", "repository", "repositoryId",
			"requiredCheck", "service", "sourceCommit", "sourceTree",
			"targetPolicyDigest", "targetSpecVersion", "workflowId"
		]) and
		.activation.activationId == "dcp-v2-twin-stage5" and
		.activation.authorityCommit == $authority and
		.activation.sourceCommit == $source and
		.activation.sourceTree == $tree and
		.activation.installReceiptSha == $receipt and
		.activation.targetSpecVersion == "dcp-wbc-integration-lab/v2" and
		.activation.targetPolicyDigest == $policy and
		.activation.repository == "orenvlad-ai/dcp-wbc-integration-lab" and
		.activation.repositoryId == $repository_id and
		(.activation.repositoryId | type == "number" and floor == .) and
		.activation.ownerId == $owner_id and
		(.activation.ownerId | type == "number" and floor == .) and
		.activation.baseRef == "main" and
		.activation.requiredCheck == "baseline" and
		.activation.issuerKind == "dcp/v2" and
		.activation.issuerActor == "orenvlad-ai" and
		.activation.issuerEvent == "repository_dispatch" and
		.activation.issuerEventType == "dcp-admission-v2" and
		.activation.workflowId == $workflow_id and
		(.activation.workflowId | type == "number" and floor == .) and
		.activation.environment == "dcp-wbc-integration-lab-selectel" and
		.activation.service == "dcp-wbc-integration-lab" and
		.activation.adapter == "selectel-systemd/v1" and
		(.activation.activatedAt | type == "string" and test("^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\\.[0-9]+)?Z$")) and
		.projectId == "dcp-wbc-integration-lab" and
		.projectPath == $path and
		.created == true and .projectCreated == true
	' >/dev/null || {
		dcp_ao_fail 'Stage 5 activation response differs from the exact lower-camel identity'; return 1;
	}
}

dcp_ao_verify_twin_stopped_activation() {
	local lab_root="$1" require_stopped="${2:-0}" require_zero="${3:-0}" database schema integrity authority_counts authority expected_config project_json activation rows policy_digest app_pid app_result=0
	database="$lab_root/data/ao.db"
	if [[ "$require_stopped" == 1 ]]; then
		app_pid="$(dcp_ao_gateway_exact_app_pid "$lab_root" 2>/dev/null)" || app_result=$?
		[[ "$app_result" -eq 1 && -z "$app_pid" && ! -e "$(dcp_ao_run_file "$lab_root")" ]] || {
			dcp_ao_fail 'Stage 5 activation proof requires the exact app/daemon to be stopped'; return 1;
		}
		if dcp_ao_gateway_port_occupied; then dcp_ao_fail 'Stage 5 activation proof requires the canonical port to be unoccupied'; return 1; fi
	fi
	[[ -f "$database" ]] || { dcp_ao_fail 'canonical SQLite is absent for Stage 5 activation proof'; return 1; }
	if [[ "$require_stopped" == 1 ]]; then
		[[ ! -e "$database-wal" && ! -e "$database-shm" ]] || { dcp_ao_fail 'Stage 5 stopped proof requires absent SQLite sidecars'; return 1; }
	fi
	integrity="$(dcp_ao_repo_only_policy_scalar "$lab_root" 'PRAGMA integrity_check;')" || return 1
	[[ "$integrity" == ok ]] || { dcp_ao_fail 'canonical SQLite integrity check failed'; return 1; }
	schema="$(dcp_ao_repo_only_policy_scalar "$lab_root" 'SELECT max(version_id) FROM goose_db_version WHERE is_applied=1;')" || return 1
	if [[ "$require_zero" == 1 ]]; then
		[[ "$schema" == 84 ]] || { dcp_ao_fail "canonical SQLite schema is not exact Stage 5 schema 84: $schema"; return 1; }
	else
		[[ "$schema" == 84 || "$schema" == 85 || "$schema" == 86 || "$schema" == 87 ]] || { dcp_ao_fail "canonical SQLite schema is outside exact Stage 5/6 set: $schema"; return 1; }
	fi
	authority_counts="$(dcp_ao_repo_only_policy_scalar "$lab_root" \
		"SELECT (SELECT count(*) FROM dcp_v2_core_authority) || '|' || (SELECT count(*) FROM dcp_v2_stage5_activation) || '|' || (SELECT count(*) FROM projects WHERE id='dcp-wbc-integration-lab');")" || return 1
	[[ "$authority_counts" == '1|1|1' ]] || { dcp_ao_fail 'Stage 4/5 authority or twin project cardinality differs'; return 1; }
	authority="$(dcp_ao_repo_only_policy_scalar "$lab_root" \
		"SELECT authority_id || '|' || control_plane_commit || '|' || architecture_version || '|' || stage || '|' || adapter_activated || '|' || installed || '|' || created_at FROM dcp_v2_core_authority;")" || return 1
	[[ "$authority" == "dcp-v2-core-stage4|$DCP_AO_TWIN_STAGE4_AUTHORITY_COMMIT|dcp.wbc-integration-twin/v2|4|0|0|$DCP_AO_TWIN_STAGE4_AUTHORITY_CREATED_AT" ]] || {
		dcp_ao_fail 'Stage 4 core authority identity differs'; return 1;
	}
	policy_digest="$(dcp_ao_twin_policy_digest)"
	activation="$(dcp_ao_repo_only_policy_scalar "$lab_root" \
		"SELECT authority_commit || '|' || source_commit || '|' || source_tree || '|' || install_receipt_sha || '|' || target_spec_version || '|' || target_policy_digest || '|' || repository || '|' || repository_id || '|' || owner_id || '|' || base_ref || '|' || required_check || '|' || issuer_kind || '|' || issuer_actor || '|' || issuer_event || '|' || issuer_event_type || '|' || workflow_id || '|' || environment || '|' || service || '|' || adapter || '|' || activated_at FROM dcp_v2_stage5_activation WHERE activation_id='dcp-v2-twin-stage5';")" || return 1
	[[ "$activation" == "$DCP_AO_TWIN_STAGE5_CONTRACT_COMMIT|$DCP_AO_TWIN_STAGE5_SOURCE_COMMIT|$DCP_AO_TWIN_STAGE5_SOURCE_TREE|$DCP_AO_TWIN_STAGE5_RECEIPT_SHA256|dcp-wbc-integration-lab/v2|$policy_digest|orenvlad-ai/dcp-wbc-integration-lab|$DCP_AO_TWIN_REPOSITORY_ID|$DCP_AO_TWIN_OWNER_ID|main|baseline|dcp/v2|orenvlad-ai|repository_dispatch|dcp-admission-v2|$DCP_AO_TWIN_WORKFLOW_ID|dcp-wbc-integration-lab-selectel|dcp-wbc-integration-lab|selectel-systemd/v1|$DCP_AO_TWIN_STAGE5_ACTIVATED_AT" ]] || {
		dcp_ao_fail 'Stage 5 activation identity differs from the exact source/install/issuer lock'; return 1;
	}
	expected_config="$(dcp_ao_twin_config_json)"
	project_json="$(dcp_ao_repo_only_policy_scalar "$lab_root" \
		"SELECT json_object('id',id,'path',path,'repo',repo_origin_url,'name',display_name,'kind',kind,'registered',registered_at,'archived',archived_at,'config',json(config)) FROM projects WHERE id='dcp-wbc-integration-lab';")" || return 1
	printf '%s' "$project_json" | /usr/bin/jq -e \
		--arg path "$lab_root/targets/dcp-wbc-integration-lab" --arg registered "$DCP_AO_TWIN_STAGE5_ACTIVATED_AT" --argjson config "$expected_config" \
		'.id == "dcp-wbc-integration-lab" and .path == $path and .repo == "https://github.com/orenvlad-ai/dcp-wbc-integration-lab.git" and .name == "dcp-wbc-integration-lab" and .kind == "single_repo" and .registered == $registered and .archived == null and (.config | del(.agentConfig, .orchestrator, .trackerIntake, .containerReap)) == $config and ((.config | has("agentConfig") | not) or .config.agentConfig == {}) and ((.config | has("orchestrator") | not) or .config.orchestrator == {agentConfig:{}}) and ((.config | has("trackerIntake") | not) or .config.trackerIntake == {}) and ((.config | has("containerReap") | not) or .config.containerReap == {})' >/dev/null || {
		dcp_ao_fail 'Stage 5 exact integration-twin project/config identity differs'; return 1;
	}
	if [[ "$require_zero" == 1 ]]; then
		rows="$(dcp_ao_repo_only_policy_scalar "$lab_root" \
			'SELECT (SELECT count(*) FROM dcp_v2_task) + (SELECT count(*) FROM dcp_v2_revision) + (SELECT count(*) FROM dcp_v2_command) + (SELECT count(*) FROM dcp_v2_action) + (SELECT count(*) FROM dcp_v2_admission) + (SELECT count(*) FROM dcp_v2_incident) + (SELECT count(*) FROM dcp_v2_external_event) + (SELECT count(*) FROM dcp_v2_result);')" || return 1
		[[ "$rows" == 0 ]] || { dcp_ao_fail 'Stage 5 zero-state gate found integration-twin lifecycle rows'; return 1; }
	fi
}

dcp_ao_validate_twin_stage6_recovery_response() {
	local receipt_sha="$1" response="$2" duplicate_paths
	[[ "$receipt_sha" =~ ^[0-9a-f]{64}$ ]] || {
		dcp_ao_fail 'Stage 6 recovery response receipt identity is malformed'; return 1;
	}
	duplicate_paths="$(printf '%s' "$response" | /usr/bin/jq --stream -s -r '
		[.[] | select(length == 2) | .[0] | map(tostring) | join(".")]
		| group_by(.) | map(select(length != 1) | .[0]) | join(",")
	')" || {
		dcp_ao_fail 'Stage 6 recovery response is not valid JSON'; return 1;
	}
	[[ -z "$duplicate_paths" ]] || {
		dcp_ao_fail 'Stage 6 recovery response contains duplicate fields'; return 1;
	}
	printf '%s' "$response" | /usr/bin/jq -e \
		--arg source "$DCP_AO_FORK_COMMIT" --arg tree "$DCP_AO_FORK_TREE" \
		--arg receipt "$receipt_sha" \
		--arg stage5_source "$DCP_AO_TWIN_STAGE5_SOURCE_COMMIT" \
		--arg stage5_tree "$DCP_AO_TWIN_STAGE5_SOURCE_TREE" \
		--arg stage5_receipt "$DCP_AO_TWIN_STAGE5_RECEIPT_SHA256" \
		--arg task "$DCP_AO_TWIN_STAGE6_TASK_ID" \
		--arg revision "$DCP_AO_TWIN_STAGE6_REVISION_ID" \
		--arg command "$DCP_AO_TWIN_STAGE6_COMMAND_ID" \
		--arg action "$DCP_AO_TWIN_STAGE6_ACTION_ID" \
		--arg base "$DCP_AO_TWIN_STAGE5_BASE_SHA" '
		type == "object" and
		(keys == ["actionId", "baseSha", "commandId", "installReceiptSha", "installedSourceCommit", "installedSourceTree", "ready", "revisionId", "schemaVersion", "stage5ActivationId", "stage5ReceiptSha", "stage5SourceCommit", "stage5SourceTree", "taskId"]) and
		.schemaVersion == "dcp.v2.stage6-native-shell-recovery/v1" and
		.installedSourceCommit == $source and .installedSourceTree == $tree and
		.installReceiptSha == $receipt and .stage5ActivationId == "dcp-v2-twin-stage5" and
		.stage5SourceCommit == $stage5_source and .stage5SourceTree == $stage5_tree and
		.stage5ReceiptSha == $stage5_receipt and .taskId == $task and
		.revisionId == $revision and .commandId == $command and .actionId == $action and
		.baseSha == $base and .ready == true
	' >/dev/null || {
		dcp_ao_fail 'Stage 6 recovery response differs from the exact lower-camel identity'; return 1;
	}
}

dcp_ao_verify_twin_stage6_recovery_fence() {
	local lab_root="$1" expected_schema="$2" require_stopped="${3:-1}" task revision command action payload_json lease_epoch lease_token counts native_counts predecessor_counts
	[[ "$expected_schema" == 84 || "$expected_schema" == 85 ]] || {
		dcp_ao_fail 'Stage 6 recovery fence expected schema must be 84 or 85'; return 1;
	}
	dcp_ao_verify_twin_stopped_activation "$lab_root" "$require_stopped" 0 || return 1
	[[ "$(dcp_ao_repo_only_policy_scalar "$lab_root" 'SELECT max(version_id) FROM goose_db_version WHERE is_applied=1;')" == "$expected_schema" ]] || {
		dcp_ao_fail "Stage 6 recovery fence schema differs from exact $expected_schema"; return 1;
	}
	task="$(dcp_ao_repo_only_policy_scalar "$lab_root" \
		"SELECT task_id || '|' || target_spec_version || '|' || repository || '|' || repository_id || '|' || owner_id || '|' || base_ref || '|' || profile || '|' || policy_digest || '|' || request_digest || '|' || scope_digest || '|' || initial_worker_budget || '|' || repair_budget || '|' || repair_used || '|' || max_readmissions || '|' || readmission_count || '|' || current_revision_id || '|' || state || '|' || state_revision || '|' || terminal_result_id || '|' || human_gate_question || '|' || error_code || '|' || created_at || '|' || updated_at FROM dcp_v2_task;")" || return 1
	[[ "$task" == "$DCP_AO_TWIN_STAGE6_TASK_ID|dcp-wbc-integration-lab/v2|orenvlad-ai/dcp-wbc-integration-lab|$DCP_AO_TWIN_REPOSITORY_ID|$DCP_AO_TWIN_OWNER_ID|main|live-runtime|$(dcp_ao_twin_policy_digest)|$DCP_AO_TWIN_STAGE6_REQUEST_DIGEST|$DCP_AO_TWIN_STAGE6_SCOPE_DIGEST|1|1|0|2|0|$DCP_AO_TWIN_STAGE6_REVISION_ID|worker_queued|1||||$DCP_AO_TWIN_STAGE6_SUBMITTED_AT|$DCP_AO_TWIN_STAGE6_SUBMITTED_AT" ]] || {
		dcp_ao_fail 'Stage 6 recovery Task fence differs'; return 1;
	}
	revision="$(dcp_ao_repo_only_policy_scalar "$lab_root" \
		"SELECT revision_id || '|' || task_id || '|' || sequence || '|' || kind || '|' || repository || '|' || base_ref || '|' || base_sha || '|' || head_ref || '|' || head_sha || '|' || predecessor_revision_id || '|' || cause_command_id || '|' || pr_number || '|' || evidence_digest || '|' || created_at FROM dcp_v2_revision;")" || return 1
	[[ "$revision" == "$DCP_AO_TWIN_STAGE6_REVISION_ID|$DCP_AO_TWIN_STAGE6_TASK_ID|1|work_input|orenvlad-ai/dcp-wbc-integration-lab|main|$DCP_AO_TWIN_STAGE5_BASE_SHA|main|$DCP_AO_TWIN_STAGE5_BASE_SHA|||0|$DCP_AO_TWIN_STAGE6_REVISION_EVIDENCE_DIGEST|$DCP_AO_TWIN_STAGE6_SUBMITTED_AT" ]] || {
		dcp_ao_fail 'Stage 6 recovery Revision fence differs'; return 1;
	}
	command="$(dcp_ao_repo_only_policy_scalar "$lab_root" \
		"SELECT command_id || '|' || task_id || '|' || revision_id || '|' || kind || '|' || payload_digest || '|' || prerequisite_digest || '|' || idempotency_key || '|' || status || '|' || lease_owner || '|' || (lease_epoch <> '') || '|' || (lease_token <> '') || '|' || effect_fence || '|' || recovery_generation || '|' || result_digest || '|' || error_code || '|' || created_at || '|' || updated_at FROM dcp_v2_command;")" || return 1
	[[ "$command" == "$DCP_AO_TWIN_STAGE6_COMMAND_ID|$DCP_AO_TWIN_STAGE6_TASK_ID|$DCP_AO_TWIN_STAGE6_REVISION_ID|worker.execute/v1|$DCP_AO_TWIN_STAGE6_PAYLOAD_DIGEST|$DCP_AO_TWIN_STAGE6_REQUEST_DIGEST|$DCP_AO_TWIN_STAGE6_TASK_ID/worker.execute/v1/1|leased|dcp-v2-daemon|1|1|model:$DCP_AO_TWIN_STAGE6_ACTION_ID|0|||$DCP_AO_TWIN_STAGE6_SUBMITTED_AT|$DCP_AO_TWIN_STAGE6_COMMAND_UPDATED_AT" ]] || {
		dcp_ao_fail 'Stage 6 recovery Command fence differs'; return 1;
	}
	payload_json="$(dcp_ao_repo_only_policy_scalar "$lab_root" 'SELECT payload_json FROM dcp_v2_command;')" || return 1
	[[ "$(printf '%s' "$payload_json" | dcp_ao_sha256_stream)" == "$DCP_AO_TWIN_STAGE6_PAYLOAD_DIGEST" ]] && \
		printf '%s' "$payload_json" | /usr/bin/jq -e --arg base "$DCP_AO_TWIN_STAGE5_BASE_SHA" \
		'type == "object" and keys == ["baseSha", "prompt"] and .baseSha == $base and (.prompt | type == "string" and test("\\S"))' >/dev/null || {
		dcp_ao_fail 'Stage 6 recovery Command payload fence differs'; return 1;
	}
	lease_epoch="$(dcp_ao_repo_only_policy_scalar "$lab_root" 'SELECT lease_epoch FROM dcp_v2_command;')" || return 1
	lease_token="$(dcp_ao_repo_only_policy_scalar "$lab_root" 'SELECT lease_token FROM dcp_v2_command;')" || return 1
	[[ "$(printf '%s' "$lease_epoch" | dcp_ao_sha256_stream)" == "$DCP_AO_TWIN_STAGE6_LEASE_EPOCH_SHA256" && \
		"$(printf '%s' "$lease_token" | dcp_ao_sha256_stream)" == "$DCP_AO_TWIN_STAGE6_LEASE_TOKEN_SHA256" ]] || {
		dcp_ao_fail 'Stage 6 recovery Command lease fence differs'; return 1;
	}
	action="$(dcp_ao_repo_only_policy_scalar "$lab_root" \
		"SELECT action_id || '|' || command_id || '|' || task_id || '|' || revision_id || '|' || role || '|' || model || '|' || reasoning || '|' || token_budget || '|' || time_budget_sec || '|' || input_digest || '|' || attempt || '|' || status || '|' || slot || '|' || launch_fence || '|' || runtime_id || '|' || result_digest || '|' || error_code || '|' || created_at || '|' || updated_at FROM dcp_v2_action;")" || return 1
	[[ "$action" == "$DCP_AO_TWIN_STAGE6_ACTION_ID|$DCP_AO_TWIN_STAGE6_COMMAND_ID|$DCP_AO_TWIN_STAGE6_TASK_ID|$DCP_AO_TWIN_STAGE6_REVISION_ID|worker|codex/default|high|20000|1800|$DCP_AO_TWIN_STAGE6_REQUEST_DIGEST|1|launching|1|model:$DCP_AO_TWIN_STAGE6_ACTION_ID||||$DCP_AO_TWIN_STAGE6_SUBMITTED_AT|$DCP_AO_TWIN_STAGE6_ACTION_UPDATED_AT" ]] || {
		dcp_ao_fail 'Stage 6 recovery Action fence differs'; return 1;
	}
	counts="$(dcp_ao_repo_only_policy_scalar "$lab_root" \
		'SELECT (SELECT count(*) FROM dcp_v2_task) || "|" || (SELECT count(*) FROM dcp_v2_revision) || "|" || (SELECT count(*) FROM dcp_v2_command) || "|" || (SELECT count(*) FROM dcp_v2_action) || "|" || (SELECT count(*) FROM dcp_v2_admission) || "|" || (SELECT count(*) FROM dcp_v2_incident) || "|" || (SELECT count(*) FROM dcp_v2_external_event) || "|" || (SELECT count(*) FROM dcp_v2_result);')" || return 1
	[[ "$counts" == '1|1|1|1|0|0|0|0' ]] || { dcp_ao_fail 'Stage 6 recovery lifecycle counts differ'; return 1; }
	native_counts="$(dcp_ao_repo_only_policy_scalar "$lab_root" \
		"SELECT (SELECT count(*) FROM dcp_review_lab_policy_task WHERE task_id='$DCP_AO_TWIN_STAGE6_TASK_ID') || '|' || (SELECT count(*) FROM sessions WHERE project_id='dcp-wbc-integration-lab') || '|' || (SELECT count(*) FROM dcp_model_action WHERE task_id='$DCP_AO_TWIN_STAGE6_TASK_ID' OR session_id='dcp-wbc-integration-lab-1');")" || return 1
	[[ "$native_counts" == '0|0|0' ]] || { dcp_ao_fail 'Stage 6 recovery found a premature native twin identity'; return 1; }
	predecessor_counts="$(dcp_ao_repo_only_policy_scalar "$lab_root" \
		"SELECT count(*) || '|' || sum(CASE WHEN status IN ('claimed','running') THEN 1 ELSE 0 END) FROM dcp_model_action;")" || return 1
	[[ "$predecessor_counts" == '73|0' ]] || { dcp_ao_fail 'Stage 6 recovery predecessor model Action fence differs'; return 1; }
	dcp_ao_install_assert_no_active_model_actions "$lab_root" || return 1
}

dcp_ao_verify_twin_stage6_aggregate_fence() {
	local lab_root="$1" require_stopped="${2:-1}" task revision command action payload_json lease_epoch lease_token counts
	local native native_prompt session native_action model_counts database
	database="$lab_root/data/ao.db"
	dcp_ao_verify_twin_stopped_activation "$lab_root" "$require_stopped" 0 || return 1
	[[ "$(dcp_ao_repo_only_policy_scalar "$lab_root" 'SELECT max(version_id) FROM goose_db_version WHERE is_applied=1;')" == 85 ]] || {
		dcp_ao_fail 'Stage 6 aggregate fence schema differs from exact 85'; return 1;
	}
	task="$(dcp_ao_repo_only_policy_scalar "$lab_root" \
		"SELECT task_id || '|' || target_spec_version || '|' || repository || '|' || repository_id || '|' || owner_id || '|' || base_ref || '|' || profile || '|' || policy_digest || '|' || request_digest || '|' || scope_digest || '|' || initial_worker_budget || '|' || repair_budget || '|' || repair_used || '|' || max_readmissions || '|' || readmission_count || '|' || current_revision_id || '|' || state || '|' || state_revision || '|' || terminal_result_id || '|' || human_gate_question || '|' || error_code || '|' || created_at || '|' || updated_at FROM dcp_v2_task;")" || return 1
	[[ "$task" == "$DCP_AO_TWIN_STAGE6_TASK_ID|dcp-wbc-integration-lab/v2|orenvlad-ai/dcp-wbc-integration-lab|$DCP_AO_TWIN_REPOSITORY_ID|$DCP_AO_TWIN_OWNER_ID|main|live-runtime|$(dcp_ao_twin_policy_digest)|$DCP_AO_TWIN_STAGE6_REQUEST_DIGEST|$DCP_AO_TWIN_STAGE6_SCOPE_DIGEST|1|1|0|2|0|$DCP_AO_TWIN_STAGE6_REVISION_ID|worker_queued|1||||$DCP_AO_TWIN_STAGE6_SUBMITTED_AT|$DCP_AO_TWIN_STAGE6_SUBMITTED_AT" ]] || {
		dcp_ao_fail 'Stage 6 aggregate Task fence differs'; return 1;
	}
	revision="$(dcp_ao_repo_only_policy_scalar "$lab_root" \
		"SELECT revision_id || '|' || task_id || '|' || sequence || '|' || kind || '|' || repository || '|' || base_ref || '|' || base_sha || '|' || head_ref || '|' || head_sha || '|' || predecessor_revision_id || '|' || cause_command_id || '|' || pr_number || '|' || evidence_digest || '|' || created_at FROM dcp_v2_revision;")" || return 1
	[[ "$revision" == "$DCP_AO_TWIN_STAGE6_REVISION_ID|$DCP_AO_TWIN_STAGE6_TASK_ID|1|work_input|orenvlad-ai/dcp-wbc-integration-lab|main|$DCP_AO_TWIN_STAGE5_BASE_SHA|main|$DCP_AO_TWIN_STAGE5_BASE_SHA|||0|$DCP_AO_TWIN_STAGE6_REVISION_EVIDENCE_DIGEST|$DCP_AO_TWIN_STAGE6_SUBMITTED_AT" ]] || {
		dcp_ao_fail 'Stage 6 aggregate Revision fence differs'; return 1;
	}
	command="$(dcp_ao_repo_only_policy_scalar "$lab_root" \
		"SELECT command_id || '|' || task_id || '|' || revision_id || '|' || kind || '|' || payload_digest || '|' || prerequisite_digest || '|' || idempotency_key || '|' || status || '|' || lease_owner || '|' || (lease_epoch <> '') || '|' || (lease_token <> '') || '|' || effect_fence || '|' || recovery_generation || '|' || result_digest || '|' || error_code || '|' || created_at || '|' || updated_at FROM dcp_v2_command;")" || return 1
	[[ "$command" == "$DCP_AO_TWIN_STAGE6_COMMAND_ID|$DCP_AO_TWIN_STAGE6_TASK_ID|$DCP_AO_TWIN_STAGE6_REVISION_ID|worker.execute/v1|$DCP_AO_TWIN_STAGE6_PAYLOAD_DIGEST|$DCP_AO_TWIN_STAGE6_REQUEST_DIGEST|$DCP_AO_TWIN_STAGE6_TASK_ID/worker.execute/v1/1|leased|dcp-v2-daemon|1|1|model:$DCP_AO_TWIN_STAGE6_ACTION_ID|0|||$DCP_AO_TWIN_STAGE6_SUBMITTED_AT|$DCP_AO_TWIN_STAGE6_COMMAND_UPDATED_AT" ]] || {
		dcp_ao_fail 'Stage 6 aggregate Command fence differs'; return 1;
	}
	payload_json="$(dcp_ao_repo_only_policy_scalar "$lab_root" 'SELECT payload_json FROM dcp_v2_command;')" || return 1
	[[ "$(printf '%s' "$payload_json" | dcp_ao_sha256_stream)" == "$DCP_AO_TWIN_STAGE6_PAYLOAD_DIGEST" ]] && \
		printf '%s' "$payload_json" | /usr/bin/jq -e --arg base "$DCP_AO_TWIN_STAGE5_BASE_SHA" \
		'type == "object" and keys == ["baseSha", "prompt"] and .baseSha == $base and (.prompt | type == "string" and test("\\S"))' >/dev/null || {
		dcp_ao_fail 'Stage 6 aggregate Command payload fence differs'; return 1;
	}
	lease_epoch="$(dcp_ao_repo_only_policy_scalar "$lab_root" 'SELECT lease_epoch FROM dcp_v2_command;')" || return 1
	lease_token="$(dcp_ao_repo_only_policy_scalar "$lab_root" 'SELECT lease_token FROM dcp_v2_command;')" || return 1
	[[ "$(printf '%s' "$lease_epoch" | dcp_ao_sha256_stream)" == "$DCP_AO_TWIN_STAGE6_LEASE_EPOCH_SHA256" && \
		"$(printf '%s' "$lease_token" | dcp_ao_sha256_stream)" == "$DCP_AO_TWIN_STAGE6_LEASE_TOKEN_SHA256" ]] || {
		dcp_ao_fail 'Stage 6 aggregate Command lease fence differs'; return 1;
	}
	action="$(dcp_ao_repo_only_policy_scalar "$lab_root" \
		"SELECT action_id || '|' || command_id || '|' || task_id || '|' || revision_id || '|' || role || '|' || model || '|' || reasoning || '|' || token_budget || '|' || time_budget_sec || '|' || input_digest || '|' || attempt || '|' || status || '|' || slot || '|' || launch_fence || '|' || runtime_id || '|' || result_digest || '|' || error_code || '|' || created_at || '|' || updated_at FROM dcp_v2_action;")" || return 1
	[[ "$action" == "$DCP_AO_TWIN_STAGE6_ACTION_ID|$DCP_AO_TWIN_STAGE6_COMMAND_ID|$DCP_AO_TWIN_STAGE6_TASK_ID|$DCP_AO_TWIN_STAGE6_REVISION_ID|worker|codex/default|high|20000|1800|$DCP_AO_TWIN_STAGE6_REQUEST_DIGEST|1|launching|1|model:$DCP_AO_TWIN_STAGE6_ACTION_ID||||$DCP_AO_TWIN_STAGE6_SUBMITTED_AT|$DCP_AO_TWIN_STAGE6_ACTION_UPDATED_AT" ]] || {
		dcp_ao_fail 'Stage 6 aggregate Action fence differs'; return 1;
	}
	counts="$(dcp_ao_repo_only_policy_scalar "$lab_root" \
		'SELECT (SELECT count(*) FROM dcp_v2_task) || "|" || (SELECT count(*) FROM dcp_v2_revision) || "|" || (SELECT count(*) FROM dcp_v2_command) || "|" || (SELECT count(*) FROM dcp_v2_action) || "|" || (SELECT count(*) FROM dcp_v2_admission) || "|" || (SELECT count(*) FROM dcp_v2_incident) || "|" || (SELECT count(*) FROM dcp_v2_external_event) || "|" || (SELECT count(*) FROM dcp_v2_result);')" || return 1
	[[ "$counts" == '1|1|1|1|0|0|0|0' ]] || { dcp_ao_fail 'Stage 6 aggregate lifecycle counts differ'; return 1; }

	native="$(dcp_ao_repo_only_policy_scalar "$lab_root" \
		"SELECT json_object('taskId',task_id,'payloadDigest',payload_digest,'target',target,'profile',profile,'repository',repository,'policyVersion',policy_version,'sessionId',session_id,'cardNumber',card_number,'worktreePath',worktree_path,'sourceBranch',source_branch,'state',state,'revision',revision,'repairCount',repair_count,'prUrl',pr_url,'prNumber',pr_number,'currentHeadSha',current_head_sha,'previousHeadSha',previous_head_sha,'reviewRunId',review_run_id,'admissionId',admission_id,'releasePhase',release_phase,'mergeCommitSha',merge_commit_sha,'errorCode',error_code,'incidentPacket',incident_packet) FROM dcp_review_lab_policy_task;")" || return 1
	printf '%s' "$native" | /usr/bin/jq -e \
		--arg task "$DCP_AO_TWIN_STAGE6_TASK_ID" --arg payload "$DCP_AO_TWIN_STAGE6_NATIVE_PAYLOAD_DIGEST" \
		--arg session 'dcp-wbc-integration-lab-1' --arg worktree "$lab_root/data/worktrees/dcp-wbc-integration-lab/dcp-wbc-integration-lab-1" '
		type == "object" and keys == ["admissionId","cardNumber","currentHeadSha","errorCode","incidentPacket","mergeCommitSha","payloadDigest","policyVersion","prNumber","prUrl","previousHeadSha","profile","releasePhase","repairCount","repository","reviewRunId","revision","sessionId","sourceBranch","state","target","taskId","worktreePath"] and
		.taskId == $task and .payloadDigest == $payload and .target == "dcp-wbc-integration-lab" and
		.profile == "live-runtime" and .repository == "orenvlad-ai/dcp-wbc-integration-lab" and
		.policyVersion == "dcp.wbc-integration-twin/v2" and .sessionId == $session and .cardNumber == 1 and
		.worktreePath == $worktree and .sourceBranch == "ao/dcp-wbc-integration-lab-1/root" and
		.state == "reserved" and .revision == 1 and .repairCount == 0 and .prUrl == "" and .prNumber == 0 and
		.currentHeadSha == "" and .previousHeadSha == "" and .reviewRunId == "" and .admissionId == "" and
		.releasePhase == "" and .mergeCommitSha == "" and .errorCode == "" and .incidentPacket == ""
	' >/dev/null || { dcp_ao_fail 'Stage 6 aggregate native card fence differs'; return 1; }
	native_prompt="$(dcp_ao_repo_only_policy_scalar "$lab_root" \
		"SELECT prompt FROM dcp_review_lab_policy_task WHERE task_id='$DCP_AO_TWIN_STAGE6_TASK_ID';")" || return 1
	[[ "$(printf '%s' "$native_prompt" | dcp_ao_sha256_stream)" == "$DCP_AO_TWIN_STAGE6_NATIVE_PROMPT_SHA256" ]] || {
		dcp_ao_fail 'Stage 6 aggregate native prompt fence differs'; return 1;
	}
	session="$(dcp_ao_repo_only_policy_scalar "$lab_root" \
		"SELECT json_object('id',id,'projectId',project_id,'num',num,'kind',kind,'harness',harness,'activityState',activity_state,'terminated',is_terminated,'branch',branch,'workspacePath',workspace_path,'runtimeHandleId',runtime_handle_id,'agentSessionId',agent_session_id,'prompt',prompt,'runtimeLaunchId',runtime_launch_id) FROM sessions WHERE project_id='dcp-wbc-integration-lab';")" || return 1
	printf '%s' "$session" | /usr/bin/jq -e '
		type == "object" and keys == ["activityState","agentSessionId","branch","harness","id","kind","num","projectId","prompt","runtimeHandleId","runtimeLaunchId","terminated","workspacePath"] and
		.id == "dcp-wbc-integration-lab-1" and .projectId == "dcp-wbc-integration-lab" and .num == 1 and
		.kind == "worker" and .harness == "codex" and .activityState == "idle" and .terminated == 0 and
		.branch == "" and .workspacePath == "" and .runtimeHandleId == "" and .agentSessionId == "" and
		.prompt == "" and .runtimeLaunchId == ""
	' >/dev/null || { dcp_ao_fail 'Stage 6 aggregate native session fence differs'; return 1; }
	native_action="$(dcp_ao_repo_only_policy_scalar "$lab_root" \
		"SELECT json_object('sequence',sequence,'id',id,'taskId',task_id,'sessionId',session_id,'kind',kind,'exactHeadSha',exact_head_sha,'status',status,'slot',slot,'launchId',launch_id,'reviewRunId',review_run_id,'incidentId',incident_id,'errorCode',error_code) FROM dcp_model_action WHERE task_id='$DCP_AO_TWIN_STAGE6_TASK_ID' OR session_id='dcp-wbc-integration-lab-1';")" || return 1
	printf '%s' "$native_action" | /usr/bin/jq -e \
		--argjson sequence "$DCP_AO_TWIN_STAGE6_NATIVE_ACTION_SEQUENCE" --arg id "$DCP_AO_TWIN_STAGE6_NATIVE_ACTION_ID" \
		--arg task "$DCP_AO_TWIN_STAGE6_TASK_ID" '
		type == "object" and keys == ["errorCode","exactHeadSha","id","incidentId","kind","launchId","reviewRunId","sequence","sessionId","slot","status","taskId"] and
		.sequence == $sequence and .id == $id and .taskId == $task and .sessionId == "dcp-wbc-integration-lab-1" and
		.kind == "initial_worker" and .exactHeadSha == "" and .status == "queued" and .slot == 0 and
		.launchId == "" and .reviewRunId == "" and .incidentId == "" and .errorCode == ""
	' >/dev/null || { dcp_ao_fail 'Stage 6 aggregate native Action fence differs'; return 1; }
	model_counts="$(dcp_ao_repo_only_policy_scalar "$lab_root" \
		"SELECT count(*) || '|' || sum(CASE WHEN status IN ('claimed','running') THEN 1 ELSE 0 END) || '|' || sum(CASE WHEN sequence <= $DCP_AO_TWIN_STAGE6_NATIVE_PREDECESSOR_ACTIONS THEN 1 ELSE 0 END) FROM dcp_model_action;")" || return 1
	[[ "$model_counts" == "$DCP_AO_TWIN_STAGE6_NATIVE_ACTION_SEQUENCE|0|$DCP_AO_TWIN_STAGE6_NATIVE_PREDECESSOR_ACTIONS" ]] || {
		dcp_ao_fail 'Stage 6 aggregate native model Action counts differ'; return 1;
	}
	dcp_ao_install_assert_no_active_model_actions "$lab_root" || return 1
}

dcp_ao_verify_twin_stage6_direct_worker_checkout() {
	local lab_root="$1" worktree
	worktree="$lab_root/data/worktrees/dcp-wbc-integration-lab/dcp-wbc-integration-lab-1"
	[[ -d "$worktree" && ! -L "$worktree" ]] || { dcp_ao_fail 'frozen Worker checkout is absent or aliased'; return 1; }
	[[ "$(git -C "$worktree" rev-parse HEAD)" == "$DCP_AO_TWIN_STAGE6_WORKER_COMMIT" ]] || {
		dcp_ao_fail 'frozen Worker commit differs'; return 1;
	}
	[[ "$(git -C "$worktree" rev-parse 'HEAD^{tree}')" == "$DCP_AO_TWIN_STAGE6_WORKER_TREE" ]] || {
		dcp_ao_fail 'frozen Worker tree differs'; return 1;
	}
	[[ "$(git -C "$worktree" branch --show-current)" == "$DCP_AO_TWIN_STAGE6_WORKER_BRANCH" ]] || {
		dcp_ao_fail 'frozen Worker branch differs'; return 1;
	}
	[[ "$(git -C "$worktree" remote get-url origin)" == 'https://github.com/orenvlad-ai/dcp-wbc-integration-lab.git' ]] || {
		dcp_ao_fail 'frozen Worker remote differs'; return 1;
	}
	[[ -z "$(git -C "$worktree" status --porcelain --untracked-files=all)" ]] || {
		dcp_ao_fail 'frozen Worker checkout is dirty'; return 1;
	}
	[[ "$(git -C "$worktree" diff-tree --no-commit-id --name-only -r HEAD)" == 'docs/STAGE6_CANARY.md' ]] || {
		dcp_ao_fail 'frozen Worker changed an unexpected path'; return 1;
	}
	[[ "$(git -C "$worktree" show HEAD:docs/STAGE6_CANARY.md)" == 'Stage 6 DCP v2 canary.' ]] || {
		dcp_ao_fail 'frozen Worker output content differs'; return 1;
	}
	git -C "$worktree" merge-base --is-ancestor "$DCP_AO_TWIN_STAGE5_BASE_SHA" "$DCP_AO_TWIN_STAGE6_WORKER_COMMIT" || {
		dcp_ao_fail 'frozen Worker ancestry differs'; return 1;
	}
}

dcp_ao_verify_twin_stage6_direct_fence() {
	local lab_root="$1" expected_schema="$2" require_stopped="${3:-1}" task revision command action counts direct_tables direct_rows
	local native session native_action model_counts foreign_keys migration_rows
	[[ "$expected_schema" == 85 || "$expected_schema" == 86 || "$expected_schema" == 87 ]] || {
		dcp_ao_fail 'Stage 6 direct install fence expected schema must be 85, 86 or 87'; return 1;
	}
	dcp_ao_verify_twin_stopped_activation "$lab_root" "$require_stopped" 0 || return 1
	[[ "$(dcp_ao_repo_only_policy_scalar "$lab_root" 'SELECT max(version_id) FROM goose_db_version WHERE is_applied=1;')" == "$expected_schema" ]] || {
		dcp_ao_fail "Stage 6 direct install schema differs from exact $expected_schema"; return 1;
	}
	foreign_keys="$(dcp_ao_repo_only_policy_scalar "$lab_root" 'PRAGMA foreign_key_check;')" || return 1
	[[ -z "$foreign_keys" ]] || { dcp_ao_fail 'Stage 6 direct install foreign-key check failed'; return 1; }
	task="$(dcp_ao_repo_only_policy_scalar "$lab_root" \
		"SELECT task_id || '|' || current_revision_id || '|' || state || '|' || state_revision || '|' || terminal_result_id || '|' || human_gate_question || '|' || error_code || '|' || created_at || '|' || updated_at FROM dcp_v2_task;")" || return 1
	[[ "$task" == "$DCP_AO_TWIN_STAGE6_TASK_ID|$DCP_AO_TWIN_STAGE6_REVISION_ID|worker_queued|1||||$DCP_AO_TWIN_STAGE6_SUBMITTED_AT|$DCP_AO_TWIN_STAGE6_SUBMITTED_AT" ]] || {
		dcp_ao_fail 'Stage 6 direct install Task fence differs'; return 1;
	}
	revision="$(dcp_ao_repo_only_policy_scalar "$lab_root" \
		"SELECT revision_id || '|' || task_id || '|' || sequence || '|' || kind || '|' || base_ref || '|' || base_sha || '|' || head_ref || '|' || head_sha || '|' || predecessor_revision_id || '|' || cause_command_id || '|' || pr_number || '|' || evidence_digest || '|' || created_at FROM dcp_v2_revision;")" || return 1
	[[ "$revision" == "$DCP_AO_TWIN_STAGE6_REVISION_ID|$DCP_AO_TWIN_STAGE6_TASK_ID|1|work_input|main|$DCP_AO_TWIN_STAGE5_BASE_SHA|main|$DCP_AO_TWIN_STAGE5_BASE_SHA|||0|$DCP_AO_TWIN_STAGE6_REVISION_EVIDENCE_DIGEST|$DCP_AO_TWIN_STAGE6_SUBMITTED_AT" ]] || {
		dcp_ao_fail 'Stage 6 direct install Revision fence differs'; return 1;
	}
	command="$(dcp_ao_repo_only_policy_scalar "$lab_root" \
		"SELECT command_id || '|' || task_id || '|' || revision_id || '|' || kind || '|' || status || '|' || lease_owner || '|' || effect_fence || '|' || recovery_generation || '|' || result_digest || '|' || error_code || '|' || created_at || '|' || updated_at FROM dcp_v2_command;")" || return 1
	[[ "$command" == "$DCP_AO_TWIN_STAGE6_COMMAND_ID|$DCP_AO_TWIN_STAGE6_TASK_ID|$DCP_AO_TWIN_STAGE6_REVISION_ID|worker.execute/v1|leased|dcp-v2-daemon|model:$DCP_AO_TWIN_STAGE6_ACTION_ID|0|||$DCP_AO_TWIN_STAGE6_SUBMITTED_AT|$DCP_AO_TWIN_STAGE6_COMMAND_UPDATED_AT" ]] || {
		dcp_ao_fail 'Stage 6 direct install Command fence differs'; return 1;
	}
	action="$(dcp_ao_repo_only_policy_scalar "$lab_root" \
		"SELECT action_id || '|' || command_id || '|' || task_id || '|' || revision_id || '|' || role || '|' || attempt || '|' || status || '|' || slot || '|' || launch_fence || '|' || runtime_id || '|' || result_digest || '|' || error_code || '|' || created_at || '|' || updated_at FROM dcp_v2_action;")" || return 1
	[[ "$action" == "$DCP_AO_TWIN_STAGE6_ACTION_ID|$DCP_AO_TWIN_STAGE6_COMMAND_ID|$DCP_AO_TWIN_STAGE6_TASK_ID|$DCP_AO_TWIN_STAGE6_REVISION_ID|worker|1|running|1|model:$DCP_AO_TWIN_STAGE6_ACTION_ID|$DCP_AO_TWIN_STAGE6_DIRECT_RUNTIME_ID|||$DCP_AO_TWIN_STAGE6_SUBMITTED_AT|$DCP_AO_TWIN_STAGE6_DIRECT_ACTION_UPDATED_AT" ]] || {
		dcp_ao_fail 'Stage 6 direct install Action fence differs'; return 1;
	}
	counts="$(dcp_ao_repo_only_policy_scalar "$lab_root" \
		'SELECT (SELECT count(*) FROM dcp_v2_task) || "|" || (SELECT count(*) FROM dcp_v2_revision) || "|" || (SELECT count(*) FROM dcp_v2_command) || "|" || (SELECT count(*) FROM dcp_v2_action) || "|" || (SELECT count(*) FROM dcp_v2_admission) || "|" || (SELECT count(*) FROM dcp_v2_incident) || "|" || (SELECT count(*) FROM dcp_v2_external_event) || "|" || (SELECT count(*) FROM dcp_v2_result);')" || return 1
	[[ "$counts" == '1|1|1|1|0|0|0|0' ]] || { dcp_ao_fail 'Stage 6 direct install lifecycle counts differ'; return 1; }
	direct_tables="$(dcp_ao_repo_only_policy_scalar "$lab_root" \
		"SELECT count(*) FROM sqlite_master WHERE type='table' AND name IN ('dcp_v2_model_runtime','dcp_v2_model_terminal_receipt','dcp_v2_stage6_worker_adoption_v1');")" || return 1
	if [[ "$expected_schema" == 85 ]]; then
		[[ "$direct_tables" == 0 ]] || { dcp_ao_fail 'Stage 6 direct tables appeared before migration 0086'; return 1; }
	else
		[[ "$direct_tables" == 3 ]] || { dcp_ao_fail 'Stage 6 direct tables are incomplete after migration 0086'; return 1; }
		direct_rows="$(dcp_ao_repo_only_policy_scalar "$lab_root" \
			'SELECT (SELECT count(*) FROM dcp_v2_model_runtime) || "|" || (SELECT count(*) FROM dcp_v2_model_terminal_receipt) || "|" || (SELECT count(*) FROM dcp_v2_stage6_worker_adoption_v1);')" || return 1
		[[ "$direct_rows" == '0|0|0' ]] || { dcp_ao_fail 'Stage 6 direct migration consumed adoption or runtime state'; return 1; }
		migration_rows="$(dcp_ao_repo_only_policy_scalar "$lab_root" "SELECT count(*) FROM goose_db_version WHERE version_id=$expected_schema AND is_applied=1;")" || return 1
		[[ "$migration_rows" == 1 ]] || { dcp_ao_fail 'Stage 6 direct migration cardinality differs'; return 1; }
	fi
	native="$(dcp_ao_repo_only_policy_scalar "$lab_root" \
		"SELECT task_id || '|' || payload_digest || '|' || state || '|' || revision || '|' || repair_count || '|' || session_id || '|' || card_number || '|' || source_branch || '|' || current_head_sha || '|' || pr_url || '|' || pr_number || '|' || review_run_id || '|' || admission_id || '|' || release_phase || '|' || merge_commit_sha || '|' || error_code FROM dcp_review_lab_policy_task WHERE task_id='$DCP_AO_TWIN_STAGE6_TASK_ID';")" || return 1
	[[ "$native" == "$DCP_AO_TWIN_STAGE6_TASK_ID|$DCP_AO_TWIN_STAGE6_NATIVE_PAYLOAD_DIGEST|ci_waiting|4|0|dcp-wbc-integration-lab-1|1|$DCP_AO_TWIN_STAGE6_WORKER_BRANCH|||0|||||" ]] || {
		dcp_ao_fail 'Stage 6 direct install historical native card fence differs'; return 1;
	}
	session="$(dcp_ao_repo_only_policy_scalar "$lab_root" \
		"SELECT id || '|' || activity_state || '|' || is_terminated || '|' || runtime_handle_id || '|' || runtime_launch_id || '|' || branch || '|' || workspace_path FROM sessions WHERE id='dcp-wbc-integration-lab-1';")" || return 1
	[[ "$session" == "dcp-wbc-integration-lab-1|idle|0|dcp-wbc-integration-lab-1||$DCP_AO_TWIN_STAGE6_WORKER_BRANCH|$lab_root/data/worktrees/dcp-wbc-integration-lab/dcp-wbc-integration-lab-1" ]] || {
		dcp_ao_fail 'Stage 6 direct install historical native session fence differs'; return 1;
	}
	native_action="$(dcp_ao_repo_only_policy_scalar "$lab_root" \
		"SELECT sequence || '|' || id || '|' || task_id || '|' || session_id || '|' || kind || '|' || exact_head_sha || '|' || status || '|' || slot || '|' || launch_id || '|' || review_run_id || '|' || incident_id || '|' || error_code FROM dcp_model_action WHERE sequence=$DCP_AO_TWIN_STAGE6_NATIVE_ACTION_SEQUENCE;")" || return 1
	[[ "$native_action" == "$DCP_AO_TWIN_STAGE6_NATIVE_ACTION_SEQUENCE|$DCP_AO_TWIN_STAGE6_NATIVE_ACTION_ID|$DCP_AO_TWIN_STAGE6_TASK_ID|dcp-wbc-integration-lab-1|initial_worker||succeeded|0|$DCP_AO_TWIN_STAGE6_DIRECT_RUNTIME_ID|||" ]] || {
		dcp_ao_fail 'Stage 6 direct install terminal native Action fence differs'; return 1;
	}
	model_counts="$(dcp_ao_repo_only_policy_scalar "$lab_root" \
		"SELECT count(*) || '|' || sum(CASE WHEN status IN ('claimed','running') THEN 1 ELSE 0 END) || '|' || sum(CASE WHEN sequence <= $DCP_AO_TWIN_STAGE6_NATIVE_PREDECESSOR_ACTIONS THEN 1 ELSE 0 END) FROM dcp_model_action;")" || return 1
	[[ "$model_counts" == "$DCP_AO_TWIN_STAGE6_NATIVE_ACTION_SEQUENCE|0|$DCP_AO_TWIN_STAGE6_NATIVE_PREDECESSOR_ACTIONS" ]] || {
		dcp_ao_fail 'Stage 6 direct install native model Action counts differ'; return 1;
	}
	dcp_ao_verify_twin_stage6_direct_worker_checkout "$lab_root" || return 1
	dcp_ao_install_assert_no_active_model_actions "$lab_root" || return 1
}

dcp_ao_verify_twin_stage6_adopted_fence() {
	local lab_root="$1" require_stopped="${2:-1}" task revision commands action counts direct_rows active_rows adoption foreign_keys migration_rows model_counts
	dcp_ao_verify_twin_stopped_activation "$lab_root" "$require_stopped" 0 || return 1
	[[ "$(dcp_ao_repo_only_policy_scalar "$lab_root" 'SELECT max(version_id) FROM goose_db_version WHERE is_applied=1;')" == 87 ]] || {
		dcp_ao_fail 'Stage 6 adopted fence requires exact schema 87'; return 1;
	}
	foreign_keys="$(dcp_ao_repo_only_policy_scalar "$lab_root" 'PRAGMA foreign_key_check;')" || return 1
	[[ -z "$foreign_keys" ]] || { dcp_ao_fail 'Stage 6 adopted foreign-key check failed'; return 1; }
	migration_rows="$(dcp_ao_repo_only_policy_scalar "$lab_root" 'SELECT count(*) FROM goose_db_version WHERE version_id=87 AND is_applied=1;')" || return 1
	[[ "$migration_rows" == 1 ]] || { dcp_ao_fail 'Stage 6 schema-87 migration cardinality differs'; return 1; }
	task="$(dcp_ao_repo_only_policy_scalar "$lab_root" \
		"SELECT task_id || '|' || state || '|' || state_revision || '|' || current_revision_id || '|' || terminal_result_id || '|' || error_code FROM dcp_v2_task;")" || return 1
	[[ "$task" =~ ^${DCP_AO_TWIN_STAGE6_TASK_ID}\|checks_waiting\|2\|v2-[0-9a-f]{40}\|\|$ ]] || {
		dcp_ao_fail 'Stage 6 adopted Task fence differs'; return 1;
	}
	revision="$(dcp_ao_repo_only_policy_scalar "$lab_root" \
		"SELECT task_id || '|' || sequence || '|' || kind || '|' || base_sha || '|' || head_ref || '|' || head_sha || '|' || tree_sha || '|' || predecessor_revision_id || '|' || cause_command_id || '|' || pr_number FROM dcp_v2_revision WHERE sequence=2;")" || return 1
	[[ "$revision" == "$DCP_AO_TWIN_STAGE6_TASK_ID|2|worker_output|$DCP_AO_TWIN_STAGE5_BASE_SHA|$DCP_AO_TWIN_STAGE6_WORKER_BRANCH|$DCP_AO_TWIN_STAGE6_WORKER_COMMIT|$DCP_AO_TWIN_STAGE6_WORKER_TREE|$DCP_AO_TWIN_STAGE6_REVISION_ID|$DCP_AO_TWIN_STAGE6_COMMAND_ID|0" ]] || {
		dcp_ao_fail 'Stage 6 adopted Worker-output Revision fence differs'; return 1;
	}
	commands="$(dcp_ao_repo_only_policy_scalar "$lab_root" \
		"SELECT group_concat(sequence || '|' || kind || '|' || status || '|' || revision_id || '|' || effect_fence, ';') FROM (SELECT sequence,kind,status,revision_id,effect_fence FROM dcp_v2_command ORDER BY sequence);")" || return 1
	[[ "$commands" =~ ^1\|worker.execute/v1\|succeeded\|${DCP_AO_TWIN_STAGE6_REVISION_ID}\|model:${DCP_AO_TWIN_STAGE6_ACTION_ID}\;2\|publication.execute/v1\|pending\|v2-[0-9a-f]{40}\|$ ]] || {
		dcp_ao_fail 'Stage 6 adopted Command chain differs'; return 1;
	}
	action="$(dcp_ao_repo_only_policy_scalar "$lab_root" \
		"SELECT action_id || '|' || status || '|' || slot || '|' || runtime_id || '|' || length(result_digest) || '|' || error_code FROM dcp_v2_action;")" || return 1
	[[ "$action" == "$DCP_AO_TWIN_STAGE6_ACTION_ID|succeeded|0|$DCP_AO_TWIN_STAGE6_DIRECT_RUNTIME_ID|64|" ]] || {
		dcp_ao_fail 'Stage 6 adopted Worker Action fence differs'; return 1;
	}
	counts="$(dcp_ao_repo_only_policy_scalar "$lab_root" \
		'SELECT (SELECT count(*) FROM dcp_v2_task) || "|" || (SELECT count(*) FROM dcp_v2_revision) || "|" || (SELECT count(*) FROM dcp_v2_command) || "|" || (SELECT count(*) FROM dcp_v2_action) || "|" || (SELECT count(*) FROM dcp_v2_admission) || "|" || (SELECT count(*) FROM dcp_v2_incident) || "|" || (SELECT count(*) FROM dcp_v2_external_event) || "|" || (SELECT count(*) FROM dcp_v2_result);')" || return 1
	[[ "$counts" == '1|2|2|1|0|0|0|0' ]] || { dcp_ao_fail 'Stage 6 adopted lifecycle counts differ'; return 1; }
	direct_rows="$(dcp_ao_repo_only_policy_scalar "$lab_root" \
		'SELECT (SELECT count(*) FROM dcp_v2_model_runtime) || "|" || (SELECT count(*) FROM dcp_v2_model_terminal_receipt) || "|" || (SELECT count(*) FROM dcp_v2_stage6_worker_adoption_v1);')" || return 1
	[[ "$direct_rows" == '1|1|1' ]] || { dcp_ao_fail 'Stage 6 adoption direct-row cardinality differs'; return 1; }
	active_rows="$(dcp_ao_repo_only_policy_scalar "$lab_root" \
		"SELECT (SELECT count(*) FROM dcp_v2_model_runtime WHERE state IN ('reserved','running')) || '|' || (SELECT count(*) FROM dcp_v2_action WHERE status IN ('launching','running'));")" || return 1
	[[ "$active_rows" == '0|0' ]] || { dcp_ao_fail 'Stage 6 adoption left an active DCP-v2 model slot'; return 1; }
	adoption="$(dcp_ao_repo_only_policy_scalar "$lab_root" \
		"SELECT adoption_id || '|' || task_id || '|' || revision_id || '|' || command_id || '|' || action_id || '|' || runtime_id || '|' || native_action_id || '|' || native_sequence || '|' || commit_sha || '|' || tree_sha || '|' || branch FROM dcp_v2_stage6_worker_adoption_v1;")" || return 1
	[[ "$adoption" == "dcp-v2-stage6-worker-adoption-v1|$DCP_AO_TWIN_STAGE6_TASK_ID|$DCP_AO_TWIN_STAGE6_REVISION_ID|$DCP_AO_TWIN_STAGE6_COMMAND_ID|$DCP_AO_TWIN_STAGE6_ACTION_ID|$DCP_AO_TWIN_STAGE6_DIRECT_RUNTIME_ID|$DCP_AO_TWIN_STAGE6_NATIVE_ACTION_ID|$DCP_AO_TWIN_STAGE6_NATIVE_ACTION_SEQUENCE|$DCP_AO_TWIN_STAGE6_WORKER_COMMIT|$DCP_AO_TWIN_STAGE6_WORKER_TREE|$DCP_AO_TWIN_STAGE6_WORKER_BRANCH" ]] || {
		dcp_ao_fail 'Stage 6 adoption immutable identity differs'; return 1;
	}
	model_counts="$(dcp_ao_repo_only_policy_scalar "$lab_root" \
		"SELECT count(*) || '|' || sum(CASE WHEN status IN ('claimed','running') THEN 1 ELSE 0 END) FROM dcp_model_action;")" || return 1
	[[ "$model_counts" == "$DCP_AO_TWIN_STAGE6_NATIVE_ACTION_SEQUENCE|0" ]] || { dcp_ao_fail 'Stage 6 adoption changed native model Action counts'; return 1; }
	dcp_ao_verify_twin_stage6_direct_worker_checkout "$lab_root" || return 1
	dcp_ao_install_assert_no_active_model_actions "$lab_root" || return 1
}

dcp_ao_stage6_gh_api() { gh api "$@"; }

dcp_ao_verify_twin_stage6_external_fence() {
	local main pulls refs runs wbc
	dcp_ao_require_tool gh || return 1
	main="$(dcp_ao_stage6_gh_api "repos/orenvlad-ai/dcp-wbc-integration-lab/git/ref/heads/main")" || return 1
	printf '%s' "$main" | /usr/bin/jq -e --arg sha "$DCP_AO_TWIN_STAGE5_BASE_SHA" \
		'type == "object" and .object.sha == $sha' >/dev/null || { dcp_ao_fail 'Stage 6 target main drifted'; return 1; }
	pulls="$(dcp_ao_stage6_gh_api 'repos/orenvlad-ai/dcp-wbc-integration-lab/pulls?state=open&per_page=100')" || return 1
	printf '%s' "$pulls" | /usr/bin/jq -e 'type == "array" and length == 0' >/dev/null || {
		dcp_ao_fail 'Stage 6 target has an unexpected open PR'; return 1;
	}
	refs="$(dcp_ao_stage6_gh_api 'repos/orenvlad-ai/dcp-wbc-integration-lab/git/matching-refs/heads/ao/dcp-wbc-integration-lab-1/root')" || return 1
	printf '%s' "$refs" | /usr/bin/jq -e 'type == "array" and length == 0' >/dev/null || {
		dcp_ao_fail 'Stage 6 target native branch already has a provider effect'; return 1;
	}
	runs="$(dcp_ao_stage6_gh_api 'repos/orenvlad-ai/dcp-wbc-integration-lab/actions/runs?per_page=100')" || return 1
	printf '%s' "$runs" | /usr/bin/jq -e --arg since '2026-08-20T17:16:00Z' '
		type == "object" and (.workflow_runs | type == "array") and
		([.workflow_runs[] | select(.created_at >= $since and (.event == "repository_dispatch" or .head_branch == "ao/dcp-wbc-integration-lab-1/root"))] | length == 0)
	' >/dev/null || { dcp_ao_fail 'Stage 6 target already has a canary provider run'; return 1; }
	wbc="$(dcp_ao_stage6_gh_api 'repos/orenvlad-ai/wb-core/pulls/987')" || return 1
	printf '%s' "$wbc" | /usr/bin/jq -e --arg head "$DCP_AO_TWIN_STAGE6_WBC_PR_HEAD" '
		type == "object" and .number == 987 and .state == "open" and .draft == false and .merged == false and
		.base.ref == "main" and .head.repo.full_name == "orenvlad-ai/wb-core" and .head.sha == $head
	' >/dev/null || { dcp_ao_fail 'frozen WBC PR 987 boundary drifted'; return 1; }
}

dcp_ao_validate_twin_stage6_aggregate_response() {
	local receipt_sha="$1" response="$2" duplicate_paths
	[[ "$receipt_sha" =~ ^[0-9a-f]{64}$ ]] || { dcp_ao_fail 'Stage 6 aggregate response receipt identity is malformed'; return 1; }
	duplicate_paths="$(printf '%s' "$response" | /usr/bin/jq --stream -s -r '
		[.[] | select(length == 2) | .[0] | map(tostring) | join(".")]
		| group_by(.) | map(select(length != 1) | .[0]) | join(",")
	')" || { dcp_ao_fail 'Stage 6 aggregate response is not valid JSON'; return 1; }
	[[ -z "$duplicate_paths" ]] || { dcp_ao_fail 'Stage 6 aggregate response contains duplicate fields'; return 1; }
	printf '%s' "$response" | /usr/bin/jq -e \
		--arg source "$DCP_AO_FORK_COMMIT" --arg tree "$DCP_AO_FORK_TREE" --arg receipt "$receipt_sha" \
		--arg predecessor_source "$DCP_AO_TWIN_STAGE6_RECOVERY_SOURCE_COMMIT" \
		--arg predecessor_tree "$DCP_AO_TWIN_STAGE6_RECOVERY_SOURCE_TREE" \
		--arg predecessor_receipt "$DCP_AO_TWIN_STAGE6_RECOVERY_RECEIPT_SHA256" \
		--arg task "$DCP_AO_TWIN_STAGE6_TASK_ID" --arg revision "$DCP_AO_TWIN_STAGE6_REVISION_ID" \
		--arg command "$DCP_AO_TWIN_STAGE6_COMMAND_ID" --arg action "$DCP_AO_TWIN_STAGE6_ACTION_ID" \
		--arg native_action "$DCP_AO_TWIN_STAGE6_NATIVE_ACTION_ID" --arg base "$DCP_AO_TWIN_STAGE5_BASE_SHA" '
		type == "object" and keys == ["actionId","baseSha","commandId","installReceiptSha","installedSourceCommit","installedSourceTree","nativeActionId","nativeCardNumber","nativeSessionId","predecessorReceiptSha","predecessorSourceCommit","predecessorSourceTree","ready","revisionId","schemaVersion","taskId"] and
		.schemaVersion == "dcp.v2.stage6-aggregate-install/v1" and .installedSourceCommit == $source and
		.installedSourceTree == $tree and .installReceiptSha == $receipt and
		.predecessorSourceCommit == $predecessor_source and .predecessorSourceTree == $predecessor_tree and
		.predecessorReceiptSha == $predecessor_receipt and .taskId == $task and .revisionId == $revision and
		.commandId == $command and .actionId == $action and .nativeSessionId == "dcp-wbc-integration-lab-1" and
		.nativeCardNumber == 1 and .nativeActionId == $native_action and .baseSha == $base and .ready == true
	' >/dev/null || { dcp_ao_fail 'Stage 6 aggregate response differs from the exact lower-camel identity'; return 1; }
}

dcp_ao_twin_stage6_aggregate_response() {
	local receipt_sha="$1"
	/usr/bin/jq -cn \
		--arg source "$DCP_AO_FORK_COMMIT" --arg tree "$DCP_AO_FORK_TREE" --arg receipt "$receipt_sha" \
		--arg predecessor_source "$DCP_AO_TWIN_STAGE6_RECOVERY_SOURCE_COMMIT" \
		--arg predecessor_tree "$DCP_AO_TWIN_STAGE6_RECOVERY_SOURCE_TREE" \
		--arg predecessor_receipt "$DCP_AO_TWIN_STAGE6_RECOVERY_RECEIPT_SHA256" \
		--arg task "$DCP_AO_TWIN_STAGE6_TASK_ID" --arg revision "$DCP_AO_TWIN_STAGE6_REVISION_ID" \
		--arg command "$DCP_AO_TWIN_STAGE6_COMMAND_ID" --arg action "$DCP_AO_TWIN_STAGE6_ACTION_ID" \
		--arg native_action "$DCP_AO_TWIN_STAGE6_NATIVE_ACTION_ID" --arg base "$DCP_AO_TWIN_STAGE5_BASE_SHA" '
		{schemaVersion:"dcp.v2.stage6-aggregate-install/v1",installedSourceCommit:$source,installedSourceTree:$tree,
		installReceiptSha:$receipt,predecessorSourceCommit:$predecessor_source,predecessorSourceTree:$predecessor_tree,
		predecessorReceiptSha:$predecessor_receipt,taskId:$task,revisionId:$revision,commandId:$command,actionId:$action,
		nativeSessionId:"dcp-wbc-integration-lab-1",nativeCardNumber:1,nativeActionId:$native_action,baseSha:$base,ready:true}'
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
			[[ "$profile" == repo-only || "$profile" == live-runtime ]] || {
				dcp_ao_fail 'locked wb-core submit received a foreign profile'; return 1;
			}
			[[ "$(dcp_ao_validate_wb_core_target "$lab_root" 1)" == "$target" ]] || return 1
			dcp_ao_require_wb_core_compatibility "$target" || return 1
			;;
		dcp-wbc-integration-lab)
			[[ "$profile" == live-runtime && "$task_id" == dcp-v2-twin-canary-v1 ]] || {
				dcp_ao_fail 'locked integration-twin submit received a foreign identity'; return 1;
			}
			[[ "$(dcp_ao_validate_twin_target "$lab_root" 1 1)" == "$target" ]] || return 1
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
		spawn_output="$("$cli" dcp submit --target wb-core --profile "$profile" \
			--repository orenvlad-ai/wb-core --task-id "$task_id" --prompt "$prompt" --json)" || return 1
		dcp_ao_validate_policy_submit_response "$lab_root" "$task_id" wb-core "$profile" "$spawn_output" || return 1
	elif [[ "$target_name" == dcp-wbc-integration-lab ]]; then
		spawn_output="$(dcp_ao_submit_v2_twin_once "$task_id" "$prompt")" || return 1
		dcp_ao_validate_v2_twin_submit_response "$lab_root" "$task_id" "$spawn_output" || return 1
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
	if [[ "$target_name" == dcp-review-lab || "$target_name" == wb-browser-extension || "$target_name" == wb-core || "$target_name" == dcp-wbc-integration-lab ]]; then
		return 0
	fi
	printf '%s\n' "$spawn_output"
	session_id="$(printf '%s\n' "$spawn_output" | sed -n 's/^spawned session \([^ ]*\).*/\1/p')"
	if [[ -z "$session_id" ]]; then dcp_ao_fail 'AO did not return a session id'; return 1; fi
	printf 'session_id=%s\n' "$session_id"
}

dcp_ao_submit_v2_twin_once() {
	local task_id="$1" prompt="$2" payload port
	dcp_ao_require_tool curl || return 1
	payload="$(/usr/bin/jq -cn --arg task "$task_id" --arg prompt "$prompt" '{taskId:$task,prompt:$prompt}')" || return 1
	port="${DCP_AO_PORT:-43231}"
	curl --silent --show-error --fail-with-body --connect-timeout 5 --max-time 120 \
		--request POST --header 'Content-Type: application/json' --data-binary "$payload" \
		"http://127.0.0.1:$port/api/v1/dcp/v2/tasks"
}

dcp_ao_validate_v2_twin_submit_response() {
	local lab_root="$1" task_id="$2" response="$3" session card worktree branch
	printf '%s' "$response" | /usr/bin/jq -e --arg task "$task_id" \
		'.task.TaskID == $task and .task.TargetSpecVersion == "dcp-wbc-integration-lab/v2" and .task.Repository == "orenvlad-ai/dcp-wbc-integration-lab" and .task.RepositoryID == 1340359100 and .task.OwnerID == 237411244 and .task.BaseRef == "main" and .task.Profile == "live-runtime" and .task.InitialWorkerBudget == 1 and .task.RepairBudget == 1 and .task.MaxReadmissions == 2 and (.task.StateRevision >= 1) and (.task.CurrentRevisionID | length > 0) and .native.taskId == $task and .native.target == "dcp-wbc-integration-lab" and .native.profile == "live-runtime" and .native.repository == "orenvlad-ai/dcp-wbc-integration-lab" and (.duplicate | type == "boolean") and (.projection.phase | length > 0)' >/dev/null || {
		dcp_ao_fail 'DCP v2 submit response immutable identity drifted'; return 1;
	}
	session="$(printf '%s' "$response" | /usr/bin/jq -er '.native.sessionId')" || return 1
	card="$(printf '%s' "$response" | /usr/bin/jq -er '.native.cardNumber')" || return 1
	worktree="$(printf '%s' "$response" | /usr/bin/jq -er '.native.worktreePath')" || return 1
	branch="$(printf '%s' "$response" | /usr/bin/jq -er '.native.sourceBranch')" || return 1
	[[ "$session" =~ ^dcp-wbc-integration-lab-([1-9][0-9]*)$ && "${BASH_REMATCH[1]}" == "$card" && \
		"$worktree" == "$lab_root/data/worktrees/dcp-wbc-integration-lab/$session" && "$branch" == "ao/$session/root" ]] || {
		dcp_ao_fail 'DCP v2 native runtime resource identity drifted'; return 1;
	}
	printf 'task_id=%s\nrevision_id=%s\nstate=%s\nstate_revision=%s\nsession_id=%s\ncard_number=%s\nworktree=%s\nbranch=%s\nduplicate=%s\nmodel_active=%s\nworkflow_active=%s\n' \
		"$task_id" "$(printf '%s' "$response" | /usr/bin/jq -er '.task.CurrentRevisionID')" \
		"$(printf '%s' "$response" | /usr/bin/jq -er '.task.State')" "$(printf '%s' "$response" | /usr/bin/jq -er '.task.StateRevision')" \
		"$session" "$card" "$worktree" "$branch" "$(printf '%s' "$response" | /usr/bin/jq -er '.duplicate')" \
		"$(printf '%s' "$response" | /usr/bin/jq -er '.projection.modelActive')" "$(printf '%s' "$response" | /usr/bin/jq -er '.projection.workflowActive')"
}

dcp_ao_validate_policy_submit_response() {
	local lab_root="$1" task_id="$2" target_name="$3" profile="$4" response="$5"
	local session_id card_number worktree branch state revision duplicate minimum=1 repository
	case "$target_name|$profile" in
		dcp-review-lab\|synthetic-pr) repository=orenvlad-ai/dcp-review-lab ;;
		wb-browser-extension\|repo-only) repository=orenvlad-ai/wb-browser-extension ;;
		wb-core\|repo-only|wb-core\|live-runtime) repository=orenvlad-ai/wb-core ;;
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
		bin/dcp-ao-submit --target wb-core --profile live-runtime --task-id task-id --prompt 'one short prompt'
		bin/dcp-ao-submit --target dcp-wbc-integration-lab --profile live-runtime --task-id dcp-v2-twin-canary-v1 --prompt 'one short prompt'

The default lab target is disposable and remote-free. Synthetic-pr, repo-only
and exact wb-core live-runtime profiles are fixed to their public repositories
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
			[[ "$profile" == repo-only || "$profile" == live-runtime ]] || { dcp_ao_fail 'wb-core requires --profile repo-only or live-runtime'; return 1; }
			dcp_ao_validate_task_id "$task_id" || return 1
			target="$lab_root/targets/wb-core"
			;;
		dcp-wbc-integration-lab)
			[[ "$profile" == live-runtime ]] || { dcp_ao_fail 'integration-twin requires --profile live-runtime'; return 1; }
			dcp_ao_validate_twin_task_id "$task_id" || return 1
			target="$lab_root/targets/dcp-wbc-integration-lab"
			;;
		*) dcp_ao_fail 'only --target dcp-lab or one exact governed public target is allowed'; return 1 ;;
	esac
	cli="$(dcp_ao_resolve_cli "$lab_root")" || return 1
	dcp_ao_gateway_with_lock "$lab_root" "$cli" dcp_ao_submit_locked "$target_name" "$profile" "$task_id" "$target" "$prompt"
}
