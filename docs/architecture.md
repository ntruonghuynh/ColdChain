# Architecture — Cold Chain Monitoring and Excursion Response

| Item | Value |
|---|---|
| Status | Milestone 0 design. **Milestone 1 implemented** the database schema (§5) and the infrastructure (§8). **Milestone 2 implemented** the synthetic data generator, dataset import and ground-truth schema (§3.7, §5, I-9). Everything else is still design |
| Inputs | `docs/requirements-analysis.md` (requirement IDs referenced in brackets, e.g. [FR-24]) |
| Last updated | 2026-11-15 (Milestone 2 review) |

---

## 1. Design principles

These principles come straight from the brief. Every module must respect them.

| # | Principle | Requirements |
|---|---|---|
| P1 | **Recommendation and authorization are separate.** ML scores and LLM drafts are advisory data. Only a human with the QUALITY role can record a disposition, and the release gate checks that disposition, not any model output. | FR-25, BR-15, SC-04 |
| P2 | **Unknown is not safe.** A missing reading creates an UNKNOWN interval. No component may fill it with a "normal" value or count it as in-range time. | FR-11, BR-04, EVAL-13 |
| P3 | **Two clocks.** Every reading keeps `event_at` (when the sensor measured) and `received_at` (when the system got it). Detection runs on `event_at`; latency is measured with `received_at`. | FR-03, BR-06 |
| P4 | **Files stay off chain.** The chain stores IDs, hashes, versions and accepted state changes. Readings, documents and drafts live in PostgreSQL. | BC-11 |
| P5 | **Everything is versioned.** Policy, procedure, feature set, model, prompt and contract versions are stored with every result they produce. | NFR-04 |
| P6 | **Reproducible by default.** Seeds and configuration files drive data generation, training and evaluation. Results are written to disk with the configuration that produced them. | NFR-03 |
| P7 | **Honest labelling.** Simulated values are labelled as simulated; unconfigured features (for example LLM without a key) say so instead of pretending. | NFR-01, NFR-11 |
| P8 | **Enforce on the server.** Role checks live in the API and in the smart contract. The UI only hides buttons for convenience. | NFR-07 |

## 2. System overview

```mermaid
flowchart LR
    subgraph Client["Browser"]
        UI["Frontend<br/>React + TS + Vite + Tailwind<br/>timeline, queue, drafts,<br/>decisions, reconciliation"]
    end

    subgraph Compose["Docker Compose network"]
        API["Backend API<br/>FastAPI<br/>auth, ingestion, policy engine,<br/>incidents, dispositions, release gate"]
        WORKER["Worker<br/>same image as API<br/>outbox relay, chain sync,<br/>re-evaluation jobs"]
        DB[("PostgreSQL<br/>operational data,<br/>outbox, signed audit log")]
        CHAIN["Local blockchain<br/>Hardhat node<br/>ColdChainRegistry contract"]
        DEPLOY["chain-deploy<br/>one-shot: deploy contract,<br/>grant roles, write address"]
    end

    subgraph Libs["Python packages loaded by API and worker"]
        ML["ml/<br/>features, windows,<br/>frozen model registry"]
        LLM["llm/<br/>retrieval, prompts,<br/>provider adapters, guards"]
    end

    SIM["data/generator<br/>seeded journey simulator<br/>(offline CLI)"]
    EXT["LLM provider API<br/>(optional, needs key)"]

    UI -- "HTTPS JSON /api" --> API
    API --> DB
    WORKER --> DB
    API -. "import" .-> ML
    API -. "import" .-> LLM
    LLM -- "HTTPS, only if configured" --> EXT
    WORKER -- "JSON-RPC: transactions" --> CHAIN
    API -- "JSON-RPC: read-only views" --> CHAIN
    DEPLOY --> CHAIN
    SIM -- "CSV.gz + manifest<br/>(import, M2)" --> DB
    SIM -- "training data" --> ML
```

Write path to the chain goes only through the **worker** (transactional outbox, section 7.4). The API reads the chain directly for reconciliation and verification.

## 3. Module responsibilities

### 3.1 Frontend (`frontend/`)

- **Owns:** presentation, client-side routing, role-aware navigation, charts.
- **Does not own:** any business rule. It never decides whether release is allowed; it shows what the API returns.
- **Screens** [FR-30 … FR-36]:
  - Login (demo users per role).
  - Shipment list and shipment detail: temperature timeline with the 2–8 °C band, UNKNOWN gaps shaded and labelled, delayed-arrival markers (`received_at − event_at`), baseline and ML detections overlaid.
  - Excursion queue: open incidents by category (`TEMPERATURE_EXCURSION`, `DATA_GAP`, `SENSOR_FAULT_SUSPECTED`), age and shipment.
  - Incident detail: evidence package, LLM draft with citations, policy version and sensor interval; disposition form (QUALITY only).
  - Decision history: dispositions with actor, time, rationale, evidence references and transaction hash.
  - Reconciliation: each business reference with DB status, outbox status and on-chain status.
  - Partner verification: compute the hash of a record or uploaded file and compare it with the anchored hash.
