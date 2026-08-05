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
import secrets
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
DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
ATTEMPT_RE = re.compile(r"^[0-9a-f]{32}$")
MIN_ORPHAN_TRANSACTION_AGE_SECONDS = 900
ROLLOUT_STAGES = (
    "snapshot_created",
    "runtime_prepared",
    "release_finalized",
    "projection_key_installed",
    "install_started",
    "certbot_timer_stopped",
    "legacy_authority_stopped",
    "config_written",
    "nginx_guarded",
    "acme_route_proved",
    "certificate_refresh_started",
    "certificate_refresh_failed",
    "certificate_ready",
    "legacy_archived",
    "app_link_switched",
    "service_ready",
    "nginx_final",
    "public_proof_started",
    "public_proof_passed",
)
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

    quarantine_status = subparsers.add_parser("quarantine-status")
    quarantine_status.add_argument("--release-sha", required=True)
    quarantine_status.set_defaults(handler=_handle_quarantine_status)

    quarantine_resolve = subparsers.add_parser("quarantine-resolve")
    quarantine_resolve.add_argument("--release-sha", required=True)
    quarantine_resolve.add_argument("--snapshot-sha256", required=True)
    quarantine_resolve.add_argument("--replacement-sha", required=True)
    quarantine_resolve_mode = quarantine_resolve.add_mutually_exclusive_group(required=True)
    quarantine_resolve_mode.add_argument("--dry-run", action="store_true")
    quarantine_resolve_mode.add_argument("--live", action="store_true")
    quarantine_resolve.set_defaults(handler=_handle_quarantine_resolve)

    transaction_status = subparsers.add_parser("transaction-status")
    transaction_status.add_argument("--release-sha", required=True)
    transaction_status.set_defaults(handler=_handle_transaction_status)

    transaction_recover = subparsers.add_parser("transaction-recover")
    transaction_recover.add_argument("--release-sha", required=True)
    transaction_recover.add_argument("--attempt-id", required=True)
    transaction_recover.add_argument("--snapshot-sha256", required=True)
    transaction_recover.add_argument("--expected-stage", required=True)
    transaction_recover_mode = transaction_recover.add_mutually_exclusive_group(required=True)
    transaction_recover_mode.add_argument("--dry-run", action="store_true")
    transaction_recover_mode.add_argument("--live", action="store_true")
    transaction_recover.set_defaults(handler=_handle_transaction_recover)

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


def _handle_quarantine_status(args: argparse.Namespace) -> int:
    if not FULL_SHA_RE.fullmatch(args.release_sha):
        _print_json({"status": "blocked", "blockers": ["invalid_quarantine_release_sha"]})
        return 1
    ssh_target = _local_ssh_target_gate()
    if ssh_target.get("status") != "passed":
        _print_json(
            {
                "status": "failed",
                "blockers": list(ssh_target.get("blockers") or ("ssh_target_gate_failed",)),
            }
        )
        return 1
    try:
        evidence = _remote_quarantine_status(args.release_sha)
    except RuntimeError as exc:
        _print_json({"status": "failed", "blockers": [str(exc)]})
        return 1
    _print_json({"status": "quarantined_safe_disabled", "evidence": evidence})
    return 0


def _handle_quarantine_resolve(args: argparse.Namespace) -> int:
    if not FULL_SHA_RE.fullmatch(args.release_sha):
        _print_json(
            {"status": "blocked", "live_executed": False, "blockers": ["invalid_quarantine_release_sha"]}
        )
        return 1
    if not DIGEST_RE.fullmatch(args.snapshot_sha256):
        _print_json(
            {
                "status": "blocked",
                "live_executed": False,
                "blockers": ["invalid_quarantine_snapshot_sha256"],
            }
        )
        return 1
    if (
        not FULL_SHA_RE.fullmatch(args.replacement_sha)
        or args.replacement_sha == args.release_sha
    ):
        _print_json(
            {
                "status": "blocked",
                "live_executed": False,
                "blockers": ["invalid_or_reused_quarantine_replacement_sha"],
            }
        )
        return 1
    source = _source_gate(enforced=True, fetch_origin=True)
    if source.status != "passed" or source.head_sha != args.replacement_sha:
        _print_json(
            {
                "status": "blocked",
                "live_executed": False,
                "blockers": ["quarantine_replacement_not_exact_origin_main"],
            }
        )
        return 1
    ssh_target = _local_ssh_target_gate()
    if ssh_target.get("status") != "passed":
        _print_json(
            {
                "status": "failed",
                "live_executed": False,
                "blockers": list(ssh_target.get("blockers") or ("ssh_target_gate_failed",)),
            }
        )
        return 1
    try:
        evidence = _remote_quarantine_status(args.release_sha)
    except RuntimeError as exc:
        _print_json(
            {"status": "failed", "live_executed": False, "blockers": [str(exc)]}
        )
        return 1
    if evidence["snapshot_sha256"] != args.snapshot_sha256:
        _print_json(
            {
                "status": "blocked",
                "live_executed": False,
                "blockers": ["quarantine_snapshot_digest_mismatch"],
                "evidence": evidence,
            }
        )
        return 1
    prior_replacement = evidence.get("replacement_sha")
    prior_anchor_sha256 = evidence.get("replacement_anchor_sha256")
    if prior_replacement is not None and prior_replacement != args.replacement_sha:
        if not evidence.get("replacement_supersession_eligible") or not _git_is_ancestor(
            prior_replacement, args.replacement_sha
        ):
            _print_json(
                {
                    "status": "blocked",
                    "live_executed": False,
                    "blockers": ["quarantine_replacement_supersession_not_admitted"],
                    "evidence": evidence,
                }
            )
            return 1
    if args.dry_run:
        _print_json(
            {
                "status": "dry_run_passed",
                "live_executed": False,
                "recovery_mode": "preserve_evidence_and_allow_full_redeploy_only",
                "replacement_sha": args.replacement_sha,
                "evidence": evidence,
            }
        )
        return 0
    repeated_target = _local_ssh_target_gate()
    if repeated_target.get("status") != "passed":
        _print_json(
            {
                "status": "failed",
                "live_executed": False,
                "blockers": ["ssh_target_gate_changed_before_quarantine_resolution"],
            }
        )
        return 1
    repeated_source = _source_gate(enforced=True, fetch_origin=True)
    if repeated_source.status != "passed" or repeated_source.head_sha != args.replacement_sha:
        _print_json(
            {
                "status": "failed",
                "live_executed": False,
                "blockers": ["source_changed_before_quarantine_resolution"],
            }
        )
        return 1
    try:
        resolved = _resolve_remote_quarantine(
            args.release_sha,
            args.snapshot_sha256,
            args.replacement_sha,
            expected_prior_replacement=prior_replacement,
            expected_prior_anchor_sha256=prior_anchor_sha256,
        )
    except RuntimeError as exc:
        _print_json(
            {"status": "failed", "live_executed": False, "blockers": [str(exc)]}
        )
        return 1
    _print_json(
        {
            "status": "quarantine_resolved_safe_disabled",
            "live_executed": True,
            "recovery_mode": "preserve_evidence_and_allow_full_redeploy_only",
            "replacement_sha": args.replacement_sha,
            "evidence": resolved,
        }
    )
    return 0


def _handle_transaction_status(args: argparse.Namespace) -> int:
    if not FULL_SHA_RE.fullmatch(args.release_sha):
        _print_json({"status": "blocked", "blockers": ["invalid_transaction_release_sha"]})
        return 1
    ssh_target = _local_ssh_target_gate()
    if ssh_target.get("status") != "passed":
        _print_json(
            {
                "status": "failed",
                "blockers": list(ssh_target.get("blockers") or ("ssh_target_gate_failed",)),
            }
        )
        return 1
    try:
        evidence = _remote_transaction_status(args.release_sha)
    except RuntimeError as exc:
        _print_json({"status": "failed", "blockers": [str(exc)]})
        return 1
    _print_json({"status": "transaction_verified", "evidence": evidence})
    return 0


def _handle_transaction_recover(args: argparse.Namespace) -> int:
    allowed_stages = {"marker_created", *ROLLOUT_STAGES}
    identity_valid = (
        FULL_SHA_RE.fullmatch(args.release_sha)
        and ATTEMPT_RE.fullmatch(args.attempt_id)
        and DIGEST_RE.fullmatch(args.snapshot_sha256)
        and args.expected_stage in allowed_stages
    )
    if not identity_valid:
        _print_json(
            {
                "status": "blocked",
                "live_executed": False,
                "blockers": ["invalid_transaction_recovery_identity"],
            }
        )
        return 1
    source = _source_gate(enforced=True, fetch_origin=True)
    if source.status != "passed" or source.head_sha != source.origin_main_sha:
        _print_json(
            {
                "status": "blocked",
                "live_executed": False,
                "blockers": ["transaction_recovery_runner_not_exact_origin_main"],
            }
        )
        return 1
    ssh_target = _local_ssh_target_gate()
    if ssh_target.get("status") != "passed":
        _print_json(
            {
                "status": "failed",
                "live_executed": False,
                "blockers": list(ssh_target.get("blockers") or ("ssh_target_gate_failed",)),
            }
        )
        return 1
    try:
        evidence = _remote_transaction_status(args.release_sha)
    except RuntimeError as exc:
        _print_json(
            {"status": "failed", "live_executed": False, "blockers": [str(exc)]}
        )
        return 1
    expected = {
        "attempt_id": args.attempt_id,
        "snapshot_sha256": args.snapshot_sha256,
        "stage": args.expected_stage,
    }
    if any(evidence.get(key) != value for key, value in expected.items()):
        _print_json(
            {
                "status": "blocked",
                "live_executed": False,
                "blockers": ["transaction_recovery_evidence_mismatch"],
                "evidence": evidence,
            }
        )
        return 1
    if not evidence.get("stale_recovery_eligible"):
        _print_json(
            {
                "status": "blocked",
                "live_executed": False,
                "blockers": ["transaction_not_stale_for_recovery"],
                "evidence": evidence,
            }
        )
        return 1
    if args.dry_run:
        _print_json(
            {
                "status": "dry_run_passed",
                "live_executed": False,
                "recovery_mode": "exact_stale_transaction_fail_safe_only",
                "evidence": evidence,
            }
        )
        return 0
    repeated_target = _local_ssh_target_gate()
    repeated_source = _source_gate(enforced=True, fetch_origin=True)
    if repeated_target.get("status") != "passed" or (
        repeated_source.status != "passed"
        or repeated_source.head_sha != repeated_source.origin_main_sha
        or repeated_source.head_sha != source.head_sha
    ):
        _print_json(
            {
                "status": "failed",
                "live_executed": False,
                "blockers": ["transaction_recovery_gates_changed_before_mutation"],
            }
        )
        return 1
    try:
        outcome = _recover_failed_projection_rollout(
            args.release_sha,
            args.attempt_id,
            expected_snapshot_sha256=args.snapshot_sha256,
            expected_stage=args.expected_stage,
            minimum_stage_age_seconds=MIN_ORPHAN_TRANSACTION_AGE_SECONDS,
        )
    except RuntimeError as exc:
        _print_json(
            {"status": "failed", "live_executed": False, "blockers": [str(exc)]}
        )
        return 1
    _print_json(
        {
            "status": "transaction_recovered_fail_safe",
            "live_executed": True,
            "outcome": outcome,
            "release_sha": args.release_sha,
            "attempt_id": args.attempt_id,
            "prior_evidence": evidence,
        }
    )
    return 0


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
        rollback_attempt_id = secrets.token_hex(16)
        begin_status = _begin_remote_activation(rollback_release, rollback_attempt_id)
        if begin_status == "busy":
            raise RuntimeError("rollback_transaction_busy")
        if begin_status not in {"created", "existing_owned"}:
            raise RuntimeError("rollback_transaction_begin_invalid")
        transaction_started = True
        try:
            _ssh_checked(
                _remote_rollback_script(
                    expected_current_sha=str(eligibility["current_sha"]),
                    expected_previous_sha=rollback_release,
                    attempt_id=rollback_attempt_id,
                ),
                operation="projection_v2_rollback",
            )
            proof = _prove_live_read_only(expected_release=rollback_release)
            _complete_remote_activation(rollback_release, rollback_attempt_id)
        except RuntimeError as exc:
            recovery = _recover_failed_projection_rollout(
                rollback_release,
                rollback_attempt_id,
            )
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
        remote = _remote_preflight(expected_release_sha=source.head_sha)
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


