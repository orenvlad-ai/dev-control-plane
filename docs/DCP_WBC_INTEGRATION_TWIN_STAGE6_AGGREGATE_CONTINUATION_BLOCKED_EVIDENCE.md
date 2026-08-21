# Stage 6 aggregate continuation blocked evidence

evidence_revision: 2026-08-21.1

technical_status: BLOCKED after the one governed aggregate installation and one same-identity start

owner_acceptance: not requested or synthesized

This document is immutable terminal evidence for the bounded Stage 6 aggregate
source-to-install-to-live continuation. It records observed facts only. It adds
no correction, reinstall, restart, submit, provider, Stage 7, WBC, production
or cutover authority.

## 1. Qualified executor and duplicate guards

- visible task `01a02392-c430-7a11-a081-5de18a278f46`, title
  `DCP · S6 seam · И33`, ran on the qualified local host with
  `approval_policy=never`, unrestricted filesystem, network enabled and zero
  platform approval prompts;
- Codex app `26.818.21641` build `6849`, bundled runner
  `0.148.0-alpha.21`, PATH CLI `0.145.0`, Git `2.50.1`, GitHub CLI `2.87.2`,
  Go `1.26.5`, Node `25.9.0`, npm `11.12.1` and Python `3.13.1` were
  machine-read before the phase;
- the executor used one separate clean `dev-control-plane` worktree and the
  existing clean managed-source aggregate worktree; no collaboration subagent,
  fork, nested executor, monitor or platform approval was created;
- fresh GitHub readback found zero open PRs in `dev-control-plane`,
  `dcp-orchestrator` and `dcp-wbc-integration-lab` before the evidence package,
  and no remote canary branch or overlapping aggregate package.

## 2. Reviewed aggregate source

Managed-source PR #76 published exactly one aggregate package:

- base `11401ff6eadb80fd87e48229fb8c5458095a63b1`, tree
  `91bf6e25ec1b0e0f971ad36f7b80272aded2482c`;
- package head `b0c2b6df76adf205229e49c48a1d7277aa7b5059`, tree
  `a6e3c3347bbbddd256e9edbfc541f115813249d2`;
- exact-head workflow `32477135149`: `package` and `source` succeeded;
- context-free semantic/security review `4992765757`: no finding and zero
  unresolved threads;
- normal merge `d084ae3cf0cb3e5e32ebefa197031c24a2b6392d`, tree
  `a6e3c3347bbbddd256e9edbfc541f115813249d2`.

The model-free package tests covered the two proven prompt/projection defects,
same-identity adoption, lifecycle truth, result dedupe/contradiction, immutable
successor Revision, CI/review/Admission/Release projections, restart fences,
drift, conflicts and zero duplicate model/provider effects. Source publication
made no installed, SQLite, target-provider or production mutation.

## 3. Reviewed pin and one installation

`dev-control-plane` PR #257 published the one-time aggregate install authority:

- base `2114fbd967959af5e7b5aaa5ac44a9b28d55adca`;
- exact head `747cda40e2a8816c4fdf8940c302e1374bfc2138`, tree
  `4a2c2808b5edd1e029bf0992abedcf78c02f7c39`;
- exact-head baseline `32479309952` succeeded;
- context-free semantic/security review `4992960012` found no issue and left
  zero unresolved threads;
- normal merge `085c23a0c1b43654b6885cea75209a70f1a18b68`, tree
  `4a2c2808b5edd1e029bf0992abedcf78c02f7c39`.

