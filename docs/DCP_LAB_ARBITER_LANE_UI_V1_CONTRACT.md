# DCP Lab shared review/arbiter lane UI v1 contract

status: owner-authorized implementation contract  
date: 2026-08-15  
scope: DCP Orchestrator presentation projection only

## 1. Purpose and immutable predecessor

This contract supersedes only the incident/arbiter presentation rules in
[the phase UI and ordinary-card arbiter contract](DCP_LAB_PHASE_UI_ARBITER_V1_CONTRACT.md)
and [the terminal Human Gate UI contract](DCP_LAB_ADMISSION_WAKE_HUMAN_GATE_UI_V1_CONTRACT.md).
It does not change task, arbiter, repair, review, admission, merge or provider
semantics.

The exact installed predecessor is managed source
`5def887cb1c240ca309c4c5ff7bd6298af4784ee`, tree
`885af5298339e8562a22a78f8538cd1c1da4b6e1`, receipt SHA-256
`15b72e71a32863c946a9e6ccf87343bd995d53fe472b2654215ab988696cba9e`.
Read-only baseline proved one canonical app and daemon, SQLite integrity `ok`,
zero claimed/running model actions and only bare retained DCP model panes. The
public managed-source and control-plane mains are exact and have no open PR.

The proven presentation defect is narrow: an ordinary future-card incident is
placed in red `Needs You` from the stock `review_failed` shell while its exact
arbiter is queued, running or has an accepted automatic decision. The system
continues autonomously, but the board falsely implies a terminal failure or an
owner action. The durable facts already distinguish reviewer, arbiter,
successor repair, Human Gate and genuine terminal error; the shared projection
does not yet expose that distinction.

The historical terminal Human Gate remains policy task `arb-c-right`, native
session/card `dcp-review-lab-27` / 27, PR #24, exact head
`58adc8c6abe1d2fee90cd1bfa9addd149cede1a8`, admission sequence 19 and arbiter
generation 1. Its exact owner question, branch, PR and durable state must remain
unchanged. This UI pass does not answer or accept it.

## 2. Existing-board layout

The stock four-column board remains intact. No fifth column, second task card,
new task service or alternate board authority is created.

The existing third column becomes one grouped lane with the header:

```text
IN REVIEW / ARBITER    <review-count> / <arbiter-count>
```

The two counts follow the same order and typography as `IDLE / WORKING` and
`READY TO MERGE / MERGED`. They count visible unique task cards in their exact
subsection, never sessions, actions or incident generations.

Inside that same column the subsections are ordered:

1. `ARBITER` first, with its own visible count and task cards;
2. `IN REVIEW` second, with its own visible count and task cards.

Each task has exactly one card and one sidebar item. A task can occupy only one
board subsection at a time. Repeated snapshots, an older stock session status
or simultaneous lifecycle facts cannot duplicate it between sections.

## 3. Shared typed projection

One typed projection remains the sole presentation authority for board lane,
subsection, primary label, dot/accent color, activity bit, detail and
accessibility text. Board cards and sidebar items consume the same result.

### 3.1 Review

- queued or pending exact-head review: `IN REVIEW`, steady yellow;
- durably claimed/running reviewer model action: `IN REVIEW`, gently pulsing
  yellow;
- a retained idle shell, stock `PR open`, stale review summary or absent model
  child cannot pulse.

### 3.2 Arbiter

- exact typed incident eligible for or durably waiting on its arbiter:
  `ARBITER`, `Waiting for arbiter`, steady purple;
- durably claimed/running arbiter model action: `ARBITER`,
  `Arbiter evaluating`, gently pulsing purple;
- accepted automatic arbiter verdict while its deterministic hold or successor
  transition is still pending: `ARBITER`, a truthful nonterminal arbiter label,
  steady purple;
- once a successor repair is durably queued/running, the same card follows the
  existing path `Working` (blue) -> `In Review` (yellow) ->
  `Ready to Merge` (green) -> `Merged` (green).

Purple must be visually distinct from review yellow, Human Gate orange,
working blue, ready/merged green and failure red in the existing dark theme.
Arbiter motion is allowed only for a durably claimed/running arbiter model
action. Passive cohort/order holds, requested/queued actions and accepted
decisions waiting on an event do not pulse and own no process or token.

### 3.3 Human Gate and failure precedence

An exact latest terminal arbiter status/verdict `human_gate` remains in
`Needs You` with `Needs your decision`, steady orange and the exact durable
owner question. It never appears in the Arbiter subsection after the terminal
Human Gate is persisted.

A real terminal task/arbiter/reviewer error without an exact automatic
arbiter-continuation state or terminal Human Gate remains red in `Needs You`.
An older failed stock review/action row cannot override a later exact active or
waiting arbiter state, accepted automatic verdict, successor repair or terminal
Human Gate.

## 4. Motion and accessibility

Pulse is layout-stable and CSS-only. `prefers-reduced-motion` disables all
animation while retaining the same steady color, primary label and accessible
state. Color is never the sole state signal. Board card and sidebar
accessibility text name Review, Arbiter, Human Gate or failure truthfully and
agree exactly for the same task.

## 5. Safety boundary

This is a renderer/query/projection change only. It adds no migration, table,
database, service, daemon, scheduler, queue, poller, watcher, timer, heartbeat,
model call, repair, reviewer, arbiter generation, admission claim, provider
operation or merge path. Runtime and state-machine code remain unchanged.

No new synthetic task or live model call may be created to demonstrate the
lane or pulse. Existing durable identities may be read, and deterministic
component/DOM/state fixtures may model queued/running/waiting/terminal facts.
Card 27/PR #24 and all historical evidence remain immutable.

## 6. Required proof

Focused tests must prove:

1. header text and ordered `<review-count> / <arbiter-count>` semantics;
2. `ARBITER` renders above `IN REVIEW` inside the existing third column;
3. one task appears in exactly one subsection and one sidebar item;
4. queued review is steady yellow and only running reviewer pulses yellow;
5. waiting/queued/held arbiter is steady purple and only running arbiter pulses
   purple;
6. successor repair returns the same card to Working, then fresh Review, Ready
   and Merged without a replacement card;
7. exact Human Gate overrides stock failure and stays steady orange in Needs
   You with the exact question;
8. genuine failure remains steady red;
9. board/sidebar projection, color, activity and accessibility parity;
10. reduced motion disables pulse without losing steady state;
11. the existing forward happy path, stale-summary suppression and no-bounce
    suites remain green.

All applicable generated-parity, Go, frontend typecheck, renderer, source and
package gates must pass. Delivery order is reviewed control-plane contract,
reviewed managed-source PR, separate reviewed immutable pin/install-guard PR,
deterministic stopped build/install/preflight and receipt-bound installed
DOM/state proof. A controlled restart may prove persistence/dedupe only after
zero active model actions; it must create zero worker, reviewer or arbiter
calls. The application is left in a safe agreed state.

Technical completion is not owner acceptance. Only the owner may later state
`Задача принята`.
