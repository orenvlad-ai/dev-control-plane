# Decisions

## 2026-08-07 — retire the legacy epoch

- v1/v2 is frozen at `archive/legacy-v1-v2-20260807`; history is preserved
  without rewrite.
- Legacy modules, imports, routes, workflows and deployment code are absent
  from the active tree.
- The old hosted projection is retired. Its runtime and TLS evidence remain
  recoverable, while `devcontrol.pro` stays reserved.

## 2026-08-07 — leave a planning surface

- This repository contains documentation and model-free CI only.
- No Agent Orchestrator or other control-plane implementation is selected or
  imported by this reset.
- Architecture and implementation require a new owner-approved task.
- Technical completion and owner acceptance remain separate states.
