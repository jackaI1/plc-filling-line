"""Validate a panel connection list against its device and pin inventory.

Each connection joins two pins. Pins may have only one wire; use an explicit
junction device where a circuit branches. Connector capacity is the maximum
number of simultaneously occupied pins, not an electrical current rating.
"""
import csv
from collections import Counter
from pathlib import Path


def read_csv(path):
    with Path(path).open(newline='', encoding='utf-8-sig') as stream:
        return list(csv.DictReader(stream))


def validate(devices, pins, wires):
    errors = []
    for name, rows, required in [
        ('devices', devices, ('device', 'capacity')),
        ('pins', pins, ('device', 'pin')),
        ('connections', wires, ('wire', 'from_device', 'from_pin', 'to_device', 'to_pin', 'gauge', 'colour')),
    ]:
        if not rows:
            errors.append(f'empty {name} inventory')
        for number, row in enumerate(rows, 2):
            for field in required:
                value = row.get(field)
                if not isinstance(value, str) or not value.strip():
                    errors.append(f'missing {name} value: row {number} {field}')
    if errors:
        return errors
    ids = [d['device'] for d in devices]
    for device, count in Counter(ids).items():
        if not device or count != 1:
            errors.append(f'duplicate or empty device: {device}')
    inventory = [(p['device'], p['pin']) for p in pins]
    for pin, count in Counter(inventory).items():
        if not all(pin) or count != 1:
            errors.append(f'duplicate or empty inventory pin: {pin}')
        if pin[0] not in ids:
            errors.append(f'unknown device in inventory: {pin[0]}')
    known = set(inventory)
    used = Counter()
    wire_ids = Counter()
    for wire in wires:
        wire_ids[wire['wire']] += 1
        endpoints = [(wire['from_device'], wire['from_pin']),
                     (wire['to_device'], wire['to_pin'])]
        if endpoints[0] == endpoints[1]:
            errors.append(f"wire {wire['wire']} connects a pin to itself")
        if not wire['gauge'] or not wire['colour']:
            errors.append(f"wire {wire['wire']} needs gauge and colour")
        for endpoint in endpoints:
            used[endpoint] += 1
            if endpoint not in known:
                errors.append(f'unknown terminal: {endpoint}')
    for number, count in wire_ids.items():
        if not number or count != 1:
            errors.append(f'duplicate or empty wire number: {number}')
    for pin, count in used.items():
        if count > 1:
            errors.append(f'duplicate terminal: {pin}')
    for pin in inventory:
        if not used[pin]:
            errors.append(f'unconnected pin: {pin}')
    for device in devices:
        try:
            capacity = int(device['capacity'])
            if capacity < 0:
                raise ValueError
        except (ValueError, TypeError):
            errors.append(f"invalid capacity: {device['device']}")
            continue
        occupied = sum(1 for (name, _), count in used.items()
                       if name == device['device'] and count and (name, _) in known)
        if occupied > capacity:
            errors.append(f"overloaded connector: {device['device']} ({occupied}/{capacity})")
    return errors
