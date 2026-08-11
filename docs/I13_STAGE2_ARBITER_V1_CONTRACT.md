# I13 Stage 2 global release arbiter v1 contract

contract_status: owner-approved-pre-runtime
contract_version: dcp-i13-stage2-arbiter-v1
recorded_at: 2026-08-11
source_baseline: b23b519cd532555c203863586032d157fc1c8c13

This contract is the required reviewed stop between the qualified I13 Stage 1
Admission Controller and any Stage 2 runtime or model call. It authorizes one
bounded implementation and one bounded synthetic qualification only after this
document is green, merged and present in the clean canonical
`dev-control-plane` checkout. It does not itself activate an arbiter.

The implementation remains inside the existing DCP Orchestrator daemon and its
existing SQLite. It is not a general arbitration loop, release service, task
service, queue service, scheduler, watcher, heartbeat, timer or polling agent.
Only the exact disposable `orenvlad-ai/dcp-review-lab` repository is in scope.

## 1. Stage 1 audit and implementation seam

The exact pinned Stage 1 source was audited before this contract was written.
Migration 0050 owns one subordinate FIFO row per exact approved `ReviewRun`, a
partial unique `claimed` lease and the durable `waiting`, `refreshing`,
`incident` and terminal states. Migration 0051 preserves the one historical
false `canonical_main_diverged` packet after exact model-free recovery.

`dcpterminalmerge.Engine` is entered only by approved structured-review and
idle/SCM lifecycle events plus startup reconciliation. It refreshes exact
provider review/check/PR facts, validates local repository/worktree identity,
serializes merge ownership in SQLite and stops the queue at the first active
incident. Waiting rows have no process, timeout or model. Focused Stage 1
engine, store, review and session-manager tests are green at the pinned source.

The existing packet schema `dcp.review-lab.arbiter-needed/v1` is a sufficient
durable mechanical trigger, but it is not an arbiter input envelope. It lacks
the canonical approved-task/scope digest, complete candidate/history/diff
digests, exact check/review set, full relevant frozen queue and explicit
mechanical-recovery results. Stage 2 therefore preserves that packet byte for
byte and derives a separate immutable incident/input record. It does not edit
migrations 0050 or 0051 or reinterpret a recovered packet as a new incident.

## 2. Exact incident identity and idempotency

Only all of the following facts may open the single Stage 2 incident:

- source packet schema exactly `dcp.review-lab.arbiter-needed/v1`;
- reason exactly `merge_conflict_or_ambiguity`;
- active admission status exactly `incident` with its original lease retained;
- repository exactly `orenvlad-ai/dcp-review-lab`;
- fresh Stage 2 native card/session exactly `dcp-review-lab-11` or
  `dcp-review-lab-12`;
- a complete approved structured review and successful named
  `dcp-review-lab` check for the exact open PR head;
- exact task/card/session/worktree/branch/repository/PR/head/base/review/run,
  admission sequence and incident lease identity;
- provider `CONFLICTING`/`DIRTY` or a model-free `git merge-tree` result that
  proves the same real ambiguity against exact current `origin/main`;
- all Stage 1 mechanical recovery options exhausted for that row.

The historical/recovered `canonical_main_diverged` packet, cards 1-10, a
waiting row, failed CI, ordinary staleness, an unavailable provider and every
other reason are permanently ineligible.

The derived incident schema is
`dcp.review-lab.global-release-incident/v1` and `generation` is exactly `1` for
this bounded stage. Its identity digest is SHA-256 over this ordered,
NUL-delimited tuple:

```text
schema version, generation, repository, admission id, admission sequence,
incident lease id, source-packet SHA-256, task id, card/session id,
canonical worktree path, source branch, PR URL, PR number, reviewed base SHA,
current base SHA, candidate head SHA, review id, review-run id, batch id,
approved-task/scope digest, candidate-history digest, candidate-diff digest,
check-set digest, review-set digest, frozen-queue digest,
mechanical-recovery digest
```

The durable `incident_id` is `dcp-global-release-` followed by that full
lowercase hexadecimal digest. The tuple, generation and digest are immutable.
A unique admission/generation key and unique identity digest make equal event
replay return the same row. A changed tuple under the same admission/generation
fails closed before mutation. There is no second incident identity or
generation in Stage 2.

Managed source may add only additive migration
`0052_dcp_review_lab_arbiter_v1.sql`. It adds one bounded incident/action table
to the existing `ao.db`; rollback drops only that new table. It does not create
a database, generic event stream, registry or queue.

## 3. Minimal frozen arbiter input

The exact persisted input schema is
`dcp.review-lab.global-release-arbiter-input/v1`. Its canonical UTF-8 JSON is at
most 16,384 bytes and contains only:

1. incident id, generation, identity digest, source-packet digest, reason and
   authoritative timestamps;
