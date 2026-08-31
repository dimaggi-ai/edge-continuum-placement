"""The validation registry: every point reproduces, the kinds stay honest,
and — the part that matters — a broken engine makes it go RED.

An earlier version of this suite asserted only that the registry passes.
It did, with the latency gate, the power gate or the fabric gate deleted
outright. The mutation tests below delete each gate in turn and require
the registry to fail; without them "all points PASS" is a statement about
the registry, not about the engine.
"""

import unittest
from unittest import mock

import validation
from continuum import place as place_mod


class TestValidationRegistry(unittest.TestCase):
    POINTS = validation.points()

    def test_every_point_reproduces(self):
        for p in self.POINTS:
            with self.subTest(point=p.name):
                self.assertTrue(
                    p.ok,
                    f"{p.name}: expected {p.expected} +/- {p.tolerance} "
                    f"{p.ref}, model gives {p.actual}")

    def test_all_three_kinds_present(self):
        self.assertEqual({p.kind for p in self.POINTS},
                         {"calibrated", "emergent", "sanity"})

    def test_evidence_points_cite_sources_and_sanity_points_do_not(self):
        for p in self.POINTS:
            with self.subTest(point=p.name):
                if p.kind in ("calibrated", "emergent"):
                    self.assertTrue(p.ref.startswith("["), p.name)
                else:
                    self.assertEqual(p.ref, "-", p.name)

    def test_validate_reports_all_ok(self):
        pts, ok = validation.validate()
        self.assertTrue(ok)
        self.assertEqual(len(pts), len(self.POINTS))


class TestBrokenEngineFailsTheRegistry(unittest.TestCase):
    """Negative controls: delete a gate, the registry must notice."""

    def _registry_fails_with(self, gate_name):
        with mock.patch.object(place_mod, gate_name,
                               lambda w, t: None):
            _, ok = validation.validate()
        return not ok

    def test_deleting_the_latency_gate_fails_the_registry(self):
        self.assertTrue(self._registry_fails_with("_latency_gate"))

    def test_deleting_the_power_gate_fails_the_registry(self):
        self.assertTrue(self._registry_fails_with("_power_gate"))

    def test_deleting_the_fabric_gate_fails_the_registry(self):
        self.assertTrue(self._registry_fails_with("_fabric_gate"))

    def test_deleting_the_gravity_gate_fails_the_registry(self):
        with mock.patch.object(place_mod, "_gravity_gate",
                               lambda w, t: (None, None)):
            _, ok = validation.validate()
        self.assertFalse(ok)

    def test_breaking_the_rtt_helper_fails_the_registry(self):
        """rtt_ms losing its round trip must be caught, not absorbed."""
        with mock.patch.object(validation, "rtt_ms",
                               lambda km: km * validation.FIBER_US_PER_KM / 1000.0):
            _, ok = validation.validate()
        self.assertFalse(ok)

    def test_no_tolerance_is_wide_enough_to_be_meaningless(self):
        for p in validation.points():
            with self.subTest(point=p.name):
                if p.expected:
                    self.assertLessEqual(
                        p.tolerance / abs(p.expected), 0.20,
                        f"{p.name}: +/-{p.tolerance} on {p.expected} is too "
                        f"wide to fail")

    def test_declined_anchors_are_disclosed(self):
        self.assertGreaterEqual(len(validation.DECLINED), 4)
        for what, why in validation.DECLINED:
            self.assertTrue(what and why)

    def test_registry_has_not_silently_shrunk(self):
        self.assertEqual(len(validation.points()), 8)


class TestPublicGeography(unittest.TestCase):
    """The haversine helper itself, against known distances."""

    def test_known_distances(self):
        # Public great-circle distances, +/- 1% of widely published figures.
        self.assertAlmostEqual(
            validation.great_circle_km("New York", "San Francisco"),
            4129.0, delta=45.0)
        self.assertAlmostEqual(
            validation.great_circle_km("London", "Paris"), 344.0, delta=5.0)

    def test_distance_is_symmetric_and_zero_on_self(self):
        a = validation.great_circle_km("Tokyo", "Osaka")
        b = validation.great_circle_km("Osaka", "Tokyo")
        self.assertAlmostEqual(a, b, places=9)
        self.assertAlmostEqual(
            validation.great_circle_km("Tokyo", "Tokyo"), 0.0, places=9)


if __name__ == "__main__":
    unittest.main()
