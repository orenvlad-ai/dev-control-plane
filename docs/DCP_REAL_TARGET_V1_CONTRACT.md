# DCP real repo-only target v1 contract

status: owner-authorized implementation contract

date: 2026-08-15

scope: one exact public repository target plus one bounded review-lane UI correction

## 1. Purpose and immutable predecessor

This contract authorizes the first real, reversible repository target for DCP.
It does not authorize the Chrome-extension product, a Wildberries API client,
credential storage, deployment, Release Train, a server or a real price
mutation. The resulting target changes source in one isolated repository only.

The exact installed predecessor is managed source
`bd8d67330fa369b4a18cea30d976567f8c3a5930`, tree
`4981847fbe6feaaee0383928c7c9d7f514c6361b`, receipt SHA-256
`653417573689a62cd0fb570c0bbc9e432a38e0b57af1347a93f606dd94228760`.
The read-only before snapshot has SQLite SHA-256
`301ef7cfd5717783e6245e15930da92b50c9435df550720494acc2408ff69a9a`,
integrity `ok`, 39 native sessions, 38 ReviewRuns, 58 model actions, 22 future
policy tasks and 26 admissions. Zero model action and zero native session are
active. The exact app/daemon pair discovered during preflight was gracefully
stopped after those durable checks; port 43231 and the run-file are absent.

All existing `dcp-review-lab` tasks, cards, worktrees, PRs, ReviewRuns,
admissions, arbiters and model actions remain byte-for-byte historical
authority. Card 27/PR #24 remains the unchanged terminal Human Gate with its
exact owner question. This contract adds no migration that rewrites an
existing identity or terminal fact.

## 2. Completed isolated repository bootstrap

The owner explicitly authorized one direct initial `main` commit because no PR
contour existed before it. Public repository
`orenvlad-ai/wb-price-extension` now has exact GitHub repository database id
`1335072844`, node id `R_kgDOT5OYTA`, owner database id `237411244`, default
branch `main`, bootstrap commit
`9522cfb633f9b3f5a87298f4f1dcce902bb7ebfd` and tree
`b43f500f195c7c1f64874b5a9c5bcda5e38401c3`.

That commit contains only `README.md`, repo-local `AGENTS.md`, high-level
`docs/PROJECT_BRIEF.md` and `docs/ARCHITECTURE.md`, `.gitignore`, a model-free
baseline script and one pinned GitHub Actions workflow. It contains no product
implementation, secret, environment, production endpoint, Wildberries call,
telemetry or deploy path.

Workflow run `31885027761`, job `95012975601`, completed successfully on the
exact bootstrap head. Its stable required check name is exactly `baseline`.
`main` requires that strict check, linear history and resolved conversations;
admin enforcement is enabled, force pushes and deletion are disabled, and the
only enabled merge method is squash. GitHub Actions secrets and environments
are both empty. After bootstrap, direct feature writes to `main` are forbidden.

## 3. Exact target registry

The existing daemon and SQLite authority gain one additional immutable static
target entry. This is not a caller-controlled repository launcher.

| Field | Exact value |
| --- | --- |
| target | `wb-price-extension` |
| profile | `repo-only` |
| repository | `orenvlad-ai/wb-price-extension` |
| origin | `https://github.com/orenvlad-ai/wb-price-extension.git` |
| provider | `github.com`, public repository id `1335072844` |
| owner | `orenvlad-ai`, provider owner id `237411244` |
| default/PR target branch | `main` |
| required check | `baseline` |
| terminal state | `MERGED` |

The existing `dcp-review-lab` / `synthetic-pr` entry remains exact and
unchanged. The registry contains only those two explicit tuples. Missing,
foreign, private, renamed, transferred, archived, forked, default-branch,
provider-id, remote, path, check-name, visibility or profile drift fails before
task mutation or model launch. No request field may supply a path, owner, repo,
remote, check name, branch pattern, GitHub id or policy rule.

## 4. Canonical submit and durable identity

The sole curator entry for the new target is:

```text
bin/dcp-ao-submit --target wb-price-extension --profile repo-only --task-id <unique> --prompt <one-line-task>
```

The adapter supplies the repository identity from the exact registry; the
caller does not pass or infer a repository or card number. Task ids retain the
bounded lowercase/hyphen policy and are globally unique in the existing policy
table. The canonical payload includes target, profile, repository, policy
version and prompt. Equal replay returns the same durable identity; a changed
field under the same task id is a conflict and fails closed.

One task owns exactly one stock native card/session, one worktree, one branch
and one ready PR:

- session/card: `wb-price-extension-<native-number>`;
- worktree: existing data root
  `worktrees/wb-price-extension/wb-price-extension-<native-number>`;
- branch: `ao/wb-price-extension-<native-number>/root`;
- PR: one non-draft PR from that exact branch to `main` in the exact repository.

Card allocation remains native and durable; no card number is an input,
authority or ceiling. The legacy SQLite policy table may be widened in place
for the two exact target tuples, but it remains the sole task/action registry.
Existing rows and foreign keys must survive migration and rollback tests
unchanged.

## 5. Worker isolation and repository behavior

The initial worker and the existing one-cycle findings repair may mutate only
the exact current target worktree, its exact private/common Git metadata and
its one allowed branch/PR. Network permission is granted only after target,
profile, project, provider ids, physical paths, worktree topology, branch,
fetch/push origin and policy action identity all match the registry.

The worker must not receive or discover paths for `wb-core`,
`dev-control-plane`, `dcp-orchestrator`, production, backups, unrelated
repositories or secrets. Its repo-local rules forbid extra branches,
worktrees, remotes, PRs, services and live Wildberries calls. It may use the
already configured GitHub transport only for the exact branch/ready-PR
contour. The worker never merges, reviews, deploys or applies a price change.

