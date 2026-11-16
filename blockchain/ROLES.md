# Local registry roles

The contract assigns one local development account to each role. Each private
key stays inside the backend or deployment container; the browser receives only
short-lived application bearer tokens.

| Role | Organization | Contract actions | Backend actions |
|---|---|---|---|
| ADMIN | Platform | Grant approved contract roles | Reconciliation, audit verification |
| SHIPPER | Shipper | Register shipment | Register its shipment; read ledger |
| CARRIER | Carrier | Accept pickup custody; anchor sensor-batch hashes | Submit telemetry for assigned shipments |
| MONITOR | Receiver | Open incidents | No interactive login; monitor service identity only |
| QUALITY | Receiver | Record RELEASE or QUARANTINE disposition | Record/review a disposition and evidence reassessment |
| WAREHOUSE | Receiver | Accept delivery custody; execute an approved release | Accept delivery custody; request release after confirmed RELEASE |

## Authorization invariants

- Only QUALITY may record disposition. The API checks active database grants and
  receiver-organization membership; the contract independently checks its
  QUALITY role.
- WAREHOUSE cannot release without the contract's confirmed RELEASE state and
  the API's corresponding confirmed database record.
- MONITOR is a service principal associated with the receiver organization
  (owner decision for D-08, 2026-11-16). It has no password and cannot log in.
- ML predictions and any future generated text are advisory and have no signing
  key or workflow permission.
- The local mnemonic is public Hardhat demo material, never a production secret.
  Replace it and the local key custody design before any non-demo deployment.

Demo human users are created by the seed loader. Set separate passwords in the
ignored `.env` using `scripts/setup_local_env.py`; no credentials are committed.
