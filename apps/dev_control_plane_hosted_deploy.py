"""Hosted dev-control-plane deploy runner with safety-first gates."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import socket
import subprocess
import sys
from typing import Any, Sequence
from urllib import error as urllib_error, request as urllib_request

ROOT = Path(__file__).resolve().parents[1]

TARGET_HOST_IP = "89.191.226.88"
SSH_ALIAS = "wb-core-eu-root"
FORBIDDEN_HOST_IP = "178.72.152.177"
PRIMARY_DOMAIN = "devcontrol.pro"
WWW_DOMAIN = "www.devcontrol.pro"
APP_DIR = Path("/opt/dev-control-plane-runtime/app")
RUNTIME_ROOT = Path("/opt/dev-control-plane-runtime")
STATE_DIR = RUNTIME_ROOT / "state"
ENV_FILE = RUNTIME_ROOT / ".env"
AUTH_FILE = Path("/etc/nginx/dev-control-plane.htpasswd")
SERVICE_NAME = "dev-control-plane.service"
LOOPBACK_HOST = "127.0.0.1"
LOOPBACK_PORT = 8770
NGINX_SITE_AVAILABLE = Path("/etc/nginx/sites-available/dev-control-plane")
NGINX_SITE_ENABLED = Path("/etc/nginx/sites-enabled/dev-control-plane")
WEBCORE_RUNTIME_DIR = Path("/opt/wb-core-runtime")
WEBCORE_ENV = Path("/opt/wb-ai/.env")
WEBCORE_NGINX_SITE = Path("/etc/nginx/sites-enabled/wb-ai")
WEBCORE_SERVICES = {"wb-core-registry-http.service", "wb-ai-api.service"}
FORBIDDEN_PORTS = {8765, 8000}
CERTBOT_EMAIL = "admin@devcontrol.pro"


@dataclass(frozen=True)
class DeployPlan:
    target_host_ip: str
    ssh_alias: str
    app_dir: str
    state_dir: str
    env_file: str
    service_name: str
    loopback: str
    domains: list[str]
    nginx_site_available: str
    nginx_site_enabled: str
    auth_boundary: str
    public_route_default: str
    forbidden_paths: list[str]
    forbidden_services: list[str]
    forbidden_ports: list[int]
    steps: list[str]


@dataclass(frozen=True)
class ValidationResult:
    status: str
    blockers: list[str]
    warnings: list[str]
    dns: dict[str, Any]
    cert_domains: list[str]
    remote: dict[str, Any]


@dataclass(frozen=True)
class DnsGateResult:
    status: str
    blockers: list[str]
    warnings: list[str]
    cert_domains: list[str]


@dataclass(frozen=True)
class PortOwnershipResult:
    status: str
    blockers: list[str]
    warnings: list[str]
    details: dict[str, Any]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Hosted dev-control-plane deploy runner.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    print_plan = subparsers.add_parser("print-plan")
    print_plan.set_defaults(handler=_handle_print_plan)

    validate = subparsers.add_parser("validate")
    validate.add_argument("--offline", action="store_true", help="Skip DNS and SSH checks for local smoke coverage.")
    validate.set_defaults(handler=_handle_validate)

    deploy = subparsers.add_parser("deploy")
    mode = deploy.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--live", action="store_true")
    deploy.add_argument("--offline", action="store_true", help="Dry-run only: skip DNS and SSH checks.")
    deploy.set_defaults(handler=_handle_deploy)

    loopback = subparsers.add_parser("loopback-probe")
    loopback.set_defaults(handler=_handle_loopback_probe)

    public = subparsers.add_parser("public-probe")
    public.add_argument("--url", default=f"https://{PRIMARY_DOMAIN}")
    public.set_defaults(handler=_handle_public_probe)

    webcore = subparsers.add_parser("webcore-probe")
    webcore.add_argument("--url", default="https://api.selleros.pro")
    webcore.set_defaults(handler=_handle_webcore_probe)

    rollback = subparsers.add_parser("rollback-plan")
    rollback.set_defaults(handler=_handle_rollback_plan)

    args = parser.parse_args(argv)
    return int(args.handler(args))


def _handle_print_plan(_: argparse.Namespace) -> int:
    _print_json({"status": "planned", "plan": asdict(_plan())})
    return 0


def _handle_validate(args: argparse.Namespace) -> int:
    result = _validate_safety(offline=args.offline)
    _print_json({"status": result.status, "validation": asdict(result)})
    return 0 if _validation_allows_live(result.status) else 1


def _handle_deploy(args: argparse.Namespace) -> int:
    if args.offline and args.live:
        _print_json({"status": "blocked", "blockers": ["--offline is allowed only with --dry-run"]})
        return 1

    validation = _validate_safety(offline=args.offline)
    payload: dict[str, Any] = {
        "validation": asdict(validation),
        "plan": asdict(_plan()),
        "live_executed": False,
    }
    if args.dry_run:
        payload["status"] = "dry_run_passed" if _validation_allows_live(validation.status) else "dry_run_blocked"
        payload["planned_commands"] = _planned_remote_steps(validation.cert_domains)
        _print_json(payload)
        return 0 if _validation_allows_live(validation.status) else 1

    if not _validation_allows_live(validation.status):
        payload["status"] = "blocked"
        payload["blockers"] = validation.blockers
        _print_json(payload)
        return 1

    try:
        _deploy_live(validation.cert_domains)
    except RuntimeError as exc:
        payload["status"] = "failed"
        payload["blockers"] = [str(exc)]
        _print_json(payload)
        return 1
    payload["status"] = "deployed"
    payload["live_executed"] = True
    _print_json(payload)
    return 0


def _handle_loopback_probe(_: argparse.Namespace) -> int:
    command = f"curl -fsS http://{LOOPBACK_HOST}:{LOOPBACK_PORT}/api/state"
    completed = _ssh(command)
    if completed.returncode != 0:
        _print_json({"status": "failed", "probe": "loopback", "stderr": completed.stderr.strip()})
        return 1
    state = json.loads(completed.stdout)
    ok = (
        state.get("runtime_profile") == "hosted"
        and state.get("host") == LOOPBACK_HOST
        and state.get("port") == LOOPBACK_PORT
        and state.get("state_dir") == str(STATE_DIR)
    )
    _print_json({"status": "passed" if ok else "failed", "probe": "loopback", "state": state})
    return 0 if ok else 1


def _handle_public_probe(args: argparse.Namespace) -> int:
    status, headers = _http_status(args.url)
    ok = status in {200, 401, 403}
    _print_json(
        {
            "status": "passed" if ok else "failed",
            "probe": "public",
            "url": args.url,
            "http_status": status,
            "auth_boundary_observed": status in {401, 403},
            "server": headers.get("server"),
        }
    )
    return 0 if ok else 1


def _handle_webcore_probe(args: argparse.Namespace) -> int:
    status, headers = _http_status(args.url)
    ok = status in {200, 301, 302, 401, 403, 404}
    _print_json({"status": "passed" if ok else "failed", "probe": "webcore", "url": args.url, "http_status": status, "server": headers.get("server")})
    return 0 if ok else 1


def _handle_rollback_plan(_: argparse.Namespace) -> int:
    _print_json(
        {
            "status": "planned",
            "rollback_commands": [
                f"systemctl stop {SERVICE_NAME}",
                f"systemctl disable {SERVICE_NAME}",
                f"rm -f /etc/systemd/system/{SERVICE_NAME}",
                f"rm -f {NGINX_SITE_ENABLED}",
                f"rm -f {NGINX_SITE_AVAILABLE}",
                "nginx -t && systemctl reload nginx",
                "systemctl daemon-reload",
            ],
            "notes": [
                "Do not remove /opt/dev-control-plane-runtime/state without an explicit data-retention decision.",
                "Do not change /etc/nginx/sites-enabled/wb-ai or WebCore services.",
            ],
        }
    )
    return 0


def _plan() -> DeployPlan:
    return DeployPlan(
        target_host_ip=TARGET_HOST_IP,
        ssh_alias=SSH_ALIAS,
        app_dir=str(APP_DIR),
        state_dir=str(STATE_DIR),
        env_file=str(ENV_FILE),
        service_name=SERVICE_NAME,
        loopback=f"{LOOPBACK_HOST}:{LOOPBACK_PORT}",
        domains=[PRIMARY_DOMAIN, WWW_DOMAIN],
        nginx_site_available=str(NGINX_SITE_AVAILABLE),
        nginx_site_enabled=str(NGINX_SITE_ENABLED),
        auth_boundary=f"nginx basic auth via {AUTH_FILE}",
        public_route_default="HTTPS only after certbot; HTTP redirects after certificate installation",
        forbidden_paths=[str(WEBCORE_RUNTIME_DIR), str(WEBCORE_ENV), str(WEBCORE_NGINX_SITE)],
        forbidden_services=sorted(WEBCORE_SERVICES),
        forbidden_ports=sorted(FORBIDDEN_PORTS),
        steps=[
            "validate DNS, host, paths, services, ports and auth boundary",
            "sync repo code to isolated app dir",
            "write non-secret hosted environment file",
            "install isolated systemd unit",
            "restart dev-control-plane.service",
            "probe loopback service",
            "write separate nginx site with auth boundary",
            "obtain LetsEncrypt certificate when DNS is clean",
            "reload nginx and run protected public probe",
            "probe WebCore public URL remains reachable",
        ],
    )


def _validate_safety(*, offline: bool = False) -> ValidationResult:
    blockers: list[str] = []
    warnings: list[str] = []
    dns: dict[str, Any] = {
        "local": {},
        "doh": {},
        "remote": {},
        "gate": "not_checked",
    }
    cert_domains: list[str] = []

    if TARGET_HOST_IP == FORBIDDEN_HOST_IP:
        blockers.append("target host is the forbidden old server")
    if SSH_ALIAS != "wb-core-eu-root":
        blockers.append(f"unexpected SSH alias: {SSH_ALIAS}")
    if _path_is_relative_to(APP_DIR, WEBCORE_RUNTIME_DIR) or _path_is_relative_to(STATE_DIR, WEBCORE_RUNTIME_DIR):
        blockers.append("dev-control-plane paths must not be inside /opt/wb-core-runtime")
    if ENV_FILE == WEBCORE_ENV:
        blockers.append("env file collides with WebCore env")
    if NGINX_SITE_ENABLED == WEBCORE_NGINX_SITE:
        blockers.append("nginx site collides with WebCore site")
    if SERVICE_NAME in WEBCORE_SERVICES:
        blockers.append("service name collides with WebCore service")
    if LOOPBACK_PORT in FORBIDDEN_PORTS:
        blockers.append(f"loopback port collides with reserved WebCore/owner port: {LOOPBACK_PORT}")
    if LOOPBACK_HOST != "127.0.0.1":
        blockers.append("loopback host must remain 127.0.0.1")

    if offline:
        cert_domains = [PRIMARY_DOMAIN, WWW_DOMAIN]
        warnings.append("offline validation skipped DNS and SSH checks")
        remote: dict[str, Any] = {"skipped": True}
    else:
        local_dns = _local_dns_probe((PRIMARY_DOMAIN, WWW_DOMAIN))
        doh_dns = _doh_dns_probe((PRIMARY_DOMAIN, WWW_DOMAIN))
        remote = _remote_preflight(blockers, warnings)
        remote_dns = _remote_dns_probe()
        dns_gate = _evaluate_dns_gate(local_dns, doh_dns, remote_dns)
        blockers.extend(dns_gate.blockers)
        warnings.extend(dns_gate.warnings)
        cert_domains = dns_gate.cert_domains
        dns = {
            "local": local_dns,
            "doh": doh_dns,
            "remote": remote_dns.get("domains", {}),
            "gate": dns_gate.status,
        }
        remote["dns_probe"] = remote_dns

    if not cert_domains and not offline and not any("DNS" in blocker or "DoH" in blocker or "remote DNS" in blocker for blocker in blockers):
        blockers.append("no DNS-clean certificate domains are available")
    status = "passed" if not blockers else "blocked"
    if not blockers and warnings:
        status = "allowed_with_warning"
    return ValidationResult(status=status, blockers=blockers, warnings=warnings, dns=dns, cert_domains=cert_domains, remote=remote)


def _remote_preflight(blockers: list[str], warnings: list[str]) -> dict[str, Any]:
    command = r"""set -e