- A permanent "SIMULATED DATA — teaching policy" banner [NFR-01, NFR-02].

### 3.2 Backend (`backend/`)

FastAPI application. Planned internal layers:

| Layer | Responsibility |
|---|---|
| `api/` | HTTP routes, request/response schemas (Pydantic), auth dependencies. No business logic. |
| `domain/` | Pure business rules with no I/O: validation (BR-07, BR-08), gap detection (BR-03 to BR-05), policy threshold engine (BR-02), incident rules (BR-09), disposition and release rules (BR-10 to BR-12). Fully unit-testable. |
| `services/` | Use cases that combine domain rules with storage: ingest batch, re-evaluate interval, open incident, build evidence package, record disposition, request release, reconcile. |
| `db/` | SQLAlchemy models, Alembic migrations, repositories. |
| `integrations/` | Adapters: `ml_adapter` (calls the `ml` package), `llm_adapter` (calls the `llm` package), `chain_gateway` (web3 client, read views), `audit_log` (signed DB log). |
| `worker/` | Outbox relay to the chain, confirmation tracking, retry with backoff, scheduled reconciliation. |

### 3.3 Database (PostgreSQL)

Single source of operational truth. Holds readings, context, policies, incidents, drafts, decisions, the outbox and the signed audit log. Schema in section 5.

### 3.4 ML pipeline (`ml/`)

Python package plus CLI. Offline: build windows and features, train, validate, freeze, test. Online: the backend loads one frozen model version and calls `predict(windows)`. Details in section 6.

### 3.5 LLM / RAG module (`llm/`)

Python package. Retrieval over the approved corpus, prompt templates, provider adapters, read-only tools with argument validation, output schema validation and citation checks. Details in section 7.3.

### 3.6 Blockchain module (`blockchain/`)

Hardhat project: Solidity contract `ColdChainRegistry`, deployment script, role setup, contract tests. Details in section 7.4.

### 3.7 Data (`data/`) — implemented in Milestone 2

- **Generator** `data/generator/coldchain_sim` (Python 3.12 standard library + PyYAML; runs in the backend image through the `data-tools` Compose service). Layers: 1-minute thermal physics → 5-minute logger observations (bias, drift, noise, spikes) → transmission (15-minute uploads, failed uploads, ocean coverage outage with buffered upload) → ground truth (true out-of-range runs, policy-derived excursions, injected causes, missing data, delays). Seeds are derived per journey with SHA-256, so journeys are independent and output is byte-identical for the same seed and configuration.
- **Output layout**: `observed/` (shipments, uploads, readings, context: what the system receives), `ground_truth/` (journeys, events, per-sample truth), `splits/journey_split.csv` (journey → partition only), `manifest.json` (versions, seed, policy hash, per-file checksums, fingerprint), `statistics.json`, `config.yaml`.
- **Canonical release** `data/release/coldchain-sim-v1.0.0-seed11/` committed (D-05); evaluation-seed manifests in `data/release/seed-manifests/`.
- **Documentation**: `data/dictionary/data-dictionary.md`, `data/dictionary/provenance.md`.
- **Import** `backend/app/dataset/` (`python -m app.dataset import <dir>`): verifies the manifest, checks that the dataset's policy hash equals the stored policy's `content_sha256`, then writes observed rows into the operational tables and labels into schema `ground_truth`, in one transaction, idempotently (re-import writes nothing). It is a dataset loader, not the M3 ingestion path, and runs no detection.

### 3.8 Scripts (`scripts/`)

Start/stop helpers for macOS and Windows, demo scenario runners, evaluation runners, ZIP packaging.

### 3.9 Infrastructure (Docker Compose)

Section 8.

## 4. Integration responsibilities

