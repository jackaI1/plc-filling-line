# Control and maintenance notes

## Build and edit the ladder

The controller uses IEC 61131-3 ladder logic in `plc/line.xml` (PLCopen TC6).
The pinned OpenPLC v3 editor's generator exports it to Structured Text in
`plc/line.st`. OpenPLC's matiec compiler translates that to C; `plc/bridge.c`
exposes the compiled controller to Python. A native library executes every scan.

```text
plc/line.xml
  -> tools/openplc_export.py (upstream OpenPLC ladder generator)
  -> plc/line.st
  -> matiec iec2c -> .build/generated/POUS.c + plc/bridge.c
  -> .build/line.so or line.dylib
  -> fillingline/controller.py (sample inputs, execute scan, read outputs)
  <-> fillingline/plant.py (sensors, bottle motion and liquid level)
  -> fillingline/server.py -> web/ (HMI and SQLite maintenance log)
```

The first build fetches exact editor and compiler revisions under `.build/`.
Their source and licenses stay in those checkouts. The headless exporter replaces
only UI translation lookup; it uses the upstream parser, standard-block
definitions and ladder generator unchanged. This is the v3 toolchain, not a
claim to support every OpenPLC v4 project format. The XML includes wire
coordinates for inspection in the legacy OpenPLC v3/Beremiz PLCopen editor.
Automated import/export and schema validation are tested; no physical PLC or
OpenPLC web runtime deployment is claimed.

After changing `plc/line.xml`, run from the repository root with the development
environment activated:

```sh
python tools/openplc_export.py
python tools/render_ladder.py
python tools/build.py
python tools/validate_schema.py
python -m playwright install chromium
python -m unittest discover -s tests -v
```

`tools/ladder.py` independently checks the supported contact/coil/TON/CTU/R_TRIG
graph and rejects broken links, cycles and unsupported elements. CI rejects
stale Structured Text, validates the PLCopen schema and compiles the native IEC
code before testing. Screenshots are CI artifacts; the README image contains
only fictional test records.

`python -m fillingline.practice` runs a bounded conveyor-stall exercise against
that same native controller. Each checkpoint reports the actual simulated scan
time and observed outputs, counter and work orders. It raises an error if a trip,
reset or completed batch fails its expected state, and always closes its native
controller and in-memory SQLite connection. It uses virtual time without sleeps.

## I/O map

The adapter samples these BOOL inputs at each 50 ms virtual scan. These are named simulation points, not claimed hardware addresses.

| Bit | Input | Meaning when true |
| --- | --- | --- |
| 0 | Start | Momentary run request; rising edge required |
| 1 | Stop | Stop request; dominates Start |
| 2 | Reset | Clear batch and request fault reset |
| 3 | EStopOK | Simulated emergency-stop permissive healthy |
| 4 | GuardClosed | Simulated guard permissive healthy |
| 5 | TankOK | Enough product available |
| 6 | BottleAtFill | Bottle occupying fill position |
| 7 | ExitSensor | Bottle at line exit |
| 8 | JamSwitch | Explicit jam trip input |

| Bit | Output | Purpose |
| --- | --- | --- |
| 0 | Run | Run seal-in state |
| 1 | Conveyor | CV-01 motor command |
| 2 | Valve | FV-01 valve command |
| 3 | Alarm | Latched fault indication |
| 4 | BatchDone | Five bottles counted |
| 5 | Filled | Internal fill-complete latch exposed for inspection |

`ExitEdge` observes the sensor even while stopped. Its pulse is gated by Run before the CTU input, so a sensor held high across a reset/restart cannot count the same bottle twice. CTU counts rising edges, not scans. Start also uses an R_TRIG block, so holding Start through a trip and reset cannot restart the line.

## Sequence and timing

- `FillTimer` is a TON with a one-second preset; filling inhibits conveyor travel. `Filled` holds until the bottle leaves the fill sensor or Run drops.
- `JamTimer` is a three-second TON driven by the **previous scan's** Conveyor command and absence of the exit sensor. Normal bottle motion/filling resets it. This models a travel timeout, not motor-current monitoring.
- Faults latch for unhealthy permissives, JamSwitch, a travel timeout or an interrupted fill. They clear only when the cause is healthy, the fill position is empty and Reset is requested.
- Resetting a stopped simulation discards its current bottle as a manual operator action. It is not a physical reject actuator in the ladder. Reset does not start the line.
- The actual OpenPLC exporter emits function-block calls before the coils. Read `plc/line.st` for executable scan order: edge detectors, counter, timers, Fault, Run, Filled, Conveyor, Valve, Alarm and BatchDone. The fill timer reads the prior Run state; output coils use the current interlocks. Tests check timer boundaries and same-scan output de-energization.
- Native IEC function blocks retain their instance state between scans. The C bridge supplies `__CURRENT_TIME`; Python advances it in fixed 50 ms steps. The HTTP server and scans run on one thread, so no concurrent native scans share that clock.
- Native PLC state and simulated bottle position start fresh after a process restart. Only maintenance orders/events persist. No automatic production restart or retained batch counter is implied.

## Assets and records

`CV-01` is the conveyor, `FV-01` the fill valve/nozzle, and `Line-01` the overall line. Each work order has an asset, corrective/preventive type, issue, open/closed status, opening/closing timestamps and resolution. SQL parameters and DOM text nodes keep notes as data. A rising alarm creates one corrective order per trip, not one per scan. Acknowledging preventive service requires a stopped line and a completed preventive order.

The 30-second preventive interval is deliberately accelerated for demonstration. It is not a manufacturer maintenance interval. This project does not establish hands-on PLC commissioning or commercial CMMS proficiency.

## QA inventory

| Claim / operator control | Check |
| --- | --- |
| Start, Stop and seal-in | Native scan tests; browser starts actual batch |
| Timed fill and five-bottle completion | Timer boundary, CTU held-input tests, complete simulated plant and browser batch |
| Emergency stop, guard, tank and jam | Native interlock tests, randomized scans, browser emergency-stop trip and plant travel timeout |
| Recovery and held Start | Native reset/edge tests; browser clear → reset → fresh start |
| Partial-fill recovery | Native fault test and plant discard test |
| Add/close work order | Browser form, mandatory resolution, literal markup rendering and SQLite reopen test |
| Preventive service | Accelerated interval and stopped-line service gate tests |
| Desktop/mobile readability | Real-browser screenshots at 1440 and 390 px; no document overflow |
| Local control boundary | Foreign-origin request and invalid command rejected; arbitrary paths unavailable |
| Resource cleanup | Test process handle terminated, page/context/browser closed, owned port checked closed |

## Upstream references

- [OpenPLC v3 editor at the pinned revision](https://github.com/thiagoralves/editor/tree/6a8e930a914e4421e8fa05966b31eb371b439243), including `PLCGenerator.py`, `plcopen/` and `xmlclass/` (GPL terms in upstream COPYING).
- [OpenPLC matiec at the pinned revision](https://github.com/thiagoralves/matiec/tree/75d6e82cce5bc8b98ce03a417b106884cbb7ebb5), compiler and IEC standard-block implementation (upstream compiler/library license terms apply).
- [PLCopen TC6 schema used for validation](https://github.com/thiagoralves/editor/blob/6a8e930a914e4421e8fa05966b31eb371b439243/plcopen/tc6_xml_v201.xsd).
