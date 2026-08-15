# DCP real-target submit recovery v1 terminal evidence

evidence_status: COMPLETE

date: 2026-08-15

scope: exact existing `price-arch-v1` / `wb-price-extension-1` identity only

## 1. Terminal outcome

The original native card 1 is terminal `MERGED`. No second submit,
replacement task/card/session/branch, duplicate worker/reviewer/arbiter,
manual product implementation, manual push or manual merge occurred.

The terminal identities are:

- task `price-arch-v1`, native session `wb-price-extension-1`, card 1;
- branch `ao/wb-price-extension-1/root`;
- worker action sequence 59,
  `dcp-model-price-arch-v1-worker-1`, launch
  `b815e3d2-0dc2-48fe-b9bd-c2bb0b426bcd`;
- reviewer accounting action sequence 60,
  `dcp-model-price-arch-v1-review-1`, existing ReviewRun
  `b0acfb9e-600c-4816-bb2f-02a67817ea05`;
- PR #1, exact head `afc748eba5ff05c0dc24d3002c690ec9f44984fb`;
- admission sequence 27,
  `dcp-admission-b0acfb9e-600c-4816-bb2f-02a67817ea05`;
- ordinary squash merge commit
  `62853496837f64522bb08ba56169f60f3b0f9a2c` at
  `2026-08-15T18:29:22Z`.

The final policy task is `merged`, revision 7. Its PR/head/ReviewRun bindings
are unchanged from the recovered exact identity.

## 2. Preserved predecessor and proof of the first failure

The first and only canonical submit ran against installed source
`9162d4c0eca9efd2a3d9fe1ad09d640c40738c47`, tree
`ec8e4c6d613e5e503a2582955b40bb8f104f76ce`, receipt SHA-256
`5cb06d6edaeb70080999f531da76109936732a57bee8262d9c0cf0af1b7ce295`.
Before correction, read-only proof found SQLite integrity `ok`, exactly one
target policy task/session/worker action, no admission and no duplicate
identity. The task was initially observed at `worker_running`, revision 3,
while the native shell had exited.

Durable artifacts and pane transcripts then proved that the initial worker had
actually completed once, consumed 27,373 tokens, created exact head
`afc748eba5ff05c0dc24d3002c690ec9f44984fb`, and opened ready PR #1 from base
`9522cfb633f9b3f5a87298f4f1dcce902bb7ebfd`. Required `baseline` workflow
`31896051686`, job `95039422914`, succeeded. Worker pane evidence digest is
`a4cfa4a2136973f2dcd6b25923ff783030902f87d5dfe430cd891d708bcc2aa4`.

One context-free reviewer had also completed once, approved with empty
findings and consumed 20,512 tokens. Its review identity is
`f754d155-faad-4a6b-8a03-53a3b93b11b8`, batch
`6b097406-b9bc-42e5-90fb-2b82180e9458`, result channel
`structured_dcp_v1`; reviewer pane evidence digest is
`1443af8a2b97cdd1ccd200b386b5fac04566e79bb80efa3d180895bc43d42dac`.

The immutable policy payload remained exact:

- payload digest
  `efe6a81cfff28be89cc327bdc9e2380ca585fcc6b03064c0290b6aaf4c7b59fe`;
- canonical JSON size 712 bytes and product prompt size 510 UTF-8 bytes;
- exact target/profile/repository `wb-price-extension` / `repo-only` /
  `orenvlad-ai/wb-price-extension`;
- exact policy `dcp.repo-only.happy-path/v1`;
- the native session prompt was the same prompt with only the deterministic
  `DCP repo-only task price-arch-v1: ` prefix.

## 3. Root causes and bounded corrections

The reported `policy submit immutable payload identity drifted` was a false
post-create projection failure. The server had accepted and persisted every
immutable field. The hidden `dcp submit` CLI decoded the response through a
reduced task struct that omitted `target`, `profile` and `repository`, so its
JSON dropped those fields. The adapter's unchanged byte-for-byte validator
correctly rejected the incomplete returned identity. The correction preserved
those three fields in CLI JSON; it did not weaken the validator, prompt limit,
payload digest or replay rules.

Two downstream seams were corrected in the same reviewed contract:

1. repo-only reviewer classification had consulted a synthetic project name
   before the durable policy gate, so the already-consumed reviewer lacked its
   global action-accounting row;
2. the terminal merger independently retained unsupported
   `gh repo view --json databaseId` instead of the already-qualified typed REST
   repository identity lookup.

Migration 0076 first proved every exact predecessor field, then performed one
model-free, idempotent forward recovery: it appended only succeeded reviewer
accounting action 60, preserved truthful token facts, bound the existing
PR/head/ReviewRun and advanced the same task to `admission_waiting`, revision
5. It created no admission and launched no model.

