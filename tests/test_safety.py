from pathlib import Path
import unittest

from fillingline.plant import Bench
from fillingline.safety import SafetySystem
from fillingline.safety_check import CASES, markdown, run_all, run_case
from tools.safety_pl import evaluate, markdown as pl_markdown

ROOT = Path(__file__).resolve().parents[1]
HEALTHY = {"EStop": (True, True), "Guard": (True, True)}


class SafetyFunctionTests(unittest.TestCase):
    def setUp(self):
        self.system = SafetySystem()

    def scan(self, estop=(True, True), guard=(True, True), reset=False):
        return self.system.scan({"EStop": estop, "Guard": guard}, reset)

    def test_either_channel_trips_in_the_same_scan_and_latches(self):
        self.assertTrue(self.scan()["EStop"]["enabled"])
        self.assertFalse(self.scan(estop=(False, True))["EStop"]["enabled"])
        self.assertFalse(self.scan(estop=(True, True))["EStop"]["enabled"])  # Released, not yet reset.
        self.assertTrue(self.scan(guard=(True, True))["Guard"]["enabled"])

    def test_reset_needs_a_rising_edge_not_a_held_button(self):
        # Reset held through the trip and the release is not an edge, so it cannot clear the trip.
        self.scan(estop=(False, False), reset=True)
        self.assertFalse(self.scan(estop=(True, True), reset=True)["EStop"]["enabled"])
        self.assertFalse(self.scan(reset=False)["EStop"]["enabled"])
        self.assertTrue(self.scan(reset=True)["EStop"]["enabled"])

    def test_reset_is_refused_while_the_function_is_unhealthy(self):
        self.scan(guard=(False, False))
        self.assertFalse(self.scan(guard=(False, False), reset=True)["Guard"]["enabled"])
        self.assertFalse(self.scan(guard=(False, False), reset=False)["Guard"]["enabled"])
        self.assertTrue(self.scan(reset=True)["Guard"]["enabled"])

    def test_one_scan_disagreement_is_a_bounce_not_a_channel_fault(self):
        self.scan(estop=(True, False))
        self.assertFalse(self.system.functions["EStop"].channel_fault)
        self.scan()
        self.assertFalse(self.system.functions["EStop"].channel_fault)

    def test_two_scan_disagreement_latches_channel_fault_until_monitored_reset(self):
        self.scan(estop=(True, False))
        self.scan(estop=(True, False))
        self.assertTrue(self.system.functions["EStop"].channel_fault)
        self.assertFalse(self.scan(estop=(True, False), reset=True)["EStop"]["enabled"])  # Still disagree.
        self.scan(reset=False)
        state = self.scan(reset=True)
        self.assertTrue(state["EStop"]["enabled"])
        self.assertFalse(state["EStop"]["channel_fault"])

    def test_stuck_healthy_channel_is_caught_when_the_button_is_pressed(self):
        # Channel A reads healthy although the button is pressed: B opens, so the channels disagree.
        self.scan(estop=(True, False))
        state = self.scan(estop=(True, False))
        self.assertFalse(state["EStop"]["enabled"])
        self.assertTrue(state["EStop"]["channel_fault"])
        self.assertTrue(state["EStop"]["channels"]["A"])
        self.assertFalse(state["EStop"]["channels"]["B"])

    def test_emergency_stop_and_guard_are_independent(self):
        state = self.scan(guard=(False, True))
        self.assertTrue(state["EStop"]["enabled"])
        self.assertFalse(state["Guard"]["enabled"])
        self.assertTrue(self.scan(reset=True)["Guard"]["enabled"])  # Guard heals; the e-stop state is irrelevant.

    def test_reset_clears_latch_and_diagnostic_only_when_all_channels_agree(self):
        self.scan(estop=(False, True))
        self.scan(estop=(False, True))
        self.assertTrue(self.system.functions["EStop"].channel_fault)
        self.scan(estop=(True, True), reset=True)
        self.assertTrue(self.system.functions["EStop"].enabled)
        self.assertFalse(self.system.functions["EStop"].channel_fault)


class SafetyFaultInjectionTests(unittest.TestCase):
    def test_every_single_fault_case_reaches_safe_state_and_recovers(self):
        rows = run_all()
        self.assertEqual(len(rows), len(CASES))
        failures = [row for row in rows if not row["passed"]]
        self.assertEqual(failures, [])

    def test_stuck_healthy_channel_is_flagged_by_its_case(self):
        case = next(c for c in CASES if c.key == "estop-a-stuck-healthy")
        row = run_case(case)
        self.assertTrue(row["safe_same_scan"])
        self.assertTrue(row["channel_fault"])
        self.assertTrue(row["reset_refused"])
        self.assertTrue(row["recovered"])

    def test_plc_output_fault_is_stopped_by_the_drive_gate_not_the_ladder(self):
        bench = Bench()
        self.addCleanup(bench.close)
        case = next(c for c in CASES if c.key == "plc-outputs-stuck-on")
        bench.command({"action": "start"})
        bench.tick()
        case.inject(bench)
        case.demand(bench)
        state = bench.tick()
        self.assertFalse(any(state["drives"].values()))  # No power reaches the drives during the trip.
        self.assertFalse(bench.safety.enabled("EStop"))
        self.assertIn("Safety function tripped", " ".join(e["message"] for e in state["events"]))

    def test_bench_rejects_unknown_channel_fault(self):
        bench = Bench()
        self.addCleanup(bench.close)
        with self.assertRaises(ValueError):
            bench.command({"action": "channel_fault", "function": "EStop", "channel": "C", "mode": None})
        with self.assertRaises(ValueError):
            bench.command({"action": "channel_fault", "function": "EStop", "channel": "A", "mode": "fast"})


class SafetyEvidenceTests(unittest.TestCase):
    def test_evidence_table_in_spec_matches_runner_output(self):
        spec = (ROOT / "docs/safety-function.md").read_text()
        self.assertIn(markdown(run_all()), spec)

    def test_performance_level_table_in_spec_matches_calculation(self):
        spec = (ROOT / "docs/safety-function.md").read_text()
        self.assertIn(pl_markdown(evaluate()), spec)

    def test_calculated_functions_reach_pl_d_at_category_3(self):
        rows = evaluate()
        self.assertEqual([(row["function"], row["category"], row["pl"]) for row in rows],
                         [("EStop", 3, "d"), ("Guard", 3, "d")])
        for row in rows:
            self.assertEqual(row["mttfd_band"], "high")
            self.assertEqual(row["mttfd_years"], 50)


if __name__ == "__main__":
    unittest.main()
