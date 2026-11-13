# scripts/

| Path | Purpose | Status |
|---|---|---|
| `smoke_test.py` | End-to-end check of the Docker stack: config, startup + health, React app and SPA routes, `/api` proxy, seeded policy, backend outage handling, shutdown, data persistence across restart. Standard library only. `python3 scripts/smoke_test.py [--keep-running]` | M1, implemented |
| `replay_dataset.py` | Replay generated journeys through the ingestion API | M3, planned |
| `demo/` | The four required demonstration scenarios | M8, planned |
| `eval/` | Evaluation runners writing raw results to `docs/evaluation/runs/` | M9, planned |
| `package_zip.sh` | Build the distributable ZIP and check it holds no secrets | M10, planned |

The one-click start/stop scripts for students live in the repository root: `start.command` / `stop.command` (macOS) and `start.bat` / `stop.bat` (Windows).
