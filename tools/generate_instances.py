#!/usr/bin/env python3
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
# Data models (parametric spec)
# -----------------------------

@dataclass(frozen=True)
class ProcessSpec:
    stages: List[str]                 # e.g., ["Cut", "Weld", "Paint"]
    skills: List[str]                 # e.g., ["A", "B", "C"]
    product_types: List[str]          # e.g., ["P1","P2","P3"]
    # product_routes[ptype] = list of operations in order:
    # (stage, skill, workers_required, duration_hours)
    product_routes: Dict[str, List[Tuple[str, str, int, float]]]

    stage_capacity: Dict[str, int]    # parallel spaces per stage
    setup_min_h: float                # setup hours for type change (lower)
    setup_max_h: float                # setup hours for type change (upper)


@dataclass(frozen=True)
class InstanceFamily:
    name: str
    horizon_days: int

    # Orders
    n_orders: int
    qty_min: int
    qty_max: int
    product_mix: Dict[str, float]     # probabilities over product types

    # Due dates (in working days)
    due_min: int
    due_max: int

    # Staff capacity (workers per skill per day)
    staff_base: Dict[str, int]
    # optional variability: some days reduced capacity (vacations)
    vacation_days: List[int]
    vacation_factor: float

    # Storage
    max_finished_storage: int


# -----------------------------
# Helpers
# -----------------------------

def _normalize_probs(p: Dict[str, float]) -> Dict[str, float]:
    s = sum(p.values())
    if s <= 0:
        raise ValueError("Probabilities must sum to > 0.")
    return {k: v / s for k, v in p.items()}

def _sample_key(rng: random.Random, probs: Dict[str, float]) -> str:
    probs = _normalize_probs(probs)
    r = rng.random()
    acc = 0.0
    for k, w in probs.items():
        acc += w
        if r <= acc:
            return k
    return list(probs.keys())[-1]


# -----------------------------
# CSV builders (format-agnostic)
# -----------------------------

def build_products_csv(proc: ProcessSpec) -> pd.DataFrame:
    rows = []
    for pt in proc.product_types:
        route = proc.product_routes[pt]
        for idx, (stage, skill, workers, dur_h) in enumerate(route, start=1):
            rows.append({
                "product_type": pt,
                "operation_id": f"{pt}_op{idx}",   # <-- obligatorio
                "op_index": idx,
                "stage": stage,
                "skill": skill,
                "workers": int(workers),
                "duration_hours": float(dur_h),
            })
    return pd.DataFrame(rows)

def build_spaces_csv(proc: ProcessSpec) -> pd.DataFrame:
    return pd.DataFrame([{"stage": s, "capacity": int(proc.stage_capacity[s])} for s in proc.stages])

def build_setups_csv(proc: ProcessSpec, rng: random.Random) -> pd.DataFrame:
    rows = []
    for stage in proc.stages:
        for f in proc.product_types:
            for t in proc.product_types:
                setup = 0.0 if f == t else rng.uniform(proc.setup_min_h, proc.setup_max_h)
                rows.append({
                    "stage": stage,
                    "from_type": f,
                    "to_type": t,
                    "setup_hours": round(setup, 3)
                })
    return pd.DataFrame(rows)

def build_orders_csv(fam: InstanceFamily, rng: random.Random) -> pd.DataFrame:
    rows = []
    for i in range(1, fam.n_orders + 1):
        pt = _sample_key(rng, fam.product_mix)
        qty = rng.randint(fam.qty_min, fam.qty_max)
        due = rng.randint(fam.due_min, fam.due_max)
        rows.append({
            "order_id": f"O{i:03d}",
            "product_type": pt,
            "quantity": int(qty),
            "due_day": int(due),
        })
    return pd.DataFrame(rows)

def build_staff_calendar_csv(proc: ProcessSpec, fam: InstanceFamily) -> pd.DataFrame:
    vac = set(fam.vacation_days)
    rows = []
    for day in range(1, fam.horizon_days + 1):
        for skill in proc.skills:
            cap = int(fam.staff_base.get(skill, 0))
            if day in vac:
                cap = int(math.floor(cap * fam.vacation_factor))
            rows.append({"day": day, "skill": skill, "max_workers": cap})
    return pd.DataFrame(rows)

def build_storage_csv(fam: InstanceFamily) -> pd.DataFrame:
    return pd.DataFrame([{"max_finished_storage": int(fam.max_finished_storage)}])


# -----------------------------
# Writer
# -----------------------------

