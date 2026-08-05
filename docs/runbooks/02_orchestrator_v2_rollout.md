# Orchestrator Codex v2 rollout

Status: authoritative rollout and rollback procedure for the runtime defined in
[`../architecture/03_orchestrator_v2.md`](../architecture/03_orchestrator_v2.md).
The host, path and Basic Auth boundary retained from
[`../architecture/02_hosted_control_plane_architecture.md`](../architecture/02_hosted_control_plane_architecture.md)
also remains mandatory.

This runbook performs one fail-closed transition from archived legacy
observation to one local Supervisor generation plus the hosted read-only
projection. It does not authorize a target-product change. Replace every
`<...>` field below with observed evidence; a placeholder is never valid
rollout evidence.

## Invariants and stop conditions

At every step:

- the local Supervisor process and its private SQLite registry are the only
  orchestration writer;
- `devcontrol.pro` is projection-only and its response to ingestion is ACK-only;
- the hosted service receives no Codex, OpenAI, GitHub or target-deploy
  credentials;
- no command starts G6, Luna Watcher, Reporter, a global Chat-Watcher or a
  legacy hosted executor;
- legacy databases, plists and hosted collections are preserved and are never
  used as v2 working truth or rollback targets;
- no HMAC value, auth file, provider body or raw legacy row is copied into the
  repository or rollout evidence.

Stop without applying the next mutating step if any command exits non-zero, a
JSON result is `blocked`/`failed`/`not_ready`, an identity differs from the
expected full SHA/thread/host/model/effort, or a proof cannot be bound to its
exact revision. A reversible technical failure is not a HumanGate: leave the
current safe release running, retain the durable state, and repair or roll back
through the bounded procedure below.

Use a private evidence directory outside Git and do not place secrets in it:

```bash
umask 077
export DCP_V2_RUNTIME_ROOT="$HOME/.dev-control-plane-v2"
export DCP_V2_EVIDENCE="$DCP_V2_RUNTIME_ROOT/backups/rollout/<UTC-rollout-id>"
export DCP_V2_PRIVATE_TMP="$(mktemp -d /tmp/dev-control-plane-v2-private.XXXXXX)"
mkdir -p "$DCP_V2_EVIDENCE"
chmod 700 "$DCP_V2_RUNTIME_ROOT" "$DCP_V2_EVIDENCE"
chmod 700 "$DCP_V2_PRIVATE_TMP"
```

The rollout record must contain sanitized command results, these immutable
identities, and no inferred success:

```text
source PR URL/number:
PR head SHA:
merged main SHA:
local release SHA and Supervisor generation:
hosted release SHA:
exact capability-canary thread/host/model/reasoning:
qualification manifest/digest and four evidence digests:
legacy archive manifest/SHA-256 or clean-Mac absence manifest/SHA-256:
pilot task/workstream/executor thread:
terminal attention/event and delivery receipt:
restart generation before/after:
offline/outbox fixture result:
hosted/local rollback eligibility and proof:
owner acceptance: pending | observed from exact curator thread
```

## 1. Fake-first qualification

Run this from the candidate `codex/*` worktree before any real App Server turn,
GitHub merge, launchd mutation or hosted mutation:

```bash
git fetch --quiet --no-tags origin \
  '+refs/heads/main:refs/remotes/origin/main'
python3 -m compileall -q apps src/dev_control_plane
git diff --check
git diff --cached --check
python3 apps/dev_control_plane_v2_suite.py
```

The suite must report every v2 and retained-safety check as passed and
`real_model_calls=0`. In particular it must cover singleton fencing, migration,
restart recovery, ACK loss, offline durable outbox replay, private socket
permissions, App Server reconnect/dedupe, scheduler conflicts, the anti-loop
budget, independent contour verification, Release Train idempotency, projection
replay protection, installer rollback and hosted rollback isolation. Do not run
the real canary if the suite or either diff check is not green.

Record the candidate head and changed paths without declaring them merged:

```bash
git status --short --branch
git rev-parse HEAD
git diff --name-only origin/main...HEAD
```

## 2. Read-only shadow and online legacy archive

Do not start, stop or restart the legacy observer here. First take its
sanitized read-only aggregate, then create an online SQLite backup while it
remains in its observed state. Capture both sanitized JSON records as the
immutable pre-retirement shadow evidence:

```bash
(
  set -o pipefail
  {
    python3 apps/dev_control_plane_migration_v2.py shadow
    python3 apps/dev_control_plane_migration_v2.py archive \
      --destination "$DCP_V2_RUNTIME_ROOT/backups/legacy-monitor"
  } | tee "$DCP_V2_EVIDENCE/legacy-shadow-archive.ndjson"
)
chmod 600 "$DCP_V2_EVIDENCE/legacy-shadow-archive.ndjson"
```

The shadow result is explicitly `authoritative=false`. Record the archive's
observed `legacy_launchd_loaded` and `legacy_launchd_pid` exactly; a currently
loaded observer may remain read-only shadow input through the staged pilot,
but it cannot survive the activation barrier or be hidden by a manifest
assertion. If a legacy database is present, the archive result must contain
`source_present=true`, `integrity=ok`, a regular backup path, a 64-character
`backup_sha256`, sanitized table counts, and the manifest path
`$DCP_V2_RUNTIME_ROOT/backups/legacy-monitor/manifest.json`. Verify the backup
digest independently without printing database content:

```bash
shasum -a 256 "<backup_path_from_manifest>"
```

The observed digest must equal `backup_sha256`. If the source is present but
these fields cannot be proven, stop. Do not run `retire` yet.

An actually clean Mac follows a separate fail-closed absence branch; it never
synthesizes a legacy SQLite file or a retirement receipt. Both the legacy DB,
the exact plist and the exact launchd label must be absent in one observation:

```bash
(
  set -o pipefail
  python3 apps/dev_control_plane_migration_v2.py absence \
    --destination "$DCP_V2_RUNTIME_ROOT/backups/legacy-absence" | \
    tee "$DCP_V2_EVIDENCE/legacy-absence.json"
)
chmod 600 "$DCP_V2_EVIDENCE/legacy-absence.json"
shasum -a 256 \
  "$DCP_V2_RUNTIME_ROOT/backups/legacy-absence/absence.json"
```

The result and its direct private manifest use schema
`dev-control-plane/legacy-absence/v2` and contain exactly `schema`, `label`,
`captured_at`, `authoritative`, `source_path`, `plist_path`, `source_present`,
`plist_present`, `launchd_loaded`, `launchd_pid`, `evidence_sha256`, and
`manifest_path`. Require the exact label and canonical source/plist paths,
`source_present=false`, `plist_present=false`, `launchd_loaded=false`,
`launchd_pid=null`, `authoritative=false`, a valid timezone-aware capture time,
the canonical identity digest in `evidence_sha256`, and an independently
recorded lowercase file SHA-256. `manifest_path` is the same-owner mode-`0600`
single-link non-symlink direct `absence.json` inside the requested mode-`0700`
directory. Any mixed state (for example DB absent but plist or label present)
is not a clean-Mac variant and blocks cutover. Re-run this exact absence proof
at the pre-activation barrier; the installer accepts either this one
machine-verifiable absence record or the complete archive → retirement →
final-shadow chain, never a mixture.

Compare only the aggregate shadow result with current GitHub truth and the
candidate task list. A mismatch is investigation evidence, not permission to
write legacy state or start an old watcher.

## 3. Zero-call Desktop thread/read discovery

This pre-cutover discovery performs
`initialize`, `model/list` and `thread/read` against one exact existing local
Desktop task. It does not start/resume a thread or invoke a model turn.

```bash
python3 apps/dev_control_plane_codex_app_server_v2_smoke.py \
  --read-only-canary '<exact-Desktop-thread-id>' \
  --codex-bin /Applications/ChatGPT.app/Contents/Resources/codex \
  --output "$DCP_V2_EVIDENCE/codex-read-only-canary.json"
```

Proceed only if the sanitized file binds the exact requested thread, attests
`model=gpt-5.6-sol` and `reasoning_effort=ultra`, and contains no auth or
provider payload. This proves snapshot-read capability only. Do not claim
cross-process live attachment to a Desktop-owned task. Do not run another
Desktop read probe. Its `real_model_calls` remains zero; the later
Supervisor-owned staged pilot is the one and only bounded one-call App Server
capability canary.

