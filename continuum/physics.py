"""Latency-domain physics for the edge<->neocloud compute continuum.

Every function is a small, checkable formula with its calibration exposed as
an argument. The three gates modeled here are the reasons a GPU fabric stops
at the metro boundary:

  1. Propagation delay  — light in standard single-mode fiber travels at
     c/n ~ 204,000 km/s, i.e. ~4.9 us/km one way. Nothing negotiates with it.
  2. Lossless headroom  — PFC-style losslessness must absorb ~2x the
     one-way bandwidth-delay product per link (a full round-trip of
     line-rate data) as switch buffer headroom; BDP grows linearly with
     distance and line rate, switch buffers do not.
  3. Collective latency — synchronous all-reduce pays the one-way latency
     2(n-1) times per ring pass; past the overlap budget the exposed time
     comes straight out of GPU utilization.

Calibration constants live in `defaults` below; each maps to an entry in
REFERENCES.md.
"""

from dataclasses import dataclass

# --- calibration (see REFERENCES.md) ---------------------------------------

FIBER_US_PER_KM = 4.9        # one-way propagation, SMF-28-class fiber (n~1.468)
HOLLOW_CORE_US_PER_KM = 3.5  # hollow-core fiber, ~99.7% c in air
PFC_HEADROOM_BDP_MULT = 2.0  # lossless reservation ~ 2x one-way BDP (Bifrost's 2-Delta)
IB_VL_BUFFER_KB = 128        # per-VL credit buffer, native InfiniBand HCA-class


def one_way_us(km: float, us_per_km: float = FIBER_US_PER_KM) -> float:
    """One-way propagation delay over `km` of fiber, in microseconds."""
    if km < 0:
        raise ValueError("distance must be >= 0")
    return km * us_per_km


def rtt_ms(km: float, us_per_km: float = FIBER_US_PER_KM) -> float:
    """Round-trip propagation over `km`, in milliseconds (propagation only)."""
    return 2.0 * one_way_us(km, us_per_km) / 1000.0


def bdp_mb(rate_gbps: float, km: float,
           us_per_km: float = FIBER_US_PER_KM) -> float:
    """One-way bandwidth-delay product of a link at `rate_gbps` over `km`, MB.

    One propagation delay's worth of line-rate data (Bifrost's Delta). A
    pause/credit loop must cover ~2x this — the pause frame travels back one
    way while line-rate data keeps arriving the other — which is what
    pfc_headroom_mb charges.
    """
    delay_s = one_way_us(km, us_per_km) * 1e-6
    return rate_gbps * 1e9 * delay_s / 8.0 / 1e6


def pfc_headroom_mb(rate_gbps: float, km: float,
                    mult: float = PFC_HEADROOM_BDP_MULT) -> float:
    """Per-port buffer headroom a lossless (PFC) link must reserve, in MB.

    ~2x the one-way BDP = one full round-trip of line-rate data (Bifrost's
    2-Delta): ~9.8 MB at 100G/80 km (Bifrost's computed requirement: 9.5),
    ~294 MB at 400G/600 km (Bifrost simulated 286 MB).
    """
    return mult * bdp_mb(rate_gbps, km)


def pfc_max_lossless_km(rate_gbps: float, headroom_mb: float,
                        mult: float = PFC_HEADROOM_BDP_MULT) -> float:
    """Longest link that stays lossless given `headroom_mb` of buffer.

    Inverts pfc_headroom_mb. A 400G port with 64 MB of dedicated headroom
    (already generous on merchant silicon shared across ports) reaches only
    ~131 km; national distances need hundreds of MB per port.
    """
    if headroom_mb <= 0 or rate_gbps <= 0:
        raise ValueError("rate and headroom must be > 0")
    one_way_s = headroom_mb * 1e6 * 8.0 / (mult * rate_gbps * 1e9)
    return one_way_s * 1e6 / FIBER_US_PER_KM


