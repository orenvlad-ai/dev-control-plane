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
4. **Upstream refreshes — separately governed maintenance.** Each update needs
   a new stable pin, LICENSE/NOTICE/dependency review, clean patch rebase,
   build/run gates and one disposable canary. No floating update channel is an
   architectural source of truth.
5. **Control-contract expansion — not approved.** DCP roles, reviewer,
   arbitration, retry/recovery, reconciliation, monitoring, real targets and
   reverse delivery require separate owner authorization.
6. **Production/hosted rollout — not approved.** Signed/notarized distribution,
   a managed fork repository, `wb-core`, `devcontrol.pro`, hosted services,
   parallel orchestration, Entire and Symphony runtime remain outside scope.
