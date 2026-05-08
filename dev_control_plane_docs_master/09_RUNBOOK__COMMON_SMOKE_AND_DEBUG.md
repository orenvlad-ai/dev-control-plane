# Common Smoke And Debug Runbook

This file is derived secondary context. Authoritative run commands and behavior live in `README.md`, `AGENTS.md`, `docs/architecture/*`, `apps/` and `src/dev_control_plane/`.

## Start The Cockpit

```bash
python3 apps/dev_control_plane_server.py --host 127.0.0.1 --port 8765
```

The default server is local-only and refuses non-`127.0.0.1` binds.

Hosted server profile remains loopback-only behind its approved service/proxy boundary:

```bash
DEV_CONTROL_PLANE_RUNTIME_PROFILE=hosted \
DEV_CONTROL_PLANE_STATE_DIR=/opt/dev-control-plane-runtime/state \
python3 apps/dev_control_plane_server.py --host 127.0.0.1 --port 8770
```

Open the live monitor through the operator UI link `Живые запуски` or directly at `/runs/live`. It is read-only and has no shell input.

## Set Up OpenAI Secret

```bash
python3 apps/dev_control_plane_setup.py openai
python3 apps/dev_control_plane_setup.py status
python3 apps/dev_control_plane_setup.py delete-openai
```

The key is entered in the terminal and stored outside this repo. Do not enter API keys into the browser UI and do not commit local secret files.

Manual sanitized probe:

```bash
python3 apps/dev_control_plane_openai_probe.py
```

## Check Codex, MCP And Hosted Toolchain

```bash
codex login
codex login --device-auth
codex --version
python3 apps/dev_control_plane_setup.py mcp-token
python3 apps/dev_control_plane_setup.py generate-mcp-token
python3 apps/dev_control_plane_setup.py delete-mcp-token
```

Use terminal-only Codex auth. The cockpit does not collect Codex credentials. ChatGPT write-tool setup uses OAuth `dcp.write`; the legacy MCP bearer token is only a protocol-smoke/direct-control fallback.

Hosted runs use sanitized diagnostics for required tools such as `git`, `rg`, `python3`, `jq`, the configured Codex binary, hosted package managers and browser readiness before Codex starts.

## Target Adapter Commands

```bash
python3 apps/dev_control_plane_target_cli.py list-targets --config-dir configs/target_projects
python3 apps/dev_control_plane_target_cli.py validate-target --config configs/target_projects/wb_core.json
python3 apps/dev_control_plane_target_cli.py snapshot-target --config configs/target_projects/wb_core.json --output /tmp/wb-core-context-snapshot.json
```

These commands are read-only against target repos.

## Run Smokes

```bash
python3 apps/dev_control_plane_smoke.py
python3 apps/dev_control_plane_cli_smoke.py
python3 apps/dev_control_plane_server_smoke.py
python3 apps/dev_control_plane_runner_smoke.py
python3 apps/dev_control_plane_state_layout_smoke.py
python3 apps/dev_control_plane_hosted_server_smoke.py
python3 apps/dev_control_plane_hosted_deploy_smoke.py
python3 apps/dev_control_plane_github_closure_smoke.py
python3 apps/dev_control_plane_github_closure_workflow_smoke.py
python3 apps/dev_control_plane_github_auth_smoke.py
python3 apps/dev_control_plane_ssh_deploy_smoke.py
python3 apps/dev_control_plane_target_production_smoke.py
python3 apps/dev_control_plane_mcp_smoke.py
python3 apps/dev_control_plane_mcp_oauth_smoke.py
python3 apps/dev_control_plane_mcp_public_discovery_smoke.py
python3 apps/dev_control_plane_mcp_sprint_bridge_smoke.py
python3 apps/dev_control_plane_mcp_start_sprint_smoke.py
python3 apps/dev_control_plane_sprint_orchestrator_smoke.py
python3 apps/dev_control_plane_live_monitor_smoke.py
python3 apps/dev_control_plane_ai_smoke.py
python3 apps/dev_control_plane_target_smoke.py
python3 apps/dev_control_plane_target_remote_source_smoke.py
python3 apps/dev_control_plane_target_workflow_smoke.py
python3 apps/dev_control_plane_practical_cockpit_smoke.py
python3 apps/dev_control_plane_real_codex_gate_smoke.py
python3 apps/dev_control_plane_real_codex_ui_smoke.py
python3 apps/dev_control_plane_run_timeline_smoke.py
python3 apps/dev_control_plane_openai_diagnostics_smoke.py
python3 apps/dev_control_plane_secrets_smoke.py
python3 apps/dev_control_plane_task_flow_smoke.py
python3 apps/dev_control_plane_codex_observability_smoke.py
python3 apps/dev_control_plane_codex_runtime_parity_smoke.py
python3 apps/dev_control_plane_target_docs_mcp_smoke.py
python3 apps/dev_control_plane_resume_production_deploy_smoke.py
git diff --check
```

These smokes must not call the real OpenAI API or execute real Codex. OpenAI diagnostics are stubbed/sanitized; Codex gate/UI/timeline/observability smokes use fake execution.

## Run Safe Fake-Flow

Use the local cockpit action `Тестовый прогон без Codex`, or run the runner fake path against a frozen TaskSpec. Safe fake-flow creates local artifacts only and does not mutate target repos.

## Run Managed Codex UI Flow

1. Start the cockpit.
2. Select a target profile such as `wb-core`.
3. Prepare and freeze a bounded task.
4. Confirm `Запустить Codex безопасно`.
5. Inspect `Ход выполнения`, `Результат выполнения` and `/runs/live`.

The run uses a managed clone and review artifacts. It does not commit, push, merge, deploy or mutate the original target repo.

## Inspect Run Artifacts

Run artifacts are written under the selected state directory, normally under `runs/<run_id>/`. Inspect prompt, handoff, diff, sanitized terminal log, raw event log, timeline, environment parity and verifier output from the cockpit, live monitor, MCP read tools or the corresponding state path.

## GitHub Closure And Production Lane Checks

For this repo, use the GitHub closure decision gate before self-merge work:

```bash
python3 apps/dev_control_plane_runner.py github-closure-decision --help
gh auth status -h github.com
git diff --check
git diff --cached --check
```

For `wb-core` production-capable target work, the production lane is explicit and gated. Generic target workflow remains decision-only unless that lane is requested and all verifier/rollback/secrets/GitHub/SSH/PR/deploy gates pass.
