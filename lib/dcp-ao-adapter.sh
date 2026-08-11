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
	printf '%s\n' "DCP synthetic PR profile v2. Work only in this exact synthetic repository and the current AO branch. Do not create subagents, extra branches, worktrees, remotes, additional pull requests, or network services. On the initial call implement only the direct task, create one commit, push the current branch, open one ready pull request targeting main, and then stop. Only if the trusted DCP daemon issues the single bounded admission-refresh continuation may the same worker rebase that branch onto the exact named origin/main, keep the same pull request, push with exact force-with-lease, and stop; abort without push on any conflict or ambiguity. Do not merge; only the trusted DCP daemon may perform terminal merge after exact-head review, checks, and admission."
}

dcp_ao_review_config_json() {
	printf '%s\n' "{\"defaultBranch\":\"main\",\"sessionPrefix\":\"dcp-review-lab\",\"worker\":{\"agent\":\"codex\",\"agentConfig\":{\"permissions\":\"accept-edits\",\"dcpReviewLabNetwork\":true}},\"reviewers\":[{\"harness\":\"codex\"}],\"agentRules\":\"$(dcp_ao_review_agent_rules)\"}"
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
					[[ "$session_id" =~ ^dcp-review-lab-[6-9]$ && "$branch" == "refs/heads/ao/$session_id/root" ]] || {
						dcp_ao_fail "dcp-review-lab linked worktree identity mismatch: $path"; return 1;
					}
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
	local status projects details spawn_output session_id expected_session_id
	if [[ "$target_name" == dcp-review-lab ]]; then
		[[ "$(dcp_ao_validate_review_target "$lab_root" 0)" == "$target" ]] || return 1
	else
		[[ "$(dcp_ao_validate_remote_free_target "$lab_root")" == "$target" ]] || return 1
	fi
	dcp_ao_gateway_ensure_locked "$lab_root" "$cli" || return 1
	dcp_ao_export_runtime_env "$lab_root"
	dcp_ao_preflight_codex_worker "$lab_root" || return 1
	status="$("$cli" status --json)"
	if ! printf '%s' "$status" | grep -Fq '"state": "ready"'; then dcp_ao_fail 'isolated AO daemon is not ready'; return 1; fi
	dcp_ao_gateway_assert_pair "$lab_root" "$status" || return 1

	if [[ "$target_name" == dcp-review-lab ]]; then
		dcp_ao_prepare_review_project "$cli" "$target" || return 1
		expected_session_id="$(dcp_ao_reject_duplicate_review_task "$cli" "$task_id")" || return 1
		spawn_output="$("$cli" spawn --project dcp-review-lab --kind worker --name "DCP:$task_id" --harness codex --prompt "DCP synthetic task $task_id: $prompt")"
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
	printf '%s\n' "$spawn_output"
	session_id="$(printf '%s\n' "$spawn_output" | sed -n 's/^spawned session \([^ ]*\).*/\1/p')"
	if [[ -z "$session_id" ]]; then dcp_ao_fail 'AO did not return a session id'; return 1; fi
	if [[ "$target_name" == dcp-review-lab ]]; then
		[[ "$session_id" == "$expected_session_id" ]] || { dcp_ao_fail 'AO returned an unexpected or out-of-cohort dcp-review-lab session id'; return 1; }
		printf 'profile=%s\ntask_id=%s\n' "$profile" "$task_id"
	fi
	printf 'session_id=%s\n' "$session_id"
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

dcp_ao_reject_duplicate_review_task() {
	local cli="$1" task_id="$2" sessions index=0 session_id details display_name stage_mask=0 seen='|'
	sessions="$("$cli" session ls --project dcp-review-lab --all --include-terminated --json)" || return 1
	printf '%s' "$sessions" | /usr/bin/jq -e '.data | type == "array"' >/dev/null 2>&1 || { dcp_ao_fail 'AO session list was malformed'; return 1; }
	while session_id="$(dcp_ao_json_extract "$sessions" "data.$index.id")"; do
		[[ "$session_id" =~ ^dcp-review-lab-([1-9])$ ]] || { dcp_ao_fail "AO returned an out-of-cohort dcp-review-lab session: $session_id"; return 1; }
		[[ "$seen" != *"|$session_id|"* ]] || { dcp_ao_fail "AO returned duplicate dcp-review-lab session identity: $session_id"; return 1; }
		seen="${seen}${session_id}|"
		case "$session_id" in
			dcp-review-lab-8) stage_mask=$((stage_mask | 1)) ;;
			dcp-review-lab-9) stage_mask=$((stage_mask | 2)) ;;
		esac
		details="$("$cli" session get "$session_id" --project dcp-review-lab --json)" || return 1
		[[ "$(dcp_ao_json_extract "$details" session.id)" == "$session_id" ]] || { dcp_ao_fail 'AO session lookup identity mismatch'; return 1; }
		[[ "$(dcp_ao_json_extract "$details" session.projectId)" == dcp-review-lab ]] || { dcp_ao_fail 'AO returned a foreign session for dcp-review-lab'; return 1; }
		display_name="$(dcp_ao_json_extract "$details" session.displayName)" || { dcp_ao_fail 'AO session identity was malformed'; return 1; }
		[[ "$display_name" != "DCP:$task_id" ]] || { dcp_ao_fail "task id already exists: $task_id"; return 1; }
		index=$((index + 1))
	done
	case "$stage_mask" in
		0) printf '%s\n' dcp-review-lab-8 ;;
		1) printf '%s\n' dcp-review-lab-9 ;;
		2) dcp_ao_fail 'I13 admission cohort is incomplete: card 9 exists without card 8'; return 1 ;;
		3) dcp_ao_fail 'I13 admission cohort already contains both bounded tasks'; return 1 ;;
		*) dcp_ao_fail 'I13 admission cohort state is invalid'; return 1 ;;
	esac
}

dcp_ao_submit() {
	local target_name='' profile='' task_id='' prompt=''
	local target_seen=0 profile_seen=0 task_seen=0 prompt_seen=0
	if [[ "${1:-}" == '-h' || "${1:-}" == '--help' ]]; then
		cat <<'EOF'
Usage: bin/dcp-ao-submit --target dcp-lab --prompt 'one short prompt'
       bin/dcp-ao-submit --target dcp-review-lab --profile synthetic-pr --task-id task-id --prompt 'one short prompt'

The default lab target is disposable and remote-free. The synthetic-pr profile
is separately fixed to the exact DCP review-lab repository and a 1-16 character
task id. Prompts must be one line and no more than 512 UTF-8 bytes.
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
			target="$(dcp_ao_validate_review_target "$lab_root" 1)" || return 1
			;;
		*) dcp_ao_fail 'only --target dcp-lab or exact dcp-review-lab is allowed'; return 1 ;;
	esac
	cli="$(dcp_ao_resolve_cli "$lab_root")" || return 1
	dcp_ao_gateway_with_lock "$lab_root" "$cli" dcp_ao_submit_locked "$target_name" "$profile" "$task_id" "$target" "$prompt"
}
