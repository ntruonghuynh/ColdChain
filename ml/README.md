# ml/

**Status: not implemented.** Scheduled for Milestone 4.

Planned contents (see `docs/architecture.md` §6):

| Path | Purpose |
|---|---|
| `coldchain_ml/` | Windowing, features, journey-level splits, training, tuning, freezing, evaluation, prediction |
| `configs/` | Versioned training and feature configs |
| `registry/<model_version>/` | Frozen model, feature spec, preprocessing config, data manifest hash, model card, file hashes |
| `tests/` | Leakage, determinism and feature tests |

Rules: split by journey; tune on validation only; freeze before the single test run; predictions are advisory only.

Main requirements: ML-01 to ML-10, FR-13, FR-14, DATA-05.
