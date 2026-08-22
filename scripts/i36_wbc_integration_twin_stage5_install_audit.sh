#!/usr/bin/env bash
set -euo pipefail

source upstream/dcp-orchestrator.lock

[[ "$DCP_AO_TWIN_STAGE6_RECOVERY_PR_URL" == https://github.com/orenvlad-ai/dcp-orchestrator/pull/75 ]]
[[ "$DCP_AO_TWIN_STAGE6_RECOVERY_SOURCE_COMMIT" == 11401ff6eadb80fd87e48229fb8c5458095a63b1 ]]
[[ "$DCP_AO_TWIN_STAGE6_RECOVERY_SOURCE_TREE" == 91bf6e25ec1b0e0f971ad36f7b80272aded2482c ]]
[[ "$DCP_AO_TWIN_POLICY_AGENT_RULES_BYTES" == 959 ]]
[[ "$DCP_AO_TWIN_POLICY_AGENT_RULES_SHA256" == 872b689e4d6b4251e5830fdc68ee4943e291f81ea62494b7197adbbb7305306b ]]
[[ "$DCP_AO_TWIN_STAGE5_CONTRACT_COMMIT" == 4143982eb054a40537d963356c209bfe8447ba31 ]]
[[ "$DCP_AO_TWIN_STAGE5_BASE_SHA" == 375b9b2d0b4c2fce6f2c417850553f79e24a0d92 ]]
[[ "$DCP_AO_TWIN_WORKFLOW_ID" == 338377713 ]]

for path in bin/dcp-ao bin/dcp-ao-submit lib/dcp-ao-common.sh lib/dcp-ao-adapter.sh \
	lib/dcp-ao-install.sh tests/test_i36_twin_adapter.sh docs/CURRENT_OPERATING_CONTRACT.md; do
	[[ -s "$path" ]]
done

grep -Fq 'dcp_ao_verify_twin_policy_source' lib/dcp-ao-common.sh
grep -Fq 'dcp_ao_twin_rules_match_source_lock' lib/dcp-ao-adapter.sh
grep -Fq 'dcp_ao_validate_twin_provider_identity' lib/dcp-ao-adapter.sh
grep -Fq 'dcp_ao_validate_twin_target' lib/dcp-ao-adapter.sh
grep -Fq 'dcp_ao_verify_twin_stopped_activation' lib/dcp-ao-adapter.sh
grep -Fq 'preflight-stage5) dcp_ao_preflight_exact_contour' bin/dcp-ao
grep -Fq 'dcp_ao_verify_twin_stopped_activation "$lab_root" 1 1' bin/dcp-ao
grep -Fq 'dcp_ao_submit_v2_twin_once' lib/dcp-ao-adapter.sh
grep -Fq -- '--request POST' lib/dcp-ao-adapter.sh
! grep -Fq -- '--retry' lib/dcp-ao-adapter.sh
grep -Fq 'dcp stage5-activate' bin/dcp-ao
grep -Fq -- '--target-path "$lab_root/targets/dcp-wbc-integration-lab"' bin/dcp-ao
grep -Fq 'activation-failure prior receipt rollback verification failed' bin/dcp-ao
grep -Fq 'init-twin' bin/dcp-ao
grep -Fq 'operating_contract_revision: 2026-08-23.1' docs/CURRENT_OPERATING_CONTRACT.md
grep -Fq '`c1fc43d74cd517b7d73540f340058fa17b56ef15`' docs/DCP_WBC_INTEGRATION_TWIN_STAGE5_TERMINAL_EVIDENCE.md
grep -Fq 'current_program_role: historical-complete Stage 5 authority' docs/DCP_WBC_INTEGRATION_TWIN_STAGE5_INSTALL_ACTIVATION_CONTRACT.md

bash -n bin/dcp-ao bin/dcp-ao-submit lib/dcp-ao-common.sh lib/dcp-ao-adapter.sh lib/dcp-ao-install.sh
tests/test_i36_twin_adapter.sh

printf 'PASS I36 WBC integration twin Stage 5 exact-pin/install audit\n'
