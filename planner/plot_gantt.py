from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


def plot_gantt_by_machine(schedule_csv: Path, out_png: Path, max_machines: int | None = None) -> None:
    df = pd.read_csv(schedule_csv)

    # Basic cleaning / ordering
    df = df.sort_values(["machine", "start_hour", "end_hour", "unit_id", "op_index"]).reset_index(drop=True)

    machines = list(df["machine"].dropna().unique())
    if max_machines is not None:
        machines = machines[:max_machines]
        df = df[df["machine"].isin(machines)]

    # Map machine -> y position
    y_map = {m: i for i, m in enumerate(machines)}
    height = 0.8

    fig_h = max(4, 0.45 * len(machines) + 1.5)
    fig, ax = plt.subplots(figsize=(14, fig_h))

    # Draw one bar per operation
    for _, r in df.iterrows():
        m = r["machine"]
        if m not in y_map:
            continue
        y = y_map[m]
        start = float(r["start_hour"])
        end = float(r["end_hour"])
        dur = end - start
        if dur <= 0:
            continue
        ax.broken_barh([(start, dur)], (y - height / 2, height))

        # Label inside the bar (compact)
        label = f'{r["unit_id"]}:{r["operation_id"]}'
        ax.text(start + dur * 0.01, y, label, va="center", ha="left", fontsize=7, clip_on=True)

    ax.set_yticks(list(y_map.values()))
    ax.set_yticklabels(list(y_map.keys()))
    ax.set_xlabel("Tiempo (horas laborables desde el inicio del horizonte)")
    ax.set_ylabel("Máquina / espacio")
    ax.set_title("Diagrama de Gantt por máquina/espacio")
    ax.grid(True, axis="x", linestyle="--", linewidth=0.5, alpha=0.5)

    # Tight layout and save
    fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=200)
    plt.close(fig)


def main():
    p = argparse.ArgumentParser(description="Plot Gantt charts from schedule.csv")
    p.add_argument("--schedule", type=str, default="outputs/schedule.csv", help="Path to schedule.csv")
    p.add_argument("--out", type=str, default="outputs/gantt_machine.png", help="Output PNG path")
    p.add_argument("--max_machines", type=int, default=None, help="Limit number of machines plotted")
    args = p.parse_args()

    plot_gantt_by_machine(Path(args.schedule), Path(args.out), max_machines=args.max_machines)
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()