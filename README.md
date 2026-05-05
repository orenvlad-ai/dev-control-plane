# Development Control Plane

Development Control Plane is a local-first development control-plane prototype. It manages bounded task specs, prompt generation, fake execution runs, handoff artifacts and deterministic verification for target repositories.

Current status: local-only standalone project. It is not tied to any single product repo, and target projects are configurable inputs.

## Project Boundary

`dev-control-plane` is its own control-plane repo and project. It is not `wb-core`, not a SellerOS/product-plane runtime, and not a public deployment surface.

`wb-core` is the first external target profile. It remains a separate target repo and is read-only by default. Control-plane runs may read target context and may create managed clones/workspaces, but the original target repo working tree is not mutated by current flows.

The UI safe flow and managed Codex flow do not commit, push, merge, deploy, open public routes, use SSH/root, or change product-plane routes. Real Codex execution is gated and runs only in a managed clone. Smoke tests use fakes/stubs and must not call the real OpenAI API or the real Codex executor.

Hosted control-plane design is tracked in `docs/architecture/02_hosted_control_plane_architecture.md`. It defines the future PR + preview/staging workflow while keeping production deploy, direct target mutation and secrets exposure out of scope.

Secrets are stored outside this repo. OpenAI key setup uses the local terminal CLI:

```bash
python3 apps/dev_control_plane_setup.py openai
```

Do not commit `.env`, `secrets.json`, auth files, run ledgers containing sensitive data, or logs containing credentials.

## Run

Start the local server:

```bash
python3 apps/dev_control_plane_server.py --host 127.0.0.1 --port 8765
```

Default behavior is local-only. The server refuses non-`127.0.0.1` binds.

State defaults to `${DEV_CONTROL_PLANE_STATE_DIR}` when the env var is set, otherwise `/tmp/development-control-plane-state`. Runner/server paths are resolved through the unified state layout: `runs/` for per-run metadata and artifacts, `workspaces/` for managed workspaces, `artifacts/` for shared prompt artifacts, `logs/`, `verifier/`, and `collections/` for cockpit state.

## GitHub Closure

Codex may perform commit, push, PR creation, merge and branch deletion for its own PRs in `orenvlad-ai/dev-control-plane`, including L3 governance tasks, only after clean gates: current-task or current `codex/*` branch ownership, clean working tree, open PR with expected head SHA, required smokes/checks passed, `git diff --check`, `git diff --cached --check`, verifier passed, no forbidden paths/actions, no protected derived docset changes unless explicitly scoped, clean secrets scan, complete handoff, no blocker and no `NO_AUTO_MERGE`.

This self-closure policy is repo-local. It does not authorize PR merge/apply in `wb-core` or any target repo, production deploy, preview/staging deploy, public routes, SSH/root, direct target mutation, or bypassing verifier/checks.

## Smokes

```bash
python3 apps/dev_control_plane_smoke.py
python3 apps/dev_control_plane_cli_smoke.py
python3 apps/dev_control_plane_server_smoke.py
python3 apps/dev_control_plane_runner_smoke.py
python3 apps/dev_control_plane_state_layout_smoke.py
python3 apps/dev_control_plane_github_closure_smoke.py
python3 apps/dev_control_plane_ai_smoke.py
python3 apps/dev_control_plane_target_smoke.py
python3 apps/dev_control_plane_practical_cockpit_smoke.py
python3 apps/dev_control_plane_real_codex_gate_smoke.py
python3 apps/dev_control_plane_real_codex_ui_smoke.py
python3 apps/dev_control_plane_run_timeline_smoke.py
python3 apps/dev_control_plane_openai_diagnostics_smoke.py
python3 apps/dev_control_plane_secrets_smoke.py
python3 apps/dev_control_plane_task_flow_smoke.py
```

## Target Projects

Target projects are external repositories described by local adapter metadata under `configs/target_projects/`. The first checked-in adapter is `wb-core`; it points at `/Users/ovlmacbook/Projects/wb-core` and is read-only by default.

Adapter config is not source of truth. Source-of-truth docs, code and policies stay in the target repo. The control-plane only reads configured source paths and merges target defaults such as forbidden paths/actions and required smokes into draft task specs.

Source-of-truth paths are context, not automatic forbidden paths. For example, `README.md`, `docs/architecture/`, `docs/modules/`, and `migration/` should not be forbidden just because they are canonical source paths.

Inspect targets locally:

```bash
python3 apps/dev_control_plane_target_cli.py list-targets --config-dir configs/target_projects
python3 apps/dev_control_plane_target_cli.py validate-target --config configs/target_projects/wb_core.json
python3 apps/dev_control_plane_target_cli.py snapshot-target --config configs/target_projects/wb_core.json --output /tmp/wb-core-context-snapshot.json
```

Target repo mutation is reserved for future explicitly gated execution modes. Current target validation/snapshot flows are read-only.

## Practical Cockpit Flow

The local cockpit is a Russian chat-first operator UI:

1. Start the server and open the local page.
2. Select a target project, for example `wb-core`.
3. Write the task in `Чат`.
4. Use `Подготовить задачу`; for simple L1/L2 repo-only tasks this drafts and freezes the card when validation passes.
5. Review the human-readable `Карточка задачи`.
6. Use `Запустить Codex безопасно` for an operator-confirmed real Codex run in a managed clone.
7. Watch the scrollable `Ход выполнения` block for managed-clone/Codex/verifier progress.
8. Review `Результат выполнения`: changed files, changed-file count, target unchanged status, verifier status, `git diff --check`, next action, and compact diff/handoff previews.
9. Raw JSON, full prompt, handoff, diff, logs and paths are under `Технические детали`.

