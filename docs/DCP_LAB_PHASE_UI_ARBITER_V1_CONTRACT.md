# DCP Lab phase UI and ordinary-card arbiter v1 contract

status: owner-authorized staged laboratory contract
date: 2026-08-15
scope: exact public `orenvlad-ai/dcp-review-lab` future policy tasks only

## Purpose and activation

This contract authorizes one sequential four-phase laboratory program on top
of [DCP Lab happy-path v1](DCP_LAB_HAPPY_PATH_V1_CONTRACT.md):

1. correct the native phase projection;
2. qualify the unchanged happy path with three concurrent tasks;
3. generalize the existing I13 arbiter pattern for typed incidents from
   ordinary future policy cards; and
4. qualify that arbiter with bounded two-card, three-card and HumanGate
   scenarios.

The installed bundle remains the current authority until each corresponding
managed-source merge, immutable pin/install-guard merge, deterministic stopped
installation and model-free preflight complete. A documentation merge does not
activate source, runtime or a model call. Phase 2 may start only after the Phase
1 install. Phase 3 source work may start only after green Phase 2. Phase 4 may
start only after the Phase 3 install. Technical completion is not owner
acceptance.

The existing DCP daemon and SQLite remain the single control and persistence
authority. No second registry, task service, database, daemon, scheduler,
queue service, watcher, heartbeat, timer, polling loop, hosted API, production
surface or parallel merge authority is permitted. Cards 1-12 and all historical
I12/I13 rows, artifacts, counters and evidence remain immutable.

## Exact safety contour

- Runtime work is limited to target `dcp-review-lab`, profile `synthetic-pr`,
  the canonical lab root and exact public repository
  `orenvlad-ai/dcp-review-lab`. `dcp-lab` remains remote-free. Every foreign,
  private, production or ambiguous target fails before mutation.
- Only `bin/dcp-ao-submit` may create the qualification tasks. Each scenario
  uses new bounded task ids and the ordinary future-card path. No manual Git
  push, rebase, reset, PR merge, Run Review or identity substitution is a
  runtime recovery path.
- At most three DCP model actions may be active globally across worker, repair,
  reviewer and arbiter roles. Waiting, CI and admission remain durable and
  model-free. No model call may be created to demonstrate animation.
- Ordinary source and control-plane delivery uses small reviewed PRs, normal
  CI and merge. Managed source never becomes runtime before a separately
  reviewed immutable pin and deterministic installation.
- Historical evidence is never truncated. Old completed synthetic cards may
  be hidden from the active board only through the stock archive/termination
  lifecycle after proving that no action is active.

## Phase 1: one typed forward-only UI projection

The native session read model remains the only source for both the board card
and sidebar dot. One shared typed projection maps the durable policy state to a
phase, board zone, steady color and active-motion bit. Stock session status may
provide a truthful substatus such as `PR open`; it cannot override the policy
phase.

| Durable policy state | Phase / existing board zone | Color | Motion |
| --- | --- | --- | --- |
| `reserved`, worker/repair queued/running, `ci_waiting` | Working | blue | pulse only for a durably running worker/repair model action |
| `review_queued`, `review_running` | In Review | yellow | pulse only for a durably running reviewer action |
| `admission_waiting` | Ready to Merge | green | none |
| `merged` | Merged | green | none |
| `failed` or non-HumanGate `incident` | Needs You | red | none |
| exact latest `human_gate` incident | Needs You | orange | none |
| no policy state and genuinely idle | Idle | gray | none |

Consequences:

- PR creation, draft/open PR, CI and pre-review preparation remain Working.
  `PR open` is a substatus in that phase and never moves a policy card into In
  Review.
- Only queued or running review occupies In Review. An inactive retained shell
  cannot turn `review_running` orange or move it to another zone; the durable
  action bit controls motion, not phase.
- Approved review plus durable admission/merge wait is Ready to Merge and
  steady green. Terminal merged is also steady green.
