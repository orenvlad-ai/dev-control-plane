# Dev Control Plane Docs Pack Index

This directory is a compact derived and secondary retrieval pack for `dev-control-plane`.

It is not a dump-copy of `README.md`, `AGENTS.md`, `docs/`, `src/`, `apps/` or target-repo docs. It is not the authoritative project record.

## Source Of Truth Rule

Authoritative sources remain:

- `README.md`
- `AGENTS.md`
- `docs/architecture/*`
- `configs/target_projects/*`
- current code-state in `apps/` and `src/dev_control_plane/`

Ordinary task-flow updates code/tests and touched authoritative docs when truth changes. It does not update `dev_control_plane_docs_master/**` or the manifest by default.

This pack is refreshed only by an explicit derived-sync flow. If this pack conflicts with authoritative docs or code-state, treat this pack as stale and fix/rebuild from the authoritative layer.

`99_MANIFEST__DOCSET_VERSION.md` is build metadata only. It must not store upload state, runtime state, local server state, secrets state or run artifact state.

## Reading Order

1. `01_PASSPORT__DEV_CONTROL_PLANE.md`
2. `02_POLICY__CONTROL_PLANE_AND_CODEX_PROTOCOL.md`
3. `03_GLOSSARY__TERMS.md`
4. `04_TARGETS__WB_CORE_CONTEXT.md`
5. `09_RUNBOOK__COMMON_SMOKE_AND_DEBUG.md`
6. `99_MANIFEST__DOCSET_VERSION.md`

## Navigation

- Passport: standalone identity, implemented capabilities, hosted-ready status and known gaps.
- Policy: task classification, MCP/Codex protocol boundaries, managed-clone safety, target mutation, secrets, Git/GitHub closure and derived-pack governance.
- Glossary: stable terms used by operators and curators.
- Target context: `wb-core` as the first external target profile, not repo identity, plus its explicit production-lane exception.
- Runbook: local/hosted startup, terminal-only credential setup, MCP/live-monitor checks, smokes and artifact inspection.
- Manifest: build metadata for this derived pack only.
