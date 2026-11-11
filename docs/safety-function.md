# Safety function specification: emergency stop and guard interlock

This is a specification for the simulated safety layer. It is not a certified
safety product and it is not wired into the 24 V drawings. It shows how the
stop paths are designed, how the design is estimated against ISO 13849-1, and
how each single fault is injected and checked.

## 1. Purpose

The filling line has two safety functions:

- **Emergency stop (EStop).** Pressing the mushroom button removes power from
  the conveyor motor and the fill valve.
- **Guard interlock (Guard).** Opening the guard removes the same power.

Both functions are kept separate from the PLC ladder in `plc/line.xml`. The PLC
still sees them as permissives, so it trips and reports the cause. The drives,
however, are gated by the safety layer, so a wrong PLC output alone cannot run
them while a safety function is tripped.

## 2. Inputs and channels

Each function has two channels, A and B, from two independent contacts. A
channel reads **True when healthy**: the emergency stop is released or the guard
is closed. This is the usual normally-closed convention.

| Input | Meaning |
| --- | --- |
| EStop A, EStop B | Emergency-stop contacts |
| Guard A, Guard B | Guard position switch contacts |
| Safety reset | Monitored reset input, a contact separate from the PLC Reset |

The panel's single **Reset** button drives both the PLC Reset and the safety
reset, as one pushbutton with two contacts would.

## 3. Behaviour

| Rule | Behaviour |
| --- | --- |
| Trip | Any channel reading unhealthy trips its function in the same scan. The trip latches. |
| Drive gate | While a function is tripped, motor and valve power are off, whatever the PLC commands. |
| PLC permissive | The PLC's EStopOK and GuardClosed inputs carry the function's enabled state, so the ladder also trips and raises its alarm. |
| Channel disagreement | If A and B disagree for 100 ms (two 50 ms scans), a channel fault latches. A single-scan difference is treated as contact bounce and does not latch. |
| Monitored reset | A reset is accepted only on a rising edge, only while the function is healthy (so both channels agree). A reset held through a trip does nothing. |
| Diagnostic clear | An accepted reset also clears a channel-fault diagnostic. |
| Independence | The two functions latch separately. A guard fault does not clear, or depend on, the e-stop. |

The safety layer runs before the PLC scan in each 50 ms step. The PLC never
clears a safety latch.

## 4. Single-fault injection

Each case in `fillingline/safety_check.py` starts a five-bottle batch, injects
one fault, demands the safe state, checks the trip, removes the fault, and then
checks that a monitored reset and a fresh start complete a five-bottle batch.
The run uses virtual time and needs no server. `tests/test_safety.py` runs every
case in CI.

Result of `python -m fillingline.safety_check` (virtual time, 50 ms scans):

| Case | Motor and valve off in the trip scan | Channel disagreement latched | Reset refused while the fault is present | Five-bottle batch after repair and reset |
| --- | --- | --- | --- | --- |
| E-stop channel A stuck healthy | Yes | Yes | Yes | Yes |
| E-stop channel B stuck healthy | Yes | Yes | Yes | Yes |
| E-stop channel A stuck open (no press) | Yes | Yes | Yes | Yes |
| Guard channel A stuck healthy | Yes | Yes | Yes | Yes |
| Guard channel B stuck open (guard closed) | Yes | Yes | Yes | Yes |
| Safety reset contact welded closed, then e-stop pressed | Yes | No | Yes | Yes |
| PLC ladder commands conveyor and valve on during an e-stop press | Yes | No | Yes | Yes |

What the cases show:

- **A stuck-healthy channel is the dangerous single fault.** Channel A reports
  healthy while the button is pressed. Channel B still opens, so the trip happens
  anyway. Channel A and B then disagree, and the disagreement latches a
  diagnostic after two scans. The next reset is refused until the channels agree.
- **A stuck-open channel is a nuisance fault.** The line stops and the
  diagnostic appears. Nothing unsafe happens.
- **A welded reset contact cannot restart the line.** With the contact welded
  closed there is never a rising edge, so the monitored reset is never accepted.
- **A wrong PLC output does not move the drives.** This is the hard-wired gate.

## 5. Performance level estimate

The estimate uses the method in ISO 13849-1: channel MTTFd from component B10d
and demand rate, diagnostic coverage from the measures in place, and a
category. Run `python tools/safety_pl.py` to print the calculation, and
`python tools/safety_pl.py --markdown` to print the table below.

| Function | Category | DC | DCavg | MTTFd per channel | MTTFd band | Result |
| --- | --- | --- | --- | --- | --- | --- |
| Emergency stop | 3 | medium | 90% | 50 years | high | PL d |
| Guard interlock | 3 | medium | 90% | 50 years | high | PL d |

How the numbers are derived:

1. **Demand rates.** The emergency stop is pressed once per working day
   (250 per year). The guard opens once an hour during an 8-hour shift
   (2,000 per year). These are assumptions for a training line.
2. **Channel MTTFd.** MTTFd = B10d / (0.1 × demands per year), capped at 100 years.
   Each channel has two components in series: the contact and the safety relay
   contact. Both use an assumed B10d of 100,000 cycles. Each component caps at
   100 years, so each channel is 1 / (1/100 + 1/100) = 50 years, in the "high" band
   (30 to 100 years).
3. **Function MTTFd.** The function takes the lower of its two channels. Both are
   50 years, so this is conservative in the same way as the symmetry rule.
4. **Diagnostic coverage.** Medium (90%), the level assumed for two channels
   compared against each other with a monitored reset. A stuck channel is found
   when it disagrees, which happens on a demand. Only a dynamic test, such as an
   automatic function test every cycle, would justify high coverage.
5. **Category 3.** A single fault does not stop the function (the other channel
   still trips it), and the fault is found at the next demand where the channels
   differ. That is the category 3 requirement.
6. **Result.** Category 3, DC medium and MTTFd high give PL d.

To reach PL e, the design would need category 4 with high DC (99%). That means
automatic testing of each channel and the reset path at every cycle, which is not
implemented here.

**Assumptions to check before any real use:** the B10d values, the demand rates,
the DC level and the PL mapping. The mapping is hard-coded in `tools/safety_pl.py`
only for the combinations this design uses. Verify the table values against the
edition of ISO 13849-1 in use.

## 6. Limitations

- This is a software simulation. The safety layer does not use certified hardware,
  and the panel drawings in `drawings/` still show the single-channel PLC
  permissives.
- Two identical stuck channels that agree with each other are not caught by
  comparison. Only a demand, or a dedicated test, reveals them.
- Timing (100 ms discrepancy time, 50 ms scans) is an example value, not a
  measured response time.
- No common-cause analysis, power-up test or reset-path diagnostics are modelled.

## 7. Evidence and how to reproduce

- `tests/test_safety.py`: unit tests for the trip, reset, discrepancy and
  independence rules, plus the fault-injection cases and the check that this
  document matches the runner and the calculation.
- `python -m fillingline.safety_check`: prints the table in section 4 and fails
  if any case fails.
- `python tools/safety_pl.py`: prints the calculation in section 5.
- Code: `fillingline/safety.py` (the functions), `fillingline/plant.py` (wiring
  into the plant and the drive gate), `fillingline/safety_check.py` (cases).
