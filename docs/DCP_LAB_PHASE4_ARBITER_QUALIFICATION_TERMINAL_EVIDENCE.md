# DCP Lab Phase 4 arbiter qualification terminal evidence

status: `FUNCTIONALLY_GREEN / ACCEPTANCE_BLOCKED`
date: 2026-08-15
scope: exact public `orenvlad-ai/dcp-review-lab` future-policy path only

## Result

The four-phase implementation and all three Phase-4 runtime scenarios reached
their intended functional terminal states. All resolvable tasks merged through
the trusted daemon path, the intentionally incompatible task stopped once in
`human_gate`, passive waits consumed no model calls, and controlled restarts
created no duplicate identity or action.

The night program cannot be declared technically complete because one required
accounting datum is no longer recoverable: card 26 was hidden through stock
`session kill` before its initial-worker terminal `tokens used` line was
captured. The immutable database records the one worker action but intentionally
does not store worker token totals; the ephemeral Codex rollout and killed tmux
pane are absent. Restoring the session would cross a prohibited second-worker
model-call fence, so no retry or reconstruction was attempted. The exact known
Scenario-C subtotal is 75,592 tokens plus that unavailable card-26 worker total.

The Mac display was locked during the final read-only Computer Use attempt.
Live daemon API facts and the already passing board/sidebar DOM and shared
projection tests prove the terminal Needs You inputs and mapping; no additional
screenshot claim is made.

## Reviewed delivery and installed authority

Phase 1 and Phase 2 are recorded separately in
`DCP_LAB_PHASE_UI_V1_INSTALL_EVIDENCE.md` and
`DCP_LAB_PHASE2_TRIPLE_QUALIFICATION_EVIDENCE.md`.

The bounded Phase-3 implementation began with managed-source PR #46, exact
head `4b77a69c11c68930dbeadc5933c7ba1e2145dd68`, review
`PRR_kwDOTydt6M8AAAABJouiDw` and workflow `31846494241`. It merged at source
`3bc21e11060d07b7f5339365b8df58f82b9c5439`, tree
`0af68800b32c4ec195722b72cd8cd39f8aafbac3`; pin PR #180 merged at
`d13e96adeeb437b2045edd4f25aab77e3be4ef10`, and deterministic install produced
receipt `82f30938095551643c8aecf0c5953121348e91f97078867e99d599973f78adfe`.

Bounded root-cause corrections remained in the same daemon, SQLite and global
three-slot action queue:

| source PR | merged source / tree | pin PR / merge | install receipt | bounded correction |
| --- | --- | --- | --- | --- |
| #47 | `3f31b66cbf93cc3067ca64cc1908b077727dad0a` / `42ec79b53cc400e9fa8a60b126b2febb61515d4f` | #181 / `492a356116e1a31aed8d43331da6ac0cef4ffab1` | `2b484047b688ffd2ce585d1e3c0491c688c048a0f0fc85aaa93e8bd1d6f761bd` | make the exact incident candidate reachable |
| #48 | `ae2be4995068c2aa532860b7ad1a798ea13752d2` / `205293679414045bdf1880e0cc435c87ac456e42` | #182 / `be1183737138502172f894eb34eb33bf0e11bbac` | `9d2432ce108addd48fd5d30f5061bd644676cc2db7a9df0b150c12ae08f3a267` | provider-compatible strict schema and exact successor generation |
| #49 | `76b272697091bfb684b079bbea9888c882545a46` / `baaa4de1d20d4d30fbf5e4a6872e8999c4c60b1d` | #183 / `d7c487095e14f1a2b1e5b3e4f6e1ba5371733195` | `9905af7cccb2ab5f34bdfdf9f8031d19eed432a7221cd942157e4c1275c8de15` | logical/physical handle split and model-free exact-result validation |
| #50 | `74432568a88f0d21f634af246133d8b1ab28ce68` / `7d5807c0c4fa6ae026284710ba234e2433befd57` | #184 / `2a70390bab83077b62d83046a0e631535cbdbf24` | `45181596257c9d4c24ffff9e2a6e534669dc7d0bdac9e2ce7d1e7e9335777ed7` | proven ancestral continuation target |
| #51 | `d37d91bfabb9b66f6a103e18382e1ec6d98f1567` / `118e64afe88748b61a691de3ad3515e600d72e3c` | #185 / `be27dc66ceb0c5581f686fb81b4a0711f63e1d58` | `e4c5454fd7be9f0ca3ace8e90d18f56eac8ba77e9f8f7f045068b7ae6edaf941` | current-head CI snapshot filtering |
| #52 | `88425a3fffbb9a926f9f0d15a9d60388fa815c98` / `e241eda7d8838cb769fd036dd9dcc1ae27611586` | #186 / `226f1b50c0ffcc491f03baefb95b0de34de64271` | `e237c1baa751773a2027833f5c31cf87309ef52ba3f796cf28263cb505677bc2` | exact canonical-base repaired-lineage range |
| #53 | `5691978bf37cb6de2b02243a40f9bac51161db25` / `f35bc7cd5858403ad71b9c2577927624ef12cb39` | #188 / `9ac37146ed4d032a3bc736f9a108d5adbdbb583e` | `f74bc9f80c8a27dd3f9dc56c6becda61bd96bac737942a6579c85efee1184a51` | exact unchanged HumanGate result validation |

