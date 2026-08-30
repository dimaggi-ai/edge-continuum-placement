"""Generate the study figures into figures/.

  efficiency_cliff.png   sync training efficiency vs distance: bandwidth
                         cannot buy back distance
  lossless_ceiling.png   how far lossless RDMA transport holds vs line rate
  placement_matrix.png   the workload x tier verdict matrix

Run: python3 run.py
"""

import pathlib

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from continuum import physics  # noqa: E402
from continuum.place import matrix  # noqa: E402
from continuum.tiers import LADDER  # noqa: E402
from continuum.workloads import LIBRARY  # noqa: E402

FIGDIR = pathlib.Path(__file__).parent / "figures"
FIGDIR.mkdir(exist_ok=True)

INK = "#1a1a2e"
plt.rcParams.update({
    "figure.dpi": 150, "savefig.dpi": 150, "font.size": 9,
    "axes.edgecolor": INK, "axes.labelcolor": INK,
    "text.color": INK, "xtick.color": INK, "ytick.color": INK,
    "axes.spines.top": False, "axes.spines.right": False,
})


def efficiency_cliff():
    km = np.logspace(-1, 3.7, 300)
    fig, ax = plt.subplots(figsize=(7.2, 4.4))
    # Payload sized so the 400G bandwidth term is PARTIALLY exposed
    # (~0.6 ms past the compute budget) while 1600G hides fully — the
    # comparison is genuine, not identical-by-construction.
    base = physics.CollectiveScenario(
        n_ranks=16, payload_gb=5.35, inter_site_gbps=400.0, compute_ms=200.0)
    wide = physics.CollectiveScenario(
        n_ranks=16, payload_gb=5.35, inter_site_gbps=1600.0, compute_ms=200.0)
    ax.plot(km, [physics.sync_step_efficiency(base, k) for k in km],
            color="#c0392b", lw=3, label="400 Gbps inter-site")
    ax.plot(km, [physics.sync_step_efficiency(wide, k) for k in km],
            color="#2980b9", lw=1.4, ls="--",
            label="1600 Gbps inter-site (4x)")
    ax.axvline(40.0, color="#2c3e50", ls="--", lw=1)
    ax.text(40 * 1.12, 0.42, "metro boundary (~40 km):\nlast stop for "
            "lossless fabrics", fontsize=8, color="#2c3e50")
    e300 = physics.sync_step_efficiency(base, 300)
    ax.annotate(
        "4x the bandwidth moves the curve by <1%:\nthe exposed term is "
        "serial hop latency,\nwhich only distance controls\n"
        "(Corning 2026, in simulation: <=0.66% from 2x)",
        xy=(300, e300), xytext=(1.3, 0.62), fontsize=8,
        arrowprops=dict(arrowstyle="->", color="#7f8c8d", lw=1))
    ax.set_xscale("log")
    ax.set_xlabel("inter-site distance (km, log scale)")
    ax.set_ylabel("synchronous step efficiency")
    ax.set_ylim(0.3, 1.02)
    ax.set_title("Bandwidth cannot buy back distance: the two curves are "
                 "indistinguishable", fontsize=10)
    ax.legend(frameon=False, loc="lower left")
    fig.text(0.99, 0.01,
             "ring all-reduce, 16 ranks, 5.35 GB payload, 200 ms compute; "
             "only the bandwidth term overlaps compute",
             fontsize=7, color="#7f8c8d", ha="right")
    fig.tight_layout()
    fig.savefig(FIGDIR / "efficiency_cliff.png")
    plt.close(fig)


def lossless_ceiling():
    rates = np.linspace(50, 1600, 200)
    fig, ax = plt.subplots(figsize=(7.2, 4.4))
    for buf, color in ((32, "#95a5a6"), (64, "#2980b9"), (256, "#27ae60")):
        km = [physics.pfc_max_lossless_km(r, float(buf)) for r in rates]
        ax.plot(rates, km, color=color, lw=2,
                label=f"{buf} MB/port PFC headroom")
    ib = [physics.ib_credit_max_km(r) for r in rates]
    ax.plot(rates, ib, color="#8e44ad", lw=2, ls=":",
            label="native IB credit loop (128 KB/VL)")
    ax.axhline(40, color="#2c3e50", ls="--", lw=1)
    ax.text(1580, 44, "metro DWDM reach (~40 km)", fontsize=8,
            ha="right", color="#2c3e50")
    # Bifrost's testbed at 100G / 80 km reserved ~9.5 MB of headroom
    # (~2x one-way BDP); mark where 64 MB actually runs out at 100G.
    ax.scatter([100], [physics.pfc_max_lossless_km(100, 64.0)], zorder=5,
               color="#2980b9", s=28)
    ax.set_yscale("log")
    ax.set_xlabel("line rate (Gbps)")
    ax.set_ylabel("max lossless distance (km, log scale)")
    ax.set_title("The lossless envelope shrinks as line rate grows: "
                 "RDMA stays inside the PoP or the metro", fontsize=10)
    ax.legend(frameon=False, loc="upper right", fontsize=8)
    fig.tight_layout()
    fig.savefig(FIGDIR / "lossless_ceiling.png")
    plt.close(fig)


def placement_matrix():
    placements = matrix(LIBRARY)
    tiers = [t.name for t in LADDER]
    status_color = {"VIABLE": "#27ae60", "COSTLY": "#f39c12",
                    "BLOCKED": "#c0392b"}
    fig, ax = plt.subplots(figsize=(7.6, 5.6))
    for y, p in enumerate(placements):
        for x, v in enumerate(p.verdicts):
            rec = p.recommended == v.tier
            ax.add_patch(plt.Rectangle(
                (x, y), 0.94, 0.9, color=status_color[v.status],
                alpha=1.0 if rec else 0.45))
            label = {"VIABLE": "OK", "COSTLY": "$",
                     "BLOCKED": v.gate[:1].upper()}[v.status]
            if rec:
                label = "REC"
            ax.text(x + 0.47, y + 0.45, label, ha="center", va="center",
                    fontsize=8, color="white", fontweight="bold")
    ax.set_xlim(0, len(tiers))
    ax.set_ylim(len(placements), 0)
    ax.set_xticks([i + 0.47 for i in range(len(tiers))])
    ax.set_xticklabels(tiers, fontsize=9)
    ax.set_yticks([i + 0.45 for i in range(len(placements))])
    ax.set_yticklabels([p.workload for p in placements], fontsize=9)
    ax.tick_params(length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_title("Placement verdicts. REC = recommended tier; "
                 "$ = viable but costly (backhaul);\nblocked cells name "
                 "their gate: F fabric, P power, L latency, G gravity",
                 fontsize=10)
    fig.tight_layout()
    fig.savefig(FIGDIR / "placement_matrix.png")
    plt.close(fig)


if __name__ == "__main__":
    efficiency_cliff()
    lossless_ceiling()
    placement_matrix()
    print(f"figures written to {FIGDIR}/")
