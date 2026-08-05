"""Safety-gated hosted rollout for the read-only projection v2 service.

The approved host receives immutable, minimal projection releases.  The Mac
Supervisor remains the only control authority: this runner never provisions
Codex, OpenAI, GitHub, target-production, or SSH credentials for the service.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
from hmac import new as hmac_new
import json
import os
from pathlib import Path
import re
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]

EXPECTED_REPOSITORY = "orenvlad-ai/dev-control-plane"
EXPECTED_ORIGIN_URLS = {
    "https://github.com/orenvlad-ai/dev-control-plane.git",
    "git@github.com:orenvlad-ai/dev-control-plane.git",
    "ssh://git@github.com/orenvlad-ai/dev-control-plane.git",
}
CANONICAL_FETCH_URL = "git@github.com:orenvlad-ai/dev-control-plane.git"
TARGET_HOST_IP = "89.191.226.88"
SSH_ALIAS = "wb-core-eu-root"
TRUSTED_KNOWN_HOSTS_FILE = Path.home() / ".ssh" / "known_hosts"
FORBIDDEN_HOST_IP = "178.72.152.177"
PRIMARY_DOMAIN = "devcontrol.pro"
WWW_DOMAIN = "www.devcontrol.pro"
WEBCORE_PROBE_URL = "https://api.selleros.pro"

RUNTIME_ROOT = Path("/opt/dev-control-plane-runtime")
ROLLOUT_LOCK = RUNTIME_ROOT / ".hosted-rollout.lock"
RELEASES_DIR = RUNTIME_ROOT / "releases"
APP_DIR = RUNTIME_ROOT / "app"
PREVIOUS_LINK = RUNTIME_ROOT / "previous"
CONFIG_DIR = RUNTIME_ROOT / "config"
ENV_FILE = CONFIG_DIR / "projection-v2.env"
PROJECTION_ROOT = RUNTIME_ROOT / "projection"
PROJECTION_STATE_DIR = PROJECTION_ROOT / "state"
PROJECTION_DB = PROJECTION_STATE_DIR / "projection.sqlite3"
PROJECTION_SECRETS_DIR = PROJECTION_ROOT / "secrets"
PROJECTION_KEY_DEST = PROJECTION_SECRETS_DIR / "projection-v2.hmac"
DEFAULT_PROJECTION_KEY_FILE = Path.home() / ".dev-control-plane-v2" / "secrets" / "projection_hmac.key"
LEGACY_STATE_DIR = RUNTIME_ROOT / "state"
ARCHIVE_DIR = RUNTIME_ROOT / "archive"
LEGACY_STATE_MARKER = ARCHIVE_DIR / "legacy-state-v1.READ_ONLY"
LEGACY_APP_ARCHIVE = ARCHIVE_DIR / "legacy-app-v1"

AUTH_FILE = Path("/etc/nginx/dev-control-plane.htpasswd")
SERVICE_NAME = "dev-control-plane.service"
PROJECTION_SERVICE_USER = "dev-control-plane-projection"
PROJECTION_SERVICE_GROUP = "dev-control-plane-projection"
LOOPBACK_HOST = "127.0.0.1"
LOOPBACK_PORT = 8770
NGINX_SITE_AVAILABLE = Path("/etc/nginx/sites-available/dev-control-plane")
NGINX_SITE_ENABLED = Path("/etc/nginx/sites-enabled/dev-control-plane")
ACME_ROOT = Path("/var/www/dev-control-plane-acme")
CERT_LIVE_DIR = Path("/etc/letsencrypt/live/devcontrol.pro")
CERT_FULLCHAIN = CERT_LIVE_DIR / "fullchain.pem"
CERT_PRIVATE_KEY = CERT_LIVE_DIR / "privkey.pem"
CERT_RENEWAL_FILE = Path("/etc/letsencrypt/renewal/devcontrol.pro.conf")
CERT_ARCHIVE_LINEAGE_DIR = Path("/etc/letsencrypt/archive/devcontrol.pro")
CERT_DEPLOY_HOOK = Path("/etc/letsencrypt/renewal-hooks/deploy/dev-control-plane-nginx-reload")
CERTBOT_EMAIL = "admin@devcontrol.pro"
MIN_CERT_DAYS = 21

WEBCORE_RUNTIME_DIR = Path("/opt/wb-core-runtime")
WEBCORE_ENV = Path("/opt/wb-ai/.env")
WEBCORE_NGINX_SITE = Path("/etc/nginx/sites-enabled/wb-ai")
WEBCORE_SERVICES = {"wb-core-registry-http.service", "wb-ai-api.service"}
FORBIDDEN_PORTS = {8765, 8000}

RELEASE_FILES = (
    "apps/dev_control_plane_projection_v2.py",
    "src/dev_control_plane/__init__.py",
    "src/dev_control_plane/projection_server.py",
    "src/dev_control_plane/projection_store.py",
)
SYSTEMD_UNIT_FILE = Path("/etc/systemd/system") / SERVICE_NAME
ROLLOUT_SNAPSHOT_PATHS = (
    APP_DIR,
    PREVIOUS_LINK,
    ENV_FILE,
    SYSTEMD_UNIT_FILE,
    NGINX_SITE_AVAILABLE,
    NGINX_SITE_ENABLED,
    CERT_DEPLOY_HOOK,
    CERT_RENEWAL_FILE,
    CERT_LIVE_DIR,
    CERT_ARCHIVE_LINEAGE_DIR,
    PROJECTION_KEY_DEST,
    LEGACY_STATE_MARKER,
    LEGACY_APP_ARCHIVE,
)
FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SAFE_BRANCH_RE = re.compile(r"^[A-Za-z0-9._/\-]{1,200}$")
TLS_CURL_EXIT_CODES = {35, 51, 53, 58, 59, 60, 64, 66, 77, 80, 82, 83, 90, 91}
SSH_EXEC_OPTIONS = (
    "-o",
    "BatchMode=yes",
    "-o",
    "ConnectTimeout=10",
    "-o",
    f"HostName={TARGET_HOST_IP}",
    "-o",
    "User=root",
    "-o",
    "Port=22",
    "-o",
    "ProxyCommand=none",
    "-o",
    "ProxyJump=none",
    "-o",
    "ControlMaster=no",
    "-o",
    "ControlPath=none",
    "-o",
    "ControlPersist=no",
    "-o",
    "ClearAllForwardings=yes",
    "-o",
    "PermitLocalCommand=no",
    "-o",
    "StrictHostKeyChecking=yes",
    "-o",
    f"UserKnownHostsFile={TRUSTED_KNOWN_HOSTS_FILE}",
    "-o",
    "GlobalKnownHostsFile=/dev/null",
    "-o",
    f"HostKeyAlias={TARGET_HOST_IP}",
)


@dataclass(frozen=True)
class DeployPlan:
    target_host_ip: str
    ssh_alias: str
    expected_repository: str
    releases_dir: str
    current_link: str
    previous_link: str
    projection_database: str
    projection_key_file: str
    legacy_state_archive_marker: str
    env_file: str
    service_name: str
    authority_role: str
    loopback: str
    domains: list[str]
    nginx_site_available: str
    nginx_site_enabled: str
    auth_boundary: str
    public_ingest_exception: str
    forbidden_paths: list[str]
    forbidden_services: list[str]
    forbidden_ports: list[int]
    steps: list[str]


@dataclass(frozen=True)
class SourceGateResult:
    status: str
    enforced: bool
    fetched_origin_main: bool
    exact_repository: bool
    clean: bool
    head_matches_origin_main: bool
    head_sha: str | None
    origin_main_sha: str | None
    branch: str
    blockers: list[str]
    warnings: list[str]


@dataclass(frozen=True)
class ProjectionKeyGateResult:
    status: str
    required: bool
    source: str
    regular_file: bool
    symlink: bool
    owner_matches_process: bool
    mode: str | None
    size_bytes: int | None
    blockers: list[str]
    warnings: list[str]


@dataclass(frozen=True)
class CertificateGateResult:
    status: str
    present: bool
    expires_at: str | None
    days_remaining: int | None
    currently_valid: bool
    fresh_for_21_days: bool
    certbot_timer_enabled: bool
    certbot_timer_active: bool
    acme_route_ready: bool
    renewal_webroot_ready: bool
    deploy_hook_ready: bool
    remediation_reasons: list[str]
    blockers: list[str]


@dataclass(frozen=True)
class ValidationResult:
    status: str
    blockers: list[str]
    warnings: list[str]
    source: SourceGateResult
    projection_key: ProjectionKeyGateResult
    certificate: CertificateGateResult
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


@dataclass(frozen=True)
class CurlProbeResult:
    status: str
    http_status: int
    transport: str
    curl_exit: int


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Hosted projection v2 deploy runner")
    subparsers = parser.add_subparsers(dest="command", required=True)

    print_plan = subparsers.add_parser("print-plan")
    print_plan.set_defaults(handler=_handle_print_plan)

    validate = subparsers.add_parser("validate")
    validate.add_argument("--offline", action="store_true", help="Skip DNS/SSH and report local gates only")
    _add_projection_key_argument(validate)
    validate.set_defaults(handler=_handle_validate)

    deploy = subparsers.add_parser("deploy")
    deploy_mode = deploy.add_mutually_exclusive_group(required=True)
    deploy_mode.add_argument("--dry-run", action="store_true")
    deploy_mode.add_argument("--live", action="store_true")
    deploy.add_argument("--offline", action="store_true", help="Dry-run only: skip DNS and SSH checks")
    _add_projection_key_argument(deploy)
    deploy.set_defaults(handler=_handle_deploy)

    loopback = subparsers.add_parser("loopback-probe")
    loopback.set_defaults(handler=_handle_loopback_probe)

    public = subparsers.add_parser("public-probe")
    public.add_argument("--url", default=f"https://{PRIMARY_DOMAIN}")
    public.set_defaults(handler=_handle_public_probe)

    webcore = subparsers.add_parser("webcore-probe")
    webcore.add_argument("--url", default=WEBCORE_PROBE_URL)
    webcore.set_defaults(handler=_handle_webcore_probe)

    rollback_plan = subparsers.add_parser("rollback-plan")
    rollback_plan.set_defaults(handler=_handle_rollback_plan)

    rollback = subparsers.add_parser("rollback")
    rollback_mode = rollback.add_mutually_exclusive_group(required=True)
    rollback_mode.add_argument("--dry-run", action="store_true")
    rollback_mode.add_argument("--live", action="store_true")
    rollback.set_defaults(handler=_handle_rollback)

    args = parser.parse_args(argv)
    return int(args.handler(args))


def _add_projection_key_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--projection-key-file",
        type=Path,
        help="External 0600 HMAC key; defaults to ~/.dev-control-plane-v2/secrets/projection_hmac.key",
    )


def _handle_print_plan(_: argparse.Namespace) -> int:
    _print_json({"status": "planned", "plan": asdict(_plan())})
    return 0


def _handle_validate(args: argparse.Namespace) -> int:
    enforce_live_gates = not args.offline
    result = _validate_safety(
        offline=args.offline,
        enforce_source=enforce_live_gates,
        require_key=enforce_live_gates,
        projection_key_file=args.projection_key_file,
    )
    _print_json({"status": result.status, "validation": asdict(result)})
    return 0 if _validation_allows_live(result.status) else 1


def _handle_deploy(args: argparse.Namespace) -> int:
    if args.offline and args.live:
        _print_json({"status": "blocked", "blockers": ["offline_live_forbidden"]})
        return 1

    enforce_external_gates = not args.offline
    validation = _validate_safety(
        offline=args.offline,
        enforce_source=enforce_external_gates,
        require_key=enforce_external_gates,
        projection_key_file=args.projection_key_file,
    )
    payload: dict[str, Any] = {
        "validation": asdict(validation),
        "plan": asdict(_plan()),
        "live_executed": False,
    }
    if args.dry_run:
        payload["status"] = "dry_run_passed" if _validation_allows_live(validation.status) else "dry_run_blocked"
        payload["planned_commands"] = _planned_remote_steps(
            validation.cert_domains,
            validation.source.origin_main_sha or "<verified-origin-main-sha>",
        )
        _print_json(payload)
        return 0 if _validation_allows_live(validation.status) else 1

    if not _validation_allows_live(validation.status):
        payload["status"] = "blocked"
        payload["blockers"] = validation.blockers
        _print_json(payload)
        return 1

    head_sha = validation.source.head_sha
    if not head_sha or not FULL_SHA_RE.fullmatch(head_sha):
        payload["status"] = "blocked"
        payload["blockers"] = ["verified_source_sha_unavailable"]
        _print_json(payload)
        return 1

    try:
        proof = _deploy_live(
            cert_domains=validation.cert_domains,
            release_sha=head_sha,
            projection_key_file=_projection_key_path(args.projection_key_file),
            certificate_remediation_reasons=validation.certificate.remediation_reasons,
        )
    except RuntimeError as exc:
        payload["status"] = "failed"
        payload["blockers"] = [str(exc)]
        _print_json(payload)
        return 1
    payload["status"] = "deployed"
    payload["live_executed"] = True
    payload["release_sha"] = head_sha
    payload["proof"] = proof
    _print_json(payload)
    return 0


def _handle_loopback_probe(_: argparse.Namespace) -> int:
    try:
        proof = _remote_loopback_health()
    except RuntimeError as exc:
        _print_json({"status": "failed", "probe": "loopback", "reason_code": str(exc)})
        return 1
    _print_json({"status": "passed", "probe": "loopback", "health": proof})
    return 0


def _handle_public_probe(args: argparse.Namespace) -> int:
    if not _approved_probe_url(args.url, {PRIMARY_DOMAIN, WWW_DOMAIN}):
        _print_json({"status": "blocked", "probe": "public", "reason_code": "unapproved_probe_url"})
        return 1
    result = _curl_probe(args.url)
    # The public UI is never a no-auth success surface. A 200 here would prove
    # that nginx lost the required Basic Auth boundary, not that rollout is
    # healthy.
    ok = result.transport == "ok" and result.http_status in {401, 403}
    _print_json(
        {
            "status": "passed" if ok else "failed",
            "probe": "public",
            "url": args.url,
            "http_status": result.http_status,
            "transport": result.transport,
            "auth_boundary_observed": result.http_status in {401, 403},
        }
    )
    return 0 if ok else 1


def _handle_webcore_probe(args: argparse.Namespace) -> int:
    if not _approved_probe_url(args.url, {"api.selleros.pro"}):
        _print_json({"status": "blocked", "probe": "webcore", "reason_code": "unapproved_probe_url"})
        return 1
    result = _curl_probe(args.url)
    ok = result.transport == "ok" and result.http_status in {200, 301, 302, 401, 403, 404}
    _print_json(
        {
            "status": "passed" if ok else "failed",
            "probe": "webcore",
            "url": args.url,
            "http_status": result.http_status,
            "transport": result.transport,
        }
    )
    return 0 if ok else 1


def _handle_rollback_plan(_: argparse.Namespace) -> int:
    _print_json({"status": "planned", "rollback": _rollback_plan_payload()})
    return 0


def _handle_rollback(args: argparse.Namespace) -> int:
    ssh_target = _local_ssh_target_gate()
    if ssh_target.get("status") != "passed":
        blockers = list(ssh_target.get("blockers") or ())
        _print_json(
            {
                "status": "failed",
                "live_executed": False,
                "blockers": blockers or ["ssh_target_gate_failed"],
            }
        )
        return 1
    transaction_started = False
    proof: dict[str, Any] | None = None
    try:
        eligibility = _remote_rollback_eligibility()
        if eligibility.get("eligible") is False:
            if args.dry_run and eligibility.get("reason_code") == "not_eligible_first_release":
                _print_json(
                    {
                        "status": "dry_run_not_eligible_first_release",
                        "live_executed": False,
                        "rollback": _rollback_plan_payload(),
                        "eligibility": eligibility,
                    }
                )
                return 0
            raise RuntimeError("projection_v2_rollback_not_eligible_first_release")
        if args.dry_run:
            _print_json(
                {
                    "status": "dry_run_passed",
                    "live_executed": False,
                    "rollback": _rollback_plan_payload(),
                    "eligibility": eligibility,
                }
            )
            return 0
        # Re-resolve the approved alias immediately before the mutation.  The
        # remote script also performs an exact current/previous CAS readback.
        repeated_target = _local_ssh_target_gate()
        if repeated_target.get("status") != "passed":
            raise RuntimeError("ssh_target_gate_changed_before_rollback")
        rollback_release = str(eligibility["previous_sha"])
        begin_status = _begin_remote_activation(rollback_release)
        transaction_started = True
        if begin_status != "created":
            recovery = _recover_failed_projection_rollout(rollback_release)
            if recovery == "completed" and proof is not None:
                pass
            elif recovery == "completed":
                proof = _prove_live_read_only(expected_release=rollback_release)
            elif recovery == "restored":
                raise RuntimeError("rollback_existing_transaction_restored")
            elif recovery == "quarantined":
                raise RuntimeError("rollback_existing_transaction_quarantined")
            elif recovery == "not_activated":
                raise RuntimeError("rollback_existing_transaction_not_activated")
            else:
                raise RuntimeError("rollback_existing_transaction_recovery_failed")
        else:
            try:
                _ssh_checked(
                    _remote_rollback_script(
                        expected_current_sha=str(eligibility["current_sha"]),
                        expected_previous_sha=rollback_release,
                    ),
                    operation="projection_v2_rollback",
                )
                proof = _prove_live_read_only(expected_release=rollback_release)
                _complete_remote_activation(rollback_release)
            except RuntimeError as exc:
                recovery = _recover_failed_projection_rollout(rollback_release)
                if recovery == "completed" and proof is not None:
                    pass
                elif recovery == "restored":
                    raise RuntimeError("rollback_failed_prior_host_state_restored") from exc
                elif recovery == "quarantined":
                    raise RuntimeError("rollback_failed_projection_quarantined") from exc
                elif recovery == "not_activated":
                    raise RuntimeError("rollback_failed_before_activation") from exc
                else:
                    raise RuntimeError("rollback_failed_quarantine_failed") from exc
    except RuntimeError as exc:
        _print_json({"status": "failed", "live_executed": False, "blockers": [str(exc)]})
        return 1
    if transaction_started and proof is None:
        _print_json({"status": "failed", "live_executed": False, "blockers": ["rollback_proof_missing"]})
        return 1
    _print_json({"status": "rolled_back", "live_executed": True, "proof": proof})
    return 0


def _plan() -> DeployPlan:
    return DeployPlan(
        target_host_ip=TARGET_HOST_IP,
        ssh_alias=SSH_ALIAS,
        expected_repository=EXPECTED_REPOSITORY,
        releases_dir=str(RELEASES_DIR / "<verified-origin-main-sha>"),
        current_link=str(APP_DIR),
        previous_link=str(PREVIOUS_LINK),
        projection_database=str(PROJECTION_DB),
        projection_key_file=str(PROJECTION_KEY_DEST),
        legacy_state_archive_marker=str(LEGACY_STATE_MARKER),
        env_file=str(ENV_FILE),
        service_name=SERVICE_NAME,
        authority_role="hosted_projection_v2",
        loopback=f"{LOOPBACK_HOST}:{LOOPBACK_PORT}",
        domains=[PRIMARY_DOMAIN, WWW_DOMAIN],
        nginx_site_available=str(NGINX_SITE_AVAILABLE),
        nginx_site_enabled=str(NGINX_SITE_ENABLED),
        auth_boundary=f"Basic Auth via {AUTH_FILE}; only exact /api/v2/ingest bypasses it",
        public_ingest_exception="POST /api/v2/ingest remains HMAC-authenticated by the application",
        forbidden_paths=[str(WEBCORE_RUNTIME_DIR), str(WEBCORE_ENV), str(WEBCORE_NGINX_SITE)],
        forbidden_services=sorted(WEBCORE_SERVICES),
        forbidden_ports=sorted(FORBIDDEN_PORTS),
        steps=[
            "prove exact clean source at origin/main and validate external 0600 projection key",
            "validate DNS, certificate renewal path, auth boundary, host, services and ports",
            "copy only projection v2 files into an immutable SHA release without --delete",
            "copy the HMAC key without printing it and install projection-only systemd configuration",
            "persist the ACME route/deploy hook and obtain a certificate fresh for at least 21 days",
            "atomically move current/previous symlinks; previous may reference only a v2 SHA release",
            "prove loopback no-authority health, public auth/read-only routes, TLS, and WebCore health",
        ],
    )


def _validate_safety(
    *,
    offline: bool = False,
    enforce_source: bool = False,
    require_key: bool = False,
    projection_key_file: Path | None = None,
) -> ValidationResult:
    blockers: list[str] = []
    warnings: list[str] = []
    source = _source_gate(enforced=enforce_source, fetch_origin=enforce_source and not offline)
    blockers.extend(source.blockers)
    warnings.extend(source.warnings)
    key_gate = _projection_key_gate(_projection_key_path(projection_key_file), required=require_key)
    blockers.extend(key_gate.blockers)
    warnings.extend(key_gate.warnings)

    if TARGET_HOST_IP == FORBIDDEN_HOST_IP:
        blockers.append("forbidden_target_host")
    if SSH_ALIAS != "wb-core-eu-root":
        blockers.append("unexpected_ssh_alias")
    if _path_is_relative_to(RELEASES_DIR, WEBCORE_RUNTIME_DIR) or _path_is_relative_to(PROJECTION_ROOT, WEBCORE_RUNTIME_DIR):
        blockers.append("control_plane_path_collides_with_webcore")
    if ENV_FILE == WEBCORE_ENV or NGINX_SITE_ENABLED == WEBCORE_NGINX_SITE:
        blockers.append("control_plane_configuration_collides_with_webcore")
    if SERVICE_NAME in WEBCORE_SERVICES or LOOPBACK_PORT in FORBIDDEN_PORTS:
        blockers.append("control_plane_service_or_port_collides_with_webcore")
    if LOOPBACK_HOST != "127.0.0.1":
        blockers.append("loopback_binding_required")

    dns: dict[str, Any] = {"local": {}, "doh": {}, "remote": {}, "gate": "not_checked"}
    cert_domains: list[str] = [PRIMARY_DOMAIN, WWW_DOMAIN] if offline else []
    if offline:
        warnings.append("offline_validation_skipped_dns_ssh_and_certificate_preflight")
        remote: dict[str, Any] = {"skipped": True}
        certificate = _unknown_certificate_gate()
    else:
        ssh_target = _local_ssh_target_gate()
        if ssh_target["status"] != "passed":
            blockers.extend(ssh_target["blockers"])
            remote = {"skipped": True, "ssh_target": ssh_target}
            certificate = _unknown_certificate_gate()
            return ValidationResult(
                status="blocked",
                blockers=sorted(set(blockers)),
                warnings=sorted(set(warnings)),
                source=source,
                projection_key=key_gate,
                certificate=certificate,
                dns=dns,
                cert_domains=[],
                remote=remote,
            )
        local_dns = _local_dns_probe((PRIMARY_DOMAIN, WWW_DOMAIN))
        doh_dns = _doh_dns_probe((PRIMARY_DOMAIN, WWW_DOMAIN))
        remote = _remote_preflight()
        remote["ssh_target"] = ssh_target
        blockers.extend(remote.pop("blockers"))
        warnings.extend(remote.pop("warnings"))
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
        certificate = _evaluate_certificate_gate(remote.get("certificate", {}))
        blockers.extend(certificate.blockers)
        if certificate.status == "renewal_required":
            warnings.extend(f"certificate_remediation:{item}" for item in certificate.remediation_reasons)

    if not cert_domains and not offline and not any(item.startswith(("dns_", "doh_", "remote_dns_")) for item in blockers):
        blockers.append("no_certificate_domains_available")
    if blockers:
        status = "blocked"
    elif certificate.status == "renewal_required":
        status = "renewal_required"
    elif warnings:
        status = "allowed_with_warning"
    else:
        status = "passed"
    return ValidationResult(
        status=status,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        source=source,
        projection_key=key_gate,
        certificate=certificate,
        dns=dns,
        cert_domains=cert_domains,
        remote=remote,
    )


def _source_gate(*, enforced: bool, fetch_origin: bool) -> SourceGateResult:
    blockers: list[str] = []
    warnings: list[str] = []
    source_failures: list[str] = []
    fetched = False
    origin_url = _local_git_value("config", "--local", "--get", "remote.origin.url") or ""
    exact_repo = origin_url in EXPECTED_ORIGIN_URLS
    rewrite_probe = _git_run(
        "config",
        "--show-origin",
        "--get-regexp",
        r"^url\..*\.(insteadof|pushinsteadof)$",
    )
    rewrite_configured = rewrite_probe.returncode == 0 and bool(rewrite_probe.stdout.strip())
    rewrite_probe_failed = rewrite_probe.returncode not in {0, 1}
    if rewrite_configured:
        source_failures.append("source_git_url_rewrite_forbidden")
    elif rewrite_probe_failed:
        source_failures.append("source_git_config_probe_failed")
    if fetch_origin and not rewrite_configured and not rewrite_probe_failed:
        fetched = (
            _git_run(
                "-c",
                "core.sshCommand=ssh -o BatchMode=yes -o ConnectTimeout=10 -o HostName=github.com "
                "-o User=git -o ProxyCommand=none -o ProxyJump=none -o StrictHostKeyChecking=yes",
                "fetch",
                "--quiet",
                "--no-tags",
                "--force",
                CANONICAL_FETCH_URL,
                "+refs/heads/main:refs/remotes/origin/main",
            ).returncode
            == 0
        )
        if not fetched:
            source_failures.append("source_origin_main_fetch_failed")
    head_sha = _full_sha_or_none(_local_git_value("rev-parse", "HEAD"))
    origin_main_sha = _full_sha_or_none(_local_git_value("rev-parse", "refs/remotes/origin/main"))
    status_result = _git_run("status", "--porcelain=v1", "--untracked-files=all")
    clean = status_result.returncode == 0 and not status_result.stdout.strip()
    matches = bool(head_sha and origin_main_sha and head_sha == origin_main_sha)
    raw_branch = _local_git_value("branch", "--show-current") or "detached"
    branch = raw_branch if SAFE_BRANCH_RE.fullmatch(raw_branch) else "unreportable"
    failures = list(source_failures)
    if not exact_repo:
        failures.append("source_repository_mismatch")
    if not clean:
        failures.append("source_worktree_not_clean")
    if not head_sha or not origin_main_sha:
        failures.append("source_revision_unavailable")
    elif not matches:
        failures.append("source_head_not_origin_main")
    if enforced:
        blockers.extend(failures)
    else:
        warnings.extend(f"dry_run_only:{item}" for item in failures)
    status = "blocked" if blockers else ("reported" if failures else "passed")
    return SourceGateResult(
        status=status,
        enforced=enforced,
        fetched_origin_main=fetched,
        exact_repository=exact_repo,
        clean=clean,
        head_matches_origin_main=matches,
        head_sha=head_sha,
        origin_main_sha=origin_main_sha,
        branch=branch,
        blockers=blockers,
        warnings=warnings,
    )


def _projection_key_path(value: Path | None) -> Path:
    candidate = (value if value is not None else DEFAULT_PROJECTION_KEY_FILE).expanduser()
    return Path(os.path.abspath(candidate))


class _ProjectionKeyValidationError(RuntimeError):
    pass


def _projection_key_snapshot(path: Path) -> bytes:
    """Return one securely opened immutable-in-memory key snapshot."""

    try:
        metadata = path.lstat()
    except OSError as exc:
        raise _ProjectionKeyValidationError("projection_key_unavailable") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise _ProjectionKeyValidationError("projection_key_not_regular_or_is_symlink")
    if metadata.st_uid != os.geteuid():
        raise _ProjectionKeyValidationError("projection_key_owner_mismatch")
    if stat.S_IMODE(metadata.st_mode) != 0o600:
        raise _ProjectionKeyValidationError("projection_key_mode_must_be_0600")
    if metadata.st_nlink != 1:
        raise _ProjectionKeyValidationError("projection_key_must_have_single_link")
    if metadata.st_size < 32 or metadata.st_size > 4096:
        raise _ProjectionKeyValidationError("projection_key_size_outside_32_4096_bytes")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        try:
            opened = os.fstat(descriptor)
            payload = os.read(descriptor, 4097)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise _ProjectionKeyValidationError("projection_key_secure_read_failed") from exc
    if (
        opened.st_dev != metadata.st_dev
        or opened.st_ino != metadata.st_ino
        or not stat.S_ISREG(opened.st_mode)
        or opened.st_uid != os.geteuid()
        or stat.S_IMODE(opened.st_mode) != 0o600
        or opened.st_nlink != 1
        or opened.st_size != metadata.st_size
    ):
        raise _ProjectionKeyValidationError("projection_key_changed_during_secure_read")
    material_size = len(payload.rstrip(b"\r\n"))
    if len(payload) > 4096 or material_size < 32 or material_size > 4096:
        raise _ProjectionKeyValidationError("projection_key_material_outside_32_4096_bytes")
    return payload


def _projection_key_gate(path: Path, *, required: bool) -> ProjectionKeyGateResult:
    blockers: list[str] = []
    warnings: list[str] = []
    source = "default" if path == DEFAULT_PROJECTION_KEY_FILE else "explicit"
    regular = False
    symlink = False
    owner_matches = False
    mode_text: str | None = None
    size: int | None = None
    issue: str | None = None
    try:
        metadata = path.lstat()
        symlink = stat.S_ISLNK(metadata.st_mode)
        regular = stat.S_ISREG(metadata.st_mode)
        owner_matches = metadata.st_uid == os.geteuid()
        mode = stat.S_IMODE(metadata.st_mode)
        mode_text = f"{mode:04o}"
        size = int(metadata.st_size)
        if symlink or not regular:
            issue = "projection_key_not_regular_or_is_symlink"
        elif not owner_matches:
            issue = "projection_key_owner_mismatch"
        elif mode != 0o600:
            issue = "projection_key_mode_must_be_0600"
        elif metadata.st_nlink != 1:
            issue = "projection_key_must_have_single_link"
        else:
            _projection_key_snapshot(path)
    except _ProjectionKeyValidationError as exc:
        issue = str(exc)
    except OSError:
        issue = "projection_key_unavailable"
    if issue:
        (blockers if required else warnings).append(issue)
    return ProjectionKeyGateResult(
        status="ready" if issue is None else ("blocked" if required else "reported_missing"),
        required=required,
        source=source,
        regular_file=regular,
        symlink=symlink,
        owner_matches_process=owner_matches,
        mode=mode_text,
        size_bytes=size,
        blockers=blockers,
        warnings=warnings,
    )


def _remote_preflight() -> dict[str, Any]:
    command = rf"""set -u
