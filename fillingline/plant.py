"""Deterministic one-bottle plant. Only physical simulation lives here."""
from .controller import PLC, SCAN_MS
from .maintenance import Maintenance
from .safety import SafetySystem

CHANNEL_MODES = (None, "stuck_healthy", "stuck_open")


class Bench:
    def __init__(self, db=":memory:"):
        self.plc = PLC()
        self.maintenance = Maintenance(db)
        # Dual-channel safety functions sit in front of the PLC and gate the drives directly.
        self.safety = SafetySystem()
        self.channel_modes = {"EStop": {"A": None, "B": None}, "Guard": {"A": None, "B": None}}
        self.safety_reset_stuck = False
        self.previous_safety = {"EStop": (True, False), "Guard": (True, False)}  # (enabled, channel fault)
        self.drives = {"Conveyor": False, "Valve": False}  # Power actually reaching the drives this scan.
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
            if action == "reset":
                self.commands["SafetyReset"] = True  # Same panel button, separate safety contact.
        elif action == "fault":
            name, value = payload.get("name"), payload.get("value")
            if name not in {*self.faults, "jammed", "fill_sensor_stuck", "safety_reset_stuck"} or type(value) is not bool:
                raise ValueError("Choose a known Boolean fault input")
            if name == "jammed":
                self.jammed = value
            elif name == "fill_sensor_stuck":
                self.fill_sensor_stuck = value
            elif name == "safety_reset_stuck":
                self.safety_reset_stuck = value
            else:
                self.faults[name] = value
        elif action == "channel_fault":
            function, channel, mode = payload.get("function"), payload.get("channel"), payload.get("mode")
            if function not in self.channel_modes or channel not in ("A", "B") or mode not in CHANNEL_MODES:
                raise ValueError("Choose EStop or Guard, channel A or B, and a known mode")
            self.channel_modes[function][channel] = mode
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
        # Safety functions read their own channels first, so the PLC sees their result in the same scan.
        physical = {"EStop": self.faults["EStopOK"], "Guard": self.faults["GuardClosed"]}
        readings = {name: tuple(self._channel_reading(name, channel, value)
                                for channel in ("A", "B")) for name, value in physical.items()}
        reset = self.commands.get("SafetyReset", False) or self.safety_reset_stuck
        self.safety.scan(readings, reset)
        self._log_safety_changes()
        inputs = {**self.faults, "EStopOK": self.safety.enabled("EStop"),
                  "GuardClosed": self.safety.enabled("Guard")}
        state = self.plc.scan(**inputs, **sensors,
                              **{n: self.commands.get(n, False) for n in ("Start", "Stop", "Reset")})
        self.commands.clear()
        out = state["outputs"]
        # Hard-wired drive gate: removes motor and valve power even if the PLC output is wrong.
        drive = self.safety.enabled("EStop") and self.safety.enabled("Guard")
        self.drives = {"Conveyor": bool(out["Conveyor"] and drive), "Valve": bool(out["Valve"] and drive)}
        if out["Valve"] and drive:
            self.level = min(1, self.level + SCAN_MS / 1000)
        if out["Conveyor"] and drive and not self.jammed:
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

    def _channel_reading(self, function, channel, physical):
        mode = self.channel_modes[function][channel]
        if mode == "stuck_healthy":
            return True   # Dangerous fault: the channel keeps saying "healthy".
        if mode == "stuck_open":
            return False  # Nuisance fault: the channel keeps saying "unhealthy".
        return physical

    def _log_safety_changes(self):
        names = {"EStop": "emergency stop", "Guard": "guard interlock"}
        for name, function in self.safety.functions.items():
            previous_enabled, previous_fault = self.previous_safety[name]
            if previous_enabled and not function.enabled:
                self.maintenance.event(f"Safety function tripped: {names[name]}; drives removed")
            if function.channel_fault and not previous_fault:
                a, b = function.channels
                self.maintenance.event(f"Safety channels disagree: {names[name]} A={int(a)} B={int(b)}")
            self.previous_safety[name] = (function.enabled, function.channel_fault)

    def snapshot(self):
        return {**self.plc.snapshot(), "plant": {"position": self.position, "level": self.level,
                "jammed": self.jammed, "fill_sensor_stuck": self.fill_sensor_stuck,
                "runtime_ms": self.elapsed_ms}, "faults": dict(self.faults),
                "safety": self.safety.snapshot(), "channel_modes": self.channel_modes,
                "drives": dict(self.drives),
                **self.maintenance.snapshot()}

    def close(self):
        self.plc.close()
        self.maintenance.close()
