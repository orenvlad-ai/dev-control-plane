# DCP Codex executor permission-routing contract

permission_routing_contract_revision: 2026-08-16.2

This document is the authoritative permission-routing contract for Codex
executors used by DCP work. It governs how a task is placed onto an execution
surface before repository work, remote operations or production mutations
begin. It does not grant business authority, expand task scope or replace any
domain-specific safety gate.

Curator dispatch identity and owner-visible executor task routing are governed
separately by the
[DCP Codex curator-to-direct-executor routing contract](DCP_CODEX_DIRECT_EXECUTOR_ROUTING_CONTRACT.md).
The route choices in this permission contract do not authorize collaboration
`spawn_agent`, hidden subagents, forks or nested curators as DCP executors.

## Proven incident basis

The 2026-08-16 Web Vitrina incident established these bounded facts:

- successful executor I2 and FBS executor I11 turns reported effective
  `approval_policy=never` and sandbox `danger-full-access` and ran with zero
  platform approval prompts;
- later I3, I4 and I5 turns created through the then-current programmatic task
  creation surface reported effective `approval_policy=on-request`, sandbox
  `workspace-write` and disabled network, even though the unchanged saved
  `~/.codex/config.toml` requested `never` and `danger-full-access`;
- prompt text and broad owner authorization did not and could not widen the
  effective approval, sandbox or network policy;
- the programmatic creation surface exposed no permission-profile argument, so
  Git metadata, network, SSH, systemd and loopback operations encountered
  platform approval boundaries under the restricted profile;
- the local Codex application binary did not change during the incident.
  Codex permission architecture has evolved, but this evidence does not prove
  a global default change and this contract makes no such claim; and
- reusing the already-qualified terminal I2 turn after a fresh read of its
  machine-reported context restored a zero-prompt lane and completed the
  bounded operational phase.

These are routing facts, not a general statement about every Codex version,
account, host or task-creation surface.

## Authority and evidence order

The effective machine-reported context of the current turn or managed runner
is the sole capability proof. It must identify the actual execution envelope,
not merely the requested settings.

The following are intent or historical evidence only and cannot prove current
capability:

- saved user or project configuration;
- permission settings from a prior turn;
- task prompt text;
- owner authorization, including broad unattended authority;
- a model's statement that it should have a capability; or
- the unchanged presence or version of an application binary.

Owner authorization still defines allowed scope and risk. It can narrow the
use of an effective capability, but it cannot widen the machine-enforced
approval, sandbox, network, filesystem or host boundary.

## Required routing record

Before any substantive executor work, the curator or a capability-only probe
records one bounded routing record containing:

| Field | Required evidence |
| --- | --- |
| Turn or runner identity | Current task/turn id or immutable managed-runner receipt |
| Destination surface | Codex app turn, CLI invocation, programmatic task surface or managed runner |
| Versions | Machine-read Codex app version when applicable and exact Codex CLI/runner version |
| Approval policy | Effective machine-reported value for this turn or runner |
| Sandbox | Effective machine-reported mode for this turn or runner |
| Network | Effective enabled/disabled state, including any relevant sandbox-specific network flag |
| Writable roots | Effective writable roots or unrestricted-host statement, plus the bounded task target |
| Needed capabilities | Exact repository, Git metadata, GitHub/network, loopback, SSH, service-manager, filesystem and other capabilities the task will actually use |
| Destination identities | Exact repository/remotes and, when applicable, host alias, service, loopback endpoint and bounded runtime/data target |
| Platform approval count | Starts at zero and remains part of terminal acceptance |

Missing, ambiguous, inherited-only or model-asserted fields fail closed. Do not
infer an effective value from saved configuration.

## Non-mutating routing canary

The routing canary precedes repository mutation, model-backed substantive work,
remote service action and production mutation. It is deliberately small and
non-mutating:

1. Read the current machine-reported turn or runner context and capture the
   routing record above.
2. Read exact app/CLI/runner versions from the installed binary or managed
   runner receipt.
3. Compare the effective envelope with the task's exact capability inventory.
4. Use only bounded read checks needed to prove the route, such as repository
   readability, filesystem writability metadata, Git/GitHub authentication and
   read-only remote reachability, loopback reachability, or an SSH connection
   that performs no target mutation.
