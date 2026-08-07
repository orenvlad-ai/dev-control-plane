# Agent Orchestrator provenance

The DCP laboratory design was qualified against the official upstream
repository `https://github.com/Untrivial-ai/agent-orchestrator.git` at exact
commit `f17013b53a1752e86c66e87b45aaa4a463fdff62`, tree
`6402905847ad8f31531b70d0d90f47324c0469b6`, committed 2026-08-07. GitHub's
commit API reported a valid verified signature. The local qualification clone
resolved the same commit and tree from that remote.

The upstream root `LICENSE` is Apache License 2.0 and has SHA-256
`1a2219722b7ef58364065e9073a2cb2831891eb147a785742a31431c9cddad1d`.
The pinned revision has no tracked NOTICE file. Its license is preserved here
byte-for-byte. Dependency manifests and applicable notices must be rechecked
before any later decision to incorporate more upstream source or dependencies.
The upstream frontend manifest separately labels itself MIT; that mismatch is
unresolved provenance evidence, not a license conclusion for a future fork.

## Modification and package boundary

No upstream runtime source file, binary or dependency is vendored or packaged
in the I2 laboratory artifact. DCP's implementation is newly authored under
the separate DCP product identity. `NOTICE` marks the DCP changes and omitted
surfaces. The upstream application was used only as pinned architectural and
safety-qualification provenance.

The laboratory artifact includes this provenance record, the preserved Apache
license and the repository NOTICE. It excludes all upstream updater,
telemetry/analytics, crash-reporting, daemon, mobile, hosted, reviewer, SCM,
release and broad agent-adapter paths.
