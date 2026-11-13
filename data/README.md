# data/

**Status: not implemented.** Scheduled for Milestone 2.

Planned contents:

| Path | Purpose | Tracked in Git |
|---|---|---|
| `generator/` | Seeded journey simulator (Python package + CLI + scenario configs) | yes |
| `dictionary/` | Data dictionary (units, timezone, missing-value meaning, label source) and provenance record | yes |
| `release/` | Canonical dataset used for evaluation, with `manifest.json` hashes (decision D-05) | yes, if approved |
| `generated/` | Scratch output from local runs | no |

Ground-truth labels are stored separately from observed readings (DATA-09).

Main requirements: DATA-01 to DATA-09, SC-02, EVAL-10.
