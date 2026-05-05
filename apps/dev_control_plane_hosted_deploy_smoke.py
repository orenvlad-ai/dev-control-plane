"""Smoke-check hosted deploy runner without SSH, root or live deploy."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "apps" / "dev_control_plane_hosted_deploy.py"


def main() -> None:
    plan = _run("print-plan")
    plan_payload = plan.get("plan") or {}
    if plan_payload.get("target_host_ip") != "89.191.226.88":
        raise AssertionError(f"deploy plan must target active host only: {plan}")
    if plan_payload.get("ssh_alias") != "wb-core-eu-root":
        raise AssertionError(f"deploy plan must use approved SSH alias: {plan}")
    if plan_payload.get("service_name") != "dev-control-plane.service":
        raise AssertionError(f"deploy plan must use isolated service: {plan}")
    if plan_payload.get("loopback") != "127.0.0.1:8770":
        raise AssertionError(f"deploy plan must use isolated loopback: {plan}")
    forbidden_paths = "\n".join(plan_payload.get("forbidden_paths", []))
    if "/opt/wb-core-runtime" not in forbidden_paths or "/etc/nginx/sites-enabled/wb-ai" not in forbidden_paths:
        raise AssertionError(f"deploy plan must pin forbidden WebCore paths: {plan}")
    if "basic auth" not in str(plan_payload.get("auth_boundary", "")):
        raise AssertionError(f"deploy plan must include auth boundary: {plan}")

    validation = _run("validate", "--offline")
    if validation.get("status") != "passed":
        raise AssertionError(f"offline validation must pass for smoke: {validation}")
    if validation.get("validation", {}).get("remote", {}).get("skipped") is not True:
        raise AssertionError(f"offline validation must skip SSH: {validation}")

    dry_run = _run("deploy", "--dry-run", "--offline")
    if dry_run.get("status") != "dry_run_passed" or dry_run.get("live_executed") is not False:
        raise AssertionError(f"dry-run must not execute live deploy: {dry_run}")
    commands = "\n".join(dry_run.get("planned_commands", []))
    for token in ("rsync repo", "systemd", "nginx", "LetsEncrypt", "control probe"):
        if token not in commands:
            raise AssertionError(f"dry-run plan missing token {token!r}: {dry_run}")

    rollback = _run("rollback-plan")
    rollback_commands = "\n".join(rollback.get("rollback_commands", []))
    if "wb-ai" in rollback_commands or "wb-core" in rollback_commands:
        raise AssertionError(f"rollback plan must not touch WebCore paths/services: {rollback}")

    print("dev-control-plane-hosted-deploy-smoke passed")


def _run(*args: str) -> dict:
    completed = subprocess.run(
        [sys.executable, str(RUNNER), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise AssertionError(f"deploy runner {' '.join(args)} failed\nstdout={completed.stdout}\nstderr={completed.stderr}")
    return json.loads(completed.stdout)


if __name__ == "__main__":
    main()
