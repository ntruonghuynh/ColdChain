# Milestone 5 — blockchain and authorized workflow

**Status: implementation complete; project-owner acceptance pending.** This
milestone adds authenticated custody and quality workflow, a local Solidity
registry, transactional outbox relay, read-only reconciliation and a signed
database audit log. It preserves M1–M4. It does not implement LLM/RAG or the M7
workflow dashboard.

## Implementation

- Solidity contract: `blockchain/contracts/ColdChainRegistry.sol`; Hardhat local
node and idempotent deployment metadata are under `blockchain/`.
- Migration `0005` adds organization-to-chain role mapping, outbox attempt
history, append-only signed audit records and immutable reassessment reviews.
- Backend writes require a PBKDF2-authenticated local user and active DB role.
Workflow events and outbox intents commit together. The worker signs with
server-side role-specific local chain accounts, retries with backoff, and marks
confirmation only after chain evidence is observed.
- `POST /api/auth/login`, `GET /api/auth/me`; `POST /api/workflow/...` for
registration, custody, disposition, reassessment review and warehouse release;
`GET /api/ledger/...` for transaction status, reconciliation, audit
verification and partner hash verification at `/api/ledger/verify/{business_ref}`;
`GET /api/health/ledger` for RPC/deployment health. OpenAPI is at `/api/docs`.
- Only receiving QUALITY may record RELEASE or QUARANTINE. Only receiving
WAREHOUSE may perform release, and only after the RELEASE event is confirmed.
MONITOR is a Receiver-owned, non-login service identity (D-08, selected by the
owner 2026-11-16). The user's M5 instruction authorizes implementation of
BR-10–BR-15; decision status is recorded in requirements §13.6.

Role and transition details: [`../../design/m5-blockchain-workflow.md`](../../design/m5-blockchain-workflow.md)
and [`../../../blockchain/ROLES.md`](../../../blockchain/ROLES.md).

## Evidence run

Executed on 2026-11-16 in this workspace, using an isolated PostgreSQL test
server and the task's temporary Python environment:

| Check | Result |
|---|---|
| Backend and generator tests | Prior host run: **298 passed**. Final Docker test-profile run: **302 passed**, 6 dependency deprecation warnings, 56.29 s. Includes M1–M4 regression, migration 0005, and M5 auth/audit/outbox/retry tests. Raw final log: `raw/backend-generator-tests-acceptance-final.log`. |
| Hardhat Solidity tests | **6 passed** in the final acceptance recheck. Covers allowed workflow, unauthorized roles/invalid transitions, duplicate references, omitted incidents, invalid role grant, invalid constructor role assignment, cross-shipment incident rejection and warehouse release authorization. Raw log: `raw/hardhat-tests-acceptance-recheck.log`. |
| Frontend regression tests | **24 passed** across 4 test files. No M5 dashboard changes were made. |
| Frontend production build | Passed; includes `tsc --noEmit` typecheck and Vite production build. |
| Solidity compilation | Passed with local pinned `solc` 0.8.26. |
| Python compileall | Passed for backend app, migrations and tests. |
| Local registry deployment | Passed against a temporary host-local Hardhat node. A second deployment reused the same contract address without submitting another deployment. Evidence: `raw/local-deploy-*.log`. |
| Local chain write benchmark | 30 accepted sensor-batch anchor transactions, 0 rejected; p50 **0.430 ms**, p95 **0.567 ms** from ethers submission call to mined receipt; median/p95 gas **97,361**. Raw samples: `raw/chain-benchmark.json`. |
| Signed audit benchmark | 30 signed entries appended and committed, 0 rejected; append/commit p50 **1.285 ms**, p95 **3.147 ms**; 30-entry verification passed in **8.617 ms**. Raw samples: `raw/signed-audit-benchmark.json`. |
| Docker service health | Owner-started PostgreSQL, Hardhat, backend, frontend and worker were inspected. PostgreSQL, chain, backend, frontend and repaired worker were healthy; deployment and migration jobs had exited 0. Only backend and worker were rebuilt/recreated. The Hardhat process and PostgreSQL volume were left intact. |
| Non-destructive full-stack smoke | **5 checks passed** through the frontend proxy: `/`, `/shipments`, `/api/health` (database and migration 0005), active policy, and `/api/health/ledger` (chain 31337 and contract bytecode). Raw output: `raw/full-stack-smoke-acceptance.json`. The legacy `scripts/smoke_test.py` was not run because it executes `docker compose down` and restarts the stack; recreating its in-memory Hardhat node would erase chain history. |
| Outbox-to-chain write and idempotency | Two shipper service-layer workflow calls were exercised with the mapped `shipper.demo` identity and a repeated business reference; both returned the same event ID. Each recovered acceptance event has one database ChainRecord and one on-chain BusinessAction, matching payload and shipment hashes. HTTP authentication remains blocked separately. Evidence: `raw/live-registration-service.json`, `raw/live-outbox-confirmation.json`. |
| Chain outage/retry/recovery | The existing chain container was temporarily disconnected from and reconnected to the Compose network (not stopped or recreated). The event moved to `RETRY` at attempt 1 while worker health remained `alive_degraded`; after reconnect it became `CONFIRMED` at attempt 2. The chain remained 31337 at the same address with bytecode present; block advanced 1179 → 1180. Raw evidence: `raw/live-network-outage-recovery.json`, `raw/worker-health-after-network-recovery.json`, `raw/m5-repair-diagnostics.json`. A paused in-flight RPC also resumed and confirmed when unpaused rather than timing out. |
| Worker liveness | The inherited HTTP probe failed because the relay does not serve Uvicorn. The worker-specific heartbeat probe now reports relay liveness/progress separately from dependency state. During the network fault, Docker kept the worker healthy and the probe reported `alive_degraded`, chain unavailable, database available. Final probe output: `raw/worker-health-final.json`. |