for tool in nginx certbot rsync python3 curl openssl systemctl ss flock ps tar sha256sum; do
  if command -v "$tool" >/dev/null 2>&1; then printf 'tool_%s=ready\n' "$tool"; else printf 'tool_%s=missing\n' "$tool"; fi
done
printf 'webcore_site=%s\n' "$(test -e {WEBCORE_NGINX_SITE} && echo present || echo missing)"
if [ -s {AUTH_FILE} ] && [ ! -L {AUTH_FILE} ]; then
  auth_mode="$(stat -c '%a' {AUTH_FILE} 2>/dev/null || true)"
  case "$auth_mode" in 600|640) printf 'basic_auth=ready\n' ;; *) printf 'basic_auth=unsafe\n' ;; esac
else
  printf 'basic_auth=missing\n'
fi
service_active="$(systemctl is-active {SERVICE_NAME} 2>/dev/null || true)"
service_pid="$(systemctl show -p MainPID --value {SERVICE_NAME} 2>/dev/null || true)"
printf 'service_active=%s\n' "$service_active"
health="$(curl -fsS --connect-timeout 2 --max-time 5 http://{LOOPBACK_HOST}:{LOOPBACK_PORT}/api/v2/health 2>/dev/null || true)"
if [ -n "$health" ]; then
  printf '%s' "$health" | python3 -c 'import json,sys; p=json.load(sys.stdin); print("health=ok"); print("health_role="+str(p.get("service_role",""))); print("health_control="+str(p.get("control_authority","")).lower()); print("health_mutation="+str(p.get("mutation_routes_enabled","")).lower())' 2>/dev/null || printf 'health=invalid\n'
else
  printf 'health=unavailable\n'
fi
listener="$(ss -ltnp 'sport = :{LOOPBACK_PORT}' 2>/dev/null | tail -n +2 || true)"
if [ -z "$listener" ]; then
  printf 'port_owner=free\n'
elif [ -n "$service_pid" ] && [ "$service_pid" != "0" ] && printf '%s' "$listener" | grep -Fq "pid=$service_pid,"; then
  printf 'port_owner=service\n'
else
  printf 'port_owner=foreign\n'
