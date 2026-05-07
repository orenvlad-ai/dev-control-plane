"""Repo-owned hosted toolchain provisioning runner for dev-control-plane.

The runner is intentionally narrow: it provisions only dev-control-plane
runtime tools and never changes WebCore paths, services or nginx configs.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from typing import Sequence

SSH_ALIAS = "wb-core-eu-root"
EXPECTED_RUNTIME_ROOT = "/opt/dev-control-plane-runtime"
SERVICE_NAME = "dev-control-plane.service"
REQUIRED_APT_PACKAGES = ("ripgrep",)
RUNTIME_TOOL_BIN_DIR = f"{EXPECTED_RUNTIME_ROOT}/tools/bin"
RUNTIME_GH_ROOT = f"{EXPECTED_RUNTIME_ROOT}/tools/gh"
RUNTIME_GH_BIN = f"{RUNTIME_TOOL_BIN_DIR}/gh"
RUNTIME_LOCAL_APT_PACKAGES = ("gh",)
FORBIDDEN_PATHS = (
    "/opt/wb-core-runtime",
    "/opt/wb-ai/.env",
    "/etc/nginx/sites-enabled/wb-ai",
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage hosted dev-control-plane toolchain readiness.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("print-plan")
    subparsers.add_parser("inventory")
    subparsers.add_parser("validate")
    provision = subparsers.add_parser("provision")
    provision.add_argument("--dry-run", action="store_true")
    provision.add_argument("--live", action="store_true")
    args = parser.parse_args(argv)

    if args.command == "print-plan":
        return _print_plan()
    if args.command == "inventory":
        return _inventory()
    if args.command == "validate":
        return _validate()
    if args.command == "provision":
        if args.dry_run == args.live:
            raise SystemExit("choose exactly one of --dry-run or --live")
        return _provision(live=bool(args.live))
    raise SystemExit(f"unknown command: {args.command}")


def _print_plan() -> int:
    print(
        json.dumps(
            {
                "status": "planned",
                "ssh_alias": SSH_ALIAS,
                "runtime_root": EXPECTED_RUNTIME_ROOT,
                "service": SERVICE_NAME,
                "apt_packages": list(REQUIRED_APT_PACKAGES),
                "runtime_tool_bin_dir": RUNTIME_TOOL_BIN_DIR,
                "runtime_local_apt_packages": list(RUNTIME_LOCAL_APT_PACKAGES),
                "policy": [
                    "install only standard OS packages needed by dev-control-plane managed Codex runtime",
                    "keep GitHub CLI runtime-local under /opt/dev-control-plane-runtime/tools/bin when provisioned",
                    "do not request, store or print GitHub credentials from this provisioning command",
                    "do not modify WebCore runtime paths, services or nginx configs",
                    "do not run real Codex tasks from this provisioning command",
                ],
                "forbidden_paths": list(FORBIDDEN_PATHS),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _inventory() -> int:
    result = _ssh(
        rf"""
set -eu
python3 - <<'PY'
import json, os, shutil, subprocess
runtime_bin = "{RUNTIME_TOOL_BIN_DIR}"
os.environ["PATH"] = runtime_bin + os.pathsep + os.environ.get("PATH", "")
tools = ["git", "rg", "python3", "pip", "pip3", "node", "npm", "corepack", "pnpm", "yarn", "jq", "bash", "sh", "sed", "awk", "grep", "find", "xargs", "tar", "gzip", "unzip", "timeout", "rsync", "ssh", "gh"]
items = []
for tool in tools:
    path = shutil.which(tool)
    version = None
    if path:
        cmd = [path, "-V"] if tool == "ssh" else ([path, "-c", "echo sh available"] if tool == "sh" else [path, "--version"])
        try:
            completed = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            text = (completed.stdout or completed.stderr or "").strip()
            version = text.splitlines()[0] if text else None
        except Exception:
            version = None
    items.append({{"name": tool, "path": path, "version": version}})
codex_path = "/opt/dev-control-plane-runtime/tools/codex/bin/codex"
codex_version = None
if shutil.which("codex") or __import__("pathlib").Path(codex_path).exists():
    path = shutil.which("codex") or codex_path
    try:
        completed = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=5)
        text = (completed.stdout or completed.stderr or "").strip()
        codex_version = text.splitlines()[0] if text else None
    except Exception:
        codex_version = None
    items.append({{"name": "codex", "path": path, "version": codex_version}})
else:
    items.append({{"name": "codex", "path": None, "version": None}})
print(json.dumps({{"status": "ok", "tools": items}}, ensure_ascii=False, sort_keys=True))
PY
""",
        check=False,
    )
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    return result.returncode


def _validate() -> int:
    script = rf"""
