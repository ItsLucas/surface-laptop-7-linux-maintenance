#!/usr/bin/python3
"""Install the user-approved click-state fix and verify both input services."""
from pathlib import Path
from datetime import datetime
import hashlib
import json
import os
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'touchpad-click-fix'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(*args):
    return subprocess.run(args, check=True, text=True, capture_output=True).stdout.strip()


def services():
    found = {}
    for node in Path('/sys/class/hidraw').glob('hidraw*'):
        values = dict(line.split('=', 1) for line in (node / 'device/uevent').read_text().splitlines())
        identity = values.get('HID_ID', '').split(':')[-2:]
        if identity in (['0000045E', '00000C77'], ['0000045E', '00000C6F']):
            found[identity[-1]] = 'iptsd@dev-' + node.name + '.service'
    assert set(found) == {'00000C77', '00000C6F'}, found
    return found


def main():
    assert os.geteuid() == 0
    package = WORK / 'iptsd_3.1.0+sl7.2_arm64.deb'
    assert sha(package) == '67404c090557a71498f1d2e3d3cb8e2863c6d099d8617eafa10383da5bc16672'
    assert run('dpkg-query', '-W', '-f=${Version}', 'iptsd') == '3.1.0+sl7.1'
    calibration = Path('/etc/iptsd.d/91-calibration-045E-0C77.conf')
    expected_calibration = '14f90f9eaaa855f4bdf52cdc41d158a9d763d4d0e35f6af40166c0f74c5b3847'
    assert sha(calibration) == expected_calibration
    active = services()
    for unit in active.values():
        assert run('systemctl', 'is-active', unit) == 'active'
    backup = Path('/var/backups/sl7-combined') / ('click-fix-installed-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
    backup.mkdir(parents=True, mode=0o700)
    shutil.copy2(calibration, backup / calibration.name)
    shutil.copy2('/usr/bin/iptsd', backup / 'iptsd-before')
    old_default = sha(Path('/etc/default/grub.d/zz-sl7-local-kernel.cfg'))
    log = WORK / 'package-install.log'
    try:
        with log.open('w') as output:
            subprocess.run(['dpkg', '--install', str(package)], stdout=output, stderr=subprocess.STDOUT, check=True)
        expected_binary = '26c9ca51dfc97372f4ae4dd7767ae42a49f49220fdc2d1c9b990bd9ff3c06822'
        assert run('dpkg-query', '-W', '-f=${Version}', 'iptsd') == '3.1.0+sl7.2'
        assert sha(Path('/usr/bin/iptsd')) == expected_binary
        for unit in active.values():
            for _ in range(40):
                pid = run('systemctl', 'show', unit, '-p', 'MainPID', '--value')
                if pid != '0' and Path('/proc', pid, 'exe').resolve() == Path('/usr/bin/iptsd'):
                    if sha(Path('/proc', pid, 'exe')) == expected_binary:
                        break
                time.sleep(.1)
            else:
                raise RuntimeError('Patched daemon did not start: ' + unit)
            assert run('systemctl', 'is-active', unit) == 'active'
        assert sha(calibration) == expected_calibration
        assert sha(Path('/etc/default/grub.d/zz-sl7-local-kernel.cfg')) == old_default
    except BaseException:
        subprocess.run(['dpkg', '--install', str(ROOT / 'artifacts/iptsd_3.1.0+sl7.1_arm64.deb')], check=False)
        raise
    report = {'timestamp': datetime.now().astimezone().isoformat(), 'user_approved': True,
              'installed_version': '3.1.0+sl7.2', 'package_sha256': sha(package),
              'binary_sha256': sha(Path('/usr/bin/iptsd')), 'services': active,
              'both_services_running_patched_binary': True, 'calibration_unchanged': True,
              'boot_configuration_unchanged_by_package_install': True, 'backup': str(backup),
              'known_heatmap_suppression_issue_not_claimed_fixed': True}
    path = WORK / 'installed-click-fix.json'
    path.write_text(json.dumps(report, indent=2) + '\n')
    owner = ROOT.stat()
    for p in [path, log]: os.chown(p, owner.st_uid, owner.st_gid)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
