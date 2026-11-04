"""Deterministic one-bottle plant. Only physical simulation lives here."""
from .controller import PLC, SCAN_MS
from .maintenance import Maintenance


class Bench:
    def __init__(self, db=":memory:"):
        self.plc = PLC()
        self.maintenance = Maintenance(db)
        self.position = 0.0
        self.level = 0.0
        self.jammed = False
        self.fill_sensor_stuck = False
        self.elapsed_ms = 0
        self.last_service_ms = 0
        self.pm_open = False
        self.last_service_order = 0
        self.commands = {}
        self.faults = {"EStopOK": True, "GuardClosed": True, "TankOK": True, "JamSwitch": False}
        self.previous_alarm = False
        self.previous_done = False

    def command(self, payload):
        if not isinstance(payload, dict):
            raise ValueError("Command must be an object")
        action = payload.get("action")
        if action in {"start", "stop", "reset"}:
            if action == "reset":
                if self.plc.snapshot()["outputs"]["Run"]:
                    raise ValueError("Stop the line before resetting the batch")
                # Operator recovery action: discard the current bottle, not a PLC actuator.
                self.position, self.level = 0.0, 0.0
                self.maintenance.event("Batch reset; current simulated bottle discarded")
            self.commands[{"start": "Start", "stop": "Stop", "reset": "Reset"}[action]] = True
        elif action == "fault":
            name, value = payload.get("name"), payload.get("value")
            if name not in {*self.faults, "jammed", "fill_sensor_stuck"} or type(value) is not bool:
                raise ValueError("Choose a known Boolean fault input")
            if name == "jammed":
                self.jammed = value
            elif name == "fill_sensor_stuck":
                self.fill_sensor_stuck = value
            else:
                self.faults[name] = value
        elif action == "open_order":
            self.maintenance.open(payload.get("asset"), payload.get("kind"), payload.get("issue"))
        elif action == "close_order":
            self.maintenance.close_order(payload.get("id"), payload.get("resolution"))
        elif action == "service":
            orders = self.maintenance.snapshot()["orders"]
            if self.plc.snapshot()["outputs"]["Run"]:
                raise ValueError("Stop the line before acknowledging service")
            completed = [o["id"] for o in orders if o["kind"] == "preventive" and o["status"] == "closed"
                         and o["id"] > self.last_service_order]
            if not completed or any(o["kind"] == "preventive" and o["status"] == "open" for o in orders):
                raise ValueError("Close a preventive work order with a resolution first")
            self.last_service_order = max(completed)
            self.last_service_ms = self.elapsed_ms
            self.pm_open = False
            self.maintenance.event("Preventive service acknowledged with line stopped")
        else:
            raise ValueError("Unknown command")

    def tick(self):
        sensors = {"BottleAtFill": self.fill_sensor_stuck or 0.40 <= self.position < 0.62,
                   "ExitSensor": 0.90 <= self.position < 1.0}
        state = self.plc.scan(**self.faults, **sensors,
                              **{n: self.commands.get(n, False) for n in ("Start", "Stop", "Reset")})
        self.commands.clear()
        out = state["outputs"]
        if out["Valve"]:
            self.level = min(1, self.level + SCAN_MS / 1000)
        if out["Conveyor"] and not self.jammed:
            self.position += 0.025
            if self.position >= 1.0:
                self.position = 0.0
                self.level = 0.0
        if out["Run"]:
            self.elapsed_ms += SCAN_MS
        if out["Alarm"] and not self.previous_alarm:
            causes = [n for n in ("EStopOK", "GuardClosed", "TankOK") if not self.faults[n]]
            if self.faults["JamSwitch"]:
                causes.append("JamSwitch")
            cause = ", ".join(causes) or "conveyor travel timeout"
            if out["FillBlocked"]:
                causes.append("fill-position clearance timeout (bottle jam or sensor held on)")
                cause = ", ".join(causes)
            self.maintenance.open("FV-01" if out["FillBlocked"] else "CV-01" if not causes else "Line-01",
                                  "corrective", cause)
            self.maintenance.event(f"PLC trip: {cause}")
        if out["BatchDone"] and not self.previous_done:
            self.maintenance.event("Batch complete: five exit-sensor rising edges")
        self.previous_alarm, self.previous_done = out["Alarm"], out["BatchDone"]
        # Accelerated demo interval, explicitly not a manufacturer recommendation.
        if self.elapsed_ms - self.last_service_ms >= 30000 and not self.pm_open:
            self.maintenance.open("FV-01", "preventive", "Demo interval: inspect fill nozzle after 30 seconds running")
            self.pm_open = True
        return self.snapshot()

    def snapshot(self):
        return {**self.plc.snapshot(), "plant": {"position": self.position, "level": self.level,
                "jammed": self.jammed, "fill_sensor_stuck": self.fill_sensor_stuck,
                "runtime_ms": self.elapsed_ms}, **self.maintenance.snapshot()}

    def close(self):
        self.plc.close()
        self.maintenance.close()
