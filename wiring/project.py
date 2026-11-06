"""Validated CSV panel model, consolidated BOM and reproducible drawing exports."""
from collections import Counter
import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path
import xml.etree.ElementTree as ET

from .validate import read_csv, validate


def load_panel(directory):
    directory = Path(directory)
    panel = {key: read_csv(directory / filename) for key, filename in
             [('devices', 'devices.csv'), ('pins', 'pins.csv'), ('wires', 'connections.csv')]}
    errors = panel_errors(panel)
    if errors:
        raise ValueError('\n'.join(errors))
    return panel


def bom(panel):
    """Lengths are cut lengths in metres, with no unstated waste allowance."""
    rows = {}
    for device in panel['devices']:
        part = device['part']
        desc = device['description']
        if not part or not desc:
            raise ValueError('Each device needs a part and description')
        if part in rows and rows[part]['description'] != desc:
            raise ValueError(f'inconsistent description for part {part}')
        row = rows.setdefault(part, dict(item=part, description=desc, quantity=Decimal(0), unit='each'))
        row['quantity'] += 1
    for wire in panel['wires']:
        try:
            length = Decimal(wire['length_m'])
            if not length.is_finite() or length <= 0:
                raise InvalidOperation
        except (InvalidOperation, KeyError):
            raise ValueError(f"invalid wire length: {wire.get('wire')}") from None
        item = f"WIRE:{wire['gauge']}:{wire['colour']}"
        row = rows.setdefault(item, dict(item=item, description=f"{wire['gauge']} {wire['colour']} hookup wire",
                                         quantity=Decimal(0), unit='m'))
        row['quantity'] += length
    return [rows[key] for key in sorted(rows)]


def plc_addresses(path):
    root = ET.parse(path).getroot()
    result = {}
    for v in root.iter():
        if v.tag.rsplit('}', 1)[-1] == 'variable' and 'address' in v.attrib:
            if v.attrib['address'] in result:
                raise ValueError('duplicate PLC source address: ' + v.attrib['address'])
            result[v.attrib['address']] = v.attrib['name']
    return result


def check_addresses(panel, plc_path):
    try:
        expected = plc_addresses(plc_path)
    except ValueError as exc:
        return [str(exc)]
    mapped = [p for p in panel['pins'] if p.get('address')]
    counts = Counter(p['address'] for p in mapped)
    errors = []
    if not expected:
        errors.append('PLC source has no located addresses')
    for addr, name in expected.items():
        if not counts[addr]:
            errors.append(f'missing PLC address: {addr} ({name})')
        elif counts[addr] > 1:
            errors.append(f'duplicate PLC address: {addr}')
    for pin in mapped:
        addr = pin['address']
        if addr not in expected:
            errors.append(f'unknown PLC address: {addr}')
        elif pin.get('signal') != expected[addr]:
            errors.append(f'PLC signal mismatch: {addr}')
        # A mapping counts only if its terminal is connected exactly once.
        connections = sum((w['from_device'], w['from_pin']) == (pin['device'], pin['pin']) or
                          (w['to_device'], w['to_pin']) == (pin['device'], pin['pin']) for w in panel['wires'])
        if connections != 1:
            errors.append(f'PLC address needs exactly one wired terminal: {addr}')
    errors.extend(validate(**panel))
    return errors


def panel_errors(panel, plc_path=None):
    """One complete validation path for checking and generation."""
    import math
    errors = validate(**panel)
    if errors:
        return errors
    for device in panel['devices']:
        for field in ('part', 'description', 'mount'):
            if not isinstance(device.get(field), str) or not device[field].strip():
                errors.append(f"missing device {device['device']} value: {field}")
        if device.get('mount') not in {'panel', 'field'}:
            errors.append(f"invalid mount: {device['device']}")
        geometry = {}
        for field in ('x_mm', 'y_mm', 'width_mm', 'height_mm'):
            try:
                value = float(device.get(field, ''))
                if not math.isfinite(value) or value < 0 or (field in {'width_mm','height_mm'} and value == 0):
                    raise ValueError
                geometry[field] = value
            except (TypeError, ValueError):
                errors.append(f"invalid layout {field}: {device['device']}")
        if len(geometry) == 4 and device.get('mount') == 'panel':
            if geometry['x_mm']+geometry['width_mm'] > 500 or geometry['y_mm']+geometry['height_mm'] > 400:
                errors.append(f"panel footprint outside 500 x 400 mm: {device['device']}")
    for wire in panel['wires']:
        if wire.get('sheet') not in {'Power','IO'}:
            errors.append(f"invalid sheet: {wire['wire']}")
    if not errors:
        try:
            bom(panel)
        except (ValueError, KeyError) as exc:
            errors.append(str(exc))
    if plc_path:
        errors.extend(check_addresses(panel, plc_path))
    return errors


