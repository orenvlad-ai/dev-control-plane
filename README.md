# Development Control Plane

Development Control Plane is a local-first development control-plane prototype. It manages bounded task specs, prompt generation, fake execution runs, handoff artifacts and deterministic verification for target repositories.

Current status: local-only prototype. It is not tied to any single product repo, and target projects are future configurable inputs.

## Run

Start the local server:

```bash
python3 apps/dev_control_plane_server.py --host 127.0.0.1 --port 8765
```

Default behavior is local-only. The server refuses non-`127.0.0.1` binds.

## Smokes

```bash
python3 apps/dev_control_plane_smoke.py
python3 apps/dev_control_plane_cli_smoke.py
python3 apps/dev_control_plane_server_smoke.py
python3 apps/dev_control_plane_runner_smoke.py
python3 apps/dev_control_plane_ai_smoke.py
python3 apps/dev_control_plane_target_smoke.py
python3 apps/dev_control_plane_practical_cockpit_smoke.py
python3 apps/dev_control_plane_real_codex_gate_smoke.py
```

## Target Projects

Target projects are external repositories described by local adapter metadata under `configs/target_projects/`. The first checked-in adapter is `wb-core`; it points at `/Users/ovlmacbook/Projects/wb-core` and is read-only by default.

Adapter config is not source of truth. Source-of-truth docs, code and policies stay in the target repo. The control-plane only reads configured source paths and merges target defaults such as forbidden paths/actions and required smokes into draft task specs.

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
4. Use `Сформировать карточку задачи`.
5. Review the human-readable `Карточка задачи`.
6. Use `Зафиксировать задачу`.
7. Run `Безопасно проверить сценарий`.
8. Review `Результат` / `Блокер`; raw JSON, prompt, handoff, logs and paths are under `Технические детали`.

The operator screen does not expose a fake/OpenAI selector. OpenAI curator mode is the normal UI path and fails closed when env configuration is missing. Fake curator remains available only for smoke/internal fallback with `DEV_CONTROL_PLANE_ENABLE_FAKE_CURATOR=1`. `Безопасно проверить сценарий` uses only the fake executor; real Codex execution is not enabled through the UI.

## Optional OpenAI Intake

The AI curator intake supports a fake provider for smokes and an optional OpenAI provider for local use.

Set local environment variables outside the repo:

```bash
export OPENAI_API_KEY=...
export CURATOR_COCKPIT_OPENAI_MODEL=...
```

Do not enter API keys in the UI. Do not commit `.env` files, API keys, auth files, logs containing secrets, or run ledgers with sensitive content.

## Codex CLI Setup

Codex CLI auth is terminal-only:

```bash
codex --login
```

Choose `Sign in with ChatGPT`. The cockpit shows whether `codex` is installed and reports that auth is checked at the first CLI run. The UI does not perform Codex login and does not expose a real Codex run button.

## Execution Boundary

The fake executor is the default and remains the only execution path exposed by the local UI. Real Codex CLI execution is available only through the runner CLI, requires `--allow-real-codex`, and runs in a managed clone under the selected state directory. It does not mutate the original target repo path and does not commit, push, merge or deploy.

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

No production route, deploy lane, public host, SSH/root action, auto-merge, or product-plane integration is part of this prototype.
