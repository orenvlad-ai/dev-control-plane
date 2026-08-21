# Stage 6 direct-model stable-source pin/install contract

contract_revision: 2026-08-22.1

owner_acceptance: not requested or claimed

## 1. Exact bounded authority

This contract authorizes one reviewed pin/install package, one governed
installation with forward migration `0086`, and a stopped preflight. It does
not authorize app restart, Worker adoption, a successor Revision, publication,
model/provider work, target mutation, Stage 7, WBC, Selectel or production.

The only install target is managed-source PR #77 merge
`e9eb18a99db71813ac8c4556a614d6a3ce4108aa`, tree
`b4db2b329accc9a93691bda7c306cc864b07ee56`. The exact predecessor is source
`d084ae3cf0cb3e5e32ebefa197031c24a2b6392d`, tree
`a6e3c3347bbbddd256e9edbfc541f115813249d2`, receipt SHA-256
`19550a9f02b14f13be8a80214529025fd6d4fe7dc8e5bd12c5eaa1a47dd54b0c`.
The one-use install identity is
`stage6-direct-model-e9eb18a99db-85-to-86-v1`.

The sole durable product identity remains:

- Task `dcp-v2-twin-canary-v1`;
- Revision `v2-13f81f321f99d1117dc931419e0bea3945ee35a5`;
- Command `v2-e028f779a18417e990911057f7db7c666f7487ca`;
- Action `v2-40f87d048813533daa1108b4316c09139acf0a8f`;
- historical runtime `78535564-a2bc-478c-80b0-207753f2152c`;
- local Worker commit `bebbf8f617f1a6fa0b9e91698fe710fe0a2bad2c`, tree
  `2fda4cae71976fd701bf3a9ccca4031f7afb630d`.

No missing row is zero. Any identity, count, receipt, source, runtime or remote
effect drift stops before installation.

## 2. MANAGED_SOURCE_WORKTREE_DRIFT closure

The prior attempt stopped before authority PR, backup, app stop, install,
migration or rollback because a task-owned managed-source worktree disappeared.
It had no live, provider or GitHub mutation. That path is not recovered or used.

Future build/install input must be one explicit permanent standalone clone. The
repository-owned guard requires its resolved canonical path class, a real
directory rather than a symlink, its own `.git` directory rather than linked
worktree metadata, exactly one allowed `origin`, a clean detached exact commit
and tree, and stable directory plus Git-metadata filesystem identity. Paths
under task worktrees, the control-plane checkout, temporary roots or `TMPDIR`
fail closed. The installer never clones, fetches, checks out or repairs source.

Immediately before staging, the guard revalidates source and filesystem
identity. Before app stop, the installer creates and verifies:

1. an exact `git archive` bound to commit, tree, remote and SHA-256;
2. an exact frozen Worker commit archive and SHA-256;
3. the exact tested, signed arm64 application artifact and archive SHA-256;
4. exact daemon and renderer archive digests;
5. a local manifest binding predecessor receipt and frozen Worker evidence.

Installation consumes only the already verified staged artifact. Loss or
replacement of source before staging stops without app control. Loss of the
checkout after successful staging cannot change install bytes. An archive or
artifact mismatch stops fail closed. An equal invocation of the one-use
identity is rejected.

## 3. Pre-mutation fence

Before staging and again under the canonical gateway lock, prove:

- schema `85`, `integrity_check=ok`, empty `foreign_key_check`;
- v2 Task/Revision/Command/Action counts `1/1/1/1` with exact ids and frozen
  `worker_queued` / leased / falsely-running state;
- Admission/Incident/ExternalEvent/Result `0/0/0/0`;
- native policy task `ci_waiting` revision `4`, session idle, terminal native
  Action sequence `74`, and zero active legacy model Actions or runtime process;
- unchanged local Worker commit/tree/branch and no remote canary branch, PR,
  check, review, release or Result;
- the exact predecessor bundle/receipt and frozen WBC boundary.

The app may be stopped only by the repository-owned graceful gateway after
exact app/daemon ownership proof. An unknown PID, run-file, port, SQLite
sidecar, runtime or model state fails closed.

## 4. One governed install and migration

`bin/dcp-ao install-stage6-direct-model` is the only installation entry. It
must be invoked exactly once. Under the singleton gateway lock it:

1. revalidates the staged digests and exact live fence;
2. gracefully stops the exact app/daemon and proves stopped/no model runtime;
3. captures exact recoverable app, state, data and receipt backups, with
   explicit present/absent state and digests for DB/WAL/SHM, receipt,
   allowlist configuration and installed bundle components;
4. revalidates the staged source, Worker and artifact digests, then verifies
   the copied daemon and renderer bytes against the same manifest;
5. atomically replaces only the app with the staged artifact;
6. writes a receipt binding source/tree, source archive, artifact archive,
   predecessor receipt and installed daemon/renderer digests;
7. invokes the installed CLI `import --dry-run` against a synthetic inert
   legacy fixture solely to open the store through the packaged SQLite
   migration path; the strict response must prove dry-run and zero import write;
8. proves schema `86` and the stopped acceptance fence.

The migration is only `0086_dcp_v2_direct_model_authority.sql`. The hidden
`stage6-direct-adopt` command is forbidden. No Task lifecycle, runtime,
terminal receipt, adoption, successor Revision or publication row may be
created. Any post-stop install, receipt, migration or acceptance failure invokes
the predeclared automatic rollback, proves exact schema-85 predecessor state,
and terminates `BLOCKED`; no second installation is allowed.

## 5. Stopped acceptance

`bin/dcp-ao preflight-stage6-direct-model` succeeds only when:

- app/daemon remain stopped, canonical port and run-file are absent, and model
  runtime/model Actions are zero;
- installed source/tree equal the PR #77 merge and the new receipt matches the
  staged archive/artifact digests;
- schema is exactly `86`, migration version `86` appears exactly once,
  integrity is `ok`, and foreign-key violations are empty;
- the same four v2 ids and `1/1/1/1` plus downstream `0/0/0/0` are unchanged;
- direct runtime, terminal receipt and one-time adoption tables each have zero
  rows; no successor Revision or publication Command exists;
- native Action `74`, idle session and local Worker commit remain unchanged;
- a read-only future adoption-input document binds the installed receipt,
  frozen ids, exact local commit/tree/content, worktree/output digests and zero
  remote effect, while remaining explicitly unconsumed;
- target/provider/WBC/Selectel/production effects remain zero.

The next boundary, if this stopped phase completes and terminal evidence is
merged, is a separately owner-authorized exact read-only adoption-input
construction and same-identity adoption/live decision. This contract grants no
such continuation. Stage 7 remains not started.
