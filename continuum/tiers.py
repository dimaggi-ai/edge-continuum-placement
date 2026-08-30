"""Site-tier envelopes of the edge<->neocloud compute continuum.

Four tiers, each defined by what its physical envelope actually permits —
power headroom, cooling class, fabric reach, and distance to the user.
The numbers are deliberately explicit and overridable: they are the
argument, not decoration. Sources for the defaults are in REFERENCES.md.
"""

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class Tier:
    name: str
    # Power available for AI compute after the radio/site loads are served.
    ai_power_kw: float
    # 'air' or 'liquid'. Air is exhausted around ~50 kW/rack; a tower
    # cabinet has no CDU, no staff, and freeze/leak consequences.
    cooling: str
    # Largest GPU pool one scheduler can treat as a single fabric here.
    max_fabric_gpus: int
    # Heaviest single accelerator the envelope can host (W TDP).
    max_gpu_watts: float
    # Scale-out fabric available inside the site.
    fabric: str                 # 'none' | 'pod' | 'full'
    # Typical one-way distance to the served user, km.
    km_to_user: float
    # Typical one-way distance up to the next tier, km.
    km_to_parent: float
    # Queuing/serialization/peering overhead on the user path (RTT, ms) —
    # what real paths add on top of fiber propagation. National backbones
    # measure 2-4x the propagation floor; this term is why.
    transit_rtt_ms: float
    # Staffed site with liquid-cooling/NOC skills on hand?
    staffed: bool

    def power_gpus(self, gpu_watts: float, overhead: float = 1.35) -> int:
        """How many GPUs of a given TDP the AI power envelope feeds.

        `overhead` covers host CPU/NIC/cooling parasitics per GPU
        (1.35 ~ a lean air-cooled edge node; hyperscale PUE-inclusive
        figures are similar once facility overhead is counted).
        """
        if gpu_watts <= 0:
            raise ValueError("gpu_watts must be > 0")
        return int(self.ai_power_kw * 1000 // (gpu_watts * overhead))


# --- default ladder (all overridable; see REFERENCES.md) --------------------

TOWER = Tier(
    name="tower",
    ai_power_kw=1.5,        # rectifier headroom at a 5-15 kW macro site
    cooling="air",
    max_fabric_gpus=2,      # no scale-out fabric: PCIe inside one 2RU box
    max_gpu_watts=75.0,     # L4-class (72 W); H100-class does not fit
    fabric="none",
    km_to_user=2.0,
    km_to_parent=15.0,
    transit_rtt_ms=0.1,
    staffed=False,
)

HUB = Tier(
    name="aggregation-hub",
    ai_power_kw=50.0,       # central office / C-RAN hotel with real power
    cooling="liquid",       # D2C/CDU serviceable: staffed site
    max_fabric_gpus=64,
    max_gpu_watts=700.0,    # H100/H200-class OK
    fabric="pod",
    km_to_user=15.0,
    km_to_parent=40.0,      # metro DWDM reach to the metro PoP
    transit_rtt_ms=0.3,
    staffed=True,
)

METRO_POP = Tier(
    name="metro-pop",
    ai_power_kw=2_000.0,    # small neocloud PoP, low-MW class
    cooling="liquid",
    max_fabric_gpus=2_048,
    max_gpu_watts=1_400.0,  # Blackwell-class dense racks
    fabric="full",
    km_to_user=40.0,
    km_to_parent=500.0,     # regional/national distance to the central site
    transit_rtt_ms=1.0,
    staffed=True,
)

CENTRAL = Tier(
    name="central-factory",
    ai_power_kw=100_000.0,  # 100 MW-class AI campus
    cooling="liquid",
    max_fabric_gpus=100_000,
    max_gpu_watts=1_400.0,
    fabric="full",
    km_to_user=500.0,
    km_to_parent=0.0,
    transit_rtt_ms=10.0,    # national backbone queuing/peering overhead
    staffed=True,
)

LADDER = (TOWER, HUB, METRO_POP, CENTRAL)


def tier(name: str) -> Tier:
    for t in LADDER:
        if t.name == name or t.name.startswith(name):
            return t
    raise KeyError(f"unknown tier {name!r}; know {[t.name for t in LADDER]}")


def custom(base: str, **overrides) -> Tier:
    """A modified tier, e.g. custom('tower', ai_power_kw=3.0)."""
    return replace(tier(base), **overrides)
