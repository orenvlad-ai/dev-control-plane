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
                "policy": [
                    "install only standard OS packages needed by dev-control-plane managed Codex runtime",
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
        r"""
set -eu
python3 - <<'PY'
import json, shutil, subprocess
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
    items.append({"name": tool, "path": path, "version": version})
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
    items.append({"name": "codex", "path": path, "version": codex_version})
else:
    items.append({"name": "codex", "path": None, "version": None})
print(json.dumps({"status": "ok", "tools": items}, ensure_ascii=False, sort_keys=True))
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
    script = rf"""
set -eu
missing=""
for tool in rg; do
  if ! command -v "$tool" >/dev/null 2>&1; then missing="$missing $tool"; fi
done
if [ -z "$missing" ]; then
  echo '{{"status":"ready","changed":false,"message":"required tools already present"}}'
  exit 0
fi
if ! command -v apt-get >/dev/null 2>&1; then
  echo '{{"status":"blocked","reason":"apt-get missing; use runtime-local reviewed package flow"}}'
  exit 2
fi
echo '{{"status":"planned","missing":"'"$missing"'","packages":"ripgrep","live":{str(live).lower()}}}'
if [ "{'1' if live else '0'}" != "1" ]; then
  exit 0
fi
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends {' '.join(REQUIRED_APT_PACKAGES)}
command -v rg
rg --version | head -n 1
"""
    result = _ssh(script, check=False)
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    return result.returncode


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
