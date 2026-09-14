#!/usr/bin/env bash
# Undo only files created by the latest kit fix; refuse if subsequently modified.
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
set -e
OUT="$RESULTS/$STAMP-undo"
mkdir -p "$OUT"
exec > >(tee "$OUT/progress.txt") 2>&1
trap 'rc=$?; trap - EXIT; finish_output; exit "$rc"' EXIT
STATE=/var/lib/sl7-kit
[[ -f "$STATE/latest-backup" ]] || { echo 'No kit backup found.'; exit 1; }
BACKUP=$(cat "$STATE/latest-backup")
[[ "$BACKUP" == "$STATE/backups/"* && -d "$BACKUP" ]] || { echo 'Invalid backup path'; exit 1; }
if [[ -f "$BACKUP/undone" ]]; then echo 'Already undone.'; exit 0; fi
GPU=/usr/lib/firmware/updates/qcom/x1e80100/microsoft/qcdxkmsuc8380.mbn
WIFI=/usr/lib/firmware/updates/ath12k/WCN7850/hw2.0/board-2.bin
HOOK=/etc/initramfs-tools/hooks/sl7-kit-firmware
if [[ -f "$BACKUP/hook-created" && ( -e "$HOOK" || -L "$HOOK" ) ]]; then
    cmp -s "$HOOK" "$BACKUP/hook-installed" || { echo 'Initramfs hook changed since fix; refusing to remove it.'; exit 1; }
fi
if [[ -f "$BACKUP/gpu-created" && ( -e "$GPU" || -L "$GPU" ) ]]; then
    [[ -L "$GPU" && $(readlink "$GPU") == Romulus/qcdxkmsuc8380.mbn ]] || { echo 'GPU destination changed since fix; refusing to remove it.'; exit 1; }
fi
if [[ -f "$BACKUP/wifi-created" && ( -e "$WIFI" || -L "$WIFI" ) ]]; then
    [[ ! -L "$WIFI" && $(sha256sum "$WIFI" | cut -d' ' -f1) == 30ced6b4ba1968866ddf15c9d128860a9c0a44f430a41f278d9daa1a44e194b7 ]] || { echo 'Wi-Fi destination changed since fix; refusing to remove it.'; exit 1; }
fi
[[ ! -f "$BACKUP/gpu-created" ]] || rm -f -- "$GPU"
[[ ! -f "$BACKUP/wifi-created" ]] || rm -f -- "$WIFI"
[[ ! -f "$BACKUP/hook-created" ]] || rm -f -- "$HOOK"
KERNEL=$(cat "$BACKUP/kernel")
[[ "$KERNEL" =~ ^[a-zA-Z0-9.+_-]+$ ]] || exit 1
update-initramfs -u -k "$KERNEL"
[[ "$KERNEL" == "$(uname -r)" ]] || update-initramfs -u -k "$(uname -r)"
rm -f -- "$STATE/pending-initramfs"
touch "$BACKUP/undone"
sync
say 'Kit-created overrides removed. Original firmware was never replaced. Reboot manually.'