## 4. GitHub self-closure

Only `orenvlad-ai/dev-control-plane` and a current `codex/*` branch are eligible.
Before push, repeat the full fake suite, diff checks, semantic/verifier review,
forbidden-path/action scan, protected-docset check and secrets scan. Commit only
the intended files, push the current branch, and open a non-draft PR to `main`.
No command in this runbook pushes `main` directly.

The PR body contains the exact ordered headers `=== ДЛЯ КУРАТОРА ===` and
`=== СЖАТАЯ ПРОВЕРКА ===` with non-empty Russian handoff text. Those sections
are presentation, not proof: self-authored `passed` markers never satisfy a
gate. The `self-closure` job consumes the exact-head evidence artifact from its
`v2-suite` dependency, validates the complete suite membership and commit, and
then independently reruns projection-isolation, legacy-retirement, workflow
mutation-authority and full repository secrets policy checks.

```bash
git status --short --branch
git diff --check
git diff --cached --check
git push -u origin '<codex-branch>'
gh pr create --repo orenvlad-ai/dev-control-plane \
  --base main --head '<codex-branch>' \
  --title '<reviewed-title>' --body-file '<reviewed-PR-body-file>'
gh pr checks '<PR-URL>' --watch --fail-fast
gh pr view '<PR-URL>' --repo orenvlad-ai/dev-control-plane \
  --json number,state,isDraft,headRefName,headRefOid,baseRefName,mergeable,mergeStateStatus,statusCheckRollup,files,url
```

Read back the exact PR head, both `v2-suite=SUCCESS` and
`self-closure=SUCCESS`, and all changed paths. Populate a closure-decision
input outside the repository from those observations. The input schema is:

```json
{
  "repo": "orenvlad-ai/dev-control-plane",
  "task_class": "<L1|L2|L3>",
  "pr_number": "<observed integer>",
  "pr_state": "OPEN",
  "branch_name": "<observed codex/* branch>",
  "expected_head_sha": "<observed full PR head SHA>",
  "pr_head_sha": "<second exact GitHub readback of the same SHA>",
  "working_tree_clean": true,
  "required_checks_passed": true,
  "diff_check_passed": true,
  "cached_diff_check_passed": true,
  "verifier_status": "passed",
  "forbidden_path_hits": [],
  "forbidden_action_hits": [],
  "changed_files": ["<every observed PR path>"],
  "secrets_scan_passed": true,
  "handoff_required_fields_present": true,
  "handoff_has_compact_check": true,
  "blocker": null,
  "no_auto_merge": false,
  "codex_owned_branch": true,
  "pr_created_for_current_task": true,
  "derived_sync_task": false
}
```

`pr_number` must be a JSON integer after substitution. A `true` value is valid
only when backed by both recorded exact-head checks, not by expectation.
Evaluate the repository-owned decision gate:

```bash
python3 apps/dev_control_plane_runner.py github-closure-decision \
  --input "$DCP_V2_EVIDENCE/github-closure-input.json" --auto-merge
```

Merge only if the result is `allowed=true`, `merge_allowed=true`,
`delete_branch_allowed=true`, has no blockers, the worktree is clean, and a
final GitHub readback still returns the same head SHA:

```bash
gh pr merge '<PR-URL>' --repo orenvlad-ai/dev-control-plane \
  --squash --delete-branch --match-head-commit '<exact-PR-head-SHA>'
git fetch --quiet --no-tags origin \
  '+refs/heads/main:refs/remotes/origin/main'
gh pr view '<PR-URL>' --repo orenvlad-ai/dev-control-plane \
  --json number,state,headRefOid,mergeCommit,statusCheckRollup,files,url
git rev-parse origin/main
```

Require `state=MERGED`, an exact merge commit, unchanged PR head and
`origin/main == mergeCommit.oid`. If any readback differs, do not deploy.
After first activation, the installed prior release supplies the independent
trust anchor for self-updates. If an actual PR diff touches `.github/**`,
`AGENTS.md`, Supervisor/registry/release/contract policy, projection auth/state,
hosted deploy, migration or local-install authority paths, green candidate
checks cannot authorize it. The current Supervisor emits one typed
`security_permission_change` HumanGate and performs no merge. Such a change
needs a new exact-head, explicitly authorized two-phase controller update. This
bootstrap is the sole pre-activation case and therefore requires the recorded
independent semantic review before its first merge.
The logical self-release lane remains held through hosted deployment and the
terminal contour proof. If `main` advances before that proof, the immutable
identity is stale: do not relabel the old deployment as current; start a new
governed release from the new exact `origin/main`.

## 5. Fresh exact `origin/main` rollout checkout

Do not deploy from the feature worktree. Create a fresh checkout outside the
repository, fetch `main`, and bind it to the merged GitHub identity:

```bash
export DCP_V2_ROLLOUT_DIR="$(mktemp -d /tmp/dev-control-plane-v2-rollout.XXXXXX)"
gh repo clone orenvlad-ai/dev-control-plane "$DCP_V2_ROLLOUT_DIR/repo" -- \
  --branch main --single-branch
git -C "$DCP_V2_ROLLOUT_DIR/repo" fetch --quiet --no-tags origin \
  '+refs/heads/main:refs/remotes/origin/main'
git -C "$DCP_V2_ROLLOUT_DIR/repo" status --porcelain
git -C "$DCP_V2_ROLLOUT_DIR/repo" rev-parse HEAD
git -C "$DCP_V2_ROLLOUT_DIR/repo" rev-parse origin/main
```

Set the immutable rollout SHA only after the last three results prove an empty
status and `HEAD == origin/main == <merged-main-SHA>`:

```bash
export DCP_V2_MERGED_SHA='<observed-40-character-merged-main-SHA>'
export DCP_V2_CHECKOUT="$DCP_V2_ROLLOUT_DIR/repo"
```

Run all later repository-owned commands from this checkout. Retain the checkout
until closure; do not reset or reuse the candidate worktree as a substitute.

## 6. Inactive local install and independent restricted keys

Install the exact merged release without `--activate`. This packages the
immutable release, records only the inert `staged` pointer, and creates the
restricted projection HMAC key, independent owner-acceptance attestation key,
independent install-acceptance HMAC key and private activation nonce if they
do not already exist:

```bash
python3 "$DCP_V2_CHECKOUT/apps/dev_control_plane_local_install_v2.py" install \
  --source "$DCP_V2_CHECKOUT" --expected-sha "$DCP_V2_MERGED_SHA"
python3 "$DCP_V2_CHECKOUT/apps/dev_control_plane_local_install_v2.py" status
```

Require the install result to report `status=staged`,
`commit_sha=$DCP_V2_MERGED_SHA`, `activated=false`,
`projection_key_present=true`, and `staged_release` equal to the immutable
`$DCP_V2_RUNTIME_ROOT/releases/$DCP_V2_MERGED_SHA`. On a first install,
`current_release` remains absent and the status command remains
`status=not_installed`; on an update, the old healthy `current_release` remains
unchanged. Staging must not write the launchd plist or move `current`/
`previous`.

Bind the inert pilot executable only to the verified staged identity:

```bash
export DCP_V2_STAGED_RELEASE="$DCP_V2_RUNTIME_ROOT/releases/$DCP_V2_MERGED_SHA"
export DCP_V2_QUALIFICATIONS="$DCP_V2_RUNTIME_ROOT/qualifications"
export DCP_V2_QUALIFICATION="$DCP_V2_QUALIFICATIONS/$DCP_V2_MERGED_SHA.qualification.json"
```

Create commit-bound qualification evidence only in this private runtime
directory. Each basename below must be new, regular, same-owner,
single-link, non-symlink and mode `0600`. First repeat the authoritative
zero-model suite from the clean merged checkout. The stopped-legacy shadow
binding is created only after the staged pilot and exact retirement:

```bash
(
  set -o pipefail
  python3 "$DCP_V2_CHECKOUT/apps/dev_control_plane_v2_suite.py" | \
    tee "$DCP_V2_QUALIFICATIONS/$DCP_V2_MERGED_SHA.suite.txt"
)
chmod 600 "$DCP_V2_QUALIFICATIONS/$DCP_V2_MERGED_SHA.suite.txt"
```