2. the exact bounded approved task text recovered from the immutable native
   `DCP synthetic task <task-id>:` prompt, plus the canonical scope
   `{repository, taskId, taskText, fixedSyntheticProfile}` and its SHA-256;
3. exact card/session/worktree/branch/repository/PR/head/reviewed-base/
   current-base/admission/review/run/batch identities;
4. candidate commit/tree identity, the ordered commit/tree history digest and
   the binary full-index diff digest, plus a bounded sorted file-status list;
5. the exact structured approved/no-findings review identity and digest;
6. the complete relevant named-check set and digest, including check id/name,
   head SHA, status and conclusion;
7. the complete frozen Stage 2 cohort picture in admission sequence order,
   including both cards 11/12, the already terminal predecessor and the active
   incident row, plus any other nonterminal row if one exists; each entry is
   exact-identity bound and the whole picture has one digest;
8. provider mergeability facts and every exhausted mechanical result,
   including exact current-main ancestry and merge-tree/conflict-path evidence,
   with one aggregate digest;
9. an explicit allowlist containing only the decision paths below.

The SHA-256 of the exact persisted input bytes is `input_digest`. The daemon
recomputes every source digest and the complete identity tuple immediately
before launch. Drift leaves the incident frozen and records no model call.

The arbiter receives no executor/reviewer transcript, chain-of-thought,
unrelated task, unrelated repository, credential, environment secret, daemon
connection, GitHub token, DCP command, provider mutation tool, worker worktree
or user Codex configuration. The model is not asked to edit code. It only
selects or rejects the one recovery path.

## 4. One model action and hard token budget

Exactly one model action is permitted for the one exact incident:

- model: `gpt-5.6-sol`;
- reasoning: `xhigh`;
- hard weighted rollout budget: 16,384 tokens, recorded before start;
- maximum calls for the incident: one; no retry, replacement, resume,
  fallback, model switch, downgrade or second generation.

The exact Codex process is stateless and ephemeral. It uses
`codex exec --ignore-user-config --ephemeral --strict-config`, explicit model
and reasoning overrides, `approval_policy="never"`, read-only sandbox,
disabled web search, hooks, apps, plugins, multi-agent and model tools, one
sealed arbiter directory and Codex-native `--output-schema` plus
`--output-last-message`. For the qualified Codex CLI, `rollout_budget` is one
structured entry under `features`, with `enabled=true`,
`limit_tokens=16384`, `reminder_at_remaining_tokens=[2048]`, and sampling and
prefill weights `1.0`; a top-level `rollout_budget.*` entry is invalid. The
installed-CLI preflight must model-free verify this exact argv/config surface
with strict parsing, not merely render command help. Unsupported budget
enforcement is a stop, not permission to call.

The daemon persists requested/running/terminal action state, exact model,
reasoning, token budget, stable launch/terminal identity and model-call count.
It sets `model_call_count=1` in the same compare-and-set that fences the launch,
before process creation. Start failure or budget exhaustion is terminal and
leaves the global freeze; restart never creates a replacement call. The only
exception is a model-free correction of the already-observed exact-pin CLI
configuration rejection: if strict config parsing rejected the child before a
Codex session or provider request existed, a governed correction may preserve
that failed launch in a one-row durable audit record and re-arm the same
incident/generation once. This is not a second model call, may not change any
incident/input identity, and is unavailable for a network, model, budget,
schema, result or unknown child failure.

The arbiter process has a stable exact terminal and one trusted one-shot
supervisor. A controlled daemon restart leaves an exact live descendant alone.
If only the exact bounded result artifact remains, startup may validate and
consume it model-free. A missing, ambiguous or foreign process/artifact fails
closed without another call.

## 5. Decision schema and trusted validation

The only accepted output schema is
`dcp.review-lab.global-release-arbiter-decision/v1`, with every identity pinned
as a JSON-Schema constant. It contains:

- incident id/generation/identity digest and input digest;
- admission/task/card/session/repository/PR/head/current-base identities;
- `verdict`, exactly `assign_recovery` or `safe_stop`;
- for `assign_recovery`, exactly one owner
  `{kind: "same_worker", sessionId: <incident session>}` and exactly one path
  `{kind: "same_worker_conflict_repair", maxWorkerCalls: 1,
  maxFreshReviews: 1}`;
- for `safe_stop`, no recovery owner and exactly one code from
  `scope_not_proven`, `identity_ambiguous`, `evidence_incomplete` or
  `no_safe_bounded_path`;
- one bounded summary and one to eight evidence digests already present in the
  input.