def write_csv(path, rows, fields):
    with Path(path).open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: ("'"+v if isinstance(v, str) and v.lstrip().startswith(('=', '+', '-', '@')) else v) for k,v in row.items()})


def terminal_schedule(panel):
    pins = {(p['device'], p['pin']): p for p in panel['pins']}
    rows = []
    for wire in panel['wires']:
        for side, other in [('from', 'to'), ('to', 'from')]:
            pin = pins[(wire[f'{side}_device'], wire[f'{side}_pin'])]
            rows.append(dict(device=pin['device'], pin=pin['pin'], address=pin.get('address', ''),
                             signal=pin.get('signal', ''), wire=wire['wire'],
                             destination=f"{wire[f'{other}_device']}:{wire[f'{other}_pin']}",
                             gauge=wire['gauge'], colour=wire['colour']))
    return rows


def export_panel(panel, output, name, plc_path=None):
    """Generate in isolation; failed rendering cannot replace a valid export."""
    import os
    import tempfile
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='panel-export-', dir=output.parent) as temp:
        staging = Path(temp)
        _write_panel(panel, staging, name, plc_path)
        output.mkdir(parents=True, exist_ok=True)
        for generated in staging.iterdir():
            os.replace(generated, output / generated.name)


def _write_panel(panel, output, name, plc_path=None):
    from .qet import write_qet
    from .drawings import write_drawings
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.worksheet.table import Table, TableStyleInfo
    errors = panel_errors(panel, plc_path)
    if errors:
        raise ValueError('\n'.join(errors))
    totals = bom(panel)
    schedule = terminal_schedule(panel)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    fields = ['item', 'description', 'quantity', 'unit']
    write_csv(output / f'{name}-bom.csv', totals, fields)
    write_csv(output / f'{name}-terminals.csv', schedule, list(schedule[0]))
    workbook = Workbook()
    workbook.remove(workbook.active)
    for title, rows, columns in [('BOM', totals, fields), ('Terminals', schedule, list(schedule[0]))]:
        sheet = workbook.create_sheet(title)
        sheet.append(columns)
        for row in rows:
            sheet.append([float(row[c]) if isinstance(row[c], Decimal) else row[c] for c in columns])
        sheet.freeze_panes = 'A2'
        sheet.print_title_rows = '1:1'
        sheet.page_setup.orientation = 'landscape'
        sheet.page_setup.paperSize = sheet.PAPERSIZE_A3
        sheet.page_setup.fitToWidth = 1
        sheet.page_setup.fitToHeight = 0
        sheet.sheet_properties.pageSetUpPr.fitToPage = True
        for row in sheet:
            for cell in row:
                if isinstance(cell.value, str):
                    cell.data_type = 's'  # Imported descriptions never become formulas.
        for cell in sheet[1]:
            cell.font = Font(bold=True, color='FFFFFF')
            cell.fill = PatternFill('solid', fgColor='183C4A')
        table = Table(displayName=title, ref=sheet.dimensions)
        table.tableStyleInfo = TableStyleInfo(name='TableStyleMedium2', showRowStripes=True)
        sheet.add_table(table)
        for column in sheet.columns:
            sheet.column_dimensions[column[0].column_letter].width = min(65, max(len(str(c.value or '')) for c in column) + 3)
    workbook.properties.creator = 'Jack Lai'
    workbook.properties.created = workbook.properties.modified = __import__('datetime').datetime(2026, 11, 6)
    workbook.save(output / f'{name}-bom.xlsx')
    write_qet(panel, output / f'{name}.qet', name)
    write_drawings(panel, output / f'{name}.dxf', output / f'{name}.pdf', name)
