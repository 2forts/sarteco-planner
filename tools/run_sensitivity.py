#!/usr/bin/env python3
"""
Sensitivity analysis runner for sarteco-planner.

It runs a controlled set of instances (default: medium/baseline, 20 instances)
and varies:
  A) ship_window (solver parameter)
  B) storage capacity (edits storage.csv in a temp copy)
  C) staff capacity factor (edits staff_calendar.csv in a temp copy)

Outputs:
  results/<tag>/runs.csv                 # all runs (one row per run)
  results/<tag>/summary.csv              # aggregated stats
  results/<tag>/fig_ship_window.(pdf/png)
  results/<tag>/fig_storage.(pdf/png)
  results/<tag>/fig_staff.(pdf/png)

Usage example:
  PYTHONPATH=. python tools/run_sensitivity.py \
    --suite data/benchmark/sarteco_synth_v1 \
    --subset medium/baseline \
    --out results/sensitivity_v1 \
    --time_limit 300 \
    --ship_windows 0,2,5 \
    --storages 5,10,20,50 \
    --staff_factors 0.8,1.0,1.2
"""

from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd
import matplotlib.pyplot as plt

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
    inst = []
    for d in root.rglob("*"):
        if d.is_dir() and is_instance_dir(d):
            inst.append(d)
    return sorted(inst)


def parse_csv_list(s: str, cast=float) -> List:
    if not s.strip():
        return []
    return [cast(x.strip()) for x in s.split(",") if x.strip()]


def read_meta(data_dir: Path) -> Dict:
    p = data_dir / "meta.json"
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            return {}
    return {}


