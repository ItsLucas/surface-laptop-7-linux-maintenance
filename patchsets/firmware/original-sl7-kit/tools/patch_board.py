#!/usr/bin/env python3
"""Add the community SL7 board-name alias, preserving every existing TLV."""
import argparse
import hashlib
from pathlib import Path
import struct

SOURCE = b'bus=pci,vendor=17cb,device=1107,subsystem-vendor=17cb,subsystem-device=3378,qmi-chip-id=2,qmi-board-id=255'
TARGET = SOURCE.replace(b'subsystem-device=3378', b'subsystem-device=1107')

def entries(data):
    pos = 0
    while pos < len(data):
        if pos + 8 > len(data):
            raise ValueError('Truncated TLV header')
        kind, size = struct.unpack_from('<II', data, pos)
        end = pos + 8 + size
        aligned = (end + 3) & ~3
        if aligned > len(data):
            raise ValueError('Truncated TLV data')
        yield kind, data[pos + 8:end], data[pos:aligned]
        pos = aligned

def board_map(data):
    magic = b'QCA-ATH12K-BOARD\0'
    if not data.startswith(magic):
        raise ValueError('Not an ath12k board container')
    result = {}
    for kind, payload, _ in entries(data[20:]):
        if kind != 0:
            continue
        nested = list(entries(payload))
        values = [p for k, p, _ in nested if k == 1]
        if len(values) != 1:
            raise ValueError('Unexpected board data count')
        for k, name, _ in nested:
            if k == 0:
                if name in result:
                    raise ValueError('Duplicate board name')
                result[name] = values[0]
    return result

def patch(data):
    old = board_map(data)
    if TARGET in old:
        return data
    if SOURCE not in old:
        raise ValueError('Required 3378/255 source entry is absent; refusing to guess')
    alias = struct.pack('<II', 0, len(TARGET)) + TARGET
    alias += b'\0' * (-len(TARGET) % 4)
    chunks = [data[:20]]
    changes = 0
    for kind, payload, raw in entries(data[20:]):
        if kind == 0 and any(k == 0 and p == SOURCE for k, p, _ in entries(payload)):
            updated = alias + payload
            chunks.append(struct.pack('<II', kind, len(updated)) + updated)
            changes += 1
        else:
            chunks.append(raw)
    if changes != 1:
        raise ValueError('Expected exactly one matching board')
    result = b''.join(chunks)
    new = board_map(result)
    if {k: v for k, v in new.items() if k != TARGET} != old or new[TARGET] != old[SOURCE]:
        raise ValueError('Payload preservation check failed')
    return result

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('input', type=Path)
    p.add_argument('output', type=Path, nargs='?')
    args = p.parse_args()
    data = args.input.read_bytes()
    boards = board_map(data)
    print('Board names:', len(boards), 'source present:', SOURCE in boards, 'SL7 target present:', TARGET in boards)
    if args.output:
        result = patch(data)
        with args.output.open('xb') as f:
            f.write(result)
        print('SHA256:', hashlib.sha256(result).hexdigest())

if __name__ == '__main__':
    main()
