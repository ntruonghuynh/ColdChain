# frontend/

**Status: not implemented.** Shell in Milestone 1, full dashboard in Milestone 7.

Stack: React + TypeScript (strict) + Vite + Tailwind CSS, served by nginx in Docker.

Planned views (see `docs/architecture.md` §3.1): shipments, shipment detail with temperature timeline and missing-data indicator, excursion queue, incident detail with response draft and disposition form, decision history, reconciliation, partner verification.

The frontend holds no business rules; it only displays what the API returns. Every screen shows that data is simulated and policies are teaching policies (NFR-01, NFR-02).

Main requirements: FR-30 to FR-36, NFR-01, NFR-02.
