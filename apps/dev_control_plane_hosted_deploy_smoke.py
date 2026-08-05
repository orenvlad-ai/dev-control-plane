"""Exhaustive local smoke for the projection-v2 hosted rollout boundary."""

from __future__ import annotations

from contextlib import redirect_stdout
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "apps" / "dev_control_plane_hosted_deploy.py"
SYSTEMD_TEMPLATE = ROOT / "deploy" / "examples" / "systemd" / "dev-control-plane.service"
ENV_TEMPLATE = ROOT / "deploy" / "examples" / "systemd" / "dev-control-plane.environment.example"
NGINX_TEMPLATE = ROOT / "deploy" / "examples" / "reverse-proxy" / "nginx.dev-control-plane.conf.example"
TARGET = "89.191.226.88"
OLD = "95.163.244.138"
DOMAINS = ("devcontrol.pro", "www.devcontrol.pro")
SHA = "a" * 40
PREVIOUS_SHA = "b" * 40
ATTEMPT_ID = "1" * 32
KEY_MATERIAL = b"hosted-projection-v2-smoke-hmac-material-32-bytes"


def main() -> None:
    deploy = _load_deploy_module()
    with tempfile.TemporaryDirectory(prefix="dcp-hosted-v2-") as raw_temp:
        temp = Path(raw_temp)
        key_file = temp / "projection.hmac"
        key_file.write_bytes(KEY_MATERIAL)
        key_file.chmod(0o600)

        _assert_cli_contract(key_file)
        _assert_source_gate_matrix(deploy)
        _assert_git_transport_isolation(deploy)
        _assert_projection_key_matrix(deploy, temp, key_file)
        _assert_projection_key_snapshot_copy(deploy, key_file)
        _assert_dns_gate_matrix(deploy)
        _assert_certificate_gate_matrix(deploy)
        _assert_port_ownership_matrix(deploy)
        _assert_ssh_target_gate(deploy)
        _assert_remote_preflight_tool_contract(deploy)
        _assert_immutable_release_flow(deploy)
        _assert_remote_release_verifier_execution(deploy, temp)
        _assert_projection_only_install(deploy)
        _assert_nginx_boundary(deploy)
        _assert_templates(deploy)
        _assert_loopback_contract(deploy)
        _assert_loopback_identity_parser(deploy)
        _assert_rollback_contract(deploy)
        _assert_rollback_marker_conflict_guard(deploy, temp)
        _assert_rollback_eligibility_handlers(deploy)
        _assert_rollback_fault_recovery_handlers(deploy)
        _assert_live_rollback_target_gate(deploy)
        _assert_failure_rollback_guard(deploy, key_file)
        _assert_activation_recovery_parser(deploy)
        _assert_transaction_recovery_contract(deploy)
        _assert_probe_sanitization(deploy)
        _assert_signed_ingest_key_probe(deploy)
        _assert_read_only_proof_matrix(deploy)
        _assert_online_dry_run_enforces_gates(deploy)
        _assert_blocked_preflight_never_mutates(deploy)

    print("dev-control-plane-hosted-deploy-smoke passed")


def _assert_ssh_target_gate(deploy: Any) -> None:
    original_run = deploy.subprocess.run
    original_known_hosts = deploy.TRUSTED_KNOWN_HOSTS_FILE
    calls: list[list[str]] = []
    with tempfile.TemporaryDirectory(prefix="dcp-hosted-known-hosts-") as raw:
      known_hosts = Path(raw) / "known_hosts"
      known_hosts.write_text("89.191.226.88 ssh-ed25519 AAAATEST\n", encoding="utf-8")
      known_hosts.chmod(0o600)
      deploy.TRUSTED_KNOWN_HOSTS_FILE = known_hosts
      try:
        def approved_run(*args: Any, **kwargs: Any) -> Any:
            calls.append(list(args[0]))
            if args[0][0] == "/usr/bin/ssh-keygen":
                return SimpleNamespace(returncode=0, stdout="# Host found\n", stderr="")
            return SimpleNamespace(
                returncode=0,
                stdout=(
                    "hostname 89.191.226.88\nuser root\nport 22\n"
                    "stricthostkeychecking yes\nproxycommand none\nproxyjump none\n"
                ),
                stderr="",
            )

        deploy.subprocess.run = approved_run
        assert deploy._local_ssh_target_gate()["status"] == "passed"
        def normalized_run(*args: Any, **kwargs: Any) -> Any:
            if args[0][0] == "/usr/bin/ssh-keygen":
                return SimpleNamespace(returncode=0, stdout="# Host found\n", stderr="")
            return SimpleNamespace(
                returncode=0,
                stdout=(
                    "hostname 89.191.226.88\nuser root\nport 22\n"
                    "stricthostkeychecking true\nproxycommand none\nproxyjump none\n"
                ),
                stderr="",
            )
        deploy.subprocess.run = normalized_run
        assert deploy._local_ssh_target_gate()["status"] == "passed"
        deploy.subprocess.run = approved_run
        deploy._ssh("true")
        assert calls[0] == [
            "/usr/bin/ssh", "-G", *deploy.SSH_EXEC_OPTIONS, "wb-core-eu-root"
        ]
        transport = calls[2]
        assert transport[0] == "/usr/bin/ssh"
        for option in (
            "HostName=89.191.226.88",
            "User=root",
            "Port=22",
            "ProxyCommand=none",
            "ProxyJump=none",
            "ControlMaster=no",
            "ControlPath=none",
            "ClearAllForwardings=yes",
            "StrictHostKeyChecking=yes",
            f"UserKnownHostsFile={original_known_hosts}",
            "GlobalKnownHostsFile=/dev/null",
            "HostKeyAlias=89.191.226.88",
        ):
            assert option in transport
        assert transport[-2:] == ["wb-core-eu-root", "true"]
        for policy in ("accept-new", "ask", "no", "off", ""):
            def rejected_run(*args: Any, _policy: str = policy, **kwargs: Any) -> Any:
                if args[0][0] == "/usr/bin/ssh-keygen":
                    return SimpleNamespace(returncode=0, stdout="# Host found\n", stderr="")
                return SimpleNamespace(
                    returncode=0,
                    stdout=(
                        "hostname 89.191.226.88\nuser root\nport 22\n"
                        f"stricthostkeychecking {_policy}\nproxycommand none\nproxyjump none\n"
                    ),
                    stderr="",
                )
            deploy.subprocess.run = rejected_run
            blocked = deploy._local_ssh_target_gate()
            assert blocked["status"] == "blocked", policy
            assert "ssh_strict_host_key_checking_not_pinned" in blocked["blockers"]

        deploy.TRUSTED_KNOWN_HOSTS_FILE = Path(raw) / "missing-known-hosts"
        deploy.subprocess.run = approved_run
        missing = deploy._local_ssh_target_gate()
        assert missing["status"] == "blocked"
        assert "ssh_trusted_known_hosts_missing" in missing["blockers"]
      finally:
        deploy.subprocess.run = original_run
        deploy.TRUSTED_KNOWN_HOSTS_FILE = original_known_hosts


def _assert_remote_preflight_tool_contract(deploy: Any) -> None:
    expected_tools = (
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
        "stat",
    )
    command_log: list[str] = []
    stdout = "\n".join(
        (
            *(f"tool_{name}=ready" for name in expected_tools),
            "rsync_exact=ready",
            "bash_exact=ready",
            "webcore_site=present",
            "basic_auth=ready",
            "service_active=inactive",
            "health=unavailable",
            "port_owner=free",
            "legacy_state=present",
            "current_release=legacy_or_absent",
            "previous_release=none",
            "cert_present=no",
            "certbot_timer_enabled=disabled",
            "certbot_timer_active=inactive",
            "acme_route=no",
            "renewal_webroot=no",
            "deploy_hook=no",
            "rollout_guard=ready",
        )
    ) + "\n"
    original_ssh = deploy._ssh
    try:
        deploy._ssh = lambda command: command_log.append(command) or subprocess.CompletedProcess(
            ["ssh"], 0, stdout, ""
        )
        result = deploy._remote_preflight(expected_release_sha=SHA)
    finally:
        deploy._ssh = original_ssh
    assert len(command_log) == 1
    expected_loop = f"for tool in {' '.join(expected_tools)}; do"
    assert expected_loop in command_log[0]
    assert "case \"$exact_mode\" in 555|755)" in command_log[0]
    assert "stat -c '%u:%g'" in command_log[0]
    assert "stat -c '%h'" in command_log[0]
    assert tuple(result["tools"]) == expected_tools
    assert len(result["tools"]) == 17
    assert all(result["tools"].values())
    assert result["rsync_exact_path"] == "/usr/bin/rsync"
    assert result["bash_exact_path"] == "/bin/bash"
    assert "remote_rsync_exact_path_unavailable" not in result["blockers"]

    missing_exact = stdout.replace("rsync_exact=ready", "rsync_exact=missing_or_unsafe")
    try:
        deploy._ssh = lambda _command: subprocess.CompletedProcess(["ssh"], 0, missing_exact, "")
        blocked = deploy._remote_preflight(expected_release_sha=SHA)
    finally:
        deploy._ssh = original_ssh
    assert blocked["rsync_exact_path"] is None
    assert "remote_rsync_exact_path_unavailable" in blocked["blockers"]

    missing_bash = stdout.replace("bash_exact=ready", "bash_exact=missing_or_unsafe")
    try:
        deploy._ssh = lambda _command: subprocess.CompletedProcess(["ssh"], 0, missing_bash, "")
        blocked_bash = deploy._remote_preflight(expected_release_sha=SHA)
    finally:
        deploy._ssh = original_ssh
    assert blocked_bash["bash_exact_path"] is None
    assert "remote_bash_exact_path_unavailable" in blocked_bash["blockers"]


def _assert_cli_contract(key_file: Path) -> None:
    deploy = _load_deploy_module()
    assert str(deploy.DEFAULT_PROJECTION_KEY_FILE).endswith(
        "/.dev-control-plane-v2/secrets/projection_hmac.key"
    )
    plan = _run("print-plan")
    plan_payload = plan.get("plan") or {}
    expected = {
        "target_host_ip": "89.191.226.88",
        "ssh_alias": "wb-core-eu-root",
        "expected_repository": "orenvlad-ai/dev-control-plane",
        "service_name": "dev-control-plane.service",
        "authority_role": "hosted_projection_v2",
        "loopback": "127.0.0.1:8770",
        "current_link": "/opt/dev-control-plane-runtime/app",
        "previous_link": "/opt/dev-control-plane-runtime/previous",
        "projection_database": "/opt/dev-control-plane-runtime/projection/state/projection.sqlite3",
        "projection_key_file": "/opt/dev-control-plane-runtime/projection/secrets/projection-v2.hmac",
    }
    for key, value in expected.items():
        assert plan_payload.get(key) == value, (key, plan_payload.get(key), value)
    assert plan_payload["releases_dir"].endswith("/releases/<verified-origin-main-sha>")
    assert "only exact /api/v2/ingest" in plan_payload["auth_boundary"]
    assert plan_payload["legacy_state_archive_marker"].endswith("legacy-state-v1.READ_ONLY")
    assert "/opt/wb-core-runtime" in plan_payload["forbidden_paths"]

    validation = _run("validate", "--offline", "--projection-key-file", str(key_file))
    assert validation["status"] in {"passed", "allowed_with_warning"}, validation
    gate = validation["validation"]
    assert gate["remote"]["skipped"] is True
    assert gate["projection_key"]["status"] == "ready"
    assert gate["source"]["enforced"] is False
    encoded_validation = json.dumps(validation, sort_keys=True)
    assert str(key_file) not in encoded_validation
    assert KEY_MATERIAL.decode() not in encoded_validation

    dry_run = _run(
        "deploy",
        "--dry-run",
        "--offline",
        "--projection-key-file",
        str(key_file),
    )
    assert dry_run["status"] == "dry_run_passed"
    assert dry_run["live_executed"] is False
    commands = "\n".join(dry_run["planned_commands"])
    required = (
        "source gate",
        "immutable",
        "without --delete",
        "0600 HMAC",
        "projection-only systemd",
        "AUTHORITY_ROLE=hosted_projection_v2",
        "ACME",
        "fresh >= 21 days",
        "atomically switch",
        "WebCore",
    )
    for token in required:
        assert token in commands, token
    for forbidden in ("provision hosted toolchain", "Codex", "OpenAI", "GitHub CLI", "gh auth"):
        assert forbidden not in commands, forbidden

    rollback = _run("rollback-plan")
    assert rollback["rollback"]["legacy_fallback"] is False
    assert rollback["rollback"]["state_deletion"] is False
    assert "/releases/<previous-verified-v2-sha>" in rollback["rollback"]["allowed_target"]
    # Rollback dry-run is intentionally online: its handler is exercised with
    # an exact remote eligibility receipt below rather than inferred locally.


