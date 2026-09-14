#!/usr/bin/env python3
"""Read-only ABI and optional cryptographic signature checks for an ath12k module.

Usage: verify-module.py staged/ath12k.ko [--cert public-certificate.der]
No module is installed or loaded. Decompression and signature extraction use a
temporary directory. --cert verifies the detached signature with that exact
certificate; it does not establish that the running kernel trusts the key.
"""

import argparse
import gzip
import hashlib
import json
import lzma
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile


SIGNATURE_MAGIC = b"~Module signature appended~\n"


class VerificationError(Exception):
    pass


def run(*args):
    proc = subprocess.run(args, capture_output=True, text=True, check=False)
    if proc.returncode:
        detail = proc.stderr.strip() or proc.stdout.strip()
        raise VerificationError(f"{args[0]} failed ({proc.returncode}): {detail[:1200]}")
    return proc.stdout.strip()


def snapshot_module(source, destination):
    if source.suffix == ".zst":
        with destination.open("wb") as output:
            proc = subprocess.run(
                ["zstd", "--decompress", "--quiet", "--stdout", "--", str(source)],
                stdout=output, stderr=subprocess.PIPE, check=False,
            )
        if proc.returncode:
            raise VerificationError(proc.stderr.decode(errors="replace").strip())
    elif source.suffix in {".xz", ".gz"}:
        opener = lzma.open if source.suffix == ".xz" else gzip.open
        with opener(source, "rb") as inp, destination.open("wb") as out:
            shutil.copyfileobj(inp, out)
    else:
        shutil.copyfile(source, destination)
    return destination


def distro_module(base):
    candidates = [Path(str(base) + suffix) for suffix in (".ko", ".ko.zst", ".ko.xz", ".ko.gz")]
    found = [candidate for candidate in candidates if candidate.is_file()]
    if len(found) != 1:
        raise VerificationError(f"Expected one distribution module at {base}.ko[.zst/.xz/.gz]; found {found}")
    return found[0]


def architecture(path):
    with path.open("rb") as inp:
        header = inp.read(64)
    if len(header) < 20 or header[:4] != b"\x7fELF":
        raise VerificationError(f"Not an ELF module: {path.name}")
    if header[4] not in (1, 2) or header[5] not in (1, 2):
        raise VerificationError("Unsupported ELF class or byte order")
    machine = struct.unpack_from("<H" if header[5] == 1 else ">H", header, 18)[0]
    return {
        "machine": machine,
        "name": {183: "AArch64", 62: "x86-64", 40: "ARM"}.get(machine, f"ELF machine {machine}"),
        "bits": {1: 32, 2: 64}[header[4]],
        "byte_order": {1: "little", 2: "big"}[header[5]],
    }


def symbol_table(text, label):
    result = {}
    for line in text.splitlines():
        fields = line.split()
        if len(fields) < 2:
            raise VerificationError(f"Malformed {label} entry: {line}")
        crc, name = int(fields[0], 16), fields[1]
        if name in result and result[name] != crc:
            raise VerificationError(f"Conflicting CRCs for {name} in {label}")
        result[name] = crc
    if not result:
        raise VerificationError(f"No symbols read from {label}")
    return result


def symbols(path, exports=False):
    flag = "--show-exports" if exports else "--show-modversions"
    return symbol_table(run("modprobe", flag, str(path)), f"{path.name} {flag}")


def compare_symbols(actual, expected, exact):
    missing = sorted(expected.keys() - actual.keys())
    extra = sorted(actual.keys() - expected.keys()) if exact else []
    mismatches = [
        {"symbol": name, "actual": f"0x{actual[name]:08x}", "expected": f"0x{expected[name]:08x}"}
        for name in sorted(actual.keys() & expected.keys()) if actual[name] != expected[name]
    ]
    return {
        "ok": not (missing or extra or mismatches),
        "checked": len(expected),
        "missing_count": len(missing), "missing": missing[:10],
        "extra_count": len(extra), "extra": extra[:10],
        "crc_mismatch_count": len(mismatches), "crc_mismatches": mismatches[:10],
    }


