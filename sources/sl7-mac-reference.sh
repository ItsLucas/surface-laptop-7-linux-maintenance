#!/bin/bash
# sl7-mac — derive the Surface Laptop 7 factory MAC family from UEFI.
#
# Surface firmware provisions one factory base address (Microsoft OUI):
#   base+0 = Wi-Fi, base+1 = Bluetooth, base+2 = Ethernet pass-through.
# The UEFI variable MacAddressEmulationAddress exposes base+2. The WCN7850
# radio ships with no burned-in addresses, so the OS must apply these —
# otherwise ath12k mints a random 00:03:7f MAC each boot and the BT
# controller comes up unconfigured.
#
# Subcommands:
#   wifi | bt | eth   print the derived address
#   all               print all three, labeled
#   write-link        stage a runtime systemd .link with the Wi-Fi MAC
#                     (run before udev coldplug; sl7-wifi-mac.service)
#   apply-bt          set the BT controller public address, no-op if already
#                     correct (root; sl7-bt-mac.service)
#
# Escape hatch: if the UEFI variable is absent, ETH_MAC=aa:bb:cc:dd:ee:ff in
# /etc/default/sl7-mac supplies base+2 manually.
set -euo pipefail

# Env overrides exist for testing only.
EFIVAR=${SL7_MAC_EFIVAR:-/sys/firmware/efi/efivars/MacAddressEmulationAddress-b7f95555-4ea5-4786-b088-78ba350a1b56}
OVERRIDE=${SL7_MAC_OVERRIDE:-/etc/default/sl7-mac}
LINK_FILE=${SL7_MAC_LINK:-/run/systemd/network/05-sl7-wifi-mac.link}
MGMT_HELPER=${SL7_MAC_HELPER:-/usr/lib/sl7-mac/mgmt-set-addr.py}
WLAN_ADDR=${SL7_MAC_WLAN:-/sys/class/net/wlan0/address}

die() { echo "sl7-mac: error: $*" >&2; exit 1; }

