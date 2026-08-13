---
evidence_status: technical-complete
captured_at: 2026-08-13T16:56:39Z
contract_commit: 9465a84ec44f72f6b7c245ebddeac22d722108ae
installed_source_commit: 15b51450b391fdc1ae0f172bbbf95275a6388030
installed_source_tree: f819398a7e78ffa68630b62a3234e6e95283be57
finalization_status: succeeded
worker_calls: 0
arbiter_calls: 0
model_free_actions: 1
reviewer_calls: 1
reviewer_tokens: 24178
reviewed_head: 4de6ff1a0b80223a9b32a05ba68cf0b665296081
merge_commit: 5bfd20d3b3f5b7d9d9ccb02500b742a917e6ea01
---

# I13 Stage 2 card-12 REBASE_HEAD finalization success evidence

## Result

The exact owner-approved retained-candidate finalization is technically
**COMPLETE**. The earlier human-only GitHub Actions billing/spending blocker
was removed without changing task, code, branch, PR or head identity. On the
unchanged exact head `4de6ff1a0b80223a9b32a05ba68cf0b665296081`, the same
workflow run completed a real successful attempt. The already installed
inspect-only continuation then applied migration 0066, adopted the already
pushed candidate without a second action or push, launched exactly one fresh
context-free reviewer, rebound admission sequence 4 and used the existing
trusted terminal-merge gate to squash-merge PR #9 once at
`5bfd20d3b3f5b7d9d9ccb02500b742a917e6ea01`.

The durable finalization row is `succeeded`, revision 9, with trusted
worker/arbiter/action/reviewer counts `0/0/1/1`. A controlled stop/start
advanced quarantine verification from 7/7 to 8/8 while preserving one
provider-base correction, one candidate ReviewRun, one admission rebind and
one merge. It launched no worker, arbiter, reviewer or other model process.
The application was stopped again after proof; the run file and listener are
absent.

## Reviewed and merged delivery chain

