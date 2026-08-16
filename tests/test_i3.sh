#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
export DCP_AO_LAB_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/dcp-ao-i3-test.XXXXXX")"
export DCP_AO_TEST_ALLOW_NONCANONICAL_LAB_ROOT=1
cleanup() {
	local status="$?"
	rm -rf "$DCP_AO_LAB_ROOT"
	return "$status"
}
trap cleanup EXIT

export DCP_AO_FAKE_LOG="$DCP_AO_LAB_ROOT/fake-ao.log"
"$REPO_ROOT/bin/dcp-ao" init-target >/dev/null

# shellcheck source=../lib/dcp-ao-common.sh
source "$REPO_ROOT/lib/dcp-ao-common.sh"
# shellcheck source=../lib/dcp-ao-gateway.sh
source "$REPO_ROOT/lib/dcp-ao-gateway.sh"
# shellcheck source=../lib/dcp-ao-adapter.sh
source "$REPO_ROOT/lib/dcp-ao-adapter.sh"
dcp_ao_export_runtime_env "$DCP_AO_LAB_ROOT"
dcp_ao_resolve_cli() { printf '%s\n' "$REPO_ROOT/tests/fixtures/fake-ao"; }
dcp_ao_preflight_codex_worker() { :; }
dcp_ao_gateway_ensure_locked() { :; }
dcp_ao_gateway_assert_pair() { :; }
dcp_ao_refresh_review_target() {
	[[ "${DCP_AO_TEST_SUBMIT_LOCK_HELD:-0}" == 1 ]] || {
		dcp_ao_fail 'review baseline refresh escaped the canonical submit lock'
		return 1
	}
	printf 'review-refresh-in-lock\n' >>"$DCP_AO_FAKE_LOG"
}
dcp_ao_refresh_repo_only_target() {
	[[ "${DCP_AO_TEST_SUBMIT_LOCK_HELD:-0}" == 1 ]] || {
		dcp_ao_fail 'repo-only baseline refresh escaped the canonical submit lock'
		return 1
	}
	printf 'repo-only-refresh-in-lock\n' >>"$DCP_AO_FAKE_LOG"
}
gh() {
	[[ "$1" == api ]] || { printf 'unexpected gh command\n' >&2; return 1; }
	case "$2" in
		repos/orenvlad-ai/dcp-review-lab)
			if [[ "${DCP_AO_FAKE_PROVIDER_PRIVATE:-0}" == 1 ]]; then
				printf '%s\n' 'orenvlad-ai/dcp-review-lab|true|main|1329007118|237411244'
			else
				printf '%s\n' 'orenvlad-ai/dcp-review-lab|false|main|1329007118|237411244'
			fi
			;;
		repos/orenvlad-ai/wb-browser-extension)
			if [[ "${DCP_AO_FAKE_REPO_ONLY_PROVIDER_OLD_NAME:-0}" == 1 ]]; then
				printf '%s\n' 'orenvlad-ai/wb-price-extension|false|main|1335072844|237411244'
			elif [[ "${DCP_AO_FAKE_REPO_ONLY_PROVIDER_PRIVATE:-0}" == 1 ]]; then
				printf '%s\n' 'orenvlad-ai/wb-browser-extension|true|main|1335072844|237411244'
			else
				printf '%s\n' 'orenvlad-ai/wb-browser-extension|false|main|1335072844|237411244'
			fi
			;;
		*) printf 'unexpected gh repository\n' >&2; return 1 ;;
	esac
}
dcp_ao_gateway_with_lock() {
	local lab_root="$1" cli="$2" callback="$3" result
	shift 3
	export DCP_AO_TEST_SUBMIT_LOCK_HELD=1
	if "$callback" "$lab_root" "$cli" "$@"; then result=0; else result=$?; fi
	unset DCP_AO_TEST_SUBMIT_LOCK_HELD
	return "$result"
}

[[ -z "${CODEX_HOME:-}" ]]
[[ "$CODEX_SQLITE_HOME" == "$DCP_AO_LAB_ROOT/data/codex-state" ]]
[[ "$DCP_AO_CODEX_ISOLATION" == exec-ignore-user-config ]]

