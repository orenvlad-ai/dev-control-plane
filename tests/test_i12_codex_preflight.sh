#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
# shellcheck source=../lib/dcp-ao-common.sh
source "$REPO_ROOT/lib/dcp-ao-common.sh"

TEST_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/dcp-ao-i12-codex-preflight.XXXXXX")"
export TEST_ROOT
cleanup() { rm -rf "$TEST_ROOT"; }
trap cleanup EXIT

export PATH="$REPO_ROOT/tests/fixtures/codex-preflight:/usr/bin:/bin"
export DCP_AO_FAKE_CODEX_LOG="$TEST_ROOT/codex.log"
unset CODEX_HOME

dcp_ao_preflight_codex_worker "$TEST_ROOT"
grep -Fq 'approval_policy=\"on-request\"' "$DCP_AO_FAKE_CODEX_LOG"
grep -Fq -- '--sandbox workspace-write' "$DCP_AO_FAKE_CODEX_LOG"
grep -Fq -- "--add-dir $TEST_ROOT/evidence/codex-preflight/gitdir" "$DCP_AO_FAKE_CODEX_LOG"
grep -Fq -- "--add-dir $TEST_ROOT/evidence/codex-preflight/common" "$DCP_AO_FAKE_CODEX_LOG"
! grep -Fq -- '--ask-for-approval' "$DCP_AO_FAKE_CODEX_LOG"
grep -Fq 'features list' "$DCP_AO_FAKE_CODEX_LOG"

export DCP_AO_FAKE_CODEX_REJECT_CONFIG=1
if dcp_ao_preflight_codex_worker "$TEST_ROOT"; then
	printf 'Codex capability rejection was accepted\n' >&2
	exit 1
fi

printf 'PASS I12 Codex worker model-free parser/config preflight\n'
