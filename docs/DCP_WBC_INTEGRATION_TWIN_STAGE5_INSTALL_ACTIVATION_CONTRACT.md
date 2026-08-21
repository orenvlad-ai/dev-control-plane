# WBC integration twin DCP v2 Stage 5 install and activation contract

contract_revision: 2026-08-20.4

contract_status: owner-authorized Stage 5 authority; technical completion
recorded in separate terminal evidence; Stage 6 remains evidence-merge gated

program_stage: 5 of 9

stage6_task_id: `dcp-v2-twin-canary-v1`

owner_acceptance: not requested or synthesized

current_program_role: historical-complete Stage 5 authority; no current install or submit authority

See the [current program manifest](DCP_WBC_INTEGRATION_TWIN_CURRENT_PROGRAM_MANIFEST.md).
The source/install/submit permissions below are spent historical authority.

## 1. Authority and terminal boundary

This contract activates one bounded Stage 5 pass after the independently
reviewed and merged Stage 4 source-complete evidence. Stage 5 may add the one
missing provider-neutral integration-twin adapter, switch the exact lab issuer,
pin and deterministically install the reviewed source, apply forward schema and
activation facts, register only the twin, and finish with a stopped model-free
preflight.

Stage 5 creates no integration-twin Task, Revision, Command, Action, Admission
or Result and performs no model call. The first and only Stage 6 submit is a
separate later gate in the same owner-authorized executor pass. This contract
does not authorize Stage 7 qualification, Stage 8 WBC shadow, Stage 9 cutover,
WBC PR #987 mutation, production, Luchiki mutation or owner acceptance.

The source, lab, issuer, pin, installation and evidence gates below do not
collapse. A failed or unmerged gate cannot be treated as authority for its
successor.

## 2. Exact selected inputs

The Stage 4 managed-source input is exact public
`orenvlad-ai/dcp-orchestrator`, repository/owner IDs
`1327984104` / `237411244`, main merge
`bcb512239cbc14788f8fe59ece1ba33cbcb18c1f` and tree
`2a894de8af6e73eabd11bd8d80dc0ed31812930b`. That merge is the required
official-ancestry base for one bounded adapter implementation PR. It is not the
final installed source lock if that PR changes source.

The exact destination is:

| Fact | Pinned value |
| --- | --- |
| Repository / owner ID | `1340359100` / `237411244` |
| Repository / base | `orenvlad-ai/dcp-wbc-integration-lab` / `main` |
| Stage 5 entry main / tree | `157ae90edb0891506639b845deac141f75189ec7` / `322dc03813a18cf91c9bf015e4c88a0c608472c3` |
| Ruleset | `Stage 2 governed main`, ID `21077248`, active, no bypass |
| Required check | strict current-head `baseline` |
| Environment | `dcp-wbc-integration-lab-selectel`, ID `20234191757` |
| Selectel server | `96be74db-785f-4653-85a8-a4e7c1d3ccdf` |
| Account / root | `dcp-wbc-lab` / `/opt/dcp-wbc-integration-lab` |
| Service / listener | `dcp-wbc-integration-lab` / `127.0.0.1:18321` |
| Adapter | `selectel-systemd/v1` |
| Retention | 90-day proof artifacts; exactly two host releases |

Entry readback must prove zero conflicting open DCP, managed-source and lab
pull requests, exact repository/provider identities, the unchanged Stage 3
last-known-good deployment and the protected Selectel/Luchiki boundary.

## 3. Bounded managed-source adapter

The Stage 4 ports remain provider-neutral. One reviewed managed-source PR may
add only the missing concrete adapter and activation wiring required for the
exact twin:

- exact GitHub repository, base, PR, head and configured required-check reads;
- expected-old-head mechanical readmission for the same branch and PR only;
- canonical `dcp-release-manifest/v1` construction and digest validation from
  the durable Task, Revision, review and FIFO Admission;
- one GitHub `repository_dispatch` release handoff with an immutable external
  idempotency/effect fence;
- bounded one-shot import and verification of repository-owned
  readmission/merge/deployment proofs; and
- the existing bounded Worker/Reviewer/repair Action path wired to the DCP v2
  Command/Action records without a second scheduler, state authority or model
  loop.