fi
printf 'legacy_state=%s\n' "$(test -d {LEGACY_STATE_DIR} && echo present || echo absent)"
if [ -L {APP_DIR} ]; then basename "$(readlink -f {APP_DIR})" | sed 's/^/current_release=/'; else printf 'current_release=legacy_or_absent\n'; fi
if [ -L {PREVIOUS_LINK} ]; then basename "$(readlink -f {PREVIOUS_LINK})" | sed 's/^/previous_release=/'; else printf 'previous_release=none\n'; fi
if [ -s {CERT_FULLCHAIN} ]; then
  printf 'cert_present=yes\n'
  epoch="$(openssl x509 -in {CERT_FULLCHAIN} -noout -enddate 2>/dev/null | cut -d= -f2- | xargs -r -I{{}} date -u -d '{{}}' +%s 2>/dev/null || true)"
  if [ -n "$epoch" ]; then
    printf 'cert_not_after_epoch=%s\n' "$epoch"
    printf 'cert_days_remaining=%s\n' "$(( (epoch - $(date +%s)) / 86400 ))"
    if openssl x509 -checkend {MIN_CERT_DAYS * 86400} -noout -in {CERT_FULLCHAIN} >/dev/null 2>&1; then printf 'cert_fresh_21d=yes\n'; else printf 'cert_fresh_21d=no\n'; fi
    if openssl x509 -checkend 0 -noout -in {CERT_FULLCHAIN} >/dev/null 2>&1; then printf 'cert_currently_valid=yes\n'; else printf 'cert_currently_valid=no\n'; fi
  else
    printf 'cert_not_after_epoch=invalid\n'
  fi
else
  printf 'cert_present=no\n'
fi
printf 'certbot_timer_enabled=%s\n' "$(systemctl is-enabled certbot.timer 2>/dev/null || true)"
printf 'certbot_timer_active=%s\n' "$(systemctl is-active certbot.timer 2>/dev/null || true)"
if grep -Fq 'location ^~ /.well-known/acme-challenge/' {NGINX_SITE_AVAILABLE} 2>/dev/null; then printf 'acme_route=yes\n'; else printf 'acme_route=no\n'; fi
if grep -Eq '^authenticator[[:space:]]*=[[:space:]]*webroot' {CERT_RENEWAL_FILE} 2>/dev/null; then printf 'renewal_webroot=yes\n'; else printf 'renewal_webroot=no\n'; fi
if test -x {CERT_DEPLOY_HOOK}; then printf 'deploy_hook=yes\n'; else printf 'deploy_hook=no\n'; fi
"""
    completed = _ssh(command)
    values = _parse_key_value_lines(completed.stdout.splitlines()) if completed.returncode == 0 else {}
    blockers: list[str] = []
    warnings: list[str] = []
    if completed.returncode != 0:
        blockers.append("remote_preflight_failed")
    tools = {
        name: values.get(f"tool_{name}") == "ready"
        for name in (
            "nginx",
            "certbot",
            "rsync",
            "python3",
            "curl",
            "openssl",
            "systemctl",
            "ss",
            "flock",
            "ps",
            "tar",
            "sha256sum",
        )
    }
    blockers.extend(f"remote_tool_missing:{name}" for name, ready in tools.items() if not ready)
    if values.get("webcore_site") != "present":
        blockers.append("webcore_nginx_marker_missing")
    if values.get("basic_auth") != "ready":
        blockers.append("basic_auth_file_missing_or_unsafe")
    port = _evaluate_port_8770_ownership(values)
    blockers.extend(port.blockers)
    warnings.extend(port.warnings)
    certificate = {
        "present": values.get("cert_present") == "yes",
        "not_after_epoch": _safe_int(values.get("cert_not_after_epoch")),
        "days_remaining": _safe_int(values.get("cert_days_remaining")),
        "fresh_21d": values.get("cert_fresh_21d") == "yes",
        "currently_valid": values.get("cert_currently_valid") == "yes",
        "timer_enabled": values.get("certbot_timer_enabled") == "enabled",
        "timer_active": values.get("certbot_timer_active") == "active",
        "acme_route": values.get("acme_route") == "yes",
        "renewal_webroot": values.get("renewal_webroot") == "yes",
        "deploy_hook": values.get("deploy_hook") == "yes",
        "parse_invalid": values.get("cert_not_after_epoch") == "invalid",
    }
    return {
        "status": "passed" if not blockers else "blocked",
        "tools": tools,
        "service": {
            "active": values.get("service_active", "unknown"),
            "health": values.get("health", "unavailable"),
            "service_role": values.get("health_role") or None,
            "control_authority": _safe_bool(values.get("health_control")),
            "mutation_routes_enabled": _safe_bool(values.get("health_mutation")),
            "port": asdict(port),
        },
        "legacy_state_present": values.get("legacy_state") == "present",
        "current_release": _safe_release_identity(values.get("current_release")),
        "previous_release": _safe_release_identity(values.get("previous_release")),
        "certificate": certificate,
        "blockers": blockers,
        "warnings": warnings,
    }


def _local_ssh_target_gate() -> dict[str, Any]:
    """Resolve the approved alias before making any network connection."""

    completed = subprocess.run(
        ["/usr/bin/ssh", "-G", *SSH_EXEC_OPTIONS, SSH_ALIAS],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    values: dict[str, str] = {}
    if completed.returncode == 0:
        for line in completed.stdout.splitlines():
            key, separator, value = line.strip().partition(" ")
            if separator and key in {
                "hostname", "user", "port", "proxycommand", "proxyjump",
                "stricthostkeychecking", "userknownhostsfile",
            }:
                values[key] = value.strip()[:200]
    blockers: list[str] = []
    if completed.returncode != 0:
        blockers.append("ssh_alias_resolution_failed")
    if values.get("hostname") != TARGET_HOST_IP:
        blockers.append("ssh_alias_target_ip_mismatch")
    if values.get("user") != "root" or values.get("port") != "22":
        blockers.append("ssh_alias_user_or_port_mismatch")
    if values.get("proxycommand") not in {None, "none"} or values.get("proxyjump") not in {None, "none"}:
        blockers.append("ssh_alias_proxy_forbidden")
    # OpenSSH normalizes command-line ``yes`` to ``true`` in ``ssh -G`` on
    # current macOS. Both are the same strict policy; every permissive value
    # (including accept-new/ask/no/off) remains blocked.
    if values.get("stricthostkeychecking", "").lower() not in {"yes", "true"}:
        blockers.append("ssh_strict_host_key_checking_not_pinned")
    known_hosts = _trusted_known_hosts_gate(TRUSTED_KNOWN_HOSTS_FILE)
    blockers.extend(known_hosts["blockers"])
    return {
        "status": "passed" if not blockers else "blocked",
        "hostname": values.get("hostname"),
        "user": values.get("user"),
        "port": values.get("port"),
        "strict_host_key_checking": values.get("stricthostkeychecking"),
        "trusted_known_hosts": known_hosts["status"],
        "proxy_configured": bool(
            values.get("proxycommand") not in {None, "none"}
            or values.get("proxyjump") not in {None, "none"}
        ),
        "blockers": blockers,
    }


def _trusted_known_hosts_gate(path: Path) -> dict[str, Any]:
    blockers: list[str] = []
    try:
        metadata = path.lstat()
    except OSError:
        metadata = None
        blockers.append("ssh_trusted_known_hosts_missing")
    if metadata is not None:
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            blockers.append("ssh_trusted_known_hosts_not_regular")
        elif metadata.st_uid != os.geteuid():
            blockers.append("ssh_trusted_known_hosts_owner_mismatch")
        elif stat.S_IMODE(metadata.st_mode) & 0o022:
            blockers.append("ssh_trusted_known_hosts_writable_by_others")
        elif metadata.st_size <= 0:
            blockers.append("ssh_trusted_known_hosts_empty")
        else:
            completed = subprocess.run(
                ["/usr/bin/ssh-keygen", "-F", TARGET_HOST_IP, "-f", str(path)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
                env={"HOME": str(path.parent.parent), "PATH": "/usr/bin:/bin", "LC_ALL": "C"},
            )
            if completed.returncode != 0 or not completed.stdout.strip():
                blockers.append("ssh_trusted_host_key_missing")
    return {"status": "passed" if not blockers else "blocked", "blockers": blockers}


def _evaluate_port_8770_ownership(values: Mapping[str, str] | Sequence[str]) -> PortOwnershipResult:
    if not isinstance(values, Mapping):
        values = _parse_key_value_lines(values)
    owner = str(values.get("port_owner") or "")
    service_active = str(values.get("service_active") or "")
    role = str(values.get("health_role") or values.get("service_loopback_service_role") or "")
    control = str(values.get("health_control") or "").lower()
    mutation = str(values.get("health_mutation") or "").lower()
    if not owner:
        legacy_lines = [line for line in values.values() if isinstance(line, str)]
        owner = "free" if not any("PORT_8770" in line for line in legacy_lines) else "foreign"
    details = {
        "owner": owner,
        "service_active": service_active,
        "service_role": role or None,
        "control_authority": _safe_bool(control),
        "mutation_routes_enabled": _safe_bool(mutation),
    }
    if owner == "free":
        return PortOwnershipResult("free", [], [], details)
    if owner == "service" and service_active == "active":
        if role == "hosted_projection_v2" and control == "false" and mutation == "false":
            return PortOwnershipResult(
                "allowed_existing_projection_v2",
                [],
                ["existing_projection_v2_service_will_be_updated"],
                details,
            )
        return PortOwnershipResult(
            "allowed_owned_legacy_migration",
            [],
            ["owned_legacy_service_will_be_replaced_not_retained"],
            details,
        )
    return PortOwnershipResult("blocked", ["port_8770_owned_by_foreign_process"], [], details)


def _unknown_certificate_gate() -> CertificateGateResult:
    return CertificateGateResult(
        status="not_checked",
        present=False,
        expires_at=None,
        days_remaining=None,
        currently_valid=False,
        fresh_for_21_days=False,
        certbot_timer_enabled=False,
        certbot_timer_active=False,
        acme_route_ready=False,
        renewal_webroot_ready=False,
        deploy_hook_ready=False,
        remediation_reasons=[],
        blockers=[],
    )


def _evaluate_certificate_gate(raw: Mapping[str, Any]) -> CertificateGateResult:
    present = bool(raw.get("present"))
    epoch = _safe_int(raw.get("not_after_epoch"))
    days = _safe_int(raw.get("days_remaining"))
    blockers: list[str] = []
    remediation: list[str] = []
    if bool(raw.get("parse_invalid")) or (present and epoch is None):
        blockers.append("certificate_expiry_unreadable")
    if not present:
        remediation.append("certificate_missing")
    elif not bool(raw.get("currently_valid")):
        remediation.append("certificate_expired")
    elif not bool(raw.get("fresh_21d")):
        remediation.append("certificate_freshness_below_21_days")
    if not bool(raw.get("timer_enabled")):
        remediation.append("certbot_timer_not_enabled")
    if not bool(raw.get("timer_active")):
        remediation.append("certbot_timer_not_active")
    if not bool(raw.get("acme_route")):
        remediation.append("permanent_acme_route_missing")
    if not bool(raw.get("renewal_webroot")):
        remediation.append("webroot_renewal_configuration_missing")
    if not bool(raw.get("deploy_hook")):
        remediation.append("certificate_deploy_hook_missing")
    expires_at = None
    if epoch is not None:
        try:
            expires_at = datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat().replace("+00:00", "Z")
        except (OverflowError, OSError, ValueError):
            blockers.append("certificate_expiry_out_of_range")
    status = "blocked" if blockers else ("renewal_required" if remediation else "ready")
    return CertificateGateResult(
        status=status,
        present=present,
        expires_at=expires_at,
        days_remaining=days,
        currently_valid=bool(raw.get("currently_valid")),
        fresh_for_21_days=bool(raw.get("fresh_21d")),
        certbot_timer_enabled=bool(raw.get("timer_enabled")),
        certbot_timer_active=bool(raw.get("timer_active")),
        acme_route_ready=bool(raw.get("acme_route")),
        renewal_webroot_ready=bool(raw.get("renewal_webroot")),
        deploy_hook_ready=bool(raw.get("deploy_hook")),
        remediation_reasons=sorted(set(remediation)),
        blockers=sorted(set(blockers)),
    )


def _deploy_live(
    *,
    cert_domains: Sequence[str],
    release_sha: str,
    projection_key_file: Path,
    certificate_remediation_reasons: Sequence[str] = (),
) -> dict[str, Any]:
    if not FULL_SHA_RE.fullmatch(release_sha):
        raise RuntimeError("invalid_verified_release_sha")
    final_source = _source_gate(enforced=True, fetch_origin=True)
    if final_source.status != "passed" or final_source.head_sha != release_sha:
        raise RuntimeError("final_source_gate_failed")
    key_gate = _projection_key_gate(projection_key_file, required=True)
    if key_gate.status != "ready":
        raise RuntimeError("projection_key_failed_final_validation")
    try:
        projection_key_material = _projection_key_snapshot(_projection_key_path(projection_key_file))
    except _ProjectionKeyValidationError as exc:
        raise RuntimeError("projection_key_failed_final_secure_snapshot") from exc
    if tuple(cert_domains) != (PRIMARY_DOMAIN, WWW_DOMAIN) and set(cert_domains) != {PRIMARY_DOMAIN, WWW_DOMAIN}:
        raise RuntimeError("certificate_domain_set_mismatch")
    staging_name = f".incoming-{release_sha}-{os.getpid()}-{int(time.time())}"
    staging_dir = RELEASES_DIR / staging_name
    force_certificate_refresh = bool(
        {
            "certificate_expired",
            "certificate_freshness_below_21_days",
            "webroot_renewal_configuration_missing",
        }.intersection(certificate_remediation_reasons)
    )
    transaction_started = False
    proof: dict[str, Any] | None = None
    try:
        with tempfile.TemporaryDirectory(prefix="dev-control-plane-projection-release-") as package_raw:
            package_root = Path(package_raw)
            package_root.chmod(0o700)
            manifest_digest = _build_projection_release_package(package_root, release_sha)
            begin_status = _begin_remote_activation(release_sha)
            transaction_started = True
            if begin_status != "created":
                raise RuntimeError("rollout_transaction_already_active")
            _ssh_checked(
                _remote_prepare_runtime_script(staging_dir, release_sha),
                operation="prepare_projection_runtime",
            )
            if not _remote_release_exists(release_sha, manifest_digest):
                _run_checked(
                    _release_rsync_command(staging_dir, package_root, release_sha),
                    operation="copy_projection_release",
                )
                _ssh_checked(
                    _remote_finalize_release_script(release_sha, staging_dir, manifest_digest),
                    operation="finalize_immutable_projection_release",
                )
        repeated_source = _source_gate(enforced=True, fetch_origin=True)
        if repeated_source.status != "passed" or repeated_source.head_sha != release_sha:
            raise RuntimeError("source_changed_during_projection_packaging")
        _install_projection_key_snapshot(projection_key_material, release_sha)
        _ssh_checked(
            _remote_install_script(
                cert_domains,
                release_sha,
                force_certificate_refresh=force_certificate_refresh,
            ),
            operation="activate_projection_v2_release",
        )
        proof = _prove_live_read_only(
            expected_release=release_sha,
            projection_key=projection_key_material,
        )
        _complete_remote_activation(release_sha)
        return proof
    except RuntimeError as exc:
        if not transaction_started:
            raise
        try:
            recovery = _recover_failed_projection_rollout(release_sha)
        except RuntimeError as recovery_error:
            # Once the activation command has been attempted, unavailable or
            # ambiguous readback is itself a failed-safe incident. Never infer
            # that the switch did not happen merely because SSH/readback failed.
            raise RuntimeError("rollout_proof_failed_quarantine_failed") from recovery_error
        if recovery == "completed" and proof is not None:
            return proof
        if recovery == "restored":
            raise RuntimeError("rollout_failed_prior_host_state_restored") from exc
        if recovery == "quarantined":
            raise RuntimeError("rollout_proof_failed_unverified_projection_quarantined") from exc
        if recovery == "not_activated":
            raise RuntimeError("rollout_failed_before_release_activation") from exc
        raise RuntimeError("rollout_proof_failed_quarantine_failed") from exc


def _begin_remote_activation(release_sha: str) -> str:
    completed = _ssh(_remote_begin_activation_script(release_sha))
    if completed.returncode != 0:
        raise RuntimeError("begin_projection_v2_activation_transaction_failed")
    values = _parse_key_value_lines(completed.stdout.splitlines())
    status = values.get("begin")
    if status not in {"created", "existing"}:
        raise RuntimeError("begin_projection_v2_activation_receipt_invalid")
    return status


def _complete_remote_activation(release_sha: str) -> None:
    release = RELEASES_DIR / release_sha
    marker = _activation_marker_path(release_sha)
    transaction_dir = _activation_transaction_dir(release_sha)
    receipt = _activation_receipt_path(release_sha, "DEPLOYED")
    _ssh_checked(
        f"""set -euo pipefail
