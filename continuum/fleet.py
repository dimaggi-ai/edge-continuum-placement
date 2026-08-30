"""Fleet arithmetic: what an operator's tower fleet vs hub fleet actually buys.

The 'AI factory at every tower' pitch counts watts. This model counts what
the watts can schedule. A tower fleet's megawatts arrive in 1-2 GPU quanta
of L4-class silicon behind unstaffed air-cooled cabinets; a hub fleet's
megawatts arrive in H100-class pods behind staffed, liquid-capable sites.
The two fleets do not host the same workload classes, and per watt they do
not deliver the same schedulable compute.

Accounting note: the per-MW comparison charges each fleet its PROVISIONED
AI power envelope, because the envelope is what the operator builds and
pays for (feed, rectifiers, cooling, battery). Per *consumed* watt the
L4 silicon is actually competitive (3.4 vs 2.8 TFLOPS/W dense FP8) — the
tower fleet's problem is that the 2-GPU fabric quantum strands ~87% of
its envelope, and that its quanta host 6 of 12 workload classes. Both
powers are reported so the reader can take either view.

Dense FP8 throughput calibration (see REFERENCES.md):
  L4-class   72 W  ~242 TFLOPS dense FP8
  H100-class 700 W ~1979 TFLOPS dense FP8
"""

from dataclasses import dataclass

from .place import place
from .tiers import Tier, TOWER, HUB
from .workloads import LIBRARY

GPU_SPECS = {
    # name: (watts, dense FP8 TFLOPS)
    "l4": (72.0, 242.0),
    "h100": (700.0, 1979.0),
}


@dataclass(frozen=True)
class FleetTier:
    tier: Tier
    n_sites: int
    gpu: str                     # key into GPU_SPECS

    @property
    def gpus_per_site(self) -> int:
        watts, _ = GPU_SPECS[self.gpu]
        return min(self.tier.power_gpus(watts), self.tier.max_fabric_gpus)

    @property
    def total_gpus(self) -> int:
        return self.gpus_per_site * self.n_sites

    @property
    def total_ai_mw(self) -> float:
        return self.tier.ai_power_kw * self.n_sites / 1000.0

    @property
    def consumed_mw(self) -> float:
        """Power the fleet actually draws (GPU TDP x 1.35 node overhead)."""
        watts, _ = GPU_SPECS[self.gpu]
        return self.total_gpus * watts * 1.35 / 1e6

    @property
    def stranded_fraction(self) -> float:
        """Share of the provisioned envelope the fleet cannot use."""
        if self.total_ai_mw == 0:
            return 0.0
        return 1.0 - self.consumed_mw / self.total_ai_mw

    @property
    def total_pflops_fp8(self) -> float:
        _, tflops = GPU_SPECS[self.gpu]
        return self.total_gpus * tflops / 1000.0

    @property
    def pflops_per_mw(self) -> float:
        if self.total_ai_mw == 0:
            return 0.0
        return self.total_pflops_fp8 / self.total_ai_mw

    def hostable(self):
        """Workload classes this tier can host (VIABLE or COSTLY)."""
        names = []
        for w in LIBRARY:
            p = place(w)
            v = next(v for v in p.verdicts if v.tier == self.tier.name)
            if v.ok:
                names.append(w.name)
        return tuple(names)


# Default operator: a national mobile operator's footprint.
# ~30k macro sites, ~1 aggregation hub (C-RAN hotel / CO) per 100 sites.
TOWER_FLEET = FleetTier(TOWER, 30_000, "l4")
HUB_FLEET = FleetTier(HUB, 300, "h100")


@dataclass(frozen=True)
class Comparison:
    tower: FleetTier
    hub: FleetTier

    def summary(self) -> dict:
        t, h = self.tower, self.hub
        return {
            "tower_sites": t.n_sites,
            "tower_gpus": t.total_gpus,
            "tower_ai_mw": round(t.total_ai_mw, 1),
            "tower_consumed_mw": round(t.consumed_mw, 1),
            "tower_stranded_pct": round(t.stranded_fraction * 100, 0),
            "tower_pflops_fp8": round(t.total_pflops_fp8, 0),
            "tower_pflops_per_mw": round(t.pflops_per_mw, 0),
            "tower_scheduling_quantum_gpus": t.gpus_per_site,
            "tower_hostable": len(t.hostable()),
            "hub_sites": h.n_sites,
            "hub_gpus": h.total_gpus,
            "hub_ai_mw": round(h.total_ai_mw, 1),
            "hub_consumed_mw": round(h.consumed_mw, 1),
            "hub_stranded_pct": round(h.stranded_fraction * 100, 0),
            "hub_pflops_fp8": round(h.total_pflops_fp8, 0),
            "hub_pflops_per_mw": round(h.pflops_per_mw, 0),
            "hub_scheduling_quantum_gpus": h.gpus_per_site,
            "hub_hostable": len(h.hostable()),
            "hub_capability_per_mw_x": round(
                h.pflops_per_mw / t.pflops_per_mw, 1)
            if t.pflops_per_mw else float("inf"),
        }


def compare(tower: FleetTier = TOWER_FLEET,
            hub: FleetTier = HUB_FLEET) -> Comparison:
    return Comparison(tower, hub)
