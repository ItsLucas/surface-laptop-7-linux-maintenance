#!/usr/bin/python3
"""SL7 SPI runtime-PM comparison: read-only preflight unless --apply/--restore."""
from pathlib import Path
import argparse
import json
import os
import shutil
import subprocess
import time

DEVICE = Path('/sys/devices/platform/soc@0/8c0000.geniqup/88c000.spi')
CONTROL = DEVICE / 'power/control'
RUNTIME = Path('/run/sl7-spi-runtime-pm-trial')
TIMER = 'sl7-spi-runtime-pm-rollback'


def run(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout.strip()


def restore():
    state = json.loads((RUNTIME / 'state.json').read_text())
    assert state['control'] == str(CONTROL)
    value = CONTROL.read_text().strip()
    assert value in ('on', state['original_control'])
    if value != state['original_control']:
        CONTROL.write_text(state['original_control'] + '\n')
    run('systemctl', 'stop', TIMER + '.timer')
    state['restored'] = True
    state['restored_epoch_ms'] = time.time() * 1000
    (RUNTIME / 'state.json').write_text(json.dumps(state, indent=2) + '\n')
    print(json.dumps(state, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--apply', action='store_true')
    action.add_argument('--restore', action='store_true')
    args = parser.parse_args()
    if args.restore:
        assert os.geteuid() == 0
        restore()
        return
    assert (DEVICE / 'driver').resolve().name == 'geni_spi'
    assert (DEVICE / 'of_node/compatible').read_bytes().split(b'\0')[0] == b'qcom,geni-spi-qspi'
    children = list(DEVICE.glob('spi_master/spi*/spi*.*'))
    assert len(children) == 1
    assert any('001C:045E:0C77.' in p.name for p in children[0].iterdir())
    assert CONTROL.read_text().strip() == 'auto'
    assert not RUNTIME.exists(), 'Previous trial needs review'
    assert run('dpkg-query', '-W', '-f=${Version}', 'iptsd') == '3.1.0+sl7.1'
    hidraw_nodes = [n for n in Path('/sys/class/hidraw').glob('hidraw*')
                    if (n / 'device').resolve().is_relative_to(children[0].resolve())]
    assert len(hidraw_nodes) == 1
    service = 'iptsd@dev-' + hidraw_nodes[0].name + '.service'
    assert run('systemctl', 'is-active', service) == 'active'
    assert '/usr/bin/iptsd ' in run('systemctl', 'show', service, '-p', 'ExecStart', '--value')
    state = {'control': str(CONTROL), 'original_control': 'auto', 'test_control': 'on',
             'automatic_restore_seconds': 180, 'iptsd_restarted': False,
             'boot_and_gpio_unchanged': True, 'restored': False}
    if not args.apply:
        print(json.dumps({'read_only_preflight_passed': True, **state}, indent=2))
        return
    assert os.geteuid() == 0
    RUNTIME.mkdir(mode=0o755)
    shutil.copyfile(Path(__file__), RUNTIME / 'trial.py')
    (RUNTIME / 'state.json').write_text(json.dumps(state, indent=2) + '\n')
    try:
        run('systemd-run', '--unit=' + TIMER, '--on-active=180s',
            '--timer-property=AccuracySec=1s', '--property=Type=oneshot',
            '/usr/bin/python3', str(RUNTIME / 'trial.py'), '--restore')
        CONTROL.write_text('on\n')
        assert CONTROL.read_text().strip() == 'on'
        for _ in range(20):
            if (DEVICE / 'power/runtime_status').read_text().strip() == 'active':
                break
            time.sleep(.05)
        else:
            raise RuntimeError('Controller did not become active')
        state['started_epoch_ms'] = time.time() * 1000
        (RUNTIME / 'state.json').write_text(json.dumps(state, indent=2) + '\n')
        print(json.dumps({'trial_active': True, **state}, indent=2))
    except BaseException:
        restore()
        raise


if __name__ == '__main__':
    main()
