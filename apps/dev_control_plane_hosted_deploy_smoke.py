"""Smoke-check hosted deploy runner without SSH, root or live deploy."""

from __future__ import annotations

import json
import importlib.util
from pathlib import Path
from contextlib import redirect_stdout
import io
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
    for token in ("rsync repo", "systemd", "nginx", "LetsEncrypt", "control probe", "provision hosted toolchain"):
        if token not in commands:
            raise AssertionError(f"dry-run plan missing token {token!r}: {dry_run}")

    rollback = _run("rollback-plan")
    rollback_commands = "\n".join(rollback.get("rollback_commands", []))
    if "wb-ai" in rollback_commands or "wb-core" in rollback_commands:
        raise AssertionError(f"rollback plan must not touch WebCore paths/services: {rollback}")

    _assert_dns_gate_matrix()
    _assert_port_ownership_matrix()
    _assert_loopback_retry_script()
    _assert_hosted_toolchain_provisioning()
    _assert_mcp_public_route()
    _assert_denied_preflight_blocks_live_steps()

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


def _assert_port_ownership_matrix() -> None:
    deploy = _load_deploy_module()
    free = deploy._evaluate_port_8770_ownership([
        "service_active=inactive",
        "service_main_pid=0",
        "service_loopback_status=unavailable",
    ])
    if free.status != "free" or free.blockers:
        raise AssertionError(f"free port must not block deploy: {free}")

    own = deploy._evaluate_port_8770_ownership([
        "service_active=active",
        "service_main_pid=123",
        "service_loopback_status=ok",
        "service_loopback_runtime_profile=hosted",
        "service_loopback_host=127.0.0.1",
        "service_loopback_port=8770",
        "service_loopback_state_dir=/opt/dev-control-plane-runtime/state",
        'PORT_8770 LISTEN 0 5 127.0.0.1:8770 0.0.0.0:* users:(("python3",pid=123,fd=3))',
    ])
    if own.status != "allowed_existing_service" or own.blockers:
        raise AssertionError(f"own service on port 8770 must allow idempotent deploy: {own}")

    own_by_loopback = deploy._evaluate_port_8770_ownership([
        "service_active=active",
        "service_main_pid=0",
        "service_loopback_status=ok",
        "service_loopback_runtime_profile=hosted",
        "service_loopback_host=127.0.0.1",
        "service_loopback_port=8770",
        "service_loopback_state_dir=/opt/dev-control-plane-runtime/state",
        'PORT_8770 LISTEN 0 5 127.0.0.1:8770 0.0.0.0:* users:(("python3",pid=999,fd=3))',
    ])
    if own_by_loopback.status != "allowed_existing_service" or own_by_loopback.blockers:
        raise AssertionError(f"hosted loopback state must allow own existing service: {own_by_loopback}")

    foreign = deploy._evaluate_port_8770_ownership([
        "service_active=inactive",
        "service_main_pid=0",
        "service_loopback_status=unavailable",
        'PORT_8770 LISTEN 0 5 127.0.0.1:8770 0.0.0.0:* users:(("python3",pid=999,fd=3))',
    ])
    if foreign.status != "blocked" or not any("port 8770" in blocker for blocker in foreign.blockers):
        raise AssertionError(f"foreign listener on port 8770 must block deploy: {foreign}")


def _assert_loopback_retry_script() -> None:
    deploy = _load_deploy_module()
    script = deploy._remote_loopback_wait_script()
    if "for attempt in $(seq 1 60)" not in script or "--max-time 10" not in script:
        raise AssertionError(f"loopback wait must retry with a warmup-safe timeout, not use a single curl: {script}")
    if "/mcp" not in script:
        raise AssertionError(f"loopback wait must use the lightweight MCP status endpoint: {script}")
    if "systemctl --no-pager --plain status dev-control-plane.service" not in script:
        raise AssertionError(f"loopback wait failure must expose service status: {script}")


def _assert_mcp_public_route() -> None:
    deploy = _load_deploy_module()
    script = deploy._remote_install_script(("devcontrol.pro", "www.devcontrol.pro"))
    expected_public_locations = (
        "location = /mcp",
        "location = /mcp/stream",
        "location = /.well-known/oauth-protected-resource",
        "location = /.well-known/oauth-protected-resource/mcp",
        "location = /.well-known/oauth-authorization-server",
        "location = /.well-known/openid-configuration",
        "location = /oauth/register",
        "location = /oauth/token",
    )
    for location in expected_public_locations:
        if location not in script:
            raise AssertionError(f"dev-control-plane nginx config missing public OAuth/MCP location: {location}")
    if script.count("auth_basic off;") < len(expected_public_locations):
        raise AssertionError("OAuth discovery/register/token and MCP endpoints must be explicit no-auth exceptions")
    if "location = /oauth/authorize" in script:
        raise AssertionError("OAuth authorize endpoint must inherit Basic Auth user gate")
    if "location = /runs/live" in script or "location = /api/runs/live" in script:
        raise AssertionError("live monitor routes must inherit Basic Auth and must not be public no-auth exceptions")
    if "location / {" not in script or 'auth_basic "Development Control Plane";' not in script:
        raise AssertionError("main dev-control-plane UI must remain behind Basic Auth")
    if "/etc/nginx/sites-enabled/wb-ai" in script:
        raise AssertionError("dev-control-plane nginx install script must not edit WebCore nginx site")


def _assert_hosted_toolchain_provisioning() -> None:
    deploy = _load_deploy_module()
    script = deploy._remote_install_script(("devcontrol.pro", "www.devcontrol.pro"))
    required_tokens = (
        "/opt/dev-control-plane-runtime/tools/bin/gh",
        "/opt/dev-control-plane-runtime/secrets",
        "chmod 700 /opt/dev-control-plane-runtime/secrets",
        "DEV_CONTROL_PLANE_TOOLCHAIN_BIN_DIR=/opt/dev-control-plane-runtime/tools/bin",
        "PATH=/opt/dev-control-plane-runtime/tools/bin:",
        "apt-get download gh",
        "dpkg-deb -x",
    )
    for token in required_tokens:
        if token not in script:
            raise AssertionError(f"hosted deploy script must provision runtime-local gh token {token!r}")
    forbidden_tokens = ("curl |", "curl -fsSL", "gh auth login", "GITHUB_TOKEN")
    for token in forbidden_tokens:
        if token in script:
            raise AssertionError(f"hosted deploy script must not use unsafe GitHub CLI provisioning/auth token {token!r}")


def _assert_denied_preflight_blocks_live_steps() -> None:
    deploy = _load_deploy_module()
    calls: list[str] = []
    original_validate = deploy._validate_safety
    original_deploy_live = deploy._deploy_live

    class Args:
        dry_run = False
        live = True
        offline = False

    try:
        deploy._validate_safety = lambda *, offline=False: deploy.ValidationResult(
            status="blocked",
            blockers=["port 8770 is already in use by another process"],
            warnings=[],
            dns={},
            cert_domains=[],
            remote={},
        )
        deploy._deploy_live = lambda cert_domains: calls.append("deploy_live")
        with redirect_stdout(io.StringIO()):
            rc = deploy._handle_deploy(Args())
    finally:
        deploy._validate_safety = original_validate
        deploy._deploy_live = original_deploy_live

    if rc == 0 or calls:
        raise AssertionError("blocked preflight must not run live nginx/TLS/deploy steps")


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
