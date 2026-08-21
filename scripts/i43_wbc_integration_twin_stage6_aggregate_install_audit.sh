#!/usr/bin/env bash
set -euo pipefail

source upstream/dcp-orchestrator.lock

contract=docs/DCP_WBC_INTEGRATION_TWIN_STAGE6_AGGREGATE_INSTALL_CONTINUATION_CONTRACT.md
manifest=docs/DCP_WBC_INTEGRATION_TWIN_CURRENT_PROGRAM_MANIFEST.md
current=docs/CURRENT_OPERATING_CONTRACT.md

for path in "$contract" "$manifest" "$current" upstream/dcp-orchestrator.lock \
	bin/dcp-ao lib/dcp-ao-common.sh lib/dcp-ao-install.sh lib/dcp-ao-adapter.sh \
	tests/test_i43_stage6_aggregate_response.sh tests/test_i43_stage6_aggregate_fence.sh \
	tests/test_i43_stage6_external_fence.sh; do
	[[ -s "$path" ]]
done

[[ "$DCP_AO_FORK_PR_URL" == https://github.com/orenvlad-ai/dcp-orchestrator/pull/76 ]]
[[ "$DCP_AO_FORK_COMMIT" == d084ae3cf0cb3e5e32ebefa197031c24a2b6392d ]]
[[ "$DCP_AO_FORK_TREE" == a6e3c3347bbbddd256e9edbfc541f115813249d2 ]]
[[ "$DCP_AO_PRIOR_FORK_COMMIT" == "$DCP_AO_TWIN_STAGE6_RECOVERY_SOURCE_COMMIT" ]]
[[ "$DCP_AO_PRIOR_FORK_TREE" == "$DCP_AO_TWIN_STAGE6_RECOVERY_SOURCE_TREE" ]]
[[ "$DCP_AO_TWIN_STAGE6_RECOVERY_RECEIPT_SHA256" == 098056d800d41f666708b7697d6ccef9f3b5cd2e077a939d89dcf0b1f35767e2 ]]
[[ "$DCP_AO_TWIN_STAGE6_NATIVE_ACTION_SEQUENCE" == 74 ]]
[[ "$DCP_AO_TWIN_STAGE6_NATIVE_PREDECESSOR_ACTIONS" == 73 ]]

for marker in \
	'func CanonicalDCPPolicySpawnEnvelope' \
	'p.ModelActive = action.Status == DCPV2ActionRunning && action.RuntimeID != ""' \
	'func (s *TwinService) reconcileNativeModelBoundary' \
	'ErrEffectReconciliationPending' \
	'func (a *TwinGitHubAdapter) PublishReadmission'; do
	grep -Fq "$marker" lib/dcp-ao-common.sh
done

grep -Fq 'dcp_ao_verify_twin_stage6_aggregate_fence()' lib/dcp-ao-adapter.sh
grep -Fq 'dcp_ao_verify_twin_stage6_external_fence()' lib/dcp-ao-adapter.sh
grep -Fq 'dcp_ao_validate_twin_stage6_aggregate_response()' lib/dcp-ao-adapter.sh
grep -Fq 'Stage 6 aggregate response contains duplicate fields' lib/dcp-ao-adapter.sh
grep -Fq '1|1|1|1|0|0|0|0' lib/dcp-ao-adapter.sh
grep -Fq 'Stage 6 aggregate native model Action counts differ' lib/dcp-ao-adapter.sh
grep -Fq 'frozen WBC PR 987 boundary drifted' lib/dcp-ao-adapter.sh

grep -Fq 'install-stage6-aggregate) install_stage6_aggregate_app' bin/dcp-ao
grep -Fq 'preflight-stage6-aggregate) preflight_stage6_aggregate' bin/dcp-ao
grep -Fq 'historical Stage 6 recovery install is disabled for the aggregate lock' bin/dcp-ao
grep -Fq 'verify_stage6_aggregate_predecessor_receipt()' bin/dcp-ao
grep -Fq 'verify_stage6_aggregate_preinstall()' bin/dcp-ao
grep -Fq 'install_built_app_locked "$lab_root" stage6-aggregate' bin/dcp-ao
grep -Fq 'Stage 6 aggregate rollback receipt verification failed' bin/dcp-ao
grep -Fq 'Stage 6 aggregate rollback identity verification failed' bin/dcp-ao
grep -Fq 'dcp_ao_install_prepare_runtime "$lab_root" "$runtime_cli"' bin/dcp-ao
grep -Fq 'dcp_ao_verify_twin_stage6_aggregate_fence "$lab_root" 1' bin/dcp-ao
! grep -Fq 'dcp stage6-recovery-preflight' <<<"$(sed -n '/install_stage6_aggregate_app()/,/^}/p' bin/dcp-ao)"

for exact in \
	'contract_revision: 2026-08-21.1' \
	'`b0c2b6df76adf205229e49c48a1d7277aa7b5059`' \
	'`d084ae3cf0cb3e5e32ebefa197031c24a2b6392d`' \
	'`a6e3c3347bbbddd256e9edbfc541f115813249d2`' \
	'`32477135149`' \
	'`4992765757`' \
	'`098056d800d41f666708b7697d6ccef9f3b5cd2e077a939d89dcf0b1f35767e2`' \
	'install-stage6-aggregate' \
	'## 3. One aggregate installation' \
	'legacy second-authority bridge' \
	'owner_acceptance: not requested or claimed'; do
	grep -Fq "$exact" "$contract"
done

grep -Fq 'manifest_revision: 2026-08-21.2' "$manifest"
grep -Fq 'program_status: Stage 6 aggregate install and same-identity continuation authorized' "$manifest"
grep -Fq 'operating_contract_revision: 2026-08-21.2' "$current"
grep -Fq 'DCP_WBC_INTEGRATION_TWIN_STAGE6_AGGREGATE_INSTALL_CONTINUATION_CONTRACT.md' \
	AGENTS.md README.md "$manifest" "$current" docs/PROJECT_BRIEF.md docs/ROADMAP.md docs/DECISIONS.md
! grep -Eq '(/Users/|/home/|\.codex/worktrees/|gho_[A-Za-z0-9_]+)' "$contract" "$manifest" "$current"
! grep -Fq 'owner_acceptance: accepted' "$contract" "$manifest" "$current"

bash -n bin/dcp-ao lib/dcp-ao-common.sh lib/dcp-ao-install.sh lib/dcp-ao-adapter.sh \
	scripts/i43_wbc_integration_twin_stage6_aggregate_install_audit.sh \
	tests/test_i43_stage6_aggregate_response.sh tests/test_i43_stage6_aggregate_fence.sh \
	tests/test_i43_stage6_external_fence.sh
tests/test_i43_stage6_aggregate_response.sh
tests/test_i43_stage6_aggregate_fence.sh
tests/test_i43_stage6_external_fence.sh
git diff --check

printf 'PASS I43 WBC integration twin Stage 6 aggregate pin/install authority\n'