def write_instance(out_dir: Path, proc: ProcessSpec, fam: InstanceFamily, seed: int) -> None:
    rng = random.Random(seed)
    out_dir.mkdir(parents=True, exist_ok=True)

    products = build_products_csv(proc)
    spaces = build_spaces_csv(proc)
    setups = build_setups_csv(proc, rng)
    orders = build_orders_csv(fam, rng)
    staff = build_staff_calendar_csv(proc, fam)
    storage = build_storage_csv(fam)

    products.to_csv(out_dir / "products.csv", index=False)
    spaces.to_csv(out_dir / "spaces.csv", index=False)
    setups.to_csv(out_dir / "setups.csv", index=False)
    orders.to_csv(out_dir / "orders.csv", index=False)
    staff.to_csv(out_dir / "staff_calendar.csv", index=False)
    storage.to_csv(out_dir / "storage.csv", index=False)

    meta = {
        "family": fam.name,
        "seed": seed,
        "horizon_days": fam.horizon_days,
        "n_orders": fam.n_orders,
        "qty_range": [fam.qty_min, fam.qty_max],
        "due_range": [fam.due_min, fam.due_max],
        "max_finished_storage": fam.max_finished_storage,
        "vacation_days": fam.vacation_days,
        "vacation_factor": fam.vacation_factor,
        "stage_capacity": proc.stage_capacity,
        "staff_base": fam.staff_base,
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2))


# -----------------------------
# CLI / Example suites
# -----------------------------

def example_process() -> ProcessSpec:
    # EDIT THIS to reflect your target industrial-like setting
    stages = ["S1", "S2", "S3"]
    skills = ["A", "B", "C"]
    product_types = ["P1", "P2", "P3"]

    routes = {
        "P1": [("S1", "A", 1, 4.0), ("S2", "B", 1, 6.0), ("S3", "C", 1, 3.0)],
        "P2": [("S1", "A", 1, 5.0), ("S2", "B", 2, 5.0), ("S3", "C", 1, 4.0)],
        "P3": [("S1", "A", 2, 4.0), ("S2", "B", 1, 7.0), ("S3", "C", 1, 2.0)],
    }
    cap = {"S1": 2, "S2": 2, "S3": 1}

    return ProcessSpec(
        stages=stages,
        skills=skills,
        product_types=product_types,
        product_routes=routes,
        stage_capacity=cap,
        setup_min_h=0.5,
        setup_max_h=2.0,
    )

def build_families() -> List[InstanceFamily]:
    # Three defensible families: baseline, tight_due, tight_storage
    return [
        InstanceFamily(
            name="baseline",
            horizon_days=30,
            n_orders=12,
            qty_min=1, qty_max=6,
            product_mix={"P1": 0.4, "P2": 0.35, "P3": 0.25},
            due_min=10, due_max=25,
            staff_base={"A": 4, "B": 4, "C": 3},
            vacation_days=[10, 11, 12],
            vacation_factor=0.6,
            max_finished_storage=20,
        ),
        InstanceFamily(
            name="tight_due",
            horizon_days=30,
            n_orders=12,
            qty_min=1, qty_max=6,
            product_mix={"P1": 0.4, "P2": 0.35, "P3": 0.25},
            due_min=8, due_max=15,   # earlier due dates -> tighter
            staff_base={"A": 4, "B": 4, "C": 3},
            vacation_days=[10, 11, 12],
            vacation_factor=0.6,
            max_finished_storage=20,
        ),
        InstanceFamily(
            name="tight_storage",
            horizon_days=30,
            n_orders=12,
            qty_min=1, qty_max=6,
            product_mix={"P1": 0.4, "P2": 0.35, "P3": 0.25},
            due_min=10, due_max=25,
            staff_base={"A": 4, "B": 4, "C": 3},
            vacation_days=[10, 11, 12],
            vacation_factor=0.6,
            max_finished_storage=6,   # smaller buffer -> tighter storage
        ),
    ]

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("data/synth"), help="Output directory root")
    ap.add_argument("--instances_per_family", type=int, default=20)
    ap.add_argument("--seed0", type=int, default=1000)
    ap.add_argument("--suite", type=str, default="S1")
    args = ap.parse_args()

    proc = example_process()
    families = build_families()

    seed = args.seed0
    for fam in families:
        fam_root = args.out / args.suite / fam.name
        for k in range(1, args.instances_per_family + 1):
            inst_dir = fam_root / f"I{k:03d}"
            write_instance(inst_dir, proc, fam, seed)
            seed += 1

    print(f"Generated {args.instances_per_family} instances for each family under {args.out / args.suite}")

if __name__ == "__main__":
    main()