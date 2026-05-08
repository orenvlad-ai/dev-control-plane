# Target Context: wb-core

This file is derived secondary context. The authoritative target adapter is `configs/target_projects/wb_core.json`; target project truth remains in the external target repo.

## Role

`wb-core` is the first checked-in target profile for `dev-control-plane`. It is external target context, not the identity of this repo.

## Adapter Identity

- Adapter file: `configs/target_projects/wb_core.json`
- Project id: `wb-core`
- Display name: `wb-core`
- Source mode: `remote_managed_clone`
- Remote managed clone source: `https://github.com/orenvlad-ai/wb-core.git` on `main`
- Local fallback/context path: `/Users/ovlmacbook/Projects/wb-core`
- Read-only by default: yes
- Direct original-target mutation: no
- Auto-merge by default: no
- Live deploy by default: no

Hosted mode does not require the local Mac path when the remote source is reachable. Missing local path is a warning for hosted mode, not a blocker when remote managed clone is available.

## Source Of Truth Paths

The adapter lists these target source-of-truth paths:

- `README.md`
- `docs/architecture/`
- `docs/modules/`
- `migration/`

The adapter also lists `wb_core_docs_master/` as derived secondary target context. Do not paste or copy the full `wb_core_docs_master` pack into this `dev-control-plane` pack.

Source-of-truth paths are context, not automatic forbidden paths. Forbidden paths come from explicit target policy and task scope.

Authenticated MCP target docs tools may read only allowlisted target docs from a cached git snapshot under control-plane state. They do not checkout/reset the original target repo, do not mutate managed clones, and reject traversal, runtime/deploy/infra/artifact/env/secret/auth paths, oversized reads and derived target packs by default.

## Forbidden Paths And Actions

Default forbidden target paths include:

- `wb_core_docs_master/**`
- `99_MANIFEST__DOCSET_VERSION.md`
- `runtime/**`
- `deploy/**`
- `infra/**`
- `artifacts/registry_upload_http_entrypoint/**`

Default forbidden actions include live deploy, SSH, root shell, public route changes, SellerOS product-plane route changes, Google Sheets Apps Script writes, secrets writes, auto-merge and direct target mutation.

## Review And Sprint Boundaries

Validation, snapshot, target-docs reads, safe fake-flow and managed Codex review flows treat the original target repo as read-only. Managed-clone output is review material until an explicit apply policy consumes it.

The MCP `start_sprint` flow is not target apply. It supports only `target_id=wb-core`, `execution_mode=managed_clone_only`, bounded step/retry counts and managed-clone child runs. It never opens PRs, merges, deploys, SSHes, starts production-lane work or mutates the original target repo.

## Production Lane Boundary

Generic target PR/preview/approval workflow is decision-only. The explicit `wb-core` production lane is the current production-capable exception:

1. consume verifier-passed managed-clone output;
2. pass production-lane toolchain, GitHub auth and SSH deploy readiness preflight;
3. acquire the single `wb-core` production lock;
4. create a `devcp/<run_id>-<slug>` target branch;
5. commit and open a target PR with required Russian metadata;
6. merge only with expected PR head SHA;
7. create rollback/app backup;
8. run the approved WebCore deploy runner;
9. run post-deploy probes and publish a report.

The lane still forbids direct push to `main`, deploy without merged PR, deploy with failed verifier/forbidden paths/secrets, external WB live writes, DB migrations and derived-pack changes by default.

OAuth-gated post-merge resume is limited to already merged blocked production-lane runs. It may resume backup/deploy/probes only after eligibility checks and must not rerun Codex, change the diff, create a branch, push, open a new PR or merge again.
