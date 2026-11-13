import json
import unittest

from moat import chain, onchain


def block(height, ts_ms, receipts, supply="1000000000000000000000000000000000"):
    """Minimal neardata-shaped block. receipts: (receiver, status, logs, predecessor)."""
    return {
        "block": {"header": {"height": height, "hash": f"h{height}",
                             "timestamp_nanosec": str(ts_ms * 10 ** 6), "total_supply": supply}},
        "shards": [{"receipt_execution_outcomes": [
            {"receipt": {"receiver_id": rcv, "predecessor_id": pred},
             "execution_outcome": {"outcome": {"status": st, "logs": logs}}}
            for rcv, st, logs, pred in receipts]}],
    }


def ev(name, data=None):
    return "EVENT_JSON:" + json.dumps({"standard": "dip4", "event": name, "data": data or []})


class Summarize(unittest.TestCase):
    def test_counts_only_successful_intents_receipts(self):
        b = block(10, 1000, [
            ("intents.near", {"SuccessValue": ""}, [ev("intents_executed"), ev("token_diff",
             [{"account_id": "solver.near"}, {"account_id": "user.near"}])], "relay.near"),
            ("intents.near", {"Failure": {}}, [ev("intents_executed")], "x.near"),
            ("other.near", {"SuccessValue": ""}, [ev("intents_executed")], "y.near"),
        ])
        s = onchain.summarize(b)
        self.assertEqual(s["intents_receipts"], 1)
        self.assertEqual(s["intents_failed"], 1)
        self.assertEqual(s["receipts_all"], 3)
        self.assertEqual(s["events"], {"intents_executed": 1, "token_diff": 1})
        self.assertEqual(s["swap_accounts"], ["solver.near", "user.near"])
        self.assertEqual(s["predecessors"], 1)

    def test_unparseable_log_is_counted_not_fatal(self):
        b = block(1, 0, [("intents.near", {"SuccessValue": ""}, ["EVENT_JSON:{bad"], "a")])
        self.assertEqual(onchain.summarize(b)["events"], {"_unparsed": 1})


class Analyses(unittest.TestCase):
    def test_solver_concentration_ignores_one_off_accounts(self):
        rows = {}
        for h in range(10):
            accts = ["s1"] * 3 + ["s2"] + [f"user{h}"]
            rows[h] = dict(ts=1000 + h, swap_accounts=accts)
        r = chain.solver_concentration(rows, since_ms=0, min_blocks=3)
        self.assertEqual(r["repeat_counterparties"], 2)
        self.assertAlmostEqual(r["top1"], 0.75)
        self.assertAlmostEqual(r["hhi"], 0.75 ** 2 + 0.25 ** 2)

    def test_supply_growth_is_annualised(self):
        y = int(365.25 * 86400 * 1000)
        rows = {1: dict(height=1, ts=0, total_supply=str(100 * 10 ** 24)),
                2: dict(height=2, ts=y, total_supply=str(102 * 10 ** 24))}
        plan = {"blocks": [{"window": "supply", "height": 1}, {"window": "supply", "height": 2}]}
        s = chain.supply(rows, plan)
        self.assertAlmostEqual(s["issued"], 2.0)
        self.assertAlmostEqual(s["growth"], 0.02)

    def test_correlation(self):
        self.assertAlmostEqual(chain.corr([1, 2, 3], [2, 4, 6]), 1.0)
        self.assertAlmostEqual(chain.corr([1, 2, 3], [3, 2, 1]), -1.0)

    def test_run_probability_matches_enumeration(self):
        import itertools
        n, length, q = 8, 3, 0.3
        exact = 0.0
        for seq in itertools.product([0, 1], repeat=n):  # 1 = empty block
            if "1" * length in "".join(map(str, seq)):
                exact += q ** sum(seq) * (1 - q) ** (n - sum(seq))
        self.assertAlmostEqual(chain.p_run_anywhere(n, length, q), exact)
        self.assertAlmostEqual(chain.p_run_anywhere(5, 1, 0.5), 1 - 0.5 ** 5)


if __name__ == "__main__":
    unittest.main()
