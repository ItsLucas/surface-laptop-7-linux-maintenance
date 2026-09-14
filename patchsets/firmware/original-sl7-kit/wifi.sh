#!/usr/bin/env bash
# Post-reboot test: record existing state, enable Wi-Fi normally, then scan.
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
OUT="$RESULTS/$STAMP-wifi-test"
mkdir -p "$OUT"
exec > >(tee "$OUT/progress.txt") 2>&1
say 'Saving Wi-Fi state, then enabling Wi-Fi through rfkill/NetworkManager and scanning.'
shelllog before 'rfkill list; iw dev; ip -details link; nmcli radio; nmcli device status'
runlog unblock rfkill unblock wifi
runlog radio-on nmcli radio wifi on
sleep 8
shelllog after 'rfkill list; iw dev; ip -details link; nmcli radio; nmcli device status'
runlog scan nmcli --wait 20 device wifi list --rescan yes
runlog kernel journalctl -b -k --no-pager -o short-monotonic
runlog network journalctl -b --no-pager -u NetworkManager -u wpa_supplicant -n 5000
finish_output
say 'If networks appear, connect using keyboard: nmtui'
say 'A hard rfkill block cannot generally be cleared by rfkill unblock; keep this report if still blocked.'
