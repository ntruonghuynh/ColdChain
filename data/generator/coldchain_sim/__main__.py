"""Command line: ``python -m coldchain_sim <command>``.

  generate  --config C --seed N --out DIR [--journeys N] [--overwrite]
  seeds     --config C --seeds 22,33,44,55,66 --out-root DIR [--journeys N] [--overwrite]
  verify    DIR [--regenerate]

Run from the repository root (inside Docker: ``docker compose --profile tools run --rm
data-tools python -m coldchain_sim ...``). Output goes to ``data/generated/`` unless you
deliberately target ``data/release/``.
"""

import argparse
import json
import sys
import time
from pathlib import Path

from coldchain_sim.config import find_repo_root
from coldchain_sim.dataset import OutputExistsError, generate_dataset
from coldchain_sim.verify import verify_by_regeneration, verify_files


def _summary(manifest: dict) -> str:
    counts = {f["path"]: f["rows"] for f in manifest["files"] if f["rows"] is not None}
    lines = [f"dataset_id          {manifest['dataset_id']}",
             f"seed / split_seed   {manifest['seed']} / {manifest['split_seed']}",
             f"journeys            {manifest['journey_count']}",
             f"fingerprint         {manifest['dataset_fingerprint']}"]
    lines += [f"  {path:<32} {rows:>8} rows" for path, rows in sorted(counts.items())]
    return "\n".join(lines)


def cmd_generate(args: argparse.Namespace) -> int:
    started = time.monotonic()
    try:
        manifest = generate_dataset(Path(args.config), args.seed, Path(args.out), journey_count=args.journeys,
                                    repo_root=Path(args.repo_root) if args.repo_root else None,
                                    overwrite=args.overwrite)
    except OutputExistsError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(_summary(manifest))
    print(f"written to          {args.out}  ({time.monotonic() - started:.1f} s)")
    return 0


def cmd_seeds(args: argparse.Namespace) -> int:
    seeds = [int(s) for s in args.seeds.split(",") if s.strip()]
    status = 0
    for seed in seeds:
        out = Path(args.out_root) / f"seed{seed}"
        args_one = argparse.Namespace(config=args.config, seed=seed, out=str(out), journeys=args.journeys,
                                      repo_root=args.repo_root, overwrite=args.overwrite)
        status = max(status, cmd_generate(args_one))
    return status


def cmd_verify(args: argparse.Namespace) -> int:
    dataset_dir = Path(args.dataset_dir)
    problems = verify_files(dataset_dir)
    print(f"checksums: {'OK' if not problems else 'FAILED'}")
    if args.regenerate:
        root = Path(args.repo_root) if args.repo_root else find_repo_root(Path.cwd())
        regen = verify_by_regeneration(dataset_dir, root)
        print(f"regeneration: {'identical content' if not regen else 'DIFFERENT'}")
        problems += regen
    for p in problems:
        print(f"  - {p}")
    if not problems:
        manifest = json.loads((dataset_dir / "manifest.json").read_text())
        print(f"dataset_id {manifest['dataset_id']}  fingerprint {manifest['dataset_fingerprint']}")
    return 1 if problems else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m coldchain_sim",
                                     description="Seeded synthetic cold-chain journey simulator (SYNTHETIC data).")
    parser.add_argument("--repo-root", help="Repository root (default: found from the config path).")
    sub = parser.add_subparsers(dest="command", required=True)

    g = sub.add_parser("generate", help="Generate one dataset.")
    g.add_argument("--config", required=True)
    g.add_argument("--seed", type=int, required=True)
    g.add_argument("--out", required=True)
    g.add_argument("--journeys", type=int, default=None, help="Override dataset.journey_count.")
    g.add_argument("--overwrite", action="store_true", help="Replace dataset files in a non-empty --out.")
    g.set_defaults(func=cmd_generate)

    s = sub.add_parser("seeds", help="Generate one dataset per seed into OUT_ROOT/seed<N>.")
    s.add_argument("--config", required=True)
    s.add_argument("--seeds", required=True, help="Comma-separated, e.g. 22,33,44,55,66")
    s.add_argument("--out-root", required=True)
    s.add_argument("--journeys", type=int, default=None)
    s.add_argument("--overwrite", action="store_true")
    s.set_defaults(func=cmd_seeds)

    v = sub.add_parser("verify", help="Check a dataset against its manifest.")
    v.add_argument("dataset_dir")
    v.add_argument("--regenerate", action="store_true", help="Also regenerate and compare content hashes.")
    v.set_defaults(func=cmd_verify)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