def _remote_preflight(*, expected_release_sha: str | None = None) -> dict[str, Any]:
    candidate_release = expected_release_sha if _safe_release_identity(expected_release_sha) else "none"
    command = rf"""set -u
if [ -f '{ROLLOUT_LOCK}' ]; then exec 9<'{ROLLOUT_LOCK}'; flock -w 30 -s 9 || exit 97; fi
{_remote_resolved_quarantine_guard_function()}
for tool in nginx certbot rsync python3 curl openssl systemctl ss flock ps tar sha256sum find findmnt sync awk; do
  if command -v "$tool" >/dev/null 2>&1; then printf 'tool_%s=ready\n' "$tool"; else printf 'tool_%s=missing\n' "$tool"; fi
done
printf 'webcore_site=%s\n' "$(test -e {WEBCORE_NGINX_SITE} && echo present || echo missing)"
if [ -s {AUTH_FILE} ] && [ ! -L {AUTH_FILE} ]; then
  auth_mode="$(stat -c '%a' {AUTH_FILE} 2>/dev/null || true)"
  case "$auth_mode" in 600|640) printf 'basic_auth=ready\n' ;; *) printf 'basic_auth=unsafe\n' ;; esac
else
  printf 'basic_auth=missing\n'
fi
service_active="$(systemctl show -p ActiveState --value {SERVICE_NAME} 2>/dev/null)" || exit 98
service_pid="$(systemctl show -p MainPID --value {SERVICE_NAME} 2>/dev/null)" || exit 98
printf 'service_active=%s\n' "$service_active"
health="$(curl -fsS --connect-timeout 2 --max-time 5 http://{LOOPBACK_HOST}:{LOOPBACK_PORT}/api/v2/health 2>/dev/null || true)"
if [ -n "$health" ]; then
  printf '%s' "$health" | python3 -c 'import json,sys; p=json.load(sys.stdin); print("health=ok"); print("health_role="+str(p.get("service_role",""))); print("health_control="+str(p.get("control_authority","")).lower()); print("health_mutation="+str(p.get("mutation_routes_enabled","")).lower())' 2>/dev/null || printf 'health=invalid\n'
else
  printf 'health=unavailable\n'
fi
listener="$(ss -H -ltnp 'sport = :{LOOPBACK_PORT}' 2>/dev/null)" || exit 98
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
certbot_timer_enabled="$(systemctl show -p UnitFileState --value certbot.timer 2>/dev/null)" || exit 98
certbot_timer_active="$(systemctl show -p ActiveState --value certbot.timer 2>/dev/null)" || exit 98
printf 'certbot_timer_enabled=%s\n' "$certbot_timer_enabled"
printf 'certbot_timer_active=%s\n' "$certbot_timer_active"
if grep -Fq 'location ^~ /.well-known/acme-challenge/' {NGINX_SITE_AVAILABLE} 2>/dev/null; then printf 'acme_route=yes\n'; else printf 'acme_route=no\n'; fi
if grep -Eq '^authenticator[[:space:]]*=[[:space:]]*webroot' {CERT_RENEWAL_FILE} 2>/dev/null; then printf 'renewal_webroot=yes\n'; else printf 'renewal_webroot=no\n'; fi
if test -x {CERT_DEPLOY_HOOK}; then printf 'deploy_hook=yes\n'; else printf 'deploy_hook=no\n'; fi
if verify_no_unresolved_rollout_markers none '{candidate_release}' >/dev/null 2>&1; then printf 'rollout_guard=ready\n'; else printf 'rollout_guard=unresolved_quarantine_or_activation\n'; fi
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
            "find",
            "findmnt",
            "sync",
            "awk",
        )
    }
    blockers.extend(f"remote_tool_missing:{name}" for name, ready in tools.items() if not ready)
    if values.get("webcore_site") != "present":
        blockers.append("webcore_nginx_marker_missing")
    if values.get("basic_auth") != "ready":
        blockers.append("basic_auth_file_missing_or_unsafe")
    if values.get("rollout_guard") != "ready":
        blockers.append("unresolved_hosted_rollout_transaction")
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
        "rollout_guard": values.get("rollout_guard", "unknown"),
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
    attempt_id = secrets.token_hex(16)
    staging_name = f".incoming-{release_sha}-{attempt_id}"
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
            begin_status = _begin_remote_activation(release_sha, attempt_id)
            if begin_status == "busy":
                raise RuntimeError("rollout_transaction_busy")
            if begin_status not in {"created", "existing_owned"}:
                raise RuntimeError("rollout_transaction_begin_invalid")
            transaction_started = True
            _ssh_checked(
                _remote_prepare_runtime_script(staging_dir, release_sha, attempt_id),
                operation="prepare_projection_runtime",
            )
            if not _remote_release_exists(release_sha, manifest_digest):
                _run_checked(
                    _release_rsync_command(staging_dir, package_root, release_sha, attempt_id),
                    operation="copy_projection_release",
                )
                _ssh_checked(
                    _remote_finalize_release_script(
                        release_sha,
                        staging_dir,
                        manifest_digest,
                        attempt_id,
                    ),
                    operation="finalize_immutable_projection_release",
                )
        repeated_source = _source_gate(enforced=True, fetch_origin=True)
        if repeated_source.status != "passed" or repeated_source.head_sha != release_sha:
            raise RuntimeError("source_changed_during_projection_packaging")
        _install_projection_key_snapshot(projection_key_material, release_sha, attempt_id)
        _ssh_checked(
            _remote_install_script(
                cert_domains,
                release_sha,
                attempt_id=attempt_id,
                force_certificate_refresh=force_certificate_refresh,
            ),
            operation="activate_projection_v2_release",
        )
        _record_remote_rollout_stage(release_sha, attempt_id, "public_proof_started")
        proof = _prove_live_read_only(
            expected_release=release_sha,
            projection_key=projection_key_material,
        )
        _record_remote_rollout_stage(release_sha, attempt_id, "public_proof_passed")
        _complete_remote_activation(release_sha, attempt_id)
        return proof
    except RuntimeError as exc:
        if not transaction_started:
            raise
        try:
            recovery = _recover_failed_projection_rollout(release_sha, attempt_id)
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


def _begin_remote_activation(release_sha: str, attempt_id: str) -> str:
    if not FULL_SHA_RE.fullmatch(release_sha) or not ATTEMPT_RE.fullmatch(attempt_id):
        raise RuntimeError("begin_projection_v2_activation_identity_invalid")
    completed = _ssh(_remote_begin_activation_script(release_sha, attempt_id))
    if completed.returncode == 0:
        try:
            values = _parse_exact_sanitized_key_value_lines(
                completed.stdout,
                {"begin", "release_sha"},
            )
        except ValueError as exc:
            raise RuntimeError("begin_projection_v2_activation_receipt_invalid") from exc
        if values["release_sha"] != release_sha or values["begin"] not in {
            "created",
            "existing_owned",
            "busy",
        }:
            raise RuntimeError("begin_projection_v2_activation_receipt_invalid")
        return values["begin"]

    readback = _ssh(_remote_activation_owner_readback_script(release_sha, attempt_id))
    if readback.returncode != 0:
        raise RuntimeError("begin_projection_v2_activation_state_unavailable")
    try:
        values = _parse_exact_sanitized_key_value_lines(
            readback.stdout,
            {"owner", "release_sha"},
        )
    except ValueError as exc:
        raise RuntimeError("begin_projection_v2_activation_state_unavailable") from exc
    if values["release_sha"] != release_sha:
        raise RuntimeError("begin_projection_v2_activation_state_unavailable")
    if values["owner"] == "owned":
        return "existing_owned"
    if values["owner"] == "foreign":
        return "busy"
    if values["owner"] == "absent":
        raise RuntimeError("begin_projection_v2_activation_failed_before_transaction")
    raise RuntimeError("begin_projection_v2_activation_state_unavailable")


def _remote_activation_owner_readback_script(release_sha: str, attempt_id: str) -> str:
    if not FULL_SHA_RE.fullmatch(release_sha) or not ATTEMPT_RE.fullmatch(attempt_id):
        raise RuntimeError("activation_owner_readback_identity_invalid")
    marker = _activation_marker_path(release_sha)
    transaction = _activation_transaction_dir(release_sha)
    state = transaction / "pre-mutation.state"
    return f"""set -euo pipefail
test -f '{ROLLOUT_LOCK}'
exec 9<'{ROLLOUT_LOCK}'
flock -w 30 -s 9
{_remote_activation_snapshot_guard_function(release_sha)}
if [ ! -e '{marker}' ] && [ ! -L '{marker}' ]; then
  printf 'owner=absent\nrelease_sha={release_sha}\n'
  exit 0
fi
test -f '{marker}' && test ! -L '{marker}'
test "$(stat -c '%a' '{marker}')" = '444'
test "$(stat -c '%u:%g' '{marker}')" = '0:0'
test "$(stat -c '%h' '{marker}')" = '1'
verify_activation_snapshot
grep -Fxq 'schema=dev-control-plane/hosted-rollout-transaction/v2' '{marker}'
grep -Fxq 'release_sha={release_sha}' '{marker}'
test "$(grep -Ec '^attempt_id=[0-9a-f]{{32}}$' '{marker}')" = '1'
marker_attempt="$(sed -n 's/^attempt_id=//p' '{marker}')"
test -f '{state}' && test ! -L '{state}'
grep -Fxq "attempt_id=$marker_attempt" '{state}'
grep -Fxq "snapshot_sha256=$(sed -n 's/^snapshot_sha256=//p' '{state}')" '{marker}'
if [ "$marker_attempt" = '{attempt_id}' ]; then owner=owned; else owner=foreign; fi
printf 'owner=%s\nrelease_sha={release_sha}\n' "$owner"
"""


def _complete_remote_activation(release_sha: str, attempt_id: str) -> None:
    if not ATTEMPT_RE.fullmatch(attempt_id):
        raise RuntimeError("complete_activation_attempt_identity_invalid")
    release = RELEASES_DIR / release_sha
    marker = _activation_marker_path(release_sha)
    transaction_dir = _activation_transaction_dir(release_sha)
    receipt = _activation_receipt_path(release_sha, "DEPLOYED")
    expected_unit_sha256 = hashlib.sha256(_systemd_unit().encode("utf-8")).hexdigest()
    _ssh_checked(
        f"""set -euo pipefail
exec 9>{ROLLOUT_LOCK}
flock -w 300 -x 9
{_remote_manifest_verifier_function()}
	{_remote_process_binding_function()}
	{_remote_activation_guard_function(release_sha, attempt_id)}
	{_remote_resolved_quarantine_guard_function()}
	{_remote_quarantine_remediation_function(release_sha)}
	{_remote_staging_cleanup_function(release_sha)}
	verify_activation_transaction
	verify_projection_release '{release}' '{release_sha}'
	verify_candidate_projection_unit
	verify_projection_process '{release}' >/dev/null
	cleanup_projection_staging
if [ -e '{receipt}' ] || [ -L '{receipt}' ]; then
  verify_prior_projection_unit '{release_sha}'
else
  receipt_next={receipt}.next.$$
  cat > "$receipt_next" <<'DCP_DEPLOYED_RECEIPT'
schema=dev-control-plane/hosted-rollout-receipt/v2
release_sha={release_sha}
outcome=deployed
unit_sha256={expected_unit_sha256}
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
fi
verify_prior_projection_unit '{release_sha}'
seal_quarantine_remediations
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


def _remote_transaction_status(release_sha: str) -> dict[str, Any]:
    if not FULL_SHA_RE.fullmatch(release_sha):
        raise RuntimeError("transaction_status_release_identity_invalid")
    completed = _ssh(_remote_transaction_status_script(release_sha))
    if completed.returncode != 0:
        raise RuntimeError("transaction_status_unavailable_or_unsafe")
    required = {
        "transaction",
        "release_sha",
        "attempt_id",
        "snapshot_sha256",
        "stage",
        "stage_age_seconds",
        "prior_kind",
        "prior_release_sha",
    }
    try:
        values = _parse_exact_sanitized_key_value_lines(completed.stdout, required)
    except ValueError as exc:
        raise RuntimeError("transaction_status_receipt_invalid") from exc
    if (
        values["transaction"] != "verified_active"
        or values["release_sha"] != release_sha
        or not ATTEMPT_RE.fullmatch(values["attempt_id"])
        or not DIGEST_RE.fullmatch(values["snapshot_sha256"])
        or values["stage"] not in {"marker_created", *ROLLOUT_STAGES}
        or values["prior_kind"] not in {"v2", "legacy", "absent"}
        or not re.fullmatch(r"[0-9]{1,12}", values["stage_age_seconds"])
    ):
        raise RuntimeError("transaction_status_receipt_invalid")
    age_seconds = int(values["stage_age_seconds"])
    if values["prior_kind"] == "v2":
        if not FULL_SHA_RE.fullmatch(values["prior_release_sha"]):
            raise RuntimeError("transaction_status_receipt_invalid")
    elif values["prior_release_sha"] != "none":
        raise RuntimeError("transaction_status_receipt_invalid")
    return {
        "release_sha": release_sha,
        "attempt_id": values["attempt_id"],
        "snapshot_sha256": values["snapshot_sha256"],
        "stage": values["stage"],
        "stage_age_seconds": age_seconds,
        "minimum_recovery_age_seconds": MIN_ORPHAN_TRANSACTION_AGE_SECONDS,
        "stale_recovery_eligible": age_seconds >= MIN_ORPHAN_TRANSACTION_AGE_SECONDS,
        "prior_kind": values["prior_kind"],
        "prior_release_sha": (
            None if values["prior_release_sha"] == "none" else values["prior_release_sha"]
        ),
        "mutation_authority": "fenced_to_exact_attempt",
        "raw_remote_payload_exposed": False,
    }


def _remote_transaction_status_script(release_sha: str) -> str:
    if not FULL_SHA_RE.fullmatch(release_sha):
        raise RuntimeError("transaction_status_release_identity_invalid")
    marker = _activation_marker_path(release_sha)
    transaction = _activation_transaction_dir(release_sha)
    state = transaction / "pre-mutation.state"
    stage_file = transaction / "stage.state"
    allowed_stages = "|".join(ROLLOUT_STAGES)
    return f"""set -euo pipefail
test -f '{ROLLOUT_LOCK}'
exec 9<'{ROLLOUT_LOCK}'
flock -w 30 -s 9
for required_tool in find findmnt sync awk; do command -v "$required_tool" >/dev/null 2>&1; done
{_remote_activation_guard_function(release_sha)}
verify_activation_transaction
test "$(wc -l < '{marker}')" = '4'
test "$(wc -l < '{state}')" = '11'
attempt_id="$(sed -n 's/^attempt_id=//p' '{marker}')"
test "$(grep -Ec '^attempt_id=[0-9a-f]{{32}}$' '{marker}')" = '1'
grep -Fxq "attempt_id=$attempt_id" '{state}'
stage=marker_created
activity_path='{marker}'
if [ -e '{stage_file}' ]; then
  test -f '{stage_file}' && test ! -L '{stage_file}'
  test "$(stat -c '%a' '{stage_file}')" = '600'
  test "$(stat -c '%u:%g' '{stage_file}')" = '0:0'
  test "$(stat -c '%h' '{stage_file}')" = '1'
  test "$(wc -l < '{stage_file}')" = '4'
  grep -Fxq 'schema=dev-control-plane/hosted-rollout-stage/v2' '{stage_file}'
  grep -Fxq 'release_sha={release_sha}' '{stage_file}'
  grep -Fxq "attempt_id=$attempt_id" '{stage_file}'
  stage="$(sed -n 's/^stage=//p' '{stage_file}')"
  case "$stage" in {allowed_stages}) ;; *) exit 96 ;; esac
  activity_path='{stage_file}'
fi
now="$(date +%s)"
activity_mtime="$(stat -c '%Y' "$activity_path")"
printf '%s:%s' "$now" "$activity_mtime" | grep -Eq '^[0-9]+:[0-9]+$'
test "$now" -ge "$activity_mtime"
stage_age_seconds=$((now - activity_mtime))
prior_kind="$(sed -n 's/^prior_app_kind=//p' '{state}')"
prior_release_sha="$(sed -n 's/^prior_release_sha=//p' '{state}')"
case "$prior_kind" in v2) printf '%s' "$prior_release_sha" | grep -Eq '^[0-9a-f]{{40}}$' ;; legacy|absent) test "$prior_release_sha" = none ;; *) exit 97 ;; esac
printf 'transaction=verified_active\nrelease_sha={release_sha}\n'
printf 'attempt_id=%s\nsnapshot_sha256=%s\n' "$attempt_id" "$(sed -n 's/^snapshot_sha256=//p' '{state}')"
printf 'stage=%s\nstage_age_seconds=%s\n' "$stage" "$stage_age_seconds"
printf 'prior_kind=%s\nprior_release_sha=%s\n' "$prior_kind" "$prior_release_sha"
"""


def _recover_failed_projection_rollout(
    release_sha: str,
    attempt_id: str,
    *,
    expected_snapshot_sha256: str | None = None,
    expected_stage: str | None = None,
    minimum_stage_age_seconds: int | None = None,
) -> str:
    if not ATTEMPT_RE.fullmatch(attempt_id):
        raise RuntimeError("failed_rollout_recovery_attempt_identity_invalid")
    completed = _ssh(
        _remote_failed_rollout_recovery_script(
            release_sha,
            attempt_id,
            expected_snapshot_sha256=expected_snapshot_sha256,
            expected_stage=expected_stage,
            minimum_stage_age_seconds=minimum_stage_age_seconds,
        )
    )
    if completed.returncode != 0:
        raise RuntimeError("failed_rollout_recovery_unavailable")
    values = _parse_key_value_lines(completed.stdout.splitlines())
    outcome = values.get("recovery")
    if outcome not in {"completed", "restored", "quarantined", "not_activated"}:
        raise RuntimeError("failed_rollout_recovery_receipt_invalid")
    if outcome == "restored" and values.get("prior_kind") != "v2":
        raise RuntimeError("failed_rollout_recovery_receipt_invalid")
    if outcome == "restored" and values.get("prior_kind") == "v2" and not _safe_release_identity(
        values.get("release")
    ):
        raise RuntimeError("failed_rollout_recovery_receipt_invalid")
    return outcome


def _remote_authority_state_guard_function() -> str:
    """Return fail-closed systemd and listener probes for remote scripts."""

    return f"""require_unit_inactive() {{
  local unit="$1" active_state
  active_state="$(systemctl show -p ActiveState --value "$unit" 2>/dev/null)" || return 1
  test "$active_state" = inactive || return 1
}}
require_unit_disabled() {{
  local unit="$1" unit_file_state
  unit_file_state="$(systemctl show -p UnitFileState --value "$unit" 2>/dev/null)" || return 1
  test "$unit_file_state" = disabled || return 1
}}
require_unit_main_pid_zero() {{
  local unit="$1" main_pid
  main_pid="$(systemctl show -p MainPID --value "$unit" 2>/dev/null)" || return 1
  test "$main_pid" = 0 || return 1
}}
require_projection_port_free() {{
  local listeners
  listeners="$(ss -H -ltnp 'sport = :{LOOPBACK_PORT}' 2>/dev/null)" || return 1
  test -z "$listeners" || return 1
}}
reload_nginx_if_active() {{
  local active_state
  active_state="$(systemctl show -p ActiveState --value nginx 2>/dev/null)" || return 1
  case "$active_state" in
    active) systemctl reload nginx >/dev/null 2>&1 || return 1 ;;
    inactive) ;;
    *) return 1 ;;
  esac
}}
capture_unit_active_flag() {{
  local unit="$1" active_state
  active_state="$(systemctl show -p ActiveState --value "$unit" 2>/dev/null)" || return 1
  case "$active_state" in active) printf yes ;; inactive) printf no ;; *) return 1 ;; esac
}}
capture_unit_enabled_flag() {{
  local unit="$1" unit_file_state
  unit_file_state="$(systemctl show -p UnitFileState --value "$unit" 2>/dev/null)" || return 1
  case "$unit_file_state" in enabled) printf yes ;; disabled) printf no ;; *) return 1 ;; esac
}}
"""


