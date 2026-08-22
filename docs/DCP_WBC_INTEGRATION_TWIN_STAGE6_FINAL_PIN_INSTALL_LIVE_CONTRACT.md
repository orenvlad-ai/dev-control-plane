# WBC integration twin Stage 6 final pin, install and live contract

contract_revision: 2026-08-22.1

technical_status: PROPOSED; effective only after this exact reviewed authority merges; live schema 86 remains stopped and unconsumed

owner_acceptance: not requested or synthesized

## 1. Exact authority and finish line

This is the one pin/install/live authority allowed by the
[Stage 6 final viability contract](DCP_WBC_INTEGRATION_TWIN_STAGE6_FINAL_VIABILITY_CONTRACT.md).
It becomes executable only after its exact-head `baseline` is green, one fresh
context-free semantic/security review has no material finding, review threads
are zero and this authority merges normally.

After merge it permits exactly one backup, one staged install, migration
`0087`, one stopped preflight, one atomic same-identity adoption, one governed live continuation
and one bounded post-terminal restart/dedupe proof. It does
not permit a second install, adoption, live attempt, source repair, submit,
Worker run, manual publication, manual merge/deploy/SSH, WBC mutation,
production mutation or Stage 7 start.

The pass terminates as exact Stage 6 technical `COMPLETE` or final
`FREEZE/BLOCKED`. Any failed or ambiguous one-use effect consumes its attempt.
There is no retry.

## 2. Source and predecessor binding

| Fact | Exact identity |
| --- | --- |
| managed-source PR | `orenvlad-ai/dcp-orchestrator#78` |
| source PR head | `1e79e4fa99e8c636f9e8d650647e002785fa08af` |
| reviewed merge commit | `d10a9791392e19510590c3fb4a3d231fe980ecf6` |
| reviewed merge tree | `acd93511dd1c77dd2508734bf0b8d331594115cf` |
| source CI | `32590686726`, `source` and `package` green |
| merged-main CI | `32591004094`, `source` and `package` green |
| fresh review | `5000793045`, exact head, no findings |
| installed predecessor source | `e9eb18a99db71813ac8c4556a614d6a3ce4108aa` |
| installed predecessor tree | `b4db2b329accc9a93691bda7c306cc864b07ee56` |
| predecessor receipt SHA-256 | `fc8f2a2f6264dc1a3e817e42f124bdbd7040a412eade3fcddf97762f59f214d8` |
| predecessor schema | `86`, stopped |
| final install identity | `stage6-final-d10a979139-86-to-87-v1` |

The install source is a new permanent standalone clone at the repository-owned
canonical final-install path. It has its own non-symlink `.git`, one exact
`origin`, a clean detached merge commit/tree and stable directory plus Git
filesystem identity. The historical PR #77 install clone, a task worktree,
temporary root, linked worktree, symlink, dirty checkout or foreign remote is
not eligible. The installer never clones, repairs, fetches or checks out source.

The source guard additionally requires migration
`0087_dcp_v2_provider_bound_revision.sql`, the `provider_bound` Revision kind,
durable `TreeSHA`, `ArtifactSourceSHA` and the exact downstream store/service
seam. Source merge grants no live authority outside this contract.

## 3. Frozen same-identity entry fence

Immediately before staging and again under the singleton gateway lock, prove:

- sole Task `dcp-v2-twin-canary-v1`, frozen Revision
  `v2-13f81f321f99d1117dc931419e0bea3945ee35a5`, Command
  `v2-e028f779a18417e990911057f7db7c666f7487ca` and Action
  `v2-40f87d048813533daa1108b4316c09139acf0a8f`;
- frozen runtime `78535564-a2bc-478c-80b0-207753f2152c` and Worker commit/tree
  `bebbf8f617f1a6fa0b9e91698fe710fe0a2bad2c` /
  `2fda4cae71976fd701bf3a9ccca4031f7afb630d`;
- schema `86`, `integrity_check=ok`, empty `foreign_key_check`, lifecycle
  counts `1/1/1/1` and downstream `0/0/0/0`;
- direct runtime/terminal/adoption rows `0/0/0` and
  `adoptionConsumed=false`;
- native Action `74` succeeded, native session idle, zero active native or v2
  model slots/runtime, app/daemon stopped and SQLite sidecars absent;
- lab main unchanged, local Worker branch/commit frozen and no remote canary
  branch, PR, workflow, Admission, Result, merge, artifact or deploy effect;
- WBC PR #987 unchanged and every WBC/production surface frozen.

Any mismatch is `CANARY_RESTRICTED` and stops before mutation.

## 4. Staging, one install and automatic rollback

`bin/dcp-ao install-stage6-final` is the only final install entry. Before app
stop it builds, signs and verifies an arm64 app, then records digest-bound
archives for the exact source, frozen Worker output and artifact plus exact
daemon/renderer bytes, source filesystem identity and predecessor receipt.

Under the gateway lock it gracefully proves the exact app/daemon stopped,
captures one recoverable app/state/data/receipt backup with explicit DB/WAL/SHM
presence and hashes, revalidates staged bytes, atomically replaces the app,
writes the new receipt and opens the packaged store through an inert strict
`import --dry-run` solely to apply migration `0087` once.