Require the suite's final summary JSON to report `status=passed`, the expected
full check count and `real_model_calls=0`. Do not create the qualification manifest
yet; its canary and staged-runtime evidence comes from the later pilot.

Never print, copy into evidence, compare in a shell argument, or commit any of
the three HMAC values or the activation nonce. The installer validates all
four external files as same-owner, regular, non-symlink, single-link
mode-`0600` files. The hosted runner receives only the projection key. A
stateless exact-chat bridge may read only `owner_acceptance_hmac.key`, and only
to attest an actually observed owner reply; it never logs or forwards the key.
Only the local installer may read `install_acceptance_hmac.key`. The
Supervisor child reads `activation_nonce.bin`; read-only health may expose its
digest, never the nonce.

Before the pilot, prove there is no already loaded v2 launchd writer:

```bash
! launchctl print "gui/$(id -u)/com.orenvlad.dev-control-plane-v2"
```

This bootstrap cutover requires the service to be absent. If a prior healthy
v2 release is already active, do not run this first-cutover pilot beside it;
stage and qualify that update in a one-writer maintenance cutover instead.

## 7. Hosted projection rollout

The only live path is the merged checkout's runner, in this exact order. Do
not add `--offline` to any live-eligibility command:

```bash
cd "$DCP_V2_CHECKOUT"
python3 apps/dev_control_plane_hosted_deploy.py print-plan
python3 apps/dev_control_plane_hosted_deploy.py validate \
  --projection-key-file "$DCP_V2_RUNTIME_ROOT/secrets/projection_hmac.key"
python3 apps/dev_control_plane_hosted_deploy.py deploy --dry-run \
  --projection-key-file "$DCP_V2_RUNTIME_ROOT/secrets/projection_hmac.key"
python3 apps/dev_control_plane_hosted_deploy.py deploy --live \
  --projection-key-file "$DCP_V2_RUNTIME_ROOT/secrets/projection_hmac.key"
python3 apps/dev_control_plane_hosted_deploy.py loopback-probe
python3 apps/dev_control_plane_hosted_deploy.py public-probe
python3 apps/dev_control_plane_hosted_deploy.py webcore-probe
```

`validate` and dry-run must have no blocker. Live output must be
`status=deployed`, `live_executed=true`, and bind
`release_sha=$DCP_V2_MERGED_SHA`. The probes must prove:

- loopback role `hosted_projection_v2`, `control_authority=false`, mutation
  routes disabled, WAL/FULL rebuildable projection storage, and the exact
  immutable release SHA;
- fresh TLS and Basic Auth on `/`, `/runs/live` and `/api/v2/state`;
- unsigned `/api/v2/ingest` rejected, legacy MCP/OAuth/control writes denied,
  and no public no-auth mutation route;
- WebCore health remains independent.

The hosted runner preserves the old hosted state as read-only audit evidence.
Do not import it into the projection database and do not provision hosted
executor credentials.

The live runner proves the release after activation. If that proof fails, its
result is also part of rollout evidence:

- `rollout_proof_failed_previous_projection_release_restored` means a verified
  previous v2 release was restored. Prove that previous identity with all three
  probes and stop this rollout; do not activate the new local release.
- `rollout_proof_failed_unverified_projection_quarantined` means no previous v2
  release could be restored. The runner fail-closes by stopping and disabling
  only `dev-control-plane.service`, disabling the exact nginx site symlink,
  unlinking the current app pointer, writing a mode-`0444` quarantine marker
  bound to the failed SHA, and proving loopback is unavailable. It preserves
  the immutable release, projection database, legacy archive and TLS material.
  Record those facts, leave any existing Mac outbox durable/offline, and stop;
  a full validated deploy is required after remediation.
- `rollout_proof_failed_quarantine_failed` is not permission to leave or claim
  the unverified surface. Treat it as a serious failed-safe incident and prove
  the exact service/app/nginx state before any further rollout action.

Never manually enable the quarantined nginx link, relink `app`, or point either
link at legacy code.

### wb-core external Release Train contract

`wb-core` remains an external target. Its registered local adapter never
merges, deploys, verifies, rolls back or changes target labels directly. For an
immutable candidate it may publish only the existing GitHub-native command:

```text
/wb-core orchestration admit <PR> head <SHA> task <target-task-id> revision <task-revision> passport sha256:<passport-digest>
```

Before that one idempotent command, and again on readback, require the exact PR
head, governed target/scope labels, a non-draft PR, target `origin/main` queue
status, no foreign active lane or halted gate, and the Actions-owned admission
proof bound to PR, owner, head, target task, revision and Passport digest. A
queue conflict or another healthy lane is a deterministic wait, not permission
to bypass the target Release Train.

A merged PR is terminal only with the expected `release:done` or
`release:production` target label, the exact admission proof and an
Actions-owned terminal proof binding PR, merge SHA and `repo-only` or
`production-verified` contour. Without that proof it remains
`waiting_release`. After independently authorized task-level closure, the
Supervisor may ask the same target protocol to release the logical lane:

```text
/wb-core orchestration release-lane <anchor-PR> task <target-task-id> revision <task-revision> outcome <completed|parked> evidence sha256:<evidence-digest>
```

The adapter rechecks that durable authorization immediately before sending,
deduplicates the command, and treats the lane as released only after the exact
Actions proof and readback that the target lane is no longer owned. This
bootstrap does not invoke either `wb-core` command and performs no target
product change.

## 8. One-attempt nonterminal App Server qualification

The first-install qualification uses the inactive merged release and the
production v2 state directory, but not launchd. It runs exactly one fenced
Supervisor process, binds loopback `127.0.0.1:8766`, creates a mode-`0600` Unix
command socket, and owns one App Server thread. Keep a present legacy observer
in its observed non-authoritative state during this proof; do not restart or
reconfigure it. A clean Mac remains on the separately proven absence branch.

This is not terminal task closure. The only real App Server turn before
activation has `output_contract=checkpoint` and one canonical progress stage
from `5, 15, 25, 40, 55, 65, 72, 80, 88, 95`. It must never report `100`,
`technical_complete`, terminal evidence or curator attention. Final attention
is deliberately deferred until the activated release survives every remaining
proof in this runbook.

Prepare one versioned `release:production` Task Passport and workstream outside
Git. Bind `curator.thread_id` to the exact bootstrap curator identity supplied
out of band as `$DCP_V2_CURATOR_THREAD_ID`, and `curator.host_id` to its observed
supported host identity. Never copy that locator into repository files or the
hosted projection. Bind the observed merged PR head/merge, the complete
observed PR file list, resource
`target:orenvlad-ai/dev-control-plane`, exactly one
`release-lane:<logical-lane-id>` routing resource, at least one non-routing
classified scheduler resource `qualification:<merged-SHA>`, and deployed
release identity. The nested workstream declares that same qualification
resource and starts in `waiting_release`:

```text
github-pr-v1:orenvlad-ai/dev-control-plane:<PR>:<head-SHA>:<merge-SHA>
hosted-release-v1:wb-core-eu-root:devcontrol.pro:<merge-SHA>
```

The Passport executor is `null`; `start_executor` binds the observed owned
thread itself. Use a private empty workspace below the runtime root, not an
original target checkout. `thread/start` performs no model call. The rollout
then permits exactly one `codex_followup` model attempt on that same thread.
The durable `model_attempt_count` is incremented before `run_turn`; failed,
timed-out, ambiguous and schema-invalid attempts all consume the single budget.
Qualification requires `single_attempt_canary=true`,
`model_attempt_count=1` and `model_call_count=1`, where the latter is the one
successfully receipted checkpoint turn. If the first attempt does not produce
that receipt, stop the pilot: do not retry the current executor, create a
successor or run an arbiter, and do not make another real canary call for this
pilot revision.

The socket input files have these exact fields (unknown or omitted contract
fields fail closed):