def _remote_legacy_archive_guard_function() -> str:
    """Return fail-closed mount and same-filesystem legacy archive probes."""

    return """require_no_mount_at_or_below() {
  local guarded_root="$1" mount_targets mount_match
  mount_targets="$(findmnt -rn -o TARGET)" || return 1
  mount_match="$(printf '%s\n' "$mount_targets" | awk -v root="$guarded_root" '$0 == root || index($0, root "/") == 1 { found=1 } END { print(found ? "present" : "absent") }')" || return 1
  test "$mount_match" = absent || return 1
}
require_same_filesystem() {
  local source="$1" destination_parent="$2" source_device destination_device
  source_device="$(stat -c '%d' "$source")" || return 1
  destination_device="$(stat -c '%d' "$destination_parent")" || return 1
  test "$source_device" = "$destination_device" || return 1
}
"""


def _remote_failed_rollout_recovery_script(
    release_sha: str,
    attempt_id: str,
    *,
    expected_snapshot_sha256: str | None = None,
    expected_stage: str | None = None,
    minimum_stage_age_seconds: int | None = None,
) -> str:
    if not FULL_SHA_RE.fullmatch(release_sha) or not ATTEMPT_RE.fullmatch(attempt_id):
        raise RuntimeError("failed_rollout_release_identity_invalid")
    orphan_values = (expected_snapshot_sha256, expected_stage, minimum_stage_age_seconds)
    if any(value is not None for value in orphan_values):
        if (
            expected_snapshot_sha256 is None
            or not DIGEST_RE.fullmatch(expected_snapshot_sha256)
            or expected_stage not in {"marker_created", *ROLLOUT_STAGES}
            or not isinstance(minimum_stage_age_seconds, int)
            or minimum_stage_age_seconds < MIN_ORPHAN_TRANSACTION_AGE_SECONDS
            or minimum_stage_age_seconds > 86400
        ):
            raise RuntimeError("failed_rollout_orphan_guard_invalid")
    activation_marker = _activation_marker_path(release_sha)
    transaction_dir = _activation_transaction_dir(release_sha)
    snapshot = transaction_dir / "pre-mutation.tar"
    state = transaction_dir / "pre-mutation.state"
    restored_receipt = _activation_receipt_path(release_sha, "RESTORED")
    quarantine_receipt = _activation_receipt_path(release_sha, "QUARANTINED")
    deployed_receipt = _activation_receipt_path(release_sha, "DEPLOYED")
    allowed_paths = json.dumps([str(path) for path in ROLLOUT_SNAPSHOT_PATHS])
    stage_file = transaction_dir / "stage.state"
    allowed_stages = "|".join(ROLLOUT_STAGES)
    orphan_guard = ""
    if expected_snapshot_sha256 is not None:
        activity_guard = (
            f"""test ! -e '{stage_file}' && test ! -L '{stage_file}'
activity_path='{activation_marker}'"""
            if expected_stage == "marker_created"
            else f"""test -f '{stage_file}' && test ! -L '{stage_file}'
test "$(stat -c '%a' '{stage_file}')" = '600'
test "$(stat -c '%u:%g' '{stage_file}')" = '0:0'
test "$(stat -c '%h' '{stage_file}')" = '1'
test "$(wc -l < '{stage_file}')" = '4'
grep -Fxq 'schema=dev-control-plane/hosted-rollout-stage/v2' '{stage_file}'
grep -Fxq 'release_sha={release_sha}' '{stage_file}'
grep -Fxq 'attempt_id={attempt_id}' '{stage_file}'
grep -Fxq 'stage={expected_stage}' '{stage_file}'
case '{expected_stage}' in {allowed_stages}) ;; *) exit 94 ;; esac
activity_path='{stage_file}'"""
        )
        orphan_guard = f"""test -e '{activation_marker}'
verify_activation_transaction
grep -Fxq 'snapshot_sha256={expected_snapshot_sha256}' '{state}'
{activity_guard}
now="$(date +%s)"
activity_mtime="$(stat -c '%Y' "$activity_path")"
printf '%s:%s' "$now" "$activity_mtime" | grep -Eq '^[0-9]+:[0-9]+$'
test "$now" -ge "$activity_mtime"
test "$((now - activity_mtime))" -ge '{minimum_stage_age_seconds}'
"""
    return f"""set -euo pipefail
exec 9>{ROLLOUT_LOCK}
flock -w 300 -x 9
for required_tool in find findmnt sync awk; do command -v "$required_tool" >/dev/null 2>&1; done
{_remote_manifest_verifier_function()}
	{_remote_process_binding_function()}
	{_remote_activation_guard_function(release_sha, attempt_id)}
	{_remote_resolved_quarantine_guard_function()}
	{_remote_quarantine_remediation_function(release_sha)}
	{_remote_staging_cleanup_function(release_sha)}
{_remote_authority_state_guard_function()}
{_remote_legacy_archive_guard_function()}
{orphan_guard}
if [ ! -e {activation_marker} ] && [ ! -L {activation_marker} ]; then
  release='{RELEASES_DIR / release_sha}'
  if [ -f '{deployed_receipt}' ] && [ ! -L '{deployed_receipt}' ] && \
     grep -Fxq 'schema=dev-control-plane/hosted-rollout-receipt/v2' '{deployed_receipt}' && \
     grep -Fxq 'release_sha={release_sha}' '{deployed_receipt}' && \
     grep -Fxq 'outcome=deployed' '{deployed_receipt}' && \
     verify_prior_projection_unit '{release_sha}' && \
     verify_projection_release "$release" '{release_sha}' && \
     verify_projection_process "$release" >/dev/null && \
     curl -fsS --connect-timeout 2 --max-time 5 http://{LOOPBACK_HOST}:{LOOPBACK_PORT}/api/v2/health 2>/dev/null | python3 -c 'import json,sys; p=json.load(sys.stdin); raise SystemExit(0 if (p.get("service_role") == "hosted_projection_v2" and p.get("control_authority") is False and p.get("mutation_routes_enabled") is False) else 1)'; then
    seal_quarantine_remediations
    cleanup_projection_staging
    python3 - '{ARCHIVE_DIR}' <<'DCP_FSYNC_COMPLETION_READBACK'
import os
import sys
descriptor = os.open(sys.argv[1], os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
try:
    os.fsync(descriptor)
finally:
    os.close(descriptor)
DCP_FSYNC_COMPLETION_READBACK
    printf 'recovery=completed\n'
    exit 0
  fi
  printf 'recovery=not_activated\n'
  exit 0
fi
verify_activation_transaction
release='{RELEASES_DIR / release_sha}'
if [ -f '{deployed_receipt}' ] && [ ! -L '{deployed_receipt}' ] && \
   grep -Fxq 'schema=dev-control-plane/hosted-rollout-receipt/v2' '{deployed_receipt}' && \
   grep -Fxq 'release_sha={release_sha}' '{deployed_receipt}' && \
   grep -Fxq 'outcome=deployed' '{deployed_receipt}' && \
   verify_prior_projection_unit '{release_sha}' && \
   verify_projection_release "$release" '{release_sha}' && \
   verify_projection_process "$release" >/dev/null && \
   curl -fsS --connect-timeout 2 --max-time 5 http://{LOOPBACK_HOST}:{LOOPBACK_PORT}/api/v2/health 2>/dev/null | python3 -c 'import json,sys; p=json.load(sys.stdin); raise SystemExit(0 if (p.get("service_role") == "hosted_projection_v2" and p.get("control_authority") is False and p.get("mutation_routes_enabled") is False) else 1)'; then
  seal_quarantine_remediations
  cleanup_projection_staging
  unlink '{activation_marker}'
  python3 - '{ARCHIVE_DIR}' <<'DCP_FSYNC_RECOVERED_COMPLETION'
import os
import sys
descriptor = os.open(sys.argv[1], os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
try:
    os.fsync(descriptor)
finally:
    os.close(descriptor)
DCP_FSYNC_RECOVERED_COMPLETION
  printf 'recovery=completed\n'
  exit 0
fi
read_snapshot_value() {{
  key="$1"
  test "$(grep -Ec "^$key=" '{state}')" = '1' || return 1
  sed -n "s/^$key=//p" '{state}' || return 1
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
  test "$prior_kind" = v2 || return 1
  verify_prior_projection_unit "$prior_release_sha" || return 1
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
    else
      require_unit_main_pid_zero '{SERVICE_NAME}' || return 1
      require_projection_port_free || return 1
    fi
  else
    require_unit_inactive '{SERVICE_NAME}' || return 1
    require_unit_main_pid_zero '{SERVICE_NAME}' || return 1
    require_projection_port_free || return 1
  fi
  restored_service_active="$(capture_unit_active_flag '{SERVICE_NAME}')" || return 1
  restored_service_enabled="$(capture_unit_enabled_flag '{SERVICE_NAME}')" || return 1
  restored_certbot_active="$(capture_unit_active_flag certbot.timer)" || return 1
  restored_certbot_enabled="$(capture_unit_enabled_flag certbot.timer)" || return 1
  test "$restored_service_active" = "$service_active" || return 1
  test "$restored_service_enabled" = "$service_enabled" || return 1
  test "$restored_certbot_active" = "$certbot_active" || return 1
  test "$restored_certbot_enabled" = "$certbot_enabled" || return 1
  restored_nginx_active="$(capture_unit_active_flag nginx)" || return 1
  test "$restored_nginx_active" = "$nginx_active" || return 1
  return 0
}}

quarantine_projection() {{
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
  reload_nginx_if_active || return 1
  if [ -L '{APP_DIR}' ]; then
    active="$(readlink -f '{APP_DIR}')"
    case "$active" in '{RELEASES_DIR}'/*) unlink '{APP_DIR}' ;; *) return 1 ;; esac
  fi
  if [ "$prior_kind" = legacy ]; then
    if [ -d '{APP_DIR}' ] && [ ! -L '{APP_DIR}' ]; then
      test ! -e '{LEGACY_APP_ARCHIVE}' && test ! -L '{LEGACY_APP_ARCHIVE}' || return 1
      unsafe_entries="$(find '{APP_DIR}' -xdev \\( -type b -o -type c -o -type p -o -type s -o -type l \\) -print -quit)" || return 1
      test -z "$unsafe_entries" || return 1
      linked_entries="$(find '{APP_DIR}' -xdev -type f -links +1 -print -quit)" || return 1
      test -z "$linked_entries" || return 1
      require_no_mount_at_or_below '{APP_DIR}' || return 1
      require_same_filesystem '{APP_DIR}' '{ARCHIVE_DIR}' || return 1
      mv -Tn '{APP_DIR}' '{LEGACY_APP_ARCHIVE}' || return 1
      test ! -e '{APP_DIR}' && test ! -L '{APP_DIR}' || return 1
    else
      test ! -e '{APP_DIR}' && test ! -L '{APP_DIR}' || return 1
    fi
    test -d '{LEGACY_APP_ARCHIVE}' && test ! -L '{LEGACY_APP_ARCHIVE}' || return 1
    unsafe_entries="$(find '{LEGACY_APP_ARCHIVE}' -xdev \\( -type b -o -type c -o -type p -o -type s -o -type l \\) -print -quit)" || return 1
    test -z "$unsafe_entries" || return 1
    linked_entries="$(find '{LEGACY_APP_ARCHIVE}' -xdev -type f -links +1 -print -quit)" || return 1
    test -z "$linked_entries" || return 1
    require_no_mount_at_or_below '{LEGACY_APP_ARCHIVE}' || return 1
    chown -R --no-dereference root:root '{LEGACY_APP_ARCHIVE}' || return 1
    chmod -R a-w '{LEGACY_APP_ARCHIVE}' || return 1
    owner_mismatch="$(find '{LEGACY_APP_ARCHIVE}' -xdev \\( \\! -uid 0 -o \\! -gid 0 \\) -print -quit)" || return 1
    test -z "$owner_mismatch" || return 1
    sync -f '{LEGACY_APP_ARCHIVE}' || return 1
    python3 - '{RUNTIME_ROOT}' '{ARCHIVE_DIR}' <<'DCP_FSYNC_LEGACY_QUARANTINE_ARCHIVE' || return 1
import os
import sys
for raw in sys.argv[1:]:
    descriptor = os.open(raw, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
DCP_FSYNC_LEGACY_QUARANTINE_ARCHIVE
    writable_entries="$(find '{LEGACY_APP_ARCHIVE}' -xdev -perm /222 -print -quit)" || return 1
    test -z "$writable_entries" || return 1
  fi
  cleanup_projection_staging || return 1
  require_unit_inactive '{SERVICE_NAME}' || return 1
  require_unit_disabled '{SERVICE_NAME}' || return 1
  require_unit_main_pid_zero '{SERVICE_NAME}' || return 1
  require_unit_inactive certbot.timer || return 1
  require_projection_port_free || return 1
  test ! -e '{NGINX_SITE_ENABLED}'
  test ! -L '{NGINX_SITE_ENABLED}'
  test ! -e '{APP_DIR}'
  test ! -L '{APP_DIR}'
  if [ -e '{quarantine_receipt}' ] || [ -L '{quarantine_receipt}' ]; then
    test -f '{quarantine_receipt}' && test ! -L '{quarantine_receipt}' || return 1
    test "$(stat -c '%a' '{quarantine_receipt}')" = '444' || return 1
    test "$(stat -c '%u:%g' '{quarantine_receipt}')" = '0:0' || return 1
    test "$(stat -c '%h' '{quarantine_receipt}')" = '1' || return 1
    grep -Fxq 'schema=dev-control-plane/hosted-rollout-receipt/v2' '{quarantine_receipt}' || return 1
    grep -Fxq 'release_sha={release_sha}' '{quarantine_receipt}' || return 1
    grep -Fxq 'outcome=quarantined' '{quarantine_receipt}' || return 1
    test "$(grep -Ec '^reason=(restore_or_terminal_proof_failed|no_previous_v2_or_restore_failed)$' '{quarantine_receipt}')" = '1' || return 1
    grep -Fxq 'authority=disabled' '{quarantine_receipt}' || return 1
    test "$(wc -l < '{quarantine_receipt}')" = '5' || return 1
  else
    receipt_next='{quarantine_receipt}.next.'$$
    cat > "$receipt_next" <<'DCP_QUARANTINE'
schema=dev-control-plane/hosted-rollout-receipt/v2
release_sha={release_sha}
outcome=quarantined
reason=no_previous_v2_or_restore_failed
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
  fi
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

if [ "$prior_kind" = v2 ] && restore_snapshot; then
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


def _remote_quarantine_status(release_sha: str) -> dict[str, Any]:
    completed = _ssh(_remote_quarantine_status_script(release_sha))
    if completed.returncode != 0:
        raise RuntimeError("quarantine_status_unavailable_or_unsafe")
    required = {
        "quarantine",
        "release_sha",
        "snapshot_sha256",
        "quarantine_receipt_sha256",
        "failed_release_layout",
        "prior_kind",
        "prior_release_sha",
        "prior_service_active",
        "prior_service_enabled",
        "current_service_active",
        "current_service_enabled",
        "current_site_enabled",
        "current_app_present",
        "legacy_layout",
        "legacy_transition_safe",
        "current_port_owner",
        "certbot_timer_active",
        "legacy_archive_present",
        "legacy_state_present",
        "projection_state_present",
        "certificate_currently_valid",
        "certificate_covers_primary",
        "certificate_covers_www",
        "last_stage",
        "disposition",
        "replacement_sha",
        "replacement_anchor_sha256",
        "replacement_supersession_eligible",
    }
    try:
        values = _parse_exact_sanitized_key_value_lines(completed.stdout, required)
    except ValueError as exc:
        raise RuntimeError("quarantine_status_receipt_invalid") from exc
    if set(values) != required:
        raise RuntimeError("quarantine_status_receipt_invalid")
    if (
        values["quarantine"] != "verified_safe_disabled"
        or values["release_sha"] != release_sha
        or not DIGEST_RE.fullmatch(values["snapshot_sha256"])
        or not DIGEST_RE.fullmatch(values["quarantine_receipt_sha256"])
        or values["failed_release_layout"] not in {"immutable", "absent"}
        or values["prior_kind"] not in {"v2", "legacy", "absent"}
        or values["current_service_active"] != "no"
        or values["current_service_enabled"] != "no"
        or values["current_site_enabled"] != "no"
        or values["current_app_present"] not in {"yes", "no"}
        or values["current_port_owner"] != "free"
        or values["certbot_timer_active"] != "no"
        or values["legacy_transition_safe"] != "yes"
        or values["disposition"] not in {"unresolved", "resolved_safe_disabled"}
        or values["replacement_supersession_eligible"] not in {"yes", "no"}
        or (
            values["replacement_anchor_sha256"] != "none"
            and not DIGEST_RE.fullmatch(values["replacement_anchor_sha256"])
        )
    ):
        raise RuntimeError("quarantine_status_receipt_invalid")
    if values["prior_kind"] == "legacy":
        if values["legacy_layout"] not in {
            "archived_absent_pointer",
            "archived_pending_normalization",
            "legacy_directory_pending_archive",
        }:
            raise RuntimeError("quarantine_status_receipt_invalid")
        expected_present = values["legacy_layout"] == "legacy_directory_pending_archive"
        if (values["current_app_present"] == "yes") != expected_present:
            raise RuntimeError("quarantine_status_receipt_invalid")
    elif values["legacy_layout"] != "not_applicable" or values["current_app_present"] != "no":
        raise RuntimeError("quarantine_status_receipt_invalid")
    replacement_sha = values["replacement_sha"]
    if values["disposition"] == "unresolved":
        if (
            replacement_sha != "none"
            or values["replacement_anchor_sha256"] != "none"
            or values["replacement_supersession_eligible"] != "no"
        ):
            raise RuntimeError("quarantine_status_receipt_invalid")
    elif (
        not FULL_SHA_RE.fullmatch(replacement_sha)
        or replacement_sha == release_sha
        or not DIGEST_RE.fullmatch(values["replacement_anchor_sha256"])
    ):
        raise RuntimeError("quarantine_status_receipt_invalid")
    for name in (
        "prior_service_active",
        "prior_service_enabled",
        "legacy_archive_present",
        "legacy_state_present",
        "projection_state_present",
        "certificate_currently_valid",
        "certificate_covers_primary",
        "certificate_covers_www",
    ):
        if values[name] not in {"yes", "no"}:
            raise RuntimeError("quarantine_status_receipt_invalid")
    if values["prior_kind"] == "v2":
        if not FULL_SHA_RE.fullmatch(values["prior_release_sha"]):
            raise RuntimeError("quarantine_status_receipt_invalid")
    elif values["prior_release_sha"] != "none":
        raise RuntimeError("quarantine_status_receipt_invalid")
    if not re.fullmatch(r"[a-z0-9_]{1,64}", values["last_stage"]):
        raise RuntimeError("quarantine_status_receipt_invalid")
    return {
        "release_sha": release_sha,
        "snapshot_sha256": values["snapshot_sha256"],
        "quarantine_receipt_sha256": values["quarantine_receipt_sha256"],
        "failed_release_layout": values["failed_release_layout"],
        "prior_kind": values["prior_kind"],
        "prior_release_sha": None
        if values["prior_release_sha"] == "none"
        else values["prior_release_sha"],
        "prior_service_active": values["prior_service_active"] == "yes",
        "prior_service_enabled": values["prior_service_enabled"] == "yes",
        "safe_disabled": True,
        "service_active": False,
        "service_enabled": False,
        "site_enabled": False,
        "app_present": values["current_app_present"] == "yes",
        "port_8770_free": True,
        "certbot_timer_active": False,
        "legacy_archive_present": values["legacy_archive_present"] == "yes",
        "legacy_state_present": values["legacy_state_present"] == "yes",
        "projection_state_present": values["projection_state_present"] == "yes",
        "certificate_currently_valid": values["certificate_currently_valid"] == "yes",
        "certificate_covers_primary": values["certificate_covers_primary"] == "yes",
        "certificate_covers_www": values["certificate_covers_www"] == "yes",
        "last_stage": values["last_stage"],
        "legacy_layout": values["legacy_layout"],
        "legacy_transition_safe": True,
        "legacy_normalization_required": values["legacy_layout"]
        in {"legacy_directory_pending_archive", "archived_pending_normalization"},
        "disposition": values["disposition"],
        "replacement_sha": None if replacement_sha == "none" else replacement_sha,
        "replacement_anchor_sha256": (
            None
            if values["replacement_anchor_sha256"] == "none"
            else values["replacement_anchor_sha256"]
        ),
        "replacement_supersession_eligible": values["replacement_supersession_eligible"]
        == "yes",
        "raw_remote_payload_exposed": False,
    }


def _remote_quarantine_status_script(release_sha: str) -> str:
    if not FULL_SHA_RE.fullmatch(release_sha):
        raise RuntimeError("quarantine_status_release_identity_invalid")
    quarantine = _activation_receipt_path(release_sha, "QUARANTINED")
    disposition = _activation_receipt_path(release_sha, "QUARANTINE_RESOLVED")
    transaction_dir = _activation_transaction_dir(release_sha)
    state = transaction_dir / "pre-mutation.state"
    stage = transaction_dir / "stage.state"
    release = RELEASES_DIR / release_sha
    return f"""set -euo pipefail
