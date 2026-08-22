#!/usr/bin/env bash
set -euo pipefail
trap 'printf "I51 audit failed at line %s\n" "$LINENO" >&2' ERR

source upstream/dcp-orchestrator.lock

contract=docs/DCP_WBC_INTEGRATION_TWIN_STAGE6_FINAL_PIN_INSTALL_LIVE_CONTRACT.md
manifest=docs/DCP_WBC_INTEGRATION_TWIN_CURRENT_PROGRAM_MANIFEST.md
current=docs/CURRENT_OPERATING_CONTRACT.md

for path in "$contract" "$manifest" "$current" upstream/dcp-orchestrator.lock bin/dcp-ao \
	lib/dcp-ao-common.sh lib/dcp-ao-adapter.sh lib/dcp-ao-stage6-direct-install.sh \
	tests/test_i51_stage6_final_fences.sh; do
	[[ -s "$path" ]]
done

[[ "$DCP_AO_FORK_PR_URL" == https://github.com/orenvlad-ai/dcp-orchestrator/pull/78 ]]
[[ "$DCP_AO_FORK_COMMIT" == d10a9791392e19510590c3fb4a3d231fe980ecf6 ]]
[[ "$DCP_AO_FORK_TREE" == acd93511dd1c77dd2508734bf0b8d331594115cf ]]
[[ "$DCP_AO_PRIOR_FORK_COMMIT" == e9eb18a99db71813ac8c4556a614d6a3ce4108aa ]]
[[ "$DCP_AO_PRIOR_FORK_TREE" == b4db2b329accc9a93691bda7c306cc864b07ee56 ]]
[[ "$DCP_AO_TWIN_STAGE6_DIRECT_RECEIPT_SHA256" == fc8f2a2f6264dc1a3e817e42f124bdbd7040a412eade3fcddf97762f59f214d8 ]]
[[ "$DCP_AO_TWIN_STAGE6_FINAL_INSTALL_ID" == stage6-final-d10a979139-86-to-87-v1 ]]

for marker in \
	'Projects/dcp-orchestrator-stage6-final-install' \
	'0087_dcp_v2_provider_bound_revision.sql' \
	'provider_bound' \
	'ArtifactSourceSHA string' \
	'case domain.DCPV2RevisionProvider:'; do
	grep -Fq "$marker" lib/dcp-ao-common.sh
done

for marker in \
	'dcp_ao_stage6_final_configure()' \
	'DCP_AO_STAGE6_PREDECESSOR_SCHEMA=86' \
	'DCP_AO_STAGE6_TARGET_SCHEMA=87' \
	'adoption_attempt=1' \
	'adoption_status=failed-or-ambiguous' \
	'continuation_attempt=1' \
	'continuation_status=failed-or-ambiguous' \
	'terminal_restart_attempt=1' \
	'terminal_restart_status=failed-or-ambiguous' \
	'dcp_ao_verify_twin_stage6_adopted_fence' \
	'dcp_ao_verify_twin_stage6_published_fence' \
	'dcp_ao_verify_twin_stage6_terminal_fence'; do
	grep -Fq "$marker" lib/dcp-ao-stage6-direct-install.sh
done

for command in \
	'install-stage6-final) install_stage6_final_app' \
	'preflight-stage6-final) preflight_stage6_final' \
	'adopt-stage6-final) adopt_stage6_final' \
	'preflight-stage6-final-adopted) preflight_stage6_final_adopted' \
	'continue-stage6-final) continue_stage6_final' \
	'restart-stage6-final-dedupe) restart_stage6_final_dedupe'; do
	grep -Fq "$command" bin/dcp-ao
done

for exact in \
	'contract_revision: 2026-08-22.1' \
	'`d10a9791392e19510590c3fb4a3d231fe980ecf6`' \
	'`acd93511dd1c77dd2508734bf0b8d331594115cf`' \
	'`fc8f2a2f6264dc1a3e817e42f124bdbd7040a412eade3fcddf97762f59f214d8`' \
	'`stage6-final-d10a979139-86-to-87-v1`' \
	'one atomic same-identity adoption' \
	'one governed live continuation' \
	'one bounded post-terminal restart/dedupe proof' \
	'owner_acceptance: not requested or synthesized'; do
	grep -Fq "$exact" "$contract"
done

grep -Fxq 'manifest_revision: 2026-08-22.5' "$manifest"
grep -Fxq 'program_status: Stage 6 final source merged; one reviewed pin/install/live authority proposed; schema 86 stopped, adoption unconsumed and zero provider effect' "$manifest"
grep -Fxq 'operating_contract_revision: 2026-08-22.5' "$current"
grep -Fq 'DCP_WBC_INTEGRATION_TWIN_STAGE6_FINAL_PIN_INSTALL_LIVE_CONTRACT.md' \
	AGENTS.md README.md "$manifest" "$current" docs/PROJECT_BRIEF.md docs/ROADMAP.md docs/DECISIONS.md
grep -Eq '^\| 6 \| ACTIVE \|' "$manifest"
for stage in 7 8 9; do grep -Eq "^\| ${stage} \| NOT STARTED \|" "$manifest"; done

! grep -Eq '(/Users/|/home/|\.codex/worktrees/|gho_[A-Za-z0-9_]+)' \
	"$contract" "$manifest" "$current" AGENTS.md README.md docs/PROJECT_BRIEF.md docs/ROADMAP.md
! grep -Fq 'owner_acceptance: accepted' "$contract" "$manifest" "$current"

bash -n bin/dcp-ao lib/dcp-ao-common.sh lib/dcp-ao-adapter.sh lib/dcp-ao-stage6-direct-install.sh \
	scripts/i51_wbc_integration_twin_stage6_final_pin_live_audit.sh tests/test_i51_stage6_final_fences.sh
tests/test_i51_stage6_final_fences.sh
git diff --check

printf 'PASS I51 Stage 6 final pin/install/live authority\n'
