"""Smoke-check hosted deploy runner without SSH, root or live deploy."""

from __future__ import annotations

import json
import importlib.util
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "apps" / "dev_control_plane_hosted_deploy.py"
TARGET = "89.191.226.88"
OLD = "95.163.244.138"
DOMAINS = ("devcontrol.pro", "www.devcontrol.pro")


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
    if validation.get("status") not in {"passed", "allowed_with_warning"}:
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

    _assert_dns_gate_matrix()

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


def _assert_dns_gate_matrix() -> None:
    deploy = _load_deploy_module()
    local_stale = _local_dns(OLD)
    doh_clean = _doh_dns(TARGET)
    remote_clean = _remote_dns(TARGET)

    allowed = deploy._evaluate_dns_gate(local_stale, doh_clean, remote_clean)
    if allowed.status != "allowed_with_warning" or allowed.blockers:
        raise AssertionError(f"local stale with clean DoH/remote must be allowed with warning: {allowed}")
    if not any("local DNS stale" in warning for warning in allowed.warnings):
        raise AssertionError(f"local stale warning must be explicit: {allowed}")

    remote_stale = deploy._evaluate_dns_gate(local_stale, doh_clean, _remote_dns(OLD))
    if remote_stale.status != "blocked" or not any("remote DNS" in blocker for blocker in remote_stale.blockers):
        raise AssertionError(f"remote stale DNS must block: {remote_stale}")

    doh_stale = deploy._evaluate_dns_gate(local_stale, _doh_dns(OLD), remote_clean)
    if doh_stale.status != "blocked" or not any("DoH" in blocker for blocker in doh_stale.blockers):
        raise AssertionError(f"DoH stale DNS must block: {doh_stale}")

    unavailable = deploy._evaluate_dns_gate(local_stale, doh_clean, {"returncode": 1, "domains": {}, "stderr": "ssh failed"})
    if unavailable.status != "blocked" or not any("remote DNS probe unavailable" in blocker for blocker in unavailable.blockers):
        raise AssertionError(f"remote DNS probe unavailable must block: {unavailable}")


def _load_deploy_module():
    spec = importlib.util.spec_from_file_location("dev_control_plane_hosted_deploy", RUNNER)
    if spec is None or spec.loader is None:
        raise AssertionError("cannot load deploy runner module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[str(spec.name)] = module
    spec.loader.exec_module(module)
    return module


def _local_dns(ip: str) -> dict:
    return {domain: {"system": [ip], "default_dig": [ip]} for domain in DOMAINS}


def _doh_dns(ip: str) -> dict:
    return {domain: {"cloudflare": [ip], "google": [ip]} for domain in DOMAINS}


def _remote_dns(ip: str) -> dict:
    return {
        "returncode": 0,
        "domains": {domain: {"getent_ahostsv4": [ip], "dig": [ip]} for domain in DOMAINS},
    }


if __name__ == "__main__":
    main()