PR #53 exact head `522afee480ebec44d334b5a15e5a5335ae9a37f9`
passed review `PRR_kwDOTydt6M8AAAABJpdFWA` and workflow `31858135970`.
Pin PR #188 exact head `916f145050e14f653ee8f85ae27b047c1389e88f`
passed review `PRR_kwDOSUqHmc8AAAABJpexRw` and baseline workflow
`31858618135`. The final deterministic install completed at
`2026-08-15T02:19:22Z`, preserving backup `i12-20260815T021921Z`; daemon and
asar digests are respectively
`2916790fee47fc11e297fdc1ae34f0da6c520d66b29f46022edd5c93a2fda58e`
and `38d883191f809269b80cad9bafff424417f0845a39e7efd6973e3a867bccc882`.

Control-plane PR #187 independently serialized review-lab baseline refresh
inside the existing typed-submit lock. Exact head `9155ded7...` passed review
`PRR_kwDOSUqHmc8AAAABJpZ-3g` and workflow `31857229890`, then merged at
`634035ab558bdcc8662d4d79d34d174e3a7cb483`.

## Scenario A — two-card resolvable conflict

Cards 21/22 were `arb-a-first` and `arb-a-second`, with admissions 13/14.
PR #18 exact head `e3d1e5e945631f777f765ec26d00bfa251e1f3a9`
trusted-merged at `55e0c64b67560dc075d12a3dbc45a3d0674f405c`.
The second exact incident produced one effective generation-2
`successor_repair` verdict after the immutable generation-1 provider-schema
rejection. One bounded repair made exact head
`931a69637be0b14d9ca145909d0f6060ad81c2fc`; one fresh context-free review and
the existing admission trusted-merged PR #19 at
`ef5eac733c8caf2c38b5aaebb4a190e486a45957`.

There was no lost entry and no duplicate card/session/action/review/arbiter/
admission/merge. Passive waiting consumed zero model calls. Exact Scenario-A
tokens were workers 66,655, reviewers 46,184, arbiter 10,569, total 123,408.
The rejected generation-1 schema request reached no inference and used zero
tokens.

## Scenario B — three-card cohort

Cards 23-25 were `arb-b-two`, `arb-b-one`, `arb-b-three`, admissions 15-17.
Their final heads and trusted merges were:

| task | PR | final exact head | trusted merge |
| --- | ---: | --- | --- |
| `arb-b-two` | #20 | `903538d839181cebec6186316377e5a05383bd38` | `d05fa5bb933a2d60c6c1b4894c6c2508100f68b7` |
| `arb-b-one` | #21 | `a6705dc5f95887eaca5558dcac102aff5cdfd457` | `51721b55e6991a3fbf5bf5a4eb5c46fda60bbcab` |
| `arb-b-three` | #22 | `04100c030bfdde30e01d940e6def6118586f223a` | `7da2d78cb4ff6ab23538983a31d5d2196b32c470` |

The two exact arbiter generations received the full three-card relevant cohort,
used 11,234 and 10,856 tokens and each authorized one bounded successor repair.
Siblings stayed passive until main advancement; final main contains `two`,
`one`, `three` without lost intent. A controlled held-point restart created
only the already queued fresh review. Scenario-B terminal restart preserved 13
policy tasks, 36 total actions, 17 admissions and four arbiter identities with
zero duplicate; Scenario C later advanced those totals to 15/41/19/5.
Scenario-B tokens were workers 134,095, reviewers 100,580, arbiters 22,090,
total 256,765.