| # | Interface | Producer → Consumer | Contract | Failure handling |
|---|---|---|---|---|
| I-1 | REST API | Backend → Frontend | OpenAPI schema generated by FastAPI; TypeScript types generated from it | Typed error body `{code, message, details}`; UI shows errors, never fabricates state |
| I-2 | Ingestion API | Simulator / gateway → Backend | `POST /api/ingest/batches` with batch ID, readings, context | Per-record accept/reject report; duplicate batch ID is idempotent [BR-07, BR-13] |
| I-3 | ML predict | Backend → `ml` package | `predict(windows: WindowFrame) -> list[Prediction]`; validated against the frozen `feature_spec.json` | Schema mismatch → error, incident queue still driven by baseline |
| I-4 | LLM draft | Backend → `llm` package | `draft(incident_context) -> DraftResult` (Pydantic schema, section 7.3) | Provider error or not configured → explicit status, no draft text |
| I-5 | LLM provider | `llm` package → external API | Provider adapter interface; Anthropic adapter first | Timeout and retry limits; usage and latency logged even on failure |
| I-6 | Chain write | Worker → Hardhat node | Contract ABI, one call per business event, unique business reference | Outbox retry with backoff; check `isReferenceUsed` before resending [BC-09] |
| I-7 | Chain read | Backend → Hardhat node | Contract view functions and event logs | Chain unreachable → reconciliation shows "chain unavailable", not "missing" |
| I-8 | Contract deploy | chain-deploy → shared volume | `deployment.json` with chain ID, address, ABI hash, role assignments | Backend refuses chain writes if the deployment file is missing or the code hash differs |
| I-9 | Dataset | Simulator → Backend / ML | Versioned files + `manifest.json` (seed, generator and config versions, policy hash, row counts, SHA-256 of stored and uncompressed bytes, dataset fingerprint) | Loader checks manifest hashes before use (implemented M2: `app.dataset.manifest.load_and_verify`); policy hash mismatch or a different dataset under an existing ID is refused |

## 5. Data model

```mermaid
erDiagram
    ORGANIZATION ||--o{ APP_USER : employs
    PRODUCT ||--o{ POLICY : "governed by"
    POLICY ||--o{ SHIPMENT : "applies to"
    SHIPMENT ||--o{ SENSOR_ASSIGNMENT : has
    SENSOR ||--o{ SENSOR_ASSIGNMENT : "assigned via"
    SHIPMENT ||--o{ INGEST_BATCH : receives
    INGEST_BATCH ||--o{ READING : contains
    INGEST_BATCH ||--o{ CONTEXT_READING : contains
    INGEST_BATCH ||--o{ REJECTED_RECORD : "rejects"
    SHIPMENT ||--o{ DATA_GAP : has
    SHIPMENT ||--o{ DETECTION : has
    SHIPMENT ||--o{ INCIDENT : has
    INCIDENT ||--o{ LLM_DRAFT : "explained by"
    SHIPMENT ||--o{ DISPOSITION : "decided by"
    DISPOSITION }o--o{ INCIDENT : closes
    SHIPMENT ||--o{ CUSTODY_EVENT : has
    SHIPMENT ||--o| WAREHOUSE_RELEASE : "released by"
    BUSINESS_EVENT ||--|| OUTBOX_ENTRY : "delivered via"
    BUSINESS_EVENT ||--o| CHAIN_RECORD : "anchored as"
    USER_ROLE ||--o{ DISPOSITION : "authorizes (QUALITY)"

    READING {
        uuid reading_id PK
        text sensor_id
        text shipment_id
        timestamptz event_at
        timestamptz received_at
        numeric temperature_c
        uuid ingest_batch_id FK
    }
    CONTEXT_READING {
        uuid context_id PK
        text shipment_id
        text sensor_id
        timestamptz event_at
        timestamptz received_at
        text door_state
        numeric battery_level_pct
        numeric ambient_temperature_c
    }
    POLICY {
        uuid policy_id PK
        text policy_code
        text policy_version
        text product_id FK
        numeric min_temp_c
        numeric max_temp_c
        int high_excursion_min_duration_min
        int low_excursion_min_duration_min
        int gap_unknown_after_min
        int gap_review_at_min
        text release_authority_role
        text procedure_version
    }
    INCIDENT {
        uuid incident_id PK
        text business_ref UK
        text category
        timestamptz interval_start
        timestamptz interval_end
        text detected_by
        text status
    }
    DISPOSITION {
        uuid disposition_id PK
        text business_ref UK
        text decision
        uuid decided_by_user_id FK
        text decided_by_role FK
        text rationale
        text evidence_sha256
    }
    BUSINESS_EVENT {
        uuid event_id PK
        text business_ref UK
        text event_type
        jsonb payload
        text payload_sha256
    }
    OUTBOX_ENTRY {
        uuid event_id PK
        text status
        int attempts
        timestamptz next_attempt_at
    }
```

