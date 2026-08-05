"""Fresh, ephemeral, schema-bound Sol Ultra adviser.

The arbiter is deliberately a bounded `codex exec --ephemeral` job.  It has a
read-only sandbox, receives one immutable case snapshot, returns one validated
decision, and has no registry/GitHub/deploy mutation capability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from .orchestration_contracts import (
    ARBITER_ACTIONS,
    ARBITER_DECISION_SCHEMA,
    REQUIRED_EXECUTOR_MODEL,
    REQUIRED_EXECUTOR_REASONING,
    ArbiterDecision,
    RevisionBinding,
    arbiter_decision_from_mapping,
    contract_to_dict,
)


class ArbiterError(RuntimeError):
    """A bounded arbiter invocation or immutable binding failed."""


@dataclass(frozen=True)
class ArbiterCase:
    kind: str
    case_id: str
    case_digest: str
    bindings: tuple[RevisionBinding, ...]
    snapshot: Mapping[str, Any]
    _snapshot_json: str = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.kind not in {"release_plan", "incident"}:
            raise ValueError("arbiter case kind is invalid")
        if not self.case_id or len(self.case_id) > 128:
            raise ValueError("arbiter case id is invalid")
        if len(self.case_digest) != 64 or any(char not in "0123456789abcdef" for char in self.case_digest):
            raise ValueError("arbiter case digest must be sha256")
        bindings = tuple(self.bindings)
        if not bindings or not all(isinstance(binding, RevisionBinding) for binding in bindings):
            raise ValueError("arbiter case requires immutable bindings")
        if not isinstance(self.snapshot, Mapping):
            raise ValueError("arbiter case snapshot must be an object")
        try:
            encoded = json.dumps(self.snapshot, ensure_ascii=False, sort_keys=True, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("arbiter case snapshot must be JSON serializable") from exc
        if len(encoded) > 512_000:
            raise ValueError("arbiter case snapshot exceeds bounded size")
        decoded = json.loads(encoded)
        object.__setattr__(self, "bindings", bindings)
        object.__setattr__(self, "snapshot", _freeze_json(decoded))
        object.__setattr__(self, "_snapshot_json", encoded)


class FreshSolArbiter:
    def __init__(
        self,
        *,
        codex_bin: str = "codex",
        timeout_seconds: float = 900.0,
        env: Mapping[str, str] | None = None,
    ) -> None:
        if not codex_bin.strip() or timeout_seconds <= 0 or timeout_seconds > 3_600:
            raise ValueError("invalid bounded arbiter configuration")
        self.codex_bin = codex_bin
        self.timeout_seconds = float(timeout_seconds)
        self.env = None if env is None else {str(key): str(value) for key, value in env.items()}

    def decide(self, case: ArbiterCase, *, cwd: Path) -> ArbiterDecision:
        root = cwd.expanduser().resolve()
        if not root.is_dir():
            raise ArbiterError("arbiter working directory is unavailable")
        with tempfile.TemporaryDirectory(prefix="dev-control-plane-arbiter-") as temporary_raw:
            temporary = Path(temporary_raw)
            temporary.chmod(0o700)
            schema_path = temporary / "decision.schema.json"
            output_path = temporary / "decision.json"
            schema_path.write_text(
                json.dumps(arbiter_output_schema(case), ensure_ascii=False, sort_keys=True),
                encoding="utf-8",
            )
            schema_path.chmod(0o600)
            command = [
                self.codex_bin,
                "exec",
                "--ephemeral",
                "--ignore-user-config",
                "--ignore-rules",
                "--strict-config",
                "-c",
                'approval_policy="never"',
                "-c",
                'web_search="disabled"',
                "-c",
                'shell_environment_policy.inherit="none"',
                "--sandbox",
                "read-only",
                "--model",
                REQUIRED_EXECUTOR_MODEL,
                "-c",
                f'model_reasoning_effort="{REQUIRED_EXECUTOR_REASONING}"',
                "--json",
                "--color",
                "never",
                "--cd",
                str(temporary),
                "--skip-git-repo-check",
                "--output-schema",
                str(schema_path),
                "--output-last-message",
                str(output_path),
                "-",
            ]
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=_arbiter_environment(self.env),
                start_new_session=True,
            )
            try:
                stdout, _stderr = process.communicate(_arbiter_prompt(case), timeout=self.timeout_seconds)
            except subprocess.TimeoutExpired as exc:
                _terminate_process_group(process)
                raise ArbiterError("fresh arbiter exceeded bounded timeout") from exc
            if process.returncode != 0:
                raise ArbiterError(f"fresh arbiter failed with exit {process.returncode}")
            _reject_runtime_identity_mismatch(stdout)
            try:
                raw = output_path.read_text(encoding="utf-8")
                payload = json.loads(raw)
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ArbiterError("fresh arbiter returned no valid schema output") from exc
        if not isinstance(payload, Mapping):
            raise ArbiterError("fresh arbiter output must be an object")
        try:
            decision = arbiter_decision_from_mapping(payload)
        except ValueError as exc:
            raise ArbiterError("fresh arbiter decision contract failed") from exc
        _validate_case_binding(case, decision)
        return decision


def arbiter_output_schema(case: ArbiterCase) -> dict[str, Any]:
    id_schema = {"type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"}
    binding_schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "task_id": id_schema,
            "task_revision": {"type": "integer", "minimum": 1},
            "workstream_id": id_schema,
            "workstream_revision": {"type": "integer", "minimum": 1},
            "pr_head_sha": {"type": "string", "pattern": "^[0-9a-f]{40,64}$"},
            "resources": {
                "type": "array",
                "minItems": 1,
                "maxItems": 128,
                "uniqueItems": True,
                "items": {"type": "string", "minLength": 1, "maxLength": 256},
            },
        },
        "required": [
            "task_id",
            "task_revision",
            "workstream_id",
            "workstream_revision",
            "pr_head_sha",
            "resources",
        ],
    }
    step_schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "step_id": id_schema,
            "action": {"type": "string", "enum": sorted(ARBITER_ACTIONS)},
            "task_id": id_schema,
            "workstream_id": id_schema,
            "depends_on": {
                "type": "array",
                "maxItems": 128,
                "uniqueItems": True,
                "items": id_schema,
            },
        },
        "required": ["step_id", "action", "task_id", "workstream_id", "depends_on"],
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "decision_id": id_schema,
            "kind": {"type": "string", "const": case.kind},
            "case_id": {"type": "string", "const": case.case_id},
            "case_digest": {"type": "string", "const": case.case_digest},
            "bindings": {"type": "array", "minItems": 1, "maxItems": 128, "items": binding_schema},
            "steps": {"type": "array", "minItems": 1, "maxItems": 128, "items": step_schema},
            "model": {"type": "string", "const": REQUIRED_EXECUTOR_MODEL},
            "reasoning": {"type": "string", "const": REQUIRED_EXECUTOR_REASONING},
            "created_at": {"type": "string", "minLength": 20, "maxLength": 40},
            "schema": {"type": "string", "const": ARBITER_DECISION_SCHEMA},
        },
        "required": [
            "decision_id",
            "kind",
            "case_id",
            "case_digest",
            "bindings",
            "steps",
            "model",
            "reasoning",
            "created_at",
            "schema",
        ],
    }


def _arbiter_prompt(case: ArbiterCase) -> str:
    payload = {
        "kind": case.kind,
        "case_id": case.case_id,
        "case_digest": case.case_digest,
        "bindings": [contract_to_dict(binding) for binding in case.bindings],
        "snapshot": json.loads(case._snapshot_json),
    }
    return (
        "You are a stateless semantic adviser. Do not mutate files, GitHub, queues, deployments, or runtime state. "
        "Return only the JSON object required by the supplied output schema. Preserve every immutable binding exactly. "
        "Choose the smallest safe sequence/DAG for this one frozen case.\n\nIMMUTABLE_CASE:\n"
        + json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )


def _validate_case_binding(case: ArbiterCase, decision: ArbiterDecision) -> None:
    if (
        decision.kind != case.kind
        or decision.case_id != case.case_id
        or decision.case_digest != case.case_digest
        or tuple(decision.bindings) != tuple(case.bindings)
    ):
        raise ArbiterError("fresh arbiter answer is stale or changed immutable bindings")


def _terminate_process_group(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()
        process.wait(timeout=3)
    except (OSError, ProcessLookupError, subprocess.TimeoutExpired):
        try:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
        except (OSError, ProcessLookupError):
            pass


def _arbiter_environment(explicit: Mapping[str, str] | None) -> dict[str, str]:
    """Keep auth/runtime discovery but never pass provider or deployment secrets."""

    source = os.environ if explicit is None else explicit
    allowed = {
        "HOME",
        "CODEX_HOME",
        "PATH",
        "TMPDIR",
        "LANG",
        "LC_ALL",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
    }
    environment = {name: str(source[name]) for name in allowed if source.get(name)}
    environment.setdefault("PATH", "/usr/bin:/bin:/usr/sbin:/sbin")
    environment["NO_COLOR"] = "1"
    return environment


def _reject_runtime_identity_mismatch(stdout: str) -> None:
    """Reject explicit CLI reroute/mismatch evidence without trusting model prose."""

    if len(stdout) > 8 * 1024 * 1024:
        raise ArbiterError("fresh arbiter runtime event stream exceeded bounded size")
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, Mapping):
            continue
        encoded = json.dumps(event, ensure_ascii=False, sort_keys=True).lower()
        if "rerout" in encoded:
            raise ArbiterError("fresh arbiter runtime reported a model reroute")
        for key, value in _walk_json(event):
            normalized = key.lower().replace("_", "")
            if normalized in {"model", "modelid"} and isinstance(value, str):
                if value != REQUIRED_EXECUTOR_MODEL:
                    raise ArbiterError("fresh arbiter runtime reported a model mismatch")
            if normalized in {"reasoningeffort", "effort"} and isinstance(value, str):
                if value != REQUIRED_EXECUTOR_REASONING:
                    raise ArbiterError("fresh arbiter runtime reported a reasoning mismatch")


def _walk_json(value: Any) -> Sequence[tuple[str, Any]]:
    rows: list[tuple[str, Any]] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            rows.append((str(key), item))
            rows.extend(_walk_json(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            rows.extend(_walk_json(item))
    return rows


def _freeze_json(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    return value
