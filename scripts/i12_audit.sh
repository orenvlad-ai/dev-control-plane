#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
cd "$REPO_ROOT"
# shellcheck source=../upstream/dcp-orchestrator.lock
source upstream/dcp-orchestrator.lock

required=(
	AGENTS.md README.md NOTICE
	docs/PROJECT_BRIEF.md docs/ROADMAP.md docs/DECISIONS.md docs/CURRENT_OPERATING_CONTRACT.md docs/UPSTREAM_QUALIFICATION.md
	upstream/dcp-orchestrator.lock
	bin/dcp-ao bin/dcp-ao-submit lib/dcp-ao-common.sh lib/dcp-ao-gateway.sh lib/dcp-ao-install.sh lib/dcp-ao-adapter.sh
	tests/test_i3.sh tests/test_i8_gateway.sh tests/test_i12_install.sh
)
for path in "${required[@]}"; do [[ -s "$path" ]]; done

retired=(
	bin/dcp-orchestrator dcp_orchestrator pyproject.toml scripts/build_artifact.py scripts/safety_audit.py
	tests/test_build.py tests/test_canary.py tests/test_server.py tests/test_i7_gateway.sh
	upstream/agent-orchestrator.lock patches/agent-orchestrator third_party/agent-orchestrator
)
for path in "${retired[@]}"; do [[ ! -e "$path" ]]; done

[[ "$DCP_AO_FORK_REPOSITORY" == 'https://github.com/orenvlad-ai/dcp-orchestrator.git' ]]
[[ "$DCP_AO_FORK_PR_URL" == 'https://github.com/orenvlad-ai/dcp-orchestrator/pull/5' ]]
[[ "$DCP_AO_FORK_COMMIT" == 695491e2f6cc7b1b327bb5dd35e61d16280b4a64 ]]
[[ "$DCP_AO_FORK_TREE" == 1689184429a415b65838a89528f81bd6de13b00d ]]
[[ "$DCP_AO_PRIOR_FORK_COMMIT" == 031610b1050818d59654ee78963e41f5f1823430 ]]
[[ "$DCP_AO_PRIOR_FORK_TREE" == 713da841831a5beabed48221fa50ec888e81d1ae ]]
[[ "$DCP_AO_I8_PARITY_COMMIT" == 23fe9bba77873075f32b813fb0a3c936598882fb ]]
[[ "$DCP_AO_I8_PARITY_DIFF_SHA256" == 047c9f74902ede19b6e3a3ba753fc7b2702a322a9be709fb0e975cc5628314d2 ]]
[[ "$DCP_AO_FORK_LICENSE_SHA256" == 1a2219722b7ef58364065e9073a2cb2831891eb147a785742a31431c9cddad1d ]]
[[ "$DCP_AO_FORK_NOTICE_SHA256" == 591f69f0abf358b44891fda2fbdf6cbf9e30bd0ef71bfc146fe92edfd1fb1637 ]]
[[ "$DCP_AO_FORK_PROVENANCE_SHA256" == 1063dee130fffa68a9b4ec6d5b94ad6ae951d1abadd8de3d6b24bcc04c917fdf ]]
[[ "$DCP_AO_UPSTREAM_REPOSITORY" == 'https://github.com/Untrivial-ai/agent-orchestrator.git' ]]
[[ "$DCP_AO_UPSTREAM_COMMIT" == 1df40e93772c2c48e916870d9c3ddf8f29a69f84 ]]
[[ "$DCP_AO_UPSTREAM_TREE" == 36bf30cc4960c10f0d94fc63a8ff0a4dd22bb8a8 ]]
[[ "$DCP_AO_UPSTREAM_NOTICE" == absent ]]

grep -Fq 'source/dcp-orchestrator-' lib/dcp-ao-common.sh
grep -Fq 'remote get-url origin' lib/dcp-ao-common.sh
grep -Fq 'remote get-url --push upstream' lib/dcp-ao-common.sh
grep -Fq 'remote set-url --add --push upstream DISABLED' lib/dcp-ao-common.sh
grep -Fq 'merge-base --is-ancestor "$DCP_AO_UPSTREAM_COMMIT" "$DCP_AO_I8_PARITY_COMMIT"' lib/dcp-ao-common.sh
grep -Fq 'merge-base --is-ancestor "$DCP_AO_I8_PARITY_COMMIT" "$DCP_AO_FORK_COMMIT"' lib/dcp-ao-common.sh
grep -Fq 'diff "$DCP_AO_UPSTREAM_COMMIT" "$DCP_AO_I8_PARITY_COMMIT" --binary --full-index' lib/dcp-ao-common.sh
grep -Fq 'Contents/Resources/NOTICE' lib/dcp-ao-common.sh
grep -Fq 'Contents/Resources/DCP_PROVENANCE.md' lib/dcp-ao-common.sh
grep -Fq 'fork_commit=$DCP_AO_FORK_COMMIT' lib/dcp-ao-common.sh
grep -Fq 'i8_parity_diff_sha256=$DCP_AO_I8_PARITY_DIFF_SHA256' lib/dcp-ao-common.sh

