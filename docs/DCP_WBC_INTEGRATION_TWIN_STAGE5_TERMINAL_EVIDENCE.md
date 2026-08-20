# WBC integration twin DCP v2 Stage 5 terminal evidence

evidence_revision: 2026-08-20.1

evidence_status: COMPLETE

program_stage: 5 of 9

owner_acceptance: not requested or claimed

## 1. Result and boundary

Stage 5 is technically `COMPLETE`. The provider-neutral twin adapter, immutable
managed-source lock, break-before-make issuer handoff, deterministic stopped
installation, migration 0084, one exact activation, one exact twin project and
model-free stopped preflight all completed at their reviewed identities.

This record activates only the already-owner-authorized single Stage 6 task
`dcp-v2-twin-canary-v1` after this evidence itself passes exact-head review,
green baseline, zero threads and normal merge. No Stage 6 submit, model Action,
lab merge/deploy, WBC mutation, production action or owner acceptance occurred
while producing this Stage 5 evidence.

## 2. Reviewed authority, source and issuer chain

| Gate | Exact evidence |
| --- | --- |
| Stage 5 authority | DCP PR #249 head `7b65486c7978a7a915be32bf7e69a18ecd9c8174`; review `4983383235`; baseline `32376079493`; merge `4143982eb054a40537d963356c209bfe8447ba31`; tree `f5baefa5aaf730726c8f2692927866b2997be6f7` |
| Provider-neutral adapter | source PR #73 head `52dd43fb5f1dc20178331580a04779797d918559`; review `4984075783`; source/package run `32382795106`; merge `bbd6a6d39d8fa8637d1b9454d0b394b49bc3ef89`; tree `009852349dff327d4d699b0295563d4f3eda21bb` |
| Issuer handoff | lab PR #7 head `3e41678216b71c9709056b3632fa5b3f9070fcb8`; review `4983822635`; baseline `32380292841`; merge/main `375b9b2d0b4c2fce6f2c417850553f79e24a0d92`; tree `1272f6a772ba07eca7bdde5f1da7f53110da183b`; Release Train run `32383551159` |
| Stopped registration correction | source PR #74 head `a5ef4a9119bb2b9941797b9b480d1d90ab20503f`; review `4984304006`; source/package run `32384543145`; merge `c1fc43d74cd517b7d73540f340058fa17b56ef15`; tree `ff51ca2b1f6f9fa502b999f50a366a8e35035421` |
| Immutable source pin | DCP PR #250 head `62c0bcb82d9910ab4894e09491a0b9d6a8101972`; review `4984631131`; baseline `32387348068`; merge `417523963aa3b08a6fb51b2599e6f6a3944d0973`; tree `e20607d625d9baa307f800b45ee1ad4199f250d2` |
| Assertion-resume authority | DCP PR #251 head `d65ffbc8e39f8fc8f7aece98d8d9024bb4d0fbc0`; review `4984967250`; baseline `32390805042`; merge `2c32046149bba97b8796d5f5ebebff96d260d74c`; tree `a5d868eb8daeba7d991ae74d398ca81766582621` |
| Exact lower-camel parser | DCP PR #252 head `837a125ed3bb482351bef2a7d8bfdf875cc2fdeb`; review `4985039918`; baseline run/job `32391613310` / `96498817548`; merge `38f40576dbf246bde6e42ef877c5473bb61fa125`; tree `9cde64e32b162b3d969b340d193bc2d60db1cf48` |

Every PR used an ordinary protected exact-head flow. The relevant reviews had
no findings, every required check was green and every review-thread count was
zero before normal squash merge. Final readback found zero open DCP, source or
lab PRs.

Lab repository ID `1340359100`, owner ID `237411244`, ruleset
`Stage 2 governed main` / `21077248` with no bypass, strict current-head
`baseline`, environment `dcp-wbc-integration-lab-selectel` / `20234191757` and
workflow `Release Train` / `338377713` remain exact. The qualification helper
is absent and the consumed one-time handoff path cannot issue qualification
work. The active issuer is only `dcp/v2`, actor `orenvlad-ai`, event
`repository_dispatch`, type `dcp-admission-v2`. Environment secret presence was
read by name only; no value was read or exposed.

## 3. Preserved failed attempt and bounded correction

The first install's exact quarantine remains backup
`i12-20260820T155118Z`. Its failed-new DB digest is
`10481ec494534c3929771b2db0d1cdc6a17bce61682b7ef9c4b1f34b534063cf`,
schema 84 with one correct activation/project and zero v2 lifecycle rows. The
canonical automatic rollback remained exact at predecessor DB digest
`561e6c624aeb5030b3d69dcba1ab2f39222c2b9dd2af16e58c488ad89f518f9b`,
source/tree `84dbee2a701186628c1ad92950aa14639000fc0b` /
`9374ece6efccf87dcb8a7627c97722a16d063b77` and receipt
`685ae805a61f24f6c7e0628c788e2ad0cfce8d605b65143034296cb212fc757e`.

Failing-first regression initially failed because the exact validator did not
exist. PR #252 then changed only the DCP-owned parser. The canonical complete
lower-camel fixture passes; missing, duplicate, wrong-type, wrong-value,
uppercase-only, invalid-time and foreign-extra fixtures fail closed. Managed
source, migration, issuer, credential and destination identities did not
change.

