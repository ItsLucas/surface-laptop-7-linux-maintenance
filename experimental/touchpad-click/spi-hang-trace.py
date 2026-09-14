#!/usr/bin/python3
"""Isolated metadata-only SPI/IRQ trace, with local keyboard-controlled markers."""
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer
from collections import Counter
import json
import os
import re
import select
import signal
import subprocess
import threading
import time

ROOT = Path(__file__).resolve().parent
TRACE = Path('/sys/kernel/tracing')
DEVICE = Path('/sys/devices/platform/soc@0/8c0000.geniqup/88c000.spi')
STOP = threading.Event()
MARKS = []
LOCK = threading.Lock()
PAGE = '''<!doctype html><meta charset="utf-8"><title>触控板 SPI 卡住跟踪</title>
<style>body{font:22px system-ui;background:#edf2f6;color:#18232d;padding:35px}main{max-width:900px;margin:auto}#pad{padding:65px 25px;background:white;border:3px solid #4677a1;border-radius:18px;text-align:center;user-select:none;min-height:180px}b{color:#245881}#status{font-size:18px}button{font:inherit;margin:15px;padding:12px}</style>
<main><h1>触控板 SPI 卡住跟踪</h1><p>在白色区域按平常能复现问题的节奏连续物理点击。</p>
<p>卡住时按 <b>空格</b> 标记；恢复后按 <b>R</b>；完成后按 <b>Esc</b> 保存并结束。</p>
<div id="pad" tabindex="0">点击测试区域<br><span id="count">0</span> 次点击</div>
<button id="hang">标记卡住（空格）</button><button id="recover">标记恢复（R）</button><button id="finish">结束（Esc）</button>
<p id="status">已开始，最长记录 3 分钟。只保存传输状态、报告数量和时间，不保存键盘文字、坐标或热图。</p></main>
<script>let count=0;let done=false;const status=document.getElementById('status');
async function mark(type){if(done)return;try{const r=await fetch('/mark',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({type,epoch_ms:Date.now(),clicks:count})});if(!r.ok)throw Error();status.textContent=type==='hang'?'已标记卡住，请继续试着移动几秒；恢复后按 R。':type==='recovered'?'已标记恢复，可以继续复现；结束按 Esc。':'日志已保存，请返回聊天。';if(type==='finish')done=true;}catch(e){status.textContent='采样可能已经结束，请返回聊天。';}}
document.getElementById('pad').addEventListener('click',()=>{document.getElementById('count').textContent=++count;});
document.getElementById('hang').onclick=()=>mark('hang');document.getElementById('recover').onclick=()=>mark('recovered');document.getElementById('finish').onclick=()=>mark('finish');
document.addEventListener('keydown',e=>{if(e.repeat)return;if(e.code==='Space'){e.preventDefault();mark('hang');}else if(e.code==='KeyR'){e.preventDefault();mark('recovered');}else if(e.code==='Escape'){e.preventDefault();mark('finish');}});
document.getElementById('pad').focus();</script>'''


def read(path):
    try:
        return path.read_text().strip()
    except OSError as error:
        return type(error).__name__


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path != '/':
            self.send_error(404)
            return
        data = PAGE.encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if self.path != '/mark':
            self.send_error(404)
            return
        try:
            size = int(self.headers.get('Content-Length', '0'))
            assert 0 < size < 2048
            data = json.loads(self.rfile.read(size))
            assert data['type'] in ('hang', 'recovered', 'finish')
            with LOCK:
                MARKS.append({'type': data['type'], 'browser_epoch_ms': data['epoch_ms'],
                              'browser_clicks': data['clicks'], 'received_epoch_ms': time.time() * 1000})
            if data['type'] == 'finish':
                STOP.set()
        except (AssertionError, KeyError, TypeError, ValueError):
            self.send_error(400)
            return
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'ok')


