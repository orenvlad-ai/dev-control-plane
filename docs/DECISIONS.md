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
  startup-only model-free recovery. The exact current source pin is
  `b23b519cd532555c203863586032d157fc1c8c13`, tree
  `a7ad1f64ee089beaeb2fc4b1f43f8778526997a6`.
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