- Typed ambiguity, HumanGate or terminal failure occupies Needs You. An exact
  `incident` plus latest durable `human_gate` verdict/status uses the primary
  label `Needs your decision` and steady orange styling. Older failed action or
  stock `review_failed` state cannot override it. A technical failure/incident
  without that exact Human Gate remains red. There is no Arbiter column.
- A policy state transition has a monotonic phase rank for the normal path:
  Working -> In Review -> Ready to Merge -> Merged. A later-arriving stock SCM
  summary cannot cause a visual bounce to an earlier or different phase.
- When durable terminal policy/PR facts say merged, an older secondary SCM
  summary may not render `PR #... open`. Enriched link metadata may be retained
  only after terminal lifecycle is reconciled from the native fact.
- Card and sidebar use the same projection function, including the same color
  and activity bit. Accessibility text, card size and lane layout remain
  stable. `prefers-reduced-motion` disables pulse without removing the steady
  color or accessible state.

Component, DOM and state-machine tests must cover every mapping, the full
forward sequence, inactive queued/running distinctions, terminal stale-summary
reconciliation, card/sidebar equality, no visual bounce and reduced motion.

## Phase 2: three-task happy-path qualification

After Phase 1 is installed and old terminal cards are stock-archived from the
active board, submit three near-simultaneous unique tasks that make three
non-overlapping simple file changes. The unchanged ordinary policy must prove:

- three and only three native task/card/session/worktree/branch/PR identities;
- no more than three globally active model actions;
- exactly one initial worker and one fresh context-free reviewer per exact head
  when all verdicts have empty findings;
- exact review and admission identities, one FIFO merge owner at a time and
  three sequential trusted merges whose final main contains all changes;
- no duplicate task, card, session, action, review, admission, PR or merge;
- installed board/sidebar evidence for the forward phase sequence and
  active-only motion; and
- one controlled safe restart that preserves the terminal identities and
  creates no duplicate activity.

Record exact model/action ids, roles, models, reasoning settings, input/output/
total token accounting, PR heads, review runs, admission sequences and merge
SHAs from durable/provider facts. Observation must not introduce a product
poller or any extra model action.

## Phase 3: ordinary future-card arbiter

### Trigger and incident identity

Mechanical reconciliation always runs first. It may resolve an unchanged
candidate, a proven irrelevant main advance or another rule whose outcome is
fully determined by exact facts. The arbiter is eligible only after that
contour persists a typed relevant conflict, incompatible main advance or
structured ambiguity that deterministic rules cannot safely resolve.

One immutable incident generation binds at least:

- task/card/session/worktree/repository/branch/PR identity;
- exact candidate head, creation/provider base, observed current main and
  admission sequence/generation;
- incident kind and normalized affected paths/modules;
- exact checks, review run/verdict and mergeability facts; and
- the relevant cohort identity and digest when more than one policy card is
  affected.

The existing daemon derives and persists the identity once. Equal submit,
startup reconciliation, provider event or webhook replay returns the same row
and action. Conflicting identity fails closed. There is at most one arbiter
model call and one accepted verdict for one exact incident generation.

### Passive cohort and event-driven wake

Relevant siblings are durably held, not terminally failed. A hold owns no
process, pane, timer, heartbeat or token. Only persistence of the exact verdict,
a predecessor terminal main advancement, a new exact reviewed head or a Human
Gate response may schedule model-free reconciliation. Siblings outside the
relevant path/module cohort continue under the normal global three-slot rule.

### Context-free evidence envelope

The arbiter is a fresh isolated `gpt-5.6-sol` / `xhigh` action under a hard
16,384-token rollout ceiling, with no daemon/GitHub credential, network tool,
shell or control-plane command. Its bounded canonical input contains only:

- each task's current intent and immutable task digest;
- exact heads/bases and bounded normalized diff/path/module facts;
- PR, check, review, mergeability and admission facts; and
- the complete relevant cohort picture, including FIFO order and held/terminal
  ownership.

It receives no worker/reviewer transcript, previous arbiter reasoning or stale
result. Oversize, missing, foreign, ambiguous or digest-mismatched evidence
fails before launch. The trusted daemon, not the model, fixes all action/review
ceilings and mutation scope.

### Structured verdict and authority

