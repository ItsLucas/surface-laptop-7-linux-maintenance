#!/usr/bin/python3
"""Summarize SPI transaction completion and snapshots around explicit user marks."""
from pathlib import Path
from collections import Counter
import json
import re
import sys


def main():
    root = Path(sys.argv[1])
    metadata = json.loads((root / 'metadata.json').read_text())
    health = [json.loads(line) for line in (root / 'health.jsonl').read_text().splitlines()]
    pending = {}
    counts = Counter()
    latencies = []
    anomalies = []
    transactions = []
    pattern = re.compile(r'\s(\d+\.\d+): (\w+): (.*)')
    pointer = re.compile(r'spi\d+\.\d+ ([0-9a-f]+)')
    last_timestamp = 0
    with (root / 'trace.txt').open() as file:
        for line in file:
            match = pattern.search(line)
            if not match:
                continue
            timestamp, event, text = match.groups()
            timestamp = float(timestamp)
            last_timestamp = max(last_timestamp, timestamp)
            counts[event] += 1
            if event.startswith('spi_message_'):
                pm = pointer.search(text)
                if not pm:
                    continue
                address = pm[1]
                if event == 'spi_message_submit':
                    if address in pending:
                        anomalies.append({'event': 'resubmitted_before_done', 'at': timestamp,
                                          'previous': pending[address]})
                    pending[address] = {'submit': timestamp}
                elif event == 'spi_message_start':
                    pending.setdefault(address, {})['start'] = timestamp
                elif event == 'spi_message_done':
                    transaction = pending.pop(address, {})
                    transaction.update({'done': timestamp, 'length': text.split('len=')[-1]})
                    if 'submit' in transaction:
                        transaction['duration_ms'] = (timestamp - transaction['submit']) * 1000
                        latencies.append(transaction['duration_ms'])
                    transactions.append(transaction)
    latencies.sort()
    marks = []
    for sample in health:
        if sample.get('type') != 'user_marker':
            continue
        before = [t for t in transactions if t['done'] <= sample['monotonic']]
        after = [t for t in transactions if t.get('submit', t['done']) > sample['monotonic']]
        marks.append({'marker': sample['marker'], 'monotonic': sample['monotonic'],
                      'last_completed_transaction': before[-1] if before else None,
                      'next_transaction': after[0] if after else None,
                      'snapshot': sample})
    durations = {'count': len(latencies)}
    if latencies:
        durations.update({'median_ms': latencies[len(latencies)//2],
                          'p99_ms': latencies[min(len(latencies)-1, int(len(latencies)*.99))],
                          'max_ms': max(latencies), 'over_10ms': sum(x>10 for x in latencies)})
    result = {'trace_directory': str(root), 'events': dict(counts),
              'latencies': durations, 'pending_at_trace_end': pending,
              'ordering_anomalies': anomalies[:20], 'user_markers': marks,
              'trace_start_monotonic': metadata['start_monotonic'],
              'trace_last_event_monotonic': last_timestamp,
              'capture_finished': health[-1].get('type') == 'finished'}
    (root / 'analysis.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