The exact active target tuple is `dcp-wbc-integration-lab` / `live-runtime` /
`orenvlad-ai/dcp-wbc-integration-lab`, repository/owner IDs above, base `main`,
required check `baseline`, target spec `dcp-wbc-integration-lab/v2`, maximum
readmission generations `2`, one initial worker, one shared repair allowance
and at most three globally active model Actions.

The adapter exposes no direct merge, install, start, restart or redeploy
operation. GitHub Actions remains the sole physical Release Train, merge,
artifact and Selectel deploy actor. A bounded observer imports an immutable
proof; it does not infer success from a green workflow or poll it periodically.
Provider reads occur only for submit validation, an exact durable Command,
startup reconciliation, one concrete provider event or an explicitly
authorized bounded observation.

There is no WBC, current-canary or production special case. Existing WBC and
historical adapters remain behaviorally unchanged. Models receive no GitHub
write/deploy credential, SSH, secret, DCP mutation route, production surface or
business data.

The exact adapter head must pass official ancestry/provenance, source/package
CI, generated parity, serial tests/build/vet, applicable race and renderer/
accessibility suites, security/absence gates, exact-head context-free
semantic/security review with no findings and zero threads before ordinary
merge. A separate DCP pin/install-guard PR then locks only the exact merged
source commit and tree.

## 4. Break-before-make issuer handoff

The Stage 3 qualification issuer is
`qualification/v1` / actor `orenvlad-ai` / event `workflow_dispatch`. The Stage
5 DCP issuer is exactly `dcp/v2` / actor `orenvlad-ai` / event
`repository_dispatch` / event type `dcp-admission-v2`. The repository-owned
Release Train workflow identity remains ID `338377713`.

The active main history and GitHub workflow state must prove this order:

1. Complete every Stage 3 qualification fact and prepare the reviewed DCP seam
   without dispatching it.
2. Disable the qualification issuer and prove a new qualification dispatch
   cannot start. Its manifest helper and `workflow_dispatch` input are absent
   or fail closed, and the Release Train workflow is disabled during the
   transition proof.
3. Only after that proof, enable the exact repository-owned DCP event seam on
   protected main and read back its actor/event/type/target-spec bindings.
4. Prove that copied, PR-authored, label-authored, foreign-actor, manual
   workflow-input and qualification manifests remain ineligible.

No point may accept both issuer kinds. An Actions run already dispatched before
the disable fence must be absent or terminal before the handoff; ambiguity
stops. Workflow enable/disable is configuration state, not permission to bypass
the protected PR or exact manifest gates.

The DCP adapter may use only the already-authorized local GitHub transport for
this exact public repository dispatch. The Selectel credential remains solely
inside the exact lab environment and forced-command boundary. No credential
value is read, printed, copied or delivered to a model. A need for a new token,
actor, repository, environment secret or credential purpose is a terminal
scope blocker.

## 5. Stopped installation fence

Before any installed mutation the canonical DCP application and daemon must be
proven stopped with no listener on `127.0.0.1:43231`, no run-file ambiguity,
no active worker/reviewer/repair/arbiter process and zero globally active model
Actions. The exact app/bundle/daemon path, hashes, source/tree/receipt and
rollback target are recorded.

Read-only SQLite proof must bind integrity `ok`, schema `83`, database and
applicable sidecar digests, row counts and the frozen predecessor:
`wbc-canary-v1` / card `1` / `wb-core-1` / PR #987 head
`26044c696651ce5873748ec3f920d40e77c5686c` / review
`18c54338-df31-4471-a344-4db6648ff4e3` / admission `32` / task revision `23` /
`73` total and `0` active model Actions / blocker
`task_first_startup_admission_continuation_missing`. Stage 5 may not drain,
repair, re-arm, reinterpret or continue it.

The same pre-mutation fence records lab main/deployed SHA, current/previous
release count, service health/provenance, exact Selectel identity and free
space plus Luchiki HTTPS/nginx/timer/unit/certificate and protected-tree
invariants. It neither repairs nor triggers Luchiki.

## 6. Forward activation and registration

The repository-owned deterministic installer builds only the exact reviewed
source lock and leaves the canonical app stopped. It creates an exact verified
backup and receipt, applies migration `0084_dcp_v2_core.sql` once, and records
one additive immutable Stage 5 activation fact. Migration 0084 and its
`adapter_activated=0`, `installed=0` Stage 4 row remain byte-for-byte immutable;
Stage 5 activation is a separate forward record and never rewrites merged
schema or predecessor history.