The response schema is strict and non-compositional. It distinguishes at least:

- `deterministic_order_hold`: retain a named FIFO/cohort order and wake only on
  the exact predecessor event;
- `successor_repair`: name one exact task, incident generation, approved
  bounded repair/rebase objective and affected paths; and
- `human_gate`: fail closed with a short specific owner question and no code
  mutation.

The arbiter cannot edit, push, review, admit or merge. A trusted one-shot result
supervisor validates exact incident/action/input/result identities and persists
at most one verdict transactionally. Missing, malformed, late, duplicate,
stale or foreign output produces no decision or retry.

A resolvable verdict may schedule only the named bounded successor repair for
that task and exact incident. That action retains the same task/card/session/
worktree/branch/PR, may change only the approved paths, and is limited to one
call for that incident generation. Its new exact head must pass a fresh
context-free reviewer, named check and the ordinary FIFO admission/terminal
merge gate. The arbiter never bypasses those gates. A second unresolved
conflict for the same generation, mutually exclusive intent or insufficient
evidence becomes one HumanGate and stops without guessing.

### UI and restart

An incident or active arbiter remains in the existing Needs You zone with a
clear incident/arbiter substatus and steady styling. Exact terminal HumanGate
uses the shared primary label `Needs your decision` and steady orange board and
sidebar projection; non-HumanGate failure remains red. Details inside the
existing card expose incident kind, generation, cohort, action state and exact
HumanGate question. No new board column is added and arbiter activity does not
pulse the worker/reviewer phase dot.

Controlled restart preserves the incident, cohort hold, arbiter action/result,
accepted verdict, repair allowance and wake ownership. Startup may reconcile
only exact persisted/live facts and cannot create a second arbiter, worker,
reviewer, admission or merge.

## Phase 4: bounded arbiter qualification

All scenarios use unique ordinary policy task ids and only the exact public
synthetic repository. Between scenarios, stock-archive completed cards from the
active board while preserving every audit row.

### Scenario A: two-card resolvable conflict

Two tasks change the same bounded area. The first advances main; the second
persists a real typed conflict/main-advance incident. Exactly one arbiter
generation chooses deterministic order/hold or one successor repair. The
second task waits model-free, performs only the approved bounded repair,
receives one fresh exact-head review/check and merges through the ordinary
admission gate. Final main contains both intents with no duplicate or lost
change.

### Scenario B: three-card cohort

Three tasks make controlled compatible changes to one shared file/module. The
arbiter envelope includes the complete relevant cohort and fixes the order.
Held siblings wake only after the relevant persisted main-advance event; each
uses at most its exact authorized repair generation and fresh review before
FIFO admission. At a safe held point, restart the canonical app/daemon and
prove persistence plus no duplicate arbiter or worker. Final main contains all
three intents.

### Scenario C: intentionally ambiguous intent

Two tasks state mutually exclusive requirements that cannot safely coexist.
Exactly one relevant incident generation reaches `human_gate`; the arbiter
does not mutate code and produces one concise question. Both affected cards
remain durably understandable in Needs You as applicable. This is the expected
successful terminal outcome. The executor must not synthesize an owner answer
or bypass the gate.

## Terminal acceptance and evidence

The program is technically complete only when:

- every Phase 1/3 contract, source and pin PR is reviewed, green and normally
  merged, with exact commits/trees and install receipts recorded;
- all Phase 2 tasks and all resolvable Phase 4 tasks merge through the trusted
  daemon path, while Scenario C remains at its single HumanGate;
- no duplicate identity/action/review/arbiter/admission/merge or foreign
  mutation exists, and the three-action global ceiling is proven;
- passive holds report zero model tokens and restart preserves terminal
  identities;
- installed UI evidence shows only the defined forward happy-path sequence and
  an understandable incident/HumanGate state; and
- exact role/scenario token accounting and immutable evidence are committed in
  this repository.

If a human-only login, payment, secret or unavailable-service blocker prevents
completion, persist exact model-free evidence, stop the bundle safely and
report the precise blocker. Repeating the same failed model call without a
proven changed cause is never an authorized recovery.