test -f '{ROLLOUT_LOCK}'
exec 9<'{ROLLOUT_LOCK}'
flock -w 30 -s 9
for required_tool in find findmnt sync awk; do command -v "$required_tool" >/dev/null 2>&1; done
{_remote_manifest_verifier_function()}
{_remote_activation_snapshot_guard_function(release_sha)}
{_remote_resolved_quarantine_guard_function()}
{_remote_authority_state_guard_function()}
{_remote_legacy_archive_guard_function()}
verify_activation_snapshot
for activation in '{ARCHIVE_DIR}'/projection-v2-*.ACTIVATING; do
  if [ ! -e "$activation" ] && [ ! -L "$activation" ]; then continue; fi
  exit 90
done
for candidate in '{ARCHIVE_DIR}'/projection-v2-*.QUARANTINED; do
  if [ ! -e "$candidate" ] && [ ! -L "$candidate" ]; then continue; fi
  if [ "$candidate" != '{quarantine}' ]; then verify_resolved_quarantine "$candidate"; fi
done
test -f '{quarantine}'
test ! -L '{quarantine}'
test "$(stat -c '%a' '{quarantine}')" = '444'
test "$(stat -c '%u:%g' '{quarantine}')" = '0:0'
test "$(stat -c '%h' '{quarantine}')" = '1'
grep -Fxq 'schema=dev-control-plane/hosted-rollout-receipt/v2' '{quarantine}'
grep -Fxq 'release_sha={release_sha}' '{quarantine}'
grep -Fxq 'outcome=quarantined' '{quarantine}'
grep -Fxq 'authority=disabled' '{quarantine}'
test "$(wc -l < '{quarantine}')" = '5'
test "$(grep -Ec '^reason=(restore_or_terminal_proof_failed|no_previous_v2_or_restore_failed)$' '{quarantine}')" = '1'
failed_release_layout=absent
if [ -e '{release}' ] || [ -L '{release}' ]; then
  verify_projection_release '{release}' '{release_sha}'
  failed_release_layout=immutable
fi
read_snapshot_value() {{
  key="$1"
  test "$(grep -Ec "^$key=" '{state}')" = '1' || return 1
  sed -n "s/^$key=//p" '{state}' || return 1
}}
prior_kind="$(read_snapshot_value prior_app_kind)"
prior_release_sha="$(read_snapshot_value prior_release_sha)"
prior_service_active="$(read_snapshot_value service_active)"
prior_service_enabled="$(read_snapshot_value service_enabled)"
case "$prior_kind" in v2|legacy|absent) ;; *) exit 91 ;; esac
case "$prior_service_active:$prior_service_enabled" in yes:yes|yes:no|no:yes|no:no) ;; *) exit 92 ;; esac
if [ "$prior_kind" = v2 ]; then
  printf '%s' "$prior_release_sha" | grep -Eq '^[0-9a-f]{{40}}$'
else
  test "$prior_release_sha" = none
fi
require_unit_inactive '{SERVICE_NAME}'
require_unit_disabled '{SERVICE_NAME}'
require_unit_main_pid_zero '{SERVICE_NAME}'
require_unit_inactive certbot.timer
test ! -e '{NGINX_SITE_ENABLED}'
test ! -L '{NGINX_SITE_ENABLED}'
require_projection_port_free
current_app_present=no
legacy_layout=not_applicable
if [ "$prior_kind" = legacy ]; then
  if [ -d '{APP_DIR}' ] && [ ! -L '{APP_DIR}' ]; then
    test ! -e '{LEGACY_APP_ARCHIVE}' && test ! -L '{LEGACY_APP_ARCHIVE}'
    unsafe_entries="$(find '{APP_DIR}' -xdev \\( -type b -o -type c -o -type p -o -type s -o -type l \\) -print -quit)"
    test -z "$unsafe_entries"
    linked_entries="$(find '{APP_DIR}' -xdev -type f -links +1 -print -quit)"
    test -z "$linked_entries"
    require_no_mount_at_or_below '{APP_DIR}'
    require_same_filesystem '{APP_DIR}' '{ARCHIVE_DIR}'
    current_app_present=yes
    legacy_layout=legacy_directory_pending_archive
  else
    test ! -e '{APP_DIR}' && test ! -L '{APP_DIR}'
    test -d '{LEGACY_APP_ARCHIVE}' && test ! -L '{LEGACY_APP_ARCHIVE}'
    unsafe_entries="$(find '{LEGACY_APP_ARCHIVE}' -xdev \\( -type b -o -type c -o -type p -o -type s -o -type l \\) -print -quit)"
    test -z "$unsafe_entries"
    linked_entries="$(find '{LEGACY_APP_ARCHIVE}' -xdev -type f -links +1 -print -quit)"
    test -z "$linked_entries"
    require_no_mount_at_or_below '{LEGACY_APP_ARCHIVE}'
    pending_normalization="$(find '{LEGACY_APP_ARCHIVE}' -xdev \\( -perm /222 -o \\! -uid 0 -o \\! -gid 0 \\) -print -quit)"
    if [ -n "$pending_normalization" ]; then
      legacy_layout=archived_pending_normalization
    else
      legacy_layout=archived_absent_pointer
    fi
  fi
else
  test ! -e '{APP_DIR}' && test ! -L '{APP_DIR}'
fi
last_stage=unrecorded_v2
if [ -e '{stage}' ]; then
  test -f '{stage}' && test ! -L '{stage}'
  test "$(stat -c '%a' '{stage}')" = '600'
  test "$(stat -c '%u:%g' '{stage}')" = '0:0'
  grep -Fxq 'schema=dev-control-plane/hosted-rollout-stage/v2' '{stage}'
  grep -Fxq 'release_sha={release_sha}' '{stage}'
  stage_lines="$(wc -l < '{stage}')"
  case "$stage_lines" in
    3) test "$(grep -Ec '^attempt_id=' '{stage}')" = '0' ;;
    4) test "$(grep -Ec '^attempt_id=[0-9a-f]{{32}}$' '{stage}')" = '1' ;;
    *) exit 96 ;;
  esac
  last_stage="$(sed -n 's/^stage=//p' '{stage}')"
  test "$(grep -Ec '^stage=[a-z0-9_]{{1,64}}$' '{stage}')" = '1'
fi
disposition_state=unresolved
replacement_sha=none
replacement_anchor_sha256=none
replacement_supersession_eligible=no
if [ -e '{disposition}' ] || [ -L '{disposition}' ]; then
  verify_resolved_quarantine '{quarantine}'
  disposition_state=resolved_safe_disabled
  read -r replacement_sha successor_receipt _declared_visited <<DCP_EFFECTIVE_QUARANTINE_TIP
$(quarantine_declared_tip '{quarantine}')
DCP_EFFECTIVE_QUARANTINE_TIP
  replacement_anchor_sha256="$(sha256sum "$successor_receipt" | awk '{{print $1}}')"
  replacement_supersession_eligible=yes
  for replacement_artifact in '{ARCHIVE_DIR}/projection-v2-'"$replacement_sha".*; do
    if [ -e "$replacement_artifact" ] || [ -L "$replacement_artifact" ]; then replacement_supersession_eligible=no; fi
  done
  if [ -e '{RELEASES_DIR}/'"$replacement_sha" ] || [ -L '{RELEASES_DIR}/'"$replacement_sha" ]; then replacement_supersession_eligible=no; fi
  incoming_replacement="$(find '{RELEASES_DIR}' -maxdepth 1 -mindepth 1 -name ".incoming-$replacement_sha-*" -print -quit)"
  if [ -n "$incoming_replacement" ]; then replacement_supersession_eligible=no; fi
fi
certificate_currently_valid=no
certificate_covers_primary=no
certificate_covers_www=no
if [ -s '{CERT_FULLCHAIN}' ]; then
  if openssl x509 -checkend 0 -noout -in '{CERT_FULLCHAIN}' >/dev/null 2>&1; then certificate_currently_valid=yes; fi
  san="$(openssl x509 -in '{CERT_FULLCHAIN}' -noout -ext subjectAltName 2>/dev/null || true)"
  if printf '%s' "$san" | grep -Eq 'DNS:devcontrol[.]pro([,[:space:]]|$)'; then certificate_covers_primary=yes; fi
  if printf '%s' "$san" | grep -Eq 'DNS:www[.]devcontrol[.]pro([,[:space:]]|$)'; then certificate_covers_www=yes; fi
fi
printf 'quarantine=verified_safe_disabled\n'
printf 'release_sha={release_sha}\n'
printf 'snapshot_sha256=%s\n' "$(read_snapshot_value snapshot_sha256)"
printf 'quarantine_receipt_sha256=%s\n' "$(sha256sum '{quarantine}' | awk '{{print $1}}')"
printf 'failed_release_layout=%s\n' "$failed_release_layout"
printf 'prior_kind=%s\nprior_release_sha=%s\n' "$prior_kind" "$prior_release_sha"
printf 'prior_service_active=%s\nprior_service_enabled=%s\n' "$prior_service_active" "$prior_service_enabled"
printf 'current_service_active=no\ncurrent_service_enabled=no\ncurrent_site_enabled=no\ncurrent_app_present=%s\ncurrent_port_owner=free\n' "$current_app_present"
printf 'legacy_layout=%s\n' "$legacy_layout"
printf 'legacy_transition_safe=yes\n'
printf 'certbot_timer_active=no\n'
printf 'legacy_archive_present=%s\n' "$(test -d '{LEGACY_APP_ARCHIVE}' && echo yes || echo no)"
printf 'legacy_state_present=%s\n' "$(test -d '{LEGACY_STATE_DIR}' && echo yes || echo no)"
printf 'projection_state_present=%s\n' "$(test -d '{PROJECTION_STATE_DIR}' && echo yes || echo no)"
printf 'certificate_currently_valid=%s\ncertificate_covers_primary=%s\ncertificate_covers_www=%s\n' "$certificate_currently_valid" "$certificate_covers_primary" "$certificate_covers_www"
printf 'last_stage=%s\ndisposition=%s\nreplacement_sha=%s\nreplacement_anchor_sha256=%s\nreplacement_supersession_eligible=%s\n' "$last_stage" "$disposition_state" "$replacement_sha" "$replacement_anchor_sha256" "$replacement_supersession_eligible"
"""


def _resolve_remote_quarantine(
    release_sha: str,
    snapshot_sha256: str,
    replacement_sha: str,
    *,
    expected_prior_replacement: str | None = None,
    expected_prior_anchor_sha256: str | None = None,
) -> dict[str, Any]:
    if (
        not FULL_SHA_RE.fullmatch(release_sha)
        or not DIGEST_RE.fullmatch(snapshot_sha256)
        or not FULL_SHA_RE.fullmatch(replacement_sha)
        or replacement_sha == release_sha
        or (
            expected_prior_replacement is not None
            and not FULL_SHA_RE.fullmatch(expected_prior_replacement)
        )
        or ((expected_prior_replacement is None) != (expected_prior_anchor_sha256 is None))
        or (
            expected_prior_anchor_sha256 is not None
            and not DIGEST_RE.fullmatch(expected_prior_anchor_sha256)
        )
    ):
        raise RuntimeError("quarantine_resolution_identity_invalid")
    completed = _ssh(
        _remote_quarantine_resolution_script(
            release_sha,
            snapshot_sha256,
            replacement_sha,
            expected_prior_replacement=expected_prior_replacement,
            expected_prior_anchor_sha256=expected_prior_anchor_sha256,
        )
    )
    if completed.returncode != 0:
        raise RuntimeError("quarantine_resolution_failed_safe_state_preserved")
    try:
        values = _parse_exact_sanitized_key_value_lines(
            completed.stdout,
            {"resolution", "release_sha", "snapshot_sha256", "replacement_sha", "authority"},
        )
    except ValueError as exc:
        raise RuntimeError("quarantine_resolution_receipt_invalid") from exc
    if values != {
        "resolution": "sealed",
        "release_sha": release_sha,
        "snapshot_sha256": snapshot_sha256,
        "replacement_sha": replacement_sha,
        "authority": "disabled",
    }:
        raise RuntimeError("quarantine_resolution_receipt_invalid")
    evidence = _remote_quarantine_status(release_sha)
    if (
        evidence.get("disposition") != "resolved_safe_disabled"
        or evidence.get("replacement_sha") != replacement_sha
    ):
        raise RuntimeError("quarantine_resolution_readback_failed")
    return evidence


def _remote_quarantine_resolution_script(
    release_sha: str,
    snapshot_sha256: str,
    replacement_sha: str,
    *,
    expected_prior_replacement: str | None = None,
    expected_prior_anchor_sha256: str | None = None,
) -> str:
    if (
        not FULL_SHA_RE.fullmatch(release_sha)
        or not DIGEST_RE.fullmatch(snapshot_sha256)
        or not FULL_SHA_RE.fullmatch(replacement_sha)
        or replacement_sha == release_sha
        or (
            expected_prior_replacement is not None
            and not FULL_SHA_RE.fullmatch(expected_prior_replacement)
        )
        or ((expected_prior_replacement is None) != (expected_prior_anchor_sha256 is None))
        or (
            expected_prior_anchor_sha256 is not None
            and not DIGEST_RE.fullmatch(expected_prior_anchor_sha256)
        )
    ):
        raise RuntimeError("quarantine_resolution_identity_invalid")
    quarantine = _activation_receipt_path(release_sha, "QUARANTINED")
    disposition = _activation_receipt_path(release_sha, "QUARANTINE_RESOLVED")
    state = _activation_transaction_dir(release_sha) / "pre-mutation.state"
    expected_prior = expected_prior_replacement or "none"
    expected_prior_anchor = expected_prior_anchor_sha256 or "none"
    return f"""set -euo pipefail
