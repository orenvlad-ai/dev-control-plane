"""Versioned, fail-closed contracts for the local Orchestrator v2.

The contracts in this module deliberately do not extend the legacy ``TaskSpec``
or sprint contracts.  They are the machine boundary shared by the deterministic
Supervisor, Codex adapters, the release scheduler and the sanitized projection.
Unknown fields and unknown enum values are rejected so that a newer producer
cannot silently weaken an older consumer.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
import hashlib
import json
from pathlib import PurePosixPath
import re
from typing import Any, Mapping, Sequence

TASK_PASSPORT_SCHEMA = "dev-control-plane/task-passport/v2"
WORKSTREAM_SCHEMA = "dev-control-plane/workstream/v2"
CHECKPOINT_SCHEMA = "dev-control-plane/checkpoint/v2"
TERMINAL_EVIDENCE_SCHEMA = "dev-control-plane/terminal-evidence/v2"
ARBITER_DECISION_SCHEMA = "dev-control-plane/arbiter-decision/v2"
RELEASE_CLOSURE_MANIFEST_SCHEMA = "dev-control-plane/release-closure-manifest/v2"

REQUIRED_EXECUTOR_MODEL = "gpt-5.6-sol"
REQUIRED_EXECUTOR_REASONING = "ultra"

CONTOURS = frozenset({"release:done", "release:production", "diagnostic", "artifact"})
WORKSTREAM_STATES = frozenset(
    {
        "started",
        "working",
        "waiting_release",
        "recovering",
        "blocked",
        "technical_complete",
        "acceptance_pending",
        "accepted",
        "parked",
    }
)
CANONICAL_PROGRESS_STAGES = frozenset({5, 15, 25, 40, 55, 65, 72, 80, 88, 95, 100})
CHECKPOINT_PROGRESS_STAGES = CANONICAL_PROGRESS_STAGES - {100}
TERMINAL_CLOSURE_KINDS = CONTOURS
ARBITER_KINDS = frozenset({"release_plan", "incident"})
ARBITER_ACTIONS = frozenset(
    {
        "release",
        "wait",
        "verify",
        "retry_current_executor",
        "start_successor_executor",
        "apply_repo_remediation",
        "park_workstream",
    }
)
HUMAN_GATE_REASON_CODES = frozenset(
    {
        "missing_credential",
        "interactive_login",
        "interactive_2fa",
        "captcha",
        "security_permission_change",
        "new_external_destination",
        "proven_irreversible_risk",
        "material_scope_risk_acceptance_change",
        "platform_hard_stop",
    }
)

# Task Passports use a closed, machine-checkable authorization vocabulary.
# These are capabilities, not descriptive prose: an actuator must name the
# exact capability immediately before it mutates external or local state.
# `self_merge` deliberately excludes changes to the installed authority
# implementation (Supervisor/registry/release policy, projection authority,
# CI/self-closure, deploy, migration and installer code). That surface is a
# separate security-permission change handled by the protected two-phase
# HumanGate; there is no broad Passport capability that can silently widen it.
AUTONOMY_ACTIONS = frozenset(
    {
        "codex_workspace_mutation",
        "repo_edit",
        "local_checks",
        "github_readback",
        "hosted_readback",
        "self_merge",
        "self_hosted_deploy",
        "wb_github_command",
        "target_release_command",
        "target_lane_release",
    }
)
RELEASE_ACTUATOR_ACTIONS = frozenset(
    {
        "self_merge",
        "self_hosted_deploy",
        "wb_github_command",
        "target_release_command",
        "target_lane_release",
    }
)
SELF_RELEASE_TARGETS = frozenset(
    {"dev-control-plane", "orenvlad-ai/dev-control-plane"}
)
WB_CORE_RELEASE_TARGET = "orenvlad-ai/wb-core"

_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_SHA_RE = re.compile(r"^[0-9a-f]{40,64}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


class OrchestrationValidationError(ValueError):
    """Raised when an Orchestrator v2 boundary contract is invalid."""


@dataclass(frozen=True)
class CuratorIdentity:
    thread_id: str
    host_id: str

    def __post_init__(self) -> None:
        _identifier("curator.thread_id", self.thread_id)
        _identifier("curator.host_id", self.host_id)


@dataclass(frozen=True)
class ExecutorIdentity:
    thread_id: str
    host_id: str
    model: str
    reasoning: str

    def __post_init__(self) -> None:
        _identifier("executor.thread_id", self.thread_id)
        _identifier("executor.host_id", self.host_id)
        if self.model != REQUIRED_EXECUTOR_MODEL:
            raise OrchestrationValidationError(
                f"executor.model must be {REQUIRED_EXECUTOR_MODEL!r}; observed {self.model!r}"
            )
        if self.reasoning != REQUIRED_EXECUTOR_REASONING:
            raise OrchestrationValidationError(
                f"executor.reasoning must be {REQUIRED_EXECUTOR_REASONING!r}; observed {self.reasoning!r}"
            )


@dataclass(frozen=True)
class AutonomyEnvelope:
    allowed_actions: Sequence[str]
    prohibited_actions: Sequence[str]
    human_gate_reasons: Sequence[str] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "allowed_actions", _strings("autonomy.allowed_actions", self.allowed_actions, required=True))
        object.__setattr__(
            self,
            "prohibited_actions",
            _strings("autonomy.prohibited_actions", self.prohibited_actions, required=True),
        )
        reasons = _strings("autonomy.human_gate_reasons", self.human_gate_reasons)
        unknown = set(reasons) - HUMAN_GATE_REASON_CODES
        if unknown:
            raise OrchestrationValidationError(f"unknown human gate reason codes: {sorted(unknown)}")
        if set(self.allowed_actions) & set(self.prohibited_actions):
            raise OrchestrationValidationError("autonomy actions cannot be both allowed and prohibited")
        unknown_actions = (
            set(self.allowed_actions) | set(self.prohibited_actions)
        ) - AUTONOMY_ACTIONS
        if unknown_actions:
            raise OrchestrationValidationError(
                f"unknown autonomy actions: {sorted(unknown_actions)}"
            )
        object.__setattr__(self, "human_gate_reasons", reasons)


@dataclass(frozen=True)
class ReleaseClosureManifest:
    """Final immutable release chain declared by a Passport revision."""

    logical_lane_id: str
    pr_identities: Sequence[str]
    deploy_identities: Sequence[str]
    finalized_at: str
    schema: str = RELEASE_CLOSURE_MANIFEST_SCHEMA

    def __post_init__(self) -> None:
        _schema("ReleaseClosureManifest", self.schema, RELEASE_CLOSURE_MANIFEST_SCHEMA)
        _identifier("release_manifest.logical_lane_id", self.logical_lane_id)
        prs = _strings("release_manifest.pr_identities", self.pr_identities, required=True)
        deploys = _strings("release_manifest.deploy_identities", self.deploy_identities)
        if len(set(prs)) != len(prs) or len(set(deploys)) != len(deploys):
            raise OrchestrationValidationError("release closure manifest identities must be unique")
        if any(not item.startswith("github-pr-v1:") for item in prs):
            raise OrchestrationValidationError("release closure manifest PR identity is not immutable v1")
        if any(not item.startswith("hosted-release-v1:") for item in deploys):
            raise OrchestrationValidationError("release closure manifest deploy identity is not immutable v1")
        _timestamp("release_manifest.finalized_at", self.finalized_at)
        object.__setattr__(self, "pr_identities", prs)
        object.__setattr__(self, "deploy_identities", deploys)


@dataclass(frozen=True)
class TaskPassport:
    task_id: str
    revision: int
    title: str
    objective: str
    expected_result: str
    contour: str
    included_scope: Sequence[str]
    excluded_scope: Sequence[str]
    constraints: Sequence[str]
    acceptance: Sequence[str]
    closure: Sequence[str]
    autonomy: AutonomyEnvelope
    workstream_ids: Sequence[str]
    release_manifest: ReleaseClosureManifest | None
    resources: Sequence[str]
    modules: Sequence[str]
    files: Sequence[str]
    dependencies: Sequence[str]
    multi_pr_intent: bool
    multi_deploy_intent: bool
    curator: CuratorIdentity
    executor: ExecutorIdentity | None
    created_at: str
    schema: str = TASK_PASSPORT_SCHEMA

    def __post_init__(self) -> None:
        _schema("TaskPassport", self.schema, TASK_PASSPORT_SCHEMA)
        _identifier("task_id", self.task_id)
        _positive_int("revision", self.revision)
        _text("title", self.title)
        _text("objective", self.objective)
        _text("expected_result", self.expected_result)
        if self.contour not in CONTOURS:
            raise OrchestrationValidationError(f"unknown contour: {self.contour!r}")
        object.__setattr__(self, "included_scope", _strings("included_scope", self.included_scope, required=True))
        object.__setattr__(self, "excluded_scope", _strings("excluded_scope", self.excluded_scope))
        object.__setattr__(self, "constraints", _strings("constraints", self.constraints, required=True))
        object.__setattr__(self, "acceptance", _strings("acceptance", self.acceptance, required=True))
        object.__setattr__(self, "closure", _strings("closure", self.closure, required=True))
        workstream_ids = _identifiers("workstream_ids", self.workstream_ids)
        if not workstream_ids:
            raise OrchestrationValidationError("workstream_ids must declare the complete closure manifest")
        object.__setattr__(self, "workstream_ids", workstream_ids)
        object.__setattr__(self, "resources", _resources("resources", self.resources, required=True))
        object.__setattr__(self, "modules", _resources("modules", self.modules))
        object.__setattr__(self, "files", _files("files", self.files))
        dependencies = _identifiers("dependencies", self.dependencies)
        if self.task_id in dependencies:
            raise OrchestrationValidationError("task cannot depend on itself")
        object.__setattr__(self, "dependencies", dependencies)
        if not isinstance(self.multi_pr_intent, bool) or not isinstance(self.multi_deploy_intent, bool):
            raise OrchestrationValidationError("multi_pr_intent and multi_deploy_intent must be booleans")
        if self.release_manifest is not None and not isinstance(self.release_manifest, ReleaseClosureManifest):
            raise OrchestrationValidationError("release_manifest must be typed or null")
        if not self.contour.startswith("release:") and self.release_manifest is not None:
            raise OrchestrationValidationError("non-release Passport cannot declare a release manifest")
        targets = tuple(
            item.removeprefix("target:")
            for item in self.resources
            if item.startswith("target:")
        )
        lanes = tuple(
            item.removeprefix("release-lane:")
            for item in self.resources
            if item.startswith("release-lane:")
        )
        routing = tuple(
            item
            for item in self.resources
            if item.startswith(("target:", "release-lane:"))
        )
        if self.contour.startswith("release:"):
            if len(targets) != 1 or not targets[0]:
                raise OrchestrationValidationError(
                    "release Passport requires exactly one target:<target-id> resource"
                )
            if len(lanes) != 1 or not lanes[0]:
                raise OrchestrationValidationError(
                    "release Passport requires exactly one release-lane:<lane-id> resource"
                )
            scheduler_resources = tuple(
                item
                for item in self.resources
                if not item.startswith(
                    ("target:", "release-lane:", "owner-priority:")
                )
            )
            if not scheduler_resources:
                raise OrchestrationValidationError(
                    "release Passport requires a non-routing scheduler resource"
                )
            required_actions = required_release_actions(self.contour, targets[0])
            prohibited_required = required_actions & set(self.autonomy.prohibited_actions)
            if prohibited_required:
                raise OrchestrationValidationError(
                    "release contour prohibits required actuator actions: "
                    + ", ".join(sorted(prohibited_required))
                )
            missing_actions = required_actions - set(self.autonomy.allowed_actions)
            if missing_actions:
                raise OrchestrationValidationError(
                    "release contour lacks explicit actuator authorization: "
                    + ", ".join(sorted(missing_actions))
                )
            if (
                self.contour == "release:done"
                and targets[0] in SELF_RELEASE_TARGETS
                and "self_hosted_deploy" in self.autonomy.allowed_actions
            ):
                raise OrchestrationValidationError(
                    "release:done cannot authorize self_hosted_deploy"
                )
        elif routing:
            raise OrchestrationValidationError(
                "non-release Passport cannot declare target/release-lane routing resources"
            )
        elif set(self.autonomy.allowed_actions) & RELEASE_ACTUATOR_ACTIONS:
            raise OrchestrationValidationError(
                "non-release Passport cannot authorize release actuator actions"
            )
        if self.release_manifest is not None:
            if self.release_manifest.logical_lane_id != lanes[0]:
                raise OrchestrationValidationError(
                    "release manifest lane differs from the declared release-lane resource"
                )
            if self.multi_pr_intent and len(self.release_manifest.pr_identities) < 2:
                raise OrchestrationValidationError("multi-PR closure manifest requires at least two PR identities")
            if not self.multi_pr_intent and len(self.release_manifest.pr_identities) != 1:
                raise OrchestrationValidationError("single-PR closure manifest requires exactly one PR identity")
            if self.contour == "release:done" and self.release_manifest.deploy_identities:
                raise OrchestrationValidationError("release:done manifest cannot claim a deploy")
            if self.contour == "release:production" and not self.release_manifest.deploy_identities:
                raise OrchestrationValidationError("production release manifest requires a deploy identity")
            if self.multi_deploy_intent and len(self.release_manifest.deploy_identities) < 2:
                raise OrchestrationValidationError("multi-deploy manifest requires at least two deploy identities")
            if not self.multi_deploy_intent and len(self.release_manifest.deploy_identities) > 1:
                raise OrchestrationValidationError("single-deploy manifest cannot list multiple deploy identities")
        _timestamp("created_at", self.created_at)


def required_release_actions(contour: str, target_id: str) -> frozenset[str]:
    """Return the exact actuator capabilities for one registered target."""

    if contour not in {"release:done", "release:production"}:
        raise OrchestrationValidationError("release actuator authorization requires a release contour")
    required = {"target_lane_release"}
    if target_id in SELF_RELEASE_TARGETS:
        required.add("self_merge")
        if contour == "release:production":
            required.add("self_hosted_deploy")
    elif target_id == WB_CORE_RELEASE_TARGET:
        required.add("wb_github_command")
    else:
        required.add("target_release_command")
    return frozenset(required)


def require_passport_action(passport: TaskPassport, action: str) -> None:
    """Fail closed unless the current Passport explicitly authorizes action."""

    if action not in AUTONOMY_ACTIONS:
        raise OrchestrationValidationError(f"unknown actuator action: {action!r}")
    if action in passport.autonomy.prohibited_actions:
        raise OrchestrationValidationError(
            f"Passport explicitly prohibits actuator action {action!r}"
        )
    if action not in passport.autonomy.allowed_actions:
        raise OrchestrationValidationError(
            f"Passport does not explicitly authorize actuator action {action!r}"
        )


@dataclass(frozen=True)
class Workstream:
    workstream_id: str
    task_id: str
    revision: int
    generation: int
    root_workstream_id: str
    corrective_of_generation: int | None
    title: str
    objective: str
    state: str
    executor: ExecutorIdentity | None
    resources: Sequence[str]
    dependencies: Sequence[str]
    created_at: str
    schema: str = WORKSTREAM_SCHEMA

    def __post_init__(self) -> None:
        _schema("Workstream", self.schema, WORKSTREAM_SCHEMA)
        _identifier("workstream_id", self.workstream_id)
        _identifier("task_id", self.task_id)
        _identifier("root_workstream_id", self.root_workstream_id)
        _positive_int("revision", self.revision)
        _positive_int("generation", self.generation)
        if self.generation == 1:
            if self.corrective_of_generation is not None:
                raise OrchestrationValidationError("first workstream generation cannot be corrective")
            if self.root_workstream_id != self.workstream_id:
                raise OrchestrationValidationError("first workstream generation must be its own root")
        elif self.corrective_of_generation != self.generation - 1:
            raise OrchestrationValidationError("corrective generation must replace the immediately preceding generation")
        _text("title", self.title)
        _text("objective", self.objective)
        if self.state not in WORKSTREAM_STATES:
            raise OrchestrationValidationError(f"unknown workstream state: {self.state!r}")
        if self.executor is not None and not isinstance(self.executor, ExecutorIdentity):
            raise OrchestrationValidationError("workstream.executor must be an exact identity or null before start")
        object.__setattr__(self, "resources", _resources("resources", self.resources, required=True))
        dependencies = _identifiers("dependencies", self.dependencies)
        if self.workstream_id in dependencies:
            raise OrchestrationValidationError("workstream cannot depend on itself")
        object.__setattr__(self, "dependencies", dependencies)
        _timestamp("created_at", self.created_at)


@dataclass(frozen=True)
class Checkpoint:
    checkpoint_id: str
    event_id: str
    task_id: str
    task_revision: int
    workstream_id: str
    workstream_revision: int
    executor_generation: int
    executor: ExecutorIdentity
    progress_stage: int
    delta_ru: str
    current_ru: str
    evidence: Sequence[str]
    created_at: str
    schema: str = CHECKPOINT_SCHEMA

    def __post_init__(self) -> None:
        _schema("Checkpoint", self.schema, CHECKPOINT_SCHEMA)
        for name in ("checkpoint_id", "event_id", "task_id", "workstream_id"):
            _identifier(name, getattr(self, name))
        for name in ("task_revision", "workstream_revision", "executor_generation"):
            _positive_int(name, getattr(self, name))
        if self.progress_stage not in CHECKPOINT_PROGRESS_STAGES:
            raise OrchestrationValidationError("checkpoint progress_stage must be a canonical non-terminal stage")
        _text("delta_ru", self.delta_ru)
        _text("current_ru", self.current_ru)
        object.__setattr__(self, "evidence", _strings("evidence", self.evidence, required=True))
        _timestamp("created_at", self.created_at)


@dataclass(frozen=True)
class TerminalEvidence:
    terminal_id: str
    event_id: str
    task_id: str
    task_revision: int
    workstream_id: str
    workstream_revision: int
    executor_generation: int
    executor: ExecutorIdentity
    closure_kind: str
    summary_ru: str
    evidence: Sequence[str]
    checks: Sequence[str]
    pr_identities: Sequence[str]
    deploy_identities: Sequence[str]
    owner_acceptance_required: bool
    created_at: str
    schema: str = TERMINAL_EVIDENCE_SCHEMA

    def __post_init__(self) -> None:
        _schema("TerminalEvidence", self.schema, TERMINAL_EVIDENCE_SCHEMA)
        for name in ("terminal_id", "event_id", "task_id", "workstream_id"):
            _identifier(name, getattr(self, name))
        for name in ("task_revision", "workstream_revision", "executor_generation"):
            _positive_int(name, getattr(self, name))
        if self.closure_kind not in TERMINAL_CLOSURE_KINDS:
            raise OrchestrationValidationError(f"unknown terminal closure kind: {self.closure_kind!r}")
        _text("summary_ru", self.summary_ru)
        object.__setattr__(self, "evidence", _strings("evidence", self.evidence, required=True))
        object.__setattr__(self, "checks", _strings("checks", self.checks, required=True))
        object.__setattr__(self, "pr_identities", _strings("pr_identities", self.pr_identities))
        object.__setattr__(self, "deploy_identities", _strings("deploy_identities", self.deploy_identities))
        if self.closure_kind == "release:production" and not self.deploy_identities:
            raise OrchestrationValidationError("release:production requires at least one deploy identity")
        if self.owner_acceptance_required is not True:
            raise OrchestrationValidationError("technical terminal evidence must require explicit owner acceptance")
        _timestamp("created_at", self.created_at)


@dataclass(frozen=True)
class RevisionBinding:
    task_id: str
    task_revision: int
    workstream_id: str
    workstream_revision: int
    pr_head_sha: str
    resources: Sequence[str]

    def __post_init__(self) -> None:
        _identifier("binding.task_id", self.task_id)
        _identifier("binding.workstream_id", self.workstream_id)
        _positive_int("binding.task_revision", self.task_revision)
        _positive_int("binding.workstream_revision", self.workstream_revision)
        if not _SHA_RE.fullmatch(self.pr_head_sha):
            raise OrchestrationValidationError("binding.pr_head_sha must be a lowercase Git object id")
        object.__setattr__(self, "resources", _resources("binding.resources", self.resources, required=True))


@dataclass(frozen=True)
class DecisionStep:
    step_id: str
    action: str
    task_id: str
    workstream_id: str
    depends_on: Sequence[str] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        for name in ("step_id", "task_id", "workstream_id"):
            _identifier(f"decision_step.{name}", getattr(self, name))
        if self.action not in ARBITER_ACTIONS:
            raise OrchestrationValidationError(f"unknown arbiter action: {self.action!r}")
        object.__setattr__(self, "depends_on", _identifiers("decision_step.depends_on", self.depends_on))
        if self.step_id in self.depends_on:
            raise OrchestrationValidationError("decision step cannot depend on itself")


@dataclass(frozen=True)
class ArbiterDecision:
    decision_id: str
    kind: str
    case_id: str
    case_digest: str
    bindings: Sequence[RevisionBinding]
    steps: Sequence[DecisionStep]
    model: str
    reasoning: str
    created_at: str
    schema: str = ARBITER_DECISION_SCHEMA

    def __post_init__(self) -> None:
        _schema("ArbiterDecision", self.schema, ARBITER_DECISION_SCHEMA)
        for name in ("decision_id", "case_id"):
            _identifier(name, getattr(self, name))
        if self.kind not in ARBITER_KINDS:
            raise OrchestrationValidationError(f"unknown arbiter kind: {self.kind!r}")
        if not _DIGEST_RE.fullmatch(self.case_digest):
            raise OrchestrationValidationError("case_digest must be a lowercase sha256 digest")
        bindings = tuple(self.bindings)
        steps = tuple(self.steps)
        if not bindings or not steps:
            raise OrchestrationValidationError("arbiter decision requires bindings and steps")
        binding_keys = {(item.task_id, item.workstream_id) for item in bindings}
        if len(binding_keys) != len(bindings):
            raise OrchestrationValidationError("arbiter decision has duplicate bindings")
        step_ids = {item.step_id for item in steps}
        if len(step_ids) != len(steps):
            raise OrchestrationValidationError("arbiter decision has duplicate step ids")
        for step in steps:
            if (step.task_id, step.workstream_id) not in binding_keys:
                raise OrchestrationValidationError("arbiter step is not covered by an immutable binding")
            if not set(step.depends_on).issubset(step_ids):
                raise OrchestrationValidationError("arbiter step refers to an unknown dependency")
        _assert_acyclic(steps)
        if self.model != REQUIRED_EXECUTOR_MODEL or self.reasoning != REQUIRED_EXECUTOR_REASONING:
            raise OrchestrationValidationError("arbiter must be a fresh gpt-5.6-sol / ultra invocation")
        _timestamp("created_at", self.created_at)
        object.__setattr__(self, "bindings", bindings)
        object.__setattr__(self, "steps", steps)


def validate_workstream_against_passport(workstream: Workstream, passport: TaskPassport) -> None:
    if workstream.task_id != passport.task_id:
        raise OrchestrationValidationError("workstream task_id does not match passport")
    if workstream.workstream_id not in passport.workstream_ids:
        raise OrchestrationValidationError("workstream is outside the Passport closure manifest")
    if not set(workstream.resources).issubset(set(passport.resources)):
        raise OrchestrationValidationError("workstream declares resources outside its passport")
    if passport.executor is not None and workstream.executor is not None and workstream.executor != passport.executor:
        # A Passport executor is the exact default for a single-executor
        # envelope. Multi-workstream envelopes leave it null and bind each
        # Workstream independently.
        raise OrchestrationValidationError("workstream executor differs from the exact Passport default")


def validate_checkpoint_binding(
    checkpoint: Checkpoint,
    *,
    task_revision: int,
    workstream_revision: int,
    executor_generation: int,
    executor: ExecutorIdentity,
) -> None:
    observed = (
        checkpoint.task_revision,
        checkpoint.workstream_revision,
        checkpoint.executor_generation,
        checkpoint.executor,
    )
    expected = (task_revision, workstream_revision, executor_generation, executor)
    if observed != expected:
        raise OrchestrationValidationError("checkpoint is stale or bound to a different executor")


def validate_terminal_binding(
    terminal: TerminalEvidence,
    *,
    contour: str,
    task_revision: int,
    workstream_revision: int,
    executor_generation: int,
    executor: ExecutorIdentity,
) -> None:
    if terminal.closure_kind != contour:
        raise OrchestrationValidationError("terminal evidence does not prove the passport contour")
    observed = (
        terminal.task_revision,
        terminal.workstream_revision,
        terminal.executor_generation,
        terminal.executor,
    )
    expected = (task_revision, workstream_revision, executor_generation, executor)
    if observed != expected:
        raise OrchestrationValidationError("terminal evidence is stale or bound to a different executor")


def contract_to_dict(value: Any) -> dict[str, Any]:
    if not hasattr(value, "__dataclass_fields__"):
        raise TypeError("value must be an Orchestrator contract dataclass")
    return _json_ready(asdict(value))


def canonical_contract_json(value: Any) -> str:
    return json.dumps(contract_to_dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def contract_digest(value: Any) -> str:
    return hashlib.sha256(canonical_contract_json(value).encode("utf-8")).hexdigest()


def task_passport_from_mapping(payload: Mapping[str, Any]) -> TaskPassport:
    _strict_keys(
        "TaskPassport",
        payload,
        required={
            "schema", "task_id", "revision", "title", "objective", "expected_result", "contour",
            "included_scope", "excluded_scope", "constraints", "acceptance", "closure", "autonomy",
            "workstream_ids", "release_manifest", "resources", "modules", "files", "dependencies", "multi_pr_intent", "multi_deploy_intent",
            "curator", "executor", "created_at",
        },
    )
    autonomy = _mapping(payload, "autonomy")
    _strict_keys("AutonomyEnvelope", autonomy, required={"allowed_actions", "prohibited_actions", "human_gate_reasons"})
    curator = _mapping(payload, "curator")
    _strict_keys("CuratorIdentity", curator, required={"thread_id", "host_id"})
    executor_payload = payload["executor"]
    executor: ExecutorIdentity | None
    if executor_payload is None:
        executor = None
    else:
        if not isinstance(executor_payload, Mapping):
            raise OrchestrationValidationError("executor must be an object or null")
        _strict_keys("ExecutorIdentity", executor_payload, required={"thread_id", "host_id", "model", "reasoning"})
        executor = ExecutorIdentity(**dict(executor_payload))
    manifest_payload = payload["release_manifest"]
    release_manifest: ReleaseClosureManifest | None
    if manifest_payload is None:
        release_manifest = None
    else:
        if not isinstance(manifest_payload, Mapping):
            raise OrchestrationValidationError("release_manifest must be an object or null")
        _strict_keys(
            "ReleaseClosureManifest",
            manifest_payload,
            required=set(ReleaseClosureManifest.__dataclass_fields__),
        )
        release_manifest = ReleaseClosureManifest(**dict(manifest_payload))
    return TaskPassport(
        schema=_str(payload, "schema"), task_id=_str(payload, "task_id"), revision=_int(payload, "revision"),
        title=_str(payload, "title"), objective=_str(payload, "objective"),
        expected_result=_str(payload, "expected_result"), contour=_str(payload, "contour"),
        included_scope=_sequence(payload, "included_scope"), excluded_scope=_sequence(payload, "excluded_scope"),
        constraints=_sequence(payload, "constraints"), acceptance=_sequence(payload, "acceptance"),
        closure=_sequence(payload, "closure"),
        autonomy=AutonomyEnvelope(
            allowed_actions=_sequence(autonomy, "allowed_actions"),
            prohibited_actions=_sequence(autonomy, "prohibited_actions"),
            human_gate_reasons=_sequence(autonomy, "human_gate_reasons"),
        ),
        workstream_ids=_sequence(payload, "workstream_ids"),
        release_manifest=release_manifest,
        resources=_sequence(payload, "resources"), modules=_sequence(payload, "modules"),
        files=_sequence(payload, "files"), dependencies=_sequence(payload, "dependencies"),
        multi_pr_intent=_bool(payload, "multi_pr_intent"), multi_deploy_intent=_bool(payload, "multi_deploy_intent"),
        curator=CuratorIdentity(thread_id=_str(curator, "thread_id"), host_id=_str(curator, "host_id")),
        executor=executor, created_at=_str(payload, "created_at"),
    )


def workstream_from_mapping(payload: Mapping[str, Any]) -> Workstream:
    fields = set(Workstream.__dataclass_fields__)
    _strict_keys("Workstream", payload, required=fields)
    values = dict(payload)
    if values["executor"] is not None:
        values["executor"] = _executor_from_value(values["executor"])
    return Workstream(**values)


def checkpoint_from_mapping(payload: Mapping[str, Any]) -> Checkpoint:
    fields = set(Checkpoint.__dataclass_fields__)
    _strict_keys("Checkpoint", payload, required=fields)
    values = dict(payload)
    values["executor"] = _executor_from_value(values["executor"])
    return Checkpoint(**values)


def terminal_evidence_from_mapping(payload: Mapping[str, Any]) -> TerminalEvidence:
    fields = set(TerminalEvidence.__dataclass_fields__)
    _strict_keys("TerminalEvidence", payload, required=fields)
    values = dict(payload)
    values["executor"] = _executor_from_value(values["executor"])
    return TerminalEvidence(**values)


def arbiter_decision_from_mapping(payload: Mapping[str, Any]) -> ArbiterDecision:
    fields = set(ArbiterDecision.__dataclass_fields__)
    _strict_keys("ArbiterDecision", payload, required=fields)
    raw_bindings = _sequence(payload, "bindings")
    raw_steps = _sequence(payload, "steps")
    bindings: list[RevisionBinding] = []
    steps: list[DecisionStep] = []
    for raw in raw_bindings:
        if not isinstance(raw, Mapping):
            raise OrchestrationValidationError("bindings items must be objects")
        _strict_keys("RevisionBinding", raw, required=set(RevisionBinding.__dataclass_fields__))
        bindings.append(RevisionBinding(**dict(raw)))
    for raw in raw_steps:
        if not isinstance(raw, Mapping):
            raise OrchestrationValidationError("steps items must be objects")
        _strict_keys("DecisionStep", raw, required=set(DecisionStep.__dataclass_fields__))
        steps.append(DecisionStep(**dict(raw)))
    values = dict(payload)
    values["bindings"] = bindings
    values["steps"] = steps
    return ArbiterDecision(**values)


def _executor_from_value(value: Any) -> ExecutorIdentity:
    if not isinstance(value, Mapping):
        raise OrchestrationValidationError("executor must be an object")
    _strict_keys("ExecutorIdentity", value, required=set(ExecutorIdentity.__dataclass_fields__))
    return ExecutorIdentity(**dict(value))


def _assert_acyclic(steps: Sequence[DecisionStep]) -> None:
    graph = {step.step_id: tuple(step.depends_on) for step in steps}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            raise OrchestrationValidationError("arbiter decision DAG contains a cycle")
        if node in visited:
            return
        visiting.add(node)
        for dependency in graph[node]:
            visit(dependency)
        visiting.remove(node)
        visited.add(node)

    for node in graph:
        visit(node)


def _schema(label: str, observed: str, expected: str) -> None:
    if observed != expected:
        raise OrchestrationValidationError(f"{label}.schema must be {expected!r}; observed {observed!r}")


def _identifier(label: str, value: Any) -> str:
    if not isinstance(value, str) or not _IDENTIFIER_RE.fullmatch(value):
        raise OrchestrationValidationError(f"{label} must be a bounded machine identifier")
    return value


def _identifiers(label: str, values: Sequence[str]) -> tuple[str, ...]:
    items = _sequence_value(label, values)
    normalized = tuple(_identifier(f"{label}[]", value) for value in items)
    if len(set(normalized)) != len(normalized):
        raise OrchestrationValidationError(f"{label} must not contain duplicates")
    return normalized


def _text(label: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 16_384 or any(ord(char) < 32 and char not in "\n\t" for char in value):
        raise OrchestrationValidationError(f"{label} must be non-empty bounded text")
    return value.strip()


def _strings(label: str, values: Sequence[str], *, required: bool = False) -> tuple[str, ...]:
    items = _sequence_value(label, values)
    normalized = tuple(_text(f"{label}[]", value) for value in items)
    if required and not normalized:
        raise OrchestrationValidationError(f"{label} must not be empty")
    if len(set(normalized)) != len(normalized):
        raise OrchestrationValidationError(f"{label} must not contain duplicates")
    return normalized


def _resources(label: str, values: Sequence[str], *, required: bool = False) -> tuple[str, ...]:
    items = _strings(label, values, required=required)
    for item in items:
        if len(item) > 256 or item != item.strip() or any(ord(char) < 33 for char in item):
            raise OrchestrationValidationError(f"{label} contains an unsafe resource identifier")
    return items


def _files(label: str, values: Sequence[str]) -> tuple[str, ...]:
    items = _strings(label, values)
    for item in items:
        if "\\" in item or item.startswith("/") or "\x00" in item:
            raise OrchestrationValidationError(f"{label} paths must be relative POSIX paths")
        path = PurePosixPath(item)
        if not path.parts or any(part in {"", ".", ".."} for part in path.parts):
            raise OrchestrationValidationError(f"{label} contains traversal or an empty path")
    return items


def _positive_int(label: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise OrchestrationValidationError(f"{label} must be a positive integer")
    return value


def _timestamp(label: str, value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise OrchestrationValidationError(f"{label} must be an RFC3339 timestamp")
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise OrchestrationValidationError(f"{label} must be an RFC3339 timestamp") from exc
    if parsed.tzinfo is None:
        raise OrchestrationValidationError(f"{label} must include a timezone")
    return value


def _sequence_value(label: str, value: Any) -> tuple[Any, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise OrchestrationValidationError(f"{label} must be an array")
    return tuple(value)


def _strict_keys(label: str, payload: Mapping[str, Any], *, required: set[str]) -> None:
    if not isinstance(payload, Mapping):
        raise OrchestrationValidationError(f"{label} must be an object")
    observed = set(payload)
    missing = required - observed
    unknown = observed - required
    if missing:
        raise OrchestrationValidationError(f"{label} missing fields: {sorted(missing)}")
    if unknown:
        raise OrchestrationValidationError(f"{label} has unknown fields: {sorted(unknown)}")


def _mapping(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key)
    if not isinstance(value, Mapping):
        raise OrchestrationValidationError(f"{key} must be an object")
    return value


def _str(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise OrchestrationValidationError(f"{key} must be a string")
    return value


def _int(payload: Mapping[str, Any], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise OrchestrationValidationError(f"{key} must be an integer")
    return value


def _bool(payload: Mapping[str, Any], key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise OrchestrationValidationError(f"{key} must be a boolean")
    return value


def _sequence(payload: Mapping[str, Any], key: str) -> tuple[Any, ...]:
    return _sequence_value(key, payload.get(key))


def _json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_ready(item) for item in value]
    return value
