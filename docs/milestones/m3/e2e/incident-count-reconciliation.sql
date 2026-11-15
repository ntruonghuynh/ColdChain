-- Read-only count reconciliation for the latest M3 acceptance review.
-- Canonical replay covered the 200 seed-11 shipments; dashboard counts include
-- every current local shipment, including the separate ocean demonstration.

SELECT
    CASE
        WHEN s.source_dataset_id = 'coldchain-sim-v1.0.0-seed11' THEN 'canonical_seed11'
        WHEN s.shipment_id = 'DEMO-OCEAN-SIM-S11-J0154' THEN 'ocean_demo'
        ELSE 'other_local'
    END AS scope,
    i.category,
    i.status,
    count(*) AS incident_rows,
    count(DISTINCT i.incident_id) AS distinct_incidents
FROM incident i
JOIN shipment s USING (shipment_id)
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3;

SELECT
    CASE
        WHEN s.source_dataset_id = 'coldchain-sim-v1.0.0-seed11' THEN 'canonical_seed11'
        WHEN s.shipment_id = 'DEMO-OCEAN-SIM-S11-J0154' THEN 'ocean_demo'
        ELSE 'other_local'
    END AS scope,
    count(DISTINCT i.incident_id) AS incident_count,
    count(r.incident_revision_id) AS revision_count
FROM incident i
JOIN shipment s USING (shipment_id)
LEFT JOIN incident_revision r USING (incident_id)
GROUP BY 1
ORDER BY 1;

-- The telemetry view itself enforces causal receipt-time visibility and gives
-- status/incident counts for each selected cutoff:
-- GET /api/shipments/SIM-S11-J0154/telemetry?as_of=2026-10-19T15:57:03Z
-- GET /api/shipments/SIM-S11-J0154/telemetry?as_of=2026-10-19T23:02:00Z
