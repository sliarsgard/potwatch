import copy
import json
import pathlib
import unittest

from potwatch.history import summarize
from potwatch.rules import (CRIT, INFO, WARN, compare_networks, evaluate, grandpa_fault_tolerance, overall)

FIX = pathlib.Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIX / f"{name}.snapshot.json").read_text())


def codes(findings):
    return {f.code: f.severity for f in findings}


class RulesOnRealSnapshots(unittest.TestCase):
    """Snapshots captured from the public Portaldot V3 endpoints on 2026-10-28 23:56 UTC."""

    def test_testnet_stall_is_critical(self):
        c = codes(evaluate(load("portaldot-v3-testnet")))
        self.assertEqual(c["HEAD_STALL"], CRIT)
        self.assertEqual(c["RPC_ISOLATED"], CRIT)
        self.assertEqual(c["SMALL_VALIDATOR_SET"], WARN)

    def test_live_is_warn_not_crit(self):
        f = evaluate(load("portaldot-v3-live"))
        self.assertNotIn("HEAD_STALL", codes(f))
        self.assertEqual(overall(f), WARN)

    def test_open_grandpa_round_is_info_when_finality_keeps_up(self):
        self.assertEqual(codes(evaluate(load("portaldot-v3-live")))["GRANDPA_ROUND_OPEN"], INFO)

    def test_finality_lag_escalates(self):
        s = load("portaldot-v3-live")
        s["substrate"]["finalized"] = s["substrate"]["best"] - 60
        c = codes(evaluate(s))
        self.assertEqual(c.get("GRANDPA_MISSING_VOTES"), CRIT)

    def test_healthy_when_everything_fine(self):
        s = load("portaldot-v3-live")
        s["substrate"]["health"]["peers"] = 8
        s["substrate"]["validators"] = [f"v{i}" for i in range(5)]
        s["substrate"]["grandpa_round"]["best"]["precommits"]["missing"] = []
        s["substrate"]["grandpa_round"]["best"]["prevotes"]["missing"] = []
        s["evm"] = None
        s["explorer"] = None
        f = evaluate(s)
        self.assertIn("HEALTHY", codes(f))
        self.assertIn(overall(f), ("ok", "info"))  # info = healthy with notes

    def test_key_reuse_detected_and_not_on_disjoint_sets(self):
        a, b = load("portaldot-v3-testnet"), load("portaldot-v3-live")
        self.assertTrue(any(f.code == "KEY_REUSE_ACROSS_NETWORKS" for _, f in compare_networks([a, b])))
        b2 = copy.deepcopy(b)
        for k in ("validators", "babe_authorities", "grandpa_authorities"):
            b2["substrate"][k] = ["x" + v for v in b2["substrate"][k]]
        self.assertFalse(any(f.code == "KEY_REUSE_ACROSS_NETWORKS" for _, f in compare_networks([a, b2])))

    def test_fault_tolerance(self):
        self.assertEqual([grandpa_fault_tolerance(n) for n in (1, 2, 3, 4, 7, 10)], [0, 0, 0, 1, 2, 3])


class HistoryTests(unittest.TestCase):
    def test_summarize_detects_missed_slots_and_gap(self):
        rows = [{"number": i, "timestamp_ms": t, "slot": s, "authority_index": i % 2, "slot_kind": "primary"}
                for i, (t, s) in enumerate([(0, 100), (6000, 101), (12000, 102), (30000, 105), (36000, 106)])]
        h = summarize(rows)
        self.assertEqual(h["slots_missed"], 2)
        self.assertEqual(h["longest_gap"], {"after_block": 2, "seconds": 18.0})
        self.assertEqual(h["block_time_s"]["median"], 6.0)


if __name__ == "__main__":
    unittest.main()
