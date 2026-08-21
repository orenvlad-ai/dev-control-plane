#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
cd "$REPO_ROOT"

target=docs/TARGET_ARCHITECTURE_V1.md
current=docs/CURRENT_OPERATING_CONTRACT.md
manifest=docs/DCP_WBC_INTEGRATION_TWIN_CURRENT_PROGRAM_MANIFEST.md

for path in "$target" "$current" "$manifest" \
	docs/DCP_WBC_INTEGRATION_TWIN_DCP_V2_ARCHITECTURE_CONTRACT.md \
	docs/DCP_LAB_HAPPY_PATH_V1_CONTRACT.md \
	docs/DCP_REAL_TARGET_V1_CONTRACT.md \
	docs/DCP_REAL_TARGET_PROVIDER_IDENTITY_V1_CONTRACT.md \
	docs/DCP_REAL_TARGET_PROVIDER_IDENTITY_V1_TERMINAL_EVIDENCE.md \
	docs/DCP_REAL_TARGET_SUBMIT_RECOVERY_V1_CONTRACT.md \
	docs/DCP_REAL_TARGET_SUBMIT_RECOVERY_V1_TERMINAL_EVIDENCE.md \
	docs/DCP_REAL_TARGET_REPOSITORY_RENAME_V1_CONTRACT.md \
	docs/DCP_REAL_TARGET_REPOSITORY_RENAME_V1_TERMINAL_EVIDENCE.md; do
	[[ -s "$path" ]]
done

grep -Fq 'contract_status: target-design-only' "$target"
grep -Fq 'historical DCP v1 design provenance' "$target"
grep -Fq 'DCP_WBC_INTEGRATION_TWIN_DCP_V2_ARCHITECTURE_CONTRACT.md' "$target"
grep -Fq 'DCP_WBC_INTEGRATION_TWIN_CURRENT_PROGRAM_MANIFEST.md' "$target"
grep -Fq 'not operating authority' "$target"

for invariant in \
	'GitHub is authoritative for repository refs, pull requests, checks, merge' \
	'READY_FOR_ADMISSION' \
	'WAITING_GLOBAL_RELEASE' \
	'release:ready' \
	'HumanGate is allowed only' \
	'Symphony is provenance, not a dependency' \
	'HistoryProvider' \
	'provider=none' \
	'I9 does not install, invoke, contact or test Entire'; do
	grep -Fq "$invariant" "$target"
done

for heading in \
	'## 2. Authority boundaries' \
	'## 5. Task, review and release states' \
	'## 6. Nominal sequence' \
	'## 9. Durable events and checkpoints' \
	'## 13. Failure matrix' \
	'## 14. Optional history/provenance seam' \
	'## 15. Fork and source-of-truth boundary' \
	'## 16. Paper test plan'; do
	grep -Fq "$heading" "$target"
done

[[ "$(grep -c '^```mermaid$' "$target")" -eq 2 ]]
[[ "$(grep -c '^| .* |' "$target")" -ge 75 ]]

happy_path=docs/DCP_LAB_HAPPY_PATH_V1_CONTRACT.md
grep -Fq 'contract_revision: 2026-08-14.3' "$happy_path"
grep -Fq 'At most three DCP model actions may be active globally' "$happy_path"
grep -Fq 'one context-free review for the resulting new exact head' "$happy_path"

real_target=docs/DCP_REAL_TARGET_V1_CONTRACT.md
grep -Fq 'status: owner-authorized implementation contract' "$real_target"
grep -Fq 'required check name is exactly `baseline`' "$real_target"
grep -Fq 'preparation task launches no worker, reviewer or arbiter' "$real_target"

provider=docs/DCP_REAL_TARGET_PROVIDER_IDENTITY_V1_CONTRACT.md
grep -Fq 'contract_status: owner-approved-pre-runtime' "$provider"
grep -Fq 'Do not run the real product DCP task' "$provider"
grep -Fq 'evidence_status: technical-complete' docs/DCP_REAL_TARGET_PROVIDER_IDENTITY_V1_TERMINAL_EVIDENCE.md

submit=docs/DCP_REAL_TARGET_SUBMIT_RECOVERY_V1_CONTRACT.md
grep -Fq 'no second submit is permitted' "$submit"
grep -Fq 'evidence_status: COMPLETE' docs/DCP_REAL_TARGET_SUBMIT_RECOVERY_V1_TERMINAL_EVIDENCE.md

rename=docs/DCP_REAL_TARGET_REPOSITORY_RENAME_V1_CONTRACT.md
grep -Fq 'contract_status: owner-approved-pre-runtime' "$rename"
grep -Fq 'does not authorize a product task' "$rename"
grep -Fq 'evidence_status: COMPLETE' docs/DCP_REAL_TARGET_REPOSITORY_RENAME_V1_TERMINAL_EVIDENCE.md

grep -Fq '[DCP v1 target architecture](TARGET_ARCHITECTURE_V1.md)' "$current"
grep -Fq 'DCP_LAB_HAPPY_PATH_V1_CONTRACT.md' "$current"
grep -Fq 'operating_contract_revision: 2026-08-21.5' "$current"
grep -Fq 'manifest_revision: 2026-08-21.5' "$manifest"
grep -Fq 'Historical WBC, DCP Lab and DCP v1 paths' docs/ROADMAP.md

! grep -Eq '(/Users/|/home/|\.codex/worktrees/)' "$target" "$current" "$manifest"
bash -n scripts/i9_contract_audit.sh
git diff --check
printf 'PASS I9 historical target-contract audit\n'
