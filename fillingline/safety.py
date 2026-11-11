"""Dual-channel safety functions for the simulated filling line.

This layer does not use the PLC ladder. Each function (emergency stop and guard
interlock) reads two channels, A and B. A channel reads True when healthy: the
emergency stop is released or the guard is closed. Any channel that reads False
trips its function in the same scan. Channels that disagree for DISCREPANCY_MS
latch a channel fault. A trip clears only through a monitored reset: a rising
edge on the reset input, accepted only while the function is healthy and its
channels agree. See docs/safety-function.md for the full specification.
"""

DISCREPANCY_MS = 100  # Two 50 ms scans of disagreement latch a channel fault.
SCAN_MS = 50          # Same scan period as the PLC adapter.
FUNCTIONS = ("EStop", "Guard")


class SafetyFunction:
    def __init__(self, name):
        self.name = name
        self.latched = False        # Set by any trip; the PLC permissive and drive gate follow it.
        self.channel_fault = False  # Latched by a sustained disagreement between channels.
        self.discrepancy_ms = 0
        self.healthy = True
        self.channels = (True, True)

    @property
    def enabled(self):
        return not self.latched

    def scan(self, channels, reset_edge):
        a, b = bool(channels[0]), bool(channels[1])
        self.channels = (a, b)
        self.healthy = a and b
        if a == b:
            self.discrepancy_ms = 0
        else:
            self.discrepancy_ms = min(DISCREPANCY_MS, self.discrepancy_ms + SCAN_MS)
            if self.discrepancy_ms >= DISCREPANCY_MS:
                self.channel_fault = True
        if not self.healthy:
            self.latched = True  # Immediate, same-scan trip; no timer on an unhealthy reading.
        elif reset_edge:
            # Monitored reset accepted: healthy (so the channels agree), on a rising edge.
            # It also clears a channel-fault diagnostic once the channels agree again.
            self.latched = False
            self.channel_fault = False

    def snapshot(self):
        return {"enabled": self.enabled, "healthy": self.healthy, "channel_fault": self.channel_fault,
                "channels": {"A": self.channels[0], "B": self.channels[1]}}


class SafetySystem:
    """Both safety functions share one monitored reset input."""

    def __init__(self):
        self.functions = {name: SafetyFunction(name) for name in FUNCTIONS}
        self.previous_reset = False

    def scan(self, readings, reset):
        reset = bool(reset)
        edge = reset and not self.previous_reset
        self.previous_reset = reset
        for name, function in self.functions.items():
            function.scan(readings[name], edge)
        return self.snapshot()

    def enabled(self, name):
        return self.functions[name].enabled

    def snapshot(self):
        return {name: function.snapshot() for name, function in self.functions.items()}
