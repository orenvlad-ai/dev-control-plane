# Dev Control Plane Docs Pack Manifest

docset_version: 0.4.0
built_at: 2026-05-10T22:49:34Z
built_from_commit: 8f7b1e79239d494dacec73c3daf22a5f0e1d75ac

authoritative_roots:

- `README.md`
- `AGENTS.md`
- `docs/architecture/*`
- `configs/target_projects/*`
- `apps/`
- `src/dev_control_plane/`

included_files:

- `00_INDEX__DEV_CONTROL_PLANE_DOCS.md`
- `01_PASSPORT__DEV_CONTROL_PLANE.md`
- `02_POLICY__CONTROL_PLANE_AND_CODEX_PROTOCOL.md`
- `03_GLOSSARY__TERMS.md`
- `04_TARGETS__WB_CORE_CONTEXT.md`
- `09_RUNBOOK__COMMON_SMOKE_AND_DEBUG.md`
- `99_MANIFEST__DOCSET_VERSION.md`

provenance: Derived from current `origin/main` / `main` at `8f7b1e79239d494dacec73c3daf22a5f0e1d75ac`.

build_note: Compact derived refresh for the standalone `dev-control-plane` project pack. This pack reflects current hosted-ready loopback control-plane status, MCP Stage 1 mixed no-auth/OAuth boundary, authenticated target docs, OpenAI/Codex setup boundaries, managed-clone Codex flow, live monitor and observability, runtime parity, verifier/timeline/result summary, target adapter policy, GitHub/SSH readiness, direct `wb-core` auto-task routing, frozen sprint/ping-pong/parent-child operator flow, selected/parallel promotion state, promotion diff matching, explicit `wb-core` production lane, post-merge resume, known gaps and smoke/runbook commands. Authoritative docs and code remain the roots listed above. This manifest is build metadata only.
