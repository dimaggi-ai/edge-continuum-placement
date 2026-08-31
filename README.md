# Edge↔Neocloud Continuum Placement: centralize by default, edge when forced

**Where on the operator's footprint — tower, aggregation hub, metro PoP, central AI factory — should a given AI workload actually run?** The AI-RAN pitch says "an AI factory at every tower"; the physics says lossless RDMA's buffer bill grows linearly with distance and line rate (the longest lossless product ever sold stops at 40 km [2, 4]) and synchronous training collapses ~26× at 1,000 km in the one published simulation study [6]. This repository turns that tension into an executable placement engine: four tier envelopes with the latency-domain physics built in, four gates (fabric, power, latency, gravity), twelve workload profiles — and a verdict matrix where every edgeward placement must name the constraint that forced it.

**TL;DR:** run `edge-placement matrix` and three findings fall out. **(1) The tower is never the recommended tier** — everything it can host, the aggregation hub hosts better; a national fleet of 30,000 GPU-equipped towers (60,000 GPUs) strands ~87% of its provisioned power in 2-GPU quanta and delivers **6.4× less schedulable FP8 per provisioned megawatt** than 300 hub pods on a third of the power. **(2) Latency is the weakest argument for the edge** — 100 ms interactive SLAs clear a 500 km path; what actually forces edge placement is the **fronthaul budget (~20 km), data gravity (~81 TB/month per 0.25 Gbps of raw ingest), and sovereignty**. **(3) The demark discipline**: RDMA stays inside the PoP's latency domain; what crosses the carrier WAN is SRv6/EVPN-carried IP — crossing the demark is RPC, never RDMA [2, 24, 27].

