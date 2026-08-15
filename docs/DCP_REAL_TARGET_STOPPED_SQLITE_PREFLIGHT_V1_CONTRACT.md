# DCP real-target stopped-SQLite preflight compatibility v1 contract

contract_status: owner-approved-pre-runtime

date: 2026-08-15

scope: one exact stopped-preflight read boundary for the existing
`price-arch-v1` recovery

## 1. Exact predecessor and preserved state

The reviewed submit-recovery chain is already merged: control-plane contract
PR #205, managed-source PR #59 at source
`2430e6268281a750f843057acf3084193efacdc5`, tree
`3c349323207913574d22a7905441cb9628d7faf0`, and pin/install-guard PR #206.
The deterministic install created backup `i12-20260815T173130Z` and installed
that exact source with receipt SHA-256
`420fc3bc9c83efcbd3b5a8288f4754e57b263847eb8a9b2d7d1937d428289c50`.

The installed application and daemon are stopped. Migration 0076 has not run.
SQLite remains at version 75 with integrity `ok`; exact task
`price-arch-v1`, native card/session `wb-price-extension-1`, action sequence 59,
PR #1 and its approved ReviewRun remain unchanged. There is no target admission,
no active model action and no process descendant. No second submit or model call
was made.

The following stopped `preflight` failed before daemon or migration activity:

```text
Error: in prepare, unable to open database file (14)
DCP AO: wb-price-extension linked worktree identity mismatch: .../wb-price-extension-1
```

## 2. Proven compatibility boundary

The exact policy row and linked-worktree metadata are valid. The defect is the
adapter's use of `sqlite3 -readonly` for the durable policy-authority query.
The database is configured for WAL journaling. A clean application shutdown
checkpoints and removes `ao.db-wal` and `ao.db-shm`, while the main database
retains WAL journal mode. This SQLite CLI cannot open that clean stopped WAL
database through `-readonly`, because a read-only connection cannot recreate
the required sidecars. It exits 14 before executing either identity query, and
the caller collapses that command failure into the generic worktree mismatch.

This is not a corrupt database, missing authority row, worktree drift or source
runtime defect. A normal read connection can see the exact row but creates
operational WAL/SHM sidecars; manually creating those sidecars would be a
workaround and is not an accepted fix.

## 3. Authorized adapter correction

One control-plane compatibility change may replace only the two policy-row
`sqlite3 -readonly` invocations with one fail-closed helper:

1. first attempt the existing read-only query, preserving correct live-WAL
   visibility when the canonical daemon is running;
2. if and only if that read-only open fails, prove the exact canonical DCP app
   is absent, the exact loopback port is not occupied, the canonical database
   is a regular file at the fixed lab-root path, and both WAL/SHM sidecars are
   absent;
3. only on that stopped-clean conjunction, retry the same SELECT through an
   SQLite URI with `mode=ro&immutable=1` so no sidecar is created;
4. return only the SELECT result. Any process, port, sidecar, malformed result,
   SQL error or ambiguous identity remains a hard failure.

The helper may not use a normal writable SQLite connection, create/delete a
sidecar, checkpoint, vacuum, migrate, copy or modify the database, change the
SELECT predicates, weaken exact task/session/card/worktree/branch/target/profile/
repository/policy equality, or turn an absent/multiple row into success.

Managed source, migration 0076, the immutable lock, installed bundle, submit
path, daemon, action queue, reviewer, admission controller and terminal merger
remain byte-for-byte unchanged by this correction. It adds no submit, model
call, task/card/session/branch/PR, database object, daemon, service, queue,
watcher, poller, timer, heartbeat, credential or merge authority.

## 4. Required model-free proof and delivery

Regression coverage must create an exact WAL-mode fixture with the repo-only
policy schema, exact policy row and linked worktree. After a clean checkpoint
and removal by SQLite itself of WAL/SHM sidecars, it must prove:

- the current `-readonly` command reproduces exit 14;
- the corrected validator accepts exactly one matching durable row;
- the main database digest and metadata stay unchanged and no sidecar appears;
- a mismatched or duplicate authority row is rejected;
- when a live WAL exists, the primary read-only path observes its current
  contents and the immutable fallback is not used;
- any exact app, occupied loopback port, existing sidecar or fallback command
  failure rejects instead of retrying immutably.

Delivery is sequential: merge this reviewed contract with green baseline;
merge one reviewed compatibility implementation PR; prove the exact app is
stopped and repeat deterministic `prepare -> build -> install -> preflight`.
Only after the stopped preflight passes may the existing canonical app start
and migration 0076 continue the original task. The original recovery contract's
ordinary admission/merge, restart/dedupe, terminal evidence and final stopped
requirements remain unchanged. Completion still requires original card 1 to be
terminal `MERGED`; otherwise preserve one exact `BLOCKED` or Human Gate state.