def _assert_source_gate_matrix(deploy: Any) -> None:
    original_git_run = deploy._git_run
    original_value = deploy._local_git_value
    facts = {
        "origin": "https://github.com/orenvlad-ai/dev-control-plane.git",
        "head": SHA,
        "origin_main": SHA,
        "branch": "main",
        "status": "",
        "fetch_rc": 0,
        "rewrite": False,
        "rewrite_probe_rc": 1,
    }
    git_calls: list[tuple[str, ...]] = []

    def fake_value(*args: str) -> str | None:
        keys = {
            ("config", "--local", "--get", "remote.origin.url"): "origin",
            ("rev-parse", "HEAD"): "head",
            ("rev-parse", "refs/remotes/origin/main"): "origin_main",
            ("branch", "--show-current"): "branch",
        }
        key = keys.get(tuple(args))
        return None if key is None else str(facts[key])

    def fake_git_run(*args: str) -> subprocess.CompletedProcess[str]:
        git_calls.append(tuple(args))
        if args[:3] == ("config", "--show-origin", "--get-regexp"):
            output = "file:.git/config url.file:///tmp/evil.insteadOf git@github.com:\n" if facts["rewrite"] else ""
            return subprocess.CompletedProcess(args, int(facts["rewrite_probe_rc"]), output, "")
        if "fetch" in args:
            return subprocess.CompletedProcess(args, int(facts["fetch_rc"]), "", "provider detail must not escape")
        if args and args[0] == "status":
            return subprocess.CompletedProcess(args, 0, str(facts["status"]), "")
        return subprocess.CompletedProcess(args, 0, "", "")

    try:
        deploy._git_run = fake_git_run
        deploy._local_git_value = fake_value
        passed = deploy._source_gate(enforced=True, fetch_origin=True)
        assert passed.status == "passed" and not passed.blockers
        assert passed.exact_repository and passed.clean and passed.head_matches_origin_main
        assert passed.fetched_origin_main
        fetch_call = next(call for call in git_calls if "fetch" in call)
        assert deploy.CANONICAL_FETCH_URL in fetch_call
        assert "origin" not in fetch_call
        assert any(item.startswith("core.sshCommand=ssh ") for item in fetch_call)

        facts["rewrite"] = True
        facts["rewrite_probe_rc"] = 0
        rewritten = deploy._source_gate(enforced=True, fetch_origin=True)
        assert "source_git_url_rewrite_forbidden" in rewritten.blockers
        assert not rewritten.fetched_origin_main
        reported_rewrite = deploy._source_gate(enforced=False, fetch_origin=False)
        assert not reported_rewrite.blockers
        assert "dry_run_only:source_git_url_rewrite_forbidden" in reported_rewrite.warnings
        facts["rewrite"] = False
        facts["rewrite_probe_rc"] = 1

        facts["status"] = "?? untracked\n"
        dirty = deploy._source_gate(enforced=True, fetch_origin=True)
        assert dirty.status == "blocked" and "source_worktree_not_clean" in dirty.blockers
        reported = deploy._source_gate(enforced=False, fetch_origin=False)
        assert not reported.blockers
        assert "dry_run_only:source_worktree_not_clean" in reported.warnings

        facts["status"] = ""
        facts["head"] = PREVIOUS_SHA
        mismatch = deploy._source_gate(enforced=True, fetch_origin=True)
        assert "source_head_not_origin_main" in mismatch.blockers

        facts["head"] = SHA
        facts["origin"] = "https://github.com/example/wrong.git"
        wrong_repo = deploy._source_gate(enforced=True, fetch_origin=True)
        assert "source_repository_mismatch" in wrong_repo.blockers

        facts["origin"] = "https://github.com/orenvlad-ai/dev-control-plane.git"
        facts["fetch_rc"] = 1
        fetch_failed = deploy._source_gate(enforced=True, fetch_origin=True)
        assert "source_origin_main_fetch_failed" in fetch_failed.blockers
        assert "provider detail" not in json.dumps(deploy.asdict(fetch_failed))
    finally:
        deploy._git_run = original_git_run
        deploy._local_git_value = original_value


def _assert_git_transport_isolation(deploy: Any) -> None:
    original_run = deploy.subprocess.run
    captured: list[tuple[list[str], dict[str, str]]] = []
    try:
        def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            captured.append((list(command), dict(kwargs.get("env") or {})))
            return subprocess.CompletedProcess(command, 0, "", "")

        deploy.subprocess.run = fake_run
        deploy._git_run("status", "--porcelain=v1")
    finally:
        deploy.subprocess.run = original_run
    command, environment = captured[0]
    assert command[:2] == ["git", "status"]
    assert environment["GIT_CONFIG_NOSYSTEM"] == "1"
    assert environment["GIT_CONFIG_SYSTEM"] == os.devnull
    assert environment["GIT_CONFIG_GLOBAL"] == os.devnull
    assert environment["GIT_TERMINAL_PROMPT"] == "0"
    assert "GIT_SSH_COMMAND" not in environment and "GIT_CONFIG_COUNT" not in environment


def _assert_projection_key_matrix(deploy: Any, temp: Path, valid_key: Path) -> None:
    ready = deploy._projection_key_gate(valid_key, required=True)
    assert ready.status == "ready"
    assert ready.mode == "0600" and ready.regular_file and not ready.symlink

    public_key = temp / "public.hmac"
    public_key.write_bytes(KEY_MATERIAL)
    public_key.chmod(0o644)
    wrong_mode = deploy._projection_key_gate(public_key, required=True)
    assert wrong_mode.status == "blocked"
    assert wrong_mode.blockers == ["projection_key_mode_must_be_0600"]

    short_key = temp / "short.hmac"
    short_key.write_bytes(b"too-short")
    short_key.chmod(0o600)
    short = deploy._projection_key_gate(short_key, required=True)
    assert short.status == "blocked"
    assert any("size" in item or "material" in item for item in short.blockers)

    link = temp / "linked.hmac"
    link.symlink_to(valid_key)
    linked = deploy._projection_key_gate(link, required=True)
    assert linked.status == "blocked" and linked.symlink
    assert "projection_key_not_regular_or_is_symlink" in linked.blockers

    hardlink = temp / "hardlinked.hmac"
    os.link(valid_key, hardlink)
    hardlinked = deploy._projection_key_gate(valid_key, required=True)
    assert hardlinked.status == "blocked"
    assert hardlinked.blockers == ["projection_key_must_have_single_link"]
    hardlink.unlink()

    missing = deploy._projection_key_gate(temp / "missing.hmac", required=False)
    assert missing.status == "reported_missing" and not missing.blockers and missing.warnings
    for result in (ready, wrong_mode, short, linked, hardlinked, missing):
        serialized = json.dumps(deploy.asdict(result), sort_keys=True)
        assert str(valid_key) not in serialized
        assert KEY_MATERIAL.decode() not in serialized


def _assert_projection_key_snapshot_copy(deploy: Any, valid_key: Path) -> None:
    original_sender = deploy._ssh_bytes_checked
    captured: list[tuple[str, bytes, str]] = []
    try:
        deploy._ssh_bytes_checked = lambda command, payload, *, operation: captured.append(
            (command, payload, operation)
        )
        deploy._copy_projection_key(valid_key, SHA, ATTEMPT_ID)
    finally:
        deploy._ssh_bytes_checked = original_sender
    assert len(captured) == 1
    command, payload, operation = captured[0]
    assert payload == KEY_MATERIAL
    assert operation == "install_projection_hmac_key"
    assert str(valid_key) not in command and KEY_MATERIAL.decode() not in command
    assert "cat > /opt/dev-control-plane-runtime/projection/secrets/.projection-v2.hmac." in command
    assert "stat -c '%h'" in command and "test \"$size\" -le 4096" in command
    assert "chown dev-control-plane-projection:dev-control-plane-projection" in command
    assert "verify_activation_transaction" in command
    assert f"projection-v2-{SHA}.ACTIVATING" in command
    assert "scp" not in command
    syntax = subprocess.run(["bash", "-n"], input=command, text=True, capture_output=True, check=False)
    assert syntax.returncode == 0, syntax.stderr


def _assert_dns_gate_matrix(deploy: Any) -> None:
    local_stale = _local_dns(OLD)
    doh_clean = _doh_dns(TARGET)
    remote_clean = _remote_dns(TARGET)
    allowed = deploy._evaluate_dns_gate(local_stale, doh_clean, remote_clean)
    assert allowed.status == "allowed_with_warning" and not allowed.blockers
    assert "local_dns_stale:devcontrol.pro" in allowed.warnings
    remote_stale = deploy._evaluate_dns_gate(local_stale, doh_clean, _remote_dns(OLD))
    assert remote_stale.status == "blocked"
    assert any(item.startswith("remote_dns_") for item in remote_stale.blockers)
    doh_stale = deploy._evaluate_dns_gate(local_stale, _doh_dns(OLD), remote_clean)
    assert doh_stale.status == "blocked"
    assert any(item.startswith("doh_") for item in doh_stale.blockers)
    unavailable = deploy._evaluate_dns_gate(local_stale, doh_clean, {"returncode": 1, "domains": {}})
    assert unavailable.status == "blocked" and "remote_dns_probe_unavailable" in unavailable.blockers