def ib_credit_max_km(rate_gbps: float,
                     vl_buffer_kb: float = IB_VL_BUFFER_KB) -> float:
    """Native InfiniBand credit-loop distance ceiling for one VL.

    Credit-based flow control can keep the pipe full only while the
    advertised buffer covers the round-trip worth of in-flight data:
    ~128 KB/VL at 100 Gbps covers ~1 km. Long-reach IB (MetroX-class)
    works by adding large external buffers, not by relaxing the rule.
    """
    rtt_s = vl_buffer_kb * 1024 * 8.0 / (rate_gbps * 1e9)
    return rtt_s * 1e6 / (2.0 * FIBER_US_PER_KM)


# --- synchronous collectives over distance ---------------------------------

@dataclass(frozen=True)
class CollectiveScenario:
    """A synchronous data-parallel training step split across two sites."""
    n_ranks: int              # ring participants that cross the inter-site link
    payload_gb: float         # gradient bytes exchanged per step (per rank)
    inter_site_gbps: float    # bandwidth of the cross-site pipe (per rank share)
    compute_ms: float         # per-step compute time available for overlap
    overlap_fraction: float = 1.0  # share of comm hidable behind compute


def ring_allreduce_ms(n_ranks: int, payload_gb: float, bw_gbps: float,
                      one_way_latency_us: float) -> float:
    """Standard ring all-reduce time: 2(n-1)/n bandwidth term + 2(n-1) latency hops.

    The latency term is why distance, not bandwidth, dominates: doubling
    bw_gbps halves the first term only, while every extra kilometer taxes
    all 2(n-1) steps.
    """
    if n_ranks < 2:
        return 0.0
    bw_term_s = 2.0 * (n_ranks - 1) / n_ranks * (payload_gb * 8.0 / bw_gbps)
    lat_term_s = 2.0 * (n_ranks - 1) * one_way_latency_us * 1e-6
    return (bw_term_s + lat_term_s) * 1000.0


def sync_step_efficiency(scn: CollectiveScenario, distance_km: float,
                         us_per_km: float = FIBER_US_PER_KM) -> float:
    """GPU utilization multiplier for a synchronous step across `distance_km`.

    efficiency = compute / (compute + exposed_comm), where exposed_comm is
    the part of the all-reduce that cannot hide behind compute. Only the
    BANDWIDTH term of the ring can overlap with backward compute; the
    latency term — 2(n-1) serially chained hops draining at the step
    boundary — always sits on the critical path. That asymmetry is the
    whole cliff: adding bandwidth attacks the hideable term, adding
    distance grows the unhideable one ('training does not cross the WAN').
    """
    one_way = one_way_us(distance_km, us_per_km)
    bw_ms = ring_allreduce_ms(scn.n_ranks, scn.payload_gb,
                              scn.inter_site_gbps, 0.0)
    lat_ms = ring_allreduce_ms(scn.n_ranks, scn.payload_gb,
                               scn.inter_site_gbps, one_way) - bw_ms
    hidden_ms = min(bw_ms, scn.compute_ms * scn.overlap_fraction)
    exposed_ms = (bw_ms - hidden_ms) + lat_ms
    return scn.compute_ms / (scn.compute_ms + exposed_ms)


# --- latency domains --------------------------------------------------------

DOMAINS = (
    # (name, max_one_way_km, fabric, allowed traffic)
    ("intra-rack",  0.002, "NVLink/NVSwitch",        "tensor/expert parallel"),
    ("intra-pod",   0.1,   "RoCEv2 / InfiniBand",    "data/pipeline parallel"),
    ("metro",       40.0,  "long-reach IB or lossless Ethernet over DWDM",
                            "pipeline stages, inference disaggregation"),
    ("regional+",   float("inf"), "SRv6/EVPN IP transport",
                            "RPC, model pull, telemetry - no RDMA collectives"),
)


def latency_domain(distance_km: float) -> str:
    """Classify a site separation into its latency domain."""
    if distance_km < 0:
        raise ValueError("distance must be >= 0")
    for name, max_km, _, _ in DOMAINS:
        if distance_km <= max_km:
            return name
    return DOMAINS[-1][0]


def collectives_allowed(distance_km: float) -> bool:
    """True if synchronous RDMA collectives are engineerable at this distance."""
    return latency_domain(distance_km) in ("intra-rack", "intra-pod", "metro")