*Part of the DIMAGGI series on turning GPU capital into usable compute — the placement factor of `usable = nominal × network × scheduling × recovery × placement`. Full analysis in [docs/study.md](docs/study.md); all claims trace to [REFERENCES.md](REFERENCES.md). Companion repo: [airan-neocloud-resiliency](https://github.com/dimaggi-ai/airan-neocloud-resiliency) — what happens when the network under this matrix fails.*

---

## The verdict matrix

![Placement matrix](figures/placement_matrix.png)

Each recommendation names its forcing gate: RAN L1 is forced to the hub by the ~100 µs eCPRI fronthaul budget [11]; the near-RT RIC loop is the *only* workload an application latency SLA forces below central (to the metro, not the tower); camera and telemetry workloads are forced edgeward by backhaul economics, not latency; sovereign inference pins to the metro PoP — sovereignty is a region pin, not an edge pin. Training never leaves the central factory, and a fantasy 1 MW tower stays blocked: the gates are orthogonal (`make test`).

## Bandwidth cannot buy back distance

![Efficiency cliff](figures/efficiency_cliff.png)

Only the bandwidth term of a ring all-reduce can hide behind compute; the 2(n−1) serially chained hops drain at the step boundary, exposed [10]. Quadrupling inter-site bandwidth moves the curve by <1% — Corning's ASTRA-sim study found ≤0.66% from doubling, in simulation [6]. Distance is the axis that matters, and 40 km — the reach of the longest InfiniBand product ever sold, which no AI lab uses [4] — is where lossless fabrics end:

![Lossless ceiling](figures/lossless_ceiling.png)

PFC needs ~2× the one-way bandwidth-delay product — a full round trip of line-rate data — as per-port headroom: ~10 MB at 100 G/80 km (Bifrost's computed requirement: 9.5 MB; its testbed reserved 15.5), ~294 MB at 400 G/600 km (286 MB in Bifrost's simulation) — against tens of MB of real switch buffer [2]. Ultra Ethernet makes PFC optional inside the fabric [5]; it does not repeal BDP across the WAN.

## Quickstart

```
pip install edge-continuum-placement          # or: pip install -e .
edge-placement matrix                          # the full verdict table
edge-placement evaluate -w sovereign-inference-70b
edge-placement physics --rate 400 --km 600     # BDP, lossless ceiling, domains
edge-placement fleet                           # tower fleet vs hub fleet
```

`evaluate -w W -t TIER` exits non-zero if the placement is blocked — usable as a CI gate for infrastructure-as-code. Every envelope is overridable in code:

```python
from continuum.place import place
from continuum.tiers import custom, TOWER, METRO_POP, CENTRAL
from continuum.workloads import workload

rural = (TOWER, custom("aggregation-hub", km_to_user=30.0), METRO_POP, CENTRAL)
place(workload("ran-l1-baseband"), rural).recommended   # -> 'tower'
```

That last line is the tower's honest job description: it earns a GPU exactly where geography strands the radio beyond the hub's ~20 km fronthaul reach.

## The validation project

The invariant suite pins the model's constants to their sources. The
[validation registry](validation.py) does the other half: it runs the
model against data it was **never fitted to**, and against synthetic
fleets, in three honest kinds. **Calibrated** points hold quoted
arithmetic in place (the O-RAN 100 µs budget as a 20.4 km C-RAN radius
[11]; and the New York–San Francisco anchor — 4,148 km, which the source
gives as a **great-circle** distance and calls "unrealistically
optimistic", not a fiber route [1] — checked against the source's own
5 µs/km arithmetic (41.48 ms) so the tolerance covers only the model's
4.9 µs/km rounding, not the source's "~" as well). **Emergent** points
meet public geography: haversine distances from published city
coordinates put the two pairs that can hold synchronous RDMA collectives
at ≤14.25 km and the nearest pair that cannot at 62.16 km — a 47.9 km
empty band with the 40 km MetroX-3 boundary [4] sitting inside it. The
geography does the separating, so the verdicts would be unchanged for
any boundary in that band; that is the honest claim, and it is why the
registry pins the *gap* rather than a count of permitted pairs, which
moves as soon as you add a pair (Ashburn↔Washington DC is 41.8 km). The
striking case stands: San Francisco↔Santa Clara, 62 km apart *inside one
metropolitan area*, is outside fabric reach. The model's propagation
floor for New York–San Francisco (40.5 ms) also sits under the observed
60–70 ms internet band, at a 1.48–1.73× route factor — only that
one-sided claim is asserted, since a floor above measurement would be a
bug.

**Sanity** points regression-guard the engine on 200 seeded random
workloads. They do not *prove* it lawful, and the distinction is not
pedantic: an earlier version of this registry passed with the latency
gate, the power gate or the fabric gate **deleted outright**, because
each point compared a count against a number computed in the same loop.
Every expected count is now a hardcoded constant, `tests/` deletes each
gate in turn and requires the registry to go red, and the points report
what they actually cover — the latency gate blocks 119 of 200 workloads
across seven distances (41 of them at every distance, so vacuously
monotone), 82 of 200 fit no tier at all, and centralize-by-default is
measured on the 10 workloads no gate applies to. Four anchors the
registry deliberately does not check are named in its `DECLINED` list
and printed with the table.

```
make validation  # the registry: public geography + synthetic topologies
```

## Reproduce

```
make test        # invariant tests + the validation registry
make figures     # regenerates figures/ (needs matplotlib)
```

Python 3.10+, stdlib only; `matplotlib` only for figures. The tests pin the model to Bifrost's measured lossless-headroom points and Corning's overlap behaviors — if a constant drifts from its source, the suite fails.

## Series — turning GPU capital into usable compute

- **GPU Cluster Networking** ([network-vs-more-gpus](https://github.com/dimaggi-ai/network-vs-more-gpus)) · **GPU Cluster Scheduling** ([scheduler-vs-more-gpus](https://github.com/dimaggi-ai/scheduler-vs-more-gpus))
- **Compute↔Power Placement** ([compute-power-placement](https://github.com/dimaggi-ai/compute-power-placement)) — move work across the grid map
- **Edge↔Neocloud Placement** (this work) — move work down the operator's footprint, gated by physics
- **Chaos Fidelity Standard** ([ai-cluster-chaos-fidelity](https://github.com/dimaggi-ai/ai-cluster-chaos-fidelity)) · **Reliability Economics** ([reliability-economics](https://github.com/dimaggi-ai/reliability-economics)) · **Governed Autonomy** ([governed-autonomy](https://github.com/dimaggi-ai/governed-autonomy))
- **AI-RAN ↔ Neocloud Resiliency** ([airan-neocloud-resiliency](https://github.com/dimaggi-ai/airan-neocloud-resiliency)) — the companion: survivability of the continuum this repo places onto

---

*Margaret (Maggie) Nanyonga — Founder & Principal Architect, [DIMAGGI AI](https://dimaggi.ai). Governed AI infrastructure: the control, reliability, and audit layer for autonomous systems operating production networks and compute.*
