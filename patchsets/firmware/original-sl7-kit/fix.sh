#!/usr/bin/env bash
# Offline firmware-only fixes. No module reload or reboot is performed.
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
set -e
OUT="$RESULTS/$STAMP-fix"
mkdir -p "$OUT"
exec > >(tee "$OUT/progress.txt") 2>&1
trap 'rc=$?; trap - EXIT; finish_output; exit "$rc"' EXIT
MODEL=$(tr -d '\0' </proc/device-tree/model)
case "$MODEL" in
    'Microsoft Surface Laptop 7 (13.8 inch)'|'Microsoft Surface Laptop 7 (15 inch)') ;;
    *) echo "Unexpected machine: $MODEL. No changes made."; exit 1 ;;
esac
command -v update-initramfs >/dev/null
command -v sha256sum >/dev/null
EXPECTED=30ced6b4ba1968866ddf15c9d128860a9c0a44f430a41f278d9daa1a44e194b7
ORIGINAL_ZST=967bf1c70eff523be30dd4510920cd202c31cef0352c20dfc5d1d4bdafce29a9
ORIGINAL_RAW=1abee7132dbccb523cca44a8de4e8968aa7bf5a5fcc032c338f687f94ea5bf4e
hash() { sha256sum "$1" | cut -d' ' -f1; }
[[ $(hash "$KIT/firmware/board-2.bin") == "$EXPECTED" ]] || { echo 'Bundle firmware checksum failed'; exit 1; }
GPU_DIR=/usr/lib/firmware/updates/qcom/x1e80100/microsoft
GPU="$GPU_DIR/qcdxkmsuc8380.mbn"
GPU_LINK=Romulus/qcdxkmsuc8380.mbn
WIFI=/usr/lib/firmware/updates/ath12k/WCN7850/hw2.0/board-2.bin
BASE=/usr/lib/firmware/ath12k/WCN7850/hw2.0/board-2.bin
check_image() {
    lsinitramfs "/boot/initrd.img-$(uname -r)" >"$OUT/initramfs-files.txt"
    local rel
    for rel in updates/qcom/x1e80100/microsoft/qcdxkmsuc8380.mbn updates/ath12k/WCN7850/hw2.0/board-2.bin; do
        [[ -f "/usr/lib/firmware/$rel" ]] || continue
        grep -Fq "lib/firmware/$rel" "$OUT/initramfs-files.txt" || { echo "Missing from initramfs: $rel"; return 1; }
    done
}
DO_GPU=0
DO_WIFI=0
if [[ -f "$GPU_DIR/$GPU_LINK" ]]; then
    if [[ -e "$GPU" || -L "$GPU" ]]; then
        if cmp -s "$GPU" "$GPU_DIR/$GPU_LINK"; then
            echo 'GPU path already resolves to the expected firmware.'
        else
            echo 'GPU destination already exists with different content; leaving it untouched.'
        fi
    else
        DO_GPU=1
    fi
else
    echo 'Romulus GPU source firmware absent; GPU fix skipped.'
fi
if [[ -f "$WIFI" ]] && [[ $(hash "$WIFI") == "$EXPECTED" ]]; then
    echo 'Wi-Fi board alias already installed.'
elif [[ -e "$WIFI" || -L "$WIFI" || -e "$WIFI.zst" || -e "$WIFI.xz" ]]; then
    echo 'An existing Wi-Fi override was found; preserving it. Review diagnostics first.'
