# Control Plane And Codex Protocol Policy

## Task Classification

- L1: narrow local repo task with low blast radius; may be handled with normal local edits and focused checks.
- L2: repo task with moderate cross-file or workflow impact; requires stronger local verification and clearer handoff.
- L3: project, governance, repo-boundary, target-boundary, security, release, remote, or policy task; requires explicit scope, exact blockers, conservative Git/GitHub closure and no target mutation unless separately authorized.

## Prompt Contract

Bounded execution starts from a frozen TaskSpec and a concrete sprint step. Real Codex handoff must start with the exact first line:

```text
=== ДЛЯ КУРАТОРА ===
```

It must also include:

```text
=== СЖАТАЯ ПРОВЕРКА ===
```

Verifier failures must name missing contract blocks or forbidden conditions directly.

## Managed Clone Safety

Real Codex is allowed only when explicitly gated by the runner/UI path and only inside a managed clone/workspace under control-plane state. The original target repo working tree and git metadata are not execution workspaces.

Safe fake-flow and managed Codex UI flow create review artifacts. They do not commit, push, merge, deploy, open public routes, use SSH/root, or mutate product-plane routes.

## Target Repo Mutation Policy

Target repos are read-only by default. `dev-control-plane` may read configured target context and clone a target into a managed workspace. Direct writes, checkout/reset, commits, pushes, merges, live smokes and deploys in the original target repo are forbidden unless a future explicit apply policy is designed and approved.

## Secrets Policy

Secrets stay outside the repo. OpenAI setup uses the local terminal CLI:

```bash
python3 apps/dev_control_plane_setup.py openai
```

The normal local store is `~/.dev-control-plane/secrets.json`, outside this repo. Do not commit `.env`, `*.env`, `secrets.json`, auth files, Codex auth, provider credentials, run ledgers with sensitive content, or logs containing credentials. Cockpit APIs and diagnostics must not return API keys, Authorization headers, raw tracebacks or full provider bodies.

## Git And GitHub Closure Policy

For L3 repo-boundary work:

- Start with exact local repo state: `pwd`, `git status --short --branch`, `git log --oneline -5`, `git remote -v`, and GitHub auth status.
- If the repo is dirty before remote creation, do not reset and do not create the remote; return the exact blocker.
- GitHub remotes for this project must be private.
- If a remote repo already exists, connect to it only if it matches the intended private repo boundary.
- Commit only intended governance/doc changes and push `main` when checks pass.
- Do not create public repos or upload this pack to a ChatGPT Project from the local task flow.