mac_to_int() {
    local hex=${1//:/}
    if [[ ! $hex =~ ^[0-9a-fA-F]{12}$ ]]; then
        die "malformed MAC: $1"
    fi
    echo $((16#$hex))
}

int_to_mac() {
    local v=$1
    printf '%02x:%02x:%02x:%02x:%02x:%02x\n' \
        $(( v >> 40 & 0xff )) $(( v >> 32 & 0xff )) $(( v >> 24 & 0xff )) \
        $(( v >> 16 & 0xff )) $(( v >> 8 & 0xff ))  $(( v & 0xff ))
}

# Ethernet pass-through address (family base+2) as a 48-bit integer.
eth_int() {
    local mac=""
    if [[ -r $OVERRIDE ]]; then
        # shellcheck source=/dev/null
        . "$OVERRIDE"
        mac=${ETH_MAC:-}
    fi
    if [[ -n $mac ]]; then
        mac_to_int "$mac"
        return
    fi
    if [[ ! -r $EFIVAR ]]; then
        die "UEFI variable missing and no ETH_MAC override in $OVERRIDE"
    fi
    local hex
    hex=$(od -An -tx1 -j4 "$EFIVAR" 2>/dev/null | tr -d ' \n')
    if [[ ${#hex} -ne 12 ]]; then
        die "unexpected efivar size $(wc -c < "$EFIVAR") (want 10: 4-byte attrs + 6-byte MAC)"
    fi
    echo $((16#$hex))
}

derive() {
    local eth
    eth=$(eth_int)
    if (( eth == 0 )) || (( eth == 16#ffffffffffff )); then
        die "implausible base address: $(int_to_mac "$eth")"
    fi
    if (( (eth >> 40) & 1 )); then
        die "base address is multicast: $(int_to_mac "$eth")"
    fi
    # Subtracting 2 must stay within the OUI's NIC-specific part; a borrow
    # into the OUI means the value can't be a real family base+2.
    if (( (eth & 16#ffffff) < 2 )); then
        die "NIC part of $(int_to_mac "$eth") too small to be family base+2"
    fi
    ETH=$(int_to_mac "$eth")
    WIFI=$(int_to_mac $(( eth - 2 )))
    BT=$(int_to_mac $(( eth - 1 )))
}

write_link() {
    derive
    mkdir -p "$(dirname "$LINK_FILE")"
    cat > "$LINK_FILE.tmp" <<EOF
# Generated at boot by sl7-mac from UEFI MacAddressEmulationAddress.
# Factory family: wifi=$WIFI bt=$BT eth=$ETH
[Match]
Type=wlan
Driver=ath12k*

[Link]
MACAddress=$WIFI
EOF
    mv "$LINK_FILE.tmp" "$LINK_FILE"
    echo "sl7-mac: staged $LINK_FILE (wifi=$WIFI; family base+2=$ETH)"
}

apply_bt() {
    # euid gate skipped under the test override: a stub helper needs no root
    if [[ -z ${SL7_MAC_HELPER:-} && $EUID -ne 0 ]]; then
        die "apply-bt needs root: opens the BT mgmt control socket"
    fi
    derive
    echo "sl7-mac: target BT public address $BT (family: wifi=$WIFI eth=$ETH)"
    exec python3 "$MGMT_HELPER" 0 "$BT"
}

# status_row <label> <derived> <live>: derived address + live verdict
status_row() {
    local state
    if [[ -z $3 ]]; then
        state="(no live reading)"
    elif [[ $3 == "$2" ]]; then
        state="applied"
    else
        state="MISMATCH: live is $3"
    fi
    printf '%-14s %s  %s\n' "$1:" "$2" "$state"
}

# unit_state <unit>: oneshot-aware — plain ActiveState reads "inactive"
# for a oneshot that ran fine at boot, which looks broken.
unit_state() {
    local st res ts
    st=$(systemctl show "$1.service" -p ActiveState --value 2>/dev/null || true)
    case $st in
        inactive)
            ts=$(systemctl show "$1.service" -p ExecMainExitTimestamp \
                     --value 2>/dev/null || true)
            res=$(systemctl show "$1.service" -p Result --value 2>/dev/null \
                     || true)
            if [[ $res == success && -n $ts ]]; then
                echo "ran ok ($ts)"
            elif [[ -n $res && $res != success ]]; then
                echo "FAILED: $res (journalctl -u $1)"
            else
                echo "not run this boot"
            fi ;;
        failed)
            echo "FAILED (journalctl -u $1)" ;;
        *)
            echo "${st:-unknown}" ;;
    esac
}

status() {
    local unit
    for unit in sl7-wifi-mac sl7-bt-mac; do
        printf '%-14s %s\n' "$unit:" "$(unit_state "$unit")"
    done
    if [[ -f $LINK_FILE ]]; then
        printf '%-14s staged (%s)\n' "link file:" \
            "$(sed -n 's/^MACAddress=//p' "$LINK_FILE")"
    else
        printf '%-14s not staged\n' "link file:"
    fi
    derive
    local wifi_live bt_live
    wifi_live=$(cat "$WLAN_ADDR" 2>/dev/null || true)
    bt_live=$(bluetoothctl show 2>/dev/null \
        | awk '/^Controller /{print tolower($2); exit}' || true)
    status_row wifi "$WIFI" "$wifi_live"
    status_row bt "$BT" "$bt_live"
    printf '%-14s %s  (dock ethernet; nothing applies it on Linux)\n' \
        "eth:" "$ETH"
}

usage() {
    cat <<'EOF'
usage: sl7-mac <command>

  wifi | bt | eth   print the derived address
  all               print all three, labeled
  write-link        stage a runtime systemd .link with the Wi-Fi MAC
  apply-bt          set the BT controller public address (root)
  status            units, staged .link, and derived vs live addresses

See sl7-mac(1) for the ETH_MAC override and details.
EOF
}

case ${1:-} in
    wifi)       derive; echo "$WIFI" ;;
    bt)         derive; echo "$BT" ;;
    eth)        derive; echo "$ETH" ;;
    all)        derive; printf 'wifi: %s\nbt:   %s\neth:  %s\n' "$WIFI" "$BT" "$ETH" ;;
    write-link) write_link ;;
    apply-bt)   apply_bt ;;
    status)     status ;;
    -h|--help|help) usage ;;
    "")         usage >&2; exit 1 ;;
    *)          echo "sl7-mac: unknown command: $1" >&2; usage >&2; exit 1 ;;
esac
