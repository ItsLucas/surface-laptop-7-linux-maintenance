#!/usr/bin/python3
"""Capture SL7 contact calibration, restoring the touch daemon on exit."""
from pathlib import Path
from datetime import datetime
import json
import argparse
import os
import re
import signal
import subprocess
import time

PROJECT = Path(__file__).resolve().parent
UNIT = "iptsd@dev-hidraw1.service"
DEVICE = Path("/dev/hidraw1")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=int, default=60, choices=range(20, 121), metavar='20..120')
    args = parser.parse_args()
    assert os.geteuid() == 0
    info = Path("/sys/class/hidraw/hidraw1/device/uevent").read_text()
    assert "HID_ID=001C:0000045E:00000C77" in info
    assert subprocess.check_output(["systemctl", "is-active", UNIT], text=True).strip() == "active"
    output = PROJECT / "calibration" / datetime.now().strftime("%Y%m%d-%H%M%S")
    output.mkdir(parents=True, mode=0o755)
    log = output / "capture.log"
    child = None
    timer = "sl7-iptsd-calibration-recover-" + str(os.getpid())
    subprocess.run(["systemd-run", "--quiet", "--unit=" + timer, f"--on-active={args.seconds + 40}s",
                    "/usr/bin/systemctl", "start", UNIT], check=True)
    try:
        subprocess.run(["systemctl", "stop", UNIT], check=True)
        with log.open("w") as stream:
            child = subprocess.Popen(["/usr/bin/iptsd-calibrate", str(DEVICE)],
                                     cwd=output, stdout=stream, stderr=subprocess.STDOUT)
            print(f"CALIBRATION_READY: move your fingers for {args.seconds} seconds now.", flush=True)
            for elapsed in range(args.seconds):
                if child.poll() is not None:
                    raise RuntimeError("Calibrator exited early; see " + str(log))
                time.sleep(1)
            samples = re.findall(r"Samples: (\d+)", log.read_text())
            if not samples or int(samples[-1]) == 0:
                child.kill()
                child.wait()
                raise RuntimeError("No contact samples: no calibration applied")
            child.send_signal(signal.SIGINT)
            try:
                code = child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
                raise RuntimeError("Calibrator did not stop promptly: no calibration applied")
            if code:
                raise RuntimeError("Calibration failed, exit " + str(code))
        generated = sorted(output.glob("iptsd_calib_045E_0C77_*mm.conf"))
        assert len(generated) == 3
        report = {"capture_directory": str(output), "samples": int(samples[-1]),
                  "generated": [str(f) for f in generated], "applied": False}
        (output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2), flush=True)
        for file in generated:
            print(file.name + "\n" + file.read_text(), flush=True)
    finally:
        if child is not None and child.poll() is None:
            child.kill()
            child.wait()
        subprocess.run(["systemctl", "start", UNIT], check=True)
        subprocess.run(["systemctl", "stop", timer + ".timer"], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("Touchpad daemon restored.", flush=True)


if __name__ == "__main__":
    main()
