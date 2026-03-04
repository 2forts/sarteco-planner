#!/usr/bin/env python3
"""
Benchmark generator for sarteco-planner.

Generates a structured synthetic benchmark with:
- 3 scales: small/medium/large
- 3 scenarios: baseline / tight_delivery / tight_storage
- N instances per (scale, scenario)
- Reproducible seeds
- Full CSV set expected by planner/io.py:
    products.csv: product_type, operation_id, op_index, stage, skill, workers, duration_hours
    spaces.csv: stage, capacity
    setups.csv: stage, from_type, to_type, setup_hours
    orders.csv: order_id, product_type, quantity, due_day
    staff_calendar.csv: day, skill, max_workers
    storage.csv: max_finished_storage
plus meta.json for traceability.

Usage:
  python tools/generate_benchmark.py --out data/benchmark --n 20 --seed0 1000
"""

from __future__ import annotations

import argparse
import json
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd


# -----------------------------
# Benchmark design (paper-like)
# -----------------------------

STAGES = ["S1", "S2", "S3", "S4"]  # Preparation, Assembly, Finishing, Inspection
SKILLS = ["R1", "R2", "R3"]        # Technician, Specialist, Inspector
PRODUCT_TYPES = ["P1", "P2", "P3", "P4", "P5"]

# Fixed process routes (4 ops each): (stage, skill, workers, duration_hours)
PRODUCT_ROUTES: Dict[str, List[Tuple[str, str, int, float]]] = {
    "P1": [("S1", "R1", 1, 4.0), ("S2", "R2", 2, 6.0), ("S3", "R1", 1, 5.0), ("S4", "R3", 1, 2.0)],
    "P2": [("S1", "R1", 1, 5.0), ("S2", "R2", 1, 7.0), ("S3", "R1", 2, 4.0), ("S4", "R3", 1, 3.0)],
    "P3": [("S1", "R1", 2, 3.0), ("S2", "R2", 2, 6.0), ("S3", "R1", 1, 4.0), ("S4", "R3", 1, 2.0)],
    "P4": [("S1", "R1", 1, 6.0), ("S2", "R2", 1, 5.0), ("S3", "R1", 2, 5.0), ("S4", "R3", 1, 3.0)],
    "P5": [("S1", "R1", 1, 4.0), ("S2", "R2", 2, 7.0), ("S3", "R1", 1, 6.0), ("S4", "R3", 1, 2.0)],
}

# Stage capacities (parallel spaces)
STAGE_CAPACITY = {"S1": 3, "S2": 2, "S3": 2, "S4": 1}

# Staff base capacity per day
STAFF_BASE = {"R1": 6, "R2": 5, "R3": 3}

# Horizon and vacations
HORIZON_DAYS = 60
VACATION_DAYS = list(range(20, 23))  # 20-22 inclusive
VACATION_FACTOR = 0.5

# Setup times (sequence-dependent) in hours
SETUP_MIN_H = 0.5
SETUP_MAX_H = 2.0

# Product mix (uniform)
PRODUCT_MIX = {p: 1.0 for p in PRODUCT_TYPES}


SCALES = {
    # scale_name: (n_orders, qty_min, qty_max)
    "small":  (10, 1, 4),
    "medium": (20, 1, 6),
    "large":  (40, 1, 8),
}

SCENARIOS = {
    # scenario_name: due_range (min,max), storage capacity
    "baseline":       ((25, 50), 50),
    "tight_delivery": ((10, 25), 50),
    "tight_storage":  ((25, 50), 10),
}


# -----------------------------
# CSV builders (match io.py)
# -----------------------------

def normalize_probs(p: Dict[str, float]) -> Dict[str, float]:
    s = sum(p.values())
    if s <= 0:
        raise ValueError("Probabilities must sum to > 0.")
    return {k: v / s for k, v in p.items()}

def sample_key(rng: random.Random, probs: Dict[str, float]) -> str:
    probs = normalize_probs(probs)
    r = rng.random()
    acc = 0.0
    for k, w in probs.items():
        acc += w
        if r <= acc:
            return k
    return list(probs.keys())[-1]

def build_products_csv() -> pd.DataFrame:
    rows = []
    for pt in PRODUCT_TYPES:
        route = PRODUCT_ROUTES[pt]
        for op_index, (stage, skill, workers, dur) in enumerate(route, start=1):
            rows.append({
                "product_type": pt,
                "operation_id": f"{pt}_op{op_index}",   # REQUIRED by planner/io.py
                "op_index": int(op_index),
                "stage": stage,
                "skill": skill,
                "workers": int(workers),
                "duration_hours": float(dur),
            })
    return pd.DataFrame(rows)

def build_spaces_csv() -> pd.DataFrame:
    return pd.DataFrame([{"stage": s, "capacity": int(STAGE_CAPACITY[s])} for s in STAGES])

def build_setups_csv(rng: random.Random) -> pd.DataFrame:
    rows = []
    for stage in STAGES:
        for f in PRODUCT_TYPES:
            for t in PRODUCT_TYPES:
                setup = 0.0 if f == t else rng.uniform(SETUP_MIN_H, SETUP_MAX_H)
                rows.append({
                    "stage": stage,
                    "from_type": f,
                    "to_type": t,
                    "setup_hours": round(setup, 3),
                })
    return pd.DataFrame(rows)

