#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
cd "$REPO_ROOT"
# shellcheck source=../upstream/agent-orchestrator.lock
source upstream/agent-orchestrator.lock

required=(
	AGENTS.md README.md NOTICE
	docs/PROJECT_BRIEF.md docs/ROADMAP.md docs/DECISIONS.md docs/CURRENT_OPERATING_CONTRACT.md docs/UPSTREAM_QUALIFICATION.md
	upstream/agent-orchestrator.lock
	patches/agent-orchestrator/0001-isolate-electron-user-data.patch
	bin/dcp-ao bin/dcp-ao-submit lib/dcp-ao-common.sh lib/dcp-ao-gateway.sh lib/dcp-ao-adapter.sh
	tests/test_i3.sh tests/test_i7_gateway.sh
)
for path in "${required[@]}"; do [[ -s "$path" ]]; done

retired=(bin/dcp-orchestrator dcp_orchestrator pyproject.toml scripts/build_artifact.py scripts/safety_audit.py tests/test_build.py tests/test_canary.py tests/test_server.py)
for path in "${retired[@]}"; do [[ ! -e "$path" ]]; done

[[ "$(shasum -a 256 third_party/agent-orchestrator/LICENSE | awk '{print $1}')" == "$DCP_AO_UPSTREAM_LICENSE_SHA256" ]]
[[ "$(shasum -a 256 "$DCP_AO_PATCH_FILE" | awk '{print $1}')" == "$DCP_AO_PATCH_SHA256" ]]
[[ "$DCP_AO_UPSTREAM_NOTICE" == absent ]]
[[ "$(grep -c '^diff --git ' "$DCP_AO_PATCH_FILE")" -eq 31 ]]
grep -Fq 'frontend/src/main.ts' "$DCP_AO_PATCH_FILE"
grep -Fq 'frontend/src/main/app-state.ts' "$DCP_AO_PATCH_FILE"
grep -Fq 'frontend/src/main/app-state.test.ts' "$DCP_AO_PATCH_FILE"
grep -Fq 'backend/internal/adapters/agent/codex/codex.go' "$DCP_AO_PATCH_FILE"
grep -Fq 'backend/internal/adapters/agent/codex/codex_test.go' "$DCP_AO_PATCH_FILE"
grep -Fq 'backend/internal/adapters/agent/codex/hooks.go' "$DCP_AO_PATCH_FILE"
grep -Fq 'backend/internal/adapters/runtime/tmux/tmux.go' "$DCP_AO_PATCH_FILE"
grep -Fq 'backend/internal/adapters/runtime/tmux/tmux_test.go' "$DCP_AO_PATCH_FILE"
grep -Fq 'backend/internal/cli/doctor_test.go' "$DCP_AO_PATCH_FILE"
grep -Fq 'backend/internal/cli/agent_process.go' "$DCP_AO_PATCH_FILE"
grep -Fq 'backend/internal/cli/agent_process_unix_test.go' "$DCP_AO_PATCH_FILE"
grep -Fq 'backend/internal/lifecycle/manager.go' "$DCP_AO_PATCH_FILE"
grep -Fq 'backend/internal/lifecycle/manager_test.go' "$DCP_AO_PATCH_FILE"
grep -Fq 'backend/internal/ports/agent.go' "$DCP_AO_PATCH_FILE"
grep -Fq 'backend/internal/service/session/status_test.go' "$DCP_AO_PATCH_FILE"
grep -Fq 'backend/internal/session_manager/manager.go' "$DCP_AO_PATCH_FILE"
grep -Fq 'backend/internal/session_manager/manager_test.go' "$DCP_AO_PATCH_FILE"
grep -Fq 'frontend/src/renderer/lib/session-presentation.test.ts' "$DCP_AO_PATCH_FILE"
grep -Fq 'frontend/src/main/daemon-owner.ts' "$DCP_AO_PATCH_FILE"
grep -Fq 'frontend/src/main/daemon-owner.test.ts' "$DCP_AO_PATCH_FILE"
grep -Fq 'frontend/src/renderer/components/BoardEmptyStates.tsx' "$DCP_AO_PATCH_FILE"
grep -Fq 'frontend/src/renderer/components/RestoreUnavailableDialog.test.tsx' "$DCP_AO_PATCH_FILE"
grep -Fq 'frontend/src/renderer/components/SessionsBoard.tsx' "$DCP_AO_PATCH_FILE"
grep -Fq 'frontend/src/renderer/components/ShellTopbar.tsx' "$DCP_AO_PATCH_FILE"
grep -Fq 'frontend/src/renderer/components/Sidebar.tsx' "$DCP_AO_PATCH_FILE"
grep -Fq 'frontend/src/renderer/lib/orchestrator-spawn-sources.ts' "$DCP_AO_PATCH_FILE"
grep -Fq 'frontend/src/renderer/lib/spawn-orchestrator.test.ts' "$DCP_AO_PATCH_FILE"
grep -Eq '^\+.*--ignore-user-config' "$DCP_AO_PATCH_FILE"
grep -Eq '^\+.*--ephemeral' "$DCP_AO_PATCH_FILE"
grep -Eq '^\+.*--strict-config' "$DCP_AO_PATCH_FILE"
grep -Eq '^\+.*appendWorkerIsolationFlags' "$DCP_AO_PATCH_FILE"
! grep -Eq '^\+.*--dangerously-bypass-hook-trust' "$DCP_AO_PATCH_FILE"
grep -Fq 'AgentExitDetectionSupervisorIdleOnSuccess' "$DCP_AO_PATCH_FILE"
grep -Fq 'idle-on-success' "$DCP_AO_PATCH_FILE"
grep -Fq 'TestSupervisorCommandAcceptsOneShotOutcomeFlag' "$DCP_AO_PATCH_FILE"
grep -Fq 'waitErr == nil' "$DCP_AO_PATCH_FILE"
grep -Fq 'next.Metadata.RuntimeLaunchID = ""' "$DCP_AO_PATCH_FILE"
grep -Fq 'successful one-shot exit as ordinary Idle and a failure as red Exited' "$DCP_AO_PATCH_FILE"
grep -Fq 'DCP_AO_FAIL_CLOSED_DAEMON_REPLACEMENT' "$DCP_AO_PATCH_FILE"
grep -Fq 'no process was killed or replaced' "$DCP_AO_PATCH_FILE"
grep -Fq 'VITE_DCP_HIDE_MANUAL_ORCHESTRATOR_SPAWN' "$DCP_AO_PATCH_FILE"
grep -Fq 'showOrchestratorControl(false)' "$DCP_AO_PATCH_FILE"
grep -Fq 'spawnOrchestrator).toBeTypeOf("function")' "$DCP_AO_PATCH_FILE"
! grep -Eq '^\+.*process\.kill\([^,]+,[[:space:]]*"SIG' "$DCP_AO_PATCH_FILE"
grep -Fq "$DCP_AO_UPSTREAM_COMMIT" docs/UPSTREAM_QUALIFICATION.md
grep -Fq "$DCP_AO_UPSTREAM_TREE" docs/UPSTREAM_QUALIFICATION.md
grep -Fq 'AO_TELEMETRY_RENDERER' lib/dcp-ao-common.sh
grep -Fq 'AO_TELEMETRY_REMOTE' lib/dcp-ao-common.sh
grep -Fq 'CODEX_SQLITE_HOME' lib/dcp-ao-common.sh
grep -Fq 'DCP_AO_UI_INSTANCE_ID' lib/dcp-ao-common.sh
grep -Fq 'DCP_AO_FAIL_CLOSED_DAEMON_REPLACEMENT' lib/dcp-ao-common.sh
grep -Fq "'/Applications/Agent Orchestrator.app'" lib/dcp-ao-common.sh
grep -Fq 'npm run dev' bin/dcp-ao
grep -Fq '__gateway-launch' bin/dcp-ao
grep -Fq 'wait "$ui_process"' bin/dcp-ao
! grep -Eq '^  (launch|daemon|stop|restart)[[:space:]]' < <(bin/dcp-ao --help)
! grep -Rq -- '--dangerously-bypass-hook-trust' bin lib
! grep -REq 'open[[:space:]]+-a|osascript|/usr/bin/open' bin lib
[[ "$(find third_party/agent-orchestrator -type f | wc -l | tr -d '[:space:]')" -eq 2 ]]

