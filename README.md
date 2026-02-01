# sarteco-planner

Reference **open-source implementation** of a **generic multi-stage production planning problem** with realistic industrial constraints.

The solver computes a **detailed production calendar** (start/end of every operation for every unit), integrating **production, workforce, setup, storage, and delivery decisions** in a single model.

This repository accompanies an academic paper (SARTECO / journal-ready) and is designed to be **reproducible**, **extensible**, and runnable both locally and in **GitHub Codespaces**.

---

## Problem features

The implemented planner supports:

- **Multi-stage routes** (precedence constraints) defined per product type  
- **Dual renewable resources**:
  - specialized **spaces / stations** (parallel machines per stage),
  - **workforce skills**, with daily availability and vacations  
- **Sequence-dependent setup times**, per stage and product-type change  
- **Realistic working calendars**:
  - 8 hours/day, Monday–Friday
  - compressed *working-time* index (no explicit weekends)  
- **Finite storage capacity** for finished items (maximum `M` units)  
- **Unit-level delivery decisions**:
  - partial deliveries allowed,
  - delivery windows controlled via a `ship_window` parameter  
- **Optimization objective**:
  - minimize total **contracted workforce-days**  
- Exact constraint-based solution using **OR-Tools CP-SAT** (open source)

---

## Repository structure

```
sarteco-planner/
├── planner/
│   ├── solve.py
│   ├── io.py
│   ├── work_calendar.py
│   ├── analyze.py
│   ├── plot_gantt.py
│   ├── plot_gantt_units.py
│   ├── __init__.py
│   └── __main__.py
├── data/
│   └── example/
├── outputs/
├── requirements.txt
├── README.md
└── .devcontainer/
```

---

## Quick start (local)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python -m planner.solve --data data/example --time_limit 20
```

Outputs are written to `outputs/`:

- `schedule.csv`
- `deliveries.csv`
- `workforce.csv`
- `kpis.json`

---

## Quick start (GitHub Codespaces)

1. Push this repository to GitHub.
2. Open it in **GitHub Codespaces**.
3. The devcontainer installs all dependencies automatically.
4. Run:

```bash
python -m planner.solve --data data/example --time_limit 20
```

---

## Command-line options

```bash
python -m planner.solve   --data data/example   --out outputs   --time_limit 20   --ship_window 2
```

---

## Input data format (CSV)

### `products.csv`
```
product_type,operation_id,op_index,stage,skill,workers,duration_hours
```

### `orders.csv`
```
order_id,product_type,quantity,due_day
```

### `spaces.csv`
```
stage,capacity
```

### `setups.csv`
```
stage,from_type,to_type,setup_hours
```

### `staff_calendar.csv`
```
day,skill,max_workers
```

### `storage.csv`
```
max_finished_storage
```

---

## Output analysis

```bash
python -m planner.analyze --out outputs
```

---

## Gantt diagrams

```bash
python -m planner.plot_gantt --schedule outputs/schedule.csv --out outputs/gantt_machine.png
python -m planner.plot_gantt_units --out outputs/gantt_units.png --max_units 20
```

---

## Modeling notes

- Time is discretized in **working days** (8h/day).
- Workforce availability is modeled at day granularity.
- Inventory constraints are enforced at daily checkpoints.

---

## License

MIT License.