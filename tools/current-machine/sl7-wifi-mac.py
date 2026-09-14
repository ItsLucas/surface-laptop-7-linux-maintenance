#!/usr/bin/python3
"""Provision only the SL7 Wi-Fi address from its Surface UEFI address family.

Algorithm: https://github.com/valeronm/sl7-mac/blob/main/sl7-mac
No firmware writes, Bluetooth operations, or kernel changes are performed.
"""
from pathlib import Path
import argparse
import os
import tempfile

EFIVAR = Path('/sys/firmware/efi/efivars/MacAddressEmulationAddress-b7f95555-4ea5-4786-b088-78ba350a1b56')
LINK = Path('/run/systemd/network/05-sl7-wifi-mac.link')
NM = Path('/run/NetworkManager/conf.d/90-sl7-wifi-mac.conf')


def derive():
    compatible = Path('/sys/firmware/devicetree/base/compatible').read_bytes().split(b'\0')
    if b'microsoft,romulus13' not in compatible:
        raise RuntimeError('This configuration is scoped to Surface Laptop 7 Romulus13')
    data = EFIVAR.read_bytes()
    if len(data) != 10:
        raise RuntimeError('Expected four EFI attribute bytes and six address bytes')
    raw = data[4:]
    value = int.from_bytes(raw, 'big')
    if raw[0] & 3 or value == 0 or value == 0xffffffffffff or value & 0xffffff < 2:
        raise RuntimeError('UEFI address is not a plausible globally assigned address family')
    return ':'.join(f'{b:02x}' for b in (value - 2).to_bytes(6, 'big'))


def configuration(mac):
    return {
        LINK: f'''# Generated from Surface UEFI by sl7-wifi-mac; do not edit.
[Match]
Path=platform-1c08000.pci-pci-0004:01:00.0
Driver=ath12k_wifi7_pci
Type=wlan

[Link]
NamePolicy=keep kernel database onboard slot path
AlternativeNamesPolicy=database onboard slot path mac
MACAddressPolicy=none
MACAddress={mac}
''',
        NM: f'''# Generated from Surface UEFI; applies to this built-in Wi-Fi interface.
# Supplies a stable address even if Wi-Fi was already enumerated in initrd.
[connection-sl7-uefi-mac]
match-device=interface-name:wlP4p1s0
wifi.cloned-mac-address={mac}
''',
    }


def write_atomic(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            os.fchmod(stream.fileno(), 0o644)
            stream.write(text)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['show', 'preview', 'stage'])
    args = parser.parse_args()
    mac = derive()
    if args.action == 'show':
        print(mac)
        return
    for path, text in configuration(mac).items():
        if args.action == 'preview':
            print(str(path) + '\n' + text)
        else:
            if os.geteuid() != 0:
                raise RuntimeError('Staging runtime configuration requires root')
            write_atomic(path, text)
    if args.action == 'stage':
        print('SL7 Wi-Fi UEFI address staged: ' + mac)


if __name__ == '__main__':
    main()
