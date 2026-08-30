# References

Every calibration constant in `continuum/` traces to an entry here. Entries
note what the source pins and how it is used. Verified against the primary
URLs on 2026-08-29.

## Propagation & lossless-transport physics

**[1] Fiber propagation ≈ 4.9 µs/km one-way.** Standard SMF, n ≈ 1.468
(~204,000 km/s). Pins `FIBER_US_PER_KM`. Canonical long-haul point: New
York–San Francisco, 4,148 km fiber route → ~21 ms one-way / **~42 ms RTT**
(theoretical fiber minimum; observed internet RTTs run 60–70+ ms).
[MapYourTech, "The 5-Microsecond Rule"](https://mapyourtech.com/the-5-microsecond-rule-fiber-propagation-latency-per-kilometer/) ·
[M2 Optics, "Calculating Optical Fiber Latency"](https://www.m2optics.com/blog/bid/70587/calculating-optical-fiber-latency) ·
[Grigorik, *High Performance Browser Networking*, Table 1-1](https://hpbn.co/primer-on-latency-and-bandwidth/)

**[2] Bifrost (IEEE ICNP 2023) — PFC headroom ≈ 2× one-way BDP;
long-distance lossless points.** "PFC requires a buffer of 2Δ" (Δ = the
one-way BDP). Testbed: 80 km / 100 Gbps → 400 µs one-way, headroom
requirement 2Δ ≈ **9.5 MB**, 15.5 MB reserved per link in practice.
Simulation: 400 Gbps / 600 km (3 ms one-way) → **286 MB headroom** on the
long-haul port. Also: InfiniBand's 12-bit FCCL credit field "limits IB to at
most 1 kilometer for a 100 Gbps link." Pins `PFC_HEADROOM_BDP_MULT`,
`pfc_headroom_mb`, `ib_credit_max_km`; `tests/test_physics.py` asserts the
9.5 MB and 286 MB points. Yu et al., "Bifrost: Extending RoCE for Long
Distance Inter-DC Links," ICNP 2023, DOI 10.1109/ICNP59255.2023.10355634.
[Author PDF](https://cs.nju.edu.cn/tianchen/lunwen/2023/icnp23-peiwenyu.pdf) ·
[IEEE Xplore](https://ieeexplore.ieee.org/document/10355634/)

**[3] InfiniBand credit window ≈ 128 KB/VL.** 12-bit FCTBS/FCCL advertising
up to 2048 × 64 B blocks ≈ 131 KB per virtual lane. Pins `IB_VL_BUFFER_KB`.
[US Patent 7,952,998, "InfiniBand credit-less flow control for long distance links"](https://patents.google.com/patent/US7952998) (2011)

**[4] MetroX-3: long-reach InfiniBand tops out at 40 km — and nobody uses
it for AI.** Announced ahead of SC22 (Nov 2022): extends Quantum-2 IB to
25 mi/40 km over DWDM, 2×100 Gbps per chassis. SemiAnalysis (Sept 4, 2024):
"no AI lab uses it… even Microsoft, who uses InfiniBand heavily, uses
Ethernet between datacenters." Pins the 40 km metro boundary in
`physics.DOMAINS` / `collectives_allowed`.
[The Register](https://www.theregister.com/2022/11/15/nvidia_turns_to_optical_trickery/) ·
[NVIDIA long-haul systems](https://www.nvidia.com/en-us/networking/infiniband-long-haul-systems/) ·
[SemiAnalysis, "Multi-Datacenter Training"](https://newsletter.semianalysis.com/p/multi-datacenter-training-openais)

**[5] Ultra Ethernet 1.0 (June 11, 2025) makes PFC optional, not
obsolete.** UET targets best-effort (lossy) networks: packet spraying,
out-of-order tolerant delivery, Link-Level Retry and CBFC as optional
link-layer features that can be used "in conjunction with or in place of"
PFC. It relaxes the lossless requirement inside the fabric; it does not
repeal the bandwidth-delay product across the WAN.
[UEC Specification v1.0 (PDF)](https://ultraethernet.org/wp-content/uploads/sites/20/2025/06/UE-Specification-6.11.25.pdf) ·
[arXiv:2508.08906, "Ultra Ethernet's Design Principles"](https://arxiv.org/html/2508.08906v1)

**[6] Corning geo-distributed training study — distance, not bandwidth, is
the binding constraint.** ASTRA-sim, GPT-3 175B, up to 8,192 GPUs:
near-complete compute-communication overlap below 10 km; **~26× step-time
penalty at 1,000 km on H100-class nodes** (~4× on A100 — faster compute
exposes more latency); **doubling inter-DC bandwidth improves overlap by at
most 0.66%**; optimal inter-DC separation 10–100 km. Hollow-core fiber
(~3.3 µs/km; `HOLLOW_CORE_US_PER_KM` = 3.5 is the conservative deployed
figure) buys ~25% more overlap / up to 50% more separation. Pins the shape
of `sync_step_efficiency`; `tests/test_physics.py` asserts the <10 km,
1,000 km, and bandwidth-doubling behaviors. Papavasileiou et al. (Corning),
submitted to ECOC 2026 — preprint, not yet peer-reviewed.
[arXiv:2605.19169](https://arxiv.org/html/2605.19169)

**[7] Spectrum-XGS "scale-across" (Aug 22, 2025).** Distance-adjusted
congestion control across DC-to-DC spans; NVIDIA cites **1.9× NCCL
performance** cross-datacenter (the ~10 km test span appears in secondary
coverage of NVIDIA's benchmark, not the press release). Evidence that the
industry is engineering *around* the WAN, within metro distances — not
through it.
[NVIDIA newsroom](https://nvidianews.nvidia.com/news/nvidia-introduces-spectrum-xgs-ethernet-to-connect-distributed-data-centers-into-giga-scale-ai-super-factories) ·
[Spectrum-X page](https://www.nvidia.com/en-us/networking/spectrumx/)

**[8] Gemini Ultra trained synchronously across multiple datacenters.**
TPUv4 SuperPods (4,096 chips), "multiple datacenters… Google's network
latencies and bandwidths are sufficient to support the commonly used
synchronous training paradigm." The report says "multiple datacenters" —
it does not say how far apart; SemiAnalysis [4] places multi-DC training
within metro/regional spans. The exception that proves the engineering
bar, not a refutation of the distance cliff.
[arXiv:2312.11805, Gemini report](https://arxiv.org/pdf/2312.11805)

**[9] Hyperscale AI back-ends standardized on RoCEv2/Ethernet.** Meta: two
24,576-GPU H100 clusters, one RoCE (Arista 7800), one InfiniBand; **Llama 3
405B trained on the RoCE cluster, 16K H100s, 400 Gbps per GPU**. Oracle OCI
superclusters: RoCEv2, quoted **2.5–9.1 µs** cluster-network latency.
[Meta engineering](https://engineering.fb.com/2024/03/12/data-center-engineering/building-metas-genai-infrastructure/) ·
[Llama 3 paper §3.3](https://arxiv.org/html/2407.21783v3) ·
[Oracle OCI](https://blogs.oracle.com/cloud-infrastructure/now-ga-largest-ai-supercomputer-oci-nvidia-h200)

**[10] Ring all-reduce cost model.** Bandwidth term 2(n−1)/n · S/B across
2(n−1) transfer steps, each step adding one hop latency — the standard
α-β model. Pins `ring_allreduce_ms`; `tests/test_physics.py` asserts both
terms exactly.
[NVIDIA nccl-tests, PERFORMANCE.md](https://github.com/NVIDIA/nccl-tests/blob/master/doc/PERFORMANCE.md) ·
Thakur, Rabenseifner & Gropp, IJHPCA 19(1), 2005

## RAN timing & the fronthaul gate

**[11] O-RAN 7.2x fronthaul one-way budget ≈ 100 µs.** WG4 CUS-plane delay
management; at 4.9 µs/km this is the ~20.4 km C-RAN radius that
`_latency_gate` enforces for R0 workloads (verified via engineering
sources; the WG4 spec text itself is member-gated). Timing: PTP telecom
profile **G.8275.1 (02/2026 edition)**, ±1.5 µs PRTC-to-antenna end-to-end
per G.8271.1.
[ITU-T G.8275.1 (2026-02)](https://www.itu.int/rec/T-REC-G.8275.1-202602-I) ·
[Comcores, O-RAN fronthaul MACsec (PDF)](https://www.comcores.com/wp-content/uploads/2023/12/MACsec-Security-for-O-RAN-Fronthaul.pdf)

**[12] NVIDIA ARC-Compact — the tower-tier reference part.** 2RU,
half-depth, Grace C1 + **L4 GPU at 72 W**, NEBS3/GR-63/GR-1089 compliant,
positioned for D-RAN cell sites; announced May 18, 2025, availability
"later in 2025" via ODMs. Pins the tower tier's GPU class in `tiers.py`
and `fleet.py`.
[NVIDIA blog](https://developer.nvidia.com/blog/deploy-ai-ran-at-cell-sites-with-nvidia-arc-compact/)

**[13] Aerial MIG co-residency is real but narrow.** NVIDIA Aerial 25-2:
RAN on a `4g.48g` MIG slice + LLM on `3g.48gb`, "validation was done up to
11C" (11 cells) on GH200. The SLA-aware Device–RAN–Cloud paper
(arXiv:2602.23722, Feb 2026) co-hosted Aerial O-DU + vLLM on fixed
2×`3g.48gb` MIG partitions — never sharing a slice. MIG gives dedicated
SMs, L2 banks, memory controllers; reconfiguration requires idle
instances. Pins the "pinned MIG slice" framing of `ran-l1-baseband` and
the non-preemptible RAN floor.
[Aerial 25-2 release notes](https://docs.nvidia.com/aerial/cuda-accelerated-ran/25-2/aerial_cubb/release_notes/limitations.html) ·
[arXiv:2602.23722](https://arxiv.org/html/2602.23722v1) ·
[MIG User Guide](https://docs.nvidia.com/datacenter/tesla/mig-user-guide/concepts.html)

## Site envelopes & fleet arithmetic

**[14] Macro cell-site power: ~2.5–19 kW envelope, −48 V DC, 2–8 h
battery.** Typical 3-sector LTE site 2.5–10 kW; 5G-era multi-band
massive-MIMO sites ~14 kW average / up to 19 kW peak. Battery backup
typically 2–4 h, designed up to 8 h. The tower tier's **1.5 kW AI
headroom** is the rectifier margin left after the radio load at a typical
site — deliberately generous to the tower (a real site may have less).
[WirelessMoves](https://blog.wirelessmoves.com/2019/08/cell-site-power-consumption.html) ·
[DCD, self-sufficient cell towers](https://www.datacenterdynamics.com/en/analysis/self-sufficient-cell-towers-when-will-cell-sites-go-off-grid-en-masse/) ·
[EnerSys macro-cell power](https://www.enersys.com/en/industries/communications-networks/macro-cells/)

**[15] Modern AI racks are liquid, 40–130 kW.** GB200 NVL72 ≈ 120 kW
nominal (HPE datasheet: 132 kW max = 115 kW liquid + 17 kW air).
Direct-to-chip cold plates capture ~70–75% of rack heat at pPUE
~1.02–1.03; practical air-cooling ceiling ~40–50 kW/rack; single-phase D2C
serves current ~1–1.5 kW parts with ~1.5 kW as the widely cited transition
toward two-phase. Pins `cooling`/`max_gpu_watts` per tier and
`AIR_COOLED_MAX_GPU_W` (350 W: the heaviest parts sold for air-cooled edge
servers are L40S-class).
[HPE GB200 NVL72](https://buy.hpe.com/us/en/compute/rack-scale-system/nvidia-nvl-system/nvidia-gb200-nvl72-by-hpe/p/1014890104) ·
[Vertiv, liquid cooling options](https://www.vertiv.com/en-us/solutions/learn-about/liquid-cooling-options-for-data-centers/) ·
[Introl, 50 kW thermal limits](https://introl.com/blog/liquid-cooling-gpu-data-centers-50kw-thermal-limits-guide) ·
[IDTechEx, two-phase cold plates](https://www.idtechex.com/en/research-article/two-phase-cold-plate-cooling-will-take-off-as-early-as-2026-2027/34068)

**[16] GPU throughput calibration (dense FP8).** L4: 72 W, 242 TFLOPS
dense FP8 (485 with sparsity). H100 SXM: 700 W, 1,979 TFLOPS dense FP8
(3,958 sparse). `fleet.py` uses dense figures for both — the comparison is
like-for-like. NVIDIA
[L4](https://www.nvidia.com/en-us/data-center/l4/) and
[H100](https://www.nvidia.com/en-us/data-center/h100/) datasheets.

**[17] ~7 million physical cell sites globally.** Omdia estimate (~10M
logical sites), as of 2020. The default 30,000-tower fleet in `fleet.py`
is an illustrative national mobile operator, not any specific carrier.
[Operator Watch, citing Omdia](https://www.operatorwatch.com/2020/08/how-many-cell-towers-base-stations.html)

**[18] Egress economics behind `INGEST_COSTLY_GBPS`.** 0.25 Gbps sustained
≈ 81 TB/month. At cloud list egress pricing (~$0.05–0.09/GB tiered) that
is roughly $4,000–7,000/month per stream — list-price arithmetic, not a
measured invoice; committed/private-interconnect rates run lower, which is
why the verdict is COSTLY, never BLOCKED.
[AWS data transfer pricing](https://aws.amazon.com/ec2/pricing/on-demand/)

## AI-RAN state of the world (context for the workload library)

**[19] SoftBank AITRAS.** Fujisawa (Nov 2024): GH200 nodes each running 20
cells at 100 MHz, 816 Mbps DL, carrier-grade, with concurrent AI tenancy —
the up-to-3× utilization figure is MIG multi-tenancy modeling (33%→~100%),
not measured throughput. Santa Clara outdoor trial (Oct 29, 2025): full 5G
PHY in software on GPUs, 16-layer MU-MIMO DL, ~3× spectral efficiency vs
the 4-layer config; commercial from 2026 onward.
[SoftBank press release](https://www.softbank.jp/en/corp/news/press/sbkk/2025/20251029_02/) ·
[NVIDIA blog](https://developer.nvidia.com/blog/ai-ran-goes-live-and-unlocks-a-new-ai-opportunity-for-telcos/)

**[20] Nokia AI-native RAN platform (July 2026).** anyRAN + NVIDIA: GPU
plug-in unit, standalone AI-RAN node, or COTS GPU servers; spectral
efficiency claims >20% now / 50% by 2027 / >100% by 2028 (analysts
skeptical); **pilots late 2026, commercial 2027**. NVIDIA took a $1B
equity stake (Oct 28, 2025).
[ComSoc analysis](https://techblog.comsoc.org/2026/07/15/analysis-nokias-new-ai-ran-platform-and-standalone-ai-ran-node-with-nvidia-gpus/) ·
[Nokia MWC26 release](https://www.nokia.com/newsroom/nokia-accelerates-ai-ran-momentum-with-new-partnerships-driving-path-to-ai-native-6g-mwc26/)

**[21] AI-for-RAN gains do not require GPUs.** Two separate Ericsson
trials: AT&T (Mar 2026) — up to 20% DL throughput from AI link adaptation
on Cloud RAN running on **Intel Xeon 6 SoC**; T-Mobile (May 2026, ~43
sites) — ~10% spectral efficiency / up to 15% DL on Ericsson's own RAN
Compute silicon. Keeps the workload library honest: `ran-l1-baseband` on a
GPU is a choice, not a necessity.
[Ericsson/AT&T](https://www.ericsson.com/en/news/2026/3/att-and-ericsson-enhance-cloud-ran-performance-with-ai-native-software-on-intel-xeon-6-soc) ·
[T-Mobile/Ericsson](https://www.prnewswire.com/news-releases/t-mobile-5g-advanced-network-achieves-world-first-with-ericsson-ai-ran-innovation-302766471.html)

**[22] AI-RAN Alliance: 132 members (Feb 26, 2026).** Founded MWC
Barcelona Feb 2024 with 11 members; workstreams AI-for-RAN / AI-and-RAN /
AI-on-RAN. The "$5 revenue per $1 AI-RAN capex" figure is an NVIDIA
projection (GB200 NVL2 basis, 5-year horizon), not measured.
[AI-RAN Alliance MWC 2026](https://ai-ran.org/press-releases/mwc-2026-momentum) ·
[NVIDIA blog](https://developer.nvidia.com/blog/ai-ran-goes-live-and-unlocks-a-new-ai-opportunity-for-telcos/)

**[23] Where the experts land — hierarchical placement.** IEEE Spectrum
(Aug 3, 2026): Kim Kyllesbech Larsen — trials prove AI can run *alongside*
the RAN, "not necessarily that AI needs to be deeply integrated";
Mérouane Debbah — "a more credible architecture is hierarchical and
heterogeneous: very small models inside radios… more capable models at
edge sites; and large foundation or agentic models at regional or central
levels." This repo is that sentence, made executable.
[IEEE Spectrum](https://spectrum.ieee.org/ai-ran-6g)

## The neocloud side of the demark

**[24] CoreWeave's tenant fabric is EVPN/VXLAN on DPUs — IP, not RDMA, at
the demark.** Clos leaf-spine, BGP-unnumbered EVPN underlay, EVPN Type-5
routes into per-tenant VRFs/VXLAN VNIs; BlueField-3 DPU on every
bare-metal node running the Nimbus control/data plane in isolation from
the host. Direct Connect offers multi-location redundancy.
[CoreWeave security architecture](https://docs.coreweave.com/docs/security/architecture) ·
[Nimbus](https://docs.coreweave.com/docs/platform/fleet-management/nimbus)

**[25] SemiAnalysis ClusterMAX 2.0 (Nov 6, 2025).** The de-facto neocloud
quality bar: CoreWeave sole Platinum (as of the Nov 2025 v2.0
update); documented failure modes at lower tiers include GPUDirect RDMA
disabled and PCIe ACS left on — evidence that the "GPU-first cloud" label
spans a wide competence range.
[ClusterMAX 2.0](https://newsletter.semianalysis.com/p/clustermax-20-the-industry-standard)

**[26] Time-to-power is the edge's opening.** Northern Virginia
interconnection runs up to ~7 years application-to-energization (national
average ~4). ERCOT alone tracked ~226 GW of large-load interconnection
requests as of Nov 2025 (~¾ data centers; observers flag duplicative
"phantom" requests). Aggregation hubs sit on *existing* telecom power
entitlements — the only tier that skips the queue.
[2026 market guide](https://www.constructionowners.com/insights/how-long-it-actually-takes-to-power-a-data-center-in-2026-a-u-s-market-by-market-reality-check) ·
[Latitude Media / ERCOT](https://www.latitudemedia.com/news/ercots-large-load-queue-has-nearly-quadrupled-in-a-single-year/)

**[27] Carrier transport between PoPs: SRv6 + BGP-EVPN is mature.** RFC
8986 (SRv6 network programming, 2021), RFC 9252 (BGP overlay services over
SRv6, 2022); EANTC 2025 multi-vendor interop: all 9 SRv6 vendors support
µSID, EVPN-over-SRv6 tested, 5G x-haul slicing validated. TI-LFA (RFC
9855) sub-50 ms protection is a vendor design target, verified in vendor
docs, not an EANTC measurement. BGP CAR (RFC 9871) and BGP CT (RFC 9832)
are 2025 *Experimental* RFCs — inter-domain intent routing is younger than
the marketing suggests.
[RFC 8986](https://www.rfc-editor.org/info/rfc8986) ·
[RFC 9252](https://www.rfc-editor.org/info/rfc9252) ·
[EANTC 2025 report](https://wiki.eantc.de/wiki/publicreports/view/Main/Multi-Vendor%20MPLS%20%26%20SDN%20Interoperability%20Test%20Report%202025/SRv6)

**[28] SRv6 reaches into the AI back-end itself.**
draft-filsfils-srv6ops-srv6-ai-backend (individual Informational draft):
µSID-encoded deterministic paths for RoCEv2 flows; SONiC 202505 shipped
SRv6 µSID support for AI back-ends. The IP/SRv6 control plane and the RDMA
data plane are converging *inside* the DC — which is exactly why the
demark discipline (RDMA stays home, IP crosses) needs stating.
[IETF draft](https://datatracker.ietf.org/doc/draft-filsfils-srv6ops-srv6-ai-backend/) ·
[SONiC 202505](https://sonicfoundation.dev/sonic-202505-powering-ai-fabrics-and-enterprise-networks-with-precision-and-insight/)
