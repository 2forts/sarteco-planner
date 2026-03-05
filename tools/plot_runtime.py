#!/usr/bin/env python3

import pandas as pd
import matplotlib.pyplot as plt

# cargar resultados
df = pd.read_csv("results/sarteco_synth_v1/kpis.csv")

# media de runtime por grupo
runtime = (
    df.groupby(["meta_scale", "meta_scenario"])["run_elapsed_s"]
    .mean()
    .reset_index()
)

# orden de tamaños
scale_order = ["small", "medium", "large"]
runtime["meta_scale"] = pd.Categorical(runtime["meta_scale"], scale_order)

# pivot para graficar
pivot = runtime.pivot(index="meta_scale", columns="meta_scenario", values="run_elapsed_s")

# figura
plt.figure(figsize=(6,4))

for scenario in pivot.columns:
    plt.plot(pivot.index, pivot[scenario], marker="o", label=scenario)

plt.xlabel("Instance size")
plt.ylabel("Average runtime (seconds)")
plt.title("Solver runtime by instance size and scenario")
plt.grid(True)
plt.legend()

plt.tight_layout()
plt.savefig("results/sarteco_synth_v1/runtime_plot.pdf")
plt.savefig("results/sarteco_synth_v1/runtime_plot.png")

print("Figura guardada en results/sarteco_synth_v1/runtime_plot.pdf")
