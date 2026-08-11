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
dcp_ao_refresh_review_target() { :; }
dcp_ao_gateway_with_lock() {
	local lab_root="$1" cli="$2" callback="$3"
	shift 3
	"$callback" "$lab_root" "$cli" "$@"
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

foreign_worktree="$DCP_AO_LAB_ROOT/foreign-worktree"
git -C "$review_target" worktree add -b ao/foreign/root "$foreign_worktree" main >/dev/null
if dcp_ao_validate_review_target "$(cd "$DCP_AO_LAB_ROOT" && pwd -P)" 0 >/dev/null; then
	printf 'foreign review-lab linked worktree was accepted\n' >&2
	exit 1
fi
git -C "$review_target" worktree remove --force "$foreign_worktree"
git -C "$review_target" branch -D ao/foreign/root >/dev/null

review_output="$(dcp_ao_submit --target dcp-review-lab --profile synthetic-pr --task-id i13-arbiter-a --prompt 'Add first bounded arbiter conflict intent')"
printf '%s' "$review_output" | grep -Fq 'profile=synthetic-pr'
printf '%s' "$review_output" | grep -Fq 'task_id=i13-arbiter-a'
printf '%s' "$review_output" | grep -Fq 'session_id=dcp-review-lab-11'
grep -Fq 'project add --id dcp-review-lab --name DCP Review Lab' "$DCP_AO_FAKE_LOG"
grep -Fq 'project set-config dcp-review-lab --config-json' "$DCP_AO_FAKE_LOG"
grep -Fq '"reviewers":[{"harness":"codex"}]' "$DCP_AO_FAKE_LOG"
grep -Fq '"permissions":"accept-edits"' "$DCP_AO_FAKE_LOG"
grep -Fq 'additional pull requests' "$DCP_AO_FAKE_LOG"
grep -Fq 'open one ready pull request targeting main' "$DCP_AO_FAKE_LOG"
grep -Fq 'single bounded admission-refresh continuation' "$DCP_AO_FAKE_LOG"
grep -Fq 'Only for native cards 11/12' "$DCP_AO_FAKE_LOG"
grep -Fq 'exact I13 arbiter recovery identity' "$DCP_AO_FAKE_LOG"
grep -Fq 'session ls --project dcp-review-lab --all --include-terminated --json' "$DCP_AO_FAKE_LOG"
grep -Fq 'spawn --project dcp-review-lab --kind worker --name DCP:i13-arbiter-a --harness codex --prompt DCP synthetic task i13-arbiter-a: Add first bounded arbiter conflict intent' "$DCP_AO_FAKE_LOG"
[[ "$(git -C "$review_target" rev-parse HEAD)" == "$(git -C "$review_target" rev-parse refs/remotes/origin/main)" ]]
[[ -z "$(git -C "$review_target" status --porcelain)" ]]

review_output="$(DCP_AO_FAKE_SESSION_STATE=one dcp_ao_submit --target dcp-review-lab --profile synthetic-pr --task-id i13-arbiter-b --prompt 'Add second bounded arbiter conflict intent')"
printf '%s' "$review_output" | grep -Fq 'task_id=i13-arbiter-b'
printf '%s' "$review_output" | grep -Fq 'session_id=dcp-review-lab-12'

before_spawns="$(grep -c '^spawn ' "$DCP_AO_FAKE_LOG")"
if (DCP_AO_FAKE_SESSION_STATE=one DCP_AO_FAKE_TASK_ID=i13-arbiter-a dcp_ao_submit --target dcp-review-lab --profile synthetic-pr --task-id i13-arbiter-a --prompt 'Do not duplicate'); then
	printf 'duplicate synthetic task id was accepted\n' >&2
	exit 1
fi
[[ "$(grep -c '^spawn ' "$DCP_AO_FAKE_LOG")" -eq "$before_spawns" ]]
if dcp_ao_submit --target dcp-review-lab --profile synthetic-pr --task-id wrong-stage2 --prompt 'Do not allocate the wrong identity'; then
	printf 'wrong Stage 2 task id was accepted\n' >&2
	exit 1
fi
if DCP_AO_FAKE_SESSION_STATE=prestage dcp_ao_submit --target dcp-review-lab --profile synthetic-pr --task-id i13-arbiter-a --prompt 'Do not start without Stage 1'; then
	printf 'missing qualified Stage 1 identities were accepted\n' >&2
	exit 1
fi
if DCP_AO_FAKE_STAGE1_CARD9_TASK_ID=foreign-stage1 dcp_ao_submit --target dcp-review-lab --profile synthetic-pr --task-id i13-arbiter-a --prompt 'Do not start after identity drift'; then
	printf 'drifted qualified Stage 1 identity was accepted\n' >&2
	exit 1
fi
for invalid_state in full gap future; do
	if DCP_AO_FAKE_SESSION_STATE="$invalid_state" dcp_ao_submit --target dcp-review-lab --profile synthetic-pr --task-id "invalid-$invalid_state" --prompt 'Do not exceed the cohort'; then
		printf 'invalid synthetic cohort state was accepted: %s\n' "$invalid_state" >&2
		exit 1
	fi
done
[[ "$(grep -c '^spawn ' "$DCP_AO_FAKE_LOG")" -eq "$before_spawns" ]]
printf 'PASS exact remote-free and synthetic-PR adapter profiles\n'
