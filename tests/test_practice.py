import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from fillingline.practice import run_practice


class PracticeTests(unittest.TestCase):
    def test_native_recovery_checkpoints_match_outputs_and_ledger(self):
        states = {state["step"]: state for state in run_practice()}
        self.assertEqual(list(states), ["tripped", "cause_cleared", "order_closed",
                                        "reset", "restarted", "complete"])
        for step in ("tripped", "cause_cleared", "order_closed"):
            state = states[step]
            self.assertTrue(state["outputs"]["Alarm"])
            self.assertFalse(any(state["outputs"][key] for key in ("Run", "Conveyor", "Valve")))
            self.assertEqual(state["count"], 0)
        self.assertEqual(states["tripped"]["orders"][0]["status"], "open")
        self.assertEqual(states["order_closed"]["orders"][0]["status"], "closed")
        self.assertFalse(states["reset"]["outputs"]["Alarm"])
        self.assertFalse(states["reset"]["outputs"]["Run"])
        self.assertTrue(states["restarted"]["outputs"]["Conveyor"])
        self.assertEqual(states["complete"]["count"], 5)
        self.assertTrue(states["complete"]["outputs"]["BatchDone"])
        self.assertEqual(len(states["complete"]["orders"]), 1)
        self.assertEqual(states["complete"]["orders"][0]["status"], "closed")

    def test_terminal_entry_point_uses_no_persistent_ledger(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run([sys.executable, "-m", "fillingline.practice"], cwd=tmp,
                                    env={**os.environ, "PYTHONPATH": str(root)},
                                    text=True, capture_output=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Stall cleared; alarm still latched", result.stdout)
            self.assertIn("Five-bottle batch complete", result.stdout)
            self.assertIn("bottles=5/5, work order=closed", result.stdout)
            self.assertEqual(list(Path(tmp).iterdir()), [])
