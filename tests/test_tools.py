"""Run with:  python -m pytest -v   (or)   python -m unittest discover -s tests -v"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.services.budget_tools import estimate_event_budget as est  # noqa: E402


class BudgetTests(unittest.TestCase):
    def test_case_1_seminar_refreshments(self):
        self.assertEqual(est("seminar_hall", 50, True, False), {
            "venue_cost": 3000, "refreshment_cost": 4000, "kit_cost": 0,
            "subtotal": 7000, "contingency": 700, "total": 7700,
            "approver": "Faculty Coordinator"})

    def test_case_2_auditorium_all_options(self):
        self.assertEqual(est("auditorium", 100, True, True), {
            "venue_cost": 8000, "refreshment_cost": 8000, "kit_cost": 12000,
            "subtotal": 28000, "contingency": 2800, "total": 30800,
            "approver": "Principal"})

    def test_case_3_capacity_exceeded(self):
        msg = est("seminar_hall", 101, False, False)["error"]
        self.assertIn("capacity", msg.lower())
        self.assertIn("100", msg)

    def test_auditorium_capacity_limits(self):
        self.assertNotIn("error", est("auditorium", 300, False, False))
        self.assertIn("capacity", est("auditorium", 301, False, False)["error"].lower())

    def test_unknown_venue(self):
        self.assertIn("Invalid venue", est("library", 10, False, False)["error"])

    def test_invalid_participants(self):
        for bad in (0, -5, 10.5, 10.0, "abc", "50", True, [5]):
            with self.subTest(bad=bad):
                self.assertIn("error", est("seminar_hall", bad, False, False))

    def test_missing_inputs(self):
        for args in ((None, 10, False, False), ("seminar_hall", None, False, False),
                     ("seminar_hall", 10, None, False), ("seminar_hall", 10, False, None)):
            with self.subTest(args=args):
                self.assertIn("Missing", est(*args)["error"])

    def test_invalid_booleans(self):
        for flag in ("yes", 1, 0, "true"):
            with self.subTest(flag=flag):
                self.assertIn("True or False", est("seminar_hall", 10, flag, False)["error"])
                self.assertIn("True or False", est("seminar_hall", 10, False, flag)["error"])

    def test_total_just_below_threshold_is_faculty(self):
        r = est("auditorium", 50, True, True)  # subtotal 18000 -> total 19800
        self.assertEqual((r["total"], r["approver"]), (19800, "Faculty Coordinator"))

    def test_total_just_above_threshold_is_principal(self):
        r = est("auditorium", 51, True, True)  # subtotal 18200 -> total 20020
        self.assertEqual((r["total"], r["approver"]), (20020, "Principal"))

    def test_exact_20000_is_not_reachable(self):
        # total = subtotal * 1.1, so 20000 would need subtotal 18181.82, which whole-number inputs can't make
        totals = set()
        for venue, cap in (("seminar_hall", 100), ("auditorium", 300)):
            for n in range(1, cap + 1):
                for r in (True, False):
                    for k in (True, False):
                        totals.add(est(venue, n, r, k)["total"])
        self.assertNotIn(20000, totals)

    def test_output_fields_and_rounding(self):
        r = est("seminar_hall", 1, True, True)
        self.assertEqual(list(r), ["venue_cost", "refreshment_cost", "kit_cost",
                                   "subtotal", "contingency", "total", "approver"])
        self.assertEqual((r["contingency"], r["total"]), (320.0, 3520.0))

    def test_venue_is_trimmed_and_case_insensitive(self):
        self.assertEqual(est(" Seminar_Hall ", 10, False, False)["subtotal"], 3000)


if __name__ == "__main__":
    unittest.main()
