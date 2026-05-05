# Target Context: wb-core

## Role

`wb-core` is the first checked-in target profile for `dev-control-plane`. It is external target context, not the identity of this repo.

## Adapter Identity

- Adapter file: `configs/target_projects/wb_core.json`
- Project id: `wb-core`
- Display name: `wb-core`
- Repo path: `/Users/ovlmacbook/Projects/wb-core`
- GitHub identity: not declared in the `dev-control-plane` adapter

## Source Of Truth Paths

The adapter lists these target source-of-truth paths:

- `README.md`
- `docs/architecture/`
- `docs/modules/`
- `migration/`

The adapter also lists `wb_core_docs_master/` as derived secondary target context. Do not paste or copy the full `wb_core_docs_master` pack into this dev-control-plane pack.

## Forbidden Paths And Actions

Default forbidden target paths include:

- `wb_core_docs_master/**`
- `99_MANIFEST__DOCSET_VERSION.md`
- `runtime/**`
- `deploy/**`
- `infra/**`
- `artifacts/registry_upload_http_entrypoint/**`

Default forbidden actions include live deploy, SSH, root shell, public route changes, SellerOS product-plane route changes, Google Sheets Apps Script writes, secrets writes, auto-merge and direct target mutation.

## Boundary Rule

The current ChatGPT Project remains canonical for `wb-core` product work. `dev-control-plane` tasks must not mutate `wb-core` except through managed clones and a future explicit apply policy.

Current validation, snapshot, safe fake-flow and managed Codex review flows treat the original `/Users/ovlmacbook/Projects/wb-core` working tree as read-only.
