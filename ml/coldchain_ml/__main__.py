"""Training and one-shot holdout command line entry points."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from coldchain_ml.train import DEFAULT_DATASET, MODEL_VERSION, REGISTRY, evaluate_internal_test, run_training


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m coldchain_ml")
    commands = parser.add_subparsers(dest="command", required=True)
    train = commands.add_parser("train", help="train, select on validation, and freeze")
    train.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    holdout = commands.add_parser("internal-test", help="run the one post-freeze seed-11 holdout check")
    holdout.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    holdout.add_argument("--model", type=Path, default=REGISTRY / MODEL_VERSION)
    args = parser.parse_args()
    if args.command == "train":
        print(run_training(args.dataset))
    else:
        print(json.dumps(evaluate_internal_test(args.model, args.dataset), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
