#!/usr/bin/python3
"""Read-only preflight by default. --apply requires explicit user approval."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
RUNTIME = Path('/run/sl7-iptsd-click-test')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(*args):
    return subprocess.run(args, check=True, text=True, capture_output=True).stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    review = json.loads((ROOT / 'candidate-review.json').read_text())
    candidate = ROOT / 'build/src/iptsd'
    calibration = Path('/etc/iptsd.d/91-calibration-045E-0C77.conf')
    assert sha(candidate) == review['candidate_binary_sha256']
    assert sha(Path('/usr/bin/iptsd')) == review['installed_binary_sha256']
    assert sha(calibration) == review['calibration_sha256']
    assert run('dpkg-query', '-W', '-f=${Version}', 'iptsd') == review['installed_version']
    candidates = []
    for node in Path('/sys/class/hidraw').glob('hidraw*'):
        entries = dict(line.split('=', 1) for line in (node / 'device/uevent').read_text().splitlines())
        if entries.get('HID_ID', '').split(':')[1:] != ['0000045E', '00000C77']:
            continue
        service = 'iptsd@dev-' + node.name + '.service'
        if run('systemctl', 'is-active', service) == 'active':
            candidates.append((node.name, service))
    assert len(candidates) == 1, candidates
    hidraw, service = candidates[0]
    assert '/usr/bin/iptsd ' in run('systemctl', 'show', service, '-p', 'ExecStart', '--value')
    override = Path('/run/systemd/system') / (service + '.d') / '90-sl7-click-test.conf'
    assert not override.exists(), 'An override already exists'
    assert not RUNTIME.exists(), 'A prior trial requires review before re-use'
    override_text = ('[Service]\nExecStart=\nExecStart=/run/sl7-iptsd-click-test/iptsd /dev/'
                     + hidraw + '\n')
    state = {'service': service, 'hidraw': hidraw, 'override': str(override),
             'override_text': override_text, 'automatic_rollback_seconds': 180,
             'original_binary_sha256': review['installed_binary_sha256'],
             'candidate_binary_sha256': review['candidate_binary_sha256'],
             'calibration_sha256': review['calibration_sha256'], 'restored': False}
    if not args.apply:
        print(json.dumps({'read_only_preflight_passed': True, **state}, indent=2))
        return
    if os.geteuid() != 0:
        raise RuntimeError('--apply requires root after user approval')
    RUNTIME.mkdir(mode=0o755)
    shutil.copyfile(candidate, RUNTIME / 'iptsd')
    (RUNTIME / 'iptsd').chmod(0o755)
    shutil.copyfile(ROOT / 'rollback-trial.py', RUNTIME / 'rollback.py')
    (RUNTIME / 'rollback.py').chmod(0o644)
    (RUNTIME / 'state.json').write_text(json.dumps(state, indent=2) + '\n')
    try:
        # Arm the rollback before changing the service that provides pointer input.
        run('systemd-run', '--unit=sl7-iptsd-click-rollback', '--on-active=180s',
            '--timer-property=AccuracySec=1s', '--property=Type=oneshot',
            '/usr/bin/python3', str(RUNTIME / 'rollback.py'))
        override.parent.mkdir(parents=True, exist_ok=True)
        override.write_text(override_text)
        run('systemctl', 'daemon-reload')
        run('systemctl', 'restart', service)
        assert run('systemctl', 'is-active', service) == 'active'
        # Type=simple can report active before the service child execs the daemon.
        executable = None
        for _ in range(40):
            pid = run('systemctl', 'show', service, '-p', 'MainPID', '--value')
            executable = Path('/proc', pid, 'exe').resolve()
            if executable == RUNTIME / 'iptsd':
                break
            time.sleep(0.05)
        else:
            raise RuntimeError('Unexpected executable after startup: ' + str(executable))
        assert sha(calibration) == review['calibration_sha256']
        print(json.dumps({'trial_active': True, **state}, indent=2))
    except BaseException:
        subprocess.run([sys.executable, str(RUNTIME / 'rollback.py')], check=False)
        raise


if __name__ == '__main__':
    main()
