# Decisions

## 2026-08-07 — retire the legacy epoch

- v1/v2 is frozen at `archive/legacy-v1-v2-20260807`; history is preserved
  without rewrite.
- Legacy modules, imports, routes, workflows and deployment code are absent
  from the active tree.
- The old hosted projection is retired. Its runtime and TLS evidence remain
  recoverable, while `devcontrol.pro` stays reserved.

## 2026-08-07 — leave a planning surface

- This repository contains documentation and model-free CI only.
- No Agent Orchestrator code or other control-plane implementation was selected
  or imported by the reset. The later architecture decision below selects a
  future foundation without adding it to the active tree.
- Architecture implementation requires a separate owner-approved task.
- Technical completion and owner acceptance remain separate states.

## 2026-08-07 — use one simple repository-change flow

- The curator owns discussion and dispatch, does not edit files, and waits
  without polling after dispatch.
- The owner's natural command `запускай` dispatches one separate, user-owned
  Codex executor task. Only one change task may be active at a time; no Release
  Train, task queue or parallel orchestration is introduced.
- The executor uses a separate branch/worktree, relevant checks, semantic
  self-review and an ordinary ready, non-draft PR with review, green required
  CI and safe merge. It then returns a concise technical handoff to the curator.
- Supported Codex Desktop title and pin controls are best-effort task metadata,
  not repository automation. The owner manually unpins tasks.
- Only the owner's exact phrase `Задача принята` records acceptance. A merge or
  technical handoff does not, and agents must not synthesize that decision.

## 2026-08-07 — reserve an isolated future orchestrator lab

- `dev-control-plane` remains the source of truth for DCP architecture.
- `DCP_lab` may later be created as a separate Project plus isolated local
  runtime, state root and disposable synthetic test repository.
- The lab is neither this repository's development workflow nor a connection to
  `wb-core`, real target repositories, hosted systems or production.
- The first canary contract is in `PROJECT_BRIEF.md`. No lab Project, runtime,
  repository, integration or canary is created by this decision; each stage
  needs separate approval.

## 2026-08-07 — select Agent Orchestrator as the future application foundation

- A DCP-managed fork of Agent Orchestrator is the approved base for the future
  local application and operator UI. Its current local desktop/daemon control
  surface, task/session visibility and isolated-worktree model make it a
  foundation, not an architecture accepted unchanged.
- No upstream code, dependency, binary or build is imported by this decision.
  A later task must pin the exact fork point, preserve provenance and implement
  the fork in a separately approved scope.
- The fork's product identity is **DCP Orchestrator**. The macOS bundle ID is
  `pro.devcontrol.dcp-orchestrator`; the application/state namespace is
  `dcp-orchestrator`. On macOS, persistent state and application data live only
  below `~/Library/Application Support/DCP Orchestrator/`, with explicit
  `state/` and `data/` children; caches and logs use
  `~/Library/Caches/pro.devcontrol.dcp-orchestrator/` and
  `~/Library/Logs/DCP Orchestrator/`. Runtime worktrees and test artifacts also
  stay outside Git in explicitly configured DCP roots.
- The fork must not reuse upstream's product name, bundle ID, executable/update
  identity, `~/.ao` paths, environment namespace, updater cache, release feed or
  telemetry identity. Migration or discovery of upstream state is not implicit;
  any future import needs an explicit owner-approved design.

### Upstream isolation release gates

A DCP build is not releasable until deterministic checks prove all of these:

1. **Updates are fully disabled:** no automatic or manual updater initialization,
   background check, update feed, updater cache, download or install path is
   reachable or packaged. A default-off preference alone is insufficient.
2. **Telemetry and analytics are fully disabled:** no PostHog or other analytics
   client initializes; no renderer, daemon, CLI, update or local analytics event
   is captured, persisted or exported; no upstream project key/host or telemetry
   install ID is present in source or built artifacts.
3. **Crash reporting is fully disabled:** source, dependency and artifact
   inventory plus a network-denial test prove that the shipped desktop/runtime
   captures, persists and uploads no crash report through an inherited upstream
   path. The reviewed upstream revision confirms PostHog telemetry and also
   contains Sentry wiring in its separate landing-site subtree, but the review
   did not establish every possible packaged crash path; absence therefore
   remains a mandatory release gate, not an upstream fact.
