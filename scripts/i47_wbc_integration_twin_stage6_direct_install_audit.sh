#!/usr/bin/env bash
set -euo pipefail
trap 'printf "I47 audit failed at line %s\n" "$LINENO" >&2' ERR

source upstream/dcp-orchestrator.lock

contract=docs/DCP_WBC_INTEGRATION_TWIN_STAGE6_DIRECT_MODEL_STABLE_INSTALL_CONTRACT.md
manifest=docs/DCP_WBC_INTEGRATION_TWIN_CURRENT_PROGRAM_MANIFEST.md
current=docs/CURRENT_OPERATING_CONTRACT.md

for path in "$contract" "$manifest" "$current" upstream/dcp-orchestrator.lock bin/dcp-ao \
	lib/dcp-ao-common.sh lib/dcp-ao-adapter.sh lib/dcp-ao-install.sh lib/dcp-ao-stage6-direct-install.sh \
	tests/test_i47_stage6_direct_source_guard.sh tests/test_i47_stage6_direct_fence.sh \
	tests/test_i47_stage6_direct_migration_response.sh tests/test_i47_stage6_direct_rollback.sh; do
	[[ -s "$path" ]]
done

[[ "$DCP_AO_FORK_PR_URL" == https://github.com/orenvlad-ai/dcp-orchestrator/pull/77 ]]
[[ "$DCP_AO_FORK_COMMIT" == e9eb18a99db71813ac8c4556a614d6a3ce4108aa ]]
[[ "$DCP_AO_FORK_TREE" == b4db2b329accc9a93691bda7c306cc864b07ee56 ]]
[[ "$DCP_AO_PRIOR_FORK_COMMIT" == d084ae3cf0cb3e5e32ebefa197031c24a2b6392d ]]
[[ "$DCP_AO_PRIOR_FORK_TREE" == a6e3c3347bbbddd256e9edbfc541f115813249d2 ]]
[[ "$DCP_AO_TWIN_STAGE6_AGGREGATE_RECEIPT_SHA256" == 19550a9f02b14f13be8a80214529025fd6d4fe7dc8e5bd12c5eaa1a47dd54b0c ]]
[[ "$DCP_AO_TWIN_STAGE6_DIRECT_INSTALL_ID" == stage6-direct-model-e9eb18a99db-85-to-86-v1 ]]

for marker in \
	'stable managed source must be a non-symlink standalone clone' \
	'managed source is inside an ephemeral or task-owned root' \
	'stable managed source clone is absent; installer will not clone or recover it' \
	'dcp_ao_source_filesystem_identity()'; do
	grep -Fq "$marker" lib/dcp-ao-common.sh
done
for marker in \
	'MANAGED_SOURCE_WORKTREE_DRIFT before staging' \
	'MANAGED_SOURCE_WORKTREE_DRIFT during source staging' \
	'Stage 6 direct install identity was already invoked; equal rerun is forbidden' \
	'git -C "$source_dir" archive --format=tar' \
	'worker_archive_sha256=' \
	'prior_database_wal_state=' \
	'prior_database_shm_state=' \
	'dcp_ao_stage6_direct_verify_install_copy' \
	'/usr/bin/ditto -c -k --keepParent' \
	'import --dry-run --yes' \
	'adoption_input_sha256=' \
	'dcp_ao_stage6_direct_rollback' \
	'rollback=not-invoked'; do
	grep -Fq "$marker" lib/dcp-ao-stage6-direct-install.sh
done
grep -Fq 'dcp_ao_verify_twin_stage6_direct_fence()' lib/dcp-ao-adapter.sh
grep -Fq "'0|0|0'" lib/dcp-ao-adapter.sh
grep -Fq 'install-stage6-direct-model) install_stage6_direct_model_app' bin/dcp-ao
grep -Fq 'preflight-stage6-direct-model) preflight_stage6_direct_model' bin/dcp-ao

for exact in \
	'contract_revision: 2026-08-22.1' \
	'`stage6-direct-model-e9eb18a99db-85-to-86-v1`' \
	'`e9eb18a99db71813ac8c4556a614d6a3ce4108aa`' \
	'`b4db2b329accc9a93691bda7c306cc864b07ee56`' \
	'`0086_dcp_v2_direct_model_authority.sql`' \
	'owner_acceptance: not requested or claimed'; do
	grep -Fq "$exact" "$contract"
done

grep -Fxq 'manifest_revision: 2026-08-22.3' "$manifest"
grep -Fxq 'operating_contract_revision: 2026-08-22.3' "$current"
grep -Fq 'DCP_WBC_INTEGRATION_TWIN_STAGE6_DIRECT_MODEL_STABLE_INSTALL_CONTRACT.md' \
	AGENTS.md README.md "$manifest" "$current" docs/PROJECT_BRIEF.md docs/ROADMAP.md docs/DECISIONS.md
! grep -Eq '(/Users/|/home/|\.codex/worktrees/|gho_[A-Za-z0-9_]+)' "$contract" "$manifest" "$current"
! grep -Fq 'owner_acceptance: accepted' "$contract" "$manifest" "$current"

bash -n bin/dcp-ao lib/dcp-ao-common.sh lib/dcp-ao-adapter.sh lib/dcp-ao-install.sh \
	lib/dcp-ao-stage6-direct-install.sh scripts/i47_wbc_integration_twin_stage6_direct_install_audit.sh \
	tests/test_i47_stage6_direct_source_guard.sh tests/test_i47_stage6_direct_fence.sh \
	tests/test_i47_stage6_direct_migration_response.sh tests/test_i47_stage6_direct_rollback.sh
tests/test_i47_stage6_direct_source_guard.sh
tests/test_i47_stage6_direct_fence.sh
tests/test_i47_stage6_direct_migration_response.sh
tests/test_i47_stage6_direct_rollback.sh
git diff --check

printf 'PASS I47 Stage 6 direct-model stable-source pin/install authority\n'