exec 9>{ROLLOUT_LOCK}
flock -w 300 -x 9
{_remote_manifest_verifier_function()}
	{_remote_process_binding_function()}
	{_remote_activation_guard_function(release_sha)}
	{_remote_staging_cleanup_function(release_sha)}
	verify_activation_transaction
	verify_projection_release '{release}' '{release_sha}'
	verify_projection_process '{release}' >/dev/null
	cleanup_projection_staging
receipt_next={receipt}.next.$$
cat > "$receipt_next" <<'DCP_DEPLOYED_RECEIPT'
schema=dev-control-plane/hosted-rollout-receipt/v2
release_sha={release_sha}
outcome=deployed
DCP_DEPLOYED_RECEIPT
chown root:root "$receipt_next"
chmod 0444 "$receipt_next"
python3 - "$receipt_next" '{ARCHIVE_DIR}' <<'DCP_FSYNC_RECEIPT'
import os
import sys
for raw in sys.argv[1:]:
    descriptor = os.open(raw, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
DCP_FSYNC_RECEIPT
mv -Tf "$receipt_next" {receipt}
unlink {marker}
test ! -e {marker}
python3 - '{ARCHIVE_DIR}' <<'DCP_FSYNC_ARCHIVE'
import os
import sys
descriptor = os.open(sys.argv[1], os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
try:
    os.fsync(descriptor)
finally:
    os.close(descriptor)
DCP_FSYNC_ARCHIVE
python3 - '{transaction_dir}' <<'DCP_REMOVE_COMPLETED_TRANSACTION' || true
from pathlib import Path
import shutil
import stat
import sys
path = Path(sys.argv[1])
metadata = path.lstat()
if not stat.S_ISDIR(metadata.st_mode) or path.is_symlink():
    raise RuntimeError("unsafe completed transaction path")
shutil.rmtree(path)
DCP_REMOVE_COMPLETED_TRANSACTION
""",
        operation="complete_projection_v2_activation_receipt",
    )


def _recover_failed_projection_rollout(release_sha: str) -> str:
    completed = _ssh(_remote_failed_rollout_recovery_script(release_sha))
    if completed.returncode != 0:
        raise RuntimeError("failed_rollout_recovery_unavailable")
    values = _parse_key_value_lines(completed.stdout.splitlines())
    outcome = values.get("recovery")
    if outcome not in {"completed", "restored", "quarantined", "not_activated"}:
        raise RuntimeError("failed_rollout_recovery_receipt_invalid")
    if outcome == "restored" and values.get("prior_kind") not in {"v2", "legacy", "absent"}:
        raise RuntimeError("failed_rollout_recovery_receipt_invalid")
    if outcome == "restored" and values.get("prior_kind") == "v2" and not _safe_release_identity(
        values.get("release")
    ):
        raise RuntimeError("failed_rollout_recovery_receipt_invalid")
    return outcome


def _remote_failed_rollout_recovery_script(release_sha: str) -> str:
    if not FULL_SHA_RE.fullmatch(release_sha):
        raise RuntimeError("failed_rollout_release_identity_invalid")
    activation_marker = _activation_marker_path(release_sha)
    transaction_dir = _activation_transaction_dir(release_sha)
    snapshot = transaction_dir / "pre-mutation.tar"
    state = transaction_dir / "pre-mutation.state"
    restored_receipt = _activation_receipt_path(release_sha, "RESTORED")
    quarantine_receipt = _activation_receipt_path(release_sha, "QUARANTINED")
    deployed_receipt = _activation_receipt_path(release_sha, "DEPLOYED")
    allowed_paths = json.dumps([str(path) for path in ROLLOUT_SNAPSHOT_PATHS])
    return f"""set -euo pipefail
exec 9>{ROLLOUT_LOCK}
flock -w 300 -x 9
{_remote_manifest_verifier_function()}
	{_remote_process_binding_function()}
	{_remote_activation_guard_function(release_sha)}
	{_remote_staging_cleanup_function(release_sha)}
if [ ! -e {activation_marker} ]; then
  release='{RELEASES_DIR / release_sha}'
  if [ -f '{deployed_receipt}' ] && [ ! -L '{deployed_receipt}' ] && \
     grep -Fxq 'schema=dev-control-plane/hosted-rollout-receipt/v2' '{deployed_receipt}' && \
     grep -Fxq 'release_sha={release_sha}' '{deployed_receipt}' && \
     grep -Fxq 'outcome=deployed' '{deployed_receipt}' && \
     verify_projection_release "$release" '{release_sha}' && \
     verify_projection_process "$release" >/dev/null && \
     curl -fsS --connect-timeout 2 --max-time 5 http://{LOOPBACK_HOST}:{LOOPBACK_PORT}/api/v2/health 2>/dev/null | python3 -c 'import json,sys; p=json.load(sys.stdin); raise SystemExit(0 if (p.get("service_role") == "hosted_projection_v2" and p.get("control_authority") is False and p.get("mutation_routes_enabled") is False) else 1)'; then
    printf 'recovery=completed\n'
    exit 0
  fi
  printf 'recovery=not_activated\n'
  exit 0
fi
verify_activation_transaction
read_snapshot_value() {{
  key="$1"
  test "$(grep -Ec "^$key=" '{state}')" = '1'
  sed -n "s/^$key=//p" '{state}'
}}
prior_kind="$(read_snapshot_value prior_app_kind)"
prior_release_sha="$(read_snapshot_value prior_release_sha)"
service_active="$(read_snapshot_value service_active)"
service_enabled="$(read_snapshot_value service_enabled)"
nginx_active="$(read_snapshot_value nginx_active)"
certbot_active="$(read_snapshot_value certbot_active)"
certbot_enabled="$(read_snapshot_value certbot_enabled)"
case "$prior_kind" in v2|legacy|absent) ;; *) exit 85 ;; esac
case "$service_active:$service_enabled:$nginx_active:$certbot_active:$certbot_enabled" in
  yes:yes:yes:yes:yes|yes:yes:yes:yes:no|yes:yes:yes:no:yes|yes:yes:yes:no:no|\
  yes:yes:no:yes:yes|yes:yes:no:yes:no|yes:yes:no:no:yes|yes:yes:no:no:no|\
  yes:no:yes:yes:yes|yes:no:yes:yes:no|yes:no:yes:no:yes|yes:no:yes:no:no|\
  yes:no:no:yes:yes|yes:no:no:yes:no|yes:no:no:no:yes|yes:no:no:no:no|\
  no:yes:yes:yes:yes|no:yes:yes:yes:no|no:yes:yes:no:yes|no:yes:yes:no:no|\
  no:yes:no:yes:yes|no:yes:no:yes:no|no:yes:no:no:yes|no:yes:no:no:no|\
  no:no:yes:yes:yes|no:no:yes:yes:no|no:no:yes:no:yes|no:no:yes:no:no|\
  no:no:no:yes:yes|no:no:no:yes:no|no:no:no:no:yes|no:no:no:no:no) ;;
  *) exit 86 ;;
esac
if [ "$prior_kind" = v2 ]; then
  printf '%s' "$prior_release_sha" | grep -Eq '^[0-9a-f]{{40}}$'
else
  test "$prior_release_sha" = none
fi

restore_snapshot() {{
  systemctl stop '{SERVICE_NAME}' >/dev/null 2>&1 || true
  systemctl stop certbot.timer >/dev/null 2>&1 || true
  python3 - '{snapshot}' <<'DCP_VALIDATE_SNAPSHOT' || return 1
from pathlib import PurePosixPath
import json
import sys
import tarfile
allowed = [PurePosixPath(item.lstrip("/")) for item in json.loads({allowed_paths!r})]
with tarfile.open(sys.argv[1], "r:*") as archive:
    for member in archive.getmembers():
        candidate = PurePosixPath(member.name)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise RuntimeError("unsafe snapshot member")
        if not any(candidate == root or root in candidate.parents for root in allowed):
            raise RuntimeError("snapshot member outside allowlist")
        if not (member.isfile() or member.isdir() or member.issym() or member.islnk()):
            raise RuntimeError("unsupported snapshot member")
DCP_VALIDATE_SNAPSHOT
  python3 - <<'DCP_CLEAR_MUTATED_PATHS' || return 1
from pathlib import Path
import os
import shutil
import stat
allowed = [Path(item) for item in {allowed_paths}]
for path in sorted(allowed, key=lambda item: len(item.parts), reverse=True):
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        continue
    if stat.S_ISDIR(metadata.st_mode) and not stat.S_ISLNK(metadata.st_mode):
        shutil.rmtree(path)
    else:
        os.unlink(path)
DCP_CLEAR_MUTATED_PATHS
  tar --extract --file='{snapshot}' --acls --xattrs --numeric-owner --same-owner --same-permissions --directory=/ || return 1
  systemctl daemon-reload || return 1
  if [ "$service_enabled" = yes ]; then
    systemctl enable '{SERVICE_NAME}' >/dev/null 2>&1 || return 1
  else
    systemctl disable '{SERVICE_NAME}' >/dev/null 2>&1 || true
  fi
  if [ "$certbot_enabled" = yes ]; then
    systemctl enable certbot.timer >/dev/null 2>&1 || return 1
  else
    systemctl disable certbot.timer >/dev/null 2>&1 || true
  fi
  nginx -t >/dev/null 2>&1 || return 1
  if [ "$nginx_active" = yes ]; then
    systemctl start nginx >/dev/null 2>&1 || return 1
    systemctl reload nginx >/dev/null 2>&1 || return 1
  else
    systemctl stop nginx >/dev/null 2>&1 || return 1
  fi
  if [ "$service_active" = yes ]; then
    systemctl start '{SERVICE_NAME}' >/dev/null 2>&1 || return 1
  else
    systemctl stop '{SERVICE_NAME}' >/dev/null 2>&1 || true
  fi
  if [ "$certbot_active" = yes ]; then
    systemctl start certbot.timer >/dev/null 2>&1 || return 1
  else
    systemctl stop certbot.timer >/dev/null 2>&1 || true
  fi
  if [ "$prior_kind" = v2 ]; then
    prior_release='{RELEASES_DIR}/'"$prior_release_sha"
    verify_projection_release "$prior_release" "$prior_release_sha" || return 1
    test "$(readlink -f '{APP_DIR}')" = "$prior_release" || return 1
    if [ "$service_active" = yes ]; then
      wait_for_projection_process "$prior_release" || return 1
    fi
  elif [ "$prior_kind" = legacy ] && [ "$service_active" = yes ]; then
    test "$(systemctl is-active '{SERVICE_NAME}')" = active || return 1
    main_pid="$(systemctl show -p MainPID --value '{SERVICE_NAME}')"
    printf '%s' "$main_pid" | grep -Eq '^[1-9][0-9]*$' || return 1
    listener="$(ss -ltnp 'sport = :{LOOPBACK_PORT}' 2>/dev/null | tail -n +2)"
    test -n "$listener" || return 1
    printf '%s' "$listener" | grep -Fq "pid=$main_pid," || return 1
  else
    test "$(systemctl is-active '{SERVICE_NAME}' 2>/dev/null || true)" != active || return 1
    if ss -ltnp 'sport = :{LOOPBACK_PORT}' 2>/dev/null | tail -n +2 | grep -q .; then
      return 1
    fi
  fi
  test "$(systemctl is-active nginx 2>/dev/null || true)" = "$(if [ "$nginx_active" = yes ]; then printf active; else printf inactive; fi)" || return 1
  return 0
}}

