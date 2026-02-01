# sarteco-planner

Reference (open-source) implementation of a **multi-stage production planner** with:

- precedence constraints (routes per product/order),
- **dual resources**: specialized **spaces/stations** + **workforce skills**,
- **sequence-dependent setups** (per stage, triggered by product-type changes),
- realistic working calendars (8h/day, Mon–Fri) via a *compressed working-time* index,
- **finite storage** of finished items (max `M` units stored),
- optional **delivery dates per unit** (partial deliveries),
- objective: minimize contracted workforce-days (or fixed capacities if preferred).

This repo is designed to run locally or in **GitHub Codespaces** (devcontainer included).

## Quick start (local)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python -m planner.solve --data data/example --time_limit 20
```

Outputs are written to `outputs/`:
- `schedule.csv` (one row per operation)
- `deliveries.csv` (one row per produced unit)
- `kpis.json`

## Quick start (Codespaces)

1. Push this folder to GitHub.
2. Open it in Codespaces.
3. The devcontainer will install dependencies automatically.
4. Run:

```bash
python -m planner.solve --data data/example --time_limit 20
```

## Input data format (CSV)

Inside `--data <folder>` the solver expects:

- `products.csv`  
  `product_type,operation_id,op_index,stage,skill,workers,duration_hours`

- `orders.csv`  
  `order_id,product_type,quantity,due_day`

- `spaces.csv`  
  `stage,capacity`

- `setups.csv`  
  `stage,from_type,to_type,setup_hours`

- `staff_calendar.csv`  
  `day,skill,max_workers`  (already accounts for vacations / absences)

- `storage.csv`  
  `max_finished_storage`

### Notes
- Time is modeled in **working hours** only (Mon–Fri, 8h/day). Day `d` has hour slots
  `8*d .. 8*d+7`.
- If you need custom calendars (e.g., plant shutdowns), modify `planner/calendar.py`.

## License
MIT.