5. Record every platform permission prompt. A qualifying lane has zero.

The canary does not fetch or branch a repository, write a test marker, change a
service, acquire a production mutation gate, alter data, or treat an HTTP/SSH
login success as business authorization. A remote operational canary may open
the one persistent host session that the same bounded phase will later reuse.

If a task-creation surface cannot expose effective settings before its first
turn, it may create only a capability-only turn whose prompt authorizes this
canary and no substantive work. That probe is never treated as the substantive
executor when the creation surface cannot pin the required profile.

For clarity, the capability-only turn itself is never substantive. After a
terminal `CANARY_QUALIFIED`, the direct-executor contract may reuse that same
visible task and thread under route 1 below only after a new owner-authorized
substantive instruction and fresh machine-context read. `CANARY_RESTRICTED`
cannot perform work or request command approval; the curator performs at most
one reroute through a qualified lane or stops with one tooling blocker.

## Qualifying unattended lanes

Work that remains inside a proven read-only or workspace-contained boundary
may use a narrower profile only when every required capability is present and
the task can complete without an interactive platform prompt.

Unattended work that crosses workspace, network or host boundaries requires a
proven non-interactive lane. The normal local lane is:

- effective `approval_policy=never`;
- effective sandbox `danger-full-access`;
- enabled network when the task needs it; and
- an explicitly trusted, owner-bounded repository, host and operation scope.

An equivalently acceptable lane is a managed non-interactive runner whose
immutable launch receipt pins the required approval, sandbox, network,
writable-root and destination capabilities. Full host capability does not
authorize work outside the bounded task target.

If programmatic task creation cannot pin and report that profile, do not use it
for the substantive task. Choose exactly one of these routes:

1. reuse one terminal, already-qualified executor turn after a fresh
   machine-context read and a new bounded task instruction;
2. use one managed runner with an explicitly pinned non-interactive profile; or
3. stop before substantive dispatch and report one tooling/routing blocker.

Do not create a succession of restricted executors to see whether a later one
receives broader permissions. One substantive executor remains the authority.

## Platform prompts are routing defects

A Codex platform permission prompt is not a DCP Human Gate. It proves that the
canary or chosen lane did not match the task's capabilities.

On the first unexpected platform prompt:

1. do not request or forward command-by-command approval from the owner;
2. do not repeat the same command through another spelling or low-level API;
3. leave repository, host and production state at the last safe point;
4. record the exact missing capability and destination; and
5. reroute through an already-qualified turn or explicitly pinned runner, or
   end before work with one tooling blocker.

Only a genuinely missing owner decision, material scope/risk expansion,
security-policy choice, new external destination or other owner-only business
decision is a DCP Human Gate. A missing platform capability, login mechanism or
interactive approval caused by the selected execution lane is not converted
into a Human Gate merely because a person could click through it.

## Operational phase discipline

Each bounded operational phase has exactly one executor and one persistent host
session. The permission canary, query-only evidence, authorized operations and
final readback reuse that session. Do not create one SSH or remote-exec session
per command, and do not run a second executor in parallel.

Production business gates, exact mutation manifests and domain safety rules
remain independently mandatory. A qualifying permission lane proves only that
the executor can carry out already-authorized actions without platform prompts.

## Revalidation triggers

Repeat the routing canary before substantive continuation whenever any of these
changes:

- Codex app or CLI/runner version;
- app relaunch, turn replacement or execution surface;
- programmatic task-create implementation or permission arguments;
- remote-exec, SSH or host-session implementation;
- effective approval, sandbox, network or writable roots;
- destination repository, remote, host, service or bounded data target; or
- the task's required capability inventory.

A terminal qualified turn may be reused only after this fresh read. Prior
qualification is not cached across a changed context.

## Acceptance and handoff

Permission-routing acceptance requires:

- a complete machine-backed routing record;
- exact match between effective and needed capabilities;
- one substantive executor;
- one persistent session per bounded host phase;
- zero platform approval prompts from canary through terminal handoff; and
- terminal reporting of the effective permission profile, versions, route,
  approval count and any remaining capability risk.

Repository tests, CI, review, merge and domain verification remain separate
acceptance gates. A successful canary does not imply owner acceptance.