def _assert_certificate_gate_matrix(deploy: Any) -> None:
    ready_payload = {
        "present": True,
        "not_after_epoch": 2_000_000_000,
        "days_remaining": 90,
        "fresh_21d": True,
        "currently_valid": True,
        "timer_enabled": True,
        "timer_active": True,
        "acme_route": True,
        "renewal_webroot": True,
        "deploy_hook": True,
        "parse_invalid": False,
    }
    ready = deploy._evaluate_certificate_gate(ready_payload)
    assert ready.status == "ready" and not ready.remediation_reasons and ready.expires_at

    expired_payload = dict(ready_payload, days_remaining=-2, currently_valid=False, fresh_21d=False)
    expired = deploy._evaluate_certificate_gate(expired_payload)
    assert expired.status == "renewal_required"
    assert "certificate_expired" in expired.remediation_reasons
    assert deploy._validation_allows_live("renewal_required")

    missing_payload = dict(
        ready_payload,
        present=False,
        not_after_epoch=None,
        days_remaining=None,
        currently_valid=False,
        fresh_21d=False,
    )
    missing = deploy._evaluate_certificate_gate(missing_payload)
    assert missing.status == "renewal_required" and "certificate_missing" in missing.remediation_reasons

    broken_renewal = deploy._evaluate_certificate_gate(
        dict(
            ready_payload,
            timer_enabled=False,
            timer_active=False,
            acme_route=False,
            renewal_webroot=False,
            deploy_hook=False,
        )
    )
    assert broken_renewal.status == "renewal_required"
    for reason in (
        "certbot_timer_not_enabled",
        "certbot_timer_not_active",
        "permanent_acme_route_missing",
        "webroot_renewal_configuration_missing",
        "certificate_deploy_hook_missing",
    ):
        assert reason in broken_renewal.remediation_reasons

    invalid = deploy._evaluate_certificate_gate(dict(ready_payload, parse_invalid=True, not_after_epoch=None))
    assert invalid.status == "blocked" and "certificate_expiry_unreadable" in invalid.blockers


def _assert_port_ownership_matrix(deploy: Any) -> None:
    free = deploy._evaluate_port_8770_ownership({"port_owner": "free", "service_active": "inactive"})
    assert free.status == "free" and not free.blockers
    own_v2 = deploy._evaluate_port_8770_ownership(
        {
            "port_owner": "service",
            "service_active": "active",
            "health_role": "hosted_projection_v2",
            "health_control": "false",
            "health_mutation": "false",
        }
    )
    assert own_v2.status == "allowed_existing_projection_v2" and not own_v2.blockers
    own_legacy = deploy._evaluate_port_8770_ownership(
        {"port_owner": "service", "service_active": "active", "health_role": "legacy"}
    )
    assert own_legacy.status == "allowed_owned_legacy_migration"
    assert "owned_legacy_service_will_be_replaced_not_retained" in own_legacy.warnings
    foreign = deploy._evaluate_port_8770_ownership(
        {"port_owner": "foreign", "service_active": "inactive"}
    )
    assert foreign.status == "blocked" and foreign.blockers == ["port_8770_owned_by_foreign_process"]


def _assert_immutable_release_flow(deploy: Any) -> None:
    with tempfile.TemporaryDirectory(prefix="dcp-projection-git-object-smoke-") as raw_fixture:
        fixture_root = Path(raw_fixture) / "source"
        fixture_root.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=fixture_root, check=True)
        subprocess.run(["git", "config", "user.email", "smoke@example.invalid"], cwd=fixture_root, check=True)
        subprocess.run(["git", "config", "user.name", "Smoke"], cwd=fixture_root, check=True)
        for release_file in deploy.RELEASE_FILES:
            destination = fixture_root / release_file
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes((ROOT / release_file).read_bytes())
        subprocess.run(["git", "add", "."], cwd=fixture_root, check=True)
        subprocess.run(["git", "commit", "-qm", "projection-fixture"], cwd=fixture_root, check=True)
        head_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=fixture_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        original_root = deploy.ROOT
        deploy.ROOT = fixture_root
        try:
            with tempfile.TemporaryDirectory(prefix="dcp-projection-package-smoke-") as raw_package:
                built_root = Path(raw_package)
                built_digest = deploy._build_projection_release_package(built_root, head_sha)
                manifest_bytes = (built_root / ".release-manifest.json").read_bytes()
                manifest = json.loads(manifest_bytes)
                assert built_digest == __import__("hashlib").sha256(manifest_bytes).hexdigest()
                assert manifest["release_sha"] == head_sha
                assert set(manifest["files"]) == set(deploy.RELEASE_FILES)
                for release_file, digest in manifest["files"].items():
                    blob = subprocess.run(
                        ["git", "show", f"{head_sha}:{release_file}"],
                        cwd=fixture_root,
                        check=True,
                        capture_output=True,
                    ).stdout
                    assert (built_root / release_file).read_bytes() == blob
                    assert digest == __import__("hashlib").sha256(blob).hexdigest()
                with tempfile.TemporaryDirectory(prefix="dcp-openrsync-layout-smoke-") as raw_layout:
                    layout_root = Path(raw_layout)
                    subprocess.run(
                        [
                            str(deploy.LOCAL_RSYNC),
                            "-aR",
                            "--chmod=Du=rwx,Dgo=rx,Fu=rw,Fgo=r",
                            *(f"./{relative}" for relative in deploy.RELEASE_FILES),
                            "./.release-manifest.json",
                            f"{layout_root}/",
                        ],
                        cwd=built_root,
                        check=True,
                        capture_output=True,
                        text=True,
                    )
                    actual_files = {
                        item.relative_to(layout_root).as_posix()
                        for item in layout_root.rglob("*")
                        if item.is_file()
                    }
                    assert actual_files == {*deploy.RELEASE_FILES, ".release-manifest.json"}
                    assert not (layout_root / "private").exists()
        finally:
            deploy.ROOT = original_root

    staging = Path(
        f"/opt/dev-control-plane-runtime/releases/.incoming-{SHA}-{ATTEMPT_ID}"
    )
    package = Path("/private/tmp/dcp-projection-package")
    manifest_digest = "d" * 64
    command = deploy._release_rsync_command(staging, package, SHA, ATTEMPT_ID)
    joined = " ".join(command)
    assert command[:2] == ["/usr/bin/rsync", "-aR"]
    assert "--delete" not in command
    assert "HostName=89.191.226.88" in joined
    assert "ProxyCommand=none" in joined and "ControlMaster=no" in joined
    assert "StrictHostKeyChecking=yes" in joined
    receiver_path = deploy._remote_rsync_receiver_path(SHA, ATTEMPT_ID)
    successor_receiver_path = deploy._remote_rsync_receiver_path(SHA, "2" * 32)
    assert successor_receiver_path != receiver_path
    assert f"--rsync-path={receiver_path}" in command
    assert "\n" not in next(item for item in command if item.startswith("--rsync-path="))
    assert f"wb-core-eu-root:{staging}/" == command[-1]
    for release_file in deploy.RELEASE_FILES:
        assert release_file in joined
        assert f"./{release_file}" in command
    assert "./.release-manifest.json" in command
    assert str(package) not in joined
    original_local_rsync = deploy.LOCAL_RSYNC
    try:
        deploy.LOCAL_RSYNC = Path("/missing/exact-rsync")
        assert deploy._local_rsync_exact_path_ready() is False
        offline_blocked = deploy._validate_safety(offline=True)
        assert "local_rsync_exact_path_unavailable" in offline_blocked.blockers
        try:
            deploy._release_rsync_command(staging, package, SHA, ATTEMPT_ID)
        except RuntimeError as exc:
            assert str(exc) == "local_rsync_exact_path_unavailable"
        else:
            raise AssertionError("missing exact local rsync was accepted")
    finally:
        deploy.LOCAL_RSYNC = original_local_rsync

    original_run = deploy.subprocess.run
    try:
        def denied_run(*_args: Any, **_kwargs: Any) -> Any:
            raise PermissionError("simulated executable race")

        deploy.subprocess.run = denied_run
        try:
            deploy._run_checked(["/usr/bin/rsync"], operation="copy_projection_release")
        except RuntimeError as exc:
            assert str(exc) == "copy_projection_release_failed"
        else:
            raise AssertionError("transport OSError bypassed sanitized RuntimeError")
    finally:
        deploy.subprocess.run = original_run
    for forbidden in (
        "dev_control_plane_server.py",
        "target_production",
        "mcp_server",
        ".env",
        "auth.json",
    ):
        assert forbidden not in joined

    prepare = deploy._remote_prepare_runtime_script(staging, SHA, ATTEMPT_ID)
    receiver_body = deploy._remote_rsync_receiver_body(staging, SHA, ATTEMPT_ID)
    syntax = subprocess.run(
        ["bash", "-n"],
        input=receiver_body,
        text=True,
        capture_output=True,
        check=False,
    )
    assert syntax.returncode == 0, syntax.stderr
    assert receiver_body.startswith("#!/bin/bash\nset -euo pipefail\n")
    assert "flock -w 300 -x 9" in receiver_body
    assert "verify_activation_transaction" in receiver_body
    assert f"projection-v2-{SHA}.ACTIVATING" in receiver_body
    assert 'test "$1" = --server' in receiver_body
    assert 'test "$receiver_arg" != --sender' in receiver_body
    assert f"test \"$receiver_destination\" = '{staging}/'" in receiver_body
    assert 'exec /usr/bin/rsync "$@"' in receiver_body
    assert str(receiver_path) in prepare
    assert "chmod 0500" in prepare
    finalize = deploy._remote_finalize_release_script(
        SHA, staging, manifest_digest, ATTEMPT_ID
    )
    assert f"/releases/{SHA}" in prepare
    assert "test ! -e" in prepare
    assert "previous" in prepare and "dev_control_plane_projection_v2.py" in prepare
    assert f"mv {staging} /opt/dev-control-plane-runtime/releases/{SHA}" in finalize
    assert ".deploy-commit" in finalize
    assert ".deploy-manifest-digest" in finalize and manifest_digest in finalize
    assert "verify_projection_release" in prepare + finalize
    assert "find " in finalize and "-type f -exec chmod 0444" in finalize
    assert "-type d -exec chmod 0555" in finalize
    verifier = deploy._remote_manifest_verifier_function()
    assert "require(actual_files == expected_all_files" in verifier
    assert "require(actual_directories == expected_directories" in verifier
    assert "require(stat.S_IMODE(metadata.st_mode) == 0o444" in verifier
    assert "require(stat.S_IMODE(metadata.st_mode) == 0o555" in verifier
    assert "require(metadata.st_uid == 0 and metadata.st_gid == 0" in verifier
    assert "assert " not in verifier
    assert "unsupported release path type" in verifier
    assert "rsync" not in finalize and "--delete" not in finalize
    assert "rm -rf" not in prepare + finalize


def _assert_remote_release_verifier_execution(deploy: Any, temp: Path) -> None:
    release = temp / "strict-release"
    release.mkdir(mode=0o700)
    files: dict[str, str] = {}
    for relative in deploy.RELEASE_FILES:
        candidate = release / relative
        candidate.parent.mkdir(parents=True, exist_ok=True)
        payload = f"strict fixture: {relative}\n".encode()
        candidate.write_bytes(payload)
        files[relative] = __import__("hashlib").sha256(payload).hexdigest()
    manifest = {
        "schema": "dev-control-plane/hosted-projection-release/v2",
        "release_sha": SHA,
        "files": files,
    }
    manifest_bytes = (
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    (release / ".release-manifest.json").write_bytes(manifest_bytes)
    (release / ".deploy-commit").write_text(SHA + "\n", encoding="utf-8")
    (release / ".deploy-manifest-digest").write_text(
        __import__("hashlib").sha256(manifest_bytes).hexdigest() + "\n",
        encoding="utf-8",
    )
    for candidate in release.rglob("*"):
        candidate.chmod(0o555 if candidate.is_dir() else 0o444)
    release.chmod(0o555)

    verifier = deploy._remote_manifest_verifier_function()
    verifier = verifier.replace(
        "root_metadata.st_uid == 0 and root_metadata.st_gid == 0",
        f"root_metadata.st_uid == {os.geteuid()} and root_metadata.st_gid == {os.getegid()}",
    ).replace(
        "metadata.st_uid == 0 and metadata.st_gid == 0",
        f"metadata.st_uid == {os.geteuid()} and metadata.st_gid == {os.getegid()}",
    )
    command = verifier + '\nverify_projection_release "$1" "$2"\n'

    def run_verifier() -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", "-c", command, "strict-verifier", str(release), SHA],
            capture_output=True,
            text=True,
            check=False,
        )

    try:
        assert run_verifier().returncode == 0

        payload_file = release / deploy.RELEASE_FILES[0]
        payload_file.chmod(0o644)
        assert run_verifier().returncode != 0
        payload_file.chmod(0o444)

        apps_dir = release / "apps"
        apps_dir.chmod(0o755)
        extra = release / "apps" / "sitecustomize.py"
        extra.write_text("raise RuntimeError('must never execute')\n", encoding="utf-8")
        extra.chmod(0o444)
        apps_dir.chmod(0o555)
        assert run_verifier().returncode != 0
    finally:
        for candidate in sorted(release.rglob("*"), reverse=True):
            candidate.chmod(0o700 if candidate.is_dir() else 0o600)
        release.chmod(0o700)