def main():
    assert os.geteuid() == 0
    hidraw_nodes = [n for n in Path('/sys/class/hidraw').glob('hidraw*')
                    if (n / 'device').resolve().is_relative_to(DEVICE.resolve())]
    assert len(hidraw_nodes) == 1
    hid = hidraw_nodes[0]
    assert '0000045E:00000C77' in (hid / 'device/uevent').read_text()
    spi = next(p for p in (hid / 'device').resolve().parents if (p / 'bus_error_count').exists())
    bus, cs = map(int, spi.name.removeprefix('spi').split('.'))
    irqs = {}
    for line in Path('/proc/interrupts').read_text().splitlines():
        if line.split()[-1:] in ([spi.name], [DEVICE.name], ['gpi-dma']):
            irqs[int(line.split(':', 1)[0])] = line.split()[-1]
    pids = {}
    for node in Path('/proc').iterdir():
        if node.name.isdigit():
            comm = read(node / 'comm')
            if comm in ('iptsd', f'spi{bus}', *(f'irq/{irq}-{spi.name}' for irq in irqs)):
                pids[int(node.name)] = comm
    assert 'iptsd' in pids.values()
    out = ROOT / ('spi-trace-' + time.strftime('%H%M%S'))
    out.mkdir()
    instance = TRACE / 'instances' / ('sl7_spi_' + str(os.getpid()))
    instance.mkdir()
    enabled = []
    pipe = raw = None
    server = None
    try:
        (instance / 'tracing_on').write_text('0')
        (instance / 'buffer_size_kb').write_text('2048')
        (instance / 'trace_clock').write_text('mono')
        def event(group, name, condition):
            directory = instance / 'events' / group / name
            (directory / 'filter').write_text(condition)
            (directory / 'enable').write_text('1')
            enabled.append({'event': group + '/' + name, 'filter': condition})
        for name in ['spi_message_submit', 'spi_message_start', 'spi_message_done']:
            event('spi', name, f'bus_num == {bus} && chip_select == {cs}')
        for name in ['spi_controller_busy', 'spi_controller_idle']:
            event('spi', name, f'bus_num == {bus}')
        for name in ['geni_spi_transfer', 'geni_spi_irq', 'geni_spi_clk_cfg', 'geni_spi_setup_params']:
            event('qcom_geni_spi', name, f'name == "{DEVICE.name}"')
        for name in ['rpm_suspend', 'rpm_resume', 'rpm_idle', 'rpm_return_int']:
            event('rpm', name, f'name == "{DEVICE.name}"')
        for name in ['irq_handler_entry', 'irq_handler_exit']:
            event('irq', name, ' || '.join(f'irq == {irq}' for irq in irqs))
        event('sched', 'sched_switch', ' || '.join(f'prev_pid == {pid} || next_pid == {pid}' for pid in pids))
        event('sched', 'sched_waking', ' || '.join(f'pid == {pid}' for pid in pids))
        pipe = os.open(instance / 'trace_pipe', os.O_RDONLY | os.O_NONBLOCK)
        raw = os.open('/dev/' + hid.name, os.O_RDONLY | os.O_NONBLOCK)
        meta = {'start_epoch_ms': time.time() * 1000, 'start_monotonic': time.monotonic(),
                'irqs': irqs, 'pids': pids, 'hidraw': hid.name, 'spi': spi.name,
                'trace_instance': str(instance), 'events': enabled,
                'spi_payload_tracepoints_disabled': True, 'driver_and_power_settings_changed': False}
        (out / 'metadata.json').write_text(json.dumps(meta, indent=2) + '\n')
        server = HTTPServer(('127.0.0.1', 8767), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        (instance / 'tracing_on').write_text('1')
        signal.signal(signal.SIGTERM, lambda *_: STOP.set())
        signal.signal(signal.SIGINT, lambda *_: STOP.set())
        end = time.monotonic() + 180
        next_sample = time.monotonic()
        reports = Counter()
        total = 0
        def snapshot(label):
            data = {'type': label, 'epoch_ms': time.time() * 1000, 'monotonic': time.monotonic(),
                    'packet_ids_since_sample': dict(reports), 'total_packets': total,
                    'runtime': read(DEVICE / 'power/runtime_status'),
                    'runtime_control': read(DEVICE / 'power/control'),
                    'device': {name: read(spi / name) for name in ['ready', 'bus_error_count', 'device_initiated_reset_count']},
                    'threads': {str(pid): {'comm': comm, 'stack': read(Path('/proc', str(pid), 'stack'))}
                                for pid, comm in pids.items()}}
            data['irqs'] = [l.strip() for l in Path('/proc/interrupts').read_text().splitlines()
                            if l.split(':', 1)[0].strip() in [str(i) for i in irqs]]
            chip = read(Path('/sys/kernel/debug/gpio')).split('\n\n', 1)[0]
            data['touchpad_gpio'] = [l.strip() for l in chip.splitlines()
                                     if re.match(r'\s*gpio(?:3|65|120)\s*:', l)]
            return data
        print('SPI_TRACE_READY', str(out), 'http://127.0.0.1:8767/', flush=True)
        with (out / 'trace.txt').open('wb') as trace, (out / 'health.jsonl').open('w') as health:
            while not STOP.is_set() and time.monotonic() < end:
                ready, _, _ = select.select([pipe, raw], [], [], .05)
                if pipe in ready:
                    try:
                        trace.write(os.read(pipe, 262144)); trace.flush()
                    except BlockingIOError:
                        pass
                if raw in ready:
                    packet = os.read(raw, 65536)
                    if packet:
                        reports[f'{packet[0]:02x}'] += 1; total += 1
                with LOCK:
                    marks = MARKS[:]; MARKS.clear()
                for mark in marks:
                    (instance / 'trace_marker').write_text(mark['type'])
                    data = snapshot('user_marker'); data['marker'] = mark
                    health.write(json.dumps(data) + '\n'); health.flush()
                    print('USER_MARKER', mark['type'], str(out), flush=True)
                if time.monotonic() >= next_sample:
                    health.write(json.dumps(snapshot('sample')) + '\n'); health.flush()
                    reports.clear(); next_sample = time.monotonic() + .5
            (instance / 'tracing_on').write_text('0')
            while True:
                try:
                    block = os.read(pipe, 262144)
                    if not block: break
                    trace.write(block)
                except BlockingIOError:
                    break
            health.write(json.dumps(snapshot('finished')) + '\n')
        stats = {str(p.relative_to(instance)): read(p) for p in (instance / 'per_cpu').glob('cpu*/stats')}
        (out / 'trace-buffer-stats.json').write_text(json.dumps(stats, indent=2) + '\n')
    finally:
        if server:
            server.shutdown(); server.server_close()
        (instance / 'tracing_on').write_text('0')
        (instance / 'events/enable').write_text('0')
        for fd in [pipe, raw]:
            if fd is not None: os.close(fd)
        instance.rmdir()
        owner = ROOT.stat()
        for p in [out, *out.iterdir()]: os.chown(p, owner.st_uid, owner.st_gid)
    print('SPI_TRACE_FINISHED', str(out), flush=True)


if __name__ == '__main__':
    main()
