"""Placement-engine invariants: the matrix must reproduce the published
qualitative consensus (edge verdicts for inference, central for training)
from the gates alone — no workload is hard-coded to a tier."""

import sys
import unittest

sys.path.insert(0, __file__.rsplit("/tests/", 1)[0])

from continuum.fleet import compare  # noqa: E402
from continuum.place import evaluate, place  # noqa: E402
from continuum.tiers import CENTRAL, HUB, LADDER, METRO_POP, TOWER, custom  # noqa: E402
from continuum.workloads import LIBRARY, workload  # noqa: E402


def verdict(wname, tier):
    return evaluate(workload(wname), tier)


class TestHardGates(unittest.TestCase):
    def test_frontier_training_only_central(self):
        p = place(workload("frontier-pretrain"))
        self.assertEqual(p.recommended, "central-factory")
        for v in p.verdicts[:-1]:
            self.assertEqual(v.status, "BLOCKED")

    def test_no_collectives_leave_the_pod_at_towers(self):
        # Anything needing a pod fabric is blocked at the tower.
        for name in ("video-vlm", "medium-llm-serving",
                     "sovereign-inference-70b"):
            self.assertEqual(verdict(name, TOWER).status, "BLOCKED", name)

    def test_ran_l1_bounded_by_fronthaul(self):
        # DU can live at tower or hub (C-RAN), never past the ~20 km
        # eCPRI budget.
        self.assertTrue(verdict("ran-l1-baseband", TOWER).ok)
        self.assertTrue(verdict("ran-l1-baseband", HUB).ok)
        self.assertEqual(verdict("ran-l1-baseband", METRO_POP).status,
                         "BLOCKED")
        self.assertEqual(verdict("ran-l1-baseband", CENTRAL).status,
                         "BLOCKED")

    def test_sovereign_never_central(self):
        for w in LIBRARY:
            if w.sovereign:
                self.assertEqual(evaluate(w, CENTRAL).status, "BLOCKED",
                                 w.name)

    def test_hot_gpus_never_at_towers(self):
        # 700 W parts exceed the tower's air-cooled envelope.
        self.assertEqual(verdict("lora-finetune", TOWER).gate, "fabric")
        v = evaluate(workload("sovereign-inference-70b"), TOWER)
        self.assertEqual(v.status, "BLOCKED")


class TestConsensusMatrix(unittest.TestCase):
    """The published qualitative matrix, reproduced from gates."""

    def test_edge_feasible_set(self):
        # CV, voice, RAG, telemetry run at hub or below.
        for name in ("realtime-cv", "agentic-voice", "rag-slm-inference",
                     "telemetry-anomaly"):
            self.assertTrue(verdict(name, HUB).ok, name)

    def test_central_only_set(self):
        for name in ("frontier-pretrain", "regional-batch-train"):
            self.assertFalse(verdict(name, TOWER).ok, name)
            self.assertFalse(verdict(name, HUB).ok, name)

    def test_every_workload_has_a_home(self):
        for w in LIBRARY:
            self.assertIsNotNone(place(w).recommended, w.name)

    def test_centralize_by_default(self):
        # A workload with no forcing constraint recommends the top tier.
        p = place(workload("lora-finetune"))
        self.assertEqual(p.recommended, "central-factory")
        self.assertEqual(p.forced_by, "")

    def test_forced_placements_name_their_forcer(self):
        for w in LIBRARY:
            p = place(w)
            if p.recommended not in (None, "central-factory"):
                self.assertNotEqual(p.forced_by, "", w.name)


class TestTowerThesis(unittest.TestCase):
    """The headline finding: under default envelopes the tower is never
    the recommended tier — the hub wins everything edgeward — and the
    tower earns its place only when the hub moves out of fronthaul reach
    (rural geometry)."""

    def test_tower_never_recommended_by_default(self):
        for w in LIBRARY:
            self.assertNotEqual(place(w).recommended, "tower", w.name)

    def test_rural_geometry_revives_the_tower(self):
        # Hub 30 km away: fronthaul (100 us ~ 20.4 km) can no longer
        # reach it, so RAN L1 must fall back to the tower.
        rural_hub = custom("aggregation-hub", km_to_user=30.0)
        ladder = (TOWER, rural_hub, METRO_POP, CENTRAL)
        p = place(workload("ran-l1-baseband"), ladder)
        self.assertEqual(p.recommended, "tower")

    def test_fleet_capability_gap(self):
        s = compare().summary()
        # The hub fleet runs on LESS total power...
        self.assertLess(s["hub_ai_mw"], s["tower_ai_mw"])
        # ...delivers more schedulable FP8 per MW...
        self.assertGreater(s["hub_capability_per_mw_x"], 5.0)
        # ...and hosts strictly more workload classes.
        self.assertGreater(s["hub_hostable"], s["tower_hostable"])


class TestGateOrthogonality(unittest.TestCase):
    def test_relaxing_power_alone_does_not_unlock_training(self):
        # Even a fantasy 1 MW tower cannot host synchronous training:
        # the fabric gate holds regardless of power.
        big_tower = custom("tower", ai_power_kw=1000.0,
                           max_gpu_watts=1400.0)
        v = evaluate(workload("frontier-pretrain"), big_tower)
        self.assertEqual(v.status, "BLOCKED")
        self.assertEqual(v.gate, "fabric")

    def test_costly_is_not_blocked(self):
        v = verdict("realtime-cv", CENTRAL)
        self.assertEqual(v.status, "COSTLY")
        self.assertTrue(v.ok)


if __name__ == "__main__":
    unittest.main(verbosity=2)
