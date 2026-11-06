"""Connection-list and drawing regressions use the published example inputs."""
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

from wiring.project import load_panel, bom, check_addresses, export_panel

ROOT = Path(__file__).resolve().parents[1]


class PanelExportsTests(unittest.TestCase):
    def test_cockpit_parts_and_wire_totals(self):
        panel = load_panel(ROOT / 'examples/cockpit')
        rows = {r['item']: r for r in bom(panel)}
        self.assertEqual(rows['SW-TOGGLE']['quantity'], Decimal('3'))
        self.assertEqual(rows['LED-24']['quantity'], Decimal('3'))
        self.assertEqual(rows['WIRE:18 AWG:red']['quantity'], Decimal('2.4'))
        self.assertEqual(rows['WIRE:18 AWG:black']['quantity'], Decimal('2.4'))
        self.assertEqual(rows['J-6']['quantity'], Decimal('1'))

    def test_every_located_plc_point_has_one_terminal(self):
        panel = load_panel(ROOT / 'examples/filling-line')
        self.assertEqual(check_addresses(panel, ROOT / 'plc/line.xml'), [])
        located = [p for p in panel['pins'] if p['address']]
        self.assertEqual(len(located), 15)
        self.assertEqual(len({p['address'] for p in located}), 15)

    def test_missing_duplicate_and_wrong_address_are_rejected(self):
        panel = load_panel(ROOT / 'examples/filling-line')
        pins = [p for p in panel['pins'] if p['address']]
        pins[0]['address'] = pins[1]['address']
        errors = check_addresses(panel, ROOT / 'plc/line.xml')
        self.assertTrue(any('missing PLC address' in e for e in errors))
        self.assertTrue(any('duplicate PLC address' in e for e in errors))
        pins[0]['address'] = '%IX9.9'
        self.assertTrue(any('unknown PLC address' in e for e in check_addresses(panel, ROOT / 'plc/line.xml')))

    def test_duplicate_address_in_source_is_rejected(self):
        panel = load_panel(ROOT / 'examples/filling-line')
        tree = ET.parse(ROOT / 'plc/line.xml')
        variables = [v for v in tree.getroot().iter() if 'address' in v.attrib]
        variables[1].set('address', variables[0].get('address'))
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'duplicate.xml'
            tree.write(path)
            self.assertTrue(any('duplicate PLC source address' in e for e in check_addresses(panel, path)))

    def test_address_check_also_rejects_unconnected_non_plc_pins(self):
        panel = load_panel(ROOT / 'examples/filling-line')
        panel['pins'].append(dict(device='J0', pin='spare', address='', signal=''))
        self.assertTrue(any('unconnected pin' in e for e in check_addresses(panel, ROOT / 'plc/line.xml')))

    def test_rejects_bad_lengths_and_mismatched_part_descriptions(self):
        panel = load_panel(ROOT / 'examples/cockpit')
        panel['wires'][0]['length_m'] = '-1'
        with self.assertRaisesRegex(ValueError, 'length'):
            bom(panel)
        panel = load_panel(ROOT / 'examples/cockpit')
        panel['devices'][1]['description'] = 'different part'
        with self.assertRaisesRegex(ValueError, 'inconsistent'):
            bom(panel)

    def test_qet_has_real_connected_terminals_and_spreadsheet_totals(self):
        from openpyxl import load_workbook
        import ezdxf
        panel = load_panel(ROOT / 'examples/filling-line')
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            export_panel(panel, output, 'line', ROOT / 'plc/line.xml')
            qet = ET.parse(output / 'line.qet').getroot()
            self.assertEqual(qet.tag, 'project')
            terminals = {t.attrib['id'] for t in qet.findall('./diagram/elements/element/terminals/terminal')}
            conductors = qet.findall('./diagram/conductors/conductor')
            self.assertEqual(len(conductors), len(panel['wires']))
            for wire in conductors:
                self.assertIn(wire.attrib['terminal1'], terminals)
                self.assertIn(wire.attrib['terminal2'], terminals)
                self.assertTrue(wire.attrib['num'])
            definitions = qet.findall('./collection/category/element/definition')
            self.assertTrue(definitions)
            self.assertEqual(qet.get('version'), '0.90')
            labels = qet.findall('./diagram/elements/element/dynamic_texts/dynamic_elmt_text/text')
            self.assertEqual(len(labels), len(panel['wires'])*2)
            self.assertTrue(all(label.text for label in labels))
            workbook = load_workbook(output / 'line-bom.xlsx', data_only=True)
            self.assertEqual(workbook['BOM'].max_row - 1, len(bom(panel)))
            actual = {r[0]: (Decimal(str(r[2])), r[3]) for r in workbook['BOM'].iter_rows(min_row=2, values_only=True)}
            self.assertEqual(actual, {r['item']: (r['quantity'], r['unit']) for r in bom(panel)})
            self.assertEqual(actual['PLC-24'], (Decimal('1'), 'each'))
            self.assertEqual(actual['TB-2'], (Decimal('15'), 'each'))
            self.assertEqual(actual['WIRE:18 AWG:blue'], (Decimal('12'), 'm'))
            self.assertEqual(actual['WIRE:18 AWG:red'], (Decimal('6.4'), 'm'))
            self.assertEqual(actual['WIRE:18 AWG:black'], (Decimal('4.35'), 'm'))
            workbook.close()
            self.assertTrue((output / 'line.pdf').read_bytes().startswith(b'%PDF'))
            dxf = ezdxf.readfile(output / 'line.dxf')
            self.assertFalse(dxf.audit().has_errors)
            self.assertEqual(set(dxf.layout_names()), {'Model', 'Power', 'IO', 'Terminals', 'Terminals2', 'Layout', 'BOM'})
            self.assertTrue(any('CONTROL PANEL LAYOUT' in e.dxf.text for e in dxf.layouts.get('Layout').query('TEXT')))
            self.assertGreater((output / 'line.pdf').stat().st_size, 1000)

    def test_untrusted_csv_strings_remain_literal_in_excel(self):
        from openpyxl import load_workbook
        from wiring.validate import read_csv
        panel = load_panel(ROOT / 'examples/cockpit')
        for device in panel['devices']:
            if device['part'] == 'SW-TOGGLE':
                device['description'] = '=1+2'
        with tempfile.TemporaryDirectory() as temp:
            export_panel(panel, Path(temp), 'literal')
            book = load_workbook(Path(temp) / 'literal-bom.xlsx', data_only=False)
            values = [cell for row in book['BOM'] for cell in row if cell.value == '=1+2']
            self.assertEqual(len(values), 1)
            self.assertEqual(values[0].data_type, 's')
            book.close()
            rows = read_csv(Path(temp) / 'literal-bom.csv')
            self.assertEqual(next(r['description'] for r in rows if r['item']=='SW-TOGGLE'), "'=1+2")

    def test_empty_panel_rejected_before_output(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, 'empty'):
                export_panel(dict(devices=[], pins=[], wires=[]), Path(temp), 'empty')
            self.assertEqual(list(Path(temp).iterdir()), [])

    def test_check_mode_rejects_bad_length_and_missing_bom_schema(self):
        import subprocess
        import sys
        import shutil
        with tempfile.TemporaryDirectory() as temp:
            panel_dir = Path(temp) / 'panel'
            shutil.copytree(ROOT / 'examples/cockpit', panel_dir)
            path = panel_dir / 'connections.csv'
            path.write_text(path.read_text().replace(',red,.4,', ',red,-1,'))
            result = subprocess.run([sys.executable, '-m', 'wiring', str(panel_dir), '--check'],
                                    cwd=ROOT, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('length', result.stderr)
            shutil.copyfile(ROOT / 'examples/cockpit/connections.csv', path)
            path = panel_dir / 'devices.csv'
            path.write_text(path.read_text().replace('part,', 'missing-part,'))
            result = subprocess.run([sys.executable, '-m', 'wiring', str(panel_dir), '--check'],
                                    cwd=ROOT, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('part', result.stderr)

    def test_bad_layout_leaves_published_outputs_untouched(self):
        panel = load_panel(ROOT / 'examples/cockpit')
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            sentinel = output / 'bad-bom.csv'
            sentinel.write_text('previous valid export')
            panel['devices'][0]['x_mm'] = 'bad'
            with self.assertRaises(ValueError):
                export_panel(panel, output, 'bad')
            self.assertEqual(sentinel.read_text(), 'previous valid export')
            self.assertEqual(len(list(output.iterdir())), 1)

    def test_invalid_input_does_not_publish_partial_outputs(self):
        panel = load_panel(ROOT / 'examples/cockpit')
        panel['wires'].append(deepcopy(panel['wires'][0]))
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, 'duplicate'):
                export_panel(panel, Path(temp), 'bad')
            self.assertEqual(list(Path(temp).iterdir()), [])
