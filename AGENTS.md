# Repository rules

This repository is an intentionally minimal planning surface. There is no
active control-plane runtime in this tree.

- Do not reactivate or copy code from the retired v1/v2 epoch into the active
  tree. Use `archive/legacy-v1-v2-20260807` only as historical evidence.
- Do not add a scheduler, supervisor, watcher, registry writer, model loop,
  App Server integration, target adapter, hosted API or UI unless a later task
  explicitly approves its design and implementation.
- Keep runtime state, databases, logs, secrets, auth and TLS material outside
  Git. Never commit credentials or private archive contents.
- Preserve repository history; use ordinary branches and pull requests. Do not
  force-push or rewrite the archived epoch.
- Treat target repositories as external and read-only unless their own current
  governed workflow explicitly authorizes a change.
- Prefer deterministic, model-free validation. Do not synthesize owner
  acceptance.

The current scope is documented only in `docs/PROJECT_BRIEF.md`,
`docs/ROADMAP.md` and `docs/DECISIONS.md`.
