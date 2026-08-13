#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
cd "$REPO_ROOT"
# shellcheck source=../upstream/dcp-orchestrator.lock
source upstream/dcp-orchestrator.lock

required=(
	AGENTS.md README.md NOTICE
	docs/PROJECT_BRIEF.md docs/ROADMAP.md docs/DECISIONS.md docs/CURRENT_OPERATING_CONTRACT.md docs/UPSTREAM_QUALIFICATION.md docs/I13_STAGE2_BLOCKED_EVIDENCE.md docs/I13_STAGE2_SUCCESSOR_TERMINAL_EVIDENCE.md docs/I13_STAGE2_CARD12_FRESH_WORKER_RECOVERY_TERMINAL_EVIDENCE.md docs/I13_STAGE2_CARD12_MODEL_FREE_PROVIDER_BASE_CORRECTION_CONTRACT.md docs/I13_STAGE2_CARD12_COLD_START_QUARANTINED_RECOVERY_CONTRACT.md
	upstream/dcp-orchestrator.lock
	bin/dcp-ao bin/dcp-ao-submit lib/dcp-ao-common.sh lib/dcp-ao-gateway.sh lib/dcp-ao-install.sh lib/dcp-ao-adapter.sh
	tests/test_i3.sh tests/test_i8_gateway.sh tests/test_i12_install.sh tests/test_i12_codex_preflight.sh tests/fixtures/codex-preflight/codex
)
for path in "${required[@]}"; do [[ -s "$path" ]]; done

retired=(
	bin/dcp-orchestrator dcp_orchestrator pyproject.toml scripts/build_artifact.py scripts/safety_audit.py
	tests/test_build.py tests/test_canary.py tests/test_server.py tests/test_i7_gateway.sh
	upstream/agent-orchestrator.lock patches/agent-orchestrator third_party/agent-orchestrator
)
for path in "${retired[@]}"; do [[ ! -e "$path" ]]; done

