"""Workload profiles for continuum placement.

Each profile reduces a workload to the variables that decide placement:
network latency budget, access path, GPU working set, collective class,
data gravity (including raw ingest bandwidth), sovereignty, and the
resilience class it rides on. The library mirrors the workload matrix in
docs/study.md; every profile is overridable.

`latency_sla_ms` is the NETWORK budget (round trip) the service can spend —
i.e. the user-facing SLA net of model/compute time, which is placement-
invariant. `access_rtt_ms` is the fixed access-path cost (5G air interface,
local wired camera LAN, internet last mile) paid regardless of tier.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Workload:
    name: str
    latency_sla_ms: float       # network RTT budget; inf = batch
    access_rtt_ms: float        # fixed access-path RTT (air interface etc.)
    gpus: int
    gpu_watts: float            # per-GPU TDP class the job actually needs
    # 'none'  - independent GPUs (or a single GPU / MIG slice)
    # 'pod'   - collectives within <=64 GPUs (tensor/pipeline in one pod)
    # 'large' - synchronous collectives across hundreds-thousands of GPUs
    collective: str
    # 'local' | 'mixed' | 'central' - where the data the job consumes lives
    data_gravity: str
    # Raw local data the job must ingest continuously (camera feeds, RF
    # telemetry). Hauling this to a distant tier is possible but costly.
    ingest_gbps: float = 0.0
    # Residency pin: must stay within the operator's regional footprint
    # (tower/hub/metro), never a remote central campus.
    sovereign: bool = False
    # Resilience class (see the airan-neocloud-resiliency repo):
    # R0 hard-real-time radio, R1 control, R2 tenant AI.
    resilience_class: str = "R2"
    note: str = ""


LIBRARY: tuple[Workload, ...] = (
    Workload("ran-l1-baseband", 0.2, 0.0, 1, 75.0, "none", "local",
             ingest_gbps=25.0, sovereign=True, resilience_class="R0",
             note="cuPHY-class TTI-loop processing on a pinned MIG slice; "
                  "gated by the ~100 us one-way eCPRI fronthaul budget"),
    Workload("ric-xapp-loop", 10.0, 0.0, 1, 75.0, "none", "local",
             resilience_class="R1",
             note="near-RT RIC control loop (10 ms - 1 s), E2 to the DU"),
    Workload("telemetry-anomaly", 100.0, 0.0, 1, 75.0, "none", "local",
             ingest_gbps=0.5,
             note="RAN/gNMI stream scoring; data already at the site"),
    Workload("realtime-cv", 20.0, 2.0, 1, 75.0, "none", "local",
             ingest_gbps=1.0,
             note="camera loops: intersections, industrial, safety"),
    Workload("agentic-voice", 100.0, 20.0, 1, 75.0, "none", "local",
             note="ASR/VAD/barge-in; net budget within a 150-300 ms "
                  "conversational SLA, 5G access"),
    Workload("rag-slm-inference", 100.0, 20.0, 1, 75.0, "none", "mixed",
             note="small/medium model + local index; one GPU or MIG slice"),
    Workload("sovereign-inference-70b", 150.0, 20.0, 4, 700.0, "pod", "local",
             sovereign=True,
             note="regulated inference pinned to the jurisdiction"),
    Workload("video-vlm", 100.0, 5.0, 8, 350.0, "pod", "local",
             ingest_gbps=4.0,
             note="multi-camera VLM / video search; L40-class pod"),
    Workload("medium-llm-serving", 100.0, 20.0, 8, 700.0, "pod", "mixed",
             note="70B-class tensor-parallel serving pod"),
    Workload("lora-finetune", float("inf"), 0.0, 8, 700.0, "pod", "mixed",
             note="parameter-efficient tuning on local data; checkpoint I/O"),
    Workload("regional-batch-train", float("inf"), 0.0, 512, 700.0, "large",
             "central", note="synchronous batch training, mid-scale"),
    Workload("frontier-pretrain", float("inf"), 0.0, 16_384, 700.0, "large",
             "central", note="Llama-405B-class synchronous pretraining"),
)


def workload(name: str) -> Workload:
    for w in LIBRARY:
        if w.name == name:
            return w
    raise KeyError(f"unknown workload {name!r}; "
                   f"know {[w.name for w in LIBRARY]}")
