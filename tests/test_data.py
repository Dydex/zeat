import datetime as dt
import unittest

from moat import data

D = dt.date


def ts(d):
    return int(dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc).timestamp())


class ParseChart(unittest.TestCase):
    def test_zero_is_missing_and_snapshot_day_excluded(self):
        raw = {"totalDataChart": [[ts(D(2026, 1, 1)), 5], [ts(D(2026, 1, 2)), 0],
                                  [ts(D(2026, 1, 3)), 7]]}
        out = data.parse_chart(raw, before=D(2026, 1, 3))
        self.assertEqual(out, {D(2026, 1, 1): 5.0})


class EventWeeks(unittest.TestCase):
    def setUp(self):
        self.e = D(2026, 2, 23)
        self.daily = {self.e + dt.timedelta(i): 10.0 for i in range(21)}

    def test_full_week_sums(self):
        w = data.event_weeks(self.daily, self.e, 0, 3, last_day=self.e + dt.timedelta(20))
        self.assertEqual(w, {0: 70.0, 1: 70.0, 2: 70.0})

    def test_gap_days_scale_up_and_sparse_weeks_drop(self):
        d = dict(self.daily)
        for i in (0, 1):            # week 0: 5 of 7 observed -> kept, scaled
            del d[self.e + dt.timedelta(i)]
        for i in range(7, 11):      # week 1: 3 of 7 observed -> missing
            del d[self.e + dt.timedelta(i)]
        w = data.event_weeks(d, self.e, 0, 2, last_day=self.e + dt.timedelta(20))
        self.assertEqual(w[0], 70.0)
        self.assertIsNone(w[1])

    def test_incomplete_final_week_omitted(self):
        w = data.event_weeks(self.daily, self.e, 0, 3, last_day=self.e + dt.timedelta(19))
        self.assertNotIn(2, w)


if __name__ == "__main__":
    unittest.main()
