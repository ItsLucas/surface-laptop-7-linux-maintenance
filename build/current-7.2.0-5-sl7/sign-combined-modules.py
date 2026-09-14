#!/usr/bin/env python3
"""Sign only staged SL7 modules, using the root-only module key."""
from pathlib import Path
import concurrent.futures
import hashlib
import json
import os
import struct
import subprocess

PROJECT = Path(__file__).resolve().parent
RELEASE = "7.2.0-5-sl7"
ROOT = PROJECT / "kernel-package-root/lib/modules" / RELEASE
KEY = Path("/var/lib/shim-signed/mok/sl7-wifi/MOK.priv")
CERT = Path("/var/lib/shim-signed/mok/sl7-wifi/MOK.der")
SIGN = Path("/usr/src/linux-headers-7.2.0-5-generic/scripts/sign-file")
MARKER = b"~Module signature appended~\n"


def sign(path):
    data = path.read_bytes()
    if not data.startswith(b"\x7fELF") or struct.unpack_from("<H", data, 18)[0] != 183:
        raise RuntimeError(f"Not an AArch64 ELF module: {path}")
    if b"vermagic=" + RELEASE.encode() + b" " not in data:
        raise RuntimeError(f"Module release mismatch: {path}")
    if data.endswith(MARKER):
        raise RuntimeError(f"Unexpected pre-existing signature: {path}")
    temporary = path.with_suffix(".ko.signed")
    subprocess.run([str(SIGN), "sha512", str(KEY), str(CERT), str(path), str(temporary)], check=True)
    signed = temporary.read_bytes()
    if not signed.endswith(MARKER):
        raise RuntimeError(f"Signing did not append a signature: {path}")
    temporary.chmod(0o644)
    os.replace(temporary, path)
    return str(path.relative_to(ROOT)), hashlib.sha256(signed).hexdigest()


if __name__ == "__main__":
    if os.geteuid() != 0:
        raise SystemExit("Run with sudo; the key remains root-only.")
    if not (ROOT / "modules.order").is_file():
        raise SystemExit("Staged module tree is incomplete.")
    modules = sorted((ROOT / "kernel").rglob("*.ko"))
    if not modules:
        raise SystemExit("No staged modules found.")
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        manifest = dict(pool.map(sign, modules))
    output = PROJECT / "logs/combined-module-signatures.json"
    output.write_text(json.dumps({"release": RELEASE, "signed_count": len(manifest), "signed_elf_sha256": manifest}, indent=2) + "\n")
    output.chmod(0o644)
    print(f"Signed {len(manifest)} modules for {RELEASE}.")
