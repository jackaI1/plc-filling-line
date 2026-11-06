"""python -m wiring: generate the project's connection drawings and cut list."""
import argparse
from pathlib import Path
from .project import load_panel, export_panel, check_addresses


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('panel', type=Path, help='Directory containing devices.csv, pins.csv and connections.csv')
    parser.add_argument('--output', type=Path, default=Path('drawings/generated'))
    parser.add_argument('--name', default='panel')
    parser.add_argument('--plc', type=Path, help='Check every located variable in this PLCopen XML')
    parser.add_argument('--check', action='store_true', help='Validate inputs and PLC map without writing files')
    args = parser.parse_args()
    try:
        panel = load_panel(args.panel)
        if args.plc:
            errors = check_addresses(panel, args.plc)
            if errors:raise ValueError('\n'.join(errors))
        if not args.check:
            export_panel(panel,args.output,args.name,args.plc)
        print(f"Validated {len(panel['devices'])} devices, {len(panel['pins'])} pins and {len(panel['wires'])} wires")
    except (ValueError, KeyError, OSError) as exc:
        parser.exit(1, str(exc)+'\n')


if __name__=='__main__':main()