- `pilot-start-executor.json`: `passport`, `workstream`, `cwd`, `message_id`.
  The Passport contains `schema`, `task_id`, `revision`, `title`, `objective`,
  `expected_result`, `contour`, `included_scope`, `excluded_scope`,
  `constraints`, `acceptance`, `closure`, `autonomy`, `workstream_ids`,
  `release_manifest`, `resources`, `modules`, `files`, `dependencies`,
  `multi_pr_intent`, `multi_deploy_intent`, `curator`, `executor`, and
  `created_at`.
  `workstream_ids` contains exactly the pilot workstream. `autonomy` contains `allowed_actions`,
  `prohibited_actions`, and `human_gate_reasons`; `curator` contains exact
  `thread_id` and `host_id`; `executor` is `null`.
  For this already-authorized self-production pilot, `allowed_actions` contains
  exactly the used closed capabilities: `codex_workspace_mutation`,
  `github_readback`, `hosted_readback`, `self_merge`,
  `self_hosted_deploy`, and `target_lane_release`; unused known capabilities
  are listed in `prohibited_actions`. A prohibited capability always wins and
  the same authorization is rechecked immediately before every side effect.
  `release_manifest` contains exactly `schema`
  (`dev-control-plane/release-closure-manifest/v2`), the same
  `logical_lane_id`, one-element ordered `pr_identities` and
  `deploy_identities` matching the immutable identities above, and
  timezone-aware `finalized_at`. Both multi-intent flags are false.
- The nested workstream contains `schema`, `workstream_id`, `task_id`,
  `revision`, `generation`, `root_workstream_id`,
  `corrective_of_generation`, `title`, `objective`, `state`, `resources`,
  `executor`, `dependencies`, and `created_at`. For the first generation,
  `root_workstream_id == workstream_id` and `corrective_of_generation` is
  `null`; `executor` is also `null` before `start_executor`, `state` is exactly
  `waiting_release`, and its resources are a subset of the Passport resources.
- `pilot-register-release-candidate.json` contains exactly `task_id`,
  `workstream_id`, `expected_pr_head_sha`, and `message_id`.
  `expected_pr_head_sha` is the exact lowercase 40-character pre-merge PR head
  read back from GitHub, not the merge commit. The caller supplies no
  candidate ID, revisions, lane, priority, resource classification, diff,
  checks, admission, conflict, risk or any other scheduler field; unknown
  fields fail closed.
- The durable intake worker derives all scheduler fields from the current
  registry, Passport/workstream revisions and exact GitHub readback. Because
  this source PR is already merged, its admission is `proof_only=true`, the
  deterministic result is `proof_only_wait`, and no release action is
  enqueued. A merged proof is never treated as a still-releasable PR.
- `pilot-checkpoint-followup.json` contains exactly `task_id`,
  `workstream_id`, one bounded credential-free `prompt`,
  `output_contract=checkpoint`, the same `cwd`, `terminal_context=null`, and a
  stable `message_id`, with `call_policy=single_attempt_canary`. The prompt
  requests one schema-bound checkpoint at one
  canonical stage below `100`; it contains no unobserved success claim and no
  terminal or owner-acceptance language.

All IDs are bounded machine identifiers, revisions are the latest values read
from the read-only local state API, file lists are the complete GitHub diff readback,
and timestamps are timezone-aware RFC 3339 values. Do not put the HMAC key,
GitHub auth or raw provider output into any input.
The checkpoint follow-up and `start_executor` use the exact `cwd`
`$DCP_V2_RUNTIME_ROOT/state/managed_workspaces/rollout-pilot`.

Start the inactive service in a dedicated operator terminal, wait for ready
health and then send the prepared socket requests with the Supervisor CLI's
`command` interface:

```bash
mkdir -p "$DCP_V2_RUNTIME_ROOT/state/managed_workspaces/rollout-pilot"
chmod 700 "$DCP_V2_RUNTIME_ROOT/state/managed_workspaces" \
  "$DCP_V2_RUNTIME_ROOT/state/managed_workspaces/rollout-pilot"
python3 "$DCP_V2_STAGED_RELEASE/apps/dev_control_plane_supervisor_v2.py" serve \
  --state-dir "$DCP_V2_RUNTIME_ROOT/state" \
  --workspace-root "$DCP_V2_RUNTIME_ROOT/state/managed_workspaces" \
  --codex-bin /Applications/ChatGPT.app/Contents/Resources/codex \
  --release-sha "$DCP_V2_MERGED_SHA" \
  --activation-nonce-file "$DCP_V2_RUNTIME_ROOT/secrets/activation_nonce.bin" \
  --projection-key-file "$DCP_V2_RUNTIME_ROOT/secrets/projection_hmac.key" \
  --host 127.0.0.1 --port 8766 --interval 10 --worker-poll 1
```

From a second terminal, use unique stable request/message IDs and the same
private socket for every mutation. The commands below are gated groups, not a
batch: inspect each state readback and meet the following prose condition
before running the next mutating command.

```bash
python3 "$DCP_V2_STAGED_RELEASE/apps/dev_control_plane_supervisor_v2.py" command \
  --state-dir "$DCP_V2_RUNTIME_ROOT/state" --name start_executor \
  --input "$DCP_V2_EVIDENCE/pilot-start-executor.json" \
  --request-id '<pilot-start-request-id>'
python3 "$DCP_V2_STAGED_RELEASE/apps/dev_control_plane_supervisor_v2.py" state \
  --state-dir "$DCP_V2_RUNTIME_ROOT/state" \
  --request-id '<pilot-executor-readback-request-id>'
python3 "$DCP_V2_STAGED_RELEASE/apps/dev_control_plane_supervisor_v2.py" command \
  --state-dir "$DCP_V2_RUNTIME_ROOT/state" --name register_release_candidate \
  --input "$DCP_V2_EVIDENCE/pilot-register-release-candidate.json" \
  --request-id '<pilot-release-registration-request-id>'
python3 "$DCP_V2_STAGED_RELEASE/apps/dev_control_plane_supervisor_v2.py" state \
  --state-dir "$DCP_V2_RUNTIME_ROOT/state" \
  --request-id '<pilot-release-registration-readback-request-id>'
python3 "$DCP_V2_STAGED_RELEASE/apps/dev_control_plane_supervisor_v2.py" command \
  --state-dir "$DCP_V2_RUNTIME_ROOT/state" --name codex_followup \
  --input "$DCP_V2_EVIDENCE/pilot-checkpoint-followup.json" \
  --request-id '<pilot-checkpoint-request-id>'
python3 "$DCP_V2_STAGED_RELEASE/apps/dev_control_plane_supervisor_v2.py" state \
  --state-dir "$DCP_V2_RUNTIME_ROOT/state" \
  --request-id '<pilot-canary-evidence-request-id>' \
  > "$DCP_V2_QUALIFICATIONS/$DCP_V2_MERGED_SHA.app-server-canary.json"
python3 "$DCP_V2_STAGED_RELEASE/apps/dev_control_plane_supervisor_v2.py" state \
  --state-dir "$DCP_V2_RUNTIME_ROOT/state" \
  --request-id '<pilot-staged-evidence-request-id>' \
  > "$DCP_V2_QUALIFICATIONS/$DCP_V2_MERGED_SHA.staged-runtime.json"
chmod 600 \
  "$DCP_V2_QUALIFICATIONS/$DCP_V2_MERGED_SHA.app-server-canary.json" \
  "$DCP_V2_QUALIFICATIONS/$DCP_V2_MERGED_SHA.staged-runtime.json"
```

Do not register the release candidate until the executor readback proves
durable exact thread/host/model/reasoning registration and started progress.
Do not send the checkpoint follow-up until durable registration, exact GitHub
admission readback and the deterministic merged-head `proof_only_wait` are
visible, with no `release_action` enqueued. Do not write the final evidence
files until that one follow-up is durably receipted. Repeat a request only with
the same request and message IDs only when the durable receipt already proves
the call completed; ambiguity about whether `run_turn` began consumes the
attempt and blocks this qualification. Proceed only when state shows
`automation_workers.ready=true`, one exact Sol/Ultra executor, exactly one
attempted and one receipted checkpoint `codex_followup`, canonical progress
below `100`, the expected proof-only queue wait, no technical terminal, no
curator attention, `final_attention_deferred=true`, and no incident/blocker.
A model string alone never proves lifecycle/event control.

Stop the foreground pilot gracefully. Its App Server child and socket must
close, while SQLite, the checkpoint and outbox remain durable for launchd
recovery. There must still be no terminal or attention event.