# I12 may replace only the exact previously pinned managed-fork install. Prove
# that its receipt is accepted by content digest while a fork-tree mismatch is
# rejected, without touching the canonical application or state.
fake_app="$DCP_AO_LAB_ROOT/fake-app/DCP Orchestrator.app"
fake_daemon="$fake_app/Contents/Resources/daemon/dcp-orchestratord"
fake_asar="$fake_app/Contents/Resources/app.asar"
mkdir -p "$(dirname "$fake_daemon")"
printf 'prior daemon\n' >"$fake_daemon"
printf 'prior asar\n' >"$fake_asar"
dcp_ao_app_path() { printf '%s\n' "$fake_app"; }
dcp_ao_embedded_cli() { printf '%s\n' "$fake_daemon"; }
receipt="$(dcp_ao_install_receipt "$DCP_AO_LAB_ROOT")"
mkdir -p "$(dirname "$receipt")"
{
	printf 'schema=1\n'
	printf 'bundle_path=%s\n' "$fake_app"
	printf 'bundle_id=pro.devcontrol.dcp-orchestrator\n'
	printf 'fork_commit=%s\n' "$DCP_AO_PRIOR_FORK_COMMIT"
	printf 'fork_tree=%s\n' "$DCP_AO_PRIOR_FORK_TREE"
	printf 'upstream_commit=%s\n' "$DCP_AO_UPSTREAM_COMMIT"
	printf 'i8_parity_diff_sha256=%s\n' "$DCP_AO_I8_PARITY_DIFF_SHA256"
	printf 'daemon_sha256=%s\n' "$(dcp_ao_sha256 "$fake_daemon")"
	printf 'asar_sha256=%s\n' "$(dcp_ao_sha256 "$fake_asar")"
} >"$receipt"
dcp_ao_verify_replaceable_install_receipt "$DCP_AO_LAB_ROOT"
sed -i.bak "s/fork_tree=$DCP_AO_PRIOR_FORK_TREE/fork_tree=foreign/" "$receipt"
if dcp_ao_verify_replaceable_install_receipt "$DCP_AO_LAB_ROOT"; then
	printf 'foreign prior fork tree was accepted\n' >&2
	exit 1
fi
sed -i.bak "s/fork_commit=$DCP_AO_PRIOR_FORK_COMMIT/fork_commit=foreign/" "$receipt"
if dcp_ao_verify_replaceable_install_receipt "$DCP_AO_LAB_ROOT"; then
	printf 'foreign prior managed fork was accepted as a legacy receipt\n' >&2
	exit 1
fi

if (DCP_AO_LAB_ROOT="${HOME:?}/.ao"; dcp_ao_require_lab_root >/dev/null); then
	printf 'installed AO state root was accepted\n' >&2
	exit 1
fi
if (dcp_ao_submit --target real-repo --prompt 'safe'); then
	printf 'forbidden target was accepted\n' >&2
	exit 1
fi
if (dcp_ao_submit --target dcp-lab --profile synthetic-pr --task-id i7-terminal --prompt 'safe'); then
	printf 'remote-free target accepted a mutation profile\n' >&2
	exit 1
fi
if (dcp_ao_submit --target dcp-review-lab --prompt 'safe'); then
	printf 'review target accepted a missing profile/task id\n' >&2
	exit 1
fi
if (dcp_ao_submit --target dcp-review-lab --profile foreign --task-id i7-terminal --prompt 'safe'); then
	printf 'review target accepted a foreign profile\n' >&2
	exit 1
fi
if (dcp_ao_submit --target wb-browser-extension --profile synthetic-pr --task-id real-one --prompt 'safe'); then
	printf 'repo-only target accepted the synthetic profile\n' >&2
	exit 1
fi
if (dcp_ao_submit --target wb-price-extension --profile repo-only --task-id legacy-submit --prompt 'safe'); then
	printf 'legacy repo-only target accepted a future submit\n' >&2
	exit 1
fi
if (dcp_ao_submit --target dcp-review-lab --profile repo-only --task-id real-one --prompt 'safe'); then
	printf 'synthetic target accepted the repo-only profile\n' >&2
	exit 1
