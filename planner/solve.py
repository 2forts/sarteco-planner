from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd
from ortools.sat.python import cp_model

from .work_calendar import HOURS_PER_DAY, day_to_end_hour, day_to_start_hour, hours_to_days
from .io import Instance, Order, OperationTemplate, load_instance

import logging
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
log = logging.getLogger(__name__)

@dataclass
class UnitOp:
    unit_id: str
    order_id: str
    product_type: str
    op_index: int
    operation_id: str
    stage: str
    skill: str
    workers: int
    duration_days: int


def _setup_days(inst: Instance, stage: str, from_type: str, to_type: str) -> int:
    if from_type == to_type:
        return 0
    hours = inst.setup_hours.get((stage, from_type, to_type), 0.0)
    return hours_to_days(hours)


def solve(data_dir: Path, out_dir: Path, time_limit_s: int = 20, ship_window: int = 2) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    inst = load_instance(data_dir)

    # Expand orders into unit-level jobs
    units: List[str] = []
    unit_to_order: Dict[str, Order] = {}
    unit_product: Dict[str, str] = {}
    unit_due: Dict[str, int] = {}
    for o in inst.orders:
        for q in range(o.quantity):
            uid = f"{o.order_id}__{q+1:03d}"
            units.append(uid)
            unit_to_order[uid] = o
            unit_product[uid] = o.product_type
            unit_due[uid] = o.due_day

    # Build operations per unit
    ops: List[UnitOp] = []
    for uid in units:
        pt = unit_product[uid]
        if pt not in inst.product_ops:
            raise ValueError(f"No operations defined for product_type={pt}")
        for tpl in inst.product_ops[pt]:
            ops.append(
                UnitOp(
                    unit_id=uid,
                    order_id=unit_to_order[uid].order_id,
                    product_type=pt,
                    op_index=tpl.op_index,
                    operation_id=tpl.operation_id,
                    stage=tpl.stage,
                    skill=tpl.skill,
                    workers=tpl.workers,
                    duration_days=hours_to_days(tpl.duration_hours),
                )
            )

    # Planning horizon (days)
    latest_due = max(unit_due.values()) if unit_due else 0
    # Add a small slack to allow early completion + storage
    horizon_days = latest_due + 10

    model = cp_model.CpModel()

    # Stage machines (capacity handled by parallel identical machines)
    stage_machines: Dict[str, List[str]] = {}
    for stage, cap in inst.stage_capacity.items():
        if cap <= 0:
            raise ValueError(f"Invalid capacity for stage {stage}: {cap}")
        stage_machines[stage] = [f"{stage}__m{i}" for i in range(cap)]

    # Create vars per operation
    start: Dict[int, cp_model.IntVar] = {}
    end: Dict[int, cp_model.IntVar] = {}
    interval: Dict[Tuple[int, str], cp_model.IntervalVar] = {}  # (op_idx, machine) -> optional interval
    assign: Dict[Tuple[int, str], cp_model.BoolVar] = {}

    for i, op in enumerate(ops):
        start[i] = model.new_int_var(0, horizon_days, f"start_{i}")
        end[i] = model.new_int_var(0, horizon_days, f"end_{i}")
        model.add(end[i] == start[i] + op.duration_days)

        machines = stage_machines.get(op.stage)
        if not machines:
            raise ValueError(f"Stage '{op.stage}' not present in spaces.csv")

        # One machine assignment
        a_bools = []
        for m in machines:
            b = model.new_bool_var(f"assign_{i}_{m}")
            assign[(i, m)] = b
            a_bools.append(b)
            interval[(i, m)] = model.new_optional_interval_var(start[i], op.duration_days, end[i], b, f"int_{i}_{m}")
        model.add(sum(a_bools) == 1)

    # NoOverlap per machine
    for stage, machines in stage_machines.items():
        for m in machines:
            ints = [interval[(i, m)] for i, op in enumerate(ops) if op.stage == stage]
            model.add_no_overlap(ints)

    # Precedence within each unit (by op_index)
    # Collect operation indices by unit sorted
    unit_ops: Dict[str, List[int]] = {}
    for i, op in enumerate(ops):
        unit_ops.setdefault(op.unit_id, []).append(i)
    for uid, idxs in unit_ops.items():
        idxs_sorted = sorted(idxs, key=lambda j: ops[j].op_index)
        for j in range(len(idxs_sorted) - 1):
            model.add(start[idxs_sorted[j + 1]] >= end[idxs_sorted[j]])

    # Sequence-dependent setups (pairwise, per machine)
    # If op i is before j on the same machine, enforce start_j >= end_i + setup(stage, type_i, type_j)
    big_m = horizon_days + 50
    for stage, machines in stage_machines.items():
        stage_op_idxs = [i for i, op in enumerate(ops) if op.stage == stage]
        for m in machines:
            for a in range(len(stage_op_idxs)):
                i = stage_op_idxs[a]
                for b in range(a + 1, len(stage_op_idxs)):
                    j = stage_op_idxs[b]
                    # order var: i before j on machine m
                    o_ij = model.new_bool_var(f"before_{i}_{j}_{m}")
                    o_ji = model.new_bool_var(f"before_{j}_{i}_{m}")

                    # Order variables can only be true if BOTH operations are assigned to this machine.
                    model.add(o_ij <= assign[(i, m)])
                    model.add(o_ij <= assign[(j, m)])
                    model.add(o_ji <= assign[(i, m)])
                    model.add(o_ji <= assign[(j, m)])
                    # If both assigned to m, exactly one of them must be true
                    model.add(o_ij + o_ji == 1).only_enforce_if([assign[(i, m)], assign[(j, m)]])

                    setup_ij = _setup_days(inst, stage, ops[i].product_type, ops[j].product_type)
                    setup_ji = _setup_days(inst, stage, ops[j].product_type, ops[i].product_type)

                    model.add(start[j] >= end[i] + setup_ij - big_m * (1 - o_ij))
                    model.add(start[i] >= end[j] + setup_ji - big_m * (1 - o_ji))

    # Workforce capacity by day (aggregated per skill)
    skills = sorted({op.skill for op in ops})
    H: Dict[Tuple[str, int], cp_model.IntVar] = {}
    for r in skills:
        for d in range(horizon_days + 1):
            maxw = inst.staff_max.get((d, r), 0)
            H[(r, d)] = model.new_int_var(0, maxw, f"H_{r}_{d}")

    # For each day and skill: sum workers of operations active that day <= H[r,d]
    # Day-granular (operation occupies whole days). Active on day d iff start <= d < end.
    for r in skills:
        for d in range(horizon_days + 1):
            demands = []
            actives = []
            for i, op in enumerate(ops):
                if op.skill != r:
                    continue
                a = model.new_bool_var(f"active_{i}_{d}")
                # a => start <= d and end > d
                model.add(start[i] <= d).only_enforce_if(a)
                model.add(end[i] > d).only_enforce_if(a)
                # not a => start > d OR end <= d (we relax with two implications to keep it linear-ish)
                # This is a common CP-SAT pattern: enforce sufficient conditions for a=1;
                # it may allow a=0 even if active, so we add the reverse with a helper.
                b1 = model.new_bool_var(f"b1_{i}_{d}")
                b2 = model.new_bool_var(f"b2_{i}_{d}")
                model.add(start[i] <= d).only_enforce_if(b1)
                model.add(start[i] > d).only_enforce_if(b1.Not())
                model.add(end[i] > d).only_enforce_if(b2)
                model.add(end[i] <= d).only_enforce_if(b2.Not())
                # If both b1 and b2 are true, the op is active, so a must be 1
                model.add(a == 1).only_enforce_if([b1, b2])

                demands.append(op.workers)
                actives.append(a)
            if actives:
                model.add(sum(demands[i] * actives[i] for i in range(len(actives))) <= H[(r, d)])

    # Delivery dates (partial deliveries) + storage capacity
    # completion day of each unit: end of its last operation
    completion: Dict[str, cp_model.IntVar] = {}
    delivery: Dict[str, cp_model.IntVar] = {}
    for uid, idxs in unit_ops.items():
        last_i = max(idxs, key=lambda j: ops[j].op_index)
        completion[uid] = end[last_i]
        earliest = max(0, unit_due[uid] - ship_window) #ship_window defines a previous temporal limit
        delivery[uid] = model.new_int_var(earliest, unit_due[uid], f"deliv_{uid}")
        model.add(delivery[uid] >= completion[uid])

    # Inventory constraint per day (event discretization on days)
    for d in range(horizon_days + 1):
        comp_bools = []
        del_bools = []
        for uid in units:
            bc = model.new_bool_var(f"compBy_{uid}_{d}")
            bd = model.new_bool_var(f"delBy_{uid}_{d}")
            model.add(completion[uid] <= d).only_enforce_if(bc)
            model.add(completion[uid] > d).only_enforce_if(bc.Not())
            model.add(delivery[uid] <= d).only_enforce_if(bd)
            model.add(delivery[uid] > d).only_enforce_if(bd.Not())
            comp_bools.append(bc)
            del_bools.append(bd)
        inv = model.new_int_var(0, inst.max_storage + len(units), f"inv_{d}")
        model.add(inv == sum(comp_bools) - sum(del_bools))
        model.add(inv <= inst.max_storage)

    # Objective: minimize total hired workers-days
    model.minimize(sum(H.values()))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit_s)
    solver.parameters.num_search_workers = 8

    status = solver.solve(model)

    kpis = {
        "status": solver.status_name(status),
        "objective": solver.objective_value if status in (cp_model.OPTIMAL, cp_model.FEASIBLE) else None,
        "time_limit_s": time_limit_s,
        "horizon_days": horizon_days,
        "num_units": len(units),
        "num_operations": len(ops),
    }

    (out_dir / "kpis.json").write_text(json.dumps(kpis, indent=2), encoding="utf-8")

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return kpis

    # Export schedule
    sched_rows = []
    for i, op in enumerate(ops):
        st_d = int(solver.value(start[i]))
        en_d = int(solver.value(end[i]))
        chosen = None
        for m in stage_machines[op.stage]:
            if solver.value(assign[(i, m)]) == 1:
                chosen = m
                break
        sched_rows.append(
            {
                "unit_id": op.unit_id,
                "order_id": op.order_id,
                "product_type": op.product_type,
                "op_index": op.op_index,
                "operation_id": op.operation_id,
                "stage": op.stage,
                "machine": chosen,
                "skill": op.skill,
                "workers": op.workers,
                "duration_days": op.duration_days,
                "start_day": st_d,
                "end_day": en_d,
                "start_hour": day_to_start_hour(st_d),
                "end_hour": day_to_end_hour(en_d),
            }
        )

    schedule_df = pd.DataFrame(sched_rows).sort_values(["unit_id", "op_index"])
    schedule_df.to_csv(out_dir / "schedule.csv", index=False)

    # Export deliveries
    del_rows = []
    for uid in units:
        del_rows.append(
            {
                "unit_id": uid,
                "order_id": unit_to_order[uid].order_id,
                "product_type": unit_product[uid],
                "completion_day": int(solver.value(completion[uid])),
                "delivery_day": int(solver.value(delivery[uid])),
                "due_day": unit_due[uid],
            }
        )
    pd.DataFrame(del_rows).sort_values(["order_id", "unit_id"]).to_csv(out_dir / "deliveries.csv", index=False)

    # Export workforce plan
    w_rows = []
    for (skill, day), var in H.items():
        w_rows.append(
            {
                "day": day,
                "skill": skill,
                "hired_workers": int(solver.value(var)),
                "max_workers": int(inst.staff_max.get((day, skill), 0)),
            }
        )
    pd.DataFrame(w_rows).sort_values(["day", "skill"]).to_csv(out_dir / "workforce.csv", index=False)
    return kpis

if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Solve a planning instance")
    p.add_argument("--data", type=str, required=True)
    p.add_argument("--out", type=str, default="outputs")
    p.add_argument("--time_limit", type=int, default=20)
    p.add_argument("--ship_window", type=int, default=20)
    args = p.parse_args()
    log.info("Loading data from %s", args.data)

    log.info("Solving (time limit = %ss)...", args.time_limit)
    kpis = solve(Path(args.data), Path(args.out), time_limit_s=args.time_limit, ship_window = args.ship_window)
    log.info("Status: %s", kpis["status"])
    log.info("Objective (workers-days): %s", kpis["objective"])
    log.info("Wrote outputs to %s", args.out)