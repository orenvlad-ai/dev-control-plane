# DCP real-target repository rename v1 contract

contract_status: owner-approved-pre-runtime

date: 2026-08-16

scope: one exact GitHub repository rename and one forward-only DCP target-name transition

## 1. Purpose and immutable predecessor

This contract authorizes the public GitHub repository rename
`orenvlad-ai/wb-price-extension` to
`orenvlad-ai/wb-browser-extension` and the corresponding future DCP target
transition from `wb-price-extension` to `wb-browser-extension`. The profile
remains `repo-only`, the default branch remains `main`, and the required check
remains `baseline`.

The installed predecessor is exact managed source
`f857fc652a529955a3bca4205c09961a1a80b811`, tree
`ce8d2a4af467faf7c816152d04ac8a423eeb1b3b`, with install receipt SHA-256
`2c38e353acb0a1e9a136a5ab77fcc2b2d49b970cede673d215daf092484df3dd`.
SQLite is schema version 76 with integrity `ok`, 60 terminal model actions,
zero active model actions, 40 native sessions and zero active sessions. The
only existing real-target policy task is terminal `price-arch-v1`, native
session/card `wb-price-extension-1` / 1, PR #1 and ordinary merge
`62853496837f64522bb08ba56169f60f3b0f9a2c`. Those identities and all other
historical rows are immutable evidence.

This change does not authorize a product task, product-file change, worker,
reviewer, arbiter, new card/session, feature branch, pull request or merge in
the renamed repository. The next product submit is a separate curator action
after this complete governed chain.

## 2. Exact provider rename

Before the rename, read-only proof must establish that the old repository is
public `orenvlad-ai/wb-price-extension`, is not archived, disabled, transferred
or forked, has repository numeric ID `1335072844`, node ID
`R_kgDOT5OYTA`, owner `orenvlad-ai` with numeric ID `237411244`, default branch
`main`, one successful exact-head check named `baseline`, no open pull request,
and protected `main` with strict `baseline`, admin enforcement, linear history,
resolved conversations, no force pushes and no deletion. It must also prove
that `orenvlad-ai/wb-browser-extension` does not already exist.

Only then may the executor issue one normal GitHub administrative rename with
an exact old-name guard. Immediately afterward, fresh provider facts must show:

- full name `orenvlad-ai/wb-browser-extension`;
- the same repository ID `1335072844`, node ID `R_kgDOT5OYTA` and owner ID
  `237411244`;
- public, non-archived, non-disabled, non-fork state;
- unchanged `main`, squash-only merge policy, required `baseline` check and
  branch protection;
- the old URL redirects to the renamed repository and returns the new exact
  `full_name`, without creating a second repository at the old namespace.

The old repository name must not be reused. Missing, ambiguous or conflicting
post-rename facts are a terminal stop before DCP source or runtime mutation.

## 3. New future target and legacy restore alias

The managed DCP source and control-plane adapter gain exactly one future-active
real-target tuple:

| Field | Exact future value |
| --- | --- |
| target/project/session prefix | `wb-browser-extension` |
| profile | `repo-only` |
| repository | `orenvlad-ai/wb-browser-extension` |
| fetch/push origin | `https://github.com/orenvlad-ai/wb-browser-extension.git` |
| repository / owner IDs | `1335072844` / `237411244` |
| default and PR base branch | `main` |
| required check | `baseline` |
| policy | `dcp.repo-only.happy-path/v1` |

New canonical submit accepts only:

```text
bin/dcp-ao-submit --target wb-browser-extension --profile repo-only --task-id <unique> --prompt <one-line-task>
```

Every new submit through target `wb-price-extension` fails closed before task,
native identity, worktree or model mutation. The old target is not an alias for
submit and cannot resolve to the new target.