Raw captured output is stored in [`raw/`](raw/).

The two timing runs use different operations and execution paths: the chain
sample is an in-process Hardhat node, while the audit sample includes a local
PostgreSQL commit and Ed25519 signing. They are not a matched benchmark and do
not support a claim that either system is faster. They are local prototype
measurements only; production-network latency, gas economics, sustained load,
concurrent contention and recovery latency remain unmeasured. Reproduce with
`npx hardhat run blockchain/scripts/benchmark.ts` and
`PYTHONPATH=backend POSTGRES_DB=<disposable-migrated-db> AUDIT_SIGNING_KEY=<local-32-byte-hex> python scripts/eval/m5_signed_audit_benchmark.py`.

## Focused final acceptance repair — 2026-11-16

The worker inherited the backend image's HTTP healthcheck, which called
`GET /api/health` on port 8000. The relay runs no Uvicorn server, so Docker saw
connection refused. Compose now overrides it with
`python -m app.worker.healthcheck`. The probe checks the relay PID and age of
its completed or active cycle. A live retrying worker stays healthy while
dependency state is reported as degraded; a dead process or cycle stale for
120 seconds fails the probe.

The repeated RPC errors were not signer, contract-address or chain-ID
mismatches. Runtime chain ID and deployment metadata both reported 31337;
contract bytecode was present at `0x5FbDB2315678afecb367f032d93F642f64180aa3`,
and all five database role mappings matched both derived signer and deployed
role addresses. Historical outbox inspection found **147** `INCIDENT_OPENED`
events across **93** shipments; at their failed sends these shipments had not
been registered. The later read-only inventory found 92 at on-chain state
`NONE` and one at `CREATED`, with eight recorded attempts each and no on-chain
record for any of the 147 incident references. Hardhat logs showed the failed
operation was `eth_sendRawTransaction` for `openIncident`. Read-only calls to
the same live contract returned custom error selector `0xa6532e5d`, which is
`InvalidTransition`; a read-only unauthorized signer probe returned
`0x82b42900` (`Unauthorized`). The contract rejects an incident for a shipment
that has not first been registered. The configured MONITOR signer was
authorized. The old relay classified deterministic contract reverts as
uncertain RPC errors, so the generic manager log obscured the cause.