For the legacy-present branch, now retire the exact archived launch agent. This
is the narrow cutover window: the staged v2 checkpoint is durable, the
foreground pilot is stopped, and launchd v2 is not active yet. Retirement must
consume the verified archive manifest and becomes part of the commit-bound
shadow evidence:

```bash
(
  set -o pipefail
  {
    cat "$DCP_V2_EVIDENCE/legacy-shadow-archive.ndjson"
    python3 "$DCP_V2_CHECKOUT/apps/dev_control_plane_migration_v2.py" retire \
      --archive-manifest "$DCP_V2_RUNTIME_ROOT/backups/legacy-monitor/manifest.json"
    python3 "$DCP_V2_CHECKOUT/apps/dev_control_plane_migration_v2.py" shadow
  } | tee "$DCP_V2_QUALIFICATIONS/$DCP_V2_MERGED_SHA.shadow.ndjson"
)
chmod 600 "$DCP_V2_QUALIFICATIONS/$DCP_V2_MERGED_SHA.shadow.ndjson"
! launchctl print "gui/$(id -u)/com.orenvlad.codex-session-monitor"
shasum -a 256 "<backup_path_from_manifest>"
```

Require `status=retired`, the exact legacy label absent from launchd,
`plist_preserved=true`, `source_state_preserved=true`, and the backup digest
unchanged. The final shadow record remains `authoritative=false`. Failure here
does not permit activation. Once retirement succeeds, no rollback in this
runbook may start the legacy observer again.

For the clean-Mac branch, run no `retire` command. Instead take a fresh exact
absence proof into a new direct private directory and use its one JSON result as
the shadow evidence file:

```bash
(
  set -o pipefail
  python3 "$DCP_V2_CHECKOUT/apps/dev_control_plane_migration_v2.py" absence \
    --destination "$DCP_V2_RUNTIME_ROOT/backups/legacy-absence-final" | \
    tee "$DCP_V2_QUALIFICATIONS/$DCP_V2_MERGED_SHA.shadow.ndjson"
)
chmod 600 "$DCP_V2_QUALIFICATIONS/$DCP_V2_MERGED_SHA.shadow.ndjson"
shasum -a 256 \
  "$DCP_V2_RUNTIME_ROOT/backups/legacy-absence-final/absence.json"
```

Require the same exact `dev-control-plane/legacy-absence/v2` fields and all
absence facts from Section 2, plus a new `captured_at`, canonical identity
digest and direct `absence.json` file digest. The qualification may bind this
one absence record instead of the archive/retirement/shadow chain. It must not
contain a fabricated retirement or an archive whose source was absent.

Build the qualification manifest only from these four direct private evidence
files and their independently observed lowercase SHA-256 digests:

```bash
shasum -a 256 \
  "$DCP_V2_QUALIFICATIONS/$DCP_V2_MERGED_SHA.suite.txt" \
  "$DCP_V2_QUALIFICATIONS/$DCP_V2_MERGED_SHA.shadow.ndjson" \
  "$DCP_V2_QUALIFICATIONS/$DCP_V2_MERGED_SHA.app-server-canary.json" \
  "$DCP_V2_QUALIFICATIONS/$DCP_V2_MERGED_SHA.staged-runtime.json"
```

Write `$DCP_V2_QUALIFICATION` as a new mode-`0600` regular file with exactly
this schema, replacing every placeholder with the direct basename/digest and a
timezone-aware creation time:

```json
{
  "schema": "dev-control-plane/local-qualification/v2",
  "commit_sha": "<merged-main-SHA>",
  "created_at": "<RFC-3339-with-timezone>",
  "suite": {
    "status": "passed",
    "evidence_file": "<merged-main-SHA>.suite.txt",
    "evidence_sha256": "<suite-evidence-sha256>",
    "real_model_calls": 0
  },
  "shadow": {
    "status": "passed",
    "evidence_file": "<merged-main-SHA>.shadow.ndjson",
    "evidence_sha256": "<shadow-evidence-sha256>",
    "authoritative": false,
    "legacy_mutation_authority": "stopped",
    "real_model_calls": 0
  },
  "app_server_canary": {
    "status": "passed",
    "evidence_file": "<merged-main-SHA>.app-server-canary.json",
    "evidence_sha256": "<canary-evidence-sha256>",
    "binary": "/Applications/ChatGPT.app/Contents/Resources/codex",
    "transport": "stdio",
    "websocket_used": false,
    "model": "gpt-5.6-sol",
    "reasoning": "ultra",
    "exact_thread_event_control": true,
    "single_attempt_canary": true,
    "model_attempt_count": 1,
    "model_call_count": 1,
    "contract_kind": "checkpoint",
    "progress_percent": 40,
    "real_model_calls": 1
  },
  "staged_runtime": {
    "status": "passed",
    "evidence_file": "<merged-main-SHA>.staged-runtime.json",
    "evidence_sha256": "<staged-runtime-evidence-sha256>",
    "private_socket": true,
    "single_writer": true,
    "final_attention_deferred": true,
    "real_model_calls": 0
  }
}
```

Replace the sample `progress_percent=40` with the actually observed canonical
stage below `100`. The canary evidence's exact `app_server_canary` object
contains only its schema and status, Supervisor/executor/thread identity,
stdio/model/reasoning identity,
`turn_ids`, `item_ids`, lifecycle count/digest and completed-turn IDs,
`single_attempt_canary`, both model counters, `contract_kind`,
`progress_percent`, `checkpoint_event_id` and
`checkpoint_payload_sha256`. It contains no task-terminal, contour-verification
or attention ID/digest. Its exact `staged_runtime` object contains private
socket mode/owner, live single-writer generation/lease, activation identity,
`final_attention_deferred=true` and `additional_model_calls=0`; it contains no
terminal/attention field or ID.

The one successful canary call is the recorded checkpoint-contract turn. The
staged runtime section makes no additional model call. Do not mark a section
passed from prose or reuse qualification evidence from another SHA. The
installer securely re-reads every direct evidence file, verifies its digest and
exact section fields, and rejects a missing, stale, symlinked, hard-linked,
over-permissive or changed artifact.

## 9. Atomic local launchd activation and signed ingestion

Activate only after the shadow/archive, canary, hosted rollout and private
socket pilot are green:

```bash
python3 "$DCP_V2_CHECKOUT/apps/dev_control_plane_local_install_v2.py" install \
  --source "$DCP_V2_CHECKOUT" --expected-sha "$DCP_V2_MERGED_SHA" --activate \
  --qualification-manifest "$DCP_V2_QUALIFICATION"
curl --fail --silent --show-error http://127.0.0.1:8766/api/v2/health
curl --fail --silent --show-error http://127.0.0.1:8766/api/v2/readiness
curl --fail --silent --show-error http://127.0.0.1:8766/api/v2/state
```

Require `local_supervisor_v2`, a live singleton lease, a fresh higher
generation, `single_writer=true`, exact current release, private-socket-only
mutation, `automation_workers.ready=true`, and the owned thread resumed. The
pilot workstream must still show its last canonical checkpoint below `100`,
`model_attempt_count=1`, `model_call_count=1`, no terminal/attention and
`final_attention_deferred=true`. A stale pilot generation must be fenced.
The HTTP service is read-only; every POST must remain denied.

The activation result must report `status=installed`, `activated=true`,
`current_release=$DCP_V2_STAGED_RELEASE`, and `staged_release=null`. If
readiness fails, the installer must restore the prior v2 links/plist/service
state and return blocked; do not move links manually or start the retired
legacy observer.

Successful readiness atomically writes two mode-`0600` per-SHA artifacts:
`$DCP_V2_QUALIFICATIONS/$DCP_V2_MERGED_SHA.accepted.json` and
`$DCP_V2_QUALIFICATIONS/$DCP_V2_MERGED_SHA.acceptance-receipt.json`. The
receipt schema is `dev-control-plane/local-activation-acceptance/v2` and it has
exactly `schema`, `commit_sha`, `qualification_sha256`,
`release_manifest_sha256`, `supervisor_generation`,
`activation_nonce_sha256`, `accepted_at`, and `hmac_sha256`. The installer
signs its canonical unsigned fields with the independent external
`install_acceptance_hmac.key` only after exact-release readiness succeeds.

