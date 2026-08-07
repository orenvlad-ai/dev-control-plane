# Agent Orchestrator provenance

DCP I3 selects official stable release `v0.12.1` from
`https://github.com/Untrivial-ai/agent-orchestrator.git` at exact commit
`1df40e93772c2c48e916870d9c3ddf8f29a69f84`, tree
`36bf30cc4960c10f0d94fc63a8ff0a4dd22bb8a8`, published 2026-08-05.
GitHub's commit API reports a valid verified signature.

The root upstream `LICENSE` is Apache License 2.0 and has SHA-256
`1a2219722b7ef58364065e9073a2cb2831891eb147a785742a31431c9cddad1d`.
The pinned revision has no tracked NOTICE file. The license beside this record
is preserved byte-for-byte. The frontend manifest's separate MIT metadata is
an unresolved upstream ambiguity that must be addressed before distribution.

## Modification and source boundary

The upstream source checkout, dependency installation, build output and runtime
data remain outside Git. `upstream/agent-orchestrator.lock` fixes provenance and
`patches/agent-orchestrator/0001-isolate-electron-user-data.patch` visibly marks
the only upstream changes. The patch adds an absolute Electron userData override
and tests while preserving upstream behavior when the override is absent.

This repository does not vendor or publish an upstream binary. Future upstream
updates require a new stable pin, license/NOTICE/dependency re-audit, clean patch
rebase and full native qualification.
