"""Authoritative fake-first CI suite for Orchestrator Codex v2."""

from __future__ import annotations

import ast
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (SRC, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dev_control_plane.v2_suite_contract import (  # noqa: E402
    AUTHORITATIVE_CHECK_COUNT,
    AUTHORITATIVE_SMOKES,
)

PROJECTION_FORBIDDEN_IMPORTS = {
    "dev_control_plane.server",
    "dev_control_plane.mcp",
    "dev_control_plane.mcp_oauth",
    "dev_control_plane.execution",
    "dev_control_plane.target_production",
    "server",
    "mcp",
    "mcp_oauth",
    "execution",
    "target_production",
}

HIGH_CONFIDENCE_SECRET = re.compile(
    r"(?:github_pat_[A-Za-z0-9_]{20,}|gh[opsu]_[A-Za-z0-9]{24,}|"
    r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{24,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)"
)
SYNTHETIC_SECRET_FIXTURES = {
    "apps/dev_control_plane_github_auth_smoke.py": (
        "github_pat_" + "smoke_secret_token_0123456789abcdef",
    ),
    "apps/dev_control_plane_resume_production_deploy_smoke.py": (
        "github_pat_" + "smoke_secret_token_0123456789abcdef",
    ),
    "apps/dev_control_plane_secrets_smoke.py": (
        "github_pat_" + "smoke_secret_token_0123456789abcdef",
    ),
    "apps/dev_control_plane_target_production_smoke.py": (
        "github_pat_" + "smoke_secret_token_0123456789abcdef",
    ),
}
WORKFLOW_ALLOWLIST = {".github/workflows/orchestrator-v2.yml"}
WORKFLOW_ACTION_ALLOWLIST = {
    "actions/checkout@11d5960a326750d5838078e36cf38b85af677262",
    "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065",
    "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02",
    "actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093",
}
FORBIDDEN_WORKFLOW_TOKENS = (
    "pull_request_target",
    "workflow_run",
    "repository_dispatch",
    "workflow_dispatch",
    "schedule:",
    "permissions: write-all",
    "contents: write",
    "pull-requests: write",
    "checks: write",
    "actions: write",
    "deployments: write",
    "id-token: write",
    "packages: write",
    "issues: write",
    "statuses: write",
    "gh pr merge",
    "git push",
    "deploy --live",
    "rollback --live",
    "sudo systemctl",
    "ssh ",
)


def main() -> None:
    started = time.monotonic()
    _compile()
    static_policy = run_static_policy_checks()
    results: list[dict[str, object]] = []
    for relative in AUTHORITATIVE_SMOKES:
        path = ROOT / relative
        if not path.is_file():
            raise AssertionError(f"authoritative suite member is missing: {relative}")
        before = time.monotonic()
        completed = subprocess.run(
            [sys.executable, str(path)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=180,
        )
        elapsed = round(time.monotonic() - before, 3)
        if completed.returncode != 0:
            raise AssertionError(
                f"suite member failed: {relative}\n"
                f"stdout={completed.stdout[-4000:]}\n"
                f"stderr={completed.stderr[-4000:]}"
            )
        results.append({"path": relative, "status": "passed", "seconds": elapsed})
        print(f"PASS {relative} ({elapsed:.3f}s)", flush=True)
    payload = {
        "schema": "dev-control-plane/v2-suite-evidence/v2",
        "status": "passed",
        "suite": "orchestrator_v2",
        "commit_sha": _git_head(),
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "checks": AUTHORITATIVE_CHECK_COUNT,
        "smokes": results,
        "seconds": round(time.monotonic() - started, 3),
        "real_model_calls": 0,
        "static_policy": static_policy,
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _git_head() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    value = completed.stdout.strip()
    if completed.returncode != 0 or len(value) != 40 or any(char not in "0123456789abcdef" for char in value):
        raise AssertionError("authoritative suite could not bind exact Git commit")
    return value


def _compile() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "compileall", "-q", "src", "apps"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if completed.returncode != 0:
        raise AssertionError(f"compileall failed: {completed.stderr[-4000:]}")


def run_static_policy_checks() -> dict[str, object]:
    """Run repository-owned policy checks and return a sanitized receipt.

    The self-closure job calls this function again after consuming the exact
    head-bound suite evidence.  Keeping the checks deterministic means a PR
    body is never treated as proof of read-only projection, legacy retirement,
    or credential hygiene.
    """

    projection_files = (
        ROOT / "src/dev_control_plane/projection_store.py",
        ROOT / "src/dev_control_plane/projection_server.py",
        ROOT / "apps/dev_control_plane_projection_v2.py",
    )
    for path in projection_files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                imported.add(module)
                imported.update(f"{module}.{alias.name}" for alias in node.names)
        hits = sorted(
            name
            for name in imported
            if any(name == forbidden or name.startswith(forbidden + ".") for forbidden in PROJECTION_FORBIDDEN_IMPORTS)
        )
        if hits:
            raise AssertionError(f"hosted projection imports mutation authority: {path}: {hits}")

    config = json.loads((ROOT / "configs/target_projects/wb_core.json").read_text(encoding="utf-8"))
    if (config.get("operator_parity") or {}).get("enabled") is not False:
        raise AssertionError("wb-core legacy operator_parity must remain disabled")

    _validate_workflow_policy()

    tracked = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout.split(b"\0")
    forbidden_names = {".env", "auth.json", "secrets.json", "projection_hmac.key"}
    for raw in tracked:
        if not raw:
            continue
        relative = raw.decode("utf-8", errors="strict")
        path = Path(relative)
        if path.name in forbidden_names or relative.startswith(".codex/"):
            raise AssertionError(f"forbidden runtime/secret path is tracked: {relative}")
        absolute = ROOT / relative
        if not absolute.is_file() or absolute.stat().st_size > 2_000_000:
            continue
        try:
            source_text = absolute.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        scan_text = source_text
        for synthetic in SYNTHETIC_SECRET_FIXTURES.get(relative, ()):
            if synthetic not in source_text:
                raise AssertionError(
                    f"declared synthetic secret fixture disappeared without updating policy: {relative}"
                )
            scan_text = scan_text.replace(synthetic, "<synthetic-secret-fixture>")
        if HIGH_CONFIDENCE_SECRET.search(scan_text):
            raise AssertionError(f"high-confidence credential pattern found in tracked file: {relative}")

    return {
        "projection_is_read_only": True,
        "legacy_operator_parity_disabled": True,
        "workflow_mutation_authority": "none",
        "secrets_scan": "passed",
        "scanned_file_count": len(tuple(raw for raw in tracked if raw)),
    }


def _validate_workflow_policy() -> None:
    workflow_paths = {
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / ".github" / "workflows").glob("*")
        if path.is_file()
    }
    if workflow_paths != WORKFLOW_ALLOWLIST:
        raise AssertionError(f"workflow allowlist mismatch: {sorted(workflow_paths)}")
    for relative in sorted(workflow_paths):
        source = (ROOT / relative).read_text(encoding="utf-8")
        lowered = source.lower()
        hits = [token for token in FORBIDDEN_WORKFLOW_TOKENS if token in lowered]
        if hits:
            raise AssertionError(f"workflow contains mutation authority: {relative}: {hits}")
        actions = {
            match.group(1)
            for match in re.finditer(r"(?m)^\s*-\s+uses:\s*([^\s#]+)\s*(?:#.*)?$", source)
        }
        unknown_actions = sorted(actions - WORKFLOW_ACTION_ALLOWLIST)
        if unknown_actions:
            raise AssertionError(f"workflow uses an unapproved action: {relative}: {unknown_actions}")
        if len(re.findall(r"(?m)^\s+name:\s*v2-suite\s*$", source)) != 1 or len(
            re.findall(r"(?m)^\s+name:\s*self-closure\s*$", source)
        ) != 1:
            raise AssertionError("workflow must emit exactly one v2-suite and self-closure check")
        if "needs: v2-suite" not in source or source.count("persist-credentials: false") != 2:
            raise AssertionError("workflow lost exact self-closure dependency or credential isolation")


if __name__ == "__main__":
    main()