The relay now performs a read-only contract preflight, distinguishes known
contract reverts from transient RPC failures, marks deterministic reverts
FAILED after one attempt, and retains bounded exponential backoff for
retryable/uncertain failures. Retry logs include business reference, event ID,
attempt, operation, sanitized error and next retry time. Repetitive Web3 request
manager errors are suppressed. A live test also exposed Web3 returning hashes
and bytes32 values without the prefix required by the database constraint and
hash comparison; these values are now normalized. A failed database
confirmation rolls back before reconciling an already-mined reference, so the
relay can confirm without resubmitting the on-chain effect.

The approximately 30 ms historical log spacing was not a same-event busy loop:
the 146 adjacent first-attempt intervals across distinct queued incidents had
26.8 ms minimum, 28.6 ms median and 192.2 ms maximum. Across 1,029 subsequent
per-event retry intervals, the minimum was 1.733 s, median 4.374 s and maximum
33.063 s. The worker was draining separate initial events quickly; the stored
retry schedule used backoff. Raw SQL outputs are in
`raw/historical-incident-first-attempt-spacing.txt` and
`raw/historical-incident-retry-spacing.txt`.

The historical 147 failed entries and their attempt rows were preserved. They
were not automatically replayed: resolving them requires registering each
shipment on-chain before opening its incidents, and that ordering and
authorization needs an owner-approved recovery plan. One initial acceptance
event accumulated three attempt records while the serialization bug was being
diagnosed; its earlier outcomes remain visible, while its single chain effect
was reconciled and marked CONFIRMED. The two final acceptance events each have
exactly one on-chain BusinessAction and matching PostgreSQL ChainRecord.

At the start of this continuation, the local JWT setting was the placeholder
`change-me-local-only`. The local setup script now replaces that placeholder
with a cryptographically secure value while preserving all valid existing
secrets and the audit-signing key. Only backend and worker were restarted;
PostgreSQL and the running chain were left up. The secret value is not committed
or included in evidence.

Additional focused tests cover worker liveness during dependency outage,
stale/dead-worker detection, custom-error decoding, transaction-hash formats,
bounded retry scheduling and recovery without a duplicate chain effect. The
M5 security test module has **11 passing tests**. `raw/m5-repair-diagnostics.json`
captures chain/deployment/role agreement, outbox counts and hashes;
`raw/live-contract-rpc-diagnostics.json` records the exact read-only RPC
responses; `raw/worker-retry-classification.log` contains sanitized worker
classification messages. `raw/live-network-outage-recovery.json` records the
observed retry/recovery states; `raw/auth-api-configuration.json` records the
sanitized HTTP 503 authentication configuration response;
`raw/historical-chain-rpc-errors.log` records the original send method and
custom-error selectors without transaction payloads.

## Audit and security boundaries

The signed DB audit uses canonical record hashes, a previous-entry hash and
Ed25519 signatures. Organization signing material is derived from
`AUDIT_SIGNING_KEY`; verification uses the expected derived public key. Database
triggers reject ordinary update/delete attempts. A PostgreSQL superuser can
still alter schema or disable triggers. Key backup, rotation and revocation are
operator responsibilities.

The local Hardhat mnemonic is public demo material. It must never be used on a
public or value-bearing chain. Passwords and JWT/audit secrets are generated in
ignored `.env`; there is no external identity provider, hardware-backed key
custody or production key rotation. Role checks exist in both backend and
contract, but the Hardhat node is a single local process and provides no
independent consortium consensus.

Chain state is in-memory. Pausing/resuming retains the local state for an outage
demo; recreating the container loses it. Deployment metadata persists, but chain
history does not. Reconciliation detects discrepancies and does not rewrite
history. A digest proves only that bytes match an anchored digest, not that the
source evidence is truthful or that product is safe. A RELEASE decision is a
teaching workflow decision, not a regulatory or clinical guarantee.

## Final acceptance continuation — 2026-11-16

