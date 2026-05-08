# Dev Control Plane Docs Pack Manifest

docset_version: 0.3.0
built_at: 2026-05-08T21:46:02Z
built_from_commit: d39fdada0c661418a038e81e08101881980da73d

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

provenance: Derived from current `origin/main` / `main` at `d39fdada0c661418a038e81e08101881980da73d`.

build_note: Compact derived refresh for the standalone `dev-control-plane` project pack. This pack reflects current hosted-ready loopback control-plane status, MCP Stage 1 mixed no-auth/OAuth boundary, authenticated target docs, OpenAI/Codex setup boundaries, managed-clone Codex flow, live monitor and observability, runtime parity, verifier/timeline/result summary, target adapter policy, GitHub/SSH readiness, explicit `wb-core` production lane, post-merge resume, sprint MVP, known gaps and smoke/runbook commands. Authoritative docs and code remain the roots listed above. This manifest is build metadata only.
