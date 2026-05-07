"""Smoke-check OAuth-gated read-only MCP target docs tools."""

from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from tempfile import TemporaryDirectory
from typing import Any, Mapping
from urllib import request as urllib_request

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "apps" / "dev_control_plane_server.py"
TOKEN = "target-docs-mcp-smoke-token-0123456789abcdef"


def main() -> None:
    port = _free_port()
    with TemporaryDirectory(prefix="dev-control-plane-target-docs-mcp-") as tmp_raw:
        tmp = Path(tmp_raw)
        source_repo = tmp / "source"
        bare_repo = tmp / "source.git"
        target_config_dir = tmp / "target-configs"
        state_dir = tmp / "state"
        _create_source_repo(source_repo)
        _git_checked(tmp, "clone", "--bare", str(source_repo), str(bare_repo))
        target_config_dir.mkdir(parents=True)
        _write_json(target_config_dir / "wb_core.json", _remote_config(f"file://{bare_repo}", tmp / "missing-wb-core"))

        process = subprocess.Popen(
            [
                sys.executable,
                str(SERVER),
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--state-dir",
                str(state_dir),
                "--target-config-dir",
                str(target_config_dir),
            ],
            cwd=ROOT,
            env=_server_env(tmp),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            base_url = f"http://127.0.0.1:{port}"
            _wait_ready(base_url)

            target_doc_tools = {"list_target_docs", "search_target_docs", "get_target_doc", "read_target_docs"}
            public_tools = _mcp(base_url, "tools/list", {})
            public_names = {tool.get("name") for tool in public_tools.get("tools", [])}
            if public_names & target_doc_tools:
                raise AssertionError(f"public discovery must hide target docs tools: {public_names & target_doc_tools}")
            denied = _tool(base_url, "list_target_docs", {"target_id": "wb-core"})
            if denied.get("status") != "denied":
                raise AssertionError(f"no-auth direct target docs call must be denied: {denied}")
            denied_fallback = _tool(base_url, "read_target_docs", {"action": "list", "target_id": "wb-core"})
            if denied_fallback.get("status") != "denied":
                raise AssertionError(f"no-auth direct fallback target docs call must be denied: {denied_fallback}")

            authed_tools = _mcp(base_url, "tools/list", {}, token=TOKEN)
            defs = authed_tools.get("tools", [])
            authed_names = {tool.get("name") for tool in defs}
            if not target_doc_tools.issubset(authed_names):
                raise AssertionError(f"authenticated discovery must expose target docs tools: {authed_names}")
            authed_status = _tool(base_url, "get_status", {}, token=TOKEN)
            claimed = set((authed_status.get("mcp") or {}).get("authenticated_read_tools") or [])
            if not claimed <= authed_names:
                raise AssertionError(f"get_status/tools-list split-brain: status={claimed} tools_list={authed_names}")
            registry = (authed_status.get("mcp") or {}).get("tool_registry") or {}
            exported = set(registry.get("exported_tool_names") or [])
            if not target_doc_tools <= exported or not target_doc_tools <= authed_names:
                raise AssertionError(f"target docs tools must be exported through registry and tools/list: {registry} {authed_names}")
            if registry.get("registry_definition_parity") is not True:
                raise AssertionError(f"registry/definition parity must hold: {registry}")
            for tool in defs:
                if tool.get("name") not in target_doc_tools:
                    continue
                annotations = tool.get("annotations") or {}
                schemes = tool.get("securitySchemes") or (tool.get("_meta") or {}).get("securitySchemes") or []
                if annotations.get("readOnlyHint") is not True or annotations.get("destructiveHint") is not False:
                    raise AssertionError(f"target docs tool must be read-only/non-destructive: {tool}")
                if {"type": "oauth2", "scopes": ["dcp.write"]} not in schemes:
                    raise AssertionError(f"target docs tool must require authenticated MCP session: {tool}")

            listed = _tool(base_url, "list_target_docs", {"target_id": "wb-core"}, token=TOKEN)
            paths = {item.get("path") for item in listed.get("docs", [])}
            expected = {
                "README.md",
                "AGENTS.md",
                "docs/modules/00_INDEX__MODULES.md",
                "docs/architecture/01_target_architecture.md",
                "migration/001_context.md",
            }
            if not expected.issubset(paths):
                raise AssertionError(f"list_target_docs missing allowlisted docs: {listed}")
            forbidden = {"runtime/secret.md", "wb_core_docs_master/00_INDEX.md", "infra/deploy.md"}
            if paths & forbidden:
                raise AssertionError(f"list_target_docs exposed forbidden paths: {paths & forbidden}")
            ref = listed.get("ref") or {}
            if not ref.get("commit") or ref.get("branch") != "main":
                raise AssertionError(f"list_target_docs must return source ref: {listed}")
            fallback_list = _tool(base_url, "read_target_docs", {"action": "list", "target_id": "wb-core"}, token=TOKEN)
            fallback_paths = {item.get("path") for item in fallback_list.get("docs", [])}
            if not expected.issubset(fallback_paths):
                raise AssertionError(f"read_target_docs list fallback missing docs: {fallback_list}")

            search = _tool(
                base_url,
                "search_target_docs",
                {"target_id": "wb-core", "query": "gravity", "max_results": 5, "path_prefix": "docs/modules"},
                token=TOKEN,
            )
            if search.get("status") != "ok" or not search.get("results"):
                raise AssertionError(f"search_target_docs must find allowlisted docs text: {search}")
            first = search["results"][0]
            if not first.get("path") or not first.get("line_start") or "gravity" not in first.get("text", "").lower():
                raise AssertionError(f"search result must include path/line/snippet: {search}")
            fallback_search = _tool(
                base_url,
                "read_target_docs",
                {"action": "search", "target_id": "wb-core", "query": "gravity", "max_results": 5},
                token=TOKEN,
            )
            if fallback_search.get("status") != "ok" or not fallback_search.get("results"):
                raise AssertionError(f"read_target_docs search fallback must work: {fallback_search}")

            readme = _tool(base_url, "get_target_doc", {"target_id": "wb-core", "path": "README.md"}, token=TOKEN)
            if "# Fixture wb-core" not in readme.get("content", ""):
                raise AssertionError(f"get_target_doc must read README.md: {readme}")
            fallback_readme = _tool(
                base_url,
                "read_target_docs",
                {"action": "get", "target_id": "wb-core", "path": "README.md"},
                token=TOKEN,
            )
            if "# Fixture wb-core" not in fallback_readme.get("content", ""):
                raise AssertionError(f"read_target_docs get fallback must read README.md: {fallback_readme}")
            module_doc = _tool(
                base_url,
                "get_target_doc",
                {"target_id": "wb-core", "path": "docs/modules/00_INDEX__MODULES.md", "line_start": 1, "line_end": 3},
                token=TOKEN,
            )
            if module_doc.get("line_start") != 1 or module_doc.get("line_end") != 3 or "gravity" not in module_doc.get("content", "").lower():
                raise AssertionError(f"get_target_doc must honor line ranges: {module_doc}")
            arch_doc = _tool(
                base_url,
                "get_target_doc",
                {"target_id": "wb-core", "path": "docs/architecture/01_target_architecture.md"},
                token=TOKEN,
            )
            if "Target Architecture" not in arch_doc.get("content", ""):
                raise AssertionError(f"get_target_doc must read architecture docs: {arch_doc}")

            secret_doc = _tool(
                base_url,
                "get_target_doc",
                {"target_id": "wb-core", "path": "docs/modules/secretish.md"},
                token=TOKEN,
            )
            if "Bearer" in secret_doc.get("content", "") or "redacted" not in secret_doc.get("content", ""):
                raise AssertionError(f"target docs output must redact bearer-like text: {secret_doc}")
            too_large = _tool(
                base_url,
                "get_target_doc",
                {"target_id": "wb-core", "path": "docs/modules/large.md", "max_bytes": 1000},
                token=TOKEN,
            )
            if too_large.get("truncated") is not True or len(too_large.get("content", "")) > 1200:
                raise AssertionError(f"large target docs reads must be size-limited: {too_large}")

            forbidden_doc = _tool(base_url, "get_target_doc", {"target_id": "wb-core", "path": "runtime/secret.md"}, token=TOKEN)
            if forbidden_doc.get("status") != "failed" or "allowed documentation boundary" not in str(forbidden_doc.get("blocker")):
                raise AssertionError(f"forbidden target docs path must be rejected: {forbidden_doc}")
            traversal = _tool(base_url, "get_target_doc", {"target_id": "wb-core", "path": "../README.md"}, token=TOKEN)
            if traversal.get("status") != "failed" or "traversal" not in str(traversal.get("blocker")):
                raise AssertionError(f"path traversal must be rejected: {traversal}")

            status = _tool(base_url, "get_status", {})
            readiness = status.get("target_docs_readiness") or {}
            if readiness.get("status") not in {"ok", "blocked"} or "list_target_docs" not in readiness.get("tools", []):
                raise AssertionError(f"get_status must include target docs diagnostics: {status}")
            state_text = "\n".join(path.read_text(encoding="utf-8", errors="replace") for path in state_dir.rglob("*") if path.is_file() and path.name.endswith((".json", ".jsonl", ".log", ".md", ".txt")))
            if TOKEN in state_text or "Authorization:" + " Bearer" in state_text:
                raise AssertionError("MCP auth token or Authorization header leaked into state logs/artifacts")
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

    print("dev-control-plane-target-docs-mcp-smoke passed")


def _create_source_repo(repo: Path) -> None:
    (repo / "docs" / "architecture").mkdir(parents=True)
    (repo / "docs" / "modules").mkdir(parents=True)
    (repo / "migration").mkdir(parents=True)
    (repo / "runtime").mkdir(parents=True)
    (repo / "wb_core_docs_master").mkdir(parents=True)
    (repo / "infra").mkdir(parents=True)
    (repo / "README.md").write_text("# Fixture wb-core\n\nCurrent WebCore context.\n", encoding="utf-8")
    (repo / "AGENTS.md").write_text("# Agents\n\nRead-only fixture instructions.\n", encoding="utf-8")
    (repo / "docs" / "architecture" / "01_target_architecture.md").write_text(
        "# Target Architecture\n\nThe hosted adapter reads this at a pinned commit.\n",
        encoding="utf-8",
    )
    (repo / "docs" / "modules" / "00_INDEX__MODULES.md").write_text(
        "# Modules\n\nThe gravity module line is searchable.\nSecond line of module context.\n",
        encoding="utf-8",
    )
    bearer = "Authorization: Bearer " + ("A" * 32)
    (repo / "docs" / "modules" / "secretish.md").write_text(
        "# Sanitized\n\n" + bearer + "\n",
        encoding="utf-8",
    )
    (repo / "docs" / "modules" / "large.md").write_text("# Large\n\n" + ("x" * 5000) + "\n", encoding="utf-8")
    (repo / "migration" / "001_context.md").write_text("# Migration Context\n\nRead-only migration context.\n", encoding="utf-8")
    (repo / "runtime" / "secret.md").write_text("# Runtime secret must not be exposed\n", encoding="utf-8")
    (repo / "wb_core_docs_master" / "00_INDEX.md").write_text("# Derived pack must not be exposed\n", encoding="utf-8")
    (repo / "infra" / "deploy.md").write_text("# Infra must not be exposed\n", encoding="utf-8")
    _git_checked(repo, "init", "-b", "main")
    _git_checked(repo, "config", "user.email", "dev-control-plane@example.invalid")
    _git_checked(repo, "config", "user.name", "Development Control Plane Smoke")
    _git_checked(repo, "add", ".")
    _git_checked(repo, "commit", "-m", "Initialize target docs fixture")


def _remote_config(repo_url: str, missing_local_path: Path) -> dict[str, Any]:
    return {
        "project_id": "wb-core",
        "display_name": "wb-core",
        "repo_path": str(missing_local_path),
        "source_mode": "remote_managed_clone",
        "repo_url": repo_url,
        "branch": "main",
        "source_of_truth_paths": ["README.md", "docs/architecture/", "docs/modules/", "migration/"],
        "derived_secondary_paths": ["wb_core_docs_master/"],
        "default_forbidden_paths": [
            "wb_core_docs_master/**",
            "99_MANIFEST__DOCSET_VERSION.md",
            "runtime/**",
            "deploy/**",
            "infra/**",
            "artifacts/**",
        ],
        "default_forbidden_actions": ["live_deploy", "ssh", "root_shell", "public_route_change"],
        "default_required_smokes": ["git diff --check"],
        "codex_prompt_contract": {
            "required_headers": ["Класс задачи:", "Причина классификации:", "Режим выполнения:"],
            "final_blocks": ["=== ДЛЯ КУРАТОРА ===", "=== СЖАТАЯ ПРОВЕРКА ==="],
        },
        "control_plane_notes": ["target docs smoke"],
        "product_plane_notes": ["target production remains untouched"],
        "target_readonly_by_default": True,
        "execution_policy": {
            "default_mode": "fake",
            "allow_managed_clone_execution": True,
            "allow_direct_target_mutation": False,
            "allow_live_deploy": False,
            "allow_auto_merge": False,
            "require_explicit_real_codex_flag": True,
        },
    }


def _mcp(base_url: str, method: str, params: Mapping[str, Any], *, token: str | None = None) -> dict[str, Any]:
    body = json.dumps({"jsonrpc": "2.0", "id": f"smoke-{time.time_ns()}", "method": method, "params": params}).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib_request.Request(base_url + "/mcp", data=body, method="POST", headers=headers)
    with urllib_request.urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if "error" in payload:
        raise AssertionError(f"MCP error for {method}: {payload}")
    return payload.get("result") or {}


def _tool(base_url: str, name: str, arguments: Mapping[str, Any], *, token: str | None = None) -> dict[str, Any]:
    result = _mcp(base_url, "tools/call", {"name": name, "arguments": dict(arguments)}, token=token)
    structured = result.get("structuredContent")
    if isinstance(structured, dict):
        return structured
    content = result.get("content", [])
    if content and isinstance(content[0], dict):
        return json.loads(content[0].get("text") or "{}")
    return {}


def _wait_ready(base_url: str) -> None:
    deadline = time.time() + 10
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib_request.urlopen(base_url + "/api/state", timeout=2) as response:
                json.loads(response.read().decode("utf-8"))
            return
        except Exception as exc:
            last_error = exc
            time.sleep(0.1)
    raise AssertionError(f"server did not become ready: {last_error}")


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _server_env(tmp: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("OPENAI_API_KEY", None)
    env["DEV_CONTROL_PLANE_SECRET_HOME"] = str(tmp / "secrets")
    env["DEV_CONTROL_PLANE_MCP_TOKEN"] = TOKEN
    env["DEV_CONTROL_PLANE_ENABLE_FAKE_CURATOR"] = "1"
    return env


def _git_checked(cwd: Path, *args: str) -> None:
    completed = subprocess.run(("git", *args), cwd=cwd, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise AssertionError(completed.stderr or completed.stdout or f"git {' '.join(args)} failed")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


if __name__ == "__main__":
    main()