The JWT placeholder was replaced in ignored `.env`; permissions are `0600`.
The setup script's synthetic-file check confirmed it replaces a placeholder
JWT without changing an existing audit key or demo credentials. The five
interactive HTTP logins returned `200` with the expected SHIPPER, CARRIER,
QUALITY, WAREHOUSE and ADMIN roles. `/auth/me` returned `200` for each. Invalid
password, malformed token, expired token, disabled account and a correctly
signed token containing an ungranted role returned `401`; anonymous workflow
requests returned `401` and wrong-role workflow requests returned `403`.
Sanitized result: [`raw/auth-http-acceptance.json`](raw/auth-http-acceptance.json).

A new uniquely prefixed simulated shipment completed the authenticated HTTP
workflow. SHIPPER registration and CARRIER pickup were confirmed first;
seven observed high readings at five-minute intervals generated one
policy-baseline incident through the Receiver-owned `monitor.service`. The
warehouse accepted delivery before QUALITY disposition because that is the
approved state-machine order. QUALITY then recorded RELEASE and WAREHOUSE
released only after confirmation. The final shipment state is `RELEASED`.
All seven business references (registration, pickup, batch anchor, monitor
incident, delivery, disposition and release) matched their chain payload and
shipment hashes. Replayed registration returned the same event ID; replayed
batch returned the original ingest result. Premature delivery and release
returned `409`; incorrect Quality role and CARRIER delivery returned `403`.
Evidence: [`raw/authenticated-http-workflow-acceptance.json`](raw/authenticated-http-workflow-acceptance.json).
An initial, separate cadence probe at 15-minute intervals left a uniquely
prefixed simulated shipment in transit with no incident: each interval exceeded
the detector's 7m30s continuity bound. Its four readings and audit records were
preserved; the successful workflow used seven readings at five-minute intervals.
No policy or detector settings changed. See
[`raw/failed-cadence-exploration.json`](raw/failed-cadence-exploration.json).

Read-only direct `eth_call` probes against the active deployed contract
confirmed `Unauthorized` (`0x82b42900`) for non-SHIPPER registration,
non-CARRIER sensor anchoring, non-MONITOR incident opening, non-QUALITY
disposition and non-WAREHOUSE release. An authorized WAREHOUSE release call
without a confirmed RELEASE state reverted with `InvalidTransition`
(`0xa6532e5d`). No transactions were submitted by these probes. See
[`raw/live-contract-readonly-authorization.json`](raw/live-contract-readonly-authorization.json).

The recovery report is strictly read-only:
[`historical-incident-recovery-plan.md`](historical-incident-recovery-plan.md)
and [`raw/incident-recovery-dry-run.json`](raw/incident-recovery-dry-run.json).
It found 147 failed incident events across 93 shipments; 92 contract shipment
states are `NONE`, while `DEMO-OCEAN-SIM-S11-J0154` is `CREATED` through its
existing confirmed registration `M5-ACCEPTANCE-20261116-register-ocean-154`.
All 147 original incident references are absent on-chain. Each failed entry
has eight preserved attempts, for 1,176 total `UNCERTAIN` attempt rows with no
transaction hashes. The 147 current incidents are all open; 92 have additional
revisions, and there are 1,008 revisions total. No failed record was edited,
retried or marked confirmed. Deterministic review references had zero database
or chain collisions. Any recovery still requires explicit project-owner
approval and Quality review; the contract remains unchanged.

Worker restart fault injection passed without restarting the chain. With the
worker stopped, a fresh registration remained `PENDING` with zero attempts and
no chain reference. After worker restart it confirmed as one event, one attempt
and one `ChainRecord` with matching on-chain payload hash. Evidence:
[`raw/worker-restart-pending.json`](raw/worker-restart-pending.json) and
[`raw/worker-restart-recovery.json`](raw/worker-restart-recovery.json). Starting
the worker caused Compose to re-run the existing one-shot migration/deployment
services; deployment logs report the same contract address was already
deployed. The original chain container remained running; chain/database
container IDs and deploy output are saved in
[`raw/chain-database-container-identity.txt`](raw/chain-database-container-identity.txt)
and [`raw/chain-deploy-idempotency.log`](raw/chain-deploy-idempotency.log).

