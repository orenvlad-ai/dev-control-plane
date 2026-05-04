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

The local cockpit is target-aware:

1. Start the server and open the local page.
2. Select a target project, for example `wb-core`.
3. Add an operator message in Discuss.
4. Use `Draft Task Spec from Discussion`.
5. Review the human-readable Task Card and target policy defaults.
6. Freeze the task.
7. Run `Run Safe Fake Flow`.
8. Review the compact result summary, blocker panel and optional prompt/handoff details.

The fake curator uses selected target defaults. OpenAI curator mode is optional and fail-closed when env configuration is missing. `Run Safe Fake Flow` uses only the fake executor; real Codex execution is not enabled through the UI.

## Optional OpenAI Intake

The AI curator intake supports a fake provider for smokes and an optional OpenAI provider for local use.

Set local environment variables outside the repo:

```bash
export OPENAI_API_KEY=...
export CURATOR_COCKPIT_OPENAI_MODEL=...
```

Do not commit `.env` files, API keys, auth files, logs containing secrets, or run ledgers with sensitive content.

## Execution Boundary

The fake executor is the default and is the only executor used by smokes. Real Codex execution is not enabled by default. Command execution exists only behind explicit policy and operator-controlled flags; it is not exposed by the local UI.

No production route, deploy lane, public host, SSH/root action, auto-merge, or product-plane integration is part of this prototype.
