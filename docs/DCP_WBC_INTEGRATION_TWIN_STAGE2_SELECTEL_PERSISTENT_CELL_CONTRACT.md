# WBC integration twin Stage 2 Selectel persistent-cell contract

contract_revision: 2026-08-20.1
contract_status: owner-authorized Stage 2 destination and execution authority
program_stage: 2 of 9
repository: `orenvlad-ai/dcp-wbc-integration-lab`
environment: `dcp-wbc-integration-lab-selectel`
service: `dcp-wbc-integration-lab`
new_paid_resources: 0

current_program_role: historical-complete Stage 2 authority; no current mutation authority

Current stage and next-task truth live in the
[current program manifest](DCP_WBC_INTEGRATION_TWIN_CURRENT_PROGRAM_MANIFEST.md).
This contract's execution language is preserved as historical authority.

This contract records the separate owner decision required by section 11 of
the [WBC integration twin and DCP v2 architecture contract](DCP_WBC_INTEGRATION_TWIN_DCP_V2_ARCHITECTURE_CONTRACT.md).
Stage 2 uses one already-paid Selectel server as a persistent isolated lab
cell. It does not activate DCP v2, submit a DCP task, continue the frozen WBC
canary or grant any WBC/production mutation authority.

The server has an unrelated protected co-tenant, **«Лучики добра»**. Old WB Core /
selleros rollback content is retired and may be removed only after exact
classification. The server is therefore a shared host, never a disposable
WBC machine.

## 1. Exact destination decision

| Fact | Pinned value |
| --- | --- |
| Selectel project | `My First Project` |
| Selectel project UUID | `771c31e1970c4cf7a836c07f398661ce` |
| Existing server UUID / DMI UUID | `96be74db-785f-4653-85a8-a4e7c1d3ccdf` |
| Current display label | `ROLLBACK-ONLY_DO-NOT-DEPLOY_wb-core-old-selleros` |
| Public / private address | `178.72.152.177` / `192.168.0.161` |
| Placement | Selectel `ru-3b` |
| OS and capacity | Ubuntu 24.04 LTS; 2 vCPU; 4 GiB RAM; 40 GiB root disk |
| Lab environment | `dcp-wbc-integration-lab-selectel` |
| Lab service | `dcp-wbc-integration-lab` |
| Lab account | new unprivileged `dcp-wbc-lab` |
| Lab root | `/opt/dcp-wbc-integration-lab` |
| Application listener | exact proven-free high port, initially `127.0.0.1:18321` |
| Post-job reachability | required on the exact host through loopback probes |
| Cost boundary | reuse this server; create no VM, disk, load balancer, floating IP or other paid resource |

The display label is evidence, not a workload identity. It may be renamed to a
truthful shared-lab label only through an exact authenticated Selectel route;
renaming is optional and may not change inventory, billing, network or server
identity. Deleting, resizing, rebuilding, snapshotting or moving the VM is
forbidden.

## 2. Authority-first mutation fence

No GitHub lab repository and no Selectel-host write may occur before this
contract passes an ordinary ready pull request with:

- an exact-head context-free semantic/security review with no findings;
- successful required check `baseline` for that exact head;
- zero unresolved review threads;
- a normal merge; and
- clean final-main readback at the exact merge descendant.

The pre-merge host pass is strictly read-only. It must prove the saved SSH host
key, exact DMI UUID, private address and one persistent session; exact lab
repository absence; no competing DCP/source pull request; current disk and
resource facts; and the complete classification below. `UNKNOWN`, identity
drift or an unsafe shared dependency stops before mutation.

## 3. Four-way host classification

Every relevant path, unit, process, account, listener, mount, schedule,
container and firewall rule is classified as exactly one of:
`LUCHIKI_DOBRA`, `LEGACY_WBC`, `SHARED_SYSTEM` or `UNKNOWN`.

### 3.1 Protected `LUCHIKI_DOBRA`

The following surface is owned by «Лучики добра» and is never a cleanup or lab
target:

- `/opt/luchiki-landing`, including its data, metadata, backups, scripts,
  environment files and the known zero-byte `app/data/.counter.*.tmp` failure
  artifacts;
