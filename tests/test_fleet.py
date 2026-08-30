"""Fleet-arithmetic and CLI invariants."""

import contextlib
import io
import sys
import unittest

sys.path.insert(0, __file__.rsplit("/tests/", 1)[0])

from continuum.cli import main  # noqa: E402
from continuum.fleet import HUB_FLEET, TOWER_FLEET, compare  # noqa: E402


class TestFleetArithmetic(unittest.TestCase):
    def test_tower_is_fabric_bound_not_power_bound(self):
        # 1.5 kW would feed 15 L4s, but the box holds 2: the scheduling
        # quantum is set by the missing fabric, not the rectifier.
        self.assertEqual(TOWER_FLEET.gpus_per_site, 2)
        self.assertGreater(TOWER_FLEET.tier.power_gpus(72.0), 2)

    def test_hub_is_power_bound_below_its_fabric(self):
        # 50 kW feeds 52 H100s; the pod fabric could hold 64.
        self.assertEqual(HUB_FLEET.gpus_per_site, 52)
        self.assertLess(HUB_FLEET.gpus_per_site,
                        HUB_FLEET.tier.max_fabric_gpus)

    def test_totals(self):
        self.assertEqual(TOWER_FLEET.total_gpus, 60_000)
        self.assertEqual(HUB_FLEET.total_gpus, 15_600)
        self.assertAlmostEqual(TOWER_FLEET.total_ai_mw, 45.0)
        self.assertAlmostEqual(HUB_FLEET.total_ai_mw, 15.0)

    def test_summary_ratio_matches_parts(self):
        s = compare().summary()
        self.assertAlmostEqual(
            s["hub_capability_per_mw_x"],
            round(s["hub_pflops_per_mw"] / s["tower_pflops_per_mw"], 1),
            delta=0.1)


class TestCli(unittest.TestCase):
    def _run(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(list(argv))
        return code, out.getvalue()

    def test_matrix_runs(self):
        code, out = self._run("matrix")
        self.assertEqual(code, 0)
        self.assertIn("frontier-pretrain", out)

    def test_evaluate_exit_codes(self):
        code, _ = self._run("evaluate", "-w", "frontier-pretrain",
                            "-t", "central")
        self.assertEqual(code, 0)
        code, _ = self._run("evaluate", "-w", "frontier-pretrain",
                            "-t", "tower")
        self.assertEqual(code, 1)

    def test_physics_runs(self):
        code, out = self._run("physics", "--rate", "400", "--km", "600")
        self.assertEqual(code, 0)
        self.assertIn("NO", out)

    def test_fleet_runs(self):
        code, out = self._run("fleet")
        self.assertEqual(code, 0)
        self.assertIn("per MW", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
