# Stage 6 direct-model stable install complete evidence

evidence_revision: 2026-08-22.2

technical_status: COMPLETE for exact pin, one governed migration/install and stopped preflight; Stage 6 adoption/live continuation remains BLOCKED

owner_acceptance: not requested or synthesized

Current stage and next-boundary truth remains in the
[current program manifest](DCP_WBC_INTEGRATION_TWIN_CURRENT_PROGRAM_MANIFEST.md).
This document is immutable evidence of the bounded stopped install only.

## 1. Exact bounded result

The owner-authorized source pin/install phase completed without starting the
new application. Managed source PR #77 merge
`e9eb18a99db71813ac8c4556a614d6a3ce4108aa`, tree
`b4db2b329accc9a93691bda7c306cc864b07ee56`, was built from one permanent
standalone clone, archived and installed once through the repository-owned
guard. Migration `0086_dcp_v2_direct_model_authority.sql` was applied exactly
once. The final application, daemon and database remain stopped.

No Worker adoption, successor Revision, `publication.execute/v1`, start,
model/provider call or target effect occurred. This evidence grants no later
mutation.

## 2. Routing and incident closure

The sole visible executor was task
`01a02392-c430-7a11-a081-5de18a278f46`, titled
`DCP · S6 stable restore/install · И33`, pinned on the local host. Its effective
profile was `approval_policy=never`, unrestricted filesystem, network enabled,
a separate clean control-plane worktree and platform approval count `0`.
Codex app `26.707.41301`, bundled runner `0.144.0-alpha.4`, PATH runner
`0.145.0`, Git `2.50.1`, GitHub CLI `2.87.2`, Go `1.26.5`, Node `25.9.0`, npm
`11.12.1` and Python `3.13.1` were machine-read.

`MANAGED_SOURCE_WORKTREE_DRIFT` is closed as a source-integrity incident with
zero live or provider effect. The vanished task-worktree source was never
recovered, deleted or used. The replacement is a clean, detached, non-symlink
standalone repository in the permanent-project path class with its own `.git`,
one exact public `origin`, PR #77 commit/tree and stable filesystem identity.
No absolute local path is part of public evidence.

The merged guard now rejects task worktrees, temporary roots, symlinks, linked
Git metadata, wrong remotes, dirty or wrong source, filesystem-identity drift,
disappearance before staging, staged digest mismatch and equal invocation. A
verified source archive and application package are complete before stop;
installation subsequently depends only on those staged bytes.

## 3. Authority PR

The single authority/install PR was `orenvlad-ai/dev-control-plane` #261:

| Fact | Exact value |
| --- | --- |
| base | `b62bafc3308795d74aa063927b2ec031478586d6` |
| final head | `37fb9420fdd3d8fb25606012941c1c1b3c4678a4` |
| final tree | `d7609aa9cbfc5575279ea36c48e8b5de3b710dc4` |
| baseline | workflow `32519332471`, job `96887899411`, success |
| fresh semantic/security review | `4996761109`, exact final head, no findings |
| unresolved review threads | `0` |
| merge | `74b421ccf2eefcbd80e3716935056874f38509f5` |
| merge tree | `d7609aa9cbfc5575279ea36c48e8b5de3b710dc4` |

The one findings-repair round corrected historical lock assertions and Linux
fixture portability. Any head replacement invalidated prior checks/review; the
table records only the final exact-head check and fresh review.

## 4. Staged and recovery evidence

One backup, one installer invocation and one migration were recorded under
install identity `stage6-direct-model-e9eb18a99db-85-to-86-v1`. The backup id
is `stage6-direct-model-e9eb18a99db-85-to-86-v1-20260821T193924Z`; no local
absolute path is published.

