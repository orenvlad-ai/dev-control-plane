#!/usr/bin/env bash
set -euo pipefail
trap 'printf "I52 audit failed at line %s\n" "$LINENO" >&2' ERR

evidence=docs/DCP_WBC_INTEGRATION_TWIN_STAGE6_FINAL_FREEZE_BLOCKED_EVIDENCE.md
manifest=docs/DCP_WBC_INTEGRATION_TWIN_CURRENT_PROGRAM_MANIFEST.md
current=docs/CURRENT_OPERATING_CONTRACT.md
contract=docs/DCP_WBC_INTEGRATION_TWIN_STAGE6_FINAL_PIN_INSTALL_LIVE_CONTRACT.md

for path in "$evidence" "$manifest" "$current" "$contract" AGENTS.md README.md \
	docs/PROJECT_BRIEF.md docs/ROADMAP.md docs/DECISIONS.md; do
	[[ -s "$path" ]]
done

grep -Fxq 'evidence_revision: 2026-08-23.1' "$evidence"
grep -Fxq 'technical_status: FINAL FREEZE/BLOCKED after the single adoption transaction applied but its reviewed gateway response validation failed' "$evidence"
grep -Fxq 'owner_acceptance: not requested or synthesized' "$evidence"

for exact in \
	'`01a02a5c-2dab-7f60-97af-d980cb92fbe5`' \
	'`DCP · S6 final pass · И35`' \
	'`d10a9791392e19510590c3fb4a3d231fe980ecf6`' \
	'`acd93511dd1c77dd2508734bf0b8d331594115cf`' \
	'`a53687edf44bd72d10495993993f292a6e21720d`' \
	'`32592786360`' \
	'`5000857575`' \
	'`9183c6207908de6f638360b86b8f6e1393d7fc8f0d169e10ac8e0b9dd97421ca`' \
	'`a8a2828f76ae21939ec6de6ee3d88d7e9269a01653e57f98477a9efe3f2e0ba0`' \
	'`f1c40b0255b0300b06a2701d3548f07d84fb5d2a3b96e46038d270eea61fe745`' \
	'`83f21a2d7af5649cbedf9e92e02a3b268fff26b996787440e33334e4f3172ebc`' \
	'`v2-0e1aadfb444bc4d9f4c90c8bf936a0ebec125300`' \
	'`v2-06b20be020812369bf4286fd335aa8f5281d15e2`' \
	'`bebbf8f617f1a6fa0b9e91698fe710fe0a2bad2c`' \
	'`2fda4cae71976fd701bf3a9ccca4031f7afb630d`' \
	'`1/2/2/1`' \
	'`1/1/1`' \
	'`adoption_status=failed-or-ambiguous`' \
	'zero provider effect' \
	'No second adoption was attempted' \
	'Stage 6 is `FINAL FREEZE/BLOCKED`' \
	'Do not' \
	'synthesize owner acceptance.'; do
	grep -Fq "$exact" "$evidence"
done

for key in TaskID RevisionID CommandID ActionID RuntimeID NativeActionID CommitSHA TreeSHA ConsumedAt; do
	grep -Fq "\`$key\`" "$evidence"
done
for key in taskId revisionId commandId actionId runtimeId nativeActionId commitSha treeSha consumedAt; do
	grep -Fq "\`$key\`" "$evidence"
done

grep -Fxq 'manifest_revision: 2026-08-23.1' "$manifest"
grep -Fxq 'program_status: Stage 6 FINAL FREEZE/BLOCKED; schema 87 stopped after one adoption transaction applied but gateway receipt validation failed; zero provider effect' "$manifest"
grep -Fxq 'operating_contract_revision: 2026-08-23.1' "$current"
grep -Eq '^\| 6 \| FINAL FREEZE/BLOCKED \|' "$manifest"
for stage in 7 8 9; do grep -Eq "^\| ${stage} \| NOT STARTED" "$manifest"; done

for path in AGENTS.md README.md "$manifest" "$current" docs/PROJECT_BRIEF.md docs/ROADMAP.md docs/DECISIONS.md; do
	grep -Fq 'DCP_WBC_INTEGRATION_TWIN_STAGE6_FINAL_FREEZE_BLOCKED_EVIDENCE.md' "$path"
done

grep -Fq 'A false, failed or ambiguous response ends `FREEZE/BLOCKED`; the' "$contract"
grep -Fq 'attempt marker forbids replay even if later readback looks equal' "$contract"
grep -Fq 'Stage 7 remains not started' AGENTS.md
grep -Fq 'Stage 7 was not started and is ineligible under the final freeze' docs/PROJECT_BRIEF.md

! grep -Eq '(/Users/|/home/|\.codex/worktrees/|gho_[A-Za-z0-9_]+|BEGIN (RSA|OPENSSH|EC|PRIVATE))' \
	"$evidence" "$manifest" "$current" AGENTS.md README.md docs/PROJECT_BRIEF.md docs/ROADMAP.md
! grep -Fq 'owner_acceptance: accepted' "$evidence" "$manifest" "$current"

bash -n scripts/i52_wbc_integration_twin_stage6_final_freeze_audit.sh
git diff --check
printf 'PASS I52 Stage 6 final freeze blocked evidence\n'
