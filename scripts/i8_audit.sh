#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
cd "$REPO_ROOT"
# shellcheck source=../upstream/agent-orchestrator.lock
source upstream/agent-orchestrator.lock

required=(
	AGENTS.md README.md NOTICE
	docs/PROJECT_BRIEF.md docs/ROADMAP.md docs/DECISIONS.md docs/CURRENT_OPERATING_CONTRACT.md docs/UPSTREAM_QUALIFICATION.md
	upstream/agent-orchestrator.lock "$DCP_AO_PATCH_FILE"
	bin/dcp-ao bin/dcp-ao-submit lib/dcp-ao-common.sh lib/dcp-ao-gateway.sh lib/dcp-ao-adapter.sh
	tests/test_i3.sh tests/test_i8_gateway.sh
)
for path in "${required[@]}"; do [[ -s "$path" ]]; done

retired=(bin/dcp-orchestrator dcp_orchestrator pyproject.toml scripts/build_artifact.py scripts/safety_audit.py tests/test_build.py tests/test_canary.py tests/test_server.py tests/test_i7_gateway.sh)
for path in "${retired[@]}"; do [[ ! -e "$path" ]]; done

[[ "$(shasum -a 256 third_party/agent-orchestrator/LICENSE | awk '{print $1}')" == "$DCP_AO_UPSTREAM_LICENSE_SHA256" ]]
[[ "$(shasum -a 256 "$DCP_AO_PATCH_FILE" | awk '{print $1}')" == "$DCP_AO_PATCH_SHA256" ]]
[[ "$DCP_AO_UPSTREAM_NOTICE" == absent ]]
[[ "$(grep -c '^diff --git ' "$DCP_AO_PATCH_FILE")" -ge 40 ]]

for path in \
	frontend/forge.config.ts frontend/package.json frontend/package-lock.json \
	frontend/src/main.ts frontend/src/preload.ts frontend/src/shared/daemon-launch.ts frontend/src/shared/daemon-discovery.ts \
	frontend/src/renderer/main.tsx frontend/src/renderer/lib/telemetry.ts frontend/src/renderer/components/Sidebar.tsx \
	backend/internal/runfile/runfile.go backend/internal/config/config.go backend/internal/daemon/telemetry_wiring.go \
	backend/internal/daemonmeta/meta.go backend/internal/adapters/agent/codex/codex.go \
	backend/internal/session_manager/manager.go backend/internal/lifecycle/manager.go; do
	grep -Fq "$path" "$DCP_AO_PATCH_FILE"
done

grep -Fq 'pro.devcontrol.dcp-orchestrator' "$DCP_AO_PATCH_FILE"
grep -Fq 'DCP Orchestrator' "$DCP_AO_PATCH_FILE"
grep -Fq 'dcp-orchestratord' "$DCP_AO_PATCH_FILE"
grep -Fq 'dcp-orchestrator-daemon' "$DCP_AO_PATCH_FILE"
grep -Fq 'requestSingleInstanceLock' "$DCP_AO_PATCH_FILE"
grep -Fq 'DCPAppInstanceID' "$DCP_AO_PATCH_FILE"
grep -Fq 'Quit Anyway' "$DCP_AO_PATCH_FILE"
grep -Fq 'makers: []' "$DCP_AO_PATCH_FILE"
grep -Fq 'publishers: []' "$DCP_AO_PATCH_FILE"
grep -Fq 'disabledEventSink' "$DCP_AO_PATCH_FILE"
grep -Fq 'return false;' "$DCP_AO_PATCH_FILE"
grep -Fq 'VITE_DCP_HIDE_MANUAL_ORCHESTRATOR_SPAWN' "$DCP_AO_PATCH_FILE"
grep -Fq 'showOrchestratorControl(false)' "$DCP_AO_PATCH_FILE"
grep -Fq 'spawnOrchestrator).toBeTypeOf("function")' "$DCP_AO_PATCH_FILE"
grep -Fq -- '--ignore-user-config' "$DCP_AO_PATCH_FILE"
grep -Fq -- '--ephemeral' "$DCP_AO_PATCH_FILE"
grep -Fq -- '--strict-config' "$DCP_AO_PATCH_FILE"
! grep -Eq '^\+.*--dangerously-bypass-hook-trust' "$DCP_AO_PATCH_FILE"
! grep -Eq '^\+.*process\.kill\([^,]+,[[:space:]]*"SIG' "$DCP_AO_PATCH_FILE"