The operator screen does not expose a fake/OpenAI selector. OpenAI curator mode is the normal UI path and fails closed when env configuration is missing. Fake curator remains available only for smoke/internal fallback with `DEV_CONTROL_PLANE_ENABLE_FAKE_CURATOR=1`. `Тестовый прогон без Codex` is an advanced optional action that uses only the fake executor and is usually not required before a standard managed-clone run. `Запустить Codex безопасно` starts real Codex only after operator confirmation and only in a managed clone; it does not mutate the original target repo and does not commit, push, merge or deploy.

Runnable specs are normalized with at least one sprint step. If no step id is supplied, safe fake-flow uses the first runnable step instead of assuming `step-001`.

Chat messages are optimistic: the operator message appears immediately, the UI shows `Куратор думает...`, and duplicate sends are disabled while the request is pending. Main actions show loading states such as `Готовлю задачу...`, `Формирую карточку...`, `Фиксирую задачу...`, `Проверяю сценарий...`, `Запускаю Codex...`, and `Проверяю OpenAI...`.

## Optional OpenAI Intake

The AI curator intake supports a fake provider for smokes and an optional OpenAI provider for local use.

Recommended one-time local setup:

```bash
python3 apps/dev_control_plane_setup.py openai
```

The setup command asks for the API key with hidden terminal input and stores it outside this repo at `~/.dev-control-plane/secrets.json`. The secret directory is created with restricted permissions where the OS supports it, and the secret file is written with mode `0600`.

Check local setup:

```bash
python3 apps/dev_control_plane_setup.py status
```

Environment variables still have priority over the local secret file:

```bash
export OPENAI_API_KEY=...
export CURATOR_COCKPIT_OPENAI_MODEL=...
```

Delete stored OpenAI credentials:

```bash
python3 apps/dev_control_plane_setup.py delete-openai
```

Do not enter API keys in the UI. Do not commit `.env` files, API keys, auth files, local secret stores, logs containing secrets, or run ledgers with sensitive content. The cockpit, status API and probe never return the API key.

Use the `Подключения` tab and its `Проверить OpenAI` button to run a minimal local connection test. The result is sanitized: it may include `error_type`, HTTP status, request id, model, short message and a suggested next step, but never the API key or Authorization header.

The OpenAI client uses the Responses API with the same minimal shape as the manual curl path: `{"model": "...", "input": "..."}`. If the local Python install cannot find a CA bundle, set `DEV_CONTROL_PLANE_OPENAI_CA_BUNDLE=/path/to/cert.pem`.

Manual terminal probe:

```bash
python3 apps/dev_control_plane_openai_probe.py
```

The probe reads env vars first, then the local secret file, prints sanitized JSON and exits `0` only when OpenAI responds successfully. Smoke tests cover diagnostics with stubs and do not call the real OpenAI API.

## Codex CLI Setup

Codex CLI auth is terminal-only:

```bash
codex --login
```

Choose `Sign in with ChatGPT`. The cockpit shows whether `codex` is installed and reports that auth is checked at the first Codex run. The UI does not perform Codex login and never asks for Codex credentials.

## Execution Boundary

The fake executor is the default safe check. Real Codex execution is available through the runner CLI and through the local UI's `Запустить Codex безопасно` button, but both paths are gated and use a managed clone under the selected state directory. They do not mutate the original target repo path and do not commit, push, merge or deploy target repo changes.

The UI real-Codex path has no arbitrary shell command field and no Codex command template input. It starts only the built-in managed-clone Codex executor, returns a job id immediately, polls job status (`queued`, `preparing`, `running_codex`, `verifying`, `passed`, `failed`, `blocked`), and stores prompt, handoff, diff, log and verifier artifacts for review.

The cockpit shows a compact scrollable `Ход выполнения` timeline built from job lifecycle, Codex JSONL log events when available, changed files, and verifier checks. Raw Codex logs stay under `Технические детали`.

Codex final handoff must start with the exact first line `=== ДЛЯ КУРАТОРА ===` and must include `=== СЖАТАЯ ПРОВЕРКА ===`. If the report is missing a required block, the verifier returns an explicit handoff contract error naming the missing header.

Safe managed-clone tasks do not require a human gate to confirm the generated workspace path. Real Codex authorization is enforced by the runner CLI flag, not by adding a repeated human gate to every TaskSpec.

The runner CLI also selects the first runnable sprint step when no `--step-id` is supplied, and falls back to that first step with a warning when a supplied step id is absent.

Operator-controlled example:

```bash
python3 apps/dev_control_plane_runner.py run-codex-cli \
  --target-config configs/target_projects/wb_core.json \
  --task-spec /path/to/frozen_task_spec.json \
  --step-id step-001 \
  --state-dir /tmp/dev-control-plane-runs \
  --allow-real-codex
```

The smoke suite uses a fake Codex binary, not the real Codex CLI. Command output is captured as local artifacts: prompt, handoff, diff and logs.

No production route, deploy lane, public host, SSH/root action, target repo auto-merge, or product-plane integration is part of this prototype.