Rollback or forward restoration is eligible only when the immutable release
manifest, accepted qualification, SHA, successful Supervisor generation,
activation nonce digest and receipt HMAC all validate. `install.json` also
binds the qualification and activation nonce digests, but matching a copied
accepted manifest is not provenance. A missing, changed, unsigned or forged
accepted/receipt pair fails closed. Never copy, reconstruct or synthesize
either artifact by hand.

Trigger bounded maintenance through the private socket, then require a signed
projection ACK and an empty due projection queue. The hosted response may
contain receipt identity only and must not contain a command. Re-run the three
hosted probes and require the dashboard's `last_seen` to become fresh; the
release and task identities must match the sanitized local projection. Inspect
the dashboard only through the existing authenticated browser/session; do not
put Basic Auth credentials on a command line or in evidence.

```bash
python3 "$DCP_V2_RUNTIME_ROOT/current/apps/dev_control_plane_supervisor_v2.py" tick \
  --state-dir "$DCP_V2_RUNTIME_ROOT/state" \
  --request-id '<post-activation-tick-request-id>'
python3 "$DCP_V2_RUNTIME_ROOT/current/apps/dev_control_plane_supervisor_v2.py" state \
  --state-dir "$DCP_V2_RUNTIME_ROOT/state" \
  --request-id '<post-activation-state-request-id>'
```

These convenience commands are socket clients; they do not open SQLite or
acquire a second generation.

## 10. Restart and network-loss/outbox recovery proof

Record the healthy generation, restart only the exact v2 launchd unit, and wait
for readiness with a bounded poll. A launchd restart may briefly make the
loopback socket unavailable; only the final bounded result is a gate:

```bash
launchctl kickstart -k "gui/$(id -u)/com.orenvlad.dev-control-plane-v2"
for attempt in $(seq 1 60); do
  if curl --fail --silent --show-error \
    http://127.0.0.1:8766/api/v2/readiness \
    > "$DCP_V2_EVIDENCE/post-restart-readiness.json"; then
    break
  fi
  test "$attempt" -lt 60 || exit 1
  sleep 1
done
curl --fail --silent --show-error http://127.0.0.1:8766/api/v2/health
curl --fail --silent --show-error http://127.0.0.1:8766/api/v2/state
python3 "$DCP_V2_RUNTIME_ROOT/current/apps/dev_control_plane_supervisor_v2.py" state \
  --state-dir "$DCP_V2_RUNTIME_ROOT/state" \
  --request-id '<post-restart-state-request-id>'
```

Require a higher generation, one live writer, exact release unchanged, owned
thread resume/reconciliation complete, the same one checkpoint and model
counters durable, and no duplicate follow-up. Progress remains below `100`,
`final_attention_deferred=true`, and no terminal or curator-attention event
exists yet.

Do not alter the Mac's global network, DNS, firewall or the public server to
manufacture an outage. The authoritative safe network-loss proof is the
isolated fake projection fixture in:

```bash
python3 "$DCP_V2_CHECKOUT/apps/dev_control_plane_supervisor_runtime_v2_smoke.py"
python3 "$DCP_V2_CHECKOUT/apps/dev_control_plane_supervisor_v2_smoke.py"
python3 "$DCP_V2_CHECKOUT/apps/dev_control_plane_projection_v2_smoke.py"
```

It must prove work continues while projection delivery fails, the durable
snapshot remains pending across a new Supervisor generation, replay is
idempotent after recovery, source time/body stay immutable, the retry transport
timestamp is fresh, and the server rejects stale/replayed generations. Couple
that fixture proof with the live restart and a successful signed post-restart
ACK; do not claim a real outage that was not observed.

## 11. Rollback plan and bounded proof

Always record the hosted plan and dry-run before declaring rollback readiness:

```bash
cd "$DCP_V2_CHECKOUT"
python3 apps/dev_control_plane_hosted_deploy.py rollback-plan
python3 apps/dev_control_plane_hosted_deploy.py rollback --dry-run
python3 apps/dev_control_plane_hosted_deploy_smoke.py
python3 apps/dev_control_plane_local_install_v2_smoke.py
```

The proof must state `legacy_fallback=false` and `state_deletion=false`. On the
first hosted v2 release, `previous` is legitimately absent. In that exact case
`rollback --dry-run` must exit `0` and return
`status=dry_run_not_eligible_first_release`, `live_executed=false`,
`eligibility.eligible=false`, and
`eligibility.reason_code=not_eligible_first_release`. This is a successful
machine-readable eligibility proof, not a rollback. A hosted
`rollback --live` is forbidden for this first-release state and must not be
called; its fail-closed fixture is the only live-path negative proof. Never
manufacture `previous`, point it at legacy code or reactivate the legacy
observer.

For a later v2 update, the dry-run must instead return
`status=dry_run_passed`, `live_executed=false` and bind two distinct, verified
immutable v2 releases. Only then is a live rollback drill eligible. If the
drill is deliberately included in that update's Passport:

1. record both identities and current health;
2. run `python3 apps/dev_control_plane_hosted_deploy.py rollback --live`;
3. repeat loopback/public/WebCore probes and prove projection-only authority;
4. restore the desired exact merged release through the complete
   print-plan/validate/dry-run/live sequence, not by moving links manually;
5. for local rollback, run
   `dev_control_plane_local_install_v2.py rollback --activate`, prove the
   generation/release, then reinstall the desired exact `origin/main` release
   with `install --expected-sha ... --activate --qualification-manifest
   <runtime-root>/qualifications/<desired-SHA>.accepted.json` and prove it
   again. Before either direction, both releases must already have an intact
   accepted qualification and a valid signed per-SHA
   `.acceptance-receipt.json` whose HMAC and immutable release bindings pass.
   The installer rotates the activation nonce, proves the new generation and
   refreshes that release's signed receipt only after readiness; never create,
   copy or repair either artifact during rollback.

For the first local v2 release, record the installer rollback fixture and the
exact-release restart/reinstall recovery proof; do not invent a local
`previous` release. A later local live rollback is eligible only under the same
two-distinct-accepted-v2-release rule in step 5.

Quarantine after a failed first-release proof is a fail-closed safety state,
not a successful rollback. Recovery from it uses the complete merged-source
`print-plan` → `validate` → `deploy --dry-run` → `deploy --live` flow;
it never manually recreates the disabled app/nginx links. The quarantine
marker, failed immutable release, projection DB, legacy evidence and TLS
material remain preserved for audit.

## 12. Post-cutover legacy-retirement or absence readback

Retirement already occurred in the narrow barrier between the staged pilot and
atomic activation because the qualification contract will not accept a second
legacy mutation authority. After local restart recovery, signed hosted
ingestion, fresh `last_seen`, all three hosted probes and rollback proof,
re-read that state without running `retire` a second time.

For the legacy-present branch:

```bash
! launchctl print "gui/$(id -u)/com.orenvlad.codex-session-monitor"
shasum -a 256 "<backup_path_from_manifest>"
curl --fail --silent --show-error http://127.0.0.1:8766/api/v2/health
```

Require the exact legacy label still absent from launchd, the backup digest
unchanged, the preserved plist and source DB still present, and v2 health
unchanged. Do not delete the plist, source DB, archive or hosted legacy
collections. A rollback never starts this observer again.

For the clean-Mac branch, there is no archive digest, preserved plist or
retirement receipt to check. Take a third direct absence observation into a
new private directory:

```bash
(
  set -o pipefail
  python3 "$DCP_V2_CHECKOUT/apps/dev_control_plane_migration_v2.py" absence \
    --destination "$DCP_V2_RUNTIME_ROOT/backups/legacy-absence-post-cutover" | \
    tee "$DCP_V2_EVIDENCE/legacy-absence-post-cutover.json"
)
chmod 600 "$DCP_V2_EVIDENCE/legacy-absence-post-cutover.json"
shasum -a 256 \
  "$DCP_V2_RUNTIME_ROOT/backups/legacy-absence-post-cutover/absence.json"
curl --fail --silent --show-error http://127.0.0.1:8766/api/v2/health
```

