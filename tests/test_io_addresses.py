"""The drawing schedule must have stable addresses in the ladder source."""
from pathlib import Path
import unittest
import tempfile
import xml.etree.ElementTree as ET

NS = {'p': 'http://www.plcopen.org/xml/tc6_0201'}


class AddressTests(unittest.TestCase):
    def test_named_inputs_and_external_outputs_have_unique_addresses(self):
        root = ET.parse(Path(__file__).resolve().parents[1] / 'plc/line.xml')
        inputs = root.findall('.//p:inputVars/p:variable', NS)
        outputs = root.findall('.//p:outputVars/p:variable', NS)
        expected = {v.get('name'): f'%IX{i // 8}.{i % 8}' for i, v in enumerate(inputs)}
        expected.update({name: f'%QX0.{i}' for i, name in enumerate(
            ('Run', 'Conveyor', 'Valve', 'Alarm', 'BatchDone', 'FillBlocked'))})
        actual = {v.get('name'): v.get('address') for v in inputs + outputs if v.get('name') != 'Filled'}
        self.assertEqual(actual, expected)
        self.assertEqual(len(set(actual.values())), 15)
        self.assertIsNone(root.find('.//p:localVars/p:variable[@name="Filled"]', NS).get('address'))

    def test_native_export_keeps_host_parameters_unlocated(self):
        from tools.openplc_export import export, ROOT
        st = export(ROOT / 'plc/line.xml')
        self.assertNotIn(' AT %', st)
        self.assertIn('Start : BOOL;', st)
        self.assertIn('FillBlocked : BOOL;', st)

    def test_native_export_preserves_explicit_local_locations(self):
        from tools.openplc_export import export, ROOT
        source = (ROOT / 'plc/line.xml').read_text().replace(
            '<variable name="Fault">', '<variable name="Fault" address="%MX0.0">')
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'located.xml'
            path.write_text(source)
            self.assertIn('Fault AT %MX0.0 : BOOL;', export(path))