Unknown keys, an unknown path/code, empty or long text, an unreferenced digest,
scope expansion or a mismatched constant is malformed. Missing, malformed,
foreign, duplicate, late or stale output is inert. The trusted daemon re-reads
and validates the exact incident/generation/task/card/session/worktree/repo/
PR/head/base/review/check/admission/queue identity before it persists the
decision. It accepts at most one decision digest and consumes at most one path.

The arbiter has no authority to change task scope, accept risk, write a
worktree, branch or PR, apply/remove a label, call GitHub, merge, retry a
release, change admission priority, clear the freeze, create a HumanGate,
record owner acceptance or claim technical success.

## 6. Sole permitted recovery path

`same_worker_conflict_repair` may wake only the exact incident worker in its
existing worktree/branch/PR and only after a transaction persists the selected
owner/path and consumes its one wake. The continuation contains the approved
task/scope digest, exact old head, exact current main, conflict paths and the
requirement to resolve only the original task. It forbids a new task, card,
branch, worktree, PR or scope.

The incident and global admission freeze remain active while that worker runs.
One new head may receive one fresh stateless exact-head reviewer. Only an
approved/no-findings verdict, the exact successful named check and a trusted
transaction may rebind the original FIFO admission/incident to the new
run/head. Normal admission then revalidates every current fact and may perform
the sole terminal merge. The arbiter never merges.

No changed head, worker failure, reviewer failure, failed check, malformed
handoff or second ambiguity gets another worker, reviewer or arbiter call.
Those outcomes persist a truthful safe technical stop with the global freeze.
Waiting tasks continue to use zero model slots and tokens.

## 7. Exact synthetic qualification budget

The only Stage 2 live cohort is two fresh native cards 11/12 with task ids
`i13-arbiter-a` and `i13-arbiter-b`. Both start from the same clean exact
`origin/main` and each creates the previously absent file
`canary/i13-arbiter-conflict.txt` with a distinct single line. Whichever exact
approved candidate wins FIFO merges first. The other then has a real add/add
conflict against current main and must create the one eligible persisted
incident. The historical false `canonical_main_diverged` packet is not used.

The absolute live ceiling is:

| Action | Ceiling |
| --- | ---: |
| Initial workers | 2 |
| Initial exact-head reviewers | 2 |
| Global release arbiter | 1 |
| Selected same-worker conflict repair | 1 |
| Fresh reviewer for the repaired head | 1 |
| Total model calls | 7 |
| Arbiter tokens | 16,384 hard maximum |

There is no replacement card, manual Run Review, second arbiter, automatic
retry or call borrowed from an earlier allowance. Any pre-model launch failure
does not authorize a replacement identity. Model-free defects in the direct
path may be corrected through sequential governed PRs without increasing the
table. The exact strict-config rejection described in section 4 may consume
one audited same-generation re-arm, but the final counters must still prove
one provider/model call and seven total live model calls.

The expected resolvable canary result is not `safe_stop`: the exact second
worker is selected, produces one new head within the original task, receives a
fresh review/check and passes exact admission to one terminal merge. An arbiter
`safe_stop` is a truthful qualification failure/blocker and cannot be reported
as COMPLETE.

## 8. Completion, restart and duplicate proof

Technical completion requires exact evidence that:

- one source packet and one derived durable incident exist for the fresh
  ambiguity and retain the global freeze;
- controlled restart after incident persistence and before decision preserves
  incident priority, single-flight and at most one live/completed model call;
- exactly one Sol/xhigh result is bound to the immutable input and chooses the
  one affected recovery owner/path;
- controlled restart after decision preserves the same decision digest,
  consumed path and zero second launch/wake;
- only the selected worker wakes once, only its new exact head is reviewed once
  and only that head proceeds through admission and one terminal merge;
- no duplicate arbiter, run, worker wake, reviewer, admission claim or merge
  exists before or after restart;
- all non-selected/waiting rows have no process, model slot or token use;
- exact installed pin, build receipt and post-install contour match the merged
  managed source and reviewed integration pin.

Managed-fork source, immutable pin/evidence and contract/evidence changes use
separate ready PRs, ordinary protected review, green CI and safe merges. The
clean canonical `dev-control-plane` checkout is fast-forwarded after each
merge. Build/install uses only the exact merged immutable pin.

After qualification, supported native session termination may reclaim only
the two new canary worktrees/retained visual terminals. Durable incident,
decision/action, review, admission, provider and terminal card evidence stays
intact. The target repository's merged synthetic canary file is audit evidence,
not cleanup trash.

## 9. Explicit non-authority

Stage 2 adds no production target, `wb-core`, Release Train, deploy, hosted or
mobile write surface, Telegram, updater, telemetry, general task/review loop,
general incident policy, HumanGate or owner-acceptance synthesis. It never
touches real repositories, installed Agent Orchestrator or `~/.ao`. Technical
completion is not owner acceptance; only the owner may write
`Задача принята`.
