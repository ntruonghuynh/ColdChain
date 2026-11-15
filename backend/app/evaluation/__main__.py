"""``python -m app.evaluation baseline DATASET_DIR --out OUT_DIR`` (development measurement only).

Run inside Docker from the repository root:
``docker compose --profile tools run --rm data-tools python -m app.evaluation baseline \
data/release/coldchain-sim-v1.0.0-seed11 --out docs/evaluation/dev/m3-baseline-seed11``
"""

import argparse
import json
import sys
from pathlib import Path

from app.evaluation.baseline import DEVELOPMENT_PARTITIONS, EvaluationRefused, run_baseline_evaluation

APP_DIR = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.evaluation")
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("baseline", help="Offline development evaluation of the M3 policy baseline.")
    b.add_argument("dataset_dir")
    b.add_argument("--out", required=True)
    b.add_argument("--partitions", default=",".join(DEVELOPMENT_PARTITIONS))
    b.add_argument("--git-commit", default=None)
    b.add_argument("--policy-file", default=str(APP_DIR / "seed/data/policies/POL-CHILL-01_v1.0.json"))
    b.add_argument("--detector-config", default=str(APP_DIR / "seed/data/detector/DET-BASELINE_v1.0.0.json"))
    args = parser.parse_args(argv)
    try:
        result = run_baseline_evaluation(
            Path(args.dataset_dir),
            Path(args.policy_file),
            Path(args.detector_config),
            Path(args.out),
            partitions=tuple(p for p in args.partitions.split(",") if p),
            git_commit=args.git_commit,
        )
    except EvaluationRefused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result["summary"], indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