grep -Fq 'DCP Orchestrator.app' lib/dcp-ao-common.sh
grep -Fq 'pro.devcontrol.dcp-orchestrator' lib/dcp-ao-common.sh
grep -Fq '/usr/bin/open "$app"' lib/dcp-ao-gateway.sh
grep -Fq 'dcpAppInstanceId' lib/dcp-ao-gateway.sh
grep -Fq 'state/gateway/submit.lock' lib/dcp-ao-gateway.sh
grep -Fq 'npm run package -- --arch=arm64' bin/dcp-ao
grep -Fq 'codesign --force --deep --sign -' bin/dcp-ao
! grep -Fq 'npm run dev' bin/dcp-ao
! grep -Fq '__gateway-launch' bin/dcp-ao
! grep -REq 'open[[:space:]]+-a|osascript' bin lib
! grep -Fq '/Applications/Agent Orchestrator.app' bin/dcp-ao lib/dcp-ao-common.sh lib/dcp-ao-gateway.sh
! grep -Eq '^  (launch|daemon|stop|restart)[[:space:]]' < <(bin/dcp-ao --help)
! grep -Rq -- '--dangerously-bypass-hook-trust' bin lib
[[ "$(find third_party/agent-orchestrator -type f | wc -l | tr -d '[:space:]')" -eq 2 ]]

grep -Fq 'docs/CURRENT_OPERATING_CONTRACT.md' AGENTS.md
grep -Fq 'current implemented laboratory stage is I8' docs/CURRENT_OPERATING_CONTRACT.md
grep -Fq '/Users/ovlmacbook/Applications/DCP Orchestrator.app' docs/CURRENT_OPERATING_CONTRACT.md
grep -Fq 'bin/dcp-ao-submit' docs/CURRENT_OPERATING_CONTRACT.md
grep -Fq 'source/dev' docs/CURRENT_OPERATING_CONTRACT.md
grep -Fq 'CODEX_SQLITE_HOME' docs/CURRENT_OPERATING_CONTRACT.md
grep -Fq "$DCP_AO_UPSTREAM_COMMIT" docs/CURRENT_OPERATING_CONTRACT.md
grep -Fq 'DCP_AO_LAB_ROOT' docs/CURRENT_OPERATING_CONTRACT.md
grep -Fq 'reviewer' docs/ROADMAP.md
grep -Fq 'not packaged' docs/DECISIONS.md

if [[ -n "${DCP_AO_CONTRACT_BASE:-}" ]] && git cat-file -e "$DCP_AO_CONTRACT_BASE^{commit}" 2>/dev/null; then
	changed_paths="$(git diff --name-only "$DCP_AO_CONTRACT_BASE"...HEAD)"
	if printf '%s\n' "$changed_paths" | grep -Eq '^(AGENTS\.md|bin/|lib/|upstream/|patches/agent-orchestrator/)'; then
		printf '%s\n' "$changed_paths" | grep -Fxq 'docs/CURRENT_OPERATING_CONTRACT.md'
	fi
fi

bash -n bin/dcp-ao bin/dcp-ao-submit lib/dcp-ao-common.sh lib/dcp-ao-gateway.sh lib/dcp-ao-adapter.sh tests/test_i3.sh tests/test_i8_gateway.sh tests/fixtures/fake-ao
tests/test_i3.sh
tests/test_i8_gateway.sh
git diff --check
printf 'PASS I8 deterministic audit\n'
