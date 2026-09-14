#!/usr/bin/python3
"""Revert only this trial's exact volatile service override."""
from pathlib import Path
import json
import subprocess

ROOT = Path('/run/sl7-iptsd-click-test')


def main():
    state = json.loads((ROOT / 'state.json').read_text())
    override = Path(state['override'])
    if override.exists():
        if override.read_text() != state['override_text']:
            raise RuntimeError('Trial override changed; refusing to remove another configuration')
        override.unlink()
        subprocess.run(['systemctl', 'daemon-reload'], check=True)
        subprocess.run(['systemctl', 'restart', state['service']], check=True)
    subprocess.run(['systemctl', 'stop', 'sl7-iptsd-click-rollback.timer'], check=False)
    state['restored'] = True
    (ROOT / 'state.json').write_text(json.dumps(state, indent=2) + '\n')
    print('Restored packaged iptsd; trial did not change calibration, tapping or boot settings.')


if __name__ == '__main__':
    main()
