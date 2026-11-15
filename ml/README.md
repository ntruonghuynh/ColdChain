# ml/

**Status: Milestone 4 implemented.** Offline reproducible pipeline and frozen inference package; see `docs/milestones/m4/README.md`.

Contents:

| Path | Purpose |
|---|---|
| `coldchain_ml/` | Causal windows, observed-only features, isolated labels, train/validation selection, event aggregation, freeze and evaluation |
| `configs/training-v1.json` | Versioned deterministic candidate, split and validation selection configuration |
| `registry/coldchain-rf-v1.0.0/` | Frozen model, feature spec, training config, model card, manifest, checksums |
| `evaluation/` | Raw validation predictions/events/metrics and one-shot post-freeze seed-11 test results |

Reproduce in the Python 3.12 environment from the repository root:

```bash
PYTHONPATH=ml:backend python -m coldchain_ml train
PYTHONPATH=ml:backend python -m coldchain_ml internal-test
```

The first command reads only train and validation rows and refuses a noncanonical seed. Run the second command once, only after confirming the frozen bundle. It refuses an existing holdout output. Seeds 22, 33, 44, 55 and 66 are not accepted. Training uses the pinned dependencies in `backend/requirements.txt`.

Operational API: `POST /api/predictions`; model readiness/version: `GET /api/predictions/model`. Predictions are advisory and append-only. The API and feature builder never access labels.

Main requirements: ML-01 to ML-10, FR-13, FR-14, DATA-05.