set -eu
test -d {EXPECTED_RUNTIME_ROOT!r}
test -d {EXPECTED_RUNTIME_ROOT!r}/state
test -d {EXPECTED_RUNTIME_ROOT!r}/tools
systemctl is-enabled {SERVICE_NAME!r} >/dev/null 2>&1 || true
for path in {' '.join(repr(path) for path in FORBIDDEN_PATHS)}; do
  case "$path" in
    /opt/wb-core-runtime*|/opt/wb-ai/.env|/etc/nginx/sites-enabled/wb-ai) : ;;
    *) echo "unexpected forbidden path pattern: $path" >&2; exit 1 ;;
  esac
done
echo "validation_ok"
"""
    result = _ssh(script, check=False)
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    return result.returncode


def _provision(*, live: bool) -> int:
    result = _ssh(remote_provision_script(live=live), check=False)
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    return result.returncode


def remote_provision_script(*, live: bool) -> str:
    """Return the reviewed remote shell script used by deploy/provision runners."""

    return rf"""
set -eu
missing=""
for tool in rg; do
  if ! command -v "$tool" >/dev/null 2>&1; then missing="$missing $tool"; fi
done
gh_ready=0
if [ -x {RUNTIME_GH_BIN!r} ] && {RUNTIME_GH_BIN!r} --version >/dev/null 2>&1; then
  gh_ready=1
elif command -v gh >/dev/null 2>&1 && gh --version >/dev/null 2>&1; then
  mkdir -p {RUNTIME_TOOL_BIN_DIR!r}
  ln -sfn "$(command -v gh)" {RUNTIME_GH_BIN!r}
  gh_ready=1
fi
if [ "$gh_ready" != "1" ]; then
  missing="$missing gh"
fi
if [ -z "$missing" ]; then
  echo '{{"status":"ready","changed":false,"message":"required hosted tools already present"}}'
  exit 0
fi
if ! command -v apt-get >/dev/null 2>&1; then
  echo '{{"status":"blocked","reason":"apt-get missing; cannot provision reviewed hosted toolchain packages"}}'
  exit 2
fi
echo '{{"status":"planned","missing":"'"$missing"'","apt_packages":"ripgrep","runtime_local_apt_packages":"gh","runtime_tool_bin_dir":"{RUNTIME_TOOL_BIN_DIR}","live":{str(live).lower()}}}'
if [ "{'1' if live else '0'}" != "1" ]; then
  exit 0
fi
export DEBIAN_FRONTEND=noninteractive
apt-get update
if ! command -v rg >/dev/null 2>&1; then
  apt-get install -y --no-install-recommends {' '.join(REQUIRED_APT_PACKAGES)}
fi
mkdir -p {RUNTIME_TOOL_BIN_DIR!r} {RUNTIME_GH_ROOT!r}
if [ "$gh_ready" != "1" ]; then
  if ! command -v dpkg-deb >/dev/null 2>&1; then
    echo '{{"status":"blocked","reason":"dpkg-deb missing; cannot extract runtime-local gh package"}}'
    exit 2
  fi
  tmpdir="$(mktemp -d)"
  trap 'rm -rf "$tmpdir"' EXIT
  cd "$tmpdir"
  apt-get download {' '.join(RUNTIME_LOCAL_APT_PACKAGES)}
  deb="$(find "$tmpdir" -maxdepth 1 -type f -name 'gh_*.deb' | head -n 1)"
  if [ -z "$deb" ]; then
    echo '{{"status":"blocked","reason":"gh apt package download did not produce a deb artifact"}}'
    exit 2
  fi
  rm -rf {RUNTIME_GH_ROOT!r}
  mkdir -p {RUNTIME_GH_ROOT!r}
  dpkg-deb -x "$deb" {RUNTIME_GH_ROOT!r}
  if [ ! -x {RUNTIME_GH_ROOT!r}/usr/bin/gh ]; then
    echo '{{"status":"blocked","reason":"gh package did not contain usr/bin/gh"}}'
    exit 2
  fi
  ln -sfn {RUNTIME_GH_ROOT!r}/usr/bin/gh {RUNTIME_GH_BIN!r}
fi
if id -u dev-control-plane >/dev/null 2>&1; then
  chown -R dev-control-plane:dev-control-plane {EXPECTED_RUNTIME_ROOT!r}/tools
fi
chmod 755 {EXPECTED_RUNTIME_ROOT!r}/tools {RUNTIME_TOOL_BIN_DIR!r} {RUNTIME_GH_ROOT!r} 2>/dev/null || true
command -v rg
rg --version | head -n 1
{RUNTIME_GH_BIN!r} --version | head -n 1
echo '{{"status":"ready","changed":true,"message":"hosted toolchain provisioned"}}'
"""


def _ssh(script: str, *, check: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        ("ssh", SSH_ALIAS, script),
        capture_output=True,
        text=True,
        check=False,
    )
    if check and completed.returncode != 0:
        raise SystemExit(completed.stderr or completed.stdout or f"ssh command failed: {completed.returncode}")
    return completed


if __name__ == "__main__":
    raise SystemExit(main())