4. **Namespace isolation is complete:** product name, macOS bundle ID, paths,
   process/service identifiers, IPC endpoints, environment variables, update
   metadata and data migrations cannot collide with Agent Orchestrator.

Local operational logs and the minimum task/evidence record may exist only
under the DCP namespace and an approved retention policy. They are not a route
to reintroduce product analytics or remote crash reporting.

### Apache-2.0 handling

The reviewed Agent Orchestrator revision carries the Apache License 2.0 in its
root `LICENSE` and has no tracked `NOTICE` file. For any distributed fork,
release compliance includes shipping a copy of the license, marking modified
files, retaining applicable copyright/patent/trademark/attribution notices and
propagating applicable `NOTICE` attributions if the selected future fork point
or incorporated dependencies include them. Apache-2.0 does not grant trademark
rights; DCP's separate product identity is mandatory. The exact future fork
point and dependency notices must be re-audited at implementation and release
time rather than inferred from this snapshot.

## 2026-08-07 — borrow Symphony principles, not its runtime

- DCP adopts these design principles from the reviewed Symphony specification:
  one authority serializes state mutations; dispatch is idempotent; attempts
  have explicit phases and terminal reasons; reconciliation precedes new work;
  failure retries are bounded and back off; restart recovery uses authoritative
  facts rather than assuming live workers survived; workspaces are contained by
  normalized-root checks; and terminal cleanup is explicit and observable.
- The mechanical supervisor may execute only those deterministic rules and
  invariant checks. Semantic review, incident judgement, scope authorization
  and owner acceptance remain outside it.
- DCP does not adopt Symphony's issue-tracker polling service, exact in-memory
  scheduler, retry formula, Codex App Server integration, workflow watcher,
  implementation code or runtime. No separate Symphony service is accepted for
  the first stage.

## Primary-source provenance

Sources were read from official upstream repositories on 2026-08-07. Links are
pinned so later upstream changes do not silently change the evidence.

