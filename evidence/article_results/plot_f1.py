"""Figure 10 of the paper: mean F1-macro without and with Monolith preparation.

Usage: python plot_f1.py [folder]   (defaults to this script's folder)
Reads extended_metrics.json and writes experimento-f1.png next to it.
"""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

folder = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent
m = json.load(open(folder / "extended_metrics.json", encoding="utf-8"))
combos = [("churn", "kNN (k=5)", "Churn\nkNN"), ("churn", "Random Forest", "Churn\nRandom Forest"),
          ("wine", "kNN (k=5)", "Wine\nkNN"), ("wine", "Random Forest", "Wine\nRandom Forest")]
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8, "axes.spines.top": False,
                     "axes.spines.right": False, "axes.edgecolor": "#8A96A3", "axes.linewidth": 0.6,
                     "xtick.color": "#3A4550", "ytick.color": "#3A4550"})
fig, ax = plt.subplots(figsize=(3.45, 2.35), dpi=300)
w = 0.36
for k, (ds, model, label) in enumerate(combos):
    for j, (cond, color, name) in enumerate((("minimum_manual", "#B3BDC7", "Sem Monolith"),
                                             ("monolith", "#035C96", "Com Monolith"))):
        mean, sd = m[f"{ds}|{cond}|{model}"]["metrics"]["f1_macro"]
        x = k + (j - 0.5) * (w + 0.03)
        ax.bar(x, mean * 100, w, color=color, label=name if k == 0 else None, zorder=2)
        ax.errorbar(x, mean * 100, yerr=sd * 100, color="#1B1B1B", lw=0.6, capsize=1.6, capthick=0.6, zorder=3)
        ax.text(x, mean * 100 + sd * 100 + 1.5, f"{mean*100:.1f}".replace(".", ","), ha="center", va="bottom",
                fontsize=6.3, color="#1B1B1B")
ax.set_xticks(range(4))
ax.set_xticklabels([c[2] for c in combos], fontsize=7)
ax.set_ylim(0, 108)
ax.set_yticks([0, 25, 50, 75, 100])
ax.set_ylabel("F1-macro (%)", fontsize=7.5)
ax.yaxis.grid(True, color="#E3E8ED", lw=0.5, zorder=0)
ax.tick_params(axis="both", length=0, pad=3)
ax.legend(frameon=False, fontsize=7, loc="upper left", ncol=2, bbox_to_anchor=(0, 1.08), handlelength=1.2,
          columnspacing=1.2)
fig.tight_layout(pad=0.4)
fig.savefig(folder / "experimento-f1.png", dpi=300)
print("saved", folder / "experimento-f1.png")