def _assert_projection_only_install(deploy: Any) -> None:
    script = deploy._remote_install_script(DOMAINS, SHA, attempt_id=ATTEMPT_ID)
    required = (
        f"/releases/{SHA}",
        "/apps/dev_control_plane_projection_v2.py",
        "AUTHORITY_ROLE=hosted_projection_v2",
        "DEV_CONTROL_PLANE_PROJECTION_V2_DB=/opt/dev-control-plane-runtime/projection/state/projection.sqlite3",
        "DEV_CONTROL_PLANE_PROJECTION_V2_HMAC_KEY_FILE=/opt/dev-control-plane-runtime/projection/secrets/projection-v2.hmac",
        "UMask=0077",
        "ReadWritePaths=/opt/dev-control-plane-runtime/projection/state",
        "User=dev-control-plane-projection",
        "Group=dev-control-plane-projection",
        "InaccessiblePaths=-/opt/dev-control-plane-runtime/state -/opt/dev-control-plane-runtime/archive -/opt/dev-control-plane-runtime/.codex -/opt/dev-control-plane-runtime/secrets -/opt/dev-control-plane-runtime/tools",
        "legacy-state-v1.READ_ONLY",
        "archive_role=read_only_audit_history",
        "mutation_authority=disabled",
        "mv -Tf /opt/dev-control-plane-runtime/.app.next.$$ /opt/dev-control-plane-runtime/app",
        "mv -Tf /opt/dev-control-plane-runtime/.previous.next.$$ /opt/dev-control-plane-runtime/previous",
        "certbot certonly --cert-name devcontrol.pro --webroot",
        f"openssl x509 -checkend {21 * 86400}",
        "systemctl enable --now certbot.timer",
        "dev-control-plane-nginx-reload",
        "flock -w 300 -x 9",
        f"projection-v2-{SHA}.ACTIVATING",
        "wait_for_projection_process",
        "/proc/$main_pid/cgroup",
        "pid=$main_pid,",
    )
    for token in required:
        assert token in script, token
    forbidden = (
        "dev_control_plane_server.py",
        "DEV_CONTROL_PLANE_CODEX",
        "CODEX_HOME",
        "OPENAI",
        "GITHUB",
        "gh auth",
        "apt-get",
        "node",
        "pnpm",
        "yarn",
        "remote_provision",
        "rsync --delete",
        "rm -rf",
        "/opt/wb-core-runtime",
        "/etc/nginx/sites-enabled/wb-ai",
    )
    for token in forbidden:
        assert token not in script, token
    # The legacy credential root appears only in the repeated unit/process
    # isolation proofs; it is never read, copied, provisioned or passed to the
    # projection process.
    assert script.count("/opt/dev-control-plane-runtime/secrets") == 5
    assert "cat /opt/dev-control-plane-runtime/secrets" not in script
    assert "chown -R dev-control-plane:dev-control-plane /opt/dev-control-plane-runtime" not in script
    prepare = deploy._remote_prepare_runtime_script(
        Path(f"/opt/dev-control-plane-runtime/releases/.incoming-{SHA}-{ATTEMPT_ID}"),
        SHA,
        ATTEMPT_ID,
    )
    assert "groupadd --system dev-control-plane-projection" in prepare
    assert "useradd --system --gid dev-control-plane-projection" in prepare
    assert "find /opt/dev-control-plane-runtime/projection -xdev -type l" in prepare
    assert "find /opt/dev-control-plane-runtime/projection -xdev -type f -links +1" in prepare
    assert "chown --no-dereference dev-control-plane-projection:dev-control-plane-projection /opt/dev-control-plane-runtime/projection " in prepare
    assert "chown -R --no-dereference" not in prepare
    renewal_script = deploy._remote_install_script(
        DOMAINS,
        SHA,
        attempt_id=ATTEMPT_ID,
        force_certificate_refresh=True,
    )
    assert "elif [ '1' = '1' ]" in renewal_script
    assert "--force-renewal" in renewal_script
    # The only no-Basic-Auth ingest stanza is installed after exact
    # systemd/process/socket/release proof, never while legacy may own 8770.
    assert script.count("auth_basic off;") == 2  # final config plus its exact post-write assertion
    assert script.index("wait_for_projection_process") < script.index("auth_basic off;")
    marker_index = script.index(f"projection-v2-{SHA}.ACTIVATING")
    switch_index = script.index("mv -Tf /opt/dev-control-plane-runtime/.app.next.$$")
    assert marker_index < switch_index

    completed_scripts: list[str] = []
    original_ssh_checked = deploy._ssh_checked
    try:
        deploy._ssh_checked = lambda command, *, operation: completed_scripts.append(command)
        deploy._complete_remote_activation(SHA, ATTEMPT_ID)
    finally:
        deploy._ssh_checked = original_ssh_checked
    assert len(completed_scripts) == 1
    completion = completed_scripts[0]
    assert "outcome=deployed" in completion
    expected_unit_sha256 = hashlib.sha256(
        deploy._systemd_unit().encode("utf-8")
    ).hexdigest()
    receipt_body = completion.split("<<'DCP_DEPLOYED_RECEIPT'\n", 1)[1].split(
        "\nDCP_DEPLOYED_RECEIPT", 1
    )[0]
    assert receipt_body.splitlines() == [
        "schema=dev-control-plane/hosted-rollout-receipt/v2",
        f"release_sha={SHA}",
        "outcome=deployed",
        f"unit_sha256={expected_unit_sha256}",
    ]
    binding = deploy._remote_process_binding_function()
    assert "verify_projection_unit_semantics()" in binding
    assert "verify_candidate_projection_unit()" in binding
    assert "verify_prior_projection_unit()" in binding
    assert f"= '{expected_unit_sha256}'" in binding
    assert 'case "$deployed_lines" in' in binding
    assert "3)\n      test \"$(grep -Ec '^unit_sha256='" in binding
    assert "return 1" in binding
    assert "4)" in binding and "unit_sha256=$(sha256sum" in binding
    assert "\n\tverify_candidate_projection_unit\n" in completion
    assert completion.index("DCP_FSYNC_RECEIPT") < completion.index(
        f"unlink /opt/dev-control-plane-runtime/archive/projection-v2-{SHA}.ACTIVATING"
    )

    shell = "\n".join(
        (
            deploy._remote_begin_activation_script(SHA, ATTEMPT_ID),
            deploy._remote_prepare_runtime_script(
                Path(f"/opt/dev-control-plane-runtime/releases/.incoming-{SHA}-{ATTEMPT_ID}"),
                SHA,
                ATTEMPT_ID,
            ),
            deploy._remote_finalize_release_script(
                SHA,
                Path(f"/opt/dev-control-plane-runtime/releases/.incoming-{SHA}-{ATTEMPT_ID}"),
                "d" * 64,
                ATTEMPT_ID,
            ),
            script,
            completion,
            deploy._remote_rollback_eligibility_script(),
            deploy._remote_rollback_script(
                expected_current_sha=SHA,
                expected_previous_sha=PREVIOUS_SHA,
                attempt_id=ATTEMPT_ID,
            ),
            deploy._remote_failed_rollout_recovery_script(SHA, ATTEMPT_ID),
        )
    )
    syntax = subprocess.run(["bash", "-n"], input=shell, text=True, capture_output=True, check=False)
    assert syntax.returncode == 0, syntax.stderr


def _assert_nginx_boundary(deploy: Any) -> None:
    config = deploy._nginx_config(include_tls=True)
    assert config.count("auth_basic off;") == 1
    assert "location = /api/v2/ingest" in config
    assert "location ^~ /.well-known/acme-challenge/" in config
    assert "server_name devcontrol.pro www.devcontrol.pro;\n    return 301" not in config
    assert "location / {\n        return 301 https://$host$request_uri;" in config
    assert 'auth_basic "Development Control Plane";' in config
    guarded = deploy._nginx_config(include_tls=True, allow_signed_ingest=False)
    assert "location = /api/v2/ingest" in guarded
    assert "auth_basic off;" not in guarded
    for forbidden_public in (
        "location = /mcp",
        "location = /mcp/stream",
        "location = /oauth/token",
        "location = /oauth/register",
        "oauth-protected-resource",
        "openid-configuration",
    ):
        assert forbidden_public not in config
    bootstrap = deploy._nginx_config(include_tls=False)
    assert "listen 443" not in bootstrap
    assert "location ^~ /.well-known/acme-challenge/" in bootstrap
    assert "auth_basic off" not in bootstrap


def _assert_templates(deploy: Any) -> None:
    unit = SYSTEMD_TEMPLATE.read_text(encoding="utf-8")
    assert unit.strip() == deploy._systemd_unit().strip()
    environment = ENV_TEMPLATE.read_text(encoding="utf-8")
    generated_environment = deploy._projection_environment()
    for line in generated_environment.splitlines():
        assert line in environment
    nginx = NGINX_TEMPLATE.read_text(encoding="utf-8")
    assert nginx.count("auth_basic off;") == 1
    assert "location = /api/v2/ingest" in nginx
    assert "location ^~ /.well-known/acme-challenge/" in nginx
    assert "server_name devcontrol.pro www.devcontrol.pro;\n    return 301" not in nginx
    combined = unit + environment
    for forbidden in ("CODEX", "OPENAI", "GITHUB", "SSH", "dev_control_plane_server.py"):
        assert forbidden not in combined, forbidden
    assert "UMask=0077" in unit
    assert "User=dev-control-plane-projection" in unit
    assert "ReadOnlyPaths=/opt/dev-control-plane-runtime/releases /opt/dev-control-plane-runtime/projection/secrets" in unit
    assert "InaccessiblePaths=-/opt/dev-control-plane-runtime/state" in unit


def _assert_loopback_contract(deploy: Any) -> None:
    script = deploy._remote_loopback_wait_script(str(deploy.RELEASES_DIR / SHA))
    assert "for attempt in $(seq 1 60)" in script
    assert "/api/v2/health" in script
    assert 'p.get("service_role") == "hosted_projection_v2"' in script
    assert 'p.get("control_authority") is False' in script
    assert 'p.get("mutation_routes_enabled") is False' in script
    assert 'p.get("projection_ingestion_enabled") is True' in script
    assert "systemctl show -p MainPID" in script
    assert "/proc/$main_pid/cwd" in script
    assert "/proc/$main_pid/cgroup" in script
    assert "systemctl show -p FragmentPath --value 'dev-control-plane.service'" in script
    assert "systemctl show -p DropInPaths --value 'dev-control-plane.service'" in script
    expected_unit_sha256 = hashlib.sha256(
        deploy._systemd_unit().encode("utf-8")
    ).hexdigest()
    assert f"= '{expected_unit_sha256}'" in script
    assert "verify_candidate_projection_unit()" in script
    assert "verify_prior_projection_unit()" in script
    assert 'test ! -e "/proc/$main_pid/root$hidden"' in script
    assert "test -r \"/proc/$main_pid/root/opt/dev-control-plane-runtime/projection/secrets/projection-v2.hmac\"" in script
    assert "ss -H -ltnp" in script and "pid=$main_pid," in script
    assert "dev-control-plane-projection" in script
    assert "/mcp" not in script
    assert "systemctl --no-pager" not in script