[[ "$DCP_AO_FORK_REPOSITORY" == 'https://github.com/orenvlad-ai/dcp-orchestrator.git' ]]
[[ "$DCP_AO_FORK_PR_URL" == 'https://github.com/orenvlad-ai/dcp-orchestrator/pull/34' ]]
[[ "$DCP_AO_FORK_COMMIT" == 04a967c26499a482fbff9a204bab046d79d2a2e2 ]]
[[ "$DCP_AO_FORK_TREE" == fedee6276e8ce4a492d3c298aaf4bf843179c8bc ]]
[[ "$DCP_AO_PRIOR_FORK_COMMIT" == 798e9bfb8f75846d846f2ec2d4dfc9ec0076573b ]]
[[ "$DCP_AO_PRIOR_FORK_TREE" == e5668c51fbc3c7aae872cafbe4759fc405fa0677 ]]
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
grep -Fq 'fetch --no-tags origin "$DCP_AO_FORK_COMMIT"' lib/dcp-ao-common.sh
grep -Fq 'fetch --no-tags "$fetch_mode" origin "$DCP_AO_FORK_COMMIT"' lib/dcp-ao-common.sh
grep -Fq 'fetch_mode=--unshallow' lib/dcp-ao-common.sh
! grep -Fq -- '--depth=20' lib/dcp-ao-common.sh
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
grep -Fq 'dcp-review-lab --profile synthetic-pr --task-id task-id' lib/dcp-ao-adapter.sh
grep -Fq 'https://github.com/orenvlad-ai/dcp-review-lab.git' lib/dcp-ao-adapter.sh
grep -Fq 'dcp_ao_review_config_json' lib/dcp-ao-adapter.sh
grep -Fq 'project.config.sessionPrefix' lib/dcp-ao-adapter.sh
grep -Fq 'project.config.worker.agentConfig.dcpReviewLabNetwork' lib/dcp-ao-adapter.sh
grep -Fq 'dcp-review-lab-([6-9]|1[0-2])' lib/dcp-ao-adapter.sh
grep -Fq 'expected_session_id="$(dcp_ao_reject_duplicate_review_task' lib/dcp-ao-adapter.sh
grep -Fq 'I13 arbiter cohort already contains both bounded tasks' lib/dcp-ao-adapter.sh
grep -Fq 'if the trusted daemon supplies the exact I13 arbiter recovery identity' lib/dcp-ao-adapter.sh tests/fixtures/fake-ao
! grep -Fq 'if the trusted DCP daemon supplies the exact I13 arbiter recovery identity' lib/dcp-ao-adapter.sh tests/fixtures/fake-ao
! grep -Fq 'dcp-pr-lab' lib/dcp-ao-adapter.sh tests/test_i3.sh tests/fixtures/fake-ao docs/CURRENT_OPERATING_CONTRACT.md
grep -Fq 'project.config.reviewers.0.harness' lib/dcp-ao-adapter.sh
grep -Fq 'DCP:$task_id' lib/dcp-ao-adapter.sh
grep -Fq 'task id already exists' lib/dcp-ao-adapter.sh
! grep -Fq 'npm run dev' bin/dcp-ao
! grep -Fq '__gateway-launch' bin/dcp-ao
grep -Fq 'dcp_ao_install_prepare_runtime' bin/dcp-ao lib/dcp-ao-install.sh
grep -Fq "activity_state = 'active'" lib/dcp-ao-install.sh
grep -Fq 'dcp_ao_install_worker_process_state' lib/dcp-ao-install.sh
grep -Fq 'dcp_ao_install_arbiter_process_state' lib/dcp-ao-install.sh
grep -Fq "rr.status = 'running'" lib/dcp-ao-install.sh
grep -Fq "status = 'running' AND model_call_count = 1" lib/dcp-ao-install.sh
grep -Fq 'dcp_review_lab_arbiter_v1_successor_attempt' lib/dcp-ao-install.sh tests/test_i12_install.sh
grep -Fq 'dcp-global-release-arbiter-v1-successor' lib/dcp-ao-install.sh tests/test_i12_install.sh
grep -Fq 'dcp-arbiter-successor-3c62ea80b56ef94165519d4f01e4c449c320bff22d16b902dd68d4a1a355ea7d' lib/dcp-ao-install.sh tests/test_i12_install.sh
grep -Fq 'dcp_review_lab_card12_fresh_worker_recovery' lib/dcp-ao-install.sh tests/test_i12_install.sh
grep -Fq 'dcp-card12-fresh-worker-recovery-d2b7142bc9e5844ba165abe24d3222b3e1a94c3577fba5f6f8d97ec3dbad151b' lib/dcp-ao-install.sh tests/test_i12_install.sh
grep -Fq 'dcp_review_lab_card12_model_free_rebase_continuation' lib/dcp-ao-install.sh tests/test_i12_install.sh
grep -Fq 'dcp-card12-model-free-rebase-continuation-66eb630c1995f90b37429a2f6c57c57794dda9fc98a29149c88bdb2f01131060' lib/dcp-ao-install.sh tests/test_i12_install.sh
grep -Fq 'dcp_review_lab_card12_cold_start_recovery' lib/dcp-ao-install.sh tests/test_i12_install.sh
grep -Fq 'dcp-card12-cold-start-recovery-087176dbe56428dc97a99823a94daa4687c41b15c14a08de21db2c6c602f0f2f' lib/dcp-ao-install.sh tests/test_i12_install.sh
grep -Fq 'kill -TERM "$app_pid"' lib/dcp-ao-install.sh
! grep -REq 'open[[:space:]]+-a|osascript' bin lib
! grep -Fq '/Applications/Agent Orchestrator.app' bin/dcp-ao lib/dcp-ao-common.sh lib/dcp-ao-gateway.sh
! grep -Eq '^  (launch|daemon|stop|restart)[[:space:]]' < <(bin/dcp-ao --help)
! grep -Rq -- '--dangerously-bypass-hook-trust' bin lib
! grep -Rq -- '--ask-for-approval' bin lib
grep -Fq 'approval_policy="on-request"' lib/dcp-ao-common.sh
grep -Fq -- '--sandbox workspace-write' lib/dcp-ao-common.sh
grep -Fq -- '--add-dir "$lab_root/evidence/codex-preflight/gitdir"' lib/dcp-ao-common.sh
grep -Fq -- '--add-dir "$lab_root/evidence/codex-preflight/common"' lib/dcp-ao-common.sh

