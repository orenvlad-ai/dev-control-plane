# Roadmap

One curator-dispatched repository change may be active at a time. Technical
completion never records owner acceptance.

1. **Documentation baseline — merged as PR #96.** Architecture and authority
   boundaries were recorded.
2. **I2 bounded Python/loopback slice — merged as PR #97 and owner-accepted.**
   It proved one synthetic worker contour but was explicitly experimental. I3
   retires its active launcher/runtime without rewriting history.
3. **I3 native Agent Orchestrator foundation — implemented by this change.**
   Pin official stable `v0.12.1`; prove clean source build/run on macOS; preserve
   native UI, daemon, projects, sessions, worktrees and Codex; add only the
   isolated source launcher and allowlisted one-task adapter; run one native
   acceptance canary with telemetry off; merge through a ready PR and
   fast-forward the canonical checkout.
4. **I5 clean worker and operating contract — implemented by this change.**
   Remove the Codex hook-trust bypass, ignore user config, disable hooks/apps/
   plugins/MCP reachability, retain standard authentication, add exact-contour
   preflight, prove one headless marker canary and publish the versioned current
   curator contract.
5. **I6 correct one-shot worker completion — implemented by this change.**
   Reuse AO's supervised process generation and exact exit outcome so the
   isolated Codex worker is Working while live, Idle after exit zero, and red
   Exited after any unsuccessful outcome. Preserve needs-input and SCM display
   precedence, prove the presentation model-free, and clean one success canary.
6. **I7 single entry and canonical UI/daemon contour — implemented by this
   change.** Make `bin/dcp-ao-submit` the only normal curator/lab lifecycle
   entry; reuse healthy UI-owned runtime without restart, start only from fully
   stopped or one known-safe stale identity, fail closed without kill on every
   foreign/ambiguous state, and hold one singleton through submit. Hide only
   manual orchestrator-spawn UI affordances while preserving backend/CLI/API
   orchestration capabilities. Do not implement reviewer or arbiter.
7. **I8 canonical packaged macOS application — implemented by this change.**
   Package the exact pinned and patched upstream as user-owned native arm64
   `DCP Orchestrator.app`; isolate bundle/executable/daemon/service/state/update
   namespaces; make the app the sole daemon lifecycle owner; move the submit
   gateway from source/dev startup to exact absolute-bundle reuse/open; prove
   cold, warm and two-concurrent synthetic submits; keep updater, telemetry and
   crash reporting unreachable and absent from the bundle. Preserve
   programmatic orchestration while adding no reviewer or arbiter.
8. **Dedicated DCP Git fork — next separately owner-approved architecture
   stage after I8 acceptance.** Create no fork during I8. Until that later
   authorization, the immutable upstream pin plus exact repository-owned patch
   queue remains the sole source boundary.
9. **Upstream refreshes — separately governed maintenance.** Each update needs
   a new stable pin, LICENSE/NOTICE/dependency review, clean patch rebase,
   build/run gates and one disposable canary. No floating update channel is an
   architectural source of truth.
10. **Control-contract expansion — not approved.** DCP roles, reviewer,
   arbitration, retry/recovery, reconciliation, monitoring, real targets and
   reverse delivery require separate owner authorization.
11. **Production/hosted rollout — not approved.** Signed/notarized distribution,
   `wb-core`, `devcontrol.pro`, hosted services, parallel orchestration, Entire
   and Symphony runtime remain outside scope.
