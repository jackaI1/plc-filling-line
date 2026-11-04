from pathlib import Path
import tempfile
import unittest

from fillingline.maintenance import Maintenance
from fillingline.plant import Bench


class BenchTests(unittest.TestCase):
    def setUp(self):
        self.bench = Bench()
        self.addCleanup(self.bench.close)

    def test_complete_batch_without_fault(self):
        self.bench.command({"action": "start"})
        states = [self.bench.tick() for _ in range(320)]
        self.assertTrue(states[-1]["outputs"]["BatchDone"])
        self.assertEqual(states[-1]["count"], 5)
        self.assertFalse(any(s["outputs"]["Alarm"] for s in states))
        self.assertIn("Batch complete", states[-1]["events"][0]["message"])

    def test_stall_creates_one_order_then_recovery(self):
        self.bench.command({"action": "fault", "name": "jammed", "value": True})
        self.bench.command({"action": "start"})
        for _ in range(100):
            state = self.bench.tick()
        self.assertTrue(state["outputs"]["Alarm"])
        self.assertEqual(len(state["orders"]), 1)
        self.assertIn("timeout", state["orders"][0]["issue"])
        self.bench.command({"action": "fault", "name": "jammed", "value": False})
        self.bench.command({"action": "reset"})
        self.assertFalse(self.bench.tick()["outputs"]["Alarm"])
        self.assertFalse(self.bench.tick()["outputs"]["Run"])
        self.bench.command({"action": "start"})
        self.assertTrue(self.bench.tick()["outputs"]["Run"])

    def test_interrupted_fill_reset_discards_bottle(self):
        self.bench.command({"action": "start"})
        for _ in range(20):
            self.bench.tick()
        self.assertGreater(self.bench.level, 0)
        self.bench.command({"action": "stop"})
        self.assertTrue(self.bench.tick()["outputs"]["Alarm"])
        self.bench.command({"action": "reset"})
        state = self.bench.tick()
        self.assertEqual(state["plant"]["level"], 0)
        self.assertFalse(state["outputs"]["Alarm"])

    def test_held_sensor_reports_one_specific_order_and_cannot_reset_until_released(self):
        self.bench.command({"action": "fault", "name": "fill_sensor_stuck", "value": True})
        self.bench.command({"action": "start"})
        for _ in range(60):
            state = self.bench.tick()
        self.assertTrue(state["outputs"]["FillBlocked"])
        self.assertFalse(state["outputs"]["Conveyor"] or state["outputs"]["Valve"])
        self.assertEqual(len(state["orders"]), 1)
        self.assertEqual(state["orders"][0]["asset"], "FV-01")
        self.assertEqual(state["orders"][0]["issue"],
                         "fill-position clearance timeout (bottle jam or sensor held on)")
        self.bench.command({"action": "reset"})
        self.assertTrue(self.bench.tick()["outputs"]["Alarm"])
        self.bench.command({"action": "fault", "name": "fill_sensor_stuck", "value": False})
        self.assertTrue(self.bench.tick()["outputs"]["FillBlocked"])
        self.bench.command({"action": "reset"})
        self.assertFalse(self.bench.tick()["outputs"]["Alarm"])
        self.assertFalse(self.bench.tick()["outputs"]["Run"])
        self.bench.command({"action": "start"})
        for _ in range(320):
            state = self.bench.tick()
        self.assertTrue(state["outputs"]["BatchDone"])
        self.assertEqual(len(state["orders"]), 1)

    def test_bottle_jam_at_fill_uses_clearance_diagnostic(self):
        self.bench.command({"action": "start"})
        for _ in range(60):
            state = self.bench.tick()
            if state["outputs"]["Filled"]:
                break
        else:
            self.fail("Bottle never finished filling")
        self.bench.command({"action": "fault", "name": "jammed", "value": True})
        for _ in range(25):
            state = self.bench.tick()
        self.assertTrue(state["inputs"]["BottleAtFill"])
        self.assertTrue(state["outputs"]["FillBlocked"])
        self.assertIn("fill-position clearance", state["orders"][0]["issue"])

    def test_accelerated_preventive_interval_and_service_gate(self):
        self.bench.elapsed_ms = 30000
        self.bench.tick()
        order = self.bench.snapshot()["orders"][0]
        self.assertEqual(order["kind"], "preventive")
        with self.assertRaises(ValueError):
            self.bench.command({"action": "service"})
        self.bench.command({"action": "close_order", "id": order["id"], "resolution": "Inspected nozzle in simulation"})
        self.bench.command({"action": "service"})
        self.bench.tick()
        self.assertEqual(len(self.bench.snapshot()["orders"]), 1)
        with self.assertRaises(ValueError):
            self.bench.command({"action": "service"})  # A closed order cannot be reused.

    def test_commands_reject_invalid_faults_and_running_reset(self):
        for payload in ({"action": "fault", "name": "bad", "value": True}, {"action": "fault", "name": "TankOK", "value": "false"}, [], {"action": "unknown"}):
            with self.assertRaises(ValueError):
                self.bench.command(payload)
        self.bench.command({"action": "start"})
        self.bench.tick()
        with self.assertRaises(ValueError):
            self.bench.command({"action": "reset"})


class MaintenanceTests(unittest.TestCase):
    def test_persistence_and_resolution_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "log.sqlite3"
            log = Maintenance(path)
            try:
                ident = log.open("CV-01", "corrective", "<script> is stored as plain text")
                with self.assertRaises(ValueError):
                    log.close_order(ident, " ")
                log.close_order(ident, "Checked alignment")
                with self.assertRaises(ValueError):
                    log.close_order(ident, "Already closed")
            finally:
                log.close()
            log = Maintenance(path)
            try:
                self.assertEqual(log.snapshot()["orders"][0]["resolution"], "Checked alignment")
                self.assertEqual(log.snapshot()["orders"][0]["status"], "closed")
            finally:
                log.close()
