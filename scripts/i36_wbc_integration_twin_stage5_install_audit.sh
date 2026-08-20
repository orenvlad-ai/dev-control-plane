#!/usr/bin/env bash
set -euo pipefail

source upstream/dcp-orchestrator.lock

[[ "$DCP_AO_FORK_PR_URL" == https://github.com/orenvlad-ai/dcp-orchestrator/pull/74 ]]
[[ "$DCP_AO_FORK_COMMIT" == c1fc43d74cd517b7d73540f340058fa17b56ef15 ]]
[[ "$DCP_AO_FORK_TREE" == ff51ca2b1f6f9fa502b999f50a366a8e35035421 ]]
[[ "$DCP_AO_PRIOR_FORK_COMMIT" == 84dbee2a701186628c1ad92950aa14639000fc0b ]]
[[ "$DCP_AO_PRIOR_FORK_TREE" == 9374ece6efccf87dcb8a7627c97722a16d063b77 ]]
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
grep -Fq 'operating_contract_revision: 2026-08-20.7' docs/CURRENT_OPERATING_CONTRACT.md
grep -Fq '`c1fc43d74cd517b7d73540f340058fa17b56ef15`' docs/CURRENT_OPERATING_CONTRACT.md AGENTS.md
grep -Fq 'does not itself build, install, open live SQLite, start runtime or submit' docs/CURRENT_OPERATING_CONTRACT.md

bash -n bin/dcp-ao bin/dcp-ao-submit lib/dcp-ao-common.sh lib/dcp-ao-adapter.sh lib/dcp-ao-install.sh
tests/test_i36_twin_adapter.sh

printf 'PASS I36 WBC integration twin Stage 5 exact-pin/install audit\n'
