#!/usr/bin/env python3
"""Deterministic source, dependency, artifact, network and namespace audit."""

from __future__ import annotations

import argparse
import ast
import hashlib
from pathlib import Path
import re
import sys
import tempfile
import tomllib
import zipfile

if __package__:
    from scripts.build_artifact import SOURCE_ROOT, build
else:  # direct repo-owned invocation: python3 scripts/safety_audit.py
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from scripts.build_artifact import SOURCE_ROOT, build


EXPECTED_APACHE_SHA256 = "1a2219722b7ef58364065e9073a2cb2831891eb147a785742a31431c9cddad1d"
FORBIDDEN_RUNTIME_BYTES = (
    b"electron-updater",
    b"app-update.yml",
    b"us.i.posthog.com",
    b"eu.i.posthog.com",
    b"sentry.io",
    b"phc_",
    b"dev.agent-orchestrator.desktop",
    b"AgentWrapper/agent-orchestrator",
    b"~/.ao",
    b"AO_TELEMETRY",
)
ALLOWED_STDLIB_IMPORTS = {
    "__future__",
    "argparse",
    "ast",
    "dataclasses",
    "datetime",
    "fcntl",
    "hashlib",
    "http",
    "importlib",
    "io",
    "json",
    "os",
    "pathlib",
    "re",
    "secrets",
    "shutil",
    "signal",
    "stat",
    "subprocess",
    "sys",
    "tempfile",
    "threading",
    "time",
    "tomllib",
    "typing",
    "urllib",
    "uuid",
    "webbrowser",
    "zipfile",
}


def fail(message: str) -> None:
    raise AssertionError(message)


def runtime_files() -> list[Path]:
    roots = [SOURCE_ROOT / "dcp_orchestrator", SOURCE_ROOT / "bin"]
    files: list[Path] = []
    for root in roots:
        files.extend(path for path in root.rglob("*") if path.is_file() and "__pycache__" not in path.parts)
    files.append(SOURCE_ROOT / "scripts" / "build_artifact.py")
    return sorted(files)


def audit_source() -> None:
    for path in runtime_files():
        payload = path.read_bytes()
        for token in FORBIDDEN_RUNTIME_BYTES:
            if token.lower() in payload.lower():
                fail(f"forbidden packaged surface {token!r} in {path.relative_to(SOURCE_ROOT)}")
        for match in re.findall(rb"https?://[^\s\"'<>]+", payload):
            if not match.startswith(b"http://127.0.0.1:"):
                fail(f"external endpoint in runtime source: {match!r}")


def audit_dependencies() -> None:
    project = tomllib.loads((SOURCE_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    if project["project"].get("dependencies") != []:
        fail("runtime dependency list is not empty")
    for path in sorted((SOURCE_ROOT / "dcp_orchestrator").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module.split(".")[0]]
            else:
                continue
            for name in names:
                if name != "dcp_orchestrator" and name not in ALLOWED_STDLIB_IMPORTS:
                    fail(f"non-stdlib import {name!r} in {path.relative_to(SOURCE_ROOT)}")


def audit_license() -> None:
    license_path = SOURCE_ROOT / "third_party" / "agent-orchestrator" / "LICENSE"
    digest = hashlib.sha256(license_path.read_bytes()).hexdigest()
    if digest != EXPECTED_APACHE_SHA256:
        fail(f"pinned Apache license digest changed: {digest}")
    provenance = (SOURCE_ROOT / "third_party" / "agent-orchestrator" / "PROVENANCE.md").read_text()
    if "f17013b53a1752e86c66e87b45aaa4a463fdff62" not in provenance:
        fail("pinned upstream revision missing from provenance")
    if "no tracked NOTICE" not in provenance:
        fail("upstream NOTICE result missing from provenance")


def audit_artifact() -> None:
    with tempfile.TemporaryDirectory(prefix="dcp-artifact-audit-") as directory:
        first = build(Path(directory) / "first.pyz")
        second = build(Path(directory) / "second.pyz")
        if first.read_bytes() != second.read_bytes():
            fail("artifact build is not deterministic")
        with zipfile.ZipFile(first) as archive:
            names = set(archive.namelist())
            required = {
                "__main__.py",
                "NOTICE",
                "licenses/agent-orchestrator-APACHE-2.0.txt",
                "licenses/agent-orchestrator-PROVENANCE.md",
            }
            if not required.issubset(names):
                fail(f"artifact missing required entries: {sorted(required - names)}")
            if any(name.startswith(("tests/", "docs/", "archive/")) for name in names):
                fail("artifact contains non-runtime repository surface")
            for name in names:
                if name.startswith("licenses/") or name == "NOTICE":
                    continue
                payload = archive.read(name)
                for token in FORBIDDEN_RUNTIME_BYTES:
                    if token.lower() in payload.lower():
                        fail(f"forbidden packaged surface {token!r} in artifact entry {name}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    checks = [audit_source, audit_dependencies, audit_license, audit_artifact]
    for check in checks:
        check()
        print(f"PASS {check.__name__}")
    print("PASS network_surface: runtime contains only an explicit loopback endpoint")
    print("PASS namespace_surface: upstream identities are absent from runtime and artifact")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