def _assert_loopback_identity_parser(deploy: Any) -> None:
    original_ssh = deploy._ssh
    try:
        deploy._ssh = lambda command: subprocess.CompletedProcess(
            ["ssh"], 0, f"main_pid=4321\nhealth=verified\nrelease={SHA}\n", ""
        )
        proof = deploy._remote_loopback_health()
        assert proof["release_sha"] == SHA
        assert proof["systemd_main_pid"] == 4321
        assert proof["process_release_bound"] is True
        assert proof["socket_owner_bound"] is True

        deploy._ssh = lambda command: subprocess.CompletedProcess(
            ["ssh"], 0, f"health=verified\nrelease={SHA}\n", ""
        )
        try:
            deploy._remote_loopback_health()
        except RuntimeError as exc:
            assert str(exc) == "loopback_projection_health_invalid"
        else:
            raise AssertionError("loopback proof accepted without a bound systemd MainPID")
    finally:
        deploy._ssh = original_ssh


def _assert_rollback_contract(deploy: Any) -> None:
    eligibility = deploy._remote_rollback_eligibility_script()
    assert "reason_code=not_eligible_first_release" in eligibility
    assert "verified_release_count=1" in eligibility
    assert 'test "$only_verified_release" = "$current"' in eligibility
    assert 'test "$previous" != "$current"' in eligibility
    assert "eligible=yes" in eligibility
    assert eligibility.count("verify_projection_release") >= 2
    script = deploy._remote_rollback_script(
        expected_current_sha=SHA,
        expected_previous_sha=PREVIOUS_SHA,
        attempt_id=ATTEMPT_ID,
    )
    assert "readlink -f /opt/dev-control-plane-runtime/previous" in script
    assert "readlink -f /opt/dev-control-plane-runtime/app" in script
    assert "/opt/dev-control-plane-runtime/releases/*" in eligibility
    assert "dev_control_plane_projection_v2.py" in script
    assert "ExecStart=/usr/bin/python3 /opt/dev-control-plane-runtime/app/apps/dev_control_plane_projection_v2.py" in script
    assert "mv -Tf /opt/dev-control-plane-runtime/.app.rollback.$$ /opt/dev-control-plane-runtime/app" in script
    assert "mv -Tf /opt/dev-control-plane-runtime/.previous.rollback.$$ /opt/dev-control-plane-runtime/previous" in script
    assert f"test \"$current\" = '/opt/dev-control-plane-runtime/releases/{SHA}'" in script
    assert f"test \"$previous\" = '/opt/dev-control-plane-runtime/releases/{PREVIOUS_SHA}'" in script
    assert 'test "$previous" != "$current"' in script
    assert f"wait_for_projection_process '/opt/dev-control-plane-runtime/releases/{PREVIOUS_SHA}'" in script
    assert f"wait_for_projection_process '/opt/dev-control-plane-runtime/releases/{SHA}'" in script
    assert ".app.rollback-restore.$$" in script
    assert "systemctl disable dev-control-plane.service" in script
    assert "unlink /etc/nginx/sites-enabled/dev-control-plane" in script
    assert "ss -H -ltnp 'sport = :8770'" in script
    assert "verify_activation_transaction" in script
    assert f"projection-v2-{PREVIOUS_SHA}.ACTIVATING" in script
    for boundary in deploy.ROLLBACK_FAULT_BOUNDARIES:
        faulted = deploy._remote_rollback_script(
            expected_current_sha=SHA,
            expected_previous_sha=PREVIOUS_SHA,
            attempt_id=ATTEMPT_ID,
            fault_after=boundary,
        )
        marker = f"exit 97 # DCP_FAULT_BOUNDARY {boundary}"
        assert marker in faulted, boundary
        assert faulted.count("exit 97 # DCP_FAULT_BOUNDARY") == 1, boundary
    for forbidden in ("legacy-app", "legacy-state", "dev_control_plane_server.py", "rm -f"):
        assert forbidden not in script

    recovery = deploy._remote_failed_rollout_recovery_script(SHA, ATTEMPT_ID)
    begin = deploy._remote_begin_activation_script(SHA, ATTEMPT_ID)
    guard = deploy._remote_activation_guard_function(SHA, ATTEMPT_ID)
    cleanup = deploy._remote_staging_cleanup_function(SHA)
    assert f"projection-v2-{SHA}.ACTIVATING" in recovery
    assert "flock -w 300 -x 9" in recovery
    assert "recovery=not_activated" in recovery
    assert "recovery=restored" in recovery
    assert "recovery=quarantined" in recovery
    assert "systemctl stop 'dev-control-plane.service'" in recovery
    assert "systemctl disable 'dev-control-plane.service'" in recovery
    assert "DCP_DISABLE_PROJECTION_SITE" in recovery
    assert "case \"$active\" in '/opt/dev-control-plane-runtime/releases'/*) unlink '/opt/dev-control-plane-runtime/app'" in recovery
    assert "authority=disabled" in recovery
    assert "DCP_VALIDATE_SNAPSHOT" in recovery
    assert "snapshot member outside allowlist" in recovery
    assert "DCP_CLEAR_MUTATED_PATHS" in recovery
    assert "tar --extract --file=" in recovery
    assert "prior_kind" in recovery and "prior_release_sha" in recovery
    assert "hosted-rollout-receipt/v2" in recovery
    assert "ss -H -ltnp 'sport = :8770'" in recovery
    for preserved in ("/opt/dev-control-plane-runtime/projection/state", "legacy-app-v1", "legacy-state-v1"):
        assert f"unlink {preserved}" not in recovery
    assert "rm -rf" not in recovery

    assert "pre-mutation.tar" in begin and "pre-mutation.state" in begin
    assert "tar --create" in begin and "--files-from=" in begin
    assert "snapshot_sha256=$snapshot_sha" in begin
    assert "DCP_FSYNC_SNAPSHOT" in begin and "DCP_FSYNC_MARKER" in begin
    assert begin.index("DCP_FSYNC_SNAPSHOT") < begin.index("DCP_ACTIVATION_MARKER")
    assert begin.index("DCP_FSYNC_MARKER") < begin.index("begin=created")
    for path in deploy.ROLLOUT_SNAPSHOT_PATHS:
        assert str(path) in begin
    assert "sha256sum" in guard and "snapshot_sha256=" in guard
    assert f".incoming-{SHA}-" in cleanup
    assert "STAGING_CLEANED" in cleanup and "removed_count=" in cleanup
    assert "DCP_FSYNC_STAGING_CLEANUP_DIR" in cleanup
    assert f"if [ -e '/opt/dev-control-plane-runtime/archive/projection-v2-{SHA}.STAGING_CLEANED' ]" in cleanup
    assert 'test "$removed" = 0 || return 1' in cleanup
    assert cleanup.index('test "$removed" = 0 || return 1') < cleanup.index("receipt_next=")
    assert "cleanup_projection_staging" in recovery

    staging = Path(f"/opt/dev-control-plane-runtime/releases/.incoming-{SHA}-{ATTEMPT_ID}")
    mutation_scripts = (
        deploy._remote_prepare_runtime_script(staging, SHA, ATTEMPT_ID),
        deploy._remote_finalize_release_script(SHA, staging, "d" * 64, ATTEMPT_ID),
        deploy._remote_install_script(DOMAINS, SHA, attempt_id=ATTEMPT_ID),
        deploy._remote_rollback_script(
            expected_current_sha=SHA,
            expected_previous_sha=PREVIOUS_SHA,
            attempt_id=ATTEMPT_ID,
        ),
    )
    for mutation_script in mutation_scripts:
        assert "verify_activation_transaction" in mutation_script
        assert (
            f"projection-v2-{SHA}.ACTIVATING" in mutation_script
            or f"projection-v2-{PREVIOUS_SHA}.ACTIVATING" in mutation_script
        )
    complete = deploy._complete_remote_activation
    assert callable(complete)


def _assert_rollback_marker_conflict_guard(deploy: Any, temp: Path) -> None:
    archive = temp / "rollback-marker-state"
    archive.mkdir()
    own_marker = archive / f"projection-v2-{PREVIOUS_SHA}.ACTIVATING"
    own_marker.write_text("owned transaction\n", encoding="utf-8")
    guard = deploy._remote_rollback_marker_conflict_guard(
        PREVIOUS_SHA,
        archive_dir=archive,
    )

    def run_guard() -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", "-c", f"set -euo pipefail\n{guard}\nprintf 'guard=passed\\n'"],
            capture_output=True,
            text=True,
            check=False,
        )

    own_only = run_guard()
    assert own_only.returncode == 0 and own_only.stdout == "guard=passed\n"

    foreign_marker = archive / f"projection-v2-{SHA}.ACTIVATING"
    foreign_marker.write_text("foreign transaction\n", encoding="utf-8")
    assert run_guard().returncode == 60
    foreign_marker.unlink()

    quarantine = archive / f"projection-v2-{SHA}.QUARANTINED"
    quarantine.write_text("quarantined transaction\n", encoding="utf-8")
    assert run_guard().returncode == 60


def _assert_live_rollback_target_gate(deploy: Any) -> None:
    original_gate = deploy._local_ssh_target_gate
    original_ssh = deploy._ssh_checked
    original_print = deploy._print_json
    ssh_calls: list[str] = []
    payloads: list[dict[str, Any]] = []
    try:
        deploy._local_ssh_target_gate = lambda: {
            "status": "blocked",
            "blockers": ["ssh_alias_target_ip_mismatch"],
        }
        deploy._ssh_checked = lambda *args, **kwargs: ssh_calls.append("ssh")
        deploy._print_json = lambda payload: payloads.append(payload)
        result = deploy._handle_rollback(SimpleNamespace(dry_run=False))
        assert result == 1
        assert not ssh_calls
        assert payloads[-1]["blockers"] == ["ssh_alias_target_ip_mismatch"]
    finally:
        deploy._local_ssh_target_gate = original_gate
        deploy._ssh_checked = original_ssh
        deploy._print_json = original_print