else
    MATCH=0
    if [[ -f "$BASE" ]]; then
        [[ $(hash "$BASE") == "$ORIGINAL_RAW" ]] && MATCH=1
    elif [[ -f "$BASE.zst" ]]; then
        [[ $(hash "$BASE.zst") == "$ORIGINAL_ZST" ]] && MATCH=1
    fi
    PCI_MATCH=0
    for d in /sys/bus/pci/devices/*; do
        if [[ $(cat "$d/vendor" 2>/dev/null) == 0x17cb && $(cat "$d/device" 2>/dev/null) == 0x1107 && $(cat "$d/subsystem_vendor" 2>/dev/null) == 0x17cb && $(cat "$d/subsystem_device" 2>/dev/null) == 0x1107 ]]; then PCI_MATCH=1; fi
    done
    CUSTOM=$(cat /sys/module/firmware_class/parameters/path 2>/dev/null || true)
    if (( MATCH && PCI_MATCH )) && [[ -z "$CUSTOM" ]]; then
        DO_WIFI=1
    else
        echo 'Wi-Fi source/PCI identity differs from the inspected machine, or a custom firmware path is active. Skipping Wi-Fi install.'
    fi
fi
STATE=/var/lib/sl7-kit
HOOK=/etc/initramfs-tools/hooks/sl7-kit-firmware
if [[ -e "$HOOK" || -L "$HOOK" ]]; then
    cmp -s "$HOOK" "$KIT/sl7-firmware-hook" || { echo 'Conflicting initramfs hook exists; no changes made.'; exit 1; }
fi
if (( DO_GPU == 0 && DO_WIFI == 0 )); then
    echo 'No new firmware changes.'
    if [[ -f "$STATE/pending-initramfs" ]]; then
        say 'Retrying initramfs generation from an earlier incomplete run.'
        update-initramfs -u -k "$(uname -r)"
        check_image
        rm -- "$STATE/pending-initramfs"
    fi
    echo 'If this is the post-reboot run, use: sudo bash run.sh collect'
    exit 0
fi
BACKUP="$STATE/backups/$STAMP"
mkdir -p "$BACKUP"
chmod 700 "$STATE" "$STATE/backups" "$BACKUP"
printf '%s\n' "$BACKUP" >"$STATE/latest-backup"
uname -r >"$BACKUP/kernel"
printf '%s\n' "$MODEL" >"$BACKUP/model"
# Originals remain in place. Save the actual original board container as well.
if [[ -f "$BASE" ]]; then cp -a "$BASE" "$BACKUP/base-board-2.bin"; fi
if [[ -f "$BASE.zst" ]]; then cp -a "$BASE.zst" "$BACKUP/base-board-2.bin.zst"; fi
touch "$STATE/pending-initramfs"
if [[ ! -e "$HOOK" ]]; then
    cp "$KIT/sl7-firmware-hook" "$BACKUP/hook-installed"
    touch "$BACKUP/hook-created"
    mkdir -p "$(dirname "$HOOK")"
    install -m 0755 "$KIT/sl7-firmware-hook" "$HOOK"
fi
if (( DO_GPU )); then
    cp -a "$GPU_DIR/$GPU_LINK" "$BACKUP/gpu-source.mbn"
    touch "$BACKUP/gpu-created"
    ln -s "$GPU_LINK" "$GPU"
    echo "Created GPU lookup link: $GPU"
fi
if (( DO_WIFI )); then
    mkdir -p "$(dirname "$WIFI")"
    touch "$BACKUP/wifi-created"
    TEMP=$(mktemp "$(dirname "$WIFI")/.sl7-board.XXXXXX")
    install -m 0644 "$KIT/firmware/board-2.bin" "$TEMP"
    mv -T -- "$TEMP" "$WIFI"
    echo "Installed Wi-Fi board alias: $WIFI"
fi
say "Backup: $BACKUP"
say 'Updating initramfs for the running kernel; this may take several minutes.'
update-initramfs -u -k "$(uname -r)"
check_image
rm -- "$STATE/pending-initramfs"
sync
say 'DONE. Reboot manually when ready: sudo reboot'
say 'After reboot: sudo bash run.sh collect'
say 'Then check Wi-Fi with: nmcli device status  (or use nmtui)'
say 'This fixes board-name lookup; an rfkill/kernel issue may still remain.'
