# WBC integration twin Stage 6 final freeze blocked evidence

evidence_revision: 2026-08-23.1

technical_status: FINAL FREEZE/BLOCKED after the single adoption transaction applied but its reviewed gateway response validation failed

owner_acceptance: not requested or synthesized

Current stage truth remains in the
[current program manifest](DCP_WBC_INTEGRATION_TWIN_CURRENT_PROGRAM_MANIFEST.md).
This document records the terminal result of the one owner-authorized final
Stage 6 viability pass. It grants no correction, retry, continuation, provider,
Stage 7, WBC or production authority.

## 1. Qualified route and completed reviewed packages

The sole owner-visible direct executor was task
`01a02a5c-2dab-7f60-97af-d980cb92fbe5`, titled
`DCP · S6 final pass · И35`, on the qualified local host. Machine readback
proved `approval_policy=never`, unrestricted filesystem, network enabled, one
separate clean `dev-control-plane` worktree and platform approval count `0`.
No collaboration subagent, fork, nested executor or overlapping DCP change
executor was used.

The bounded architecture/source phase completed exactly once:

- architecture PR #264 merged as
  `03d9f9943d06e5507dc1fc9c02c53cee782407c8` after exact-head baseline and
  fresh review;
- the sole managed-source PR #78 merged as
  `d10a9791392e19510590c3fb4a3d231fe980ecf6`, tree
  `acd93511dd1c77dd2508734bf0b8d331594115cf`; source/package workflow
  `32590686726`, merged-main workflow `32591004094`, review `5000793045` and
  zero threads were exact;
- the sole pin/install/live authority PR #265 had exact head
  `f580207e9d9fd8320adfc045b3b7690d40ae966d`, tree
  `ddabcfa82ba75f3abce055a6545fb64a80b93484`, green baseline
  `32592786360`, fresh review `5000857575`, zero threads and normal merge
  `a53687edf44bd72d10495993993f292a6e21720d`.

No managed-source findings-repair round was used. All three allowed
pre-terminal PR identities are spent.

## 2. Single governed install and stopped schema-87 result

The merged one-use gateway revalidated the schema-86 predecessor, frozen
Task/Revision/Command/Action/native Action/Worker output, clean detached source,
zero active model state and zero provider effect. It then performed exactly one
install invocation:

| Fact | Exact value |
| --- | --- |
| install identity | `stage6-final-d10a979139-86-to-87-v1` |
| backup | `stage6-final-d10a979139-86-to-87-v1-20260822T191027Z` |
| installed source/tree | `d10a9791392e19510590c3fb4a3d231fe980ecf6` / `acd93511dd1c77dd2508734bf0b8d331594115cf` |
| predecessor receipt | `fc8f2a2f6264dc1a3e817e42f124bdbd7040a412eade3fcddf97762f59f214d8` |
| new receipt | `9183c6207908de6f638360b86b8f6e1393d7fc8f0d169e10ac8e0b9dd97421ca` |
| source archive | `81827afcc62ae19851cbbfaf2621106a11fc11533664204ca43de4995d3c4a9f` |
| Worker archive | `70604506cfd1daa6fcb9d5910c800be65af857129c0fbf8f12f5f9d4b2959cb9` |
| signed artifact archive | `5475abdfb8401e693a2d848672f7cf355217ef65dfb0c8e3ca10160a5038c4cb` |
| adoption input | `a8a2828f76ae21939ec6de6ee3d88d7e9269a01653e57f98477a9efe3f2e0ba0` |
| stopped database after migration | `7dd2ad381e0155a0690be9d6e1c198fd22e468473bf9fd567a958e120fe9c71e` |

Migration `0087` applied exactly once. Stopped preflight proved schema `87`,
`integrity_check=ok`, zero foreign-key violations, absent SQLite sidecars,
unchanged frozen lifecycle counts `1/1/1/1`, downstream counts `0/0/0/0`,
direct rows `0/0/0`, `adoptionConsumed=false`, app/daemon stopped and no
provider effect. Rollback was not invoked. The install authority is spent and
must not be replayed.

## 3. One adoption attempt and exact validation failure

The sole adoption entry was invoked once at `2026-08-22T19:14:38Z`. The
installed typed command returned exit success and one response with
`applied=true`; its SQLite transaction committed at
`2026-08-22T19:14:40.720786Z`. The reviewed gateway then rejected the response
as `Stage 6 final adoption response identity differs` and returned failure.
Its one-use manifest records exactly:

