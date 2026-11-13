# scripts/

**Status: not implemented.**

Planned contents:

| Path | Purpose | Milestone |
|---|---|---|
| `start.sh`, `start.ps1`, `stop.*`, `reset.*` | One-command start/stop/reset for Docker Desktop users | M1 |
| `replay_dataset.py` | Replay generated journeys through the ingestion API | M3 |
| `demo/` | The four required demonstration scenarios (normal, ocean gap, unauthorized action, retry recovery) | M8 |
| `eval/` | Evaluation runners writing raw results to `docs/evaluation/runs/` | M9 |
| `package_zip.sh` | Build the distributable ZIP and check it holds no secrets | M10 |