| Stage | Pull request | Exact result |
| --- | --- | --- |
| Governing contract | dev-control-plane [#161](https://github.com/orenvlad-ai/dev-control-plane/pull/161) | baseline green; exact-head no-findings review; merge `9465a84ec44f72f6b7c245ebddeac22d722108ae` |
| Initial finalizer source | dcp-orchestrator [#35](https://github.com/orenvlad-ai/dcp-orchestrator/pull/35) | source/package green; semantic/security no findings; merge `6f53f74f456b869c98bb82d928f671b54672808a`, tree `0fab2ee443d8bf20a0efcc524851e8c9589e6dd9` |
| Initial pin/install guard | dev-control-plane [#162](https://github.com/orenvlad-ai/dev-control-plane/pull/162) | baseline green; no findings; merge `277b1dbc57f20125b181c09dbaa787d4858b7918` |
| Audit-query correction | dcp-orchestrator [#36](https://github.com/orenvlad-ai/dcp-orchestrator/pull/36) | source/package green; no findings; merge `e15a6d22f83876b240fa61889b6821bd49904f28`, tree `48d1266abc44de79bda0ca2865558d259325fc0d` |
| Audit-query correction pin | dev-control-plane [#163](https://github.com/orenvlad-ai/dev-control-plane/pull/163) | baseline green; no findings; merge `51473eb5a651ac041c86901599da409126e8d7d6` |
| Revision-gate correction | dcp-orchestrator [#37](https://github.com/orenvlad-ai/dcp-orchestrator/pull/37) | source/package green; no findings; merge `1f1e8cedf44d30773568f8801710f1371b14a47b`, tree `4523bfacf690c15f75c155ccfc2f14831db7b2f2` |
| Revision-gate correction pin | dev-control-plane [#164](https://github.com/orenvlad-ai/dev-control-plane/pull/164) | final baseline green; no findings; merge `3e0f1e90116a5cc801dfa05758b4f17bb246fd22` |
| Inspect-only provider-base correction | dcp-orchestrator [#38](https://github.com/orenvlad-ai/dcp-orchestrator/pull/38) | source/package green; no findings; merge `15b51450b391fdc1ae0f172bbbf95275a6388030`, tree `f819398a7e78ffa68630b62a3234e6e95283be57` |
| Provider-base correction pin | dev-control-plane [#165](https://github.com/orenvlad-ai/dev-control-plane/pull/165) | baseline green; no findings; merge `ca7c28b62f787ec283af4eee6fe66801197004d1` |
| Blocked-state evidence | dev-control-plane [#166](https://github.com/orenvlad-ai/dev-control-plane/pull/166) | baseline green; no findings; merge `c660465ccf92aaa486a027dabd8044b39b007e75` |

The blocked-state evidence remains immutable historical proof of the safe stop.
This success evidence records only the explicitly owner-directed continuation
after the external prerequisite changed.

## Installed source and stopped preflight

The exact final source/tree `15b51450...` / `f819398...` was already
deterministically installed at `2026-08-13T16:25:14Z`. Full provenance/source
gates, serial Go tests/build, renderer typecheck, 15 files / 348 renderer tests,
native arm64 package and installed-artifact preflight passed. The final receipt
SHA-256 is
`b362851fb43d772a7cbd1d1a85ebeaa6980f78a5e1b96d87f6ae74bb2b5eb0dc`,
daemon SHA-256 is
`a53c4f2ad38ff2303ee5437c3fa83af80931add00443804ef58a7d6f192b62d2`
and ASAR SHA-256 is
`a1206d002b16a8d9a3cb4485c4522b4fe685fdb102840d1d96530a4f11a4ff90`.

The final integration backup before that install was
`i12-20260813T162514Z`; its prior receipt SHA-256 was
`ea65c53c997ea78dd3d8ab9e2582658426c3f3bdc2c6a211f008c9e1873dea69`.
The earlier exact install backups/receipts remain the immutable sequence named
in the blocked evidence.

Before continuation, the app/daemon were stopped with no run file or listener.
Goose version was 65; migration 0066 and its recovery table were absent. The
finalizer remained `failed/provider_identity_drift`, revision 4, at `0/0/1/0`;
the cold-start predecessor remained terminal revision 7 at `0/0/1/0`.
Quarantine was 6/6, admission sequence 4 remained the old incident and there
was no ReviewRun or GitHub review on the candidate. Both governed panes were
bare `zsh` shells with zero descendants.

## External check recovery and public-history proof

The repository visibility changed from private to public only after a bounded
curator review; task/code identity did not change. The executor independently
verified `PUBLIC` visibility, 18 reachable commits, only the bounded canary,
workflow and README-era paths, and zero reachable-commit matches for AWS,
GitHub, OpenAI, Slack or private-key credential patterns.

The same GitHub Actions run
[31718637023](https://github.com/orenvlad-ai/dcp-review-lab/actions/runs/31718637023)
ran attempt 3 on unchanged candidate `4de6ff1a...`. Job `94521518361` executed
`actions/checkout@v4` and `test -f README.md`, completed all steps and returned
`SUCCESS` in seven seconds. The prior two zero-step billing failures remain
historical attempts of the same run. No commit, rebase, push, worker, arbiter,
reviewer or model call was used to remove the blocker.

Immediately before runtime start, PR #9 was exact OPEN/non-draft,
MERGEABLE/CLEAN with head `4de6ff1a...`, base/current main `b34b31b...` and the
single current named check successful. GitHub and SQLite still contained no
candidate review verdict.

## Exact Git, pseudoref and backup identity

The same session `dcp-review-lab-12`, task `i13-arbiter-b`, worktree, branch
`ao/dcp-review-lab-12/root`, PR #9, incident and admission sequence 4 were used.
Candidate `4de6ff1a...` remained clean with parent `b34b31b...`, exact original
subject/author/date and sole diff `M canary/i13-arbiter-conflict.txt`. The file
SHA-256 remained
`2a5da25a78ff8bcd9aff4493f195eaefecbc70c3d4db8902dda468ccf69e5e46`.

Regular `REBASE_HEAD` and `ORIG_HEAD` still contain exact old head
`d4fcb68051ae113ed497d02151a759800ee85633` plus LF and share SHA-256
`657c15026f6e8f51e96e6ff6c2ae94a5d6f4031ec95f07030b52f6226cc4d810`.
No rebase directory, sequencer, merge/cherry-pick/revert/bisect state or extra
worktree change exists. The sealed backup manifest remains exact at
`82d0e5834375c380069e7d48a7fdb2066371670d92733ce59545718469a4f3dd`.
No continuation step wrote, reset, rebased, amended or pushed the repository.

## Inspect-only adoption and one review

The single live continuation start applied migration 0066. Its immutable
provider-base recovery row recorded the prior revision-4 failure/action count,
historical base `dbaf01b...`, post-push base `b34b31b...`, first failed check
`94509683728` and quarantine evidence. It re-armed only revision 5 with action
count already one. The running path used `InspectCompleted`; it could not
re-enter the finalization action or push path.

Fresh provider/Git proof adopted exact candidate `4de6ff1a...` and launched
one reviewer:

- ReviewRun `efa36083-3efd-497f-90b7-db7e7fbf04d2`;
- batch `a233b681-3197-497b-b258-d94d7c10be44`;
- reviewer terminal `review-dcp-review-lab-12`;
- Codex session `019ffc0a-2409-7c03-9e6c-a0c3f580ad93`;
- `gpt-5.6-sol`, reasoning effort `none`, 24,178 reported tokens;
- schema-bound `approved` verdict, empty findings, exact PR/head identities;
- structured channel `structured_dcp_v1`.

The old-head verdict and old successful check were not reused. The current
check id persisted on the finalization row is `94521518361`. The review process
exited successfully and its terminal became a bare shell.

## Admission rebind and terminal merge

After the structured approval, named green check, no findings/threads and fresh
MERGEABLE/CLEAN facts, the trusted daemon rebound only admission sequence 4:

- target head `4de6ff1a...`;
- review/admitted base `b34b31b...`;
- ReviewRun `efa36083...`;
- status `succeeded`, refresh wake count 0;
- merge commit `5bfd20d3b3f5b7d9d9ccb02500b742a917e6ea01`.

GitHub records PR #9 MERGED once at `2026-08-13T16:53:11Z`. The squash commit
has parent `b34b31b...`, tree `c55e698957bde0261498915e7da5a8710ba05d25`
and modifies only `canary/i13-arbiter-conflict.txt` to blob
`80a658c4cfc3ffda5786da316bc0bd10ffb1834f`. Remote main now points exactly to
`5bfd20d3...`; the remote PR branch remains exact reviewed candidate
`4de6ff1a...`.

## Controlled restart and final stopped state

The app was cleanly stopped after success. At the stopped boundary the row was
`succeeded` revision 9 at `0/0/1/1`, quarantine was 7/7, provider recovery
rows=1, candidate ReviewRuns=1 and succeeded sequence-4 admissions=1.

One controlled restart advanced only quarantine to 8/8. All finalization,
review, admission, check and merge identities/timestamps/counts remained
unchanged. Cards 11/12 and the completed reviewer terminal were bare shells
with zero descendants; no Codex reviewer, worker or arbiter process launched.
The app was then stopped again. The final run file/listener are absent, goose
is 66, SQLite WAL is empty and stopped database SHA-256 is
`caef8e77f6e7102025ba596957a971f80e6e20891a4c22c7f2a49243d83ab5b6`.

## Complete model and token accounting

| Contour | Actual calls | Exact reported tokens | Additional bounded tokens |
| --- | ---: | ---: | ---: |
| Stage 2 before this reviewer | 9 exact-usage calls | 199,596 | 16,384 maximum for one separate failed fresh-worker call |
| This finalization worker calls | 0 | 0 | 0 |
| This finalization arbiter calls | 0 | 0 | 0 |
| This finalization reviewer | 1 | 24,178 | 0 |
| **Aggregate after completion** | **10 exact-usage calls plus 1 bounded failed call** | **223,774** | **16,384 maximum** |

Thus the truthful Stage 2 aggregate is eleven actual calls: ten calls with
exactly reported usage totaling 223,774 tokens, plus the earlier failed worker
call whose only proven usage bound is 16,384. The full ceiling is 240,158
tokens. The prior unauthorized card-11/card-12 restoration calls remain inside
the exact total at 33,238 and 33,573 tokens, respectively, for immutable
subtotal 66,811. This continuation introduced no worker/arbiter call and no
second reviewer.

## Scope closure and residual risks

- PR #9 is merged and no further runtime continuation is authorized or needed.
- The repository remains public after the bounded history proof. That
  visibility is an explicit operational fact, not a general authority to use
  other repositories or expose future content.
- The regular pseudorefs remain as exact inert evidence; no cleanup authority
  was inferred.
- No second action, push, check rerun, reviewer, worker, arbiter, admission,
  merge, replacement identity or manual bypass occurred.
- Production, `wb-core`, secrets, Telegram, foreign PRs and owner acceptance
  remain out of scope. Technical completion is not owner acceptance.