printf 'nginx=%s\n' "$(command -v nginx || true)"
printf 'certbot=%s\n' "$(command -v certbot || true)"
printf 'rsync=%s\n' "$(command -v rsync || true)"
printf 'python3=%s\n' "$(command -v python3 || true)"
printf 'wb_ai_site=%s\n' "$(test -e /etc/nginx/sites-enabled/wb-ai && echo present || echo missing)"
printf 'service_active=%s\n' "$(systemctl is-active dev-control-plane.service 2>/dev/null || true)"
printf 'service_main_pid=%s\n' "$(systemctl show -p MainPID --value dev-control-plane.service 2>/dev/null || true)"
state_json="$(curl -fsS --max-time 2 http://127.0.0.1:8770/api/state 2>/dev/null || true)"
if [ -n "$state_json" ]; then
  printf 'service_loopback_status=ok\n'
  printf 'service_loopback_runtime_profile=%s\n' "$(printf '%s' "$state_json" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("runtime_profile", ""))' 2>/dev/null || true)"
  printf 'service_loopback_host=%s\n' "$(printf '%s' "$state_json" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("host", ""))' 2>/dev/null || true)"
  printf 'service_loopback_port=%s\n' "$(printf '%s' "$state_json" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("port", ""))' 2>/dev/null || true)"
  printf 'service_loopback_state_dir=%s\n' "$(printf '%s' "$state_json" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("state_dir", ""))' 2>/dev/null || true)"