fi
if (dcp_ao_submit --target dcp-review-lab --profile synthetic-pr --task-id 'Too-Long-Or-Foreign' --prompt 'safe'); then
	printf 'review target accepted a foreign task id\n' >&2
	exit 1
fi
if (dcp_ao_submit --target dcp-lab --target dcp-lab --prompt 'safe'); then
	printf 'duplicate target option was accepted\n' >&2
	exit 1
fi
if (dcp_ao_submit --target dcp-lab --prompt 'line one
line two'); then
	printf 'multiline prompt was accepted\n' >&2
	exit 1
fi
long_prompt="$(printf 'x%.0s' {1..513})"
if (dcp_ao_submit --target dcp-lab --prompt "$long_prompt"); then
	printf 'oversized prompt was accepted\n' >&2
	exit 1
fi

output="$(dcp_ao_submit --target dcp-lab --prompt 'Create the safe marker only')"
printf '%s' "$output" | grep -Fq 'session_id=dcp-i3-0001'
[[ "$(grep -c '^spawn ' "$DCP_AO_FAKE_LOG")" -eq 1 ]]
grep -Fq 'project add --id dcp-lab' "$DCP_AO_FAKE_LOG"
grep -Fq 'project set-config dcp-lab --config-json' "$DCP_AO_FAKE_LOG"
grep -Fq 'spawn --project dcp-lab --kind worker --name DCP I8 Task --harness codex --prompt Create the safe marker only' "$DCP_AO_FAKE_LOG"
[[ -z "$(git -C "$DCP_AO_LAB_ROOT/targets/dcp-lab" remote)" ]]
[[ -z "$(git -C "$DCP_AO_LAB_ROOT/targets/dcp-lab" status --porcelain)" ]]

review_target="$DCP_AO_LAB_ROOT/targets/dcp-review-lab"
mkdir -p "$review_target"
git -C "$review_target" init -b main >/dev/null
git -C "$review_target" config user.name 'DCP Review Lab'
git -C "$review_target" config user.email 'dcp-review-lab@example.invalid'
printf 'DCP review lab\n' >"$review_target/README.md"
git -C "$review_target" add README.md
git -C "$review_target" commit -m 'Initialize exact review lab' >/dev/null
git -C "$review_target" remote add origin https://github.com/orenvlad-ai/dcp-review-lab.git
git -C "$review_target" update-ref refs/remotes/origin/main HEAD

git -C "$review_target" remote set-url --push origin https://github.com/orenvlad-ai/foreign.git
if dcp_ao_validate_review_target "$(cd "$DCP_AO_LAB_ROOT" && pwd -P)" 0 >/dev/null; then
	printf 'foreign review-lab push remote was accepted\n' >&2
	exit 1
fi
git -C "$review_target" remote set-url --push origin https://github.com/orenvlad-ai/dcp-review-lab.git

if DCP_AO_FAKE_PROVIDER_PRIVATE=1 dcp_ao_validate_review_target "$(cd "$DCP_AO_LAB_ROOT" && pwd -P)" 0 >/dev/null; then
	printf 'private review-lab provider identity was accepted\n' >&2
	exit 1
fi

failed_worktree="$DCP_AO_LAB_ROOT/data/worktrees/dcp-review-lab/dcp-review-lab-6"
mkdir -p "$(dirname "$failed_worktree")"
git -C "$review_target" worktree add -b ao/dcp-review-lab-6/root "$failed_worktree" main >/dev/null
printf 'preserved network-denied attempt\n' >"$failed_worktree/FAILED.md"
git -C "$failed_worktree" add FAILED.md
git -C "$failed_worktree" commit -m 'Preserve failed card 6' >/dev/null

allowed_worktree="$DCP_AO_LAB_ROOT/data/worktrees/dcp-review-lab/dcp-review-lab-7"
mkdir -p "$(dirname "$allowed_worktree")"
git -C "$review_target" worktree add -b ao/dcp-review-lab-7/root "$allowed_worktree" main >/dev/null
dcp_ao_validate_review_target "$(cd "$DCP_AO_LAB_ROOT" && pwd -P)" 0 >/dev/null

resolved_lab_root="$(cd "$DCP_AO_LAB_ROOT" && pwd -P)"
future_worktree="$resolved_lab_root/data/worktrees/dcp-review-lab/dcp-review-lab-13"
git -C "$review_target" worktree add -b ao/dcp-review-lab-13/root "$future_worktree" main >/dev/null
sqlite3 "$resolved_lab_root/data/ao.db" <<SQL
CREATE TABLE dcp_review_lab_policy_task (
  session_id TEXT, card_number INTEGER, worktree_path TEXT, source_branch TEXT,
  target TEXT, profile TEXT, repository TEXT, policy_version TEXT
);
INSERT INTO dcp_review_lab_policy_task VALUES (
  'dcp-review-lab-13', 13, '$future_worktree', 'ao/dcp-review-lab-13/root',
  'dcp-review-lab', 'synthetic-pr', 'orenvlad-ai/dcp-review-lab', 'dcp.review-lab.happy-path/v1'
);
SQL
dcp_ao_validate_review_target "$(cd "$DCP_AO_LAB_ROOT" && pwd -P)" 0 >/dev/null
sqlite3 "$resolved_lab_root/data/ao.db" "UPDATE dcp_review_lab_policy_task SET repository='orenvlad-ai/foreign';"
if dcp_ao_validate_review_target "$(cd "$DCP_AO_LAB_ROOT" && pwd -P)" 0 >/dev/null; then
	printf 'future worktree without exact durable policy authority was accepted\n' >&2
	exit 1
fi
sqlite3 "$resolved_lab_root/data/ao.db" "UPDATE dcp_review_lab_policy_task SET repository='orenvlad-ai/dcp-review-lab';"

foreign_worktree="$DCP_AO_LAB_ROOT/foreign-worktree"
git -C "$review_target" worktree add -b ao/foreign/root "$foreign_worktree" main >/dev/null
if dcp_ao_validate_review_target "$(cd "$DCP_AO_LAB_ROOT" && pwd -P)" 0 >/dev/null; then
	printf 'foreign review-lab linked worktree was accepted\n' >&2
	exit 1
fi
git -C "$review_target" worktree remove --force "$foreign_worktree"
git -C "$review_target" branch -D ao/foreign/root >/dev/null

review_output="$(dcp_ao_submit --target dcp-review-lab --profile synthetic-pr --task-id future-a --prompt 'Add the first future policy marker')"
printf '%s' "$review_output" | grep -Fq 'profile=synthetic-pr'
printf '%s' "$review_output" | grep -Fq 'task_id=future-a'
printf '%s' "$review_output" | grep -Fq 'session_id=dcp-review-lab-13'
printf '%s' "$review_output" | grep -Fq 'duplicate=false'
grep -Fq 'project add --id dcp-review-lab --name DCP Review Lab' "$DCP_AO_FAKE_LOG"
grep -Fq 'project set-config dcp-review-lab --config-json' "$DCP_AO_FAKE_LOG"
grep -Fq '"reviewers":[{"harness":"codex"}]' "$DCP_AO_FAKE_LOG"
grep -Fq '"permissions":"accept-edits"' "$DCP_AO_FAKE_LOG"
grep -Fq 'additional pull requests' "$DCP_AO_FAKE_LOG"
grep -Fq 'open one ready pull request targeting main' "$DCP_AO_FAKE_LOG"
grep -Fq 'one bounded findings-repair envelope' "$DCP_AO_FAKE_LOG"
grep -Fq 'exact-head review, FIFO admission and terminal merge' "$DCP_AO_FAKE_LOG"
grep -Fq 'dcp submit --target dcp-review-lab --profile synthetic-pr --repository orenvlad-ai/dcp-review-lab --task-id future-a --prompt Add the first future policy marker --json' "$DCP_AO_FAKE_LOG"
[[ "$(grep -c '^review-refresh-in-lock$' "$DCP_AO_FAKE_LOG")" -eq 1 ]]
! grep -Fq 'spawn --project dcp-review-lab' "$DCP_AO_FAKE_LOG"
[[ "$(git -C "$review_target" rev-parse HEAD)" == "$(git -C "$review_target" rev-parse refs/remotes/origin/main)" ]]
[[ -z "$(git -C "$review_target" status --porcelain)" ]]

review_output="$(DCP_AO_FAKE_POLICY_DUPLICATE=true dcp_ao_submit --target dcp-review-lab --profile synthetic-pr --task-id future-a --prompt 'Add the first future policy marker')"
printf '%s' "$review_output" | grep -Fq 'session_id=dcp-review-lab-13'
printf '%s' "$review_output" | grep -Fq 'duplicate=true'

review_output="$(DCP_AO_FAKE_POLICY_CARD=14 dcp_ao_submit --target dcp-review-lab --profile synthetic-pr --task-id future-b --prompt 'Add the second future policy marker')"
printf '%s' "$review_output" | grep -Fq 'session_id=dcp-review-lab-14'

review_output="$(DCP_AO_FAKE_POLICY_CARD=42 dcp_ao_submit --target dcp-review-lab --profile synthetic-pr --task-id future-many --prompt 'Prove there is no card ceiling')"
printf '%s' "$review_output" | grep -Fq 'session_id=dcp-review-lab-42'

if DCP_AO_FAKE_POLICY_CONFLICT=1 dcp_ao_submit --target dcp-review-lab --profile synthetic-pr --task-id future-a --prompt 'Conflicting payload'; then
	printf 'conflicting future-task replay was accepted\n' >&2
	exit 1
fi
if DCP_AO_FAKE_POLICY_SESSION=dcp-review-lab-99 dcp_ao_submit --target dcp-review-lab --profile synthetic-pr --task-id future-drift --prompt 'Reject response drift'; then
	printf 'foreign policy native response identity was accepted\n' >&2
	exit 1
fi

repo_only_target="$DCP_AO_LAB_ROOT/targets/wb-browser-extension"
mkdir -p "$repo_only_target/docs" "$repo_only_target/.github/workflows" "$repo_only_target/scripts"
git -C "$repo_only_target" init -b main >/dev/null
git -C "$repo_only_target" config user.name 'DCP Repo Only'
git -C "$repo_only_target" config user.email 'dcp-repo-only@example.invalid'
printf 'bootstrap\n' >"$repo_only_target/README.md"
printf 'repo-only\n' >"$repo_only_target/AGENTS.md"
printf 'brief\n' >"$repo_only_target/docs/PROJECT_BRIEF.md"
printf 'architecture\n' >"$repo_only_target/docs/ARCHITECTURE.md"
printf 'name: baseline\n' >"$repo_only_target/.github/workflows/baseline.yml"
printf '#!/usr/bin/env bash\nset -euo pipefail\n' >"$repo_only_target/scripts/baseline.sh"
chmod +x "$repo_only_target/scripts/baseline.sh"
git -C "$repo_only_target" add .
git -C "$repo_only_target" commit -m 'Initialize exact repo-only target' >/dev/null
git -C "$repo_only_target" remote add origin https://github.com/orenvlad-ai/wb-browser-extension.git
git -C "$repo_only_target" update-ref refs/remotes/origin/main HEAD

git -C "$repo_only_target" remote set-url --push origin https://github.com/orenvlad-ai/foreign.git
if dcp_ao_validate_repo_only_target "$resolved_lab_root" 0 >/dev/null; then
	printf 'foreign repo-only push remote was accepted\n' >&2
	exit 1
fi
git -C "$repo_only_target" remote set-url --push origin https://github.com/orenvlad-ai/wb-browser-extension.git
git -C "$repo_only_target" remote set-url origin https://github.com/orenvlad-ai/wb-price-extension.git
if dcp_ao_validate_repo_only_target "$resolved_lab_root" 0 >/dev/null; then
	printf 'legacy repo-only fetch remote was accepted for the current target\n' >&2
	exit 1
fi
git -C "$repo_only_target" remote set-url origin https://github.com/orenvlad-ai/wb-browser-extension.git
if DCP_AO_FAKE_REPO_ONLY_PROVIDER_PRIVATE=1 dcp_ao_validate_repo_only_target "$resolved_lab_root" 0 >/dev/null; then
	printf 'private repo-only provider identity was accepted\n' >&2
	exit 1
fi
if DCP_AO_FAKE_REPO_ONLY_PROVIDER_OLD_NAME=1 dcp_ao_validate_repo_only_target "$resolved_lab_root" 0 >/dev/null; then
	printf 'redirected old provider full name was accepted\n' >&2
	exit 1
fi

repo_only_worktree="$resolved_lab_root/data/worktrees/wb-browser-extension/wb-browser-extension-1"
mkdir -p "$(dirname "$repo_only_worktree")"
git -C "$repo_only_target" worktree add -b ao/wb-browser-extension-1/root "$repo_only_worktree" main >/dev/null
sqlite3 "$resolved_lab_root/data/ao.db" <<SQL
INSERT INTO dcp_review_lab_policy_task VALUES (
  'wb-browser-extension-1', 1, '$repo_only_worktree', 'ao/wb-browser-extension-1/root',
  'wb-browser-extension', 'repo-only', 'orenvlad-ai/wb-browser-extension', 'dcp.repo-only.happy-path/v1'
);
SQL
dcp_ao_validate_repo_only_target "$resolved_lab_root" 0 >/dev/null
sqlite3 "$resolved_lab_root/data/ao.db" "UPDATE dcp_review_lab_policy_task SET profile='synthetic-pr' WHERE session_id='wb-browser-extension-1';"
if dcp_ao_validate_repo_only_target "$resolved_lab_root" 0 >/dev/null; then
	printf 'repo-only worktree without exact durable policy authority was accepted\n' >&2
	exit 1
fi
sqlite3 "$resolved_lab_root/data/ao.db" "UPDATE dcp_review_lab_policy_task SET profile='repo-only' WHERE session_id='wb-browser-extension-1';"

repo_only_output="$(dcp_ao_submit --target wb-browser-extension --profile repo-only --task-id real-one --prompt 'Refine the architecture boundary')"
printf '%s' "$repo_only_output" | grep -Fq 'profile=repo-only'
printf '%s' "$repo_only_output" | grep -Fq 'task_id=real-one'
printf '%s' "$repo_only_output" | grep -Fq 'session_id=wb-browser-extension-1'
printf '%s' "$repo_only_output" | grep -Fq "worktree=$resolved_lab_root/data/worktrees/wb-browser-extension/wb-browser-extension-1"
grep -Fq 'project add --id wb-browser-extension --name WB Browser Extension' "$DCP_AO_FAKE_LOG"
grep -Fq 'project set-config wb-browser-extension --config-json' "$DCP_AO_FAKE_LOG"
grep -Fq 'Do not access or mutate wb-core, dev-control-plane, dcp-orchestrator, production, secrets' "$DCP_AO_FAKE_LOG"
grep -Fq 'run the repository baseline' "$DCP_AO_FAKE_LOG"
grep -Fq 'dcp submit --target wb-browser-extension --profile repo-only --repository orenvlad-ai/wb-browser-extension --task-id real-one --prompt Refine the architecture boundary --json' "$DCP_AO_FAKE_LOG"
[[ "$(grep -c '^repo-only-refresh-in-lock$' "$DCP_AO_FAKE_LOG")" -eq 1 ]]
! grep -Fq 'spawn --project wb-browser-extension' "$DCP_AO_FAKE_LOG"
[[ "$(git -C "$repo_only_target" rev-parse HEAD)" == "$(git -C "$repo_only_target" rev-parse refs/remotes/origin/main)" ]]
[[ -z "$(git -C "$repo_only_target" status --porcelain)" ]]

if DCP_AO_FAKE_POLICY_SESSION=wb-browser-extension-99 dcp_ao_submit --target wb-browser-extension --profile repo-only --task-id real-drift --prompt 'Reject response drift'; then
	printf 'foreign repo-only native response identity was accepted\n' >&2
	exit 1
fi
[[ "$(grep -c '^spawn ' "$DCP_AO_FAKE_LOG")" -eq 1 ]]
printf 'PASS exact remote-free, synthetic-PR, and repo-only adapter profiles\n'