Seven actual integration latency samples span authenticated HTTP submission,
PostgreSQL outbox, relay and confirmation observation on the existing Hardhat
chain. Request-start to authenticated status observation had p50 **1,083.051
ms** and nearest-rank p95 **1,122.469 ms** (n=7). Relay attempt start to
database-recorded chain confirmation had p50 **46.383 ms** and nearest-rank
p95 **60.555 ms**. The first metric includes the worker's polling interval and
250 ms observation polling; these are local prototype figures, not production
latency. Raw samples and calculation are in
[`raw/authenticated-http-workflow-acceptance.json`](raw/authenticated-http-workflow-acceptance.json)
and [`raw/integration-latency-summary.json`](raw/integration-latency-summary.json).
These are separate from the prior in-process chain and signed-audit
microbenchmarks and do not establish that either ledger approach is faster.

Final checks for this continuation: backend/generator **302 passed** in the
isolated test database; Hardhat **6 passed** on its ephemeral test network; the
live authenticated workflow confirmed; six live contract authorization probes
passed; frontend-proxy smoke **5/5 passed**; worker restart recovery passed;
Docker reports PostgreSQL, chain, backend, frontend and worker healthy. The
reconciliation API reported 147 historical `FAILED`, 12 normal `OK` and two
`DUPLICATE_SUBMISSION_ATTEMPTS` findings (those attempts retain one business
effect each); it found no unknown on-chain reference hashes. Signed audit
verification checked 161 entries and returned valid. Evidence is under
[`raw/`](raw/), including
[`raw/backend-generator-regression-final.log`](raw/backend-generator-regression-final.log)
and [`raw/hardhat-contract-regression-final.log`](raw/hardhat-contract-regression-final.log).
Frontend regression was **24 passed**, and the production build/typecheck
passed; logs are [`raw/frontend-regression-final.log`](raw/frontend-regression-final.log)
and [`raw/frontend-build-final.log`](raw/frontend-build-final.log). The frontend
proxy smoke was **5/5** in [`raw/frontend-proxy-smoke.json`](raw/frontend-proxy-smoke.json).
The approved policy, canonical seed-11 files and frozen M4 registry files had
no Git diff; the model checksum check is recorded in
[`raw/integrity-boundaries.json`](raw/integrity-boundaries.json).

## Final recovery and release-readiness review — 2026-11-16

### Registration ordering

The worker now leaves `SENSOR_BATCH_ANCHORED` and `INCIDENT_OPENED` outbox
entries unclaimed until a `SHIPMENT_REGISTERED` event for the same shipment is
`CONFIRMED`. They remain pending with zero submission attempts while blocked.
This does not grant SHIPPER rights to MONITOR. The M3 importer only imports
observed data; M3 replay and the ocean demo can create operational incidents
before a chain registration exists. That ordering is now safe: the relay
captures the incident event but waits for authenticated SHIPPER registration.
The behavior is covered by an automated same-shipment/multiple-incident test
and an isolated HTTP run. The isolated ocean-demo incident stayed pending with
zero attempts, CARRIER registration was rejected (403), and the authorized
SHIPPER registration and incident anchor each confirmed once. Replaying the
registration returned the same event ID. Evidence:
[`raw/isolated-registration-order-http.json`](raw/isolated-registration-order-http.json),
[`raw/isolated-ocean-demo-before-registration.log`](raw/isolated-ocean-demo-before-registration.log),
and the final backend test log.

### Isolated recovery simulation

All testing used Compose project `coldchain-m5-recovery-isolated`, its own
`coldchain-m5-recovery-isolated_pgdata` and
`coldchain-m5-recovery-isolated_chain-deployments` volumes, and host ports
18545/13000. The resolved configuration had no external volumes or fixed
container names. The active project was never used for writes. The unchanged
canonical fixture was imported into the isolated database; one M3-generated
incident exercised the registration prerequisite. A concurrent duplicate
registration test returned one event ID. With the worker stopped, the event
remained pending with zero attempts; after worker restart it confirmed once
and verified against the isolated chain. See
[`raw/isolated-worker-stop-pending.json`](raw/isolated-worker-stop-pending.json)
and the saved HTTP evidence. The isolated DB retained exactly one demo
`Incident` ID and its original revision after registration/anchoring; see
[`raw/isolated-recovery-simulation-summary.json`](raw/isolated-recovery-simulation-summary.json)
and [`raw/recovery-simulation-matrix.json`](raw/recovery-simulation-matrix.json).