Historical terminal rows retain their stored target, repository, project,
session, worktree and branch strings, including `price-arch-v1` /
`wb-price-extension-1` / `ao/wb-price-extension-1/root`. A closed legacy
classifier acts only as a read-only legacy restore alias and may recognize
only the complete exact terminal conjunction for
deterministic startup restore, display and evidence. It must require terminal
state `merged`, exact PR/head/review/admission/merge identity and the same
numeric provider identity now returned under the new full name. It grants no
submit, worker, reviewer, arbiter, repair, admission or merge authority and
must never register a second active provider target.

Crossed current/legacy target, project, session prefix, repository, origin,
provider full name, numeric ID, policy, branch or nonterminal state fails
closed. Repository redirects are not identity authority: every current path
must validate the provider-returned `full_name` exactly as
`orenvlad-ai/wb-browser-extension`.

## 4. Local checkout and one-way migration

The canonical target checkout may be mechanically renamed beneath the existing
lab root from `targets/wb-price-extension` to
`targets/wb-browser-extension`, and its sole origin may be updated to the new
canonical HTTPS URL. Its clean `main` must fast-forward to the exact provider
`main` before installation. No product file, commit, branch or pull request is
created by that mechanical move.

If durable current-target metadata requires a migration, it must be additive,
one-way, model-free and identity-preserving. It may add only the new future
target classification or mapping; it may not rewrite the existing terminal
policy row, session ID, card, worktree, branch, PR, ReviewRun, action,
admission, merge SHA or historical token accounting. The migration must first
pass on a copied schema-76 database and prove replay idempotence. No installed
start may occur until that copied-database proof is green.

## 5. Required model-free source proof

Fixtures must prove all of the following without a model call:

- exact new-target submit acceptance and provider/local identity checks;
- hard rejection of every new old-target submit before durable mutation;
- exact terminal legacy row restore and display without activation;
- rejection of crossed future/legacy tuples and nonterminal legacy rows;
- rejection when an old URL redirects but provider `full_name` is not the new
  canonical name, or when numeric repository/owner identity changes;
- one native identity per new task, equal replay dedupe and conflicting replay
  rejection;
- restart preservation with zero duplicate target, task, card, action, review,
  admission or merge identity;
- unchanged global three-slot action FIFO, per-head review, one repair,
  Human Gate and sole FIFO terminal merger;
- generated SQL/OpenAPI parity, serial Go tests/build/vet, frontend typecheck,
  source/package gates and applicable control-plane audits.

The change adds no second daemon, database, service, registry, queue, watcher,
poller, timer, heartbeat, credential, retry policy, merge bypass, production
surface or general repository launcher.

## 6. Sequential delivery and installed proof

Delivery is strictly ordered:

1. merge this exact-head reviewed contract with green `baseline`;
2. rename the provider repository and prove the complete post-rename identity,
   redirect and protection facts;
3. merge one ordinary managed-source PR after exact-head semantic/security
   review and successful `source` and `package` checks;
4. merge one separate reviewed immutable pin/install-guard PR;
5. prove the canonical DCP process/action contour stopped, then run deterministic
   `prepare -> build -> install -> preflight` with verified backup, receipt and
   artifact hashes;
6. if runtime startup is necessary, start only the canonical installed bundle,
   prove legacy terminal restoration and new-target readiness without a submit,
   then perform one controlled restart and stop again;
7. merge one exact-head reviewed terminal evidence PR and leave canonical
   `dev-control-plane` main clean and fast-forwarded.

The final stopped proof requires SQLite integrity `ok`, zero active model
actions/sessions/process descendants, no new real-target policy task, no
product PR, successful old-target submit rejection and model-free new-target
readiness. `dcp-review-lab` PR #24 and its Human Gate remain unchanged.

## 7. Exclusions and terminal meaning

Do not implement Manifest V3, popup, API, dependencies or other product code.
Do not touch `wb-core`, production, servers, secrets, Telegram, foreign
repositories, backups outside the canonical lab contour or historical
`dcp-review-lab` PR #24. No manual merge or protection bypass is authorized.

Technical `COMPLETE` means the renamed repository is the only future-active
real target, its exact new tuple is installed and preflight-ready, historical
terminal rows restore safely, and the old target cannot accept a future
submit. It is not owner acceptance or product completion.
