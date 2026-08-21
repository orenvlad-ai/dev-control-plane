#!/usr/bin/env bash
set -euo pipefail

source upstream/dcp-orchestrator.lock

[[ "$DCP_AO_TWIN_STAGE6_RECOVERY_PR_URL" == https://github.com/orenvlad-ai/dcp-orchestrator/pull/75 ]]
[[ "$DCP_AO_TWIN_STAGE6_RECOVERY_SOURCE_COMMIT" == 11401ff6eadb80fd87e48229fb8c5458095a63b1 ]]
[[ "$DCP_AO_TWIN_STAGE6_RECOVERY_SOURCE_TREE" == 91bf6e25ec1b0e0f971ad36f7b80272aded2482c ]]
[[ "$DCP_AO_TWIN_STAGE5_RECEIPT_SHA256" == 54dd88beef2e9c93ee86435df2645d6707acf2dc3e2c0c0b4dad6de9b40cc9c0 ]]
[[ "$DCP_AO_TWIN_STAGE6_REQUEST_DIGEST" == ce4cad12791d0d1faf13304d4fc0d8690dfbd8df77c42a3ee938a6a1c2dcb50e ]]
[[ "$DCP_AO_TWIN_STAGE6_SCOPE_DIGEST" == 6e4dff1d409632c7413242b0430ea14c9270ea9d3027402967ae76f12f5e0a2a ]]
[[ "$DCP_AO_TWIN_STAGE6_PAYLOAD_DIGEST" == a50a5196f5bb7de1127c3900636a73dcdd4930d844842a6978e61895db2167cb ]]

for path in bin/dcp-ao lib/dcp-ao-common.sh lib/dcp-ao-install.sh lib/dcp-ao-adapter.sh \
	tests/test_i41_stage6_recovery_response.sh tests/test_i41_stage6_stopped_sqlite_reader.sh \
	docs/DCP_WBC_INTEGRATION_TWIN_STAGE6_POST_SUBMIT_NATIVE_SHELL_CORRECTION_CONTRACT.md \
	docs/CURRENT_OPERATING_CONTRACT.md; do
	[[ -s "$path" ]]
done

grep -Fq '0085_dcp_v2_twin_native_shell_compatibility.sql' lib/dcp-ao-common.sh
grep -Fq 'Use:    "stage6-recovery-preflight"' lib/dcp-ao-common.sh
grep -Fq 'dcp_ao_validate_twin_stage6_recovery_response()' lib/dcp-ao-adapter.sh
grep -Fq 'Stage 6 recovery response contains duplicate fields' lib/dcp-ao-adapter.sh
grep -Fq 'dcp_ao_verify_twin_stage6_recovery_fence()' lib/dcp-ao-adapter.sh
grep -Fq '1|1|1|1|0|0|0|0' lib/dcp-ao-adapter.sh
grep -Fq '73|0' lib/dcp-ao-adapter.sh
grep -Fq 'Stage 6 recovery Command payload fence differs' lib/dcp-ao-adapter.sh
grep -Fq 'Stage 6 recovery Command lease fence differs' lib/dcp-ao-adapter.sh
grep -Fq 'install-stage6-recovery) install_stage6_recovery_app' bin/dcp-ao
grep -Fq 'generic Stage 5 install is disabled for Stage 6 locks' bin/dcp-ao
grep -Fq 'dcp stage6-recovery-preflight' bin/dcp-ao
grep -Fq 'preflight-stage6-recovery) dcp_ao_preflight_exact_contour' bin/dcp-ao
grep -Fq 'dcp_ao_verify_twin_stage6_recovery_fence "$lab_root" 85 1' bin/dcp-ao
grep -Fq '! dcp_ao_verify_installed_bundle "$lab_root" ||' bin/dcp-ao
grep -Fq '! dcp_ao_verify_twin_stage6_recovery_fence "$lab_root" 85 1; then' bin/dcp-ao
grep -Fq 'Stage 6 recovery rollback identity verification failed' bin/dcp-ao
grep -Fq 'immutable install policy read requires the exact runtime to be stopped' lib/dcp-ao-install.sh
grep -Fq "printf 'twin_schema=%s\\n' \"\$twin_schema\"" lib/dcp-ao-common.sh
! grep -Fq "printf 'twin_schema=85\\n'" lib/dcp-ao-common.sh
grep -Fq 'operating_contract_revision: 2026-08-21.2' docs/CURRENT_OPERATING_CONTRACT.md
grep -Fq '`11401ff6eadb80fd87e48229fb8c5458095a63b1`' docs/CURRENT_OPERATING_CONTRACT.md AGENTS.md
! grep -Fq 'dcp stage5-activate' <<<"$(sed -n '/install_stage6_recovery_app()/,/^}/p' bin/dcp-ao)"

bash -n bin/dcp-ao lib/dcp-ao-common.sh lib/dcp-ao-install.sh lib/dcp-ao-adapter.sh \
	tests/test_i41_stage6_recovery_response.sh tests/test_i41_stage6_stopped_sqlite_reader.sh
tests/test_i41_stage6_recovery_response.sh
tests/test_i41_stage6_stopped_sqlite_reader.sh
git diff --check

printf 'PASS I41 WBC integration twin Stage 6 exact recovery pin/install guard\n'
