# M5 blockchain and workflow contract

## Scope and trust boundary

PostgreSQL remains authoritative for operational rows. A transactional
`business_event` plus `outbox_entry` is written in the same transaction; the
worker relays it to the local Hardhat registry. The chain stores only hashed
business references, shipment identifiers, payload hashes, action types, actor
addresses and block/time metadata. It stores no readings, private customer
information or documents. A hash proves that a later supplied byte sequence
matches an anchored digest; it does not prove sensor calibration, truthfulness,
temperature safety, identity outside the local key setup, or regulatory
compliance.

The backend authenticates local demo users with PBKDF2 password hashes and
short-lived HS256 bearer tokens. Each request rechecks current user activity and
database role grants. The outbox worker derives the role-specific local account
from the configured Hardhat development mnemonic, verifies its address against
the seeded organization/role mapping, and signs transactions server-side. The
frontend and public API never receive those keys.

## Role and transition rules

See [`../../blockchain/ROLES.md`](../../blockchain/ROLES.md). The workflow is:

| Current state | Command | Required role | Next state |
|---|---|---|---|
| NONE | Register shipment | SHIPPER | CREATED |
| CREATED | Pickup custody acceptance | CARRIER | IN_TRANSIT |
| IN_TRANSIT | Delivery custody acceptance | WAREHOUSE at receiver | DELIVERED |
| Any registered, unreleased shipment | Open incident | MONITOR | incident count increases; a prior nonterminal decision is reopened for review |
| DELIVERED | Quality RELEASE disposition | QUALITY at receiver | RELEASE_APPROVED |
| DELIVERED | Quality QUARANTINE disposition | QUALITY at receiver | QUARANTINED |
| RELEASE_APPROVED | Warehouse release | WAREHOUSE at receiver | RELEASED |

Every command has a globally unique business reference. The API returns the
original result for same-reference/same-payload replay and rejects conflicts;
the contract rejects any reused reference, preventing a second chain effect.
Disposition payloads bind policy hash, all incident references, latest M3
evidence revision identifiers and evidence/rationale hashes. A new incident or
late-evidence reassessment does not rewrite a prior disposition. An authorized
Quality Officer must reassess before a new disposition; an executed warehouse
release is irreversible in the prototype.

## Outbox, confirmation, recovery

Outbox events are inserted with their business records in one PostgreSQL
transaction. The relay claims pending work with `FOR UPDATE SKIP LOCKED`, records
each attempt, retries with bounded exponential backoff and leaves exhausted
events visibly FAILED. After a submission timeout it queries the deterministic
reference before retrying; it marks an event CONFIRMED only after observing the
required chain confirmations and matching the emitted reference/payload.
Shipment state changes tied to custody or disposition are applied only after
confirmation. Attempt rows cannot be deleted; their outcome fields advance from
STARTED to a terminal or uncertain status so an interrupted attempt remains
visible. `SENSOR_BATCH_ANCHORED` and `INCIDENT_OPENED` entries are not claimed
until a `SHIPMENT_REGISTERED` event for the same shipment is CONFIRMED. A blocked
entry remains PENDING with zero attempts; it is not repeatedly submitted and
MONITOR is never granted SHIPPER authority. Reconciliation is read-only and reports pending/failed events,
missing records, unknown chain references, payload or shipment mismatches and
multiple submission attempts.

Hardhat state is in-memory and resets when its container is recreated. The
Compose deployment volume retains deployment metadata, not chain state. A
restart that loses chain state therefore creates an explicit reconciliation
gap; there is no automatic historical rewrite or silent re-anchoring. For a
demo outage, pause/resume the chain container to retain its state. Durable chain
storage and disaster recovery are outside this local prototype.

The local setup helpers generate missing database and M5 secrets without
printing values, and replace the legacy JWT placeholder while preserving valid
existing secrets. PostgreSQL's named volume persists across Compose `down`; the
Hardhat process does not. Do not describe the whole ledger as persistent across
container recreation. A future distributable release must add and verify a
chain-state persistence/recovery strategy.

## Signed database audit comparison

`audit_log` is append-only and stores a deterministic record hash, previous
entry hash, Ed25519 signature and verification public key. Signing keys are
derived per organization from `AUDIT_SIGNING_KEY` using HMAC-SHA256. Verification
checks the canonical record hash, previous-hash chain, signature, sequence and
expected public key. Database triggers reject updates/deletes. This baseline
shares the application's administrator access boundary; a database superuser
can still disable triggers or destroy the table. Signing-key backup/rotation is
an operator responsibility.

Blockchain offers independently replicated ordering within the running chain
and role checks at the contract boundary; this local single-node chain is not a
distributed trust network. The signed DB log adds cryptographic tamper evidence
without a chain node. The M5 report records local performance samples; their
different execution paths make them illustrative, not a fair speed comparison.

## API surface

- `POST /api/auth/login`, `GET /api/auth/me`
- `POST /api/workflow/shipments/{id}/register`
- `POST /api/workflow/shipments/{id}/custody`
- `POST /api/workflow/shipments/{id}/disposition`
- `POST /api/workflow/shipments/{id}/release`
- `POST /api/workflow/shipments/{id}/reassessments/{id}/review`
- `GET /api/ledger/transactions`, `/api/ledger/reconciliation`,
  `/api/ledger/verify/{business_ref}`, `/api/ledger/audit`, `/api/ledger/audit/verify`
- `GET /api/health/ledger`

All workflow commands require bearer auth and return pending confirmation
status. Ledger/reconciliation/audit reads are role-gated; reconciliation and
audit verification are administrator-only. See OpenAPI at `/api/docs`.