def _assert_rollback_eligibility_handlers(deploy: Any) -> None:
    originals = {
        "_local_ssh_target_gate": deploy._local_ssh_target_gate,
        "_remote_rollback_eligibility": deploy._remote_rollback_eligibility,
        "_begin_remote_activation": deploy._begin_remote_activation,
        "_ssh_checked": deploy._ssh_checked,
        "_prove_live_read_only": deploy._prove_live_read_only,
        "_complete_remote_activation": deploy._complete_remote_activation,
        "_record_remote_rollout_stage": deploy._record_remote_rollout_stage,
        "_recover_failed_projection_rollout": deploy._recover_failed_projection_rollout,
        "_print_json": deploy._print_json,
    }
    payloads: list[dict[str, Any]] = []
    mutations: list[tuple[str, str]] = []
    transactions: list[tuple[str, str]] = []
    eligibility = {
        "eligible": True,
        "current_sha": SHA,
        "previous_sha": PREVIOUS_SHA,
        "distinct": True,
    }
    try:
        deploy._local_ssh_target_gate = lambda: {"status": "passed", "blockers": []}
        deploy._remote_rollback_eligibility = lambda: eligibility
        deploy._begin_remote_activation = lambda sha, _attempt_id: transactions.append(
            ("begin", sha)
        ) or "created"
        deploy._print_json = lambda payload: payloads.append(payload)
        deploy._ssh_checked = lambda command, *, operation: mutations.append((command, operation))
        deploy._prove_live_read_only = lambda *, expected_release=None: {
            "loopback": {"release_sha": expected_release}
        }
        deploy._complete_remote_activation = lambda sha, _attempt_id: transactions.append(
            ("complete", sha)
        )
        deploy._recover_failed_projection_rollout = lambda sha, _attempt_id: transactions.append(
            ("recover", sha)
        ) or "restored"

        dry_result = deploy._handle_rollback(SimpleNamespace(dry_run=True))
        assert dry_result == 0 and not mutations
        assert payloads[-1]["status"] == "dry_run_passed"
        assert payloads[-1]["eligibility"] == eligibility

        live_result = deploy._handle_rollback(SimpleNamespace(dry_run=False))
        assert live_result == 0 and len(mutations) == 1
        assert transactions == [("begin", PREVIOUS_SHA), ("complete", PREVIOUS_SHA)]
        command, operation = mutations[0]
        assert operation == "projection_v2_rollback"
        assert f"test \"$current\" = '/opt/dev-control-plane-runtime/releases/{SHA}'" in command
        assert f"test \"$previous\" = '/opt/dev-control-plane-runtime/releases/{PREVIOUS_SHA}'" in command
        assert payloads[-1]["status"] == "rolled_back"

        deploy._remote_rollback_eligibility = lambda: {
            "eligible": False,
            "reason_code": "not_eligible_first_release",
            "current_sha": SHA,
            "previous_sha": None,
            "distinct": False,
            "verified_release_count": 1,
        }
        first_release_result = deploy._handle_rollback(SimpleNamespace(dry_run=True))
        assert first_release_result == 0 and len(mutations) == 1
        assert payloads[-1]["status"] == "dry_run_not_eligible_first_release"
        assert payloads[-1]["eligibility"]["verified_release_count"] == 1

        first_release_live_result = deploy._handle_rollback(SimpleNamespace(dry_run=False))
        assert first_release_live_result == 1 and len(mutations) == 1
        assert payloads[-1]["blockers"] == [
            "projection_v2_rollback_not_eligible_first_release"
        ]

        deploy._remote_rollback_eligibility = lambda: (_ for _ in ()).throw(
            RuntimeError("projection_v2_rollback_not_eligible")
        )
        blocked_result = deploy._handle_rollback(SimpleNamespace(dry_run=True))
        assert blocked_result == 1
        assert payloads[-1]["blockers"] == ["projection_v2_rollback_not_eligible"]
    finally:
        for name, value in originals.items():
            setattr(deploy, name, value)


def _assert_rollback_fault_recovery_handlers(deploy: Any) -> None:
    originals = {
        "_local_ssh_target_gate": deploy._local_ssh_target_gate,
        "_remote_rollback_eligibility": deploy._remote_rollback_eligibility,
        "_begin_remote_activation": deploy._begin_remote_activation,
        "_remote_rollback_script": deploy._remote_rollback_script,
        "_ssh_checked": deploy._ssh_checked,
        "_recover_failed_projection_rollout": deploy._recover_failed_projection_rollout,
        "_print_json": deploy._print_json,
    }
    try:
        deploy._local_ssh_target_gate = lambda: {"status": "passed", "blockers": []}
        deploy._remote_rollback_eligibility = lambda: {
            "eligible": True,
            "current_sha": SHA,
            "previous_sha": PREVIOUS_SHA,
            "distinct": True,
        }
        deploy._begin_remote_activation = lambda _sha, _attempt_id: "created"
        real_builder = originals["_remote_rollback_script"]
        for boundary in deploy.ROLLBACK_FAULT_BOUNDARIES:
            recoveries: list[str] = []
            payloads: list[dict[str, Any]] = []
            deploy._remote_rollback_script = lambda **kwargs: real_builder(
                **kwargs, fault_after=boundary
            )

            def fail_at_boundary(command: str, *, operation: str) -> None:
                assert operation == "projection_v2_rollback"
                assert f"exit 97 # DCP_FAULT_BOUNDARY {boundary}" in command
                raise RuntimeError("simulated_remote_rollback_fault")

            deploy._ssh_checked = fail_at_boundary
            deploy._recover_failed_projection_rollout = lambda sha, _attempt_id: (
                recoveries.append(sha) or "restored"
            )
            deploy._print_json = lambda payload: payloads.append(payload)
            result = deploy._handle_rollback(SimpleNamespace(dry_run=False))
            assert result == 1, boundary
            assert recoveries == [PREVIOUS_SHA], boundary
            assert payloads[-1]["blockers"] == [
                "rollback_failed_prior_host_state_restored"
            ], boundary
    finally:
        for name, value in originals.items():
            setattr(deploy, name, value)


def _assert_failure_rollback_guard(deploy: Any, key_file: Path) -> None:
    originals = {
        "_source_gate": deploy._source_gate,
        "_ssh": deploy._ssh,
        "_ssh_checked": deploy._ssh_checked,
        "_ssh_bytes_checked": deploy._ssh_bytes_checked,
        "_begin_remote_activation": deploy._begin_remote_activation,
        "_remote_release_exists": deploy._remote_release_exists,
        "_run_checked": deploy._run_checked,
        "_install_projection_key_snapshot": deploy._install_projection_key_snapshot,
        "_build_projection_release_package": deploy._build_projection_release_package,
        "_recover_failed_projection_rollout": deploy._recover_failed_projection_rollout,
        "_prove_live_read_only": deploy._prove_live_read_only,
        "_complete_remote_activation": deploy._complete_remote_activation,
        "_record_remote_rollout_stage": deploy._record_remote_rollout_stage,
    }
    try:
        # A missed fake must fail locally, never fall through to SSH/rsync/curl.
        deploy._ssh = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("hosted smoke attempted SSH")
        )
        deploy._ssh_bytes_checked = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("hosted smoke attempted secret transport")
        )

        def passed_source() -> Any:
            return deploy.SourceGateResult(
                status="passed",
                enforced=True,
                fetched_origin_main=True,
                exact_repository=True,
                clean=True,
                head_matches_origin_main=True,
                head_sha=SHA,
                origin_main_sha=SHA,
                branch="main",
                blockers=[],
                warnings=[],
            )

        def run_case(
            fail_stage: str | None,
            *,
            recovery_outcome: str = "restored",
            begin_status: str = "created",
        ) -> tuple[list[str], list[str], str | None]:
            events: list[str] = []
            recoveries: list[str] = []
            source_calls = 0
            package_root_seen: Path | None = None

            def maybe_fail(stage: str) -> None:
                events.append(stage)
                if fail_stage == stage:
                    raise RuntimeError(f"simulated_{stage}_failure")

            def source_gate(**_: Any) -> Any:
                nonlocal source_calls
                source_calls += 1
                stage = "source_initial" if source_calls == 1 else "source_recheck"
                maybe_fail(stage)
                return passed_source()

            def ssh_checked(_: str, *, operation: str) -> None:
                stage = {
                    "prepare_projection_runtime": "prepare",
                    "finalize_immutable_projection_release": "finalize",
                    "activate_projection_v2_release": "install",
                }[operation]
                maybe_fail(stage)

            def recover(sha: str, _attempt_id: str) -> str:
                recoveries.append(sha)
                if recovery_outcome == "unavailable":
                    raise RuntimeError("simulated_recovery_unavailable")
                return recovery_outcome

            deploy._source_gate = source_gate
            def build_package(package_root: Path, _release_sha: str) -> str:
                nonlocal package_root_seen
                package_root_seen = package_root
                maybe_fail("package")
                return "d" * 64

            def run_checked(_command: Any, *, operation: str, cwd: Path) -> None:
                assert operation == "copy_projection_release"
                assert cwd == package_root_seen
                maybe_fail("rsync")

            deploy._build_projection_release_package = build_package
            deploy._begin_remote_activation = lambda _sha, _attempt_id: (
                maybe_fail("begin") or begin_status
            )
            deploy._ssh_checked = ssh_checked
            deploy._remote_release_exists = lambda *_args: (
                maybe_fail("release_probe") or False
            )
            deploy._run_checked = run_checked
            deploy._install_projection_key_snapshot = lambda *_args: maybe_fail("key")
            deploy._prove_live_read_only = lambda **_kwargs: (
                maybe_fail("proof") or {"loopback": {"release_sha": SHA}}
            )
            deploy._complete_remote_activation = lambda _sha, _attempt_id: maybe_fail(
                "complete"
            )
            deploy._record_remote_rollout_stage = lambda *_args: None
            deploy._recover_failed_projection_rollout = recover

            error: str | None = None
            try:
                result = deploy._deploy_live(
                    cert_domains=DOMAINS,
                    release_sha=SHA,
                    projection_key_file=key_file,
                )
                assert fail_stage is None or (
                    fail_stage == "complete" and recovery_outcome == "completed"
                )
                assert result["loopback"]["release_sha"] == SHA
            except RuntimeError as exc:
                error = str(exc)
            return events, recoveries, error

        before_transaction_events, before_transaction_recoveries, before_transaction_error = run_case(
            "package"
        )
        assert before_transaction_events == ["source_initial", "package"]
        assert not before_transaction_recoveries
        assert before_transaction_error == "simulated_package_failure"

        begin_events, begin_recoveries, begin_error = run_case("begin")
        assert begin_events == ["source_initial", "package", "begin"]
        assert not begin_recoveries
        assert begin_error == "simulated_begin_failure"

        for stage in (
            "prepare",
            "release_probe",
            "rsync",
            "finalize",
            "source_recheck",
            "key",
            "install",
            "proof",
            "complete",
        ):
            events, recoveries, error = run_case(stage)
            assert events.index("begin") < events.index(stage), (stage, events)
            assert recoveries == [SHA], (stage, recoveries)
            assert error == "rollout_failed_prior_host_state_restored", (stage, error)

        success_events, success_recoveries, success_error = run_case(None)
        assert success_error is None and not success_recoveries
        assert success_events == [
            "source_initial",
            "package",
            "begin",
            "prepare",
            "release_probe",
            "rsync",
            "finalize",
            "source_recheck",
            "key",
            "install",
            "proof",
            "complete",
        ]

        _, recoveries, error = run_case("proof", recovery_outcome="quarantined")
        assert recoveries == [SHA]
        assert error == "rollout_proof_failed_unverified_projection_quarantined"

        _, recoveries, error = run_case("proof", recovery_outcome="unavailable")
        assert recoveries == [SHA]
        assert error == "rollout_proof_failed_quarantine_failed"

        outer = RuntimeError("rollout_proof_failed_unverified_projection_quarantined")
        inner = RuntimeError("finalize_immutable_projection_release_failed")
        outer.__cause__ = inner
        assert deploy._sanitized_runtime_reason_codes(outer) == [
            "rollout_proof_failed_unverified_projection_quarantined",
            "finalize_immutable_projection_release_failed",
        ]
        unsafe = RuntimeError("provider body: secret")
        assert deploy._sanitized_runtime_reason_codes(unsafe) == [
            "unsanitized_runtime_failure"
        ]

        _, recoveries, error = run_case("complete", recovery_outcome="completed")
        assert recoveries == [SHA]
        assert error is None

        _, recoveries, error = run_case(None, begin_status="busy")
        assert not recoveries
        assert error == "rollout_transaction_busy"
    finally:
        for name, value in originals.items():
            setattr(deploy, name, value)


