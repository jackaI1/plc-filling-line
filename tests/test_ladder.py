from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

from tools.ladder import compile_ld, NS, ROOT


class LadderTests(unittest.TestCase):
    def test_generated_st_matches_source(self):
        from tools.openplc_export import export
        self.assertEqual(export(ROOT / "plc/line.xml"), (ROOT / "plc/line.st").read_text())

    def mutate(self, callback):
        tree = ET.parse(ROOT / "plc/line.xml")
        callback(tree)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.xml"
            tree.write(path)
            with self.assertRaises(ValueError):
                compile_ld(path)

    def test_unknown_ladder_element_fails_closed(self):
        self.mutate(lambda t: ET.SubElement(t.find('.//p:LD', NS), '{'+NS['p']+'}jump', localId='999'))

    def test_dangling_connection_fails_closed(self):
        self.mutate(lambda t: t.find('.//p:connection', NS).set('refLocalId', '99999'))

    def test_duplicate_execution_order_fails_closed(self):
        self.mutate(lambda t: t.find('.//p:coil', NS).set('executionOrderId', '1'))

    def test_cyclic_contact_fails_closed(self):
        def cycle(tree):
            node = tree.find('.//p:contact', NS)
            node.find('.//p:connection', NS).set('refLocalId', node.get('localId'))
        self.mutate(cycle)