This was not a 147-event backfill simulation. No safe executable recovery
mapping exists today between a new compensating contract reference and the
original operational incident reference required by Quality disposition.
The revised [recovery plan](historical-incident-recovery-plan.md) now keeps all
original event/outbox/attempt rows immutable and defines a separate deterministic
recovery case, actual recovery timestamps, SHIPPER authorization, incident
revision checks, idempotency, and Quality review. Full-inventory recovery is
deferred until the mapping and API are implemented and reviewed. No recovery
event was created for any of the 147 historical failures.

### Fault injection and performance

- Isolated PostgreSQL stop returned HTTP 503 with database unavailable; after
  restarting only that isolated DB, readiness returned HTTP 200 at migration
  0005. The worker probe reported `alive_degraded` and database unavailable
  while it was down. The PostgreSQL volume was retained. Raw log:
  [`raw/isolated-database-outage-recovery.log`](raw/isolated-database-outage-recovery.log).
- A mined-transaction/database-confirmation interruption is covered by a new
  injected-gateway regression: after the simulated commit-window exception,
  the relay reads the existing reference and creates exactly one confirmed
  `ChainRecord` without a second submit.
- An isolated Hardhat pause held an RPC in flight. Unpausing let that same
  attempt confirm once. Isolated network disconnection produced `RETRY` after
  one attempt and worker status `alive_degraded`. The first manual reconnect
  omitted Compose's `chain` DNS alias, so that isolated reference exhausted its
  eight attempts and stayed FAILED without a chain record; this failure is
  preserved in the isolated database. A corrected isolated run restored the
  alias immediately: the same event ID moved from RETRY/attempt 1 to
  CONFIRMED/attempt 2 with a matching chain reference. A fresh registration
  after worker restart also confirmed. Raw evidence:
  [`raw/isolated-network-retry-recovery-corrected.json`](raw/isolated-network-retry-recovery-corrected.json)
  and [`raw/isolated-outbox-fault-summary.json`](raw/isolated-outbox-fault-summary.json).
- Actual isolated relay-attempt-start to database-recorded chain-confirmation
  latency was **41.295, 58.140 and 85.387 ms** (n=3, p50 **58.140 ms**,
  interpolated p95 **82.662 ms**). These are small-sample local integration
  measurements, distinct from the earlier in-process benchmark and not a
  chain-versus-signed-log comparison. Raw timestamps:
  [`raw/isolated-integration-confirmation-latency.json`](raw/isolated-integration-confirmation-latency.json).
- A Hardhat process restart necessarily loses its in-memory state; it cannot
  be a restart-without-state-loss test. The isolated state-loss test confirms
  block 6 with 5,670-byte code and a verified reference became block 0/no code after
  restart. The database retained its `CONFIRMED` row, but reference verification
  returned false (`CHAIN_UNAVAILABLE`) and reconciliation reported
  `CHAIN_QUERY_ERROR`, not `OK`. Restoration is unsupported. Evidence:
  [`raw/isolated-chain-state-loss-test.json`](raw/isolated-chain-state-loss-test.json).
  After redeploying a fresh contract only on the isolated chain, stale database
  confirmations reconciled as `MISSING_ON_CHAIN`, and direct verification stayed
  false; they were not rewritten or treated as verified. See
  [`raw/isolated-chain-loss-reconciliation-after-redeploy.json`](raw/isolated-chain-loss-reconciliation-after-redeploy.json)
  and [`raw/isolated-chain-final-after-recovery.json`](raw/isolated-chain-final-after-recovery.json).

### First-run and packaging readiness

