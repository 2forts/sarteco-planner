#!/usr/bin/env python3
"""
Run the whole synthetic benchmark and aggregate KPIs into a single CSV.

- Walks a benchmark directory tree and detects instance folders containing the required CSVs.
- Calls the solver programmatically (planner.solve.solve) for speed and reliability.
- Writes per-instance outputs to an output directory mirroring the input structure.
- Produces a single kpis.csv with one row per instance.

Usage:
  python tools/run_benchmark.py \
    --suite data/benchmark/sarteco_synth_v1 \
    --out results/sarteco_synth_v1 \
    --time_limit 300 \
    --ship_window 2 \
    --kpi_csv results/sarteco_synth_v1/kpis.csv

Resume:
  If --resume is set, it skips instances that already have a kpis.json in their output folder.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from planner.solve import solve as solve_instance


REQUIRED_FILES = [
    "products.csv",
    "orders.csv",
    "spaces.csv",
    "setups.csv",
    "staff_calendar.csv",
    "storage.csv",
]


def is_instance_dir(p: Path) -> bool:
    return all((p / f).exists() for f in REQUIRED_FILES)


def find_instances(root: Path) -> List[Path]:
    # Fast enough for ~180 instances; walks whole tree once.
    inst = []
    for d in root.rglob("*"):
        if d.is_dir() and is_instance_dir(d):
            inst.append(d)
    return sorted(inst)


def read_meta_if_exists(data_dir: Path) -> Dict:
    meta = data_dir / "meta.json"
    if meta.exists():
        try:
            return json.loads(meta.read_text())
        except Exception:
            return {}
    return {}


def write_json(p: Path, obj: Dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2, ensure_ascii=False))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", type=Path, required=True, help="Benchmark suite root (e.g., data/benchmark/sarteco_synth_v1)")
    ap.add_argument("--out", type=Path, required=True, help="Output root for solver results")
    ap.add_argument("--time_limit", type=int, default=300, help="Time limit (seconds) per instance")
    ap.add_argument("--ship_window", type=int, default=2, help="Shipping window (days), passed to solver")
    ap.add_argument("--kpi_csv", type=Path, required=True, help="Path to consolidated KPI CSV output")
    ap.add_argument("--resume", action="store_true", help="Skip instances already solved (kpis.json exists)")
    args = ap.parse_args()

    suite_root = args.suite.resolve()
    out_root = args.out.resolve()
    out_root.mkdir(parents=True, exist_ok=True)

    instances = find_instances(suite_root)
    if not instances:
        raise SystemExit(f"No instances found under: {suite_root}")

    rows: List[Dict] = []
    t0_all = time.time()

    print(f"[INFO] Found {len(instances)} instances under {suite_root}")
    print(f"[INFO] time_limit={args.time_limit}s, ship_window={args.ship_window}")

    for i, data_dir in enumerate(instances, start=1):
        rel = data_dir.relative_to(suite_root)
        out_dir = out_root / rel
        out_dir.mkdir(parents=True, exist_ok=True)

        kpis_json_path = out_dir / "kpis.json"

        if args.resume and kpis_json_path.exists():
            # Load existing KPIs into the consolidated table
            try:
                existing = json.loads(kpis_json_path.read_text())
            except Exception:
                existing = {}
            row = {
                "instance_path": str(rel),
                "data_dir": str(data_dir),
                "out_dir": str(out_dir),
                "time_limit_s": args.time_limit,
                "ship_window": args.ship_window,
                **existing,
            }
            meta = read_meta_if_exists(data_dir)
            # Flatten a few helpful meta fields if present
            row.update({
                "meta_seed": meta.get("seed"),
                "meta_scale": meta.get("scale"),
                "meta_scenario": meta.get("scenario"),
                "meta_n_orders": meta.get("n_orders"),
            })
            rows.append(row)
            print(f"[{i:03d}/{len(instances):03d}] SKIP (resume) {rel}")
            continue

        print(f"[{i:03d}/{len(instances):03d}] SOLVE {rel}")
        t0 = time.time()
        try:
            kpis = solve_instance(
                data_dir=data_dir,
                out_dir=out_dir,
                time_limit_s=args.time_limit,
                ship_window=args.ship_window,
            )
            status = "ok"
            err = ""
        except Exception as e:
            # Keep going; record the failure
            kpis = {}
            status = "error"
            err = repr(e)

        elapsed = time.time() - t0

        # Persist instance-level KPIs for resume/debug
        payload = {
            "status": status,
            "error": err,
            "elapsed_s": round(elapsed, 6),
            **(kpis if isinstance(kpis, dict) else {"kpis_raw": str(kpis)}),
        }
        write_json(kpis_json_path, payload)

        meta = read_meta_if_exists(data_dir)

        row = {
            "instance_path": str(rel),
            "data_dir": str(data_dir),
            "out_dir": str(out_dir),
            "time_limit_s": args.time_limit,
            "ship_window": args.ship_window,
            "run_status": status,
            "run_error": err,
            "run_elapsed_s": round(elapsed, 6),
            # Some common meta fields (if your generator writes them)
            "meta_seed": meta.get("seed"),
            "meta_scale": meta.get("scale"),
            "meta_scenario": meta.get("scenario"),
            "meta_n_orders": meta.get("n_orders"),
        }
        # Merge solver KPIs at top level
        if isinstance(kpis, dict):
            row.update(kpis)

        rows.append(row)

    total_elapsed = time.time() - t0_all
    df = pd.DataFrame(rows)

    # Put some columns first if they exist
    preferred = [
        "instance_path", "meta_scale", "meta_scenario", "meta_seed",
        "meta_n_orders", "time_limit_s", "ship_window",
        "run_status", "run_elapsed_s",
    ]
    cols = preferred + [c for c in df.columns if c not in preferred]
    df = df[cols]

    args.kpi_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.kpi_csv, index=False)

    print(f"[OK] Wrote KPIs CSV: {args.kpi_csv}")
    print(f"[OK] Total elapsed: {total_elapsed:.2f}s")


if __name__ == "__main__":
    main()