Require a new mode-`0600` direct manifest with schema
`dev-control-plane/legacy-absence/v2`, the exact label and canonical paths,
`source_present=false`, `plist_present=false`, `launchd_loaded=false`,
`launchd_pid=null`, `authoritative=false`, valid `captured_at`, a matching
`evidence_sha256`, and an independently matching direct `absence.json` file
SHA-256. This is machine-verifiable clean-Mac evidence; it must not contain an
archive, retirement claim or synthetic legacy path. Exactly one of the two
branches in this section belongs in the rollout record.

At this point every required proof is complete, but the workstream is still
nonterminal and no curator attention exists.

## 13. Deterministic terminal and target-lane closure

Only after Sections 1–12 pass, perform fresh exact GitHub, hosted and local
readbacks and write one private terminal command input. It has exactly
`terminal` and `message_id`; its terminal object has every field below and no
unknown field:

```json
{
  "terminal": {
    "terminal_id": "<stable-terminal-id>",
    "event_id": "<stable-terminal-event-id>",
    "task_id": "<pilot-task-id>",
    "task_revision": 1,
    "workstream_id": "<pilot-workstream-id>",
    "workstream_revision": 1,
    "executor_generation": 1,
    "executor": {
      "thread_id": "<exact-owned-thread-id>",
      "host_id": "<exact-owned-host-id>",
      "model": "gpt-5.6-sol",
      "reasoning": "ultra"
    },
    "closure_kind": "release:production",
    "summary_ru": "Orchestrator Codex v2 развёрнут и независимо проверен.",
    "evidence": [
      "origin/main:<exact-merge-SHA>",
      "production:healthy:<exact-hosted-release-identity>",
      "local-supervisor:ready:<exact-release-and-generation>",
      "restart-recovery:passed:<before-and-after-generations>",
      "offline-outbox-replay:passed:<fixture-evidence-digest>",
      "rollback:passed:<exact-dry-run-status>",
      "legacy-state:passed:<archive-or-absence-manifest-digest>"
    ],
    "checks": [
      "v2-suite:passed",
      "self-closure:SUCCESS",
      "hosted-probes:passed",
      "local-readiness:passed",
      "restart-recovery:passed",
      "offline-outbox-replay:passed",
      "rollback-proof:passed",
      "legacy-retirement-or-absence:passed"
    ],
    "pr_identities": [
      "github-pr-v1:orenvlad-ai/dev-control-plane:<PR>:<head-SHA>:<merge-SHA>"
    ],
    "deploy_identities": [
      "hosted-release-v1:wb-core-eu-root:devcontrol.pro:<merge-SHA>"
    ],
    "owner_acceptance_required": true,
    "created_at": "<RFC-3339-with-timezone>",
    "schema": "dev-control-plane/terminal-evidence/v2"
  },
  "message_id": "<stable-terminal-message-id>"
}
```

Replace the three sample integer values with the latest observed positive
revision/generation values; they remain JSON integers. Every
evidence item is a sanitized immutable identity or digest observed in this
rollout; no placeholder, prose-only assertion or raw provider payload is
admissible. Submit it once through the private socket:

```bash
python3 "$DCP_V2_RUNTIME_ROOT/current/apps/dev_control_plane_supervisor_v2.py" command \
  --state-dir "$DCP_V2_RUNTIME_ROOT/state" --name terminal \
  --input "$DCP_V2_PRIVATE_TMP/final-terminal.json" \
  --request-id '<terminal-request-id>'
```

This command is deterministic and invokes the registered independent
`release:production` contour verifier. It never calls App Server or any model;
the complete rollout still has `model_attempt_count=1` and
`model_call_count=1`. Require `created=true`, `progress=100`,
`technical_complete=true`, one verification ID and exactly one pending terminal
attention for the exact curator thread. Repeating after an ambiguous socket
response is allowed only with the identical request/message/event IDs and
payload; it may return `created=false` but may not create another terminal or
attention.

Terminal admission queues the local self-target logical-lane closure. Do not
claim or deliver attention yet. Wait until the active Supervisor has
mechanically processed that queue, then capture a fresh private state readback:

```bash
python3 "$DCP_V2_RUNTIME_ROOT/current/apps/dev_control_plane_supervisor_v2.py" state \
  --state-dir "$DCP_V2_RUNTIME_ROOT/state" \
  --request-id '<post-terminal-lane-readback-request-id>' \
  > "$DCP_V2_EVIDENCE/post-terminal-lane-state.json"
chmod 600 "$DCP_V2_EVIDENCE/post-terminal-lane-state.json"
sqlite3 -readonly "$DCP_V2_RUNTIME_ROOT/state/supervisor.sqlite3" \
  "SELECT event_type, COUNT(*) FROM events
   WHERE task_id = '<pilot-task-id>'
     AND event_type = 'target_lane_closure_completed'
     AND json_extract(payload_json, '$.action.task_revision') = <latest-task-revision>
     AND json_extract(payload_json, '$.action.workstream_revision') = <latest-workstream-revision>
   GROUP BY event_type;
   SELECT kind, state, COUNT(*) FROM outbox
   WHERE task_id = '<pilot-task-id>'
     AND state IN ('pending', 'inflight')
     AND kind IN (
       'codex_thread_start', 'codex_followup', 'codex_successor_start',
       'release_candidate_intake', 'release_candidate_resolution',
       'release_action', 'release_arbiter_case', 'incident_arbiter_case',
       'incident_arbiter_application', 'target_lane_closure'
     )
   GROUP BY kind, state;"
```

The first query must return exactly
`target_lane_closure_completed|1`; the second must return no rows. The
sanitized state must contain exactly one current release-lane row with
`deploy_status=lane_released` and `verification_status=released`, the exact
terminal attention still `pending`, and no parked lane or incident. This
read-only SQLite query acquires no generation and selects only machine fields;
it is not a writer or a substitute for the socket/API readback. Finally tick
until the terminal/lane-complete projection receives a signed ACK and no due
projection snapshot remains. A pending curator attention is expected and does
not count as a lane mutation.

## 14. Stateless exact-curator delivery and owner acceptance

After the exact lane-closure and projection-ACK barrier above, prepare one
durable attention claim:

```bash
printf '%s\n' '{"visibility_timeout":120}' \
  > "$DCP_V2_PRIVATE_TMP/prepare-attention.json"
chmod 600 "$DCP_V2_PRIVATE_TMP/prepare-attention.json"
python3 "$DCP_V2_RUNTIME_ROOT/current/apps/dev_control_plane_supervisor_v2.py" command \
  --state-dir "$DCP_V2_RUNTIME_ROOT/state" --name prepare_attention \
  --input "$DCP_V2_PRIVATE_TMP/prepare-attention.json" \
  --request-id '<prepare-terminal-attention-request-id>' \
  > "$DCP_V2_PRIVATE_TMP/prepared-terminal-attention.json"
chmod 600 "$DCP_V2_PRIVATE_TMP/prepared-terminal-attention.json"
```

Require `kind=terminal`, `attempt=1`, the exact task/workstream and curator
thread `$DCP_V2_CURATOR_THREAD_ID`, one immutable `event_id`,
`attention_id`, `payload_digest` and `claim_token`. The returned `handoff_ru`
must be short, self-contained Russian text containing the real PR/merge/deploy
identities, one or two completed items, checks and genuine limitations, and it
must end by asking the owner to reply exactly:

```text
Задача принята
```

The stateless delivery-only bridge sends exactly that one `handoff_ru` once
through the supported `send_message_to_thread`/Codex delegation transport to
that exact curator task. It does not monitor, schedule, decide or send routine
progress. After the transport returns an exact success identity, create the
ACK input with exactly the prepared `event_id`, `attention_id`,
`curator_thread_id`, `payload_digest` and `claim_token`, then call
`--name ack_attention`. Require `delivered=true`, retain the transport identity
and ACK result, and obtain a signed projection ACK showing the same attention
as delivered.

If transport fails before delivery is proven, submit one bound
`nack_attention` with a future `retry_at` and sanitized reason code; the durable
event remains pending and technical closure is not presented as delivered. If
transport outcome is ambiguous, do not send the text again blindly: preserve
the inflight claim and reconcile the exact transport message identity first.
No ACK may be synthesized without proved delivery, and no second terminal
attention may be created.

