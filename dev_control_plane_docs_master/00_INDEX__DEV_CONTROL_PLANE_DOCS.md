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

## Current Focus

This refresh captures the current post-freeze control-plane shape:

- `dev-control-plane` is the primary project identity.
- `wb-core` is an external target profile, not this repo identity.
- Ordinary ChatGPT Project WebCore work uses direct `start_wb_core_auto_task`: one production-capable run or an exact blocker before Codex starts.
- `start_sprint`, curator ping-pong, parent/child decomposition and the `DEVCONTROL_START_SPRINT_V1` bridge are frozen for ordinary operator flow.
- Parallel and selected promotion flows remain explicit, policy-gated and routed through existing verifier/production-lane gates.

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
- Target context: `wb-core` as the first external target profile, direct WebCore auto-task boundary and explicit production-lane exception.
- Runbook: local/hosted startup, terminal-only credential setup, MCP/live-monitor checks, direct auto-task/sprint-freeze smokes and artifact inspection.
- Manifest: build metadata for this derived pack only.
