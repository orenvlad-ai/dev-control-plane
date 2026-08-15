# DCP Lab admission wake and Human Gate UI v1 contract

status: owner-authorized implementation contract  
date: 2026-08-15  
scope: exact public `orenvlad-ai/dcp-review-lab` policy tasks only

## 1. Purpose and immutable predecessor

This contract corrects two proven boundaries in the already-qualified
happy-path and phase-UI/arbiter contour. It does not reopen the terminal Phase
4 accounting blocker, change any historical evidence row or expand model
authority.

The installed predecessor is managed source
`5691978bf37cb6de2b02243a40f9bac51161db25`, tree
`f35bc7cd5858403ad71b9c2577927624ef12cb39`, installed with receipt SHA-256
`f74bc9f80c8a27dd3f9dc56c6becda61bd96bac737942a6579c85efee1184a51`.
Before any source, installation or runtime mutation, the running predecessor
was preserved as a consistent SQLite backup, receipt/provenance hashes and a
live UI image beneath the canonical lab evidence directory.

The immutable terminal Human Gate is policy task `arb-c-right`, native
session/card `dcp-review-lab-27` / 27, PR #24, exact head
`58adc8c6abe1d2fee90cd1bfa9addd149cede1a8`, admission sequence 19 and future
arbiter generation 1. Its terminal verdict is `human_gate` and its exact owner
question is:

> Should qualification/arbiter-c.txt on main remain mode=left or be replaced
> with mode=right?

The correction must not answer that question, mutate or close PR #24, create a
repair/review/admission/merge continuation, or convert the incident into a
failure.

Three existing approved tasks expose the admission boundary:

| sequence | task | card | PR | exact head | predecessor state |
| ---: | --- | ---: | ---: | --- | --- |
| 20 | `manual-triple-a` | 28 | 25 | `f61ead3aeb9900a1142e237b1ed75b6be787e5c2` | waiting |
| 21 | `manual-triple-b` | 29 | 26 | `33969ae8d066cc6eccb17858d2204ef897c74664` | waiting |
| 22 | `manual-triple-c` | 30 | 27 | `c914f1a8d3f85b6ccc6e8bf9b6578641956ff2dc` | waiting |

Each task has one successful worker, one fresh approved exact-head review and
a successful required check. Each provider PR is open, ready and currently
clean/mergeable. The durable admissions were created after the last unchanged
SCM eligibility snapshot and remained waiting because no later eligibility
event reached the terminal merger. A restart would invoke startup
reconciliation, but is not an acceptable substitute for the missing durable
completion boundary.

## 2. Admission post-commit wake

### 2.1 Single authority

The existing daemon, SQLite, `terminalMerger.Try`, process mutex, durable FIFO
claim/lease and guarded provider merge remain the only terminal-merge
authority. The correction adds no timer, poller, heartbeat, watcher, daemon,
service, registry, database, queue or merge bypass.

### 2.2 Required event boundary

When an approved exact review/head causes the exact policy admission identity
to be committed durably, the same lifecycle completion must emit one
best-effort in-process eligibility signal to the existing terminal merger.
The signal is allowed only after the admission transaction commits and the
exact committed identity has been returned to trusted code. It owns no claim,
provider observation, Git operation or merge; it only asks the existing
terminal merger to re-evaluate durable state.

The first terminal-merger pass may create the admission. It must release its
process mutex before emitting the post-commit signal, so the signalled pass can
use the ordinary mutex, SQLite FIFO lease and trusted current-provider checks.
No SCM or merge side effect is permitted before the durable admission commit.

The signal is emitted only for a newly created exact future-policy admission.
Existing admission replay, stale or foreign review/head identity, conflicting
binding, ambiguous task state, transaction failure or unknown identity emits
no signal. Delivery is idempotent: concurrent review completion, ordinary SCM
eligibility, startup reconciliation, webhook replay or duplicated in-process
delivery may all call `Try`, but can create at most one admission, one claim,
one guarded merge and one durable terminal result.

### 2.3 Queue behavior

Terminal admission sequence 19 remains an incident with a terminal Human Gate
and is skipped by FIFO selection. It does not own or block the merge lease.
Sequence 20 is therefore the first eligible waiter. After each trusted merge,
the same existing drain refreshes canonical main and provider facts before
considering sequences 21 and 22. Their common historical creation base is not
treated as current provider truth, and no change may be lost.

The correction launches no worker, reviewer or arbiter and consumes no model
call or token.

### 2.4 Exact terminal-Human-Gate claim boundary

Managed-source PR #54 was reviewed, merged and deterministically installed at
source `e7497c954baeb38ef494b2346046dc4d21e8f5e3`, tree
`52a6037bfde5272d2eea9bfa21909d04201b9a11`, receipt SHA-256
`dc2fc68b0a66ebaa94862ce4dbc9c792c84009ac514b186803d958a26c13f3c9`.
The first installed start preserved zero active model actions and exposed one
additional exact lease boundary. The Go FIFO selector correctly skipped
terminal Human Gate sequence 19, and a live-copy reproduction obtained fresh
`MERGEABLE` / `CLEAN` provider facts for PR #25. The final atomic SQLite claim
still returned false because its predecessor predicate rejected the presence
of *any* `incident` admission. The transaction therefore never claimed or
mutated sequence 20, and the first-start failure is preserved as evidence.

