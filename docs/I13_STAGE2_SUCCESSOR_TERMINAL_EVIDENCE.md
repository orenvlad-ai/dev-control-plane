# I13 Stage 2 successor terminal BLOCKED evidence

evidence_status: technical-blocked
recorded_at: 2026-08-12
installed_source: 6f1b5f9828853b6c597d6e6b82fda52ced097b61
incident_generation: 1
successor_attempt_generation: 2

This is the immutable technical handoff evidence for the owner-approved I13
Stage 2 exact-incident successor cycle. It records a truthful terminal
`BLOCKED`, not owner acceptance and not a successful safe stop. The unchanged
successor result was accepted exactly once by the reviewed model-free
validation recovery. The required controlled restart then consumed the one
authorized card-12 wake, but native same-worker restoration failed before a
Codex child or model request because the preserved session has no restorable
Codex session identity. The wake budget is consumed and no re-arm, replacement
identity or additional model call is authorized.

The earlier [Stage 2 terminal BLOCKED evidence](I13_STAGE2_BLOCKED_EVIDENCE.md)
remains unchanged. Nothing in this record rewrites or accepts its first failed
arbiter artifact.

## Governed contract, source, pin and installation

- The exact-incident successor contract PR
  [#142](https://github.com/orenvlad-ai/dev-control-plane/pull/142) merged
  normally at `4dfff558ac425080d62bd6fe2fb13b573ef50661`. Managed-source PR
  [#26](https://github.com/orenvlad-ai/dcp-orchestrator/pull/26) passed its
  source/package checks and merged at
  `baac2921a6901e836cbbf3759c3c42f5259ea37c`, tree
  `a1ecbb79bd14a48ee270e6ce320633f2227cfe46`. Pin PR
  [#143](https://github.com/orenvlad-ai/dev-control-plane/pull/143) merged at
  `b273d9ed1640f164d209f5a21e25f38929cc402d`.
- The exact-result validation-recovery contract PR
  [#144](https://github.com/orenvlad-ai/dev-control-plane/pull/144) merged
  normally at `28546ce0cc2be84349221464c4938c98ed11d32a`. Managed-source PR
  [#27](https://github.com/orenvlad-ai/dcp-orchestrator/pull/27) passed its
  source/package checks and merged at
  `6f1b5f9828853b6c597d6e6b82fda52ced097b61`, tree
  `7cb55d85073af960944a645e2fbe13503e98bf4f`.
- Pin PR [#145](https://github.com/orenvlad-ai/dev-control-plane/pull/145)
  retained exact head `90e58613b0a327a85adba10da8d1d0c93f71f475`. Its one owner-authorized
  baseline rerun was Actions run `31556202627`, job `94075049657`; checkout and
  both audit steps succeeded. The PR merged normally at
  `0df41738a68d89aa1a9239d577d69cd5aff23d5b`, tree
  `d7830b4023cfe085e90f48276dc856783da57159`, and the clean canonical checkout
  fast-forwarded to that exact merge.
- Deterministic `prepare`, `build`, `install` and `preflight` then succeeded for
  exact source `6f1b5f9828853b6c597d6e6b82fda52ced097b61`. Both build passes ran the
  source/provenance, generated-parity, complete Go, frontend typecheck and
  348-test Vitest gates before the arm64 package was installed at
  `/Users/ovlmacbook/Applications/DCP Orchestrator.app`.
- The install receipt records tree
  `7cb55d85073af960944a645e2fbe13503e98bf4f`, install time
  `2026-08-12T10:03:14Z`, daemon SHA-256
  `9626fc552b39ba52e81d4ebfa218acba7c23645111c904b0fd0b97e3de83bb98`
  and `app.asar` SHA-256
  `a1206d002b16a8d9a3cb4485c4522b4fe685fdb102840d1d96530a4f11a4ff90`.
  The main executable SHA-256 is
  `d1783cccdcf4fd2adb519682f1e3f3f1f5c3662defb9d3895c93de4e69348fdd`;
  the prior verified bundle backup is `i12-20260812T100313Z`.

No model or runtime action occurred before the governed contract/source/pin
merges and deterministic installation/preflight.

## Preserved incident and original rejected attempt

- Card 11 / PR #8 remains the one successful first candidate. Exact reviewed
  head `2166d10911f06e14a525267975393c0be03727d0` merged once at
  `b34b31b5443890e69128db2862726950a6bbac0d` through admission sequence 3.
- Card 12 remains native session `dcp-review-lab-12`, task
  `i13-arbiter-b`, worktree
  `/Users/ovlmacbook/Library/Application Support/DCP Orchestrator/data/worktrees/dcp-review-lab/dcp-review-lab-12`,
  branch `ao/dcp-review-lab-12/root`, and ready PR
  [#9](https://github.com/orenvlad-ai/dcp-review-lab/pull/9). Its original
  reviewed head is `d4fcb68051ae113ed497d02151a759800ee85633`.
- Review run `ecb500ad-f9f0-443b-9d73-2c8a6350ce34`, review
  `6aab2a2f-beb2-40a2-bcdb-c47ebf304a65` and batch
  `ddeeb966-30a0-4870-8f3f-fda32a4ee568` remain complete/approved through
  `structured_dcp_v1`. Card 12 still has exactly one review run. The named
  `dcp-review-lab` check remains successful (run `31518650351`, job
  `93869979794`). Fresh provider facts remain OPEN, non-draft, CONFLICTING and
  DIRTY with no merge commit.
- Admission sequence 4 remains the same row
  `dcp-admission-ecb500ad-f9f0-443b-9d73-2c8a6350ce34`, lease
  `dcp-incident-dcp-admission-ecb500ad-f9f0-443b-9d73-2c8a6350ce34`, status
  `incident`, error `merge_conflict_or_ambiguity`, target head
  `d4fcb68051ae113ed497d02151a759800ee85633`, zero refresh wakes and no merge
  SHA.
- The sole incident remains
  `dcp-global-release-2694dbd8b3d4897063603d7a8607ca516aa2f8e05c5a3c39cf56d8e3f18c3c60`,
  generation 1 and identity digest
  `2694dbd8b3d4897063603d7a8607ca516aa2f8e05c5a3c39cf56d8e3f18c3c60`.
  Its original durable result remains terminal `failed/submit_failed`, with
  `model_call_count=1`, no decision, no recovery owner/path and zero wakes.
- Post-terminal SHA-256 verification proves the original input, schema and
  rejected result artifacts are unchanged at
  `355a00609c8ded920bd87b215cea74d3c50213fa4ed8f0b484ea577f73bdbd7d`,
  `8314793a7dbc3f0fc654c28e5936687138883b6e134460fc7204a025102b805f`
  and `d121d012a0b3042f02886fdc0c2aca806f34be64f9e5a3d15e1edf444ff3ae2d`.
  Original arbiter Codex session
  `019ff23c-7cbf-7ee1-9567-30c6693f95fe` and 11,583 tokens remain immutable.

## Successor decision and exact-result recovery

- The only successor attempt is
  `dcp-arbiter-successor-3c62ea80b56ef94165519d4f01e4c449c320bff22d16b902dd68d4a1a355ea7d`,
  attempt generation 2 and identity digest
  `3c62ea80b56ef94165519d4f01e4c449c320bff22d16b902dd68d4a1a355ea7d`.
  Its frozen semantic input digest is
  `aa44c625c940048d5e0266dac23dd4835a1afcf7648116a056758093b67160e6`.
- The sole successor `gpt-5.6-sol`/`xhigh` inference used Codex session
  `019ff3a1-7f0e-79e2-baa5-cbaa1cc6fc37`, the hard 16,384-token ceiling and
  12,271 tokens. Its unchanged 1,705-byte result artifact SHA-256 is
  `9b5ff7847db2533e56bdbbc424114e5bea8e5e3c352ad1d029a99deaba05c172`.
  Post-terminal SHA-256 verification also records the unchanged successor
  input and schema files as
  `fa30d6ea6620e58c36d5163505b2ae80dcdf70b1ee6e2225e0948fe71bdce627`
  and `8779ee3a04b9d3cf0fa2302ced20407f781f5204cd650fe7326c3f93f23925ca`.
  Its nested merge-tree evidence digest is
  `a19c64060d0f41320b6bf652c47ff5c58810ebec0416d003963bc1b4fcdf524f`.
- First startup of the exact installed bundle created exactly one migration-0056
  audit row and validated only that unchanged result model-free. The row is
  `applied`, bound to contract commit
  `28546ce0cc2be84349221464c4938c98ed11d32a`, the exact artifact/session/token
  facts above, and finished at `2026-08-12 10:04:15.14042 +0000 UTC`.
- The successor attempt atomically reached `decided` with no wake and exact
  decision digest
  `237472879b22a8db65c5a3a0715510dc17aee1de93c45eaab45dde538cefb939`.
  The accepted decision is bound to the same incident, attempt generation,
  attempt/input digests and target head. It selects only owner
  `dcp-review-lab-12` and path `same_worker_conflict_repair`; trusted daemon
  policy, not the model, remains fixed at one worker call and one fresh review.
  Its current-base SHA is `b34b31b5443890e69128db2862726950a6bbac0d`;
  scope, diff and mechanical evidence digests are
  `1259b9d8569638c986e1dcd56d13f5d8e1e049e5ad2987c94b713bbbc28fd62f`,
  `c81b1e31b06c0045562ac8a2eb13a6cb772483e8c8859b01c3822ad7e630aa62`
  and `1730d612b1f6755c507cd8d6a21871a329e4f5d556361fcef8dbd289d3ab9cc3`.
  No third arbiter inference or additional artifact replay occurred.

## Controlled restart, failed wake and duplicate proof

- The decision-boundary daemon started at
  `2026-08-12T10:04:15.141914Z`. A controlled exact app/daemon stop and restart
  then started the downstream daemon at `2026-08-12T10:05:10.607376Z`.
- That restart consumed the sole durable recovery wake for the exact existing
  card-12 owner/path. Before any native spawn or Codex model request, stock
  `ResumeDCPReviewLabIdleAgent` proved the preserved session is not restorable:
  `activity_state=idle`, `is_terminated=0`, exact workspace/branch and runtime
  handle are present, but both `runtime_launch_id` and `agent_session_id` are
  empty. The stock resume gate therefore returned `ErrNotRestorable`.
- The successor row became terminal `failed/repair_launch_failed` at
  `2026-08-12 10:05:10.607149 +0000 UTC`. It retained the exact decision
  digest, owner/path, `model_call_count=1` and `recovery_wake_count=1`; it has no
  recovery target SHA or recovery review-run id. The retained tmux pane is
  only the original idle `zsh` and has no child process.
- A second controlled exact app/daemon stop and restart started the final daemon
  at `2026-08-12T10:06:59.17111Z`. The terminal row, validation audit, session,
  admission and review facts remained unchanged. Counts stayed 11 total review
  runs, four admissions, one successor attempt, one accepted successor
  decision, one successor wake and zero successor recovery reviews. Card 12
  still has one review run; PR #9 has no new head and no merge.
- Thus both actual arbiter inferences total exactly two for the incident: the
  original immutable rejected inference and the one successor inference. There
  is at most one accepted decision and exactly one consumed wake. No duplicate
  arbiter, run, wake, review, admission claim or merge appeared. Waiting and
  restart reconciliation remained model-free, event-driven and free of a
  heartbeat, timer, watcher or polling loop.

## Model totals and terminal state

The Stage 2 canary used six actual model calls and 132,785 tokens: the original
two workers (75,985), two initial reviewers (32,946), original arbiter (11,583)
and successor arbiter (12,271). Exact-result replay, both controlled restarts
and the failed wake used zero model calls and zero model tokens. No recovery
worker or fresh reviewer started.

Status is `BLOCKED`. Not done: card 12 produced no repaired exact head, no fresh
context-free review exists, admission sequence 4 did not succeed and PR #9 did
not merge. The exact blocker is exhausted downstream authority after the one
authorized wake reached an unrestorable preserved worker identity before model
launch. Continuing would require new owner authority and a separately reviewed
contract/budget for another worker action or a scope-changing replacement;
neither is authorized here. Production, `wb-core`, real repositories, secrets,
labels, Telegram, HumanGate, hosted UI, owner acceptance and Release Train
production were untouched. Technical completion and owner acceptance are not
claimed.
