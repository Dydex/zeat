"""Known-answer tests for the estimator, plus a reproducibility check."""

import datetime as dt
import json
import math
import random
import unittest

from zeat import analysis
from zeat.fetch import ROOT

D = dt.date


def make_panel(effect, event=D(2026, 3, 2), weeks_pre=40, weeks_post=8, seed=0):
    """Treated = 0.5*A + 0.5*B (+ level shift) with a known post-event effect."""
    rng = random.Random(seed)
    start = event - dt.timedelta(7 * weeks_pre)
    days = 7 * (weeks_pre + weeks_post)
    a, b, c = {}, {}, {}
    la, lb, lc = 10.0, 11.0, 9.0
    treated = {}
    for i in range(days):
        d = start + dt.timedelta(i)
        if i % 7 == 0:
            la += rng.gauss(0, 0.08)
            lb += rng.gauss(0, 0.08)
            lc += rng.gauss(0, 0.08)
        a[d], b[d], c[d] = math.exp(la), math.exp(lb), math.exp(lc)
        lt = 2.0 + 0.5 * la + 0.5 * lb + (effect if d >= event else 0.0)
        treated[d] = math.exp(lt)
    return {"treated": treated, "a": a, "b": b, "c": c}, event, start + dt.timedelta(days - 1)


class SyntheticControlEvent(unittest.TestCase):
    def test_recovers_injected_loss(self):
        series, event, last = make_panel(effect=math.log(0.7))
        r = analysis.sc_event(series, "treated", ["a", "b", "c"], event, 26, 8, range(8), last)
        self.assertAlmostEqual(r["effect"], math.log(0.7), places=2)
        self.assertAlmostEqual(r["weights"]["a"], 0.5, places=2)
        self.assertAlmostEqual(r["weights"]["b"], 0.5, places=2)
        self.assertLess(r["pre_rmspe"], 0.01)

    def test_no_effect_gives_zero(self):
        series, event, last = make_panel(effect=0.0, seed=5)
        r = analysis.sc_event(series, "treated", ["a", "b", "c"], event, 26, 8, range(8), last)
        self.assertAlmostEqual(r["effect"], 0.0, places=2)

    def test_placebo_windows_end_before_event(self):
        series, event, last = make_panel(effect=math.log(0.7))
        pl = analysis.placebo_in_time(series, "treated", ["a", "b", "c"], event, 26, 8, range(8))
        self.assertTrue(pl)
        for p in pl:
            fake = D.fromisoformat(p["event"])
            self.assertLessEqual(fake + dt.timedelta(7 * 8), event)
            # an untreated window should show no effect
            self.assertAlmostEqual(p["effect"], 0.0, places=2)

    def test_donor_missing_post_week_is_excluded(self):
        series, event, last = make_panel(effect=0.0)
        for i in range(7):
            series["c"].pop(event + dt.timedelta(14 + i), None)
        r = analysis.sc_event(series, "treated", ["a", "b", "c"], event, 26, 8, range(8), last)
        self.assertNotIn("c", r["weights"])


class Reproducible(unittest.TestCase):
    """The committed results.json must be exactly what the snapshot produces."""

    def test_results_match_snapshot(self):
        committed = ROOT / "results" / "results.json"
        if not committed.exists():
            self.skipTest("no committed results yet")
        fresh = analysis.public(analysis.run())
        self.assertEqual(json.loads(json.dumps(fresh, sort_keys=True)),
                         json.loads(committed.read_text()))


if __name__ == "__main__":
    unittest.main()
