# DCP Codex curator-to-direct-executor routing contract

direct_executor_routing_contract_revision: 2026-08-16.1
contract_status: owner-approved current routing authority

This document is the authoritative DCP contract for curator dispatch, executor
task identity and owner-visible task routing. It is intentionally separate from
the [Codex executor permission-routing contract](DCP_CODEX_EXECUTOR_PERMISSION_ROUTING_CONTRACT.md),
which remains the sole authority for effective approval, sandbox, network and
writable-root capability. Both contracts must pass: a visible task does not
prove capability, and a capable task is not a valid DCP executor when it was
created as a hidden collaboration subagent.

This contract governs only the Codex curator/task routing layer. It changes no
DCP runtime or product behavior, Worker/Reviewer/Arbiter authority, model-action
accounting, production gate, Human Gate or owner-acceptance rule.

## Proven incident basis

The following bounded 2026-08-15 observations establish a repeatable routing
and protocol defect:

- curator task `DCP · Настройка контура`, thread
  `019fa7f5-5f36-7101-8e07-27f8cdfbab08`, made 16 collaboration
  `spawn_agent` calls;
- that curator reported executor `/root/dcp_provider_identity_i23` as active,
  then, when the owner requested its task link, acknowledged that it had
  started a hidden internal subagent that was not a separate visible task. It
  stopped or transferred the work into a visible user-owned task;
- curator task `WBC · FBS и перемещения · К1`, thread
  `019fef4e-b486-7a71-a397-aff97a54520c`, made three hidden executor-like
  collaboration calls named `stage2_takeover`, `stage3_surfaces` and
  `stage6_cutover_runner`; and
- two other checked recent WBC curator tasks made zero actual `spawn_agent`
  calls. Hidden delegation is therefore not an unavoidable Codex property.

The incident record stores only stable task identities, bounded counts and the
observed routing result. It does not store local session paths, transcripts or
prompt contents. An official OpenAI documentation search found general
multi-agent behavior but no ready product contract that distinguishes a
curator-owned visible executor from a collaboration subagent. This is therefore
a local project-governance contract based on observed task identity and owner
visibility, not a claim about universal Codex product behavior.

## Terms and authority boundary

- **Curator** means the owner-facing discussion task that clarifies scope and
  dispatches work but does not implement the repository change.
- **Direct executor** means exactly one separate, visible, user-owned Codex task
  created through the supported task/thread creation surface. It is a peer task
  with its own durable thread/task identity and observable status.
- **Collaboration subagent** means an internal `spawn_agent`/subagent target
  whose lifecycle is nested beneath another task and which is not the separate
  owner-visible executor card required here.
- **DCP model roles** mean the internal product Worker, Reviewer and Arbiter
  actions governed by DCP runtime contracts. They are not Codex collaboration
  subagents and are outside this prohibition.

Prompt text and owner authority can authorize scope but cannot convert a hidden
agent, fork or discussion task into the direct executor. Likewise, task
visibility does not expand the effective machine capability established by the
permission-routing contract.

## Mandatory direct dispatch

After an owner dispatch, the curator performs exactly one direct dispatch:

1. Prove that no other DCP change task is active by checking visible task state,
   open PRs and relevant branches/worktrees without mutating them.
2. Create one separate visible, user-owned Codex task through the supported
   task/thread creation surface. Never use collaboration `spawn_agent` or a
   subagent as the executor creation surface.
3. Record and verify the source curator thread id, executor thread/task id,
   executor title, pin state, destination repository, worktree, host and the
   required terminal-handoff destination. A surface that cannot expose these
   facts fails before substantive work.
4. Give the task one bounded repository change, the exact authority read order,
   the permission-routing canary, duplicate guards, terminal acceptance gates
   and the instruction to send exactly one final technical handoff to the
   source curator.
5. End the curator turn after dispatch. The curator performs no parallel work,
   monitoring agent, reviewer agent, reporter agent or polling loop.

The executor title and pin are required owner-observability controls, not
business authority. The executor remains pinned for the active chain; the
owner controls later unpinning. The owner must be able to open the card and
observe its current status throughout execution.

## Capability-only canary transition

A task-creation program that cannot pin and report the required permission
profile may create only one capability-only task. That task records the
machine-reported routing fields required by the permission-routing contract and
performs no fetch, branch, file, GitHub or implementation mutation.

- `CANARY_QUALIFIED` ends the capability-only turn. The curator may then send
  the owner-authorized substantive instruction to that same visible task and
  thread identity. The later turn is the one direct executor; qualification is
  not a second executor and is freshly revalidated before substantive work.
- `CANARY_RESTRICTED` performs no substantive work, asks for no command-level
  platform approval and remains a routing defect rather than a Human Gate. The
  curator performs at most one reroute through a qualified lane allowed by the
  permission-routing contract, or stops with its one tooling blocker when no
  qualified lane exists. It must not create a succession of probes.

The canary transition does not weaken the permission contract: saved settings,
prompt text, owner authority or prior-turn capability never substitute for the
current machine-reported context. Platform approval count starts at zero and
must remain zero through terminal handoff.

## Forbidden substitutions

A Codex curator MUST NOT call, request or rely on collaboration `spawn_agent`
or any other internal subagent for delegation of analysis, implementation,
review, monitoring, recovery, takeover, reporting or an executor role.

The following are also invalid substitutes for the one direct executor:

- a fork of the curator or executor task;
- a nested curator or executor-like child agent;
- a hidden monitor, reporter, reviewer, takeover or recovery agent;
- repository implementation inside the owner-facing discussion task; or
- a task without the required separate identity, title, pin, destination and
  terminal handoff.

Internal DCP Worker, Reviewer and Arbiter model actions remain governed by
their existing runtime authority and are not prohibited by this rule.

## Dispatch-defect recovery

The first curator-side `spawn_agent` call is a dispatch defect. On discovery:

1. Stop the hidden agent at the next safe point before any further mutation.
2. Preserve evidence already produced without exposing session paths, prompt
   contents or credentials.
3. Check repository, worktree, branch, PR, host and production state for
   duplicate or overlapping mutations.
4. Select exactly one visible direct executor task as the continuing authority.
5. Reconcile or adopt safe existing work once, then continue without repeating
   completed mutation, model action, review, push, merge or production work.

The defect is not converted into a Human Gate and does not authorize owner
command approvals. Ambiguous or unsafe duplicate state fails closed under the
applicable repository or production contract.

## Acceptance record

Every curator-dispatched chain is accepted only when its terminal record proves:

- zero curator-side `spawn_agent` calls;
- exactly one visible direct executor thread/task id;
- verified executor title, pin, destination repository, worktree and host;
- one machine-backed permission-routing record and zero platform approval
  prompts;
- no nested curator, fork, hidden executor/reviewer/monitor/reporter or
  discussion-task implementation;
- ordinary repository review, CI, merge and final-main gates required by the
  current operating contract; and
- exactly one terminal technical handoff from the executor to the originating
  curator, after which the executor stops.

The handoff reports status, incident findings, exact changed authorities,
tests/checks, PR/head/merge SHA, final main state, platform approval count and
out-of-scope work. It does not ask for owner acceptance and does not synthesize
`Задача принята`.

## Safety invariants

This routing contract does not weaken Human Gates, production safety, protected
review, duplicate guards, credential boundaries or exact destination checks.
Owner or prompt authority can narrow or authorize work within effective
machine capability; neither can widen the machine capability or bypass a
domain gate. A routing-compliant executor must still stop on every owner-only
decision or safety condition required by the current DCP authority.
