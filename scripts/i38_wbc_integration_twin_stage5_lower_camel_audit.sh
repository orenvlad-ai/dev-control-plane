#!/usr/bin/env bash
set -euo pipefail

source upstream/dcp-orchestrator.lock

[[ "$DCP_AO_TWIN_STAGE5_SOURCE_COMMIT" == c1fc43d74cd517b7d73540f340058fa17b56ef15 ]]
[[ "$DCP_AO_TWIN_STAGE5_SOURCE_TREE" == ff51ca2b1f6f9fa502b999f50a366a8e35035421 ]]

for path in bin/dcp-ao lib/dcp-ao-adapter.sh \
	tests/test_i37_stage5_activation_response.sh \
	docs/DCP_WBC_INTEGRATION_TWIN_STAGE5_INSTALL_ACTIVATION_CONTRACT.md \
	docs/CURRENT_OPERATING_CONTRACT.md; do
	[[ -s "$path" ]]
done

grep -Fq 'dcp_ao_validate_twin_stage5_activation_response()' lib/dcp-ao-adapter.sh
grep -Fq '/usr/bin/jq --stream -s' lib/dcp-ao-adapter.sh
grep -Fq 'Stage 5 activation response contains duplicate fields' lib/dcp-ao-adapter.sh
grep -Fq '.activation.sourceCommit == $source' lib/dcp-ao-adapter.sh
grep -Fq '.activation.installReceiptSha == $receipt' lib/dcp-ao-adapter.sh
grep -Fq 'keys == ["activation", "created", "projectCreated", "projectId", "projectPath"]' lib/dcp-ao-adapter.sh
grep -Fq 'dcp_ao_validate_twin_stage5_activation_response "$lab_root" "$receipt_sha" "$activation_output"' bin/dcp-ao
! grep -Fq '.activation.SourceCommit' bin/dcp-ao lib/dcp-ao-adapter.sh
! grep -Fq '.activation.InstallReceiptSHA' bin/dcp-ao lib/dcp-ao-adapter.sh
grep -Fq 'contract_revision: 2026-08-20.4' docs/DCP_WBC_INTEGRATION_TWIN_STAGE5_INSTALL_ACTIVATION_CONTRACT.md
grep -Fq 'operating_contract_revision: 2026-08-21.1' docs/CURRENT_OPERATING_CONTRACT.md

bash -n bin/dcp-ao lib/dcp-ao-adapter.sh tests/test_i37_stage5_activation_response.sh
tests/test_i37_stage5_activation_response.sh

printf 'PASS I38 Stage 5 lower-camel activation parser audit\n'