Two later compatibility blockers were proven and corrected without expanding
authority:

- stopped preflight used `sqlite3 -readonly` on a clean WAL-mode database
  after SQLite had removed WAL/SHM sidecars. The fixed helper keeps that live
  read first and permits `mode=ro&immutable=1` only after exact app, port,
  regular-file and absent-sidecar proof;
- governed startup quarantine enumerated all policy tasks but hard-coded only
  the synthetic `dcp-review-lab` tuple. The fixed classifier uses a closed
  static allowlist for the existing synthetic tuple and the exact public
  `wb-price-extension` repo-only tuple, while every crossed or unknown field
  still fails closed.

## 4. Reviewed delivery chain

| Gate | Exact head | Review / CI | Normal merge or source |
| --- | --- | --- | --- |
| control-plane contract PR #205 | `83017cf611a5a98d08266a77486dadd86af29af8` | `PRR_kwDOSUqHmc8AAAABJrPSjA`; baseline `31896834213` | `cf6c39fb46257da0c6dd7c856d52381fd5ca59ac` |
| managed-source PR #59 | `fe75d421a161820e02a4a1bd22f2c1434cf5d887` | `PRR_kwDOTydt6M8AAAABJrRQwQ`; source/package `31897733520` | source `2430e6268281a750f843057acf3084193efacdc5`, tree `3c349323207913574d22a7905441cb9628d7faf0` |
| pin/install-guard PR #206 | `e4b85f14be1da4f97a96867ed5387caad4bded7f` | `PRR_kwDOSUqHmc8AAAABJrSAAg`; baseline `31898119170` | `b8906e69e23c67b784257fead296729e7e73a45d` |
| stopped-SQLite contract PR #207 | `27aa69bcdc44c9bfe4c0d9e818f704741fd2e93b` | `PRR_kwDOSUqHmc8AAAABJrTmEg`; baseline `31898845480` | `1d272600cb9217b15a4ee396e0baa68c1254dd35` |
| stopped-SQLite implementation PR #208 | `872425d7f43b907805033b9b6a92a0feda01cd1a` | `PRR_kwDOSUqHmc8AAAABJrVDZg`; baseline `31899425214` | `f5f15b9b9ba43c07e5a8fc7c7380f47f05ad2ea3` |
| startup-quarantine contract PR #209 | `79d7e7cc303c85a0ca058047c1581bf750f800f3` | `PRR_kwDOSUqHmc8AAAABJrWVCg`; baseline `31900038333` | `73337ec9afdf0eb7dbe9e4e5b03c62d39840cfff` |
| managed-source PR #60 | `fea7ef95ecf0844ac9059c78ccd1e65778d74928` | `PRR_kwDOTydt6M8AAAABJrXpVQ`; source/package `31900560949` | source `f857fc652a529955a3bca4205c09961a1a80b811`, tree `ce8d2a4af467faf7c816152d04ac8a423eeb1b3b` |
| final pin/install-guard PR #210 | `5ec89b745d31ab0bdc970e10ba6f30fcd08cda14` | `PRR_kwDOSUqHmc8AAAABJrYecg`; baseline `31900942255` | `7c8db9ee8ae4888b4fc5d0f424475a194b6be949` |

Every review was anchored to the exact final head. The managed source retained
official Agent Orchestrator ancestry. No source branch was treated as runtime
authority before its separate immutable pin and stopped install.

## 5. Deterministic install ledger

The sequential stopped install ledger is:

| Cycle | Backup | Receipt SHA-256 | Result |
| --- | --- | --- | --- |
| submit-recovery source | `i12-20260815T173130Z` | `420fc3bc9c83efcbd3b5a8288f4754e57b263847eb8a9b2d7d1937d428289c50` | exact install; stopped preflight exposed the clean-WAL CLI boundary before migration |
| stopped-SQLite compatibility | `i12-20260815T175234Z` | `6f8c8d846a263eab8409f9370af0ddf36d409574dd43ae769690cfcf14077698` | stopped preflight passed; migration 0076 applied once; startup quarantine then failed before runtime construction |
| startup-quarantine source | `i12-20260815T182802Z` | `2c38e353acb0a1e9a136a5ab77fcc2b2d49b970cede673d215daf092484df3dd` | stopped prepare/build/install/preflight and exact schema-76 live-copy test passed |