- `adoption_attempt=1`;
- `adoption_status=failed-or-ambiguous`;
- no continuation-attempt marker;
- adoption response SHA-256
  `f1c40b0255b0300b06a2701d3548f07d84fb5d2a3b96e46038d270eea61fe745`;
- post-adoption database SHA-256
  `83f21a2d7af5649cbedf9e92e02a3b268fff26b996787440e33334e4f3172ebc`.

The mismatch is exact and model-free. The top-level response fields matched
the strict schema, but its nested adoption object used exported Go field names
such as `TaskID`, `RevisionID`, `CommandID`, `ActionID`, `RuntimeID`,
`NativeActionID`, `CommitSHA`, `TreeSHA` and `ConsumedAt`. The reviewed gateway
required the lower-camel JSON names `taskId`, `revisionId`, `commandId`,
`actionId`, `runtimeId`, `nativeActionId`, `commitSha`, `treeSha` and
`consumedAt`. The command therefore applied its durable transaction while the
one-use caller could not accept its receipt.

This is not authority to reinterpret the failed response as success. The final
contract says a false, failed or ambiguous adoption response consumes the
attempt, triggers `FREEZE/BLOCKED` and forbids replay even if later readback is
equal. No second adoption was attempted.

## 4. Exact safe durable state

One immutable stopped readback after the failure proved:

| Fact | Exact value |
| --- | --- |
| Task | `dcp-v2-twin-canary-v1`, `checks_waiting`, state revision `2`, same Task identity |
| current Revision | `v2-0e1aadfb444bc4d9f4c90c8bf936a0ebec125300`, sequence `2`, `worker_output`, `PRNumber=0` |
| Worker Revision predecessor/cause | `v2-13f81f321f99d1117dc931419e0bea3945ee35a5` / `v2-e028f779a18417e990911057f7db7c666f7487ca` |
| publication Command | `v2-06b20be020812369bf4286fd335aa8f5281d15e2`, sequence `2`, pending, no effect fence |
| historical Worker Command | `v2-e028f779a18417e990911057f7db7c666f7487ca`, succeeded |
| historical Worker Action | `v2-40f87d048813533daa1108b4316c09139acf0a8f`, succeeded, slot `0`, runtime `78535564-a2bc-478c-80b0-207753f2152c` |
| frozen Worker commit/tree | `bebbf8f617f1a6fa0b9e91698fe710fe0a2bad2c` / `2fda4cae71976fd701bf3a9ccca4031f7afb630d` |
| lifecycle counts | Task/Revision/Command/Action `1/2/2/1`; Admission/Incident/ExternalEvent/Result `0/0/0/0` |
| direct rows | model-runtime/terminal-receipt/adoption `1/1/1`; active runtime/model rows `0/0` |
| native boundary | Action `74` remains succeeded; total native model Actions `74`, active `0` |
| SQLite/process | schema `87`; integrity `ok`; FK violations `0`; sidecars absent; app/daemon stopped |

The repository-owned adopted fence independently accepted these durable row
identities. It does not override the consumed gateway failure or authorize a
start.

## 5. Zero-provider and frozen-target proof

The app was never started after adoption. No continuation command, bounded
terminal restart or provider retry occurred. Fresh external readback proved:

- integration-lab main remained
  `375b9b2d0b4c2fce6f2c417850553f79e24a0d92`;
- the canary branch was absent, canary PR count was `0` and workflow-run count
  for that branch was `0`;
- no CI, Reviewer, repair, Admission, Release Train, merge, artifact, deploy,
  provenance or Result effect appeared;
- WBC PR #987 remained open and behind at
  `26044c696651ce5873748ec3f920d40e77c5686c`;
- WBC, production, cutover and the protected co-tenant were not touched.

There was one Task, one install and one adoption attempt, with no duplicate
Task, model Action, publication, Admission, merge, deploy or Result.

## 6. Terminal classification and recommendation

Stage 6 is `FINAL FREEZE/BLOCKED`. The single live-continuation budget is
unconsumed but permanently unusable because its prerequisite adoption attempt
ended failed/ambiguous and replay is forbidden. The source-PR, install and
adoption budgets are spent; a second source PR, installation, adoption or
start is outside this pass.

The project should remain frozen at the exact safe state in section 4. Do not
patch, reinstall, replay adoption, start the app, publish the canary, or begin
Stage 7. Any future reconsideration requires a new owner program outside this
final pass; this evidence grants none. Technical classification does not
synthesize owner acceptance.
