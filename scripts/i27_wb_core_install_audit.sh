#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
cd "$REPO_ROOT"
# shellcheck source=../upstream/dcp-orchestrator.lock
source upstream/dcp-orchestrator.lock

contract=docs/DCP_WB_CORE_RELEASE_TRAIN_HANDOFF_V1_CONTRACT.md
current=docs/CURRENT_OPERATING_CONTRACT.md
adapter=lib/dcp-ao-adapter.sh

for path in \
	"$contract" "$current" upstream/dcp-orchestrator.lock \
	bin/dcp-ao bin/dcp-ao-submit lib/dcp-ao-common.sh "$adapter" \
	tests/test_i27_wb_core_adapter.sh; do
	[[ -s "$path" ]]
done

[[ "$DCP_AO_FORK_PR_URL" == https://github.com/orenvlad-ai/dcp-orchestrator/pull/62 ]]
[[ "$DCP_AO_FORK_COMMIT" == 99e8243ac66bfdd7e77538368403d0a3b5964c21 ]]
[[ "$DCP_AO_FORK_TREE" == 81b391c80eef98c5723340a1da8e42a3da1bbaec ]]
[[ "$DCP_AO_PRIOR_FORK_COMMIT" == d152afae2bcbcc3d2b1874adf2e6855bebcf00fb ]]
[[ "$DCP_AO_PRIOR_FORK_TREE" == aa7a6f486cf89ec299763ebcde7a5fc35a59214f ]]

grep -Fq 'orenvlad-ai/wb-core|false|main|1201929580|237411244' "$adapter"
grep -Fq 'dcp.wb-core.repo-only.release-train/v1' "$adapter"
grep -Fq 'wb-core.dcp-release-handoff/v1' "$adapter"
grep -Fq 'dcp_ao_require_wb_core_compatibility "$target"' "$adapter"
grep -Fq 'dcp_ao_prepare_wb_core_project' "$adapter"
grep -Fq '"$cli" dcp submit --target wb-core --profile repo-only' "$adapter"
grep -Fq -- '--repository orenvlad-ai/wb-core' "$adapter"
grep -Fq 'release_waiting' "$adapter"
grep -Fq 'WBC Release Train is the sole merge and release actor' "$adapter"
grep -Fq 'python3 -c' "$adapter"
! grep -Fq 'python3 -m py_compile "$target/apps/github_release_train.py"' "$adapter"

grep -Fq 'dcp_ao_validate_wb_core_target "$lab_root" 0' lib/dcp-ao-common.sh
grep -Fq 'wb_core_compatibility=%s' lib/dcp-ao-common.sh
grep -Fq 'init-wb-core' bin/dcp-ao
grep -Fq 'register-wb-core' bin/dcp-ao
grep -Fq 'The target `wb-core` remains' "$current"
grep -Fq 'compatibility-locked' "$current"
grep -Fq '99e8243ac66bfdd7e77538368403d0a3b5964c21' AGENTS.md "$current" docs/DECISIONS.md docs/PROJECT_BRIEF.md docs/ROADMAP.md

bash -n scripts/i27_wb_core_install_audit.sh tests/test_i27_wb_core_adapter.sh \
	bin/dcp-ao bin/dcp-ao-submit lib/dcp-ao-common.sh "$adapter"
tests/test_i27_wb_core_adapter.sh
git diff --check
printf 'PASS I27 wb-core immutable pin/install audit\n'
