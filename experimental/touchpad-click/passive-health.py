#!/usr/bin/python3
"""Count SL7 HID packets, IRQs and runtime states without changing the device."""
from pathlib import Path
from collections import Counter
import argparse
import json
import os
import select
import time


def read_text(path):
    try:
        return path.read_text().strip()
    except OSError as error:
        return type(error).__name__


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=int, default=60)
    args = parser.parse_args()
    assert 1 <= args.seconds <= 600
    devices = []
    for node in Path('/sys/class/hidraw').glob('hidraw*'):
        data = dict(s.split('=', 1) for s in (node / 'device/uevent').read_text().splitlines())
        if data.get('HID_ID', '').split(':')[1:] == ['0000045E', '00000C77']:
            devices.append(node)
    assert len(devices) == 1
    node = devices[0]
    ancestors = list((node / 'device').resolve().parents)
    spi = next(p for p in ancestors if (p / 'bus_error_count').exists())
    states = [p / 'power/runtime_status' for p in ancestors if (p / 'power/runtime_status').exists()]
    output = Path(__file__).resolve().parent / ('passive-health-' + time.strftime('%H%M%S') + '.jsonl')
    fd = os.open('/dev/' + node.name, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
    end = time.monotonic() + args.seconds
    next_sample = time.monotonic() + 1
    reports = Counter()
    total = 0
    with output.open('w') as log:
        log.write(json.dumps({'started_epoch_ms': time.time() * 1000,
                              'device': node.name, 'spi': str(spi),
                              'read_only': True, 'payloads_and_coordinates_saved': False}) + '\n')
        log.flush()
        print('PASSIVE_HEALTH_READY', str(output), flush=True)
        try:
            while time.monotonic() < end:
                ready, _, _ = select.select([fd], [], [], min(.1, max(0, next_sample - time.monotonic())))
                if ready:
                    packet = os.read(fd, 65536)
                    if packet:
                        reports[f'{packet[0]:02x}'] += 1
                        total += 1
                    else:
                        break
                if time.monotonic() < next_sample:
                    continue
                irq = None
                for line in Path('/proc/interrupts').read_text().splitlines():
                    if line.split()[-1:] == [spi.name]:
                        irq = sum(int(x) for x in line.split(':', 1)[1].split()[:os.cpu_count()])
                        break
                sample = {'epoch_ms': time.time() * 1000, 'packets_by_report_id': dict(reports),
                          'total_packets': total, 'irq_count': irq,
                          'runtime': {str(p.parent.parent): read_text(p) for p in states}}
                for name in ['ready', 'bus_error_count', 'device_initiated_reset_count']:
                    sample[name] = read_text(spi / name)
                log.write(json.dumps(sample) + '\n')
                log.flush()
                reports.clear()
                next_sample = time.monotonic() + 1
        finally:
            os.close(fd)
            log.write(json.dumps({'finished_epoch_ms': time.time() * 1000, 'total_packets': total}) + '\n')
    owner = Path(__file__).resolve().parent.stat()
    os.chown(output, owner.st_uid, owner.st_gid)
    print('PASSIVE_HEALTH_FINISHED', str(output), 'packets', total, flush=True)


if __name__ == '__main__':
    main()