else
  printf 'service_loopback_status=unavailable\n'
fi
ss -ltnp 2>/dev/null | grep -E ':(8765|8000)' || true
ss -ltnp 'sport = :8770' 2>/dev/null | tail -n +2 | sed 's/^/PORT_8770 /' || true
"""
    completed = _ssh(command)
    remote = {"returncode": completed.returncode, "stdout": completed.stdout.strip().splitlines(), "stderr": completed.stderr.strip()}
    if completed.returncode != 0:
        blockers.append(f"SSH preflight failed for {SSH_ALIAS}")
        return remote
    joined = "\n".join(remote["stdout"])
    for tool in ("nginx", "certbot", "rsync", "python3"):
        if f"{tool}=" not in joined or any(line == f"{tool}=" for line in remote["stdout"]):
            blockers.append(f"remote tool missing: {tool}")
    if "wb_ai_site=present" not in joined:
        blockers.append("WebCore nginx site marker was not found; refusing to proceed")
    port_ownership = _evaluate_port_8770_ownership(remote["stdout"])
    blockers.extend(port_ownership.blockers)
    warnings.extend(port_ownership.warnings)
    remote["port_8770"] = asdict(port_ownership)
    return remote


def _deploy_live(cert_domains: Sequence[str]) -> None:
    _ssh_checked(f"mkdir -p {APP_DIR}")
    _run(["rsync", "-a", "--delete", *(_rsync_excludes()), f"{ROOT}/", f"{SSH_ALIAS}:{APP_DIR}/"])
    _write_deploy_metadata()
    _ssh_checked(_remote_install_script(cert_domains))
    _ssh_checked(_remote_loopback_wait_script())


def _write_deploy_metadata() -> None:
    commit = _local_git_value("rev-parse", "HEAD") or "unknown"
    branch = _local_git_value("branch", "--show-current") or "unknown"
    script = f"""set -euo pipefail
