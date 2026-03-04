#!/usr/bin/env python3
"""
Generate synthetic planning instances in the CSV format expected by sarteco-planner.

Output structure:
  data/synth/<suite_name>/<class_name>/<instance_id>/
      products.csv
      setups.csv
      spaces.csv
      orders.csv
      staff_calendar.csv
      storage.csv

The planner reads these files via planner.io.load_instance().
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


# ----------------------------
# Config schema
# ----------------------------

@dataclass(frozen=True)
class ProcessTemplate:
    stages: List[str]
    skills: List[str]
    product_types: List[str]
    # operations_per_product[product_type] = list of (stage, skill, workers, duration_hours)
    operations_per_product: Dict[str, List[Tuple[str, str, int, float]]]
    # stage capacities (parallel spaces)
    stage_capacity: Dict[str, int]
    # setup time distribution per stage (hours) for type changes
    setup_min: float
    setup_max: float


@dataclass(frozen=True)
class SuiteConfig:
    name: str
    horizon_days: int
    n_instances_per_class: int
    seeds: List[int]  # used cyclically if needed

    # Orders
    n_orders: int
    quantity_min: int
    quantity_max: int
    mix_product_probs: Dict[str, float]  # per product_type

    # Due dates: due_day sampled from [min_due, max_due]
    min_due: int
    max_due: int

    # Staff
    base_staff_per_skill: Dict[str, int]  # nominal daily capacity
    vacation_days: List[int]              # days where capacity is reduced
    vacation_factor: float                # multiplicative factor on those days (e.g., 0.6)

    # Storage
    max_finished_storage: int


# ----------------------------
# Generators
# ----------------------------

def normalize_probs(p: Dict[str, float]) -> Dict[str, float]:
    s = sum(p.values())
    if s <= 0:
        raise ValueError("Product mix probabilities must sum to > 0.")
    return {k: v / s for k, v in p.items()}


def sample_product_type(rng: random.Random, probs: Dict[str, float]) -> str:
    items = list(probs.items())
    r = rng.random()
    acc = 0.0
    for k, w in items:
        acc += w
        if r <= acc:
            return k
    return items[-1][0]


def build_products_csv(proc: ProcessTemplate) -> pd.DataFrame:
    rows = []
    for pt in proc.product_types:
        ops = proc.operations_per_product[pt]
        for op_index, (stage, skill, workers, dur) in enumerate(ops, start=1):
            rows.append(
                dict(
                    product_type=pt,
                    operation_id=f"{pt}_op{op_index}",
                    op_index=op_index,
                    stage=stage,
                    skill=skill,
                    workers=int(workers),
                    duration_hours=float(dur),
                )
            )
    return pd.DataFrame(rows)


def build_spaces_csv(proc: ProcessTemplate) -> pd.DataFrame:
    rows = [dict(stage=s, capacity=int(proc.stage_capacity[s])) for s in proc.stages]
    return pd.DataFrame(rows)


def build_setups_csv(proc: ProcessTemplate, rng: random.Random) -> pd.DataFrame:
    # sequence-dependent setup times per stage and type change (including same->same as 0)
    rows = []
    for stage in proc.stages:
        for f in proc.product_types:
            for t in proc.product_types:
                setup = 0.0 if f == t else rng.uniform(proc.setup_min, proc.setup_max)
                rows.append(dict(stage=stage, from_type=f, to_type=t, setup_hours=round(setup, 2)))
    return pd.DataFrame(rows)


def build_orders_csv(cfg: SuiteConfig, rng: random.Random) -> pd.DataFrame:
    probs = normalize_probs(cfg.mix_product_probs)
    rows = []
    for i in range(1, cfg.n_orders + 1):
        pt = sample_product_type(rng, probs)
        qty = rng.randint(cfg.quantity_min, cfg.quantity_max)
        due = rng.randint(cfg.min_due, cfg.max_due)
        rows.append(dict(order_id=f"O{i:03d}", product_type=pt, quantity=qty, due_day=due))
    return pd.DataFrame(rows)


def build_staff_calendar_csv(cfg: SuiteConfig, proc: ProcessTemplate) -> pd.DataFrame:
    rows = []
    vac_set = set(cfg.vacation_days)
    for day in range(1, cfg.horizon_days + 1):
        for skill in proc.skills:
            base = int(cfg.base_staff_per_skill.get(skill, 0))
            if day in vac_set:
                base = int(math.floor(base * cfg.vacation_factor))
            rows.append(dict(day=day, skill=skill, max_workers=base))
    return pd.DataFrame(rows)


def build_storage_csv(cfg: SuiteConfig) -> pd.DataFrame:
    return pd.DataFrame([dict(max_finished_storage=int(cfg.max_finished_storage))])


def write_instance(
    out_dir: Path,
    proc: ProcessTemplate,
    cfg: SuiteConfig,
    seed: int,
) -> None:
    rng = random.Random(seed)
    out_dir.mkdir(parents=True, exist_ok=True)

    products = build_products_csv(proc)
    spaces = build_spaces_csv(proc)
    setups = build_setups_csv(proc, rng)
    orders = build_orders_csv(cfg, rng)
    staff = build_staff_calendar_csv(cfg, proc)
    storage = build_storage_csv(cfg)

    products.to_csv(out_dir / "products.csv", index=False)
    spaces.to_csv(out_dir / "spaces.csv", index=False)
    setups.to_csv(out_dir / "setups.csv", index=False)
    orders.to_csv(out_dir / "orders.csv", index=False)
    staff.to_csv(out_dir / "staff_calendar.csv", index=False)
    storage.to_csv(out_dir / "storage.csv", index=False)

    meta = {
        "suite": cfg.name,
        "seed": seed,
        "horizon_days": cfg.horizon_days,
        "n_orders": cfg.n_orders,
        "due_range": [cfg.min_due, cfg.max_due],
        "quantity_range": [cfg.quantity_min, cfg.quantity_max],
        "max_finished_storage": cfg.max_finished_storage,
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2))


# ----------------------------
# CLI
# ----------------------------

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("data/synth"), help="Output root directory")
    ap.add_argument("--suite", type=str, required=True, help="Suite name (e.g., S1)")
    ap.add_argument("--class_name", type=str, required=True, help="Class name (e.g., tight_storage)")
    ap.add_argument("--n", type=int, default=10, help="Number of instances to generate")
    ap.add_argument("--seed0", type=int, default=123, help="Base seed")
    args = ap.parse_args()

    # ---- Example process template (EDIT THIS to match your paper) ----
    proc = ProcessTemplate(
        stages=["S1", "S2", "S3"],
        skills=["A", "B", "C"],
        product_types=["P1", "P2", "P3"],
        operations_per_product={
            # Each tuple: (stage, skill, workers, duration_hours)
            "P1": [("S1", "A", 1, 4.0), ("S2", "B", 1, 6.0), ("S3", "C", 1, 3.0)],
            "P2": [("S1", "A", 1, 5.0), ("S2", "B", 2, 5.0), ("S3", "C", 1, 4.0)],
            "P3": [("S1", "A", 2, 4.0), ("S2", "B", 1, 7.0), ("S3", "C", 1, 2.0)],
        },
        stage_capacity={"S1": 2, "S2": 2, "S3": 1},
        setup_min=0.5,
        setup_max=2.0,
    )

    # ---- Example suite config (EDIT THIS per class) ----
    cfg = SuiteConfig(
        name=args.suite,
        horizon_days=30,
        n_instances_per_class=args.n,
        seeds=[args.seed0 + i for i in range(args.n)],
        n_orders=12,
        quantity_min=1,
        quantity_max=6,
        mix_product_probs={"P1": 0.4, "P2": 0.35, "P3": 0.25},
        min_due=8,
        max_due=25,
        base_staff_per_skill={"A": 4, "B": 4, "C": 3},
        vacation_days=[10, 11, 12],
        vacation_factor=0.6,
        max_finished_storage=20,
    )

    root = args.out / cfg.name / args.class_name
    for k in range(cfg.n_instances_per_class):
        inst_dir = root / f"I{k+1:03d}"
        seed = cfg.seeds[k % len(cfg.seeds)]
        write_instance(inst_dir, proc, cfg, seed)

    print(f"Generated {cfg.n_instances_per_class} instances under: {root}")


if __name__ == "__main__":
    main()