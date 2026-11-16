# Historical incident anchor recovery plan — owner review required

**Status: design approved for isolated testing only; active recovery is not
authorized.** The read-only inventory is complete. The 147 original failed
events and all related incident/revision/attempt history remain untouched.
This document does not authorize any live registration, replay, retry,
backfill, chain reset or database change.

## Read-only inventory

The active stack was inspected on 2026-11-16. The read-only inventory is
[`raw/incident-recovery-dry-run.json`](raw/incident-recovery-dry-run.json),
produced by
[`scripts/eval/m5_historical_incident_recovery_dry_run.py`](../../../scripts/eval/m5_historical_incident_recovery_dry_run.py).
The script has no write path and checks the current PostgreSQL rows against the
active chain contract.

| Finding | Count / state |
|---|---:|
| Failed `INCIDENT_OPENED` business events | 147 |
| Distinct shipments | 93 |
| Shipments with on-chain state `NONE` | 92 |
| Shipments already `CREATED` on-chain | 1 |
| Original incident refs already present on-chain | 0 |
| Original incident payload or shipment hash mismatches | 0 |
| Failed events with a PostgreSQL `ChainRecord` | 0 |
| Failed outbox entries with 8 preserved attempts | 147 / 147 |
| Historical attempt rows, all `UNCERTAIN` | 1,176 |
| Attempts with recorded transaction hash | 0 |
| Current incidents still `OPEN` | 147 |
| Current incidents with one or more revisions | 147; 1,008 revisions total |
| Incidents with more than the original revision | 92 |
| Deterministic proposed recovery reference collisions | 0 |

The already registered shipment is
`DEMO-OCEAN-SIM-S11-J0154`. Its confirmed registration is
`M5-ACCEPTANCE-20261116-register-ocean-154`, and its on-chain state is
`CREATED`. It still has one incident among the 147 whose reference is absent
on-chain. No other shipment in this inventory is registered on-chain.

The 147 operational `Incident` records already exist; the failed business
events each point to an incident ID, the original M3 evidence revision ID,
business reference, payload hash and event time. All are currently open, but
92 have additional revisions after the revision captured in their original
event payload. The current counts are 106 temperature excursions and 41 data
gaps. The per-event inventory contains event IDs, original and current
incident references, payload hashes, original event timestamps, revision IDs,
outbox attempt timestamps/outcomes and each shipment's current contract state.

The confirmed cause is the contract transition order: `openIncident` rejects
state `NONE` with `InvalidTransition`. The earlier RPC symptom was recorded as
uncertain because the old relay did not classify that revert. The old
attempts have no transaction hashes, and none of the 147 original incident
references exists on-chain. The detailed original RPC diagnosis remains in
[`raw/live-contract-rpc-diagnostics.json`](raw/live-contract-rpc-diagnostics.json)
and [`raw/historical-chain-rpc-errors.log`](raw/historical-chain-rpc-errors.log).

## Safe recovery design (not executable against the active environment)

1. Freeze the read-only inventory and re-run it immediately before any future
   separately authorized recovery. Stop on changes to registration state,
   incident status or revisions, event identity, payload hashes, or reference
   collision results.
2. Obtain specific authorization for each retrospective registration. The
   existing assigned SHIPPER identity must authorize it. For each of the 92
   shipments at `NONE`, create at most one registration using the deterministic
   `M5-RECOVERY-REG-<24 hex>` reference derived from the shipment ID. Do not
   register the one shipment already in `CREATED` again. Registration time and
   block time must be actual execution times, never historical shipment time.
3. Wait until registration has a confirmed matching chain record, shipment
   key and policy hash before anchoring any incident evidence for that
   shipment. MONITOR remains an incident-evidence identity; it is never given
   SHIPPER permission.
4. Do **not** retry or change any of the 147 original failed outbox rows. A
   recovery implementation must create a separate append-only recovery case
   and a new deterministic `M5-RECOVERY-INC-<24 hex>` business reference
   derived from the original event ID. It must include a unique mapping to the
   original event ID, original incident ID and business reference, original
   payload hash and evidence-revision ID. The new event's `occurred_at`, its
   signed audit creation time and the blockchain block time must describe the
   actual recovery action; the original historical time remains separately
   recorded as source evidence, never represented as a chain timestamp.