printf '%s\\n' '{_shell_single_quote(commit)}' > {APP_DIR}/.deploy-commit
printf '%s\\n' '{_shell_single_quote(branch)}' > {APP_DIR}/.deploy-branch
if id -u dev-control-plane >/dev/null 2>&1; then
  chown dev-control-plane:dev-control-plane {APP_DIR}/.deploy-commit {APP_DIR}/.deploy-branch
fi
chmod 640 {APP_DIR}/.deploy-commit {APP_DIR}/.deploy-branch
"""
    _ssh_checked(script)


def _evaluate_port_8770_ownership(lines: Sequence[str]) -> PortOwnershipResult:
    port_lines = [line.removeprefix("PORT_8770 ").strip() for line in lines if line.startswith("PORT_8770 ")]
    service_active = _preflight_value(lines, "service_active")
    service_main_pid = _preflight_value(lines, "service_main_pid")
    loopback_status = _preflight_value(lines, "service_loopback_status")
    loopback_profile = _preflight_value(lines, "service_loopback_runtime_profile")
    loopback_host = _preflight_value(lines, "service_loopback_host")
    loopback_port = _preflight_value(lines, "service_loopback_port")
    loopback_state_dir = _preflight_value(lines, "service_loopback_state_dir")
    details = {
        "service_active": service_active,
        "service_main_pid": service_main_pid,
        "loopback_status": loopback_status,
        "loopback_runtime_profile": loopback_profile,
        "loopback_host": loopback_host,
        "loopback_port": loopback_port,
        "loopback_state_dir": loopback_state_dir,
        "listeners": port_lines,
    }
    if not port_lines:
        return PortOwnershipResult(status="free", blockers=[], warnings=[], details=details)

    main_pid_matches = bool(service_main_pid and service_main_pid != "0" and any(f"pid={service_main_pid}," in line for line in port_lines))
    loopback_matches = (
        loopback_status == "ok"
        and loopback_profile == "hosted"
        and loopback_host == LOOPBACK_HOST
        and loopback_port == str(LOOPBACK_PORT)
        and loopback_state_dir == str(STATE_DIR)
    )
    if service_active == "active" and (main_pid_matches or loopback_matches):
        return PortOwnershipResult(
            status="allowed_existing_service",
            blockers=[],
            warnings=["port 8770 is already served by dev-control-plane.service; continuing idempotent deploy"],
            details=details,
        )

    return PortOwnershipResult(
        status="blocked",
        blockers=["port 8770 is already in use by another process"],
        warnings=[],
        details=details,
    )


def _preflight_value(lines: Sequence[str], key: str) -> str:
    prefix = f"{key}="
    for line in lines:
        if line.startswith(prefix):
            return line.removeprefix(prefix).strip()
    return ""


def _remote_loopback_wait_script() -> str:
    return f"""set -euo pipefail
