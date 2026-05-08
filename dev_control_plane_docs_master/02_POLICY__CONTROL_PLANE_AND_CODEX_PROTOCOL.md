# Control Plane And Codex Protocol Policy

This file is derived secondary context. The authoritative policy remains in `AGENTS.md`, `README.md`, `docs/architecture/*` and current code-state.

## Task Classification

- L1: narrow local repo task with low blast radius; normal local edits and focused checks are enough.
- L2: bounded repo task with moderate cross-file or workflow impact; requires stronger local verification and clear handoff.
- L3: project, governance, repo-boundary, target-boundary, security, release, remote, live, or policy task; requires explicit scope, exact blockers, conservative Git/GitHub closure and no target mutation unless separately authorized.

## Two-Layer Documentation Governance

- Authoritative source of truth is `README.md`, `AGENTS.md`, `docs/architecture/*`, `configs/target_projects/*`, `apps/` and `src/dev_control_plane/`.
- Ordinary task-flow updates code/tests and touched authoritative docs only when current truth changed.
- `dev_control_plane_docs_master/**` is a derived secondary retrieval pack. It is not updated by default in ordinary task-flow.
- This pack is refreshed only by explicit derived-sync.
- `99_MANIFEST__DOCSET_VERSION.md` is build metadata only and must not store operational lifecycle fields.

## MCP And UI Boundary

The main hosted UI remains behind the approved Basic Auth boundary. `/mcp` is the controlled ChatGPT interface exception: public no-auth discovery/calls expose only read tools with `readOnlyHint=true`, write tools are hidden/denied without OAuth, and authenticated write exposure requires OAuth authorization-code + PKCE with `dcp.write`.

Authenticated target docs tools are read-only but not public no-auth tools. They read allowlisted target docs from cached snapshots and reject traversal, forbidden paths, derived target packs, runtime/deploy/infra/artifact paths, env/secret/auth files and oversized reads.

MCP tools must not expose arbitrary shell, raw command execution, secret reads or direct target mutation. Start tools return a `run_id` quickly plus live/watch URLs; follow-up inspection uses status/report/artifact/timeline/log-tail tools.

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

Real Codex is allowed only when explicitly gated by the runner/UI/MCP path and only inside a managed clone/workspace under control-plane state. The original target repo working tree and git metadata are not execution workspaces.

Safe fake-flow and managed Codex review flow create artifacts. They do not commit, push, merge, deploy, open product routes, use SSH/root or mutate product-plane routes.

The real-Codex path has no arbitrary shell command field and no Codex command template input. It starts the built-in managed-clone executor, returns a job/run id, records prompt/handoff/diff/log/verifier artifacts, and exposes sanitized live monitor state.

Hosted Codex may use `danger-full-access` only inside the isolated managed clone when the Linux sandbox cannot create its loopback namespace. DCP gates still enforce workspace ownership, preflight, forbidden-path/action, original-target-unchanged and no target mutation outside an explicit production lane.

Before Codex starts, runtime parity and prompt consistency gates may block with exact operator-facing reasons. Smokes use fake/stub Codex/OpenAI paths.

## Target Repo Mutation Policy

Target repos are read-only by default. `dev-control-plane` may read configured target context and clone a target into a managed workspace. Direct writes, checkout/reset, commits, pushes, merges, live smokes and deploys in the original target repo are forbidden.

Generic target PR, preview and approve/reject workflows are decision-only. The explicit `wb-core` production lane is the current exception: it may create a target branch/PR, merge and run the approved WebCore deploy runner only from verifier-passed managed-clone output and only after rollback, secrets, forbidden-path, GitHub auth, SSH readiness, PR head SHA, deploy-runner and single-target-lock gates pass.

The `start_sprint` MVP and its `DEVCONTROL_START_SPRINT_V1` compatibility bridge are managed-clone-only. They cannot create PRs, merge, deploy, SSH, mutate the original target repo or enter the production lane.

The post-merge resume path for `wb-core` is a recovery path only for already merged blocked production-lane runs. It may resume backup/deploy/probes after eligibility gates; it must not rerun Codex, create a branch, commit, push, open a new PR or merge again.

These exceptions do not make `wb-core` the identity of this repo and do not authorize external WB live actions, DB migrations or derived-pack changes by default.

## Secrets Policy

Secrets stay outside the repo. OpenAI setup uses the terminal CLI:

```bash
python3 apps/dev_control_plane_setup.py openai
```

Codex CLI auth is terminal-only:

```bash
codex login
codex login --device-auth
```

Hosted GitHub tokens, Codex auth and `wb-core` deploy SSH target config also belong outside the repo under approved runtime secret/config locations. Diagnostics may report readiness/source/status only; they must not return token values, Authorization headers, cookies, private key material, raw env, raw provider bodies, raw tracebacks or auth file contents.

Do not commit `.env`, `*.env`, `secrets.json`, auth files, Codex auth, provider credentials, run ledgers with sensitive content, or logs containing credentials.

## Git And GitHub Closure Policy

Codex-owned GitHub closure is allowed only for this `orenvlad-ai/dev-control-plane` repo and only for the current task/current `codex/*` branch or PR created by the task.

Required gates include clean working tree, open PR with expected head SHA, required smokes/checks, `git diff --check`, `git diff --cached --check`, verifier passed where applicable, no forbidden paths/actions, protected derived docset unchanged unless explicitly scoped, clean secrets scan, complete handoff, no blocker and no `NO_AUTO_MERGE`.

Runner/server expose `github-closure-decision` and `POST /api/github-closure/decision` as decision-only gates. They return closure eligibility but do not store GitHub credentials or perform hidden GitHub API mutation.

This self-closure policy does not apply to `wb-core` or any target repo, production deploy, preview/staging deploy, direct target mutation, public routes, SSH/root, or bypassing checks.
