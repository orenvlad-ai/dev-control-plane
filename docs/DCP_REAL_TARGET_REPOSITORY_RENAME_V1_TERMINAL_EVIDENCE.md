# DCP real-target repository rename v1 terminal evidence

evidence_status: COMPLETE

date: 2026-08-16

scope: exact provider rename and forward-only repo-only target transition

## 1. Terminal outcome

The public repository is now exact
`orenvlad-ai/wb-browser-extension`. Repository id `1335072844`, node id
`R_kgDOT5OYTA` and owner id `237411244` are unchanged. The only future-active
real-target tuple installed in DCP is:

- target `wb-browser-extension`;
- profile `repo-only`;
- repository `orenvlad-ai/wb-browser-extension`;
- public default branch `main`;
- required check `baseline`.

The former target name `wb-price-extension` is absent from the active target
allowlist and a canonical submit through it fails before daemon or SQLite
mutation. It survives only inside one closed terminal-restore predicate and
one immutable forward-mapping audit row. This maintenance created no product
task, card, session, model action, branch, product PR or merge.

## 2. Provider identity before and after

Immediately before the rename, the repository was exact public
`orenvlad-ai/wb-price-extension`, repository id `1335072844`, node id
`R_kgDOT5OYTA`, owner id `237411244`, default branch `main`, squash-only merge
policy and protected required check `baseline`. No repository existed at the
new name.

Immediately after the guarded administrative rename and again at terminal
proof:

- `GET /repos/orenvlad-ai/wb-browser-extension` returns full name
  `orenvlad-ai/wb-browser-extension` and the unchanged numeric/node identities;
- the repository remains public, enabled, unarchived, non-fork, `main` and
  squash-only;
- `main` remains exact
  `62853496837f64522bb08ba56169f60f3b0f9a2c`;
- successful `baseline` workflow run `31901256556` remains bound to that head;
- protection remains strict required `baseline`, enforce-admins, linear
  history and conversation resolution, with force-pushes and deletion denied;
- the repository has no repository rulesets beyond that branch-protection
  authority and has zero open pull requests;
- the former web URL returns HTTP 301 to the new URL; querying the former API
  namespace resolves repository id `1335072844` with returned full name
  `orenvlad-ai/wb-browser-extension`, proving it is a redirect and not a second
  repository.

Historical PR #1 remains closed/merged with head
`afc748eba5ff05c0dc24d3002c690ec9f44984fb`, base
`9522cfb633f9b3f5a87298f4f1dcce902bb7ebfd` and merge commit
`62853496837f64522bb08ba56169f60f3b0f9a2c`.

## 3. Reviewed delivery chain

Every mutation boundary used an ordinary exact-head reviewed pull request and
required workflow; no manual merge or protection bypass occurred.