The final installed artifact is exact source
`f857fc652a529955a3bca4205c09961a1a80b811`, tree
`ce8d2a4af467faf7c816152d04ac8a423eeb1b3b`. Its daemon SHA-256 is
`b5c7ed2d793af629868cc752a4a13f7134073c848ed256f93f79d2fb150c84dd`
and app.asar SHA-256 is
`9e4388d9f23364c6cd626c2b16e2b5f3de469986c3ff743120d5886ba4fa8404`.

## 6. Worker, reviewer and merge accounting

There was exactly one worker call, one reviewer call, zero repair calls and
zero arbiter calls for this task:

| Role | Durable identity | Calls | Tokens | Result |
| --- | --- | ---: | ---: | --- |
| worker | action 59 / launch `b815e3d2-0dc2-48fe-b9bd-c2bb0b426bcd` | 1 | 27,373 | succeeded |
| reviewer | action 60 / ReviewRun `b0acfb9e-600c-4816-bb2f-02a67817ea05` | 1 | 20,512 | approved, empty findings |
| repair | none | 0 | 0 | not needed |
| arbiter | none | 0 | 0 | not needed |

Total truthful model tokens are 47,885. The final target counts are exactly
one task, one native session, two model-action rows, one ReviewRun and one
admission; active model actions are zero.

Admission sequence 27 was created and claimed only by the existing terminal
merger. It revalidated exact public provider facts: full name
`orenvlad-ai/wb-price-extension`, default branch `main`, repository id
`1335072844`, owner id `237411244`, non-private/non-archived/non-disabled,
current CLEAN/MERGEABLE head and successful named check. It completed with
status `succeeded`, one lease
`dcp-merge-dcp-admission-b0acfb9e-600c-4816-bb2f-02a67817ea05`, zero refresh
wakes and no error.

PR #1 contains one commit and changes only `docs/ARCHITECTURE.md` (279
additions, 24 deletions). It adds no product code, dependency, credential,
live Wildberries call, server or deployment. Provider `main` is exact merge
commit `62853496837f64522bb08ba56169f60f3b0f9a2c`.

## 7. Restart, deduplication and final stopped proof

The first corrected canonical start became ready at
`2026-08-15T18:29:22Z`. Existing reconciliation created admission 27 and
performed the ordinary merge once. After graceful stop, SQLite SHA-256 was
`b82e6e11b0b30fc43d65c07b98e5b90ba41fa6ba91ad5ddb46fb89f72964fdc0`.

A controlled second start became ready at
`2026-08-15T18:31:30Z`. It preserved task revision 7, actions 59/60, the sole
ReviewRun, admission 27, merge commit and zero active actions. Global totals
remained 60 actions, 39 ReviewRuns and 27 admissions. The only expected SQLite
write on restart was the pre-existing historical card-11/card-12 governed
startup-quarantine verification touch: their counters advanced from 42 in the
install backup to 43 on the first corrected start and 44 on the controlled
restart. It created no policy, model, review, admission or merge identity.

After the final graceful stop:

- SQLite integrity is `ok`, schema version 76 and SHA-256 is
  `20596b57275d07d9d7aa4702b9757d9a0d64e81a254ddda98121b37ce6577551`;
- the exact app process, daemon process, run-file, TCP listener on 43231,
  WAL/SHM sidecars and active model descendants are absent;
- final `bin/dcp-ao preflight` passes against receipt
  `2c38e353acb0a1e9a136a5ab77fcc2b2d49b970cede673d215daf092484df3dd`;
- public `dcp-review-lab` PR #24 remains OPEN and unchanged at head
  `58adc8c6abe1d2fee90cd1bfa9addd149cede1a8`;
- `wb-core`, production, server, secrets, Telegram and foreign repositories
  were not touched.

## 8. Difficulties and residual risks

The three observed failures stayed fail-closed and were preserved rather than
hidden: the post-submit CLI projection defect, stopped clean-WAL read
compatibility, and synthetic-only startup quarantine classifier. The first two
stopped-SQLite CI attempts also exposed platform differences in WAL behavior;
the final regression holds a real WAL connection and injects only the primary
read failure needed to prove the fallback fence deterministically.

Inspecting the pre-fix UI through Computer Use automatically relaunched the app
once after a quit. That extra pre-fix app process was stopped explicitly; it
never constructed a ready daemon, created an admission or launched a model,
and migration 0076 remained idempotent. No UI restart or submit control was
pressed.

The pinned dependency install reports existing npm audit and Node engine
warnings. No dependency was changed or auto-fixed inside this bounded repair.
The local target baseline checkout remains clean at the creation base while
the public provider `main` is the trusted merge commit; it was deliberately not
manually refreshed because local main movement is not part of terminal-merge
authority. These are recorded operational facts, not blockers to the exact
docs-only terminal result.

The original `price-arch-v1` / card 1 has therefore met the contract's COMPLETE
condition.