def clone_instance(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def patch_storage(data_dir: Path, max_storage: int) -> None:
    p = data_dir / "storage.csv"
    df = pd.read_csv(p)
    if "max_finished_storage" not in df.columns:
        raise ValueError(f"{p} missing column max_finished_storage")
    df["max_finished_storage"] = int(max_storage)
    df.to_csv(p, index=False)


def patch_staff_factor(data_dir: Path, factor: float) -> None:
    p = data_dir / "staff_calendar.csv"
    df = pd.read_csv(p)
    if "max_workers" not in df.columns:
        raise ValueError(f"{p} missing column max_workers")
    # multiply and floor to int, keep >=0
    df["max_workers"] = (df["max_workers"].astype(float) * float(factor)).apply(lambda x: max(int(x // 1), 0))
    df.to_csv(p, index=False)


def plot_param(summary: pd.DataFrame, param_col: str, out_pdf: Path, title: str) -> None:
    """
    summary must have columns: param_col, run_elapsed_s_mean and optionally run_elapsed_s_max/median
    """
    # one plot, no manual colors (per instructions)
    plt.figure(figsize=(6, 4))
    x = summary[param_col].tolist()
    y = summary["run_elapsed_s_mean"].tolist()
    plt.plot(x, y, marker="o")
    plt.xlabel(param_col)
    plt.ylabel("Average runtime (seconds)")
    plt.title(title)
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(out_pdf)
    plt.savefig(out_pdf.with_suffix(".png"))
    plt.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", type=Path, required=True, help="Benchmark suite root (e.g., data/benchmark/sarteco_synth_v1)")
    ap.add_argument("--subset", type=str, default="medium/baseline", help="Subfolder within suite to use (e.g., medium/baseline)")
    ap.add_argument("--out", type=Path, required=True, help="Output root for sensitivity results")
    ap.add_argument("--time_limit", type=int, default=300, help="Time limit per solve (seconds)")
    ap.add_argument("--ship_windows", type=str, default="0,2,5", help="Comma-separated ship_window values")
    ap.add_argument("--storages", type=str, default="10,50", help="Comma-separated max_finished_storage values")
    ap.add_argument("--staff_factors", type=str, default="1.0", help="Comma-separated staff capacity factors (e.g., 0.8,1.0,1.2)")
    ap.add_argument("--max_instances", type=int, default=20, help="Limit number of instances from the subset")
    ap.add_argument("--workdir", type=Path, default=Path(".tmp_sensitivity"), help="Temp working directory")
    ap.add_argument("--resume", action="store_true", help="Skip runs already present in runs.csv")
    args = ap.parse_args()

    suite_root = args.suite.resolve()
    subset_root = (suite_root / args.subset).resolve()
    out_root = args.out.resolve()
    out_root.mkdir(parents=True, exist_ok=True)

    ship_windows = [int(x) for x in parse_csv_list(args.ship_windows, cast=int)]
    storages = [int(x) for x in parse_csv_list(args.storages, cast=int)]
    staff_factors = [float(x) for x in parse_csv_list(args.staff_factors, cast=float)]

    # discover instances
    instances = [p for p in find_instances(subset_root) if p.name.startswith("I")]
    instances = instances[: args.max_instances]

    if not instances:
        raise SystemExit(f"No instances found under subset: {subset_root}")

    print(f"[INFO] Subset: {subset_root}")
    print(f"[INFO] Using {len(instances)} instances (max_instances={args.max_instances})")
    print(f"[INFO] ship_windows={ship_windows}, storages={storages}, staff_factors={staff_factors}")
    print(f"[INFO] time_limit={args.time_limit}s")

    runs_csv = out_root / "runs.csv"
    existing_keys = set()
    if args.resume and runs_csv.exists():
        df_old = pd.read_csv(runs_csv)
        for _, r in df_old.iterrows():
            existing_keys.add((r["instance_path"], int(r["ship_window"]), int(r["storage"]), float(r["staff_factor"])))

    rows: List[Dict] = []
    t0_all = time.time()

    # temp workspace
    work_root = args.workdir.resolve()
    work_root.mkdir(parents=True, exist_ok=True)

    for idx, src_dir in enumerate(instances, start=1):
        rel = src_dir.relative_to(suite_root)
        instance_id = str(rel)

        meta = read_meta(src_dir)
        meta_seed = meta.get("seed")
        meta_n_orders = meta.get("n_orders")
        meta_scale = meta.get("scale", args.subset.split("/")[0] if "/" in args.subset else None)
        meta_scenario = meta.get("scenario", args.subset.split("/")[1] if "/" in args.subset else None)

        for W in ship_windows:
            for storage in storages:
                for sf in staff_factors:
                    key = (instance_id, int(W), int(storage), float(sf))
                    if args.resume and key in existing_keys:
                        print(f"[{idx:03d}/{len(instances):03d}] SKIP {instance_id} W={W} storage={storage} staff={sf}")
                        continue

                    # clone and patch in temp directory
                    tmp_dir = work_root / rel / f"W{W}_S{storage}_F{sf}"
                    clone_instance(src_dir, tmp_dir)
                    patch_storage(tmp_dir, storage)
                    patch_staff_factor(tmp_dir, sf)

                    out_dir = out_root / "per_instance" / rel / f"W{W}_S{storage}_F{sf}"
                    out_dir.mkdir(parents=True, exist_ok=True)

                    print(f"[{idx:03d}/{len(instances):03d}] RUN  {instance_id} | W={W} storage={storage} staff={sf}")
                    t0 = time.time()
                    try:
                        kpis = solve_instance(
                            data_dir=tmp_dir,
                            out_dir=out_dir,
                            time_limit_s=args.time_limit,
                            ship_window=W,
                        )
                        status = "ok"
                        err = ""
                    except Exception as e:
                        kpis = {}
                        status = "error"
                        err = repr(e)
                    elapsed = time.time() - t0

                    row = {
                        "instance_path": instance_id,
                        "meta_scale": meta_scale,
                        "meta_scenario": meta_scenario,
                        "meta_seed": meta_seed,
                        "meta_n_orders": meta_n_orders,
                        "time_limit_s": args.time_limit,
                        "ship_window": int(W),
                        "storage": int(storage),
                        "staff_factor": float(sf),
                        "run_status": status,
                        "run_error": err,
                        "run_elapsed_s": round(elapsed, 6),
                    }
                    if isinstance(kpis, dict):
                        # merge any KPIs your solver returns (e.g., objective, num_units, num_operations...)
                        row.update(kpis)

                    rows.append(row)

    # merge with existing runs if resuming
    df_new = pd.DataFrame(rows)
    if runs_csv.exists():
        df_prev = pd.read_csv(runs_csv)
        df_all = pd.concat([df_prev, df_new], ignore_index=True)
    else:
        df_all = df_new

    df_all.to_csv(runs_csv, index=False)

    # summaries for each parameter (fix the other params by taking all combinations)
    # We'll produce three summaries: ship_window, storage, staff_factor
    def summarize_by(param: str) -> pd.DataFrame:
        g = df_all[df_all["run_status"] == "ok"].groupby(param)["run_elapsed_s"]
        out = pd.DataFrame({
            param: g.mean().index,
            "run_elapsed_s_mean": g.mean().values,
            "run_elapsed_s_median": g.median().values,
            "run_elapsed_s_max": g.max().values,
            "n_runs": g.size().values,
        })
        return out.sort_values(param)

    sum_ship = summarize_by("ship_window")
    sum_storage = summarize_by("storage")
    sum_staff = summarize_by("staff_factor")

    summary_csv = out_root / "summary.csv"
    # store all three stacked with a tag column
    sum_ship2 = sum_ship.copy(); sum_ship2.insert(0, "parameter", "ship_window")
    sum_storage2 = sum_storage.copy(); sum_storage2.insert(0, "parameter", "storage")
    sum_staff2 = sum_staff.copy(); sum_staff2.insert(0, "parameter", "staff_factor")
    pd.concat([sum_ship2, sum_storage2, sum_staff2], ignore_index=True).to_csv(summary_csv, index=False)

    # plots
    plot_param(sum_ship, "ship_window", out_root / "fig_ship_window.pdf", "Sensitivity: ship_window (W)")
    plot_param(sum_storage, "storage", out_root / "fig_storage.pdf", "Sensitivity: storage capacity")
    plot_param(sum_staff, "staff_factor", out_root / "fig_staff.pdf", "Sensitivity: staff availability factor")

    total_elapsed = time.time() - t0_all
    print(f"[OK] runs.csv:    {runs_csv}")
    print(f"[OK] summary.csv: {summary_csv}")
    print(f"[OK] figs:       {out_root / 'fig_ship_window.pdf'}, {out_root / 'fig_storage.pdf'}, {out_root / 'fig_staff.pdf'}")
    print(f"[OK] Total elapsed: {total_elapsed:.2f}s")


if __name__ == "__main__":
    main()
