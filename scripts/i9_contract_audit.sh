#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
cd "$REPO_ROOT"

target=docs/TARGET_ARCHITECTURE_V1.md
[[ -s "$target" ]]

grep -Fq 'contract_status: target-design-only' "$target"
grep -Fq 'The current operating contour is the packaged I12/I13' "$target"
grep -Fq 'daemon and its existing SQLite are the only local' "$target"
grep -Fq 'GitHub is authoritative for repository refs, pull requests, checks, merge' "$target"
grep -Fq 'Three consecutive complete reviewer cycles are allowed' "$target"
grep -Fq 'READY_FOR_ADMISSION' "$target"
grep -Fq 'WAITING_GLOBAL_RELEASE' "$target"
grep -Fq 'release:ready' "$target"
grep -Fq 'Sol, `xhigh`' "$target"
grep -Fq 'HumanGate is allowed only' "$target"
grep -Fq 'Desktop release loop' "$target"
grep -Fq 'DCP v1 architecture, authority/transition/event contracts' "$target"
grep -Fq 'Telegram' "$target"
grep -Fq 'Symphony is provenance, not a dependency' "$target"
grep -Fq 'HistoryProvider' "$target"
grep -Fq 'provider=none' "$target"
grep -Fq 'I9 does not install, invoke, contact or test Entire' "$target"

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

for paper_case in \
	'Normal success' \
	'Reviewer reject' \
	'Three-cycle escalation' \
	'Two conflicting PRs' \
	'Head change' \
	'Release halt' \
	'Lost executor' \
	'DCP restart' \
	'HumanGate' \
	'Concurrent tasks' \
	'Desktop rollback' \
	'History provider absent' \
	'History provider failure'; do
	grep -Fq "| $paper_case |" "$target"
done

grep -Fq '[DCP v1 target architecture](TARGET_ARCHITECTURE_V1.md)' docs/CURRENT_OPERATING_CONTRACT.md
grep -Fq 'current approved source stage is I13 Stage 2 source integration' docs/CURRENT_OPERATING_CONTRACT.md
grep -Fq 'design-only and is not part of the current operating flow' docs/CURRENT_OPERATING_CONTRACT.md
grep -Fq 'I9 DCP v1 target architecture contract' docs/ROADMAP.md
grep -Fq 'Remaining target-contract implementation — not approved by I9-I12' docs/ROADMAP.md
grep -Fq 'record the DCP v1 target contract without activating it in I9' docs/DECISIONS.md
grep -Fq 'I9 target design, not current runtime' docs/PROJECT_BRIEF.md

stage2=docs/I13_STAGE2_ARBITER_V1_CONTRACT.md
[[ -s "$stage2" ]]
grep -Fq 'contract_status: owner-approved-pre-runtime' "$stage2"
grep -Fq 'dcp.review-lab.global-release-incident/v1' "$stage2"
grep -Fq 'dcp.review-lab.global-release-arbiter-input/v1' "$stage2"
grep -Fq 'dcp.review-lab.global-release-arbiter-decision/v1' "$stage2"
grep -Fq 'gpt-5.6-sol' "$stage2"
grep -Fq '16,384 tokens' "$stage2"
grep -Fq 'same_worker_conflict_repair' "$stage2"
grep -Fq 'Total model calls | 7' "$stage2"
grep -Fq 'The expected resolvable canary result is not `safe_stop`' "$stage2"
grep -Fq '[I13 Stage 2 global release arbiter v1](I13_STAGE2_ARBITER_V1_CONTRACT.md)' docs/CURRENT_OPERATING_CONTRACT.md

git diff --check
printf 'PASS I9 target-contract documentation audit\n'