def _assert_activation_recovery_parser(deploy: Any) -> None:
    original_ssh = deploy._ssh
    try:
        for outcome, stdout in (
            ("completed", "recovery=completed\n"),
            ("not_activated", "recovery=not_activated\n"),
            ("quarantined", "recovery=quarantined\n"),
            ("restored", f"recovery=restored\nprior_kind=v2\nrelease={PREVIOUS_SHA}\n"),
        ):
            deploy._ssh = lambda command, payload=stdout: subprocess.CompletedProcess(
                ["ssh"], 0, payload, ""
            )
            assert deploy._recover_failed_projection_rollout(SHA, ATTEMPT_ID) == outcome

        for forbidden_prior in ("legacy", "absent"):
            deploy._ssh = lambda command, prior=forbidden_prior: subprocess.CompletedProcess(
                ["ssh"], 0, f"recovery=restored\nprior_kind={prior}\n", ""
            )
            try:
                deploy._recover_failed_projection_rollout(SHA, ATTEMPT_ID)
            except RuntimeError as exc:
                assert str(exc) == "failed_rollout_recovery_receipt_invalid"
            else:
                raise AssertionError("legacy/absent recovery was accepted as a rollback target")

        deploy._ssh = lambda command: subprocess.CompletedProcess(["ssh"], 255, "", "network detail")
        try:
            deploy._recover_failed_projection_rollout(SHA, ATTEMPT_ID)
        except RuntimeError as exc:
            assert str(exc) == "failed_rollout_recovery_unavailable"
        else:
            raise AssertionError("unknown activation readback was accepted")
    finally:
        deploy._ssh = original_ssh


def _assert_transaction_recovery_contract(deploy: Any) -> None:
    snapshot_sha256 = "d" * 64

    def transaction_stdout(
        *,
        attempt_id: str = ATTEMPT_ID,
        snapshot: str = snapshot_sha256,
        stage: str = "marker_created",
        age_seconds: int = 899,
        prior_kind: str = "absent",
        prior_release_sha: str = "none",
        extra_line: str | None = None,
    ) -> str:
        lines = [
            "transaction=verified_active",
            f"release_sha={SHA}",
            f"attempt_id={attempt_id}",
            f"snapshot_sha256={snapshot}",
            f"stage={stage}",
            f"stage_age_seconds={age_seconds}",
            f"prior_kind={prior_kind}",
            f"prior_release_sha={prior_release_sha}",
        ]
        if extra_line is not None:
            lines.append(extra_line)
        return "\n".join(lines) + "\n"

    def expect_runtime(reason: str, callback: Any) -> None:
        try:
            callback()
        except RuntimeError as exc:
            assert str(exc) == reason
        else:
            raise AssertionError(f"expected RuntimeError({reason})")

    # The CLI binds exact transaction identities and requires an explicit
    # dry-run/live choice before a recovery handler can run.
    parser_calls: list[tuple[str, Any]] = []
    original_status_handler = deploy._handle_transaction_status
    original_recover_handler = deploy._handle_transaction_recover
    try:
        deploy._handle_transaction_status = lambda args: parser_calls.append(
            ("status", args)
        ) or 17
        deploy._handle_transaction_recover = lambda args: parser_calls.append(
            ("recover", args)
        ) or 19
        assert deploy.main(["transaction-status", "--release-sha", SHA]) == 17
        assert parser_calls[-1][0] == "status"
        assert parser_calls[-1][1].release_sha == SHA
        assert deploy.main(
            [
                "transaction-recover",
                "--release-sha",
                SHA,
                "--attempt-id",
                ATTEMPT_ID,
                "--snapshot-sha256",
                snapshot_sha256,
                "--expected-stage",
                "nginx_guarded",
                "--dry-run",
            ]
        ) == 19
        parsed = parser_calls[-1][1]
        assert parser_calls[-1][0] == "recover"
        assert parsed.release_sha == SHA and parsed.attempt_id == ATTEMPT_ID
        assert parsed.snapshot_sha256 == snapshot_sha256
        assert parsed.expected_stage == "nginx_guarded"
        assert parsed.dry_run is True and parsed.live is False
    finally:
        deploy._handle_transaction_status = original_status_handler
        deploy._handle_transaction_recover = original_recover_handler

    commands: list[str] = []
    original_ssh = deploy._ssh
    try:
        deploy._ssh = lambda command: commands.append(command) or subprocess.CompletedProcess(
            ["ssh"], 0, transaction_stdout(), "provider detail must not escape"
        )
        marker_evidence = deploy._remote_transaction_status(SHA)
        assert marker_evidence == {
            "release_sha": SHA,
            "attempt_id": ATTEMPT_ID,
            "snapshot_sha256": snapshot_sha256,
            "stage": "marker_created",
            "stage_age_seconds": 899,
            "minimum_recovery_age_seconds": 900,
            "stale_recovery_eligible": False,
            "prior_kind": "absent",
            "prior_release_sha": None,
            "mutation_authority": "fenced_to_exact_attempt",
            "raw_remote_payload_exposed": False,
        }
        status_script = commands[-1]
        assert "flock -w 30 -s 9" in status_script
        assert "stage=marker_created" in status_script
        assert "activity_path=" in status_script and "stage_age_seconds=" in status_script
        assert "for required_tool in find findmnt sync awk" in status_script
        syntax = subprocess.run(
            ["bash", "-n"], input=status_script, text=True, capture_output=True, check=False
        )
        assert syntax.returncode == 0, syntax.stderr

        deploy._ssh = lambda _command: subprocess.CompletedProcess(
            ["ssh"],
            0,
            transaction_stdout(
                stage="nginx_guarded",
                age_seconds=901,
                prior_kind="v2",
                prior_release_sha=PREVIOUS_SHA,
            ),
            "",
        )
        later_evidence = deploy._remote_transaction_status(SHA)
        assert later_evidence["stage"] == "nginx_guarded"
        assert later_evidence["stage_age_seconds"] == 901
        assert later_evidence["stale_recovery_eligible"] is True
        assert later_evidence["prior_release_sha"] == PREVIOUS_SHA

        invalid_payloads = (
            transaction_stdout(attempt_id="x" * 32),
            transaction_stdout(snapshot="f" * 63),
            transaction_stdout(stage="unsafe/stage"),
            transaction_stdout(prior_kind="v2", prior_release_sha="none"),
            transaction_stdout(extra_line="raw_payload=provider-secret"),
            transaction_stdout() + f"release_sha={SHA}\n",
        )
        for payload in invalid_payloads:
            deploy._ssh = lambda _command, value=payload: subprocess.CompletedProcess(
                ["ssh"], 0, value, "provider detail must not escape"
            )
            expect_runtime(
                "transaction_status_receipt_invalid",
                lambda: deploy._remote_transaction_status(SHA),
            )

        # A contended/busy shared-lock probe returns no evidence and cannot
        # become permission to invoke the recovery mutation.
        deploy._ssh = lambda _command: subprocess.CompletedProcess(
            ["ssh"], 75, "", "rollout lock owner detail"
        )
        expect_runtime(
            "transaction_status_unavailable_or_unsafe",
            lambda: deploy._remote_transaction_status(SHA),
        )
    finally:
        deploy._ssh = original_ssh

    base_evidence = {
        "release_sha": SHA,
        "attempt_id": ATTEMPT_ID,
        "snapshot_sha256": snapshot_sha256,
        "stage": "nginx_guarded",
        "stage_age_seconds": 901,
        "minimum_recovery_age_seconds": 900,
        "stale_recovery_eligible": True,
        "prior_kind": "absent",
        "prior_release_sha": None,
        "mutation_authority": "fenced_to_exact_attempt",
        "raw_remote_payload_exposed": False,
    }

    def source_result() -> Any:
        return deploy.SourceGateResult(
            status="passed",
            enforced=True,
            fetched_origin_main=True,
            exact_repository=True,
            clean=True,
            head_matches_origin_main=True,
            head_sha=SHA,
            origin_main_sha=SHA,
            branch="main",
            blockers=[],
            warnings=[],
        )

    recovery_args = SimpleNamespace(
        release_sha=SHA,
        attempt_id=ATTEMPT_ID,
        snapshot_sha256=snapshot_sha256,
        expected_stage="nginx_guarded",
        dry_run=True,
        live=False,
    )
    evidence_holder = {"value": dict(base_evidence), "error": None}
    source_calls: list[dict[str, Any]] = []
    target_calls: list[str] = []
    recovery_calls: list[tuple[str, str, dict[str, Any]]] = []
    payloads: list[dict[str, Any]] = []

    def remote_status(_release_sha: str) -> dict[str, Any]:
        error = evidence_holder["error"]
        if error is not None:
            raise RuntimeError(str(error))
        return dict(evidence_holder["value"])

    originals = {
        "_source_gate": deploy._source_gate,
        "_local_ssh_target_gate": deploy._local_ssh_target_gate,
        "_remote_transaction_status": deploy._remote_transaction_status,
        "_recover_failed_projection_rollout": deploy._recover_failed_projection_rollout,
        "_print_json": deploy._print_json,
    }
    try:
        deploy._source_gate = lambda **kwargs: source_calls.append(kwargs) or source_result()
        deploy._local_ssh_target_gate = lambda: target_calls.append("target") or {
            "status": "passed",
            "blockers": [],
        }
        deploy._remote_transaction_status = remote_status
        deploy._recover_failed_projection_rollout = (
            lambda release_sha, attempt_id, **kwargs: recovery_calls.append(
                (release_sha, attempt_id, kwargs)
            )
            or "quarantined"
        )
        deploy._print_json = lambda payload: payloads.append(payload)

        assert deploy._handle_transaction_status(SimpleNamespace(release_sha=SHA)) == 0
        assert payloads[-1] == {
            "status": "transaction_verified",
            "evidence": base_evidence,
        }

        for field, mismatch in (
            ("attempt_id", "2" * 32),
            ("snapshot_sha256", "e" * 64),
            ("stage", "service_ready"),
        ):
            payloads.clear()
            recovery_calls.clear()
            evidence_holder["value"] = dict(base_evidence) | {field: mismatch}
            assert deploy._handle_transaction_recover(recovery_args) == 1
            assert payloads[-1]["blockers"] == [
                "transaction_recovery_evidence_mismatch"
            ]
            assert not recovery_calls

        payloads.clear()
        evidence_holder["value"] = dict(base_evidence) | {
            "stage_age_seconds": 899,
            "stale_recovery_eligible": False,
        }
        assert deploy._handle_transaction_recover(recovery_args) == 1
        assert payloads[-1]["blockers"] == ["transaction_not_stale_for_recovery"]
        assert not recovery_calls

        payloads.clear()
        evidence_holder["value"] = dict(base_evidence)
        assert deploy._handle_transaction_recover(recovery_args) == 0
        assert payloads[-1]["status"] == "dry_run_passed"
        assert payloads[-1]["live_executed"] is False
        assert not recovery_calls

        payloads.clear()
        source_calls.clear()
        target_calls.clear()
        live_args = SimpleNamespace(**vars(recovery_args))
        live_args.dry_run = False
        live_args.live = True
        assert deploy._handle_transaction_recover(live_args) == 0
        assert source_calls == [
            {"enforced": True, "fetch_origin": True},
            {"enforced": True, "fetch_origin": True},
        ]
        assert target_calls == ["target", "target"]
        assert recovery_calls == [
            (
                SHA,
                ATTEMPT_ID,
                {
                    "expected_snapshot_sha256": snapshot_sha256,
                    "expected_stage": "nginx_guarded",
                    "minimum_stage_age_seconds": 900,
                },
            )
        ]
        assert payloads[-1]["status"] == "transaction_recovered_fail_safe"
        assert payloads[-1]["live_executed"] is True
        assert payloads[-1]["outcome"] == "quarantined"
        assert payloads[-1]["prior_evidence"] == base_evidence

        payloads.clear()
        recovery_calls.clear()
        evidence_holder["error"] = "transaction_status_unavailable_or_unsafe"
        assert deploy._handle_transaction_recover(recovery_args) == 1
        assert payloads[-1]["blockers"] == [
            "transaction_status_unavailable_or_unsafe"
        ]
        assert not recovery_calls
    finally:
        for name, value in originals.items():
            setattr(deploy, name, value)

    guarded_recovery = deploy._remote_failed_rollout_recovery_script(
        SHA,
        ATTEMPT_ID,
        expected_snapshot_sha256=snapshot_sha256,
        expected_stage="nginx_guarded",
        minimum_stage_age_seconds=900,
    )
    assert "flock -w 300 -x 9" in guarded_recovery
    assert f"snapshot_sha256={snapshot_sha256}" in guarded_recovery
    assert f"attempt_id={ATTEMPT_ID}" in guarded_recovery
    assert "stage=nginx_guarded" in guarded_recovery
    assert 'test "$((now - activity_mtime))" -ge \'900\'' in guarded_recovery


