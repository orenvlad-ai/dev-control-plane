# WBC integration twin Stage 2 terminal evidence

evidence_status: `COMPLETE`

date: 2026-08-20

program_stage: 2 of 9

owner_acceptance: not requested or synthesized

## 1. Terminal result

Stage 2 is technically `COMPLETE`. Exact public repository
`orenvlad-ai/dcp-wbc-integration-lab` now owns one protected mechanical Release
Train, one qualification-only issuer, one inert target and one persistent
Selectel adapter. The bounded smoke used one ordinary ready PR, one current-head
`baseline`, one fresh context-free no-findings review, one exact Admission
manifest, one Actions-owned merge, one immutable artifact and one real
persistent install/start/probe on the exact pre-existing Selectel server.

This completion creates no DCP Task, Revision, Command, Action or Admission,
does not touch the installed DCP application or live SQLite, and does not
continue WBC PR #987. It is not owner acceptance.

The owner-approved forward program is separately frozen in
[the combined Stage 3 to Stage 4 contract](DCP_WBC_INTEGRATION_TWIN_STAGE3_4_COMBINED_EXECUTION_CONTRACT.md).
Stage 3 is the next active gate. Stage 4 source work remains inactive until an
ordinary merged Stage 3 terminal-evidence/activation PR records every fixed
independent case green.

## 2. Authority and route

The Stage 2 authority PR was dev-control-plane PR #245:

- exact head `a0a0945619bc7a3d8c207d1f5c229247d12a2052`;
- context-free semantic/security review
  `PRR_kwDOSUqHmc8AAAABKM7n3g`, no findings;
- exact-head `baseline` run `32338651891`, job `96333082597`, successful;
- zero review threads;
- ordinary merge `86dfdb0f66889494219da7fc60351c5cee38660d`.

The direct executor routing record for this closure is:

- curator task `01a00e22-ae1e-7ef2-8db1-36a473434cbb`;
- executor task `01a01e7c-d1a9-7233-a358-481a0f98397c`;
- Codex app `26.707.41301` build `5103` and Codex CLI `0.145.0`;
- effective `approval_policy=never`, unrestricted filesystem, network enabled,
  separate worktree and platform approval count `0`;
- zero collaboration subagents, forks, monitors or nested executors.

Fresh GitHub readback found zero open dev-control-plane PRs and zero open
dcp-orchestrator PRs before this closure branch was published.

## 3. Repository identity and protection

The exact lab repository readback is:

| Fact | Exact value |
| --- | --- |
| Repository / owner ID | `1340359100` / `237411244` |
| Visibility / default branch | public / `main` |
| Sole bootstrap | `d5455175a3798a382796003fd6053e8b6b7c1534` |
| Current main / tree | `ec23bcbd8a5282a4566307d1a308061094ef839c` / `f1172755a20d543fe87ae4da67f51f41bda0b386` |
| Ruleset | `Stage 2 governed main`, ID `21077248`, active, no bypass |
| Environment | `dcp-wbc-integration-lab-selectel`, ID `20234191757` |
| Required check | strict current `baseline` |

Ruleset `21077248` applies to the default branch and requires an up-to-date
`baseline`, an ordinary pull request, thread resolution and squash-only merge.
Deletion and non-fast-forward updates are blocked. `current_user_can_bypass`
is `never`. The environment accepts protected branches only.

Repository Actions secrets are empty. The environment contains exactly secret
names `DCP_WBC_LAB_KNOWN_HOSTS` and `DCP_WBC_LAB_SSH_KEY`; values were never
read or printed. Its only variables are host `178.72.152.177` and account
`dcp-wbc-lab`. `target-spec.json` pins issuer `qualification/v1` to actor
`orenvlad-ai` and event `workflow_dispatch`; `dcp_issuer` is `off`. No second
issuer, DCP label or DCP database fact participates.

## 4. Exact smoke and immutable proof

Lab PR #1 used:

- base `d5455175a3798a382796003fd6053e8b6b7c1534`;
- corrected exact head `5030236a22168c2bdc525b62985bda2c11888f76`;
- fresh review `PRR_kwDOT-RBvM8AAAABKNIaKA` / numeric ID `4979825192`,
  no findings for that head;
- successful `baseline` run `32341023840`, job/check `96339996893`;
- zero unresolved review threads;
- Actions-owned squash merge
  `ec23bcbd8a5282a4566307d1a308061094ef839c`.

Release Train run `32341176639`, job `96340438173`, used manifest digest
`af73cd04167a94ccb96b9ad257c023d51a7830d6993eae2a62cc254fb6985a58`.
It merged the exact admitted head, built artifact digest
`c5c18e63304ab9f4ba3fd244ab780e91fd7d7b49540a24b296dbc9d2ea0f0fe7`,
installed it and published artifact ID `9396402262`, retained until
2026-11-18. The canonical deployment proof digest is
`b96b837e5a1d3ba9575767097e9c8a49e8d54a228bf67f77715f0d5e3270954c`.
Independent canonical-JSON recomputation matched both manifest and proof
digests byte-for-byte.

The proof binds merge, artifact source and deployed SHA all to
`ec23bcbd8a5282a4566307d1a308061094ef839c`; environment and service are
`dcp-wbc-integration-lab-selectel` / `dcp-wbc-integration-lab`. Health,
provenance and post-job forced-SSH readback are all successful. Merge without
this proof would not be terminal.

