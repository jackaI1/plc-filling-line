# PLC filling-line training bench

[![PLC simulation](https://github.com/jackaI1/plc-filling-line/actions/workflows/ci.yml/badge.svg)](https://github.com/jackaI1/plc-filling-line/actions/workflows/ci.yml)

A small bottle-filling line for practising PLC control and maintenance troubleshooting. Start a five-bottle batch, watch the simulated conveyor stop under the fill valve, inject a fault, then recover the line and record the work performed.

The controller is **real IEC 61131-3 ladder logic** in [plc/line.xml](plc/line.xml). The actual OpenPLC v3 editor's code generator exports it to Structured Text, and OpenPLC's matiec compiler compiles it to C. A native library executes every PLC scan; the browser does not decide when the motor or valve runs.

![Local HMI showing simulated equipment, live I/O and maintenance work orders](docs/hmi.png)

## Run locally

Requires Python 3.9+, Git, a C/C++ compiler, autoconf, automake, Bison 3+ and Flex. No Python packages are needed by the running HMI; `lxml` is needed for the OpenPLC build tools.

```sh
# Ubuntu / Debian
sudo apt-get update
sudo apt-get install -y build-essential autoconf automake bison flex python3-venv git

# macOS alternative (Apple Silicon Homebrew shown)
brew install autoconf automake bison flex
export PATH="/opt/homebrew/opt/bison/bin:/opt/homebrew/opt/flex/bin:$PATH"

python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
python tools/build.py
python tools/validate_schema.py
python -m fillingline.server
```

Open **http://127.0.0.1:8765**. Stop with Ctrl+C. The server binds only to loopback and rejects foreign Host/Origin headers. Use `--port 8766` if the default port is occupied. Work orders persist in `.build/maintenance.sqlite3`; use `--db /path/to/demo.sqlite3` for a separate ledger. The directory is ignored by Git.

The first build fetches the exact pinned OpenPLC editor and matiec revisions into `.build/`; no system OpenPLC runtime, container or background daemon is installed. Compiler source and licenses remain in those checkouts. The headless exporter replaces only UI translation lookup, using the upstream parser, standard-block definitions and LD generator unchanged. These are the **v3 toolchain**, not a claim to support every OpenPLC v4 project format.

## Try the operator workflow

1. Press **Start line**. The fill sensor stops the conveyor, the valve opens for one second and the bottle indexes out. The fifth exit-sensor rising edge ends the batch.
2. Reset while stopped to clear the batch and discard the current simulated bottle. A fresh Start is always required.
3. Select **Stall conveyor**. After three seconds of commanded travel without an exit pulse, the controller trips and a corrective work order appears. Clear the stall, Reset, then Start.
4. Try a low tank, open guard or emergency-stop input. The motor and valve turn off in the next simulated scan. Clearing an input alone does not restart equipment. Reset cannot override an unhealthy permissive.
5. Enter a resolution and close a work order. The accelerated preventive interval opens a nozzle inspection order after 30 seconds of running time. Stop, complete that order and acknowledge service.

Stopping mid-fill latches a recovery fault. A partially filled bottle must be removed before the fault can reset; the HMI's **Reset batch / discard bottle** models that manual recovery action. Closing a maintenance order does not reset the PLC or energize outputs.

## Skills demonstrated

- **PLC programming (ladder logic, OpenPLC):** series/parallel contacts, seal-in logic, permissives, latched trips, `TON` timers, `R_TRIG` edge detection and a `CTU` batch counter, exported and compiled with the actual OpenPLC v3 toolchain.
- **Simulated equipment and HMI:** a deterministic bottle/conveyor model, 50 ms virtual PLC scans, live I/O monitoring, batch controls and fault injection.
- **CMMS concepts:** asset-linked corrective/preventive work orders, required completion notes, timestamps, persistent SQLite storage and event history. This is a small demonstration, not experience with a commercial CMMS product.
- **Verification:** native controller tests, 2,000 randomized interlock scans, full-plant batch/fault recovery tests, persistent maintenance records, and real Chromium HMI tests on CI.

## How the controller runs

```text
plc/line.xml (PLCopen TC6 ladder diagram)
  → tools/openplc_export.py (pinned upstream OpenPLC LD generator)
  → plc/line.st (checked-in, reproducible Structured Text)
  → OpenPLC matiec iec2c (pinned revision)
  → .build/generated/POUS.c + plc/bridge.c
  → .build/line.so or line.dylib
  → fillingline/controller.py (ctypes; sampled inputs → PLC scan → outputs)
  ↔ fillingline/plant.py (sensors, bottle motion and liquid level)
  → fillingline/server.py → web/ (local HMI and SQLite maintenance log)
```

See [the ladder diagram](docs/ladder.svg), [I/O and scan notes](docs/control-notes.md), and [the actual exported ST](plc/line.st). The source contains wire coordinates so it can also be inspected with the legacy OpenPLC v3/Beremiz PLCopen editor. Automated import/export and schema validation are tested; no physical PLC or OpenPLC web runtime deployment is claimed.

To edit control logic, change `plc/line.xml`, then run:

```sh
python tools/openplc_export.py
python tools/render_ladder.py
python tools/build.py
python tools/validate_schema.py
python -m playwright install chromium
python -m unittest discover -s tests -v
```

`tools/ladder.py` independently checks the project's supported contact/coil/TON/CTU/R_TRIG graph and rejects broken links, cycles and unsupported elements. CI rejects stale ST, validates the PLCopen schema, builds native IEC code and exercises the controller, plant, maintenance log and real HMI. Browser tests own and close their server, page and Chromium process, then verify the port is closed. Screenshots are CI artifacts; the README image uses fictional test records.

## Scope

This is a training simulation with virtual time and idealized sensors. It is **not a safety-rated controller** or a production machine design. There is no physical I/O, Modbus link, calibrated flow model, dosing accuracy claim, hardware emergency-stop circuit, independent safety relay or validated equipment guarding. Scheduler delays slow virtual time rather than proving a real-time response. A real installation needs engineered safety circuits, risk assessment, commissioning and hardware testing.

Project code is MIT licensed. The OpenPLC editor and matiec retain their respective upstream licenses; they are fetched as build dependencies, not relicensed as this project's code. See [upstream references](docs/control-notes.md#upstream-references).