The Supervisor must not generate `Задача принята` on the owner's behalf.
Only after the delivery ACK is durable may an observed reply from the exact
Passport curator thread be submitted through the private socket as an
`owner_acceptance` receipt bound to the current task revision. The socket
payload contains exactly `receipt`, `source_attestation` and `message_id`. The
receipt contains exactly `schema` (`dev-control-plane/owner-acceptance/v2`),
`receipt_id`, `task_id`, current `task_revision`, exact `curator_thread_id`,
`reply` (`Задача принята`) and `created_at`. The source attestation contains
exactly `schema` (`dev-control-plane/owner-acceptance-source/v2`), exact
`curator_thread_id`, the supported host bridge's `source_message_id`, the
delivered terminal `attention_event_id`, numeric `observed_at_epoch`, lowercase
SHA-256 `reply_sha256`, and HMAC-SHA256 `signature`.

The stateless bridge signs the canonical source binding with the exact current
release's `owner_acceptance_source_signature` helper and the independent
owner-acceptance key only after observing that exact reply; it does not
reimplement or weaken the canonical JSON. An observation more than seven days
old or over 120 seconds in the future, changed receipt/source binding,
reply-digest mismatch or invalid signature fails closed.

Send this payload with `--name owner_acceptance` only after the configured
stateless bridge verifier independently attests the source message and the
registry shows that exact attention delivered. If the bridge verifier is
unavailable, acceptance remains pending. Any other text, thread,
message/attention binding or revision is rejected:

```bash
python3 "$DCP_V2_RUNTIME_ROOT/current/apps/dev_control_plane_supervisor_v2.py" command \
  --state-dir "$DCP_V2_RUNTIME_ROOT/state" --name owner_acceptance \
  --input "$DCP_V2_PRIVATE_TMP/owner-acceptance-private.json" \
  --request-id '<owner-acceptance-request-id>'
```

After the exact receipt is durable and its signed projection ACK is observed,
the task may disappear from active dashboard cards while remaining in sanitized
audit history. Securely dispose of the remaining private claim/receipt files
and temporary directory. If owner acceptance has not arrived, the rollout is
technically complete but the task remains
`Завершена — требуется приёмка`; do not report it as accepted.

If the outcome before terminal is instead a proven strict HumanGate, send its
one durable self-contained handoff through the same exact-curator delivery/ACK
path. It contains exact evidence and exactly one minimal human-exclusive
action; it never converts routine Git, CI, merge, deploy, retry,
reconciliation or a reversible engineering choice into a gate. The sole
protected-authority case is Section 15, where exact-head governed review/merge
is itself the allowlisted security/permission authorization. Terminal evidence
is not created for a blocked contour.

## 15. Governed one-writer maintenance updates

After the bootstrap, a candidate release is never started beside the installed
Supervisor. The current accepted v2 release and its registry remain the trust
anchor and sole writer throughout staging. The update Passport declares the
exact PR/head, changed paths, resources, rollout and rollback scope; a merged PR
observed later is proof-only and can never be converted into a pending release
actuation.

An ordinary unprotected update follows the same clean-main, fake-first,
hosted-runner, inactive-install and qualification gates above. A change to
`.github/**`, `AGENTS.md`, Supervisor/registry/release/contract policy,
projection authority/auth/state, hosted deploy, migration or local installer
is protected and uses exactly two governed phases:

1. **Permission phase.** The installed Supervisor independently reads the full
   diff at the exact open PR head, parks that workstream, releases its scheduler
   locks and creates one durable `security_permission_change` HumanGate. It
   performs no merge and no candidate code processes its own authorization.
   After all independent safe checks are complete, the stateless bridge
   delivers that exact-head gate once. The one human-exclusive action is for
   the owner to explicitly authorize and merge that exact head through governed
   GitHub review/merge. `owner_acceptance`, a Task Passport flag, green checks
   or candidate-authored evidence cannot supply this permission. If the head or
   protected path set changes, the authorization is stale: use a new Passport
   and PR/head and repeat the permission phase.
2. **Application phase.** Only after GitHub returns `MERGED`, the unchanged PR
   head and exact `origin/main == mergeCommit.oid` may the installed old
   Supervisor treat that result as read-only authorization proof. From a fresh
   checkout, run the complete v2 suite and hosted
   `print-plan` → `validate` → `deploy --dry-run` → `deploy --live`
   sequence, stage the immutable local release without activation, and create
   all SHA-bound evidence. The old release remains the only local writer during
   these steps.

The local application barrier is exact:

1. require the current release ready, its projection ACK current, no pending or
   inflight mutation kind from the Section 13 query, and no live task/resource/
   release/thread claim that the update would interrupt;
2. create and integrity-check an online SQLite backup under the private v2
   backup directory, retain the current release/plist/acceptance receipt, and
   record their immutable identities;
3. gracefully boot out only
   `com.orenvlad.dev-control-plane-v2` and prove its lease/process is gone; do
   not move `current` or `previous` and do not start legacy code;
4. start exactly one staged foreground Supervisor on the same registry. It must
   acquire a strictly higher fenced generation, reconcile the durable state and
   perform at most one SHA-bound checkpoint qualification attempt. No old
   launchd generation may coexist with it;
5. stop the staged process gracefully and activate only through
   `dev_control_plane_local_install_v2.py install --expected-sha ... --activate
   --qualification-manifest ...`. Require the new launchd generation, exact
   release, signed activation receipt, resume/reconciliation and projection ACK;
6. if staged qualification fails before links move, stop it and bootstrap the
   unchanged old launchd plist/current release, then prove the prior exact
   health. If activation fails after links move, let the installer restore only
   the verified prior v2 links/plist/service and prove that identity. Never run
   two generations, repair symlinks manually or fall back to legacy.

At the barrier, the global mutation query (not merely an update-task filter)
must return no rows. Create the online backup before bootout and verify it
without opening a write transaction in the Supervisor:

```bash
sqlite3 -readonly "$DCP_V2_RUNTIME_ROOT/state/supervisor.sqlite3" \
  "SELECT kind, state, COUNT(*) FROM outbox
   WHERE state IN ('pending', 'inflight')
     AND kind IN (
       'codex_thread_start', 'codex_followup', 'codex_successor_start',
       'release_candidate_intake', 'release_candidate_resolution',
       'release_action', 'release_arbiter_case', 'incident_arbiter_case',
       'incident_arbiter_application', 'target_lane_closure'
     )
   GROUP BY kind, state;"
export DCP_V2_PREUPDATE_BACKUP="$DCP_V2_RUNTIME_ROOT/state/backups/supervisor.pre-update.<old-SHA>.<UTC-id>.sqlite3"
test ! -e "$DCP_V2_PREUPDATE_BACKUP"
sqlite3 "$DCP_V2_RUNTIME_ROOT/state/supervisor.sqlite3" \
  ".backup '$DCP_V2_PREUPDATE_BACKUP'"
chmod 600 "$DCP_V2_PREUPDATE_BACKUP"
sqlite3 -readonly "$DCP_V2_PREUPDATE_BACKUP" 'PRAGMA quick_check;'
shasum -a 256 "$DCP_V2_PREUPDATE_BACKUP"
launchctl bootout "gui/$(id -u)/com.orenvlad.dev-control-plane-v2"
! launchctl print "gui/$(id -u)/com.orenvlad.dev-control-plane-v2"
```

Require the first query empty, `quick_check` exactly `ok`, a recorded backup
digest and the old launchd label absent before starting the staged foreground
command from Section 8. If the pre-link qualification fails, restore the
unchanged old authority only with:

```bash
launchctl bootstrap "gui/$(id -u)" \
  "$HOME/Library/LaunchAgents/com.orenvlad.dev-control-plane-v2.plist"
launchctl kickstart -k "gui/$(id -u)/com.orenvlad.dev-control-plane-v2"
```

Then apply the bounded readiness poll from Section 10 and require the exact old
release identity. These commands are not a second updater or rollback path;
they restore the launchd unit whose plist and `current` link were deliberately
left unchanged.

The short interval with zero Supervisor processes is a fenced maintenance
window over durable SQLite/outbox state, not a second authority. At every
instant there is at most one writer, and the next generation may mutate only
after the previous lease is gone and its own higher fencing token is current.
After a successful update, repeat restart/network-loss/rollback, terminal,
lane-closure and exact-curator delivery barriers for that update's own
acceptance envelope.
