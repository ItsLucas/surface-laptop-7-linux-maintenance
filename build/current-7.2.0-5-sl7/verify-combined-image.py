#!/usr/bin/env python3
"""Verify the signed Stubble image, its inner kernel, and the exact SL7 DTB."""
from pathlib import Path
import hashlib
import json
import subprocess
import tempfile
import pefile

PROJECT = Path(__file__).resolve().parent
RELEASE = "7.2.0-5-sl7"
IMAGE = PROJECT / "artifacts/sl7-combined-signed.efi"
INNER = PROJECT / "artifacts/sl7-inner-signed.efi"
CERT = PROJECT / "artifacts/SL7-Kernel-BOOT.pem"
DTB = PROJECT / "kernel-build/sl7/arch/arm64/boot/dts/qcom/x1e80100-microsoft-romulus13.dtb"


def main():
    for path in [IMAGE, INNER]:
        subprocess.run(["sbverify", "--cert", str(CERT), str(path)], check=True)
    pe = pefile.PE(str(IMAGE))
    assert pe.FILE_HEADER.Machine == 0xAA64
    security = pe.OPTIONAL_HEADER.DATA_DIRECTORY[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_SECURITY"]]
    assert security.Size > 0
    sections = {}
    for section in pe.sections:
        name = section.Name.rstrip(b"\0").decode()
        sections.setdefault(name, []).append(section.get_data(length=section.Misc_VirtualSize))
    assert sections[".linux"] == [INNER.read_bytes()], "Inner signed kernel changed while wrapping"
    assert sections[".uname"][0].rstrip(b"\0").decode() == RELEASE
    assert len(sections[".dtbauto"]) == 1
    dtb = sections[".dtbauto"][0]
    assert dtb[:4] == b"\xd0\x0d\xfe\xed"
    dtb = dtb[:int.from_bytes(dtb[4:8], "big")]
    assert dtb == DTB.read_bytes(), "Embedded DTB differs from the compiled touchpad DTB"
    with tempfile.TemporaryDirectory(prefix="sl7-dtb-check-") as dirname:
        path = Path(dirname) / "romulus13.dtb"
        path.write_bytes(dtb)
        def prop(node, name):
            return subprocess.check_output(["fdtget", str(path), node, name], text=True).strip()
        spi = "/soc@0/geniqup@8c0000/spi@88c000"
        assert "microsoft,romulus13" in prop("/", "compatible").split()
        assert prop(spi, "status") == "okay"
        assert prop(spi, "compatible") == "qcom,geni-spi-qspi"
        assert prop(spi + "/touchpad@0", "compatible") == "hid-over-spi"
    hwids = json.loads((PROJECT / "logs/stubble-hwid-check.json").read_text())
    assert hwids["firmware_matches_bundled_romulus13_profile"]
    report = {
        "ok": True, "release": RELEASE,
        "outer_pe_sha256": hashlib.sha256(IMAGE.read_bytes()).hexdigest(),
        "inner_pe_sha256": hashlib.sha256(INNER.read_bytes()).hexdigest(),
        "dtb_sha256": hashlib.sha256(dtb).hexdigest(),
        "outer_and_inner_signatures_verified": True,
        "embedded_kernel_and_device_tree_match_staged_artifacts": True,
        "romulus13_hwid_match_count": hwids["romulus13_hwid_match_count"],
        "hardware_runtime_tested": False,
    }
    (PROJECT / "logs/combined-image-verification.json").write_text(json.dumps(report, indent=2) + "\n")
    print("Verified both PE signatures, exact inner kernel/DTB, touchpad nodes and machine-profile match.")


if __name__ == "__main__":
    main()
