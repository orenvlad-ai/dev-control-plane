# Stage 6 same-identity adoption blocked evidence

evidence_revision: 2026-08-22.1

technical_status: BLOCKED before live adoption and governed continuation by DCP_V2_PUBLICATION_REVISION_PR_BINDING_MISSING

owner_acceptance: not requested or synthesized

Current stage and next-boundary truth remains in the
[current program manifest](DCP_WBC_INTEGRATION_TWIN_CURRENT_PROGRAM_MANIFEST.md).
This document records the owner-authorized adoption/live-continuation attempt
only. It grants no managed-source, install, runtime, provider, Stage 7, WBC or
production mutation.

## 1. Qualified route and safe-stop boundary

The sole visible executor was task
`01a0282b-bc36-76c0-af83-4a8e4ec5a71e`, titled
`DCP · S6 adoption · И34`, on the qualified local host. Machine readback proved
`approval_policy=never`, unrestricted filesystem, network enabled, one separate
clean `dev-control-plane` worktree and platform approval count `0`. Codex app
`26.707.41301` build `5103`, bundled runner `0.144.0-alpha.4`, PATH runner
`0.145.0`, Git `2.50.1`, GitHub CLI `2.87.2`, Go `1.26.5`, Node `25.9.0`, npm
`11.12.1` and Python `3.13.1` were machine-read.

Fresh `origin/main` was
`701307ae9c650b39bfc0d363289dfdfc25b87430`, tree
`d0e278ddc04a94a5e1b3cc0a39c7cd4d795aefef`, with zero open
`dev-control-plane` pull requests and zero overlapping active DCP change
executors. The owner authorized one reviewed adoption/live authority package,
one exact same-identity adoption and continuation, and one terminal evidence
package. Its automatic safe-stop rule required termination before mutation if
a new managed-source defect or need to change `dcp-orchestrator` was found.

That rule fired during Phase A source inspection. No adoption authority package
was published, and no live adoption, start or provider action was attempted.
This is the single authorized evidence-only `BLOCKED` closure.

## 2. Exact immutable input

The fresh stopped preflight and repository-owned readback reconfirmed:

| Fact | Exact value |
| --- | --- |
| Task | `dcp-v2-twin-canary-v1`, `worker_queued`, state revision `1` |
| Revision | `v2-13f81f321f99d1117dc931419e0bea3945ee35a5` |
| Command | `v2-e028f779a18417e990911057f7db7c666f7487ca`, `worker.execute/v1`, `leased` |
| DCP-v2 Action | `v2-40f87d048813533daa1108b4316c09139acf0a8f`, historical `running`, slot `1` |
| historical runtime | `78535564-a2bc-478c-80b0-207753f2152c` |
| native terminal fact | Action `74` succeeded, slot `0`; session idle; zero active native model Actions |
| frozen Worker output | commit `bebbf8f617f1a6fa0b9e91698fe710fe0a2bad2c`, tree `2fda4cae71976fd701bf3a9ccca4031f7afb630d` |
| installed source | commit `e9eb18a99db71813ac8c4556a614d6a3ce4108aa`, tree `b4db2b329accc9a93691bda7c306cc864b07ee56` |
| installed receipt | `fc8f2a2f6264dc1a3e817e42f124bdbd7040a412eade3fcddf97762f59f214d8` |
| frozen adoption input SHA-256 | `1e3fdd63457d2c1bfdb1a64c647c56b5d75c5d7260de91b033a93e22a82f7f09` |
| SQLite | schema `86`; `integrity_check=ok`; foreign-key violations `0` |
| durable counts | Task/Revision/Command/Action `1/1/1/1`; Admission/Incident/ExternalEvent/Result `0/0/0/0` |
| direct rows | model-runtime/terminal-receipt/adoption `0/0/0`; `adoptionConsumed=false` |
| stopped contour | app stopped; daemon stopped; zero app/daemon/model runtime processes |

The installed source checkout was detached, clean and exact at the commit/tree
above. The adoption-input digest still matched the immutable stable-install
evidence.

