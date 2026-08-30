"""edge-placement: where on the edge<->neocloud continuum can this run?

Subcommands:
  matrix                     full workload x tier placement matrix
  evaluate -w W [-t T]       one workload: verdicts per tier + recommendation
  physics [--rate G] [--km K] [--buffer-mb M]
                             the WAN gates: BDP, lossless ceiling, domains
  fleet                      tower-fleet vs hub-fleet arithmetic
"""

import argparse
import sys

from . import physics
from .fleet import compare
from .place import matrix, place
from .tiers import LADDER, tier
from .workloads import LIBRARY, workload

STATUS_MARK = {"VIABLE": "+", "COSTLY": "~", "BLOCKED": "x"}


def _cmd_matrix(_args) -> int:
    names = [t.name for t in LADDER]
    wcol = max(len(w.name) for w in LIBRARY) + 2
    print("Legend: + viable   ~ viable-but-costly   x blocked "
          "(gate initial: f fabric, p power, l latency, g gravity)\n")
    header = "workload".ljust(wcol) + "".join(n.ljust(20) for n in names) \
        + "recommended"
    print(header)
    print("-" * len(header))
    for p in matrix(LIBRARY):
        cells = []
        for v in p.verdicts:
            mark = STATUS_MARK[v.status]
            cell = mark if v.status == "VIABLE" else f"{mark}({v.gate[:1]})"
            cells.append(cell.ljust(20))
        rec = p.recommended or "NONE"
        if p.forced_by:
            rec += f"  <- forced by {p.forced_by}"
        print(p.workload.ljust(wcol) + "".join(cells) + rec)
    return 0


def _cmd_evaluate(args) -> int:
    w = workload(args.workload)
    p = place(w)
    print(f"{w.name}: {w.note}\n")
    for v in p.verdicts:
        line = f"  {v.tier:<18} {v.status:<8}"
        if v.detail:
            line += f" [{v.gate}] {v.detail}"
        print(line)
    print(f"\n  recommended: {p.recommended or 'NONE'}")
    if p.forced_by:
        print(f"  forced below central-factory by the {p.forced_by} gate")
    if args.tier:
        try:
            t = tier(args.tier)
        except KeyError as e:
            print(f"error: {e.args[0]}", file=sys.stderr)
            return 2
        v = next(v for v in p.verdicts if v.tier == t.name)
        return 0 if v.ok else 1
    return 0


def _cmd_physics(args) -> int:
    rate, km, buf = args.rate, args.km, args.buffer_mb
    if rate <= 0 or km < 0 or buf <= 0:
        print("error: --rate and --buffer-mb must be > 0, --km must be >= 0",
              file=sys.stderr)
        return 2
    print(f"link: {rate:g} Gbps over {km:g} km of SMF")
    print(f"  one-way propagation : {physics.one_way_us(km):,.0f} us")
    print(f"  round trip          : {physics.rtt_ms(km):.2f} ms")
    print(f"  one-way BDP         : {physics.bdp_mb(rate, km):,.1f} MB")
    print(f"  lossless headroom   : {physics.pfc_headroom_mb(rate, km):,.1f} "
          f"MB/port (~2x one-way BDP)")
    print(f"  latency domain      : {physics.latency_domain(km)}")
    print(f"  RDMA collectives    : "
          f"{'engineerable' if physics.collectives_allowed(km) else 'NO'}")
    ceiling = physics.pfc_max_lossless_km(rate, buf)
    print(f"\nwith {buf:g} MB/port of real headroom, lossless holds to "
          f"~{ceiling:,.1f} km at {rate:g} Gbps")
    print(f"native IB credit loop ({physics.IB_VL_BUFFER_KB} KB/VL) holds to "
          f"~{physics.ib_credit_max_km(rate):,.2f} km at {rate:g} Gbps")
    return 0


def _cmd_fleet(_args) -> int:
    s = compare().summary()
    print("fleet                     tower            hub")
    rows = (
        ("sites", "tower_sites", "hub_sites"),
        ("AI power provisioned (MW)", "tower_ai_mw", "hub_ai_mw"),
        ("AI power consumed (MW)", "tower_consumed_mw", "hub_consumed_mw"),
        ("envelope stranded (%)", "tower_stranded_pct", "hub_stranded_pct"),
        ("GPUs", "tower_gpus", "hub_gpus"),
        ("dense FP8 PFLOPS", "tower_pflops_fp8", "hub_pflops_fp8"),
        ("PFLOPS per MW", "tower_pflops_per_mw", "hub_pflops_per_mw"),
        ("scheduling quantum", "tower_scheduling_quantum_gpus",
         "hub_scheduling_quantum_gpus"),
        ("workload classes hosted", "tower_hostable", "hub_hostable"),
    )
    for label, tk, hk in rows:
        print(f"{label:<25} {s[tk]:<16,} {s[hk]:,}")
    print(f"\nper PROVISIONED MW, the hub fleet delivers "
          f"{s['hub_capability_per_mw_x']}x the schedulable FP8 compute;")
    print("per consumed watt the L4 silicon is competitive — the tower "
          "fleet's cost is the ~87% of envelope its 2-GPU quantum strands")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="edge-placement",
        description="Placement on the tower->hub->metro->central continuum.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("matrix", help="full workload x tier matrix")

    ev = sub.add_parser("evaluate", help="verdicts for one workload")
    ev.add_argument("-w", "--workload", required=True,
                    choices=[w.name for w in LIBRARY])
    ev.add_argument("-t", "--tier", default=None,
                    help="exit non-zero if blocked on this tier")

    ph = sub.add_parser("physics", help="WAN gates for a link")
    ph.add_argument("--rate", type=float, default=400.0, help="Gbps")
    ph.add_argument("--km", type=float, default=600.0)
    ph.add_argument("--buffer-mb", type=float, default=64.0,
                    help="real per-port headroom available")

    sub.add_parser("fleet", help="tower vs hub fleet arithmetic")

    args = ap.parse_args(argv)
    return {"matrix": _cmd_matrix, "evaluate": _cmd_evaluate,
            "physics": _cmd_physics, "fleet": _cmd_fleet}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
