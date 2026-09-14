#!/usr/bin/env python3
"""Check the complete staged module set and verify critical module signatures."""
from pathlib import Path
import hashlib
import importlib.util
import io
import json
import re
import struct
import tempfile
import zstandard
from elftools.elf.elffile import ELFFile

PROJECT = Path(__file__).resolve().parent
RELEASE = "7.2.0-5-sl7"
ROOT = PROJECT / "kernel-package-root/lib/modules" / RELEASE
CERT = PROJECT / "artifacts/SL7-WiFi-MOK.der"
CRITICAL = {"ath12k", "ath12k_wifi7", "spi_geni_qcom", "gpi", "spi_hid", "nvme", "surface_hid"}

spec = importlib.util.spec_from_file_location("module_verifier", PROJECT / "verify-module.py")
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


def version_tables(data):
    elf = ELFFile(io.BytesIO(data))
    legacy = {}
    section = elf.get_section_by_name("__versions")
    if section:
        raw = section.data()
        assert len(raw) % 64 == 0
        for offset in range(0, len(raw), 64):
            name = raw[offset + 8:offset + 64].split(b"\0", 1)[0].decode()
            legacy[name] = struct.unpack_from("<Q", raw, offset)[0]
    names_section = elf.get_section_by_name("__version_ext_names")
    crcs_section = elf.get_section_by_name("__version_ext_crcs")
    if names_section and crcs_section:
        names = names_section.data().rstrip(b"\0").split(b"\0")
        raw = crcs_section.data()
        crcs = struct.unpack("<" + "I" * (len(raw) // 4), raw)
        assert len(names) == len(crcs)
        return {name.decode(): crc for name, crc in zip(names, crcs)}, legacy
    return legacy, legacy


def main():
    manifest = json.loads((PROJECT / "logs/combined-module-signatures.json").read_text())
    expected = manifest["signed_elf_sha256"]
    files = sorted((ROOT / "kernel").rglob("*.ko.zst"))
    actual = {str(f.relative_to(ROOT))[:-4] for f in files}
    order = set((ROOT / "modules.order").read_text().splitlines())
    assert actual == set(expected) == order, "Staged modules, signing manifest and modules.order differ"
    symbols = verifier.symbol_table((PROJECT / "kernel-build/sl7/Module.symvers").read_text(), "Module.symvers")
    checks = {}
    all_imports_checked = 0
    warnings = {}
    log = PROJECT / "logs/combined-depmod.log"
    for line in log.read_text().splitlines():
        match = re.fullmatch(r"depmod: WARNING: (.+) disagrees about version of symbol (.+)", line)
        assert match, ("Unclassified depmod diagnostic", line)
        relative = str(Path(match.group(1)).relative_to(ROOT))[:-4]
        warnings.setdefault(relative, set()).add(match.group(2))
    explained = 0
    for file in files:
        data = zstandard.ZstdDecompressor().decompress(file.read_bytes())
        relative = str(file.relative_to(ROOT))[:-4]
        assert hashlib.sha256(data).hexdigest() == expected[relative], relative
        assert data.startswith(b"\x7fELF") and struct.unpack_from("<H", data, 18)[0] == 183, relative
        assert b"vermagic=" + RELEASE.encode() + b" " in data, relative
        assert data.endswith(b"~Module signature appended~\n"), relative
        # Match the kernel's preference for extended version tables. kmod 34.2
        # can select the legacy table and falsely reject long Rust symbol names.
        imports, legacy = version_tables(data)
        missing = sorted(set(imports) - set(symbols))
        mismatches = [n for n, crc in imports.items() if n in symbols and symbols[n] != crc]
        assert not missing and not mismatches, (relative, missing, mismatches)
        all_imports_checked += len(imports)
        for symbol in warnings.get(relative, set()):
            assert symbol not in legacy and imports[symbol] == symbols[symbol], (relative, symbol)
            explained += 1
        name = file.name.removesuffix(".ko.zst").replace("-", "_")
        if name not in CRITICAL:
            continue
        with tempfile.TemporaryDirectory(prefix="sl7-combined-check-") as dirname:
            temp = Path(dirname)
            raw = temp / "module.ko"
            raw.write_bytes(data)
            checks[name] = {
                "imported_symbols_checked": len(imports),
                "signature": verifier.signature_check(raw, CERT, temp),
            }
    assert set(checks) == CRITICAL, ("Missing critical modules", CRITICAL - set(checks))
    assert explained == sum(len(values) for values in warnings.values())
    embedded = PROJECT / "kernel-build/sl7/certs/signing_key.x509"
    assert embedded.read_bytes() == CERT.read_bytes(), "Built-in certificate mismatch"
    image = PROJECT / "kernel-build/sl7/arch/arm64/boot/Image"
    assert CERT.read_bytes() in image.read_bytes(), "Module certificate is absent from the built kernel image"
    report = {
        "ok": True, "release": RELEASE, "signed_modules_checked": len(files),
        "all_module_hashes_architectures_versions_and_signature_trailers_match": True,
        "all_imported_symbol_crcs_checked_using_kernel_version_table_rules": all_imports_checked,
        "depmod_legacy_table_false_positives_explained": explained,
        "module_public_certificate_embedded_in_kernel": True,
        "critical_module_cryptographic_and_symbol_checks": checks,
        "hardware_runtime_tested": False,
    }
    destination = PROJECT / "logs/combined-module-verification.json"
    destination.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Verified {len(files)} modules and {all_imports_checked} imported CRCs; {len(checks)} critical signatures; {explained} legacy-table tool false positives explained.")


if __name__ == "__main__":
    main()