## 3. Deterministic managed-source defect

The installed source cannot carry the adopted Worker output through its first
real check event while preserving its own exact-identity predicates:

1. `completeWorkerReceipt` creates the immutable successor Worker-output
   Revision and its `publication.execute/v1` Command. The Revision has
   `PRNumber=0` because no PR exists yet.
2. `publicationOutcome` receives the real publication receipt and creates
   `checks.observe/v1` with the returned commit and PR in the Command payload,
   but it does not bind that PR number to the Revision.
3. The atomic store transition inserts a `NextRevision` only when one is
   supplied. Publication supplies none, and the store exposes no transition
   that updates the already-created immutable Revision.
4. `completeChecks` then calls `ObserveChecks` and requires the real
   `facts.PRNumber` to equal `revision.PRNumber`. A successful publication has
   a non-zero PR number while the Revision remains `0`, so the first real check
   event deterministically fails as `DCP v2 exact check observation drifted`.

The exact defect code is
`DCP_V2_PUBLICATION_REVISION_PR_BINDING_MISSING`. It is in managed source
`e9eb18a99db71813ac8c4556a614d6a3ce4108aa` and requires a
`dcp-orchestrator` correction plus new reviewed pin/install authority. No such
source change was authorized in this task.

## 4. Disposable-copy proof

A model-free diagnostic copied the stopped database to a disposable location
and invoked the installed adoption entrypoint only against that copy. It made
no live SQLite, model or provider mutation. The atomic copy-only transition
produced exactly:

- successor Revision
  `v2-0e1aadfb444bc4d9f4c90c8bf936a0ebec125300`, sequence `2`, kind
  `worker_output`, frozen Worker commit/tree, `PRNumber=0`;
- publication Command
  `v2-06b20be020812369bf4286fd335aa8f5281d15e2`, pending;
- terminal receipt
  `v2-eb68fd8ab844afa1e0639deebc6aca641704a88a`;
- historical Action, Command and runtime terminalized, with slot released;
- one consumed adoption row and an otherwise valid database with
  `integrity_check=ok` and zero foreign-key violations.

The copy-only result proves that the adoption transition itself reaches the
successor publication boundary and preserves `PRNumber=0`; source inspection
then proves the missing binding before `completeChecks`. It was not replayed
against live state.

The read-only snapshot operation briefly created empty WAL/coordination
sidecars beside the stopped live database. No process held them, the database
digest and rows did not change, and integrity and foreign-key checks remained
clean. The two exact sidecars were moved recoverably out of the contour; the
repository-owned stopped preflight then passed again with both absent. No
database write, install, migration, restart or cleanup of unrelated state
occurred.

## 5. Unconsumed live and provider boundary

Fresh post-diagnostic readback proved the live contour remained exactly at the
immutable input in section 2. In particular:

- there was no second submit, adoption row, terminal receipt, model-runtime
  row, successor Revision or publication Command;
- the app and daemon remained stopped, the native Action remained succeeded
  and idle, and no model or provider process ran;
- no canary remote branch or PR, CI, review, Admission, Release Train, merge,
  artifact, deploy, provenance or Result appeared;
- `dcp-orchestrator` main remained the installed source commit with zero open
  PRs; integration-lab main remained
  `375b9b2d0b4c2fce6f2c417850553f79e24a0d92`, with no canary ref or open PR;
- WBC PR #987 remained open at
  `26044c696651ce5873748ec3f920d40e77c5686c`; WBC, production, cutover and the
  protected co-tenant were not touched.

The adoption authority is therefore unconsumed. Equal invocation is not a
recovery path: no adoption may occur until the named source defect is corrected,
reviewed, pinned and installed under new exact owner authority.

## 6. Terminal classification

Stage 6 remains technically `BLOCKED` before live adoption. Stage 7 is not
started. The safe terminal state is schema `86`, app/daemon stopped,
`adoptionConsumed=false`, direct rows `0/0/0`, frozen sole identity, zero provider effect
and no other target effect. Technical classification does not synthesize owner
acceptance.
