# Panel connection drawings

I wanted a way to check a panel's wire list before drawing every connection by
hand. The filling-line example gives each sensor, switch, indicator, contactor
coil and valve a numbered connection. A smaller cockpit-style panel has three
labelled toggle switches, three indicator lights and a six-pin harness connector.
Both examples are simulated design exercises.

## Generate or check a panel

Install the Python dependencies from `requirements-dev.txt`, then run from the
repository root:

```sh
python -m wiring examples/filling-line --plc plc/line.xml --output drawings/filling-line --name filling-line
python -m wiring examples/cockpit --output drawings/cockpit --name cockpit
python -m wiring examples/filling-line --plc plc/line.xml --check
python -m unittest discover -s tests -p 'test_wiring*.py' -v
```

`--check` writes nothing and exits nonzero if a connection or PLC address is
wrong. It is suitable for CI. Generation validates first, renders in a temporary
directory, then publishes the completed files. A bad layout value cannot
replace a previous valid BOM with a partial export.

The committed examples can be opened without running Python:

- `drawings/filling-line/filling-line.qet`: five editable wiring folios in QElectroTech.
- `drawings/filling-line/filling-line.dxf`: editable power, I/O, terminal schedule,
  panel layout and BOM sheets. All sheets are in model space and named paper layouts.
- `drawings/filling-line/filling-line.pdf`: the six-page printable drawing set.
- `drawings/filling-line/filling-line-bom.csv` and `-bom.xlsx`: consolidated parts
  and cut-wire quantities. Excel also includes the full terminal schedule.
- `drawings/filling-line/filling-line-terminals.csv`: one row for each wire endpoint.

The cockpit folder contains the same formats. Its MASTER, PUMP and LIGHTS labels
are fictional controls for practising panel documentation, not an aircraft design.

## CSV input contract

Each panel is a directory containing three UTF-8 CSV files. Identifiers are
case-sensitive. Every declared pin must have exactly one external wire. For a
branch, declare a distribution block with a separate numbered port for each
wire rather than putting several wires on a single pin.

| File | Required columns | Meaning |
| --- | --- | --- |
| `devices.csv` | `device,part,description,capacity,mount,x_mm,y_mm,width_mm,height_mm` | One purchased or simulated device; capacity is the maximum occupied pin count. `mount` is `panel` or `field`; dimensions are illustrative millimetres. Optional `function` labels the cockpit controls. |
| `pins.csv` | `device,pin,address,signal` | Complete pin inventory. `address` and `signal` are blank for ordinary pins; PLC pins use the exact located address and variable name from `plc/line.xml`. |
| `connections.csv` | `wire,from_device,from_pin,to_device,to_pin,gauge,colour,length_m,sheet` | A cut wire joining two pins; positive finite length in metres; `sheet` is `Power` or `IO`. |

The validator reports duplicate devices, inventory pins, wire numbers and wired
terminals, unknown terminals, self-connections, unconnected pins, missing values
and connector occupancy beyond capacity. Capacity is **pin occupancy**, not an
ampacity or thermal calculation. Wire gauge and colour must be supplied, but
this tool does not infer whether they are electrically suitable.

The BOM groups devices by `part`; the same part must have one consistent
description. It groups wire by gauge and colour and adds lengths with decimal
arithmetic. The Excel quantity cells are numbers. Imported text is stored as
literal text, and CSV text starting with a spreadsheet formula marker receives
an apostrophe so opening a user-supplied description cannot execute a formula.
No price, spare stock or cutting-waste allowance is invented.

## Following the filling-line circuits

The 24 V inlet J0 feeds fuse F1, positive distribution D24 and common return D0.
PLC1 is one simulated controller with nine input pins, six output pins and
24 V supply pins. X1-X15 are feedthrough terminals: each has an F field side
internally connected to its P PLC side. D24/D0 ports are internally common.
Those internal component connections are not extra cut wires.

Inputs run from D24 through a contact and a numbered terminal to the controller.
Outputs run from the controller through a numbered terminal to a lamp, K1's
contactor coil or Y1's valve solenoid, then back to D0. The I/O sheet draws each
complete branch with its cut-wire IDs; the schedule gives every exact endpoint.

`plc/line.xml` is the address authority: `%IX0.0` through `%IX1.0` identify the
nine inputs, and `%QX0.0` through `%QX0.5` identify the six outputs. `Filled` is
an internal latch, so it has no wired hardware terminal. The checker rejects a
missing, duplicate, unknown or incorrectly named address, a duplicate source
address and any mapped pin without exactly one wire. The native controller
continues to use its existing sampled input/output interface; these addresses
are canonical drawing assignments for the simulated panel, not a claim that a
physical PLC has been wired.

The filling-line example contains 35 devices, 100 wired pins and 50 numbered
wires. Its cut list totals 12 m blue, 6.4 m red and 4.35 m black 18 AWG wire.
The cockpit example contains seven devices and nine wires, totalling 2.4 m red
and 2.4 m black wire. These fixed totals have independent test assertions.

## Drawing formats and checks

The QElectroTech export is XML in the 0.90 project format. It embeds its own
original pin-view symbols, so no external symbol library is required. Each row
shows a device-pin reference at each end of a real QElectroTech conductor,
labelled with wire number, gauge and colour. Repeated device labels are views
of different pins of the same device, not extra BOM quantities. Instance labels
use modern `dynamic_texts`, rather than relying only on legacy text inputs.
The generated project was opened in native QElectroTech 0.200.1 on macOS and its
five folios, pin labels and conductor numbers were inspected.

DXF and PDF use the same drawing primitives. The native CAD file has distinct
A3 paper layouts for power, I/O, both terminal schedule pages, panel layout and
BOM, plus all sheets in model space. The panel footprints come from the CSV,
not a screenshot. Tests load and audit the generated DXF, reopen the Excel
workbook and compare every BOM quantity with the CSV model. The exported PDF
pages were rendered and visually inspected for clipped or overlapping content.

The QElectroTech format follows the [upstream XML example](https://www.qelectrotech.org/wiki_new/en/doc/documentation_xml_schemas_exemple)
and the [official example projects](https://github.com/qelectrotech/qelectrotech-source-mirror/tree/master/examples).
The [QElectroTech manual](https://qelectrotech.org/) explains editing and printing
folios. DXF is produced with [ezdxf](https://ezdxf.readthedocs.io/).

## Limits

Generic study parts and footprints are not manufacturer selections. The drawing
set covers a simulated 24 V control panel; it excludes mains wiring, motor power,
overload coordination, enclosure/heat calculations and physical safety circuits.
EStopOK and GuardClosed are simulated permissives, not a safety-rated emergency
stop or guard chain. Any physical build needs its own component selection,
ratings, protective design and qualified review. Editing a generated drawing in
CAD does not update its source CSV; make lasting changes in the CSV and regenerate.