The local environment helpers now generate a blank PostgreSQL password as
well as M5 secrets, replace the legacy JWT placeholder, preserve nonempty
credentials and never print secret values. A temporary-file test passed for
the Python helper; PowerShell execution was not available in this environment.
Migration/seed and contract deployment completed in the isolated first-run
stack. Deployment metadata is persistent and deployment is idempotent, but it
is not a chain-state backup. The macOS/Windows start scripts' broad claim that
all data is kept between runs must be read as PostgreSQL data only: recreating
Hardhat loses every chain action. M10 packaging must provide durable chain
state or an explicitly designed and tested restoration/reconciliation
procedure before claiming restart-safe ledger history. This review does not
implement M10.

### Regression and preservation evidence

Final isolated backend/generator tests: **305 passed**, 6 dependency warnings;
Hardhat contract tests: **6 passed**; frontend: **24 passed**; TypeScript
typecheck and production build passed. Logs are
[`raw/backend-generator-tests-recovery-final.log`](raw/backend-generator-tests-recovery-final.log),
[`raw/isolated-hardhat-tests.log`](raw/isolated-hardhat-tests.log), and
[`raw/frontend-tests-final.log`](raw/frontend-tests-final.log),
[`raw/frontend-typecheck-final.log`](raw/frontend-typecheck-final.log),
[`raw/frontend-build-final.log`](raw/frontend-build-final.log).
The final backend run includes a fail-closed check for invalid local audit
signing-key material, in addition to tamper and signature verification.

The owner-approved policy, canonical seed-11 files and frozen M4 artifacts
were not edited. The active PostgreSQL volume, Hardhat process, deployed
contract and all 147 failed original incident events/1,176 attempts were
preserved. The final read-only inventory was byte-for-byte identical to the
earlier dry run: 147 failed events, 93 shipments, 92 state `NONE`, one state
`CREATED`, 147 open incidents and the same revision distribution. The active
deployment remains chain 31337 at
`0x5FbDB2315678afecb367f032d93F642f64180aa3`, block 1191 with bytecode.
There are 1,177 attempt rows across all 148 `INCIDENT_OPENED` business events:
1,176 attempts belong to the 147 historical failed events (eight each), and
one attempt belongs to a separate already-confirmed M5 HTTP acceptance event.
See [`raw/incident-recovery-dry-run-final.json`](raw/incident-recovery-dry-run-final.json),
[`raw/active-attempt-count-reconciliation.json`](raw/active-attempt-count-reconciliation.json),
and [`raw/active-state-preservation-final.json`](raw/active-state-preservation-final.json).
Docker health for the active environment was only inspected. Faults that can
erase chain state were exercised only against the named isolated project.

**Acceptance recommendation:** accept M5's authenticated workflow, contract
authorization, outbox ordering, retry and audit behavior with the stated local
prototype limitations. Do not authorize historical backfill until the
recovery-reference-to-Quality linkage is implemented and separately approved.
The project is not ready to claim M10 ZIP release resilience until Hardhat
state persistence/recovery and Windows PowerShell setup are verified.

## Remaining acceptance limitations

1. **147 historical incident outbox entries remain FAILED.** No original
   event, attempt, incident or revision was modified. Recovery is design-only;
   the compensating-reference mapping is not yet implemented. The current
   isolated scenario had only one evidence revision; later-revision handling
   was specified but not simulated end to end.
2. Hardhat chain state is in memory; reliable restoration after node restart or
   recreation is unsupported. The destructive state-loss test was isolated.
3. The legacy smoke script remains intentionally unrun because it shuts down
and recreates the stack. Non-destructive frontend proxy and authenticated API
checks passed instead.
4. Performance values are local-stack samples only. A production-network,
concurrent-load or statistically powered blockchain-versus-signed-log
comparison remains unmeasured.
5. Contract tests and live read-only authorization probes are focused checks,
not a complete function × role matrix or an independent production security
audit.
6. Local demo credentials, public Hardhat mnemonic, single-process in-memory
chain and local signing-key storage are unsuitable for production.
7. Windows PowerShell setup/start was inspected but not executed; PowerShell is
   unavailable in this environment. macOS start was not run as a full desktop
   workflow. A role-aware end-user workflow dashboard remains planned for M7.

Do not begin M6 or commit this work before project-owner review.
