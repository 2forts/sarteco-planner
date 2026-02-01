from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd


@dataclass(frozen=True)
class OperationTemplate:
    product_type: str
    operation_id: str
    op_index: int
    stage: str
    skill: str
    workers: int
    duration_hours: float


@dataclass(frozen=True)
class Order:
    order_id: str
    product_type: str
    quantity: int
    due_day: int


@dataclass(frozen=True)
class Instance:
    product_ops: Dict[str, List[OperationTemplate]]
    orders: List[Order]
    stage_capacity: Dict[str, int]
    setup_hours: Dict[Tuple[str, str, str], float]  # (stage, from_type, to_type) -> setup
    staff_max: Dict[Tuple[int, str], int]  # (day, skill) -> max workers
    max_storage: int


def load_instance(data_dir: Path) -> Instance:
    """Load a planning instance from CSV files.

    Required files are documented in README.md.
    """
    products = pd.read_csv(data_dir / "products.csv")
    orders_df = pd.read_csv(data_dir / "orders.csv")
    spaces = pd.read_csv(data_dir / "spaces.csv")
    setups = pd.read_csv(data_dir / "setups.csv")
    staff = pd.read_csv(data_dir / "staff_calendar.csv")
    storage = pd.read_csv(data_dir / "storage.csv")

    product_ops: Dict[str, List[OperationTemplate]] = {}
    for _, row in products.iterrows():
        ot = OperationTemplate(
            product_type=str(row["product_type"]),
            operation_id=str(row["operation_id"]),
            op_index=int(row["op_index"]),
            stage=str(row["stage"]),
            skill=str(row["skill"]),
            workers=int(row["workers"]),
            duration_hours=float(row["duration_hours"]),
        )
        product_ops.setdefault(ot.product_type, []).append(ot)
    for pt, ops in list(product_ops.items()):
        product_ops[pt] = sorted(ops, key=lambda x: x.op_index)

    orders: List[Order] = []
    for _, row in orders_df.iterrows():
        orders.append(
            Order(
                order_id=str(row["order_id"]),
                product_type=str(row["product_type"]),
                quantity=int(row["quantity"]),
                due_day=int(row["due_day"]),
            )
        )

    stage_capacity = {str(r["stage"]): int(r["capacity"]) for _, r in spaces.iterrows()}

    setup_hours: Dict[Tuple[str, str, str], float] = {}
    for _, r in setups.iterrows():
        setup_hours[(str(r["stage"]), str(r["from_type"]), str(r["to_type"]))] = float(r["setup_hours"])

    staff_max: Dict[Tuple[int, str], int] = {}
    for _, r in staff.iterrows():
        staff_max[(int(r["day"]), str(r["skill"]))] = int(r["max_workers"])

    max_storage = int(storage.iloc[0]["max_finished_storage"])

    return Instance(
        product_ops=product_ops,
        orders=orders,
        stage_capacity=stage_capacity,
        setup_hours=setup_hours,
        staff_max=staff_max,
        max_storage=max_storage,
    )