- `/etc/systemd/system/luchiki-counter.service` and
  `/etc/systemd/system/luchiki-counter.timer`;
- `/etc/nginx/sites-available/luchiki-landing` and the exact enabled
  `luchiki-landing` site;
- its TLS material below
  `/etc/letsencrypt/live/xn----8sbclsang6avz2c.xn--p1ai`;
- nginx public listeners `80` and `443` insofar as they serve that site; and
- its process, timer, HTTPS, certificate-renewal and network dependencies.

Read-only entry evidence on 2026-08-20 proved HTTP 200 with successful TLS
verification, active nginx on 80/443, the enabled site, the same certificate
fingerprint and expiry, active/waiting `luchiki-counter.timer`, and the same
pre-existing `luchiki-counter.service` exit-code failure. The timer and service
unit SHA-256 values remained
`61973e6a6d4807463e01ad748dde7032cf6cb74a958102b0b22791dff72ca4b6` and
`35d44a10865180aea9cdc604eff44ec3adee8a43ea7238269de3f52311927426`.

The failing timer continues to create zero-byte temporary files while the root
disk is full. That protected project-owned dynamic subtree is recorded
separately from the static application metadata digest; it is not repaired,
deleted or normalized by Stage 2. A later timer-owned change is acceptable only
when its exact unit invocation and timestamps prove it, the static application
digest is unchanged and HTTPS remains healthy. No Stage 2 step may trigger,
rewrite or hide the truthful pre-existing failure.

### 3.2 Retired `LEGACY_WBC`

The following exact exclusive surfaces are retired WB Core / selleros and may
be stopped, disabled, quarantined or removed after the authority merge:

- roots `/opt/wb-core-runtime`, `/opt/wb-ai`, `/opt/wb-ai-repo` and
  `/opt/wb-web-bot`;
- services `wb-ai-api.service` and `wb-core-registry-http.service`;
- timers and paired services
  `wb-core-sheet-vitrina-closure-retry.*` and
  `wb-core-sheet-vitrina-refresh.*`;
- the five non-comment root crontab entries, all of which resolve exclusively
  beneath `/opt/wb-ai` or `/opt/wb-web-bot`, and their exact descendant
  processes;
- Docker container `wb_ai_postgres`, compose project `wb-ai`, and exclusive
  volume `wb-ai_pgdata`;
- legacy listeners `0.0.0.0:8000` and `127.0.0.1:8765`;
- `wb-ai` and `wb-ai.*` nginx site files and old selleros certificate/config
  material, provided nginx itself and every «Лучики добра» binding remain
  unchanged; and
- exact WB-only data roots, starting with
  `/opt/wb-core-runtime/state/promo_xlsx_collector_runs`.

The pre-authority readback measured that collector path at 35,050,256,255
bytes. It is the first destructive cleanup candidate only after every producer
above is stopped/disabled and the literal path is revalidated as a directory,
not a symlink or mount. Because the disk has zero free bytes, the owner permits
permanent deletion of that exact legacy-only data when reversible quarantine
cannot fit. Permanent deletion has no recovery promise and must be reported
literally. No broad path, glob or unresolved variable may be a destructive
target.

### 3.3 Preserved `SHARED_SYSTEM`

The VM, root filesystem and mount, SSH/systemd/journald/cron base services,
nginx process and common configuration, certbot, Docker/containerd engines,
Docker firewall chains, DNS, time service, kernel, system accounts, package
runtime, `/opt/containerd`, root Playwright cache and all other OS/network
infrastructure are `SHARED_SYSTEM`. They remain present and are not upgraded,
removed or reconfigured for the lab. Individual exact legacy units, crontab
lines, container and volume may be retired without stopping their shared
engines.

The entry listener classification is: 22 SSH and 53/323 system services are
shared; 80/443 are protected/shared nginx; 8000 and 8765 are legacy; the lab
high port is absent before install. The host has no UFW policy, INPUT is
accept-by-default, and Docker owns the remaining firewall rules. Stage 2 adds
no public application port and changes no firewall rule.