| Upstream | Reviewed revision | Primary material and fact boundary |
| --- | --- | --- |
| [Untrivial-ai/agent-orchestrator](https://github.com/Untrivial-ai/agent-orchestrator) | [`f17013b53a1752e86c66e87b45aaa4a463fdff62`](https://github.com/Untrivial-ai/agent-orchestrator/tree/f17013b53a1752e86c66e87b45aaa4a463fdff62), committed 2026-08-07 | [README](https://github.com/Untrivial-ai/agent-orchestrator/blob/f17013b53a1752e86c66e87b45aaa4a463fdff62/README.md), [architecture](https://github.com/Untrivial-ai/agent-orchestrator/blob/f17013b53a1752e86c66e87b45aaa4a463fdff62/docs/architecture.md), [telemetry](https://github.com/Untrivial-ai/agent-orchestrator/blob/f17013b53a1752e86c66e87b45aaa4a463fdff62/docs/telemetry.md), [updater](https://github.com/Untrivial-ai/agent-orchestrator/blob/f17013b53a1752e86c66e87b45aaa4a463fdff62/frontend/src/main/auto-updater.ts), [packaging identity](https://github.com/Untrivial-ai/agent-orchestrator/blob/f17013b53a1752e86c66e87b45aaa4a463fdff62/frontend/forge.config.ts), landing-site [Sentry wiring](https://github.com/Untrivial-ai/agent-orchestrator/blob/f17013b53a1752e86c66e87b45aaa4a463fdff62/frontend/src/landing/sentry.server.config.ts) and [LICENSE](https://github.com/Untrivial-ai/agent-orchestrator/blob/f17013b53a1752e86c66e87b45aaa4a463fdff62/LICENSE). These support only the upstream capabilities, mechanisms and license observations stated above. |
| [openai/symphony](https://github.com/openai/symphony) | [`f8e8b8a670c799f6e0ade7a8c25c4bf4a4a56ec7`](https://github.com/openai/symphony/tree/f8e8b8a670c799f6e0ade7a8c25c4bf4a4a56ec7), committed 2026-07-24 | [README](https://github.com/openai/symphony/blob/f8e8b8a670c799f6e0ade7a8c25c4bf4a4a56ec7/README.md), normative [SPEC](https://github.com/openai/symphony/blob/f8e8b8a670c799f6e0ade7a8c25c4bf4a4a56ec7/SPEC.md), [LICENSE](https://github.com/openai/symphony/blob/f8e8b8a670c799f6e0ade7a8c25c4bf4a4a56ec7/LICENSE) and [NOTICE](https://github.com/openai/symphony/blob/f8e8b8a670c799f6e0ade7a8c25c4bf4a4a56ec7/NOTICE). The SPEC supports the cited orchestration principles; Symphony code and runtime are not selected. |

## 2026-08-07 — implement the bounded I2 laboratory slice

- The owner separately authorized I2 even though owner acceptance of I1 was
  not recorded. That authorization does not itself record acceptance.
- The exact required Agent Orchestrator revision
  `f17013b53a1752e86c66e87b45aaa4a463fdff62` remains the provenance point. A
  fresh clone and GitHub commit evidence resolved tree
  `6402905847ad8f31531b70d0d90f47324c0469b6` with valid signature verification.
  The full qualification is in `UPSTREAM_QUALIFICATION.md`.
- Upstream's broad Electron/Go packaged surface contains reachable updater,
  PostHog, state/IPC and remote capabilities, while its landing subtree also
  contains Sentry wiring. Importing that tree would enlarge the fixed canary
  beyond its threat boundary. I2 therefore packages a newly DCP-authored,
  stdlib-only lab slice and no upstream runtime file, binary or dependency.
- The upstream Apache-2.0 license is preserved byte-for-byte, no tracked
  upstream NOTICE exists at the pin, DCP attribution is supplied and the
  modification/package boundary is explicit. The upstream frontend manifest's
  separate MIT metadata conflicts with the root license observation; because
  I2 redistributes no upstream source/dependency, that ambiguity is recorded
  for mandatory clarification and re-audit before any future source fork.
- The supported I2 interface is a token-protected loopback web UI launched by
  `./bin/dcp-orchestrator`. Identity and macOS roots use only DCP Orchestrator,
  `pro.devcontrol.dcp-orchestrator` and `dcp-orchestrator` namespaces. It does
  not discover or import installed Agent Orchestrator state.
- The sole allowed flow is one fixed task/card/attempt/worker with no queue,
  retry or reviewer. The worker creates only the exact uncommitted marker in an
  allowlisted disposable repository. Success follows deterministic marker and
  mutation verification plus complete branch/worktree/process/session/lock/
  attempt cleanup; otherwise a truthful terminal reason is recorded.
- Updater, telemetry, analytics and crash reporting are absent from source and
  package paths, rather than preference-disabled. Model-free source,
  dependency, artifact, endpoint, namespace, containment, failure and cleanup
  gates enforce this boundary.
- DCP alone owns runtime state; GitHub owns code/PR/CI/merge facts. The
  provider-neutral history seam stores only optional refs, defaults to
  `provider=none` and never stores a full transcript. Entire is not installed,
  contacted or required. A later private canary needs explicit opt-in and a
  separately approved privacy boundary.
- No signed macOS `.app`, production, hosted DCP server, target integration,
  `wb-core`, `devcontrol.pro`, parallel orchestration, Release Train, reviewer
  loop, arbiter, legacy runtime or Symphony code is implemented.

## 2026-08-07 — replace the active I2 experiment with native Agent Orchestrator in I3

- The owner's explicit I3 authorization supersedes earlier statements that an
  upstream runtime or packaging decision was only future scope. It does not
  authorize any other target-architecture expansion.
- The active lab foundation is official stable Agent Orchestrator `v0.12.1` at
  commit `1df40e93772c2c48e916870d9c3ddf8f29a69f84`, tree
  `36bf30cc4960c10f0d94fc63a8ff0a4dd22bb8a8`. Its native Electron UI, Go
  daemon, SQLite authority, project/session model, tmux worktrees and Codex
  adapter are retained.
- I2 remains a completed, owner-accepted experiment but is no longer an active
  foundation or launcher. Its Python server, local web UI, private registry and
  worker supervisor are removed from the active tree without rewriting Git
  history.
- DCP uses a managed external source checkout rather than vendoring the
  upstream tree or creating an unapproved fork repository. The repository owns
  only the immutable pin, provenance, exact patch queue, launcher and adapter.
  Updates require a new reviewed stable pin and clean requalification.
- Upstream keeps its native Agent Orchestrator identity for this source-run lab;
  rebranding is not technically required and is not performed. Isolation comes
  from an explicit DCP lab root, not product-name collision.
- The sole upstream patch adds an absolute
  `AO_ELECTRON_USER_DATA_DIR` override with tests. It leaves upstream defaults
  unchanged when the override is absent and is necessary because
  `AO_DATA_DIR`/`AO_RUN_FILE` do not reparent Electron Chromium/crash state.
- Telemetry is disabled using supported configuration:
  `AO_TELEMETRY_RENDERER=off`, `AO_TELEMETRY_EVENTS=off`,
  `AO_TELEMETRY_METRICS=off`, `AO_TELEMETRY_REMOTE=off` and the supported `*`
  event-stream kill switch. I3 runs Electron in source/dev mode, where packaged
  updater initialization and relocation are skipped. No broad updater or
  telemetry refactor is accepted.
- The curator adapter accepts only a one-line prompt up to 512 UTF-8 bytes and
  the allowlisted remote-free `dcp-lab` target. It invokes native `ao project`
  and exactly one native `ao spawn --harness codex`; it stores no parallel task
  state.
- Upstream's additional agents, orchestrator/reviewer loops, PR/CI automation,
  mobile/browser/remote features and parallelism remain present upstream but
  are not exercised or adopted as DCP policy by I3.

## 2026-08-08 — isolate the I5 Codex worker and version the operating start

- The AO Codex adapter keeps standard Codex authentication but launches the
  worker through `codex exec --ignore-user-config --ephemeral`. Per-invocation
  feature flags disable hooks, apps, plugins and multi-agent tools; user MCP
  configuration is therefore not loaded and no hook-trust bypass is used.
- Codex worker SQLite state is lab-local. Credentials are neither copied nor
  exposed, and no global user configuration is changed.
- `bin/dcp-ao preflight` is mandatory before launch/check. It proves the pinned
  source and exact source-built executable, lab runtime paths, Codex isolation
  surface and authentication, and fails when the installed AO app path exists.
- `CURRENT_OPERATING_CONTRACT.md` is the versioned current-flow handoff reached
  automatically from root `AGENTS.md`. CI checks the link, revision and narrow
  code/document invariants; it is not a second architecture source or a runtime
  updater.
- Until separately changed by the owner, one primary curator directly creates
  one executor with no nested curator and only one active DCP change. Technical
  completion remains distinct from owner acceptance.

## 2026-08-08 — classify the I6 one-shot worker by process outcome

- The DCP Codex adapter remains a clean one-shot
  `exec --ignore-user-config --ephemeral --strict-config` launch. Its existing
  AO process supervisor is the sole outcome authority: successful start is
  active, exit status zero is idle, and launch failure, non-zero exit or signal
  is exited. Output text, model claims and marker content are not lifecycle
  inputs.
- A successful exit atomically closes the supervised runtime generation while
  retaining the native tmux shell and scrollback. This uses AO's existing
  durable generation field and prevents a stale workload-dead poll from
  rewriting the successful idle outcome as a failure; no registry, watcher,
  service or new state is added.
- Successful completion does not mask waiting-input/blocked, and idle continues
  through the existing PR/review/merge status derivation. The board therefore
  uses its ordinary Idle presentation for success and existing red Exited
  presentation for failure.

## 2026-08-08 — make submit the single I7 DCP Lab entry

- The owner's bounded I7 authorization makes `bin/dcp-ao-submit` the only
  normal curator/lab lifecycle entry. Direct source UI launch, headless daemon,
  stop and restart instructions are removed from that flow; upstream backend,
  CLI and API surfaces remain present.
- One lab-local singleton is held from exact-contour preflight through the
  complete native worker spawn. A healthy source UI/app-owned daemon pair is
  reused without restart, including with active workers. A fully stopped pair
  starts from pinned source and proves a shared per-launch instance identity
  before submission.
- Recovery is limited to deleting one complete dead app-owned stale run-file
  whose port and browser socket are exact. Live, incomplete, headless,
  persistent, foreign, unhealthy or ambiguous states fail closed. DCP disables
  the upstream desktop wedged-daemon kill-and-replace branch for this contour;
  no process is killed or replaced by the gateway.
- DCP Lab hides manual orchestrator-spawn controls and related retry hints in
  the renderer. Existing orchestrators remain navigable, automatic/programmatic
  orchestration and the native spawn API remain intact, and additional worker
  sessions remain supported upstream. This does not authorize or implement a
  reviewer, arbiter, model loop or retry/reconciliation policy.

## 2026-08-08 — replace the source-run contour with canonical DCP Orchestrator.app in I8

- The owner's explicit I8 authorization supersedes I3/I7 decisions only where
  they made source/dev the runtime or retained upstream product identity. The
  pin, managed-source boundary, I5 worker isolation, I6 outcome classification,
  single submit door and non-production scope remain authoritative.
- The sole DCP Lab runtime is native arm64
  `/Users/ovlmacbook/Applications/DCP Orchestrator.app`, bundle id
  `pro.devcontrol.dcp-orchestrator`. Its main executable is
  `dcp-orchestrator`, embedded daemon/CLI is `dcp-orchestratord`, health service
  is `dcp-orchestrator-daemon`, fixed port is `43231`, and its run-file carries
  the exact contour, app PID, per-launch instance id, bundle id and absolute
  path. Managed pinned source is development-only build/test input.
- Durable state and data use
  `~/Library/Application Support/DCP Orchestrator/{state,data}`. Managed
  source, builds, evidence and the disposable target also remain beneath that
  canonical explicit lab root. Chromium/Electron caches use
  `~/Library/Caches/pro.devcontrol.dcp-orchestrator`; application logs use
  `~/Library/Logs/DCP Orchestrator`. No path discovery, migration or import of
  `/Applications/Agent Orchestrator.app` or `~/.ao` is allowed.
- The app is the sole daemon lifecycle owner through the native supervisor
  link. Closing the macOS window keeps app/daemon/work alive. Explicit Quit
  queries active worker state and requires a native warning confirmation when
  work is active or cannot be proven inactive.
- `bin/dcp-ao-submit` owns no lifecycle process. Under one lock it reuses a
  proven exact app/daemon or opens the absolute bundle only from a completely
  stopped contour. Stale, foreign, duplicate, unhealthy, port-conflicting or
  incomplete identities fail closed without cleanup, kill, stop, restart or
  replacement. Concurrent submits serialize through one app/daemon and one
  distinct spawn each.
- Local build/install is repository-owned: exact patch verification, model-free
  tests, arm64 Electron Forge package, ad-hoc signature, canonical copy and a
  digest-bound receipt. Replacement retains a prior verified DCP bundle below
  the lab root. Notarization and distribution installer are not implemented.
- Auto-update is not packaged: the active main graph has no updater import or
  initialization, Forge has no makers/publishers/feed metadata, preload update
  calls are inert, update UI is hidden, and artifact gates reject
  `app-update.yml` or an updater module. No runtime setting can reach it.
- Telemetry/analytics is not merely default-off. Renderer initialization and
  capture are no-ops; daemon configuration ignores telemetry enable variables;
  daemon wiring is an always-disabled sink; telemetry control routes are not
  mounted; CLI emitters are no-ops. The package carries no analytics module,
  key, host, install identity or local reservoir. Electron/Chromium crash
  reporting switches are disabled before ready and artifact/runtime gates prove
  no crash uploader or emitted reports.
- Manual orchestrator-spawn controls remain hidden, while backend/CLI/API and
  programmatic orchestrator/additional-agent mechanisms remain available.
  Reviewer, arbiter, queue, retry/recovery, monitoring, real targets, hosted or
  production work remain unimplemented and unauthorized.
- The daemon is the producer of the exact `dcp-orchestrator-daemon` identity in
  both its authenticated status and run-file. The gateway requires both
  independent values to agree and remains fail-closed when either is absent or
  mismatched.
- Exact `AO_DATA_DIR` and `AO_RUN_FILE` values are passed only as hidden
  arguments to the packaged one-shot supervisor wrapper so its start/exit hooks
  can update the right daemon. They are removed from the retained tmux shell
  environment and from the Codex child. This preserves strict, ephemeral,
  ignore-user-config isolation while allowing exit zero to become Idle.
- The completed I8 live qualification consumed the owner-raised cumulative
  allowance exactly: one diagnostic stop-gate plus four qualified calls, with
  no automatic retry. Cold `dcp-lab-2`, warm `dcp-lab-3` and concurrent
  `dcp-lab-4`/`dcp-lab-5` created distinct exact markers and reached Idle under
  one persistent exact app and daemon, with no duplicate session and no AO
  external network socket. Minimal redacted evidence is retained outside Git;
  I7 evidence was not changed.
- Creating a dedicated DCP Git fork is the next separately owner-approved
  architectural stage after I8 acceptance. I8 does not create it; the exact
  upstream pin and repository-owned patch queue remain authoritative meanwhile.

## 2026-08-08 — record the DCP v1 target contract without activating it in I9

- [DCP v1 target architecture](TARGET_ARCHITECTURE_V1.md) is the normative
  future design for task, attempt, review, admission, incident, release and UI
  semantics. I9 is docs-only: packaged I8 remains the only current operating
  contour and none of the target roles or transitions is implemented or run.
- The future DCP daemon and its existing SQLite are the sole local state
  authority. GitHub remains authoritative for PR, CI, merge and deploy facts;
  the only Release Train is model-free GitHub Actions. There is no separate
  Watcher, registry, scheduler or service, and any future server projection is
  read-only.
- An external curator submits an approved task once and sleeps. DCP UI owns
  operational status, allowed HumanGate actions and owner acceptance. Reverse
  delivery is optional future work; Telegram is excluded from I9 and the first
  implementation.
- One event-driven Sol `xhigh` executor and one worktree belong to a task. Every
  completed variant receives a new context-free read-only Sol `xhigh` reviewer.
  Three complete review cycles per epoch precede one durable arbiter incident;
  no automatic fourth review or HumanGate is synthesized. Proven executor loss
  creates a fenced successor from a durable checkpoint.
- Admission is deterministic daemon code and owns one serialized admission
  line. Approval yields `READY_FOR_ADMISSION`, never an executor-applied
  `release:ready`. Exact head/current-main baseline and freeze precede the
  controller label and Release Train; head or relevant-main change invalidates
  admission and requires revalidation and fresh review.
- Post-merge failure freezes global admission. Bounded exact-SHA mechanical
  reconciliation/retry/rollback runs first; only exhaustion or ambiguity opens
  one global incident whose arbiter sees the whole queue and assigns one
  recovery owner/path. Other tasks remain durable, model-free waiters.
- Up to three intellectual agents may be active, with a configurable limit and
  arbiter priority. Waiting and monitoring use no model and have no timeout;
  only active actions time out. Restart recovers from SQLite plus reconciled
  GitHub facts.
- HumanGate is limited to credentials/login/2FA/captcha, proven irreversible
  data-loss risk, security/permission authority, new external-data purpose,
  material scope/risk expansion or platform-owner-only action. CI, conflicts,
  retries, unknown technical paths and waiting are not gates.
- A later owner-approved managed `dcp-orchestrator` fork will own application
  code. `dev-control-plane` will retain architecture/integration policy and the
  exact approved fork commit. Upstream stays read-only with manual reviewed
  updates. I9 creates no fork and leaves the I8 lock/patch authority intact.
- The previously pinned Symphony review remains provenance only for serialized
  mutation authority, idempotent dispatch, explicit phases/terminal reasons,
  reconcile-before-new-work, bounded backoff, authoritative restart recovery,
  workspace containment and observable cleanup. No Symphony runtime, service,
  code, issue polling, App Server integration or watcher becomes a dependency.
- The target reserves an outbound `HistoryProvider`/`ProvenanceAdapter` seam
  with `provider=none` by default. Core state remains in DCP SQLite and GitHub
  remains PR/CI/merge/deploy authority. A future provider may receive only
  allowlisted compact immutable refs/digests; never prompts/transcripts, code,
  secrets or credentials, and never authority over admission, release, queue or
  recovery. Entire requires later privacy review and explicit owner opt-in; I9
  does not install, invoke or test it.

## 2026-08-08 — move the unchanged I8 application source to a managed fork in I10

- I10 creates `orenvlad-ai/dcp-orchestrator` as a private standalone managed
  repository. GitHub cannot place a private repository in the public upstream
  fork network under the available account plan, so standalone history
  preservation is the fail-closed alternative; no public repository or release
  is created.
- The fork preserves the exact official Agent Orchestrator `v0.12.1` ancestry
  at commit `1df40e93772c2c48e916870d9c3ddf8f29a69f84`. `origin` is the DCP repository;
  official upstream is a read-only, push-disabled reference. Apache-2.0,
  upstream provenance and the upstream-absent `NOTICE` result are recorded in
  the fork, which adds its own DCP `NOTICE` and provenance file.
- The accepted I8 patch sequence is retained as seven reviewable fork commits.
  Parity anchor `23fe9bba77873075f32b813fb0a3c936598882fb` has the exact binary full-index
  upstream diff SHA-256
  `047c9f74902ede19b6e3a3ba753fc7b2702a322a9be709fb0e975cc5628314d2`.
  The approved fork revision is merge commit
  `e770c2745dbf3b839af7dc7a6789aea192208a06`, tree
  `a85d5c1abac34371399065fdd521752ae687491f`.
- The fork owns Electron/Go application code, tests and package metadata.
  `dev-control-plane` remains architecture, integration, release-policy and
  exact-pin authority. Its former patch queue and copied upstream license are
  removed from the active tree and remain recoverable only through Git history;
  there is no second active application source of truth.
- Fork CI is read-only and covers backend tests/build, renderer typecheck and
  selected tests, native package/artifact identity, namespace, absence of
  updater/telemetry/crash paths, and LICENSE/NOTICE/provenance. It has no
  publisher, release trigger, auto-update or artifact upload.
- I10 changes only source ownership and build provenance. I8 remains the sole
  implemented runtime semantics, including its SQLite schema, task lifecycle,
  UI and isolated Codex worker. I9 remains inactive target design; no reviewer,
  arbiter, admission, queue, retry/recovery or production surface is added.
- The fork was built and packaged first in a disposable build/state contour.
  Replacement of the canonical bundle is allowed only from exact merged
  `dev-control-plane` main and the exact fork pin, after model-free gates and a
  verified backup of the prior DCP bundle plus applicable state. No model
  canary is required unless transport parity remains otherwise unproven.

## 2026-08-09 — add the minimal durable model-free task foundation in I11

- Fork PR [#2](https://github.com/orenvlad-ai/dcp-orchestrator/pull/2) replaces
  the misleading upstream operational entry before application design and
  implementation. The fork now points automatically to exact pinned
  `dev-control-plane` operating/target contracts and CI rejects `~/.ao`,
  updater/publisher/telemetry/crash authority or loss of the contract link.
  Useful surgical coding conventions remain, but upstream product/runtime
  rules do not govern DCP.
- The approved fork revision is merge commit
  `417a844e7b85b6b14ae9a1855009d8bf139ee43d`, tree
  `15a77f0804c99c8b603b96aaf7797dad8e77b4df`. The fork remains the sole owner
  of application code; this repository remains architecture, integration,
  release-policy and immutable-pin authority; official upstream stays
  read-only provenance.
- Additive migration 0048 adds `dcp_tasks` and `dcp_task_events` to the existing
  `ao.db`. The logical contract binds stable task/idempotency identity,
  immutable canonical approved task/scope plus digest, exact remote-free
  `dcp-lab` identity, SUBMITTED/revision/timestamps and an append-only monotonic
  event stream. State and event commit atomically; equal replay is idempotent,
  conflict/invalid target fails before mutation, and stale compare-and-set is
  rejected.
- The existing loopback daemon boundary exposes typed model-free
  submit/read/list-events. The board adds one clearly labelled synthetic/lab
  SUBMITTED card without mixing it with legacy session identity. Every normal
  Spawn/Open Orchestrator affordance is removed, while backend/API/programmatic
  mechanisms needed by future authorized roles remain intact. The existing
  `bin/dcp-ao-submit` gateway is unchanged and no second curator flow exists.
- Restart validates the additive schema, preserves I8 sessions and restores the
  same task/revision/events. A SUBMITTED task starts no worker, process, timeout
  or model call. The prior I10 daemon successfully reopened an I11 migration-48
  database, after which I11 reread the same task; rollback therefore retains
  the verified prior bundle and does not require a destructive down migration.
- I9 remains inactive target design outside this exact foundation. I11 does not
  activate executor/reviewer/arbiter, action/checkpoint lease, admission,
  Release Train, retry/recovery, HumanGate, webhook, server projection,
  HistoryProvider/Entire, Telegram, reverse delivery, real targets, WBC or
  production. Technical completion does not create owner acceptance.