def build_orders_csv(n_orders: int, qty_min: int, qty_max: int, due_min: int, due_max: int,
                     rng: random.Random) -> pd.DataFrame:
    rows = []
    for i in range(1, n_orders + 1):
        pt = sample_key(rng, PRODUCT_MIX)
        qty = rng.randint(qty_min, qty_max)
        due = rng.randint(due_min, due_max)
        rows.append({
            "order_id": f"O{i:03d}",
            "product_type": pt,
            "quantity": int(qty),
            "due_day": int(due),
        })
    return pd.DataFrame(rows)

def build_staff_calendar_csv() -> pd.DataFrame:
    vac = set(VACATION_DAYS)
    rows = []
    for day in range(1, HORIZON_DAYS + 1):
        for skill in SKILLS:
            cap = int(STAFF_BASE.get(skill, 0))
            if day in vac:
                cap = int(math.floor(cap * VACATION_FACTOR))
            rows.append({"day": day, "skill": skill, "max_workers": cap})
    return pd.DataFrame(rows)

def build_storage_csv(max_finished_storage: int) -> pd.DataFrame:
    return pd.DataFrame([{"max_finished_storage": int(max_finished_storage)}])


# -----------------------------
# Writer
# -----------------------------

@dataclass(frozen=True)
class InstanceSpec:
    scale: str
    scenario: str
    instance_id: str
    seed: int
    n_orders: int
    qty_min: int
    qty_max: int
    due_min: int
    due_max: int
    max_finished_storage: int

def write_instance(out_dir: Path, spec: InstanceSpec) -> None:
    rng = random.Random(spec.seed)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Fixed across the whole benchmark (process definition)
    products = build_products_csv()
    spaces = build_spaces_csv()
    staff = build_staff_calendar_csv()

    # Varies by instance/seed
    setups = build_setups_csv(rng)
    orders = build_orders_csv(spec.n_orders, spec.qty_min, spec.qty_max, spec.due_min, spec.due_max, rng)
    storage = build_storage_csv(spec.max_finished_storage)

    products.to_csv(out_dir / "products.csv", index=False)
    spaces.to_csv(out_dir / "spaces.csv", index=False)
    setups.to_csv(out_dir / "setups.csv", index=False)
    orders.to_csv(out_dir / "orders.csv", index=False)
    staff.to_csv(out_dir / "staff_calendar.csv", index=False)
    storage.to_csv(out_dir / "storage.csv", index=False)

    meta = {
        "scale": spec.scale,
        "scenario": spec.scenario,
        "instance_id": spec.instance_id,
        "seed": spec.seed,
        "horizon_days": HORIZON_DAYS,
        "vacation_days": VACATION_DAYS,
        "vacation_factor": VACATION_FACTOR,
        "setup_range_hours": [SETUP_MIN_H, SETUP_MAX_H],
        "n_orders": spec.n_orders,
        "quantity_range": [spec.qty_min, spec.qty_max],
        "due_range_days": [spec.due_min, spec.due_max],
        "max_finished_storage": spec.max_finished_storage,
        "stage_capacity": STAGE_CAPACITY,
        "staff_base": STAFF_BASE,
        "product_mix": PRODUCT_MIX,
        "process": {
            "stages": STAGES,
            "skills": SKILLS,
            "product_types": PRODUCT_TYPES,
            "routes": PRODUCT_ROUTES,
        },
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2))


# -----------------------------
# Main
# -----------------------------

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("data/benchmark"), help="Output root directory")
    ap.add_argument("--n", type=int, default=20, help="Instances per (scale, scenario)")
    ap.add_argument("--seed0", type=int, default=1000, help="Base seed")
    ap.add_argument("--suite_name", type=str, default="sarteco_synth_v1", help="Top-level suite folder name")
    args = ap.parse_args()

    suite_root = args.out / args.suite_name
    seed = args.seed0

    total = 0
    for scale, (n_orders, qty_min, qty_max) in SCALES.items():
        for scenario, (due_rng, storage_cap) in SCENARIOS.items():
            due_min, due_max = due_rng
            for k in range(1, args.n + 1):
                inst_id = f"I{k:03d}"
                spec = InstanceSpec(
                    scale=scale,
                    scenario=scenario,
                    instance_id=inst_id,
                    seed=seed,
                    n_orders=n_orders,
                    qty_min=qty_min,
                    qty_max=qty_max,
                    due_min=due_min,
                    due_max=due_max,
                    max_finished_storage=storage_cap,
                )
                out_dir = suite_root / scale / scenario / inst_id
                write_instance(out_dir, spec)
                seed += 1
                total += 1

    print(f"[OK] Generated {total} instances under: {suite_root}")
    print("Example:")
    print(f"  python -m planner.solve --data {suite_root}/small/baseline/I001 --time_limit 20 --ship_window 2")


if __name__ == "__main__":
    main()