# I13 Stage 2 successor exact-result validation recovery contract

contract_status: owner-approved-pre-runtime-model-free
contract_revision: 1
authorized_at_utc: 2026-08-12
installed_source: baac2921a6901e836cbbf3759c3c42f5259ea37c
incident_generation: 1
successor_attempt_generation: 2
successor_model_call_count: 1
additional_model_calls: 0

This contract applies the owner's explicit authorization to correct model-free
defects on the direct successor path. It applies only to the existing card 12,
PR #9, incident and successor attempt fixed by
[the successor contract](I13_STAGE2_ARBITER_SUCCESSOR_CONTRACT.md). It does not
authorize a new arbiter call, a new model artifact, a replacement identity or a
general late-result/retry path.

## 1. Proven failure and immutable evidence

The one successor `gpt-5.6-sol`/`xhigh` call completed under its hard
16,384-token ceiling. Codex session
`019ff3a1-7f0e-79e2-baa5-cbaa1cc6fc37` consumed 12,271 tokens and produced the
schema-valid 1,705-byte result artifact with SHA-256
`9b5ff7847db2533e56bdbbc424114e5bea8e5e3c352ad1d029a99deaba05c172`.
The durable successor row is `failed/submit_failed`, `model_call_count=1`, no
decision, no recovery owner/path and `recovery_wake_count=0`. A controlled
restart preserved that state and the exact artifact without a second call.

The result selects only `dcp-review-lab-12` and
`same_worker_conflict_repair`, with exact incident, generation, attempt, input,
card, PR, head and base identities. Its evidence set contains exact
`mergeTreeEvidenceDigest`
`a19c64060d0f41320b6bf652c47ff5c58810ebec0416d003963bc1b4fcdf524f`,
which is already present in the authorized frozen incident envelope. The
trusted validator incorrectly omitted that nested digest from its allowlist
while allowing the enclosing `mechanicalDigest`. This is a deterministic
validator defect, not foreign model evidence or a model-policy choice.

The first rejected generation-1 row/artifacts and this generation-2 failed
result, input/schema artifacts, session, token count, call fence and failed
state are immutable audit evidence. Neither result may be edited, replaced or
treated as a new model output.

## 2. Exact additive recovery

One reviewed additive migration may create exactly one
`dcp_arbiter_successor_result_validation_recovery` audit row. It is bound to:

- incident
  `dcp-global-release-2694dbd8b3d4897063603d7a8607ca516aa2f8e05c5a3c39cf56d8e3f18c3c60`;
- attempt
  `dcp-arbiter-successor-3c62ea80b56ef94165519d4f01e4c449c320bff22d16b902dd68d4a1a355ea7d`;
- successor input digest
  `aa44c625c940048d5e0266dac23dd4835a1afcf7648116a056758093b67160e6`;
- result artifact SHA-256 above, exact Codex session and 12,271-token count;
- prior `failed/submit_failed`, call count 1, empty decision and zero wake;
- this reviewed contract and the exact corrected managed-source commit.

The migration preserves the prior failure facts in that audit row and does not
reset `model_call_count`, create a process or change the result artifact. Its
rollback must refuse after the exact recovery is consumed.

The trusted validator may add only the exact nested digest above to the
successor evidence allowlist. It must still reject every other unlisted,
duplicate, malformed, stale or foreign digest and validate the complete exact
decision identity and owner/path.

On one startup reconciliation, and only while the exact audit row is unused,
the daemon verifies the stored result path/type/mode/size/SHA-256, proves the
successor process is not active, parses the unchanged result through the
corrected trusted validator and atomically records at most one decision while
marking the audit row consumed. It must not launch Codex. A missing, changed or
still-invalid result terminally fails this recovery without another action.

## 3. Restart and downstream bounds

The model-free validation recovery stops at durable `decided` with zero wake.
Only a subsequent controlled restart may consume the already-authorized
deterministic policy of one same-worker wake and one fresh exact-head review.
The original successor contract then governs exact card/PR/head review,
admission and terminal merge. No worker or reviewer is authorized unless the
unchanged result becomes the one accepted decision.

After a terminal success or stop, a controlled restart must prove the audit
row, call fence, decision, wake, review and merge are not duplicated. Startup
replay after the audit is consumed is inert. Waiting remains model-free and
there is no timer, watcher, heartbeat, poll, retry, replacement or general
result-recovery facility.

## 4. Budget and stop conditions

The live totals at this boundary are six actual model calls and 132,785 tokens:
two initial workers, two initial reviewers, the 11,583-token original arbiter
and the 12,271-token successor arbiter. This correction authorizes zero model
calls. Only the still-unused one same-worker recovery call and one fresh
reviewer remain conditionally available after an accepted decision, so the
existing eight-call ceiling is unchanged.

Any mismatch in the exact row, artifact, process, digest, session, token,
decision or audit identity is terminal `BLOCKED`. There is no second validation
recovery, third arbiter attempt or owner acceptance in this contract.