## 5. Persistent Selectel cell

One persistent read-only SSH ControlMaster session proved:

- DMI and cloud-metadata UUID
  `96be74db-785f-4653-85a8-a4e7c1d3ccdf`;
- project `771c31e1970c4cf7a836c07f398661ce`, placement `ru-3b`, private address
  `192.168.0.161` and public route `178.72.152.177`;
- Ubuntu 24.04, 2 vCPU, 4 GiB memory and 40 GiB root disk;
- unprivileged account/root `dcp-wbc-lab` / `/opt/dcp-wbc-integration-lab`;
- exact listener `127.0.0.1:18321` and zero non-loopback listener on that port;
- active hardened user service with CPU quota 50%, memory maximum 512 MiB,
  tasks maximum 64 and open-file limit 1024;
- one retained release, no incomplete incoming release and no previous release;
- current build SHA `ec23bcbd8a5282a4566307d1a308061094ef839c`, artifact digest
  `c5c18e63304ab9f4ba3fd244ab780e91fd7d7b49540a24b296dbc9d2ea0f0fe7`
  and the same manifest digest as the immutable proof; and
- 33,406,214,144 free root bytes at closure.

The root-owned forced command `/usr/local/sbin/dcp-wbc-lab-deploy` has mode
`0755` and SHA-256
`52931a6b51636639c06a32ae3ad6183a5fa612fc50dfb4fc49c303d637c981d7`,
equal to reviewed repository source. The one authorized key is mode `0600` and
uses `restrict,command=...`; its key bytes were redacted. The installed unit
SHA-256 `402be6e8822d2f7405f95a32db0e53e8f2161b6dcb73f94c8c665b196e69da9c`
also equals reviewed source.

Cloud metadata and current host identity prove reuse of the contract-pinned
existing paid server. This pass issued no Selectel create, resize, rebuild,
snapshot, disk, IP, load-balancer, network or billing mutation. The zero-new-
paid-resource statement is about this program's bounded delta; it does not
claim that the Selectel project contains no other historical resource.

## 6. Protected co-tenant

No protected path, unit, nginx/TLS surface or timer was written, restarted or
triggered by this closure. Current readback proved:

- HTTPS 200 with TLS verification result 0;
- active nginx with only the existing public 80/443 bindings;
- certificate SHA-256 fingerprint
  `4D:19:EA:99:27:C6:BB:BF:5E:68:24:9E:00:DD:C3:33:4B:86:8F:7F:9C:39:AC:CB:92:3C:E2:F8:DD:B5:36:39`
  and expiry 2026-09-19;
- active/waiting `luchiki-counter.timer`;
- unchanged timer/service hashes
  `61973e6a6d4807463e01ad748dde7032cf6cb74a958102b0b22791dff72ca4b6` /
  `35d44a10865180aea9cdc604eff44ec3adee8a43ea7238269de3f52311927426`;
- current static metadata digest, excluding exact timer-owned `app/data`,
  `6ac398928975915283c2b2c713a0933d81e1cf7e00c926352a4936ff6a436a50`;
- timer-owned dynamic subtree 934 entries / 41,550 bytes / 931 zero-byte files.

The pre-cleanup counter exit-code failure remains preserved in the Stage 2
authority evidence and was not repaired or hidden. At this fresh readback the
ordinary timer's 09:00 UTC invocation had naturally completed with result
`success` after disk recovery. Recording that current state does not rewrite
the earlier failure, attribute a repair to this executor or synthesize a new
failure.

## 7. Literal legacy retirement result

The permanent exact deletion target
`/opt/wb-core-runtime/state/promo_xlsx_collector_runs` is absent. Its deleted
35,050,256,255 bytes have no recovery promise.

All legacy producers are retired: zero matching processes, zero root crontab
entries, zero listeners on 8000/8765, both named application services inactive
and disabled, and both named timers inactive and disabled. Paired one-shot
services retain their historical failed/static state without a running process.

The following non-producing rollback remnants are deliberately retained and
reported literally:

| Surface | Current fact |
| --- | --- |
| `/opt/wb-core-runtime` | retained directory, 359,188,746 bytes |
| `/opt/wb-ai` | retained directory, 162,012,805 bytes |
| `/opt/wb-ai-repo` | retained directory, 81,282 bytes |
| `/opt/wb-web-bot` | retained directory, 167,126,221 bytes |
| `wb_ai_postgres` | retained container, exited for five weeks |
| `wb-ai_pgdata` | retained local volume |
| `wb-ai` nginx site files | retained, no legacy listener |

None is a lab dependency or rollback target. Retention is safer than guessing
at further destructive cleanup and is permitted by the Stage 2 classification
contract.

## 8. Safe completion boundary

The lab checkout is clean at exact main. dev-control-plane and managed-source
had no conflicting open PR at entry. The installed DCP app/daemon/SQLite,
schema-83 blocker, WBC repository and PR #987 were not inspected through live
runtime surfaces or mutated. No DCP submit, twin row, model call, WBC write,
production write, new paid resource, owner-acceptance statement or platform
approval occurred.

Stage 2 closure is therefore technical `COMPLETE`. Stage 3 may start only from
this exact merged record and current lab main; any identity, protection,
issuer, credential, host, co-tenant or deployment drift stops before the
qualification matrix.
