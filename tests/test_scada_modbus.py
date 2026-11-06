"""Exercise the wire protocol against the compiled PLC, without a fake controller."""
import socket
import struct
import time
import unittest

from fillingline.modbus import PlantRegisters, ModbusServer


class ModbusTests(unittest.TestCase):
    def setUp(self):
        self.plant = PlantRegisters()

    def tearDown(self):
        self.plant.close()

    def test_fillblocked_refuses_reset_until_sensor_released(self):
        self.plant.write(103, 1)  # simulation fault switch
        self.plant.write(100, 1)  # Start pulse
        for _ in range(65):
            self.plant.tick()
        self.assertEqual(self.plant.read(15, 1), [1])  # FillBlocked
        self.assertEqual(self.plant.read(10, 2), [0, 0])  # Conveyor, Valve
        self.plant.write(102, 1)
        self.plant.tick()
        self.assertEqual(self.plant.read(15, 1), [1])
        self.plant.write(103, 0)
        self.plant.write(102, 1)
        self.plant.tick()
        self.assertEqual(self.plant.read(9, 1), [0])
        self.assertEqual(self.plant.read(15, 1), [0])

    def test_five_bottles_reach_count_register(self):
        self.plant.write(100, 1)
        for _ in range(500):
            self.plant.tick()
        self.assertEqual(self.plant.read(16, 1), [5])
        self.assertEqual(self.plant.read(13, 1), [1])

    def test_readonly_unknown_and_invalid_commands_rejected(self):
        for address, value in [(0, 1), (99, 1), (100, 2)]:
            with self.assertRaises(ValueError):
                self.plant.write(address, value)
        with self.assertRaises(ValueError):
            self.plant.read(19, 1)

    def test_tcp_framing_split_packets_and_exception_response(self):
        with ModbusServer(self.plant, port=0) as server:
            with socket.create_connection(server.address, timeout=2) as client:
                frame = struct.pack('>HHHBBHH', 42, 0, 6, 1, 3, 0, 3)
                client.sendall(frame[:4])
                client.sendall(frame[4:])
                result = client.recv(100)
                self.assertEqual(result[:9], struct.pack('>HHHBBB', 42, 0, 9, 1, 3, 6))
                self.assertEqual(struct.unpack('>3H', result[9:]), (0, 0, 0))
                client.sendall(struct.pack('>HHHBBHH', 43, 0, 6, 1, 6, 0, 1))
                self.assertEqual(client.recv(100), struct.pack('>HHHBBB', 43, 0, 3, 1, 0x86, 2))
            port = server.address[1]
        with socket.socket() as probe:
            self.assertNotEqual(probe.connect_ex(('127.0.0.1', port)), 0)

    def test_exit_closes_active_persistent_client(self):
        start = time.monotonic()
        server = ModbusServer(self.plant, port=0)
        server.__enter__()
        try:
            with socket.create_connection(server.address, timeout=2) as client:
                request = struct.pack('>HHHBBHH', 1, 0, 6, 1, 3, 0, 1)
                client.sendall(request)
                self.assertTrue(client.recv(100))
                server.__exit__()
                self.assertEqual(client.recv(100), b'')
                self.assertLess(time.monotonic() - start, 2)
        finally:
            server.__exit__()
