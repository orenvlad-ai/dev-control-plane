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

Hosted mode does not require the local Mac path when the remote source is reachable.

## Source Of Truth Paths

The adapter lists these target source-of-truth paths:

- `README.md`
- `docs/architecture/`
- `docs/modules/`
- `migration/`

The adapter also lists `wb_core_docs_master/` as derived secondary target context. Do not paste or copy the full `wb_core_docs_master` pack into this `dev-control-plane` pack.

Source-of-truth paths are context, not automatic forbidden paths. Forbidden paths come from explicit target policy and task scope.

## Forbidden Paths And Actions

Default forbidden target paths include:

- `wb_core_docs_master/**`
- `99_MANIFEST__DOCSET_VERSION.md`
- `runtime/**`
- `deploy/**`
- `infra/**`
- `artifacts/registry_upload_http_entrypoint/**`

Default forbidden actions include live deploy, SSH, root shell, public route changes, SellerOS product-plane route changes, Google Sheets Apps Script writes, secrets writes, auto-merge and direct target mutation.

## Review And Production Boundaries

Validation, snapshot, safe fake-flow and managed Codex review flows treat the original target repo as read-only. Managed-clone output is review material until an explicit apply policy consumes it.

Generic target PR/preview/approval workflow is decision-only. The explicit `wb-core` production lane is the current production-capable exception:

1. consume verifier-passed managed-clone output;
2. acquire the single `wb-core` production lock;
3. create a `devcp/<run_id>-<slug>` target branch;
4. commit and open a target PR with required Russian metadata;
5. merge only with expected PR head SHA;
6. create rollback/app backup;
7. run the approved WebCore deploy runner;
8. run post-deploy probes and publish a report.

The lane still forbids direct push to `main`, deploy without merged PR, deploy with failed verifier/forbidden paths/secrets, external WB live writes, DB migrations and derived-pack changes by default.