grep -Fq 'docs/CURRENT_OPERATING_CONTRACT.md' AGENTS.md
grep -Fq 'current approved development stage is the pinned card-12 cold-start' docs/CURRENT_OPERATING_CONTRACT.md
grep -Fq 'evidence_status: technical-blocked' docs/I13_STAGE2_BLOCKED_EVIDENCE.md
grep -Fq 'evidence_status: technical-blocked' docs/I13_STAGE2_SUCCESSOR_TERMINAL_EVIDENCE.md
grep -Fq 'failed/repair_launch_failed' docs/I13_STAGE2_SUCCESSOR_TERMINAL_EVIDENCE.md
grep -Fq '132,785 tokens' docs/I13_STAGE2_SUCCESSOR_TERMINAL_EVIDENCE.md
grep -Fq 'evidence_status: technical-blocked' docs/I13_STAGE2_CARD12_FRESH_WORKER_RECOVERY_TERMINAL_EVIDENCE.md
grep -Fq 'failed/worker_process_failed' docs/I13_STAGE2_CARD12_FRESH_WORKER_RECOVERY_TERMINAL_EVIDENCE.md
grep -Fq '25663a5a551fce7ec0d6d9055588b4c4d1d1294fd926e2c7c2347cacd799ab59' docs/I13_STAGE2_CARD12_MODEL_FREE_PROVIDER_BASE_CORRECTION_CONTRACT.md
grep -Fq 'dbaf01b05e85ffffa4c843a905e2fe5229eaf0da' docs/I13_STAGE2_CARD12_MODEL_FREE_PROVIDER_BASE_CORRECTION_CONTRACT.md
grep -Fq '019ff5f3-c655-7ea2-9213-6e137f148285' docs/I13_STAGE2_CARD12_FRESH_WORKER_RECOVERY_TERMINAL_EVIDENCE.md
grep -Fq '149,169' docs/I13_STAGE2_CARD12_FRESH_WORKER_RECOVERY_TERMINAL_EVIDENCE.md
grep -Fq '087176dbe56428dc97a99823a94daa4687c41b15c14a08de21db2c6c602f0f2f' docs/I13_STAGE2_CARD12_COLD_START_QUARANTINED_RECOVERY_CONTRACT.md
grep -Fq '66,811' docs/I13_STAGE2_CARD12_COLD_START_QUARANTINED_RECOVERY_CONTRACT.md
grep -Fq '/Users/ovlmacbook/Applications/DCP Orchestrator.app' docs/CURRENT_OPERATING_CONTRACT.md
grep -Fq 'bin/dcp-ao-submit' docs/CURRENT_OPERATING_CONTRACT.md
grep -Fq 'source/dev' docs/CURRENT_OPERATING_CONTRACT.md
grep -Fq 'CODEX_SQLITE_HOME' docs/CURRENT_OPERATING_CONTRACT.md
grep -Fq 'private pane-local exact-binary `ao` alias remains only for compatibility' docs/CURRENT_OPERATING_CONTRACT.md
grep -Fq -- '--output-schema' docs/CURRENT_OPERATING_CONTRACT.md
grep -Fq 'one unused emergency worker-call ceiling remains' docs/CURRENT_OPERATING_CONTRACT.md
grep -Fq 'automatic reviewer allowance is consumed' docs/CURRENT_OPERATING_CONTRACT.md
grep -Fq 'failed I2 run `b65be186-7326-4272-85aa-acfcd39bc938`' docs/CURRENT_OPERATING_CONTRACT.md
grep -Fq 'failed I3 run' docs/CURRENT_OPERATING_CONTRACT.md
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

bash -n bin/dcp-ao bin/dcp-ao-submit lib/dcp-ao-common.sh lib/dcp-ao-gateway.sh lib/dcp-ao-install.sh lib/dcp-ao-adapter.sh tests/test_i3.sh tests/test_i8_gateway.sh tests/test_i12_install.sh tests/test_i12_codex_preflight.sh tests/fixtures/fake-ao tests/fixtures/codex-preflight/codex
tests/test_i3.sh
tests/test_i8_gateway.sh
tests/test_i12_install.sh
tests/test_i12_codex_preflight.sh
git diff --check
printf 'PASS I12 deterministic audit\n'
