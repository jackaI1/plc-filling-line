import random
import unittest

from fillingline.controller import PLC


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.plc = PLC()
        self.addCleanup(self.plc.close)

    def start(self):
        state = self.plc.scan(Start=True)
        self.plc.scan(Start=False)
        return state

    def test_idle_and_seal_in_stop(self):
        self.assertFalse(self.plc.scan()["outputs"]["Run"])
        self.assertTrue(self.start()["outputs"]["Conveyor"])
        self.assertTrue(self.plc.scan()["outputs"]["Run"])
        self.assertFalse(self.plc.scan(Stop=True)["outputs"]["Run"])
        self.assertFalse(self.plc.scan(Stop=False)["outputs"]["Run"])

    def test_fill_timer_boundary_and_bottle_release(self):
        self.start()
        self.assertTrue(self.plc.scan(BottleAtFill=True)["outputs"]["Valve"])
        for _ in range(19):
            self.assertTrue(self.plc.scan()["outputs"]["Valve"])
        state = self.plc.scan()
        self.assertFalse(state["outputs"]["Valve"])
        self.assertTrue(state["outputs"]["Conveyor"])
        self.assertTrue(state["outputs"]["Filled"])
        for _ in range(10):
            self.assertFalse(self.plc.scan()["outputs"]["Valve"])
        self.assertFalse(self.plc.scan(BottleAtFill=False)["outputs"]["Filled"])

    def test_exit_counter_edges_and_five_bottle_stop(self):
        self.start()
        for expected in range(1, 6):
            state = self.plc.scan(ExitSensor=True)
            self.assertEqual(state["count"], expected)
            for _ in range(3):
                self.assertEqual(self.plc.scan()["count"], expected)
            self.plc.scan(ExitSensor=False)
        self.assertTrue(state["outputs"]["BatchDone"])
        self.assertFalse(state["outputs"]["Run"])
        self.assertEqual(self.plc.scan(Reset=True)["count"], 0)
        self.assertFalse(self.plc.scan(Reset=False)["outputs"]["Run"])

    def test_trip_requires_cause_clear_reset_and_new_start_edge(self):
        self.start()
        self.plc.scan(Start=True, GuardClosed=False)
        state = self.plc.scan(GuardClosed=True, Reset=True)
        self.assertFalse(state["outputs"]["Run"])
        self.assertFalse(state["outputs"]["Alarm"])
        self.assertFalse(self.plc.scan(Reset=False)["outputs"]["Run"])
        self.plc.scan(Start=False)
        self.assertTrue(self.plc.scan(Start=True)["outputs"]["Run"])

    def test_reset_cannot_override_unhealthy_permissive(self):
        for name in ("EStopOK", "GuardClosed", "TankOK"):
            state = self.plc.scan(**{name: False}, Start=True, Reset=True)
            self.assertTrue(state["outputs"]["Alarm"])
            self.assertFalse(state["outputs"]["Conveyor"])
            self.assertFalse(state["outputs"]["Valve"])
            self.plc.scan(**{name: True}, Start=False, Reset=False)

    def test_travel_jam_timeout(self):
        self.start()
        for _ in range(59):
            self.assertFalse(self.plc.scan()["outputs"]["Alarm"])
        state = self.plc.scan()
        self.assertTrue(state["outputs"]["Alarm"])
        self.assertFalse(state["outputs"]["Conveyor"])

    def test_stop_during_fill_needs_bottle_removal(self):
        self.start()
        self.plc.scan(BottleAtFill=True)
        state = self.plc.scan(Stop=True)
        self.assertTrue(state["outputs"]["Alarm"])
        self.assertFalse(state["outputs"]["Valve"])
        self.assertTrue(self.plc.scan(Stop=False, Reset=True)["outputs"]["Alarm"])
        self.assertFalse(self.plc.scan(BottleAtFill=False)["outputs"]["Alarm"])

    def test_exit_held_across_restart_does_not_count_twice(self):
        self.start()
        self.assertEqual(self.plc.scan(ExitSensor=True)["count"], 1)
        self.plc.scan(Stop=True)
        self.plc.scan(Stop=False, Reset=True)
        self.plc.scan(Reset=False)
        self.start()
        self.assertEqual(self.plc.scan()["count"], 0)

    def test_randomized_interlock_invariants_2000_scans(self):
        rng = random.Random(61131)
        for _ in range(2000):
            state = self.plc.scan(**{name: bool(rng.getrandbits(1)) for name in self.plc.inputs})
            out, inp = state["outputs"], state["inputs"]
            if not all(inp[n] for n in ("EStopOK", "GuardClosed", "TankOK")) or out["Alarm"]:
                self.assertFalse(out["Valve"] or out["Conveyor"] or out["Run"])
            if out["Valve"]:
                self.assertTrue(inp["BottleAtFill"] and out["Run"])
                self.assertFalse(out["Conveyor"])
            self.assertGreaterEqual(state["count"], 0)
            self.assertLessEqual(state["count"], 5)

    def test_instances_have_independent_latches(self):
        other = PLC()
        self.addCleanup(other.close)
        self.start()
        self.assertFalse(other.scan()["outputs"]["Run"])
        self.assertTrue(self.plc.scan()["outputs"]["Run"])
