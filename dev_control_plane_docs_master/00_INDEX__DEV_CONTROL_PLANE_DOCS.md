# Dev Control Plane Docs Pack Index

This directory is a compact derived project-pack skeleton for a future standalone ChatGPT Project for `dev-control-plane`.

It is not a dump-copy of `docs/`, and it is not the authoritative project record.

## Source Of Truth Rule

Authoritative sources remain:

- `README.md`
- `AGENTS.md`
- `docs/architecture/*`
- `configs/target_projects/*`
- `apps/` and `src/dev_control_plane/` code-state

This pack is secondary. If this pack conflicts with authoritative docs or code-state, update the authoritative source first and then refresh this pack.

## Reading Order

1. `01_PASSPORT__DEV_CONTROL_PLANE.md`
2. `02_POLICY__CONTROL_PLANE_AND_CODEX_PROTOCOL.md`
3. `03_GLOSSARY__TERMS.md`
4. `04_TARGETS__WB_CORE_CONTEXT.md`
5. `09_RUNBOOK__COMMON_SMOKE_AND_DEBUG.md`
6. `99_MANIFEST__DOCSET_VERSION.md`

## Navigation

- Passport: standalone identity, current capabilities, MVP status and known gaps.
- Policy: task classification, prompt contract, managed-clone safety, target mutation, secrets and Git/GitHub closure.
- Glossary: stable terms used by operators and curators.
- Target context: the first checked-in target profile, `wb-core`, as read-only external context.
- Runbook: local cockpit startup, local secret setup, smokes and artifact inspection.
- Manifest: docset build metadata only.
