"""DCP-authored deterministic single-canary supervisor."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
from typing import Callable, Protocol
import uuid

from .config import RuntimePaths, TASK_ID
from .provenance import HistoryRefs


MARKER_RELATIVE = "canary/dcp-orchestrator-canary.txt"
MARKER_BYTES = b"DCP isolated canary\n"
MARKER_SHA256 = hashlib.sha256(MARKER_BYTES).hexdigest()
TERMINAL_STATES = {"succeeded", "failed", "cleanup_failed", "safety_violation"}
STATE_LABELS = {
    "preparing": "готовится",
    "running": "выполняется",
    "verifying": "проверяется",
    "cleaning": "очищается",
    "succeeded": "завершена",
    "failed": "ошибка",
    "cleanup_failed": "ошибка очистки",
    "safety_violation": "нарушение безопасности",
}


class CanaryError(RuntimeError):
    reason = "canary_error"


class SafetyViolation(CanaryError):
    reason = "safety_boundary_violation"


@dataclass(frozen=True)
class WorkerReceipt:
    pid: int
    returncode: int
    executor_identity: str
    output_digest: str
    timed_out: bool = False


class Worker(Protocol):
    def execute(self, cwd: Path) -> WorkerReceipt: ...


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _git(*args: str, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and result.returncode != 0:
        message = result.stderr.decode("utf-8", "replace").strip()
        raise CanaryError(f"git {' '.join(args)} failed: {message}")
    return result


class CodexWorker:
    """One ephemeral Codex CLI process with a fixed, non-user-authored task."""

    PROMPT = (
        "You are the single isolated worker for the DCP laboratory canary. "
        "Work only in the current disposable repository. Do not inspect any path "
        "outside the current working directory and do not use the network. Create "
        "exactly one file, canary/dcp-orchestrator-canary.txt, with exact UTF-8 "
        "bytes DCP isolated canary followed by one LF. Do not modify any other "
        "file. Do not commit, push, create a remote, or create another worktree. "
        "After writing the marker, verify only its bytes and git status, then stop."
    )

    def __init__(self, timeout_seconds: int = 180):
        self.timeout_seconds = timeout_seconds

    def execute(self, cwd: Path) -> WorkerReceipt:
        executable = shutil.which("codex")
        if not executable:
            raise CanaryError("codex CLI is not available on PATH")
        command = [
            executable,
            "exec",
            "--ephemeral",
            "--ignore-user-config",
            "--sandbox",
            "workspace-write",
            "--color",
            "never",
            "--cd",
            str(cwd),
            self.PROMPT,
        ]
        allowed_env = {
            "HOME",
            "PATH",
            "CODEX_HOME",
            "OPENAI_API_KEY",
            "HTTPS_PROXY",
            "HTTP_PROXY",
            "ALL_PROXY",
            "NO_PROXY",
            "SSL_CERT_FILE",
            "SSL_CERT_DIR",
            "TMPDIR",
            "LANG",
            "LC_ALL",
        }
        env = {key: value for key, value in os.environ.items() if key in allowed_env}
        env.update(
            {
                "DCP_ORCHESTRATOR_TASK_ID": TASK_ID,
                "DCP_ORCHESTRATOR_WORKER": "1",
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_CONFIG_NOSYSTEM": "1",
            }
        )
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        timed_out = False
        try:
            output, _ = process.communicate(timeout=self.timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            process.terminate()
            try:
                output, _ = process.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                output, _ = process.communicate()
        return WorkerReceipt(
            pid=process.pid,
            returncode=process.returncode,
            executor_identity="codex-cli/ephemeral/workspace-write",
            output_digest=hashlib.sha256(output or b"").hexdigest(),
            timed_out=timed_out,
        )


class CanarySupervisor:
    """Serializes one canary attempt and emits facts through a callback."""

    def __init__(
        self,
        paths: RuntimePaths,
        worker: Worker | None = None,
        on_snapshot: Callable[[dict], None] | None = None,
    ):
        self.paths = paths
        self.worker = worker or CodexWorker()
        self.on_snapshot = on_snapshot or (lambda _snapshot: None)
        self._run_lock = threading.Lock()

    def _transition(self, record: dict, state: str, reason: str, *, publish: bool = True) -> None:
        sequence = len(record["transitions"]) + 1
        event = {"sequence": sequence, "state": state, "reason": reason, "at": _utc_now()}
        record["transitions"].append(event)
        record["state"] = state
        record["state_label"] = STATE_LABELS[state]
        record["reason"] = reason
        if publish:
            self.on_snapshot(json.loads(json.dumps(record)))

    def _new_record(self, run_id: str) -> dict:
        return {
            "schema_version": 1,
            "task_id": TASK_ID,
            "run_id": run_id,
            "state": "preparing",
            "state_label": STATE_LABELS["preparing"],
            "reason": "accepted",
            "card_count": 1,
            "attempt_count": 1,
            "worker_count": 1,
            "retry_count": 0,
            "attempt": 1,
            "transitions": [],
            "summary": "Лабораторный canary принят; prompt не сохраняется.",
            "evidence_refs": [],
            "history_refs": HistoryRefs().to_dict(),
            "owner_acceptance": None,
        }

    def _ensure_repository(self) -> tuple[str, Path]:
        self.paths.create()
        repo = self.paths.assert_lab_containment(self.paths.repository)
        allowlist_path = self.paths.state / "lab-allowlist.json"
        if not repo.exists():
            if allowlist_path.exists():
                raise SafetyViolation("allowlist exists but disposable repository is absent")
            repo.mkdir(parents=True, mode=0o700)
            _git("init", "--initial-branch=main", cwd=repo)
            (repo / "README.md").write_text(
                "# DCP_lab\n\nDisposable repository for the fixed DCP canary only.\n",
                encoding="utf-8",
            )
            (repo / "AGENTS.md").write_text(
                "# DCP laboratory rules\n\n"
                "Only create canary/dcp-orchestrator-canary.txt with exact bytes "
                "`DCP isolated canary\\n`. Do not inspect outside this repository. "
                "Do not modify another file, use a network, commit, push, merge, "
                "add a remote or create another worktree.\n",
                encoding="utf-8",
            )
            _git("add", "README.md", "AGENTS.md", cwd=repo)
            _git(
                "-c",
                "user.name=DCP Laboratory",
                "-c",
                "user.email=dcp-lab@invalid.local",
                "commit",
                "-m",
                "Initialize disposable DCP laboratory",
                cwd=repo,
            )
            baseline = _git("rev-parse", "HEAD", cwd=repo).stdout.decode().strip()
            payload = {
                "schema_version": 1,
                "repository": str(repo.resolve()),
                "git_common_dir": str((repo / ".git").resolve()),
                "baseline_commit": baseline,
                "remote_count": 0,
            }
            with allowlist_path.open("x", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.write("\n")
            allowlist_path.chmod(0o600)
        elif not allowlist_path.exists():
            raise SafetyViolation("existing repository has no DCP allowlist")

        allowlist = json.loads(allowlist_path.read_text(encoding="utf-8"))
        baseline = _git("rev-parse", "HEAD", cwd=repo).stdout.decode().strip()
        common_dir_raw = _git("rev-parse", "--git-common-dir", cwd=repo).stdout.decode().strip()
        common_dir = (repo / common_dir_raw).resolve()
        remotes = _git("remote", cwd=repo).stdout.decode().splitlines()
        status = _git("status", "--porcelain=v1", "--untracked-files=all", cwd=repo).stdout
        checks = {
            "repository": str(repo.resolve()) == allowlist.get("repository"),
            "git_common_dir": str(common_dir) == allowlist.get("git_common_dir"),
            "baseline_commit": baseline == allowlist.get("baseline_commit"),
            "remote_count": len(remotes) == 0 == allowlist.get("remote_count"),
            "clean_baseline": status == b"",
            "outside_source_repository": not str(repo.resolve()).startswith(
                str(self.paths.source_root.resolve()) + os.sep
            ),
        }
        if not all(checks.values()):
            failed = ",".join(key for key, value in checks.items() if not value)
            raise SafetyViolation(f"disposable repository allowlist mismatch: {failed}")
        return baseline, common_dir

    def _verify_marker(self, worktree: Path) -> dict:
        marker = worktree / MARKER_RELATIVE
        if not marker.is_file():
            raise CanaryError("marker_missing")
        payload = marker.read_bytes()
        if payload != MARKER_BYTES:
            raise CanaryError("marker_bytes_mismatch")
        status = _git(
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=all",
            cwd=worktree,
        ).stdout
        expected = f"?? {MARKER_RELATIVE}\0".encode()
        if status != expected:
            raise SafetyViolation("mutation_set_outside_marker_allowlist")
        tracked_diff = _git("diff", "--name-only", "--", cwd=worktree).stdout
        staged_diff = _git("diff", "--cached", "--name-only", "--", cwd=worktree).stdout
        if tracked_diff or staged_diff:
            raise SafetyViolation("tracked_or_staged_mutation_detected")
        diff_receipt = (
            f"untracked {MARKER_RELATIVE}\n"
            f"bytes {len(payload)}\nsha256 {hashlib.sha256(payload).hexdigest()}\n"
        ).encode()
        return {
            "relative_path": MARKER_RELATIVE,
            "byte_count": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "expected_sha256": MARKER_SHA256,
            "git_status_porcelain": f"?? {MARKER_RELATIVE}",
            "tracked_diff_paths": [],
            "staged_diff_paths": [],
            "scoped_diff_digest": hashlib.sha256(diff_receipt).hexdigest(),
        }

    def _persist_terminal(self, record: dict, evidence: dict) -> list[str]:
        record_dir = self.paths.records / record["run_id"]
        record_dir.mkdir(mode=0o700)
        task_path = record_dir / "terminal-task.json"
        evidence_path = record_dir / "evidence-manifest.json"
        refs = [
            f"dcp://data/lab/records/{record['run_id']}/terminal-task.json",
            f"dcp://data/lab/records/{record['run_id']}/evidence-manifest.json",
        ]
        record["evidence_refs"] = refs
        for path, payload in ((task_path, record), (evidence_path, evidence)):
            with path.open("x", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True, ensure_ascii=False)
                handle.write("\n")
            path.chmod(0o600)
        return refs

    def run(self) -> dict:
        if not self._run_lock.acquire(blocking=False):
            raise SafetyViolation("a canary attempt is already active")

        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
        record = self._new_record(run_id)
        evidence: dict = {
            "schema_version": 1,
            "task_id": TASK_ID,
            "run_id": run_id,
            "operator_prompt_retained": False,
            "worker_transcript_retained": False,
            "network": {
                "application_endpoints": ["loopback-only"],
                "worker_tool_network": "denied-by-workspace-write-policy-and-fixed-instruction",
                "updater": "absent",
                "telemetry_analytics_crash_reporting": "absent",
            },
            "negative_targets": {
                "dev_control_plane": "not-allowlisted; source root outside lab root",
                "wb_core": "not-allowlisted",
                "production": "not-allowlisted",
                "hosted": "not-allowlisted",
                "real_targets": "not-allowlisted",
            },
            "history_refs": HistoryRefs().to_dict(),
            "retention": "manual-owner-controlled-no-automatic-deletion",
        }
        lock_path = self.paths.locks / f"{TASK_ID}.lock"
        attempt_dir = self.paths.attempts / run_id
        worktree = self.paths.worktrees / run_id
        branch = f"dcp-canary-{run_id.lower()}"
        worker_receipt: WorkerReceipt | None = None
        marker_evidence: dict | None = None
        worktree_created = False
        baseline = ""
        common_dir = Path()
        terminal = "failed"
        reason = "unclassified_failure"
        cleanup_errors: list[str] = []

        try:
            self._transition(record, "preparing", "accepted")
            self.paths.create()
            try:
                descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError as exc:
                raise SafetyViolation("active_lock_present") from exc
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(run_id + "\n")
            attempt_dir.mkdir(mode=0o700)

            baseline, common_dir = self._ensure_repository()
            self.paths.assert_lab_containment(worktree)
            _git("worktree", "add", "-b", branch, str(worktree), baseline, cwd=self.paths.repository)
            worktree_created = True
            cwd_resolved = worktree.resolve()
            worktree_common_raw = _git("rev-parse", "--git-common-dir", cwd=worktree).stdout.decode().strip()
            worktree_common = (worktree / worktree_common_raw).resolve()
            containment = {
                "cwd": str(cwd_resolved),
                "cwd_inside_lab_root": str(cwd_resolved).startswith(str(self.paths.lab.resolve()) + os.sep),
                "cwd_outside_source_repository": not str(cwd_resolved).startswith(
                    str(self.paths.source_root.resolve()) + os.sep
                ),
                "git_common_dir": str(worktree_common),
                "git_common_dir_matches_allowlist": worktree_common == common_dir,
                "repository": str(self.paths.repository.resolve()),
                "baseline_commit": baseline,
                "branch": branch,
                "remote_count": 0,
            }
            if not all(
                containment[key]
                for key in (
                    "cwd_inside_lab_root",
                    "cwd_outside_source_repository",
                    "git_common_dir_matches_allowlist",
                )
            ):
                raise SafetyViolation("worktree containment check failed")
            evidence["containment"] = containment

            self._transition(record, "running", "single_worker_started")
            worker_receipt = self.worker.execute(worktree)
            evidence["worker"] = {
                "count": 1,
                "pid": worker_receipt.pid,
                "exited": worker_receipt.returncode is not None,
                "returncode": worker_receipt.returncode,
                "timed_out": worker_receipt.timed_out,
                "executor_identity": worker_receipt.executor_identity,
                "output_digest": worker_receipt.output_digest,
                "transcript_retained": False,
                "session_persistence": "ephemeral",
            }
            if worker_receipt.timed_out:
                raise CanaryError("worker_timeout")
            if worker_receipt.returncode != 0:
                raise CanaryError("worker_nonzero_exit")

            self._transition(record, "verifying", "worker_exited")
            marker_evidence = self._verify_marker(worktree)
            evidence["marker"] = marker_evidence
            terminal = "succeeded"
            reason = "marker_verified_and_cleanup_complete"
        except SafetyViolation as exc:
            terminal = "safety_violation"
            reason = str(exc) or exc.reason
        except Exception as exc:  # truthfully classified after cleanup
            terminal = "failed"
            reason = str(exc) or getattr(exc, "reason", type(exc).__name__)
        finally:
            self._transition(record, "cleaning", "cleanup_started")
            if worktree_created:
                result = _git(
                    "worktree",
                    "remove",
                    "--force",
                    str(worktree),
                    cwd=self.paths.repository,
                    check=False,
                )
                if result.returncode != 0:
                    cleanup_errors.append("worktree_remove_failed")
                _git("worktree", "prune", cwd=self.paths.repository, check=False)
                result = _git("branch", "-D", branch, cwd=self.paths.repository, check=False)
                if result.returncode != 0:
                    cleanup_errors.append("branch_remove_failed")
            if attempt_dir.exists():
                try:
                    attempt_dir.rmdir()
                except OSError:
                    cleanup_errors.append("attempt_state_remove_failed")
            if lock_path.exists():
                try:
                    lock_path.unlink()
                except OSError:
                    cleanup_errors.append("lock_remove_failed")

            marker_gone = not (worktree / MARKER_RELATIVE).exists()
            cleanup = {
                "worker_exited": worker_receipt is None or worker_receipt.returncode is not None,
                "session_persistence": "ephemeral",
                "lock_removed": not lock_path.exists(),
                "timers_remaining": 0,
                "attempt_state_removed": not attempt_dir.exists(),
                "worktree_removed": not worktree.exists(),
                "branch_removed": (
                    not worktree_created
                    or _git("branch", "--list", branch, cwd=self.paths.repository, check=False).stdout.strip() == b""
                ),
                "marker_disappeared": marker_gone,
                "errors": cleanup_errors,
            }
            evidence["cleanup"] = cleanup
            if cleanup_errors or not all(
                cleanup[key]
                for key in (
                    "worker_exited",
                    "lock_removed",
                    "attempt_state_removed",
                    "worktree_removed",
                    "branch_removed",
                    "marker_disappeared",
                )
            ):
                terminal = "cleanup_failed"
                reason = "cleanup_incomplete"

            record["summary"] = {
                "succeeded": "Canary завершён: marker проверен, worker завершён, cleanup подтверждён.",
                "failed": "Canary завершился ошибкой до подтверждённого результата.",
                "cleanup_failed": "Canary неуспешен: cleanup подтверждён не полностью.",
                "safety_violation": "Canary остановлен из-за нарушения safety boundary.",
            }[terminal]
            record["terminal_reason"] = reason
            record["repository"] = str(self.paths.repository)
            record["baseline_commit"] = baseline or None
            record["executor_identity"] = (
                worker_receipt.executor_identity if worker_receipt else "not_started"
            )
            record["marker"] = marker_evidence
            # Persist the immutable terminal record and evidence before the UI is
            # allowed to observe a successful terminal state.
            self._transition(record, terminal, reason, publish=False)
            evidence["terminal_state"] = terminal
            evidence["terminal_reason"] = reason
            evidence["transition_sequences"] = [item["sequence"] for item in record["transitions"]]
            try:
                self._persist_terminal(record, evidence)
            finally:
                self._run_lock.release()
            self.on_snapshot(json.loads(json.dumps(record)))
        return record
