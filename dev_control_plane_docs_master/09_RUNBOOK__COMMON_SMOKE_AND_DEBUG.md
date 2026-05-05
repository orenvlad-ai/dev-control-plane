# Common Smoke And Debug Runbook

## Start The Cockpit

```bash
python3 apps/dev_control_plane_server.py --host 127.0.0.1 --port 8765
```

The server is local-only and refuses non-`127.0.0.1` binds.

## Set Up OpenAI Secret

```bash
python3 apps/dev_control_plane_setup.py openai
python3 apps/dev_control_plane_setup.py status
```

The key is entered in the terminal and stored outside this repo. Do not enter API keys into the browser UI and do not commit local secret files.

## Check Codex Login

```bash
codex --login
codex --version
```

Use terminal-only Codex auth. The cockpit does not collect Codex credentials.

## Run Smokes

```bash
python3 apps/dev_control_plane_smoke.py
python3 apps/dev_control_plane_cli_smoke.py
python3 apps/dev_control_plane_server_smoke.py
python3 apps/dev_control_plane_runner_smoke.py
python3 apps/dev_control_plane_ai_smoke.py
python3 apps/dev_control_plane_target_smoke.py
python3 apps/dev_control_plane_practical_cockpit_smoke.py
python3 apps/dev_control_plane_real_codex_gate_smoke.py
python3 apps/dev_control_plane_real_codex_ui_smoke.py
python3 apps/dev_control_plane_openai_diagnostics_smoke.py
python3 apps/dev_control_plane_secrets_smoke.py
python3 apps/dev_control_plane_task_flow_smoke.py
python3 apps/dev_control_plane_run_timeline_smoke.py
python3 -m py_compile apps/*.py src/dev_control_plane/*.py
git diff --check
```

These smokes must not call the real OpenAI API or execute real Codex. OpenAI diagnostics are stubbed/sanitized; Codex gate/UI smokes use fake execution.

## Run Safe Fake-Flow

Use the local cockpit action `Тестовый прогон без Codex`, or run the runner fake path against a frozen TaskSpec. Safe fake-flow creates local artifacts only and does not mutate target repos.

## Run Managed Codex UI Flow

1. Start the cockpit.
2. Select a target profile such as `wb-core`.
3. Prepare and freeze a bounded task.
4. Confirm `Запустить Codex безопасно`.
5. Inspect the job timeline and result summary.

The run uses a managed clone and review artifacts. It does not commit, push, merge, deploy or mutate the original target repo.

## Inspect Run Artifacts

Run artifacts are written under the selected state directory. Inspect prompt, handoff, diff, logs and verifier output from cockpit `Технические детали` or the corresponding state path.
