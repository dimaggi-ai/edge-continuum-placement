#!/usr/bin/env python3
"""The validation project: the model against public geography and synthetic fleets.

The physics constants themselves (Bifrost's 9.5 MB and 286 MB headroom
points, the ring-allreduce terms, the Corning overlap behaviors, the
MetroX-3 metro boundary) are asserted directly in tests/test_physics.py.
This registry adds the two things those tests cannot do: it runs the
model against **public data it was never fitted to** — real city
geography, computed by haversine from published coordinates — and
against a **seeded synthetic fleet**, 200 random workloads run over the
ladder and over seven site distances, to regression-guard the placement
engine outside the twelve hand-written library profiles.

Three kinds of points, honestly separated:

  calibrated  quotes a published figure the model is pinned to. Passing
              proves the repo has not drifted from its citations, not
              that it predicts anything.
  emergent    the model meeting data nothing was tuned to: real
              inter-city distances, and the observed-RTT band. These can
              fail; that is the point.
  sanity      regression guards on the engine's behaviour over synthetic
              input. Cites no external evidence and claims none.

Every sanity point below pins a COUNT against a hardcoded constant
rather than against a number computed in the same loop. That is not a
style preference: an earlier version of this file compared each count
against itself, and deleting the latency gate, the power gate or the
fabric gate outright left every point PASSing. tests/test_validation.py
now deletes each gate in turn and requires the registry to go red.

Anchors this registry does NOT check are listed in DECLINED and printed
with the table.

Run: python3 validation.py   (exit 1 if any point fails)
"""

from __future__ import annotations

import dataclasses
import math
import random
import sys

from continuum.physics import (
    FIBER_US_PER_KM,
    collectives_allowed,
    one_way_us,
    rtt_ms,
)
from continuum.place import FRONTHAUL_BUDGET_US, evaluate, place
from continuum.tiers import LADDER, custom
from continuum.workloads import Workload

# Public coordinates (degrees, WGS84) — geographic facts, not a model input.
CITIES = {
    "New York": (40.7128, -74.0060),
    "Secaucus": (40.7895, -74.0565),
    "Newark": (40.7357, -74.1724),
    "San Francisco": (37.7749, -122.4194),
    "Santa Clara": (37.3541, -121.9552),
    "Ashburn": (39.0438, -77.4874),
    "London": (51.5074, -0.1278),
    "Paris": (48.8566, 2.3522),
    "Frankfurt": (50.1109, 8.6821),
    "Amsterdam": (52.3676, 4.9041),
    "Tokyo": (35.6762, 139.6503),
    "Osaka": (34.6937, 135.5023),
    "Dallas": (32.7767, -96.7970),
    "Houston": (29.7604, -95.3698),
}

# Nine real pairs: two intra-metro, one same-metro-but-spread (SF/Santa
# Clara, 62 km apart inside one metropolitan area), five regional, one
# transcontinental.
PAIRS = (
    ("New York", "Secaucus"),
    ("New York", "Newark"),
    ("San Francisco", "Santa Clara"),
    ("New York", "Ashburn"),
    ("London", "Paris"),
    ("Frankfurt", "Amsterdam"),
    ("Tokyo", "Osaka"),
    ("Dallas", "Houston"),
    ("New York", "San Francisco"),
)

EARTH_R_KM = 6371.0088

# The four gates the cascade can block on. Every one of them must block at
# least one synthetic evaluation, or a gate has silently stopped working.
GATES = ("fabric", "power", "latency", "gravity")

# Hardcoded expectations for the seeded synthetic fleet. These are constants
# on purpose — see the module docstring.
SYNTH_N = 200
LATENCY_BLOCKED_IN_SWEEP = 119     # of 200, at >=1 of seven distances
UNPLACEABLE = 82                   # of 200, no tier accepts them
UNCONSTRAINED = 10                 # of 200, no gate applies at all