exec 9>'{ROLLOUT_LOCK}'
flock -w 300 -x 9
for required_tool in find findmnt sync awk; do command -v "$required_tool" >/dev/null 2>&1; done
{_remote_manifest_verifier_function()}
{_remote_activation_snapshot_guard_function(release_sha)}
{_remote_resolved_quarantine_guard_function()}
{_remote_authority_state_guard_function()}
{_remote_legacy_archive_guard_function()}
verify_activation_snapshot
for activation in '{ARCHIVE_DIR}'/projection-v2-*.ACTIVATING; do
  if [ ! -e "$activation" ] && [ ! -L "$activation" ]; then continue; fi
  exit 95
done
for candidate in '{ARCHIVE_DIR}'/projection-v2-*.QUARANTINED; do
  if [ ! -e "$candidate" ] && [ ! -L "$candidate" ]; then continue; fi
  if [ "$candidate" != '{quarantine}' ]; then
    # The current failed release must already be an admitted chain tip.  Its
    # new disposition is written below; only then may the replacement become
    # the next admitted tip.
    verify_quarantine_permits_release "$candidate" '{release_sha}'
  fi
done
test ! -e '{_activation_receipt_path(replacement_sha, "QUARANTINED")}'
test ! -L '{_activation_receipt_path(replacement_sha, "QUARANTINED")}'
test -f '{quarantine}' && test ! -L '{quarantine}'
test "$(stat -c '%a' '{quarantine}')" = '444'
test "$(stat -c '%u:%g' '{quarantine}')" = '0:0'
test "$(stat -c '%h' '{quarantine}')" = '1'
grep -Fxq 'schema=dev-control-plane/hosted-rollout-receipt/v2' '{quarantine}'
grep -Fxq 'release_sha={release_sha}' '{quarantine}'
grep -Fxq 'outcome=quarantined' '{quarantine}'
grep -Fxq 'authority=disabled' '{quarantine}'
test "$(wc -l < '{quarantine}')" = '5'
test "$(grep -Ec '^reason=(restore_or_terminal_proof_failed|no_previous_v2_or_restore_failed)$' '{quarantine}')" = '1'
failed_release_layout=absent
if [ -e '{RELEASES_DIR / release_sha}' ] || [ -L '{RELEASES_DIR / release_sha}' ]; then
  verify_projection_release '{RELEASES_DIR / release_sha}' '{release_sha}'
  failed_release_layout=immutable
fi
grep -Fxq 'snapshot_sha256={snapshot_sha256}' '{state}'
prior_kind="$(sed -n 's/^prior_app_kind=//p' '{state}')"
test "$(grep -Ec '^prior_app_kind=(v2|legacy|absent)$' '{state}')" = '1'
require_unit_inactive '{SERVICE_NAME}'
require_unit_disabled '{SERVICE_NAME}'
require_unit_main_pid_zero '{SERVICE_NAME}'
require_unit_inactive certbot.timer
test ! -e '{NGINX_SITE_ENABLED}' && test ! -L '{NGINX_SITE_ENABLED}'
require_projection_port_free
if [ "$prior_kind" = legacy ]; then
  if [ -d '{APP_DIR}' ] && [ ! -L '{APP_DIR}' ]; then
    test ! -e '{LEGACY_APP_ARCHIVE}' && test ! -L '{LEGACY_APP_ARCHIVE}'
    unsafe_entries="$(find '{APP_DIR}' -xdev \\( -type b -o -type c -o -type p -o -type s -o -type l \\) -print -quit)"
    test -z "$unsafe_entries"
    linked_entries="$(find '{APP_DIR}' -xdev -type f -links +1 -print -quit)"
    test -z "$linked_entries"
    require_no_mount_at_or_below '{APP_DIR}'
    require_same_filesystem '{APP_DIR}' '{ARCHIVE_DIR}'
    mv -Tn '{APP_DIR}' '{LEGACY_APP_ARCHIVE}'
    test ! -e '{APP_DIR}' && test ! -L '{APP_DIR}'
  else
    test ! -e '{APP_DIR}' && test ! -L '{APP_DIR}'
  fi
  test -d '{LEGACY_APP_ARCHIVE}' && test ! -L '{LEGACY_APP_ARCHIVE}'
  unsafe_entries="$(find '{LEGACY_APP_ARCHIVE}' -xdev \\( -type b -o -type c -o -type p -o -type s -o -type l \\) -print -quit)"
  test -z "$unsafe_entries"
  linked_entries="$(find '{LEGACY_APP_ARCHIVE}' -xdev -type f -links +1 -print -quit)"
  test -z "$linked_entries"
  require_no_mount_at_or_below '{LEGACY_APP_ARCHIVE}'
  chown -R --no-dereference root:root '{LEGACY_APP_ARCHIVE}'
  chmod -R a-w '{LEGACY_APP_ARCHIVE}'
  owner_mismatch="$(find '{LEGACY_APP_ARCHIVE}' -xdev \\( \\! -uid 0 -o \\! -gid 0 \\) -print -quit)"
  test -z "$owner_mismatch"
  sync -f '{LEGACY_APP_ARCHIVE}'
  python3 - '{RUNTIME_ROOT}' '{ARCHIVE_DIR}' <<'DCP_FSYNC_RESOLVED_LEGACY_ARCHIVE'
import os
import sys
for raw in sys.argv[1:]:
    descriptor = os.open(raw, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
DCP_FSYNC_RESOLVED_LEGACY_ARCHIVE
  writable_entries="$(find '{LEGACY_APP_ARCHIVE}' -xdev -perm /222 -print -quit)"
  test -z "$writable_entries"
fi
test ! -e '{APP_DIR}' && test ! -L '{APP_DIR}'
quarantine_sha="$(sha256sum '{quarantine}' | awk '{{print $1}}')"
if [ -e '{disposition}' ] || [ -L '{disposition}' ]; then
  test '{expected_prior}' != none
  verify_resolved_quarantine '{quarantine}'
  read -r current_replacement predecessor_receipt declared_visited <<DCP_CURRENT_QUARANTINE_TIP
$(quarantine_declared_tip '{quarantine}')
DCP_CURRENT_QUARANTINE_TIP
  test "$current_replacement" = '{expected_prior}'
  test "$(sha256sum "$predecessor_receipt" | awk '{{print $1}}')" = '{expected_prior_anchor}'
  if [ "$current_replacement" != '{replacement_sha}' ]; then
    case "$declared_visited" in *:'{replacement_sha}':*) exit 99 ;; esac
    current_quarantine='{ARCHIVE_DIR}/projection-v2-'"$current_replacement"'.QUARANTINED'
    test ! -e "$current_quarantine" && test ! -L "$current_quarantine"
    if verify_quarantine_permits_release '{quarantine}' '{replacement_sha}'; then exit 99; fi
    for current_artifact in '{ARCHIVE_DIR}/projection-v2-'"$current_replacement".*; do
      if [ -e "$current_artifact" ] || [ -L "$current_artifact" ]; then exit 99; fi
    done
    test ! -e '{RELEASES_DIR}/'"$current_replacement" && test ! -L '{RELEASES_DIR}/'"$current_replacement"
    incoming_artifact="$(find '{RELEASES_DIR}' -maxdepth 1 -mindepth 1 -name ".incoming-$current_replacement-*" -print -quit)"
    test -z "$incoming_artifact"
    successor='{ARCHIVE_DIR}/projection-v2-{release_sha}-'"$current_replacement"'.SUPERSEDED'
    test ! -e "$successor" && test ! -L "$successor"
    predecessor_sha="$(sha256sum "$predecessor_receipt" | awk '{{print $1}}')"
    root_disposition_sha="$(sha256sum '{disposition}' | awk '{{print $1}}')"
    successor_next="$successor.next.$$"
    cat > "$successor_next" <<DCP_QUARANTINE_SUCCESSOR
schema=dev-control-plane/hosted-rollout-supersession/v2
root_failed_sha={release_sha}
root_disposition_sha256=$root_disposition_sha
prior_tip_sha=$current_replacement
prior_anchor_sha256=$predecessor_sha
successor_sha={replacement_sha}
source_ref=refs/remotes/origin/main
reason=origin_main_advanced_before_activation
authority=disabled
next_action=full_validated_deploy_only
DCP_QUARANTINE_SUCCESSOR
    chown root:root "$successor_next"
    chmod 0444 "$successor_next"
    python3 - "$successor_next" <<'DCP_FSYNC_SUCCESSOR'
