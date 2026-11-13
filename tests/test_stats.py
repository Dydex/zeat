import math
import random
import unittest

from zeat import stats


class SimplexProjection(unittest.TestCase):
    def test_already_on_simplex_is_unchanged(self):
        w = stats.project_simplex([0.2, 0.3, 0.5])
        for a, b in zip(w, [0.2, 0.3, 0.5]):
            self.assertAlmostEqual(a, b)

    def test_result_is_on_simplex(self):
        rng = random.Random(1)
        for _ in range(200):
            v = [rng.uniform(-3, 3) for _ in range(rng.randint(1, 8))]
            w = stats.project_simplex(v)
            self.assertAlmostEqual(sum(w), 1.0, places=12)
            self.assertTrue(all(x >= 0 for x in w))

    def test_known_answer(self):
        # (2, 0) -> (1, 0); (0.5, 0.5, 2) -> (0, 0, 1)
        self.assertEqual(stats.project_simplex([2, 0]), [1.0, 0.0])
        self.assertEqual(stats.project_simplex([0.5, 0.5, 2]), [0.0, 0.0, 1.0])


class SyntheticControl(unittest.TestCase):
    def test_recovers_true_weights_and_intercept(self):
        rng = random.Random(42)
        T, true_w, c = 40, [0.6, 0.0, 0.4, 0.0], 1.7
        X = [[rng.gauss(0, 1) + 0.05 * t * (j + 1) for j in range(4)] for t in range(T)]
        y = [c + sum(w * x for w, x in zip(true_w, row)) for row in X]
        w, a = stats.synthetic_control(y, X)
        for got, want in zip(w, true_w):
            self.assertAlmostEqual(got, want, places=4)
        self.assertAlmostEqual(a, c, places=4)

    def test_weights_stay_on_simplex_when_target_is_outside_hull(self):
        rng = random.Random(3)
        X = [[rng.gauss(0, 1), rng.gauss(0, 1)] for _ in range(30)]
        y = [3 * r[0] - 2 * r[1] for r in X]  # not a convex combination
        w, _ = stats.synthetic_control(y, X)
        self.assertAlmostEqual(sum(w), 1.0, places=9)
        self.assertTrue(all(x >= -1e-12 for x in w))

    def test_single_donor(self):
        w, a = stats.synthetic_control([2, 3, 4], [[1], [2], [3]])
        self.assertEqual(w, [1.0])
        self.assertAlmostEqual(a, 1.0)


class Regression(unittest.TestCase):
    def test_ols_exact_line(self):
        a, b = stats.ols([0, 1, 2, 3], [1, 3, 5, 7])
        self.assertAlmostEqual(a, 1)
        self.assertAlmostEqual(b, 2)

    def test_block_bootstrap_covers_true_slope_and_is_deterministic(self):
        rng = random.Random(0)
        x = list(range(40))
        y = [0.5 * t + rng.gauss(0, 2) for t in x]
        lo, hi = stats.block_bootstrap_slope(x, y)
        self.assertLess(lo, 0.5)
        self.assertGreater(hi, 0.5)
        self.assertEqual((lo, hi), stats.block_bootstrap_slope(x, y))

    def test_quantile_matches_numpy_linear(self):
        self.assertEqual(stats.quantile([1, 2, 3, 4], 0.5), 2.5)
        self.assertAlmostEqual(stats.quantile([1, 2, 3, 4], 0.1), 1.3)

    def test_rmspe(self):
        self.assertAlmostEqual(stats.rmspe([3, 4]), math.sqrt(12.5))


if __name__ == "__main__":
    unittest.main()