loopback_ready=0
for attempt in $(seq 1 30); do
  if curl -fsS --max-time 2 http://{LOOPBACK_HOST}:{LOOPBACK_PORT}/api/state >/dev/null; then
    loopback_ready=1
    break
  fi
  sleep 1
done
if [ "$loopback_ready" != "1" ]; then
  systemctl --no-pager --plain status {SERVICE_NAME} >&2 || true
  exit 1
fi
"""


def _remote_install_script(cert_domains: Sequence[str]) -> str:
    domain_args = " ".join(f"-d {domain}" for domain in cert_domains)
    server_names = " ".join(cert_domains)
    if not server_names:
        raise RuntimeError("cert domains must not be empty")
    return f"""set -euo pipefail
id -u dev-control-plane >/dev/null 2>&1 || useradd --system --home-dir {RUNTIME_ROOT} --shell /usr/sbin/nologin dev-control-plane
mkdir -p {APP_DIR} {STATE_DIR} {RUNTIME_ROOT}/auth /var/www/html
chown -R dev-control-plane:dev-control-plane {RUNTIME_ROOT}
chmod 750 {RUNTIME_ROOT}
cat > {ENV_FILE} <<'EOF'
DEV_CONTROL_PLANE_RUNTIME_PROFILE=hosted
DEV_CONTROL_PLANE_HOST=127.0.0.1
DEV_CONTROL_PLANE_PORT=8770
DEV_CONTROL_PLANE_STATE_DIR={STATE_DIR}
DEV_CONTROL_PLANE_SECRET_HOME={RUNTIME_ROOT}/secrets
DEV_CONTROL_PLANE_CODEX_BIN={RUNTIME_ROOT}/tools/codex/bin/codex
DEV_CONTROL_PLANE_OPENAI_TIMEOUT_SECONDS=180
DEV_CONTROL_PLANE_OPENAI_RETRY_COUNT=2
DEV_CONTROL_PLANE_OPENAI_RETRY_BACKOFF_SECONDS=2
HOME={RUNTIME_ROOT}
CODEX_HOME={RUNTIME_ROOT}/.codex
PYTHONDONTWRITEBYTECODE=1
EOF
chown root:dev-control-plane {ENV_FILE}
chmod 640 {ENV_FILE}
if [ ! -s {AUTH_FILE} ]; then
  password="$(openssl rand -base64 32)"
  hash="$(printf '%s\\n' "$password" | openssl passwd -apr1 -stdin)"
  printf 'operator:%s\\n' "$hash" > {AUTH_FILE}
  chown root:www-data {AUTH_FILE} 2>/dev/null || chown root:root {AUTH_FILE}
  chmod 640 {AUTH_FILE}
  printf '%s\\n' "$password" > {RUNTIME_ROOT}/auth/basic-auth-password
  chown root:root {RUNTIME_ROOT}/auth/basic-auth-password
  chmod 600 {RUNTIME_ROOT}/auth/basic-auth-password
