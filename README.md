# PLC filling-line training bench

I built a simulated bottle-filling line with a browser control panel and maintenance log because I wanted to practise fault recovery without physical equipment.

## Overview

When a conveyor stops, clearing the fault and getting it running again are separate
steps. I wanted a small bench where I could practise that sequence, see why the
motor or valve stayed off, and keep a record of what I checked without needing
physical equipment.

This personal project runs a five-bottle batch on a simulated conveyor. I use the
browser control panel to watch each bottle fill, stall the conveyor or open a
guard, then work through clearing the cause, resetting and starting again. The
maintenance log records corrective work after a fault and opens a nozzle
inspection order at an accelerated practice interval.

Follow the setup below, open **http://127.0.0.1:8765**, and press **Start line**.
The panel shows the conveyor, valve, sensors and bottle count. For a quick
terminal walkthrough after building, run `python -m fillingline.practice`.
Everything here is simulated; it does not connect to real equipment.

## Run locally

Requires Python 3.9+, Git and a C/C++ compiler. Install the build tools for your
operating system first. On Ubuntu / Debian:

```sh
sudo apt-get update
sudo apt-get install -y build-essential autoconf automake bison flex python3-venv git
```

On macOS (Apple Silicon Homebrew shown; install Xcode Command Line Tools for the
C/C++ compiler if needed):

```sh
brew install autoconf automake bison flex
export PATH="/opt/homebrew/opt/bison/bin:/opt/homebrew/opt/flex/bin:$PATH"
```

Then get the project and start the panel:

```sh
git clone https://github.com/jackaI1/plc-filling-line.git
cd plc-filling-line
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
python tools/build.py
python tools/validate_schema.py
python -m fillingline.server
```

Open **http://127.0.0.1:8765**. Stop with Ctrl+C. Use `--port 8766` if the default
port is occupied. Work orders persist in `.build/maintenance.sqlite3`; use
`--db /path/to/demo.sqlite3` for a separate log. That directory is ignored by Git.
The server accepts connections from this computer only.

The first build downloads the pinned OpenPLC tools into `.build/` and compiles
the controller. It does not install a background service. No Python packages are
needed by the running panel; the build tools use `lxml`.

![Local control panel showing simulated equipment, live inputs and outputs, and maintenance work orders](docs/hmi.png)

## Try a fault and recovery

1. Press **Start line**. The conveyor stops each bottle under the valve for a
   one-second fill. The fifth bottle reaching the exit ends the batch.
2. While running, select **Stall conveyor**. After three seconds of commanded
   travel without an exit signal, the line trips and a corrective work order
   appears.
3. Clear the stall. The alarm stays latched until you press
   **Reset batch / discard bottle**. Reset clears the batch and removes the
   current simulated bottle; you must press **Start line** to run again.
4. Enter a resolution and close the work order. Closing an order records the
   work; it does not reset or start the line.
5. Try a low tank, open guard or emergency-stop input. The motor and valve turn
   off in the next simulation step. Reset cannot override an unhealthy input.

Stopping mid-fill also requires a reset and removal of the partly filled bottle.
After 30 seconds of accumulated running time, the log opens a preventive nozzle
inspection order. Stop the line, complete that order and acknowledge service.
This short interval makes the workflow easy to try; it is not a maintenance
recommendation for real equipment.

To follow the conveyor-stall recovery in the terminal instead:

```sh
python -m fillingline.practice
```

It prints the simulated time, motor and valve state, bottle count and work-order
status at each checkpoint. It clears the stall, closes the order, checks that
neither action restarts the line, then resets and starts a full five-bottle batch.
It runs the same compiled controller and plant as the browser, with an isolated
in-memory log. It opens no server and leaves the browser's saved work orders alone.

## Controller and tests

The control program lives in [plc/line.xml](plc/line.xml), a ladder diagram made
of contacts, coils, timers and a bottle counter. OpenPLC exports it to code that
is compiled and run by Python. The browser displays its decisions and sends
operator requests; it does not decide when the motor or valve runs.

See [the ladder diagram](docs/ladder.svg) and
[control and build notes](docs/control-notes.md) for the input/output map,
scan order, toolchain and instructions for changing the ladder.

After setup, run:

```sh
python -m playwright install chromium
python -m unittest discover -s tests -v
```

CI rebuilds the controller and checks that its exported code matches the ladder.
Tests exercise timed filling, counting, fault recovery, 2,000 randomized input
steps, saved maintenance records, the terminal walkthrough and the browser panel.
The browser test also checks the panel at desktop and phone widths. It closes its
test page, browser and server and verifies that the server port is closed.

## Scope

This is a personal practice simulation with idealized sensors and virtual time.
It has no physical PLC, connected equipment or hardware safety circuit. It does
not establish dosing accuracy, real-time response or safe control of a machine.
The maintenance log is a small local work-order record, not a commercial CMMS.

Project code is MIT licensed. The OpenPLC editor and matiec compiler keep their
upstream licenses. See [upstream references](docs/control-notes.md#upstream-references).