5. Create no new operational `Incident` row. Repeated requests with the same
   recovery reference and identical source hashes must return the existing
   recovery case; conflicting content must fail. Enforce uniqueness in both
   the database and contract-facing reference mapping.
6. Preserve the original event and its eight failed attempts per event as
   read-only history. Append recovery attempts only to the new recovery event.
   Reconcile the original and recovery records independently; never relabel an
   original failure as a success.
7. Before any quality disposition, compare current incident status and latest
   M3 revision with the source revision captured by the original event. The 92
   incidents with later revisions require authorized Quality review of current
   evidence. A closed, merged or otherwise changed incident must be held for
   a separately authorized review; recovery must not reopen or alter it.
   Release or quarantine remains solely a Quality Officer decision. Recovery
   evidence cannot imply safety or authorize warehouse release.
8. Reconcile after each shipment and at completion: registration state,
   original-event hashes and failure status, recovery-case uniqueness,
   contract reference/payload/shipment hashes, Quality links, and incident
   counts. Confirm that no operational incident ID or `Incident` row was
   duplicated.

## Deterministic IDs and duplicate prevention

The dry-run proposes registration references as
`M5-RECOVERY-REG-` plus the first 24 lowercase hex characters of
`SHA-256(shipment_id)`. It proposes owner-review case IDs as
`M5-RECOVERY-INC-` plus the first 24 lowercase hex characters of
`SHA-256(original event_id)`. The latter are **review/case IDs only**; they
must not be submitted as contract business references. All proposed IDs had
zero PostgreSQL or chain collisions at the time of the dry run.

The original incident `business_ref` and event ID remain the operational
source identity. The deterministic `M5-RECOVERY-INC-...` reference belongs to
a distinct recovery case and must not overwrite the source identity. The
current M5 Quality workflow binds dispositions to the original incident
business references, while the current contract accepts unique incident
references. Therefore a recovery-case-to-contract-anchor mapping and a
Quality-verifiable link are required before this design can be executed. The
current implementation has no recovery-case model, mapping, endpoint or
contract workflow for that link. **No live or isolated code path is approved
to backfill these historical events yet.** Implement and review that mapping
before requesting separate approval for a live backfill.

## Preservation, reconciliation and rollback limits

The active inventory was read only. This review changed no failed outbox
state, attempt history, business event, incident, revision, contract record or
shipment registration. There is no rollback for a confirmed transaction:
chain entries are immutable. A wrong registration or incident anchor can only
be countered by a later, separately authorized business action; it cannot be
erased. Reconciliation reports discrepancies but must not repair them by
rewriting historical records.

The active Hardhat chain is in-memory. Recreating it would erase its full
history, including existing registrations. Do not use `docker compose down`,
remove volumes, rerun deployment against a fresh node, or reset the chain as a
recovery shortcut. The existing deployment at
`0x5FbDB2315678afecb367f032d93F642f64180aa3` must be preserved.

## Authorization boundary and test status

The owner approved design and isolated testing only. Live retrospective
registration and recovery-event creation remain prohibited until the mapping
implementation described above is reviewed and separately approved. The
isolated test reproduced the unregistered-shipment ordering case with one
M3-generated incident: the relay left the incident event pending with zero
attempts, a CARRIER registration request received 403, SHIPPER registration
was confirmed, and then the incident anchor confirmed once. Parallel duplicate
registration requests returned one event ID; a worker stop/restart preserved a
pending event and later confirmed it once. This is a workflow-ordering test,
not a backfill of the 147-event inventory or a test of the missing recovery
mapping. Full 147-event simulation was not run because no recovery-case
implementation exists to safely model its required source-to-chain linkage.

The active 147 failed outbox rows and all 1,176 original attempt rows remain
failed/preserved and are not eligible for live retries under this plan.