### 3.4 `UNKNOWN` stop rule

An item is not legacy merely because its name is old or its owner is `root`.
Any unclassified process, path, schedule, listener, mount, container, account,
firewall rule or dependency is `UNKNOWN`. Any `UNKNOWN`, any cross-class
symlink/mount, or any legacy removal that could change «Лучики добра» or a shared
dependency stops the stage before that mutation. Classification may narrow
cleanup; it may not broaden this contract.

## 4. Atomic legacy retirement and protected guard

After authority merge, retirement proceeds one exact action at a time:

1. Capture a fresh protected guard: stable Luchiki application metadata digest
   excluding the exact timer-owned `app/data` subtree; separate dynamic
   metadata digest/count/bytes for that subtree; path byte total; unit
   hashes/states; nginx/site/listeners; HTTPS/TLS proof; and the truthful
   counter failure.
2. Stop and disable one exact legacy producer unit/timer, or remove one exact
   legacy crontab line, and wait for its already-started descendant to exit or
   stop that exact process tree.
3. Immediately repeat the protected guard. Any unaccounted difference stops;
   if the preceding reversible action caused it, restore that exact action.
4. Stop/remove only the exact legacy container and exclusive volume if needed,
   leaving Docker/containerd and their shared rules intact; repeat the guard.
5. Revalidate the literal collector-runs path, then permanently delete only
   that exact legacy-only directory if quarantine cannot fit. Repeat the guard
   and prove free space.
6. Retain any unneeded legacy item rather than guessing. Nginx and its
   Luchiki site are not reloaded merely to remove inactive legacy endpoints.

The lab is not installed until the protected guard is green after cleanup and
the host has adequate disk, memory and CPU headroom.

## 5. Persistent isolated lab cell

The cell uses one new unprivileged `dcp-wbc-lab` account and exact root
`/opt/dcp-wbc-integration-lab`. It may not read, traverse or write Luchiki,
legacy, root, Docker, DCP or other application paths. A self-contained
versioned service artifact is preferred; no host-wide container runtime,
language runtime or shared package is installed or upgraded for the lab.

The service is a hardened systemd unit bound only to `127.0.0.1:18321` after a
fresh free-port proof. It has no public application exposure and no production
route, WBC API, business data or existing server secret. Its target ceilings
are exact:

- `CPUQuota=50%` (at most about 0.5 CPU);
- `MemoryMax=512M`;
- `TasksMax=64` and a bounded open-file limit;
- at most two versioned release artifacts with atomic `current`/`previous`
  selection; and
- rate-limited, non-business service logs with no separate unbounded log file.

The running service exposes only loopback `/healthz` and `/provenance`. The
provenance response reports the exact deployed merge SHA, repository, artifact
digest, environment and service. It contains no credential or host secret.

Lab rollback changes only the lab `current`/`previous` pointer and service.
It cannot restore permanently deleted legacy data and never changes Luchiki,
the VM, network, firewall, nginx, Docker or shared OS. At most two releases and
the current/previous install receipts remain on the host.

## 6. Dedicated deployment credential

One new Ed25519 deployment key is created only after authority merge. Its only
durable private copy is delivered directly to the lab repository Actions
secret `DCP_WBC_LAB_SSH_KEY`; it is never written to Git history or output and
is removed from transient local storage after secret-presence/update readback.
Pinned host verification is stored separately as `DCP_WBC_LAB_KNOWN_HOSTS`;
public host, port and account values are environment-scoped configuration.

The public half is authorized only for `dcp-wbc-lab` with a root-owned exact
forced deploy command, no PTY, no agent/X11/TCP forwarding and no interactive
shell. The command accepts one bounded artifact and exact manifest by stdin,
validates their size/digest/version/repository/merge/environment/service, keeps
at most current/previous, atomically activates one release and starts/restarts
only the lab service. It cannot execute caller-supplied commands or name a
path. The credential grants no access to Luchiki, retired WBC, existing
secrets, Docker, nginx, firewall, users or shared services.

No pre-existing host key, SSH key, password, token, environment secret or
application secret is copied or exposed.

