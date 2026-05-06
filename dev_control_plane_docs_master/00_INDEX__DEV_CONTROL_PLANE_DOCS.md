# Dev Control Plane Docs Pack Index

This directory is a compact derived and secondary project pack for `dev-control-plane`.

It is not a dump-copy of `docs/`, `README.md`, `AGENTS.md`, `src/`, `apps/` or target-repo docs, and it is not the authoritative project record.

## Source Of Truth Rule

Authoritative sources remain:

- `README.md`
- `AGENTS.md`
- `docs/architecture/*`
- `configs/target_projects/*`
- current code-state in `apps/` and `src/dev_control_plane/`

This pack is refreshed only by an explicit derived-sync flow. Ordinary task-flow updates code/tests and touched authoritative docs when truth changed; it does not update `dev_control_plane_docs_master/**` or the manifest by default.

If this pack conflicts with authoritative docs or code-state, treat this pack as stale. Fix the authoritative source first when needed, then rebuild this derived pack.

## Reading Order

1. `01_PASSPORT__DEV_CONTROL_PLANE.md`
2. `02_POLICY__CONTROL_PLANE_AND_CODEX_PROTOCOL.md`
3. `03_GLOSSARY__TERMS.md`
4. `04_TARGETS__WB_CORE_CONTEXT.md`
5. `09_RUNBOOK__COMMON_SMOKE_AND_DEBUG.md`
6. `99_MANIFEST__DOCSET_VERSION.md`

## Navigation

- Passport: standalone identity, implemented capabilities, hosted-ready status and known gaps.
- Policy: task classification, prompt contract, managed-clone safety, target mutation, secrets, Git/GitHub closure and derived-pack governance.
- Glossary: stable terms used by operators and curators.
- Target context: the first checked-in target profile, `wb-core`, as external target context and explicit production-lane exception.
- Runbook: local cockpit startup, terminal-only credential setup, hosted diagnostics, smokes and artifact inspection.
- Manifest: build metadata only.