quarantine_projection() {{
  receipt_next='{quarantine_receipt}.next.'$$
  cat > "$receipt_next" <<'DCP_QUARANTINE'
schema=dev-control-plane/hosted-rollout-receipt/v2
release_sha={release_sha}
outcome=quarantined
reason=restore_or_terminal_proof_failed
authority=disabled
DCP_QUARANTINE
  chown root:root "$receipt_next"
  chmod 0444 "$receipt_next"
  python3 - "$receipt_next" <<'DCP_FSYNC_QUARANTINE'
import os
import sys
descriptor = os.open(sys.argv[1], os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
try:
    os.fsync(descriptor)
finally:
    os.close(descriptor)
DCP_FSYNC_QUARANTINE
  mv -Tf "$receipt_next" '{quarantine_receipt}'
  systemctl stop '{SERVICE_NAME}' >/dev/null 2>&1 || true
  systemctl disable '{SERVICE_NAME}' >/dev/null 2>&1 || true
  systemctl stop certbot.timer >/dev/null 2>&1 || true
  python3 - '{NGINX_SITE_ENABLED}' <<'DCP_DISABLE_PROJECTION_SITE'
from pathlib import Path
import os
import stat
import sys
path = Path(sys.argv[1])
try:
    metadata = path.lstat()
except FileNotFoundError:
    pass
else:
    if stat.S_ISDIR(metadata.st_mode) and not stat.S_ISLNK(metadata.st_mode):
        raise RuntimeError("refusing projection site directory")
    os.unlink(path)
DCP_DISABLE_PROJECTION_SITE
  nginx -t >/dev/null 2>&1 || return 1
  if systemctl is-active --quiet nginx; then systemctl reload nginx >/dev/null 2>&1 || return 1; fi
  if [ -L '{APP_DIR}' ]; then
    active="$(readlink -f '{APP_DIR}')"
    case "$active" in '{RELEASES_DIR}'/*) unlink '{APP_DIR}' ;; *) return 1 ;; esac
  fi
	  cleanup_projection_staging
  test "$(systemctl is-active '{SERVICE_NAME}' 2>/dev/null || true)" != active || return 1
  if ss -ltnp 'sport = :{LOOPBACK_PORT}' 2>/dev/null | tail -n +2 | grep -q .; then return 1; fi
  unlink '{activation_marker}'
  python3 - '{ARCHIVE_DIR}' <<'DCP_FSYNC_QUARANTINE_DIR'
import os
import sys
descriptor = os.open(sys.argv[1], os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
try:
    os.fsync(descriptor)
finally:
    os.close(descriptor)
DCP_FSYNC_QUARANTINE_DIR
  printf 'recovery=quarantined\n'
}}

if restore_snapshot; then
	  cleanup_projection_staging
  receipt_next='{restored_receipt}.next.'$$
  cat > "$receipt_next" <<DCP_RESTORED_RECEIPT
schema=dev-control-plane/hosted-rollout-receipt/v2
release_sha={release_sha}
outcome=restored
prior_kind=$prior_kind
prior_release_sha=$prior_release_sha
DCP_RESTORED_RECEIPT
  chown root:root "$receipt_next"
  chmod 0444 "$receipt_next"
  python3 - "$receipt_next" <<'DCP_FSYNC_RESTORED'
import os
import sys
descriptor = os.open(sys.argv[1], os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
try:
    os.fsync(descriptor)
finally:
    os.close(descriptor)
DCP_FSYNC_RESTORED
  mv -Tf "$receipt_next" '{restored_receipt}'
  unlink '{activation_marker}'
  python3 - '{ARCHIVE_DIR}' <<'DCP_FSYNC_RESTORED_DIR'
import os
import sys
descriptor = os.open(sys.argv[1], os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
try:
    os.fsync(descriptor)
finally:
    os.close(descriptor)
DCP_FSYNC_RESTORED_DIR
  printf 'recovery=restored\nprior_kind=%s\n' "$prior_kind"
  if [ "$prior_kind" = v2 ]; then printf 'release=%s\n' "$prior_release_sha"; fi
  exit 0
fi
quarantine_projection
"""


def _build_projection_release_package(package_root: Path, release_sha: str) -> str:
    """Materialize the minimal hosted release from one immutable Git tree."""

    if not FULL_SHA_RE.fullmatch(release_sha):
        raise RuntimeError("projection_package_release_sha_invalid")
    files: dict[str, str] = {}
    for relative in RELEASE_FILES:
        listing = subprocess.run(
            ["git", "ls-tree", release_sha, "--", relative],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        rows = [line for line in listing.stdout.splitlines() if line]
        if listing.returncode != 0 or len(rows) != 1:
            raise RuntimeError("projection_git_object_file_missing")
        try:
            metadata, observed_path = rows[0].split("\t", 1)
            mode, object_type, object_sha = metadata.split(" ")
        except ValueError as exc:
            raise RuntimeError("projection_git_object_listing_invalid") from exc
        if (
            observed_path != relative
            or object_type != "blob"
            or mode not in {"100644", "100755"}
            or not FULL_SHA_RE.fullmatch(object_sha)
        ):
            raise RuntimeError("projection_git_object_file_unsafe")
        blob = subprocess.run(
            ["git", "cat-file", "blob", object_sha],
            cwd=ROOT,
            capture_output=True,
            check=False,
        )
        if blob.returncode != 0 or len(blob.stdout) > 25 * 1024 * 1024:
            raise RuntimeError("projection_git_object_blob_unavailable")
        destination = package_root.joinpath(*Path(relative).parts)
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor = os.open(
            destination,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o700 if mode == "100755" else 0o600,
        )
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(blob.stdout)
            handle.flush()
            os.fsync(handle.fileno())
        files[relative] = hashlib.sha256(blob.stdout).hexdigest()
    manifest = {
        "schema": "dev-control-plane/hosted-projection-release/v2",
        "release_sha": release_sha,
        "files": files,
    }
    manifest_bytes = (
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    manifest_path = package_root / ".release-manifest.json"
    descriptor = os.open(manifest_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(manifest_bytes)
        handle.flush()
        os.fsync(handle.fileno())
    return hashlib.sha256(manifest_bytes).hexdigest()


def _remote_manifest_verifier_function() -> str:
    expected_files = json.dumps(list(RELEASE_FILES), separators=(",", ":"))
    return f"""verify_projection_release() {{
  python3 - "$1" "$2" <<'DCP_VERIFY_RELEASE'
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
def require(condition, label):
    if not condition:
        raise RuntimeError(label)
root = Path(sys.argv[1])
expected_sha = sys.argv[2]
manifest_path = root / '.release-manifest.json'
expected_payload_files = set({expected_files})
expected_metadata_files = {{'.release-manifest.json', '.deploy-commit', '.deploy-manifest-digest'}}
expected_all_files = expected_payload_files | expected_metadata_files
expected_directories = {{'.'}}
for relative in expected_payload_files:
    parent = Path(relative).parent
    while str(parent) != '.':
        expected_directories.add(parent.as_posix())
        parent = parent.parent
root_metadata = root.lstat()
require(stat.S_ISDIR(root_metadata.st_mode) and not root.is_symlink(), 'release root type')
require(stat.S_IMODE(root_metadata.st_mode) == 0o555, 'release root mode')
require(root_metadata.st_uid == 0 and root_metadata.st_gid == 0, 'release root owner')
actual_files = set()
actual_directories = {{'.'}}
for candidate in root.rglob('*'):
    relative = candidate.relative_to(root).as_posix()
    metadata = candidate.lstat()
    require(not stat.S_ISLNK(metadata.st_mode), 'release symlink')
    require(metadata.st_uid == 0 and metadata.st_gid == 0, 'release path owner')
    if stat.S_ISREG(metadata.st_mode):
        require(stat.S_IMODE(metadata.st_mode) == 0o444, 'release file mode')
        actual_files.add(relative)
    elif stat.S_ISDIR(metadata.st_mode):
        require(stat.S_IMODE(metadata.st_mode) == 0o555, 'release directory mode')
        actual_directories.add(relative)
    else:
        raise AssertionError('unsupported release path type')
require(actual_files == expected_all_files, 'release files')
require(actual_directories == expected_directories, 'release directories')
require(manifest_path.is_file() and not manifest_path.is_symlink(), 'release manifest type')
manifest_bytes = manifest_path.read_bytes()
manifest = json.loads(manifest_bytes)
require(set(manifest) == {{'schema', 'release_sha', 'files'}}, 'release manifest fields')
require(manifest['schema'] == 'dev-control-plane/hosted-projection-release/v2', 'release schema')
require(manifest['release_sha'] == expected_sha, 'release identity')
files = manifest['files']
require(isinstance(files, dict) and set(files) == expected_payload_files, 'release payload fields')
for relative, expected_digest in files.items():
    require(isinstance(expected_digest, str) and len(expected_digest) == 64, 'release digest shape')
    require(all(character in '0123456789abcdef' for character in expected_digest), 'release digest alphabet')
    candidate = root.joinpath(*Path(relative).parts)
    require(candidate.is_file() and not candidate.is_symlink(), 'release payload type')
    require(candidate.resolve().is_relative_to(root.resolve()), 'release payload containment')
    require(hashlib.sha256(candidate.read_bytes()).hexdigest() == expected_digest, 'release payload digest')
require((root / '.deploy-commit').read_text().strip() == expected_sha, 'release commit')
require((root / '.deploy-manifest-digest').read_text().strip() == hashlib.sha256(manifest_bytes).hexdigest(), 'release manifest digest')
DCP_VERIFY_RELEASE
}}
"""


def _remote_prepare_runtime_script(staging_dir: Path, release_sha: str) -> str:
    release = RELEASES_DIR / release_sha
    return f"""set -euo pipefail
exec 9>{ROLLOUT_LOCK}
flock -w 300 -x 9
{_remote_manifest_verifier_function()}
{_remote_activation_guard_function(release_sha)}
verify_activation_transaction
getent group {PROJECTION_SERVICE_GROUP} >/dev/null 2>&1 || groupadd --system {PROJECTION_SERVICE_GROUP}
id -u {PROJECTION_SERVICE_USER} >/dev/null 2>&1 || useradd --system --gid {PROJECTION_SERVICE_GROUP} --home-dir {PROJECTION_ROOT} --shell /usr/sbin/nologin {PROJECTION_SERVICE_USER}
install -d -o root -g root -m 0755 {RUNTIME_ROOT} {RELEASES_DIR} {CONFIG_DIR} {ARCHIVE_DIR} {ACME_ROOT}
for projection_path in {PROJECTION_ROOT} {PROJECTION_STATE_DIR} {PROJECTION_SECRETS_DIR}; do
  if [ -e "$projection_path" ]; then
    test -d "$projection_path"
    test ! -L "$projection_path"
  fi
done
install -d -o {PROJECTION_SERVICE_USER} -g {PROJECTION_SERVICE_GROUP} -m 0700 {PROJECTION_ROOT} {PROJECTION_STATE_DIR} {PROJECTION_SECRETS_DIR}
test -z "$(find {PROJECTION_ROOT} -xdev -type l -print -quit)"
test -z "$(find {PROJECTION_ROOT} -xdev ! -type d ! -type f -print -quit)"
test -z "$(find {PROJECTION_ROOT} -xdev -type f -links +1 -print -quit)"
chown --no-dereference {PROJECTION_SERVICE_USER}:{PROJECTION_SERVICE_GROUP} {PROJECTION_ROOT} {PROJECTION_STATE_DIR} {PROJECTION_SECRETS_DIR}
if [ ! -e {release} ]; then
  test ! -e {staging_dir}
  install -d -o root -g root -m 0755 {staging_dir}
fi
if [ -e {PREVIOUS_LINK} ] && [ ! -L {PREVIOUS_LINK} ]; then exit 30; fi
if [ -L {PREVIOUS_LINK} ]; then
  previous="$(readlink -f {PREVIOUS_LINK})"
  case "$previous" in {RELEASES_DIR}/*) ;; *) exit 31 ;; esac
  previous_sha="$(basename "$previous")"
  printf '%s' "$previous_sha" | grep -Eq '^[0-9a-f]{{40}}$'
  verify_projection_release "$previous" "$previous_sha"
fi
"""


def _remote_release_exists(release_sha: str, expected_manifest_digest: str) -> bool:
    if not re.fullmatch(r"[0-9a-f]{64}", expected_manifest_digest):
        raise RuntimeError("projection_manifest_digest_invalid")
    release = RELEASES_DIR / release_sha
    command = f"""set -euo pipefail
{_remote_manifest_verifier_function()}
if [ ! -e {release} ]; then printf 'release=absent\n'; exit 0; fi
test -d {release}
test ! -L {release}
verify_projection_release '{release}' '{release_sha}'
test "$(cat {release}/.deploy-manifest-digest)" = '{expected_manifest_digest}'
printf 'release=verified\n'
"""
    completed = _ssh(command)
    if completed.returncode != 0:
        raise RuntimeError("existing_release_failed_immutable_identity_check")
    value = _parse_key_value_lines(completed.stdout.splitlines()).get("release")
    if value not in {"absent", "verified"}:
        raise RuntimeError("release_presence_probe_invalid")
    return value == "verified"


def _release_rsync_command(
    staging_dir: Path,
    package_root: Path,
    release_sha: str,
) -> list[str]:
    if not FULL_SHA_RE.fullmatch(release_sha):
        raise RuntimeError("projection_rsync_release_identity_invalid")
    expected_prefix = f".incoming-{release_sha}-"
    if staging_dir.parent != RELEASES_DIR or not staging_dir.name.startswith(expected_prefix):
        raise RuntimeError("projection_rsync_staging_identity_invalid")
    remote_shell = " ".join(("/usr/bin/ssh", *SSH_EXEC_OPTIONS))
    receiver = f"""set -euo pipefail
exec 9>{ROLLOUT_LOCK}
flock -w 300 -x 9
{_remote_activation_guard_function(release_sha)}
verify_activation_transaction
test -d '{staging_dir}'
test ! -L '{staging_dir}'
test ! -e '{RELEASES_DIR / release_sha}'
exec /usr/bin/rsync"""
    return [
        "/usr/bin/rsync",
        "-aR",
        f"--rsh={remote_shell}",
        f"--rsync-path={receiver}",
        "--chmod=Du=rwx,Dgo=rx,Fu=rw,Fgo=r",
        *(f"{package_root}/./{relative}" for relative in RELEASE_FILES),
        f"{package_root}/./.release-manifest.json",
        f"{SSH_ALIAS}:{staging_dir}/",
    ]


def _remote_finalize_release_script(
    release_sha: str,
    staging_dir: Path,
    manifest_digest: str,
) -> str:
    if not re.fullmatch(r"[0-9a-f]{64}", manifest_digest):
        raise RuntimeError("projection_manifest_digest_invalid")
    release = RELEASES_DIR / release_sha
    return f"""set -euo pipefail
exec 9>{ROLLOUT_LOCK}
flock -w 300 -x 9
{_remote_manifest_verifier_function()}
{_remote_activation_guard_function(release_sha)}
verify_activation_transaction
test ! -e {release}
printf '%s\n' '{release_sha}' > {staging_dir}/.deploy-commit
printf '%s\n' '{manifest_digest}' > {staging_dir}/.deploy-manifest-digest
chown -R root:root {staging_dir}
find {staging_dir} -type f -exec chmod 0444 {{}} +
find {staging_dir} -type d -exec chmod 0555 {{}} +
verify_projection_release '{staging_dir}' '{release_sha}'
mv {staging_dir} {release}
verify_projection_release '{release}' '{release_sha}'
"""


def _copy_projection_key(local_path: Path, release_sha: str) -> None:
    if not FULL_SHA_RE.fullmatch(release_sha):
        raise RuntimeError("projection_key_release_identity_invalid")
    try:
        snapshot = _projection_key_snapshot(_projection_key_path(local_path))
    except _ProjectionKeyValidationError as exc:
        raise RuntimeError("projection_key_failed_final_secure_snapshot") from exc
    _install_projection_key_snapshot(snapshot, release_sha)


def _install_projection_key_snapshot(snapshot: bytes, release_sha: str) -> None:
    if not FULL_SHA_RE.fullmatch(release_sha):
        raise RuntimeError("projection_key_release_identity_invalid")
    material_size = len(snapshot.rstrip(b"\r\n"))
    if len(snapshot) > 4096 or material_size < 32 or material_size > 4096:
        raise RuntimeError("projection_key_snapshot_invalid")
    incoming = PROJECTION_SECRETS_DIR / f".projection-v2.hmac.{release_sha}.{os.getpid()}.{int(time.time())}.incoming"
    _ssh_bytes_checked(
        f"""set -euo pipefail
umask 077
exec 9>{ROLLOUT_LOCK}
flock -w 300 -x 9
{_remote_activation_guard_function(release_sha)}
verify_activation_transaction
test ! -e {incoming}
trap 'test ! -e {incoming} || unlink {incoming}' EXIT
cat > {incoming}
test -f {incoming}
test ! -L {incoming}
test "$(stat -c '%a' {incoming})" = '600'
test "$(stat -c '%h' {incoming})" = '1'
size="$(wc -c < {incoming})"
test "$size" -ge 32
test "$size" -le 4096
chown {PROJECTION_SERVICE_USER}:{PROJECTION_SERVICE_GROUP} {incoming}
chmod 0600 {incoming}
mv -f {incoming} {PROJECTION_KEY_DEST}
test ! -L {PROJECTION_KEY_DEST}
test "$(stat -c '%a' {PROJECTION_KEY_DEST})" = '600'
test "$(stat -c '%h' {PROJECTION_KEY_DEST})" = '1'
""",
        snapshot,
        operation="install_projection_hmac_key",
    )


def _remote_install_script(
    cert_domains: Sequence[str],
    release_sha: str,
    *,
    force_certificate_refresh: bool = False,
) -> str:
    domains = tuple(cert_domains)
    if set(domains) != {PRIMARY_DOMAIN, WWW_DOMAIN}:
        raise RuntimeError("certificate_domain_set_mismatch")
    if not FULL_SHA_RE.fullmatch(release_sha):
        raise RuntimeError("invalid_verified_release_sha")
    release = RELEASES_DIR / release_sha
    domain_args = " ".join(f"-d {item}" for item in domains)
    bootstrap_nginx = _nginx_config(include_tls=False)
    guarded_nginx = _nginx_config(include_tls=True, allow_signed_ingest=False)
    final_nginx = _nginx_config(include_tls=True)
    environment = _projection_environment()
    unit = _systemd_unit()
    return f"""set -euo pipefail
exec 9>{ROLLOUT_LOCK}
flock -w 300 -x 9
{_remote_manifest_verifier_function()}
{_remote_activation_guard_function(release_sha)}
verify_activation_transaction
verify_projection_release '{release}' '{release_sha}'
systemctl stop certbot.timer >/dev/null 2>&1 || true
test -f {PROJECTION_KEY_DEST}
test ! -L {PROJECTION_KEY_DEST}
test "$(stat -c '%a' {PROJECTION_KEY_DEST})" = '600'
test -s {AUTH_FILE}
cat > {ENV_FILE} <<'DCP_ENV'
{environment}DCP_ENV
chown root:{PROJECTION_SERVICE_GROUP} {ENV_FILE}
chmod 0640 {ENV_FILE}
cat > /etc/systemd/system/{SERVICE_NAME} <<'DCP_UNIT'
{unit}DCP_UNIT
chmod 0644 /etc/systemd/system/{SERVICE_NAME}
install -d -o root -g root -m 0755 {CERT_DEPLOY_HOOK.parent}
cat > {CERT_DEPLOY_HOOK} <<'DCP_HOOK'
#!/bin/sh
set -eu
nginx -t >/dev/null 2>&1
systemctl reload nginx
DCP_HOOK
chown root:root {CERT_DEPLOY_HOOK}
chmod 0700 {CERT_DEPLOY_HOOK}
if [ -s {CERT_FULLCHAIN} ] && [ -s {CERT_PRIVATE_KEY} ]; then
  cat > {NGINX_SITE_AVAILABLE} <<'DCP_NGINX_EXISTING'
{guarded_nginx}DCP_NGINX_EXISTING
else
  cat > {NGINX_SITE_AVAILABLE} <<'DCP_NGINX_BOOTSTRAP'
{bootstrap_nginx}DCP_NGINX_BOOTSTRAP
fi
ln -sfn {NGINX_SITE_AVAILABLE} {NGINX_SITE_ENABLED}
nginx -t >/dev/null 2>&1
systemctl reload nginx
if [ ! -s {CERT_FULLCHAIN} ]; then
  certbot certonly --cert-name {PRIMARY_DOMAIN} --webroot -w {ACME_ROOT} {domain_args} --non-interactive --agree-tos -m {CERTBOT_EMAIL} >/dev/null 2>&1
elif [ '{1 if force_certificate_refresh else 0}' = '1' ] || ! openssl x509 -checkend {MIN_CERT_DAYS * 86400} -noout -in {CERT_FULLCHAIN} >/dev/null 2>&1; then
  certbot certonly --cert-name {PRIMARY_DOMAIN} --webroot -w {ACME_ROOT} {domain_args} --non-interactive --agree-tos -m {CERTBOT_EMAIL} --force-renewal >/dev/null 2>&1
fi
test -s {CERT_FULLCHAIN}
test -s {CERT_PRIVATE_KEY}
openssl x509 -checkend {MIN_CERT_DAYS * 86400} -noout -in {CERT_FULLCHAIN} >/dev/null 2>&1
grep -Eq '^authenticator[[:space:]]*=[[:space:]]*webroot' {CERT_RENEWAL_FILE}
systemctl enable --now certbot.timer >/dev/null 2>&1
test "$(systemctl is-enabled certbot.timer)" = 'enabled'
test "$(systemctl is-active certbot.timer)" = 'active'
cat > {NGINX_SITE_AVAILABLE} <<'DCP_NGINX_GUARDED'
{guarded_nginx}DCP_NGINX_GUARDED
chmod 0644 {NGINX_SITE_AVAILABLE}
nginx -t >/dev/null 2>&1
systemctl reload nginx
if [ -d {LEGACY_STATE_DIR} ]; then
  if [ ! -e {LEGACY_STATE_MARKER} ]; then
    cat > {LEGACY_STATE_MARKER} <<'DCP_ARCHIVE'
legacy_state_path={LEGACY_STATE_DIR}
archive_role=read_only_audit_history
mutation_authority=disabled
DCP_ARCHIVE
    chown root:root {LEGACY_STATE_MARKER}
    chmod 0444 {LEGACY_STATE_MARKER}
  fi
  test -f {LEGACY_STATE_MARKER}
  test ! -L {LEGACY_STATE_MARKER}
  test "$(stat -c '%a' {LEGACY_STATE_MARKER})" = '444'
  grep -Fxq 'legacy_state_path={LEGACY_STATE_DIR}' {LEGACY_STATE_MARKER}
  grep -Fxq 'archive_role=read_only_audit_history' {LEGACY_STATE_MARKER}
  grep -Fxq 'mutation_authority=disabled' {LEGACY_STATE_MARKER}
fi
if [ -e {APP_DIR} ] && [ ! -L {APP_DIR} ]; then
  test ! -e {LEGACY_APP_ARCHIVE}
  mv {APP_DIR} {LEGACY_APP_ARCHIVE}
  chown -R root:root {LEGACY_APP_ARCHIVE}
  chmod -R a-w {LEGACY_APP_ARCHIVE}
fi
current=""
if [ -L {APP_DIR} ]; then current="$(readlink -f {APP_DIR})"; fi
if [ -n "$current" ] && [ "$current" != '{release}' ]; then
  case "$current" in {RELEASES_DIR}/*) ;; *) exit 41 ;; esac
  current_sha="$(basename "$current")"
  printf '%s' "$current_sha" | grep -Eq '^[0-9a-f]{{40}}$'
  verify_projection_release "$current" "$current_sha"
  ln -s "$current" {RUNTIME_ROOT}/.previous.next.$$
  mv -Tf {RUNTIME_ROOT}/.previous.next.$$ {PREVIOUS_LINK}
fi
ln -s '{release}' {RUNTIME_ROOT}/.app.next.$$
mv -Tf {RUNTIME_ROOT}/.app.next.$$ {APP_DIR}
systemctl daemon-reload
systemctl enable {SERVICE_NAME} >/dev/null 2>&1
systemctl restart {SERVICE_NAME}
{_remote_loopback_wait_script(str(release))}
test "$(readlink -f {APP_DIR})" = '{release}'
cat > {NGINX_SITE_AVAILABLE} <<'DCP_NGINX_FINAL'
{final_nginx}DCP_NGINX_FINAL
chmod 0644 {NGINX_SITE_AVAILABLE}
nginx -t >/dev/null 2>&1
systemctl reload nginx
test "$(grep -Fc 'auth_basic off;' {NGINX_SITE_AVAILABLE})" = '1'
"""


def _projection_environment() -> str:
    return f"""AUTHORITY_ROLE=hosted_projection_v2
DEV_CONTROL_PLANE_PROJECTION_V2_HOST={LOOPBACK_HOST}
DEV_CONTROL_PLANE_PROJECTION_V2_PORT={LOOPBACK_PORT}
DEV_CONTROL_PLANE_PROJECTION_V2_DB={PROJECTION_DB}
DEV_CONTROL_PLANE_PROJECTION_V2_HMAC_KEY_FILE={PROJECTION_KEY_DEST}
DEV_CONTROL_PLANE_PROJECTION_V2_MAX_SKEW_SECONDS=300
DEV_CONTROL_PLANE_PROJECTION_V2_STALE_AFTER_SECONDS=120
PYTHONDONTWRITEBYTECODE=1
"""


def _systemd_unit() -> str:
    return f"""[Unit]
Description=Development Control Plane hosted read-only projection v2
Documentation=https://github.com/{EXPECTED_REPOSITORY}
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User={PROJECTION_SERVICE_USER}
Group={PROJECTION_SERVICE_GROUP}
WorkingDirectory={APP_DIR}
EnvironmentFile={ENV_FILE}
Environment=AUTHORITY_ROLE=hosted_projection_v2
Environment=PYTHONDONTWRITEBYTECODE=1
ExecStart=/usr/bin/python3 {APP_DIR}/apps/dev_control_plane_projection_v2.py
Restart=on-failure
RestartSec=5
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
PrivateDevices=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true
CapabilityBoundingSet=
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
ReadWritePaths={PROJECTION_STATE_DIR}
ReadOnlyPaths={RELEASES_DIR} {PROJECTION_SECRETS_DIR}
InaccessiblePaths=-{LEGACY_STATE_DIR} -{ARCHIVE_DIR} -{RUNTIME_ROOT}/.codex -{RUNTIME_ROOT}/secrets -{RUNTIME_ROOT}/tools

[Install]
WantedBy=multi-user.target
"""


def _nginx_config(*, include_tls: bool, allow_signed_ingest: bool = True) -> str:
    port_80 = f"""server {{
    listen 80;
    server_name {PRIMARY_DOMAIN} {WWW_DOMAIN};

    location ^~ /.well-known/acme-challenge/ {{
        root {ACME_ROOT};
        try_files $uri =404;
    }}

    location / {{
        return 301 https://$host$request_uri;
    }}
}}
"""
    if not include_tls:
        return port_80
    ingest_auth = "        auth_basic off;\n" if allow_signed_ingest else ""
    return port_80 + f"""
server {{
    listen 443 ssl http2;
    server_name {PRIMARY_DOMAIN} {WWW_DOMAIN};

    ssl_certificate {CERT_FULLCHAIN};
    ssl_certificate_key {CERT_PRIVATE_KEY};

    auth_basic "Development Control Plane";
    auth_basic_user_file {AUTH_FILE};

    location = /api/v2/ingest {{
{ingest_auth}        # The application still requires the independent projection HMAC.
        client_max_body_size 1m;
        proxy_pass http://{LOOPBACK_HOST}:{LOOPBACK_PORT};
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }}

    location / {{
        proxy_pass http://{LOOPBACK_HOST}:{LOOPBACK_PORT};
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }}
}}
"""


def _activation_marker_path(release_sha: str) -> Path:
    if not FULL_SHA_RE.fullmatch(release_sha):
        raise RuntimeError("activation_marker_release_identity_invalid")
    return ARCHIVE_DIR / f"projection-v2-{release_sha}.ACTIVATING"


def _activation_transaction_dir(release_sha: str) -> Path:
    if not FULL_SHA_RE.fullmatch(release_sha):
        raise RuntimeError("activation_transaction_release_identity_invalid")
    return ARCHIVE_DIR / f"projection-v2-{release_sha}.ROLLBACK"


def _activation_receipt_path(release_sha: str, outcome: str) -> Path:
    if not FULL_SHA_RE.fullmatch(release_sha) or outcome not in {
        "DEPLOYED",
        "RESTORED",
        "QUARANTINED",
        "STAGING_CLEANED",
    }:
        raise RuntimeError("activation_receipt_identity_invalid")
    return ARCHIVE_DIR / f"projection-v2-{release_sha}.{outcome}"


def _remote_staging_cleanup_function(release_sha: str) -> str:
    if not FULL_SHA_RE.fullmatch(release_sha):
        raise RuntimeError("staging_cleanup_release_identity_invalid")
    receipt = _activation_receipt_path(release_sha, "STAGING_CLEANED")
    prefix = f".incoming-{release_sha}-"
    return f"""cleanup_projection_staging() {{
  removed="$(
python3 - '{RELEASES_DIR}' '{prefix}' <<'DCP_CLEAN_STAGING'
from pathlib import Path
import shutil
import stat
import sys
root = Path(sys.argv[1])
prefix = sys.argv[2]
count = 0
for path in sorted(root.iterdir() if root.exists() else ()):
    if not path.name.startswith(prefix):
        continue
    metadata = path.lstat()
    if not stat.S_ISDIR(metadata.st_mode) or path.is_symlink():
        raise RuntimeError("unsafe projection staging path")
    shutil.rmtree(path)
    count += 1
print(count)
DCP_CLEAN_STAGING
)"
  printf '%s' "$removed" | grep -Eq '^[0-9]+$'
  receipt_next='{receipt}.next.'$$
  cat > "$receipt_next" <<DCP_STAGING_CLEANED
schema=dev-control-plane/hosted-rollout-receipt/v2
release_sha={release_sha}
outcome=staging_cleaned
removed_count=$removed
DCP_STAGING_CLEANED
  chown root:root "$receipt_next"
  chmod 0444 "$receipt_next"
  python3 - "$receipt_next" <<'DCP_FSYNC_STAGING_CLEANUP'
import os
import sys
descriptor = os.open(sys.argv[1], os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
try:
    os.fsync(descriptor)
finally:
    os.close(descriptor)
DCP_FSYNC_STAGING_CLEANUP
  mv -Tf "$receipt_next" '{receipt}'
  python3 - '{ARCHIVE_DIR}' <<'DCP_FSYNC_STAGING_CLEANUP_DIR'
import os
import sys
descriptor = os.open(sys.argv[1], os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
try:
    os.fsync(descriptor)
finally:
    os.close(descriptor)
DCP_FSYNC_STAGING_CLEANUP_DIR
}}
"""


def _remote_activation_guard_function(release_sha: str) -> str:
    marker = _activation_marker_path(release_sha)
    transaction_dir = _activation_transaction_dir(release_sha)
    snapshot = transaction_dir / "pre-mutation.tar"
    state = transaction_dir / "pre-mutation.state"
    return f"""verify_activation_transaction() {{
  test -d '{transaction_dir}'
  test ! -L '{transaction_dir}'
  test "$(stat -c '%a' '{transaction_dir}')" = '700'
  test "$(stat -c '%u:%g' '{transaction_dir}')" = '0:0'
  test -f '{snapshot}'
  test ! -L '{snapshot}'
  test "$(stat -c '%a' '{snapshot}')" = '600'
  test "$(stat -c '%u:%g' '{snapshot}')" = '0:0'
  test -f '{state}'
  test ! -L '{state}'
  test "$(stat -c '%a' '{state}')" = '600'
  test "$(stat -c '%u:%g' '{state}')" = '0:0'
  test -f '{marker}'
  test ! -L '{marker}'
  test "$(stat -c '%a' '{marker}')" = '444'
  test "$(stat -c '%u:%g' '{marker}')" = '0:0'
  grep -Fxq 'schema=dev-control-plane/hosted-rollout-transaction/v2' '{marker}'
  grep -Fxq 'release_sha={release_sha}' '{marker}'
  grep -Fxq 'schema=dev-control-plane/hosted-rollout-snapshot/v2' '{state}'
  grep -Fxq 'release_sha={release_sha}' '{state}'
  expected_snapshot_sha="$(sed -n 's/^snapshot_sha256=//p' '{state}')"
  printf '%s' "$expected_snapshot_sha" | grep -Eq '^[0-9a-f]{{64}}$'
  test "$(sha256sum '{snapshot}' | awk '{{print $1}}')" = "$expected_snapshot_sha"
  grep -Fxq "snapshot_sha256=$expected_snapshot_sha" '{marker}'
}}
"""


def _remote_begin_activation_script(release_sha: str) -> str:
    if not FULL_SHA_RE.fullmatch(release_sha):
        raise RuntimeError("begin_activation_release_identity_invalid")
    marker = _activation_marker_path(release_sha)
    transaction_dir = _activation_transaction_dir(release_sha)
    snapshot = transaction_dir / "pre-mutation.tar"
    state = transaction_dir / "pre-mutation.state"
    paths_file = transaction_dir / "snapshot.paths"
    deployed_receipt = _activation_receipt_path(release_sha, "DEPLOYED")
    restored_receipt = _activation_receipt_path(release_sha, "RESTORED")
    snapshot_paths = " ".join(f"'{path}'" for path in ROLLOUT_SNAPSHOT_PATHS)
    return f"""set -euo pipefail
umask 077
install -d -o root -g root -m 0755 '{RUNTIME_ROOT}' '{ARCHIVE_DIR}'
touch '{ROLLOUT_LOCK}'
chown root:root '{ROLLOUT_LOCK}'
chmod 0600 '{ROLLOUT_LOCK}'
exec 9>'{ROLLOUT_LOCK}'
flock -w 300 -x 9
{_remote_manifest_verifier_function()}
{_remote_activation_guard_function(release_sha)}
if [ -e '{marker}' ]; then
  verify_activation_transaction
  printf 'begin=existing\n'
  exit 0
fi
if find '{ARCHIVE_DIR}' -maxdepth 1 -mindepth 1 \\( -name 'projection-v2-*.ACTIVATING' -o -name 'projection-v2-*.QUARANTINED' \\) -print -quit | grep -q .; then
  exit 81
fi
if [ -e '{transaction_dir}' ]; then
  test -d '{transaction_dir}'
  test ! -L '{transaction_dir}'
  test -f '{deployed_receipt}' -o -f '{restored_receipt}' -o ! -e '{marker}'
  python3 - '{transaction_dir}' <<'DCP_REMOVE_STALE_TRANSACTION'
from pathlib import Path
import shutil
import stat
import sys
path = Path(sys.argv[1])
metadata = path.lstat()
if not stat.S_ISDIR(metadata.st_mode) or path.is_symlink():
    raise RuntimeError("unsafe stale transaction path")
shutil.rmtree(path)
DCP_REMOVE_STALE_TRANSACTION
fi
install -d -o root -g root -m 0700 '{transaction_dir}'
prior_app_kind=absent
prior_release_sha=none
if [ -L '{APP_DIR}' ]; then
  prior_app="$(readlink -f '{APP_DIR}')"
  case "$prior_app" in '{RELEASES_DIR}'/*) ;; *) exit 82 ;; esac
  prior_release_sha="$(basename "$prior_app")"
  printf '%s' "$prior_release_sha" | grep -Eq '^[0-9a-f]{{40}}$'
  verify_projection_release "$prior_app" "$prior_release_sha"
  prior_app_kind=v2
elif [ -d '{APP_DIR}' ]; then
  prior_app_kind=legacy
elif [ -e '{APP_DIR}' ]; then
  exit 83
fi
service_active=no
if systemctl is-active --quiet '{SERVICE_NAME}'; then service_active=yes; fi
service_enabled=no
if systemctl is-enabled --quiet '{SERVICE_NAME}'; then service_enabled=yes; fi
nginx_active=no
if systemctl is-active --quiet nginx; then nginx_active=yes; fi
certbot_active=no
if systemctl is-active --quiet certbot.timer; then certbot_active=yes; fi
certbot_enabled=no
if systemctl is-enabled --quiet certbot.timer; then certbot_enabled=yes; fi
if [ "$service_active" = yes ] && [ "$prior_app_kind" = absent ]; then exit 84; fi
: > '{paths_file}'
chmod 0600 '{paths_file}'
for snapshot_path in {snapshot_paths}; do
  if [ -e "$snapshot_path" ] || [ -L "$snapshot_path" ]; then
    printf '%s\n' "$snapshot_path" | sed 's#^/##' >> '{paths_file}'
  fi
done
tar --create --file='{snapshot}.next' --acls --xattrs --numeric-owner --one-file-system --directory=/ --files-from='{paths_file}'
chown root:root '{snapshot}.next'
chmod 0600 '{snapshot}.next'
snapshot_sha="$(sha256sum '{snapshot}.next' | awk '{{print $1}}')"
printf '%s' "$snapshot_sha" | grep -Eq '^[0-9a-f]{{64}}$'
cat > '{state}.next' <<DCP_SNAPSHOT_STATE
schema=dev-control-plane/hosted-rollout-snapshot/v2
release_sha={release_sha}
prior_app_kind=$prior_app_kind
prior_release_sha=$prior_release_sha
service_active=$service_active
service_enabled=$service_enabled
nginx_active=$nginx_active
certbot_active=$certbot_active
certbot_enabled=$certbot_enabled
snapshot_sha256=$snapshot_sha
DCP_SNAPSHOT_STATE
chown root:root '{state}.next'
chmod 0600 '{state}.next'
mv -Tf '{snapshot}.next' '{snapshot}'
mv -Tf '{state}.next' '{state}'
python3 - '{snapshot}' '{state}' '{paths_file}' '{transaction_dir}' <<'DCP_FSYNC_SNAPSHOT'
import os
import sys
for raw in sys.argv[1:]:
    descriptor = os.open(raw, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
DCP_FSYNC_SNAPSHOT
cat > '{marker}.next' <<DCP_ACTIVATION_MARKER
schema=dev-control-plane/hosted-rollout-transaction/v2
release_sha={release_sha}
snapshot_sha256=$snapshot_sha
DCP_ACTIVATION_MARKER
chown root:root '{marker}.next'
chmod 0444 '{marker}.next'
python3 - '{marker}.next' <<'DCP_FSYNC_MARKER'
import os
import sys
descriptor = os.open(sys.argv[1], os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
try:
    os.fsync(descriptor)
finally:
    os.close(descriptor)
DCP_FSYNC_MARKER
mv -Tf '{marker}.next' '{marker}'
python3 - '{ARCHIVE_DIR}' <<'DCP_FSYNC_ARCHIVE'
import os
import sys
descriptor = os.open(sys.argv[1], os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
try:
    os.fsync(descriptor)
finally:
    os.close(descriptor)
DCP_FSYNC_ARCHIVE
verify_activation_transaction
printf 'begin=created\n'
"""


def _remote_process_binding_function() -> str:
    return f"""verify_projection_process() {{
  expected_release="$1"
  test "$(systemctl is-active {SERVICE_NAME})" = 'active'
  test "$(readlink -f {APP_DIR})" = "$expected_release"
  main_pid="$(systemctl show -p MainPID --value {SERVICE_NAME})"
  printf '%s' "$main_pid" | grep -Eq '^[1-9][0-9]*$'
  test "$main_pid" -gt 1
  test -d "/proc/$main_pid"
  test "$(readlink -f "/proc/$main_pid/cwd")" = "$expected_release"
  test "$(ps -o user= -p "$main_pid" | tr -d ' ')" = '{PROJECTION_SERVICE_USER}'
  systemctl cat --no-pager {SERVICE_NAME} | grep -Fxq 'InaccessiblePaths=-{LEGACY_STATE_DIR} -{ARCHIVE_DIR} -{RUNTIME_ROOT}/.codex -{RUNTIME_ROOT}/secrets -{RUNTIME_ROOT}/tools'
  for hidden in {LEGACY_STATE_DIR} {ARCHIVE_DIR} {RUNTIME_ROOT}/.codex {RUNTIME_ROOT}/secrets {RUNTIME_ROOT}/tools; do
    test ! -e "/proc/$main_pid/root$hidden"
  done
  test -r "/proc/$main_pid/root{PROJECTION_KEY_DEST}"
  tr '\\0' ' ' < "/proc/$main_pid/cmdline" | grep -Fq '/usr/bin/python3 {APP_DIR}/apps/dev_control_plane_projection_v2.py'
  grep -Fq '/{SERVICE_NAME}' "/proc/$main_pid/cgroup"
  listener="$(ss -ltnp 'sport = :{LOOPBACK_PORT}' 2>/dev/null | tail -n +2)"
  test -n "$listener"
  printf '%s' "$listener" | grep -Fq "pid=$main_pid,"
  printf 'main_pid=%s\n' "$main_pid"
}}
wait_for_projection_process() {{
  expected_release="$1"
  for attempt in $(seq 1 60); do
    if verify_projection_process "$expected_release" >/dev/null 2>&1 && curl -fsS --connect-timeout 2 --max-time 5 http://{LOOPBACK_HOST}:{LOOPBACK_PORT}/api/v2/health 2>/dev/null | python3 -c 'import json,sys; p=json.load(sys.stdin); raise SystemExit(0 if (p.get("status") == "ready" and p.get("service_role") == "hosted_projection_v2" and p.get("control_authority") is False and p.get("mutation_routes_enabled") is False and p.get("projection_ingestion_enabled") is True) else 1)' 2>/dev/null; then
      return 0
    fi
    sleep 1
  done
  return 1
}}
"""


def _remote_loopback_wait_script(expected_release: str) -> str:
    release = Path(expected_release)
    if release.parent != RELEASES_DIR or not FULL_SHA_RE.fullmatch(release.name):
        raise RuntimeError("loopback_expected_release_invalid")
    return f"""{_remote_process_binding_function()}
wait_for_projection_process '{release}'
"""


def _remote_loopback_health() -> dict[str, Any]:
    command = f"""set -euo pipefail
{_remote_manifest_verifier_function()}
{_remote_process_binding_function()}
current="$(readlink -f {APP_DIR})"
case "$current" in {RELEASES_DIR}/*) ;; *) exit 51 ;; esac
sha="$(basename "$current")"
printf '%s' "$sha" | grep -Eq '^[0-9a-f]{{40}}$'
verify_projection_release "$current" "$sha"
verify_projection_process "$current"
payload="$(curl -fsS --connect-timeout 2 --max-time 10 http://{LOOPBACK_HOST}:{LOOPBACK_PORT}/api/v2/health 2>/dev/null)"
printf '%s' "$payload" | python3 -c 'import json,sys; p=json.load(sys.stdin); d=p.get("database") or {{}}; ok=(p.get("status") == "ready" and p.get("service_role") == "hosted_projection_v2" and p.get("control_authority") is False and p.get("mutation_routes_enabled") is False and p.get("projection_ingestion_enabled") is True and d.get("journal_mode") == "wal" and d.get("synchronous") == "full" and d.get("rebuildable") is True); print("health=verified") if ok else None; raise SystemExit(0 if ok else 1)'
printf 'release=%s\n' "$sha"
state="$(curl -fsS --connect-timeout 2 --max-time 10 http://{LOOPBACK_HOST}:{LOOPBACK_PORT}/api/v2/state 2>/dev/null)"
printf '%s' "$state" | python3 -c 'import json,sys; p=json.load(sys.stdin); raise SystemExit(0 if (p.get("service_role") == "hosted_projection_v2" and p.get("control_authority") is False and p.get("mutation_routes_enabled") is False and isinstance(p.get("tasks"), list)) else 1)'
dashboard="$(curl -fsS --connect-timeout 2 --max-time 10 http://{LOOPBACK_HOST}:{LOOPBACK_PORT}/runs/live 2>/dev/null)"
printf '%s' "$dashboard" | grep -Fq 'Мониторинг задач'
if printf '%s' "$dashboard" | grep -Fq '<pre'; then exit 52; fi
"""
    completed = _ssh(command)
    if completed.returncode != 0:
        raise RuntimeError("loopback_projection_health_failed")
    values = _parse_key_value_lines(completed.stdout.splitlines())
    release = _safe_release_identity(values.get("release"))
    main_pid = _safe_int(values.get("main_pid"))
    if values.get("health") != "verified" or not release or main_pid is None or main_pid <= 1:
        raise RuntimeError("loopback_projection_health_invalid")
    return {
        "service_role": "hosted_projection_v2",
        "control_authority": False,
        "mutation_routes_enabled": False,
        "projection_ingestion_enabled": True,
        "release_sha": release,
        "systemd_main_pid": main_pid,
        "process_release_bound": True,
        "socket_owner_bound": True,
    }


def _prove_live_read_only(
    *,
    expected_release: str | None = None,
    projection_key: bytes | None = None,
) -> dict[str, Any]:
    loopback = _remote_loopback_health()
    if expected_release and loopback.get("release_sha") != expected_release:
        raise RuntimeError("active_release_identity_mismatch")
    probes = {
        "ui_auth": _curl_probe(f"https://{PRIMARY_DOMAIN}/"),
        "live_auth": _curl_probe(f"https://{PRIMARY_DOMAIN}/runs/live"),
        "state_auth": _curl_probe(f"https://{PRIMARY_DOMAIN}/api/v2/state"),
        "unsigned_ingest": _curl_probe(
            f"https://{PRIMARY_DOMAIN}/api/v2/ingest",
            method="POST",
            body=b"{}",
            headers=("Content-Type: application/json",),
        ),
        "legacy_mcp_denied": _curl_probe(
            f"https://{PRIMARY_DOMAIN}/mcp",
            method="POST",
            body=b"{}",
            headers=("Content-Type: application/json",),
        ),
        "legacy_oauth_denied": _curl_probe(
            f"https://{PRIMARY_DOMAIN}/oauth/token",
            method="POST",
            body=b"{}",
            headers=("Content-Type: application/json",),
        ),
        "acme_route": _curl_probe(
            f"http://{PRIMARY_DOMAIN}/.well-known/acme-challenge/dcp-v2-route-proof-not-present"
        ),
        "webcore": _curl_probe(WEBCORE_PROBE_URL),
    }
    if projection_key is not None:
        probes["signed_ingest_key"] = _signed_ingest_key_probe(projection_key)
    expected = {
        "ui_auth": {401, 403},
        "live_auth": {401, 403},
        "state_auth": {401, 403},
        "unsigned_ingest": {401},
        "legacy_mcp_denied": {401, 403},
        "legacy_oauth_denied": {401, 403},
        "acme_route": {404},
        "webcore": {200, 301, 302, 401, 403, 404},
    }
    if projection_key is not None:
        # A correctly signed but deliberately schema-invalid body reaches the
        # projection parser and returns 422 without mutating projection state.
        expected["signed_ingest_key"] = {422}
    failed = [
        name
        for name, probe in probes.items()
        if probe.transport != "ok" or probe.http_status not in expected[name]
    ]
    if failed:
        raise RuntimeError("post_rollout_read_only_or_tls_proof_failed:" + ",".join(sorted(failed)))
    return {
        "loopback": loopback,
        "public_routes": {
            name: {"http_status": probe.http_status, "transport": probe.transport}
            for name, probe in probes.items()
        },
        "single_control_authority": True,
        "legacy_mutation_routes_public": False,
    }


def _rollback_plan_payload() -> dict[str, Any]:
    return {
        "current_link": str(APP_DIR),
        "previous_link": str(PREVIOUS_LINK),
        "allowed_target": str(RELEASES_DIR / "<previous-verified-v2-sha>"),
        "steps": [
            "verify previous resolves to an immutable SHA release under releases/",
            "verify its deploy identity and projection-v2 entrypoint",
            "atomically swap current and previous symlinks",
            "restart the same projection-only systemd unit and prove no-authority health",
        ],
        "legacy_fallback": False,
        "state_deletion": False,
    }


def _remote_rollback_eligibility() -> dict[str, Any]:
    completed = _ssh(_remote_rollback_eligibility_script())
    if completed.returncode != 0:
        raise RuntimeError("projection_v2_rollback_not_eligible")
    values = _parse_key_value_lines(completed.stdout.splitlines())
    current_sha = _safe_release_identity(values.get("current_sha"))
    if (
        values.get("eligible") == "no"
        and values.get("reason_code") == "not_eligible_first_release"
        and current_sha
        and values.get("verified_release_count") == "1"
    ):
        return {
            "eligible": False,
            "reason_code": "not_eligible_first_release",
            "current_sha": current_sha,
            "previous_sha": None,
            "distinct": False,
            "verified_release_count": 1,
        }
    previous_sha = _safe_release_identity(values.get("previous_sha"))
    if values.get("eligible") != "yes" or not current_sha or not previous_sha or current_sha == previous_sha:
        raise RuntimeError("projection_v2_rollback_eligibility_invalid")
    return {
        "eligible": True,
        "current_sha": current_sha,
        "previous_sha": previous_sha,
        "distinct": True,
    }


def _remote_rollback_eligibility_script() -> str:
    return f"""set -euo pipefail
test -f {ROLLOUT_LOCK}
exec 9<{ROLLOUT_LOCK}
flock -w 30 -s 9
{_remote_manifest_verifier_function()}
if find {ARCHIVE_DIR} -maxdepth 1 -mindepth 1 \\( -name 'projection-v2-*.ACTIVATING' -o -name 'projection-v2-*.QUARANTINED' \\) -print -quit | grep -q .; then exit 60; fi
test -L {APP_DIR}
current="$(readlink -f {APP_DIR})"
case "$current" in {RELEASES_DIR}/*) ;; *) exit 61 ;; esac
current_sha="$(basename "$current")"
printf '%s' "$current_sha" | grep -Eq '^[0-9a-f]{{40}}$'
verify_projection_release "$current" "$current_sha"
if [ ! -L {PREVIOUS_LINK} ]; then
  verified_release_count=0
  only_verified_release=""
  for release in {RELEASES_DIR}/*; do
    [ -d "$release" ] || continue
    sha="$(basename "$release")"
    if printf '%s' "$sha" | grep -Eq '^[0-9a-f]{{40}}$' && verify_projection_release "$release" "$sha" >/dev/null 2>&1; then
      verified_release_count=$((verified_release_count + 1))
      only_verified_release="$release"
    fi
  done
  test "$verified_release_count" = '1'
  test "$only_verified_release" = "$current"
  printf 'eligible=no\nreason_code=not_eligible_first_release\ncurrent_sha=%s\nverified_release_count=1\n' "$current_sha"
  exit 0
fi
previous="$(readlink -f {PREVIOUS_LINK})"
test "$previous" != "$current"
case "$previous" in {RELEASES_DIR}/*) ;; *) exit 62 ;; esac
previous_sha="$(basename "$previous")"
printf '%s' "$previous_sha" | grep -Eq '^[0-9a-f]{{40}}$'
verify_projection_release "$previous" "$previous_sha"
printf 'eligible=yes\ncurrent_sha=%s\nprevious_sha=%s\n' "$(basename "$current")" "$(basename "$previous")"
"""


ROLLBACK_FAULT_BOUNDARIES = (
    "app_link_swapped",
    "previous_link_swapped",
    "service_restart_attempted",
    "app_link_restored",
    "previous_link_restored",
    "service_restore_attempted",
    "service_stopped",
    "service_disabled",
    "site_unlinked",
    "nginx_reloaded",
    "app_unlinked",
)


def _rollback_fault_boundary(name: str, fault_after: str | None) -> str:
    if name not in ROLLBACK_FAULT_BOUNDARIES:
        raise RuntimeError("rollback_fault_boundary_invalid")
    return "exit 97" if fault_after == name else ":"


def _remote_rollback_script(
    *,
    expected_current_sha: str,
    expected_previous_sha: str,
    fault_after: str | None = None,
) -> str:
    if (
        not FULL_SHA_RE.fullmatch(expected_current_sha)
        or not FULL_SHA_RE.fullmatch(expected_previous_sha)
        or expected_current_sha == expected_previous_sha
    ):
        raise RuntimeError("projection_v2_rollback_identity_invalid")
    if fault_after is not None and fault_after not in ROLLBACK_FAULT_BOUNDARIES:
        raise RuntimeError("rollback_fault_boundary_invalid")
    current_release = RELEASES_DIR / expected_current_sha
    previous_release = RELEASES_DIR / expected_previous_sha
    return f"""set -euo pipefail
exec 9>{ROLLOUT_LOCK}
flock -w 300 -x 9
	{_remote_manifest_verifier_function()}
	{_remote_process_binding_function()}
	{_remote_activation_guard_function(expected_previous_sha)}
	verify_activation_transaction
{_remote_rollback_marker_conflict_guard(expected_previous_sha)}
test -L {PREVIOUS_LINK}
test -L {APP_DIR}
previous="$(readlink -f {PREVIOUS_LINK})"
current="$(readlink -f {APP_DIR})"
test "$current" = '{current_release}'
test "$previous" = '{previous_release}'
test "$previous" != "$current"
verify_projection_release "$current" '{expected_current_sha}'
verify_projection_release "$previous" '{expected_previous_sha}'
grep -Fq 'ExecStart=/usr/bin/python3 {APP_DIR}/apps/dev_control_plane_projection_v2.py' /etc/systemd/system/{SERVICE_NAME}
	ln -s "$previous" {RUNTIME_ROOT}/.app.rollback.$$
	mv -Tf {RUNTIME_ROOT}/.app.rollback.$$ {APP_DIR}
	{_rollback_fault_boundary("app_link_swapped", fault_after)} # DCP_FAULT_BOUNDARY app_link_swapped
	ln -s "$current" {RUNTIME_ROOT}/.previous.rollback.$$
	mv -Tf {RUNTIME_ROOT}/.previous.rollback.$$ {PREVIOUS_LINK}
	{_rollback_fault_boundary("previous_link_swapped", fault_after)} # DCP_FAULT_BOUNDARY previous_link_swapped
	restart_status=0
	systemctl restart {SERVICE_NAME} || restart_status=$?
	{_rollback_fault_boundary("service_restart_attempted", fault_after)} # DCP_FAULT_BOUNDARY service_restart_attempted
	if [ "$restart_status" = 0 ] && wait_for_projection_process '{previous_release}'; then
  test "$(readlink -f {APP_DIR})" = "$previous"
  exit 0
fi
# A failed rollback activation must not become a new ambiguous live state.
# Restore the exact original links/process; if even that cannot be proven,
# quarantine the service and public site in this same locked operation.
	ln -s "$current" {RUNTIME_ROOT}/.app.rollback-restore.$$
	mv -Tf {RUNTIME_ROOT}/.app.rollback-restore.$$ {APP_DIR}
	{_rollback_fault_boundary("app_link_restored", fault_after)} # DCP_FAULT_BOUNDARY app_link_restored
	ln -s "$previous" {RUNTIME_ROOT}/.previous.rollback-restore.$$
	mv -Tf {RUNTIME_ROOT}/.previous.rollback-restore.$$ {PREVIOUS_LINK}
	{_rollback_fault_boundary("previous_link_restored", fault_after)} # DCP_FAULT_BOUNDARY previous_link_restored
	restore_status=0
	systemctl restart {SERVICE_NAME} || restore_status=$?
	{_rollback_fault_boundary("service_restore_attempted", fault_after)} # DCP_FAULT_BOUNDARY service_restore_attempted
	if [ "$restore_status" = 0 ] && wait_for_projection_process '{current_release}'; then
  exit 74
fi
	systemctl stop {SERVICE_NAME} >/dev/null 2>&1 || true
	{_rollback_fault_boundary("service_stopped", fault_after)} # DCP_FAULT_BOUNDARY service_stopped
	systemctl disable {SERVICE_NAME} >/dev/null 2>&1 || true
	{_rollback_fault_boundary("service_disabled", fault_after)} # DCP_FAULT_BOUNDARY service_disabled
if [ -L {NGINX_SITE_ENABLED} ]; then
  test "$(readlink -f {NGINX_SITE_ENABLED})" = '{NGINX_SITE_AVAILABLE}'
	  unlink {NGINX_SITE_ENABLED}
	  {_rollback_fault_boundary("site_unlinked", fault_after)} # DCP_FAULT_BOUNDARY site_unlinked
elif [ -e {NGINX_SITE_ENABLED} ]; then
  exit 75
fi
nginx -t >/dev/null 2>&1
	systemctl reload nginx
	{_rollback_fault_boundary("nginx_reloaded", fault_after)} # DCP_FAULT_BOUNDARY nginx_reloaded
	if [ -L {APP_DIR} ]; then unlink {APP_DIR}; elif [ -e {APP_DIR} ]; then exit 76; fi
	{_rollback_fault_boundary("app_unlinked", fault_after)} # DCP_FAULT_BOUNDARY app_unlinked
test ! -e {APP_DIR}
test ! -e {NGINX_SITE_ENABLED}
test "$(systemctl is-active {SERVICE_NAME} 2>/dev/null || true)" != 'active'
if ss -ltnp 'sport = :{LOOPBACK_PORT}' 2>/dev/null | tail -n +2 | grep -q .; then exit 77; fi
exit 78
"""


def _remote_rollback_marker_conflict_guard(
    expected_release_sha: str,
    *,
    archive_dir: Path = ARCHIVE_DIR,
) -> str:
    """Allow only the exact already-verified rollback transaction marker."""

    if not FULL_SHA_RE.fullmatch(expected_release_sha):
        raise RuntimeError("rollback_marker_release_identity_invalid")
    archive_text = str(archive_dir)
    if not archive_dir.is_absolute() or not re.fullmatch(r"[A-Za-z0-9_./-]+", archive_text):
        raise RuntimeError("rollback_marker_archive_path_invalid")
    expected_marker = archive_dir / f"projection-v2-{expected_release_sha}.ACTIVATING"
    return f"""if find '{archive_dir}' -maxdepth 1 -mindepth 1 \\
  \\( \\( -name 'projection-v2-*.ACTIVATING' ! -path '{expected_marker}' \\) \\
     -o -name 'projection-v2-*.QUARANTINED' \\) \\
  -print -quit | grep -q .; then
  exit 60
fi"""


def _planned_remote_steps(cert_domains: Sequence[str], release_sha: str) -> list[str]:
    sha = release_sha if FULL_SHA_RE.fullmatch(release_sha) else "<verified-origin-main-sha>"
    return [
        f"source gate: exact {EXPECTED_REPOSITORY}, clean worktree, HEAD == origin/main",
        f"minimal rsync (without --delete) to immutable {RELEASES_DIR}/{sha}",
        f"secure-copy external 0600 HMAC key to {PROJECTION_KEY_DEST} without printing content",
        f"archive legacy app metadata and preserve {LEGACY_STATE_DIR} via {LEGACY_STATE_MARKER}",
        f"write projection-only systemd unit {SERVICE_NAME} with AUTHORITY_ROLE=hosted_projection_v2",
        f"persist ACME route/hook and ensure certificate for {list(cert_domains)} is fresh >= {MIN_CERT_DAYS} days",
        f"atomically switch {APP_DIR}; set {PREVIOUS_LINK} only to a verified v2 SHA release",
        "prove loopback no-authority health, Basic Auth/read-only public routes, TLS, and WebCore",
    ]


def _validation_allows_live(status: str) -> bool:
    return status in {"passed", "allowed_with_warning", "renewal_required"}


def _evaluate_dns_gate(
    local_dns: dict[str, Any],
    doh_dns: dict[str, Any],
    remote_dns: dict[str, Any],
) -> DnsGateResult:
    blockers: list[str] = []
    warnings: list[str] = []
    if remote_dns.get("returncode") != 0:
        blockers.append("remote_dns_probe_unavailable")
    remote_domains = remote_dns.get("domains", {})
    for domain in (PRIMARY_DOMAIN, WWW_DOMAIN):
        local = local_dns.get(domain, {})
        system_ips = _as_list(local.get("system"))
        dig_ips = _as_list(local.get("default_dig"))
        if system_ips != [TARGET_HOST_IP] or dig_ips != [TARGET_HOST_IP]:
            warnings.append(f"local_dns_stale:{domain}")
        for provider in ("cloudflare", "google"):
            if _as_list(doh_dns.get(domain, {}).get(provider)) != [TARGET_HOST_IP]:
                blockers.append(f"doh_{provider}_mismatch:{domain}")
        remote = remote_domains.get(domain, {})
        if _as_list(remote.get("getent_ahostsv4")) != [TARGET_HOST_IP]:
            blockers.append(f"remote_dns_getent_mismatch:{domain}")
        remote_dig = _as_list(remote.get("dig"))
        if remote_dig != ["<dig-missing>"] and remote_dig != [TARGET_HOST_IP]:
            blockers.append(f"remote_dns_dig_mismatch:{domain}")
    if blockers:
        return DnsGateResult("blocked", sorted(set(blockers)), sorted(set(warnings)), [])
    return DnsGateResult(
        "allowed_with_warning" if warnings else "passed",
        [],
        sorted(set(warnings)),
        [PRIMARY_DOMAIN, WWW_DOMAIN],
    )


def _local_dns_probe(domains: Sequence[str]) -> dict[str, dict[str, list[str]]]:
    return {domain: {"system": _system_resolve(domain), "default_dig": _dig_resolve(domain)} for domain in domains}


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
    completed = subprocess.run(
        ["dig", "+time=3", "+tries=1", "+short", domain, "A"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return []
    return sorted({line.strip() for line in completed.stdout.splitlines() if line.strip()})


def _doh_resolve(domain: str, provider: str) -> list[str]:
    url = {
        "cloudflare": f"https://cloudflare-dns.com/dns-query?name={domain}&type=A",
        "google": f"https://dns.google/resolve?name={domain}&type=A",
    }[provider]
    completed = subprocess.run(
        [
            "/usr/bin/curl",
            "-q",
            "--silent",
            "--max-time",
            "10",
            "--proto",
            "=https",
            "-H",
            "accept: application/dns-json",
            url,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        env={"HOME": str(ROOT), "PATH": "/usr/bin:/bin", "LC_ALL": "C"},
    )
    if completed.returncode != 0:
        return []
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return []
    return sorted(
        {
            str(item["data"])
            for item in payload.get("Answer", [])
            if isinstance(item, Mapping) and item.get("type") == 1 and "data" in item
        }
    )


def _remote_dns_probe() -> dict[str, Any]:
    command = f"""set -u
for domain in {PRIMARY_DOMAIN} {WWW_DOMAIN}; do
  printf 'DOMAIN %s\n' "$domain"
  printf 'GETENT '
  getent ahostsv4 "$domain" 2>/dev/null | awk '{{print $1}}' | sort -u | tr '\n' ' '
  printf '\n'
  if command -v dig >/dev/null 2>&1; then
    printf 'DIG '
    dig +time=3 +tries=1 +short "$domain" A 2>/dev/null | sort -u | tr '\n' ' '
    printf '\n'
  else
    printf 'DIG <dig-missing>\n'
  fi
done
"""
    completed = _ssh(command)
    return {
        "returncode": completed.returncode,
        "domains": _parse_remote_dns_stdout(completed.stdout.splitlines()) if completed.returncode == 0 else {},
    }


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
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value]
    return [str(value)]


def _signed_ingest_key_probe(projection_key: bytes) -> CurlProbeResult:
    """Prove the installed key through a signed, non-mutating schema failure."""

    key = bytes(projection_key)
    if not 32 <= len(key.rstrip(b"\r\n")) <= 4096 or len(key) > 4096:
        raise RuntimeError("projection_key_snapshot_invalid")
    body = b"{}"
    timestamp = max(1, int(time.time()))
    supervisor_id = "hosted-rollout-key-canary"
    event_id = f"key-canary-{timestamp}"
    idempotency_key = f"key-canary-{timestamp}"
    body_digest = hashlib.sha256(body).hexdigest()
    canonical = (
        "\n".join(
            (
                "DCP-PROJECTION-V2",
                "POST",
                "/api/v2/ingest",
                str(timestamp),
                supervisor_id,
                "1",
                "1",
                "1",
                event_id,
                idempotency_key,
                body_digest,
            )
        )
        + "\n"
    ).encode("utf-8")
    signature = hmac_new(key, canonical, "sha256").hexdigest()
    headers = {
        "Content-Type": "application/json",
        "X-DCP-Timestamp": str(timestamp),
        "X-DCP-Supervisor-ID": supervisor_id,
        "X-DCP-Generation": "1",
        "X-DCP-Sequence": "1",
        "X-DCP-Revision": "1",
        "X-DCP-Event-ID": event_id,
        "X-DCP-Idempotency-Key": idempotency_key,
        "X-DCP-Signature": "sha256=" + signature,
    }
    temporary = Path(tempfile.mkdtemp(prefix="dev-control-plane-ingest-key-proof-"))
    try:
        temporary.chmod(0o700)
        body_path = temporary / "request.body"
        config_path = temporary / "curl.config"
        _private_write_bytes(body_path, body)
        config_lines = [
            f'url = "https://{PRIMARY_DOMAIN}/api/v2/ingest"',
            'request = "POST"',
            'proto = "=https"',
            "tlsv1.2",
            "silent",
            f'data-binary = "@{_curl_config_quote(str(body_path))}"',
            'output = "/dev/null"',
            'write-out = "%{http_code}"',
            'connect-timeout = "5"',
            'max-time = "20"',
        ]
        for name, value in sorted(headers.items()):
            config_lines.append(f'header = "{_curl_config_quote(name + ": " + value)}"')
        _private_write_bytes(config_path, ("\n".join(config_lines) + "\n").encode("utf-8"))
        completed = subprocess.run(
            ["/usr/bin/curl", "-q", "--config", str(config_path)],
            cwd=ROOT,
            capture_output=True,
            check=False,
            env={"HOME": str(temporary), "PATH": "/usr/bin:/bin", "LC_ALL": "C"},
        )
        raw_status = completed.stdout.decode("ascii", errors="ignore").strip()
        http_status = int(raw_status) if raw_status.isdigit() else 0
        transport = _classify_curl_transport(completed.returncode)
        return CurlProbeResult(
            status="passed" if completed.returncode == 0 and http_status == 422 else "failed",
            http_status=http_status,
            transport=transport,
            curl_exit=int(completed.returncode),
        )
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def _private_write_bytes(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _curl_config_quote(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _curl_probe(
    url: str,
    *,
    method: str = "GET",
    body: bytes | None = None,
    headers: Sequence[str] = (),
) -> CurlProbeResult:
    command = [
        "/usr/bin/curl",
        "-q",
        "--silent",
        "--output",
        "/dev/null",
        "--write-out",
        "%{http_code}",
        "--connect-timeout",
        "5",
        "--max-time",
        "20",
        "--proto",
        "=" + (urlsplit(url).scheme or "invalid"),
        "--request",
        method,
    ]
    if urlsplit(url).scheme == "https":
        command.insert(command.index("--request"), "--tlsv1.2")
    for header in headers:
        command.extend(("--header", header))
    if body is not None:
        command.extend(("--data-binary", "@-"))
    command.append(url)
    completed = subprocess.run(
        command,
        cwd=ROOT,
        input=body,
        capture_output=True,
        check=False,
        env={"HOME": str(ROOT), "PATH": "/usr/bin:/bin", "LC_ALL": "C"},
    )
    raw_status = completed.stdout.decode("ascii", errors="ignore").strip()
    http_status = int(raw_status) if raw_status.isdigit() else 0
    transport = _classify_curl_transport(completed.returncode)
    return CurlProbeResult(
        status="passed" if completed.returncode == 0 and http_status > 0 else "failed",
        http_status=http_status,
        transport=transport,
        curl_exit=int(completed.returncode),
    )


def _classify_curl_transport(returncode: int) -> str:
    if returncode == 0:
        return "ok"
    if returncode in TLS_CURL_EXIT_CODES:
        return "tls_error"
    return "network_error"


def _approved_probe_url(url: str, allowed_hosts: set[str]) -> bool:
    parsed = urlsplit(url)
    return parsed.scheme == "https" and parsed.hostname in allowed_hosts and parsed.username is None and parsed.password is None


def _ssh(command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/usr/bin/ssh", *SSH_EXEC_OPTIONS, SSH_ALIAS, command],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _ssh_checked(command: str, *, operation: str) -> None:
    completed = _ssh(command)
    if completed.returncode != 0:
        raise RuntimeError(f"{operation}_failed")


def _ssh_bytes_checked(command: str, payload: bytes, *, operation: str) -> None:
    """Send a bounded secret snapshot on stdin without exposing it in argv/logs."""

    completed = subprocess.run(
        ["/usr/bin/ssh", *SSH_EXEC_OPTIONS, SSH_ALIAS, command],
        cwd=ROOT,
        input=payload,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"{operation}_failed")


def _run_checked(command: Sequence[str], *, operation: str) -> None:
    completed = subprocess.run(list(command), cwd=ROOT, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"{operation}_failed")


def _git_run(*args: str) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    for key in tuple(environment):
        if key.startswith("GIT_CONFIG_") or key in {"GIT_SSH", "GIT_SSH_COMMAND"}:
            environment.pop(key, None)
    # The fetch uses a literal canonical SSH URL and an explicit ssh command.
    # System/global Git config is therefore unnecessary and cannot inject URL
    # rewrites or transport commands. Local rewrites are separately rejected
    # before any fetch.
    environment.update(
        {
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def _local_git_value(*args: str) -> str | None:
    completed = _git_run(*args)
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


def _full_sha_or_none(value: str | None) -> str | None:
    return value if value and FULL_SHA_RE.fullmatch(value) else None


def _parse_key_value_lines(lines: Sequence[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in lines:
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if re.fullmatch(r"[a-z0-9_]+", key):
            result[key] = value.strip()[:200]
    return result


def _safe_int(value: Any) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _safe_bool(value: Any) -> bool | None:
    text = str(value or "").lower()
    if text == "true":
        return True
    if text == "false":
        return False
    return None


def _safe_release_identity(value: Any) -> str | None:
    text = str(value or "")
    return text if FULL_SHA_RE.fullmatch(text) else None


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
