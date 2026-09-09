"""Run behavioral RTL tests; missing simulators are an error, never a pass.

Usage from any directory: python fpga/sim/run.py
Requires Icarus Verilog (iverilog and vvp on PATH). No FPGA tools or board needed.
"""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    compiler, simulator = shutil.which("iverilog"), shutil.which("vvp")
    if not compiler or not simulator:
        print("NOT RUN: install Icarus Verilog and add iverilog + vvp to PATH.", file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory(prefix="braille_rtl_") as output:
        executable = Path(output) / "test.vvp"
        build = subprocess.run(
            [compiler, "-g2012", "-Wall", "-s", "tb_blind_printer_core",
             "-o", str(executable), "-c", "rtl/files.f", "sim/tb_blind_printer_core.sv"],
            cwd=root, check=False,
        )
        if build.returncode:
            return build.returncode
        return subprocess.run([simulator, str(executable)], cwd=root, check=False).returncode


if __name__ == "__main__":
    sys.exit(main())