grep -Fq 'DCP Orchestrator.app' lib/dcp-ao-common.sh
grep -Fq 'pro.devcontrol.dcp-orchestrator' lib/dcp-ao-common.sh
grep -Fq '/usr/bin/open "$app"' lib/dcp-ao-gateway.sh
grep -Fq 'dcpAppInstanceId' lib/dcp-ao-gateway.sh
grep -Fq 'state/gateway/submit.lock' lib/dcp-ao-gateway.sh
grep -Fq 'npm run package -- --arch=arm64' bin/dcp-ao
grep -Fq 'codesign --force --deep --sign -' bin/dcp-ao
grep -Fq 'build/backups/i12-' bin/dcp-ao
grep -Fq 'dcp_ao_verify_replaceable_bundle_at' bin/dcp-ao
grep -Fq 'dcp_ao_verify_replaceable_install_receipt' bin/dcp-ao
grep -Fq 'ditto "$lab_root/state" "$backup_root/state"' bin/dcp-ao
grep -Fq 'ditto "$lab_root/data" "$backup_root/data"' bin/dcp-ao
grep -Fq 'diff -qr "$lab_root/state" "$backup_root/state"' bin/dcp-ao
grep -Fq 'diff -qr "$lab_root/data" "$backup_root/data"' bin/dcp-ao
grep -Fq 'fork_commit=%s' bin/dcp-ao
grep -Fq './scripts/dcp-ci-gates.sh source' bin/dcp-ao
grep -Fq 'npm run sqlc && npm run api && git diff --exit-code' bin/dcp-ao
grep -Fq 'src/renderer/components/SessionsBoard.test.tsx' bin/dcp-ao
grep -Fq 'src/renderer/components/SessionInspector.test.tsx' bin/dcp-ao
grep -Fq 'src/renderer/i18n/renderer-coverage.test.ts' bin/dcp-ao
grep -Fq 'fork_commit=$DCP_AO_PRIOR_FORK_COMMIT' lib/dcp-ao-common.sh
grep -Fq 'fork_tree=$DCP_AO_PRIOR_FORK_TREE' lib/dcp-ao-common.sh
grep -Fq 'prior receipt names an unapproved managed fork' lib/dcp-ao-common.sh
! grep -Fq 'npm run dev' bin/dcp-ao
! grep -Fq '__gateway-launch' bin/dcp-ao
grep -Fq 'dcp_ao_install_prepare_runtime' bin/dcp-ao lib/dcp-ao-install.sh
grep -Fq "activity_state = 'active'" lib/dcp-ao-install.sh
grep -Fq "rr.status = 'running'" lib/dcp-ao-install.sh
grep -Fq 'kill -TERM "$app_pid"' lib/dcp-ao-install.sh
! grep -REq 'open[[:space:]]+-a|osascript' bin lib
! grep -Fq '/Applications/Agent Orchestrator.app' bin/dcp-ao lib/dcp-ao-common.sh lib/dcp-ao-gateway.sh
! grep -Eq '^  (launch|daemon|stop|restart)[[:space:]]' < <(bin/dcp-ao --help)
! grep -Rq -- '--dangerously-bypass-hook-trust' bin lib

grep -Fq 'docs/CURRENT_OPERATING_CONTRACT.md' AGENTS.md
grep -Fq 'current implemented laboratory stage is I12' docs/CURRENT_OPERATING_CONTRACT.md
grep -Fq '/Users/ovlmacbook/Applications/DCP Orchestrator.app' docs/CURRENT_OPERATING_CONTRACT.md
grep -Fq 'bin/dcp-ao-submit' docs/CURRENT_OPERATING_CONTRACT.md
grep -Fq 'source/dev' docs/CURRENT_OPERATING_CONTRACT.md
grep -Fq 'CODEX_SQLITE_HOME' docs/CURRENT_OPERATING_CONTRACT.md
grep -Fq "$DCP_AO_FORK_COMMIT" docs/CURRENT_OPERATING_CONTRACT.md docs/PROJECT_BRIEF.md docs/UPSTREAM_QUALIFICATION.md docs/DECISIONS.md docs/TARGET_ARCHITECTURE_V1.md
grep -Fq "$DCP_AO_UPSTREAM_COMMIT" docs/CURRENT_OPERATING_CONTRACT.md
grep -Fq 'DCP_AO_LAB_ROOT' docs/CURRENT_OPERATING_CONTRACT.md
grep -Fq 'reviewer' docs/ROADMAP.md
grep -Fq 'not packaged' docs/DECISIONS.md
grep -Fq 'I9 remains inactive target design' docs/DECISIONS.md
grep -Fq 'ZERO model calls' docs/UPSTREAM_QUALIFICATION.md

if [[ -n "${DCP_AO_CONTRACT_BASE:-}" ]] && git cat-file -e "$DCP_AO_CONTRACT_BASE^{commit}" 2>/dev/null; then
	changed_paths="$(git diff --name-only "$DCP_AO_CONTRACT_BASE"...HEAD)"
	if printf '%s\n' "$changed_paths" | grep -Eq '^(AGENTS\.md|bin/|lib/|upstream/|patches/agent-orchestrator/)'; then
		printf '%s\n' "$changed_paths" | grep -Fxq 'docs/CURRENT_OPERATING_CONTRACT.md'
	fi
fi

bash -n bin/dcp-ao bin/dcp-ao-submit lib/dcp-ao-common.sh lib/dcp-ao-gateway.sh lib/dcp-ao-install.sh lib/dcp-ao-adapter.sh tests/test_i3.sh tests/test_i8_gateway.sh tests/test_i12_install.sh tests/fixtures/fake-ao
tests/test_i3.sh
tests/test_i8_gateway.sh
tests/test_i12_install.sh
git diff --check
printf 'PASS I12 deterministic audit\n'
