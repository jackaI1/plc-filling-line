"""Loopback Modbus TCP adapter for the existing compiled ladder and virtual plant.

Registers use zero-based protocol offsets. FUXA displays these as offset + 1.
No control decisions are reimplemented here; button writes queue Bench commands.
"""
import argparse
import json
import signal
import socketserver
import struct
import threading
import time

from .plant import Bench
from .controller import INPUTS, OUTPUTS, SCAN_MS

TAGS = (*INPUTS, *OUTPUTS, 'BatchCount', 'BottlePosition', 'BottleLevel')
COMMANDS = {100: 'start', 101: 'stop', 102: 'reset'}


class PlantRegisters:
    def __init__(self):
        self.bench = Bench()
        self.lock = threading.RLock()
        self.state = self.bench.snapshot()
        self.pending = []

    def tick(self):
        with self.lock:
            for command in self.pending:
                self.bench.command(command)
            self.pending.clear()
            self.state = self.bench.tick()
            return self.state

    def read(self, address, count):
        with self.lock:
            state = self.state
            values = [int(state['inputs'][name]) for name in INPUTS]
            values += [int(state['outputs'][name]) for name in OUTPUTS]
            values += [state['count'], round(state['plant']['position'] * 1000),
                       round(state['plant']['level'] * 1000)]
            if 100 <= address and address + count <= 104 and count > 0:
                commands = [0, 0, 0, int(self.bench.fill_sensor_stuck)]
                return commands[address - 100:address - 100 + count]
            if count < 1 or count > 125 or address < 0 or address + count > len(values):
                raise ValueError('Illegal data address')
            return values[address:address + count]

    def write(self, address, value):
        with self.lock:
            if value not in (0, 1) or address not in (*COMMANDS, 103):
                raise ValueError('Read-only, unknown or non-Boolean command')
            if len(self.pending) >= 100:
                raise ValueError('Command queue full')
            if address == 103:
                self.pending.append({'action': 'fault', 'name': 'fill_sensor_stuck', 'value': bool(value)})
            elif value:
                if address == 102 and self.state['outputs']['Run']:
                    raise ValueError('Stop before reset')
                self.pending.append({'action': COMMANDS[address]})

    def close(self):
        self.bench.close()


def receive(connection, size):
    data = bytearray()
    while len(data) < size:
        chunk = connection.recv(size - len(data))
        if not chunk:
            return None
        data.extend(chunk)
    return bytes(data)


class RequestHandler(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(1)
        try:
            while not self.server.stopping.is_set():
                header = receive(self.request, 7)
                if not header:
                    return
                transaction, protocol, length, unit = struct.unpack('>HHHB', header)
                if protocol != 0 or not 2 <= length <= 254:
                    return
                data = receive(self.request, length - 1)
                if not data:
                    return
                function = data[0]
                try:
                    if unit != 1:
                        raise ValueError('Unknown unit')
                    if function not in (3, 6):
                        response = bytes((function | 0x80, 1))
                    elif len(data) != 5:
                        response = bytes((function | 0x80, 3))
                    else:
                        address, number = struct.unpack('>HH', data[1:])
                        if function == 3:
                            values = self.server.plant.read(address, number)
                            response = bytes((3, len(values) * 2)) + struct.pack('>' + 'H' * len(values), *values)
                        else:
                            self.server.plant.write(address, number)
                            response = data
                except ValueError:
                    response = bytes((function | 0x80, 2))
                self.request.sendall(struct.pack('>HHHB', transaction, 0, len(response) + 1, unit) + response)
        except (TimeoutError, OSError):
            return


class ModbusServer:
    """Owns its accept thread and clients; caller owns and scans the plant."""
    def __init__(self, plant, port=1502):
        self.server = socketserver.ThreadingTCPServer(('127.0.0.1', port), RequestHandler)
        self.server.daemon_threads = False
        self.server.plant = plant
        self.server.stopping = threading.Event()
        self.address = self.server.server_address
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': .05})

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.server.stopping.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=1502)
    args = parser.parse_args()
    stopped = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stopped.set())
    signal.signal(signal.SIGINT, lambda *_: stopped.set())
    plant = PlantRegisters()
    try:
        with ModbusServer(plant, args.port) as server:
            print(json.dumps({'modbus': list(server.address), 'scan_ms': SCAN_MS}), flush=True)
            while not stopped.is_set():
                deadline = time.monotonic() + SCAN_MS / 1000
                plant.tick()
                stopped.wait(max(0, deadline - time.monotonic()))
    finally:
        plant.close()


if __name__ == '__main__':
    main()