**Implemented in Milestone 1** (migration `0001`, models in `backend/app/db/models/`): `organization`, `app_user`, `user_role`, `product`, `policy`, `shipment`, `sensor`, `sensor_assignment`, `ingest_batch`, `reading`, `context_reading`, `rejected_record`, `incident`, `disposition`, `disposition_incident`, `custody_event`, `warehouse_release`, `business_event`, `outbox_entry`, `chain_record`.

Change from the M0 design: the mutable delivery state (`status`, `attempts`, `next_attempt_at`, `last_error`) moved from `business_event` to a separate `outbox_entry` table, so `business_event` stays an immutable fact as required by the append-only rule below.

**Implemented in Milestone 2** (migration `0002`, additive only):

| Object | Purpose |
|---|---|
| `dataset_release` | Provenance of each imported dataset: generator and config versions, seed, split seed, policy (FK) and policy hash, content fingerprint (unique), full manifest (JSONB) [DATA-07] |
| `shipment.source_dataset_id` | Nullable FK to `dataset_release`; NULL for shipments not created by an import |
| schema `ground_truth`, tables `journey` and `event` | Simulator labels (scenario, ambient profile, parameters; labelled intervals with `label_source` and JSONB attributes), apart from the operational tables [DATA-09] |

Only `app/db/models/ground_truth.py`, the model index and the importer may refer to the ground-truth models; `backend/tests/test_ground_truth_boundary.py` enforces this for every other application module (detection, features, API). Both live under the same database role in this prototype; a separate read-only role for detection is not configured (limitation).

**Added in later milestones** (not drawn as implemented): `detection` (source `BASELINE`/`ML`, model version, window, class, score) and `data_gap` (start, end, status `UNKNOWN`) in M3–M4, `llm_draft` (prompt version, provider, model, source IDs, status, tokens, latency, cost) in M6, `audit_log` (hash-chained, signed entries for the comparison in EVAL-03) in M5.

Rules for the schema:

- All timestamps are `timestamptz`, stored in UTC [NFR-05].
- Unit suffixes in column names: `_c`, `_pct`, `_min` [NFR-06].
- Readings unique on `(sensor_id, event_at)` [BR-07]. Business references unique per table and globally across `business_event` [BR-13].
- Readings, decisions and business events are append-only. Corrections are new rows that reference the old ones.
- Enumerations are stored as `VARCHAR` with a `CHECK` constraint (not native PostgreSQL enums) so values can be added with simple migrations.
- `NULL` in a context field means "not reported", never a default value.

Integrity rules enforced **by the database** (tested in `backend/tests/test_data_model_constraints.py`):

| Rule | Mechanism |
|---|---|
| Only the QUALITY role can record a disposition (BC-05, approved 2026-11-14) | Composite FK `disposition(decided_by_user_id, decided_by_role)` → `user_role(user_id, role)` plus `CHECK decided_by_role = 'QUALITY'` |
| A warehouse release needs a RELEASE disposition of the same shipment | Composite FK `warehouse_release(disposition_id, shipment_id, disposition_decision)` → `disposition`, plus `CHECK disposition_decision = 'RELEASE'` |
| A disposition can only reference incidents of its own shipment | Composite FKs from `disposition_incident` with `shipment_id` |
| A shipment's policy belongs to the shipment's product | Composite FK `shipment(policy_id, product_id)` → `policy` |
| One ACTIVE policy per product; release authority is QUALITY; min < max; review gap ≥ unknown gap | Partial unique index and `CHECK` constraints on `policy` |
| Business references unique | `UNIQUE (business_ref)` on every business table |
| Timestamps must carry a timezone | Application type `UTCDateTime` rejects naive datetimes before they reach the database |

Role grants are revoked by setting `user_role.revoked_at`, never deleted, because past dispositions keep a foreign key to the grant they were made under. Checking `revoked_at` at decision time is application logic (M5).
## 6. ML pipeline design

```mermaid
flowchart LR
    G["Seed 11 development dataset<br/>(200 journeys)"] --> S["Journey-level split<br/>train / val / test<br/>grouped by journey,<br/>stratified"]
    S --> W["Windowing on event_at grid<br/>5-min slots, gaps kept as NaN"]
    W --> F["Feature builder<br/>observed data only<br/>feature_spec vN"]
    GT["Ground-truth events<br/>(targets only, D-12)"] --> L["Label builder<br/>(allow-listed)"]
    L --> T
    F --> T["Train candidates<br/>on train"]
    T --> V["Select model and tune thresholds<br/>on validation only"]
    V --> Z["Freeze: model + feature spec<br/>+ preprocessing + hashes"]
    Z --> E["Seed-11 test partition:<br/>one regression check, no tuning"]
    Z --> FE["Final evaluation (M9)<br/>seeds 22, 33, 44, 55, 66"]
    Z --> P["Serve via backend<br/>validated predict API<br/>(no ground truth)"]
```