fi
cat > /etc/systemd/system/{SERVICE_NAME} <<'EOF'
[Unit]
Description=Development Control Plane cockpit
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=dev-control-plane
Group=dev-control-plane
WorkingDirectory={APP_DIR}
EnvironmentFile={ENV_FILE}
Environment=PYTHONDONTWRITEBYTECODE=1
ExecStart=/usr/bin/python3 {APP_DIR}/apps/dev_control_plane_server.py
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths={RUNTIME_ROOT}

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable {SERVICE_NAME}
systemctl restart {SERVICE_NAME}
{_remote_loopback_wait_script()}
cat > {NGINX_SITE_AVAILABLE} <<'EOF'
server {{
    listen 80;
    server_name {server_names};

    location /.well-known/acme-challenge/ {{
        root /var/www/html;
    }}

    location / {{
        return 404;
    }}
}}
EOF
ln -sfn {NGINX_SITE_AVAILABLE} {NGINX_SITE_ENABLED}
nginx -t
systemctl reload nginx
certbot certonly --webroot -w /var/www/html {domain_args} --non-interactive --agree-tos -m {CERTBOT_EMAIL}
cat > {NGINX_SITE_AVAILABLE} <<'EOF'
server {{
    listen 80;
    server_name {server_names};
    return 301 https://$host$request_uri;
}}

