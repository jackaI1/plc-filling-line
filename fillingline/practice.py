"""A repeatable, server-free fault-recovery exercise using the compiled PLC."""
import argparse

from .plant import Bench


def run_practice(fault="conveyor"):
    """Return observed checkpoints; fail rather than print a successful bad run."""
    if fault not in {"conveyor", "fill-sensor"}:
        raise ValueError("Choose conveyor or fill-sensor")
    sensor = fault == "fill-sensor"
    fault_input = "fill_sensor_stuck" if sensor else "jammed"
    issue = ("fill-position clearance timeout (bottle jam or sensor held on)"
             if sensor else "conveyor travel timeout")
    bench = Bench()  # Isolated in-memory ledger, never the HMI's saved database.
    checkpoints = []

    def record(step, message, state):
        checkpoints.append({"step": step, "message": message,
                            "time_ms": state["time_ms"], "count": state["count"],
                            "outputs": state["outputs"], "orders": state["orders"]})

    def require(condition, message):
        if not condition:
            raise RuntimeError(message)

    def wait_for(output, max_scans):
        for _ in range(max_scans):
            state = bench.tick()
            if state["outputs"][output]:
                return state
        raise RuntimeError(f"Practice timed out waiting for {output}")

    def stopped(state):
        return not any(state["outputs"][name] for name in ("Run", "Conveyor", "Valve"))

    try:
        bench.command({"action": "fault", "name": fault_input, "value": True})
        bench.command({"action": "start"})
        state = wait_for("Alarm", 100)
        require(stopped(state), "Trip left equipment running")
        require(len(state["orders"]) == 1 and
                state["orders"][0]["issue"] == issue,
                "PLC timeout did not create one matching corrective work order")
        order_id = state["orders"][0]["id"]
        record("tripped", "Fill position timed out; corrective order opened." if sensor
               else "Stalled conveyor tripped; corrective order opened.", state)

        if sensor:
            bench.command({"action": "reset"})
            state = bench.tick()
            require(stopped(state) and state["outputs"]["FillBlocked"] and state["outputs"]["Alarm"],
                    "Reset bypassed a fill sensor still held on")
            record("reset_refused", "Reset cannot clear a fill sensor still held on.", state)

        bench.command({"action": "fault", "name": fault_input, "value": False})
        state = bench.tick()
        require(stopped(state) and state["outputs"]["Alarm"], "Clearing stall restarted the line")
        record("cause_cleared", "Sensor released; alarm still latched and equipment stopped." if sensor
               else "Stall cleared; alarm still latched and equipment stopped.", state)

        bench.command({"action": "close_order", "id": order_id,
                       "resolution": "Released simulated fill sensor; ready for reset and fresh start." if sensor
                       else "Removed simulated conveyor obstruction; ready for reset and fresh start."})
        state = bench.tick()
        require(stopped(state) and state["outputs"]["Alarm"], "Closing order changed PLC recovery state")
        require(state["orders"][0]["status"] == "closed", "Work order did not close")
        record("order_closed", "Work order closed; line still needs reset and start.", state)

        bench.command({"action": "reset"})
        state = bench.tick()
        require(stopped(state) and not state["outputs"]["Alarm"] and state["count"] == 0,
                "Reset did not leave a cleared, stopped batch")
        record("reset", "Batch reset and bottle discarded; equipment remains stopped.", state)
        for _ in range(3):
            require(stopped(bench.tick()), "Line restarted without a fresh start request")

        bench.command({"action": "start"})
        state = bench.tick()
        require(state["outputs"]["Run"], "Fresh start did not run the line")
        record("restarted", "Fresh start requested; conveyor running again.", state)
        state = wait_for("BatchDone", 400)
        require(stopped(state) and not state["outputs"]["Alarm"] and state["count"] == 5,
                "Recovered batch did not finish with five bottles and equipment stopped")
        record("complete", "Five-bottle batch complete; equipment stopped.", state)
        return checkpoints
    finally:
        bench.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fault", choices=("conveyor", "fill-sensor"), default="conveyor")
    args = parser.parse_args()
    print(f"Simulated {args.fault} practice (virtual time; temporary maintenance log)")
    for state in run_practice(args.fault):
        out = state["outputs"]
        print(f"{state['time_ms'] / 1000:5.2f}s  {state['message']}")
        print(f"        motor={'on' if out['Conveyor'] else 'off'}, "
              f"valve={'on' if out['Valve'] else 'off'}, bottles={state['count']}/5, "
              f"work order={state['orders'][0]['status']}")


if __name__ == "__main__":
    main()
