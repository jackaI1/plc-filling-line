"""Single-fault injection for the emergency-stop and guard safety functions.

Each case starts a batch, injects one fault, demands the safe state, checks the
trip, repairs the fault and proves that a monitored reset plus a fresh start
recovers the line. Run `python -m fillingline.safety_check` to print the table
that docs/safety-function.md records. Virtual time only; no server or sleeps.
"""
from dataclasses import dataclass
from typing import Callable

from .plant import Bench

Action = Callable[[Bench], None]


def command(**payload) -> Action:
    return lambda bench: bench.command(payload)


def channel(function: str, name: str, mode):
    return command(action="channel_fault", function=function, channel=name, mode=mode)


def fault(name: str, value: bool) -> Action:
    return command(action="fault", name=name, value=value)


def nothing(_bench):
    return None


def force_plc_outputs_on(bench):
    # Models a wrong PLC output: conveyor and valve commanded on whatever the ladder decides.
    original = bench.plc.scan
    bench.original_plc_scan = original

    def forced(**changes):
        state = original(**changes)
        state["outputs"].update(Conveyor=True, Valve=True)
        return state
    bench.plc.scan = forced


def restore_plc_outputs(bench):
    bench.plc.scan = bench.original_plc_scan


@dataclass(frozen=True)
class Case:
    key: str
    label: str
    function: str            # Safety function whose state is checked.
    expect_channel_fault: bool
    inject: Action
    demand: Action           # Physical demand that causes the trip.
    repair: Action           # Removes the injected fault.
    release: Action          # Releases the demand after repair.


PRESS_ESTOP = fault("EStopOK", False)
RELEASE_ESTOP = fault("EStopOK", True)
OPEN_GUARD = fault("GuardClosed", False)
CLOSE_GUARD = fault("GuardClosed", True)

CASES = (
    Case("estop-a-stuck-healthy", "E-stop channel A stuck healthy", "EStop", True,
         channel("EStop", "A", "stuck_healthy"), PRESS_ESTOP,
         channel("EStop", "A", None), RELEASE_ESTOP),
    Case("estop-b-stuck-healthy", "E-stop channel B stuck healthy", "EStop", True,
         channel("EStop", "B", "stuck_healthy"), PRESS_ESTOP,
         channel("EStop", "B", None), RELEASE_ESTOP),
    Case("estop-a-stuck-open", "E-stop channel A stuck open (no press)", "EStop", True,
         channel("EStop", "A", "stuck_open"), nothing,
         channel("EStop", "A", None), nothing),
    Case("guard-a-stuck-healthy", "Guard channel A stuck healthy", "Guard", True,
         channel("Guard", "A", "stuck_healthy"), OPEN_GUARD,
         channel("Guard", "A", None), CLOSE_GUARD),
    Case("guard-b-stuck-open", "Guard channel B stuck open (guard closed)", "Guard", True,
         channel("Guard", "B", "stuck_open"), nothing,
         channel("Guard", "B", None), nothing),
    Case("reset-contact-welded", "Safety reset contact welded closed, then e-stop pressed", "EStop", False,
         fault("safety_reset_stuck", True), PRESS_ESTOP,
         fault("safety_reset_stuck", False), RELEASE_ESTOP),
    Case("plc-outputs-stuck-on", "PLC ladder commands conveyor and valve on during an e-stop press", "EStop", False,
         force_plc_outputs_on, PRESS_ESTOP,
         restore_plc_outputs, RELEASE_ESTOP),
)


def _running(bench):
    bench.command({"action": "start"})
    return bench.tick()["outputs"]["Conveyor"]


def run_case(case: Case) -> dict:
    bench = Bench()
    try:
        running = _running(bench)
        bench.tick()
        case.inject(bench)
        case.demand(bench)
        trip = bench.tick()
        out = trip["outputs"]
        # Judge the drives, not the PLC's command: the hard-wired gate is what must hold.
        safe_same_scan = not any(trip["drives"].values()) and out["Alarm"]
        for _ in range(3):
            bench.tick()
        function = bench.safety.functions[case.function]
        channel_fault = function.channel_fault
        bench.command({"action": "reset"})
        bench.tick()
        reset_refused = not function.enabled
        case.repair(bench)
        case.release(bench)
        bench.tick()
        bench.command({"action": "reset"})
        bench.tick()
        cleared = function.enabled and not bench.plc.snapshot()["outputs"]["Alarm"]
        bench.command({"action": "start"})
        final = None
        for _ in range(400):
            final = bench.tick()
            if final["outputs"]["BatchDone"]:
                break
        recovered = bool(cleared and final and final["outputs"]["BatchDone"] and final["count"] == 5
                         and not final["outputs"]["Alarm"])
        passed = (running and safe_same_scan and channel_fault == case.expect_channel_fault
                  and reset_refused and recovered)
        return {"case": case.key, "label": case.label, "safe_same_scan": safe_same_scan,
                "channel_fault": channel_fault, "reset_refused": reset_refused,
                "recovered": recovered, "passed": passed}
    finally:
        bench.close()


def run_all():
    return [run_case(case) for case in CASES]


def markdown(rows):
    yes = lambda value: "Yes" if value else "No"
    lines = ["| Case | Motor and valve off in the trip scan | Channel disagreement latched | "
             "Reset refused while the fault is present | Five-bottle batch after repair and reset |",
             "| --- | --- | --- | --- | --- |"]
    for row in rows:
        lines.append(f"| {row['label']} | {yes(row['safe_same_scan'])} | {yes(row['channel_fault'])} | "
                     f"{yes(row['reset_refused'])} | {yes(row['recovered'])} |")
    return "\n".join(lines)


def main():
    rows = run_all()
    print(markdown(rows))
    failed = [row["case"] for row in rows if not row["passed"]]
    if failed:
        raise SystemExit("Safety fault cases failed: " + ", ".join(failed))


if __name__ == "__main__":
    main()
