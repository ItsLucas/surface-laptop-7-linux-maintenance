#!/usr/bin/python3
"""Local-only single-page click counter, with constrained diagnostic JSON storage."""
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import json
import re
import threading

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / 'click-test-results'
OUTPUT.mkdir(exist_ok=True)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path != '/':
            self.send_error(404)
            return
        data = (ROOT / 'click-test.html').read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if self.path not in ('/save', '/finish'):
            self.send_error(404)
            return
        length = int(self.headers.get('Content-Length', '0'))
        if not 0 < length <= 262144:
            self.send_error(400)
            return
        try:
            data = json.loads(self.rfile.read(length))
            session = data['session']
            assert isinstance(session, str) and re.fullmatch(r'\d{10,16}', session)
            assert isinstance(data['events'], list) and len(data['events']) < 2000
            assert all(e['type'] in ('pointerdown', 'pointerup', 'click', 'dblclick') for e in data['events'])
            file = OUTPUT / (session + '.json')
            old = json.loads(file.read_text()) if file.exists() else {'sequence': -1}
            if data['sequence'] >= old['sequence']:
                file.write_text(json.dumps(data, indent=2) + '\n')
        except (KeyError, ValueError, TypeError, AssertionError):
            self.send_error(400)
            return
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'saved')
        if self.path == '/finish':
            threading.Thread(target=self.server.shutdown, daemon=True).start()


server = HTTPServer(('127.0.0.1', 8766), Handler)
timer = threading.Timer(600, server.shutdown)
timer.daemon = True
timer.start()
print('Click test: http://127.0.0.1:8766/', flush=True)
try:
    server.serve_forever()
finally:
    timer.cancel()
    server.server_close()