Reviewer behavior is unchanged: one fresh context-free exact-head reviewer,
no worker network contour, no daemon/GitHub credentials in the model, one
schema-constrained verdict and trusted result submission. Findings permit only
the existing one same-task repair and one fresh review on its new exact head.

The already installed event-driven future-card arbiter may handle a genuinely
technical exact incident for this target through the same generation, global
slot, bounded repair and Human Gate rules. It does not gain a new model loop,
retry policy or merge power. Qualification prompts are kept unambiguous; this
preparation task launches no worker, reviewer or arbiter.

## 6. Shared concurrency, admission and merge

Both exact targets share the existing `dcp_model_action` FIFO and global
three-active-slot uniqueness. Queued work, CI and admission remain durable and
model-free. Restart uses the same exact action/native identity and cannot
duplicate a call, branch, PR, review or admission.

All policy-eligible tasks from both targets share the existing single durable
FIFO terminal-merge lease. Target-aware admission revalidates the registered
repository, current `main`, exact PR/head/base/author/branch, one successful
named check, approved no-findings ReviewRun, zero unresolved conversations,
public provider identity and current CLEAN/MERGEABLE facts immediately before
claim and merge. Only the existing terminal merger performs one squash merge
and persists its provider result. No adapter, worker, reviewer or arbiter owns
SCM merge authority.

Historical `dcp-review-lab` admissions retain their exact order and identities.
A waiting task from either target cannot bypass an earlier eligible FIFO row;
an exact terminal Human Gate remains fail-closed without globally blocking a
later safe row under the already qualified rule.

## 7. I21 empty-subsection correction

The physical third board column remains `IN REVIEW / ARBITER` with its paired
header counts and all qualified color, pulse, Human Gate, failure,
board/sidebar, accessibility and reduced-motion semantics.

Its internal subsections render by visible card count:

- review `0`, arbiter `0`: render neither internal heading nor empty section;
- review `n`, arbiter `0`: render only `IN REVIEW n` and its cards;
- review `0`, arbiter `n`: render only `ARBITER n` and its cards;
- review `n`, arbiter `n`: render both, ordered `ARBITER` above `IN REVIEW`.

The paired physical-column header is never removed. No placeholder, zero
heading or empty landmark remains in the DOM/accessibility tree. This is a
renderer-only correction and changes no durable state or model authority.

## 8. Installer and model-free preflight

The immutable control-plane pin and install guard must know both exact registry
entries. Replacement remains forbidden for any claimed/running/unknown model
action, active worker/reviewer/arbiter descendant, ambiguous process, foreign
listener, submission race or unverified prior receipt.

Deterministic `prepare -> build -> install -> preflight` must verify the exact
merged source/tree, generated SQL/OpenAPI parity, source/package gates,
signature and installed artifact. The new target preflight verifies only
repository/provider/config/CLI facts and must be structurally incapable of
creating a task/card/action/branch/PR or invoking a model. The canonical app is
left stopped with no run-file, listener or model child.

## 9. Required proof and delivery order

Delivery is strictly sequential:

1. merge this reviewed control-plane contract with green baseline;
2. merge ordinary ready managed-source PR or PRs with exact-head
   semantic/security review and successful `source` and `package` checks;
3. merge one separate reviewed immutable pin/install-guard PR;
4. deterministically prepare, build, install and run model-free preflight;
5. merge one terminal evidence PR with exact PRs, heads, trees, workflows,
   receipt and stopped-state facts.

Required model-free proof includes:

- migration upgrade/rollback, foreign-key and historical-row preservation;
- exact registry acceptance for both allowed tuples and rejection of foreign,
  missing, private, transferred, renamed, wrong-id, wrong-main, wrong-check,
  wrong-profile, wrong-origin and foreign-worktree identities;
- canonical CLI argument mapping, idempotent equal replay and conflicting
  replay rejection without native creation;
- one-task/one-card/worktree/branch/PR topology and repo-only worker path and
  network isolation;
- the existing global three-slot action bound, per-head review, one repair,
  cross-target FIFO admission, exact merge and restart dedupe fixtures;
- generated SQL/OpenAPI parity, serial Go tests/build/vet, frontend typecheck,
  governed renderer suites and source/package/artifact gates;
- focused UI cases `0/0`, `n/0`, `0/n`, `n/n`, board/sidebar parity,
  accessibility and reduced motion;
- clean public bootstrap `main`, green exact `baseline`, zero secrets and no
  open feature PR;
- before/after SQLite integrity and counts proving no live DCP task or model
  call occurred during preparation.

## 10. Handoff-only future qualifications

Terminal evidence includes three ready but unsubmitted prompt sets:

1. one small real documentation/design task with no expected conflict;
2. three independent parallel scaffold tasks that remain product-safe;
3. one deliberately technical, mechanically resolvable conflict for the
   existing arbiter without requiring owner preference.

They are examples for the next curator stage, not authority to submit in this
task. No feature branch, PR, card or model action may be created from them now.

## 11. Exclusions and terminal meaning

Do not implement the Chrome extension, Wildberries price adapter, token store,
product UI, server, deployment, telemetry or live API call. Do not touch
`wb-core`, production, Telegram, Entire/Symphony, foreign PRs, historical
evidence, old backups/apps or PR #24.

The technical result of this contract is a stopped, preflight-ready DCP build
that accepts only the exact new target/profile and leaves the next live task to
the curator. Technical completion is not owner acceptance. Only the owner may
later write `Задача принята`.
