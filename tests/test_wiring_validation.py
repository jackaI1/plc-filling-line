import unittest
from wiring.validate import validate


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.devices = [{'device': 'J1', 'capacity': '1'}, {'device': 'S1', 'capacity': '2'}]
        self.pins = [{'device': 'J1', 'pin': '1'}, {'device': 'S1', 'pin': '1'}]
        self.wires = [{'wire': '101', 'from_device': 'J1', 'from_pin': '1',
                       'to_device': 'S1', 'to_pin': '1', 'gauge': '18 AWG', 'colour': 'red'}]

    def test_valid(self):
        self.assertEqual(validate(self.devices, self.pins, self.wires), [])

    def test_duplicate_terminal(self):
        self.wires.append(dict(self.wires[0], wire='102'))
        self.assertTrue(any('duplicate terminal' in e for e in validate(self.devices, self.pins, self.wires)))

    def test_unconnected_pin(self):
        self.pins.append({'device': 'S1', 'pin': '2'})
        self.assertTrue(any('unconnected pin' in e for e in validate(self.devices, self.pins, self.wires)))

    def test_overloaded_connector(self):
        self.devices[0]['capacity'] = '0'
        self.assertTrue(any('overloaded connector' in e for e in validate(self.devices, self.pins, self.wires)))

    def test_missing_and_empty_inventory_is_rejected(self):
        self.assertTrue(any('empty' in e for e in validate([], [], [])))
        self.devices[0]['capacity'] = None
        self.assertTrue(any('capacity' in e for e in validate(self.devices, self.pins, self.wires)))

    def test_missing_csv_cell_is_rejected(self):
        self.wires[0]['from_pin'] = None
        self.assertTrue(any('missing' in e for e in validate(self.devices, self.pins, self.wires)))
