#!/usr/bin/env bash
set -euo pipefail

contract=docs/DCP_WBC_INTEGRATION_TWIN_STAGE5_INSTALL_ACTIVATION_CONTRACT.md
current=docs/CURRENT_OPERATING_CONTRACT.md

for path in "$contract" "$current" AGENTS.md; do
	[[ -s "$path" ]]
done

grep -Fq 'contract_revision: 2026-08-20.4' "$contract"
grep -Fq 'operating_contract_revision: 2026-08-21.1' "$current"
grep -Fq '`i12-20260820T155118Z`' "$contract" "$current" AGENTS.md
grep -Fq '`10481ec494534c3929771b2db0d1cdc6a17bce61682b7ef9c4b1f34b534063cf`' "$contract"
grep -Fq '`activation.sourceCommit`' "$contract"
grep -Fq '`activation.installReceiptSha`' "$contract"
grep -Fq '`SourceCommit`, `SourceTree` and `InstallReceiptSHA`' "$contract"
grep -Fq '`c1fc43d74cd517b7d73540f340058fa17b56ef15`' "$contract"
grep -Fq '`ff51ca2b1f6f9fa502b999f50a366a8e35035421`' "$contract"
grep -Fq '`685ae805a61f24f6c7e0628c788e2ad0cfce8d605b65143034296cb212fc757e`' "$contract"
grep -Fq 'exactly one further governed' "$contract" "$current" AGENTS.md
grep -Fq 'Any second defect class, second failed install' "$contract"
grep -Fq 'Stage 6 remains' "$contract"
grep -Fq 'ineligible until the corrected install/preflight succeeds' "$contract"

printf 'PASS I37 Stage 5 assertion-recovery authority audit\n'
