#!/bin/bash
# Staging and signing only: never installs into the running OS or changes boot.
set -euo pipefail
project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
cd -- "$project_dir"
release=7.2.0-5-sl7
source_dir=$project_dir/kernel-source/linux-source-7.2.0
output_dir=$project_dir/kernel-build/sl7
stage_dir=$project_dir/kernel-package-root

[[ $(cat "$output_dir/include/config/kernel.release") == "$release" ]]
[[ -s $output_dir/Module.symvers && -s $output_dir/modules.order && -s $output_dir/vmlinux ]]
make_args=(-C "$source_dir" O="$output_dir" LOCALVERSION=-5-sl7 RUSTC=rustc-1.95 BINDGEN=bindgen)

nice -n 10 make "${make_args[@]}" -j8 vmlinuz.efi > logs/combined-zboot-build.log 2>&1
mkdir -p "$stage_dir"
# Disable automatic signing only while staging. The next step must sign every
# stripped module with the actual root-protected key before packaging.
nice -n 10 make "${make_args[@]}" -j4 modules_install \
    INSTALL_MOD_PATH="$stage_dir" INSTALL_MOD_STRIP=1 CONFIG_MODULE_SIG_ALL= \
    DEPMOD=/bin/true > logs/combined-module-staging.log 2>&1
sudo -n python3 "$project_dir/sign-combined-modules.py"

python3 - <<'PY'
from pathlib import Path
import concurrent.futures
import subprocess
root = Path('kernel-package-root/lib/modules/7.2.0-5-sl7')
modules = sorted((root / 'kernel').rglob('*.ko'))
def compress(path):
    subprocess.run(['zstd', '-q', '-8', '-T1', '--rm', '--', str(path)], check=True)
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    list(pool.map(compress, modules))
for name in ['build', 'source']:
    link = root / name
    if link.is_symlink():
        link.unlink()
print(f'Compressed {len(modules)} signed modules.')
PY
depmod -e -E "$output_dir/Module.symvers" -b "$stage_dir" "$release" > logs/combined-depmod.log 2>&1

sudo -n sbsign --key /var/lib/shim-signed/mok/sl7-kernel/BOOT.priv \
    --cert /var/lib/shim-signed/mok/sl7-kernel/BOOT.pem \
    --output "$project_dir/artifacts/sl7-inner-signed.efi" \
    "$output_dir/arch/arm64/boot/vmlinuz.efi"
mkdir -p "$project_dir/kernel-build/romulus13-hwids"
cp stubble-package/usr/share/stubble/hwids/x1e80100-microsoft-romulus13.json \
    kernel-build/romulus13-hwids/
python3 stubble-package/usr/bin/stubblify build \
    --stub="$project_dir/stubble-package/usr/lib/stubble/stubble.efi" \
    --linux="$project_dir/artifacts/sl7-inner-signed.efi" \
    --devicetree-auto="$output_dir/arch/arm64/boot/dts/qcom/x1e80100-microsoft-romulus13.dtb" \
    --hwids="$project_dir/kernel-build/romulus13-hwids" \
    --uname="$release" --no-sign-kernel \
    --output="$project_dir/artifacts/sl7-combined-unsigned.efi"
sudo -n sbsign --key /var/lib/shim-signed/mok/sl7-kernel/BOOT.priv \
    --cert /var/lib/shim-signed/mok/sl7-kernel/BOOT.pem \
    --output "$project_dir/artifacts/sl7-combined-signed.efi" \
    "$project_dir/artifacts/sl7-combined-unsigned.efi"
sbverify --cert artifacts/SL7-Kernel-BOOT.pem artifacts/sl7-inner-signed.efi
sbverify --cert artifacts/SL7-Kernel-BOOT.pem artifacts/sl7-combined-signed.efi
printf 'Signed kernel, embedded device tree and modules staged successfully.\n'
