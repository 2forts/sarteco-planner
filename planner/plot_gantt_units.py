from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


def plot_gantt_by_unit(schedule_csv: Path, out_png: Path, max_units: int | None = 25) -> None:
    df = pd.read_csv(schedule_csv)
    df = df.sort_values(["unit_id", "op_index"]).reset_index(drop=True)

    units = list(df["unit_id"].unique())
    if max_units is not None:
        units = units[:max_units]
        df = df[df["unit_id"].isin(units)]

    y_map = {u: i for i, u in enumerate(units)}
    height = 0.8

    fig_h = max(4, 0.45 * len(units) + 1.5)
    fig, ax = plt.subplots(figsize=(14, fig_h))

    for _, r in df.iterrows():
        u = r["unit_id"]
        y = y_map[u]
        start = float(r["start_hour"])
        end = float(r["end_hour"])
        dur = end - start
        if dur <= 0:
            continue
        ax.broken_barh([(start, dur)], (y - height / 2, height))

        label = f'{r["stage"]}'
        ax.text(start + dur * 0.01, y, label, va="center", ha="left", fontsize=7, clip_on=True)

    ax.set_yticks(list(y_map.values()))
    ax.set_yticklabels(list(y_map.keys()))
    ax.set_xlabel("Tiempo (horas laborables desde el inicio del horizonte)")
    ax.set_ylabel("Unidad")
    ax.set_title("Diagrama de Gantt por unidad (flujo de operaciones)")
    ax.grid(True, axis="x", linestyle="--", linewidth=0.5, alpha=0.5)

    fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=200)
    plt.close(fig)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--schedule", type=str, default="outputs/schedule.csv")
    p.add_argument("--out", type=str, default="outputs/gantt_units.png")
    p.add_argument("--max_units", type=int, default=25)
    args = p.parse_args()

    plot_gantt_by_unit(Path(args.schedule), Path(args.out), max_units=args.max_units)
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()