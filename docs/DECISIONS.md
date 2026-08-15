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

## 2026-08-09 — activate one bounded stock automatic reviewer in I12

- Managed-fork PR [#3](https://github.com/orenvlad-ai/dcp-orchestrator/pull/3)
  is the application change. Its approved immutable merge commit is
  `f925dd9922b144b324c3cdd327c9e117e656ccb4`, tree
  `d0dcc5b06c65a44a10e119d5fb360dbfc6616b89`. It preserves official
  `v0.12.1`, the exact I8 parity anchor and the I11 task schema; no new database
  or migration is introduced.
- I12 uses the existing review engine, `review`/`review_run` rows, worker
  session/card, stable reviewer terminal and stock findings delivery. It adds
  no reviewer service, watcher, scheduler, heartbeat, queue or second state
  authority. The automatic trigger is an event reaction after supervised
  worker success/Idle or existing SCM observation and shares the same engine
  with manual Run Review.
- Eligibility is bound to one exact current head of an open non-draft PR, a
  safely idle worker with no active launch, and absence of a prior run for that
  exact PR/SHA. Per-worker serialization plus the existing database uniqueness
  gives single-flight/idempotency. Failed or completed exact-head runs are not
  automatically retried; a new head may receive one fresh run.
- The installed Codex CLI review command removes the unsupported exec-level
  `--ask-for-approval`, pins `approval_policy="never"` and `--sandbox
  read-only`, keeps standard authentication and rejects dangerous approval/
  sandbox bypass. Only the supervisor wrapper receives exact daemon connection
  arguments; the reviewer child does not inherit a writable control-plane
  environment.
- Reviewer start and exit are supervised. Early launch failure, non-zero exit,
  signal, or zero exit without a verdict durably fails the exact still-running
  run and projects Needs You. Startup reconciliation leaves an exact live
  supervisor untouched, fails ambiguous liveness without retry, and converts a
  proven stale running row to failure before at most one exact-head recovery
  launch. Reconciliation itself makes no model call.
- Approval continues through stock Ready-to-Merge/SCM status. Findings continue
  through stock delivery to the same worker identity/worktree. I12 adds no
  arbiter, admission, Release Train, auto-merge, repeated repair loop,
  Telegram, real execution target or production surface.
- The installer may gracefully stop one exact canonical old DCP app/daemon
  under the submit lock only after read-only SQLite/tmux proof that no worker or
  reviewer model action is active. A foreign, duplicate, unhealthy or
  ambiguous contour fails closed. A running review with an exactly missing
  pane or bare stable shell is preserved for new-daemon reconciliation. Bundle,
  state and data are backed up before replacement; installation leaves the new
  app stopped for post-install preflight.
- Live qualification is capped at one fresh automatic reviewer on the existing
  `DCP Review Canary` and `orenvlad-ai/dcp-review-lab#1`, after all model-free
  gates. No manual Run Review, second chat impulse, replacement card or merge of
  the canary PR is allowed. Technical completion still does not create owner
  acceptance.

## 2026-08-10 — close the bounded I12 preserved-worktree recovery gap

- Managed-fork PR [#4](https://github.com/orenvlad-ai/dcp-orchestrator/pull/4)
  is the approved follow-up to PR #3. Its immutable application pin is
  `031610b1050818d59654ee78963e41f5f1823430`, tree
  `713da841831a5beabed48221fa50ec888e81d1ae`; PR #3's merge commit remains the
  prior approved pin and historical I12 foundation.
- The deterministic defect was not GitHub, the model or the UI: restart
  reconciliation reused a terminated worker's saved workspace path after its
  directory had disappeared, so the reviewer terminal started with no valid
  cwd and exited before a model call. The fix uses the existing stock workspace
  `Restore` path before reviewer preflight and never resumes the worker.
- This continuation is available only when the latest durable run proves that
  exact working-directory mismatch, the worker remains Exited/terminated with
  no active launch, and SCM observes one new exact head. The restored project
  must be single-repository, at the saved absolute path and branch, clean and
  exactly at the observed head. Any new run or preparation failure consumes
  the continuation, preserving fail-closed single-flight behavior.
- The same native worker session/card and stable `review-<session>` terminal
  remain the only review owners. No task card, database, migration, watcher,
  scheduler, queue, retry framework, model loop or second state authority is
  introduced. The one authorized live canary remains subject to every existing
  model-free install/identity gate and does not merge its PR.

## 2026-08-10 — close the bounded I12 SCM event-delivery gap

- Managed-fork PR [#5](https://github.com/orenvlad-ai/dcp-orchestrator/pull/5)
  is the approved event-delivery closure after PR #4. The current immutable
  application pin is `695491e2f6cc7b1b327bb5dd35e61d16280b4a64`, tree
  `1689184429a415b65838a89528f81bd6de13b00d`; PR #4 remains the prior approved
  worktree-recovery pin.
- The deterministic remaining defect was that the stock SCM observer skipped
  every terminated session before reading its tracked PR. The review engine's
  recovery could restore the exact worktree once called, but a replacement
  head for the preserved Exited/terminated card could not emit the lifecycle
  event that calls it.
- The observer now retains only a worker with no active launch and exactly one
  durable missing-worktree review failure. All other terminated sessions remain
  excluded. The shared predicate requires that proof to be the latest run and
  appear exactly once; any resulting run, different later outcome or second
  matching failure consumes eligibility and prevents automatic retry.
- This is an extension of the existing stock observer/read surface, not a new
  watcher or recovery service. It adds no mutation before SCM persistence, no
  worker resurrection, task/card, schema, registry, scheduler, queue, polling
  cadence, model loop or second state authority.

## 2026-08-10 — restore the packaged stock verdict channel

- Managed-fork PR [#6](https://github.com/orenvlad-ai/dcp-orchestrator/pull/6)
  is the bounded closure after PR #5. The current immutable application pin is
  `723f99844ef07822d0ec55c452923dd553adeae5`, tree
  `b9519265daaf692bc6d899c86c5c359aca3b782d`; PR #5 remains the prior approved
  event-delivery pin.
- The deterministic defect was packaging identity, not review semantics: the
  stock prompt invokes `ao review submit`, while the renamed DCP bundle contains
  only `dcp-orchestratord`. The existing PATH helper deliberately accepts only
  an executable already named `ao`, so the callback fell through to a PATH with
  no command after the reviewer had produced an approved result.
- The launcher now creates one private reviewer-pane `ao` symlink under DCP
  data with temp-link plus atomic rename, then proves it resolves to the exact
  same embedded executable already passed to the one-shot supervisor. Only that
  pane prepends the private directory. A relative, missing, foreign or changed
  target fails closed before model launch; no global PATH, installed/retired AO,
  `~/.ao`, reviewer network, new credential or unrestricted daemon capability
  is introduced.
- Verdict handling remains the stock CLI-to-daemon-to-existing-SQLite path.
  Its guarded running-row update is atomic; process exit fails only an
  unsubmitted still-running row. Exact-head uniqueness and terminal run states
  continue to prevent a duplicate verdict or automatic retry.
- The old failed run `b65be186-7326-4272-85aa-acfcd39bc938` and
  `orenvlad-ai/dcp-review-lab#1` stay immutable and unmerged. After the merged
  pin is installed and model-free gates pass, live qualification permits one
  new minimal canary/native card, one automatic reviewer/model call, no manual
  Run Review and no retry. Its PR is not merged; an approved saved verdict must
  remain Ready to Merge across app/daemon restart without a second reviewer.

## 2026-08-10 — make the I12 reviewer verdict channel deterministic

- Managed-fork PR [#7](https://github.com/orenvlad-ai/dcp-orchestrator/pull/7)
  is the approved deterministic-result closure after PR #6. The current
  immutable application pin is
  `f4970bd46f55ac75069c569e96b89597cd646b6c`, tree
  `c207b38c685b6c2d071fe9ff1efe3ccee0e01de1`; PR #6 remains the prior
  compatibility-alias pin and historical evidence.
- The failed I3 proof showed that an available exact `ao` command was still not
  deterministic because a model could return its semantic approval without
  choosing to invoke `ao review submit`. The model is therefore no longer a
  control-plane actor: Codex receives a per-run JSON Schema and writes exactly
  one final result artifact after a read-only, web-disabled review.
- The trusted supervisor alone reads that bounded artifact after successful
  model exit, validates the exact worker, stable reviewer terminal, batch, run,
  PR URL and target SHA, and posts it through the existing session-scoped
  daemon route. One guarded SQLite update completes the existing running
  `ReviewRun` only while the same open non-draft PR row still owns the exact
  head. This is the sole verdict mutation; no migration, artifact database,
  service, watcher, callback chat or second state authority is introduced.
- Missing, ambiguous, malformed, foreign, duplicate, late, closed/draft and
  stale-head results record no verdict and start no automatic retry. The model
  receives no DCP daemon variables, GitHub token, network tool or private `ao`
  alias. The exact-binary alias remains only for other stock reviewer-adapter
  compatibility and is not the Codex success path.
- Model-free tests cover schema validation, every identity/head binding, a
  single atomic winner under concurrent duplicate submission, malformed and
  foreign rejection, credential/network absence, no model-command dependency,
  restart persistence without another reviewer and absence of a new migration.
  Managed-fork CI passed full source checks plus native arm64 package/artifact
  gates; one unrelated stock browserruntime timeout passed on the single
  failed-job rerun without a source change.
- The failed I2/I3 runs and `dcp-review-lab` PRs #1/#2 remain immutable and
  unmerged. Final live qualification uses one new native card and one fresh
  unmerged minimal PR only after exact install/preflight. Its entire model
  budget is one worker call and one automatic reviewer call, with no retry,
  manual Run Review, second chat impulse or test-PR merge. A saved approval must
  remain Ready to Merge across canonical app/daemon restart without another
  reviewer. Technical completion still does not create owner acceptance.

## 2026-08-10 — make the I12 worker launch compatible with installed Codex

- Managed-fork PR [#8](https://github.com/orenvlad-ai/dcp-orchestrator/pull/8)
  is the final bounded worker-side compatibility closure after PR #7. The
  current immutable application pin is
  `5ab85f0010bd120728b8514c84f1fe41fac0ba70`, tree
  `6c0b7fadb5a4525a822b371b10fc2069fc9afa4c`; PR #7 remains the prior
  deterministic structured-verdict pin and historical evidence.
- The I4 native card proved that the review-lab worker never reached a model:
  Codex CLI rejected `--ask-for-approval` because the stock adapter placed that
  root-only option after `exec`. The empty I4 card is retained unchanged; it is
  not reused, retried or represented as a model call.
- Non-bypass Codex worker modes now use the installed CLI's supported
  `approval_policy="on-request"` config override and explicit
  `--sandbox workspace-write`. The reviewer adapter removes that worker policy
  before enforcing its existing `approval_policy="never"`/read-only policy.
  Unknown worker permission modes fail closed. Bypass-mode behavior is not
  widened, and no network, global PATH, user config, service, scheduler,
  watcher, database or authority is added.
- Targeted tests drive the real generated worker command through parser-only
  `--help`, exercise config/feature capability through offline `features list`,
  assert the unsupported exec argument is absent, and cover reviewer policy
  replacement plus unknown-mode rejection. Managed-fork PR CI passed full
  source and ephemeral native-package jobs on its first exact head.
- The remaining live budget is unchanged: one new native card may make exactly
  one minimal worker model call, followed by exactly one automatic reviewer
  model call. There is no retry, manual Run Review, second chat impulse or
  canary merge; every prior card, run and PR remains immutable evidence.

## 2026-08-11 — scope Codex writes to verified linked-worktree metadata

- The first post-PR-#8 native worker call reached Codex session
  `019fece4-e13f-79b1-b3af-c0e6392ebdb5` and consumed 16,222 tokens. It created
  only the requested untracked marker: Codex's built-in workspace sandbox could
  write the checkout but Git could not create its external worktree index/object
  metadata. Card `dcp-review-lab-4` remains unchanged with no commit, push, PR
  or reviewer run.
- Managed-fork PR [#9](https://github.com/orenvlad-ai/dcp-orchestrator/pull/9)
  is the minimal compatibility closure at merge
  `be3239808c88dff1a0f2a7801fedfb73c61ed789`, tree
  `7fdd7db08e8c37f1fe783538cfea3cba2c55441a`. For non-bypass writable modes the
  adapter parses the concrete linked-worktree pointers, requires one exact
  common `.git/worktrees/<id>` child with a reciprocal backlink, checks the
  top-level/gitdir/common paths against local Git, and adds only that gitdir and
  common `.git` through supported `--add-dir` arguments. Missing, ordinary or
  inconsistent layouts fail before launch.
- The reviewer builder strips the worker's `--add-dir` pairs before enforcing
  `approval_policy="never"`, disabled web search and `read-only`; malformed
  pairs fail closed. Approval/sandbox isolation, network denial, user-config
  isolation and all existing authority boundaries remain unchanged.
- Model-free proof uses the real installed parser and an isolated linked
  worktree. It reproduces the baseline sandbox denial, proves a successful
  `git add` only with both derived roots, covers launch/restore/unknown modes and
  invalid topology, and proves that reviewer argv retains no write root.
- The owner separately authorized up to three fresh worker calls after this
  checkpoint; card 6 consumed one on the distinct network-denial blocker, so at
  most two remain, each on a new native card and only after a distinct proven
  fix.
  An unchanged failure is not retried and the same root cause repeating twice
  stops the flow. Exactly one automatic reviewer call is permitted, only after
  a worker creates the intended commit and fresh unmerged PR; manual Run Review,
  a second chat impulse, canary merge and synthetic owner acceptance remain
  forbidden.

## 2026-08-11 — distinguish stale worker launch identity during install

- The first exact #9 install correctly refused replacement because the I4
  parser-failure row retained a historical `runtime_launch_id` even though its
  activity is `exited`, its tmux pane is a bare shell and no supervisor/Codex
  descendant exists. No model action was running and no bundle mutation
  occurred.
- The install gate still rejects every non-terminated `active` worker without
  consulting process state. For a non-active row with a historical launch id,
  it now validates the exact runtime identities and uses the same bounded
  tmux/process-tree proof as a stale reviewer: a missing pane or bare shell is
  stale, any descendant is active, and malformed or ambiguous state fails
  closed. The installer writes no SQLite state and starts no recovery path.

## 2026-08-11 — authorize one exact synthetic-PR terminal contour

- The ordinary `dcp-lab` entry remains remote-free and cannot commit, push or
  open a PR. The same sole `bin/dcp-ao-submit` entry has one separately explicit
  mode: exact target `dcp-review-lab`, profile `synthetic-pr`, a unique bounded
  lowercase task id and one-line prompt. It verifies the canonical repository,
  remote URLs, clean fast-forwarded main, allowed worktree/Git-dir topology and
  exact typed worker/reviewer configuration before one native worker spawn.
- Managed-fork PR [#10](https://github.com/orenvlad-ai/dcp-orchestrator/pull/10)
  adds only a guarded terminal claim on the existing `ReviewRun` and an
  exact-head squash merge for `orenvlad-ai/dcp-review-lab`. PR
  [#11](https://github.com/orenvlad-ai/dcp-orchestrator/pull/11) preserves the
  typed reviewer through the stock CLI config route. PR
  [#12](https://github.com/orenvlad-ai/dcp-orchestrator/pull/12) makes the
  `DCP:<task-id>` identity fit the stock native card-name limit. PR
  [#13](https://github.com/orenvlad-ai/dcp-orchestrator/pull/13) removes the
  contradictory prohibition on the one required PR while still forbidding
  extras. The first fresh terminal attempt, card `dcp-review-lab-6`, created
  local commit `c92bbef` but proved that its sandbox could not resolve GitHub;
  it produced no remote branch, PR or reviewer. PR
  [#14](https://github.com/orenvlad-ai/dcp-orchestrator/pull/14) permits network
  only when a typed marker, native card 7+, canonical data/worktree/Git paths,
  exact branch and sole fetch/push origin all match. Cards 1-6 and every
  reviewer remain network-disabled. The first post-install canonical submit
  then failed closed before spawn because the strict CLI config mirror did not
  accept that typed field. PR
  [#15](https://github.com/orenvlad-ai/dcp-orchestrator/pull/15) preserves the
  field through exact JSON without exposing a generic flag. Card 7 then created
  the exact commit/PR and the sole reviewer stored approved/no-findings, but the
  terminal candidate still expected the retired prefix and pre-marker config.
  PR [#16](https://github.com/orenvlad-ai/dcp-orchestrator/pull/16) aligns those
  exact checks while keeping cards 1-6 ineligible. Stock native spawn leaves
  both session diff-base fields absent, so PR
  [#17](https://github.com/orenvlad-ai/dcp-orchestrator/pull/17) accepts only
  that paired absence and binds the valid stored/fresh PR base to clean local
  `main` and `origin/main`; partial or unknown base identity still fails closed.
  The GitHub adapter also normalizes an absent provider review to domain `none`;
  PR [#18](https://github.com/orenvlad-ai/dcp-orchestrator/pull/18) accepts only
  that known non-blocking value or `approved`, while empty, unknown,
  review-required and changes-requested values still fail closed.
  The same stock GraphQL batch omitted head-repository identity, so PR
  [#19](https://github.com/orenvlad-ai/dcp-orchestrator/pull/19) requests and
  preserves `headRepository.nameWithOwner`; null/missing values remain empty
  and therefore ineligible rather than weakening exact repository binding.
  PR [#20](https://github.com/orenvlad-ai/dcp-orchestrator/pull/20) adds the
  exact two-task durable admission slice. Model-free preflight then found that
  card 8 and PR #5 were already completed pre-stage evidence. PR
  [#21](https://github.com/orenvlad-ai/dcp-orchestrator/pull/21) therefore binds
  the fresh cohort to cards 9/10 and fixes the browser broker cancellation race
  exposed by source CI. Canary then exposed a false `canonical_main_diverged`
  packet after the first merge advanced exact `origin/main`; PR
  [#22](https://github.com/orenvlad-ai/dcp-orchestrator/pull/22) preserves that
  packet, proves fast-forward ancestry and a clean merge tree, and permits one
  startup-only model-free recovery. Managed-fork PR
  [#23](https://github.com/orenvlad-ai/dcp-orchestrator/pull/23) implements only
  the separately frozen Stage 2 incident, one-shot arbiter and bounded
  same-worker repair contour. The exact current source pin is
  `d5f9fd4b3459596fcb2d79efc0023bad4f7f0aa0`, tree
  `8f192acb5fe3e54997e098c7069605b7d916db1d`.
- Eligibility binds exact project/session/task/prompt, clean base, worktree,
  private/common Git dirs, branch, one ready PR and its author/base/head, one
  structured approved no-findings verdict, exactly one successful named
  `dcp-review-lab` check, no unresolved thread, and fresh OPEN,
  MERGEABLE/CLEAN provider facts. Missing, foreign, duplicate, skipped, neutral
  or unknown values fail closed.
- Only the trusted daemon claims and merges. The model has no merge command or
  credential. Success stores one provider merge SHA on the same durable run and
  projects the card to `Merged`; the synthetic repository has no deploy and no
  deploy is fabricated. Provider uncertainty is terminal with no automatic
  retry, while restart can only reconcile an already-claimed action from exact
  merged provider facts.
- PRs #1/#2/#3 and every earlier card/run remain immutable. Card 6 and card 7
  consumed two of the three-worker ceiling; one unused emergency worker call
  remains. The exactly one reviewer allowance is consumed by card 7's approved
  exact-head run, so terminal closure is model-free and creates no new card or
  reviewer. There is no manual Run Review, second chat impulse, general
  auto-merge, arbiter, Release Train, production deploy or owner-acceptance
  synthesis.
- Final qualification installed exact fork
  `1cca0af6043e3930b184e79d1f871b88ca402e01` and reconciled the existing
  approved run without another model call. The daemon claimed once and
  squash-merged PR #4 at `202ca32a0e8d563c6c478d094073246383720e5d`.
  Card 7 was `Merged` before restart and remained the same `Merged` card/run/SHA
  after controlled restart; counts stayed one review, one run and seven cards,
  card 8 was absent, and exact retained panes were bare shells. PRs #1/#2/#3
  stayed open and unchanged. The repository reported zero deployments, so the
  terminal record contains no fabricated deploy fact.

## 2026-08-11 — authorize the bounded two-stage I13 block

- The owner approved two sequential autonomous stages. Stage 1 is the current
  authorized implementation: a mechanical Admission Controller for exactly two
  new synthetic `dcp-review-lab` tasks. Stage 2 is conditionally approved only
  after Stage 1 has a green terminal handoff, the curator independently checks
  it and dispatches a fresh executor. The Stage 1 executor does not implement
  or invoke Stage 2.
- Stage 1 reuses native card/session/worktree identity, the stock-compatible
  worker and automatic reviewer contours, the existing daemon and its existing
  SQLite. It may add only additive admission/event/action records needed for
  one durable FIFO owner/lease and passive waiter. It adds no second registry,
  database, daemon, queue service, watcher, scheduler, heartbeat, general retry
  loop, Release Train or new UI column.
- Exactly two new task/card identities may independently execute and receive at
  most one automatic reviewer for each initial exact head. Only one task may
  own terminal merge. The other persists without a process, timeout, model
  poll or token use. First-task completion causes one model-free reconciliation
  of the next durable waiter.
- The second candidate proceeds when exact facts prove it fresh and compatible.
  If deterministic relevant-main rules prove an ordinary refresh is needed,
  the daemon may create one bounded wake/resume for the same worker and one
  fresh automatic review for its new exact head. Real conflict or ambiguity
  creates one structured arbiter-needed packet and no arbiter call. Duplicate
  review/wake/claim/merge, stale ownership, manual orchestration and ambiguous
  identity fail closed across restart.
- The separate live allowance is two initial worker calls and two initial
  reviewer calls. At most one additional worker wake plus fresh reviewer is
  allowed only for the proven ordinary-refresh path. The preferred happy-path
  canary uses compatible changes, two workers, two reviewers and two strictly
  sequential terminal merges. Old PRs, cards and runs stay immutable.
- Stage 2 is limited to one event-driven arbiter v1 for a persisted proven
  ambiguity. Its exact schema, model budget and mutation authority must be
  bounded by the fresh executor before implementation. Production, `wb-core`,
  real repositories, Telegram, Human Gate, owner-acceptance synthesis and a
  general arbitration/model loop remain prohibited.

## 2026-08-11 — qualify I13 Stage 1 admission

- Managed-fork PRs #20, #21 and #22 merged at
  `64f71ae0b45d725eeeb7bb00d7b964d5e68258ed`,
  `0107508ee8fb074dfc69486360f1793b4e7f79ac` and
  `b23b519cd532555c203863586032d157fc1c8c13`. Reviewed pin PRs #129, #130
  and #131 merged at `5551d5a4bd4cb172a1f9e17639c6e8eb012f6ca3`,
  `90f258a3943b824a31481bfaf132b06b442891f7` and
  `5b2375f2be367ff28cbb086c2e3f6dfe36c90314`. Fork CI, pin baseline,
  deterministic build/install and packaging gates are green.
- The clean bounded cohort is native card 9 `DCP:i13-admit-a` and card 10
  `DCP:i13-admit-b`. Their initial workers used 20,437 and 20,055 tokens;
  their one automatic reviewer each used 25,539 and 9,976 tokens. Total Stage 1
  live use is four model calls and 76,007 tokens. No worker refresh or extra
  review occurred.
- Verdict completion assigned durable FIFO sequence 1 to card 10 / PR #6 /
  exact head `3afd3d4cbcc2fe4a6bf2fde3e747213e5c874d53` and sequence 2 to card 9 /
  PR #7 / exact head `649c60cbe6c8542f0a3d20b05b11ae5c54a79263`. Each had one approved
  no-findings run and one successful named check. The daemon merged PR #6 once
  at `5e65c167d8d9d36d70c89fc8e9b5b07497905645`, then PR #7 once at
  `dbaf01b05e85ffffa4c843a905e2fe5229eaf0da`.
- The initial second-row reconciliation conservatively persisted a false
  `canonical_main_diverged` incident when GitHub's PR base remained the stale
  pre-first-merge SHA. PR #22 preserves that original structured packet, then
  permits only startup recovery after proving the provider base is an ancestor
  of exact current `origin/main` and the current-base/head merge tree is clean.
  Recovery made no model call and left `refresh_wake_count=0`.
- Two controlled starts preserved both succeeded admission rows, FIFO order,
  exact leases and task/session/PR/head/base/review/run/merge identity. Counts
  stayed seven reviews, nine runs and ten cards; no card 11, duplicate run,
  duplicate merge or active DCP model process appeared. Native termination then
  reclaimed only the two canary worktrees while retaining both audit cards as
  terminal `Merged`. Stage 2 was neither implemented nor invoked and remains
  contingent on independent curator verification and fresh dispatch.

## 2026-08-11 — freeze the pre-runtime I13 Stage 2 arbiter v1 contract

- The independently checked Stage 1 handoff and fresh-executor dispatch satisfy
  the owner-approved entry condition for contract design, but do not themselves
  activate runtime. The reviewed
  [Stage 2 contract](I13_STAGE2_ARBITER_V1_CONTRACT.md) must merge and reach the
  clean canonical checkout before application-source work or any new model
  call.
- Only a fresh cards 11/12 `merge_conflict_or_ambiguity` packet may derive one
  `dcp.review-lab.global-release-incident/v1` generation. The recovered
  historical `canonical_main_diverged` packet, routine waits, staleness and
  failed CI are ineligible. Equal event replay reuses the same full SHA-256
  incident identity; drift fails closed.
- The arbiter receives one immutable 16,384-byte maximum structured input with
  approved task/scope, exact candidate/history/diff, review/check, complete
  relevant frozen queue and exhausted mechanical-recovery digests. It receives
  no transcript, credential or mutation tool.
- Exactly one `gpt-5.6-sol`/`xhigh` call is allowed with a hard 16,384-token
  rollout budget set before launch. The only positive decision assigns the
  incident's same worker to one `same_worker_conflict_repair`; the only other
  result is a reasoned safe stop. Duplicate/late/stale/foreign/malformed output
  and restart replay are inert without a second call.
- Qualification intentionally creates a real add/add conflict with exactly two
  new native tasks. The total ceiling is two initial workers, two initial
  reviewers, one arbiter, one selected-worker repair and one fresh reviewer:
  seven model calls. A resolvable result must reach fresh exact-head review,
  admission and terminal merge; safe stop is truthful failure, not success.
- The daemon/SQLite remain the sole authority. No second daemon/database,
  queue/scheduler/watcher/heartbeat/timer, UI card, general arbitration loop,
  HumanGate, owner acceptance, production target or unrelated repository is
  authorized.

## 2026-08-11 — pin the bounded I13 Stage 2 source before runtime

- Contract PR [#133](https://github.com/orenvlad-ai/dev-control-plane/pull/133)
  merged at `0b12727a99ddc448b5d19c252615b7bf13bd7113` before runtime source work
  or a new model call. Managed-fork PR
  [#23](https://github.com/orenvlad-ai/dcp-orchestrator/pull/23) then passed
  protected source/package CI and merged at
  `d5f9fd4b3459596fcb2d79efc0023bad4f7f0aa0`, tree
  `8f192acb5fe3e54997e098c7069605b7d916db1d`.
- The source adds only migration 0052, one daemon-local durable incident/action
  row, exact frozen-input and decision validation, one stateless Sol/xhigh
  launch and one bounded same-worker repair path. Launch is fenced by the
  persisted `model_call_count=1`; restart artifact replay revalidates all frozen
  facts and cannot create a second call.
- The source/pin merge is not live qualification. The installed receipt remains
  the exact Stage 1 fork until deterministic build/install replaces it. Cards
  11/12, the incident and every Stage 2 model call remain unused at this point.

## 2026-08-11 — correct and immutably pin the pre-provider arbiter launch

- Live cards 11/12 used only their two initial workers and two initial
  exact-head reviewers. Card 11 merged once; card 12 durably opened exact
  conflict incident
  `dcp-global-release-2694dbd8b3d4897063603d7a8607ca516aa2f8e05c5a3c39cf56d8e3f18c3c60`
  under the global freeze.
- The first package set its one-call fence, but Codex 0.145 strict parsing
  rejected the top-level `rollout_budget.*` keys before a Codex session or
  provider request. This consumed no model call and cannot authorize a
  replacement incident, generation, card or general retry.
- Contract correction PR
  [#137](https://github.com/orenvlad-ai/dev-control-plane/pull/137) merged at
  `4d3e0736635579db053516813e2d5944f903f777`. Managed-fork correction PR
  [#24](https://github.com/orenvlad-ai/dcp-orchestrator/pull/24) then passed
  protected source/package CI and merged at
  `2fbd9bf4789a5b388fb12c58d9347968ed06e6de`, tree
  `ada1ccead3e9920bf1e658ac3c136bc61acea6ab`.
- Migration 0053 preserves the failed fence in one bounded audit row and
  re-arms only the same incident/generation once. The corrected launcher pins
  `codex-cli 0.145.0`, strictly parses the complete structured
  `features.rollout_budget` configuration model-free and retains the original
  one-arbiter/seven-total-call ceilings. All other launch/model/result failures
  remain terminal.

## 2026-08-11 — replace unsupported arbiter response-schema composition before inference

- The exact correction pin `2fbd9bf4789a5b388fb12c58d9347968ed06e6de`
  passed strict config and created Codex session
  `019ff21d-4cde-72d1-b70d-49efd3cd1c17`, but the provider rejected root
  `oneOf` with exact `invalid_json_schema` before inference, result output or
  token use. The incident, input digests and global freeze remained unchanged;
  no worker wake or decision exists.
- The response schema will use only required constant/enum scalar fields plus
  trusted cross-field validation: exact owner/path and maxima `1/1` for
  `assign_recovery`, or empty owner/path, maxima `0/0` and one bounded code for
  `safe_stop`. Root composition is forbidden.
- A new additive audit row must prove exact source/session/error, absent result
  and absent token record before the same incident/generation may be re-armed
  once. This is the final pre-inference correction, not a second model call;
  every other failure remains terminal.
- Managed-fork [#25](https://github.com/orenvlad-ai/dcp-orchestrator/pull/25)
  passed protected source/package CI and merged at
  `182f7a1a95d4e1705de63355e65599b9d79f2c12`, tree
  `3f4c9c7a6efc9a7164852eeaafde4423ef9cec6f`. The integration pin does not
  claim installation or resumed live qualification.

## 2026-08-11 — retain fail-closed Stage 2 BLOCKED terminal state

- The exact final bundle ran the sole Sol/xhigh inference under its persisted
  16,384-token ceiling. Session `019ff23c-7cbf-7ee1-9567-30c6693f95fe`
  consumed 11,583 tokens and returned `assign_recovery` for the exact card 12
  worker/path, but with `maxFreshReviews=0` instead of the contract-required
  `1`.
- Trusted validation rejected the artifact. The same incident is now
  `failed/submit_failed`, call count `1`, with no decision digest, recovery
  owner/path, wake, fresh review or second merge. Controlled restart preserved
  that state and created no duplicate process or action.
- The model budget is exhausted; modifying the result or calling another
  arbiter is unauthorized. Preserve the frozen incident and OPEN/DIRTY PR #9.
  Exact evidence and totals are in
  [I13 Stage 2 terminal BLOCKED evidence](I13_STAGE2_BLOCKED_EVIDENCE.md).

## 2026-08-12 — authorize one exact-incident successor arbiter attempt

- The owner explicitly authorized the minimal corrective cycle in
  [the successor contract](I13_STAGE2_ARBITER_SUCCESSOR_CONTRACT.md). It applies
  only to the existing card 12 / PR #9 incident and requires its own reviewed
  contract merge before managed-source work, then reviewed source/pin merges
  and deterministic installation before runtime or a model call.
- The original `failed/submit_failed` row, first result/input/schema artifacts,
  their digests, Codex session, 11,583-token use and counters remain immutable.
  One additive exact successor-attempt row uses incident generation 1 and
  attempt generation 2; it cannot overwrite the original artifact directory or
  become a generic retry surface.
- Exactly one additional `gpt-5.6-sol`/`xhigh` inference is authorized under a
  hard 16,384-token budget. This raises the incident ceiling to two actual
  arbiter inferences and the Stage 2 live ceiling to eight model calls. There is
  no re-arm, third arbiter, replacement incident/card/PR or borrowed allowance.
- `maxWorkerCalls` and `maxFreshReviews` are removed from the model-owned
  decision. The trusted daemon fixes the positive policy at `1/1`, validates it
  in the accepted-decision and downstream-action transactions and consumes at
  most one existing card-12 recovery path. The model still chooses only the
  exact owner/path or one bounded safe stop.
- An accepted decision remains exact incident/attempt/input/digest-bound.
  Controlled restart at the persisted-decision boundary precedes any wake; a
  second restart follows the terminal outcome. Duplicate/late/stale/foreign or
  malformed result, restart replay and every post-call failure remain inert or
  terminal without another model call.
- Managed-fork [#26](https://github.com/orenvlad-ai/dcp-orchestrator/pull/26)
  passed source/package CI and merged normally at
  `baac2921a6901e836cbbf3759c3c42f5259ea37c`, tree
  `a1ecbb79bd14a48ee270e6ce320633f2227cfe46`. This integration revision pins
  only that reviewed source and extends the installer’s no-active-model proof
  to the exact successor runtime; it does not claim install, inference,
  decision, wake, review or merge.

## 2026-08-12 — authorize one model-free exact-result validation recovery

- The single successor call used session
  `019ff3a1-7f0e-79e2-baa5-cbaa1cc6fc37` and 12,271 tokens, then produced exact
  result SHA-256
  `9b5ff7847db2533e56bdbbc424114e5bea8e5e3c352ad1d029a99deaba05c172`.
  Trusted validation failed closed only because its allowlist omitted exact
  nested frozen-envelope `mergeTreeEvidenceDigest`
  `a19c64060d0f41320b6bf652c47ff5c58810ebec0416d003963bc1b4fcdf524f`.
- The owner already authorized model-free direct-path defect corrections. The
  separate
  [validation recovery contract](I13_STAGE2_SUCCESSOR_VALIDATION_RECOVERY_CONTRACT.md)
  permits one additive exact audit row, one allowlist correction and one atomic
  validation of the unchanged result. It permits zero model calls and no
  artifact edit, result replacement or generic late-result path.
- The recovery must stop at `decided`/zero-wake. Only a later controlled
  restart can consume the original deterministic `1/1` downstream policy.
  Mismatch or repeated replay is terminal/inert, with no further correction.
- Managed-fork [#27](https://github.com/orenvlad-ai/dcp-orchestrator/pull/27)
  passed source/package CI and merged normally at
  `6f1b5f9828853b6c597d6e6b82fda52ced097b61`, tree
  `7cb55d85073af960944a645e2fbe13503e98bf4f`. Migration 0056 binds one audit
  row to the observed artifact/session/token/contract facts; startup admits
  only the exact nested frozen digest and atomically stops at
  `decided`/zero-wake. This pin revision claims no install or live recovery.

## 2026-08-12 — retain fail-closed successor BLOCKED terminal state

- Pin PR [#145](https://github.com/orenvlad-ai/dev-control-plane/pull/145)
  retained exact head `90e58613b0a327a85adba10da8d1d0c93f71f475`; authorized Actions run
  `31556202627` / job `94075049657` passed the baseline and both audit steps.
  The PR merged normally at
  `0df41738a68d89aa1a9239d577d69cd5aff23d5b`, and exact managed source
  `6f1b5f9828853b6c597d6e6b82fda52ced097b61` then passed deterministic
  prepare/build/install/preflight.
- First startup created the one exact migration-0056 audit row and accepted
  only unchanged 1,705-byte result artifact
  `9b5ff7847db2533e56bdbbc424114e5bea8e5e3c352ad1d029a99deaba05c172`
  model-free. The generation-2 attempt reached `decided`/zero-wake with exact
  decision digest
  `237472879b22a8db65c5a3a0715510dc17aee1de93c45eaab45dde538cefb939`.
- The required controlled restart consumed the one authorized card-12 wake.
  Stock native resume returned `ErrNotRestorable` before process/model launch
  because the preserved idle session has empty `agent_session_id` and
  `runtime_launch_id`. The row became terminal `failed/repair_launch_failed`,
  retaining one decision, one call and one wake, with no new head, recovery
  review or merge.
- A post-terminal controlled restart was inert. Counts remain 11 review runs,
  four admissions, one successor attempt, one accepted successor decision, one
  wake and zero recovery reviews. PR #9 remains OPEN/DIRTY on exact reviewed
  head `d4fcb68051ae113ed497d02151a759800ee85633` and admission sequence 4 remains
  the same incident row. The incident has exactly two actual arbiter
  inferences total and Stage 2 has six calls / 132,785 tokens total.
- Preserve this state as truthful technical `BLOCKED`. Another worker wake,
  model call, repair, replacement card/PR/incident or retry policy is not
  authorized. Exact evidence is in
  [I13 Stage 2 successor terminal evidence](I13_STAGE2_SUCCESSOR_TERMINAL_EVIDENCE.md).

## 2026-08-12 — authorize one exact card-12 fresh worker-session recovery

- The owner explicitly authorized the separately governed
  [fresh worker-session recovery contract](I13_STAGE2_CARD12_FRESH_WORKER_RECOVERY_CONTRACT.md)
  after the immutable `failed/repair_launch_failed` terminal predecessor. The
  reviewed contract must merge before managed-source implementation; separate
  source/pin merges and deterministic install/preflight must complete before
  runtime or a model call.
- The exact incident, accepted generation-2 decision, recovery owner/path,
  card/session `dcp-review-lab-12`, task `i13-arbiter-b`, worktree, branch,
  PR #9 and old head stay fixed. The consumed wake and old empty native
  `agent_session_id`/`runtime_launch_id` remain immutable; recovery generation
  1 records one fresh runtime/action/launch/Codex session identity separately.
- Exactly one fresh stateless worker call is permitted under a hard 16,384-token
  ceiling. Its bounded structured envelope contains only original task/scope,
  exact PR/head/current-main/conflict evidence and the same-branch repair. It
  excludes the old worker transcript and arbiter reasoning and may produce only
  one guarded new head for the existing branch/PR.
- At most one fresh context-free reviewer may inspect that exact new head.
  Approved/no-findings output, the named successful check and current
  OPEN/non-draft/MERGEABLE/CLEAN provider facts remain prerequisites for the
  existing admission sequence 4 and one terminal merge of PR #9.
- Any drift, duplicate, late, stale, foreign, malformed, restart ambiguity or
  exhausted worker/reviewer budget fails closed and ends truthfully. No new
  card/task/native session/worktree/branch/PR/incident, arbiter call/decision,
  transcript replay, second worker/reviewer attempt or general retry is
  authorized.
- Managed-fork [#28](https://github.com/orenvlad-ai/dcp-orchestrator/pull/28)
  passed required source/package CI and merged normally at
  `fbcf4929f9192f7cce9c5097b0bc6a449d28e663`, tree
  `2ce917e525690d0cd05e060b552dc8bd072b8a15`. Migration 0057 creates only the
  exact subordinate recovery row; the daemon separately fences one stateless
  worker and one context-free reviewer before reusing existing admission and
  merge gates. The integration installer now refuses replacement while that
  exact worker action is active. This pin claims no install or live recovery.
- Exact source `fbcf4929f9192f7cce9c5097b0bc6a449d28e663` was then
  deterministically installed and passed preflight. Its first controlled start
  created the exact generation-1 row but failed closed before the worker fence
  at `preflight_failed/identity_drift`, retaining 0/0 worker/reviewer calls and
  no runtime/session/artifact/head. Model-free proof showed the conflict path
  is `M` from current main, while the source incorrectly required `A`.
- Managed-fork [#29](https://github.com/orenvlad-ai/dcp-orchestrator/pull/29)
  passed source/package CI and merged normally at
  `75a14431a3433f581755f2e0ec096814e3e9ecb1`, tree
  `a993819f30776ca595d5687f098ec00b98d67ba2`. Migration 0058 preserves the
  exact zero-call failure in a separate audit, re-arms only the same unused
  row once and refuses rollback after its call fence; source changes only the
  exact path-status assertion. This pin claims no install or live recovery.

## 2026-08-12 — retain card-12 fresh worker recovery BLOCKED terminal state

- Correction pin PR
  [#149](https://github.com/orenvlad-ai/dev-control-plane/pull/149) retained
  exact head `74a12daaaece1a9e136f538ab60de27c010ecbf5`, passed baseline run
  `31596234569` and merged normally at
  `60acb70fd1d4ca603286f6930e899116317395d0`. Exact source
  `75a14431a3433f581755f2e0ec096814e3e9ecb1` then passed deterministic
  prepare/build/install/preflight.
- Migration 0058 preserved the prior zero-call failure in exactly one audit
  row and re-armed only the same unused recovery generation. The one fresh
  stateless worker call used separate Codex thread
  `019ff5f3-c655-7ea2-9213-6e137f148285`, reached the exact add/add conflict
  and wrote only the permitted local resolution.
- The worker exhausted its hard 16,384-token rollout budget before commit or
  guarded push. The recovery row is terminal `failed/worker_process_failed`,
  revision 5, with worker/reviewer counts `1/0`, no new head, review/check,
  admission rebind or merge. PR #9 remains OPEN/DIRTY/CONFLICTING on old head
  `d4fcb68051ae113ed497d02151a759800ee85633`.
- A post-terminal controlled restart preserved all identities, rows,
  timestamps and counters. There is no recovery Codex/supervisor process and
  no duplicate session, wake, review, admission or merge. Original arbiter and
  successor artifacts retained their exact digests.
- Preserve this state as truthful technical `BLOCKED`. The sole worker budget
  is consumed; no second worker/reviewer attempt, manual completion or general
  retry is authorized. Exact evidence is in
  [card-12 fresh worker recovery terminal evidence](I13_STAGE2_CARD12_FRESH_WORKER_RECOVERY_TERMINAL_EVIDENCE.md).

## 2026-08-13 — authorize one exact model-free continuation of the preserved card-12 rebase

- The owner explicitly authorized the separately governed
  [model-free rebase continuation contract](I13_STAGE2_CARD12_MODEL_FREE_REBASE_CONTINUATION_CONTRACT.md)
  after the immutable `failed/worker_process_failed` terminal predecessor. The
  contract must merge before managed-source implementation; separate source
  and pin merges plus deterministic install/preflight must precede runtime.
- The failed fresh-worker row, its one consumed worker call, zero reviewer
  calls, artifacts, Codex thread and unknown exact token total remain
  immutable. No worker or arbiter model call is added.
- Only the exact unfinished detached rebase in the same card-12 worktree is
  eligible. One trusted daemon action may stage the already permitted two-line
  resolution, non-interactively continue exactly one stopped commit, move only
  the existing local branch ref from its old head and push the same remote ref
  once with an exact old-head force-with-lease.
- Preconditions bind the complete task/card/session/worktree/repository/PR/
  branch/incident/admission identity, predecessor row and artifact digests,
  old remote head, unchanged current main, full rebase metadata, one AA path,
  exact resolved bytes, no other status path and no active mutator. Drift is a
  stop, not authority to reconstruct or retry.
- The one resulting exact head may receive at most one fresh context-free
  reviewer. Only approved/no-findings, the successful named check and fresh
  CLEAN/MERGEABLE provider facts may rebind admission sequence 4 and permit the
  existing daemon to terminally merge PR #9 once. No replacement identity,
  second continuation/reviewer, manual bypass or general Git recovery path is
  authorized.

## 2026-08-13 — pin the reviewed exact model-free continuation source

- The governing contract merged as dev-control-plane PR #151 at
  `e17fa9080434b5642667392fb06db61cf35f19bd` after the baseline check passed.
- Managed-fork [#30](https://github.com/orenvlad-ai/dcp-orchestrator/pull/30)
  implements only that contract. Its `source` and `package` checks passed and
  it merged normally at `a7b5476fb886bcbb6bbd91aa89da17966547b3b8`, tree
  `53525c260b4de1ed749aeb4c89f4e085e433c9bd`.
- Migration 0059 adds one exact subordinate continuation row, immutable
  predecessor/evidence bindings, one model-free action fence and one fresh
  reviewer fence. The installer now refuses replacement while that action or
  reviewer path is active.
- Pinning records reviewed source only. No installation, runtime Git action,
  new PR head, review, admission rebind or merge is claimed until deterministic
  install/preflight and the governed live proof complete.

## 2026-08-13 — separate the exact PR-base snapshot from current main

- Exact source `a7b5476fb886bcbb6bbd91aa89da17966547b3b8` passed deterministic
  build/install/preflight and remained stopped. Migration 0059 did not run and
  no model-free action or reviewer fence was consumed.
- Read-only REST, GraphQL, SQLite and Git proof established that PR #9's exact
  provider base is `dbaf01b05e85ffffa4c843a905e2fe5229eaf0da`, current main is
  `b34b31b5443890e69128db2862726950a6bbac0d`, and the former is an ancestor of
  the latter. Equating them is a pre-action implementation defect, not drift in
  either governed identity.
- The separately reviewed
  [provider-base correction contract](I13_STAGE2_CARD12_MODEL_FREE_PROVIDER_BASE_CORRECTION_CONTRACT.md)
  permits only one immutable correction row and exact independent validation
  of provider base/current main/ancestry. It adds no task, action, worker,
  arbiter, reviewer, retry or merge authority.

## 2026-08-13 — pin the exact provider-base correction source

- The correction contract merged as dev-control-plane PR #153 at
  `9610bf1a8fa41f631ca5ed336d0d9b0313d7d73f` after its baseline check passed.
- Managed-fork [#31](https://github.com/orenvlad-ai/dcp-orchestrator/pull/31)
  passed `source` and `package` and merged normally at
  `b22d8961fcc367d414510a5daae53eab19bd2578`, tree
  `f10fed7982187a3a963b85c93285e641c41c289d`.
- Migration 0060 and the exact validator implement only the reviewed
  provider-base/current-main/ancestry distinction. Pinning claims no repeat
  installation, runtime action, model call, review, rebind or merge.

## 2026-08-13 — retain card-12 model-free continuation BLOCKED terminal state

- Exact source `b22d8961fcc367d414510a5daae53eab19bd2578`, tree
  `f10fed7982187a3a963b85c93285e641c41c289d`, passed repeat deterministic
  build/install/preflight. The first controlled bundle start ran migrations
  0059/0060 once.
- Native terminal restoration concurrently launched ordinary workers for
  preserved cards 11 and 12 before the continuation action fence. They opened
  fresh Codex threads and reported 33,238 and 33,573 tokens. This irreversibly
  exceeds the contract's zero-worker-call condition even though neither worker
  created a commit, push or PR.
- The continuation row failed closed as `failed/identity_drift`, revision 1,
  with trusted worker/arbiter/action/reviewer counters `0/0/0/0` and no new
  head, review, check or merge. Startup also replaced the exact detached rebase
  and resolved bytes with a branch-attached `UU` conflict-marker state.
- Preserve the result as technical `BLOCKED`. PR #9 remains open at old head
  `d4fcb68051ae113ed497d02151a759800ee85633`; no fresh reviewer, admission
  rebind or merge exists. No restart, reconstruction or further continuation
  is authorized. Exact proof is in
  [card-12 model-free continuation terminal evidence](I13_STAGE2_CARD12_MODEL_FREE_REBASE_CONTINUATION_TERMINAL_EVIDENCE.md).

## 2026-08-13 — authorize exact cold-start quarantine and card-12 recovery

- The owner separately authorized the reviewed
  [cold-start quarantined recovery](I13_STAGE2_CARD12_COLD_START_QUARANTINED_RECOVERY_CONTRACT.md)
  after the immutable `failed/identity_drift` result. It supersedes rather
  than reuses the violated zero-worker-call continuation authority and keeps
  both unauthorized native restoration calls plus 66,811 tokens as evidence.
- The daemon must durably classify exact governed cards 11/12 model-free before
  any session reconcile, tmux/native restore or stored worker launch. Missing,
  ambiguous or unreadable state stops before runtime creation; unrelated
  eligible sessions keep stock restore behavior. Cold first-start, crash and
  restart tests must prove zero governed worker launches.
- One subordinate recovery generation may create an immutable backup and then
  reconstruct only the exact branch-attached card-12 `UU` marker state into
  the known one-commit rebase on current main. It may write only the exact
  authorized two-line bytes and push only the existing PR #9 branch once with
  old-head force-with-lease.
- No worker or arbiter model call is authorized. At most one fresh context-free
  reviewer may run on the exact new head; the existing check, admission rebind
  and terminal merge gates remain mandatory. Any mismatch or worker launch is
  terminal.
- Contract, managed source, immutable pin/install guard and deterministic
  install/preflight are separate sequential reviewed stages before runtime.

## 2026-08-13 — pin exact cold-start quarantine and recovery source

- The governing contract merged as dev-control-plane PR #156 at
  `623c3896a50d410e5b305ed08cf29abdc40b5b23` after its baseline check passed.
- Managed-fork [#32](https://github.com/orenvlad-ai/dcp-orchestrator/pull/32)
  passed `source` and `package`, received a semantic/security review with no
  findings, and merged normally at
  `032e16aa3025858eeddecc1a25e87d4ec8ea4f18`, tree
  `cc519e93923e02d59463bbe14dd77192a237ce95`.
- The daemon opens SQLite, validates schema and atomically establishes/reads
  the exact governed startup quarantine before constructing runtime or session
  restoration. Exact cards 11/12 cannot enter stock restore/resume paths;
  unknown or partial state fails startup closed while unrelated sessions keep
  stock behavior.
- Migration 0061 and the one exact subordinate recovery preserve the failed
  predecessor and 66,811-token error, permit zero worker/arbiter calls, one
  guarded model-free action and at most one exact-head reviewer. The integration
  installer now refuses replacement while that recovery is active. Pinning
  claims no installation, runtime start, Git action, review, rebind or merge.

## 2026-08-13 — pin exact cold-start physical-tool correction

- Deterministic installation of PR #32 and its first controlled start proved
  the pre-restoration quarantine: cards 11/12 remained bare shells with zero
  descendants and no governed worker call. The recovery then failed before
  backup/action as `failed/preflight_or_backup_failed`, revision 1, with
  worker/arbiter/action/reviewer counters `0/0/0/0`.
- The sole defect was model-free and exact: `/opt/homebrew/bin/gh` is a symlink,
  while the trusted verifier intentionally accepts only a physical regular
  file. Its resolved physical file and expected digest were independently
  proven before source work; Git/PR/runtime identity did not change.
- The contract's bounded direct-path correction is managed-fork
  [#33](https://github.com/orenvlad-ai/dcp-orchestrator/pull/33). Migration 0062
  preserves the exact failed row in an immutable audit and may re-arm only that
  same row at revision 2. Execution requires that exact audit, and the code
  changes only the trusted path to the pre-proven physical binary while
  retaining the digest.
- PR #33 passed `source` and `package`, received an exact-head semantic/security
  review with no findings, and merged normally at
  `798e9bfb8f75846d846f2ec2d4dfc9ec0076573b`, tree
  `e5668c51fbc3c7aae872cafbe4759fc405fa0677`. It adds no identity, model call,
  action, reviewer, retry policy or authority. Pinning claims no repeat install
  or live action.

## 2026-08-13 — pin exact preserved AUTO_MERGE correction

- Deterministic installation of PR #33 and the next controlled start again
  proved the pre-restoration quarantine with bare cards 11/12 and no governed
  worker. Recovery failed before backup/action as
  `failed/preflight_or_backup_failed`, revision 3, at counters `0/0/0/0`.
- The newly proven direct-path fact is Git's regular `AUTO_MERGE` ref from the
  same preserved conflict. Exact tree `3eba7b0dec18c759875b2b33a8d7d2379caaa6a1`,
  file digest `dac6e5a895aed94e8cd5a0f1a39b1c23f0201393e621c635ed228070710c13ed`
  and blob `1af18aad20e3aab90ea7f1c617d330abc3b08de9` reproduce the unchanged marker
  bytes. A copied exact Git proof showed normal `reset --hard` removes the ref
  and restores the clean old-head basis.
- Managed-fork [#34](https://github.com/orenvlad-ai/dcp-orchestrator/pull/34)
  preserves only that exact second zero-call failure in migration 0063, re-arms
  only the same row at revision 4, validates all ref/object identities and seals
  the ref into the immutable backup. It passed `source`/`package`, exact-head
  semantic/security review and merged normally at
  `04a967c26499a482fbff9a204bab046d79d2a2e2`, tree
  `fedee6276e8ce4a492d3c298aaf4bf843179c8bc`.
- The correction adds no identity, model call, action, reviewer, retry policy or
  authority. Pinning claims no final repeat install or live action.

## 2026-08-13 — record terminal cold-start recovery result

- Exact source `04a967c26499a482fbff9a204bab046d79d2a2e2`, tree
  `fedee6276e8ce4a492d3c298aaf4bf843179c8bc`, passed deterministic
  build/install/preflight before the terminal attempt. Its pre-restoration
  quarantine classified cards 11/12 before runtime construction and prevented
  every new worker launch.
- The one daemon-owned model-free action sealed backup digest
  `82d0e5834375c380069e7d48a7fdb2066371670d92733ce59545718469a4f3dd`,
  reconstructed the exact one-commit rebase and produced clean local head
  `4de6ff1a0b80223a9b32a05ba68cf0b665296081` with the authorized bytes and
  parent. Git retained regular `REBASE_HEAD`; the trusted candidate validator
  rejected it before the guarded push.
- The row is terminal `failed/model_free_action_failed`, revision 7, at
  worker/arbiter/action/reviewer counts `0/0/1/0`. Remote PR #9 remains on
  `d4fcb68051ae113ed497d02151a759800ee85633`, with no fresh review/check,
  admission rebind or merge. One controlled restart advanced quarantine
  verification to 4/4 and produced no duplicate activity.
- The source/pin/install/live chain and the immutable 66,811-token prior
  restoration error are recorded in
  [cold-start recovery terminal evidence](I13_STAGE2_CARD12_COLD_START_QUARANTINED_RECOVERY_TERMINAL_EVIDENCE.md).
  The bundle is stopped; no further reconstruction, push, reviewer, merge or
  retry is authorized.

## 2026-08-13 — authorize exact retained-candidate REBASE_HEAD finalization

- The owner separately authorized the reviewed
  [exact REBASE_HEAD finalization contract](I13_STAGE2_CARD12_REBASE_HEAD_FINALIZATION_CONTRACT.md)
  after the immutable cold-start terminal result. It creates a new subordinate
  finalization row and never re-arms or rewrites the failed revision-7 recovery,
  sealed backup, action fence, counters or artifacts.
- Regular `REBASE_HEAD` may be treated as inert historical evidence only when
  its exact bytes and mode, `ORIG_HEAD`, clean candidate
  `4de6ff1a0b80223a9b32a05ba68cf0b665296081`, sole parent/path/bytes, branch,
  remote old head, provider base/current main, quarantine, process and SQLite
  identities all match. The general operation-residue guard remains strict.
- The daemon may perform one model-free adoption and one exact old-head force-
  with-lease push without rebase, reconstruction or any local Git write. At
  most one fresh context-free reviewer may run on the new exact head before the
  existing admission rebind and normal terminal merge gates.
- No worker or arbiter call, replacement identity, second push/reviewer,
  manual Git action or general retry is authorized. Contract, source and pin/
  install-guard changes must be separate reviewed merges and deterministic
  stopped preflight must pass before the single live attempt.

## 2026-08-13 — pin exact retained-candidate finalization source

- The governing contract merged as dev-control-plane PR #161 at
  `9465a84ec44f72f6b7c245ebddeac22d722108ae` after its baseline check passed.
- Managed-fork [#35](https://github.com/orenvlad-ai/dcp-orchestrator/pull/35)
  implements migration 0064 plus the exact daemon-local finalizer. It preserves
  the failed revision-7 recovery and sealed backup, performs no local Git write,
  and accepts regular `REBASE_HEAD` only inside the full exact conjunction.
- PR #35 passed source/package CI, received exact-head semantic/security review
  with no findings and merged normally at
  `6f53f74f456b869c98bb82d928f671b54672808a`, tree
  `0fab2ee443d8bf20a0efcc524851e8c9589e6dd9`.
- The integration installer refuses replacement while the one finalization row
  is active. Pinning adds no runtime authority and claims no install, action,
  push, reviewer, admission rebind or merge; the PR-34 bundle remains stopped.

## 2026-08-13 — pin exact finalization audit-query correction

- Installed source `6f53f74f456b869c98bb82d928f671b54672808a` passed preflight. Its first
  start held quarantine 5/5 and launched no governed worker, then failed before
  the action fence as `failed/identity_drift`, revision 1, counters `0/0/0/0`.
- The proven cause was finalizer reuse of the historical tool-path and
  `AUTO_MERGE` queries whose recovery-state predicates describe authorized
  rev2/rev4. Both correctly return zero for terminal rev7 even though each
  immutable audit exists once. All candidate/provider/backup/admission facts
  remained unchanged, with no push or fresh review.
- Managed-fork [#36](https://github.com/orenvlad-ai/dcp-orchestrator/pull/36)
  adds migration 0065 with immutable correction identity
  `52490d8c01eccc8f02984ec4d863895c0215950590cfc5309d00a1525eb8f11b`.
  It re-arms only the same finalization row and binds the correction, both
  original audit identities, terminal predecessor and quarantine 6/6+ without
  weakening either historical query.
- PR #36 passed source/package CI and exact-head semantic/security review, then
  merged normally at `e15a6d22f83876b240fa61889b6821bd49904f28`, tree
  `48d1266abc44de79bda0ca2865558d259325fc0d`. Pinning claims no repeat install,
  action, push, reviewer, admission rebind or merge.

## 2026-08-13 — pin exact finalization revision-gate correction

- The repeat PR-36 install/preflight passed and runtime remained stopped. A
  final source-level prestart proof found that executor preflight still required
  obsolete revision 0, contradicting migration 0065 and engine predecessor
  validation which exclusively authorize the audited re-armed revision 2.
- Managed-fork [#37](https://github.com/orenvlad-ai/dcp-orchestrator/pull/37)
  introduces one shared exact revision-2 constant for both gates and regression
  coverage proving revision 2 reaches the unchanged preconditions while revision
  0 fails closed. It adds no migration, row mutation or runtime authority.
- PR #37 passed source/package CI and exact-head semantic/security review, then
  merged normally at `1f1e8cedf44d30773568f8801710f1371b14a47b`, tree
  `4523bfacf690c15f75c155ccfc2f14831db7b2f2`. Pinning claims no install,
  action, push, reviewer, admission rebind or merge.

## 2026-08-13 — preserve exact post-push finalization and block on private CI

- The installed PR-37 bundle passed preflight. Its sole live action consumed
  one action/push and moved PR #9 from old head `d4fcb68051ae113ed497d02151a759800ee85633`
  to exact candidate `4de6ff1a0b80223a9b32a05ba68cf0b665296081`.
  It then failed closed as `provider_identity_drift`, revision 4, counters
  `0/0/1/0`, because GitHub advanced the PR base snapshot from historical
  `dbaf01b05e85ffffa4c843a905e2fe5229eaf0da` to exact current main
  `b34b31b5443890e69128db2862726950a6bbac0d` after the successful push.
- The exact-head required check failed before any runner step on its initial
  attempt and one ordinary rerun. GitHub's annotation says recent account
  payments failed or the spending limit must be increased for this private
  repository. No reviewer, admission rebind or merge occurred.
- Managed-fork [#38](https://github.com/orenvlad-ai/dcp-orchestrator/pull/38)
  adds migration 0066 with immutable correction identity
  `d140ac8daec5f311a278050c6e1e0b33011e28b0ee2ee9b52bb357f3b34ac923`.
  It preserves the consumed action and exact first provider/check observation,
  re-arms only inspect-only revision 5 and requires current main only on the
  post-push path. The engine cannot execute a second push from that state.
- PR #38 passed source/package CI and exact-head semantic/security review, then
  merged normally at `15b51450b391fdc1ae0f172bbbf95275a6388030`, tree
  `f819398a7e78ffa68630b62a3234e6e95283be57`. Runtime remains stopped and no
  reviewer/admission/merge may proceed until a human resolves GitHub billing
  and the same exact-head required check succeeds.
- The exact PR-38 source was deterministically installed/preflighted while
  stopped at `2026-08-13T16:25:14Z`; receipt SHA-256 is
  `b362851fb43d772a7cbd1d1a85ebeaa6980f78a5e1b96d87f6ae74bb2b5eb0dc`.
  Goose remains 65 and migration 0066 is unapplied. The technical terminal
  result is `BLOCKED`, because starting the inspect-only continuation against a
  known-failed external check would consume the sole reviewer before the human
  prerequisite can be fixed. No corrected-runtime start/restart, reviewer,
  admission rebind or merge was performed.

## 2026-08-13 — complete exact retained-candidate finalization after external unblock

- The owner explicitly directed continuation after the curator removed only
  the GitHub Actions billing blocker. The synthetic repository became public
  after a bounded full reachable-history review found zero secret-pattern
  matches; task, PR, branch and head identities remained unchanged.
- The same run `31718637023`, attempt 3, job `94521518361` executed checkout
  and the repository test on exact head `4de6ff1a...` and returned `SUCCESS`.
- One installed PR-38 start applied migration 0066 and entered only the
  inspect-completed path. It did not re-execute the consumed action or push.
  Exactly one `gpt-5.6-sol` context-free reviewer used 24,178 tokens and
  returned structured approval with empty findings.
- Admission sequence 4 rebound to the new exact run/head/current main, and the
  existing terminal gate squash-merged only PR #9 at
  `5bfd20d3b3f5b7d9d9ccb02500b742a917e6ea01`. The finalizer is `succeeded`
  revision 9 at `0/0/1/1`.
- One controlled restart advanced quarantine from 7/7 to 8/8 while preserving
  one correction, review, admission and merge and launching no model. The
  bundle is stopped. This is technical completion, not owner acceptance.

## 2026-08-14 — authorize policy-driven DCP Lab happy-path v1

- The owner removed the qualification-only total-card/cohort and globally
  consumed reviewer ceilings for future exact synthetic lab tasks. The current
  contract is [DCP Lab happy-path v1](DCP_LAB_HAPPY_PATH_V1_CONTRACT.md). It
  supersedes those ceilings only for new tasks after the separately reviewed
  source/pin/install gates; cards 1-12 and every historical row, artifact,
  counter and token record remain immutable.
- The only PR-capable scope remains exact public
  `orenvlad-ai/dcp-review-lab`, target `dcp-review-lab`, profile
  `synthetic-pr`, canonical paths/remotes and one native branch/ready PR per
  unique task id. `dcp-lab` stays remote-free and every other repository or
  target fails closed.
- Each accepted task persists one canonical payload/digest and native
  card/session/worktree/branch identity in the existing daemon SQLite. Equal
  replay returns that identity; conflicting replay rejects. Card number is no
  longer authority. Crash recovery may finish only an already reserved
  identity and cannot create a replacement.
- At most three DCP model actions may be active globally. Durable action slots
  and FIFO waits are daemon-local and event-driven; queued work, CI and
  admission consume no process, timer, heartbeat, poll or token. One task has
  at most one active worker and one exact head at most one active reviewer.
- Each task receives one initial worker and fresh context-free review. One
  structured findings result may cause one same-identity repair worker and one
  fresh review for its new exact head. A second findings verdict or machine,
  budget, stale-head or ambiguous failure is terminal; there is no general
  retry loop and no verdict is reused across heads.
- The existing admission table/lease is generalized without rewriting its
  historical rows. Every eligible approved exact head enters one durable FIFO
  line; one trusted daemon owner revalidates current head/base/check/review/
  CLEAN/MERGEABLE immediately before ordinary expected-head squash merge.
  Main advancement reconciles the next waiter model-free. Conflict or
  ambiguity persists an incident and stops without arbiter, HumanGate or
  manual bypass.
- The stock native cards/columns remain truthful UI. The exact cards-11/12
  pre-restoration quarantine remains active only for those historical sessions
  and cannot act as a future-task ban. No second task-card service, registry,
  daemon, database, scheduler, watcher, hosted surface, production target or
  external service is authorized.
- Delivery is a reviewed contract PR, reviewed managed-source PR(s) with green
  `source`/`package`, a separate exact pin/install-guard PR with green
  `baseline`, deterministic backed-up install/preflight and model-free fixtures
  for at least four future tasks, three-slot cap, per-head review, head change,
  duplicate submit/SCM events, FIFO admission, restart and terminal dedupe. The
  executor must not launch `chat-probe-b` or any live worker/reviewer and must
  leave the exact new bundle stopped for the owner's canary. Technical
  completion is not owner acceptance.

## 2026-08-14 — pin reviewed happy-path v1 source and remove the adapter ceiling

- Managed-source [PR #39](https://github.com/orenvlad-ai/dcp-orchestrator/pull/39)
  passed exact-head semantic/security review plus required `source` and
  `package`, then merged normally at exact commit
  `5c9ce30bfdd61bc8cc49106c9eb3d62fbf867abd`, tree
  `45660cc8293d78dded4235f9406586fd8771077d`.
- The immutable lock advances only to that merge and accepts installed source
  `15b51450b391fdc1ae0f172bbbf95275a6388030`, tree
  `f819398a7e78ffa68630b62a3234e6e95283be57`, as its one verified predecessor.
  This pin stage claims no installation or runtime/model activity.
- Canonical `bin/dcp-ao-submit` retains exact target/profile/task validation,
  adds an independent public-provider proof, provisions the exact stock
  project configuration and calls only hidden typed `ao dcp submit`. It no
  longer scans the cards-11/12 cohort, predicts a card number or invokes normal
  `spawn`. Equal and conflicting replay are decided durably by the daemon.
- Historical linked worktrees keep their exact allowlist. Every future
  `dcp-review-lab-<n>` worktree requires one matching happy-path policy row;
  card number alone grants nothing. The installer additionally refuses any
  claimed/running durable future model action before bundle replacement.

## 2026-08-14 — repair live card-13 admission catch-up and unify status dots

- The exact preserved canary is policy task `chat-probe-b`, native session/card
  `dcp-review-lab-13` / 13, PR #10 at head
  `e467d1a44668294d59cca15a756c6cef18e4b247`, approved ReviewRun
  `152048c0-6720-4397-9430-df975a453807` and admission sequence 5. One worker
  and one reviewer succeeded; no model action is active. The task remains
  `admission_waiting` revision 9 with no lease, merge or error.
- The proven ordering gap is event delivery, not merge authority. Stock SCM
  durably acknowledged CLEAN/MERGEABLE before the admission row existed. The
  first direct terminal read remained passive on transient provider unknown,
  and later identical stock snapshots skipped lifecycle because their semantic
  hashes already matched. No timer, heartbeat, new watcher, restart trick or
  manual merge is authorized.
- Managed-source [PR #40](https://github.com/orenvlad-ai/dcp-orchestrator/pull/40)
  passed exact-head semantic/security review and green `source`/`package`, then
  merged normally at exact source
  `70187c13ab0bc8bac07cd2d9ff27e230b866e087`, tree
  `ee81758b33443a66835f785e2cb178b560808c15`. An unchanged but freshly fetched
  stock SCM event may now signal only an exact durable waiting policy admission
  whose current head is materially OPEN/passing/CLEAN/MERGEABLE. The existing
  terminal merger, process mutex and SQLite FIFO lease still revalidate and own
  every claim/merge; unknown, stale, foreign, conflicting and terminal facts
  remain passive or fail closed.
- The same native session read model now carries only its durable policy state
  and a boolean that is true solely for a running model action. One shared
  mapper drives both central-card and sidebar dots: active worker blue pulse,
  active reviewer yellow pulse, queued worker/reviewer steady blue/yellow,
  passive/human/merge waits steady orange, merged green, failure/incident/exited
  red and idle gray. Reduced motion disables pulse without removing status.
- The immutable lock advances only to PR #40 and accepts installed source
  `5c9ce30bfdd61bc8cc49106c9eb3d62fbf867abd`, tree
  `45660cc8293d78dded4235f9406586fd8771077d`, as its sole replacement
  predecessor. This pin stage claims zero installation, runtime mutation or
  model call. After reviewed pin merge and deterministic install/preflight, one
  controlled canonical start may finish only card 13 through the repaired
  model-free path, followed by one dedupe restart and installed visual/DOM
  smoke. No new worker, reviewer, arbiter, card, task or PR is permitted.

### Controlled-start correction

- Exact source `70187c13ab0bc8bac07cd2d9ff27e230b866e087` was
  deterministically installed at `2026-08-14T08:19:34Z`; receipt SHA-256 was
  `1504d133445f4aa66e3c369356d6f52d9a49736f953cde3808229e77588b53b1`
  and verified backup `i12-20260814T081933Z` was retained. Its first controlled
  start failed closed before daemon wiring with exact error `exact governed
  startup quarantine is unavailable`. Card 13 remained revision 9/waiting,
  admission sequence 5 remained unclaimed and both model actions remained
  succeeded once.
- Read-only history proved cards 11/12 had naturally transitioned at
  `2026-08-14T07:18:16Z` to stock terminal `exited/terminated` after their exact
  admissions succeeded. The prior startup fence incorrectly required only
  `idle/non-terminated`, although every quarantine/admission/recovery identity
  remained exact. Managed-source [PR #41](https://github.com/orenvlad-ai/dcp-orchestrator/pull/41)
  accepts only those two exact lifecycle pairs, rejects mixed/active pairs and
  never restores either terminal runtime. Required run `31783935999` passed
  source/package; ordinary merge is
  `50136576ce287ed0563b54144523ec14ab34d76c`, tree
  `db4ee06ad176c91402cfc852cc63e1e2252148f3`.
- The lock now advances only to PR #41 and accepts installed `70187c13...` /
  `ee81758...` as its sole predecessor. Repeat deterministic stopped install
  and preflight must pass before the next controlled card-13 start. No model
  call, restoration, admission claim, reviewer, merge, new identity or token
  use occurred in the failed start or correction work.

### Creation-base persistence correction

- Repeat deterministic installation of exact source `50136576ce287ed0563b54144523ec14ab34d76c`,
  tree `db4ee06ad176c91402cfc852cc63e1e2252148f3`, completed at
  `2026-08-14T09:00:51Z` with receipt SHA-256
  `0b8744901c8ddf9223ee8bab4add0f645e59bc244888d5d1846b4033d343ee2c`
  and verified backup `i12-20260814T090051Z`. One controlled start passed the
  exact terminal quarantine and launched zero model actions.
- Current provider facts remained OPEN, ready, passing and CLEAN/MERGEABLE. A
  read-only provider/observer fixture proved the existing stock event emitted
  terminal eligibility for card 13; a read-only terminal-engine call then
  failed before claim with `policy task creation base is unavailable`. The
  exact session row had empty `diff_base_sha` and `diff_base_ref`.
- Source review proved `resolveSpawnDiffBase` had computed the creation base at
  provisioning, but stock lifecycle `mergeMetadata` discarded both fields
  before persistence. This hidden lineage precondition, not another event gap,
  prevented the existing sole terminal merger from claiming admission 5.
- Managed-source [PR #42](https://github.com/orenvlad-ai/dcp-orchestrator/pull/42)
  retains both fields for future policy sessions. For the already reviewed live
  row, its post-migration startup repair writes only the exact base/ref when all
  immutable card/task/session/worktree/branch/PR/head/base/review/admission/
  check facts match and zero DCP model actions are active. It owns no process,
  timer, watcher, poller, model call, claim or merge; mismatch is a no-op and
  every existing terminal Git/provider/review/check/FIFO gate remains.
- Exact head `705697df72f4954140904698273587c31cf65ac1` passed semantic/security
  review `4935928889`; CI run `31788673005` completed `source=success` and
  `package=success`. Ordinary merge is
  `f54b597572d7204096cb16581becee067e1febdc`, tree
  `a56f684853989623fe84c15f2a7958ffa03fd95e`.
- The lock advances only to PR #42 and accepts installed `50136576...` /
  `db4ee06a...` as its sole predecessor. This pin stage claims zero runtime or
  model mutation. One deterministic stopped install/preflight and one
  controlled model-free completion plus restart dedupe remain authorized.

### Card-13 terminal completion

- Exact source `f54b597572d7204096cb16581becee067e1febdc`, tree
  `a56f684853989623fe84c15f2a7958ffa03fd95e`, was deterministically installed
  at `2026-08-14T09:55:20Z` with verified backup `i12-20260814T095519Z` and
  receipt SHA-256
  `5f8ce03ca79da650c23c4968eae2e1e9c3deed05dcd57c6d08e108bbe2c6a782`.
- One controlled start repaired only the exact empty creation-base fields and
  reused the stock SCM event, existing terminal merger and FIFO lease. The same
  task/card/head/ReviewRun/admission completed at task revision 10; PR #10
  merged once at `1b3f9fb266370326bbb35283fb51fb5226502c42`.
- Worker/reviewer actions remain exactly two and succeeded; the repair added
  zero worker, reviewer, arbiter or other model calls and zero model tokens.
  Controlled restart preserved one review, one lease and one merge with no
  duplicate; quarantine reached 14/14. The canonical bundle is stopped.
- Installed native/DOM evidence also preserves the single shared card/sidebar
  status projection and active-only reduced-motion-safe pulse. Exact terminal
  proof is [recorded here](I18_CARD13_ADMISSION_STATUS_DOT_REPAIR_SUCCESS_EVIDENCE.md).

## 2026-08-15 — authorize staged phase UI and ordinary future-card arbiter v1

- The owner authorized one sequential four-phase laboratory program under the
  exact [phase UI and arbiter contract](DCP_LAB_PHASE_UI_ARBITER_V1_CONTRACT.md).
  Documentation alone activates nothing. Phase 1 source/install precedes the
  three-task happy-path qualification; only a green qualification permits the
  bounded arbiter source/install; only that installed source permits its three
  live sandbox scenarios.
- One shared typed native-session projection must keep policy PR/CI preparation
  in blue Working, use yellow In Review only for review queue/run, use steady
  green Ready to Merge for admission wait, steady green Merged for terminal
  success and existing Needs You with red emphasis for typed incidents/failure.
  Only a durably active worker/repair or reviewer pulses. Board placement and
  sidebar dot consume the same projection, and terminal native PR facts defeat
  an older secondary `PR open` summary.
- The existing daemon/SQLite may generalize only the bounded I13 pattern: one
  immutable typed incident generation, complete relevant cohort evidence, one
  fresh context-free Sol/xhigh arbiter action, one strict accepted verdict and
  either passive deterministic order/hold, one exact bounded successor repair
  or a fail-closed HumanGate question. The arbiter has no edit, review,
  admission or merge authority and receives no transcript or prior reasoning.
- Holds own no process/timer/poll/token and wake only from an exact persisted
  state transition. Every repair head still requires a fresh reviewer, named
  check and the ordinary durable FIFO terminal merge gate. Restart/replay must
  deduplicate arbiter, repair, review, admission and merge identities. No
  Arbiter column, second daemon/service/database, general retry loop, foreign
  target or production authority is added.

### Phase 1 reviewed source and immutable pin

- Managed-source [PR #43](https://github.com/orenvlad-ai/dcp-orchestrator/pull/43)
  maps durable policy phase to board lane, card status and sidebar dot through
  one typed projection, retains stock placement without a policy state and
  makes terminal native/policy PR facts defeat a lagging `PR open` summary.
  Component/DOM/state tests cover the full forward sequence, active-only pulse,
  reduced motion, stale stock frames and terminal summary reconciliation.
- Exact head `1a57142c67bd761efc496488d1f50afd20825452` passed semantic/security
  review `4940798548`; workflow run `31836221807` completed `source=success`
  and `package=success`. Ordinary merge is
  `01d8905d98ddc7e1ace42c1e6440a4cb6a652e22`, tree
  `3b4a01d924ea582bdc555f9b744ce502ed87ef0b`.
- The immutable lock advances only to PR #43 and accepts installed
  `f54b597572d7204096cb16581becee067e1febdc`, tree
  `a56f684853989623fe84c15f2a7958ffa03fd95e`, as its sole replacement
  predecessor. This pin stage claims no installation, runtime mutation, task,
  model action or token use. Phase 2 remains fenced until deterministic stopped
  installation and model-free preflight pass.

### Phase 1 deterministic installation

- Pin/install-guard PR #175 exact head
  `d370ae83783685590d689b88b37aea29a2a92ea5` passed review
  `4940855923` and baseline run `31836896642`, then merged normally at
  `619431abca3d8a3d7fa75bc949f82b6750f18876`, tree
  `d0a6e3b306c4d1521eae763a6393ebcb0a14b93b`.
- Exact source `01d8905d98ddc7e1ace42c1e6440a4cb6a652e22`, tree
  `3b4a01d924ea582bdc555f9b744ce502ed87ef0b`, passed the canonical
  prepare/build/install/preflight sequence. Installation completed at
  `2026-08-14T20:19:32Z` with backup `i12-20260814T201931Z` and receipt
  SHA-256 `a3f73b2a5c24abe95dc7891ad5768ce33ceb28b6ae79292bc0313546b1edc10f`.
- The installed application is stopped with no run-file or daemon. SQLite
  retains five merged policy tasks, ten terminal model actions, zero active
  model actions and zero nonterminal policy tasks. No live task, model call or
  token was used by source, pin or installation. Phase 2 is now eligible only
  through the canonical typed submit path. Exact proof is
  [recorded here](DCP_LAB_PHASE_UI_V1_INSTALL_EVIDENCE.md).

## 2026-08-15 — keep incomplete policy PR provider facts passive

- The Phase 2 triple canonical submission created cards 18-20 once and reached
  the global ceiling of three active worker actions without exceeding it.
  Cards 18/19 each completed one worker, one fresh exact-head reviewer and one
  trusted merge. Card 20 completed its sole worker, exact ready PR #17 and
  successful named check but received no reviewer.
- The stock SCM observer first persisted a structural PR row and enriched its
  provider identity in a later state update. The old policy gate treated the
  partial snapshot as a complete contradiction and durably failed card 20 as
  `provider_identity_drift`. Re-submission or a second worker is forbidden.
- Managed-source [PR #44](https://github.com/orenvlad-ai/dcp-orchestrator/pull/44)
  makes absent/incomplete provider facts a model-free wait for the next stock
  event while complete contradictory identity still fails closed. Migration
  0068 preserves the exact prior incident in one immutable row and may re-arm
  only task `night-ui-b`, card/session 20, its succeeded worker, PR #17, exact
  head/base and successful named check; it launches no action itself.
- Exact head `a5c78752601818e24e300e9b8ca8a9082773e338` passed review
  `4941087038` and workflow `31839691295` (`source` and `package` successful),
  then merged normally at `7147171e9e2e7fcfcb14cbd1dc25e215d7c86312`, tree
  `3be7ed1acd064faca53702fc7ddcead9a796a10b`.
- The immutable lock advances only to that merge with installed
  `01d8905d98ddc7e1ace42c1e6440a4cb6a652e22` / tree `3b4a01d...` as its exact
  replacement predecessor. This pin stage runs no daemon, migration, task or
  model action. Phase 2 may resume only after reviewed pin merge, deterministic
  stopped install and model-free preflight.

## 2026-08-15 — terminal UI archive must not block policy startup drain

- PR #44 source `7147171e...` / tree `3be7ed1a...` was deterministically
  installed at `2026-08-14T21:04:16Z` with backup
  `i12-20260814T210415Z` and receipt SHA-256
  `0c8bffd3f019c2c2844b0f5ba60dd3c953dec6285f1dccb343d276338543c2b9`.
- Its first controlled start applied migration 0068 exactly once, preserved the
  false card-20 incident in its immutable audit and moved the same task to
  `review_queued` revision 7 with its exact PR/head and one reviewer action.
  The action remained queued at slot 0; no ReviewRun, process, model call or
  reviewer token existed.
- Model-free inspection proved that stock UI Terminate had correctly archived
  already-merged cards 13-17 as terminated/exited shells while retaining their
  session/card/branch/worktree/prompt metadata. Policy startup nevertheless
  required every task's shell to be nonterminated, stopped on card 13 and
  returned before draining card 20. The application was stopped without a
  second launch or state rewrite.
- Managed-source [PR #45](https://github.com/orenvlad-ai/dcp-orchestrator/pull/45)
  accepts a terminated/exited native shell only when its policy task is already
  terminal and all existing identity checks still match. A terminated
  nonterminal task, non-exited shell or metadata drift remains fail-closed. It
  adds no migration, action, retry, timer, model path or authority.
- Exact head `8f7cbfc723581f9395be5b3347f9d306dbfff8dc` passed review
  `4941219173` and workflow `31841271780` (`source` and `package` successful),
  then merged normally at `a96f4ba9410f088401cee8700e092f1f674ad872`, tree
  `bedd8adf2508a8f8fdb692354f146d4353535c4d`.
- The lock advances only to that source with installed `7147171e...` / tree
  `3be7ed1a...` as its exact replacement predecessor. The existing queued
  reviewer remains passive and may start only after this separate pin merge,
  deterministic stopped install and model-free preflight.

## 2026-08-15 — complete the three-task happy-path qualification

- Pin/install-guard PR #178 merged at `1c8f9b0c...`, tree `7afdef1a...`, and
  exact source `a96f4ba9410f088401cee8700e092f1f674ad872`, tree
  `bedd8adf2508a8f8fdb692354f146d4353535c4d`, was deterministically installed
  and preflighted while stopped. Receipt SHA-256 is `865956b3...`.
- The first controlled start accepted archived terminal shells without
  weakening nonterminal identity, claimed the sole queued card-20 reviewer,
  created one exact-head ReviewRun and obtained one empty-findings approval.
  Admission sequence 12 then merged PR #17 once at `b1b58cb9...` through the
  trusted daemon. No replacement task, worker, reviewer or manual merge ran.
- Cards 18-20 are all merged. Their contour contains exactly three initial
  workers, three fresh reviewers, three approved ReviewRuns and three succeeded
  FIFO admissions. Final main contains all three independent intents. The
  maximum active-model count was three; workers used 91,078 tokens and
  reviewers 62,658, total 153,736.
- Controlled restart preserved all terminal identities, the one immutable
  provider-recovery audit, zero active actions and zero duplicates. The bundle
  is stopped. Phase 2 is green and the separately authorized Phase 3 bounded
  ordinary-card arbiter source work may begin. Exact proof is
  [recorded here](DCP_LAB_PHASE2_TRIPLE_QUALIFICATION_EVIDENCE.md).

## 2026-08-15 — pin the bounded ordinary future-card arbiter source

- Managed-source PR #46 implements only Phase 3 of the reviewed staged
  contract. It uses the existing daemon, SQLite and global three-slot
  `dcp_model_action` queue for one immutable ordinary-card incident generation;
  there is no second scheduler, registry, database, poller or timer.
- The exact generation freezes task/admission/PR/head/base/review/check,
  affected-path, cohort and evidence digests. Conflicting replay fails closed,
  restart adopts only exact persisted/live facts and one generation can cross
  the model-call fence once.
- The context-free arbiter is fixed to `gpt-5.6-sol` / `xhigh` and 16,384
  rollout tokens. Its strict verdict can only retain deterministic order/hold,
  authorize one bounded same-task/path successor repair, or ask one HumanGate
  question. It cannot edit, push, review, admit or merge.
- An approved successor must produce a new exact head, pass a fresh context-free
  review and rebind the original FIFO admission before the trusted daemon may
  merge. Active/held incidents remain steady inside the existing Needs You card
  with typed incident, generation, cohort, action and question detail.
- Exact head `4b77a69c11c68930dbeadc5933c7ba1e2145dd68` passed semantic/security
  review plus workflow `31846494241`; PR #46 merged normally at exact source
  `3bc21e11060d07b7f5339365b8df58f82b9c5439`, tree
  `0af68800b32c4ec195722b72cd8cd39f8aafbac3`.
- The immutable lock advances only to that merge with installed source
  `a96f4ba9410f088401cee8700e092f1f674ad872`, tree
  `bedd8adf2508a8f8fdb692354f146d4353535c4d`, as the exact predecessor.
  Runtime remains stopped; migration 0069 and every arbiter call are prohibited
  until this separate pin merge, deterministic stopped install and model-free
  preflight complete.

## 2026-08-15 — make the ordinary future-card incident candidate reachable

- Exact source `3bc21e11...` was deterministically installed with receipt
  SHA-256 `82f30938095551643c8aecf0c5953121348e91f97078867e99d599973f78adfe`.
  Scenario A created two workers, two fresh reviewers, PRs #18/#19, one trusted
  merge and one exact conflict incident. The durable incident remained passive
  with no arbiter row, process, call or token.
- A model-free reproduction against a SQLite backup returned `DCP future
  arbiter candidate is not exact`. The ordinary candidate helper intentionally
  admits only `admission_waiting`, but arbiter reconciliation invoked it after
  the same transaction had moved the task and admission to `incident`, making
  the Phase-3 path unreachable.
- Managed-source PR #47 keeps every ordinary admission call on the existing
  `admission_waiting` gate and adds a separate helper restricted to exact
  `incident` for arbiter derivation and pre-launch revalidation. Its regression
  proves both the positive incident path and the negative ordinary path; no
  queue, capability, launcher, model, token, reviewer, admission or merge rule
  changes.
- PR #47 passed workflow `31848548624` and semantic/security review, then merged
  at exact source `3f31b66cbf93cc3067ca64cc1908b077727dad0a`, tree
  `42ec79b53cc400e9fa8a60b126b2febb61515d4f`. It was deterministically
  installed with receipt SHA-256
  `2b484047b688ffd2ce585d1e3c0491c688c048a0f0fc85aaa93e8bd1d6f761bd`.

## 2026-08-15 — preserve the provider schema rejection and allow one exact successor generation

- Scenario-A generation 1 opened with exact incident
  `dcp-future-arbiter-141e3d64af9568aea9ea1fb6835045060dfd566bc3b21d50ff6f3f90f3f67a52`.
  Codex strict configuration passed, but the provider returned HTTP 400 because
  response-schema `uniqueItems` is unsupported. No inference, result or token
  use occurred. The incident/action remain immutable `failed/launch_failed`
  with logical call count 1 and actual inference tokens 0.
- Managed-source PR #48 replaces `$schema`, `const` and `uniqueItems` with
  enum-backed exact identities while the trusted parser retains identity,
  cohort-set, evidence-set, path and verdict checks. A recursive model-free
  compatibility validator runs before the one-call fence.
- Migration 0070 records the exact provider rejection/schema digest and grants
  only one generation-2 consume for that predecessor. It cannot authorize a
  clean database or mutate/rearm generation 1; only the latest immutable
  generation controls admission after the exact consume.
- Exact head `a2d49d99d248ebce455500084b2f0a0e5e498c7b` passed workflow
  `31850383431` plus semantic/security review and merged at exact source
  `ae2be4995068c2aa532860b7ad1a798ea13752d2`, tree
  `205293679414045bdf1880e0cc435c87ac456e42`. No generation-2 call is
  authorized before the separate pin merge, deterministic stopped install and
  model-free preflight.

## 2026-08-15 — validate the exact generation-2 result model-free

- Source `ae2be499...` was deterministically installed with receipt SHA-256
  `9d2432ce108addd48fd5d30f5061bd644676cc2db7a9df0b150c12ae08f3a267`.
  Migration 0070 was consumed once and generation 2 crossed its one-call fence.
  Codex session `01a002a6-56e1-7781-917b-ff5640953091` used 10,569 tokens and
  produced one valid `successor_repair` result whose 1,158-byte artifact digest
  is `b8d34711413d429d2ae75eccd078c58a6ece778a4b0ad7d606361ce30a51d36d`.
- The daemon falsely persisted generation 2 and its action as
  `failed/launch_failed` immediately after successful process creation. The
  launcher compared the durable 83-byte incident identity with tmux's correct
  shortened opaque handle `dcp-future-arbiter-9e94bbd542baf-631f35f9`; the
  child then completed, but its trusted callback correctly rejected the late
  result against the already-terminal row. No second inference is authorized.
- Managed-source PR #49 adds a read-only runtime handle resolver so create,
  stale-destroy and supervised-process probes all use the exact adapter handle.
  Migration 0071 inserts only for the frozen Scenario-A generation-2 facts and
  records the failed state/action, physical handle, input/schema/result
  digests/sizes, Codex session and token count in a one-way audit.
- On exact artifact/process/provider/task/admission identity, the daemon may
  validate only the unchanged result model-free and atomically queue the one
  existing bounded repair. The failed arbiter action remains immutable. Every
  mismatch makes the audit terminal failed; replay cannot add a generation,
  call or repair action.
- Exact head `ffdec2bd87838b8efe65e1b6dbc34cddc91fd43e` passed workflow
  `31852087643`, semantic/security review
  `PRR_kwDOTydt6M8AAAABJpDoBw`, full Go tests and zero delta lint issues. PR #49
  merged at source `76b272697091bfb684b079bbea9888c882545a46`, tree
  `baaa4de1d20d4d30fbf5e4a6872e8999c4c60b1d`. Runtime validation remains
  prohibited until the separate pin merge, deterministic stopped install and
  preflight.

## 2026-08-15 — recover the exact pre-launch continuation-target failure

- Source `76b27269...` was deterministically installed with receipt SHA-256
  `9905af7cccb2ab5f34bdfdf9f8031d19eed432a7221cd942157e4c1275c8de15`.
  Migration 0071 accepted the unchanged generation-2 result model-free once,
  preserved its 10,569-token audit and queued the sole authorized repair.
- `dcp-model-arb-a-second-worker-2` failed before launch with slot zero, empty
  launch/review identities and `worker_target_invalid`. The exact clean target
  local main `b1b58cb...` was behind refreshed `origin/main` `55e0c64b...` by
  ancestry; the daemon had reused the equality rule intended for a freshly
  refreshed submit target on an existing cohort continuation.
- Managed-source PR #50 leaves new-submit equality unchanged and adds an
  optional continuation validator used only by repair launch and exact-head
  review. It preserves every path/origin/push/cleanliness/managed-worktree and
  public-provider proof, accepting behind state only after `merge-base
  --is-ancestor` succeeds; divergence still fails closed.
- Migration 0072 binds the exact task/session/admission/incident/head/decision,
  applied result recovery, task revision 13 and failed action timestamp. Its
  immutable audit re-arms only the same pre-launch action and restores the
  original strict task/action transition triggers in the same transaction. It
  creates no new action, repair, arbiter generation, token budget or retry rule.
- Exact head `965fb40f5a6424769dc2635dc599bbf522781adc` passed workflow
  `31853597371`, semantic/security review
  `PRR_kwDOTydt6M8AAAABJpKSNA`, full Go/source/package/typecheck/applicable
  renderer gates and a live-DB-backup migration probe. PR #50 merged at source
  `74432568a88f0d21f634af246133d8b1ab28ce68`, tree
  `7d5807c0c4fa6ae026284710ba234e2433befd57`. Runtime repair remains prohibited
  until this separate pin merges and deterministic stopped install/preflight
  passes.

## 2026-08-15 — recover the exact post-repair CI snapshot failure

- Source `74432568...` was installed at `2026-08-15T00:38:11Z` with receipt
  SHA-256 `45181596257c9d4c24ffff9e2a6e534669dc7d0bdac9e2ce7d1e7e9335777ed7`.
  Migration 0072 re-armed only the existing repair action, which completed once
  with 23,741 tokens, made commit `931a696...` on exact main `55e0c64b...`,
  guarded-pushed PR #19 and received one successful named check.
- Stock SCM correctly retained successful check rows for both old head
  `8b3f601...` and current head `931a696...`. The policy validator incorrectly
  required every historical row to equal current head and persisted the exact
  false failure `incident/ci_identity_failed` at task revision 17.
- Managed-source PR #51 ignores only non-current historical rows, passively
  waits if no current-head row has arrived and continues to fail closed on a
  present current-head failure, invalid provider URL or named-check cardinality.
- Migration 0073 immutably binds the exact task/session/incident/repair action,
  two heads, current main, provider PR and both check URLs. It clears only that
  false incident, binds fresh head `931a696...` and queues exactly reviewer
  action 2. It creates no worker, repair or arbiter call and no new service,
  scheduler, poller, admission or merge authority.
- Exact head `89eba5363b498aa2205af1b822bc8fdc142aa392` passed workflow
  `31854720141`, semantic/security review
  `PRR_kwDOTydt6M8AAAABJpOpjQ`, full source/package/backend/typecheck/applicable
  renderer gates and a WAL-consistent live-DB-copy migration probe. PR #51
  merged at source `d37d91bfabb9b66f6a103e18382e1ec6d98f1567`, tree
  `118e64afe88748b61a691de3ad3515e600d72e3c`. Runtime reviewer launch remains
  prohibited until this separate pin merges and deterministic stopped
  install/preflight passes.

## 2026-08-15 — count repaired future-card lineage from exact canonical base

- Source `d37d91bf...` was installed exactly and Scenario A completed. In the
  three-card cohort, tasks `arb-b-two` and `arb-b-one` merged in FIFO order;
  `arb-b-three` then produced one bounded repair head `04100c0...`, one fresh
  approved review and a green named check against current main `51721b5...`.
- The terminal gate still counted `creationBase..head`. That range contained
  the two trusted sibling merge commits already in current main, so the gate
  returned `policy commit lineage exceeds its bounded worker actions` before
  any merge claim. No model action was active and no identity was mutated.
- Managed-source PR #52 retains proof that the immutable creation base is an
  ancestor of the exact head, but counts and merge-scans only commits outside
  the exact canonical base already fetched, fast-forwarded and validated for
  the admission. This continues to cap task-owned side commits at one initial
  worker plus one repair and still rejects merge commits.
- Exact head `d93908cfecb804bb069c8bbb0752ae7da49df40a` passed full source/package
  workflow `31856517507`, exact-head semantic/security review
  `PRR_kwDOTydt6M8AAAABJpXrgQ` and full backend tests. PR #52 merged at source
  `88425a3fffbb9a926f9f0d15a9d60388fa815c98`, tree
  `e241eda7d8838cb769fd036dd9dcc1ae27611586`. Runtime remains stopped until
  the separate immutable pin, deterministic install and preflight complete.

## 2026-08-15 — serialize review-lab baseline refresh with typed submit

- Scenario B's first two typed submits were issued concurrently. Both entered
  the same adapter before its canonical gateway lock, and both fetched/shared
  the mutable baseline. One process fast-forwarded `main` while the other was
  still validating its pre-lock snapshot, so the latter failed before durable
  task identity creation. A later unique retry succeeded and created no
  duplicate, but the adapter boundary was unnecessarily racy.
- The review-lab target path is now only selected before the lock. Fetch,
  fast-forward, provider/repository/worktree validation and native typed submit
  all execute under the existing singleton. The remote-free path is unchanged.
- The adapter fixture fails if a review baseline refresh occurs outside the
  canonical lock and proves the first valid review submit performs exactly one
  locked refresh. This adds no lock, daemon, database, scheduler, model call or
  retry policy.