def _assert_probe_sanitization(deploy: Any) -> None:
    assert deploy._classify_curl_transport(0) == "ok"
    assert deploy._classify_curl_transport(60) == "tls_error"
    assert deploy._classify_curl_transport(7) == "network_error"
    original_run = deploy.subprocess.run
    captured: list[tuple[list[str], dict[str, str]]] = []
    try:
        def fake_run(*args: Any, **kwargs: Any) -> Any:
            captured.append((list(args[0]), dict(kwargs.get("env") or {})))
            return subprocess.CompletedProcess(
                args[0], 60, b"000", b"certificate path and provider payload"
            )

        deploy.subprocess.run = fake_run
        result = deploy._curl_probe("https://devcontrol.pro")
    finally:
        deploy.subprocess.run = original_run
    assert result.transport == "tls_error" and result.http_status == 0
    serialized = json.dumps(deploy.asdict(result), sort_keys=True)
    assert "certificate path" not in serialized and "provider payload" not in serialized
    command, environment = captured[0]
    assert command[:2] == ["/usr/bin/curl", "-q"]
    assert environment == {"HOME": str(ROOT), "PATH": "/usr/bin:/bin", "LC_ALL": "C"}
    assert not any("proxy" in key.lower() for key in environment)
    assert deploy._approved_probe_url("https://devcontrol.pro/runs/live", {"devcontrol.pro"})
    assert not deploy._approved_probe_url("http://devcontrol.pro", {"devcontrol.pro"})
    assert not deploy._approved_probe_url("https://user:pass@devcontrol.pro", {"devcontrol.pro"})
    assert not deploy._approved_probe_url("https://example.com", {"devcontrol.pro"})


def _assert_signed_ingest_key_probe(deploy: Any) -> None:
    original_run = deploy.subprocess.run
    captured: list[tuple[list[str], dict[str, str], str, int]] = []
    try:
        def fake_run(command: list[str], **kwargs: Any) -> Any:
            config_path = Path(command[-1])
            captured.append(
                (
                    list(command),
                    dict(kwargs.get("env") or {}),
                    config_path.read_text(encoding="utf-8"),
                    config_path.stat().st_mode & 0o777,
                )
            )
            return subprocess.CompletedProcess(command, 0, b"422", b"provider detail")

        deploy.subprocess.run = fake_run
        result = deploy._signed_ingest_key_probe(KEY_MATERIAL)
    finally:
        deploy.subprocess.run = original_run
    assert result.http_status == 422 and result.transport == "ok" and result.status == "passed"
    assert len(captured) == 1
    command, environment, config, mode = captured[0]
    assert command[:3] == ["/usr/bin/curl", "-q", "--config"]
    assert len(command) == 4
    assert mode == 0o600
    assert environment["PATH"] == "/usr/bin:/bin" and "HOME" in environment
    assert not any("proxy" in key.lower() for key in environment)
    assert "https://devcontrol.pro/api/v2/ingest" in config
    assert "X-DCP-Signature: sha256=" in config
    assert "X-DCP-Supervisor-ID: hosted-rollout-key-canary" in config
    assert KEY_MATERIAL.decode() not in config
    assert "sha256=" not in " ".join(command)


def _assert_read_only_proof_matrix(deploy: Any) -> None:
    original_health = deploy._remote_loopback_health
    original_probe = deploy._curl_probe
    original_signed_probe = deploy._signed_ingest_key_probe
    statuses = {
        "/": 401,
        "/runs/live": 401,
        "/api/v2/state": 401,
        "/api/v2/ingest": 401,
        "/mcp": 401,
        "/oauth/token": 401,
        "/.well-known/acme-challenge/dcp-v2-route-proof-not-present": 404,
        "api.selleros.pro": 200,
    }

    def fake_probe(url: str, **_: Any) -> Any:
        key = "api.selleros.pro" if "api.selleros.pro" in url else urlsplit_path(url)
        return deploy.CurlProbeResult("passed", statuses[key], "ok", 0)

    try:
        deploy._remote_loopback_health = lambda: {
            "service_role": "hosted_projection_v2",
            "control_authority": False,
            "mutation_routes_enabled": False,
            "projection_ingestion_enabled": True,
            "release_sha": SHA,
        }
        deploy._curl_probe = fake_probe
        proof = deploy._prove_live_read_only(expected_release=SHA)
        assert proof["single_control_authority"] is True
        assert proof["legacy_mutation_routes_public"] is False
        assert proof["public_routes"]["unsigned_ingest"]["http_status"] == 401

        deploy._signed_ingest_key_probe = lambda key: deploy.CurlProbeResult(
            "passed", 422, "ok", 0
        )
        signed_proof = deploy._prove_live_read_only(
            expected_release=SHA,
            projection_key=KEY_MATERIAL,
        )
        assert signed_proof["public_routes"]["signed_ingest_key"]["http_status"] == 422

        statuses["/mcp"] = 200
        try:
            deploy._prove_live_read_only(expected_release=SHA)
        except RuntimeError as exc:
            assert "legacy_mcp_denied" in str(exc)
        else:
            raise AssertionError("public legacy MCP route was accepted")
    finally:
        deploy._remote_loopback_health = original_health
        deploy._curl_probe = original_probe
        deploy._signed_ingest_key_probe = original_signed_probe


def _assert_blocked_preflight_never_mutates(deploy: Any) -> None:
    calls: list[str] = []
    original_validate = deploy._validate_safety
    original_deploy = deploy._deploy_live
    certificate = deploy._unknown_certificate_gate()
    source = deploy.SourceGateResult(
        status="blocked",
        enforced=True,
        fetched_origin_main=True,
        exact_repository=True,
        clean=False,
        head_matches_origin_main=True,
        head_sha=SHA,
        origin_main_sha=SHA,
        branch="main",
        blockers=["source_worktree_not_clean"],
        warnings=[],
    )
    key = deploy.ProjectionKeyGateResult(
        status="ready",
        required=True,
        source="explicit",
        regular_file=True,
        symlink=False,
        owner_matches_process=True,
        mode="0600",
        size_bytes=48,
        blockers=[],
        warnings=[],
    )
    blocked = deploy.ValidationResult(
        status="blocked",
        blockers=["source_worktree_not_clean"],
        warnings=[],
        source=source,
        projection_key=key,
        certificate=certificate,
        dns={},
        cert_domains=list(DOMAINS),
        remote={},
    )

    class Args:
        dry_run = False
        live = True
        offline = False
        projection_key_file = None

    try:
        deploy._validate_safety = lambda **kwargs: blocked
        deploy._deploy_live = lambda **kwargs: calls.append("deploy_live")
        output = io.StringIO()
        with redirect_stdout(output):
            rc = deploy._handle_deploy(Args())
    finally:
        deploy._validate_safety = original_validate
        deploy._deploy_live = original_deploy
    assert rc == 1 and not calls
    payload = json.loads(output.getvalue())
    assert payload["status"] == "blocked"


def _assert_online_dry_run_enforces_gates(deploy: Any) -> None:
    calls: list[dict[str, Any]] = []
    original_validate = deploy._validate_safety
    source = deploy.SourceGateResult(
        status="blocked",
        enforced=True,
        fetched_origin_main=True,
        exact_repository=True,
        clean=False,
        head_matches_origin_main=True,
        head_sha=SHA,
        origin_main_sha=SHA,
        branch="main",
        blockers=["source_worktree_not_clean"],
        warnings=[],
    )
    key = deploy.ProjectionKeyGateResult(
        status="blocked",
        required=True,
        source="default",
        regular_file=False,
        symlink=False,
        owner_matches_process=False,
        mode=None,
        size_bytes=None,
        blockers=["projection_key_unavailable"],
        warnings=[],
    )
    blocked = deploy.ValidationResult(
        status="blocked",
        blockers=["source_worktree_not_clean", "projection_key_unavailable"],
        warnings=[],
        source=source,
        projection_key=key,
        certificate=deploy._unknown_certificate_gate(),
        dns={},
        cert_domains=list(DOMAINS),
        remote={},
    )

    class Args:
        dry_run = True
        live = False
        offline = False
        projection_key_file = None

    try:
        def fake_validate(**kwargs: Any) -> Any:
            calls.append(kwargs)
            return blocked

        deploy._validate_safety = fake_validate
        output = io.StringIO()
        with redirect_stdout(output):
            rc = deploy._handle_deploy(Args())
    finally:
        deploy._validate_safety = original_validate
    assert rc == 1
    assert calls == [
        {
            "offline": False,
            "enforce_source": True,
            "require_key": True,
            "projection_key_file": None,
        }
    ]
    assert json.loads(output.getvalue())["status"] == "dry_run_blocked"


def _run(*args: str) -> dict[str, Any]:
    completed = subprocess.run(
        [sys.executable, str(RUNNER), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise AssertionError(
            f"deploy runner {' '.join(args)} failed\nstdout={completed.stdout}\nstderr={completed.stderr}"
        )
    payload = json.loads(completed.stdout)
    assert isinstance(payload, dict)
    return payload


def _load_deploy_module() -> Any:
    spec = importlib.util.spec_from_file_location("dev_control_plane_hosted_deploy", RUNNER)
    if spec is None or spec.loader is None:
        raise AssertionError("cannot load deploy runner module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[str(spec.name)] = module
    spec.loader.exec_module(module)
    return module


def _local_dns(ip: str) -> dict[str, Any]:
    return {domain: {"system": [ip], "default_dig": [ip]} for domain in DOMAINS}


def _doh_dns(ip: str) -> dict[str, Any]:
    return {domain: {"cloudflare": [ip], "google": [ip]} for domain in DOMAINS}


def _remote_dns(ip: str) -> dict[str, Any]:
    return {
        "returncode": 0,
        "domains": {domain: {"getent_ahostsv4": [ip], "dig": [ip]} for domain in DOMAINS},
    }


def urlsplit_path(url: str) -> str:
    from urllib.parse import urlsplit

    return urlsplit(url).path or "/"


if __name__ == "__main__":
    main()
