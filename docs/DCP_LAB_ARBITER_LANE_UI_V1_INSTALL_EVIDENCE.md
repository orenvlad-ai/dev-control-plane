# DCP Lab shared review/arbiter lane UI v1 installation evidence

Date: 2026-08-15 (Asia/Yekaterinburg)

Status: `INSTALLED_AND_STOPPED`

## Authority and reviewed delivery

- Contract PR #195 exact head
  `7259fc5a9c6aaef5ca966fb90b1113fbccf9b9f5` passed semantic/security review
  `PRR_kwDOSUqHmc8AAAABJqsDow` and baseline workflow `31881285530`, then merged
  at `eb07d5e27d8c22ee39333dac00b66ccf52f930e8`, tree
  `61150d6d99606e543c4a4dc07e7b1098f654255d`.
- Managed-source PR #56 exact head
  `4594d618df1bb43b24a4fc5926415388d728736a` passed semantic/security review
  `PRR_kwDOTydt6M8AAAABJquGbw` and source/package workflow `31882170555`, then
  merged normally at source `bd8d67330fa369b4a18cea30d976567f8c3a5930`,
  tree `4981847fbe6feaaee0383928c7c9d7f514c6361b`.
- Separate pin/install-guard PR #196 exact head
  `2a5c26c1219312b2288586f87dad8cbc3017fe54` passed exact-head review
  `PRR_kwDOSUqHmc8AAAABJqu03Q` and baseline workflow `31882605667`, then merged
  at `57c246d716d9fc9de168577bbe9def0f66bb5dbf`, tree
  `5191e2508099ece86caa4e9070447bcbdf3b8cab`.

## Implemented presentation boundary

- The stock board remains four physical columns. The existing third column is
  one `IN REVIEW / ARBITER` lane with paired review/arbiter counts, ordered
  `ARBITER` and `IN REVIEW` subsections and one card per durable task.
- The shared typed projection owns board lane/subsection, primary label,
  detail, dot/accent, activity and accessibility text for both board and
  sidebar. Queued review is steady yellow; only a running reviewer pulses.
- An eligible/waiting/held or accepted-pending automatic arbiter is steady
  purple. Only a durably running arbiter action pulses purple. A successor
  repair returns the same card through Working, Review, Ready and Merged.
- Exact terminal Human Gate remains steady orange Needs You / Needs your
  decision with its durable question. Genuine failure remains steady red.
  Reduced-motion disables animation without changing the state signal.
- No backend, API schema, SQLite, migration, daemon, lifecycle, model,
  provider, admission or merge-authority source changed.

## Source, DOM and package proof

The managed-source exact head and GitHub workflow passed source/provenance/
identity/absence gates, sqlc/OpenAPI parity, all Go tests and build, frontend
typecheck, the governed 15-file renderer suite with 352 tests, arm64 packaging,
signing and bundle inspection. Local focused projection/board/sidebar/query/
i18n coverage passed 177 tests across five files.

Canonical `prepare`, `build`, `install` and `preflight` repeated the complete
gates from clean control-plane main `57c246d716d9fc9de168577bbe9def0f66bb5dbf`.
The receipt-bound exact installed-source checkout independently passed the same
five focused files and all 177 tests. The installed `app.asar` contains the
exact `In review / Arbiter`, `Waiting for arbiter`, `Arbiter evaluating`,
`Needs your decision`, dark-theme `#c084fc` and light-theme `#7e22ce` literals.

An optional unrestricted renderer sweep was also diagnostic-only: its new DCP
tests passed, while 20 pre-existing non-contract cases remained red in DCP
mode (18 removed-updater expectations and two API-dependent PR-hydration
expectations). They are outside the governed 15-file package suite and this
UI-only diff; no acceptance claim relies on that sweep.

## Deterministic stopped install

Before replacement, the shared laboratory held 58 durable model actions, 38
ReviewRuns and zero active worker/reviewer/policy/arbiter actions. Cards 31-34
had been added and terminally merged by a separate preceding laboratory flow
after the supplied checkpoint; this UI pass created or changed none of them.
The exact prior bundle was source `5def887cb1c240ca309c4c5ff7bd6298af4784ee`,
tree `885af5298339e8562a22a78f8538cd1c1da4b6e1`, receipt SHA-256
`15b72e71a32863c946a9e6ccf87343bd995d53fe472b2654215ab988696cba9e`.

The governed installer proved the exact app/daemon pair and zero active model
actions under the gateway lock, requested Quit of only that exact app, waited
for its daemon/run-file/port to disappear, and created backup
`i12-20260815T114625Z`. The backed-up and final SQLite files are byte-identical
at SHA-256 `301ef7cfd5717783e6245e15930da92b50c9435df550720494acc2408ff69a9a`.

Installation completed at `2026-08-15T11:46:26Z`. The exact receipt is:

```text
fork_commit=bd8d67330fa369b4a18cea30d976567f8c3a5930
fork_tree=4981847fbe6feaaee0383928c7c9d7f514c6361b
daemon_sha256=efbfe12f1891c9e013a56fc8b3e1bc8a98884af6ec8c54dd2259b51c2307e953
asar_sha256=bf51470a52cf5b3e4de382daeb9554db98fe61ad682997b3731db80d9b0c1d4d
receipt_sha256=653417573689a62cd0fb570c0bbc9e432a38e0b57af1347a93f606dd94228760
```

Model-free preflight passed. Post-install status is `stopped`: run-file is
absent and port 43231 is free. SQLite integrity is `ok` and still contains 22
policy tasks, 58 actions, 38 reviews, 26 admissions and six ordinary-card
arbiter generations with zero active actions, running reviews or active
admissions.

Card 27 remains `incident` revision 10, PR #24 remains exact head
`58adc8c6abe1d2fee90cd1bfa9addd149cede1a8`, and the latest arbiter remains
terminal `human_gate` with the unchanged question:

```text
Should qualification/arbiter-c.txt on main remain mode=left or be replaced with mode=right?
```

## Model and mutation accounting

This presentation pass launched zero DCP workers, reviewers or arbiters,
created zero synthetic tasks/branches/PRs, consumed zero DCP model tokens and
performed no provider/admission/merge operation. No live synthetic canary or
controlled runtime restart was needed: receipt-bound artifact strings and
deterministic DOM/state fixtures cover the UI contract while the canonical
application remains stopped. No old-application cleanup was performed.

This is technical installation evidence, not owner acceptance.