Post-stop install, receipt, migration or stopped-preflight failure invokes the
predeclared automatic rollback to the exact schema-86 predecessor app/data/
state/receipt. Whether rollback succeeds or not, the install attempt is spent
and the pass ends `FREEZE/BLOCKED`; reinstall is forbidden.

## 5. Stopped schema-87 acceptance and adoption input

`bin/dcp-ao preflight-stage6-final` accepts only:

- schema exactly `87`, migration row exactly one, integrity `ok`, zero FK
  violations and no SQLite sidecar while stopped;
- installed source/tree and receipt matching the staged source/Worker/artifact
  digests and predecessor receipt;
- every frozen row and timestamp unchanged, direct rows still `0/0/0`, no
  successor/publication/provider effect and zero active model runtime;
- one new immutable adoption-input document bound to the final install receipt,
  exact frozen ids, Worker commit/tree/branch/content, local worktree/output
  digests, remote-branch absence and `consumed=false` at construction.

The input digest is recorded in the one-use install manifest. Equal install
invocation and a second adoption input are rejected.

## 6. One atomic same-identity adoption

`bin/dcp-ao adopt-stage6-final` is the sole adoption entry. Before writing an
attempt marker it repeats the stopped schema-87 and zero-provider fence. Under
the same lock it records `adoption_attempt=1`, invokes the installed hidden
typed adoption command exactly once and validates the full strict JSON result.

Adoption performs no model launch and no provider write. In one SQLite
transaction it creates the historical runtime terminal receipt and immutable
adoption record, terminalizes the existing Action and Command, releases slot
`1`, creates one immutable `worker_output` Revision with `PRNumber=0`, advances
the same Task and enqueues one `publication.execute/v1` Command. Exact stopped
acceptance is Task/Revision/Command/Action `1/2/2/1`, downstream `0/0/0/0`,
direct rows `1/1/1`, zero active slots and unchanged native history.

`bin/dcp-ao preflight-stage6-final-adopted` proves that exact state and remote
zero-effect. A false, failed or ambiguous response ends `FREEZE/BLOCKED`; the
attempt marker forbids replay even if later readback looks equal.

## 7. One governed continuation

`bin/dcp-ao continue-stage6-final` is the only initial live-start entry. It
requires the stopped adopted fence, remote zero-effect and no prior
`continuation_attempt`. Under the gateway lock it records the one-use attempt,
opens only the exact installed application and verifies exact process/run-file/
bundle ownership.

Startup reconciles the pending publication Command. Its durable effect fence
must yield exactly one remote branch and one ready PR. The publication receipt
atomically succeeds that Command, creates one immutable `provider_bound`
successor Revision with the real PR, identical head/tree and explicit
predecessor/cause, advances the same Task and creates one checks Command. The
Worker-output Revision remains `PRNumber=0`. Crossed or multiple effects fail
closed without retry.

The running daemon then carries the same Task through exact checks, one fresh
context-free Reviewer, at most one task-level findings repair plus new exact
checks/review, zero unresolved threads, mechanical FIFO Admission and the exact
integration-lab Release Train. DCP/models do not merge or deploy. Only that
Release Train may merge, build, publish the artifact and perform persistent
Selectel deploy.

Provider events are correctness inputs only after durable exact readback;
polling is never correctness. A request timeout after a possible effect is
ambiguous and triggers `FREEZE/BLOCKED`, never replay.

## 8. Exact terminal and bounded restart/dedupe

Success requires one immutable verified deployment Result and all of:

- deployed SHA = artifact source SHA = merge SHA;
- exact Task/Revision/Admission/PR/head/base/check/review/manifest binding;
- one merge, one artifact and one deploy effect;
- exact health, provenance and anti-co-tenant proof;
- Task terminal `deployed`, truthful `workflowActive=false` and
  `modelActive=false`, zero active v2/native model slots/runtime;
- no duplicate Task, Revision, Command, Action, publication, Admission, merge,
  artifact, deploy or Result.

Only after that terminal fence may the gateway perform one bounded clean
restart/dedupe check. It records a separate one-use restart marker, stops only
the proven exact app/daemon, starts the same installed bundle and compares
complete row/effect cardinalities plus immutable Result/proof digests before
and after. Any change or ambiguous provider effect is `FREEZE/BLOCKED`.

## 9. Mandatory final freeze and global exclusions

Immediately freeze if migration/install/adoption/start cannot complete under
its one-use contract, an effect is ambiguous, a duplicate appears, a new state
falls outside the disposable matrix, or another fundamental lifecycle defect
would require another managed-source PR or installation. No small follow-up
fix is authorized.

WBC, PR #987, production, cutover, Stage 7, manual branch/PR publication,
manual merge/deploy/SSH, a second submit, Worker rerun, replacement identity,
second install/adoption/start and credentials outside the lab Release Train
remain forbidden. Terminal evidence must explicitly say owner acceptance was
not synthesized.
