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
    dns: dict[str, list[str]]
    cert_domains: list[str]
    remote: dict[str, Any]


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
    return 0 if result.status == "passed" else 1


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
        payload["status"] = "dry_run_passed" if validation.status == "passed" else "dry_run_blocked"
        payload["planned_commands"] = _planned_remote_steps(validation.cert_domains)
        _print_json(payload)
        return 0 if validation.status == "passed" else 1

    if validation.status != "passed":
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
    dns = {PRIMARY_DOMAIN: [], WWW_DOMAIN: []}
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
        dns = _resolve_domains((PRIMARY_DOMAIN, WWW_DOMAIN))
        primary_ips = dns.get(PRIMARY_DOMAIN, [])
        if primary_ips != [TARGET_HOST_IP]:
            blockers.append(f"DNS {PRIMARY_DOMAIN} must point only to {TARGET_HOST_IP}; got {primary_ips or ['<empty>']}")
        else:
            cert_domains.append(PRIMARY_DOMAIN)
        www_ips = dns.get(WWW_DOMAIN, [])
        if www_ips == [TARGET_HOST_IP]:
            cert_domains.append(WWW_DOMAIN)
        else:
            warnings.append(f"DNS {WWW_DOMAIN} is not clean for {TARGET_HOST_IP}; www will not be included in cert")
        remote = _remote_preflight(blockers)

    if not cert_domains and not offline:
        blockers.append("no DNS-clean certificate domains are available")
    status = "passed" if not blockers else "blocked"
    return ValidationResult(status=status, blockers=blockers, warnings=warnings, dns=dns, cert_domains=cert_domains, remote=remote)


def _remote_preflight(blockers: list[str]) -> dict[str, Any]:
    command = r"""set -e
printf 'nginx=%s\n' "$(command -v nginx || true)"
printf 'certbot=%s\n' "$(command -v certbot || true)"
printf 'rsync=%s\n' "$(command -v rsync || true)"
printf 'python3=%s\n' "$(command -v python3 || true)"
printf 'wb_ai_site=%s\n' "$(test -e /etc/nginx/sites-enabled/wb-ai && echo present || echo missing)"
ss -ltnp 2>/dev/null | grep -E ':(8770|8765|8000)' || true
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
    if ":8770" in joined and "dev-control-plane" not in joined:
        blockers.append("port 8770 is already in use by another process")
    return remote


def _deploy_live(cert_domains: Sequence[str]) -> None:
    _run(["rsync", "-a", "--delete", *(_rsync_excludes()), f"{ROOT}/", f"{SSH_ALIAS}:{APP_DIR}/"])
    _ssh_checked(_remote_install_script(cert_domains))
    loopback = _ssh(f"curl -fsS http://{LOOPBACK_HOST}:{LOOPBACK_PORT}/api/state")
    if loopback.returncode != 0:
        raise RuntimeError("loopback probe failed after deploy")


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
curl -fsS http://127.0.0.1:8770/api/state >/dev/null
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


def _resolve_domains(domains: Sequence[str]) -> dict[str, list[str]]:
    resolved: dict[str, list[str]] = {}
    for domain in domains:
        try:
            infos = socket.getaddrinfo(domain, 443, type=socket.SOCK_STREAM)
            resolved[domain] = sorted({item[4][0] for item in infos})
        except socket.gaierror:
            resolved[domain] = []
    return resolved


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