The fresh and locked preflights proved the accepted predecessor source/tree
`11401ff6eadb80fd87e48229fb8c5458095a63b1` /
`91bf6e25ec1b0e0f971ad36f7b80272aded2482c`, receipt SHA-256
`098056d800d41f666708b7697d6ccef9f3b5cd2e077a939d89dcf0b1f35767e2`,
schema `85`, the sole exact v2/native identity, zero active model and zero
target/WBC provider effect. The installer then ran exactly once. It created
recoverable backup `i12-20260821T120041Z`, installed only merged source/tree
`d084ae3cf0cb3e5e32ebefa197031c24a2b6392d` /
`a6e3c3347bbbddd256e9edbfc541f115813249d2`, and produced receipt SHA-256
`19550a9f02b14f13be8a80214529025fd6d4fe7dc8e5bd12c5eaa1a47dd54b0c`.
The stopped post-install preflight preserved schema `85`, all identities and
Task/Revision/Command/Action `1/1/1/1` with Admission/Incident/ExternalEvent/
Result `0/0/0/0`. No migration, direct SQLite write, blind kill, rollback,
retry or second installation occurred.

## 4. Same-identity continuation and exact blocker

The governed gateway started the exact installed app once. It adopted the
already leased Command and queued native Action without submit or replacement:

| Layer | Observed fact |
| --- | --- |
| Task | `dcp-v2-twin-canary-v1`, still `worker_queued`, state revision `1` |
| Revision | `v2-13f81f321f99d1117dc931419e0bea3945ee35a5`; no successor Revision |
| Command | `v2-e028f779a18417e990911057f7db7c666f7487ca`, still `leased`, effect fence `model:v2-40f87d048813533daa1108b4316c09139acf0a8f` |
| DCP-v2 Action | `v2-40f87d048813533daa1108b4316c09139acf0a8f`, `running`, slot `1`, runtime `78535564-a2bc-478c-80b0-207753f2152c` |
| Native Action | sequence `74`, `dcp-model-dcp-v2-twin-canary-v1-worker-1`, `succeeded`, slot `0`, same launch id |
| Native session/task | session idle with no runtime launch id; policy task `ci_waiting`, revision `4` |

The one Worker produced local commit
`bebbf8f617f1a6fa0b9e91698fe710fe0a2bad2c`, tree
`2fda4cae71976fd701bf3a9ccca4031f7afb630d`, on the canonical native branch.
It added only `docs/STAGE6_CANARY.md` with the required single synthetic line.
No remote branch or PR was created.

At `2026-08-21T12:02:34Z`, the native Action durably succeeded, released its
slot and the session became idle. A fresh read after that terminal native fact
still showed the DCP-v2 Action as `running` with the runtime id and slot `1`,
while the DCP-v2 Task remained `worker_queued`. Counts remained v2
Task/Revision/Command/Action `1/1/1/1`, downstream `0/0/0/0`, and native active
model Actions `0`.

This is an unambiguous false terminal runtime/model projection after the only
authorized aggregate installation. It triggers the contract's mandatory hard
stop. Stage 6 is therefore technically `BLOCKED`. No corrective source change,
provider publication, restart, retry, reinstall or substitute identity is
authorized. The legacy second-authority bridge must be simplified or removed
under a separately owner-authorized architecture/source phase before another
live attempt.

## 5. Provider and protected-surface proof

The integration lab remained at main
`375b9b2d0b4c2fce6f2c417850553f79e24a0d92`, tree
`1272f6a772ba07eca7bdde5f1da7f53110da183b`. Fresh provider readback found no
canary remote branch, PR, check, review, Admission manifest, Release Train run,
merge, artifact, deploy or Result. There was exactly one canary Worker model
Action and no Reviewer, repair, arbiter or duplicate provider/model effect.

WBC PR #987 remained open at
`26044c696651ce5873748ec3f920d40e77c5686c`, `BEHIND`, with no release label.
No WBC, production, credential, business-data, Selectel, Luchiki, SSH,
service-manager or co-tenant mutation occurred. Stage 7, WBC shadow and cutover
remain `NOT STARTED`. Technical evidence does not imply owner acceptance.

Current authority remains the
[program manifest](DCP_WBC_INTEGRATION_TWIN_CURRENT_PROGRAM_MANIFEST.md).