def signature_check(path, cert, temp):
    data = path.read_bytes()
    result = {"present": data.endswith(SIGNATURE_MAGIC), "cryptographically_verified": False}
    if not result["present"]:
        if cert:
            raise VerificationError("--cert supplied, but the module has no appended signature")
        return result
    trailer_end = len(data) - len(SIGNATURE_MAGIC)
    trailer_start = trailer_end - 12
    if trailer_start < 0:
        raise VerificationError("Truncated module signature trailer")
    trailer = data[trailer_start:trailer_end]
    sig_len = int.from_bytes(trailer[8:12], "big")
    sig_start = trailer_start - sig_len
    if sig_len <= 0 or sig_start <= 0:
        raise VerificationError("Invalid module signature length")
    if trailer[:8] != b"\x00\x00\x02\x00\x00\x00\x00\x00":
        raise VerificationError("Unsupported signature trailer; expected detached PKCS#7")
    result["pkcs7_bytes"] = sig_len
    if cert:
        # Copy only the public certificate. No private key is read by this tool.
        der = temp / "certificate.der"
        shutil.copyfile(cert, der)
        pem = temp / "certificate.pem"
        run("openssl", "x509", "-inform", "DER", "-in", str(der), "-out", str(pem))
        payload = temp / "unsigned-module.bin"
        signature = temp / "module-signature.der"
        payload.write_bytes(data[:sig_start])
        signature.write_bytes(data[sig_start:trailer_start])
        # -nointern limits signer lookup to this exact supplied public cert.
        # -noverify skips CA-chain checking, not the actual content signature.
        run(
            "openssl", "cms", "-verify", "-binary", "-inform", "DER",
            "-in", str(signature), "-content", str(payload), "-certfile", str(pem),
            "-nointern", "-noverify", "-out", os.devnull,
        )
        result.update({
            "cryptographically_verified": True,
            "certificate_sha256": hashlib.sha256(der.read_bytes()).hexdigest(),
            "certificate_subject": run("openssl", "x509", "-inform", "DER", "-in", str(der), "-noout", "-subject"),
            "kernel_trust_checked": False,
        })
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("module", type=Path, help="Staged ath12k.ko; compression is also supported")
    parser.add_argument("--kernel-release", default=os.uname().release)
    parser.add_argument("--stock", type=Path, help="Distribution ath12k module path")
    parser.add_argument("--wifi7", type=Path, help="Distribution ath12k_wifi7 module path")
    parser.add_argument("--symvers", type=Path, help="Matching distribution headers' Module.symvers")
    parser.add_argument("--cert", type=Path, help="Exact DER public certificate for cryptographic verification")
    args = parser.parse_args()
    report = {"ok": False, "kernel_release": args.kernel_release, "errors": []}
    try:
        module_root = Path("/lib/modules") / args.kernel_release
        ath_root = module_root / "kernel/drivers/net/wireless/ath/ath12k"
        stock = args.stock or distro_module(ath_root / "ath12k")
        wifi7 = args.wifi7 or distro_module(ath_root / "wifi7/ath12k_wifi7")
        symvers = args.symvers or module_root / "build/Module.symvers"
        report["inputs"] = {"staged": str(args.module.resolve()), "stock": str(stock.resolve()), "wifi7": str(wifi7.resolve()), "symvers": str(symvers.resolve())}
        with tempfile.TemporaryDirectory(prefix="sl7-verify-module-") as dirname:
            temp = Path(dirname)
            staged_copy = snapshot_module(args.module, temp / "staged.ko")
            stock_copy = snapshot_module(stock, temp / "stock.ko")
            wifi7_copy = snapshot_module(wifi7, temp / "wifi7.ko")
            staged_magic = run("modinfo", "-F", "vermagic", str(staged_copy))
            stock_magic = run("modinfo", "-F", "vermagic", str(stock_copy))
            wifi7_magic = run("modinfo", "-F", "vermagic", str(wifi7_copy))
            staged_arch = architecture(staged_copy)
            stock_arch = architecture(stock_copy)
            wifi7_arch = architecture(wifi7_copy)
            staged_name = run("modinfo", "-F", "name", str(staged_copy))
            report["module"] = {
                "name": staged_name, "sha256": hashlib.sha256(staged_copy.read_bytes()).hexdigest(),
                "vermagic": staged_magic, "architecture": staged_arch,
                "srcversion": run("modinfo", "-F", "srcversion", str(staged_copy)),
                "signer_metadata": run("modinfo", "-F", "signer", str(staged_copy)),
            }
            staged_exports = symbols(staged_copy, exports=True)
            stock_exports = symbols(stock_copy, exports=True)
            staged_imports = symbols(staged_copy)
            wifi7_imports = symbols(wifi7_copy)
            kernel_symbols = symbol_table(symvers.read_text(), "Module.symvers")
            expected_imports = {name: kernel_symbols[name] for name in staged_imports if name in kernel_symbols}
            unknown_imports = sorted(staged_imports.keys() - kernel_symbols.keys())
            import_check = compare_symbols(staged_imports, expected_imports, exact=True)
            import_check.update({"import_count": len(staged_imports), "missing_from_symvers": unknown_imports[:10], "missing_from_symvers_count": len(unknown_imports)})
            wanted_exports = {name: wifi7_imports[name] for name in wifi7_imports.keys() & stock_exports.keys()}
            if not wanted_exports:
                raise VerificationError("No stock wifi7 dependencies on ath12k were identified")
            checks = {
                "name": {"ok": staged_name == "ath12k"},
                "vermagic": {"ok": bool(staged_magic) and staged_magic == stock_magic == wifi7_magic and staged_magic.split()[0] == args.kernel_release, "stock": stock_magic, "wifi7": wifi7_magic},
                "architecture": {"ok": staged_arch == stock_arch == wifi7_arch, "stock": stock_arch, "wifi7": wifi7_arch},
                "exports_match_stock": compare_symbols(staged_exports, stock_exports, exact=True),
                "imports_match_symvers": import_check,
                "stock_wifi7_abi": compare_symbols(staged_exports, wanted_exports, exact=False),
            }
            report["checks"] = checks
            report["signature"] = signature_check(staged_copy, args.cert, temp)
            report["errors"].extend(name for name, result in checks.items() if not result["ok"])
            report["ok"] = not report["errors"]
    except (VerificationError, OSError, ValueError, subprocess.SubprocessError) as exc:
        report["errors"].append(str(exc))
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
