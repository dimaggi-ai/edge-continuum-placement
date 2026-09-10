import unittest
from dataclasses import replace
from continuum.tiers import HUB
from continuum.workloads import workload
from continuum.place import _power_gate


class CoolingEnvelope(unittest.TestCase):
    def test_air_is_not_a_universal_tdp_cutoff(self):
        w = workload('medium-llm-serving')
        self.assertIsNone(_power_gate(w, replace(HUB, cooling='air')))

    def test_boundary_and_sensitivity(self):
        w = workload('medium-llm-serving')
        for cooling in ('air', 'liquid'):
            for watts in (350, 699, 700, 701, 1400):
                for power in (5, 10, 50):
                    t = replace(HUB, cooling=cooling, max_gpu_watts=watts, ai_power_kw=power)
                    fits = watts >= w.gpu_watts and power * 1000 >= w.gpus * w.gpu_watts * 1.35
                    self.assertEqual(_power_gate(w, t) is None, fits)