DECLINED: tuple[tuple[str, str], ...] = (
    ("That the 40 km metro boundary is the RIGHT boundary",
     "the nine real pairs straddle it with a 14.25-62.16 km gap, so any "
     "boundary in that band gives the same verdicts. The geography check "
     "below therefore pins the GAP, not the constant: it would still pass "
     "if MetroX-3's 40 km were wrong by -64%/+55%."),
    ("That the synthetic fleet resembles a real fleet",
     "it is a uniform grid sample over the library's own parameter values; "
     "32% of it is R0 and 41% of it is unplaceable. It is a regression "
     "corpus, not a market model, and no claim about real demand is made."),
    ("Monotonicity as a discovered property",
     "with the tier fixed and only distance swept, the latency gate is "
     "strictly increasing in km against a fixed threshold, so monotonicity "
     "is provable from its form. The point is a regression guard that the "
     "gate still runs and still blocks the expected 119 workloads."),
    ("That REFERENCES.md quotes its sources correctly",
     "no numeric check can. The NYC-SF entry was in fact mislabelled a "
     "'fiber route' when the source calls it a great-circle distance; that "
     "was caught by reading the source, not by this file."),
)


def great_circle_km(a: str, b: str) -> float:
    """Haversine distance between two public coordinates. Pure geometry."""
    (la1, lo1), (la2, lo2) = CITIES[a], CITIES[b]
    p1, p2 = math.radians(la1), math.radians(la2)
    dp, dl = p2 - p1, math.radians(lo2 - lo1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_R_KM * math.asin(math.sqrt(h))


@dataclasses.dataclass(frozen=True)
class Point:
    name: str
    kind: str        # 'calibrated' | 'emergent' | 'sanity'
    ref: str         # '-' allowed for sanity points only
    expected: float
    tolerance: float
    actual: float
    note: str

    @property
    def ok(self) -> bool:
        return abs(self.actual - self.expected) <= self.tolerance


def _synthetic_workloads(n: int, rng: random.Random) -> list[Workload]:
    """Seeded random workloads spanning the whole parameter space."""
    out = []
    for i in range(n):
        collective = rng.choice(("none", "pod", "large"))
        out.append(Workload(
            name=f"synth-{i}",
            latency_sla_ms=rng.choice((0.2, 5.0, 20.0, 100.0, 150.0,
                                       float("inf"))),
            access_rtt_ms=rng.choice((0.0, 2.0, 5.0, 20.0)),
            gpus=rng.choice((1, 2, 4, 8, 64, 512, 16_384)),
            gpu_watts=rng.choice((72.0, 75.0, 350.0, 700.0, 1_400.0)),
            collective=collective,
            data_gravity=rng.choice(("local", "mixed", "central")),
            ingest_gbps=rng.choice((0.0, 0.1, 1.0, 25.0)),
            sovereign=rng.random() < 0.25,
            resilience_class=rng.choice(("R0", "R1", "R2")),
        ))
    return out


def points() -> tuple[Point, ...]:
    pts: list[Point] = []

    # ---------------------------------------------------------- calibrated
    pts.append(Point(
        "fronthaul-radius-20km", "calibrated", "[11]",
        expected=20.4, tolerance=0.1,
        actual=FRONTHAUL_BUDGET_US / FIBER_US_PER_KM,
        note="The O-RAN 7.2x ~100 us one-way fronthaul budget over "
             "4.9 us/km fiber = a 20.4 km C-RAN radius — the constant "
             "_latency_gate enforces for R0 workloads. Source arithmetic, "
             "pinned against drift: it moves on any change to either "
             "constant.",
    ))
    pts.append(Point(
        "nyc-sf-great-circle-rtt", "calibrated", "[1]",
        expected=41.48, tolerance=0.9, actual=rtt_ms(4148.0),
        note="The published New York-San Francisco anchor. NOTE the "
             "source's own framing: 4,148 km is the GREAT-CIRCLE distance, "
             "and the source calls its 42 ms 'unrealistically optimistic' "
             "because real fiber routes are longer — this repo previously "
             "called it a 'fiber route'. The check is against the source's "
             "own arithmetic (4,148 x 5 us/km x 2 = 41.48 ms), not its "
             "rounded 42 ms, so the tolerance covers only the difference "
             "between the model's 4.9 us/km and the source's 5 us/km "
             "(0.83 ms) rather than absorbing the source's '~' as well.",
    ))

    # ------------------------------------------------------------ emergent
    # Real geography the model was never fitted to. The pairs were chosen
    # to span the ladder: two intra-metro (<15 km), one same-metropolitan-
    # area-but-spread, five regional, one transcontinental. Stating the
    # selection rule matters, because the COUNT of permitted pairs is a
    # property of that choice, not of the model.
    dists = {f"{a}-{b}": great_circle_km(a, b) for a, b in PAIRS}
    permitted = {k: v for k, v in dists.items() if collectives_allowed(v)}
    refused = {k: v for k, v in dists.items() if k not in permitted}
    gap = min(refused.values()) - max(permitted.values())
    pts.append(Point(
        "metro-boundary-falls-in-an-empty-band", "emergent", "[4]",
        expected=47.9, tolerance=0.1, actual=gap,
        note=f"Measured by haversine from public coordinates: the "
             f"{len(permitted)} pairs that can hold synchronous collectives "
             f"top out at {max(permitted.values()):.2f} km "
             f"({max(permitted, key=permitted.get)}), and the nearest pair "
             f"that cannot is {min(refused.values()):.2f} km "
             f"({min(refused, key=refused.get)}) — a {gap:.2f} km empty "
             f"band with the model's 40 km MetroX-3 boundary inside it. "
             f"This is the honest form of the claim: the geography, not the "
             f"constant, does the separating, and the verdicts would be "
             f"unchanged for any boundary in that band. The striking case "
             f"is San Francisco-Santa Clara, 62 km apart INSIDE one "
             f"metropolitan area and outside fabric reach — 'the metro' as "
             f"real estate is larger than 'the metro' as a fabric. Adding "
             f"pairs changes the count (Ashburn-DC is 41.8 km, on the "
             f"knife edge), which is why the count is not the claim.",
    ))
    nyc_sf_floor = rtt_ms(great_circle_km("New York", "San Francisco"))
    factor_lo = 60.0 / nyc_sf_floor
    factor_hi = 70.0 / nyc_sf_floor
    pts.append(Point(
        "floor-sits-under-observed-internet-rtt", "emergent", "[1]",
        expected=1.0, tolerance=0.0, actual=float(factor_lo >= 1.0),
        note=f"The model's great-circle propagation floor for New "
             f"York-San Francisco is {nyc_sf_floor:.1f} ms RTT, under the "
             f"60-70+ ms the source reports as observed internet RTT — a "
             f"route-plus-equipment factor of {factor_lo:.2f}-"
             f"{factor_hi:.2f}x. Only the ONE-SIDED claim is asserted: a "
             f"physics floor above measurement would be a model bug. An "
             f"earlier version also asserted an upper bound of 2.5x, a "
             f"number appearing in no source and wide enough to admit "
             f"anything from 2,857 to 6,122 km; it is gone.",
    ))

    # -------------------------------------------------------------- sanity
    rng = random.Random(0)
    synth = _synthetic_workloads(SYNTH_N, rng)

    # The point that caught the hole: every gate must actually block
    # something. Deleting any one gate drops this from 4 and fails.
    blocking = {v.gate for w in synth for t in LADDER
                if (v := evaluate(w, t)).status == "BLOCKED"}
    pts.append(Point(
        "every-gate-blocks-something", "sanity", "-",
        expected=float(len(GATES)), tolerance=0.0,
        actual=float(len(blocking & set(GATES))),
        note=f"All {len(GATES)} gates fire over the synthetic fleet x the "
             f"ladder: {', '.join(sorted(blocking & set(GATES)))}. Without "
             f"this point the registry passed with the latency, power or "
             f"fabric gate deleted outright — every other point was blind "
             f"to a gate that always returns None. The power gate in "
             f"particular fires nowhere in the distance sweep below; it "
             f"only appears here, against the real ladder.",
    ))

    monotone = 0
    tested = 0
    always_blocked = 0
    distances = (1.0, 5.0, 20.0, 40.0, 100.0, 500.0, 2000.0)
    for w in synth:
        blocked_at = None
        ok = True
        seq = []
        for km in distances:
            t = custom("metro-pop", km_to_user=km)
            v = evaluate(w, t)
            is_lat_block = v.status == "BLOCKED" and v.gate == "latency"
            seq.append(is_lat_block)
            if is_lat_block and blocked_at is None:
                blocked_at = km
            elif blocked_at is not None and not is_lat_block:
                ok = False           # un-blocked by moving FURTHER away
        if blocked_at is not None:
            tested += 1
            monotone += int(ok)
            always_blocked += int(all(seq))
    pts.append(Point(
        "latency-blocking-monotone-in-distance", "sanity", "-",
        expected=float(LATENCY_BLOCKED_IN_SWEEP), tolerance=0.0,
        actual=float(monotone),
        note=f"{len(synth)} seeded workloads at seven site distances "
             f"(1-2,000 km). {tested} are blocked by the latency gate at "
             f"one or more distances, and all {monotone} stay blocked at "
             f"every greater distance. The expected count is the hardcoded "
             f"constant {LATENCY_BLOCKED_IN_SWEEP}, not a number computed "
             f"in this loop — comparing the loop against itself made the "
             f"point pass when the gate was deleted. Disclosure: "
             f"{always_blocked} of {tested} are blocked at ALL seven "
             f"distances and so are vacuously monotone; only "
             f"{tested - always_blocked} show a real transition. And given "
             f"a fixed tier with only distance swept, monotonicity is "
             f"provable from the gate's form, so this guards against "
             f"regression, it does not discover anything.",
    ))

    unplaceable = sum(1 for w in synth if place(w).recommended is None)
    pts.append(Point(
        "synthetic-fleet-unplaceable-count", "sanity", "-",
        expected=float(UNPLACEABLE), tolerance=0.0, actual=float(unplaceable),
        note=f"{unplaceable} of {len(synth)} synthetic workloads "
             f"({unplaceable / len(synth):.0%}) fit NO tier on the ladder "
             f"and are returned as infeasible. Pinned as a count because "
             f"the point it replaced — 'every workload resolves' — was a "
             f"tautology: place() returns recommended=None only in the "
             f"branch that sets forced_by='infeasible', so the disjunction "
             f"was identically true (verified exhaustively over 181,440 "
             f"parameter combinations). It also read as a health check on "
             f"a fleet where two workloads in five land nowhere.",
    ))

    unconstrained = [
        w for w in synth
        if not w.sovereign and w.latency_sla_ms == float("inf")
        and w.data_gravity != "local" and w.resilience_class != "R0"
    ]
    central = sum(1 for w in unconstrained
                  if place(w).recommended == LADDER[-1].name)
    pts.append(Point(
        "centralize-by-default-on-synthetic-input", "sanity", "-",
        expected=float(UNCONSTRAINED), tolerance=0.0, actual=float(central),
        note=f"All {len(unconstrained)} synthetic workloads with no "
             f"sovereignty pin, no latency budget, no local data gravity "
             f"and no R0 class land on the central factory — the "
             f"'centralize by default, move edgeward only when forced' "
             f"rule holding on input the library never saw. Honest "
             f"limits: that is {len(unconstrained) / len(synth):.0%} of the "
             f"sample, the filter removes exactly the four gate triggers, "
             f"and the central tier's envelope dominates every sampled "
             f"value — so this fires only on a structural change (it does "
             f"catch max_fabric_gpus being cut to 8, or the ladder walk "
             f"being reversed).",
    ))

    return tuple(pts)


def validate() -> tuple[tuple[Point, ...], bool]:
    pts = points()
    return pts, all(p.ok for p in pts)


def main() -> int:
    pts, ok = validate()
    w = max(len(p.name) for p in pts)
    print(f"{'point':<{w}}  {'kind':<10}  {'ref':<5}  {'expected':>9}  "
          f"{'actual':>9}  verdict")
    for p in pts:
        print(f"{p.name:<{w}}  {p.kind:<10}  {p.ref:<5}  {p.expected:>9.4g}  "
              f"{p.actual:>9.4g}  {'PASS' if p.ok else 'FAIL'}")
    print()
    print("anchors this registry does NOT check:")
    for what, why in DECLINED:
        print(f"  - {what}\n      {why}")
    print()
    if ok:
        print("all points reproduced — calibrated points hold the repo to "
              "its citations, emergent points meet public geography the "
              "model was never fitted to, sanity points regression-guard "
              "the engine on synthetic fleets (they do not prove it "
              "lawful: see DECLINED)")
    else:
        print("VALIDATION FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
