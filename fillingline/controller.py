import ctypes
from pathlib import Path
import platform

ROOT = Path(__file__).resolve().parents[1]
INPUTS = ("Start", "Stop", "Reset", "EStopOK", "GuardClosed", "TankOK",
          "BottleAtFill", "ExitSensor", "JamSwitch")
OUTPUTS = ("Run", "Conveyor", "Valve", "Alarm", "BatchDone", "Filled", "FillBlocked")
SCAN_MS = 50


class PLC:
    """One native controller instance. Call serially (matiec's clock is global)."""
    def __init__(self):
        path = ROOT / ".build" / ("line.dylib" if platform.system() == "Darwin" else "line.so")
        if not path.exists():
            raise RuntimeError("Build the PLC first: python3 tools/build.py")
        self.lib = ctypes.CDLL(str(path))
        self.lib.plc_new.restype = ctypes.c_void_p
        self.lib.plc_free.argtypes = [ctypes.c_void_p]
        self.lib.plc_scan.argtypes = [ctypes.c_void_p, ctypes.c_uint64, ctypes.c_uint32]
        for name in ("plc_outputs", "plc_count", "plc_fill_ms"):
            getattr(self.lib, name).argtypes = [ctypes.c_void_p]
            getattr(self.lib, name).restype = ctypes.c_int
        self.handle = self.lib.plc_new()
        if not self.handle:
            raise MemoryError("Could not allocate PLC instance")
        self.ms = 0
        self.inputs = {name: name in ("EStopOK", "GuardClosed", "TankOK") for name in INPUTS}

    def close(self):
        if self.handle:
            self.lib.plc_free(self.handle)
            self.handle = None

    def scan(self, **changes):
        if not self.handle:
            raise RuntimeError("Controller is closed")
        if not set(changes) <= set(INPUTS) or any(type(v) is not bool for v in changes.values()):
            raise ValueError("Inputs must be known BOOL values")
        self.inputs.update(changes)
        bits = sum(int(self.inputs[n]) << i for i, n in enumerate(INPUTS))
        self.lib.plc_scan(self.handle, self.ms, bits)
        self.ms += SCAN_MS
        return self.snapshot()

    def snapshot(self):
        bits = self.lib.plc_outputs(self.handle)
        return {"time_ms": self.ms, "inputs": dict(self.inputs),
                "outputs": {n: bool(bits & (1 << i)) for i, n in enumerate(OUTPUTS)},
                "count": self.lib.plc_count(self.handle), "fill_ms": self.lib.plc_fill_ms(self.handle)}