## Scenario C — intentional ambiguity

Cards 26/27 were `arb-c-left` and `arb-c-right`, admissions 18/19. Their intents
required mutually exclusive sole values in `qualification/arbiter-c.txt`.
PR #23 exact head `5cdccbb18a34ae7b03e5015375063ce0abdf59ec`
trusted-merged at `e7056f5f0328e041f9f81aa420ab22f713acecdf`.
PR #24 remains open on unchanged exact head
`58adc8c6abe1d2fee90cd1bfa9addd149cede1a8`, with a successful named check and
provider state `CONFLICTING`.

Exact incident
`dcp-future-arbiter-98e4d77336bdfc1539aa44932eacc45514adcbbf8600ff0483d0fb1fb1ed499a`
crossed the arbiter fence once. Codex session
`01a00318-9df3-7721-aa41-fcdc3a0ad00d` used 10,430 tokens and returned
`human_gate` with the exact question:

> Should qualification/arbiter-c.txt on main remain mode=left or be replaced
> with mode=right?

The trusted parser initially rejected its schema-permitted diagnostic path and
preserved `failed/submit_failed`. Migration 0074 then bound the same action,
physical handle, session, input/schema/result artifacts and token count before
one model-free validation. Recovery row
`dcp-future-arbiter-human-gate-recovery-98e4d77336bdfc1539aa44932eacc45514adcbbf8600ff0483d0fb1fb1ed499a`
is `applied`; the incident is now terminal `human_gate`, decision digest
`4d80e72eafc9f61dc31d8b3ecaabb374618cde8d6b9a3d0d3fef4bbb388829f1`.
Task and admission remain incident, with empty repair action, empty recovery
review and no merge.

The live session API reported one shared projection input:
`dcpPolicyState=incident`, `dcpArbiterStatus=human_gate`, generation 1, exact
cohort `arb-c-left, arb-c-right`, the same question and open/conflicting PR #24.
The installed DOM/state-machine tests map it to steady orange Needs You without
pulse in both board and sidebar. Stock cleanup hid only merged card 26; card 27
remains the sole visible active-interface card. Card 26's merged policy,
admission, PR, merge and model-action records remain immutable.

Known Scenario-C terminal accounting is:

| action | tokens |
| --- | ---: |
| card 26 initial worker | **unavailable after stock hide; acceptance blocker** |
| card 26 reviewer | 19,626 |
| card 27 initial worker | 20,635 |
| card 27 reviewer | 24,901 |
| sole arbiter | 10,430 |
| **known subtotal** | **75,592 + unavailable worker total** |

No model call was launched by migration 0074, either restart, cleanup, UI/API
inspection, build/install/preflight or terminal verification.

## Restart, dedupe and final stopped state

Before and after the terminal controlled restart, the full ordered identity
digest was exactly
`3c2bf8fb971f9b4ad6800da1cbd401d6b1dd557fdf7db04d474fd25de06c872b`.
Both snapshots contained 15 policy tasks, 41 model actions, 19 admissions, five
future arbiters, one HumanGate recovery and zero active model actions. The
Scenario-C incident stayed `human_gate` with one call and one decision; the
recovery timestamp and question did not change. No new head, review, admission
rebind, merge or provider mutation appeared.

The final bundle is stopped; the canonical run-file and daemon are absent and
SQLite has zero reserved/running model actions. Cards 21-26 were hidden only
through stock terminal-session handling; immutable task, action, review,
admission, arbiter and merge evidence was not truncated. Card 27 remains
Needs You and no owner response has been simulated.

## Program accounting and blocker

Phase 1 used zero DCP calls/tokens. Phase 2 used 153,736 tokens. Scenario A used
123,408; Scenario B used 256,765. Across every preserved exact terminal line,
the known program totals are workers 312,463, reviewers 253,949 and arbiters
43,089: **609,501 known tokens plus the unavailable card-26 worker total**.

All functional acceptance criteria are green: bounded three-slot authority,
one call per incident generation, passive zero-token hold, context-free fresh
review after every repair head, FIFO trusted merges, no duplicate identity,
no lost change, no foreign mutation and fail-closed HumanGate. Exact total
model/token accounting is not proven, so the four-phase block is terminal
`BLOCKED`, not complete. No safe in-scope action can recreate that terminal
line without violating the one-worker-call authority.