grep -Fq 'docs/CURRENT_OPERATING_CONTRACT.md' AGENTS.md
grep -Fq 'DCP_curators/AGENTS.md' docs/CURRENT_OPERATING_CONTRACT.md
grep -Fq 'automatically receives `AGENTS.md`' docs/CURRENT_OPERATING_CONTRACT.md
grep -Eq '^operating_contract_revision: [0-9]{4}-[0-9]{2}-[0-9]{2}\.[0-9]+$' docs/CURRENT_OPERATING_CONTRACT.md
grep -Fq '/Applications/Agent Orchestrator.app' docs/CURRENT_OPERATING_CONTRACT.md
grep -Fq 'no nested curator' docs/CURRENT_OPERATING_CONTRACT.md
grep -Fq 'bin/dcp-ao preflight' docs/CURRENT_OPERATING_CONTRACT.md
grep -Fq 'CODEX_SQLITE_HOME' docs/CURRENT_OPERATING_CONTRACT.md
grep -Fq 'exec --ignore-user-config' docs/CURRENT_OPERATING_CONTRACT.md
grep -Fq 'current implemented laboratory stage is I7' docs/CURRENT_OPERATING_CONTRACT.md
grep -Fq 'single synchronous DCP Gateway' docs/CURRENT_OPERATING_CONTRACT.md
grep -Fq 'one normal mechanical entry only' docs/CURRENT_OPERATING_CONTRACT.md
grep -Fq 'without kill, stop, restart, or' docs/CURRENT_OPERATING_CONTRACT.md
grep -Fq 'synchronously update this contract' docs/CURRENT_OPERATING_CONTRACT.md
grep -Fq "$DCP_AO_UPSTREAM_COMMIT" docs/CURRENT_OPERATING_CONTRACT.md
grep -Fq 'DCP_AO_LAB_ROOT' docs/CURRENT_OPERATING_CONTRACT.md

if [[ -n "${DCP_AO_CONTRACT_BASE:-}" ]] && git cat-file -e "$DCP_AO_CONTRACT_BASE^{commit}" 2>/dev/null; then
	changed_paths="$(git diff --name-only "$DCP_AO_CONTRACT_BASE"...HEAD)"
	if printf '%s\n' "$changed_paths" | grep -Eq '^(AGENTS\.md|bin/|lib/|upstream/|patches/agent-orchestrator/)'; then
		printf '%s\n' "$changed_paths" | grep -Fxq 'docs/CURRENT_OPERATING_CONTRACT.md'
	fi
fi

bash -n bin/dcp-ao bin/dcp-ao-submit lib/dcp-ao-common.sh lib/dcp-ao-gateway.sh lib/dcp-ao-adapter.sh tests/test_i3.sh tests/test_i7_gateway.sh tests/fixtures/fake-ao
tests/test_i3.sh
tests/test_i7_gateway.sh
git diff --check
printf 'PASS I3 deterministic audit\n'
