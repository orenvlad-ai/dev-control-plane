#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
export DCP_AO_LAB_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/dcp-ao-i3-test.XXXXXX")"
cleanup() { rm -rf "$DCP_AO_LAB_ROOT"; }
trap cleanup EXIT

export DCP_AO_FAKE_LOG="$DCP_AO_LAB_ROOT/fake-ao.log"
"$REPO_ROOT/bin/dcp-ao" init-target >/dev/null

# shellcheck source=../lib/dcp-ao-common.sh
source "$REPO_ROOT/lib/dcp-ao-common.sh"
# shellcheck source=../lib/dcp-ao-adapter.sh
source "$REPO_ROOT/lib/dcp-ao-adapter.sh"
dcp_ao_resolve_cli() { printf '%s\n' "$REPO_ROOT/tests/fixtures/fake-ao"; }

if (DCP_AO_LAB_ROOT="${HOME:?}/.ao"; dcp_ao_require_lab_root >/dev/null); then
	printf 'installed AO state root was accepted\n' >&2
	exit 1
fi
if (dcp_ao_submit --target real-repo --prompt 'safe'); then
	printf 'forbidden target was accepted\n' >&2
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
grep -Fq 'spawn --project dcp-lab --kind worker --name DCP I3 Canary --harness codex --prompt Create the safe marker only' "$DCP_AO_FAKE_LOG"
[[ -z "$(git -C "$DCP_AO_LAB_ROOT/targets/dcp-lab" remote)" ]]
[[ -z "$(git -C "$DCP_AO_LAB_ROOT/targets/dcp-lab" status --porcelain)" ]]
printf 'PASS adapter validation and one-spawn integration\n'
