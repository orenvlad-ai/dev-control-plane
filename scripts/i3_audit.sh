#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
cd "$REPO_ROOT"
# shellcheck source=../upstream/agent-orchestrator.lock
source upstream/agent-orchestrator.lock

required=(
	AGENTS.md README.md NOTICE
	docs/PROJECT_BRIEF.md docs/ROADMAP.md docs/DECISIONS.md docs/UPSTREAM_QUALIFICATION.md
	upstream/agent-orchestrator.lock
	patches/agent-orchestrator/0001-isolate-electron-user-data.patch
	bin/dcp-ao bin/dcp-ao-submit lib/dcp-ao-common.sh lib/dcp-ao-adapter.sh
)
for path in "${required[@]}"; do [[ -s "$path" ]]; done

retired=(bin/dcp-orchestrator dcp_orchestrator pyproject.toml scripts/build_artifact.py scripts/safety_audit.py tests/test_build.py tests/test_canary.py tests/test_server.py)
for path in "${retired[@]}"; do [[ ! -e "$path" ]]; done

[[ "$(shasum -a 256 third_party/agent-orchestrator/LICENSE | awk '{print $1}')" == "$DCP_AO_UPSTREAM_LICENSE_SHA256" ]]
[[ "$(shasum -a 256 "$DCP_AO_PATCH_FILE" | awk '{print $1}')" == "$DCP_AO_PATCH_SHA256" ]]
[[ "$DCP_AO_UPSTREAM_NOTICE" == absent ]]
[[ "$(grep -c '^diff --git ' "$DCP_AO_PATCH_FILE")" -eq 3 ]]
grep -Fq 'frontend/src/main.ts' "$DCP_AO_PATCH_FILE"
grep -Fq 'frontend/src/main/app-state.ts' "$DCP_AO_PATCH_FILE"
grep -Fq 'frontend/src/main/app-state.test.ts' "$DCP_AO_PATCH_FILE"
grep -Fq "$DCP_AO_UPSTREAM_COMMIT" docs/UPSTREAM_QUALIFICATION.md
grep -Fq "$DCP_AO_UPSTREAM_TREE" docs/UPSTREAM_QUALIFICATION.md
grep -Fq 'AO_TELEMETRY_RENDERER' lib/dcp-ao-common.sh
grep -Fq 'AO_TELEMETRY_REMOTE' lib/dcp-ao-common.sh
grep -Fq 'npm run dev' bin/dcp-ao
! grep -Rq '/Applications/Agent Orchestrator.app' bin lib
[[ "$(find third_party/agent-orchestrator -type f | wc -l | tr -d '[:space:]')" -eq 2 ]]

bash -n bin/dcp-ao bin/dcp-ao-submit lib/dcp-ao-common.sh lib/dcp-ao-adapter.sh tests/test_i3.sh tests/fixtures/fake-ao
tests/test_i3.sh
git diff --check
printf 'PASS I3 deterministic audit\n'
