
# sarteco-planner

Reference **open‑source implementation** of a **generic multi‑stage production planning problem** with realistic industrial constraints.

The solver computes a **detailed production calendar** (start/end of every operation for every unit), integrating **production, workforce, setup, storage, and delivery decisions** in a single model.

This repository accompanies an academic paper (SARTECO / journal‑ready) and is designed to be **reproducible**, **extensible**, and runnable both locally and in **GitHub Codespaces**.

---

# Problem features

The implemented planner supports:

- **Multi-stage production routes** defined per product type
- **Dual renewable resources**
  - specialized **production spaces / stations**
  - **workforce skills** with calendar‑based availability
- **Sequence‑dependent setup times** depending on product transitions
- **Realistic working calendars**
  - 8 hours per working day
  - Monday–Friday working schedule
  - compressed working-time representation (no explicit weekends)
- **Finite storage capacity** for finished items
- **Unit-level deliveries**
  - partial deliveries allowed
  - configurable delivery window parameter
- **Optimization objective**
  - minimize total **contracted workforce-days**
- Exact constraint‑based solution using **OR‑Tools CP‑SAT**

The system produces **operational production schedules** that respect all resource, temporal and logistics constraints.

---

# Repository structure

```
sarteco-planner/
│
├── planner/                     # Core planning model
│   ├── solve.py                 # Main solver entry point
│   ├── io.py                    # CSV instance loader
│   ├── work_calendar.py         # Working-time calendar utilities
│   ├── analyze.py               # KPI analysis tools
│   ├── plot_gantt.py            # Machine Gantt visualization
│   ├── plot_gantt_units.py      # Unit-level Gantt visualization
│   ├── __init__.py
│   └── __main__.py
│
├── tools/
│   ├── generate_instances.py    # Synthetic instance generator
│   ├── run_benchmark.py         # Benchmark execution script
│   └── sensitivity_analysis.py  # Parameter sensitivity experiments
│
├── data/
│   ├── example/                 # Minimal example instance
│   └── benchmark/               # Generated benchmark suites
│
├── results/                     # Experiment outputs (generated)
│
├── requirements.txt
├── README.md
└── .devcontainer/               # GitHub Codespaces configuration
```

---

# Quick start (local)

Create a Python environment and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run the solver on the example instance:

```bash
python -m planner.solve --data data/example --time_limit 20
```

Outputs are written to `outputs/`:

- `schedule.csv` — operation schedule
- `deliveries.csv` — delivery plan
- `workforce.csv` — workforce utilization
- `kpis.json` — summary statistics

---

# Quick start (GitHub Codespaces)

1. Push this repository to GitHub.
2. Open it in **GitHub Codespaces**.
3. The devcontainer installs all dependencies automatically.
4. Run:

```bash
python -m planner.solve --data data/example --time_limit 20
```

---

# Command-line options

```bash
python -m planner.solve   --data data/example   --out outputs   --time_limit 300   --ship_window 2
```

Parameters:

| Parameter | Description |
|-----------|-------------|
| `--data` | Directory containing CSV instance files |
| `--out` | Output directory |
| `--time_limit` | Maximum solver time (seconds) |
| `--ship_window` | Delivery window size in days |

---

# Input data format (CSV)

The planner reads instances defined through structured CSV files.

## products.csv

Defines the production route for each product type.

```
product_type,operation_id,op_index,stage,skill,workers,duration_hours
```

## orders.csv

Defines demand and delivery deadlines.

```
order_id,product_type,quantity,due_day
```

## spaces.csv

Defines capacity per production stage.

```
stage,capacity
```

## setups.csv

Defines sequence‑dependent setup times.

```
stage,from_type,to_type,setup_hours
```

## staff_calendar.csv

Defines workforce availability per skill and day.

```
day,skill,max_workers
```

## storage.csv

Defines maximum storage capacity for finished items.

```
max_finished_storage
```

---

# Output analysis

Compute KPIs and aggregated metrics:

```bash
python -m planner.analyze --out outputs
```

---

# Gantt diagrams

Machine-level schedule:

```bash
python -m planner.plot_gantt   --schedule outputs/schedule.csv   --out outputs/gantt_machine.png
```

Unit-level schedule:

```bash
python -m planner.plot_gantt_units   --out outputs/gantt_units.png   --max_units 20
```

These diagrams provide visual insight into:

- operation sequencing
- resource utilization
- production bottlenecks

---

# Synthetic benchmark generation

The repository includes tools for generating synthetic planning instances used in the accompanying paper.

Generate benchmark instances:

```bash
python tools/generate_instances.py
```

This produces a benchmark suite with multiple scales and scenarios.

Typical benchmark configuration:

| Scale | Orders |
|------|------|
| small | ~10 |
| medium | ~20 |
| large | ~40 |

Scenarios include:

- baseline
- tight storage capacity
- tight delivery windows

---

# Running the benchmark

Solve all generated instances automatically:

```bash
python tools/run_benchmark.py   --suite data/benchmark/sarteco_synth_v1   --out results/sarteco_synth_v1   --time_limit 300   --ship_window 2   --kpi_csv results/sarteco_synth_v1/kpis.csv
```

The script executes all instances and records:

- solver runtime
- instance size
- number of operations
- planning horizon
- solver status

---

# Sensitivity analysis

To reproduce the sensitivity experiments described in the paper:

```bash
python tools/sensitivity_analysis.py
```

This script evaluates the impact of:

- delivery window size
- storage capacity
- workforce availability

on computational performance and scheduling behavior.

---

# Modeling notes

- Time is discretized in **working days** (8h/day).
- Workforce capacity is modeled per **skill and day**.
- Inventory constraints are enforced through **daily storage limits**.
- Setup times are triggered when consecutive operations process **different product types**.

The model is implemented using **OR‑Tools CP‑SAT**, combining constraint programming and SAT-based optimization techniques.

---

# Reproducibility

The repository includes:

- full solver implementation
- instance generator
- benchmark scripts
- analysis tools

allowing all computational experiments from the associated research paper to be **fully reproducible**.

---

# License

MIT License.