import os
import sys
descriptor = os.open(sys.argv[1], os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
try:
    os.fsync(descriptor)
finally:
    os.close(descriptor)
DCP_FSYNC_SUCCESSOR
    mv -Tf "$successor_next" "$successor"
    python3 - '{ARCHIVE_DIR}' <<'DCP_FSYNC_SUCCESSOR_DIR'
import os
import sys
descriptor = os.open(sys.argv[1], os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
try:
    os.fsync(descriptor)
finally:
    os.close(descriptor)
DCP_FSYNC_SUCCESSOR_DIR
    verify_quarantine_successor '{release_sha}' "$current_replacement" "$predecessor_receipt" >/dev/null
  fi
else
  test '{expected_prior}' = none
  test '{expected_prior_anchor}' = none
  disposition_next='{disposition}.next.'$$
  cat > "$disposition_next" <<DCP_QUARANTINE_RESOLVED
schema=dev-control-plane/hosted-rollout-receipt/v2
release_sha={release_sha}
outcome=quarantine_resolved_safe_disabled
snapshot_sha256={snapshot_sha256}
quarantine_receipt_sha256=$quarantine_sha
replacement_sha={replacement_sha}
failed_release_layout=$failed_release_layout
legacy_layout=archived_absent_pointer
authority=disabled_at_resolution
next_action=full_validated_deploy_only
DCP_QUARANTINE_RESOLVED
  chown root:root "$disposition_next"
  chmod 0444 "$disposition_next"
  python3 - "$disposition_next" <<'DCP_FSYNC_DISPOSITION'
import os
import sys
descriptor = os.open(sys.argv[1], os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
try:
    os.fsync(descriptor)
finally:
    os.close(descriptor)
DCP_FSYNC_DISPOSITION
  mv -Tf "$disposition_next" '{disposition}'
  python3 - '{ARCHIVE_DIR}' <<'DCP_FSYNC_DISPOSITION_DIR'
import os
import sys
descriptor = os.open(sys.argv[1], os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
try:
    os.fsync(descriptor)
finally:
    os.close(descriptor)
DCP_FSYNC_DISPOSITION_DIR
  verify_resolved_quarantine '{quarantine}'
fi
read -r effective_replacement _effective_receipt _effective_visited <<DCP_EFFECTIVE_REPLACEMENT
$(quarantine_declared_tip '{quarantine}')
DCP_EFFECTIVE_REPLACEMENT
test "$effective_replacement" = '{replacement_sha}'
verify_no_unresolved_rollout_markers none '{replacement_sha}'
require_unit_inactive '{SERVICE_NAME}'
require_unit_disabled '{SERVICE_NAME}'
require_unit_main_pid_zero '{SERVICE_NAME}'
require_projection_port_free
test ! -e '{NGINX_SITE_ENABLED}' && test ! -L '{NGINX_SITE_ENABLED}'
test ! -e '{APP_DIR}' && test ! -L '{APP_DIR}'
printf 'resolution=sealed\nrelease_sha={release_sha}\nsnapshot_sha256={snapshot_sha256}\nreplacement_sha={replacement_sha}\nauthority=disabled\n'
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


def _remote_prepare_runtime_script(
    staging_dir: Path,
    release_sha: str,
    attempt_id: str,
) -> str:
    if not ATTEMPT_RE.fullmatch(attempt_id):
        raise RuntimeError("prepare_runtime_attempt_identity_invalid")
    release = RELEASES_DIR / release_sha
    return f"""set -euo pipefail
exec 9>{ROLLOUT_LOCK}
flock -w 300 -x 9
	{_remote_manifest_verifier_function()}
	{_remote_activation_guard_function(release_sha, attempt_id)}
	{_remote_resolved_quarantine_guard_function()}
	{_remote_rollout_stage_function(release_sha, attempt_id)}
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
unsafe_projection_links="$(find {PROJECTION_ROOT} -xdev -type l -print -quit)"
test -z "$unsafe_projection_links"
unsafe_projection_types="$(find {PROJECTION_ROOT} -xdev ! -type d ! -type f -print -quit)"
test -z "$unsafe_projection_types"
unsafe_projection_hardlinks="$(find {PROJECTION_ROOT} -xdev -type f -links +1 -print -quit)"
test -z "$unsafe_projection_hardlinks"
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
record_rollout_stage runtime_prepared
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
    attempt_id: str,
) -> list[str]:
    if not FULL_SHA_RE.fullmatch(release_sha) or not ATTEMPT_RE.fullmatch(attempt_id):
        raise RuntimeError("projection_rsync_release_identity_invalid")
    expected_prefix = f".incoming-{release_sha}-"
    if staging_dir.parent != RELEASES_DIR or not staging_dir.name.startswith(expected_prefix):
        raise RuntimeError("projection_rsync_staging_identity_invalid")
    remote_shell = " ".join(("/usr/bin/ssh", *SSH_EXEC_OPTIONS))
    receiver = f"""set -euo pipefail
exec 9>{ROLLOUT_LOCK}
flock -w 300 -x 9
{_remote_activation_guard_function(release_sha, attempt_id)}
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
    attempt_id: str,
) -> str:
    if not re.fullmatch(r"[0-9a-f]{64}", manifest_digest) or not ATTEMPT_RE.fullmatch(
        attempt_id
    ):
        raise RuntimeError("projection_manifest_digest_invalid")
    release = RELEASES_DIR / release_sha
    return f"""set -euo pipefail
exec 9>{ROLLOUT_LOCK}
flock -w 300 -x 9
{_remote_manifest_verifier_function()}
{_remote_activation_guard_function(release_sha, attempt_id)}
{_remote_rollout_stage_function(release_sha, attempt_id)}
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
record_rollout_stage release_finalized
"""


def _copy_projection_key(local_path: Path, release_sha: str, attempt_id: str) -> None:
    if not FULL_SHA_RE.fullmatch(release_sha) or not ATTEMPT_RE.fullmatch(attempt_id):
        raise RuntimeError("projection_key_release_identity_invalid")
    try:
        snapshot = _projection_key_snapshot(_projection_key_path(local_path))
    except _ProjectionKeyValidationError as exc:
        raise RuntimeError("projection_key_failed_final_secure_snapshot") from exc
    _install_projection_key_snapshot(snapshot, release_sha, attempt_id)


def _install_projection_key_snapshot(snapshot: bytes, release_sha: str, attempt_id: str) -> None:
    if not FULL_SHA_RE.fullmatch(release_sha) or not ATTEMPT_RE.fullmatch(attempt_id):
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
{_remote_activation_guard_function(release_sha, attempt_id)}
{_remote_rollout_stage_function(release_sha, attempt_id)}
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
record_rollout_stage projection_key_installed
""",
        snapshot,
        operation="install_projection_hmac_key",
    )


def _remote_install_script(
    cert_domains: Sequence[str],
    release_sha: str,
    *,
    attempt_id: str,
    force_certificate_refresh: bool = False,
) -> str:
    domains = tuple(cert_domains)
    if set(domains) != {PRIMARY_DOMAIN, WWW_DOMAIN}:
        raise RuntimeError("certificate_domain_set_mismatch")
    if not FULL_SHA_RE.fullmatch(release_sha) or not ATTEMPT_RE.fullmatch(attempt_id):
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
{_remote_process_binding_function()}
{_remote_activation_guard_function(release_sha, attempt_id)}
{_remote_rollout_stage_function(release_sha, attempt_id)}
{_remote_authority_state_guard_function()}
{_remote_legacy_archive_guard_function()}
verify_activation_transaction
verify_projection_release '{release}' '{release_sha}'
record_rollout_stage install_started
systemctl stop certbot.timer >/dev/null 2>&1 || true
record_rollout_stage certbot_timer_stopped
systemctl stop {SERVICE_NAME} >/dev/null 2>&1 || true
systemctl disable {SERVICE_NAME} >/dev/null 2>&1 || true
for authority_stop_attempt in $(seq 1 30); do
  service_state="$(systemctl show -p ActiveState --value {SERVICE_NAME} 2>/dev/null)" || exit 97
  service_pid="$(systemctl show -p MainPID --value {SERVICE_NAME} 2>/dev/null)" || exit 97
  listener="$(ss -H -ltnp 'sport = :{LOOPBACK_PORT}' 2>/dev/null)" || exit 97
  if [ "$service_state" = inactive ] && [ "$service_pid" = 0 ] && [ -z "$listener" ]; then break; fi
  sleep 1
done
require_unit_inactive {SERVICE_NAME}
require_unit_disabled {SERVICE_NAME}
require_unit_main_pid_zero {SERVICE_NAME}
require_unit_inactive certbot.timer
require_projection_port_free
record_rollout_stage legacy_authority_stopped
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
record_rollout_stage config_written
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
record_rollout_stage nginx_guarded
install -d -o root -g root -m 0755 {ACME_ROOT}/.well-known {ACME_ROOT}/.well-known/acme-challenge
challenge_name='dcp-v2-{release_sha}'
challenge_path='{ACME_ROOT}/.well-known/acme-challenge/'"$challenge_name"
printf '%s' '{release_sha}' > "$challenge_path"
chmod 0644 "$challenge_path"
trap 'unlink "$challenge_path" >/dev/null 2>&1 || true' EXIT
for challenge_domain in {PRIMARY_DOMAIN} {WWW_DOMAIN}; do
  observed="$(curl -fsS --noproxy '*' --proto '=http' --connect-timeout 5 --max-time 15 --resolve "$challenge_domain:80:{TARGET_HOST_IP}" "http://$challenge_domain/.well-known/acme-challenge/$challenge_name" 2>/dev/null)"
  test "$observed" = '{release_sha}'
done
unlink "$challenge_path"
trap - EXIT
record_rollout_stage acme_route_proved
if [ ! -s {CERT_FULLCHAIN} ]; then
  record_rollout_stage certificate_refresh_started
  certbot_status=0
  certbot certonly --cert-name {PRIMARY_DOMAIN} --webroot -w {ACME_ROOT} {domain_args} --non-interactive --agree-tos -m {CERTBOT_EMAIL} >/dev/null 2>&1 || certbot_status=$?
  if [ "$certbot_status" != 0 ]; then record_rollout_stage certificate_refresh_failed; exit 96; fi
elif [ '{1 if force_certificate_refresh else 0}' = '1' ] || ! openssl x509 -checkend {MIN_CERT_DAYS * 86400} -noout -in {CERT_FULLCHAIN} >/dev/null 2>&1; then
  record_rollout_stage certificate_refresh_started
  certbot_status=0
  certbot certonly --cert-name {PRIMARY_DOMAIN} --webroot -w {ACME_ROOT} {domain_args} --non-interactive --agree-tos -m {CERTBOT_EMAIL} --force-renewal >/dev/null 2>&1 || certbot_status=$?
  if [ "$certbot_status" != 0 ]; then record_rollout_stage certificate_refresh_failed; exit 96; fi
fi
test -s {CERT_FULLCHAIN}
test -s {CERT_PRIVATE_KEY}
openssl x509 -checkend {MIN_CERT_DAYS * 86400} -noout -in {CERT_FULLCHAIN} >/dev/null 2>&1
certificate_san="$(openssl x509 -in {CERT_FULLCHAIN} -noout -ext subjectAltName 2>/dev/null)"
printf '%s' "$certificate_san" | grep -Eq 'DNS:devcontrol[.]pro([,[:space:]]|$)'
printf '%s' "$certificate_san" | grep -Eq 'DNS:www[.]devcontrol[.]pro([,[:space:]]|$)'
grep -Eq '^authenticator[[:space:]]*=[[:space:]]*webroot' {CERT_RENEWAL_FILE}
record_rollout_stage certificate_ready
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
  test ! -L {LEGACY_APP_ARCHIVE}
  test -d {APP_DIR}
  unsafe_entries="$(find '{APP_DIR}' -xdev \\( -type b -o -type c -o -type p -o -type s -o -type l \\) -print -quit)"
  test -z "$unsafe_entries"
  linked_entries="$(find '{APP_DIR}' -xdev -type f -links +1 -print -quit)"
  test -z "$linked_entries"
  require_no_mount_at_or_below '{APP_DIR}'
  require_same_filesystem '{APP_DIR}' '{ARCHIVE_DIR}'
  mv -Tn {APP_DIR} {LEGACY_APP_ARCHIVE}
  test ! -e {APP_DIR} && test ! -L {APP_DIR}
fi
if [ -e {LEGACY_APP_ARCHIVE} ] || [ -L {LEGACY_APP_ARCHIVE} ]; then
  test -d {LEGACY_APP_ARCHIVE} && test ! -L {LEGACY_APP_ARCHIVE}
  unsafe_entries="$(find '{LEGACY_APP_ARCHIVE}' -xdev \\( -type b -o -type c -o -type p -o -type s -o -type l \\) -print -quit)"
  test -z "$unsafe_entries"
  linked_entries="$(find '{LEGACY_APP_ARCHIVE}' -xdev -type f -links +1 -print -quit)"
  test -z "$linked_entries"
  require_no_mount_at_or_below '{LEGACY_APP_ARCHIVE}'
  chown -R --no-dereference root:root {LEGACY_APP_ARCHIVE}
  chmod -R a-w {LEGACY_APP_ARCHIVE}
  normalization_mismatch="$(find '{LEGACY_APP_ARCHIVE}' -xdev \\( \\! -uid 0 -o \\! -gid 0 -o -perm /222 \\) -print -quit)"
  test -z "$normalization_mismatch"
  sync -f {LEGACY_APP_ARCHIVE}
  python3 - '{RUNTIME_ROOT}' '{ARCHIVE_DIR}' <<'DCP_FSYNC_INSTALLED_LEGACY_ARCHIVE'
import os
import sys
for raw in sys.argv[1:]:
    descriptor = os.open(raw, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
DCP_FSYNC_INSTALLED_LEGACY_ARCHIVE
fi
record_rollout_stage legacy_archived
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
record_rollout_stage app_link_switched
systemctl daemon-reload
verify_candidate_projection_unit
systemctl enable {SERVICE_NAME} >/dev/null 2>&1
systemctl restart {SERVICE_NAME}
{_remote_loopback_wait_script(str(release))}
record_rollout_stage service_ready
test "$(readlink -f {APP_DIR})" = '{release}'
cat > {NGINX_SITE_AVAILABLE} <<'DCP_NGINX_FINAL'
{final_nginx}DCP_NGINX_FINAL
chmod 0644 {NGINX_SITE_AVAILABLE}
nginx -t >/dev/null 2>&1
systemctl reload nginx
test "$(grep -Fc 'auth_basic off;' {NGINX_SITE_AVAILABLE})" = '1'
record_rollout_stage nginx_final
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
        "QUARANTINE_RESOLVED",
        "REMEDIATED",
        "STAGING_CLEANED",
    }:
        raise RuntimeError("activation_receipt_identity_invalid")
    return ARCHIVE_DIR / f"projection-v2-{release_sha}.{outcome}"


def _remote_activation_snapshot_guard_function(
    release_sha: str,
    attempt_id: str | None = None,
) -> str:
    if attempt_id is not None and not ATTEMPT_RE.fullmatch(attempt_id):
        raise RuntimeError("activation_snapshot_attempt_identity_invalid")
    transaction_dir = _activation_transaction_dir(release_sha)
    snapshot = transaction_dir / "pre-mutation.tar"
    state = transaction_dir / "pre-mutation.state"
    attempt_guard = (
        f"""  grep -Fxq 'attempt_id={attempt_id}' '{state}' || return 1
  test "$(wc -l < '{state}')" = '11' || return 1
"""
        if attempt_id is not None
        else f"""  state_lines="$(wc -l < '{state}')"
  case "$state_lines" in
    10) test "$(grep -Ec '^attempt_id=' '{state}')" = '0' || return 1 ;;
    11) test "$(grep -Ec '^attempt_id=[0-9a-f]{{32}}$' '{state}')" = '1' || return 1 ;;
    *) return 1 ;;
  esac
"""
    )
    return f"""verify_activation_snapshot() {{
  test -d '{transaction_dir}' || return 1
  test ! -L '{transaction_dir}' || return 1
  test "$(stat -c '%a' '{transaction_dir}')" = '700' || return 1
  test "$(stat -c '%u:%g' '{transaction_dir}')" = '0:0' || return 1
  test -f '{snapshot}' || return 1
  test ! -L '{snapshot}' || return 1
  test "$(stat -c '%a' '{snapshot}')" = '600' || return 1
  test "$(stat -c '%u:%g' '{snapshot}')" = '0:0' || return 1
  test "$(stat -c '%h' '{snapshot}')" = '1' || return 1
  test -f '{state}' || return 1
  test ! -L '{state}' || return 1
  test "$(stat -c '%a' '{state}')" = '600' || return 1
  test "$(stat -c '%u:%g' '{state}')" = '0:0' || return 1
  test "$(stat -c '%h' '{state}')" = '1' || return 1
  grep -Fxq 'schema=dev-control-plane/hosted-rollout-snapshot/v2' '{state}' || return 1
  grep -Fxq 'release_sha={release_sha}' '{state}' || return 1
{attempt_guard}
  expected_snapshot_sha="$(sed -n 's/^snapshot_sha256=//p' '{state}')" || return 1
  test "$(grep -Ec '^snapshot_sha256=[0-9a-f]{{64}}$' '{state}')" = '1' || return 1
  test "$(sha256sum '{snapshot}' | awk '{{print $1}}')" = "$expected_snapshot_sha" || return 1
}}
"""


def _remote_rollout_stage_function(release_sha: str, attempt_id: str) -> str:
    if not FULL_SHA_RE.fullmatch(release_sha) or not ATTEMPT_RE.fullmatch(attempt_id):
        raise RuntimeError("rollout_stage_release_identity_invalid")
    stage_file = _activation_transaction_dir(release_sha) / "stage.state"
    allowed = "|".join(ROLLOUT_STAGES)
    return f"""record_rollout_stage() {{
  requested_stage="$1"
  case "$requested_stage" in {allowed}) ;; *) return 95 ;; esac
  verify_activation_transaction || return 1
  stage_next='{stage_file}.next.'$$
  cat > "$stage_next" <<DCP_ROLLOUT_STAGE
schema=dev-control-plane/hosted-rollout-stage/v2
release_sha={release_sha}
attempt_id={attempt_id}
stage=$requested_stage
DCP_ROLLOUT_STAGE
  chown root:root "$stage_next"
  chmod 0600 "$stage_next"
  python3 - "$stage_next" <<'DCP_FSYNC_STAGE'
import os
import sys
descriptor = os.open(sys.argv[1], os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
try:
    os.fsync(descriptor)
finally:
    os.close(descriptor)
DCP_FSYNC_STAGE
  mv -Tf "$stage_next" '{stage_file}'
  python3 - '{_activation_transaction_dir(release_sha)}' <<'DCP_FSYNC_STAGE_DIR'
import os
import sys
descriptor = os.open(sys.argv[1], os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
try:
    os.fsync(descriptor)
finally:
    os.close(descriptor)
DCP_FSYNC_STAGE_DIR
}}
"""


def _record_remote_rollout_stage(release_sha: str, attempt_id: str, stage: str) -> None:
    if not ATTEMPT_RE.fullmatch(attempt_id) or stage not in ROLLOUT_STAGES:
        raise RuntimeError("rollout_stage_invalid")
    _ssh_checked(
        f"""set -euo pipefail
