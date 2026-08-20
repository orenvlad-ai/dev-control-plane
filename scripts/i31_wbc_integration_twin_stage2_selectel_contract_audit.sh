#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
cd "$REPO_ROOT"

contract=docs/DCP_WBC_INTEGRATION_TWIN_STAGE2_SELECTEL_PERSISTENT_CELL_CONTRACT.md
architecture=docs/DCP_WBC_INTEGRATION_TWIN_DCP_V2_ARCHITECTURE_CONTRACT.md
current=docs/CURRENT_OPERATING_CONTRACT.md

for path in "$contract" "$architecture" "$current" AGENTS.md docs/PROJECT_BRIEF.md docs/ROADMAP.md docs/DECISIONS.md; do
	[[ -s "$path" ]]
done

for needle in \
	'contract_status: owner-authorized Stage 2 destination and execution authority' \
	'program_stage: 2 of 9' \
	'repository: `orenvlad-ai/dcp-wbc-integration-lab`' \
	'environment: `dcp-wbc-integration-lab-selectel`' \
	'service: `dcp-wbc-integration-lab`' \
	'new_paid_resources: 0' \
	'771c31e1970c4cf7a836c07f398661ce' \
	'96be74db-785f-4653-85a8-a4e7c1d3ccdf' \
	'178.72.152.177' \
	'192.168.0.161' \
	'`/opt/dcp-wbc-integration-lab`' \
	'`127.0.0.1:18321`'; do
	grep -Fq "$needle" "$contract"
done

for class in LUCHIKI_DOBRA LEGACY_WBC SHARED_SYSTEM UNKNOWN; do
	grep -Fq "$class" "$contract"
done

for protected in \
	'/opt/luchiki-landing' \
	'luchiki-counter.service' \
	'luchiki-counter.timer' \
	'/etc/nginx/sites-available/luchiki-landing' \
	'/etc/letsencrypt/live/xn----8sbclsang6avz2c.xn--p1ai' \
	'HTTP 200' \
	'pre-existing `luchiki-counter.service` exit-code failure' \
	'.counter.*.tmp'; do
	grep -Fq "$protected" "$contract"
done

for legacy in \
	'/opt/wb-core-runtime' \
	'/opt/wb-ai' \
	'/opt/wb-ai-repo' \
	'/opt/wb-web-bot' \
	'wb-ai-api.service' \
	'wb-core-registry-http.service' \
	'wb-core-sheet-vitrina-closure-retry.*' \
	'wb-core-sheet-vitrina-refresh.*' \
	'wb_ai_postgres' \
	'wb-ai_pgdata' \
	'/opt/wb-core-runtime/state/promo_xlsx_collector_runs' \
	'35,050,256,255'; do
	grep -Fq "$legacy" "$contract"
done

grep -Fq 'No broad path, glob or unresolved variable may be a destructive' "$contract"
grep -Fq 'repeat the protected guard' "$contract"
grep -Fq 'create no VM, disk, load balancer, floating IP' "$contract"
grep -Fq '`CPUQuota=50%`' "$contract"
grep -Fq '`MemoryMax=512M`' "$contract"
grep -Fq '`TasksMax=64`' "$contract"
grep -Fq 'at most two versioned release artifacts' "$contract"
grep -Fq '`DCP_WBC_LAB_SSH_KEY`' "$contract"
grep -Fq '`DCP_WBC_LAB_KNOWN_HOSTS`' "$contract"
grep -Fq 'forced deploy command' "$contract"
grep -Fq 'no PTY, no agent/X11/TCP forwarding' "$contract"
grep -Fq 'sole empty-repository exception' "$contract"
grep -Fq 'sole qualification issuer as actor' "$contract"
grep -Fq 'DCP issuer is absent/off' "$contract"
grep -Fq 'Both issuers are never active together' "$contract"
grep -Fq 'no second queue' "$contract"
grep -Fq 'never auto-syncs, rebases' "$contract"
grep -Fq 'immutable `readmission_required`' "$contract"
grep -Fq 'Merge without verified deployment is nonterminal' "$contract"
grep -Fq 'retained for exactly 90 days' "$contract"
grep -Fq 'ready PR -> exact-head baseline -> exact-head semantic/security review' "$contract"
grep -Fq 'It is not a DCP Task,' "$contract"
grep -Fq 'Technical completion is not owner acceptance' "$contract"

for authority in AGENTS.md "$current" docs/PROJECT_BRIEF.md docs/ROADMAP.md docs/DECISIONS.md; do
	grep -Fq 'DCP_WBC_INTEGRATION_TWIN_STAGE2_SELECTEL_PERSISTENT_CELL_CONTRACT.md' "$authority"
done

grep -Fq 'operating_contract_revision: 2026-08-20.8' "$current"
grep -Fq 'No server write or lab-repository creation' AGENTS.md
grep -Fq 'one real PR-to-persistent-deploy smoke' "$current"
grep -Fq 'authority PR must merge before' docs/ROADMAP.md
grep -Fq 'qualification-only PR-to-persistent-deploy proof' docs/PROJECT_BRIEF.md
grep -Fq 'select the Stage 2 Selectel persistent lab cell' docs/DECISIONS.md

grep -Fq 'owner-approved architecture-only; not runtime authority' "$architecture"
grep -Fq 'Stage 2 creates any repository or destination' "$architecture"
grep -Fq 'both issuers are never active together' "$architecture"
grep -Fq 'The first DCP submit occurs only in Stage 6' "$architecture"

! grep -Eq '(/Users/|/home/|\.codex/worktrees/)' "$contract"
bash -n scripts/i31_wbc_integration_twin_stage2_selectel_contract_audit.sh
git diff --check
printf 'PASS I31 Stage 2 Selectel persistent-cell contract audit\n'
