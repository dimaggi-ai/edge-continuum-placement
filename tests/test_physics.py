"""Physics invariants, pinned to published data points (see REFERENCES.md)."""

import math
import sys
import unittest

sys.path.insert(0, __file__.rsplit("/tests/", 1)[0])

from continuum import physics  # noqa: E402


class TestPropagation(unittest.TestCase):
    def test_five_microsecond_rule(self):
        # ~4.9 us/km one way in SMF.
        self.assertAlmostEqual(physics.one_way_us(100), 490.0, delta=1.0)

    def test_coast_to_coast(self):
        # NY-SF 4,148 km fiber route: ~21 ms one-way, ~42 ms RTT (HPBN).
        self.assertAlmostEqual(physics.one_way_us(4148) / 1000, 20.3, delta=1.5)
        self.assertAlmostEqual(physics.rtt_ms(4148), 40.7, delta=3.0)

    def test_hollow_core_is_faster(self):
        self.assertLess(
            physics.one_way_us(100, physics.HOLLOW_CORE_US_PER_KM),
            physics.one_way_us(100))


class TestLosslessHeadroom(unittest.TestCase):
    def test_bifrost_testbed_point(self):
        # Bifrost (ICNP'23): 80 km / 100G testbed reserved ~9.5 MB of
        # headroom (~2x the one-way BDP, Bifrost's 2-Delta). Our 4.9 us/km
        # gives 392 us one-way -> headroom ~9.8 MB, within ~5%.
        self.assertAlmostEqual(physics.pfc_headroom_mb(100, 80), 9.5,
                               delta=0.5)

    def test_bifrost_simulation_point(self):
        # Bifrost: 400G / 600 km (one-way ~3 ms) -> headroom ~286 MB.
        # 2x one-way BDP at our propagation constant gives ~294 MB.
        self.assertAlmostEqual(physics.pfc_headroom_mb(400, 600), 286.0,
                               delta=15.0)

    def test_headroom_is_twice_one_way_bdp(self):
        self.assertAlmostEqual(
            physics.pfc_headroom_mb(400, 100),
            2.0 * physics.bdp_mb(400, 100))

    def test_ceiling_inverts_headroom(self):
        km = physics.pfc_max_lossless_km(400, 64.0)
        self.assertAlmostEqual(physics.pfc_headroom_mb(400, km), 64.0,
                               delta=0.01)

    def test_ceiling_shrinks_with_rate(self):
        self.assertGreater(physics.pfc_max_lossless_km(100, 64.0),
                           physics.pfc_max_lossless_km(800, 64.0))

    def test_ib_credit_km_point(self):
        # ~128 KB/VL at 100 Gbps covers ~1 km (Bifrost / US7952998).
        self.assertAlmostEqual(physics.ib_credit_max_km(100), 1.0, delta=0.2)


class TestCollectives(unittest.TestCase):
    SCN = physics.CollectiveScenario(
        n_ranks=16, payload_gb=1.0, inter_site_gbps=400.0, compute_ms=200.0)

    def test_ring_formula_terms(self):
        # Zero latency: pure bandwidth term 2(n-1)/n * S/B.
        t = physics.ring_allreduce_ms(16, 1.0, 400.0, 0.0)
        expect = 2 * 15 / 16 * (8.0 / 400.0) * 1000
        self.assertAlmostEqual(t, expect, delta=0.01)
        # Latency term adds 2(n-1) hops.
        t2 = physics.ring_allreduce_ms(16, 1.0, 400.0, 1000.0)
        self.assertAlmostEqual(t2 - t, 2 * 15 * 1.0, delta=0.01)

    def test_efficiency_monotone_in_distance(self):
        effs = [physics.sync_step_efficiency(self.SCN, km)
                for km in (0, 10, 100, 1000, 5000)]
        for a, b in zip(effs, effs[1:]):
            self.assertGreaterEqual(a, b)

    def test_near_complete_overlap_below_10km(self):
        # Corning (arXiv:2605.19169): near-complete overlap below 10 km.
        self.assertGreater(physics.sync_step_efficiency(self.SCN, 10), 0.97)

    def test_long_distance_cliff(self):
        # Distance must dominate: at 1000 km efficiency collapses even
        # though bandwidth is unchanged.
        self.assertLess(physics.sync_step_efficiency(self.SCN, 1000), 0.90)

    def test_bandwidth_cannot_buy_back_distance(self):
        # Corning: doubling bandwidth improved things <=0.66%. Use a
        # scenario whose bandwidth term is PARTIALLY exposed (56 ms of
        # ring bandwidth time vs 50 ms of compute) so doubling bandwidth
        # genuinely helps a little — and still does far less than
        # halving the distance does.
        tight = physics.CollectiveScenario(
            n_ranks=16, payload_gb=1.5, inter_site_gbps=400.0,
            compute_ms=50.0)
        wider_scn = physics.CollectiveScenario(
            n_ranks=16, payload_gb=1.5, inter_site_gbps=800.0,
            compute_ms=50.0)
        base = physics.sync_step_efficiency(tight, 1000)
        wider = physics.sync_step_efficiency(wider_scn, 1000)
        closer = physics.sync_step_efficiency(tight, 500)
        self.assertGreater(wider, base)          # bandwidth is not useless...
        self.assertGreater(closer - base, (wider - base) * 5)  # ...just weak


class TestDomains(unittest.TestCase):
    def test_ladder(self):
        self.assertEqual(physics.latency_domain(0.001), "intra-rack")
        self.assertEqual(physics.latency_domain(0.05), "intra-pod")
        self.assertEqual(physics.latency_domain(35), "metro")
        self.assertEqual(physics.latency_domain(600), "regional+")

    def test_metro_boundary_is_metrox_reach(self):
        # 40 km: the long-reach IB (MetroX-class) DWDM ceiling.
        self.assertTrue(physics.collectives_allowed(40))
        self.assertFalse(physics.collectives_allowed(41))

    def test_negative_distance_rejected(self):
        with self.assertRaises(ValueError):
            physics.latency_domain(-1)
        with self.assertRaises(ValueError):
            physics.one_way_us(-5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
