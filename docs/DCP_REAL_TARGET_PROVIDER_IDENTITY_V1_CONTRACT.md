# DCP real-target runtime provider identity v1 contract

contract_status: owner-approved-pre-runtime

date: 2026-08-15

scope: one model-free daemon runtime provider lookup correction

## 1. Proven predecessor and blocker

The installed predecessor is exact managed source
`f94b0603916c410419654ca4752ffa9084116ff8`, tree
`11a9856ea2504ef923221a97064a59a762a99ed8`, with install receipt SHA-256
`06ebdbf6c418ed3805ff85737a638cf9e78cf5f70a1b035211016c0b117d26fc`.
The only real target remains public `orenvlad-ai/wb-price-extension`, target
`wb-price-extension`, profile `repo-only`, default branch `main`, repository id
`1335072844`, owner id `237411244` and required check `baseline`.

The first canonical live submit failed closed before task/card creation. The
installed daemon's `readPublicReviewRepository` calls:

```text
gh repo view <repository> --json nameWithOwner,isPrivate,defaultBranchRef,databaseId,owner
```

Installed GitHub CLI `2.87.2` rejects that command with
`Unknown JSON field: "databaseId"`. The same CLI returns the exact current
facts through read-only REST repository metadata. Control-plane PR #200 fixed
the model-free adapter/preflight lookup but did not change this independent
daemon runtime path. Repository identity is not in doubt; the unsupported
projection is the complete proven blocker.

The failed submit started only the exact canonical app/daemon pair. Before any
stop or replacement, read-only proof found SQLite integrity `ok`, 39 sessions
with zero active, 38 ReviewRuns with zero running, 58 terminal model actions
with zero claimed/running, 22 policy tasks, and zero `wb-price-extension`
tasks/sessions. Six retained arbiter panes and 22 retained reviewer panes are
bare `zsh` shells with no descendants. No worker, reviewer or arbiter model call
or token was created by the failed submit.

## 2. Authorized runtime correction

Replace only the daemon's unsupported GraphQL-shaped `gh repo view --json`
projection with a supported stable read-only GitHub REST path exposed by the
same installed `gh`. Decode its JSON into a typed Go value and independently
require all of these exact fields:

- repository full name equals the compile-time target repository;
- `private` is exactly false;
- default branch equals the compile-time target branch;
- numeric repository id equals the compile-time provider repository id;
- numeric owner id equals the compile-time provider owner id.

Unknown, null, absent, malformed, wrong-type, private, renamed, transferred,
wrong-branch, wrong-repository-id, wrong-owner-id and command-error results all
fail closed as `DCP_POLICY_TARGET_INVALID` before native identity or model
mutation. The runtime may not fall back to name-only, node id, local remote or
caller-supplied identity. Keep the existing local path, remote, branch, clean
main, origin/main, worktree-root and static allowlist checks unchanged.

The model-free adapter/preflight and daemon runtime should use the same REST
repository semantics where practical, but shell validation remains shell and
runtime validation remains typed Go. This contract does not create a shared
service or a second provider authority.

## 3. Test and security boundary

Focused source tests must prove the supported current-CLI command path and typed
success for exact `nameWithOwner/public/main/1335072844/237411244`. They must
also reject private, wrong repository name, wrong default branch, wrong
repository id, wrong owner id, null/absent values, malformed JSON and command
failure. Existing injected-validator tests for local Git/worktree identity stay
green.

The implementation adds no provider service, daemon, database, table,
migration, registry, queue, timer, poller, retry loop, credential, secret,
network grant, target, model authority, card/task identity or merge bypass.
Generated SQL/OpenAPI should remain byte-identical; their parity gates still
run. Serial Go tests/build/vet, governed renderer/type checks where applicable,
source/package/artifact gates, I9 and I12 audits remain required.

## 4. Governed delivery and stopped validation

Delivery is sequential:

1. merge this reviewed contract with green baseline;
2. merge one ordinary managed-source PR after exact-head semantic/security
   review and successful source/package CI;
3. merge one separate reviewed dev-control-plane immutable pin/install-guard
   PR;
4. only after proving zero active or unknown model/session/process activity,
   gracefully stop the exact canonical predecessor if it is still running;
5. deterministically run `prepare -> build -> install -> preflight` from clean
   fast-forwarded canonical `main` checkouts;
6. run a model-free installed/runtime provider validator through the exact
   production code path or a deterministic harness structurally incapable of
   task creation;
7. merge one terminal evidence PR and fast-forward clean canonical
   dev-control-plane `main`.

The installed/runtime harness may read the exact target and provider but may
not invoke submission, create a task/card/session/worktree/branch/PR, start a
worker/reviewer/arbiter or consume model tokens. The final application is
`STOPPED` and preflight-ready: runfile, browser socket, listener and app/daemon/
model descendants are absent. The target remains clean `main == origin/main`
at `9522cfb633f9b3f5a87298f4f1dcce902bb7ebfd`, with zero DCP tasks/sessions.

## 5. Preserved state and terminal meaning

All `dcp-review-lab` history, SQLite rows, retained bare panes, artifacts,
backups and PR #24 remain unchanged. Do not touch `wb-core`, production,
servers, other repositories, the two unrelated external Codex threads, product
implementation or Wildberries APIs. Do not run the real product DCP task; the
curator owns that separate post-handoff decision.

Technical completion means only that the exact installed daemon runtime
provider check accepts the exact public target model-free and that DCP is left
stopped/preflight-ready. It is not owner acceptance, product completion,
deployment or production mutation.
