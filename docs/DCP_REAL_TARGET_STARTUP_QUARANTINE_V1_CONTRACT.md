# DCP real-target startup quarantine compatibility v1 contract

contract_status: owner-approved-pre-runtime

date: 2026-08-15

scope: one exact startup classification correction for the recovered
`price-arch-v1` policy session

## 1. Preserved exact state

The submit-recovery and stopped-SQLite compatibility chains are reviewed,
merged and installed. Exact managed source is
`2430e6268281a750f843057acf3084193efacdc5`, tree
`3c349323207913574d22a7905441cb9628d7faf0`; final stopped install backup is
`i12-20260815T175234Z` and receipt SHA-256 is
`6f8c8d846a263eab8409f9370af0ddf36d409574dd43ae769690cfcf14077698`.

The first controlled start applied migration 0076 exactly once and no model
action. SQLite integrity is `ok`, schema version is 76, and the same task is
`admission_waiting`, revision 5. Its exact native session remains
`wb-price-extension-1`, project `wb-price-extension`, card 1, branch
`ao/wb-price-extension-1/root`, idle and not terminated. Worker action 59 and
reviewer accounting action 60 are succeeded; the immutable recovery audit has
one row. PR #1, exact head/check/approved ReviewRun are unchanged. There is no
target admission, no active model action and no process descendant.

The daemon failed before runtime construction with:

```text
establish DCP governed startup quarantine: future DCP policy session classification drifted
```

The application is stopped after proof. No restart button, submit, worker,
reviewer, arbiter, admission or merge was invoked.

## 2. Proven root cause

`EstablishDCPGovernedStartupQuarantine` correctly lists every durable policy
task so stock restore cannot own it. Its per-task validator, however, still
hard-codes only historical/future `dcp-review-lab`: project and session prefix
must be `dcp-review-lab`, and card must be greater than 12. The already-
authorized repo-only policy row is exact but necessarily has project/prefix
`wb-price-extension` and card 1, so the cold-start fence rejects it.

This is a static allowlist classification omission. It is not session, policy,
payload, recovery or provider drift, and it does not authorize removing the
quarantine fence or skipping stock-restore exclusion.

## 3. Authorized source correction

One managed-source change may alter only this per-policy startup classifier:

- preserve the existing exact synthetic tuple: target/project/session prefix
  `dcp-review-lab`, profile `synthetic-pr`, repository
  `orenvlad-ai/dcp-review-lab`, policy `dcp.review-lab.happy-path/v1`, and card
  greater than 12;
- accept the one already-authorized repo-only tuple: target/project/session
  prefix `wb-price-extension`, profile `repo-only`, repository
  `orenvlad-ai/wb-price-extension`, policy `dcp.repo-only.happy-path/v1`, and
  positive card number;
- for either tuple, still require an existing native session whose project,
  card number and exact `<prefix>-<card>` identity match the policy row;
- add the exact session to the same in-memory restore-quarantine map.

Every unknown/mixed target, profile, repository, policy, project, session
prefix, card or absent/duplicate row remains a startup error. Historical card
11/12 quarantine, its immutable rows/touch fence and all stock restore guards
remain unchanged.

The correction adds no migration, recovery write, task/session/action,
submit, model call, database object, daemon, service, queue, watcher, poller,
timer, heartbeat, retry, credential, provider authority, admission or merge
bypass. Migration 0076 and all recovered identities remain immutable.

## 4. Regression and delivery

Model-free tests must prove ordinary databases remain unaffected; exact
synthetic and repo-only rows are quarantined; every crossed tuple and session
identity fails closed. An opt-in copy of the exact schema-76 live database must
reproduce the predecessor failure, pass after correction with
`wb-price-extension-1` present in the quarantine map, and prove unchanged
task/action/recovery/admission/model counts.

Delivery remains sequential: merge this reviewed contract; merge one ordinary
managed-source PR after fresh exact-head semantic/security review and source/
package CI; merge one separate immutable pin/install-guard PR; prove stopped
`prepare -> build -> install -> preflight`; then start only the canonical app.
Its existing startup reconciliation alone may create/claim the ordinary FIFO
admission and merge exact PR #1. One controlled restart must prove stable
identities and no duplicates, followed by final stopped preflight and reviewed
terminal evidence. Completion still requires original card 1 to be terminal
`MERGED`; otherwise preserve one exact `BLOCKED` or Human Gate state.