server {{
    listen 443 ssl http2;
    server_name {server_names};

    ssl_certificate /etc/letsencrypt/live/{PRIMARY_DOMAIN}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/{PRIMARY_DOMAIN}/privkey.pem;

    auth_basic "Development Control Plane";
    auth_basic_user_file {AUTH_FILE};

    location / {{
        proxy_pass http://127.0.0.1:8770;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }}
}}
EOF
nginx -t
systemctl reload nginx
systemctl --no-pager --plain status {SERVICE_NAME} >/dev/null
"""


def _planned_remote_steps(cert_domains: Sequence[str]) -> list[str]:
    return [
        f"rsync repo to {SSH_ALIAS}:{APP_DIR}",
        f"create {RUNTIME_ROOT}, {STATE_DIR}, {ENV_FILE}",
        f"write systemd unit /etc/systemd/system/{SERVICE_NAME}",
        f"restart {SERVICE_NAME}",
        f"probe http://{LOOPBACK_HOST}:{LOOPBACK_PORT}/api/state",
        f"write isolated nginx site {NGINX_SITE_AVAILABLE}",
        f"request LetsEncrypt certificate for {list(cert_domains)}",
        "reload nginx",
        f"public probe https://{PRIMARY_DOMAIN}",
        "control probe https://api.selleros.pro",
    ]


def _validation_allows_live(status: str) -> bool:
    return status in {"passed", "allowed_with_warning"}


def _evaluate_dns_gate(local_dns: dict[str, Any], doh_dns: dict[str, Any], remote_dns: dict[str, Any]) -> DnsGateResult:
    blockers: list[str] = []
    warnings: list[str] = []
    cert_domains: list[str] = []

    remote_domains = remote_dns.get("domains", {})
    if remote_dns.get("returncode") != 0:
        blockers.append(f"remote DNS probe unavailable for {SSH_ALIAS}")

    for domain in (PRIMARY_DOMAIN, WWW_DOMAIN):
        local = local_dns.get(domain, {})
        system_ips = _as_list(local.get("system"))
        default_dig_ips = _as_list(local.get("default_dig"))
        if system_ips != [TARGET_HOST_IP] or default_dig_ips != [TARGET_HOST_IP]:
            warnings.append(
                f"local DNS stale for {domain}: system={system_ips or ['<empty>']}, "
                f"default_dig={default_dig_ips or ['<empty>']}"
            )

        doh = doh_dns.get(domain, {})
        for provider in ("cloudflare", "google"):
            ips = _as_list(doh.get(provider))
            if ips != [TARGET_HOST_IP]:
                blockers.append(f"DoH {provider} {domain} must point only to {TARGET_HOST_IP}; got {ips or ['<empty>']}")

        remote = remote_domains.get(domain, {})
        getent_ips = _as_list(remote.get("getent_ahostsv4"))
        if getent_ips != [TARGET_HOST_IP]:
            blockers.append(f"remote DNS getent {domain} must point only to {TARGET_HOST_IP}; got {getent_ips or ['<empty>']}")
        dig_ips = _as_list(remote.get("dig"))
        if dig_ips != ["<dig-missing>"] and dig_ips != [TARGET_HOST_IP]:
            blockers.append(f"remote DNS dig {domain} must point only to {TARGET_HOST_IP}; got {dig_ips or ['<empty>']}")

    if blockers:
        return DnsGateResult(status="blocked", blockers=blockers, warnings=warnings, cert_domains=[])
    cert_domains = [PRIMARY_DOMAIN, WWW_DOMAIN]
    status = "allowed_with_warning" if warnings else "passed"
    return DnsGateResult(status=status, blockers=[], warnings=warnings, cert_domains=cert_domains)


def _local_dns_probe(domains: Sequence[str]) -> dict[str, dict[str, list[str]]]:
    return {
        domain: {
            "system": _system_resolve(domain),
            "default_dig": _dig_resolve(domain),
        }
        for domain in domains
    }


def _doh_dns_probe(domains: Sequence[str]) -> dict[str, dict[str, list[str]]]:
    return {
        domain: {
            "cloudflare": _doh_resolve(domain, "cloudflare"),
            "google": _doh_resolve(domain, "google"),
        }
        for domain in domains
    }


def _system_resolve(domain: str) -> list[str]:
    try:
        return sorted({item[4][0] for item in socket.getaddrinfo(domain, 443, type=socket.SOCK_STREAM)})
    except socket.gaierror:
        return []


def _dig_resolve(domain: str) -> list[str]:
    completed = subprocess.run(["dig", "+time=3", "+tries=1", "+short", domain, "A"], cwd=ROOT, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        return []
    return sorted({line.strip() for line in completed.stdout.splitlines() if line.strip()})


def _doh_resolve(domain: str, provider: str) -> list[str]:
    url = {
        "cloudflare": f"https://cloudflare-dns.com/dns-query?name={domain}&type=A",
        "google": f"https://dns.google/resolve?name={domain}&type=A",
    }[provider]
    completed = subprocess.run(
        ["curl", "-fsS", "--max-time", "10", "-H", "accept: application/dns-json", url],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return []
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return []
    return sorted({item["data"] for item in payload.get("Answer", []) if item.get("type") == 1 and "data" in item})


def _remote_dns_probe() -> dict[str, Any]:
    command = f"""set -u
for domain in {PRIMARY_DOMAIN} {WWW_DOMAIN}; do
  printf 'DOMAIN %s\\n' "$domain"
  printf 'GETENT '
  getent ahostsv4 "$domain" 2>/dev/null | awk '{{print $1}}' | sort -u | tr '\\n' ' '
  printf '\\n'
  if command -v dig >/dev/null 2>&1; then
    printf 'DIG '
    dig +time=3 +tries=1 +short "$domain" A 2>/dev/null | sort -u | tr '\\n' ' '
    printf '\\n'
  else
    printf 'DIG <dig-missing>\\n'
  fi
done
"""
    completed = _ssh(command)
    result = {
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip().splitlines(),
        "stderr": completed.stderr.strip(),
        "domains": {},
    }
    if completed.returncode != 0:
        return result
    result["domains"] = _parse_remote_dns_stdout(result["stdout"])
    return result


def _parse_remote_dns_stdout(lines: Sequence[str]) -> dict[str, dict[str, list[str]]]:
    parsed: dict[str, dict[str, list[str]]] = {}
    current: str | None = None
    for line in lines:
        if line.startswith("DOMAIN "):
            current = line.split(" ", 1)[1].strip()
            parsed[current] = {"getent_ahostsv4": [], "dig": []}
        elif current and line.startswith("GETENT "):
            parsed[current]["getent_ahostsv4"] = _split_ips(line.removeprefix("GETENT "))
        elif current and line.startswith("DIG "):
            parsed[current]["dig"] = _split_ips(line.removeprefix("DIG "))
    return parsed


def _split_ips(raw: str) -> list[str]:
    return sorted({item.strip() for item in raw.split() if item.strip()})


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, tuple):
        return [str(item) for item in value]
    return [str(value)]


def _http_status(url: str) -> tuple[int, dict[str, str]]:
    request = urllib_request.Request(url, method="GET")
    try:
        with urllib_request.urlopen(request, timeout=15) as response:
            return int(response.status), {key.lower(): value for key, value in response.headers.items()}
    except urllib_error.HTTPError as exc:
        return int(exc.code), {key.lower(): value for key, value in exc.headers.items()}
    except urllib_error.URLError as exc:
        return 0, {"error": str(exc.reason)}


def _rsync_excludes() -> list[str]:
    return [
        "--exclude=.git/",
        "--exclude=.env",
        "--exclude=*.env",
        "--exclude=.DS_Store",
        "--exclude=__pycache__/",
        "--exclude=.pytest_cache/",
        "--exclude=state/",
        "--exclude=runs/",
        "--exclude=logs/",
        "--exclude=workspaces/",
        "--exclude=dev_control_plane_docs_master/",
    ]


def _ssh(command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", SSH_ALIAS, command],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _ssh_checked(command: str) -> None:
    completed = _ssh(command)
    if completed.returncode != 0:
        raise RuntimeError(f"remote command failed: {completed.stderr.strip()}")


def _run(command: Sequence[str]) -> None:
    completed = subprocess.run(list(command), cwd=ROOT, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(command)}\n{completed.stderr.strip()}")


def _local_git_value(*args: str) -> str | None:
    completed = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


def _shell_single_quote(value: str) -> str:
    return value.replace("'", "'\"'\"'")


def _path_is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
