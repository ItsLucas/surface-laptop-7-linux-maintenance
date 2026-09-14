#!/usr/bin/python3
"""Install the reviewed Wi-Fi-only UEFI provisioning and apply while disconnected."""
from pathlib import Path
from datetime import datetime
import configparser
import importlib.util
import json
import os
import shutil
import subprocess
import time

PROJECT = Path(__file__).resolve().parent
IFACE = 'wlP4p1s0'


def run(args):
    return subprocess.check_output(args, text=True).strip()


def main():
    assert os.geteuid() == 0
    spec = importlib.util.spec_from_file_location('sl7_mac', PROJECT / 'sl7-wifi-mac.py')
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    address = helper.derive()
    assert address == '78:86:2e:5e:ec:47', 'Firmware value changed; review before applying'
    net = Path('/sys/class/net') / IFACE
    assert (net / 'device/driver').resolve().name == 'ath12k_wifi7_pci'
    state = int(run(['nmcli', '-g', 'GENERAL.STATE', 'device', 'show', IFACE]).split()[0])
    assert state in (10, 20, 30), 'Wi-Fi is connected or connecting; will not interrupt it'
    original = (net / 'address').read_text().strip()
    up = bool(int((net / 'flags').read_text().strip(), 16) & 1)
    backup = Path('/var/backups/sl7-combined') / ('wifi-mac-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
    backup.mkdir(parents=True, mode=0o700)
    mapping = {
        PROJECT / 'sl7-wifi-mac.py': Path('/usr/local/libexec/sl7-wifi-mac'),
        PROJECT / 'sl7-wifi-mac.service': Path('/etc/systemd/system/sl7-wifi-mac.service'),
    }
    for src, dest in mapping.items():
        if dest.exists():
            shutil.copy2(dest, backup / dest.name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        os.chmod(dest, 0o755 if src.suffix == '.py' else 0o644)
    for dest in (helper.LINK, helper.NM):
        if dest.exists():
            shutil.copy2(dest, backup / dest.name)
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    subprocess.run(['systemd-analyze', 'verify', str(mapping[PROJECT / 'sl7-wifi-mac.service'])], check=True)
    subprocess.run(['systemctl', 'enable', '--now', 'sl7-wifi-mac.service'], check=True)
    config = configparser.ConfigParser(interpolation=None)
    config.read_string(run(['NetworkManager', '--print-config']))
    assert config['connection-sl7-uefi-mac']['wifi.cloned-mac-address'] == address
    subprocess.run(['nmcli', 'general', 'reload', 'conf'], check=True)
    managed = state != 10
    try:
        if managed:
            subprocess.run(['nmcli', 'device', 'set', IFACE, 'managed', 'no'], check=True)
        subprocess.run(['ip', 'link', 'set', 'dev', IFACE, 'down'], check=True)
        subprocess.run(['ip', 'link', 'set', 'dev', IFACE, 'address', address], check=True)
        if up:
            subprocess.run(['ip', 'link', 'set', 'dev', IFACE, 'up'], check=True)
    except Exception:
        subprocess.run(['ip', 'link', 'set', 'dev', IFACE, 'down'], check=False)
        subprocess.run(['ip', 'link', 'set', 'dev', IFACE, 'address', original], check=False)
        if up:
            subprocess.run(['ip', 'link', 'set', 'dev', IFACE, 'up'], check=False)
        raise
    finally:
        if managed:
            subprocess.run(['nmcli', 'device', 'set', IFACE, 'managed', 'yes'], check=True)
    time.sleep(2)
    current = (net / 'address').read_text().strip()
    assert current == address, 'Runtime address did not remain applied'
    report = {'timestamp': datetime.now().astimezone().isoformat(), 'interface': IFACE,
              'previous_address': original, 'uefi_derived_address': address,
              'current_address': current, 'boot_service_enabled': True,
              'networkmanager_default_verified': True, 'backup_directory': str(backup),
              'bluetooth_modified': False, 'next_boot_verified': False,
              'corporate_connection_verified': False}
    out = PROJECT / 'logs/wifi-mac-installed.json'
    out.write_text(json.dumps(report, indent=2) + '\n')
    os.chown(out, PROJECT.stat().st_uid, PROJECT.stat().st_gid)
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    main()