## 4. Stopped installation and activation

The final pre-install fence proved the canonical app/daemon stopped, port
43231 unoccupied and run file absent. SQLite integrity was `ok`, schema was 83,
DB digest was `561e6c624a...`, WAL was empty with digest `e3b0c442...`, SHM was
32,768 bytes with digest `fd4c9fda...`, and model Actions were 73 total / 0
active. Seven frozen WBC row digests were recorded and later matched exactly.

The single owner-authorized governed install attempt succeeded. Full source,
provenance and absence gates, generated parity, serial Go tests/build,
renderer typecheck and 359 focused renderer tests passed before the atomic
replacement. The installer created backup `i12-20260820T163147Z`; its manifest
digest is `87f2fdb1b9de3ce3663bee9ce9938fcdeeb03148cf9aac67f420bf33eb24e66f`
and its prior DB is the exact `561e6c624a...` predecessor.

The installed facts are:

| Fact | Exact value |
| --- | --- |
| Managed source / tree | `c1fc43d74cd517b7d73540f340058fa17b56ef15` / `ff51ca2b1f6f9fa502b999f50a366a8e35035421` |
| Receipt SHA-256 | `54dd88beef2e9c93ee86435df2645d6707acf2dc3e2c0c0b4dad6de9b40cc9c0` |
| Daemon / app.asar SHA-256 | `9f74f1407bfb963988c9671dffbbb8e171a565b8796d89cf9819f276f46436cf` / `4f8c83c1dbaa24d88bc0f3e44d6ce3d3cc9829b860d4cd514b0b0aa5fb372b7a` |
| Installed / activated UTC | `2026-08-20T16:31:49Z` / `2026-08-20T16:31:51.157325Z` |
| Canonical DB SHA-256 | `da0918196d4c63f571d63feaf00f71c84e27d91498240779590a0ee67700eb86` |
| Integrity / schema | `ok` / `84` |
| Core authority / Stage 5 activation / twin project | `1` / `1` / `1` |
| Task / Revision / Command / Action / Admission / Incident / ExternalEvent / Result | `0 / 0 / 0 / 0 / 0 / 0 / 0 / 0` |
| Predecessor model Actions | `73` total / `0` active |
| Runtime after preflight | stopped; no exact process, listener, run file, WAL or SHM |

The activation binds authority merge `4143982e...`, the exact source/tree and
receipt above, target spec `dcp-wbc-integration-lab/v2`, repository, IDs,
`main`, `baseline`, issuer, workflow, environment, service and
`selectel-systemd/v1`. `preflight-stage5` passed the packaged contour and exact
schema-84 zero-state proof.

## 5. Frozen WBC and persistent-cell invariants

The frozen predecessor remains `wbc-canary-v1` / card 1 / `wb-core-1` / task
revision 23 / PR #987 head `26044c696651ce5873748ec3f920d40e77c5686c` /
review `18c54338-df31-4471-a344-4db6648ff4e3` / admission sequence 32 in
`waiting`. PR #987 remains open with unchanged labels and green `baseline`.
The task, session, PR, review run, admission, readmission-generation set and
task-first recovery row digests are byte-identical before and after migration.

Fresh read-only Selectel proof found exact DMI UUID
`96be74db-785f-4653-85a8-a4e7c1d3ccdf`, active/enabled service with 50% CPU,
512 MiB memory, 64 tasks and 1024 open-file limits, and only
`127.0.0.1:18321`. Health is `ok`; provenance and current release remain
`157ae90edb0891506639b845deac141f75189ec7`, artifact
`55569381f6579efe98ba75f553822a85597d7dd6c5379c07f58ce223f5fa88f7`.
Previous is exact `cd6aa715f9c9ebeeccb676001021f0fe89fc0945`, release count is two,
incoming count zero and root free space 33,341,145,088 bytes.

Protected Luchiki remained HTTPS 200 with nginx active, timer active/waiting,
unit hashes `61973e6a6d4807463e01ad748dde7032cf6cb74a958102b0b22791dff72ca4b6` /
`35d44a10865180aea9cdc604eff44ec3adee8a43ea7238269de3f52311927426`
and certificate fingerprint
`4D:19:EA:99:27:C6:BB:BF:5E:68:24:9E:00:DD:C3:33:4B:86:8F:7F:9C:39:AC:CB:92:3C:E2:F8:DD:B5:36:39`.
No Luchiki trigger, repair or content read occurred. The retired collector path
is absent, named legacy services/timers remain inactive/disabled, and retained
container/volume evidence remains exited/present. No new Selectel resource,
shared OS/network/firewall, WBC or production change occurred.

## 6. Safe handoff

At this evidence head, Stage 6 has not started. After this exact evidence
merges and final `main` readback succeeds, the only eligible submit is the one
idempotent `dcp-v2-twin-canary-v1` Task through the installed canonical DCP
gateway. Stage 7 remains prohibited until the separately required curator
read-only verification after the Stage 6 checkpoint.

Effective route remained approval policy `never`, unrestricted filesystem,
network enabled, separate worktree ready and platform approval count 0. No
subagent, fork, monitor, nested executor or parallel DCP task was created.
