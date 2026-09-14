#!/usr/bin/python3
"""Promote the tested signed SPI image; no image replacement or reboot."""
from pathlib import Path
from datetime import datetime
import argparse
import hashlib
import json
import os
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
ENTRY = 'sl7-spi-touchscreen-test'
SCRIPT = Path('/etc/grub.d/45_sl7_spi_touchscreen_test')
DEFAULT = Path('/etc/default/grub.d/zz-sl7-local-kernel.cfg')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    old = DEFAULT.read_text()
    assert 'GRUB_DEFAULT="sl7-combined-kernel"' in old
    new = old.replace('GRUB_DEFAULT="sl7-combined-kernel"', 'GRUB_DEFAULT="' + ENTRY + '"')
    script = SCRIPT.read_text()
    assert script.count("menuentry 'SL7 SPI touchscreen test (MSHW0461 GTCH)'") == 1
    renamed = script.replace("menuentry 'SL7 SPI touchscreen test (MSHW0461 GTCH)'",
                             "menuentry 'SL7 - Wi-Fi, touchpad and touchscreen'")
    assert 'spi-touchscreen-test/kernel.efi' in Path('/proc/cmdline').read_text()
    if not args.apply:
        print(json.dumps({'read_only_preflight_passed': True, 'new_default': ENTRY,
                          'menu_title': 'SL7 - Wi-Fi, touchpad and touchscreen',
                          'fallback': 'sl7-combined-kernel', 'menu_timeout_seconds': 5,
                          'only_changed_files': [str(DEFAULT), str(SCRIPT)],
                          'runs_update_grub': True, 'replaces_kernel': False, 'reboots': False}, indent=2))
        return
    assert os.geteuid() == 0
    image = Path('/boot/sl7/7.2.0-5-sl7-spi-touchscreen-test/kernel.efi')
    assert hashlib.sha256(image.read_bytes()).hexdigest() == '94003dc6c6c1e194054037ced995eb2258a08e1c346acaaf0964a37c673e927f'
    subprocess.run(['sbverify', '--cert', str(ROOT / 'artifacts/SL7-Kernel-BOOT.pem'), str(image)], check=True)
    backup = Path('/var/backups/sl7-combined') / ('touchscreen-default-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
    backup.mkdir(parents=True, mode=0o700)
    for p in [DEFAULT, SCRIPT, Path('/boot/grub/grub.cfg')]: shutil.copy2(p, backup / p.name)
    try:
        DEFAULT.write_text(new)
        SCRIPT.write_text(renamed)
        subprocess.run(['update-grub'], check=True)
        text = Path('/boot/grub/grub.cfg').read_text()
        assert text.count("--id '" + ENTRY + "'") == 1
        assert "--id 'sl7-combined-kernel'" in text
        assert 'set default="' + ENTRY + '"' in text
    except BaseException:
        DEFAULT.write_text(old); SCRIPT.write_text(script)
        subprocess.run(['update-grub'], check=False)
        raise
    report = {'timestamp': datetime.now().astimezone().isoformat(), 'user_approved': True,
              'default': ENTRY, 'normal_fallback': 'sl7-combined-kernel', 'timeout_seconds': 5,
              'image_unchanged': True, 'rebooted': False, 'backup': str(backup)}
    path = ROOT / 'spi-touchscreen-test/default-promoted.json'
    path.write_text(json.dumps(report, indent=2) + '\n')
    owner = ROOT.stat(); os.chown(path, owner.st_uid, owner.st_gid)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