exec 9>'{ROLLOUT_LOCK}'
flock -w 300 -x 9
{_remote_activation_guard_function(release_sha, attempt_id)}
{_remote_rollout_stage_function(release_sha, attempt_id)}
record_rollout_stage '{stage}'
""",
        operation="record_projection_rollout_stage",
    )


def _remote_resolved_quarantine_guard_function() -> str:
    """Permit immutable quarantine history only with a digest-bound disposition."""

    return f"""verify_failed_release_layout() {{
  failed_release_sha="$1"
  printf '%s' "$failed_release_sha" | grep -Eq '^[0-9a-f]{{40}}$' || return 1
  failed_release='{RELEASES_DIR}/'"$failed_release_sha"
  if [ -e "$failed_release" ] || [ -L "$failed_release" ]; then
    verify_projection_release "$failed_release" "$failed_release_sha" || return 1
    printf immutable
  else
    printf absent
  fi
}}
verify_resolved_quarantine() {{
  quarantine_marker="$1"
  marker_name="$(basename "$quarantine_marker")"
  failed_sha="${{marker_name#projection-v2-}}"
  failed_sha="${{failed_sha%.QUARANTINED}}"
  printf '%s' "$failed_sha" | grep -Eq '^[0-9a-f]{{40}}$' || return 1
  test "$quarantine_marker" = '{ARCHIVE_DIR}/projection-v2-'"$failed_sha"'.QUARANTINED' || return 1
  test -f "$quarantine_marker" || return 1
  test ! -L "$quarantine_marker" || return 1
  test "$(stat -c '%a' "$quarantine_marker")" = '444' || return 1
  test "$(stat -c '%u:%g' "$quarantine_marker")" = '0:0' || return 1
  test "$(stat -c '%h' "$quarantine_marker")" = '1' || return 1
  grep -Fxq 'schema=dev-control-plane/hosted-rollout-receipt/v2' "$quarantine_marker" || return 1
  grep -Fxq "release_sha=$failed_sha" "$quarantine_marker" || return 1
  grep -Fxq 'outcome=quarantined' "$quarantine_marker" || return 1
  grep -Fxq 'authority=disabled' "$quarantine_marker" || return 1
  test "$(wc -l < "$quarantine_marker")" = '5' || return 1
  test "$(grep -Ec '^reason=(restore_or_terminal_proof_failed|no_previous_v2_or_restore_failed)$' "$quarantine_marker")" = '1' || return 1
  quarantine_sha="$(sha256sum "$quarantine_marker" | awk '{{print $1}}')" || return 1
  disposition='{ARCHIVE_DIR}/projection-v2-'"$failed_sha"'.QUARANTINE_RESOLVED'
  test -f "$disposition" || return 1
  test ! -L "$disposition" || return 1
  test "$(stat -c '%a' "$disposition")" = '444' || return 1
  test "$(stat -c '%u:%g' "$disposition")" = '0:0' || return 1
  test "$(stat -c '%h' "$disposition")" = '1' || return 1
  grep -Fxq 'schema=dev-control-plane/hosted-rollout-receipt/v2' "$disposition" || return 1
  grep -Fxq "release_sha=$failed_sha" "$disposition" || return 1
  grep -Fxq 'outcome=quarantine_resolved_safe_disabled' "$disposition" || return 1
  grep -Fxq "quarantine_receipt_sha256=$quarantine_sha" "$disposition" || return 1
  grep -Fxq 'legacy_layout=archived_absent_pointer' "$disposition" || return 1
  grep -Fxq 'authority=disabled_at_resolution' "$disposition" || return 1
  grep -Fxq 'next_action=full_validated_deploy_only' "$disposition" || return 1
  disposition_lines="$(wc -l < "$disposition")" || return 1
  case "$disposition_lines" in
    9)
      test "$(grep -Ec '^failed_release_layout=' "$disposition")" = '0' || return 1
      test "$(verify_failed_release_layout "$failed_sha")" = immutable || return 1
      ;;
    10)
      test "$(grep -Ec '^failed_release_layout=(immutable|absent)$' "$disposition")" = '1' || return 1
      failed_release_layout="$(sed -n 's/^failed_release_layout=//p' "$disposition")" || return 1
      test "$(verify_failed_release_layout "$failed_sha")" = "$failed_release_layout" || return 1
      ;;
    *) return 1 ;;
  esac
  snapshot_sha="$(sed -n 's/^snapshot_sha256=//p' "$disposition")" || return 1
  test "$(grep -Ec '^snapshot_sha256=[0-9a-f]{{64}}$' "$disposition")" = '1' || return 1
  state='{ARCHIVE_DIR}/projection-v2-'"$failed_sha"'.ROLLBACK/pre-mutation.state'
  snapshot='{ARCHIVE_DIR}/projection-v2-'"$failed_sha"'.ROLLBACK/pre-mutation.tar'
  test -f "$state" && test ! -L "$state" || return 1
  test -f "$snapshot" && test ! -L "$snapshot" || return 1
  test "$(stat -c '%a' "$state")" = '600' || return 1
  test "$(stat -c '%u:%g' "$state")" = '0:0' || return 1
  test "$(stat -c '%h' "$state")" = '1' || return 1
  test "$(stat -c '%a' "$snapshot")" = '600' || return 1
  test "$(stat -c '%u:%g' "$snapshot")" = '0:0' || return 1
  test "$(stat -c '%h' "$snapshot")" = '1' || return 1
  grep -Fxq 'schema=dev-control-plane/hosted-rollout-snapshot/v2' "$state" || return 1
  grep -Fxq "release_sha=$failed_sha" "$state" || return 1
  grep -Fxq "snapshot_sha256=$snapshot_sha" "$state" || return 1
  test "$(sha256sum "$snapshot" | awk '{{print $1}}')" = "$snapshot_sha" || return 1
  replacement_sha="$(sed -n 's/^replacement_sha=//p' "$disposition")" || return 1
  test "$(grep -Ec '^replacement_sha=[0-9a-f]{{40}}$' "$disposition")" = '1' || return 1
  test "$replacement_sha" != "$failed_sha" || return 1
}}
verify_quarantine_successor() {{
  failed_sha="$1"
  previous_sha="$2"
  predecessor="$3"
  successor='{ARCHIVE_DIR}/projection-v2-'"$failed_sha"'-'"$previous_sha"'.SUPERSEDED'
  root_disposition='{ARCHIVE_DIR}/projection-v2-'"$failed_sha"'.QUARANTINE_RESOLVED'
  test -f "$predecessor" && test ! -L "$predecessor" || return 1
  test "$(stat -c '%a' "$predecessor")" = '444' || return 1
  test "$(stat -c '%u:%g' "$predecessor")" = '0:0' || return 1
  test "$(stat -c '%h' "$predecessor")" = '1' || return 1
  if [ "$predecessor" = "$root_disposition" ]; then
    grep -Fxq "release_sha=$failed_sha" "$predecessor" || return 1
    grep -Fxq "replacement_sha=$previous_sha" "$predecessor" || return 1
  else
    grep -Fxq 'schema=dev-control-plane/hosted-rollout-supersession/v2' "$predecessor" || return 1
    grep -Fxq "root_failed_sha=$failed_sha" "$predecessor" || return 1
    grep -Fxq "successor_sha=$previous_sha" "$predecessor" || return 1
  fi
  predecessor_sha="$(sha256sum "$predecessor" | awk '{{print $1}}')" || return 1
  root_disposition_sha="$(sha256sum "$root_disposition" | awk '{{print $1}}')" || return 1
  test -f "$successor" && test ! -L "$successor" || return 1
  test "$(stat -c '%a' "$successor")" = '444' || return 1
  test "$(stat -c '%u:%g' "$successor")" = '0:0' || return 1
  test "$(stat -c '%h' "$successor")" = '1' || return 1
  test "$(wc -l < "$successor")" = '10' || return 1
  grep -Fxq 'schema=dev-control-plane/hosted-rollout-supersession/v2' "$successor" || return 1
  grep -Fxq "root_failed_sha=$failed_sha" "$successor" || return 1
  grep -Fxq "root_disposition_sha256=$root_disposition_sha" "$successor" || return 1
  grep -Fxq "prior_tip_sha=$previous_sha" "$successor" || return 1
  grep -Fxq "prior_anchor_sha256=$predecessor_sha" "$successor" || return 1
  grep -Fxq 'source_ref=refs/remotes/origin/main' "$successor" || return 1
  grep -Fxq 'reason=origin_main_advanced_before_activation' "$successor" || return 1
  grep -Fxq 'authority=disabled' "$successor" || return 1
  grep -Fxq 'next_action=full_validated_deploy_only' "$successor" || return 1
  next_sha="$(sed -n 's/^successor_sha=//p' "$successor")" || return 1
  test "$(grep -Ec '^successor_sha=[0-9a-f]{{40}}$' "$successor")" = '1' || return 1
  test "$next_sha" != "$failed_sha" || return 1
  test "$next_sha" != "$previous_sha" || return 1
  printf '%s' "$next_sha"
}}
quarantine_declared_tip() {{
  quarantine_marker="$1"
  verify_resolved_quarantine "$quarantine_marker" || return 1
  marker_name="$(basename "$quarantine_marker")"
  failed_sha="${{marker_name#projection-v2-}}"
  failed_sha="${{failed_sha%.QUARANTINED}}"
  predecessor='{ARCHIVE_DIR}/projection-v2-'"$failed_sha"'.QUARANTINE_RESOLVED'
  current_sha="$(sed -n 's/^replacement_sha=//p' "$predecessor")" || return 1
  visited=":$failed_sha:"
  successor_hop=0
  while [ "$successor_hop" -lt 64 ]; do
    case "$visited" in *:"$current_sha":*) return 1 ;; esac
    visited="$visited$current_sha:"
    successor='{ARCHIVE_DIR}/projection-v2-'"$failed_sha"'-'"$current_sha"'.SUPERSEDED'
    if [ ! -e "$successor" ] && [ ! -L "$successor" ]; then
      printf '%s %s %s\n' "$current_sha" "$predecessor" "$visited"
      return 0
    fi
    next_sha="$(verify_quarantine_successor "$failed_sha" "$current_sha" "$predecessor")" || return 1
    predecessor="$successor"
    current_sha="$next_sha"
    successor_hop=$((successor_hop + 1))
  done
  return 1
}}
quarantine_candidate_anchor() {{
  quarantine_marker="$1"
  candidate_release="$2"
  printf '%s' "$candidate_release" | grep -Eq '^[0-9a-f]{{40}}$' || return 1
  verify_resolved_quarantine "$quarantine_marker" || return 1
  marker_name="$(basename "$quarantine_marker")"
  failed_sha="${{marker_name#projection-v2-}}"
  failed_sha="${{failed_sha%.QUARANTINED}}"
  chain_tip="$(quarantine_declared_tip "$quarantine_marker")" || return 1
  read -r chain_sha chain_receipt _declared_visited <<< "$chain_tip" || return 1
  visited=":$failed_sha:"
  chain_hop=0
  while [ "$chain_hop" -lt 64 ]; do
    case "$visited" in *:"$chain_sha":*) return 1 ;; esac
    if [ "$candidate_release" = "$chain_sha" ]; then
      sha256sum "$chain_receipt" | awk '{{print $1}}' || return 1
      return 0
    fi
    visited="$visited$chain_sha:"
    chain_quarantine='{ARCHIVE_DIR}/projection-v2-'"$chain_sha"'.QUARANTINED'
    if [ ! -e "$chain_quarantine" ] && [ ! -L "$chain_quarantine" ]; then return 1; fi
    chain_tip="$(quarantine_declared_tip "$chain_quarantine")" || return 1
    read -r chain_sha chain_receipt _declared_visited <<< "$chain_tip" || return 1
    chain_hop=$((chain_hop + 1))
  done
  return 1
}}
verify_quarantine_candidate_chain() {{
  quarantine_candidate_anchor "$1" "$2" >/dev/null || return 1
}}
verify_quarantine_permits_release() {{
  quarantine_marker="$1"
  candidate_release="$2"
  verify_resolved_quarantine "$quarantine_marker" || return 1
  marker_name="$(basename "$quarantine_marker")"
  failed_sha="${{marker_name#projection-v2-}}"
  failed_sha="${{failed_sha%.QUARANTINED}}"
  disposition='{ARCHIVE_DIR}/projection-v2-'"$failed_sha"'.QUARANTINE_RESOLVED'
  replacement_sha="$(sed -n 's/^replacement_sha=//p' "$disposition")" || return 1
  if [ "$candidate_release" != none ]; then
    if verify_quarantine_candidate_chain "$quarantine_marker" "$candidate_release"; then
      return 0
    fi
  fi
  remediation='{ARCHIVE_DIR}/projection-v2-'"$failed_sha"'.REMEDIATED'
  test -f "$remediation" && test ! -L "$remediation" || return 1
  test "$(stat -c '%a' "$remediation")" = '444' || return 1
  test "$(stat -c '%u:%g' "$remediation")" = '0:0' || return 1
  test "$(stat -c '%h' "$remediation")" = '1' || return 1
  quarantine_sha="$(sha256sum "$quarantine_marker" | awk '{{print $1}}')" || return 1
  disposition_sha="$(sha256sum "$disposition" | awk '{{print $1}}')" || return 1
  remediation_lines="$(wc -l < "$remediation")" || return 1
  test "$remediation_lines" = '9' || return 1
  test "$(grep -Ec '^deployed_release_sha=[0-9a-f]{{40}}$' "$remediation")" = '1' || return 1
  test "$(grep -Ec '^terminal_chain_anchor_sha256=[0-9a-f]{{64}}$' "$remediation")" = '1' || return 1
  deployed_release_sha="$(sed -n 's/^deployed_release_sha=//p' "$remediation")" || return 1
  terminal_chain_anchor_sha="$(quarantine_candidate_anchor "$quarantine_marker" "$deployed_release_sha")" || return 1
  grep -Fxq "terminal_chain_anchor_sha256=$terminal_chain_anchor_sha" "$remediation" || return 1
  deployed='{ARCHIVE_DIR}/projection-v2-'"$deployed_release_sha"'.DEPLOYED'
  test -f "$deployed" && test ! -L "$deployed" || return 1
  test "$(stat -c '%a' "$deployed")" = '444' || return 1
  test "$(stat -c '%u:%g' "$deployed")" = '0:0' || return 1
  test "$(stat -c '%h' "$deployed")" = '1' || return 1
  deployed_sha="$(sha256sum "$deployed" | awk '{{print $1}}')" || return 1
  grep -Fxq 'schema=dev-control-plane/hosted-rollout-receipt/v2' "$remediation" || return 1
  grep -Fxq "release_sha=$failed_sha" "$remediation" || return 1
  grep -Fxq 'outcome=quarantine_remediated' "$remediation" || return 1
  grep -Fxq "replacement_sha=$replacement_sha" "$remediation" || return 1
  grep -Fxq "deployed_release_sha=$deployed_release_sha" "$remediation" || return 1
  grep -Fxq "quarantine_receipt_sha256=$quarantine_sha" "$remediation" || return 1
  grep -Fxq "disposition_receipt_sha256=$disposition_sha" "$remediation" || return 1
  grep -Fxq "deployment_receipt_sha256=$deployed_sha" "$remediation" || return 1
  test "$(wc -l < "$deployed")" = '4' || return 1
  test "$(grep -Ec '^unit_sha256=[0-9a-f]{{64}}$' "$deployed")" = '1' || return 1
  grep -Fxq 'schema=dev-control-plane/hosted-rollout-receipt/v2' "$deployed" || return 1
  grep -Fxq "release_sha=$deployed_release_sha" "$deployed" || return 1
  grep -Fxq 'outcome=deployed' "$deployed" || return 1
}}
verify_no_unresolved_rollout_markers() {{
  allowed_activation="${{1:-none}}"
  candidate_release="${{2:-none}}"
  for activation in '{ARCHIVE_DIR}'/projection-v2-*.ACTIVATING; do
    if [ ! -e "$activation" ] && [ ! -L "$activation" ]; then continue; fi
    if [ "$allowed_activation" != none ] && [ "$activation" = "$allowed_activation" ]; then
      continue
    fi
    return 1
  done
  for quarantine in '{ARCHIVE_DIR}'/projection-v2-*.QUARANTINED; do
    if [ ! -e "$quarantine" ] && [ ! -L "$quarantine" ]; then continue; fi
    verify_quarantine_permits_release "$quarantine" "$candidate_release" || return 1
  done
}}
"""


def _remote_quarantine_remediation_function(replacement_sha: str) -> str:
    if not FULL_SHA_RE.fullmatch(replacement_sha):
        raise RuntimeError("quarantine_remediation_replacement_identity_invalid")
    deployed = _activation_receipt_path(replacement_sha, "DEPLOYED")
    return f"""seal_quarantine_remediations() {{
  for quarantine in '{ARCHIVE_DIR}'/projection-v2-*.QUARANTINED; do
    if [ ! -e "$quarantine" ] && [ ! -L "$quarantine" ]; then continue; fi
    verify_resolved_quarantine "$quarantine" || return 1
    marker_name="$(basename "$quarantine")"
    failed_sha="${{marker_name#projection-v2-}}"
    failed_sha="${{failed_sha%.QUARANTINED}}"
    disposition='{ARCHIVE_DIR}/projection-v2-'"$failed_sha"'.QUARANTINE_RESOLVED'
    remediation='{ARCHIVE_DIR}/projection-v2-'"$failed_sha"'.REMEDIATED'
    if [ -e "$remediation" ] || [ -L "$remediation" ]; then
      verify_quarantine_permits_release "$quarantine" none || return 1
      continue
    fi
    expected_replacement="$(sed -n 's/^replacement_sha=//p' "$disposition")" || return 1
    verify_quarantine_permits_release "$quarantine" '{replacement_sha}' || return 1
    terminal_chain_anchor_sha="$(quarantine_candidate_anchor "$quarantine" '{replacement_sha}')" || return 1
    quarantine_sha="$(sha256sum "$quarantine" | awk '{{print $1}}')" || return 1
    disposition_sha="$(sha256sum "$disposition" | awk '{{print $1}}')" || return 1
    deployed_sha="$(sha256sum '{deployed}' | awk '{{print $1}}')" || return 1
    remediation_next="$remediation.next.$$"
    cat > "$remediation_next" <<DCP_QUARANTINE_REMEDIATED
schema=dev-control-plane/hosted-rollout-receipt/v2
release_sha=$failed_sha
outcome=quarantine_remediated
replacement_sha=$expected_replacement
deployed_release_sha={replacement_sha}
terminal_chain_anchor_sha256=$terminal_chain_anchor_sha
quarantine_receipt_sha256=$quarantine_sha
disposition_receipt_sha256=$disposition_sha
deployment_receipt_sha256=$deployed_sha
DCP_QUARANTINE_REMEDIATED
    chown root:root "$remediation_next"
    chmod 0444 "$remediation_next"
    python3 - "$remediation_next" <<'DCP_FSYNC_REMEDIATION'
import os
import sys
descriptor = os.open(sys.argv[1], os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
try:
    os.fsync(descriptor)
finally:
    os.close(descriptor)
DCP_FSYNC_REMEDIATION
    mv -Tf "$remediation_next" "$remediation"
    verify_quarantine_permits_release "$quarantine" none || return 1
  done
  python3 - '{ARCHIVE_DIR}' <<'DCP_FSYNC_REMEDIATION_DIR'
import os
import sys
descriptor = os.open(sys.argv[1], os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
try:
    os.fsync(descriptor)
finally:
    os.close(descriptor)
DCP_FSYNC_REMEDIATION_DIR
}}
"""


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
)" || return 1
  printf '%s' "$removed" | grep -Eq '^[0-9]+$' || return 1
  if [ -e '{receipt}' ] || [ -L '{receipt}' ]; then
    test -f '{receipt}' && test ! -L '{receipt}' || return 1
    test "$(stat -c '%a' '{receipt}')" = '444' || return 1
    test "$(stat -c '%u:%g' '{receipt}')" = '0:0' || return 1
    test "$(stat -c '%h' '{receipt}')" = '1' || return 1
    test "$(wc -l < '{receipt}')" = '4' || return 1
    grep -Fxq 'schema=dev-control-plane/hosted-rollout-receipt/v2' '{receipt}' || return 1
    grep -Fxq 'release_sha={release_sha}' '{receipt}' || return 1
    grep -Fxq 'outcome=staging_cleaned' '{receipt}' || return 1
    test "$(grep -Ec '^removed_count=[0-9]+$' '{receipt}')" = '1' || return 1
    test "$removed" = 0 || return 1
    return 0
  fi
  receipt_next='{receipt}.next.'$$
  cat > "$receipt_next" <<DCP_STAGING_CLEANED
schema=dev-control-plane/hosted-rollout-receipt/v2
release_sha={release_sha}
outcome=staging_cleaned
removed_count=$removed
DCP_STAGING_CLEANED
  chown root:root "$receipt_next" || return 1
  chmod 0444 "$receipt_next" || return 1
  python3 - "$receipt_next" <<'DCP_FSYNC_STAGING_CLEANUP' || return 1
import os
import sys
descriptor = os.open(sys.argv[1], os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
try:
    os.fsync(descriptor)
finally:
    os.close(descriptor)
DCP_FSYNC_STAGING_CLEANUP
  mv -Tf "$receipt_next" '{receipt}' || return 1
  python3 - '{ARCHIVE_DIR}' <<'DCP_FSYNC_STAGING_CLEANUP_DIR' || return 1
import os
import sys
descriptor = os.open(sys.argv[1], os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
try:
    os.fsync(descriptor)
finally:
    os.close(descriptor)
DCP_FSYNC_STAGING_CLEANUP_DIR
  test -f '{receipt}' && test ! -L '{receipt}' || return 1
  test "$(stat -c '%a' '{receipt}')" = '444' || return 1
  test "$(stat -c '%u:%g' '{receipt}')" = '0:0' || return 1
  test "$(stat -c '%h' '{receipt}')" = '1' || return 1
  test "$(wc -l < '{receipt}')" = '4' || return 1
  grep -Fxq 'schema=dev-control-plane/hosted-rollout-receipt/v2' '{receipt}' || return 1
  grep -Fxq 'release_sha={release_sha}' '{receipt}' || return 1
  grep -Fxq 'outcome=staging_cleaned' '{receipt}' || return 1
  grep -Fxq "removed_count=$removed" '{receipt}' || return 1
}}
"""


def _remote_activation_guard_function(
    release_sha: str,
    attempt_id: str | None = None,
) -> str:
    if attempt_id is not None and not ATTEMPT_RE.fullmatch(attempt_id):
        raise RuntimeError("activation_guard_attempt_identity_invalid")
    marker = _activation_marker_path(release_sha)
    transaction_dir = _activation_transaction_dir(release_sha)
    snapshot = transaction_dir / "pre-mutation.tar"
    state = transaction_dir / "pre-mutation.state"
    attempt_guard = (
        f"""  grep -Fxq 'attempt_id={attempt_id}' '{marker}' || return 1
  test "$(wc -l < '{marker}')" = '4' || return 1
"""
        if attempt_id is not None
        else f"""  marker_lines="$(wc -l < '{marker}')"
  case "$marker_lines" in
    3)
      test "$(grep -Ec '^attempt_id=' '{marker}')" = '0' || return 1
      test "$(wc -l < '{state}')" = '10' || return 1
      ;;
    4)
      test "$(grep -Ec '^attempt_id=[0-9a-f]{{32}}$' '{marker}')" = '1' || return 1
      test "$(wc -l < '{state}')" = '11' || return 1
      marker_attempt="$(sed -n 's/^attempt_id=//p' '{marker}')" || return 1
      grep -Fxq "attempt_id=$marker_attempt" '{state}' || return 1
      ;;
    *) return 1 ;;
  esac
"""
    )
    return f"""{_remote_activation_snapshot_guard_function(release_sha, attempt_id)}
verify_activation_transaction() {{
  verify_activation_snapshot || return 1
  test -f '{marker}' || return 1
  test ! -L '{marker}' || return 1
  test "$(stat -c '%a' '{marker}')" = '444' || return 1
  test "$(stat -c '%u:%g' '{marker}')" = '0:0' || return 1
  test "$(stat -c '%h' '{marker}')" = '1' || return 1
  grep -Fxq 'schema=dev-control-plane/hosted-rollout-transaction/v2' '{marker}' || return 1
  grep -Fxq 'release_sha={release_sha}' '{marker}' || return 1
{attempt_guard}
  expected_snapshot_sha="$(sed -n 's/^snapshot_sha256=//p' '{state}')" || return 1
  grep -Fxq "snapshot_sha256=$expected_snapshot_sha" '{marker}' || return 1
}}
"""


def _remote_begin_activation_script(release_sha: str, attempt_id: str) -> str:
    if not FULL_SHA_RE.fullmatch(release_sha) or not ATTEMPT_RE.fullmatch(attempt_id):
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
		{_remote_process_binding_function()}
		{_remote_activation_guard_function(release_sha, attempt_id)}
		{_remote_resolved_quarantine_guard_function()}
	{_remote_authority_state_guard_function()}
	{_remote_rollout_stage_function(release_sha, attempt_id)}
if [ -e '{marker}' ] || [ -L '{marker}' ]; then
  test -f '{marker}' && test ! -L '{marker}'
  marker_attempt="$(sed -n 's/^attempt_id=//p' '{marker}')"
  if [ "$marker_attempt" = '{attempt_id}' ]; then
    verify_activation_transaction
    printf 'begin=existing_owned\nrelease_sha={release_sha}\n'
  else
    printf 'begin=busy\nrelease_sha={release_sha}\n'
  fi
  exit 0
fi
if ! verify_no_unresolved_rollout_markers none '{release_sha}'; then
  printf 'begin=busy\nrelease_sha={release_sha}\n'
  exit 0
fi
if [ -e '{transaction_dir}' ] || [ -L '{transaction_dir}' ]; then
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
service_active="$(capture_unit_active_flag '{SERVICE_NAME}')"
service_enabled="$(capture_unit_enabled_flag '{SERVICE_NAME}')"
nginx_active="$(capture_unit_active_flag nginx)"
certbot_active="$(capture_unit_active_flag certbot.timer)"
certbot_enabled="$(capture_unit_enabled_flag certbot.timer)"
if [ "$service_active" = yes ] && [ "$prior_app_kind" = absent ]; then exit 84; fi
if [ "$prior_app_kind" = v2 ]; then
  verify_prior_projection_unit "$prior_release_sha"
  if [ "$service_active" = yes ]; then
    verify_projection_process "$prior_app" >/dev/null
    curl -fsS --connect-timeout 2 --max-time 5 http://{LOOPBACK_HOST}:{LOOPBACK_PORT}/api/v2/health 2>/dev/null | python3 -c 'import json,sys; p=json.load(sys.stdin); raise SystemExit(0 if (p.get("service_role") == "hosted_projection_v2" and p.get("control_authority") is False and p.get("mutation_routes_enabled") is False) else 1)'
  fi
fi
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
attempt_id={attempt_id}
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
attempt_id={attempt_id}
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
record_rollout_stage snapshot_created
printf 'begin=created\n'
printf 'release_sha={release_sha}\n'
"""


def _remote_process_binding_function() -> str:
    expected_unit_sha256 = hashlib.sha256(_systemd_unit().encode("utf-8")).hexdigest()
    return f"""verify_projection_unit_semantics() {{
  test -f '{SYSTEMD_UNIT_FILE}' && test ! -L '{SYSTEMD_UNIT_FILE}' || return 1
  test "$(stat -c '%a' '{SYSTEMD_UNIT_FILE}')" = '644' || return 1
  test "$(stat -c '%u:%g' '{SYSTEMD_UNIT_FILE}')" = '0:0' || return 1
  test "$(stat -c '%h' '{SYSTEMD_UNIT_FILE}')" = '1' || return 1
  test "$(systemctl show -p FragmentPath --value '{SERVICE_NAME}')" = '{SYSTEMD_UNIT_FILE}' || return 1
  projection_drop_ins="$(systemctl show -p DropInPaths --value '{SERVICE_NAME}')" || return 1
  test -z "$projection_drop_ins" || return 1
  test "$(grep -Fxc 'User={PROJECTION_SERVICE_USER}' '{SYSTEMD_UNIT_FILE}')" = '1' || return 1
  test "$(grep -Fxc 'Group={PROJECTION_SERVICE_GROUP}' '{SYSTEMD_UNIT_FILE}')" = '1' || return 1
  test "$(grep -Fxc 'WorkingDirectory={APP_DIR}' '{SYSTEMD_UNIT_FILE}')" = '1' || return 1
  test "$(grep -Fxc 'Environment=AUTHORITY_ROLE=hosted_projection_v2' '{SYSTEMD_UNIT_FILE}')" = '1' || return 1
  test "$(grep -Fxc 'ExecStart=/usr/bin/python3 {APP_DIR}/apps/dev_control_plane_projection_v2.py' '{SYSTEMD_UNIT_FILE}')" = '1' || return 1
  test "$(grep -Ec '^ExecStart=' '{SYSTEMD_UNIT_FILE}')" = '1' || return 1
  test "$(grep -Fxc 'NoNewPrivileges=true' '{SYSTEMD_UNIT_FILE}')" = '1' || return 1
  test "$(grep -Fxc 'ProtectSystem=strict' '{SYSTEMD_UNIT_FILE}')" = '1' || return 1
  test "$(grep -Fxc 'ReadWritePaths={PROJECTION_STATE_DIR}' '{SYSTEMD_UNIT_FILE}')" = '1' || return 1
  test "$(grep -Fxc 'InaccessiblePaths=-{LEGACY_STATE_DIR} -{ARCHIVE_DIR} -{RUNTIME_ROOT}/.codex -{RUNTIME_ROOT}/secrets -{RUNTIME_ROOT}/tools' '{SYSTEMD_UNIT_FILE}')" = '1' || return 1
}}
verify_candidate_projection_unit() {{
  verify_projection_unit_semantics || return 1
  test "$(sha256sum '{SYSTEMD_UNIT_FILE}' | awk '{{print $1}}')" = '{expected_unit_sha256}' || return 1
}}
verify_prior_projection_unit() {{
  prior_release_sha="$1"
  printf '%s' "$prior_release_sha" | grep -Eq '^[0-9a-f]{{40}}$' || return 1
  verify_projection_unit_semantics || return 1
  deployed_receipt='{ARCHIVE_DIR}/projection-v2-'"$prior_release_sha"'.DEPLOYED'
  test -f "$deployed_receipt" && test ! -L "$deployed_receipt" || return 1
  test "$(stat -c '%a' "$deployed_receipt")" = '444' || return 1
  test "$(stat -c '%u:%g' "$deployed_receipt")" = '0:0' || return 1
  test "$(stat -c '%h' "$deployed_receipt")" = '1' || return 1
  grep -Fxq 'schema=dev-control-plane/hosted-rollout-receipt/v2' "$deployed_receipt" || return 1
  grep -Fxq "release_sha=$prior_release_sha" "$deployed_receipt" || return 1
  grep -Fxq 'outcome=deployed' "$deployed_receipt" || return 1
  deployed_lines="$(wc -l < "$deployed_receipt")" || return 1
  case "$deployed_lines" in
    3)
      test "$(grep -Ec '^unit_sha256=' "$deployed_receipt")" = '0' || return 1
      return 1
      ;;
    4)
      test "$(grep -Ec '^unit_sha256=[0-9a-f]{{64}}$' "$deployed_receipt")" = '1' || return 1
      grep -Fxq "unit_sha256=$(sha256sum '{SYSTEMD_UNIT_FILE}' | awk '{{print $1}}')" "$deployed_receipt" || return 1
      ;;
    *) return 1 ;;
  esac
}}
verify_projection_process() {{
  expected_release="$1"
  verify_projection_unit_semantics || return 1
  test "$(systemctl is-active {SERVICE_NAME})" = 'active' || return 1
  test "$(readlink -f {APP_DIR})" = "$expected_release" || return 1
  main_pid="$(systemctl show -p MainPID --value {SERVICE_NAME})" || return 1
  printf '%s' "$main_pid" | grep -Eq '^[1-9][0-9]*$' || return 1
  test "$main_pid" -gt 1 || return 1
  test -d "/proc/$main_pid" || return 1
  test "$(readlink -f "/proc/$main_pid/cwd")" = "$expected_release" || return 1
  test "$(ps -o user= -p "$main_pid" | tr -d ' ')" = '{PROJECTION_SERVICE_USER}' || return 1
  for hidden in {LEGACY_STATE_DIR} {ARCHIVE_DIR} {RUNTIME_ROOT}/.codex {RUNTIME_ROOT}/secrets {RUNTIME_ROOT}/tools; do
    test ! -e "/proc/$main_pid/root$hidden" || return 1
  done
  test -r "/proc/$main_pid/root{PROJECTION_KEY_DEST}" || return 1
  tr '\\0' ' ' < "/proc/$main_pid/cmdline" | grep -Fq '/usr/bin/python3 {APP_DIR}/apps/dev_control_plane_projection_v2.py' || return 1
  grep -Fq '/{SERVICE_NAME}' "/proc/$main_pid/cgroup" || return 1
  listener="$(ss -H -ltnp 'sport = :{LOOPBACK_PORT}' 2>/dev/null)" || return 1
  test -n "$listener" || return 1
  printf '%s' "$listener" | grep -Fq "pid=$main_pid," || return 1
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
verify_prior_projection_unit "$sha"
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
{_remote_resolved_quarantine_guard_function()}
verify_no_unresolved_rollout_markers none none || exit 60
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
    attempt_id: str,
    fault_after: str | None = None,
) -> str:
    if (
        not FULL_SHA_RE.fullmatch(expected_current_sha)
        or not FULL_SHA_RE.fullmatch(expected_previous_sha)
        or not ATTEMPT_RE.fullmatch(attempt_id)
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
	{_remote_authority_state_guard_function()}
	{_remote_activation_guard_function(expected_previous_sha, attempt_id)}
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
verify_prior_projection_unit '{expected_current_sha}'
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
require_unit_inactive {SERVICE_NAME}
require_unit_disabled {SERVICE_NAME}
require_unit_main_pid_zero {SERVICE_NAME}
require_projection_port_free
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
    guard = _remote_resolved_quarantine_guard_function()
    if archive_dir != ARCHIVE_DIR:
        guard = guard.replace(str(ARCHIVE_DIR), archive_text)
    return f"""{guard}
if ! verify_no_unresolved_rollout_markers '{expected_marker}' '{expected_release_sha}'; then
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
        if key.startswith("GIT_"):
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
            "GIT_NO_REPLACE_OBJECTS": "1",
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


def _parse_exact_sanitized_key_value_lines(
    raw: str,
    allowed_keys: set[str],
) -> dict[str, str]:
    """Parse one bounded fixed-schema remote receipt without provider detail."""

    if len(raw.encode("utf-8", errors="ignore")) > 8192:
        raise ValueError("receipt_too_large")
    parsed: dict[str, str] = {}
    for line in raw.splitlines():
        if not line or "=" not in line:
            raise ValueError("receipt_line_invalid")
        key, value = line.split("=", 1)
        if key not in allowed_keys or key in parsed:
            raise ValueError("receipt_key_invalid_or_duplicate")
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", value):
            raise ValueError("receipt_value_not_sanitized")
        parsed[key] = value
    if set(parsed) != allowed_keys:
        raise ValueError("receipt_fields_incomplete")
    return parsed


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


def _git_is_ancestor(ancestor_sha: str, descendant_sha: str) -> bool:
    if not FULL_SHA_RE.fullmatch(ancestor_sha) or not FULL_SHA_RE.fullmatch(descendant_sha):
        return False
    graft_path = _git_run("rev-parse", "--path-format=absolute", "--git-path", "info/grafts")
    replacements = _git_run("for-each-ref", "--format=%(refname)", "refs/replace")
    if (
        graft_path.returncode != 0
        or replacements.returncode != 0
        or replacements.stdout.strip()
        or Path(graft_path.stdout.strip()).exists()
    ):
        return False
    completed = _git_run("merge-base", "--is-ancestor", ancestor_sha, descendant_sha)
    return completed.returncode == 0


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
