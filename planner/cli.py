import argparse
from pathlib import Path

from .solve import solve


def main() -> None:
    p = argparse.ArgumentParser(description="Multi-stage production planner (SARTECO companion)")
    p.add_argument("--data", type=str, required=True, help="Path to a data folder (CSV inputs)")
    p.add_argument("--time_limit", type=int, default=20, help="Solver time limit (seconds)")
    p.add_argument("--out", type=str, default="outputs", help="Output folder")
    args = p.parse_args()

    solve(Path(args.data), Path(args.out), time_limit_s=args.time_limit)


if __name__ == "__main__":
    main()