## 7. Lab repository bootstrap and protections

The exact public repository `orenvlad-ai/dcp-wbc-integration-lab` is created
only after a fresh 404 readback and this authority merge. A minimal direct
default-branch bootstrap is the sole empty-repository exception and must state
that exception in its commit and README. It creates only the inert target,
baseline, target spec, qualification issuer, Release Train, deploy adapter,
security boundary and tests needed to make ordinary pull requests possible.

Immediately after bootstrap:

- default branch is `main`, deletion and force-push are blocked;
- pull requests and exact required check `baseline` are required for later
  changes;
- required workflow permissions are least-privilege;
- the environment/repository/ruleset numeric identities are read back and
  documented; and
- substantive heads receive a real exact-head context-free semantic/security
  review with no unresolved findings before Release Train admission.

The Stage 2/3 target spec pins the sole qualification issuer as actor
`orenvlad-ai` through the repository-owned qualification dispatch seam. The
DCP issuer is absent/off. A copied manifest, PR content, label or dispatch by a
foreign actor is ineligible. Both issuers are never active together.

## 8. Mechanical Release Train and deploy proof

Stage 2 implements the Stage-1 protocol rather than another architecture. The
provider-neutral core validates the complete immutable manifest, current
repository/base/PR/head/main/check/review/issuer facts, then performs one
expected-head merge or writes immutable `readmission_required` evidence. It
makes no semantic decision, has no second queue, and never auto-syncs, rebases,
updates a branch, force-pushes, substitutes a head or blindly retries.

The versioned Selectel adapter builds a self-contained artifact from the exact
merge SHA, proves its digest/source/run, transfers that artifact through the
dedicated forced command, starts the persistent service and probes loopback
health and provenance. Merge without verified deployment is nonterminal.

The immutable proof binds protocol/target version, task, revision, admission,
PR, admitted head, check and review identity, merge SHA/actor, artifact
identity/digest/source, deployed SHA, environment/service, every probe,
Actions workflow/run/job/actor, all timestamps and a canonical proof digest.
Service-reported deployed SHA, artifact source SHA and merge SHA must be equal.
Proof artifacts and workflow evidence are retained for exactly 90 days; local
host receipts retain current/previous only. Failure produces exact proof and
no automatic redeploy.

## 9. Stage 2 bounded smoke and stop boundary

One bounded inert implementation smoke must use an ordinary pull request and
the qualification-only issuer:

`ready PR -> exact-head baseline -> exact-head semantic/security review -> exact manifest -> Release Train exact merge -> artifact -> persistent install/start -> post-job health/provenance/deployed-SHA readback`

The smoke is one repository change and one merge/deploy. It is not a DCP Task,
card, Command, Action, Admission row or model action. DCP app/daemon/SQLite,
managed source, lock/pin/install and WBC remain untouched. Full independent
adversarial qualification remains Stage 3.

One bounded correction is allowed only for a newly proven implementation
defect that does not widen this contract. Destination ambiguity, protected
drift, unsafe shared dependency, unclassified item, need for another paid
resource, broader credential/network authority or architecture change stops
at a safe atomic `BLOCKED` boundary.

## 10. Stage 2 technical completion

Stage 2 is technically `COMPLETE` only when:

- this authority PR is reviewed, green, merged and present on final main;
- exact legacy retirements and recoverability are recorded literally, root
  free space is proven and the protected before/after guard is truthful;
- the exact public lab repository, repository/ruleset/environment identities,
  workflows, issuer exclusivity and required check are read back;
- the dedicated credential is bounded to the lab cell and no secret appears in
  Git, output or another host path;
- the service is persistent, least-privilege, loopback-only and within the
  exact resource/release/log limits;
- one real exact-head PR merges through the mechanical Release Train and its
  exact artifact remains deployed after the job;
- post-job service health, provenance and deployed SHA equal the immutable
  proof; and
- all worktrees are clean, no new VM/paid resource exists, platform approval
  count is zero and all DCP/WBC prohibited surfaces remain unchanged.

Technical completion is not owner acceptance. Only the owner may write
`Задача принята`.
