"""The placement engine: workload x tier -> verdict, with the binding gate.

The rule the engine encodes (and the study defends): centralize by default —
scale economies live at the top of the ladder — and place edgeward only when
a constraint FORCES it. Five gates can force or forbid a placement:

  fabric   - collective class vs what the site fabric can hold
  power    - GPU count x TDP vs the AI power envelope, and cooling class
  latency  - fronthaul budget (R0) or network RTT budget (interactive)
  gravity  - sovereignty pins; raw-ingest backhaul makes distance costly
  physics  - 'large' collectives cannot span sites (latency domains)

Verdicts: VIABLE, COSTLY (works, but hauls raw ingest a tier too far),
BLOCKED (hard gate). The recommendation is the most central VIABLE tier;
if the recommendation sits below the top of the ladder, the engine names
the constraint that forced it down — that constraint is the *reason the
edge tier exists* for this workload.
"""

from dataclasses import dataclass

from .physics import one_way_us, rtt_ms
from .tiers import Tier, LADDER
from .workloads import Workload

# O-RAN 7.2x fronthaul one-way latency budget (us); see REFERENCES.md.
FRONTHAUL_BUDGET_US = 100.0
# Above this continuous raw-ingest haul, a placement beyond the metro edge
# is flagged COSTLY, not blocked: 0.25 Gbps sustained ~ 81 TB/month, which
# at cloud-egress-class transfer pricing is thousands of dollars monthly —
# the 'intelligent egress control' line item, priced.
INGEST_COSTLY_GBPS = 0.25
# Cooling: air handles this much per accelerator before liquid is required.
AIR_COOLED_MAX_GPU_W = 350.0


@dataclass(frozen=True)
class Verdict:
    workload: str
    tier: str
    status: str          # 'VIABLE' | 'COSTLY' | 'BLOCKED'
    gate: str            # which gate decided it ('' when VIABLE)
    detail: str

    @property
    def ok(self) -> bool:
        return self.status != "BLOCKED"


def _fabric_gate(w: Workload, t: Tier) -> str | None:
    if w.collective == "large" and t.fabric != "full":
        return (f"synchronous collectives across {w.gpus} GPUs need a "
                f"full-scale fabric; '{t.name}' offers '{t.fabric}'")
    if w.collective == "pod" and t.fabric == "none":
        return f"pod collectives need a scale-out fabric; '{t.name}' has none"
    if w.gpus > t.max_fabric_gpus:
        return (f"needs {w.gpus} GPUs in one fabric; '{t.name}' holds "
                f"{t.max_fabric_gpus}")
    return None


def _power_gate(w: Workload, t: Tier) -> str | None:
    if w.gpu_watts > t.max_gpu_watts:
        return (f"{w.gpu_watts:.0f} W accelerators exceed the "
                f"{t.max_gpu_watts:.0f} W envelope of '{t.name}'")
    if t.cooling == "air" and w.gpu_watts > AIR_COOLED_MAX_GPU_W:
        return (f"{w.gpu_watts:.0f} W parts need liquid cooling; "
                f"'{t.name}' is air-only")
    fits = t.power_gpus(w.gpu_watts)
    if w.gpus > fits:
        return (f"needs {w.gpus} x {w.gpu_watts:.0f} W; the "
                f"{t.ai_power_kw:g} kW envelope feeds {fits}")
    return None


def _latency_gate(w: Workload, t: Tier) -> str | None:
    if w.resilience_class == "R0":
        fh = one_way_us(t.km_to_user)
        if fh > FRONTHAUL_BUDGET_US:
            return (f"fronthaul one-way {fh:.0f} us over "
                    f"{t.km_to_user:g} km busts the "
                    f"{FRONTHAUL_BUDGET_US:.0f} us eCPRI budget")
        return None
    if w.latency_sla_ms == float("inf"):
        return None
    path = w.access_rtt_ms + rtt_ms(t.km_to_user) + t.transit_rtt_ms
    if path > w.latency_sla_ms:
        return (f"access {w.access_rtt_ms:g} ms + propagation "
                f"{rtt_ms(t.km_to_user):.1f} ms + transit "
                f"{t.transit_rtt_ms:g} ms exceeds the "
                f"{w.latency_sla_ms:g} ms budget")
    return None


def _gravity_gate(w: Workload, t: Tier) -> tuple[str | None, str | None]:
    """Returns (block_reason, costly_reason)."""
    if w.sovereign and t.name == "central-factory":
        return ("residency pins this workload inside the operator's "
                "regional footprint", None)
    if (w.data_gravity == "local" and w.ingest_gbps > INGEST_COSTLY_GBPS
            and t.km_to_user > 20.0):
        return (None,
                f"hauls {w.ingest_gbps:g} Gbps of raw local ingest "
                f"{t.km_to_user:g} km upstream — works, but the backhaul "
                f"bill is the product")
    return (None, None)


def evaluate(w: Workload, t: Tier) -> Verdict:
    """Run the gate cascade for one workload on one tier."""
    for gate, fn in (("fabric", _fabric_gate), ("power", _power_gate),
                     ("latency", _latency_gate)):
        reason = fn(w, t)
        if reason:
            return Verdict(w.name, t.name, "BLOCKED", gate, reason)
    block, costly = _gravity_gate(w, t)
    if block:
        return Verdict(w.name, t.name, "BLOCKED", "gravity", block)
    if costly:
        return Verdict(w.name, t.name, "COSTLY", "gravity", costly)
    return Verdict(w.name, t.name, "VIABLE", "", "")


@dataclass(frozen=True)
class Placement:
    workload: str
    recommended: str | None     # most central VIABLE (or COSTLY) tier
    forced_by: str              # gate that pushed it below the top; '' if none
    verdicts: tuple[Verdict, ...]


def place(w: Workload, ladder: tuple[Tier, ...] = LADDER) -> Placement:
    verdicts = tuple(evaluate(w, t) for t in ladder)
    # Most central viable tier: walk the ladder top-down.
    rec = next((v for v in reversed(verdicts) if v.status == "VIABLE"), None)
    if rec is None:
        rec = next((v for v in reversed(verdicts) if v.status == "COSTLY"),
                   None)
    if rec is None:
        return Placement(w.name, None, "infeasible", verdicts)
    # What forced it down from the top of the ladder?
    forced = ""
    if rec.tier != ladder[-1].name:
        above = next(v for v in reversed(verdicts)
                     if v.tier == ladder[-1].name)
        forced = above.gate
    return Placement(w.name, rec.tier, forced, verdicts)


def matrix(workloads, ladder: tuple[Tier, ...] = LADDER):
    """All placements for a workload library."""
    return [place(w, ladder) for w in workloads]
