import json
from pathlib import Path
import pandas as pd

def main(out_dir="outputs"):
    out = Path(out_dir)
    sched = pd.read_csv(out / "schedule.csv")
    deliv = pd.read_csv(out / "deliveries.csv")
    work = pd.read_csv(out / "workforce.csv")

    H = int(max(deliv["due_day"].max(), deliv["delivery_day"].max()))
    inv=[]
    for day in range(H+1):
        comp = (deliv["completion_day"] <= day).sum()
        dele = (deliv["delivery_day"] <= day).sum()
        inv.append(int(comp - dele))
    max_inv = max(inv)
    max_inv_day = inv.index(max_inv)

    workers_days = int(work["hired_workers"].sum())

    # Utilization per machine (day-granular, sum durations)
    util = (
        sched.groupby("machine")["duration_days"]
        .sum()
        .sort_values(ascending=False)
        .to_dict()
    )

    report = {
        "workers_days": workers_days,
        "max_inventory": max_inv,
        "max_inventory_day": max_inv_day,
        "machines_load_days": util,
        "num_units": int(deliv.shape[0]),
        "num_ops": int(sched.shape[0]),
    }

    (out / "analysis.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="outputs")
    args = p.parse_args()
    main(args.out)