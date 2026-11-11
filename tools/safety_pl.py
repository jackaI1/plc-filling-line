"""Estimate the performance level (PL) of the simulated safety functions, ISO 13849-1 style.

Method, summarised in docs/safety-function.md:
  channel MTTFd = B10d / (0.1 * nop), capped at 100 years (ISO 13849-1 limit);
  a series chain's MTTFd is 1 / sum(1 / MTTFd_component);
  the function's MTTFd is the lower of its two channels (conservative for two equal channels);
  PL comes from category, diagnostic coverage (DC) and MTTFd.

Every input below is an assumption to replace with datasheet values before any real use.
Run `python tools/safety_pl.py` to print the table; `--markdown` prints the spec's table.
"""
import argparse

MISSION_DAYS = 250     # Working days per year.
HOURS_PER_DAY = 8      # Operating hours per day.
MTTFD_CAP = 100.0      # Years; ISO 13849-1 caps a channel's MTTFd here.
DC_LEVELS = {"none": 0.0, "low": 0.60, "medium": 0.90, "high": 0.99}  # Table E.1 style levels.

# Components per channel: (name, B10d cycles, demands per year). B10d is an assumption.
CHANNEL_COMPONENTS = {
    "EStop": [("emergency-stop contact", 100_000, MISSION_DAYS * 1),          # One press per day.
              ("safety relay contact", 100_000, MISSION_DAYS * 1)],
    "Guard": [("guard position switch contact", 100_000, MISSION_DAYS * HOURS_PER_DAY),  # Door opened hourly.
              ("safety relay contact", 100_000, MISSION_DAYS * HOURS_PER_DAY)],
}
FUNCTION_SETUP = {
    # Category 3 with cross-monitoring of the channels and a monitored reset.
    # Category 4 would need DC high (automatic testing); that is not implemented here.
    "EStop": {"category": 3, "dc": "medium"},
    "Guard": {"category": 3, "dc": "medium"},
}


def channel_mttfd(components):
    """Years for one channel built from components in series, each capped at MTTFD_CAP."""
    inverse_sum = 0.0
    for _name, b10d, demands in components:
        nop = demands  # Demands per year on this component.
        mttfd = min(MTTFD_CAP, b10d / (0.1 * nop))
        inverse_sum += 1.0 / mttfd
    return min(MTTFD_CAP, 1.0 / inverse_sum)


def mttfd_band(years):
    if years < 3:
        return "below low"
    if years < 10:
        return "low"
    if years < 30:
        return "medium"
    return "high"


def performance_level(category, dc_name, band):
    """Published PL mapping for the combinations this project uses; anything else is refused."""
    if category == 4 and dc_name == "high" and band == "high":
        return "e"
    if category == 3 and dc_name == "medium" and band == "high":
        return "d"
    if category == 3 and dc_name == "low" and band == "high":
        return "c"
    raise ValueError(f"Mapping not implemented for category {category}, DC {dc_name}, MTTFd {band}")


def evaluate():
    rows = []
    for function, components in CHANNEL_COMPONENTS.items():
        channel_years = channel_mttfd(components)
        band = mttfd_band(channel_years)
        setup = FUNCTION_SETUP[function]
        pl = performance_level(setup["category"], setup["dc"], band)
        rows.append({"function": function, "category": setup["category"], "dc": setup["dc"],
                     "dc_percent": round(DC_LEVELS[setup["dc"]] * 100), "mttfd_years": round(channel_years, 1),
                     "mttfd_band": band, "pl": pl})
    return rows


def markdown(rows):
    lines = ["| Function | Category | DC | DCavg | MTTFd per channel | MTTFd band | Result |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    names = {"EStop": "Emergency stop", "Guard": "Guard interlock"}
    for row in rows:
        lines.append(f"| {names[row['function']]} | {row['category']} | {row['dc']} | {row['dc_percent']}% | "
                     f"{row['mttfd_years']:.0f} years | {row['mttfd_band']} | PL {row['pl']} |")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--markdown", action="store_true", help="print only the markdown table")
    args = parser.parse_args()
    rows = evaluate()
    print(markdown(rows) if args.markdown else "\n".join(str(row) for row in rows))


if __name__ == "__main__":
    main()