- **Windows** [ML-01]: resample to a 5-minute grid by `event_at`; missing slots stay `NaN` (no forward fill across a gap, P2). Window length and stride are configuration (starting proposal: 60 minutes, stride 5 minutes). Features use only data at or before the window end [ML-09].
- **Features** (starting set, frozen in `feature_spec.json`): mean, min, max, standard deviation, last value, linear slope, largest step between consecutive readings, minutes above 8 °C, minutes below 2 °C, longest in-range-violating run, missing fraction, longest gap, spike score (largest deviation from rolling median), ambient mean, product-minus-ambient difference, door-open fraction, battery minimum and slope.
- **Window classes** [ML-04]: `NORMAL`, `EXCURSION_GRADUAL` (true product temperature out of range, sustained), `SENSOR_SPIKE`, `SENSOR_BIAS`, `INSUFFICIENT_DATA`. Exact label rules are written into the data dictionary in M2.
- **Models** [ML-02, ML-05]:
  - B0 — policy threshold rule (the brief's baseline; not ML).
  - B1 — ML baseline: logistic regression on the same features.
  - C1 — candidate: gradient-boosted trees (`HistGradientBoostingClassifier`, handles `NaN`).
  - C2 — optional: `IsolationForest` anomaly score as an extra spike/bias signal.
  The final candidate is chosen on validation results only [ML-08].
- **Event aggregation**: consecutive positive windows form a predicted event; the minimum run length is tuned on validation [EVAL-11].
- **Training-time labels vs inference-time features** [ML-09, D-12, approved 2026-11-15]: *labels* (targets) come from the simulator's ground-truth events. They are read by one explicitly allow-listed label-builder module, only during training and evaluation, and only for the journeys of the partition in use. *Features* are computed only from observed data (`reading`, `context_reading`, or the `observed/` files), identically in training and in inference. Inference, operational APIs and the frontend never read ground truth. `backend/tests/test_ground_truth_boundary.py` enforces this. M4 adds the label builder to its allow-list and the feature and predict modules stay forbidden.
- **Seeds and partitions** [D-13, approved 2026-11-15]: seed 11 is used for development, training (train partition), model selection and threshold tuning (validation partition) and internal regression checks (test partition). The seed-11 test partition is never used for iterative tuning. Seeds 22, 33, 44, 55, 66 are final evaluation seeds. They do not influence feature selection, model selection, preprocessing or thresholds, and they are evaluated only after the model and preprocessing are frozen.
- **Freeze** [ML-06]: `ml/registry/<model_version>/` holds the model file, `feature_spec.json`, preprocessing config, training-data manifest hash, validation metrics, model card and a SHA-256 of each file (D-05: committed, small, versioned). The freeze record also stores the seed assignments (development seed and split seed; final evaluation seeds) and the evaluation-protocol version. Final evaluation seeds are opened only after this record exists.
- **Serving** [ML-07]: backend loads one model version (`ML_MODEL_VERSION`), validates feature frames against the spec, stores every prediction with its model version. Predictions open incidents for review only [BR-15].

## 7. Key flows

### 7.1 Ocean coverage gap (DEMO-01)

```mermaid
sequenceDiagram
    autonumber
    participant L as Data logger (simulated)
    participant API as Backend API
    participant DB as PostgreSQL
    participant W as Worker
    participant C as Chain
    participant Q as Quality officer
    participant WH as Warehouse operator

    Note over L: Coverage lost. Logger keeps measuring and buffers.
    API->>DB: Gap detector: no readings > 15 min → DATA_GAP (UNKNOWN)
    API->>DB: Gap ≥ 30 min → open DATA_GAP incident
    Note over L: Coverage restored
    L->>API: Upload buffered batch (original event_at, new received_at)
    API->>DB: Validate, store readings, keep both timestamps
    API->>DB: Re-evaluate interval: baseline + ML → TEMPERATURE_EXCURSION
    API->>DB: business_event(batch hash), business_event(incident) in outbox
    W->>C: anchorSensorBatch(ref, hash) / openIncident(ref, ...)
    C-->>W: confirmed
    WH->>API: Request warehouse release
    API-->>WH: 409 Blocked: no RELEASE disposition on chain
    Q->>API: Review evidence + LLM draft, record QUARANTINE or RELEASE
    API->>DB: disposition + outbox event
    W->>C: recordDisposition(ref, decision) [QUALITY account]
    C-->>W: confirmed
    WH->>API: Request warehouse release
    API-->>WH: Allowed only if decision = RELEASE and confirmed
```

### 7.2 Disposition and release state machine

```mermaid
stateDiagram-v2
    [*] --> CREATED: shipper registers shipment
    CREATED --> IN_TRANSIT: carrier accepts custody
    IN_TRANSIT --> DELIVERED: receiver accepts custody
    DELIVERED --> AWAITING_DISPOSITION: arrival checks complete
    IN_TRANSIT --> IN_TRANSIT: incidents may open any time
    AWAITING_DISPOSITION --> RELEASE_APPROVED: QUALITY records RELEASE
    AWAITING_DISPOSITION --> QUARANTINED: QUALITY records QUARANTINE
    RELEASE_APPROVED --> RELEASED: WAREHOUSE executes release
    QUARANTINED --> [*]
    RELEASED --> [*]
```

Guards (enforced in `domain/` and again in the contract):

- `RELEASE_APPROVED` requires the QUALITY role and a disposition that references every open incident [BR-10].
- `RELEASED` requires a confirmed on-chain `RELEASE` disposition [BR-11]. No path leads from an ML score or LLM draft to any of these states [BR-15].
- Any other transition (for example `CREATED → RELEASED`) is rejected as invalid [EVAL-08].

### 7.3 LLM / RAG design

```mermaid
flowchart TB
    INC["Incident context<br/>(structured system results)"] --> R
    Q["Retrieval query"] --> R["Retriever<br/>TF-IDF/BM25 over approved corpus<br/>filtered by procedure_version"]
    R --> CTX["Evidence bundle<br/>each item has a source_id"]
    UNT["Untrusted documents<br/>(e.g. carrier notes)<br/>marked as data"] --> CTX
    CTX --> P["Prompt template vN<br/>(versioned file + hash)"]
    P --> PROV["Provider adapter<br/>Anthropic first; 'disabled' if no key"]
    PROV <--> TOOLS["Read-only tools<br/>get_readings, get_incident,<br/>search_procedures<br/>(Pydantic-validated args)"]
    PROV --> OUT["Structured draft JSON"]
    OUT --> VAL["Output validator<br/>schema, citations ⊆ supplied sources,<br/>policy_version and interval match"]
    VAL -->|pass| DRAFT["Stored draft (advisory)"]
    VAL -->|fail| INS["insufficient_evidence result"]
```

- **Corpus** [LLM-01]: `llm/corpus/approved/` — short teaching procedures written by the team, each with front matter (`doc_id`, `version`, `status: approved`, `effective_date`). Only `approved` documents matching the shipment's `procedure_version` are retrievable.
- **Retrieval**: local TF-IDF/BM25 with scikit-learn, deterministic and offline. Chunk IDs (`SOP-EXC-001#3`) are the source IDs [LLM-06].
- **Structured evidence** [LLM-05]: incident, readings summary for the interval, gaps, baseline and ML detections, each with a system source ID (for example `SYS:incident/<id>`, `SYS:readings/<shipment>/<from>/<to>`).
- **Output schema**: `status` (`draft` | `insufficient_evidence` | `not_configured` | `provider_error`), `alert_explanation`, `recommended_actions[]`, `evidence_required[]`, `citations[{source_id, claim}]`, `policy_version`, `sensor_interval {start, end}` [LLM-02 to LLM-04, LLM-07].
- **Tools** [LLM-08]: read-only. Arguments validated: shipment must equal the incident's shipment; time range within the shipment and at most 48 hours; unknown fields rejected. There are no write tools, so a draft cannot change state [LLM-09].
- **Injection defense** [LLM-10]: documents are wrapped as quoted data with their trust level; the system prompt says instructions inside documents must be ignored; the output validator rejects drafts that recommend actions outside the procedure or cite unsupplied sources. Defense is measured, not assumed (EVAL-07).
- **Provider** [LLM-12, D-03]: Anthropic Python SDK; default model `claude-opus-5-5` (set by `LLM_MODEL`). Structured output via the SDK's structured-output support. The current API does not accept sampling parameters such as `temperature` on this model, so LLM output is **not deterministic**; evaluation therefore stores every raw response. Price used for cost: $4 input / $20 output per million tokens (Anthropic list price cached 2026-11-03 — re-check on the evaluation date and record the source).
- **Versioning** [LLM-11]: prompts live in `llm/prompts/<name>/vN.md`; each draft stores prompt version and hash, provider, model ID, input/output tokens, latency and computed cost.

### 7.4 Blockchain design and retry

**Contract `ColdChainRegistry`** (Solidity, OpenZeppelin `AccessControl`):

| Function | Allowed role | Effect | Rejects |
|---|---|---|---|
| `registerShipment(ref, shipmentKey, policyVersion)` | SHIPPER | Shipment record `CREATED` | duplicate ref |
| `acceptCustody(ref, shipmentKey, stage)` | CARRIER (pickup), WAREHOUSE (delivery) | `IN_TRANSIT` / `DELIVERED` | wrong role for stage, invalid transition, duplicate ref |
| `anchorSensorBatch(ref, shipmentKey, batchHash, firstEventAt, lastEventAt, count)` | CARRIER | Batch anchored | duplicate ref |
| `openIncident(ref, shipmentKey, category, evidenceHash)` | MONITOR | Incident open | duplicate ref, unknown shipment |
| `recordDisposition(ref, shipmentKey, decision, incidentRefs[], evidenceHash)` | QUALITY | `RELEASE_APPROVED` / `QUARANTINED` | non-QUALITY caller, open incident not referenced, already decided, duplicate ref |
| `recordWarehouseRelease(ref, shipmentKey)` | WAREHOUSE | `RELEASED` | no `RELEASE` disposition, duplicate ref |
| `isReferenceUsed(ref)` (view) | anyone | — | — |

Business references are `bytes32` hashes of the DB business reference string. `shipmentKey` is a hash of the shipment ID, so no business data is stored in clear [BC-11].

**Organizations and roles** [BC-07]:

| Organization | Roles | Chain account (local dev) |
|---|---|---|
| Shipper | SHIPPER | Hardhat dev account #1 |
| Carrier | CARRIER | Hardhat dev account #2 |
| Receiver | QUALITY, WAREHOUSE, MONITOR (service) | Hardhat dev accounts #3, #4, #5 |
| Platform (deployer) | DEFAULT_ADMIN (grants roles only, no business actions) | Hardhat dev account #0 |

Hardhat dev accounts come from Hardhat's public test mnemonic. They are only for the local chain and must never hold real value.

**Retry without duplicates** [BC-09, DEMO-04]:

```mermaid
sequenceDiagram
    autonumber
    participant API as Backend
    participant DB as Outbox (PostgreSQL)
    participant W as Worker
    participant C as Chain
    API->>DB: INSERT business_event(ref UNIQUE, PENDING) in same transaction as the domain change
    W->>DB: Claim PENDING event
    W->>C: send tx(ref)
    C--xW: RPC unavailable (outage)
    W->>DB: attempts+1, status RETRY, next_try_at = backoff
    Note over C: Chain becomes available again
    W->>C: isReferenceUsed(ref)?
    alt already on chain (earlier tx did land)
        C-->>W: true
        W->>DB: mark CONFIRMED, link existing tx
    else not on chain
        W->>C: send tx(ref)
        C-->>W: receipt
        W->>DB: mark CONFIRMED
    end
    Note over C: Contract also reverts a second write of ref
```

Outage simulation for tests uses `docker compose pause chain` / `unpause`, which keeps the in-memory chain state (a restarted Hardhat node would lose it; see section 11).

**Comparison system** [EVAL-03]: a signed, hash-chained `audit_log` table in PostgreSQL. Each entry stores the previous entry's hash and an Ed25519 signature from the acting organization's key; the API applies the same role rules. Evaluation runs the same scenarios against both and compares coordination value and overhead.

## 8. Infrastructure

Compose services (`docker-compose.yml`). Services marked M1 exist now; the others are added by their milestone.

| Service | Image / build | Host port | Health / completion | Notes |
|---|---|---|---|---|
| `db` (M1) | `postgres:16-alpine` | none | `pg_isready` | Named volume `coldchain_pgdata`; session timezone UTC |
| `migrate` (M1) | `backend/` image, target `runtime` | none | exits 0 | One-shot: `alembic upgrade head && python -m app.seed` (idempotent reference data) |
| `backend` (M1) | same image as `migrate` | none | `GET /api/health` (DB reachable and schema at head) | Starts only after `migrate` completed successfully |
| `frontend` (M1) | multi-stage: `node:24-alpine` build → `nginx:1.28-alpine` | `127.0.0.1:3000` → 8080 | `GET /healthz` | Serves the SPA; reverse-proxies `/api/` to `backend:8000` |
| `backend-tests` (M1, profile `test`) | `backend/` image, target `test` | none | pytest exit code | Uses separate `*_test` databases. Since M2 it mounts the repository read-only at `/workspace` and also runs `data/generator/tests` |
| `data-tools` (M2, profile `tools`) | same image as `backend` | none | exit code | One-shot dataset tools: `python -m coldchain_sim ...` (generate, verify) and `python -m app.dataset ...` (verify, import, status). Mounts the repository at `/workspace` |
| `chain` (M5) | built from `blockchain/` (Node LTS + Hardhat) | 8545 | — | In-memory chain; reset together with `db` |
| `chain-deploy` (M5) | same as `chain` | none | — | One-shot: deploy, grant roles, write `deployment.json` |
| `worker` (M5) | same image as `backend` | none | — | Outbox relay and scheduled jobs |

- **Startup order:** `db` healthy → `migrate` completed successfully → `backend` healthy → `frontend`. `docker compose up -d --build --wait` returns only when all are healthy (verified in M1).
- **One port:** only the frontend is published, on `127.0.0.1:${FRONTEND_PORT:-3000}` (`FRONTEND_BIND_ADDRESS` can widen it). The browser calls `/api/...` on the same origin, so no backend hostname or port is built into the frontend.
- **Reverse proxy:** nginx resolves `backend` at request time through Docker's DNS (`resolver 127.0.0.11`), so the UI still loads when the backend is down and the proxy answers with a JSON error `{"error": {"code": "api_unreachable", ...}}` (HTTP 502). Backend responses, including its own 503 health report, pass through unchanged. nginx forwards or generates `X-Request-ID`.
- **API conventions:** every route is under `/api`; success bodies are `{"data": ..., "meta": ...}`, errors are `{"error": {"code", "message", "details", "request_id"}}`. OpenAPI at `/api/openapi.json`, Swagger UI at `/api/docs`.
- **Start/stop for non-technical users:** `start.command` / `stop.command` (macOS) and `start.bat` / `stop.bat` (Windows) at the repository root. They check Docker, create `.env` if missing, refuse to start if another program holds the port, run `up --wait`, verify `/api/health` through the proxy, and never delete data (`down` without `-v`).
- **Line endings:** `.sh`, `.command`, `.py` and `Dockerfile` are LF; `.bat` is CRLF (`.gitattributes`).
- **Configuration** comes from `.env` (copied from `.env.example`). Compose refuses to start without `POSTGRES_PASSWORD`; no secret is written into `docker-compose.yml`.

## 9. Security model

| Concern | Control |
|---|---|
| Authentication | Demo users per role, password login, JWT signed with `JWT_SECRET` from `.env` |
| Authorization | Role check in API dependencies **and** in the contract (`onlyRole`) [NFR-07] |
| Signing keys | Backend holds one local dev key per organization (simplification; see limitations) |
| Prompt injection | Untrusted text wrapped as data, read-only tools, output validation [LLM-10] |
| Tampering | Batch and evidence hashes anchored; partner verification recomputes and compares [BC-13] |
| Secrets | `.env` is git-ignored; `.env.example` holds only placeholders [NFR-08] |

## 10. Evaluation architecture

| Configuration | Detection | Response | Record keeping |
|---|---|---|---|
| E0 Baseline | Policy threshold rule (B0) | Manual (no draft) | DB only |
| E1 ML only | Frozen ML model (C1) + B0 shown alongside | Manual | DB only |
| E2 ML + LLM | as E1 | LLM draft + evidence list | DB only |
| E3 Complete | as E1 | as E2 | DB + blockchain |
| E3-alt Comparator | as E1 | as E2 | DB + signed audit log |

Runners in `scripts/eval/` read a run config (seeds, model version, prompt version, contract version), write raw per-case results (CSV/JSONL) and a summary to `docs/evaluation/runs/<run_id>/`, together with the exact config and git commit. Uncertainty: per-seed values plus mean ± standard deviation across ≥5 seeds (the reserved evaluation seeds 22, 33, 44, 55, 66; seed 11 is the development dataset, A-13), and journey-level bootstrap 95% intervals where the sample allows [EVAL-09, EVAL-10].

## 11. Known limitations (by design)

1. **Custodial keys.** In the prototype the backend signs for every organization. A real consortium would give each organization its own node and keys. Blockchain results show the mechanism, not real decentralization.
2. **Ephemeral local chain.** The Hardhat node keeps state in memory. Restarting it without also resetting the database breaks consistency; the reconciliation view will show this. Start/stop scripts reset both together; outages are simulated by pausing, not restarting.
3. **Synthetic data.** Results describe the simulator's behaviour. 200 journeys per seed is a teaching scale, not statistical proof (as the brief says).
4. **Non-deterministic LLM.** Drafts vary between runs; evaluation stores raw outputs and reports variation rather than one "true" score.
5. **Teaching policy.** Limits, durations and procedures are invented for teaching and are not clinical or regulatory guidance.
