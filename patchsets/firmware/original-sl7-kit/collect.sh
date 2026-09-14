#!/usr/bin/env bash
# All collection is offline. Individual commands time out; absent tools are logged.
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
LABEL=${1:-manual}
LABEL=${LABEL//[^a-zA-Z0-9_-]/_}
OUT="$RESULTS/$STAMP-$LABEL"
mkdir -p "$OUT"
export OUT
exec > >(tee "$OUT/progress.txt") 2>&1
say 'Collecting SL7 diagnostics. Missing commands are OK. Usually 2-5 minutes.'
runlog identity uname -a
shelllog system 'date -Is; uptime; cat /etc/os-release /proc/cmdline; cat /sys/class/dmi/id/{sys_vendor,product_name,product_version,bios_version,bios_date}; tr "\0" "\n" </proc/device-tree/model; cat /sys/kernel/security/lockdown; mokutil --sb-state; bootctl status'
runlog disks lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINTS,UUID
runlog mounts findmnt
runlog kernel-current journalctl -b -k --no-pager -o short-monotonic
runlog dmesg dmesg
runlog boot-list journalctl --list-boots --no-pager
for b in 1 2 3; do runlog "kernel-previous-$b" journalctl -b "-$b" -k --no-pager -o short-monotonic; done
runlog system-journal journalctl -b --no-pager -n 15000 -o short-monotonic
runlog network-journal journalctl -b --no-pager -u NetworkManager -u wpa_supplicant -u bluetooth -n 6000
runlog failures systemctl --failed --no-pager
runlog usb-tree lsusb -t
runlog usb-ids lsusb
runlog usb-details lsusb -v
runlog pci lspci -nnk -vv
runlog modules lsmod
shelllog module-details 'for m in ath12k ath12k_wifi7 ath12k_pci dwc3 dwc3_qcom xhci_plat_hcd ucsi_glink pmic_glink pmic_glink_altmode ps883x phy_qcom_qmp_combo phy_snps_eusb2 phy_nxp_ptn3222 qcom_q6v5_pas msm; do echo "### $m"; modinfo "$m"; done'
shelllog module-settings 'for d in /sys/module/ath12k* /sys/module/dwc3* /sys/module/usbcore /sys/module/ucsi* /sys/module/pmic_glink*; do for f in "$d"/parameters/*; do [ -f "$f" ] && { echo "$f"; cat "$f"; }; done; done; grep -R -n -E "ath12k|usb|dwc3|ucsi|glink|remoteproc|firmware" /etc/modprobe.d /etc/modules-load.d 2>/dev/null'
shelllog usb-platform 'for d in /sys/bus/platform/drivers/dwc3* /sys/bus/platform/drivers/xhci* /sys/bus/platform/devices/*usb* /sys/bus/auxiliary/devices/*glink*; do echo "### $d"; ls -l "$d"; done'
shelllog platform-power 'for d in /sys/bus/platform/devices/*usb* /sys/bus/platform/devices/*phy* /sys/bus/platform/devices/*repeater* /sys/bus/platform/devices/pmic-glink /sys/bus/i2c/devices/3-0008 /sys/bus/i2c/devices/7-0008; do [ -d "$d" ] || continue; echo "### $d"; readlink "$d/driver"; for n in power/control power/runtime_status power/runtime_active_time power/runtime_suspended_time power/autosuspend_delay_ms power/wakeup modalias uevent; do [ -f "$d/$n" ] && { echo "$n"; cat "$d/$n"; }; done; done'
shelllog usb-sysfs 'for d in /sys/bus/usb/devices/*; do echo "### $d"; for n in product manufacturer idVendor idProduct busnum devnum speed authorized bConfigurationValue power/control power/runtime_status power/autosuspend_delay_ms power/wakeup; do [ -f "$d/$n" ] && { echo "$n"; cat "$d/$n"; }; done; done'
shelllog typec 'ls -l /sys/class/typec /sys/class/usb_role; for d in /sys/class/typec/* /sys/class/usb_role/*; do echo "### $d"; ls -l "$d/"; for n in data_role power_role port_type preferred_role orientation power_operation_mode usb_power_delivery_revision usb_typec_revision number_of_alternate_modes supports_usb_power_delivery role active svid mode; do [ -f "$d/$n" ] && { echo "$n"; cat "$d/$n"; }; done; done'
shelllog remoteproc 'for d in /sys/class/remoteproc/remoteproc*; do echo "### $d"; for n in name state firmware recovery coredump; do [ -f "$d/$n" ] && { echo "$n"; cat "$d/$n"; }; done; done; ls -l /sys/bus/rpmsg/devices /sys/bus/auxiliary/devices'
shelllog network 'ip -details link; ip address; ip route; rfkill list; iw dev; iw phy; iw reg get; nmcli general status; nmcli radio; nmcli device status; nmcli device show'
shelllog rfkill 'for d in /sys/class/rfkill/*; do echo "### $d"; for n in name type soft hard state; do [ -f "$d/$n" ] && { echo "$n"; cat "$d/$n"; }; done; done; ls -l /sys/class/ieee80211'
shelllog wifi-pci 'for d in /sys/bus/pci/devices/*; do [ "$(cat "$d/vendor" 2>/dev/null)" = 0x17cb ] || continue; echo "### $d"; ls -l "$d"; for n in vendor device subsystem_vendor subsystem_device modalias enable power/control power/runtime_status; do echo "$n"; cat "$d/$n" 2>/dev/null; done; done'
runlog interrupts cat /proc/interrupts
shelllog power 'cat /sys/power/state /sys/power/mem_sleep /sys/power/pm_wakeup_irq; for f in /sys/class/power_supply/*/uevent; do echo "$f"; cat "$f"; done'
shelllog debugfs 'for f in devices_deferred usb/devices clk/clk_summary regulator/regulator_summary pm_genpd/pm_genpd_summary interconnect/interconnect_summary gpio wakeup_sources suspend_stats; do echo "### $f"; timeout 5 cat "/sys/kernel/debug/$f" 2>/dev/null; done; ls -l /sys/kernel/debug/usb /sys/kernel/debug/ieee80211; for f in /sys/kernel/debug/pinctrl/*/pinmux-pins; do echo "$f"; timeout 5 cat "$f"; done'
runlog inputs cat /proc/bus/input/devices
shelllog graphics 'ls -l /dev/dri /sys/class/drm; for f in /sys/class/drm/card*-*/status; do echo "$f"; cat "$f"; done; command -v glxinfo >/dev/null && glxinfo -B'
shelllog audio 'cat /proc/asound/cards; aplay -l; arecord -l'
shelllog firmware 'for d in /usr/lib/firmware/updates/qcom/x1e80100/microsoft /usr/lib/firmware/qcom/x1e80100/microsoft /usr/lib/firmware/ath12k/WCN7850/hw2.0 /usr/lib/firmware/updates/ath12k/WCN7850/hw2.0; do echo "### $d"; find "$d" -maxdepth 3 -printf "%y %s %p -> %l\n" 2>/dev/null; find "$d" -maxdepth 3 -type f -exec sha256sum {} + 2>/dev/null; done; cat /sys/module/firmware_class/parameters/path'
shelllog packages 'dpkg-query -W -f="${binary:Package}\t${Version}\n" | grep -Ei "linux-|firmware|qcom|stubble|flash-kernel|surface|ipts|mesa|network-manager|wpasupplicant"; apt-cache policy linux-image-generic linux-firmware-qualcomm-wireless hwe-qcom-x1e-meta; ls -lh /boot; grep -E "CONFIG_(ATH12K|RFKILL|FW_LOADER|USB_DWC3|TYPEC|QCOM|SURFACE)" /boot/config-$(uname -r)'
shelllog boot-config 'cat /etc/default/grub; grep -R -n -E "devicetree|linux.*vmlinuz|initrd|menuentry" /boot/grub/grub.cfg /etc/grub.d /etc/default/grub.d 2>/dev/null'
shelllog initramfs 'lsinitramfs /boot/initrd.img-$(uname -r) | grep -Ei "qcdx|qcadsp|qccdsp|adsp_dtbs|board-2|WCN7850|ath12k|dwc3|glink|ps883"'
runlog device-tree dtc -I fs -O dts /sys/firmware/devicetree/base
if [ -r /sys/firmware/fdt ]; then cp /sys/firmware/fdt "$OUT/live.dtb"; fi
if [ -d /sys/firmware/devicetree/base ]; then
    timeout 30 tar -C /sys/firmware/devicetree/base -cf "$OUT/device-tree.tar" . 2>"$OUT/device-tree-tar-errors.txt"
fi
shelllog pstore 'for f in /sys/fs/pstore/*; do [ -f "$f" ] && { echo "### $f"; head -c 1048576 "$f"; }; done'
# Preserve only board containers for exact name matching, not unrelated personal files.
mkdir -p "$OUT/board-files"
mkdir -p "$OUT/module-files"
for m in ath12k ath12k_wifi7 ucsi_glink dwc3 dwc3_qcom pmic_glink; do
    f=$(modinfo -n "$m" 2>/dev/null || true)
    [[ -f "$f" ]] && cp -L "$f" "$OUT/module-files/$(basename "$f")"
done
for d in /usr/lib/firmware/ath12k/WCN7850/hw2.0 /usr/lib/firmware/updates/ath12k/WCN7850/hw2.0; do
    for f in "$d"/board-2.bin*; do
        [ -f "$f" ] || continue
        prefix=base; [[ "$d" == */updates/* ]] && prefix=updates
        cp -L "$f" "$OUT/board-files/$prefix-$(basename "$f")"
    done
done
if [ "${2:-}" != --no-live ]; then
    say 'USB LIVE TEST: 90 seconds. Use known data-capable cables/devices.'
    timeout --kill-after=2s 92s journalctl -k -f -n 0 -o short-monotonic >"$OUT/usb-live-kernel.txt" 2>&1 &
    KPID=$!
    timeout --kill-after=2s 92s udevadm monitor --kernel --udev --property >"$OUT/usb-live-udev.txt" 2>&1 &
    UPID=$!
    for step in 1 2 3; do
        case $step in
            1) say '0-30s: unplug/replug a USB-A mouse or flash drive directly.' ;;
            2) say '30-60s: test rear USB-C port (near hinge), flip cable once.' ;;
            3) say '60-90s: test front USB-C port, flip cable once.' ;;
        esac
        date -Is >>"$OUT/usb-test-markers.txt"
        echo "step=$step" >>"$OUT/usb-test-markers.txt"
        sleep 30
        runlog "usb-tree-stage-$step" lsusb -t
    done
    wait "$KPID" "$UPID" 2>/dev/null || true
fi
runlog kernel-final journalctl -b -k --no-pager -o short-monotonic
shelllog final-status 'lsusb -t; rfkill list; iw dev; nmcli device status; ls -l /sys/class/typec /sys/class/usb_role'
finish_output
say 'Diagnostics saved in your Linux home. Return to Windows and I can extract them from ext4.'
