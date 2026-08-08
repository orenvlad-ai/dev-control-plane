# Project brief

## Purpose

Keep the governed DCP architecture and one bounded local laboratory entry for
handing synthetic work from a curator to native Agent Orchestrator. This is not
a production control plane.

## Current I8 state

- Official Agent Orchestrator `v0.12.1`, commit
  `1df40e93772c2c48e916870d9c3ddf8f29a69f84`, remains the pinned foundation.
  The Electron UI, Go daemon, SQLite authority, projects, sessions, tmux
  worktrees and Codex adapter are retained through one exact patch queue.
- Git owns the immutable pin, provenance, patch, build/install/gateway scripts
  and adapter—not a copy or fork of the upstream tree. Managed source and every
  generated artifact remain under explicit canonical `DCP_AO_LAB_ROOT`.
- The only runtime is native arm64
  `/Users/ovlmacbook/Applications/DCP Orchestrator.app`, bundle id
  `pro.devcontrol.dcp-orchestrator`. Source/dev is build/test only.
- The app is the sole owner of its bundled `dcp-orchestratord` lifecycle.
  Closing its window does not exit; explicit Quit protects active work.
- `bin/dcp-ao-submit` is the sole normal curator door. It serializes exact
  identity/readiness proof and exactly one programmatic worker spawn. It never
  starts npm/source, stops, kills, restarts, replaces or recovers a daemon.
- Manual orchestrator spawn UI and hints are hidden. Native backend/CLI/API
  mechanisms remain for future separately authorized roles.
- I5 isolation remains: Codex uses standard authentication with
  `exec --ignore-user-config --ephemeral --strict-config`, and apps, hooks,
  plugins and multi-agent disabled. I6 process-outcome classification remains:
  Working while live, Idle on zero exit, Exited on machine failure. Exact
  daemon connection variables reach only the one-shot supervisor wrapper and
  are filtered from both the retained shell and the Codex child.
- The package cannot initialize an updater or telemetry and includes no update
  feed, maker/publisher, updater module, analytics client/key/host/identity,
  telemetry reservoir or crash reporter.

## Managed source, artifact and namespaces

`upstream/agent-orchestrator.lock` pins repository, tag, commit, tree,
publication, LICENSE, NOTICE result and patch digest. `bin/dcp-ao prepare`
creates a detached checkout below `DCP_AO_LAB_ROOT`, applies the exact patch and
refuses another diff or untracked source file. An upstream refresh requires a
new reviewed stable pin and clean patch rebase.

The canonical lab root is
`~/Library/Application Support/DCP Orchestrator`. Durable `state/` and `data/`,
managed source/build/evidence and the remote-free `targets/dcp-lab` are isolated
there. Cache is `~/Library/Caches/pro.devcontrol.dcp-orchestrator`; logs are
`~/Library/Logs/DCP Orchestrator`. The app executable, daemon executable,
health service, run-file/socket, fixed port and per-launch instance identity are
all DCP-specific. No installed Agent Orchestrator application or `~/.ao` data is
ever discovered, inspected, migrated or imported.

`bin/dcp-ao build` runs model-free backend tests/build, renderer type/tests and
native packaging. `bin/dcp-ao install` ad-hoc signs the verified artifact and
installs it only at the canonical user-owned path. The receipt binds bundle
path/id, exact upstream commit, patch digest, embedded daemon digest and ASAR
digest. Notarization and a distribution installer are deliberately absent.

## Gateway and adapter

The adapter accepts only target `dcp-lab` and a one-line prompt of at most 512
UTF-8 bytes. It proves the repository root, marker, baseline, no remotes and
that every linked worktree is under DCP data.

Under one submission lock, the gateway either reuses one proven ready exact app
or opens its absolute bundle path from a completely stopped state. Readiness
binds app PID/instance/bundle to daemon PID/executable/service/port/run-file and
browser socket. Stale, foreign, duplicate, unhealthy, port-conflicting or
incomplete facts fail closed and are preserved as evidence. Concurrent submits
therefore produce one app, one daemon and distinct native sessions without
duplicate spawn.

The daemon produces its exact `dcp-orchestrator-daemon` service namespace in
both authenticated status and the run-file. The gateway requires both facts to
agree; it neither infers nor supplies a missing identity.

The adapter registers/verifies the single native project, installs its strict
remote-free policy and calls one `spawn --kind worker --harness codex`. It owns
no registry, database, scheduler, queue, watcher, retry, model loop or reverse
delivery.

## I8 qualification

Model-free gates cover the patch/source boundary, worker isolation/outcomes,
gateway cold/warm/concurrent behavior, fail-closed identities, application
Info.plist/signature/architecture, embedded daemon, license/notice and
telemetry/updater/crash artifact absence. The completed bounded live
qualification used the owner-raised cumulative allowance of five short
marker-only model calls with no automatic retry: one preserved diagnostic
stop-gate followed by these four qualified calls:

1. cold submit while the exact app is off;
2. warm submit while the same app and daemon remain alive;
3. two simultaneous minimal submits.

The cold `dcp-lab-2`, warm `dcp-lab-3` and concurrent `dcp-lab-4`/`dcp-lab-5`
sessions each created its exact isolated marker and reached Idle with no
duplicates. One exact app and daemon remained alive, the UI showed the tasks,
the child connection variables were absent and updater/telemetry/external
network gates were clean. Minimal redacted evidence stays outside Git. Earlier
I7 evidence is immutable diagnostic input and is not deleted or changed.

## Development and delivery

One curator dispatches one direct executor from current `origin/main`. The
executor qualifies before opening one ready PR, uses ordinary CI/review/merge,
fast-forwards the clean canonical checkout, rebuilds/installs from exact merged
main and runs a model-free post-install identity/readiness smoke. Technical
completion never means owner acceptance.

## I9 target design, not current runtime

I9 records the agreed future [DCP v1 target architecture](TARGET_ARCHITECTURE_V1.md).
It selects the existing DCP daemon and SQLite as the sole future local authority,
GitHub as PR/CI/merge/deploy authority, a model-free Admission Controller inside
the daemon, one GitHub Actions Release Train, event-driven Sol `xhigh`
executor/reviewer/arbiter roles, durable model-free waits, bounded review and
release-incident recovery, a compact DCP UI and a separately governed future
fork boundary. It preserves Symphony only as pinned design provenance, not a
runtime dependency, and reserves a default-off provider-neutral history seam
whose future outputs are compact immutable refs/digests rather than task state,
code or transcripts.

This is a documentation contract only. I9 does not implement or activate any
of those target mechanisms and does not create the fork. The current I8 lab,
single curator-to-worker flow, managed upstream pin/patch boundary and all I8
non-implementation restrictions remain operationally authoritative until a
later approved implementation changes them.

## Deliberate non-implementations

The current I8 runtime adds no reviewer, arbiter, DCP role loop, queue,
retry/recovery policy, monitoring, real target, remote, `wb-core`, hosted
service, production UI, reverse delivery, dedicated Git fork, updater,
notarization or distribution
installer. A dedicated DCP fork is the next separately owner-approved
implementation stage after the I9 design contract and is not created here.
Until then the exact pin and repository-owned patch queue remain authoritative.
Upstream capabilities outside the synthetic session and I9 target mechanisms
remain design/capabilities, not authorization to exercise them.
