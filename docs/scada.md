# Operating the simulated line through FUXA

I wanted the operator screen to read the same controller over a normal industrial
connection. FUXA is an open-source web SCADA system: it reads equipment values,
shows them on a screen, and records warnings. Here its equipment is my simulated
plant, running the existing OpenPLC-generated ladder program.

## Start it

Build the controller and install the Python requirements using the README first.
Install Node.js 22 or 24, then run:

```sh
npm --prefix scada ci --ignore-scripts=false
```

Run these in two terminals from the repository root:

```sh
python -m fillingline.modbus
```

```sh
npm --prefix scada start
```

Open <http://127.0.0.1:1881/resources/operator/index.html>. Start the line and watch
the bottle move, the motor turn, and the valve open while the bottle fills. The
fill-count graph keeps up to 60 seconds of received readings. Its vertical axis
is the number of completed bottles, from zero to five.

Select **Hold fill sensor on**, then start. Once the filled bottle fails to leave
the sensor, the controller stops the motor and valve. **Acknowledge alarm** marks
the FUXA warning as seen. It does not clear the controller fault or start anything.
Reset while the sensor remains held on is refused. Release the checkbox, reset,
then start again. Reset discards the current virtual bottle and clears the count.

Stop both terminals with Ctrl+C. The adapter closes its listener and accepted
clients. FUXA closes with its upstream shutdown handler. Neither installs a
background service. Both listeners accept connections only from this computer.
If npm 11 reports that native install scripts were withheld, run
`npm --prefix scada rebuild sqlite3 @serialport/bindings-cpp --ignore-scripts=false`
after reviewing the pinned packages. This builds the local database and serial
bindings; the demo uses TCP, not serial hardware.

## What is connected

```text
FUXA-hosted browser screen
  | Socket.IO values, FUXA alarm HTTP API
FUXA Modbus driver, alarm manager and local database
  | Modbus TCP, localhost port 1502, unit 1
Python register adapter and virtual plant
  | existing 50 ms native scan
OpenPLC/matiec controller compiled from plc/line.xml
```

The operator page is served by FUXA under `/resources/operator/`. The committed
[`filling-line.fuxap`](../scada/filling-line.fuxap) project also embeds it in a native
FUXA iframe view. Open <http://127.0.0.1:1881/editor> to inspect the device and alarm
configuration. The launcher imports this project on every start, so save any
editor experiments as an export before restarting it.

The launcher uses the published FUXA package without changing upstream source.
Its plugin scanner expects a dependency folder beside the package; npm hoists
those dependencies. A directory link exposes that existing folder without making
a second copy. Generated settings, resources, project data and alarm history stay
in `.build/fuxa/`. Override `FUXA_WORK`, `FUXA_PORT` and `MODBUS_PORT` to isolate a
second instance; pass the matching `--port` to the Python adapter.

## Tag map

[`scada/tag-map.csv`](../scada/tag-map.csv) lists every tag and its register.
Modbus TCP uses zero-based offsets on the wire. FUXA's address field is one-based,
so protocol offset 15 is FUXA address 16 in the holding-register area (400000).
All values are unsigned 16-bit integers, with Boolean values represented by 0/1.

| Protocol offsets | Tags | Meaning |
| --- | --- | --- |
| 0 to 8 | Start, Stop, Reset, EStopOK, GuardClosed, TankOK, BottleAtFill, ExitSensor, JamSwitch | Inputs from the last scan, with ladder names unchanged |
| 9 to 15 | Run, Conveyor, Valve, Alarm, BatchDone, Filled, FillBlocked | Outputs from the compiled program; Filled is an internal state |
| 16 | BatchCount | The ladder counter's `BatchCount.CV` |
| 17, 18 | BottlePosition, BottleLevel | Plant position and level scaled from 0 to 1000 |
| 100, 101, 102 | StartCommand, StopCommand, ResetCommand | Write 1 to queue one button press; reads return 0 |
| 103 | HoldFillSensor | Read/write the simulated stuck sensor switch |

Telemetry registers are read-only at the adapter. Button writes are queued for
the scan thread, keeping the controller and maintenance database under one owner.
The protocol supports function 03 (read holding registers) and 06 (write one
holding register), with exceptions for unsupported functions, unknown addresses,
and invalid command values. It accepts unit 1 only. The screen disables controls
and labels equipment **Unknown** if its readings stop arriving or the link drops.

## Alarm and trend behaviour

`FillBlocked` is a native FUXA high alarm for register value 1. Its acknowledgement
mode permits acknowledgement while the fault is active. The screen reads
`/api/alarms` and posts `/api/alarmack`; it does not keep an independent browser
alarm state. FUXA retains alarm events in its local database. The count graph is
a bounded live session trace of FUXA's received `BatchCount` values; it does not
restore a historical graph after a browser reload. The project also enables
FUXA data acquisition for the count tag.

The animated SVG shows received plant position, fill level, `Conveyor` and `Valve`
values. Reduced-motion preferences stop decorative rotation and belt movement;
position and status still update. The simulation has no real hardware, certified
safety system, authentication for remote operation, or guaranteed real-time
response. Keep these listeners on loopback. Acknowledgement is an operator record,
not an electrical reset.

## Repeat the checks

After the controller build, npm setup and Playwright browser setup:

```sh
python -m unittest discover -s tests -p 'test_scada*.py' -v
```

The tests start the compiled plant, exercise actual Modbus packets, verify five
bottles and fault recovery, then start upstream FUXA and a real browser. They
check live motor/valve/bottle animation, the native alarm acknowledgement, refused
reset, a complete five-bottle batch, the live count trace, a phone-width layout,
and disconnected-controller behaviour. Each test owns its temporary listeners,
process handles and browser, closes them in `finally`, and checks the ports closed.

FUXA is MIT licensed; see its [source and installation instructions](https://github.com/frangoteam/FUXA).