Only the exact twin target/profile may be registered. The activation record
binds the Stage 5 DCP authority merge, final managed-source merge/tree, installed
receipt, target spec/version/digest, repository/owner/base/check, issuer,
workflow, environment/service/adapter and activation timestamp. Conflicting or
duplicate activation fails closed. Registration creates zero twin Task,
Revision, Command, Action, Admission, Incident and Result rows.

Migration and installer tests use disposable exact schema-83 copies before the
live stopped pass. They prove forward-only preservation, rollback, foreign-key
integrity, unchanged historical row digests and absence of a predecessor wake.
The live database is never copied back from a test and is not opened writable
until the exact stopped installer crosses its migration fence.

## 7. Stopped model-free preflight

Stage 5 preflight is green only when it proves:

- exact installed source/tree, receipt, bundle identity, executable/daemon
  hashes, signature, provenance and absence gates;
- schema `84`, the immutable Stage 4 row and exactly one matching Stage 5
  activation record;
- adapter activation only for the exact twin and no WBC/live-production
  activation;
- qualification issuer disabled and unable to dispatch, with only the exact
  DCP issuer enabled and effective;
- exact target/provider/repository/base/check/workflow/environment/service/
  adapter identities and manifest/proof schemas;
- zero twin Task, Revision, Command, Action, Admission, Incident and Result
  rows; zero active model Actions globally;
- the frozen schema-83/WBC predecessor remains identical in every preserved
  field and PR #987 is unchanged;
- no DCP app/daemon process, run file or listener remains after preflight;
- lab service health/provenance/deployed SHA and two-release retention are
  unchanged from the Stage 3 last-known-good state; and
- Selectel/Luchiki/shared-host, paid-resource, WBC and production boundaries
  remain unchanged.

One bounded correction is allowed only for a newly proven packaging or
integration assertion defect. A second defect class, architecture change,
credential/destination decision or protected-surface drift stops Stage 5
`BLOCKED` with all evidence preserved.

## 8. Stage 5 completion and Stage 6 gate

Stage 5 is technically `COMPLETE` only after one ordinary reviewed/green DCP
terminal-evidence PR records the authority PR, optional adapter PR, exact pin,
issuer handoff, installation receipt, schema/activation facts, stopped
preflight and all invariant readbacks. It must merge normally and be read back
on final main.

Only that merged Stage 5 evidence activates the one Stage 6 Task
`dcp-v2-twin-canary-v1`. Equal submit replay is idempotent, conflicting replay
fails and no second submit is authorized. Stage 6 must still finish at one
verified persistent deployment and restart dedupe before any Stage 7 work.

Technical completion is not owner acceptance.

## 9. Paused install rollback and one assertion-only resume

The first governed install attempt after DCP pin PR #250 merged reached the
correct stopped managed-source activation, but the DCP-owned installer then
rejected its canonical JSON response. The preserved quarantine is exact backup
`i12-20260820T155118Z`: `failed-new-data/ao.db` has SHA-256
`10481ec494534c3929771b2db0d1cdc6a17bce61682b7ef9c4b1f34b534063cf`,
integrity `ok`, schema `84`, one exact `dcp-v2-twin-stage5` activation, one
exact `dcp-wbc-integration-lab` project and zero twin lifecycle rows. Its
activation binds managed source/tree
`c1fc43d74cd517b7d73540f340058fa17b56ef15` /
`ff51ca2b1f6f9fa502b999f50a366a8e35035421`, install-receipt digest
`11e6cbebb529a20d9553451cb1a705668969c7c38912cd434d83aa24b4794024`
and the already-reviewed repository, issuer, workflow, environment, service
and adapter identities.