| Evidence | SHA-256 / state |
| --- | --- |
| source archive | `7e4d4f65e7ba05080f476641dce15fd49338f4fcbcedec3ce5c06168a9b3d75d` |
| frozen Worker archive | `70604506cfd1daa6fcb9d5910c800be65af857129c0fbf8f12f5f9d4b2959cb9` |
| signed arm64 artifact archive | `daa766bdc41da8455a6804cd3fcc5d0d5b3e5454da00dd8cdb4dc7060802cce4` |
| staged daemon | `4ad17df6bbfbf95a08ac9e8af0176025b0afa595b01c36135e1a423d322e1c25` |
| staged renderer | `4f8c83c1dbaa24d88bc0f3e44d6ce3d3cc9829b860d4cd514b0b0aa5fb372b7a` |
| predecessor database | `e74bb1529dff227ca359773fd30ea308c1a4e55fbd6fab97872c0206e59c3227` |
| predecessor WAL / SHM | absent after the reviewed graceful stop |
| predecessor receipt | `19550a9f02b14f13be8a80214529025fd6d4fe7dc8e5bd12c5eaa1a47dd54b0c` |
| predecessor allowlist config | `eff850cd70b8c18ae903e5647710b04997b1f56712d53510e4aa752a113a4909` |
| unconsumed adoption input | `1e3fdd63457d2c1bfdb1a64c647c56b5d75c5d7260de91b033a93e22a82f7f09` |
| installed receipt | `fc8f2a2f6264dc1a3e817e42f124bdbd7040a412eade3fcddf97762f59f214d8` |

Counts are backup `1`, install invocation `1`, migration `1`, rollback `0`.
The predecessor app/state/data remain recoverable. No reinstall or retry was
performed.

## 5. Stopped machine readback

The repository-owned stopped preflight returned source/tree PR #77 exact,
receipt `fc8f2a2f6264dc1a3e817e42f124bdbd7040a412eade3fcddf97762f59f214d8`,
database schema `86`, `appStopped=true` and `adoptionConsumed=false`.
Independent immutable SQLite readback proved `integrity_check=ok`, zero foreign
key violations and one applied version `86` row.

The same frozen identity remains:

- Task `dcp-v2-twin-canary-v1`, `worker_queued`, state revision `1`;
- Revision `v2-13f81f321f99d1117dc931419e0bea3945ee35a5`;
- Command `v2-e028f779a18417e990911057f7db7c666f7487ca`, still `leased`;
- Action `v2-40f87d048813533daa1108b4316c09139acf0a8f`, preserved historical
  `running`, slot `1`, runtime `78535564-a2bc-478c-80b0-207753f2152c`;
- v2 Task/Revision/Command/Action `1/1/1/1`, downstream
  Admission/Incident/ExternalEvent/Result `0/0/0/0`;
- direct model-runtime/terminal-receipt/one-time-adoption rows `0/0/0`;
- native Action sequence `74` succeeded, slot `0`; session
  `dcp-wbc-integration-lab-1` idle with no runtime launch id and zero active
  legacy model Actions;
- local Worker commit `bebbf8f617f1a6fa0b9e91698fe710fe0a2bad2c`, tree
  `2fda4cae71976fd701bf3a9ccca4031f7afb630d`, unchanged and locally
  recoverable.

The preserved DCP-v2 `running` row is historical frozen adoption input, not a
claim that a process is alive. The stopped preflight proved no matching app,
daemon or model runtime process.

## 6. Zero effects and next boundary

Fresh GitHub and local fences proved no canary remote branch or PR, CI, review,
Admission, Release Train, merge, artifact, deploy or Result. No target,
provider, WBC PR #987, Selectel/Luchiki, production, credential or business-data
effect occurred. The stable managed source remained clean at PR #77 merge.

Stage 6 remains technically `BLOCKED`, now at a safer stopped schema-86
checkpoint. The next possible phase requires new owner authority for exact
read-only revalidation of the digest-bound adoption input, atomic same-identity
adoption and any governed start/live continuation. It may not resubmit, rerun
the Worker, publish the local commit manually or infer Stage 7 authority.
Stage 7, WBC shadow and cutover remain not started.

Technical completion of this pin/install phase does not constitute owner
acceptance.
