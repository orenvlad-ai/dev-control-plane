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

dcp_ao_validate_target() {
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

dcp_ao_resolve_cli() {
	local lab_root="$1"
	dcp_ao_preflight_exact_contour "$lab_root"
	local cli
	cli="$(dcp_ao_embedded_cli)"
	if [[ ! -x "$cli" ]]; then dcp_ao_fail 'packaged DCP daemon/CLI is absent'; return 1; fi
	printf '%s\n' "$cli"
}

dcp_ao_submit_locked() {
	local lab_root="$1" cli="$2" target="$3" prompt="$4"
	local status projects details spawn_output session_id
	dcp_ao_gateway_ensure_locked "$lab_root" "$cli" || return 1
	dcp_ao_export_runtime_env "$lab_root"
	dcp_ao_preflight_codex_worker "$lab_root" || return 1
	status="$("$cli" status --json)"
	if ! printf '%s' "$status" | grep -Fq '"state": "ready"'; then dcp_ao_fail 'isolated AO daemon is not ready'; return 1; fi
	dcp_ao_gateway_assert_pair "$lab_root" "$status" || return 1

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
	printf '%s\n' "$spawn_output"
	session_id="$(printf '%s\n' "$spawn_output" | sed -n 's/^spawned session \([^ ]*\).*/\1/p')"
	if [[ -z "$session_id" ]]; then dcp_ao_fail 'AO did not return a session id'; return 1; fi
	printf 'session_id=%s\n' "$session_id"
}

dcp_ao_submit() {
	local target_name='' prompt=''
	if [[ "${1:-}" == '-h' || "${1:-}" == '--help' ]]; then
		cat <<'EOF'
Usage: bin/dcp-ao-submit --target dcp-lab --prompt 'one short prompt'

The target is fixed to the disposable remote-free DCP lab repository. The
prompt must be one line and no more than 512 UTF-8 bytes.
EOF
		return 0
	fi
	while [[ "$#" -gt 0 ]]; do
		case "$1" in
			--target)
				if [[ "$#" -lt 2 ]]; then dcp_ao_fail '--target requires a value'; return 1; fi
				target_name="$2"
				shift 2
				;;
			--prompt)
				if [[ "$#" -lt 2 ]]; then dcp_ao_fail '--prompt requires a value'; return 1; fi
				prompt="$2"
				shift 2
				;;
			*) dcp_ao_fail "unknown argument: $1" ; return 1 ;;
		esac
	done
	if [[ "$target_name" != 'dcp-lab' ]]; then
		dcp_ao_fail 'only --target dcp-lab is allowed'
		return 1
	fi
	dcp_ao_validate_prompt "$prompt" || return 1
	local lab_root target cli
	lab_root="$(dcp_ao_require_lab_root)" || return 1
	target="$(dcp_ao_validate_target "$lab_root")" || return 1
	cli="$(dcp_ao_resolve_cli "$lab_root")" || return 1
	dcp_ao_gateway_with_lock "$lab_root" "$cli" dcp_ao_submit_locked "$target" "$prompt"
}