| Boundary | Exact head | Exact-head review and workflow | Ordinary merge |
| --- | --- | --- | --- |
| contract PR [#212](https://github.com/orenvlad-ai/dev-control-plane/pull/212) | `fc08c9d56e006c95be741aae146bcfeb91b23c8c` | `PRR_kwDOSUqHmc8AAAABJsjUwA`; `31933422695` | `a1bfdd9328566dc630587220b60b7faa7ba1d745` |
| managed-source PR [#61](https://github.com/orenvlad-ai/dcp-orchestrator/pull/61) | `05530e0a45ac630dd87dc9e5a6c4712d3305b3d7` | `PRR_kwDOTydt6M8AAAABJskmTw`; source/package `31934075873` | source `d152afae2bcbcc3d2b1874adf2e6855bebcf00fb`, tree `aa7a6f486cf89ec299763ebcde7a5fc35a59214f` |
| pin/install-guard PR [#213](https://github.com/orenvlad-ai/dev-control-plane/pull/213) | `139a6956aec05ee141ba9046aaf5377333bfc89d` | `PRR_kwDOSUqHmc8AAAABJsl5mg`; baseline `31934670646` | `6d5ec91880894a22b9ad5d96918a4c8488d1e053` |
| exact legacy-worktree guard PR [#214](https://github.com/orenvlad-ai/dev-control-plane/pull/214) | `ebfae9742d16fde7aa87d91f89f2dc917765f011` | `PRR_kwDOSUqHmc8AAAABJsmnAQ`; baseline `31934854087` | `19de6d75f947ee960db30297bf93e2dc98f7b8bb` |

The final adapter guard was found during a stopped pre-install rehearsal. It
accepts the old local linked-worktree path only when the complete immutable
terminal task/session/PR/review/admission/merge conjunction matches. A
nonterminal or crossed legacy row fails closed.

## 4. Source, checkout and deterministic install

The canonical managed source is exact commit
`d152afae2bcbcc3d2b1874adf2e6855bebcf00fb`, tree
`aa7a6f486cf89ec299763ebcde7a5fc35a59214f`. The full source gate, serial Go
suite, generated-source verification, frontend typecheck, 356 frontend tests,
package build and model-free identity fixtures passed.

Before canonical database mutation, the receipt-bound exact-source live-copy
test passed against the stopped schema-76 database. It applied migration 0077
on a copy, produced schema 77 and exactly one forward mapping, preserved all
authority counts and the full historical terminal identity, and passed
startup quarantine/restart checks.

The stopped canonical checkout moved mechanically from
`targets/wb-price-extension` to `targets/wb-browser-extension`; its sole origin
became the exact new HTTPS URL and clean `main` fast-forwarded to
`62853496837f64522bb08ba56169f60f3b0f9a2c`. The existing linked worktree stayed
at `data/worktrees/wb-price-extension/wb-price-extension-1`, clean at head
`afc748eba5ff05c0dc24d3002c690ec9f44984fb` on branch
`ao/wb-price-extension-1/root`, with its repaired common Git directory pointing
to the renamed canonical checkout. The stopped SQLite digest was unchanged by
this filesystem move.

Deterministic `prepare -> build -> install -> preflight` created backup
`i12-20260816T080249Z`. The installed proof is:

- receipt SHA-256
  `bc49040398a05c6127b140cd10f3828db178bc410f1b722f887ae7d63b79438b`;
- daemon SHA-256
  `0bb9c4972ceade6f96d743e75c6051a23c55bc7686c15b0c2e23878467fc5119`;
- app.asar SHA-256
  `9e4388d9f23364c6cd626c2b16e2b5f3de469986c3ff743120d5886ba4fa8404`;
- installed source/tree exactly `d152afae...` / `aa7a6f48...`.

## 5. Migration, restoration and readiness

The first controlled installed start applied migration 0077 exactly once.
SQLite then contained one immutable mapping:

`wb-price-extension` / `orenvlad-ai/wb-price-extension` ->
`wb-browser-extension` / `orenvlad-ai/wb-browser-extension`, profile
`repo-only`, repository id `1335072844`, owner id `237411244`.

The historical row remained byte-for-byte in its legacy identity fields:

- task `price-arch-v1`, session `wb-price-extension-1`, state `merged`,
  revision 7;
- PR #1/head `afc748eba5ff05c0dc24d3002c690ec9f44984fb`;
- ReviewRun `b0acfb9e-600c-4816-bb2f-02a67817ea05`;
- admission `dcp-admission-b0acfb9e-600c-4816-bb2f-02a67817ea05`;
- merge `62853496837f64522bb08ba56169f60f3b0f9a2c`.

The canonical native project `wb-browser-extension` was registered once,
model-free, at the new checkout with exact repository URL, `main`, session
prefix `wb-browser-extension`, one Codex worker and one Codex reviewer. The
legacy `wb-price-extension` project remains one read-only restoration object,
not a future target.

An installed old-target submit returned the exact allowlist rejection. Before
and after counts were identical: 23 policy tasks, 60 model actions, 40
sessions, five projects and 27 admissions; rejected task `i25-reject` was not
created. No `wb-browser-extension` policy task exists, and reserved next-stage
task id `mv3-shell-v1` is absent.

After controlled restart, idempotent project preparation preserved exactly
23 policy tasks, 60 actions, 39 ReviewRuns, 27 admissions, 40 sessions, five
projects and one forward mapping. There is one new project, one legacy project,
zero active actions and zero duplicate identity.

## 6. Final stopped proof

After the final graceful stop:

- SQLite integrity is `ok`, schema is 77 and SHA-256 is
  `0261e46f39eda1b3507ab0c7c6997b91e52ae9e2cc1d055a8c57d872f9f608e1`;
- counts remain 23 policy tasks, 60 actions, 39 ReviewRuns, 27 admissions, 40
  sessions, five projects and one forward mapping;
- claimed/running model actions, active native sessions, new-target tasks and
  `mv3-shell-v1` rows are all zero;
- 30 retained terminal panes have zero immediate process descendants;
- the exact app process, daemon/run-file, port 43231 listener and SQLite
  WAL/SHM sidecars are absent;
- final stopped `bin/dcp-ao preflight` passes against the exact receipt and new
  repo-only checkout.

No product repository content was changed by this executor. `wb-core`,
production, servers, secrets, Telegram, foreign repositories and historical
`dcp-review-lab` PR #24 were not touched. The next product task remains a
separate curator responsibility after this evidence merges.

## 7. Difficulties and residual risks

The canonical runtime was unexpectedly ready during initial read-only proof;
its exact app/daemon pair and zero-active contour were proven before a graceful
stop. The managed-source fetch was slow but continuously progressing and was
allowed to finish without a duplicate prepare. The stopped checkout rehearsal
correctly exposed the linked-worktree common-Git-dir boundary before canonical
mutation, so the narrow reviewed guard was added before install.

The locked dependency install reports the existing upstream npm audit and Node
engine warnings. No dependency was changed or auto-fixed. GitHub will continue
to redirect historical URLs; every active provider check nevertheless requires
the returned full name to equal `orenvlad-ai/wb-browser-extension`, so a
redirect cannot reactivate the former target.
