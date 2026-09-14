# sl7-mac

Factory MAC address provisioning for the Microsoft Surface Laptop 7
(Snapdragon X Elite) under Linux — derived from UEFI at boot, no hardcoded
per-machine values.

## The problem

The WCN7850 Wi-Fi/Bluetooth chip in Snapdragon-based Surface devices ships
with **no burned-in addresses** — on Windows-on-ARM platforms, address
provisioning is the OS's job. Under Linux this means:

- **Wi-Fi**: ath12k invents a random `00:03:7f:…` MAC on every boot
  (`ethtool -P` even reports it as "permanent"). Breaks DHCP reservations
  and anything that identifies the machine by MAC.
- **Bluetooth**: the controller comes up with the invalid default address
  `00:00:00:00:5A:AD`, is flagged *unconfigured*, and BlueZ ignores it —
  Bluetooth simply doesn't work.

## The fix

Surface firmware provisions one factory address family per machine, based
at a Microsoft-OUI address:

| offset | radio |
|--------|-------------------------|
| base+0 | Wi-Fi |
| base+1 | Bluetooth |
| base+2 | Ethernet (MAC pass-through) |

The UEFI variable `MacAddressEmulationAddress-b7f95555-4ea5-4786-b088-78ba350a1b56`
(part of Surface's "MAC Address Emulation" / dock pass-through feature)
exposes **base+2**. Everything else is derivable, so:

- **`sl7-mac`** (`/usr/bin`) reads the variable via efivarfs and derives all
  three addresses (48-bit arithmetic, validated).
- **`sl7-wifi-mac.service`** runs before udev coldplug each boot and stages
  `/run/systemd/network/05-sl7-wifi-mac.link`, so udev applies the factory
  Wi-Fi MAC when the wlan device appears.
- **`sl7-bt-mac.service`** (pulled in by a udev rule when `hci0` appears,
  ordered before `bluetooth.service`) runs `mgmt-set-addr.py`, which speaks
  the BlueZ management socket directly, waits out the controller's firmware
  setup, and sets the public address on the unconfigured controller. No-ops
  if the address is already correct. (It's a raw-socket helper because
  `btmgmt` — BlueZ 5.85, at least — hangs without a TTY even for read-only
  commands, so it can't run from a unit.)

Result: both radios come up on their factory addresses on every boot, on
any kernel, on any SL7 (and most likely any Snapdragon Surface exposing the
same UEFI variable).

## Install

Grab the deb from the [Releases page](https://github.com/valeronm/sl7-mac/releases)
(CI builds and attaches it on every tag), or build it yourself:

```sh
sudo apt install build-essential debhelper   # build deps
dpkg-buildpackage -us -uc -b
sudo apt install ../sl7-mac_*.deb
```

Dependencies: `python3` only. The Wi-Fi unit is enabled automatically; the
BT unit is udev-triggered.

## Usage

```
sl7-mac wifi|bt|eth     # print a derived address
sl7-mac all             # print all three
sudo sl7-mac apply-bt   # manual recovery: set BT address now
sudo sl7-mac write-link # manual: (re)stage the runtime .link file
```

If the UEFI variable is absent on your machine, set
`ETH_MAC=aa:bb:cc:dd:ee:ff` (the base+2 address) in `/etc/default/sl7-mac`.

## Notes

- Verify what your firmware exposes:
  `od -An -tx1 -j4 /sys/firmware/efi/efivars/MacAddressEmulationAddress-*`
  (first 4 bytes of the variable are efivarfs attributes, then 6 MAC bytes).
- The Wi-Fi MAC must be applied by udev *before* NetworkManager touches the
  device, hence a `.link` file rather than `ip link set`. Runtime-generated
  `.link` files in `/run/systemd/network` are the mechanism that allows a
  computed address.
- The BT address can only be set while the controller is powered off; the
  helper handles power-down and the setup-time race (mgmt returns Invalid
  Index until the firmware download finishes).
- The `-2`/`-1` offsets are a Surface firmware convention, confirmed against
  the Windows registry (`NetworkSetup2\…\Kernel`, `PermanentAddress`) on
  hardware; the tool logs the derived family at boot so a mismatch on other
  models would be visible.