The managed CLI response schema is canonical lower camel case:
`activation.sourceCommit`, `activation.sourceTree`,
`activation.installReceiptSha`, `projectId`, `projectPath`, `created` and
`projectCreated`. The DCP installer alone required the three activation fields
as `SourceCommit`, `SourceTree` and `InstallReceiptSHA`. That assertion mismatch
occurred after the correct transaction committed inside the subsequently
quarantined data copy. The installer failed closed and restored the canonical
predecessor bundle, data and receipt. Fresh readback after rollback proved
source/tree `84dbee2a701186628c1ad92950aa14639000fc0b` /
`9374ece6efccf87dcb8a7627c97722a16d063b77`, receipt SHA-256
`685ae805a61f24f6c7e0628c788e2ad0cfce8d605b65143034296cb212fc757e`,
SQLite SHA-256
`561e6c624aeb5030b3d69dcba1ab2f39222c2b9dd2af16e58c488ad89f518f9b`,
integrity `ok`, schema `83`, `73` total and `0` active model Actions, no DCP
process/run file/listener, and the exact frozen WBC predecessor/admission 32.

After the safe pause, the owner authorized exactly one additional DCP-only
correction despite the otherwise consumed Stage 5 correction budget. It may:

1. add failing-first tests for the exact canonical lower-camel response and
   fail closed on missing, duplicate, wrong-type, wrong-value, uppercase-only
   or foreign-extra identity fields;
2. change only the installer/adapter parsing and directly related tests,
   audits and authority text; and
3. after a separately reviewed/green merge, run exactly one further governed
   stopped install attempt of the unchanged managed source/tree above.

The parser must not accept both casing variants or weaken any activation,
project, source/tree/receipt, issuer, workflow, target or destination check.
Managed source, its lock, the lab issuer seam and Selectel destination remain
immutable. Any second defect class, second failed install, source or
architecture change, credential/destination decision, protected-surface drift
or install ambiguity stops Stage 5 `BLOCKED` without retry. Stage 6 remains
ineligible until the corrected install/preflight succeeds and the ordinary
Stage 5 terminal-evidence PR merges.

## 10. Exact lower-camel implementation gate

Authority amendment PR #251 exact head
`d65ffbc8e39f8fc8f7aece98d8d9024bb4d0fbc0` passed context-free review
`4984967250`, baseline run `32390805042` and zero threads, then merged normally
at `2c32046149bba97b8796d5f5ebebff96d260d74c`, tree
`a5d868eb8daeba7d991ae74d398ca81766582621`.

The bounded DCP implementation replaces only the installer's uppercase jq
predicate with one exact response validator. It requires the complete canonical
root and activation key sets, lower-camel field names, exact types and every
locked activation/project/source/tree/receipt/policy/issuer/workflow/
destination value. Streaming JSON paths reject duplicate keys before the
ordinary object validation. Missing, duplicate, wrong-type, wrong-value,
uppercase-only and foreign-extra fixtures all fail closed; a canonical
lower-camel fixture succeeds. Unknown fields and accepting both casing forms
remain prohibited.

This implementation does not change managed source/tree
`c1fc43d74cd517b7d73540f340058fa17b56ef15` /
`ff51ca2b1f6f9fa502b999f50a366a8e35035421`, migration 0084, target policy,
issuer seam, credentials, lab destination or runtime semantics. Its own merge
does not install, migrate, start runtime or submit. Only after exact-head
review, green baseline, zero threads and normal merge may the one remaining
governed stopped install attempt run.

## 11. Technical completion record

Lower-camel parser PR #252 exact head
`837a125ed3bb482351bef2a7d8bfdf875cc2fdeb` passed review `4985039918`,
baseline run `32391613310` and zero threads, then merged normally at
`38f40576dbf246bde6e42ef877c5473bb61fa125`, tree
`9cde64e32b162b3d969b340d193bc2d60db1cf48`.

The single further governed stopped install succeeded. Backup
`i12-20260820T163147Z`, receipt
`54dd88beef2e9c93ee86435df2645d6707acf2dc3e2c0c0b4dad6de9b40cc9c0`
and DB `da0918196d4c63f571d63feaf00f71c84e27d91498240779590a0ee67700eb86`
bind exact source/tree `c1fc43d7...` / `ff51ca2b...`. Stopped preflight proved
schema 84, one core authority, one Stage 5 activation, one twin project, zero
v2 lifecycle rows, 73/0 model Actions, no process/listener/run file/sidecars
and unchanged frozen WBC, Selectel lab and Luchiki invariants.

Exact proof is in
`DCP_WBC_INTEGRATION_TWIN_STAGE5_TERMINAL_EVIDENCE.md`. Stage 5 becomes
technically `COMPLETE` only when that evidence PR itself passes review/CI and
merges. No Stage 6 submit is part of this contract update.