The bounded successor correction may change only that final claim predicate.
`claimed` and `refreshing` rows remain global blockers. An `incident` row may
be ignored only when the same transaction can prove all of these durable exact
facts:

- one bound policy task is still `incident` for the same admission, session,
  review run, head, incident packet and error code;
- the latest generation for that admission has exact admission sequence,
  session, task, review run, head and incident-kind identity;
- that latest generation has both status and verdict `human_gate`.

An absent, older-generation-only, failed, running, requested, repairing,
foreign, stale or identity-mismatched arbiter row remains a blocker. The
existing minimum-waiting-sequence CAS, one-lease transaction, ReviewRun claim,
process mutex and guarded provider merge remain unchanged. No migration,
historical-row rewrite, owner answer, model action or retry loop is authorized.
The generated SQL must remain source-parity clean.

Managed-source PR #55 implements only this predicate correction. Exact head
`1faad9882dd5bbb3f0486545bb2e26d511aaea16` passed semantic/security review
`PRR_kwDOTydt6M8AAAABJqGR4Q`, workflow `31869526221` (`source` and `package`),
full Go/build, generated parity and focused race coverage. It merged at source
`5def887cb1c240ca309c4c5ff7bd6298af4784ee`, tree
`885af5298339e8562a22a78f8538cd1c1da4b6e1`. It remains build/test input until
this separate immutable pin merges and repeated stopped install/preflight
complete.

## 3. Shared terminal Human Gate projection

For a future policy session whose durable policy state is `incident` and whose
latest exact arbiter status/verdict is `human_gate`, the shared typed
projection is:

- board lane: `Needs You`;
- primary label: `Needs your decision`;
- status dot and detail accent: steady orange;
- motion: none, including reduced-motion mode;
- detail: exact incident kind, generation, cohort and exact durable owner
  question.

The board card and sidebar consume that same projection. An older failed
arbiter action, stock `review_failed` session status or action error cannot
override a later exact terminal Human Gate. A real terminal failure without
that exact Human Gate identity remains red and retains its failure label. No
new Arbiter column, workflow or owner-answer control is added.

## 4. Delivery gates

Implementation proceeds only in this order:

1. merge this reviewed control-plane contract;
2. create a bounded managed-source change from the then-current immutable
   managed-fork main;
3. pass exact-head semantic/security review, required source/package CI,
   complete Go tests, frontend tests/typecheck and generated/provenance parity;
4. merge a separate reviewed immutable pin/install-guard change;
5. with the predecessor stopped, perform deterministic source checkout,
   build, install and model-free preflight;
6. start the exact installed bundle once for live qualification.

The immutable first PR-54 installed start described in section 2.4 did not
cross the SQLite claim fence. After a separately reviewed source correction,
immutable pin and repeated stopped install/preflight, exactly one corrected
controlled start is the live acceptance attempt. Repeated starts are not a
substitute for this correction.

The fixed runtime must not start before both reviewed merges, exact immutable
pinning, stopped deterministic installation and preflight.

## 5. Deterministic proof requirements

Source tests must prove:

1. an approved review creates its admission after the final unchanged clean
   snapshot and the durable completion emits exactly one eligibility signal;
2. concurrent review completion, SCM eligibility and startup/replay create no
   duplicate admission, signal-owned mutation, claim or merge;
3. terminal Human Gate sequence 19 is skipped and waiting sequences 20, 21 and
   22 are selected FIFO;
4. three clean PRs sharing an old base merge sequentially with fresh provider
   and canonical-base validation after every advancement and no lost change;
5. stale, unknown, foreign and ambiguous identities fail closed;
6. exact Human Gate overrides stock `Review failed`, renders steady orange in
   board/sidebar parity, exposes the exact details and respects reduced motion,
   while ordinary failures remain red;
7. the existing forward-only happy-path UI and lifecycle suites remain green;
8. source, package, control-plane, pin and install audits remain green.

The real SQLite store suite must additionally prove that an exact latest
terminal Human Gate releases the next minimum waiting row, while a requested,
running, failed, stale, foreign or identity-mismatched incident still blocks
the same claim. Concurrent claims after release must still produce exactly one
lease owner.

## 6. Live acceptance

Qualification reuses only cards 28-30 and PRs #25-#27. It creates no new
card, task, branch, PR, worker, reviewer or arbiter. One controlled canonical
start must let the trusted daemon merge admissions 20, 21 and 22 strictly FIFO.
Exact merge SHAs and remote-main file bytes must be recorded for:

```text
qualification/manual-triple-20260815-a.txt = manual-triple-a=ok
qualification/manual-triple-20260815-b.txt = manual-triple-b=ok
qualification/manual-triple-20260815-c.txt = manual-triple-c=ok
```

The proof must show zero new model calls/tokens and no duplicate action,
review, admission or merge. A controlled restart after terminal merges must
preserve those identities and counts. Card 27/PR #24 must remain unchanged at
terminal Human Gate and the installed board/API/sidebar must expose orange
`Needs You` / `Needs your decision` without an owner answer. If the live Mac
screen is unavailable, installed DOM/state fixtures and API evidence may prove
the projection, but they do not replace the required live queue qualification.

Technical proof is not owner acceptance. Only the owner may later state
`Задача принята`.
